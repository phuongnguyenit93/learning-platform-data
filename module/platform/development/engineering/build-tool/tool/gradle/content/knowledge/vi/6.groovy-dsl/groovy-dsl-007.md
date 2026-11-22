# Groovy DSL trong Gradle: Extra properties, script plugin và giới hạn của cấu hình động

## 1. Mục tiêu và bức tranh tổng quan

Trong file `build.gradle` dùng **Groovy DSL**, có thể gặp các đoạn như:

~~~groovy
ext {
    libraryVersion = '1.4.0'
}
apply from: "$rootDir/gradle/common.gradle"
~~~

Hai cơ chế này xuất hiện nhiều ở các dự án Gradle lâu năm:

- **Extra properties** (`ext`) gắn những giá trị tự định nghĩa vào một đối tượng Gradle, ví dụ `Project` hoặc `Task`. Nhờ tính động của Groovy, một property đã khai báo qua `ext` còn có thể được đọc trực tiếp trên đối tượng sở hữu.
- **Script plugin** là script Gradle riêng (`.gradle` với Groovy DSL), được nạp bằng `apply from:` để dùng lại một phần cấu hình hoặc đăng ký task.
- **Cấu hình động** cho phép tìm property theo tên khi chạy, thay đổi đối tượng sau khi plugin được áp dụng, và điều khiển cấu hình bằng closure. Nó linh hoạt nhưng có thể gây lỗi khó phát hiện, phụ thuộc thứ tự đánh giá, khó kiểm tra kiểu và ảnh hưởng đến Configuration Cache hoặc Isolated Projects.

Bài này tập trung vào cách **đọc hiểu, viết đúng và bảo trì** Groovy DSL. Ví dụ dùng các task Gradle và Groovy; không yêu cầu một chương trình Java riêng. Để thực hành, sử dụng Gradle Wrapper của dự án với JDK tương thích bản Gradle đang chạy.

## 2. Vì sao Groovy DSL được gọi là động?

Groovy hỗ trợ truy cập property bằng dấu chấm (`object.name`), chuyển lời gọi sang một đối tượng nhận (delegate) của closure và phân giải phương thức/property vào thời điểm cấu hình. Gradle tận dụng các đặc tính đó để tạo DSL dễ đọc:

~~~groovy
plugins {
    id 'base'
}

tasks.register('sayHello') {
    doLast {
        println('Xin chào từ Gradle')
    }
}
~~~

Các khối `plugins { ... }`, `tasks.register(...)` và `doLast { ... }` không phải là cú pháp tự có của Gradle trong ngôn ngữ Java. Chúng là API Gradle kết hợp cú pháp Groovy. Khi đọc một đoạn script, cần phân biệt:

| Thành phần | Bản chất | Ví dụ |
| --- | --- | --- |
| Biến Groovy cục bộ | Biến trong phạm vi script/closure; không tự thành property của `Project` | `def message = 'hello'` |
| Property có sẵn của Gradle | Tên do đối tượng Gradle cung cấp | `project.name`, `project.version` |
| Extra property | Key/value được thêm vào `ExtensionAware` qua `ext` | `project.ext.apiLevel = 2` |
| Project property từ môi trường build | Cấu hình từ `-P`, `gradle.properties`, v.v. | `-PdeployEnv=staging` |
| Extension do plugin đăng ký | Đối tượng cấu hình có API riêng | `java { ... }` sau khi áp dụng Java plugin |
| Task do plugin hoặc script đăng ký | Đối tượng task có tên trong project | `tasks.named('help')` |

Một tên ngắn như `version` hoặc `release` có thể trùng với property có sẵn, extension hay task. Vì vậy, khi cần đọc một giá trị quan trọng, cách viết rõ đối tượng sở hữu như `project.ext.apiLevel` thường dễ duy trì hơn một tên trần `apiLevel`.

## 3. Extra properties: khai báo, đọc và cập nhật

`ExtraPropertiesExtension` là đối tượng gắn với các đối tượng Gradle triển khai `ExtensionAware`. Nó đóng vai trò kho key/value linh hoạt; ở Groovy, Gradle đặt tên truy cập ngắn là `ext`.

Ví dụ **độc lập** trong `build.gradle`:

~~~groovy
plugins {
    id 'base'
}

ext {
    applicationCode = 'inventory'
    retryLimit = 3
    releaseEnabled = false
}

assert project.ext.applicationCode == 'inventory'
assert project.ext.get('applicationCode') == 'inventory'
assert project.ext['applicationCode'] == 'inventory'
assert project.applicationCode == 'inventory'

project.ext.retryLimit = 4
assert project.ext.retryLimit == 4
assert project.retryLimit == 4
~~~

Tất cả assert phải đúng; chúng được đánh giá trong pha **configuration** khi Gradle đọc script. Đây là ví dụ để học cú pháp, không phải lý do để đưa các assert khó hiểu vào build script sản xuất.

