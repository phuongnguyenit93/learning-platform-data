# Chia cấu hình dùng chung với cấu hình riêng từng dịch vụ

Một nền tảng có nhiều ứng dụng Spring Boot thường có hai nhóm cấu hình. Nhóm thứ nhất là các giá trị có ý nghĩa chung, chẳng hạn quy ước log, định dạng thời gian, một số timeout mặc định hoặc thông tin quan sát. Nhóm thứ hai là giá trị phụ thuộc vào từng dịch vụ, chẳng hạn cổng lắng nghe, tên queue, URL API, datasource, giới hạn xử lý hoặc chính sách retry của riêng dịch vụ đó.

Nếu mọi thứ được sao chép vào từng tệp cấu hình, các giá trị chung dễ bị lệch và việc cập nhật trở nên tốn công. Nếu dồn mọi thứ vào một tệp dùng chung, thay đổi của một dịch vụ có thể vô tình ảnh hưởng tới các dịch vụ khác. Thiết kế repository cho Spring Cloud Config cần cân bằng giữa tái sử dụng và ranh giới sở hữu: đặt giá trị ở phạm vi rộng nhất mà nó thực sự đúng, sau đó bổ sung cấu hình riêng tại nơi có trách nhiệm rõ ràng.

Bài học này trình bày cách chia cấu hình dùng chung với cấu hình riêng từng dịch vụ, cách chọn cấu trúc Git repository, cách phối hợp application/profile/label, cách kiểm tra giá trị cuối cùng và cách quản trị thay đổi để giảm rủi ro lan truyền.

Sau bài học, bạn có thể:

- Nhận diện thuộc tính nào nên dùng chung và thuộc tính nào phải thuộc về một dịch vụ.
- Thiết kế cấu trúc tệp và thư mục cho kho cấu hình Spring Cloud Config.
- Dùng cấu hình mặc định và cấu hình ghi đè theo ứng dụng hoặc profile.
- Chọn giữa repository chung, thư mục riêng và repository tách biệt.
- Kiểm soát trùng khóa, phạm vi ảnh hưởng và quyền sở hữu cấu hình.
- Kiểm tra property source thực tế và phát hành thay đổi có thể truy vết.

## 1. Nguyên tắc phân chia: dùng chung khi ngữ nghĩa thực sự giống nhau

Không nên quyết định phạm vi cấu hình chỉ dựa trên việc hai dịch vụ đang có cùng một giá trị. Hai thuộc tính có giá trị giống nhau hôm nay có thể có ý nghĩa vận hành khác nhau và sẽ thay đổi theo hai hướng khác nhau trong tương lai.

Ví dụ, <code>orders-service</code> và <code>inventory-service</code> hiện cùng có timeout HTTP là <code>2s</code>. Nếu cả hai dùng cùng thư viện HTTP client, cùng đặc tính tải và cùng yêu cầu độ trễ, giá trị mặc định có thể đặt ở phạm vi chung. Nhưng nếu một dịch vụ gọi hệ thống nội bộ nhanh, còn dịch vụ kia gọi nhà cung cấp bên ngoài có độ trễ cao, timeout nên thuộc cấu hình riêng dù hiện tại chúng tình cờ bằng nhau.

Một thuộc tính phù hợp để dùng chung khi:

- Nó có cùng ý nghĩa đối với các dịch vụ sử dụng.
- Các dịch vụ có cùng yêu cầu bảo mật và vận hành đối với thuộc tính đó.
- Việc thay đổi giá trị nên được review và phát hành cùng nhau.
- Có một nhóm hoặc chủ sở hữu chịu trách nhiệm về mặc định chung.
- Dịch vụ có thể ghi đè có chủ đích nếu có nhu cầu khác biệt.

Một thuộc tính nên đặt riêng theo dịch vụ khi nó mô tả tài nguyên, hành vi hoặc ranh giới của dịch vụ đó. Ví dụ:

- <code>spring.application.name</code>, cổng HTTP hoặc tên ứng dụng.
- URL của dịch vụ phụ thuộc, tên topic, queue hoặc consumer group.
- Datasource, schema, pool size và giới hạn kết nối riêng.
- Thời gian timeout, retry hoặc circuit breaker gắn với một luồng gọi cụ thể.
- Cờ tính năng, hạn mức nghiệp vụ hoặc chính sách xử lý dữ liệu của dịch vụ.
- Thông tin định danh và quyền truy cập chỉ dành cho một ứng dụng.

Quy tắc thực tế là: **đặt mặc định ở phạm vi chung khi các dịch vụ cùng chịu một chính sách; đặt khác biệt ở phạm vi dịch vụ khi quyết định đó thuộc trách nhiệm của dịch vụ.** Không đưa bí mật dạng rõ vào Git chỉ vì muốn tái sử dụng một giá trị cho nhiều ứng dụng.

## 2. Cấu trúc phẳng: cách đơn giản để bắt đầu

Spring Cloud Config Git backend hỗ trợ quy ước đặt tên tệp dựa trên application và profile. Với repository nhỏ hoặc số lượng dịch vụ vừa phải, cấu trúc phẳng thường dễ hiểu và dễ kiểm tra:

~~~text
config-repo/
├── application.yml
├── application-dev.yml
├── application-prod.yml
├── orders-service.yml
├── orders-service-dev.yml
├── orders-service-prod.yml
├── inventory-service.yml
├── inventory-service-dev.yml
├── inventory-service-prod.yml
├── payment-service.yml
└── payment-service-prod.yml
~~~

Ý nghĩa các tệp:

| Tệp | Phạm vi |
|---|---|
| <code>application.yml</code> | Giá trị mặc định dùng chung cho các ứng dụng |
| <code>application-dev.yml</code> | Giá trị chung khi profile <code>dev</code> được kích hoạt |
| <code>application-prod.yml</code> | Giá trị chung khi profile <code>prod</code> được kích hoạt |
| <code>orders-service.yml</code> | Giá trị riêng của <code>orders-service</code>, dùng ở các profile |
| <code>orders-service-prod.yml</code> | Giá trị riêng của <code>orders-service</code> khi chạy profile <code>prod</code> |
| <code>inventory-service.yml</code> | Giá trị riêng của <code>inventory-service</code>, dùng ở các profile |
| <code>payment-service-prod.yml</code> | Giá trị riêng của <code>payment-service</code> ở profile <code>prod</code> |

Tên ứng dụng do client gửi, thường lấy từ <code>spring.application.name</code>, phải khớp với quy ước tên tệp. Profile quyết định biến thể cấu hình cần nạp. Label quyết định phiên bản Git mà server đọc. Ba khái niệm này có vai trò riêng: tên ứng dụng chọn dịch vụ, profile chọn môi trường hoặc nhóm hành vi theo quy ước, label chọn phiên bản của repository.

Ví dụ, khi <code>orders-service</code> gửi yêu cầu với profile <code>prod</code>, Config Server có thể tổng hợp các nguồn cấu hình chung và riêng tương ứng từ label được chọn. Một ứng dụng khác như <code>inventory-service</code> nhận tệp riêng của nó, trong khi vẫn dùng các mặc định chung.

### Ví dụ về giá trị chung

Giả sử mọi dịch vụ cùng dùng một chuẩn log và một timeout mặc định cho các thao tác HTTP thông thường:

~~~yaml
# application.yml
logging:
  level:
    root: INFO

platform:
  observability:
    tracing-enabled: true

http-client:
  connect-timeout: 2s
  read-timeout: 5s
~~~

Các giá trị này chỉ nên đặt ở đây nếu chúng thực sự là chuẩn chung. Không nên đưa URL của một API cụ thể hoặc tên queue của một dịch vụ vào <code>application.yml</code>, vì các ứng dụng khác có thể nhận thuộc tính mà chúng không sử dụng hoặc hiểu theo nghĩa khác.

### Ví dụ về cấu hình riêng dịch vụ

<code>orders-service.yml</code> có thể mô tả các phụ thuộc và giới hạn riêng của dịch vụ đơn hàng:

~~~yaml
# orders-service.yml
server:
  port: 8081

orders:
  reservation:
    endpoint: http://inventory-service
    timeout: 1500ms
  events:
    topic: orders.events
