# Thứ tự ưu tiên và xử lý thuộc tính trùng tên trong Gradle

Một dự án Gradle có thể khai báo cùng tên `buildMode` trong file `gradle.properties`, biến môi trường của máy chạy, tham số `-P`, system property `-D`, và cả `ext` trong `build.gradle`. Khi kết quả build thay đổi giữa máy cá nhân và CI, câu hỏi cần giải đáp là: **giá trị nào thật sự được Gradle đọc, lấy từ đâu, và vì sao?**

Điều khó là Gradle có **nhiều họ thuộc tính khác nhau**, với cơ chế tra cứu và thứ tự ưu tiên riêng. Không có một bảng “`-P` luôn cao hơn mọi thứ, rồi đến `-D`, rồi đến môi trường” áp dụng cho tất cả đối tượng.

Bài học này giúp bạn:

1. Phân biệt **project properties**, **Gradle properties**, **JVM system properties**, **environment variables**, thuộc tính của **Project/task/extension** và biến cục bộ Groovy/Kotlin DSL.
2. Nhớ đúng thứ tự nguồn của `providers.gradleProperty("key")` và thứ tự giữa các file `gradle.properties`.
3. Giải thích tại sao `project.findProperty("key")` có thể khác `providers.gradleProperty("key")` dù cùng một tên.
4. Điều tra và sửa trường hợp giá trị bị ghi đè hoặc trùng tên; tránh làm thay đổi cấu hình của cả nhóm chỉ để sửa một máy.
5. Thực hành bằng ví dụ Gradle Wrapper với Groovy DSL, có kết quả đầu ra cụ thể.

Phần cú pháp dưới đây dùng `build.gradle` (Groovy DSL). Với Kotlin DSL `build.gradle.kts`, nguyên tắc nguồn vẫn tương ứng nhưng cú pháp truy cập API khác. Tên phiên bản và chính sách được nêu theo tài liệu Gradle hiện hành; khi bảo trì dự án thật, luôn kiểm tra phiên bản bằng `./gradlew --version` và tra tài liệu phù hợp với Gradle Wrapper đó.

## 1. Tách đúng các loại thuộc tính trước khi hỏi “ai thắng?”

| Loại / đối tượng | Ví dụ nguồn thiết lập | Cách đọc phù hợp | Dùng để làm gì? |
| --- | --- | --- | --- |
| **Project property từ môi trường build** | `-PbuildMode=release`, `ORG_GRADLE_PROJECT_buildMode`, `buildMode=dev` trong `gradle.properties` | `providers.gradleProperty('buildMode')` | Giá trị tham số hóa build, cấu hình plugin/task. |
| **Gradle property** | `org.gradle.caching=true`, `org.gradle.parallel=true` | Gradle tự áp dụng; thường đặt ở `gradle.properties` hoặc `-Dorg.gradle.*` | Điều khiển cơ chế của Gradle. |
| **JVM system property** | `-Dapp.region=local`, `systemProp.app.region=local` | `providers.systemProperty('app.region')`; đôi khi `System.getProperty` | Thuộc tính JVM chạy Gradle. |
| **Environment variable** | `JAVA_HOME`, `BUILD_MODE`, `ORG_GRADLE_PROJECT_buildMode` | `providers.environmentVariable('BUILD_MODE')` cho biến thô; `providers.gradleProperty('buildMode')` cho biến có tiền tố đặc biệt | Thông tin do hệ điều hành/CI cung cấp. |
| **Thuộc tính sẵn có của Project** | `project.version`, `project.group`, `project.name` | `project.version`, `project.property('version')` | Trạng thái mô hình Project trong Gradle. |
| **Extra property của Project** | `project.ext.set('buildMode', 'preview')` | `project.extensions.extraProperties.get('buildMode')` hoặc dynamic lookup | Giá trị được thêm động vào đối tượng Project. |
| **Biến local trong script** | `def buildMode = 'local'` | Tên biến `buildMode` trong phạm vi local | Tính toán nội bộ của Groovy script; không tự thành Project property. |

Phải xác định **API đọc** trước khi quyết định giá trị. Chẳng hạn, `providers.environmentVariable('buildMode')` đọc đúng biến môi trường tên `buildMode`; nó không tự tìm `-PbuildMode`. Ngược lại, `providers.gradleProperty('buildMode')` tra cứu những nguồn **project property** mà Gradle quy định; nó không đọc mọi biến môi trường bất kỳ.

Một tên có thể xuất hiện ở nhiều tầng mà **không có xung đột trực tiếp**, nếu mỗi tầng là một namespace khác. Ví dụ `-Dcolor=blue` tạo system property `color`; `-Pcolor=red` tạo project property `color`. `providers.systemProperty('color')` và `providers.gradleProperty('color')` có thể trả **hai giá trị khác nhau** trong cùng một lần build.

## 2. Nguồn project property: `providers.gradleProperty()` ưu tiên thế nào?

Với một tên thông thường như `buildMode`, khi đọc bằng **`providers.gradleProperty('buildMode')`**, thứ tự từ **cao đến thấp** theo API Provider của Gradle hiện hành:

| Ưu tiên | Nguồn | Ví dụ cùng khóa `buildMode` |
| --- | --- | --- |
| **1** | Tham số project property trên CLI: `-P` hoặc `--project-prop` | `./gradlew showMode -PbuildMode=cli` |
| **2** | JVM system property có tiền tố đặc biệt `org.gradle.project.` | `-Dorg.gradle.project.buildMode=system` |
| **3** | Environment variable có tiền tố `ORG_GRADLE_PROJECT_` | `ORG_GRADLE_PROJECT_buildMode=env` |
| **4** | `gradle.properties` ở **Gradle User Home** (`GRADLE_USER_HOME`) | `buildMode=user-home` |
| **5** | `gradle.properties` ở **thư mục root của build** | `buildMode=root-file` |
| **6** | `gradle.properties` ở **thư mục cài Gradle** (`GRADLE_HOME`, nếu có) | `buildMode=installation` |

