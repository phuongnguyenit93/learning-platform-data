# Chuỗi, nội suy, collection, map và named arguments trong Gradle Groovy DSL

## 1. Mục tiêu và ngữ cảnh

`build.gradle` và `settings.gradle` là script theo **Gradle Groovy DSL**. Nhìn giống những dòng khai báo cấu hình, nhưng chúng là mã Groovy được Gradle thực thi với các đối tượng và API riêng. Nắm được cú pháp ngôn ngữ sẽ giúp đọc chính xác DSL, nhận diện được biểu thức nào là dữ liệu và lời gọi nào thuộc Gradle.

Sau bài học, bạn cần:

1. Chọn đúng literal chuỗi `'...'`, `"..."`, triple quote; phân biệt `String` với `GString`.
2. Nội suy `$name`, `${expression}` và hiểu thời điểm nội suy; biết cách escape ký tự `$`.
3. Tạo, truy cập, lọc và biến đổi `List`/`Set`.
4. Sử dụng `Map`, key cố định, key lấy từ biến và tránh `GString` làm key.
5. Giải thích named arguments `foo(name: 'x')` dưới dạng truyền `Map` và áp dụng đúng khi đọc Gradle DSL.
6. Chạy một task Gradle hoàn chỉnh để quan sát kết quả và tránh các lỗi Groovy DSL thường gặp.

**Phạm vi:** tất cả đoạn script Gradle dùng **Groovy DSL** (`build.gradle`); chúng không phải Kotlin DSL (`build.gradle.kts`). Gradle đóng gói phiên bản Groovy tương ứng của chính nó; với tính năng Groovy mới, kiểm tra bản Gradle thực tế thay vì mặc định Groovy độc lập mới nhất luôn tương thích.

## 2. Chuỗi (String) và nội suy (GString)

Groovy có các loại literal chuỗi sau:

| Cú pháp | Có thể trải nhiều dòng | Nội suy biểu thức? | Ghi chú |
| --- | --- | --- | --- |
| `'hello'` | Không | Không | `java.lang.String`. |
| `"hello"` | Không | Có nếu chứa `$...` | `String` khi không nội suy, `GString` khi có nội suy. |
| `'''hello'''` | Có | Không | Multiline `String`. |
| `"""hello"""` | Có | Có | Multiline `String`/`GString` tùy nội dung. |
| `/.../` (slashy) | Có | Có thể | Thuận tiện với regex; phải chú ý dấu `/`. |
| `$/.../$/` (dollar-slashy) | Có | Có thể | Hữu ích khi nhiều dấu `\` hoặc `/`. |

**Nháy đơn không nội suy.** Nháy kép cho phép tham chiếu tên đơn giản bằng `$name` hoặc biểu thức phức tạp trong `${...}`:

```groovy
def user = 'Lan'
def major = 2

assert 'Hello $user' == 'Hello $user'
assert "Hello $user" == 'Hello Lan'
assert "Hello ${user.toUpperCase()}" == 'Hello LAN'
assert "version-${major + 1}" == 'version-3'
```

Với tên được ghép thêm hậu tố, dùng ngoặc `{ }` để không nhầm ranh giới biến:

```groovy
def module = 'core'
assert "${module}-api" == 'core-api'
assert 'cost=$25' == 'cost=$25'
assert "cost=\$25" == 'cost=$25'
```

Nếu bạn thực sự muốn ký tự `$` trong nháy kép, viết `\$`. Còn trong nháy đơn, `$` vốn là ký tự thường.

### 2.1. Chuỗi nhiều dòng và ký tự escape

```groovy
def noInterpolation = '''one
$module'''
def name = 'core'
def interpolated = """one
${name}"""

