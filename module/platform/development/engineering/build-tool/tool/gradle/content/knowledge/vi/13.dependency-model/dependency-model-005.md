# Quan hệ extendsFrom và phạm vi kế thừa dependency trong Gradle

## 1. Bài toán và mục tiêu

Trong một dự án Gradle, dependency không nằm trong “một danh sách chung” được dùng cho mọi công việc. Gradle chia dependency theo **configuration**: tập dependency phục vụ biên dịch, chạy ứng dụng, kiểm thử, annotation processing, phát hành thư viện hoặc một công việc tùy chỉnh.

Khi nhiều configuration cần dùng chung một tập khai báo dependency, Gradle cung cấp quan hệ **`extendsFrom`**. Ví dụ đơn giản:

~~~text
implementation  (dependency khai báo cho ứng dụng)
      |
      | được kế thừa bởi
      v
testImplementation (dependency dùng khi biên dịch/chạy test)
~~~

Trong Java plugin, `testImplementation` thường mở rộng `implementation`: mã test có thể sử dụng thư viện mà mã chính sử dụng, cộng với thư viện chỉ dành cho test. Nhưng quan hệ này **không có nghĩa** rằng mọi dependency dành cho test sẽ quay ngược vào classpath của mã chính.

Sau bài học, bạn có thể:

- Phân biệt configuration với dependency, task, classpath và project.
- Đọc đúng chiều `child.extendsFrom(parent)`, kể cả khi có nhiều cha và nhiều tầng.
- Hiểu chính xác các thành phần được kế thừa: **dependencies, dependency constraints, exclude rules, artifacts và capabilities**.
- Hiểu các thành phần **không** được kế thừa: **attributes và vai trò declarable/resolvable/consumable**.
- Liên hệ `implementation`, `api`, `compileOnly`, `runtimeOnly`, `testImplementation` và các resolvable classpath của Java/Java Library plugin.
- Tạo configuration tùy chỉnh đúng vai trò bằng Kotlin DSL và Groovy DSL, tránh vòng lặp hoặc trộn sai phạm vi.
- Chạy một project Java 17 dùng một JAR nội bộ để thấy dependency thực sự đi qua chuỗi `extendsFrom` vào compile/runtime classpath.
- Chẩn đoán trường hợp dependency “không xuất hiện”, “xuất hiện sai phạm vi” hoặc bị chọn phiên bản không mong muốn.

## 2. Configuration không phải task và cũng không phải một JAR

Ví dụ:

~~~kotlin
plugins {
    id("java")
}

dependencies {
    implementation("org.apache.commons:commons-lang3:3.14.0")
    testImplementation("org.junit.jupiter:junit-jupiter:5.11.4")
}
~~~

`implementation` và `testImplementation` là **tên dependency configurations** do Java plugin tạo. Một dependency declaration như `org.apache.commons:commons-lang3:3.14.0` mô tả một module muốn sử dụng.

Cần tách ba lớp:

1. **Khai báo dependency:** muốn dùng module/project/file nào, cho mục đích gì.
2. **Giải quyết dependency:** Gradle xác định phiên bản, biến thể (*variant*), các dependency bắc cầu và file thực tế; tạo classpath được dùng.
3. **Thực thi task:** `compileJava`, `test`, `run` hoặc task khác tiêu thụ classpath đã được giải quyết.

Một configuration **không tự biên dịch** và không phải là task. Một task có thể dùng một hoặc nhiều configuration làm input. Một configuration declarable như `implementation` **không nên được resolve trực tiếp** chỉ để lấy JAR; plugin thường có configuration resolvable như `compileClasspath` hoặc `runtimeClasspath` cho việc đó.

### 2.1. Ba vai trò quan trọng của configuration

Gradle hiện đại phân biệt:

| Vai trò | Dùng để làm gì? | Ví dụ phổ biến |
| --- | --- | --- |
| **Declarable** / dependency scope | Chứa các khai báo dependency được nhóm theo mục đích | `implementation`, `runtimeOnly`, `testImplementation` |
| **Resolvable** | Giải quyết graph để lấy file/artifact phục vụ công việc | `compileClasspath`, `runtimeClasspath`, `testRuntimeClasspath` |
| **Consumable** | Công bố biến thể/artifact cho project khác sử dụng | `apiElements`, `runtimeElements` |

Các cờ API có liên quan:

- `canBeDeclared` — configuration có thể nhận dependency declarations hay không.
- `canBeResolved` — configuration có thể được resolve hay không.
- `canBeConsumed` — configuration có thể được tiêu thụ như một variant hay không.

Một configuration mới nên có **một vai trò rõ ràng**. Các API mới như `configurations.dependencyScope(...)`, `configurations.resolvable(...)` và `configurations.consumable(...)` thể hiện vai trò trực tiếp (một số API này ở các phiên bản Gradle vẫn mang trạng thái incubating). Nếu dùng `create(...)` hoặc `register(...)`, cần cấu hình cờ phù hợp.

**Điểm then chốt:** `extendsFrom` **không đổi vai trò** của configuration. Một `runtimeClasspath` vẫn là resolvable dù kế thừa `implementation` declarable. Ngược lại, `implementation` không trở thành resolvable chỉ vì một configuration resolvable kế thừa nó.

## 3. Cách đọc extendsFrom: luôn đọc từ configuration con

### 3.1. Cú pháp

Kotlin DSL (`build.gradle.kts`):

~~~kotlin
configurations.named("child") {
    extendsFrom(configurations.getByName("parent"))
}
~~~

Đây là **đoạn minh họa**, đòi hỏi đã có configuration tên `child` và `parent` trong **cùng Project**. Nó có nghĩa:

> Configuration **child kế thừa các khai báo dependency-related của parent**.

Không phải ngược lại. Nếu thêm dependency vào `child`, `parent` không vì thế sở hữu dependency đó.

Trong Groovy DSL (`build.gradle`):

~~~groovy
configurations {
    child.extendsFrom(parent)
}
~~~

Đoạn Groovy cũng giả định `child` và `parent` đã được tạo. Tên `extendsFrom` thuộc API của **Configuration**, không phải inheritance của class Java/Kotlin.

### 3.2. Mô hình hai tầng

~~~text
baseDeps
  ├── thư viện A
  └── thư viện B
       |
       v  child.extendsFrom(baseDeps)
childDeps
  └── thư viện C (khai báo trực tiếp)
~~~

Khi xem toàn bộ các dependency declarations mà `childDeps` thừa hưởng:

~~~text
childDeps = baseDeps + declarations của childDeps
          = A + B + C
~~~

Nhưng `baseDeps` vẫn chỉ có A và B. Cách viết toán học trên minh họa **phạm vi khai báo có thể sử dụng**, không nói rằng Gradle nối ba file JAR theo đúng thứ tự này: trong quá trình resolve, Gradle còn xử lý conflicts, constraints, biến thể và dependency bắc cầu.

### 3.3. Nhiều parent

Một configuration có thể kế thừa từ nhiều configuration:

~~~kotlin
configurations.named("combined") {
    extendsFrom(
        configurations.getByName("common"),
        configurations.getByName("feature")
    )
}
~~~

Nếu `common` khai báo A, `feature` khai báo B, `combined` khai báo C, thì khi được sử dụng, `combined` bao gồm declarations từ ba scope A/B/C. Nó **không** tạo quan hệ giữa `common` và `feature`, cũng không ngụ ý A phải “được tải trước” B.

Nhiều parent có thể dẫn tới các yêu cầu phiên bản khác nhau cho cùng module. Gradle giải quyết chúng bằng cơ chế version/conflict resolution chứ không đơn giản chọn “parent được ghi trước”.

### 3.4. Kế thừa bắc cầu giữa các configuration

Nếu:

~~~text
base
  |
  v
middle
  |
  v
leaf
~~~

và `middle.extendsFrom(base)`, `leaf.extendsFrom(middle)`, thì `leaf` cũng nhìn thấy dependency-related declarations từ `base` qua `middle`.

