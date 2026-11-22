# Xây dựng ứng dụng Java từ init đến chạy, kiểm thử và phân phối bằng Gradle

## 1. Bài thực hành tổng hợp: đi từ thư mục rỗng đến bản phân phối chạy được

Một ứng dụng Java thực tế không dừng ở việc chạy `javac` thành công. Ta cần khởi tạo build thống nhất, quản lý dependencies, cố định JDK, biên dịch source, kiểm thử tự động, chạy ứng dụng, đóng gói artifact và cuối cùng đưa cho người khác một **bản phân phối** gồm thư viện cùng scripts khởi chạy.

Bài học này thuộc chủ đề **Build Tool Gradle**, nhóm **Thực hành tổng hợp**, với mục tiêu chính **“Xây dựng ứng dụng Java từ init đến chạy, kiểm thử và phân phối”**. Tất cả các phần được nối bằng **một project xuyên suốt**, tránh chỉ giới thiệu những lệnh không có code để thử.

Ta sẽ tạo ứng dụng dòng lệnh `greeting-cli`:

- Nhận tên người dùng qua command-line arguments.
- Chuẩn hóa khoảng trắng, viết hoa chữ cái đầu bằng thư viện Apache Commons Lang.
- In một lời chào UTF-8.
- Dùng **Java 17**, **Gradle Groovy DSL**, **Application plugin** và **JUnit Jupiter**.
- Có Gradle Wrapper để những người khác chạy đúng Gradle version.
- Có tests cho null, blank, chữ thường và nhiều khoảng trắng.
- Tạo JAR, ZIP/TAR distributions, thư mục install và scripts `bin/greeting-cli`/`bin/greeting-cli.bat`.
- Chứng minh bản phân phối chứa dependency cần thiết, nên không đòi người nhận phải tự thêm `commons-lang3.jar` vào classpath.
- Kiểm tra các đầu ra và nhận diện lỗi thường gặp của dependency resolution, toolchain, tests và packaging.

**Kết quả chức năng cuối:** khi chạy `greeting-cli Linh` từ bản đã cài, Java program in:

~~~text
Xin chào, Linh!
~~~

Với `greeting-cli "mai anh"`:

~~~text
Xin chào, Mai anh!
~~~

Đây là chương trình CLI học tập, chưa phải service web hoặc chương trình cài đặt hệ điều hành. Gradle Application plugin tạo scripts và các archives, **không tự đóng gói JRE/JDK**. Máy chạy bản phân phối cần Java runtime tương thích, ở đây là Java 17 hoặc mới hơn phù hợp.

### 1.1. Sơ đồ pipeline

~~~text
Gradle cài sẵn dùng để bootstrap
                   |
                   v
            gradle init
       --type java-application
       --dsl groovy
       --no-split-project
       --java-version 17
                   |
                   v
          Gradle Wrapper
          settings.gradle
           build.gradle
             Java source
                tests
                   |
                   v
        ./gradlew compileJava
                   |
                   v
        ./gradlew test / check
                   |
                   v
       ./gradlew run --args=...
                   |
                   v
      ./gradlew build / assemble
                   |
             +-----+------+
             |            |
             v            v
        JAR artifact   ZIP/TAR distributions
                         +-- bin/ launcher scripts
                         +-- lib/ application JAR
                         +-- lib/ third-party JAR
                         +-- README.txt
                               |
                               v
                 installDist / giải nén
                               |
                               v
                   chạy ngoài Gradle
~~~

### 1.2. Sau bài, người học có thể

1. Chạy `gradle init` đúng options trên Gradle 9.9 và giải thích lựa chọn `--type java-application`, `--dsl groovy`, `--no-split-project`, `--test-framework junit-jupiter` và `--java-version 17`.
2. Phân biệt Gradle cài sẵn khi bootstrap với Gradle Wrapper đã sinh ra.
3. Đọc `settings.gradle`, `build.gradle`, `src/main/java` và `src/test/java`.
4. Cấu hình `application.mainClass` và `java.toolchain` chính xác.
5. Khai báo `implementation`, `testImplementation` và `testRuntimeOnly` đúng mục đích.
6. Dùng `run --args` để kiểm dòng lệnh và stdout.
7. Viết JUnit Jupiter tests và chạy toàn bộ hoặc lọc một method.
8. Hiểu `check`, `assemble`, `build`, `jar` và nhiệm vụ `distZip`/`distTar`/`installDist`.
9. Chạy script trong `build/install/greeting-cli/bin` mà không cần `gradlew run`.
10. Xác minh JAR, dependency JAR, report và archive contents.
11. Biết cách chẩn đoán lỗi và thực hiện CI/release đúng ranh giới.
12. Không nhầm `jar` thường với fat/uber JAR.

---

## 2. Điều kiện thực hiện và tính tương thích phiên bản

Bài thực hành được soạn theo tài liệu chính thức **Gradle 9.9.0** (đối chiếu trong tháng 11/2026). Các tùy chọn `init` có thể khác ở Wrapper version cũ. Khi thực hiện ở dự án khác, hãy đọc trang tài liệu **đúng phiên bản Gradle**.

### 2.1. Cần chuẩn bị

- **JDK 17** cho compiler và runtime của ví dụ; không chỉ có JRE nếu muốn biên dịch.
- Một **Gradle distribution đã được cài và tin cậy** để chạy `gradle init` ban đầu. Sau khi `init` sinh Wrapper, không cần Gradle cài sẵn để dùng project.
- Terminal Linux/macOS hoặc PowerShell trên Windows.
- Kết nối tới Maven Central trong lần đầu Gradle tải Apache Commons Lang và JUnit; nếu đã có đúng artifacts trong dependency cache có thể chạy offline theo điều kiện.
- Một thư mục mới, không chứa files cần bảo toàn. Không chạy `init --overwrite` vào repo đang có dữ liệu quan trọng.
- Quyền tạo source files và đọc/ghi trong project directory.
- JDK phù hợp với Gradle distribution đang dùng. Với Gradle 9.9.0, JVM chạy Gradle phải thuộc dải được Gradle hỗ trợ; JDK 17 là lựa chọn cụ thể phù hợp cho bài này.

### 2.2. Kiểm công cụ

Linux/macOS:

~~~bash
java -version
javac -version
gradle --version
~~~

Windows PowerShell:

~~~powershell
java -version
javac -version
gradle --version
~~~

`java` hiển thị Java runtime, `javac` cho biết JDK compiler; `gradle --version` lúc này chỉ dùng cho bootstrap. Sau khi tạo dự án, **luôn ưu tiên**:

~~~bash
./gradlew --version
~~~

hoặc trên Windows:

~~~powershell
.\gradlew.bat --version
~~~

để xác minh Gradle Wrapper đã pin.

### 2.3. Java runtime, Gradle JVM và toolchain khác nhau

- **Gradle JVM:** Java process chạy Gradle Daemon. Kiểm ở `./gradlew --version`.
- **Java toolchain:** JDK mà Gradle lựa chọn cho JavaCompile, Test và các task hỗ trợ toolchain.
- **Java được gọi bởi start script:** Java runtime hiện có trên **máy chạy bản phân phối**, thường qua `JAVA_HOME` hoặc `PATH`, không tự lấy JDK trong source repository.
- **IDE Project SDK:** có thể là Java version khác nếu IDE chưa đồng bộ.

Một cấu hình `java { toolchain { languageVersion = JavaLanguageVersion.of(17) } }` giúp Gradle chọn Java 17 toolchain cho công việc Java; nó **không tạo JDK 17 bên trong ZIP distribution**.

---

## 3. Bước khởi tạo: `gradle init` và lựa chọn template có kiểm soát

Theo tài liệu Gradle 9.9, Build Init plugin hỗ trợ `java-application`, Groovy DSL, JUnit Jupiter, package, project name, `--into` và lựa chọn không tách thành nhiều subprojects. Bài này **chủ động chọn một project duy nhất** để tất cả `build.gradle` và `build/` nằm ở root.

### 3.1. Khởi tạo từ thư mục cha (Linux/macOS)

Ở một thư mục học tập không chứa project khác cần ghi đè, chạy:

~~~bash
gradle init \
  --type java-application \
  --dsl groovy \
  --test-framework junit-jupiter \
  --package org.example.greeting \
  --project-name greeting-cli \
  --no-split-project \
  --java-version 17 \
  --use-defaults \
  --into ./greeting-cli

cd greeting-cli
./gradlew --version
~~~

Đọc ý nghĩa của từng tham số:

| Tham số | Lý do |
| --- | --- |
| `--type java-application` | Tạo build ứng dụng Java CLI, áp Application plugin |
| `--dsl groovy` | Sinh `.gradle` chứ không phải `.gradle.kts` |
| `--test-framework junit-jupiter` | Chọn JUnit Jupiter, không nhầm JUnit 4 |
| `--package org.example.greeting` | Namespace Java trong source được tạo |
| `--project-name greeting-cli` | Root project name nhất quán với archive/scripts |
| `--no-split-project` | Tránh template nhiều module, dùng root single-project |
| `--java-version 17` | Project được sinh cho Java 17 |
| `--use-defaults` | Chọn mặc định cho những câu hỏi khác chưa đặt |
| `--into ./greeting-cli` | Tạo project trong subfolder mới |

