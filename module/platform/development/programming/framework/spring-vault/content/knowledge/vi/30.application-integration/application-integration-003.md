# Chọn lấy secret khi khởi tạo hay theo nhu cầu sử dụng

## 1. Bài toán tích hợp ứng dụng với Spring Vault

Khi dùng **Spring Vault**, ứng dụng Java truy cập HashiCorp Vault qua `VaultTemplate` (giao diện `VaultOperations`), xác thực bằng danh tính workload và chỉ được đọc các đường dẫn mà Vault policy cho phép. Vault có thể cung cấp secret tĩnh từ KV, credential động có lease (ví dụ tài khoản database), hoặc thực hiện các phép toán Transit và PKI. Một quyết định kiến trúc tác động trực tiếp đến khả năng khởi động, độ trễ và vòng đời bí mật là:

> **Ứng dụng lấy secret ngay lúc khởi tạo (eager/startup) hay chỉ gọi Vault khi tính năng thực sự cần dùng (lazy/on-demand)?**

Giả sử dịch vụ `orders-api` cần:

- Khóa API của dịch vụ thanh toán nằm tại **KV v2** `secret/data/orders/payment`, hầu như mọi request thanh toán đều dùng.
- Một khóa tích hợp báo cáo đối tác chỉ dùng khi chạy job đêm; không cần để phục vụ các API khác.
- Tài khoản database động từ `database/creds/orders` với thời gian sống hữu hạn và có thể bị thu hồi.
- Một khóa Transit để mã hóa giá trị khi lưu: ứng dụng chỉ cần **gọi Vault Transit**, không cần tự kéo private key ra khỏi Vault.

Một chiến lược “lấy hết khi startup” có thể khiến toàn bộ `orders-api` không khởi động chỉ vì cấu hình của job đêm đang thiếu. Một chiến lược “đọc Vault cho mọi HTTP request” lại có thể tạo độ trễ, tăng tải Vault và khiến sự cố mạng Vault lan rộng. Chọn đúng thời điểm đọc phải dựa trên **mức độ thiết yếu, tần suất sử dụng, vòng đời và chính sách lỗi** của từng secret.

### Kết quả học tập

Sau bài này, bạn có thể:

1. Phân biệt **startup/eager**, **on-demand/lazy**, **cache có TTL** và **hybrid**.
2. Quyết định phương thức lấy secret bằng ma trận nghiệp vụ, latency, rotation và failure handling.
3. Viết mã Spring Vault đọc KV v2 theo cả hai kiểu, kiểm tra dữ liệu thiếu/sai dạng và che giấu secret khỏi log.
4. Giải thích vì sao **KV tĩnh**, **dynamic credentials có lease**, **Transit** và **PKI** không thể dùng chung một quy tắc cache.
5. Thiết kế readiness, timeout/retry, phân quyền, giám sát và kiểm thử tích hợp cho phương thức đã chọn.

## 2. Bốn chiến lược truy cập secret

~~~mermaid
flowchart TD
    A[Ứng dụng cần giá trị bí mật] --> B{Thiết yếu để phục vụ traffic?}
    B -->|Có| C{Có lease hoặc phải xoay vòng khi chạy?}
    C -->|Có| D[Tải ban đầu + quản lý lease/rotation trong runtime]
    C -->|Không| E[Tải lúc khởi tạo + chính sách refresh theo loại secret]
    B -->|Không| F{Tần suất sử dụng cao?}
    F -->|Thấp| G[Đọc khi cần, trả lỗi theo từng tính năng]
    F -->|Cao| H[Đọc khi cần + cache TTL có giới hạn]
~~~

Bốn cách thường gặp:

| Chiến lược | Thời điểm gọi Vault | Ưu điểm | Chi phí/rủi ro |
| --- | --- | --- | --- |
| **Startup (eager)** | Khi bootstrap, khởi tạo bean hoặc chạy startup hook | Phát hiện thiếu secret sớm; request đầu tiên không chờ Vault | Có thể chặn khởi động; dữ liệu dễ cũ nếu không refresh |
| **On-demand (lazy)** | Khi endpoint/job cần secret | Không phụ thuộc secret ít dùng lúc startup; ít lưu giữ bí mật không cần thiết | Request đầu tiên chịu latency Vault; lỗi Vault xuất hiện trên luồng nghiệp vụ |
| **On-demand + cache TTL** | Lần đầu hoặc sau khi cache hết hạn | Hạn chế số lần đọc và latency; phù hợp KV hay dùng | Có cửa sổ dữ liệu cũ; invalidation và đồng thời phức tạp |
| **Hybrid/lifecycle-managed** | Tải secret thiết yếu lúc startup; tải secret tùy chọn khi cần; quản lý lease/rotation chủ động | Cân bằng readiness và tính linh hoạt | Cần quy định rõ vòng đời từng loại secret |

**Không có một lựa chọn đúng cho mọi dữ liệu.** Một ứng dụng thường dùng nhiều chiến lược cùng lúc. Điều quan trọng là lập hợp đồng cho từng secret: **ai được đọc, khi nào đọc, dùng được bao lâu, khi nào làm mới và phải làm gì nếu đọc thất bại**.

### 2.1. Tải khi khởi tạo: phù hợp điều gì?

Dùng startup khi thiếu secret có nghĩa là ứng dụng không thể thực hiện **chức năng chính** hoặc không thể thiết lập thành phần thiết yếu, ví dụ certificate/mTLS identity bắt buộc trước khi nhận kết nối, cấu hình mã hóa bắt buộc để khởi tạo pipeline hoặc credential dùng để mở kết nối quan trọng.

Các đặc trưng:

- **Fail fast**: thiếu secret, bị `403` hoặc schema sai thì báo lỗi và chưa nhận traffic.
- **Ít request đường nóng**: request đầu tiên không phải chờ round-trip Vault.
- **Định nghĩa rõ readiness**: ứng dụng sẵn sàng khi secret bắt buộc đã tải, kiểm tra và cài vào thành phần dùng nó.
- **Rủi ro cũ hóa**: nếu secret đổi trong Vault, giá trị đã nạp không tự thay. Muốn giữ hiệu lực cần refresh/rotation và cập nhật đúng consumer.

