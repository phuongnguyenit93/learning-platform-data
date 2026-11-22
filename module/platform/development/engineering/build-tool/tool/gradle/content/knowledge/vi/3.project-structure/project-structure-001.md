# Khởi tạo dự án bằng `gradle init` và lựa chọn mẫu phù hợp

## 1. Tổng quan và mục tiêu

`gradle init` giúp tạo một bộ khung Gradle build mới từ những lựa chọn về loại sản phẩm, ngôn ngữ, DSL, framework kiểm thử và cách tổ chức project. Sau khi học bài này, bạn có thể chọn đúng template thay vì tạo ngẫu nhiên, tự khởi tạo ứng dụng/thư viện Java, hiểu các file sinh ra và kiểm tra build bằng Gradle Wrapper.

**Phân biệt ngay từ đầu:** `init` là thao tác tạo cấu trúc ban đầu. Nó không tự hoàn thành nghiệp vụ của ứng dụng, không tự biến Java CLI thành Spring Boot hay Android và không thay thế việc thiết kế dependency, build pipeline, kiểm thử đầy đủ hoặc review cấu hình sản xuất.

## 2. `gradle init` làm việc như thế nào?

Gradle cung cấp sẵn task `init` thông qua **Build Init plugin** trên root project. Trong một thư mục mới chưa có `build.gradle`, bạn vẫn có thể chạy `gradle init` để tạo build. Plugin sẽ hỏi các lựa chọn còn thiếu hoặc nhận tham số CLI để tự tạo bộ khung.

```text
Thư mục dự án mới
       |
       v
   gradle init
       |
       +-- Chọn type: application / library / plugin / basic / pom
       +-- Chọn DSL: Groovy hoặc Kotlin cho file build
       +-- Chọn test framework, tên, package, Java version
       +-- Chọn cấu trúc project (nếu template hỗ trợ)
       |
       v
settings.gradle(.kts) + build.gradle(.kts)
gradlew + gradlew.bat + gradle/wrapper/*
source/test mẫu (với loại build phù hợp)
       |
       v
./gradlew projects / build / test / run (theo task có thật)
```

Các file thường gặp:

| Nhóm | File/thư mục | Vai trò |
| --- | --- | --- |
| Settings | `settings.gradle` hoặc `settings.gradle.kts` | Đặt tên root project và khai báo những subproject được include. |
| Build script | `build.gradle` hoặc `build.gradle.kts` ở project tương ứng | Áp dụng plugin, khai báo repository, dependency, task, toolchain và main class. |
| Wrapper | `gradlew`, `gradlew.bat`, `gradle/wrapper/gradle-wrapper.jar`, `gradle/wrapper/gradle-wrapper.properties` | Chạy bản Gradle do dự án chọn, kể cả máy chưa cài Gradle toàn hệ thống. |
| Source/test | `src/main/java`, `src/test/java` hoặc tương đương | Code và test mẫu nếu template hỗ trợ. |
| Version catalog | `gradle/libs.versions.toml` (nếu có) | Quản lý alias/phiên bản thư viện hoặc plugin. |

Template và cấu trúc file có thể thay đổi theo phiên bản Gradle. Không mặc định tất cả source nằm ở root: project mới có thể có subproject `:app` với `app/build.gradle`.

## 3. Chuẩn bị trước khi khởi tạo

Bạn cần **Gradle CLI** để chạy lệnh `gradle init` lần đầu và JDK phù hợp nếu xây dựng dự án Java. Kiểm tra:

```bash
gradle --version
java -version
javac -version
```

Hai phiên bản Java cần phân biệt: **JDK chạy chính Gradle** phải tương thích với Gradle version; còn **Java version dùng để biên dịch sản phẩm** có thể được khai báo riêng bằng Java toolchain. Ví dụ `--java-version 17` không tự bảo đảm JDK 17 đã cài hoặc có dịch vụ cung cấp toolchain.

Nên tạo dự án trong thư mục trống, chẳng hạn:

```bash
# macOS/Linux
mkdir hello-gradle
cd hello-gradle
gradle init
```

Trên Windows PowerShell, có thể dùng `New-Item -ItemType Directory hello-gradle` và `Set-Location hello-gradle` trước khi chạy `gradle init`. Hoặc chạy trực tiếp từ thư mục cha với option `--into` để chọn thư mục đầu ra.

**Không sử dụng `--overwrite` mặc định** khi thử nghiệm: option này cho phép ghi đè file có sẵn. Với mã nguồn thực tế, tạo thư mục mới hoặc bản sao để tránh thay file chưa được review. Khi cần tải Gradle distribution hoặc dependency, hãy kiểm tra kết nối mạng, proxy, repository và quyền truy cập.

## 4. Chọn template phù hợp

Quyết định theo **sản phẩm đầu ra** trước, rồi mới chọn DSL và test framework.

| Nhu cầu | Build type | Vì sao phù hợp |
| --- | --- | --- |
| Ứng dụng Java có `main()`, chạy từ terminal | `java-application` | Dùng khả năng plugin `application`, có task chạy ứng dụng sau khi cấu hình main class. |
| Thư viện/JAR Java cho module khác dùng | `java-library` | Dùng build thư viện, kiểm thử, đóng gói và các dependency configuration như `api`/`implementation`. |
| Tự viết plugin mở rộng Gradle bằng Java | `java-gradle-plugin` | Khung dành cho tác giả Gradle plugin, hỗ trợ kiểm thử logic plugin. |
| Bộ khung Gradle gần như trống | `basic` | Cho phép tự thêm plugin/source/test theo yêu cầu. |
| Ứng dụng hoặc thư viện Kotlin/JVM | `kotlin-application`, `kotlin-library` | Source là Kotlin/JVM; file build vẫn có thể dùng Kotlin hoặc Groovy DSL. |
| Ứng dụng/thư viện Groovy, Scala | `groovy-application`, `groovy-library`, `scala-application`, `scala-library` | Các template theo ngôn ngữ nguồn. |
| Gradle plugin viết bằng Kotlin hoặc Groovy | `kotlin-gradle-plugin`, `groovy-gradle-plugin` | Khung phát triển plugin tương ứng. |
| Chuyển build Maven đã có `pom.xml` | `pom` | Chuyển đổi cấu hình Maven sang Gradle để tiếp tục đối chiếu và kiểm thử. |
| Dự án native C++/Swift | `cpp-application`, `cpp-library`, `swift-application`, `swift-library` | Template cho hệ sinh thái native và toolchain phù hợp. |

**Ví dụ chọn mẫu:** viết công cụ Java đọc CSV → `java-application`; viết JAR xử lý validation cho nhiều service → `java-library`; viết custom Gradle task/plugin để các repo khác dùng → `java-gradle-plugin`; muốn tự thiết kế mọi cấu hình → `basic`; có Maven multi-module sẵn cần chuyển → `pom` trong bản sao để kiểm tra tương đương.

`gradle init` chuẩn không cung cấp loại `spring-boot` hay `android-application`. Với Spring Boot, chọn Gradle trong Spring Initializr hoặc tự áp dụng Spring Boot plugin/dependency sau khi có Java build. Với Android, dùng Android Studio/Android Gradle Plugin. Không suy đoán một build type chỉ từ tên framework.

## 5. Những lựa chọn quan trọng trong `gradle init`

### 5.1. Loại build: `--type`

`java-application` sinh khung chương trình có thể chạy với entry point; `java-library` sinh khung cho mã được thành phần khác tiêu thụ. `java-gradle-plugin` tạo plugin dùng trong **quá trình build Gradle**, khác việc áp dụng plugin `java` trong ứng dụng thông thường. `basic` không tự tạo khả năng compile/test Java. `pom` yêu cầu dự án Maven/POM hợp lệ.

### 5.2. Ngôn ngữ cấu hình: `--dsl kotlin` hoặc `--dsl groovy`