**Lưu ý:** tên file và template sample code Gradle init sinh ra có thể thay đổi giữa các Gradle versions. Ở bài này ta **thay thế rõ ràng build files và những sample Java classes** bằng nội dung ở phần 4–6. Vì thế không phụ thuộc chính xác template chọn tên `App.java` hay `Main.java` trong một version cụ thể.

### 3.2. PowerShell trên Windows

Bạn có thể viết tất cả options trên một dòng (không cần backslash continuation):

~~~powershell
gradle init --type java-application --dsl groovy --test-framework junit-jupiter --package org.example.greeting --project-name greeting-cli --no-split-project --java-version 17 --use-defaults --into ./greeting-cli
Set-Location greeting-cli
.\gradlew.bat --version
~~~

Nếu PowerShell không tìm thấy `gradle`, phải cài/bootstrap Gradle distribution phù hợp hoặc dùng IDE trusted Gradle installation để tạo project. **Không sử dụng một Wrapper JAR lạ lấy từ web** để giải quyết lỗi này.

### 3.3. Nếu muốn dùng tương tác

Từ thư mục rỗng có Gradle cài sẵn:

~~~bash
gradle init
~~~

Chọn **Java application**, **Groovy DSL**, **JUnit Jupiter**, **Java 17** và **single-project** theo prompts của Gradle version. Vì prompts/version có thể khác, phần còn lại của bài dùng command `init` có flags cố định để giảm mơ hồ.

### 3.4. Tại sao không chạy `./gradlew init` ở thư mục rỗng?

Một thư mục rỗng **chưa có Wrapper**. Để có lệnh `./gradlew` cần `gradlew`/`gradlew.bat`, `gradle/wrapper/gradle-wrapper.jar` và properties. Gradle cài sẵn chỉ dùng bước bootstrap. `gradle init` tạo Wrapper cho project mới, sau đó commit Wrapper vào version control.

Nếu đang ở **repository đã có Wrapper tin cậy**, có thể dùng Wrapper của repository đó cho tasks tương ứng, nhưng không biến việc re-init một repo có source thành hành động mặc định.

### 3.5. Không dùng `--overwrite` thiếu chủ đích

`gradle init` có option `--overwrite` cho phép ghi lên files hiện có. Bài này dùng `--into` đến một thư mục mới để tránh phá source. Nếu trong `greeting-cli` đã có files cần giữ, dừng lại và xác định mục tiêu, **không chạy `--overwrite` để ép cho lệnh thành công**.

---

## 4. Khóa cấu trúc dự án mà toàn bộ bài sẽ sử dụng

Sau `init` với `--no-split-project`, ta dùng một root project. Bố cục cuối cùng:

~~~text
greeting-cli/
├── settings.gradle
├── build.gradle
├── gradlew
├── gradlew.bat
├── gradle/
│   └── wrapper/
│       ├── gradle-wrapper.jar
│       └── gradle-wrapper.properties
├── src/
│   ├── main/java/org/example/greeting/
│   │   ├── Greeter.java
│   │   └── Main.java
│   ├── test/java/org/example/greeting/
│   │   └── GreeterTest.java
│   └── dist/
│       └── README.txt
└── build/                          (sinh bởi Gradle khi chạy tasks)
    ├── classes/
    ├── libs/
    ├── reports/tests/test/
    ├── test-results/test/
    ├── scripts/
    ├── install/
    └── distributions/
~~~

Các thư mục trong `build/` chỉ xuất hiện khi tasks liên quan đã chạy. `build/` **không phải source**, không cần tạo thủ công. Root `settings.gradle` và `build.gradle` là files mà chúng ta sẽ viết đầy đủ ở phần sau.

**Xử lý sample mà init sinh sẵn:** template có thể sinh `App.java`/`AppTest.java` trong package đã chọn. Hãy xác định và **xóa đúng các file sample** khi thay bằng `Greeter.java`/`Main.java`/`GreeterTest.java` của bài này, để chúng không làm lệch classpath/tests. Đừng xóa cả `src` hay `gradle/wrapper`. Nếu build initializer tạo thêm `gradle/libs.versions.toml` hoặc comment files, chúng có thể giữ lại nhưng **bản `build.gradle` hoàn chỉnh dưới đây không phụ thuộc chúng**.

### 4.1. Vai trò source sets

| Đường dẫn | Nhiệm vụ |
| --- | --- |
| `src/main/java` | Production Java code được compile thành classes, đóng vào JAR |
| `src/main/resources` | Resources đưa vào main runtime classpath, nếu có |
| `src/test/java` | Test classes được compile riêng và không nằm trong production JAR |
| `src/test/resources` | Test fixtures/resources, nếu có |
| `src/dist` | File tùy chọn chép vào root của application distribution |
| `build/classes/java/main` | Classes của production source |
| `build/classes/java/test` | Classes của test source |
| `build/libs` | JAR artifact |
| `build/reports/tests/test` | HTML test report |
| `build/test-results/test` | JUnit XML và test results |
| `build/install/greeting-cli` | Thư mục distribution đã cài |
| `build/distributions` | ZIP/TAR artifacts |

Đừng đặt `Main.java` trong `src/test/java`: code ở test source set không được đóng vào production JAR theo cấu hình mặc định.

---

## 5. `settings.gradle`: khai tên project một cách rõ ràng

File `settings.gradle` đầy đủ:

~~~groovy
rootProject.name = 'greeting-cli'
~~~

Đây là một **single-project Gradle build**, nên không có `include 'app'` và cũng không cần tạo `app/build.gradle`.

### 5.1. Hậu quả nếu quên `--no-split-project`

Với một số phiên bản/init options, Gradle có thể tạo nhiều projects, ví dụ `app` dưới root và task paths `:app:run`, `:app:test`, archives ở `app/build/...`. **Không trộn layout đó vào bài này**.

Khi đang dùng generated multi-project template thật:
- Nhìn `settings.gradle` để biết `include`.
- Dùng đúng `:app:run`, `:app:test` và `app/build.gradle`.
- Nếu muốn theo chính xác bài, tạo lại **một project mới** với `--no-split-project` thay vì tự dời files thiếu kiểm soát.

### 5.2. Gradle Wrapper cần giữ nguyên và kiểm version

Kiểm `gradle/wrapper/gradle-wrapper.properties`, file do `init` tạo. Một distribution URL cố định có dạng:

~~~properties
distributionUrl=https\://services.gradle.org/distributions/gradle-9.9.0-bin.zip
~~~

URL trên là ví dụ cho Gradle 9.9.0; bản được `init` tạo theo Gradle bootstrap sẽ phản ánh distribution/version thực tế. Không chỉ sửa URL để “nâng version” mà bỏ qua Wrapper JAR và compatibility checks.

**Bảo mật:** Gradle khuyến nghị pin `distributionSha256Sum` với checksum công bố chính thức và xác minh Wrapper JAR, nhất là lúc nâng Gradle. Không bịa checksum hoặc copy checksum của version khác. Mọi người trong team dùng `./gradlew` trên Wrapper đã được review thay vì tùy ý dùng `gradle` khác phiên bản.

---

## 6. `build.gradle` hoàn chỉnh: Java 17, Application, dependencies, JUnit

Đây là file **chạy được** cho demo một project. Thay toàn bộ nội dung `build.gradle` mà init đã sinh (trong project bài tập), giữ nguyên các Wrapper files.

~~~groovy
plugins {
    id 'application'
}

group = 'org.example'
version = '1.0.0'

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.encoding = 'UTF-8'
}

dependencies {
    implementation 'org.apache.commons:commons-lang3:3.17.0'

    testImplementation 'org.junit.jupiter:junit-jupiter:5.12.0'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher:1.12.0'
}

application {
    mainClass = 'org.example.greeting.Main'
}

tasks.named('test', Test) {
    useJUnitPlatform()

    testLogging {
        events 'passed', 'failed', 'skipped'
    }
}
~~~

### 6.1. Vì sao `application` mà không chỉ `java`?

`application` là plugin Gradle dành cho **ứng dụng JVM chạy được**. Nó tự áp **Java plugin** và **Distribution plugin**, đồng thời cung cấp:

- `run` — JavaExec khởi chạy main class với runtime classpath.
- `startScripts` — tạo launch scripts Linux/macOS và Windows.
- `installDist` — bản phân phối dạng thư mục đã cài.
- `distZip` và `distTar` — archives chứa chương trình, scripts và dependencies.
- `assembleDist` — tạo cả ZIP và TAR.
- Các task Java thông thường như `compileJava`, `classes`, `jar`, `test`, `check`, `build`.

Nếu chỉ dùng `java` plugin, không có mặc định mọi task `run` và application distribution. Vì vậy dùng `application` thay vì tự viết một `JavaExec`/Copy task phức tạp.

### 6.2. Vì sao phải cấu hình `mainClass`?

~~~groovy
application {
    mainClass = 'org.example.greeting.Main'
}
~~~

Gradle cần biết class chứa `public static void main(String[] args)` để chạy bằng `run` và điền vào start scripts. **Phải dùng fully qualified class name**, không chỉ `Main` nếu file có package `org.example.greeting`.

Trong bài này `Main.java` có:

~~~java
package org.example.greeting;
~~~

nên class name đúng là `org.example.greeting.Main`. Nếu đổi package/class, phải cập nhật `application.mainClass`.

