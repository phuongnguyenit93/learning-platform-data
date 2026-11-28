# Các khái niệm: nguồn cấu hình, môi trường, profile, label và bí mật

Một ứng dụng Spring Boot cần nhiều giá trị để chạy đúng trong từng bối cảnh: địa chỉ dịch vụ phụ thuộc, thời gian chờ, mức log, giới hạn kết nối, cờ tính năng và thông tin kết nối cơ sở dữ liệu. Khi có nhiều ứng dụng và nhiều môi trường, đặt các giá trị này rải rác trong từng mã nguồn khiến cấu hình dễ lệch nhau, khó kiểm tra và khó truy vết khi có thay đổi.

Spring Cloud Config cung cấp một cách tổ chức tập trung. Config Server đọc cấu hình từ một nguồn như Git và cung cấp qua HTTP; Config Client lấy cấu hình đó khi khởi động. Các khái niệm **nguồn cấu hình**, **môi trường**, **profile**, **label** và **bí mật** giúp xác định chính xác ứng dụng sẽ nhận bộ cấu hình nào, từ phiên bản nào và với mức bảo vệ ra sao.

Sau bài học, bạn có thể:

- Phân biệt cấu hình cục bộ, cấu hình tập trung và kho Git dùng làm nguồn cấu hình.
- Giải thích quan hệ giữa tên ứng dụng, môi trường, Spring profile và Git label.
- Đọc cấu trúc kho cấu hình và endpoint của Spring Cloud Config Server.
- Xác định cách các giá trị trùng khóa được phân giải theo thứ tự ưu tiên.
- Chọn cách lưu trữ và phân phối bí mật an toàn.
- Mô tả cách cập nhật cấu hình bằng refresh hoặc Spring Cloud Bus và cách kiểm soát thay đổi.

## 1. Spring Cloud Config tổ chức cấu hình như thế nào?

Có thể hình dung luồng cấu hình gồm ba thành phần:

1. **Kho cấu hình** lưu các tệp cấu hình. Trong mô hình phổ biến, kho này là một Git repository có lịch sử commit, nhánh và tag.
2. **Config Server** kết nối tới kho cấu hình, tìm các tệp phù hợp với yêu cầu rồi công bố chúng qua HTTP.
3. **Config Client** là ứng dụng Spring Boot khai báo cách kết nối tới Config Server. Client nhận các property source từ máy chủ và đưa chúng vào Spring Environment để ứng dụng sử dụng.

Ví dụ, một hệ thống có ba ứng dụng <code>order-service</code>, <code>inventory-service</code> và <code>payment-service</code>. Thay vì mỗi ứng dụng tự lưu một bản cấu hình riêng cho mọi môi trường, nhóm phát triển có thể dùng một Config Server và một kho Git chung. Các giá trị dùng chung được khai báo một lần; các giá trị riêng cho từng ứng dụng hoặc profile được đặt trong tệp tương ứng.

Config Server không tự quyết định toàn bộ hành vi nghiệp vụ của ứng dụng. Nó phân phối các thuộc tính đã được tổ chức trong nguồn cấu hình. Ứng dụng vẫn chịu trách nhiệm đọc và sử dụng thuộc tính đúng cách, còn nhóm vận hành chịu trách nhiệm kiểm soát nguồn, quyền truy cập và phiên bản cấu hình.

Một yêu cầu lấy cấu hình thường được xác định bằng ba phần:

| Thành phần | Ý nghĩa | Ví dụ |
|---|---|---|
| Application | Tên ứng dụng cần cấu hình, thường lấy từ <code>spring.application.name</code> | <code>inventory-service</code> |
| Profile | Profile đang được kích hoạt ở client | <code>dev</code>, <code>prod</code> |
| Label | Nhãn Git chỉ phiên bản hoặc nhánh cấu hình cần đọc | <code>main</code>, <code>release-2026.11</code>, mã commit |

Ba phần này trả lời ba câu hỏi khác nhau: **ứng dụng nào**, **biến thể cấu hình nào**, và **đọc cấu hình ở phiên bản nào**.