Đây là ngôn ngữ của **build script**, không phải ngôn ngữ chương trình. Hai đoạn sau cấu hình plugin application tương đương:

```kotlin
// build.gradle.kts: Kotlin DSL
plugins {
    application
}

application {
    mainClass = "dev.example.app.App"
}
```

```groovy
// build.gradle: Groovy DSL
plugins {
    id 'application'
}

application {
    mainClass = 'dev.example.app.App'
}
```

Cả hai có thể dùng để build **source Java**; ví dụ giả định bạn đã có lớp `dev.example.app.App` chứa `main`. Chọn DSL thống nhất với dự án/đội nhóm. Kotlin DSL giúp IDE kiểm tra cú pháp và kiểu; Groovy DSL thường xuất hiện trong nhiều build script lâu đời. Chọn `--dsl kotlin` không tự chuyển mã Java thành Kotlin.

### 5.3. Kiểm thử: `--test-framework`

Với Java, `junit-jupiter` là lựa chọn phổ biến cho JUnit 5. Tùy bản Gradle và build type, các lựa chọn có thể gồm `junit` (JUnit 4), `testng`, `spock`. Chọn framework theo chuẩn của nhóm và kiểm chứng bằng task `test` sau init. Template có thể tạo lớp test mẫu, nhưng sự tồn tại của file test không đồng nghĩa kiểm thử chạy thành công.

### 5.4. Tên, package, thư mục: ba khái niệm khác nhau

| Tham số | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| `--project-name` | `hello-app` | Tên logic root build, thường ghi vào `settings.gradle(.kts)`. |
| `--package` | `dev.example.hello` | Java package của source mẫu, thường ánh xạ thành thư mục `dev/example/hello`. |
| `--into` | `./hello-app` | Thư mục vật lý nhận các file; nếu bỏ qua thì dùng thư mục hiện tại. |

Dấu `-` trong `hello-app` có thể dùng cho tên build, nhưng không hợp lệ trong thành phần package Java. Package nên dùng chữ thường phân cách bằng dấu chấm. Thay đổi package về sau đòi hỏi sửa `package`, `import` và đúng source path.

### 5.5. Phiên bản Java: `--java-version`

Ví dụ `--java-version 17` chọn Java version dành cho project được sinh. Đây là lựa chọn target/toolchain của mã nguồn; nó khác với JVM dùng để chạy Gradle. Nếu JDK yêu cầu chưa có, build có thể thất bại trừ khi toolchain resolver được cấu hình đúng.

### 5.6. Cấu trúc nhiều project: `--split-project` và `--no-split-project`

Một số template hỗ trợ tách chức năng thành nhiều subproject. Khi mới học hoặc dự án rất nhỏ, bắt đầu bằng `--no-split-project`. Khi cần tách ứng dụng và thư viện dùng chung, `--split-project` có thể là điểm khởi đầu nếu template hỗ trợ.

Tên option **không bảo đảm** source luôn nằm trong root build: một ứng dụng đơn giản vẫn có thể có subproject `:app`. Luôn đọc `settings.gradle(.kts)` và chạy `./gradlew projects` để xác định project paths thực.

### 5.7. Các cờ khác

- `--use-defaults`: dùng giá trị mặc định cho lựa chọn chưa khai báo, thích hợp khi tự động hóa.
- `--comments`/`--no-comments`: bật hoặc tắt chú thích trong file sinh.
- `--incubating`/`--no-incubating`: cho phép hoặc tránh các API/tính năng Gradle còn thử nghiệm.
- `--overwrite`: cho phép ghi đè file hiện có; chỉ dùng khi chủ động chấp nhận.
- `gradle help --task init`: tra cứu các option task trên bản Gradle đang cài.

Danh sách câu hỏi, giá trị mặc định và các template có thể thay đổi theo phiên bản. Khi không chắc, xem tài liệu Build Init Plugin tương ứng với Gradle version.

