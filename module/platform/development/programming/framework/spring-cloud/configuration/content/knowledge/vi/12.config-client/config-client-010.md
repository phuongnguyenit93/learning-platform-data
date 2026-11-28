# Tắt Config Client đúng phạm vi và chạy ứng dụng độc lập

## 1. Khi nào cần tắt Config Client?

Trong kiến trúc Spring Cloud Config, một ứng dụng Spring Boot có thể lấy cấu hình từ xa qua Config Server khi khởi động. Tuy nhiên, không phải môi trường nào cũng cần hoặc có thể truy cập Config Server. Một ứng dụng có thể cần chạy độc lập trong các tình huống:

- Developer chạy ứng dụng trên máy cá nhân khi không kết nối VPN hoặc mạng nội bộ.
- Unit test cần khởi động ApplicationContext mà không phụ thuộc Config Server.
- Môi trường CI chạy kiểm thử với cấu hình giả lập hoặc cấu hình riêng của pipeline.
- Một dịch vụ cần chạy tạm thời bằng cấu hình được cấp trực tiếp từ môi trường triển khai.
- Sự cố hạ tầng khiến Config Server không sẵn sàng và nhóm vận hành cần một chế độ chạy dự phòng đã được chuẩn bị.

Chạy độc lập có nghĩa Config Client không thực hiện việc lấy cấu hình từ Config Server. Khi đó, các giá trị cần thiết phải có sẵn từ file cấu hình cục bộ, biến môi trường, system properties, tham số dòng lệnh hoặc secret manager mà ứng dụng truy cập trực tiếp.

Không thể chỉ tắt kết nối rồi kỳ vọng ứng dụng vẫn có đủ cấu hình. Trước khi dùng chế độ độc lập, cần xác định các property bắt buộc, nguồn thay thế của chúng và cách kiểm tra ứng dụng khởi động an toàn.

## 2. Tắt Config Client bằng spring.cloud.config.enabled

Thuộc tính chính để bật/tắt Config Client là:

```yaml
spring:
  cloud:
    config:
      enabled: false
```

Khi thuộc tính này được đặt thành `false` trong cấu hình mà Config Client đọc được đủ sớm, Config Client sẽ không thực hiện việc lấy cấu hình từ Config Server. Ứng dụng vẫn khởi động bằng các nguồn cấu hình khác.

Có thể truyền thuộc tính qua biến môi trường:

```bash
SPRING_CLOUD_CONFIG_ENABLED=false
```

Hoặc tham số dòng lệnh:

```bash
java -jar order-service.jar --spring.cloud.config.enabled=false
```

Biến môi trường và tham số dòng lệnh thường thuận tiện cho CI/container vì không phải sửa file cấu hình đóng gói. Tham số dòng lệnh có độ ưu tiên cao trong Spring Environment, vì vậy có thể dùng để ghi đè giá trị mặc định trong file cấu hình.

Thuộc tính phải được cung cấp ở phía client. Đặt `spring.cloud.config.enabled=false` trong Git repository mà client chỉ có thể đọc thông qua Config Server sẽ không giải quyết được việc bootstrap: client cần biết có tắt Config Client hay không trước khi gọi server để tải repository đó.

## 3. Chỉ tắt Config Client trong một profile

Thông thường, developer vẫn muốn dùng Config Server ở `staging` và `prod`, nhưng chạy độc lập ở `local`. Có thể đặt thuộc tính trong file profile tương ứng:

`application-local.yml`:

```yaml
spring:
  cloud:
    config:
      enabled: false

server:
  port: 8081

logging:
  level:
    root: DEBUG
```

Chạy ứng dụng với profile `local`:

```bash
java -jar order-service.jar --spring.profiles.active=local
```

Ở môi trường khác, profile `staging` hoặc `prod` có thể để Config Client hoạt động theo cấu hình triển khai. Hãy bảo đảm chỉ profile dự kiến mới chứa `enabled: false`; không đặt thuộc tính này ở file chung nếu các môi trường khác vẫn cần Config Server.

