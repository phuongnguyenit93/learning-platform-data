# Ứng dụng đã chạy so với ứng dụng vừa khởi động khi mất nguồn cấu hình

Khi Config Server hoặc repository cấu hình gặp sự cố, một ứng dụng vừa khởi động và một ứng dụng đã chạy ổn định thường có hành vi khác nhau. Ứng dụng mới cần lấy cấu hình trong quá trình bootstrap. Nếu nguồn cấu hình bắt buộc không truy cập được, quá trình khởi động có thể thất bại. Ứng dụng đang chạy thường đã nạp cấu hình vào Spring Environment và bind giá trị vào bean; việc mất kết nối sau đó không tự động xóa các giá trị đang nằm trong bộ nhớ.

Sự khác biệt này tạo ra một rủi ro vận hành dễ bị bỏ sót: hệ thống vẫn phục vụ traffic bằng các instance cũ, nhưng không thể thay thế instance lỗi hoặc scale out vì replica mới không lấy được cấu hình. Nếu restart hàng loạt trong lúc Config Server hoặc Git đang mất kết nối, số instance sẵn sàng có thể giảm nhanh.

Bài học này phân tích hai thời điểm đó, cách Spring Cloud Config Client xử lý nguồn cấu hình bắt buộc và tùy chọn, retry khi khởi động, hành vi refresh khi đang chạy, chính sách stale configuration, local fallback, readiness/liveness và cách phục hồi sau khi nguồn cấu hình hoạt động trở lại.

Sau bài học, bạn có thể:

- Giải thích vì sao process đang chạy có thể tiếp tục dùng cấu hình đã nạp khi Config Server mất kết nối.
- Dự đoán hành vi của instance mới khi Config Server không truy cập được.
- Phân biệt Config Data import bắt buộc với import có tiền tố optional.
- Cấu hình fail-fast và retry phù hợp với chế độ bootstrap đang dùng.
- Nhận biết refresh thất bại khác với mất kết nối thông thường.
- Thiết kế last-known-good, local fallback và chính sách giới hạn tuổi cấu hình.
- Dùng readiness và liveness để tránh restart loop khi nguồn cấu hình gián đoạn.
- Phục hồi theo canary và xác minh cấu hình trên từng instance.

## 1. Hai thời điểm, hai đường đi cấu hình

Ứng dụng lấy cấu hình từ xa trong quá trình khởi động. Với Config Data API, Spring Boot đọc <code>spring.config.import</code> rồi gọi Config Server trước khi hoàn tất việc tạo application context. Với bootstrap legacy, Config Client tải property source trong bootstrap context trước khi context chính được tạo.

Sau khi khởi động, Environment và các bean đã nhận cấu hình. Khi Config Server mất kết nối, process không tự động quay lại bước bootstrap. Nó tiếp tục sử dụng trạng thái đã nạp cho tới khi có một hành động khác như refresh, restart hoặc logic riêng của ứng dụng thay đổi cấu hình.

~~~mermaid
flowchart TD
    A["Config Server / Git mất kết nối"] --> B{"Ứng dụng ở trạng thái nào?"}
    B -->|"Đang khởi động"| C["Config Client cần fetch remote config"]
    C --> D{"Import bắt buộc?"}
    D -->|"Có"| E["Retry theo policy rồi fail startup nếu vẫn lỗi"]
    D -->|"Không, optional"| F["Tiếp tục bằng cấu hình local/default"]
    B -->|"Đã chạy"| G["Environment và bean đã có snapshot"]
    G --> H["Tiếp tục dùng giá trị trong process"]
    H --> I["Refresh hoặc restart trong lúc nguồn vẫn lỗi?"]
    I --> J["Refresh có thể thất bại; cần kiểm tra trạng thái"]
    I --> K["Restart phải fetch lại; có thể không khởi động được"]
~~~

Có thể hình dung:

