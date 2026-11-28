# Ánh xạ `spring.application.name` và cấu hình name, profile, label

Spring Cloud Config Client cần gửi đúng ba thông tin để Config Server tìm bộ cấu hình từ xa: tên cấu hình (application name), profile và label. Ba thông tin này tạo thành địa chỉ logic của một bộ cấu hình. Nếu tên ứng dụng sai, client có thể nhận cấu hình của dịch vụ khác; nếu profile sai, giá trị theo môi trường có thể bị thiếu; nếu label sai, client có thể đọc nhầm phiên bản cấu hình.

Trong cấu hình Spring Boot, `spring.application.name` thường là tên ứng dụng mặc định mà Config Client dùng để tìm cấu hình. Client cũng có các thuộc tính riêng `spring.cloud.config.name`, `spring.cloud.config.profile` và `spring.cloud.config.label` để điều khiển chính xác request. Cần hiểu sự khác nhau giữa tên ứng dụng đang chạy và tên cấu hình được yêu cầu, đồng thời đặt các giá trị định tuyến ở thời điểm đủ sớm để Config Data có thể tải cấu hình.

## 1. Ba thành phần định tuyến cấu hình

Config Server cung cấp endpoint Environment phổ biến:

```text
/{application}/{profile}/{label}
```

| Thành phần | Thuộc tính phía client | Ví dụ | Vai trò |
|---|---|---|---|
| Application name | `spring.cloud.config.name` hoặc mặc định từ `spring.application.name` | `order-service` | Chọn bộ cấu hình theo ứng dụng |
| Profile | `spring.cloud.config.profile` hoặc mặc định từ active profiles | `prod` | Chọn cấu hình theo môi trường hoặc nhóm hành vi |
| Label | `spring.cloud.config.label` | `release-2026.11` | Chọn phiên bản cấu hình trong backend |

Ví dụ request được tạo từ ba giá trị:

```text
GET http://config-server:8888/order-service/prod/release-2026.11
```

Config Server dùng application và profile để tìm các property source phù hợp, sau đó đọc label được yêu cầu. Với Git backend, label thường là branch, tag hoặc Git ref. Với JDBC hay backend khác, label có thể là một mã phiên bản do tổ chức quy ước.

## 2. `spring.application.name` xác định tên ứng dụng mặc định

Trong một ứng dụng Spring Boot, khai báo:

```yaml
spring:
  application:
    name: order-service
```

Khi Config Client không có cấu hình tên riêng, `spring.application.name` được dùng làm application name để yêu cầu Config Server. Vì vậy, nếu client có tên `order-service`, Config Server sẽ tìm các tệp như:

```text
application.yml
application-prod.yml
order-service.yml
order-service-prod.yml
```

Các tệp `application*.yml` thường chứa cấu hình chung; các tệp bắt đầu bằng `order-service` chứa cấu hình riêng cho ứng dụng đó. Profile trong request quyết định các tệp profile-specific được xem xét.

Tên ứng dụng nên ổn định, dễ nhận biết và thống nhất giữa cấu hình client, log, service discovery và giám sát. Tránh để mỗi môi trường tự đặt một tên khác nhau nếu chúng vẫn là cùng một dịch vụ; dùng profile để phân biệt môi trường.

## 3. Phân biệt tên ứng dụng chạy với `spring.cloud.config.name`

`spring.cloud.config.name` cho phép client yêu cầu một tên cấu hình từ xa khác với tên ứng dụng đang chạy. Điều này hữu ích khi nhiều ứng dụng dùng chung một bộ cấu hình hoặc khi tên artifact/service khác với tên đã quy ước trong Config Repository.

Ví dụ ứng dụng đang chạy có tên `orders-api`, nhưng bộ cấu hình trong Git được đặt theo tên `order-service`:

```yaml
spring:
  application:
    name: orders-api
  cloud:
    config:
      name: order-service
```

Khi đó:

- Tên ứng dụng trong Spring vẫn là `orders-api`.
- Config Client yêu cầu cấu hình theo tên `order-service`.
- Config Server tìm `order-service.yml`, `order-service-prod.yml` hoặc các nguồn tương ứng với profile được yêu cầu.

