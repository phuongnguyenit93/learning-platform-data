# Giới hạn mã hóa của Spring Boot thuần và vai trò kho bí mật bên ngoài

Trong Spring Boot Externalized Configuration, ứng dụng thường phải nhận **thông tin bí mật**: mật khẩu cơ sở dữ liệu, API token, private key, client secret, chứng chỉ, credential truy cập broker, hoặc khóa để gọi dịch vụ bên thứ ba. Spring Boot hỗ trợ nhiều cách **đưa giá trị cấu hình vào Environment** rồi bind chúng sang các bean Java. Nhưng khả năng đọc cấu hình **không đồng nghĩa** với việc framework tự mã hóa, lưu khóa giải mã, quản lý quyền truy cập hay xoay vòng bí mật.

**Thông điệp cốt lõi:**

> Spring Boot thuần không cung cấp một cơ chế mặc định có thể nhận mọi chuỗi `ENC(...)` trong `application.yml`/`application.properties` rồi tự giải mã an toàn. Nếu ứng dụng cần quản lý bí mật, phải thiết kế nguồn cấp secret và vòng đời khóa phù hợp, thường dựa vào **secret manager**, **Vault**, **KMS**, hoặc cơ chế secret của nền tảng triển khai, cùng xác thực và phân quyền thích hợp.

Điều đó không có nghĩa Spring Boot không dùng được bí mật. Nó có thể đọc bí mật từ biến môi trường, Java system properties, Config Data, tệp được mount vào container, `configtree:` hoặc một tích hợp bên ngoài. Điểm cần tách biệt là:

- **Nguồn cấp:** bí mật từ đâu đến?
- **Bảo vệ lúc lưu và truyền:** ai mã hóa, ai giữ khóa và dữ liệu được truyền qua kênh nào?
- **Sử dụng lúc chạy:** giá trị xuất hiện trong bộ nhớ, bean, connection pool hoặc HTTP client như thế nào?
- **Vòng đời:** ai cấp, thay, thu hồi, audit và xử lý sự cố lộ bí mật?

Bài học trình bày giới hạn Spring Boot core, những nhầm lẫn về Base64 và `ENC(...)`, mô hình secret manager/Vault/KMS, cách sử dụng `configtree:`, phương án cấp secret qua nền tảng triển khai, kiểm thử, rotation và các nguy cơ rò rỉ qua log/Actuator/CI.

## 1. Phân loại dữ liệu cấu hình: không phải key nào cũng là secret

Một file `application.yml` có thể chứa nhiều loại giá trị:

~~~yaml
warehouse:
  client:
    base-url: "https://warehouse.example.invalid"
    timeout: 3s
    max-retries: 3
    api-key: "replace-me"
~~~

Các field không có cùng mức nhạy cảm:

| Cấu hình | Thông thường có phải secret? | Cân nhắc |
| --- | --- | --- |
| `base-url` | Không phải lúc nào cũng vậy | Có thể tiết lộ topology nội bộ |
| `timeout` | Không | Có thể lưu trong repo |
| `max-retries` | Không | Có thể lưu trong repo |
| `api-key` | Có | Không lưu giá trị thật trong repo |
| `spring.datasource.password` | Có | Hạn chế quyền đọc và vòng đời |
| Private key | Có | Yêu cầu kiểm soát mạnh hơn, tránh log/export |
| Client ID công khai | Tùy loại | Thường không thay thế client secret |
| Access token ngắn hạn | Có | Không log; cần expiry/refresh |

**Nguyên tắc:** phân loại theo **khả năng cấp quyền hoặc gây thiệt hại khi lộ**, chứ không chỉ theo tên key. Một URL chứa embedded credentials hoặc query token cũng là dữ liệu nhạy cảm dù key được gọi là `url`.

Trong ví dụ cấu hình học tập, dùng giá trị giả và domain dành cho minh họa. Đừng thay trực tiếp vào README bằng mật khẩu thật hoặc token của môi trường production.

## 2. Spring Boot thuần làm gì và không làm gì?

Các khả năng chuẩn của Spring Boot:

1. Nạp Config Data như `application.properties`, `application.yml`, profile-specific files và những import được hỗ trợ.
2. Đọc OS environment variables, Java system properties, command-line arguments và một số nguồn khác.
3. Đưa các nguồn vào Spring `Environment` theo thứ tự ưu tiên.
4. Phân giải placeholder như `${WAREHOUSE_API_KEY}` theo property sources có sẵn.
5. Bind nhóm cấu hình vào `@ConfigurationProperties` hoặc inject một số giá trị bằng `@Value`.
6. Với `configtree:`, đọc tệp trong một cây thư mục như các property có tên tương ứng.

Những điều **không mặc định được cung cấp như một tính năng chung**:

- Mã hóa mọi property trước khi ghi vào `application.yml`.
- Tự giải mã chuỗi `ENC(ciphertext)` mà không cấu hình giải pháp bổ sung.
- Tự chọn nơi lưu encryption key an toàn và cấp quyền giải mã.
- Tự thay mật khẩu cơ sở dữ liệu khi secret bị lộ.
- Tự đồng bộ tất cả bean khi file secret thay đổi.
- Bảo đảm mọi debug log, exception, heap dump và endpoint quan sát không làm lộ giá trị.
- Tự kết nối tới mọi secret manager của nhà cung cấp cloud.
- Tự cấp dynamic credentials hoặc audit các lần đọc secret.

Có thể tích hợp những chức năng này qua thư viện/extension, nền tảng triển khai hoặc mã của ứng dụng. Nhưng **lúc ấy cần nêu rõ thành phần nào thực hiện từng chức năng**, không nên gọi chung là “Spring Boot đã mã hóa”.

## 3. Giá trị ENC(...) không phải cú pháp mã hóa được Spring Boot core tự hiểu

Ví dụ một file:

~~~properties
warehouse.client.api-key=ENC(A1B2C3-illustrative-ciphertext)
~~~

Nếu không có custom property source, converter hoặc thư viện mã hóa cấu hình đã được tích hợp, Spring Boot không có lý do để tự diễn giải `ENC(...)` như một ciphertext cần giải mã. Giá trị có thể chỉ được xem là **một chuỗi văn bản**.

Ví dụ:

~~~java
String key = environment.getProperty(
    "warehouse.client.api-key"
);
~~~

Không nên giả định `key` là bản rõ của token. Nó có thể vẫn là chuỗi `"ENC(...)"` như nguồn đã cung cấp.

Muốn dùng cú pháp dạng `ENC(...)`, dự án phải bổ sung cơ chế rõ:

- Một implementation nhận biết ký hiệu ciphertext.
- Thuật toán mã hóa xác thực phù hợp và định dạng ciphertext có version/nonce/tag.
- Nguồn encryption key được cấp riêng và bảo vệ.
- Đường giải mã đủ sớm trước khi bean cần sử dụng giá trị.
- Chính sách xử lý lỗi key sai, ciphertext lỗi hoặc key rotation.
- Tests bảo đảm dữ liệu không lộ trong log/exception.

Một vài thư viện cộng đồng hỗ trợ encrypted properties trong Spring ecosystem, nhưng chúng **không phải hợp đồng mặc định của Spring Boot core**. Mỗi thư viện có API, chu kỳ bảo trì, threat model và trách nhiệm quản lý key riêng.

## 4. Base64 là encoding, không phải encryption

Một số người xem:

~~~yaml
database:
  password: "cGxhY2Vob2xkZXI="
~~~

và gọi đó là “mật khẩu đã được mã hóa”. Đây có thể chỉ là **Base64 encoding**. Base64 biến đổi biểu diễn dữ liệu để dễ truyền/nhúng trong định dạng văn bản; ai có chuỗi cũng có thể decode nếu không có bảo vệ khác.

So sánh:

| Kỹ thuật | Mục đích | Có bảo mật nội dung bằng secret key không? |
| --- | --- | --- |
| Base64 | Biểu diễn bytes thành text | Không |
| Hex | Biểu diễn bytes thành text | Không |
| URL encoding | Escape ký tự trong URL | Không |
| Hash một chiều | Kiểm tra/so sánh dữ liệu trong ngữ cảnh phù hợp | Không giải mã ngược; không dùng làm cách cấp secret runtime |
| Encryption đối xứng | Giữ bí mật dữ liệu khi có key bảo vệ | Có, nếu thực hiện đúng |
| TLS | Bảo vệ kênh truyền giữa các đầu mút | Có cho dữ liệu trên đường truyền, không tự bảo vệ mọi nơi lưu |
| KMS/Vault | Quản lý khóa/secret, quyền và lifecycle | Tùy khả năng và cấu hình dịch vụ |

Trong Kubernetes, trường `data` của Secret thường chứa giá trị **Base64-encoded**. Điều này **không tự chứng minh etcd đang mã hóa dữ liệu at rest**, cũng không thay thế RBAC và chính sách kiểm soát truy cập. Cấu hình cluster có thể bổ sung encryption at rest, nhưng cần được vận hành và xác minh riêng.

