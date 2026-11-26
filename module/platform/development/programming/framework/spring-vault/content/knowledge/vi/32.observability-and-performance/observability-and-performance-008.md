# Gộp yêu cầu theo lô khi engine hỗ trợ

## 1. Bài toán hiệu năng trong Spring Vault

Một ứng dụng Java dùng **Spring Vault** có thể gọi **VaultTemplate/VaultOperations** để đọc KV secrets, sử dụng Transit encryption, yêu cầu chứng thư PKI hoặc làm việc với token và lease. Với một khối lượng lớn dữ liệu, việc gọi Vault riêng lẻ cho từng item gây thêm lượt HTTP, độ trễ mạng, chi phí xác thực/routing và áp lực lên Vault.

**Gộp yêu cầu theo lô (batching)** là gửi nhiều phần tử **trong một request tới endpoint có hỗ trợ batch**, thay vì phát sinh một request cho mỗi phần tử. Ví dụ rõ ràng trong HashiCorp Vault là **Transit Secrets Engine**: các API encrypt, decrypt, rewrap và một số thao tác mật mã khác nhận trường **batch_input**. Spring Vault cung cấp phương thức batch tương ứng cho encrypt/decrypt/rewrap.

Mục tiêu của bài:

- Hiểu khác biệt giữa batching, concurrency và retry.
- Nhận diện endpoint hỗ trợ batch, tránh suy ra mọi secrets engine đều có batch.
- Tạo request mã hóa/giải mã danh sách bằng **VaultTransitOperations** trong Java.
- Bảo toàn thứ tự và định danh các item, kiểm tra lỗi từng phần tử lẫn lỗi toàn request.
- Thiết kế giới hạn batch size, byte size, thời gian chờ và concurrency.
- Đo latency, throughput, p95/p99, CPU, request count và tỷ lệ lỗi.
- Bảo vệ dữ liệu nhạy cảm, tuân thủ policy phân quyền theo workload và kiểm thử tích hợp.

Tình huống minh họa: dịch vụ **orders-api** cần mã hóa 70 chuỗi định danh đơn hàng trước khi lưu vào database. Các giá trị ví dụ như **order-001**, **order-002** là dữ liệu giả, không chứa bí mật thực.

## 2. Batch thực sự khác gửi nhiều request song song

~~~mermaid
flowchart TB
    subgraph Single["70 lời gọi riêng lẻ"]
        S["Ứng dụng"] --> R1["HTTP: encrypt item 1"]
        S --> R2["HTTP: encrypt item 2"]
        S --> R3["... 68 HTTP requests khác"]
    end
    subgraph Batch["Gộp 32 item/lô"]
        B["Ứng dụng"] --> T1["HTTP: batch 1 - 32 item"]
        B --> T2["HTTP: batch 2 - 32 item"]
        B --> T3["HTTP: batch 3 - 6 item"]
    end
~~~

Với ví dụ 70 item, nếu dùng giới hạn 32 item/lô, ứng dụng gửi **3 request batch** trong điều kiện không có lỗi hoặc retry. Nếu dùng 70 lời gọi đơn lẻ bằng **CompletableFuture**, đó vẫn là **70 request HTTP**, dù chúng chạy đồng thời.

Một mô hình lý thuyết có thể giúp hình dung:

- Gọi riêng lẻ N item: chi phí gần **N × (L + C)**.
- Gửi một batch N item: chi phí gần **L + N × C + B**.

Trong đó **L** là chi phí cố định mỗi request, **C** là chi phí tính toán một item và **B** là chi phí serialize/parse batch. Đây chỉ là mô hình giải thích; hiệu năng thật phụ thuộc Vault cluster, TLS, HSM, kích thước dữ liệu, concurrency, CPU và mạng. Batch có thể giảm round trip nhưng **không bỏ qua thao tác mật mã cho mỗi item**.

| Yếu tố | Gọi riêng lẻ | Batch request |
| --- | --- | --- |
| Số HTTP calls cho N item | N | Có thể còn 1 hoặc vài request |
| Chi phí request chung | Lặp lại nhiều lần | Ít lần hơn |
| Chi phí mật mã | Xử lý từng item | Vẫn xử lý từng item |
| Kích thước payload | Nhỏ mỗi request | Lớn hơn theo số item |
| Lỗi một item | Riêng request | Có thể thành lỗi từng phần tử |
| Thời gian item chờ | Không cần chờ gom | Có thể chờ đủ item hoặc max wait |
| Quan sát | Request latency | Cần đo request latency và item latency |
| Retry | Theo request | Phải xét kết quả đã thành công một phần |

