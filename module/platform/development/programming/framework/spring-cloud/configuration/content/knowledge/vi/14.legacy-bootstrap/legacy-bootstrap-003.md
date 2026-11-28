# Phân biệt bootstrap.yml, application.yml và spring.config.import

Spring Cloud Config Client có hai cách tích hợp chính qua các thế hệ Spring Boot và Spring Cloud. Cách cũ dùng **bootstrap context** với `bootstrap.yml`; cách hiện đại dùng **Config Data API** qua `spring.config.import=configserver:`. Cả hai đều giúp ứng dụng lấy cấu hình từ Config Server, nhưng khác nhau ở thời điểm nạp, context tham gia, cách khai báo và quy tắc ưu tiên.

Hiểu rõ vai trò của `bootstrap.yml`, `application.yml` và `spring.config.import` rất quan trọng khi duy trì ứng dụng cũ hoặc chuyển sang phiên bản Spring Boot mới. Nếu trộn hai cơ chế mà không có chủ đích, ứng dụng có thể nạp cấu hình hai lần, khó giải thích giá trị thắng hoặc khởi động không giống môi trường mong đợi.

## 1. Hai giai đoạn cấu hình trong kiến trúc cũ

**Bootstrap context** là context khởi tạo sớm của Spring Cloud. Nó chạy trước context chính của Spring Boot, dùng để lấy các thông tin cần thiết nhằm thiết lập ứng dụng, chẳng hạn địa chỉ Config Server, tên application, profile và label.

Trong mô hình legacy, ứng dụng có hai tệp cấu hình thường được nhắc đến:

| Tệp | Context/giai đoạn | Vai trò chính |
| --- | --- | --- |
| `bootstrap.yml` | Bootstrap context, chạy sớm | Cấu hình quá trình bootstrap và kết nối nguồn cấu hình từ xa |
| `application.yml` | Main application context | Cấu hình ứng dụng Spring Boot và các bean nghiệp vụ |

Bootstrap context có thể tạo một parent context cho main application context. Spring Cloud Config Client trong bootstrap context liên hệ Config Server, lấy các property source từ xa rồi đưa chúng vào môi trường cấu hình của ứng dụng.

Ví dụ cấu trúc dự án cũ:

```text
src/main/resources/
├── bootstrap.yml
├── bootstrap-prod.yml
├── application.yml
└── application-prod.yml
```

`bootstrap-prod.yml` có thể bổ sung cấu hình bootstrap khi profile `prod` được kích hoạt. Tương tự, `application-prod.yml` chứa các thuộc tính của main context dành cho profile đó.

## 2. bootstrap.yml dùng để làm gì?

Trong legacy bootstrap, `bootstrap.yml` được nạp sớm để định danh ứng dụng và cấu hình cách kết nối Config Server:

```yaml
spring:
  application:
    name: billing-api
  cloud:
    config:
      uri: http://config-server:8888
      label: release-2026
      profile: prod
```

Các thuộc tính quan trọng:

- `spring.application.name`: tên application mà Config Client yêu cầu.
- `spring.cloud.config.uri`: địa chỉ Config Server.
- `spring.cloud.config.label`: branch, tag hoặc revision được yêu cầu.
- `spring.cloud.config.profile`: profile dùng cho truy vấn Config Server; nếu không đặt riêng, client thường dựa trên profile ứng dụng đang hoạt động.

Bootstrap context cần các giá trị này trước khi main context hoàn tất việc nạp cấu hình. Vì vậy, các thông tin kết nối bootstrap được đặt trong `bootstrap.yml` hoặc được truyền qua biến môi trường/system property có sẵn từ trước khi ứng dụng khởi tạo.

Để dùng cơ chế legacy, dự án cần bật bootstrap support. Ở các dòng Spring Cloud mới hơn, bootstrap context legacy không còn được bật mặc định như các thế hệ cũ. Có thể opt-in bằng dependency `spring-cloud-starter-bootstrap` hoặc bằng thuộc tính hệ thống `spring.cloud.bootstrap.enabled=true` được đặt trước khi Spring Application bắt đầu chạy. Hãy kiểm tra đúng release train đang sử dụng vì cơ chế bootstrap phụ thuộc phiên bản.

## 3. application.yml thuộc main application context

`application.yml` là tệp cấu hình chính của Spring Boot. Nó thường chứa cấu hình server, datasource, logging, feature flag và các thuộc tính dùng bởi bean nghiệp vụ.

Ví dụ:

```yaml
server:
  port: 8081

acme:
  billing:
    connect-timeout: 3s
    retry:
      max-attempts: 4

management:
  endpoints:
    web:
      exposure:
        include: health,info
```

