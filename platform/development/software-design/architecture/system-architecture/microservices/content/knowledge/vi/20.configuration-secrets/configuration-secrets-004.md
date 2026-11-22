# Giá trị mặc định, xác thực và phát hiện cấu hình sai

> **Chủ đề:** Software Design / Software Architecture / System Architecture / Microservices  
> **Nhóm kiến thức:** Cấu hình và bí mật (Configuration & Secrets)  
> **Mục tiêu:** Thiết kế cấu hình có mặc định an toàn, phát hiện giá trị thiếu hoặc sai trước khi gây sự cố, kiểm soát thay đổi cấu hình qua nhiều môi trường và bảo đảm thông tin bí mật không bị lộ trong quá trình xác thực, ghi log hay vận hành.

## 1. Vì sao cấu hình là một phần của thiết kế hệ thống?

Cùng một bản build có thể hoạt động rất khác nhau tùy vào cấu hình. Một service xử lý đơn hàng có thể đúng ở môi trường kiểm thử nhưng gây lỗi nghiêm trọng ở production chỉ vì:

- Timeout gọi Payment API được đặt thành 30 giây, lâu hơn deadline của request đặt hàng.
- Retry không giới hạn khiến hàng nghìn request cùng thử lại khi Payment chậm.
- Feature flag vô tình tắt một kiểm tra phân quyền.
- Endpoint trỏ nhầm sang môi trường staging hoặc vùng dữ liệu khác.
- Số connection tối đa nhân với số replica vượt giới hạn của database.
- Khóa ký token, chứng chỉ TLS hoặc secret cần thiết không được cấp hoặc đã hết hiệu lực.
- Hai replica dùng hai phiên bản cấu hình khác nhau trong khi cùng xử lý một loại request.

Những lỗi này có thể xuất hiện mà **mã chương trình không đổi**. Vì thế cấu hình phải được xem như một giao diện đầu vào của ứng dụng, có hợp đồng, kiểu dữ liệu, giới hạn, vòng đời và người chịu trách nhiệm.

Một luồng cấu hình lành mạnh:

~~~text
Nguồn cấu hình được phép
    |
    v
Đọc + xác định thứ tự ưu tiên
    |
    v
Bind thành mô hình có kiểu
    |
    v
Kiểm tra giá trị bắt buộc và cú pháp
    |
    v
Kiểm tra quan hệ giữa các giá trị
    |
    v
Kiểm tra điều kiện phụ thuộc môi trường
    |
    +--- Không hợp lệ ---> Báo lỗi rõ, không nhận traffic
    |
    v
Khởi tạo tài nguyên / client
    |
    v
Readiness đạt điều kiện thực sự
    |
    v
Quan sát phiên bản cấu hình và thay đổi vận hành
~~~

**Mục tiêu:** phát hiện cấu hình sai ở ranh giới sớm nhất có thể; khi không thể phát hiện trước, hạn chế phạm vi ảnh hưởng, cho phép rollback và giữ tín hiệu điều tra rõ ràng.

## 2. Từ vựng và ranh giới trách nhiệm

### 2.1. Configuration, secret và runtime state

- **Configuration:** tham số điều chỉnh hành vi có chủ đích, ví dụ endpoint API, timeout, giới hạn pool, feature flag, tên queue, chính sách retry.
- **Secret:** thông tin mà ai sở hữu nó có thể được cấp quyền hoặc truy cập dữ liệu, ví dụ password, API key, private key, client secret, token dài hạn.
- **Runtime state:** trạng thái thay đổi khi ứng dụng hoạt động, ví dụ số request đang xử lý, queue depth, session hiện hành. Không nên đặt runtime state biến động cao vào cùng hợp đồng lưu trữ với cấu hình tĩnh.
- **Policy:** quy tắc nghiệp vụ hoặc bảo mật có thể được biểu diễn bằng cấu hình, nhưng cần người sở hữu, kiểm soát thay đổi và kiểm chứng rõ hơn các tham số tiện ích.

Secret có thể được tham chiếu bởi cấu hình, chẳng hạn secret reference, nhưng giá trị secret không nên nằm trong repository, file example, artifact build hay log chỉ vì ứng dụng cần cấu hình nó.

### 2.2. Default, required, override và effective value

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| Default | Giá trị dùng khi nguồn cấu hình không cung cấp một thuộc tính | Retry attempts = 1 |
| Required | Giá trị phải được cung cấp hợp lệ ở thời điểm cần thiết | Payment endpoint của production |
| Override | Giá trị từ một nguồn ưu tiên cao hơn thay thế giá trị nguồn khác | Environment variable thay cấu hình package |
| Effective configuration | Kết quả cuối cùng sau khi áp dụng các lớp và quy tắc | Timeout thực sự là 800 ms |
| Configuration drift | Các instance/môi trường dự kiến giống nhau nhưng dùng cấu hình khác nhau | Hai pod có retry budget khác nhau |
| Misconfiguration | Cấu hình thiếu, sai, xung đột, không an toàn hoặc không còn phù hợp | Public API cho phép CORS quá rộng theo nhầm lẫn |

“Có giá trị” và “hợp lệ” không giống nhau. Một chuỗi endpoint không rỗng có thể là URL sai scheme, sai host hoặc trỏ nhầm môi trường. Một số nguyên dương vẫn có thể làm quá tải DB nếu vượt ngân sách tài nguyên của hệ thống.

## 3. Thiết kế giá trị mặc định theo mức độ rủi ro

Giá trị mặc định giúp hệ thống dễ chạy, nhưng mặc định sai có thể che giấu thiếu cấu hình và tạo sự cố hàng loạt. Không phải thuộc tính nào cũng nên có default.

### 3.1. Nhóm có thể dùng mặc định bảo thủ

Những giá trị có thể áp dụng default khi đội phát triển đã xác định yêu cầu, thước đo và điều kiện:

| Thuộc tính | Ví dụ default minh họa | Lý do |
|---|---|---|
| Retry max attempts | 1 lần thử, tức không retry | Tránh nhân tải khi chưa có retry policy |
| Connect timeout | Thời hạn ngắn, dương, phù hợp mạng nội bộ | Không giữ connection vô hạn |
| Queue capacity | Dung lượng hữu hạn | Giữ áp lực bộ nhớ có giới hạn |
| Connection pool size | Giới hạn thận trọng | Tránh mỗi instance chiếm quá nhiều connection |
| Logging redaction | Bật | Giảm rủi ro lộ credential/secret |
| Feature thử nghiệm không thiết yếu | Tắt cho đến khi bật có chủ đích | Hạn chế phát hành ngoài ý muốn |
| Metrics cơ bản | Bật theo chính sách vận hành | Có tín hiệu quan sát lỗi |
| Batch size | Hữu hạn và phù hợp tải | Tránh đột biến bộ nhớ, CPU |

