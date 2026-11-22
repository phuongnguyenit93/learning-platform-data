# Rủi ro lộ bí mật qua dòng lệnh, log, `toString()` và thông báo lỗi trong Spring Boot

## 1. Mục tiêu của bài học

Spring Boot cho phép cấu hình ứng dụng qua `application.yml`, `application.properties`, biến môi trường, Java system properties, tham số dòng lệnh, Config Data và nhiều `PropertySource` khác. Cơ chế này thuận tiện cho việc triển khai giữa môi trường phát triển, kiểm thử và production. Tuy nhiên, **đưa một bí mật vào cấu hình không đồng nghĩa bí mật đó đã được bảo vệ**.

Những giá trị sau cần được coi là nhạy cảm khi xuất hiện trong cấu hình:

- Mật khẩu cơ sở dữ liệu, Redis, message broker và các dịch vụ bên ngoài.
- API key, access token, refresh token, bearer token và client secret.
- Private key, passphrase, signing key, encryption key và secret dùng ký JWT.
- Chuỗi kết nối có thông tin xác thực nhúng bên trong.
- Cookie phiên, mã xác thực tạm thời, mã khôi phục và credential có thời hạn ngắn.
- Một số định danh hoặc thông tin cấu hình nội bộ nếu việc tiết lộ có tác động bảo mật.

Bài này tập trung vào bốn đường rò rỉ phổ biến:

1. **Dòng lệnh**: bí mật xuất hiện trong lệnh khởi chạy, process arguments hoặc shell history.
2. **Log**: bí mật được in ra application log, access log, HTTP client log hoặc hệ thống thu thập log.
3. **`toString()`**: một đối tượng cấu hình/DTO chứa bí mật bị chuyển thành chuỗi và lan sang log, debugger hoặc exception.
4. **Thông báo lỗi**: exception, lỗi binding, validation, error response hoặc diagnostic endpoint vô tình hiển thị giá trị nhạy cảm.

Mục tiêu cuối cùng không chỉ là “che vài ký tự khi in log”, mà là tạo một **chiến lược quản lý bí mật xuyên suốt vòng đời**: đưa bí mật vào ứng dụng an toàn hơn, dùng tối thiểu, tránh xuất ra các kênh quan sát, kiểm thử không rò rỉ và có kế hoạch xoay vòng khi sự cố xảy ra.

## 2. Phân biệt bí mật với cấu hình thông thường

Một số cấu hình có thể công khai trong phạm vi hệ thống:

~~~yaml
app:
  notification:
    enabled: true
    retry-count: 3
    connect-timeout: 5s
~~~

Nhưng cấu hình khác cần được bảo vệ:

~~~yaml
app:
  integration:
    endpoint: https://api.example.org
    api-key: "DEMO-NOT-A-REAL-SECRET"
~~~

Chuỗi `DEMO-NOT-A-REAL-SECRET` chỉ là **dữ liệu giả để học tập**, không phải credential có thể dùng. Trong production, không nên ghi API key thật trực tiếp vào YAML rồi commit vào Git.

Điểm đáng lưu ý: một property như `endpoint` có vẻ không nhạy cảm, nhưng URL thực tế có thể chứa username/password, token trong query string hoặc tham số ký. Vì vậy, không nên đánh giá một giá trị có an toàn để log **chỉ dựa vào tên field**.

Một ví dụ điển hình:

~~~text
https://user:password@example.org/api?access_token=secret
~~~

Cả phần userinfo và query parameter đều có thể tiết lộ thông tin xác thực. Một hệ thống log đầy đủ URL cũng có thể làm lộ bí mật dù không hề in field có tên `password`.

## 3. Những nơi bí mật có thể lan tới

Một bí mật ban đầu chỉ nằm trong một file hoặc kho bí mật. Khi được nạp vào ứng dụng, nó có thể đi qua nhiều lớp:

~~~text
Secret manager / mounted file / environment / CLI
                     |
                     v
           Spring Environment
                     |
                     v
      Binder / @Value / configuration bean
                     |
             +-------+--------+
             |       |        |
             v       v        v
        HTTP client  Logs   Exception
             |       |        |
             v       v        v
       Remote API  Log system  Error response
                     |
                     v
           Search, export, backup,
           dashboards, alerting
~~~

Mỗi bước tạo thêm một ranh giới tin cậy. Ví dụ:

- Secret manager có kiểm soát quyền truy cập chặt chẽ, nhưng log aggregator cho nhiều nhóm nhân viên xem.
- File secret chỉ được mount vào container, nhưng một stack trace được gửi sang công cụ giám sát bên ngoài.
- Người dùng cuối không thể đọc cấu hình, nhưng error handler trả nguyên văn exception message.
- Dữ liệu không được commit vào Git, nhưng đã tồn tại trong shell history hoặc job log của CI.

Vì vậy, câu hỏi bảo mật cần đặt ra là: **bí mật có thể được quan sát, sao chép, lưu trữ hoặc xuất hiện ngoài nơi sử dụng cần thiết hay không?**

## 4. Rủi ro thứ nhất: truyền bí mật bằng đối số dòng lệnh

Spring Boot hỗ trợ command-line properties:

~~~bash
java -jar app.jar --app.integration.api-key=DEMO-NOT-A-REAL-SECRET
~~~

Lệnh trên có thể bind property `app.integration.api-key` đúng cách. Nhưng về mặt bảo mật, nó có các rủi ro:

- Nội dung command line có thể xuất hiện trong công cụ quản lý process hoặc hệ thống inventory/monitoring.
- Shell có thể lưu lệnh vào history.
- Job runner hoặc CI/CD có thể hiển thị câu lệnh trong log.
- Tập lệnh khởi chạy có thể bị lưu vào repository, artifact hoặc backup.
- Công cụ chẩn đoán tiến trình có thể thu thập command-line arguments.
- Lệnh có thể bị copy vào ticket, chat hoặc tài liệu vận hành.

Khả năng quan sát arguments phụ thuộc hệ điều hành, quyền truy cập, namespace/container và cấu hình bảo vệ; **không phải mọi người dùng trên mọi máy đều xem được toàn bộ arguments**. Nhưng không nên đặt bí mật lên command line chỉ vì máy thử nghiệm hiện tại chưa cho người khác nhìn thấy.

Tương tự, Java system property:

~~~bash
java -Dapp.integration.api-key=DEMO-NOT-A-REAL-SECRET -jar app.jar
~~~

cũng có thể xuất hiện trong process command line. `-D` và `--app.integration.api-key=...` khác nhau về cơ chế cung cấp cấu hình, nhưng **đều có rủi ro bí mật nằm trong câu lệnh khởi chạy**.

**Nguyên tắc:** không dùng CLI arguments hoặc `-D` để truyền password/token thật nếu có phương án quản lý bí mật được hỗ trợ tốt hơn.

## 5. Shell history, script và môi trường phát triển

Một lệnh thủ công có thể được lưu lại:

~~~bash
java -jar app.jar --app.api-key=REAL_SECRET
~~~

Các nơi cần kiểm tra theo chính sách hệ thống:

- History của Bash, Zsh, PowerShell hoặc công cụ terminal.
- File script `run.sh`, `start.ps1`, batch file.
- IDE run configuration, launch configuration, debug profile.
- Task runner, Makefile, Gradle/Maven command-line options.
- Tài liệu copy/paste lệnh khởi động trong wiki hoặc chat.
- Session recording của máy chủ, terminal multiplexer hoặc hệ thống jump host.

Kể cả khi xóa một dòng khỏi history ở máy cá nhân, giá trị có thể đã được đồng bộ vào backup hoặc log trước đó. Vì vậy, **xóa dấu vết hiển thị không thay thế việc thu hồi và xoay vòng một bí mật đã lộ**.

Một lựa chọn tốt hơn là để runtime đọc bí mật từ nguồn quản lý được cấp quyền tại thời điểm triển khai, thay vì gõ giá trị thật vào lệnh. Tuy nhiên, nguồn thay thế cũng phải được đánh giá về quyền truy cập, lưu trữ và khả năng bị log.

## 6. Biến môi trường: thường hữu ích, nhưng không phải kho bí mật tuyệt đối

Spring Boot có thể ánh xạ biến môi trường vào cấu hình:

~~~text
APP_INTEGRATION_APIKEY
~~~

tương ứng với tên canonical:

~~~text
app.integration.api-key
~~~

Trong nhiều môi trường triển khai, đưa giá trị bằng biến môi trường tránh việc ghi trực tiếp secret vào file `application.yml` hoặc source code. Nhưng biến môi trường **không được mã hóa tự động chỉ vì tên là environment variable**.

Các rủi ro có thể có:

- Người có quyền phù hợp với process/container có thể đọc environment.
- Process con có thể thừa kế environment nếu ứng dụng hoặc script không giới hạn.
- Một số công cụ debug, crash dump, diagnostic hoặc container inspection có thể hiện environment.
- CI/CD có thể in environment nếu script chạy `env`, `printenv` hoặc xuất debug log.
- `System.getenv()` hoặc việc in cả map environment trong Java làm rò rỉ hàng loạt giá trị.
- Giá trị có thể được cấu hình trong manifest hoặc pipeline lưu trữ lâu dài.

Không bao giờ log:

~~~java
System.out.println(System.getenv());
~~~

Và tránh:

~~~java
log.debug("Environment variables: {}", System.getenv());
~~~

