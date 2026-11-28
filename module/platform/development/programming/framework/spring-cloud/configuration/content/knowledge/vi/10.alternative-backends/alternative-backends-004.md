# Đóng gói cấu hình cùng ứng dụng hoặc gắn thư mục bên ngoài container

Spring Cloud Config Server không bắt buộc phải đọc cấu hình từ Git. Với native backend, server có thể lấy file từ classpath của chính ứng dụng Config Server hoặc từ hệ thống file mà container nhìn thấy. Hai cách triển khai này phù hợp với những nhu cầu khác nhau: đóng gói cấu hình cùng image để tạo một đơn vị phát hành bất biến, hoặc mount thư mục cấu hình bên ngoài để cập nhật nội dung độc lập với image.

Bài viết tập trung vào cách cấu hình native backend, tổ chức file, đóng gói tài nguyên vào JAR, mount thư mục read-only trong Docker Compose và kết nối Config Client. Cần phân biệt cấu hình backend mà Config Server dùng để tìm file với cấu hình ứng dụng mà Config Client nhận được qua HTTP.

## 1. Native backend trong Spring Cloud Config

Config Server hỗ trợ nhiều backend lưu trữ. Git backend đọc repository và có lịch sử revision; native backend đọc tài nguyên từ classpath hoặc filesystem của tiến trình server.

Để sử dụng native backend, bật profile `native` cho Config Server:

```yaml
spring:
  application:
    name: config-server
  profiles:
    active: native
  cloud:
    config:
      server:
        native:
          search-locations:
            - classpath:/config
            - file:/etc/config-repo
server:
  port: 8888
```

Dependency của ứng dụng Config Server cần có `spring-cloud-config-server`. Lớp khởi động vẫn bật `@EnableConfigServer`:

```java
@SpringBootApplication
@EnableConfigServer
public class ConfigServerApplication {
    public static void main(String[] args) {
        SpringApplication.run(ConfigServerApplication.class, args);
    }
}
```

Profile `native` chọn native EnvironmentRepository. Thuộc tính `spring.cloud.config.server.native.search-locations` khai báo những vị trí mà server sẽ tìm file cấu hình. Có thể dùng một hoặc nhiều location, gồm:

- `classpath:/config`: thư mục `config` nằm trong classpath của ứng dụng Config Server.
- `file:/etc/config-repo`: thư mục trên filesystem mà tiến trình Config Server có thể đọc.
- Các location khác theo định dạng Spring Resource, miễn là tài nguyên đó tồn tại và có quyền truy cập.

Khi đã khai báo search locations tường minh, hãy kiểm tra chúng có bao phủ đúng các vị trí cần dùng hay không. Đừng dựa vào thư mục làm việc ngẫu nhiên của container; ưu tiên đường dẫn tuyệt đối cho filesystem để kết quả không phụ thuộc `WORKDIR`.

## 2. Tổ chức file cấu hình cho native backend

Native backend vẫn dùng quy tắc đặt tên file theo application và profile. Ví dụ:

```text
config-repo/
├── application.yml
├── application-prod.yml
├── orders-service.yml
├── orders-service-prod.yml
├── payment-service.yml
└── payment-service-prod.yml
```

- `application.yml`: thuộc tính mặc định dùng chung.
- `application-prod.yml`: thuộc tính chung cho profile `prod`.
- `orders-service.yml`: cấu hình mặc định của ứng dụng `orders-service`.
- `orders-service-prod.yml`: cấu hình riêng của `orders-service` khi chạy `prod`.
- Các file `payment-service...` có vai trò tương tự cho ứng dụng thanh toán.

Ví dụ `application.yml`:

```yaml
platform:
  region: ap-southeast-1
  connect-timeout: 2s
```

Ví dụ `orders-service.yml`:

```yaml
orders:
  retry:
    max-attempts: 2
  http:
    read-timeout: 5s
```

Ví dụ `orders-service-prod.yml`:

```yaml
orders:
  retry:
    max-attempts: 4
  http:
    read-timeout: 10s
```

Client có `spring.application.name=orders-service` và profile `prod` sẽ yêu cầu cấu hình tương ứng từ Config Server. Các file chung và file cụ thể được kết hợp thành Environment theo quy tắc property source của Config Server. Khi cùng một key xuất hiện ở nhiều nguồn, hãy kiểm tra thứ tự `propertySources` trong response JSON để xác định giá trị có hiệu lực.