- **Instance cũ:** đã có cấu hình trong bộ nhớ, có thể tiếp tục xử lý request.
- **Instance mới:** chưa có snapshot cấu hình, phải lấy nguồn cần thiết hoặc dùng fallback được thiết kế trước.
- **Instance được refresh:** chủ động yêu cầu cấu hình mới; đây là một lần truy cập nguồn từ xa khác với việc process giữ cấu hình cũ.

Mất nguồn cấu hình không nhất thiết làm toàn bộ ứng dụng dừng ngay. Rủi ro lớn nhất thường xuất hiện khi một instance cần restart, scale out hoặc refresh trong lúc nguồn chưa phục hồi.

## 2. Điều gì được giữ lại trong ứng dụng đang chạy?

Sau khi Config Client tải Environment thành công, các property source được thêm vào Spring Environment trong process. Bean dùng <code>@ConfigurationProperties</code>, <code>@Value</code> hoặc constructor injection đã nhận giá trị theo cơ chế bind tương ứng.

Ví dụ:

~~~yaml
orders:
  reservation:
    endpoint: https://inventory.internal
    timeout: 2s
    max-attempts: 3
~~~

~~~java
@ConfigurationProperties(prefix = "orders.reservation")
public class ReservationProperties {

    private URI endpoint;
    private Duration timeout;
    private int maxAttempts;

    // getters và setters
}
~~~

Nếu Config Server ngừng hoạt động sau khi bean đã được tạo:

- Spring Environment vẫn chứa property source đã nạp trong process.
- Bean đã bind vẫn giữ các giá trị đã nhận.
- Một lời gọi nghiệp vụ không tự động truy vấn Config Server cho mỗi property.
- Một HTTP client hoặc connection pool đã được tạo có thể tiếp tục dùng cấu hình cũ.
- Log có thể báo lỗi khi có refresh hoặc health check chủ động gọi Config Server, dù request nghiệp vụ vẫn hoạt động.

Điều này không có nghĩa mọi thành phần đều tiếp tục khỏe mạnh. Nếu ứng dụng tự gọi Config Server trong runtime, dùng dynamic secret lease, tự tạo client mới hoặc có refresh watcher, những phần đó vẫn có thể gặp lỗi. Cũng cần tách sự cố Config Server khỏi sự cố của dependency nghiệp vụ: cấu hình cũ có thể còn trong bộ nhớ nhưng database hoặc downstream mà cấu hình trỏ tới đã hỏng.

### Cấu hình đang chạy là snapshot, không phải bản sao bền vững

Snapshot trong Environment nằm trong bộ nhớ của process. Nó không mặc nhiên được lưu thành bản cache bền vững để dùng lại sau restart.

Khi process bị dừng và khởi động lại, bộ nhớ cũ mất đi. Instance mới phải lấy cấu hình từ Config Server hoặc một nguồn fallback được cấu hình rõ ràng. Không nên coi việc một replica cũ vẫn chạy được là bằng chứng rằng hệ thống có thể khởi động lại trong lúc Config Server đang mất.

## 3. Instance mới cần nguồn cấu hình ngay trong startup

Với Config Data API, ứng dụng thường khai báo:

~~~yaml
spring:
  config:
    import: "configserver:https://config.internal"
~~~

Import không có tiền tố <code>optional:</code> là bắt buộc. Nếu Config Server không truy cập được và không có cơ chế phục hồi thành công, quá trình khởi động sẽ thất bại.

Điều này phù hợp khi ứng dụng không thể hoạt động an toàn nếu thiếu cấu hình từ xa, ví dụ:

- Endpoint database hoặc credential bắt buộc chỉ có ở Config Server.
- Các giới hạn an toàn phải được nạp trước khi nhận traffic.
- Ứng dụng cần biết đúng tenant, queue hoặc downstream để tránh xử lý nhầm dữ liệu.
- Không có local default an toàn cho các thuộc tính cốt lõi.

Lợi ích của startup fail là không đưa một instance thiếu cấu hình vào service pool. Nhược điểm là khả năng scale out hoặc phục hồi replica phụ thuộc vào tính sẵn sàng của Config Server và backend cấu hình.

