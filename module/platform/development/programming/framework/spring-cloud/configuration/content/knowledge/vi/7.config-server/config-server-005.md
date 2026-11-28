# Cấu hình accept-empty và hành vi khi không tìm thấy ứng dụng

Config Server nhận yêu cầu cấu hình theo tên ứng dụng, profile và label. Trong một số trường hợp, request tới được máy chủ và được xử lý bình thường nhưng repository không có thuộc tính nào phù hợp với yêu cầu. Khi đó, Config Server có thể trả về một Environment rỗng thay vì báo lỗi HTTP. Hành vi này được điều khiển bằng thuộc tính <code>spring.cloud.config.server.accept-empty</code>.

Lựa chọn này ảnh hưởng trực tiếp tới cách Config Client khởi động và cách nhóm phát hiện lỗi đặt sai tên ứng dụng, thiếu tệp cấu hình hoặc chọn nhầm nguồn. Nếu server trả HTTP 200 với danh sách property source rỗng, client có thể tiếp tục với cấu hình cục bộ hoặc giá trị mặc định. Điều đó có thể phù hợp với một số ứng dụng tùy chọn, nhưng nguy hiểm với dịch vụ cần cấu hình tập trung để kết nối đúng hạ tầng hoặc áp dụng chính sách bảo mật.

Bài học này giải thích ý nghĩa của <code>accept-empty</code>, phân biệt Environment rỗng với cấu hình dùng chung, mô tả phản hồi khi không tìm thấy cấu hình và cách thiết kế chính sách fail-fast, validation, giám sát và kiểm thử.

Sau bài học, bạn có thể:

- Giải thích <code>spring.cloud.config.server.accept-empty</code> và hành vi mặc định.
- Phân biệt ứng dụng không có tệp riêng với request thực sự không có property source.
- So sánh phản hồi Environment rỗng với HTTP 404.
- Nhận diện các tình huống application name sai nhưng server vẫn trả cấu hình dùng chung.
- Phối hợp chính sách của Config Server với cách Config Client xử lý lỗi.
- Kiểm thử và giám sát việc thiếu cấu hình bắt buộc.

## 1. Config Server xử lý yêu cầu không tìm thấy cấu hình

Config Client thường gửi request theo dạng:

~~~http
GET /{application}/{profile}/{label}
~~~

Ví dụ:

~~~http
GET /orders-service/prod/release-2026.11
~~~

Trong đó:

- <code>application</code> là tên ứng dụng, thường được lấy từ <code>spring.application.name</code>.
- <code>profile</code> là profile mà client yêu cầu, ví dụ <code>dev</code>, <code>staging</code> hoặc <code>prod</code>.
- <code>label</code> là nhánh, tag hoặc commit trong nguồn cấu hình, thường là Git.

Config Server dùng các thông tin này để tìm property source trong repository. Nếu tìm thấy, server trả về một đối tượng Environment chứa thông tin request và các nguồn cấu hình. Nếu không tìm thấy nguồn phù hợp, kết quả phụ thuộc vào chính sách <code>accept-empty</code>.

Điểm cần hiểu là Config Server đang trả lời câu hỏi: **repository có cung cấp nguồn cấu hình nào cho request này không?** Nó không tự hiểu rằng một ứng dụng có bắt buộc phải có các khóa nghiệp vụ cụ thể hay không. Việc một response có property source không đồng nghĩa ứng dụng đã nhận đủ tất cả thuộc tính cần thiết.

## 2. Ý nghĩa của accept-empty

Thuộc tính cấu hình trên Config Server là:

~~~yaml
spring:
  cloud:
    config:
      server:
        accept-empty: true
~~~

Theo hành vi mặc định phổ biến, <code>accept-empty</code> là <code>true</code>. Khi không tìm thấy cấu hình phù hợp và Environment không có property source nào, server chấp nhận request và trả về Environment rỗng, thường với HTTP 200 OK.

Nếu đặt thành <code>false</code>:

~~~yaml
spring:
  cloud:
    config:
      server:
        accept-empty: false
~~~

Config Server trả HTTP 404 Not Found khi không tìm thấy cấu hình và kết quả là Environment rỗng. Client nhận được một trạng thái HTTP thể hiện rõ request không có cấu hình.

Bảng so sánh:

| Cấu hình | Khi Environment thực sự rỗng | Ý nghĩa |
|---|---|---|
| <code>accept-empty: true</code> | Trả Environment rỗng, thường HTTP 200 | Request được chấp nhận dù không có property source |
| <code>accept-empty: false</code> | Trả HTTP 404 Not Found | Không chấp nhận kết quả cấu hình rỗng |

Ví dụ phản hồi rỗng có thể có dạng minh họa:

~~~json
{
  "name": "unknown-service",
  "profiles": ["prod"],
  "label": "release-2026.11",
  "propertySources": []
}
~~~

Cấu trúc thực tế có thể có thêm metadata như version hoặc state tùy backend và phiên bản. Điều quan trọng là danh sách <code>propertySources</code> rỗng: không có nguồn thuộc tính nào được trả về cho request.

Với <code>accept-empty: false</code>, cùng request không có nguồn cấu hình sẽ nhận HTTP 404. Client và hệ thống giám sát có thể phân biệt rõ hơn tình huống thiếu cấu hình với request thành công.

## 3. Không có tệp riêng cho ứng dụng chưa chắc là Environment rỗng

Đây là điểm dễ gây hiểu nhầm nhất.

Trong Spring Cloud Config, tệp <code>application.yml</code> có thể cung cấp cấu hình dùng chung cho nhiều ứng dụng. Vì vậy, một ứng dụng không có tệp riêng vẫn có thể nhận được cấu hình từ nguồn chung.

Ví dụ repository:

~~~text
config-repo/
├── application.yml
├── application-prod.yml
├── orders-service.yml
└── inventory-service.yml
~~~

Nếu client gửi:

~~~http
GET /payment-service/prod/main
~~~

nhưng repository không có <code>payment-service.yml</code>, server vẫn có thể tìm thấy <code>application.yml</code> hoặc <code>application-prod.yml</code>. Khi đó Environment không rỗng vì có property source dùng chung. <code>accept-empty: false</code> không có nghĩa server bắt buộc phải tìm thấy một tệp riêng mang tên application trước khi trả cấu hình.

Ví dụ nguồn dùng chung:

~~~yaml
# application.yml
logging:
  level:
    root: INFO

platform:
  tracing-enabled: true
~~~

Một ứng dụng mới chưa có tệp riêng vẫn có thể nhận các thuộc tính trên. Điều này hữu ích khi nhóm muốn mọi dịch vụ mới thừa hưởng mặc định nền tảng.

Ngược lại, nếu repository không có cấu hình chung phù hợp và cũng không có tệp cho ứng dụng/profile được yêu cầu, Environment mới có thể thực sự rỗng. Khi đó <code>accept-empty</code> quyết định server trả Environment rỗng hay HTTP 404.

Do đó, cần phân biệt ba tình huống:

1. **Không có tệp riêng, nhưng có cấu hình chung:** server trả cấu hình chung; Environment không rỗng.
2. **Có tệp riêng hoặc nguồn phù hợp:** server trả các property source tương ứng.
3. **Không có bất kỳ property source phù hợp nào:** Environment rỗng; hành vi phụ thuộc <code>accept-empty</code>.

## 4. Khi nào một ứng dụng có thể bị xem là không tìm thấy?

Có nhiều nguyên nhân khiến request không nhận được cấu hình riêng mong đợi:

- Client gửi sai <code>spring.application.name</code>.
- Tên tệp trong repository không khớp tên application.
- Profile được gửi không đúng quy ước, ví dụ <code>production</code> trong khi tệp dùng hậu tố <code>prod</code>.
- Label trỏ tới nhánh hoặc tag không chứa tệp cần thiết.
- Tệp nằm ngoài thư mục tìm kiếm được khai báo bằng <code>search-paths</code>.
- Repository không có tệp chung lẫn tệp riêng phù hợp.
- Cấu hình đã được chuyển sang repository khác nhưng Config Server chưa được cập nhật cách định tuyến.

Không phải mọi nguyên nhân trên đều dẫn tới cùng một HTTP status. Ví dụ, label không tồn tại có thể làm Git backend phát sinh lỗi khi resolve ref. Repository không truy cập được có thể tạo lỗi backend. Các lỗi xác thực, mạng, TLS, parse hoặc fetch Git cũng có cách biểu hiện riêng.

<code>accept-empty</code> xử lý trường hợp kết quả phân giải không có property source. Nó không phải cơ chế tổng quát để biến mọi lỗi backend thành HTTP 404, và cũng không thay thế kiểm tra label, credential hoặc kết nối Git.

