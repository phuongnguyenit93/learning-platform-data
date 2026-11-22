# Gradle: mô hình Project, Task, Plugin và Dependency cùng mối quan hệ

## 1. Bức tranh tổng thể

Gradle là công cụ tự động hóa build. Khi chạy một lệnh như `./gradlew :app:build`, Gradle không chỉ thực thi một đoạn script theo thứ tự từ trên xuống; nó tạo mô hình build, xác định các công việc cần chạy rồi thực thi chúng theo quan hệ phụ thuộc.

| Thành phần | Câu hỏi trả lời | Vai trò chính | Ví dụ |
| --- | --- | --- | --- |
| **Project** | Đang cấu hình và build phần nào? | Đơn vị tổ chức trong một build; chứa cấu hình, plugin, task và dependency. | Project gốc `:`; project con `:core`, `:app`. |
| **Plugin** | Project này có năng lực build nào? | Bổ sung quy ước, task, extension và configuration vào Project. | `java-library`, `application`. |
| **Task** | Cần thực hiện công việc gì? | Đơn vị thực thi của Gradle, có thể có action, đầu vào/đầu ra và quan hệ với các task khác. | `:app:compileJava`, `:app:run`, `:app:build`. |
| **Dependency** | Mã nguồn cần thành phần nào để biên dịch/chạy? | Khai báo thư viện, module, project hoặc file dùng trên classpath/các cấu hình khác. | `implementation project(':core')`, `implementation 'group:name:version'`. |

**Mối quan hệ cốt lõi:** một build có một hoặc nhiều Project; Plugin được áp dụng vào Project và tạo/cấu hình các thành phần của Project; Project sở hữu các Task; các Dependency nằm trong những configuration của Project; Gradle chọn và sắp thứ tự Task cần chạy để cung cấp artifact, biên dịch, kiểm thử và đóng gói.

```text
Build (settings.gradle)
  ├── Project :
  ├── Project :core
  │     ├── Plugin: java-library
  │     ├── Task: compileJava, jar, build, ...
  │     └── Dependency configurations: api, implementation, ...
  └── Project :app
        ├── Plugin: application
        ├── Task: compileJava, run, build, ...
        └── Dependency: implementation project(':core')

Task graph: các task liên hệ qua dependsOn và yêu cầu tạo artifact.
Dependency graph: các module/artifact liên hệ qua các khai báo dependency.
```

Hai loại đồ thị trên **liên quan nhưng không đồng nhất**: `implementation project(':core')` mô tả phụ thuộc mã/thư viện; `dependsOn tasks.named('check')` mô tả quan hệ thực thi giữa task.

## 2. Project — đơn vị tổ chức build

Đối tượng `Project` đại diện cho một thành phần trong build Gradle. Mỗi project có đường dẫn logic, ví dụ `:` (root), `:core`, `:app`, và thường có file build riêng (`build.gradle` dùng Groovy DSL hoặc `build.gradle.kts` dùng Kotlin DSL). `settings.gradle`/`settings.gradle.kts` định nghĩa cấu trúc build, đặc biệt những project nào được `include`.

```groovy
// settings.gradle
rootProject.name = 'gradle-model-demo'
include 'core', 'app'
```

Với cấu hình này, `:core` và `:app` là hai project con cùng thuộc một build; tên trong `include` là đường dẫn project, không phải tên class Java. Project gốc vẫn tồn tại ngay cả khi không có mã nguồn Java. Các project con thường tương ứng với thư mục, nhưng Gradle cũng cho phép ánh xạ `projectDir` sang thư mục khác.

Trong `build.gradle`, các khối `plugins`, `repositories`, `dependencies`, `tasks` và các extension của plugin đều đang cấu hình **project hiện tại**. Vì vậy `:app:build` nghĩa là task tên `build` của project `:app`, trong khi `:core:build` là task khác. Một build đa project chia sẻ cùng lần chạy Gradle nhưng không có nghĩa mọi project dùng cùng plugin hay thư viện.

## 3. Plugin — bổ sung năng lực và quy ước

Plugin là mã cấu hình được áp dụng cho một Project. Ví dụ:

```groovy
plugins {
    id 'java-library'
}
```