Đây là **transitive configuration inheritance**, nhưng đừng nhầm với **transitive module dependencies** (một module A phụ thuộc module B). Hai cơ chế khác nhau được phân biệt kỹ ở mục 11.

### 3.5. Cấm một số quan hệ sai

- `extendsFrom` chỉ được phép giữa configurations của **cùng một project**; không trực tiếp kế thừa configuration từ project `:library` bằng cách lấy đối tượng của nó.
- Một **detached configuration** không được kế thừa configuration khác.
- Không tạo chu trình như `a.extendsFrom(b)` và `b.extendsFrom(a)`. Khi graph inheritance không còn có hướng hợp lệ, Gradle sẽ từ chối.
- Tránh cố cho dependency scope kế thừa một configuration chuyên dùng để resolve, hoặc để variant consumable kế thừa scope không phù hợp một cách thiếu kiểm soát. Thiết kế theo đúng vai trò và hướng dùng của plugin.

## 4. extendsFrom kế thừa chính xác những gì?

Theo tài liệu chính thức về configuration inheritance của Gradle, configuration con kế thừa các thành phần liên quan dependency sau từ parent:

| Thành phần | Có kế thừa? | Giải thích |
| --- | --- | --- |
| **Dependency declarations** | **Có** | Module dependencies, project dependencies, file dependencies được khai báo trên parent |
| **Dependency constraints** | **Có** | Các ràng buộc phiên bản/quy tắc constraint khai báo trong parent có thể ảnh hưởng resolution ở child |
| **Exclude rules** | **Có** | Quy tắc exclude cấu hình ở parent được áp dụng trong phạm vi kế thừa |
| **Artifacts** | **Có** | Các artifact declarations liên quan configuration có thể được thừa hưởng |
| **Capabilities** | **Có** | Các capability declarations liên quan configuration được thừa hưởng |
| **Attributes** | **Không** | Attribute chọn variant của child phải được cấu hình riêng khi cần |
| **Vai trò/cờ** (`canBeResolved`, `canBeConsumed`, `canBeDeclared`) | **Không** | Các cờ riêng của từng configuration không thay đổi vì `extendsFrom` |

Điểm dễ bị bỏ qua nhất là **attributes không được kế thừa**. Gradle dùng attributes như `org.gradle.usage`, `org.gradle.category`, `org.gradle.libraryelements` và các attribute tùy biến để thực hiện variant-aware dependency resolution. Nếu tạo custom resolvable/consumable configuration, bạn có trách nhiệm thiết lập attributes thích hợp; không thể trông đợi `extendsFrom` tự chép attributes từ một parent.

Tương tự, một configuration có thể chứa các dependency declarations cần thiết nhưng vẫn không thể `resolve()`, nếu vai trò của nó chỉ là declarable.

### 4.1. Dependency declarations được nhìn thấy nhưng có thể chưa được tải

~~~kotlin
dependencies {
    implementation("com.example:shared-api:1.0")
}
~~~

Sau khi cấu hình các scope kế thừa từ `implementation`, sự hiện diện của declaration **không đồng nghĩa Gradle đã tải được JAR**. Việc resolve còn cần repository, metadata module đúng, kết nối mạng/cache và một configuration resolvable hợp lệ.

Ví dụ module `com.example:shared-api:1.0` ở trên chỉ để mô tả cú pháp, **không khẳng định artifact này tồn tại**. Dự án thật cần dùng tọa độ chính xác của thư viện và repository phù hợp.

### 4.2. Constraints không phải dependency bổ sung

Một **dependency constraint** ảnh hưởng cách chọn phiên bản của một module **nếu module đó nằm trong graph phù hợp**; khai báo constraint không tự thêm module vào graph.

Giả sử parent có constraint trên `com.example:core`, và child chứa dependency thực tế kéo `com.example:core` vào resolution. Khi resolve child, constraint kế thừa có thể ảnh hưởng phiên bản được chọn. Nếu không có dependency nào tham chiếu module đó, constraint riêng không bảo đảm JAR xuất hiện.

Không hiểu `extendsFrom` là “ép chạy/cài đặt tất cả dependency trong parent”; Gradle là build tool khai báo, cơ chế resolution được thực hiện theo nhu cầu.

### 4.3. Exclude rule và phạm vi áp dụng

Ví dụ Groovy DSL minh họa:

~~~groovy
configurations {
    commonDeps {
        exclude group: 'org.unwanted', module: 'old-logger'
    }
    childDeps.extendsFrom commonDeps
}
~~~

Đây là **đoạn minh họa** chỉ hợp lệ khi đã tạo `commonDeps` và `childDeps`. Configuration `childDeps` kế thừa rule loại module `org.unwanted:old-logger` từ `commonDeps`.

Lưu ý có **hai loại exclude thường gặp**:

1. **Configuration-level exclude** (trên configuration) — áp dụng trong phạm vi resolution sử dụng configuration đó và có thể được kế thừa qua `extendsFrom`.
2. **Dependency-level exclude** (trong một dependency declaration) — giới hạn một nhánh quan hệ phụ thuộc cụ thể.

Không được đánh đồng hai loại. Khi một module vẫn xuất hiện sau exclude, kiểm tra nó có được kéo từ nhiều dependency paths hay không và xem graph resolve thực tế; tránh kết luận rằng Gradle “bỏ qua exclude” chỉ dựa vào một dòng cấu hình.

### 4.4. Artifacts/capabilities được kế thừa không đồng nghĩa công bố tự động

Tài liệu Gradle nêu rằng artifacts và capabilities nằm trong những thành phần có thể được thừa hưởng. Tuy nhiên, khả năng **công bố variant** vẫn phụ thuộc configuration có vai trò consumable, attributes, plugin publishing và thiết lập component. Kế thừa một dependency scope không tự biến child thành một variant xuất bản đúng chuẩn.

Với Java Library plugin, hãy ưu tiên cấu hình `api`/`implementation`/`runtimeOnly` theo ý định sử dụng, để plugin quản lý các variant phổ biến thay vì tự nối `extendsFrom` vào `apiElements` hoặc `runtimeElements` không cần thiết.

## 5. Java plugin: phạm vi compile/runtime/test được nối thế nào?

Java plugin tạo nhiều configurations được phân vai rõ ràng. Mô hình đơn giản hóa (tên và quan hệ đúng cho Java plugin thông thường):

~~~text
implementation ----------> compileClasspath
      |                          ^
      |                          |
      +------------> runtimeClasspath <------- runtimeOnly
      |
      +----> testImplementation -----> testCompileClasspath
                     |                          ^
                     |                          |
                     +-----> testRuntimeClasspath <--- testRuntimeOnly
                                 ^
                                 |
                            testRuntimeOnly
~~~

**Lưu ý:** Sơ đồ trên chỉ nêu ý chính, dễ nhìn các nhánh; đọc bảng dưới để biết parent chính xác. Mỗi mũi tên nên hiểu là “configuration phía đích được xây dựng từ các dependency scopes được nêu”, không phải một task phụ thuộc task khác. Đặc biệt `testRuntimeOnly` trong Java plugin thường kế thừa `runtimeOnly`, nên runtime dependency của mã chính cũng có thể nằm trong runtime của test.

Bảng phân biệt:

| Configuration | Vai trò | Quan hệ kế thừa chính hoặc ý nghĩa |
| --- | --- | --- |
| `implementation` | Declarable | Dependency cần cả compile và runtime cho mã chính |
| `compileOnly` | Declarable | Dependency chỉ cần compile mã chính |
| `runtimeOnly` | Declarable | Dependency chỉ cần runtime mã chính |
| `compileClasspath` | Resolvable | Kế thừa `compileOnly` và `implementation` |
| `runtimeClasspath` | Resolvable | Kế thừa `runtimeOnly` và `implementation` |
| `testImplementation` | Declarable | Kế thừa `implementation`; thêm dependency riêng cho test |
| `testCompileOnly` | Declarable | Chỉ phục vụ compile test |
| `testRuntimeOnly` | Declarable | Kế thừa `runtimeOnly`; thêm dependency chỉ dùng lúc chạy test |
| `testCompileClasspath` | Resolvable | Kế thừa `testCompileOnly` và `testImplementation` |
| `testRuntimeClasspath` | Resolvable | Kế thừa `testRuntimeOnly` và `testImplementation` |