**Nhớ:** nếu một người có quyền đọc YAML/manifest và chỉ cần Base64 decode là thấy password, thì password không được bảo vệ bằng mã hóa bí mật ở lớp dữ liệu đó.

## 5. Threat model: bí mật có thể lộ ở đâu?

Không nên bắt đầu bằng câu hỏi “mã hóa chuỗi trong YAML bằng thuật toán nào?”. Nên bắt đầu bằng “ai có thể đọc bí mật ở từng giai đoạn?”

~~~text
Người / CI / hệ thống cấp secret
            |
            v
   Secret manager / Vault / KMS
       kiểm soát quyền
       audit và lifecycle
            |
       kênh truyền phù hợp
            |
            v
   Runtime / container / VM
       Environment / file mount / SDK
            |
            v
   Spring Environment / Binder
            |
            v
   Bean, HTTP client, JDBC pool
            |
            v
   Dịch vụ bên ngoài
~~~

Những bề mặt cần xét:

- **Git repository:** mật khẩu, token, private key bị commit.
- **CI/CD:** job logs, artifacts, pipeline variables, caches, debug output.
- **Container image:** secret bị copy vào image layer.
- **Host filesystem:** file mount, backup, permission, snapshot.
- **Container/cluster control plane:** ai có quyền đọc Secret hoặc mô tả workload.
- **Process environment:** người có quyền inspect tiến trình hoặc công cụ debug có thể đọc.
- **Command-line arguments:** có thể xuất hiện trong process listings, logs và deployment metadata.
- **Memory:** giá trị sau giải mã được sử dụng ở dạng có thể đọc bởi tiến trình.
- **Application logs:** `toString()`, exception, HTTP headers, debug interceptors.
- **Actuator/observability:** endpoint, tracing attributes, metrics labels, heap dumps.
- **Network:** đường truyền từ secret store tới ứng dụng và từ ứng dụng tới hệ thống sử dụng secret.
- **Credentials lifecycle:** key hết hạn, nhân sự rời dự án, sự cố lộ token, việc thu hồi quyền.

Mã hóa trong file chỉ xử lý **một phần** bề mặt. Nếu khóa giải mã cũng nằm trong repo, trong image hoặc trong cùng file, lợi ích bảo vệ có thể rất thấp.

## 6. Ba trạng thái dữ liệu cần bảo vệ

Có ba khái niệm thường gặp:

**At rest — khi lưu trữ:** Secret nằm trong database của secret store, file, snapshot, disk hoặc backup. Có thể bảo vệ bằng mã hóa at rest, phân quyền và quản lý key.

**In transit — khi truyền:** Secret đi từ secret manager tới pod/service hoặc từ ứng dụng tới dịch vụ. Sử dụng kênh được xác thực và mã hóa như TLS/mTLS phù hợp.

**In use — khi đang sử dụng:** Secret phải được ứng dụng đọc để gửi yêu cầu, tạo kết nối hoặc ký một thông điệp. Nếu ứng dụng thật sự cần mật khẩu, đến một thời điểm giá trị đó thường phải có thể được truy cập trong process memory.

Do đó, một ứng dụng có thể lấy secret từ kho được mã hóa at rest qua TLS nhưng secret vẫn hiện diện trong `String` Java sau khi được bind.

Một số hệ thống có thể giảm nhu cầu nắm giữ secret lâu dài bằng workload identity, short-lived tokens hoặc dịch vụ ký từ xa. Nhưng không có cách mặc định nào của Spring Boot làm biến mất toàn bộ rủi ro dữ liệu đang sử dụng.

## 7. Tại sao “mã hóa property trong YAML” chưa đủ?

Giả sử một dự án tự mã hóa:

~~~yaml
payment:
  gateway:
    api-key: "ENC(some-ciphertext)"
~~~

Ứng dụng cần biết khóa để giải mã. Nếu deployment đặt ngay bên cạnh:

~~~yaml
payment:
  gateway:
    decryption-key: "example-key"
~~~

thì ai đọc được cùng nguồn cấu hình có thể có **cả ciphertext lẫn decryption key**. Mô hình này không giải quyết vấn đề truy cập trái phép với cùng mức quyền đọc.

Ngay cả khi key được đặt trong biến môi trường, vẫn cần trả lời:

- Ai cấp biến môi trường đó?
- Ai có quyền đọc job, process hoặc pod spec?
- Key tồn tại lâu đến đâu?
- Có policy phân quyền giải mã theo service hay không?
- Nếu key bị lộ, có thể rotate thế nào?
- Có audit khi service sử dụng key không?
- Ciphertext có phiên bản/metadata thuật toán để chuyển đổi sau này không?

Một thiết kế trưởng thành thường đặt quyền giải mã hoặc quyền lấy secret ở **dịch vụ quản lý bên ngoài**. Ứng dụng xác thực bằng danh tính workload thay vì mang theo một master key dùng chung lâu dài.

## 8. Secret manager là gì?

Một **secret manager** là hệ thống chuyên quản lý dữ liệu bí mật và cách chúng được cấp cho ứng dụng. Các tính năng phụ thuộc từng sản phẩm, nhưng có thể gồm:

- Lưu trữ secret trong hệ thống có kiểm soát truy cập.
- Phân quyền đọc theo identity của service, environment và đường dẫn secret.
- Mã hóa at rest với quản lý khóa phù hợp.
- Kênh giao tiếp được bảo vệ.
- Audit lần đọc, cập nhật, thu hồi.
- Versioning, rotation, expiration hoặc lease.
- Tích hợp với workload identity/role, không cần hard-code root token.
- Trong một số trường hợp, cấp credential động sống ngắn thay cho password dùng chung.

Ví dụ hệ sinh thái: HashiCorp Vault; secret manager của các cloud provider; secret-control-plane của nền tảng triển khai kết hợp với KMS và các controller thích hợp.

Không phải sản phẩm nào cũng cung cấp mọi tính năng, và **lưu secret trong một service có tên “secret manager” không tự động giải quyết phân quyền sai**. Người vận hành phải thiết kế identity, policies và vòng đời.

## 9. Vault và KMS có vai trò giống nhau không?

Không hoàn toàn.

**KMS (Key Management Service):** thường tập trung vào quản lý khóa mật mã và các thao tác cryptographic như encrypt/decrypt/sign, kiểm soát quyền sử dụng key và audit. KMS có thể tham gia cơ chế **envelope encryption** để bảo vệ dữ liệu lớn bằng data key.

**Vault/secret manager:** thường tập trung vào việc lưu và cấp secret cho workload; có thể hỗ trợ version, policy, dynamic credentials và lease. Một hệ thống secret manager cũng có thể dùng KMS ở tầng dưới để bảo vệ master key hoặc dữ liệu lưu.

So sánh nhanh:

| Câu hỏi | Secret manager/Vault | KMS |
| --- | --- | --- |
| Lưu phiên bản API token để service đọc? | Thường phù hợp | Không nhất thiết là vai trò chính |
| Cấp database user/password có lease ngắn? | Một số hệ thống hỗ trợ | Không phải chức năng mặc định của mọi KMS |
| Giữ quyền sử dụng encryption key? | Có thể tích hợp | Vai trò trọng tâm |
| Decrypt data key/ciphertext theo policy? | Tùy khả năng | Thường là chức năng đặc trưng |
| Làm Spring Boot tự có secret không? | Không, cần tích hợp | Không, cần tích hợp |

Trong thực tế, có thể dùng **cả hai**: KMS bảo vệ khóa, secret manager quản lý phiên bản và cấp secret, Spring Boot chỉ nhận kết quả thông qua nguồn đã được tích hợp.

## 10. Envelope encryption qua KMS: hình dung đúng

Khi một hệ thống cần lưu ciphertext trong repository hoặc database, mô hình envelope encryption có thể được dùng:

~~~text
Secret gốc
    |
    v
Mã hóa bằng data encryption key (DEK)
    |
    +--> Ciphertext của secret
    |
    +--> DEK được bảo vệ / wrapped bằng KMS key
               |
               v
        Chỉ workload được cấp quyền mới
        gọi KMS để unwrap/decrypt
~~~

Khi ứng dụng cần dùng secret:

1. Workload xác thực với IAM/KMS bằng identity được cấp quyền.
2. Hệ thống lấy ciphertext và encrypted data key.
3. Gọi KMS phù hợp để unwrap data key hoặc decrypt theo thiết kế.
4. Giải mã dữ liệu cần thiết trong process.
5. Dùng giá trị cho đúng mục đích, hạn chế thời gian/bề mặt truy cập.

Đây là mô hình khái niệm, không phải đoạn code production để tự triển khai thuật toán. Cần dùng SDK/thư viện đã được kiểm chứng, nonce/IV, authenticated encryption, key version, error handling, retry, audit và policy phù hợp.

**Cảnh báo:** tự sáng tác một thuật toán mã hóa property hoặc đưa master key vào JAR thường làm tăng rủi ro. Nếu cần encryption, ưu tiên dịch vụ/SDK chuẩn mà tổ chức đã vận hành.

