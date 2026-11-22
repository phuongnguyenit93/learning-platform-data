# Closure, delegate và cách hiểu các khối cấu hình Gradle (Groovy DSL)

## 1. Mục tiêu bài học

Khi đọc `build.gradle` viết bằng Groovy DSL, bạn liên tục gặp các cấu trúc như:

~~~groovy
repositories {
    mavenCentral()
}

dependencies {
    implementation 'com.google.guava:guava:33.4.0-jre'
}

tasks.register('hello') {
    doLast {
        println 'Xin chào Gradle'
    }
}
~~~

Ba khối đều dùng dấu ngoặc nhọn, nhưng **không cùng cấu hình một đối tượng**. `repositories` thường cấu hình đối tượng quản lý kho; `dependencies` cấu hình đối tượng quản lý dependency; `tasks.register` cấu hình một task. Điều làm cú pháp này ngắn gọn là **Groovy closure** và khả năng Gradle cung cấp **đối tượng đích** cho closure.

Sau bài học, bạn có thể:
1. Giải thích closure là gì, phân biệt closure với method và block cú pháp thông thường.
2. Phân biệt `thisObject`, `owner`, `delegate`, `resolveStrategy` và biến cục bộ được closure capture.
3. Nhận ra đối tượng được cấu hình trong `repositories {}`, `dependencies {}`, `java {}`, `tasks.register {}`, các khối lồng nhau.
4. Hiểu lúc nào closure là cấu hình và lúc nào là hành động chạy task.
5. Tránh lỗi gọi nhầm thuộc tính/method vì quá tin vào implicit delegate và biết cách tra Gradle DSL reference.

**Phạm vi:** Gradle Groovy DSL trong `settings.gradle` và `build.gradle`, không phải Kotlin DSL (`*.gradle.kts`). Ví dụ dùng Gradle Wrapper và JDK 17+. Những câu lệnh trình bày dưới dạng Linux/macOS `./gradlew`; trên Windows PowerShell dùng `.\gradlew.bat`.

## 2. Closure là đối tượng chứa hành vi

Trong Groovy, `{ ... }` có thể tạo một closure: một đối tượng `groovy.lang.Closure` chứa mã có thể gọi, nhận đối số, trả giá trị và **ghi nhớ biến trong phạm vi từ vựng** (lexical scope) nơi được tạo.

~~~groovy
def doubleNumber = { int value -> value * 2 }
assert doubleNumber(3) == 6
assert doubleNumber.call(4) == 8

def prefix = 'Xin chào'
def greet = { String name -> prefix + ', ' + name }
assert greet('Gradle') == 'Xin chào, Gradle'
~~~

Ý nghĩa:
- `{ int value -> ... }` định nghĩa tham số tường minh; `->` phân cách tham số với nội dung.
- Có thể gọi `doubleNumber(3)` hoặc `doubleNumber.call(3)`.
- Giá trị của biểu thức cuối cùng được trả về nếu không dùng `return` tường minh.
- `greet` truy cập biến `prefix` được khai báo ngoài closure; đó là **capture**, không phải tra `delegate`.
- Nếu chỉ có một tham số ngầm, Groovy cho phép dùng `it`: `{ it * 2 }`. Với closure không có tham số, dùng `{ -> ... }` để thể hiện rõ ý định.

### 2.1. Closure là đối số của lời gọi method

Groovy cho phép chuyển tham số closure ra sau dấu ngoặc tròn:

~~~groovy
def applyThreeTimes = { int n, Closure operation ->
    operation(operation(operation(n)))
}

assert applyThreeTimes(1, { it + 1 }) == 4
assert applyThreeTimes(1) { it + 1 } == 4
~~~

Bởi vậy, đoạn DSL sau có thể đọc ở mức cú pháp như **gọi method `repositories` rồi đưa một closure làm đối số**:

~~~groovy
repositories({
    mavenCentral()
})

// Cách viết DSL gọn và quen thuộc hơn:
repositories {
    mavenCentral()
}
~~~

Đây không phải hai kiểu lệnh khác nhau. Đối tượng/method thật được gọi vẫn phụ thuộc nơi đặt đoạn mã: một `Project` khác `Settings`, và một extension hoặc task cũng có các method khác nhau.

**Phân biệt:** Không phải *mọi* cặp `{ }` là closure tạo mới. Dấu ngoặc nhọn trong Groovy còn có thể bao thân class/method, điều kiện, vòng lặp; riêng `plugins {}` của Gradle là một DSL đặc biệt có cú pháp hạn chế (xem phần 8).

## 3. Bốn khái niệm nền tảng: `thisObject`, `owner`, `delegate`, `resolveStrategy`

Một closure có những mối liên hệ cần phân biệt:

| Thuộc tính | Nghĩa | Điều dễ nhầm |
| --- | --- | --- |
| `thisObject` (từ khóa `this` bên trong closure) | Đối tượng `this` thuộc phạm vi từ vựng nơi closure được **định nghĩa** | Không tự đổi thành đối tượng Gradle đang được cấu hình |
| `owner` | Đối tượng hoặc closure bao quanh tại nơi closure được định nghĩa; với closure lồng nhau, owner có thể là **closure ngoài** | Không nhất thiết trùng `thisObject` |
| `delegate` | Đối tượng thay thế để hỗ trợ tra thuộc tính/method động; có thể bị mã gọi closure gán lại | Không đồng nghĩa Java `this` hay luôn là object thuộc Project |
| `resolveStrategy` | Quy tắc tra các tên không được định danh tường minh giữa owner và delegate | Không thay đổi cách closure capture biến cục bộ |

Trong **Groovy thông thường**, khi mới tạo closure, `delegate` mặc định bằng `owner` và `resolveStrategy` mặc định là `Closure.OWNER_FIRST`. Một framework như Gradle có thể thay delegate và cách cấu hình closure theo API nó sử dụng. Vì vậy, không lấy `OWNER_FIRST` của Groovy thuần để kết luận rằng **mọi** cấu hình Gradle ưu tiên owner hơn đối tượng cần cấu hình.

### 3.1. Các chiến lược tra tên

| Giá trị | Hành vi tra property/method không định danh |
| --- | --- |
| `Closure.OWNER_FIRST` | Tìm ở `owner` trước; nếu không có mới tìm `delegate` (mặc định Groovy) |
| `Closure.DELEGATE_FIRST` | Tìm ở `delegate` trước, rồi `owner` |
| `Closure.OWNER_ONLY` | Chỉ tìm ở `owner` |
| `Closure.DELEGATE_ONLY` | Chỉ tìm ở `delegate` |
| `Closure.TO_SELF` | Cơ chế đặc biệt: tra ở chính đối tượng closure, chủ yếu cho meta-programming |

**Quy tắc rất quan trọng:** Biến cục bộ/biến được capture theo lexical scope được giải quyết trước sự lựa chọn owner/delegate. Đổi `resolveStrategy` sẽ **không** khiến một biến `def label` ở scope ngoài tự nhiên chuyển thành property `label` của delegate.

### 3.2. Ví dụ Groovy thuần: cùng một tên, hai kết quả

Ví dụ này chạy được trong Gradle nên không yêu cầu cài trình thông dịch Groovy riêng. Tạo thư mục `closure-resolution-lab` với `settings.gradle` và `build.gradle` (tạo Wrapper bằng `gradle wrapper` nếu chưa có).

**`settings.gradle`:**

~~~groovy
rootProject.name = 'closure-resolution-lab'
~~~

**`build.gradle` — mã đầy đủ:**

~~~groovy
plugins {
    id 'base'
}

class LabelOwner {
    String label = 'OWNER'

    Closure readLabel() {
        return { -> label }
    }
}

tasks.register('compareResolution') {
    group = 'help'
    description = 'So sánh hai cách tra tên của Groovy closure'

    doLast {
        def read = new LabelOwner().readLabel()
        read.delegate = [label: 'DELEGATE']

        println 'Default: ' + read()
        read.resolveStrategy = Closure.DELEGATE_FIRST
        println 'Delegate-first: ' + read()
    }
}
~~~

Chạy ở thư mục gốc:

~~~bash
./gradlew compareResolution
~~~

**Hai dòng stdout do task in ra (không tính log Gradle):**

~~~text
Default: OWNER
Delegate-first: DELEGATE
~~~

Giải thích theo từng bước:

1. `LabelOwner.readLabel()` tạo closure ở bên trong instance `LabelOwner`. Closure dùng tên `label` không kèm object.
2. `read.owner` là instance `LabelOwner` có property `label = 'OWNER'`.
3. `read.delegate` được đặt thành Map có khóa `label = 'DELEGATE'`.
4. Khi chưa đổi `resolveStrategy`, `OWNER_FIRST` tìm `label` của owner và trả `OWNER`.
5. Khi chuyển sang `DELEGATE_FIRST`, lookup chọn khóa `label` của Map và trả `DELEGATE`.

Đây là ví dụ về **quy tắc Groovy**, không phải khẳng định mọi Gradle configuration block đều dùng `DELEGATE_FIRST`. Để hiểu Gradle, phải biết API cụ thể cấp target nào cho closure.

### 3.3. Ví dụ capture: đổi delegate vẫn không át được biến cục bộ

~~~groovy
def label = 'LOCAL'
def readLabel = { -> label }