### 6.3. Dependency scopes

| Configuration | Dùng ở đâu | Ví dụ trong demo |
| --- | --- | --- |
| `implementation` | Compile/runtime main code; runtime distribution chứa phụ thuộc cần thiết | Apache Commons Lang |
| `compileOnly` | Chỉ compile; không tự mang vào runtime | Không dùng trong demo |
| `runtimeOnly` | Chỉ main runtime | Không dùng trong demo |
| `testImplementation` | Compile/runtime tests | JUnit Jupiter API + engine qua aggregate artifact |
| `testRuntimeOnly` | Chỉ test runtime | JUnit Platform Launcher |
| `annotationProcessor` | Annotation processing compile main | Không dùng |

`implementation 'org.apache.commons:commons-lang3:3.17.0'` giúp `Greeter.java` import `org.apache.commons.lang3.StringUtils`. Đó là **external production dependency**, sẽ được Application plugin đưa vào `lib/` của distribution khi cần tại runtime.

`testImplementation 'org.junit.jupiter:junit-jupiter:5.12.0'` và `testRuntimeOnly 'org.junit.platform:junit-platform-launcher:1.12.0'` dành cho test execution, **không nên tự chui vào production runtime distribution**.

### 6.4. Gradle Groovy DSL khác Java

- `build.gradle` là Gradle **Groovy DSL script**; không phải Java file, không compile bằng `javac`.
- `Greeter.java` và `Main.java` là Java 17 production source.
- `GreeterTest.java` là Java 17 test source.
- Gradle plugins tạo task graph; source code được Java compiler compile ở tasks thực thi.

Điều này quan trọng khi chẩn đoán: lỗi `Could not find method implementation` là build script/configuration issue; lỗi `cannot find symbol StringUtils` là dependency/classpath/source issue; lỗi `NoClassDefFoundError` lúc chạy thường liên quan runtime classpath/distribution.

---

## 7. Production Java code: tên, khoảng trắng và chương trình chính

Ứng dụng dùng Commons Lang 3 để chuẩn hóa tên. Tất cả code là **Java 17 source hoàn chỉnh** theo package đã chọn.

### 7.1. `src/main/java/org/example/greeting/Greeter.java`

~~~java
package org.example.greeting;

import org.apache.commons.lang3.StringUtils;

public final class Greeter {
    private Greeter() {
    }

    public static String greetingFor(String rawName) {
        String name = StringUtils.normalizeSpace(rawName);

        if (name == null || name.isBlank()) {
            return "Xin chào, bạn!";
        }

        return "Xin chào, " + StringUtils.capitalize(name) + "!";
    }
}
~~~

Phân tích từng phần:

- `StringUtils.normalizeSpace` bỏ khoảng trắng thừa ở đầu/cuối và chuẩn hóa các cụm khoảng trắng; khi input là `null`, hàm trả về `null`. Đây là API của thư viện `commons-lang3` đã khai.
- `name == null || name.isBlank()` tránh `NullPointerException` vì toán tử `||` short-circuit, và xử lý tên rỗng.
- `StringUtils.capitalize` viết hoa ký tự đầu của chuỗi nếu có thể, **không biến mọi từ thành title case**. Vì vậy `mai anh` thành `Mai anh`, không phải `Mai Anh`.
- Không dùng thời gian hiện tại, random, mutable global state hay environment làm kết quả không xác định.
- Class là `final` với private constructor vì chỉ chứa static utility method.

### 7.2. `src/main/java/org/example/greeting/Main.java`

~~~java
package org.example.greeting;

public final class Main {
    private Main() {
    }

    public static void main(String[] args) {
        String rawName = args.length == 0
            ? "Gradle"
            : String.join(" ", args);

        System.out.println(Greeter.greetingFor(rawName));
    }
}
~~~

Cách hoạt động:

- Không có argument: dùng tên mặc định `Gradle`.
- Có một argument `Linh`: in `Xin chào, Linh!`.
- Có hai arguments `mai`, `anh`: `String.join(" ", args)` thành `mai anh`, rồi `Greeter` viết hoa chữ đầu.
- Tên chứa spaces phải được **quote đúng** ở shell/start script hoặc đặt đúng dạng `--args`.
- Dòng `System.out.println` thêm newline theo runtime; text hiển thị không có khoảng trắng dư.

### 7.3. Đầu ra của các ca mẫu

| Đầu vào `args` | Raw name ở Main | Java stdout |
| --- | --- | --- |
| Không có args | `Gradle` | `Xin chào, Gradle!` |
| `Linh` | `Linh` | `Xin chào, Linh!` |
| `linh` | `linh` | `Xin chào, Linh!` |
| `mai anh` với khoảng trắng được giữ theo arguments | `mai anh` | `Xin chào, Mai anh!` |
| `"   "` là argument toàn khoảng trắng | `   ` | `Xin chào, bạn!` |

Mọi output trong bảng là **output của Java code trên khi build thành công**, không phải ví dụ đã được chạy trên môi trường người đọc. Nếu console hiển thị sai dấu tiếng Việt, kiểm encoding terminal/JVM thay vì tự thay Java logic.

---

## 8. Viết tests đúng package bằng JUnit Jupiter

### 8.1. `src/test/java/org/example/greeting/GreeterTest.java`

~~~java
package org.example.greeting;

import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;

class GreeterTest {
    @Test
    void greetsKnownName() {
        assertEquals(
            "Xin chào, Linh!",
            Greeter.greetingFor("Linh")
        );
    }

    @Test
    void capitalizesInitialLetter() {
        assertEquals(
            "Xin chào, Linh!",
            Greeter.greetingFor("linh")
        );
    }

    @Test
    void normalizesExtraSpaces() {
        assertEquals(
            "Xin chào, Mai anh!",
            Greeter.greetingFor("   mai    anh   ")
        );
    }

    @Test
    void returnsFallbackForBlank() {
        assertEquals(
            "Xin chào, bạn!",
            Greeter.greetingFor("   ")
        );
    }

    @Test
    void returnsFallbackForEmpty() {
        assertEquals(
            "Xin chào, bạn!",
            Greeter.greetingFor("")
        );
    }

    @Test
    void returnsFallbackForNull() {
        assertEquals(
            "Xin chào, bạn!",
            Greeter.greetingFor(null)
        );
    }
}
~~~

Có **6 JUnit test methods**. Mỗi method kiểm một behavior có giá trị thực tế. Vì `Greeter` không truy cập network/files, tests chạy nhanh, độc lập và có expected output rõ.

### 8.2. `useJUnitPlatform` là gì?

~~~groovy
tasks.named('test', Test) {
    useJUnitPlatform()
}
~~~

Gradle `Test` task cần biết dùng JUnit Platform để phát hiện các tests với `org.junit.jupiter.api.Test`. `useJUnitPlatform()` **không tự cung cấp JUnit dependencies**; vì thế chúng ta đã khai `testImplementation` và `testRuntimeOnly`.

Nếu quên Jupiter dependencies, Java test source có thể không compile. Nếu thiếu launcher/engine phù hợp với Gradle version, test runtime có thể báo lỗi engine/launcher hoặc không chạy test như mong muốn. Với Gradle 9+, nên khai JUnit Platform Launcher rõ ràng thay vì dựa vào leaked implementation details từ Gradle internals.

### 8.3. Vì sao không đưa test code vào production JAR?

`src/test/java` được compile bằng `compileTestJava` và đưa lên test runtime classpath. `jar` mặc định đóng gói **main outputs**, không chứa JUnit tests. Distribution của application dùng **runtime dependencies của main source set**, nên JUnit test libraries không trở thành third-party runtime libraries của người dùng ứng dụng.

### 8.4. Chạy toàn bộ tests

~~~bash
./gradlew test
~~~

Trong build output có thể hiện các task như:

~~~text
> Task :compileJava
> Task :processResources NO-SOURCE
> Task :classes
> Task :compileTestJava
> Task :test
BUILD SUCCESSFUL
~~~

Đây là **minh họa task sequence**, không cam kết trạng thái y hệt mọi lần. Khi không đổi inputs, tasks có thể `UP-TO-DATE` hoặc `FROM-CACHE`. Khi `testLogging.events` được bật, Gradle có thể in thêm các method events.

Kỳ vọng: **6 tests pass**, build không có failing assertions. Nếu đã có sample test code của `init` chưa loại, số tests có thể nhiều hơn; đây là lý do phải xác định sample files ở phần 4.

### 8.5. Chạy duy nhất một test method

~~~bash
./gradlew test --tests "org.example.greeting.GreeterTest.normalizesExtraSpaces"
~~~

Điều này giúp điều tra case riêng, không cần chạy toàn bộ class. Lọc cả test class:

~~~bash
./gradlew test --tests "org.example.greeting.GreeterTest"
~~~

Nếu Gradle không tìm thấy tests phù hợp, kiểm **fully qualified class name, method name, JUnit Platform config và source directory** trước khi xóa caches.

### 8.6. Đọc HTML và XML test reports

Các đường dẫn mặc định thường là:

~~~text
build/reports/tests/test/index.html
build/test-results/test/TEST-org.example.greeting.GreeterTest.xml
~~~

XML file name theo test class, trong trường hợp naming mặc định. HTML report để người học mở bằng browser; XML reports thường được CI đọc để hiển thị test results/trends.

