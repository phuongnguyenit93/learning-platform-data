# Thao tác theo lô và kiểm tra kết quả từng mục

## 1. Bối cảnh và mục tiêu

Một ứng dụng Java có thể cần mã hóa hàng nghìn trường dữ liệu nhạy cảm khi nhập dữ liệu, di trú cơ sở dữ liệu, xoay vòng khóa hoặc xử lý thông điệp. Nếu mỗi mục tạo một HTTP request đến HashiCorp Vault, chi phí mạng và thời gian chờ có thể tăng đáng kể. Ngược lại, nếu gộp nhiều mục vào một request mà chỉ kiểm tra mã HTTP, chương trình dễ bỏ sót **một số mục đã thất bại**, hoặc bỏ mất những mục đã thành công khi cả request được gắn mã lỗi.

Trong module **Spring Vault (SPRING_VAULT)**, ứng dụng Java dùng `VaultTemplate`/`VaultOperations`, authentication theo workload và Vault policy để truy cập các secrets engine. Bài này thuộc chương **Engine mở rộng**, giải thích cách thực hiện **thao tác theo lô và kiểm tra kết quả từng mục**, lấy **Transit batch API** làm ví dụ chính.

Kết thúc bài, bạn có thể:

- Phân biệt API batch do engine cung cấp với việc Java tự lặp qua nhiều HTTP request.
- Sử dụng `batch_input`, `batch_results` và `reference` trong Transit.
- Xác định lỗi từng mục, lỗi toàn request và kết quả thành công một phần.
- Gọi batch qua Spring Vault, ánh xạ chính xác kết quả với bản ghi nguồn.
- Xử lý retry, phân quyền, giám sát, timeout và kiểm thử tích hợp một cách an toàn.

## 2. Thao tác theo lô không có cùng ý nghĩa ở mọi engine

Vault có nhiều loại secrets engine. Không thể mặc định mọi endpoint hỗ trợ một trường chung `batch_input`. Phải đọc hợp đồng của từng API trước khi áp dụng.

| Kiểu thực hiện | Cơ chế | Điểm cần chú ý |
| --- | --- | --- |
| **Batch API trong engine** | Một request chứa nhiều item và nhận nhiều kết quả | Có thể có lỗi trên từng item; cần kiểm tra response schema |
| **Batch do ứng dụng tự điều phối** | Java gửi nhiều request đơn lẻ, có giới hạn song song | Mỗi request có status, timeout, lease và retry riêng |
| **Workflow nhiều secrets engine** | Ví dụ đọc KV, mã hóa Transit rồi cấp PKI | Không tự có giao dịch nguyên tử giữa các engine |
| **Batch cập nhật cơ sở dữ liệu** | JDBC batch sau khi gọi Vault | Thành công của Vault không bảo đảm DB đã commit |

**Transit** hỗ trợ `batch_input` ở các endpoint như `encrypt`, `decrypt` và `rewrap`. Một số thao tác HMAC/chữ ký cũng hỗ trợ xử lý theo lô nhưng trường đầu vào và đầu ra khác nhau. Trong khi đó, **KV** không cung cấp cùng một API batch đa path tổng quát; nếu cần đọc nhiều secret, ứng dụng phải điều phối theo API tương ứng. **PKI** và **dynamic secrets** có thể tạo chứng thư, token/lease hoặc credential mới; khi tự gửi nhiều request, lỗi và retry phải xét riêng từng credential.

Bài này sử dụng Transit để làm rõ mô hình kết quả từng mục, sau đó rút ra nguyên tắc áp dụng rộng hơn.

## 3. Request và response batch của Transit

### 3.1. Gửi nhiều giá trị tới cùng một key

Giả sử quản trị viên đã bật Transit tại mount `transit` và tạo khóa `orders-pii`. Workload có policy gọi endpoint mã hóa. Request:

~~~http
POST /v1/transit/encrypt/orders-pii
X-Vault-Token: <WORKLOAD_TOKEN>
Content-Type: application/json