Đây là bảng cho **project property của build được đọc qua Provider API**. `providers.gradleProperty()` **không** tìm `gradle.properties` riêng của subproject, `ext` hay thuộc tính được thêm động vào Project. Không áp dụng bảng này máy móc cho `project.findProperty()`, `System.getProperty()` hoặc một thuộc tính Gradle như `org.gradle.caching`.

Ví dụ, nếu cùng lúc có:

```properties
# gradle.properties ở root build
buildMode=root-file
```

Và chạy:

```bash
./gradlew showMode -PbuildMode=cli
```

thì `providers.gradleProperty('buildMode')` đọc **`cli`**. Khi bỏ `-P`, kết quả có thể trở về `root-file` **nếu không có** nguồn ưu tiên cao hơn như `-Dorg.gradle.project.buildMode`, biến `ORG_GRADLE_PROJECT_buildMode` hoặc file User Home.

### 2.1. Vì sao không phải mọi `-D` đều là project property?

So sánh:

```bash
./gradlew showMode -DbuildMode=system
./gradlew showMode -Dorg.gradle.project.buildMode=system
```

- `-DbuildMode=system`: thiết lập **system property JVM** tên `buildMode`; đọc bằng `providers.systemProperty('buildMode')`.
- `-Dorg.gradle.project.buildMode=system`: thiết lập system property có tên được Gradle quy ước để **đưa giá trị vào nguồn project property** `buildMode`; đọc được bằng `providers.gradleProperty('buildMode')`.

Vì thế, nói “`-D` mạnh hơn `-P`” là sai trong ngữ cảnh này: khi hai nguồn cùng cung cấp **project property `buildMode`**, `-PbuildMode` có ưu tiên cao hơn `-Dorg.gradle.project.buildMode`.

### 2.2. Biến môi trường đặc biệt khác biến môi trường thông thường

```bash
export BUILD_MODE=development
export ORG_GRADLE_PROJECT_buildMode=ci
./gradlew showMode
```

- `providers.environmentVariable('BUILD_MODE')` trả giá trị `development` từ biến thô.
- `providers.gradleProperty('buildMode')` có thể lấy `ci`, theo quy tắc `ORG_GRADLE_PROJECT_`.
- `providers.environmentVariable('ORG_GRADLE_PROJECT_buildMode')` trả `ci` nếu bạn chủ động đọc đúng tên đó; nhưng cách đọc project property nên dùng `providers.gradleProperty`.

Các tên biến môi trường có thể phân biệt chữ hoa/chữ thường trên hệ điều hành nhất định; hãy giữ nguyên chính xác phần tên sau `ORG_GRADLE_PROJECT_`. `ORG_GRADLE_PROJECT_buildMode` và `ORG_GRADLE_PROJECT_BUILDMODE` không nên được coi là cùng một khóa trên mọi môi trường.

Lưu ý: việc viết `export` áp dụng cho shell Unix. Với PowerShell, có thể thiết lập phiên làm việc bằng `$env:ORG_GRADLE_PROJECT_buildMode = 'ci'`. Đừng đặt biến chứa giá trị thật nhạy cảm vào ví dụ chụp log hoặc lưu trong lịch sử lệnh.

## 3. Thứ tự của nhiều file `gradle.properties`

Gradle có thể đọc file `gradle.properties` ở nhiều vị trí. Với **thuộc tính cấu hình Gradle** như `org.gradle.parallel`, giữa những file chuẩn này Gradle ưu tiên:

```text
GRADLE_USER_HOME/gradle.properties
             ↓ ưu tiên cao hơn
<build-root>/gradle.properties
             ↓ ưu tiên cao hơn
<GRADLE_HOME>/gradle.properties   (nếu dùng Gradle cài riêng)
```

Nói cách khác, **User Home thắng build root, build root thắng installation** khi cùng một khóa Gradle property có giá trị khác nhau ở các file đó (trừ nguồn CLI có quyền ưu tiên cao hơn).

Ví dụ:

```properties
# <build-root>/gradle.properties
org.gradle.parallel=false
```

```properties
# <GRADLE_USER_HOME>/gradle.properties
org.gradle.parallel=true
```

Trong cấu hình này, giá trị **`true` từ Gradle User Home** được Gradle ưu tiên. Nếu một đồng nghiệp có `true` trong User Home còn bạn không có, cùng một repository có thể build khác nhau về mức độ song song.

**Đừng nhầm `GRADLE_USER_HOME` với `GRADLE_HOME`:**

- `GRADLE_USER_HOME` mặc định là thư mục `.gradle` trong home của người dùng, chứa cấu hình cá nhân, cache, log, wrapper downloads; có thể thay bằng biến môi trường hoặc tham số `-g`.
- `GRADLE_HOME` là thư mục cài bản Gradle độc lập, nếu tồn tại. Khi dùng Wrapper, nhiều dự án không cần quản lý thủ công `GRADLE_HOME`.

### 3.1. Project property trong file của subproject

Với một multi-project build, có thể có `app/gradle.properties` bên cạnh root `gradle.properties`. Không nên mặc định mọi API đều quét toàn bộ file subproject.

- `providers.gradleProperty('buildMode')`: đọc **các nguồn ở cấp build** như bảng mục 2, **không lấy** từ file `gradle.properties` nằm riêng trong subproject `app/`.
- `project.findProperty('buildMode')`: tra cứu **mô hình Project động** và trong những phiên bản Gradle hỗ trợ có thể nhận giá trị gắn với project hiện tại; tài liệu hiện hành phân biệt rõ `gradle.properties` trong current project directory với nguồn cấp build. Cần xác nhận phiên bản và nơi đang gọi API.

Để dữ liệu được truy cập nhất quán ở nhiều subproject, ưu tiên đặt project properties cần chia sẻ ở **root build** hoặc truyền rõ qua convention/plugin API. Nếu muốn một module có cấu hình riêng, cần thiết kế nguồn và API đọc theo scope module đó, thay vì dựa vào may mắn từ thứ tự tra cứu ngầm.

