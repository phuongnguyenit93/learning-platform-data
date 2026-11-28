# optional:configserver: và hành vi khi máy chủ không truy cập được

Spring Cloud Config Client thường lấy cấu hình từ Config Server trong quá trình khởi động ứng dụng. Nhưng Config Server có thể tạm thời không truy cập được vì mạng, DNS, triển khai, lỗi Git backend hoặc sự cố hạ tầng. Khi đó, ứng dụng có nên tiếp tục khởi động bằng cấu hình cục bộ hay phải dừng để chờ cấu hình tập trung?

Với cơ chế Spring Boot Config Data, tiền tố **optional:** trong thuộc tính **spring.config.import** quyết định cách xử lý khi một nguồn cấu hình không thể được nạp. Khai báo **optional:configserver:** cho phép ứng dụng tiếp tục quá trình nạp cấu hình nếu Config Server không khả dụng. Bỏ tiền tố **optional:** khiến việc lấy cấu hình từ Config Server trở thành yêu cầu bắt buộc; nếu client không kết nối được, quá trình khởi động thất bại.

Lựa chọn này ảnh hưởng trực tiếp đến độ sẵn sàng và tính nhất quán của ứng dụng. Ứng dụng khởi động được bằng cấu hình cục bộ có thể vẫn thiếu endpoint, timeout, chính sách bảo mật hoặc feature flag vốn chỉ được khai báo ở Config Server. Vì vậy, cần quyết định rõ những giá trị nào có thể dùng mặc định và những giá trị nào bắt buộc phải có trước khi nhận traffic.

Sau bài học, bạn có thể:

- Giải thích ý nghĩa của **optional:configserver:** trong Spring Boot Config Data.
- Phân biệt import tùy chọn và import bắt buộc khi Config Server không truy cập được.
- Thiết kế cấu hình cục bộ đủ an toàn cho trường hợp remote configuration không được nạp.
- Hiểu khác biệt giữa Config Data import và cơ chế bootstrap cũ.
- Chọn cách retry, theo dõi health và xử lý sự cố phù hợp với mức độ quan trọng của cấu hình.

## 1. Config Client lấy cấu hình ở thời điểm nào?

Config Client kết nối Config Server trong quá trình khởi động để nạp các property sources từ xa. Với cách cấu hình hiện đại, Spring Boot dùng Config Data import thông qua thuộc tính **spring.config.import**. Cách này được giới thiệu từ Spring Boot 2.4 và hiện là phương thức mặc định để kết nối Spring Cloud Config.

Ví dụ:

~~~yaml
spring:
  application:
    name: order-service
  config:
    import: "optional:configserver:http://config-server:8888"
~~~

Ứng dụng khai báo tên **order-service** và địa chỉ Config Server. Client gửi yêu cầu theo application, profile và label để lấy cấu hình phù hợp. Nếu không chỉ rõ địa chỉ trong import hoặc qua thuộc tính **spring.cloud.config.uri**, địa chỉ mặc định là **http://localhost:8888**.

Khi dùng Config Data import, không cần tạo file **bootstrap.yml** chỉ để khai báo Config Server. Spring Boot nạp cấu hình theo các giai đoạn: trước hết tải cấu hình với profile **default** để xác định các profile có thể được kích hoạt, sau đó tải thêm cấu hình cho những profile đang hoạt động. Vì vậy, log có thể cho thấy nhiều request đến Config Server trong cùng một lần khởi động; đây là hành vi bình thường.

Luồng khởi động có thể hình dung như sau:

~~~mermaid
flowchart TD
    A["Spring Boot bắt đầu khởi động"] --> B["Đọc spring.config.import"]
    B --> C["Config Client gọi Config Server"]
    C --> D{"Server trả cấu hình?"}
    D -->|Có| E["Nạp remote PropertySources"]
    D -->|Không, import optional| F["Bỏ qua nguồn remote bị lỗi"]
    D -->|Không, import bắt buộc| G["Dừng khởi động"]
    E --> H["Hợp nhất cấu hình và tạo bean"]
    F --> H
    H --> I["Ứng dụng tiếp tục khởi động"]
