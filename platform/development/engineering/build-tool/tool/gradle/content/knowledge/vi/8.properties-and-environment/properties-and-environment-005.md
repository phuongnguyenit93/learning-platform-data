# Chuyển đổi kiểu, giá trị mặc định và kiểm tra cấu hình bắt buộc trong Gradle

## 1. Vấn đề cần giải quyết

Trong **Build Tool Gradle**, cấu hình thường đến từ tham số dòng lệnh, `gradle.properties`, Java system properties và biến môi trường. Phần lớn giá trị ngoài build được biểu diễn bằng **chuỗi**, dù ý nghĩa thực tế của chúng là số, boolean, mode hoặc đường dẫn. Chẳng hạn:

```properties
appPort=8080
appMode=dev
featureEnabled=false
```

Một build đáng tin cậy cần thực hiện đúng trình tự: **xác định nguồn → lấy giá trị → quyết định mặc định khi thiếu → chuyển sang kiểu đích → kiểm tra miền hợp lệ → báo lỗi có thể xử lý**.

Các lỗi thường gặp:

- Dùng chuỗi `'false'` trong `if ('false')`: Groovy xem chuỗi không rỗng là true.
- Dùng `Integer.parseInt('abc')` hoặc `Integer.parseInt('999999999999999')`: lỗi chuyển số.
- Chỉ đặt giá trị mặc định khi biến không tồn tại mà quên kiểm tra trường hợp người dùng truyền `-PappPort=` (có mặt nhưng trống).
- Dùng `Boolean.parseBoolean('flase')`: Java trả false âm thầm, làm lỗi đánh máy trở thành một quyết định cấu hình.
- Đòi token deploy ngay khi Gradle cấu hình dự án, khiến `help` hoặc `test` cũng thất bại mặc dù không cần deploy.
- In token/secret ra thông báo lỗi hoặc CI log để “debug”.

Bài học dùng **Gradle Groovy DSL** trong `build.gradle`; ví dụ không viết cho `build.gradle.kts` (Kotlin DSL). Lệnh minh hoạ dùng Gradle Wrapper của dự án.

## 2. Nguồn cấu hình và API đọc tương ứng

### 2.1. Phân biệt project property, system property, environment variable

| Nguồn | Cách cấp giá trị | API lấy giá trị |
| --- | --- | --- |
| Project property từ CLI | `./gradlew help -PappPort=9090` | `providers.gradleProperty('appPort')` |
| Project property trong `gradle.properties` | `appPort=8080` | `providers.gradleProperty('appPort')` |
| Project property qua system property đặc biệt | `-Dorg.gradle.project.appPort=9090` | `providers.gradleProperty('appPort')` |
| Project property qua biến môi trường theo quy ước | `ORG_GRADLE_PROJECT_appPort=9090` | `providers.gradleProperty('appPort')` |
| Java system property thông thường | `-Dapp.port=9090` | `providers.systemProperty('app.port')` |
| Biến môi trường thông thường | `APP_PORT=9090` | `providers.environmentVariable('APP_PORT')` |

**Quan trọng:** `-PappPort=9090` không tương đương `-DappPort=9090`. Cờ `-P` tạo **project property**. Cờ `-D` tạo **Java system property**. Dùng prefix `org.gradle.project.` nếu cố ý cấp project property qua `-D`.

Đối với project properties cấp build, các nguồn `providers.gradleProperty()` tìm kiếm theo thứ tự ưu tiên được Gradle tài liệu hoá: `-P` → system property `org.gradle.project.*` → environment `ORG_GRADLE_PROJECT_*` → `gradle.properties` tại Gradle User Home → `gradle.properties` tại build root → `gradle.properties` tại Gradle installation. Bởi vậy lệnh:

```bash
./gradlew help -PappPort=9090
```

ghi đè giá trị `appPort=8080` ở file `gradle.properties`. Không suy đoán thứ tự giữa `APP_PORT` và `appPort` nếu chưa tự định nghĩa cách kết hợp: đó là **hai key ở hai nguồn khác nhau**.

