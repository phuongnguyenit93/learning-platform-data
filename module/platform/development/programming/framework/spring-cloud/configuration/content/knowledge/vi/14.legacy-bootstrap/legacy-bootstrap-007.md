# Chuyển sang Config Data mà không nạp trùng nguồn cấu hình

Spring Cloud Config từng dùng bootstrap context để lấy cấu hình từ xa trước khi tạo `ApplicationContext` chính. Từ Spring Boot 2.4, cách tích hợp mặc định là Config Data API thông qua `spring.config.import`. Chuyển đổi giúp ứng dụng dùng cơ chế nạp cấu hình thống nhất của Spring Boot, nhưng cần làm rõ cơ chế cũ đã được tắt hay chưa, địa chỉ Config Server được khai báo ở đâu và các property source nào đang được nạp.

Mục tiêu của migration là để mỗi ứng dụng có một luồng kết nối Config Server được kiểm soát rõ ràng, giữ nguyên giá trị cấu hình hiệu lực và không vô tình kích hoạt đồng thời bootstrap legacy với Config Data. Cũng cần phân biệt việc gọi Config Server nhiều lần trong quá trình Config Data resolution với việc nạp trùng cùng một nguồn: hai hiện tượng này không giống nhau.

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích sự khác nhau giữa bootstrap context và Config Data API.
- Kiểm kê dependency, file bootstrap, biến môi trường và tham số JVM đang bật cơ chế cũ.
- Chuyển cấu hình kết nối sang `spring.config.import`.
- Loại bỏ cấu hình bootstrap legacy khỏi Config Client mà không làm mất các thiết lập cần thiết.
- Nhận biết nhiều request hợp lệ khi Config Data tải `default` rồi tải các profile đang hoạt động.
- Phân biệt property source layering bình thường với việc cùng một Config Server được cấu hình qua hai cơ chế.
- Kiểm tra giá trị hiệu lực, thứ tự ưu tiên, log và rollback sau migration.

## Hai cơ chế nạp cấu hình

### Bootstrap legacy

Trong cơ chế cũ, ứng dụng bật bootstrap context bằng `spring-cloud-starter-bootstrap` hoặc bằng system property/environment variable `spring.cloud.bootstrap.enabled=true`. Spring Cloud Config Client đọc các thiết lập kết nối trong bootstrap configuration, thường là `bootstrap.yml`, rồi gọi Config Server và thêm remote property source vào Spring `Environment` trước khi khởi tạo context chính.

Ví dụ `bootstrap.yml` cũ:

```yaml
spring:
  application:
    name: order-service
  cloud:
    config:
      uri: https://config.internal.example
      name: order-service
      profile: prod
      label: release-2026.11
      fail-fast: true
```

Ứng dụng cần dependency bootstrap để cơ chế này được kích hoạt. `spring.cloud.config.uri` chỉ định Config Server; `name`, `profile` và `label` xác định bộ cấu hình cần lấy.

### Config Data API

Config Data API được Spring Boot giới thiệu từ 2.4 và là cách mặc định để kết nối Config Server trong các phiên bản hiện đại. Ứng dụng khai báo location `configserver:` bằng `spring.config.import` trong `application.yml` hoặc file cấu hình được nạp sớm.

```yaml
spring:
  application:
    name: order-service
  config:
    import: "configserver:https://config.internal.example"
  cloud:
    config:
      label: release-2026.11
```

Không cần `bootstrap.yml` cho luồng Config Data. Nếu import có URL, URL đó được ưu tiên hơn `spring.cloud.config.uri`; vì vậy nên chọn một nơi khai báo địa chỉ để tránh nhầm lẫn khi vận hành.

| Nội dung | Bootstrap legacy | Config Data API |
|---|---|---|
| Cơ chế khởi tạo | Bootstrap context | Spring Boot Config Data |
| Điểm khai báo kết nối | `spring.cloud.config.uri` trong bootstrap properties | `spring.config.import=configserver:...` |
| File thường dùng | `bootstrap.yml` / `bootstrap.properties` | `application.yml` / `application.properties` |
| Kích hoạt | `spring-cloud-starter-bootstrap` hoặc `spring.cloud.bootstrap.enabled=true` | Config Data import và Config Client trên classpath |
| Fail-fast | `spring.cloud.config.fail-fast=true` | Bỏ `optional:` khỏi import; khi dùng retry, cấu hình fail-fast theo hướng dẫn client |

## Vì sao có thể thấy request nhiều lần mà không phải nạp trùng?

