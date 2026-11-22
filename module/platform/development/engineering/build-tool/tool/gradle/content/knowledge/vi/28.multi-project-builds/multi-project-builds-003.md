# Đường dẫn project và cách gọi task toàn bộ hoặc từng module trong Gradle

## 1. Mục tiêu: chọn đúng project, chọn đúng task

Khi một Gradle build chứa nhiều module, câu lệnh `./gradlew build` có thể xây toàn bộ cây project, nhưng `./gradlew :app:build` chỉ yêu cầu build của một module, còn `./gradlew :build` chỉ chọn task `build` ở **root project**. Ba lệnh này **không đồng nghĩa**, dù đều có chữ `build`.

Gradle phân biệt:

- **Project**: đơn vị cấu hình/build độc lập bên trong cùng một multi-project build. Mỗi project có tên, build script, plugins, dependencies, tasks và outputs riêng.
- **Root project**: project đứng đầu hierarchy, có path đặc biệt `:`, thường chứa `settings.gradle.kts`.
- **Subproject**: project con được khai báo với `include(...)` trong Settings.
- **Project path**: định danh vị trí project trong cây bằng dấu hai chấm, như `:app`, `:shared`, `:services:api`.
- **Task name**: tên task **trong một project**, như `build`, `test`, `compileJava`.
- **Task path**: đường dẫn đến **một task cụ thể**, ghép project path với task name, như `:app:build` hoặc `:services:api:test`.
- **Task selector**: lệnh không chỉ định full task path, chẳng hạn `build` hay `test`, có thể chọn các task cùng tên ở **nhiều project bên dưới ngữ cảnh hiện tại**.

Bài học trình bày đường dẫn tuyệt đối và tương đối, quy tắc chọn task từ root và subproject, cách xem project/task graph, cách gọi từng module hay nhiều modules, cách dependency giữa modules tác động những tasks được thực thi, và kỹ thuật kiểm tra khi lệnh Gradle gọi nhầm task.

Sau bài, bạn cần phân biệt được chính xác:

~~~bash
./gradlew build
./gradlew :build
./gradlew :app:build
./gradlew :shared:test
./gradlew :app:run --args="alpha beta"
~~~

Bài thực hành dùng **Java 17**, **Gradle Kotlin DSL** và **Gradle Wrapper**. Không cần viết Groovy build scripts; tất cả file nguồn Java có package/class và vị trí cụ thể, cùng lệnh `javac`/`java` độc lập để đối chiếu stdout.

## 2. Project hierarchy và cú pháp path có dấu `:`

Một multi-project build có thể được hình dung:

~~~text
Root project ":"
├── Project ":app"
├── Project ":shared"
└── Project ":services"
    ├── Project ":services:api"
    └── Project ":services:worker"
~~~

**Quy tắc project path:**

| Ký hiệu | Ý nghĩa |
| --- | --- |
| `:` | Root project, không phải tên thư mục. |
| `:app` | Subproject tên `app` nằm trực tiếp dưới root. |
| `:shared` | Subproject `shared` nằm trực tiếp dưới root. |
| `:services:api` | Subproject `api` nằm dưới project `services`. |
| `:services:worker` | Subproject `worker` nằm dưới `services`. |
| `:app:test` | Task `test` **trong** project `:app`. |
| `:services:api:build` | Task `build` **trong** nested project `:services:api`. |

Dấu `:` đầu path biểu thị **bắt đầu từ root**. Các thành phần tiếp theo phân tách bằng dấu `:`. **Root project path không bao gồm root project name**. Ví dụ, nếu `rootProject.name = "learning-platform"`, đường dẫn đúng tới `app` vẫn là `:app`, **không** là `:learning-platform:app`.

### Project path KHÔNG phải filesystem path

Project `:services:api` thường được map mặc định tới directory `services/api`, nhưng Gradle cho phép Settings thay đổi `projectDir`. Vì thế:

- `:services:api` là **định danh logic trong Gradle**.
- `services/api` là **filesystem location** (mặc định).
- `services/api/build.gradle.kts` là **build script file** của project.
- `:services:api:test` là **task path**, không phải đường dẫn file trong ổ đĩa.

Không dùng slash `/` để phân tách project trong task selector kiểu `:services/api:test`. Đó không phải cú pháp task path thông thường.

## 3. Project path được tạo trong `settings.gradle.kts`

Ví dụ Settings:

~~~kotlin
rootProject.name = "shop-platform"

include("app", "shared", "services:api", "services:worker")
~~~

Gradle biết các project `:app`, `:shared`, `:services:api`, `:services:worker` từ `include`. Project `:services` là node trung gian trong hierarchy, với directory tương ứng theo mapping thông thường.

Với Gradle 9+, những project directories được include cần tồn tại và có thể ghi. Nếu dùng nested path, cần đảm bảo cả đường dẫn trung gian và thư mục project là hợp lệ. Không chỉ khai báo một path rồi kỳ vọng Gradle tự tạo toàn bộ dự án và mã Java cần thiết.

### Đọc cấu trúc bằng task `projects`

~~~bash
./gradlew projects
./gradlew -q projects
~~~

Lệnh này hiển thị project hierarchy và, ở các Gradle version mới, có thể kèm thông tin vị trí project. Không cố so sánh chính xác toàn bộ format stdout giữa Gradle versions.

Khi không chắc dự án có project `:billing` hay `:payments:billing`, **chạy `projects` trước** rồi mới gọi task. Đây là cách nhanh nhất tránh sai project path.

### Đổi project directory không làm đổi project path

Một ví dụ cấu hình khác:

~~~kotlin
rootProject.name = "shop-platform"
include("app", "shared")

project(":app").projectDir = file("applications/console")
~~~

Gradle project vẫn tên `:app` nhưng build script và sources của nó giờ nằm trong `applications/console` nếu project directory được cấu hình đúng. Từ root, lệnh vẫn là:

~~~bash
./gradlew :app:build
~~~

**Không** đổi thành `./gradlew :applications:console:build` chỉ vì physical directory chứa app như vậy. Không trộn ví dụ `projectDir` này vào lab mục 4 nếu chưa di chuyển file app: nó là **phương án thay thế về mapping**.

## 4. Lab Java 17 hoàn chỉnh: root, `:shared` và `:app`

Chúng ta sẽ dựng một build có ba projects:
- Root `:`: giữ Settings, và có Base plugin để tạo lifecycle tasks `:build`, `:check`, `:clean`. Root không có Java source.
- `:shared`: Java library cung cấp một phương thức tạo lời chào.
- `:app`: Java Application plugin, phụ thuộc project `:shared` và in kết quả ra stdout.

Hai subprojects đều có JUnit tests để bạn thấy sự khác nhau giữa `test` (task selector nhiều project), `:shared:test` và `:app:test`.