{
  "batch_input": [
    { "reference": "row-101", "plaintext": "YWxpY2U=" },
    { "reference": "row-102", "plaintext": "Ym9i" },
    { "reference": "row-103", "plaintext": "Y2Fyb2w=" }
  ]
}
~~~

Mỗi `plaintext` là **Base64 của byte dữ liệu gốc**: ví dụ `YWxpY2U=` biểu diễn `alice`. Base64 chỉ là cách biểu diễn byte trong JSON, **không bảo mật dữ liệu**. Với dữ liệu văn bản, dùng UTF-8 nhất quán; với dữ liệu nhị phân, encode trực tiếp `byte[]`.

`reference` là mã do phía ứng dụng cung cấp, được Vault đưa vào kết quả tương ứng. Dùng mã bản ghi không nhạy cảm, duy nhất trong lô; không đưa email, token hay bản rõ vào reference.

Một response minh họa:

~~~json
{
  "data": {
    "batch_results": [
      { "reference": "row-101", "ciphertext": "vault:v1:<A>" },
      { "reference": "row-102", "ciphertext": "vault:v1:<B>" },
      { "reference": "row-103", "ciphertext": "vault:v1:<C>" }
    ]
  }
}
~~~

Các chuỗi `<A>`, `<B>`, `<C>` chỉ là placeholder, không phải ciphertext thật. Vault trả ciphertext dạng `vault:v1:...` (phiên bản key có thể khác).

**Bất biến quan trọng:** Transit giữ **thứ tự** `batch_results` tương ứng với `batch_input`. Nếu dùng `reference`, kết quả cũng mang giá trị đó. Ứng dụng nên kiểm tra **độ dài mảng, thứ tự và reference**, sau đó mới ghi kết quả về đúng bản ghi. Nếu thiếu item, sai reference hoặc response hỏng, phải chặn việc cập nhật dữ liệu.

### 3.2. Một batch không phải transaction nguyên tử

Một batch có thể gồm mục thành công và mục lỗi, chẳng hạn một mục có Base64 sai hoặc thiếu `context` của khóa dẫn xuất. Không được coi một request là all-or-nothing. Phía Java cần phân loại **từng mục**, ngay cả khi toàn lô dùng chung một mã HTTP.

~~~mermaid
flowchart TD
    A[Đọc các item cần xử lý] --> B[Chia lô theo key và thao tác]
    B --> C[Gửi Vault batch_input]
    C --> D{Nhận phản hồi có thể đọc?}
    D -- Không/timeout --> U[UNKNOWN: đối soát request]
    D -- Có --> E[Đọc data.batch_results]
    E --> F[So khớp số lượng, vị trí, reference]
    F --> G{Mỗi item trả gì?}
    G -- ciphertext/plaintext hợp lệ --> H[SUCCEEDED: lưu item]
    G -- error --> I[FAILED_INPUT: phân loại và xử lý]
    G -- Thiếu/sai schema --> U
    H --> J[Ghi trạng thái và metrics từng item]
    I --> J
~~~

## 4. Kiểm tra kết quả và lỗi của từng phần tử

### 4.1. Response thành công một phần

Ví dụ mục thứ hai lỗi, nhưng mục thứ nhất và thứ ba đã có ciphertext:

~~~json
{
  "data": {
    "batch_results": [
      {
        "reference": "row-101",
        "ciphertext": "vault:v1:<A>"
      },
      {
        "reference": "row-102",
        "error": "invalid input"
      },
      {
        "reference": "row-103",
        "ciphertext": "vault:v1:<C>"
      }
    ]
  }
}
~~~

Thông điệp `invalid input` ở đây chỉ mang tính minh họa. Tên trường `error` là điểm cần kiểm tra; nội dung lỗi cụ thể có thể thay đổi theo phiên bản Vault. Với mục thành công, phải kiểm tra `ciphertext` là chuỗi hợp lệ. Với mục có `error`, không lưu ciphertext giả hoặc đánh dấu thành công.