## 6. Cách A: khởi tạo bằng trình hướng dẫn tương tác

Trong thư mục mới, chạy:

```bash
gradle init
```

Gradle có thể hỏi (thứ tự tùy phiên bản): loại sản phẩm, ngôn ngữ nguồn, DSL, test framework, project name, Java package, Java version và có tách project hay không. Chọn dựa trên **tên lựa chọn được hiển thị**, không học thuộc số thứ tự của menu từ một hướng dẫn cũ.

Ví dụ bài thực hành: chọn Java application, Groovy/Kotlin DSL theo nhóm, JUnit Jupiter, package `dev.example.learning`, Java 17 nếu tương thích, cấu trúc đơn giản. Sau đó chạy:

```bash
./gradlew --version
./gradlew projects
./gradlew build
```

Khi mới init, Gradle CLI là `gradle` vì chưa có Wrapper trong thư mục; sau init dùng `./gradlew` trên macOS/Linux hoặc `gradlew.bat` trên Windows. Không cần cài cùng một bản Gradle trên mọi máy khi project đã có Wrapper hợp lệ.

## 7. Cách B: khởi tạo Java application bằng tham số rõ ràng

Khi muốn kết quả có thể lặp lại mà không chọn menu, truyền sẵn các thông số. Ví dụ Java 17, Groovy DSL, JUnit Jupiter và layout không chủ động tách chức năng:

```bash
# macOS/Linux: chạy trong thư mục cha
gradle init \
  --type java-application \
  --dsl groovy \
  --test-framework junit-jupiter \
  --package dev.example.hello \
  --project-name hello-app \
  --java-version 17 \
  --no-split-project \
  --use-defaults \
  --into ./hello-app

cd hello-app
./gradlew projects
./gradlew build
```

Dấu `\` ở cuối dòng là cú pháp nối dòng của Bash/zsh. Trên Windows PowerShell, viết lệnh `gradle init` trên một dòng:

```powershell
gradle init --type java-application --dsl groovy --test-framework junit-jupiter --package dev.example.hello --project-name hello-app --java-version 17 --no-split-project --use-defaults --into ./hello-app
Set-Location hello-app
.\gradlew.bat projects
.\gradlew.bat build
```

Sau khi sinh, **không giả định** app luôn ở root hay có tên `:app`: xem danh sách project và plugin của từng project trước khi chạy task. Nếu `./gradlew projects` cho thấy `:app` chứa application plugin, dùng:

```bash
./gradlew :app:tasks --all
./gradlew :app:run
```

Nếu application plugin ở root, task là `./gradlew run`; nếu project path khác thì thay tương ứng.

### Ví dụ Java 17+ chỉnh sửa sau khi init

Tìm source root của project chứa plugin `application`, thêm file `dev/example/hello/HelloApp.java` vào thư mục `src/main/java` của **project đó**:

```java
package dev.example.hello;

public final class HelloApp {
    private HelloApp() {
    }

    public static void main(String[] args) {
        System.out.println("Hello from Gradle!");
    }
}
```

Cập nhật main class trong build script Groovy DSL của project chứa ứng dụng:

```groovy
application {
    mainClass = 'dev.example.hello.HelloApp'
}
```

Chạy task `run` đúng project. Chương trình in chính xác:

```text
Hello from Gradle!
```

Đây là ví dụ **tùy chỉnh sau init**; không khẳng định mọi bản Gradle tạo sẵn file `HelloApp.java` hoặc đặt source tại root. Đoạn Java tự hoàn chỉnh và biên dịch được trên JDK 17+ khi đặt đúng package path.

## 8. Cách C: khởi tạo Java library

Nếu xây thư viện thay vì chương trình có entry point, chọn `java-library`:

```bash
gradle init \
  --type java-library \
  --dsl kotlin \
  --test-framework junit-jupiter \
  --package dev.example.util \
  --project-name util-lib \
  --java-version 17 \
  --no-split-project \
  --use-defaults \
  --into ./util-lib