## 3. Cách 1: đóng gói cấu hình trong JAR của Config Server

Nếu cấu hình ít thay đổi và cần phát hành cùng phiên bản Config Server, có thể đặt file trong resources của dự án:

```text
config-server/
└── src/
    └── main/
        └── resources/
            └── config/
                ├── application.yml
                ├── orders-service.yml
                └── orders-service-prod.yml
```

Khi build Spring Boot executable JAR, tài nguyên trong `src/main/resources` được đưa vào classpath bên trong JAR. Config Server có thể đọc chúng qua `classpath:/config`.

Cấu hình server:

```yaml
spring:
  application:
    name: config-server
  profiles:
    active: native
  cloud:
    config:
      server:
        native:
          search-locations:
            - classpath:/config
```

Sau khi build:

```bash
mvn clean package
java -jar target/config-server.jar
```

Nếu dùng Gradle, chạy task build tương ứng rồi khởi chạy JAR được tạo. Tên file JAR phụ thuộc cấu hình artifact của dự án.

**Ưu điểm của cách đóng gói:**

- Cấu hình và phiên bản Config Server được phát hành cùng nhau.
- Image có thể tự chứa, không cần mount thư mục cấu hình riêng.
- Dễ tái tạo một bản triển khai vì JAR chứa cả ứng dụng lẫn tài nguyên.
- Phù hợp với cấu hình mặc định hoặc cấu hình ít thay đổi theo vòng đời image.

**Điểm cần cân nhắc:**

- Thay đổi cấu hình yêu cầu build lại JAR/image và triển khai lại Config Server.
- Một thay đổi nhỏ trong cấu hình cũng tạo phiên bản image mới.
- Nếu nhiều ứng dụng dùng chung server, phải phối hợp lịch phát hành cấu hình với lịch phát hành server.
- Không nên nhúng secret vào JAR vì image và artifact có thể được lưu, sao chép hoặc phân phối rộng.

Đóng gói cấu hình cùng server có lợi khi muốn một artifact bất biến và có thể truy vết. Mỗi bản phát hành nên gắn với version hoặc digest của image để biết chính xác bộ cấu hình nào đã được đóng gói.

## 4. Cách 2: mount thư mục cấu hình bên ngoài container

Nếu muốn cập nhật file cấu hình độc lập với image Config Server, có thể giữ thư mục trên máy host hoặc volume quản lý riêng rồi mount vào container. Config Server đọc vị trí mount bằng file URI.

Ví dụ cấu trúc trên máy phát triển:

```text
workspace/
├── compose.yaml
├── config-server/
│   ├── Dockerfile
│   └── target/config-server.jar
└── config-repo/
    ├── application.yml
    ├── orders-service.yml
    └── orders-service-prod.yml
```

Config Server khai báo đường dẫn trong container:

```yaml
spring:
  application:
    name: config-server
  profiles:
    active: native
  cloud:
    config:
      server:
        native:
          search-locations:
            - file:/etc/config-repo
```

Docker Compose mount thư mục từ host vào đường dẫn đó:

```yaml
services:
  config-server:
    build:
      context: ./config-server
    environment:
      SERVER_PORT: "8888"
      SPRING_PROFILES_ACTIVE: native
      SPRING_CLOUD_CONFIG_SERVER_NATIVE_SEARCH_LOCATIONS: file:/etc/config-repo
    volumes:
      - ./config-repo:/etc/config-repo:ro
    ports:
      - "127.0.0.1:8888:8888"
    restart: unless-stopped
```

Dấu `:ro` làm mount read-only bên trong container. Config Server có thể đọc file nhưng không ghi thay đổi trở lại thư mục cấu hình. Đây là lựa chọn phù hợp cho một dịch vụ chỉ có nhiệm vụ phân phối cấu hình.

Đường dẫn hai phía có ý nghĩa khác nhau:

- `./config-repo` là đường dẫn tương đối trên host, tính từ thư mục chứa Compose file.
- `/etc/config-repo` là đường dẫn bên trong container.
- `file:/etc/config-repo` là URI mà Spring Resource dùng để truy cập filesystem của container.

