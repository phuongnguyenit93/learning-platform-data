# Tách cấu hình, bí mật, đồng hồ và dịch vụ ngoài khỏi logic nghiệp vụ

Một ca sử dụng có thể cần biết địa chỉ của dịch vụ thanh toán, thời gian chờ HTTP, khóa API, múi giờ hoặc thời điểm hiện tại. Đây là những thông tin và khả năng cần thiết để ứng dụng vận hành, nhưng chúng thay đổi theo môi trường, nhà cung cấp hoặc thời gian. Nếu đặt chúng trực tiếp trong logic nghiệp vụ, code sẽ khó kiểm thử, khó triển khai ở nhiều môi trường và dễ phụ thuộc vào công nghệ bên ngoài.

Trong module `SOFTWARE_DESIGN_ARCHITECTURE_ARCHITECTURAL_PATTERN_LAYERED` — học tổ chức phần mềm theo kiến trúc phân tầng — bài học này trình bày cách tách cấu hình, bí mật, đồng hồ và dịch vụ ngoài khỏi logic nghiệp vụ. Mục tiêu là để tầng ứng dụng/miền diễn đạt quy tắc và nhu cầu bằng hợp đồng ổn định, còn tầng hạ tầng và điểm lắp ráp cung cấp giá trị cấu hình, nguồn thời gian và adapter cụ thể.

Các mối quan tâm này thường được gọi là *cross-cutting concerns* vì chúng ảnh hưởng đến nhiều phần của ứng dụng. Không có nghĩa tất cả chúng phải nằm trong một package `common` hoặc một lớp tiện ích dùng chung. Cần xác định rõ ai sở hữu chính sách, ai cung cấp chi tiết kỹ thuật và nơi nào nối các thành phần với nhau.

## 1. Phân biệt chính sách nghiệp vụ với chi tiết vận hành

Hãy xét một chức năng thanh toán. Một ca sử dụng có thể cần quyết định:

- Đơn hàng nào đủ điều kiện thanh toán?
- Khi nào được phép thu tiền?
- Nếu thanh toán thất bại thì trạng thái đơn hàng thay đổi thế nào?
- Một khoản thanh toán có thể được thử lại trong trường hợp nào?

Đây là những câu hỏi về chính sách và hành vi nghiệp vụ. Trong khi đó, các thông tin sau là chi tiết vận hành:

- URL của cổng thanh toán ở môi trường thử nghiệm hoặc production.
- API key hoặc chứng thư xác thực.
- HTTP connect timeout, response timeout và số lần retry.
- Cách tạo HTTP client, cấu hình TLS hoặc proxy.
- Nguồn thời gian và múi giờ mặc định của ứng dụng.

Hai nhóm có liên quan nhưng không nên bị trộn lẫn. Logic nghiệp vụ có thể quyết định một khoản thanh toán được thử lại khi nhận một kết quả tạm thời cụ thể; adapter hạ tầng chịu trách nhiệm thực hiện request HTTP với timeout và chuyển lỗi mạng thành kết quả mà tầng ứng dụng hiểu.

| Mối quan tâm | Câu hỏi thuộc về nó | Nơi thường sở hữu |
|---|---|---|
| Chính sách nghiệp vụ | Có được thanh toán đơn hàng này không? | Miền hoặc tầng ứng dụng |
| Cấu hình triển khai | Cổng thanh toán ở địa chỉ nào? Timeout bao lâu? | Cấu hình ứng dụng / hạ tầng |
| Bí mật | Dùng credential nào để xác thực? | Secret manager hoặc nền tảng triển khai; adapter nhận credential cần thiết |
| Thời gian | Thời điểm hiện tại là gì? Quy tắc hạn chót được tính ra sao? | Nguồn `Clock` được cung cấp; chính sách thời gian thuộc nghiệp vụ |
| Giao tiếp bên ngoài | HTTP request, TLS, JSON và mã lỗi được xử lý thế nào? | Adapter hạ tầng |

Nguyên tắc này giúp thay đổi URL, khóa xác thực, nhà cung cấp hoặc cách đọc thời gian mà không phải sửa các quy tắc cốt lõi.

## 2. Đưa cấu hình ra khỏi mã nguồn