assert noInterpolation.readLines() == ['one', '$module']
assert interpolated.readLines() == ['one', 'core']
```

Multiline literal giữ các xuống dòng thật trong nội dung. Nếu thụt lề nằm trong triple quotes, nó cũng có thể trở thành nội dung; dùng `stripIndent()` hoặc `stripMargin()` khi cần chuẩn hóa chuỗi. Các escape như `\n`, `\t`, `\\` cần được hiểu theo luật chuỗi Groovy. Ví dụ đường dẫn Windows có thể biểu diễn `'C:\\work\\app'`, còn regex kiểu `/\d+/` trong slashy string giảm nhu cầu escape backslash.

### 2.2. String và GString không phải một

Chuỗi nội suy có kiểu `groovy.lang.GString`; khi truyền cho API nhận `String`, Groovy thường chuyển qua `toString()`. Việc trông giống nhau khi in ra không có nghĩa hai đối tượng đồng nhất về kiểu và hash:

```groovy
def version = '1.0'
def plain = 'lib-1.0'
def dynamic = "lib-${version}"

assert plain instanceof String
assert dynamic instanceof groovy.lang.GString
assert dynamic.toString() == plain
```

Nội suy `${variable}` thông thường lấy giá trị tại lúc tạo `GString`. Biến có thể được đọc lại ở thời điểm `toString()` nếu dùng biểu thức closure `${-> variable}`:

```groovy
def phase = 'alpha'
def snapshot = "phase=${phase}"
def live = "phase=${-> phase}"

phase = 'beta'
assert snapshot.toString() == 'phase=alpha'
assert live.toString() == 'phase=beta'
```

Đây là cơ chế **GString của Groovy**, không phải cơ chế trì hoãn cấu hình của Gradle. Đặc biệt trong build script, không thay `Provider`/`Property` bằng thủ thuật nội suy closure rồi mặc định rằng Gradle sẽ quản lý dependency/lifecycle đúng.

### 2.3. Ví dụ Gradle dùng String và GString

Trong `build.gradle`:

```groovy
tasks.register('showNames') {
    doLast {
        def module = 'api'
        logger.quiet('literal: $module')
        logger.quiet("rendered: ${module}-service")
    }
}
```

Chạy:

```bash
./gradlew --quiet showNames --console=plain
```

Phần output của task là:

```text
literal: $module
rendered: api-service
```

Ở đây `logger.quiet` được dùng để output vẫn xuất hiện khi cờ `--quiet` được bật; khi chạy trong project khác có task hoặc plugin đặc biệt, output tổng thể có thể có thông điệp bổ sung. Đoạn mã chạy trong `doLast`, tức khi task được thực thi, chứ không phải mỗi lần Gradle đánh giá script ở pha cấu hình.

## 3. Collection: List, Set và closure

### 3.1. Tạo và truy cập List

Ngoặc vuông với phần tử như `['core', 'api']` tạo `List`. `[]` là List rỗng.

```groovy
def modules = ['core', 'api', 'web']

assert modules instanceof List
assert modules.size() == 3
assert modules[0] == 'core'
assert modules[-1] == 'web'

modules << 'tool'
assert modules == ['core', 'api', 'web', 'tool']
```

List có thứ tự và chấp nhận phần tử trùng. Dùng `Set` khi quan tâm tính duy nhất của phần tử:

```groovy
def tags = ['ci', 'fast', 'ci'] as Set
assert tags.size() == 2
assert tags.contains('ci')
```

### 3.2. Lọc, biến đổi và duyệt collection

Groovy dùng **closure** trong cặp `{ ... }` để cung cấp hành động hoặc điều kiện. Một closure có tham số ngầm `it` hoặc khai báo tham số tường minh:

```groovy
def modules = ['core', 'api', 'web', 'test']

def chosen = modules.findAll { it != 'test' }
def upper = chosen.collect { module -> module.toUpperCase() }
def hasApi = modules.any { it == 'api' }