### 4.2. Phân biệt HTTP status và trạng thái mỗi item

Trên các endpoint Transit hỗ trợ `partial_failure_response_code`, nếu chỉ một số item thất bại, **HTTP 400 có thể được trả theo mặc định**, mặc dù response chứa kết quả thành công của những item khác. Có thể yêu cầu một mã khác, ví dụ **207**, để xử lý partial failure:

~~~json
{
  "partial_failure_response_code": 207,
  "batch_input": [
    { "reference": "row-101", "plaintext": "YWxpY2U=" },
    { "reference": "row-102", "plaintext": "!!!invalid!!!" },
    { "reference": "row-103", "plaintext": "Y2Fyb2w=" }
  ]
}
~~~

Điều này **không** có nghĩa mọi lỗi sẽ nhận HTTP 207. Nếu tất cả phần tử lỗi, key/mount sai, token hết hạn, policy không cho phép hoặc request bị từ chối trước khi xử lý, Vault vẫn có thể trả mã lỗi HTTP thông thường.

| Quan sát | Điều có thể kết luận | Xử lý cần thiết |
| --- | --- | --- |
| HTTP 2xx và mọi mục trong `batch_results` hợp lệ | Đã có kết quả từng mục theo response | Lưu các mục đã xác minh |
| HTTP 207 và có cả `ciphertext`/`error` | Partial failure trên API có hỗ trợ mã này | Tách thành công/thất bại từng mục |
| HTTP 400 nhưng body có `batch_results` | Có thể đã xử lý thành công một số mục | Đọc body trước khi quyết định retry |
| HTTP 400/403/404 không có results hợp lệ | Lỗi ở mức request hoặc cấu hình | Không phán đoán trạng thái từng mục |
| HTTP 429/5xx hoặc timeout | Hạ tầng lỗi hoặc trạng thái không chắc chắn | Giữ `UNKNOWN` và đối soát |
| Thiếu item, sai reference hoặc response hỏng | Không thể ánh xạ an toàn | Không ghi kết quả vào DB |

**Lưu ý về Spring Vault:** nhiều HTTP client ném exception với status 400 trước khi code nghiệp vụ đọc response body. Do đó dùng `partial_failure_response_code=207` khi endpoint và phiên bản đã xác minh hỗ trợ, hoặc cấu hình cách đọc body lỗi phù hợp. Không được bắt exception rồi retry toàn lô mà không xem xét phần đã xử lý.

### 4.3. Lỗi đầu vào và lỗi toàn request

Một mục lỗi Base64 là tình huống khác hẳn token thiếu policy. Cách xử lý thường là:

- **Lỗi input per item:** sửa input/context/ciphertext của đúng mục và retry mục đó nếu thích hợp.
- **Lỗi auth, key hoặc mount:** dừng cả lô, kiểm tra workload authentication và cấu hình; không tự cấp quyền rộng hơn.
- **Lỗi mạng/tải:** retry có backoff và giới hạn sau khi đánh giá trạng thái trước đó.
- **Sai schema/ghép sai reference:** báo lỗi hợp đồng; đặc biệt cần tránh gán ciphertext của khách hàng này cho khách hàng khác.

## 5. Spring Vault: adapter mã hóa theo lô

Ví dụ Java 17+ dùng `VaultOperations`, do `VaultTemplate` triển khai. Client phải được cấu hình TLS, endpoint HTTPS và `ClientAuthentication` theo workload. Phía Java truyền path **không có prefix `/v1/`**.

### 5.1. Định nghĩa dữ liệu

~~~java
package com.example.orders.crypto;

public record EncryptInput(String itemId, String value) {}

public record EncryptOutcome(
        String itemId,
        boolean success,
        String ciphertext,
        String errorCategory) {}
~~~