Một startup hook chạy sau khi web server bắt đầu bind cổng **không luôn đồng nghĩa** cổng chưa nhận kết nối. Với Spring Boot, nên dựa thêm vào **readiness** (thường chỉ chuyển sang accepting traffic sau khi startup runners hoàn thành) hoặc thiết kế lifecycle chặn traffic cho đến khi bí mật được cài đặt. Không đánh đồng `ApplicationRunner` với “không bao giờ có socket mở”.

### 2.2. Lấy khi cần: phù hợp điều gì?

Dùng on-demand khi secret thuộc tính năng tùy chọn, tenant ít truy cập hoặc job theo lịch; điều kiện sử dụng chỉ xuất hiện sau khi ứng dụng đã phục vụ những chức năng khác.

Ví dụ:

- Job xuất báo cáo đọc token đối tác khi bắt đầu chạy, thay vì lúc deploy.
- Endpoint quản trị hiếm khi dùng chỉ truy cập credential chuyên dụng sau khi đã kiểm tra quyền.
- Chức năng riêng của một tenant chỉ tải cấu hình tenant đó sau khi được xác thực và định tuyến hợp lệ.

On-demand làm **giảm phụ thuộc startup**, nhưng không làm biến mất phụ thuộc Vault: lỗi chuyển sang lúc thực thi. Cần timeout, retry có giới hạn, kết quả lỗi có ý nghĩa, và chính sách cache nếu có nhiều lời gọi đồng thời.

## 3. Ma trận quyết định theo đặc điểm secret

| Dữ liệu/tác vụ | Chiến lược gợi ý | Điều cần tránh |
| --- | --- | --- |
| KV v2 tĩnh, bắt buộc ở gần như mọi request | Startup + refresh có kiểm soát, hoặc lazy + cache ngắn | Đọc Vault mỗi request; giữ cache vô hạn dù có rotation |
| KV tĩnh, ít dùng | On-demand; có thể cache ngắn nếu được phép | Chặn startup khi job tùy chọn thiếu cấu hình |
| KV theo tenant, số tenant lớn | On-demand + cache giới hạn theo tenant/TTL nếu cần | Prefetch mọi tenant, để cache không giới hạn |
| Dynamic database credential có lease | Cấp lúc cần mở kết nối hoặc startup nếu DB thiết yếu; **quản lý lease/rotation** | Dùng TTL cache KV cho credential có lease |
| Certificate PKI hoặc private key dùng làm TLS identity | Cấp/nạp trước khi TLS nhận traffic; thay certificate trước `notAfter` | Chỉ cấp một lần rồi bỏ qua hạn chứng thư |
| Transit encrypt/decrypt | Gọi Vault theo thao tác nghiệp vụ, cân nhắc thiết kế batch và tải | Cố lấy key Transit về application heap để tự mã hóa |
| Secret dùng cho một job ngắn | Lấy ngay trước job, giải phóng sau khi dùng | Lưu lâu từ startup dù không cần |
| Giá trị có yêu cầu thu hồi gần thời gian thực | Chính sách refresh/invalidation chặt hoặc cơ chế server kiểm tra mỗi lần | Cache nhiều giờ bất kể yêu cầu revocation |

**Câu hỏi để tự quyết định:**

1. Nếu bí mật không đọc được trong **lúc startup**, ứng dụng nên không khởi động hay vẫn phục vụ được phần còn lại?
2. Bí mật có **đổi khi ứng dụng đang chạy** không; cần phản ánh thay đổi sau bao lâu?
3. Đó là **KV versioned** hay **dynamic secret có lease**? Thời gian sống do ai điều khiển?
4. Tần suất đọc và thời gian round-trip Vault có chấp nhận được trên đường xử lý request?
5. Nếu Vault mất kết nối, có được dùng giá trị cũ không, và tối đa bao lâu?
6. Có cần cách ly bí mật giữa tenant/workload hoặc giới hạn số secret tồn tại trong bộ nhớ?

Không đưa ra quyết định chỉ bằng việc ứng dụng chạy trên Spring Boot hay microservices. Chính sách thời điểm đọc phải bám **hợp đồng nghiệp vụ và vòng đời** của từng secret.

## 4. Giả định chung cho ví dụ Java

Các ví dụ dùng **Java 17+, Spring Vault và Vault KV v2** được mount tại `secret/`, nơi lưu dữ liệu thử:

~~~bash
# Chỉ thực hành trên Vault dev/test với dữ liệu mẫu không nhạy cảm.
vault kv put -mount=secret orders/payment apiKey="demo-placeholder-not-real"
vault kv get -mount=secret orders/payment
~~~

Cùng đường dẫn có hai cách biểu diễn:

| Cách truy cập | Path |
| --- | --- |
| Vault CLI KV aware | `vault kv get -mount=secret orders/payment` |
| Vault HTTP API / `VaultOperations.read(...)` | `secret/data/orders/payment` |
| Vault ACL cho đọc KV v2 | `path "secret/data/orders/payment"` với capability `read` |

Một JSON response KV v2 có dạng:

~~~json
{
  "data": {
    "data": {
      "apiKey": "demo-placeholder-not-real"
    },
    "metadata": {
      "version": 4,
      "created_time": "2026-11-20T09:00:00Z",
      "deletion_time": "",
      "destroyed": false
    }
  }
}
~~~

Trường `data.data` là giá trị nghiệp vụ; `data.metadata.version` biểu thị phiên bản KV v2, **không phải lease TTL**. Với `VaultOperations.read("secret/data/orders/payment")`, `VaultResponse.getData()` thường ánh xạ object JSON `data` **ở lớp ngoài**, nên giá trị thật nằm trong map `response.getData().get("data")`. Nếu dùng API `opsForVersionedKeyValue(...)` của Spring Vault thì hình thức kết quả khác, vì thư viện trừu tượng hóa lớp bao KV v2.