**Không đánh đồng batching với cache:** batch giảm lượt gọi cho các item được xử lý cùng lúc; cache giảm số lần gọi khi có dữ liệu được phép tái sử dụng. Cache cho secret cần xét TTL, revoke, rotation và tính nhất quán riêng.

## 3. Chọn đúng engine và endpoint

**Batching chỉ hợp lệ khi contract của endpoint cho phép.** Không thể tự thêm **batch_input** vào một request bất kỳ rồi mong Vault thực hiện nhiều thao tác.

| Engine / nghiệp vụ | Hỗ trợ batch liên quan | Cách áp dụng |
| --- | --- | --- |
| **Transit encrypt/decrypt/rewrap** | Có **batch_input** và Spring Vault overload List | Phạm vi ví dụ chính |
| **Transit HMAC/sign/verify** | Một số endpoint HTTP có **batch_input** | Đọc đúng tài liệu thuật toán và schema |
| **KV v1/v2 đọc nhiều path** | API KV đọc chuẩn theo path, không có batch-get chung | Không giả lập batch bằng body đa path |
| **Database dynamic credentials** | Đọc credentials có thể phát hành lease mới | Không tự gom hoặc retry như đọc thuần túy |
| **PKI issue** | Phát hành certificate riêng theo role và request | Không mặc định có batch nếu endpoint không hỗ trợ |
| **Token/lease và wrapping** | Có vòng đời, quyền và tác dụng phụ riêng | Chọn API cụ thể, không trộn vào Transit batch |
| **System API** | Quản trị cấu hình, mount, auth, policy | Không gộp request quản trị tùy tiện |

Nếu sử dụng một plugin secrets engine hoặc phiên bản Vault riêng, hãy xác minh schema request/response từ tài liệu **đúng endpoint và đúng phiên bản**. Việc tăng concurrency không tạo thành API batch và có thể khiến cluster quá tải.

## 4. HTTP API Transit với batch_input

Giả sử quản trị viên đã bật Transit tại mount **transit** và tạo key **orders**. Các endpoint:

~~~text
POST /v1/transit/encrypt/orders
POST /v1/transit/decrypt/orders
POST /v1/transit/rewrap/orders
~~~

Một request mã hóa ba item:

~~~json
{
  "batch_input": [
    {"plaintext": "b3JkZXItMDAx", "reference": "item-001"},
    {"plaintext": "b3JkZXItMDAy", "reference": "item-002"},
    {"plaintext": "b3JkZXItMDAz", "reference": "item-003"}
  ]
}
~~~

Giá trị **plaintext** phải là **Base64 của byte plaintext** khi gọi Vault HTTP trực tiếp. Ba chuỗi trên tương ứng **order-001**, **order-002** và **order-003**. Base64 chỉ là encoding để truyền an toàn qua JSON, **không phải thuật toán bảo mật**.

Response thành công có hình dạng:

~~~json
{
  "data": {
    "batch_results": [
      {"ciphertext": "vault:v1:<demo-1>", "reference": "item-001"},
      {"ciphertext": "vault:v1:<demo-2>", "reference": "item-002"},
      {"ciphertext": "vault:v1:<demo-3>", "reference": "item-003"}
    ]
  }
}
~~~

**Các chuỗi có dấu < và > chỉ là placeholder mô tả**, không phải ciphertext hợp lệ để decrypt. Khi gọi Vault thật, các mục ciphertext chứa kết quả mã hóa do engine trả về.

Điểm cần nhớ:

1. **Một endpoint gắn với một key** thông qua tên **orders** trong URL. Các item dùng key khác phải nhóm sang request khác.
2. **batch_results giữ thứ tự** tương ứng với **batch_input**; raw HTTP hỗ trợ **reference** tùy chọn để đối chiếu.
3. Nếu key bật **derived key**, từng item có thể cần **context** đúng định dạng; context phải được giữ tương ứng khi decrypt.
4. Khi dùng **batch_input**, tham số plaintext/context cấp top-level có thể bị bỏ qua; phải điền đúng schema từng item.
5. Một phần tử sai có thể khiến **một item lỗi** trong khi phần tử khác thành công. Phần xử lý lỗi ở mục 8 là bắt buộc.