Khi sử dụng biến môi trường, cần hạn chế quyền đọc process/container, không truyền thừa cho subprocess không cần thiết, che log trong pipeline và tránh hiển thị nguyên cấu hình.

**Quan điểm cân bằng:** biến môi trường có thể là cơ chế cung cấp bí mật phù hợp cho một số nền tảng, nhưng không thay thế secret manager, phân quyền, kiểm soát log và rotation.

## 7. Không đặt secret trong `SPRING_APPLICATION_JSON` hoặc URI mà không đánh giá rủi ro

Spring Boot hỗ trợ nhiều cách cung cấp cấu hình; một trong số đó là `SPRING_APPLICATION_JSON`. Ví dụ dữ liệu giả:

~~~bash
SPRING_APPLICATION_JSON='{"app":{"integration":{"api-key":"DEMO-ONLY"}}}'
~~~

Cơ chế này tiện cho cấu hình có cấu trúc, nhưng nếu đưa secret thật vào JSON nằm trong biến môi trường hoặc command line, rủi ro của **kênh vận chuyển ban đầu** vẫn tồn tại.

Một vấn đề khác là URI import hoặc connection string:

~~~text
https://user:password@service.example.org/
jdbc:postgresql://database.example.org/app?password=secret
~~~

Ngay cả khi không có property tên `password` riêng, thông tin xác thực vẫn nằm trong chuỗi URL. Việc log nguyên URL, HTTP request target hoặc exception từ thư viện kết nối có thể làm rò rỉ chúng.

Khuyến nghị:

1. Ưu tiên cơ chế xác thực tách credential khỏi URL.
2. Không nhúng token vào query parameter nếu có cách truyền qua header bảo mật phù hợp với API.
3. Không log full connection string/URI nếu có thể chứa userinfo hoặc query nhạy cảm.
4. Khi cần hiển thị endpoint, tạo một biểu diễn an toàn chỉ chứa scheme, host và thông tin được phê duyệt.
5. Đừng cho rằng URL không có từ `secret` thì an toàn để in.

## 8. Rủi ro thứ hai: log trực tiếp giá trị cấu hình

Một lỗi phổ biến:

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

@Service
public class IntegrationService {
    private static final Logger log =
            LoggerFactory.getLogger(IntegrationService.class);

    public void connect(String apiKey) {
        log.info("Using API key: {}", apiKey); // KHÔNG AN TOÀN
    }
}
~~~

Dù sử dụng SLF4J parameterized logging thay vì nối chuỗi, giá trị `apiKey` vẫn được đưa vào log khi mức log tương ứng được bật. Cú pháp `{}` **không tự thực hiện redaction**.

Tương tự:

~~~java
log.debug("Configuration loaded: {}", properties);
log.error("Unable to authenticate with {}", token);
System.out.println("password=" + password);
~~~

nếu giá trị hoặc `properties.toString()` chứa bí mật.

Cách tốt hơn:

~~~java
log.info("Integration settings loaded; endpoint configured");
log.warn("Authentication failed for integration service");
~~~

Nếu cần nhận biết một cấu hình đã được cấp mà không tiết lộ giá trị:

~~~java
boolean credentialPresent =
        apiKey != null && !apiKey.isBlank();

log.info("Integration credential configured: {}", credentialPresent);
~~~

Tuy nhiên, cả trạng thái “credential có tồn tại” cũng cần được xem xét theo mức độ nhạy cảm của hệ thống. Trong đa số ứng dụng, log mức INFO cho một chỉ báo có/không là ít rủi ro hơn log nội dung secret.

## 9. Mức log DEBUG/TRACE không phải vùng an toàn

Có quan niệm rằng:

~~~java
log.debug("Token: {}", token);
~~~

sẽ an toàn vì production thường chạy với INFO.

Điều này không đáng tin cậy vì:

- DEBUG/TRACE có thể được bật tạm để chẩn đoán sự cố.
- Một cấu hình profile có thể vô tình bật log chi tiết trong production.
- Test/CI có thể chạy với log level thấp hơn.
- Một người vận hành có thể bật dynamic logging qua cơ chế quản trị được cấp quyền.
- Log phát ra có thể tồn tại lâu trong hệ thống tập trung hoặc backup.

Bí mật không nên xuất hiện trong log **ở bất kỳ level nào**, trừ khi có một quy trình bảo mật rất cụ thể, được kiểm soát và không xuất bản giá trị thô.

Đặc biệt thận trọng với:

~~~properties
logging.level.root=TRACE
logging.level.org.springframework.web=TRACE
logging.level.org.springframework.http=TRACE
~~~

những mức log sâu ở các thư viện liên quan đến HTTP, security, connection hoặc configuration. Một số thư viện có cơ chế tự che header/cookie nhạy cảm, nhưng **không nên dựa vào đó như biện pháp duy nhất**. Cần biết chính xác framework và version đang sử dụng log những gì.

## 10. HTTP request và response logging

Một REST client có thể gửi credential trong header:

~~~http
Authorization: Bearer DEMO-NOT-A-REAL-TOKEN
X-API-Key: DEMO-NOT-A-REAL-KEY
~~~

Nếu bật interceptor log toàn bộ request:

~~~java
log.debug("Headers: {}", request.getHeaders()); // KHÔNG AN TOÀN
~~~

thì header có thể bị lộ.

Một cách an toàn hơn là log các thông tin có ích nhưng không chứa credential:

~~~java
log.info(
        "Outbound request method={} targetHost={} status={}",
        method,
        approvedHost,
        status
);
~~~

Chỉ nên lấy `approvedHost` từ dữ liệu đã được kiểm soát, không phải in nguyên URL có thể chứa userinfo hoặc query. Với HTTP client, có thể dùng cấu hình log có **allowlist**: chỉ cho phép method, status, latency, một vài header không nhạy cảm và request ID.

Các dữ liệu nên được che hoặc loại khỏi log nếu có thể chứa secret:

- `Authorization`, `Proxy-Authorization`.
- `Cookie`, `Set-Cookie`.
- `X-API-Key` hoặc header credential riêng.
- Token trong query string.
- Body đăng nhập, password reset, OAuth token exchange.
- Multipart upload chứa dữ liệu bí mật.
- Response body có access token, refresh token hoặc password tạm.

Với `RestTemplate`, `WebClient`, Apache HTTP Client, OkHttp hoặc Feign, cần kiểm tra tùy chọn logging **của đúng client**. Một interceptor tự viết có thể làm mất tác dụng cơ chế redaction mặc định của thư viện.

## 11. Structured logging và MDC vẫn có thể làm lộ bí mật

Structured logging thường tạo bản ghi JSON:

~~~json
{
  "timestamp": "2026-11-12T09:00:00Z",
  "level": "INFO",
  "event": "external_call",
  "requestId": "req-123",
  "status": 200
}
~~~

Đây là cấu trúc dễ tìm kiếm và phân tích. Nhưng JSON không tự làm log an toàn.

Ví dụ nguy hiểm:

~~~java
MDC.put("apiKey", apiKey);
MDC.put("authorization", authorizationHeader);
~~~

Nếu log pattern hoặc JSON encoder được cấu hình xuất tất cả MDC, các giá trị này có thể xuất hiện trong mọi bản ghi của luồng xử lý.

Chỉ đưa vào MDC dữ liệu đã được đánh giá phù hợp, chẳng hạn correlation ID không chứa secret:

~~~java
MDC.put("requestId", requestId);
try {
    log.info("Processing integration request");
} finally {
    MDC.remove("requestId");
}
~~~

Tùy hệ thống, tenant ID, user ID hay request ID cũng có thể là dữ liệu nhạy cảm. Cần đánh giá quyền truy cập log và quy định lưu trữ thay vì coi chúng luôn công khai.

Không dùng tên field an toàn như `requestId` để cất token thực tế. Cơ chế redaction dựa trên tên khóa sẽ thất bại khi dữ liệu nhạy cảm bị đặt sai trường.

## 12. Vì sao “mask bằng regex ở log aggregator” chưa đủ?

Một số hệ thống cấu hình bộ lọc thay:

~~~text
password=abcdef
~~~

thành:

~~~text
password=******
~~~

Điều này hữu ích như **lớp bảo vệ bổ sung**, nhưng không bao phủ tất cả:

- Credential có thể không có tiền tố `password=`.
- Token có thể nằm trong URL, JSON, XML hoặc binary body.
- Giá trị có thể bị encode, rút gọn hoặc tách thành nhiều field.
- Một logger hoặc exporter có thể gửi dữ liệu đi trước khi bộ lọc chạy.
- Regex quá rộng có thể xóa thông tin vận hành cần thiết; quá hẹp thì bỏ sót.
- Log có thể được ghi xuống file cục bộ rồi mới được chuyển sang aggregator.

**Thứ tự ưu tiên:**

1. **Không tạo log chứa bí mật ngay từ code.**
2. Thiết kế log schema theo allowlist các trường được phép.
3. Che/loại bỏ header, cookie, query/body nhạy cảm tại điểm ghi log.
4. Áp dụng bộ lọc redaction ở logging framework và pipeline như lớp bổ sung.
5. Kiểm thử bằng secret giả và quan sát cả log cục bộ lẫn đầu ra aggregator.

Không xem một quy tắc regex là bảo đảm tuyệt đối rằng mọi bí mật đã bị loại khỏi hệ thống logging.

