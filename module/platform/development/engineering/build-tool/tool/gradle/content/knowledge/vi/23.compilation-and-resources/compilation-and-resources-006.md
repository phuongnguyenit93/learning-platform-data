# Lọc biến môi trường trong resources và tránh rò rỉ thông tin bí mật với Gradle

## 1. Vấn đề: một resource được tạo lúc build có thể trở thành dữ liệu công khai

Trong Gradle, thư mục `src/main/resources` thường chứa file cấu hình, mẫu văn bản, hình ảnh, chứng chỉ công khai, thông điệp, schema và những tài nguyên ứng dụng cần đọc bằng classpath. Task `processResources` sao chép các file này vào output; đối với project Java thông thường, chúng có thể được đưa vào JAR, ứng dụng phân phối, Docker image hoặc artifact được CI lưu trữ.

Một nhu cầu hợp lệ là thay biến môi trường **công khai** vào resource khi build. Ví dụ:

- `PUBLIC_LABEL=Staging Demo` để tạo một tên hiển thị trong `app.properties`.
- `PUBLIC_BUILD_CHANNEL=beta` để ghi nhãn artifact thử nghiệm.
- `PUBLIC_DOCS_URL=https://docs.example.org` để đưa một URL công khai vào HTML hoặc resource metadata.

Nhưng nhu cầu nguy hiểm là thay **bí mật** vào cùng đường đi:

- `DB_PASSWORD`, `API_TOKEN`, `PRIVATE_KEY`, `CLOUD_SECRET_ACCESS_KEY`.
- Mật khẩu production, access token CI, refresh token, credential repository.
- Giá trị kết nối có chứa username/password hoặc URL có embedded token.

**Nguyên tắc trọng tâm:** Nếu một giá trị được thay vào resource lúc build, hãy mặc định rằng nó có thể bị **lưu lại trong artifact** và được người có quyền tải artifact đọc được. JAR chỉ là một định dạng archive; file `.properties` bên trong không được mã hóa chỉ vì nó nằm trong `.jar`.

Bài học này giải thích luồng `processResources`, cách dùng `providers.environmentVariable` và `CopySpec.expand` đúng chỗ, khai báo inputs để Gradle theo dõi thay đổi, thiết kế build “một lần, triển khai nhiều môi trường”, và các ranh giới cần giữ để **không đưa secret vào resource, log, cache hoặc artifact**.

## 2. Luồng tài nguyên Java trong Gradle

Project áp dụng plugin `java` hoặc `application` thường có luồng:

```text
src/main/resources/
    |
    +-- app.properties.template  (mẫu đầu vào)
    +-- messages.txt             (file tĩnh)
    |
    v
:processResources (Copy task chuyên biệt)
    |
    +-- sao chép, đổi tên, mở rộng template nếu cấu hình
    |
    v
build/resources/main/
    |
    +-- app.properties           (resource đã render)
    +-- messages.txt
    |
    +-------------------+
                        |
                        v
                 :classes / :jar
                        |
                        v
                  app JAR / distribution
                        |
                        v
              Java ClassLoader đọc resource
```

Tùy plugin, task và cách đóng gói, đường đi output cuối cùng có thể khác. Điều quan trọng là **resource được xử lý không chỉ phục vụ máy developer**: nó có thể đi vào sản phẩm được chia sẻ.

Một số thuật ngữ cần tách biệt:

| Thành phần | Ý nghĩa |
| --- | --- |
| `src/main/resources` | Nguồn tài nguyên thuộc project |
| `processResources` | Task xử lý/sao chép resources cho source set main |
| `ProcessResources` | Kiểu task Gradle hỗ trợ các thao tác CopySpec |
| `filesMatching(...)` | Giới hạn phép xử lý vào những file khớp mẫu |
| `expand(...)` | Mở rộng template theo các biến được cung cấp |
| `build/resources/main` | Output tài nguyên đã xử lý trong cấu trúc Java phổ biến |
| `jar` | Đóng gói classes và resources vào artifact JAR |
| `ClassLoader.getResourceAsStream(...)` | Đọc resource từ classpath khi ứng dụng chạy |

**Không nhầm compile Java với lọc resource.** Task `compileJava` xử lý mã nguồn `.java`; `processResources` xử lý các file tài nguyên. Task `jar` có thể lấy output của cả hai. Mã Java có thể biên dịch sạch nhưng JAR vẫn mang secret nếu build đã chèn secret vào resource.

## 3. Ba loại dữ liệu và nơi chúng nên tồn tại

Trước khi dùng `System.getenv` trong build script, hãy phân loại dữ liệu.

| Loại dữ liệu | Ví dụ | Có nên nhúng vào resource/JAR? | Cách dùng gợi ý |
| --- | --- | --- | --- |
| Công khai, không nhạy cảm | Tên ứng dụng, kênh beta, URL trang tài liệu công khai | Có thể, nếu chấp nhận artifact khác nhau giữa môi trường | Lọc bằng `processResources` với whitelist |
| Cấu hình môi trường không bí mật nhưng thay đổi thường xuyên | Hostname nội bộ không chứa credential, feature flag deploy | Tùy chính sách, thường nên đọc lúc chạy | Runtime environment/config injection |
| Bí mật hoặc credential | Mật khẩu DB, access token, private key | **Không** | Secret manager hoặc runtime environment/volume/identity phù hợp |

Ngay cả giá trị không phải secret cũng có thể là thông tin nội bộ không được công bố: hostname quản trị, endpoint staging, đường dẫn nội bộ hoặc mã khách hàng. **Tên biến có tiền tố `PUBLIC_` không tự chứng minh nó an toàn**. Giá trị cần được phân loại và được phê duyệt theo mục đích xuất bản.

Nếu build tạo artifact để triển khai ở staging rồi production, việc nhúng hostname/môi trường vào artifact có thể phá vỡ ý tưởng **build once, deploy many**. Khi có thể, hãy dùng cùng một artifact và cung cấp cấu hình cần thiết **lúc ứng dụng khởi động**.

## 4. API Gradle để lấy biến môi trường: Provider thay vì đọc tùy tiện

Gradle có `ProviderFactory.environmentVariable(name)`. Trong Kotlin DSL:

```kotlin
val publicLabel = providers.environmentVariable("PUBLIC_LABEL")
    .orElse("Gradle resources")
```

`publicLabel` là `Provider<String>`, không phải giá trị String đã đọc ngay ở mọi trường hợp. Điều đó giúp Gradle quản lý giá trị đầu vào và tương tác tốt hơn với cấu hình lười.

Groovy DSL tương đương:

```groovy
def publicLabel = providers.environmentVariable('PUBLIC_LABEL')
    .orElse('Gradle resources')
```

### 4.1. Vì sao không dùng `System.getenv(...)` khắp build script?