Plugin `java-library` hỗ trợ build thư viện Java: tích hợp chức năng của Java plugin, thêm task liên quan đến biên dịch/đóng gói/kiểm thử, cùng các configuration như `api`, `implementation`, `testImplementation`. Plugin `application` bổ sung cách xác định main class và task `run` để chạy ứng dụng Java.

Plugin **không phải một task được chạy mỗi lần build**. Nó tham gia quá trình cấu hình Project; các task do plugin tạo ra chỉ chạy khi nằm trong đồ thị task được yêu cầu. Plugin có thể đóng góp các thành phần sau:

- **Task** (ví dụ `compileJava`, `test`, `jar`, `run`) và quan hệ giữa chúng.
- **Extension** để người dùng cung cấp cấu hình, như `application { mainClass = 'demo.app.Main' }`.
- **Configuration** để khai báo/giải quyết/cung cấp dependency, như `implementation` và `runtimeClasspath`.
- **Quy ước** về đường dẫn mã nguồn (`src/main/java`), artifact, test và các thuộc tính liên quan.

Plugin có thể được áp dụng bởi `plugins { id '...' }` hoặc theo cơ chế `apply plugin: '...'` trong các tình huống phù hợp. Với plugin cộng đồng, thường cần phiên bản/plugin repository; hai plugin có sẵn trong ví dụ này (`java-library`, `application`) không cần tự ghi phiên bản. Khai báo plugin trong một project không tự động áp dụng plugin đó cho mọi project con.

## 4. Task — đơn vị thực thi và đồ thị công việc

Task là một công việc Gradle có tên, thuộc một Project và có thể chứa action thực hiện lúc chạy. Task cũng có thể là task vòng đời (`build`, `check`) chỉ phối hợp các task khác thay vì tự xử lý file.

```groovy
// app/build.gradle
tasks.register('sayHello') {
    group = 'learning'
    description = 'In lời chào khi task chạy'
    doLast {
        println 'Xin chào từ task Gradle'
    }
}

tasks.register('prepareDemo') {
    group = 'learning'
    dependsOn tasks.named('sayHello')
    doLast {
        println 'Đã chuẩn bị xong'
    }
}
```

`tasks.register` đăng ký task theo cách trì hoãn cấu hình (configuration avoidance): Gradle không cần hiện thực hóa mọi task không liên quan. `doLast` là action thực thi khi task chạy; phần cấu hình xung quanh được Gradle đánh giá để tạo mô hình. Chạy `:app:prepareDemo` sẽ yêu cầu `:app:sayHello` chạy trước.

**Phân biệt các quan hệ giữa task:**

- `dependsOn`: task đích thực sự phụ thuộc vào task khác; Gradle thêm task phụ thuộc vào đồ thị và chạy nó trước khi task đích có thể hoàn tất.
- `mustRunAfter`: áp thứ tự nếu **cả hai** task đều đã được chọn; bản thân nó không buộc task kia xuất hiện trong đồ thị.
- `shouldRunAfter`: gợi ý thứ tự yếu hơn, cũng không kéo task kia vào đồ thị.
- `finalizedBy`: yêu cầu task dọn dẹp/kết thúc sau task được finalizer gắn vào, thường dùng cho cleanup.

Trong các plugin Java, task `build` thường phụ thuộc vào `assemble` và `check`; `assemble` phụ thuộc vào các task tạo artifact cần thiết; `check` kết nối các bước xác minh. Đồ thị có thứ tự theo ràng buộc, không nhất thiết trùng với thứ tự khai báo trong file `build.gradle`. Gradle có thể chạy song song những task không bị ràng buộc thứ tự (khi được cấu hình phù hợp). Quan hệ phụ thuộc vòng tròn giữa task là lỗi cấu hình.

Để Gradle quyết định task có cần chạy lại, plugin/task có thể công bố input, output, hoặc cacheability. Khi input/output không đổi, Gradle có thể báo `UP-TO-DATE` hoặc dùng kết quả cache (nếu điều kiện cho phép). Một task tùy biến chỉ có `doLast { println ... }` như trên không tự nhiên có output file để kiểm tra up-to-date.

## 5. Dependency — mô hình thư viện và classpath

Dependency là đầu vào mà project cần để build, kiểm thử hoặc chạy chương trình. Khai báo nằm trong một **configuration** do plugin cung cấp hoặc người dùng tự tạo. Thường gặp ba loại:

```groovy
dependencies {
    implementation project(':core')               // project khác trong cùng build
    implementation 'org.apache.commons:commons-lang3:3.17.0' // module bên ngoài
    // implementation files('libs/local-library.jar')       // file JAR cục bộ
}
```

Đoạn trên chỉ minh họa các hình thức khai báo: nếu dùng thư viện ngoài phải khai báo repository như `repositories { mavenCentral() }`, và máy cần truy cập/có cache artifact. Ví dụ chạy ở phần 7 chỉ dùng `project(':core')` nên không bắt buộc tải thư viện ngoài.

Trong dự án Java, các configuration thường dùng có ý nghĩa khác nhau:

| Configuration | Ý nghĩa điển hình |
| --- | --- |
| `implementation` | Cần cho biên dịch mã của project và khi chạy; với `java-library` không đưa dependency triển khai đó vào compile classpath của project tiêu thụ. |
| `api` | Do plugin `java-library` cung cấp; dependency là một phần API công khai của thư viện và được đưa đến compile classpath của project tiêu thụ. |
| `compileOnly` | Cần lúc biên dịch nhưng không tự được đưa vào runtime classpath. |
| `runtimeOnly` | Chỉ cần lúc chạy, không có mặt trên compile classpath chính. |
| `testImplementation` | Dùng cho biên dịch/chạy kiểm thử của project; không mặc nhiên là dependency của sản phẩm phát hành. |
| `testRuntimeOnly` | Chỉ cần ở runtime của kiểm thử. |

Ví dụ, nếu public method của `:core` trả về một kiểu từ thư viện `X`, phía sử dụng `:core` có thể cần `X` trên compile classpath: trong `java-library`, cân nhắc `api 'group:x:version'`. Nếu `X` chỉ được dùng bên trong implementation của `:core`, dùng `implementation` để hạn chế lộ chi tiết triển khai. Không gán `api` cho mọi thư viện theo thói quen.

Gradle phân biệt **declarable configuration** để khai báo phụ thuộc (như `implementation`) với **resolvable configuration** để giải quyết classpath (như `compileClasspath`, `runtimeClasspath`) và configuration tiêu thụ artifact/variant. Các plugin tạo các liên hệ giữa chúng. Lúc thực sự cần classpath, Gradle giải quyết module, phiên bản, phụ thuộc bắc cầu và biến thể thích hợp.

Một dependency bên ngoài cũng không phải task: `implementation 'group:name:version'` không làm xuất hiện một task tên `name`. Ngược lại, `dependsOn` không cung cấp classpath cho Java. Với `implementation project(':core')`, Gradle vừa chọn artifact/variant do `:core` cung cấp, vừa có thể thiết lập quan hệ với các task sản xuất artifact cần thiết; không nên thêm `dependsOn(':core:build')` một cách máy móc để thay thế dependency project.

## 6. Các thành phần phối hợp như thế nào?

Xét yêu cầu `./gradlew :app:run`:

1. `settings.gradle` xác định build có `:core` và `:app` (các đối tượng Project).
2. Gradle cấu hình những project cần thiết, áp dụng `java-library` cho `:core` và `application` cho `:app` (Plugin). Các plugin tạo task, configuration và extension.
3. `:app` khai báo `implementation project(':core')` (Dependency). Khi `:app` cần compile/runtime classpath, Gradle chọn đầu ra phù hợp từ `:core` và các dependency liên quan.
4. Task `:app:run` có các yêu cầu về lớp đã biên dịch và runtime classpath. Gradle dựng task graph với các task sản xuất dữ liệu cần thiết, ví dụ những task biên dịch của `:core` và `:app`.
5. Gradle chạy các task theo ràng buộc. Chương trình Java trong `:app` gọi lớp của `:core` qua classpath đã được giải quyết.

```text
Project :app
  application plugin
       | tạo/cấu hình
       v
  Task :app:run  ----------> cần classes + runtimeClasspath
                                   |
                                   v
                           Dependency project(':core')
                                   |
                                   v
                            Project :core
                              java-library plugin
                              các task sản xuất classes/JAR
```

**Điểm mấu chốt:** Dependency graph quyết định *thành phần phần mềm nào cần được cung cấp*; task graph quyết định *công việc nào và theo thứ tự nào tạo/tiêu thụ các thành phần ấy*. Hai đồ thị được nối với nhau qua task input/output, artifact và cơ chế variant-aware dependency resolution của Gradle.