`providers.gradleProperty('name')` chỉ đọc **build-level Gradle properties**; nó không tự đọc tất cả `ext`/extra properties được gán động hay `gradle.properties` của subproject. `project.findProperty('name')` là API tìm property động của `Project`, có phạm vi khác và giá trị có thể là kiểu `Object` không phải String. Với cấu hình do người chạy build cấp, nên dùng Provider API để giữ tính lazy và rõ nguồn.

### 2.2. Với bí mật (secret)

Token triển khai, mật khẩu và private key không nên được commit trong `gradle.properties` của repository. CI nên cấp chúng qua secret store thành biến môi trường, ví dụ `APP_DEPLOY_TOKEN`. Dùng `providers.environmentVariable('APP_DEPLOY_TOKEN')` để đọc khi cần; **không in giá trị bí mật** ra terminal, exception, file báo cáo hay Gradle debug output. Khi cấu hình repository xác thực, ưu tiên API credentials chuyên dụng của Gradle.

## 3. Provider: giá trị có thể chưa được cung cấp

Gradle `providers.gradleProperty('appPort')` tạo `Provider<String>` — một nguồn giá trị chỉ đọc, có thể **hiện hữu hoặc vắng mặt**, cho phép trì hoãn việc giải quyết giá trị đến khi cần.

| Phương thức | Ý nghĩa |
| --- | --- |
| `isPresent()` | Cho biết Provider có giá trị hay không. |
| `get()` | Lấy giá trị; khi không có giá trị có thể ném exception. |
| `getOrNull()` | Lấy giá trị hoặc `null` nếu vắng mặt. |
| `getOrElse(defaultValue)` | Lấy **giá trị ngay lúc gọi**; thiếu thì trả default. |
| `orElse(defaultValue)` | Trả **Provider mới** có fallback, vẫn có thể gắn vào task khác một cách lazy. |
| `map { ... }` | Biến đổi dữ liệu sang kiểu mới khi Provider được yêu cầu. |
| `flatMap { ... }` | Biến đổi sang một Provider khác (dùng cho phụ thuộc vào Provider). |

Ví dụ:

```groovy
def rawPort = providers.gradleProperty('appPort')  // Provider<String>
def withDefault = rawPort.orElse('8080')            // Provider<String>
def typedPort = withDefault.map { String text ->
    Integer.parseInt(text.trim())                   // Provider<Integer>
}
```

Ba dòng chỉ **xây dựng chuỗi Provider**. Để lấy số thực, `typedPort.get()` hoặc nối Provider vào `Property<Integer>` của task. Việc giữ Provider giúp tránh tính toàn bộ cấu hình ngay khi Gradle đang nạp build script.

### 3.1. “Không có giá trị” khác “giá trị trống”

Xét `appPort`:

- **Không khai báo** ở bất cứ nguồn nào: `rawPort.isPresent()` là false; `orElse('8080')` dùng mặc định.
- **Khai báo `-PappPort=`**: property **có mặt** với chuỗi rỗng. `orElse('8080')` không thay `''`; parser phải quyết định rằng rỗng là lỗi hay trường hợp hợp lệ.
- **Khai báo `-PappPort=abc`**: property có mặt nhưng sai định dạng; lỗi được phát hiện khi chuyển kiểu/validate.

Vì thế mặc định phải phục vụ **trường hợp thiếu**, còn dữ liệu sai phải được xử lý bằng **validation**. Không nên xóa đi lỗi cấu hình bằng cách fallback vô điều kiện.

### 3.2. Provider và Property

`Provider<T>` chỉ cung cấp giá trị. `Property<T>` là loại Provider có thể cấu hình với `set(...)` và `convention(...)`. Trong custom Gradle task, khai báo typed input như `Property<Integer>` sẽ giúp Gradle hiểu kiểu và quản lý input.

Ví dụ **minh hoạ bên trong phần cấu hình một task đã có Property<Integer> tên port**:

```groovy
port.convention(
    providers.gradleProperty('appPort')
        .orElse('8080')
        .map { Integer.parseInt(it.trim()) }
)
// Một cấu hình tường minh có thể ghi đè giá trị quy ước:
port.set(9090)
```

`convention` là mặc định cho Property; `set` là lựa chọn được cấu hình tường minh, sẽ ưu tiên giá trị mới. Đoạn này là **mã minh hoạ API**, không phải build script độc lập vì `port` cần được khai báo trong một task/extension typed.