ID phải ổn định, duy nhất trong lô và không nhạy cảm. `errorCategory` là nhãn chuẩn hóa thay vì nguyên văn lỗi từ Vault.

### 5.2. Gửi batch và kiểm tra tất cả mục

~~~java
package com.example.orders.crypto;

import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.Base64;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;

import org.springframework.stereotype.Service;
import org.springframework.vault.core.VaultOperations;
import org.springframework.vault.support.VaultResponse;

@Service
public final class TransitBatchEncryptionService {
    private static final String ENCRYPT_PATH = "transit/encrypt/orders-pii";

    private final VaultOperations vault;

    public TransitBatchEncryptionService(VaultOperations vault) {
        this.vault = vault;
    }

    public List<EncryptOutcome> encryptBatch(List<EncryptInput> inputs) {
        Objects.requireNonNull(inputs, "inputs");

        if (inputs.isEmpty()) {
            return List.of();
        }
        if (inputs.size() > 100) {
            throw new IllegalArgumentException("Batch too large");
        }

        Set<String> seen = new HashSet<>();
        List<Map<String, String>> batch = new ArrayList<>();

        for (EncryptInput input : inputs) {
            Objects.requireNonNull(input, "item");
            Objects.requireNonNull(input.itemId(), "itemId");
            Objects.requireNonNull(input.value(), "value");

            if (input.itemId().isBlank() || !seen.add(input.itemId())) {
                throw new IllegalArgumentException("Duplicate/blank itemId");
            }

            String b64 = Base64.getEncoder().encodeToString(
                    input.value().getBytes(StandardCharsets.UTF_8));
            batch.add(Map.of(
                    "reference", input.itemId(),
                    "plaintext", b64));
        }

        // Endpoint Transit hỗ trợ trả HTTP 207 khi một phần thất bại.
        // Lỗi toàn request vẫn có thể khiến Spring Vault throw.
        VaultResponse response = vault.write(
                ENCRYPT_PATH,
                Map.of(
                        "batch_input", batch,
                        "partial_failure_response_code", 207));

        if (response == null || response.getData() == null) {
            throw new IllegalStateException("Missing Transit data");
        }

        Object raw = response.getData().get("batch_results");
        if (!(raw instanceof List<?> results)
                || results.size() != inputs.size()) {
            throw new IllegalStateException("Invalid batch_results length");
        }

        List<EncryptOutcome> outcomes = new ArrayList<>();

        for (int i = 0; i < results.size(); i++) {
            if (!(results.get(i) instanceof Map<?, ?> item)) {
                throw new IllegalStateException("Invalid item shape");
            }

            String id = inputs.get(i).itemId();
            if (!id.equals(item.get("reference"))) {
                throw new IllegalStateException("Reference mismatch");
            }

            Object error = item.get("error");
            if (error instanceof String message && !message.isBlank()) {
                outcomes.add(new EncryptOutcome(
                        id, false, null, "ITEM_REJECTED"));
                continue;
            }

            Object value = item.get("ciphertext");
            if (!(value instanceof String ciphertext)
                    || !ciphertext.startsWith("vault:v")) {
                throw new IllegalStateException("Missing ciphertext");
            }

            outcomes.add(new EncryptOutcome(
                    id, true, ciphertext, null));
        }

        return List.copyOf(outcomes);
    }
}
~~~

Phần quan trọng là **đối chiếu kích thước và reference trước khi trả kết quả**. Trong trường hợp `batch_results` không đúng cấu trúc, adapter ném exception, để tầng điều phối không vô tình ghi sai dữ liệu.

Giới hạn 100 item chỉ là **ngưỡng ví dụ do ứng dụng lựa chọn**, không phải giới hạn mặc định của Vault. Trong production cần giới hạn cả **kích thước byte request** và số batch đồng thời.