Các ví dụ không phải cấu hình production có thể sao chép nguyên xi. Timeout phải dựa vào SLO, latency thực tế và deadline đầu cuối; pool phải dựa vào ngân sách toàn cụm. Default phải có lý do và phép đo, không chỉ vì thư viện cung cấp sẵn.

### 3.2. Nhóm nên yêu cầu cấu hình tường minh

Đây là các giá trị nếu đoán sai có thể làm hỏng dữ liệu hoặc ranh giới bảo mật:

- Endpoint hệ thống thanh toán, database chính, hệ thống định danh hoặc kho dữ liệu production.
- Thông tin nhận dạng môi trường và phạm vi dữ liệu khi lỗi có thể trộn môi trường.
- Mã định danh khóa mã hóa/ký, secret reference và quyền truy cập tài nguyên.
- Tenant ID, region, resource namespace, tên bucket dùng cho dữ liệu nghiệp vụ nhạy cảm.
- Quyết định cho phép dùng chế độ không xác thực, bỏ kiểm tra chứng chỉ hoặc chấp nhận HTTP thuần trong ngữ cảnh không an toàn.
- Cờ kích hoạt hành vi phá hủy dữ liệu, migrate nhạy cảm hoặc chạy backfill trên production.

Khi một giá trị cần được chọn có chủ đích, **thiếu giá trị phải là lỗi rõ ràng**, không tự suy đoán từ hostname, thứ tự profile hay giá trị của môi trường dev.

### 3.3. Default an toàn khác default tiện lợi

Ví dụ nguy hiểm:

~~~yaml
payment:
  endpoint: https://sandbox-payment.example.invalid
  enabled: true
~~~

Nếu file này được đóng gói và production quên cung cấp override, ứng dụng có thể gửi giao dịch thật vào sandbox hoặc ngược lại. Giá trị trông hợp lệ về cú pháp nhưng sai về môi trường.

Phương án thiết kế:

- Endpoint Payment bắt buộc được cấp bởi nguồn cấu hình production đã xác định.
- Xác minh scheme, host/audience, môi trường và quyền truy cập trước khi nhận traffic.
- Nếu dependency bắt buộc thiếu cấu hình, fail startup hoặc giữ readiness ở trạng thái không sẵn sàng tùy mô hình vận hành.
- Nếu dependency tùy chọn không được cấu hình, có thể tắt rõ chức năng đó và phát một trạng thái vận hành dễ quan sát, miễn không làm sai nghiệp vụ.

Một tính năng tùy chọn thường có default OFF; **một kiểm soát bảo mật không được mặc định OFF chỉ vì nó cũng được biểu diễn bằng feature flag**. Quyết định phải theo yêu cầu an toàn của chức năng.

### 3.4. Phân biệt absent, null, blank, zero và false

Những trường hợp này cần được xử lý theo hợp đồng, không đánh đồng:

| Đầu vào | Diễn giải có thể có | Rủi ro |
|---|---|---|
| Không có thuộc tính | Dùng default hoặc báo thiếu required | Default có thể che thiếu cấu hình |
| null | Chưa cấp giá trị hoặc vô hiệu hóa có chủ đích | Binder/serializer xử lý khác nhau |
| Chuỗi rỗng | Đã cấp nhưng không có nội dung | Có thể vượt kiểm tra not-null |
| Chuỗi toàn khoảng trắng | Không chứa định danh hữu dụng | Có thể vượt kiểm tra not-empty |
| 0 | Giá trị số hợp lệ hoặc vô hiệu hóa | Timeout 0 có thể thành chờ vô hạn ở thư viện khác |
| false | Tắt có chủ đích hoặc do kiểu nguyên thủy mặc định | Có thể vô tình tắt kiểm tra quan trọng |
| Danh sách rỗng | Không có đối tượng nào | Với allowlist/role/host có thể là lỗi nghiêm trọng |

Với thuộc tính bắt buộc, tránh dùng primitive khi cần phân biệt “chưa được cấp” với zero hoặc false; ví dụ dùng Integer/Boolean có kiểm tra NotNull hoặc cơ chế khai báo required tương đương.

## 4. Xác thực cấu hình cần nhiều lớp

Chỉ kiểm tra parse YAML/JSON thành công là chưa đủ. Hệ thống nên phân biệt ít nhất sáu lớp kiểm tra.

### 4.1. Cú pháp (syntax)

Có đọc được YAML, JSON, env var, URL hay file cấu hình không? Các lỗi điển hình: ký tự sai, thụt lề YAML, khóa trùng, chuỗi escape không hợp lệ, parse duration thất bại, giá trị enum không nhận diện.

Ví dụ:

~~~yaml
checkout:
  retry:
    max-attempts: "nhieu"   # Sai kiểu số nguyên
~~~

Lỗi cần chỉ ra property path và kiểu mong đợi, không cần in ra giá trị nếu nó có thể chứa secret.

### 4.2. Kiểu dữ liệu và bắt buộc (shape, type, required)

Một contract nên mô tả:

- Tên chuẩn của property và kiểu dữ liệu.
- Required hay optional; default nếu có.
- Đơn vị: ms, s, MiB, số phần tử, phần trăm.
- Có được phép null/blank/empty hay không.
- Tập giá trị enum/định dạng URI, hostname hoặc tên tài nguyên.
- Owner, môi trường áp dụng và mức nhạy cảm.

Ví dụ: checkout.payment.timeout phải là Duration, bắt buộc và dương; checkout.retry.max-attempts là Integer từ 1 đến 3; checkout.payment.endpoint phải là URI HTTPS phù hợp.

### 4.3. Khoảng hợp lệ (range)

Một timeout âm hoặc bằng 0 có thể không có ý nghĩa đối với chính sách hiện tại. Pool size = 1 có thể quá nhỏ, pool size = 10.000 có thể làm DB sập. Cần kiểm tra min/max, độ dài chuỗi, giới hạn số phần tử, độ lớn buffer, phần trăm trong khoảng 0–100 và tính hữu hạn của số thực.

Không dùng giới hạn dựa trên suy đoán. Ví dụ tối đa 50 connection mỗi pod phải được xét với số replica tối đa, connection dự phòng và quota database.

### 4.4. Quan hệ giữa các trường (cross-field invariants)

Đây là nơi nhiều lỗi cấu hình nguy hiểm bị bỏ sót:

- connectTimeout phải nhỏ hơn hoặc bằng requestTimeout nếu flow phụ thuộc như vậy.
- retry delay và số lần thử phải không vượt deadline nghiệp vụ.
- minPoolSize phải nhỏ hơn hoặc bằng maxPoolSize.
- Khi bật TLS/mTLS phải có trust material hoặc credential reference phù hợp.
- Khi bật tính năng liên quan phải khai báo đầy đủ endpoint, scope và secret reference.
- Queue max in-flight và batch size phải phù hợp worker count.
- Port/routing/namespace phải không xung đột trong deployment.

Ví dụ không thể kiểm chứng chỉ từng trường riêng lẻ:

~~~yaml
orders:
  deadline: 700ms
payment:
  timeout: 2s
retry:
  max-attempts: 3
~~~

Cả ba giá trị đều có vẻ hợp lệ riêng lẻ, nhưng yêu cầu thanh toán có thể chờ quá deadline 700 ms, trong khi retry càng kéo dài. Cần kiểm tra **ngân sách của toàn luồng**.

### 4.5. Tương thích môi trường và hạ tầng

Cấu hình có thể hợp lệ về mặt ứng dụng nhưng sai đối với môi trường hiện tại:

- Production endpoint chứa hostname staging.
- Bucket hoặc database nằm sai region theo chính sách dữ liệu.
- OAuth audience khác audience được API sử dụng.
- Certificate không khớp host hoặc sắp hết hiệu lực.
- Secret reference tồn tại nhưng service account không được quyền đọc.
- Kafka topic chưa có, sai số partition hoặc retention không đáp ứng nghiệp vụ.
- Replica count × pool size vượt DB connection budget.

Những kiểm tra cần gọi dịch vụ bên ngoài phải có timeout, cách xử lý outage và chính sách riêng: không biến một sự cố tạm của control plane thành hàng loạt restart không cần thiết. Phân biệt **cấu hình chắc chắn sai** với **chưa xác minh được do hạ tầng tạm lỗi**.

### 4.6. Tương thích với phiên bản ứng dụng (schema/version)

Khi service cập nhật, khóa cấu hình có thể bị đổi tên hoặc đổi nghĩa. Một release mới dùng retry.max-attempts nhưng deploy cũ vẫn đặt retry.attempts. Nếu binder im lặng bỏ qua khóa lạ và dùng default, production có thể đổi hành vi mà không ai biết.

Có thể dùng schema version, kiểm tra unknown keys, migration có thời gian chuyển đổi và CI test config theo từng môi trường. Khi đổi tên property, tài liệu cần chỉ rõ:

- Tên cũ và tên mới.
- Có chấp nhận đồng thời hay không; ưu tiên cái nào.
- Thời điểm ngừng hỗ trợ và cơ chế báo deprecation.
- Hành vi khi cả hai cùng xuất hiện.

Không để hai tên cùng điều khiển một hành vi mà thứ tự ưu tiên không được xác định.

## 5. Giá trị hiệu lực và thứ tự ưu tiên nguồn cấu hình

Ứng dụng phân tán có thể đọc cấu hình từ code defaults, file đóng gói, file theo môi trường, environment variables, command-line flags, Kubernetes ConfigMap, secret manager hoặc config service.

~~~text
Application defaults
       |
       v
Cấu hình đóng gói và cấu hình môi trường
       |
       v
Nguồn external/override được phép
       |
       v
Resolve placeholder, bind và validate
       |
       v
Effective configuration của một instance
~~~

Sơ đồ thể hiện ý tưởng; **thứ tự ưu tiên thực tế phải lấy từ framework và cấu hình deployment được chọn**. Trong Spring Boot, ví dụ, nhiều property source có thứ tự ưu tiên cụ thể; không nên tự đoán rằng file YAML luôn thắng env var hoặc ngược lại trong mọi ngữ cảnh.

### 5.1. Source of truth và ownership

Mỗi thuộc tính quan trọng nên có một owner và một nguồn gốc được quyết định trước. Ví dụ:

| Thuộc tính | Owner hợp lý | Nguồn chính sách |
|---|---|---|
| Payment endpoint và credential reference | Team Payment / Platform | Deployment config + secret store |
| Timeout theo SLO đặt hàng | Team Checkout | Config được version cùng ứng dụng/release |
| Feature flag rollout | Product/Operations với kiểm soát kỹ thuật | Feature management service |
| DB pool size | Platform + owner DB | Capacity plan và deployment |
| TLS trust policy | Security/Platform | Policy và hạ tầng certificate |
| Queue topic/consumer concurrency | Team sở hữu workflow | Config và vận hành messaging |

Tách quyền đọc và quyền sửa; các thay đổi rủi ro cao cần review, audit và khả năng rollback. Một property có thể bị override ở nhiều nơi, nhưng nếu không ai biết giá trị **cuối cùng**, vận hành gần như không thể tái hiện sự cố.

### 5.2. Tránh “magic override”

Ví dụ ai đó đặt PAYMENT_TIMEOUT=5000 trong deployment và không biết thư viện hiểu đơn vị là millisecond hay second. Người khác sửa timeout trong file nhưng không có hiệu lực vì env var ưu tiên hơn. Cả hai đều tưởng đã thay đổi production đúng cách.

Cách giảm rủi ro:

- Dùng kiểu Duration với đơn vị rõ ràng như 500ms, 2s thay vì số trần khi có thể.
- Cho biết danh sách property sources được phép và thứ tự ưu tiên.
- Có đường kiểm tra cấu hình hiệu lực ở startup và trong incident, nhưng **redact secret**.
- Bắt lỗi tên property không được nhận diện ở những namespace quan trọng.
- Đưa config revision/commit ID vào release metadata.

Không hiển thị toàn bộ environment variables ra trang quản trị để debug; nhiều biến môi trường chứa credential và thông tin hạ tầng nhạy cảm.

## 6. Ví dụ Java / Spring Boot: cấu hình có kiểu và fail fast

Giả sử Checkout cần gọi Payment và có policy retry. Ta muốn:

- Endpoint phải được cung cấp, dùng HTTPS.
- Secret reference phải được cung cấp, nhưng không ghi giá trị secret trong file.
- Payment timeout nằm trong khoảng có ý nghĩa của hệ thống.
- Số lần thử nằm trong giới hạn.
- Các giá trị sai khiến ứng dụng không khởi tạo client Payment và không nhận traffic.

### 6.1. Ví dụ cấu hình nguồn

~~~yaml
checkout:
  payment:
    endpoint: https://payments.example.invalid
    credential-ref: secrets/prod/checkout/payment-client
    timeout: 800ms
  retry:
    max-attempts: 2
    initial-backoff: 100ms
~~~

Các giá trị trên chỉ minh họa shape và đơn vị, không phải endpoint/secret thực. Trong production, endpoint và secret reference phải lấy từ nguồn môi trường được quản trị, đồng thời được kiểm chứng để tránh dùng nhầm địa chỉ hoặc quyền.