Có ba cách khai báo tương đương:

~~~groovy
project.ext.color = 'blue'
project.ext['color'] = 'blue'
project.extensions.extraProperties.set('color', 'blue')
~~~

Các phép gán này **tạo hoặc cập nhật** một extra property tên `color` trên `project`. Sau khi tên đã được khai báo qua `ext`, Groovy cũng cho phép gán `project.color = 'green'`. Tuy nhiên, phép gán tùy ý `project.unknownName = 'value'` khi chưa có property tương ứng có thể báo lỗi; cách tạo rõ ràng là `project.ext.unknownName = 'value'`.

Giá trị `ext` có thể là String, Integer, Boolean, List, Map hay đối tượng bất kỳ. Điểm thuận tiện này cũng là nhược điểm: **Gradle không tự tạo hợp đồng kiểu cho từng key** và không bảo đảm kiểu ở mọi nơi sử dụng.

### 3.1. Kiểm tra sự tồn tại trước khi đọc

~~~groovy
ext.optionalLabel = null

assert ext.has('optionalLabel')          // property tồn tại
assert ext.get('optionalLabel') == null   // giá trị của nó là null
assert !ext.has('notDefined')             // property không tồn tại
~~~

Với `ext`, `has('name')` là cách rõ ràng để xác nhận *key có được khai báo hay chưa*. Không dùng `get('name') == null` hoặc `if (ext.name)` để phân biệt thiếu key, giá trị `null` và giá trị `false`: chúng là các tình huống khác nhau.

Khi truy cập key không tồn tại:

- `ext.get('missing')` ném `ExtraPropertiesExtension.UnknownPropertyException`.
- `ext.missing` dùng cú pháp Groovy, có thể ném `groovy.lang.MissingPropertyException`.
- `project.findProperty('missing')` trả về `null` nếu không tìm thấy sau khi xét các phạm vi property của Project; nó không chỉ tìm trong `ext`.

Nếu chỉ muốn kiểm tra **extra property trên đối tượng hiện tại**, dùng `project.extensions.extraProperties.has('name')`. `project.hasProperty('name')` có phạm vi tìm kiếm rộng hơn và có thể báo `true` cho property có sẵn, extension hoặc task.

### 3.2. `ext.properties` không phải Map để ghi ngược

~~~groovy
project.ext.featureFlag = true

def snapshot = project.ext.properties
snapshot.featureFlag = false

assert project.ext.featureFlag == true
~~~

`ext.properties` trả một **bản Map tách rời**. Chỉnh Map đó không cập nhật `ExtraPropertiesExtension`. Muốn đổi giá trị thật, gán qua `project.ext.featureFlag = false` hoặc gọi `set('featureFlag', false)`.

## 4. Phạm vi: biến cục bộ, Project, Task và rootProject

`def localFlag = true` chỉ định một biến Groovy trong vùng mã tương ứng. Nó không tự xuất hiện ở `project.ext`, không bảo đảm script khác nhìn thấy và không tự truyền xuống subproject.

Ngược lại, `project.ext.flag = true` lưu trên đối tượng `Project`. Nếu đang cấu hình task hoặc extension khác, `ext` không nhất thiết là `project.ext`: delegate của closure có thể là chính đối tượng đang được cấu hình.

Ví dụ phân biệt tên sở hữu:

~~~groovy
// build.gradle của root
project.ext.teamName = 'backend'

tasks.register('checkScope') {
    ext.taskNote = 'Chỉ gắn trên task checkScope'

    // Tại configuration: đọc rõ Project và Task
    assert project.ext.teamName == 'backend'
    assert ext.taskNote == 'Chỉ gắn trên task checkScope'
}
~~~

Ở trong closure cấu hình task, `ext.taskNote` gắn vào **Task**, còn `project.ext.teamName` thuộc **Project**. Tránh viết tên trần `teamName` khi có nhiều scope dễ gây nhầm. Cũng không nên đọc `task.ext` trong `doLast` chỉ để chuyển một tham số vào task: cách truy cập extra properties lúc thực thi có rủi ro tương thích với các phiên bản Gradle mới.

### 4.1. Đọc property root từ subproject

Trong dự án nhiều module, mã cũ có thể dựa vào cơ chế tìm property của project cha:

~~~groovy
// Root build.gradle
rootProject.ext.sharedLabel = 'common'

// app/build.gradle — cách đọc rõ nơi sở hữu
def label = rootProject.extensions.extraProperties.get('sharedLabel')
~~~

Lịch sử Groovy DSL cho phép một số tên property của parent/root được tra cứu ngầm từ project con. **Gradle 9.6 đã deprecate việc tìm property/method ngầm trong parent project**, hướng tới loại bỏ trong Gradle 10 và không hỗ trợ ở Isolated Projects. Khi duy trì mã cũ, không nên đặt niềm tin vào `sharedLabel` không có tiền tố; xác định nguồn rõ ràng.

