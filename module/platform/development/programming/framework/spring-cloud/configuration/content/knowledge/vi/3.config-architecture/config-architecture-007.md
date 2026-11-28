# Các điểm có thể lỗi giữa client, Config Server và kho lưu trữ

Trong kiến trúc Spring Cloud Config, một ứng dụng chỉ nhận được cấu hình khi nhiều thành phần phối hợp đúng: Config Client phải tạo được yêu cầu với đúng tên ứng dụng, profile và label; yêu cầu phải tới được Config Server; máy chủ phải xác thực và phân giải yêu cầu; Git backend phải đọc được đúng phiên bản kho cấu hình; cuối cùng client phải nạp được các property source vào Spring Environment.

Chỉ cần một mắt xích sai, ứng dụng có thể không khởi động, khởi động với cấu hình mặc định, nhận cấu hình của môi trường khác hoặc tiếp tục chạy bằng giá trị cũ. Bài học này phân tích các điểm hỏng thường gặp giữa client, server và kho lưu trữ, cách nhận diện triệu chứng, thứ tự kiểm tra và cách phục hồi có kiểm soát.

Sau bài học, bạn có thể:

- Mô tả đường đi của một yêu cầu cấu hình từ Config Client tới Git repository và quay lại.
- Phân loại lỗi ở phía client, mạng, xác thực, Config Server và Git backend.
- Phân biệt lỗi kết nối với lỗi phân giải sai application, profile hoặc label.
- Đọc log, HTTP status và phản hồi Config Server để khoanh vùng nguyên nhân.
- Thiết kế timeout, retry, fail-fast, health check và phương án dự phòng phù hợp.
- Lập quy trình xử lý sự cố và xác nhận cấu hình sau khi phục hồi.

## 1. Đường đi của một yêu cầu cấu hình

Trước khi tìm lỗi, cần biết thành phần nào xử lý từng bước. Với Spring Boot sử dụng Config Data API, client thường khai báo Config Server trong <code>spring.config.import</code>. Khi khởi động, Spring Config Data resolver tạo yêu cầu tới server dựa trên các thông tin như tên ứng dụng, profile đang hoạt động và label.

Luồng tổng quát:

~~~mermaid
flowchart TD
    A["Spring Boot khởi động"] --> B["Config Client đọc spring.config.import"]
    B --> C["Tạo yêu cầu application / profile / label"]
    C --> D["DNS, TCP, TLS và HTTP"]
    D --> E["Config Server xác thực yêu cầu"]
    E --> F["EnvironmentRepository phân giải cấu hình"]
    F --> G["Git backend đọc nhánh, tag hoặc commit"]
    G --> H["Đọc tệp cấu hình phù hợp"]
    H --> I["Trả về Environment và propertySources"]
    I --> J["Client nạp vào Spring Environment"]
    J --> K["Ứng dụng tạo bean và khởi động"]
~~~

Ở phía server, endpoint phổ biến có dạng:

~~~http
GET /{application}/{profile}/{label}
~~~

Ví dụ:

~~~http
GET /inventory-service/staging/release-2026.11
~~~

Yêu cầu này có nghĩa là: lấy cấu hình cho ứng dụng <code>inventory-service</code>, profile <code>staging</code>, từ label <code>release-2026.11</code>. Label thường đại diện cho nhánh, tag hoặc commit trong Git backend.

Config Server tiếp nhận yêu cầu, gọi một <code>EnvironmentRepository</code> để tìm cấu hình, rồi trả về một đối tượng Environment gồm các property source. Client đưa các nguồn này vào Spring Environment cùng các nguồn cấu hình khác của ứng dụng. Việc phân giải giá trị cuối cùng còn phụ thuộc thứ tự ưu tiên property source ở phía client.

Có thể chia đường đi thành sáu vùng cần quan sát:

1. **Khởi tạo client:** dependency, import URI, application name, profile và label.
2. **Kết nối:** DNS, định tuyến, cổng, proxy, TLS và timeout.
3. **Tiếp nhận ở server:** tiến trình, endpoint, xác thực và phân quyền.
4. **Phân giải cấu hình:** repository, tên tệp, profile và thứ tự property source.
5. **Truy cập Git:** URI, thông tin xác thực, nhánh/tag/commit và trạng thái bản clone.
6. **Nạp cấu hình:** phản hồi, kiểu dữ liệu, ràng buộc và quá trình tạo bean ở ứng dụng.

Khi điều tra, hãy xác định bước cuối cùng đã thành công. Nếu client chưa mở được kết nối TCP, việc kiểm tra tên tệp YAML trong Git chưa giúp ích. Nếu server trả về đúng property source nhưng ứng dụng vẫn dùng giá trị khác, cần kiểm tra thứ tự ưu tiên ở client.

## 2. Lỗi khởi tạo ở Config Client