assert chosen == ['core', 'api', 'web']
assert upper == ['CORE', 'API', 'WEB']
assert upper.join(':') == 'CORE:API:WEB'
assert hasApi
assert modules == ['core', 'api', 'web', 'test']
```

Các phương thức hay gặp:

| Phương thức | Mục đích | Có trả collection mới? |
| --- | --- | --- |
| `each { ... }` | Duyệt để thực hiện tác vụ. | Thường trả collection gốc. |
| `findAll { ... }` | Chọn phần tử theo điều kiện. | Có. |
| `collect { ... }` | Ánh xạ phần tử sang giá trị mới. | Có. |
| `find { ... }` | Tìm phần tử đầu tiên phù hợp. | Trả một phần tử hoặc null. |
| `any`/`every` | Kiểm tra tồn tại / tất cả thỏa điều kiện. | Trả boolean. |
| `join(', ')` | Nối các phần tử thành chuỗi. | Trả String. |
| `unique()` | Loại trùng, mặc định thường sửa list nguồn. | Cẩn thận tính mutable. |

Không nên giả định mọi operation đều sửa list: `findAll` và `collect` ở trên không đổi `modules`. Muốn dùng kết quả, cần gán hoặc nối lời gọi. Khi chia sẻ một list mutable giữa nhiều đoạn cấu hình Gradle, những chỉnh sửa ngoài ý muốn có thể làm build khó dự đoán.

### 3.3. Collection ở đâu trong Gradle?

Trong `settings.gradle`, có thể viết:

```groovy
rootProject.name = 'multi-demo'
include 'core', 'api'
```

Đây là **lời gọi Gradle `include`** nhận project path, còn dấu phẩy và string literal là cú pháp Groovy. Chỉ thêm tên project khi đã có ý định định nghĩa project con tương ứng. Với API nhận varargs, có thể chuẩn bị danh sách và chuyển sang `String[]` nếu cần:

```groovy
def children = ['core', 'api']
include(children as String[])
```

Một đối tượng Gradle như `FileCollection`, `Configuration` hay `Provider` **không phải List thông thường**. Chúng có ngữ nghĩa về nguồn file, dependency và lazy evaluation; hãy dùng API của đúng kiểu thay vì ép mọi thứ thành List để xử lý.

## 4. Map: key-value, truy cập và key động

**Map** có dạng `[key: value, other: value]`. Trong Groovy, `[:]` là Map rỗng (khác `[]`).

```groovy
def artifact = [group: 'org.example', name: 'api', version: '1.0']

assert artifact instanceof Map
assert artifact.group == 'org.example'
assert artifact['name'] == 'api'

artifact.version = '1.1'
artifact['classifier'] = 'sources'

assert artifact['version'] == '1.1'
assert artifact.classifier == 'sources'
```

Map literal thường dùng `LinkedHashMap` và giữ thứ tự thêm các cặp, nhưng thứ tự key của Map không quyết định thứ tự thực thi task trong Gradle.

### 4.1. Cạm bẫy `key:` so với `(key):`

Trong map literal, key viết như một tên đơn giản là **chuỗi literal**, không phải biến cùng tên:

```groovy
def key = 'environment'

def wrong = [key: 'dev']
def right = [(key): 'dev']

assert wrong['key'] == 'dev'
assert wrong['environment'] == null
assert right['environment'] == 'dev'
```

Viết `[(key): 'dev']` nếu muốn dùng **giá trị của biến** làm key. Có thể truy cập bằng `map[key]` khi tên key cũng động. Với key chứa dấu gạch ngang hay khoảng trắng, đặt trong dấu nháy: `['project-name': 'demo']`. Khi key có thể trùng tên property/method của Map, ưu tiên `map['class']` hoặc `map.get('class')` để tránh nhập nhằng.

### 4.2. Cạm bẫy GString làm Map key

Khi Map lưu key dựa trên hash, `GString` không có hashCode bằng `String` cùng nội dung. Trường hợp này dễ gây lỗi dù khi log, hai giá trị in giống nhau:

```groovy
def name = 'api'
def interpolatedKey = "module-${name}"

def unsafe = [:]
unsafe.put(interpolatedKey, 42)
assert unsafe.get('module-api') == null

def safe = [(interpolatedKey.toString()): 42]
assert safe['module-api'] == 42
```

Nếu key sẽ được truy cập bằng chuỗi thường, chuyển `GString` sang `String` trước khi đưa vào Map. Đặc biệt chú ý khi tạo Map bằng tên module, tên task hoặc environment được nội suy.

### 4.3. Duyệt Map và nối Map

```groovy
def versions = [core: '1.0', api: '2.0']
def result = []