## 7. Ví dụ hoàn chỉnh có thể chạy với Java 17+ (Groovy DSL)

Ví dụ gồm thư viện `core` và ứng dụng `app`. Ta không cần dependency ngoài để kiểm chứng cơ chế liên kết hai project.

```text
gradle-model-demo/
├── settings.gradle
├── core/
│   ├── build.gradle
│   └── src/main/java/demo/core/Greeting.java
└── app/
    ├── build.gradle
    └── src/main/java/demo/app/Main.java
```

**File `settings.gradle` — khai báo mô hình Project:**

```groovy
rootProject.name = 'gradle-model-demo'
include 'core', 'app'
```

**File `core/build.gradle` — thư viện Java:**

```groovy
plugins {
    id 'java-library'
}
```

**File `core/src/main/java/demo/core/Greeting.java`:**

```java
package demo.core;

public final class Greeting {
    private Greeting() {
    }

    public static String message() {
        return "Xin chào từ core";
    }
}
```

**File `app/build.gradle` — ứng dụng có project dependency và task riêng:**

```groovy
plugins {
    id 'application'
}

application {
    mainClass = 'demo.app.Main'
}

dependencies {
    implementation project(':core')
}

tasks.register('sayHello') {
    group = 'learning'
    description = 'Minh họa một task do người dùng khai báo'
    doLast {
        println 'Xin chào từ task Gradle'
    }
}

tasks.register('prepareDemo') {
    group = 'learning'
    dependsOn tasks.named('sayHello')
    doLast {
        println 'Đã chuẩn bị xong'
    }
}
```

**File `app/src/main/java/demo/app/Main.java`:**

```java
package demo.app;

import demo.core.Greeting;

public final class Main {
    private Main() {
    }

    public static void main(String[] args) {
        System.out.println(Greeting.message());
    }
}
```

Điều kiện chạy: cài JDK 17+ và dùng bản Gradle tương thích với JDK. Nếu dự án đã có Gradle Wrapper thì dùng wrapper hiện có; nếu chưa có, từ thư mục gốc chạy `gradle wrapper` một lần trên máy đã cài Gradle. Wrapper sẽ tạo các file `gradlew`, `gradlew.bat`, `gradle/wrapper/...`, giúp nhóm sử dụng phiên bản Gradle được cấu hình thống nhất.

```bash
# macOS/Linux, tại thư mục gradle-model-demo
./gradlew projects
./gradlew :app:run
./gradlew :app:prepareDemo
./gradlew :app:tasks --all
./gradlew :app:dependencies --configuration runtimeClasspath
./gradlew :app:prepareDemo --dry-run
```

Trên Windows, dùng `gradlew.bat` tương ứng, ví dụ `gradlew.bat :app:run` tại thư mục gốc.

Kết quả chương trình Java của `:app:run` in ra dòng sau (Gradle còn có thể in các dòng trạng thái task/build):

```text
Xin chào từ core
```

Khi chạy `:app:prepareDemo`, các action của hai custom task in đúng thứ tự:

```text
Xin chào từ task Gradle
Đã chuẩn bị xong
```

Ở đây `:app:prepareDemo` chạy `sayHello` trước nhờ `dependsOn`; nó không cần biên dịch `core` hay `app` vì bản thân hai custom task không tiêu thụ Java class. Ngược lại `:app:run` cần classpath và sẽ kéo vào đồ thị những task tạo output cần thiết. Dùng `--dry-run` để xem task được lựa chọn và quan hệ thứ tự mà không chạy action; dùng `dependencies` để xem dependency graph của `runtimeClasspath`. Các task cụ thể và trạng thái `UP-TO-DATE`/`FROM-CACHE` có thể thay đổi theo phiên bản Gradle và trạng thái build.

## 8. Vòng đời Gradle và vị trí của bốn thành phần

Gradle thường mô tả ba giai đoạn logic:

1. **Initialization:** xác định settings, build và các project tham gia.
2. **Configuration:** đọc/cấu hình build scripts, áp dụng plugin, khai báo dependency và đăng ký/cấu hình task cần thiết. `tasks.register` giúp tránh hiện thực hóa task không liên quan; dependency thường chỉ được giải quyết khi classpath thật sự được yêu cầu.
3. **Execution:** xây dựng/thực thi đồ thị task đã chọn theo ràng buộc và cơ chế kiểm tra input/output, cache, incremental work.