Config Client là điểm bắt đầu của luồng lấy cấu hình. Một lỗi khai báo nhỏ có thể khiến ứng dụng không gửi yêu cầu tới Config Server hoặc gửi yêu cầu với thông tin sai.

### Thiếu hoặc khai báo sai cấu hình import

Với Spring Boot hiện đại, Config Data API thường dùng cấu hình tương tự:

~~~yaml
spring:
  application:
    name: inventory-service
  profiles:
    active: staging
  config:
    import: "configserver:http://config.internal:8888"
  cloud:
    config:
      label: release-2026.11
~~~

Một số trường hợp lỗi:

- Thiếu dependency Config Client nên scheme <code>configserver:</code> không được nhận diện.
- Viết sai địa chỉ, cổng hoặc scheme trong import URI.
- Đưa cấu hình vào tệp được nạp quá muộn, trong khi client cần thông tin để truy cập server ngay ở giai đoạn Config Data.
- Sao chép cấu hình từ hướng dẫn dùng bootstrap context cũ nhưng dự án lại dùng Config Data API, hoặc ngược lại.
- Dùng phiên bản Spring Boot và Spring Cloud không tương thích.

Với dự án dùng cơ chế bootstrap cũ, cách khai báo và thời điểm nạp cấu hình có thể khác. Hãy kiểm tra đúng cách khởi tạo mà phiên bản Spring Cloud của dự án hỗ trợ; tránh trộn hai mô hình mà không có chủ đích.

### Sai application name

Nếu <code>spring.application.name</code> bị thiếu, Config Client có thể dùng tên mặc định <code>application</code>. Khi đó server có thể trả về cấu hình dùng chung mà không có cấu hình riêng của dịch vụ. Đây là lỗi nguy hiểm vì ứng dụng vẫn có thể khởi động bình thường.

Ví dụ, client dự kiến yêu cầu <code>inventory-service</code> nhưng log hoặc request thực tế cho thấy application là <code>application</code>. Kiểm tra:

- Giá trị <code>spring.application.name</code> trong cấu hình khởi động cục bộ.
- Biến môi trường hoặc tham số dòng lệnh có ghi đè tên ứng dụng không.
- Pipeline triển khai có truyền đúng tên dịch vụ cho mọi instance không.

Tên application phải khớp quy ước tên tệp trong repository. Nếu tệp là <code>inventory-service-prod.yml</code> nhưng client gửi tên <code>inventory</code>, server không thể chọn đúng tệp theo ý định của nhóm.

### Sai profile hoặc label

Client có thể kết nối thành công nhưng yêu cầu sai profile hoặc label. Ví dụ, pipeline triển khai production nhưng <code>SPRING_PROFILES_ACTIVE=dev</code>; hoặc client dùng label mặc định <code>main</code> thay vì tag phát hành.

Hãy đối chiếu ba giá trị thực tế trong log và request:

| Giá trị | Nguồn thường gặp | Dấu hiệu sai |
|---|---|---|
| Application | <code>spring.application.name</code> | Server chỉ trả cấu hình dùng chung hoặc tệp của dịch vụ khác |
| Profile | <code>spring.profiles.active</code>, biến môi trường, tham số chạy | Nhận URL, mức log hoặc giới hạn của môi trường khác |
| Label | <code>spring.cloud.config.label</code> hoặc label mặc định server | Nhận giá trị cũ, mới ngoài dự kiến hoặc không tìm thấy ref |

Nếu nhiều profile cùng hoạt động, hãy kiểm tra toàn bộ danh sách profile mà client gửi. Config Server có thể nhận một chuỗi profile được phân tách theo cú pháp mà client hỗ trợ; thứ tự và cách ghép cấu hình cần được xác nhận từ phản hồi thực tế.

## 3. Lỗi kết nối giữa client và Config Server

Khi client không kết nối được server, nguyên nhân có thể nằm ở DNS, mạng, cổng, proxy, TLS hoặc trạng thái tiến trình server. Không nên kết luận Git có vấn đề chỉ vì ứng dụng báo không tải được cấu hình: client chưa tới được server thì Git backend chưa được gọi.

### DNS và định tuyến

Các triệu chứng phổ biến gồm:

- Không phân giải được hostname.
- Hostname phân giải tới IP cũ hoặc sai mạng.
- Container hoặc pod không có route tới subnet chứa Config Server.
- Network policy, firewall hoặc security group chặn cổng.
- Dịch vụ có DNS nhưng không có endpoint khỏe phía sau load balancer.

Kiểm tra từ đúng môi trường chạy của ứng dụng. Một lệnh chạy thành công trên máy phát triển không chứng minh pod production cũng truy cập được hostname đó. Với container, hãy kiểm tra DNS và kết nối từ chính container hoặc pod của client.

### Cổng và trạng thái tiến trình

Các lỗi như connection refused thường cho thấy địa chỉ đã tới được máy đích nhưng không có tiến trình lắng nghe ở cổng đó, hoặc kết nối bị từ chối bởi một lớp trung gian. Kiểm tra:

- Config Server có đang chạy không.
- Giá trị <code>server.port</code> thực tế là bao nhiêu.
- Service và target port trong nền tảng triển khai có khớp không.
- Load balancer có trỏ tới đúng cổng và đúng instance không.
- Ứng dụng có khởi động xong trước khi client gửi yêu cầu không.

Nếu Config Server khởi động chậm do clone Git hoặc kiểm tra repository, health check của nền tảng có thể đánh dấu instance chưa sẵn sàng. Cần phân biệt trạng thái tiến trình đã chạy với trạng thái server đã sẵn sàng phục vụ cấu hình.

### TLS, chứng thư và proxy

Khi dùng HTTPS, client phải tin cậy chứng thư mà server trình bày. Lỗi handshake có thể do chứng thư hết hạn, hostname không khớp Subject Alternative Name, CA chưa được đưa vào truststore hoặc cấu hình TLS giữa hai phía không tương thích.

Nếu server yêu cầu mutual TLS, client còn phải cung cấp chứng thư và private key phù hợp. Việc cấu hình truststore chỉ giúp client xác thực server; nó không thay thế keystore dùng để client chứng minh danh tính.

Trong môi trường có proxy, kiểm tra proxy được cấu hình cho đúng tiến trình Java và có cho phép hostname Config Server hay không. Không nên vô hiệu hóa kiểm tra chứng thư để chữa lỗi tạm thời; cách đó làm mất khả năng xác thực đầu kia của kết nối.

### Timeout và tải cao

Timeout có thể xuất hiện khi:

- DNS hoặc kết nối mạng chậm.
- Config Server đang quá tải hoặc bị giới hạn CPU/bộ nhớ.
- Server phải fetch Git từ remote trong lúc repository chưa được cập nhật.
- Git remote phản hồi chậm.
- Nhiều client cùng khởi động sau một đợt triển khai.

Hãy phân biệt timeout kết nối với timeout đọc phản hồi. Tăng timeout một cách máy móc có thể kéo dài thời gian khởi động và làm dồn nhiều yêu cầu đang chờ. Trước hết, đo thời gian ở từng chặng và kiểm tra tài nguyên server, Git remote, số lượng client khởi động đồng thời.

## 4. Lỗi ở Config Server

Config Server là điểm tiếp nhận yêu cầu từ nhiều client. Lỗi tại đây có thể làm ảnh hưởng hàng loạt dịch vụ.

### Server không khởi động hoặc chưa sẵn sàng

Một Config Server cơ bản cần dependency phù hợp và được bật chức năng server bằng <code>@EnableConfigServer</code>. Nếu thiếu cấu hình hoặc dependency, ứng dụng có thể khởi động như một Spring Boot app thông thường mà không cung cấp endpoint Config Server như mong đợi.

Ngoài việc kiểm tra tiến trình và cổng, hãy xem log lúc khởi động để tìm lỗi cấu hình backend. Nếu bật chế độ clone repository ngay khi khởi động, server có thể thất bại trước khi sẵn sàng do Git URI, quyền truy cập hoặc DNS tới remote bị sai.

Không nên chỉ kiểm tra một endpoint health chung rồi kết luận Config Server đã hoạt động đầy đủ. Health của tiến trình và khả năng đọc được repository là hai điều kiện khác nhau. Hãy kiểm tra cả endpoint cấu hình bằng một bộ application/profile/label thử nghiệm đã biết.

### HTTP 401 và 403

HTTP 401 thường liên quan tới việc thiếu hoặc sai thông tin xác thực. HTTP 403 thường cho thấy danh tính đã được nhận diện nhưng không có quyền thực hiện yêu cầu. Cần xác định lớp nào đang trả mã này:

- Reverse proxy hoặc API gateway.
- Spring Security ở Config Server.
- Cơ chế bảo vệ ở Git remote.

Client gọi Config Server có thể cần thông tin xác thực riêng; Config Server gọi Git remote lại dùng danh tính khác. Thành công ở lớp này không bảo đảm lớp kia thành công. Không gửi token Git cho mọi Config Client chỉ để làm cho request chạy được.

### HTTP 404 hoặc cấu hình không có giá trị mong đợi

Một endpoint sai path, application không tồn tại, profile/label không hợp lệ hoặc ref Git không có có thể dẫn tới phản hồi không như mong đợi. Tùy phiên bản và cách cấu hình, một số trường hợp không tìm thấy cấu hình có thể trả về Environment rỗng thay vì biểu hiện lỗi giống nhau.

Vì vậy, không chỉ dựa vào status code. Hãy đọc body phản hồi, danh sách <code>propertySources</code>, metadata phiên bản và log phía server. Một phản hồi thành công nhưng không chứa property source dự kiến vẫn là một lỗi cấu hình đối với dịch vụ.

### HTTP 5xx