## 13. Rủi ro thứ ba: `toString()` của Java object

Một đối tượng cấu hình có thể chứa thông tin nhạy cảm:

~~~java
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.integration")
public record IntegrationProperties(
        String endpoint,
        String apiKey
) {}
~~~

Java record tự sinh `toString()` hiển thị các component. Nếu viết:

~~~java
log.info("Integration properties: {}", properties);
~~~

`toString()` có thể tạo chuỗi gồm `endpoint` và **apiKey thật**. Dù log statement không gọi `properties.apiKey()` trực tiếp, bí mật vẫn có thể bị lộ.

Ví dụ kết quả giả lập:

~~~text
IntegrationProperties[endpoint=https://api.example.org,
apiKey=DEMO-NOT-A-REAL-SECRET]
~~~

Rủi ro tương tự xảy ra với:

- `@Data` hoặc `@ToString` của Lombok.
- IDE-generated `toString()`.
- Kotlin data class với `toString()` tự sinh.
- Thư viện debug/diagnostic chuyển object sang chuỗi.
- String interpolation: `"config=" + properties`.
- Exception message chứa `properties` hoặc DTO.

**Nguyên tắc:** một object có chứa credential không nên được log nguyên vẹn.

## 14. Khắc phục `toString()` trên Java record

Một cách đơn giản là override `toString()`:

~~~java
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.integration")
public record IntegrationProperties(
        String endpoint,
        String apiKey
) {
    @Override
    public String toString() {
        return "IntegrationProperties[endpoint=<omitted>, apiKey=<redacted>]";
    }
}
~~~

Tại đây:

- Giá trị thật của `apiKey` không được đưa vào chuỗi.
- `endpoint` cũng được ẩn để tránh trường hợp URL chứa userinfo hoặc query nhạy cảm.
- Chuỗi vẫn cho biết object đang được mô tả, nhưng không công bố nội dung.

Một cách khác là **không log object cấu hình** và chỉ ghi những trường được allowlist, ví dụ:

~~~java
log.info("Integration configuration initialized");
~~~

Ngay cả khi override `toString()` an toàn, bí mật vẫn tồn tại trong object và vẫn có thể bị truy xuất qua getter, reflection, debugger hoặc serializer. Override `toString()` chỉ bảo vệ **một đường xuất dữ liệu**, không phải mã hóa hay ẩn secret khỏi mọi API.

Nếu một record chứa collection hoặc nested object có secret, không được gọi `nested.toString()` từ implementation tùy chỉnh một cách vô ý.

## 15. Lombok: `@Data` và `@ToString` cần được xem xét

Lombok giúp giảm boilerplate:

~~~java
import lombok.Data;

@Data
public class ApiCredentials {
    private String clientId;
    private String clientSecret;
}
~~~

Nhưng `@Data` bao gồm hành vi sinh `toString()`; object có thể in cả `clientSecret` nếu không có cấu hình loại trừ.

Một cách giảm rủi ro:

~~~java
import lombok.Getter;
import lombok.Setter;
import lombok.ToString;

@Getter
@Setter
@ToString(onlyExplicitlyIncluded = true)
public class ApiCredentials {

    @ToString.Include
    private String clientId;

    private String clientSecret;
}
~~~

Chỉ đưa `clientId` vào `toString()` nếu nó không nhạy cảm theo mô hình threat của dự án. Nếu ngay cả identifier cũng phải ẩn, không include bất kỳ dữ liệu nào.

Có thể dùng `@ToString.Exclude` cho field nhạy cảm:

~~~java
@Getter
@Setter
@ToString
public class ApiCredentials {

    private String clientId;

    @ToString.Exclude
    private String clientSecret;
}
~~~

Tuy nhiên, **allowlist** thường an toàn hơn blacklist: khi developer thêm một field `refreshToken` mới, quy tắc `onlyExplicitlyIncluded = true` sẽ không tự công bố field đó.

Không quên kiểm tra `toString()` của các nested object/DTO, không chỉ class cấu hình gốc.

## 16. `equals()`, `hashCode()` và serialization cũng cần đánh giá riêng

Lombok `@Data` hoặc Java record có thể sinh `equals()` và `hashCode()` dựa trên component. Chúng không tự log bí mật, nhưng có thể xử lý dữ liệu credential theo những cách không phù hợp với mục đích an toàn hoặc gây rò rỉ gián tiếp qua instrumentation.

Đặc biệt, **ẩn field khỏi `toString()` không đồng nghĩa ẩn khỏi JSON serialization**:

~~~java
public record IntegrationProperties(
        String apiKey
) {
    @Override
    public String toString() {
        return "IntegrationProperties[apiKey=<redacted>]";
    }
}
~~~

Nếu một controller vô tình trả object này:

~~~java
@GetMapping("/config")
public IntegrationProperties config() {
    return properties;
}
~~~

Jackson có thể serialize component `apiKey` thành JSON, tùy cấu hình mapper. `toString()` an toàn **không ngăn được** việc object bị trả qua HTTP response.

Phòng tránh:

- Không trả trực tiếp configuration bean chứa secret từ controller.
- Tạo response DTO riêng với allowlist các trường được phép.
- Dùng `@JsonIgnore` tại nơi phù hợp nếu phải serialize một object có field nhạy cảm, nhưng không xem nó như hàng rào duy nhất.
- Tránh endpoint debug tùy biến trả toàn bộ `Environment` hoặc `@ConfigurationProperties`.
- Kiểm tra serialization của nested object và map, không chỉ top-level.

## 17. Thiết kế object cấu hình với ranh giới an toàn

Một cách làm là tách phần cấu hình dùng để vận hành khỏi credential:

~~~yaml
app:
  integration:
    base-url: https://api.example.org
    connect-timeout: 5s
    api-key: "${INTEGRATION_API_KEY}"
~~~

Java:

~~~java
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.integration")
public record IntegrationProperties(
        String baseUrl,
        Duration connectTimeout,
        String apiKey
) {
    @Override
    public String toString() {
        return "IntegrationProperties[baseUrl=<omitted>, "
                + "connectTimeout=" + connectTimeout
                + ", apiKey=<redacted>]";
    }
}
~~~

`${INTEGRATION_API_KEY}` là placeholder Spring, không phải lời khuyên đặt giá trị bí mật vào `application.yml`. Cách cung cấp thực tế có thể là environment hoặc secret source an toàn hơn.

Tuy nhiên, trong một ứng dụng lớn, việc có cùng một object chứa cả cấu hình công khai và secret làm tăng nguy cơ người khác log cả object. Có thể cân nhắc:

~~~java
public record PublicIntegrationOptions(
        Duration connectTimeout
) {}

public final class IntegrationCredential {
    private final String apiKey;

    public IntegrationCredential(String apiKey) {
        this.apiKey = apiKey;
    }

    public String value() {
        return apiKey;
    }

    @Override
    public String toString() {
        return "IntegrationCredential[redacted]";
    }
}
~~~

Class `IntegrationCredential` vẫn có method `value()` để tích hợp với HTTP client. Nó không ngăn mọi cách rò rỉ, nhưng làm cho việc log object không vô tình công bố nội dung ngay lập tức.

Với secret có vòng đời đặc biệt, nên hạn chế phạm vi truy cập bằng cách inject credential chỉ vào thành phần thực sự cần sử dụng.

## 18. Rủi ro thứ tư: thông báo lỗi và exception

Một lỗi thường gặp khi gọi API:

~~~java
try {
    callPartner(apiKey);
} catch (RuntimeException ex) {
    throw new IllegalStateException(
            "Partner API failed with key=" + apiKey, ex
    );
}
~~~

Câu lệnh trên tạo exception message chứa credential. Khi exception được log bằng:

~~~java
log.error("Partner integration failed", exception);
~~~

hoặc trả lỗi ra HTTP, bí mật có thể bị công bố.

Thay bằng thông báo không chứa dữ liệu bí mật:

~~~java
try {
    callPartner(apiKey);
} catch (PartnerAuthenticationException ex) {
    log.warn("Partner authentication failed; code={}", ex.errorCode());
    throw new IntegrationUnavailableException(
            "Partner authentication failed"
    );
}
~~~

Ở đây `ex.errorCode()` phải là một mã lỗi **được allowlist và không chứa secret**, không phải thông điệp thô tùy ý của remote service. Các class exception trong ví dụ là class do ứng dụng tự định nghĩa.

Việc giữ nguyên `cause` đôi khi cần thiết cho chẩn đoán, nhưng **cause chain cũng có thể chứa credential**. Nếu biết exception gốc chứa dữ liệu nhạy cảm, đừng mặc định log full stack trace ở kênh truy cập rộng. Hãy tách cơ chế chẩn đoán có quyền kiểm soát hoặc chuẩn hóa thông báo tại ranh giới phù hợp.

Không nên giải quyết bằng cách nuốt mọi exception và trả một kết quả thành công giả; cần giữ tín hiệu lỗi và thông tin hữu ích nhưng không lộ secret.

## 19. Không nối nguyên văn remote response vào exception

Một HTTP client có thể nhận lỗi như:

~~~json
{
  "error": "invalid_token",
  "detail": "Token DEMO-NOT-A-REAL-TOKEN was rejected"
}
~~~

Nếu ứng dụng viết:

~~~java
throw new IllegalStateException(
        "Remote API error: " + responseBody
);
~~~