Config Data resolution của Spring Boot diễn ra theo hai giai đoạn. Đầu tiên, client lấy cấu hình với profile `default` để có thể phát hiện cấu hình từ xa kích hoạt thêm profile. Sau khi Spring Boot xác định các profile đang hoạt động, client tiếp tục lấy cấu hình cho các profile đó.

Ví dụ, ứng dụng có profile `prod` có thể tạo request cho `order-service/default` rồi request tiếp cho `order-service/prod`. Đây là hành vi bình thường của Config Data API. Cơ chế bootstrap cũ thường chỉ thực hiện một lượt lấy cấu hình sớm hơn, nhưng không có cùng khả năng kích hoạt profile từ dữ liệu Config Server trong giai đoạn Config Data.

Spring Boot cũng quy định một import location chỉ được import một lần dù được khai báo ở nhiều nơi. Do đó, việc thấy một import giống nhau trong nhiều tài liệu cấu hình không tự động có nghĩa location đó bị tải lặp. Tuy vậy, khai báo cả bootstrap legacy và Config Data có thể tạo hai luồng khởi tạo Config Client riêng biệt. Hãy kiểm tra cơ chế đang hoạt động và property source thực tế, thay vì chỉ đếm số dòng log HTTP.

## Kiểm kê trước khi chuyển đổi

Trước khi sửa file, ghi lại cấu hình hiện tại của từng ứng dụng:

- Dependency `spring-cloud-starter-config` và `spring-cloud-starter-bootstrap` trong Maven/Gradle.
- `bootstrap.yml`, `bootstrap.properties` và các file bootstrap theo profile.
- Các thuộc tính `spring.cloud.config.uri`, `name`, `profile`, `label`, `fail-fast`, `retry`, `username`, `password`, `discovery` và các thiết lập liên quan.
- Biến môi trường như `SPRING_CLOUD_BOOTSTRAP_ENABLED`, `SPRING_CLOUD_CONFIG_URI` và các biến credential.
- System properties JVM, command-line arguments, Helm values, manifest Kubernetes và cấu hình của nền tảng triển khai.
- Profile thực tế đang hoạt động và các property source remote/local mà ứng dụng nhận được.

Đặc biệt, `spring.cloud.bootstrap.enabled=true` phải được đặt bằng system property hoặc environment variable để bật bootstrap theo tài liệu Spring Cloud. Vì vậy, chỉ xóa file `bootstrap.yml` chưa chắc đã tắt cơ chế cũ nếu biến môi trường, JVM option hoặc starter vẫn còn.

Nên lưu lại giá trị hiệu lực trước migration cho các thuộc tính quan trọng như datasource URL, broker address, timeout, feature flag và endpoint dịch vụ phụ thuộc. Không sao chép mật khẩu hay token vào tài liệu kiểm kê; chỉ ghi nhận tên nguồn cấp secret.

## Chuyển từng bước sang Config Data

### 1. Giữ Config Client và kiểm tra phiên bản

Ứng dụng vẫn cần `spring-cloud-starter-config`. Dependency này cung cấp Config Client cho cả luồng Config Data và bootstrap legacy. Kiểm tra Spring Boot/Spring Cloud release train tương thích trước khi thay đổi; Config Data API yêu cầu nền tảng Spring Boot hỗ trợ cơ chế này.

Nếu không còn thành phần nào khác cần bootstrap context, loại `spring-cloud-starter-bootstrap` khỏi module. Nếu dependency đó đang được dùng bởi một integration legacy khác, cần rà soát integration đó riêng và xác nhận Config Client không còn bị bootstrap kích hoạt ngoài ý muốn.

Ví dụ dependency Maven sau migration:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-config</artifactId>
    </dependency>
</dependencies>
```

Giữ BOM Spring Cloud tương thích với Spring Boot. Không thêm một phiên bản Config Client riêng lẻ chỉ để chuyển sang Config Data.

### 2. Chuyển thông tin kết nối vào `application.yml`

Đưa tên ứng dụng và địa chỉ Config Server sang cấu hình được Spring Boot nạp sớm:

```yaml
spring:
  application:
    name: order-service
  config:
    import: "configserver:https://config.internal.example"
  cloud:
    config:
      label: release-2026.11
```

Nếu dùng URL mặc định `http://localhost:8888`, có thể viết `configserver:` mà không kèm host. Nếu chọn khai báo URL trong import, bỏ `spring.cloud.config.uri` trùng lặp để tránh hai nơi cùng biểu diễn endpoint. Khi URL nằm trong import, nó có ưu tiên cao hơn `spring.cloud.config.uri`.