### Import tùy chọn

Nếu khai báo:

~~~yaml
spring:
  config:
    import: "optional:configserver:https://config.internal"
~~~

ứng dụng được phép tiếp tục startup khi không lấy được cấu hình từ Config Server. Nó sẽ dùng các nguồn còn lại như cấu hình đóng gói trong artifact, file local, biến môi trường và default trong code.

Optional không tạo ra một bản sao cấu hình từ xa. Nó chỉ cho phép bỏ qua nguồn không khả dụng. Nếu một thuộc tính bắt buộc không có ở các nguồn còn lại, ứng dụng vẫn có thể thất bại khi bind, validate hoặc khởi tạo bean.

Dùng optional chỉ khi ứng dụng có chế độ chạy suy giảm được thiết kế và kiểm thử. Không dùng optional để che lỗi kết nối trong khi vẫn giả định instance mới đã có cấu hình production đầy đủ.

## 4. Legacy bootstrap và fail-fast

Các dự án dùng bootstrap legacy thường khai báo địa chỉ Config Server trong <code>bootstrap.yml</code>:

~~~yaml
spring:
  application:
    name: orders-service
  cloud:
    config:
      uri: https://config.internal
      fail-fast: true
~~~

Với <code>fail-fast: true</code>, client yêu cầu quá trình bootstrap thất bại khi không thể lấy cấu hình từ xa theo policy. Đây là cách ngăn instance mới chạy với cấu hình thiếu khi remote configuration là bắt buộc.

Nếu fail-fast bị tắt, một số cấu hình legacy cho phép ứng dụng tiếp tục khởi động sau lỗi fetch, tùy phiên bản và cách cấu hình. Khi đó, cần kiểm tra rõ giá trị nào được dùng thay thế và liệu ứng dụng có vượt qua validation an toàn hay không.

Không trộn hướng dẫn Config Data API và bootstrap legacy như thể chúng là một cơ chế duy nhất. Hãy xác định dự án đang dùng cách nạp cấu hình nào, dependency nào bật bootstrap và thuộc tính nào thực sự được đọc ở giai đoạn đó.

## 5. Retry khi nguồn cấu hình tạm thời không sẵn sàng

Config Server có thể chưa sẵn sàng trong vài giây đầu do DNS, load balancer, Git clone/fetch, TLS hoặc quá trình triển khai. Retry hữu hạn giúp client vượt qua gián đoạn ngắn.

Ví dụ cấu hình retry thường gặp:

~~~yaml
spring:
  cloud:
    config:
      retry:
        max-attempts: 8
        initial-interval: 1000
        max-interval: 5000
        multiplier: 1.5
~~~

Các thuộc tính và điều kiện bật retry phụ thuộc phiên bản Spring Cloud Config và chế độ Config Data/legacy bootstrap. Nhiều cấu hình retry cần các dependency Spring Retry và AOP tương ứng. Kiểm tra tài liệu của release train đang dùng và xác nhận bằng startup test.

Retry nên có:

- Số lần thử tối đa.
- Khoảng chờ ban đầu và hệ số tăng dần.
- Giới hạn thời gian khởi động phù hợp với startup budget.
- Log và metric cho số lần thử, lỗi cuối cùng và thời gian chờ.
- Phân biệt lỗi tạm thời với lỗi cấu hình vĩnh viễn như 401/403 hoặc application/profile/label không tồn tại.

Không retry vô hạn. Nếu Config Server sai credential hoặc repository không có cấu hình cho application, lặp request chỉ kéo dài thời gian phục hồi và tạo tải lên hệ thống đang gặp sự cố.

### Retry không thay thế high availability

Retry giúp một request chịu được gián đoạn ngắn. Nó không thay thế nhiều Config Server instance, backend Git sẵn sàng, DNS/LB đáng tin cậy hoặc một chiến lược fallback. Nếu tất cả instance đều không truy cập được backend cấu hình trong thời gian dài, retry cuối cùng vẫn thất bại.