Ví dụ cố ý chưa triển khai tầng retry/DB. Nếu HTTP 400 trả body partial failure, một cấu hình Spring Vault mặc định có thể ném exception; cần cơ chế đọc body lỗi của REST client hoặc dùng 207 theo API/version trước khi có thể phân loại từng item. Mọi ngoại lệ trước khi đọc kết quả phải được ghi nhận là trạng thái **chưa đủ bằng chứng**, không tự gán tất cả item thất bại.

### 5.3. Ghi kết quả vào cơ sở dữ liệu

~~~java
List<EncryptInput> items = List.of(
        new EncryptInput("c101", "An"),
        new EncryptInput("c102", "Bình"),
        new EncryptInput("c103", "Chi"));

List<EncryptOutcome> results = batchService.encryptBatch(items);

for (EncryptOutcome result : results) {
    if (result.success()) {
        // Chỉ cập nhật đúng bản ghi theo itemId.
        repository.saveEncryptedValue(
                result.itemId(), result.ciphertext());
    } else {
        repository.markFailed(
                result.itemId(), result.errorCategory());
    }
}
~~~

Đây là phác thảo của tầng nghiệp vụ, `repository` là interface do ứng dụng tự xây dựng. Hãy dùng transaction/optimistic locking khi lưu để tránh ghi đè các cập nhật đồng thời. Nếu Vault đã trả thành công nhưng DB ghi lỗi, phải ghi nhận tình huống này để xử lý lại an toàn.

## 6. Các thao tác batch khác: decrypt, rewrap, HMAC

Với **batch decrypt**, request dùng field `ciphertext`:

~~~json
{
  "batch_input": [
    { "reference": "row-101", "ciphertext": "vault:v1:<A>" },
    { "reference": "row-102", "ciphertext": "vault:v1:<B>" }
  ],
  "partial_failure_response_code": 207
}
~~~

Endpoint là `POST /v1/transit/decrypt/orders-pii`. Kết quả thành công trong `batch_results[i].plaintext` là Base64 của byte đã giải mã. Chỉ chuyển sang UTF-8 nếu dữ liệu ban đầu thật sự là văn bản. Không trả chuỗi rỗng cho item lỗi.

Với **batch rewrap**, endpoint `POST /v1/transit/rewrap/orders-pii` nhận ciphertext cũ và trả ciphertext mới theo key version đang được sử dụng. Vault xử lý giải mã/mã hóa lại nội bộ; response rewrap không đưa plaintext về ứng dụng. Một job migration có thể chỉ cần quyền `rewrap` rồi ghi ciphertext mới bằng optimistic locking.

| API | Input mỗi mục | Output thành công | Quyền Vault tối thiểu |
| --- | --- | --- | --- |
| `transit/encrypt/orders-pii` | `plaintext` Base64 | `ciphertext` | `update` trên encrypt |
| `transit/decrypt/orders-pii` | `ciphertext` | `plaintext` Base64 | `update` trên decrypt |
| `transit/rewrap/orders-pii` | `ciphertext` cũ | `ciphertext` mới | `update` trên rewrap |
| Transit HMAC/sign | `input` Base64 và tham số riêng | `hmac` hoặc `signature` | Quyền tương ứng endpoint |

Không được xem kết quả HMAC/sign như ciphertext, cũng không suy luận mọi endpoint cùng hỗ trợ các tham số giống nhau. Với **derived keys**, từng mục phải cung cấp `context` Base64 đúng với dữ liệu đã mã hóa. Nếu dùng **convergent encryption**, cần đánh giá rủi ro rò rỉ thông tin về các giá trị trùng nhau và yêu cầu nonce riêng; không bật chế độ này chỉ để tiện tìm kiếm dữ liệu.

## 7. Phân quyền và danh tính workload

Batch vẫn chịu kiểm soát của Vault policy. Job chỉ mã hóa nên có quyền tối thiểu:

~~~hcl
path "transit/encrypt/orders-pii" {
  capabilities = ["update"]
}
~~~

Job chỉ rewrap dùng policy riêng:

~~~hcl
path "transit/rewrap/orders-pii" {
  capabilities = ["update"]
}
~~~