Không tự ghép đường dẫn Vault từ chuỗi tenant do request gửi lên. Nếu cần path theo tenant, xác thực tenant, kiểm tra quyền sở hữu và ràng buộc path/mount trước khi gọi Vault; dùng token/policy chỉ cấp quyền đúng phạm vi.

### 4.1. Policy đọc tối thiểu

~~~hcl
path "secret/data/orders/payment" {
  capabilities = ["read"]
}
~~~

Token workload cần quyền `read` trên path **thực của KV v2**. Chỉ cấp `list` nếu ứng dụng thực sự cần liệt kê; tránh `secret/*` hoặc quyền ghi/cập nhật khi dịch vụ chỉ đọc. Đường dẫn `secret/metadata/...` có mục đích khác với `secret/data/...`, không phải permission “tự có” cùng quyền đọc.

## 5. Xây dựng một lớp đọc secret có kiểm tra chặt

Lớp đọc chung sau giúp tách logic Vault và parse schema khỏi lựa chọn **khi nào** gọi. Điều đó cho phép dùng **chính cùng một reader** cho startup hoặc on-demand và tránh trùng code.

~~~java
import java.util.Map;
import java.util.Objects;

import org.springframework.vault.core.VaultOperations;
import org.springframework.vault.support.VaultResponse;

public final class PaymentSecretReader {

    private static final String PATH = "secret/data/orders/payment";
    private final VaultOperations vault;

    public PaymentSecretReader(VaultOperations vault) {
        this.vault = Objects.requireNonNull(vault);
    }

    public PaymentSecret readFresh() {
        // Spring Vault tự gửi token phù hợp qua session/auth cấu hình.
        VaultResponse response = vault.read(PATH);

        if (response == null || response.getData() == null) {
            throw new IllegalStateException(
                    "Required payment secret is missing");
        }

        Map<String, Object> envelope = response.getData();
        Object valueObject = envelope.get("data");

        if (!(valueObject instanceof Map<?, ?> values)) {
            throw new IllegalStateException(
                    "Invalid KV v2 payload structure");
        }

        Object rawApiKey = values.get("apiKey");
        if (!(rawApiKey instanceof String apiKey) || apiKey.isBlank()) {
            throw new IllegalStateException(
                    "Missing or invalid payment API key");
        }

        long kvVersion = -1L;
        Object metaObject = envelope.get("metadata");
        if (metaObject instanceof Map<?, ?> metadata) {
            Object version = metadata.get("version");
            if (version instanceof Number number) {
                kvVersion = number.longValue();
            }
        }

        return new PaymentSecret(apiKey, kvVersion);
    }

    // Giá trị bí mật vẫn tồn tại trong heap của JVM.
    // Đừng để IDE/log framework tự tạo toString chứa raw secret.
    public record PaymentSecret(String apiKey, long kvVersion) {
        @Override
        public String toString() {
            return "PaymentSecret[apiKey=REDACTED, kvVersion="
                    + kvVersion + "]";
        }
    }
}
~~~

**Điểm cần hiểu:**

- `VaultOperations.read(...)` trả `null` nếu không tìm thấy path và có thể ném exception khi lỗi mạng/TLS, không có quyền, token hết hạn hoặc Vault tạm không sẵn sàng. **Không** đổi tất cả các lỗi này thành `null` hay key mặc định.
- Parser fail khi `data.data.apiKey` thiếu hoặc sai kiểu; dùng cache giá trị cũ phải là quyết định vận hành có chính sách riêng.
- KV `version` giúp quan sát việc đã nhận bản nào; tránh log `apiKey`, raw response hay map chứa secret.
- `PaymentSecret` chứa `String` do nhiều API ứng dụng yêu cầu; Java không bảo đảm xóa bản sao chuỗi khỏi heap. Chỉ lưu reference khi cần và không trả object cho serializer/API ngoài.
- Đây là **KV v2**. Nếu mount ở KV v1, JSON và path khác. Tránh áp dụng parser này nguyên xi cho Transit, database credentials hoặc PKI.

Nếu Spring Vault version đang dùng hỗ trợ, bạn có thể chọn `opsForVersionedKeyValue("secret")` cho KV v2 để làm việc với giá trị và metadata qua API chuyên biệt. Bài sử dụng `VaultOperations.read(...)` vì giúp thấy rõ cấu trúc HTTP và thống nhất với ví dụ tiếp theo.

## 6. Phương án A: tải secret lúc khởi tạo

Với secret thiết yếu, ta muốn **đọc, kiểm tra, lắp vào consumer** trước khi ứng dụng nhận traffic. Ví dụ đơn giản dùng `ApplicationRunner` và một holder để giữ snapshot:

~~~java
import java.util.Objects;
import java.util.concurrent.atomic.AtomicReference;

public final class PaymentSecretHolder {

    private final AtomicReference<PaymentSecretReader.PaymentSecret>
            current = new AtomicReference<>();

    public void install(PaymentSecretReader.PaymentSecret secret) {
        current.set(Objects.requireNonNull(secret));
    }

    public PaymentSecretReader.PaymentSecret current() {
        PaymentSecretReader.PaymentSecret value = current.get();
        if (value == null) {
            throw new IllegalStateException(
                    "Payment secret has not been initialized");
        }
        return value;
    }
}
~~~

~~~java
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class PaymentSecretStartupConfiguration {

    @Bean
    PaymentSecretReader paymentSecretReader(
            org.springframework.vault.core.VaultOperations vault) {
        return new PaymentSecretReader(vault);
    }

    @Bean
    PaymentSecretHolder paymentSecretHolder() {
        return new PaymentSecretHolder();
    }

    @Bean
    ApplicationRunner loadPaymentSecretOnStartup(
            PaymentSecretReader reader, PaymentSecretHolder holder) {

        return args -> {
            PaymentSecretReader.PaymentSecret secret = reader.readFresh();
            holder.install(secret);
            // Không ghi secret.apiKey() vào log.
        };
    }
}
~~~

