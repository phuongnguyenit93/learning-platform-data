# Cú pháp Groovy cần thiết để đọc và viết build script Gradle

## 1. Groovy DSL là gì và cần học đến mức nào?

Gradle hỗ trợ viết script bằng **Groovy DSL** (tệp `build.gradle`, `settings.gradle`) hoặc **Kotlin DSL** (tệp `build.gradle.kts`, `settings.gradle.kts`). Với Groovy DSL, các biểu thức như `plugins { id 'java' }`, `repositories { mavenCentral() }` và `tasks.register('hello') { ... }` đều dựa trên **ngôn ngữ Groovy kết hợp API của Gradle**.

Để đọc và viết build script, bạn cần nắm những phần Groovy thực sự xuất hiện trong cấu hình build: biểu thức, biến, chuỗi, danh sách/map, gọi phương thức, closure, cách tra cứu thuộc tính và phạm vi thực thi. Không cần học toàn bộ lập trình hướng đối tượng hay metaprogramming của Groovy trước khi dùng Gradle.

**Sau bài học, bạn có thể:**

- Đọc được cấu trúc một `build.gradle` và hiểu cú pháp Groovy đằng sau từng khối cấu hình.
- Phân biệt thứ thuộc **ngôn ngữ Groovy** (`def`, list/map, closure, nội suy chuỗi) với thứ thuộc **API/Plugin Gradle** (`plugins`, `dependencies`, `tasks.register`, `doLast`).
- Viết một task đơn giản, cấu hình plugin và dependency, dùng biến/collection mà không gây lỗi phạm vi.
- Hiểu vì sao cùng một dấu `{ ... }` có lúc dùng để **cấu hình**, có lúc dùng để **chạy action** của task.
- Biết cách đọc tài liệu Gradle để xác định đối tượng chịu trách nhiệm cho một thuộc tính/phương thức.

## 2. Ngữ cảnh của script: `settings.gradle` khác `build.gradle`

Cả hai đều có cú pháp Groovy nhưng cấu hình **đối tượng khác nhau**:

| Tệp | Đối tượng chính | Trách nhiệm điển hình |
| --- | --- | --- |
| `settings.gradle` | `Settings` | Đặt tên build gốc, khai báo project con, quản lý plugin/dependency repositories ở cấp settings khi cần. |
| `build.gradle` tại project gốc | `Project` tương ứng với `:` | Áp dụng plugin, khai báo dependency, thiết lập group/version, đăng ký task cho project gốc. |
| `app/build.gradle` | `Project` tương ứng với `:app` | Cấu hình plugin, dependency, task riêng của project `:app`. |

Ví dụ, trong `settings.gradle`:

```groovy
rootProject.name = 'groovy-dsl-lab'
include 'app'
```

Ở đây `rootProject` và `include` là API của **Settings**. Trong `app/build.gradle`:

```groovy
plugins {
    id 'java'
}

group = 'org.example'
version = '1.0.0'
```

`plugins`, `group` và `version` thuộc ngữ cảnh cấu hình của **Project**. Những dòng này không phải từ khóa của bản thân ngôn ngữ Groovy. Lệnh `./gradlew :app:tasks` truy vấn task của project `:app`, còn `./gradlew tasks` mặc định bắt đầu từ project hiện hành (thường là root khi chạy tại thư mục gốc).

## 3. Cú pháp cơ bản: câu lệnh, chú thích, biến và kiểu

Groovy gần Java về biểu thức nhưng ít dấu câu hơn. Dấu chấm phẩy cuối câu thường **không bắt buộc**, chuỗi có thể dùng nháy đơn, và Groovy cho phép khai báo biến bằng `def`.

```groovy
// Đây là chú thích một dòng.
/*
   Đây là chú thích
   nhiều dòng.
*/
def count = 3             // Biến local, kiểu suy ra động.
String title = 'Gradle'   // Biến có khai báo kiểu rõ ràng.
boolean enabled = true
def rate = 1.5

count += 2
println "count=${count}"   // count=5
```