Cú pháp Java vẫn có thể đọc biến môi trường:

```kotlin
val label = System.getenv("PUBLIC_LABEL") ?: "Gradle resources"
```

Nhưng trong Gradle hiện đại, `providers.environmentVariable(...)` thường phù hợp hơn vì có thể được kết nối với inputs của task và giúp biểu diễn một nguồn giá trị được quản lý. Việc gọi `System.getenv` trực tiếp trong cấu hình không phải lúc nào cũng tự gây lỗi, nhưng **không tự tạo ra quan hệ input/output rõ ràng cho task**.

Một ví dụ thiếu an toàn về tính đúng đắn của build:

```kotlin
tasks.named("processResources") {
    doLast {
        println(System.getenv("PUBLIC_LABEL"))
    }
}
```

Đoạn trên không lọc resource, in dữ liệu ra console và đọc giá trị ở một điểm khó kiểm soát. Nó chỉ dùng để minh họa **điều không nên làm**, không phải ví dụ cần thực thi. Nếu đổi biến môi trường, không có gì trong code đó biểu diễn resource template hoặc tính hợp lệ của output.

### 4.2. `orElse` không phải thao tác che giấu secret

`orElse("Gradle resources")` chỉ cung cấp giá trị dự phòng khi provider không có giá trị. Nó **không mã hóa**, **không redact log** và **không xác minh giá trị đầu vào đã an toàn**. Với credential quan trọng, việc dùng fallback mặc định yếu hoặc rỗng có thể gây hành vi nguy hiểm. Đừng đặt token giả “default-token” trong source rồi tưởng đó là chiến lược quản lý bí mật.

### 4.3. Không cần đọc mọi biến môi trường

Chỉ đọc **tên biến đã được duyệt**:

```kotlin
providers.environmentVariable("PUBLIC_LABEL")
```

Tránh lấy toàn bộ environment rồi đưa vào template:

```kotlin
// NGUY HIỂM: ví dụ sai, không sử dụng.
val everyEnvironmentVariable = System.getenv()
```

Mặc dù chương trình có thể lấy map này, việc đưa cả environment vào `expand` hoặc `filter` có nguy cơ làm lộ token CI, cloud credentials, PATH nội bộ hoặc các biến nhạy cảm khác.

## 5. `expand` là gì và giới hạn vào file nào?

`ProcessResources` là một task dựa trên sao chép; nó hỗ trợ những cấu hình tương tự `CopySpec`. Phép `expand(mapOf(...))` cho phép một file văn bản nguồn có placeholder được thay theo mapping.

File mẫu:

```properties
app.title=${label}
```

Khi mapping là `label = "Gradle resources"`, kết quả:

```properties
app.title=Gradle resources
```

Các điểm cần nhớ:

- `expand` hỗ trợ cú pháp Groovy template, không chỉ tìm-thay chuỗi thuần.
- Chỉ áp dụng filter cho file văn bản cần render; không biến toàn bộ images, JAR, certificates, binary resources thành template.
- `filesMatching("app.properties.template")` giới hạn hành động vào file phù hợp thay vì mọi resource.
- File gốc có thể được đổi tên thành `app.properties` khi copy.
- Nếu input chứa dấu xuống dòng, dấu `=`, backslash, dấu `$` hoặc biểu thức template phức tạp, output `.properties` có thể bị hỏng hoặc mang nội dung ngoài dự kiến.
- **Không dùng template không đáng tin** như nơi thực thi các biểu thức tùy ý; chỉ cho phép template nằm trong source được review.

Với tên hiển thị đơn giản, ta có thể chấp nhận whitelist ký tự ASCII an toàn. Với dữ liệu tổng quát hơn (URL, Unicode, JSON, YAML), cần xử lý **escaping/serialization theo đúng định dạng đích**; `expand` không phải bộ mã hóa bảo mật tự động cho mọi loại file.

## 6. Ví dụ hoàn chỉnh: Java 17 + Gradle Kotlin DSL, chỉ lọc giá trị công khai

Dự án này chạy được mà không cần thư viện bên ngoài, chỉ cần JDK 17 và một phiên bản Gradle tương thích. Biến `PUBLIC_LABEL` có thể được cấp hoặc không; ví dụ **không đọc token/mật khẩu**.

### 6.1. Cây file

```text
safe-resources-lab/
├── settings.gradle.kts
├── build.gradle.kts
└── src/
    └── main/
        ├── java/
        │   └── demo/
        │       └── Main.java
        └── resources/
            └── app.properties.template
```

**File `settings.gradle.kts`:**

```kotlin
rootProject.name = "safe-resources-lab"
```

**File `src/main/resources/app.properties.template`:**

```properties
app.title=${label}
```

**File `build.gradle.kts`:**

```kotlin
plugins {
    application
}

java {
    toolchain.languageVersion.set(JavaLanguageVersion.of(17))
}

application {
    mainClass.set("demo.Main")
}

// Chỉ đọc một biến công khai đã được cho phép.
val publicLabel = providers.environmentVariable("PUBLIC_LABEL")
    .orElse("Gradle resources")
    .map { raw ->
        // Không đưa input tùy ý vào cú pháp .properties / Groovy template.
        require(raw.matches(Regex("[A-Za-z0-9 ._-]{1,60}"))) {
            "PUBLIC_LABEL must be 1..60 safe ASCII characters"
        }
        raw
    }

// ProcessResources là task sao chép resource của source set main.
tasks.named<org.gradle.language.jvm.tasks.ProcessResources>("processResources") {
    // Gradle theo dõi thay đổi giá trị công khai trong task inputs.
    inputs.property("publicLabel", publicLabel)

    // Chỉ biến đổi đúng một template, không quét tất cả resources.
    filesMatching("app.properties.template") {
        name = "app.properties"
        expand(mapOf("label" to publicLabel.get()))
    }
}
```

**File `src/main/java/demo/Main.java`:**

```java
package demo;

import java.io.IOException;
import java.io.InputStream;
import java.util.Properties;

public final class Main {
    private Main() {
    }

    public static void main(String[] args) throws IOException {
        Properties properties = new Properties();

        try (InputStream input =
                     Main.class.getResourceAsStream("/app.properties")) {
            if (input == null) {
                throw new IllegalStateException("Resource app.properties not found");
            }
            properties.load(input);
        }

        System.out.println(properties.getProperty("app.title"));
    }
}
```

### 6.2. Lệnh build và stdout mặc định

Nếu project đã có Gradle Wrapper, dùng Wrapper. Nếu tạo thư mục mới chưa có Wrapper, cần một phiên bản Gradle tương thích đã cài để tạo Wrapper một lần:

```bash
gradle wrapper
```

Trên Linux/macOS:

```bash
./gradlew --quiet run
```

Trên Windows PowerShell:

```powershell
.\gradlew.bat --quiet run
```