### Phân quyền theo workload

Chỉ cấp quyền cho path cần dùng:

~~~hcl
path "transit/encrypt/orders" {
  capabilities = ["update"]
}

path "transit/decrypt/orders" {
  capabilities = ["update"]
}
~~~

Service chỉ encrypt có thể **không cần** quyền decrypt. Batch không vượt qua ACL; Vault áp dụng policy cho endpoint như với lời gọi đơn. Không dùng root token trong ứng dụng.

Để thiết lập Vault lab (chỉ cho quản trị viên, và chỉ thực hiện khi mount/key chưa tồn tại):

~~~bash
vault secrets enable -path=transit transit
vault write -f transit/keys/orders
~~~

Không đưa thao tác bật mount và tạo key vào startup hook của ứng dụng nghiệp vụ. Ứng dụng chỉ dùng khóa đã được provisioning theo quy trình quản trị.

## 5. Gọi batch bằng Spring Vault

Spring Vault có phương thức:

~~~java
List<VaultEncryptionResult> encrypt(
        String keyName, List<Plaintext> batchRequest);

List<VaultDecryptionResult> decrypt(
        String keyName, List<Ciphertext> batchRequest);
~~~

Đây là overload thực của **VaultTransitOperations**. **Plaintext** và **Ciphertext** là value objects của Spring Vault; result object hỗ trợ **isSuccessful()**, **getCause()** và **get()**.

Ví dụ ngắn với Java 17:

~~~java
import java.nio.charset.StandardCharsets;
import java.util.List;

import org.springframework.vault.core.VaultOperations;
import org.springframework.vault.core.VaultTransitOperations;
import org.springframework.vault.support.Plaintext;
import org.springframework.vault.support.VaultEncryptionResult;

VaultTransitOperations transit = vaultOperations.opsForTransit();

List<Plaintext> input = List.of(
        Plaintext.of("order-001", StandardCharsets.UTF_8),
        Plaintext.of("order-002", StandardCharsets.UTF_8),
        Plaintext.of("Đơn hàng 003", StandardCharsets.UTF_8));

List<VaultEncryptionResult> encrypted = transit.encrypt("orders", input);

if (encrypted.size() != input.size()) {
    throw new IllegalStateException("Số kết quả batch không hợp lệ");
}

for (int i = 0; i < encrypted.size(); i++) {
    VaultEncryptionResult item = encrypted.get(i);

    if (!item.isSuccessful()) {
        throw new IllegalStateException(
                "Mã hóa lỗi tại index " + i, item.getCause());
    }

    // Giá trị cần lưu được lấy từ item.get().getCiphertext().
    // Không log ciphertext đầy đủ hoặc plaintext.
}
~~~

**Dùng UTF-8 rõ ràng** với **Plaintext.of(value, StandardCharsets.UTF_8)** để tránh khác biệt charset. Với dữ liệu nhị phân, có thể dùng **Plaintext.of(byte[])**. Spring Vault tự xử lý encoding cần thiết khi gọi Transit; không tự Base64 chuỗi rồi lại đưa vào **Plaintext.of**.

Nếu thao tác được thực hiện ở một mount khác **transit**, sử dụng **vaultOperations.opsForTransit(mountPath)**. Thư viện và authentication vẫn cần cấu hình Vault endpoint/TLS phù hợp.

## 6. Service Java chia lô 32 item và bảo toàn thứ tự

Ví dụ sau đặt **MAX_ITEMS_PER_BATCH = 32** như một **quyết định của ứng dụng**, không phải giới hạn mặc định do Vault quy định. Cả encrypt và decrypt đều chia danh sách thành nhiều lô, kiểm tra số lượng và trạng thái từng kết quả.

~~~java
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

import org.springframework.stereotype.Service;
import org.springframework.vault.core.VaultOperations;
import org.springframework.vault.core.VaultTransitOperations;
import org.springframework.vault.support.Ciphertext;
import org.springframework.vault.support.Plaintext;
import org.springframework.vault.support.VaultDecryptionResult;
import org.springframework.vault.support.VaultEncryptionResult;

@Service
public class OrderTransitBatchService {

    private static final String KEY_NAME = "orders";
    private static final int MAX_ITEMS_PER_BATCH = 32;

