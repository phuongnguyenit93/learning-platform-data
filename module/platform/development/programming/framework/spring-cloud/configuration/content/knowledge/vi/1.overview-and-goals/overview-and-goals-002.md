# Vì sao cấu hình cần tách khỏi mã nguồn và gói triển khai

Hãy hình dung dịch vụ `order-service` được triển khai ở ba môi trường: phát triển, kiểm thử và sản xuất. Cả ba môi trường chạy cùng một phiên bản mã nguồn, nhưng mỗi môi trường cần địa chỉ cơ sở dữ liệu, cổng thanh toán, mức log, giới hạn kết nối và thời gian chờ khác nhau. Nếu những giá trị này được ghi cứng trong mã nguồn hoặc đóng vào từng gói triển khai, nhóm phát triển phải tạo và quản lý nhiều biến thể của cùng một ứng dụng. Mỗi lần thay đổi một địa chỉ hay tham số vận hành, nhóm có thể phải sửa mã, build lại, kiểm thử lại và phát hành lại.

Tách cấu hình khỏi mã nguồn giúp một phiên bản ứng dụng có thể chạy trong nhiều bối cảnh bằng cách nhận các giá trị phù hợp lúc khởi động hoặc trong quá trình vận hành. Đây là nền tảng của cấu hình ngoài trong Spring Boot và là lý do Spring Cloud Config cung cấp một nơi quản lý cấu hình tập trung cho nhiều dịch vụ.

## 1. Phân biệt mã nguồn, gói triển khai và cấu hình chạy

Ba khái niệm này liên quan với nhau nhưng có vòng đời thay đổi khác nhau:

| Thành phần | Trả lời câu hỏi | Ví dụ |
|---|---|---|
| Mã nguồn | Ứng dụng thực hiện hành vi nào? | Quy tắc tính phí, kiểm tra đơn hàng, xử lý lỗi, cấu trúc API |
| Gói triển khai | Phiên bản nào của ứng dụng được đưa lên môi trường? | JAR, container image, phiên bản `order-service:2.4.1` |
| Cấu hình chạy | Phiên bản đó hoạt động với những giá trị nào ở môi trường hiện tại? | URL dịch vụ phụ thuộc, timeout, số kết nối, mức log, feature flag |

Mã nguồn định nghĩa hành vi và thường thay đổi khi có yêu cầu sản phẩm, sửa lỗi hoặc thay đổi thiết kế. Gói triển khai là kết quả đã build và kiểm thử từ một phiên bản mã nguồn. Cấu hình cung cấp các giá trị có thể thay đổi theo môi trường hoặc nhu cầu vận hành mà không nhất thiết phải biên dịch lại ứng dụng.

Ví dụ, logic tạo đơn hàng không đổi giữa staging và production. Tuy nhiên, staging phải gọi cổng thanh toán thử nghiệm, còn production phải gọi cổng thanh toán thật. Hai địa chỉ này là cấu hình. Nếu nhóm đưa chúng vào mã nguồn bằng các nhánh `if (environment == ...)`, mã nguồn sẽ phải biết quá nhiều về môi trường triển khai và khó kiểm soát khi số môi trường tăng lên.

Tách cấu hình không có nghĩa là xóa mọi giá trị mặc định khỏi ứng dụng. Những mặc định an toàn, dùng được ở môi trường phát triển hoặc trong kiểm thử có thể nằm trong `application.yml` đi kèm ứng dụng. Các giá trị phụ thuộc môi trường, thay đổi thường xuyên hoặc cần quản trị tập trung nên được cung cấp từ bên ngoài. Bí mật như mật khẩu và khóa API cần một cơ chế quản lý bí mật riêng.

## 2. Vì sao không nên gắn cấu hình môi trường vào mã nguồn hoặc gói triển khai?

### Một gói có thể được đưa qua nhiều môi trường

Nếu mỗi môi trường cần một bản build riêng, nhóm phải bảo đảm các bản build thực sự tương đương về mã nguồn và phụ thuộc. Một khác biệt nhỏ trong quá trình build có thể khiến staging chạy tốt nhưng production gặp lỗi. Cách làm ổn định hơn là build một artifact đã xác định phiên bản, sau đó promote cùng artifact qua các môi trường và cung cấp cấu hình tương ứng khi triển khai.

