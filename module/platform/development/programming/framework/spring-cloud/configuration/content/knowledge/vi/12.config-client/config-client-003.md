# Địa chỉ trong import so với spring.cloud.config.uri

Config Client cần biết địa chỉ của Config Server trước khi có thể lấy cấu hình từ xa. Trong Spring Cloud Config, địa chỉ này thường xuất hiện ở hai nơi: URL được viết trực tiếp trong <code>spring.config.import</code> theo Config Data API, hoặc thuộc tính <code>spring.cloud.config.uri</code> thường gặp trong mô hình bootstrap truyền thống.

Hai cách khai báo có liên quan nhưng không hoàn toàn thay thế nhau. <code>spring.config.import</code> là cơ chế đưa Config Server vào quá trình nạp cấu hình của Spring Boot hiện đại. <code>spring.cloud.config.uri</code> là thuộc tính chỉ vị trí server; nó thường được dùng trong bootstrap context cũ và cũng có thể cung cấp URL mặc định khi import không ghi URL cụ thể. Hiểu đúng vai trò và thời điểm đọc của từng thuộc tính giúp tránh gọi Config Server hai lần, dùng nhầm địa chỉ hoặc khiến ứng dụng khởi động với cấu hình không mong đợi.

Bài học này giải thích sự khác nhau giữa hai cách, cách chọn URL, ảnh hưởng của optional/mandatory import, profile và label, thứ tự ưu tiên, cách chuyển từ bootstrap sang Config Data API và cách chẩn đoán khi client không kết nối được.

Sau bài học, bạn có thể:

- Phân biệt cơ chế <code>spring.config.import</code> với thuộc tính <code>spring.cloud.config.uri</code>.
- Xác định cách khai báo phù hợp với Config Data API và bootstrap context truyền thống.
- Hiểu URL tường minh trong import và URL mặc định từ <code>spring.cloud.config.uri</code>.
- Cấu hình application name, profile, label và chính sách optional/mandatory.
- Nhận diện rủi ro khi bật đồng thời hai cơ chế nạp cấu hình.
- Chuyển đổi cấu hình client và kiểm tra địa chỉ server thực tế mà ứng dụng sử dụng.

## 1. Config Client cần địa chỉ Config Server ở thời điểm nào?

Một ứng dụng Spring Boot có thể lấy cấu hình từ nhiều nguồn: tệp YAML cục bộ, biến môi trường, tham số JVM, Config Server và các nguồn khác. Để lấy cấu hình tập trung, Config Client cần biết server ở giai đoạn đủ sớm để nạp property source từ xa.

Luồng tổng quát:

~~~mermaid
flowchart TD
    A["Spring Boot bắt đầu khởi động"] --> B{"Cơ chế nạp cấu hình"}
    B --> C["Config Data API"]
    B --> D["Bootstrap context truyền thống"]
    C --> E["spring.config.import"]
    E --> F["Địa chỉ configserver: trong import hoặc URL mặc định"]
    D --> G["spring.cloud.config.uri"]
    F --> H["Gọi Config Server"]
    G --> H
    H --> I["Nhận Environment / property sources"]
    I --> J["Spring Environment và binding"]
    J --> K["Khởi tạo bean ứng dụng"]
~~~

Hai nhánh trên thể hiện hai cách tích hợp theo hai thế hệ cơ chế nạp cấu hình:

- **Config Data API:** Spring Boot nạp các location cấu hình thông qua <code>spring.config.import</code>. Đây là cách được khuyến nghị cho các ứng dụng Spring Boot hiện đại sử dụng Spring Cloud Config.
- **Bootstrap context:** Spring Cloud tạo một context bootstrap trước application context chính để lấy cấu hình từ xa. Trong mô hình này, <code>spring.cloud.config.uri</code> thường được khai báo trong <code>bootstrap.yml</code> hoặc <code>bootstrap.properties</code>.