Cách `rootProject.ext.sharedLabel` làm ý định rõ hơn, nhưng **đọc/chỉnh đối tượng Project khác vẫn có thể không tương thích Isolated Projects**. Với cấu hình dùng chung nhiều module về lâu dài, nên chuyển sang convention plugin, extension hoặc property/provider được khai báo ở từng project theo cơ chế Gradle hỗ trợ, tránh logic `allprojects`/`subprojects` truy cập chéo tùy tiện.

## 5. Extra property và `-P`/`gradle.properties` khác nhau thế nào?

Đây là một trong những nguồn lỗi khó thấy nhất.

| Cơ chế | Nơi giá trị xuất phát | Cách truy cập phù hợp |
| --- | --- | --- |
| Extra property gắn vào Project | `project.ext.key = value` trong build logic | `project.extensions.extraProperties.get('key')`, `ext.key` |
| Gradle project property từ môi trường | `-Pkey=value`, `gradle.properties` hoặc nguồn `ORG_GRADLE_PROJECT_*` / system property tương ứng | `providers.gradleProperty('key')` |
| `Project.findProperty('key')` | Tra cứu **mô hình Project động**: property gốc, extra properties, extension, task, và có thể parent theo version | `project.findProperty('key')` trả Object hoặc null |
| Biến Groovy thông thường | `def key = ...` trong một script/closure | Dùng trực tiếp theo phạm vi lexical |

Ví dụ file `gradle.properties` ở root:

~~~properties
buildMode=local
~~~

Trong `build.gradle`, giá trị từ **nguồn Gradle property** nên được đọc theo cách lazy:

~~~groovy
def buildModeProvider = providers.gradleProperty('buildMode').orElse('dev')

tasks.register('printMode') {
    def mode = buildModeProvider
    doLast {
        println('mode=' + mode.get())
    }
}
~~~

Tại root project, với lệnh:

~~~bash
./gradlew -q printMode
./gradlew -q printMode -PbuildMode=ci
~~~

Các dòng do task in ra tương ứng là `mode=local` và `mode=ci`. Kết quả có thể có thêm thông điệp môi trường/Gradle nếu runner phát cảnh báo; hai giá trị trên là phần output của task. Cờ `-P` là **project property**, không đồng nghĩa việc tạo một `ext` trong mã script.

**Quan trọng:** `providers.gradleProperty('key')` tìm trong các **nguồn Gradle property của môi trường build**; nó **không tìm các extra properties được tạo động** qua `project.ext.key`, cũng không tìm extension/task của Project. Vì vậy, với `ext.buildMode = 'custom'`, không được giả định `providers.gradleProperty('buildMode')` sẽ trả về `custom`. Ngược lại, `findProperty('buildMode')` có thể đọc extra property đó.

Nếu chủ động đặt một extra property **trùng tên** với `-PbuildMode=ci`, các kết quả lookup động và provider có thể khác nhau vì extra property được gán tường minh có ưu tiên trong mô hình Project, còn Provider API đọc nguồn build-level. Tránh tái sử dụng cùng một tên cho hai cơ chế khác ý nghĩa. Dùng tên rõ, thống nhất nguồn dữ liệu và xác định chủ đích người dùng có được override bằng `-P` hay không.

## 6. Script plugin là gì và khi nào được chạy?

Một **script plugin** dùng Groovy DSL là file có đuôi `.gradle` chứa mã build logic; một build script có thể áp dụng nó bằng:

~~~groovy
apply from: "$rootDir/gradle/reports.gradle"
~~~

Khi `apply from:` được thực thi trong **pha configuration**, Gradle đánh giá script được tham chiếu **trong ngữ cảnh đối tượng được áp dụng**, thông thường là `Project` của build script gọi nó. Vì vậy script có thể truy cập `project`, `tasks`, `repositories` hoặc cấu hình extension sẵn có của project đó.

Script plugin khác các khái niệm sau:

- **Binary plugin** (`Plugin<Project>`) là một thành phần có kiểu, class và API rõ ràng; có thể đóng gói, test và phân phối.
- **Precompiled script plugin** là script DSL được biên dịch thành plugin, thường đặt trong `buildSrc` hoặc included build `build-logic`; áp dụng bằng plugin ID.
- **`plugins { id 'java' }`** trong build script là DSL khai báo plugin; nó **không tương đương** `apply from:` và không phải nơi nạp script Gradle tùy ý.

Theo Gradle hiện đại, `plugins { ... }` được giới hạn cho project build script, settings script và ngữ cảnh precompiled script plugin được hỗ trợ; **không đặt khối `plugins { }` trong script plugin thông thường nạp bằng `apply from:`**. Nếu script plugin cần bảo đảm một plugin đã có, hãy khai báo plugin đó trong build script chính hoặc chuyển logic sang convention plugin. Lệnh imperative `apply plugin: 'java'` vẫn tồn tại cho mã cũ, nhưng `plugins { id 'java' }` ở build script chính thường rõ ràng hơn.

