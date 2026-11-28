# Cấu hình chung, cấu hình theo môi trường và dữ liệu nghiệp vụ

Trong một hệ thống có nhiều ứng dụng Spring Boot, không phải mọi giá trị mà ứng dụng sử dụng đều thuộc cùng một loại. Một số giá trị là mặc định dùng chung cho nhiều dịch vụ; một số phụ thuộc môi trường triển khai như `dev`, `staging` hoặc `prod`; còn một số là dữ liệu nghiệp vụ được tạo và thay đổi trong quá trình xử lý đơn hàng, thanh toán hay quản lý tồn kho.

Phân biệt đúng ba nhóm này giúp tổ chức kho cấu hình Spring Cloud Config rõ ràng, giảm sao chép, tránh đưa dữ liệu nghiệp vụ vào Git và kiểm soát được phạm vi ảnh hưởng khi thay đổi. Bài học đặt trong bối cảnh quản lý cấu hình tập trung cho nhiều ứng dụng Spring Boot bằng Config Server, Config Client và nguồn cấu hình Git.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

- Phân biệt cấu hình chung, cấu hình theo môi trường và dữ liệu nghiệp vụ dựa trên mục đích, chủ sở hữu và vòng đời thay đổi.
- Chọn nơi lưu phù hợp cho một giá trị: tệp cấu hình dùng chung, tệp riêng cho ứng dụng, tệp theo profile, hệ thống quản lý bí mật hay kho dữ liệu nghiệp vụ.
- Tổ chức các tệp `application.yml`, `application-{profile}.yml`, `{application}.yml` và `{application}-{profile}.yml` trong Git repository của Config Server.
- Giải thích cách profile giúp chọn cấu hình theo môi trường và vì sao cần kiểm tra thứ tự ưu tiên khi một thuộc tính xuất hiện ở nhiều nguồn.
- Sử dụng cấu hình có kiểu dữ liệu với `@ConfigurationProperties` và quản trị thay đổi theo phạm vi ảnh hưởng.

## 2. Ba nhóm giá trị cần phân biệt

### Cấu hình chung

Cấu hình chung là các mặc định có cùng ý nghĩa và có thể tái sử dụng ở nhiều ứng dụng. Ví dụ:

- Mức log mặc định của các dịch vụ.
- Thời gian chờ HTTP mặc định khi gọi dịch vụ nội bộ.
- Một số thuộc tính quan sát hệ thống như tên môi trường trong nhãn metric hoặc tỷ lệ lấy mẫu trace mặc định.
- Quy ước định dạng ngày giờ hoặc giới hạn kỹ thuật được nhiều ứng dụng cùng tuân theo.

Đặt giá trị ở cấp chung giúp các dịch vụ nhất quán và giảm khai báo lặp. Tuy nhiên, chỉ dùng chung khi ngữ nghĩa thực sự giống nhau. Nếu một dịch vụ cần thời gian chờ dài hơn vì xử lý tác vụ khác biệt, hãy cho phép cấu hình riêng thay vì ép mọi dịch vụ dùng một con số.

### Cấu hình theo môi trường

Cấu hình theo môi trường là các giá trị thay đổi theo nơi ứng dụng được triển khai hoặc theo đặc điểm của môi trường chạy. Ví dụ:

- URL và cổng của cơ sở dữ liệu, message broker hoặc dịch vụ phụ thuộc.
- Địa chỉ API của hệ thống thanh toán thử nghiệm và hệ thống thanh toán thật.
- Thời gian chờ, giới hạn kết nối hoặc mức log được chọn cho từng môi trường.
- Cờ bật tính năng phục vụ thử nghiệm có kiểm soát.

Một cấu hình có thể vừa thuộc phạm vi một ứng dụng vừa phụ thuộc môi trường. Chẳng hạn, URL cơ sở dữ liệu của `order-service` là cấu hình riêng của ứng dụng và có giá trị khác nhau ở `dev` và `prod`. Vì vậy, “chung/riêng theo ứng dụng” và “theo môi trường” là hai chiều phân loại có thể kết hợp, không phải ba ngăn hoàn toàn tách biệt.

### Dữ liệu nghiệp vụ

Dữ liệu nghiệp vụ mô tả các đối tượng và trạng thái mà hệ thống quản lý để thực hiện hoạt động kinh doanh. Ví dụ:

- Khách hàng, địa chỉ giao hàng và trạng thái tài khoản.
- Đơn hàng, dòng sản phẩm, trạng thái thanh toán và lịch sử hoàn tiền.
- Số lượng tồn kho, lô hàng và lịch sử xuất nhập kho.
- Giao dịch, hóa đơn và lịch sử sử dụng khuyến mãi.

Những dữ liệu này thường được tạo, cập nhật và truy vấn liên tục trong lúc hệ thống hoạt động. Chúng cần ràng buộc toàn vẹn, giao dịch, phân quyền theo nghiệp vụ, lịch sử kiểm toán và khả năng truy vấn. Vì thế, dữ liệu nghiệp vụ thường thuộc cơ sở dữ liệu, dịch vụ miền hoặc hệ thống dữ liệu chuyên trách, không nên được lưu như các thuộc tính cấu hình trong Git.

| Tiêu chí | Cấu hình chung | Cấu hình theo môi trường | Dữ liệu nghiệp vụ |
| --- | --- | --- | --- |
| Mục đích | Đặt mặc định kỹ thuật có thể dùng chung | Điều chỉnh ứng dụng cho nơi triển khai | Mô tả đối tượng và trạng thái nghiệp vụ |
| Ví dụ | HTTP timeout mặc định, mức log mặc định | URL database, endpoint sandbox/prod | Đơn hàng, khách hàng, tồn kho |
| Nhịp thay đổi | Thường theo thay đổi nền tảng hoặc tiêu chuẩn kỹ thuật | Theo thay đổi hạ tầng và vận hành môi trường | Có thể thay đổi liên tục theo giao dịch |
| Nơi lưu thường gặp | Tệp cấu hình chung trong Git | Tệp cấu hình theo profile, biến môi trường hoặc secret manager | Cơ sở dữ liệu và hệ thống dữ liệu nghiệp vụ |
| Cách phân phối | Config Server cung cấp cho nhiều client | Client nhận cấu hình của profile đang chạy | Ứng dụng truy vấn hoặc nhận sự kiện từ hệ thống dữ liệu |

## 3. Cách quyết định một giá trị thuộc nhóm nào

Khi gặp một giá trị mới, hãy đặt một số câu hỏi trước khi chọn nơi lưu:

1. **Giá trị này mô tả cách ứng dụng được vận hành hay mô tả trạng thái của hoạt động kinh doanh?** Timeout kết nối là cấu hình; trạng thái đơn hàng là dữ liệu nghiệp vụ.
2. **Ai chịu trách nhiệm thay đổi?** Nhóm nền tảng hoặc vận hành thường quản lý cấu hình kỹ thuật; nghiệp vụ hoặc người dùng được phân quyền có thể tạo và cập nhật dữ liệu nghiệp vụ.
3. **Giá trị thay đổi theo môi trường triển khai hay theo từng giao dịch?** URL của dịch vụ phụ thuộc thường thay đổi theo môi trường; địa chỉ giao hàng thay đổi theo đơn hàng.
4. **Có cần cập nhật nguyên tử cùng một giao dịch nghiệp vụ, tìm kiếm, lọc hoặc lưu lịch sử theo từng bản ghi không?** Nếu có, cơ sở dữ liệu hoặc dịch vụ nghiệp vụ thường phù hợp hơn tệp cấu hình.
5. **Thay đổi có cần review và phát hành cùng phiên bản cấu hình không?** Nếu có, Git và quy trình review có thể là lựa chọn phù hợp.

Một số trường hợp nằm ở ranh giới giữa cấu hình và dữ liệu. Ví dụ, mã quốc gia có thể là danh mục tham chiếu ổn định, nhưng bảng giá, thuế suất, hạn mức tín dụng hoặc chính sách khuyến mãi thường có ý nghĩa nghiệp vụ, hiệu lực theo thời gian và yêu cầu kiểm toán. Nếu các giá trị đó do nghiệp vụ quản lý, cần truy vấn hoặc thay đổi thường xuyên, hãy mô hình hóa chúng thành dữ liệu nghiệp vụ có phiên bản và quyền quản trị phù hợp.

Cờ tính năng (feature flag) cũng cần được xem xét theo cách sử dụng. Một cờ bật/tắt tính năng để triển khai theo đợt có thể là cấu hình vận hành. Một quy tắc quyết định khách hàng nào được hưởng ưu đãi lại là logic hoặc dữ liệu nghiệp vụ. Không nên biến mọi quy tắc kinh doanh thành một tập hợp biến cấu hình chỉ vì chúng có thể biểu diễn bằng boolean hoặc con số.

## 4. Tổ chức các tệp trong Git repository