Giá trị cấu hình thường khác nhau giữa môi trường local, test, staging và production. Ví dụ, ứng dụng có thể gọi cổng thanh toán giả lập trong test, sandbox ở staging và endpoint chính thức trong production. Nếu viết cứng URL hoặc timeout trong service, mỗi lần đổi môi trường có thể buộc phải sửa mã nguồn và tạo bản build khác.

Hãy đưa các giá trị có thể thay đổi ra cấu hình triển khai. Với Spring Boot, có thể khai báo trong `application.yml`:

```yaml
payments:
  client:
    base-url: ${PAYMENT_API_BASE_URL:https://sandbox.example.test}
    connect-timeout: 2s
    response-timeout: 5s
    max-attempts: 2
```

`PAYMENT_API_BASE_URL` có thể được cung cấp bởi môi trường chạy; giá trị mặc định ở đây chỉ phục vụ cấu hình sandbox minh họa. Không nên để một URL sandbox trở thành mặc định production nếu cấu hình triển khai không được kiểm soát.

### Dùng cấu hình có kiểu thay vì đọc chuỗi tùy tiện

Spring Boot hỗ trợ `@ConfigurationProperties` để gom cấu hình liên quan thành một đối tượng có kiểu. Ví dụ dưới đây dùng record, phù hợp với constructor binding trong Spring Boot 3:

```java
@ConfigurationProperties(prefix = "payments.client")
@Validated
public record PaymentClientProperties(
    @NotNull URI baseUrl,
    @NotNull Duration connectTimeout,
    @NotNull Duration responseTimeout,
    @Min(1) @Max(5) int maxAttempts
) {}
```

Đăng ký cấu hình bằng `@ConfigurationPropertiesScan` trên lớp ứng dụng hoặc `@EnableConfigurationProperties(PaymentClientProperties.class)` trong một lớp cấu hình:

```java
@SpringBootApplication
@ConfigurationPropertiesScan
public class PaymentApplication {
    public static void main(String[] args) {
        SpringApplication.run(PaymentApplication.class, args);
    }
}
```

Các annotation validation cần dependency Bean Validation tương ứng, chẳng hạn `spring-boot-starter-validation`. Khi cấu hình thiếu hoặc sai kiểu, ứng dụng có thể thất bại ngay lúc khởi động thay vì chạy một thời gian rồi mới lỗi ở request đầu tiên.

`URI`, `Duration` và số nguyên thể hiện rõ kiểu dữ liệu hơn chuỗi tùy ý. Điều đó giúp phát hiện lỗi định dạng, đơn vị thời gian và giới hạn ngay tại ranh giới cấu hình. Hãy chọn default có chủ đích; với giá trị bắt buộc, nên yêu cầu khai báo rõ và kiểm tra khi khởi động.

### Cấu hình theo môi trường

Có thể dùng file cấu hình cơ sở và profile riêng:

```yaml
# application.yml
payments:
  client:
    connect-timeout: 2s
    response-timeout: 5s
    max-attempts: 2
```

```yaml
# application-local.yml
payments:
  client:
    base-url: http://localhost:9090
```

```yaml
# application-prod.yml
payments:
  client:
    base-url: ${PAYMENT_API_BASE_URL}
    connect-timeout: 1s
    response-timeout: 3s
    max-attempts: 2
```

Profile `prod` có thể được kích hoạt bằng `SPRING_PROFILES_ACTIVE=prod` hoặc cơ chế triển khai tương đương. File cấu hình được đóng gói trong ứng dụng nên chỉ chứa giá trị không nhạy cảm; cấu hình production và bí mật có thể được cung cấp từ môi trường hoặc nền tảng quản lý cấu hình. Cần tránh để nhiều nguồn cấu hình ghi đè lẫn nhau mà nhóm không biết nguồn nào có độ ưu tiên cao hơn.

Không nên tạo một nhánh `if (environment.equals("prod"))` bên trong nghiệp vụ để chọn URL hoặc chính sách triển khai. Việc lựa chọn môi trường thuộc cấu hình và composition root. Nếu có khác biệt thực sự về chính sách nghiệp vụ theo khu vực hoặc loại sản phẩm, hãy mô hình hóa điều đó thành policy rõ ràng thay vì giấu trong tên profile.

