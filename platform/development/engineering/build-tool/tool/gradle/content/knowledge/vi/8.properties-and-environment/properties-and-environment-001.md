# Project properties, system properties và biến môi trường trong Gradle

## 1. Tại sao phải phân biệt ba loại giá trị?

Khi chạy Gradle, cùng một thông tin như `profile=staging`, đường dẫn JDK, tên môi trường CI hoặc cấu hình JVM có thể được đưa vào build qua những cơ chế khác nhau. Nếu nhầm cơ chế, Gradle có thể không nhìn thấy giá trị, đọc giá trị từ nguồn ưu tiên khác, hoặc không chuyển giá trị sang tiến trình chạy ứng dụng/test.

| Loại | Bản chất | Cách cấp ví dụ | Cách đọc trong Groovy DSL |
| --- | --- | --- | --- |
| **Project property** | Tham số cấu hình build-level của dự án | `-Pprofile=dev` hoặc `profile=dev` trong `gradle.properties` | `providers.gradleProperty('profile')` |
| **JVM system property** | Thuộc tính JVM chạy Gradle | `-Ddemo.mode=trace` | `providers.systemProperty('demo.mode')` hoặc `System.getProperty('demo.mode')` |
| **Environment variable** | Biến của môi trường hệ điều hành chạy Gradle | Linux: `APP_REGION=vn ./gradlew help`; Windows PowerShell: `$env:APP_REGION='vn'` | `providers.environmentVariable('APP_REGION')` hoặc `System.getenv('APP_REGION')` |
| **Gradle runtime property** | Cấu hình bản thân công cụ Gradle, thường có tiền tố `org.gradle.` | `org.gradle.caching=true`, `org.gradle.jvmargs=-Xmx2g` trong `gradle.properties` | Gradle tự áp dụng; không nên dùng như cờ nghiệp vụ thông thường |

Điều quan trọng là **`-Pfoo=x` và `-Dfoo=x` không đồng nghĩa**. Biến môi trường tên `FOO` cũng không tự động thành project property `foo`. Chỉ những tên có tiền tố theo quy tắc Gradle (`org.gradle.project.` hoặc `ORG_GRADLE_PROJECT_`) mới được chuyển đổi tương ứng.

**Mục tiêu:** Sau bài học, bạn phải xác định được namespace của một giá trị, nguồn gốc/ưu tiên khi có trùng tên, cách đọc phù hợp, thời điểm đọc và tiến trình nào thực sự nhận nó.

Ví dụ dùng **Gradle Groovy DSL** (`build.gradle`), **Gradle Wrapper** và Java 17+ khi có mã Java. Trên Windows PowerShell, thay `./gradlew` bằng `.\gradlew.bat`.

## 2. Project properties: cấu hình build bằng `-P` và tệp `gradle.properties`

### 2.1. Cấp từ dòng lệnh

~~~bash
./gradlew build -Pprofile=staging
./gradlew build -Pprofile=production -PbuildNumber=42
~~~

`-Pprofile=staging` cấp **project property** tên `profile`; giá trị ban đầu là chuỗi. `buildNumber=42` không tự trở thành integer. Truyền tham số kiểu `-Pname=value` thích hợp để đổi hành vi build giữa các lần chạy mà không sửa mã.

### 2.2. Cấp từ tệp

**`gradle.properties` tại root:**

~~~properties
profile=development
buildNumber=0
org.gradle.caching=true
~~~

Hai dòng đầu là project properties thông thường; dòng cuối là Gradle runtime property, điều khiển build cache. Đây là cú pháp **Java properties**, không phải Groovy: không có `def`, dấu ngoặc nhọn hay method call.

Bạn cũng có thể có `gradle.properties` tại **Gradle User Home** (thường là `~/.gradle/gradle.properties`) hoặc thư mục cài Gradle. Cấu hình chia sẻ không bí mật có thể nằm trong file root được commit. Giá trị cá nhân và credentials không nên commit.

### 2.3. Đọc bằng Provider API

~~~groovy
def profile = providers.gradleProperty('profile').orElse('development')

def buildNumber = providers.gradleProperty('buildNumber')
    .map { String value -> Integer.parseInt(value) }
    .orElse(0)