## 4. Chuyển từ chuỗi sang số nguyên có kiểm tra

### 4.1. Chuyển kiểu khác với xác minh giá trị hợp lệ

Chuỗi `'8080'` phải được parse trước khi dùng như số:

```groovy
String raw = ' 9090 '
int port = Integer.parseInt(raw.trim())
assert port == 9090
```

Có ít nhất **hai lỗi độc lập**:

1. **Sai định dạng:** `abc`, `12.5`, `''`, chuỗi số vượt phạm vi Integer. Java `Integer.parseInt` ném `NumberFormatException`.
2. **Ngoài miền nghiệp vụ:** `0`, `-1`, `65536` parse có thể thành công, nhưng không hợp lệ nếu đây là số cổng mạng (miền ví dụ: 1–65535).

Một parser bảo vệ hai tầng:

```groovy
def parsePort = { String raw ->
    String text = raw.trim()
    if (!(text ==~ /[0-9]+/)) {
        throw new GradleException(
            "appPort phải là số nguyên 1..65535; đã nhập '${text}'"
        )
    }
    int value
    try {
        value = Integer.parseInt(text)
    } catch (NumberFormatException cause) {
        throw new GradleException('appPort vượt phạm vi Integer', cause)
    }
    if (value < 1 || value > 65535) {
        throw new GradleException('appPort phải nằm trong 1..65535')
    }
    value
}

assert parsePort(' 9090 ') == 9090
```

Regex `==~ /[0-9]+/` buộc **toàn bộ** chuỗi phải gồm chữ số, nên `-1` và `+1` bị từ chối theo chính sách này. Với retry count, timeout hoặc tỷ lệ phần trăm, miền được phép có thể khác; phải đặt validation riêng cho từng thuộc tính.

## 5. Chuyển từ chuỗi sang boolean an toàn

Trong Groovy, chuỗi không rỗng được xem là **true** khi dùng làm điều kiện:

```groovy
String text = 'false'
assert (text ? true : false) == true
assert Boolean.parseBoolean(text) == false
```

Cả `Boolean.parseBoolean('maybe')` và `Boolean.parseBoolean('flase')` đều trả false, nên **không dùng riêng parseBoolean** nếu cần phát hiện lỗi cấu hình. Đặt chính sách rõ ràng chỉ chấp nhận `true`/`false`:

```groovy
def parseStrictBoolean = { String raw ->
    String text = raw.trim().toLowerCase(Locale.ROOT)
    if (!(text in ['true', 'false'])) {
        throw new GradleException(
            'featureEnabled chỉ nhận true hoặc false'
        )
    }
    text == 'true'
}
assert parseStrictBoolean(' TRUE ') == true
assert parseStrictBoolean('false') == false
```

Nếu dự án muốn hỗ trợ `yes/no` hoặc `1/0`, hãy công khai tập giá trị đó và parse riêng. Không tự coi mọi giá trị ngoài `true` là false. Đừng dùng `if (project.findProperty('featureEnabled'))` trực tiếp: nếu kết quả là String `'false'` thì nhánh if vẫn được chạy.

## 6. Chuyển kiểu theo tập giá trị và các kiểu khác

### 6.1. Chỉ chấp nhận mode được phép

```groovy
def parseMode = { String raw ->
    String mode = raw.trim().toLowerCase(Locale.ROOT)
    if (!(mode in ['dev', 'test', 'prod'])) {
        throw new GradleException(
            'appMode chỉ nhận dev, test hoặc prod'
        )
    }
    mode
}

assert parseMode(' PROD ') == 'prod'
```

Kiểu giá trị đã chuẩn hóa có thể là String hoặc một enum được định nghĩa sẵn. Với ID, token và đường dẫn có phân biệt hoa/thường, không tùy tiện `toLowerCase` hoặc trim nếu không được chính sách cho phép.

### 6.2. Các phép chuyển khác