~~~

## 2. optional:configserver: có nghĩa gì?

Tiền tố **optional:** đánh dấu Config Server import là nguồn cấu hình không bắt buộc đối với quá trình nạp Config Data. Client vẫn thử kết nối Config Server. Nếu server khả dụng, ứng dụng nhận cấu hình từ xa như bình thường. Nếu server không thể truy cập, client bỏ qua import không nạp được và tiếp tục với các nguồn cấu hình còn lại.

Ví dụ:

~~~yaml
spring:
  config:
    import: "optional:configserver:http://config-server:8888"
~~~

Nếu Config Server đang hoạt động, Config Client có thể nhận các thuộc tính như:

~~~yaml
order:
  fulfillment:
    endpoint: https://fulfillment.internal
    connect-timeout: 2s
~~~

Nếu Config Server không truy cập được trong lúc khởi động, các thuộc tính chỉ tồn tại ở nguồn remote sẽ không xuất hiện trong Environment của client. Ứng dụng tiếp tục với những giá trị có trong file cục bộ, biến môi trường, tham số dòng lệnh hoặc các property sources khác đã nạp thành công.

Điểm quan trọng là **optional không tự tạo giá trị mặc định**. Nó chỉ cho phép bỏ qua một nguồn cấu hình không nạp được. Nếu ứng dụng cần một thuộc tính nhưng thuộc tính đó chỉ có ở Config Server, ứng dụng vẫn có thể thất bại sau đó khi Spring tạo bean, bind cấu hình hoặc chạy validation.

Ví dụ, nếu một bean yêu cầu endpoint bắt buộc, nhưng local configuration không khai báo thuộc tính đó, Spring có thể báo lỗi unresolved placeholder khi tạo bean. Như vậy, import optional không bảo đảm toàn bộ ứng dụng luôn khởi động thành công; nó chỉ loại bỏ lỗi bắt buộc phát sinh từ chính nguồn import không khả dụng.

## 3. Khi bỏ optional:, ứng dụng sẽ fail fast

Nếu cấu hình tập trung là điều kiện bắt buộc để ứng dụng hoạt động đúng, hãy bỏ tiền tố **optional:**:

~~~yaml
spring:
  application:
    name: payment-service
  config:
    import: "configserver:http://config-server:8888"
~~~

Với khai báo này, Config Client phải nạp được cấu hình từ Config Server. Nếu không thể kết nối hoặc lấy cấu hình theo yêu cầu, quá trình khởi động thất bại. Ứng dụng không chuyển sang trạng thái sẵn sàng với một bộ cấu hình có thể thiếu.

So sánh hai cách:

| Tình huống | Import tùy chọn | Import bắt buộc |
|---|---|---|
| Config Server khả dụng | Nạp cấu hình remote | Nạp cấu hình remote |
| Config Server không truy cập được | Bỏ qua import và tiếp tục nạp nguồn khác | Khởi động thất bại |
| Thuộc tính remote không có local fallback | Có thể lỗi ở bước bind hoặc tạo bean sau đó | Thất bại ngay trong quá trình nạp cấu hình |
| Phù hợp khi | Có local fallback an toàn hoặc remote config không bắt buộc | Thiếu remote config khiến ứng dụng không thể hoạt động đúng |
| Rủi ro chính | Ứng dụng có thể chạy với cấu hình thiếu hoặc mặc định | Ứng dụng không khởi động khi Config Server gặp sự cố |

Không nên chọn optional chỉ để tăng tỷ lệ khởi động. Với dịch vụ thanh toán, xác thực, xử lý dữ liệu hoặc kết nối hạ tầng quan trọng, chạy bằng cấu hình thiếu có thể nguy hiểm hơn việc không khởi động.

## 4. Thiết kế local fallback có chủ đích

Nếu muốn ứng dụng vẫn chạy khi Config Server tạm thời không khả dụng, hãy khai báo các giá trị fallback an toàn trong cấu hình cục bộ. Ví dụ:

~~~yaml
spring:
  application:
    name: catalog-service
  config:
    import: "optional:configserver:http://config-server:8888"