Không xem `BUILD SUCCESSFUL` là toàn bộ việc kiểm thử. Khi một task được skip vì `UP-TO-DATE`, có thể xem last test report; khi cần chạy lại action vì mục đích điều tra, dùng `--rerun-tasks` có chủ đích.

### 8.7. Bài thử cố ý cho một test fail

Tạm đổi implementation từ:

~~~java
return "Xin chào, " + StringUtils.capitalize(name) + "!";
~~~

thành:

~~~java
return "Chào, " + StringUtils.capitalize(name) + "!";
~~~

Rồi chạy:

~~~bash
./gradlew test
~~~

Vì JUnit assertions vẫn kỳ vọng `Xin chào`, tests phải thất bại. Mục đích là chứng minh **tests thực sự kiểm behavior** và `build` sẽ fail nếu `check` fail. Sau thí nghiệm, **khôi phục** implementation đúng và chạy tests lại. Không commit đoạn lỗi hay dùng skip tests để giấu thất bại.

---

## 9. Chạy ứng dụng từ source bằng Gradle

### 9.1. Lệnh chạy mặc định

~~~bash
./gradlew -q run
~~~

Java application stdout:

~~~text
Xin chào, Gradle!
~~~

`-q` là `--quiet`: giảm Gradle console messages để người học thấy output của chương trình rõ hơn. Nó không làm Java process bỏ qua business logic hoặc tests.

### 9.2. Truyền một argument

~~~bash
./gradlew -q run --args="Linh"
~~~

Stdout:

~~~text
Xin chào, Linh!
~~~

### 9.3. Truyền nhiều từ

~~~bash
./gradlew -q run --args="mai anh"
~~~

Vì application code nối các `args` bằng spaces, stdout:

~~~text
Xin chào, Mai anh!
~~~

`--args` là option của Gradle Application plugin `run` task. Nội dung chuỗi được chuyển thành command line arguments cho Java application. Với dữ liệu có dấu ngoặc kép, dấu cách đặc biệt hoặc dấu `$`, rules của shell/Gradle args parsing có thể phức tạp; thử trên đúng terminal và dùng các chuỗi đơn giản trước.

### 9.4. Gradle `run` thực sự làm gì?

`run` là task loại `JavaExec`. Gradle bảo đảm main classes được compile qua task dependency, dựng **runtime classpath** gồm classes và các `implementation`/`runtimeOnly` dependencies, rồi khởi chạy `application.mainClass`.

Do đó chạy:

~~~bash
./gradlew run
~~~

khác việc chạy:

~~~bash
java org.example.greeting.Main
~~~

một cách trần trụi. Lệnh `java` không có `-cp` (và chưa có classpath được chuẩn bị) sẽ không biết tìm classes/library ở đâu.

### 9.5. Kiểm dependency được đưa vào runtime

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

Trong graph có `org.apache.commons:commons-lang3:3.17.0`. Muốn xem vì sao module này được chọn:

~~~bash
./gradlew dependencyInsight \
  --dependency commons-lang3 \
  --configuration runtimeClasspath
~~~

Nếu build failed ở compile do `StringUtils` không tìm thấy, kiểm `implementation`, repository và resolved classpath. Không giải quyết bằng cách thêm JAR tay vào IDE rồi hy vọng CI hoặc distribution cũng có nó.

---

## 10. Biên dịch, kiểm thử và build lifecycle

### 10.1. Những task quan trọng và mối liên hệ

| Task | Công việc |
| --- | --- |
| `compileJava` | Biên dịch `src/main/java` |
| `processResources` | Sao chép `src/main/resources` nếu có |
| `classes` | Chuẩn bị main classes/resources |
| `compileTestJava` | Biên dịch `src/test/java` |
| `test` | Chạy JUnit Jupiter |
| `check` | Tổng hợp verification tasks, bao gồm `test` mặc định |
| `jar` | Đóng gói main output thành application library JAR |
| `assemble` | Assemble artifacts; với Application/Distribution còn có archives |
| `build` | Tổng hợp `check` và `assemble` |
| `run` | Khởi chạy application qua JavaExec |
| `startScripts` | Sinh scripts Unix/Windows |
| `installDist` | Tạo application directory chạy được |
| `distZip` | Tạo ZIP của distribution |
| `distTar` | Tạo TAR của distribution |
| `assembleDist` | Tạo ZIP và TAR |

### 10.2. Chạy từng bước

~~~bash
./gradlew compileJava
./gradlew test
./gradlew jar
./gradlew assemble
./gradlew build
~~~

Bạn **không phải chạy đủ năm command này trong CI**. Chúng được trình bày riêng để học; `build` đã phụ thuộc `check` và `assemble`. Với Application plugin, `assemble` được nối tới distribution archives; `build` sẽ tạo các distribution archives cũng như chạy tests theo lifecycle.

Nếu muốn **chỉ xác minh mà không sinh ZIP/TAR**, dùng:

~~~bash
./gradlew check
~~~

Nếu chỉ muốn một archive, dùng `distZip` hoặc `distTar` riêng.

### 10.3. `build` khác `assemble` như thế nào?

- `assemble` tạo artifacts mà không mặc định chạy toàn bộ verification như `check`.
- `check` chạy quality/verification tasks liên quan (trong project này là JUnit tests).
- `build` phụ thuộc **cả `assemble` và `check`**.
- Có task execution order và caching do Gradle quyết định, nên output log thứ tự có thể khác giữa các invocations.
- Không dùng `assemble` rồi coi tests đã được thực hiện. Chạy `build` hoặc `check` để xác minh.

### 10.4. Phân biệt artifact JAR và distribution archive

Sau `jar`, file chính:

~~~text
build/libs/greeting-cli-1.0.0.jar
~~~

Đây là archive chứa compiled main classes/resources của project, nhưng **thông thường không tự chứa Apache Commons Lang JAR**. Khi chạy `java -jar` trực tiếp:

- Có thể gặp “no main manifest attribute” vì default Jar task chưa khai manifest Main-Class.
- Dù thêm manifest Main-Class, vẫn cần runtime classpath cho `commons-lang3` nếu không dùng fat JAR/manifest Class-Path hoặc packaging tương đương.
- Application plugin giải quyết chuyện phân phối bằng `lib/` và launch scripts.

Vì vậy sản phẩm được khuyên dùng trong bài là **distribution ZIP/TAR hoặc installDist directory**, không phải sao chép một JAR rồi chạy trần.

---

## 11. Tạo bản phân phối với Application plugin

Application plugin áp dụng Distribution plugin và tạo main distribution. Nội dung mặc định:

~~~text
greeting-cli/
├── bin/
│   ├── greeting-cli
│   └── greeting-cli.bat
├── lib/
│   ├── greeting-cli-1.0.0.jar
│   └── commons-lang3-3.17.0.jar
└── README.txt
~~~

Bố cục trên là **các thành phần chính của demo**; Gradle runtime dependency graph có thể có thêm files nếu bạn mở rộng dependencies. `README.txt` đến từ `src/dist` sẽ được tạo ở phần 12.

### 11.1. `startScripts`

~~~bash
./gradlew startScripts
~~~

Gradle tạo launcher scripts (đường dẫn mặc định `build/scripts`) dùng `application.mainClass` và application runtime classpath. Scripts của `installDist`/archives được tạo từ task này.

Trên Unix, `bin/greeting-cli` là script shell. Trên Windows, `bin/greeting-cli.bat` là batch script. Scripts biết tìm `lib` tương đối với distribution directory; người nhận không phải tự nhập `java -cp`.

### 11.2. `installDist`: bản cài không nén

~~~bash
./gradlew installDist
~~~

Thư mục kết quả:

~~~text
build/install/greeting-cli/
~~~

Chạy từ root project Linux/macOS:

~~~bash
./build/install/greeting-cli/bin/greeting-cli Linh
~~~

Expected stdout:

~~~text
Xin chào, Linh!
~~~

Nhiều từ:

~~~bash
./build/install/greeting-cli/bin/greeting-cli "mai anh"
~~~

Stdout:

~~~text
Xin chào, Mai anh!
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat installDist
.\build\install\greeting-cli\bin\greeting-cli.bat Linh
~~~

Stdout của Java:

~~~text
Xin chào, Linh!
~~~

**Lưu ý runtime:** scripts cần tìm được Java phù hợp trên máy chạy. `installDist` không cài JDK 17 cho bạn. Nếu Java 11 được dùng để chạy class file 17, có thể báo `UnsupportedClassVersionError`.

### 11.3. `distZip`: gói chia sẻ dễ đưa qua máy khác

~~~bash
./gradlew distZip
~~~

Vì `project.name = greeting-cli` và `version = 1.0.0`, ZIP mặc định dự kiến ở:

~~~text
build/distributions/greeting-cli-1.0.0.zip
~~~

Kiểm nội dung trên Linux/macOS nếu đã có `unzip`:

~~~bash
unzip -l build/distributions/greeting-cli-1.0.0.zip
~~~

Danh sách cần có:
- `greeting-cli-1.0.0/bin/greeting-cli`.
- `greeting-cli-1.0.0/bin/greeting-cli.bat`.
- `greeting-cli-1.0.0/lib/greeting-cli-1.0.0.jar`.
- `greeting-cli-1.0.0/lib/commons-lang3-3.17.0.jar`.
- `greeting-cli-1.0.0/README.txt` nếu đã thêm file ở `src/dist`.