Điểm mấu chốt là URL phải sẵn sàng trước khi Config Client thực hiện request. Nếu đặt thuộc tính ở một tệp chỉ được nạp sau thời điểm đó, client có thể không nhìn thấy địa chỉ hoặc dùng giá trị mặc định.

## 2. spring.config.import: khai báo Config Server như một nguồn cấu hình

Config Data API được Spring Boot giới thiệu từ dòng 2.4. Với Spring Cloud Config tương thích, client khai báo Config Server trong <code>spring.config.import</code>:

~~~yaml
spring:
  application:
    name: orders-service
  profiles:
    active: prod
  config:
    import: "configserver:http://config.internal:8888"
~~~

Scheme <code>configserver:</code> cho Spring biết location này được xử lý bởi Config Server Config Data Location Resolver. Phần URL theo sau chỉ ra địa chỉ server.

Client sẽ gửi request tương ứng với application name và profile, thường theo endpoint dạng:

~~~http
GET http://config.internal:8888/orders-service/prod
~~~

Nếu có label, client cũng gửi label theo cơ chế của Config Client:

~~~yaml
spring:
  cloud:
    config:
      label: release-2026.11
~~~

### Import bắt buộc và optional

Nếu khai báo:

~~~yaml
spring:
  config:
    import: "configserver:http://config.internal:8888"
~~~

location là bắt buộc. Nếu client không lấy được cấu hình từ server, quá trình nạp cấu hình thường thất bại và ứng dụng không khởi động.

Nếu khai báo:

~~~yaml
spring:
  config:
    import: "optional:configserver:http://config.internal:8888"
~~~

client có thể tiếp tục khởi động khi nguồn cấu hình từ xa không truy cập được. Khi đó ứng dụng cần có cấu hình cục bộ hoặc fallback an toàn để vận hành.

Tiền tố <code>optional:</code> không có nghĩa Config Server không được gọi. Nó chỉ thay đổi cách Spring xử lý khi location không nạp được. Nếu ứng dụng production cần URL datasource, endpoint nội bộ hoặc chính sách bảo mật từ Config Server, dùng optional có thể khiến ứng dụng tiếp tục với cấu hình thiếu hoặc giá trị mặc định. Hãy chọn theo mức độ thiết yếu của cấu hình.

### Dùng import không ghi URL tường minh

Có thể khai báo:

~~~yaml
spring:
  config:
    import: "configserver:"
~~~

Khi location không chỉ rõ URL, Config Client sử dụng địa chỉ mặc định của Config Server. Giá trị mặc định phổ biến là <code>http://localhost:8888</code>. Có thể đặt địa chỉ mặc định khác bằng <code>spring.cloud.config.uri</code>:

~~~yaml
spring:
  application:
    name: orders-service
  config:
    import: "configserver:"
  cloud:
    config:
      uri: https://config.internal
~~~

Cách này tách hai vai trò: <code>spring.config.import</code> bật việc nạp Config Server; <code>spring.cloud.config.uri</code> cung cấp địa chỉ mặc định cho location không chứa URL cụ thể.

Khi URL đã được ghi trực tiếp trong import, hãy coi URL đó là địa chỉ của location ấy. Không nên khai báo một URL tường minh khác trong import rồi kỳ vọng <code>spring.cloud.config.uri</code> sẽ âm thầm thay thế nó. Tránh cấu hình hai giá trị khác nhau vì người vận hành sẽ khó biết client đang gọi server nào.

## 3. spring.cloud.config.uri: thuộc tính chỉ địa chỉ server

<code>spring.cloud.config.uri</code> có nghĩa là địa chỉ hoặc danh sách địa chỉ Config Server mà Config Client sử dụng. Trong mô hình bootstrap truyền thống, nó thường được đặt trong tệp <code>bootstrap.yml</code>:

~~~yaml
# bootstrap.yml
spring:
  application:
    name: orders-service
  cloud:
    config:
      uri: https://config.internal
      label: release-2026.11
~~~

