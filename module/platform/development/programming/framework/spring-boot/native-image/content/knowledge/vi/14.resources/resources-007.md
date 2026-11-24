# Đường dẫn tương đối, thư mục làm việc và khác biệt phân biệt chữ hoa, chữ thường

## 1. Vì sao đường dẫn có thể chạy trên máy dev nhưng lỗi trong native container?

Ứng dụng Spring Boot thường đọc classpath resource, file cấu hình, template, chứng chỉ hoặc dữ liệu từ filesystem. Một lỗi phổ biến là chương trình hoạt động trên máy phát triển nhưng không tìm thấy file khi chạy bằng GraalVM Native Image trong container.

Nguyên nhân thường không nằm ở compiler Java mà ở cách ứng dụng phân giải đường dẫn:

- Đường dẫn tương đối được tính từ **current working directory (CWD)** của process.
- Đường dẫn classpath được phân giải bởi classloader theo tên resource, không phải theo CWD.
- Linux thường phân biệt chữ hoa và chữ thường trong tên file; Windows mặc định thường không phân biệt.
- Container có filesystem riêng, layout khác máy host và có thể chạy dưới một user khác.
- Native executable không tự mang các file bên ngoài binary vào trong image.

Trong module **SPRING_BOOT_NATIVE_IMAGE**, cần hiểu rõ các quy tắc này để resource được tìm thấy nhất quán khi chạy trên JVM, native executable và runtime container.

## 2. Đường dẫn tuyệt đối và tương đối

**Đường dẫn tuyệt đối** xác định vị trí từ root của filesystem hoặc volume:

```text
Linux:   /etc/orders/rules.json
Windows: C:\orders\config\rules.json
```

**Đường dẫn tương đối** được diễn giải dựa trên một thư mục gốc đang có ngữ cảnh:

```text
config/rules.json
../shared/rules.json
./data/input.csv
```

Trong Java, khi dùng:

```java
Path path = Path.of("config/rules.json");
```

đường dẫn tương đối thường được phân giải theo thư mục làm việc hiện tại của process:

```java
Path absolute = path.toAbsolutePath();
System.out.println(absolute);
System.out.println("cwd = " + System.getProperty("user.dir"));
```

Nếu process khởi chạy từ `/app`, đường dẫn có thể trở thành `/app/config/rules.json`. Nếu khởi chạy từ `/`, cùng chuỗi tương đối có thể trở thành `/config/rules.json`.

Không nên giả định CWD luôn là thư mục chứa JAR hoặc native executable. CWD do cách khởi chạy process, cấu hình container `WORKDIR`, service manager hoặc orchestration quyết định.

## 3. Current working directory là gì?

CWD là thư mục làm việc mà process dùng để phân giải các đường dẫn tương đối. Trên Linux có thể kiểm tra:

```bash
pwd
```

Trong Java:

```java
System.out.println(System.getProperty("user.dir"));
```

Ví dụ Dockerfile:

```dockerfile
FROM eclipse-temurin:21-jre
WORKDIR /app
COPY application /app/application
COPY config/rules.json /app/config/rules.json
ENTRYPOINT ["/app/application"]
```

Với `WORKDIR /app`, CWD mặc định khi container chạy là `/app`, trừ khi runtime override working directory. Vì vậy, `Path.of("config/rules.json")` có thể trỏ đến `/app/config/rules.json`.

Nếu dùng:

```bash
docker run --workdir /tmp orders-service:1.0
```

CWD bị đổi thành `/tmp`, khiến cùng đường dẫn tương đối trỏ đến `/tmp/config/rules.json`. Ứng dụng có thể thất bại dù file vẫn tồn tại ở `/app/config/rules.json`.

Với dữ liệu quan trọng, nên dùng đường dẫn cấu hình tường minh hoặc mount path ổn định, không phụ thuộc ngầm vào CWD.

## 4. Đường dẫn classpath không phụ thuộc CWD

Classpath resource được tìm bằng classloader, không phải bằng cách ghép CWD với chuỗi tên file.

Ví dụ:

```java
try (InputStream input =
        getClass().getResourceAsStream("/schemas/invoice.json")) {
    if (input == null) {
        throw new IllegalStateException("Classpath resource missing");
    }
    // Đọc dữ liệu
}
```

Hoặc Spring:

```java
Resource resource =
        new ClassPathResource("schemas/invoice.json");
```

Resource này thường nằm trong `src/main/resources/schemas/invoice.json`, sau đó được copy vào output build/JAR. Nếu ứng dụng chạy từ `/tmp` hay `/app`, classloader vẫn tìm theo classpath đã thiết lập.

Ngược lại:

```java
new File("schemas/invoice.json")
```

tạo một filesystem path tương đối theo CWD; nó không có nghĩa là đọc resource bên trong JAR. Hai cách truy cập có thể cho kết quả khác nhau.

Trong Native Image, classpath resource còn phải được Native Image nhận diện hoặc đăng ký qua RuntimeHints khi không thể suy ra tĩnh. Đổi CWD không làm một classpath resource đã được đóng gói biến mất, nhưng resource thiếu metadata vẫn có thể không có trong executable.

## 5. Phân biệt chữ hoa, chữ thường trên filesystem

Tên file trên Linux thường phân biệt chữ hoa và chữ thường:

```text
config/Rules.json
config/rules.json
```

Đây là hai đường dẫn khác nhau trên filesystem Linux thông thường. Trên Windows mặc định, chúng thường được xem là cùng một tên file; macOS có thể dùng filesystem cấu hình phân biệt hoặc không phân biệt tùy volume.

Ví dụ code:

```java
Path path = Path.of("config/Rules.json");
```

Nếu repository thực tế lưu file là `config/rules.json`, code có thể chạy trên Windows nhưng thất bại trên Linux container với `NoSuchFileException`.

Classpath resource cũng cần khớp tên chính xác. Ví dụ:

```java
new ClassPathResource("Templates/invoice.html");
```

không tự động tương đương với `templates/invoice.html` trên Linux. ClassLoader tra cứu resource theo tên và phân biệt chữ hoa/thường trong môi trường Linux phổ biến.

Quy tắc an toàn: thống nhất tên thư mục/file chữ thường, dùng đúng chính tả trong code và kiểm tra trên Linux CI.

## 6. Phân biệt đường dẫn resource và đường dẫn filesystem

| Cách truy cập | Ví dụ | Quy tắc phân giải |
|---|---|---|
| Classpath resource | `classpath:schemas/invoice.json` | ClassLoader và resource đã đóng gói |
| Filesystem tương đối | `config/rules.json` | CWD của process |
| Filesystem tuyệt đối | `/etc/orders/rules.json` | Root filesystem/volume |
| Spring config data | `file:/etc/orders/` | Cơ chế external configuration của Spring Boot |
| URL resource | `https://config.example/rules.json` | Network client và endpoint từ xa |

Không nên thay thế một loại bằng loại khác mà không xem xét vòng đời. Classpath resource phù hợp với dữ liệu mặc định đi cùng ứng dụng; external file phù hợp với cấu hình và dữ liệu được cung cấp khi triển khai.

## 7. Dùng Path và Files một cách rõ ràng

Đối với external file, có thể inject base directory hoặc full path qua cấu hình:

```java
@ConfigurationProperties(prefix = "orders.rules")
public record RulesProperties(Path file) {
}
```

Ví dụ application config:

```yaml
orders:
  rules:
    file: /etc/orders/rules.json
```

Service đọc file:

```java
@Service
class RulesLoader {

    private final RulesProperties properties;

    RulesLoader(RulesProperties properties) {
        this.properties = properties;
    }

    String load() throws IOException {
        Path path = properties.file();

        if (!Files.isRegularFile(path)) {
            throw new FileNotFoundException(
                    "Rules file does not exist: " + path);
        }

        return Files.readString(path, StandardCharsets.UTF_8);
    }
}
```

Cách này giúp đường dẫn rõ ràng và có thể thay đổi theo môi trường mà không build lại native image. Cần bật configuration properties scanning hoặc đăng ký class bằng `@EnableConfigurationProperties(RulesProperties.class)`, tùy cấu trúc ứng dụng.