    private final VaultTransitOperations transit;

    public OrderTransitBatchService(VaultOperations operations) {
        this.transit = operations.opsForTransit();
    }

    public List<String> encrypt(List<String> values) {
        Objects.requireNonNull(values, "values");

        // Kiểm tra toàn bộ input trước khi gửi tới Vault.
        for (String value : values) {
            if (value == null || value.isEmpty()) {
                throw new IllegalArgumentException(
                        "Plaintext phải khác null và không rỗng");
            }
        }

        List<String> output = new ArrayList<>(values.size());

        for (int start = 0; start < values.size();
                start += MAX_ITEMS_PER_BATCH) {
            int end = Math.min(start + MAX_ITEMS_PER_BATCH, values.size());

            List<Plaintext> batch = new ArrayList<>(end - start);
            for (int i = start; i < end; i++) {
                batch.add(
                        Plaintext.of(values.get(i), StandardCharsets.UTF_8));
            }

            List<VaultEncryptionResult> results =
                    transit.encrypt(KEY_NAME, batch);

            if (results.size() != batch.size()) {
                throw new IllegalStateException(
                        "Transit trả thiếu hoặc thừa kết quả");
            }

            for (int i = 0; i < results.size(); i++) {
                VaultEncryptionResult result = results.get(i);

                if (!result.isSuccessful()) {
                    throw new IllegalStateException(
                            "Encrypt lỗi ở index " + (start + i),
                            result.getCause());
                }

                Ciphertext value = Objects.requireNonNull(result.get(),
                        "Thiếu ciphertext trong kết quả thành công");
                output.add(value.getCiphertext());
            }
        }
        return List.copyOf(output);
    }

    public List<String> decrypt(List<String> values) {
        Objects.requireNonNull(values, "values");

        List<String> output = new ArrayList<>(values.size());

        for (int start = 0; start < values.size();
                start += MAX_ITEMS_PER_BATCH) {
            int end = Math.min(start + MAX_ITEMS_PER_BATCH, values.size());

            List<Ciphertext> batch = new ArrayList<>(end - start);
            for (int i = start; i < end; i++) {
                batch.add(Ciphertext.of(values.get(i)));
            }

            List<VaultDecryptionResult> results =
                    transit.decrypt(KEY_NAME, batch);

            if (results.size() != batch.size()) {
                throw new IllegalStateException(
                        "Transit trả thiếu hoặc thừa kết quả decrypt");
            }

            for (int i = 0; i < results.size(); i++) {
                VaultDecryptionResult result = results.get(i);

                if (!result.isSuccessful()) {
                    throw new IllegalStateException(
                            "Decrypt lỗi ở index " + (start + i),
                            result.getCause());
                }

                Plaintext value = Objects.requireNonNull(result.get(),
                        "Thiếu plaintext trong kết quả thành công");
                output.add(value.asString(StandardCharsets.UTF_8));
            }
        }
        return List.copyOf(output);
    }
}
~~~

Ví dụ dùng trong logic ứng dụng:

~~~java
List<String> original = List.of(
        "order-001", "order-002", "Đơn hàng 003");

List<String> ciphertexts = batchService.encrypt(original);
List<String> recovered = batchService.decrypt(ciphertexts);

if (!original.equals(recovered)) {
    throw new IllegalStateException("Round-trip không khớp");
}
~~~

**Bảo toàn thứ tự:** Spring Vault trả danh sách kết quả tương ứng thứ tự input. Caller phải gắn vị trí **i** với **business ID** gốc. Nếu thay đổi thứ tự, lọc item hoặc nhóm lại theo key/tenant, cần lưu mapping ID → vị trí. Không được gán ciphertext cho bản ghi chỉ bằng cách giả định thứ tự database trả về giống thứ tự request.

**Giới hạn lỗi:** service trên tích lũy kết quả trong bộ nhớ và chỉ return khi hoàn thành, nhưng các request trước đó đã được Vault xử lý. Nếu batch thứ ba lỗi sau hai batch thành công, không có transaction chung ở phía Vault. Tầng lưu database phải quyết định ghi toàn bộ hay ghi theo nhóm với trạng thái riêng.

**Giới hạn kích thước:** mã đang giới hạn **số item**; môi trường production cần thêm **max bytes**, max wait, deadline và concurrency limit như mục 9.