## 2. Nguồn cấu hình: giá trị đến từ đâu?

Nguồn cấu hình là nơi lưu trữ các thuộc tính mà ứng dụng cần đọc. Trong ứng dụng Spring Boot, nguồn có thể là tệp YAML hoặc properties nằm cùng ứng dụng, biến môi trường, tham số khởi chạy, hệ thống quản lý bí mật hoặc một dịch vụ cấu hình tập trung.

### Cấu hình cục bộ

Cấu hình cục bộ nằm trong phạm vi triển khai của ứng dụng, thường gồm <code>application.yml</code>, <code>application.properties</code> và các tệp theo profile. Cách này thuận tiện cho mặc định đơn giản, thử nghiệm hoặc ứng dụng nhỏ. Tuy nhiên, khi nhiều dịch vụ dùng chung một giá trị, nhóm có thể phải sửa nhiều nơi và khó bảo đảm các bản sao luôn đồng nhất.

### Cấu hình tập trung với Config Server

Với Spring Cloud Config, cấu hình được đưa vào một kho riêng. Config Server đọc kho đó và trả về các property source phù hợp với tên ứng dụng, profile và label của client. Nhờ vậy, nhóm có thể xem lịch sử thay đổi qua Git, yêu cầu review trước khi hợp nhất và khôi phục về một phiên bản đã biết.

Một cấu trúc kho Git thường gặp:

~~~text
config-repo/
├── application.yml
├── application-dev.yml
├── application-prod.yml
├── inventory-service.yml
├── inventory-service-dev.yml
├── inventory-service-prod.yml
├── order-service.yml
└── order-service-prod.yml
~~~

Tên tệp thể hiện phạm vi áp dụng:

- <code>application.yml</code>: cấu hình mặc định có thể dùng chung cho nhiều ứng dụng.
- <code>application-prod.yml</code>: cấu hình chung cho các ứng dụng chạy với profile <code>prod</code>.
- <code>inventory-service.yml</code>: cấu hình riêng của <code>inventory-service</code>, áp dụng cho các profile.
- <code>inventory-service-prod.yml</code>: cấu hình riêng của <code>inventory-service</code> khi profile <code>prod</code> được kích hoạt.

Ví dụ, <code>application.yml</code> có thể chứa mức log mặc định và các giới hạn dùng chung. <code>inventory-service-dev.yml</code> chứa địa chỉ dịch vụ phục vụ phát triển; <code>inventory-service-prod.yml</code> chứa địa chỉ nội bộ của môi trường sản xuất. Những tệp này là dữ liệu cấu hình, không cần chứa mã Java của ứng dụng.

~~~yaml
# application.yml
logging:
  level:
    root: INFO

service-client:
  connect-timeout: 2s
~~~

~~~yaml
# inventory-service-dev.yml
inventory:
  api-base-url: http://localhost:8091
~~~

~~~yaml
# inventory-service-prod.yml
inventory:
  api-base-url: https://inventory.internal
~~~

Ứng dụng đọc thuộc tính bằng các cơ chế quen thuộc của Spring, chẳng hạn <code>@Value</code> hoặc <code>@ConfigurationProperties</code>. Với nhóm thuộc tính có quan hệ với nhau, <code>@ConfigurationProperties</code> thường giúp gom cấu hình vào một kiểu dữ liệu rõ ràng, dễ kiểm tra và dễ bảo trì.

Nên đặt giá trị mặc định dùng chung ở phạm vi rộng, sau đó chỉ ghi đè những khác biệt thực sự cần thiết ở phạm vi ứng dụng hoặc profile. Cách tổ chức này giảm lặp, giúp người đọc nhận ra đâu là quy tắc chung và đâu là ngoại lệ.

## 3. Môi trường và Spring profile

Hai khái niệm này thường xuất hiện cùng nhau nhưng có ý nghĩa khác nhau.