### Sai application name nhưng vẫn có response 200

Giả sử ứng dụng cần cấu hình riêng từ <code>orders-service-prod.yml</code>, nhưng client lại gửi tên <code>order-service</code>. Nếu repository có <code>application.yml</code>, Config Server có thể trả cấu hình chung và HTTP 200.

Ứng dụng khi đó có thể khởi động với các mặc định chung nhưng thiếu URL kho hàng, topic hoặc giới hạn nghiệp vụ của orders. Đây là một lỗi cấu hình thực tế dù request không rỗng.

Vì vậy, HTTP 200 chỉ xác nhận server đã trả một response thành công. Nó không chứng minh application name đúng hoặc ứng dụng đã nhận đủ các thuộc tính bắt buộc.

## 5. Cấu hình accept-empty trên Config Server

Ví dụ cấu hình Git backend với chính sách không chấp nhận Environment rỗng:

~~~yaml
server:
  port: 8888

spring:
  cloud:
    config:
      server:
        accept-empty: false
        git:
          uri: https://git.example.com/platform/config-repo.git
          default-label: main
~~~

Thuộc tính <code>spring.cloud.config.server.accept-empty</code> nằm ở phía Config Server. Nó không phải cấu hình của Config Client.

Có thể đặt giá trị qua biến môi trường theo quy tắc relaxed binding của Spring Boot:

~~~text
SPRING_CLOUD_CONFIG_SERVER_ACCEPT_EMPTY=false
~~~

Khi triển khai nhiều Config Server instance, cần bảo đảm mọi replica sử dụng cùng chính sách. Nếu một instance đặt <code>true</code> và instance khác đặt <code>false</code>, cùng một request có thể nhận HTTP 200 hoặc 404 tùy load balancer định tuyến tới đâu. Điều này làm hành vi khó dự đoán và gây nhiễu khi giám sát.

Sau khi thay đổi cấu hình, xác nhận giá trị thực tế mà từng instance đã nạp. Không chỉ kiểm tra tệp triển khai hoặc biến môi trường dự kiến.

## 6. Chọn chính sách true hay false

Không có một giá trị phù hợp cho mọi hệ thống. Quyết định cần dựa trên việc một request không có cấu hình có được xem là trạng thái hợp lệ hay không.

### Khi chấp nhận Environment rỗng

<code>accept-empty: true</code> có thể hữu ích khi:

- Một số ứng dụng mới chưa có cấu hình riêng và chỉ cần nhận mặc định dùng chung.
- Có request hợp lệ trong giai đoạn khởi tạo hoặc đăng ký dịch vụ, khi repository chưa chứa tệp riêng.
- Một số ứng dụng tùy chọn có thể chạy với cấu hình cục bộ đã được kiểm soát.
- Hệ thống có cơ chế validation và cảnh báo riêng để phát hiện ứng dụng thiếu thuộc tính bắt buộc.

Tuy nhiên, nếu ứng dụng nhận Environment rỗng rồi tiếp tục chạy, nó có thể dùng giá trị mặc định hoặc cấu hình cục bộ. Chỉ chọn cách này khi các giá trị đó an toàn và đã được kiểm tra.

### Khi từ chối Environment rỗng

<code>accept-empty: false</code> thường phù hợp khi:

- Mọi request hợp lệ phải tìm thấy ít nhất một nguồn cấu hình.
- Thiếu cấu hình là lỗi triển khai cần phát hiện ngay.
- Dịch vụ phụ thuộc vào cấu hình tập trung để biết URL, datasource hoặc chính sách bảo mật.
- Nhóm muốn tránh ứng dụng khởi động âm thầm với cấu hình mặc định không mong đợi.

Với chính sách này, request không có property source sẽ nhận HTTP 404. Nhóm vận hành có thể phát hiện request sai hoặc thiếu cấu hình sớm hơn.

### Ma trận quyết định

| Bối cảnh | Hướng cân nhắc | Lý do |
|---|---|---|
| Dịch vụ production cần cấu hình bắt buộc | <code>false</code> | Thiếu nguồn cấu hình phải biểu hiện thành lỗi |
| Ứng dụng thử nghiệm có thể dùng mặc định an toàn | Có thể <code>true</code> | Chấp nhận một số request chưa có cấu hình riêng |
| Nền tảng có nhiều dịch vụ mới được tạo dần | Cân nhắc theo chính sách chung và validation từng dịch vụ | Tệp chung có thể phục vụ giai đoạn ban đầu |
| Dịch vụ xử lý thanh toán hoặc dữ liệu quan trọng | Thường chọn <code>false</code> cùng validation | Tránh tiếp tục với cấu hình không đầy đủ |
| Môi trường phát triển cá nhân | Có thể <code>true</code> nếu có fallback an toàn | Tăng tính linh hoạt khi thử nghiệm |

