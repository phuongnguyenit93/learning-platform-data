# Kiểm tra tài nguyên bị thiếu và tránh đóng gói dữ liệu bí mật

## 1. Hai rủi ro cần xử lý trước khi phát hành native image

Trong module **SPRING_BOOT_NATIVE_IMAGE**, Spring AOT chuẩn bị mã và metadata ở build time, sau đó GraalVM Native Image phân tích các đầu vào để tạo executable. Khi đóng gói ứng dụng, có hai lỗi dễ bị bỏ qua:

1. **Thiếu tài nguyên khi chạy native:** file template, schema, message bundle hoặc cấu hình có trong JAR/JVM nhưng không được đưa vào native executable, khiến một luồng nghiệp vụ lỗi khi truy cập.
2. **Đóng gói dữ liệu bí mật:** password, API token, private key, credential hoặc file môi trường bị đưa vào JAR, generated resources, native executable hay container image.

Hai vấn đề có liên quan đến classpath và resource metadata nhưng cách xử lý khác nhau. Tài nguyên ứng dụng cần thiết phải được khai báo để Native Image giữ lại; dữ liệu bí mật phải được cung cấp từ môi trường chạy và được bảo vệ bằng cơ chế quản lý secret.

**Nguyên tắc:** xác minh tài nguyên nào cần có trong artifact, chỉ đăng ký resource hints cho phạm vi cần thiết, và giữ credential bên ngoài mọi artifact được build.

## 2. Phân biệt classpath resource và file bên ngoài

Không phải mọi file ứng dụng đọc đều được xử lý giống nhau.

| Loại dữ liệu | Vị trí thường gặp | Cách truy cập | Có được đóng gói vào native image? |
| --- | --- | --- | --- |
| Classpath resource | `src/main/resources/`, resource trong dependency JAR | `ClassPathResource`, `ClassLoader.getResource`, `getResourceAsStream` | Có thể được đóng gói; cần resource metadata nếu không được phân tích tĩnh nhận diện |
| Resource bundle | `messages.properties`, file dịch thuật | `ResourceBundle`, message source | Cần bảo đảm bundle được giữ; có thể đăng ký resource bundle hint |
| External configuration | File trong thư mục mount hoặc đường dẫn cấu hình | Config Data, `FileSystemResource`, `Path` | Không tự trở thành một phần binary; phải có mặt ở runtime |
| Secret file | Secret manager mount, config tree, volume read-only | Environment hoặc file path được cấp lúc chạy | Nên giữ bên ngoài JAR/native image/container layer |
| Build output | `target/classes`, `build/resources/main`, generated resources | Classpath của task/build | Có thể được đóng gói nếu thuộc input artifact |

Ví dụ cấu trúc resource an toàn:

~~~text
src/main/resources/
  application.yml
  templates/
    invoice.html
  i18n/
    messages.properties
~~~

Các file template và message bundle là dữ liệu ứng dụng có thể đóng gói. Một file như `application-prod.yml` chứa password thật, `service-account.json` hoặc `private-key.pem` không nên nằm trong thư mục resource này.

### 2.1. Classpath resource khác external file

Classpath resource được tìm trong JAR/dependency hoặc trong classpath của ứng dụng. Ví dụ:

~~~java
ClassPathResource template =
    new ClassPathResource("templates/invoice.html");
try (InputStream input = template.getInputStream()) {
    // Đọc template.
}
~~~

Ngược lại, file ngoài ứng dụng có thể được đặt tại một mount path:

~~~java
Path secretFile = Path.of("/run/secrets/storage-password");
String password = Files.readString(secretFile).trim();
~~~

Resource hint cho Native Image không tạo ra file tại `/run/secrets/` và không cấp quyền đọc file hệ thống. File ngoài phải được cung cấp trong môi trường chạy, với đường dẫn và quyền truy cập phù hợp.

## 3. Vì sao resource có trên JVM nhưng thiếu trong native executable?

Trên JVM, classloader có thể tìm tài nguyên trong JAR khi ứng dụng yêu cầu. Với GraalVM Native Image, trình biên dịch sử dụng phân tích reachability và metadata để quyết định resource nào cần được đưa vào executable.