Một job mã hóa không cần quyền quản lý `transit/keys/*` và không cần quyền decrypt nếu không có nghiệp vụ giải mã. Trong Kubernetes, dùng danh tính ServiceAccount và Kubernetes auth role để cấp token Vault theo workload; trong các môi trường khác cân nhắc AppRole hoặc JWT/OIDC. Không hardcode token root hoặc để token trong log/CI artifact.

**TTL của Vault authentication token** quyết định khi nào workload được gọi Vault. Nó khác với key version Transit và **lease của dynamic secrets** ở các engine khác. Với job chạy dài, cần quản lý token renewal/re-login và phân loại 403 là lỗi quyền/xác thực ở **mức request**.

## 8. Retry theo mục và trạng thái nhất quán

### 8.1. Không retry cả batch mà bỏ qua kết quả cũ

Transit encrypt mặc định dùng nonce ngẫu nhiên, nên mã hóa cùng plaintext hai lần có thể tạo **ciphertext khác nhau**. Retry tùy tiện có thể ghi đè ciphertext trước đó và gây mất vết audit. Với API PKI hoặc cấp dynamic credential, retry còn có thể tạo nhiều chứng thư/lease. Vì vậy phải xét **tác dụng phụ của từng API**, không dùng chung một quy tắc retry mù cho tất cả engine.

Nên lưu trạng thái theo `jobId` + `itemId`:

| Trạng thái | Ý nghĩa | Bước tiếp theo |
| --- | --- | --- |
| `PENDING` | Chưa gửi | Chọn vào batch |
| `IN_FLIGHT` | Đã gửi, đang chờ | Ngăn worker khác xử lý trùng |
| `SUCCEEDED` | Có kết quả hợp lệ và đã lưu | Không xử lý lại nếu không có yêu cầu mới |
| `FAILED_INPUT` | Lỗi dữ liệu của mục | Sửa input, chỉ thử lại mục tương ứng |
| `FAILED_AUTH_OR_CONFIG` | Lỗi policy/key/mount của request | Dừng job, sửa cấu hình |
| `UNKNOWN` | Timeout hoặc không có kết quả đáng tin | Đối soát trước khi retry |
| `PERSIST_FAILED` | Vault trả thành công, DB chưa lưu | Khôi phục kết quả hoặc xử lý lại có điều kiện |

Ví dụ job đã encrypt 90/100 mục, 10 mục sai Base64. Chỉ 10 mục cần sửa rồi gửi lại, không cần gộp 90 mục thành công vào batch mới. Nếu timeout trước khi nhận response, không biết chắc Vault đã hoàn thành mục nào: với encrypt có thể lập kế hoạch tính lại có kiểm soát và không ghi đè sai; với thao tác sinh lease/certificate cần quy trình đối soát nghiêm ngặt hơn.

### 8.2. Ánh xạ kết quả là yêu cầu an toàn dữ liệu

Nếu lô chứa dữ liệu của nhiều khách hàng, gán ciphertext sai khách hàng là lỗi nghiêm trọng dù Vault đã mã hóa đúng. Phải:

1. Tạo ID duy nhất không nhạy cảm cho mỗi mục, lưu cùng trạng thái job.
2. So khớp số lượng, index và reference của response.
3. Chặn cập nhật DB nếu response thiếu/méo hoặc bị gán sai.
4. Dùng version check hoặc compare-and-set khi cập nhật bản ghi.
5. Tránh lưu plaintext trong bảng staging, log hoặc metadata của job.

## 9. Kích thước batch, timeout và giới hạn tài nguyên

Một batch rất lớn có thể làm tăng độ trễ, kích thước body, bộ nhớ và thời gian một request chiếm tài nguyên Vault. Việc chọn batch size cần đo bằng dữ liệu thật.