### Tổ chức import theo profile

Một cách rõ ràng hơn là chỉ khai báo Config Data import trong tài liệu cấu hình được kích hoạt bởi profile dành cho remote config:

```yaml
spring:
  application:
    name: order-service

---
spring:
  config:
    activate:
      on-profile: cloud-config
    import: "configserver:${CONFIG_SERVER_URI}"
```

Khi chạy với profile `cloud-config`, client thực hiện import từ Config Server. Khi chạy profile `local`, tài liệu có điều kiện này không được kích hoạt, vì vậy ứng dụng có thể dùng cấu hình cục bộ mà không cần import remote.

Ví dụ chạy độc lập:

```bash
java -jar order-service.jar --spring.profiles.active=local
```

Ví dụ chạy với cấu hình tập trung:

```bash
java -jar order-service.jar --spring.profiles.active=cloud-config,prod
```

Khi sử dụng nhiều profile cùng lúc, hãy kiểm tra thứ tự và cách kết hợp các tài liệu cấu hình theo quy tắc Spring Boot. Đặc biệt, không kích hoạt đồng thời profile local và profile remote nếu chính sách của ứng dụng không cho phép cả hai nguồn cùng tham gia.

## 4. Phân biệt tắt Config Client với optional Config Server import

Hai cấu hình sau giải quyết hai vấn đề khác nhau.

| Cấu hình | Hành vi | Có gọi Config Server không? |
|---|---|---|
| `spring.cloud.config.enabled=false` | Tắt Config Client. | Không thực hiện lấy cấu hình qua Config Client. |
| `spring.config.import=optional:configserver:...` | Vẫn thử lấy cấu hình; nếu Config Server không sẵn sàng thì cho phép ứng dụng tiếp tục khởi động. | Có, client vẫn thử kết nối. |

Ví dụ import tùy chọn:

```yaml
spring:
  config:
    import: "optional:configserver:http://localhost:8888"
```

`optional:` phù hợp khi ứng dụng có thể hoạt động bằng cấu hình dự phòng nếu Config Server tạm thời không truy cập được. Nếu Config Server đang hoạt động, client vẫn có thể lấy cấu hình từ xa. Vì vậy, `optional:` không phải cách tắt Config Client.

Ngược lại, nếu yêu cầu ứng dụng phải có cấu hình tập trung mới được khởi động, dùng import bắt buộc:

```yaml
spring:
  config:
    import: "configserver:http://config-server:8888"
```

Khi server không truy cập được, quá trình khởi động sẽ thất bại để tránh chạy với cấu hình thiếu. Quyết định dùng import bắt buộc hay tùy chọn phải dựa trên mức độ an toàn của cấu hình dự phòng.

## 5. Không nhầm import-check với việc tắt Config Client

Spring Cloud Config có thuộc tính:

```yaml
spring:
  cloud:
    config:
      import-check:
        enabled: false
```

Thuộc tính `spring.cloud.config.import-check.enabled=false` tắt bước kiểm tra liên quan đến việc khai báo Config Server import. Nó không phải công tắc chung để ngăn Config Client lấy cấu hình. Nếu `spring.config.import` vẫn chứa `configserver:`, client vẫn có thể thực hiện import.

Chỉ dùng import-check khi có lý do cụ thể liên quan đến cách tổ chức bootstrap hoặc tích hợp cấu hình của dự án. Không dùng nó thay cho `spring.cloud.config.enabled=false` khi mục tiêu là chạy độc lập.

## 6. Cấu hình local phải đủ để ứng dụng hoạt động

Khi tắt Config Client, các property từ Git hoặc backend khác sẽ không được nạp. Vì vậy, ứng dụng cần có cấu hình thay thế cho các thành phần thiết yếu.

Ví dụ `application-local.yml`:

```yaml
spring:
  cloud:
    config:
      enabled: false
  datasource:
    url: ${LOCAL_DB_URL:jdbc:postgresql://localhost:5432/orders}
    username: ${LOCAL_DB_USER:orders_dev}
    password: ${LOCAL_DB_PASSWORD}

orders:
  reservation-timeout: 10s
  max-items-per-request: 20

payment:
  provider: sandbox
```