Các thuộc tính này được dùng trong main context, chẳng hạn để cấu hình embedded server, Actuator hoặc bind vào `@ConfigurationProperties`.

Có thể tách phần theo môi trường:

```yaml
# application-prod.yml
acme:
  billing:
    connect-timeout: 5s
```

Khi profile `prod` hoạt động, tài liệu profile-specific có thể ghi đè thuộc tính trong `application.yml` theo quy tắc Config Data của Spring Boot. Các khóa không xuất hiện trong tài liệu profile vẫn được kế thừa từ nguồn có độ ưu tiên thấp hơn.

## 4. Cấu hình từ xa được đưa vào ứng dụng như thế nào trong bootstrap cũ?

Trong legacy mode, Config Client chạy trong bootstrap context để lấy cấu hình từ Config Server. Server trả về một `Environment` gồm metadata và `propertySources`; các nguồn này được thêm vào môi trường cấu hình của ứng dụng.

Ví dụ Config Server có `billing-api-prod.yml`:

```yaml
acme:
  billing:
    connect-timeout: 4s
    currency: VND
```

Trong khi `application.yml` local có:

```yaml
acme:
  billing:
    connect-timeout: 2s
    retry:
      max-attempts: 3
```

Sau khi Config Client nạp nguồn từ xa, ứng dụng có thể nhận `connect-timeout` từ property source remote và vẫn nhận `retry.max-attempts` từ cấu hình local vì remote không khai báo khóa đó. Kết quả cụ thể phụ thuộc thứ tự property source và chính sách override của Spring Cloud Config.

Ở legacy mode, remote property source thường có độ ưu tiên cao. Theo mặc định, cấu hình local không thể ghi đè remote property source. Nếu cần cho phép local override, có thể dùng các thuộc tính như `spring.cloud.config.allowOverride`, `spring.cloud.config.overrideNone` và `spring.cloud.config.overrideSystemProperties` theo quy tắc của phiên bản đang dùng. Các cờ override cần được đặt trong **nguồn cấu hình từ xa** theo hướng dẫn Spring Cloud Config; không nên giả định đặt chúng trong `bootstrap.yml` local sẽ tạo cùng hiệu lực.

## 5. Config Data API và spring.config.import

Từ Spring Boot 2.4, cơ chế Config Data được giới thiệu để chuẩn hóa cách nạp cấu hình từ nhiều location. Spring Cloud Config tích hợp với cơ chế này qua location `configserver:`. Đây là phương thức được ưu tiên cho ứng dụng mới dùng các release train tương thích.

Ví dụ `application.yml` hiện đại:

```yaml
spring:
  application:
    name: billing-api
  config:
    import: "configserver:http://config-server:8888"
  cloud:
    config:
      label: release-2026
```

Khi Spring Boot xử lý Config Data, nó phát hiện location `configserver:`, gọi Config Server và đưa các property source nhận được vào quá trình nạp cấu hình. Không cần bootstrap context legacy chỉ để lấy cấu hình từ xa theo cách này.

Nếu dùng URI mặc định hoặc khai báo URI ở thuộc tính riêng, có thể viết:

```yaml
spring:
  application:
    name: billing-api
  cloud:
    config:
      uri: http://config-server:8888
  config:
    import: "configserver:"
```

Nếu không đặt URI, Config Client thường dùng `http://localhost:8888`. Môi trường triển khai nên khai báo hostname rõ ràng, không phụ thuộc mặc định local.

## 6. Optional và mandatory import

Config Data import có thể là bắt buộc hoặc tùy chọn:

```yaml
spring:
  config:
    import: "configserver:http://config-server:8888"
```

Import bắt buộc khiến ứng dụng khởi động thất bại nếu không thể nạp cấu hình từ xa. Đây là lựa chọn phù hợp khi ứng dụng không thể hoạt động an toàn nếu thiếu cấu hình trung tâm.

Nếu muốn ứng dụng tiếp tục khởi động khi Config Server không khả dụng, thêm tiền tố `optional:`:

```yaml
spring:
  config:
    import: "optional:configserver:http://config-server:8888"
```

Optional không đồng nghĩa mọi lỗi cấu hình đều được bỏ qua. Ứng dụng vẫn có thể thất bại khi validation phát hiện thiếu thuộc tính bắt buộc hoặc khi một giá trị không chuyển đổi được sang kiểu Java. Chỉ dùng optional nếu cấu hình local fallback an toàn và có cảnh báo khi nguồn remote không được nạp.

## 7. So sánh bootstrap.yml và spring.config.import