~~~

- `providers.gradleProperty('profile')` tạo `Provider<String>` đọc build-level project property khi cần; không trả `null` thay cho provider.
- `orElse('development')` cấp mặc định khi nguồn không có.
- `map` chuyển kiểu, giữ cơ chế lazy; nếu `buildNumber=abc`, `Integer.parseInt` báo lỗi rõ thay vì coi `abc` là số.
- Gắn Provider trực tiếp với task input hoặc extension có hỗ trợ, tránh gọi `.get()` ở configuration time khi chưa cần.

Cách đọc theo model `Project`:

~~~groovy
def value = project.findProperty('profile')   // null nếu không có
boolean exists = project.hasProperty('profile')
def required = project.property('profile')    // lỗi nếu không có
~~~

`project.findProperty`, `property` và `hasProperty` có cơ chế lookup động của Project, có thể thấy các giá trị như **extra properties** ngoài nguồn build-level. Chúng **không hoàn toàn tương đương** với `providers.gradleProperty`. Với tham số đến từ CLI, root/user-home `gradle.properties` hay prefixed env, Provider API thường rõ ý định hơn.

### 2.4. Extra properties là một khái niệm khác

~~~groovy
ext {
    documentationLabel = 'Ví dụ nội bộ'
}
~~~

`ext.documentationLabel` là extra property được thêm vào Project qua build script; đây không phải biến môi trường hoặc JVM system property. Không dùng `ext` để giấu secrets hay truyền dữ liệu xuyên nhiều project một cách ngầm định.

## 3. Bốn nguồn của cùng một project property và thứ tự ưu tiên

Gradle cho phép cấp cùng một project property `profile` bằng các cách sau:

| Nguồn | Ví dụ | Kết quả |
| --- | --- | --- |
| CLI `-P` | `./gradlew help -Pprofile=release` | Cấp trực tiếp `profile=release` |
| JVM property có tiền tố Gradle | `./gradlew help -Dorg.gradle.project.profile=integration` | Gradle chuyển thành project property `profile=integration` |
| Environment variable có tiền tố Gradle | `ORG_GRADLE_PROJECT_profile=staging` | Gradle chuyển thành project property `profile=staging` |
| Tệp properties | `profile=development` trong `gradle.properties` | Cấp giá trị mặc định từ file |

Theo `ProviderFactory.gradleProperty()`, thứ tự **ưu tiên cao đến thấp** của giá trị build-level là:

1. `-Pprofile=...` trên command line.
2. `-Dorg.gradle.project.profile=...` hoặc nguồn JVM system property tương đương.
3. Biến môi trường `ORG_GRADLE_PROJECT_profile=...`.
4. `gradle.properties` trong `GRADLE_USER_HOME`.
5. `gradle.properties` tại root của build.
6. `gradle.properties` trong thư mục cài Gradle.

**Tình huống:** root file đặt `profile=dev`; env đặt `ORG_GRADLE_PROJECT_profile=staging`; lệnh có cả `-Dorg.gradle.project.profile=integration` và `-Pprofile=production`. `providers.gradleProperty('profile').get()` cho giá trị **`production`**. Bỏ `-P` thì được **`integration`**; bỏ tiếp `-Dorg.gradle.project.profile` thì được **`staging`**.

Quy tắc trên mô tả nguồn mà **`providers.gradleProperty`** đọc. Nó không đồng nghĩa mọi lookup động trên `Project` có cùng phạm vi: extra properties gán bằng mã hoặc file trong subproject có các quy tắc riêng. Đặc biệt, **`providers.gradleProperty` không đọc `gradle.properties` ở thư mục của subproject** như một nguồn build-level. Ưu tiên đặt tham số chung ở root hoặc dùng extension được cấu hình rõ cho từng project.

### 3.1. Ba lệnh `-D` dễ bị nhầm

~~~bash
./gradlew help -Dprofile=dev
./gradlew help -Dorg.gradle.project.profile=dev
./gradlew help -Dorg.gradle.caching=true
~~~