## 6. Khi Config Server mất kết nối sau khi ứng dụng đã chạy

Giả sử orders-service đã khởi động và đang dùng config label <code>release-2026.11</code>. Sau đó Config Server bị mất mạng hoặc Git backend không truy cập được.

Hành vi thường thấy:

1. Các request nghiệp vụ tiếp tục dùng bean và Environment hiện tại.
2. Health check riêng của Config Server có thể báo lỗi.
3. Một lần refresh chủ động có thể không lấy được property source mới.
4. Một sự kiện Bus refresh có thể tới ứng dụng nhưng việc fetch lại từ Config Server thất bại.
5. Nếu process restart, nó phải thực hiện startup fetch lại và có thể không khởi động được.
6. Khi nguồn phục hồi, ứng dụng không nhất thiết tự nhận cấu hình mới ngay; cần cơ chế refresh/watch hoặc rollout phù hợp.

Không nên suy luận rằng Config Client liên tục polling Config Server và tự xóa property source khi server mất. Cơ chế lấy cấu hình ban đầu và cơ chế theo dõi/refresh là các phần riêng biệt.

### Mất kết nối không đồng nghĩa cấu hình hết hạn

Config Server không tự đặt TTL chung cho mọi property source đã nạp vào Spring Environment. Nếu tổ chức muốn giới hạn tuổi của cấu hình, cần tự theo dõi thời điểm fetch thành công, config revision hoặc thời gian kể từ lần xác nhận gần nhất.

Một ứng dụng có thể tiếp tục chạy bằng cấu hình cũ nhiều giờ nếu process còn sống. Việc đó có thể là chủ đích để giữ dịch vụ hoạt động, nhưng cũng có thể tạo rủi ro nếu cấu hình cũ chứa endpoint đã bị thu hồi, certificate hết hạn hoặc policy bảo mật không còn phù hợp.

## 7. Refresh thất bại khác với việc không có refresh

Nếu không có refresh event hoặc thao tác refresh, Environment của process đang chạy thường giữ snapshot đã nạp. Khi có refresh request, ứng dụng chủ động bước vào một luồng tải lại và áp dụng cấu hình.

Ví dụ endpoint cục bộ:

~~~http
POST /actuator/refresh
~~~

Hoặc sự kiện qua Spring Cloud Bus:

~~~http
POST /actuator/busrefresh
~~~

Nếu Config Server không truy cập được tại thời điểm đó, refresh có thể thất bại. Cách Environment và bean giữ trạng thái sau lỗi phụ thuộc phiên bản, Config Client mode và thời điểm exception xảy ra. Không được coi một HTTP response lỗi là bằng chứng toàn bộ bean đã quay lại trạng thái trước đó, cũng không coi response thành công là bằng chứng mọi resource đã được tái tạo an toàn.

Với <code>@RefreshScope</code>, target bean có thể bị loại khỏi cache scope khi refresh. Target mới thường được tạo khi có lời gọi tiếp theo. Nếu cấu hình hoặc dependency không hợp lệ, việc tạo target mới có thể thất bại tại runtime. Vì thế, refresh phải được kiểm soát và theo dõi sau khi gửi.

### Quy trình khi refresh gặp lỗi

1. Dừng phát thêm refresh event diện rộng.
2. Ghi lại instance, config label, thời điểm và lỗi fetch.
3. Kiểm tra bean quan trọng và luồng nghiệp vụ đang phục vụ.
4. Không restart hàng loạt trong lúc nguồn cấu hình chưa phục hồi.
5. Nếu có thể, giữ traffic trên các instance đang hoạt động ổn định.
6. Khi nguồn trở lại, xác thực candidate và refresh một canary.
7. Chỉ mở rộng sau khi canary đã nạp và sử dụng cấu hình thành công.

Nếu không xác định được instance đang giữ trạng thái nào, dùng rolling restart theo một label/commit đã biết sau khi Config Server hoạt động trở lại.

## 8. Optional import và local fallback phải được thiết kế rõ