Gradle hiện **không khuyến nghị mở rộng lâu dài cách tổ chức build logic bằng `apply from:`**. Nó vẫn hữu ích để đọc hiểu dự án hiện hữu hoặc thực nghiệm nhỏ; khi logic thành quy ước chung, ưu tiên precompiled script plugin hay binary plugin.

## 7. Ví dụ đầy đủ: truyền extra property vào script plugin

Ví dụ này chỉ cần một Gradle project **đã có Wrapper**, không cần thư viện ngoài hay source Java. Tạo đúng các file dưới đây:

~~~text
groovy-dsl-demo/
├── gradlew
├── gradlew.bat
├── settings.gradle
├── build.gradle
└── gradle/
    ├── wrapper/
    │   ├── gradle-wrapper.jar
    │   └── gradle-wrapper.properties
    └── report.gradle
~~~

### Bước 1 — `settings.gradle`

~~~groovy
rootProject.name = 'groovy-dsl-demo'
~~~

### Bước 2 — `build.gradle`

~~~groovy
plugins {
    id 'base'
}

ext {
    appCode = 'inventory'
    retryLimit = 3
}

apply from: "$rootDir/gradle/report.gradle"
~~~

`ext { ... }` khai báo hai extra properties của root Project **trước khi** nạp `report.gradle`. Việc dùng `$rootDir` khiến đường dẫn script rõ ràng ngay cả khi file được tham chiếu từ một thư mục khác; với các dự án nhiều module, vẫn phải chọn đúng project nhận script.

### Bước 3 — `gradle/report.gradle`

~~~groovy
import org.gradle.api.GradleException

def values = project.extensions.extraProperties

if (!values.has('appCode') || !values.has('retryLimit')) {
    throw new GradleException(
        'Missing required extra properties: appCode or retryLimit'
    )
}

def code = values.get('appCode').toString()
def retries = values.get('retryLimit') as Integer

tasks.register('showBuildConfig') {
    // Lấy các giá trị tại thời điểm cấu hình task.
    def codeForTask = code
    def retriesForTask = retries

    // buildMode là Gradle property của môi trường, không phải ext.
    def modeForTask = project.providers
        .gradleProperty('buildMode')
        .orElse('local')

    doLast {
        println('appCode=' + codeForTask)
        println('retryLimit=' + retriesForTask)
        println('buildMode=' + modeForTask.get())
    }
}
~~~

Đoạn mã có thể chạy trên Gradle tương thích với JDK của máy. Nó cố ý đọc `ext` và tạo Provider **trong pha configuration của task**, rồi `doLast` chỉ dùng các scalar và Provider đã nắm giữ. Điều này tránh một anti-pattern thường gặp: truy cập `project.ext` trực tiếp trong task action. Ví dụ phục vụ học tập; cấu hình cache/input/output và khả năng tái sử dụng dài hạn của mọi script plugin vẫn phải kiểm tra theo Gradle version của dự án.

### Bước 4 — chạy và kiểm chứng

Trên Linux/macOS, ở thư mục gốc:

~~~bash
./gradlew -q showBuildConfig
./gradlew -q showBuildConfig -PbuildMode=ci
~~~

Phần output **do task này in ra** ở lệnh thứ nhất:

~~~text
appCode=inventory
retryLimit=3
buildMode=local
~~~

Lệnh thứ hai in:

~~~text
appCode=inventory
retryLimit=3
buildMode=ci
~~~

`appCode` và `retryLimit` là extra properties trong script chính; `buildMode` đến từ Gradle Provider API và có thể được ghi đè bằng `-P`. Không có `gradle.properties` trong ví dụ nên `orElse('local')` cung cấp mặc định. Trên Windows dùng `gradlew.bat -q showBuildConfig` (Command Prompt) hoặc `.\gradlew.bat -q showBuildConfig` (PowerShell).

Thử chuyển dòng `apply from:` **lên trước** khối `ext { ... }`: script plugin kiểm tra `has` khi được áp dụng và sẽ báo thiếu hai key. Đây là bằng chứng đơn giản rằng **thứ tự đánh giá** có ảnh hưởng đến script plugin và cấu hình động.

Không cần thực hiện phép đổi thứ tự trên dự án thật để học; có thể tái hiện trong một project demo riêng.

## 8. Script plugin nhận giá trị ra sao? Hiểu đúng thứ tự cấu hình

Với ví dụ trên, Gradle đi qua các bước logic:

~~~text
Đọc settings.gradle
         │
         ▼