readLabel.delegate = [label: 'DELEGATE']
readLabel.resolveStrategy = Closure.DELEGATE_FIRST

assert readLabel() == 'LOCAL'
~~~

Đoạn trên là Groovy hợp lệ đặt trong script Groovy hoặc build script phù hợp, và không có stdout vì dùng `assert`. Khi có tên trùng với biến lexical, việc cố sửa `delegate` để “ép” tên đó chọn object khác là không đúng cách.

### 3.4. Closure lồng nhau làm `owner` khó đoán hơn

~~~groovy
def outer = {
    def inner = { ->
        assert owner.is(outer)
    }
    inner()
}
outer()
~~~

Trong `inner`, từ khóa `owner` thuộc về **closure `outer`**, còn `this` vẫn trỏ về đối tượng lexical bao quanh chỗ khai báo. Khi khối Gradle lồng sâu, không nên dựa vào suy đoán “owner luôn là project”. Để gọi rõ mục tiêu, ưu tiên `project.name`, `task.name`, `java.toolchain`, `configurations.named(...)` hoặc một biến có tên mô tả đối tượng.

## 4. Cách đọc các khối Gradle: hỏi “ai nhận closure, ai được cấu hình?”

Một cách đọc chính xác:

~~~text
Đối tượng đang nhận lời gọi
     |
     v
methodName( closure )  ---- Gradle/API chọn đối tượng đích
                                |
                                v
                        các property/method
                        trong khối cấu hình
~~~

Với Groovy DSL, một số từ khóa trông giống từ khóa riêng của ngôn ngữ thực ra là method, extension, container hoặc cấu hình mà plugin đăng ký.

### 4.1. Bảng nhận diện các khối phổ biến

| Khối trong `build.gradle` | Đối tượng/ý nghĩa đích | Tên bên trong thường thuộc về |
| --- | --- | --- |
| `repositories { mavenCentral() }` | `RepositoryHandler` của project | Method đăng ký kho như `mavenCentral()`, `maven { url = ... }` |
| `dependencies { implementation 'g:a:v' }` | `DependencyHandler` | Configuration `implementation` do Java plugin tạo; cú pháp Groovy method call |
| `java { toolchain { ... } }` | Java plugin extension rồi `JavaToolchainSpec` | `toolchain`, `languageVersion` |
| `application { mainClass = '...' }` | Application plugin extension | `mainClass` của ứng dụng |
| `tasks.register('hello') { ... }` | Task mang tên `hello` khi được tạo/cấu hình | `group`, `description`, `doLast` và API của `Task` |
| `tasks.named('test') { ... }` | Task `test` đã được plugin đăng ký | API `Test` như `useJUnitPlatform()`, `testLogging` |
| `configurations { create('integrationTest') }` | `ConfigurationContainer` | Các configuration phụ thuộc/runtime |
| `sourceSets { main { java { ... } } }` | `SourceSetContainer` → `SourceSet` → `SourceDirectorySet` | `main`, `java`, `srcDir`/`srcDirs` |
| `tasks.withType(Test).configureEach { ... }` | Mỗi `Test` task phù hợp khi được cấu hình | API `Test`; cấu hình lazy |

**Phân biệt “method nhận closure” với “đối tượng đích”:** Ở `repositories { mavenCentral() }`, lời gọi `repositories` được khởi phát từ script/project, nhưng `mavenCentral()` là method của `RepositoryHandler`. Không phải `mavenCentral()` tự nhiên là method của `Project`.

### 4.2. Đọc cú pháp rút gọn thành câu có chủ ngữ

~~~groovy
repositories {
    mavenCentral()
}
~~~

Đọc: “Hãy cấu hình bộ quản lý kho dependency của **project hiện tại**, bằng cách thêm Maven Central.”

~~~groovy
dependencies {
    implementation 'org.apache.commons:commons-lang3:3.17.0'
}
~~~

Đọc: “Hãy thêm module `commons-lang3` vào configuration `implementation` của **project hiện tại**.” Ví dụ này cần plugin tạo configuration đó, chẳng hạn `java`, `java-library` hoặc `application`. Giá trị phiên bản chỉ phục vụ bài học và không được hiểu là phiên bản mới nhất.

~~~groovy
tasks.register('printVersion') {
    group = 'help'
    doLast { task ->
        println task.project.version
    }
}
~~~

Đọc: “Đăng ký task `printVersion`; khi task được cấu hình, đặt `group`; khi task **được thực thi**, in version của project sở hữu nó.” `task` trong closure `doLast` là tham số tường minh do task action API cấp. Cú pháp nhận closure ở nhiều tầng **không có nghĩa** mọi tầng cùng chạy trong một pha.

