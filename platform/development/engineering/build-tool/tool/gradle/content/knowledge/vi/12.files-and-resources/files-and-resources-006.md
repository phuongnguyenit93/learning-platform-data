# Lọc tài nguyên, thay thế biến và giới hạn khi xử lý tệp nhị phân trong Gradle

Trong dự án Java, không phải mọi tệp dưới `src/main/resources` đều được đóng gói giống nhau. Có tệp phải chép nguyên trạng (PNG, PDF, font, ZIP, chứng chỉ công khai), có tệp văn bản cần thay biến theo version hoặc môi trường, và có tệp không được phép đưa vào sản phẩm. Gradle cho phép giải quyết ba nhu cầu đó bằng **`CopySpec`**, **`ProcessResources`**, `include`/`exclude`, `filesMatching`, `expand` và `filter`.

Nguyên tắc quan trọng nhất: **chỉ áp dụng bộ lọc nội dung lên những tệp văn bản đã xác định rõ**. Các bộ lọc như `expand` hoặc `filter` đọc và ghi lại nội dung dưới dạng ký tự; nếu áp dụng lên ảnh, font, file nén hay dữ liệu nhị phân, chúng có thể làm hỏng tệp dù bản gốc không chứa placeholder.

Bài học tập trung vào Gradle Kotlin DSL (`build.gradle.kts`), có ví dụ chạy được với Java plugin, cách theo dõi input để Gradle tái build khi biến thay đổi, kiểm chứng tài nguyên sau xử lý và các lỗi dễ gặp khi đóng gói.

## 1. Phân biệt ba việc thường đều gọi là “filter”

| Nhu cầu | Gradle API chính | Ví dụ | Tác động lên bytes |
| --- | --- | --- | --- |
| **Lọc tệp theo tên/đường dẫn** | `include`, `exclude`, `filesMatching`, `filesNotMatching` | Chỉ sao chép `**/*.properties`, bỏ `**/*.bak` | Tự việc chọn tệp **không** biến đổi nội dung |
| **Biến đổi nội dung tệp văn bản** | `expand`, `filter` | Thay `${appVersion}` thành `2.1.0` | Có thể thay nội dung, encoding và kiểu newline |
| **Chọn tệp vào đầu ra Java/JAR** | `processResources`, source sets, copy/archive specs | Đưa `config/app.properties` vào classpath, không đưa `.secret` | Chỉ các tệp được chọn mới có trong output |

Một file có thể được **chọn để chép** nhưng **không được biến đổi**. Ví dụ `images/logo.png` cần nằm trong JAR của ứng dụng Java nhưng không được đưa qua template engine.

Ngoài ra, `filesMatching("**/*.properties") { ... }` **không tự loại các file khác khỏi bản sao**; nó chỉ áp dụng hành động cho những file khớp. Muốn loại file khỏi output, dùng `include`/`exclude` (hoặc `exclude()` trong hành động phù hợp).

## 2. Luồng tài nguyên mặc định của Java plugin

Với Java plugin:

```kotlin
plugins {
    java
}
```

Quy ước thông dụng:

```text
src/
└── main/
    ├── java/                 # mã nguồn Java
    └── resources/            # tài nguyên gốc
        ├── config/app.properties
        ├── templates/email.txt
        └── images/logo.png

./gradlew processResources
              |
              v
build/resources/main/
    ├── config/app.properties
    ├── templates/email.txt
    └── images/logo.png

./gradlew jar
              |
              v
JAR chứa resource output của main source set
```

- `processResources` có kiểu `org.gradle.language.jvm.tasks.ProcessResources`, là một dạng `Copy` task do Java plugin cấu hình.
- Nó lấy tài nguyên từ source set `main` và đưa tới thư mục output tương ứng (mặc định `build/resources/main`).
- Task `jar` của Java plugin đóng gói output của main source set, trong đó có tài nguyên đã được xử lý.
- Tài nguyên test nằm trong `src/test/resources` và thường do `processTestResources` xử lý. Sửa `processResources` **không tự động** áp dụng thay biến cho test resources.

Đường dẫn trên là **quy ước mặc định**, có thể khác nếu build thay đổi source sets hoặc output layout. Tài nguyên đi vào JAR thông qua task output, nên không cần sửa trực tiếp `src/main/resources` mỗi lần phát hành.

**Không ghi file đã thay biến đè lên file nguồn** trong `src/main/resources`. Giữ template nguyên bản trong Git, sinh output trong `build/` để build có thể tái lập và dễ kiểm tra diff.

## 3. Chọn tệp bằng `include` và `exclude`

Ví dụ độc lập trong `build.gradle.kts`, sao chép chỉ HTML/CSS/JS từ `src/site` vào thư mục riêng:

```kotlin
tasks.register<Copy>("copyWebText") {
    from("src/site") {
        include("**/*.html", "**/*.css", "**/*.js")
        exclude("**/*.draft.html")
        exclude("**/temp/**")
    }
    into(layout.buildDirectory.dir("web-text"))
}
```

- `from("src/site")`: nguồn tệp/thư mục; đường dẫn tương đối được Gradle hiểu từ project hiện tại.
- `include(...)`: chỉ nhận những file khớp pattern (nếu không khai báo include, mặc định không hạn chế loại file theo extension).
- `exclude(...)`: loại đường dẫn khớp pattern ngay cả khi nó cũng khớp include.
- `into(layout.buildDirectory.dir(...))`: nơi chép output; dùng Gradle layout để tránh hard-code đường dẫn tuyệt đối.
- `**/*.html`: pattern Ant-style, tìm HTML ở root hoặc thư mục con.
- `**/temp/**`: loại cây con tên `temp` theo pattern đã chọn.