## 7. Nhóm dữ liệu trước khi batch

Gộp tùy tiện mọi item thành một lô có thể vi phạm giới hạn bảo mật và gây sai kết quả.

~~~text
tenant-a / transit key orders-a -> batch A
tenant-b / transit key orders-b -> batch B

Một request /transit/encrypt/orders-a
không thể đồng thời dùng key orders-b.
~~~

Những thuộc tính cần xem khi nhóm:

- **Operation:** encrypt, decrypt và rewrap là những request khác nhau.
- **Mount + keyName:** endpoint gắn với một key đã được Vault quản lý.
- **Workload/tenant/security boundary:** không đưa dữ liệu của tenant khác vào cùng hàng đợi nếu điều đó làm lộ metadata hoặc sai chính sách cách ly.
- **Key configuration:** derived key hoặc convergent encryption có thể cần context/nonce đúng theo từng item.
- **Deadline:** item ưu tiên cao hoặc sắp hết thời gian không nên bị giữ quá lâu chỉ để đủ batch.
- **Payload size:** một item lớn có thể làm cả lô vượt ngưỡng byte.

Nếu khóa dùng derived key, tạo **Plaintext.with(VaultTransitContext)** cho mỗi item theo tài liệu Spring Vault. Giữ context tương ứng khi decrypt qua **Ciphertext.with(VaultTransitContext)**. Không tự dùng lại nonce với cùng khóa/context trong các chế độ yêu cầu nonce duy nhất.

## 8. Lỗi toàn request và lỗi từng phần tử

Một request batch cần kiểm tra cả **HTTP response** và **kết quả từng item**.

| Tình huống | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Token thiếu quyền **update** | Toàn request bị từ chối, thường 403 | Kiểm tra ACL workload; không tăng quyền tùy tiện |
| Mount/key sai | Toàn request thất bại | Đối chiếu mount/key/config |
| Vault timeout hoặc 5xx | Có thể không nhận được kết quả | Không retry toàn batch một cách mù quáng |
| Payload quá lớn | Request bị từ chối ở listener/proxy | Chia lô theo số item và byte |
| Một item có context/ciphertext sai | Có thể có thành công một phần | Xem index và error của từng item |
| Số lượng kết quả không khớp | Không thể map đúng với input | Dừng ghi dữ liệu và cảnh báo |
| Decrypt ra lỗi | Có thể do ciphertext/key/context không hợp lệ | Không thay bằng chuỗi rỗng, điều tra nguồn dữ liệu |

Ví dụ **raw HTTP response minh họa**, trong đó item thứ hai lỗi:

~~~json
{
  "data": {
    "batch_results": [
      {"ciphertext": "vault:v1:<success-1>"},
      {"error": "invalid input"},
      {"ciphertext": "vault:v1:<success-3>"}
    ]
  }
}
~~~

**Điểm rất quan trọng của Transit HTTP API:** tham số **partial_failure_response_code** cho encrypt/decrypt có giá trị mặc định **400** khi một số item lỗi nhưng item khác thành công. Do đó, dù Vault có dữ liệu **batch_results** trong raw response, HTTP client hoặc Spring Vault có thể ném exception do HTTP 400 **trước khi** cung cấp danh sách **VaultEncryptionResult** cho ứng dụng. Không được mặc định mã Java luôn nhận List trong trường hợp partial failure.

Nếu Spring Vault thực sự trả **List<VaultEncryptionResult>**, hãy kiểm tra **isSuccessful()**, **getCause()** và độ dài danh sách; **get()** của item lỗi có thể ném **VaultException**. Nếu HTTP request thất bại trước đó, bắt lỗi ở tầng gọi request và xử lý theo contract API/thư viện của phiên bản triển khai.

**Không coi partial success là thành công của cả lô.** Nếu nghiệp vụ yêu cầu all-or-nothing, chỉ ghi sau khi mọi phần tử được xác nhận. Nếu nghiệp vụ cho phép thành công một phần, cần cấu trúc kết quả riêng gồm business ID, trạng thái, mã lỗi được làm sạch và cơ chế xử lý lại cho từng item.

### Retry và idempotency

Với Transit encrypt thông thường, gửi lại cùng plaintext có thể sinh ciphertext khác do nonce ngẫu nhiên. Nếu lần gửi trước đã xử lý thành công nhưng client mất response, việc retry cả batch tạo thêm kết quả mật mã không chứng minh dữ liệu đã được ghi đúng.