- `-Dprofile=dev` tạo **JVM system property** `profile`, không tự chuyển thành project property `profile`.
- `-Dorg.gradle.project.profile=dev` tạo system property có tiền tố đặc biệt và Gradle nhận thành **project property** `profile`.
- `-Dorg.gradle.caching=true` cấu hình một **Gradle property** mà công cụ hiểu, không tạo tham số nghiệp vụ `caching`.

Trong file, `profile=dev` tạo project property; `systemProp.profile=dev` tạo system property `profile`. Đây là hai khóa khác nhau, dù cuối cùng tên lookup đều có thể là `profile`.

## 4. JVM system properties: Gradle JVM có phải JVM của ứng dụng không?

Java system property thuộc **một tiến trình JVM cụ thể**. Trong build script:

~~~groovy
def mode = providers.systemProperty('demo.mode').orElse('normal')

// Đọc trực tiếp ngay thời điểm gọi:
def now = System.getProperty('demo.mode', 'normal')
~~~

Cấp giá trị:

~~~bash
./gradlew help -Ddemo.mode=trace
~~~

Hoặc đặt trong **root `gradle.properties`**:

~~~properties
systemProp.demo.mode=trace
~~~

Tiền tố `systemProp.` trong tệp nói với Gradle hãy tạo JVM system property `demo.mode`. `demo.mode=trace` không có tiền tố lại là project property `demo.mode`. Trong **multi-project build**, cấu hình `systemProp.*` tại `app/gradle.properties` (subproject) **không phải cách hợp lệ để cài system property cho Gradle JVM**; đặt tại root hoặc cấp qua CLI theo cơ chế hỗ trợ.

### 4.1. JVM Gradle, JVM test và JVM ứng dụng khác nhau

~~~bash
./gradlew test -Dapp.mode=ci
~~~

Lệnh trên cấu hình JVM đang chạy Gradle; **không bảo đảm** test JVM forked nhận `System.getProperty("app.mode") == "ci"`. Tương tự, `./gradlew run -Dapp.mode=ci` không tự động áp property cho ứng dụng do task `JavaExec` tạo.

Nếu có Java plugin, bạn có thể chuyển tường minh sang JVM chạy JUnit test:

~~~groovy
tasks.named('test', Test) {
    systemProperty 'app.mode', providers.systemProperty('app.mode')
        .orElse('test-default')
        .get()
}
~~~

Đây là **đoạn cấu hình thêm** vào một `build.gradle` đã áp dụng Java plugin, không phải build script độc lập. `Test.systemProperty` cấu hình system property ở JVM chạy test. `get()` ở đây lấy giá trị trong pha configuration cho ví dụ ngắn; trong build lớn, xem API hỗ trợ Provider hoặc thiết kế typed task input để giữ cấu hình lazy và tránh resolve secret quá sớm.

### 4.2. Cấu hình JVM của Gradle không phải Java toolchain

~~~properties
org.gradle.jvmargs=-Xmx2g -Dfile.encoding=UTF-8
org.gradle.parallel=true
~~~

- `org.gradle.jvmargs` cấu hình JVM chạy Gradle daemon (ví dụ heap), **không tự đặt heap của ứng dụng hoặc mọi forked test JVM**.
- `org.gradle.parallel` là cấu hình Gradle, không phải project property nghiệp vụ.
- `JAVA_HOME` thường ảnh hưởng JVM được dùng để khởi chạy Gradle; **Java toolchains** có thể chọn JDK khác cho việc biên dịch/chạy task Java.
- `org.gradle.java.home` có thể cấu hình vị trí JDK chạy Gradle; điều này vẫn không thay cho cấu hình `java.toolchain` của project.

Khi gặp lỗi phiên bản Java, kiểm tra `./gradlew --version` và toolchain được cấu hình riêng, thay vì kết luận mọi JVM phải bằng `JAVA_HOME`.

## 5. Environment variables: đầu vào của hệ điều hành và CI

Biến môi trường được cấp bởi shell, hệ điều hành hoặc CI runner cho tiến trình Gradle.

**Linux/macOS:**

~~~bash
export APP_REGION=vn
./gradlew help
~~~

**Windows PowerShell:**

~~~powershell
$env:APP_REGION = 'vn'
.\gradlew.bat help
~~~

Trong Groovy DSL:

~~~groovy
def region = providers.environmentVariable('APP_REGION').orElse('local')
def immediate = System.getenv('APP_REGION')  // null nếu không có
~~~

Những biến sau có **cơ chế khác nhau**:

| Biến | Cơ chế |
| --- | --- |
| `APP_REGION=vn` | Đọc bằng `providers.environmentVariable('APP_REGION')`; không tự tạo project property |
| `ORG_GRADLE_PROJECT_profile=staging` | Gradle chuyển thành project property `profile`, đọc qua `providers.gradleProperty('profile')` |
| `JAVA_HOME=/path/to/jdk` | Ảnh hưởng việc chọn JVM theo launcher/cấu hình; không tự trở thành project property |
| `GRADLE_USER_HOME=/path/to/cache` | Đổi thư mục user home của Gradle; không tự tạo project property |
| `CI=true` | Biến môi trường CI, chỉ ảnh hưởng build nếu script/plugin chủ động dùng |

Tên env **phân biệt hoa/thường trên Linux**. Nếu muốn đặt project property `profile` thì dùng chính xác `ORG_GRADLE_PROJECT_profile`; `ORG_GRADLE_PROJECT_PROFILE` không được giả định sẽ tự đổi thành `profile`.

Một process con do Gradle mở có thể kế thừa environment mặc định từ process mẹ, nhưng plugin/task có thể thay đổi. Để tránh suy đoán, với các giá trị quan trọng hãy kiểm tra task `JavaExec`, `Test` hoặc tool tương ứng có nhận env nào.

## 6. Phòng thực hành 1: Gradle task kiểm chứng cả ba nguồn

Tạo thư mục `gradle-property-lab`:

~~~text
gradle-property-lab/
├── settings.gradle
├── gradle.properties
├── build.gradle
├── gradlew
├── gradlew.bat
└── gradle/wrapper/
    ├── gradle-wrapper.jar
    └── gradle-wrapper.properties
~~~

Nếu chưa có Wrapper, cài Gradle tạm thời rồi chạy `gradle wrapper` một lần tại root; lưu bộ Wrapper trong VCS. Ví dụ không cần plugin bên ngoài hoặc download dependency.

**`settings.gradle`:**

~~~groovy
rootProject.name = 'gradle-property-lab'
~~~

**`gradle.properties`:**

~~~properties
profile=from-file
systemProp.demo.mode=from-file-system
org.gradle.caching=true
~~~

**`build.gradle` (toàn bộ):**

~~~groovy
plugins {
    id 'base'
}

def profile = providers.gradleProperty('profile').orElse('local')
def mode = providers.systemProperty('demo.mode').orElse('normal')
def channel = providers.environmentVariable('APP_CHANNEL').orElse('unset')

tasks.register('showInputs') {
    group = 'verification'
    description = 'In các giá trị demo không nhạy cảm'

    inputs.property('profile', profile)
    inputs.property('mode', mode)
    inputs.property('channel', channel)

    doLast {
        println 'profile=' + profile.get()
        println 'mode=' + mode.get()
        println 'channel=' + channel.get()
    }
}
~~~

Giải thích: `providers.gradleProperty`, `providers.systemProperty` và `providers.environmentVariable` đọc ba namespace độc lập. `orElse` trả giá trị mặc định. `inputs.property` khai báo task input để Gradle biết task phụ thuộc các giá trị. Task demo không khai báo output nên action thường chạy mỗi lần được yêu cầu; trong task tạo artifact thực tế phải khai báo output thích hợp để có up-to-date checks.

### 6.1. Đọc mặc định

Khi không có override từ CLI/user home/environment:

~~~bash
./gradlew showInputs --quiet
~~~

**Stdout của task:**

~~~text
profile=from-file
mode=from-file-system
channel=unset
~~~

Nếu máy đã có `ORG_GRADLE_PROJECT_profile`, `APP_CHANNEL` hoặc cấu hình trong Gradle User Home thì output có thể khác. Điều đó là bằng chứng có nguồn ưu tiên khác, không phải script “chạy ngẫu nhiên”.

### 6.2. Override đúng từng namespace

**Linux/macOS:**

~~~bash
APP_CHANNEL=beta ./gradlew showInputs -Pprofile=release -Ddemo.mode=trace --quiet
~~~