Một đường truy cập trực tiếp với tên hằng có thể được công cụ nhận diện trong một số trường hợp. Nhưng nếu tên resource được ghép từ property, tên tenant, locale hoặc dữ liệu runtime, trình phân tích có thể không biết file nào sẽ được yêu cầu:

~~~java
String templateName = environment.getProperty("app.invoice.template");
String path = "templates/" + templateName + ".html";

try (InputStream input =
         getClass().getClassLoader().getResourceAsStream(path)) {
    if (input == null) {
        throw new IllegalStateException("Không tìm thấy template: " + path);
    }
    // Render hóa đơn.
}
~~~

JVM có thể đọc file tương ứng nếu file nằm trên classpath. Native Image cần biết trước tập resource hợp lệ. Nếu không, `getResourceAsStream` có thể trả về `null` trong executable dù file từng tồn tại trong JAR.

Những nguyên nhân thường gặp:

- Tên resource được tạo động nên không được reachability analysis nhận diện.
- File chỉ có trong `src/test/resources`, không có trong resource của ứng dụng.
- Resource nằm trong một dependency tùy chọn nhưng dependency đó không có ở build classpath.
- Tên đường dẫn khác chữ hoa/thường; môi trường Linux phân biệt hoa/thường.
- Resource filtering hoặc task copy đã loại bỏ/đổi tên file.
- Native Image không nhận được resource hints phù hợp.

**Một hint không thể khôi phục file đã thiếu khỏi đầu vào.** Trước tiên phải xác nhận resource có trong output của Maven/Gradle hoặc JAR; sau đó mới cấu hình metadata để Native Image đóng gói nó.

## 4. Đăng ký resource hints với Spring AOT

Spring cung cấp `RuntimeHintsRegistrar` để khai báo các resource cần thiết cho native executable.

Giả sử ứng dụng đọc mọi template HTML trong `templates/`. Có thể đăng ký pattern:

~~~java
package com.example.invoice;

import org.springframework.aot.hint.RuntimeHints;
import org.springframework.aot.hint.RuntimeHintsRegistrar;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.ImportRuntimeHints;

@Configuration(proxyBeanMethods = false)
@ImportRuntimeHints(InvoiceResourceHints.class)
class InvoiceResourceConfiguration {
}

class InvoiceResourceHints implements RuntimeHintsRegistrar {
    @Override
    public void registerHints(RuntimeHints hints, ClassLoader classLoader) {
        hints.resources().registerPattern("templates/*.html");
    }
}
~~~

`@ImportRuntimeHints` giúp Spring AOT nạp registrar. Pattern được viết tương đối từ classpath root, không cần thêm dấu `/` ở đầu. Chỉ dùng `templates/*.html` nếu ứng dụng thực sự cần nhóm file đó.

Nếu chỉ đọc một file, đăng ký chính xác file:

~~~java
hints.resources().registerPattern("templates/invoice.html");
~~~

Với message bundle, có thể đăng ký base name:

~~~java
hints.resources().registerResourceBundle("i18n.messages");
~~~

Tên bundle phải tương ứng với package/path của resource, ví dụ `src/main/resources/i18n/messages.properties`.

### 4.1. Không dùng pattern quá rộng

Tránh đăng ký mọi resource nếu chỉ cần một nhóm nhỏ:

~~~java
// Không nên dùng như giải pháp mặc định:
hints.resources().registerPattern("**/*");
~~~

Pattern rộng có thể:

- đưa dữ liệu không cần thiết vào executable;
- tăng kích thước binary và thời gian native compilation;
- vô tình giữ lại file cấu hình nội bộ hoặc dữ liệu không nên phát hành;
- làm khó việc rà soát artifact và nguyên nhân resource được đóng gói.

Hãy lập danh sách resource theo tính năng. Với template, schema và bundle, dùng path hoặc pattern hẹp. Nếu resource thuộc dependency, kiểm tra thư viện có cung cấp reachability metadata sẵn không trước khi thêm hints trùng lặp.

### 4.2. Resource được sinh trong build

Nếu một task Maven/Gradle sinh file vào thư mục generated resources, cần bảo đảm task đó chạy trước bước đóng gói và output được thêm vào resource/classpath input phù hợp. `RuntimeHintsRegistrar` chỉ mô tả resource cần giữ; nó không thay thế task sinh file hoặc task copy resource.

Quy trình kiểm tra:

1. Xác nhận file có trong thư mục output resource.
2. Xác nhận file có trong JAR nếu ứng dụng đóng gói JAR trung gian.
3. Xác nhận hint có trong đầu vào AOT/native compilation.
4. Chạy native executable và đọc đúng resource đó.

## 5. Chẩn đoán tài nguyên bị thiếu theo từng lớp

Khi JVM đọc được file nhưng native executable không đọc được, hãy đi từ đầu vào đến runtime.

### Bước 1: xác nhận resource có trong source

Ví dụ file mong đợi:

~~~text
src/main/resources/templates/invoice.html
~~~

Kiểm tra đúng tên, phần mở rộng, chữ hoa/thường và đường dẫn. Không đặt file chỉ dùng trong test dưới `src/test/resources` nếu ứng dụng production cần nó.

### Bước 2: xác nhận resource được xử lý vào build output

Với Maven:

~~~bash
./mvnw process-resources
~~~

Kiểm tra file dưới `target/classes/templates/`.

Với Gradle:

~~~bash
./gradlew processResources
~~~

Kiểm tra file dưới `build/resources/main/templates/`.

### Bước 3: xác nhận resource nằm trong JAR

~~~bash
jar tf target/application.jar | grep 'templates/invoice.html'
~~~

Nếu lệnh không tìm thấy file, lỗi nằm ở resource processing/packaging hoặc đường dẫn artifact đang kiểm tra. Chưa cần sửa Native Image hints.

### Bước 4: kiểm tra resource metadata

Xem registrar có được import trong ApplicationContext AOT không, pattern có đúng classpath path không và resource có thực sự tồn tại trong dependency/application JAR không. Tránh giả định rằng một file JSON metadata tùy ý đã được GraalVM nhận; nếu dùng metadata dạng JSON, phải tuân thủ đúng schema và vị trí được phiên bản Native Image hỗ trợ.

### Bước 5: chạy lại native executable

Sau khi sửa hint hoặc resource input, build lại native image. Chạy đúng luồng đọc file; chỉ kiểm tra health endpoint là chưa đủ nếu endpoint đó không sử dụng template.

### Bảng chẩn đoán nhanh

| Quan sát | Nguyên nhân có khả năng | Hướng xử lý |
| --- | --- | --- |
| Không có file trong `target/classes`/`build/resources/main` | Resource processing hoặc source path sai | Sửa cấu hình Maven/Gradle, kiểm tra task copy/filter |
| Có trong build output nhưng không có trong JAR | Packaging exclude hoặc artifact đang kiểm tra sai | Kiểm tra Spring Boot Maven/Gradle packaging và tên JAR |
| Có trong JAR nhưng native không đọc được | Thiếu resource hint hoặc đường dẫn runtime khác | Đăng ký pattern hẹp, kiểm tra path/case |
| Chỉ lỗi trên Linux | Khác biệt chữ hoa/thường hoặc file permission | Chuẩn hóa tên file, kiểm tra quyền và mount |
| Resource ngoài filesystem không có | Volume chưa mount hoặc đường dẫn sai | Kiểm tra cấu hình container và quyền đọc |
| Resource có chứa secret | Dữ liệu nhạy cảm đã lọt vào source/build artifact | Gỡ khỏi resource, xoay vòng secret và phát hành artifact mới |

## 6. Vì sao không được đóng gói secret vào resource?

JAR và native executable là artifact có thể được tải xuống, lưu trong cache, đẩy lên registry hoặc phân phối cho nhiều môi trường. Một khi credential được đưa vào resource, generated file, hằng số trong mã hoặc container layer, người có quyền đọc artifact có thể tìm cách trích xuất nó.

Các dữ liệu không được đặt trong `src/main/resources` hoặc thư mục generated để đóng gói:

- mật khẩu database, Redis, message broker;
- API key, OAuth client secret, access token, refresh token;
- private key, file keystore/truststore có private key và mật khẩu;
- cloud service account JSON, access key/secret key;
- certificate bundle hoặc file cấu hình chứa credential riêng;
- file `.env` có giá trị thật, bản dump dữ liệu hoặc backup chứa thông tin nhạy cảm.

Certificate công khai, CA bundle công khai hoặc truststore không chứa private key có thể là tài nguyên ứng dụng hợp lệ. Tuy nhiên, cần kiểm tra nội dung trước khi đưa vào artifact; đừng chỉ dựa vào tên file.

