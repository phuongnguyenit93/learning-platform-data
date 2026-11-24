# Chạy binary Spring Boot Native Image với tham số, biến môi trường và cấu hình cần thiết

> **Chương:** Ứng dụng đầu tiên  
> **Module:** `SPRING_BOOT_NATIVE_IMAGE`  
> **Mục tiêu:** Chạy executable Spring Boot đã biên dịch bằng Spring AOT và GraalVM Native Image; cấu hình bằng tham số dòng lệnh, biến môi trường và tệp bên ngoài; kiểm tra giá trị có hiệu lực và nhận diện những giới hạn AOT khi đổi cấu hình ở runtime.

## 1. Chạy bản native khác chạy JAR như thế nào?

Spring Boot có thể chạy dưới dạng JAR bằng JVM hoặc dưới dạng **executable native** đã biên dịch ahead-of-time bằng GraalVM Native Image. Spring AOT chuẩn bị mô hình bean, mã khởi tạo và các runtime hints cần thiết trong bước build, sau đó Native Image tạo binary cho một hệ điều hành và kiến trúc đích.

```mermaid
flowchart LR
    A["Mã Spring Boot + dependencies"] --> B["Spring AOT"]
    B --> C["GraalVM Native Image"]
    C --> D["Executable native"]
    D --> E["CLI / environment / config file"]
    E --> F["SpringApplication khởi động"]
    F --> G["Endpoint sẵn sàng"]
```

Ví dụ:

```bash
# Chạy bản JVM
java -jar target/native-demo.jar --server.port=9090

# Chạy bản native Linux/macOS
./target/native-demo --server.port=9090
```

Lệnh thứ hai **không khởi động HotSpot JVM**. Tuy nhiên, nếu chương trình giữ `SpringApplication.run(..., args)` và cấu hình Spring Boot thông thường, nó vẫn hiểu các property như `server.port`, `logging.level.root` và `spring.config.additional-location`.

Cần phân biệt **tham số ứng dụng** với **tham số launcher JVM**. Dạng `--server.port=9090` là tham số Spring Boot. Các cờ `-Xms`, `-Xmx`, `-XX:...` dùng với `java` không được mặc định xem là cờ hợp lệ của executable native. Việc tuning bộ nhớ bản native phải dựa vào tùy chọn mà GraalVM Native Image và bản binary cụ thể hỗ trợ.

Binary native thường được build riêng cho Linux, Windows hoặc macOS và một kiến trúc CPU như `x86_64` hay `aarch64`. Một binary Linux không tự chạy trên Windows, và binary còn phụ thuộc các thư viện hệ thống nếu dùng liên kết động.

## 2. Ứng dụng mẫu để quan sát cấu hình

Giả sử dự án Spring Boot có `spring-boot-starter-web`. Tạo một endpoint đọc giá trị cấu hình từ Spring `Environment`. Ví dụ này không cần database để dễ kiểm tra.

**`src/main/java/com/example/nativedemo/NativeDemoApplication.java`**

```java
package com.example.nativedemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.core.env.Environment;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class NativeDemoApplication {

    private final Environment environment;

    public NativeDemoApplication(Environment environment) {
        this.environment = environment;
    }

    public static void main(String[] args) {
        SpringApplication.run(NativeDemoApplication.class, args);
    }

    @GetMapping("/greeting")
    public String greeting() {
        return environment.getProperty(
                "app.greeting",
                "Xin chào từ Spring Boot Native Image");
    }
}
```

**`src/main/resources/application.yml`**

```yaml
spring:
  application:
    name: native-demo

server:
  port: 8080

app:
  greeting: "Xin chào từ cấu hình mặc định"

logging:
  level:
    root: INFO
```

Trong ví dụ này, `app.greeting` là **custom property** của ứng dụng. `/greeting` cho phép thấy ngay property thực sự được chọn từ file, environment hay tham số khi khởi động.

### Build executable

Dự án cần JDK/GraalVM tương thích với Spring Boot và plugin **GraalVM Native Build Tools** đã cấu hình. Với dự án có sẵn hạ tầng build:

```bash
# Maven: sử dụng profile native của dự án
./mvnw -Pnative native:compile

# Hoặc Gradle: sử dụng task do native plugin cung cấp
./gradlew nativeCompile
```

Vị trí đầu ra thường gặp:

| Build tool | Đường dẫn thông dụng | Ghi chú |
|---|---|---|
| Maven | `target/<ten-executable>` | Tên phụ thuộc `artifactId`, `finalName` hoặc plugin |
| Gradle | `build/native/nativeCompile/<ten-executable>` | Tên phụ thuộc cấu hình build |
| Windows native | `<ten-executable>.exe` | Phải build cho Windows |
| Linux/macOS native | `<ten-executable>` | Cần quyền execute và đúng hệ điều hành |

**Các lệnh tiếp theo giả định executable Linux/macOS là `target/native-demo`.** Hãy thay bằng đúng đường dẫn mà dự án thực tế sinh ra. Bài này tập trung vận hành binary đã build; lệnh Maven/Gradle có thể cần cấu hình plugin bổ sung tùy dự án.

## 3. Cách 1 — Truyền tham số dòng lệnh

Cú pháp quen thuộc của Spring Boot là `--spring.property=value`. Với ứng dụng mẫu:

```bash
./target/native-demo \
  --server.port=9090 \
  --app.greeting="Xin chào từ command line"
```

Khi ứng dụng đã sẵn sàng, mở terminal thứ hai:

```bash
curl --fail --show-error http://127.0.0.1:9090/greeting
```

Kết quả mong đợi:

```text
Xin chào từ command line
```

Trên Windows PowerShell (dùng binary **được build cho Windows**):

```powershell
.\target\native-demo.exe --server.port=9090 --app.greeting="Xin chào từ PowerShell"
```

Bảng những tham số hữu ích:

| Tham số | Tác dụng |
|---|---|
| `--server.port=9090` | Đặt cổng HTTP của ứng dụng |
| `--server.address=127.0.0.1` | Chỉ lắng nghe trên loopback, phù hợp thử nghiệm local |
| `--logging.level.root=WARN` | Giảm mức log tổng quát |
| `--app.greeting="..."` | Ghi đè giá trị do ứng dụng tự định nghĩa |
| `--spring.profiles.active=prod` | Chọn profile cấu hình; phải xét giới hạn AOT về topology bean |
| `--spring.config.additional-location=optional:file:./config/` | Bổ sung thư mục cấu hình ngoài |
| `--spring.config.location=file:/etc/native-demo/application.yml` | Thay thế các vị trí tìm cấu hình mặc định bằng vị trí chỉ định |

**Cẩn thận khi dùng CLI:**

- Ghi đúng `--server.port=9090`; đừng thay bằng `-Dserver.port=9090` chỉ vì quen chạy `java -jar`.
- Dùng dấu ngoặc phù hợp shell khi giá trị có khoảng trắng, ký tự `$` hoặc `&`.
- Spring Boot mặc định đưa command-line arguments vào `Environment`. Nếu ứng dụng chủ động dùng `SpringApplication.setAddCommandLineProperties(false)`, các property này sẽ không được nạp theo cách mặc định.
- Không truyền password/token qua command line khi có cơ chế an toàn hơn: chúng có thể xuất hiện trong process listing, shell history hoặc hệ thống thu thập log.

## 4. Cách 2 — Cấp biến môi trường

Biến môi trường phù hợp để chạy **cùng một binary** trong local, CI/CD, Docker hoặc Kubernetes. Spring Boot dùng cơ chế relaxed binding cho nhiều tên property: dấu chấm/gạch ngang trong tên property được ánh xạ sang dạng in hoa với dấu gạch dưới.

| Spring property | Biến môi trường phổ biến | Ý nghĩa |
|---|---|---|
| `server.port` | `SERVER_PORT` | Cổng web server |
| `app.greeting` | `APP_GREETING` | Thông điệp demo |
| `spring.profiles.active` | `SPRING_PROFILES_ACTIVE` | Profile |
| `logging.level.root` | `LOGGING_LEVEL_ROOT` | Log level |
| `spring.datasource.url` | `SPRING_DATASOURCE_URL` | JDBC URL nếu dùng database |
| `spring.datasource.username` | `SPRING_DATASOURCE_USERNAME` | Tên người dùng database |
| `spring.datasource.password` | `SPRING_DATASOURCE_PASSWORD` | Mật khẩu database |