Các thuộc tính xác thực, retry, timeout, discovery và label cần được chuyển sang vị trí phù hợp với Config Data theo đúng phiên bản. Credential phải được cấp từ biến môi trường, secret manager hoặc cơ chế bảo mật của nền tảng; không đưa token vào URL hay file cấu hình được commit.

### 3. Chọn import bắt buộc hoặc tùy chọn

Import bắt buộc:

```yaml
spring:
  config:
    import: "configserver:https://config.internal.example"
```

Nếu Config Server không thể truy cập, ứng dụng không hoàn tất quá trình nạp cấu hình và startup thất bại. Đây là lựa chọn phù hợp khi các giá trị từ xa là điều kiện bắt buộc để ứng dụng chạy đúng.

Import tùy chọn:

```yaml
spring:
  config:
    import: "optional:configserver:https://config.internal.example"
```

Tiền tố `optional:` cho phép ứng dụng tiếp tục khi Config Server không truy cập được. Chỉ dùng khi cấu hình cục bộ có đầy đủ giá trị an toàn và việc bỏ qua remote config không làm dịch vụ kết nối sai môi trường hoặc vi phạm yêu cầu nghiệp vụ.

### 4. Giữ profile và label nhất quán

Profile cần được kích hoạt từ nguồn phù hợp như environment variable, JVM argument hoặc cấu hình chung của ứng dụng:

```yaml
spring:
  profiles:
    active: prod
```

Không đặt `spring.profiles.active` trong một tài liệu cấu hình chỉ dành cho profile, ví dụ `application-prod.yml`; Spring Boot yêu cầu thuộc tính kích hoạt profile nằm trong tài liệu không đặc thù profile. Config Data có thể thực hiện lượt lấy `default` rồi mới lấy profile đang hoạt động để hỗ trợ profile được kích hoạt từ cấu hình từ xa.

Label có thể giữ trong `spring.cloud.config.label` hoặc theo cách khai báo được phiên bản client hỗ trợ. Hãy bảo đảm label trỏ đến cùng branch/tag/commit mà ứng dụng đã dùng trước migration.

### 5. Tắt luồng bootstrap cũ

Sau khi Config Data import hoạt động, loại bỏ các yếu tố kích hoạt bootstrap legacy nếu không còn cần:

- Gỡ `spring-cloud-starter-bootstrap` khỏi dependency graph khi không còn integration nào cần nó.
- Bỏ `SPRING_CLOUD_BOOTSTRAP_ENABLED=true` khỏi môi trường triển khai.
- Bỏ `-Dspring.cloud.bootstrap.enabled=true` khỏi JVM options.
- Xóa hoặc di chuyển các khai báo Config Client khỏi `bootstrap.yml` và `bootstrap.properties` sau khi đã chuyển đầy đủ giá trị cần thiết.
- Loại bỏ các file bootstrap theo profile nếu không còn thành phần legacy nào sử dụng.

Nếu giữ một file bootstrap vì một integration khác, đừng để trong đó còn cấu hình kết nối Config Client cũ. Kiểm thử riêng integration đó để chắc chắn việc giữ bootstrap không vô tình bật thêm một lần lấy cấu hình từ Config Server.

### 6. Loại bỏ khai báo trùng và cấu hình cũ

Tìm các vị trí khai báo Config Server trong application files, profile files, biến môi trường và tham số JVM. Với một client migration hoàn chỉnh, chỉ duy trì một cơ chế kết nối rõ ràng.

Tránh các trường hợp sau:

```yaml
# Không duy trì cả hai kiểu khai báo như một cấu hình migration cuối cùng
spring:
  config:
    import: "configserver:https://config.internal.example"
  cloud:
    config:
      uri: https://old-config.internal.example
```

Trong ví dụ này, URL nhúng trong `spring.config.import` được ưu tiên hơn `spring.cloud.config.uri`; giá trị cũ có thể gây nhầm lẫn khi điều tra. Hãy giữ một endpoint có chủ đích.

Không chép các giá trị remote đã có trong Config Server vào `application.yml` chỉ để “phòng hờ”. Việc đó tạo hai nguồn quản lý cùng một khóa và khiến nhóm khó xác định nguồn nào là chuẩn. Chỉ giữ local default khi nó được thiết kế rõ ràng và phù hợp với chính sách optional/fallback.

## Phân biệt property source layering với nạp trùng

Config Server có thể tổng hợp nhiều file như `application.yml`, `application-prod.yml`, `order-service.yml` và `order-service-prod.yml`. Nhiều `PropertySource` cùng xuất hiện là điều bình thường: các file chung, file theo ứng dụng và file theo profile tạo thành lớp cấu hình có thứ tự ưu tiên.