### 5.1. Đọc bảng qua một ví dụ

~~~kotlin
plugins {
    id("java")
}

repositories {
    mavenCentral()
}

dependencies {
    implementation("org.apache.commons:commons-lang3:3.14.0")
    compileOnly("org.jetbrains:annotations:24.1.0")
    runtimeOnly("ch.qos.logback:logback-classic:1.5.6")
    testImplementation("org.junit.jupiter:junit-jupiter:5.11.4")
}
~~~

Các tọa độ là ví dụ về **phạm vi khai báo**; để chạy test JUnit 5 còn cần cấu hình `useJUnitPlatform()` và thành phần runtime cần thiết. Từ inheritance và roles:

- `compileJava` có thể resolve `compileClasspath`, gồm `implementation` + `compileOnly`; không tự lấy `runtimeOnly`.
- Khi chạy ứng dụng, `runtimeClasspath` gom `implementation` + `runtimeOnly`; `compileOnly` không đương nhiên nằm ở đây.
- Mã test thấy `implementation` nhờ `testImplementation` kế thừa, cộng các thư viện test trực tiếp.
- Thư viện chỉ khai báo ở `testImplementation` không tự “chảy ngược” vào classpath biên dịch mã chính.
- `runtimeOnly` của mã chính không biến thành `compileOnly` của test; nó được dùng ở test runtime qua đường kế thừa tương ứng.

**Hiểu đúng:** “test thấy dependency của mã chính” không phải vì một tệp JAR được copy vào `src/test`, cũng không phải Gradle nối `testImplementation` với một task `compileJava`. Đó là mối quan hệ giữa các scopes và resolvable classpath.

### 5.2. Đừng tự nối lại những quan hệ plugin đã tạo

Với Java plugin, không cần tự viết:

~~~kotlin
configurations.named("testImplementation") {
    extendsFrom(configurations.getByName("implementation"))
}
~~~

để test “kế thừa” implementation — Java plugin thường đã thiết lập quan hệ này. Đoạn trên là cú pháp hợp lệ nhưng thường **dư thừa**. Tránh thiết lập thủ công lại cả cây configuration nếu plugin quản lý nó đúng sẵn.

Thêm một relation tùy ý vào các configuration built-in có thể làm thay đổi classpath nhiều task hoặc biến thể công bố. Hãy xác định yêu cầu thực tế trước khi can thiệp.

## 6. Java Library plugin: extendsFrom không đồng nghĩa API exposure

Khi build một thư viện Java sử dụng plugin `java-library`, người đọc thường gặp hai khai báo:

~~~kotlin
plugins {
    id("java-library")
}

dependencies {
    api("com.example:public-contract:1.0")
    implementation("com.example:internal-engine:1.0")
}
~~~

Hai tọa độ `com.example:...` chỉ minh họa; không giả định tồn tại để có thể tải. Ý nghĩa:

- `api`: dependency xuất hiện trong **API biên dịch** mà consumer cần; ví dụ public class/method trong library sử dụng một kiểu từ dependency này.
- `implementation`: dependency dùng nội bộ library, không quảng bá như dependency API compile cho consumer; tuy nhiên dependency cần ở runtime vẫn có thể được xuất qua runtime variant.

Trong Java Library plugin, configuration `implementation` **kế thừa `api`**, để bản thân library compile/run với cả dependency API và implementation. Điều này **không có nghĩa** rằng dependencies chỉ nằm trong `implementation` tự động lộ ra compile classpath của consumer.

Các relation điển hình của Java Library plugin:

| Configuration | Kế thừa / mục đích |
| --- | --- |
| `implementation` | Kế thừa `api` |
| `compileOnly` | Kế thừa `compileOnlyApi` |
| `apiElements` (consumable) | Kế thừa `api` và `compileOnlyApi`; phục vụ compile variant |
| `runtimeElements` (consumable) | Kế thừa `runtimeOnly` và `implementation`; phục vụ runtime variant |
| `compileClasspath` (resolvable) | Kế thừa `compileOnly` và `implementation` |
| `runtimeClasspath` (resolvable) | Kế thừa `runtimeOnly` và `implementation` |

**Rất quan trọng:** `extendsFrom` là quan hệ cục bộ của configurations trong một Project. Việc thư viện được **xuất bản và project tiêu thụ chọn đúng variant** còn phụ thuộc plugin Java Library, attributes/capabilities và metadata. Không suy ra `apiElements`/`runtimeElements` tự xuất hiện chỉ vì bạn tạo configuration tùy chỉnh tên giống chúng.

### 6.1. Ví dụ dễ kiểm chứng về ranh giới API

Thư viện `:library` có:

~~~kotlin
plugins {
    id("java-library")
}

dependencies {
    api("org.apache.commons:commons-lang3:3.14.0")
    implementation("com.fasterxml.jackson.core:jackson-databind:2.17.2")
}
~~~

Project `:app` khai báo:

~~~kotlin
dependencies {
    implementation(project(":library"))
}
~~~

**Đây là đoạn minh họa**, giả định `settings.gradle.kts` đã `include(":library", ":app")` và có repository để phân giải module. Mã của `:app` có thể sử dụng các kiểu thuộc API library và các dependency được công bố qua compile variant; dependency chỉ ở `implementation` của `:library` không mặc nhiên được công bố cho compiler của `:app`. Nhưng runtime variant có thể mang dependency implementation theo nhu cầu chạy library.

Đây là khác biệt giữa **configuration inheritance trong một project** và **variant-aware project dependency qua các project**.

## 7. Kotlin DSL: tạo ba scope tùy chỉnh có extendsFrom

Khi thực sự cần một tập dependency riêng cho một tác vụ như kiểm tra nội bộ, phân tích tài liệu hoặc smoke test, có thể tạo các configurations tùy chỉnh. Mẫu dưới đây dùng API `create(...)` với cờ vai trò tường minh (ổn định để hiểu ngữ nghĩa):

~~~kotlin
// build.gradle.kts — ví dụ cấu hình, cần Gradle hỗ trợ canBeDeclared.
val commonTools = configurations.create("commonTools") {
    isCanBeDeclared = true
    isCanBeResolved = false
    isCanBeConsumed = false
}

val smokeTools = configurations.create("smokeTools") {
    isCanBeDeclared = true
    isCanBeResolved = false
    isCanBeConsumed = false

    extendsFrom(commonTools)
}

val smokeClasspath = configurations.create("smokeClasspath") {
    isCanBeDeclared = false
    isCanBeResolved = true
    isCanBeConsumed = false

    extendsFrom(smokeTools)
}
~~~

Mô hình:

~~~text
commonTools (declarable)
    |
    v
smokeTools (declarable)
    |
    v
smokeClasspath (resolvable)
~~~

Ý nghĩa:

- Khai báo dependency chung trong `commonTools`.
- Khai báo phần bổ sung cho smoke test trong `smokeTools`.
- Resolve **`smokeClasspath`**, không resolve trực tiếp các bucket khai báo.
- `smokeClasspath` có thể thấy declarations của cả `smokeTools` và `commonTools` do inheritance nhiều tầng.

Ví dụ thêm dependency declarations:

~~~kotlin
dependencies {
    add("commonTools", "org.apache.commons:commons-lang3:3.14.0")
    add("smokeTools", "org.junit.jupiter:junit-jupiter-api:5.11.4")
}
~~~

Đây là ví dụ **cấu hình**; nó cần repository phù hợp để resolve và một task thực sự sử dụng `smokeClasspath` nếu muốn chạy công việc. Việc có `smokeClasspath` **không tự tạo task `smokeTest`, không tự compile Java và không tự chạy test**.

### 7.1. API khai báo vai trò mới

Ở Gradle hiện đại, có thể dùng API tiện lợi (một số vẫn được đánh dấu incubating trong tài liệu):