Khi `PUBLIC_LABEL` không được thiết lập, stdout **do `Main.main` in ra**:

```text
Gradle resources
```

Đây là output của ứng dụng; Gradle có thể in thêm log trong môi trường cụ thể. `Properties.load(InputStream)` đọc file theo định dạng `.properties`. Vì ví dụ giới hạn label ở ASCII nên không gặp yêu cầu encoding Unicode phức tạp.

### 6.3. Đổi giá trị công khai qua environment

Linux/macOS:

```bash
PUBLIC_LABEL="Staging Demo" ./gradlew --quiet run
```

Windows PowerShell:

```powershell
$env:PUBLIC_LABEL = "Staging Demo"
.\gradlew.bat --quiet run
Remove-Item Env:PUBLIC_LABEL
```

Stdout:

```text
Staging Demo
```

Không cần sửa `src/main/resources/app.properties.template`. Giá trị được dùng từ environment khi task `processResources` được thực thi.

**Lưu ý:** nếu bạn chạy Gradle theo chế độ offline, task này vẫn có thể chạy khi Gradle và toolchain đã sẵn sàng vì ví dụ không cần thư viện remote. Nhưng việc dùng Gradle Wrapper chưa được tải hoặc JDK 17 toolchain chưa tồn tại vẫn có thể yêu cầu setup ngoài ví dụ.

### 6.4. Xem output đã xử lý

Sau một lần build:

```bash
./gradlew --quiet processResources
```

Kiểm tra:

```bash
cat build/resources/main/app.properties
```

Hoặc PowerShell:

```powershell
Get-Content build\resources\main\app.properties
```

Giá trị mặc định:

```properties
app.title=Gradle resources
```

Khi environment `PUBLIC_LABEL="Staging Demo"` được cấp, output là:

```properties
app.title=Staging Demo
```

Đó là một **tài nguyên đã ghi vào ổ đĩa**. Dù chúng ta cố ý dùng giá trị không nhạy cảm, nó cho thấy vì sao không được thay `DB_PASSWORD` theo cách tương tự.

### 6.5. Xem resource bên trong JAR

Chạy:

```bash
./gradlew --quiet jar
jar tf build/libs/safe-resources-lab.jar
```

Tìm đường dẫn:

```text
app.properties
```

Với project/phiên bản `jar` thông thường, tên JAR mặc định dựa trên tên project và version nếu có; ở ví dụ không khai báo version nên đường dẫn trên là kỳ vọng mặc định. Nếu project đã được cấu hình archive naming khác, hãy dùng tên JAR thực tế trong `build/libs`.

Điểm chính: `app.properties` không chỉ ở `build/resources/main`; nó đã đi vào artifact JAR. Người có JAR có thể giải nén và đọc tài nguyên, vì vậy **không bao giờ thay secret thật vào mẫu này**.

### 6.6. Kiểm tra whitelist hoạt động

Linux/macOS:

```bash
PUBLIC_LABEL='line1=line2' ./gradlew processResources
```

Hoặc PowerShell:

```powershell
$env:PUBLIC_LABEL = "line1=line2"
.\gradlew.bat processResources
Remove-Item Env:PUBLIC_LABEL
```

Giá trị có dấu `=`, không khớp whitelist nên build dự kiến thất bại với thông điệp:

```text
PUBLIC_LABEL must be 1..60 safe ASCII characters
```

Đây là hành vi **fail closed** cho dữ liệu công khai được phép đi vào `.properties`. Thông điệp không lặp lại giá trị đầu vào; nếu đây là một input nhạy cảm, việc in lại raw value trong exception sẽ gây rò rỉ log.

### 6.7. Vì sao khai báo `inputs.property(...)`?

Trong ví dụ:

```kotlin
inputs.property("publicLabel", publicLabel)
```

Task `processResources` phụ thuộc vào giá trị `PUBLIC_LABEL` đã qua kiểm tra. Khai báo input giúp Gradle tính trạng thái task từ dữ liệu cần thiết, để việc đổi giá trị công khai có thể khiến output được tạo lại đúng.

Nếu chỉ lấy environment value trong một closure tác động tại runtime mà **không biểu diễn input**, build có thể mắc lỗi `UP-TO-DATE` không đúng hoặc dùng lại output cũ trong một cấu hình không được theo dõi đầy đủ.

Đừng làm vậy với **secret** rồi kết luận bảo mật đã được giải quyết. Việc đăng ký `inputs.property("dbPassword", secretProvider)` có thể khiến giá trị hoặc dấu vết liên quan đi vào các cơ chế fingerprint/caching/diagnostics tùy cấu hình. Với secret thật, ưu tiên **không nhúng vào task output** ngay từ đầu.

### 6.8. Giới hạn trách nhiệm của ví dụ

Ví dụ này chủ đích chỉ giải quyết **một giá trị công khai có tập ký tự giới hạn**. Nó không phải engine dùng để render nội dung YAML/JSON, không phù hợp cho Unicode tùy ý, không xử lý escape cho bất kỳ URL phức tạp nào, và không được thiết kế để lưu secret.

Nếu dự án cần dữ liệu có dấu xuống dòng, dấu `:`, `=`, dấu ngoặc kép, backslash hoặc Unicode, hãy dùng serialization phù hợp với định dạng file. Đừng chỉ mở rộng regex một cách tùy tiện rồi tin `expand` luôn bảo toàn semantics.

## 7. Groovy DSL tương đương cho project Java

Cùng mô hình trên có thể viết bằng `build.gradle` (Groovy DSL):

```groovy
plugins {
    id 'application'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'demo.Main'
}

def publicLabel = providers.environmentVariable('PUBLIC_LABEL')
    .orElse('Gradle resources')
    .map { raw ->
        if (!(raw ==~ /[A-Za-z0-9 ._-]{1,60}/)) {
            throw new GradleException(
                'PUBLIC_LABEL must be 1..60 safe ASCII characters'
            )
        }
        return raw
    }

tasks.named('processResources', ProcessResources) {
    inputs.property('publicLabel', publicLabel)

    filesMatching('app.properties.template') {
        name = 'app.properties'
        expand([label: publicLabel.get()])
    }
}
```

Đây là **phương án thay thế** cho `build.gradle.kts`, không phải file cần chạy đồng thời. Các file `settings.gradle`, Java và resource template có thể chuyển tương ứng theo tên DSL; ví dụ Java và `app.properties.template` không thay đổi.

Lưu ý Groovy regular expression `==~` yêu cầu chuỗi khớp toàn bộ pattern, tương đương ý định của Kotlin `Regex.matches`. Cách đọc Provider và khai báo input giống nhau về mặt mô hình; cú pháp thuộc hai ngôn ngữ DSL khác nhau.

## 8. `processResources`, `Copy`, `Sync` và những nơi có thể làm rò rỉ