~~~

<code>inventory-service.yml</code> mô tả tài nguyên riêng của dịch vụ kho:

~~~yaml
# inventory-service.yml
server:
  port: 8082

inventory:
  events:
    topic: inventory.events
  allocation:
    max-items-per-request: 100
~~~

<code>payment-service.yml</code> có thể khai báo nhóm thuộc tính thanh toán:

~~~yaml
# payment-service.yml
server:
  port: 8083

payment:
  provider:
    connect-timeout: 3s
    read-timeout: 10s
~~~

Mặc dù các tệp nằm trong cùng repository, mỗi tệp ứng dụng có một phạm vi sở hữu rõ ràng. Nhóm phụ trách dịch vụ có thể review các giá trị riêng; nhóm nền tảng review thay đổi ở <code>application.yml</code> vì chúng có thể tác động nhiều dịch vụ.

## 3. Cấu hình theo profile: chỉ ghi đè phần khác biệt

Một môi trường thường cần một số giá trị khác nhau, nhưng không phải mọi thuộc tính đều phải lặp lại trong từng tệp. Hãy giữ giá trị chung trong tệp nền và chỉ ghi đè thuộc tính thực sự thay đổi.

Ví dụ, <code>application.yml</code> có timeout mặc định:

~~~yaml
# application.yml
http-client:
  connect-timeout: 2s
  read-timeout: 5s
~~~

Ở môi trường production, nhóm có thể tăng read timeout dùng chung cho các dịch vụ phù hợp:

~~~yaml
# application-prod.yml
http-client:
  read-timeout: 7s
~~~

Một dịch vụ có yêu cầu riêng có thể ghi đè thêm:

~~~yaml
# payment-service-prod.yml
payment:
  provider:
    read-timeout: 12s
~~~

Ví dụ trên minh họa hai phạm vi khác nhau. <code>application-prod.yml</code> điều chỉnh mặc định dùng chung theo profile; <code>payment-service-prod.yml</code> chỉ điều chỉnh thuộc tính của thanh toán. Không cần sao chép toàn bộ <code>http-client</code> hoặc mọi thuộc tính khác vào tệp riêng nếu chúng không thay đổi.

Cấu trúc này giúp người đọc thấy rõ khác biệt giữa các môi trường. Khi một giá trị không xuất hiện trong tệp cụ thể, nó vẫn có thể được kế thừa từ nguồn chung. Khi một dịch vụ cần giá trị khác, nhóm ghi đè tại tệp ứng dụng/profile phù hợp.

Cần lưu ý rằng <code>dev</code>, <code>test</code>, <code>staging</code> và <code>prod</code> là quy ước của tổ chức. Profile Spring là cơ chế chọn cấu hình và bean; nó không tự bảo đảm ứng dụng đang chạy ở hạ tầng tương ứng. Pipeline triển khai cần đặt profile đúng với môi trường và xác nhận client gửi đúng profile lên Config Server.

## 4. Một ví dụ tổng hợp về các lớp cấu hình

Giả sử ba dịch vụ dùng chung chuẩn quan sát và timeout mặc định, nhưng có URL, cổng và giới hạn nghiệp vụ riêng. Một repository phẳng có thể chứa:

~~~text
config-repo/
├── application.yml
├── application-prod.yml
├── orders-service.yml
├── orders-service-prod.yml
├── inventory-service.yml
├── inventory-service-prod.yml
├── payment-service.yml
└── payment-service-prod.yml
~~~

<code>application.yml</code> chứa quy ước dùng chung:

~~~yaml
logging:
  level:
    root: INFO

management:
  endpoint:
    health:
      show-details: never

http-client:
  connect-timeout: 2s
  read-timeout: 5s
~~~

<code>application-prod.yml</code> chỉ điều chỉnh chính sách chung cho production:

~~~yaml
logging:
  level:
    root: WARN

http-client:
  connect-timeout: 1s
~~~

<code>orders-service.yml</code> chứa cấu hình riêng của đơn hàng:

~~~yaml
server:
  port: 8081

orders:
  inventory:
    base-url: http://inventory-service
  events:
    topic: orders.events