### 3.2. Thuộc tính `systemProp.*` trong multi-project

Khi khai báo JVM system property qua `gradle.properties`, dùng tiền tố **`systemProp.`**:

```properties
# gradle.properties ở build root
systemProp.lesson.region=from-file
```

Gradle dùng giá trị này để đặt system property `lesson.region` cho quá trình Gradle. Trong multi-project build, Gradle **chỉ xét các khai báo `systemProp` ở root project**, không áp dụng `systemProp` khai báo trong file `gradle.properties` của mọi subproject. Đây là điểm dễ sai khi một module được di chuyển từ single-project sang multi-project.

## 4. Gradle property `org.gradle.*`: thứ tự riêng, mục đích riêng

Các khóa như:

```properties
org.gradle.caching=true
org.gradle.parallel=false
org.gradle.jvmargs=-Xmx2g
org.gradle.warning.mode=all
```

được Gradle nhận biết như **cấu hình của build tool**. Thông thường bạn đặt chúng ở `gradle.properties` ở root để nhóm chia sẻ, hoặc ở User Home cho lựa chọn cá nhân. Có thể dùng các CLI option tương ứng, ví dụ `--build-cache` / `--no-build-cache` cho build cache, hoặc dùng `-D` đối với khóa Gradle property như:

```bash
./gradlew build -Dorg.gradle.caching=false
```

Với thuộc tính Gradle được hỗ trợ theo cơ chế này, `-Dorg.gradle.caching=false` có ưu tiên cao hơn các file `gradle.properties`. Với một tùy chọn CLI có cờ trực tiếp, cờ đó điều khiển hành vi theo quy tắc CLI của Gradle.

**`-Porg.gradle.caching=false` không phải cách tương đương** để bật/tắt build cache. `-P` khai báo một **project property** có tên `org.gradle.caching`; nó không được hiểu là cờ thiết lập Gradle property theo cùng cơ chế `-Dorg.gradle.caching=false`.

Đừng nhầm `org.gradle.jvmargs` (cấu hình JVM/daemon thực thi Gradle) với `java.toolchain.languageVersion` (JDK dùng cho task Java) hoặc `JAVA_HOME` (đường dẫn JDK do môi trường cung cấp). Chúng liên quan môi trường Java nhưng không tạo thành một “cùng khóa, ai thắng” đơn giản.

**Gợi ý thực hành:** đặt cấu hình build được dùng chung, ổn định trong root `gradle.properties` có quản lý phiên bản. Dùng CLI cho kiểm tra ngắn hạn; tránh phụ thuộc vào tham số mà đồng nghiệp/CI dễ quên. Khi kết quả giữa máy khác nhau, kiểm tra `GRADLE_USER_HOME/gradle.properties` trước khi sửa cấu hình chung.

## 5. System property: `-D` và `systemProp.*` khác project property

JVM system property có namespace của JVM chạy Gradle, ví dụ `service.region`:

```properties
# root gradle.properties
systemProp.service.region=local
```

Có thể ghi đè cho một lần chạy Gradle:

```bash
./gradlew showSystem -Dservice.region=temporary
```

Theo cơ chế system property của Gradle, giá trị `-Dservice.region` trên CLI có ưu tiên hơn khai báo `systemProp.service.region` từ file tương ứng. Đọc đúng bằng:

```groovy
def region = providers.systemProperty('service.region')
```

Đối với biến hệ điều hành:

```groovy
def regionFromEnv = providers.environmentVariable('SERVICE_REGION')
```

Hai Provider có thể trả các giá trị khác nhau: `SERVICE_REGION` **không tự ghi đè** system property JVM `service.region`. Nếu muốn có logic “CLI hoặc system property trước, rồi environment variable”, bạn phải **thiết kế chính sách fallback rõ ràng**:

```groovy
def effectiveRegion = providers.systemProperty('service.region')
    .orElse(providers.environmentVariable('SERVICE_REGION'))
    .orElse('local')
```

Đây là **quy tắc do bạn viết** trong build script, không phải một thứ tự mặc định Gradle tự áp dụng giữa hai tên `service.region` và `SERVICE_REGION`.

### 5.1. JVM chạy Gradle và JVM chạy ứng dụng Java khác nhau

Giả sử bạn có lớp Java 17:

```java
// src/main/java/demo/ShowRegion.java
package demo;

public final class ShowRegion {
    public static void main(String[] args) {
        System.out.println(System.getProperty("service.region", "missing"));
    }
}
```

Biên dịch và chạy trực tiếp bằng JDK 17+:

```bash
mkdir -p out
javac -d out src/main/java/demo/ShowRegion.java
java -cp out -Dservice.region=from-app demo.ShowRegion
```

Đầu ra chính xác:

```text
from-app
```

`-Dservice.region=from-app` ở **lệnh `java`** là system property của JVM chạy ứng dụng. Trong khi đó `./gradlew -Dservice.region=from-gradle ...` đặt property ở **quá trình Gradle**; các JVM con của task `JavaExec`, `Test` hoặc ứng dụng được fork **không mặc nhiên nhận mọi `-D` của Gradle**. Muốn chuyển giá trị sang ứng dụng/test, hãy cấu hình `systemProperty` trên task tương ứng, hoặc truyền rõ qua cách mà ứng dụng nhận cấu hình.

Ví dụ minh họa phần cấu hình này trong một build Groovy đã áp dụng plugin `application` và đặt `mainClass`:

```groovy
def regionValue = providers.systemProperty('service.region').orElse('local')

tasks.named('run', JavaExec) {
    systemProperty 'service.region', regionValue.get()
}
```

Đoạn trên **chỉ là mảnh cấu hình** cho task `run` đã có; không phải file `build.gradle` chạy độc lập. Hợp đồng với ứng dụng vẫn là system property `service.region` truyền cho JVM chạy `ShowRegion`. Nếu không khai báo cách truyền, dựa vào `-D` của Gradle để cấu hình ứng dụng có thể dẫn đến kết quả bất ngờ.