## 3. Quản lý bí mật riêng với cấu hình thông thường

API key, mật khẩu database, private key, client secret và token truy cập là **bí mật**. Chúng khác với cấu hình thông thường như URL, timeout hay kích thước batch vì nếu bị lộ, người khác có thể truy cập hoặc thao tác hệ thống.

Không đặt bí mật trực tiếp trong:

- Mã nguồn Java hoặc file cấu hình được commit vào Git.
- Docker image, file mẫu hoặc tài liệu có thể chia sẻ công khai.
- Log, exception message, metric label hoặc nội dung trace.
- Screenshot, ticket hay thông điệp hỗ trợ không có kiểm soát truy cập.

Một cách cung cấp secret đơn giản trong môi trường phát triển là biến môi trường:

```yaml
payments:
  credentials:
    api-key: ${PAYMENT_API_KEY}
```

Không ghi giá trị mặc định cho `PAYMENT_API_KEY`. Nếu biến này không có, ứng dụng nên báo cấu hình thiếu và không khởi động chức năng thanh toán ở trạng thái giả vờ hoạt động. Trong production, có thể dùng secret manager của nền tảng, dịch vụ quản lý bí mật hoặc cơ chế mount secret vào container/VM. Cách phân phối cụ thể tùy hạ tầng; nguyên tắc là bí mật được cấp tại runtime với quyền truy cập tối thiểu.

### Bind credential mà không làm lộ khi log

Có thể dùng một lớp cấu hình riêng cho credential. Không tạo `toString()` chứa giá trị secret và không log toàn bộ đối tượng cấu hình:

```java
@ConfigurationProperties(prefix = "payments.credentials")
@Validated
public class PaymentCredentials {
    @NotBlank
    private String apiKey;

    public String getApiKey() {
        return apiKey;
    }

    public void setApiKey(String apiKey) {
        this.apiKey = apiKey;
    }

    @Override
    public String toString() {
        return "PaymentCredentials[apiKey=REDACTED]";
    }
}
```

Đăng ký cả `PaymentCredentials` bằng `@ConfigurationPropertiesScan` hoặc `@EnableConfigurationProperties`. Khi cần log cấu hình để chẩn đoán, chỉ log những trường không nhạy cảm và che các trường có thể nhận diện bí mật. Cũng cần kiểm tra log của HTTP client vì một số chế độ wire logging có thể ghi header `Authorization` hoặc body chứa token.

### Vòng đời và xoay vòng bí mật

Credential cần được cấp theo nguyên tắc quyền tối thiểu, có thời hạn và có quy trình thu hồi. Khi xoay vòng API key, hệ thống có thể cần giai đoạn chấp nhận cả key cũ và key mới, cập nhật secret tại nền tảng triển khai, khởi động lại hoặc refresh client, rồi thu hồi key cũ. Quy trình chính xác phụ thuộc nhà cung cấp.

Không nên lưu secret vào database nghiệp vụ chỉ vì muốn dùng chung giữa các instance. Secret manager thường phù hợp hơn vì có kiểm soát truy cập, audit và cơ chế rotation. Nếu phải lưu một bí mật trong database, cần có yêu cầu bảo vệ, mã hóa, phân quyền và vòng đời rõ ràng.

## 4. Đưa nguồn thời gian vào ứng dụng qua Clock

Gọi trực tiếp `Instant.now()` hoặc `LocalDate.now()` bên trong nhiều lớp làm cho hành vi phụ thuộc vào đồng hồ thật. Khi kiểm thử hạn thanh toán, ngày hết hạn hoặc thời điểm khóa tài khoản, test khó tái lập vì thời gian luôn trôi.

Java cung cấp `java.time.Clock` để tách nguồn thời gian khỏi logic. Trong Spring, đăng ký một bean dùng UTC:

```java
@Configuration
class TimeConfiguration {
    @Bean
    Clock applicationClock() {
        return Clock.systemUTC();
    }
}
```

Tầng ứng dụng hoặc miền nhận `Clock` qua constructor:

```java
public final class PaymentDeadlinePolicy {
    private final Clock clock;

    public PaymentDeadlinePolicy(Clock clock) {
        this.clock = clock;
    }

    public boolean isExpired(Instant deadline) {
        return !clock.instant().isBefore(deadline);
    }
}
```

Quy tắc “đã đến hoặc vượt hạn chót thì hết hạn” vẫn là logic nghiệp vụ. `Clock` chỉ cung cấp thời điểm hiện tại. Nhờ vậy, có thể thay đồng hồ thật bằng đồng hồ cố định trong test:

```java
@Test
void deadlineIsExpiredAtTheExactInstant() {
    Instant deadline = Instant.parse("2026-05-10T10:00:00Z");
    Clock fixedClock = Clock.fixed(deadline, ZoneOffset.UTC);
    PaymentDeadlinePolicy policy = new PaymentDeadlinePolicy(fixedClock);

    assertTrue(policy.isExpired(deadline));
}
```

Với đồng hồ cố định, test không phụ thuộc thời điểm chạy. Có thể dùng `Clock.offset` để mô phỏng thời gian trôi hoặc `Clock.fixed` cho một thời điểm cụ thể. Tránh tạo một static clock toàn cục có thể bị thay đổi tùy tiện trong test song song.

### Instant, LocalDate và múi giờ

Hãy chọn kiểu thời gian theo ý nghĩa nghiệp vụ:

- `Instant` biểu diễn một thời điểm tuyệt đối trên dòng thời gian, thích hợp cho thời điểm tạo, thanh toán hoặc phát sự kiện.
- `LocalDate` biểu diễn ngày lịch không kèm múi giờ, phù hợp với ngày sinh hoặc ngày làm việc theo lịch.
- `LocalDateTime` biểu diễn ngày và giờ địa phương nhưng không xác định được một thời điểm tuyệt đối nếu thiếu múi giờ/offset.
- `ZonedDateTime` kết hợp thời điểm với múi giờ, hữu ích khi cần quy tắc lịch theo vùng như giờ mở cửa hoặc lịch địa phương.

Đối với thời điểm kỹ thuật, thường lưu `Instant` và trao đổi theo UTC. Với quy tắc lịch địa phương, cần lưu hoặc xác định `ZoneId` có ý nghĩa, ví dụ `Asia/Ho_Chi_Minh`; không giả định mọi người dùng hoặc máy chủ cùng một múi giờ. `Clock.systemDefaultZone()` có thể phụ thuộc cấu hình máy chạy, nên chọn UTC hoặc zone tường minh để tránh thay đổi ngầm khi triển khai.

Không dùng `Clock` để thay thế mọi khái niệm thời gian trong miền. Một lịch làm việc, ngày nghỉ hoặc giờ cắt đơn hàng có thể cần một `BusinessCalendar` hay policy riêng vì nó phụ thuộc khu vực, ngày lễ và quy tắc tổ chức. `Clock` trả lời “bây giờ là lúc nào”; policy quyết định “thời điểm đó có ý nghĩa gì trong nghiệp vụ”.

## 5. Dịch vụ ngoài nên được truy cập qua hợp đồng

Tầng nghiệp vụ có thể cần một khả năng do hệ thống bên ngoài cung cấp: xác thực danh tính, thanh toán, gửi email, lấy tỷ giá hoặc kiểm tra địa chỉ. Nếu logic nghiệp vụ trực tiếp tạo HTTP client, ghép URL, thêm header và phân tích JSON, nó sẽ phụ thuộc vào giao thức, thư viện và nhà cung cấp.

Hãy định nghĩa một port theo nhu cầu của bên gọi. Ví dụ, tầng ứng dụng cần ủy quyền thanh toán:

```java
public interface PaymentGateway {
    AuthorizationResult authorize(PaymentRequest request);
}
```

Ca sử dụng phụ thuộc vào hợp đồng:

```java
public final class AuthorizeOrderPayment {
    private final PaymentGateway paymentGateway;

    public AuthorizeOrderPayment(PaymentGateway paymentGateway) {
        this.paymentGateway = paymentGateway;
    }

    public AuthorizationResult authorize(PaymentRequest request) {
        // Quy tắc nghiệp vụ có thể kiểm tra đơn đủ điều kiện trước lời gọi này.
        return paymentGateway.authorize(request);
    }
}
```

