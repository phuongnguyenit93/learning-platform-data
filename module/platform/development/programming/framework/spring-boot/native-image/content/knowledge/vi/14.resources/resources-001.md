# Classpath resource khác với tệp bên ngoài binary

## 1. Vì sao cần phân biệt hai loại tài nguyên?

Ứng dụng Spring Boot thường đọc nhiều loại dữ liệu: file cấu hình, template email, schema JSON, chứng chỉ, ảnh, message bundle và file do người vận hành cung cấp. Một số tài nguyên nằm trong classpath của ứng dụng; số khác được mount hoặc đặt trên filesystem khi triển khai.

Khi chạy trên JVM, classpath thường bao gồm thư mục classes và các JAR dependency. Ứng dụng có thể dùng classloader để tìm resource trong những vị trí này. Khi chuyển sang **GraalVM Native Image**, executable được tạo ở build time. Native Image không tự mang toàn bộ filesystem hoặc mọi file trên máy build vào binary. Những **classpath resource cần dùng** phải được nhận diện và đưa vào image; những **tệp bên ngoài binary** tiếp tục được cung cấp từ filesystem/runtime environment.

Trong module **SPRING_BOOT_NATIVE_IMAGE**, phân biệt hai nhóm giúp tránh lỗi “JVM đọc được file nhưng native không tìm thấy”, đồng thời giữ cấu hình, secret và dữ liệu vận hành có thể thay đổi mà không phải build lại executable.

- **Classpath resource:** tài nguyên thuộc ứng dụng hoặc dependency, được truy cập qua classloader/resource API và thường được đóng gói cùng artifact.
- **External file:** tệp được đọc bằng đường dẫn filesystem tại runtime, ví dụ `/etc/orders/application.yml`, `/var/lib/orders/rules.json` hoặc file được mount vào container.

Đường dẫn trông giống nhau không quyết định loại tài nguyên. Cách ứng dụng truy cập và nơi tài nguyên được cung cấp mới là yếu tố quyết định.

## 2. Classpath resource trên JVM

Một tài nguyên có thể nằm trong:

```text
src/main/resources/
├── application.properties
├── templates/
│   └── invoice.html
├── schemas/
│   └── invoice-v1.json
└── messages/
    └── messages.properties
```

Maven/Gradle thường copy nội dung `src/main/resources` vào output classes và executable JAR. Java có thể đọc bằng classloader:

```java
try (InputStream input =
        getClass().getResourceAsStream("/schemas/invoice-v1.json")) {
    if (input == null) {
        throw new IllegalStateException("Schema resource not found");
    }
    // Đọc nội dung input
}
```

Hoặc dùng Spring Resource abstraction:

```java
Resource resource =
        new ClassPathResource("schemas/invoice-v1.json");

try (InputStream input = resource.getInputStream()) {
    // Đọc resource
}
```

Đối với resource classpath, ứng dụng không nên giả định luôn có một file vật lý để lấy bằng `new File(...)`. Resource trong JAR hoặc native image có thể không tương ứng với một đường dẫn filesystem thông thường. Dùng `InputStream` hoặc Spring `Resource` API thường an toàn hơn.

## 3. External file được đọc từ filesystem lúc chạy

Một file bên ngoài binary thường được chỉ định bằng đường dẫn cấu hình:

```java
Path rulesPath = Path.of(
        System.getProperty("orders.rules.path",
                "/etc/orders/rules.json"));

if (!Files.isRegularFile(rulesPath)) {
    throw new IllegalStateException(
            "Rules file does not exist: " + rulesPath);
}

try (InputStream input = Files.newInputStream(rulesPath)) {
    // Đọc rules từ filesystem
}
```

Trong container, file có thể được mount từ host, Kubernetes ConfigMap/Secret hoặc volume:

```bash
docker run --rm \
  -v ./config/rules.json:/etc/orders/rules.json:ro \
  -e ORDERS_RULES_PATH=/etc/orders/rules.json \
  orders-service:1.0
```

Ví dụ cần đồng bộ tên property với cách ứng dụng đọc nó; nếu dùng Spring Boot binding, có thể inject `orders.rules.path` qua `@ConfigurationProperties`. File external không cần được nhúng vào Native Image, miễn nó tồn tại và process có quyền đọc khi chạy.

