# Trùng khóa giữa nhiều kho và nhiều hệ thống cấu hình

## 1. Vì sao cùng một khóa có nhiều giá trị?

Trong hệ thống dùng Spring Cloud Config, một thuộc tính có thể được khai báo ở nhiều nơi: file cấu hình chung, file riêng của ứng dụng, file theo profile, nhiều Git repository, Vault hoặc backend khác, file local của Spring Boot, biến môi trường và tham số dòng lệnh.

Ví dụ, khóa `payment.timeout` có thể xuất hiện trong:

- `application.yml` của repository dùng chung.
- `payment-service-prod.yml` của repository nhóm Payments.
- Một Git repository khác được ghép bằng composite.
- Vault chứa cấu hình vận hành nhạy cảm.
- `application-prod.yml` đóng gói trong ứng dụng.
- Biến môi trường `PAYMENT_TIMEOUT` do nền tảng triển khai cấp.

Spring không hợp nhất các giá trị trùng khóa thành nhiều giá trị cùng lúc. Khi tạo `Environment`, các property source được sắp xếp theo độ ưu tiên. Nguồn có ưu tiên cao hơn sẽ cung cấp giá trị được dùng khi ứng dụng đọc khóa đó.

Vấn đề quan trọng là có nhiều tầng ưu tiên độc lập. Thứ tự file bên trong một Git repository, thứ tự repository trong composite Config Server, thứ tự các Config Data import và thứ tự property source của Spring Boot là những quy tắc khác nhau. Cần tìm đúng tầng đang có xung đột trước khi sửa.

## 2. Bản đồ các tầng ưu tiên

Khi một client nhận cấu hình từ nhiều nguồn, có thể phân tích theo các tầng sau:

| Tầng | Câu hỏi cần trả lời | Quy tắc cần kiểm tra |
|---|---|---|
| File trong một repository | File chung hay file ứng dụng/profile có giá trị cao hơn? | Quy tắc tìm file và profile của EnvironmentRepository. |
| Nhiều repository ở Config Server | Nguồn Git/Vault/SVN nào được ưu tiên? | Thứ tự composite hoặc thuộc tính `order`. |
| Nhiều tên cấu hình | Các bộ cấu hình được yêu cầu theo `spring.cloud.config.name` theo thứ tự nào? | Tên xuất hiện sau có thể ghi đè tên trước. |
| Nhiều Config Data import ở client | Import nào có ưu tiên cao hơn? | Các location được xử lý theo thứ tự khai báo; import sau có ưu tiên cao hơn. |
| Spring Boot Environment | Remote, file local, biến môi trường và CLI cạnh tranh thế nào? | Thứ tự property source của Spring Boot và cơ chế tích hợp Config Client. |
| Override policy của bootstrap legacy | Client có được phép ghi đè remote property không? | `allow-override`, `override-none`, `override-system-properties` đặt trong remote source. |

Không có một quy tắc duy nhất kiểu “Git luôn thắng” hoặc “biến môi trường luôn thắng” áp dụng giống nhau cho mọi kiến trúc. Trước tiên cần xác định ứng dụng dùng Config Data import hiện đại hay bootstrap context legacy, Config Server dùng composite hay backend đơn, và có bật chính sách override nào.

## 3. Trùng khóa giữa các file trong cùng repository

Với Git, native hoặc SVN EnvironmentRepository, Config Server đọc các file dùng chung và file theo tên application. File theo application có thể ghi đè file dùng chung; file theo profile có ưu tiên cao hơn file mặc định.

Ví dụ client yêu cầu:

```yaml
spring:
  application:
    name: order-service
  profiles:
    active: dev,mysql
```

Trong một search location, thứ tự file từ ưu tiên cao đến thấp theo quy tắc EnvironmentRepository là:

| Ưu tiên | File | Phạm vi |
|---:|---|---|
| 1 | `order-service-mysql.yml` | Riêng order-service, profile `mysql`. |
| 2 | `application-mysql.yml` | Dùng chung, profile `mysql`. |
| 3 | `order-service-dev.yml` | Riêng order-service, profile `dev`. |
| 4 | `application-dev.yml` | Dùng chung, profile `dev`. |
| 5 | `order-service.yml` | Mặc định riêng order-service. |
| 6 | `application.yml` | Mặc định dùng chung. |

Nếu `payment.timeout` xuất hiện trong `application.yml` với giá trị `5s`, trong `order-service.yml` với giá trị `8s`, và trong `order-service-dev.yml` với giá trị `12s`, thì order service ở profile `dev` nhận `12s` từ property source có ưu tiên cao hơn.

Khi kích hoạt nhiều profile, profile được liệt kê sau có thể ghi đè profile đứng trước. Trong ví dụ `dev,mysql`, cấu hình `mysql` có ưu tiên cao hơn `dev` đối với cùng khóa. Hãy xác nhận danh sách profile thực tế mà client gửi; profile có thể được kích hoạt thêm từ cấu hình hoặc từ môi trường triển khai.

## 4. Trùng khóa giữa nhiều repository trong composite

Composite environment repository cho phép Config Server ghép nhiều backend thành một `Environment`. Thứ tự các phần tử trong `spring.cloud.config.server.composite` quyết định ưu tiên: repository được khai báo trước có ưu tiên cao hơn repository khai báo sau.

Ví dụ:

```yaml
spring:
  profiles:
    active: composite
  cloud:
    config:
      server:
        composite:
          - type: git
            uri: ${ORDERS_CONFIG_URI}
          - type: git
            uri: ${PLATFORM_CONFIG_URI}
          - type: vault
            host: ${VAULT_HOST}
            port: 8200
            scheme: https
            backend: secret
```

Với danh sách trên, repository Orders được xét ưu tiên trước Platform, rồi đến Vault. Nếu cùng một khóa có trong nhiều nguồn, nguồn đứng trước có giá trị ưu tiên cao hơn.

Giả sử:

| Repository | `orders.payment-timeout` |
|---|---:|
| Orders Git | `7s` |
| Platform Git | `10s` |
| Vault | `15s` |

Kết quả composite ưu tiên `7s` từ Orders Git. Nếu muốn giá trị nền tảng có quyền ưu tiên cao hơn, phải thay đổi thứ tự danh sách một cách có chủ đích.

Với các backend được kích hoạt bằng profile riêng thay vì profile `composite`, có thể dùng thuộc tính `order`. Giá trị số nhỏ hơn có ưu tiên cao hơn. Ví dụ `vault.order: 1` và `git.order: 2` làm Vault có ưu tiên cao hơn Git.

Composite không phải cơ chế chọn một repository theo application. Nó truy vấn nhiều nguồn cho cùng yêu cầu. Nếu mỗi ứng dụng chỉ cần một repository riêng, Git `repos` theo pattern thường phù hợp hơn composite.

## 5. Trùng khóa giữa các tên cấu hình dùng chung

Config Client có thể yêu cầu nhiều bộ cấu hình bằng `spring.cloud.config.name`, là danh sách tên phân tách bằng dấu phẩy. Điều này hữu ích khi một số dịch vụ cần chia sẻ cấu hình cho một thành phần như Cassandra, Redis hoặc JPA.

Ví dụ:

```yaml
spring:
  application:
    name: order-service
  cloud:
    config:
      name: ${spring.application.name},database,platform
```

Nếu client yêu cầu `order-service,database,platform`, Config Server có thể trả về các file theo từng tên và profile. Tên xuất hiện sau có thể ghi đè giá trị cùng khóa từ tên xuất hiện trước.

Ví dụ thứ tự property source có thể là:

1. `application.properties`
2. `application-prod.properties`
3. `order-service.properties`
4. `order-service-prod.properties`
5. `database.properties`
6. `database-prod.properties`
7. `platform.properties`
8. `platform-prod.properties`

Vì `platform` đứng sau, nó có thể ghi đè khóa đã được khai báo trong `order-service` hoặc `database`. Chỉ thêm một tên cấu hình khi ứng dụng thực sự cần dùng bộ giá trị đó; danh sách dài làm tăng nguy cơ xung đột và khó truy vết.