**Bash (Linux/macOS):**

```bash
export SERVER_PORT=9091
export APP_GREETING="Xin chào từ biến môi trường"
export LOGGING_LEVEL_ROOT=INFO

./target/native-demo
```

Ở terminal khác:

```bash
curl --fail --show-error http://127.0.0.1:9091/greeting
```

Kết quả mong đợi là `Xin chào từ biến môi trường`.

Có thể đặt env **chỉ cho một tiến trình**:

```bash
SERVER_PORT=9092 APP_GREETING="Cấu hình một tiến trình" ./target/native-demo
```

**PowerShell:**

```powershell
$env:SERVER_PORT = "9093"
$env:APP_GREETING = "Xin chào từ PowerShell"

.\target\native-demo.exe

# Dọn biến trong phiên PowerShell sau khi thử nghiệm
Remove-Item Env:SERVER_PORT
Remove-Item Env:APP_GREETING
```

Không bắt buộc đặt placeholder trong `application.yml`: Spring Boot đã biết đọc OS environment như một nguồn property. Tuy vậy, khi muốn ánh xạ **một tên env tùy ý** sang property, có thể sử dụng placeholder:

```yaml
app:
  greeting: "${WELCOME_MESSAGE:Xin chào mặc định}"
```

Khi đó, `WELCOME_MESSAGE` cấp giá trị cho `app.greeting` nếu có; nếu không, Spring dùng fallback sau dấu `:`.

**Lưu ý kỹ thuật:** ánh xạ env cho logger có tên package/class dài và phân biệt hoa/thường không phải lúc nào cũng được bảo toàn vì một số phép chuẩn hóa tên mất thông tin chữ hoa. Với logging chi tiết theo từng class, nên ưu tiên cấu hình dạng file hoặc cơ chế được Spring Boot hỗ trợ tương ứng.

## 5. Cách 3 — Dùng file cấu hình bên ngoài

### 5.1. Tại sao cần external configuration?

Tệp `src/main/resources/application.yml` được đưa vào build của ứng dụng. Khi tạo Native Image, resource phù hợp được đưa vào artifact thông qua quá trình AOT/native. **Sửa source YAML sau khi build không khiến binary cũ thay đổi.**

Trong vận hành, người dùng thường muốn một executable chạy ở nhiều môi trường. Spring Boot cho phép đọc `application.yml`, `application.properties` và các biến thể theo profile từ **filesystem lúc khởi động**.

Ví dụ bố trí:

```text
/opt/native-demo/
  native-demo
  config/
    application.yml
```

Nội dung file ngoài:

```yaml
server:
  port: 9094

app:
  greeting: "Cấu hình từ file ngoài"

logging:
  level:
    root: INFO
```

Mặc định Spring Boot có các vị trí tra cứu cấu hình liên quan thư mục làm việc, bao gồm `./` và `./config/`. Tuy nhiên, working directory của systemd, Docker hoặc IDE có thể khác lúc chạy bằng terminal. Để tránh phụ thuộc vị trí làm việc, nên chỉ rõ đường dẫn.

### 5.2. `spring.config.additional-location`

Để **bổ sung** một nơi tìm cấu hình bên ngoài:

```bash
./target/native-demo \
  --spring.config.additional-location=optional:file:./config/
```

Trong tham số này:

- `spring.config.additional-location` thêm location ngoài vào tập location thông thường.
- `file:./config/` là một đường dẫn tương đối theo **working directory của tiến trình**, không phải mặc nhiên theo vị trí của binary.
- Dấu `/` cuối cần có khi chỉ định một **directory** để Spring Boot tự tìm `application.yml` hoặc `application.properties`.
- `optional:` cho phép chạy nếu location không tồn tại. **Không dùng `optional:` cho file cấu hình bắt buộc**, vì thiếu file có thể bị bỏ qua và ứng dụng chạy với giá trị mặc định.