Nếu Vault trả 403, thiếu path hoặc payload không hợp lệ, exception làm startup runner thất bại; quá trình khởi động không kết thúc bình thường. Đây là hành vi **fail fast có chủ ý** khi không thể vận hành dịch vụ thanh toán.

Trong Spring Boot, nên kết hợp readiness state với việc holder đã được cài. Thông thường hệ thống điều phối chỉ gửi traffic khi readiness xác nhận application startup đã hoàn thành; không dựa duy nhất vào cổng TCP đang lắng nghe. Nếu có nhiều runner, cần kiểm tra thứ tự dependency hoặc dùng lifecycle phù hợp để consumer không truy cập holder trước khi `install`.

### 6.1. Startup snapshot không tự cập nhật

Giả sử secret KV chuyển từ version 4 sang version 5 sau khi ứng dụng chạy. `holder.current()` vẫn chứa snapshot cũ cho đến khi **một cơ chế refresh** gọi `reader.readFresh()` và `holder.install(newSecret)`.

Một quy trình refresh an toàn cho KV:

1. Đọc bản mới trong một luồng quản lý riêng, có timeout/retry giới hạn.
2. Kiểm tra cấu trúc, giá trị, quyền và tính tương thích với consumer.
3. Thử cài đặt/kiểm tra kết nối nếu consumer yêu cầu (ví dụ client HTTP dùng API key mới).
4. Chỉ **đổi atomically** reference sau khi giá trị mới được xác nhận hoạt động.
5. Ngừng sử dụng identity/client cũ, không log hoặc xuất giá trị.
6. Theo dõi version đã áp dụng, thời gian refresh và lỗi gần nhất.

Nếu secret đã bị **thu hồi** tại phía nhà cung cấp, việc còn lưu snapshot cũ không giúp nó tiếp tục hoạt động. Tách rõ *giá trị trong bộ nhớ* và *giá trị được hệ thống đích chấp nhận*.

### 6.2. Lấy secret qua PropertySource tại startup

Khi các secret là **cấu hình ứng dụng**, có thể dùng cách tích hợp khác:

- **Spring Vault `@VaultPropertySource`**: tải key-value vào `Environment`/`PropertySource` theo khai báo; cơ chế lấy lại phụ thuộc cấu hình và cách dùng.
- **Spring Cloud Vault**: thường dùng Spring Boot Config Data, ví dụ `spring.config.import: "vault://"` sau khi đã cài starter và cấu hình xác thực.

~~~yaml
# Ví dụ cấu hình Spring Cloud Vault (yêu cầu dependency tương ứng).
spring:
  config:
    import: "vault://"
  cloud:
    vault:
      uri: "https://vault.internal.example:8200"
      authentication: KUBERNETES
      kubernetes:
        role: orders-api
~~~

Đây là **ví dụ định hướng**, cần cấu hình Kubernetes service account, mount/auth path, CA TLS và context KV theo hệ thống. `spring.config.import` thuộc **Spring Cloud Vault**, không phải method của `VaultTemplate`. Việc bind một property vào `@Value` hoặc singleton `@ConfigurationProperties` **không bảo đảm bean tự rebind** mỗi khi giá trị trong Vault thay đổi. Muốn đáp ứng rotation, cần cơ chế refresh/rebind và tái cấu hình consumer phù hợp, kể cả connection pool.

Các phương án PropertySource rất tiện cho bí mật cấu hình và phụ thuộc khởi tạo; với dữ liệu theo request/tenant hoặc luồng nghiệp vụ, một service gọi `VaultOperations` trực tiếp thường dễ kiểm soát thời điểm hơn.

## 7. Phương án B: đọc theo nhu cầu sử dụng

Thay vì chạy `reader.readFresh()` khi ứng dụng khởi động, chỉ gọi nó trong chức năng thực sự cần secret:

~~~java
public final class PaymentService {

    private final PaymentSecretReader reader;
    private final RemotePaymentClient paymentClient;

    public PaymentService(
            PaymentSecretReader reader, RemotePaymentClient paymentClient) {
        this.reader = reader;
        this.paymentClient = paymentClient;
    }

    public PaymentResult charge(PaymentCommand command) {
        // Chỉ đọc khi có yêu cầu thanh toán đã được xác thực/ủy quyền.
        PaymentSecretReader.PaymentSecret secret = reader.readFresh();

        return paymentClient.charge(
                secret.apiKey(),
                command);
    }

    // Các interface minh họa của chính ứng dụng, không thuộc Spring Vault.
    public interface RemotePaymentClient {
        PaymentResult charge(String apiKey, PaymentCommand command);
    }
    public record PaymentCommand(String orderId) {}
    public record PaymentResult(String providerReference) {}
}
~~~

**Giả định:** controller/API đã kiểm tra quyền của người gọi và validate input trước khi vào hàm `charge`. Việc call Vault **không** thay thế authorization ở ứng dụng. Code trả về giá trị placeholder nghiệp vụ và tách client thanh toán để thấy ranh giới; không dùng key vào URL, query string hoặc exception message.

Ưu điểm: nếu không có request thanh toán, ứng dụng không cần đọc KV payment. Nhược điểm: **mỗi request charge là một lượt đọc Vault**. Nếu có nhiều pod và lưu lượng cao, tổng số call có thể rất lớn; timeout Vault sẽ nằm trực tiếp trên critical path.

### 7.1. Phải tính tải trên toàn cụm

Nếu một pod xử lý 20 payment requests/giây và có 50 pod, cách đọc mỗi lần có thể tạo **1.000 KV reads/giây** vào Vault cho đúng một secret. Cần so với SLO, quota, khả năng Vault HA, số lượng connection và overhead TLS/auth.