Giải nén vào một thư mục thử nghiệm độc lập để kiểm hoạt động **không qua Gradle**:

~~~bash
mkdir -p extracted
unzip -q build/distributions/greeting-cli-1.0.0.zip -d extracted
./extracted/greeting-cli-1.0.0/bin/greeting-cli Linh
~~~

Stdout:

~~~text
Xin chào, Linh!
~~~

Nếu shell báo permission denied vì cơ chế giải nén/mount làm mất executable bit, kiểm permission và policy hệ điều hành; không coi source Java sai. Trên Windows, dùng `greeting-cli.bat` trong thư mục giải nén.

### 11.4. `distTar`: gói TAR

~~~bash
./gradlew distTar
~~~

Task tạo distribution TAR trong `build/distributions/`. **Phần mở rộng TAR có thể thay đổi theo compression configuration**, nên kiểm đường dẫn thực tế bằng `ls build/distributions` hoặc PowerShell `Get-ChildItem build\distributions` rồi dùng công cụ `tar` với options phù hợp (plain TAR khác TAR.GZ).

Ví dụ với plain TAR:

~~~bash
tar -tf build/distributions/greeting-cli-1.0.0.tar
~~~

Nếu bạn hoặc plugin cấu hình TAR compression tạo `.tar.gz`/`.tgz`, dùng đúng file extension và `tar -tzf`. Đừng khẳng định mọi Gradle build luôn ra duy nhất một extension mà không xem task configuration.

### 11.5. `assembleDist`: cả ZIP lẫn TAR

~~~bash
./gradlew assembleDist
~~~

Task lifecycle tổng hợp `distZip` và `distTar`. Phù hợp khi tổ chức muốn phát hành cả hai dạng. Nếu hệ thống chỉ nhận ZIP, dùng `distZip` để tránh tạo output không cần.

### 11.6. Vì sao phải kiểm **đầy đủ** distribution?

Một `BUILD SUCCESSFUL` có thể chỉ chứng minh Gradle tasks chạy xong; cần kiểm:
1. Archive có script Unix/Windows.
2. `lib` chứa application JAR và tất cả runtime dependencies.
3. Script chạy đúng `mainClass`.
4. Cài/giải nén ở thư mục khác vẫn chạy được.
5. Chạy với input mặc định và input có spaces.
6. Có tài liệu sử dụng/lưu ý Java runtime.
7. Tên file, version và nội dung phù hợp release requirements.

**Không chỉ copy `build/libs/greeting-cli-1.0.0.jar` rồi bỏ `lib/commons-lang3-3.17.0.jar`:** với code dùng `StringUtils`, một Java runtime thiếu dependency sẽ fail.

---

## 12. Thêm tài liệu hướng dẫn vào bản phân phối

Tạo file:

~~~text
src/dist/README.txt
~~~

Nội dung đầy đủ ví dụ:

~~~text
Greeting CLI 1.0.0

Yeu cau:
- Java runtime 17 hoac cao hon.

Su dung Linux/macOS:
  ./bin/greeting-cli Linh
  ./bin/greeting-cli "mai anh"

Su dung Windows:
  bin\greeting-cli.bat Linh

Vi du ket qua:
  Xin chao, Linh!

Ghi chu:
- Chay tu thu muc goc cua distribution.
- Thu muc lib chua application JAR va runtime dependencies.
- Khong can Gradle tren may nhan distribution.
~~~

File hướng dẫn chọn nội dung ASCII để dễ mở trên nhiều terminal; **Java program** vẫn in tiếng Việt có dấu đúng như các ví dụ. Khi `src/dist/README.txt` đã tồn tại, Application/Distribution plugin sẽ đưa nó vào main distribution theo behavior mặc định.

Chạy:

~~~bash
./gradlew installDist distZip
~~~

Kiểm:

~~~text
build/install/greeting-cli/README.txt
~~~

và dùng `unzip -l` để xác minh ZIP cũng chứa file này.

### 12.1. Nếu cần thêm config files

Ví dụ đặt `src/dist/config/application.properties`; file sẽ được đưa vào dưới `config/` của distribution (theo cấu hình mặc định). Nếu application cần đọc file ấy, **đường dẫn runtime phải được thiết kế rõ**; đừng giả định current working directory của mọi process luôn là distribution root.

Một ứng dụng chuyên nghiệp thường phân biệt:
- **Resources nội bộ**: đóng vào classpath trong JAR qua `src/main/resources`.
- **Cấu hình triển khai bên ngoài**: để trong `src/dist/config` và cho phép override.
- **Secrets**: inject từ runtime secrets/environment, **không** đưa vào ZIP/TAR.
- **Logs/data viết được**: đặt vào external writable directory thay vì sửa `lib`.

### 12.2. Tùy chỉnh JVM options đúng cách

Application plugin có `applicationDefaultJvmArgs`:

~~~groovy
application {
    mainClass = 'org.example.greeting.Main'
    applicationDefaultJvmArgs = ['-Dfile.encoding=UTF-8']
}
~~~

Đây là **thay thế có chủ đích** cho `application {}` trong `build.gradle` nếu môi trường học cần cố định encoding. Gradle dùng các default JVM args này cho `run` và generated start scripts. Với production cần kiểm tương thích Java/OS và dùng encoding giải pháp đúng tại I/O boundaries (ví dụ `StandardCharsets.UTF_8`) thay vì cho rằng một system property sửa được mọi cấu hình terminal.

---

## 13. Kiểm thủ công Java compilation/classpath ngoài Gradle

Để hiểu Gradle tự quản lý classpath như thế nào, hãy thử `javac` và `java`. Vì code `Greeter.java` import **Commons Lang**, không thể chỉ biên dịch bằng lệnh `javac Greeter.java Main.java` mà không có `-cp`; phải đưa thư viện vào classpath.

Đầu tiên để Gradle chuẩn bị runtime dependencies:

~~~bash
./gradlew installDist
~~~

### 13.1. Linux/macOS

~~~bash
mkdir -p manual-classes

javac -encoding UTF-8 \
  -cp build/install/greeting-cli/lib/commons-lang3-3.17.0.jar \
  -d manual-classes \
  src/main/java/org/example/greeting/Greeter.java \
  src/main/java/org/example/greeting/Main.java

java -cp "manual-classes:build/install/greeting-cli/lib/commons-lang3-3.17.0.jar" \
  org.example.greeting.Main Linh
~~~

Expected Java stdout:

~~~text
Xin chào, Linh!
~~~

`javac` compile hai source files vào `manual-classes/org/example/greeting/`; `java` tìm main classes và external JAR trên classpath. Separator giữa classpath entries trên Unix-like systems là dấu hai chấm `:`.

### 13.2. Windows PowerShell

~~~powershell
New-Item -ItemType Directory -Force manual-classes | Out-Null
javac -encoding UTF-8 -cp "build\install\greeting-cli\lib\commons-lang3-3.17.0.jar" -d manual-classes src\main\java\org\example\greeting\Greeter.java src\main\java\org\example\greeting\Main.java
java -cp "manual-classes;build\install\greeting-cli\lib\commons-lang3-3.17.0.jar" org.example.greeting.Main Linh
~~~

Windows dùng **dấu chấm phẩy `;`** để tách classpath entries. Stdout vẫn là:

~~~text
Xin chào, Linh!
~~~

Đây là **bài kiểm Java**; nó không thử Gradle `run`/`installDist` task graph hay Gradle Build Cache. Đường dẫn JAR ở đây dựa trên chính version dependency đã pin trong bài. Nếu thay version hoặc cấu hình archive, kiểm `build/install/greeting-cli/lib` rồi điều chỉnh.

### 13.3. Vì sao không nên lấy cách `java -cp` làm cơ chế distribution chính?

Nếu ứng dụng có 10 dependencies, tự dựng classpath bằng tay trở nên dễ lỗi. Application plugin đã sinh startup scripts biết tất cả runtime JARs và layout của distribution. Bản phân phối giúp người nhận dùng:

~~~bash
./bin/greeting-cli Linh
~~~

thay vì nhớ danh sách `lib/*.jar` và classpath separator cho OS. Đây là giá trị thật của `installDist`/`distZip`/`distTar`.

---

## 14. Kiểm tính lặp lại, caching và incremental correctness

### 14.1. Chạy lại không đổi code

~~~bash
./gradlew build --info
./gradlew build --info
~~~

Ở lần lặp, Gradle có thể báo `UP-TO-DATE` hoặc `FROM-CACHE` tùy task/cache state. Đó là tối ưu hợp lệ. Không cần chạy `clean` để chứng minh chương trình còn hoạt động.

### 14.2. Thay source có chủ đích

Trong `Greeter.java`, tạm đổi:

~~~java
return "Xin chào, " + StringUtils.capitalize(name) + "!";
~~~

thành:

~~~java
return "Chào, " + StringUtils.capitalize(name) + "!";
~~~

Chạy:

~~~bash
./gradlew test --info
~~~

Tests đang kỳ vọng `Xin chào` nên sẽ fail, chứng tỏ đổi Java source đã được compilation/test tasks nhận biết mà không phải xóa `build/`.

