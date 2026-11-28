# Nạp nhiều nguồn import và xác định thứ tự áp dụng

Một ứng dụng Spring Boot có thể nhận cấu hình từ nhiều nơi: file `application.yml` đóng gói trong JAR, file bên ngoài container, thư mục secret được mount, Config Server hoặc biến môi trường của nền tảng triển khai. Spring Boot dùng cơ chế Config Data để nạp các nguồn này vào Environment. Khi nhiều nguồn cùng khai báo một key, thứ tự xử lý quyết định giá trị cuối cùng mà ứng dụng nhìn thấy.

Trong hệ thống Spring Cloud Config, cần hiểu hai lớp thứ tự: thứ tự giữa các location được khai báo qua `spring.config.import` và chính sách ưu tiên của property source từ Config Server so với cấu hình cục bộ. Hai lớp này có liên quan nhưng không hoàn toàn giống nhau. Bài viết hướng dẫn cách khai báo nhiều import, cách xác định nguồn thắng, và cách kiểm tra giá trị hiệu lực khi triển khai nhiều ứng dụng Spring Boot.

## 1. Các loại nguồn cấu hình có thể import

Config Data hỗ trợ nhiều loại location. Một ứng dụng có thể phối hợp chúng trong cùng một lần khởi động.

| Nguồn | Ví dụ location | Mục đích |
| --- | --- | --- |
| File ngoài ứng dụng | `file:./config/common.yml` | Giá trị theo môi trường hoặc theo instance |
| File trong classpath | `classpath:/defaults.yml` | Giá trị mặc định được đóng gói cùng ứng dụng |
| Config tree | `configtree:/run/secrets/` | Đọc secret từ các file được mount |
| Spring Cloud Config Server | `configserver:http://config-server:8888` | Cấu hình tập trung theo application, profile và label |
| Import tùy chọn | `optional:file:./local.yml` | Cho phép bỏ qua location có thể không tồn tại |

Cơ chế import giúp ứng dụng nạp các nguồn theo một khai báo tập trung trong `spring.config.import`. Với Config Server, ứng dụng cần dependency Config Client tương thích với Spring Boot/Spring Cloud và khai báo location có scheme `configserver:`.

## 2. Khai báo nhiều nguồn trong spring.config.import

Có thể khai báo một danh sách location trong YAML:

```yaml
spring:
  application:
    name: orders-service
  profiles:
    active: prod
  config:
    import:
      - "optional:classpath:/defaults.yml"
      - "optional:file:./config/common.yml"
      - "optional:file:./config/orders-service.yml"
      - "optional:configtree:/run/secrets/"
      - "configserver:http://config-server:8888"
```

Các location được xử lý theo thứ tự khai báo. Với các nguồn cùng tham gia Config Data, import được xử lý theo thứ tự và các location đứng sau có thể ghi đè location đứng trước khi cùng khai báo một key. Giá trị được import cũng có độ ưu tiên cao hơn document khai báo import đó.

Ví dụ, nếu `defaults.yml` đặt `orders.http.read-timeout=5s`, còn `common.yml` đặt giá trị là `8s`, thì nguồn được import sau có thể thay thế giá trị trước. Khi Config Server cũng cung cấp key đó, cần xét thêm chính sách ưu tiên remote property source của Spring Cloud Config; phần này được trình bày ở mục riêng.

Có thể viết danh sách trên thành một chuỗi phân tách bằng dấu phẩy trong properties:

```properties
spring.config.import=optional:classpath:/defaults.yml,optional:file:./config/common.yml,optional:file:./config/orders-service.yml,optional:configtree:/run/secrets/,configserver:http://config-server:8888
```

Không đặt dấu phẩy trong tên location trừ khi đã xử lý đúng quy tắc phân tách. Với cấu hình phức tạp, YAML sequence thường dễ đọc và review hơn.

## 3. Ý nghĩa của optional và import bắt buộc

Tiền tố `optional:` đánh dấu location là không bắt buộc. Với file location, ứng dụng có thể tiếp tục khi file không tồn tại; với Config Server, tiền tố này cho phép ứng dụng khởi động khi server không truy cập được. Lỗi cú pháp hoặc lỗi parse trong một file đã tìm thấy vẫn cần được xử lý, không nên coi `optional:` là cách bỏ qua mọi lỗi cấu hình.

Ví dụ, file cấu hình cá nhân chỉ tồn tại trên một số máy phát triển:

```yaml
spring:
  config:
    import:
      - "optional:file:./config/developer-overrides.yml"
      - "configserver:http://config-server:8888"
```

Trong ví dụ này, file override cá nhân có thể vắng mặt. Config Server vẫn là nguồn bắt buộc; nếu không lấy được cấu hình từ xa, ứng dụng sẽ thất bại khi nạp Config Data.