Không gửi lại toàn lô chỉ vì timeout mà chưa xác định kết quả phía nghiệp vụ. Hãy gắn **ID nghiệp vụ** với mỗi phần tử, tách bước ghi database, và chỉ retry những phần có cơ chế idempotency/đối chiếu phù hợp. Đặc biệt, lỗi decrypt của một item không nên bị bỏ qua vì có thể liên quan ciphertext đã bị sửa hoặc context không khớp.

## 9. Giới hạn lô và hàng đợi để tránh quá tải

Gộp càng nhiều chưa chắc càng nhanh. Khi tăng batch size, kích thước request/response và thời gian chờ item có thể tăng đáng kể.

| Giới hạn cần đặt | Mục đích |
| --- | --- |
| **maxItems** | Chặn số phần tử trong một request |
| **maxBytes** | Giới hạn byte UTF-8 + Base64/JSON overhead |
| **maxWait** | Không để item đầu tiên chờ quá lâu để đủ lô |
| **maxConcurrentBatches** | Giới hạn số batch request đồng thời |
| **queueCapacity** | Chặn bộ nhớ tăng vô hạn khi Vault chậm |
| **request timeout** | Tránh HTTP call giữ thread vô hạn |
| **overall deadline** | Bao gồm cả chờ queue và thời gian Vault xử lý |
| **per-tenant quota** | Một tenant không chiếm hết tài nguyên batcher |

Mẫu flush phổ biến:

~~~text
flush khi đủ maxItems
HOẶC sắp vượt maxBytes (flush trước khi thêm item mới)
HOẶC oldestItemWait >= maxWait
~~~

Ngưỡng **32 item** trong ví dụ là lựa chọn minh họa của ứng dụng. Với item lớn, 32 item có thể vượt giới hạn byte. Base64 tăng kích thước dữ liệu truyền và JSON có overhead; Vault/proxy có thể áp dụng giới hạn request body. Tài liệu Transit mô tả giới hạn HTTP request mặc định trong bối cảnh server là **32 MB**, có thể được cấu hình lại; không thiết kế production sát ngưỡng đó.

**Giới hạn đồng thời cần được đo:** một batch 64 item vẫn tiêu tốn CPU mật mã cho 64 item. Nếu Transit dùng HSM hoặc Vault đang gần bão hòa, tăng kích thước lô hoặc số batch concurrent có thể khiến p99 cao hơn. Khi queue đầy, ưu tiên backpressure hoặc từ chối có kiểm soát thay vì nhận vô hạn.

Đối với luồng liên tục, chọn **maxWait nhỏ** để latency đầu cuối phù hợp với SLA; với xử lý offline, có thể dùng lô lớn hơn vì throughput thường quan trọng hơn thời gian phản hồi từng item.

## 10. Quan sát hiệu năng theo item và theo batch

Một HTTP batch chứa **32 item** tương ứng **1 request** và **32 phép xử lý**. Nếu chỉ nhìn requests/s sẽ dễ đánh giá sai throughput.

Các metric có thể xây dựng bằng **Micrometer** quanh lớp batcher:

| Metric gợi ý | Để trả lời |
| --- | --- |
| **vault_transit_batch_requests_total** | Bao nhiêu HTTP batch request thực tế? |
| **vault_transit_batch_items_total** | Bao nhiêu item được đưa vào batch? |
| **vault_transit_batch_size** | Phân phối item/request đang là bao nhiêu? |
| **vault_transit_batch_item_failures_total** | Có bao nhiêu item lỗi? |
| **vault_transit_batch_request_failures_total** | Có bao nhiêu request HTTP lỗi? |
| **vault_transit_batch_duration_seconds** | p50/p95/p99 latency của batch? |
| **vault_transit_item_latency_seconds** | Mỗi item mất bao lâu từ lúc vào queue đến kết quả? |
| **vault_transit_batch_queue_wait_seconds** | Item chờ để được gom lô bao lâu? |
| **vault_transit_batch_inflight** | Có bao nhiêu batch đang xử lý đồng thời? |
| **vault_transit_batch_payload_bytes** | Lô có đang gần ngưỡng byte? |
| **vault_transit_batch_retries_total** | Có phát sinh retry storm hay không? |