Khôi phục source đúng, rồi:

~~~bash
./gradlew test
./gradlew distZip
~~~

Kiểm script từ bản phân phối mới in output đúng.

### 14.3. Phân biệt các tối ưu

| Cơ chế | Làm gì? | Có xóa source/output không? |
| --- | --- | --- |
| Task up-to-date checks | Bỏ chạy task khi inputs/outputs không đổi | Không |
| Build Cache | Khôi phục task outputs nếu cache key khớp | Không |
| Configuration Cache | Tái dùng configured task graph | Không |
| Dependency cache | Tái dùng external JARs/metadata | Không |
| `--rerun-tasks` | Ép task action chạy lại để điều tra | Không xóa toàn `build/` trước |
| `--no-build-cache` | Tạm không đọc/ghi task outputs cache | Không |
| `clean` | Xóa build directory được clean task quản lý | Có, trong scope |
| `--refresh-dependencies` | Revalidate dependency resolution/metadata/artifacts | Không ép redownload toàn bộ |

**Không dùng `clean` hoặc xóa `~/.gradle` làm cách sửa lỗi compiler/test mặc định.** Nếu một task `UP-TO-DATE` nhưng output sai khi input đổi, phải sửa input/output tracking.

### 14.4. Xác minh distribution sau khi source thay

Một release-like verification có thể gồm:
1. `./gradlew test` pass.
2. `./gradlew build` pass.
3. `./gradlew installDist` tạo thư mục mới phù hợp.
4. Chạy script không qua Gradle, so stdout.
5. Giải nén ZIP vào thư mục khác, chạy script.
6. Kiểm dependency JAR có trong `lib`.
7. Kiểm archive name/version và file README.
8. Với môi trường trusted release, kiểm checksums/provenance.

Đây là cách phát hiện lỗi packaging mà một unit test thuần Java không thể đảm bảo.

---

## 15. Biết đọc build outputs và cách kiểm chứng artifacts

### 15.1. Khám phá tasks trong project

~~~bash
./gradlew tasks
./gradlew tasks --all
./gradlew help --task installDist
./gradlew help --task distZip
~~~

`tasks --all` có thể rất dài. Nên dùng `help --task ...` để hiểu một task cụ thể, thay vì đoán task names từ tutorial khác version.

### 15.2. Xem nội dung JAR

Trên JDK có tool `jar`:

~~~bash
jar tf build/libs/greeting-cli-1.0.0.jar
~~~

Trong main JAR có các class names như:

~~~text
org/example/greeting/Greeter.class
org/example/greeting/Main.class
~~~

Danh sách còn có manifest/metadata. **Không có** các JUnit test classes `GreeterTest.class` vì test source set không phải main source set.

### 15.3. Xem thư viện runtime trong installDist

~~~bash
ls build/install/greeting-cli/lib
~~~

Các tên chính:

~~~text
greeting-cli-1.0.0.jar
commons-lang3-3.17.0.jar
~~~

Đây là hai artifacts chủ yếu của demo. Với một dependency graph khác, danh sách có thể có nhiều JARs hoặc variant artifacts hơn. Từ đây thấy rõ **distribution khác JAR**.

### 15.4. Kiểm ZIP không phải chỉ kiểm file tồn tại

~~~bash
unzip -l build/distributions/greeting-cli-1.0.0.zip
~~~

Kiểm có `bin`, `lib` và `README.txt`. Nếu archive chỉ có JAR mà thiếu scripts, có thể người học đang xem nhầm `build/libs`, không phải `build/distributions`, hoặc đã dùng task `jar` thay vì `distZip`.

### 15.5. Tính checksum

Linux với `sha256sum`:

~~~bash
sha256sum build/distributions/greeting-cli-1.0.0.zip
~~~

macOS có thể dùng:

~~~bash
shasum -a 256 build/distributions/greeting-cli-1.0.0.zip
~~~

PowerShell:

~~~powershell
Get-FileHash build\distributions\greeting-cli-1.0.0.zip -Algorithm SHA256
~~~

Checksum giúp so sánh bytes của archive đã chuyển qua CI/file server, **không tự chứng minh nguồn đáng tin nếu attacker có thể thay cả artifact lẫn checksum**. Trong release pipeline cần sử dụng attestations/signatures/provenance phù hợp.

### 15.6. Bản phân phối có chứa JDK không?

Không. `installDist`/`distZip`/`distTar` của Application plugin đóng gói application classes/dependencies/start scripts, không tự nhúng Java runtime. Trên máy nhận, kiểm `java -version` và cấu hình `JAVA_HOME`/`PATH`. Nếu muốn native installer/JRE runtime image, cần các công cụ khác như `jlink`/`jpackage` và build logic riêng; **không gán khả năng đó cho `distZip` mặc định**.

---

## 16. Xử lý arguments, encoding và cấu hình runtime

### 16.1. Thử các trường hợp dòng lệnh

~~~bash
./gradlew -q run
./gradlew -q run --args="Linh"
./gradlew -q run --args="linh"
./gradlew -q run --args="mai anh"
~~~

Kết quả của Java:

~~~text
Xin chào, Gradle!
Xin chào, Linh!
Xin chào, Linh!
Xin chào, Mai anh!
~~~

**Đây là bốn dòng từ bốn invocation độc lập được ghép để minh họa**, không phải stdout của một command duy nhất.

Trong distribution:

~~~bash
./build/install/greeting-cli/bin/greeting-cli
./build/install/greeting-cli/bin/greeting-cli Linh
./build/install/greeting-cli/bin/greeting-cli "mai anh"
~~~

Không dùng `--args` trên **start script**: `--args` là option của Gradle `run`, còn script là command-line launcher nên nhận arguments trực tiếp.

### 16.2. Mối quan hệ encoding

- Java source chứa dấu tiếng Việt → cấu hình `options.encoding = 'UTF-8'` cho JavaCompile.
- Code in chuỗi Unicode qua `System.out`; cách terminal hiển thị tùy console encoding/platform.
- `System.out.println` thêm newline; ký tự newline trên Windows và POSIX có thể khác khi redirect ra file.
- Khi so output text trong automated tests, ưu tiên kiểm string trả về từ `Greeter` thay vì dựa vào environment console settings.
- Một artifact JAR có bytecode đúng nhưng terminal hiển thị sai dấu không nhất thiết có bug trong `Greeter`.

### 16.3. Nếu muốn cấu hình chính sách logging/runtime

Bạn có thể bổ sung Gradle Application plugin configuration như:

~~~groovy
application {
    mainClass = 'org.example.greeting.Main'
    applicationDefaultJvmArgs = ['-Dfile.encoding=UTF-8']
}
~~~

Đây là **đoạn thay thế block application hiện tại**, không thêm `application` block mâu thuẫn. Với ứng dụng lớn, log level/endpoint nên được cấu hình runtime thông qua arguments/config/env, không hard-code credentials vào Gradle build scripts.

### 16.4. Phân biệt app arguments và Gradle arguments

~~~bash
./gradlew -q run --args="Linh"
~~~

`-q` là Gradle logging flag; `run` là task; `--args` truyền text cho Java application.

~~~bash
./build/install/greeting-cli/bin/greeting-cli Linh
~~~

đây là script của **ứng dụng**, nên chỉ cần tên người nhận. Không phải shell plugin hoặc Gradle CLI nữa.

---

## 17. CI pipeline và release có trách nhiệm

### 17.1. Pipeline tối thiểu về logic

Một CI runner trên clean checkout đã verify Wrapper/JDK có thể thực hiện:

~~~bash
./gradlew --version
./gradlew test
./gradlew build
./gradlew installDist
./build/install/greeting-cli/bin/greeting-cli Linh
~~~

Ở Windows, dùng `gradlew.bat` và `greeting-cli.bat`. Lệnh `build` đã bao gồm `test` qua `check`, nên chạy `test` riêng trong pipeline có thể chỉ vì muốn có stage/report rõ, không phải requirement để build đúng.

### 17.2. CI cần archive artifacts nào?

Với single-project layout này, cần kiểm/thu:

~~~text
build/distributions/greeting-cli-1.0.0.zip
build/distributions/greeting-cli-1.0.0.tar
build/reports/tests/test/index.html
build/test-results/test/
~~~

TAR extension cần đọc từ thực tế theo compression configuration. Nếu chỉ publish ZIP, dùng ZIP. Không đưa `build/.gradle` hoặc JUnit test runtime libraries vào production package thủ công.

### 17.3. Vấn đề phát hành khác một developer build

- Developer builds có thể dùng Configuration Cache, Build Cache và incremental compilation để nhanh.
- Trusted CI cần xem dependencies/Wrapper/plugins được pin/verify, tests pass, source review và artifacts đúng.
- Release artifact generation ở môi trường **fresh, isolated, trusted** theo supply-chain policy, thay vì dựa vào những cached binaries không rõ nguồn.
- `clean` trong workspace cũ **không tự chứng minh** trusted clean build vì tasks vẫn có thể `FROM-CACHE` nếu Build Cache bật.
- Khi yêu cầu rebuild compiler thật, dùng fresh trusted runner và `--no-build-cache` theo policy; không bỏ qua tests để release “cho kịp”.
- `distributionSha256Sum` và verify Wrapper JAR để giảm rủi ro toolchain distribution bị thay đổi.
- Không commit repository credentials/signing keys vào `build.gradle` hoặc `gradle.properties` trong VCS.