### 4.1. Cấu trúc thư mục

~~~text
multi-project-paths/
├── settings.gradle.kts
├── build.gradle.kts
├── gradlew
├── gradlew.bat
├── gradle/wrapper/...
├── shared/
│   ├── build.gradle.kts
│   └── src/
│       ├── main/java/example/shared/Greeting.java
│       └── test/java/example/shared/GreetingTest.java
└── app/
    ├── build.gradle.kts
    └── src/
        ├── main/java/example/app/App.java
        └── test/java/example/app/AppTest.java
~~~

Yêu cầu: Gradle Wrapper hoạt động, JDK 17 được cài hoặc toolchain provisioned, Maven Central truy cập được nếu chưa cache JUnit. Các phiên bản JUnit trong ví dụ là **mốc cụ thể cho bài lab**, không mặc định là phiên bản mới nhất.

### 4.2. `settings.gradle.kts`

~~~kotlin
rootProject.name = "multi-project-paths"
include("shared", "app")
~~~

Root project path luôn là `:`. Hai subprojects có paths `:shared` và `:app`. Thứ tự trong `include(...)` không quyết định thứ tự task execution khi có dependency graph; Gradle quyết định thứ tự qua task dependencies và rules.

### 4.3. Root `build.gradle.kts`

~~~kotlin
plugins {
    base
}
~~~

Base plugin tạo các lifecycle tasks, bao gồm `assemble`, `check`, `build` và `clean` ở root. Root **không** áp `java`/`application`, vì không có Java source. Đặc biệt, root `:build` chỉ là lifecycle task của **root**, nó không tự phụ thuộc vào `:app:build` hoặc `:shared:build` chỉ vì có `include`.

Điều này có chủ đích để bạn kiểm tra:

~~~bash
./gradlew :build
./gradlew build
~~~

Lệnh đầu chỉ **chọn** `:build`; lệnh thứ hai là selector từ root, chọn cả các task `build` trong subprojects có task này.

### 4.4. `shared/build.gradle.kts`