Ví dụ, pipeline có thể build một container image `order-service:2.4.1`. Môi trường dev, staging và production đều dùng đúng image đó, nhưng nhận các giá trị cấu hình khác nhau. Khi có sự cố, nhóm có thể xác định rõ image nào đang chạy và cấu hình nào đã được áp dụng.

### Thay đổi vận hành không phải lúc nào cũng cần phát hành mã mới

Giả sử hệ thống thanh toán bên ngoài yêu cầu giảm timeout từ hai giây xuống một giây, hoặc nhóm vận hành cần nâng mức log của một dịch vụ để điều tra sự cố. Nếu các giá trị này được externalize, người có quyền có thể thay đổi cấu hình theo quy trình đã thống nhất. Ứng dụng có thể nhận giá trị mới ở lần khởi động tiếp theo hoặc qua cơ chế refresh được hỗ trợ.

Điều này rút ngắn vòng phản hồi vận hành và giảm số lần build, đóng gói, phát hành chỉ vì thay đổi tham số. Tuy nhiên, không phải mọi thuộc tính đều có thể thay đổi an toàn khi ứng dụng đang chạy. Một số giá trị chỉ được đọc lúc khởi động; một số bean cần được làm mới; một số thay đổi vẫn đòi hỏi restart hoặc triển khai lại. Khả năng refresh phải được kiểm tra theo từng thuộc tính và thành phần sử dụng nó.

### Tránh cấu hình lệch nhau giữa các dịch vụ

Trong một hệ thống nhiều dịch vụ, các giá trị dùng chung như endpoint của một nền tảng nội bộ, chính sách timeout mặc định hoặc mức log cơ sở có thể xuất hiện ở nhiều nơi. Nếu mỗi nhóm sao chép và sửa các file riêng, cấu hình dễ bị lệch: dịch vụ A gọi endpoint mới trong khi dịch vụ B vẫn gọi endpoint cũ.

Quản lý cấu hình tập trung giúp áp dụng quy ước chung, tái sử dụng giá trị mặc định và theo dõi thay đổi ở một nguồn có kiểm soát. Mỗi dịch vụ vẫn có thể có cấu hình riêng; tập trung không đồng nghĩa với việc mọi dịch vụ phải dùng chung mọi giá trị.

### Có lịch sử, khả năng xem xét và khôi phục

Cấu hình ảnh hưởng trực tiếp đến hành vi của ứng dụng. Một giá trị sai có thể làm cạn connection pool, gửi yêu cầu đến nhầm hệ thống hoặc vô hiệu hóa một tính năng. Khi cấu hình được lưu trong Git, mỗi thay đổi có thể đi cùng commit, người thực hiện, nội dung review và lịch sử phiên bản.

Nhờ đó, nhóm có thể trả lời các câu hỏi: cấu hình production thay đổi khi nào, ai đã thay đổi, thay đổi nào đi cùng sự cố và có thể quay lại phiên bản trước hay không. Git cung cấp lịch sử và cơ chế review; quyền truy cập repository, quy trình phê duyệt và quyền triển khai vẫn cần được thiết kế phù hợp.

## 3. Spring Cloud Config đưa cấu hình ra ngoài như thế nào?

Spring Boot đã hỗ trợ cấu hình ngoài thông qua nhiều nguồn thuộc tính, chẳng hạn file cấu hình, biến môi trường, tham số JVM và tham số dòng lệnh. Spring Cloud Config bổ sung mô hình quản lý tập trung: một **Config Server** đọc cấu hình từ nguồn được quản lý, thường là Git, và các **Config Client** lấy cấu hình dành cho ứng dụng của mình.

Luồng cơ bản gồm các bước:

1. Nhóm lưu các file cấu hình trong một Git repository riêng hoặc một vùng được quản trị như repository cấu hình.
2. Config Server được cấu hình để đọc repository đó và cung cấp cấu hình qua HTTP.
3. Mỗi Spring Boot service khai báo tên ứng dụng, profile và địa chỉ Config Server.
4. Khi khởi động, Config Client yêu cầu cấu hình tương ứng. Spring Boot kết hợp các nguồn thuộc tính để tạo môi trường cấu hình cuối cùng cho ứng dụng.
5. Khi cấu hình trong Git thay đổi, nhóm quyết định thời điểm và cách để các instance nhận giá trị mới: khởi động lại, refresh từng ứng dụng hoặc phát sự kiện refresh qua Spring Cloud Bus.

Ví dụ cấu hình tối thiểu ở phía Config Client, dùng cơ chế `spring.config.import` của Spring Boot hiện đại:

```yaml
spring:
  application:
    name: order-service
  profiles:
    active: ${APP_PROFILE:dev}
  config:
    import: "configserver:http://config-server:8888"
```

`spring.application.name` xác định tên ứng dụng mà Config Server dùng để tìm cấu hình. Profile được chọn từ biến môi trường `APP_PROFILE`, mặc định là `dev` trong ví dụ này. `spring.config.import` khai báo nguồn cấu hình từ Config Server. Trong môi trường production, địa chỉ thực tế cần dùng kết nối được bảo vệ và cơ chế xác thực phù hợp. Có thể thêm tiền tố `optional:` trước `configserver:` nếu ứng dụng được phép khởi động khi Config Server không sẵn sàng; chỉ nên chọn cách này khi ứng dụng có mặc định an toàn và nhóm hiểu rõ rủi ro thiếu cấu hình từ xa.

Ví dụ cấu hình phía Config Server để đọc Git:

```yaml
server:
  port: 8888

spring:
  cloud:
    config:
      server:
        git:
          uri: https://git.example.com/platform/config-repository.git
          default-label: main
```

Config Server cần được triển khai với dependency và bật vai trò Config Server theo cấu hình của ứng dụng Spring Cloud. Đoạn YAML trên chỉ minh họa nguồn Git và nhánh mặc định; thông tin xác thực repository phải được cấp qua cơ chế bảo mật của môi trường, không ghi trực tiếp vào file cấu hình được commit.

## 4. Profile và label giúp chọn đúng cấu hình

Một cấu hình thường được ghép từ nhiều lớp. Tên ứng dụng cho biết dịch vụ nào đang yêu cầu cấu hình; profile cho biết dịch vụ đang chạy trong bối cảnh nào; label xác định phiên bản của repository cấu hình.

Ví dụ repository có thể được tổ chức như sau:

```text
config-repository/
├── application.yml
├── order-service.yml
├── order-service-dev.yml
├── order-service-prod.yml
└── inventory-service.yml
```

- `application.yml` chứa các giá trị mặc định có thể dùng chung.
- `order-service.yml` chứa cấu hình riêng của `order-service`.
- `order-service-dev.yml` và `order-service-prod.yml` chứa phần khác biệt theo profile.
- `inventory-service.yml` chứa cấu hình riêng của một dịch vụ khác.

Config Server định tuyến yêu cầu theo bộ ba application, profile và label; API thường được biểu diễn dưới dạng `/{application}/{profile}/{label}`. Với ví dụ trên, yêu cầu cấu hình cho `order-service`, profile `prod`, label `main` tương ứng với `/order-service/prod/main`.

Profile giúp tránh đóng cứng điều kiện môi trường trong mã nguồn. Label thường là tên branch, tag hoặc commit của Git, cho phép xác định phiên bản cấu hình cần đọc. Branch như `main` thuận tiện khi phát triển nhưng nội dung có thể thay đổi theo thời gian. Với môi trường cần khả năng tái lập cao, nhóm nên cân nhắc dùng tag hoặc commit đã được phê duyệt và ghi nhận label đang triển khai.

Các file cấu hình được ghép thành những property source. Giá trị cuối cùng còn phụ thuộc quy tắc ưu tiên của Spring Boot, vị trí import và các tùy chọn override của Spring Cloud Config. Vì vậy, không nên giả định rằng “cấu hình ở Git luôn thắng” hoặc “biến môi trường luôn thắng” trong mọi cách thiết lập. Nhóm cần xác định nguồn nào được phép ghi đè nguồn nào, ghi lại quy tắc đó và tránh khai báo cùng một thuộc tính ở nhiều nơi nếu không có lý do rõ ràng.