Adapter hạ tầng hiện thực port bằng HTTP client hoặc SDK của nhà cung cấp:

```java
@Component
@RequiredArgsConstructor
class HttpPaymentGateway implements PaymentGateway {
    private final PaymentHttpClient httpClient;
    private final PaymentClientProperties properties;
    private final PaymentCredentials credentials;

    @Override
    public AuthorizationResult authorize(PaymentRequest request) {
        ProviderPaymentResponse response = httpClient.authorize(
            properties.baseUrl(),
            properties.responseTimeout(),
            credentials.getApiKey(),
            request.idempotencyKey(),
            request.amount(),
            request.currency()
        );

        return mapResult(response);
    }

    private AuthorizationResult mapResult(ProviderPaymentResponse response) {
        // Chuyển mã và payload của nhà cung cấp thành kiểu nội bộ.
        return switch (response.status()) {
            case "APPROVED" -> AuthorizationResult.approved(response.reference());
            case "DECLINED" -> AuthorizationResult.declined(response.reasonCode());
            default -> AuthorizationResult.pending(response.reference());
        };
    }
}
```

`PaymentHttpClient` và `ProviderPaymentResponse` là các kiểu minh họa thuộc hạ tầng; chúng đại diện cho HTTP client và DTO theo API nhà cung cấp. Adapter sử dụng URL, timeout và credential từ cấu hình, sau đó chuyển kết quả ngoài thành kiểu mà tầng ứng dụng hiểu. Tầng nghiệp vụ không cần biết header xác thực, JSON field hoặc tên trạng thái riêng của nhà cung cấp.

Không phải mọi dịch vụ ngoài đều cần một interface riêng nếu ứng dụng nhỏ và không có ranh giới cần cách ly. Nhưng khi một dịch vụ ngoài ảnh hưởng nhiều ca sử dụng, có nhiều implementation, yêu cầu kiểm thử độc lập hoặc có thể thay đổi nhà cung cấp, port/adapter thường tạo ra ranh giới có giá trị.

## 6. Cấu hình client và xử lý lỗi ở adapter

Adapter là nơi thích hợp để tập trung các chi tiết giao tiếp:

- URL và đường dẫn endpoint.
- Header xác thực, credential và TLS.
- Connect timeout, response timeout và giới hạn kích thước payload.
- Mã hóa/giải mã request và response.
- Ánh xạ mã lỗi giao thức thành lỗi mà tầng ứng dụng hiểu.
- Retry, circuit breaker và rate limit nếu được cấu hình và phù hợp với ngữ nghĩa thao tác.

Ví dụ, timeout mạng nên được cấu hình bằng `Duration`, không rải số mili giây trong nhiều phương thức. Khi adapter nhận timeout, nó chuyển giá trị đó vào HTTP client lúc khởi tạo hoặc tạo request theo cách client hỗ trợ. Cần kiểm tra client có áp dụng timeout ở cấp kết nối, cấp request hay cả hai; tên thuộc tính cấu hình không tự đảm bảo hành vi tương ứng.

### Retry cần xét tính an toàn của thao tác

Retry một request đọc thường ít rủi ro hơn retry một request ghi. Nếu client gửi lệnh thanh toán, timeout có thể xảy ra sau khi nhà cung cấp đã xử lý request nhưng trước khi ứng dụng nhận response. Gửi lại một request mới mà không có idempotency key có thể thu tiền hai lần.

Vì vậy:

- Chỉ retry lỗi có khả năng tạm thời, ví dụ một số lỗi kết nối, timeout hoặc mã HTTP được chính sách xác định.
- Không retry mù quáng lỗi xác thực, request sai dữ liệu hoặc kết quả từ chối nghiệp vụ.
- Với thao tác ghi, dùng idempotency key ổn định cho cùng một ý định nghiệp vụ nếu nhà cung cấp hỗ trợ.
- Giới hạn số lần thử, thời gian tổng và dùng backoff có jitter để tránh tạo bão request.
- Giữ quyền quyết định nghiệp vụ ở tầng ứng dụng/miền; adapter chỉ thực hiện chính sách giao tiếp đã cấu hình và trả kết quả rõ ràng.