### 6.1. Secret có thể lọt vào artifact bằng cách nào?

| Nguồn rủi ro | Ví dụ | Cách phòng tránh |
| --- | --- | --- |
| Source resource | `application-prod.yml` chứa password thật | Chỉ để placeholder trong resource; cấp giá trị runtime |
| File local bị copy | `.env`, `credentials.json`, `*.pem` | Đặt ngoài resource source set, loại khỏi packaging và quản lý bằng secret store |
| Resource filtering | Maven filtering hoặc Gradle `expand(...)` thay placeholder bằng secret | Không filter secret vào resource; giới hạn filtering cho file không nhạy cảm |
| AOT/build-time configuration | Giá trị bí mật được đưa vào môi trường khi chạy AOT hoặc custom code generation | Không cung cấp secret trong build job; không sinh mã chứa credential |
| Native compiler arguments | Truyền password/token qua `-D`, build argument hoặc command line | Tránh secret trong command line và compiler arguments |
| Container build | Docker `ARG`, `ENV`, copy secret vào layer hoặc build context | Dùng secret mount của builder/CI, không lưu secret trong image |
| Build logs/cache | In toàn bộ Environment, Maven debug log hoặc generated file | Mask secret, giới hạn quyền log/cache và không dump cấu hình nhạy cảm |

**Loại resource khỏi Native Image không phải biện pháp xử lý secret đã bị nhúng vào bytecode.** Nếu secret đã đi vào Java constant, generated AOT code, build argument hoặc một layer khác, chỉ xóa resource hint không làm secret biến mất.

## 7. Cung cấp cấu hình và secret ở runtime

### 7.1. Đặt placeholder trong application.yml

Có thể lưu tên property và placeholder trong resource:

~~~yaml
spring:
  datasource:
    url: ${DB_URL}
    username: ${DB_USERNAME}
    password: ${DB_PASSWORD}
~~~

File này không chứa credential thật. Khi chạy native executable, môi trường cung cấp các biến:

~~~bash
DB_URL='jdbc:postgresql://db.internal:5432/billing' \
DB_USERNAME='billing_app' \
DB_PASSWORD='value-from-secret-store' \
./target/billing-service
~~~

Trong CI/CD, giá trị thực phải được inject từ secret store của nền tảng và được mask khỏi log. Không commit file `.env` thật hoặc đưa secret vào tham số Maven/Gradle.

### 7.2. Dùng file secret được mount

Với Spring Boot Config Data, có thể nạp một config tree từ thư mục mount:

~~~yaml
spring:
  config:
    import: "optional:configtree:/run/secrets/"
~~~

Ví dụ runtime mount:

~~~text
/run/secrets/
  spring.datasource.username
  spring.datasource.password
~~~

Tên file trong config tree trở thành property key; nội dung file là giá trị. Như vậy `spring.datasource.password` được đọc từ file secret khi ứng dụng chạy, thay vì nằm trong JAR/native executable.

Nếu dùng file path riêng, ứng dụng có thể đọc bằng `Files.readString(Path.of(...))`; khi đó phải kiểm tra file tồn tại, encoding, quyền đọc và cách xử lý newline. Không ghi nội dung secret vào exception message hoặc log.

### 7.3. Docker và Kubernetes

Trong container, nên dùng secret mechanism của nền tảng:

- inject environment variable từ secret reference;
- mount secret thành file với quyền chỉ đọc và quyền truy cập tối thiểu;
- dùng workload identity/managed identity khi dịch vụ đích hỗ trợ, tránh lưu access key dài hạn.

Ví dụ Docker minh họa cách mount một file secret có sẵn trên host:

~~~bash
docker run --rm \
  --mount type=bind,src=/secure/runtime-secrets,dst=/run/secrets,readonly \
  -p 8080:8080 \
  billing-service:native
~~~

Đường dẫn `src` là ví dụ; cần thay bằng secret mount do môi trường vận hành quản lý. Không đưa thư mục secret vào Docker build context và không dùng `COPY` để đóng gói nó.

## 8. Bảo vệ secret trong AOT, Maven/Gradle và Buildpacks

