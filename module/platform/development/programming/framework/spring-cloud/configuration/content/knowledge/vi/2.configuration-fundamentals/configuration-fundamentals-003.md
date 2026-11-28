# Binding kiểu dữ liệu, Duration, danh sách và cấu trúc lồng nhau

Trong một hệ thống dùng Spring Cloud Config, cấu hình thường được lưu tập trung trong Git rồi phân phối đến nhiều ứng dụng Spring Boot. Config Client lấy các property source theo tên ứng dụng, profile và label; Spring Boot đưa chúng vào Environment. Bước binding chuyển các khóa trong Environment thành những đối tượng Java có kiểu rõ ràng để mã nghiệp vụ sử dụng.

Bài này tập trung vào bước binding: gom cấu hình thành nhóm có cấu trúc, chuyển chuỗi thành kiểu Java, biểu diễn thời lượng bằng Duration, khai báo danh sách và cấu trúc lồng nhau, sau đó kiểm tra dữ liệu trước khi ứng dụng sử dụng. Ví dụ dùng Spring Boot 3.x và Java 17 trở lên.

## 1. Từ property key đến đối tượng Java

Một file cấu hình có thể chứa các khóa đơn giản:

```yaml
orders:
  retry-max-attempts: 4
  connect-timeout: 1500
  allowed-origins: https://shop.example.vn
```

Nếu đọc từng giá trị bằng @Value, lớp cấu hình sẽ nhanh chóng có nhiều biểu thức rời rạc. Kiểu dữ liệu và quan hệ giữa các thuộc tính cũng khó nhìn thấy ở một nơi. Với nhóm cấu hình có cùng mục đích, nên dùng @ConfigurationProperties:

- Có một prefix xác định phạm vi, chẳng hạn orders.
- Các thuộc tính được bind vào field, setter hoặc constructor tương ứng.
- Spring Boot thực hiện chuyển đổi kiểu dữ liệu từ các nguồn cấu hình.
- Có thể kiểm tra dữ liệu bằng Jakarta Bean Validation.
- Nhóm cấu hình trở thành một hợp đồng rõ ràng giữa cấu hình triển khai và mã ứng dụng.

@Value vẫn hữu ích cho một vài giá trị đơn lẻ. @ConfigurationProperties phù hợp hơn khi có nhiều thuộc tính liên quan, cấu trúc lồng nhau hoặc cần kiểm tra cấu hình một cách nhất quán.

## 2. Khai báo cấu hình có cấu trúc

Ví dụ dưới đây mô tả cấu hình cho dịch vụ đơn hàng. Cấu hình gồm chính sách retry, timeout HTTP, danh sách origin được phép và các endpoint có tên.

```yaml
orders:
  retry:
    max-attempts: 4
    initial-delay: 5
    max-delay: 2m
  http:
    connect-timeout: 1500ms
    read-timeout: PT10S
  allowed-origins:
    - https://shop.example.vn
    - https://admin.example.vn
  endpoints:
    catalog:
      base-url: https://catalog.internal.example
      timeout: 3s
    inventory:
      base-url: https://inventory.internal.example
      timeout: 5s
```

Dùng kebab-case trong YAML giúp tên khóa dễ đọc. Spring Boot hỗ trợ relaxed binding nên khóa orders.retry.max-attempts có thể bind vào thuộc tính maxAttempts trong Java. Khi chuyển tên thuộc tính sang biến môi trường, dấu chấm thành dấu gạch dưới, dấu gạch ngang bị loại bỏ và toàn bộ tên được viết hoa; ví dụ ORDERS_RETRY_MAXATTEMPTS.

Có thể biểu diễn cấu trúc đó bằng các record:

```java
package com.example.orders.config;

import java.net.URI;
import java.time.Duration;
import java.time.temporal.ChronoUnit;
import java.util.List;
import java.util.Map;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.convert.DurationUnit;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "orders")
public record OrdersProperties(
        @Valid @NotNull Retry retry,
        @Valid @NotNull Http http,
        List<URI> allowedOrigins,
        Map<String, @Valid Endpoint> endpoints) {

    public OrdersProperties {
        allowedOrigins = allowedOrigins == null
                ? List.of()
                : List.copyOf(allowedOrigins);
        endpoints = endpoints == null
                ? Map.of()
                : Map.copyOf(endpoints);
    }

    public record Retry(
            @Min(1) int maxAttempts,
            @NotNull
            @DurationUnit(ChronoUnit.SECONDS)
            Duration initialDelay,
            @NotNull Duration maxDelay) {
    }

    public record Http(
            @NotNull Duration connectTimeout,
            @NotNull Duration readTimeout) {
    }

    public record Endpoint(
            @NotNull URI baseUrl,
            @NotNull Duration timeout) {
    }
}
```

Đăng ký lớp cấu hình bằng @ConfigurationPropertiesScan trên lớp ứng dụng:

```java
@SpringBootApplication
@ConfigurationPropertiesScan
public class OrdersApplication {
    public static void main(String[] args) {
        SpringApplication.run(OrdersApplication.class, args);
    }
}
```

Một lựa chọn khác là khai báo @EnableConfigurationProperties(OrdersProperties.class) trên một lớp @Configuration. Chọn một cách đăng ký phù hợp với cấu trúc ứng dụng để Spring tạo bean cấu hình.

Với record có một constructor canonical, Spring Boot 3 hỗ trợ constructor binding mà không cần thêm @ConstructorBinding. Cấu trúc bất biến giúp các thành phần khác đọc cấu hình mà không vô tình thay đổi danh sách hoặc map. Compact constructor ở ví dụ trên chuẩn hóa giá trị thiếu thành collection rỗng và tạo bản sao không thể sửa đổi.

Nếu dùng validation, thêm dependency spring-boot-starter-validation. @Validated bật kiểm tra cho lớp cấu hình; @Valid yêu cầu kiểm tra tiếp các đối tượng lồng nhau; @NotNull và @Min là các ràng buộc cụ thể. Hãy đặt ràng buộc theo yêu cầu thực tế: maxAttempts phải ít nhất là 1, còn retry và http phải tồn tại. Nếu một trường bắt buộc bị thiếu hoặc sai kiểu, ứng dụng nên thất bại ngay khi khởi động để lỗi được phát hiện trước khi nhận lưu lượng.

## 3. Binding Duration và đơn vị thời gian

Timeout, thời gian chờ retry và khoảng nghỉ nên dùng java.time.Duration thay cho số nguyên không có đơn vị. Một giá trị Duration mang cả độ dài thời gian, nhờ vậy người đọc không phải đoán một số là mili giây, giây hay phút.

Spring Boot hỗ trợ các dạng phổ biến:

| Giá trị cấu hình | Ý nghĩa |
| --- | --- |
| 500ms | 500 mili giây |
| 30s | 30 giây |
| 5m | 5 phút |
| 2h | 2 giờ |
| PT1M30S | 1 phút 30 giây theo ISO-8601 |

Ví dụ trong YAML:

```yaml
orders:
  http:
    connect-timeout: 750ms
    read-timeout: 10s
  retry:
    initial-delay: 2s
    max-delay: 1m
```

Nếu dùng số thuần cho Duration, đơn vị mặc định là mili giây. Vì vậy giá trị 5 thường được hiểu là 5 mili giây, không phải 5 giây. Đây là lỗi cấu hình dễ bị bỏ qua vì ứng dụng vẫn có thể khởi động bình thường.

Có thể đổi đơn vị mặc định cho một thuộc tính số bằng @DurationUnit. Trong record ở trên, initialDelay được đánh dấu @DurationUnit(ChronoUnit.SECONDS), vì vậy giá trị số 5 được hiểu là 5 giây. Giá trị có hậu tố như 500ms vẫn thể hiện đơn vị tường minh và dễ đọc hơn. Với cấu hình chia sẻ giữa nhiều nhóm, nên ưu tiên luôn ghi hậu tố thay vì dựa vào đơn vị mặc định.

Khi nhận Duration, mã ứng dụng có thể truyền trực tiếp vào API cần Duration hoặc đổi sang đơn vị phù hợp:

```java
Duration timeout = properties.http().connectTimeout();

httpClientBuilder.connectTimeout(timeout);
long timeoutMillis = timeout.toMillis();
```

Cần kiểm tra cả miền giá trị, không chỉ kiểu dữ liệu. Duration âm thường không hợp lệ cho timeout hoặc thời gian chờ; Duration bằng zero có ý nghĩa riêng tùy API. Jakarta Bean Validation không có sẵn một ràng buộc số dương áp dụng trực tiếp cho mọi Duration. Có thể kiểm tra trong constructor hoặc viết custom constraint:

```java
if (connectTimeout.isNegative() || connectTimeout.isZero()) {
    throw new IllegalArgumentException(
            "orders.http.connect-timeout phải lớn hơn 0");
}
```

Không nên giả định mọi thư viện xử lý timeout giống nhau. Hãy xác định rõ zero nghĩa là tắt timeout, không chờ, hay giá trị không hợp lệ theo API mà ứng dụng đang dùng.

## 4. Binding danh sách

Khi một thuộc tính có nhiều giá trị cùng loại, biểu diễn bằng YAML sequence và bind vào List có kiểu phần tử cụ thể:

```yaml
orders:
  allowed-origins:
    - https://shop.example.vn
    - https://admin.example.vn
```

Spring Boot chuyển từng phần tử thành URI khi bind vào List<URI>. Cách biểu diễn tương đương trong application.properties là:

```properties
orders.allowed-origins[0]=https://shop.example.vn
orders.allowed-origins[1]=https://admin.example.vn
```

Danh sách có thể chứa kiểu đơn giản hoặc đối tượng có cấu trúc. Ví dụ, nếu mỗi route có name, path và timeout, có thể khai báo List<Route> với một record Route riêng. Khi đó YAML dùng các phần tử có các thuộc tính con tương ứng.

Một điểm quan trọng khi phối hợp nhiều nguồn cấu hình: danh sách ở property source có độ ưu tiên cao hơn thường thay thế toàn bộ danh sách ở nguồn thấp hơn, thay vì tự động nối thêm phần tử. Ví dụ, application.yml khai báo ba origin nhưng application-prod.yml chỉ khai báo một origin thì danh sách hiệu lực ở profile prod có thể chỉ còn phần tử được khai báo trong nguồn ưu tiên cao. Vì vậy, khi ghi đè danh sách trong profile hoặc cấu hình theo môi trường, hãy khai báo đầy đủ danh sách mong muốn.

Đừng nhầm danh sách với map. List phù hợp khi thứ tự phần tử có ý nghĩa hoặc các phần tử là một tập hợp tuần tự. Nếu mỗi giá trị có một tên ổn định như catalog hay inventory, Map thường dễ quản trị hơn.

## 5. Binding map và cấu trúc lồng nhau

Map phù hợp với cấu hình có số lượng khóa thay đổi theo môi trường hoặc theo dịch vụ. Trong ví dụ, endpoints là Map<String, Endpoint>. Các khóa catalog và inventory trở thành key; mỗi key chứa một đối tượng Endpoint.

```yaml
orders:
  endpoints:
    catalog:
      base-url: https://catalog.internal.example
      timeout: 3s
    inventory:
      base-url: https://inventory.internal.example
      timeout: 5s
```

Có thể truy cập cấu hình bằng key:

```java
OrdersProperties.Endpoint catalog =
        properties.endpoints().get("catalog");

URI catalogUri = catalog.baseUrl();
Duration catalogTimeout = catalog.timeout();
```

Hãy kiểm tra key trước khi sử dụng nếu một endpoint có thể không được khai báo. Nếu endpoint là bắt buộc, kiểm tra sự tồn tại của key trong bước xác thực cấu hình hoặc khi khởi tạo thành phần phụ thuộc. Với map chứa đối tượng, có thể dùng @Valid trên kiểu giá trị để yêu cầu validation đi sâu vào từng phần tử.