## 11. Cách đơn giản: ứng dụng đọc secret từ biến môi trường

Một mô hình phổ biến là deployment cấp secret cho tiến trình qua environment variable.

File `application.yml` chỉ chứa placeholder:

~~~yaml
warehouse:
  client:
    base-url: "https://warehouse.example.invalid"
    timeout: 3s
    api-key: "${WAREHOUSE_API_KEY}"
~~~

Spring sẽ tìm `WAREHOUSE_API_KEY` trong các nguồn property hiện có khi phân giải placeholder.

Typed configuration:

~~~java
package example.warehouse;

import jakarta.validation.constraints.NotBlank;
import java.net.URI;
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "warehouse.client")
public record WarehouseClientProperties(
        URI baseUrl,
        Duration timeout,
        @NotBlank String apiKey
) {}
~~~

Đăng ký:

~~~java
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(WarehouseClientProperties.class)
class WarehouseConfiguration {}
~~~

**Lợi ích:** không đặt secret thật trực tiếp trong YAML/JAR. Ứng dụng dùng cùng một artifact cho nhiều môi trường.

**Giới hạn:** environment variable không mặc nhiên được mã hóa; ai có quyền truy cập phù hợp vào process, deployment system hoặc logs có thể đọc nó. Secret phải được cấp bằng pipeline hoặc nền tảng có phân quyền, và phải tránh truyền qua command line công khai hoặc ghi giá trị vào build logs.

Không viết vào README một lệnh shell chứa API key thật. Chỉ mô tả tên biến và cơ chế cấp bởi hệ thống triển khai.

## 12. Placeholder không phải “giải mã bí mật”

Trong ví dụ:

~~~yaml
warehouse:
  client:
    api-key: "${WAREHOUSE_API_KEY}"
~~~

Spring Boot chỉ **phân giải placeholder** sang giá trị của property `WAREHOUSE_API_KEY`. Nếu giá trị đầu vào là ciphertext, placeholder không tự giải mã nó.

Tương tự:

~~~yaml
warehouse:
  client:
    api-key: "ENC(${WAREHOUSE_CIPHERTEXT})"
~~~

không tự tạo decryption pipeline. Nó chỉ tạo một chuỗi có chứa giá trị nội suy trong dấu `ENC(...)`, trừ khi một thành phần khác được tích hợp xử lý chuỗi đó.

Cần tách khái niệm:

- Placeholder resolution: tìm key từ Environment.
- Property binding: chuyển giá trị sang Java type.
- Decryption: dùng thuật toán và encryption key hoặc dịch vụ bên ngoài.
- Authorization: xác định workload nào được phép lấy/decrypt secret.

Đây là bốn trách nhiệm khác nhau.

## 13. Về lỗi khi biến môi trường chưa được cấp

Nếu không có `WAREHOUSE_API_KEY`, property trên có placeholder chưa được phân giải. Tùy đường bind và Spring Boot version/configuration, application có thể báo lỗi unresolved placeholder, bind/validation, hoặc nhận dữ liệu không như kỳ vọng.

Không nên chỉ dựa vào tên placeholder để bảo đảm **fail-fast** trong mọi đường code. Với secret bắt buộc, nên:

- Sử dụng `@NotBlank` hoặc validation tương đương trên typed configuration.
- Kiểm tra rằng không chấp nhận placeholder mẫu hoặc chuỗi bất thường.
- Không có default secret giả ở production.
- Có integration test thiếu secret để bảo đảm startup bị từ chối theo đúng hợp đồng của ứng dụng.
- Tránh log giá trị secret trong error message.

Một default rỗng:

~~~yaml
warehouse:
  client:
    api-key: "${WAREHOUSE_API_KEY:}"
~~~

có thể cho phép Binder nhận chuỗi rỗng khi environment variable không có. Điều này phù hợp **nếu validation sẽ từ chối** chuỗi rỗng ở môi trường bắt buộc, nhưng không nên dùng để che thiếu secret mà không kiểm tra.

## 14. Rủi ro của biến môi trường

Biến môi trường thường thuận tiện và được nhiều nền tảng hỗ trợ, nhưng không phải nơi lưu bí mật có tính năng bảo mật tự thân.

Những rủi ro:

- Người có quyền debug/inspect process có thể xem environment.
- CI log hoặc script `set -x` có thể in lệnh và biến.
- Dữ liệu có thể xuất hiện trong metadata của orchestrator, process dumps hoặc báo cáo sự cố.
- Biến được kế thừa bởi child process nếu môi trường chạy không kiểm soát.
- Tên biến khác nhau giữa local, CI và production dễ gây lỗi.
- Thay đổi biến môi trường sau khi process đã khởi động không tự thay giá trị trong bean đã bind.

Đối với production có yêu cầu bảo mật cao, **file mount ngắn hạn, identity-based retrieval hoặc secret store integration** có thể phù hợp hơn, tùy hạ tầng.

Không có một câu trả lời “environment variable luôn an toàn nhất” cho mọi hệ thống. Cần cân nhắc threat model và cách cấp quyền thực tế.

## 15. Dùng configtree: đọc secret từ thư mục được mount

Spring Boot Config Data hỗ trợ scheme **`configtree:`** để biểu diễn các file trong một directory thành properties.

Giả sử nền tảng triển khai mount các file:

~~~text
/run/secrets/warehouse/
  warehouse.client.api-key
  warehouse.client.client-id
~~~

Nội dung mỗi file là giá trị secret/setting tương ứng, không phải một file YAML. Không cần ghi giá trị thật vào repository.

Trong `application.yml`:

~~~yaml
spring:
  config:
    import: "configtree:/run/secrets/warehouse/"
~~~

Spring Boot sẽ đưa các file trong cây cấu hình thành properties để code hoặc Binder có thể đọc theo tên file/đường dẫn.

Ví dụ:

~~~java
String apiKey = environment.getProperty(
    "warehouse.client.api-key"
);
~~~

Hoặc typed record:

~~~java
@Validated
@ConfigurationProperties(prefix = "warehouse.client")
public record WarehouseClientProperties(
        @NotBlank String apiKey,
        String clientId
) {}
~~~

Nếu file `warehouse.client.api-key` tồn tại trong config tree và không bị nguồn có ưu tiên cao hơn ghi đè, Binder có thể nhận nội dung file.

**Đây là cách đưa bí mật vào Spring Environment**, không phải một thuật toán mã hóa. Nội dung file có thể là bản rõ được platform mount cho container; bảo vệ dựa vào secret manager/orchestrator, permission filesystem và quyền chạy process.

## 16. Khi nào dùng optional:configtree?

Ví dụ:

~~~yaml
spring:
  config:
    import: "optional:configtree:/run/secrets/warehouse/"
~~~

Tiền tố `optional:` cho phép vị trí import không tồn tại trong những trường hợp phù hợp. Nó hữu ích nếu developer local không có mount secret.

Nhưng trong production, thiếu thư mục secret có thể là lỗi nghiêm trọng. Khi đó có thể chọn import **không optional**:

~~~yaml
spring:
  config:
    import: "configtree:/run/secrets/warehouse/"
~~~

Nếu thư mục không tồn tại, Config Data import có thể làm ứng dụng fail khi bootstrap. Tuy nhiên, **thư mục tồn tại mà thiếu một file cần thiết** vẫn phải được kiểm tra qua typed properties validation hoặc logic yêu cầu cụ thể.

Một thiết kế có thể dùng profile/Config Data để quyết định vị trí import theo môi trường, nhưng đừng dùng cấu hình optional để vô tình cho ứng dụng production khởi động thiếu secret.

**Quy tắc:** optional chỉ điều chỉnh xử lý **location không có**; nó không khiến token rỗng trở thành hợp lệ và không thay ràng buộc an toàn của ứng dụng.

## 17. File configtree lấy bí mật từ đâu?

`configtree:` không tự kết nối Vault hay KMS. Có một thành phần **bên ngoài** tạo hoặc mount file:

~~~text
Secret manager / Kubernetes Secret / CSI driver /
Docker secret / init container / deployment system
                  |
                  v
        File trong /run/secrets/warehouse/
                  |
                  v
      Spring Boot configtree import
                  |
                  v
       Environment + Binder
                  |
                  v
          Bean sử dụng secret
~~~

Ai chịu trách nhiệm?

- **Secret platform:** cấp secret và giới hạn ai được cấp.
- **Container orchestrator/driver:** mount file, giới hạn quyền file và danh tính workload.
- **Spring Boot Config Data:** đọc file thành property.
- **Application:** validate cấu hình, sử dụng secret đúng mục đích và xử lý thay đổi vòng đời.

Nếu file chỉ được tạo bằng cách copy secret từ repo ra container, thì bài toán nguồn lưu secret vẫn chưa được giải quyết. Quan trọng là **đường cấp secret có kiểm soát**.

## 18. Một ví dụ Kubernetes: Secret được mount thành file

Ở Kubernetes, có thể mount key của Secret vào pod dưới dạng file.