- `def` khai báo biến local trong phạm vi script/block/method. `def` **không đồng nghĩa** với khai báo thuộc tính của `Project`.
- Các kiểu thường gặp: `String`, `int`/`Integer`, `boolean`/`Boolean`, `List`, `Map`, `File`. Groovy cũng hỗ trợ kiểu tĩnh khi cần.
- Toán tử `+`, `-`, `*`, `/`, `%`; phép so sánh `==`, `!=`, `<`, `>`; toán tử logic `&&`, `||`, `!` hoạt động theo quy tắc của Groovy.
- Gán thuộc tính dùng `=`: `version = '1.0.0'`. Truy cập thuộc tính dùng dấu chấm: `project.version`, `tasks.named('build')`.
- Có thể dùng `if`, `for` và phép lặp Groovy, nhưng hạn chế logic phức tạp chạy sớm trong giai đoạn cấu hình build.

Ví dụ điều kiện và vòng lặp:

```groovy
def profiles = ['dev', 'test', 'prod']

if (profiles.contains('prod')) {
    println 'Có profile prod'
}

profiles.each { profile ->
    println "profile=${profile}"
}
```

Ở cấp trên cùng của `build.gradle`, các lệnh `println` này chạy **khi Gradle đánh giá script để cấu hình build**, không đợi đến lúc một task tùy biến được thực thi.

### Groovy truth: giá trị nào được xem là đúng?

Trong điều kiện `if`, Groovy có cách chuyển đổi giá trị sang boolean (thường gọi là *Groovy truth*): `null`, `false`, số `0`, chuỗi rỗng và collection rỗng thường được xem là false; các giá trị phù hợp khác là true.

```groovy
def options = [enabled: false, retries: 0]

if (!options.enabled) {
    println 'Tính năng đang tắt'
}

def retries = options.retries ?: 3
// retries là 3 vì 0 bị xem là false.
```

**Lỗi hay gặp:** dùng `value ?: defaultValue` khi `0`, `false` hoặc chuỗi rỗng lại là giá trị hợp lệ. Nếu chỉ muốn thay khi `null`, viết điều kiện rõ ràng: `value != null ? value : defaultValue`.

## 4. Chuỗi: nháy đơn, nháy kép, GString và escape

Đây là khác biệt quan trọng trong Groovy:

| Cú pháp | Ý nghĩa |
| --- | --- |
| `'hello'` | Chuỗi thông thường, **không nội suy** biến. |
| `"hello"` | Chuỗi có thể nội suy `${expression}` hoặc `$variable`, tạo `GString` khi có nội suy. |
| `'''...'''` | Chuỗi nhiều dòng, không nội suy. |
| `"""..."""` | Chuỗi nhiều dòng, có thể nội suy. |
| `'\n'` | Cách viết chứa ký tự xuống dòng theo quy tắc escape của Groovy. |
| `'\$'` trong chuỗi nháy kép | Dùng dấu gạch chéo ngược trước `$` khi muốn in dấu `$` thay vì nội suy. |

Ví dụ:

```groovy
def moduleName = 'core'

println 'Module: ${moduleName}'
println "Module: ${moduleName}"
println "Uppercase: ${moduleName.toUpperCase()}"
```

Phần output do ba dòng `println` tạo ra:

```text
Module: ${moduleName}
Module: core
Uppercase: CORE
```

**Lưu ý thời điểm đánh giá:** nếu tạo chuỗi `"version=${version}"` ở cấp script, biểu thức nội suy được đánh giá khi tạo chuỗi. Nó không tự động cập nhật mỗi khi một giá trị cấu hình thay đổi sau này. Với dữ liệu Gradle có tính trì hoãn, ưu tiên `Provider` (mục 9) thay vì nội suy giá trị quá sớm.

**Đường dẫn:** dùng dấu `/` trong đường dẫn tương đối để dễ dùng đa nền tảng, ví dụ `file('src/main/java')`. Nếu phải viết đường dẫn Windows chứa `\` trong literal, cần escape thích hợp, chẳng hạn `'C:\\work\\demo'`; không ghép đường dẫn bằng cách đoán dấu phân cách khi API Gradle đã có `file(...)` hoặc `layout`.

## 5. List và Map: dạng dữ liệu xuất hiện khắp build script

`List` biểu diễn một dãy có thứ tự, `Map` là các cặp khóa–giá trị. Dấu `[]` biểu diễn list rỗng; `[:]` biểu diễn map rỗng.

```groovy
def stages = ['dev', 'test', 'prod']
def retriesByStage = [dev: 1, test: 2, prod: 3]
def emptyList = []
def emptyMap = [:]