## 6. Thực hành số 1: quan sát giá trị nào thắng trong một project

Tạo thư mục riêng:

```text
priority-lab/
├── settings.gradle
├── build.gradle
├── gradle.properties
├── gradlew
├── gradlew.bat
└── gradle/wrapper/
    ├── gradle-wrapper.jar
    └── gradle-wrapper.properties
```

Ví dụ giả định đã có Gradle Wrapper được tạo bằng một phiên bản Gradle phù hợp, với `java`/JDK khả dụng để chạy Gradle. Nếu chưa có Wrapper, trên máy có sẵn Gradle tương thích, tại root chạy `gradle wrapper --gradle-version 8.5`, rồi lưu đủ bốn file Wrapper được tạo. Mục tiêu ở đây là quan sát project properties nên chưa cần thêm mã nguồn Java.

**`settings.gradle`:**

```groovy
rootProject.name = 'priority-lab'
```

**`gradle.properties`:**

```properties
buildMode=from-root-file
systemProp.lesson.region=from-root-systemprop
```

**`build.gradle`:**

```groovy
def projectMode = providers.gradleProperty('buildMode').orElse('not-set')
def jvmRegion = providers.systemProperty('lesson.region').orElse('not-set')

tasks.register('showValues') {
    group = 'learning'
    description = 'Show project and JVM system properties'

    doLast {
        println 'projectMode=' + projectMode.get()
        println 'jvmRegion=' + jvmRegion.get()
    }
}
```

Khi chạy từ root, trên Linux/macOS:

```bash
./gradlew -q showValues
```

Nếu **không có** nguồn `buildMode`/ `lesson.region` ưu tiên cao hơn trong môi trường và User Home, kết quả chính xác là:

```text
projectMode=from-root-file
jvmRegion=from-root-systemprop
```

Trên Windows có thể chạy `gradlew.bat -q showValues`. `-q` chỉ giảm log Gradle, không thay thứ tự ưu tiên.

### 6.1. Ghi đè project property bằng `-P`

```bash
./gradlew -q showValues -PbuildMode=from-cli
```

Giữ nguyên file root, nếu không có xung đột khác với tên cần thử, output là:

```text
projectMode=from-cli
jvmRegion=from-root-systemprop
```

Bạn thấy `-P` làm thay đổi **projectMode**; `jvmRegion` độc lập vì nó là system property khác tên.

### 6.2. Dùng tiền tố system property dành cho project property

```bash
./gradlew -q showValues -Dorg.gradle.project.buildMode=from-system
```

Với các điều kiện nguồn ưu tiên khác giống ban đầu, kết quả:

```text
projectMode=from-system
jvmRegion=from-root-systemprop
```

Nếu truyền **cả hai**:

```bash
./gradlew -q showValues -PbuildMode=from-cli -Dorg.gradle.project.buildMode=from-system
```

kết quả của dòng `projectMode` là:

```text
projectMode=from-cli
```

Lý do: `-PbuildMode` đứng trước nguồn `-Dorg.gradle.project.buildMode` trong bảng ưu tiên của **project property**.

### 6.3. Ghi đè system property độc lập

```bash
./gradlew -q showValues -Dlesson.region=from-cli-system
```

Nếu project property vẫn lấy từ root file, output:

```text
projectMode=from-root-file
jvmRegion=from-cli-system
```

Lưu ý tên `-Dlesson.region` ở đây **không có** tiền tố `org.gradle.project.`, nên nó **không ghi đè** `buildMode`.

### 6.4. Thử biến môi trường của project property

Trên Linux/macOS, dùng biến chỉ cho đúng một invocation:

```bash
ORG_GRADLE_PROJECT_buildMode=from-env ./gradlew -q showValues
```

Theo thứ tự tra cứu `providers.gradleProperty` của Gradle hiện hành, nếu không có `-P` hoặc `-Dorg.gradle.project.buildMode` và không có nguồn trùng có ưu tiên cao hơn, bạn sẽ thấy:

```text
projectMode=from-env
jvmRegion=from-root-systemprop
```

Trên PowerShell, có thể thiết lập trong phiên terminal rồi xóa sau khi thử:

```powershell
$env:ORG_GRADLE_PROJECT_buildMode = 'from-env'
.\gradlew.bat -q showValues
Remove-Item Env:ORG_GRADLE_PROJECT_buildMode
```

**Đừng để biến thử nghiệm tồn tại trong mọi lần chạy sau** rồi kết luận root `gradle.properties` “không hoạt động”. Khi tên trùng, biến môi trường đặc biệt có thể là nguồn đang chi phối. Để lặp lại thí nghiệm, loại những nguồn ngoài phạm vi đang kiểm tra hoặc dùng Gradle User Home riêng cho phòng lab; không xóa bừa cấu hình thật của người dùng.

## 7. Thực hành số 2: hai file `gradle.properties` trùng tên

Trong lab trên, root có:

```properties
buildMode=from-root-file
```

Bạn có thể tạo một **Gradle User Home riêng cho thử nghiệm** trong cùng thư mục, ví dụ `lab-user-home/gradle.properties`:

```properties
buildMode=from-user-home
```

Trên Linux/macOS, gọi:

```bash
./gradlew -g ./lab-user-home -q showValues
```

Trong môi trường không có `-P`, `-Dorg.gradle.project.buildMode`, `ORG_GRADLE_PROJECT_buildMode`, nguồn project property theo file User Home thắng root file; dòng tương ứng dự kiến:

```text
projectMode=from-user-home
```

Có thể có thêm log/việc tải Gradle theo môi trường Wrapper và Gradle User Home mới; ví dụ chỉ cố định **dòng mà task in**.

Thêm `-PbuildMode=from-cli` vào cùng lệnh sẽ làm giá trị trở thành `from-cli`, cho thấy CLI project property có ưu tiên cao hơn file User Home. Nhờ dùng `-g`, bạn có thể kiểm chứng quy tắc mà không sửa `~/.gradle/gradle.properties` đang dùng thật.