cd util-lib
./gradlew projects
./gradlew build
./gradlew test
```

Ví dụ này tạo **source Java + Kotlin DSL**. Plugin Java Library thường cung cấp khả năng compile, test, đóng gói JAR và `build`; nó không tự có task `run` như Java application.

Ví dụ lớp thư viện Java 17+:

```java
package dev.example.util;

public final class TextUtil {
    private TextUtil() {
    }

    public static String greet(String name) {
        return "Hello, " + name;
    }
}
```

Đặt file `TextUtil.java` trong source root/package đúng vị trí của project thư viện. Một ứng dụng khác có thể sử dụng class này nếu đã khai báo dependency và đưa artifact lên classpath. JAR tạo bởi task `jar` thường nằm trong `build/libs` của project thư viện. Nếu muốn thử mã thư viện, tạo test JUnit và chạy `test`, thay vì gọi `run` trên library.

## 9. Cách D: `basic` cho bộ khung gần như trống

```bash
gradle init --type basic --dsl groovy --project-name sandbox --use-defaults --into ./sandbox
cd sandbox
./gradlew projects
./gradlew tasks
```

`basic` là nền tảng Gradle, không có nghĩa đã cấu hình Java plugin, source và JUnit. Ví dụ, nếu muốn từ build trống bật khả năng biên dịch Java, trong `build.gradle` của project liên quan:

```groovy
plugins {
    id 'java'
}
```

Bạn còn cần source, repository/dependency và test thực tế. Khi mục đích đã rõ là ứng dụng hoặc thư viện Java, template chuyên biệt giúp tránh các bước cấu hình lặp lại.

## 10. Khi nào dùng template `pom` để chuyển Maven?

Build Init có khả năng chuyển Maven build đã có `pom.xml` sang Gradle. Đây là tác vụ migration, không phải cách tạo ứng dụng mới từ zero. Chỉ dùng khi có POM hợp lệ, thực hiện trên bản sao/nhánh an toàn rồi đối chiếu:

1. Dependency, repository, Maven scope, exclusion và các dependency bắc cầu.
2. Maven plugin/goal so với Gradle plugin/task, packaging JAR/WAR.
3. Source/test, Java version, profile, generated source và resource filtering.
4. Build/test report, artifact đầu ra và quy trình CI/publish.
5. Các module con, dependency giữa module và cấu hình đặc thù dự án.

`gradle init --type pom` có thể chuyển được nhiều cấu hình thường gặp, nhưng **không chứng minh** hai build tương đương chỉ vì lệnh init thành công. Với build sản xuất, cần chạy so sánh và sửa các trường hợp khác biệt.

## 11. Hiểu cấu trúc sinh ra

Một build ứng dụng Java có thể trông như sau, nhưng đường dẫn thực tế phụ thuộc template và Gradle version:

```text
hello-app/
├── settings.gradle                 # hoặc settings.gradle.kts
├── gradlew
├── gradlew.bat
├── gradle/
│   ├── wrapper/
│   │   ├── gradle-wrapper.jar
│   │   └── gradle-wrapper.properties
│   └── libs.versions.toml          # nếu có catalog
└── app/                             # nếu có project :app
    ├── build.gradle               # hoặc build.gradle.kts
    └── src/
        ├── main/java/...
        └── test/java/...