## 5. Cấu hình nào nên đưa ra ngoài?

Quyết định externalize nên dựa vào vòng đời và mức độ nhạy cảm của giá trị, không chỉ dựa vào việc giá trị đó có nằm trong file YAML hay không.

| Loại giá trị | Ví dụ | Cách quản lý phù hợp |
|---|---|---|
| Địa chỉ phụ thuộc môi trường | URL payment gateway, endpoint inventory | Cấu hình ngoài, chọn theo profile hoặc môi trường |
| Tham số vận hành | Timeout, số kết nối tối đa, mức log | Cấu hình có kiểm soát; xác định giới hạn hợp lệ |
| Bật/tắt tính năng | `orders.new-checkout-enabled` | Cấu hình hoặc hệ thống feature flag, kèm quy trình rollout |
| Hành vi nghiệp vụ cốt lõi | Cách tính thuế, quy tắc chuyển trạng thái đơn hàng | Mã nguồn hoặc mô hình quy tắc có phiên bản và kiểm thử rõ ràng |
| Bí mật | Mật khẩu database, token, private key | Secret manager, Vault, KMS hoặc cơ chế cấp bí mật của nền tảng |

Một số giá trị nằm ở ranh giới. Ví dụ, giới hạn số lần thử lại có thể là tham số vận hành, nhưng chính sách retry cũng có thể ảnh hưởng đến tính đúng đắn và tải của hệ thống. Nếu thay đổi giá trị có thể làm thay đổi cam kết nghiệp vụ hoặc gây tác động lớn, cần review và kiểm thử như một thay đổi có ảnh hưởng đến hành vi, kể cả khi nó được lưu trong repository cấu hình.

Đặc biệt, repository Git không nên trở thành nơi lưu mật khẩu hoặc token dạng rõ. Lịch sử Git có thể giữ lại giá trị nhạy cảm ngay cả sau khi file hiện tại đã được sửa. Spring Cloud Config có hỗ trợ một số cơ chế mã hóa và giải mã thuộc tính, nhưng nhóm vẫn phải quản lý khóa, quyền đọc và đường truyền an toàn. Với bí mật cần xoay vòng và phân quyền chặt chẽ, nên dùng secret manager hoặc dịch vụ quản lý khóa chuyên dụng; cấu hình ứng dụng chỉ giữ tham chiếu hoặc nhận bí mật lúc chạy.

## 6. Tách cấu hình tạo ra trách nhiệm vận hành mới

Đưa cấu hình ra ngoài giúp triển khai linh hoạt hơn, đồng thời tạo thêm một thành phần mà hệ thống phải quản lý. Config Server, Git repository, mạng kết nối và cơ chế xác thực đều có thể ảnh hưởng đến khả năng khởi động hoặc cập nhật ứng dụng.

**Quyết định khi Config Server không truy cập được.** Nếu import là bắt buộc, ứng dụng có thể không khởi động khi không lấy được cấu hình. Nếu import là tùy chọn, ứng dụng có thể tiếp tục với các nguồn cấu hình còn lại, nhưng điều đó chỉ an toàn khi các mặc định đủ để ứng dụng hoạt động đúng. Cần xác định rõ hành vi mong muốn cho từng dịch vụ.

**Quyết định cách nhận cấu hình mới.** Một commit mới trong Git không tự động làm mọi instance đang chạy thay đổi giá trị. Client có thể nhận cấu hình mới ở lần khởi động sau. Khi cần cập nhật lúc chạy, Spring Boot Actuator có thể cung cấp endpoint refresh cho các ứng dụng được cấu hình phù hợp; Spring Cloud Bus có thể phát thông báo refresh đến nhiều instance qua broker được hỗ trợ. Các endpoint quản trị phải được giới hạn quyền truy cập và bảo vệ trên mạng. Chỉ những bean và thuộc tính hỗ trợ refresh mới cập nhật đúng cách; cần xác minh tác động trước khi dùng cho thay đổi production.