**Môi trường (environment)** mô tả bối cảnh triển khai và vận hành của ứng dụng. Các môi trường thường gặp là <code>dev</code> (phát triển), <code>test</code> (kiểm thử), <code>staging</code> (tiền sản xuất) và <code>prod</code> (sản xuất). Mỗi môi trường có hạ tầng, dữ liệu, quyền truy cập, địa chỉ dịch vụ và yêu cầu vận hành riêng.

**Spring profile** là cơ chế của Spring để chọn một nhóm cấu hình hoặc bean phù hợp với một tình huống chạy. Profile được kích hoạt bằng <code>spring.profiles.active</code>, biến môi trường <code>SPRING_PROFILES_ACTIVE</code> hoặc tham số khởi chạy. Config Client gửi profile đang hoạt động tới Config Server để nhận các tệp cấu hình tương ứng.

Trong một hệ thống đơn giản, nhóm có thể dùng profile <code>dev</code> cho môi trường phát triển và <code>prod</code> cho môi trường sản xuất. Nhưng quan hệ này không bắt buộc là một-một. Một môi trường có thể kích hoạt nhiều profile, ví dụ <code>prod,metrics</code>; profile <code>metrics</code> có thể bật cấu hình giám sát trong khi <code>prod</code> chọn địa chỉ dịch vụ và giới hạn tài nguyên của môi trường sản xuất.

| Góc nhìn | Môi trường | Spring profile |
|---|---|---|
| Trả lời câu hỏi | Ứng dụng đang được triển khai ở đâu, với hạ tầng nào? | Spring cần áp dụng nhóm cấu hình và bean nào? |
| Ví dụ | <code>dev</code>, <code>staging</code>, <code>prod</code> | <code>dev</code>, <code>prod</code>, <code>metrics</code>, <code>cloud</code> |
| Phạm vi | Quy trình triển khai và vận hành | Cơ chế cấu hình của Spring |
| Quan hệ | Có thể tương ứng với một profile theo quy ước của nhóm | Có thể dùng độc lập hoặc kết hợp nhiều profile |

Profile không tự tạo ra một môi trường triển khai. Kích hoạt <code>prod</code> chỉ chọn cấu hình mang tên <code>prod</code>; nhóm vẫn phải bảo đảm ứng dụng thực sự được triển khai tới hạ tầng sản xuất, có quyền phù hợp và kết nối tới đúng dịch vụ.

Khi cần phân biệt cấu hình theo môi trường, hãy thống nhất cách đặt tên giữa pipeline triển khai và <code>spring.profiles.active</code>. Tránh để pipeline triển khai vào sản xuất nhưng ứng dụng vẫn chạy với profile <code>dev</code>, vì ứng dụng có thể nhận nhầm địa chỉ, giới hạn hoặc hành vi dành cho phát triển.

## 4. Label: chọn phiên bản cấu hình trong Git

Profile chọn **biến thể** cấu hình; label chọn **phiên bản nguồn** chứa biến thể đó.

Khi Config Server dùng Git backend, label thường trỏ tới một nhánh, tag hoặc commit. Ví dụ:

- <code>main</code> trỏ tới nhánh đang phát triển cấu hình chính.
- <code>release-2026.11</code> trỏ tới một tag đã phát hành.
- <code>a1b2c3d</code> đại diện cho một commit cụ thể.

Nếu client không chỉ định label, Config Server sử dụng label mặc định được cấu hình trên máy chủ. Với Git backend, thuộc tính thường dùng để đặt giá trị này là <code>spring.cloud.config.server.git.default-label</code>.

Label ảnh hưởng trực tiếp tới khả năng tái lập. Nếu production luôn lấy cấu hình từ nhánh <code>main</code>, nội dung nhánh có thể thay đổi theo thời gian; hai lần khởi động cùng một phiên bản ứng dụng vì thế có thể nhận cấu hình khác nhau. Ghim production vào tag phát hành hoặc commit đã được duyệt giúp xác định chính xác bộ cấu hình đang chạy. Nhánh phát triển vẫn hữu ích cho môi trường cần nhận các thay đổi mới thường xuyên.