println stages[0]                      // dev
println stages.size()                   // 3
println retriesByStage.prod             // 3
println retriesByStage['test']          // 2
println stages.join(', ')               // dev, test, prod
```

Trong `[dev: 1]`, khóa `dev` được hiểu là chuỗi `'dev'`. Nếu khóa được tính bằng một biểu thức/biến, hãy dùng cú pháp khóa động của Groovy hoặc tạo map qua phép gán rõ ràng; đừng mặc định `[variable: value]` sẽ đọc giá trị của biến `variable`.

Các thao tác hữu ích là `each` (duyệt), `collect` (biến đổi), `findAll` (lọc):

```groovy
def numbers = [1, 2, 3, 4]

def doubled = numbers.collect { n -> n * 2 }
def even = numbers.findAll { it % 2 == 0 }

println doubled                        // [2, 4, 6, 8]
println even                           // [2, 4]
```

`it` là tham số ngầm khi closure có đúng một đối số và bạn không đặt tên cho đối số đó. Khi cần rõ ràng, viết `{ n -> n * 2 }`. Map cũng có thể chứa các tùy chọn cấu hình, nhưng **không phải mọi khối Gradle đều nhận map**; phải xem chữ ký API tương ứng.

## 6. Gọi phương thức: vì sao Gradle trông giống ngôn ngữ riêng?

Groovy cho phép bỏ cặp ngoặc tròn trong nhiều trường hợp gọi phương thức có tham số:

```groovy
println('Hello')
println 'Hello'

file('src/main/java')
tasks.named('build')
```

Trong Groovy DSL, các cách viết sau thể hiện cùng ý tưởng gọi một phương thức có tham số (với API cho phép):

```groovy
plugins {
    id 'java'
}

repositories {
    mavenCentral()
}
```

`id 'java'` là dạng rút gọn của gọi `id('java')`. `mavenCentral()` không cần đối số nên vẫn có `()`. Dạng `repositories { ... }` là lời gọi một phương thức, với **closure** `{ ... }` được truyền làm đối số cuối.

Ví dụ một khai báo dependency khi **đã áp dụng Java plugin**:

```groovy
repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.apache.commons:commons-lang3:3.17.0'
    testImplementation 'org.junit.jupiter:junit-jupiter:5.11.4'
}
```

Trong ví dụ này, `implementation '...'` tương ứng với `implementation('...')`. Hai tên `implementation` và `testImplementation` do các configuration/API Gradle được plugin Java cung cấp; **không phải hàm dựng sẵn của Groovy**. Khối `repositories` khai báo nơi Gradle có thể lấy module ngoài; việc resolve/download thực tế xảy ra khi build cần artifact. Đoạn này minh họa cú pháp và cần kết nối repository/cached artifact nếu chạy.

**Cách đọc một dòng DSL:** tìm tên được gọi, đối số của nó, closure cuối cùng (nếu có), rồi xác định đối tượng Gradle đang được cấu hình. Đừng đoán một từ là “từ khóa Groovy” chỉ vì nó không có dấu ngoặc.

## 7. Closure — chìa khóa để hiểu dấu `{ ... }`

Closure trong Groovy là một khối mã có thể truyền như một giá trị. Nó có thể có tham số tường minh, truy cập biến ở phạm vi ngoài và trả về giá trị của biểu thức cuối.

```groovy
def multiply = { int a, int b -> a * b }
def square = { int x -> x * x }
def upper = { it.toUpperCase() }

println multiply(3, 4)    // 12
println square(5)         // 25
println upper('gradle')   // GRADLE
```

Cú pháp:

- `{ ... }`: closure không viết tham số tường minh; nếu được gọi với một đối số, có thể truy cập đối số qua `it`.
- `{ x -> ... }`: đặt tên tham số.
- `{ a, b -> ... }`: nhiều tham số.
- `{ -> ... }`: tuyên bố closure không nhận tham số.
- `->`: ngăn cách danh sách tham số và phần thân.

Closure **khác với dấu ngoặc nhọn tạo khối thông thường** ở chỗ closure là đối tượng có thể truyền vào phương thức và được Gradle cấu hình/hoãn thực thi tùy API.

### Closure trong một build script được “delegate” cho đối tượng nào?

Xét:

```groovy
repositories {
    mavenCentral()
}