| Tiêu chí | Legacy bootstrap | Config Data import |
| --- | --- | --- |
| Cơ chế | Bootstrap context riêng chạy trước main context | Spring Boot Config Data loader |
| Cách khai báo | `bootstrap.yml` và bootstrap support | `spring.config.import=configserver:` trong Config Data, thường ở `application.yml` |
| Dependency/kích hoạt | Cần bootstrap support; các release mới thường phải opt-in | `spring-cloud-starter-config` với release train tương thích |
| Thời điểm lấy cấu hình | Trong giai đoạn bootstrap context | Khi Spring Boot xử lý Config Data |
| Optional source | Phụ thuộc cấu hình legacy và phiên bản | Tiền tố `optional:` trên import location |
| Profile-specific | Có thể dùng `bootstrap-{profile}.yml` và profile bootstrap | Config Data profile activation và profile-specific documents |
| Hướng sử dụng | Duy trì ứng dụng cũ hoặc yêu cầu tương thích | Cách tích hợp ưu tiên cho ứng dụng mới trên nền tảng hiện đại |

Hai cơ chế đều có thể đưa cấu hình từ Config Server vào `Environment`, nhưng không nên xem chúng là hai tên gọi cho cùng một tính năng. Chúng dùng cơ chế khởi tạo và vị trí khai báo khác nhau.

## 8. Ví dụ hai cấu hình tương đương

### Cách legacy

`bootstrap.yml`:

```yaml
spring:
  application:
    name: billing-api
  cloud:
    config:
      uri: http://config-server:8888
      profile: prod
      label: release-2026
```

`application.yml`:

```yaml
server:
  port: 8081

acme:
  billing:
    retry:
      max-attempts: 3
```

Ứng dụng phải có bootstrap support được bật để `bootstrap.yml` được xử lý.

### Cách Config Data

`application.yml`:

```yaml
spring:
  application:
    name: billing-api
  profiles:
    active: prod
  cloud:
    config:
      label: release-2026
  config:
    import: "configserver:http://config-server:8888"

server:
  port: 8081

acme:
  billing:
    retry:
      max-attempts: 3
```

Cả hai ví dụ đều định danh `billing-api`, lấy profile `prod` và Git label `release-2026`. Trong cách Config Data, `spring.config.import` xác định nguồn từ xa và các thuộc tính bootstrap được chuyển sang cơ chế Config Data tương ứng.

## 9. Không nên bật cả hai cơ chế một cách vô tình

Nếu dự án vừa thêm `spring-cloud-starter-bootstrap` vừa khai báo `spring.config.import=configserver:`, có thể tồn tại cả bootstrap context và Config Data import. Tùy phiên bản và cách cấu hình, ứng dụng có thể tạo nhiều lần yêu cầu tới Config Server hoặc nạp các property source khó phân biệt.

Các triệu chứng thường gặp:

- Log cho thấy Config Server được gọi nhiều lần khi startup.
- Cùng một khóa xuất hiện trong nhiều property source với tên nguồn khác nhau.
- Giá trị local hoặc remote thắng không giống kỳ vọng.
- Profile được gửi trong bootstrap request khác với profile của Config Data request.
- Ứng dụng hoạt động khác nhau khi bỏ hoặc thêm bootstrap starter.

Khi duy trì legacy mode, giữ bootstrap support và cấu hình bootstrap theo đúng phiên bản. Khi chuyển sang Config Data, hãy có kế hoạch loại bỏ cơ chế bootstrap cũ và xác nhận không còn dependency hoặc cờ kích hoạt legacy không cần thiết.

## 10. Lộ trình chuyển từ bootstrap.yml sang spring.config.import

Khi nâng cấp ứng dụng cũ, không nên chỉ đổi tên `bootstrap.yml` thành `application.yml`. Cần chuyển từng trách nhiệm cấu hình và kiểm tra lại thứ tự nguồn.

1. **Ghi nhận trạng thái hiện tại:** phiên bản Spring Boot, Spring Cloud release train, dependency bootstrap, tên application, profile, label và URI Config Server.
2. **Liệt kê nội dung bootstrap:** tách thuộc tính cần thiết để kết nối Config Server khỏi cấu hình nghiệp vụ của main context.
3. **Chọn release train tương thích:** cập nhật Spring Boot và Spring Cloud theo ma trận tương thích trước khi chuyển cơ chế nạp.
4. **Thêm Config Data import:** khai báo `spring.config.import` và URI trong `application.yml` hoặc location phù hợp.
5. **Chuyển thuộc tính truy vấn:** bảo đảm `spring.application.name`, profile và label được gửi giống với ứng dụng cũ.
6. **Chuyển chính sách optional/fail-fast:** xác định ứng dụng có được khởi động khi Config Server không khả dụng hay không.
7. **Rà soát precedence:** kiểm tra `allowOverride`, `overrideNone`, `overrideSystemProperties` và mọi nguồn local/environment đang tham gia.
8. **Loại bỏ bootstrap support khi không còn dùng:** bỏ dependency hoặc cờ kích hoạt legacy theo kế hoạch đã kiểm chứng.
9. **So sánh response và giá trị cuối cùng:** kiểm tra Config Server `Environment`, client `Environment` và bean `@ConfigurationProperties`.
10. **Kiểm thử các tình huống lỗi:** Config Server offline, sai label, thiếu profile, giá trị không hợp lệ và cấu hình local fallback.