Tăng tài nguyên Vault không phải giải pháp duy nhất: với **KV tĩnh dùng chung và được phép cache**, cache giới hạn thời gian thường giảm đáng kể số call. Với **operation phải diễn ra trong Vault** như Transit encrypt/decrypt, không thể thay thế call bằng cache kết quả theo cách tương tự.

## 8. Phương án C: on-demand kết hợp cache TTL cho KV tĩnh

Ví dụ dưới đây chỉ cache **một giá trị KV v2 tĩnh** trong 30 giây kể từ lúc đọc thành công, dùng đồng bộ hóa để các request đồng thời không cùng truy cập Vault khi cache hết hạn:

~~~java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.util.Objects;

public final class CachedPaymentSecretProvider {

    private static final Duration MAX_AGE = Duration.ofSeconds(30);

    private final PaymentSecretReader reader;
    private final Clock clock;
    private volatile CacheEntry cached;

    public CachedPaymentSecretProvider(
            PaymentSecretReader reader, Clock clock) {
        this.reader = Objects.requireNonNull(reader);
        this.clock = Objects.requireNonNull(clock);
    }

    public PaymentSecretReader.PaymentSecret get() {
        Instant now = clock.instant();
        CacheEntry snapshot = cached;

        if (snapshot != null && now.isBefore(snapshot.expiresAt())) {
            return snapshot.secret();
        }

        synchronized (this) {
            // Double-check để tránh nhiều luồng cùng reload.
            now = clock.instant();
            snapshot = cached;
            if (snapshot != null && now.isBefore(snapshot.expiresAt())) {
                return snapshot.secret();
            }

            // Khi đọc lỗi, KHÔNG kéo dài TTL hay tự dùng giá trị quá hạn.
            PaymentSecretReader.PaymentSecret refreshed = reader.readFresh();

            // Tính expiry sau khi đọc hoàn thành để không kéo dài
            // cache dựa trên request bắt đầu trước đó.
            cached = new CacheEntry(
                    refreshed, clock.instant().plus(MAX_AGE));

            return refreshed;
        }
    }

    public synchronized void invalidate() {
        cached = null;
    }

    private record CacheEntry(
            PaymentSecretReader.PaymentSecret secret,
            Instant expiresAt) {}
}
~~~

Với thiết kế này:

- Request đầu tiên đọc Vault; request tiếp theo trước `expiresAt` dùng snapshot có sẵn.
- Hết hạn cache tạo tối đa **một lượt reload tại một thời điểm trong một JVM**. Nhiều pod vẫn có cache và lượt reload riêng.
- Nếu Vault lỗi khi cache đã hết hạn, hàm **ném lỗi** thay vì âm thầm trả snapshot quá hạn.
- `invalidate()` cho phép một sự kiện vận hành có kiểm soát yêu cầu đọc lại ở lần truy cập sau; bản thân KV v2 **không phát sự kiện push** tới cache này.
- `MAX_AGE` là **chính sách stale-data của ứng dụng**, không phải TTL/lease của KV và không bảo đảm giá trị còn được phía đối tác chấp nhận.

### 8.1. Khi nào được dùng dữ liệu cũ nếu Vault tạm lỗi?

Một số hệ thống chọn **stale-if-error** để duy trì khả năng phục vụ khi Vault mất kết nối. Quyết định phải có ranh giới cụ thể:

| Loại secret | Có thể cân nhắc stale-if-error? | Điều kiện |
| --- | --- | --- |
| KV cấu hình tĩnh ít nhạy cảm với rotation | Có, nếu chấp nhận được | Tuổi tối đa rõ ràng, quan sát lỗi và không dùng quá thời hạn được phê duyệt |
| Khóa API của hệ thống đối tác có thể rotate/revoke | Rất thận trọng | Khóa cũ có thể bị đối tác từ chối; cần xử lý kết quả xác thực thất bại |
| Dynamic database credential | **Không dùng cache TTL thuần túy** | Lease có thể hết hạn/revoked; phải renew/rotate đúng vòng đời |
| Access token dùng gọi API ngoài có expiry | Chỉ trong thời hạn thực của token | Không kéo dài “hạn dùng” bằng TTL cache |
| Private key/TLS certificate | Không vượt `notAfter`/policy | Phải cấp lại và nạp identity mới trước hết hạn |

**Fail closed** thường phù hợp với secret bắt buộc, dữ liệu mã hóa hoặc các trường hợp revocation cần có hiệu lực nhanh. Nếu cho phép stale-if-error, giới hạn bằng một chính sách được duyệt trước (ví dụ `maxStaleAge` riêng), không tự thêm một lần gia hạn vô hạn mỗi khi kết nối Vault lỗi.

### 8.2. Cache theo tenant: tránh tăng vô hạn

Nếu ứng dụng có một secret cho mỗi tenant, key cache phải chứa tenant ID **đã xác thực**, path phải do ứng dụng xây dựng theo allowlist, và có:

- Giới hạn tổng số entry và memory budget.
- TTL, evict/expire và kiểm soát reload đồng thời theo key.
- Quy tắc invalidate khi tenant bị đình chỉ/chuyển quyền.
- Metric tổng hợp, tránh đưa tenant ID nhạy cảm vào nhãn metric nhiều cardinality.
- Phân quyền Vault theo tenant hoặc path tương ứng nếu cần cô lập mạnh hơn.

Không dùng một singleton cache duy nhất cho nhiều tenant nếu có nguy cơ trả secret tenant A khi xử lý tenant B.

## 9. Secret động có lease phải quản lý vòng đời riêng

**Dynamic secret** như `database/creds/orders` khác KV:

~~~json
{
  "lease_id": "database/creds/orders/...",
  "lease_duration": 3600,
  "renewable": true,
  "data": {
    "username": "v-orders-...",
    "password": "<dynamic-password>"
  }
}
~~~

Đây là cấu trúc minh họa. Khi Vault cấp credential động, response đi cùng lease metadata; TTL gắn với **tính hợp lệ của credential** chứ không chỉ chính sách refresh trong cache. Sau khi lease hết hạn hoặc bị revoke, credential có thể không còn sử dụng được ở database.