Nếu Config Server được phép tạm thời không truy cập được và ứng dụng có giá trị mặc định an toàn, có thể dùng:

```yaml
spring:
  config:
    import: "optional:configserver:http://config-server:8888"
```

Không nên thêm `optional:` một cách máy móc cho mọi nguồn. Nếu thiếu database password, endpoint dịch vụ hoặc chính sách bảo mật mà ứng dụng cần để chạy đúng, khởi động thành công với cấu hình thiếu có thể nguy hiểm hơn việc dừng rõ ràng. Chỉ đánh dấu optional khi có phương án fallback đã được thiết kế và kiểm thử.

## 4. File mặc định, file ngoài container và Config Server

Một ví dụ thực tế cho dịch vụ đơn hàng có thể phân chia trách nhiệm như sau:

- `application.yml` trong JAR chứa cấu hình mặc định an toàn.
- `common.yml` bên ngoài container chứa giá trị theo môi trường triển khai.
- `orders-service.yml` bên ngoài container chứa điều chỉnh riêng cho service.
- Config Server cung cấp cấu hình tập trung được review và quản lý theo profile/label.
- Config tree cung cấp secret từ các file được nền tảng mount.

Cấu trúc trên máy host:

```text
deployment/
├── config/
│   ├── common.yml
│   └── orders-service.yml
└── secrets/
    ├── orders.db.password
    └── orders.api-token
```

Ví dụ `common.yml`:

```yaml
platform:
  region: ap-southeast-1
orders:
  http:
    connect-timeout: 2s
```

Ví dụ `orders-service.yml`:

```yaml
orders:
  http:
    read-timeout: 8s
  retry:
    max-attempts: 3
```

Các file trong thư mục `secrets` chứa giá trị secret thuần do secret manager hoặc nền tảng cấp vào runtime. Ví dụ tên file `orders.db.password` trở thành property key tương ứng trong config tree. Không commit nội dung secret vào Git hoặc Docker image.

Config Server có thể cung cấp thêm giá trị `orders.http.read-timeout` theo profile `prod`. Nếu key đó được khai báo ở nhiều nơi, hãy xác định nguồn nào có quyền sở hữu key và kiểm tra kết quả thực tế sau khi nạp.

## 5. Config tree và secret được mount

Config tree phù hợp với container secret hoặc volume chứa các file nhỏ. Mỗi tên file trở thành property name, nội dung file là property value.

Ví dụ Docker Compose:

```yaml
services:
  orders-service:
    image: example/orders-service:1.0
    volumes:
      - ./secrets:/run/secrets:ro
    environment:
      SPRING_CONFIG_IMPORT: "optional:configtree:/run/secrets/"
```

Nếu thư mục có file `orders.db.password`, ứng dụng có thể bind property đó vào cấu hình:

```java
@ConfigurationProperties(prefix = "orders.db")
public record OrdersDatabaseProperties(
        String url,
        String username,
        String password) {
}
```

Trong production, secret nên được cấp từ secret manager hoặc cơ chế secret của nền tảng. Mount read-only giảm khả năng ứng dụng sửa file nguồn. Hạn chế quyền đọc file và tránh log giá trị đã bind. Nếu secret là bắt buộc, bỏ `optional:` để ứng dụng không khởi động khi thiếu thư mục hoặc file cần thiết.

## 6. Thứ tự ưu tiên trong Config Data

Có một số quy tắc nền tảng cần nhớ:

1. Giá trị được import có ưu tiên cao hơn document khai báo `spring.config.import`.
2. Nhiều import được xử lý theo thứ tự khai báo; import đứng sau có thể ghi đè import đứng trước nếu cùng key.
3. Cấu hình profile-specific như `application-prod.yml` được áp dụng theo profile đang hoạt động và có thể ghi đè cấu hình không phụ thuộc profile.
4. Nhiều profile hoạt động có thể cùng đóng góp property source; thứ tự profile có ảnh hưởng khi trùng key.
5. Các nguồn bên ngoài Config Data như command-line arguments, system properties và environment variables có vị trí ưu tiên riêng trong Spring Environment.

Ví dụ cùng key được khai báo ở các nguồn:

```yaml
# classpath:/defaults.yml
orders:
  http:
    read-timeout: 5s
```

```yaml
# file:./config/common.yml
orders:
  http:
    read-timeout: 8s
```

```yaml
# Config Server: orders-service-prod.yml
orders:
  http:
    read-timeout: 10s
```

Nếu chỉ xét hai file đầu trong danh sách import đã nêu, `common.yml` được import sau và có thể thay giá trị của `defaults.yml`. Khi Config Server cũng cung cấp key, giá trị cuối cùng phụ thuộc thêm chính sách remote override. Vì vậy, không nên suy luận giá trị cuối chỉ từ thứ tự dòng trong YAML hoặc vị trí file trong repository.