catalog:
  display:
    page-size: 20
    show-recommendations: false
  upstream:
    connect-timeout: 2s
~~~

Các giá trị này cho phép ứng dụng có một hành vi cơ bản khi remote config không nạp được. Khi Config Server hoạt động, cấu hình từ xa có thể cung cấp giá trị theo profile và ứng dụng như đã thiết kế.

Nên phân loại thuộc tính trước khi quyết định fallback:

| Nhóm cấu hình | Có nên có fallback local? | Ví dụ |
|---|---|---|
| Giao diện hoặc tính năng không thiết yếu | Thường có thể | Kích thước trang, banner, feature hiển thị |
| Timeout và retry có giới hạn | Có thể, nếu giá trị mặc định an toàn | Connect timeout 2 giây, tối đa 3 lần retry |
| Endpoint của dịch vụ phụ thuộc | Chỉ khi endpoint fallback được xác định và kiểm soát | URL nội bộ dự phòng |
| Chính sách bảo mật và quyền truy cập | Không dùng giá trị nới lỏng khi thiếu remote config | Bắt buộc xác thực, yêu cầu chữ ký |
| Secret và credentials | Không dùng chuỗi rỗng hoặc secret giả làm fallback | Database password, API token |
| Giới hạn tài chính hoặc dữ liệu quan trọng | Chỉ fallback khi được thiết kế và phê duyệt rõ | Hạn mức giao dịch, chính sách lưu trữ |

Một fallback an toàn phải bảo toàn các invariant quan trọng của ứng dụng. Ví dụ, nếu không tải được cấu hình bảo mật từ xa, ứng dụng không nên tự chuyển sang chế độ bỏ qua xác thực. Nếu không có credential bắt buộc, việc dừng khởi động có thể là hành vi đúng.

Cũng cần chú ý đến thứ tự ưu tiên property sources. Giá trị remote được nạp qua Config Data import có thể ghi đè giá trị trong tài liệu cấu hình khai báo import theo quy tắc của Spring Boot. Khi remote import bị bỏ qua, các giá trị local vẫn là nguồn còn lại. Hãy kiểm thử cả hai trường hợp để chắc chắn fallback chỉ được dùng khi dự kiến.

## 5. Optional không phải là cache hoặc tự động chờ server hồi phục

Một hiểu nhầm thường gặp là cho rằng **optional:configserver:** sẽ lưu bộ cấu hình remote cũ, tự chờ Config Server hoạt động trở lại rồi nạp bù. Tiền tố này không tự cung cấp cơ chế cache last-known-good, không đảm bảo giữ bản remote từ lần chạy trước và không tạo một tiến trình polling nền để tự tải lại cấu hình sau khi ứng dụng đã khởi động.

Khi Config Server không khả dụng tại thời điểm nạp Config Data, client bỏ qua nguồn đó và tiếp tục. Nếu Config Server hồi phục sau đó, ứng dụng không tự động chạy lại toàn bộ quá trình Config Data import chỉ vì server đã hoạt động. Nếu cần nạp lại cấu hình, phải có cơ chế được thiết kế rõ ràng, chẳng hạn refresh được bảo vệ và kiểm thử, hoặc restart/rolling restart ứng dụng.

Vì vậy, hãy phân biệt:

- **Local fallback:** giá trị được khai báo sẵn trong các nguồn cấu hình tại ứng dụng.
- **Cached remote configuration:** bản remote đã lưu lại có chủ đích bằng một cơ chế cache riêng.
- **Runtime refresh:** thao tác yêu cầu ứng dụng đang chạy tải lại cấu hình và cập nhật các bean hỗ trợ.
- **Restart:** chạy lại quy trình khởi động và nạp Config Data từ đầu.

Không nên gọi một file local là cache remote nếu file đó không được đồng bộ và kiểm soát theo revision. Hai nguồn có thể khác nhau theo thời gian và không bảo đảm phản ánh cấu hình remote mới nhất.

## 6. Retry khác với optional

Nếu Config Server đôi khi mất vài giây để sẵn sàng trong lúc triển khai, retry có thể giúp client thử lại trước khi kết luận không thể nạp cấu hình.