## 11. Chẩn đoán lỗi theo cơ chế nạp

| Hiện tượng | Kiểm tra ở legacy bootstrap | Kiểm tra ở Config Data |
| --- | --- | --- |
| Không gọi Config Server | Bootstrap support chưa được bật, thiếu starter hoặc bootstrap disabled | Thiếu `spring.config.import` hoặc thiếu Config Client starter |
| Gọi sai server | `spring.cloud.config.uri` trong bootstrap context | URI trong import location hoặc `spring.cloud.config.uri` |
| Sai application/profile | Thuộc tính trong bootstrap context và profile kích hoạt sớm | `spring.application.name`, active profiles và Config Client overrides |
| Giá trị remote/local không như mong đợi | Bootstrap remote property source và override flags | Thứ tự Config Data import, profile documents và nguồn ngoài Config Data |
| Ứng dụng chạy khi Config Server lỗi | Chính sách legacy/fail-fast của phiên bản | Có hay không `optional:` trong import |
| Hai request cấu hình lúc startup | Có thể đang bật đồng thời bootstrap và Config Data | Rà soát bootstrap starter/cờ legacy và import location |

Hãy bắt đầu bằng log startup và xác định ứng dụng đang dùng cơ chế nào. Sau đó gọi trực tiếp Config Server với đúng `/{application}/{profile}/{label}` để xác nhận phản hồi. Cuối cùng kiểm tra `Environment` phía client và bean đã bind. Không nên thay đổi nhiều thuộc tính precedence cùng lúc vì sẽ khó xác định nguyên nhân.

## 12. Bảo mật và quản trị cấu hình

Bootstrap configuration thường chứa URI, tên ứng dụng, profile hoặc thông tin xác thực để truy cập Config Server. Config Data import cũng có thể dùng thông tin xác thực. Trong cả hai cơ chế:

- Dùng TLS và xác thực giữa client với Config Server.
- Đưa username, password và token qua biến môi trường hoặc secret manager.
- Không commit bí mật vào `bootstrap.yml`, `application.yml` hoặc Git repository.
- Cấp quyền truy cập tối thiểu cho từng client và bảo vệ endpoint cấu hình.
- Không log toàn bộ `Environment` hoặc giá trị bí mật khi chẩn đoán.
- Ghi nhận application, profile, label và Git revision đã dùng trong mỗi lần phát hành.

Việc chuyển sang Config Data không thay thế các yêu cầu bảo mật này. Nó chỉ thay đổi cơ chế nạp nguồn cấu hình; quyền truy cập và cách quản trị bí mật vẫn phải được thiết kế riêng.

## 13. Checklist chọn và kiểm tra cơ chế

- [ ] Xác định phiên bản Spring Boot và Spring Cloud release train.
- [ ] Xác định ứng dụng đang dùng legacy bootstrap hay Config Data.
- [ ] Nếu dùng legacy, xác nhận bootstrap support được bật đúng cách.
- [ ] Nếu dùng Config Data, xác nhận có `spring-cloud-starter-config` và `spring.config.import`.
- [ ] Xác nhận application, profile, label và URI giống với môi trường mong muốn.
- [ ] Kiểm tra thứ tự remote property source, local profile document và biến môi trường.
- [ ] Chọn optional hay mandatory dựa trên yêu cầu an toàn của ứng dụng.
- [ ] Tránh vô tình bật cả bootstrap context và Config Data import.
- [ ] Bảo vệ credential, TLS, log và endpoint chẩn đoán.
- [ ] Nếu migration, so sánh response Config Server và giá trị cuối cùng trong client trước/sau chuyển đổi.

`bootstrap.yml` thuộc mô hình bootstrap context cũ; `application.yml` là cấu hình của main application context; `spring.config.import=configserver:` là cách Config Data hiện đại yêu cầu cấu hình từ xa. Phân biệt đúng ba thành phần này giúp duy trì ứng dụng Spring Cloud Config cũ, chuyển đổi có kiểm soát và tránh sai lệch thứ tự ưu tiên khi nhiều nguồn cấu hình cùng tồn tại.