Lỗi 5xx thường cho thấy server không hoàn thành yêu cầu. Nguyên nhân có thể là lỗi repository, lỗi giải mã bí mật, lỗi backend composite, hết tài nguyên hoặc exception trong xử lý request.

Ghi lại thời điểm, request path đã loại bỏ dữ liệu nhạy cảm, mã phản hồi và correlation/request ID nếu có. Sau đó đối chiếu log server cùng thời điểm để tìm exception gốc. Log client thường chỉ cho biết không lấy được cấu hình; log server mới cho thấy thao tác nào thất bại.

## 5. Lỗi ở Git backend và kho cấu hình

Khi Config Server nhận được request nhưng không lấy được nội dung mong muốn, cần kiểm tra kết nối từ chính server tới Git remote. Git backend có thể dùng HTTPS hoặc SSH; mỗi cách có bộ thông tin xác thực và kiểm tra danh tính riêng.

### URI và quyền truy cập repository

Các lỗi thường gặp:

- URI sai, repository bị đổi tên hoặc chuyển tổ chức.
- Repository private nhưng server thiếu token hoặc deploy key.
- Token hết hạn, bị thu hồi hoặc thiếu scope đọc.
- SSH key không đúng với tài khoản/deploy key.
- Máy chủ không phân giải được hostname Git hoặc không đi được qua proxy.
- SSH host key chưa được xác minh trong known_hosts hoặc host key remote đã thay đổi.

Kiểm tra kết nối từ máy chạy Config Server, với đúng tài khoản và cấu hình mà tiến trình server sử dụng. Một lần clone thành công bằng tài khoản cá nhân trên laptop không chứng minh service account trong production có quyền tương tự.

Thông tin xác thực Git nên được cấp cho Config Server bằng secret manager, biến môi trường hoặc cơ chế quản lý bí mật của nền tảng. Tránh ghi token hoặc private key vào repository cấu hình, log hay tệp cấu hình được chia sẻ rộng.

### Nhánh, tag hoặc commit không tồn tại

Một label có thể trỏ tới ref đã bị xóa, đổi tên hoặc chưa được đẩy lên remote. Ví dụ client yêu cầu <code>release-2026.11</code> nhưng Git remote chỉ có <code>release-2026.10</code>. Server có thể báo lỗi khi resolve label hoặc không lấy được cấu hình tương ứng.

Đối chiếu label được client gửi với danh sách branch, tag hoặc commit đang tồn tại ở remote. Kiểm tra cả chữ hoa/chữ thường và quy ước đặt tên. Đừng dùng tên môi trường thay cho label trừ khi nhóm đã tạo ref tương ứng.

### Sai đường dẫn và tên tệp

Với Git backend mặc định, Config Server tìm các tệp theo tên application và profile. Các tệp thường gặp gồm:

~~~text
config-repo/
├── application.yml
├── application-staging.yml
├── inventory-service.yml
└── inventory-service-staging.yml
~~~

Nếu client gửi application là <code>inventory-api</code> trong khi repository dùng <code>inventory-service</code>, cấu hình riêng sẽ không được tìm thấy. Nếu profile là <code>staging</code> nhưng tệp lại đặt tên <code>inventory-service-stage.yml</code>, server cũng không tự hiểu hai tên đó tương đương.

Khi dùng <code>searchPaths</code> hoặc nhiều repository, hãy kiểm tra thư mục tìm kiếm và quy tắc khớp tệp. Một tệp có thể tồn tại trong repository nhưng nằm ngoài search path mà server đang dùng.

### Lỗi nội dung YAML hoặc Properties

Tệp có thể được tải thành công nhưng không chứa cấu trúc mà ứng dụng mong đợi. Các lỗi thường gặp:

- YAML sai thụt lề hoặc cú pháp.
- Khóa bị viết sai chính tả.
- Giá trị có kiểu dữ liệu khác với kiểu mà ứng dụng yêu cầu.
- Cấu hình bị đặt dưới nhánh YAML khác.
- Profile-specific file không chứa khóa mà ứng dụng cần.
- Một giá trị rỗng hoặc placeholder chưa được thay thế.

Phản hồi Config Server cho biết server đã tìm thấy property source nào. Hãy đọc nội dung cấu hình đã được phân giải và so sánh với schema hoặc <code>@ConfigurationProperties</code> của ứng dụng. Nếu YAML parse được nhưng giá trị không hợp lệ với bean, lỗi có thể chỉ xuất hiện lúc bind hoặc khởi tạo bean phía client.

### Bản clone cục bộ và cập nhật remote

Git backend thường duy trì một bản clone cục bộ để đọc cấu hình. Nếu clone không fetch được thay đổi mới, server có thể tiếp tục trả nội dung cũ. Nguyên nhân gồm lỗi mạng tới remote, credential đã hết hạn, ref không cập nhật hoặc bản clone cục bộ gặp trạng thái bất thường.

Kiểm tra:

- Log fetch/pull của Config Server tại thời điểm request.
- Commit hoặc version mà server trả về nếu metadata phản hồi có cung cấp.
- Ref mà server đang dùng so với ref trên Git remote.
- Cấu hình refresh của Git backend và thời gian cache.
- Sự khác nhau giữa các instance Config Server nếu đang chạy nhiều replica.

Không xóa bản clone trên production như phản xạ đầu tiên. Trước hết xác định server nào đang phục vụ request, bản clone nào đang có vấn đề và liệu có replica khỏe để chuyển lưu lượng hay không. Nếu cần làm mới bản clone, thực hiện theo quy trình vận hành có kiểm soát và xác nhận lại version sau đó.

## 6. Lỗi khi ghép nhiều nguồn cấu hình

Một số hệ thống dùng nhiều repository hoặc composite repository để ghép cấu hình từ nhiều nguồn. Khi đó một request có thể phụ thuộc vào nhiều backend. Nếu một nguồn không truy cập được, kết quả có thể không đầy đủ hoặc toàn bộ request thất bại tùy chính sách cấu hình.

Cần làm rõ:

- Mỗi repository chịu trách nhiệm cho nhóm ứng dụng hoặc thuộc tính nào.
- Thứ tự ưu tiên giữa các repository.
- Một backend không sẵn sàng có làm toàn bộ request thất bại không.
- Có cho phép bỏ qua backend lỗi hay không, và việc đó có an toàn với cấu hình bắt buộc không.

Với composite repository, thuộc tính <code>spring.cloud.config.server.fail-on-composite-error</code> điều khiển hành vi khi một thành phần gặp lỗi trong một số cấu hình. Nếu cho phép bỏ qua backend lỗi, server có thể trả về cấu hình thiếu mà ứng dụng vẫn khởi động. Cần đánh giá theo tính chất dữ liệu: thiếu một cờ giao diện có thể chấp nhận được, nhưng thiếu URL dịch vụ hoặc chính sách bảo mật thì không.

Một nguyên tắc hữu ích là tách cấu hình bắt buộc khỏi cấu hình tùy chọn. Các thuộc tính bắt buộc nên được kiểm tra ở client khi khởi động bằng validation rõ ràng; không nên coi việc server trả HTTP 200 là bằng chứng toàn bộ cấu hình cần thiết đã có mặt.

## 7. Khi client nhận cấu hình nhưng ứng dụng vẫn chạy sai

Đây là nhóm lỗi khó nhận diện vì kết nối và phản hồi HTTP có thể đều thành công.

### Nguồn khác ghi đè cấu hình từ xa

Sau khi client nhận property source từ Config Server, biến môi trường, tham số JVM, tham số dòng lệnh hoặc tệp cục bộ có thể cung cấp cùng một khóa. Giá trị hiệu lực phụ thuộc thứ tự ưu tiên của Spring Boot và chính sách ghi đè được cấu hình cho Config Client.

Ví dụ, Config Server trả về:

~~~yaml
inventory:
  api-base-url: https://inventory.internal
~~~

Nhưng môi trường triển khai có biến:

~~~text
INVENTORY_API_BASE_URL=http://localhost:8091
~~~

Nếu nguồn cục bộ có độ ưu tiên cao hơn trong cấu hình hiện tại, ứng dụng có thể dùng URL localhost dù server đã trả đúng URL production.

Hãy xác định giá trị cuối cùng và nguồn đã cung cấp nó. Có thể dùng Actuator <code>env</code> hoặc <code>configprops</code> khi được bật và bảo vệ đúng cách. Các endpoint này có thể tiết lộ thông tin nội bộ, do đó chỉ cấp quyền cho người vận hành phù hợp và che giá trị nhạy cảm.

### Cấu hình đã tải nhưng bean không cập nhật

Không phải mọi đối tượng trong Spring đều tự thay đổi khi property source được refresh. Một bean đã khởi tạo có thể giữ giá trị cũ; connection pool hoặc client thư viện có thể cần tạo lại. Các bean hỗ trợ <code>@RefreshScope</code> có cơ chế tạo lại khi refresh, nhưng điều đó không bảo đảm mọi tài nguyên bên ngoài đều được thay đổi an toàn.

Hãy kiểm tra nơi thuộc tính được bind, vòng đời bean, khả năng refresh của thư viện và log sau thao tác. Nếu thay đổi liên quan tới cổng lắng nghe, datasource hoặc cấu trúc tài nguyên không thể cập nhật tại chỗ, nên triển khai lại dịch vụ theo quy trình.

### Client dùng cấu hình cũ

Một commit mới trong Git không tự động cập nhật các client đang chạy. Cần xác định cơ chế refresh đã được thiết kế: gọi refresh cho instance, phát sự kiện qua Spring Cloud Bus hoặc triển khai lại.

Nếu dùng Bus, kiểm tra broker, kết nối của từng instance, quyền truy cập endpoint phát sự kiện và log nhận sự kiện. Sự kiện được gửi thành công từ một instance không đồng nghĩa mọi instance đều nhận và xử lý thành công.