Optional import có thể giúp một instance mới khởi động trong lúc Config Server không sẵn sàng. Nhưng local fallback cần đủ để ứng dụng hoạt động ở một chế độ an toàn và có giới hạn.

Ví dụ cấu hình đóng gói trong artifact:

~~~yaml
# application.yml trong ứng dụng
spring:
  config:
    import: "optional:configserver:https://config.internal"

orders:
  reservation:
    enabled: false
    timeout: 1s
    max-attempts: 1
~~~

Trong ví dụ này, nếu Config Server mất kết nối, chức năng reservation bị tắt theo default an toàn. Các endpoint health hoặc chức năng không phụ thuộc reservation vẫn có thể hoạt động.

Đây chỉ là ví dụ cho một hệ thống có thể chạy degraded. Không phải ứng dụng nào cũng có thể dùng giá trị mặc định này. Với ứng dụng thanh toán, định tuyến tenant hoặc xác thực, chạy thiếu cấu hình có thể nguy hiểm hơn việc từ chối startup.

### Local fallback cần đáp ứng điều kiện nào?

- Chỉ chứa các giá trị không bí mật và thực sự cần để khởi động.
- Có default an toàn, được review và kiểm thử.
- Không chứa endpoint hoặc credential production cũ đã hết hiệu lực.
- Có chế độ degraded rõ ràng để không xử lý nghiệp vụ vượt khả năng.
- Có metric cho biết remote config không được nạp.
- Có quy trình chuyển từ fallback sang cấu hình chuẩn khi nguồn phục hồi.

Không đặt secret production trong file local để biến optional import thành cách bỏ qua Config Server. Nếu secret cần thiết, lấy từ secret manager có khả năng sẵn sàng độc lập hoặc giữ startup fail khi không thể xác thực an toàn.

## 9. Last-known-good cho instance mới

Một process đang chạy có thể giữ snapshot trong bộ nhớ, nhưng instance mới không có snapshot đó. Nếu muốn instance mới khởi động khi Config Server chính gặp sự cố, phải có một nguồn last-known-good được lưu trữ bền vững và bảo vệ.

Một số lựa chọn:

- Một Config Server replica khác cùng phục vụ đúng repository/label.
- Git mirror hoặc repository replica được kiểm soát.
- Một artifact cấu hình bất biến đã được phê duyệt và triển khai cùng release.
- Một nguồn fallback độc lập, ví dụ secret/config platform có SLA riêng.
- Một bản config snapshot đã ký và được phân phối theo quy trình release.

Không nên tự động ghi toàn bộ Environment đang chạy ra file rồi dùng lại mà không có kiểm soát. Snapshot có thể chứa secret đã giải mã, giá trị tạm thời, thuộc tính không còn hợp lệ hoặc cấu hình của một instance khác.

Một bản last-known-good cần có metadata:

| Metadata | Mục đích |
|---|---|
| Application | Xác định dịch vụ |
| Profile | Xác định môi trường |
| Label/commit | Tái lập nội dung cấu hình |
| App version | Xác nhận tương thích schema |
| Timestamp | Biết độ cũ của snapshot |
| Checksum/signature | Phát hiện nội dung bị thay đổi |
| Key/secret reference version | Xác định dependency bí mật |
| Approval/source | Truy vết người hoặc pipeline phát hành |

Chỉ dùng snapshot nếu nó được xác thực, còn trong giới hạn tuổi cho phép và tương thích với phiên bản ứng dụng đang chạy.

## 10. Config Server và Git backend cũng cần high availability

Khả năng lấy cấu hình phụ thuộc ít nhất hai tầng: endpoint Config Server và backend mà Config Server dùng để đọc cấu hình.

~~~mermaid
flowchart TD
    A["Config Clients"] --> B["Internal load balancer / DNS"]
    B --> C1["Config Server replica A"]
    B --> C2["Config Server replica B"]
    C1 --> G["Git repository / mirror"]
    C2 --> G
    C1 --> S["Secret/key provider"]
    C2 --> S
~~~

Một số nguyên tắc:

- Chạy nhiều Config Server instance sau internal load balancer.
- Các replica có cùng cấu hình bảo mật, encryption key access và repository policy.
- Dùng Git service có HA hoặc mirror được đồng bộ.
- Kiểm tra khả năng truy cập Git, credential, TLS và label ở từng Config Server.
- Không giả định local clone của một replica đồng nghĩa các replica khác có cùng revision.
- Dùng health/readiness phản ánh khả năng phục vụ config cần thiết, không chỉ process đang sống.
- Có timeout và connection pool hợp lý cho Git/backend calls.

Nếu Git upstream mất kết nối, Config Server có thể có bản clone local từ lần fetch trước, nhưng khả năng phục vụ và độ mới phụ thuộc trạng thái clone, cách fetch/pull và phiên bản. Không coi local clone là một cơ chế cache bền vững được bảo đảm nếu chưa kiểm thử tình huống đó.

### Cần kiểm tra tính nhất quán giữa các replica

Một load balancer có thể chuyển request giữa nhiều Config Server. Nếu các replica đang ở revision khác nhau, hai instance cùng yêu cầu một application/profile/label có thể nhận giá trị khác nhau.

Để tránh tình trạng đó:

- Ưu tiên label bất biến như commit hoặc tag đã phát hành.
- Theo dõi revision được phục vụ bởi từng replica.
- Không dùng branch thay đổi liên tục cho rollout cần tái lập chính xác.
- Kiểm tra repository clone/fetch sau khi Git phục hồi.
- Chỉ đưa replica trở lại pool khi nó phục vụ đúng revision và vượt readiness check.

## 11. Readiness và liveness khi nguồn cấu hình bị mất

Readiness quyết định instance có nên nhận traffic hay không. Liveness xác định process có còn sống và cần restart hay không. Không nên dùng cùng một tiêu chí cho cả hai.

Một chiến lược thường phù hợp:

| Trạng thái | Readiness | Liveness |
|---|---|---|
| Instance mới chưa lấy được cấu hình bắt buộc | Not ready hoặc startup fail | Không restart liên tục chỉ vì Config Server ngoài tiến trình đang lỗi |
| Instance cũ có last-known-good còn hợp lệ | Có thể tiếp tục ready, đồng thời báo degraded | Healthy nếu process hoạt động bình thường |
| Cấu hình đã quá tuổi tối đa theo policy | Not ready nếu nghiệp vụ không được phép dùng stale config | Process vẫn có thể live |
| Refresh thất bại nhưng snapshot cũ an toàn | Có thể tiếp tục phục vụ theo degraded policy | Healthy |
| Bean quan trọng lỗi, process không thể phục vụ | Not ready | Chỉ fail liveness nếu process thực sự không thể phục hồi |
| Config Server đã phục hồi và client nạp thành công | Ready sau khi kiểm tra nghiệp vụ | Healthy |

Không làm liveness phụ thuộc trực tiếp vào một Config Server bên ngoài nếu điều đó khiến mọi instance restart liên tục khi Config Server outage. Restart loop làm mất snapshot đang hoạt động và có thể biến một sự cố cấu hình thành outage toàn hệ thống.

### Theo dõi tuổi cấu hình

Ứng dụng có thể ghi nhận metadata riêng khi fetch config thành công:

- <code>config.last-successful-fetch</code>
- <code>config.revision</code>
- <code>config.source</code>
- <code>config.age-seconds</code>
- <code>config.refresh.failure.count</code>

Các tên trên là metric/metadata minh họa, không phải property mặc định do Spring Cloud Config tự cung cấp. Không lưu secret hoặc toàn bộ Environment trong metric.

Từ đó, readiness có thể áp dụng policy như: cho phép tiếp tục phục vụ nếu config age dưới ngưỡng; chuyển degraded hoặc not ready khi vượt ngưỡng. Ngưỡng cần dựa trên loại cấu hình và rủi ro nghiệp vụ.

## 12. Tình huống scale out và rolling restart trong outage