Spring Cloud Config có thể đọc các tệp cấu hình theo tên ứng dụng và profile. Một cách tổ chức thường gặp là:

```text
config-repo/
├── application.yml
├── application-dev.yml
├── application-prod.yml
├── order-service.yml
├── order-service-dev.yml
├── order-service-prod.yml
├── payment-service.yml
├── payment-service-dev.yml
└── payment-service-prod.yml
```

Ý nghĩa của các tệp:

- `application.yml`: cấu hình mặc định dùng chung cho các ứng dụng.
- `application-dev.yml` và `application-prod.yml`: cấu hình chung khi các ứng dụng chạy với profile tương ứng.
- `order-service.yml`: cấu hình mặc định riêng của `order-service`.
- `order-service-dev.yml` và `order-service-prod.yml`: cấu hình riêng của `order-service` theo từng môi trường.
- Các tệp `payment-service...` tổ chức theo cùng nguyên tắc cho dịch vụ thanh toán.

Tên ứng dụng thường được khai báo qua `spring.application.name`. Profile đang hoạt động quyết định nhóm cấu hình theo môi trường mà client yêu cầu. Config Server đọc các nguồn phù hợp và trả về một `Environment` gồm các property source. Client nhận các nguồn đó rồi sử dụng theo cơ chế cấu hình của Spring Boot.

Không nhất thiết phải tạo đủ mọi tệp cho mọi ứng dụng và mọi môi trường. Chỉ tạo tệp khi có thuộc tính cần quản lý ở phạm vi đó. Một tệp profile rỗng hoặc sao chép toàn bộ nội dung từ tệp chung sẽ làm kho cấu hình khó bảo trì.

## 5. Ví dụ phân chia cấu hình

Giả sử hệ thống có `order-service` và `payment-service`. Hai dịch vụ dùng chung mặc định về thời gian chờ và logging, nhưng mỗi dịch vụ có cấu hình kết nối riêng. Ví dụ `application.yml`:

```yaml
platform:
  http:
    connect-timeout: 2s
    read-timeout: 5s
  logging:
    level: INFO
```

Các thuộc tính trên là mặc định kỹ thuật dùng chung. `order-service.yml` có thể bổ sung cấu hình riêng:

```yaml
order:
  downstream:
    inventory:
      max-connections: 20
      read-timeout: 3s
```

`payment-service.yml` có thể có nhóm thuộc tính riêng cho tích hợp thanh toán:

```yaml
payment:
  gateway:
    connect-timeout: 4s
    read-timeout: 12s
    retry-count: 2
```

Giá trị endpoint cơ sở dữ liệu của `order-service` có thể thay đổi theo profile. Ví dụ `order-service-dev.yml`:

```yaml
spring:
  datasource:
    url: jdbc:postgresql://localhost:5432/orders
    username: orders_app
```

Và `order-service-prod.yml`:

```yaml
spring:
  datasource:
    url: jdbc:postgresql://orders-db.internal:5432/orders
    username: orders_app
    password: ${ORDER_DB_PASSWORD}
```

`ORDER_DB_PASSWORD` trong ví dụ là biến được cung cấp từ môi trường triển khai hoặc hệ thống quản lý bí mật. Không commit mật khẩu thật vào Git. Cách phân giải placeholder cần được kiểm tra với cấu hình client và nền tảng triển khai đang dùng.

Trong ví dụ này, URL database là cấu hình theo môi trường; tên người dùng là cấu hình kết nối; mật khẩu là bí mật cần bảo vệ. Bản ghi đơn hàng và số lượng tồn kho vẫn là dữ liệu nghiệp vụ và được lưu trong các hệ thống dữ liệu tương ứng.

## 6. Profile giúp chọn cấu hình môi trường

Profile biểu diễn một nhóm điều kiện chạy, thường được đặt tên như `dev`, `test`, `staging` và `prod`. Ứng dụng có thể nhận profile qua biến môi trường hoặc tham số triển khai. Ví dụ cấu hình Config Client dùng Config Data API:

```yaml
spring:
  application:
    name: order-service
  config:
    import: "configserver:http://config-server:8888"
```

Profile có thể được truyền từ môi trường chạy, chẳng hạn:

```text
SPRING_PROFILES_ACTIVE=prod
```