| Kiểu đích | Cách xử lý mẫu | Bẫy cần tránh |
| --- | --- | --- |
| `Long` | `Long.parseLong(raw.trim())` | Chuỗi không hợp lệ hoặc số quá lớn. |
| `BigDecimal` | `new BigDecimal(raw.trim())` | Dấu thập phân và định dạng theo locale. |
| Danh sách | `raw.split(',').collect { it.trim() }` | Phần tử rỗng, trùng, dấu phẩy bên trong giá trị. |
| Tệp tương đối | `layout.projectDirectory.file(relativePath)` | Cần quyết định chấp nhận đường dẫn nào. |
| Thư mục output | `layout.buildDirectory.dir('reports')` | Nên giữ Provider của Gradle thay vì ghép path thủ công. |

Các type `DirectoryProperty`, `RegularFileProperty`, `ListProperty<T>`, `MapProperty<K,V>` có cơ chế lazy và theo dõi input riêng; không ép chúng thành String hoặc List thường khi Gradle API cung cấp model typed phù hợp.

## 7. Giá trị mặc định: thiếu, trống hay giá trị falsey?

Một thuộc tính có thể thuộc một trong ba dạng:

- **Optional có mặc định:** `appMode` không được cấp thì là `dev`.
- **Optional không có mặc định:** chẳng hạn `reportLabel` vắng mặt có ý nghĩa “bỏ qua nhãn”.
- **Required:** thiếu hoặc chỉ có khoảng trắng phải báo lỗi khi chức năng cần thuộc tính đó.

Cú pháp lazy phổ biến:

```groovy
def modeProvider = providers.gradleProperty('appMode').orElse('dev')
def retryProvider = providers.gradleProperty('retryCount').orElse('3')
    .map { Integer.parseInt(it.trim()) }
```

`orElse` trả Provider; `getOrElse('dev')` trả String ngay khi gọi. Nếu có thể chuyển Provider thẳng vào task/extension, hãy dùng `orElse` và trì hoãn `get` đến lúc cần.

**Bẫy toán tử Elvis `?:` của Groovy:** `value ?: fallback` chọn fallback khi `value` mang giá trị falsey — có thể là `null`, `false`, `0` hoặc `''`. Nếu số retry `0` là hợp lệ, hoặc cờ boolean false được người dùng chỉ định tường minh, Elvis có thể xóa mất ý nghĩa của chúng. Chỉ dùng Elvis khi bạn **thực sự muốn coi mọi giá trị falsey là thiếu**. `Provider.orElse` áp dụng khi Provider vắng mặt, không “nuốt” `false` hoặc chuỗi rỗng.

## 8. Kiểm tra cấu hình bắt buộc và thông điệp lỗi

Một validation cần phân loại rõ:

- **Missing:** Provider không có giá trị.
- **Blank:** có giá trị nhưng `trim().isEmpty()`.
- **Malformed:** định dạng không đổi được sang kiểu cần thiết.
- **Out-of-range:** đúng kiểu, sai miền nghiệp vụ.
- **Conflicting:** hai thuộc tính không thể đồng thời nhận giá trị đã cho.

Ví dụ token deploy chỉ bắt buộc với tác vụ triển khai:

```groovy
def tokenProvider = providers.environmentVariable('APP_DEPLOY_TOKEN')

tasks.register('checkDeploySettings') {
    doLast {
        String token = tokenProvider.getOrNull()
        if (token == null || token.trim().isEmpty()) {
            throw new GradleException(
                'Thiếu APP_DEPLOY_TOKEN: hãy cấp biến môi trường khi deploy'
            )
        }
        logger.quiet('Required deploy configuration: OK')
    }
}
```

Nếu token trống hoặc không có, Gradle fail với thông điệp nêu tên key và hành động sửa. Nếu token được cấp hợp lệ, output của task:

```text
Required deploy configuration: OK
```

**Đọc và kiểm tra khi nào?** Với token chỉ dùng cho deploy, validate trong task deploy hoặc task kiểm tra riêng. Khi đó `./gradlew help` và `./gradlew test` không bị chặn vì thiếu token. Với cấu hình bắt buộc cho toàn bộ plugin/build, có thể fail fast ở pha configuration với thông điệp rõ ràng. Không nên kiểm tra tất cả biến của mọi môi trường trong mọi build.