## 8. Timeout, retry và fail-fast

Không phải mọi lỗi cấu hình đều có cùng cách xử lý. Một lỗi DNS tạm thời có thể hồi phục sau vài giây; một label bị gõ sai sẽ không tự đúng dù client thử lại nhiều lần.

### Chọn hành vi khi Config Server không sẵn sàng

Với Config Data API, import có tiền tố <code>optional:</code> cho phép ứng dụng tiếp tục khởi động khi nguồn cấu hình từ xa không lấy được. Điều này có thể hữu ích nếu ứng dụng có bộ cấu hình cục bộ an toàn và có thể hoạt động ở chế độ giới hạn.

~~~yaml
spring:
  config:
    import: "optional:configserver:http://config.internal:8888"
~~~

Nếu ứng dụng cần cấu hình tập trung để kết nối đúng dịch vụ hoặc áp dụng chính sách bảo mật, bỏ qua lỗi có thể làm ứng dụng khởi động với giá trị mặc định không phù hợp. Trong trường hợp đó, nên để import bắt buộc và làm cho lỗi khởi động hiển thị rõ.

Quyết định này cần dựa trên mức độ thiết yếu của cấu hình:

| Loại cấu hình | Hành vi thường phù hợp |
|---|---|
| URL dịch vụ bắt buộc | Không khởi động nếu không lấy được giá trị hợp lệ |
| Thông tin xác thực hoặc chính sách bảo mật | Không tiếp tục với giá trị mặc định không an toàn |
| Mức log hoặc thuộc tính chẩn đoán tùy chọn | Có thể dùng mặc định cục bộ nếu đã được phê duyệt |
| Cờ tính năng có ảnh hưởng dữ liệu | Cần giá trị mặc định an toàn và validation rõ ràng |

### Retry có giới hạn

Retry hữu ích với lỗi tạm thời như mất kết nối ngắn hoặc server đang khởi động. Retry không sửa được lỗi cấu hình cố định như sai hostname, sai credential, sai profile hoặc label không tồn tại.

Khi thiết kế retry:

- Giới hạn số lần thử và tổng thời gian chờ.
- Dùng backoff, có thể thêm jitter để giảm việc nhiều client thử lại cùng lúc.
- Không retry liên tục các lỗi xác thực hoặc request sai.
- Đảm bảo số lần retry không làm thời gian khởi động vượt quá giới hạn của nền tảng.
- Đo tỷ lệ thành công sau retry và ghi nhận nguyên nhân ban đầu.

Spring Cloud Config hỗ trợ các tùy chọn retry theo cơ chế và phiên bản tích hợp. Một số cách cấu hình cần thêm thư viện retry hoặc khai báo tham số trong Config Data import. Hãy dùng tài liệu đúng phiên bản của dự án và kiểm tra log để xác nhận retry thực sự được áp dụng.

### Khả năng sẵn sàng của Config Server

Với hệ thống quan trọng, có thể triển khai nhiều Config Server instance sau load balancer. Tuy nhiên, mỗi instance phải có cùng cấu hình backend, quyền truy cập Git, CA/truststore, khóa giải mã nếu có và quy tắc phân giải cấu hình.

Các replica có thể có bản clone cục bộ và thời điểm fetch khác nhau. Nếu một instance trả commit mới trong khi instance khác còn commit cũ, client có thể nhận kết quả không nhất quán tùy request được định tuyến tới đâu. Cần theo dõi version/ref được phục vụ và có quy trình phát hành để các instance hội tụ trước khi chuyển client sang label mới.

## 9. Bảo mật cũng là một điểm có thể gây lỗi

Cấu hình bảo mật sai có thể biểu hiện thành lỗi kết nối, lỗi xác thực hoặc lỗi giải mã. Khi điều tra, cần tách ba danh tính:

1. **Client tới Config Server:** xác thực người gọi và quyền đọc endpoint cấu hình.
2. **Config Server tới Git:** quyền đọc repository bằng token, SSH key hoặc danh tính máy.
3. **Config Server giải mã bí mật:** quyền sử dụng khóa mã hóa hoặc keystore.

Mỗi danh tính có mục đích và vòng đời riêng. Thay token Git không giải quyết lỗi xác thực client; cập nhật truststore của client cũng không sửa được SSH key của Config Server.

Những lỗi thường gặp:

- Token hết hạn nhưng chỉ được thay ở một trong nhiều replica.
- Chứng thư mới được cài trên load balancer nhưng client chưa tin CA tương ứng.
- Server dùng sai alias hoặc mật khẩu keystore.
- Khóa giải mã thay đổi nhưng ciphertext vẫn được mã hóa bằng khóa cũ.
- Endpoint cấu hình hoặc Actuator bị chặn bởi security rule mới.
- Reverse proxy bỏ header Authorization hoặc thay đổi path.