Vì vậy:

1. **Khi nào cấp?** Nếu database thiết yếu, cấp trước khi nhận traffic và khởi tạo connection pool. Nếu job hiếm dùng, có thể cấp lúc job bắt đầu.
2. **Trong lúc sử dụng:** theo dõi `lease_id`, `lease_duration`, `renewable`; renew khi được phép, hoặc cấp credential mới khi hết hạn/không thể renew.
3. **Khi rotate:** cập nhật connection pool/client **một cách phối hợp**. Chỉ thay một String password không tự thay các kết nối đã thiết lập.
4. **Khi ngừng dùng:** release tài nguyên, xét revoke lease theo policy; token/session gốc và lease secret là hai vòng đời độc lập.

Spring Vault có **`SecretLeaseContainer`**, hỗ trợ request, renew và rotate secret có lease với `RequestedSecret` và các lease event. Đây là điểm tích hợp thích hợp khi cần vòng đời dynamic credentials, thay vì bắt chước bằng một `CachedPaymentSecretProvider` có TTL bất kỳ. Nếu dùng `@VaultPropertySource`/Spring Cloud Vault với dynamic secrets, cần kiểm tra cơ chế lease và cách consumer nhận rotation trong phiên bản đang triển khai. <u>Lease tự gia hạn không có nghĩa pool kết nối tự sử dụng credential mới.</u>

### 9.1. Token TTL cũng không phải cache TTL

Spring Vault client phải xác thực theo workload và quản lý Vault session token, có thể cần renew hoặc re-login khi token hết hạn. Một secret KV còn trong cache **không chứng minh** token Vault còn hiệu lực để thực hiện lần đọc kế tiếp. Ngược lại, token được renew thành công không kéo dài `lease_duration` của credential động nếu không renew lease tương ứng.

| Đồng hồ | Đối tượng | Cách xử lý |
| --- | --- | --- |
| **Token TTL** | Quyền gọi Vault API | SessionManager/authentication/re-login theo workload |
| **Dynamic secret lease TTL** | Hiệu lực credential được Vault cấp | Renew/rotate/revoke và thay consumer |
| **KV cache TTL** | Độ cũ chấp nhận được của giá trị trong ứng dụng | Re-read, invalidate, xử lý lỗi |
| **PKI certificate `notAfter`** | Hạn hiệu lực danh tính X.509 | Issue/sign cert mới, thay TLS identity |
| **Transit key version** | Phiên bản khóa mã hóa do Vault quản lý | Vault tự xử lý các phép toán; thiết kế rotate/rewrap theo chính sách |

Không sử dụng TTL cache để thay thế vòng đời token hoặc secret lease.

## 10. Hybrid: áp dụng cho một dịch vụ thực tế

Một phương án thực tiễn của `orders-api`:

~~~text
                   Khởi động orders-api
                            |
                 Workload auth tới Vault
                            |
               +------------+-------------+
               |                          |
        Secret bắt buộc?             Tính năng tùy chọn
               |                          |
    KV payment / TLS identity      Secret của job báo cáo
               |                          |
      Kiểm tra, cài vào runtime     Chưa đọc khi startup
               |                          |
            READY                      Khi job chạy
               |                          |
       Refresh/rotate có hạn           Đọc một lần
               |                          |
       Consumer được cập nhật          Xử lý, giải phóng
               |
        API thanh toán phục vụ
~~~

Một bảng quyết định cụ thể:

| Phần ứng dụng | Thời điểm đọc | Điều kiện sẵn sàng | Làm mới |
| --- | --- | --- | --- |
| Payment adapter cần KV API key | Startup nếu không thể thanh toán thiếu key; hoặc lazy + cache nếu endpoint tùy chọn | Key tồn tại, có định dạng hợp lệ, client dùng được | Poll/version check hoặc reload có kiểm soát |
| Báo cáo đêm | On-demand lúc job bắt đầu | Không chặn readiness API chính | Lấy mới mỗi lần job hoặc cache ngắn |
| Database pool thiết yếu | Startup để tạo pool | Có credential còn lease, connection test đạt | SecretLeaseContainer/renew/rotate + thay pool |
| TLS mTLS server | Trước khi chấp nhận TLS traffic | Key + cert + chain hợp lệ, chưa hết hạn | Reissue + hot reload theo server hỗ trợ |
| Transit encryption | Theo request nghiệp vụ cần mã hóa | Vault Transit endpoint phục vụ và token có quyền | Vault quản lý key version; ứng dụng không cache key gốc |

**Quy tắc phụ thuộc:** Nếu một tính năng phụ bắt buộc trong một số deployment nhưng tùy chọn ở deployment khác, nên cấu hình rõ `required=true/false` theo profile/feature flag; không ngẫu nhiên fail startup tùy dữ liệu vào thời điểm đó.

## 11. Kiểm soát lỗi, latency và khả năng chịu sự cố

### 11.1. Ba loại lỗi cần tách biệt

| Lỗi | Ví dụ | Cách xử lý phù hợp |
| --- | --- | --- |
| **Cấu hình hoặc phân quyền** | 403, sai mount, thiếu path, schema sai | Fail fast với thành phần thiết yếu; báo đường dẫn/mã lỗi đã che secret; không retry vô hạn |
| **Tạm thời** | Timeout, Vault không reachable, node sealed/HA chuyển leader | Timeout, retry có giới hạn và jitter/backoff; ứng dụng thể hiện degraded/unknown phù hợp |
| **Bí mật không còn hợp lệ** | Lease expired/revoked, API key đối tác bị vô hiệu, cert hết hạn | Reissue/rotate và cập nhật consumer; không dùng lại credential cũ vô hạn |