Đối với một khóa Gradle property như `org.gradle.parallel`, có thể thử cùng quy luật User Home > root. Để **quan sát** đúng hiệu ứng của `org.gradle.parallel`, cần một build multi-project có task phù hợp; đừng chỉ dựa vào số dòng log một lần chạy nhỏ để kết luận parallelism đã thực sự phát huy hiệu quả.

## 8. Vì sao `project.findProperty()` có thể khác `providers.gradleProperty()`?

Đây là trường hợp trùng tên **cấp mô hình Project**, khác với hai file cùng khai báo một property.

`providers.gradleProperty('key')` là API đọc **nguồn property ở cấp build**, trả về một `Provider<String>` và hỗ trợ mô hình cấu hình lazy. Nó không tra cứu extra properties và extension được thêm vào Project.

Trong khi đó, `project.findProperty('key')`, `project.property('key')` và `project.hasProperty('key')` tra cứu **mô hình Project động**. Theo tài liệu Gradle hiện hành, trong phạm vi Project hiện tại, thứ tự có thể gồm:

1. **Thuộc tính sẵn có/cấu hình trực tiếp trên Project**, như `version`, `group`, `description`.
2. **Extra properties** của chính Project.
3. **Extension** có tên được hỏi.
4. **Task** có tên được hỏi.
5. Trong các phiên bản còn hỗ trợ, extra properties/extension của các **Project cha**, từ gần đến root.

Trong Gradle 9.6, tra cứu ngầm lên Project cha thuộc diện deprecated, và tài liệu hướng tới loại bỏ ở Gradle 10. Điều này là lý do nên truy cập cross-project bằng API tường minh như `rootProject.ext.foo` hoặc thiết kế convention riêng; với dự án dùng Gradle 8.x, hãy đối chiếu chính sách phiên bản khi nâng cấp.

Ngoài thứ tự các đối tượng mô hình, **những project properties từ Gradle sources** còn được đưa vào extra properties hoặc thuộc tính Project phù hợp. Một `ext.set('key', value)` **gán tường minh** có thể che giá trị từ `-P` khi bạn đọc qua dynamic lookup. Vì thế không được nói `-P` luôn là giá trị cuối của `findProperty` nếu build script đã ghi đè vào Project bằng API khác.

### 8.1. Ví dụ có hai kết quả khác nhau nhưng cả hai đều đúng

Giả sử root `gradle.properties`:

```properties
buildMode=from-file
```

Và đoạn sau trong `build.gradle` (dùng để quan sát khi cấu hình):

```groovy
def inputMode = providers.gradleProperty('buildMode')

// Ghi tường minh một extra property cùng tên vào Project.
project.extensions.extraProperties.set('buildMode', 'from-extra')

println 'provider=' + inputMode.getOrElse('missing')
println 'dynamic=' + project.findProperty('buildMode')
```

Chạy `./gradlew help -q`, nếu không có nguồn ưu tiên cao hơn `buildMode`:

```text
provider=from-file
dynamic=from-extra
```

Giải thích:

- **`provider`** vẫn lấy từ build-level project property được khai báo trong file.
- **`dynamic`** thấy extra property đã được gán tường minh trên Project.

Ngay cả nếu có `-PbuildMode=from-cli`, Provider có thể đọc `from-cli` còn `findProperty` vẫn thấy `from-extra` sau khi script gán `ext`. Đây không phải lỗi Gradle “quên ưu tiên `-P`”; bạn đang dùng **hai API với phạm vi tra cứu khác nhau**.

Ví dụ dùng `println` ở top level chỉ để minh họa trong lab: nó chạy trong **giai đoạn cấu hình**, kể cả với task `help`. Trong build thực tế, tránh in cấu hình nhạy cảm và tránh side effect ở top level.

### 8.2. Biến local có thể che tên khác khi viết DSL

```groovy
def buildMode = 'local-value'
```

Đây là **local variable** trong script Groovy, không tự thêm `buildMode` vào `Project` hay `providers.gradleProperty`. Ở nơi lexical scope thấy local này, viết `buildMode` có thể trả `local-value` dù Gradle project property cùng tên có giá trị `from-file`.

Cách so sánh rõ ràng là:

```groovy
def buildMode = 'local-value'
def externalMode = providers.gradleProperty('buildMode').getOrElse('missing')

println 'local=' + buildMode
println 'external=' + externalMode
```

Trong lab có `buildMode=from-file` và không có override khác:

```text
local=local-value
external=from-file
```

Để tránh nhầm, đặt tên local diễn đạt rõ như `effectiveMode`, `configuredMode`, `modeProvider`; khi muốn kiểm tra nguồn cụ thể, luôn dùng API có ghi tên nguồn thay vì tên không qualify.

## 9. Phương thức đọc, fallback và lỗi khi khóa không tồn tại

| API | Nguồn tra cứu | Khi không có khóa | Khi nên dùng |
| --- | --- | --- | --- |
| `providers.gradleProperty('key')` | Project property **cấp build** từ `-P`, `-Dorg.gradle.project.*`, env đặc biệt và file chuẩn | Provider **không có giá trị**; `.get()` sẽ lỗi khi gọi | Cấu hình đầu vào build, laziness, tích hợp task inputs. |
| `providers.systemProperty('key')` | JVM system property | Provider không có giá trị | Cấu hình JVM Gradle cần đọc. |
| `providers.environmentVariable('KEY')` | Biến môi trường nguyên tên | Provider không có giá trị | Cấu hình ngoài, CI; không giả định mapping thành project property. |
| `project.findProperty('key')` | Dynamic Project lookup, gồm ext/extension/task/ancestor theo phiên bản | Trả `null` | Phải đọc mô hình Project động. |
| `project.property('key')` | Cùng phạm vi dynamic lookup | Báo lỗi nếu không có thuộc tính | Thuộc tính bắt buộc theo hợp đồng. |
| `project.hasProperty('key')` | Cùng phạm vi dynamic lookup | Trả `false` | Kiểm tra tồn tại, không tự giải quyết xung đột. |
| `project.extensions.extraProperties.has('key')` | Extra properties **của Project được chỉ rõ** | Trả `false` | Kiểm tra đúng scope của `ext`. |