Nếu muốn hỗ trợ relative path, hãy xác định base directory rõ ràng thay vì phụ thuộc CWD:

```java
Path base = Path.of(
        System.getProperty("orders.config-dir", "/etc/orders"));
Path rules = base.resolve("rules.json").normalize();
```

Có thể kiểm tra path sau khi resolve và áp dụng chính sách bảo vệ chống path traversal nếu phần tên file đến từ input không tin cậy.

## 8. Đường dẫn trong container

Container có filesystem namespace riêng. File trên host không tự xuất hiện trong container nếu không được copy vào image hoặc mount.

Ví dụ:

```bash
docker run --rm \
  -v ./config:/etc/orders:ro \
  -e ORDERS_RULES_FILE=/etc/orders/rules.json \
  orders-service:1.0
```

Ứng dụng đọc `ORDERS_RULES_FILE` tại runtime. Thư mục host `./config` được Docker phân giải theo ngữ cảnh chạy lệnh Docker, sau đó mount vào `/etc/orders` trong container.

Một số điểm cần xác minh:

- Source path của bind mount có tồn tại trên host.
- Destination path nằm trong filesystem container và đúng với cấu hình ứng dụng.
- File được mount với quyền đọc cho user chạy process.
- CWD trong container không bị override ngoài dự kiến.
- Runtime image thực sự có các thư mục cha cần thiết.

Không dùng đường dẫn host như `C:\Users\...` trong cấu hình Linux container. Host path chỉ dùng để Docker tạo mount; ứng dụng trong container phải đọc destination path.

## 9. Path separator và chuẩn hóa đường dẫn

Windows thường hiển thị dấu gạch chéo ngược `\`, còn Linux dùng `/`. Java `Path` và `Paths` giúp xây dựng path theo hệ điều hành:

```java
Path config = Path.of("config", "rules.json");
```

Không nên nối chuỗi thủ công:

```java
String path = base + "\\config\\rules.json";
```

Cách nối chuỗi này dễ tạo path sai trên Linux. Dùng `resolve`:

```java
Path config = Path.of(base).resolve("config").resolve("rules.json");
```

`normalize()` loại bỏ các thành phần `.` và một số cặp `..` về mặt cú pháp, nhưng không tự kiểm tra file có tồn tại hoặc ngăn mọi trường hợp symlink/path traversal. Nếu path đến từ người dùng, cần kiểm tra path đã chuẩn hóa nằm trong thư mục được phép.

Đối với URL/classpath location, không dùng `Path` để xử lý tùy tiện. `classpath:`, `file:` và URI có quy tắc riêng; hãy dùng API Spring Resource hoặc URI phù hợp.

## 10. Tương tác với Spring Boot external configuration

Spring Boot có thể nạp config từ classpath và filesystem. Ví dụ:

```bash
SPRING_CONFIG_ADDITIONAL_LOCATION=file:/etc/orders/ ./application
```

Hoặc chỉ định location qua command line:

```bash
./application --spring.config.additional-location=file:/etc/orders/
```

Cấu hình external có thể chứa các property như database URL, đường dẫn rules hoặc feature threshold. Với Native Image, file cấu hình external vẫn được đọc lúc runtime nếu Spring Boot config data loader và filesystem hoạt động đúng.

Cần phân biệt config file external với classpath resource. Một file `/etc/orders/application.yml` không cần RuntimeHints resource pattern chỉ vì Spring Boot đọc nó từ filesystem. Ngược lại, `application.yml` nằm trong classpath phải có trong native image và được đóng gói phù hợp.

Không nhúng credentials vào classpath config hoặc binary. Dùng secret mount/environment hoặc secret manager phù hợp nền tảng triển khai.

## 11. Kiểm tra đường dẫn ở runtime

Khi lỗi không tìm thấy file, log các thông tin không nhạy cảm:

```java
Path path = configuredPath.toAbsolutePath().normalize();