### 4.3. Khối lồng nhau: mỗi tầng có thể đổi target

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

Diễn giải:

1. `plugins` yêu cầu áp dụng Java plugin. Đây là khối khai báo plugin đặc biệt, có ràng buộc cú pháp (xem phần 8).
2. Plugin thêm Java extension cho project.
3. `java { ... }` cấu hình extension này.
4. `toolchain { ... }` cấu hình spec của Java toolchain trong extension.
5. `languageVersion = JavaLanguageVersion.of(17)` đặt thuộc tính thuộc **toolchain spec**; không đặt version dự án Gradle.

Nếu project dùng Java plugin mà vẫn khai báo `languageVersion` ở top-level, sẽ không có cùng nghĩa. Trong Groovy DSL, vị trí của biểu thức trong các khối cấu hình quyết định object nhận nó.

## 5. Ví dụ Gradle + Java 17 chạy được: nhận biết từng đối tượng

Tạo `gradle-closure-app` như sau:

~~~text
gradle-closure-app/
├── settings.gradle
├── build.gradle
├── gradlew
├── gradlew.bat
├── gradle/wrapper/
│   ├── gradle-wrapper.jar
│   └── gradle-wrapper.properties
└── src/main/java/demo/App.java
~~~

**`settings.gradle`:**

~~~groovy
rootProject.name = 'gradle-closure-app'
~~~

**`build.gradle` — toàn bộ script:**

~~~groovy
plugins {
    id 'application'
}

group = 'demo'
version = '1.0'

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'demo.App'
}

tasks.register('showConfiguration') {
    group = 'help'
    description = 'In thông tin từ Task và Project'

    doLast { task ->
        println 'Project: ' + task.project.name
        println 'Version: ' + task.project.version
        println 'Task: ' + task.name
        println 'Path: ' + task.path
    }
}
~~~

**`src/main/java/demo/App.java`:**

~~~java
package demo;

public final class App {
    private App() {
    }

    public static void main(String[] args) {
        System.out.println("Gradle closure OK");
    }
}
~~~

Bài thực hành giả định đã có Wrapper trong thư mục root. Nếu chưa có, cần cài Gradle tạm thời, chạy `gradle wrapper` một lần rồi commit bộ Wrapper. Gradle cần tìm được toolchain JDK 17 hoặc đã cấu hình cơ chế cấp toolchain.

Chạy:

~~~bash
./gradlew showConfiguration
./gradlew run
./gradlew build
~~~

**Stdout từ `showConfiguration`, bỏ log task của Gradle:**

~~~text
Project: gradle-closure-app
Version: 1.0
Task: showConfiguration
Path: :showConfiguration
~~~

**Stdout của ứng dụng Java khi chạy `run`:**

~~~text
Gradle closure OK
~~~

Giải thích luồng:
- `application` áp dụng các khả năng Java và tạo các extension/task cần thiết. `mainClass` thuộc application extension, `languageVersion` thuộc toolchain spec.
- `version = '1.0'` ở top-level đặt version của `Project`. Trong closure của task, dùng `task.project.version` để phân biệt rõ với các thuộc tính của task.
- `tasks.register` trả về một `TaskProvider`. Nó đăng ký task **lazily**; mã cấu hình `group` và `description` được áp dụng khi task cần được cấu hình, còn `doLast` chỉ chạy khi task được thực thi.
- `doLast { task -> ... }` nhận task thực tế qua tham số của action, vì vậy không phải đoán `owner`/`delegate` để biết `task.name` và `task.path`.
- `build` biên dịch/đóng gói ứng dụng nhưng **không tự gọi** `showConfiguration` hoặc `run` trừ khi bạn cấu hình task dependency khác.

## 6. Configuration closure khác action closure

Hai đoạn sau đều có `{ }` nhưng chức năng khác nhau:

~~~groovy
tasks.register('hello') {
    group = 'help'              // Cấu hình Task
    description = 'In lời chào'

    doLast { task ->            // Action chạy khi task thực thi
        println 'Hello from ' + task.path
    }
}
~~~

| Vị trí | Cách hiểu | Thời điểm chạy |
| --- | --- | --- |
| Closure của `tasks.register('hello') { ... }` | Cấu hình task, khai báo properties và actions | Khi task được **realize/configure** (có thể được trì hoãn bởi API lazy) |
| Closure của `doLast { task -> ... }` | Action thực thi, thực hiện công việc của task | Khi task `hello` được chạy và không bị bỏ qua |
| Closure của `repositories { ... }` | Cấu hình mô hình kho dependency | Trong configuration của build, theo lifecycle API tương ứng |
| Closure của `dependencies { ... }` | Cấu hình graph khai báo dependency | Trong configuration của build |
| Closure trong `provider { ... }` | Tạo phép tính lười (deferred) của Provider API | Khi provider cần giá trị, theo ngữ nghĩa API và ràng buộc Gradle |