Bootstrap context được nạp trước application context chính. Nhờ đó, Config Client biết địa chỉ Config Server trước khi các cấu hình từ xa được đưa vào ứng dụng.

Trong các phiên bản Spring Cloud mới, bootstrap context không còn được bật mặc định theo cách cũ trong mọi cấu hình. Để dùng mô hình này, dự án thường cần dependency <code>spring-cloud-starter-bootstrap</code> hoặc bật bootstrap theo hướng dẫn tương ứng của phiên bản. Chỉ tạo một tệp <code>bootstrap.yml</code> trong dự án mới không bảo đảm tệp đó được đọc.

<code>spring.cloud.config.uri</code> là thuộc tính vị trí. Bản thân nó không thay thế cơ chế kích hoạt nạp cấu hình. Trong mô hình bootstrap, bootstrap infrastructure kích hoạt Config Client. Trong Config Data API, <code>spring.config.import</code> đưa location vào quá trình nạp cấu hình.

### Đặt URI ở đâu?

Với bootstrap context, nên đặt <code>spring.cloud.config.uri</code> trong <code>bootstrap.yml</code> hoặc <code>bootstrap.properties</code>, hoặc truyền từ biến môi trường/tham số hệ thống có sẵn trước khi bootstrap bắt đầu.

Với Config Data API, có hai lựa chọn thường gặp:

- Ghi URL trực tiếp trong <code>spring.config.import</code> để mỗi location tự mô tả địa chỉ.
- Dùng <code>spring.config.import=configserver:</code> và đặt URL mặc định bằng <code>spring.cloud.config.uri</code>.

Nếu đặt <code>spring.cloud.config.uri</code> trong <code>application.yml</code> nhưng vẫn dùng bootstrap cũ, cần kiểm tra xem thuộc tính có được nạp đủ sớm hay không. Tệp application chính có thể được đọc sau giai đoạn bootstrap; khi đó client không thể dùng giá trị vừa được nạp muộn để tạo request ban đầu.

## 4. So sánh trực tiếp hai cách khai báo

| Tiêu chí | <code>spring.config.import</code> | <code>spring.cloud.config.uri</code> |
|---|---|---|
| Vai trò | Khai báo location Config Server tham gia nạp cấu hình | Chỉ định URL của Config Server |
| Cơ chế thường dùng | Config Data API | Bootstrap context truyền thống; cũng có thể làm URL mặc định cho import không ghi URL |
| Vị trí thường gặp | <code>application.yml</code> hoặc cấu hình được nạp sớm | <code>bootstrap.yml</code>, biến môi trường hoặc tham số khởi chạy |
| Kích hoạt việc nạp | Có, thông qua scheme <code>configserver:</code> | Không tự thay thế cơ chế kích hoạt; cần bootstrap hoặc Config Data import |
| Khai báo URL | Có thể ghi trực tiếp sau scheme | Giá trị thuộc tính URI |
| Optional | Có thể dùng tiền tố <code>optional:</code> | Dùng chính sách fail-fast/optional tương ứng với cơ chế client đang chạy |
| Hướng dùng | Phù hợp với ứng dụng mới theo Config Data API | Phù hợp với cấu hình bootstrap cũ hoặc URL mặc định của import |

Có thể nhớ theo cách sau:

- <code>spring.config.import</code> trả lời: **Config Server có tham gia vào quá trình nạp cấu hình không, và location cụ thể là gì?**
- <code>spring.cloud.config.uri</code> trả lời: **URL mặc định của Config Server là gì?**

Chúng có thể xuất hiện cùng nhau trong một ứng dụng Config Data API khi import không ghi URL. Khi import đã có URL cụ thể, không nên dùng URI khác như một cấu hình thay thế ngầm.

## 5. Bootstrap context truyền thống hoạt động ra sao?

Trước Config Data API, Spring Cloud Config Client thường dùng bootstrap context. Context này khởi tạo sớm, đọc cấu hình bootstrap và liên hệ Config Server trước khi application context chính được tạo.

