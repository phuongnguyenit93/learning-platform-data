# Gọi HTTP API với timeout và cách báo lỗi phù hợp CLI

Ứng dụng Spring Shell thường gọi API bên ngoài để tra cứu dữ liệu, đồng bộ trạng thái hoặc thực hiện một thao tác từ command. Một request không nên chờ vô hạn, và lỗi từ hệ thống từ xa cần được chuyển thành thông báo mà người dùng CLI có thể hiểu và xử lý.

Bài học dùng `RestClient` của Spring Framework 6.1+ (Spring Boot 3.2+) cùng API command annotation legacy của Spring Shell 3.3.x. `RestClient` là client đồng bộ, phù hợp với command xử lý tuần tự. Nếu ứng dụng đã xây dựng theo WebFlux và cần I/O reactive, `WebClient` là lựa chọn tương ứng.

## 1. Tách command, service và HTTP client

Không nên đặt toàn bộ request HTTP, phân tích status code và định dạng thông báo trong command method. Hãy chia trách nhiệm thành ba lớp:

1. **Command:** nhận option/argument, gọi service và trình bày kết quả cho terminal.
2. **Service hoặc API client:** gửi HTTP request, chuyển response thành kiểu dữ liệu và phân loại lỗi từ xa.
3. **Cấu hình:** giữ base URL, timeout và thông tin kết nối ở cấu hình ứng dụng.

Ví dụ, command `catalog show 42` có thể gọi `CatalogApiClient.findById("42")`. Client chịu trách nhiệm giao tiếp HTTP; command chỉ cần nhận một `CatalogItem` hoặc một exception nghiệp vụ đã được phân loại.

Cách chia lớp này giúp thay đổi HTTP engine, base URL hoặc quy tắc timeout mà không phải sửa command. Đồng thời, logic ánh xạ lỗi có thể được kiểm thử độc lập với giao diện terminal.

## 2. Chọn RestClient cho command đồng bộ

Spring Framework cung cấp một số lựa chọn HTTP client:

| Client | Mô hình | Khi phù hợp |
|---|---|---|
| `RestClient` | Đồng bộ, fluent API | Command gọi API rồi chờ kết quả |
| `WebClient` | Non-blocking, reactive | Ứng dụng đã dùng Reactor/WebFlux |
| `RestTemplate` | Đồng bộ, template API | Hệ thống cũ cần duy trì hoặc chưa thể chuyển đổi |

`RestClient` hỗ trợ cấu hình base URL, header mặc định, request factory, interceptor và chuyển đổi JSON thành Java object. Trong Spring Boot, có thể inject `RestClient.Builder` đã được cấu hình sẵn để tạo client riêng cho từng API.

Với một CLI thực hiện mỗi command theo kiểu gọi request rồi hiển thị kết quả, API đồng bộ giúp luồng xử lý dễ theo dõi. Không cần gọi `block()` như khi dùng WebClient.

## 3. Dependency và cấu hình endpoint

