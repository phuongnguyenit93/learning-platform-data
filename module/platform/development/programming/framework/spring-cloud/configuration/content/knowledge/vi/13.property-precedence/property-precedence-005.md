# Tác động của server.overrides lên giá trị client nhận được

Spring Cloud Config Server có thể bổ sung một nhóm thuộc tính dùng chung cho mọi Config Client thông qua **spring.cloud.config.server.overrides**. Đây là cơ chế để người vận hành đặt các giá trị do nền tảng quản lý, chẳng hạn một mã môi trường, thông tin liên hệ vận hành hoặc một số thiết lập mặc định cần nhất quán giữa các ứng dụng.

Các thuộc tính này được gửi cùng cấu hình của từng client và có độ ưu tiên cao theo mặc định. Vì vậy, nếu repository của ứng dụng hoặc file cấu hình local khai báo cùng một khóa, client thường nhận giá trị từ **server.overrides**. Có thể thay đổi cách ưu tiên để các ứng dụng được phép cung cấp giá trị riêng trong một số trường hợp.

Bài học này tập trung vào tác động thực tế của **server.overrides**: giá trị nào được gửi đến client, khi nào nó thắng cấu hình khác, cách cho phép client thay thế giá trị, và giới hạn của cơ chế này.

Sau bài học, bạn có thể:

- Khai báo bản đồ thuộc tính **spring.cloud.config.server.overrides** trên Config Server.
- Giải thích vì sao cùng một giá trị override xuất hiện ở nhiều Config Client.
- Dự đoán giá trị client nhận được khi khóa bị khai báo ở nhiều nguồn.
- Dùng placeholder để tạo giá trị mặc định có thể tùy biến theo từng ứng dụng.
- Phân biệt server overrides với các cờ điều khiển thứ tự ưu tiên của remote property sources.
- Kiểm tra kết quả qua Config Server và Config Client, đồng thời tránh dùng overrides như một cơ chế bảo mật bắt buộc.

## 1. server.overrides được khai báo ở đâu?

**server.overrides** là một tính năng của Config Server. Người vận hành khai báo một map gồm các cặp tên thuộc tính và giá trị trong cấu hình của chính Config Server:

~~~yaml
spring:
  cloud:
    config:
      server:
        overrides:
          platform.company-code: "ACME"
          platform.support-channel: "#platform-support"
          feature.audit.enabled: true
          logging.level.root: INFO
~~~

Khi Config Server trả cấu hình cho một ứng dụng bất kỳ, các thuộc tính trên được đưa vào Environment mà client nhận được. Ví dụ, cả **order-service**, **inventory-service** và **payment-service** đều nhận:

~~~properties
platform.company-code=ACME
platform.support-channel=#platform-support
feature.audit.enabled=true
logging.level.root=INFO
~~~

Tên application, profile hoặc label mà client yêu cầu không làm thay đổi phạm vi chung của map này. Nếu ba ứng dụng cùng kết nối đến một Config Server có cấu hình overrides như trên, chúng đều nhận các thuộc tính đó.

Cần phân biệt hai nơi cấu hình:

- **spring.cloud.config.server.overrides:** khai báo tại Config Server, áp dụng chung cho các Config Client mà server phục vụ.
- **application.yml**, **order-service-prod.yml** hoặc file tương tự trong repository cấu hình: cung cấp giá trị dùng chung, theo ứng dụng hoặc theo profile từ nguồn cấu hình mà Config Server đọc.

Overrides là một cơ chế tập trung ở tầng server. Không cần sao chép cùng một thuộc tính vào từng file ứng dụng trong Git để mọi client nhận nó.

## 2. Giá trị server.overrides ảnh hưởng đến client như thế nào?

Theo mặc định, các thuộc tính trong **server.overrides** được đặt ở vị trí ưu tiên cao đối với Config Client. Các cơ chế Spring Boot thông thường như file cấu hình local không thể vô tình ghi đè chúng.

Giả sử Config Server có:

~~~yaml
spring:
  cloud:
    config:
      server:
        overrides:
          platform.region: "ap-southeast"
          platform.banner: "Managed by platform"
~~~

Repository cấu hình của **order-service** có:

~~~yaml
platform:
  region: "order-region"
  banner: "Order team"
  timeout: 2s
~~~

Và file **application.yml** tại client có:

~~~yaml
platform:
  region: "local-region"
  banner: "Local development"
  timeout: 5s
~~~

Với chính sách ưu tiên mặc định, client nhận kết quả:

| Thuộc tính | Giá trị client nhận | Nguồn thắng |
|---|---|---|
| **platform.region** | **ap-southeast** | Config Server overrides |
| **platform.banner** | **Managed by platform** | Config Server overrides |
| **platform.timeout** | **2s** | Repository riêng của order-service |

Hai khóa có trong map overrides sẽ nhận giá trị do Config Server cung cấp. Khóa không có trong map tiếp tục được phân giải theo thứ tự ưu tiên bình thường giữa remote property sources và các nguồn local.

Điều này hữu ích khi tổ chức cần một số giá trị nhất quán giữa nhiều dịch vụ. Tuy nhiên, hãy chỉ đưa vào map các thuộc tính thực sự có phạm vi chung. Nếu đưa cả endpoint, timeout hoặc feature flag riêng của từng dịch vụ vào overrides, giá trị chung có thể che mất cấu hình được thiết kế riêng cho ứng dụng đó.

## 3. Luồng phân phối giá trị override

Có thể hình dung luồng xử lý như sau:

~~~mermaid
flowchart TD
    A["Cấu hình Config Server"] --> B["spring.cloud.config.server.overrides"]
    R["Git / backend cấu hình"] --> C["Remote property sources"]
    B --> D["Config Server tạo Environment"]
    C --> D
    D --> E["Config Client nhận Environment"]
    E --> F["Spring Environment hợp nhất property sources"]
    F --> G["@Value / @ConfigurationProperties / Environment"]
    G --> H["Mã ứng dụng sử dụng giá trị"]
~~~

Config Server gửi thuộc tính override cùng Environment trả về. Client nhận các property sources và Spring phân giải giá trị theo thứ tự ưu tiên. Khi mã ứng dụng đọc một khóa bằng **Environment**, **@Value** hoặc **@ConfigurationProperties**, nó nhận giá trị đã thắng sau quá trình phân giải.

Có hai bước cần kiểm tra riêng:

1. Config Server có đưa khóa và giá trị override vào response hay không.
2. Config Client có phân giải khóa thành giá trị mong đợi hay không.

Nếu response từ Config Server đã chứa giá trị đúng nhưng ứng dụng vẫn hoạt động với giá trị khác, hãy kiểm tra Environment phía client và cách mã ứng dụng đọc hoặc sử dụng thuộc tính.

## 4. Cho phép giá trị môi trường ghi đè server.overrides

Trong một số trường hợp, tổ chức muốn **server.overrides** đóng vai trò giá trị mặc định chung, còn từng môi trường triển khai được phép thay thế bằng biến môi trường hoặc system property.

Tài liệu Spring Cloud Config cho phép thay đổi ưu tiên của các overrides bằng cách đặt **spring.cloud.config.overrideNone=true** trong remote repository. Mặc định thuộc tính này là **false**. Khi được áp dụng, các overrides có hành vi gần với giá trị mặc định hơn, cho phép ứng dụng cung cấp giá trị qua environment variables hoặc system properties.

Ví dụ trong repository cấu hình từ xa, chẳng hạn **application.yml**:

~~~yaml
spring:
  cloud:
    config:
      override-none: true
~~~

Config Server vẫn khai báo giá trị chung:

~~~yaml
spring:
  cloud:
    config:
      server:
        overrides:
          platform.region: "default-region"
~~~

Môi trường production có thể cấp biến:

~~~text
PLATFORM_REGION=ap-southeast
~~~

Hoặc dùng JVM system property:

~~~bash
java -Dplatform.region=ap-southeast -jar order-service.jar
~~~

Khi cơ chế ưu tiên tương ứng có hiệu lực, client có thể nhận **ap-southeast** thay cho giá trị mặc định **default-region**.

Cần nhớ rằng **spring.cloud.config.override-none** là một thiết lập được lấy từ remote repository, không phải một cờ có thể đặt tùy ý ở local để tự cấp quyền ghi đè. Hãy xác minh hành vi theo phiên bản Spring Cloud và cách client nạp cấu hình đang dùng, đặc biệt khi ứng dụng sử dụng Config Data import thay vì config-first bootstrap cũ.

## 5. Placeholder giúp tạo giá trị chung nhưng vẫn tùy biến

Không phải lúc nào tổ chức cũng muốn một giá trị cứng áp dụng cho tất cả ứng dụng. Có thể dùng placeholder để server cung cấp giá trị mặc định, trong khi client có quyền đưa vào giá trị riêng.

Ví dụ Config Server khai báo:

~~~yaml
spring:
  cloud:
    config:
      server:
        overrides:
          platform.welcome-message: '\${app.welcome-message:Welcome from platform}'
~~~

Dấu gạch chéo ngược trước placeholder của Spring giữ biểu thức để nó được phân giải ở phía client, thay vì bị xử lý ngay tại Config Server.

Ứng dụng **order-service** có thể khai báo trong cấu hình riêng:

~~~yaml
app:
  welcome-message: "Welcome to order service"
~~~

Khi client phân giải **platform.welcome-message**, placeholder đọc **app.welcome-message** từ Environment của client. Nếu ứng dụng không khai báo khóa đó, giá trị mặc định **Welcome from platform** được sử dụng.

| Client | app.welcome-message | platform.welcome-message sau phân giải |
|---|---|---|
| order-service | Welcome to order service | Welcome to order service |
| inventory-service | Welcome to inventory service | Welcome to inventory service |
| payment-service | Không khai báo | Welcome from platform |

Đây là cách hữu ích để định nghĩa một hợp đồng cấu hình chung nhưng vẫn cho phép mỗi ứng dụng cung cấp dữ liệu riêng.

Với YAML, có thể dùng scalar dạng single-quoted như ví dụ để giữ nguyên dấu gạch chéo ngược. Nếu khai báo overrides trong file properties, cần escape dấu gạch chéo ngược theo cú pháp properties để placeholder không bị xử lý sớm.

## 6. Phân biệt server.overrides với allowOverride và các cờ precedence

Các thuộc tính có tên gần giống nhau nhưng giải quyết các vấn đề khác nhau. Cần tránh coi chúng là một công tắc duy nhất.

| Thuộc tính | Nơi khai báo | Vai trò |
|---|---|---|
| **spring.cloud.config.server.overrides** | Cấu hình của Config Server | Tạo các giá trị chung gửi đến mọi Config Client |
| **spring.cloud.config.override-none** | Remote repository | Điều chỉnh overrides theo hướng giống giá trị mặc định, cho phép các nguồn như environment variables hoặc system properties cung cấp giá trị riêng theo tài liệu Config Server |
| **spring.cloud.config.allow-override** | Remote property source | Cấp quyền cho client ghi đè remote properties trong cơ chế config-first bootstrap |
| **spring.cloud.config.override-system-properties** | Remote property source | Điều chỉnh việc system properties, environment variables và command-line arguments có thể đứng trước remote properties hay không |

Trong cơ chế config-first bootstrap, remote property source mặc định có ưu tiên cao hơn local property sources. Nếu muốn ứng dụng ghi đè remote properties, remote property source phải cấp quyền bằng:

~~~yaml
spring:
  cloud:
    config:
      allow-override: true
~~~

Khi **allow-override=true**, hai cờ sau quyết định vị trí tương đối của remote properties:

| Cấu hình | Kết quả trong config-first bootstrap |
|---|---|
| **override-none=true** | Remote properties có ưu tiên thấp nhất; các nguồn local, bao gồm file cấu hình, environment variables, system properties và command line, có thể ghi đè |
| **override-none=false**, **override-system-properties=true** | System properties, environment variables và command line có thể ghi đè; local config files không ghi đè remote properties |
| **override-none=false**, **override-system-properties=false** | System properties, environment variables và command line vẫn có thể ghi đè; local config files không ghi đè remote properties |

Các cờ **allow-override**, **override-none** và **override-system-properties** phải được đặt trong remote property source để điều khiển precedence theo cơ chế bootstrap. Đặt **allow-override** trong file local không cấp quyền ghi đè remote property source.

Đây là quy tắc của cơ chế config-first bootstrap được Spring Cloud mô tả. Với ứng dụng sử dụng Config Data import hiện đại, hãy kiểm tra tài liệu đúng phiên bản và thử nghiệm property source thực tế thay vì áp dụng nguyên xi mọi giả định của bootstrap cũ.

## 7. server.overrides không phải cơ chế cưỡng chế bảo mật

Tên gọi **overrides** có thể khiến người vận hành nghĩ rằng ứng dụng bắt buộc phải tuân theo giá trị do server đặt. Thực tế, Spring Cloud Config phân phối dữ liệu cấu hình; nó không thể buộc mã ứng dụng phải sử dụng dữ liệu đó.

Một Config Client có thể:

- Đọc khóa bằng Spring Environment và sử dụng giá trị đã phân giải.
- Không đọc khóa đó và dùng một giá trị hard-code.
- Tự ghi đè hoặc chuyển đổi giá trị trong logic ứng dụng.
- Sử dụng một nguồn cấu hình riêng nằm ngoài Spring Environment.

Vì vậy, tài liệu chính thức lưu ý rằng overrides không thể được thực thi tuyệt đối. Chúng cung cấp hành vi mặc định hữu ích cho các Spring Cloud Config Client tuân theo cơ chế cấu hình chuẩn.

Không dùng **server.overrides** làm ranh giới bảo mật duy nhất cho các chính sách như xác thực bắt buộc, quyền truy cập dữ liệu, mã hóa hoặc giới hạn giao dịch. Những chính sách này cần được kiểm tra và cưỡng chế ở tầng ứng dụng, Spring Security, gateway hoặc hệ thống hạ tầng có trách nhiệm tương ứng.

Cũng không nên dùng map overrides để phát tán mật khẩu, private key hoặc token. Vì map áp dụng cho mọi client, một giá trị bí mật có thể được phân phối rộng hơn phạm vi cần thiết. Hãy dùng secret manager và cơ chế cấp secret theo danh tính ứng dụng.

## 8. Chọn thuộc tính nào để đưa vào overrides?

Một thuộc tính phù hợp với **server.overrides** thường có các đặc điểm:

- Có ý nghĩa với hầu hết hoặc tất cả Config Client do Config Server phục vụ.
- Có một owner ở cấp nền tảng hoặc vận hành.
- Không phụ thuộc sâu vào nghiệp vụ riêng của một ứng dụng.
- Không chứa secret hoặc dữ liệu cần giới hạn theo danh tính.
- Có quy trình review và thông báo khi giá trị thay đổi.

Ví dụ có thể cân nhắc:

| Thuộc tính | Mức độ phù hợp | Lý do |
|---|---|---|
| **platform.support-channel** | Phù hợp | Thông tin liên hệ vận hành dùng chung |
| **platform.organization-code** | Phù hợp nếu toàn bộ client cùng tổ chức | Giá trị định danh chung |
| **logging.pattern.correlation** | Có thể phù hợp | Chuẩn log tương quan nếu mọi ứng dụng hỗ trợ |
| **order.payment.timeout** | Không phù hợp cho toàn bộ client | Chỉ thuộc miền order/payment |
| **spring.datasource.password** | Không phù hợp | Secret phải được cấp theo ứng dụng |
| **security.authentication.required** | Không nên chỉ dựa vào override | Chính sách bắt buộc phải được cưỡng chế ở tầng bảo mật |

Nếu chỉ một số ứng dụng cần giá trị, hãy cân nhắc cấu hình theo application/profile trong repository thay vì đưa vào map global. Điều đó làm rõ phạm vi áp dụng và giảm nguy cơ thay đổi một khóa gây ảnh hưởng ngoài dự kiến.

## 9. Kiểm tra giá trị mà client thực sự nhận

Khi thêm một khóa vào **server.overrides**, hãy kiểm tra cả response của Config Server lẫn Environment phía client.

Ví dụ gọi Config Server:

~~~bash
curl --fail --show-error \
  "http://localhost:8888/order-service/prod/main"
~~~

Trong response, tìm property source chứa các giá trị được server gửi và kiểm tra **platform.region**. Cấu trúc response có application, profile, label, version/state và danh sách property sources. Tên và thứ tự property sources giúp xác định nguồn nào đang cung cấp khóa.

Nếu Actuator được bật và bảo vệ, có thể kiểm tra riêng thuộc tính phía client:

~~~text
GET /actuator/env/platform.region
~~~

Endpoint **env** có thể tiết lộ thông tin cấu hình, vì vậy chỉ expose trên mạng quản trị, yêu cầu xác thực và giới hạn quyền truy cập. Không bật endpoint công khai chỉ để debug.

Một bài kiểm thử hữu ích nên có ít nhất ba giá trị cạnh tranh cho cùng một khóa:

1. Giá trị trong **server.overrides**.
2. Giá trị trong remote repository của ứng dụng.
3. Giá trị trong file local hoặc environment variable của client.

Chạy kiểm thử theo chính sách mặc định, sau đó bật cơ chế cho phép override và so sánh kết quả. Ghi lại phiên bản Spring Cloud, cách nạp cấu hình và property source cuối cùng để kết quả có thể tái lập.

## 10. Thay đổi overrides trong môi trường nhiều Config Server