### 6.2. Bind vào mô hình bất biến, có Bean Validation

Ví dụ theo kiểu Spring Boot 3 và Jakarta Validation:

~~~java
import java.net.URI;
import java.time.Duration;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(
    prefix = "checkout",
    ignoreUnknownFields = false
)
public record CheckoutProperties(
        @Valid @NotNull Payment payment,
        @Valid @NotNull Retry retry
) {
    public record Payment(
            @NotNull URI endpoint,
            @NotBlank String credentialRef,
            @NotNull Duration timeout
    ) {}

    public record Retry(
            @NotNull @Min(1) @Max(3) Integer maxAttempts,
            @NotNull Duration initialBackoff
    ) {}
}
~~~

Điểm cần hiểu:

- Record cung cấp mô hình có kiểu và bất biến sau khi bind.
- NotNull bắt các trường không có giá trị; NotBlank bắt chuỗi rỗng và toàn khoảng trắng; Min/Max giới hạn số lần thử.
- **Integer** có thể phân biệt missing với giá trị 0. Dùng int nguyên thủy có thể che mất trạng thái missing.
- Valid yêu cầu xác thực lồng nhau; nếu bỏ qua, một đối tượng con có thể không được kiểm tra đầy đủ.
- ignoreUnknownFields=false giúp đặt yêu cầu chặt cho các khóa thuộc phạm vi binding; vẫn phải kiểm thử quy tắc tên khóa, các profile và các nguồn thực tế của ứng dụng.
- Spring cần hỗ trợ Jakarta Bean Validation trong classpath, ví dụ dependency validation thích hợp; không chỉ thêm annotation rồi giả định validation đang chạy.

### 6.3. Kiểm tra quy tắc liên trường và ranh giới bảo mật

Bean Validation xử lý required/range. Một kiểm tra khởi tạo bổ sung xử lý các quy tắc đặc thù:

~~~java
import java.time.Duration;

import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(CheckoutProperties.class)
public class CheckoutConfiguration {

    @Bean
    CheckoutConfigGuard checkoutConfigGuard(CheckoutProperties p) {
        return new CheckoutConfigGuard(p);
    }

    static final class CheckoutConfigGuard {
        CheckoutConfigGuard(CheckoutProperties p) {
            CheckoutProperties.Payment payment = p.payment();
            CheckoutProperties.Retry retry = p.retry();

            if (!"https".equalsIgnoreCase(
                    payment.endpoint().getScheme())) {
                throw new IllegalStateException(
                    "checkout.payment.endpoint must use HTTPS"
                );
            }

            Duration timeout = payment.timeout();
            if (timeout.isNegative() || timeout.isZero()
                    || timeout.compareTo(Duration.ofSeconds(2)) > 0) {
                throw new IllegalStateException(
                    "checkout.payment.timeout out of allowed range"
                );
            }

            if (retry.initialBackoff().isNegative()
                    || retry.initialBackoff().isZero()) {
                throw new IllegalStateException(
                    "checkout.retry.initial-backoff must be positive"
                );
            }

            // Đặt kiểm tra deadline toàn luồng ở nơi biết
            // đầy đủ ngân sách của request và các dependency.
        }
    }
}
~~~

Khi một singleton bean trong quá trình khởi tạo gặp lỗi, application context thường thất bại và tiến trình không thể phục vụ theo cấu hình sai. Với kiến trúc khởi tạo đặc biệt hoặc bean lazy, phải bảo đảm guard thực sự chạy trước readiness và trước khi xử lý request. Các thông báo lỗi ở trên cố ý ghi **tên thuộc tính và loại lỗi**, không ghi secret.

Mẫu guard chỉ là minh họa. Hệ thống thực còn có thể phải kiểm tra host allowlist, TLS trust, credential reference, timeout tổng, pool budget, retry budget và môi trường đích. Không nên xác minh bằng cách thực hiện giao dịch thanh toán thật ở startup.

### 6.4. Không để framework default âm thầm điều khiển chính sách

Một số thư viện có default riêng: retry vô hạn, connection pool lớn, timeout không giới hạn hoặc tự theo redirect. Ngay cả khi file cấu hình ứng dụng không có thuộc tính, thư viện vẫn có thể khởi động.

Với thuộc tính ảnh hưởng trực tiếp đến SLO, dữ liệu và bảo mật, **đặt giá trị tường minh trong cấu hình đã quản trị hoặc xác thực default thư viện có phù hợp hay không**. Khi nâng phiên bản thư viện, phải kiểm tra default có đổi không.

### 6.5. Phân biệt fail fast và fail gracefully

- Nếu cấu hình làm sai hợp đồng cốt lõi: fail fast, không quảng bá readiness, không “chạy tạm” bằng giá trị đoán.
- Nếu tích hợp phụ là tùy chọn: cho phép khởi động với tính năng đó disabled theo hợp đồng rõ ràng; ghi trạng thái degraded.
- Nếu dependency tạm lỗi lúc khởi tạo nhưng cấu hình vẫn đúng: tùy mô hình, có thể giữ readiness false rồi retry trong ngân sách, hoặc khởi động và mở circuit breaker. Không nhầm **dịch vụ tạm không tới được** với **cấu hình định danh sai chắc chắn**.

## 7. Phát hiện sai cấu hình trong CI và trước triển khai

Tốt nhất là lỗi được phát hiện trước khi có request thật.

### 7.1. Kiểm tra schema trong pull request

Một pipeline có thể dùng các bước:

1. Parse toàn bộ cấu hình theo schema/typed model.
2. Kiểm tra trùng khóa, khóa lạ, tên deprecated và chênh lệch giữa profile.
3. Kiểm tra required/range/cross-field invariants.
4. Tìm secret bị commit nhầm bằng secret scanning và quy tắc kiểm soát nội dung.
5. Kiểm tra cấu hình triển khai khớp phiên bản ứng dụng dự kiến.
6. So sánh các giới hạn với ngân sách tài nguyên: pool, queue, retries, timeout, replica count.
7. Xuất báo cáo chỉ chứa tên thuộc tính, trạng thái hợp lệ và giá trị **không nhạy cảm** nếu được phép.

Việc schema valid không chứng minh endpoint đang sẵn sàng hay secret có quyền. Những điều đó thuộc lớp kiểm chứng môi trường.

### 7.2. Kiểm tra môi trường trước rollout

Ví dụ môi trường production có những điều kiện:

~~~text
release version: 2.8.0
target environment: production
config revision: cfg-2026-11-12-07