Có thể sử dụng fallback **tường minh**:

```groovy
def mode = providers.gradleProperty('buildMode').orElse('development')
```

`orElse('development')` chỉ dùng giá trị thay thế **khi Provider không có giá trị**; nó **không ghi lại** vào file và không làm xuất hiện `buildMode` trong mọi API lookup. Nếu property được cung cấp là chuỗi rỗng, bạn cần tự định nghĩa chính sách chấp nhận hay bác bỏ chuỗi rỗng; đừng mặc định Provider coi nó như “không có”.

Đối với thiết lập bắt buộc, có thể cố ý yêu cầu giá trị bằng `.get()` tại thời điểm thích hợp, hoặc cấu hình validation task rõ ràng. Tuy nhiên đừng gọi `.get()` ở top level quá sớm khi giá trị cần được cấu hình sau đó hoặc khi muốn giữ cấu hình lazy.

### 9.1. Phân biệt fallback với thứ tự ưu tiên mặc định

Ví dụ:

```groovy
def apiBaseUrl = providers.gradleProperty('apiBaseUrl')
    .orElse(providers.environmentVariable('API_BASE_URL'))
    .orElse('http://localhost:8080')
```

Đây là chính sách riêng mà **bạn** thiết kế: dùng Gradle project property nếu hiện diện, nếu không thì biến thô `API_BASE_URL`, cuối cùng là URL mặc định. Nó **không chứng minh** biến `API_BASE_URL` có vị trí trong thứ tự ưu tiên của `providers.gradleProperty('apiBaseUrl')`.

Cách này tốt hơn việc gọi `System.getenv()` hoặc dùng `findProperty()` rải rác trong nhiều task khiến mỗi nơi có chính sách khác nhau.

## 10. Xung đột tên với thuộc tính sẵn có, task và extension

Một số tên như `name`, `version`, `group`, `description` đã có nghĩa trong mô hình Project. Các plugin cũng có thể thêm extension như `java`, `application`, hoặc task tên `test`, `build`, `jar`.

Hãy cân nhắc khác nhau giữa:

```groovy
project.version
providers.gradleProperty('version')
project.findProperty('version')
```

`project.version` là property của Project. `providers.gradleProperty('version')` tra cứu **nguồn project property cấp build** tên `version`; hai API có thể nhìn thấy các giá trị đã được áp dụng theo đường khác nhau. `project.findProperty('version')` ưu tiên property của chính Project theo dynamic lookup. Nếu cần một biến tùy biến cho quy trình phát hành, đặt tên rõ như `releaseVersion` thay vì vô tình ghi đè `version` hoặc thêm extension `version`.

Tương tự, task `test` và project property `test` là hai thực thể khác nhau; không nên đặt cùng một tên chỉ để giảm chữ. Nếu cần tham chiếu task, gọi `tasks.named('test')` thay vì suy luận giá trị từ `project.findProperty('test')`.

Một nguyên tắc hữu ích trong multi-project:

```groovy
// Rõ ràng tên và nơi sở hữu property:
rootProject.extensions.extraProperties.get('releaseChannel')
project.extensions.extraProperties.get('moduleChannel')
```

Hai phép đọc chỉ hợp lệ khi key thực sự được khai báo trên đối tượng tương ứng. Chúng **không phải** là phương pháp đồng bộ property giữa root và tất cả subproject; bạn cần một thiết kế cấu hình/chia sẻ thích hợp.

## 11. Xử lý trùng tên trong cùng một file

Nếu một file `gradle.properties` có hai dòng:

```properties
buildMode=dev
buildMode=release
```

thì bản thân file đã mơ hồ với người bảo trì. Trình đọc `.properties` sẽ thu được một giá trị cho cùng khóa theo cơ chế parse, nhưng **đừng lấy việc lặp key làm cơ chế thiết kế thứ tự ưu tiên**. Hãy giữ mỗi khóa xuất hiện **một lần** trong file, rồi dùng `-P`, env hoặc biến thể cấu hình được thiết kế rõ khi cần override.

Tương tự, tránh gọi cùng một CLI option trùng tên nhiều lần để dựa vào “giá trị cuối”. Quy định trong tài liệu và cách parser xử lý lệnh sẽ dễ thay đổi hơn một cấu hình duy nhất. Khi muốn thay giá trị một lần chạy, đặt một override rõ ràng.

Với file được build bằng tool/script tự động, cân nhắc kiểm tra duplicate key trước khi ghi; cách đơn giản là review `gradle.properties` trong code review hoặc dùng công cụ lint phù hợp. Tên khóa có dấu chấm, dấu gạch nối, chữ hoa/chữ thường hoặc ký tự escape có thể được trình đọc properties diễn giải theo quy tắc Java properties; đừng đoán khóa tương đương chỉ từ mắt thường.

## 12. Chẩn đoán “máy tôi ra giá trị khác CI”

Một tình huống thực tế: repository có:

```properties
# Root gradle.properties được commit
buildMode=development
```

Máy của bạn chạy `./gradlew showMode` ra `development`; CI chạy tương tự nhưng ra `release`. Trước khi sửa file root, hãy kiểm tra theo hướng sau:

1. **API nào đã đọc giá trị?** `providers.gradleProperty`, `project.findProperty`, `providers.systemProperty` hay `System.getenv`? Không thể tìm đúng nguồn nếu chưa biết API.
2. **CI có truyền `-PbuildMode=release` không?** Kiểm tra command thực tế trong workflow/job template.
3. **Có `-Dorg.gradle.project.buildMode=release` không?** Không nhầm với `-DbuildMode`.
4. **Có `ORG_GRADLE_PROJECT_buildMode` không?** Xem cấu hình biến môi trường của pipeline, runner hoặc secret injection.
5. **`GRADLE_USER_HOME` trỏ tới đâu?** Một runner có thể dùng User Home khác với máy cá nhân; file `gradle.properties` trong đó có thể ghi đè root file.
6. **Có script/plugin gán `ext.buildMode` không?** Nếu code đọc qua `findProperty`, extra property có thể che nguồn project property.
7. **Có subproject context khác nhau không?** Trong multi-project, nơi gọi dynamic lookup và parent/child property có thể làm giá trị đổi.
8. **Đã so đúng Gradle Wrapper và daemon/JVM chưa?** Nên chạy `./gradlew --version` và dùng Wrapper trong cả local lẫn CI để thống nhất cách xử lý cấu hình.