~~~

<code>orders-service-prod.yml</code> thay đổi endpoint và giới hạn theo production:

~~~yaml
orders:
  inventory:
    base-url: https://inventory.internal
  reservation:
    max-retries: 2
~~~

<code>inventory-service.yml</code> có thể chứa:

~~~yaml
server:
  port: 8082

inventory:
  allocation:
    max-items-per-request: 100
  events:
    topic: inventory.events
~~~

Với request <code>orders-service/prod/&lt;label&gt;</code>, Config Server tìm cấu hình chung và cấu hình riêng phù hợp. Ứng dụng có thể nhận mức log <code>WARN</code> từ cấu hình chung production, cổng và topic từ cấu hình riêng của orders, cùng URL inventory production từ tệp riêng theo profile.

Không nên dựa vào suy đoán để biết chính xác nguồn nào thắng khi cùng khóa xuất hiện ở nhiều property source. Hãy xem phản hồi Environment của Config Server, danh sách <code>propertySources</code> và thứ tự ưu tiên trong Spring Environment của client. Việc kiểm tra trực tiếp đặc biệt cần thiết khi một thuộc tính bị khai báo ở cả <code>application.yml</code>, tệp theo profile và tệp theo dịch vụ.

## 5. Chọn cách tổ chức repository

Không có một cấu trúc duy nhất phù hợp cho mọi tổ chức. Có ba cách phổ biến, có thể kết hợp tùy quy mô và quyền sở hữu.

### Một repository chung, tệp đặt phẳng

Ví dụ:

~~~text
config-repo/
├── application.yml
├── application-prod.yml
├── orders-service.yml
├── inventory-service.yml
└── payment-service.yml
~~~

Phù hợp khi số lượng dịch vụ chưa quá lớn, nhóm nền tảng quản trị cấu hình tập trung và quy trình review chung đã rõ.

Ưu điểm:

- Dễ nhìn thấy toàn bộ cấu hình và quan hệ dùng chung.
- Dễ tìm kiếm khóa bị khai báo lặp.
- Một commit có thể cập nhật các giá trị liên quan trong cùng đợt phát hành.
- Config Server chỉ cần kết nối tới một repository.

Điểm cần quản trị:

- Nhiều nhóm cùng sửa một repository có thể gây xung đột review.
- Quyền truy cập Git thường ở mức repository; khó tách quyền đọc theo từng dịch vụ nếu không có cơ chế bổ sung.
- Thay đổi ở tệp dùng chung có phạm vi ảnh hưởng rộng.
- Repository lớn dần có thể làm review và kiểm tra khó hơn.

### Một repository, chia thư mục theo phạm vi

Khi số lượng dịch vụ tăng, có thể dùng search path để tổ chức cấu hình theo thư mục:

~~~text
config-repo/
├── shared/
│   ├── application.yml
│   └── application-prod.yml
├── orders-service/
│   ├── orders-service.yml
│   └── orders-service-prod.yml
├── inventory-service/
│   ├── inventory-service.yml
│   └── inventory-service-prod.yml
└── payment-service/
    ├── payment-service.yml
    └── payment-service-prod.yml
~~~

Config Server Git backend hỗ trợ cấu hình <code>search-paths</code>. Ví dụ:

~~~yaml
spring:
  cloud:
    config:
      server:
        git:
          uri: https://git.example.com/platform/config-repo.git
          default-label: main
          search-paths:
            - shared
            - '{application}'
~~~

Trong ví dụ này, server tìm cấu hình trong thư mục chung và thư mục có tên tương ứng với application được yêu cầu. Placeholder <code>{application}</code> được thay bằng tên ứng dụng trong request. Có thể dùng thêm placeholder phù hợp với nhu cầu tổ chức, nhưng phải kiểm tra cách các search path được áp dụng trong phiên bản Spring Cloud Config của dự án.

Cách chia thư mục làm repository dễ điều hướng hơn, đồng thời giúp nhóm phụ trách dịch vụ tìm được vùng cấu hình của mình. Tuy vậy, thư mục không tự tạo ranh giới bảo mật. Nếu mọi người đều có quyền đọc cả repository, họ vẫn có thể đọc các tệp của dịch vụ khác. Search path cũng không thay thế quy tắc phân quyền.