[OK] checkout.payment.endpoint: configured, scheme HTTPS
[OK] checkout.payment.credential-ref: reference present
[OK] checkout.payment.timeout: inside policy range
[OK] checkout.retry.max-attempts: inside policy range
[OK] issuer / audience: compatible with service identity
[OK] DB connection budget: under approved capacity
[OK] required secret references: accessible by workload identity
~~~

Báo cáo chỉ chứa metadata và kết quả kiểm tra, không in secret. Một bước kiểm chứng secret reference có thể xác định reference tồn tại và có quyền đọc mà không phơi bày giá trị bí mật. Cần phân biệt kiểm tra an toàn với việc tự động thực hiện hành động thay đổi dữ liệu.

### 7.3. Thử nghiệm config-only change

Không phải chỉ thay code mới cần test. Thay timeout, retry, feature flag hay pool size cũng có thể làm thay đổi hành vi sản phẩm. Với thay đổi cấu hình có rủi ro, áp dụng cùng nguyên tắc release: review, test, canary, metric, quyết định rollback.

Nếu cấu hình thay đổi nhưng version ứng dụng giữ nguyên, hệ thống quan sát cần vẫn nhìn thấy **config revision** để giải thích khi nào hành vi bắt đầu khác.

## 8. Phát hiện sai cấu hình lúc khởi động

Một tiến trình khởi động có thể ở các trạng thái khác nhau:

~~~text
Process started
    |
    v
Read / bind configuration
    |
    +-- invalid --> Startup failed: CONFIG_INVALID
    |
    v
Validate security & invariant
    |
    +-- invalid --> Startup failed: CONFIG_INVALID
    |
    v
Initialize dependencies
    |
    +-- temporarily unavailable --> Waiting / not ready
    |
    v
Ready to serve requests
~~~

**Liveness** trả lời “process còn hoạt động không?”, **readiness** trả lời “instance đã đủ điều kiện nhận traffic chưa?”. Không nên báo readiness thành công khi service chưa có key xác minh token hoặc chưa được cấu hình endpoint bắt buộc.

Một số ví dụ kết quả mong đợi:

| Tình huống | Phát hiện | Hành vi dự kiến |
|---|---|---|
| Missing required Payment endpoint | Bind/validation | Fail startup |
| Timeout = chuỗi không parse được | Type conversion | Fail startup |
| Timeout = 0 | Range/invariant validation | Fail startup |
| Endpoint dùng HTTP khi policy yêu cầu HTTPS | Security validation | Fail startup |
| Retry vượt giới hạn | Range/cross-field validation | Fail startup |
| Secret reference không tồn tại | Environment validation | Không nhận traffic; báo lỗi an toàn |
| Identity service tạm thời không phản hồi | Dependency health | Readiness phụ thuộc chính sách; retry có giới hạn |
| Optional recommendations chưa cấu hình | Optional-feature policy | Chạy core service, disabled/degraded có giám sát |

Lỗi startup phải nói **thuộc tính nào sai và vi phạm quy tắc gì**. Không bao giờ ghép nguyên văn password/API key/token vào exception; framework có thể đưa exception lên log, alert, CI và công cụ hỗ trợ.

### 8.1. Tránh vòng lặp restart vì lỗi vĩnh viễn

Nếu config sai cố định, auto-restart liên tục không chữa được. Restart có thể làm đầy log, tăng tải secret/config service và che root cause. Hệ thống cần biểu diễn rõ nguyên nhân CONFIG_INVALID hoặc trạng thái tương đương, gắn với config revision và route sự cố đến owner thích hợp.

Nếu lỗi là dịch vụ ngoài tạm thời, chiến lược retry phải có backoff, jitter và giới hạn. Tránh để hàng trăm pod cùng retry đồng bộ vào một dependency đang yếu.

## 9. Cấu hình động và kiểm tra thay đổi khi runtime

Một số hệ thống cho phép thay đổi feature flag, rate limit, routing hoặc policy khi ứng dụng đang chạy. Điều này thêm một chiều rủi ro: giá trị đúng lúc startup không chắc còn đúng sau 30 phút.

### 9.1. Các lựa chọn cập nhật

| Cơ chế | Ưu điểm | Rủi ro hoặc chi phí |
|---|---|---|
| Chỉ đọc lúc startup | Dễ tái hiện, hợp đồng ổn định | Phải redeploy/restart để đổi |
| Hot reload từng property | Phản ứng nhanh | Trạng thái giữa các trường có thể không nhất quán |
| Hot reload theo snapshot version | Có thể áp dụng một bộ thuộc tính đồng bộ | Cần validation, publish atomic và rollback |
| Remote feature flag | Rollout/kill switch nhanh | Phụ thuộc config service/cache và tính nhất quán |
| Secret rotation có điều phối | Đổi credential không phải build lại | Cần xử lý overlap, connection refresh và quyền |

Không có giải pháp cập nhật phù hợp mọi property. Ví dụ thay limit có thể cập nhật động tương đối đơn giản; thay trust root, encryption key hay endpoint DB cần quy trình chuyển đổi phức tạp hơn.

### 9.2. Validate trước khi áp dụng, publish đồng bộ

Giả sử endpoint mới chỉ hợp lệ nếu đi kèm credential reference mới. Nếu cập nhật hai biến độc lập, có thể xuất hiện thời điểm endpoint mới dùng credential cũ và gây lỗi.

Luồng an toàn hơn:

~~~text
Config revision mới
     |
     v
Đọc toàn bộ candidate snapshot
     |
     v
Bind + validate cú pháp, range, cross-field và policy
     |
     +-- invalid --> Reject revision, giữ snapshot hợp lệ trước
     |
     v
Chuẩn bị tài nguyên mới nếu cần
     |
     v
Atomic publish snapshot mới
     |
     v
Theo dõi error rate / latency / auth failures
     |
     +-- vượt guardrail --> Rollback có kiểm soát
~~~

Giữ snapshot cũ chỉ hợp lý khi nó **vẫn còn an toàn và hợp lệ**. Nếu secret bị thu hồi, khóa bị lộ hoặc chính sách bảo mật yêu cầu chặn ngay, không được tiếp tục dùng snapshot cũ chỉ để giữ availability. Cần quy tắc riêng cho loại cấu hình nhạy cảm.

### 9.3. Consistency giữa các replica

Với rollout từng phần, có thể có nhiều revision đồng thời. Điều này cần được thiết kế, không nhất thiết là lỗi. Tuy nhiên, nếu cùng một giao dịch đi qua nhiều service có chính sách không tương thích, có thể xảy ra lỗi ngẫu nhiên.

Cân nhắc config version trong request context ở các workflow nhạy cảm, feature flag assignment ổn định theo user/tenant và cơ chế compatibility giữa các phiên bản. Với auth policy, encryption key rotation hoặc format event, phải hỗ trợ giai đoạn chuyển tiếp được xác định rõ.