~~~kotlin
val commonTools = configurations.dependencyScope("commonTools")

val smokeTools = configurations.dependencyScope("smokeTools") {
    extendsFrom(commonTools.get())
}

val smokeClasspath = configurations.resolvable("smokeClasspath") {
    extendsFrom(smokeTools.get())
}
~~~

`commonTools`/`smokeTools` là dependency scopes; `smokeClasspath` có vai trò resolve. Cách này ngắn và diễn đạt trực tiếp ý định. Vì là các API có thể thay đổi theo phiên bản Gradle, hãy dùng **Gradle Wrapper** và kiểm tra tài liệu đúng phiên bản bạn đang chạy. Không trộn ví dụ mới này với `configurations.create("commonTools")` ở phía trên trong cùng một build script vì sẽ tạo trùng tên configuration.

### 7.2. Groovy DSL tương đương

~~~groovy
// build.gradle — một ví dụ độc lập thay cho Kotlin ở trên.
def commonTools = configurations.create('commonTools') {
    canBeDeclared = true
    canBeResolved = false
    canBeConsumed = false
}

def smokeTools = configurations.create('smokeTools') {
    canBeDeclared = true
    canBeResolved = false
    canBeConsumed = false

    extendsFrom commonTools
}

def smokeClasspath = configurations.create('smokeClasspath') {
    canBeDeclared = false
    canBeResolved = true
    canBeConsumed = false

    extendsFrom smokeTools
}

dependencies {
    add('commonTools', 'org.apache.commons:commons-lang3:3.14.0')
}
~~~

Groovy cho phép cú pháp `extendsFrom commonTools` không ngoặc; Kotlin viết `extendsFrom(commonTools)`. Cả hai là một quan hệ configuration inheritance, không phải `class SmokeTools extends CommonTools` trong lập trình hướng đối tượng.

### 7.3. Tại sao không cứ tạo một configuration canBeResolved=true cho tất cả?

Một configuration kiêm nhiều vai trò có thể gây mơ hồ: nó vừa là nơi khai báo dependency, vừa là thứ đi resolve, vừa có thể là variant công bố. Mô hình mới của Gradle khuyến nghị mỗi configuration có **một trách nhiệm chính**.

Vì thế:

- Bucket kiểu `commonTools`/`smokeTools` giúp người đọc biết dependency được thêm ở đâu.
- `smokeClasspath` biết **được resolve khi nào** và có thể định nghĩa attributes riêng cho consumer.
- Các variant consumable, nếu có, cần thiết lập riêng cho việc xuất bản.
- `extendsFrom` cho phép tái sử dụng declarations mà không đánh đồng ba vai trò.

## 8. Dự án Java 17 chạy được: local JAR được kế thừa qua extendsFrom

Đây là ví dụ quan trọng nhất: **không cần tải thư viện bên ngoài**, vì ta tự biên dịch một local JAR bằng JDK 17 rồi để Gradle kế thừa file dependency đó vào `implementation`. Khi compile và chạy ứng dụng, Gradle sử dụng JAR nhờ chuỗi inheritance do Java plugin quản lý.

### 8.1. Cây thư mục

~~~text
configuration-inheritance-lab/
├── settings.gradle.kts
├── build.gradle.kts
├── libs/
│   └── shared.jar                 (được tạo ở bước 8.4)
├── shared-src/
│   └── demo/
│       └── shared/
│           └── Message.java
└── src/
    └── main/
        └── java/
            └── demo/
                └── app/
                    └── Main.java
~~~

Cần có JDK 17 và Gradle tương thích với bản JDK đó. Thư mục `libs` ban đầu có thể rỗng. Project này không cần `repositories { mavenCentral() }` vì chỉ sử dụng file dependency tự tạo.

### 8.2. settings.gradle.kts

~~~kotlin
rootProject.name = "configuration-inheritance-lab"
~~~

### 8.3. build.gradle.kts hoàn chỉnh