tasks.register('hello') {
    group = 'learning'
    description = 'In lời chào'
    doLast {
        println 'Hello from Gradle'
    }
}
```

- `repositories { ... }` cấu hình `RepositoryHandler`; `mavenCentral()` được tra cứu theo ngữ cảnh đối tượng đó.
- `tasks.register('hello') { ... }` cấu hình task `hello`; `group` và `description` là thuộc tính của task.
- `doLast { ... }` **đăng ký action** chạy khi task được thực thi; `println` ở bên trong được gọi lúc chạy action, không phải ngay khi đọc `build.gradle`.

Về mặt Groovy, closure có những khái niệm như `owner`, `thisObject` và `delegate`. Gradle sử dụng cơ chế cấu hình/ủy quyền để các method/property không ghi tên đối tượng vẫn được tìm đúng chỗ. Với tên mơ hồ hoặc bị trùng, hãy ghi rõ `project.version`, `tasks.named('hello')`, `project.file('...')` hoặc dùng biến cục bộ có tên rõ nghĩa. Tránh dựa vào hiệu ứng ngầm của nhiều tầng closure lồng nhau.

**Quy tắc quan trọng:** muốn biết bên trong một khối có những property/method nào, tra **API của đối tượng mà closure đang cấu hình**. `repositories` → `RepositoryHandler`; `dependencies` → `DependencyHandler`; `tasks.register` → `Task` (hoặc loại task cụ thể); `application` → extension của Application plugin.

## 8. Nhận diện cấu trúc thường gặp trong `build.gradle`

Đây là minh họa phần cú pháp của một project Java dùng Groovy DSL:

```groovy
plugins {
    id 'java'
}

group = 'org.example'
version = '1.0.0'

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.apache.commons:commons-lang3:3.17.0'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.named('compileJava') {
    options.encoding = 'UTF-8'
}
```

Đọc theo lớp:

| Biểu thức | Ý nghĩa trong Groovy | Ý nghĩa trong Gradle |
| --- | --- | --- |
| `plugins { ... }` | Gọi phương thức kèm closure. | Áp dụng plugin vào Project; khối `plugins` có các quy tắc cú pháp/giá trị hạn chế riêng. |
| `id 'java'` | Gọi phương thức bỏ ngoặc tròn. | Chọn plugin Java của Gradle. |
| `group = 'org.example'` | Gán thuộc tính. | Gán thuộc tính `group` cho Project. |
| `repositories { mavenCentral() }` | Closure lồng lời gọi không đối số. | Cấu hình nơi tìm module dependency. |
| `dependencies { implementation '...' }` | Gọi phương thức với chuỗi. | Khai báo module trong configuration `implementation`. |
| `java { toolchain { ... } }` | Closure lồng nhau, property assignment. | Cấu hình extension do Java plugin tạo ra. |
| `JavaLanguageVersion.of(17)` | Gọi phương thức tĩnh trên class. | Tạo giá trị phiên bản toolchain Java 17. |
| `tasks.named('compileJava') { ... }` | Gọi phương thức với chuỗi và closure. | Cấu hình task đã có theo cách trì hoãn (khi plugin Java tạo task đó). |

**Các giới hạn cần nhớ:**

1. Khối `plugins { }` có quy tắc Gradle riêng; không tự ý tính toán plugin id hoặc thêm các câu lệnh Groovy tùy ý bên trong. Để áp dụng plugin bên ngoài, theo cú pháp phiên bản và plugin repositories phù hợp.
2. Khối `java { ... }` và task `compileJava` chỉ có khi áp dụng plugin cung cấp chúng.
3. `implementation` không tồn tại như một configuration khai báo dependency của project thuần nếu chưa có plugin tạo nó.
4. Tùy API, thuộc tính có thể là giá trị thường hoặc `Property<T>`/`Provider<T>` của Gradle; hãy theo đúng kiểu cấu hình được tài liệu mô tả. Ví dụ `languageVersion = JavaLanguageVersion.of(17)` là gán vào property do Java toolchain hỗ trợ.
5. Các ví dụ không có nghĩa mọi plugin đều dùng chung khối/thuộc tính; Groovy chỉ cung cấp cú pháp, plugin mới quyết định DSL cụ thể.

## 9. Biến `def`, extra property và Provider của Gradle

Ba trường hợp này trông giống nhau nhưng có vòng đời và phạm vi khác nhau.

### Biến local bằng `def`

```groovy
def stageNames = ['dev', 'prod']
def releaseLabel = 'internal'
```

`stageNames` và `releaseLabel` là biến local của script; có thể được closure ở phạm vi phù hợp capture, nhưng **không tự trở thành thuộc tính của Project** và không nên dùng chúng như một API chia sẻ giữa các project.

### Extra properties do Gradle cung cấp

```groovy
ext.releaseLabel = 'internal'
println project.ext.releaseLabel
```

`ext` là extension của Gradle cho phép thêm thuộc tính động. Nó khác từ khóa `def` của Groovy. Dùng khi cần tương thích cấu hình hiện có; với cấu hình build phức tạp, extension có kiểu và `Provider` thường dễ kiểm tra hơn nhiều thuộc tính động.

### Provider cho giá trị có thể chỉ biết khi chạy

Ví dụ nhận thuộc tính từ command line `-Pstage=prod`:

```groovy
def stageProvider = providers.gradleProperty('stage').orElse('dev')