Khi dùng nhiều search path, cần kiểm tra thứ tự và property source mà server trả về. Nếu cùng một khóa được khai báo trong <code>shared</code> và thư mục dịch vụ, kết quả phải được xác nhận bằng phản hồi thực tế, không nên phụ thuộc vào giả định về thứ tự thư mục.

### Repository tách riêng theo dịch vụ hoặc miền nghiệp vụ

Ví dụ:

~~~text
platform-config/
orders-config/
inventory-config/
payment-config/
~~~

Cách này phù hợp khi các nhóm dịch vụ có vòng đời phát hành, quyền truy cập, mức độ nhạy cảm hoặc quy trình phê duyệt khác nhau đáng kể.

Ưu điểm:

- Có thể phân quyền đọc/ghi theo repository.
- Nhóm dịch vụ tự quản lý lịch sử và review cấu hình riêng.
- Một repository của dịch vụ thay đổi không tạo commit chung với các dịch vụ khác.
- Có thể tách vòng đời release và quy trình bảo vệ nhánh.

Chi phí cần tính tới:

- Config Server phải quản lý nhiều URI và credential.
- Các thay đổi dùng chung có thể cần cập nhật ở nhiều repository.
- Cần quy ước version/label nhất quán giữa các nguồn.
- Khi ghép nhiều repository, phải kiểm tra thứ tự ưu tiên và hành vi khi một backend lỗi.
- Vận hành, audit và đồng bộ credential phức tạp hơn.

Nếu chọn nhiều repository, có thể dùng cấu hình nhiều Git repository theo pattern application hoặc cơ chế composite repository. Cần xác định rõ repository nào phục vụ ứng dụng nào, cách phân giải khi nhiều nguồn cùng cung cấp một khóa và việc một nguồn không sẵn sàng có làm request thất bại hay không.

## 6. Chia quyền sở hữu và tránh cấu hình dùng chung quá rộng

Repository chỉ là nơi lưu trữ. Để cấu hình dễ vận hành, nhóm cần xác định ai sở hữu từng phạm vi và ai có quyền thay đổi.

Một mô hình trách nhiệm tham khảo:

| Phạm vi | Chủ sở hữu thường gặp | Ví dụ thay đổi |
|---|---|---|
| Mặc định nền tảng | Nhóm platform | Chuẩn log, tracing, timeout mặc định |
| Cấu hình theo môi trường | Nhóm platform/operations | Giá trị mặc định cho staging hoặc production |
| Cấu hình riêng dịch vụ | Nhóm sở hữu dịch vụ | URL phụ thuộc, queue, pool size, giới hạn nghiệp vụ |
| Bí mật | Chủ sở hữu dịch vụ và nhóm bảo mật/vận hành | Cấp quyền, xoay vòng secret, cập nhật tham chiếu |

Một số nguyên tắc giúp ranh giới rõ hơn:

- Chỉ đưa vào <code>application.yml</code> những thuộc tính có cùng ngữ nghĩa và chính sách với các ứng dụng sử dụng.
- Dùng namespace theo dịch vụ, ví dụ <code>orders.*</code>, <code>inventory.*</code>, <code>payment.*</code>, để tránh các khóa chung chung như <code>timeout</code> hoặc <code>url</code>.
- Không để cấu hình riêng của một dịch vụ trở thành mặc định toàn cục chỉ vì dịch vụ đó được tạo trước.
- Tránh sao chép cùng một giá trị vào nhiều tệp nếu nó thực sự có một chủ sở hữu và một nguồn chân lý.
- Với giá trị có thể khác theo dịch vụ, hãy đặt mặc định chung có giới hạn rồi cho phép dịch vụ khai báo rõ ngoại lệ.
- Ghi lại lý do khi một dịch vụ ghi đè chính sách chung để reviewer hiểu đó là quyết định có chủ đích.