```

`settings.gradle(.kts)` là nguồn sự thật về root name và project path: `rootProject.name = 'hello-app'` đặt **tên**, còn `include 'app'` tạo **subproject path** `:app`. Không được suy luận tên root build thành `:hello-app:run`.

`build.gradle(.kts)` thuộc project nào sẽ cấu hình plugin, task, dependency của project đó. Với `application`, kiểm tra `mainClass`; với `java-library`, kiểm tra dependency cấu hình phù hợp.

`gradle/wrapper/gradle-wrapper.properties` khai báo Gradle distribution/version. `gradlew`, `gradlew.bat` và `gradle-wrapper.jar` là bộ chạy thống nhất giữa máy dev và CI. **Commit cả bốn file Wrapper** cùng mã nguồn; không commit `build/` (output tạo ra khi build) theo thông lệ.

`gradle/libs.versions.toml`, nếu tồn tại, hỗ trợ alias cho dependency/plugin; tên alias được sử dụng trong build script phải khớp catalog. Không cần tự tạo catalog bằng tay nếu bài học hiện tại chưa yêu cầu.

## 12. Wrapper và các lệnh kiểm tra hậu khởi tạo

| Việc cần làm | macOS/Linux | Windows |
| --- | --- | --- |
| Xem Gradle/JVM đang chạy | `./gradlew --version` | `gradlew.bat --version` |
| Liệt kê project | `./gradlew projects` | `gradlew.bat projects` |
| Liệt kê task | `./gradlew tasks --all` | `gradlew.bat tasks --all` |
| Build toàn bộ task cần thiết | `./gradlew build` | `gradlew.bat build` |
| Chạy test nếu task tồn tại | `./gradlew test` | `gradlew.bat test` |
| Chạy ứng dụng tại project `:app` nếu có | `./gradlew :app:run` | `gradlew.bat :app:run` |

Nên xác nhận từng bước:

- `--version` chứng minh Wrapper khởi chạy, cho biết Gradle/JVM thực dùng. Nếu lần đầu tải Gradle distribution, mạng có thể là yếu tố gây lỗi.
- `projects` cho biết các project path để gọi đúng task.
- `tasks --all` giúp xác định application/test/jar tasks có thật trong project nào.
- `build` chạy lifecycle build theo plugin; với project Java, thường có compile/test/assemble.
- `test` chỉ gọi được khi có task test; trong `basic` chưa thêm plugin Java, việc không có task test là bình thường.
- `run` là task của project có khả năng application; không nên gọi `:app:run` nếu chưa thấy project `:app`.
- Với library, kiểm tra JAR sinh từ task `jar` dưới `build/libs` của chính project đó.

**Không dùng số task hoặc stdout template cố định làm tiêu chí.** Các lớp mã nguồn, dependency version, tên file và log có thể khác theo Gradle version, lựa chọn split-project và cache. Tiêu chí là task tồn tại, build thành công, artifact đúng mục tiêu.

Khi lỗi, dùng `./gradlew build --stacktrace` để xem nguyên nhân chi tiết; dùng `./gradlew help --task build` để xem thông tin task. Cần kiểm tra tính tương thích Java–Gradle trước khi coi lỗi JDK là lỗi template.

## 13. Single-project và multi-project sau khi init

Đối với bài học đầu tiên, giữ cấu trúc gọn là lựa chọn tốt. Khi sản phẩm bắt đầu có ứng dụng và một thư viện cần được build/kiểm thử độc lập, có thể thiết kế project `:app` và `:core`. Đây là ví dụ **tự tổ chức sau init**, không khẳng định Gradle init tự tạo đúng tên này:

```groovy
// settings.gradle
rootProject.name = 'sample-multi'
include 'app', 'core'
```

```groovy
// core/build.gradle
plugins {
    id 'java-library'
}
```

```groovy
// app/build.gradle
plugins {
    id 'application'
}