`spring.cloud.config.name` chỉ điều khiển tên dùng để lấy cấu hình từ xa; nó không đổi `spring.application.name` của ứng dụng. Nếu không khai báo `spring.cloud.config.name`, client dùng `spring.application.name` làm tên cấu hình mặc định.

Một ví dụ khác là hai ứng dụng nhỏ dùng chung một bộ cấu hình nền:

```yaml
spring:
  application:
    name: order-worker
  cloud:
    config:
      name: order-service
```

```yaml
spring:
  application:
    name: order-scheduler
  cloud:
    config:
      name: order-service
```

Hai tiến trình vẫn có tên ứng dụng riêng để quan sát và vận hành, nhưng cùng yêu cầu cấu hình tên `order-service`. Chỉ nên chia sẻ theo cách này khi hai ứng dụng thực sự tương thích về key, kiểu dữ liệu và vòng đời cấu hình.

## 4. Profile được chọn từ đâu?

Spring Boot dùng `spring.profiles.active` để xác định profile đang hoạt động. Nếu Config Client không khai báo `spring.cloud.config.profile`, client thường sử dụng các active profiles làm profile yêu cầu Config Server. Nếu không có profile nào được kích hoạt, Spring sử dụng profile mặc định `default`.

Ví dụ:

```yaml
spring:
  application:
    name: order-service
  profiles:
    active: prod
```

Client yêu cầu cấu hình với profile `prod`. Config Server có thể trả về các nguồn như `application-prod.yml` và `order-service-prod.yml` cùng các nguồn không gắn profile.

Có thể đặt active profile bằng biến môi trường hoặc tham số dòng lệnh:

```powershell
$env:SPRING_PROFILES_ACTIVE = "prod"
.\mvnw.cmd spring-boot:run
```

Hoặc:

```bash
java -jar order-service.jar --spring.profiles.active=prod
```

Nếu muốn chỉ định profile gửi đến Config Server một cách tường minh, có thể dùng `spring.cloud.config.profile`:

```yaml
spring:
  application:
    name: order-service
  cloud:
    config:
      profile: prod
```

`spring.cloud.config.profile` là profile dành cho yêu cầu Config Server; `spring.profiles.active` điều khiển profile hoạt động của ứng dụng Spring Boot. Trong trường hợp đặt cả hai, cần hiểu rõ mục đích và xác minh request thực tế. Tránh đặt hai giá trị khác nhau nếu không có nhu cầu rõ ràng, vì điều đó dễ làm client nhận cấu hình theo một profile nhưng các bean local lại được cấu hình theo profile khác.

### 4.1. Nhiều profile

Spring Boot có thể chạy với nhiều active profiles, ví dụ:

```yaml
spring:
  profiles:
    active: prod,observability
```

Config Client có thể gửi danh sách profile tương ứng để Config Server kết hợp cấu hình. Thứ tự và cách xử lý các nguồn profile cần được kiểm tra qua response Environment; không giả định hai profile sẽ có cùng độ ưu tiên ở mọi backend hoặc mọi cách cấu hình.

Profile nên biểu diễn môi trường hoặc một nhóm hành vi có ý nghĩa, chẳng hạn `dev`, `test`, `prod`, `observability`. Không nên tạo profile mới chỉ để phân biệt từng máy hoặc từng instance nếu các instance cần cùng bộ cấu hình.

## 5. Label chọn phiên bản cấu hình

Label được khai báo bằng `spring.cloud.config.label`:

```yaml
spring:
  cloud:
    config:
      label: release-2026.11
```

Với Git backend, label thường là branch, tag hoặc commit ref. Ví dụ:

```yaml
spring:
  cloud:
    config:
      label: main
```

hoặc:

```yaml
spring:
  cloud:
    config:
      label: release-2026.11
```

Nếu không khai báo label, Config Server có thể dùng `default-label` được cấu hình ở backend. Để triển khai có thể tái lập, production thường nên dùng một tag hoặc ref phát hành đã được kiểm soát thay vì phụ thuộc vào nhánh phát triển luôn thay đổi.

Label phải tồn tại trong đúng backend mà request được định tuyến tới. Nếu dùng nhiều Git repository, Config Server trước tiên chọn repository theo application/profile rồi mới tìm label trong repository đó. Một tag có ở repository này không có nghĩa nó tồn tại ở repository khác.

## 6. Cấu hình Config Client bằng Config Data API