~~~kotlin
plugins {
    id("application")
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

application {
    mainClass.set("demo.app.Main")
}

// Scope tùy chỉnh: chỉ chứa các dependency dùng chung.
// Không resolve/consume trực tiếp scope này.
val sharedLibs = configurations.create("sharedLibs") {
    isCanBeDeclared = true
    isCanBeResolved = false
    isCanBeConsumed = false
    description = "Local libraries shared by production code"
}

// Chiều quan hệ: implementation (con) kế thừa sharedLibs (cha).
configurations.named("implementation") {
    extendsFrom(sharedLibs)
}

dependencies {
    // File dependency có thật, được tạo ở bước 8.4.
    add(sharedLibs.name, files("libs/shared.jar"))
}
~~~

**Điều được chứng minh:**

1. `sharedLibs` là declarable configuration chứa declaration của file `shared.jar`.
2. `implementation.extendsFrom(sharedLibs)` khiến `implementation` thừa hưởng declaration đó.
3. Java/Application plugin đã tạo `compileClasspath` và `runtimeClasspath` lấy dependency declarations từ `implementation`.
4. Vì vậy Java code trong `src/main/java` có thể import class từ local JAR khi **compile** và sử dụng class đó khi **run**.
5. Không có dòng `implementation(files("libs/shared.jar"))` trực tiếp. Sự hiện diện của JAR trên compile/runtime classpath đến từ **quan hệ inheritance**.
6. Vai trò `sharedLibs` vẫn là declarable; nó không tự trở thành resolvable vì `implementation` kế thừa nó.

**Không nhầm hướng:** Nếu đổi thành `sharedLibs.extendsFrom(implementation)`, dependency đặt ở `sharedLibs` **không đi ngược vào implementation**; Java compile/run có thể không còn tìm thấy class cần thiết.

### 8.4. Java nguồn của local JAR

Tạo `shared-src/demo/shared/Message.java`:

~~~java
package demo.shared;

public final class Message {
    private Message() {
    }

    public static String greeting() {
        return "Hello from inherited JAR";
    }
}
~~~

Đây là Java 17 hợp lệ. Trước khi chạy Gradle, biên dịch và đóng gói JAR bằng JDK.

**macOS/Linux (shell):**

~~~bash
mkdir -p build-shared/classes libs
javac -d build-shared/classes shared-src/demo/shared/Message.java
jar --create --file libs/shared.jar -C build-shared/classes .
~~~

**Windows PowerShell:**

~~~powershell
New-Item -ItemType Directory -Force -Path build-shared\classes, libs | Out-Null
javac -d build-shared\classes shared-src\demo\shared\Message.java
jar --create --file libs\shared.jar -C build-shared\classes .
~~~

Lệnh `javac -d` tạo `build-shared/classes/demo/shared/Message.class`; `jar --create` đặt class đó vào `libs/shared.jar`. Không dùng thư viện Maven bên ngoài. Tên JAR và package bên trong phải khớp với file `Message.java` ở trên.

Có thể xem nội dung JAR bằng:

~~~bash
jar --list --file libs/shared.jar
~~~

Output có thể chứa mục directory và metadata, nhưng bắt buộc phải chứa class entry:

~~~text
demo/shared/Message.class
~~~

Không dùng một stdout cố định cho toàn bộ lệnh `jar --list` vì thứ tự và các directory entries có thể khác nhau. Chỉ kiểm tra đường dẫn class ở trên.

### 8.5. Ứng dụng Java 17 sử dụng class bên trong JAR

Tạo `src/main/java/demo/app/Main.java`:

~~~java
package demo.app;

import demo.shared.Message;

public final class Main {
    private Main() {
    }

    public static void main(String[] args) {
        System.out.println(Message.greeting());
    }
}
~~~

Trong project đúng cấu trúc, chạy:

~~~bash
gradle --quiet run
~~~

Stdout của **ứng dụng Java** chính xác:

~~~text
Hello from inherited JAR
~~~

Vì sao `Main.java` có thể import `demo.shared.Message` mặc dù class này không nằm trong `src/main/java`? Java compiler nhìn thấy class qua `shared.jar` trên `compileClasspath`. Java application chạy được vì `shared.jar` cũng nằm trên `runtimeClasspath`. Cả hai classpath kế thừa gián tiếp declaration từ `sharedLibs` qua `implementation`.

### 8.6. Thí nghiệm phá vỡ inheritance

**Thí nghiệm có chủ đích gây lỗi, không phải trạng thái cuối của ví dụ thành công:** tạm bỏ/comment khối:

~~~kotlin
configurations.named("implementation") {
    extendsFrom(sharedLibs)
}
~~~

Sau đó chạy một lần build sạch:

~~~bash
gradle clean compileJava
~~~

Bây giờ `implementation` không còn nhận declaration của `libs/shared.jar`, nên compiler có thể báo lỗi tương đương:

~~~text
package demo.shared does not exist
cannot find symbol: Message
~~~

Nội dung/đường dẫn dòng lỗi có thể khác theo phiên bản javac; đây là **dạng lỗi dự kiến**, không phải toàn bộ output cố định.

Khôi phục chính xác khối `implementation.extendsFrom(sharedLibs)`, rồi chạy:

~~~bash
gradle clean run
~~~

Kết quả Java lại in:

~~~text
Hello from inherited JAR
~~~

Điều này cô lập tác dụng của `extendsFrom`: bạn không cần sửa mã Java hay thêm một dependency trực tiếp khác.

### 8.7. Kiểm tra riêng bằng javac/java không dùng Gradle

Sau khi đã tạo `libs/shared.jar`, để xác minh class/package và tính runnable của Java 17:

**macOS/Linux:**

~~~bash
mkdir -p out
javac -cp libs/shared.jar -d out src/main/java/demo/app/Main.java
java -cp "out:libs/shared.jar" demo.app.Main
~~~

**Windows PowerShell/cmd:**

~~~powershell
javac -cp libs\shared.jar -d out src\main\java\demo\app\Main.java
java -cp "out;libs\shared.jar" demo.app.Main
~~~

Stdout của ứng dụng:

~~~text
Hello from inherited JAR
~~~

Dấu phân cách classpath giữa các entry là `:` trên Linux/macOS và `;` trên Windows. Lệnh `javac` trực tiếp **không chứng minh** cấu hình `extendsFrom` đúng; nó chỉ chứng minh code và JAR hợp lệ. Lệnh Gradle `run` ở mục 8.5 mới kiểm tra đường đi dependency thông qua configuration inheritance.

### 8.8. Dùng Wrapper và kết quả test

Nếu repository đã có Gradle Wrapper, thay `gradle` bằng `./gradlew` trên macOS/Linux hoặc `gradlew.bat` trên Windows. Khi chưa có Wrapper, dùng bản Gradle được cài tương thích để chạy `gradle wrapper` và đưa file wrapper vào quản lý phiên bản của dự án.

Ví dụ có thể chạy thêm:

~~~bash
gradle compileJava
gradle classes
gradle build
~~~

Các lệnh Gradle có thể in log task, thông tin `UP-TO-DATE` hoặc kiểm tra JDK tùy môi trường. Không đoán stdout cố định cho những lệnh này. Task `build` chủ yếu ghép các task kiểm tra/đóng gói do plugin quản lý; điều này không thay thế kiểm tra thực nghiệm về classpath của `run`.

## 9. Quan hệ kế thừa khác việc công bố dependency sang project khác

Giả sử multi-project build:

~~~text
workspace/
├── settings.gradle.kts
├── app/
│   └── build.gradle.kts
└── library/
    └── build.gradle.kts
~~~

`settings.gradle.kts`:

~~~kotlin
rootProject.name = "workspace"
include(":app", ":library")
~~~

Nếu `:app` muốn sử dụng class từ `:library`, hãy khai báo **project dependency**:

~~~kotlin
// app/build.gradle.kts, đã áp dụng java/application plugin
dependencies {
    implementation(project(":library"))
}
~~~

**Không được** làm tương đương:

~~~kotlin
// KHÔNG HỢP LỆ theo mục đích: không dùng extendsFrom xuyên Project.
configurations.named("implementation") {
    extendsFrom(project(":library").configurations.getByName("implementation"))
}
~~~

`extendsFrom` không cho phép liên kết giữa configuration thuộc hai project. Gradle dùng `project(":library")`, variant attributes và tiêu thụ artifact để xử lý dependency xuyên project. Dù tên `implementation` giống nhau trong hai project, chúng vẫn là **hai configuration riêng biệt**.

Không đồng nhất “kế thừa dependency declaration” với “kế thừa source code”, “tham chiếu project” hoặc “copy file”. Một project dependency có thể kéo các task build của producer vào graph khi consumer cần artifact, nhưng `extendsFrom` bản thân nó không phải một task dependency.

## 10. Tại sao extendsFrom không tự sao chép attributes?

Gradle chọn module variant dựa vào những attributes như `Usage` (compile/runtime), `Category`, `LibraryElements`, JVM target version và attributes của plugin. Hai configurations có thể **kế thừa cùng dependency declarations** nhưng dùng attributes khác nhau để chọn **các artifacts khác nhau** từ một module.

Ví dụ:

~~~text
implementation (declarable)
       |
       +----> compileClasspath (resolvable, yêu cầu Java API)
       |
       +----> runtimeClasspath (resolvable, yêu cầu Java runtime)
~~~

`compileClasspath` và `runtimeClasspath` đều nhìn thấy `implementation`, nhưng không nhất thiết resolve ra **cùng một tập files**. Chúng có vai trò tiêu thụ khác nhau; resolution dựa vào attributes và metadata để chọn variant phù hợp.

Do đó:

- `extendsFrom` thừa hưởng dependencies/constraints/excludes/... chứ **không thừa hưởng attributes**.
- Không tự đưa tất cả dependency scopes vào một configuration rồi hy vọng Gradle chọn đúng JAR/API/runtime nếu chưa thiết lập attributes phù hợp.
- Với custom consumer của Java library/project dependency, cần dùng attributes theo nhu cầu tương thích; configuration không có attributes rõ ràng dễ dẫn đến lỗi variant selection.
- Trong phần lớn Java application/library đơn giản, nên dùng `compileClasspath`/`runtimeClasspath` do plugin tạo thay vì tự tạo configuration resolvable mới mà không hiểu thuộc tính của nó.

### 10.1. Vai trò cũng không được kế thừa

~~~text
implementation: canBeDeclared=true
                canBeResolved=false
                canBeConsumed=false
         |
         v
runtimeClasspath: canBeDeclared=false
                  canBeResolved=true
                  canBeConsumed=false
~~~

Lược đồ này minh họa chủ đích của những configuration do Java plugin quản lý trong các phiên bản Gradle hiện đại. Quan hệ `runtimeClasspath.extendsFrom(implementation)` **không biến `implementation` thành resolvable**, cũng không làm `runtimeClasspath` nhận cờ `canBeDeclared=true`.

Một lỗi thường gặp là gọi:

~~~kotlin
// KHÔNG NÊN: implementation thuộc role declarable.
val jars = configurations.getByName("implementation").files
~~~

Đây là thao tác **resolve** một configuration không dành cho việc resolve. Thay vào đó, nếu thực sự cần các artifact runtime (và đã hiểu tác động của việc resolve), dùng resolvable configuration như:

~~~kotlin
val runtimeFiles = configurations.getByName("runtimeClasspath")
~~~

Đây chỉ là tham chiếu một configuration trong configuration phase; **không** tự gọi `.files` ở top-level để eager resolve mọi dependency. Với task tùy chỉnh, nên nối provider/configuration vào task file input và để Gradle resolve vào thời điểm hợp lệ.

## 11. Hai khái niệm “transitive” khác nhau

### 11.1. Transitive configuration inheritance

~~~text
commonDeps -> testDeps -> testClasspath
~~~

Nếu `testDeps.extendsFrom(commonDeps)` và `testClasspath.extendsFrom(testDeps)`, thì `testClasspath` nhìn thấy các dependency declarations khai báo ở `commonDeps` (cộng declarations từ các scope ở giữa).

### 11.2. Transitive module dependencies

~~~text
Project của bạn -> module A -> module B -> module C
~~~

Khi module A khai báo B và B khai báo C trong metadata, Gradle có thể lấy cả B/C khi resolve một dependency trên A. Hành vi này được điều chỉnh bởi metadata, constraints, exclusions và thuộc tính transitivity của configuration/dependency.

**Chúng không đồng nhất:** `extendsFrom` nói configuration này thừa hưởng declarations từ configuration khác; `transitive = false` (hoặc `isTransitive = false` trên configuration hỗ trợ API tương ứng) nói tới việc có lấy dependency bắc cầu từ module hay không. Tắt module transitivity **không tương đương xóa quan hệ `extendsFrom`** hoặc chỉ giữ dependencies được khai báo trực tiếp ở configuration con.

### 11.3. Ví dụ khác biệt bằng mô hình

Giả sử:

~~~text
sharedDeps:
  A (module A -> B)

smokeDeps.extendsFrom(sharedDeps):
  C

smokeClasspath.extendsFrom(smokeDeps):
  (resolvable)
~~~

Ở mức **declarations** mà `smokeClasspath` nhìn thấy: A và C. Ở mức **resolved graph**, có thể gồm A, B, C (và phụ thuộc khác của chúng). Nếu module B xung đột phiên bản với một dependency khác, Gradle còn phải chọn phiên bản cuối; không thể dự đoán chỉ từ thứ tự khai báo trong build script.

Để kiểm tra, hãy xem `gradle dependencies --configuration smokeClasspath` hoặc `dependencyInsight`, không chỉ quan sát danh sách direct declarations.

## 12. Dependency constraints, excludes và phiên bản: ảnh hưởng tới child

### 12.1. Constraint kế thừa có thể thay đổi lựa chọn phiên bản

Ví dụ minh họa với Gradle Kotlin DSL và scope có sẵn từ Java plugin:

~~~kotlin
plugins {
    id("java")
}

dependencies {
    constraints {
        implementation("org.apache.commons:commons-lang3:3.14.0") {
            because("Chọn phiên bản đã kiểm thử cho ứng dụng")
        }
    }

    testImplementation("org.apache.commons:commons-lang3:3.12.0")
}
~~~

Đây là **đoạn cấu hình**, giả định repository phù hợp. Vì `testImplementation` kế thừa `implementation`, constraint khai báo cho implementation cũng tham gia vào resolution liên quan test. Gradle có thể chọn phiên bản cuối theo toàn bộ dependency/constraint graph; **không** suy luận “lệnh testImplementation ghi sau sẽ thắng”. Với ràng buộc nghiêm ngặt `strictly`, metadata và các yêu cầu phiên bản khác, kết quả có thể là một conflict thay vì tự chọn phiên bản.

Quan trọng: constraint **không** tự mang module vào graph. Trong ví dụ, module hiện diện vì có `testImplementation(...)` thực tế.

### 12.2. Exclude rule được thừa hưởng có thể tạo bất ngờ

Nếu thêm một **configuration-level exclude** vào `implementation`, các child cấu hình có quan hệ kế thừa có thể nhận exclude rule đó. Điều này có thể ảnh hưởng classpath main/test và variant runtime. Vì vậy **không** đặt exclude toàn cục chỉ để sửa một test task cụ thể nếu nó còn ảnh hưởng các scope khác.

Một dependency-level exclude thường có phạm vi hẹp hơn:

~~~kotlin
dependencies {
    implementation("org.example:client:1.0") {
        exclude(group = "org.example", module = "old-logger")
    }
}
~~~

Đây là cú pháp minh họa; không khẳng định `org.example:client` là module tồn tại. Lưu ý exclude trong một dependency declaration khác với exclude trên configuration. Khi nhiều nhánh graph cùng kéo dependency, các yêu cầu hợp lệ khác có thể khiến module tiếp tục hiện diện.

### 12.3. Quan hệ inheritance không giải quyết mọi version conflict

Các giải pháp thường có mục đích khác nhau:

- `extendsFrom`: tái sử dụng dependency declarations/constraints/excludes giữa configurations.
- Dependency constraint: biểu đạt kỳ vọng/ràng buộc phiên bản.
- Platforms/BOM: tập trung quản lý phiên bản tương thích của nhóm modules.
- Component metadata rules và resolution strategy: điều chỉnh resolution trong tình huống đặc biệt.
- Exclude: ngăn một module/nhánh không mong muốn theo cơ chế của Gradle.
- Variant attributes: chọn dạng artifact/API/runtime phù hợp với consumer.

Không lạm dụng `extendsFrom` để giải quyết xung đột phiên bản hoặc biến một dependency runtime-only thành compile-time chỉ vì “cho hết vào một chỗ”.

## 13. Phạm vi kế thừa trong các source sets và test suites

Java plugin cung cấp scope mặc định cho `main` và `test`. Khi thêm source set mới, plugin có thể tạo các configurations mang tên theo source set, ví dụ `integrationTestImplementation`, `integrationTestRuntimeOnly`, `integrationTestRuntimeClasspath`, tùy cách bạn khai báo.

Nếu muốn mã integration test dùng các dependency giống unit test, có thể **cấu hình kế thừa có chủ đích**. Ví dụ sau chỉ nêu phần **configuration** sau khi đã tạo source set tên `integrationTest`:

~~~kotlin
configurations.named("integrationTestImplementation") {
    extendsFrom(configurations.getByName("testImplementation"))
}

configurations.named("integrationTestRuntimeOnly") {
    extendsFrom(configurations.getByName("testRuntimeOnly"))
}
~~~

Đây không phải project chạy độc lập, vì chưa tạo source set `integrationTest`, task test tương ứng, Java files hoặc test runner. Khi triển khai thực tế, cần làm đủ các bước ấy hoặc dùng JVM Test Suite plugin phù hợp. `extendsFrom` chỉ dùng lại declarations; nó **không tự tạo hoặc chạy** một test suite.

**Cẩn thận phạm vi:** Nếu thêm một thư viện chỉ dành cho `integrationTestImplementation`, `testImplementation` **không bị ảnh hưởng ngược lại**. Nhưng nếu chọn để `testImplementation` kế thừa ngược từ `integrationTestImplementation`, unit test lại có thể mang những thư viện chỉ dành cho integration test.

### 13.1. Vì sao không chỉ dùng testImplementation cho tất cả?

Với dự án nhỏ, tái sử dụng `testImplementation` có thể hợp lý. Với dự án lớn, integration test có thể cần HTTP client, testcontainers, driver database hoặc các công cụ tốn tài nguyên mà unit test không cần. Nên giữ scope riêng:

~~~text
implementation --------------------+
      |                            |
      v                            v
testImplementation          integrationTestImplementation
      |                            |
      v                            v
testRuntimeClasspath       integrationTestRuntimeClasspath
~~~

Dựa vào mục tiêu mà cho integration scope kế thừa từ `testImplementation` hoặc chỉ từ `implementation`. Không có “một cây kế thừa bắt buộc” cho mọi tổ chức; điều đúng là **mỗi scope nhận đúng các dependency nó cần**.

## 14. Các lệnh kiểm tra configuration và dependency graph

Gradle có các task báo cáo giúp phân biệt **configuration nào tồn tại** với **classpath nào resolve ra những module/artifact nào**.

### 14.1. Xem danh sách các configuration

~~~bash
gradle resolvableConfigurations
gradle consumableConfigurations
~~~

Các task báo cáo này được Gradle cung cấp trong nhiều phiên bản hiện đại. Tên, nội dung và độ chi tiết có thể phụ thuộc plugin/Gradle version. Nếu task không có trong bản đang dùng, xem `gradle tasks --all` hoặc dùng các báo cáo dependency được hỗ trợ.

### 14.2. Xem dependencies của một resolvable configuration

~~~bash
gradle dependencies --configuration runtimeClasspath
gradle dependencies --configuration testRuntimeClasspath
~~~

Báo cáo mô tả resolved dependency graph cho classpath tương ứng. Với dependency chỉ là file JAR trong ví dụ mục 8, báo cáo dependency theo **module coordinates** có thể không biểu diễn đầy đủ file dependency; hãy xác minh bằng khả năng compile/run và classpath file thực tế thay vì kết luận “không có JAR” chỉ từ một báo cáo module.

### 14.3. Truy vết một module và phiên bản

~~~bash
gradle dependencyInsight --dependency commons-lang3 --configuration runtimeClasspath
~~~

`dependencyInsight` giúp kiểm tra module xuất hiện qua nhánh nào, phiên bản nào được chọn và vì sao. Task này cần graph có dependency phù hợp; với dự án local JAR không có module `commons-lang3`, nó sẽ không tìm được module đó.

### 14.4. Đừng resolve declarable configuration để chẩn đoán

Lệnh hoặc code cố lấy file trực tiếp từ `implementation` có thể báo lỗi vai trò configuration. Đúng hơn:

- **Muốn hiểu khai báo:** kiểm tra `implementation`, các parent trong `extendsFrom` và dependency declarations.
- **Muốn hiểu classpath compile:** resolve/xem `compileClasspath`.
- **Muốn hiểu classpath runtime:** resolve/xem `runtimeClasspath`.
- **Muốn hiểu classpath test:** xem `testCompileClasspath`/`testRuntimeClasspath`.
- **Muốn hiểu variant xuất bản:** xem consumable configurations và attributes/metadata của Java Library plugin.

Đừng truy cập configuration của **project khác** và gọi `.files` từ task action. Việc resolve cấu hình xuyên project theo cách này có thể bị Gradle cảnh báo không an toàn; hãy khai báo project dependency đúng cách.

## 15. Anti-patterns và lỗi thường gặp

### Lỗi 1. Đảo chiều extendsFrom

Bạn muốn child nhận dependency của parent nhưng viết:

~~~kotlin
configurations.named("parent") {
    extendsFrom(configurations.getByName("child"))
}
~~~

Sửa thành `child.extendsFrom(parent)`. Đọc tên bên trái của dấu chấm là **đối tượng được thêm cha**, không phải “gửi dependency cho child”.

### Lỗi 2. Cho rằng inheritance hai chiều

`A.extendsFrom(B)` cho A thấy dependency B, **không** làm B thấy dependency A. Đây là khác biệt cơ bản của inheritance có hướng.

### Lỗi 3. Cho rằng extendsFrom sao chép thuộc tính variant

Attributes **không được thừa hưởng**. Custom resolvable/consumable configuration vẫn cần attributes phù hợp để Gradle chọn variant của project/module. Không đoán “cùng dependency là cùng artifact”.

### Lỗi 4. Cho rằng child nhận vai trò của parent

`implementation` chỉ để declare, `runtimeClasspath` để resolve; dù runtimeClasspath kế thừa implementation, `implementation` vẫn không trở thành resolvable. Đặt vai trò đúng khi tạo custom configurations.

### Lỗi 5. Trộn compileOnly vào runtime hoặc runtimeOnly vào compile vô cớ

Nếu ép `runtimeClasspath` kế thừa `compileOnly`, một dependency chỉ cần lúc compile có thể xuất hiện ở runtime trái mục đích. Nếu ép `compileClasspath` kế thừa `runtimeOnly`, compile có thể vô tình dùng một API vốn không được dự kiến. Hãy hiểu scope trước khi thêm relation.

### Lỗi 6. Tự sửa cấu hình Java plugin đã đúng

Plugin Java/Java Library đã định nghĩa những quan hệ cơ bản. Tạo thêm relation “cho chắc” có thể gây duplicate declarations, version conflicts hoặc dependency leak. Trước khi sửa, dùng báo cáo và đối chiếu graph hiện tại theo đúng phiên bản Gradle.

### Lỗi 7. Dùng extendsFrom qua hai project

Không thể dùng `project(":lib").configurations.getByName("implementation")` làm parent của `:app:implementation`. Dùng `implementation(project(":lib"))` để Gradle xử lý variants/artifacts và quan hệ build task theo cách chuẩn.

### Lỗi 8. Tạo chu trình parent/child

~~~text
a extendsFrom b
b extendsFrom c
c extendsFrom a   <- vòng lặp
~~~

Gradle phải có thứ tự inheritance hợp lệ. Sửa bằng cách tách một `commonDeps` đứng ở trên làm parent cho các configuration khác, thay vì nối vòng.

### Lỗi 9. Resolve configuration chỉ dùng để declare

Nếu code gọi `configurations.getByName("implementation").files`, nó cố resolve dependency bucket. Dùng resolvable configuration, hoặc nối configuration vào task input của Gradle khi cần.

### Lỗi 10. Tin rằng extendsFrom tự thêm thư viện vào compile của project khác

Với `java-library`, `implementation` và `api` có mục tiêu khác nhau. Dependency trong implementation của producer không tự lộ ra compile classpath của consumer; Gradle dựa vào variant-aware metadata.

### Lỗi 11. Dùng dependency graph để suy thứ tự task action

`extendsFrom` chỉ liên quan dependency configuration. `tasks.register`, `dependsOn` hay action `doLast` thuộc **task graph**, là tầng khác. Có thêm một module dependency không có nghĩa Gradle chạy một task tùy ý có tên giống module.

### Lỗi 12. Không thấy module rồi tưởng Gradle bỏ inheritance

Có thể classpath đang kiểm tra sai scope, repository không có module, constraint/conflict chọn phiên bản khác, dependency bị exclude, hoặc một file dependency không hiển thị như module coordinate trong báo cáo. Kiểm tra **resolvable classpath thật** và nguồn khai báo.

### Lỗi 13. Cho mọi thứ kế thừa từ implementation

Không phải dependency nào cũng dành cho compile và runtime của mã chính. Annotation processor, test-only tool, compile-only API và runtime driver nên đặt ở scope đúng. Một “super configuration” dùng cho tất cả sẽ làm classpath lớn, tăng rủi ro conflict và làm sai hợp đồng API.

### Lỗi 14. Resolve trong configuration phase vì muốn debug

Lấy `.files` hoặc `resolve()` sớm có thể tốn I/O, gây download và khóa mô hình trước khi plugin khác hoàn tất cấu hình, tương tác không tốt với Configuration Cache. Ưu tiên task báo cáo và cơ chế Provider/FileCollection khai báo thay vì resolve eager.

### Lỗi 15. Diễn giải sai nghĩa inherited constraint/exclude

Constraint kế thừa có thể ảnh hưởng **version selection**, nhưng không tự thêm dependency. Exclude kế thừa có thể ảnh hưởng graph, nhưng cần xét các nhánh kéo module vào graph. Không coi inherited declarations là danh sách kết quả đã resolve chắc chắn.

## 16. Phương pháp thiết kế configuration inheritance an toàn

Trước khi thêm `extendsFrom`, tự trả lời:

1. **Scope nào khai báo giá trị nguồn?** Ví dụ `commonTestLibs`.
2. **Scope nào cần nhận giá trị?** Ví dụ `integrationTestImplementation`.
3. **Hướng đúng chưa?** `integrationTestImplementation.extendsFrom(commonTestLibs)`.
4. **Mục đích là tái sử dụng declarations hay cần một project dependency?** Hai việc khác nhau.
5. **Configuration con được dùng để declare, resolve hay consume?** Thiết lập cờ vai trò tương ứng.
6. **Nếu con được resolve/consume, attributes đã phù hợp chưa?** Không giả định thừa hưởng.
7. **Có dependency constraints/excludes/artifacts/capabilities ở parent có thể gây tác động ngoài ý muốn không?** Nhìn toàn bộ graph.
8. **Quan hệ có làm dependency test chỉ dùng cho môi trường đặc biệt lọt vào main/runtime không?** Không mở rộng scope quá mức.
9. **Có chu trình hoặc kế thừa chéo Project không?** Phải tránh.
10. **Kiểm chứng ở classpath thực tế:** dùng report và chạy task compile/test/run đúng mục đích.

Mục tiêu không phải tạo **ít configuration nhất**, mà tạo **những configuration có tên, vai trò và phạm vi chính xác**, dùng inheritance để tránh lặp declaration khi thật sự hợp lý.

## 17. Bài tập tự kiểm tra có đáp án

### Bài 1. Đoán tập khai báo được kế thừa

Có:

~~~text
baseDeps: A, B
featureDeps: C, extendsFrom(baseDeps)
runtimeFiles: extendsFrom(featureDeps)
~~~

Hỏi: những declaration nào `runtimeFiles` có thể nhìn thấy? `baseDeps` có tự nhận C không?

**Đáp án:** `runtimeFiles` nhìn thấy A, B, C qua hai tầng inheritance. `baseDeps` vẫn chỉ có A, B; quan hệ không truyền dependency ngược.

### Bài 2. Đổi chiều cho đúng

Cần để `integrationTestImplementation` dùng thư viện từ `testImplementation`. Đoạn nào đúng?

~~~kotlin
// A
configurations.named("integrationTestImplementation") {
    extendsFrom(configurations.getByName("testImplementation"))
}

// B
configurations.named("testImplementation") {
    extendsFrom(configurations.getByName("integrationTestImplementation"))
}
~~~

**Đáp án:** A, giả định hai configurations đã tồn tại. B làm unit test kế thừa dependency riêng của integration test, trái mục tiêu.

### Bài 3. Vai trò có di chuyển theo extendsFrom không?

`runtimeClasspath` là resolvable và kế thừa `implementation` declarable. Có thể resolve `implementation` vì runtimeClasspath resolve được không?

**Đáp án:** Không. `extendsFrom` không di chuyển `canBeResolved` từ child sang parent; các cờ thuộc riêng từng configuration.

### Bài 4. Attributes có được kế thừa không?

Custom `ciRuntime` kế thừa một parent có attribute JVM target và Usage. `ciRuntime` tự nhận attributes đó chứ?

**Đáp án:** Không. Gradle không kế thừa configuration attributes qua `extendsFrom`; resolvable configuration phải được cấu hình attributes cần thiết, nhất là khi chọn project/module variants.

### Bài 5. Constraints có kéo module vào graph không?

`commonDeps` có constraint cho module A nhưng không chứa dependency A, child cũng không kéo A từ bất kỳ nơi nào. Chỉ vì constraint được kế thừa, A có xuất hiện như direct dependency không?

**Đáp án:** Không. Constraint ràng buộc version của module khi module tham gia resolution, không tự tạo một dependency.

### Bài 6. Tách module transitivity và config inheritance

`child.extendsFrom(parent)`; trong parent có dependency module X, X phụ thuộc module Y. Cơ chế nào làm child thấy X, cơ chế nào có thể làm Y được resolve?

**Đáp án:** `extendsFrom` làm child thấy declaration X từ parent. Module dependency transitivity mới có thể làm Y xuất hiện trong resolved graph. Hai quan hệ không đồng nhất.

### Bài 7. Java Library API exposure

Một project thư viện dùng `implementation("group:internal:1.0")` và `api("group:public:1.0")`. Consumer project phụ thuộc thư viện. Thư viện `internal` có mặc nhiên được cung cấp cho **compile classpath của consumer** không?

**Đáp án:** Không. `api` được dành cho API compile của consumer; `implementation` dùng nội bộ producer và có thể đi theo runtime variant. Kết quả cụ thể còn do metadata/attributes và variant selection.

### Bài 8. Thấy JAR trong app nhưng không khai báo trực tiếp

Trong ví dụ mục 8, `implementation` không chứa dòng `implementation(files("libs/shared.jar"))`. Vì sao `demo.app.Main` vẫn biên dịch được?

**Đáp án:** `sharedLibs` trực tiếp khai báo local file dependency; `implementation.extendsFrom(sharedLibs)` làm implementation nhìn thấy nó; `compileClasspath` và `runtimeClasspath` của Java plugin kế thừa implementation. Compiler và JavaExec nhận file JAR khi resolve classpath.

### Bài 9. Chọn configuration đúng để xem kết quả

Bạn muốn xem những module xuất hiện trên runtime classpath của Java application. Chạy báo cáo với `implementation` hay `runtimeClasspath`?

**Đáp án:** `runtimeClasspath`. `implementation` là bucket khai báo, không phải configuration để resolve trực tiếp.

### Bài 10. Sửa lỗi cross-project inheritance

Project `:app` đang cố cho `implementation` kế thừa `:library:implementation` bằng cách lấy đối tượng Configuration từ project khác. Sửa thế nào?

**Đáp án:** Giữ mỗi project quản lý configurations của nó. Ở `:app`, khai báo `implementation(project(":library"))` sau khi settings đã khai báo `include(":app", ":library")`, và áp dụng plugin phù hợp cho `:library` để xuất variant/artifact tiêu thụ được.

## 18. Bảng ghi nhớ cuối bài

| Khái niệm | Cách hiểu ngắn |
| --- | --- |
| `child.extendsFrom(parent)` | Child kế thừa dependency-related declarations của parent |
| Nhiều parents | Child hợp nhất declarations từ các parent trước khi resolve |
| Nhiều tầng inheritance | Child ở cuối có thể nhìn thấy declarations của ancestor |
| Dependencies | Kế thừa |
| Dependency constraints | Kế thừa, ảnh hưởng version selection khi module tham gia graph |
| Exclude rules | Kế thừa, có thể ảnh hưởng resolved graph |
| Artifacts/capabilities | Kế thừa theo API configuration |
| Attributes | **Không** kế thừa |
| `canBeDeclared`/`canBeResolved`/`canBeConsumed` | **Không** kế thừa |
| `implementation` | Dependency scope cho mã chính |
| `testImplementation` | Dependency scope cho test, thường kế thừa implementation |
| `compileClasspath` / `runtimeClasspath` | Resolvable classpaths do plugin tạo |
| `api` vs `implementation` trong Java Library | Ranh giới API compile của consumer và dependency nội bộ |
| `project(":lib")` | Khai báo project dependency xuyên project, không dùng `extendsFrom` |
| Transitive config inheritance | Kế thừa declarations qua nhiều configurations |
| Transitive module dependency | Resolve phụ thuộc bắc cầu giữa các module |
| Configuration Cache | Tối ưu cấu hình build; khác dependency configurations |
| `gradle dependencies --configuration ...` | Xem resolved dependency graph của configuration tương ứng |
| `gradle dependencyInsight ...` | Truy vết nguyên nhân/version của module |

**Kết luận:** `extendsFrom` là cơ chế **tái sử dụng các khai báo liên quan dependency giữa các configurations trong cùng Project**. Nó không phải Java class inheritance, không phải task dependency, không tự tạo project dependency và không sao chép attributes/vai trò. Hãy cho child kế thừa đúng parent, giữ declarable/resolvable/consumable rõ ràng, và xác minh kết quả ở **classpath/variant được resolve** thay vì chỉ đếm các dòng `dependencies { ... }`.

## Tài liệu tham khảo chính thức

- [Gradle — Creating Dependency Configurations](https://docs.gradle.org/current/userguide/declaring_configurations.html) — configuration roles, inheritance, những thành phần được/không được kế thừa.
- [Gradle — Dependency Configurations](https://docs.gradle.org/current/userguide/dependency_configurations.html) — phạm vi dependency trong Java/JVM.
- [Gradle — Java Plugin](https://docs.gradle.org/current/userguide/java_plugin.html) — configuration hierarchy và các Java source sets.
- [Gradle — Java Library Plugin](https://docs.gradle.org/current/userguide/java_library_plugin.html) — `api`, `implementation`, publish/consumer variants.
- [Gradle — Configuration API](https://docs.gradle.org/current/javadoc/org/gradle/api/artifacts/Configuration.html) — `extendsFrom`, `getExtendsFrom` và các role flags.
- [Gradle — Viewing and Debugging Dependencies](https://docs.gradle.org/current/userguide/viewing_debugging_dependencies.html) — `dependencies`, `dependencyInsight` và phiên bản được chọn.