nó có thể chuyển secret từ response body sang exception message, rồi lan sang log, alert và error response.

Hướng xử lý:

1. Parse response theo schema đã biết.
2. Chỉ ghi **mã lỗi hoặc trạng thái** được chấp thuận.
3. Không hiển thị toàn bộ response body cho người dùng cuối.
4. Nếu cần chẩn đoán sâu, dùng cơ chế lưu trữ được bảo vệ và có redaction đã kiểm thử.
5. Tránh sử dụng `ex.getMessage()` làm nội dung response công khai.

Ví dụ:

~~~java
log.warn(
        "Partner request rejected: status={}, category={}",
        statusCode,
        safeCategory
);
~~~

`safeCategory` phải được ánh xạ từ một tập giá trị xác định như `AUTHENTICATION`, `RATE_LIMIT` hoặc `REMOTE_ERROR`. Không coi một chuỗi bất kỳ từ phía bên kia là an toàn chỉ vì nó có tên `errorCode`.

## 20. Spring Boot binding failure có thể chứa dữ liệu cấu hình

Một class cấu hình:

~~~java
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.integration")
public record IntegrationProperties(
        Duration timeout,
        String apiKey
) {}
~~~

Nếu một property có giá trị sai kiểu:

~~~properties
app.integration.timeout=not-a-duration
~~~

quá trình bind `Duration` có thể thất bại. Tùy phiên bản Spring Boot, thông báo lỗi có thể hiển thị:

- Tên property.
- Giá trị gây lỗi.
- Kiểu Java đích.
- Origin (ví dụ tên file và dòng).
- Nguyên nhân chuyển đổi hoặc validation.

Với property bình thường, thông tin này hữu ích. Nhưng nếu trường được bind là secret, **không nên giả định mọi exception đều tự động ẩn giá trị**.

Ví dụ nên tránh trong custom error handler:

~~~java
catch (Exception e) {
    log.error("Configuration failure: {}", e.getMessage());
}
~~~

nếu `e.getMessage()` có thể chứa nội dung property nhạy cảm.

Một số thành phần Spring Boot có chức năng sanitize cho diagnostic endpoints; đây không phải bảo đảm rằng **mọi đường exception hoặc mọi logger tùy biến** đều sanitize theo cùng chính sách.

Không xây dựng hệ thống bảo mật dựa trên việc tin rằng một từ khóa như `password` chắc chắn sẽ được che trong toàn bộ stack.

## 21. Bean Validation và thông điệp constraint

Có thể dùng `@Validated` để từ chối cấu hình không hợp lệ:

~~~java
import jakarta.validation.constraints.NotBlank;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app.integration")
public record IntegrationProperties(
        @NotBlank String apiKey
) {}
~~~

Nếu `apiKey` trống, validation có thể thất bại khi bean được tạo. Đây là cách bảo vệ tính hiện diện của credential, **không phải cách bảo vệ giá trị khỏi log**.

Một số báo cáo validation hoặc công cụ error reporting có thể hiển thị rejected value tùy đường xử lý. Vì vậy:

- Không đưa secret vào message template của constraint.
- Không viết custom validator ném exception chứa secret.
- Không log toàn bộ validation error object nếu nó có thể giữ giá trị bị từ chối.
- Tránh hiển thị rejected value ra API hoặc giao diện người dùng.
- Bảo đảm logging cấu hình startup không vô tình phơi bày secret.

Ví dụ constraint message nên đơn giản:

~~~java
@NotBlank(message = "Integration credential must be configured")
String apiKey
~~~

Không viết message theo mẫu mô tả lại giá trị thật của `apiKey`.

## 22. Error response: không trả exception message trực tiếp cho client

Ví dụ controller exception handler nguy hiểm:

~~~java
@RestControllerAdvice
public class UnsafeErrorHandler {

    @ExceptionHandler(Exception.class)
    public ResponseEntity<String> handle(Exception ex) {
        return ResponseEntity
                .internalServerError()
                .body(ex.getMessage()); // KHÔNG AN TOÀN
    }
}
~~~

Nếu một exception trong tầng thấp chứa password, token hoặc connection string, người gọi API có thể nhận được giá trị đó.

Hướng an toàn hơn:

~~~java
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class ApiErrorHandler {

    @ExceptionHandler(IntegrationUnavailableException.class)
    public ResponseEntity<ApiError> handleIntegrationFailure(
            IntegrationUnavailableException ex) {

        return ResponseEntity
                .status(HttpStatus.BAD_GATEWAY)
                .body(new ApiError(
                        "UPSTREAM_UNAVAILABLE",
                        "Dịch vụ tích hợp tạm thời không khả dụng"
                ));
    }

    public record ApiError(String code, String message) {}
}
~~~

Cần khai báo `IntegrationUnavailableException` như exception của ứng dụng. Quan trọng là response chỉ có **mã lỗi ổn định** và **thông báo được cho phép**, không lấy nguyên văn message/cause từ thư viện hoặc remote system.

Với các loại exception khác, sử dụng một handler phù hợp và không trả stack trace trong production. Không nên gửi nguyên object `Exception` hoặc `Throwable` về client.

## 23. Spring Boot error endpoint và stack trace

Spring Boot cung cấp cơ chế xử lý lỗi cho web application. Các tùy chọn như việc đưa message, binding errors hoặc stack trace vào error response khác nhau theo phiên bản và cấu hình.

Với production, ưu tiên không xuất stack trace và chi tiết exception nội bộ ra response. Ví dụ cấu hình minh họa cho Spring Boot 3.x:

~~~yaml
server:
  error:
    include-message: never
    include-stacktrace: never
    include-binding-errors: never
~~~

Các tùy chọn này giúp giảm thông tin trong error response mặc định, nhưng **không tự kiểm soát mọi custom `@RestControllerAdvice`**, logger hoặc thư viện bên thứ ba.

Một custom exception handler có thể bỏ qua các thiết lập trên và trả `ex.getMessage()` dù default error endpoint đang được cấu hình an toàn.

Do đó cần kiểm thử các đường lỗi thực tế, đặc biệt:

- Lỗi xác thực với upstream.
- Lỗi JDBC/Redis connection.
- Lỗi bind configuration lúc startup.
- Lỗi parse token.
- Lỗi validation.
- Lỗi không mong đợi ở controller.

Mục tiêu là client nhận được thông tin đủ để biết request thất bại, nhưng không nhận credential hoặc chi tiết nội bộ không cần thiết.

## 24. Actuator `env` và `configprops`

Spring Boot Actuator có các endpoint phục vụ quan sát cấu hình. Hai endpoint đáng lưu ý:

- `/actuator/env`: thông tin về environment/property sources.
- `/actuator/configprops`: các bean `@ConfigurationProperties` và giá trị cấu hình tương ứng trong phạm vi endpoint cho phép.

Spring Boot có cơ chế sanitize và chính sách hiển thị giá trị cho các endpoint này, nhưng **không nên coi việc có sanitizer là đủ để mở chúng công khai trên internet**.

Ví dụ cấu hình hạn chế exposure:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info
  endpoint:
    env:
      show-values: never
    configprops:
      show-values: never
~~~

Ý nghĩa:

- Web exposure chỉ cho phép nhóm endpoint cần thiết trong ví dụ.
- Chính sách hiển thị giá trị của `env` và `configprops` được đặt nghiêm ngặt.
- Các endpoint khác, như `heapdump` hoặc công cụ chẩn đoán, cần được kiểm soát riêng nếu có bật.

Tên thuộc tính và hành vi chi tiết có thể khác theo phiên bản Spring Boot/Actuator. Khi triển khai, đọc tài liệu của **phiên bản đang chạy** và kiểm tra cấu hình bảo mật thực tế.

Ngay cả khi một endpoint chỉ hiện tên property mà không hiện giá trị, tên cũng có thể tiết lộ cấu trúc hệ thống. Giới hạn truy cập, bảo vệ network và quan sát audit vẫn cần thiết.

## 25. Các endpoint chẩn đoán khác cũng có thể chứa bí mật

Không chỉ `env` và `configprops`. Một số công cụ hỗ trợ vận hành có thể cung cấp:

- Heap dump.
- Thread dump.
- System diagnostics.
- Runtime metrics với tag/label tùy chỉnh.
- HTTP trace/observation thông tin request.
- Log level management.
- Profiling và crash report.

Heap dump có thể chứa chuỗi bí mật còn nằm trong bộ nhớ JVM. Một metric label chứa token hoặc tên khách hàng cũng có thể lộ dữ liệu, đồng thời tạo cardinality không kiểm soát.

Khi bật các công cụ này:

1. Xác định ai có thể truy cập.
2. Giới hạn mạng và authentication/authorization.
3. Giới hạn nơi lưu file dump/report.
4. Định nghĩa retention và quy trình xóa.
5. Không đưa secret vào metric tag hoặc trace attribute.
6. Giám sát việc tải xuống artifact chẩn đoán.

Việc một giá trị đã được che khỏi `toString()` không có nghĩa nó sẽ biến mất khỏi bộ nhớ JVM. Redaction của log và bảo vệ memory dump là hai lớp khác nhau.

## 26. Dùng Config Data và file secret được mount

Một lựa chọn vận hành là đưa bí mật vào file được mount với quyền hạn phù hợp và cho Spring Boot đọc qua **configuration tree**.