Để điều tra an toàn, in **tên nguồn** và trạng thái “có/không” trước. Chỉ in giá trị khi biết chắc không chứa secret. Với property nhạy cảm, có thể log `present=true` và một nhãn môi trường chung mà không ghi trực tiếp token/password.

### 12.1. Một task hỗ trợ kiểm tra sự hiện diện

Trong một project Groovy DSL có thể tạo:

```groovy
def propertyInput = providers.gradleProperty('buildMode')
def environmentInput = providers.environmentVariable('ORG_GRADLE_PROJECT_buildMode')

tasks.register('diagnoseMode') {
    doLast {
        println 'buildMode.present=' + propertyInput.present
        println 'envOverride.present=' + environmentInput.present
    }
}
```

Dòng log này giúp biết một nguồn có được đặt hay không, nhưng `envOverride.present=true` **chưa chứng minh** nó là nguồn cuối khi có `-P` hoặc `-Dorg.gradle.project.*` với ưu tiên cao hơn. Tương tự, `buildMode.present=true` chỉ biết Provider có giá trị, **không truy ngược được** nguồn chính xác đã thắng.

Muốn phân biệt sâu, hãy kiểm tra nguồn được cấp trong CLI, hệ thống quản lý CI và file cấu hình có quyền truy cập. Không nên “debug bằng cách in toàn bộ `System.getenv()` / `System.getProperties()`” vì có thể lộ dữ liệu nhạy cảm trong log.

## 13. Các tình huống xung đột và kết quả cần nhớ

| Tình huống | Giá trị / cách xử lý đúng |
| --- | --- |
| `-PbuildMode=cli` và root file `buildMode=file` | `providers.gradleProperty('buildMode')` chọn `cli`. |
| `-PbuildMode=cli` và `-Dorg.gradle.project.buildMode=sys` | Provider project property chọn `cli`. |
| `-DbuildMode=sys` và root file `buildMode=file` | `providers.systemProperty('buildMode')` thấy `sys`; `providers.gradleProperty('buildMode')` vẫn có thể thấy `file`. |
| Biến thô `BUILD_MODE=env` và root file `buildMode=file` | Không tự cùng một key; dùng `providers.environmentVariable('BUILD_MODE')` nếu muốn biến thô. |
| `ORG_GRADLE_PROJECT_buildMode=env` và root file `buildMode=file` | Theo thứ tự Provider hiện hành, `env` được ưu tiên hơn root file nếu không có `-P`/`-Dorg.gradle.project.*` đứng trước. |
| User Home `buildMode=user` và root `buildMode=file` | Trong cùng nhóm file chuẩn, User Home được ưu tiên hơn root. |
| Root `org.gradle.parallel=false`, User Home `org.gradle.parallel=true` | Gradle property từ User Home được ưu tiên, trừ override CLI cao hơn. |
| Root `systemProp.service.region=local`, CLI `-Dservice.region=ci` | System property đọc bằng `providers.systemProperty('service.region')` có giá trị từ CLI. |
| `ext.set('buildMode','extra')` và root `buildMode=file` | Dynamic lookup `findProperty('buildMode')` có thể thấy `extra`; Provider cấp build vẫn đọc nguồn file. |
| `def buildMode='local'` và `-PbuildMode=ci` | Biến local `buildMode` ở đúng scope vẫn là `local`; Provider cấp build thấy `ci`. |
| `-Porg.gradle.caching=false` | Là một project property mang tên đặc biệt; đừng dùng nó thay `-Dorg.gradle.caching=false` để cấu hình build cache. |
| `project.version` và `providers.gradleProperty('version')` | Phải xác định API và thời điểm gán; không suy ra chúng luôn bằng nhau. |

Các kết quả có điều kiện “không có nguồn ưu tiên cao hơn” để tránh việc một file User Home hoặc runner thay đổi kỳ vọng. **Đúng phạm vi và đúng API** quan trọng hơn học thuộc một sơ đồ ưu tiên tổng quát.

## 14. Quy tắc thiết kế để tránh lỗi trùng tên

**Đặt tên theo mục đích.** Nên dùng `releaseChannel`, `dependencyMirrorUrl`, `runIntegrationTests` thay vì những tên chung như `name`, `version`, `test` vốn dễ trùng Project/task/extension. Nếu cần dùng `version` của Project, truy cập `project.version` rõ ràng.

**Chọn một nguồn mặc định cho cả nhóm.** Đặt giá trị không nhạy cảm, được chia sẻ vào root `gradle.properties` hoặc convention plugin. Hạn chế cấu hình khác nhau không được ghi nhận giữa máy.

**Chọn một đường override được tài liệu hóa.** Với một tham số thay đổi theo job, `-P` hoặc env có tiền tố đặc biệt là những cơ chế rõ. Nếu chọn env cho CI, ghi chính xác tên `ORG_GRADLE_PROJECT_...` trong hướng dẫn triển khai và quản lý secret bằng tính năng bảo mật của nền tảng CI.

**Dùng Provider API cho input môi trường build.** `providers.gradleProperty`, `providers.environmentVariable` và `providers.systemProperty` hỗ trợ đọc lazy và tích hợp với cách Gradle theo dõi cấu hình. Dùng `findProperty` khi thật sự cần mô hình động của Project.

**Khai báo fallback tại một nơi.** Một `Provider` có `orElse` rõ ràng tốt hơn nhiều đoạn `System.getenv() ?: project.findProperty()` được sao chép với thứ tự khác nhau. Tránh vô ý dùng hai “nguồn truth” cho một quyết định.