Không đưa token, mật khẩu, private key hoặc giá trị cấu hình nhạy cảm vào log để chẩn đoán. Khi cần chia sẻ log, hãy che thông tin xác thực, query parameter nhạy cảm và nội dung property source có bí mật.

## 10. Bảng triệu chứng và hướng khoanh vùng

Bảng sau giúp chọn điểm kiểm tra đầu tiên. Một triệu chứng có thể có nhiều nguyên nhân; hãy xác nhận bằng log và phản hồi thực tế.

| Triệu chứng | Vùng nghi ngờ đầu tiên | Kiểm tra tiếp theo |
|---|---|---|
| Client báo không nhận diện <code>configserver:</code> | Dependency hoặc cấu hình import | Kiểm tra Config Client dependency và cách nạp Config Data |
| Unknown host | DNS hoặc hostname | Phân giải DNS từ đúng container/pod |
| Connection refused | Cổng hoặc tiến trình server | Kiểm tra listener, service port và trạng thái instance |
| Connect/read timeout | Mạng, tải server hoặc Git remote | Đo thời gian từng chặng và xem log server |
| TLS handshake failed | Chứng thư, truststore, hostname hoặc mTLS | Kiểm tra chain, hạn chứng thư và danh tính hai phía |
| HTTP 401 | Thiếu hoặc sai thông tin xác thực | Xác định lớp trả lỗi và credential tương ứng |
| HTTP 403 | Quyền truy cập | Kiểm tra role, scope và security rule |
| HTTP 404 hoặc Environment rỗng | Path, application, profile, label hoặc repository | Đối chiếu request và ref/tệp trong Git |
| Server trả property source thiếu | Search path, tên tệp hoặc backend ghép | Kiểm tra danh sách property source và từng repository |
| Server trả giá trị cũ | Fetch/cache/ref hoặc replica không đồng bộ | So sánh commit/version ở remote và từng server |
| Client nhận đúng nhưng dùng giá trị khác | Property source ưu tiên hoặc bean giữ giá trị cũ | Kiểm tra Actuator, biến môi trường và vòng đời bean |
| Một số instance cập nhật, số khác không | Refresh/Bus hoặc replica | Kiểm tra từng instance và broker |
| Server khởi động thất bại khi clone repo | Git URI, DNS hoặc quyền Git | Đọc exception lúc startup và kiểm tra kết nối remote |

## 11. Quy trình xử lý sự cố từ đầu tới cuối

Khi có cảnh báo ứng dụng không lấy được cấu hình, nên đi theo thứ tự để tránh thay đổi nhiều thành phần cùng lúc.

### Bước 1: Ghi lại yêu cầu thực tế

Thu thập:

- Tên ứng dụng.
- Danh sách profile đang hoạt động.
- Label được yêu cầu hoặc label mặc định.
- URL Config Server và instance client đang gọi.
- Thời điểm xảy ra lỗi, môi trường và phiên bản ứng dụng.

Không lấy các giá trị dự kiến từ tài liệu triển khai rồi coi đó là giá trị thực tế. Hãy xác minh từ log hoặc request.

### Bước 2: Kiểm tra client tới server

Từ cùng môi trường chạy client, kiểm tra DNS, cổng, TLS và HTTP. Gọi trực tiếp endpoint cấu hình với application/profile/label đã ghi nhận. Nếu không kết nối được, xử lý mạng hoặc trạng thái server trước khi kiểm tra Git.

### Bước 3: Đọc phản hồi HTTP

Phân biệt status code, body và danh sách property source. Ghi nhận request ID nếu có. Xác định server trả lỗi, trả Environment rỗng hay trả cấu hình nhưng thiếu một khóa.

### Bước 4: Kiểm tra log Config Server

Tìm request cùng thời điểm và xác định server đã đi tới bước nào: xác thực, chọn repository, fetch Git, resolve label, đọc tệp hay giải mã giá trị. Đọc exception gốc thay vì chỉ nhìn thông báo tổng quát phía client.

### Bước 5: Kiểm tra Git từ phía server

Xác minh remote URI, credential, branch/tag/commit, search path và tệp cấu hình. So sánh version mà server đang phục vụ với version trên remote. Nếu có nhiều replica, kiểm tra từng instance.

### Bước 6: Xác minh giá trị hiệu lực phía client

Nếu Config Server trả đúng dữ liệu, kiểm tra property source ưu tiên, biến môi trường, tham số JVM và giá trị đã bind vào bean. Kiểm tra cả vòng đời bean nếu cấu hình vừa được refresh.

### Bước 7: Phục hồi và xác nhận

Chọn hành động nhỏ nhất phù hợp nguyên nhân: sửa import, khôi phục DNS, cấp lại credential, đẩy đúng Git ref, sửa tệp, đồng bộ replica, refresh hoặc triển khai lại. Sau phục hồi, xác nhận lại đúng application, profile, label, version và các thuộc tính bắt buộc.