## 7. Chính sách ưu tiên của remote property source

Spring Cloud Config thường đặt remote property source ở mức ưu tiên cao hơn cấu hình cục bộ của client theo mặc định. Điều này cho phép nhóm vận hành kiểm soát các thuộc tính tập trung. Tuy nhiên, có thể cấu hình server cho phép client override remote property source trong những trường hợp cần thiết.

Các cờ liên quan được đặt trong cấu hình từ xa mà Config Server trả về:

| Thuộc tính | Ý nghĩa khái quát |
| --- | --- |
| `spring.cloud.config.allowOverride` | Cho phép nguồn cục bộ có khả năng ghi đè nguồn từ xa |
| `spring.cloud.config.overrideNone` | Cho phép các nguồn cục bộ đứng trước nguồn từ xa |
| `spring.cloud.config.overrideSystemProperties` | Điều chỉnh phạm vi nguồn hệ thống được phép ghi đè |

Các cờ này có quy tắc chi tiết và phải được cấu hình theo tài liệu của phiên bản Spring Cloud Config đang dùng. Đặc biệt, `allowOverride` phải được đặt ở phía repository cấu hình do server phục vụ; đặt tùy ý ở client không thay đổi được chính sách mà server gửi.

Ví dụ, nếu tổ chức muốn Config Server kiểm soát hoàn toàn timeout production, không bật chính sách cho phép file local ghi đè key đó. Nếu muốn môi trường triển khai có thể override một số thuộc tính, hãy xác định rõ phạm vi key, nguồn được phép override và trách nhiệm phê duyệt. Tránh cho phép ghi đè rộng toàn bộ cấu hình nếu chỉ cần một vài ngoại lệ.

Đây là lớp ưu tiên giữa remote và local property source, tách biệt với thứ tự import giữa các file cục bộ. Khi có sự cố, cần kiểm tra cả hai lớp.

## 8. spring.config.location và spring.config.additional-location

Ngoài `spring.config.import`, Spring Boot còn có hai thuộc tính để chỉ định vị trí cấu hình mặc định:

- `spring.config.location` thay thế các vị trí tìm kiếm mặc định.
- `spring.config.additional-location` bổ sung vị trí mới bên cạnh các vị trí mặc định; cấu hình tại vị trí bổ sung có thể ghi đè cấu hình mặc định.

Ví dụ thêm một thư mục cấu hình bên ngoài:

```bash
SPRING_CONFIG_ADDITIONAL_LOCATION=file:./config/
```

Ví dụ chỉ định tập vị trí riêng:

```bash
SPRING_CONFIG_LOCATION=classpath:/,classpath:/config/,file:./config/
```

Hai thuộc tính này không hoàn toàn tương đương với `spring.config.import`. Import phù hợp khi muốn đưa một nguồn vào ngay trong một document và kiểm soát thứ tự của các nguồn liên quan. `additional-location` bổ sung các vị trí được Spring Boot tìm kiếm theo cơ chế mặc định; `location` thay thế danh sách mặc định nên cần khai báo lại mọi vị trí muốn giữ.

Các location được xử lý theo thứ tự. Khi có nhiều location hoặc profile-specific file cùng khai báo key, location được xử lý sau có thể có ưu tiên cao hơn. Nếu dùng dấu chấm phẩy để tạo location group, các location trong cùng nhóm được xử lý như một nhóm ở cùng mức profile; chỉ dùng khi đã hiểu quy tắc location group của phiên bản Spring Boot đang dùng.

## 9. Nhiều profile và cấu hình theo môi trường

Một ứng dụng có thể hoạt động với nhiều profile:

```yaml
spring:
  profiles:
    active:
      - prod
      - observability
```

Khi các profile cùng khai báo một key, thứ tự profile đang hoạt động có ảnh hưởng đến kết quả. Hãy giới hạn profile vào các nhóm có mục đích rõ ràng. Nếu cần kích hoạt nhiều profile liên quan cùng nhau, profile group có thể giúp biểu diễn một tên môi trường tổng hợp.

Config Server cũng nhận application và profile để chọn các file như `application-prod.yml`, `orders-service-prod.yml`. Client nên xác định profile đủ sớm để Config Data import yêu cầu đúng tập cấu hình từ xa.

Không đặt `spring.profiles.active` hoặc `spring.profiles.default` trong một tài liệu profile-specific đang phụ thuộc vào chính profile đó. Hãy khai báo profile kích hoạt trong cấu hình không phụ thuộc profile, biến môi trường hoặc tham số triển khai.

## 10. Cách kiểm tra giá trị cuối cùng

Khi nhiều nguồn cùng khai báo một key, kiểm tra kết quả trong Environment thay vì chỉ đọc từng file.