Với Spring Boot 2.4 trở lên, cách phổ biến là dùng Config Data API qua `spring.config.import`. Ví dụ đầy đủ:

```yaml
server:
  port: 8080

spring:
  application:
    name: order-service
  profiles:
    active: prod
  config:
    import: "configserver:http://config-server:8888"
  cloud:
    config:
      name: order-service
      profile: prod
      label: release-2026.11
```

Trong ví dụ này, client yêu cầu bộ cấu hình:

```text
application = order-service
profile     = prod
label       = release-2026.11
```

Vì application name, profile và label đều được khai báo tường minh, người vận hành có thể đối chiếu trực tiếp với URL Environment của Config Server. Trong cấu hình thông thường, có thể bỏ `spring.cloud.config.name` và `spring.cloud.config.profile` nếu muốn dùng giá trị mặc định từ `spring.application.name` và active profiles.

Nếu Config Server bắt buộc để ứng dụng hoạt động, dùng import không có `optional:` như ví dụ trên. Nếu môi trường local có cấu hình dự phòng đầy đủ và chấp nhận khởi động khi Config Server tạm thời không truy cập được, có thể dùng:

```yaml
spring:
  config:
    import: "optional:configserver:http://localhost:8888"
```

`optional:` chỉ thay đổi hành vi khi không lấy được nguồn cấu hình; nó không sửa được sai application/profile/label và không bảo đảm các property bắt buộc đã có giá trị. Cần kiểm tra fallback để ứng dụng không khởi động trong trạng thái thiếu cấu hình quan trọng.

## 7. Đặt thông tin định tuyến ở thời điểm đủ sớm

Config Client phải biết Config Server URL, application name, profile và label trước khi có thể yêu cầu cấu hình. Vì vậy, các thuộc tính điều khiển việc tìm cấu hình nên có sẵn trong cấu hình local không phụ thuộc vào chính remote configuration đang được tìm.

Một cấu hình bootstrap theo Config Data thường đặt trong `application.yml`:

```yaml
spring:
  application:
    name: order-service
  config:
    import: "configserver:http://config-server:8888"
  cloud:
    config:
      profile: prod
      label: release-2026.11
```

Các giá trị này cũng có thể được cấp từ biến môi trường, system property hoặc command-line khi triển khai. Ví dụ:

```bash
SPRING_APPLICATION_NAME=order-service
SPRING_CLOUD_CONFIG_PROFILE=prod
SPRING_CLOUD_CONFIG_LABEL=release-2026.11
```

Không nên chỉ đặt `spring.cloud.config.name`, profile hoặc label trong tệp remote rồi kỳ vọng client dùng chúng để tìm chính tệp remote đầu tiên. Đó là vòng phụ thuộc: client cần các giá trị này để tạo request trước khi đọc được response từ server.

Các project dùng cơ chế bootstrap cũ có thể đặt thông tin kết nối và định tuyến trong `bootstrap.yml` cùng bootstrap starter tương ứng. Hãy dùng một cách cấu hình phù hợp với phiên bản Spring Boot/Spring Cloud của dự án; không trộn bootstrap context cũ và Config Data API nếu chưa xác định rõ thứ tự nạp.

## 8. Ví dụ ánh xạ tên service và tên cấu hình khác nhau

Giả sử ứng dụng runtime tên `checkout-api`, nhưng nhóm cấu hình đã chuẩn hóa tên trong repository thành `order-service`. Cấu hình client:

```yaml
spring:
  application:
    name: checkout-api
  config:
    import: "configserver:http://localhost:8888"
  cloud:
    config:
      name: order-service
      profile: prod
      label: release-2026.11
```

Client sẽ yêu cầu:

```text
GET http://localhost:8888/order-service/prod/release-2026.11
```

Config Server tìm các tệp phù hợp với `order-service`, profile `prod` và label `release-2026.11`. Trong khi đó, tên ứng dụng runtime vẫn là `checkout-api`, nên các thành phần như log, metric hoặc service discovery có thể tiếp tục dùng tên đó.

Để xác minh, gọi trực tiếp endpoint Environment:

```bash
curl -i "http://localhost:8888/order-service/prod/release-2026.11"
```

Kiểm tra các trường `name`, `profiles`, `label`, `version` và danh sách `propertySources`. Nếu `name` trong response không phải `order-service`, hãy kiểm tra lại thuộc tính `spring.cloud.config.name` và cấu hình được client nạp ở giai đoạn sớm.