Spring AOT chạy ApplicationContext trong build time để chuẩn bị cấu trúc ứng dụng. Vì vậy, build job nên dùng cấu hình không chứa credential thật. Nếu custom bean initialization hoặc code generation đọc secret lúc AOT, giá trị đó có thể xuất hiện trong generated output hoặc log tùy cách ứng dụng xử lý.

### Maven

- Không truyền password qua `-Ddb.password=...` hoặc ghi property bí mật vào `pom.xml`.
- Không bật resource filtering cho file có thể nhận secret từ Maven properties.
- Không lưu secret trong generated resources hoặc thư mục `target/`.
- Dùng secret store/CI credential binding cho những bước thực sự cần xác thực; ưu tiên tách chúng khỏi AOT/native compilation.

### Gradle

- Không đặt secret trong `build.gradle`, version catalog hoặc file properties được commit.
- Tránh `processResources { expand(...) }` hoặc `filter(...)` với giá trị credential.
- Không log `System.getenv()` hoặc toàn bộ Gradle project properties.
- Giữ secret ngoài `src/main/resources` và ngoài output generated.

### Buildpacks và container build

- `BP_NATIVE_IMAGE=true` là biến điều khiển buildpack, không phải nơi truyền application password.
- Không đưa secret qua `pack --env`, builder environment hoặc biến build chỉ để nó được lưu vào image.
- Không copy file credential vào build context.
- Nếu một bước build thật sự cần credential để tải dependency riêng, dùng secret mechanism được CI/builder hỗ trợ và bảo đảm giá trị không đi vào image layer, build metadata hay log.

### AOT condition không phải kho secret

Property quyết định bean graph có thể được đánh giá lúc AOT. Chỉ đưa các giá trị cấu trúc không nhạy cảm vào môi trường build. Password, token và private key phải được đọc khi runtime qua secret store hoặc mount path. Không dùng `@ConditionalOnProperty` với giá trị secret để quyết định cấu trúc ứng dụng.

## 9. Kiểm tra artifact để phát hiện resource và secret ngoài ý muốn

Kiểm tra trước khi publish nên gồm cả **tên file** và **nội dung file**.

### 9.1. Liệt kê JAR

~~~bash
jar tf target/billing-service.jar
~~~

Tìm những tên đáng ngờ:

~~~bash
jar tf target/billing-service.jar | grep -Ei '(^|/)(\.env|.*secret.*|.*credential.*|.*private.*key.*|.*keystore.*|.*password.*)$'
~~~

Lệnh này chỉ là bộ lọc theo tên file. Secret có thể nằm trong `application.yml`, file JSON tên bình thường hoặc bytecode, nên **không tìm thấy tên đáng ngờ không có nghĩa artifact sạch**.

### 9.2. Quét nội dung JAR và generated output

Giải nén vào thư mục tạm trong workspace CI, sau đó chạy secret scanner được tổ chức phê duyệt. Không in giá trị phát hiện ra log:

~~~bash
mkdir -p target/artifact-inspection
cd target/artifact-inspection
jar -xf ../billing-service.jar

# Chỉ tìm key/tên property đáng ngờ; không dump toàn bộ nội dung file.
grep -RIlE 'password|secret|api[_-]?key|private[_-]?key|access[_-]?token' .
~~~

Đây là bước rà soát sơ bộ theo từ khóa, có thể tạo false positive và không phát hiện mọi định dạng mã hóa. Nên bổ sung secret scanner có kiểm tra entropy/pattern, quét source, JAR, generated files, container image và lịch sử CI artifact. Khi phát hiện secret, không copy giá trị vào ticket/log để minh họa.

### 9.3. Kiểm tra native executable và container image

Với native executable, có thể dùng `strings` như một phép dò sơ bộ:

~~~bash
strings target/billing-service | grep -Ei 'password|secret|api[_-]?key|token'
~~~

`strings` không phải secret scanner đầy đủ: secret có thể được mã hóa, nén, chia nhỏ hoặc biểu diễn theo dạng không in được. Ngược lại, một chuỗi trùng từ khóa có thể chỉ là tên property hợp lệ.

Với container image:

~~~bash
docker history --no-trunc billing-service:native
~~~

Kiểm tra thêm filesystem/layers của image bằng công cụ scanner phù hợp. Docker history có thể cho thấy command hoặc metadata build, nhưng không chứng minh mọi layer đều sạch. Nếu secret từng được copy vào một layer rồi xóa ở layer sau, dữ liệu vẫn có thể tồn tại trong layer cũ.