dependencies {
    implementation project(':core')
}
```

Ứng dụng `:app` cần artifact của thư viện `:core` trên classpath. Gradle sẽ xác định các producer task cần thiết qua dependency metadata; không cần thêm `dependsOn(':core:build')` máy móc để thay thế project dependency. Nếu chọn `--split-project`, hãy đọc source/settings sinh ra để hiểu subproject thật; option này không tự quyết định kiến trúc dài hạn thay bạn.

## 14. Các lỗi phổ biến và cách xử lý

| Triệu chứng hoặc ngộ nhận | Cách hiểu đúng và hành động |
| --- | --- |
| `gradle` không nhận diện | Cài Gradle CLI/kiểm tra PATH để tạo project lần đầu; sau init dùng Wrapper. |
| Gradle báo Java không tương thích | Xem `java -version`, `gradle --version` và ma trận tương thích Gradle–JDK. |
| Chọn `--dsl kotlin` rồi kỳ vọng source Kotlin | DSL chỉ điều khiển build scripts; chọn `kotlin-application` nếu cần source Kotlin. |
| `Task 'run' not found` | `java-library`/`basic` không mặc nhiên có run; kiểm tra plugin và `tasks --all`. |
| `Project 'app' not found` | Không giả định `:app` luôn tồn tại; xem `settings.gradle(.kts)`/`projects`. |
| `--type spring-boot` hoặc `--type android-application` lỗi | Không phải loại template mặc định; dùng generator/plugin chuyên dụng. |
| Package như `my-app` không hợp lệ | Package Java dùng dạng `dev.example.app`, khác với tên build. |
| `gradle init` muốn thay file đã có | Khởi tạo tại thư mục trống hoặc bản sao; hạn chế `--overwrite`. |
| Wrapper tải không được | Kiểm tra Gradle distribution URL, mạng, chứng chỉ, proxy, firewall và cache. |
| Lỗi test hoặc dependency resolution | Kiểm tra test framework, repository, dependency, JDK và stacktrace. |
| Dự án Maven convert nhưng artifact không giống trước | So sánh scope/plugin/packaging/lifecycle/test, tiếp tục migration. |
| Copy đường dẫn source từ tutorial mà không thấy file | Cấu trúc thay đổi theo version/layout; đọc kết quả thực của `init`. |

### Checklist nghiệm thu nhanh

- [ ] Build type khớp sản phẩm: application/library/plugin/basic/pom.
- [ ] Ngôn ngữ nguồn, DSL, test framework và Java version đã chọn rõ ràng.
- [ ] `--project-name`, `--package`, `--into` được phân biệt đúng; package hợp lệ.
- [ ] Không ghi đè source cũ ngoài ý muốn.
- [ ] Đã xem `settings.gradle(.kts)`, build script và đúng project path.
- [ ] Có đủ Wrapper, dùng Wrapper để chạy build và commit Wrapper vào Git.
- [ ] `./gradlew --version` và `./gradlew projects` hoạt động.
- [ ] `./gradlew build` thành công; chạy `test`/`run` đúng project khi task tồn tại.
- [ ] Đã review sample source/test, plugin, dependency, artifact và Java toolchain.

## 15. Quy tắc nhớ nhanh

```text
Có ứng dụng Java cần main()/run?       → java-application
Có API/JAR Java cho code khác gọi?      → java-library
Đang viết plugin cho Gradle?           → java-gradle-plugin
Cần bộ khung trống, tự cấu hình?        → basic
Đã có Maven pom.xml cần chuyển?        → pom (và kiểm thử lại)
Cần source Kotlin/Groovy/Scala/native? → chọn type theo ngôn ngữ
```

Sau khi chọn **loại sản phẩm**, lần lượt quyết định **DSL → test framework → Java version → tên/package → project layout → thư mục đích**. Dùng `gradle init` để **tạo** build và `./gradlew` hoặc `gradlew.bat` để **thực thi** build.

**Nguồn chính thức để kiểm tra khi cập nhật Gradle:**

- [Build Init Plugin](https://docs.gradle.org/current/userguide/build_init_plugin.html) — build types và cờ CLI.
- [Installing Gradle](https://docs.gradle.org/current/userguide/installation.html) — cài đặt và khởi tạo.
- [Gradle Wrapper](https://docs.gradle.org/current/userguide/gradle_wrapper.html) — thành phần, dùng và cập nhật Wrapper.
- [Structuring and Organizing Gradle Projects](https://docs.gradle.org/current/userguide/organizing_gradle_projects.html) — root/subproject và layout.
- [Compatibility Matrix](https://docs.gradle.org/current/userguide/compatibility.html) — Gradle–Java compatibility.