tasks.register('showStage') {
    doLast {
        println "stage=${stageProvider.get()}"
    }
}
```

Lệnh `./gradlew -q showStage` in `stage=dev` theo mặc định; `./gradlew -q showStage -Pstage=prod` in `stage=prod`. `stageProvider` là một `Provider<String>` (khái niệm của Gradle), không phải chuỗi Groovy thông thường. Việc dùng `get()` trong task action giúp tránh ép Gradle lấy giá trị sớm khi chưa cần; trong các API hỗ trợ Provider, ưu tiên **nối các Provider** với nhau thay vì gọi `get()` chỉ để chuyển chúng về chuỗi.

### Safe navigation và Elvis khi đọc dữ liệu tùy chọn

```groovy
def config = null
def timeout = config?.timeout       // null; không ném lỗi null dereference
def safeTimeout = timeout ?: 30      // 30
```

`?.` giúp truy cập an toàn khi đối tượng có thể `null`. `?:` chọn giá trị dự phòng theo Groovy truth; như đã nói, nó cũng thay `0`/`false`/giá trị rỗng. Đừng dùng `?:` khi cần phân biệt chính xác `null` với `false`.

## 10. Đăng ký task: cú pháp và thời điểm thực thi

Với task Gradle, phải phân biệt **cấu hình task** và **thực thi action**.

```groovy
tasks.register('greet') {
    group = 'learning'
    description = 'In lời chào khi được yêu cầu'

    doLast {
        println 'Xin chào từ task greet'
    }
}
```

`tasks.register('greet')` trả về `TaskProvider`, hỗ trợ Gradle trì hoãn việc hiện thực hóa/cấu hình task không cần thiết. Hai phép gán `group` và `description` thuộc phần cấu hình task; `doLast` gắn action sẽ chạy khi người dùng yêu cầu `greet`. Nếu task không nằm trong đồ thị thực thi, action không chạy.

Định nghĩa phụ thuộc giữa task:

```groovy
def prepare = tasks.register('prepare') {
    doLast {
        println 'prepare'
    }
}

tasks.register('runDemo') {
    dependsOn prepare
    doLast {
        println 'runDemo'
    }
}
```

Khi chạy `./gradlew -q runDemo`, output của hai action là:

```text
prepare
runDemo
```

`dependsOn prepare` được viết theo cú pháp gọi phương thức Groovy và sử dụng `TaskProvider` của Gradle. Có thể viết `dependsOn tasks.named('prepare')` nếu cần lấy task theo tên. Việc gọi `tasks.named('...') { ... }` để cấu hình task hiện có thường tốt hơn những dạng truy cập task theo tên có thể làm task được tạo quá sớm. `mustRunAfter` và `shouldRunAfter` chỉ quy định thứ tự nếu hai task cùng có trong đồ thị; chúng không mang nghĩa `dependsOn`.

**Hai tình huống dễ nhầm:**

```groovy
println 'Cấu hình build'              // Chạy khi script được đánh giá.