### 9.4. Nếu phát hiện secret đã bị đóng gói

1. **Thu hồi/rotate secret ngay** ở hệ thống cấp phát; không chỉ xóa file khỏi source.
2. Xác định artifact, image tag, registry, cache và môi trường nào đã nhận dữ liệu.
3. Build lại từ source sạch, không truyền secret vào build/AOT.
4. Xóa/thu hồi artifact cũ theo quy trình quản lý registry và CI của tổ chức.
5. Kiểm tra log, cache và quyền truy cập để xác định phạm vi lộ lọt.

Xóa secret khỏi JAR hoặc tạo image mới không làm credential cũ mất hiệu lực; phải rotate credential đã bị lộ.

## 10. Ví dụ tổng hợp: template được đóng gói, password ở runtime

Giả sử dịch vụ hóa đơn cần template HTML và kết nối database.

**Resource được đóng gói:**

~~~text
src/main/resources/
  templates/invoice.html
  application.yml
~~~

`application.yml` chỉ chứa placeholder:

~~~yaml
spring:
  datasource:
    url: ${DB_URL}
    username: ${DB_USERNAME}
    password: ${DB_PASSWORD}
~~~

Đăng ký template:

~~~java
@Configuration(proxyBeanMethods = false)
@ImportRuntimeHints(InvoiceResourceHints.class)
class InvoiceConfiguration {
}

class InvoiceResourceHints implements RuntimeHintsRegistrar {
    @Override
    public void registerHints(RuntimeHints hints, ClassLoader classLoader) {
        hints.resources().registerPattern("templates/invoice.html");
    }
}
~~~

Build ứng dụng theo Maven hoặc Gradle sau khi đã cấu hình Spring AOT và Native Image. Kiểm tra JAR có `templates/invoice.html`; kiểm tra resource hints được AOT xử lý; build executable native.

Khi chạy container:

~~~bash
docker run --rm \
  -e DB_URL='jdbc:postgresql://db.internal:5432/billing' \
  -e DB_USERNAME='billing_app' \
  -e DB_PASSWORD='injected-at-runtime' \
  -p 8080:8080 \
  billing-service:native
~~~

Trong môi trường thật, `DB_PASSWORD` phải được inject từ secret store, không ghi literal vào lệnh trong tài liệu triển khai, shell history, Dockerfile hay CI log. Ví dụ trên dùng giá trị minh họa để thể hiện cơ chế.

Kiểm tra hai hành vi độc lập:

- Endpoint tạo hóa đơn đọc được `templates/invoice.html` trong native executable.
- Database connection nhận credential từ runtime environment/secret mount; khi kiểm tra JAR, generated resources, native binary và image không có password thật.

## 11. Checklist trước khi phát hành

- [ ] Mỗi classpath resource production có đường dẫn và mục đích rõ ràng.
- [ ] File cần đọc động đã có resource hints phù hợp.
- [ ] Không dùng pattern resource rộng hơn nhu cầu.
- [ ] Resource tồn tại trong build output/JAR trước khi build native.
- [ ] Đã chạy native executable trên các luồng đọc template, bundle, schema và resource quan trọng.
- [ ] Không có `.env`, credential JSON, private key hoặc file secret trong resource source set.
- [ ] Maven/Gradle resource filtering không chèn secret vào generated output.
- [ ] Build-time/AOT environment không chứa credential thật.
- [ ] Secret được cấp từ runtime environment, secret manager hoặc read-only mount.
- [ ] Đã quét JAR, generated output, native binary và container image bằng công cụ phù hợp.
- [ ] Không in giá trị secret vào log, exception, command line hoặc báo cáo CI.
- [ ] Nếu phát hiện secret đã đóng gói, đã rotate credential và xử lý artifact cũ.

**Ghi nhớ:** resource hint giải quyết việc Native Image giữ lại file ứng dụng cần đọc; nó không thay thế bước tạo/copy file vào build output. Secret phải ở ngoài JAR, generated code, native executable và container layers; chỉ cấp khi ứng dụng chạy. Kiểm tra cả sự hiện diện của tài nguyên cần thiết lẫn sự vắng mặt của dữ liệu bí mật trước khi phát hành.