Các lớp hoặc record lồng nhau giúp phản ánh cấu trúc nghiệp vụ. Ví dụ, orders.retry.max-attempts được bind vào Retry.maxAttempts; orders.http.connect-timeout được bind vào Http.connectTimeout. Nên nhóm các thuộc tính theo trách nhiệm như retry, http, security hoặc endpoints. Cấu trúc rõ ràng giúp người vận hành tìm đúng phần cần sửa và giảm nguy cơ đặt nhầm khóa.

Map có thể kết hợp với cấu trúc lồng nhau, nhưng tránh dùng Map<String, Object> cho mọi thứ. Kiểu Object làm mất hợp đồng kiểu dữ liệu, khiến lỗi chỉ xuất hiện khi mã đọc và ép kiểu giá trị. Hãy dùng record hoặc class cụ thể khi cấu trúc đã biết; dành map động cho những khóa thực sự do môi trường hoặc người vận hành quyết định.

## 6. Đưa cấu hình vào Spring Cloud Config

Giả sử Config Server đang đọc một Git repository. Repository có thể chứa cấu hình dùng chung và cấu hình riêng cho từng ứng dụng, chẳng hạn:

```text
application.yml
orders-service.yml
orders-service-prod.yml
```

Config Client khai báo tên ứng dụng và kết nối đến Config Server trong application.yml của chính ứng dụng:

```yaml
spring:
  application:
    name: orders-service
  config:
    import: "configserver:http://localhost:8888"
```

Tên ứng dụng giúp Config Server tìm cấu hình tương ứng. Profile chọn tập cấu hình theo môi trường như dev, staging hoặc prod. Label chọn nhánh, tag hoặc commit của repository theo cấu hình backend. Khi cần ghim ứng dụng vào một phiên bản cấu hình đã kiểm soát, hãy đặt label rõ ràng thay vì phụ thuộc vào nhánh mặc định.

Config Server trả về Environment gồm các property source phù hợp với application, profile và label. Spring Boot kết hợp chúng theo thứ tự ưu tiên của property source rồi binding prefix orders vào OrdersProperties. Vì vậy, nếu một giá trị không như mong đợi, cần kiểm tra cả tên khóa, profile đang chạy, label đang dùng và nguồn nào đang thắng theo precedence. Không nên kết luận rằng file YAML nhìn thấy trong Git chắc chắn là giá trị cuối cùng mà bean nhận được.

Có thể dùng endpoint Actuator như env và configprops trong môi trường phát triển để kiểm tra nguồn thuộc tính và kết quả binding. Các endpoint này có thể tiết lộ thông tin nhạy cảm; chỉ bật và cấp quyền truy cập có kiểm soát, đặc biệt ở production. Nếu cần cấu hình client tiếp tục khởi động khi Config Server tạm thời không truy cập được, có thể dùng optional:configserver: trong spring.config.import. Chỉ dùng optional khi ứng dụng thực sự có giá trị mặc định an toàn và chấp nhận chạy thiếu cấu hình từ xa.

Việc lấy cấu hình lúc khởi động không đồng nghĩa bean sẽ tự thay đổi ngay khi Git được cập nhật. Với Spring Cloud Context, có thể kích hoạt refresh qua cơ chế refresh được cấu hình cho ứng dụng; Spring Cloud Bus có thể phát sự kiện refresh đến nhiều instance. Bean có trạng thái hoặc giữ bản sao cấu hình cần được kiểm tra kỹ về vòng đời và khả năng refresh. Đối với cấu hình ảnh hưởng đến hành vi quan trọng, hãy thử nghiệm refresh trên một instance trước khi phát tán đến toàn hệ thống.

## 7. Quản trị thay đổi và bảo vệ cấu hình

Cấu hình tập trung là một phần của vận hành hệ thống. Mỗi thay đổi trong Git nên có người chịu trách nhiệm, nội dung thay đổi dễ đọc và khả năng quay lại phiên bản trước. Có thể dùng pull request, review, nhánh hoặc tag để kiểm soát thay đổi; label của Config Client cần trỏ đến phiên bản đã được phê duyệt theo quy trình triển khai.