Các giá trị mặc định trong ví dụ chỉ dành cho môi trường local. Mật khẩu database vẫn được cấp qua biến môi trường hoặc secret store; không đặt secret production trong file local được commit.

Nên kiểm tra cấu hình bằng `@ConfigurationProperties` và validation để phát hiện thiếu giá trị bắt buộc ngay khi khởi động:

```java
@Validated
@ConfigurationProperties(prefix = "orders")
public record OrdersProperties(
        @NotNull Duration reservationTimeout,
        @Min(1) int maxItemsPerRequest) {
}
```

Nếu ứng dụng không có cấu hình `orders.reservation-timeout` hoặc `orders.max-items-per-request` hợp lệ, validation sẽ giúp lỗi xuất hiện sớm thay vì để dịch vụ chạy với trạng thái không mong muốn.

Không nên sao chép toàn bộ cấu hình production vào file local. Chỉ cung cấp các giá trị cần cho tác vụ phát triển, dùng sandbox/test endpoint và giới hạn quyền truy cập dữ liệu.

## 7. Tắt Config Client qua môi trường triển khai

Trong container, có thể đặt biến môi trường:

```yaml
services:
  order-service:
    image: example/order-service:1.0.0
    environment:
      SPRING_PROFILES_ACTIVE: local
      SPRING_CLOUD_CONFIG_ENABLED: "false"
      LOCAL_DB_URL: jdbc:postgresql://db:5432/orders
      LOCAL_DB_USER: orders_dev
```

Trong Kubernetes, biến môi trường tương ứng có thể được đặt trong Deployment hoặc lấy từ ConfigMap/Secret theo chính sách của cluster. Không đưa mật khẩu hoặc token trực tiếp vào manifest được commit nếu repository không được bảo vệ như secret store.

Nếu cùng một image được dùng cho nhiều môi trường, việc điều khiển bằng biến môi trường hoặc profile giúp tránh phải build image riêng cho local và production. Cần kiểm soát pipeline để không vô tình truyền `SPRING_CLOUD_CONFIG_ENABLED=false` vào production khi dịch vụ bắt buộc dùng cấu hình tập trung.

## 8. Trường hợp dự án dùng bootstrap legacy

Các dự án Spring Cloud Config đời cũ có thể sử dụng bootstrap context với `bootstrap.yml` và dependency `spring-cloud-starter-bootstrap`. Trong mô hình này, Config Client có thể được khởi tạo trước ApplicationContext chính.

Nếu dự án đang dùng bootstrap legacy, thuộc tính tắt client cần có mặt trong nguồn cấu hình được bootstrap context đọc, chẳng hạn `bootstrap.yml`, biến môi trường hoặc system property:

```yaml
spring:
  cloud:
    config:
      enabled: false
```

Không chỉ đặt thuộc tính trong một file mà bootstrap context chưa đọc tới. Nếu property chỉ xuất hiện sau khi Config Client đã bắt đầu lấy cấu hình, nó đến quá muộn để ngăn request ban đầu.

`spring.cloud.bootstrap.enabled=false` là một công tắc rộng hơn, có thể tắt bootstrap context và ảnh hưởng đến các bootstrap property source hoặc tích hợp khác. Chỉ dùng khi muốn thay đổi toàn bộ cơ chế bootstrap legacy và đã đánh giá tác động; không coi nó là alias của `spring.cloud.config.enabled=false`.

Với Spring Boot hỗ trợ Config Data, nên ưu tiên cơ chế `spring.config.import` và tránh trộn bootstrap legacy với Config Data nếu không có yêu cầu tương thích cụ thể.

## 9. Tắt Config Client khác với tắt Config Server

Một ứng dụng có thể chứa Config Client, Config Server hoặc cả hai vai trò. Cần đặt công tắc đúng phía:

| Thành phần | Cách điều khiển | Phạm vi |
|---|---|---|
| Config Client | `spring.cloud.config.enabled=false` | Ngăn ứng dụng lấy cấu hình từ xa qua Config Client. |
| Config Server | Dependency `spring-cloud-config-server` và `@EnableConfigServer` | Bật endpoint cung cấp cấu hình cho client khác. |
| Config Data import | `spring.config.import` có hoặc không có `configserver:` | Khai báo nguồn cấu hình từ xa cho client. |
| Import check | `spring.cloud.config.import-check.enabled` | Kiểm soát bước kiểm tra import, không phải cơ chế tắt client. |

Nếu ứng dụng chỉ là client, tắt Config Client không làm Config Server ở hệ thống khác dừng hoạt động. Nếu cùng một tiến trình vừa có `@EnableConfigServer` vừa có chức năng client, cần kiểm tra riêng hai vai trò: tắt client không đồng nghĩa gỡ endpoint server.

## 10. Hành vi khi chạy độc lập và những gì thay đổi

Khi Config Client bị tắt:

- Ứng dụng không lấy các property source mới từ Config Server trong quá trình khởi động.
- Thay đổi trên Git không tự xuất hiện trong ứng dụng đang chạy.
- Refresh qua Config Client hoặc Spring Cloud Bus không thể cập nhật các giá trị remote mà client không nạp.
- Giá trị được dùng đến từ file local, biến môi trường, system properties, tham số dòng lệnh và các nguồn cấu hình còn lại.
- Các thành phần yêu cầu cấu hình từ xa có thể không hoạt động nếu chưa có nguồn thay thế.

Vì vậy, chế độ độc lập thường phù hợp cho phát triển, kiểm thử hoặc tình huống vận hành dự phòng có giới hạn. Nếu chạy production dài hạn mà không dùng Config Server, cần có quy trình quản lý cấu hình thay thế, audit, phân phối secret và phát hành thay đổi tương đương.

## 11. Xác minh ứng dụng thực sự chạy độc lập

Không chỉ nhìn thấy ứng dụng khởi động thành công. Hãy xác minh Config Client đã ngừng gọi Config Server.

Các bước kiểm tra:

1. Xác nhận profile thực tế, ví dụ `local`.
2. Kiểm tra `spring.cloud.config.enabled=false` được nạp từ nguồn cấu hình local hoặc môi trường triển khai.
3. Kiểm tra không có import `configserver:` đang được kích hoạt ngoài dự kiến.
4. Khởi động ứng dụng khi Config Server không truy cập được; ứng dụng phải sử dụng được cấu hình local đã chuẩn bị.
5. Kiểm tra log khởi động để xác nhận không có lần lấy cấu hình từ xa.
6. Kiểm tra access log/metric của Config Server nếu có quyền, xác nhận không xuất hiện request từ client đó.
7. Kiểm tra các property bắt buộc đã bind đúng vào `@ConfigurationProperties`.
8. Thử một luồng nghiệp vụ cơ bản để xác nhận cấu hình local đủ dùng.

Nếu cần xem `Environment` qua Actuator, chỉ expose endpoint trong môi trường kiểm thử được bảo vệ. Endpoint `env` hoặc `configprops` có thể làm lộ dữ liệu nhạy cảm; không bật công khai và không chia sẻ phản hồi chưa lọc.

## 12. Lỗi thường gặp