Không thể nhận diện “chạy khi nào” chỉ bằng dấu ngoặc nhọn. Phải xác định **API nhận closure** và Gradle sẽ gọi nó lúc nào.

### 6.1. Tránh hiệu ứng phụ trong configuration

Sai mục tiêu nếu chỉ muốn ghi file khi task chạy:

~~~groovy
tasks.register('writeGreeting') {
    def outFile = file('greeting.txt')
    outFile.text = 'Xin chào'
}
~~~

Phần ghi file đặt ngay trong closure cấu hình task. Nó có thể xảy ra **khi task được cấu hình**, dù chưa đến giai đoạn execution; với lazy configuration, còn có nguy cơ thời điểm xảy ra không như người viết tưởng. Đó cũng không phải thiết kế task có input/output rõ ràng.

Phiên bản tối thiểu minh họa đúng thời điểm hành động:

~~~groovy
tasks.register('writeGreeting') {
    doLast {
        def outFile = layout.buildDirectory.file('greeting.txt').get().asFile
        outFile.parentFile.mkdirs()
        outFile.text = 'Xin chào'
        println outFile.name
    }
}
~~~

Khi chạy `./gradlew writeGreeting`, task tạo `build/greeting.txt` và in `greeting.txt`. Để dùng trong build thực tế có cache, cần **khai báo output** bằng `outputs.file(...)` hoặc tốt hơn là tạo task type có `@OutputFile`, input/provider rõ ràng; ví dụ ngắn chỉ làm rõ khác biệt configuration/action. Không nên đọc biến môi trường tùy tiện hoặc gọi mạng trong configuration closure.

### 6.2. API lazy: `register`, `named`, `configureEach`

~~~groovy
tasks.register('alpha') {
    doLast {
        println 'alpha'
    }
}

tasks.register('beta') {
    dependsOn tasks.named('alpha')
    doLast {
        println 'beta'
    }
}

tasks.withType(Test).configureEach {
    testLogging {
        events 'passed', 'failed'
    }
}
~~~

Đoạn ví dụ cuối (`Test`) yêu cầu plugin `java`/`application` cung cấp task `Test`; thêm nó vào một script đang có Java plugin, **không** chỉ sao chép tách rời. `configureEach` áp dụng cấu hình khi các task phù hợp được realize mà không ép cấu hình toàn bộ ngay lập tức. `named('alpha')` trả provider của task đã đăng ký, giúp khai báo dependency không cần lấy instance sớm.

Thay `tasks.register` bằng `tasks.create` hoặc `task alpha` chỉ vì muốn closure “chạy ngay” thường làm tăng chi phí configuration không cần thiết. Cách viết DSL đẹp không đồng nghĩa với task graph hiệu quả.

## 7. Vì sao implicit delegate gây nhầm lẫn và cách viết rõ ràng

### 7.1. Nhầm thuộc tính của project với thuộc tính task

~~~groovy
version = '1.0'

tasks.register('inspect') {
    doLast { task ->
        println task.project.version  // Version của Project
        println task.name             // Tên Task
    }
}
~~~

`Project.version` và `Task.name` là hai model property khác nhau. Khi trùng tên/không chắc object đích, dùng **chủ ngữ tường minh**, chẳng hạn `project.version`, `task.name`, `task.project.name`. Không coi việc một biến nằm “bên trong `tasks.register`” là đủ để giải thích mọi property không định danh trong các closure lồng nhau.

### 7.2. Nhầm dependency của project với dependency của task

~~~groovy
plugins {
    id 'java'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.apache.commons:commons-lang3:3.17.0'
}

tasks.register('verifyDocs') {
    doLast {
        println 'docs ok'
    }
}

tasks.named('check') {
    dependsOn tasks.named('verifyDocs')
}
~~~

- `dependencies { implementation '...' }`: thêm **thư viện** vào configuration của project; `implementation` không phải method trên Task.
- `dependsOn tasks.named('verifyDocs')`: thêm **quan hệ phụ thuộc giữa các task** trong graph thực thi; không thêm thư viện Java vào classpath.

Cùng chữ “dependency” nhưng khác model. Đây là lỗi tư duy thường gặp khi đọc DSL theo từ khóa thay vì theo đối tượng được cấu hình.

### 7.3. Một tên có thể bị biến lexical che khuất

~~~groovy
def name = 'LOCAL'
def closure = { -> name }
closure.delegate = [name: 'DELEGATE']
closure.resolveStrategy = Closure.DELEGATE_FIRST