## 9. Kiểm tra request thực tế và giá trị phía client

Có thể dùng các cách sau để xác nhận client đang gửi đúng thông tin:

1. Đọc log khởi động của Config Client để kiểm tra địa chỉ Config Server và quá trình nạp Config Data.
2. Gọi endpoint Environment trực tiếp với application/profile/label mong muốn rồi so sánh metadata và property sources.
3. Dùng Spring Boot Actuator `env` trong môi trường được bảo vệ để kiểm tra property source phía client.
4. Kiểm tra `@ConfigurationProperties` đã bind đúng key và kiểu dữ liệu.

Ví dụ expose endpoint `env` ở môi trường phát triển:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,env
  endpoint:
    env:
      show-values: when-authorized
```

Yêu cầu thông tin của một key:

```bash
curl "http://localhost:8080/actuator/env/orders.timeout"
```

Endpoint này có thể tiết lộ cấu hình nội bộ. Chỉ expose trong mạng được kiểm soát, yêu cầu xác thực/phân quyền phù hợp và che giá trị nhạy cảm. Không bật hiển thị toàn bộ secret trong production chỉ để tiện debug.

## 10. Lỗi thường gặp khi ánh xạ name, profile và label

| Hiện tượng | Nguyên nhân có thể có | Cách kiểm tra |
|---|---|---|
| Client nhận cấu hình của ứng dụng khác | `spring.application.name` hoặc `spring.cloud.config.name` sai | Kiểm tra tên trong cấu hình local và trường `name` của response |
| Không nhận cấu hình riêng của ứng dụng | Tên request không khớp tên tệp trong repository | So sánh `spring.cloud.config.name` với tên file như `order-service-prod.yml` |
| Nhận cấu hình sai môi trường | Active profile hoặc `spring.cloud.config.profile` không đúng | Kiểm tra `spring.profiles.active`, profile gửi lên và trường `profiles` |
| Không tìm thấy phiên bản cấu hình | Label không tồn tại trong repository được chọn | Kiểm tra `spring.cloud.config.label`, branch/tag và `default-label` |
| Client chạy profile khác với profile lấy cấu hình | `spring.cloud.config.profile` và `spring.profiles.active` không thống nhất | Xác định rõ có chủ đích tách hai profile hay không; kiểm tra Environment của client |
| Client không thể lấy remote config khi startup | Sai `spring.config.import`, URL, DNS hoặc Config Server chưa sẵn sàng | Kiểm tra log và gọi endpoint Config Server từ môi trường của client |
| Thay đổi cấu hình không xuất hiện | Client vẫn dùng label cũ hoặc Config Server chưa đọc ref mới | Xác nhận label/commit và cách backend cập nhật repository |

## 11. Quy trình chọn và phát hành bộ định tuyến cấu hình

Trước mỗi lần triển khai, có thể kiểm tra theo trình tự:

1. **Xác định tên runtime:** chọn `spring.application.name` ổn định cho dịch vụ.
2. **Xác định tên cấu hình:** chỉ đặt `spring.cloud.config.name` khi tên bộ cấu hình từ xa khác tên runtime hoặc cần dùng chung một bộ cấu hình.
3. **Chọn profile:** xác định profile ứng dụng đang chạy và profile Config Server cần phục vụ; giữ chúng đồng bộ nếu không có lý do tách biệt.
4. **Chọn label:** ghim vào branch/tag/ref phù hợp với môi trường; ghi nhận commit/version khi cần truy vết.
5. **Kiểm tra endpoint:** gọi `/{application}/{profile}/{label}` trực tiếp và xác nhận metadata cùng property sources.
6. **Kiểm tra client:** xác nhận remote sources đã được nạp, local override đúng chính sách và bean bind đúng kiểu.
7. **Ghi nhận triển khai:** lưu application name, config name, profile, label và commit được dùng để có thể tái lập hoặc rollback.

Tên, profile và label là hợp đồng định tuyến giữa Config Client và Config Server. Khi chúng được khai báo rõ ràng, đặt đúng thời điểm và xác minh bằng response Environment, mỗi ứng dụng Spring Boot có thể lấy đúng bộ cấu hình theo môi trường và phiên bản đã được kiểm soát.