Đánh giá build.gradle
         │
         ├── áp dụng plugin base
         ├── khai báo project.ext.appCode / retryLimit
         └── apply from: gradle/report.gradle
                     │
                     ├── đọc project.ext
                     ├── kiểm tra các key bắt buộc
                     └── đăng ký task showBuildConfig
                               │
                               ▼
                      chọn task cần chạy
                               │
                               ▼
                  cấu hình task được yêu cầu
                               │
                               ▼
                   thực thi doLast của task
~~~

`tasks.register` đăng ký task theo mô hình configuration avoidance; closure cấu hình task có thể chỉ chạy khi task được yêu cầu hoặc cần được cấu hình. Đừng nhầm thời điểm **áp dụng script plugin** với thời điểm **doLast chạy**.

Nếu đổi thứ tự hoặc bổ sung logic thay đổi giá trị `ext`, hãy tự hỏi:

1. **Ai sở hữu key?** `project.ext` của root, `project.ext` của module, hay `task.ext`?
2. **Ai khai báo trước?** Script chính đã có `ext.foo` khi plugin bắt đầu đọc hay chưa?
3. **Ai thay đổi sau?** Một plugin hoặc script khác có ghi đè key?
4. **Task chụp giá trị khi nào?** Ở configuration hay đọc Project tại execution?
5. **Key đến từ nguồn nào?** `-P`/`gradle.properties` hay extra property động?

Để bảo trì, đặt khai báo ở vị trí rõ ràng và tránh cơ chế một script “bí mật” sửa hàng loạt property mà người dùng không thể truy vết.

## 9. Nhiều module: tránh phụ thuộc ngầm và tên va chạm

Giả sử có `:app` và `:library`:

~~~groovy
// settings.gradle
rootProject.name = 'example'
include 'app', 'library'
~~~

Mỗi project có các extension, task và extra properties của riêng nó. Nếu cần áp dụng cùng script vào hai module:

~~~groovy
// app/build.gradle (chỉ ví dụ cho module app)
plugins {
    id 'base'
}

ext.appCode = 'app'
ext.retryLimit = 2
apply from: "$rootDir/gradle/report.gradle"
~~~

~~~groovy
// library/build.gradle (chỉ ví dụ cho module library)
plugins {
    id 'base'
}

ext.appCode = 'library'
ext.retryLimit = 4
apply from: "$rootDir/gradle/report.gradle"
~~~

Tại mỗi module, script được áp dụng với **project hiện hành** làm target và đăng ký `showBuildConfig` trong project đó. Có thể chạy `./gradlew -q :app:showBuildConfig` và `./gradlew -q :library:showBuildConfig` để nhắm đúng task path.

Đây là ví dụ minh họa việc **lặp logic script plugin**, không phải kiến trúc khuyến nghị cho số lượng lớn module. Khi các module phải tuân theo cùng một bộ quy ước, tạo convention plugin để mỗi module áp dụng một plugin ID sẽ rõ ràng hơn và hỗ trợ tiến tới Isolated Projects.

Tránh đặt key quá chung như `version`, `name`, `java`, `test`, `build` trong `ext` vì chúng có thể trùng với property Project, extension hoặc task. Nên dùng tên đặc thù (`releaseChannel`, `serviceCode`) và định nghĩa tập key bắt buộc một cách minh bạch.

## 10. Giới hạn lớn nhất của cấu hình động

### 10.1. Khó kiểm tra kiểu và phát hiện lỗi muộn

Groovy cho phép giá trị tùy ý:

~~~groovy
ext.timeoutSeconds = '30'
~~~

Một đoạn khác giả sử nó là Integer:

~~~groovy
def timeout = project.ext.timeoutSeconds as Integer
~~~

Việc ép kiểu phụ thuộc dữ liệu thực khi script được đánh giá; gõ nhầm key hoặc đưa vào giá trị không ép kiểu được mới gây lỗi lúc cấu hình. Với số lượng module lớn, lỗi có thể nằm cách xa nơi khai báo key. Một **typed extension** với `Property<Integer>` hoặc `Property<String>` giúp Gradle nhận biết kiểu, convention và validation rõ hơn.

### 10.2. Closure có delegate, owner và quy tắc tìm tên động

Trong `build.gradle`:

~~~groovy
ext.descriptionText = 'Mô tả của dự án'

tasks.register('example') {
    ext.descriptionText = 'Mô tả của task'
}
~~~

Hai giá trị này không giống nhau: một thuộc Project, một thuộc Task. Khi không viết tiền tố `project` hoặc `ext` rõ ràng, Groovy có thể tra tên ở delegate/owner khác với suy đoán của người đọc. Hãy dùng `project.extensions.extraProperties`, `tasks.named(...)` và API cấu hình rõ ràng để giảm nhập nhằng.

### 10.3. Phụ thuộc thứ tự và `afterEvaluate`