Circuit breaker có thể tạm ngừng gọi một dịch vụ đang lỗi liên tục để tránh chiếm tài nguyên và làm chậm toàn hệ thống. Nó không thay thế timeout, retry có giới hạn hoặc xử lý kết quả nghiệp vụ. Khi circuit mở, tầng ứng dụng cần nhận được lỗi hoặc trạng thái có thể diễn giải, ví dụ “dịch vụ thanh toán tạm thời không khả dụng”, để quyết định giữ đơn ở trạng thái chờ, thử lại sau hay yêu cầu can thiệp.

Không nên bắt mọi exception trong adapter rồi trả `null` hoặc một kết quả thành công giả. Hãy phân biệt lỗi giao tiếp, lỗi xác thực, lỗi dữ liệu và kết quả nghiệp vụ như thanh toán bị từ chối. Việc ánh xạ này là một phần của hợp đồng port.

## 7. Nối cấu hình, Clock và adapter tại composition root

Composition root là nơi ứng dụng tạo và kết nối các thành phần. Trong Spring, container quản lý bean và inject dependency qua constructor. Ví dụ cấu hình:

```java
@Configuration
@EnableConfigurationProperties({
    PaymentClientProperties.class,
    PaymentCredentials.class
})
class PaymentInfrastructureConfiguration {

    @Bean
    Clock applicationClock() {
        return Clock.systemUTC();
    }

    @Bean
    PaymentGateway paymentGateway(
            PaymentHttpClient httpClient,
            PaymentClientProperties properties,
            PaymentCredentials credentials) {
        return new HttpPaymentGateway(httpClient, properties, credentials);
    }
}
```

Nếu `HttpPaymentGateway` đã được đăng ký bằng `@Component`, không khai báo thêm một bean `PaymentGateway` trả về cùng adapter trong cấu hình. Chọn một cơ chế đăng ký cho mỗi implementation để tránh có hai bean cạnh tranh. Cũng cần bảo đảm `PaymentHttpClient` được tạo ở hạ tầng và được cấu hình timeout, TLS cùng connection pool phù hợp.

Trong một ứng dụng lớn, có thể đặt cấu hình client, adapter và bean factory trong module hạ tầng tương ứng. Tầng ứng dụng chỉ biết `PaymentGateway`, `Clock` hoặc các hợp đồng khác mà nó cần. Composition root có thể nằm ở module bootstrap hoặc lớp cấu hình của ứng dụng; vị trí cụ thể phụ thuộc cách tổ chức dự án.

## 8. Kiểm thử khi các phụ thuộc có thể thay thế

Tách cấu hình, thời gian và dịch vụ ngoài làm cho kiểm thử dễ tái lập hơn. Mỗi loại phụ thuộc có cách kiểm thử phù hợp:

| Phụ thuộc | Trong unit test | Trong integration test |
|---|---|---|
| Cấu hình | Truyền object properties với giá trị rõ ràng | Kiểm tra binding, validation và profile của Spring context |
| Bí mật | Dùng credential giả, không dùng key production | Xác minh secret được nạp từ nguồn test và không xuất hiện trong log |
| Đồng hồ | Dùng `Clock.fixed` | Kiểm tra tích hợp với database hoặc scheduler nếu thời điểm ảnh hưởng xử lý |
| Dịch vụ ngoài | Dùng fake/mock port để kiểm thử chính sách | Dùng HTTP stub server hoặc sandbox của nhà cung cấp để kiểm tra adapter |

Ví dụ test policy với đồng hồ cố định:

```java
@Test
void paymentCanBeRetriedOnlyBeforeRetryDeadline() {
    Instant now = Instant.parse("2026-07-01T10:00:00Z");
    Clock clock = Clock.fixed(now, ZoneOffset.UTC);
    RetryWindow policy = new RetryWindow(clock);

    assertTrue(policy.isOpenUntil(now.plusSeconds(60)));
    assertFalse(policy.isOpenUntil(now.minusSeconds(1)));
}
```

Test không cần chờ thời gian thực trôi qua. Đối với dịch vụ ngoài, fake `PaymentGateway` có thể trả về kết quả được kiểm soát để kiểm tra ca sử dụng. Adapter HTTP cần test riêng cho URL, header, payload, timeout và ánh xạ response bằng stub server. Không nên để unit test của miền phụ thuộc mạng hoặc API thật.

