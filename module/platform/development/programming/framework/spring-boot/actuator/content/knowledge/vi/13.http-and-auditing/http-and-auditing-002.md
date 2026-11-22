# Kích hoạt endpoint `httpexchanges` bằng `HttpExchangeRepository`

## 1. Từ một yêu cầu HTTP đến dữ liệu chẩn đoán

Khi thử một API, bạn thường muốn biết ứng dụng vừa nhận yêu cầu nào, trả mã trạng thái gì và mất bao lâu để xử lý. Chỉ nhìn kết quả của một lệnh gọi sẽ khó đối chiếu nhiều yêu cầu liên tiếp. Actuator có thể giữ thông tin về các lần trao đổi HTTP gần đây để bạn kiểm tra lại.

Một **trao đổi HTTP (HTTP exchange)** là thông tin gắn với một cặp yêu cầu–phản hồi. `httpexchanges` là endpoint dùng để đọc những thông tin đã được lưu. Trong Spring Boot 3.3, cần cung cấp một bean `HttpExchangeRepository` để bật khả năng ghi nhận; chỉ thêm Actuator hoặc mở endpoint trong cấu hình chưa cung cấp nơi lưu dữ liệu. [Tài liệu ghi nhận HTTP của Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/actuator/http-exchanges.html)

Bài này tập trung vào ứng dụng Spring MVC và cách nối đủ các thành phần để đọc được dữ liệu tại `/actuator/httpexchanges`. Bạn cần biết cách khai báo một bean bằng `@Bean`, tạo một API `@GetMapping` và cấu hình YAML.

## 2. Vai trò của repository, bộ ghi nhận và endpoint

`HttpExchangeRepository` là một interface lưu và lấy các đối tượng `HttpExchange`, với hai phương thức chính:

```java
void add(HttpExchange httpExchange);
List<HttpExchange> findAll();
```

Đây là trích đoạn chữ ký để giải thích hợp đồng, không phải tệp Java chạy độc lập. `add(...)` nhận một bản ghi; `findAll()` trả các bản ghi mà repository đang giữ. Tên `Repository` ở đây không có nghĩa là phải tạo Spring Data JPA repository, bảng cơ sở dữ liệu hay phương thức truy vấn. [API `HttpExchangeRepository`](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/web/exchanges/HttpExchangeRepository.html)

Luồng khái niệm trong ứng dụng Servlet:

```text
Yêu cầu HTTP đi vào ứng dụng
        ↓
Bộ lọc ghi nhận thông tin quanh quá trình xử lý
        ↓
HttpExchangeRepository.add(exchange)
        ↓
Dữ liệu được giữ trong repository
        ↓
GET /actuator/httpexchanges
        ↓
Endpoint đọc repository và trả JSON
```

`HttpExchangesFilter` là bộ lọc Servlet dành cho việc ghi nhận này. Với cấu hình tự động thông thường của Spring Boot, bạn cung cấp repository và để Boot thiết lập hạ tầng ghi nhận; không cần chèn lời gọi `repository.add(...)` vào từng controller. [API `HttpExchangesFilter`](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/web/exchanges/servlet/HttpExchangesFilter.html)

`HttpExchangesEndpoint` nhận `HttpExchangeRepository` qua constructor và cung cấp thao tác đọc. Vì vậy, endpoint là phía đọc dữ liệu, còn repository là điểm nối chung giữa phía ghi nhận và phía đọc. [API `HttpExchangesEndpoint`](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/web/exchanges/HttpExchangesEndpoint.html)

Để chẩn đoán đúng, hãy kiểm tra riêng từng điều kiện:

| Điều kiện | Câu hỏi cần trả lời |
| --- | --- |
| Có hạ tầng web và Actuator | Ứng dụng có chạy HTTP và có dependency Actuator không? |
| Có repository bean | Spring có quản lý một đối tượng `HttpExchangeRepository` không? |
| Ghi nhận được bật | Có cấu hình nào tắt việc ghi nhận không? |
| Endpoint được bật | `httpexchanges` có bị tắt ở mức endpoint không? |
| Endpoint được mở qua HTTP | Danh sách exposure có chứa `httpexchanges` và không bị exclude không? |
| Được phép truy cập | Quy tắc bảo mật có cho người gọi đọc endpoint không? |

Trong Spring Boot 3.3, endpoint này được bật theo mặc định nhưng không được mở qua HTTP theo mặc định; mặc định HTTP chỉ mở `health`. `exposure.exclude` được ưu tiên hơn `exposure.include`. Việc mở qua HTTP cũng không tự cấp quyền truy cập khi có Spring Security. [Quy tắc bật, mở và bảo vệ endpoint](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html)

## 3. Ví dụ độc lập: cung cấp repository rồi tạo lưu lượng