Ngoài ra, Spring Boot có quy tắc precedence giữa các nguồn local và Config Data import. Nội dung được import được đặt ngay dưới tài liệu khai báo import trong thứ tự xử lý Config Data, nên có thể ghi đè giá trị trong tài liệu khai báo import. Thứ tự ưu tiên bên trong các property source do Config Server trả về lại phụ thuộc cách server tổng hợp backend và các thiết lập override của Spring Cloud Config.

| Hiện tượng | Bình thường hay cần điều tra? | Cách xác minh |
|---|---|---|
| Một request cho profile `default`, tiếp theo là request cho `prod` | Bình thường với Config Data hai giai đoạn | Đối chiếu log request và profile được yêu cầu |
| Nhiều property source từ `application.yml` và `order-service-prod.yml` | Bình thường, đây là cấu hình phân lớp | Xem tên property source và thứ tự trong phản hồi Config Server |
| Cùng một location `configserver:` được khai báo lặp trong Config Data | Spring Boot chỉ import một location một lần | Kiểm tra location thực tế và log Config Data |
| Bootstrap legacy và Config Data đều đang bật | Cần xử lý | Kiểm tra bootstrap starter, cờ bootstrap và log Config Client |
| Hai endpoint Config Server khác nhau cùng được khai báo | Cần xác định có chủ đích hay không | Kiểm tra URL trong import, `spring.cloud.config.uri` và các location khác |
| Một khóa có giá trị ở local và remote | Có thể bình thường; cần hiểu precedence | Kiểm tra origin/property source và giá trị hiệu lực |

Không kết luận bị nạp trùng chỉ vì số request tăng sau migration. Cũng không xem nhiều property source là lỗi nếu chúng là các lớp cấu hình được thiết kế có chủ đích.

## Kiểm tra giá trị hiệu lực sau migration

Kiểm thử nên so sánh hành vi trước và sau migration bằng cùng application, profile, label và backend. Các bước gợi ý:

1. Khởi động phiên bản cũ và ghi nhận giá trị hiệu lực của một tập thuộc tính đại diện, không lưu bí mật.
2. Chuyển sang Config Data import và tắt bootstrap legacy.
3. Khởi động lại với cùng profile, label và danh tính truy cập.
4. Kiểm tra log để xác nhận Config Data resolver gọi đúng Config Server; chấp nhận lượt `default` và lượt profile riêng nếu có.
5. So sánh giá trị hiệu lực và nguồn gốc của từng thuộc tính đại diện.
6. Kiểm tra các profile `dev`, `test`, `prod` và trường hợp không có profile tường minh.
7. Kiểm tra khi Config Server không sẵn sàng để xác nhận optional/fail-fast hoạt động đúng.
8. Kiểm tra dependency tree và biến môi trường để chắc chắn bootstrap cũ đã được tắt.