Ví dụ cấu trúc:

~~~text
/run/secrets/
  app.integration.api-key
~~~

Nội dung file `/run/secrets/app.integration.api-key` là **giá trị bí mật** (không phải tên property). Trong YAML ứng dụng:

~~~yaml
spring:
  config:
    import: "optional:configtree:/run/secrets/"
~~~

Khi nguồn config tree được nạp và đặt tên phù hợp, tên file `app.integration.api-key` có thể trở thành property để Binder sử dụng:

~~~java
@Value("${app.integration.api-key}")
private String apiKey;
~~~

Ví dụ này chỉ minh họa cơ chế nạp. Cần lưu ý:

- File secret không được commit vào repository.
- Mount nên có quyền đọc tối thiểu, phù hợp với user của process.
- Tránh để file secret trong thư mục được web server hoặc static resource handler phục vụ.
- Không log đường dẫn kèm nội dung hoặc dump cả thư mục.
- Dùng cơ chế quản lý secret của nền tảng để cấp/thu hồi/xoay vòng.
- `optional:` cho phép import không có mà không làm lỗi tìm vị trí; **điều đó không tự làm credential trở thành tùy chọn**. Với secret bắt buộc, dùng validation hoặc bỏ `optional:` tùy hợp đồng triển khai.

Tùy OS, container và cách mount, file secret vẫn có thể bị đọc bởi process có đủ quyền hoặc bị đưa vào backup/diagnostic. Mounted file an toàn hơn CLI trong nhiều bối cảnh, nhưng không tự loại bỏ mọi rủi ro.

## 27. Docker: tránh secret trong image và câu lệnh build

Các cách dễ làm lộ secret:

~~~dockerfile
# KHÔNG AN TOÀN - ví dụ cần tránh
ENV APP_INTEGRATION_APIKEY=REAL_SECRET
~~~

hoặc:

~~~dockerfile
# KHÔNG AN TOÀN - ví dụ cần tránh
ARG API_KEY
RUN echo "$API_KEY" > /opt/app/key.txt
~~~

Những giá trị này có thể xuất hiện trong image layer, build cache, metadata, history hoặc artifact tùy cách build.

Nguyên tắc:

- Không bake secret thật vào container image.
- Không commit `.env` chứa credential thật vào Git.
- Không truyền secret qua build argument thông thường khi nó có thể lưu dấu trong metadata/layer.
- Với nhu cầu secret chỉ dùng ở build time, dùng cơ chế **build secret mount** được nền tảng hỗ trợ và kiểm tra artifact đầu ra.
- Với runtime, dùng secret store hoặc mount phù hợp thay vì đưa vào Dockerfile.

Ví dụ ý tưởng runtime mount:

~~~text
Container filesystem:
/run/secrets/app.integration.api-key
~~~

Ứng dụng đọc qua Config Data như phần trước. Secret không cần nằm trong image để ứng dụng khởi động.

Cần bảo vệ cả host/container runtime, nơi mount file, quyền đọc và công cụ inspection. Việc dùng một thư mục tên `/run/secrets` không tự mang lại quyền bảo vệ nếu file được cấp quyền quá rộng.

## 28. Kubernetes Secret và những hiểu lầm thường gặp

Kubernetes hỗ trợ resource `Secret` để cấp dữ liệu nhạy cảm cho Pod dưới dạng environment variable hoặc volume mount. Nhưng cần hiểu:

- Giá trị `data` trong YAML Secret được biểu diễn bằng Base64; **Base64 không phải mã hóa bảo mật**.
- Quyền đọc Kubernetes Secret thông qua API cần được giới hạn bằng RBAC.
- Nên xem xét mã hóa at rest trong etcd theo chính sách cluster.
- Manifest chứa giá trị đã encode vẫn không nên được chia sẻ tùy tiện.
- Environment injection có rủi ro riêng về process environment.
- Volume mount cần bảo vệ filesystem permissions và phạm vi Pod.

Ví dụ Pod đọc secret được mount làm file:

~~~yaml
apiVersion: v1
kind: Pod
metadata:
  name: integration-demo
spec:
  containers:
    - name: app
      image: example/integration:1.0
      volumeMounts:
        - name: app-secrets
          mountPath: /run/secrets
          readOnly: true
  volumes:
    - name: app-secrets
      secret:
        secretName: integration-credentials
~~~

Đây là ví dụ cho đường mount, giả định resource `Secret` đã tồn tại và ứng dụng/định dạng file được cấu hình phù hợp. Trên hệ thống thật, cần triển khai thêm security context, service account, RBAC, image hardening và network policies theo yêu cầu.

Nếu ứng dụng dùng `spring.config.import=configtree:/run/secrets/`, cần bảo đảm tên file trong Secret volume tạo ra đúng tên property muốn bind, hoặc dùng cơ chế mapping key-to-path thích hợp.

## 29. Secret manager: tách vòng đời credential khỏi source code

Khi nền tảng hỗ trợ, một kho bí mật chuyên dụng có thể cung cấp:

- Phân quyền truy xuất theo workload identity.
- Audit truy cập.
- Versioning và rotation.
- TTL hoặc short-lived credentials.
- Quản lý khóa mã hóa.
- Chính sách thu hồi khi sự cố.

Các hệ thống có thể dùng cơ chế tích hợp riêng để nạp secret vào Spring Boot, ví dụ Config Data integration, mounted file, SDK hoặc sidecar.

Tuy nhiên, việc dùng secret manager **không tự làm code an toàn**. Sau khi nạp vào JVM, giá trị vẫn có thể bị:

~~~java
log.info("secret={}", secret);
~~~

hoặc:

~~~java
throw new RuntimeException("secret=" + secret);
~~~

đưa ra kênh không được phép.

Vì vậy, secret manager xử lý **nguồn cấp và quản trị credential**; ứng dụng vẫn phải đảm bảo **sử dụng và không xuất tiết lộ** qua các kênh logging, serialization và error handling.

## 30. Cấu hình theo profile không được dùng để che secret trong repository

Có thể có các file:

~~~text
application.yml
application-dev.yml
application-test.yml
application-prod.yml
~~~

Một lỗi thiết kế:

~~~yaml
# application-prod.yml - KHÔNG AN TOÀN
app:
  integration:
    api-key: "REAL_PRODUCTION_SECRET"
~~~

Rồi nghĩ rằng file chỉ được dùng khi profile production hoạt động nên không ai khác thấy nó. Thực tế, file vẫn có thể:

- Được commit vào Git.
- Có mặt trong build artifact.
- Được đóng gói vào JAR.
- Được sao chép sang môi trường khác.
- Bị đọc bởi người có quyền truy cập repository hoặc artifact.

Profile ảnh hưởng đến **cấu hình được kích hoạt khi chạy**, không phải ranh giới bảo mật của bí mật trong source code.

Một cấu hình tốt hơn là để các file profile chỉ giữ các setting không nhạy cảm, còn credential được cấp qua cơ chế triển khai:

~~~yaml
app:
  integration:
    connect-timeout: 5s
    api-key: "${INTEGRATION_API_KEY}"
~~~

Và dùng validation để từ chối thiếu key bắt buộc. Nếu xuất hiện secret trong Git, việc xóa nó ở commit mới không đủ; cần đánh giá toàn bộ lịch sử và thực hiện rotation.

## 31. Ghi log các thuộc tính cấu hình “đã nạp thành công” sao cho an toàn

Một log startup thường được viết như:

~~~java
log.info("Loaded config: {}", properties);
~~~

Điều này tiện nhưng rủi ro nếu class có thêm credential trong tương lai.

Thay bằng một log theo allowlist:

~~~java
log.info(
        "Integration config ready; timeoutSeconds={} featureEnabled={}",
        properties.connectTimeout().toSeconds(),
        properties.featureEnabled()
);
~~~

Giả định `connectTimeout` và `featureEnabled` được phê duyệt là không nhạy cảm. Không đưa `apiKey` vào log.

Một biến thể tốt hơn là tạo method hoặc DTO dành riêng cho diagnostic:

~~~java
public record IntegrationDiagnostics(
        boolean configured,
        long timeoutSeconds
) {}
~~~

Trong service:

~~~java
IntegrationDiagnostics diagnostics =
        new IntegrationDiagnostics(
                credential != null && !credential.isBlank(),
                properties.connectTimeout().toSeconds()
        );

log.info("Integration diagnostics: {}", diagnostics);
~~~

Nếu ngay cả trạng thái `configured` là thông tin nhạy cảm, loại nó khỏi diagnostic. “Allowlist” có nghĩa chỉ ghi những thông tin đã được đánh giá và thật sự cần thiết.

Không nên tạo diagnostic object chứa secret rồi dùng `@JsonIgnore` để “cứu” mọi đường log, vì `toString()` và JSON serialization là hai cơ chế khác nhau.

## 32. Không dùng hash thông thường để thay thế secret trong log một cách tùy tiện

Có đề xuất:

~~~java
log.info("apiKeyHash={}", sha256(apiKey));
~~~

để tiện đối chiếu cùng một credential giữa các request.

Cách này có thể giảm việc in secret trực tiếp, nhưng **không phải lúc nào cũng an toàn**:

- Secret có entropy thấp có thể bị tấn công đoán giá trị qua hash.
- Hash ổn định có thể trở thành định danh theo dõi giữa nhiều hệ thống.
- Log vẫn có thể công bố mối liên hệ giữa các request sử dụng cùng credential.
- Một số dữ liệu nhạy cảm, như mã OTP ngắn, không nên được đưa vào hash công khai vì có thể brute-force.

Nếu thật sự cần correlation, ưu tiên một identifier không nhạy cảm được cấp riêng, hoặc dùng cơ chế HMAC có khóa được quản lý thích hợp và thiết kế threat model rõ ràng. Trong nhiều trường hợp, chỉ cần request ID là đủ.

Không log password, API key, token ở dạng nguyên văn, Base64, hoặc “mã hóa” tự chế. **Base64 là encoding, không phải redaction.**

## 33. Exception `toString()` và nested cause chain

Một exception có thể in thông tin theo nhiều cách:

~~~java
log.error("Failure: {}", exception);
log.error("Failure", exception);
throw new IllegalStateException("Failure", exception);
~~~

Các cách trên không tương đương hoàn toàn:

- `exception.toString()` thường gồm class name và message.
- Logger có throwable argument có thể xuất stack trace và các cause lồng nhau.
- Một exception được bọc bằng cause vẫn giữ thông tin từ exception gốc, có thể bị log về sau.

Ví dụ lỗi JDBC hoặc HTTP client đôi khi có message chứa URI, query, header hoặc response body. Không thể giả định thư viện nào cũng không in dữ liệu nhạy cảm.

Giải pháp là **giảm việc đưa dữ liệu nhạy cảm vào exception từ đầu**, dùng code lỗi an toàn, và hạn chế nơi xuất full stack trace. Với sự cố cần forensic sâu, quy trình bảo mật riêng có thể lưu thông tin chẩn đoán ở hệ thống hạn chế quyền truy cập và retention, nhưng cũng phải đánh giá việc thu thập bí mật có thật sự cần thiết hay không.

## 34. Thiết kế một lớp exception an toàn

Một lớp exception nghiệp vụ có thể chỉ giữ mã lỗi và message cố định:

~~~java
public final class IntegrationUnavailableException
        extends RuntimeException {

    private final String errorCode;

    public IntegrationUnavailableException() {
        super("External integration is temporarily unavailable");
        this.errorCode = "UPSTREAM_UNAVAILABLE";
    }

    public String errorCode() {
        return errorCode;
    }
}
~~~

Trong service:

~~~java
try {
    remoteClient.call();
} catch (RemoteClientException e) {
    log.warn("Upstream call failed; code=UPSTREAM_UNAVAILABLE");
    throw new IntegrationUnavailableException();
}
~~~

Mã ví dụ giả định có `RemoteClientException` và `remoteClient` do dự án cung cấp. Lớp exception an toàn không giữ secret trong message.

Nhưng đừng dùng một message cố định rồi đánh mất hoàn toàn khả năng debug: có thể log request ID, service name đã cho phép, status code, latency và category. Những thông tin này thường đủ để liên kết sự kiện với hệ thống quan sát có quyền truy cập.

Một nguyên tắc: **exception message và API error message nên được xem là nội dung có thể bị phân phối rộng**, không phải vị trí để chứa dữ liệu cần giữ bí mật.

## 35. Đọc cấu hình bằng `@Value` hoặc `@ConfigurationProperties` đều có rủi ro xuất dữ liệu

Hai cách:

~~~java
@Value("${app.integration.api-key}")
private String apiKey;
~~~

và:

~~~java
@ConfigurationProperties(prefix = "app.integration")
public record IntegrationProperties(String apiKey) {}
~~~

đều có thể đưa secret vào bộ nhớ JVM. Chọn một trong hai không tự giải quyết vấn đề log.

`@ConfigurationProperties` có lợi cho schema cấu hình, binding có kiểu, validation và khả năng kiểm thử. Nhưng Java record auto `toString()` có thể làm xuất lộ credential nếu log cả record.

`@Value` thường đơn giản cho một scalar, nhưng nếu logger được viết ngay tại class chứa field:

~~~java
log.debug("apiKey={}", apiKey);
~~~

thì vẫn rò rỉ.

Mục tiêu bảo mật phải đặt ở **quy trình sử dụng dữ liệu**, không chỉ ở annotation đọc property.

## 36. Tránh in toàn bộ `Environment` và `PropertySource`

Một số công cụ debug viết:

~~~java
for (PropertySource<?> source : environment.getPropertySources()) {
    log.debug("Source: {}", source);
}
~~~

Ngay cả khi cách `toString()` cụ thể của một `PropertySource` không in mọi giá trị, kiểu debug này vẫn không phải ý tưởng tốt nếu code bắt đầu duyệt và log toàn bộ khóa/giá trị.

Ví dụ thực sự nguy hiểm:

~~~java
for (String key : knownPropertyNames) {
    log.info("{}={}", key, environment.getProperty(key));
}
~~~

Nếu danh sách chứa `app.integration.api-key`, nó bị log thẳng.

Hãy ưu tiên:

~~~java
log.info("Configuration initialized successfully");
~~~

Hoặc xuất một danh sách **tên property được phê duyệt** mà không có giá trị, nếu chỉ cần chẩn đoán key nào có mặt. Đối với secret, ngay cả tên property hoặc trạng thái tồn tại cũng cần đánh giá độ nhạy cảm và quyền truy cập log.

Không viết một utility “dump all config” để dùng trong production chỉ vì nó giúp debug nhanh ở môi trường local.

## 37. Kiểm thử không rò rỉ bằng `OutputCaptureExtension`

Spring Boot Test có `OutputCaptureExtension` để bắt output trong test, hữu ích cho việc xác nhận một đường log **không chứa secret giả**.

Ví dụ Java:

~~~java
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.boot.test.system.CapturedOutput;
import org.springframework.boot.test.system.OutputCaptureExtension;

import static org.assertj.core.api.Assertions.assertThat;

@ExtendWith(OutputCaptureExtension.class)
class SafeLoggingTest {

    @Test
    void shouldNotLogSecret(CapturedOutput output) {
        String fakeSecret = "TEST_ONLY_SENTINEL_KEY_12345";

        IntegrationCredential credential =
                new IntegrationCredential(fakeSecret);

        System.out.println("Credential object: " + credential);

        assertThat(output.getOut())
                .doesNotContain(fakeSecret);
    }
}
~~~

Ví dụ này kiểm tra `toString()` của `IntegrationCredential` ở phần trên; implementation của nó trả chuỗi `[redacted]`.

Test dùng sentinel là giá trị giả, **không bao giờ dùng credential thật trong test log**. Có thể dùng một chuỗi giả duy nhất dễ nhận dạng để tìm rò rỉ trong nhiều đường xuất dữ liệu.

Lưu ý: `CapturedOutput` chỉ quan sát những stream/log đã được gắn vào hạ tầng output của test. Nếu ứng dụng dùng custom appender, exporter bất đồng bộ hoặc gửi log đến dịch vụ từ xa, cần test riêng cho các đường đó.

## 38. Test `toString()` và serializer tách biệt

Một test `toString()`:

~~~java
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

class IntegrationPropertiesTest {

    @Test
    void toStringMustNotExposeSecret() {
        String fakeSecret = "TEST_ONLY_SENTINEL_SECRET";

        IntegrationProperties props = new IntegrationProperties(
                "https://api.example.org",
                fakeSecret
        );

        assertThat(props.toString())
                .doesNotContain(fakeSecret);
        assertThat(props.toString())
                .contains("<redacted>");
    }
}
~~~

Để test trên đúng, class `IntegrationProperties` phải có override `toString()` đã định nghĩa ở phần 14.

Nhưng test này **chưa kiểm tra JSON**. Với Jackson hoặc framework serializer mà ứng dụng dùng, cần một test độc lập:

~~~java
String json = objectMapper.writeValueAsString(props);

assertThat(json).doesNotContain(fakeSecret);
~~~

Nếu serializer vẫn xuất `apiKey`, cần sửa API DTO hoặc cấu hình serialization thay vì chỉ chỉnh `toString()`.

Với error response, thêm integration test gọi endpoint gây lỗi rồi assert:

~~~java
assertThat(responseBody)
        .doesNotContain("TEST_ONLY_SENTINEL_SECRET");
~~~

Không xem một test `toString()` là đủ để chứng minh toàn bộ hệ thống không rò rỉ.

## 39. Kiểm thử luồng error handling

Một chiến lược test có thể gồm:

1. Cấp một secret giả làm cấu hình cho ứng dụng test.
2. Gây một lỗi có chủ đích tại HTTP client mock.
3. Kiểm tra response chỉ chứa mã lỗi và thông báo an toàn.
4. Kiểm tra log thu được không chứa secret giả.
5. Kiểm tra exception message của class nghiệp vụ không chứa secret.
6. Kiểm tra structured log fields và trace attributes nếu hệ thống hỗ trợ.
7. Kiểm tra error response trong môi trường cấu hình gần production.

Một test có thể sử dụng mock service trả lỗi giả chứa sentinel:

~~~text
Remote error: token TEST_ONLY_SENTINEL_SECRET rejected
~~~

Nếu code copy nguyên response body vào `IllegalStateException` hoặc `ApiError`, test sẽ phát hiện sentinel xuất hiện.

Không chỉ assert HTTP status 500 hoặc 502; **status đúng không chứng minh response body đã được sanitize**.