Ví dụ dùng JDK 21, Spring Boot 3.3.0 và Gradle Wrapper 8.5. Đây là một dự án thực hành độc lập. Các đường dẫn dưới đây tính từ thư mục dự án mẫu.

### 3.1. Cấu trúc và dependency

```text
http-exchanges-demo/
├── settings.gradle
├── build.gradle
├── gradlew
├── gradlew.bat
├── gradle/wrapper/...
└── src/main/
    ├── java/example/exchanges/ExchangeDemoApplication.java
    └── resources/application.yml
```

Wrapper 8.5 cần có sẵn trong dự án mẫu. Nếu chưa có wrapper và máy đã có Gradle, hãy tạo `settings.gradle` như bên dưới, chạy `gradle wrapper --gradle-version 8.5`, rồi thêm `build.gradle` có cấu hình plugin.

Nội dung `settings.gradle`:

```groovy
rootProject.name = 'http-exchanges-demo'
```

Nội dung `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.0'
    id 'io.spring.dependency-management' version '1.1.5'
}

group = 'example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
}
```

`spring-boot-starter-web` cung cấp ứng dụng Servlet và Spring MVC; `spring-boot-starter-actuator` cung cấp các thành phần Actuator. Ví dụ không thêm Spring Security để quan sát cơ chế cơ bản trên máy cá nhân.

### 3.2. Đăng ký bean có kiểu `HttpExchangeRepository`

Nội dung đầy đủ của `src/main/java/example/exchanges/ExchangeDemoApplication.java`:

```java
package example.exchanges;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.actuate.web.exchanges.HttpExchangeRepository;
import org.springframework.boot.actuate.web.exchanges.InMemoryHttpExchangeRepository;
import org.springframework.context.annotation.Bean;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class ExchangeDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(ExchangeDemoApplication.class, args);
    }

    @Bean
    HttpExchangeRepository httpExchangeRepository() {
        InMemoryHttpExchangeRepository repository =
                new InMemoryHttpExchangeRepository();
        repository.setCapacity(100);
        return repository;
    }

    @RestController
    public static class DemoController {

        @GetMapping("/demo/ping")
        public String ping() {
            return "pong";
        }
    }
}
```

Điểm quyết định là đối tượng được trả từ phương thức `@Bean`, không phải tên biến `repository`. Spring quản lý bean với kiểu `HttpExchangeRepository`; Boot có thể dùng bean đó cho tính năng HTTP exchanges. Nếu chỉ gọi `new InMemoryHttpExchangeRepository()` trong một biến cục bộ của controller mà không đăng ký bean, cấu hình tự động không nhận được nơi lưu cần thiết.