Resource filtering không nhất thiết chỉ xuất hiện ở `processResources`. Gradle có `Copy`, `Sync`, các source set khác và những plugin đóng gói artifact. Ví dụ thao tác sai có thể xảy ra trong:

- `processResources` của Java/Kotlin JVM project.
- Task `Copy` tạo thư mục phân phối.
- Task `Sync` tạo tập tin cấu hình deploy.
- Task `Jar`, `Zip`, `Tar` hoặc Docker build lấy output đã được render.
- Plugin packaging bổ sung resource của source set test hoặc environment-specific.
- Task custom generate-config tạo file rồi được đưa vào `src/main/resources` hoặc `build/resources`.

Ví dụ **mảnh cấu hình sai về bảo mật**:

```kotlin
// KHÔNG LÀM: minh họa anti-pattern.
tasks.named<org.gradle.language.jvm.tasks.ProcessResources>("processResources") {
    filesMatching("application.properties") {
        expand(
            mapOf(
                "databasePassword" to providers
                    .environmentVariable("DB_PASSWORD")
                    .get()
            )
        )
    }
}
```

Ngoài rủi ro config-cache vì cách tham chiếu tới project APIs ở execution-time, vấn đề lớn nhất là **mật khẩu sẽ xuất hiện trong file output được process**. Nếu file này đi vào JAR hoặc artifact CI, mật khẩu có thể bị trích xuất. Không “vá” bằng cách chỉ tránh in log; giá trị vẫn ở trong artifact.

**Đúng hơn:** resource được đóng gói chỉ chứa những thiết lập công khai/không nhạy cảm; secret được cung cấp ở runtime qua một cơ chế phù hợp.

## 9. Secret nên được đưa vào ứng dụng ở runtime thế nào?

Thay vì thay secret vào resource khi build:

```text
CI build (không có production secret)
   |
   +--> compile/test/package
   |
   v
artifact JAR dùng chung
   |
   +--> triển khai staging: inject secret staging ở runtime
   |
   +--> triển khai production: inject secret production ở runtime
   |
   v
ứng dụng đọc secret cần thiết khi chạy
```

Lợi ích:

- Không cần build lại chỉ để đổi credential.
- Artifact không chứa credential theo thiết kế.
- Có thể dùng một artifact đã kiểm thử cho nhiều môi trường.
- Secret manager hoặc nền tảng deploy quản lý luân chuyển/quyền truy cập.
- Cần ít quyền hơn trên runner thực hiện compilation/package.

### 9.1. Ví dụ Java 17 đọc credential lúc chạy mà không in giá trị

Đây là **một chương trình riêng** minh họa runtime input, không dùng file `app.properties`:

**File `RuntimeCredentialCheck.java`:**

```java
public final class RuntimeCredentialCheck {
    private RuntimeCredentialCheck() {
    }

    public static void main(String[] args) {
        String token = System.getenv("APP_API_TOKEN");

        if (token == null || token.isBlank()) {
            System.out.println("Runtime credential unavailable");
            return;
        }

        // Không ghi token vào stdout, file, metrics hoặc exception message.
        System.out.println("Runtime credential available");
    }
}
```

Biên dịch:

```bash
javac RuntimeCredentialCheck.java
java RuntimeCredentialCheck
```

Khi không có biến `APP_API_TOKEN`, stdout chính xác:

```text
Runtime credential unavailable
```

Nếu thử bằng **giá trị giả, không có quyền truy cập thật**:

```bash
APP_API_TOKEN=demo-only java RuntimeCredentialCheck
```

Stdout:

```text
Runtime credential available
```

Ví dụ chỉ xác nhận sự hiện diện của giá trị, **không thực hiện xác thực API thật** và không bảo đảm mọi secret đều an toàn chỉ vì đã đọc ở runtime. Environment variables vẫn có thể bị lộ qua cấu hình container, quyền xem process, child process, crash dumps, telemetry hoặc người có quyền quản trị máy. Với hệ thống quan trọng, dùng secret manager, workload identity hoặc volume/FD được quản lý theo nền tảng thay vì xem environment là kênh bất khả xâm phạm.

### 9.2. Không biến runtime secret thành task input cho packaging

Đừng dùng:

```kotlin
// KHÔNG LÀM:
val token = providers.environmentVariable("APP_API_TOKEN")
tasks.named<org.gradle.language.jvm.tasks.ProcessResources>("processResources") {
    inputs.property("apiToken", token)
}
```

Chỉ khai báo input mà chưa dùng nó không tạo ra lợi ích chức năng; nhưng việc đưa secret vào phạm vi Gradle task model/fingerprints khiến thiết kế khó kiểm soát hơn. Nếu resource không cần token, **đừng đọc token trong build logic**.

Nếu một công việc build thực sự cần secret (ví dụ publish đến repository nội bộ), hãy dùng API credentials/secret injection tương ứng, phân quyền CI và tránh in hoặc ghi vào output. Đây là ngoại lệ có kiểm soát khác với **tạo resource cho ứng dụng**.

## 10. Những đường rò rỉ phổ biến

Không phải chỉ có `println(password)` mới làm lộ bí mật. Hãy kiểm tra **toàn bộ vòng đời dữ liệu**:

| Đường rò rỉ | Ví dụ | Cách phòng |
| --- | --- | --- |
| Resource output | `build/resources/main/application.properties` chứa token | Không đưa secret vào `expand`/`filter` |
| JAR/ZIP/distribution | File resource được đóng gói vào artifact | Chỉ đóng gói dữ liệu được phép công khai |
| Log build | `println(System.getenv("DB_PASSWORD"))` | Không in raw value, kể cả khi debug |
| Exception | `error("Bad token: " + token)` | Thông báo lỗi không chứa secret |
| Task inputs/diagnostics | Secret trở thành task input của packaging | Tránh tạo secret-dependent artifact |
| Build cache | Output đã chứa secret được lưu/tái sử dụng | Thiết kế output không chứa secret; xem policy cache |
| Configuration cache | Build logic giữ thông tin nhạy cảm trong state | Không đọc/giữ secret trong configuration nếu không cần |
| Build scan / tracing | Tự động hoặc tùy biến thu thập environment/args | Kiểm tra data collection/redaction policy |
| CI artifacts | Upload cả `build/` hoặc logs chứa file cấu hình | Allowlist paths; scan và giới hạn quyền tải |
| Command line | `-Ppassword=...`, `-Dtoken=...` trong process args | Tránh đặt raw secret trên command line |
| Source control | Commit `application-prod.properties` chứa credential | Không commit secret; dùng CI secret store |
| Docker image | `COPY build/ ...` hoặc `ARG SECRET` ghi vào layer | Không nhúng secret vào image layers |
| Test output | Integration tests log toàn bộ config | Test dùng giá trị giả; không in secret |
| IDE sync | Plugin/init script/console lộ config | Review plugin và nơi lưu credential |
| Lưu tạm trên disk | File config có secret trong workspace runner | Tránh tạo hoặc giới hạn thời gian/quyền tồn tại |