Đây là **tên metric đề xuất**, không phải metric Spring Vault tự tạo. Có thể đo bằng Timer, Counter và DistributionSummary, đồng thời đối chiếu với Vault telemetry và audit.

Phân biệt:

~~~text
item end-to-end latency =
  queue wait
  + concurrency wait
  + Vault HTTP round trip
  + parse result
  + lưu/tiêu thụ kết quả
~~~

Batch làm ít HTTP hơn nhưng có thể khiến item đầu tiên chờ gom dữ liệu. Vì vậy luôn đo **item latency p95/p99** bên cạnh **batch latency**, **items/s**, CPU và memory.

**Không gắn plaintext, full ciphertext, Vault token, tên secret nhạy cảm hoặc business ID tự do vào metric labels**. Nhãn nên có cardinality thấp như **operation=encrypt/decrypt**, **outcome=success/error**, **batch_size_bucket** và key group đã được phép quan sát.

## 11. Benchmark: chọn kích thước lô dựa trên số liệu

Thử nghiệm trên Vault lab với một khóa Transit, TLS và xác thực workload tương tự production:

1. Chuẩn bị cùng tập item giả, cùng kích thước và phân bố UTF-8 cho các lần đo.
2. Warm up JVM và HTTP connection pool, tránh tính việc tạo key vào latency.
3. So sánh các mức **batch size 1, 8, 16, 32, 64** dưới cùng concurrency và tổng số item.
4. Thu **HTTP requests**, **items/s**, **batch p50/p95/p99**, **item p50/p95/p99**, CPU/memory Vault và client.
5. Lặp lại ở lưu lượng thấp để phát hiện tác động của **maxWait**, sau đó tăng tải để tìm điểm bão hòa.
6. Đo tỷ lệ lỗi, partial failures, độ trễ proxy, ảnh hưởng HTTP timeout và retry.
7. Chọn cấu hình dựa trên SLO ứng dụng và kiểm tra lại sau khi rollout.

Ví dụ số request **lý thuyết** cho 320 item, giả định mọi batch được lấp đầy và không có lỗi:

| Batch size | Số request |
| ---: | ---: |
| 1 | 320 |
| 8 | 40 |
| 16 | 20 |
| 32 | 10 |
| 64 | 5 |

Đây chỉ là phép chia số item, **không phải benchmark throughput đã chạy**. Trong thực tế, khi flush do maxWait, chia nhóm theo key, retry hoặc lỗi, số request có thể cao hơn.

Nếu lưu lượng là **1 item mỗi 300 ms**, chờ đủ 32 item có thể tạo độ trễ rất lớn; lựa chọn gọi đơn hoặc flush theo thời gian sẽ phù hợp hơn. Với workload hàng triệu item offline, batch lớn hơn có thể có lợi nếu được kiểm tra dưới tải.

## 12. Kiểm thử tích hợp với Vault

Các ví dụ kiểm thử cần Vault test đã bật Transit, có khóa **orders**, và token có capability **update** trên **transit/encrypt/orders** và **transit/decrypt/orders**.

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.util.List;
import java.util.stream.IntStream;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest
class OrderTransitBatchServiceIT {

    @Autowired
    OrderTransitBatchService batchService;

    @Test
    void batchRoundTripPreservesOrderAndUnicode() {
        List<String> input = List.of(
                "order-001", "Đơn hàng 002", "order-003");

        List<String> encrypted = batchService.encrypt(input);
        List<String> restored = batchService.decrypt(encrypted);

        assertThat(encrypted).hasSize(input.size());
        assertThat(encrypted).allSatisfy(ciphertext ->
                assertThat(ciphertext).startsWith("vault:v"));
        assertThat(restored).containsExactlyElementsOf(input);
    }

    @Test
    void splitsSeventyItemsWithoutLosingOrder() {
        List<String> input = IntStream.range(0, 70)
                .mapToObj(i -> "order-" + i)
                .toList();

        assertThat(batchService.decrypt(batchService.encrypt(input)))
                .containsExactlyElementsOf(input);
    }
}
~~~

Bài test thứ hai dùng **70 item**, vượt ngưỡng 32 của service nên phải xử lý qua **3 batch**. Các assertion ở đây xác minh nội dung round-trip và thứ tự. Muốn xác nhận **chính xác 3 HTTP requests**, cần instrument HTTP client/proxy hoặc một test adapter đo số lời gọi vào Transit.