~~~kotlin
plugins {
    `java-library`
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

dependencies {
    testImplementation(platform("org.junit:junit-bom:5.11.4"))
    testImplementation("org.junit.jupiter:junit-jupiter")
    testRuntimeOnly("org.junit.platform:junit-platform-launcher")
}

tasks.test {
    useJUnitPlatform()
}
~~~

`java-library` tạo `compileJava`, `jar`, `test` và `build` cho project `:shared`, cùng các configurations `api`/`implementation` cho library. JUnit dependencies chỉ cần cho tests; Java source chính không có external library.

### 4.5. `shared/src/main/java/example/shared/Greeting.java`

~~~java
package example.shared;

public final class Greeting {
    private Greeting() {
    }

    public static String message() {
        return "Hello from shared";
    }
}
~~~

Phương thức `message()` là production API mà app sẽ sử dụng. Với Java 17, code có thể compile độc lập.

### 4.6. `shared/src/test/java/example/shared/GreetingTest.java`

~~~java
package example.shared;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class GreetingTest {
    @Test
    void returnsExpectedMessage() {
        assertEquals("Hello from shared", Greeting.message());
    }
}
~~~

Khi `:shared:test` chạy, test kiểm tra implementation của project `:shared`. Gradle/JUnit không nhất thiết in tên từng test ở terminal; xem HTML report hoặc bật test logging nếu muốn quan sát chi tiết.

### 4.7. `app/build.gradle.kts`

~~~kotlin
plugins {
    application
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

application {
    mainClass.set("example.app.App")
}

dependencies {
    implementation(project(":shared"))

    testImplementation(platform("org.junit:junit-bom:5.11.4"))
    testImplementation("org.junit.jupiter:junit-jupiter")
    testRuntimeOnly("org.junit.platform:junit-platform-launcher")
}

tasks.test {
    useJUnitPlatform()
}
~~~

Điểm cần nhớ là:

~~~kotlin
implementation(project(":shared"))
~~~

đây là **project dependency** giữa `:app` và `:shared`, không phải một task path. Nó làm `:app` nhận các compiled classes/variants/dependencies thích hợp của `:shared` trên classpath, đồng thời Gradle tự nối các task sản xuất artifact cần thiết.

Không thay nó bằng `implementation("shared")`: chuỗi đơn không chỉ định Gradle project path. Cũng không thay bằng `dependsOn(":shared:build")` rồi nghĩ đã có classpath: task dependency chỉ đặt thứ tự, **không tự thêm library vào compile classpath**.

### 4.8. `app/src/main/java/example/app/App.java`

~~~java
package example.app;

import example.shared.Greeting;

public final class App {
    private App() {
    }

    public static String messageLine() {
        return "APP_MESSAGE=" + Greeting.message();
    }

    public static void main(String[] args) {
        System.out.println(messageLine());
        System.out.println("ARG_COUNT=" + args.length);
    }
}
~~~

App sử dụng library từ `:shared` qua Java import. Nếu dependency `implementation(project(":shared"))` bị xóa, `:app:compileJava` sẽ không tìm được `example.shared.Greeting`, mặc dù `:shared` có thể vẫn được build riêng.

### 4.9. `app/src/test/java/example/app/AppTest.java`

~~~java
package example.app;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class AppTest {
    @Test
    void usesSharedProject() {
        assertEquals(
            "APP_MESSAGE=Hello from shared",
            App.messageLine()
        );
    }
}
~~~

Test app kiểm tra code app gọi được Java library trong `:shared`. Khi chạy `:app:test`, Gradle có thể thực thi các task compile/package cần thiết của `:shared` trước, nhưng không có nghĩa đã chạy toàn bộ tests của `:shared`.

## 5. Gọi Gradle từ root: toàn bộ và từng module

Tại thư mục root `multi-project-paths`, dùng Gradle Wrapper:

~~~bash
./gradlew projects
./gradlew :tasks --all
./gradlew :shared:tasks --all
./gradlew :app:tasks --all
~~~

`projects` liệt kê project paths. `:tasks` hiển thị tasks **root**; `:shared:tasks` hiển thị tasks của library; `:app:tasks` hiển thị tasks của app. Một task không được tạo trên project nào đó thì bạn không thể gọi nó bằng project path của project đó.

### 5.1. Build toàn bộ cây project

~~~bash
./gradlew build
~~~

Từ root, đây là **task selector không có dấu `:` đầu**, nên Gradle chọn tasks tên `build` trong project hiện tại (root) và các subprojects bên dưới có task đó. Trong lab, có `:build`, `:shared:build` và `:app:build`.

Gradle còn chạy các **prerequisites** của những tasks được chọn: compile, tests, JAR, dependency resolution... Thứ tự cụ thể theo graph, không đơn giản bằng thứ tự subprojects được ghi trong Settings. Nếu một task đã `UP-TO-DATE` hoặc `FROM-CACHE`, nó có thể không chạy actions lần này.

**Không diễn giải `./gradlew build` từ root là "một task root tự gọi mọi child build"**. Đó là **task selector** chọn nhiều tasks theo tên; cơ chế khác với `:build`.

### 5.2. Chỉ yêu cầu root `build`

~~~bash
./gradlew :build
~~~

Dấu `:` chỉ rõ task path tuyệt đối của **root**. Trong lab root chỉ có Base plugin, nên `:build` không tự chạy Java tests/compile ở hai subprojects.

Nếu bạn sau này viết:

~~~kotlin
tasks.named("build") {
    dependsOn(":app:build", ":shared:build")
}
~~~

vào root build script, thì `:build` **sẽ** kéo các child tasks qua dependency được cấu hình rõ. Vì vậy câu “`:build` chỉ chọn root task” phải hiểu là **task được người dùng chọn trực tiếp**, còn Gradle vẫn có thể chạy những dependencies của root task nếu bạn khai báo. Đó là điểm quan trọng để tránh nhầm trong dự án thực tế.

### 5.3. Chỉ build library

~~~bash
./gradlew :shared:build
~~~

Lệnh chỉ **chọn trực tiếp** task `build` ở project `:shared`. Nó chạy compilation/tests/archive của `:shared` và prerequisites, không tự chọn `:app:build`.

Nếu cần build JAR của library mà không yêu cầu toàn bộ unit tests, dùng:

~~~bash
./gradlew :shared:jar
~~~

Task `jar` sẽ kéo những compile/resources tasks cần thiết, nhưng không mặc định chạy `:shared:test`.

### 5.4. Chỉ build application

~~~bash
./gradlew :app:build
~~~

Lệnh chỉ chọn `:app:build`, nhưng **không có nghĩa chỉ chạy tasks có prefix `:app:`**. Vì app phụ thuộc `project(":shared")`, Gradle có thể cần chạy một số task của `:shared` để cung cấp compiled classes/JAR cho `:app`.

Tuy nhiên `:app:build` **không mặc nhiên tương đương `:shared:build` đầy đủ**: shared tests có thể không chạy chỉ vì app dùng shared artifact. Khi muốn đảm bảo cả shared và app đều được test, gọi `./gradlew build` từ root hoặc chọn rõ `:shared:test` và `:app:test`.

### 5.5. Chạy application và quan sát stdout

~~~bash
./gradlew -q :app:run --args="alpha beta"
~~~

Gradle Application plugin thêm task `:app:run`. Vì app Java code đọc args, stdout **do `App.main` in ra** là:

~~~text
APP_MESSAGE=Hello from shared
ARG_COUNT=2
~~~

Trên Windows PowerShell:

~~~powershell
.\gradlew.bat -q :app:run --args="alpha beta"
~~~

Kết quả từ Java main giống hai dòng trên. Các thông báo Gradle/daemon/mạng có thể khác theo môi trường; không khẳng định toàn bộ terminal output chỉ có hai dòng khi có cảnh báo hoặc logging bổ sung.

### 5.6. Chạy tests cho tất cả hoặc từng module

~~~bash
# Selector từ root: chạy test tasks của các projects có task test.
./gradlew test

# Chỉ test module shared.
./gradlew :shared:test

# Chỉ test module app (có thể kéo shared compile/artifact).
./gradlew :app:test

# Chọn rõ cả hai test tasks.
./gradlew :shared:test :app:test
~~~

Trong lab, root **chỉ** có Base plugin nên root **không có `test` task**. Do đó:

~~~bash
./gradlew :test
~~~

sẽ báo task `:test` không tồn tại, dù lệnh `./gradlew test` có thể chạy thành công nhờ `:shared:test` và `:app:test`. Đây là minh họa rất rõ sự khác nhau giữa **task selector** và **fully qualified task path**.

## 6. Quy tắc quan trọng: `build` không dấu hai chấm là task selector

Tài liệu Gradle nêu **khi gọi tên task không kèm project path từ root**, Gradle tìm tasks cùng tên trong project hiện tại và các subprojects của nó.

| Chạy từ root | Project/task trực tiếp được chọn | Ghi chú |
| --- | --- | --- |
| `./gradlew build` | `build` tại root và các subprojects có task này. | Prerequisites có thể kéo tasks khác. |
| `./gradlew :build` | Chỉ chọn root `:build`. | Root task có thể có explicit dependencies. |
| `./gradlew test` | `test` ở các projects có task này. | Trong lab không có root `:test`. |
| `./gradlew :app:test` | Chỉ chọn `:app:test`. | Có thể kéo shared compile. |
| `./gradlew :shared:jar` | Chỉ chọn `:shared:jar`. | Build artifact library, không yêu cầu shared test. |
| `./gradlew :app:run` | Chỉ chọn `:app:run`. | Dùng Application plugin. |
| `./gradlew clean` | `clean` trong cây projects có task này. | Không giống chỉ root clean. |
| `./gradlew :clean` | Chỉ root `:clean`. | Có thể thiếu clean task nếu root không áp Base. |
| `./gradlew :app:clean` | Chỉ clean outputs của app. | Không tự xóa outputs của shared. |

**Một ngoại lệ về task selector:** các tasks mang tính **trợ giúp/báo cáo** như `help` và `dependencies` được Gradle xử lý đặc biệt, thường chỉ chạy trên project được invoke để không in thông tin trùng lặp từ mọi subprojects. Đừng dùng `./gradlew dependencies` từ root rồi nghĩ bạn đã xem runtimeClasspath của tất cả modules.

Ví dụ đúng khi cần xem dependencies của app:

~~~bash
./gradlew :app:dependencies --configuration runtimeClasspath
./gradlew :app:dependencyInsight --configuration runtimeClasspath --dependency shared
~~~

Trong ví dụ Java của bài, `implementation(project(":shared"))` làm runtimeClasspath của app chứa project dependency đến shared; để phân tích chính xác hãy đọc output thực tế của `dependencies`. Gradle selection reasons ở `dependencyInsight` sẽ phụ thuộc graph, không có transcript bất biến.

### Tại sao task selector giúp ích?

Khi tất cả subprojects đều có `test`, `./gradlew test` rất tiện để kiểm thử toàn bộ cây. Nhưng chính sự tiện lợi đó gây lỗi nếu chỉ muốn test một module: lệnh không đủ qualified có thể chạy lâu, cần nhiều môi trường hoặc fail vì một module không liên quan.

**Dùng full task path khi bạn muốn kiểm soát phạm vi rõ.**

## 7. Đường dẫn tương đối và current working directory

Gradle có notion **current project context** dựa trên thư mục đang invoke, cùng project hierarchy trong Settings. Từ root, hai lệnh thường tương đương:

~~~bash
./gradlew :app:build
./gradlew app:build
~~~

Từ root, `app:build` có project path tương đối với root; `:app:build` là path **tuyệt đối**. Trong script CI, nên ưu tiên có `:` đầu để rõ ràng và bền hơn nếu command được chạy từ thư mục con khác.

### Chạy Wrapper từ thư mục `app`

Linux/macOS:

~~~bash
cd app
../gradlew build
../gradlew test
../gradlew run --args="alpha beta"
~~~

Vì context hiện tại là project `:app`, các lệnh tên task trần được áp vào project đó (và các descendants nếu có), chứ **không** tự quét siblings như `:shared` để chọn `:shared:test`. Nhưng project dependencies của app vẫn có thể kéo các task cần thiết từ shared.

Muốn chắc chắn project nào được chọn dù đứng ở thư mục nào, dùng absolute task path:

~~~bash
../gradlew :shared:build
../gradlew :app:run --args="alpha beta"
~~~

Trên Windows PowerShell, nếu đang trong thư mục `app`:

~~~powershell
..\gradlew.bat build
..\gradlew.bat :shared:build
..\gradlew.bat :app:run --args="alpha beta"
~~~

**Không nên đồng nhất đường dẫn đến Wrapper executable với project path.** `../gradlew` chỉ là file shell nằm ở parent directory; việc chọn Gradle project liên quan tới Settings và current project context, không chỉ tên executable.

### `--project-dir` / `-p`

Gradle có tùy chọn `--project-dir` (viết tắt `-p`) để đặt working/project directory cho Gradle invocation:

~~~bash
./gradlew -p app build
./gradlew :app:build
~~~

Trong một build chuẩn với Settings ở root, hai lệnh thường chọn app build theo context tương ứng, nhưng chúng **không hoàn toàn cùng semantics** trong những tình huống settings discovery, included builds, project directory mapping và script path khác nhau. Với CI cần tái lập, path tuyệt đối `:app:build` từ root thường dễ kiểm soát hơn.

### Một project có descendants

Nếu có `:services` với children `:services:api` và `:services:worker`, khi chạy từ thư mục project `services`:

~~~bash
../gradlew test
~~~

task selector `test` tìm trong project `:services` và các descendants của nó có `test`, không tự chọn siblings `:app`/`:shared` ở root. Đây là quy tắc **hierarchical task selection** của multi-project builds.

## 8. Nested modules: `:services:api:build`

Với cấu trúc:

~~~text
shop-platform/
├── settings.gradle.kts
├── services/
│   ├── build.gradle.kts
│   ├── api/
│   │   └── build.gradle.kts
│   └── worker/
│       └── build.gradle.kts
└── shared/
    └── build.gradle.kts
~~~

Settings:

~~~kotlin
rootProject.name = "shop-platform"

include("shared", "services:api", "services:worker")
~~~

Dự án được map mặc định:

~~~text
:                   -> shop-platform/
:shared             -> shop-platform/shared/
:services           -> shop-platform/services/
:services:api       -> shop-platform/services/api/
:services:worker    -> shop-platform/services/worker/
~~~

Nếu muốn `:services` cũng có lifecycle tasks, đặt một `services/build.gradle.kts` và apply plugin thích hợp. `include("services:api")` không tự áp Java plugin cho `:services`; đây chỉ là cách khai báo hierarchy.

Chạy chính xác:

~~~bash
./gradlew :services:api:build
./gradlew :services:worker:test
./gradlew :services:api:tasks --all
./gradlew :shared:jar
~~~

Không viết `./gradlew :services:build:api`: task name nằm **cuối**, không kẹp giữa các project path segments.

### Khi thay directory mapping

~~~kotlin
include("services:api")
project(":services:api").projectDir = file("backend/http-api")
~~~

Đây là **phương án thay thế** cho Settings mặc định trong phần này. Project path vẫn `:services:api`, dù source files sống ở `backend/http-api`. Trong Gradle 9+, hãy chắc các project directories được include, kể cả node trung gian như `services`, tồn tại và có thể ghi; nếu mapping có chủ đích thì cấu hình directories đúng, không tạo project rỗng bất ngờ.

Project path là **API định danh logic** của build, không phải cách suy ngược tuyệt đối từ filesystem.

## 9. Chọn nhiều tasks trong một command

Gradle có thể nhận nhiều task paths:

~~~bash
./gradlew :shared:build :app:build
./gradlew :shared:test :app:test
./gradlew :shared:jar :app:run --args="alpha beta"
~~~

Dấu cách phân tách task requests. Gradle hợp nhất thành **một task execution graph**, nên mỗi task/producer được thực thi tối đa theo graph của invocation chứ không chạy trùng hoàn toàn vì nó xuất hiện như prerequisite nhiều lần. Các dependencies và ordering constraints vẫn có hiệu lực.

### Phân biệt thứ tự command line với task dependencies

Lệnh:

~~~bash
./gradlew :shared:build :app:build
~~~

thường giúp người đọc biết yêu cầu cả hai builds, nhưng không nên tự tạo một dependency logic “app luôn chờ toàn bộ shared tests” chỉ dựa vào việc người dùng ghi task shared trước. Các thứ tự mà Gradle đảm bảo dựa vào graph/task ordering rules, và Gradle có thể song song hóa những phần độc lập. Muốn một task **phải chạy sau** task khác, mô hình hóa quan hệ tương ứng trong build logic; đừng trông chờ thứ tự CLI như một cơ chế thiết kế dài hạn cho mọi CI.

### `clean build` từ root

~~~bash
./gradlew clean build
~~~

Từ root, cả hai là selectors. Các task `clean`/`build` ở những projects phù hợp được chọn. Gradle sắp xếp graph để tránh build artifacts bị dọn sau khi đã tạo khi các quan hệ task/lifecycle được mô hình hóa phù hợp. Khi cần chỉ clean app:

~~~bash
./gradlew :app:clean :app:build
~~~

Lệnh này không tự clean thư mục `shared/build`, dù `:app:build` có thể cần sử dụng/rebuild outputs của shared.

## 10. Project dependency không đồng nghĩa trực tiếp với task dependency

Đây là điểm quan trọng nhất để dự đoán chính xác **những tasks thực sự được thực thi**.

Trong `app/build.gradle.kts`:

~~~kotlin
dependencies {
    implementation(project(":shared"))
}
~~~

Project dependency yêu cầu Java library của `:shared`. Khi Gradle resolve compile/runtime classpath, nó chọn **variants/artifacts** phù hợp và thêm các task producer cần thiết vào execution graph.

Ví dụ:

~~~bash
./gradlew :app:compileJava
~~~

Lệnh chọn task `:app:compileJava`; tùy Gradle version, plugin, variant model và optimization, graph còn có các tasks compile/classes/JAR của `:shared` cần thiết để cung cấp inputs cho compiler app. **Không hard-code rằng luôn phải chạy đúng `:shared:jar` trong mọi Gradle version/configuration.**

Nhưng **không mặc định** `:shared:test` hay `:shared:build` được chọn chỉ vì app dùng shared classes. App có thể compile thành công trong khi shared unit tests chưa được chạy ở invocation này.

### Nếu chỉ dùng `dependsOn(":shared:build")`?

~~~kotlin
tasks.named("compileJava") {
    dependsOn(":shared:build")
}
~~~

Đây là **mảnh phản ví dụ về thiết kế** khi mục tiêu là thêm một Java library dependency. Nó có thể buộc build/test shared trước app compile, nhưng **không thêm compiled shared classes vào Java compile classpath** của app. Nó còn làm app compile phụ thuộc nặng vào unrelated shared tests và tạo cross-project task coupling.

Thay bằng `implementation(project(":shared"))` để Gradle tự mô hình hóa đúng compiler inputs. Nếu thực sự chỉ muốn gọi một task khác như prerequisite orchestration, `dependsOn(":shared:someTask")` là cơ chế task graph đúng nhưng phải có lý do riêng.

### Khi cần tạo output custom từ một project khác

Nếu một module cần generated artifact do module khác tạo, ưu tiên mô hình hóa **outgoing configuration/variant/task output Provider** để consumer có task dependency ngầm và artifact metadata rõ. Tránh hard-code:

~~~kotlin
from("../shared/build/libs/shared.jar")
~~~

chỉ là path text, có thể sai khi shared đổi archive name/version/target directory, và không tự truyền producer relation như provider-aware dependency.

## 11. API Kotlin DSL khi tạo task trong multi-project

Mỗi project có `tasks` container riêng. Trong `app/build.gradle.kts`:

~~~kotlin
tasks.register("printProjectIdentity") {
    doLast {
        println("TASK_PATH=" + path)
    }
}
~~~

`path` ở đây là property của **Task** đang được thực thi. Nếu gọi:

~~~bash
./gradlew -q :app:printProjectIdentity
~~~

stdout chính xác do task in ra:

~~~text
TASK_PATH=:app:printProjectIdentity
~~~

Nếu đăng ký task cùng tên trong `shared/build.gradle.kts` và gọi `:shared:printProjectIdentity`, task path tương ứng là `:shared:printProjectIdentity`. Hai tasks có **cùng tên** nhưng khác project path, không phải một task.

### `tasks.named` tra task trong project hiện tại

~~~kotlin
tasks.named("test") {
    // Cấu hình task test của project này.
}
~~~

Đoạn này thuộc project có Java plugin; nó **không tự chọn task `test` của mọi project**. Ở `app/build.gradle.kts`, nó cấu hình `:app:test`; ở `shared/build.gradle.kts` thì cấu hình `:shared:test`.

### Tạo aggregator task ở root

Nếu CI muốn một task path rõ để chạy kiểm thử của các modules chọn lọc, root có thể đăng ký:

~~~kotlin
tasks.register("verifySelectedModules") {
    group = "verification"
    description = "Checks shared and app modules"

    dependsOn(":shared:check", ":app:check")
}
~~~

Đây là **mảnh bổ sung** cho root project có `:shared` và `:app`. Khi gọi:

~~~bash
./gradlew :verifySelectedModules
~~~

Gradle schedule `:shared:check` và `:app:check`. Đây là **task aggregation với explicit dependencies**; không phải behavior tự động của `:build` hoặc `:check`.

Nên dùng task aggregator khi nhóm dự án có contract CI riêng. Nếu mục tiêu đơn giản là test mọi module, `./gradlew test` hoặc `./gradlew check` từ root đã là selector thuận tiện; đừng tạo hàng trăm root aggregator tasks không cần thiết.

## 12. Gradle task matching và abbreviation: tiện nhưng dễ nhầm

Gradle CLI hỗ trợ **viết tắt task/project names** nếu có thể resolve duy nhất. Ví dụ, với project `:app` và task `compileJava`, các dạng rút gọn có thể hoạt động:

~~~bash
./gradlew :app:compileJava
./gradlew :app:cJ
~~~

Tuy nhiên việc `:app:cJ` match được hay không tùy bộ tasks hiện có; nếu có nhiều task names cùng match, Gradle có thể báo ambiguous hoặc yêu cầu tên đầy đủ.

Tài liệu còn mô tả camel-case/kebab-case name matching, ví dụ task `compileTestJava` có thể viết tắt khi phân biệt được. Không nên hard-code abbreviation vào CI scripts dài hạn vì khi thêm plugin/task khác, tên tắt trước đây hợp lệ có thể **trở nên ambiguous**.

### Ambiguous task names

Giả sử cả `:shared` và `:app` có `test`. Từ root:

~~~bash
./gradlew test
~~~

đây là **task selector** để chạy cả hai, không báo “ambiguous” chỉ vì có nhiều project cùng có task `test`. **Ambiguity** chủ yếu xuất hiện khi một abbreviated name không đủ phân biệt những task/project names **trong cơ chế name matching**. Đừng nhầm “selector chọn nhiều tasks” với “abbreviation mơ hồ”.

### Dùng full task path trong tài liệu/CI

Ưu tiên:

~~~bash
./gradlew :app:compileJava
./gradlew :app:test
./gradlew :app:run --args="alpha beta"
~~~

thay vì abbreviations. Người mới đọc logs sẽ biết ngay task path, giảm nguy cơ gọi nhầm khi cấu trúc modules thay đổi.

## 13. Công cụ kiểm tra trước khi chạy task thật

Khi bạn chưa chắc command sẽ chạy những tasks nào, dùng:

~~~bash
./gradlew :app:build --dry-run
./gradlew build --dry-run
./gradlew :build --dry-run
./gradlew :shared:test --dry-run
~~~

`--dry-run` cho biết **những tasks được lên lịch** trong graph và thứ tự dự kiến mà **không chạy actions**. Nó hữu ích để xác minh task selector, project paths và prerequisites.

**Nó không chứng minh**:
- Java source compile thành công.
- JUnit tests pass.
- Project dependency resolution có thể tải mọi artifact từ repository.
- Một service/database/HTTP endpoint thực sự sẵn sàng.
- Task output sau khi chạy đầy đủ sẽ có nội dung đúng.

### `--info` khi cần thấy lý do task chạy hoặc skip

~~~bash
./gradlew :app:build --info
./gradlew :app:test --rerun-tasks --info
~~~

`--info` cho thêm thông tin về execution, resolve/up-to-date reasons. `--rerun-tasks` buộc tasks chạy lại thay vì chỉ `UP-TO-DATE` (có thể tốn thời gian). Không bật `--rerun-tasks` trên mọi CI build nếu mục tiêu là tận dụng incremental/caching.

### `help --task` và `tasks --all`

~~~bash
./gradlew help --task test
./gradlew :app:tasks --all
./gradlew :shared:tasks --all
~~~

`help --task test` mô tả task name, type và các full task paths có thể match; một số Gradle version còn hiển thị options/provenance. Khi cần biết chính xác module nào có `test`, `:app:tasks`/`:shared:tasks` vẫn là cách rất rõ ràng.

### `projects` và `properties`

~~~bash
./gradlew projects
./gradlew :app:properties
~~~

`projects` để xem hierarchy; `:app:properties` để xem project properties của app theo phiên bản Gradle. Cẩn thận chia sẻ output vì properties/logs có thể chứa environment, paths hoặc thông tin nhạy cảm.

## 14. `--continue`, `--parallel` và phạm vi task selection

### `--continue` không bỏ qua prerequisites bị lỗi

~~~bash
./gradlew test --continue
~~~

Từ root, `test` chọn test tasks ở subprojects. Nếu `:shared:test` fail, Gradle có thể tiếp tục những tasks khác **không phụ thuộc vào task bị lỗi**. Nó **không** làm `:app:compileJava` chạy được nếu prerequisite compile shared fail; tasks có failed dependencies vẫn bị chặn.

`--continue` đặc biệt hữu ích khi muốn lấy nhiều test failures trong một CI run, thay vì dừng ở module test đầu tiên lỗi.

### `--parallel` không đổi ý nghĩa task path

~~~bash
./gradlew build --parallel
./gradlew :app:build --parallel
~~~

`--parallel` cho phép Gradle thực thi tasks/projects độc lập song song theo support/cấu hình. Nó **không** tự biến `:app:build` thành “build mọi module”, không bỏ qua dependencies và không cho phép app compile trước khi shared inputs sẵn sàng.

Nếu nhiều modules dùng chung port, database, thư mục output hoặc service, parallel execution có thể gây race. Cần khai báo inputs/outputs, resource locks hoặc tách môi trường theo module. Đừng dùng `mustRunAfter`/`shouldRunAfter` như một giải pháp mơ hồ cho resource contention nếu có thể mô hình hóa Shared Build Service/resource đúng hơn.

### `--exclude-task`

Gradle hỗ trợ bỏ một task ra khỏi execution, ví dụ:

~~~bash
./gradlew build -x test
~~~

Khi chạy selector `build` từ root, `-x test` có thể loại các test tasks tương ứng. **Đây không phải một “build đầy đủ đã kiểm thử”**; dùng cho tình huống có chủ đích (chẩn đoán/packaging nhanh) và tránh dùng làm CI validation mặc định.

Nếu mục tiêu chỉ bỏ test của **một** module, không nên dùng selector `-x test` một cách toàn cục rồi vô tình bỏ mọi tests; xem cách chỉ định task path của exclude option trong Gradle version bạn dùng và kiểm tra graph qua `--dry-run`.

## 15. Từ subproject gọi task của sibling và nested project

Giả sử đang ở thư mục `app` và cần build library `shared`:

~~~bash
cd app
../gradlew :shared:build
~~~

Đường dẫn `:shared:build` là absolute task path trong cùng build, không phụ thuộc việc task được gọi từ app directory. Còn:

~~~bash
../gradlew build
~~~

từ `app` chỉ chọn task `build` trong context app và descendants (lab không có child dưới app). Nó **không tự chọn `:shared:build`**, dù dependency `project(":shared")` vẫn có thể kéo các shared tasks liên quan.

Với nested project `:services:api`, luôn có thể gọi từ root:

~~~bash
./gradlew :services:api:build
~~~

Nếu đứng ở `services/api`, path đến Wrapper executable thường là `../../gradlew`, nhưng Gradle project path vẫn `:services:api`. **Filesystem navigation và logical task path là hai hệ tọa độ khác nhau**.

### Dùng `rootProject.name` không đổi task namespace

Nếu đổi:

~~~kotlin
rootProject.name = "another-name"
~~~

các paths `:app:build`/`:shared:test` không tự đổi theo root name; chúng vẫn tham chiếu cùng project names trong Settings. Nếu đổi một **subproject name** hoặc project inclusion path, các task paths chứa tên subproject đó sẽ đổi và CI scripts phải cập nhật.

## 16. Từ `build` selector đến CI pipeline

Một pipeline có thể cần ba mức phạm vi:

| Nhu cầu | Lệnh gợi ý | Tại sao |
| --- | --- | --- |
| Mọi modules trong build | `./gradlew build` từ root. | Selector chọn tất cả tasks `build` trong hierarchy. |
| Mọi modules, chỉ tests | `./gradlew test` từ root. | Selector chọn tasks `test`. |
| Chỉ build app và các prerequisites | `./gradlew :app:build`. | Chọn app build, dependency graph lấy shared artifacts cần. |
| Chỉ compile app | `./gradlew :app:compileJava`. | Không bắt buộc full tests của app/shared. |
| Chỉ test library | `./gradlew :shared:test`. | Phạm vi rõ. |
| Chạy ứng dụng demo | `./gradlew :app:run --args="alpha beta"`. | Application plugin của app. |
| Root-only lifecycle | `./gradlew :build`. | Không tự chọn child builds nếu root không có aggregator dependency. |
| Kiểm tra graph không thực thi | `./gradlew build --dry-run`. | Review selector/graph trước chạy. |
| Đọc project hierarchy | `./gradlew projects`. | Xác minh names và nested paths. |
| Lấy nhiều independent failures | `./gradlew test --continue`. | Tiếp tục tasks không phụ thuộc failure. |

**Không chỉ nhìn tên CI job “Build All” để khẳng định nó dùng `./gradlew build`.** Đọc task paths thực được invoke. Một CI job chỉ gọi `:app:build` có thể hoàn tất app nhưng không chạy library's own tests, nếu không có dependency/lifecycle policy riêng.

### Tránh lạm dụng root `subprojects { ... }`

Bạn có thể thấy:

~~~kotlin
subprojects {
    apply(plugin = "java")
}
~~~

Cách này áp Java plugin chéo lên mọi subproject, có thể tạo tasks không cần thiết, che nguồn cấu hình và làm build logic khó quản lý. Với nhiều modules, thường nên đặt `plugins` phù hợp vào từng subproject hoặc dùng convention plugin trong included build.

Đặc biệt, root `plugins { java }` **không** đồng nghĩa mọi subprojects có Java plugin. Root plugin application và child plugin application độc lập.

## 17. Multi-project build khác composite build (`includeBuild`)

Hai câu lệnh trong Settings có mục đích khác:

~~~kotlin
include("app", "shared")
~~~

và:

~~~kotlin
includeBuild("build-logic")
~~~

- `include(...)` thêm **subprojects thuộc cùng một multi-project build**, được gọi bằng project paths như `:app`.
- `includeBuild(...)` thêm **một Gradle build khác** vào composite, với Settings/project/task model riêng; nó thường dùng cho build logic hoặc dependency substitution.
- Không mặc nhiên coi mọi project trong included build là subproject của root build chính.
- Cú pháp task path cho included builds có thể thêm build identity/qualified paths; xem `./gradlew projects` và tài liệu composite builds của Gradle version đang dùng.
- Khi cần gọi task trong một included build, kiểm tra namespace thực, đừng chỉ lấy tên thư mục và đoán `:build-logic:build` luôn tương đương một subproject build.

Bài học này tập trung vào **multi-project build** dùng `include(...)`. Composite build cần hiểu thêm build identity và dependency substitution để không gọi nhầm tasks khi có tên module giống nhau.

## 18. Java source của lab: kiểm tra độc lập bằng `javac` và `java`

Khi Gradle build fail, bạn có thể xác minh code Java đơn giản có lỗi cú pháp hay không. Từ root, Linux/macOS:

~~~bash
mkdir -p build/manual/shared
mkdir -p build/manual/app

javac -encoding UTF-8 -d build/manual/shared \
    shared/src/main/java/example/shared/Greeting.java

javac -encoding UTF-8 \
    -cp build/manual/shared \
    -d build/manual/app \
    app/src/main/java/example/app/App.java

java -cp build/manual/shared:build/manual/app \
    example.app.App alpha beta
~~~

Stdout chính xác:

~~~text
APP_MESSAGE=Hello from shared
ARG_COUNT=2
~~~

Trên Windows PowerShell:

~~~powershell
New-Item -ItemType Directory -Force build/manual/shared | Out-Null
New-Item -ItemType Directory -Force build/manual/app | Out-Null

javac -encoding UTF-8 -d build/manual/shared shared/src/main/java/example/shared/Greeting.java
javac -encoding UTF-8 -cp build/manual/shared -d build/manual/app app/src/main/java/example/app/App.java

java -cp "build/manual/shared;build/manual/app" example.app.App alpha beta
~~~

**Lưu ý quan trọng:** classpath separator trên Linux/macOS là `:`, còn trên Windows là `;`. Dấu `:` ở **Java classpath** **không cùng nghĩa** dấu `:` ở Gradle project/task path.

Lệnh trên chứng minh Java source và Java classpath hoạt động. Nó **không chứng minh** Settings `include(...)`, Project dependency trong Gradle, Gradle task selection hoặc JUnit configuration đều đúng. Những việc đó phải kiểm tra bằng Wrapper commands từ mục 5.

## 19. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách sửa |
| --- | --- | --- |
| `Task 'build' not found in root project` | Root không có `build` lifecycle task hoặc gọi `:build` thay vì selector. | Áp Base plugin ở root nếu cần root task; dùng `./gradlew build` từ root để chọn child tasks. |
| `./gradlew :test` báo không có task | Root không áp Java plugin. | Dùng `./gradlew test` hoặc `:app:test`/`:shared:test`. |
| Gọi `./gradlew build` chạy quá nhiều modules | Task name trần từ root chọn cả hierarchy. | Dùng full path `:app:build`. |
| `:app:build` vẫn chạy tasks từ shared | `implementation(project(":shared"))` kéo artifact producer tasks. | Đây là expected; xem task graph với `--dry-run`. |
| `:app:build` không chạy shared unit tests | Project dependency không đòi toàn bộ `:shared:build`. | Chọn `:shared:test` hoặc gọi root `build`/`test`. |
| `:shared:test` chạy nhưng không có app tests | Chỉ chọn shared test. | Gọi `:app:test` hoặc root `test`. |
| `Project with path ':x' could not be found` | Settings không include `x` hoặc path sai/nested. | Chạy `./gradlew projects`, sửa `include(...)`. |
| `:services:api:build` không tìm thấy | Nested path/project mapping sai hoặc module không có task `build`. | Kiểm tra hierarchy và `:services:api:tasks`. |
| `Unresolved reference` trong Kotlin DSL | Plugin/accessor chưa có hoặc code nằm sai project script. | Kiểm tra plugins ở đúng module. |
| Java app không import được `Greeting` | App chưa có `implementation(project(":shared"))`. | Khai báo project dependency thay vì task dependency. |
| `dependencies` ở root không thấy app runtime classpath | Report task selector thường chỉ chạy current project. | `:app:dependencies --configuration runtimeClasspath`. |
| Task abbr như `:app:cJ` bỗng ambiguous | Có task/project mới cùng match abbreviation. | Dùng full names. |
| `--dry-run` hiển thị graph nhưng build thực fail | Dry-run không execute compile/tests/dependency resolution. | Chạy task thật với `--info --stacktrace`. |
| `./gradlew :app:clean` không xóa shared outputs | Clean task có project scope. | Gọi shared clean riêng nếu cần. |
| CI gọi `:build` nhưng chỉ thấy root Base tasks | Root-only task path, chưa có aggregator. | Dùng selector `build` hoặc explicit aggregator dependencies. |
| CI bỏ qua tests do `-x test` | Exclude task đã được chọn. | Xóa exclude hoặc tạo CI build/test policy rõ. |
| Build chạy song song và tranh chấp port/output | Multiple projects dùng chung tài nguyên không khóa. | Tách resources hoặc dùng resource coordination. |
| `java -cp` dùng sai dấu phân cách trên Windows | Java classpath separator khác hệ điều hành. | Windows `;`, Linux/macOS `:`. |
| Directory đổi nhưng task path cũ vẫn chạy/không chạy | `projectDir` đổi nhưng project name/Settings khác. | Dùng logical project paths từ `projects`. |
| Gradle 9 báo missing project directory | `include(...)` trỏ directory không tồn tại/không writable. | Tạo đúng directory hoặc sửa mapping Settings. |
| Plugin ở root nhưng child thiếu `build` | Plugin application có scope từng Project. | Áp Java/Base plugin đúng subproject. |

## 20. Checklist dùng task paths an toàn

- [ ] Đọc `settings.gradle.kts` và liệt kê các project paths thật.
- [ ] Dùng `./gradlew projects` trước khi viết CI script với nested paths.
- [ ] Phân biệt root path `:`, project path `:app` và task path `:app:build`.
- [ ] Không thêm root project name như một path segment.
- [ ] Không dùng slash filesystem thay dấu `:` cho Gradle tasks.
- [ ] Hiểu task selector `build` từ root có thể chọn mọi subprojects.
- [ ] Hiểu `:build` chỉ chọn root task; prerequisites có thể kéo thêm tasks.
- [ ] Khi chỉ muốn một module, dùng full task path có `:` đầu.
- [ ] Không nhầm Gradle task dependency với Java project dependency/classpath.
- [ ] Kiểm tra `implementation(project(":shared"))` trước khi dùng shared classes.
- [ ] Hiểu `:app:build` có thể kéo shared compile/artifact tasks nhưng không shared tests.
- [ ] Dùng `:module:tasks --all` và `help --task` để tìm task name thật.
- [ ] Dùng `--dry-run` để xem graph trước khi chạy action nguy hiểm/chậm.
- [ ] Dùng `--info`/`--stacktrace` để điều tra errors thực.
- [ ] Không dùng name abbreviations mơ hồ trong CI.
- [ ] Lưu ý exception của help/dependencies task selectors.
- [ ] Dùng `--continue` chỉ để chạy independent tasks sau failure, không bỏ qua prerequisites.
- [ ] Dùng `--parallel` khi outputs/resources giữa modules an toàn.
- [ ] Không vô tình bỏ toàn bộ tests bằng `-x test`.
- [ ] Với projectDir custom, phân biệt logical path và physical directory.
- [ ] Với included builds, phân biệt `includeBuild` với `include`.
- [ ] Test chương trình bằng `:app:run` và kiểm tra output Java 17 độc lập.

## 21. Câu hỏi tự kiểm tra

1. **Root project path là gì?** `:`, không chứa `rootProject.name`.
2. **`:app` khác `:app:build` thế nào?** Một cái là project path, một cái là task path.
3. **`./gradlew build` từ root chạy cái gì?** Chọn `build` tasks của root và các subprojects có task đó, rồi chạy prerequisites.
4. **`./gradlew :build` từ root có tự chọn `:app:build`?** Không, trừ khi root task có dependency được định nghĩa rõ.
5. **`./gradlew :app:build` có thể chạy shared tasks không?** Có, nếu app có project dependency đến shared hoặc prerequisites khác.
6. **`:app:build` có buộc chạy `:shared:test` không?** Không tự động chỉ vì `implementation(project(":shared"))`.
7. **`./gradlew test` khác `./gradlew :test`?** Selector trong hierarchy so với root-only test task path.
8. **Vì sao `:test` không tồn tại ở lab?** Root chỉ áp Base plugin, không áp Java.
9. **Chạy duy nhất Java library JAR task thế nào?** `./gradlew :shared:jar`.
10. **Chạy app main với hai arguments thế nào?** `./gradlew :app:run --args="alpha beta"`.
11. **Cần gì để app Java import class của shared?** `implementation(project(":shared"))`.
12. **Chỉ `dependsOn(":shared:build")` có cấp shared classes vào compile classpath không?** Không.
13. **`include("services:api")` tạo logical path gì?** `:services:api`.
14. **Đổi `projectDir` của app có đổi `:app:build` không?** Không nếu project path/name giữ nguyên.
15. **Gọi từ thư mục app bằng `../gradlew build` có tự test shared không?** Không chọn sibling shared test; chỉ có thể chạy shared producer tasks cần cho app.
16. **`--dry-run` dùng để làm gì?** Xem scheduled tasks mà không chạy actions.
17. **`--parallel` có thay phạm vi task path không?** Không, chỉ ảnh hưởng cách thực thi các tasks độc lập.
18. **`--continue` có chạy task phụ thuộc một failed prerequisite không?** Không; chỉ tiếp tục tasks đủ điều kiện.
19. **Name abbreviation có luôn an toàn cho CI không?** Không, có thể ambiguous sau khi thêm tasks/plugins.
20. **`includeBuild("build-logic")` có tạo `:build-logic` như subproject bình thường không?** Không; đó là included build có identity/Settings riêng.
21. **Vì sao nên dùng full task path?** Để tránh gọi nhầm module và làm CI/log dễ hiểu.
22. **`java -cp a:b` dấu `:` có nghĩa project path không?** Không, đó là Java classpath separator trên Unix.
23. **Task `help`/`dependencies` không prefix có chạy báo cáo cho mọi modules không?** Không nên giả định; Gradle xử lý các report selectors đặc biệt, thường chỉ current project.
24. **Vì sao một task `:app:test` có thể chạy task `:shared:compileJava`?** Project dependency/selected variants cần shared compiled artifact.
25. **Muốn kiểm thử cả app và shared rõ ràng trong CI?** Gọi root `test` hoặc `:shared:test :app:test`.

## 22. Tài liệu chính thức của Gradle

- [Gradle — Structuring Multi-Project Builds](https://docs.gradle.org/current/userguide/intro_multi_project_builds.html): project hierarchy, project paths, task selectors và fully qualified task names.
- [Gradle — Multi-Project Builds](https://docs.gradle.org/current/userguide/multi_project_builds.html): `settings.include`, ProjectDescriptor, project dependencies, directory mapping và Gradle 9 project directory rule.
- [Gradle — Command-Line Interface](https://docs.gradle.org/current/userguide/gradle_command_line.html): command syntax, task paths, task selector from subprojects, name abbreviation, `--continue`.
- [Gradle — Command-Line Interface Basics](https://docs.gradle.org/current/userguide/command_line_interface_basics.html): task names, options, colon syntax.
- [Gradle — Declaring Dependencies Between Subprojects](https://docs.gradle.org/current/userguide/declaring_dependencies_between_subprojects.html): `implementation(project(":shared"))`, variant-aware project dependency, producer tasks.
- [Gradle — Structuring and Organizing Gradle Projects](https://docs.gradle.org/current/userguide/organizing_gradle_projects.html): root/subprojects và `projects` task.
- [Gradle — Build Lifecycle](https://docs.gradle.org/current/userguide/build_lifecycle.html): initialization, configuration, execution và task graph.
- [Gradle — Controlling Task Execution](https://docs.gradle.org/current/userguide/controlling_task_execution.html): `dependsOn`, `mustRunAfter`, `shouldRunAfter` và prerequisites.
- [Gradle — Task Configuration Avoidance](https://docs.gradle.org/current/userguide/task_configuration_avoidance.html): `tasks.register`, `tasks.named`, TaskProvider.
- [Gradle — Base Plugin](https://docs.gradle.org/current/userguide/base_plugin.html): root lifecycle tasks `assemble`, `check`, `build`, `clean`.
- [Gradle — Java Library Plugin](https://docs.gradle.org/current/userguide/java_library_plugin.html): `java-library`, `api` và `implementation`.
- [Gradle — Application Plugin](https://docs.gradle.org/current/userguide/application_plugin.html): `run`, `--args`, mainClass.
- [Gradle — Composite Builds](https://docs.gradle.org/current/userguide/composite_builds.html): phân biệt included builds với multi-project builds.