**Một cấu hình nguồn “không in secret” vẫn có thể làm lộ secret nếu sản phẩm build chứa secret.** Bảo mật phải bắt đầu ở việc chọn nơi đọc/ghi dữ liệu, không chỉ ở giao diện log.

## 11. Build cache và trạng thái UP-TO-DATE: tại sao secret-dependent outputs nguy hiểm?

Gradle dùng các inputs, outputs và metadata của task để quyết định có cần thực hiện task lại và có thể tái sử dụng output từ build cache hay không. Nếu một giá trị môi trường được **chèn vào output**, về nguyên tắc nó ảnh hưởng tới bytes của output.

Với giá trị **công khai** `PUBLIC_LABEL` trong ví dụ:

```kotlin
inputs.property("publicLabel", publicLabel)
```

điều này là hợp lý: đổi label giúp Gradle theo dõi thay đổi và tạo lại resource. Tuy nhiên, hãy phân biệt:

- **`UP-TO-DATE`:** input/output task khớp trạng thái địa phương, không nhất thiết chạy lại action.
- **`FROM-CACHE`:** output có thể được khôi phục từ build cache khi task đủ điều kiện và cache hit.
- **`NO-SOURCE`/`SKIPPED`:** task không thực hiện theo điều kiện khác, không đồng nghĩa resource đã được tạo đúng.
- **`--rerun-tasks`:** yêu cầu chạy lại tasks, **không làm secret trong output biến mất**.
- **`clean`:** xóa output project thông thường, **không xóa mọi bản artifact đã upload hoặc cache từ xa**.

Nếu secret được chèn vào file rồi output được cache hoặc upload, việc xóa file ở workspace không thể thu hồi mọi bản sao. Tắt build cache cho một task cụ thể có thể giảm một đường lan truyền **nhưng không giải quyết việc secret vẫn nằm trong output/JAR**. Biện pháp đúng là **không tạo artifact chứa secret**.

### 11.1. Không dựa vào cấu hình cache như một hàng rào bảo mật duy nhất

Một cấu hình kiểu:

```kotlin
tasks.named("processResources") {
    outputs.cacheIf { false }
}
```

có thể ảnh hưởng tính được cache của task, nhưng **không** khiến resource có secret tự an toàn. Output vẫn có thể được task `jar` tiêu thụ và công bố; CI vẫn có thể lưu cả `build/`. Vì vậy đừng xem `cacheIf { false }` là cách thay thế cho secret management.

### 11.2. Nếu môi trường khác nhau nhưng dùng chung remote cache?

Khi một task thực sự tạo ra output khác nhau theo biến **công khai**, cần đảm bảo mọi input ảnh hưởng output được Gradle theo dõi. Nếu một đầu vào không được khai báo đúng, task có thể tái sử dụng output sai môi trường.

Nhưng với secret, “đăng ký secret làm input để cache đúng” vẫn là thiết kế rủi ro. Với artifact được triển khai qua nhiều môi trường, hãy loại secret khỏi bước build thay vì tìm cách cache đúng một file chứa secret.

## 12. Configuration cache và Provider: hiệu năng không đồng nghĩa bảo mật

Configuration cache có thể giúp Gradle không phải cấu hình lại toàn bộ build khi cấu hình tương thích. API `providers.environmentVariable` hữu ích trong mô hình Provider và được thiết kế để làm việc với Gradle configuration tracking.

Tuy nhiên:

1. **Hỗ trợ configuration cache không có nghĩa dữ liệu tự được mã hóa.**
2. Nếu bạn materialize secret ở configuration phase, giá trị có thể đi vào trạng thái/logic mà plugin hoặc công cụ khác quan sát.
3. Đưa secret vào closure/task action hoặc project model có thể tạo cả rủi ro bảo mật lẫn vấn đề tương thích configuration cache.
4. Đọc environment quá rộng làm khó xác định đâu là input thực sự cần thiết.
5. Một plugin bên ngoài vẫn có thể logging/capture dữ liệu; phải xem nguồn plugin và policy dữ liệu được thu thập.

**Nguyên tắc:** dùng Provider cho **những input build hợp lệ và tối thiểu**; không dùng sự tồn tại của Provider như lý do để đưa thông tin nhạy cảm vào Gradle.

Trong ví dụ `PUBLIC_LABEL`, task khai báo Provider làm input và chỉ đọc giá trị công khai trong hành động lọc file. Việc sử dụng giá trị trong execution-time action phải tránh tham chiếu tùy tiện tới `Project` object hoặc API bị hạn chế bởi configuration cache.

## 13. Build once, deploy many so với lọc từng môi trường

Có hai chiến lược:

| Chiến lược | Cách hoạt động | Ưu điểm | Rủi ro/cân nhắc |
| --- | --- | --- | --- |
| Build-time public filtering | Gradle tạo resource khác nhau theo environment | Tiện cho nhãn giao diện, tài liệu, thông tin tĩnh | Phải build lại cho từng môi trường, dễ lẫn artifact |
| Runtime config injection | Build tạo một artifact chung; môi trường cấp config khi chạy | Dễ kiểm thử/tái lập và tách credential | Cần cơ chế runtime config/secret manager |

Ví dụ nên dùng build-time filtering: ghi `app.title=Staging Demo` vào một artifact phục vụ thử nghiệm, với điều kiện nhãn này thực sự công khai và artifact được nhận diện rõ.

Ví dụ nên dùng runtime injection: DB password production, API token, tenant-specific keys, endpoint có credential hoặc certificate private key. Không nên tạo `application-prod.properties` chứa secret rồi đóng gói trong release JAR.

Một số hệ thống cần **runtime configuration file** ngoài JAR, ví dụ được mount dưới `/etc/app/config.properties` hoặc thư mục cấu hình của container. File đó phải được cấp đúng quyền, không được commit và không được upload nhầm vào artifact. Việc chuyển secret ra file runtime cần quản lý filesystem permissions và vòng đời secret, không mặc định an toàn hơn environment trong mọi mô hình đe dọa.

## 14. Kiểm tra artifact trước khi phát hành

Đối với project ví dụ mục 6, một số phép kiểm tra:

### 14.1. Xem source/template và output

```bash
./gradlew --quiet clean processResources
cat src/main/resources/app.properties.template
cat build/resources/main/app.properties
```

Ở PowerShell:

```powershell
.\gradlew.bat --quiet clean processResources
Get-Content src\main\resources\app.properties.template
Get-Content build\resources\main\app.properties
```