Ví dụ về ba yêu cầu:

| Yêu cầu | Application | Profile | Label | Mục đích |
|---|---|---|---|---|
| Lập trình cục bộ | <code>inventory-service</code> | <code>dev</code> | <code>main</code> | Thử cấu hình đang phát triển |
| Kiểm thử bản phát hành | <code>inventory-service</code> | <code>staging</code> | <code>release-2026.11</code> | Kiểm tra cấu hình đã chốt |
| Chạy sản xuất | <code>inventory-service</code> | <code>prod</code> | <code>release-2026.11</code> | Dùng đúng bộ cấu hình đã phê duyệt |

Label không phải tên môi trường và cũng không phải tên profile. Một label có thể chứa nhiều tệp cho nhiều ứng dụng và profile; profile được dùng để chọn tệp phù hợp bên trong phiên bản Git mà label chỉ tới.

## 5. Kết nối Config Server và Config Client

Ví dụ sau minh họa Config Server đọc một kho Git và lắng nghe trên cổng <code>8888</code>. Địa chỉ kho và thông tin xác thực thực tế cần được cấp qua cấu hình triển khai an toàn.

~~~yaml
# Cấu hình của Config Server
server:
  port: 8888

spring:
  cloud:
    config:
      server:
        git:
          uri: https://git.example.com/platform/config-repo.git
          default-label: main
~~~

Ở phía client, khai báo tên ứng dụng, profile và Config Server. Với Spring Boot hiện đại, Config Data API cho phép dùng <code>spring.config.import</code> để nạp cấu hình từ Config Server:

~~~yaml
# Cấu hình ban đầu của inventory-service
spring:
  application:
    name: inventory-service
  profiles:
    active: dev
  config:
    import: "optional:configserver:http://localhost:8888"
  cloud:
    config:
      label: main
~~~

Giá trị <code>spring.application.name</code> xác định application mà Config Server cần tìm. Profile <code>dev</code> chọn biến thể cấu hình. <code>spring.cloud.config.label</code> chỉ phiên bản Git cần đọc.

Tiền tố <code>optional:</code> cho phép ứng dụng tiếp tục khởi động khi Config Server không truy cập được; khi đó ứng dụng có thể chỉ còn các nguồn cấu hình sẵn có khác. Cách này hữu ích trong một số môi trường phát triển, nhưng có thể che giấu sự cố phân phối cấu hình nếu ứng dụng bắt buộc phải có cấu hình tập trung. Với dịch vụ cần cấu hình từ xa để khởi động an toàn, hãy cân nhắc khai báo import bắt buộc và thiết kế cơ chế sẵn sàng của Config Server phù hợp.

Có thể kiểm tra cách Config Server phân giải yêu cầu bằng endpoint:

~~~http
GET http://localhost:8888/inventory-service/dev/main
~~~

Endpoint có dạng <code>/{application}/{profile}/{label}</code>. Phản hồi chứa các property source mà client có thể nạp. Khi kiểm tra, hãy xác nhận tên ứng dụng, profile và label đúng như mong đợi; một phản hồi HTTP thành công vẫn có thể chứa bộ cấu hình sai nếu một trong ba giá trị được chọn nhầm.

## 6. Thứ tự ưu tiên khi nhiều nguồn cùng khai báo một thuộc tính

Một thuộc tính có thể xuất hiện ở nhiều nơi: tệp dùng chung, tệp riêng ứng dụng, tệp theo profile, cấu hình cục bộ, biến môi trường hoặc tham số khởi chạy. Spring cần một quy tắc ưu tiên để quyết định giá trị hiệu lực.

Có hai lớp cần xem xét.

### Ưu tiên giữa các tệp trong kho cấu hình

Trong cách tổ chức thông thường của Config Server, cấu hình được ghép từ phạm vi chung tới phạm vi cụ thể. Ví dụ, với <code>inventory-service</code> và profile <code>prod</code>, các tệp liên quan có thể gồm:

1. <code>application.yml</code>
2. <code>application-prod.yml</code>
3. <code>inventory-service.yml</code>
4. <code>inventory-service-prod.yml</code>

Các giá trị ở tệp chuyên biệt cho ứng dụng và profile có thể ghi đè giá trị chung. Vì vậy, nếu <code>application.yml</code> đặt <code>service-client.connect-timeout</code> là <code>2s</code> còn <code>inventory-service-prod.yml</code> đặt là <code>1s</code>, ứng dụng có thể nhận <code>1s</code> từ nguồn cụ thể hơn. Hãy kiểm tra danh sách <code>propertySources</code> mà Config Server trả về khi cần xác nhận thứ tự thực tế.

### Ưu tiên giữa các property source ở phía ứng dụng

Sau khi client nạp cấu hình, Spring Boot phân giải thuộc tính từ các property source trong Spring Environment. Thứ tự cụ thể phụ thuộc phiên bản Spring Boot, cách khai báo Config Data import và chính sách ghi đè của Spring Cloud Config. Các tham số như <code>spring.cloud.config.allowOverride</code>, <code>spring.cloud.config.overrideNone</code> và <code>spring.cloud.config.overrideSystemProperties</code> ảnh hưởng tới việc nguồn cục bộ nào được phép ghi đè nguồn từ xa; cần cấu hình chúng theo chủ đích và theo phiên bản đang sử dụng.

Tham số khởi chạy, thuộc tính hệ thống Java và biến môi trường thường được dùng để cung cấp giá trị theo từng lần triển khai. Chúng cũng có thể có độ ưu tiên cao hơn cấu hình trong tệp. Vì vậy, không nên chỉ nhìn một tệp YAML rồi kết luận đó là giá trị ứng dụng đang dùng.

Khi một giá trị không như mong đợi:

- Xác định chính xác tên thuộc tính và mọi nơi đang khai báo thuộc tính đó.
- Kiểm tra application, profile và label mà client thực sự gửi.
- Kiểm tra danh sách property source và nguồn gốc giá trị trong Spring Environment.
- Xem lại chính sách ghi đè của Config Server và các biến môi trường hoặc tham số khởi chạy.

Actuator có endpoint <code>env</code> hỗ trợ kiểm tra môi trường thuộc tính và nguồn gốc của một số giá trị. Endpoint này có thể làm lộ thông tin nhạy cảm nếu cấu hình hiển thị không phù hợp; chỉ mở cho người có quyền và che dữ liệu nhạy cảm theo chính sách vận hành.

## 7. Bí mật và dữ liệu nhạy cảm

Bí mật là những giá trị mà người không có quyền không được đọc hoặc sử dụng, chẳng hạn mật khẩu cơ sở dữ liệu, token truy cập, khóa ký, chứng thư và thông tin xác thực dịch vụ. Những giá trị này cần được quản lý khác với cấu hình thông thường như mức log hay thời gian chờ.

Một Git repository có thể được nhiều người và pipeline truy cập. Lịch sử commit cũng có thể lưu lại giá trị đã bị xóa ở commit mới hơn. Vì vậy, không đưa bí mật dạng rõ vào kho cấu hình, kể cả khi repository là private. Xóa giá trị khỏi tệp hiện tại không tự loại bỏ nó khỏi lịch sử Git; nếu bí mật đã bị commit, cần thu hồi hoặc xoay vòng bí mật và xử lý lịch sử theo quy trình bảo mật của tổ chức.

Các lựa chọn thường dùng gồm:

- **Secret manager hoặc Vault:** lưu bí mật trong hệ thống chuyên dụng, cấp quyền đọc theo danh tính dịch vụ và ghi nhận hoạt động truy cập.
- **Biến môi trường hoặc secret mount của nền tảng triển khai:** pipeline hoặc nền tảng cấp bí mật cho tiến trình khi chạy. Cần hạn chế quyền đọc và tránh in giá trị ra log.
- **Mã hóa giá trị trong nguồn cấu hình:** Spring Cloud Config hỗ trợ cơ chế mã hóa/giải mã thuộc tính. Giá trị mã hóa có thể được lưu trong Git; Config Server dùng khóa được quản lý riêng để giải mã khi cần.