versions.each { key, value ->
    result << "${key}=${value}"
}

assert result == ['core=1.0', 'api=2.0']

def extended = versions + [web: '3.0']
assert extended == [core: '1.0', api: '2.0', web: '3.0']
assert versions == [core: '1.0', api: '2.0']
```

`Map.each { key, value -> ... }` duyệt từng cặp. Toán tử `+` tạo map kết quả mới; nếu muốn cập nhật trực tiếp, dùng `map[key] = value`, `put` hoặc `putAll`.

## 5. Named arguments: cú pháp giống tham số đặt tên

Trong Groovy, lời gọi sau trông như truyền tham số `name` và `count`:

```groovy
def describe(Map options) {
    return "${options.name} x ${options.count}"
}

assert describe(name: 'compile', count: 2) == 'compile x 2'
assert describe([name: 'compile', count: 2]) == 'compile x 2'
```

Đối với phương thức thông thường, Groovy **gom các cặp có tên thành một Map**, đưa Map này vào **tham số đầu tiên** của phương thức. Nó không tự động ánh xạ theo tên khai báo của mọi method. Nếu phương thức chỉ có `describe(String name, int count)`, lời gọi `describe(name: 'compile', count: 2)` sẽ không khớp chữ ký đó như trong Python/Kotlin.

Có thể trộn thêm positional argument khi method có Map đầu tiên:

```groovy
def repeatMessage(Map options, int times) {
    return ([options.label] * times).join(' | ')
}

assert repeatMessage(label: 'OK', 2) == 'OK | OK'
assert repeatMessage(2, label: 'OK') == 'OK | OK'
```

Tuy được phép, việc trộn hai dạng dễ làm code khó hiểu; khi thiết kế API, nên ưu tiên signature và quy ước gọi thống nhất. Constructor Groovy có thể có quy tắc named properties riêng, không nên dùng đặc tính đó để kết luận mọi method đều nhận named arguments.

### 5.1. Phân biệt ba kiểu câu lệnh trong Gradle

```groovy
group = 'com.example'                   // Gán property trên Project
tasks.register('hello') { }            // Method nhận tên và closure
def options = [format: 'text']          // Map literal
```

Và đoạn:

```groovy
plugins {
    id 'java'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.apache.commons:commons-lang3:3.17.0'
}
```

Các block `plugins`, `repositories`, `dependencies` đến từ **Gradle API và closure/delegate**, không phải Map literal. `id 'java'` là lời gọi method bỏ dấu ngoặc; `implementation` là phương thức thêm dependency, có khi plugin `java` đã thêm configuration đó. Chỉ nhìn thấy dấu `:` không đủ kết luận một expression là named arguments; phải biết **chữ ký API** và context closure.

### 5.2. Cảnh báo đặc biệt: map notation của dependency bị deprecated

Một số build script cũ dùng:

```groovy
dependencies {
    // Cú pháp cũ để học cách nhận diện named arguments:
    implementation group: 'org.apache.commons',
                   name: 'commons-lang3',
                   version: '3.17.0'
}
```

Groovy gom `group/name/version` vào một Map; Gradle đời trước chấp nhận biểu thức đó khi thêm dependency. Nhưng **map notation cho external module dependencies đã bị deprecated từ Gradle 9.1**; tài liệu Gradle hiện hành cho biết kiểu khai báo này sẽ không còn được hỗ trợ ở Gradle 10. Khi viết build mới, dùng:

```groovy
dependencies {
    implementation 'org.apache.commons:commons-lang3:3.17.0'
}
```

Không có mâu thuẫn: **Groovy vẫn hỗ trợ named arguments** cho method được thiết kế để nhận Map, nhưng **API dependency của Gradle** đang thay đổi để dùng tọa độ dạng chuỗi. Xem https://docs.gradle.org/current/userguide/declaring_dependencies_basics.html và https://docs.gradle.org/current/userguide/best_practices_dependencies.html.

## 6. Bài thực hành tổng hợp với build.gradle chạy được

Trong một dự án Gradle có Wrapper, tạo hoặc thay nội dung file `build.gradle` **chỉ trong thư mục thực hành riêng** bằng mã sau. Không đặt trong `build.gradle.kts`.

```groovy
String renderOption(Map options) {
    return "${options.label} x${options.count}"
}