**Không ghi đè input bằng `ext` tùy tiện.** Nếu đã công bố `-PbuildMode` là đầu vào của build, việc thêm `project.ext.buildMode = ...` rồi dùng `findProperty` có thể làm kết quả bất ngờ. Nếu cần giá trị sau xử lý, đặt tên khác như `effectiveBuildMode`.

**Không commit secret vào root `gradle.properties`.** File User Home cũng là plaintext nên cần bảo vệ quyền truy cập. Với CI, dùng secret store và injection phù hợp; không log trực tiếp credentials. “Có thứ tự ưu tiên đúng” không có nghĩa là “đã an toàn để ghi mật khẩu ra console”.

**Nhớ sự khác nhau giữa Gradle JVM và app JVM.** Một `-D` trên `gradlew` không bảo đảm mọi JavaExec/Test nhận nó. Nếu app/test cần property, cấu hình truyền rõ từ Provider sang task đúng loại.

**Đối chiếu phiên bản khi nâng Gradle.** Nguồn Provider API tương đối ổn định, nhưng các hành vi dynamic lookup, parent project và API tiện ích có lộ trình deprecation. Dùng Wrapper và kiểm tra [tài liệu build environment theo phiên bản](https://docs.gradle.org/current/userguide/build_environment.html) để tránh nhầm hướng dẫn mới với Gradle cũ.

## 15. Bài tập tự kiểm tra

**1.** Root `gradle.properties` có `buildMode=dev`; chạy `./gradlew help -PbuildMode=release`. `providers.gradleProperty('buildMode')` cho gì?

**Đáp án:** `release`, do nguồn `-P` đứng trước file.

**2.** Có đồng thời `-DbuildMode=one` và `-PbuildMode=two`. Cùng một tên, liệu `providers.systemProperty('buildMode')` và `providers.gradleProperty('buildMode')` có phải trả cùng giá trị?

**Đáp án:** Không. Một API trả `one` từ JVM system property, API kia trả `two` từ Gradle project property.

**3.** Vì sao `-Dorg.gradle.project.buildMode=system` khác `-DbuildMode=system`?

**Đáp án:** Tiền tố `org.gradle.project.` là quy ước Gradle để map system property sang **project property**; `-DbuildMode` thông thường chỉ là system property JVM.

**4.** User Home có `org.gradle.parallel=true`, root có `org.gradle.parallel=false`. Nếu không có CLI override, Gradle dùng gì?

**Đáp án:** `true` từ User Home vì file User Home ưu tiên cao hơn root cho Gradle property.

**5.** Root file có `buildMode=file`, còn script gọi `ext.set('buildMode', 'extra')`. Có thể có một API đọc `file` và API khác đọc `extra` không?

**Đáp án:** Có. `providers.gradleProperty('buildMode')` chỉ xem nguồn project property của build; `project.findProperty('buildMode')` tra cứu mô hình Project động, nơi `ext` được gán tường minh.

**6.** `ORG_GRADLE_PROJECT_buildMode=ci` và `BUILD_MODE=local` có phải hai cách viết của cùng tên biến môi trường không?

**Đáp án:** Không. Biến có tiền tố đặc biệt cung cấp project property `buildMode`; biến `BUILD_MODE` thô chỉ được dùng khi code chủ động đọc nó.

**7.** Thêm `systemProp.service.region=ci` vào `app/gradle.properties` của một multi-project build có chắc được Gradle áp dụng không?

**Đáp án:** Không. Với cơ chế `systemProp` từ file `gradle.properties`, chỉ root project được Gradle xét trong multi-project build.

**8.** Vì sao `System.getProperty('buildMode')` không phải lựa chọn tốt để đọc giá trị truyền bằng `-PbuildMode=release`?

**Đáp án:** `-P` cung cấp Gradle project property; system property là namespace khác. Dùng `providers.gradleProperty('buildMode')`.

**9.** Tại sao log `BUILD SUCCESSFUL` không chứng minh giá trị cấu hình giống máy CI?

**Đáp án:** Build có thể thành công với nhiều giá trị khác nhau. Cần so command, env, User Home, project source, API lookup và các override dynamic.

**10.** Một task cần giá trị mặc định `development` nhưng cho phép `-PbuildMode=release`. Cách đọc rõ là gì?

**Đáp án:** `providers.gradleProperty('buildMode').orElse('development')`, sau đó gắn kết quả vào cấu hình/task phù hợp.

## 16. Nguồn tham khảo

- [Gradle User Manual — Build Environment Configuration](https://docs.gradle.org/current/userguide/build_environment.html): các nguồn và thứ tự ưu tiên, Gradle User Home, `-P`, `-D`, `systemProp.*`, Project API và environment variables.
- [Gradle ProviderFactory API — `gradleProperty`](https://docs.gradle.org/current/javadoc/org/gradle/api/provider/ProviderFactory.html): thứ tự nguồn dành riêng cho `ProviderFactory.gradleProperty` và giới hạn không tra cứu extra/subproject dynamic properties.
- [Gradle Command-Line Interface](https://docs.gradle.org/current/userguide/command_line_interface.html): cú pháp `-P`, `-D`, `-g` và những tùy chọn Gradle liên quan.
- [Gradle — Best Practices](https://docs.gradle.org/current/userguide/best_practices_general.html): cách dùng `gradle.properties` để chia sẻ cấu hình build ổn định.

**Ghi nhớ:** muốn giải quyết trùng tên trong Gradle, hãy hỏi **“thuộc tính thuộc loại nào và đang được đọc bằng API nào?”** trước. `providers.gradleProperty` áp dụng ưu tiên của project property cấp build; `org.gradle.*` có thứ tự riêng; `-D` thông thường là JVM system property; `project.findProperty` còn xét thuộc tính/extra/extension/task của Project. Một khi xác định đúng namespace và nguồn, bạn sẽ biết cách sửa xung đột mà không tạo thêm những override khó kiểm soát.