Không khai báo `file:./config-repo` nếu không chắc thư mục làm việc của tiến trình. Với container, đường dẫn tuyệt đối dễ kiểm soát hơn và không phụ thuộc `WORKDIR`.

## 5. Dockerfile cho Config Server

Nếu dùng thư mục mount bên ngoài, image chỉ cần chứa ứng dụng Config Server. Ví dụ Dockerfile:

```dockerfile
FROM eclipse-temurin:17-jre-jammy

WORKDIR /app
COPY target/config-server.jar app.jar

EXPOSE 8888

ENTRYPOINT ["java", "-jar", "/app/app.jar"]
```

JAR phải được build trước khi Compose tạo image. Ví dụ Maven:

```bash
mvn -pl config-server -am package -DskipTests
docker compose build config-server
docker compose up -d config-server
```

Điều chỉnh module và tên JAR theo dự án thực tế. Nếu Dockerfile dùng `COPY target/config-server.jar`, file đó phải tồn tại trong build context trước khi chạy lệnh build.

Nếu dùng cấu hình đóng gói trong JAR, không cần volume mount. Các file cấu hình được đưa vào `src/main/resources/config` và được đọc qua `classpath:/config`.

## 6. Kết hợp classpath và filesystem

Có thể khai báo nhiều search locations:

```yaml
spring:
  cloud:
    config:
      server:
        native:
          search-locations:
            - classpath:/config
            - file:/etc/config-repo
```

Cách này cho phép đóng gói một số giá trị mặc định cùng server và đặt phần cấu hình có thể thay đổi ở thư mục mount. Ví dụ, classpath giữ cấu hình chung ít thay đổi, filesystem giữ phần điều chỉnh theo môi trường.

Tuy nhiên, khi cùng một key xuất hiện ở cả hai nơi, thứ tự property source sẽ quyết định giá trị hiệu lực. Đừng dựa vào thứ tự dòng YAML để suy đoán mà hãy gọi endpoint Environment JSON và kiểm tra `propertySources`. Nếu cần quy tắc override rõ ràng, thiết kế mỗi nguồn sở hữu một nhóm key hoặc kiểm thử precedence bằng chính phiên bản Spring Cloud đang sử dụng.

Một cấu hình khác có thể dùng placeholder theo application, profile hoặc label trong search location:

```yaml
spring:
  cloud:
    config:
      server:
        native:
          search-locations:
            - classpath:/config
            - file:/etc/config-repo/{application}
            - file:/etc/config-repo/{profile}
```

Native backend hỗ trợ placeholder trong search location. Chúng giúp tìm thư mục theo ngữ cảnh request. Cần tổ chức cây thư mục phù hợp và xác nhận kết quả bằng endpoint JSON. Không nhầm placeholder này với `${...}` dùng để phân giải giá trị property trong Spring.

## 7. Cấu hình Config Client kết nối đến native Config Server

Từ góc nhìn client, backend phía server không làm thay đổi cách gọi Config Server. Client vẫn dùng Config Data import:

```yaml
spring:
  application:
    name: orders-service
  profiles:
    active: prod
  config:
    import: "configserver:http://config-server:8888"
```

Trong Docker Compose, hostname `config-server` là tên service trên mạng Compose. Không dùng `localhost:8888` từ container client vì localhost sẽ trỏ về chính client.

Nếu muốn ứng dụng tiếp tục khởi động khi Config Server tạm thời không truy cập được, có thể dùng:

```yaml
spring:
  config:
    import: "optional:configserver:http://config-server:8888"
```

Chỉ chọn optional khi client có giá trị mặc định an toàn và chấp nhận vận hành khi thiếu cấu hình từ xa. Nếu các thuộc tính từ Config Server là bắt buộc, hãy để ứng dụng báo lỗi khởi động khi không nạp được cấu hình để tránh chạy với thiết lập thiếu hoặc sai.

Client có thể đóng gói `application.yml` riêng để khai báo tên ứng dụng, profile, địa chỉ Config Server và các thiết lập kết nối cần thiết. Đây là cấu hình khởi động của client; nó không phải thư mục mà native backend đọc. Các thuộc tính nghiệp vụ do Config Server cung cấp sẽ đi vào Spring Environment cùng các property source khác, theo quy tắc ưu tiên được áp dụng.

## 8. Kiểm tra Config Server đang đọc đúng vị trí