Với startup, retry bounded có thể giúp vượt qua Vault failover ngắn nhưng **không nên giấu lỗi mãi mãi**; kết quả cuối phải thể hiện readiness hoặc deployment thất bại đúng mức. Với on-demand, exception cần được chuyển thành lỗi nghiệp vụ có chủ đích, không để response vô tình chứa đường dẫn nhạy cảm, token, username/password hoặc raw Vault response.

### 11.2. Ngăn sự cố lan rộng

- Đặt **connect timeout**, **read timeout** và circuit breaker ở đường truy cập Vault phù hợp với SLO.
- Giới hạn đồng thời, tránh nhiều request cùng reload cache (cache stampede).
- Nếu retry, chỉ retry những thao tác có thể lặp lại an toàn. Một số endpoint **phát hành dữ liệu mới** như `pki/issue` hay `database/creds/role` có thể tạo nhiều secret khác nhau nếu response bị mất.
- Tách dependency giữa API cốt lõi và job hiếm dùng, tránh job tùy chọn làm chết toàn bộ process.
- Theo dõi thời gian tải secret trong startup và trong đường request; điều chỉnh cache TTL dựa trên nhu cầu rotation và lưu lượng thực tế.
- Khi Vault tạm down, **không restart liveness** toàn bộ workload liên tục. Tách liveness của tiến trình với readiness theo khả năng phục vụ.

### 11.3. Readiness khác liveness

**Liveness** trả lời ứng dụng còn hoạt động bình thường hay cần được restart; thông thường không nên gọi Vault theo từng probe liveness. **Readiness** trả lời ứng dụng có thể nhận traffic **ngay lúc này** với các dependency thiết yếu hay không.

Ví dụ: Payment adapter đã nạp một key KV hợp lệ, provider vẫn chấp nhận key, nhưng Vault đang mất kết nối trong vài giây. Liveness nên còn tốt. Readiness phụ thuộc chính sách: có thể tiếp tục phục vụ từ snapshot hợp lệ trong giới hạn cho phép; nếu cần cấp lại credential trước mỗi giao dịch thì readiness có thể chuyển sang không sẵn sàng. Phải diễn đạt quy tắc này bằng trạng thái *khả năng phục vụ thực tế*, tránh lấy một HTTP `200` từ `/sys/health` làm bằng chứng mọi secret đọc được.

## 12. Bảo mật khi đọc và cache secret

Cả startup và on-demand đều phải tuân thủ nguyên tắc chung:

1. Dùng **workload authentication** (Kubernetes auth/AppRole hoặc cơ chế phù hợp), kết nối HTTPS và CA tin cậy; không hardcode root token.
2. Giới hạn Vault policy theo đúng secret engine, path và hành động; chỉ cấp quyền đọc khi cần.
3. Xác thực người dùng/tenant **trước khi** chọn path. Không cho client gửi path tùy ý để biến ứng dụng thành proxy đọc secrets.
4. Không in raw `VaultResponse`, `apiKey`, database password, private key, JWT hoặc token vào log/tracing/metrics.
5. Hạn chế copy bí mật và vòng đời trong memory; dùng secret manager chuyên trách khi cần. Với `String` trên JVM, không thể đảm bảo xóa sạch byte cũ.
6. Cache chỉ những dữ liệu cần, giới hạn dung lượng/TTL, không để secret vào cache phân tán không được bảo vệ.
7. Các exception và HTTP response chỉ lộ mã lỗi/chủng loại; không đưa giá trị từ Vault vào message trả cho client.
8. Khi rotate, cần đổi consumer theo trình tự an toàn và xử lý tài nguyên cũ; không giả định thay biến trong singleton sẽ thay kết nối đã mở.
9. Khi thu hồi bí mật, chính sách stale-data phải phù hợp mức độ rủi ro. Với credential revoked không thể đảm bảo vẫn dùng được từ cache.
10. Đánh giá ranh giới multi-tenant: một Vault token dùng chung có quyền đọc tất cả path tạo rủi ro lan rộng nếu application authorization bị lỗi.

## 13. Quan sát hệ thống mà không lộ bí mật

Các chỉ số nên có:

| Metric/Signal | Diễn giải | Không nên ghi |
| --- | --- | --- |
| `vault_secret_fetch_duration` | Latency đọc theo loại secret/stage (startup, on-demand, refresh) | Giá trị bí mật và dữ liệu input chưa lọc |
| `vault_secret_fetch_errors_total` | Lỗi theo nguyên nhân: auth, not found, timeout, malformed, sealed | Raw response hoặc session token |
| `vault_secret_cache_hit_ratio` | Cache có làm giảm call và độ trễ? | Khóa cache chứa PII/secret |
| `vault_secret_cache_age_seconds` | Độ tuổi snapshot để kiểm soát stale | Giá trị snapshot |
| `vault_lease_remaining_seconds` | Thời gian còn lại của dynamic credential lease | Username/password động |
| `vault_secret_applied_version` | KV v2 version đã lắp vào consumer | Secret hoặc nội dung payload |
| `vault_secret_refresh_failures_total` | Có lỗi thay secret khi đang chạy? | Body response thất bại |

Thường chỉ nên gắn label `service`, `secret_category`, `result`, `deployment` đã được allowlist. Path cụ thể có thể tiết lộ tenant hoặc mô hình nội bộ, nên tránh phát tán qua các dashboard công khai. Dựa trên trace/span đã làm sạch để đo thời gian request đến Vault và giai đoạn chờ cache lock.

## 14. Thực hành kiểm thử tích hợp

Dùng Vault dev/test tách biệt và secret giả. Chuẩn bị KV v2 tại mount `secret/`, workload policy đọc path đã chọn và một `VaultOperations` cấu hình TLS/auth phù hợp. Các bài test không cần khóa/credential production.

### 14.1. Các tình huống phải kiểm tra