assert closure() == 'LOCAL'
~~~

Trong một build script phức tạp, đặt tên biến cục bộ trùng với property của extension có thể khiến kết quả rất khó đọc. Ưu tiên tên biến rõ nghĩa, và khi cần cấu hình object cụ thể hãy dùng API tường minh/đối tượng được cung cấp làm tham số thay cho dựa vào phép lookup động.

### 7.4. Không tự sửa `delegate` của closure do Gradle nhận để “chữa lỗi”

Mẫu như `myClosure.delegate = project` hoặc `myClosure.resolveStrategy = Closure.DELEGATE_ONLY` có giá trị trong **bài thực hành Groovy thuần**, nhưng không nên tùy tiện áp dụng cho configuration closure mà Gradle quản lý. Gradle và plugin có thể thiết lập cơ chế cấu hình/ủy quyền riêng, thêm extension động hoặc adapter. Sửa closure bên ngoài hợp đồng API dễ làm thay đổi ý nghĩa/tạo lỗi âm thầm.

Khi muốn cấu hình, hãy ưu tiên:
- Các block được API chính thức công bố (`java {}`, `publishing {}`, `tasks.register {}`).
- Truy cập đối tượng tường minh (`project`, `tasks.named(...)`, `extensions.getByType(...)` khi thật sự cần).
- Container API, Provider API và convention plugin thay vì mẹo delegate động.
- Đọc thông báo lỗi kèm **đúng vị trí script và đối tượng** nó nêu.

## 8. Một vài khối đặc biệt: `plugins {}`, `settings.gradle` và `pluginManagement {}`