Với cơ chế mã hóa của Spring Cloud Config, giá trị mã hóa thường được đánh dấu bằng tiền tố <code>{cipher}</code>. Config Server cần có khóa mã hóa phù hợp, chẳng hạn khóa đối xứng hoặc cấu hình keystore. Khóa phải được lưu ngoài repository cấu hình và được bảo vệ bằng cơ chế quản lý khóa thích hợp. Nếu ciphertext nằm trong Git nhưng khóa giải mã cũng nằm trong cùng repository, mục tiêu bảo vệ gần như mất ý nghĩa.

Mã hóa không thay thế kiểm soát truy cập. Hãy kết hợp các lớp bảo vệ sau:

1. Dùng HTTPS giữa client và Config Server; xác thực client và giới hạn quyền đọc theo ứng dụng hoặc nhóm vận hành.
2. Giới hạn quyền đọc repository và khóa mã hóa; tách quyền quản trị kho cấu hình khỏi quyền xem bí mật.
3. Không ghi token, mật khẩu hoặc nội dung cấu hình nhạy cảm vào log, thông báo lỗi hay dữ liệu chẩn đoán.
4. Không công khai endpoint trả về cấu hình hoặc endpoint Actuator nhạy cảm ra mạng không tin cậy.
5. Xoay vòng bí mật định kỳ và ngay khi có dấu hiệu lộ lọt; xác minh các dịch vụ đã nhận giá trị mới.

Dù bí mật được lấy từ Vault, biến môi trường hay Config Server, ứng dụng vẫn có thể giữ giá trị rõ trong bộ nhớ khi sử dụng. Do đó, quyền truy cập tiến trình, log, heap dump và kênh chẩn đoán cũng thuộc phạm vi bảo vệ bí mật.

## 8. Refresh cấu hình và Spring Cloud Bus

Config Client thường nạp cấu hình trong quá trình khởi động. Khi một commit mới được đưa vào kho Git, các ứng dụng đang chạy không tự động đọc lại mọi giá trị chỉ vì repository đã thay đổi. Nhóm cần có cơ chế refresh hoặc khởi động lại theo kế hoạch.

Với Spring Boot Actuator và Spring Cloud phù hợp, ứng dụng có thể bật endpoint refresh. Một số bean được đánh dấu <code>@RefreshScope</code> sẽ được tạo lại khi refresh; các bean cấu hình theo <code>@ConfigurationProperties</code> có thể được bind lại theo cơ chế refresh của phiên bản đang dùng.

Ví dụ cấu hình endpoint:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,refresh
~~~

Sau khi endpoint được bật và bảo vệ bằng xác thực, người vận hành có thể gửi yêu cầu <code>POST /actuator/refresh</code> tới một instance để yêu cầu nạp lại cấu hình. Cần thử nghiệm trước với các bean thực tế: không phải mọi thư viện, kết nối hoặc đối tượng đã khởi tạo đều có thể thay đổi an toàn khi refresh. Một số thay đổi vẫn cần khởi động lại dịch vụ.

Trong hệ thống có nhiều instance, gọi refresh lần lượt từng instance sẽ tạo thêm thao tác vận hành. **Spring Cloud Bus** giải quyết bài toán phát thông báo thay đổi tới các ứng dụng đã tham gia cùng một bus. Bus thường dùng broker như RabbitMQ hoặc Kafka. Khi một instance nhận sự kiện refresh, các instance liên quan cũng có thể nhận thông báo và cập nhật cấu hình.

Endpoint thường dùng cho thao tác phát sự kiện là <code>POST /actuator/busrefresh</code>, tùy cấu hình và phiên bản Spring Cloud Bus. Endpoint này phải được giới hạn quyền truy cập như một thao tác vận hành có ảnh hưởng rộng. Một sự kiện refresh được gửi nhầm có thể khiến nhiều instance cùng tải lại cấu hình trong một thời điểm.