Hai file này chỉ được phép chứa giá trị công khai. Trong dự án thực, nên có bước review/scan tự động cho output, không chỉ kiểm tra bằng mắt.

### 14.2. Xem danh sách file trong JAR

```bash
./gradlew --quiet jar
jar tf build/libs/safe-resources-lab.jar
```

Kiểm tra có file `app.properties` đúng dự kiến, không có `.env`, `credentials.json`, `private.key`, secret directories hoặc file phát sinh ngoài ý muốn.

**Chỉ xem danh sách file là chưa đủ** để xác minh nội dung không chứa secret: một file tên `app.properties` vẫn có thể chứa mật khẩu. Cần scan nội dung resources đã render và các artifact theo chính sách bảo mật, bảo đảm không đưa raw secrets vào logs của scanner.

### 14.3. Những file không nên đưa vào `src/main/resources`

Ví dụ:

```text
src/main/resources/.env
src/main/resources/application-prod-with-password.properties
src/main/resources/credentials.json
src/main/resources/private.key
src/main/resources/service-account-key.json
```

Đừng lưu file bí mật ở resource tree rồi chỉ mong `processResources` tự biết bỏ qua. Java plugin thường copy resources có trong source directory. Có thể bổ sung `exclude` như một lớp phòng vệ, nhưng cách đúng hơn là **không đưa secret vào source tree** và dùng allowlist các file đóng gói khi cần.

### 14.4. Phòng vệ bổ sung bằng exclude

Mảnh Kotlin DSL minh họa:

```kotlin
tasks.named<org.gradle.language.jvm.tasks.ProcessResources>("processResources") {
    exclude("**/.env", "**/secrets/**", "**/*.p12", "**/*.key")
}
```

Điều này giảm nguy cơ copy những file có đường dẫn phù hợp pattern. Nó **không phát hiện secret đặt trong file có tên vô hại** và không bảo vệ các task khác nếu chúng trực tiếp copy source. Không coi exclude là đủ thay cho source hygiene, security review và artifact scanning.

## 15. Định dạng file và escaping: những bẫy thực tế

### 15.1. `.properties` không giống JSON hoặc YAML

Trong Java `.properties`, dấu `=`, dấu `:`, backslash, dấu xuống dòng và Unicode có thể có quy tắc parsing riêng. `Properties.load(InputStream)` theo hành vi định dạng truyền thống; không nên đơn thuần nối chuỗi tùy ý vào file.

Với ví dụ chỉ có nhãn ASCII, whitelist đủ cho mục tiêu bài học. Nếu cần hỗ trợ Unicode tiếng Việt, hãy chọn mã hóa/escape đúng và kiểm tra cả bước **write** lẫn bước Java **read**, thay vì chỉ tăng regex cho phép mọi ký tự.

### 15.2. Placeholder dùng cú pháp template

Trong resource mẫu:

```properties
app.title=${label}
```

`expand` có thể hiểu placeholder từ Groovy template engine. Nếu file gốc có nội dung dùng dấu `$` cho một công cụ khác, có thể xảy ra va chạm template. Nên chỉ lọc đúng file cần thiết và dùng tên placeholder rõ ràng.

Một số file resource như JSON, CSS, shell script hoặc YAML có ký hiệu đặc biệt. Đừng chạy `expand` trên tất cả file theo `**/*`; việc này vừa có thể phá cú pháp vừa tăng bề mặt rò rỉ.

### 15.3. Không tin biến môi trường là dữ liệu sạch

Ngay cả biến công khai có thể được cấp từ CI job, terminal hoặc hệ thống orchestration. Nên:

- Giới hạn danh sách biến được đọc.
- Kiểm tra giá trị theo định dạng đích.
- Giới hạn độ dài.
- Không đưa raw value vào lỗi hoặc log khi có thể nhạy cảm.
- Chọn fallback rõ ràng khi giá trị vắng.
- Không tự động render các environment variables chưa được review.

Một chuỗi dài chứa newline có thể biến một dòng `app.title=...` thành nhiều keys mới trong `.properties`. Whitelist nhỏ ở ví dụ chính tránh cả một loại lỗi ngẫu nhiên lẫn khả năng chèn thêm cấu hình ngoài dự kiến.

## 16. CI/CD: tách quyền build và quyền deploy

Một pipeline tốt thường có:

```text
Checkout
  |
  v
Compile + unit test
  |
  v
Artifact scan / packaging QA
  |
  v
Publish immutable artifact
  |
  +--> Staging deploy (inject runtime config + staging secret)
  |
  +--> Production deploy (inject runtime config + production secret)
```

Gợi ý kiểm soát:

1. **Build runner** không được cấp production secrets trừ khi thật sự cần và đã có cơ chế cách ly.
2. **Deploy job** có quyền truy cập secret theo môi trường, phân quyền tối thiểu.
3. Artifact được tạo một lần nên có digest/checksum để xác nhận staging và production dùng cùng bytes.
4. Logs và build scans phải theo policy redaction; không thêm `println(env)` để debug.
5. Artifact retention và quyền tải phải được kiểm soát; resource nhạy cảm bị đưa vào artifact có thể tồn tại lâu trong storage.
6. Secret rotation không nên bắt buộc build lại JAR nếu secret được cấp ở runtime.
7. Những file generated trong workspace CI phải được xử lý theo chính sách cleanup, nhưng cleanup **không thu hồi bản đã upload**.
8. Pipeline scanning nên báo fail khi phát hiện secret, đồng thời tránh in nguyên secret ra console khi tạo báo cáo.

Nếu build cần credential để **tải dependency từ repository riêng**, đó là một use case khác: credential phục vụ network access của Gradle, không phải cấu hình runtime của ứng dụng. Phải giữ credential trong phạm vi repository authentication, không đưa nó vào `expand` của app resources.

## 17. Secret trong Gradle properties và environment: chọn đúng mục đích

Gradle có nhiều nguồn cấu hình:

- Environment variables (`providers.environmentVariable`).
- Gradle properties (`providers.gradleProperty`).
- System properties (`providers.systemProperty`).
- Cấu hình riêng của CI/IDE, init script, credential helper và secret manager.

**Không có nguồn nào tự biến giá trị thành “an toàn để nhúng vào JAR”.** Khác biệt chủ yếu là cách cung cấp và phạm vi truy cập.

Đối với credential để **publish** artifact hoặc đọc Maven nội bộ, có thể dùng API credentials của task/repository và cơ chế secret management, không truyền qua task resource processing. Đối với API token của ứng dụng, cấp ở runtime. Đối với nhãn công khai, dùng Provider và `processResources` có kiểm soát nếu việc build-time embedding thực sự được chấp nhận.

### 17.1. `-Ppassword=...` có thể lộ qua command line

Lệnh như:

```bash
# KHÔNG LÀM với secret thật.
./gradlew assemble -PdbPassword=real-production-password
```