Cách khắc phục lỗi “property chưa có” bằng `afterEvaluate { ... }` thường chỉ **dời thời điểm chạy** mà không làm quan hệ cấu hình trở nên rõ ràng. Nó có thể tạo chuỗi callback khó dự đoán, phụ thuộc thứ tự plugin và làm build kém tương thích các cơ chế cấu hình mới.

Nếu cần đợi một plugin cụ thể xuất hiện, dùng callback nhắm vào plugin:

~~~groovy
plugins.withId('java') {
    tasks.named('jar') {
        archiveBaseName.set('demo-artifact')
    }
}
~~~

Khối này được chạy khi plugin `java` đã được áp dụng; task `jar` được cấu hình qua API lazy. Nó là **trích đoạn** thích hợp trong build script hoặc plugin cấu hình Project; task `jar` tồn tại khi Java plugin được áp dụng, và những logic dành cho `jar` nên nằm trong callback này. Không cần `afterEvaluate` chỉ để chờ tên plugin.

### 10.4. Chi phí cấu hình và configuration avoidance

Thực thi tính toán tốn kém, truy cập filesystem/network, tạo task hàng loạt hoặc phân giải dependency một cách eager trong script plugin khiến mọi lệnh Gradle phải gánh chi phí cấu hình khi cache chưa được dùng. Những cách viết sau đáng xem lại:

- `tasks.create('x')` tạo/cấu hình task tức thì khi chưa cần; `tasks.register('x')` thường phù hợp hơn.
- `tasks.getByName('x')` kích hoạt cấu hình task; `tasks.named('x')` trả `TaskProvider` để tiếp tục cấu hình lazy.
- `allprojects { ... }`, `subprojects { ... }` với truy cập qua lại giữa các Project cản trở mô hình project isolation.
- `afterEvaluate` và callback phụ thuộc trạng thái thay đổi muộn khiến khó biết thời điểm tính giá trị.

Lazy configuration giúp Gradle chỉ cấu hình phần cần dùng; nhưng chỉ bọc mã trong `tasks.register` không tự giải quyết tác dụng phụ của script plugin hoặc truy cập Project sai thời điểm.

### 10.5. Configuration Cache không lưu/đọc lại mọi đối tượng động một cách tùy ý

Configuration Cache lưu trạng thái cấu hình của task graph để tránh đánh giá lại build script khi đầu vào không đổi. Để hoạt động ổn định, task action không được tham chiếu trực tiếp tới `Project`/`Gradle`/`Settings` hoặc thao tác với extension, convention và extra properties lúc execution.

**Cách cũ có vấn đề** trong `build.gradle`:

~~~groovy
ext.serviceCode = 'billing'

tasks.register('badReport') {
    doLast {
        // Không nên: lấy Project + extra property tại task execution
        println(project.ext.serviceCode)
    }
}
~~~

**Cách cải thiện cho ví dụ nhỏ**:

~~~groovy
ext.serviceCode = 'billing'

tasks.register('betterReport') {
    // Chụp dữ liệu thuần trong pha cấu hình task
    def codeForTask = project.ext.serviceCode.toString()

    doLast {
        println(codeForTask)
    }
}
~~~

Dòng của task `betterReport` in `billing`. Tuy nhiên, với **task sản xuất có output cần kiểm soát và cache**, nên mô hình hóa `@Input`, `@OutputFile` và các `Property<T>` trên **typed task class**; chuyển giá trị qua convention/Provider rồi để task dùng property riêng. Trường hợp chỉ in ra stdout không có output file nên cách minh họa trên không biến task thành một task “có thể cache output”.

Với dữ liệu đến từ build environment, dùng trực tiếp:

~~~groovy
tasks.register('printRegion') {
    def region = providers.gradleProperty('region').orElse('local')

    doLast {
        println(region.get())
    }
}
~~~

Provider được tạo trong configuration và đọc tại execution; nó đọc `-Pregion`/`gradle.properties`, **không đọc `ext.region`**. Hãy chạy thử `--configuration-cache` ít nhất hai lần và xem báo cáo Gradle khi điều chỉnh logic build; đừng chỉ kiểm tra một lần không có lỗi.

### 10.6. Độ tin cậy, kiểm soát nguồn và bảo mật

Một script plugin thực thi mã Groovy với quyền của tiến trình Gradle. Nếu nạp script từ đường dẫn không kiểm soát hoặc sửa file script mà không review, người thay đổi có thể tác động cấu hình, dependency và tác vụ toàn build. Nên đặt script thuộc repository được quản lý, review thay đổi và tránh tải thực thi mã từ URL không tin cậy.

Extra properties dùng chung cũng dễ bị lạm dụng làm nơi lưu secret. Không commit password/token vào `ext` hay `gradle.properties` của dự án; đối với credential dùng thiết lập người dùng/CI và API credential Provider của Gradle theo thực tế plugin. Không in giá trị nhạy cảm ra console hoặc đưa vào task input/output không cần thiết.