Quy trình cập nhật nên có các bước: đưa thay đổi vào Git, kiểm tra phiên bản và nội dung, phát tín hiệu refresh, xác nhận các instance đã nhận cấu hình, rồi quan sát log và chỉ số sau thay đổi. Với thay đổi ảnh hưởng kết nối hoặc tài nguyên, hãy cân nhắc refresh theo từng nhóm hoặc triển khai lại có kiểm soát.

## 9. Quản trị thay đổi cấu hình

Cấu hình tập trung có thể tác động đồng thời tới nhiều ứng dụng. Một lỗi nhỏ trong tệp dùng chung có thể ảnh hưởng tới toàn bộ dịch vụ đang sử dụng tệp đó. Vì vậy, thay đổi cấu hình cần được quản trị như thay đổi mã nguồn.

Một quy trình thực tế có thể gồm:

1. **Tạo thay đổi có phạm vi rõ:** ghi rõ ứng dụng, profile, thuộc tính, lý do và dịch vụ chịu ảnh hưởng.
2. **Review qua Git:** dùng pull request, người phê duyệt và bảo vệ nhánh. Thay đổi giá trị dùng chung cần người phụ trách nền tảng xem xét.
3. **Kiểm tra tự động:** xác thực cú pháp YAML, kiểu dữ liệu, tên thuộc tính quan trọng và các quy tắc nội bộ. Có thể chạy kiểm thử tích hợp với Config Server để xác nhận đúng bộ cấu hình được trả về.
4. **Triển khai theo môi trường:** kiểm tra ở <code>dev</code>, sau đó <code>test</code> hoặc <code>staging</code>, rồi mới đưa label đã duyệt vào <code>prod</code>.
5. **Ghim phiên bản và lưu dấu vết:** dùng tag hoặc commit cho bản cấu hình phát hành; ghi nhận ứng dụng, profile, label, thời điểm và người phê duyệt.
6. **Refresh và quan sát:** xác nhận instance đã nạp phiên bản mong muốn; theo dõi lỗi khởi động, kết nối, log và chỉ số vận hành.
7. **Rollback khi cần:** chuyển về label hoặc commit đã biết là tốt, sau đó refresh hoặc triển khai lại theo quy trình.

Đối với production, label trỏ tới tag hoặc commit bất biến giúp tái lập trạng thái. Nếu dùng nhánh có thể thay đổi, cần xác định rõ ai được phép cập nhật nhánh và cách ghi nhận phiên bản mà mỗi lần triển khai đã sử dụng.

Cũng nên phân chia quyền theo trách nhiệm. Người phát triển có thể đề xuất cấu hình cho dịch vụ của mình; người phụ trách nền tảng review giá trị dùng chung; người vận hành phê duyệt thay đổi ảnh hưởng production; tài khoản của ứng dụng chỉ có quyền đọc những nguồn cần thiết. Cách phân quyền này giảm nguy cơ một tài khoản bị lộ có thể sửa hoặc đọc toàn bộ cấu hình.

## 10. Ví dụ tổng hợp: cùng một ứng dụng qua các môi trường

Giả sử <code>inventory-service</code> chạy ở <code>dev</code>, <code>staging</code> và <code>prod</code>. Nhóm có kho Git chứa các tệp dùng chung và tệp riêng theo ứng dụng. Khi ứng dụng khởi động, các bước diễn ra như sau:

1. Pipeline triển khai đặt <code>spring.application.name=inventory-service</code>.
2. Pipeline đặt profile phù hợp với môi trường, chẳng hạn <code>staging</code>.
3. Client kết nối Config Server và yêu cầu application <code>inventory-service</code>, profile <code>staging</code>, label <code>release-2026.11</code>.
4. Config Server đọc đúng phiên bản Git và ghép các nguồn phù hợp, từ cấu hình dùng chung tới cấu hình riêng của dịch vụ.
5. Client nạp property source vào Spring Environment. Nếu cùng một khóa có nhiều giá trị, Spring áp dụng thứ tự ưu tiên đang được cấu hình.
6. Ứng dụng khởi động với địa chỉ dịch vụ và giới hạn phù hợp. Bí mật được lấy từ nguồn được bảo vệ hoặc giải mã bằng khóa do hệ thống quản lý riêng.
7. Khi cần thay đổi, nhóm tạo commit mới, review, kiểm tra, phát hành label mới và refresh hoặc triển khai lại dịch vụ.

Nếu <code>inventory-service-prod.yml</code> có một giá trị sai, nhóm có thể truy ngược từ phiên bản label đang chạy tới commit Git, pull request và người phê duyệt. Nếu cần phục hồi, nhóm có thể chuyển client về label đã được xác nhận hoạt động tốt. Lịch sử Git và thông tin triển khai giúp quá trình điều tra có căn cứ.

## 11. Những nhầm lẫn cần tránh

| Nhầm lẫn | Cách hiểu đúng |
|---|---|
| Môi trường và profile là một khái niệm | Môi trường là bối cảnh triển khai; profile là cơ chế chọn cấu hình của Spring. |
| Profile quyết định phiên bản cấu hình | Profile chọn biến thể; label chọn nhánh, tag hoặc commit trong nguồn Git. |
| Tên ứng dụng chỉ để hiển thị | <code>spring.application.name</code> được dùng để Config Server tìm cấu hình riêng của ứng dụng. |
| Git private có thể chứa mật khẩu dạng rõ | Repository private vẫn có lịch sử và nhiều loại tài khoản truy cập; bí mật cần nguồn lưu trữ và quyền bảo vệ riêng. |
| Commit mới làm mọi instance đổi cấu hình ngay | Instance thường cần refresh hoặc khởi động lại; Bus có thể phát thông báo tới nhiều instance. |
| Refresh bảo đảm mọi thay đổi đều có hiệu lực | Chỉ các thành phần hỗ trợ cơ chế refresh mới cập nhật an toàn; một số thay đổi cần khởi động lại. |
| Xóa bí mật khỏi tệp là đủ | Bí mật có thể còn trong lịch sử Git; cần thu hồi hoặc xoay vòng giá trị đã lộ. |

## 12. Checklist khi thiết kế cấu hình tập trung

- [ ] Mỗi ứng dụng có <code>spring.application.name</code> ổn định và nhất quán với tên tệp cấu hình.
- [ ] Quy ước profile giữa pipeline và môi trường triển khai được thống nhất.
- [ ] Label của từng môi trường được xác định rõ; production dùng phiên bản có thể truy vết.
- [ ] Cấu hình dùng chung và cấu hình riêng được đặt đúng phạm vi, hạn chế khai báo trùng.
- [ ] Nhóm hiểu thứ tự ưu tiên giữa các property source và biết cách kiểm tra giá trị hiệu lực.
- [ ] Bí mật không được commit ở dạng rõ; khóa giải mã được quản lý ngoài kho Git.
- [ ] Config Server, endpoint Actuator và broker Bus được xác thực, giới hạn quyền truy cập.
- [ ] Thay đổi cấu hình có review, kiểm tra, dấu vết phát hành và phương án rollback.
- [ ] Quy trình refresh đã được thử nghiệm với các bean và kết nối thực tế.
- [ ] Sau mỗi lần cập nhật, nhóm xác nhận instance đã nhận đúng application, profile và label.

Khi tổ chức đúng các khái niệm này, Spring Cloud Config giúp nhiều ứng dụng Spring Boot dùng chung một nguồn cấu hình có lịch sử, nhận đúng biến thể theo profile và phiên bản theo label. Việc kiểm soát thứ tự ưu tiên, bảo vệ bí mật, refresh và quản trị thay đổi giúp cấu hình được phân phối nhất quán trong suốt quá trình phát triển và vận hành.