- **Giới hạn theo byte và số mục**: tính cả Base64/JSON overhead; không giả định Vault chấp nhận mọi kích thước.
- **Nhóm theo key/operation**: một request `transit/encrypt/orders-pii` xử lý một key, không trộn item của key khác.
- **Backpressure**: giới hạn số batch song song, tránh làm Vault hoặc DB quá tải.
- **Timeout thực tế**: đo p50/p95/p99 theo kích thước batch, đặt timeout theo SLA và xử lý kết quả không xác định.
- **Không lộ dữ liệu**: plaintext, SecretID, token, private key không được ghi vào metrics label, URL, log hoặc exception trả ra ngoài.
- **Đối với payload lớn**: cân nhắc envelope encryption với data encryption key, thay vì gửi lượng lớn dữ liệu qua Transit request.

## 10. Metrics, audit và chẩn đoán

Cần theo dõi **hai tầng**: request-level và item-level. Một request có một item lỗi và 99 item thành công không nên bị biến thành “100 item thất bại”.

| Chỉ số gợi ý | Ý nghĩa |
| --- | --- |
| `vault_batch_requests_total` | Số request theo engine, operation, HTTP status |
| `vault_batch_items_total` | Số item theo SUCCEEDED/FAILED_INPUT/UNKNOWN |
| `vault_batch_partial_failures_total` | Số batch có cả thành công và lỗi |
| `vault_batch_size` | Số mục trong lô |
| `vault_batch_latency_seconds` | p50/p95/p99 latency |
| `vault_batch_retries_total` | Retry theo nguyên nhân |
| `vault_auth_errors_total` | Lỗi token/policy ở mức request |

Đây là tên metric đề xuất của ứng dụng, không phải metric mặc định của Vault. Tránh đưa `itemId`, token hoặc ciphertext vào metrics label vì rò rỉ và cardinality cao.

Các lỗi thường gặp:

- **400**: dữ liệu sai; với Transit batch có thể có partial results trong body.
- **403**: workload thiếu quyền, token hết hạn hoặc role sai.
- **404**: mount/key/endpoint sai.
- **429/5xx**: rate limiting hoặc Vault/hạ tầng trục trặc, cần retry hữu hạn.
- **Timeout**: trạng thái request chưa rõ, không coi mặc nhiên tất cả chưa xử lý.
- **Schema/reference mismatch**: rủi ro ghi sai dữ liệu, cần báo lỗi và dừng ghi DB.

Đối chiếu sự kiện từ audit Vault và log ứng dụng theo `jobId`, timestamp và loại operation; không cần log request chứa plaintext. Thời gian sống token, lease và giới hạn key rotation phải được giám sát riêng.

## 11. Kiểm thử tích hợp và tình huống lỗi

Unit test có thể kiểm tra mapping và state machine, nhưng phải có **integration test với Vault test cô lập** để kiểm tra hợp đồng batch thực và policy. Không dùng credential production trong test.

Các tình huống cần kiểm chứng:

1. **Tất cả mục hợp lệ**: gửi ba chuỗi Unicode, nhận ba ciphertext, reference đúng và decrypt round-trip chính xác.
2. **Một mục lỗi**: chèn một Base64 không hợp lệ giữa hai item hợp lệ, kiểm tra per-item error và các item khác vẫn thành công.
3. **Partial HTTP status**: xác minh hành vi mặc định 400 và khi đặt `partial_failure_response_code=207` trên phiên bản Vault đang dùng.
4. **Tất cả mục lỗi**: bảo đảm code không xem request là thành công chỉ do đã chỉ định 207.
5. **Sai quyền**: token chỉ encrypt không được decrypt hoặc rewrap.
6. **Rotation và rewrap**: encrypt ở key version cũ, rotate, batch rewrap, decrypt vẫn đúng.
7. **Sai reference/độ dài**: dùng fake response để kiểm tra mapper từ chối và không lưu sai dữ liệu.
8. **Timeout và DB write failure**: đánh dấu UNKNOWN hoặc PERSIST_FAILED, không tự làm mất kết quả cũ.
9. **Load test**: đo batch size, throughput, concurrency và latency trong Vault test.