**Stdout ba dòng từ task:**

~~~text
profile=release
mode=trace
channel=beta
~~~

**Windows PowerShell:**

~~~powershell
$env:APP_CHANNEL = 'beta'
.\gradlew.bat showInputs -Pprofile=release -Ddemo.mode=trace --quiet
Remove-Item Env:APP_CHANNEL
~~~

Lưu ý `Remove-Item` xóa biến khỏi phiên PowerShell đang dùng; nếu trước đó đã có giá trị cần giữ, hãy lưu để khôi phục sau bài thực hành.

### 6.3. Thử thứ tự ưu tiên

~~~bash
ORG_GRADLE_PROJECT_profile=env \
  ./gradlew showInputs -Dorg.gradle.project.profile=sys -Pprofile=cli --quiet
~~~

Với `APP_CHANNEL` không đặt, dòng profile sẽ là:

~~~text
profile=cli
~~~

Bỏ `-Pprofile=cli`, dòng profile thành `profile=sys`. Bỏ tiếp `-Dorg.gradle.project.profile=sys`, nó thành `profile=env`. Tệp root `profile=from-file` chỉ được chọn khi các nguồn ưu tiên hơn không hiện diện.

## 7. Phòng thực hành 2: Java 17 chứng minh system property của ứng dụng

Tạo file **`EnvironmentApp.java`** (chạy độc lập, chưa cần Gradle):

~~~java
public final class EnvironmentApp {
    private EnvironmentApp() {
    }

    public static void main(String[] args) {
        String mode = System.getProperty("app.mode", "unset");
        String region = System.getenv().getOrDefault("DEMO_REGION", "unset");

        System.out.println("mode=" + mode);
        System.out.println("region=" + region);
    }
}
~~~

Biên dịch/chạy trên Linux/macOS:

~~~bash
javac EnvironmentApp.java
DEMO_REGION=vn java -Dapp.mode=release EnvironmentApp
~~~

**Stdout chính xác của Java application:**

~~~text
mode=release
region=vn
~~~

`-Dapp.mode=release` ở đây được truyền trực tiếp vào JVM của `EnvironmentApp`, còn `DEMO_REGION` là biến môi trường. Không có Gradle project property nào vì ta không chạy Gradle.

Để chạy qua **Gradle Application plugin**, đặt Java file tại `src/main/java/EnvironmentApp.java`, tạo `settings.gradle` với `rootProject.name = 'java-environment-lab'`, rồi tạo **`build.gradle`**:

~~~groovy
plugins {
    id 'application'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'EnvironmentApp'
}

tasks.named('run', JavaExec) {
    systemProperty 'app.mode', 'from-gradle'
    environment 'DEMO_REGION', 'vn'
}
~~~

Chạy:

~~~bash
./gradlew run --quiet
~~~

**Stdout ứng dụng:**

~~~text
mode=from-gradle
region=vn
~~~

Task `run` đã được cấu hình **truyền tường minh** property/env sang JVM ứng dụng. Vì cấu hình trên ghi cố định `from-gradle`, việc chạy `./gradlew run -Dapp.mode=other` không mặc nhiên khiến `System.getProperty("app.mode")` trong app thành `other`. Đừng nhầm Gradle process với forked application process.

## 8. Eager lookup, Provider API và configuration cache

### 8.1. Đọc ngay lúc cấu hình

~~~groovy
def region = System.getenv('APP_REGION') ?: 'local'
~~~

Đoạn này đọc environment ngay ở pha configuration. Gradle có thể theo dõi các nguồn môi trường/JVM được đọc trong configuration cache và vô hiệu hóa cache khi giá trị thay đổi. Nhưng nếu có nhiều input thay đổi thường xuyên, cấu hình sẽ phải được dựng lại nhiều lần.

### 8.2. Nối Provider vào task input

~~~groovy
def regionProvider = providers.environmentVariable('APP_REGION')
    .orElse('local')

tasks.register('showRegion') {
    inputs.property('region', regionProvider)

    doLast {
        println 'region=' + regionProvider.get()
    }
}
~~~

