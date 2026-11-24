# Cấu hình application.yml, profile và biến môi trường

Một ứng dụng Spring Cloud thường chạy ở nhiều môi trường: máy local, Docker, staging và production. Mỗi môi trường có thể dùng port, địa chỉ Consul, database hoặc mức log khác nhau. Nếu viết các giá trị này cố định trong mã nguồn, việc chuyển môi trường dễ gây lỗi và có thể làm lộ thông tin nhạy cảm.

Spring Boot cung cấp cơ chế externalized configuration để ứng dụng đọc cấu hình từ `application.yml`, file theo profile, biến môi trường, tham số dòng lệnh và các nguồn bên ngoài khác. Bài học này hướng dẫn tổ chức cấu hình theo môi trường, kích hoạt profile và ghi đè giá trị bằng biến môi trường trong một dự án Spring Cloud Service Discovery.

## 1. Vai trò của application.yml

Spring Boot tự động tìm các file cấu hình theo quy ước như `application.properties` hoặc `application.yml`. File YAML biểu diễn cấu hình dạng cây, phù hợp khi có nhiều nhóm thuộc tính lồng nhau như `spring.application`, `spring.cloud.consul` và `management.endpoints`.

Ví dụ cấu hình nền cho một service:

```yaml
spring:
  application:
    name: order-service
  cloud:
    consul:
      host: ${CONSUL_HOST:localhost}
      port: ${CONSUL_PORT:8500}
      discovery:
        register: true
        health-check-path: /actuator/health
        health-check-interval: 10s

server:
  port: ${SERVER_PORT:8080}

management:
  endpoints:
    web:
      exposure:
        include: health,info
  endpoint:
    health:
      show-details: never
```

Ý nghĩa của các thuộc tính:

- `spring.application.name` đặt tên service mà Consul đăng ký và các consumer dùng để discovery.
- `spring.cloud.consul.host` và `port` xác định địa chỉ Consul Agent hoặc endpoint Consul mà ứng dụng kết nối tới, tùy topology triển khai.
- `spring.cloud.consul.discovery.register` bật đăng ký service.
- `health-check-path` và `health-check-interval` xác định endpoint và chu kỳ health check.
- `server.port` đặt cổng HTTP của ứng dụng.
- `management.endpoints.web.exposure.include` cho phép truy cập các Actuator endpoint đã liệt kê.
- `show-details: never` tránh công khai chi tiết nội bộ của health indicator qua endpoint health.

Biểu thức `${CONSUL_HOST:localhost}` có nghĩa là đọc biến `CONSUL_HOST`; nếu biến chưa được đặt thì dùng `localhost`. Tương tự, `SERVER_PORT` mặc định là `8080`. Giá trị mặc định hữu ích cho môi trường local, nhưng không nên dùng fallback tùy tiện cho các thông tin bắt buộc ở production.

YAML phụ thuộc vào thụt lề. Các cấp con thường thụt vào hai dấu cách; không dùng tab. Một thuộc tính đặt sai cấp có thể khiến Spring Boot không đọc đúng cấu hình mong muốn.

## 2. Tách cấu hình theo profile

Profile là nhãn môi trường hoặc nhóm cấu hình mà Spring Boot có thể kích hoạt khi khởi động. Cách tổ chức phổ biến là giữ cấu hình dùng chung trong `application.yml`, sau đó tạo file riêng cho từng môi trường:

```text
src/main/resources/
├── application.yml
├── application-local.yml
├── application-docker.yml
├── application-staging.yml
└── application-prod.yml
```

Spring Boot nạp `application.yml` làm cấu hình nền. Khi profile `local` được kích hoạt, các thuộc tính trong `application-local.yml` được áp dụng bổ sung và có thể ghi đè giá trị tương ứng trong file nền. Các thuộc tính không được khai báo lại vẫn kế thừa từ cấu hình nền.

### 2.1. Cấu hình local

Ví dụ `application-local.yml`:

```yaml
spring:
  cloud:
    consul:
      host: localhost
      port: 8500

logging:
  level:
    root: INFO
    org.springframework.cloud.consul: DEBUG
```

Profile local trỏ tới Consul chạy trên máy phát triển và bật log chi tiết hơn cho phần tích hợp Consul. Không cần sao chép toàn bộ `application.yml`; chỉ khai báo những giá trị cần khác.

### 2.2. Cấu hình Docker

Trong Docker Compose, tên service thường được dùng làm hostname trên mạng nội bộ. Ví dụ `application-docker.yml`:

```yaml
spring:
  cloud:
    consul:
      host: consul
      port: 8500
```

Ở đây `consul` phải khớp với tên service hoặc DNS alias có thể phân giải từ container ứng dụng. `localhost` bên trong container ứng dụng trỏ về chính container đó, không tự động trỏ tới container Consul.

### 2.3. Cấu hình production

Production thường lấy thông tin kết nối từ môi trường triển khai hoặc secret manager. Ví dụ `application-prod.yml`:

```yaml
spring:
  cloud:
    consul:
      host: ${CONSUL_HOST}
      port: ${CONSUL_PORT:8500}
  datasource:
    url: ${DB_URL}
    username: ${DB_USERNAME}
    password: ${DB_PASSWORD}

server:
  port: ${SERVER_PORT:8080}

logging:
  level:
    root: INFO
```

Các placeholder `${CONSUL_HOST}`, `${DB_URL}`, `${DB_USERNAME}` và `${DB_PASSWORD}` không có giá trị mặc định. Nếu môi trường không cung cấp chúng, ứng dụng sẽ báo lỗi khi phân giải cấu hình thay vì âm thầm kết nối tới một địa chỉ không đúng. Không commit mật khẩu, token, private key hoặc connection string chứa credential vào Git.

Profile giúp chọn cấu hình, nhưng không tự tạo ra hạ tầng tương ứng. Ví dụ, kích hoạt profile `docker` không khởi động container Consul; container đó vẫn phải được khai báo và chạy trong môi trường triển khai.

## 3. Kích hoạt profile khi chạy ứng dụng

Không cần sửa file cấu hình mỗi lần chuyển môi trường. Có thể chọn profile bằng tham số dòng lệnh hoặc biến môi trường.

Chạy JAR với profile local:

```bash
java -jar target/order-service.jar --spring.profiles.active=local
```

Chạy với profile Docker:

```bash
java -jar target/order-service.jar --spring.profiles.active=docker
```

Hoặc dùng biến môi trường:

```bash
SPRING_PROFILES_ACTIVE=local java -jar target/order-service.jar
```

Trên PowerShell của Windows:

```powershell
$env:SPRING_PROFILES_ACTIVE = "local"
java -jar target/order-service.jar
```

Để bỏ biến môi trường trong phiên PowerShell hiện tại:

```powershell
Remove-Item Env:SPRING_PROFILES_ACTIVE
```

Không nên đặt `spring.profiles.active` bên trong file `application-local.yml` hoặc `application-prod.yml` để file tự kích hoạt chính nó. Hãy chọn profile từ cấu hình nền phù hợp hoặc từ môi trường khởi chạy. Nếu muốn đặt profile mặc định khi không có profile nào được chỉ định, có thể dùng `spring.profiles.default`; tuy nhiên, cần cân nhắc để ứng dụng production không vô tình chạy với cấu hình local.

## 4. Ghi đè cấu hình bằng biến môi trường

Spring Boot ánh xạ tên thuộc tính dạng dấu chấm sang tên biến môi trường viết hoa và dùng dấu gạch dưới thay cho dấu chấm. Với phần lớn thuộc tính thông thường, có thể áp dụng quy tắc:

| Thuộc tính trong YAML | Biến môi trường |
| --- | --- |
| `spring.application.name` | `SPRING_APPLICATION_NAME` |
| `spring.cloud.consul.host` | `SPRING_CLOUD_CONSUL_HOST` |
| `spring.cloud.consul.port` | `SPRING_CLOUD_CONSUL_PORT` |
| `spring.cloud.consul.discovery.register` | `SPRING_CLOUD_CONSUL_DISCOVERY_REGISTER` |
| `server.port` | `SERVER_PORT` |
| `management.endpoints.web.exposure.include` | `MANAGEMENT_ENDPOINTS_WEB_EXPOSURE_INCLUDE` |
| `spring.profiles.active` | `SPRING_PROFILES_ACTIVE` |

Biến môi trường có thể ghi đè giá trị trong file cấu hình. Ví dụ, nếu `application.yml` đặt `server.port: 8080` nhưng môi trường cung cấp `SERVER_PORT=8085`, ứng dụng sẽ dùng port `8085`.

Đặt nhiều biến trên Linux hoặc macOS:

```bash
SPRING_PROFILES_ACTIVE=local \
SERVER_PORT=8081 \
CONSUL_HOST=localhost \
java -jar target/order-service.jar
```