**`plugins {}` không phải sandbox Groovy tự do.** Đây là plugin DSL có cú pháp cố ý hạn chế để Gradle giải quyết plugin sớm, ổn định; thông thường dùng ở cấp top-level của `build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'application'
}
~~~

Không đưa vòng lặp, lệnh `println`, điều kiện tùy ý hoặc biến động vào block này rồi kỳ vọng nó hoạt động như một closure Groovy thông thường. `id`/`version` trong plugin block tuân thủ những quy tắc riêng của Gradle. Nếu cần version plugin được quản lý tập trung, dùng `pluginManagement` ở settings hoặc version catalog theo hướng dẫn chính thức.

**`settings.gradle` cấu hình Settings, không phải Project.** Ví dụ:

~~~groovy
pluginManagement {
    repositories {
        gradlePluginPortal()
    }
}

rootProject.name = 'multi-sample'
include 'app', 'core'
~~~

- `pluginManagement { repositories {} }` cấu hình nơi **tìm plugin**.
- `repositories { mavenCentral() }` trong `build.gradle` cấu hình nơi **tìm dependency của project** (trừ khi có chính sách repository tập trung khác).
- `include 'app', 'core'` là lời gọi thuộc mô hình Settings.
- `rootProject.name` trong settings chỉ tên root build; không phải cách đặt tên một task.

Điều này giải thích vì sao cùng chữ `repositories` nhưng target và mục đích có thể khác, tùy đang ở file Settings hay Project và nằm trong block nào.

**Kotlin DSL là hệ khác:** `build.gradle.kts` dùng Kotlin lambda có receiver/type checking tĩnh; không áp dụng trực tiếp các thuộc tính Groovy `owner`, `delegate`, `resolveStrategy` cho lambda Kotlin. Đừng chuyển ví dụ Groovy sang Kotlin bằng cách chỉ đổi dấu nháy hoặc thêm ngoặc.

## 9. Cách tự xác định delegate/đối tượng đích khi đọc một DSL lạ

Thay vì đoán, dùng thứ tự kiểm tra sau:

1. **Đọc file và cấp thực thi:** `settings.gradle` hay `build.gradle`? Root project hay subproject? Đang ở configuration hay action?
2. **Xác định method nhận closure:** `repositories`, `dependencies`, `java`, `tasks.register`, `withType`, `doLast` hay API của plugin bên thứ ba?
3. **Tra API/DSL reference của method:** Nó nhận `Closure`, `Action<T>`, configuration block hay provider? Model type `T` là gì?
4. **Xác định plugin tạo extension/configuration:** `java {}` và `implementation` có tồn tại nếu plugin tương ứng chưa áp dụng không?
5. **Theo dõi từng tầng lồng:** Ở mỗi `{ }`, mô hình có thể đổi target. Không mang nguyên giả định từ khối ngoài vào khối trong.
6. **Xử lý tên mơ hồ bằng truy cập tường minh:** `project.version`, `task.path`, `repositories.mavenCentral()` trong ngữ cảnh phù hợp, `java.toolchain` hoặc tham số action.
7. **Chạy quan sát có mục đích:** dùng task riêng để in `task.path`/`project.name`; đối với closure **do bạn sở hữu**, có thể tạm in `owner`/`delegate`/`resolveStrategy`, rồi bỏ log khi xong.
8. **Đọc lỗi đúng project/line:** thông báo “unknown property” hoặc “Could not find method” thường gợi ý tên bị lookup trên object nào.

Ví dụ script **thăm dò có chủ đích**, thêm vào build đã áp dụng `base` hoặc plugin Java:

~~~groovy
tasks.register('inspectTask') {
    doLast { task ->
        println 'Class: ' + task.getClass().getName()
        println 'Project: ' + task.project.path
        println 'Task: ' + task.path
    }
}
~~~

Lệnh `./gradlew inspectTask` cho biết object `Task` mà action nhận và project chứa nó. Tên class Task có thể là class nội bộ/decorated class khác nhau giữa phiên bản Gradle, vì vậy không chép cố định dòng `Class: ...` thành kỳ vọng. Hai dòng `Project: :` và `Task: :inspectTask` là kết quả khi chạy ở **root project**.

## 10. Lỗi thường gặp và cách sửa

| Triệu chứng | Nguyên nhân thường gặp | Hướng sửa |
| --- | --- | --- |
| `Could not find method implementation()` | Gọi `implementation` khi plugin chưa tạo configuration, hoặc gọi sai vị trí | Áp dụng plugin Java phù hợp; đặt khai báo trong `dependencies { }`; kiểm tra configuration có tồn tại |
| `Could not find method mavenCentral()` | Gọi `mavenCentral()` ở object không phải `RepositoryHandler` | Đặt trong `repositories { }` thích hợp; phân biệt settings/plugin repositories với project repositories |
| `Could not get unknown property 'mainClass'` | Đặt property ngoài application extension hoặc thiếu plugin | Áp dụng `application` và đặt `application { mainClass = '...' }` |
| `Could not find method toolchain()` | Thiếu Java plugin hoặc sai target/configuration block | Kiểm tra `plugins { id 'java' }` và `java { toolchain { ... } }` |
| Gán `version` mà giá trị không thuộc object mong muốn | Tên property bị resolve theo closure không như dự tính | Chỉ rõ `project.version` hoặc object extension/task phù hợp; xem lexical scope |
| Gọi `doLast` trong block cấu hình extension không phải Task | Nhầm action API của task với extension configuration | Đăng ký task qua `tasks.register(...)` rồi thêm `doLast` ở đó |
| Task chạy code sớm dù chỉ muốn chạy lúc thực thi | Đặt hiệu ứng phụ trong configuration closure | Đưa hành động vào task action; khai báo input/output cho task có sản phẩm |
| Task nào cũng được realize khi cấu hình | Dùng `tasks.create`, `tasks.all` hoặc API eager | Ưu tiên `register`, `named`, `configureEach` |
| `MissingPropertyException` dù delegate có property giống tên biến | Biến lexical bị capture hoặc strategy/owner khác dự tính | Kiểm tra scope biến; gọi object tường minh |
| `plugins {}` báo lỗi cú pháp với lệnh Groovy bình thường | Plugin DSL hạn chế cú pháp | Dùng các khai báo plugin hợp lệ, quản lý plugin version qua settings/catalog |
| Đoạn Groovy chạy trong `build.gradle` nhưng sai khi dán sang `build.gradle.kts` | Groovy closure khác Kotlin lambda | Viết lại theo Kotlin DSL và type-safe receiver |
| `:app` xử lý nhầm cấu hình của root | Nhầm project đích khi dùng root/subproject | Cấu hình trong `app/build.gradle` hoặc trỏ đúng `project(':app')`; tránh phụ thuộc vào delegate tình cờ |

Không “chữa” mọi lỗi bằng `clean`: lỗi phân giải property/method xảy ra khi cấu hình model, không được sửa bằng việc xóa output biên dịch.

## 11. Luyện tập theo mức độ

### Bài 1: Đọc closure và dự đoán output

~~~groovy
class Person {
    String name = 'OWNER'
    Closure buildMessage() {
        return { -> 'Hello ' + name }
    }
}
def action = new Person().buildMessage()
action.delegate = [name: 'DELEGATE']
println action()
action.resolveStrategy = Closure.DELEGATE_FIRST
println action()
~~~

**Đáp án:**

~~~text
Hello OWNER
Hello DELEGATE
~~~

Vì `name` là property được tra trên owner và delegate theo resolveStrategy. Thử đổi thân closure thành `{ -> def name = 'LOCAL'; 'Hello ' + name }` thì cả hai dòng đều là `Hello LOCAL` do `name` lúc này là biến local trong closure.

### Bài 2: Đọc cấu hình theo object

~~~groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'demo.App'
}
~~~

Hãy chỉ ra:
- Ai cung cấp `application` extension? **Application plugin**.
- `mavenCentral()` thuộc API của ai? **RepositoryHandler**.
- `languageVersion` thuộc về ai? **Java toolchain spec**.
- `mainClass` thuộc về ai? **Application extension**.
- Điều gì xảy ra nếu bỏ `id 'application'` mà vẫn giữ `application { }`? **Extension không còn được plugin tạo**, cấu hình sẽ thất bại trừ khi một plugin khác tự định nghĩa extension cùng tên.

### Bài 3: Dự đoán lúc task chạy

~~~groovy
tasks.register('sample') {
    description = 'Một task có action'
    doLast {
        println 'ACTION'
    }
}
~~~

Chạy `./gradlew help` rồi `./gradlew sample`. Với `tasks.register` và không có mã eager khác khiến task được realize sớm, `help` không cần thực thi action của `sample`. Khi chạy `sample`, action mới in dòng `ACTION`.

### Bài 4: Phân biệt hai loại dependency

~~~groovy
dependencies {
    testImplementation 'org.junit.jupiter:junit-jupiter:5.11.4'
}

tasks.named('check') {
    dependsOn tasks.named('test')
}
~~~

Giải thích `testImplementation` thêm gì vào classpath và `dependsOn` thêm gì vào task graph. **Đáp án:** `testImplementation` khai báo thư viện ngoài cho test; `dependsOn` khai báo quan hệ thứ tự/chạy task. Đoạn này cần Java plugin để có `testImplementation`, `check` và `test`. Java plugin đã nối `check -> test` mặc định nên dòng `dependsOn` ở ví dụ này **không cần thiết trong cấu hình Java chuẩn**; nó chỉ giúp đối chiếu hai khái niệm.

### Bài 5: Đọc một plugin DSL lạ

Gặp một plugin có block `foo { bar { baz = 1 } }`, **không** khẳng định ngay `foo`/`bar`/`baz` là property của Project. Tìm tài liệu plugin để xác định:
- Plugin id, nơi áp dụng và thời điểm tạo extension `foo`.
- Kiểu object mà `foo` và `bar` cấu hình.
- `baz` là property nào, loại dữ liệu gì, có dùng `Property<T>`/Provider API không?
- Có tương thích configuration cache và task configuration avoidance không?

Đạt bài học khi bạn giải thích được đối tượng sở hữu từng dòng của một `build.gradle` không cần đoán theo độ thụt lề.

## 12. Tóm tắt mô hình áp dụng

**Từ dưới lên:** closure là object có mã; Groovy tra tên không định danh theo lexical scope và cơ chế owner/delegate; Gradle cung cấp những configuration API dùng closure để thay đổi mô hình Project/Settings/Task/extension; plugin thêm các khối và thuộc tính; lifecycle Gradle quyết định closure cấu hình hoặc action thực thi chạy khi nào.

Một câu hỏi cần tự đặt trước mọi block:

> “**Ai nhận closure này, object nào được cấu hình, và những dòng bên trong chạy ở phase nào?**”

Nếu trả lời được đủ ba ý, bạn sẽ hiểu phần lớn những đoạn Groovy DSL trông như “ngôn ngữ bí mật”, tránh nhầm `Project` với `Task`, tránh dùng sai property trong nested closure và viết được build script dễ kiểm soát.

## Tài liệu đối chiếu

- [Apache Groovy — Closures](https://groovy-lang.org/closures.html): `this`, `owner`, `delegate`, resolution strategy và lexical capture.
- [Groovy Closure API](https://docs.groovy-lang.org/docs/groovy-latest/html/api/groovy/lang/Closure.html): ý nghĩa chính xác của các hằng `OWNER_FIRST`, `DELEGATE_FIRST`, `DELEGATE_ONLY`.
- [Gradle — Writing Build Scripts](https://docs.gradle.org/current/userguide/writing_build_scripts_intermediate.html): closure và đối tượng được cấu hình trong DSL.
- [Gradle — Writing Settings Files](https://docs.gradle.org/current/userguide/writing_settings_files.html): Settings, project và các block tương ứng.
- [Gradle — Working with Plugins](https://docs.gradle.org/current/userguide/plugins_intermediate.html): ràng buộc đặc biệt của `plugins {}`.
- [Gradle — Avoiding Unnecessary Task Configuration](https://docs.gradle.org/current/userguide/task_configuration_avoidance.html): `register`, `named`, `configureEach`.
- [Gradle — Groovy DSL Reference](https://docs.gradle.org/current/dsl/): tra method/property và type cho từng đối tượng DSL.