## 10. Secret và validation: kiểm tra đủ nhưng không làm lộ

Secret không nên được coi chỉ là string property thông thường. Cần phân biệt hai mức:

1. **Secret reference:** định danh bản ghi trong secret manager, ví dụ tên path/key hoặc định danh phiên bản.
2. **Secret material:** nội dung nhạy cảm thực tế, ví dụ private key hoặc API secret.

Đối với cấu hình, thường giữ reference và quyền truy cập; thành phần chịu trách nhiệm kết nối secret manager lấy material tại thời điểm phù hợp.

### 10.1. Những kiểm tra có thể làm an toàn

- Reference được cung cấp và đúng namespace/môi trường.
- Workload identity được phép đọc secret cần thiết.
- Secret material tồn tại, đúng định dạng hoặc độ dài chính sách.
- Chứng chỉ/khóa tương thích với thuật toán và endpoint.
- Thời hạn chứng chỉ hoặc credential chưa vượt ngưỡng phải xoay.
- Phiên bản key cần thiết vẫn được hỗ trợ trong giai đoạn chuyển đổi.

Thông báo sai nên là “secret reference missing”, “credential invalid for target service” hoặc “certificate expired”; không ghi secret hay phần đủ dài giúp tái dựng nó.

### 10.2. Đề phòng leak qua công cụ debug

Những bề mặt thường bị bỏ sót: endpoint quản trị hiển thị môi trường, log bind properties, Java record toString, exception với giá trị property, crash dump, debug response, tracing span attribute, deployment diff và artifact CI.

Nếu đối tượng chứa password hoặc token, tránh in toàn bộ đối tượng. Masking bằng vài dấu sao chỉ hữu dụng khi không có đường khác tiết lộ giá trị gốc; kiểm soát truy cập vào log/telemetry vẫn cần.

### 10.3. Rotation là thay đổi cấu hình có trạng thái

Thay reference hoặc key cần quan tâm:

- Service cũ và mới có chấp nhận key tương ứng trong cửa sổ chuyển đổi không?
- Connection pool có tiếp tục dùng credential cũ sau khi config đã cập nhật không?
- Consumer/producer có cần drain hay recreate client?
- Khi thu hồi key cũ, có request dài hoặc message trễ nào còn dùng nó?
- Có audit trail, kế hoạch rollback và giới hạn thời gian overlap không?

Một secret đã bị xâm phạm có thể cần **thu hồi gấp**, khi đó ưu tiên chặn lạm dụng thay vì giữ mọi instance hoạt động bằng credential cũ.

## 11. Cấu hình sai và phạm vi ảnh hưởng trong microservices

Trong monolith, một config lỗi có thể làm cả process lỗi. Trong microservices, một lỗi ở shared infrastructure hoặc config service có thể tác động nhiều service cùng lúc.

### 11.1. Shared config là shared failure domain

Ví dụ tất cả service cùng đọc cấu hình circuit breaker từ một config server. Một thay đổi “timeout = 0” lan tới mọi service có thể khiến hệ thống đồng loạt tăng số request chờ. Lỗi khi đó không giới hạn ở service đầu tiên.

Cách giảm blast radius:

- Giới hạn namespace config theo owner/service/tenant.
- Cấp quyền ghi hẹp, review cho thay đổi ảnh hưởng nhiều service.
- Rollout canary theo replica, cell, tenant hoặc region khi có thể.
- Kiểm tra schema tương thích từng service trước khi publish.
- Giữ khả năng rollback revision và báo trạng thái theo cohort.
- Có default/last-known-good theo chính sách phù hợp, không được dùng giá trị cũ nếu nó đã bị thu hồi về mặt bảo mật.

### 11.2. Timeout và retry phải được xét toàn tuyến

Ví dụ:

~~~text
Gateway deadline:          900 ms
  |
  +-- Orders budget:       800 ms
        |
        +-- Inventory:     200 ms
        |
        +-- Payment:       350 ms
        |
        +-- DB commit:     150 ms
        |
        +-- Network/queue reserve
~~~

Nếu Payment timeout được override thành 5 giây, giá trị đó có thể hợp lệ với HTTP client nhưng **không hợp lệ với đường đặt hàng**. Khi nhiều lớp cùng retry, tải downstream còn có thể tăng cấp số nhân theo số lần thử ở từng tầng.

Một cấu hình đúng phải tính theo critical path, ngân sách timeout của caller, số lần retry, backoff, khả năng cancellation và headroom của dependency. Đừng chỉ copy timeout riêng của từng SDK.

### 11.3. Capacity configuration là hợp đồng liên service

Giả sử mỗi instance Order dùng pool tối đa 30 connection tới DB; triển khai 40 replica có thể đòi tới 1.200 connection trước khi tính client khác. Nếu DB quota toàn cluster chỉ có 800 connection khả dụng, cấu hình từng instance vẫn “hợp lệ” nhưng tổng thể không hợp lệ.

~~~text
Max possible connections
  ≈ replicas × per-replica pool limit
    + other services' DB connections
    + reserved operational connections
~~~

Đây là phép ước tính giới hạn, không phải số connection thực tại mọi thời điểm. Phải kiểm chứng với autoscaling maxReplicas, connection proxy/pooler và traffic burst. Kích thước pool, queue, worker count và retry cần xem như **ngân sách tài nguyên toàn hệ thống**.

### 11.4. Tenant và region

Một tenant có thể được triển khai với limit khác tenant khác, nhưng cơ chế override phải chặn vượt giới hạn an toàn và không cho tenant tự điều chỉnh policy bảo mật dành cho chính mình. Với multi-region, cấu hình phải giữ dữ liệu ở đúng vùng theo chính sách và có kiểm soát khi failover.

## 12. Phát hiện configuration drift

**Configuration drift** xảy ra khi trạng thái thực tế khác trạng thái mong muốn hoặc các instance lẽ ra tương đương lại dùng khác nhau.

Ví dụ:

- Replica A dùng timeout 800 ms, replica B dùng 5 giây.
- Một pod được restart và nhận secret mới; các pod khác còn connection đang dùng credential cũ.
- Dashboard feature flag bị thay đổi thủ công, không đi qua change review.
- Bản deployment mới vẫn giữ một env var cũ ưu tiên hơn config file.

### 12.1. Quan sát revision và fingerprint an toàn

Có thể gắn cho mỗi instance:

- Application version/build ID.
- Deployment revision.
- Config schema version.
- Config revision hoặc fingerprint của **phần cấu hình không nhạy cảm đã canonicalize**.
- Thời điểm load config.
- Cohort/cell/region và trạng thái validation.