Khi đó, client yêu cầu cấu hình cho `order-service` với profile `prod`. Trong thực tế, địa chỉ Config Server cũng cần được cấp phù hợp cho môi trường. Nếu dùng tiền tố `optional:` trong `spring.config.import`, ứng dụng có thể khởi động khi Config Server không truy cập được; chỉ nên làm vậy nếu có giá trị dự phòng an toàn và ứng dụng vẫn có thể hoạt động đúng. Với cấu hình bắt buộc, nên để khởi động thất bại khi không lấy được cấu hình cần thiết.

Profile chỉ là cơ chế chọn cấu hình. Tên `prod` không tự tạo ra bảo mật, không mã hóa giá trị và không ngăn ứng dụng khác yêu cầu profile đó. Quyền đọc Config Server, quyền truy cập Git và quyền truy cập bí mật phải được kiểm soát riêng.

## 7. Thứ tự ưu tiên khi nhiều nguồn cùng khai báo một khóa

Một thuộc tính có thể xuất hiện trong `application.yml`, tệp riêng của ứng dụng, tệp profile hoặc nguồn cấu hình cục bộ của client. Khi nhiều nguồn cùng khai báo một khóa, ứng dụng cần có quy tắc rõ ràng để xác định giá trị nào được sử dụng.

Hãy phân biệt hai bước:

1. **Config Server tổng hợp nguồn từ repository:** server tìm các tệp phù hợp với tên ứng dụng và profile, rồi trả về danh sách property source. Thứ tự các nguồn trong phản hồi có ý nghĩa đối với việc ghi đè giá trị.
2. **Spring Boot hợp nhất các nguồn của client:** cấu hình từ xa được đưa vào `Environment` cùng các nguồn khác như file cục bộ, biến môi trường và tham số dòng lệnh. Thứ tự ưu tiên thực tế chịu ảnh hưởng của phiên bản Spring Boot/Spring Cloud và chính sách override của Config Client.

Do đó, không nên mặc định rằng biến môi trường, file theo profile hay cấu hình từ xa luôn thắng trong mọi dự án. Khi cần xác định giá trị hiệu lực:

- Kiểm tra endpoint Config Server theo ứng dụng, profile và label, ví dụ `GET /order-service/prod/main`, để xem các property source mà server trả về.
- Kiểm tra cấu hình của client và các tùy chọn cho phép cấu hình từ xa bị ghi đè hoặc ghi đè cấu hình cục bộ. Những tùy chọn này cần được đặt đúng phía và theo phiên bản Spring Cloud đang dùng.
- Trong môi trường đã bảo vệ, có thể dùng endpoint chẩn đoán của Spring Boot Actuator như `/actuator/env` để xác định nguồn của một thuộc tính. Endpoint này có thể tiết lộ thông tin nhạy cảm nên phải giới hạn quyền truy cập và che giá trị phù hợp.
- Tránh khai báo cùng một khóa ở nhiều nơi nếu không có chủ đích. Nếu có ghi đè, hãy ghi rõ lý do và phạm vi áp dụng.

Ví dụ, `platform.http.read-timeout` có thể có mặc định 5 giây trong `application.yml`, nhưng `order-service` cần 3 giây. Nếu quy tắc property source được thiết lập để tệp riêng ứng dụng có ưu tiên cao hơn nguồn chung, giá trị 3 giây sẽ được dùng cho dịch vụ đó. Hãy xác minh thứ tự thực tế trong phản hồi và môi trường chạy thay vì dựa vào tên tệp để suy đoán.

## 8. Đọc cấu hình có kiểu dữ liệu trong Spring Boot

Khi cấu hình có nhiều thuộc tính liên quan, nên nhóm chúng thành một lớp hoặc record bằng `@ConfigurationProperties`. Cách này giúp cấu hình có cấu trúc, dễ kiểm tra và dễ sử dụng hơn việc rải nhiều chuỗi `@Value` trong mã nguồn.

Ví dụ với các thuộc tính `platform.http`:

```java
import java.time.Duration;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "platform.http")
public record HttpClientProperties(
        Duration connectTimeout,
        Duration readTimeout) {
}
```

Ứng dụng có thể bật quét cấu hình bằng `@ConfigurationPropertiesScan` trên lớp khởi động hoặc đăng ký lớp bằng `@EnableConfigurationProperties(HttpClientProperties.class)`. Sau đó inject `HttpClientProperties` vào thành phần cần dùng.

Việc dùng kiểu `Duration` cho thời gian chờ giúp giá trị trong YAML như `2s` hoặc `500ms` được biểu diễn rõ ràng. Với cấu hình quan trọng, có thể bổ sung validation như `@NotNull`, `@Min` hoặc các ràng buộc phù hợp để ứng dụng phát hiện giá trị không hợp lệ ngay khi khởi động.