### 17.4. Version không phải ký tự trang trí

~~~groovy
version = '1.0.0'
~~~

ảnh hưởng artifact names như `greeting-cli-1.0.0.jar`/`greeting-cli-1.0.0.zip`. Khi release, nhóm cần chọn version theo quy ước, gắn git tag/changelog và bảo đảm artifacts từ đúng source commit. Nếu quên `version`, Gradle default có thể tạo filename chứa `unspecified`, gây khó xác định bản phát hành.

---

## 18. Những sai lầm đặc trưng của bài “init → distribution”

| Lỗi hoặc hiểu nhầm | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| `gradle: command not found` lúc init | Chưa có Gradle bootstrap distribution | Cài Gradle tin cậy hoặc dùng IDE bootstrap hợp lệ |
| `./gradlew: No such file` trước init | Wrapper chưa được tạo | Chạy `gradle init` trước |
| `gradlew permission denied` Unix | Không có executable bit | Kiểm quyền cho script generated trusted; không thay Wrapper JAR |
| Init ra `app/build.gradle` thay vì root | Split-project template | Dùng `--no-split-project` hoặc đổi lệnh sang `:app:*` nhất quán |
| `Unknown command-line option '--no-split-project'` | Gradle init version cũ | Kiểm `gradle --version` và versioned docs |
| Dùng `build.gradle.kts` nhưng copy Groovy DSL | Chọn nhầm DSL | Init `--dsl groovy` hoặc viết lại đúng Kotlin DSL |
| `UnknownPluginException` | Plugin declaration/repository/Gradle version | Kiểm plugin ID, Wrapper/metadata |
| `Cannot resolve commons-lang3` | Repository/network/GAV | Kiểm `mavenCentral()`, internet, TLS/proxy, dependency graph |
| `cannot find symbol StringUtils` | Dependency không ở compileClasspath | Khai `implementation`, kiểm import/case |
| `Could not find method implementation` | Thiếu Java/Application plugin | Kiểm `plugins { id 'application' }` |
| `Main class ... not found` | Package/class/mainClass mismatch | Kiểm fully qualified mainClass và source |
| `NoClassDefFoundError: StringUtils` | Chạy JAR thô thiếu runtime library | Dùng distribution start script hoặc đúng classpath |
| `no main manifest attribute` từ `java -jar` | Plain Jar mặc định thiếu main manifest | Dùng Application distribution; đừng coi đây là fat JAR |
| `UnsupportedClassVersionError` | Runtime Java thấp hơn Java 17 | Cung cấp Java 17+ runtime tương thích |
| `No matching toolchains found` | JDK 17 không cài/detected | Cài toolchain hoặc cấu hình resolver theo docs |
| `Test class not found` | Sai source path/package/filter | Kiểm `src/test/java` và `--tests` |
| `No tests found` | Quên Jupiter engine/useJUnitPlatform hoặc source | Khai dependencies, `useJUnitPlatform()` |
| `Test runtime launcher missing` | Thiếu JUnit Platform Launcher | Khai `testRuntimeOnly` phù hợp |
| `test` FAIL khi cố ý đổi greeting | Assertion khác business logic | Khôi phục source hoặc cập nhật yêu cầu/test hợp lệ |
| ZIP không có Commons Lang | Build dependency hoặc archive customization sai | Kiểm `implementation` và `distZip` |
| Chỉ tìm thấy `jar` không có scripts | Chạy sai task hoặc thiếu Application plugin | `installDist`/`distZip` và `application.mainClass` |
| ZIP có scripts nhưng không chạy | Java runtime/permissions/classpath | Kiểm JDK, launcher, distribution layout |
| App chạy bằng `run` nhưng bản cài fail | Runtime dependency không đóng gói, relative path bug | Chạy `installDist` trên môi trường mới |
| `--args` trên shell script không hoạt động | Nhầm Gradle `run` option | Đưa args trực tiếp vào start script |
| Tên JAR là `unspecified` | Không đặt project `version` | Pin `version = '1.0.0'` |
| Archive file name khác hướng dẫn | Project name/version hoặc compression khác | Xem `settings.gradle`, `build.gradle`, output thực tế |
| `clean` xong mới build được | Task input/output bugs hoặc stale artifact | Điều tra incremental contract, không clean mọi lần |
| Offline fail tải JUnit | Dependencies chưa có cache | Online resolve trước; không xóa `~/.gradle` |
| IDE đỏ nhưng Gradle CLI pass | Gradle JVM/IDE SDK/model sync khác | Dùng Wrapper, sync Gradle model, kiểm JDK |
| Windows script báo file lock | IDE/process/antivirus giữ JAR | Xác định process, không xóa toàn caches |
| ZIP không chứa README | Chưa tạo `src/dist/README.txt` hoặc custom distribution sai | Tạo đúng source path, chạy distZip lại |

### 18.1. Bộ lệnh tìm lỗi từ ít tác động

~~~bash
./gradlew --version
./gradlew tasks --all
./gradlew help --task run
./gradlew dependencies --configuration runtimeClasspath
./gradlew test --stacktrace --info
./gradlew distZip --info
~~~

Nếu package/service không có trên classpath, sửa `implementation`/repositories. Nếu artifact bị lỗi nhưng source đúng, xem `--info` cache/up-to-date logic. Không xóa `~/.gradle` hoặc chạy `--refresh-dependencies` ở mọi invocation.

### 18.2. Lỗi JUnit: đừng nhầm unit test report với console

Khi `test` fail:
1. Mở `build/reports/tests/test/index.html`.
2. Tìm method, expected vs actual.
3. Xem Java stacktrace.
4. Xác định do source behavior, fixture hay dependency/test engine.
5. Sửa đúng code/test theo yêu cầu.
6. Chạy lại method bằng `--tests` trước, rồi chạy toàn `test` và `build`.
7. Không dùng `-x test` cho release để che lỗi.

### 18.3. Lỗi distribution: kiểm từ trong ra ngoài

Khi ZIP có nhưng chạy không được:

1. `jar tf build/libs/greeting-cli-1.0.0.jar`: `Main.class`/`Greeter.class` có?
2. `unzip -l build/distributions/greeting-cli-1.0.0.zip`: có `bin/` và `lib/`?
3. Có `commons-lang3-3.17.0.jar` không?
4. `build/install/greeting-cli/bin/greeting-cli Linh` có chạy trên máy build không?
5. Chạy từ thư mục giải nén mới có khác?
6. Runtime Java version nào đang được start script chọn?
7. Có code phụ thuộc current working directory mà chưa khai configuration?
8. Rebuild có cùng code/inputs đúng không?
9. Nếu cần cross-platform, thử cả Unix và Windows scripts trên OS tương ứng.

---

## 19. Bài tập tự luyện có đáp án

### Bài 1 — Tại sao cần Gradle cài sẵn ở bước `init`?

**Đáp án:** Thư mục rỗng chưa có Gradle Wrapper. Gradle bootstrap chạy `init` tạo build files và Wrapper. Sau đó dùng `./gradlew` nhất quán.

### Bài 2 — Vì sao chọn `--type java-application` thay vì `java-library`?

**Đáp án:** Ứng dụng cần `mainClass`, `run` và distribution start scripts; Application plugin hỗ trợ chúng. Java Library plugin hướng tới module library.

### Bài 3 — Tại sao phải có `--no-split-project`?

**Đáp án:** Bài dùng single-project root `build.gradle` và task paths `:run`/`:test`. Nếu init sinh subproject `app`, cấu trúc/tên task thay đổi, dễ chạy nhầm.

### Bài 4 — `mainClass` trong demo phải bằng gì?

**Đáp án:** `org.example.greeting.Main` vì Java source khai `package org.example.greeting` và public main method nằm trong class `Main`.

### Bài 5 — `implementation` khác `testImplementation` thế nào?

**Đáp án:** `implementation` của Commons Lang phục vụ main compile/runtime và distribution. JUnit ở `testImplementation` phục vụ tests, không phải production runtime dependencies.

### Bài 6 — Vì sao khai `testRuntimeOnly`?

**Đáp án:** JUnit Platform Launcher cần khi Gradle chạy JUnit Jupiter tests; từ Gradle 9 không nên dựa vào các internal test dependencies trước kia được rò từ Gradle.

### Bài 7 — Chạy `./gradlew -q run --args="linh"` in gì?

**Đáp án:**

~~~text
Xin chào, Linh!
~~~

`StringUtils.capitalize` viết hoa chữ đầu.

### Bài 8 — Vì sao “mai anh” không thành “Mai Anh”?

**Đáp án:** `StringUtils.capitalize` chỉ viết hoa ký tự đầu của **toàn chuỗi**. Vì vậy kết quả là `Mai anh`, không phải title case từng từ.

### Bài 9 — Khi chạy `./gradlew test`, bao nhiêu test methods của file bài này được chạy?

**Đáp án:** 6, nếu đã loại sample tests do `init` sinh ra và JUnit Platform được cấu hình đúng.

### Bài 10 — `assemble` và `build` khác gì?

**Đáp án:** `assemble` tạo artifacts; `build` bao gồm `assemble` và `check`, do đó chạy unit tests theo lifecycle.