Các pattern dùng **đường dẫn tương đối bên trong nguồn/copy spec**, không phải biểu thức regex tùy ý. `*.png` khác `**/*.png`; trong cấu trúc lồng nhau, dùng `**/` khi muốn khớp nhiều cấp.

Nếu task trên chạy và `src/site` không tồn tại, sẽ không có tệp để copy; muốn quan sát rõ, cần tạo các file mẫu trong thư mục nguồn. Ví dụ này minh họa lọc **file paths**, không phải thay nội dung.

### `include` khác `filesMatching`

```kotlin
tasks.register<Copy>("copyResourcesDemo") {
    from("src/main/resources")
    into(layout.buildDirectory.dir("demo-resources"))

    // Chỉ đổi nội dung text của một file phù hợp; file khác vẫn được copy.
    filesMatching("config/banner.txt") {
        filter { line: String ->
            line.replace("@APP_NAME@", "Catalog")
        }
    }

    // Thực sự loại những tệp backup khỏi output.
    exclude("**/*.bak")
    filteringCharset = "UTF-8"
}
```

Nếu nguồn có `config/banner.txt`, nó có thể bị biến đổi; `images/logo.png` vẫn được copy **nguyên trạng** vì không khớp `config/banner.txt`. Tệp `.bak` bị loại khỏi output. Khi biến thay đổi từ cấu hình, nên khai báo biến đó trong inputs của Copy task (xem mục 7).

Các `filesMatching` actions có thể được gọi cho từng file khớp khi Gradle sao chép, vì vậy chúng phải có logic ổn định và không dựa vào side effect bất định.

## 4. Thay biến bằng `expand`: cú pháp của template khác cú pháp Kotlin

`CopySpec.expand` dùng **Groovy `SimpleTemplateEngine`** để xử lý file nguồn. Template có placeholder kiểu `$name` hoặc `${name}`; các biểu thức bên trong `${...}` là **biểu thức Groovy trong file template**.

Ví dụ file **`src/main/resources/config/build-info.properties`** (đây là văn bản thuần, không phải Kotlin code):

```properties
app.name=${appName}
app.version=${appVersion}
app.environment=${targetEnv}
```

Một file `build.gradle.kts` có thể cung cấp ba giá trị qua:

```kotlin
filesMatching("config/build-info.properties") {
    expand(
        mapOf(
            "appName" to "catalog-demo",
            "appVersion" to "2.1.0",
            "targetEnv" to "qa"
        )
    )
}
```

Đây là **mảnh ghép** đặt bên trong cấu hình của task `Copy` hoặc `ProcessResources`, chưa phải file chạy độc lập. Output text mong muốn:

```properties
app.name=catalog-demo
app.version=2.1.0
app.environment=qa
```

Ở đây:

- `mapOf(...)` là biểu thức Kotlin **trong build script**.
- `${appVersion}` là placeholder **trong nội dung file tài nguyên**, được Groovy template engine xử lý lúc copy.
- Giá trị map chỉ được thay trong những file nhận lời gọi `expand`.
- `expand` không phải thay chuỗi cứng đơn giản: engine hỗ trợ Groovy expressions; vì vậy **không dùng nó cho template do người dùng không đáng tin cậy tải lên**.
- Nếu template chứa placeholder lạ như `${undefinedKey}`, engine có thể báo lỗi thiếu binding/không thể đánh giá template. Không nên cố đưa cả mọi biến của `project.properties` vào template để “cho khỏi lỗi”.

**Rủi ro trùng placeholder:** Nhiều ứng dụng (ví dụ Spring) cũng dùng cú pháp `${ENV_NAME}` để nội suy lúc ứng dụng chạy. Nếu áp dụng `expand` cho toàn bộ `application.yml`/`application.properties`, Gradle có thể diễn giải các placeholder này **ngay lúc build** và làm mất hoặc thay sai ý nghĩa runtime. Hãy **chỉ expand những file template được chọn có chủ đích**, hoặc chọn placeholder riêng như `@BUILD_VERSION@` với phép thay literal.

## 5. Ví dụ hoàn chỉnh: Java `processResources` chỉ expand một file text

Ví dụ này dùng Gradle Kotlin DSL và Java plugin. Không cần mã Java để thử việc xử lý resource.

### 5.1. Cấu trúc thư mục

```text
resource-filtering-demo/
├── settings.gradle.kts
├── build.gradle.kts
├── gradlew
├── gradlew.bat
├── gradle/wrapper/...
└── src/main/resources/
    ├── config/build-info.properties
    └── config/runtime.properties
```

Nếu project hiện có Wrapper, sử dụng bộ Wrapper đó. Nếu chưa có, tạo Wrapper theo tài liệu chính thức hoặc sử dụng một bản Gradle đã cài thích hợp với JVM của bạn.

### 5.2. File settings

**`settings.gradle.kts`:**

```kotlin
rootProject.name = "resource-filtering-demo"
```

### 5.3. File `build.gradle.kts` đầy đủ