Đây là lựa chọn phù hợp cho dữ liệu thay đổi theo môi trường, file cấu hình triển khai hoặc dữ liệu vận hành không nên đóng gói cố định vào executable.

## 4. Bảng so sánh classpath resource và external file

| Tiêu chí | Classpath resource | External file |
|---|---|---|
| Vị trí nguồn | `src/main/resources`, dependency JAR hoặc resource của thư viện | Filesystem, volume, mount hoặc đường dẫn runtime |
| Cách truy cập | ClassLoader, `Class.getResourceAsStream`, Spring `Resource` | `Path`, `Files`, `FileInputStream`, Spring `FileSystemResource` |
| Có nằm trong native binary? | Có thể được đưa vào image khi được cấu hình/nhận diện | Không tự động; thường tồn tại bên ngoài executable |
| Thay đổi nội dung | Thường cần build lại artifact/image | Có thể thay khi triển khai nếu ứng dụng hỗ trợ |
| Cần resource hints? | Có thể cần khi Native Image không tự suy ra đường dẫn | Không cần resource hint classpath chỉ vì file external |
| Quản lý secret | Không phù hợp để nhúng secret vào artifact | Có thể mount từ secret store với quyền truy cập phù hợp |
| Phụ thuộc môi trường | Ít phụ thuộc filesystem path | Phụ thuộc đường dẫn, mount, quyền và dung lượng filesystem |

Không nên nhầm external file với resource classpath chỉ vì file được mount vào một thư mục trùng tên với package. Một file ở `/app/config/app.yml` được đọc bằng filesystem API là external file, dù nó nằm bên cạnh executable.

## 5. Native Image xử lý classpath resource như thế nào?

Native Image thực hiện phân tích tĩnh và tạo image chứa các resource được nhận diện hoặc khai báo. Nếu code truy cập resource bằng một đường dẫn hằng, công cụ có thể tự nhận diện trong một số trường hợp. Nhưng khi tên resource được ghép từ property, tên file được tạo động hoặc resource nằm trong dependency được tải theo logic không tĩnh, công cụ có thể không biết phải đóng gói file nào.

Ví dụ:

```java
String schemaName = configuration.getProperty("schema.name");
String path = "schemas/" + schemaName + ".json";

try (InputStream input =
        getClass().getClassLoader().getResourceAsStream(path)) {
    // ...
}
```

Reachability analysis nhìn thấy việc gọi classloader nhưng không thể luôn biết giá trị `schemaName` trong mọi deployment. Resource tương ứng có thể bị bỏ khỏi image. Khi đó bản JVM tìm được file trong JAR, còn native executable nhận `null`.

Giải pháp là khai báo resource pattern qua Spring RuntimeHints hoặc reachability metadata của GraalVM. Pattern phải khớp resource thực tế trong classpath tại build time.

## 6. Đăng ký classpath resource bằng RuntimeHints

Spring cung cấp `RuntimeHints.resources()` để khai báo tài nguyên cần đóng gói:

```java
final class InvoiceResourceHints implements RuntimeHintsRegistrar {

    @Override
    public void registerHints(
            RuntimeHints hints,
            ClassLoader classLoader) {

        hints.resources().registerPattern(
                "schemas/invoice-*.json");
    }
}
```

Gắn registrar vào configuration:

```java
@Configuration(proxyBeanMethods = false)
@ImportRuntimeHints(InvoiceResourceHints.class)
class InvoiceConfiguration {
}
```

Pattern `schemas/invoice-*.json` yêu cầu các file khớp pattern được đưa vào resource metadata. Nếu chỉ có một file, có thể đăng ký tên cụ thể:

```java
hints.resources().registerPattern(
        "schemas/invoice-v1.json");
```

Các đường dẫn resource trong hints thường được khai báo tương đối với classpath root, không bắt đầu bằng dấu `/`. Kiểm tra API và cú pháp pattern theo phiên bản Spring Framework dự án đang sử dụng.