Đặt biến trong PowerShell:

```powershell
$env:SPRING_PROFILES_ACTIVE = "local"
$env:SERVER_PORT = "8081"
$env:CONSUL_HOST = "localhost"
java -jar target/order-service.jar
```

Lưu ý rằng `SERVER_PORT` là thuộc tính phổ biến nên có tên ngắn, dễ dùng. Các thuộc tính dài cần giữ đúng quy tắc chuyển đổi tên của Spring Boot. Với map, list hoặc tên thuộc tính phức tạp, hãy kiểm tra quy tắc relaxed binding của phiên bản Spring Boot đang dùng thay vì tự suy luận tên biến.

## 5. Thứ tự ưu tiên khi có nhiều nguồn cấu hình

Một thuộc tính có thể xuất hiện ở nhiều nơi. Spring Boot áp dụng thứ tự ưu tiên của các property source; nguồn có ưu tiên cao hơn sẽ ghi đè nguồn thấp hơn. Trong quy trình chạy ứng dụng thông thường, có thể ghi nhớ thứ tự tổng quát sau, từ ưu tiên cao xuống thấp:

1. Tham số dòng lệnh, ví dụ `--server.port=8082`.
2. `SPRING_APPLICATION_JSON` và các nguồn cấu hình ngoài có ưu tiên tương ứng.
3. Thuộc tính hệ thống Java, ví dụ `-Dserver.port=8083`.
4. Biến môi trường của tiến trình.
5. File cấu hình được nạp, như `application.yml` và file theo profile.
6. Giá trị mặc định được khai báo trong ứng dụng.

Thứ tự thực tế còn phụ thuộc loại property source, vị trí file, config import và phiên bản Spring Boot. Trong các file cấu hình, profile-specific config được áp dụng sau cấu hình không gắn profile để có thể ghi đè giá trị nền.

Ví dụ, cùng lúc có:

```yaml
# application.yml
server:
  port: 8080
```

```yaml
# application-local.yml
server:
  port: 8081
```

Và biến môi trường:

```text
SERVER_PORT=8082
```

Khi chạy với profile `local`, biến môi trường có ưu tiên cao hơn file cấu hình nên ứng dụng dùng port `8082`. Nếu truyền thêm `--server.port=8083`, tham số dòng lệnh sẽ thắng và ứng dụng dùng port `8083`.

Khi giá trị thực tế không như mong đợi, kiểm tra cả profile đã kích hoạt và mọi nguồn ghi đè. Có thể bật log cấu hình phù hợp trong môi trường phát triển hoặc dùng Actuator `env`/`configprops` khi endpoint được bảo vệ đúng cách. Không expose các endpoint này công khai vì chúng có thể tiết lộ thông tin cấu hình.

## 6. Chạy nhiều instance local với cấu hình khác nhau

Một ứng dụng có thể chạy nhiều tiến trình trên cùng máy để thử đăng ký nhiều instance vào Consul. Mỗi tiến trình cần port riêng; các tiến trình có thể dùng chung profile local và cùng tên service để Consul nhận diện chúng là các instance của một service.

Ví dụ chạy hai JAR trong hai terminal PowerShell riêng.

Terminal thứ nhất:

```powershell
$env:SPRING_PROFILES_ACTIVE = "local"
$env:SERVER_PORT = "8081"
java -jar target/order-service.jar
```

Terminal thứ hai:

```powershell
$env:SPRING_PROFILES_ACTIVE = "local"
$env:SERVER_PORT = "8082"
java -jar target/order-service.jar
```

Hoặc chạy trên Linux/macOS:

```bash
SPRING_PROFILES_ACTIVE=local SERVER_PORT=8081 java -jar target/order-service.jar
SPRING_PROFILES_ACTIVE=local SERVER_PORT=8082 java -jar target/order-service.jar
```

Hai tiến trình dùng chung `spring.application.name: order-service`, nhưng có port khác nhau. Khi đăng ký thành công, Consul có thể hiển thị hai instance. Hãy xác minh cấu hình đăng ký của phiên bản Spring Cloud Consul đang dùng tạo instance ID riêng cho từng tiến trình; nếu tự cấu hình `instance-id`, cần bảo đảm giá trị không trùng nhau.

Nếu dùng Actuator health check, endpoint phải được expose và có thể truy cập ở từng port. Kiểm tra riêng từng instance:

```bash
curl -i http://localhost:8081/actuator/health
curl -i http://localhost:8082/actuator/health
```

Sau đó kiểm tra Consul Catalog/Health API để xác nhận cả hai instance được đăng ký và đang passing. Việc hai tiến trình cùng chạy không đảm bảo chúng đã đăng ký thành công; cần kiểm tra log khởi động, địa chỉ Consul, health check và instance ID.

## 7. Một số lỗi cấu hình thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Cách kiểm tra hoặc xử lý |
| --- | --- | --- |
| Ứng dụng không đọc giá trị trong `application-local.yml` | Profile `local` chưa được kích hoạt hoặc file đặt sai vị trí/tên | Kiểm tra `SPRING_PROFILES_ACTIVE` và đặt file trong `src/main/resources`. |
| Biến môi trường không ghi đè YAML | Sai tên biến, sai kiểu dữ liệu hoặc biến chưa được truyền vào tiến trình | Kiểm tra tên theo relaxed binding và in giá trị biến trong đúng shell đang chạy ứng dụng. |
| Consul không kết nối được khi chạy trong Docker | Cấu hình `localhost` trong container ứng dụng | Dùng hostname service Consul trên mạng Docker, ví dụ `consul`. |
| Ứng dụng báo thiếu placeholder | Biến bắt buộc như `DB_URL` hoặc `CONSUL_HOST` chưa được cung cấp | Đặt biến ở môi trường chạy hoặc bổ sung nguồn cấu hình bảo mật phù hợp. |
| Hai instance không thể khởi động đồng thời | Cùng dùng một `server.port` hoặc có cấu hình port ghi đè ngoài dự kiến | Cấp port riêng cho từng tiến trình và kiểm tra tham số dòng lệnh/biến môi trường. |
| Hai instance xuất hiện dưới cùng ID | `instance-id` được cấu hình cố định và trùng nhau | Dùng ID duy nhất theo instance, ví dụ kết hợp hostname và port. |
| Ứng dụng dùng nhầm profile production/local | Biến `SPRING_PROFILES_ACTIVE` còn sót trong shell, IDE hoặc cấu hình run | In profile đang hoạt động trong log khởi động và xóa biến cũ khi cần. |

Không nên giải quyết lỗi bằng cách đặt thêm nhiều giá trị ở nhiều nơi mà không xác định nguồn nào đang thắng. Hãy tìm property source thực tế trước, sau đó sửa một nguồn có trách nhiệm rõ ràng.

## 8. Nguyên tắc quản lý cấu hình an toàn

- Đưa cấu hình chung, không nhạy cảm vào `application.yml`.
- Chỉ đặt phần khác biệt của môi trường trong `application-{profile}.yml`.
- Dùng biến môi trường hoặc secret manager cho password, token, private key và dữ liệu xác thực.
- Không commit file `.env` chứa secret hoặc giá trị production vào repository.
- Dùng placeholder có default cho giá trị local thực sự có thể mặc định; để placeholder bắt buộc không có default khi ứng dụng cần fail fast nếu thiếu cấu hình.
- Giữ cùng một tên service giữa các instance của cùng service; thay đổi port và instance ID theo từng tiến trình.
- Hạn chế expose Actuator endpoint nhạy cảm và bảo vệ endpoint vận hành bằng security phù hợp.
- Ghi lại các biến bắt buộc trong tài liệu triển khai, nhưng chỉ mô tả tên và mục đích, không ghi giá trị bí mật.

## 9. Ghi nhớ

- `application.yml` chứa cấu hình nền; `application-{profile}.yml` chứa phần khác biệt theo môi trường.
- Kích hoạt profile bằng `SPRING_PROFILES_ACTIVE` hoặc `--spring.profiles.active`.
- Biến môi trường ghi đè cấu hình file theo thứ tự ưu tiên của Spring Boot; tham số dòng lệnh thường có ưu tiên cao hơn.
- Placeholder `${NAME:default}` giúp dùng biến môi trường và cung cấp giá trị mặc định khi phù hợp.
- Mỗi tiến trình local cần port riêng và instance ID không trùng để đăng ký nhiều instance cùng service.
- Không lưu credential trong YAML được commit vào Git; dùng biến môi trường hoặc secret manager.

Khi tách cấu hình theo profile và quản lý giá trị thay đổi qua môi trường, cùng một artifact Spring Boot có thể chạy nhất quán trên máy local, Docker và production mà không phải sửa mã nguồn cho từng nơi triển khai.