```kotlin
import org.gradle.language.jvm.tasks.ProcessResources

plugins {
    java
}

version = "2.1.0"

val appName = "catalog-demo"
val appVersion = version.toString()
val targetEnv = providers.gradleProperty("targetEnv")
    .getOrElse("dev")
    .trim()

require(targetEnv in setOf("dev", "qa", "prod")) {
    "Unsupported targetEnv: $targetEnv"
}

tasks.named<ProcessResources>("processResources") {
    filteringCharset = "UTF-8"

    // Theo dõi các tham số ảnh hưởng đến nội dung resource được sinh.
    inputs.property("template.appName", appName)
    inputs.property("template.appVersion", appVersion)
    inputs.property("template.targetEnv", targetEnv)

    // Chỉ file này được đưa qua Groovy template engine.
    filesMatching("config/build-info.properties") {
        expand(
            mapOf(
                "appName" to appName,
                "appVersion" to appVersion,
                "targetEnv" to targetEnv
            )
        ) {
            escapeBackslash.set(true)
        }
    }
}
```

**`src/main/resources/config/build-info.properties`:**

```properties
app.name=${appName}
app.version=${appVersion}
app.environment=${targetEnv}
```

**`src/main/resources/config/runtime.properties`:**

```properties
runtime.endpoint=${REMOTE_SERVICE_URL}
runtime.label=unchanged
```

Trong `runtime.properties`, placeholder `${REMOTE_SERVICE_URL}` **được giữ nguyên** để một hệ thống runtime phù hợp có thể xử lý sau, bởi file này không khớp pattern được expand. Ví dụ chỉ minh họa **bảo toàn văn bản**; việc runtime thực sự nội suy placeholder phụ thuộc framework/ứng dụng, không phải Java Properties tự thực hiện.

### 5.4. Chạy và kiểm tra output

Linux/macOS:

```bash
./gradlew processResources -PtargetEnv=qa --console=plain
cat build/resources/main/config/build-info.properties
cat build/resources/main/config/runtime.properties
```

Windows PowerShell:

```powershell
.\gradlew.bat processResources -PtargetEnv=qa --console=plain
Get-Content build/resources/main/config/build-info.properties
Get-Content build/resources/main/config/runtime.properties
```

File `build/resources/main/config/build-info.properties` có nội dung:

```properties
app.name=catalog-demo
app.version=2.1.0
app.environment=qa
```

File `build/resources/main/config/runtime.properties` vẫn có nội dung:

```properties
runtime.endpoint=${REMOTE_SERVICE_URL}
runtime.label=unchanged
```

Lệnh `gradlew processResources` có thể in thông tin `Task`, `BUILD SUCCESSFUL`, cache hoặc `UP-TO-DATE` khác nhau theo Gradle version/môi trường, vì vậy **không giả định một stdout Gradle cố định**. Các khối `properties` trên là **nội dung file đầu ra**, không phải stdout của bản thân Gradle.

Đổi sang:

```bash
./gradlew processResources -PtargetEnv=prod --console=plain
```

Nội dung dòng `app.environment` sẽ là `prod`. Nếu bỏ `-PtargetEnv`, fallback hợp lệ là `dev`. Giá trị `-PtargetEnv=unknown` sẽ bị `require` chặn trong Configuration với thông báo về cấu hình không được hỗ trợ.

### 5.5. Vì sao phải dùng `inputs.property`?

Trong ví dụ, `appName`, `appVersion`, `targetEnv` là các giá trị được closure đưa vào quá trình lọc. Các `inputs.property(...)` công khai những tham số **ảnh hưởng đến output** để Gradle có thể xét thay đổi trong up-to-date checks và build cache khi áp dụng.

Nếu task chỉ khai báo file nguồn nhưng **không theo dõi giá trị dùng để thay biến**, task có thể bị đánh giá là không cần chạy dù giá trị mới phải tạo output khác. Với `ProcessResources`, hãy khai báo rõ các inputs động này theo đúng Gradle task API.

Đừng đưa giá trị ngẫu nhiên như `System.currentTimeMillis()` trực tiếp vào template rồi mong output tái lập. Nếu cần build identifier, hãy định nghĩa nguồn input rõ và chấp nhận rằng giá trị thay đổi sẽ làm task phải thực hiện lại.

### 5.6. Kiểm tra resource trong JAR

Khi Java plugin tạo JAR, tài nguyên từ `processResources` thường được đưa vào output của main source set và đóng gói trong JAR:

```bash
./gradlew jar -PtargetEnv=qa
```

Để xem danh sách thành phần của JAR, có thể dùng `jar tf <duong-dan-file-jar>` với JDK. Đừng giả định đường dẫn/filename JAR giống hệt trên mọi project: archive name, version và destination có thể được build cấu hình khác đi.

**Lưu ý bảo mật:** bất cứ chuỗi nào đã được expand vào `build/resources/main` cũng có thể nằm trong JAR và được người nhận đọc. Vì vậy chỉ nhúng **cấu hình công khai**, như tên app, version hoặc nhãn môi trường. Không nhúng mật khẩu, API token hay private key vào packaged resource, kể cả khi chúng lấy từ biến môi trường hoặc CI secrets.

## 6. Giới hạn cốt lõi: tại sao không filter file nhị phân?

Ảnh PNG/JPEG, PDF, JAR, ZIP, font `ttf`/`woff`, file âm thanh và nhiều tệp định dạng riêng là **byte sequences**, không nhất thiết tạo thành văn bản UTF-8 hợp lệ.

Khi dùng:

```kotlin
// MẪU SAI: filter mọi tệp, kể cả nhị phân
tasks.named<ProcessResources>("processResources") {
    expand(mapOf("appVersion" to "2.1.0"))
}
```

Gradle áp dụng template processing cho tất cả file thuộc copy spec. Với binary data, việc đọc dưới dạng ký tự và mã hóa lại có thể:

- Thay byte không hợp lệ bằng ký tự thay thế hoặc làm khác các byte ban đầu.
- Thay newline/escape hoặc nhận nhầm chuỗi `$` thành template marker.
- Làm lỗi parser của template engine nếu binary chứa sequence không hợp lệ.
- Hỏng header/checksum của PNG, ZIP, PDF và khiến ứng dụng không còn đọc được file.

**Giải pháp đúng: chọn tệp văn bản thật hẹp.** Ví dụ chỉ `config/build-info.properties`, `templates/build-info.txt`, một file JSON template có chủ đích. Những file còn lại được copy theo byte gốc.

Một `.svg` có nội dung XML dạng text, nhưng không có nghĩa mọi SVG nên được expand; cấu trúc SVG có thể chứa ký tự đặc biệt hoặc tham chiếu cần giữ nguyên. Việc có thể đọc bằng text editor chỉ là **điều kiện cần**, không đủ để áp dụng một template engine tùy ý.

### Mẫu copy gồm text cần xử lý và binary cần giữ

```kotlin
tasks.register<Copy>("prepareWebAssets") {
    into(layout.buildDirectory.dir("web-assets"))
    filteringCharset = "UTF-8"

    // Nhánh 1: biến đổi đúng HTML template theo yêu cầu.
    from("src/web") {
        include("**/*.html")
        filesMatching("**/*.html") {
            filter { line: String ->
                line.replace("@APP_NAME@", "Catalog")
            }
        }
    }

    // Nhánh 2: giữ nguyên byte của ảnh và font.
    from("src/web") {
        include("**/*.png", "**/*.jpg", "**/*.woff2")
    }
}
```

Đây là **một task Copy hợp lệ**, với giả định thư mục `src/web` có các file tương ứng. File HTML được biến đổi theo từng dòng; file ảnh/font không đi qua `filter`. Các nhánh `from` là những child copy specs riêng. Nếu cần cập nhật `APP_NAME` động, hãy khai báo nó qua task input như ở ví dụ chính.

Không nên dựa vào quy tắc “mọi file có đuôi `.properties` chắc chắn là text UTF-8”. Một số project lưu data file có extension không chuẩn; trước khi lọc, cần biết **định dạng thực tế và charset** của từng nhóm file.

## 7. `filter` theo dòng và `expand` theo template khác nhau

### `expand`: thay placeholder theo Groovy template

```kotlin
filesMatching("config/build-info.properties") {
    expand(mapOf("appVersion" to "2.1.0"))
}
```

Ưu điểm: cú pháp template `${appVersion}` rõ ràng, tiện cho nhiều biến và biểu thức. Hạn chế: `SimpleTemplateEngine` xử lý văn bản như template Groovy, có thể gặp xung đột với cú pháp `${...}` của ứng dụng và không phù hợp cho nguồn template không đáng tin cậy.

### `filter`: biến đổi từng dòng

Ví dụ đoạn dưới đặt **bên trong `CopySpec` hoặc `filesMatching`**, khi nguồn text dùng token `@APP_VERSION@`:

```kotlin
filter { line: String ->
    line.replace("@APP_VERSION@", "2.1.0")
}
```

Nếu file nguồn là:

```properties
build.version=@APP_VERSION@
runtime.value=${DO_NOT_REPLACE_AT_BUILD_TIME}
```

Sau lọc sẽ có:

```properties
build.version=2.1.0
runtime.value=${DO_NOT_REPLACE_AT_BUILD_TIME}
```

Ưu điểm: chỉ thay một token literal, tránh đụng cú pháp `${...}` của runtime. Hạn chế: line-based transformer làm việc với **các dòng text**, không phù hợp khi token cần thay trải qua nhiều dòng hoặc khi phải bảo toàn byte-for-byte định dạng ban đầu. Cả `filter` lẫn `expand` đều cần khoanh vùng loại file và charset.

Với `filter { line -> ... }`, có thể trả `null` để loại cả dòng. Cẩn thận: loại dòng khác với loại **file**; nếu mọi dòng bị loại, file kết quả có thể rỗng chứ không tự biến mất. Nếu muốn bỏ cả file, dùng `exclude`/quy tắc lọc path thích hợp.

### `ReplaceTokens` của Ant: có giới hạn theo phiên bản

Một số ví dụ Gradle cũ dùng:

```kotlin
import org.apache.tools.ant.filters.ReplaceTokens

// MẢNH GHÉP, chỉ chạy khi Ant FilterReader hiện diện trên build classpath.
filter(ReplaceTokens::class, "tokens" to mapOf("APP_VERSION" to "2.1.0"))
```

`ReplaceTokens` xử lý token kiểu `@APP_VERSION@`, nhưng từ **Gradle 10**, tài liệu Gradle nêu rằng Ant classes không còn mặc định có sẵn trên classpath của build scripts. Nếu tiếp tục dùng `FilterReader` kiểu Ant, phải cấu hình dependency Ant phù hợp cho build logic. **Đừng sao chép snippet Ant từ tutorial cũ rồi mặc định nó chạy trên mọi Gradle version.**

Để thay một vài token literal, `filter { line: String -> line.replace(...) }` thường đơn giản hơn vì không yêu cầu import Ant. Khi nhiều file cùng cần biến đổi nội dung lớn, cân nhắc một task/plugin chuyên biệt với inputs/outputs được mô tả rõ.

## 8. `filteringCharset`: bảo vệ tiếng Việt và các ký tự ngoài ASCII

Các phép lọc nội dung phải giải mã byte thành ký tự rồi mã hóa trở lại. Vì vậy cần biết file nguồn dùng encoding nào.

```kotlin
tasks.named<ProcessResources>("processResources") {
    filteringCharset = "UTF-8"
}
```