Trong Gradle plugin/task thực tế, ưu tiên `Property<T>` và khai báo input bằng `@Input`/`@InputFile` khi thích hợp để Gradle hiểu dữ liệu liên quan đến task, incremental build và configuration cache. Tránh gọi `project` hay duyệt mọi biến từ `System.getenv()` bên trong task action; dùng `providers.environmentVariable('KEY')` để chỉ định chính xác nguồn. Không ghi giá trị secret vào exception hoặc log; cân nhắc chính sách lưu cache khi cấu hình bí mật.

## 9. Ví dụ Gradle Groovy DSL đầy đủ và chạy được

Tạo project thực hành riêng có Gradle Wrapper rồi đặt toàn bộ mã này trong **`build.gradle`**, không phải `build.gradle.kts`. Ví dụ dùng Gradle API cơ bản, không cần plugin bên thứ ba.

```groovy
import java.util.Locale
import org.gradle.api.GradleException

def portProvider = providers.gradleProperty('appPort')
    .orElse('8080')
    .map { String raw ->
        String text = raw.trim()
        if (!(text ==~ /[0-9]+/)) {
            throw new GradleException(
                "appPort phải là số nguyên 1..65535; đã nhập '${text}'"
            )
        }
        int port
        try {
            port = Integer.parseInt(text)
        } catch (NumberFormatException cause) {
            throw new GradleException('appPort vượt phạm vi Integer', cause)
        }
        if (port < 1 || port > 65535) {
            throw new GradleException('appPort phải nằm trong 1..65535')
        }
        port
    }

def modeProvider = providers.gradleProperty('appMode')
    .orElse('dev')
    .map { String raw ->
        String mode = raw.trim().toLowerCase(Locale.ROOT)
        if (!(mode in ['dev', 'test', 'prod'])) {
            throw new GradleException(
                'appMode chỉ nhận dev, test hoặc prod'
            )
        }
        mode
    }

def featureProvider = providers.gradleProperty('featureEnabled')
    .orElse('false')
    .map { String raw ->
        String value = raw.trim().toLowerCase(Locale.ROOT)
        if (!(value in ['true', 'false'])) {
            throw new GradleException(
                'featureEnabled chỉ nhận true hoặc false'
            )
        }
        value == 'true'
    }

def deployTokenProvider =
    providers.environmentVariable('APP_DEPLOY_TOKEN')

tasks.register('inspectSettings') {
    doLast {
        logger.quiet("appMode=${modeProvider.get()}")
        logger.quiet("appPort=${portProvider.get()}")
        logger.quiet("featureEnabled=${featureProvider.get()}")
    }
}

tasks.register('checkDeploySettings') {
    doLast {
        String token = deployTokenProvider.getOrNull()
        if (token == null || token.trim().isEmpty()) {
            throw new GradleException(
                'Thiếu APP_DEPLOY_TOKEN: hãy cấp biến môi trường khi deploy'
            )
        }
        logger.quiet('Required deploy configuration: OK')
    }
}
```

Các Provider được tạo bên ngoài task để diễn tả các nguồn cấu hình một cách lazy. Phần `doLast` chỉ giải quyết giá trị khi task tương ứng chạy. Đây là ví dụ học tập; với task sản xuất có output cần cache, hãy dùng custom task có typed input properties.

### 9.1. Chạy với giá trị mặc định

Khi không có `appPort`, `appMode`, `featureEnabled` ở bất kỳ nguồn cấu hình nào, chạy:

```bash
./gradlew -q inspectSettings --console=plain
```

Output do task in:

```text
appMode=dev
appPort=8080
featureEnabled=false
```

`-q` tương đương `--quiet`. Vì code dùng `logger.quiet`, ba dòng vẫn được in dù Gradle được yêu cầu giảm log.

### 9.2. Ghi đè bằng -P

```bash
./gradlew -q inspectSettings --console=plain \
  -PappMode=prod -PappPort=9090 -PfeatureEnabled=true
```

Output task:

```text
appMode=prod
appPort=9090
featureEnabled=true
```

Trên PowerShell:

```powershell
.\gradlew.bat -q inspectSettings --console=plain -PappMode=prod -PappPort=9090 -PfeatureEnabled=true
```