Một dấu hiệu cấu hình dùng chung quá rộng là khi <code>application.yml</code> có nhiều khóa chỉ một dịch vụ sử dụng. Một dấu hiệu phân chia quá vụn là khi các repository khác nhau chứa các bản sao giống hệt nhau của nhiều thuộc tính, và một thay đổi đơn giản phải cập nhật nhiều nơi. Cần điều chỉnh ranh giới khi chi phí đồng bộ hoặc phạm vi ảnh hưởng bắt đầu tăng.

## 7. Quản lý bí mật trong cấu trúc repository

Mật khẩu database, API token, private key, signing key và thông tin xác thực Git không nên xuất hiện dưới dạng rõ trong repository, dù ở tệp chung hay tệp riêng dịch vụ.

Một số cách tổ chức:

- Đặt tham chiếu tới secret trong cấu hình, còn giá trị thật được lấy từ secret manager hoặc nền tảng triển khai.
- Cấp biến môi trường hoặc secret mount cho đúng dịch vụ cần sử dụng.
- Nếu dùng cơ chế mã hóa của Spring Cloud Config, lưu ciphertext trong Git và quản lý khóa giải mã ở nơi riêng biệt, có kiểm soát quyền.

Không đặt secret chung vào <code>application.yml</code> chỉ vì nhiều dịch vụ cùng cần một loại thông tin. Mỗi dịch vụ nên có danh tính và quyền tối thiểu phù hợp. Hai dịch vụ cùng kết nối một hệ thống không có nghĩa chúng phải dùng chung một tài khoản hoặc cùng có quyền như nhau.

Khi bí mật đã bị commit, xóa khỏi phiên bản mới không loại bỏ nó khỏi lịch sử. Cần thu hồi hoặc xoay vòng giá trị, kiểm tra log và bản sao repository, rồi xử lý lịch sử theo quy trình của tổ chức. Quyền đọc Git repository và quyền đọc secret cũng nên được xem là hai quyền riêng.

## 8. Tránh trùng khóa và xác định giá trị hiệu lực

Một khóa được khai báo ở nhiều nơi có thể là chủ đích ghi đè, nhưng cũng có thể là dấu hiệu thiết kế chưa rõ. Trước khi thêm một thuộc tính, hãy tìm xem khóa đó đã tồn tại ở phạm vi chung, profile hoặc dịch vụ hay chưa.

Ví dụ khóa <code>http-client.read-timeout</code> xuất hiện ở:

- <code>application.yml</code>: mặc định <code>5s</code>.
- <code>application-prod.yml</code>: mặc định production <code>7s</code>.
- <code>payment-service-prod.yml</code>: riêng payment <code>12s</code>.

Đây là một chuỗi ghi đè có thể giải thích được nếu payment thực sự cần thời gian chờ dài hơn. Ngược lại, nếu cùng một khóa <code>database.url</code> xuất hiện trong <code>application.yml</code> và nhiều tệp dịch vụ với ý nghĩa khác nhau, cấu trúc namespace đang quá rộng và dễ gây nhầm.

Để kiểm tra kết quả:

1. Gọi endpoint Config Server bằng đúng application, profile và label.
2. Đọc danh sách <code>propertySources</code> trong phản hồi và xác định nguồn cung cấp khóa.
3. Kiểm tra giá trị hiệu lực ở Spring Environment phía client nếu còn nguồn cục bộ có thể ghi đè.
4. Kiểm tra giá trị đã bind vào bean, đặc biệt khi dùng <code>@ConfigurationProperties</code>.
5. Ghi nhận khóa nào được phép ghi đè và lý do của ngoại lệ.

Ví dụ endpoint:

~~~http
GET http://config.internal:8888/orders-service/prod/release-2026.11
~~~

Không nên dựa vào tên tệp để kết luận chắc chắn giá trị cuối cùng. Cấu hình server có thể có nhiều search path hoặc repository; client cũng có thể có biến môi trường và tham số chạy. Phản hồi và Environment thực tế mới là bằng chứng về nguồn và giá trị đã được nạp.

## 9. Kiểm tra repository trước khi phát hành

Một repository cấu hình cần được kiểm tra trước khi hợp nhất thay đổi, đặc biệt với tệp dùng chung. Quy trình có thể bao gồm:

1. **Kiểm tra cú pháp:** parse toàn bộ YAML/Properties để phát hiện lỗi định dạng.
2. **Kiểm tra tên tệp:** xác nhận application và profile khớp với quy ước đã công bố.
3. **Kiểm tra khóa:** tìm khóa trùng, khóa không còn dùng, namespace sai hoặc thuộc tính bị khai báo nhầm phạm vi.
4. **Kiểm tra bắt buộc:** bảo đảm các dịch vụ có đủ URL, timeout, pool size và giá trị thiết yếu.
5. **Kiểm tra bí mật:** quét token, mật khẩu, private key và các chuỗi có dấu hiệu nhạy cảm; không coi kết quả quét tự động là thay thế cho review.
6. **Kiểm tra phản hồi Config Server:** chạy thử các tổ hợp application/profile/label đại diện để xem đúng property source được trả về.
7. **Kiểm tra ứng dụng:** chạy kiểm thử khởi động hoặc integration test để xác nhận bind và validation.
8. **Review theo phạm vi:** thay đổi <code>application.yml</code> cần reviewer hiểu tác động nhiều dịch vụ; thay đổi tệp riêng cần người sở hữu dịch vụ review.

Một kiểm tra đơn giản cho repository không chỉ hỏi “YAML có hợp lệ không?” mà còn hỏi “dịch vụ nào nhận được giá trị này?” và “thay đổi này có thể tác động tới ai?”. Đó là lý do cần test cả nội dung lẫn phạm vi phân phối.

## 10. Quản lý label và phát hành cấu hình

Cấu hình được version hóa cùng Git. Cần thống nhất cách dùng branch, tag và commit cho các môi trường.

Một quy ước ví dụ:

| Mục đích | Label gợi ý | Cách cập nhật |
|---|---|---|
| Phát triển tích cực | <code>main</code> hoặc nhánh phát triển | Nhận thay đổi thường xuyên |
| Kiểm thử tích hợp | Nhánh hoặc tag kiểm thử | Chốt theo đợt kiểm thử |
| Staging | Tag ứng viên phát hành | Chỉ thay đổi khi có bản ứng viên mới |
| Production | Tag phát hành hoặc commit bất biến | Chỉ cập nhật sau phê duyệt |

Không nên giả định label là môi trường. Profile chọn biến thể cấu hình; label chọn phiên bản Git. Có thể dùng <code>prod</code> cùng một tag phát hành, hoặc dùng profile khác nhau cùng một label nếu nhiều môi trường cần đọc chung một phiên bản repository.

Với production, ghim vào tag hoặc commit đã được duyệt giúp tái lập cấu hình. Nếu client chỉ dùng nhánh <code>main</code>, cùng một phiên bản ứng dụng có thể nhận nội dung khác nhau ở hai thời điểm khác nhau. Khi cần rollback, có thể quay lại tag/commit đã xác nhận và refresh hoặc triển khai lại dịch vụ theo quy trình.

## 11. Quy trình thay đổi cấu hình dùng chung và riêng

Một thay đổi cấu hình nên có phạm vi, người chịu trách nhiệm và cách xác nhận rõ ràng.

### Khi thay đổi giá trị dùng chung

Ví dụ tăng timeout mặc định cho các HTTP client:

1. Xác định dịch vụ đang sử dụng khóa đó và có phụ thuộc nào bị ảnh hưởng.
2. Kiểm tra giá trị riêng hiện có để tránh tạo xung đột không chủ ý.
3. Tạo pull request mô tả lý do, phạm vi ảnh hưởng và cách kiểm tra.
4. Chạy kiểm tra cú pháp, cấu hình và integration test với các dịch vụ đại diện.
5. Review bởi nhóm nền tảng cùng các chủ sở hữu dịch vụ liên quan.
6. Phát hành qua label đã kiểm soát, theo dõi lỗi và khả năng kết nối sau khi cập nhật.

### Khi thay đổi cấu hình riêng dịch vụ

Ví dụ đổi topic của <code>orders-service</code>:

1. Nhóm orders xác nhận tên topic mới đã tồn tại và quyền publish/subscribe phù hợp.
2. Chỉ sửa tệp thuộc dịch vụ và profile cần thay đổi.
3. Kiểm tra client nhận đúng cấu hình ở label dự kiến.
4. Phối hợp thứ tự triển khai producer và consumer nếu hai phía phải thay đổi cùng nhau.
5. Theo dõi message flow sau khi refresh hoặc triển khai lại.

Nếu thay đổi ở một repository chung nhưng chỉ ảnh hưởng một dịch vụ, vẫn cần kiểm tra xem khóa có bị kế thừa bởi ứng dụng khác không. Nếu thay đổi thuộc tính dùng chung nhưng chỉ test một dịch vụ, có thể bỏ sót tác động ở các consumer khác.

## 12. Các lỗi thiết kế thường gặp

| Cách tổ chức chưa tốt | Hệ quả | Hướng điều chỉnh |
|---|---|---|
| Đặt URL riêng của một dịch vụ trong <code>application.yml</code> | Ứng dụng khác nhận thuộc tính không liên quan hoặc sai | Chuyển về tệp của dịch vụ |
| Sao chép mọi khóa vào mọi tệp profile | Khó đồng bộ và dễ lệch giá trị | Đặt mặc định chung, chỉ ghi đè khác biệt |
| Dùng khóa chung chung như <code>url</code>, <code>timeout</code> cho nhiều miền nghiệp vụ | Trùng tên nhưng khác ý nghĩa | Dùng namespace theo chức năng hoặc dịch vụ |
| Tách quá nhiều repository cho các giá trị luôn thay đổi cùng nhau | Tăng chi phí đồng bộ và phát hành | Gom theo vòng đời và quyền sở hữu |
| Dồn tất cả cấu hình vào một repository không có owner | Review chậm và khó truy trách nhiệm | Gán owner theo thư mục, tệp hoặc quy trình |
| Dùng nhánh thay đổi liên tục cho production | Khó tái lập phiên bản cấu hình | Ghim tag hoặc commit đã phê duyệt |
| Đưa bí mật dạng rõ vào tệp dùng chung | Nhiều ứng dụng và người dùng có thể đọc | Dùng secret manager hoặc cơ chế mã hóa với khóa riêng |
| Không kiểm tra property source sau khi đổi search path | Giá trị bị ghi đè ngoài dự kiến | Kiểm tra phản hồi endpoint theo từng ứng dụng |

## 13. Checklist thiết kế kho cấu hình

- [ ] Đã phân loại thuộc tính dùng chung, theo môi trường và theo dịch vụ.
- [ ] Mỗi thuộc tính dùng chung có cùng ngữ nghĩa và chính sách với các ứng dụng sử dụng.
- [ ] Cấu hình riêng được đặt trong tệp hoặc thư mục có tên ứng dụng rõ ràng.
- [ ] Quy ước tên application, profile và label được thống nhất với pipeline triển khai.
- [ ] Cấu hình theo profile chỉ chứa các giá trị thực sự khác biệt.
- [ ] Namespace tránh trùng khóa giữa các miền nghiệp vụ.
- [ ] Cấu trúc repository phù hợp với quy mô, quyền truy cập và vòng đời release.
- [ ] Mỗi phạm vi cấu hình có chủ sở hữu và reviewer phù hợp.
- [ ] Bí mật không được lưu ở dạng rõ trong Git; quyền đọc secret được giới hạn theo dịch vụ.
- [ ] Có kiểm tra YAML, khóa bắt buộc, property source và giá trị bind trước khi phát hành.
- [ ] Production dùng label có thể truy vết và có phương án rollback.
- [ ] Thay đổi dùng chung được kiểm tra với nhiều dịch vụ chịu ảnh hưởng.

Một kho cấu hình tốt giúp nhóm biết giá trị nào là mặc định của nền tảng, giá trị nào thuộc môi trường và giá trị nào do từng dịch vụ quyết định. Khi phạm vi, quyền sở hữu và quy tắc ghi đè được thiết kế rõ ràng, Spring Cloud Config có thể phân phối cấu hình nhất quán mà vẫn giữ được tính độc lập cần thiết của từng ứng dụng.