RuntimeHints chỉ giúp Native Image nhận biết resource có trong build inputs. Nó không thể đóng gói file external chỉ tồn tại trên máy production và không có trong classpath khi build.

## 7. Đọc classpath resource bằng Spring Resource API

Spring cung cấp abstraction `Resource` để code không phụ thuộc quá chặt vào nguồn dữ liệu:

```java
@Component
class InvoiceSchemaLoader {

    private final ResourceLoader resourceLoader;

    InvoiceSchemaLoader(ResourceLoader resourceLoader) {
        this.resourceLoader = resourceLoader;
    }

    InputStream openSchema(String version) throws IOException {
        Resource resource = resourceLoader.getResource(
                "classpath:schemas/invoice-" + version + ".json");

        if (!resource.exists()) {
            throw new FileNotFoundException(
                    "Schema not found: " + version);
        }
        return resource.getInputStream();
    }
}
```

Ví dụ dùng tên resource động, do đó cần khai báo các file có thể chọn qua hints. Cần import `ResourceLoader`, `Resource`, `InputStream` và exception phù hợp.

Nếu đường dẫn luôn cố định, code có thể dùng `ClassPathResource` trực tiếp. Nếu lựa chọn version đến từ runtime property, hãy bảo đảm toàn bộ tập resource hợp lệ được đóng gói vào native image.

Không dùng `resource.getFile()` một cách mặc định. Resource bên trong JAR hoặc native image không nhất thiết tồn tại như file thường; `getInputStream()` tương thích hơn với nhiều nguồn.

## 8. Đọc external file bằng Spring Resource API

Spring `ResourceLoader` hỗ trợ prefix như `file:` để chỉ rõ nguồn filesystem:

```java
Resource resource = resourceLoader.getResource(
        "file:/etc/orders/rules.json");

try (InputStream input = resource.getInputStream()) {
    // Đọc file ngoài binary
}
```

Với cấu hình có thể thay đổi, nên inject path bằng `@ConfigurationProperties`:

```java
@ConfigurationProperties(prefix = "orders.rules")
public record RulesProperties(Path path) {
}
```

Ví dụ cấu hình runtime:

```yaml
orders:
  rules:
    path: /etc/orders/rules.json
```

Đường dẫn này có thể được cung cấp bằng environment variable hoặc config file mount. Spring Boot binding hỗ trợ chuyển đổi string thành `Path` trong cấu hình thông thường. Cần xác nhận property source, default và validation để tránh lỗi khi file không tồn tại.

Không khai báo resource hint classpath cho `/etc/orders/rules.json` nếu file thực sự được mount ở runtime. Thay vào đó, kiểm tra filesystem, quyền truy cập và xử lý trường hợp thiếu file rõ ràng.

## 9. application.properties và config data

Spring Boot có quy tắc riêng để nạp application configuration. Cần phân biệt:

- `application.properties` hoặc `application.yml` nằm trong classpath: thường được đóng gói cùng ứng dụng.
- `application-prod.yml` trong classpath: resource profile-specific thuộc artifact nếu được đóng gói.
- `/etc/orders/application.yml`: file external được cung cấp bởi môi trường chạy.
- Environment variables/command-line arguments: nguồn cấu hình runtime, không phải classpath resource.

Một cấu hình external có thể được chỉ định qua cơ chế config data, ví dụ:

```bash
SPRING_CONFIG_ADDITIONAL_LOCATION=file:/etc/orders/
./application
```

Đây là cách yêu cầu Spring Boot nạp thêm config location; hành vi chính xác và cách ưu tiên property source phụ thuộc phiên bản Spring Boot và cấu hình khởi chạy. Cần bảo đảm file tồn tại trong container và process có quyền đọc.

Native Image vẫn có thể đọc config data external khi chạy nếu filesystem có file đó. Không cần nhúng file này vào image chỉ để Spring Boot nạp nó.

## 10. Secret và dữ liệu thay đổi theo môi trường

Không nên đóng gói secret vào classpath resource hoặc native binary. Nếu `application.properties` chứa mật khẩu database, token hay private key, những giá trị này có thể bị trích xuất từ artifact hoặc image.

Thực hành phù hợp:

- Giữ cấu hình không nhạy cảm mặc định trong classpath.
- Cung cấp secret qua secret manager, mounted secret file hoặc environment được quản lý an toàn.
- Chỉ cấp quyền đọc file secret cho user chạy process.
- Không in secret ra log hoặc đưa vào build arguments.
- Không tạo resource hints cho file secret external như thể nó là resource build-time.

Ví dụ đọc secret từ file mount:

```java
Path secretFile = Path.of("/run/secrets/payment-api-key");
String apiKey = Files.readString(secretFile).trim();
```

Đoạn code minh họa việc đọc file tại runtime; trong ứng dụng thực tế nên dùng cơ chế secret/config binding phù hợp và không log giá trị. Khi secret được rotate, ứng dụng cần có chiến lược reload hoặc restart theo khả năng hỗ trợ.

## 11. Resource trong dependency JAR

Classpath resource không chỉ đến từ `src/main/resources` của ứng dụng. Thư viện có thể cung cấp:

- Template hoặc message bundle.
- Schema, rule file và mapping metadata.
- Service provider configuration.
- File cấu hình mặc định hoặc dữ liệu đi kèm thư viện.

Ví dụ thư viện cung cấp `META-INF/services/com.example.Plugin` để Java `ServiceLoader` khám phá provider. Nếu ứng dụng sử dụng service discovery, cần kiểm tra cả resource metadata và cơ chế đăng ký provider tương ứng. Resource hints chỉ đóng gói file; chúng không tự bảo đảm class provider và constructor được reachability analysis giữ lại.

Với dependency đã hỗ trợ Native Image, thư viện có thể cung cấp reachability metadata sẵn. Ưu tiên metadata chính thức của dependency và tránh đăng ký trùng lặp tùy tiện. Nếu thư viện không khai báo resource động, ứng dụng có thể bổ sung RuntimeHintsRegistrar cho pattern cụ thể.

## 12. Resource pattern và phạm vi đăng ký

Pattern quá rộng có thể làm native image giữ nhiều resource không cần thiết; pattern quá hẹp khiến một số file hợp lệ bị thiếu. Hãy xác định tập file ứng dụng thực sự đọc.

| Pattern ví dụ | Ý định |
|---|---|
| `schemas/invoice-v1.json` | Một file cụ thể |
| `schemas/invoice-*.json` | Các schema invoice theo version |
| `templates/mail/*.html` | Template HTML trong thư mục mail |
| `i18n/messages*.properties` | Các bundle message theo locale |

Cú pháp pattern được hỗ trợ và cách match cần kiểm tra theo API Spring/GraalVM version. Không giả định wildcard trong RuntimeHints giống hoàn toàn cú pháp glob của shell hoặc regex.

Đối với resource nằm trong subdirectory, kiểm tra chính xác classpath path, phân biệt chữ hoa/thường trên Linux và đảm bảo Maven/Gradle đã copy resource vào output. Có thể xem nội dung JAR bằng:

```bash
jar tf target/orders-service.jar
```

Với Spring Boot executable JAR, resource ứng dụng thường nằm trong `BOOT-INF/classes/`, còn resource dependency nằm trong các JAR dưới `BOOT-INF/lib/`. Vị trí cụ thể phụ thuộc cách đóng gói.

## 13. Chẩn đoán lỗi resource trên native

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| `getResourceAsStream` trả null | Resource không được đóng gói hoặc sai path | Kiểm tra JAR/build output và resource hints |
| JVM đọc được, native không đọc được | Tên resource được tạo động hoặc thiếu metadata | Đăng ký pattern và build lại |
| File external không tồn tại | Volume chưa mount hoặc sai đường dẫn | Kiểm tra container mount và runtime config |
| Permission denied | User/container không có quyền đọc | Điều chỉnh ownership/mode hoặc mount permissions |
| Resource có trong JAR nhưng thiếu ở native | Metadata/resource pattern chưa được Native Image nhận | Kiểm tra AOT hints và native build log |
| Đọc file bằng `getFile()` thất bại | Resource không phải filesystem file | Dùng `getInputStream()` |
| Chỉ lỗi trên Linux | Khác biệt case-sensitive hoặc path separator | Chuẩn hóa resource path và kiểm tra chữ hoa/thường |
| Secret không cập nhật | Secret bị nhúng lúc build hoặc ứng dụng không reload | Chuyển sang external runtime source và xác định reload strategy |