Phác thảo JUnit 5 + AssertJ:

~~~java
@Test
void batchEncryptPreservesReferences() {
    List<EncryptInput> inputs = List.of(
            new EncryptInput("row-a", "Xin chào"),
            new EncryptInput("row-b", "Dữ liệu"));

    List<EncryptOutcome> results = batchService.encryptBatch(inputs);

    assertThat(results).hasSize(2);
    assertThat(results)
            .extracting(EncryptOutcome::itemId)
            .containsExactly("row-a", "row-b");
    assertThat(results).allMatch(EncryptOutcome::success);
    assertThat(results).allSatisfy(result ->
            assertThat(result.ciphertext()).startsWith("vault:v"));
}
~~~

Đây là phần test mẫu; bean Spring Vault, khóa test và fixture Vault phải được dự án cung cấp. Test quan trọng nhất cho chủ đề là **một item lỗi nhưng các item hợp lệ vẫn ghép đúng kết quả**.

## 12. Bài thực hành: mã hóa danh sách khách hàng

**Bối cảnh:** job Java cần mã hóa trường thông tin cá nhân của 5.000 khách hàng trước khi ghi vào kho dữ liệu mới.

1. Trong Vault test, tạo Transit key `orders-pii` và workload policy chỉ cho phép encrypt.
2. Lấy 20 bản ghi test, tạo `reference` ổn định và chia thành batch nhỏ.
3. Gọi Spring Vault với `batch_input` và cấu hình mã partial failure có kiểm chứng.
4. Chèn một giá trị Base64 lỗi trong request test thủ công; xác minh cả HTTP status và `batch_results`.
5. Ghi ciphertext của những mục thành công theo ID; giữ riêng những item thất bại để sửa dữ liệu.
6. Giả lập lỗi 403, timeout, reference trùng và lỗi DB khi lưu; xác minh job xử lý an toàn.
7. Đo throughput, latency và tỷ lệ lỗi khi thay đổi kích thước batch, không log plaintext.

**Câu hỏi tự kiểm tra:**

1. Vì sao một batch HTTP 400 vẫn có thể chứa các item đã mã hóa thành công?
2. Vì sao phải kiểm tra cả index và `reference`?
3. Khi một item có `error`, có nên đánh dấu toàn bộ batch thất bại không?
4. `partial_failure_response_code=207` giải quyết vấn đề gì và không giải quyết vấn đề gì?
5. Vì sao batch Transit không bảo đảm cập nhật DB nguyên tử?
6. Vì sao policy encrypt và policy decrypt nên tách riêng?
7. Khi timeout, thông tin nào quyết định retry có an toàn không?
8. Vì sao không thể mặc định KV, PKI hay dynamic secrets có API batch giống Transit?

## 13. Tổng kết

**Thao tác theo lô** làm giảm số HTTP request đến Vault nhưng đòi hỏi kiểm tra **đến từng phần tử**. Với Transit, `batch_input` chứa các mục cần xử lý, `batch_results` phản hồi theo thứ tự, `reference` hỗ trợ ghép kết quả và `error` đánh dấu mục lỗi. HTTP status, kể cả 207 hoặc 400, không thay thế việc đọc từng phần tử.

Trong **Spring Vault**, dùng `VaultTemplate`/`VaultOperations` với authentication theo workload, policy tối thiểu, kiểm tra schema và reference, retry có chọn lọc, trạng thái UNKNOWN và integration test. Khi mở rộng sang engine khác, luôn đối chiếu lại hợp đồng của endpoint và vòng đời token/lease/secret tương ứng.

**Tài liệu API:** [HashiCorp Vault Transit HTTP API](https://developer.hashicorp.com/vault/api-docs/secret/transit). Đối chiếu `batch_input`, `batch_results` và `partial_failure_response_code` theo phiên bản Vault đang triển khai.