**Kiểm soát thứ tự ưu tiên.** Cùng một thuộc tính có thể xuất hiện trong cấu hình đóng gói, cấu hình từ xa, biến môi trường hoặc tham số khởi chạy. Nếu không có quy ước, người vận hành khó biết giá trị nào đang có hiệu lực. Hãy quy định rõ nguồn chuẩn cho từng loại thuộc tính, cách override trong tình huống khẩn cấp và cách quan sát giá trị hiệu lực mà không làm lộ bí mật.

**Quản lý thay đổi như một lần phát hành.** Một commit cấu hình có thể thay đổi hành vi production dù không có commit mã nguồn mới. Vì vậy, cấu hình cần review, kiểm tra cú pháp, kiểm thử ở môi trường phù hợp, phê duyệt, theo dõi sau triển khai và kế hoạch rollback. Nên ghim label cho lần triển khai quan trọng để có thể tái tạo đúng tổ hợp mã nguồn và cấu hình đã chạy.

## 7. Ví dụ: cùng một dịch vụ, hai môi trường

Giả sử `order-service` có cấu hình chung trong `order-service.yml`:

```yaml
orders:
  request-timeout: 2s
  max-retry-attempts: 2

payment:
  gateway:
    connect-timeout: 1s

logging:
  level:
    com.example.orders: INFO
```

Trong `order-service-dev.yml`, dịch vụ có thể gọi sandbox và bật log chi tiết hơn:

```yaml
payment:
  gateway:
    base-url: https://sandbox-payments.example.test

logging:
  level:
    com.example.orders: DEBUG
```

Trong `order-service-prod.yml`, dịch vụ dùng endpoint production và mức log phù hợp với vận hành:

```yaml
payment:
  gateway:
    base-url: https://payments.example.com

logging:
  level:
    com.example.orders: INFO
```

Các file trên không chứa mật khẩu hoặc token. Cùng một image của `order-service` có thể nhận profile `dev` hoặc `prod` tùy môi trường triển khai. Khi chuyển từ môi trường này sang môi trường khác, nhóm thay đổi nguồn cấu hình được chọn và thông tin bí mật được cấp từ hệ thống quản lý bí mật; không cần tạo một nhánh mã nguồn chỉ để thay URL.

Nếu muốn giảm timeout ở production, nhóm tạo thay đổi cấu hình, review và triển khai theo quy trình. Nếu thay đổi chỉ có hiệu lực sau restart, nhóm lên lịch restart phù hợp. Nếu thuộc tính và bean hỗ trợ refresh, nhóm có thể dùng cơ chế refresh đã được bảo vệ. Trong cả hai trường hợp, cần quan sát lỗi, độ trễ và tải hệ thống sau thay đổi, đồng thời giữ lại label hoặc commit trước đó để rollback.

## 8. Nguyên tắc cần ghi nhớ

- Giữ mã nguồn tập trung vào hành vi của ứng dụng; đưa khác biệt theo môi trường vào cấu hình chạy.
- Build một artifact có phiên bản rõ ràng và promote artifact đó qua các môi trường khi có thể.
- Dùng tên ứng dụng, profile và label để xác định đúng cấu hình; chọn label có chủ đích cho production.
- Quản lý cấu hình trong Git để có lịch sử và review, nhưng không commit bí mật dạng rõ.
- Xác định quy tắc ưu tiên giữa cấu hình đóng gói, cấu hình từ xa, biến môi trường và tham số khởi chạy.
- Thiết kế trước hành vi khi Config Server mất kết nối và cách các instance nhận cấu hình mới.
- Xem thay đổi cấu hình là thay đổi có thể ảnh hưởng production: cần kiểm thử, phê duyệt, quan sát và rollback.

Tách cấu hình khỏi mã nguồn và gói triển khai giúp cùng một phiên bản ứng dụng thích nghi với nhiều môi trường, giảm sai lệch giữa các lần phát hành và làm rõ lịch sử thay đổi vận hành. Spring Cloud Config cung cấp cách phân phối cấu hình tập trung qua Config Server và Config Client, còn Git, profile, label, quy tắc ưu tiên, bảo vệ bí mật và quy trình refresh quyết định việc cấu hình đó có thể được quản trị an toàn và nhất quán hay không.