`InMemoryHttpExchangeRepository` là cách triển khai sẵn dùng bộ nhớ. Mặc định nó giữ 100 trao đổi gần nhất; dòng `setCapacity(100)` làm rõ lựa chọn đó trong ví dụ và có thể được bỏ đi khi dùng mặc định. API cho phép đổi dung lượng bằng `setCapacity(...)` và đổi chiều liệt kê bằng `setReverse(...)`. [Hành vi mặc định](https://docs.spring.io/spring-boot/3.3/reference/actuator/http-exchanges.html), [API repository bộ nhớ](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/web/exchanges/InMemoryHttpExchangeRepository.html)

### 3.3. Mở endpoint và xác định dữ liệu cần ghi

Nội dung `src/main/resources/application.yml`:

```yaml
server:
  address: 127.0.0.1
  port: 8080

management:
  endpoint:
    httpexchanges:
      enabled: true
  endpoints:
    web:
      exposure:
        include: health,httpexchanges
  httpexchanges:
    recording:
      enabled: true
      include:
        - time-taken
```

Ba nhánh cấu hình có nhiệm vụ khác nhau:

- `management.endpoint.httpexchanges.enabled` bật endpoint có ID `httpexchanges`.
- `management.endpoints.web.exposure.include` cho phép ánh xạ endpoint đó qua HTTP.
- `management.httpexchanges.recording` điều khiển việc ghi nhận trao đổi và các nhóm thông tin tùy chọn được đưa vào bản ghi.

Chú ý số ít `endpoint` ở thuộc tính bật một endpoint và số nhiều `endpoints` ở phần exposure. Nhánh `management.httpexchanges` dành cho cơ chế ghi nhận, không nằm bên trong `management.endpoint`.

Hai giá trị `enabled: true` được ghi rõ để dễ đọc, dù trong cấu hình mặc định của Boot 3.3 chúng đã được bật. Exposure `health,httpexchanges` vẫn cần thiết để truy cập endpoint mới qua HTTP. [Thuộc tính cấu hình Actuator](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/index.html)

`recording.include` trong ví dụ chỉ chọn `time-taken`: vẫn có thông tin cơ bản để nhận diện yêu cầu và mã trạng thái, đồng thời không yêu cầu ghi các nhóm header. `TIME_TAKEN` là một tùy chọn của `Include`; các tùy chọn khác gồm header yêu cầu, header phản hồi, địa chỉ từ xa, principal và session ID. Chọn danh sách này theo nhu cầu quan sát, không hiểu nó là danh sách endpoint được mở. [Các tùy chọn `Include`](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/web/exchanges/Include.html)

### 3.4. Khởi động và gọi API

Trên PowerShell, từ thư mục dự án mẫu:

```powershell
.\gradlew.bat bootRun
```

Trên Linux/macOS:

```bash
./gradlew bootRun
```

Chờ ứng dụng khởi động xong rồi mở một cửa sổ terminal khác. Trên PowerShell:

```powershell
curl.exe -s http://127.0.0.1:8080/demo/ping
```

Phần thân phản hồi chính xác:

```text
pong
```

Đọc dữ liệu Actuator:

```powershell
curl.exe -s http://127.0.0.1:8080/actuator/httpexchanges
```

Trên Linux/macOS dùng `curl` thay cho `curl.exe`. Trong cấu hình mẫu không đổi context path, base path hay cổng quản trị riêng, nên đường dẫn là `/actuator/httpexchanges` trên cổng 8080.

Endpoint trả một đối tượng có mảng `exchanges`; mỗi phần tử chứa thông tin yêu cầu và phản hồi. Những trường quan trọng để tìm lần gọi vừa tạo là `request.uri`, `request.method`, `response.status` và, khi được ghi, `timeTaken`. Timestamp và thời lượng thay đổi giữa các lần chạy, nên không so khớp nguyên văn toàn bộ JSON với một mẫu cố định. [Cấu trúc phản hồi HTTP Exchanges](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/httpexchanges.html)

Để kiểm tra kết quả ổn định hơn trên PowerShell, lọc riêng đường dẫn thử nghiệm:

```powershell
$snapshot = Invoke-RestMethod http://127.0.0.1:8080/actuator/httpexchanges
$ping = @($snapshot.exchanges | Where-Object {
    ([uri]$_.request.uri).AbsolutePath -eq '/demo/ping'
})
if ($ping.Count -eq 0) {
    throw 'Khong tim thay ban ghi /demo/ping'
}
$ping[0].request.method
$ping[0].response.status
```

Với lần gọi `/demo/ping` thành công phía trên, hai dòng cuối in:

```text
GET
200
```

Phép kiểm tra lọc theo đường dẫn thay vì giả định phần tử đầu tiên của toàn bộ `exchanges` luôn là yêu cầu cần tìm. Khi có nhiều yêu cầu khác hoặc bạn đọc Actuator nhiều lần, danh sách có thể chứa thêm các bản ghi.

## 4. Thí nghiệm để phân biệt từng lớp cấu hình

Mỗi lần thí nghiệm chỉ đổi một yếu tố, khởi động lại ứng dụng rồi gọi lại `/demo/ping` trước khi đọc endpoint. Không dùng dữ liệu bộ nhớ từ một lần khởi động trước làm bằng chứng cho lần chạy sau.

| Thay đổi trên ví dụ | Điều cần quan sát | Giải thích |
| --- | --- | --- |
| Giữ nguyên cấu hình mẫu | Tìm thấy bản ghi `GET /demo/ping` với trạng thái `200` | Có đủ phía ghi, nơi lưu và phía đọc |
| Bỏ phương thức `@Bean` repository, giữ exposure | Không còn endpoint HTTP exchanges được tự cấu hình như trường hợp mẫu | Exposure không tạo repository |
| Giữ bean, bỏ `httpexchanges` khỏi exposure | Không đọc được endpoint đó qua đường dẫn HTTP mặc định | Có nơi lưu không đồng nghĩa đã mở đường đọc qua HTTP |
| Giữ bean và exposure, đặt `recording.enabled: false` | Sau khi khởi động lại, gọi ping rồi đọc sẽ không thấy bản ghi ping mới | Tắt ghi nhận khác với tắt endpoint |
| Giữ các phần khác, đặt `endpoint.httpexchanges.enabled: false` | Không có thao tác đọc HTTP exchanges qua endpoint | Bật ghi nhận không tự bật lại endpoint đã bị tắt |

Riêng thí nghiệm tắt ghi nhận, với repository bộ nhớ mới và không có mã tự thêm dữ liệu, phản hồi đọc là:

```json
{"exchanges":[]}
```

`management.httpexchanges.recording.enabled=false` tắt việc ghi nhận tự động; không nên suy ra rằng nó xóa dữ liệu đã có trong một repository tự triển khai. Việc còn giữ dữ liệu nào thuộc chính sách của repository. [Điều khiển ghi nhận](https://docs.spring.io/spring-boot/3.3/reference/actuator/http-exchanges.html)

## 5. Chẩn đoán khi endpoint chưa hoạt động

| Hiện tượng | Các điểm cần kiểm tra |
| --- | --- |
| `/demo/ping` cũng không truy cập được | Ứng dụng đã khởi động chưa; địa chỉ và cổng có đúng không |
| HTTP `404` ở `/actuator/httpexchanges` | Dependency Actuator, repository bean, endpoint enabled, exposure include/exclude và đường dẫn thực tế |
| HTTP `401` hoặc `403` | Cơ chế xác thực, quyền truy cập và cấu hình Spring Security |
| Có `exchanges` nhưng thiếu lần gọi cần tìm | Đã gọi đúng tiến trình ứng dụng chưa; ghi nhận có bị tắt không; bản ghi có bị đẩy khỏi vùng lưu gần nhất không |
| Không có header hay danh tính người dùng | `recording.include` có yêu cầu nhóm dữ liệu đó không; thông tin ấy có tồn tại trong yêu cầu không |
| Dữ liệu biến mất sau restart | Đang dùng repository bộ nhớ, không có lưu trữ bền vững |

Đừng kết luận từ một mã `404` rằng chắc chắn thiếu bean: nhiều điều kiện khác nhau có thể dẫn đến cùng biểu hiện. Cũng đừng sửa bằng cách mở `*` ngay từ đầu; giữ danh sách endpoint cụ thể giúp tìm chính xác điều kiện còn thiếu.

Nếu Spring Security có trên classpath, Boot mặc định bảo vệ các endpoint ngoài `health` khi chưa có `SecurityFilterChain` do ứng dụng tự định nghĩa. Khi có chain riêng, phải kiểm tra chính những quy tắc của ứng dụng. Exposure và quyền truy cập là hai cấu hình độc lập. [Bảo mật Actuator](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.security)

## 6. Giới hạn và cách sử dụng hợp lý

`InMemoryHttpExchangeRepository` phù hợp cho việc thử và chẩn đoán trong môi trường phát triển; tài liệu Spring Boot khuyến nghị giải pháp tracing/observability phù hợp cho production hoặc một repository do ứng dụng triển khai. [Phạm vi sử dụng repository bộ nhớ](https://docs.spring.io/spring-boot/3.3/reference/actuator/http-exchanges.html)

Khi cân nhắc mở rộng ví dụ, cần trả lời các câu hỏi thiết kế cụ thể:

- **Dung lượng:** giữ nhiều bản ghi hơn sẽ tiêu tốn thêm bộ nhớ; cần biết khoảng lịch sử thực sự cần quan sát.
- **Khởi động lại:** nếu cần xem dữ liệu sau restart, phải thiết kế nơi lưu bền vững thay vì trông chờ vào đối tượng bộ nhớ.
- **Nhiều tiến trình:** nếu mỗi bản sao ứng dụng tạo repository riêng như ví dụ, mỗi bản sao chỉ có dữ liệu của nó; một lần gọi qua bộ cân bằng tải không đại diện toàn hệ thống.
- **Thông tin nhạy cảm:** việc không chọn header không làm URI tự hết nhạy cảm. Tham số URL vẫn cần được xem xét; không đưa bí mật vào URL.
- **Mục đích kiểm toán:** nếu cần bằng chứng nghiệp vụ lâu dài, phải thiết kế sự kiện, thời hạn lưu và quyền đọc phù hợp. Một cửa sổ trao đổi HTTP gần nhất không tự đáp ứng yêu cầu đó.

Không cần tự triển khai database repository chỉ để làm endpoint xuất hiện. Hãy chạy được ví dụ bộ nhớ trước, xác nhận luồng ghi–lưu–đọc, rồi mới chọn chính sách lưu phù hợp với nhu cầu thực tế.

## 7. Tự kiểm tra

1. Vì sao thêm `httpexchanges` vào exposure mà không có repository bean vẫn chưa đủ?
2. Tắt `management.endpoint.httpexchanges.enabled` khác gì tắt `management.httpexchanges.recording.enabled`?
3. Nếu đọc được `exchanges` nhưng không có `/demo/ping`, bạn sẽ kiểm tra điều gì trước?
4. Vì sao repository trong ví dụ không cần Spring Data JPA?

Đối chiếu: (1) exposure chỉ điều khiển mở endpoint qua một công nghệ, không tạo nơi lưu; (2) một thuộc tính điều khiển phía đọc qua endpoint, thuộc tính kia điều khiển ghi nhận; (3) kiểm tra đã tạo yêu cầu trên đúng ứng dụng và ghi nhận đang bật, sau đó mới xét dung lượng hoặc lưu lượng khác; (4) đây là bean triển khai hợp đồng `HttpExchangeRepository`, ví dụ dùng bộ nhớ thay vì cơ sở dữ liệu.