Nếu dự án Spring Boot chưa có Spring Web, thêm starter:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
</dependency>
```

Dự án đã có Spring Shell giữ nguyên dependency starter của Spring Shell. Phiên bản Spring Boot nên được quản lý bằng parent hoặc BOM của dự án; không tự ghim một phiên bản Spring Framework riêng lẻ.

Đặt endpoint và timeout trong cấu hình:

```yaml
catalog:
  api:
    base-url: ${CATALOG_API_BASE_URL:https://api.example.test}
    connect-timeout: 2s
    read-timeout: 5s
spring:
  main:
    web-application-type: none
```

Giá trị `https://api.example.test` chỉ là endpoint minh họa. Khi triển khai, truyền URL thật qua biến môi trường hoặc cấu hình theo môi trường.
Vì `spring-boot-starter-web` cũng mang theo web server, đặt `web-application-type: none` để ứng dụng CLI không khởi động server HTTP khi chỉ cần dùng `RestClient`.

Có thể bind cấu hình vào record:

```java
import java.net.URI;
import java.time.Duration;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "catalog.api")
public record CatalogApiProperties(
    URI baseUrl,
    Duration connectTimeout,
    Duration readTimeout
) {
}
```

Khai báo properties và tạo `RestClient`:

```java
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.web.client.RestClient;

@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(CatalogApiProperties.class)
public class CatalogHttpConfiguration {

    @Bean
    RestClient catalogRestClient(
            RestClient.Builder builder,
            CatalogApiProperties properties) {

        SimpleClientHttpRequestFactory requestFactory =
            new SimpleClientHttpRequestFactory();

        requestFactory.setConnectTimeout(properties.connectTimeout());
        requestFactory.setReadTimeout(properties.readTimeout());

        return builder
            .baseUrl(properties.baseUrl().toString())
            .requestFactory(requestFactory)
            .defaultHeader(
                HttpHeaders.ACCEPT,
                MediaType.APPLICATION_JSON_VALUE
            )
            .build();
    }
}
```

Spring Boot cung cấp `RestClient.Builder` đã được cấu hình với message converters và request factory phù hợp. Ví dụ thay request factory bằng `SimpleClientHttpRequestFactory` để đặt timeout rõ ràng cho client Catalog.

Không nên dùng chung một client với timeout và chính sách xác thực khác nhau cho tất cả API nếu chúng có yêu cầu khác nhau. Tạo bean riêng như `catalogRestClient` giúp cấu hình của từng hệ thống từ xa được kiểm soát độc lập.

## 4. Phân biệt connect timeout và read timeout

Timeout cần được đặt rõ ràng. Nếu để mặc định của HTTP engine, thời gian chờ có thể phụ thuộc vào cấu hình hệ điều hành hoặc thư viện đang chạy.

| Loại timeout | Giới hạn điều gì? | Ví dụ |
|---|---|---|
| Connect timeout | Thời gian thiết lập kết nối tới máy chủ | Không kết nối được trong 2 giây |
| Read timeout | Thời gian chờ dữ liệu đọc từ kết nối | Máy chủ không gửi dữ liệu tiếp trong 5 giây |
| Request/deadline timeout | Ngân sách thời gian tổng cho một request | Toàn bộ thao tác phải hoàn tất trong 7 giây |

`SimpleClientHttpRequestFactory` dùng cơ chế JDK `HttpURLConnection` và cung cấp `setConnectTimeout(Duration)` cùng `setReadTimeout(Duration)`. Giá trị `Duration.ZERO` tương ứng không giới hạn thời gian chờ; vì vậy, ứng dụng CLI nên cấu hình giá trị dương, hữu hạn.

Cần phân biệt read timeout với deadline tổng. Read timeout giới hạn thời gian chờ ở thao tác đọc dữ liệu; nó không phải cam kết rằng toàn bộ request, bao gồm mọi lần đọc, xử lý redirect, upload và các bước khác, sẽ kết thúc trong đúng khoảng thời gian đó. Nếu nghiệp vụ cần deadline tổng nghiêm ngặt, hãy chọn HTTP engine có hỗ trợ request timeout phù hợp và kiểm tra hành vi của engine đó.

Timeout ví dụ `connect-timeout: 2s` và `read-timeout: 5s` chỉ là điểm bắt đầu. Hãy chọn dựa trên độ trễ thực tế, SLA của API và thời gian tối đa mà người dùng CLI có thể chấp nhận.

## 5. Gọi API và chuyển JSON thành object

Giả sử API trả về dữ liệu:

```json
{
  "id": "42",
  "name": "Inventory",
  "status": "ACTIVE"
}
```

Khai báo DTO:

```java
public record CatalogItem(
    String id,
    String name,
    String status
) {
}
```

Client gửi GET request:

```java
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;

@Component
public class CatalogApiClient {

    private final RestClient restClient;

    public CatalogApiClient(RestClient catalogRestClient) {
        this.restClient = catalogRestClient;
    }

    public CatalogItem findById(String id) {
        return restClient.get()
            .uri("/items/{id}", id)
            .accept(MediaType.APPLICATION_JSON)
            .retrieve()
            .body(CatalogItem.class);
    }
}
```

`uri("/items/{id}", id)` dùng URI variable để truyền ID vào path. Cách này giúp URI builder xử lý encoding giá trị thay vì nối chuỗi thủ công.

Chuỗi gọi có các bước:

1. `get()` chọn HTTP method.
2. `uri(...)` xác định endpoint.
3. `accept(...)` khai báo kiểu response mong muốn.
4. `retrieve()` thực hiện request và chuẩn bị đọc response.
5. `body(CatalogItem.class)` chuyển JSON thành DTO.

`retrieve()` riêng lẻ chưa thực hiện request; cần gọi một thao tác kết thúc như `body(...)` hoặc `toBodilessEntity()` để gửi request và tiêu thụ response.

Nếu API có thể trả body rỗng trong trường hợp đáng lẽ phải có dữ liệu, hãy kiểm tra kết quả `null` và chuyển thành lỗi giao thức dễ hiểu. Đừng để command vô tình gọi `item.name()` trên một giá trị null.

## 6. Các nhóm lỗi khi gọi HTTP API

Lỗi HTTP và lỗi kết nối có ý nghĩa khác nhau. CLI nên phân loại để người dùng biết nên sửa input, kiểm tra quyền truy cập hay thử lại sau.

| Nhóm lỗi | Ví dụ | Cách báo cho người dùng |
|---|---|---|
| Input không hợp lệ | HTTP 400 hoặc 422 | Kiểm tra lại giá trị truyền vào |
| Không có tài nguyên | HTTP 404 | Không tìm thấy mã tài nguyên |
| Xác thực hoặc quyền | HTTP 401 hoặc 403 | Kiểm tra credential và quyền truy cập |
| Bị giới hạn tốc độ | HTTP 429 | Thử lại sau; tôn trọng `Retry-After` nếu có |
| Lỗi máy chủ từ xa | HTTP 5xx | Dịch vụ đang gặp sự cố |
| Timeout | Connect/read timeout | API phản hồi quá thời gian cho phép |
| Không kết nối được | DNS, connection refused, TLS hoặc I/O | Kiểm tra mạng và endpoint |
| Response không hợp lệ | JSON sai định dạng hoặc body rỗng | API trả về dữ liệu không đọc được |

Với `RestClient`, response có status 4xx hoặc 5xx mặc định được chuyển thành một subclass của `RestClientException`. Có thể tùy chỉnh việc xử lý status bằng `onStatus(...)`. Lỗi I/O được biểu diễn bằng `ResourceAccessException`, một subclass của `RestClientException`.

Không nên gộp tất cả lỗi thành một thông báo “Không thể gọi API”. Một HTTP 404 có thể là mã người dùng nhập sai; timeout lại có thể cần thử lại. Phân loại đúng giúp hướng dẫn khắc phục cụ thể hơn.

## 7. Chuyển lỗi HTTP thành exception của ứng dụng

Không nên để command phụ thuộc trực tiếp vào các exception chi tiết của HTTP engine. Client có thể chuyển chúng thành một loại exception của ứng dụng, giữ nguyên nguyên nhân gốc để log hoặc chẩn đoán.

Ví dụ một exception có mã thoát riêng:

```java
public class CatalogApiException extends RuntimeException {

    private final int exitCode;

    public CatalogApiException(
            String message,
            int exitCode,
            Throwable cause) {
        super(message, cause);
        this.exitCode = exitCode;
    }

    public int exitCode() {
        return exitCode;
    }

    public static final class NotFound extends CatalogApiException {
        public NotFound(String id, Throwable cause) {
            super("Không tìm thấy mục có mã " + id + ".", 3, cause);
        }
    }

    public static final class Timeout extends CatalogApiException {
        public Timeout(Throwable cause) {
            super("Catalog API không phản hồi trong thời gian cho phép.", 4, cause);
        }
    }

    public static final class Unavailable extends CatalogApiException {
        public Unavailable(Throwable cause) {
            super("Không thể kết nối tới Catalog API.", 5, cause);
        }
    }

    public static final class HttpFailure extends CatalogApiException {
        public HttpFailure(int statusCode, Throwable cause) {
            super(messageFor(statusCode), 6, cause);
        }

        private static String messageFor(int statusCode) {
            return switch (statusCode) {
                case 400, 422 ->
                    "Catalog API từ chối dữ liệu. Hãy kiểm tra lại tham số.";
                case 401, 403 ->
                    "Không được phép truy cập Catalog API. Kiểm tra credential và quyền.";
                case 429 ->
                    "Catalog API đang giới hạn yêu cầu. Hãy thử lại sau.";
                default ->
                    "Catalog API trả về HTTP " + statusCode + ".";
            };
        }
    }

    public static final class InvalidResponse extends CatalogApiException {
        public InvalidResponse(Throwable cause) {
            super("Catalog API trả về dữ liệu không hợp lệ.", 7, cause);
        }
    }
}
```

Client bắt các exception theo thứ tự từ cụ thể tới tổng quát:

```java
import org.springframework.stereotype.Component;
import org.springframework.web.client.HttpClientErrorException;
import org.springframework.web.client.ResourceAccessException;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientException;
import org.springframework.web.client.RestClientResponseException;

@Component
public class CatalogApiClient {

    private final RestClient restClient;

    public CatalogApiClient(RestClient catalogRestClient) {
        this.restClient = catalogRestClient;
    }

    public CatalogItem findById(String id) {
        try {
            CatalogItem item = restClient.get()
                .uri("/items/{id}", id)
                .retrieve()
                .body(CatalogItem.class);

            if (item == null) {
                throw new CatalogApiException.InvalidResponse(null);
            }

            return item;
        }
        catch (HttpClientErrorException.NotFound ex) {
            throw new CatalogApiException.NotFound(id, ex);
        }
        catch (ResourceAccessException ex) {
            if (ex.contains(java.net.SocketTimeoutException.class)) {
                throw new CatalogApiException.Timeout(ex);
            }
            throw new CatalogApiException.Unavailable(ex);
        }
        catch (RestClientResponseException ex) {
            throw new CatalogApiException.HttpFailure(
                ex.getStatusCode().value(),
                ex
            );
        }
        catch (RestClientException ex) {
            throw new CatalogApiException.InvalidResponse(ex);
        }
    }
}
```

Thứ tự catch có ý nghĩa:

- Bắt `HttpClientErrorException.NotFound` trước lớp exception response tổng quát để nhận diện 404.
- Bắt `ResourceAccessException` trước `RestClientException` vì đây là lỗi I/O, có thể chứa nguyên nhân timeout.
- Bắt `RestClientResponseException` để lấy status code của response lỗi.
- Cuối cùng bắt `RestClientException` cho lỗi client khác, chẳng hạn không chuyển đổi được response.

Trong ví dụ dùng `SimpleClientHttpRequestFactory`, timeout đọc từ `HttpURLConnection` thường xuất hiện dưới dạng `SocketTimeoutException` nằm trong cause chain. `contains(...)` kiểm tra exception lồng bên trong. Nếu thay request factory hoặc HTTP engine, hãy kiểm tra loại exception thực tế và điều chỉnh bộ phân loại.

Thông điệp hiển thị không chứa response body thô. Response body có thể chứa dữ liệu cá nhân, thông tin nội bộ hoặc chi tiết xác thực. Giữ exception gốc làm cause để log có kiểm soát ở tầng phù hợp.

## 8. Ánh xạ exception thành thông báo và exit code của Spring Shell

Trong Spring Shell 3.3.x, có thể dùng `@ExceptionResolver` để chuyển exception nghiệp vụ thành `CommandHandlingResult`.

`CommandHandlingResult` chứa thông điệp và exit code. Mã thoát đặc biệt hữu ích khi command chạy non-interactive, ví dụ trong script hoặc CI/CD.

Ví dụ command:

```java
import org.springframework.shell.command.CommandHandlingResult;
import org.springframework.shell.command.annotation.ExceptionResolver;
import org.springframework.shell.standard.ShellComponent;
import org.springframework.shell.standard.ShellMethod;

@ShellComponent
public class CatalogCommands {

    private final CatalogApiClient catalogApiClient;

    public CatalogCommands(CatalogApiClient catalogApiClient) {
        this.catalogApiClient = catalogApiClient;
    }

    @ShellMethod(
        key = "catalog show",
        value = "Hiển thị một mục trong Catalog API"
    )
    public String show(String id) {
        CatalogItem item = catalogApiClient.findById(id);
        return "%s | %s | %s".formatted(
            item.id(),
            item.name(),
            item.status()
        );
    }

    @ExceptionResolver
    public CommandHandlingResult handleCatalogError(
            CatalogApiException exception) {

        return CommandHandlingResult.of(
            exception.getMessage(),
            exception.exitCode()
        );
    }
}
```

Resolver bắt exception thuộc `CatalogApiException` và trả thông điệp phù hợp. Command không cần biết chi tiết `HttpClientErrorException`, `ResourceAccessException` hoặc cách đọc cause chain.

Có thể công bố bảng exit code của ứng dụng:

| Exit code | Ý nghĩa |
|---:|---|
| 0 | Thành công |
| 1 | Lỗi không dự kiến |
| 2 | Đầu vào command không hợp lệ |
| 3 | Không tìm thấy tài nguyên |
| 4 | API timeout |
| 5 | Không kết nối được API |
| 6 | API trả HTTP error khác |
| 7 | Response không hợp lệ |

Đây là quy ước do ứng dụng định nghĩa. Hãy giữ mã ổn định nếu script bên ngoài dựa vào chúng.

Mã thoát của Spring Shell có ý nghĩa đối với chế độ non-interactive. Trong phiên REPL, người dùng thường vẫn tiếp tục nhập command sau khi một command lỗi. Nếu chuyển ứng dụng sang Spring Shell 4.x, cần chuyển từ resolver legacy sang `ExitStatusExceptionMapper` và API `ExitStatus` tương ứng; phần HTTP client và timeout có thể giữ độc lập với thay đổi đó.

## 9. Khi nào dùng onStatus?

Nếu muốn chuyển đổi status code ngay tại điểm gửi request, `RestClient.ResponseSpec.onStatus(...)` cho phép đăng ký handler theo điều kiện.

Ví dụ:

```java
import org.springframework.http.HttpStatusCode;

CatalogItem item = restClient.get()
    .uri("/items/{id}", id)
    .retrieve()
    .onStatus(
        HttpStatusCode::isError,
        (request, response) -> {
            if (response.getStatusCode().value() == 404) {
                throw new CatalogApiException.NotFound(id, null);
            }
            throw new CatalogApiException.HttpFailure(
                response.getStatusCode().value(),
                null
            );
        }
    )
    .body(CatalogItem.class);
```

Cách này hữu ích khi muốn quy tắc status được gắn trực tiếp với request. Với nhiều endpoint dùng chung quy tắc, có thể cấu hình handler mặc định ở `RestClient.Builder`.

Chọn một nơi làm chủ việc ánh xạ status để tránh xử lý trùng lặp. Nếu đã ánh xạ 4xx/5xx trong `onStatus`, service không nên tiếp tục xử lý cùng status như thể đó vẫn là exception mặc định.

## 10. Retry có giới hạn và có điều kiện

Timeout không đồng nghĩa request luôn nên được gửi lại. Retry cần dựa trên loại thao tác và khả năng phục hồi của API.

| Tình huống | Có nên retry? | Lưu ý |
|---|---|---|
| GET bị timeout tạm thời | Có thể | Giới hạn số lần và tổng thời gian |
| HTTP 429 | Có thể | Tôn trọng `Retry-After` |
| HTTP 503 | Có thể | Backoff và giới hạn retry |
| HTTP 400 hoặc 422 | Không | Người dùng cần sửa input |
| HTTP 401 hoặc 403 | Không tự động | Sửa credential hoặc quyền |
| POST tạo tài nguyên bị timeout | Cẩn trọng | Server có thể đã xử lý dù client chưa nhận response |

Một chính sách retry an toàn thường có:

- Số lần thử lại nhỏ và cố định.
- Exponential backoff, có thể thêm jitter.
- Tổng thời gian retry không vượt quá ngân sách command.
- Chỉ retry lỗi được xem là tạm thời.
- Dùng idempotency key khi API hỗ trợ thao tác ghi có thể bị gửi lặp.

Không retry vô hạn. Với command CLI, người dùng cần biết thao tác đã thất bại và có thể chủ động quyết định bước tiếp theo.

## 11. Bảo vệ credential và thông tin lỗi

Khi gọi API, thông tin xác thực và response có thể chứa dữ liệu nhạy cảm. Hãy:

- Đọc token từ biến môi trường, secret store hoặc cơ chế cấu hình bảo mật.
- Không ghi token, cookie hoặc authorization header vào log.
- Không ghép token vào URL query string.
- Không hiển thị nguyên response body cho người dùng terminal.
- Không in stack trace ở output thông thường.
- Log cause ở mức phù hợp, có request ID hoặc correlation ID nếu API cung cấp.
- Không ghi dữ liệu bí mật vào thông báo exception.

Ví dụ thêm bearer token từ cấu hình:

```java
return builder
    .baseUrl(properties.baseUrl().toString())
    .defaultHeader(
        HttpHeaders.AUTHORIZATION,
        "Bearer " + properties.accessToken()
    )
    .requestFactory(requestFactory)
    .build();
```

Ví dụ trên chỉ minh họa vị trí cấu hình header. Trong ứng dụng thực tế, `accessToken` phải đến từ nguồn bí mật phù hợp và không được đưa vào file cấu hình được commit vào source control.

## 12. Kiểm thử timeout và cách báo lỗi

Nên kiểm thử riêng từng tầng:

| Tầng | Cách kiểm thử | Điều cần xác minh |
|---|---|---|
| HTTP client | Mock response 404, 401, 500 | Status được phân loại đúng |
| Exception mapping | Gọi service với lỗi giả lập | Đúng loại exception, message và exit code |
| Command | Gọi command với service mock | Output dễ hiểu, không lộ stack trace |
| Timeout tích hợp | HTTP server giả lập phản hồi chậm | Request kết thúc trong timeout cấu hình |
| CI/non-interactive | Chạy command một lần | Process nhận exit code theo hợp đồng |

`MockRestServiceServer` phù hợp để giả lập status, header và response body mà không cần gọi dịch vụ thật. Với timeout ở tầng socket, dùng một HTTP server thử nghiệm có khả năng trì hoãn response để kiểm tra request factory thật; mock response tức thời không chứng minh timeout mạng hoạt động.

Các ca kiểm thử tối thiểu:

- API trả 200 và JSON hợp lệ.
- API trả 200 nhưng body rỗng.
- API trả 404.
- API trả 401 hoặc 403.
- API trả 429 hoặc 5xx.
- Kết nối bị từ chối.
- Server trì hoãn response vượt read timeout.
- Response JSON sai định dạng.
- Lỗi hiển thị không chứa token hoặc response body nhạy cảm.
- Command non-interactive trả đúng exit code đã công bố.

Đối với timeout, nên kiểm tra khoảng thời gian với biên độ hợp lý thay vì assert chính xác tới mili giây. Thời gian thực tế có thể dao động do scheduler, hệ điều hành và môi trường CI.

## 13. Các lỗi thường gặp

**Không cấu hình timeout.** Request có thể chờ quá lâu so với trải nghiệm CLI. Đặt connect timeout và read timeout hữu hạn.

**Nhầm read timeout với deadline tổng.** Hai khái niệm có phạm vi khác nhau. Nếu cần giới hạn toàn bộ thao tác, chọn HTTP engine hỗ trợ request timeout hoặc deadline tổng.

**Bắt mọi lỗi rồi trả một thông báo chung.** Người dùng không phân biệt được 404, timeout, lỗi xác thực hay server error. Phân loại theo status và I/O exception.

**Chỉ bắt `RestClientException` mà không phân loại.** `ResourceAccessException` là subclass của `RestClientException`; cần xử lý riêng để nhận diện lỗi kết nối và timeout.

**Đọc response body lỗi rồi in thẳng ra terminal.** Body có thể chứa dữ liệu nhạy cảm hoặc chi tiết nội bộ. Chỉ trích xuất thông tin đã được kiểm duyệt nếu thực sự cần.

**Retry mọi request.** POST có thể đã được server xử lý dù client timeout. Chỉ retry thao tác an toàn hoặc có idempotency key.

**Đặt token trong URL.** URL thường xuất hiện trong log, proxy và lịch sử. Dùng header xác thực.

**Để command phụ thuộc vào HTTP exception.** Command nên làm việc với kết quả hoặc exception nghiệp vụ, còn HTTP client chịu trách nhiệm phân loại lỗi giao thức.

**Cho rằng exit code luôn kết thúc phiên REPL.** Exit code chủ yếu phục vụ non-interactive execution. Trong REPL, shell tiếp tục nhận command theo cấu hình.

## 14. Checklist triển khai

- [ ] Chọn `RestClient` cho command đồng bộ hoặc `WebClient` cho luồng reactive.
- [ ] Dùng `RestClient.Builder` được Spring Boot cấu hình.
- [ ] Đặt base URL theo môi trường, không hardcode endpoint triển khai.
- [ ] Cấu hình connect timeout và read timeout hữu hạn.
- [ ] Hiểu giới hạn giữa timeout kết nối, timeout đọc và deadline tổng.
- [ ] Truyền path variable qua `uri(...)` để URI builder xử lý encoding.
- [ ] Phân loại 4xx, 5xx, timeout và lỗi I/O.
- [ ] Chuyển exception HTTP thành exception nghiệp vụ.
- [ ] Ánh xạ exception thành thông điệp dễ hiểu và exit code ổn định.
- [ ] Giữ response body và credential nhạy cảm khỏi output/log.
- [ ] Chỉ retry lỗi tạm thời với số lần và tổng thời gian giới hạn.
- [ ] Kiểm thử status mapping, timeout thật và command non-interactive.
- [ ] Kiểm tra dependency và API tương thích với phiên bản Spring Boot/Spring Shell.

## 15. Tài liệu tham khảo chính thức

- [Spring Boot 3.2 — Calling REST Services](https://docs.spring.io/spring-boot/docs/3.2.x/reference/htmlsingle/#io.rest-client): chọn `RestClient` cho API đồng bộ, inject `RestClient.Builder` và cấu hình client.
- [Spring Framework — REST Clients](https://docs.spring.io/spring-framework/reference/integration/rest-clients.html): tạo request, chuyển đổi response, `onStatus` và xử lý lỗi.
- [Spring Framework 6.1 — SimpleClientHttpRequestFactory API](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/http/client/SimpleClientHttpRequestFactory.html): `setConnectTimeout` và `setReadTimeout`.
- [Spring Framework 6.1 — ResourceAccessException API](https://docs.spring.io/spring-framework/docs/6.1.18/javadoc-api/org/springframework/web/client/ResourceAccessException.html): exception đại diện cho lỗi I/O.
- [Spring Framework 6.1 — RestClient.ResponseSpec API](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/web/client/RestClient.ResponseSpec.html): `body`, `toEntity` và lỗi response mặc định.
- [Spring Shell 3.3.4 — Exception Handling](https://docs.spring.io/spring-shell/reference/3.3/commands/exceptionhandling/index.html): xử lý exception và exit code trong non-interactive mode.
- [Spring Shell 3.3.0 — CommandHandlingResult API](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/command/CommandHandlingResult.html): trả message và exit code từ resolver.

Một command CLI tốt cần kết thúc request trong thời gian có thể dự đoán, phân biệt lỗi từ xa và đưa ra hướng xử lý cụ thể. Giữ HTTP timeout trong cấu hình client, chuyển lỗi giao thức thành exception nghiệp vụ và ánh xạ lỗi tại biên Spring Shell để người dùng terminal lẫn script nhận được kết quả nhất quán.