Ở Config Server, gọi endpoint Environment:

```bash
curl http://localhost:8888/orders-service/prod/main
```

Response cho biết application, profile, label, revision và property source từ server. Đây là cách xác nhận phần cấu hình tập trung đã được trả về như mong muốn.

Ở client, có thể bật Actuator endpoint `env` và `configprops` trong môi trường kiểm thử để kiểm tra nguồn và bean đã binding. Ví dụ cấu hình expose có kiểm soát:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,env,configprops
```

Sau đó truy cập `/actuator/env/orders.http.read-timeout` hoặc `/actuator/configprops` tùy phiên bản và cấu hình Actuator. Các endpoint này có thể tiết lộ giá trị nhạy cảm; chỉ bật trong môi trường quản trị, bật xác thực và kiểm soát quyền truy cập. Không expose công khai hoặc lưu response chứa secret vào log CI.

Có thể kiểm tra thứ tự bằng một thử nghiệm nhỏ:

1. Đặt cùng một key với các giá trị khác nhau trong hai import.
2. Khởi động ứng dụng với đúng profile cần thử.
3. Kiểm tra Environment và xác định property source đang thắng.
4. Thêm Config Server vào import và lặp lại phép thử.
5. Kiểm tra lại sau khi bật/tắt chính sách remote override.

Bài thử này giúp phát hiện khác biệt do phiên bản Spring Boot/Spring Cloud, profile, thứ tự import hoặc chính sách server.

## 11. Xử lý lỗi khi một nguồn không nạp được

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Ứng dụng dừng khi khởi động | Location bắt buộc không tồn tại hoặc Config Server không truy cập được | Kiểm tra import URI, network, log Config Data |
| Ứng dụng khởi động nhưng thiếu thuộc tính | Nguồn được đánh dấu optional hoặc file không có key | Kiểm tra fallback và validation của cấu hình |
| Giá trị khác mong đợi | Import order, profile hoặc remote override | Kiểm tra Environment và property source |
| Secret không được bind | Tên file config tree không khớp property key hoặc mount sai | Kiểm tra đường dẫn, tên file và quyền đọc |
| Config Server trả đúng nhưng client khác giá trị | Local property source, environment variable hoặc command-line override | Kiểm tra Actuator env và chính sách remote |
| Chỉ production gặp lỗi | Profile production thiếu file hoặc Config Server chọn sai profile/label | Kiểm tra active profiles và endpoint Environment |
| Khởi động thất bại khi server chậm | Không có retry hoặc timeout chưa phù hợp | Cấu hình retry và timeout theo phiên bản Config Client |

Nếu Config Server là nguồn bắt buộc, giữ import không có `optional:` để lỗi được phát hiện sớm. Nếu cần retry khi server tạm thời chưa sẵn sàng, có thể cấu hình retry của Config Client và bổ sung dependency phù hợp theo hướng dẫn phiên bản đang dùng. Không nên dùng optional thay cho một chiến lược retry nếu cấu hình từ xa là điều kiện bắt buộc.

## 12. Nguyên tắc thiết kế nhiều nguồn import

- Chỉ import các nguồn thật sự cần thiết; mỗi nguồn nên có phạm vi sở hữu rõ ràng.
- Dùng classpath cho giá trị mặc định, file bên ngoài cho override theo triển khai, config tree cho secret và Config Server cho cấu hình tập trung.
- Đặt import bắt buộc cho nguồn không thể thiếu; chỉ dùng optional cho nguồn có fallback an toàn.
- Giữ thứ tự import rõ ràng và tránh định nghĩa trùng key giữa các nguồn.
- Phân biệt thứ tự Config Data với chính sách ưu tiên remote property source của Spring Cloud Config.
- Dùng `spring.config.additional-location` khi cần bổ sung vị trí mặc định; dùng `spring.config.location` chỉ khi muốn thay thế danh sách mặc định.
- Kiểm tra Environment và bean cấu hình sau khi binding, nhất là khi nhiều profile đang hoạt động.
- Bảo vệ Actuator và không ghi secret vào log hoặc artifact.
- Ghi nhận profile, label, revision và cấu hình deploy để có thể tái hiện kết quả.

Nạp nhiều nguồn import giúp ứng dụng kết hợp giá trị mặc định, cấu hình theo triển khai, secret và cấu hình tập trung. Muốn kết quả nhất quán, cần thiết kế rõ nguồn nào sở hữu từng key, thứ tự import nào được áp dụng và Config Server có quyền ưu tiên ra sao. Khi kiểm tra bằng Environment và xác thực cấu hình lúc khởi động, nhóm phát triển có thể phát hiện sớm xung đột thay vì để sai khác xuất hiện khi ứng dụng đã nhận lưu lượng.