### Kiểm thử cấu hình sai

Hãy kiểm tra cả cấu hình hợp lệ và cấu hình bị thiếu:

- URL không phải URI hợp lệ.
- Timeout bằng 0 hoặc âm nếu hợp đồng yêu cầu giá trị dương.
- Số lần retry vượt giới hạn được chấp nhận.
- Credential bắt buộc không được cấp.
- Profile production vô tình dùng endpoint sandbox.

Fail-fast khi khởi động thường dễ chẩn đoán hơn lỗi xuất hiện giữa một request. Tuy nhiên, không đưa giá trị secret vào thông báo validation hoặc log lỗi.

## 9. Những sai lầm thường gặp

- **Hard-code endpoint và timeout trong service:** thay đổi môi trường buộc sửa code và làm test khó cấu hình.
- **Đưa API key vào Git:** secret có thể tồn tại trong lịch sử commit ngay cả khi đã xóa ở commit sau; cần thu hồi và xoay vòng nếu đã lộ.
- **Log toàn bộ đối tượng cấu hình:** `toString()` hoặc debug log có thể in credential và token.
- **Gọi `Instant.now()` ở khắp nơi:** test phụ thuộc đồng hồ thật và khó tái lập tại biên thời gian.
- **Dùng múi giờ mặc định của máy:** cùng một dữ liệu có thể được diễn giải khác nhau giữa môi trường.
- **Để tầng miền tạo HTTP client:** mô hình nghiệp vụ phụ thuộc thư viện, giao thức và nhà cung cấp.
- **Trả DTO của nhà cung cấp qua tầng ứng dụng:** thay đổi API ngoài lan vào logic nội bộ.
- **Retry mọi lỗi:** thao tác ghi có thể lặp side effect, còn lỗi vĩnh viễn làm tăng tải vô ích.
- **Nuốt exception hoặc trả null:** tầng ứng dụng không phân biệt được lỗi kỹ thuật với kết quả nghiệp vụ.
- **Tạo một lớp `Utility` toàn cục:** nhiều mối quan tâm khác nhau bị gom lại và khó xác định quyền sở hữu.

## 10. Quy trình áp dụng cho một phụ thuộc mới

Khi một ca sử dụng cần cấu hình, thời gian hoặc dịch vụ ngoài, hãy đi qua các bước:

1. Xác định phần nào là chính sách nghiệp vụ và phần nào là chi tiết triển khai có thể thay đổi.
2. Đưa URL, timeout, giới hạn và tùy chọn triển khai vào cấu hình có kiểu; xác thực chúng khi khởi động.
3. Cấp bí mật qua secret manager hoặc cơ chế runtime được kiểm soát; giới hạn quyền và không ghi log giá trị.
4. Nếu logic cần thời điểm hiện tại, inject `Clock` và chọn `Instant`, `LocalDate` hoặc múi giờ theo đúng ý nghĩa.
5. Nếu cần dịch vụ ngoài, định nghĩa port theo nhu cầu của consumer và đặt adapter ở hạ tầng.
6. Tập trung xác thực, timeout, retry, circuit breaker và ánh xạ lỗi ở adapter; giữ chính sách nghiệp vụ trong tầng sở hữu nó.
7. Nối implementation tại composition root và xác định rõ profile/bean được dùng ở mỗi môi trường.
8. Kiểm thử với cấu hình giả, đồng hồ cố định, fake port và HTTP stub; kiểm tra thêm binding và cấu hình production.

Tách cấu hình, bí mật, đồng hồ và dịch vụ ngoài giúp các tầng tập trung vào đúng trách nhiệm. Tầng nghiệp vụ diễn đạt điều hệ thống phải làm và những điều kiện phải bảo vệ; tầng hạ tầng biết cách kết nối với thế giới bên ngoài; composition root cung cấp các giá trị và implementation phù hợp cho từng môi trường. Khi các ranh giới này rõ ràng, ứng dụng dễ kiểm thử, dễ thay đổi nhà cung cấp và an toàn hơn khi triển khai.