## 6. Trùng khóa giữa nhiều Config Data import ở client

Với Spring Boot hiện đại, Config Client dùng `spring.config.import`. Có thể khai báo nhiều location, ví dụ một Config Server chính và một nguồn cấu hình bổ sung được hỗ trợ.

Ví dụ minh họa hai Config Server import:

```yaml
spring:
  config:
    import:
      - "configserver:https://config-base.internal"
      - "configserver:https://config-team.internal"
```

Các location được xử lý theo thứ tự khai báo; import sau có ưu tiên cao hơn import trước khi cùng cung cấp một khóa. Với ví dụ trên, giá trị từ `config-team.internal` có thể ghi đè giá trị trùng khóa từ `config-base.internal`.

Một import được xử lý như dữ liệu cấu hình bổ sung và có thể có ưu tiên cao hơn tài liệu đã khai báo import. Các tài liệu profile-specific và các location khác cũng tham gia vào quy tắc Config Data của Spring Boot. Vì vậy, không chỉ nhìn vào thứ tự các dòng YAML; hãy kiểm tra toàn bộ `Environment` sau khi ứng dụng khởi động.

Phân biệt nhiều import với nhiều URL dự phòng trong `spring.cloud.config.uri`:

| Cách khai báo | Mục đích | Hành vi |
|---|---|---|
| Nhiều location trong `spring.config.import` | Nạp nhiều nguồn cấu hình | Các import được xử lý theo thứ tự; import sau có thể ghi đè import trước. |
| Danh sách URL trong `spring.cloud.config.uri` | Tăng khả năng sẵn sàng của Config Server | Client thử các URL theo chiến lược failover; không phải cơ chế ghép mọi server thành một bộ cấu hình. |

Nếu mục tiêu là HA, hãy cấu hình nhiều địa chỉ server theo cơ chế failover. Nếu mục tiêu là hợp nhất nhiều bộ property source, hãy thiết kế composite ở server hoặc nhiều Config Data import với thứ tự rõ ràng.

## 7. Thứ tự property source trong Spring Boot

Sau khi Config Client nạp dữ liệu từ xa, giá trị cuối còn phụ thuộc các property source khác của Spring Boot. Với Spring Boot hiện đại, các nguồn có độ ưu tiên cao hơn có thể ghi đè nguồn cấu hình có độ ưu tiên thấp hơn.

Một số nguồn thường gặp, từ thấp lên cao trong thứ tự phổ biến:

| Nguồn | Ví dụ | Ghi chú |
|---|---|---|
| Default properties | `SpringApplication.setDefaultProperties` | Giá trị dự phòng thấp. |
| `@PropertySource` | Annotation trên cấu hình Java | Được thêm khi context refresh; một số thuộc tính khởi động được đọc trước đó. |
| Config Data | `application.yml`, profile-specific files và các import | Bao gồm cấu hình được nạp qua Config Data. |
| OS environment variables | `PAYMENT_TIMEOUT=20s` | Có thể ghi đè Config Data theo thứ tự Spring Boot. |
| Java system properties | `-Dpayment.timeout=25s` | Có độ ưu tiên cao hơn biến môi trường trong thứ tự chuẩn. |
| `SPRING_APPLICATION_JSON` | JSON truyền qua env/system property | Cung cấp nhiều khóa trong một nguồn. |
| Command-line arguments | `--payment.timeout=30s` | Thường có ưu tiên rất cao. |
| Test property sources | `@TestPropertySource`, `@DynamicPropertySource` | Có thể ghi đè khi chạy test. |

Bảng này mô tả thứ tự property source tiêu chuẩn của Spring Boot; các tích hợp Spring Cloud, bootstrap legacy và cấu hình import có thể thay đổi vị trí hoặc cách remote source tham gia. Cần xác định đúng phiên bản và cơ chế nạp cấu hình đang dùng trước khi kết luận một nguồn sẽ thắng.