Không lưu mật khẩu, token, private key hoặc thông tin xác thực dạng rõ trong repository cấu hình. Dùng secret manager hoặc cơ chế mã hóa phù hợp; giới hạn quyền đọc repository và Config Server; bảo vệ endpoint quản trị và refresh bằng xác thực, phân quyền và mạng nội bộ. Giá trị đã mã hóa vẫn cần quản lý khóa giải mã an toàn. Tránh ghi secret vào log, thông báo lỗi hoặc endpoint chẩn đoán có quyền truy cập rộng.

Khi rollout cấu hình, nên kiểm tra trước trên môi trường thử nghiệm, xác nhận ứng dụng bind và validate thành công, sau đó mới áp dụng cho production. Với thay đổi có thể làm tăng tải hoặc thay đổi hành vi retry, timeout, endpoint, cần theo dõi log, metric và lỗi kết nối sau refresh. Git history giúp truy vết ai thay đổi và có thể khôi phục nội dung, nhưng không thay thế việc kiểm tra tác động khi cấu hình được áp dụng.

## 8. Lỗi thường gặp và cách chẩn đoán

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| Bean cấu hình không được tạo | Thiếu @ConfigurationPropertiesScan hoặc @EnableConfigurationProperties | Kiểm tra nơi đăng ký lớp cấu hình |
| Thuộc tính luôn nhận null hoặc giá trị mặc định | Sai prefix, sai tên khóa hoặc file không thuộc application/profile/label đang chạy | Kiểm tra Environment và tên file trong Git |
| Ứng dụng lỗi khi bind | Giá trị không chuyển đổi được sang kiểu Java hoặc YAML sai cấu trúc | Đọc lỗi binding, kiểm tra kiểu và thụt lề |
| Timeout ngắn bất thường | Số thuần của Duration đang được hiểu là mili giây | Ghi đơn vị như 500ms hoặc 5s |
| Danh sách thiếu phần tử sau khi đổi profile | Danh sách ở nguồn ưu tiên cao thay thế danh sách nguồn thấp | Khai báo đầy đủ danh sách cho profile đó |
| Thuộc tính lồng nhau không được kiểm tra | Thiếu @Valid ở đối tượng lồng nhau hoặc thiếu dependency validation | Kiểm tra annotation và spring-boot-starter-validation |
| Giá trị trong Git khác giá trị runtime | Profile, label hoặc precedence khiến property source khác thắng | Kiểm tra cấu hình client và nguồn thuộc tính hiệu lực |
| Instance chưa nhận cấu hình mới | Chưa có refresh event hoặc bean không hỗ trợ cập nhật theo vòng đời hiện tại | Kiểm tra endpoint refresh/Bus và cách bean giữ cấu hình |

## 9. Quy trình áp dụng cho một thuộc tính mới

Khi thêm một cấu hình vào dịch vụ, có thể thực hiện theo trình tự sau:

1. Xác định thuộc tính thuộc nhóm nào và đặt tên dưới prefix ổn định.
2. Chọn kiểu Java thể hiện đúng ý nghĩa: Duration cho thời gian, URI cho địa chỉ, List cho tập hợp có thứ tự, Map cho tập hợp có khóa.
3. Thêm thuộc tính vào file cấu hình chung hoặc file theo ứng dụng/profile trong Git.
4. Bổ sung field hoặc record component tương ứng trong lớp @ConfigurationProperties.
5. Thêm validation cho trường bắt buộc và miền giá trị hợp lệ.
6. Kiểm tra binding với profile và label thực tế, gồm cả giá trị ghi đè từ các nguồn có ưu tiên cao hơn.
7. Thử refresh và rollback nếu thuộc tính được cập nhật khi ứng dụng đang chạy.

Một lớp cấu hình có kiểu rõ ràng giúp lỗi được phát hiện sớm, tài liệu cấu hình dễ đọc và các môi trường triển khai giữ cùng một hợp đồng. Khi kết hợp đúng @ConfigurationProperties, Duration, collection, cấu trúc lồng nhau và validation, Spring Cloud Config có thể phân phối cấu hình tập trung mà từng ứng dụng vẫn sử dụng dữ liệu theo kiểu an toàn và dễ kiểm soát.