Không kết thúc sự cố chỉ vì HTTP status đã trở thành 200. Cần xác nhận ứng dụng đang sử dụng đúng giá trị và các chức năng phụ thuộc cấu hình đã hoạt động.

## 12. Ví dụ điều tra: production nhận nhầm cấu hình staging

Giả sử <code>inventory-service</code> được triển khai ở production nhưng log cho thấy ứng dụng gọi:

~~~http
GET /inventory-service/staging/main
~~~

Trong khi nhóm dự kiến production dùng profile <code>prod</code> và label <code>release-2026.11</code>.

Đường điều tra:

1. Kiểm tra biến môi trường <code>SPRING_PROFILES_ACTIVE</code>; phát hiện pipeline đã truyền <code>staging</code> do tái sử dụng biến của job kiểm thử.
2. Kiểm tra <code>spring.cloud.config.label</code>; client không nhận label phát hành nên dùng default label <code>main</code>.
3. So sánh phản hồi Config Server; property source đúng với yêu cầu staging/main, chứng minh server đang làm đúng theo request nhận được.
4. Sửa biến triển khai để profile là <code>prod</code>, cấu hình label thành <code>release-2026.11</code>.
5. Triển khai lại hoặc khởi động lại theo quy trình để client tạo request mới.
6. Xác nhận request mới, version Git, URL dịch vụ và các thuộc tính production đã được nạp.

Trường hợp này không phải lỗi Git hay lỗi kết nối. Cả server lẫn repository có thể hoạt động bình thường; lỗi nằm ở dữ liệu đầu vào mà client gửi. Việc ghi nhận đủ ba thành phần application/profile/label giúp tránh sửa nhầm backend.

## 13. Chuẩn bị để giảm thời gian gián đoạn

Một kiến trúc Config có thể vận hành ổn định hơn nếu nhóm chuẩn bị sẵn các thông tin và kiểm tra sau:

- **Health check có ý nghĩa:** kiểm tra trạng thái server và khả năng đọc backend cần thiết; phân biệt liveness với readiness.
- **Log có ngữ cảnh:** ghi request path đã loại bỏ dữ liệu nhạy cảm, application, profile, label, server instance và thời gian xử lý.
- **Theo dõi Git version:** lưu commit/ref được phục vụ để có thể đối chiếu giữa các replica.
- **Cảnh báo lỗi có phân loại:** phân biệt lỗi kết nối, xác thực, Git fetch, resolve label, parse/bind và refresh.
- **Credential có vòng đời:** có lịch xoay vòng, chủ sở hữu và cách cập nhật đồng bộ trên mọi server replica.
- **Thay đổi cấu hình có kiểm soát:** review, kiểm tra ở staging, ghim label production và chuẩn bị rollback.
- **Bộ cấu hình dự phòng có chủ đích:** chỉ cho phép client tiếp tục khi thiếu server nếu bộ cấu hình cục bộ thực sự an toàn và đã được kiểm tra.
- **Diễn tập phục hồi:** thử tình huống Git remote mất kết nối, credential hết hạn, server replica lỗi và refresh không tới được một số client.

Một số endpoint Actuator như <code>health</code>, <code>env</code> hoặc <code>configprops</code> có thể hỗ trợ vận hành. Chỉ mở những endpoint cần thiết, giới hạn quyền truy cập và che thông tin nhạy cảm. Việc thêm endpoint chẩn đoán mà không kiểm soát quyền có thể tạo ra một điểm rò rỉ cấu hình mới.

## 14. Checklist khi xử lý lỗi Config

- [ ] Đã ghi lại application, profile, label và URL server mà client thực sự sử dụng.
- [ ] Đã xác nhận Config Client dependency và cơ chế import phù hợp với phiên bản dự án.
- [ ] Đã kiểm tra DNS, route, cổng, TLS, proxy và timeout từ đúng môi trường client.
- [ ] Đã xác nhận Config Server đang sẵn sàng và endpoint được bảo vệ đúng cách.
- [ ] Đã phân biệt lỗi HTTP 401, 403, 404, 5xx và phản hồi Environment rỗng.
- [ ] Đã kiểm tra Git URI, credential, ref, search path và nội dung tệp từ phía server.
- [ ] Đã đối chiếu version/ref giữa Git remote và từng Config Server replica.
- [ ] Đã kiểm tra property source ưu tiên và giá trị thực tế được bind vào bean.
- [ ] Đã xác minh refresh hoặc Bus tới tất cả instance cần cập nhật.
- [ ] Đã xác nhận ứng dụng hoạt động với đúng cấu hình sau khi phục hồi.

Một sự cố Config thường xuất hiện ở ranh giới giữa nhiều thành phần. Việc kiểm tra theo luồng từ client, mạng, server, repository tới Spring Environment giúp tìm đúng mắt xích lỗi, giảm thay đổi thử-sai và khôi phục cấu hình có thể truy vết.