- `filteringCharset` áp dụng khi Gradle **đọc/ghi file để filter**, không có nghĩa đổi encoding của mọi file được sao chép không qua filter.
- Nếu bỏ qua cấu hình, các API filtering có thể dùng **charset mặc định của JVM**, dễ khác giữa laptop và CI.
- `filteringCharset = "UTF-8"` **không tự sửa** file gốc đang lưu Windows-1258, ISO-8859-1 hay một encoding khác.
- Dữ liệu text có ký tự tiếng Việt cần được lưu dưới encoding nhất quán, thường chọn UTF-8, và kiểm tra đầu ra thực tế.
- Một số định dạng có quy tắc escaping riêng. Chẳng hạn Java `.properties`, JSON, YAML hoặc XML có ngữ nghĩa riêng khi parser đọc. Filter thay text **không tự escape hợp lệ** cho từng định dạng.

Ví dụ nếu muốn đưa tên hiển thị `Bản dựng QA` vào file JSON, không chỉ thay chuỗi tùy ý vào giữa dấu nháy nếu giá trị có ký tự `"`, `\` hay newline. Cần dùng serializer hoặc escape đúng quy tắc JSON. Với XML/YAML cũng tương tự. Cấu hình charset chỉ giải quyết **mã hóa**, không giải quyết **escaping theo định dạng**.

### Bẫy backslash trong `expand`

Groovy `SimpleTemplateEngine` có cách xử lý escape, ví dụ `\n`, `\t`, `\\`. Một template chứa đường dẫn Windows hoặc regex có thể bị thay đổi bất ngờ dù placeholder được thay đúng.

Để giữ chuỗi backslash literal trong template khi dùng Gradle hỗ trợ `ExpandDetails` (từ Gradle 7.2), cấu hình:

```kotlin
filesMatching("config/build-info.properties") {
    expand(mapOf("appVersion" to "2.1.0")) {
        escapeBackslash.set(true)
    }
}
```

Giá trị `true` bảo `SimpleTemplateEngine` **không chuyển đổi** những escape sequence trong file nguồn thành ký tự điều khiển theo mặc định. Đây là lý do ví dụ ở mục 5 dùng `escapeBackslash.set(true)`.

**Nhưng:** tùy chọn này **không biến binary thành text an toàn**, không bảo vệ mọi cú pháp placeholder `${...}` và không bảo đảm output giống nguyên từng byte. Nó chỉ điều khiển riêng phần xử lý backslash của template engine.

## 9. Quản lý placeholder trùng với biến runtime

Đây là một tình huống rất hay gặp trong ứng dụng Spring hoặc file cấu hình cho container.

Giả sử nguồn `application.yml`:

```yaml
service:
  endpoint: ${SERVICE_ENDPOINT:http://localhost:8080}
  name: ${spring.application.name}
```

Những placeholder này thuộc **framework/runtime**. Nếu Gradle áp dụng `expand(mapOf("buildVersion" to "..."))` lên toàn bộ `application.yml`, template engine có thể thử diễn giải `${SERVICE_ENDPOINT:http://localhost:8080}` hoặc `${spring.application.name}` như Groovy expressions, dẫn tới lỗi hoặc biến đổi không mong muốn.

Có ba cách xử lý có chủ đích:

1. **Tách file build-time riêng** như `config/build-info.properties` rồi chỉ `filesMatching` file đó, như bài thực hành.
2. Dùng placeholder khác biệt như `@BUILD_VERSION@` và chỉ thay literal `@BUILD_VERSION@` bằng `filter`, giữ nguyên mọi `${...}` runtime.
3. Nếu cần tạo file cấu hình theo framework phức tạp, dùng công cụ cấu hình/serialization hiểu đúng format và tách rõ build-time với runtime concerns.

Không chọn “escape mọi ký tự dollar” cho toàn bộ file mà chưa kiểm tra semantics của template và ứng dụng. Sửa một placeholder có thể che lỗi ở những placeholder khác.

## 10. Inputs/outputs, cấu hình lazy và khả năng tái lập build

`ProcessResources` và `Copy` là Gradle tasks: nguồn và đích cần được khai báo qua API task, để Gradle theo dõi trạng thái, sắp xếp dependencies và kiểm tra các thay đổi.

Ví dụ đơn giản về tham số thay biến:

```kotlin
val label = providers.gradleProperty("buildLabel").getOrElse("local")

tasks.named<ProcessResources>("processResources") {
    inputs.property("filtered.buildLabel", label)
    filesMatching("config/label.txt") {
        expand(mapOf("buildLabel" to label))
    }
}
```

Đây là đoạn **bổ sung** vào `build.gradle.kts` đã áp dụng Java plugin. Nó buộc người đọc xem `buildLabel` vừa là giá trị cần thay, vừa là input của task. Nếu chỉ thay biến trong callback mà Gradle không biết input đã đổi, có nguy cơ kết quả output bị coi là hợp lệ dù dữ liệu mới yêu cầu xử lý lại.

Các lựa chọn hợp lý:

- Nếu biến là **cấu hình build-time**, dùng `providers.gradleProperty` hoặc typed `Property<String>`; ghi input rõ và có default/validation đúng nghiệp vụ.
- Nếu biến là **secret**, đừng expand nó vào file đóng gói; dùng môi trường triển khai hoặc secret management ở runtime.
- Nếu output của task khác là nguồn cần copy, ưu tiên `from(producerTask.flatMap { it.outputFile })` hoặc task provider artifact wiring để Gradle giữ implicit dependency, thay vì đoán đường dẫn.
- Nếu file nguồn đã được Gradle quản lý như input, ưu tiên file paths từ `layout.projectDirectory`/`layout.buildDirectory`, tránh hardcoded absolute paths.
- Nếu phải sinh file cấu hình mới từ nhiều input, một custom task có `@Input`, `@OutputFile` và `@TaskAction` có thể rõ ràng hơn chuỗi `filter` nhiều tầng.

**Cache lưu ý:** up-to-date checks, build cache và configuration cache là cơ chế khác nhau. Filter có cấu hình đúng vẫn không bảo đảm task được lấy từ build cache; cacheability và tính tái lập còn phụ thuộc loại task và metadata. `Copy`/`ProcessResources` không nên được mặc định coi là cacheable chỉ vì có `inputs.property`.

### Tránh làm việc ở Configuration

Không nên chép tài nguyên bằng `project.copy { ... }` tại top-level chỉ để xử lý file trước các task. Cách đó tạo side effects khi Gradle đang cấu hình, làm `help` cũng có thể thay đổi filesystem, khó tương thích configuration cache và làm Gradle không theo dõi output như task.

Đối với công việc chép lọc đơn giản, dùng `tasks.register<Copy> { ... }` hoặc `tasks.named<ProcessResources> { ... }`. Nếu cần thao tác copy trong custom task action, dùng service `FileSystemOperations` theo yêu cầu của Gradle, thay vì gọi `Project.copy` tại execution time trong logic muốn tương thích configuration cache.

## 11. Duplicate resources và thứ tự ghi: cẩn thận khi nhiều nguồn trùng path

Một build có thể đưa tệp cùng đích từ nhiều thư mục:

```text
src/main/resources/config/app.properties
src/generated/resources/config/app.properties

→ cả hai cùng muốn thành config/app.properties
```

Nếu có nhiều source chứa cùng relative path, Gradle áp dụng **duplicates strategy** của copy spec. Tùy cấu hình và phiên bản, việc gặp duplicate có thể gây lỗi hoặc hành vi không như mong đợi. Không nên âm thầm trông cậy “file source thứ hai luôn ghi đè file trước”.

Khi cần phát hiện duplicate sớm:

```kotlin
import org.gradle.api.file.DuplicatesStrategy
import org.gradle.language.jvm.tasks.ProcessResources

tasks.named<ProcessResources>("processResources") {
    duplicatesStrategy = DuplicatesStrategy.FAIL
}
```

Đây là **snippet bổ sung** vào build đã có Java plugin. Nếu các nguồn chép hai file về cùng relative path, `FAIL` chủ động báo lỗi để nhóm sửa source hoặc cấu hình. Chọn `EXCLUDE`/`INCLUDE` chỉ khi có chủ đích với các bản sao; không đặt `EXCLUDE` tùy tiện vì có thể che một file đáng lẽ cần xử lý.

Nếu muốn một nguồn được ưu tiên, hãy thiết kế nguồn và destination có thứ tự rõ, hoặc tạo riêng file đầu ra ở một task producer, để chỉ có **một chủ sở hữu** cho artifact cuối.

## 12. Cách xác minh binary vẫn nguyên vẹn

Giả sử project có `src/main/resources/images/logo.png` và sau `processResources` có `build/resources/main/images/logo.png`.

Trên Linux/macOS, có thể so sánh hash:

```bash
sha256sum src/main/resources/images/logo.png
sha256sum build/resources/main/images/logo.png
```

Trên Windows PowerShell:

```powershell
Get-FileHash src/main/resources/images/logo.png -Algorithm SHA256
Get-FileHash build/resources/main/images/logo.png -Algorithm SHA256
```

Nếu tài nguyên nhị phân được copy nguyên trạng, **hai SHA-256 digest phải trùng nhau**. Hai lệnh trên chỉ là cách kiểm chứng với một file có thật; trong bài thực hành ở mục 5 không cung cấp `logo.png`, nên chỉ chạy sau khi project đã có file đó.

Một số hệ điều hành/format có metadata tách khỏi nội dung; SHA-256 ở đây kiểm tra **bytes của file**, không kiểm tra toàn bộ thông tin ngoài file. Nếu file binary nằm trong JAR, để xác minh cần trích entry tương ứng rồi so sánh bytes, vì hash của cả JAR hiển nhiên khác hash PNG.

Với text đã thay biến, nên kiểm tra **nội dung output** thay vì so hash với template vì hash khác nhau là kết quả mong đợi. Có thể bổ sung automated test chạy trên processed resources để xác minh placeholder build-time đã được thay hết và placeholder runtime được giữ nguyên.

### Lược đồ test có ý nghĩa

```text
Text input (build-info.properties)
    -> processResources
    -> assert app.version đã là version cụ thể
    -> assert không còn ${appVersion}

Runtime input (runtime.properties)
    -> processResources
    -> assert ${REMOTE_SERVICE_URL} còn nguyên

Binary input (logo.png)
    -> processResources
    -> assert SHA-256 nguồn == SHA-256 đầu ra
```

Đây là checklist xác minh, **không phải output terminal**. Việc kiểm tra trên CI nên sử dụng file fixture nhị phân có thật, cố định bytes và dự kiến thay đổi theo version.

## 13. Khi nào dùng Copy, Sync, ProcessResources, Jar và task riêng?

| Công cụ | Trường hợp phù hợp | Điều cần chú ý |
| --- | --- | --- |
| `tasks.register<Copy>` | Chép tài nguyên độc lập, gói asset cho web hoặc phân phối | Quy định rõ `from`, `into`, inputs và vùng output |
| `tasks.register<Sync>` | Giữ thư mục đích đồng nhất với nguồn | Có thể **xóa** file trong destination không thuộc nguồn copy; chỉ dùng với thư mục do task sở hữu |
| `tasks.named<ProcessResources>` | Xử lý main resources của Java plugin | Mặc định đã có nguồn/đích; thêm `filesMatching` đủ hẹp |
| `tasks.named<ProcessResources>("processTestResources")` | Nếu cần xử lý test resources | Kiểm tra đúng task/output của test source set; không áp dụng nhầm cấu hình production |
| `tasks.named<Jar>` | Kiểm soát các mục khi đóng gói JAR | Tránh áp dụng expand/filter toàn JAR; JAR có class và binary entries |
| Custom task với `@Input`, `@OutputFile` | Tạo file cấu hình phức tạp hoặc có validation riêng | Tự khai báo toàn bộ inputs/outputs và triển khai logic đúng giai đoạn |

**Đừng dùng `Sync` trỏ vào thư mục đang được nhiều task khác cùng ghi**, vì việc dọn những file không thuộc source của Sync có thể xóa output của task khác. Tương tự, đừng để một `Copy` task filter lại những file đã qua `processResources` mà không xác định đúng nguồn, tránh thay biến nhiều lần.

## 14. Các lỗi thường gặp và hướng sửa

| Triệu chứng | Nguyên nhân thường gặp | Hướng xử lý |
| --- | --- | --- |
| PNG/JPG không mở được sau build | Áp dụng `expand` hoặc `filter` toàn bộ resources | Chỉ filter text qua `filesMatching`; so SHA-256 của binary |
| `MissingPropertyException` hoặc template evaluation error | File chứa `${...}` không có key trong map hoặc dùng syntax không phải Groovy template | Thu hẹp pattern; kiểm tra tên key và biểu thức trong template |
| Spring placeholder biến mất hoặc build fail | `expand` đụng `${spring...}`/`${ENV...}` vốn dành cho runtime | Tách file build-info hoặc dùng token literal `@...` |
| Tiếng Việt trong output thành ký tự lỗi | `filteringCharset` khác encoding file nguồn/JVM default | Lưu file bằng UTF-8, dùng `filteringCharset = "UTF-8"`, kiểm tra bytes và parser |
| Chuỗi `\n` bất ngờ thành newline | `SimpleTemplateEngine` xử lý backslash escapes | Dùng `escapeBackslash.set(true)` khi phù hợp |
| Đổi `-PtargetEnv` nhưng output không đổi | Giá trị thay biến không được theo dõi như task input hoặc build lấy output cũ | Khai báo `inputs.property`; kiểm tra Gradle task state/outputs |
| Không thấy file trong JAR | File bị `exclude`, source set sai, hoặc task đóng gói không lấy processed resources | Kiểm tra `processResources`, output folder và entries JAR |
| File bị thay biến không có trong `build/resources/main` | `filesMatching` không **tự thêm** file, pattern/source sai | Đảm bảo file nằm trong source set hoặc được `from(...)`; sửa relative pattern |
| Một file xuất hiện nhiều lần hoặc lỗi duplicate | Hai nguồn copy về cùng destination path | Xem CopySpec, `duplicatesStrategy`; ưu tiên `FAIL` để chẩn đoán |
| `ReplaceTokens` unresolved khi nâng Gradle | Thiếu Ant trên build classpath ở Gradle mới | Dùng line-based `filter` hoặc bổ sung Ant cho build logic thích hợp |
| Chuỗi JSON/YAML hỏng cấu trúc sau thay | Thay giá trị mà không escape theo format | Sử dụng serializer/escaping của format, validate output |
| Build thay đổi tệp nguồn | Copy/expand được thiết kế ghi vào source directory | Đưa output vào `build/`; template nguồn chỉ đọc |
| File bị sửa ngay lúc chạy `gradlew help` | Copy logic chạy eagerly trong Configuration | Đăng ký `Copy` hoặc `ProcessResources` task, làm việc khi task thực thi |
| Secret bị lộ trong JAR | Expand `-Ppassword` hoặc env token vào resource | Dừng nhúng secret; quản lý tại runtime, thu hồi token nếu đã phát hành |
| Không giống nhau giữa Windows và Linux | Charset mặc định, đường dẫn tuyệt đối, line endings hoặc biến môi trường khác | Thiết lập charset rõ, dùng Gradle layout, kiểm tra output ở CI |

## 15. Quy trình xử lý sự cố có thứ tự

1. Xác định **file nguồn và file output**, source set/module đúng, và task chép thực sự là `processResources`, `processTestResources` hay `Copy` tùy chỉnh.
2. Phân loại tệp đang lỗi thành **text có template**, **text không nên biến đổi** hoặc **binary**. Không đoán chỉ từ extension.
3. Kiểm tra `include`, `exclude`, `filesMatching`, `filesNotMatching`, các child copy specs và duplicate source paths.
4. Với text bị thay sai, kiểm tra placeholder nào thuộc **Gradle build-time** và placeholder nào thuộc **runtime/framework**; chọn `expand` hoặc thay literal phù hợp.
5. Kiểm tra charset và backslash handling, nhất là khi có tiếng Việt, Windows paths, regex hoặc JSON/YAML.
6. Xem các giá trị được cung cấp từ `gradle.properties`, `-P` hoặc input task; xác định có khai báo `inputs.property` cho dữ liệu ngoài nguồn file chưa.
7. Chạy lại task với logging thích hợp, kiểm tra nội dung text output hoặc hash binary. Dùng `--rerun-tasks` **chỉ để chẩn đoán**, không thay thế việc khai báo inputs.
8. Xác minh JAR/ZIP cuối cùng, không dừng ở việc thấy file nguồn đúng. Với output chứa dữ liệu cấu hình nhạy cảm, rà soát artifact đã đóng gói trước khi publish.

Lệnh kiểm tra cơ bản cho project Java:

```bash
./gradlew processResources --info
./gradlew jar
```

Trên PowerShell:

```powershell
.\gradlew.bat processResources --info
.\gradlew.bat jar
```

Các lệnh này giả định project có Java plugin và Gradle Wrapper. `--info` chỉ cung cấp thông tin chẩn đoán bổ sung; phải đối chiếu nội dung các file output để kết luận bytes hoặc placeholders đã được xử lý đúng.

## 16. Câu hỏi tự kiểm tra

**Câu 1.** `filesMatching("**/*.properties") { expand(...) }` có loại PNG khỏi `processResources` không?

**Đáp:** Không. Nó chỉ áp dụng hành động expand lên file khớp; PNG vẫn được copy nếu không bị loại bằng include/exclude hoặc cơ chế khác.

**Câu 2.** Tại sao không gọi `expand(mapOf(...))` ở cấp toàn bộ `processResources` khi resources chứa PNG?

**Đáp:** Vì expand là **bộ lọc văn bản**, có thể làm thay bytes của binary. Hãy khoanh vào file template đã biết, ví dụ `filesMatching("config/build-info.properties")`.

**Câu 3.** File Spring có `${SERVICE_URL}` nhưng Gradle chỉ cần thay version. Cách an toàn hơn là gì?

**Đáp:** Tách build-info template riêng, hoặc dùng token `@BUILD_VERSION@` với literal replacement. Tránh cho Groovy template engine diễn giải placeholder runtime.

**Câu 4.** Khác nhau giữa `include("**/*.txt")` và `filesMatching("**/*.txt") { filter(...) }`?

**Đáp:** `include` quyết định **file nào được copy**; `filesMatching` quyết định **file nào nhận thao tác biến đổi**. Những file không khớp `filesMatching` vẫn được copy trừ khi bị loại riêng.

**Câu 5.** Nếu `targetEnv` từ `-PtargetEnv` thay đổi nhưng tài nguyên không được xử lý lại, cần kiểm tra điều gì?

**Đáp:** `targetEnv` có được khai báo làm task input hay chưa, cách dùng providers/configuration, trạng thái up-to-date và output. Đừng chỉ gắn `--rerun-tasks` cố định.

**Câu 6.** `filteringCharset = "UTF-8"` có nghĩa mọi PNG sẽ được chuyển sang UTF-8?

**Đáp:** Không. Thuộc tính chi phối các **bước content filtering**. PNG không nên qua filter; khi copy nguyên trạng, bytes PNG cần được giữ nguyên.

**Câu 7.** `escapeBackslash.set(true)` có bảo đảm tài nguyên nhị phân an toàn qua `expand`?

**Đáp:** Không. Nó chỉ điều khiển việc chuyển đổi các escape sequences trong Groovy template engine, không thay đổi bản chất text-only của expand.

**Câu 8.** Vì sao không nên đưa password vào `build-info.properties` bằng `expand`, dù password đến từ biến môi trường?

**Đáp:** Vì file đã expand có thể được đóng gói vào JAR/ZIP và phân phối tới người khác. Secret nên được cấp bởi runtime/secret manager, không nằm trong artifact công khai.

**Câu 9.** Làm sao kiểm tra logo PNG sau `processResources` không bị sửa?

**Đáp:** So SHA-256 của PNG nguồn và PNG trong thư mục processed resources; nếu cần xác minh JAR, trích đúng entry rồi so bytes.

**Câu 10.** Vì sao `ReplaceTokens` từ tutorial cũ có thể không build được khi nâng lên Gradle 10?

**Đáp:** Vì Ant classes không còn được mặc định cung cấp trên build script classpath. Cần thêm Ant phù hợp vào build logic hoặc dùng biến đổi từng dòng bằng `filter` không phụ thuộc Ant.

## 17. Tài liệu chính thức

- [Gradle — Working with Files](https://docs.gradle.org/current/userguide/working_with_files.html): `CopySpec`, `include`/`exclude`, copy specs phân cấp, `expand`, `filter`, charset, Copy/Sync và giới hạn với Ant filters.
- [Gradle — ProcessResources API](https://docs.gradle.org/current/dsl/org.gradle.language.jvm.tasks.ProcessResources.html): task xử lý resources của JVM projects, phương thức `filesMatching`, `filter`, `expand`.
- [Gradle — Copy API](https://docs.gradle.org/current/dsl/org.gradle.api.tasks.Copy.html): copy spec, rename, filtering, duplicates strategy.
- [Gradle — ContentFilterable API](https://docs.gradle.org/current/javadoc/org/gradle/api/file/ContentFilterable.html): cách `expand` đánh giá Groovy templates và `filter` hoạt động theo từng dòng.
- [Gradle — ExpandDetails API](https://docs.gradle.org/current/javadoc/org/gradle/api/file/ExpandDetails.html): `escapeBackslash` và cách xử lý escape sequences.
- [Gradle — Java Plugin](https://docs.gradle.org/current/userguide/java_plugin.html): Java source sets, `processResources`, `processTestResources`, `jar`.
- [Gradle — Task Input/Output Validation](https://docs.gradle.org/current/userguide/validation_problems.html): cách khai báo và kiểm tra các đầu vào/đầu ra task.