Giả sử một dịch vụ có bốn replica, cả bốn đã chạy với cấu hình hợp lệ. Config Server bị outage.

| Hành động | Kết quả có thể xảy ra |
|---|---|
| Giữ nguyên bốn replica | Chúng có thể tiếp tục phục vụ bằng snapshot trong bộ nhớ |
| Scale từ bốn lên sáu | Hai replica mới có thể fail startup nếu remote config bắt buộc |
| Restart một replica | Replica đó phải fetch lại; có thể không quay lại Ready |
| Restart cả bốn | Có nguy cơ mất toàn bộ capacity đang hoạt động |
| Gửi busrefresh | Event có thể được nhận nhưng fetch config thất bại |
| Đợi Config Server phục hồi rồi scale | Replica mới có thể khởi động sau khi kiểm tra nguồn đã sẵn sàng |

Trong outage, tránh rolling restart chỉ để “làm mới cho đồng bộ” nếu không có nguồn cấu hình thay thế đã xác nhận. Giữ các replica ổn định có thể là phương án ít rủi ro hơn.

### Quy trình quyết định

1. Xác định số replica đang ready và capacity còn lại.
2. Xác nhận chúng đang dùng revision cấu hình nào.
3. Xác định mức độ an toàn khi tiếp tục dùng revision đó.
4. Tạm dừng deployment, scale down và restart không cần thiết.
5. Khôi phục Config Server hoặc backend Git.
6. Kiểm tra revision và readiness của Config Server.
7. Khởi động hoặc restart một canary.
8. Xác nhận giá trị Environment, binding và luồng nghiệp vụ.
9. Tiếp tục rollout theo batch.

## 13. Xử lý secret và credential khi Config Server mất nguồn

Secret có thể được cung cấp từ Config Server đã giải mã, Vault, cloud secret manager hoặc một hệ thống credential riêng. Không nên gộp mọi trường hợp thành “cấu hình vẫn còn trong memory”.

Với secret tĩnh đã bind vào bean, process có thể tiếp tục giữ giá trị trong bộ nhớ sau khi Config Server mất kết nối. Với dynamic secret có lease, credential có thể hết hạn dù Environment vẫn chứa chuỗi cũ. Database hoặc broker có thể từ chối credential cũ sau thời điểm expiry/revocation.

Cần phân biệt:

- **Config Server outage:** không thể fetch property source mới.
- **Secret provider outage:** không thể lấy secret mới hoặc renew lease.
- **Credential expiry/revocation:** giá trị đang giữ không còn được dependency chấp nhận.
- **Certificate expiry:** TLS handshake có thể thất bại dù ứng dụng vẫn có cấu hình cũ.

Với dynamic secret, theo dõi lease TTL và renewal status riêng. Nếu không thể renew trước thời điểm an toàn, đưa instance vào degraded/not-ready theo policy; không giả định snapshot cũ sẽ hoạt động vô thời hạn.

## 14. Phục hồi sau khi nguồn cấu hình trở lại

Khi Config Server và Git hoạt động trở lại, không nên lập tức phát refresh toàn hệ thống mà chưa xác minh nguồn đã ổn định.

Quy trình phục hồi:

1. Kiểm tra health/readiness của tất cả Config Server replica.
2. Kiểm tra Git backend, credential, TLS và label/commit.
3. Xác nhận các replica phục vụ cùng revision dự kiến.
4. Kiểm tra một request Environment bằng application/profile đại diện.
5. Xác thực cấu hình candidate bằng đúng phiên bản ứng dụng.
6. Refresh hoặc restart một canary.
7. Kiểm tra Environment, config properties, secret access và luồng nghiệp vụ.
8. Mở rộng tới từng batch, theo dõi lỗi và latency.
9. Khôi phục scale/deployment đã tạm dừng.
10. Ghi nhận instance nào vẫn dùng revision cũ hoặc local fallback.