| Tình huống | Startup strategy | On-demand/cache strategy |
| --- | --- | --- |
| Secret KV tồn tại, đúng schema | Startup thành công; holder có snapshot | Lần đầu đọc thành công, cache cập nhật |
| Secret bị thiếu hoặc không có quyền `read` | Startup không hoàn tất hoặc readiness không đạt | Chỉ tính năng gọi secret báo lỗi có chủ đích |
| Cấu trúc KV v2 khác dự kiến | Parser fail, không đưa dữ liệu rỗng vào consumer | Fail request đó, không ghi cache lỗi |
| Secret cập nhật version 4 → 5 | Không đổi nếu chưa refresh; sau refresh nhận version 5 | Đến TTL/invalidate thì lấy version 5 |
| Nhiều request đồng thời sau cache expiry | Không áp dụng cache lazy | Một lần reload mỗi JVM nếu dùng synchronized như ví dụ |
| Vault timeout vài giây | Startup retry bounded hoặc fail rõ | Request phụ thuộc secret fail; không kéo dài stale vô hạn |
| Workload token hết hạn | Read/refresh mới có thể lỗi | Cache vẫn còn nhưng fetch tiếp cần auth hợp lệ |
| Dynamic credential hết lease | Renewal/rotation phải xử lý | Không thể chỉ lấy dữ liệu từ KV TTL cache |
| Startup với secret tùy chọn bị thiếu | Không chặn core readiness nếu đã thiết kế optional | Tính năng tùy chọn nhận lỗi khi được gọi |
| Mô phỏng rotation | Cài snapshot mới và consumer đổi phù hợp | TTL/invalidation và consumer phản ứng đúng |

### 14.2. Unit test quyết định cache không cần Vault thật

Có thể đưa `Clock` giả vào `CachedPaymentSecretProvider` rồi cố định các thời điểm thay vì `Thread.sleep` để kiểm tra TTL; stub `PaymentSecretReader` theo luồng kiểm thử. Vì ví dụ cung cấp concrete class, nếu muốn mock dễ hơn có thể trích interface nhỏ:

~~~java
@FunctionalInterface
public interface SecretLoader<T> {
    T load();
}
~~~

Sau đó cache nhận `SecretLoader<PaymentSecret>` hoặc `Supplier<PaymentSecret>` để test được:
- Trong TTL, cùng giá trị được trả về và `load()` chỉ được gọi một lần.
- Đúng tại/qua deadline, `load()` được gọi lại.
- Khi reload ném lỗi, giá trị quá hạn **không** được trả về trong policy mặc định.
- Nhiều luồng tới cùng lúc không nhân số lần refresh tại một JVM.

### 14.3. Integration test cần chứng minh điều gì?

Một integration test dùng Vault thật xác minh Spring Vault map chính xác `secret/data/...`, token có ACL đúng, khả năng đọc version mới, timeout/auth errors và quy tắc không log secret. Với dynamic credentials, cần thêm hệ cơ sở dữ liệu test để kiểm tra lease renew/rotate thực sự và cách connection pool chuyển đổi. Test chỉ so sánh String trong cache không đủ chứng minh đã quản lý đúng lease.

Không sinh credential động trong vòng lặp test không giới hạn, không để secret trong JUnit assertion message, và không dùng token root của môi trường dùng chung.

## 15. Checklist lựa chọn kiến trúc

- [ ] Mỗi secret có phân loại: cần ở startup, chỉ dùng khi có request, hay bắt buộc có lifecycle manager.
- [ ] Đã xác định chính sách nếu Vault không reachable: fail fast, degraded, hoặc stale-if-error có giới hạn.
- [ ] KV v2 được đọc đúng `secret/data/...` và parse `data.data`, theo dõi version khi cần.
- [ ] Nếu dùng bootstrap properties, biết rõ Spring Vault PropertySource và Spring Cloud Vault Config Data khác lời gọi `VaultTemplate.read`.
- [ ] Secret startup có tiêu chí readiness rõ và cơ chế refresh nếu có rotation.
- [ ] Secret on-demand có timeout, giới hạn đồng thời, xử lý exception và SLO phù hợp.
- [ ] Cache KV có TTL/size/invalidation, không nhầm với token TTL hoặc dynamic secret lease.
- [ ] Dynamic credentials dùng renew/rotate theo lease và cập nhật connection pool, không giữ password quá hạn.
- [ ] PKI certificate được cấp/lắp trước lúc dùng TLS và thay trước `notAfter`.
- [ ] Transit vẫn thực hiện phép toán trong Vault, không xuất khóa gốc vào JVM.
- [ ] Workload auth và Vault ACL có quyền tối thiểu, path/tenant được validate.
- [ ] Secret không xuất hiện trong log, trace, metrics, exception hoặc HTTP response.
- [ ] Đã kiểm tra tình huống cập nhật secret, Vault down, token hết hạn, lease revoke, nhiều request đồng thời và startup fail.

## Tài liệu tham khảo

- Spring Vault, [VaultOperations API](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/core/VaultOperations.html) — `read` và các `opsFor...`.
- Spring Vault, [VaultTemplate API](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/core/VaultTemplate.html) — triển khai client đồng bộ và callback.
- Spring Vault, [Credential Rotation](https://docs.spring.io/spring-vault/reference/vault/credential-rotation.html) và [SecretLeaseContainer](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/core/lease/SecretLeaseContainer.html) — vòng đời lease, renew và rotation.
- Spring Vault, [Property Sources](https://docs.spring.io/spring-vault/reference/vault/propertysource.html) — `@VaultPropertySource` và cấu hình secret tại context startup.
- Spring Cloud Vault, [Quick Start](https://docs.spring.io/spring-cloud-vault/reference/quickstart.html) — Config Data `spring.config.import`.
- HashiCorp Vault, [KV secrets engine](https://developer.hashicorp.com/vault/docs/secrets/kv) và [KV v2 API](https://developer.hashicorp.com/vault/api-docs/secret/kv/kv-v2) — path, version và lớp bao response.
- HashiCorp Vault, [Database secrets engine](https://developer.hashicorp.com/vault/docs/secrets/databases) và [Lease, Renew, Revoke](https://developer.hashicorp.com/vault/docs/concepts/lease) — credential động và vòng đời lease.