tasks.register('example') {
    println 'Cấu hình task'           // Chạy khi task được hiện thực hóa/cấu hình.
    doLast {
        println 'Thực thi task'       // Chạy khi action của task được thực thi.
    }
}
```

Không kết luận rằng dòng `println 'Cấu hình task'` chạy ngay khi Gradle nhìn thấy `tasks.register`: registration có thể trì hoãn cấu hình task. Muốn làm công việc có side effect lúc chạy, đặt nó vào task action/API task thích hợp, không đặt ở cấp script hoặc một configuration closure.

## 11. Ví dụ hoàn chỉnh: một build Groovy DSL chạy được

Ví dụ này cố ý chỉ dùng plugin `base` có sẵn trong Gradle, không cần tải thư viện Java bên ngoài. Dùng JDK 17+ và bản Gradle tương thích với JDK đang dùng. Từ thư mục `groovy-dsl-lab`, tạo đúng hai tệp sau.

**Tệp `settings.gradle`:**

```groovy
rootProject.name = 'groovy-dsl-lab'
```

**Tệp `build.gradle`:**

```groovy
plugins {
    id 'base'
}

group = 'org.example'
version = '1.0.0'

def environments = ['dev', 'staging', 'prod']
def retriesByEnv = [dev: 1, staging: 2, prod: 3]
def makeLabel = { String env ->
    "${env.toUpperCase()}-${project.version}"
}

tasks.register('inspectDsl') {
    group = 'learning'
    description = 'Minh họa cú pháp Groovy trong Gradle'

    doLast {
        def evenNumbers = [1, 2, 3, 4].findAll { it % 2 == 0 }

        println "project=${project.name}"
        println "envs=${environments.join(', ')}"
        println "retry.prod=${retriesByEnv.prod}"
        println "label=${makeLabel('prod')}"
        println "even=${evenNumbers.join(', ')}"
    }
}

def prepare = tasks.register('prepareDemo') {
    group = 'learning'
    doLast {
        println 'prepareDemo'
    }
}

tasks.register('runDemo') {
    group = 'learning'
    dependsOn prepare
    doLast {
        println 'runDemo'
    }
}