có thể làm lộ dữ liệu qua process arguments, shell history, CI logs hoặc công cụ quan sát. Hãy dùng secret store và API credentials phù hợp. Không dùng giá trị của ví dụ này làm mật khẩu; đây chỉ là anti-pattern minh họa.

### 17.2. `gradle.properties` không tự là kho secret an toàn

Một `gradle.properties` trong repository có thể được commit hoặc được người có quyền đọc source xem. File ở user home có phạm vi khác nhưng vẫn cần kiểm soát quyền file và quản lý máy. Không commit token thật chỉ vì Gradle có API đọc property.

### 17.3. Runtime environment không phải giải pháp hoàn hảo cho mọi trường hợp

Lưu secret trong runtime environment có thể phù hợp với một số nền tảng, nhưng vẫn có nguy cơ nếu:

- Process bị compromise.
- Người dùng có quyền xem môi trường của process/container.
- Application hoặc dependency log toàn bộ config.
- Secret được truyền sang child process không cần thiết.
- Hệ thống monitoring thu thập environment không đúng chính sách.

Với yêu cầu bảo mật cao, dùng service identity, secret manager hoặc workload identity và tránh giữ secret lâu hơn cần thiết.

## 18. Debug khi resource filtering không như kỳ vọng

### 18.1. Task `processResources` báo `UP-TO-DATE` nhưng file không đổi

Kiểm tra:

- Biến `PUBLIC_LABEL` được cấp cho đúng Gradle invocation chưa?
- Provider có nhận giá trị kỳ vọng không? Tránh in secret, chỉ kiểm tra biến công khai.
- Task đã có `inputs.property("publicLabel", publicLabel)` chưa?
- Có phải file mẫu `app.properties.template` thuộc `src/main/resources` không?
- `filesMatching` có khớp đúng đường dẫn tương đối không?
- Bạn đang đọc đúng `build/resources/main/app.properties` hay một file cũ ở thư mục khác?
- Một plugin khác có override/copy lại resource sau task không?

Chạy:

```bash
./gradlew processResources --info --console=plain
```

Nếu có nghi ngờ output cũ, có thể chạy:

```bash
./gradlew clean processResources --console=plain
```

Đây là thao tác dọn output build project; nó không chứng minh đã thu hồi các bản artifact/caches chứa secret nếu trước đây từng làm rò rỉ.

### 18.2. Lỗi “template variable not found”

Nếu template có `${label}` nhưng mapping dùng tên `title`, `expand` có thể báo lỗi vì không biết `label`. Cần thống nhất key:

```kotlin
filesMatching("app.properties.template") {
    expand(mapOf("label" to publicLabel.get()))
}
```

Đây là **mảnh cấu hình** đặt trong `ProcessResources`; nó không tự là script runnable nếu thiếu `publicLabel` và plugin.

Không sửa bằng cách truyền toàn bộ `System.getenv()` chỉ để mong mọi placeholder đều có giá trị. Làm vậy có thể đưa secret vào template context.

### 18.3. Resource bị thiếu ở runtime

Nếu Java code:

```java
Main.class.getResourceAsStream("/app.properties")
```

trả về `null`, hãy kiểm tra:

1. `src/main/resources/app.properties.template` có tồn tại không?
2. `processResources` có tạo file và đổi tên thành `app.properties` không?
3. `build/resources/main/app.properties` có tồn tại không?
4. File có ở root của JAR không?
5. Ứng dụng chạy với classpath đúng chưa?

Dấu `/` trong `getResourceAsStream("/app.properties")` biểu thị tìm ở root classpath, không phải root filesystem.

### 18.4. Build khác nhau giữa local và CI

Các nguyên nhân thường gặp:

- CI không đặt `PUBLIC_LABEL` nên dùng fallback.
- Local dùng biến shell khác, dẫn đến JAR khác.
- Task không khai báo input nên cached/up-to-date output không được làm mới theo biến.
- CI dùng JDK/Gradle Wrapper khác.
- Mẫu resource hoặc environment có định dạng khác.
- Một task packaging khác đưa vào resource chưa render.
- Repo có file `.env` nhạy cảm bị vô tình commit và copy.

Một khác biệt environment **không tự là bug**, nếu thiết kế build cho từng môi trường. Nhưng phải có chính sách nhận diện artifact và không trộn staging JAR với production JAR. Nếu muốn một artifact chung, chuyển cấu hình biến động sang runtime.

## 19. Bảng lỗi và hướng xử lý

| Triệu chứng | Nguyên nhân có thể | Hướng giải quyết |
| --- | --- | --- |
| `app.title=${label}` vẫn nguyên sau build | `filesMatching` không khớp, action chưa chạy hoặc resource không được lọc | Kiểm tra input path, output và task configuration |
| `MissingPropertyException` khi expand | Template key thiếu trong map | Khai báo mapping cụ thể, không đổ cả env vào |
| Output resource chứa literal `null` hoặc rỗng | Provider không có giá trị, fallback thiếu hoặc validation không đủ | `orElse` hợp lệ và validate giá trị công khai |
| Giá trị xuống dòng làm hỏng `.properties` | Không escape/validate theo định dạng | Whitelist hoặc serializer phù hợp |
| Resource từ lần build cũ xuất hiện trong JAR | Task output/cache/inputs không tương ứng | Kiểm tra `inputs`, clean trong môi trường thử và kiểm tra JAR |
| `processResources` chạy nhưng Java không tìm được resource | File chưa rename/copy đúng classpath | Xem `build/resources/main` và `jar tf` |
| Gradle báo không tìm JDK 17 | Toolchain chưa có/resolver chưa cấu hình | Cài/cấu hình JDK hoặc toolchain resolver đúng |
| Lộ token trong JAR | Secret đã được lọc vào resource | Thu hồi artifact, xoay token, sửa pipeline và kiểm tra phạm vi ảnh hưởng |
| Lộ token trong CI log | Print raw secret, exception hoặc plugin log | Thu hồi log nếu có thể, rotate và redact |
| Build cache chứa secret | Task output hoặc input có secret | Kiểm soát cache access/retention, rotate và loại secret khỏi output |
| Exclude `.env` mà vẫn lộ | Secret nằm trong file tên khác hoặc task khác copy | Source hygiene, artifact scanning, review packaging tasks |
| Kotlin DSL code không nhận `ProcessResources` | Thiếu plugin/ngữ cảnh hoặc kiểu không import | Dùng tên kiểu đầy đủ và Java/Application plugin |
| Gradle config-cache báo project access tại execution | Action sử dụng project APIs sai thời điểm | Chuẩn bị Provider/task inputs đúng, tránh capture `Project` object |
| Runtime secret thiếu | Deploy chưa inject đúng runtime config/identity | Kiểm tra orchestration/secret manager; không chuyển secret vào JAR |