Phân biệt cấu hình và thực thi qua ví dụ:

```groovy
tasks.register('explain') {
    println 'Đang cấu hình task khi task được hiện thực hóa'
    doLast {
        println 'Đang chạy action của task'
    }
}
```

Dòng `println` trực tiếp trong khối đăng ký chạy **khi cấu hình task được hiện thực hóa**, không phải mỗi lần action được chạy; `doLast` chạy ở giai đoạn thực thi nếu task được chọn và không bị skip. Vì `register` trì hoãn hiện thực hóa, không được suy luận rằng mọi dòng cấu hình task đều chạy ngay khi Gradle đọc script.

## 9. Những nhầm lẫn thường gặp và cách kiểm tra

| Nhầm lẫn | Cách hiểu đúng / hành động |
| --- | --- |
| "Một `build.gradle` là một task." | `build.gradle` là script cấu hình Project; một Project có thể có nhiều task. |
| "Áp dụng plugin là chạy hết task của plugin." | Plugin thêm năng lực; chỉ task được yêu cầu hoặc là dependency trong task graph mới chạy. |
| "`implementation` giống `dependsOn`." | `implementation` mô tả dependency phần mềm/classpath; `dependsOn` mô tả quan hệ thực thi task. |
| "Khai báo project dependency thì phải `dependsOn(':core:build')`." | Hãy dùng `project(':core')` để Gradle xác định đầu ra/producer tasks; chỉ thêm quan hệ task thủ công khi có lý do riêng. |
| "Dùng `api` và `implementation` như nhau." | Với `java-library`, `api` lộ dependency ra compile classpath của consumer; `implementation` che chi tiết triển khai khỏi compile classpath của consumer. |
| "Task chạy theo thứ tự được viết." | Task chạy theo đồ thị phụ thuộc và ràng buộc thứ tự; có thể chạy song song nếu được phép. |
| "Không thấy task custom vì Gradle bị lỗi." | Kiểm tra đã áp dụng plugin đúng project, dùng đúng path `:app:taskName` và chạy `./gradlew :app:tasks --all`. |
| "`project(':core')` vẫn không tìm thấy." | Kiểm tra `settings.gradle` có `include 'core'`, đường dẫn logic chính xác và `:core` cung cấp artifact/variant phù hợp. |
| "Thêm thư viện ngoài mà Gradle không tải được." | Kiểm tra repository, tọa độ `group:name:version`, mạng/offline và khả năng tương thích của artifact. |

**Cách tự kiểm chứng một build thực tế:**

- Dùng `./gradlew projects` để xác định Project và đường dẫn project.
- Dùng `./gradlew :app:tasks --all` để xem Task mà plugin/script cung cấp.
- Dùng `./gradlew :app:help --task run` để đọc thông tin một task nếu nó tồn tại.
- Dùng `./gradlew :app:dependencies --configuration runtimeClasspath` để xem dependency graph.
- Dùng `./gradlew :app:compileJava --dry-run` để xem các task Gradle dự định chạy; đây là công cụ quan sát, không phải bằng chứng mọi artifact đã được build thành công.

## 10. Ghi nhớ mô hình

**Project** xác định *phạm vi cấu hình*; **Plugin** bổ sung *khả năng và quy ước*; **Dependency** mô tả *thứ cần cung cấp để biên dịch/chạy*; **Task** thực hiện *công việc cụ thể* theo đồ thị. Khi đọc một build Gradle, hãy đi từ `settings.gradle` → plugin của từng project → các configuration/dependency → những task và quan hệ thực thi mà lệnh người dùng kích hoạt.

Tài liệu chính thức để đào sâu: [Multi-Project Builds](https://docs.gradle.org/current/userguide/multi_project_builds.html), [Plugins](https://docs.gradle.org/current/userguide/plugins.html), [Declaring Dependencies](https://docs.gradle.org/current/userguide/declaring_dependencies.html), [Build Lifecycle](https://docs.gradle.org/current/userguide/build_lifecycle.html) và [Task Configuration Avoidance](https://docs.gradle.org/current/userguide/task_configuration_avoidance.html).