Ví dụ cấu hình hợp lệ về cú pháp vẫn có thể sai về nghiệp vụ vận hành: timeout bằng 0, số kết nối âm hoặc URL trỏ nhầm môi trường. Kiểm tra kiểu dữ liệu và giới hạn hợp lệ giúp phát hiện một phần lỗi trước khi dịch vụ nhận lưu lượng.

## 9. Dữ liệu nghiệp vụ nên có vòng đời riêng

Giả sử `order-service` cần lưu đơn hàng. Một đơn hàng có mã, khách hàng, danh sách sản phẩm, tổng tiền và trạng thái. Những giá trị này không phải cấu hình của ứng dụng. Chúng thay đổi theo giao dịch và cần được lưu bền vững trong hệ thống dữ liệu nghiệp vụ.

Nếu đưa dữ liệu đơn hàng vào Git như cấu hình, mỗi lần tạo đơn sẽ cần thay đổi repository và kích hoạt quy trình phân phối cấu hình. Cách làm đó không hỗ trợ tốt giao dịch đồng thời, truy vấn theo khách hàng, ràng buộc dữ liệu hay lịch sử trạng thái. Nó còn khiến kho cấu hình chứa dữ liệu có thể nhạy cảm và mở rộng rất nhanh.

Tương tự, không nên lưu số lượng tồn kho hiện tại, số dư tài khoản, trạng thái thanh toán hoặc địa chỉ khách hàng trong Config Server. Ứng dụng nên đọc và cập nhật dữ liệu qua repository, database hoặc API của dịch vụ sở hữu dữ liệu đó.

Một số dữ liệu tham chiếu ít thay đổi như danh sách mã vùng hoặc đơn vị đo có thể được đóng gói hoặc quản lý tập trung nếu quy mô nhỏ và yêu cầu cập nhật đơn giản. Nhưng nếu danh mục được người dùng nghiệp vụ quản trị, có hiệu lực theo thời gian, cần tìm kiếm hoặc cần kiểm toán, hãy xem nó như dữ liệu nghiệp vụ và chọn hệ thống lưu trữ tương ứng.

## 10. Bảo vệ bí mật trong cấu hình

Mật khẩu, token truy cập, khóa ký và chứng thư riêng là bí mật. Chúng thường được ứng dụng sử dụng cùng cấu hình kết nối, nhưng cần vòng đời và quyền truy cập riêng.

- Không lưu bí mật dạng văn bản thuần trong Git, kể cả trong tệp `*-prod.yml` hoặc nhánh chỉ dành cho sản xuất.
- Ưu tiên Vault hoặc dịch vụ quản lý bí mật của nền tảng triển khai; cấp bí mật cho ứng dụng theo danh tính và quyền tối thiểu.
- Nếu dùng cơ chế mã hóa của Spring Cloud Config, quản lý khóa giải mã bên ngoài repository, giới hạn endpoint mã hóa/giải mã và xây dựng quy trình xoay vòng khóa.
- Bảo vệ Config Server bằng xác thực, phân quyền và TLS; giới hạn ứng dụng nào được đọc cấu hình nào.
- Không để giá trị bí mật xuất hiện trong log, thông báo lỗi hoặc endpoint chẩn đoán.

Việc tách bí mật khỏi Git cũng giúp phân biệt rõ cấu hình kết nối và thông tin xác thực. Ví dụ, URL database có thể được lưu theo profile, trong khi mật khẩu được lấy từ secret manager khi ứng dụng khởi động.

## 11. Quản trị thay đổi theo đúng phạm vi

Một thay đổi trong `application.yml` có thể ảnh hưởng nhiều dịch vụ; thay đổi trong `order-service-prod.yml` có phạm vi hẹp hơn. Trước khi cập nhật, hãy xác định các client nhận thuộc tính đó và môi trường nào sẽ bị tác động.

Quy trình quản trị nên bao gồm:

1. **Đặt đúng phạm vi:** chỉ đưa giá trị dùng chung lên cấp `application`; đặt giá trị riêng trong tệp của ứng dụng; đặt giá trị theo môi trường trong tệp profile tương ứng.
2. **Review thay đổi:** mô tả lý do, giá trị cũ/mới, ứng dụng và môi trường bị ảnh hưởng; yêu cầu người có trách nhiệm phê duyệt.
3. **Kiểm tra trước khi áp dụng:** kiểm tra YAML, kiểu dữ liệu, giá trị bắt buộc, placeholder và tính tương thích với ứng dụng.
4. **Chọn phiên bản có thể tái lập:** dùng label trỏ đến nhánh, tag hoặc commit theo chính sách phát hành; ghi nhận phiên bản cấu hình của từng môi trường.
5. **Phân phối có kiểm soát:** thử trên môi trường hoặc nhóm instance nhỏ, quan sát metric và log, sau đó mới mở rộng.
6. **Chuẩn bị quay lui:** giữ lại label hoặc commit đã biết là tốt và xác định cách đưa các instance về phiên bản đó.

Không nên dùng một thay đổi cấu hình để lén thay đổi dữ liệu nghiệp vụ hoặc triển khai một quy tắc kinh doanh phức tạp. Khi thay đổi thuộc miền nghiệp vụ, hãy dùng quy trình và mô hình dữ liệu có kiểm soát tương ứng.

## 12. Tình huống minh họa: hai dịch vụ, ba môi trường

Một nền tảng có `order-service` và `payment-service`, triển khai ở `dev`, `staging` và `prod`.

- Cả hai dịch vụ dùng chung mức log mặc định và timeout HTTP cơ bản. Các giá trị này đặt trong `application.yml`.
- Mỗi dịch vụ có timeout gọi phụ thuộc riêng. Các giá trị này đặt trong `{application}.yml`.
- URL database và endpoint thanh toán khác nhau theo môi trường. Các giá trị này đặt trong `{application}-{profile}.yml` hoặc được cấp qua cấu hình triển khai thích hợp.
- Mật khẩu database và token cổng thanh toán lấy từ secret manager; chúng không được commit vào Git.
- Đơn hàng, giao dịch thanh toán và tồn kho được lưu trong database hoặc dịch vụ nghiệp vụ sở hữu dữ liệu.

Khi đổi timeout HTTP mặc định, nhóm nền tảng phải đánh giá cả hai dịch vụ. Khi đổi endpoint sandbox của cổng thanh toán, phạm vi chính là `payment-service` ở môi trường tương ứng. Khi cập nhật trạng thái một đơn hàng, `order-service` ghi dữ liệu nghiệp vụ qua giao dịch; Config Server không tham gia vào thao tác đó.

| Thay đổi | Nơi quản lý phù hợp | Phạm vi cần xem xét |
| --- | --- | --- |
| Timeout HTTP mặc định | `application.yml` trong Git | Các ứng dụng dùng mặc định chung |
| Timeout riêng của gọi tồn kho | `order-service.yml` | `order-service` |
| URL database sản xuất | `order-service-prod.yml` hoặc cấu hình môi trường | `order-service` ở `prod` |
| Mật khẩu database | Secret manager hoặc nguồn bí mật của nền tảng | Ứng dụng được cấp quyền đọc bí mật |
| Trạng thái đơn hàng | Cơ sở dữ liệu nghiệp vụ | Đơn hàng và quy trình xử lý liên quan |
| Số lượng tồn kho hiện tại | Dịch vụ/kho dữ liệu tồn kho | Giao dịch nhập, xuất và giữ hàng |

## 13. Checklist trước khi thêm một thuộc tính

- [ ] Đã xác định đây là cấu hình kỹ thuật, bí mật hay dữ liệu nghiệp vụ.
- [ ] Đã xác định chủ sở hữu và những ứng dụng cần sử dụng giá trị.
- [ ] Đã chọn đúng phạm vi chung, riêng theo ứng dụng và profile môi trường.
- [ ] Đã kiểm tra xem thuộc tính có bị khai báo trùng ở nguồn khác không.
- [ ] Đã xác định giá trị hiệu lực theo property source và chính sách override thực tế.
- [ ] Đã tránh đưa mật khẩu, token hoặc khóa riêng vào Git ở dạng văn bản thuần.
- [ ] Đã kiểm tra giá trị, kiểu dữ liệu, quyền truy cập và phương án quay lui.

Khi tổ chức cấu hình Spring Cloud Config, hãy giữ cấu hình chung cho những mặc định kỹ thuật thực sự được chia sẻ, dùng profile để cung cấp giá trị phù hợp với môi trường và để dữ liệu nghiệp vụ đi theo vòng đời của hệ thống nghiệp vụ. Ranh giới rõ ràng giúp Config Server phân phối cấu hình nhất quán, đồng thời giữ cho dữ liệu giao dịch, bí mật và quy tắc kinh doanh được quản lý đúng cách.