def stageProvider = providers.gradleProperty('stage').orElse('dev')
tasks.register('showStage') {
    group = 'learning'
    doLast {
        println "stage=${stageProvider.get()}"
    }
}
```

**Cách chạy trên macOS/Linux** (ở thư mục `groovy-dsl-lab`):

```bash
./gradlew -q inspectDsl
./gradlew -q runDemo
./gradlew -q showStage -Pstage=prod
```

Nếu chưa có Gradle Wrapper, dùng Gradle đã cài trên máy chạy `gradle wrapper` một lần để tạo `gradlew`, `gradlew.bat` và các file wrapper. Lần đầu sử dụng wrapper có thể cần tải Gradle distribution đã cấu hình. Trên Windows chạy `gradlew.bat -q inspectDsl` và các lệnh tương tự.

**Output của `./gradlew -q inspectDsl`:**

```text
project=groovy-dsl-lab
envs=dev, staging, prod
retry.prod=3
label=PROD-1.0.0
even=2, 4
```

**Output của `./gradlew -q runDemo`:**

```text
prepareDemo
runDemo
```

**Output của `./gradlew -q showStage -Pstage=prod`:**

```text
stage=prod
```

Điều gì vừa xảy ra?

1. `plugins { id 'base' }` áp dụng một plugin có sẵn; bản thân `id` là lời gọi method trong DSL Gradle.
2. `group` và `version` gán các thuộc tính của root Project.
3. `environments` là `List`, `retriesByEnv` là `Map`, `makeLabel` là closure capture giá trị version của Project khi được gọi.
4. `inspectDsl` minh họa truy cập property, nội suy chuỗi, `findAll`, tham số ngầm `it` và gọi closure.
5. `runDemo` phụ thuộc vào `prepareDemo`: thứ tự action do đồ thị task quyết định, không phụ thuộc vị trí khai báo trong script.
6. `showStage` nhận command-line project property thông qua Provider và đọc nó khi chạy action.
7. `-q` làm gọn log Gradle; các dòng ở trên là output do mã `println` tạo ra. Cấu hình hệ thống hoặc plugin khác vẫn có thể in thông tin riêng nếu người dùng bổ sung chúng.

Ví dụ không chứa mã Java, vì mục tiêu là **đọc và viết cú pháp Groovy của build script**. Đối với Java/Spring Boot thực tế, plugin sẽ bổ sung thêm `sourceSets`, Java toolchain, dependency configurations và các task tương ứng.

## 12. Cách đọc và sửa một build script thực tế

Khi gặp một đoạn DSL chưa hiểu, đi theo thứ tự sau:

1. **Xác định tệp và project:** `settings.gradle` hay `build.gradle`? Project gốc hay module con? Đối tượng `Settings` hay `Project` đang được cấu hình?
2. **Nhìn vào dấu câu:** `foo = x` là gán property; `foo(...)` hoặc `foo x` thường là gọi method; `foo { ... }` là gọi method kèm closure.
3. **Tìm plugin:** `java`, `application`, `java-library` và plugin cộng đồng có thể tạo ra các khối DSL, configuration hoặc task khác nhau.
4. **Tìm đối tượng delegate của closure:** bên trong `repositories` là repository handler, bên trong `tasks.register` là task; bên trong `dependencies` là dependency handler.
5. **Kiểm tra phạm vi biến:** `def` local, `ext` của Gradle, project property và `Provider` có ý nghĩa khác nhau; tránh đặt cùng tên dẫn đến tra cứu nhầm.
6. **Kiểm tra thời điểm thực thi:** phần cấp script, configuration closure, task action và dữ liệu Provider không chạy/lấy giá trị cùng thời điểm.
7. **Đối chiếu Gradle API:** nếu không chắc một phương thức/thuộc tính, kiểm tra tài liệu của loại object đang cấu hình trước khi sửa.

Một số lệnh hỗ trợ quan sát:

```bash
./gradlew help
./gradlew tasks --all
./gradlew properties
./gradlew -q inspectDsl
./gradlew runDemo --dry-run
./gradlew inspectDsl --stacktrace
```

`--dry-run` cho thấy các task Gradle dự định chạy nhưng không thực thi action; vì vậy không thấy output `println` trong action là bình thường. `--stacktrace` hiển thị stack trace khi một lệnh lỗi (không tự gây lỗi để in stack trace). `tasks --all` giúp biết task nào thực sự được plugin/script tạo ra.

## 13. Lỗi Groovy/Gradle thường gặp

| Triệu chứng | Nguyên nhân hay gặp | Cách khắc phục |
| --- | --- | --- |
| `Could not find method implementation()` | Chưa áp dụng plugin cung cấp configuration `implementation`, viết sai tên hoặc gọi sai ngữ cảnh. | Kiểm tra `plugins { id 'java' }` hoặc plugin tương đương và vị trí khối `dependencies`. |
| `Could not get unknown property 'foo'` | Sai chính tả, biến `def` ngoài phạm vi, hoặc gán nhầm ngữ cảnh delegate. | Xác định object hiện hành; dùng `project.foo`/biến đúng phạm vi khi phù hợp. |
| Nhầm `'${name}'` với `"${name}"` | Nháy đơn không nội suy biến. | Dùng nháy kép khi cần nội suy, hoặc nối chuỗi một cách rõ ràng. |
| `plugins` từ chối một biểu thức Groovy động | Khối này có ràng buộc cú pháp Gradle riêng. | Dùng literal/biểu thức hợp lệ theo tài liệu plugins DSL; đừng đặt vòng lặp hay method tùy ý trong đó. |
| Task in ra chữ ngay khi `gradle help` | `println` nằm ở cấp script/cấu hình thay vì action. | Đưa side effect cần chạy vào `doLast` hoặc task có loại phù hợp. |
| Task không thấy khi chạy | Đăng ký vào project khác hoặc dùng sai tên/path task. | Dùng `./gradlew tasks --all` hoặc `./gradlew :module:tasks --all` để kiểm tra. |
| `val`, `fun` hoặc cú pháp `tasks.register<T>` bị báo lỗi | Đã dán Kotlin DSL vào `build.gradle` Groovy. | Chọn cú pháp đúng với đuôi `.gradle`; Kotlin DSL dùng `.gradle.kts`. |
| `0`/`false` bị thay bằng giá trị mặc định | Dùng Elvis `?:` với Groovy truth. | Dùng kiểm tra `null` tường minh nếu 0/false hợp lệ. |
| Truy cập `tasks.getByName(...)` làm cấu hình chậm | Ép hiện thực hóa task sớm. | Ưu tiên `tasks.register(...)`, `tasks.named(...)` và `configureEach` theo API. |
| Build chạy được nhưng sai khi thay thứ tự cấu hình | Truy cập giá trị sớm hoặc giả định một closure luôn chạy ngay. | Dựa vào Provider, task graph và API trì hoãn cấu hình; hạn chế logic ở cấp script. |
| Dependency ngoài không resolve được | Thiếu repository, sai tọa độ/version, offline hoặc mạng không sẵn. | Khai báo repository phù hợp và kiểm tra dependency resolution. |

### Hai ví dụ cần tránh vì dễ hiểu sai

**Ví dụ A: nội suy quá sớm trong cấu hình.**

```groovy
def snapshot = "version=${project.version}"
version = '2.0.0'