Đoạn này có thể thêm vào script đang áp dụng Base plugin. Việc dùng Provider cho task input thể hiện rõ phụ thuộc dữ liệu, giữ lookup theo cách lazy. Cần bổ sung task outputs khi task thật tạo file/artifact; không có output thì không thể mong đợi caching sản phẩm.

| API | Ý nghĩa |
| --- | --- |
| `providers.gradleProperty('key')` | Provider cho project property build-level |
| `providers.systemProperty('key')` | Provider cho JVM system property |
| `providers.environmentVariable('KEY')` | Provider cho OS env |
| `provider.isPresent()` | Kiểm tra có giá trị (có thể kích hoạt lookup) |
| `provider.get()` | Lấy giá trị hoặc báo thiếu nếu absent |
| `provider.orElse('fallback')` | Mặc định khi absent, vẫn trả Provider |
| `provider.map { ... }` | Chuyển đổi giá trị lazy |
| `provider.flatMap { ... }` | Tạo Provider phụ thuộc từ Provider khác |

### 8.3. Boolean: sự tồn tại khác với giá trị đúng/sai

Đừng kiểm tra `providers.gradleProperty('strict').isPresent()` để suy ra bật chế độ strict: người dùng có thể truyền `-Pstrict=false` mà property vẫn **tồn tại**.

~~~groovy
def strict = providers.gradleProperty('strict')
    .map { String value ->
        if (!value.equalsIgnoreCase('true') &&
            !value.equalsIgnoreCase('false')) {
            throw new GradleException(
                'strict chỉ nhận true hoặc false'
            )
        }
        return Boolean.parseBoolean(value)
    }
    .orElse(false)
~~~

`strict.get()` là Boolean, mặc định false khi absent, và báo lỗi khi nhập `-Pstrict=maybe`. Đây là đoạn minh họa đặt trong `build.gradle`, có thể dùng kết quả để cấu hình một task cụ thể.

### 8.4. Hai lưu ý về configuration cache

- Duyệt `System.getenv()` hoặc `System.getProperties()` **toàn bộ** trong configuration làm tăng số lượng configuration inputs và có thể gây mất cache không cần thiết. Nếu cần nhóm env có prefix, API như `providers.environmentVariablesPrefixedBy('JDK_')` (ở Gradle hỗ trợ) rõ ràng hơn.
- Configuration cache có thể lưu task state. Nếu resolve secret sớm và giữ nó trong field của task, giá trị nhạy cảm có thể xuất hiện trong dữ liệu cache. Provider API chỉ hỗ trợ xử lý an toàn khi **cách wiring và thời điểm đọc** đúng; nó không tự bảo đảm secret không lộ trong logs hay artifacts.

## 9. Multi-project: phạm vi và nguồn mặc định

Ví dụ cấu trúc:

~~~text
company-build/
├── settings.gradle
├── gradle.properties
├── app/build.gradle
└── core/build.gradle
~~~

**`settings.gradle`:**

~~~groovy
rootProject.name = 'company-build'
include 'app', 'core'
~~~

**`gradle.properties` ở root:**

~~~properties
appProfile=staging
coreMode=strict
~~~

Trong `app/build.gradle` bạn có thể đọc `providers.gradleProperty('appProfile')`; trong `core/build.gradle` đọc `providers.gradleProperty('coreMode')`. Cả hai xuất phát từ build-level source, mỗi project chọn tên property có ý nghĩa.

Lưu ý:
- `-PappProfile=production` có thể override thuộc tính build-level từ CLI, kể cả khi task được gọi là `:app:build`.
- `providers.gradleProperty` không tự tìm trong `app/gradle.properties` và `core/gradle.properties` như nguồn build-level.
- `systemProp.*` trong subproject file không phải cách cấu hình JVM system properties được Gradle hỗ trợ.
- Đừng coi `-P` là công cụ truyền system property sang JVM ứng dụng, hoặc cho rằng `:app:build` tự nhận mọi env của máy developer.
- Nếu mỗi project có quy tắc riêng phức tạp, dùng extension/configuration của convention plugin thay cho một tập tên property mơ hồ.

## 10. Secrets và CI: tách nguồn cấp khỏi nơi tiêu thụ

### 10.1. Nguồn cấp hợp lý