Với pipeline gửi log ngoài test runner, cần môi trường quan sát riêng hoặc contract test để kiểm tra giá trị nào được xuất ra.

## 40. Lưu log tập trung và retention

Ngay cả khi một log chỉ được ghi một lần trong vài giây, nó có thể được nhân bản:

~~~text
Application stdout
      |
      +--> Container log
      |
      +--> Log collector
      |
      +--> Search cluster
      |
      +--> Alert notification
      |
      +--> Archived object storage
      |
      +--> Support ticket / exported report
~~~

Mỗi bản sao làm việc khắc phục sự cố khó hơn. Các hệ thống có thể có retention, backup, immutable storage và quyền truy cập khác nhau.

Biện pháp kiểm soát:

- Giới hạn log theo nguyên tắc ít quyền nhất.
- Định nghĩa retention phù hợp.
- Hạn chế export và quyền chia sẻ log.
- Bảo vệ tài khoản của log collector và alerting.
- Không đưa secret vào alert message, e-mail hoặc chat notification.
- Khi phát hiện lộ bí mật, kiểm kê những nơi log đã được sao chép.

Không giả định rằng xóa một log line từ dashboard cũng xóa toàn bộ bản sao hoặc backup. Đó là lý do **ngăn dữ liệu đi vào log ban đầu** có giá trị cao hơn xử lý sau sự cố.

## 41. Phát hiện và ứng phó khi bí mật đã lộ

Nếu phát hiện token/password thật đã xuất hiện trong command line, log, exception hay source code, cần xử lý như một sự cố bảo mật có khả năng ảnh hưởng credential.

Quy trình khái quát:

1. **Đánh giá loại bí mật và quyền truy cập của nó**: token gì, scope nào, còn hiệu lực không?
2. **Thu hồi hoặc xoay vòng** credential sớm theo quy trình sự cố và khả năng hệ thống.
3. **Xác định phạm vi lộ**: CLI, shell history, CI logs, application logs, log aggregator, error tracking, ticket, backup.
4. **Hạn chế truy cập** đến dữ liệu đã lộ, ưu tiên không tạo thêm bản sao khi điều tra.
5. **Cập nhật ứng dụng** để loại bỏ đường rò rỉ trước khi triển khai credential mới.
6. **Xem lại audit** về việc sử dụng credential bất thường, nếu hệ thống hỗ trợ.
7. **Dọn dữ liệu và lưu vết sự cố** theo chính sách tổ chức, quy định retention và yêu cầu pháp lý.
8. **Bổ sung test/guardrail** để tránh tái diễn.

Không nên chỉ đổi text trong log bằng `****` rồi cho rằng credential an toàn trở lại. Secret đã bị lộ có thể đã được đọc, lưu hoặc sao chép trước đó.

Với private key hoặc credential dùng trên nhiều môi trường, rotation có thể đòi hỏi điều phối rộng hơn và cần tránh làm gián đoạn dịch vụ. Mục tiêu là xử lý đúng phạm vi ảnh hưởng, không phải xóa dấu vết một cách vội vàng.

## 42. Guardrail trong code review và CI

Một số nguyên tắc có thể đưa vào code review:

- Không đưa password/token thật vào `application*.yml` hoặc `application*.properties` trong repository.
- Không log object cấu hình chứa secret.
- Không dùng `@Data` hay auto `toString()` cho credential DTO mà không kiểm soát.
- Không trả `exception.getMessage()` trực tiếp cho người dùng.
- Không log toàn bộ HTTP headers, query parameters hoặc response body nhạy cảm.
- Không đưa secret vào MDC, metrics tag hoặc trace attribute.
- Không dùng `--password=...` trong các script vận hành.
- Không in environment hoặc toàn bộ Spring `Environment` khi debug.
- Có test dùng sentinel cho ít nhất những đường nguy hiểm nhất.
- Có cơ chế rotation và quy trình xử lý sự cố.

CI có thể sử dụng secret scanning để tìm chuỗi nghi là credential trong repository và artifact. Nhưng secret scanner không hoàn hảo, có false positive/false negative, nên vẫn cần review và quy định không dùng secret thật trong test.

Không đưa credential thật vào báo cáo CI để chứng minh scanner hoạt động. Dùng chuỗi thử nghiệm do công cụ khuyến nghị hoặc sentinel vô hại.

## 43. Bảng tổng hợp bốn nguồn rò rỉ chính

| Kênh | Ví dụ không an toàn | Nguyên nhân | Hướng xử lý |
| --- | --- | --- | --- |
| Dòng lệnh | `--app.api-key=secret` | Giá trị có thể nằm trong arguments, history, job log | Cấp qua secret source phù hợp; tránh CLI |
| Java system property | `-Dapp.password=secret` | Vẫn là thành phần của command line | Dùng cơ chế cấp secret không nằm trong command string |
| Environment dump | `log.info("{}", System.getenv())` | In nhiều giá trị nhạy cảm | Không dump toàn bộ environment |
| Application log | `log.info("token={}", token)` | Log thẳng secret | Chỉ log trạng thái/mã lỗi không nhạy cảm |
| HTTP log | Log `Authorization`/`Cookie` | Header/body có credential | Allowlist fields; loại header/body nhạy cảm |
| MDC/structured log | `MDC.put("apiKey", key)` | Giá trị lan tới mọi log record | Không đưa secret vào MDC |
| Record `toString()` | `log.info("{}", properties)` | Record in component mặc định | Không log bean; override/redact |
| Lombok `@Data` | DTO chứa password | Auto `toString()` có thể in field | Dùng include-only hoặc exclude rõ ràng |
| JSON response | Return credential bean | Serializer không dùng `toString()` | Response DTO allowlist |
| Exception message | `"Failed with key=" + key` | Secret vào stack trace/log | Thông báo cố định và safe error code |
| Error controller | `return ex.getMessage()` | Client nhận nguyên văn exception | Response không chứa chi tiết nội bộ |
| Binding failure | Giá trị sai gây lỗi | Diagnostic có thể chứa attempted value | Kiểm soát log/triage; không log raw exception tùy tiện |
| Actuator | Mở `env/configprops` rộng | Cấu hình có thể bị quan sát | Hạn chế exposure, sanitize, RBAC |
| Dump/diagnostic | Heap dump chứa secret | Secret còn trong memory | Bảo vệ đường dump, retention và truy cập |

Bảng này không phải danh sách đầy đủ mọi kênh rò rỉ; đây là các tình huống phổ biến nhất khi ứng dụng đọc bí mật từ Externalized Configuration và sử dụng nó trong quá trình vận hành.

## 44. Một thiết kế Spring Boot mẫu theo hướng an toàn hơn

Yêu cầu:

- App cần gọi API bằng credential.
- Runtime cấp credential qua file mount.
- Không muốn secret xuất hiện trong `application.yml` hoặc log startup.
- Muốn fail-fast khi thiếu credential.
- Muốn response lỗi không chứa credential.

Cấu hình:

~~~yaml
spring:
  config:
    import: "configtree:/run/secrets/"

app:
  integration:
    connect-timeout: 5s

server:
  error:
    include-message: never
    include-stacktrace: never
    include-binding-errors: never

management:
  endpoints:
    web:
      exposure:
        include: health,info
~~~

Với file mount:

~~~text
/run/secrets/app.integration.api-key
~~~

Record cấu hình:

~~~java
package com.example.demo.config;

import java.time.Duration;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app.integration")
public record IntegrationProperties(
        @NotNull Duration connectTimeout,
        @NotBlank String apiKey
) {
    @Override
    public String toString() {
        return "IntegrationProperties[redacted]";
    }
}
~~~

Đăng ký:

~~~java
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class DemoApplication {}
~~~

Sử dụng:

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

@Service
public class PartnerGateway {
    private static final Logger log =
            LoggerFactory.getLogger(PartnerGateway.class);

    private final IntegrationProperties properties;

    public PartnerGateway(IntegrationProperties properties) {
        this.properties = properties;
    }

    public void sendRequest() {
        log.info(
                "Preparing partner request; timeoutSeconds={}",
                properties.connectTimeout().toSeconds()
        );

        // Truyền properties.apiKey() đến HTTP client qua cơ chế
        // authentication tương ứng, không đưa vào log.
    }
}
~~~

Ứng dụng cần Bean Validation provider, thường là `spring-boot-starter-validation` trong Spring Boot 3.x. Ví dụ sử dụng config tree **không bao gồm toàn bộ cấu hình TLS, network hay access control** của một hệ thống production; đó là những trách nhiệm triển khai riêng.

Các lớp bảo vệ trong ví dụ bổ sung cho nhau:

1. Secret không được hardcode trong source.
2. Secret được cấp qua file với quyền hạn triển khai.
3. `@Validated` phát hiện credential trống.
4. `toString()` không in credential.
5. Log chỉ dùng timeout — giả định đã được đánh giá là không nhạy cảm.
6. Error response mặc định bị giới hạn.
7. Actuator web exposure được thu hẹp.

Nếu ở tầng HTTP client vẫn log full request headers, toàn bộ thiết kế trên có thể bị phá vỡ. Phải bảo vệ **đường dùng secret thực tế**, không chỉ cấu hình lúc startup.

## 45. Bài tập thực hành

### Bài 1 — Phát hiện rủi ro dòng lệnh

Cho lệnh:

~~~bash
java -Dapp.integration.api-key=DEMO-KEY -jar app.jar
~~~

Hỏi: Vì sao bí mật không nên được cung cấp theo cách này?

**Đáp án:** giá trị nằm trong command-line string và có thể xuất hiện trong process inspection, shell history hoặc log của job runner, tùy quyền và nền tảng. Nên dùng nguồn cấp bí mật phù hợp và kiểm soát truy cập thay vì truyền credential thật trên CLI.

### Bài 2 — Parameterized logging có tự che token?

~~~java
log.debug("Authorization token: {}", token);
~~~

Hỏi: `{}` có tự redact không?

**Đáp án:** không. Đây là cơ chế định dạng tham số. Khi log level cho phép ghi, giá trị token có thể được đưa vào log. Không log token ở bất kỳ level nào.

### Bài 3 — Java record và `toString()`

~~~java
public record Credentials(String username, String password) {}
~~~

~~~java
log.info("Credentials: {}", credentials);
~~~

Hỏi: nguy cơ gì?

**Đáp án:** record tự sinh `toString()` có thể in cả `password`. Không log object trực tiếp; dùng một biểu diễn diagnostic an toàn hoặc override `toString()` loại bỏ secret.

### Bài 4 — `@Data` của Lombok

Một DTO có `@Data` và field `refreshToken`. Hãy nêu cách giảm rủi ro.

**Đáp án:** tránh `@Data` nếu không cần toàn bộ hành vi, hoặc sử dụng `@ToString(onlyExplicitlyIncluded=true)` với danh sách field được phép. Đồng thời kiểm tra JSON serialization, vì `toString()` được che chưa chắc field không bị serialize.

### Bài 5 — Exception message

~~~java
throw new IllegalStateException(
        "API key is invalid: " + apiKey
);
~~~

Hỏi: sửa theo nguyên tắc nào?

**Đáp án:** thông báo nên cố định, không chứa giá trị credential, ví dụ `"Partner authentication failed"`, kèm safe error code/correlation ID nếu cần; không log message/cause thô có thể chứa secret.

### Bài 6 — Kiểm tra endpoint lỗi

Controller trả:

~~~java
return ResponseEntity.status(500).body(ex.getMessage());
~~~

Hỏi: tại sao cấu hình `server.error.include-message=never` chưa đủ?

**Đáp án:** custom handler tự dựng response từ exception, có thể bỏ qua hành vi của error endpoint mặc định. Cần sửa handler để trả DTO lỗi allowlist và test response không có sentinel secret.

### Bài 7 — Secret trong profile

`application-prod.yml` chứa API key thật và chỉ được kích hoạt ở production. Có an toàn để commit không?

**Đáp án:** không. Profile chỉ điều khiển nguồn cấu hình được chọn khi chạy, không ngăn người có quyền đọc repository/JAR nhìn thấy file. Bí mật cần được cấp qua cơ chế triển khai phù hợp.

### Bài 8 — Actuator

Một hệ thống bật công khai `/actuator/env` và `/actuator/configprops`, nhưng tin rằng framework đã sanitize. Nên làm gì?

**Đáp án:** giới hạn web exposure, authentication/authorization, policy hiển thị giá trị, network access và kiểm thử endpoint thực tế. Sanitization không phải lý do để mở endpoint diagnostic công khai.

### Bài 9 — Biến môi trường có tuyệt đối an toàn?

Hệ thống cấp `APP_INTEGRATION_APIKEY` bằng environment. Có cần quan tâm `System.getenv()`, crash dump hoặc CI logs không?

**Đáp án:** có. Environment là một kênh cấp giá trị, không phải kho bí mật được mã hóa tự động. Cần phân quyền, tránh dump và kiểm soát công cụ diagnostic.

### Bài 10 — Test secret giả

Hãy đề xuất cách kiểm thử log không in API key.

**Đáp án gợi ý:** dùng một chuỗi sentinel giả như `TEST_ONLY_SENTINEL_SECRET`, tạo đường request hoặc exception liên quan, dùng `OutputCaptureExtension` hoặc test appender để bắt log, rồi assert không có sentinel. Với JSON response và trace attributes, viết test riêng.

### Bài 11 — Secret đã xuất hiện trong log

Token thật vô tình bị ghi vào log aggregator. Chỉ xóa log khỏi dashboard có đủ không?

**Đáp án:** không. Cần đánh giá tác động, thu hồi/xoay vòng token, tìm nơi dữ liệu đã được nhân bản và sửa code để không tiếp tục rò rỉ. Việc xóa log hiển thị không có nghĩa mọi bản sao/backup đã biến mất.

### Bài 12 — Khác nhau giữa redaction và secret management

Một service dùng secret manager nhưng vẫn viết:

~~~java
log.info("Secret loaded: {}", apiKey);
~~~

Hỏi: secret manager đã giải quyết được vấn đề chưa?

**Đáp án:** chưa. Secret manager quản lý nguồn cấp/quyền truy cập/rotation; code vẫn có thể làm lộ giá trị khi sử dụng. Cần loại bỏ việc log bí mật và kiểm soát toàn bộ đường xuất dữ liệu.

## 46. Checklist trước khi triển khai production

### Nguồn cấp

- [ ] Không có secret thật trong Git, Dockerfile, image layer hoặc file cấu hình đóng gói.
- [ ] Không truyền secret thật qua command line hoặc Java `-D` nếu có phương án phù hợp hơn.
- [ ] Runtime lấy credential từ một nguồn quản lý được kiểm soát.
- [ ] Quyền đọc secret theo nguyên tắc ít quyền nhất.
- [ ] Có chính sách thu hồi, rotation và audit truy cập credential.
- [ ] Không dùng Base64 như một giải pháp mã hóa.

### Code và object model

- [ ] Không log secret trực tiếp hoặc gián tiếp qua `toString()`.
- [ ] Record, Lombok DTO và nested objects có chính sách biểu diễn chuỗi an toàn.
- [ ] Không trả configuration bean chứa secret từ controller.
- [ ] Không đưa secret vào metrics, MDC hoặc trace attributes.
- [ ] Không ghép secret vào exception message.
- [ ] Dùng mã lỗi và diagnostic theo allowlist.

### Web, HTTP và log

- [ ] HTTP client không log Authorization/Cookie/token query/body.
- [ ] Access log và structured logging được xem xét cho các field nhạy cảm.
- [ ] Error response không trả `ex.getMessage()` hoặc stack trace nội bộ.
- [ ] Actuator diagnostic endpoints được hạn chế và kiểm thử.
- [ ] Log aggregator, alerting, backup có phân quyền và retention phù hợp.
- [ ] Bộ lọc redaction là lớp bổ sung, không thay thế code an toàn.

### Kiểm thử và ứng phó

- [ ] Có test với sentinel secret cho log và `toString()`.
- [ ] Có test JSON serialization và error response.
- [ ] Có test tích hợp với logger/HTTP client thật nếu sử dụng interceptors.
- [ ] Có quy trình xử lý khi credential bị lộ.
- [ ] Có kế hoạch điều phối rotation khi secret liên quan nhiều hệ thống.

Checklist này không đồng nghĩa hệ thống được chứng nhận an toàn; nó giúp đội phát triển tránh những đường rò rỉ phổ biến trong vòng đời cấu hình Spring Boot.

## 47. Ghi nhớ

- **Externalized Configuration giúp thay đổi nguồn cấp, không tự bảo vệ bí mật** sau khi giá trị được nạp vào ứng dụng.
- **Command-line arguments và Java `-D`** có thể lộ trong process inspection, shell history, CI logs và công cụ diagnostic.
- **Environment variables** tiện dụng nhưng vẫn cần quản lý quyền truy cập, tránh dump và không xem là secret store tuyệt đối.
- **Parameterized logging bằng `{}` không tự redact**; không log token/password ngay cả ở DEBUG/TRACE.
- **Record `toString()` và Lombok `@Data`/`@ToString`** có thể làm lộ field credential khi log object.
- **`toString()` an toàn không đồng nghĩa JSON serialization an toàn**; controller phải dùng response DTO allowlist.
- **Exception message, nested cause, validation và lỗi binding** có thể mang dữ liệu nhạy cảm; không copy nguyên văn vào log hoặc API response.
- **Actuator và diagnostic dump** cần giới hạn quyền truy cập, web exposure, retention và chính sách hiển thị giá trị.
- **Secret manager/mounted file** giúp quản lý nguồn cấp nhưng không ngăn code tự log bí mật.
- **Ngăn secret xuất vào log từ đầu** quan trọng hơn chỉ mask tại aggregator.
- Nếu bí mật đã lộ, cần **đánh giá phạm vi, thu hồi/rotation và sửa đường rò rỉ**, không chỉ xóa dấu vết hiển thị.
- Kiểm thử bằng **sentinel giả**, không dùng credential thật để xác nhận redaction.

## Tài liệu tham khảo

- [Spring Boot — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html)
- [Spring Boot — Config Trees](https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.files.configtree)
- [Spring Boot — Actuator Endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html)
- [Spring Boot — Logging](https://docs.spring.io/spring-boot/reference/features/logging.html)
- [Spring Framework — Validation](https://docs.spring.io/spring-framework/reference/core/validation.html)
- [OWASP — Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html)
- [OWASP — Secrets Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html)
- [Kubernetes — Secrets](https://kubernetes.io/docs/concepts/configuration/secret/)