## 11. Khi nào chọn `ext`, script plugin, convention plugin hay typed extension?

| Nhu cầu | Cách tiếp cận | Lý do |
| --- | --- | --- |
| Một giá trị tạm thời, cục bộ trong script | `def localName = ...` | Rõ phạm vi, không làm phình model Project |
| Giá trị cấu hình từ CLI hoặc CI | `providers.gradleProperty('name')`, `providers.environmentVariable('NAME')` | Lazy, có cơ chế theo dõi input phù hợp |
| Cần đọc extra property trong dự án cũ | `project.extensions.extraProperties.has/get` | Chính xác tên, phạm vi và xử lý khi thiếu |
| Cấu hình dùng chung cực nhỏ trong một build cũ | `apply from:` với đường dẫn được quản lý | Dễ tiếp nhận mã hiện hữu; giới hạn việc mở rộng |
| Một bộ quy ước cho nhiều module | Precompiled script plugin trong `build-logic`/`buildSrc` | Có plugin ID, áp dụng rõ và kiểm tra dễ hơn |
| Logic build có yêu cầu kiểu và test cao | Binary plugin + typed extension/task | API rõ ràng, kiểm tra/phiên bản hóa/tái sử dụng tốt hơn |
| Giá trị tùy chọn được các task sử dụng | `Property<T>` hoặc `Provider<T>`, khai báo task inputs | Kiểu, lifecycle và cache rõ hơn |

`ext` không phải tính năng “sai”; nó phục vụ mục đích mở rộng linh hoạt. Vấn đề phát sinh khi sử dụng nó như cơ chế cấu hình chính cho cả hệ thống mà không có hợp đồng về kiểu, vòng đời và nguồn giá trị.

### 11.1. Lộ trình nâng cấp từ script plugin

Nếu repository có nhiều dòng `apply from: "$rootDir/gradle/quality.gradle"`:

1. Kiểm kê task, plugin, extension và extra key do script cấu hình; ghi lại module cần dùng từng phần.
2. Phân biệt logic **đăng ký cấu hình** với logic **thực thi task**; bỏ truy cập Project/`ext` trong task action.
3. Đưa phần cấu hình chung vào convention plugin (`build-logic` hoặc `buildSrc`), giữ API typed cho giá trị cấu hình cần chia sẻ.
4. Áp dụng plugin ID ở `plugins { ... }` của từng project; tránh chia sẻ trạng thái động bằng callback xuyên project.
5. Thay `-P`/`gradle.properties` được dùng động bằng Provider API phù hợp; tách secret khỏi mã nguồn.
6. Kiểm tra task path, output, test của build và `--configuration-cache` trước và sau chuyển đổi.

Không bắt buộc chuyển toàn bộ build logic trong một commit; chọn một nhóm quy ước có ranh giới rõ và bảo toàn hành vi.

## 12. Chẩn đoán lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra / hướng sửa |
| --- | --- | --- |
| `Could not get unknown property 'x'` hoặc `MissingPropertyException` | Key không có, sai chữ hoa/thường hoặc tra nhầm owner | Dùng `ext.has('x')` trên đúng đối tượng; kiểm tra điểm khai báo và thứ tự áp dụng |
| `project.findProperty('x') == null` dù trông như có giá trị | Key chưa khai báo, hoặc có giá trị `null`; tra sai phạm vi | Dùng `project.ext.has('x')` để phân biệt tồn tại với giá trị |
| `-PbuildMode=ci` không thay giá trị đang dùng | Script đọc key `ext` độc lập hoặc chủ động ghi đè key động | Dùng `providers.gradleProperty('buildMode')` nếu muốn CLI override, tránh trùng tên |
| `providers.gradleProperty('x')` trả empty dù `ext.x` có giá trị | Provider API không tìm Project extra property | Đọc `ext` rõ ràng hoặc chuyển nguồn cấu hình sang `gradle.properties`/`-P` |
| `Could not read script ...` | Sai đường dẫn `apply from:` | Thử đường dẫn rõ như `"$rootDir/gradle/report.gradle"` và xác nhận file tồn tại |
| `Only Project and Settings build scripts can contain plugins {} blocks` | Đặt `plugins { }` trong script plugin thường | Chuyển khai báo plugin vào `build.gradle` hoặc convention plugin |
| `Task with name 'x' already exists` | Script nạp lại hoặc nhiều plugin cùng đăng ký task tên `x` | Tìm nguồn đăng ký, gom quy ước vào một plugin và tránh apply lặp |
| Giá trị thay đổi theo module hoặc theo lần chạy | Dùng lookup ngầm parent/project/task; thứ tự script khác nhau | Viết rõ owner, task path và thời điểm tạo; bỏ phụ thuộc parent lookup ngầm |
| Configuration Cache báo `Project` được dùng ở execution time | `doLast` hoặc `@TaskAction` truy cập `project`, `ext`/extension | Chuyển cấu hình sang Provider/typed task input và sử dụng task-owned state |
| Build cấu hình chậm dù chỉ chạy một task nhỏ | Script plugin tạo task/eager resolve hoặc chạy IO khi configuration | Dùng `tasks.register`, `tasks.named`/`configureEach`, bỏ IO không cần, kiểm tra build profile |
| `ClassCastException` hoặc ép kiểu không thành công | Giá trị `ext` có kiểu khác dự kiến | Kiểm tra dữ liệu đầu vào, thêm validation và typed extension |
| Build cũ cảnh báo về parent project lookup | Dùng tên property/method trên parent ngầm; hành vi bị deprecate từ Gradle 9.6 | Viết rõ nơi tham chiếu khi cần và thiết kế convention plugin tránh cross-project access |