Ví dụ cấu trúc:

~~~text
orders-service/
├── src/main/resources/
│   ├── bootstrap.yml
│   └── application.yml
└── build.gradle
~~~

<code>bootstrap.yml</code>:

~~~yaml
spring:
  application:
    name: orders-service
  cloud:
    config:
      uri: https://config.internal
      label: release-2026.11
      fail-fast: true
~~~

<code>application.yml</code> có thể chứa cấu hình cục bộ khác:

~~~yaml
server:
  port: 8081
~~~

Trong mô hình này, Config Client thực hiện request sớm bằng tên ứng dụng và các thông tin có trong bootstrap context. Các property source từ xa được đưa vào môi trường cấu hình để application context chính sử dụng.

Để bootstrap hoạt động trong các phiên bản Spring Cloud hiện đại, dự án có thể cần dependency:

~~~groovy
dependencies {
    implementation("org.springframework.cloud:spring-cloud-starter-config")
    implementation("org.springframework.cloud:spring-cloud-starter-bootstrap")
}
~~~

Dependency chính xác và cách bật bootstrap phụ thuộc phiên bản Spring Cloud BOM của dự án. Nếu dự án đang dùng một phiên bản cũ mà bootstrap đã được bật theo mặc định, không cần thêm dependency một cách máy móc. Kiểm tra dependency tree và tài liệu phiên bản trước khi thay đổi.

### fail-fast trong bootstrap

Với bootstrap, có thể đặt:

~~~yaml
spring:
  cloud:
    config:
      fail-fast: true
~~~

Khi Config Server không thể cung cấp cấu hình và fail-fast được bật, client dừng khởi động thay vì âm thầm tiếp tục. Đây là chính sách riêng của mô hình bootstrap truyền thống.

Không nhầm <code>spring.cloud.config.fail-fast</code> với tiền tố <code>optional:</code> của Config Data API. Hai cơ chế thuộc hai cách nạp cấu hình khác nhau. Khi chuyển sang Config Data API, hãy xác định rõ import bắt buộc hay optional và kiểm tra cách retry được cấu hình trong phiên bản đó.

## 6. Cấu hình hiện đại bằng Config Data API

Một cấu hình client hiện đại có thể viết trong <code>application.yml</code>:

~~~yaml
spring:
  application:
    name: orders-service
  profiles:
    active: prod
  config:
    import: "configserver:https://config.internal"
  cloud:
    config:
      label: release-2026.11
~~~

Cấu hình này thể hiện:

- Tên ứng dụng là <code>orders-service</code>.
- Profile đang hoạt động là <code>prod</code>.
- Client nạp Config Server tại URL <code>https://config.internal</code>.
- Client yêu cầu label <code>release-2026.11</code>.

Nếu server là bắt buộc, giữ location không có <code>optional:</code>. Nếu server có thể vắng mặt trong một số môi trường và client có fallback an toàn, có thể dùng:

~~~yaml
spring:
  config:
    import: "optional:configserver:https://config.internal"
~~~

Trong môi trường production, nếu Config Server là nguồn duy nhất cung cấp thông tin kết nối hoặc secret bắt buộc, nên dùng import bắt buộc và validation để phát hiện thiếu cấu hình ngay lúc khởi động.

### Không cần đặt URL hai lần

Một cấu hình dễ gây nhầm:

~~~yaml
spring:
  config:
    import: "configserver:https://config-a.internal"
  cloud:
    config:
      uri: https://config-b.internal
~~~

Ở đây import đã chỉ rõ URL location là <code>config-a</code>. Không nên kỳ vọng <code>spring.cloud.config.uri</code> sẽ thay thế địa chỉ được ghi trực tiếp trong import. Hai giá trị khác nhau làm cấu hình khó bảo trì và gây nhầm khi chẩn đoán.

Nếu muốn dùng URI làm địa chỉ mặc định, viết:

~~~yaml
spring:
  config:
    import: "configserver:"
  cloud:
    config:
      uri: https://config.internal
~~~

Nếu muốn cấu hình đơn giản, ghi thẳng URL trong import và bỏ URI trùng lặp.

## 7. Application, profile và label không phải địa chỉ server

Một lỗi thường gặp là trộn URL server với thông tin xác định bộ cấu hình cần lấy.

Các thuộc tính có vai trò khác nhau:

| Thuộc tính | Mục đích | Ví dụ |
|---|---|---|
| <code>spring.config.import</code> | Bật location Config Server và có thể chứa URL | <code>configserver:https://config.internal</code> |
| <code>spring.cloud.config.uri</code> | Địa chỉ Config Server | <code>https://config.internal</code> |
| <code>spring.application.name</code> | Tên ứng dụng | <code>orders-service</code> |
| <code>spring.profiles.active</code> | Profile Spring đang hoạt động | <code>prod</code> |
| <code>spring.cloud.config.label</code> | Nhánh, tag hoặc commit cấu hình | <code>release-2026.11</code> |

Config Server thường phân giải request theo dạng:

~~~http
GET /{application}/{profile}/{label}
~~~

Ví dụ:

~~~http
GET https://config.internal/orders-service/prod/release-2026.11
~~~

URL cơ sở xác định nơi gửi request. Application/profile/label xác định bộ cấu hình cần lấy từ server. Nếu địa chỉ server đúng nhưng application name sai, client vẫn có thể kết nối thành công và nhận sai hoặc thiếu cấu hình.

## 8. Retry, nhiều server và bảo mật URL

### Retry khi server tạm thời không sẵn sàng

Một lỗi mạng ngắn hoặc Config Server vừa khởi động có thể khiến request đầu tiên thất bại. Spring Cloud Config hỗ trợ retry với các tùy chọn phụ thuộc cơ chế bootstrap hay Config Data API và phiên bản thư viện.

Với bootstrap, retry thường được cấu hình bằng các thuộc tính <code>spring.cloud.config.retry.*</code> và dependency retry phù hợp. Với Config Data API, một số tùy chọn có thể được truyền trong location import theo cú pháp mà phiên bản hỗ trợ.

Không nên thêm retry vô hạn. Hãy giới hạn số lần thử, thời gian chờ và tổng thời gian khởi động. Retry có thể xử lý lỗi tạm thời, nhưng không sửa được URL sai, DNS sai cố định hoặc credential hết hạn.

### Nhiều Config Server

Một số hệ thống cần nhiều địa chỉ Config Server để tăng khả năng sẵn sàng. <code>spring.cloud.config.uri</code> trong các mô hình hỗ trợ có thể nhận danh sách URL phân tách bằng dấu phẩy. Hành vi failover, thứ tự thử và việc chuyển sang server tiếp theo phụ thuộc phiên bản và cấu hình client.

Không giả định rằng nhiều URL tự động đồng nghĩa cân bằng tải hoặc đồng bộ dữ liệu. Các server cần dùng cùng nguồn cấu hình, cùng policy xác thực và phiên bản backend phù hợp. Nếu một server trả commit cũ trong khi server khác đã cập nhật, client có thể nhận cấu hình không nhất quán.

Với Config Data API, nếu cần nhiều location, khai báo theo cú pháp nhiều import được phiên bản hỗ trợ và kiểm tra thứ tự property source. Không sao chép cú pháp danh sách của bootstrap sang import nếu chưa xác nhận tài liệu phiên bản.

### Không nhúng credential vào URL

Tránh khai báo:

~~~yaml
spring:
  config:
    import: "configserver:https://user:password@config.internal"
~~~

Credential có thể bị lộ qua cấu hình, log, exception hoặc thông tin chẩn đoán. Dùng cơ chế xác thực của Config Client, biến môi trường hoặc secret manager để cấp thông tin xác thực. Với HTTPS, xác minh chứng thư của Config Server; không tắt TLS verification để chữa lỗi tạm thời.