Ví dụ phần liên quan của một Deployment (giả định Secret `warehouse-client-secrets` đã được tạo bởi quy trình an toàn):

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: warehouse-client
spec:
  replicas: 1
  selector:
    matchLabels:
      app: warehouse-client
  template:
    metadata:
      labels:
        app: warehouse-client
    spec:
      containers:
        - name: app
          image: registry.example.invalid/warehouse-client:release
          volumeMounts:
            - name: warehouse-secrets
              mountPath: /run/secrets/warehouse
              readOnly: true
      volumes:
        - name: warehouse-secrets
          secret:
            secretName: warehouse-client-secrets
            items:
              - key: api-key
                path: warehouse.client.api-key
~~~

Trong `application.yml`:

~~~yaml
spring:
  config:
    import: "configtree:/run/secrets/warehouse/"
~~~

Ví dụ minh họa mapping:

~~~text
Secret key: api-key
       |
       v
Mount file:
  /run/secrets/warehouse/warehouse.client.api-key
       |
       v
Spring property:
  warehouse.client.api-key
~~~

Lưu ý các điều kiện quan trọng:

- Đây **không** phải một manifest đầy đủ cho production; cần bổ sung resource limits, security context, service account, probes, network policies và các thiết lập theo hạ tầng.
- Không commit manifest có secret thật trong `stringData` hoặc `data` chỉ vì nó là YAML.
- Quyền đọc Kubernetes Secret, RBAC, encryption at rest của control plane và quyền truy cập tới container phải được cấu hình/kiểm chứng riêng.
- Secret volume là cơ chế cấp file; ứng dụng vẫn phải bảo vệ secret sau khi đọc vào bộ nhớ.
- Nếu backend secret thay đổi và volume được cập nhật, Spring Boot **không tự rebind toàn bộ bean** chỉ vì file thay đổi.

Nên dùng một công cụ/deployment workflow được tổ chức phê duyệt để tạo và quản lý Secret, thay vì tự lưu password vào Git.

## 19. Secret mount khác “mã hóa property”

So sánh hai mô hình:

**Mô hình A — ciphertext nằm trong YAML:**

~~~yaml
warehouse:
  client:
    api-key: "ENC(ciphertext)"
~~~

Ứng dụng phải có thư viện giải mã và một khóa giải mã được bảo vệ. Nếu không, chỉ là chuỗi.

**Mô hình B — file secret được nền tảng mount:**

~~~text
/run/secrets/warehouse/warehouse.client.api-key
~~~

Và:

~~~yaml
spring:
  config:
    import: "configtree:/run/secrets/warehouse/"
~~~

Spring Boot đọc nội dung file; việc secret được mã hóa khi lưu ở secret manager và cách file được mount thuộc trách nhiệm hạ tầng.

Mô hình B giúp **tách mã nguồn/artifact khỏi secret**, nhưng nội dung file trong container có thể ở dạng plaintext. Cần permission, isolation và hạn chế người có quyền truy cập. Không nên gọi bản thân `configtree:` là “cơ chế decrypt của Spring Boot”.

## 20. Spring Cloud Vault và các tích hợp ngoài Spring Boot core

Nếu ứng dụng cần lấy bí mật trực tiếp từ Vault, một giải pháp trong hệ sinh thái Spring là **Spring Cloud Vault** (phải chọn phiên bản tương thích với Spring Boot/Spring Cloud đang dùng). Thành phần này có thể tích hợp Vault secret backend vào quá trình cấu hình, qua các cơ chế bootstrap/Config Data được phiên bản hỗ trợ.

Nhưng đó là **thành phần bổ sung**, không tự xuất hiện chỉ vì ứng dụng có `spring-boot-starter`.

Một luồng ý tưởng:

~~~text
Application identity
        |
        v
Spring Cloud Vault integration
        |
        v
Vault authentication + policy
        |
        v
Vault secret backend
        |
        v
PropertySource / configuration binding
        |
        v
Bean ứng dụng
~~~

Cần quyết định:

- Auth method: AppRole, Kubernetes/workload identity, cloud IAM hoặc phương thức được tổ chức chấp thuận.
- Path và namespace của secret.
- Quyền chỉ đọc với các path cần thiết.
- TLS certificate trust và endpoint Vault.
- Môi trường/phân tách dev, staging, prod.
- Secret leasing/renewal nếu backend cung cấp.
- Hành vi khi Vault tạm không sẵn sàng.
- Rotation và cách cập nhật các client đã dùng credential.

Không đưa Vault root token vào `application.yml` để “giải quyết nhanh” việc tích hợp; điều đó có thể tạo một secret quyền rất rộng trong cùng bề mặt mà ta muốn bảo vệ.

## 21. SDK truy cập secret manager trực tiếp

Một cách khác là ứng dụng dùng SDK của cloud provider hoặc secret manager để lấy secret bằng identity của workload. Ở mức thiết kế:

~~~java
public interface SecretProvider {
    String getRequiredSecret(String logicalName);
}
~~~

Ví dụ service:

~~~java
public final class WarehouseCredentialsService {

    private final SecretProvider provider;

    public WarehouseCredentialsService(SecretProvider provider) {
        this.provider = provider;
    }

    public String apiKey() {
        return provider.getRequiredSecret(
            "warehouse/client/api-key"
        );
    }
}
~~~

Đây là interface **minh họa**, không phải API Spring Boot có sẵn. Implementation thực tế phải dùng SDK và chính sách của provider đã chọn.

Khi dùng SDK trực tiếp, ứng dụng chịu trách nhiệm lớn hơn:

- Auth và refresh access token tới secret manager.
- Timeout/retry/backoff.
- Cache/TTL để không gọi secret store trên mọi request.
- Phân biệt secret chưa có, không được quyền đọc và lỗi mạng.
- Không đưa secret vào exception hoặc metrics.
- Xử lý rotation/expiry.
- Fail-open hay fail-closed theo rủi ro; thông thường không thể dùng “secret mặc định” khi kho tạm lỗi.
- Tests có fake provider, integration tests với môi trường test được cấp quyền.

Mô hình này phù hợp khi secret cần được lấy theo hành động hoặc vòng đời riêng, không nhất thiết phải hiện diện như một property bình thường trong Environment.

## 22. Workload identity quan trọng hơn hard-coded access key

Một hệ thống secret tốt cần trả lời: “workload nào được quyền đọc path nào?”

Thay vì lưu:

~~~yaml
secret-store:
  access-key: "long-lived-admin-key"
~~~

ứng dụng có thể dùng identity của service account, VM, pod hoặc cơ chế federation được cloud/platform cung cấp.

Ví dụ ở mức chính sách:

~~~text
service: warehouse-client-prod
environment: production
allowed:
  read: secret/production/warehouse/client/*
denied:
  read: secret/production/payments/*
  write: secret/*
~~~

Đây là mô hình phân quyền khái niệm. Cú pháp policy thật phụ thuộc secret manager.

Nguyên tắc:

1. **Least privilege:** chỉ quyền đọc bí mật thực sự cần.
2. **Environment isolation:** staging không được đọc production secret.
3. **Short-lived credentials:** dùng token/lease ngắn hạn khi khả thi.
4. **Identity rotation:** không dựa vào một key chia sẻ cố định giữa nhiều ứng dụng.
5. **Audit:** ghi nhận ai đọc/đổi/thu hồi secret.
6. **Revocation:** có khả năng khóa quyền mà không sửa source code.

Có mã hóa dữ liệu mạnh nhưng cấp quyền đọc cho toàn bộ cluster hoặc mọi developer thì mô hình vẫn rủi ro.

## 23. Static secret và dynamic secret

**Static secret:** ví dụ API token của nhà cung cấp ngoài hoặc password DB được tạo thủ công. Nó tồn tại cho tới khi người quản trị đổi hoặc thu hồi.

**Dynamic secret:** một số secret manager có thể cấp credential dùng ngắn hạn theo identity/lease, ví dụ database user tạm thời với hạn sử dụng cụ thể.

So sánh:

| Thuộc tính | Static secret | Dynamic secret |
| --- | --- | --- |
| Tạo và phân phối | Có thể theo quy trình thủ công | Có thể tạo khi workload yêu cầu |
| Thời gian sống | Thường dài hơn | Có thể ngắn |
| Rủi ro lộ | Có thể hữu hiệu lâu nếu không rotate | Có thể giới hạn bằng TTL |
| Rotation | Cần cập nhật ở nguồn và consumer | Có thể có lease/renew/revoke |
| Độ phức tạp vận hành | Thấp hơn lúc đầu | Cần hỗ trợ lifecycle ở cả store và client |
| Phù hợp | API nhà cung cấp không hỗ trợ lease | DB/backend hỗ trợ cấp quyền động |

Dynamic credentials không tự được Spring Boot core quản lý. Nếu Vault cấp database credentials có TTL, connection pool như HikariCP và các kết nối đang tồn tại cần chiến lược gia hạn/đổi thông tin và xử lý kết nối cũ.

**Có TTL ngắn chưa đủ** nếu ứng dụng vẫn giữ credential hết hạn trong một singleton bean mãi mãi.

## 24. Rotation không đồng nghĩa thay file là xong

Giả sử secret store đã đổi password vào thời điểm T.

Các bước cần đồng bộ có thể gồm:

~~~text
1. Secret store tạo phiên bản mới
2. Platform/SDK cấp phiên bản mới cho workload
3. Ứng dụng nhận bản mới
4. Consumer/client/connection pool dùng credential mới
5. Xử lý các kết nối hoặc credential cũ
6. Thu hồi phiên bản trước theo cửa sổ chuyển đổi
7. Xác nhận health và audit
~~~

Trong ứng dụng Spring Boot:

~~~java
@Service
class ClientService {
    private final String apiKey;

    ClientService(WarehouseClientProperties properties) {
        this.apiKey = properties.apiKey();
    }
}
~~~

Field `apiKey` được gán khi bean được tạo. Kể cả file trên filesystem thay đổi, field này **không tự cập nhật**. Tương tự, một JDBC pool có thể giữ credentials đã dùng để mở connections.

Các chiến lược:

- Restart/rollout ứng dụng sau khi secret được cấp bản mới.
- Tích hợp refresh/rebind được thiết kế và kiểm thử.
- SDK secret provider có cache TTL/lease renewal và client có khả năng thay credential.
- Dùng cơ chế identity/token ngắn hạn mà client library hiểu.

Không bật refresh tùy tiện nếu không có kế hoạch xử lý thread-safety, connection pool và failure window. Nhiều hệ thống chọn **rollout có kiểm soát** vì dễ chứng minh hơn.

## 25. Rotation hai phiên bản để tránh downtime

Một rủi ro phổ biến: secret store đổi DB password rồi database lập tức từ chối mật khẩu cũ, trong khi một số pod chưa nhận password mới.

Một kịch bản giảm gián đoạn:

1. Chuẩn bị credential hoặc identity mới ở backend.
2. Cho phép song song credential cũ/mới nếu hệ thống hỗ trợ.
3. Cấp phiên bản mới qua secret manager.
4. Rollout/restart hoặc refresh ứng dụng.
5. Kiểm tra các pod/client đã kết nối bằng credential mới.
6. Thu hồi credential cũ.
7. Kiểm tra không còn lỗi xác thực và lưu audit.

Nếu backend không hỗ trợ hai credential song song, cần một kế hoạch cutover phù hợp và có thể chấp nhận gián đoạn ngắn.

Đừng chỉ kiểm tra rằng `Environment` đã thấy chuỗi mới. Cần kiểm tra rằng **thành phần sử dụng secret** (ví dụ DB pool, HTTP client, message broker connection) đã dùng credential mới.

## 26. Secret trong Spring Environment vẫn có thể bị ghi đè

Spring Boot có thứ tự ưu tiên property sources. Khi một secret được đưa vào Config Data hoặc Environment, một nguồn **ưu tiên cao hơn** có thể định nghĩa cùng key.

Ví dụ:

~~~yaml
spring:
  config:
    import: "configtree:/run/secrets/warehouse/"
~~~

File mount cấp:

~~~text
warehouse.client.api-key = giá trị do nền tảng cấp
~~~

Nhưng nếu deployment còn có command-line argument cùng key, một cấu hình ưu tiên cao có thể ghi đè secret này theo quy tắc nguồn của Spring Boot.

Đây là điều cần xem xét về security:

- Không để nhiều nơi cùng sở hữu một secret key mà không có chính sách rõ.
- Tránh đặt secret trong command-line arguments.
- Xem xét ai có quyền chỉnh environment/CLI của workload.
- Dùng tên property canonical và test giá trị hiệu lực theo các nguồn triển khai thực.
- Không hiển thị secret value khi xác minh source precedence.

**Bảo mật của secret không chỉ ở nơi lưu giá trị gốc**; nếu một người có quyền thay nguồn cấu hình ưu tiên cao, người đó có thể thay credential mà ứng dụng thực sự sử dụng.

## 27. Config Data import không phải công cụ đảm bảo secret được bảo vệ

Ví dụ:

~~~yaml
spring:
  config:
    import: "file:./config/credentials.properties"
~~~

Nếu file chứa:

~~~properties
warehouse.client.api-key=some-plaintext-placeholder
~~~

Spring Boot có thể đọc file như Config Data theo quy tắc định dạng/lifecycle. Nhưng không vì dùng `spring.config.import` mà file được mã hóa. Nếu file nằm trong repo hoặc được copy vào image, nó vẫn lộ cho người có quyền đọc.

Ngược lại, một file trên volume được cấp từ secret manager qua driver có phân quyền, audit và rotation có thể là giải pháp hợp lý. **Nguồn sinh ra file và quyền truy cập** quan trọng hơn chỉ tên property source.

Ngoài ra, Config Data import có quy tắc precedence của nó. Nếu đổi từ `@PropertySource` sang `spring.config.import` chỉ để hỗ trợ YAML/secret file, phải kiểm tra các key trùng nhau vì mức ưu tiên hiệu lực có thể thay đổi.

## 28. Cẩn thận với .env và Docker Compose

Một file:

~~~text
.env
~~~

thường được một số công cụ triển khai dùng để cung cấp biến khi dựng cấu hình. Nhưng **Spring Boot không tự đọc mọi file `.env` trong thư mục chạy chỉ vì file đó có tên .env**.

Trong Docker Compose, file `.env` có thể phục vụ **variable substitution** của Compose; không nên mặc định mọi key trong file ấy đã được truyền vào environment của container. Cần kiểm tra `environment` hoặc `env_file` của service và quyền đọc file.

Nếu file `.env` có secret thật:

- Không commit vào Git.
- Không copy vào container image bằng Dockerfile.
- Không in nội dung vào CI log.
- Đặt quyền đọc phù hợp.
- Cân nhắc chuyển sang secret mount/secret manager khi cần kiểm soát mạnh hơn.

`.gitignore` là lớp hỗ trợ tránh commit nhầm, **không phải biện pháp bảo mật đủ** nếu file đã nằm trong Git history, artifact hoặc backup.

## 29. Các nguy cơ rò rỉ do log và toString()

Một cấu hình dạng record:

~~~java
@ConfigurationProperties(prefix = "payment")
public record PaymentProperties(
        String merchantId,
        String apiSecret
) {}
~~~

Java record sinh `toString()` mặc định, và nếu gọi:

~~~java
log.info("Payment config: {}", properties);
~~~

thì nội dung `apiSecret` có thể xuất hiện trong log.

Đây là ví dụ của **secret at use**, nơi encryption at rest không còn ngăn rò rỉ.

Quy tắc:

- Không log toàn bộ `@ConfigurationProperties` bean nếu có secret.
- Không dùng `record.toString()` vô điều kiện cho kiểu giữ password/token.
- Nếu cần log trạng thái cấu hình, chỉ log Boolean như `configured=true` hoặc tên nguồn không nhạy cảm.
- Dùng structured logging/redaction policy; không phụ thuộc hoàn toàn vào keyword filtering.
- Không để client HTTP debug interceptor in `Authorization` hoặc custom API-key header.
- Không đưa secret vào exception message hoặc trace span attributes.

Nếu phải viết một `toString()` riêng, luôn loại bỏ hoặc mask secret. Nhưng cách tốt nhất là **không log cấu hình chứa secret**.

## 30. Actuator /env và /configprops có rủi ro gì?

Spring Boot Actuator có những endpoint như:

~~~text
/actuator/env
/actuator/configprops
~~~

Chúng có thể giúp chẩn đoán nguồn cấu hình và configuration properties. Tùy phiên bản và cấu hình, các giá trị nhạy cảm có thể được **sanitized hoặc chỉ hiện dạng masked** theo chính sách mặc định.

Tuy nhiên, không nên suy ra endpoint này an toàn để public:

- Có thể lộ tên key, source/path hoặc topology, dù value bị mask.
- Cấu hình hiển thị giá trị có thể bị thay đổi bởi người vận hành.
- Các endpoint có thể bị expose ra internet nếu security rules sai.
- Bean/class cấu hình có thể chứa thông tin nhạy cảm không được nhận diện chỉ bằng tên key.
- Rủi ro từ heapdump, threaddump, logs, metrics/tracing còn tồn tại ngoài `env` và `configprops`.

Nguyên tắc:

1. Chỉ expose endpoint thật sự cần.
2. Bảo vệ bằng authentication/authorization/network isolation.
3. Đánh giá khả năng hiển thị giá trị theo phiên bản Spring Boot và cấu hình thực.
4. Không bật `show-values=always` hoặc cơ chế tương đương chỉ để dễ debug production.
5. Không đặt bí mật trong property name, metric labels hoặc tag.
6. Review các endpoint dump/diagnostic có thể làm lộ dữ liệu runtime.

Actuator sanitization là lớp giảm thiểu rủi ro, **không thay thế secret management**.

## 31. Exception và startup failure cũng có thể làm lộ secret

Khi cấu hình thiếu hoặc sai, có thể phát sinh `BindException` hoặc validation failure. Thông báo lỗi hữu ích để xác định key bị lỗi, nhưng có thể chứa giá trị cấu hình tùy loại lỗi và cách formatter/logger được thiết lập.

Ví dụ một phần mềm tự viết:

~~~java
throw new IllegalStateException(
    "Invalid API token: " + properties.apiKey()
);
~~~

là cách làm không an toàn.

Nên viết:

~~~java
throw new IllegalStateException(
    "warehouse.client.api-key is missing or invalid"
);
~~~

Với credential thật, thông báo lỗi nên nói **key nào cần kiểm tra**, không tiết lộ giá trị.

Một rule quan trọng: không chỉ tránh `System.out.println(secret)` mà còn tránh việc secret được nối vào:

- Exception message.
- URI/URL query.
- HTTP access log.
- MDC/logging context.
- Metric labels.
- Trace attributes.
- Audit details không có mask.
- Health indicator diagnostic output.

## 32. Secret có thể lộ trong command-line arguments

Một cách khởi động không nên dùng với secret thật:

~~~bash
java -jar app.jar --payment.api-key=<actual-secret>
~~~

Command-line arguments có thể được ghi nhận trong process listings, shell history, deployment descriptors hoặc hệ thống giám sát.

Spring Boot cho phép command-line override về mặt cấu hình, nhưng **cho phép kỹ thuật không đồng nghĩa an toàn cho secret**.

Dùng nền tảng cấp secret theo identity, secret mount hoặc phương án được tổ chức chấp thuận. Với debugging, không in giá trị trong output và không cố xác minh secret bằng cách echo ra console.

Java system properties `-Dpayment.api-key=...` cũng cần được xem là nhạy cảm vì có thể xuất hiện trong runtime inspection hoặc cấu hình khởi chạy. Không mặc định `-D` an toàn hơn CLI thông thường.

## 33. Secret trong CI/CD: chỉ cấp tại nơi cần

Một pipeline build không nên bắt buộc phải biết DB password của production nếu nhiệm vụ chỉ là compile và chạy unit tests.

Mô hình tốt:

~~~text
Build:
  source -> compile -> test với fake credentials -> artifact

Deploy:
  artifact -> runtime identity -> secret access -> application startup
~~~

Thực hiện:

- Phân biệt build-time dependency và runtime secret.
- Không copy secret vào Docker image layer hoặc JAR.
- Hạn chế job nào được quyền đọc production secret.
- Dùng pipeline secret masking nhưng không xem masking là bảo vệ tuyệt đối.
- Tránh command echo, script debug và artifact upload có chứa secret.
- Có audit khi pipeline truy cập secret.
- Không dùng lại production secret cho test/local.
- Rotate khi nghi ngờ lộ; xóa khỏi Git ở commit mới **không làm nó biến mất khỏi Git history**.

Một pipeline có thể build cùng artifact cho staging và production, rồi mỗi environment cấp secret tương ứng tại runtime.

## 34. Ví dụ đối chiếu ba phương án cấp API key

Giả sử ứng dụng có typed bean:

~~~java
@Validated
@ConfigurationProperties(prefix = "warehouse.client")
public record WarehouseClientProperties(
        @NotBlank String apiKey
) {}
~~~

**Phương án A — commit trong YAML:**

~~~yaml
warehouse:
  client:
    api-key: "real-key-from-production"
~~~

Rủi ro cao; không nên làm.

**Phương án B — placeholder lấy từ environment:**

~~~yaml
warehouse:
  client:
    api-key: "${WAREHOUSE_API_KEY}"
~~~

Không commit giá trị thật, nhưng cần bảo vệ nơi cấp environment variable và process.

**Phương án C — secret file do platform mount:**

~~~yaml
spring:
  config:
    import: "configtree:/run/secrets/warehouse/"
~~~

File mount:

~~~text
/run/secrets/warehouse/warehouse.client.api-key
~~~

Không commit secret trong source; bảo vệ bằng secret platform, volume isolation, permission và RBAC. Nhưng nội dung file ở runtime có thể là plaintext.

**Phương án D — secret provider SDK/Vault integration:**

~~~text
Workload identity -> secret store -> SDK/integration -> consumer
~~~

Có thể hỗ trợ audit/lease/short-lived credential, đổi lại tăng độ phức tạp triển khai. Lựa chọn tùy hệ thống và threat model.

## 35. Không nên lấy secret tùy ý theo mỗi request

Một ứng dụng có secret manager SDK có thể viết:

~~~java
String token = secretProvider.getRequiredSecret(
    "warehouse/client/api-key"
);
~~~

Nếu gọi secret store trên **mọi HTTP request**, hệ thống có thể gặp:

- Tăng latency và chi phí request tới secret manager.
- Rate limit hoặc outage lan sang ứng dụng.
- Secret store trở thành dependency đồng bộ của mỗi request.
- Nhiều lần đọc làm tăng audit events không cần thiết.
- Khó quản lý TTL/renewal và race condition.

Nếu secret ít thay đổi, có thể lấy tại startup, cache có TTL hoặc dùng integration quản lý refresh phù hợp. Nhưng nếu secret là dynamic/short-lived, cache phải gắn với lease/expiration thực, không được giữ quá thời hạn.

**Thiết kế cache** luôn đi cùng:

- TTL tối đa.
- Refresh trước expiry.
- Retry/backoff và circuit breaker phù hợp.
- Không log dữ liệu trong cache.
- Hành vi khi refresh thất bại.
- Thu hồi và thay client đang dùng phiên bản cũ.

Không có một TTL chung an toàn cho mọi loại secret.

## 36. Fail-fast hay fallback khi secret manager không sẵn sàng?

Giả sử ứng dụng khởi động nhưng không lấy được `warehouse.client.api-key`.

Một fallback không nên làm:

~~~java
String apiKey = provider.getSecret("warehouse/api-key");

if (apiKey == null) {
    apiKey = "default-key";
}
~~~

Đối với dịch vụ cần xác thực thực sự, điều này có thể che lỗi cấp quyền và khiến ứng dụng chạy sai hoặc gửi yêu cầu với credential không hợp lệ.

Cần phân loại:

| Tình huống | Hướng phản ứng |
| --- | --- |
| Không có secret bắt buộc | Fail-fast hoặc đánh dấu unavailable theo hợp đồng |
| Workload không được phép đọc | Báo lỗi permission, không dùng secret mặc định |
| Secret manager tạm timeout | Retry có giới hạn, backoff và chính sách khởi động rõ |
| Secret hết hạn | Refresh/renew theo API, tránh tiếp tục dùng credential đã expired |
| Secret bị thu hồi | Ngừng dùng, cập nhật identity/credential hợp lệ |
| Tính năng tùy chọn bị tắt | Có thể không yêu cầu secret của tính năng đó |
| Test/local environment | Dùng fake credential, local provider hoặc stub được kiểm soát |

Không phải hệ thống nào cũng phải dừng cả ứng dụng khi một integration tùy chọn chưa có secret; nhưng quyết định degrade/disable cần được **thiết kế rõ** chứ không tự biến secret thiếu thành chuỗi giả.

## 37. Kiểm thử configuration binding mà không dùng secret thật

Ví dụ integration test:

~~~java
package example.warehouse;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(properties = {
    "warehouse.client.base-url=https://example.invalid",
    "warehouse.client.timeout=2s",
    "warehouse.client.api-key=fake-key-for-tests"
})
class WarehouseClientPropertiesTest {

    @Autowired
    WarehouseClientProperties properties;

    @Test
    void bindsFakeSecret() {
        assertThat(properties.apiKey())
            .isEqualTo("fake-key-for-tests");
    }
}
~~~

Giá trị `fake-key-for-tests` chỉ là fixture học tập, không được nhầm với token có quyền truy cập thật.

Test này kiểm tra Binder và bean registration. Nó **không kiểm tra secret manager** hoặc cách container mount file.

Với integration test cấp secret:

- Dùng một secret store test instance hoặc fake provider.
- Test identity được cấp quyền tối thiểu.
- Không dùng production token.
- Có test thiếu secret và secret không đọc được.
- Không đưa secret test nhạy cảm vào snapshots của CI.
- Kiểm tra application không log secret khi startup thất bại.

## 38. Kiểm thử configtree tại môi trường chạy

Một quy trình kiểm thử có chủ đích:

1. Chuẩn bị một thư mục tạm chỉ chứa dữ liệu giả.
2. Đặt tệp tên `warehouse.client.api-key` vào đó với nội dung `fake-secret-for-local-test`.
3. Cấu hình Spring Boot import `configtree:` tới đúng đường dẫn tạm.
4. Khởi động application/test context.
5. Assert properties bean nhận giá trị giả tương ứng.
6. Kiểm tra trường hợp tệp bị thiếu.
7. Xóa thư mục tạm sau test và không log nội dung.

Ví dụ cấu hình:

~~~yaml
spring:
  config:
    import: "configtree:/run/secrets/test-warehouse/"
~~~

Cần đảm bảo directory thực sự có trước khi Config Data được xử lý. Một test `@TempDir` chỉ tạo thư mục sau khi application context đã bootstrap có thể **quá muộn** nếu test không chuẩn bị property và file trước đúng lifecycle.

Điểm quan trọng là test cả hai tầng:

- File được mount/đặt đúng tên và được đọc.
- Validation/consumer sử dụng đúng property.

Không chỉ kiểm tra rằng file tồn tại rồi suy luận Binder chắc nhận nó.

## 39. Kiểm thử vòng đời rotation

Một test quan trọng khác không liên quan tới file YAML: giả lập secret provider trả hai phiên bản:

~~~text
Lần 1: credential-A
Lần 2: credential-B
Credential-A bị thu hồi
~~~

Điều ứng dụng phải chứng minh:

- Không tiếp tục sử dụng credential-A sau khi hạn của nó kết thúc.
- Refresh không làm nhiều thread dùng trạng thái cấu hình nửa cũ nửa mới.
- Connection pool/client có thể tạo kết nối với credential-B.
- Khi Vault hoặc secret manager tạm lỗi, ứng dụng có phản ứng được quy định.
- Không in credential-A/B vào log khi test thất bại.

Với database credential, test nên quan sát hành vi kết nối thực, không chỉ xác nhận một field `String password` đã đổi.

Không phải mọi hệ thống đều cần dynamic rotation trong process. Nếu chiến lược là restart/rollout sau khi đổi secret, test cần chứng minh pod mới đọc bản mới và pod cũ được loại bỏ đúng quy trình.

## 40. Private key và chứng chỉ: đừng trộn với API token

Một số secret là **private key** dùng cho TLS, ký số hoặc mTLS. Đây là dữ liệu có yêu cầu xử lý riêng:

- File format như PEM, PKCS#8, PKCS#12/JKS.
- Password bảo vệ keystore (nếu có).
- Certificate chain và trust anchors.
- Key usage và thời hạn chứng chỉ.
- Rotation và rollout.
- Phân quyền đọc file/keystore.
- Nếu dùng HSM/KMS để ký từ xa, có thể tránh đưa private key thô vào process.

Spring Boot có những tiện ích cấu hình TLS/SSL (bao gồm SSL bundles ở các phiên bản hỗ trợ), nhưng **quản lý TLS không đồng nghĩa Spring Boot tự mã hóa mọi application property**.

Ví dụ một server có TLS certificate không có nghĩa `spring.datasource.password` trong YAML đã được encrypted at rest.

Hãy tách:

1. Bảo vệ network traffic bằng TLS.
2. Bảo vệ private key và chứng chỉ của TLS.
3. Bảo vệ database/API credentials.
4. Bảo vệ khóa mã hóa dữ liệu ứng dụng.

Mỗi loại có lifecycle và policy riêng.

## 41. Tại sao không tự viết “decrypt property on access” tùy tiện?

Một thiết kế tự viết có thể muốn:

~~~java
String value = environment.getProperty("payment.api-key");
if (value.startsWith("ENC(")) {
    return decrypt(value, localKey);
}
~~~

Rủi ro:

- Không quản lý version và format ciphertext.
- Key có thể bị hard-code/copy cùng artifact.
- Không có authenticated encryption hoặc xử lý nonce đúng.
- Không kiểm tra integrity/ciphertext tampering.
- Khó audit ai dùng key.
- Có thể log plaintext khi lỗi.
- Decrypt lặp lại ở nhiều nơi, tạo nhiều bản sao secret trong memory.
- Gặp lỗi dependency/order nếu bean decrypt cần chính các properties đang được decrypt.

Nếu thực sự cần decrypt property, hãy dùng thư viện/SDK và extension đã được security review, chọn lifecycle đúng, cung cấp key bằng identity-based mechanism và test rotation/exception handling. Tránh biến một helper method vài dòng thành nền tảng bảo mật mà toàn ứng dụng phụ thuộc.

Không phải mọi giải pháp mã hóa property đều kém, nhưng **phải đánh giá toàn bộ key management**, không chỉ lời gọi `decrypt(...)`.

## 42. Mã hóa file trước khi commit: SOPS/KMS và vai trò deploy

Một số tổ chức có chính sách lưu **ciphertext** trong Git, ví dụ dùng công cụ secret encryption được quản trị như SOPS kết hợp KMS/age/GPG theo quy định nội bộ.

Luồng có thể là:

~~~text
File mã hóa trong Git
        |
        v
CI/CD hoặc secret controller được cấp quyền
        |
        v
Giải mã tại deployment bằng KMS/identity
        |
        v
Secret file/mount/runtime source
        |
        v
Spring Boot đọc qua Environment hoặc configtree
~~~

Spring Boot không tự hiểu mọi định dạng SOPS/ciphertext. **Thành phần deployment** chịu trách nhiệm giải mã đúng cách và cấp giá trị cho runtime.

Các điều kiện vận hành:

- Key không nằm trong repo cùng ciphertext.
- Identity CI/controller có quyền tối thiểu.
- Plaintext không bị ghi vào artifacts/logs.
- Decrypted files có scope và lifetime phù hợp.
- Rotate encryption key/secret theo chính sách.
- Kiểm soát truy cập Git và review thay đổi ciphertext.
- Có quy trình incident response nếu credential bị lộ.

Đừng hiểu rằng “ciphertext được commit” là đã hoàn tất bảo vệ; cần kiểm soát **người có quyền giải mã và nơi bản rõ xuất hiện**.

## 43. Cơ chế ưu tiên nguồn có thể tạo lỗi bảo mật âm thầm

Giả sử password được cấp từ secret mount:

~~~text
/run/secrets/db/spring.datasource.password
~~~

Nhưng ở application config lại có:

~~~yaml
spring:
  datasource:
    password: "dev-default"
~~~

Nếu Config Data import configtree và precedence được thiết lập đúng, file secret có thể thắng giá trị dev. Nhưng nếu deployment hoặc một nguồn ưu tiên cao khác ghi lại cùng key, ứng dụng có thể dùng credential không mong muốn.

Bên cạnh đó, một giá trị mặc định dev trong artifact có thể vô tình được dùng khi secret import optional bị thiếu.

Để giảm rủi ro:

- Không đặt password mặc định có quyền thật.
- Với production, fail khi secret mount không có.
- Giữ một nguồn chủ trì cho mỗi credential.
- Xác định policy override rõ ràng.
- Test source precedence trong cấu hình triển khai thực.
- Không log secret để so sánh; kiểm tra trạng thái kết nối và nguồn theo cách không lộ giá trị.

## 44. Bộ checklist bảo mật cho một Spring Boot service

Trước khi triển khai một service nhận secret:

1. Secret có được phân loại đúng và không xuất hiện trong source không?
2. Git history và artifacts có từng chứa secret thật không?
3. Nguồn authoritative là secret manager/Vault/KMS/platform nào?
4. Workload xác thực bằng identity gì?
5. Quyền đọc secret có đúng least privilege không?
6. Dev/staging/prod được tách policy và paths chưa?
7. Có encryption at rest theo yêu cầu và bảo vệ kênh truyền không?
8. Secret vào app bằng env, configtree hay SDK? Vì sao chọn cách đó?
9. Nếu dùng configtree, file permission/mount và path có đúng chưa?
10. Nếu dùng env, ai có quyền inspect process và deployment?
11. Nếu dùng `application.yml`, có chỉ chứa placeholders chứ không chứa bản rõ không?
12. Secret có bị ghi đè bởi nguồn config ưu tiên cao khác không?
13. Có validation để fail-fast khi secret bắt buộc thiếu không?
14. Không dùng secret giả ở production chứ?
15. Có tránh log values, bean `toString()` và HTTP headers không?
16. Actuator endpoints và diagnostics đã được hạn chế quyền chưa?
17. Heap dumps, backups, crash reports và traces có chính sách bảo vệ chưa?
18. Có strategy rotation/restart/refresh phù hợp với client/pool không?
19. Secret hết hạn hoặc bị thu hồi thì service phản ứng ra sao?
20. Có audit truy cập và quy trình thu hồi khi sự cố không?
21. CI/CD có cấp secret chỉ lúc cần, không bake vào image không?
22. Tests có dùng giá trị giả và kịch bản lỗi/rotation không?

Không nên xem checklist này là việc riêng của developer. Security, DevOps/SRE và người sở hữu dịch vụ phải phối hợp vì phần lớn nguồn secret và IAM nằm ngoài mã Spring Boot.

## 45. Bài tập 1: chuyển password hard-coded sang external source

**Ban đầu — cách không nên dùng:**

~~~yaml
spring:
  datasource:
    url: "jdbc:postgresql://db.example.invalid:5432/orders"
    username: "orders_app"
    password: "hard-coded-example-password"
~~~

Mục tiêu: cùng một JAR nhưng password không nằm trong file cấu hình commit.

Một giải pháp bằng placeholder:

~~~yaml
spring:
  datasource:
    url: "jdbc:postgresql://db.example.invalid:5432/orders"
    username: "orders_app"
    password: "${ORDERS_DB_PASSWORD}"
~~~

Deployment cấp `ORDERS_DB_PASSWORD` từ hệ thống được kiểm soát. Không đưa giá trị cụ thể vào lệnh ví dụ, CI logs hoặc hướng dẫn commit.

**Câu hỏi tự kiểm tra:**

- Password còn nằm trong repository không?
- Ai có quyền cấp và đọc ORDERS_DB_PASSWORD?
- Nếu password thiếu, startup có thất bại theo hợp đồng không?
- Có cách đổi password mà không build lại JAR không?
- Có cần restart/rollout khi password thay đổi không?
- Ai có thể xem env của tiến trình?
- Credential có bị log bởi thư viện kết nối không?

## 46. Bài tập 2: thay environment bằng configtree

Giả sử nền tảng cấp một file:

~~~text
/run/secrets/orders/spring.datasource.password
~~~

Trong `application.yml`:

~~~yaml
spring:
  config:
    import: "configtree:/run/secrets/orders/"
  datasource:
    url: "jdbc:postgresql://db.example.invalid:5432/orders"
    username: "orders_app"
~~~

Không khai báo password trong YAML; Spring Boot đọc property `spring.datasource.password` từ file mount.

**Yêu cầu thực hành:**

1. Dùng một secret giả trong môi trường test.
2. Tạo file với tên đúng key.
3. Khởi động Spring Boot với directory đã sẵn sàng.
4. Xác minh datasource/consumer nhận credential cần dùng bằng cách test khả năng kết nối tới một database test.
5. Tắt mount hoặc đổi tên file, xác minh behavior khi secret thiếu.
6. Giữ log không chứa secret.
7. Mô phỏng thay file và xác định có cần restart để bean/connection pool nhận bản mới.

Không nhầm việc ứng dụng đọc được file với bảo đảm file đã được mã hóa. Nguồn bảo vệ ở phía secret platform.

## 47. Bài tập 3: lập kế hoạch dùng Vault/KMS

Hãy thiết kế cho hệ thống gồm ba service:

~~~text
orders-service
billing-service
inventory-service
~~~

Yêu cầu:

- Mỗi service chỉ đọc secret của chính mình.
- Staging không đọc production.
- Không hard-code root token.
- Có audit lần đọc.
- Có phương án rotation.
- Billing credential cần được thu hồi nhanh khi nghi ngờ lộ.

Gợi ý mô hình phân quyền:

~~~text
identity/orders-prod    -> read /prod/orders/*
identity/billing-prod   -> read /prod/billing/*
identity/inventory-prod -> read /prod/inventory/*
identity/orders-staging -> read /staging/orders/*
~~~

Cần trả lời:

1. Danh tính workload được cấp ở đâu?
2. Kênh từ pod/VM tới Vault/secret manager được xác thực ra sao?
3. Bí mật được lưu ở backend nào, có mã hóa at rest không?
4. Có dynamic secret phù hợp với database không?
5. Secret được đưa vào Spring Boot qua mounted file, integration hay SDK?
6. Khi kho secret tạm unavailable, service có thể khởi động không?
7. Credential mới được đưa vào client/connection pool thế nào?
8. Bao lâu có thể thu hồi credential cũ?
9. Những log/traces nào phải tránh lưu giá trị?
10. Cách test rotation mà không dùng production secret?

Bài tập này nhấn mạnh rằng **quản lý secret là một bài toán kiến trúc và vận hành**, không chỉ một annotation Java.

## 48. Những sai lầm thường gặp và hướng sửa

**Sai lầm 1 — “Base64 là mã hóa.”**  
Không. Base64 là encoding. Dùng secret store và encryption at rest thực sự khi cần.

**Sai lầm 2 — “Spring Boot tự decrypt ENC(...).”**  
Không mặc định. Phải có integration/library và quản lý key tương ứng.

**Sai lầm 3 — “Có TLS thì application.yml đã an toàn.”**  
TLS bảo vệ truyền tải, không tự bảo vệ file config hoặc source repository.

**Sai lầm 4 — “Đặt key giải mã ngay cạnh ciphertext là đủ.”**  
Không. Cần tách quyền và nguồn quản lý decryption key.

**Sai lầm 5 — “Kubernetes Secret đã Base64 nên không ai đọc được.”**  
Không. Cần RBAC, giới hạn quyền trong cluster và cấu hình encryption at rest theo yêu cầu.

**Sai lầm 6 — “Mọi thứ trong /run/secrets đều encrypted.”**  
Không. File mount có thể là plaintext; protection nằm ở cơ chế cấp và permission.

**Sai lầm 7 — “Dùng configtree là tích hợp Vault.”**  
Không. Configtree đọc thư mục; một driver/agent/controller có thể lấy secret từ Vault trước.

**Sai lầm 8 — “Sửa file secret là mọi bean tự cập nhật.”**  
Không mặc định. Cần refresh/rebind hoặc restart có chủ đích.

**Sai lầm 9 — “Mask trong Actuator nghĩa là mọi log đã an toàn.”**  
Không. Các đường rò rỉ khác vẫn tồn tại.

**Sai lầm 10 — “Thêm @NotBlank đủ để bảo vệ password.”**  
`@NotBlank` chỉ validate presence/blank, không mã hóa hay quản lý quyền.

**Sai lầm 11 — “Secret manager luôn sẵn sàng nên không cần retry/timeout.”**  
Không. Phải thiết kế lỗi mạng, permission, expiry và dependency availability.

**Sai lầm 12 — “Mỗi request đọc Vault là an toàn nhất.”**  
Không hẳn. Cần cache/lease policy phù hợp và giới hạn tải.

**Sai lầm 13 — “Xóa secret khỏi file hiện tại là đủ.”**  
Không nếu secret đã xuất hiện trong Git history, artifact, log hoặc backup. Phải coi credential đã bị lộ và rotate/revoke phù hợp.

**Sai lầm 14 — “Có mã hóa at rest thì developer không thể thấy secret trong memory.”**  
Không. Tiến trình sử dụng secret thường có khả năng đọc nó; bảo vệ runtime và quyền debug vẫn cần thiết.

## 49. Tóm tắt đối chiếu công cụ và trách nhiệm

| Thành phần | Đóng góp chính | Không tự làm |
| --- | --- | --- |
| Spring Boot `Environment` | Truy xuất property từ nhiều nguồn | Không tự mã hóa mọi secret |
| `@ConfigurationProperties` | Bind typed config và hỗ trợ validation | Không làm secret store |
| Placeholder `${...}` | Tra giá trị từ nguồn hiện có | Không decrypt |
| `configtree:` | Đọc file thành property | Không tự bảo vệ nơi lưu/khóa |
| Kubernetes Secret | Phân phối secret tới workloads qua cluster | Base64 không đồng nghĩa encryption at rest |
| Secret manager/Vault | Lưu/cấp secret, policy, audit, có thể hỗ trợ rotation/lease | Không tự cập nhật mọi Java bean |
| KMS | Quản lý và dùng encryption keys theo quyền | Không tự là property binder |
| Spring Cloud Vault / integration | Kết nối secret store vào Spring ecosystem | Không phải tính năng core không cần dependency |
| SDK provider | Cho ứng dụng lấy secret chủ động | Cần xử lý auth/cache/refresh |
| TLS | Bảo vệ kênh truyền | Không mã hóa toàn bộ application.yml |
| Bean Validation | Phát hiện property thiếu/sai ràng buộc | Không ngăn log lộ giá trị |
| CI/CD security | Cấp secret và tách build/deploy | Không thay kiểm soát runtime |

## 50. Ghi nhớ

**Spring Boot thuần là một framework rất mạnh về externalized configuration, nhưng không phải một hệ thống quản lý bí mật hoàn chỉnh.** Nó đọc và bind giá trị từ nhiều nguồn; muốn có mã hóa at rest, chính sách giải mã, identity, audit, rotation hoặc dynamic credential, cần một lớp quản lý bí mật phù hợp bên ngoài hoặc một integration được triển khai có chủ đích.

Không nhầm **Base64**, **placeholder**, **Config Data import** hay **`configtree:`** với cơ chế mã hóa. `ENC(...)` không phải cú pháp được Spring Boot tự giải mã trong mọi ứng dụng. Một file được mount vào container có thể là bản rõ; quyền truy cập và nguồn cấp phải được bảo vệ.

Mô hình thực hành tốt là **giữ secret ra khỏi source code và artifact**, dùng workload identity/least privilege để lấy giá trị từ secret manager hoặc nền tảng triển khai, kiểm soát nguồn nào được phép ghi đè, kiểm thử thiếu secret và rotation, hạn chế log/Actuator/debug exposure, và có quy trình thu hồi credential khi bị lộ.

**Câu kết luận:** bảo vệ bí mật không kết thúc ở việc giá trị được mã hóa trên đĩa. Nó phải được bảo vệ suốt **vòng đời cấp — lưu — truyền — sử dụng — thay — thu hồi**, với trách nhiệm rõ ràng giữa Spring Boot, hạ tầng và secret manager.