Nếu cấu hình mới có thay đổi schema, không dùng refresh diện rộng trước khi xác nhận tất cả phiên bản ứng dụng còn chạy tương thích. Một nguồn cấu hình đã phục hồi không có nghĩa mọi giá trị mới đều an toàn để áp dụng ngay.

## 15. Kịch bản minh họa: Config Server mất trong 20 phút

Giả sử orders-service đang chạy bốn replica với label <code>release-2026.11.20</code>. Config Server mất kết nối Git và load balancer trong 20 phút.

- Bốn replica hiện tại tiếp tục xử lý request bằng Environment đã nạp.
- Một pod bị crash và được orchestrator tạo lại. Pod mới không fetch được remote config; nếu import bắt buộc, startup fail sau retry.
- Hệ thống còn ba replica. Không nên restart ba replica còn lại chỉ để thử lại.
- Autoscaler muốn tăng lên sáu replica, nhưng hai replica mới cũng không thể Ready.
- Operator kiểm tra revision đang dùng và xác nhận cấu hình cũ còn an toàn trong thời gian outage.
- Config Server phục hồi, tất cả replica phục vụ cùng label/commit.
- Một canary được khởi động và xác minh trước.
- Sau khi canary Ready và smoke test pass, scale out theo batch.
- Cuối cùng mới cho phép rollout cấu hình mới nếu có candidate đã được validate.

Nếu cấu hình cũ không còn an toàn, ví dụ credential đã bị revoke, việc giữ process cũ cũng không bảo đảm phục vụ được. Khi đó, ưu tiên policy an toàn nghiệp vụ: chuyển not-ready, dừng thao tác nhạy cảm hoặc dùng nguồn secret độc lập đã được xác minh.

## 16. Checklist thiết kế khả năng chịu lỗi nguồn cấu hình

- [ ] Đã xác định client dùng Config Data API hay legacy bootstrap.
- [ ] Import bắt buộc hay optional được chọn theo yêu cầu nghiệp vụ.
- [ ] Các thuộc tính bắt buộc có validation trước khi instance nhận traffic.
- [ ] Retry có giới hạn, backoff và timeout phù hợp.
- [ ] Không retry vô hạn khi lỗi credential hoặc path không tồn tại.
- [ ] Hiểu rằng process đang chạy giữ snapshot trong memory; snapshot đó mất khi restart.
- [ ] Không giả định Config Client tự persist last-known-good vào disk.
- [ ] Optional import có local fallback an toàn và chế độ degraded rõ ràng.
- [ ] Có revision/label bất biến và metadata để truy vết cấu hình đang chạy.
- [ ] Refresh failure được theo dõi riêng với Config Server connectivity.
- [ ] Có canary trước khi refresh hoặc rollout diện rộng.
- [ ] Config Server có nhiều replica và backend Git/mirror phù hợp.
- [ ] Kiểm tra revision nhất quán giữa các Config Server replica.
- [ ] Readiness phản ánh khả năng phục vụ nghiệp vụ và tuổi cấu hình.
- [ ] Liveness không gây restart loop chỉ vì một dịch vụ cấu hình bên ngoài bị outage.
- [ ] Dynamic secret lease và credential expiry được theo dõi riêng.
- [ ] Có kế hoạch tạm dừng scale/restart trong outage.
- [ ] Đã diễn tập phục hồi, canary, rolling restart và fallback.

Ứng dụng đang chạy thường có thể tiếp tục dùng cấu hình đã nạp trong Environment khi Config Server mất kết nối, còn instance mới phải lấy cấu hình lại hoặc dùng fallback được thiết kế trước. Vì vậy, khả năng chịu lỗi không chỉ nằm ở số lượng Config Server replica: cần xác định rõ import bắt buộc/tùy chọn, retry, last-known-good, readiness, giới hạn tuổi cấu hình và quy trình phục hồi. Bằng cách giữ instance đang hoạt động ổn định, tránh restart loop và chỉ mở rộng sau khi canary xác minh nguồn đã phục hồi, hệ thống có thể giảm tác động của outage cấu hình mà vẫn giữ được tính an toàn nghiệp vụ.