Nếu URL được cấp qua biến môi trường, chỉ ghi nhận hostname và trạng thái cấu hình khi chẩn đoán, không in token hoặc password.

## 9. Chuyển từ bootstrap URI sang Config Data import

Khi nâng cấp ứng dụng từ cấu hình bootstrap truyền thống sang Config Data API, cần chuyển đổi có kiểm soát.

Giả sử cấu hình cũ:

~~~yaml
# bootstrap.yml
spring:
  application:
    name: orders-service
  cloud:
    config:
      uri: https://config.internal
      label: release-2026.11
      fail-fast: true
~~~

Cấu hình mới có thể là:

~~~yaml
# application.yml
spring:
  application:
    name: orders-service
  config:
    import: "configserver:https://config.internal"
  cloud:
    config:
      label: release-2026.11
~~~

Các bước chuyển đổi:

1. Xác định phiên bản Spring Boot và Spring Cloud đang dùng; chọn phiên bản tương thích với Config Data API.
2. Xác nhận dependency <code>spring-cloud-starter-config</code> và loại bỏ bootstrap starter nếu không còn dùng bootstrap cho mục đích khác.
3. Chuyển URL từ <code>spring.cloud.config.uri</code> sang URL tường minh trong <code>spring.config.import</code> hoặc giữ URI làm URL mặc định của import rỗng.
4. Chuyển application name, profile, label và thông tin xác thực sang các nguồn được nạp đúng thời điểm.
5. Chọn import bắt buộc hay optional theo chính sách production.
6. Kiểm tra retry và fail-fast theo cơ chế mới; không sao chép thuộc tính cũ mà không xác nhận.
7. Khởi động ứng dụng trong môi trường thử nghiệm và xác nhận request thực tế, property source và giá trị bind.
8. Khi đã xác nhận không còn phụ thuộc bootstrap, loại bỏ tệp hoặc dependency bootstrap không dùng.

Nếu ứng dụng cần bootstrap context cho một tích hợp khác, không xóa bootstrap một cách máy móc. Có thể tiếp tục dùng bootstrap theo thiết kế của dự án, nhưng cần tránh để Config Client được kích hoạt đồng thời qua bootstrap và Config Data import mà không có chủ đích.

## 10. Lỗi thường gặp khi khai báo địa chỉ

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| Client gọi <code>localhost:8888</code> ngoài dự kiến | Import không có URL và không có URI mặc định được nạp | Kiểm tra <code>spring.cloud.config.uri</code> và giá trị runtime |
| Có <code>spring.cloud.config.uri</code> nhưng không thấy request | Chưa kích hoạt bootstrap hoặc chưa khai báo Config Data import | Kiểm tra cơ chế nạp cấu hình đang dùng |
| Client gọi nhầm server | URL trong import khác URI mặc định | Xác định location import có URL tường minh hay không |
| Bootstrap không đọc <code>bootstrap.yml</code> | Bootstrap chưa được bật hoặc thiếu starter cần thiết | Kiểm tra dependency và cờ bootstrap theo phiên bản |
| Client gọi Config Server hai lần | Cả bootstrap và Config Data API cùng kích hoạt Config Client | Kiểm tra starter, import và bootstrap settings |
| Ứng dụng khởi động dù Config Server lỗi | Import có <code>optional:</code> hoặc fallback được bật | Xác nhận đây có phải chính sách mong muốn |
| Ứng dụng dừng khi Config Server tạm thời lỗi | Import bắt buộc hoặc fail-fast, retry chưa phù hợp | Kiểm tra timeout/retry và readiness của server |
| Kết nối được nhưng nhận cấu hình sai | Application, profile hoặc label không đúng | Kiểm tra request path và property source |
| TLS handshake thất bại | Chứng thư, hostname hoặc truststore không đúng | Kiểm tra certificate chain và hostname |
| Nhiều replica nhận giá trị khác nhau | URI trỏ tới server có trạng thái repository khác nhau | So sánh version/ref trên các Config Server |