## 13. Bài luyện tập có tiêu chí đánh giá

**Bài A — phân biệt local/extra/project property.** Trong project demo, thêm `def message = 'local'` và `ext.message = 'extra'`. Quan sát `message` và `project.ext.message` trong phần cấu hình. Giải thích vì sao hai giá trị là hai biến khác phạm vi, và khi nào lookup tên trần có thể gây hiểu nhầm.

**Bài B — tính năng tùy chọn.** Thay `buildMode` bằng `-PfeatureLevel=2`; đọc bằng `providers.gradleProperty('featureLevel').map { it.toInteger() }.orElse(1)`, truyền vào task configuration và in giá trị. Chạy có/không có `-P`. Nếu đưa `-PfeatureLevel=abc` thì cần quyết định rõ cách báo lỗi dữ liệu không hợp lệ.

**Bài C — tránh cấu hình muộn.** Với một đoạn `afterEvaluate { tasks.getByName('jar') ... }` trong build cũ, viết lại bằng `plugins.withId('java') { tasks.named('jar') { ... } }` và kiểm tra task `jar` vẫn được cấu hình khi plugin Java áp dụng.

**Bài D — kiểm tra Configuration Cache.** Chạy hai lần với cùng task và cờ `--configuration-cache`. Tìm báo cáo nếu Gradle phản ánh vấn đề, truy nguyên closure có truy cập `Project` khi execution không, và sửa bằng Provider/typed task. Không đánh giá “đã tương thích” chỉ từ việc task in đúng chữ.

Các bài tập thay đổi cấu hình trong **project demo** và nên được hoàn tác sau khi học; không áp dụng thử trực tiếp lên build production mà chưa review.

## 14. Ghi nhớ

- `ext` gắn **key/value động vào đối tượng sở hữu**. Khai báo và đọc nên ghi rõ `project.ext`, `task.ext` hoặc `extensions.extraProperties`.
- `has` kiểm tra key tồn tại; `get` lấy giá trị hoặc ném lỗi nếu thiếu; `ext.properties` là Map tách rời.
- `project.findProperty/hasProperty` tìm trong **mô hình Project động**; `providers.gradleProperty` chỉ tìm trong **nguồn Gradle property của môi trường build**. Chúng có phạm vi khác nhau.
- Script plugin `.gradle` được nạp bằng `apply from:`; **thứ tự áp dụng** và Project target quyết định key/task nào sẵn có.
- Giới hạn của cấu hình động là **thiếu hợp đồng kiểu, dễ trùng tên, phụ thuộc thứ tự, cấu hình eager và rủi ro khi task truy cập Project ở execution**.
- Khi logic trở nên dùng chung/lâu dài, ưu tiên **convention plugin + typed extension/task + Provider API**, kiểm tra Configuration Cache và tránh lookup xuyên project ngầm.

## Tài liệu tham khảo chính thức

- [ExtraPropertiesExtension — Gradle API](https://docs.gradle.org/current/dsl/org.gradle.api.plugins.ExtraPropertiesExtension.html): `ext`, `get`, `set`, `has`, Map properties và ngoại lệ khi thiếu key.
- [Build Environment Configuration](https://docs.gradle.org/current/userguide/build_environment.html): `-P`, `gradle.properties`, `providers.gradleProperty` và phân biệt lookup động.
- [Working with Plugins](https://docs.gradle.org/current/userguide/plugins.html): script plugin, `apply from:`, precompiled script plugin, plugin DSL.
- [Implementation Options for Plugins](https://docs.gradle.org/current/userguide/implementing_gradle_plugins.html): lựa chọn script, precompiled hay binary plugin.
- [Configuration Cache](https://docs.gradle.org/current/userguide/configuration_cache.html): vòng đời cấu hình và điều kiện cache.
- [Configuration Cache Requirements](https://docs.gradle.org/current/userguide/configuration_cache_requirements.html): tránh dùng Project/extra properties ở task execution.
- [Isolated Projects](https://docs.gradle.org/current/userguide/isolated_projects.html): deprecation lookup parent ngầm, giới hạn cross-project access.