Nếu một Config Server phục vụ cả ứng dụng bắt buộc và ứng dụng tùy chọn, đây là quyết định chính sách ở cấp server. Vì <code>accept-empty</code> là cấu hình chung, hãy cân nhắc tách nhóm server hoặc repository theo ranh giới vận hành nếu hai nhóm cần hành vi khác nhau rõ rệt. Dù chọn chính sách nào, ứng dụng vẫn cần tự kiểm tra các khóa bắt buộc.

## 7. Kết hợp accept-empty với cách Config Client khởi động

Cần xem xét hai lớp độc lập:

- Config Server quyết định phản hồi thế nào khi không tìm thấy property source.
- Config Client quyết định có tiếp tục khởi động khi không lấy được cấu hình từ xa hay không.

Với Config Data API, import bắt buộc có dạng:

~~~yaml
spring:
  config:
    import: "configserver:http://config.internal:8888"
~~~

Nếu Config Server trả HTTP 404 vì <code>accept-empty: false</code>, lỗi lấy cấu hình thường khiến quá trình nạp Config Data thất bại và ứng dụng không khởi động được.

Nếu import có tiền tố <code>optional:</code>:

~~~yaml
spring:
  config:
    import: "optional:configserver:http://config.internal:8888"
~~~

client được phép tiếp tục khi nguồn từ xa không lấy được theo semantics của optional location. Điều đó có thể khiến ứng dụng vẫn khởi động dù server trả lỗi, tùy cơ chế xử lý và phiên bản tích hợp.

Vì vậy, chỉ đặt <code>accept-empty: false</code> không bảo đảm mọi client đều fail-fast. Nếu client khai báo nguồn là optional, nhóm cần xác nhận hành vi thực tế của phiên bản đang dùng và bảo đảm fallback an toàn.

Với các dự án sử dụng bootstrap context cũ, có thể gặp thuộc tính <code>spring.cloud.config.fail-fast</code> và cách khai báo khác. Hãy phân biệt mô hình bootstrap với Config Data API, không sao chép cấu hình giữa hai mô hình mà chưa kiểm tra phiên bản Spring Boot và Spring Cloud.

### Bảng kết hợp hành vi

| Config Server | Config Client | Kết quả cần dự kiến |
|---|---|---|
| <code>accept-empty: true</code>, trả Environment rỗng | Import bắt buộc | Response thành công; client có thể tiếp tục nhưng không có property source từ xa |
| <code>accept-empty: false</code>, trả 404 | Import bắt buộc | Nạp cấu hình từ xa thất bại; ứng dụng thường không khởi động |
| <code>accept-empty: false</code>, trả 404 | Import optional | Client có thể bỏ qua nguồn từ xa và tiếp tục; cần xác minh theo phiên bản |
| Server lỗi mạng hoặc Git | Import optional | Client có thể tiếp tục mà không có cấu hình từ xa; fallback phải an toàn |
| Server trả cấu hình chung nhưng thiếu khóa bắt buộc | Bất kỳ | Client vẫn có thể khởi động; cần validation thuộc tính ở ứng dụng |

Bảng này cho thấy chính sách server và client cần được thiết kế cùng nhau. Đừng sử dụng optional chỉ để che lỗi kết nối trong production nếu ứng dụng không thể vận hành an toàn khi thiếu cấu hình tập trung.

## 8. Kiểm tra khóa bắt buộc ở phía ứng dụng

<code>accept-empty</code> chỉ biết có property source hay không. Một Environment có thể chứa một thuộc tính log chung nhưng vẫn thiếu URL dịch vụ, tên queue hoặc thông tin xác thực mà ứng dụng cần.

Do đó, ứng dụng nên xác thực các thuộc tính thiết yếu khi khởi động. Với <code>@ConfigurationProperties</code>, có thể kết hợp validation để làm rõ yêu cầu:

~~~java
@ConfigurationProperties(prefix = "orders.inventory")
@Validated
public class InventoryClientProperties {

    @NotBlank
    private String baseUrl;