Khi debug, hãy ghi nhận:

- Cơ chế đang chạy: Config Data API hay bootstrap.
- URL mà client thực sự gọi.
- Application, profile và label.
- HTTP status và request ID.
- Danh sách property source, không in nội dung secret.
- Phiên bản Git/ref được server phục vụ nếu có.

Không kết luận từ nội dung tệp cấu hình dự kiến. Hãy kiểm tra log khởi động hoặc request thực tế để biết client đã nạp URL nào.

## 11. Ví dụ cấu hình hoàn chỉnh cho hai mô hình

### Mô hình A: Config Data API với URL trong import

~~~yaml
spring:
  application:
    name: inventory-service
  profiles:
    active: prod
  config:
    import: "configserver:https://config.internal"
  cloud:
    config:
      label: release-2026.11
~~~

Đây là lựa chọn rõ ràng khi ứng dụng dùng Config Data API. Location và URL nằm cùng một khai báo.

### Mô hình B: Config Data API với URI mặc định

~~~yaml
spring:
  application:
    name: inventory-service
  config:
    import: "optional:configserver:"
  cloud:
    config:
      uri: https://config.internal
      label: release-2026.11
~~~

Import kích hoạt Config Server và <code>spring.cloud.config.uri</code> cung cấp URL mặc định. Do có <code>optional:</code>, ứng dụng có thể tiếp tục khi không lấy được nguồn từ xa; chỉ dùng khi fallback an toàn.

### Mô hình C: Bootstrap context truyền thống

~~~yaml
# bootstrap.yml
spring:
  application:
    name: inventory-service
  cloud:
    config:
      uri: https://config.internal
      label: release-2026.11
      fail-fast: true
~~~

Mô hình này cần bootstrap infrastructure được bật và dependency tương thích. Không thêm <code>spring.config.import</code> cùng lúc nếu mục tiêu là chỉ dùng bootstrap.

## 12. Checklist lựa chọn và vận hành

- [ ] Đã xác định ứng dụng dùng Config Data API hay bootstrap context.
- [ ] Nếu dùng Config Data API, đã khai báo <code>spring.config.import</code> với scheme <code>configserver:</code>.
- [ ] Nếu import không ghi URL, đã cấu hình đúng <code>spring.cloud.config.uri</code> làm địa chỉ mặc định.
- [ ] Nếu import ghi URL tường minh, không khai báo URI khác gây nhầm lẫn.
- [ ] Nếu dùng bootstrap, đã bật bootstrap đúng cách cho phiên bản Spring Cloud.
- [ ] Application name, profile và label được cấp đúng với môi trường triển khai.
- [ ] Đã chọn import bắt buộc hay optional dựa trên mức độ thiết yếu của cấu hình.
- [ ] Retry, timeout và fail-fast có giới hạn và đã được kiểm thử.
- [ ] Không nhúng username, password hoặc token vào URL.
- [ ] HTTPS và truststore được cấu hình đúng.
- [ ] Không vô tình kích hoạt cả bootstrap và Config Data API làm client tải cấu hình hai lần.
- [ ] Đã kiểm tra URL thực tế, property source và giá trị bind sau khởi động.
- [ ] Các Config Server replica có cấu hình backend và phiên bản dữ liệu nhất quán.

<code>spring.config.import</code> và <code>spring.cloud.config.uri</code> giải quyết hai phần khác nhau của việc kết nối Config Server: một bên khai báo location tham gia nạp cấu hình, bên kia cung cấp địa chỉ server. Chọn đúng cơ chế theo phiên bản Spring Boot/Spring Cloud, khai báo URL ở một nơi rõ ràng và xác minh request thực tế sẽ giúp Config Client nạp đúng cấu hình ngay từ giai đoạn khởi động.