Tương tự, có thể đặt các property trong `gradle.properties` nếu phù hợp với chính sách của project. Nếu property xuất hiện cả file và `-P`, tham số CLI có ưu tiên cao hơn.

### 9.3. Thử đầu vào sai

Chạy **riêng từng lệnh**:

```bash
./gradlew -q inspectSettings -PappPort=abc --console=plain
./gradlew -q inspectSettings -PappPort=65536 --console=plain
./gradlew -q inspectSettings -PappMode=unknown --console=plain
./gradlew -q inspectSettings -PfeatureEnabled=maybe --console=plain
./gradlew -q inspectSettings -PappMode= --console=plain
```

Tất cả được thiết kế để **fail (exit code khác 0)**. Thông điệp từ validation tương ứng:

```text
appPort phải là số nguyên 1..65535; đã nhập 'abc'
appPort phải nằm trong 1..65535
appMode chỉ nhận dev, test hoặc prod
featureEnabled chỉ nhận true hoặc false
appMode chỉ nhận dev, test hoặc prod
```

Đây là **các thông điệp exception do script sinh ra**, không phải toàn bộ output stderr của Gradle. Gradle còn có thể in `FAILURE: Build failed with an exception.` và task name. `-PappMode=` có mặt nhưng trống nên **không** được default thành `dev`.

### 9.4. Bắt buộc có token khi chạy task liên quan

Nếu chưa có `APP_DEPLOY_TOKEN`:

```bash
./gradlew -q checkDeploySettings --console=plain
```

Task thất bại với thông điệp:

```text
Thiếu APP_DEPLOY_TOKEN: hãy cấp biến môi trường khi deploy
```

Thử với giá trị demo **không phải secret thật** trên Linux/macOS:

```bash
APP_DEPLOY_TOKEN=local-test-only ./gradlew -q checkDeploySettings --console=plain
```

Trên Windows PowerShell:

```powershell
$env:APP_DEPLOY_TOKEN = 'local-test-only'
.\gradlew.bat -q checkDeploySettings --console=plain
Remove-Item Env:APP_DEPLOY_TOKEN
```

Output task khi token không trống:

```text
Required deploy configuration: OK
```

Không đặt token thật vào command line có lịch sử hoặc log công khai. Hãy cấp secret bằng CI secret store. `help` không gọi task kiểm tra deploy, nên không cần token để xem danh sách task hoặc thông tin trợ giúp.

## 10. Khi có điều kiện bắt buộc phụ thuộc vào tùy chọn khác

Đôi khi một thuộc tính chỉ bắt buộc nếu một thuộc tính khác được bật:

- `publishEnabled=true` yêu cầu `repositoryUrl` hợp lệ.
- `integrationTests=true` yêu cầu `testEndpoint`.
- `appMode=prod` có thể không được đồng thời `debugEnabled=true`.
- Giá trị retry `0` có thể hợp lệ và không nên bị thay bằng fallback qua `?:`.

Ví dụ kiểm tra tương quan:

```groovy
def validatePublishing = { boolean enabled, String url ->
    if (enabled && (url == null || url.trim().isEmpty())) {
        throw new GradleException(
            'publishEnabled=true yêu cầu repositoryUrl không rỗng'
        )
    }
}
```

Đây là **closure kiểm tra riêng**, phải được gọi ở nơi có các giá trị `enabled` và `url` đã được parse. Đừng áp dụng nó cho mọi task nếu chỉ task publish cần các giá trị đó. Với URL thực, kiểm tra thêm scheme, host và chính sách nguồn kết nối nếu phù hợp.

Một thông báo lỗi tốt nêu **tên key, kỳ vọng, giá trị không nhạy cảm hoặc phạm vi hợp lệ và cách cung cấp**. Với secret, chỉ nhắc key bị thiếu, không lặp lại giá trị người dùng nhập.

## 11. Lỗi phổ biến và cách tránh