Các ca thử bổ sung:

| Ca thử | Kỳ vọng |
| --- | --- |
| Danh sách rỗng | Trả danh sách rỗng; không gọi Vault |
| Null/rỗng trong encrypt input | Bị từ chối trước khi tạo request |
| 32/33/64/65 item | Chia chunk đúng, giữ nguyên số lượng và thứ tự |
| Dữ liệu Unicode hoặc nhị phân | Giữ đúng UTF-8 hoặc byte[] |
| Token không có quyền | Request bị Vault từ chối, không có kết quả được ghi |
| Ciphertext/context sai | Báo lỗi item hoặc request; không trả chuỗi rỗng |
| Một item lỗi trong lô | Xác minh hành vi partial failure theo HTTP và Spring Vault |
| Timeout sau xử lý | Không retry toàn lô mù quáng |
| Byte limit vượt ngưỡng | Chia lô hoặc từ chối có kiểm soát trước request |
| Tải đồng thời cao | Queue/inflight/p99 không vượt budget |

### Kiểm tra partial failure thực tế

Dựng một request raw HTTP trong Vault test với ít nhất một item không hợp lệ và so sánh **status**, **batch_results** với behavior của Spring Vault. Vì mặc định partial failure của Transit có thể trả **HTTP 400**, đừng giả định phương thức Java luôn trả List khi request có item lỗi. Kiểm thử phải phân biệt **response HTTP lỗi** với **kết quả theo item** khi thư viện cung cấp được.

Không dùng secret production hoặc ghi body chứa plaintext/ciphertext vào test report. Khi thao tác thất bại, chỉ ghi loại lỗi, index, operation và correlation ID đã làm sạch.

## 13. Checklist đưa batching vào vận hành

1. Kiểm tra đúng **engine + endpoint** hỗ trợ batch, không giả định KV/PKI/token có batch chung.
2. Phân nhóm theo **mount, key, operation, tenant và context**, tuân thủ ACL workload.
3. Dùng **VaultTransitOperations.encrypt/decrypt(List)** với Plaintext/Ciphertext đúng kiểu và UTF-8 rõ ràng.
4. Kiểm tra **size/isSuccessful/getCause** từng item; xử lý cả HTTP error và partial failure.
5. Bảo toàn **business ID + index**, không đổi thứ tự hoặc ghi dở dang khi nghiệp vụ yêu cầu nguyên lô.
6. Giới hạn **maxItems, maxBytes, maxWait, queueCapacity, concurrent batches** và deadline tổng.
7. Không retry toàn batch nếu kết quả request trước còn mơ hồ; dùng cơ chế idempotency nghiệp vụ.
8. Không log plaintext, token, request body hoặc ciphertext đầy đủ; bảo vệ dữ liệu trong bộ nhớ và đường truyền TLS.
9. Benchmark theo **items/s, HTTP requests, item latency, batch latency, p95/p99, errors, CPU**.
10. Kiểm thử 70 item/chunk, Unicode, input sai, thiếu quyền, context sai, timeout và partial failure.

**Điểm cần ghi nhớ:** batching trong **SPRING_VAULT** thực sự hiệu quả khi **Vault secrets engine có API batch chính thức**, điển hình là **Transit batch_input**. Giảm số HTTP requests không đồng nghĩa bỏ qua chi phí mật mã hay tự bảo đảm tất cả item thành công. Một thiết kế tốt luôn đo latency cả ở mức batch và item, giới hạn tải và xử lý lỗi theo đúng kết quả từng phần tử.

## Tài liệu tham khảo chính thức

- [Spring Vault — VaultTransitOperations API](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/core/VaultTransitOperations.html).
- [Spring Vault — Plaintext API](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/support/Plaintext.html).
- [Spring Vault — Ciphertext API](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/support/Ciphertext.html).
- [Spring Vault — VaultEncryptionResult API](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/support/VaultEncryptionResult.html).
- [Spring Vault — VaultDecryptionResult API](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/support/VaultDecryptionResult.html).
- [HashiCorp Vault — Transit HTTP API](https://developer.hashicorp.com/vault/api-docs/secret/transit).
- [HashiCorp Vault — Transit Secrets Engine](https://developer.hashicorp.com/vault/docs/secrets/transit).