## 8. Quyền ghi đè remote properties trong bootstrap legacy

Với Config Client dùng bootstrap context legacy, remote property source mặc định có ưu tiên cao hơn local property source và không thể bị ghi đè cục bộ. Nếu muốn client được phép ghi đè một phần cấu hình remote, remote property source phải cấp quyền.

Đặt trong repository hoặc remote source mà Config Server phân phối:

```yaml
spring:
  cloud:
    config:
      allow-override: true
      override-none: false
      override-system-properties: false
```

Ba thuộc tính có ý nghĩa:

- `spring.cloud.config.allow-override`: remote source cho phép client áp dụng chính sách ghi đè.
- `spring.cloud.config.override-none`: khi `true`, remote source được đặt ở ưu tiên thấp nhất; mọi local source có thể ghi đè.
- `spring.cloud.config.override-system-properties`: khi `false`, system properties, environment variables và command-line arguments được phép ghi đè remote, còn local config files thì không.

Bảng hành vi khi `allow-override=true`:

| `override-none` | `override-system-properties` | Kết quả |
|---|---|---|
| `true` | Bất kỳ | Tất cả local property sources có thể ghi đè remote, gồm file local, env, system và CLI. |
| `false` | `true` | Remote cao hơn local config files; env, system properties và CLI có thể ghi đè remote. |
| `false` | `false` | Env, system properties và CLI có thể ghi đè remote; local config files không thể. |

Các thuộc tính này phải được đặt trong remote property source. Đặt `spring.cloud.config.allow-override=true` trong file local của client không tự cấp quyền ghi đè remote. Cơ chế này thuộc mô hình bootstrap legacy; không nên mặc định áp dụng cùng cách giải thích cho Config Data import hiện đại.

## 9. Config Server overrides là một nguồn riêng

Config Server cho phép người vận hành khai báo các giá trị chung bằng `spring.cloud.config.server.overrides`:

```yaml
spring:
  cloud:
    config:
      server:
        overrides:
          platform.support-url: https://support.example.internal
          platform.region-default: ap-southeast-1
```

Các giá trị này được đưa vào cấu hình mà Config Server cung cấp cho các client. Chúng hữu ích cho giá trị mặc định hoặc thông tin nền tảng mà mọi ứng dụng cần.

Tuy nhiên, đây không phải cơ chế cưỡng chế bảo mật. Một hệ thống cấu hình không thể buộc ứng dụng phải sử dụng một giá trị theo mọi cách; ứng dụng vẫn có thể có nguồn cấu hình hoặc logic riêng làm thay đổi hành vi. Không dùng `server.overrides` để thay thế authorization, policy bảo mật hoặc validation ở ứng dụng.

Nếu cùng khóa xuất hiện trong `server.overrides` và repository, cần kiểm tra vị trí property source thực tế do phiên bản Config Server trả về. Không giả định tên `overrides` đồng nghĩa luôn đứng cao nhất trong mọi kiểu client và mọi cơ chế bootstrap.

## 10. Ví dụ truy vết một khóa bị ghi đè

Giả sử `order-service` chạy với profile `prod` và khóa `payment.timeout` có các giá trị:

| Nguồn | Giá trị | Tầng |
|---|---:|---|
| `application.yml` trong shared Git | `5s` | File chung trong repository. |
| `order-service-prod.yml` trong orders Git | `8s` | File riêng application/profile. |
| Repository thứ hai trong composite | `10s` | Repository ưu tiên thấp hơn trong composite. |
| `application-prod.yml` local | `12s` | Config Data local. |
| Environment variable `PAYMENT_TIMEOUT` | `15s` | OS environment. |
| CLI `--payment.timeout=20s` | `20s` | Command line. |

Không nên cộng các giá trị hoặc chọn giá trị “hợp lý nhất” theo cảm tính. Hãy truy vết:

1. Config Server nhận application/profile/label nào?
2. Các file nào được đọc trong từng repository?
3. Repository nào có ưu tiên cao hơn trong composite?
4. Các Config Data import được xử lý theo thứ tự nào?
5. Ứng dụng dùng Config Data import hay bootstrap legacy?
6. Remote source có cho phép local override không nếu là bootstrap legacy?
7. Có biến môi trường, system property, JSON property hoặc tham số CLI nào đang ghi đè không?
8. Giá trị cuối mà bean bind nhận được là bao nhiêu?

Sau khi kiểm tra, hãy loại bỏ bản khai báo trùng không cần thiết hoặc đặt rõ quy tắc sở hữu. Không giải quyết xung đột bằng cách thêm một bản khai báo thứ sáu ở một nơi khác.

## 11. Công cụ và quy trình chẩn đoán

### Kiểm tra phản hồi Config Server

Gọi endpoint theo application/profile/label:

```text
GET /order-service/prod/release-2026-11
```

Kiểm tra danh sách property source và thứ tự của chúng. Endpoint này giúp xác định xung đột đã xảy ra ngay ở tầng server hay chưa.

### Kiểm tra Environment của client

Trong môi trường phát triển được bảo vệ, có thể dùng Actuator `env` hoặc `configprops` để xem property source và giá trị đã bind. Chỉ expose các endpoint này với xác thực, phân quyền và lọc dữ liệu nhạy cảm. Không đưa token, mật khẩu hoặc giá trị secret vào log/ticket.

### Dùng placeholder để tìm nguồn

Đối với khóa có thể đặt mặc định, có thể dùng placeholder để biểu diễn quan hệ:

```yaml
payment:
  connect-timeout: 3s
  response-timeout: ${payment.connect-timeout}
```

Placeholder chỉ tham chiếu giá trị cuối được resolver tìm thấy theo Environment; nó không giải quyết xung đột về quyền sở hữu. Tránh tạo vòng tham chiếu giữa các khóa hoặc giữa các hệ thống cấu hình.

### Quy trình điều tra

1. Ghi lại khóa, giá trị mong đợi, giá trị thực tế và môi trường đang chạy.
2. Xác định application, profile, label và revision cấu hình của client.
3. Kiểm tra từng property source trong phản hồi Config Server.
4. Kiểm tra thứ tự composite hoặc `order` của backend.
5. Kiểm tra danh sách `spring.cloud.config.name` và các file/profile tương ứng.
6. Kiểm tra `spring.config.import`, các location và thứ tự import.
7. Kiểm tra env, JVM properties, `SPRING_APPLICATION_JSON` và CLI.
8. Với bootstrap legacy, kiểm tra ba thuộc tính override trong remote source.
9. Kiểm tra giá trị cuối được bind vào bean và thêm test cho quy tắc mong muốn.

## 12. Nguyên tắc thiết kế để tránh xung đột

- Mỗi khóa nên có một nguồn sở hữu chính được ghi lại, ví dụ `payment.timeout` do nhóm Payments quản lý.
- Dùng repository chung cho giá trị thực sự dùng chung; không đặt cấu hình nghiệp vụ riêng vào nguồn global.
- Dùng composite khi cần ghép nguồn; dùng routing theo application khi mỗi client chỉ nên đọc một kho riêng.
- Đặt thứ tự ưu tiên có chủ đích và ghi lại trong tài liệu vận hành.
- Hạn chế khai báo lại cùng khóa ở nhiều nơi nếu không có lý do override rõ ràng.
- Tách secret khỏi file Git thông thường và giới hạn phạm vi backend secret theo danh tính client.
- Dùng label cố định hoặc commit SHA cho release cần tái lập.
- Kiểm tra thay đổi cấu hình bằng pull request, schema validation và test cho các khóa quan trọng.
- Ghi log application/profile/label/revision, nhưng không ghi giá trị bí mật.
- Có test khởi động hoặc integration test xác nhận giá trị cuối của những khóa ảnh hưởng đến bảo mật, thanh toán, kết nối và giới hạn tài nguyên.

## 13. Bài thực hành

### Bước 1: Tạo xung đột trong một repository