| Lỗi | Nguyên nhân | Giải pháp |
| --- | --- | --- |
| `if ('false')` chạy nhánh true | Chuỗi không rỗng là truthy. | Parse boolean tường minh. |
| `Boolean.parseBoolean('flase')` không báo lỗi | Java trả false khi text khác true. | Chỉ chấp nhận tập `true/false`, báo lỗi nếu ngoài tập. |
| `Provider.get()` thất bại khi property thiếu | Không có giá trị. | Optional dùng fallback; required đưa thông điệp lỗi. |
| `-PappMode=` không dùng default | Chuỗi rỗng vẫn được xem là present. | Validate blank và báo lỗi. |
| `'80.5'` hoặc số quá lớn không parse được | Không phải Integer hợp lệ. | Kiểm tra định dạng, bắt `NumberFormatException`. |
| Port `65536` parse thành công | Sai miền ứng dụng. | Validate `1..65535`. |
| Dùng `value ?: default` làm mất `0`/`false` | Elvis coi falsey là thiếu. | Dùng Provider `orElse` hoặc null check. |
| Thiếu deploy token làm `help` thất bại | Kiểm tra required quá sớm. | Chỉ kiểm tra ở task cần token. |
| `-DappPort=9090` không đổi `gradleProperty('appPort')` | System property thường khác project property. | Dùng `-PappPort` hoặc prefix `org.gradle.project.`. |
| `ext.foo` không hiện khi đọc `gradleProperty('foo')` | `gradleProperty` truy vấn build-level properties. | Dùng đúng API theo nguồn. |
| Token xuất hiện trong CI log | In giá trị bí mật khi debug. | Chỉ log trạng thái kiểm tra và tên biến thiếu. |
| Sử dụng `get()` tại pha cấu hình cho mọi task | Đọc sớm dữ liệu chỉ cần cho task nhất định. | Giữ Provider đến khi task cần; gắn vào typed property. |

## 12. Bài tập tự kiểm tra

**Bài 1 — Default:** bỏ các property nguồn và chạy `inspectSettings`. Giải thích tại sao in `dev/8080/false`. Thử `-PappPort=` và giải thích tại sao không fallback.

**Bài 2 — Integer:** thử `-PappPort=0`, `-PappPort=65535`, `-PappPort=65536` và `-PappPort=abc`. Phân biệt không parse được với parse được nhưng ngoài miền.

**Bài 3 — Boolean:** so sánh `if ('false')` với parser nghiêm ngặt. Dự đoán khi chạy `-PfeatureEnabled=FALSE` và `-PfeatureEnabled=maybe`.

**Bài 4 — Nguồn:** so sánh `-PappPort=9090`, `-Dorg.gradle.project.appPort=9090`, `-Dapp.port=9090` và `APP_PORT=9090`. API nào đọc từng trường hợp?

**Bài 5 — Required:** chạy `checkDeploySettings` trước và sau khi cấp biến môi trường thử nghiệm `APP_DEPLOY_TOKEN`. Kiểm tra không có token nào bị in ra.

**Bài 6 — Phụ thuộc:** xây dựng quy tắc `publishEnabled=true` yêu cầu `repositoryUrl` hợp lệ. Vì sao không nên kiểm tra repository URL khi chỉ chạy `help`?

**Đáp án cần nắm:** `Provider.orElse` chỉ thay khi **vắng mặt**; `getOrElse` trả giá trị tức thời; text `'false'` vẫn truthy trong Groovy; parsing đúng kiểu chưa đồng nghĩa đúng miền; required nên được kiểm tra tại tác vụ dùng giá trị.

## 13. Tài liệu chính thức

- Gradle Build Environment Configuration: https://docs.gradle.org/current/userguide/build_environment.html
- Gradle Properties and Providers: https://docs.gradle.org/current/userguide/properties_providers.html
- Gradle Lazy Configuration: https://docs.gradle.org/current/userguide/lazy_configuration.html
- Gradle Configuration Cache Requirements: https://docs.gradle.org/current/userguide/configuration_cache_requirements.html
- Gradle `Provider<T>` API: https://docs.gradle.org/current/javadoc/org/gradle/api/provider/Provider.html
- Java `Integer.parseInt`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Integer.html
- Java `Boolean.parseBoolean`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Boolean.html

**Kết luận kiến thức:** đọc cấu hình từ đúng nguồn bằng Provider, định nghĩa default có chủ đích, parse một cách rõ ràng, kiểm tra cả miền nghiệp vụ và sự hiện diện của giá trị bắt buộc ở đúng thời điểm.