Nếu Config Server chạy nhiều replica, tất cả replica cần dùng cùng một bộ **server.overrides**. Nếu mỗi instance có map khác nhau, cùng một Config Client có thể nhận giá trị khác nhau tùy instance mà request được định tuyến đến.

Hãy quản lý map overrides như một phần của cấu hình nền tảng:

1. Lưu thay đổi trong cấu hình triển khai có review.
2. Xác định ứng dụng và môi trường chịu ảnh hưởng.
3. Triển khai đồng nhất đến các Config Server replica.
4. Gọi endpoint Config Server qua từng replica hoặc qua từng đường truy cập cần kiểm tra.
5. Xác nhận các client nhận cùng giá trị.
6. Theo dõi lỗi sau thay đổi và giữ bản cấu hình trước đó để rollback.

Việc cập nhật map ở Config Server không tự bảo đảm mọi client đang chạy lập tức thay đổi giá trị trong bean. Client cần cơ chế nạp lại hoặc refresh phù hợp; các bean đã giữ giá trị tại thời điểm khởi tạo có thể cần được refresh hoặc restart theo thiết kế ứng dụng.

## 11. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Client nào cũng nhận cùng một giá trị | Khóa nằm trong map **server.overrides** global | Xác nhận phạm vi global có đúng ý định không |
| Local config không ghi đè được | Overrides đang có ưu tiên cao theo mặc định | Kiểm tra **overrideNone** trong remote repository và chế độ nạp cấu hình |
| Đặt **allow-override** local nhưng vẫn không ghi đè được | Quyền phải được cấp trong remote property source ở config-first bootstrap | Đưa cờ vào remote repository và kiểm tra đúng bootstrap mode |
| Placeholder bị thay thế ở Config Server | Thiếu dấu escape trước placeholder | Giữ placeholder bằng dấu gạch chéo ngược trước ký hiệu dollar để client phân giải |
| Client nhận giá trị khác response server | Có property source hoặc logic ứng dụng khác tác động | Kiểm tra **/actuator/env** có bảo vệ và cách mã ứng dụng đọc giá trị |
| Các replica Config Server trả giá trị khác nhau | Overrides không đồng nhất giữa các instance | Đồng bộ cấu hình triển khai và kiểm tra từng replica |
| Thay override nhưng bean vẫn giữ giá trị cũ | Bean đã giữ giá trị lúc khởi tạo hoặc chưa refresh | Kiểm tra vòng đời bean, refresh scope và yêu cầu restart |
| Nghĩ rằng override buộc ứng dụng tuân thủ chính sách | Coi dữ liệu cấu hình như cơ chế enforcement | Thực hiện kiểm tra bắt buộc ở ứng dụng hoặc tầng bảo mật |

## 12. Tự kiểm tra

1. **spring.cloud.config.server.overrides** được khai báo ở Config Server hay trong repository của từng ứng dụng?
2. Vì sao một khóa trong server overrides có thể thắng giá trị cùng tên ở remote repository và local application.yml?
3. Mặc định **spring.cloud.config.overrideNone** có giá trị gì và tác động của nó là gì?
4. Vì sao cần escape placeholder của Spring khi khai báo trong server overrides?
5. **allow-override** khác gì với **server.overrides**?
6. Vì sao không nên dùng server overrides làm cơ chế cưỡng chế xác thực hoặc phân quyền?
7. Nếu có ba Config Server replica, cần kiểm tra điều gì để bảo đảm client nhận giá trị nhất quán?
8. Vì sao cần kiểm tra cả Config Server response và Environment phía client?

Hãy tạo một Config Server thử nghiệm với hai khóa trong **server.overrides**. Đặt cùng khóa trong file cấu hình remote và local của Config Client, rồi quan sát giá trị cuối cùng. Tiếp đó, thử cấu hình **override-none** trong remote repository và dùng environment variable để thay giá trị. Cuối cùng, thử placeholder có escape để mỗi client cung cấp thông điệp riêng. Ghi lại property source và kết quả trong từng lần chạy; thực hiện với dữ liệu giả lập và không dùng secret thật.

## Tài liệu tham khảo

- [Spring Cloud Config — Property Overrides](https://docs.spring.io/spring-cloud-config/reference/server/environment-repository/property-overrides.html)
- [Spring Cloud Config — Using Bootstrap To Override Properties](https://docs.spring.io/spring-cloud-config/reference/server/environment-repository/using-bootstrap-to-override-properties.html)
- [Spring Cloud Commons — Overriding the Values of Remote Properties](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/application-context-services.html)