Sau khi khởi động server, gọi endpoint Environment:

```bash
curl http://localhost:8888/orders-service/prod
```

Response JSON cho biết application, profile, label và danh sách property source. Ví dụ rút gọn:

```json
{
  "name": "orders-service",
  "profiles": ["prod"],
  "propertySources": [
    {
      "name": "file:/etc/config-repo/orders-service-prod.yml",
      "source": {
        "orders.http.read-timeout": "10s"
      }
    },
    {
      "name": "file:/etc/config-repo/application.yml",
      "source": {
        "platform.region": "ap-southeast-1"
      }
    }
  ]
}
```

Tên source thực tế phụ thuộc vị trí và phiên bản backend. Hãy kiểm tra các dấu hiệu:

1. Response có đúng application và profile không.
2. Các property source có đến từ `classpath:` hoặc `file:` như dự kiến không.
3. Giá trị có đúng với file cấu hình đã đóng gói hoặc mount không.
4. Key bị trùng có thứ tự ưu tiên đúng như chính sách mong muốn không.

Có thể kiểm tra client lấy được cấu hình bằng cách gọi health endpoint hoặc một endpoint ứng dụng có trả về giá trị không nhạy cảm. Không tạo endpoint chẩn đoán trả toàn bộ Environment trong production.

## 9. Cập nhật file và refresh client

Với classpath backend, file nằm trong JAR đã build. Muốn thay đổi nội dung, cần build image/JAR mới và triển khai lại Config Server.

Với filesystem backend, file có thể được cập nhật trên host hoặc volume mount mà không cần build lại image. Sau khi thay đổi, cần kiểm tra Config Server đã trả nội dung mới cho một request Environment hay chưa. Hành vi đọc lại và cache phụ thuộc phiên bản cùng cấu hình backend, vì vậy nên kiểm tra trực tiếp response thay vì giả định mọi thay đổi đều được thấy ngay.

Dù Config Server đã trả giá trị mới, các Config Client đang chạy không tự động cập nhật Environment chỉ vì file nguồn thay đổi. Cần kích hoạt refresh theo thiết kế của ứng dụng, ví dụ:

- Gọi endpoint refresh được bảo vệ trên client.
- Dùng Spring Cloud Bus để phát sự kiện refresh đến nhiều client.
- Triển khai lại client nếu thay đổi yêu cầu restart hoặc bean không hỗ trợ refresh.

Bean cần cập nhật trong runtime phải được thiết kế phù hợp, chẳng hạn dùng `@RefreshScope` hoặc cơ chế cập nhật trạng thái có chủ đích. Sau refresh, kiểm tra log, metric và giá trị hiệu lực của từng instance.

## 10. Native backend và Git backend khác nhau thế nào?

| Tiêu chí | Native backend | Git backend |
| --- | --- | --- |
| Nguồn dữ liệu | Classpath hoặc filesystem | Git repository |
| Cấu hình vị trí | `search-locations` | `uri`, `search-paths`, credential |
| Revision | Theo artifact hoặc file hiện tại | Branch, tag, commit |
| Lịch sử thay đổi | Do quy trình quản lý artifact/filesystem cung cấp | Git history |
| Cập nhật | Build lại artifact hoặc cập nhật file mount | Commit/push và fetch repository |
| Phù hợp | Lab, cấu hình đóng gói, file share hoặc hệ thống đơn giản | Quản trị cấu hình có review, trace và rollback theo revision |

Native backend không cung cấp lịch sử commit Git. Nếu dùng placeholder `{label}` trong search location, label được dùng như một phần của đường dẫn tìm kiếm trong filesystem/classpath; nó không tự checkout branch hoặc tag như Git backend. Muốn có lịch sử và rollback có thể kiểm chứng, cần quản lý version của image, artifact hoặc thư mục cấu hình bằng một cơ chế riêng.

Với hệ thống nhiều ứng dụng và nhiều môi trường, Git backend thường thuận tiện cho review, audit và quản trị release. Native backend phù hợp khi muốn phân phối tài nguyên đóng gói hoặc lấy từ filesystem có quy trình triển khai riêng.