tasks.register('printSnapshot') {
    doLast {
        println snapshot
    }
}
```

Trong script thông thường, `snapshot` được tạo trước khi `version` được gán `2.0.0`. Nó phản ánh version tại **thời điểm tạo chuỗi**, không tự biến thành `version=2.0.0` về sau. Nếu muốn lấy version khi action chạy, đọc `project.version` bên trong action hoặc dùng Provider/configuration API phù hợp.

**Ví dụ B: nhầm dependency của phần mềm với phụ thuộc của task.**

```groovy
dependencies {
    implementation project(':core')
}

tasks.register('afterCompile') {
    dependsOn tasks.named('compileJava')
    doLast {
        println 'Đã qua bước compileJava'
    }
}
```

`implementation project(':core')` khai báo dependency project cho classpath; `dependsOn tasks.named('compileJava')` khai báo quan hệ thực thi giữa hai task. Đoạn này chỉ hợp lệ khi `:core` đã được khai báo trong `settings.gradle` và plugin của project hiện tại cung cấp `implementation`/`compileJava`. Chúng giải quyết hai vấn đề khác nhau.

## 14. Những nguyên tắc viết Groovy DSL dễ bảo trì

- Ưu tiên cú pháp đơn giản; dùng ngoặc tròn ở chỗ giúp người đọc thấy rõ đối số và method call, dù Groovy cho phép bỏ ngoặc.
- Dùng `def` cho biến local ngắn gọn, đặt tên tránh trùng với property của Gradle; đừng dùng `ext` cho mọi cấu hình.
- Tránh metaprogramming phức tạp hoặc dựa vào thứ tự side effect để “điều khiển” Gradle. Build script chủ yếu nên **mô tả** cấu hình.
- Dùng `tasks.register` khi tạo task, `tasks.named` khi cấu hình task hiện có; ưu tiên API lazy/Provider để không buộc xử lý mọi task trong mỗi lần chạy Gradle.
- Với task có đầu ra thực, dùng task type và khai báo input/output phù hợp để hưởng incremental build, up-to-date check và build cache khi đủ điều kiện; `doLast` minh họa ở đây chỉ dùng cho bài tập.
- Để một task làm công việc thật trong giai đoạn execution, tránh đọc file, gọi mạng hay tạo artifact ở cấp script chỉ vì Groovy cho phép chạy code ở đó.
- Dùng plugin và configuration đúng ngữ cảnh: Gradle DSL là các API có điều kiện tồn tại, không phải một bộ tên toàn cục luôn dùng được.

**Mô hình ghi nhớ:** dấu `=` thường biểu diễn gán property; `tên(x)` hoặc `tên x` biểu diễn gọi method; `tên { ... }` truyền closure; `def`, `[]`, `[:]`, `${...}`, `?.` và `?:` là cú pháp Groovy; còn `plugins`, `repositories`, `dependencies`, `tasks`, `Provider` và `doLast` là khả năng từ Gradle hoặc plugin. Khi hiểu ranh giới đó, bạn có thể đọc build script như mã cấu hình có đối tượng và vòng đời rõ ràng.

### Tài liệu chính thức

- [A Groovy Build Script Primer](https://docs.gradle.org/current/userguide/groovy_build_script_primer.html): cách đọc property, method, closure và delegate trong Gradle.
- [Writing Build Scripts](https://docs.gradle.org/current/userguide/writing_build_scripts_intermediate.html): đối tượng Settings/Project, cấu trúc script và biến.
- [Build File Basics](https://docs.gradle.org/current/userguide/build_file_basics.html): thành phần cơ bản của build script.
- [Creating and Registering Tasks](https://docs.gradle.org/current/userguide/writing_tasks.html): task và action.
- [Avoiding Unnecessary Task Configuration](https://docs.gradle.org/current/userguide/task_configuration_avoidance.html): `register`, `named` và các API trì hoãn cấu hình.
- [The Apache Groovy Language](https://groovy-lang.org/syntax.html): ngữ pháp Groovy về chuỗi, list/map, closure và toán tử.