    @NotNull
    private Duration timeout;

    // getters và setters
}
~~~

Các annotation validation cần dependency phù hợp, ví dụ Jakarta Bean Validation và implementation tương ứng. Cách đăng ký properties có thể dùng <code>@ConfigurationPropertiesScan</code> hoặc <code>@EnableConfigurationProperties</code> tùy cấu trúc ứng dụng.

Nếu thiếu <code>orders.inventory.base-url</code> hoặc <code>timeout</code>, ứng dụng nên báo lỗi khởi động với tên thuộc tính rõ ràng. Không đưa giá trị secret vào thông báo lỗi. Cách này phát hiện được cả trường hợp Config Server trả HTTP 200 với cấu hình chung nhưng chưa đủ dữ liệu riêng cho dịch vụ.

Có thể phân nhóm thuộc tính theo mức độ bắt buộc:

- **Bắt buộc để khởi động:** URL datasource, endpoint phụ thuộc chính, khóa định danh hoặc cấu hình bảo mật.
- **Có mặc định an toàn:** mức log, một số giới hạn chẩn đoán hoặc giá trị quan sát.
- **Tùy chọn theo tính năng:** thuộc tính chỉ cần khi một feature được bật.

Nếu một feature tùy chọn được bật nhưng thiếu cấu hình phụ thuộc, validation nên báo lỗi thay vì để lỗi xuất hiện muộn trong lúc xử lý request.

## 9. Kiểm thử accept-empty bằng endpoint

Nên kiểm thử bằng các request có kết quả đã biết. Ví dụ repository có:

~~~text
config-repo/
├── application.yml
├── orders-service.yml
└── inventory-service.yml
~~~

Thực hiện một ma trận request:

| Request | Kỳ vọng |
|---|---|
| <code>/orders-service/prod/main</code> | Có thể nhận cấu hình chung và cấu hình riêng của orders |
| <code>/inventory-service/prod/main</code> | Có thể nhận cấu hình chung và cấu hình riêng của inventory |
| <code>/unknown-service/prod/main</code> | Có thể nhận cấu hình chung nếu <code>application.yml</code> phù hợp |
| <code>/unknown-service/prod/missing-label</code> | Phụ thuộc khả năng resolve label; không coi đây là phép thử accept-empty thuần túy |
| Request không có bất kỳ property source phù hợp | Environment rỗng hoặc HTTP 404 theo <code>accept-empty</code> |

Dùng <code>curl -i</code> để xem cả status code và body:

~~~bash
curl -i http://localhost:8888/unknown-service/prod/main
~~~

Với <code>accept-empty: true</code>, nếu repository thực sự không có property source phù hợp, kết quả thường là HTTP 200 cùng Environment rỗng. Với <code>false</code>, cùng tình huống đó trả HTTP 404.

Để kiểm tra chính sách một cách rõ ràng, cần có một test repository hoặc label riêng không chứa cả cấu hình chung lẫn cấu hình riêng. Nếu luôn có <code>application.yml</code>, request cho một application giả vẫn có thể nhận property source chung và không kiểm tra được trường hợp Environment rỗng.

Không dùng label không tồn tại để thay thế bài test này. Label sai có thể tạo lỗi resolve Git ref trước khi server có thể đưa ra kết quả Environment rỗng.

## 10. Quan sát và cảnh báo

Một số tín hiệu hữu ích:

- Số lượng request nhận Environment có <code>propertySources</code> rỗng.
- Tỷ lệ HTTP 404 từ Config Server.
- Tỷ lệ Config Client khởi động thất bại do lấy cấu hình.
- Application/profile/label được yêu cầu trong từng môi trường.
- Các khóa bắt buộc không được bind hoặc validation thất bại.
- Chênh lệch giữa version Git được các Config Server replica phục vụ.

Không ghi nội dung bí mật của property source vào log hoặc metric label. Có thể ghi nhận tên application, profile, label, số lượng property source, status code, thời gian xử lý và version Git nếu có mà không lộ giá trị nhạy cảm.

Health check chung của Config Server không thay thế phép thử lấy cấu hình. Server có thể đang sống và trả health OK nhưng một application cụ thể không có tệp, label hoặc quyền truy cập phù hợp. Nên có kiểm tra tổng hợp với một bộ application/profile/label đã biết, đồng thời có validation ở từng client cho các khóa bắt buộc.