Retry và optional giải quyết hai chính sách khác nhau:

- **Retry:** quyết định số lần thử lại và khoảng nghỉ giữa các lần thử khi request thất bại.
- **Optional:** quyết định có cho phép bỏ qua nguồn cấu hình nếu cuối cùng không nạp được hay không.

Với cấu hình bắt buộc, có thể dùng retry để chờ Config Server phục hồi trong một khoảng thời gian giới hạn, sau đó vẫn thất bại nếu hết số lần thử. Đây là lựa chọn phù hợp khi ứng dụng không được phép chạy thiếu remote configuration.

Ví dụ cấu hình retry theo Spring Cloud Config hiện hành:

~~~yaml
spring:
  config:
    import: "configserver:http://config-server:8888"
  cloud:
    config:
      fail-fast: true
      retry:
        enabled: true
        max-attempts: 6
        initial-interval: 1000
        max-interval: 2000
        multiplier: 1.1
~~~

Các giá trị trên minh họa số lần thử, khoảng nghỉ ban đầu, khoảng nghỉ tối đa và hệ số tăng lũy thừa. Trong tài liệu Spring Cloud Config 5.1, retry được bật bằng **spring.cloud.config.retry.enabled=true** và không cần thêm dependency retry riêng. Trước phiên bản 5.1, cơ chế retry yêu cầu Spring Retry trên classpath; một số cấu hình cũ còn yêu cầu spring-boot-starter-aop. Hãy kiểm tra tài liệu đúng phiên bản release train và dependency đang dùng.

Nếu import nằm trong một file profile-specific, ví dụ application-prod.yml, tài liệu hiện hành hướng dẫn đặt các tham số retry dưới dạng query parameters trên chính URL import. Điều này giúp các tham số retry có mặt đủ sớm trong giai đoạn Config Data đang nạp profile đó.

Không nên kỳ vọng retry và optional sẽ tự tạo một chính sách fallback phức tạp. Hãy quyết định rõ: ứng dụng có được phép khởi động khi remote config không lấy được hay phải dừng sau khi retry hết giới hạn.

## 7. Phân biệt Config Data import và bootstrap cũ

Các dự án Spring Cloud Config có thể sử dụng hai cơ chế nạp cấu hình khác nhau.

| Cơ chế | Khai báo | Điều khiển fail fast |
|---|---|---|
| Spring Boot Config Data (hiện đại) | spring.config.import | Bỏ optional: để yêu cầu remote config |
| Legacy bootstrap | bootstrap.yml và spring.cloud.config.uri | spring.cloud.config.fail-fast=true |

Ví dụ legacy bootstrap:

~~~yaml
spring:
  cloud:
    config:
      uri: http://config-server:8888
      fail-fast: true
~~~

Để sử dụng bootstrap cũ, dự án phải bật bootstrap bằng thuộc tính hệ thống/môi trường hoặc dependency **spring-cloud-starter-bootstrap**, tùy cấu hình phiên bản. Chỉ tạo file bootstrap.yml mà không bật cơ chế bootstrap tương ứng không có nghĩa ứng dụng sẽ tự dùng nó.

Với Config Data import, cách tương đương fail-fast là bỏ tiền tố optional. Không nên trộn hai cơ chế một cách tùy tiện trong cùng ứng dụng vì chúng có thời điểm nạp, nguồn thuộc tính và cách điều khiển lỗi khác nhau.

## 8. Quan sát tình trạng Config Server

Khi dùng optional, ứng dụng có thể khởi động thành công dù Config Server không truy cập được. Vì vậy, trạng thái process đang chạy không đủ để kết luận cấu hình tập trung đã được nạp.

Spring Cloud Config Client cung cấp Config Health Indicator để thử tải cấu hình từ Config Server. Health indicator này có thể được tắt bằng:

~~~yaml
management:
  health:
    config:
      enabled: false
~~~

Không nên tắt indicator chỉ để làm cho health endpoint luôn xanh. Hãy chọn readiness và liveness probe phù hợp với chính sách vận hành:

- **Liveness:** kiểm tra tiến trình có còn hoạt động bình thường hay không; không nên restart liên tục chỉ vì Config Server tạm thời không sẵn sàng.
- **Readiness:** xác định ứng dụng có đủ điều kiện nhận traffic hay không. Nếu ứng dụng đã khởi động bằng fallback nhưng chưa có cấu hình bắt buộc, readiness có thể cần ở trạng thái chưa sẵn sàng.
- **Config health:** cung cấp tín hiệu về khả năng kết nối và lấy cấu hình từ xa; cần hiểu rằng kết quả được cache để giảm request.

Theo tài liệu hiện hành, Config Health Indicator cache kết quả để tăng hiệu năng, TTL mặc định là 5 phút và có thể thay đổi bằng thuộc tính **health.config.time-to-live** tính bằng mili giây. Vì có cache, trạng thái health có thể không phản ánh tức thời sự cố vừa xảy ra hoặc vừa được khắc phục.

Nên ghi nhận rõ ứng dụng đã nạp cấu hình remote thành công hay đang chạy bằng fallback. Có thể ghi một trạng thái hoặc metric không nhạy cảm như nguồn cấu hình, revision/label và thời điểm nạp. Không log toàn bộ Environment hoặc secret để chứng minh cấu hình đã được tải.

## 9. Nhiều Config Server URL và tính sẵn sàng cao

Nếu có nhiều instance Config Server, Config Client có thể được cấu hình nhiều URL hoặc dùng service discovery tùy cơ chế kết nối. Điều này giúp client thử một server khác khi instance đầu tiên không sẵn sàng.

Ví dụ dùng nhiều URL trong thuộc tính uri:

~~~yaml
spring:
  cloud:
    config:
      uri: http://config-server-a:8888,http://config-server-b:8888
~~~

Theo mặc định hiện hành, client thử các URL theo thứ tự cho đến khi một request thành công. Có thể cấu hình **spring.cloud.config.multiple-uri-strategy** thành **connection-timeout-only** nếu chỉ muốn chuyển sang URL tiếp theo khi server không chạy hoặc kết nối timeout. Hành vi này áp dụng cho danh sách URI khai báo qua thuộc tính **spring.cloud.config.uri**.

Nếu khai báo nhiều location trong cùng **spring.config.import**, các import được xử lý theo thứ tự khai báo và import sau có độ ưu tiên cao hơn. Cần đọc tài liệu đúng phiên bản về cách xử lý lỗi và fail-fast cho nhiều import; không giả định cơ chế multiple-uri-strategy của thuộc tính uri cũng áp dụng cho nhiều location trong import.

Nhiều URL giúp giảm phụ thuộc vào một instance Config Server, nhưng không khắc phục được lỗi chung của Git backend, Redis backend, DNS, credential hoặc mạng nếu tất cả server cùng phụ thuộc vào một thành phần đang hỏng. Cần kiểm tra tính độc lập thực tế của các điểm dự phòng.

## 10. Chọn chính sách cho từng loại dịch vụ

Có thể dùng các câu hỏi sau để chọn optional hay mandatory:

1. Ứng dụng có đủ cấu hình local để thực hiện hành vi tối thiểu và an toàn không?
2. Thuộc tính remote nào là bắt buộc để tạo bean hoặc mở kết nối?
3. Nếu fallback được dùng, ứng dụng có thể xử lý dữ liệu sai, mất an toàn hoặc gửi request đến endpoint không mong muốn không?
4. Có thể để ứng dụng chờ Config Server phục hồi trong thời gian giới hạn bằng retry không?
5. Readiness probe có phân biệt được trạng thái chạy bằng remote config và local fallback không?
6. Đội vận hành có thể phát hiện, thông báo và khôi phục cấu hình sau sự cố không?

Ví dụ lựa chọn:

| Dịch vụ | Chính sách gợi ý | Lý do |
|---|---|---|
| Catalog hoặc nội dung hiển thị | Có thể dùng optional | Có thể định nghĩa bộ giá trị mặc định an toàn |
| Dịch vụ xử lý thanh toán | Thường dùng mandatory | Không nên chạy với thiếu hạn mức hoặc chính sách xác thực |
| Dịch vụ đọc dữ liệu công khai | Tùy thuộc endpoint và giới hạn | Có thể có fallback nếu không làm thay đổi quyền truy cập |
| Dịch vụ định tuyến hoặc phân quyền | Mandatory hoặc fallback đã được kiểm soát chặt | Cấu hình sai có thể ảnh hưởng diện rộng |
| Worker xử lý batch | Tùy tác động của job | Cần cân nhắc việc chạy với cấu hình cũ hoặc thiếu |

Không có một lựa chọn duy nhất phù hợp mọi dịch vụ. Chính sách cần xuất phát từ tác động khi thiếu cấu hình, khả năng phục hồi và mức độ rủi ro nghiệp vụ.

## 11. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Ứng dụng vẫn khởi động dù Config Server ngừng | Import được đánh dấu optional | Kiểm tra remote config có bắt buộc không; bỏ optional nếu cần fail fast |
| Ứng dụng khởi động xong rồi lỗi tạo bean | Thuộc tính remote bắt buộc không có local fallback | Khai báo fallback an toàn hoặc dùng import bắt buộc |
| Ứng dụng khởi động bằng giá trị mặc định không mong muốn | Local fallback khác remote config | Kiểm thử hai trạng thái server up/down và log trạng thái nguồn |
| Server hồi phục nhưng ứng dụng vẫn dùng giá trị cũ/local | Optional không tự polling hoặc nạp lại sau startup | Thực hiện refresh có kiểm soát hoặc restart/rollout |
| Ứng dụng dừng ngay khi server vừa khởi động chậm | Import bắt buộc nhưng chưa có retry | Cấu hình retry với giới hạn phù hợp |
| Health vẫn báo trạng thái cũ | Config Health Indicator có cache | Kiểm tra TTL và thời điểm cập nhật kết quả |
| Dịch vụ nhận traffic dù remote config thiếu | Readiness chỉ kiểm tra process, không kiểm tra điều kiện cấu hình | Bổ sung readiness dựa trên trạng thái cấu hình cần thiết |
| Dùng fail-fast sai cách với Config Data | Nhầm thuộc tính legacy bootstrap với optional prefix | Dùng bỏ optional cho Config Data import hoặc fail-fast cho bootstrap cũ |

## 12. Tự kiểm tra

1. **optional:configserver:** khác gì so với **configserver:** khi Config Server không truy cập được?
2. Vì sao optional không bảo đảm ứng dụng chắc chắn khởi động thành công?
3. Nếu ứng dụng chỉ có endpoint và credentials trong Config Server, điều gì có thể xảy ra khi import optional bị bỏ qua?
4. Retry và optional giải quyết hai vấn đề khác nhau như thế nào?
5. Cơ chế nào tương đương fail-fast khi ứng dụng dùng Spring Boot Config Data import?
6. Vì sao không nên coi optional là cơ chế cache cấu hình remote?
7. Readiness và liveness nên phản ánh trạng thái Config Server như thế nào?
8. Vì sao nhiều URL Config Server không bảo đảm hệ thống hoạt động nếu tất cả server cùng phụ thuộc một Git backend đang lỗi?

Hãy thử chạy cùng một Config Client với hai cấu hình: một lần dùng **optional:configserver:** và một lần dùng **configserver:**. Tắt Config Server trước khi khởi động client, quan sát log và kết quả khởi động. Bổ sung một thuộc tính chỉ có ở remote và kiểm tra hành vi bind khi import optional bị bỏ qua. Sau đó thêm local fallback, bật lại Config Server và xác minh cấu hình remote được nạp. Cuối cùng, thử retry với một thời gian chờ có giới hạn và kiểm tra health/readiness để phân biệt ứng dụng chạy bằng fallback với ứng dụng đã lấy được cấu hình tập trung.

## Tài liệu tham khảo

- [Spring Cloud Config Client — Config Data Import, Fail Fast and Retry](https://docs.spring.io/spring-cloud-config/reference/client.html)
- [Spring Boot — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html)
- [Spring Cloud Config — Multiple Config Server URLs and Health Indicator](https://docs.spring.io/spring-cloud-config/reference/client.html)