Đặt `payment.timeout` trong `application.yml`, `order-service.yml` và `order-service-prod.yml`. Gọi endpoint với application `order-service`, profile `prod`.

**Kết quả cần đạt:** xác định file nào có ưu tiên cao nhất trong cùng repository.

### Bước 2: Tạo xung đột giữa hai repository composite

Đặt cùng khóa trong hai Git repository, khai báo chúng theo thứ tự composite và gọi endpoint. Đảo thứ tự hai phần tử rồi so sánh phản hồi.

**Kết quả cần đạt:** chứng minh repository khai báo trước có ưu tiên cao hơn.

### Bước 3: Tạo xung đột giữa các Config Data import

Khai báo hai import trong `spring.config.import`, mỗi nguồn định nghĩa cùng một khóa với giá trị khác nhau. Đổi thứ tự import và quan sát giá trị cuối.

**Kết quả cần đạt:** hiểu import sau có ưu tiên cao hơn import trước.

### Bước 4: Thử biến môi trường và command line

Giữ nguyên cấu hình remote, đặt `PAYMENT_TIMEOUT` rồi chạy ứng dụng với `--payment.timeout=20s`. Kiểm tra giá trị cuối và property source tạo ra nó.

**Kết quả cần đạt:** hiểu tác động của các nguồn ngoài Config Data theo thứ tự Spring Boot.

### Bước 5: Thử bootstrap override policy

Nếu dự án có bootstrap legacy, đặt `allow-override=true` trong remote source và thử từng tổ hợp `override-none`/`override-system-properties`. Không áp dụng bài thử này cho Config Data import nếu chưa xác minh đúng phiên bản và cơ chế.

**Kết quả cần đạt:** giải thích được vì sao quyền ghi đè phải được remote source cấp.

### Bước 6: Viết quy tắc sở hữu khóa

Chọn ba khóa quan trọng, xác định owner, nguồn chính, nguồn override được phép và cách kiểm tra. Thêm test xác nhận giá trị cuối.

**Kết quả cần đạt:** có thể ngăn xung đột cấu hình lặp lại trong quy trình phát hành.

## 14. Tự kiểm tra

1. Vì sao một khóa có thể xuất hiện ở nhiều repository và nhiều property source?
2. Trong một Git repository, file application/profile được ưu tiên thế nào?
3. Trong composite, repository khai báo trước hay sau có ưu tiên cao hơn?
4. Khi dùng nhiều backend profile riêng, thuộc tính `order` được hiểu ra sao?
5. Các tên trong `spring.cloud.config.name` có ảnh hưởng thế nào đến trùng khóa?
6. Nhiều Config Data import khác gì với nhiều URL Config Server dự phòng?
7. Những nguồn nào trong Spring Boot có thể ghi đè Config Data?
8. Vì sao `spring.cloud.config.allow-override` phải được đặt ở remote source trong bootstrap legacy?
9. `override-none` và `override-system-properties` khác nhau như thế nào?
10. Vì sao `server.overrides` không thể thay thế cơ chế bảo mật?
11. Làm thế nào truy ra property source đã tạo ra giá trị cuối của một khóa?

Khi hoàn thành bài thực hành, người học có thể truy vết xung đột từ file cấu hình đến repository, Config Server, Config Data import và Spring Environment; xác định đúng nguồn thắng; và thiết kế quy tắc sở hữu/ghi đè có thể kiểm chứng.

## Tài liệu tham khảo

- [Spring Cloud Config Client](https://docs.spring.io/spring-cloud-config/reference/client.html): nhiều tên cấu hình, Config Data import, nhiều URL và thứ tự property source.
- [Spring Cloud Config – Composite Environment Repositories](https://docs.spring.io/spring-cloud-config/reference/server/environment-repository/composite-repositories.html): thứ tự repository và thuộc tính `order`.
- [Spring Cloud Context – Overriding Remote Properties](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/application-context-services.html#overriding-the-values-of-remote-properties): `allow-override`, `override-none` và `override-system-properties` trong bootstrap.
- [Spring Boot – Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html): thứ tự property source, profile-specific files và Config Data import.