| Triệu chứng | Nguyên nhân cần kiểm tra | Cách xử lý |
|---|---|---|
| Ứng dụng vẫn gọi Config Server | `enabled=false` không được nạp đủ sớm, profile local không active hoặc một import khác vẫn được kích hoạt. | Kiểm tra profile, nguồn property và các tài liệu `spring.config.import`. |
| Ứng dụng khởi động được khi server mất kết nối nhưng vẫn có request remote | Đang dùng `optional:configserver:`. | Dùng `spring.cloud.config.enabled=false` hoặc bỏ import remote khỏi profile độc lập. |
| Đã đặt `import-check.enabled=false` nhưng client vẫn kết nối | Import check chỉ tắt bước kiểm tra, không tắt Config Client. | Đặt `spring.cloud.config.enabled=false`. |
| Ứng dụng khởi động nhưng lỗi khi gọi nghiệp vụ | Property vốn đến từ Git không có giá trị thay thế local. | Bổ sung cấu hình local tối thiểu và validation cho khóa bắt buộc. |
| Local profile hoạt động nhưng CI vẫn gọi server | Pipeline đang kích hoạt profile khác hoặc truyền URI/import riêng. | Kiểm tra biến môi trường và tham số dòng lệnh của job CI. |
| Legacy bootstrap vẫn gọi server | Thuộc tính disable chỉ nằm trong nguồn cấu hình được nạp sau bootstrap. | Đặt thuộc tính trong bootstrap source hoặc environment/system property được đọc sớm. |
| Tắt client nhưng endpoint Config Server vẫn chạy | Ứng dụng cũng bật `@EnableConfigServer`; đây là vai trò độc lập. | Nếu muốn dừng server, thay đổi dependency/annotation hoặc cấu hình triển khai của server riêng. |

## 13. Bài thực hành

### Bước 1: Chạy ứng dụng với Config Client

Khai báo `spring.config.import: configserver:http://localhost:8888`, khởi động Config Server và client. Ghi nhận một property nhận từ Git.

**Kết quả cần đạt:** xác nhận client có thể lấy cấu hình tập trung.

### Bước 2: Tạo profile local

Tạo `application-local.yml`, đặt `spring.cloud.config.enabled: false` và cung cấp giá trị local cho các property bắt buộc. Khởi động với profile `local`.

**Kết quả cần đạt:** ứng dụng chạy bằng cấu hình local mà không phụ thuộc Config Server.

### Bước 3: So sánh optional import

Đổi sang `optional:configserver:` nhưng không tắt client. Tạm thời làm Config Server không truy cập được và quan sát ứng dụng khởi động. Sau đó bật server lại và quan sát client vẫn lấy cấu hình từ xa.

**Kết quả cần đạt:** phân biệt được optional import với việc tắt Config Client.

### Bước 4: Thử điều khiển bằng biến môi trường

Đặt `SPRING_CLOUD_CONFIG_ENABLED=false` khi chạy container hoặc job kiểm thử. Xác nhận profile và giá trị local được nạp như mong muốn.

**Kết quả cần đạt:** biết cách tắt client theo từng môi trường mà không sửa image.

### Bước 5: Kiểm tra nguồn cấu hình bắt buộc

Tắt Config Client rồi cố ý bỏ một property cần thiết. Bổ sung validation để ứng dụng báo lỗi rõ ràng. Sau đó cấp property từ biến môi trường và xác nhận ứng dụng khởi động.

**Kết quả cần đạt:** hiểu rằng chạy độc lập cần có nguồn thay thế và kiểm tra tính đầy đủ của cấu hình.

## 14. Tự kiểm tra

1. `spring.cloud.config.enabled=false` có tác dụng gì?
2. Vì sao phải đặt thuộc tính disable ở nguồn cấu hình mà client đọc được trước khi kết nối Config Server?
3. `optional:configserver:` khác gì với tắt Config Client?
4. `spring.cloud.config.import-check.enabled=false` có tắt việc lấy cấu hình không?
5. Có thể chỉ tắt Config Client trong profile `local` như thế nào?
6. Với dự án bootstrap legacy, cần đặt thuộc tính disable ở đâu?
7. Vì sao `spring.cloud.bootstrap.enabled=false` có phạm vi rộng hơn?
8. Khi Config Client tắt, các property source remote và refresh qua Bus thay đổi thế nào?
9. Cần kiểm tra gì để xác nhận ứng dụng thật sự chạy độc lập?
10. Vì sao cấu hình local cần validation cho các property bắt buộc?

Khi hoàn thành bài thực hành, người học có thể tắt Config Client theo đúng môi trường, phân biệt việc tắt client với import tùy chọn hoặc tắt import check, chuẩn bị cấu hình thay thế và xác minh ứng dụng Spring Boot có thể chạy độc lập.