Để dùng đường dẫn tuyệt đối:

```bash
./target/native-demo \
  --spring.config.additional-location=file:/etc/native-demo/
```

Hoặc dùng env thay vì CLI:

```bash
export SPRING_CONFIG_ADDITIONAL_LOCATION="file:/etc/native-demo/"
./target/native-demo
```

Phân biệt hai property thường bị nhầm:

| Property | Hành vi | Khi nào dùng |
|---|---|---|
| `spring.config.additional-location` | **Bổ sung** location vào những nơi tìm config mặc định | Có default trong binary và muốn file ngoài ghi đè một số property |
| `spring.config.location` | **Thay thế** tập location mặc định bằng những vị trí chỉ định | Muốn kiểm soát chính xác toàn bộ nguồn config được tìm |

Nếu chuyển từ `additional-location` sang `location` mà file ngoài không khai báo các property từng có trong file đóng gói, một số giá trị mặc định có thể không còn được tìm thấy. Đây là khác biệt vận hành cần kiểm tra.

### 5.3. Cấu hình theo profile

Ví dụ tạo `/etc/native-demo/application-prod.yml`:

```yaml
app:
  greeting: "Xin chào từ cấu hình prod"

logging:
  level:
    root: WARN
```

Chạy:

```bash
./target/native-demo \
  --spring.profiles.active=prod \
  --spring.config.additional-location=file:/etc/native-demo/
```

Spring Boot sẽ nạp config data liên quan profile đã kích hoạt theo quy tắc thứ tự location và profile. Một file YAML cũng có thể chứa nhiều tài liệu ngăn bởi `---`:

```yaml
app:
  greeting: "Giá trị mặc định"

---
spring:
  config:
    activate:
      on-profile: prod

app:
  greeting: "Giá trị cho prod"
```

**Quan trọng với Spring AOT:** chọn profile lúc chạy binary có thể quyết định giá trị runtime như log level, endpoint hoặc thông điệp. Nhưng những annotation và điều kiện như `@Profile`, `@ConditionalOnProperty` làm thay đổi **tập bean** thường đã được Spring đánh giá ở quá trình AOT **tại build time**. Một binary không tự tạo thêm mọi bean vừa được bật bằng runtime profile mới. Nếu thay đổi profile làm đổi topology của application context, hãy dùng profile phù hợp ngay khi chạy AOT và build/kiểm thử binary cho cấu hình đó.

## 6. Nguồn nào được ưu tiên khi trùng property?

Giả sử `server.port` xuất hiện ở bốn nơi. Trong ví dụ thông thường sau, thứ tự ưu tiên **từ cao tới thấp** là:

| Nguồn | Giá trị port | Kết quả khi mọi nguồn đồng thời hiện diện |
|---|---:|---|
| Command line `--server.port=9100` | 9100 | **Được chọn** |
| Environment `SERVER_PORT=9090` | 9090 | Bị CLI ghi đè |
| File config bên ngoài nạp với ưu tiên cao | 8085 | Bị env/CLI ghi đè |
| File config đóng gói trong ứng dụng | 8080 | Giá trị mặc định |

Đây chỉ là bốn nguồn phổ biến. Spring Boot còn hỗ trợ Java system properties, `SPRING_APPLICATION_JSON`, các loại config import, test property sources và các nguồn chuyên biệt khác. Thứ tự giữa các **config documents** còn chịu ảnh hưởng location, file theo profile và thứ tự import. Không suy từ bảng rằng mọi external file luôn cao hơn mọi nguồn khác.

Đặc biệt, `spring.config.location`, `spring.config.additional-location` và `spring.config.name` được dùng **rất sớm trong quá trình tìm config**. Nên cấp các giá trị này qua command line hoặc environment, thay vì đặt vào một file chưa được Spring tìm thấy.

### Thử precedence với ứng dụng mẫu

Giữ `application.yml` đóng gói có `server.port=8080` và `app.greeting="Đóng gói"`. Tạo `./config/application.yml`:

```yaml
server:
  port: 8085

app:
  greeting: "File ngoài"
```

Chạy:

```bash
APP_GREETING="Từ môi trường" ./target/native-demo \
  --spring.config.additional-location=file:./config/ \
  --server.port=9100
```

Kỳ vọng ứng dụng phục vụ tại `http://127.0.0.1:9100/greeting` và trả `Từ môi trường`. Property `server.port` lấy từ CLI, còn `app.greeting` lấy từ environment. Mỗi property được phân giải **độc lập** theo nguồn có định nghĩa và mức ưu tiên của nó.

Nếu cần khảo sát quá trình tìm cấu hình ở môi trường phát triển:

```bash
./target/native-demo \
  --spring.config.additional-location=file:./config/ \
  --logging.level.org.springframework.boot.context.config=TRACE
```

Log TRACE giúp theo dõi các bước nạp config data, nhưng có thể rất dài nên chỉ bật khi chẩn đoán.

## 7. Ranh giới giữa cấu hình runtime và build time trong Native Image

Sự khác biệt quan trọng nhất của Spring Boot Native Image là **mô hình bean đã được xử lý một phần từ trước**. Không phải thay đổi nào tại runtime cũng có thể khiến ứng dụng native tái tạo cấu trúc Spring context.

| Loại thông tin | Có thể thay lúc chạy cùng binary? | Ví dụ |
|---|---|---|
| Cổng HTTP | **Có** | `SERVER_PORT=9090` |
| Endpoint, timeout, credential dùng bởi các bean đã có | **Thông thường có** | `SPRING_DATASOURCE_URL`, secret, property business |
| Log level | **Thông thường có** | `LOGGING_LEVEL_ROOT=WARN` |
| Profile làm thay đổi **giá trị** trong file config | **Có**, nếu không xung đột với ràng buộc AOT | `application-prod.yml` đổi thông điệp |
| Profile/condition tạo thêm bean không có ở thời điểm AOT | **Không thể kỳ vọng** | `@Profile("prod")` trên một `@Bean` mới |
| Thêm JAR/plugin hoặc class động từ filesystem sau khi build | **Không** theo cách classpath JVM linh hoạt | Plugin chỉ tồn tại sau deploy |
| Sửa resource **bên trong binary** | **Không** | Template/config nhúng muốn thay phải build lại |
| Thêm metadata reflection/resource còn thiếu | **Cần build lại** trong tình huống phải đổi hints | Tính năng chỉ lỗi ở nhánh runtime native |

Ví dụ:

```java
@Profile("cloud")
@Bean
CloudStorageClient cloudStorageClient() {
    return new CloudStorageClient();
}
```

Nếu lúc build AOT bean này không nằm trong application context, chỉ đặt `SPRING_PROFILES_ACTIVE=cloud` ở runtime không bảo đảm tạo lại bean mới. Thay vào đó, với bean đã được đưa vào binary, thay đổi URL endpoint đọc từ runtime property có thể hoàn toàn hợp lệ.

Một cách phân định hữu ích:

- **Thông tin quyết định cấu trúc khi build:** tập bean, `@Conditional`, một số profile, dependency, lớp dùng động và resource cần đóng gói.
- **Thông tin vận hành lúc chạy:** port, host, URL, timeout, mức log, secret và những giá trị không đổi cấu trúc bean.

Phân định hai nhóm này trước khi dùng chung một binary giữa môi trường development, staging và production.

## 8. Quản lý secret và cấu hình quan trọng

**Không đưa mật khẩu thực vào lệnh CLI, mã nguồn, Dockerfile hoặc ứng dụng đã biên dịch.** Native binary không phải kho chứa bí mật: chuỗi hoặc resource đóng vào executable có thể bị phân tích và trích xuất.

Với ứng dụng có datasource, có thể dùng environment được cấp qua secret manager/hạ tầng deploy:

```bash
export SPRING_DATASOURCE_URL="jdbc:postgresql://db.internal:5432/orders"
export SPRING_DATASOURCE_USERNAME="orders_app"

# Mật khẩu được cấp riêng bởi cơ chế quản lý secret của môi trường.
./target/native-demo
```