Fingerprint không nên tạo bằng cách phơi bày danh sách secret. Nếu cần biết secret version đang dùng, dùng ID phiên bản hoặc metadata hạn chế truy cập; không đưa secret content vào label metric hoặc hash công khai có thể giúp đoán những bí mật entropy thấp.

### 12.2. Tín hiệu cảnh báo

| Tín hiệu | Cách diễn giải |
|---|---|
| config_validation_failure tăng | Có release hoặc runtime update không hợp lệ |
| config_revision_mismatch trong cùng cohort | Drift, rollout dở hoặc refresh lỗi |
| readiness_failure sau deploy | Cấu hình sai hoặc dependency bắt buộc không sẵn sàng |
| secret_access_denied | Service account/path/permission sai |
| cert_expiry_days thấp | Chứng chỉ cần rotation |
| timeout/retry/fallback tăng sau config revision | Có thể config mới ảnh hưởng độ trễ và tải |
| 401/403 tăng sau đổi issuer/key/audience | Khả năng cấu hình xác thực không tương thích |
| DB connection pool saturation tăng | Capacity config thiếu headroom |
| Queue lag và retry storm tăng | Worker/backoff/concurrency config không phù hợp |

Đặt cảnh báo theo ngưỡng hợp lý và owner. Một đợt canary có thể cố ý chạy nhiều revision; phân biệt sự khác biệt đã được phép với drift bất thường.

## 13. Quy trình xử lý khi phát hiện cấu hình sai

Ví dụ một deploy làm tỷ lệ timeout Payment tăng từ 0,2% lên 18%.

1. **Nhìn thay đổi gần nhất:** app version, deployment revision, config revision, feature flag và secret version.
2. **Xác định phạm vi:** endpoint, tenant, region, cell, instance; phân biệt toàn bộ lưu lượng với canary.
3. **Đối chiếu hiệu lực:** timeout, retry, endpoint, credential reference và route thực tế; kiểm tra có override ngoài dự kiến không.
4. **Khoanh vùng:** dừng rollout, giảm traffic vào cohort lỗi hoặc vô hiệu hóa feature không thiết yếu theo policy.
5. **Khôi phục trạng thái an toàn:** rollback revision hoặc áp dụng config đã xác minh; nếu có credential bị lộ thì thu hồi theo quy trình an ninh, không quay về credential nguy hiểm.
6. **Kiểm chứng:** readiness, latency, error rate, retry rate, chất lượng kết quả nghiệp vụ và khả năng phục hồi backlog.
7. **Ngăn tái diễn:** thêm kiểm tra schema/invariant, ràng buộc quyền thay đổi, cảnh báo drift hoặc thử nghiệm tương ứng.

Không chỉ sửa file YAML rồi tuyên bố xong. Nếu override ở deployment đang thắng file, thay đổi file có thể không tác động tới giá trị hiệu lực.

### Báo lỗi kỹ thuật có ích mà vẫn an toàn

Ví dụ:

~~~text
CONFIG_INVALID
  service: checkout
  environment: production
  configRevision: cfg-2026-11-12-07
  property: checkout.payment.timeout
  rule: must be positive and <= approved dependency budget
  remediation: correct deployment config and redeploy
~~~

Không đưa URL nhạy cảm chứa credential, secret material hoặc toàn bộ config dump vào log. Đối với định danh target không nhạy cảm có thể hiện giá trị đã kiểm soát; với secret chỉ hiện trạng thái hoặc reference đã được phép công bố.

## 14. Bộ kiểm thử cần có cho config contract

### 14.1. Kiểm thử schema và binder

| Trường hợp | Hành vi mong đợi |
|---|---|
| Missing required endpoint | Khởi tạo thất bại với property path rõ |
| Chuỗi timeout không parse được | Binding thất bại |
| Timeout = 0, âm hoặc vượt policy | Validation thất bại |
| Retry max-attempts ngoài phạm vi | Validation thất bại |
| credential-ref là chuỗi trắng | Validation thất bại |
| Key bị đánh máy sai trong namespace kiểm soát | Phát hiện unknown key hoặc thiếu required field |
| Giá trị default không được override | Dùng default đã định và hiển thị metadata an toàn |
| Config cho môi trường dev đưa vào production | Bị chặn bởi environment policy |
| Hai trường mâu thuẫn | Cross-field validation thất bại |
| Có secret trong log exception | Kiểm tra redaction phải phát hiện và ngăn |

### 14.2. Kiểm thử thực tế của deployment

- Cấu hình dùng cho từng môi trường có tương thích phiên bản ứng dụng?
- Các secret reference có được cấp đúng quyền cho workload identity?
- Cấu hình có chịu được tăng replica, failover, hot partition, traffic burst?
- Một lỗi config của tenant A có bị cô lập khỏi tenant B?
- Một revision sai đang rollout có dừng được trước khi ảnh hưởng cả cluster?
- Rollback config có phục hồi hành vi không? Có phụ thuộc migration dữ liệu hoặc secret rotation khiến rollback không an toàn?
- Khi config service mất kết nối, mỗi loại property dùng last-known-good, fail closed hoặc không sẵn sàng theo chính sách nào?
- Khi hot reload hai property liên quan, có khoảng chuyển tiếp không nhất quán không?
- Có thể tìm được version config gây incident mà không cần đọc secret?

Kiểm thử config hợp lý phải bao gồm trường hợp **cấu hình thay đổi nhưng code không đổi**, vì đó là một nguồn sự cố vận hành phổ biến.

## 15. Những ngộ nhận dễ gây lỗi

**“Đặt default cho mọi trường giúp ứng dụng luôn chạy.”** Có trường thiếu nên khiến startup thất bại. Default cho DB production hoặc khóa mã hóa có thể dẫn tới kết nối sai môi trường hay mất an toàn dữ liệu.

**“YAML parse được nghĩa là cấu hình đúng.”** Cú pháp chỉ là bước đầu. Cần kiểm kiểu, required, range, cross-field, môi trường và tài nguyên liên quan.

**“Có @NotNull là đủ.”** Chuỗi rỗng vẫn khác null; URI đúng cú pháp vẫn có thể dùng HTTP không phù hợp hoặc trỏ sai host. Nhiều quy tắc phải được kiểm tra riêng.

**“Kiểm tra từng service độc lập là đủ.”** Mỗi pool có thể hợp lệ nhưng tổng pool vượt quota DB; mỗi timeout có thể dương nhưng tổng luồng vượt deadline.

**“Application tự restart sẽ tự hết lỗi.”** Cấu hình sai bất biến qua restart; restart storm chỉ khiến giám sát ồn hơn. Cần báo CONFIG_INVALID và sửa nguồn đúng.