- Máy cá nhân: dùng `GRADLE_USER_HOME/gradle.properties` với quyền filesystem thích hợp cho credentials; **không commit** vào repository.
- CI: dùng secret store để cấp environment vars, ví dụ `ORG_GRADLE_PROJECT_repoToken` (project property có tiền tố chuẩn) hoặc `REPO_TOKEN` (env thông thường).
- Với credential của repository, ưu tiên API `credentials` của Gradle cho repository tương ứng, giúp tránh tự lắp ghép và log giá trị.
- Tránh đặt secret trực tiếp trong `-Ptoken=...` hoặc `-Dtoken=...` vì command line, shell history, logs hoặc process arguments có thể lộ.
- Không in `project.properties`, toàn bộ `System.getenv()`, `System.getProperties()` hoặc nội dung token.

Ví dụ minh họa chỉ **kiểm tra sự có mặt** của secret, không tiết lộ giá trị:

~~~groovy
def token = providers.environmentVariable('REPO_TOKEN')

tasks.register('checkTokenPresence') {
    doLast {
        println(token.isPresent() ? 'REPO_TOKEN present' : 'REPO_TOKEN absent')
    }
}
~~~

Đoạn này không thực hiện publishing. Trong task thật, lấy secret qua Provider ở execution time và sử dụng API phù hợp; không giữ secret đã resolve trong task state ở configuration time. Khi debug, log **tên khóa và trạng thái có/không** là đủ trong phần lớn trường hợp.

### 10.2. Gradle settings riêng với tham số ứng dụng

~~~properties
org.gradle.jvmargs=-Xmx2g
org.gradle.caching=true
~~~

Hai dòng trên là Gradle runtime properties. Không dùng tên `org.gradle.*` cho cờ ứng dụng tự định nghĩa. Nếu cần phiên bản Java để compile, cấu hình toolchain, ví dụ:

~~~groovy
plugins {
    id 'java'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}
~~~

`JAVA_HOME` và Java toolchain có trách nhiệm khác nhau. Toolchain Java 17 phải có sẵn hoặc đã cấu hình cơ chế cung cấp thích hợp; chỉ có `JAVA_HOME` không bảo đảm đúng compiler version nếu build yêu cầu toolchain khác.

## 11. Lỗi thường gặp

| Lỗi/hiện tượng | Nguyên nhân | Cách sửa |
| --- | --- | --- |
| `providers.gradleProperty('profile')` rỗng dù có `-Dprofile=x` | `-Dprofile` là system property, không phải project property | Dùng `-Pprofile=x` hoặc `-Dorg.gradle.project.profile=x` |
| `System.getProperty('profile')` rỗng dù `-Pprofile=x` | Project property không tự là JVM property | Đọc `providers.gradleProperty('profile')` |
| `providers.environmentVariable('profile')` rỗng dù root `gradle.properties` có `profile=x` | Nhầm file property với OS environment | Đọc bằng `providers.gradleProperty('profile')` |
| `ORG_GRADLE_PROJECT_PROFILE` không thành `profile` | Sai chữ hoa/thường trên Linux | Dùng `ORG_GRADLE_PROJECT_profile` |
| Root `profile=dev` bị một giá trị khác thay thế | `-P`, `-Dorg.gradle.project.*`, prefixed env hoặc user-home file ưu tiên hơn | Tìm và đối chiếu nguồn cấp theo thứ tự |
| `systemProp.demo.mode` trong `app/gradle.properties` không có tác dụng | Gradle không đọc `systemProp.*` ở subproject như root | Đặt ở root hoặc dùng `-D` |
| `providers.gradleProperty` không thấy `ext.foo` | Provider tìm build-level source; `ext` thuộc Project model | Dùng model/extension API tương ứng |
| `-Dapp.mode=ci` không thấy trong JavaExec/Test | JVM ứng dụng/test khác Gradle JVM | Cấu hình `systemProperty` ở task phù hợp |
| `-Pstrict=false` vẫn bị coi là true | Kiểm tra tồn tại chứ không parse chuỗi | Dùng `map` để parse/validate boolean |
| Thay env nhưng task không cập nhật | Đọc sớm, thiếu task input hoặc tác động cache | Dùng Provider + task input, kiểm tra up-to-date state |
| Heap của app không tăng dù có `org.gradle.jvmargs=-Xmx2g` | Cấu hình heap cho Gradle daemon | Cấu hình heap của Test/JavaExec riêng |
| Token xuất hiện trong logs/CI | Dump toàn bộ properties/env, in command line hoặc task logs | Xóa log, thu hồi/rotate token nếu đã lộ, dùng secret store |