## 11. Lỗi thường gặp khi dùng classpath hoặc file location

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| Server không tìm thấy file classpath | File không nằm trong resources hoặc đường dẫn classpath sai | Kiểm tra nội dung JAR và `classpath:/config` |
| Server không tìm thấy file mount | Volume mount sai hoặc đường dẫn trong container không tồn tại | Kiểm tra `docker compose config`, mount và quyền đọc |
| Config Server vẫn dùng file cũ | Image chưa build lại hoặc server chưa đọc nội dung mount mới | Kiểm tra JAR/image và endpoint Environment |
| Client không kết nối được server | Dùng localhost bên trong container hoặc service chưa sẵn sàng | Dùng hostname service và kiểm tra network/health |
| Sai profile hoặc application | Tên ứng dụng/profile truyền từ client không đúng | Kiểm tra URL Environment và tên file |
| Key có giá trị ngoài dự kiến | Nhiều location cùng khai báo key | Kiểm tra `propertySources` và thứ tự nguồn |
| Không thấy cập nhật ở client | Client chưa refresh hoặc bean không hỗ trợ refresh | Kiểm tra refresh event và vòng đời bean |
| Permission denied | User trong container không có quyền đọc thư mục hoặc file | Kiểm tra owner, mode và user chạy tiến trình |

Một số lệnh kiểm tra hữu ích:

```bash
# Xem cấu hình Compose sau nội suy
docker compose config

# Xem container và port
docker compose ps

# Xem log Config Server
docker compose logs -f config-server

# Gọi endpoint Environment từ máy host
curl http://localhost:8888/orders-service/prod
```

Nếu cần kiểm tra đường dẫn bên trong container, có thể chạy shell trong container hoặc dùng lệnh liệt kê file phù hợp với base image. Kiểm tra đúng đường dẫn mà Spring đang dùng, không chỉ kiểm tra thư mục trên host.

## 12. Bảo mật và vận hành

Cấu hình tập trung có thể chứa địa chỉ nội bộ, tên tài nguyên và tham số vận hành nhạy cảm. Dù dữ liệu nằm trong JAR hay thư mục mount, cần giới hạn ai có thể đọc và thay đổi nó.

- Không đóng gói mật khẩu, token hoặc private key dạng rõ vào JAR hay image.
- Mount thư mục read-only nếu Config Server chỉ cần đọc.
- Cấp quyền filesystem tối thiểu cho user chạy container.
- Dùng secret manager hoặc cơ chế mã hóa có quản lý khóa cho dữ liệu nhạy cảm.
- Bảo vệ HTTP API Config Server bằng TLS, xác thực và phân quyền.
- Không expose Actuator hoặc endpoint cấu hình ra mạng công cộng.
- Theo dõi version của image, JAR và thư mục cấu hình để có thể truy vết.
- Nếu có nhiều replica Config Server, bảo đảm tất cả replica nhìn thấy cùng nội dung và cùng quyền đọc.

Nếu mount thư mục được cập nhật trực tiếp, nên dùng quy trình thay đổi nguyên tử hoặc thư mục phiên bản rồi chuyển mount/symlink theo kế hoạch của nền tảng. Tránh ghi dở file đang được server đọc. Sau mỗi thay đổi, gọi endpoint Environment để xác nhận dữ liệu mới rồi mới kích hoạt refresh client.

## 13. Chọn cách triển khai

- Chọn **classpath/JAR** khi cấu hình thay đổi cùng nhịp với Config Server và muốn phát hành một artifact tự chứa.
- Chọn **filesystem mount** khi muốn tách vòng đời cấu hình khỏi image, cần dùng volume hoặc thư mục được quản lý bên ngoài container.
- Chọn **kết hợp cả hai** khi có giá trị mặc định đóng gói và phần override được quản trị riêng; phải kiểm thử thứ tự ưu tiên.
- Chọn **Git backend** khi cần lịch sử commit, review, tag, audit và rollback cấu hình theo revision.

Native backend cho phép Config Server đọc cấu hình từ nơi triển khai sẵn có mà không yêu cầu Git. Dù file được đóng gói trong classpath hay mount bên ngoài, client vẫn truy cập qua cùng API application/profile và nhận cấu hình trong Spring Environment. Quy trình vận hành cần xác nhận nguồn dữ liệu, giá trị hiệu lực và trạng thái refresh trước khi coi thay đổi đã được áp dụng trên toàn hệ thống.