Trong môi trường thử nghiệm, có thể dùng Actuator `env` để xem property source và origin của một khóa:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,env
```

Chỉ expose `env` tạm thời trong môi trường được bảo vệ, với xác thực và phân quyền phù hợp. Endpoint này có thể tiết lộ cấu hình nội bộ hoặc dữ liệu nhạy cảm. Sau kiểm thử, tắt exposure nếu không cần trong vận hành thường ngày. Có thể kiểm tra phản hồi Config Server API trực tiếp trong môi trường thử nghiệm để xem danh sách `propertySources` mà không mở endpoint quản trị cho người dùng cuối.

Ví dụ truy vấn Config Server:

```bash
curl -i https://config.internal.example/order-service/default
curl -i https://config.internal.example/order-service/prod
```

Hai phản hồi này giúp xác nhận dữ liệu theo từng profile. Chúng không thay thế việc kiểm tra giá trị cuối cùng trong `Environment` của client, vì client còn hợp nhất property source remote với các nguồn local và biến môi trường.

## Những lỗi migration thường gặp

| Hiện tượng | Nguyên nhân có thể gặp | Cách xử lý |
|---|---|---|
| Client vẫn kết nối Config Server hai lần theo hai luồng | Bootstrap starter/cờ bootstrap còn bật cùng Config Data import | Tắt bootstrap legacy và kiểm tra dependency/environment/JVM options |
| Client không kết nối sau khi xóa `bootstrap.yml` | Chưa khai báo `spring.config.import` hoặc thiếu Config Client | Thêm import vào application config và giữ `spring-cloud-starter-config` |
| Client kết nối sai server | URL cũ còn trong environment/JVM hoặc URL import có precedence cao hơn | Kiểm tra tất cả nguồn cấp `spring.cloud.config.uri` và URL import |
| Giá trị sau migration khác trước | Profile, label, application name hoặc thứ tự property source thay đổi | So sánh request, `PropertySource` và origin của khóa |
| Ứng dụng tiếp tục chạy với cấu hình local khi server lỗi | Import vẫn có `optional:` | Bỏ `optional:` nếu remote config là bắt buộc |
| Startup kéo dài hoặc thất bại khi server tạm thời chưa sẵn sàng | Retry/timeout chưa phù hợp hoặc fail-fast chưa được thiết kế | Cấu hình retry có giới hạn, timeout và startup budget |
| Profile không được nạp như dự kiến | Profile kích hoạt đặt trong file profile-specific hoặc profile truyền khác trước | Đưa profile activation về nguồn không đặc thù profile và kiểm tra request Config Server |

## Kế hoạch rollback

Migration nên được triển khai theo từng ứng dụng hoặc từng nhóm instance để có thể khôi phục nhanh. Trước khi rollout, lưu lại dependency graph và các giá trị bootstrap cũ cần thiết.

Nếu Config Data chưa hoạt động đúng:

1. Dừng rollout phiên bản mới.
2. Khôi phục đúng một luồng bootstrap legacy đã biết hoạt động: dependency bootstrap (nếu cần), cờ bootstrap và cấu hình kết nối cũ.
3. Gỡ `spring.config.import=configserver:` khỏi cấu hình của bản rollback để không chạy đồng thời hai luồng.
4. Khởi động lại và xác minh giá trị hiệu lực, profile, label và endpoint.
5. Điều tra lỗi Config Data trong môi trường thử nghiệm rồi thực hiện lại migration theo từng bước.

Không rollback bằng cách chỉ bật lại `spring.cloud.bootstrap.enabled=true` trong khi vẫn giữ Config Data import bắt buộc; điều đó có thể kích hoạt cả hai cơ chế.

## Checklist hoàn tất migration

- [ ] Spring Boot/Spring Cloud release train hỗ trợ Config Data API.
- [ ] `spring-cloud-starter-config` vẫn có trên classpath.
- [ ] `spring.config.import` trỏ đến đúng Config Server.
- [ ] Optional hay required được chọn theo yêu cầu vận hành.
- [ ] Application name, profile, label và credential giữ đúng ý nghĩa.
- [ ] Bootstrap starter và `spring.cloud.bootstrap.enabled=true` đã được loại bỏ nếu không còn dùng.
- [ ] Không còn cấu hình Config Client cũ trong bootstrap file, environment hoặc JVM options.
- [ ] Giá trị hiệu lực và origin đã được so sánh với trước migration.
- [ ] Các request `default`/profile được hiểu đúng, không nhầm là duplicate fetch.
- [ ] Hành vi khi Config Server lỗi, retry và rollback đã được kiểm thử.
- [ ] Endpoint Actuator nhạy cảm đã được đóng hoặc bảo vệ sau kiểm thử.

## Kết luận

Chuyển từ bootstrap legacy sang Config Data là chuyển cơ chế khởi tạo Config Client từ bootstrap context sang `spring.config.import`. Một migration sạch cần giữ `spring-cloud-starter-config`, chuyển địa chỉ và tùy chọn cần thiết sang cấu hình ứng dụng, đồng thời tắt bootstrap starter/cờ bootstrap cũ khi không còn sử dụng.

Config Data có thể tạo nhiều request hợp lệ, trước tiên cho `default` rồi cho các profile đang hoạt động. Spring Boot cũng chỉ import cùng một location một lần. Vì vậy, muốn phát hiện nạp trùng cần kiểm tra cơ chế bootstrap có còn bật, endpoint nào được gọi, danh sách property source và giá trị hiệu lực. So sánh origin trước/sau, kiểm thử từng profile và giữ kế hoạch rollback một cơ chế tại một thời điểm giúp migration an toàn và dễ truy nguyên.

## Tài liệu tham khảo

- [Spring Cloud Config Client – Config Data Import và Bootstrap](https://docs.spring.io/spring-cloud-config/reference/client.html)
- [Spring Boot – Externalized Configuration và Config Data](https://docs.spring.io/spring-boot/reference/features/external-config.html)
- [Spring Cloud – Config First Bootstrap](https://docs.spring.io/spring-cloud/docs/current/reference/htmlsingle/spring-cloud.html)