**“Config trong Git là source of truth duy nhất.”** Khi hệ thống có override từ env, command line, secret service hoặc UI feature flag, trạng thái hiệu lực có thể khác với Git. Cần biết source thực và precedence.

**“Có checksum thì có thể public toàn bộ config.”** Hash/fingerprint của cấu hình bí mật hoặc giá trị entropy thấp vẫn có rủi ro suy đoán; không biến secret thành dữ liệu telemetry.

**“Rollback config luôn an toàn.”** Nếu rollback tái kích hoạt khóa đã thu hồi, bỏ policy bảo mật mới hoặc không tương thích migration, có thể nguy hiểm hơn giữ release ở trạng thái chưa sẵn sàng.

**“Feature flag có thể cập nhật từng trường độc lập.”** Với các trường phụ thuộc, cập nhật dở có thể tạo snapshot không hợp lệ. Cần validate toàn bộ snapshot và publish đồng bộ.

**“Secret tồn tại là đã đúng.”** Secret có thể hết hạn, sai quyền, sai môi trường, sai đối tượng nhận, hoặc không khớp endpoint. Kiểm tra reference chỉ là một lớp.

## 16. Tình huống phân tích: cấu hình đổi khiến Checkout quá tải

**Bối cảnh:** hệ thống có Gateway → Checkout → Payment. Gateway có deadline 1 giây. Payment thường phản hồi trong 200 ms. Một kỹ sư đổi config Payment timeout từ 700 ms thành 5 giây để “tránh lỗi mạng” và tăng max-attempts từ 1 lên 4. Mỗi instance Checkout có 40 worker; có 30 instance; Payment dùng chung giới hạn request đồng thời.

Sau deploy, lưu lượng không tăng nhiều nhưng in-flight requests, queue length và timeout toàn request tăng nhanh. Một số người dùng thử lại và có nguy cơ tạo giao dịch trùng.

**Câu hỏi:**

1. Vì sao timeout 5 giây và retry 4 lần có thể làm hệ thống lỗi nặng hơn dù Payment đôi khi chậm?
2. Cần xác thực những quan hệ nào giữa Gateway deadline, Payment timeout, số lần thử và retry backoff?
3. Đặt giới hạn concurrency ở Checkout hay Payment thì có tác dụng nào? Cần xét tổng giới hạn toàn cụm như thế nào?
4. Nếu client timeout nhưng Payment đã xử lý thành công, cơ chế nào giúp tránh giao dịch lặp?
5. Phát hiện cấu hình sai nên diễn ra ở PR, trước deploy, startup hay runtime? Tín hiệu nào giúp chứng minh nguyên nhân?
6. Khi rollback config, cần kiểm chứng lại những dữ liệu và kết quả giao dịch nào?

**Gợi ý hướng giải:**

- Xác định deadline tổng, ngân sách cho từng chặng và chính sách retry có giới hạn, backoff, jitter.
- Kiểm tra ràng buộc tổng thời gian và concurrency trước khi rollout; không chấp nhận timeout riêng lớn hơn ngân sách caller nếu không có lý do và cơ chế bất đồng bộ phù hợp.
- Áp dụng idempotency key/deduplication cho thao tác có side effect và kiểm soát kết quả “chưa xác định” sau timeout.
- Quan sát config revision bên cạnh p95/p99 latency, in-flight requests, rejection, retry rate và tỷ lệ giao dịch hoàn tất.
- Canary cấu hình, dừng rollout khi vượt guardrail và rollback có kiểm chứng tính đúng đắn nghiệp vụ.

Bài học chính: **cấu hình không phải chỉ là dữ liệu đọc lúc startup; nó quyết định mức tải, ranh giới lỗi và tính đúng đắn của nghiệp vụ**.

## 17. Checklist áp dụng cho một thuộc tính cấu hình mới

Trước khi thêm một property, trả lời rõ:

1. **Purpose:** thuộc tính điều khiển hành vi gì, hậu quả nếu sai?
2. **Owner:** ai chịu trách nhiệm quyết định và phê duyệt giá trị?
3. **Type / unit:** kiểu, đơn vị và định dạng được chấp nhận?
4. **Required / default:** có bắt buộc không; nếu có default, tại sao nó an toàn?
5. **Scope:** môi trường, tenant, service, region hay instance nào sử dụng?
6. **Source / precedence:** giá trị đến từ đâu, nguồn nào có quyền override?
7. **Validation:** required, syntax, range, cross-field, environment và version constraints là gì?
8. **Security:** property có chứa secret hoặc ảnh hưởng authentication/authorization không?
9. **Activation:** áp dụng lúc startup, restart hay hot reload; có cần atomic snapshot?
10. **Failure behavior:** fail fast, giữ readiness false hay degrade chức năng tùy chọn?
11. **Observability:** có thể xác minh effective value/revision mà không rò rỉ dữ liệu nhạy cảm?
12. **Change safety:** test, canary, rollback, deprecation và migration strategy?

Nếu chưa trả lời được các câu này cho thuộc tính có rủi ro cao, nên hoàn thiện hợp đồng cấu hình trước khi triển khai.

## 18. Kết luận cần ghi nhớ

- **Default là quyết định thiết kế, không phải cách che thiếu dữ liệu.** Dùng mặc định bảo thủ cho thuộc tính ít rủi ro; yêu cầu cấu hình tường minh khi việc đoán sai có thể làm hỏng dữ liệu hoặc bảo mật.
- **Validation phải đi xa hơn cú pháp:** bắt buộc, kiểu, khoảng giá trị, quan hệ liên trường, điều kiện môi trường và khả năng tương thích phiên bản.
- **Fail fast có chủ đích:** cấu hình cốt lõi sai cần được phát hiện trước khi nhận request; lỗi dependency tạm thời được xử lý theo readiness và chính sách phục hồi riêng.
- **Effective configuration và nguồn override quyết định hành vi thực tế.** Theo dõi revision, drift và thay đổi trên từng cohort/region.
- **Runtime hot reload cần validate snapshot trước khi áp dụng**, không công bố nửa trạng thái mới khi các trường phụ thuộc nhau.
- **Secret là loại dữ liệu đặc biệt:** lưu và truy cập có kiểm soát, không log, không tự xuất hiện trong các bản dump cấu hình hoặc metric.
- **Trong microservices, giới hạn đúng phải xét toàn hệ thống:** deadline, retry, pool, replica, tenant và shared infrastructure.
- **Mỗi thay đổi cấu hình quan trọng là một thay đổi vận hành có thể gây sự cố**, cần kiểm thử, quan sát, rollout và khả năng khôi phục tương xứng.