Ứng dụng REST ví dụ ở phần 2 **không có dependency database**; các biến `SPRING_DATASOURCE_*` chỉ minh họa cách đặt tên cho dự án thực tế có JDBC/DataSource.

Một cách khác là mount secret thành file và dùng **Spring Boot config tree**:

```yaml
spring:
  config:
    import: "configtree:/run/secrets/"
```

Ví dụ khi thư mục đã được mount, file `/run/secrets/spring.datasource.password` có thể cung cấp property `spring.datasource.password`. Dùng `optional:configtree:/run/secrets/` chỉ nếu ứng dụng được phép chạy khi thư mục secrets không có; không nên biến thiếu secret bắt buộc thành sự cố âm thầm.

Ngay cả biến môi trường cũng cần giới hạn quyền xem, tránh ghi toàn bộ environment vào log hoặc crash dump. Với HTTPS/TLS, kiểm tra quyền đọc certificate/truststore và việc native binary/container có đủ CA certificates cần thiết.

## 9. Chạy native binary trong Docker

Container image đóng gói tiến trình native cùng hệ điều hành tối thiểu cần thiết; container **không thay đổi cách Spring Boot phân giải các property**.

Ví dụ Dockerfile cho executable **Linux** đã biên dịch đúng kiến trúc và dùng các thư viện mà image nền đáp ứng:

```dockerfile
FROM debian:bookworm-slim
WORKDIR /app

COPY target/native-demo /app/native-demo
RUN chmod 755 /app/native-demo

EXPOSE 8080
ENTRYPOINT ["/app/native-demo"]
```

Image thực tế cần khớp kiến trúc, libc, thư viện động và certificate; có thể cấu hình user không phải root nếu deployment yêu cầu.

Build và chạy:

```bash
docker build -t native-demo:local .

docker run --rm \
  --name native-demo \
  -p 8081:8080 \
  -e SERVER_PORT=8080 \
  -e APP_GREETING="Xin chào từ container" \
  native-demo:local
```

Kiểm tra từ host:

```bash
curl --fail --show-error http://127.0.0.1:8081/greeting
```

Ở ví dụ này, `8080` là **cổng Spring Boot lắng nghe trong container** còn `8081` là **cổng host** được publish. Dòng `EXPOSE 8080` của Dockerfile chỉ mang tính khai báo, bản thân nó không mở port trên host.

Mount file config ngoài trong Bash:

```bash
docker run --rm \
  -p 8081:8080 \
  -v "$PWD/deploy-config:/config:ro" \
  -e SPRING_CONFIG_ADDITIONAL_LOCATION="file:/config/" \
  native-demo:local
```

Đặt `deploy-config/application.yml` trên host để Spring Boot nạp file tại `/config/application.yml` trong container. Nếu file ngoài đổi `server.port` thành `9090` thì container phải publish theo `-p 8081:9090`; nếu muốn giữ mapping cũ, khai báo `SERVER_PORT=8080` để ghi đè port từ file.

Trong Kubernetes, nguyên tắc tương đương: dùng `env`, `ConfigMap`, `Secret` hoặc volume mount và cấu hình readiness probe. Một container ở trạng thái `Running` chưa chứng minh ứng dụng đã thực sự sẵn sàng nhận request.

## 10. Khi khởi động bằng systemd hoặc nền tảng quản lý tiến trình

Điểm dễ gây lỗi là **working directory**. Cùng một lệnh `file:./config/` có thể tham chiếu thư mục khác nhau khi chạy từ terminal, systemd hoặc container.

Ví dụ file unit Linux tối giản:

```ini
[Unit]
Description=Spring Boot Native Demo
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=nativeapp
WorkingDirectory=/opt/native-demo
Environment=SERVER_PORT=8080
Environment=SPRING_CONFIG_ADDITIONAL_LOCATION=file:/etc/native-demo/
ExecStart=/opt/native-demo/native-demo
Restart=on-failure
RestartSec=3

[Install]
WantedBy=multi-user.target
```