### Bài 11 — `jar` có đủ để đưa chương trình cho người dùng cuối không?

**Đáp án:** Không nhất thiết. JAR mặc định không tự kèm Commons Lang và có thể không có Main-Class manifest. Distribution chứa start scripts và runtime dependencies.

### Bài 12 — `installDist` cho ra gì?

**Đáp án:** Thư mục `build/install/greeting-cli` với `bin/`, `lib/` và tài liệu trong `src/dist` nếu có; có thể chạy mà không cần Gradle trên máy nhận.

### Bài 13 — `distZip` khác `distTar`?

**Đáp án:** Cùng đóng gói main distribution, khác định dạng archive ZIP/TAR. `assembleDist` tạo cả hai.

### Bài 14 — Người nhận ZIP có cần Gradle không?

**Đáp án:** Không; dùng start script. Họ vẫn cần Java runtime phù hợp (demo Java 17+), trừ khi tổ chức phát triển một dạng runtime image/installer riêng.

### Bài 15 — Vì sao `java -jar build/libs/...jar` có thể fail?

**Đáp án:** Plain Gradle JAR không mặc định là executable fat JAR; thiếu manifest Main-Class hoặc runtime dependencies. Dùng application distribution.

### Bài 16 — Đổi source rồi test fail có nên chạy clean?

**Đáp án:** Không mặc định. Test fail vì expected/actual behavior khác nhau, không phải artifact stale. Sửa code hoặc test theo yêu cầu.

### Bài 17 — File `src/dist/README.txt` đi đâu?

**Đáp án:** Vào root của application distribution khi chạy `installDist`/`distZip` theo mặc định Application plugin.

### Bài 18 — Chạy `gradle run` hay `./gradlew run` trong team?

**Đáp án:** Ưu tiên `./gradlew run` để mọi người dùng Gradle distribution được pin trong repository.

### Bài 19 — Muốn chạy một JUnit method thì sao?

**Đáp án:** Dùng `./gradlew test --tests "org.example.greeting.GreeterTest.greetsKnownName"`.

### Bài 20 — Khi ZIP có `lib` nhưng CLI fail Java version?

**Đáp án:** Kiểm Java runtime trên máy nhận. Application distribution không tự đóng gói JDK; compiled Java 17 class files không chạy trên Java 11.

### Bài 21 — `--no-build-cache` có cần chạy mọi lần không?

**Đáp án:** Không. Gradle Build Cache là tối ưu hợp lệ cho developer builds; tắt khi muốn kiểm correctness/release policy có mục đích.

### Bài 22 — Vì sao phải kiểm archive sau build thành công?

**Đáp án:** Build success không thay kiểm đầy đủ scripts, JARs, dependencies, README và smoke test từ thư mục giải nén. Packaging có thể bị custom config làm sai dù unit tests pass.

### Bài 23 — `gradle init --overwrite` có nên dùng vào repo thật?

**Đáp án:** Không mặc định. Dùng thư mục mới với `--into` và backup dữ liệu; chỉ overwrite khi thật sự muốn thay files đã kiểm.

### Bài 24 — Manual `javac` vì sao cần commons-lang3 JAR?

**Đáp án:** `Greeter.java` import `StringUtils` ngoài JDK. Gradle `implementation` tự thêm compile/runtime classpath, còn manual `javac` cần `-cp` explicit.

### Bài 25 — Khi nào nên phát hành?

**Đáp án:** Khi tests/build pass, distribution từ trusted source/toolchain chạy smoke test, artifact name/version đúng, dependencies/licensing/security review hợp lệ, checksum/provenance và release policy đã đạt.

---

## 20. Checklist hoàn thành bài thực hành

1. Đã chọn một thư mục mới, không overwrite files quan trọng?
2. Đã kiểm JDK 17 và Gradle bootstrap distribution?
3. Đã dùng `gradle init --type java-application`?
4. Đã chọn `--dsl groovy`?
5. Đã chọn `--test-framework junit-jupiter`?
6. Đã chọn `--no-split-project` phù hợp phiên bản?
7. Đã chọn package `org.example.greeting` và project name `greeting-cli`?
8. Đã chỉ định `--java-version 17`?
9. Đã có `gradlew`, `gradlew.bat`, Wrapper JAR và properties?
10. Đã chạy `./gradlew --version` thành công?
11. Đã thay sample build/source files một cách có kiểm soát?
12. `settings.gradle` có `rootProject.name = 'greeting-cli'`?
13. `build.gradle` áp `application` plugin?
14. Đã pin `group` và `version`?
15. Đã có `mavenCentral()` và đúng `implementation` Commons Lang?
16. Java toolchain là 17 và Java source encoding UTF-8?
17. `application.mainClass` trùng fully qualified main class?
18. `Greeter.java` và `Main.java` đúng package/path?
19. `GreeterTest.java` có 6 JUnit Jupiter tests?
20. JUnit dependencies và `useJUnitPlatform()` khai đúng?
21. `./gradlew test` pass?
22. Đã mở HTML test report hoặc XML nếu cần?
23. `./gradlew -q run` in đúng `Xin chào, Gradle!`?
24. `run --args="Linh"` in đúng `Xin chào, Linh!`?
25. Input `mai anh` cho ra `Xin chào, Mai anh!`?
26. `./gradlew build` pass, tạo JAR và distribution artifacts?
27. Đã phân biệt `check`, `assemble` và `build`?
28. Đã xác minh JAR có `Main.class`/`Greeter.class`?
29. Đã tạo `src/dist/README.txt`?
30. `installDist` cho đúng `bin/`/`lib/`?
31. `lib` chứa `commons-lang3-3.17.0.jar`?
32. Start script Unix/Windows chạy được trên OS phù hợp?
33. `distZip` và `distTar` tạo archives trong `build/distributions`?
34. Đã giải nén ZIP sang thư mục mới và smoke test?
35. Có kiểm Java runtime 17+ trên máy nhận?
36. Có tránh nhầm JAR thường với fat JAR?
37. Có thực hành manual `javac`/`java -cp` với external library?
38. Khi đổi source, Gradle tự nhận biết thay đổi mà không cần clean?
39. Có xác nhận Wrapper/checksums và dependency trust khi đưa vào CI?
40. Nếu chuẩn bị phát hành, có trusted clean environment, checksums và version/release policy?

## 21. Tài liệu chính thức và cách tra tiếp

Các tài liệu được đối chiếu theo **Gradle 9.9.0**. Với một project đang dùng Wrapper version khác, thay `current` bằng version cụ thể để tránh áp nhầm options/API.

- [Gradle Build Init Plugin — 9.9.0](https://docs.gradle.org/9.9.0/userguide/build_init_plugin.html): `init`, `java-application`, `--dsl`, `--test-framework`, `--no-split-project`, `--java-version`, `--into`.
- [Gradle Application Plugin](https://docs.gradle.org/9.9.0/userguide/application_plugin.html): `application.mainClass`, `run`, `--args`, `startScripts`, `installDist`, `distZip` và `distTar`.
- [Gradle Distribution Plugin](https://docs.gradle.org/9.9.0/userguide/distribution_plugin.html): archives, `src/dist`, `assembleDist` và output directories.
- [Gradle Java Plugin](https://docs.gradle.org/9.9.0/userguide/java_plugin.html): source sets, JavaCompile, `jar`, `assemble`, `check` và `build`.
- [Gradle Java Testing](https://docs.gradle.org/9.9.0/userguide/java_testing.html): JUnit Jupiter/Platform, test filters, HTML/XML reports và test runtime.
- [Gradle Java Toolchains](https://docs.gradle.org/9.9.0/userguide/toolchains.html): Java 17 toolchain, Gradle JVM và compiler runtime.
- [Gradle Gradle Wrapper](https://docs.gradle.org/9.9.0/userguide/gradle_wrapper.html): `gradlew`, version pinning và `distributionSha256Sum`.
- [Gradle Command-Line Interface](https://docs.gradle.org/9.9.0/userguide/command_line_interface.html): `--info`, `--stacktrace`, `--tests` và task names.
- [Gradle Dependency Management Basics](https://docs.gradle.org/9.9.0/userguide/declaring_dependencies_basics.html): `implementation`, `testImplementation`, `testRuntimeOnly`.
- [Gradle Build Cache](https://docs.gradle.org/9.9.0/userguide/build_cache.html): up-to-date/Build Cache khác test correctness.
- [Gradle Security Best Practices](https://docs.gradle.org/9.9.0/userguide/best_practices_security.html): Wrapper integrity, dependency trust và build artifacts.
- [Gradle Compatibility Matrix](https://docs.gradle.org/9.9.0/userguide/compatibility.html): Gradle/JVM/toolchain supported versions.

**Tổng kết:** một ứng dụng Java sẵn sàng phân phối cần nhiều hơn `Main.java`. `gradle init` chuẩn hóa điểm bắt đầu; Wrapper pin build tool; Application plugin chạy chương trình và đóng gói; JUnit Jupiter bảo vệ behavior; `build`/`check` xác minh; `installDist`/`distZip`/`distTar` đưa chương trình cùng dependencies và launch scripts sang máy khác. Khi kiểm được **bản đã giải nén chạy mà không cần Gradle**, bạn đã hoàn thành trọn quy trình **init → code → compile → test → run → distribute**.