Khi điều tra, xác định trước resource là classpath hay external. Không thêm resource hints để sửa một file external bị mount sai; cũng không mount file vào container để thay thế việc đóng gói classpath resource cần có trong executable.

## 14. Kiểm thử classpath và external file

Một bộ test nên xác minh hai cơ chế riêng biệt.

Classpath resource test:

```java
@Test
void invoiceSchemaIsAvailable() throws IOException {
    Resource resource =
            new ClassPathResource("schemas/invoice-v1.json");

    assertThat(resource.exists()).isTrue();

    try (InputStream input = resource.getInputStream()) {
        assertThat(input.read()).isNotEqualTo(-1);
    }
}
```

External file test nên tạo file tạm hoặc mount fixture trong integration environment, truyền path qua cấu hình runtime rồi xác minh ứng dụng đọc được. Không dùng đường dẫn máy developer cố định trong test chạy CI.

Với Native Image:

1. Chạy test RuntimeHints để xác nhận registrar đăng ký pattern.
2. Build native executable.
3. Chạy endpoint/service thực sự đọc classpath resource.
4. Chạy cùng executable với external file được mount tại đường dẫn test.
5. Thử thiếu file, sai quyền và resource path không tồn tại để xác minh thông báo lỗi.
6. Chạy trong runtime container thực tế, vì host build có thể có resource hoặc file mà container không có.

Unit test JVM không đủ chứng minh classpath resource đã được đưa vào Native Image. Cần native integration test hoặc chạy binary thực tế.

## 15. Bài thực hành: một classpath schema và một external rules file

**Bối cảnh:** dịch vụ Spring Boot xử lý hóa đơn. JSON schema cố định được đóng gói trong ứng dụng; bộ rules nghiệp vụ thay đổi theo từng deployment.

**Bước 1 — Tạo classpath resource.** Đặt `schemas/invoice-v1.json` trong `src/main/resources`, đọc qua `ClassPathResource`.

**Bước 2 — Đăng ký RuntimeHints.** Tạo registrar khai báo `schemas/invoice-v1.json` hoặc pattern thực tế, gắn qua `@ImportRuntimeHints`.

**Bước 3 — Tạo external rules file.** Đọc `/etc/orders/rules.json` bằng `Path` hoặc `FileSystemResource`, nhận path từ runtime configuration.

**Bước 4 — Kiểm thử JVM.** Xác nhận cả schema và rules được đọc đúng, bao gồm trường hợp external file thiếu.

**Bước 5 — Build native.** Chạy Spring AOT và GraalVM Native Image; kiểm tra classpath schema vẫn đọc được.

**Bước 6 — Chạy container.** Mount rules file vào đúng đường dẫn, chạy executable dưới user production và xác minh cả hai nguồn resource.

**Bước 7 — Thay rules file.** Cập nhật file external và chạy lại process theo cơ chế ứng dụng hỗ trợ; schema classpath không thay đổi nếu không build lại.

Tiêu chí hoàn thành: classpath resource có mặt trong native image, external file được cung cấp từ runtime filesystem, secret không bị đóng gói và ứng dụng xử lý rõ ràng trường hợp thiếu tài nguyên.

## 16. Kết luận

Classpath resource và external file có vòng đời khác nhau. **Classpath resource** thuộc ứng dụng/dependency và cần được Native Image nhận diện, đóng gói bằng phân tích hoặc RuntimeHints khi cần. **External file** được cung cấp từ filesystem khi chạy, phụ thuộc mount, đường dẫn và quyền truy cập; nó không tự được đưa vào binary.

Với Spring Boot Native Image, hãy dùng Resource/ClassLoader API cho classpath, Files/Path hoặc Spring `file:` Resource cho external file, đăng ký resource pattern chính xác và giữ secret/dữ liệu thay đổi theo môi trường bên ngoài executable. Kiểm thử cả hai loại trên native executable trong container đích để tránh khác biệt giữa JVM, máy build và production.