Ví dụ giả định user `nativeapp` đã tồn tại, binary có quyền execute và file config ngoài có quyền read. Mục đích là chỉ rõ ba yếu tố: **`ExecStart` dùng binary**, **`WorkingDirectory` ổn định**, **cấu hình được cấp qua environment**.

Đối với dịch vụ HTTP, cần kiểm tra graceful shutdown nếu muốn hoàn tất request đang xử lý:

```yaml
server:
  shutdown: graceful

spring:
  lifecycle:
    timeout-per-shutdown-phase: 20s
```

Hãy thử dừng tiến trình bằng tín hiệu phù hợp trên hệ đích và kiểm tra timeout thực tế; không mặc định mọi kết nối tự được xử lý xong khi container dừng.

## 11. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân khả dĩ | Hướng xử lý |
|---|---|---|
| `Permission denied` | Thiếu quyền execute, thư mục không cho truy cập hoặc mount `noexec` | Kiểm tra quyền và vị trí chạy |
| `Exec format error` | Binary khác OS hoặc CPU architecture | Build đúng nền tảng và kiến trúc |
| File binary tồn tại nhưng báo `No such file or directory` | Dynamic loader hoặc thư viện hệ thống không phù hợp | Kiểm tra libc/loader và dependencies của binary |
| Port không như mong đợi | Property bị nguồn khác ghi đè hoặc tên env không đúng | Xác minh CLI, env, file và log startup |
| `Port already in use` | Có tiến trình khác giữ cổng | Chọn port mới hoặc dừng tiến trình cũ |
| Không tìm thấy `application.yml` ngoài | Sai working directory, đường dẫn, quyền đọc hoặc dùng `optional:` | Dùng absolute path và bỏ `optional:` khi bắt buộc |
| Đổi profile nhưng thiếu bean | Topology đã được Spring AOT quyết định lúc build | Build lại với điều kiện/profile phù hợp |
| JVM JAR chạy tốt nhưng native lỗi template/serialization | Thiếu RuntimeHints/reflection/resource hoặc thư viện chưa tương thích | Test chức năng thật trên binary, bổ sung hints và rebuild |
| HTTPS thất bại trong container | CA certificates/truststore hoặc thư viện cần thiết không có | Kiểm tra TLS, base image và đường dẫn chứng chỉ |
| Container không truy cập được từ host | Sai `-p`, `server.port`, bind interface hoặc chưa ready | Kiểm tra port nội bộ, mapping và readiness |

### Chẩn đoán theo trình tự

**Bước 1. Kiểm tra binary và môi trường.** Trên Linux:

```bash
ls -l ./target/native-demo
file ./target/native-demo
```

**Bước 2. Chạy tối giản với port riêng.**

```bash
./target/native-demo --server.port=9191 --app.greeting="smoke-test"
```

**Bước 3. Gọi chức năng thật.** Ở terminal khác:

```bash
curl --fail --show-error --max-time 5 http://127.0.0.1:9191/greeting
```

**Bước 4. Thêm từng nguồn cấu hình.** Thử environment, sau đó thêm file ngoài. Xem property nào bị ghi đè. Khi xác định file nào được nạp, có thể bật TRACE tạm thời cho `org.springframework.boot.context.config`.

**Bước 5. Nếu chỉ native bị lỗi, kiểm thử chức năng trên cả JVM và native của cùng commit.** Kiểm tra những nhánh đòi reflection, dynamic proxy, resource, TLS, JSON và các kết nối ngoài. Build thành công chưa đồng nghĩa ứng dụng tương thích hoàn toàn.

## 12. Bài thực hành: cùng một executable, ba cấu hình

Mục tiêu là **không build lại binary** trong ba lượt chạy. Dừng lượt trước khi chạy lượt tiếp theo.

**Lượt A — Cấu hình mặc định:**

```bash
./target/native-demo
curl --fail --show-error http://127.0.0.1:8080/greeting
```

Kỳ vọng: `Xin chào từ cấu hình mặc định`.

**Lượt B — Dùng environment:**