**Cách chẩn đoán:** Xác định khóa và namespace → xác định nguồn cấp (CLI/JVM/env/file) → kiểm tra precedence nếu là project property → xác định process đang đọc → kiểm tra configuration/execution và Provider wiring → quan sát qua ví dụ dùng giá trị không nhạy cảm. `clean` không chữa được lỗi chọn sai namespace.

## 12. Bài tập có đáp án

**Bài 1:** Root đặt `profile=dev`, env đặt `ORG_GRADLE_PROJECT_profile=staging`, lệnh `-Pprofile=production`. Kết quả `providers.gradleProperty('profile')`? **`production`**, do `-P` ưu tiên cao nhất trong nhóm nguồn này.

**Bài 2:** `./gradlew help -Dregion=vn`. `providers.environmentVariable('region')` có tự nhận `vn` không? **Không**. Dùng `providers.systemProperty('region')` để đọc JVM system property.

**Bài 3:** Root file có đồng thời `systemProp.demo.mode=trace` và `demo.mode=debug`. Nếu không có override, `providers.systemProperty('demo.mode')` là **`trace`**, còn `providers.gradleProperty('demo.mode')` là **`debug`**.

**Bài 4:** Tại sao `./gradlew run -Dapp.mode=release` không đảm bảo ứng dụng nhận `release`? **Gradle JVM và JavaExec JVM khác nhau**; cần cấu hình task `run` để cấp system property cho JVM của ứng dụng.

**Bài 5:** `-Pstrict=false` rồi kiểm tra `hasProperty('strict')` để quyết định bật strict có đúng không? **Không**; property có tồn tại dù giá trị là false. Phải parse Boolean.

**Bài 6:** Muốn `:app` dùng profile khác `:core`, nên đặt thế nào? **Đặt tên rõ** (`appProfile`, `coreMode`) tại build-level source hoặc extension theo project, thay vì dựa vào file con hay tên `profile` chung có ý nghĩa mơ hồ.

**Bài 7:** Dùng các file ở phần 6, chạy ba lần: mặc định; với `-Pprofile=release`; với `-Dorg.gradle.project.profile=system` và `ORG_GRADLE_PROJECT_profile=env`. Quan sát đầu ra `showInputs` và giải thích tại sao kết quả đổi.

**Tiêu chí hoàn thành:** Bạn phân biệt được `-P`, `-D`, env thông thường, prefixed env và `gradle.properties`; viết được task dùng Provider; xác nhận được precedence và hiểu ranh giới giữa Gradle JVM và Java application/test JVM.

## Tài liệu chính thức để đối chiếu

- [Gradle: Build Environment Configuration](https://docs.gradle.org/current/userguide/build_environment.html) — các nhóm properties, cách cấp và thứ tự ưu tiên.
- [Gradle: ProviderFactory API](https://docs.gradle.org/current/javadoc/org/gradle/api/provider/ProviderFactory.html) — `gradleProperty`, `systemProperty` và `environmentVariable`.
- [Gradle: Properties and Providers](https://docs.gradle.org/current/userguide/properties_providers.html) — Provider, Property, `map`, `orElse`, lazy wiring.
- [Gradle: Configuration Cache Requirements](https://docs.gradle.org/current/userguide/configuration_cache_requirements.html) — environment/system properties như configuration inputs.
- [Gradle: Configuration Cache](https://docs.gradle.org/current/userguide/configuration_cache.html) — bảo vệ credentials và dữ liệu cache.
- [Gradle: JavaExec](https://docs.gradle.org/current/dsl/org.gradle.api.tasks.JavaExec.html) và [Gradle: Test](https://docs.gradle.org/current/dsl/org.gradle.api.tasks.testing.Test.html) — cấu hình JVM/process của task riêng.