tasks.register('inspectGroovyDsl') {
    doLast {
        def app = 'portal'
        def modules = ['core', 'api', 'web']

        def selected = modules
            .findAll { it != 'web' }
            .collect { it.toUpperCase() }

        def options = [env: 'dev', retries: 2]

        def key = 'module'
        def dynamicMap = [(key): app]

        logger.quiet('literal: $app')
        logger.quiet("rendered: ${app}")
        logger.quiet("modules: ${selected.join(', ')}")
        logger.quiet("env: ${options.env}")
        logger.quiet("retries: ${options['retries']}")
        logger.quiet("dynamic: ${dynamicMap['module']}")
        logger.quiet("named: ${renderOption(label: 'sync', count: 2)}")
    }
}
```

Chạy trên Linux/macOS:

```bash
./gradlew --quiet inspectGroovyDsl --console=plain
```

Trên Windows PowerShell:

```powershell
.\gradlew.bat --quiet inspectGroovyDsl --console=plain
```

Output do task in ra (với mã nguyên vẹn trên):

```text
literal: $app
rendered: portal
modules: CORE, API
env: dev
retries: 2
dynamic: portal
named: sync x2
```

Giải thích kết quả:

- **literal:** nháy đơn giữ nguyên `$app`.
- **rendered:** nháy kép nội suy biến `app` thành `portal`.
- **modules:** `findAll` lọc bỏ `web`; `collect` đổi thành chữ hoa; `join` nối bằng dấu phẩy.
- **env/retries:** đọc một Map bằng `.property` và `['key']`.
- **dynamic:** key của Map lấy từ giá trị biến `key` nhờ cú pháp `(key)`.
- **named:** `renderOption(label: 'sync', count: 2)` truyền Map cho method `renderOption(Map)`.

Task dùng `doLast` để chỉ in output khi **thực thi task**, còn Gradle đánh giá script trong pha cấu hình để đăng ký task. Lệnh không khai báo plugin/dependency ngoài nên phần thực hành không cần tải thư viện; vẫn cần một phiên bản Gradle và Java tương thích. Để tránh output phụ trội từ thông điệp lifecycle, dùng `--quiet --console=plain`.

## 7. Liên hệ với quá trình cấu hình thực tế

Các giá trị Groovy có thể được tính ngay khi Gradle cấu hình project. Ví dụ:

```groovy
def module = 'api'
def destination = "reports/${module}"
```

`destination` được tạo thành một GString trong quá trình script được đánh giá. Nếu dữ liệu đầu vào xuất phát từ Gradle project property, environment hoặc kết quả task khác, **đừng xem nội suy chuỗi là cơ chế lazy tự động**. Với API hỗ trợ `Provider` và `Property`, ưu tiên kết nối các giá trị thông qua API lazy được Gradle hướng dẫn thay vì ép ra chuỗi quá sớm.

Về collection và Map, tránh thay đổi một cấu trúc mutable được chia sẻ trong lúc cấu hình nhiều project/task mà không có chủ đích. Khi chọn module/task, list có thứ tự và map key-value là **dữ liệu**, không tự thay đổi dependency graph hay task execution order nếu bạn chưa gọi đúng API Gradle.

Một số quy tắc đọc DSL:

1. `'...'` là literal, `"...${...}"` nội suy; `GString` có thể ảnh hưởng đến Map key.
2. `[]` là List rỗng, `[:]` là Map rỗng.
3. `[key: value]` có key chuỗi `'key'`; `[(key): value]` có key lấy từ biến.
4. `foo(name: 'a')` đối với method thường là truyền Map; signature của method quyết định hợp lệ.
5. `repositories { ... }` là block closure Gradle, không phải một Map.
6. Với dependency hiện đại, dùng tọa độ chuỗi `'group:name:version'`, tránh map notation đã deprecated.

## 8. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách sửa |
| --- | --- | --- |
| Viết `'v=${version}'` nhưng output chứa nguyên `${version}` | Nháy đơn không nội suy. | Dùng `"v=${version}"`. |
| `MissingPropertyException` khi nối tên biến với chữ | Ranh giới nội suy chưa rõ. | Dùng `${name}-suffix`. |
| `def m = [key: x]` không có key từ biến `key` | Key trong map literal là chữ `key`. | Dùng `[(key): x]`. |
| Tra Map bằng `String` không thấy key từng nội suy | Map key lưu `GString` với hash khác. | Chuyển `toString()` trước khi thêm key. |
| Dùng `[]` làm Map rỗng | Đây là List. | Dùng `[:]`. |
| Dùng `collect` nhưng list ban đầu không đổi | `collect` trả kết quả mới. | Gán kết quả vào biến; sửa list có chủ đích nếu cần. |
| `foo(name: 'x')` không gọi được `foo(String name)` | Named arguments là Map, không phải biến tên của method. | Khai báo tham số Map hoặc gọi `foo('x')`. |
| Gradle báo deprecated với dependency map notation | API external dependency không còn khuyến nghị named map. | Dùng chuỗi tọa độ `group:name:version`. |
| Copy Groovy DSL sang `build.gradle.kts` bị lỗi | Hai DSL dùng ngôn ngữ khác nhau. | Viết lại cú pháp Kotlin đúng kiểu. |
| Dùng String động tại pha configuration rồi mong tự cập nhật | GString thông thường chốt giá trị, khác Provider. | Dùng Gradle Provider/Property khi API yêu cầu lazy. |

## 9. Bài tập tự kiểm tra

**Bài 1:** dự đoán kết quả rồi dùng `assert` kiểm tra: `def name = 'api'`; `'mod=$name'`; `"mod=${name}"`; `"mod=${name.toUpperCase()}"`. Tại sao cùng một giá trị ban đầu nhưng kết quả khác?

**Bài 2:** từ list `['core', 'api', 'web', 'test']`, lọc `test`, biến thành chữ hoa và nối bằng dấu `:`. Đáp án mong đợi `CORE:API:WEB`; xác nhận list ban đầu không bị sửa.

**Bài 3:** đặt `def key = 'environment'`. So sánh `[key: 'dev']` và `[(key): 'dev']` bằng `assert map['environment']`.

**Bài 4:** viết `def label(Map options)` nhận `name` và `count`; gọi bằng `label(name: 'compile', count: 3)`. Nếu đổi method thành `label(String name, int count)`, vì sao cú pháp named argument cũ không còn khớp?

**Bài 5:** chạy task `inspectGroovyDsl`, đổi `modules` thành `['core', 'api', 'web', 'docs']`, rồi thử bỏ `findAll`. Tự giải thích dòng output collection đổi ra sao.

**Bài 6:** đọc mã cũ `implementation group: 'g', name: 'a', version: '1'`. Chỉ rõ Map mà Groovy tạo và đổi sang `implementation 'g:a:1'` theo khuyến nghị Gradle mới.

## 10. Tài liệu chính thức

- Groovy Language Documentation — string, GString, list/map literal và named arguments: https://docs.groovy-lang.org/latest/html/documentation/
- Groovy Development Kit — collection/map operations, chú ý GString key: https://docs.groovy-lang.org/latest/html/documentation/core-gdk.html
- Gradle Groovy Build Script Primer: https://docs.gradle.org/current/userguide/groovy_build_script_primer.html
- Gradle Writing Build Scripts — delegate, closure, project properties: https://docs.gradle.org/current/userguide/writing_build_scripts_intermediate.html
- Gradle Declaring Dependencies — dependency notation/deprecation: https://docs.gradle.org/current/userguide/declaring_dependencies_basics.html
- Gradle Best Practices for Dependencies: https://docs.gradle.org/current/userguide/best_practices_dependencies.html

Hiểu `String/GString`, collection, `Map` và named arguments giúp bạn đọc Groovy DSL như mã nguồn có quy tắc rõ ràng, và kiểm tra đúng API Gradle nào đang nhận từng giá trị.