```bash
SERVER_PORT=9091 APP_GREETING="Từ env" ./target/native-demo
```

Ở terminal khác, gọi `http://127.0.0.1:9091/greeting`. Kỳ vọng: `Từ env`.

**Lượt C — Kết hợp file ngoài và command line:**

Tạo `./config/application.yml` với:

```yaml
server:
  port: 9092

app:
  greeting: "Từ file ngoài"
```

Chạy:

```bash
./target/native-demo \
  --spring.config.additional-location=file:./config/ \
  --server.port=9093
```

Ứng dụng phải nghe ở **9093** vì CLI ghi đè port của file ngoài; `/greeting` phải trả **Từ file ngoài**. Thử thêm `APP_GREETING="Từ env"` để xác minh environment ghi đè riêng property đó.

### Ghi kết quả kiểm tra

| Lượt chạy | Nguồn cấu hình chính | Port kỳ vọng | Phản hồi `/greeting` |
|---|---|---:|---|
| A | Config đóng gói | 8080 | Xin chào từ cấu hình mặc định |
| B | Environment | 9091 | Từ env |
| C | File ngoài + CLI | 9093 | Từ file ngoài |

Sau khi xác minh runtime config, thử một `@Profile` ảnh hưởng tập bean trong dự án riêng và so sánh build time với runtime. Đây là cách thấy rõ ranh giới AOT, tránh nghĩ “đổi profile” luôn đồng nghĩa “đổi toàn bộ cấu trúc ứng dụng” trong binary native.

## 13. Checklist triển khai

- [ ] Binary được build cho đúng OS, CPU architecture và đáp ứng yêu cầu thư viện hệ thống của môi trường đích.
- [ ] Command khởi chạy dùng executable phù hợp, có quyền execute và đường dẫn đúng.
- [ ] CLI, OS environment và external config đều được kiểm tra trên **binary thật**.
- [ ] Các đường dẫn file config dùng absolute path khi môi trường triển khai thay đổi working directory.
- [ ] File cấu hình bắt buộc gây lỗi nếu thiếu; không dùng `optional:` để che lỗi.
- [ ] Profile/conditional ảnh hưởng bean topology đã được chuẩn bị đúng trong AOT build.
- [ ] Secrets không bị đưa vào Git, log, history hoặc binary.
- [ ] Port nội bộ, Docker/Kubernetes mapping, health/readiness và shutdown đã thử nghiệm.
- [ ] Các chức năng dùng reflection/resource/TLS/database đã có integration test trên native executable.
- [ ] Khi so sánh với bản JVM, đo thời gian từ start tới **readiness** và RAM thực tế trong cùng workload; không lấy kích thước file binary làm bộ nhớ đang dùng.

## 14. Tổng kết

Ứng dụng Spring Boot Native Image vẫn dùng các cơ chế **externalized configuration** quen thuộc: tham số `--property=value`, biến môi trường như `SERVER_PORT`, tệp `application.yml` theo profile và location ngoài. Những cơ chế đó cho phép vận hành một binary trên các môi trường có cùng mô hình bean, giảm nhu cầu build lại chỉ để đổi port, URL hoặc mức log.

Giới hạn cốt lõi là **Spring AOT đã xử lý một phần cấu trúc ứng dụng ở build time**. Đổi giá trị runtime không tương đương thay đổi classpath, các bean đã được lựa chọn hoặc các hints đã biên dịch. Vì vậy, cần vừa xác minh property thực tế có hiệu lực khi khởi động vừa chạy smoke test và integration test trên binary native trước khi triển khai.

### Tài liệu tham khảo

- [Spring Boot Reference — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html)
- [Spring Boot Reference — GraalVM Native Images](https://docs.spring.io/spring-boot/reference/packaging/native-image/introducing-graalvm-native-images.html)
- [Spring Boot Reference — Developing Your First GraalVM Native Application](https://docs.spring.io/spring-boot/reference/packaging/native-image/developing-your-first-application.html)
- [Spring Framework Reference — Ahead of Time Optimizations](https://docs.spring.io/spring-framework/reference/core/aot.html)