Nếu có nhiều Config Server replica, hãy kiểm tra chính sách và kết quả trên từng instance hoặc qua load balancer. Sự khác nhau giữa các replica có thể khiến cùng một request lúc trả 200, lúc trả 404.

## 11. Các tình huống thực tế

### Tình huống A: ứng dụng mới chỉ cần mặc định chung

Nhóm vừa tạo <code>catalog-service</code>. Repository có <code>application.yml</code> với cấu hình log, tracing và một số timeout chung, nhưng chưa có <code>catalog-service.yml</code>.

Client yêu cầu <code>catalog-service/dev/main</code>. Config Server tìm thấy nguồn <code>application.yml</code> nên trả property source chung. Đây không phải Environment rỗng. Ứng dụng có thể khởi động nếu các thuộc tính bắt buộc khác đã được cung cấp từ nguồn hợp lệ và validation thành công.

Khi nhóm thêm cấu hình riêng, ứng dụng bắt đầu nhận thêm các thuộc tính theo dịch vụ.

### Tình huống B: sai tên ứng dụng nhưng vẫn nhận cấu hình chung

Pipeline của <code>orders-service</code> truyền nhầm <code>spring.application.name=order-service</code>. Repository có <code>application.yml</code> nhưng tệp riêng dùng tên <code>orders-service.yml</code>.

Request vẫn có thể trả HTTP 200 với cấu hình chung. Nhờ validation yêu cầu <code>orders.inventory.base-url</code> và <code>orders.events.topic</code>, ứng dụng phát hiện thiếu cấu hình riêng ngay khi khởi động. Log request giúp nhóm xác định tên application đã bị truyền sai.

### Tình huống C: không có bất kỳ cấu hình nào

Một ứng dụng thử nghiệm yêu cầu application chưa được tạo, repository test cũng không có <code>application.yml</code>. Với <code>accept-empty: true</code>, server trả Environment rỗng. Với <code>false</code>, server trả 404.

Nếu client dùng import bắt buộc, response 404 thường làm quá trình nạp cấu hình thất bại. Nếu client dùng optional import, ứng dụng có thể tiếp tục với các nguồn cục bộ; nhóm cần kiểm tra xem hành vi đó có được cho phép trong môi trường này không.

### Tình huống D: Git backend không truy cập được

Config Server không thể fetch repository do token hết hạn. Đây là lỗi backend, không phải đơn thuần là không có ứng dụng. <code>accept-empty</code> không nên được dùng để che lỗi Git; server cần báo lỗi truy cập repository và hệ thống cần cảnh báo, khôi phục credential hoặc kết nối.

## 12. Checklist triển khai

- [ ] Đã quyết định có chấp nhận Environment rỗng hay không và đặt rõ <code>spring.cloud.config.server.accept-empty</code>.
- [ ] Đã hiểu rằng <code>application.yml</code> có thể làm request của ứng dụng chưa có tệp riêng vẫn nhận cấu hình.
- [ ] Đã phân biệt request không có property source với label không tồn tại hoặc Git backend lỗi.
- [ ] Đã đồng bộ giá trị <code>accept-empty</code> trên mọi Config Server replica.
- [ ] Đã thống nhất client dùng import bắt buộc hay optional theo mức độ thiết yếu của cấu hình.
- [ ] Đã xác thực các khóa bắt buộc ở phía ứng dụng bằng validation.
- [ ] Đã kiểm thử cả response Environment rỗng và HTTP 404 bằng repository/label thử nghiệm phù hợp.
- [ ] Đã giám sát status code, property source rỗng và lỗi khởi động.
- [ ] Đã bảo vệ log và endpoint chẩn đoán khỏi rò rỉ bí mật.
- [ ] Đã kiểm tra lại hành vi sau khi thay đổi cấu hình hoặc nâng cấp Spring Boot/Spring Cloud.

<code>accept-empty</code> là một chính sách phản hồi của Config Server khi không có property source phù hợp. Nó giúp chọn cách biểu hiện của tình huống thiếu cấu hình, nhưng không thể xác nhận application name đúng, không thể kiểm tra các khóa nghiệp vụ bắt buộc và không xử lý thay lỗi Git hoặc mạng. Kết hợp chính sách server rõ ràng, cách khởi động client có chủ đích và validation ở ứng dụng giúp nhóm phát hiện thiếu cấu hình đúng lúc, thay vì để dịch vụ chạy với một bộ giá trị không đầy đủ.