logger.info("Working directory: {}", System.getProperty("user.dir"));
logger.info("Resolved rules path: {}", path);
logger.info("Rules file exists: {}", Files.exists(path));
```

Tránh log nội dung file hoặc secret. Các lệnh Linux hữu ích:

```bash
pwd
ls -l /etc/orders
stat /etc/orders/rules.json
```

Trong container tối giản, có thể không có `sh`, `ls` hoặc `stat`. Khi đó kiểm tra mount/permissions từ host hoặc dùng debug image tương thích; không giả định runtime image distroless có shell.

Với classpath resource, kiểm tra JAR:

```bash
jar tf application.jar
```

Với native image, việc kiểm tra file JAR không chứng minh resource đã được nhúng. Hãy xác minh RuntimeHints/build metadata và chạy code path đọc resource trong executable native.

## 12. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| `NoSuchFileException` trên container | Relative path được tính từ CWD khác | Ghi nhận `user.dir`, dùng absolute/configured path |
| Chạy Windows được, Linux lỗi | Sai chữ hoa/thường trong tên file | Sửa code hoặc tên file khớp chính xác |
| Classpath resource trả null | Sai resource path hoặc chưa đóng gói/hints | Kiểm tra classpath/JAR và RuntimeHints |
| File có trên host nhưng container không thấy | Chưa copy hoặc mount | Kiểm tra bind mount và destination |
| Permission denied | User container không có quyền đọc | Sửa ownership/mode hoặc mount read-only phù hợp |
| Lỗi chỉ ở native | Resource classpath không được đưa vào image | Đăng ký resource hints và build lại |
| Đường dẫn có dấu `\\` lỗi trên Linux | Nối chuỗi theo Windows | Dùng `Path.resolve` |
| Config runtime không được nạp | Sai config location hoặc precedence | Kiểm tra Spring Boot config data và log |

Phân loại lỗi trước khi sửa: classpath resource, filesystem path, CWD, case sensitivity hay permission. Mỗi loại cần cách xử lý khác nhau.

## 13. Bài thực hành: kiểm thử đường dẫn trên JVM và Native Image

**Bối cảnh:** dịch vụ Spring Boot có schema cố định trong classpath và file rules được mount vào container.

**Bước 1 — Tạo classpath resource.** Đặt `schemas/invoice.json` trong `src/main/resources`; đọc bằng `ClassPathResource`.

**Bước 2 — Tạo external file.** Cung cấp `/etc/orders/rules.json` bằng bind mount; đường dẫn được truyền qua `ORDERS_RULES_FILE`.

**Bước 3 — Ghi nhận CWD.** Log `user.dir` và resolved path; chạy process từ hai thư mục khác nhau để chứng minh relative path phụ thuộc CWD.

**Bước 4 — Kiểm tra case sensitivity.** Đổi một lần tên resource từ `invoice.json` thành `Invoice.json` trên Linux test environment và xác nhận tên phải khớp chính xác.

**Bước 5 — Chạy JVM.** Kiểm tra classpath resource và external file; thử file thiếu và quyền đọc không đủ.

**Bước 6 — Build native.** Đăng ký resource hint nếu cần, build executable và lặp lại cùng bộ test.

**Bước 7 — Chạy container.** Đặt `WORKDIR` rõ ràng, mount external file, chạy dưới user không phải root và kiểm tra endpoint đọc cả hai nguồn.

Tiêu chí hoàn thành: classpath resource được tìm độc lập với CWD; external path được resolve theo cấu hình rõ ràng; tên file đúng case; container mount và permission chính xác; JVM và native có hành vi nhất quán.

## 14. Kết luận

Đường dẫn tương đối phụ thuộc **current working directory**, còn classpath resource được tìm thông qua classloader. Linux thường phân biệt chữ hoa và chữ thường trong tên file, vì vậy code chạy trên Windows có thể lỗi khi chuyển sang Linux container. Container còn có filesystem và working directory riêng; file host chỉ xuất hiện bên trong khi được copy hoặc mount.

Với Spring Boot Native Image, hãy dùng ClassLoader/Spring Resource cho tài nguyên classpath, Path/Files cho external file, cấu hình CWD và mount path rõ ràng, dùng `Path.resolve` thay cho nối chuỗi thủ công và kiểm thử trên Linux runtime image. Các bước này giúp tránh lỗi đường dẫn giữa JVM, native executable và môi trường triển khai.