### 19.1. Nếu đã thực sự rò rỉ secret

Không chỉ sửa source rồi coi như xong. Cần thực hiện quy trình ứng cứu phù hợp:

1. **Vô hiệu hóa/rotate credential** đã bị lộ theo mức độ khẩn cấp.
2. Xác định nơi xuất hiện: Git history, JAR, ZIP, Docker layer, CI artifact, build logs, build cache, build scans, backup.
3. Thu hồi/quản lý quyền truy cập các bản sao còn giữ được; không tuyên bố đã xóa sạch khi không có bằng chứng.
4. Đánh giá tác động truy cập, audit events và sự cố liên quan theo policy.
5. Sửa pipeline để build không còn đọc hoặc đóng gói secret.
6. Thêm secret scanning và kiểm thử release artifacts để phòng lặp lại.
7. Kiểm tra lần phát hành mới từ đầu trên runner sạch trước khi sử dụng.

**Đừng in token thật vào báo cáo sự cố** để chứng minh nó bị lộ. Có thể báo loại secret, nơi bị ảnh hưởng và thời điểm, kèm bằng chứng đã redact.

## 20. Bài tập thực hành

**Bài tập A — phân loại dữ liệu.** Với các biến `PUBLIC_LABEL`, `DB_PASSWORD`, `PUBLIC_DOCS_URL`, `APP_API_TOKEN` và `PRIVATE_KEY`, hãy xác định biến nào có thể xuất hiện trong artifact khi đã được xác nhận công khai và biến nào phải được cấp ở runtime.

**Bài tập B — build resource từ biến công khai.** Tạo project mục 6, chạy mặc định và kiểm tra stdout `Gradle resources`. Sau đó đặt `PUBLIC_LABEL="Staging Demo"`, chạy lại và kiểm tra output resource đổi thành `app.title=Staging Demo`.

**Bài tập C — thay đổi input.** Chạy `processResources` hai lần với cùng `PUBLIC_LABEL`, quan sát task state; đổi giá trị rồi chạy lại. Vì sao `inputs.property("publicLabel", publicLabel)` quan trọng?

**Bài tập D — whitelist.** Thử `PUBLIC_LABEL='line1=line2'` trong project ví dụ. Vì sao build nên fail thay vì chèn thẳng chuỗi không hợp lệ vào `.properties`? Lý do nào khiến ta không in raw input trong exception?

**Bài tập E — kiểm tra JAR.** Chạy `jar tf build/libs/safe-resources-lab.jar`. Xác định file `app.properties`, chứng minh resource đóng gói có thể được đọc và giải thích vì sao không dùng cách này cho `APP_API_TOKEN`.

**Bài tập F — runtime credential.** Biên dịch `RuntimeCredentialCheck.java`, chạy không có biến và với giá trị giả. Vì sao chương trình chỉ in trạng thái có/không, không in token thật?

**Bài tập G — tách môi trường.** Đề xuất pipeline build một JAR chung cho staging và production; chỉ cấp secret khi deploy. Nêu cách xác nhận hai môi trường thực sự dùng cùng artifact hash.

**Bài tập H — anti-pattern.** Một đồng nghiệp viết `expand(mapOf("password" to System.getenv("DB_PASSWORD")))` trong `processResources`. Hãy giải thích ít nhất bốn nơi có thể lưu lại mật khẩu, và cách thiết kế lại.

**Bài tập I — mã hóa dữ liệu.** Nếu cần một label tiếng Việt có dấu hoặc URL chứa ký tự đặc biệt trong `.properties`, vì sao ví dụ whitelist ASCII không đủ? Hãy chọn phương thức escaping/serialization và kiểm thử `Properties.load` thực tế.

**Bài tập J — kiểm tra CI.** Thiết kế checklist trước publish gồm: không có `.env`/keys trong archive, không có credential trong generated resources, secret không được đưa vào log, artifact retention phù hợp và chỉ cho phép runtime deploy job truy cập production secrets.

### Câu hỏi tự kiểm tra

1. `processResources` là task gì trong Java plugin?
2. Tài nguyên từ `src/main/resources` thường đi đâu trước khi vào JAR?
3. `filesMatching(...)` giúp giảm rủi ro và giới hạn hành động như thế nào?
4. `expand(...)` chỉ thay chuỗi thuần hay có cơ chế template?
5. Vì sao không nên render toàn bộ `System.getenv()`?
6. `providers.environmentVariable` khác gì việc đọc env trực tiếp trong code build?
7. `inputs.property` giúp Gradle xác định trạng thái task ra sao?
8. Vì sao ghi secret vào task input không phải biện pháp bảo mật?
9. Nếu JAR là ZIP archive, người nhận có thể đọc `app.properties` không?
10. Lý do gì khiến `PUBLIC_` prefix chưa đủ chứng minh an toàn?
11. Vì sao một file `.properties` cần escaping/validation riêng?
12. `--quiet` có tự che secret nếu app in ra token không?
13. `--offline` có tự bảo vệ secret trong build output không?
14. Tại sao `outputs.cacheIf { false }` chưa giải quyết leak vào JAR?
15. Khi nào nên dùng runtime environment hoặc secret manager?
16. Build once, deploy many giúp giảm việc đưa production secret vào build thế nào?
17. Runtime environment variables có thể rò rỉ qua những đường nào?
18. Làm sao phân biệt `UP-TO-DATE` với `FROM-CACHE`?
19. Nếu Java `getResourceAsStream` trả null, nên kiểm tra những file/đường dẫn nào?
20. Nếu credential từng nằm trong artifact đã phát hành, vì sao chỉ xóa file ở workspace là chưa đủ?
21. Vì sao một artifact khác nhau theo staging/production có thể khó bảo đảm tính tái lập?
22. Điều gì cần kiểm tra sau khi thay đổi resource filtering nhưng IDE/CI báo kết quả khác nhau?

**Tài liệu tham khảo chính thức:** [Gradle — Copying files](https://docs.gradle.org/current/userguide/working_with_files.html); [Gradle — Build Environment](https://docs.gradle.org/current/userguide/build_environment.html); [Gradle — Incremental Build](https://docs.gradle.org/current/userguide/incremental_build.html); [Gradle — Build Cache](https://docs.gradle.org/current/userguide/build_cache.html); [Java — Properties API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Properties.html).

**Ghi nhớ:** Lọc resource là thao tác **ghi giá trị vào file output**; nếu giá trị là secret, nó có thể xuất hiện trong `build/resources`, JAR, distribution, CI artifacts, cache hoặc logs. Chỉ dùng `processResources`/`expand` cho **dữ liệu đã xác nhận được phép công khai**, với whitelist và task inputs rõ ràng; cung cấp credential ở runtime qua cơ chế được quản lý và kiểm tra artifact trước khi phát hành.