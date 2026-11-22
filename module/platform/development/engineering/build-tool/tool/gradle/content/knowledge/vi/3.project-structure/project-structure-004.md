# Bố cục `src/main`, `src/test`, `resources` và thư mục `build` trong Gradle

## 1. Mô hình tư duy: tách đầu vào, kiểm thử và sản phẩm đầu ra

Một dự án Java thường chứa **mã dùng khi ứng dụng chạy**, **mã/dữ liệu để kiểm thử**, và **kết quả sinh ra trong quá trình build**. Gradle có quy ước thư mục để nhận diện ba nhóm này. Khi dùng Java plugin (hoặc plugin `application`, vốn áp dụng Java plugin), Gradle có thể tự thiết lập task biên dịch, xử lý tài nguyên, chạy test và đóng gói.

Ba nhóm cần phân biệt:

- `src/main` chứa nguồn chính: mã Java của ứng dụng/thư viện và các tài nguyên đi cùng ứng dụng.
- `src/test` chứa nguồn kiểm thử: mã test và dữ liệu chỉ cần cho các bài test.
- `build` chứa output do Gradle tạo: bytecode, tài nguyên đã xử lý, JAR, kết quả kiểm thử, báo cáo và dữ liệu tạm.

Mối quan hệ cơ bản:

```text
src/main/java       --> compileJava         --> build/classes/java/main
src/main/resources  --> processResources    --> build/resources/main
                                                   |
                                                main output
                                                   |
                                            jar / run / test

src/test/java       --> compileTestJava     --> build/classes/java/test
src/test/resources  --> processTestResources--> build/resources/test
                                                   |
                                                test output
                                                   |
                                         test (dùng thêm main output)
                                                   |
                                build/test-results và build/reports
```

Các đường dẫn đầu ra thể hiện **mặc định phổ biến** của Java plugin; chúng có thể thay đổi theo plugin, phiên bản Gradle hoặc cấu hình. Ý chính là: file thuộc **source set** nào sẽ được task tương ứng xử lý, rồi sản phẩm của task được dùng cho những mục tiêu build thích hợp.

## 2. Cây thư mục điển hình

Ví dụ một project Java có tên `layout-demo`:

```text
layout-demo/
├── settings.gradle
├── build.gradle
├── gradle.properties              (tùy chọn)
├── gradlew                        (Gradle Wrapper trên Unix)
├── gradlew.bat                    (Gradle Wrapper trên Windows)
├── gradle/
│   └── wrapper/
│       ├── gradle-wrapper.jar
│       └── gradle-wrapper.properties
├── src/
│   ├── main/
│   │   ├── java/
│   │   │   └── demo/
│   │   │       └── App.java
│   │   └── resources/
│   │       └── message.txt
│   └── test/
│       ├── java/
│       │   └── demo/
│       │       └── AppTest.java
│       └── resources/
│           └── test-only.txt
├── .gitignore
└── build/                         (Gradle tạo khi chạy task)
```

Đừng nhầm những thành phần ở thư mục gốc với source code:

| Vị trí | Vai trò |
| --- | --- |
| `settings.gradle` | Đặt tên root project, khai báo các project con nếu có |
| `build.gradle` | Khai báo plugin, dependency, task, các quy tắc build |
| `gradle.properties` | Chứa thuộc tính cấu hình Gradle phù hợp với phạm vi file |
| `gradlew`, `gradlew.bat`, `gradle/wrapper/` | Gradle Wrapper, giúp thành viên dùng phiên bản Gradle được dự án chỉ định |
| `src/main/java` | Java source của phần chính |
| `src/main/resources` | Tài nguyên dùng khi chạy phần chính |
| `src/test/java` | Java source của kiểm thử |
| `src/test/resources` | Dữ liệu/tài nguyên dùng trong kiểm thử |
| `build/` | Sản phẩm được build, thường không quản lý bằng Git |
| `.gradle/` | Trạng thái/cache Gradle ở mức project; khác `gradle/wrapper/` |

Thư mục `gradle/wrapper` chứa Wrapper nên thường được đưa vào Git, bao gồm Wrapper JAR lấy từ nguồn tin cậy. Ngược lại, `.gradle` và `build` do Gradle tạo thường nằm trong `.gitignore`. Cache tại `~/.gradle` thuộc môi trường người dùng, cũng không phải source của project.

Quy tắc dễ nhớ: **`src` là dữ liệu đầu vào do lập trình viên duy trì; `build` là nơi Gradle ghi kết quả có thể tạo lại**. Đừng lưu file tự viết duy nhất bên trong `build` vì task `clean` có thể xóa nó.

## 3. Source set là gì, và tại sao tên `main`/`test` quan trọng?

Một **source set** (tập nguồn) mô tả một nhóm mã nguồn, tài nguyên, output và classpath. Java plugin tạo sẵn hai source set chuẩn là `main` và `test`.

`main` chứa lớp của ứng dụng hoặc thư viện được phát hành. `test` chứa các lớp kiểm thử để xác minh `main`. Classpath dùng khi chạy test thông thường bao gồm **output của test**, **output của main** cùng dependency kiểm thử. Vì vậy, test có thể gọi lớp chính, nhưng mã sản phẩm không được mặc định phụ thuộc ngược vào mã test.

Bảng quy ước:

| Source set | Nguồn vào | Task liên quan | Output thường gặp |
| --- | --- | --- | --- |
| `main` / Java | `src/main/java/**/*.java` | `compileJava` | `build/classes/java/main/` |
| `main` / tài nguyên | `src/main/resources/**` | `processResources` | `build/resources/main/` |
| `test` / Java | `src/test/java/**/*.java` | `compileTestJava` | `build/classes/java/test/` |
| `test` / tài nguyên | `src/test/resources/**` | `processTestResources` | `build/resources/test/` |

Task `classes` chuẩn bị các output của `main`. Task `testClasses` chuẩn bị các output của `test`. Task `test` chạy kiểm thử trên classpath phù hợp; task `jar` của Java plugin thường đóng gói output của `main`.

Đây là **các quy ước do plugin thiết lập**, không phải Gradle tự phát hiện bất kỳ thư mục tên `src` nào. Nếu không áp dụng plugin ngôn ngữ phù hợp, Gradle không mặc nhiên tạo các task như `compileJava`. Chỉ tạo thư mục `src/integrationTest/java` cũng chưa đủ để có một source set/task integration test; cần cấu hình bổ sung hoặc plugin hỗ trợ.

## 4. `src/main/java`: mã ứng dụng và quy ước package

Đặt lớp `App` vào file `src/main/java/demo/App.java`:

```java
package demo;

public final class App {
    private App() {
    }

    public static void main(String[] args) {
        System.out.println("Hello Gradle");
    }
}
```

`src/main/java` là **source root**. Phần `demo/App.java` tương ứng với khai báo `package demo;` theo quy ước. Khi task `compileJava` hoàn thành, file được biên dịch thường ở:

```text
build/classes/java/main/demo/App.class
```

`App.class` chứa bytecode Java, không phải bản sao của `App.java`. Mã Java được viết trong `src/main/java`, còn kết quả biên dịch xuất hiện trong `build/classes`.

Không đặt file `.java` dưới `src/main/resources` với hy vọng Java plugin sẽ tự biên dịch. Mặc định, thư mục `resources` được xử lý như tài nguyên. Nếu có nhu cầu dùng một source root khác, hãy cấu hình `sourceSets` như mục 10.

## 5. `src/main/resources`: file dữ liệu nằm trên classpath

Tài nguyên có thể là file văn bản, JSON, cấu hình `.properties`, bản mẫu thông báo hoặc dữ liệu tĩnh. Ví dụ:

```text
src/main/resources/
├── message.txt
└── config/
    └── app.properties
```

Task `processResources` thông thường sao chép file, giữ đường dẫn tương đối:

```text
build/resources/main/
├── message.txt
└── config/
    └── app.properties
```

Khi đóng gói JAR chính theo quy ước, các resource của `main` được đặt trong JAR, chẳng hạn `message.txt` ở gốc và `config/app.properties` dưới thư mục `config`.

Điều quan trọng là **đọc resource thông qua classpath**, vì ứng dụng đóng gói thành JAR không còn đảm bảo có thư mục `src/main/resources` ở nơi đang chạy. Ví dụ đoạn mã dưới đây được đặt bên trong một phương thức Java có xử lý ngoại lệ `IOException`:

```java
try (java.io.InputStream input =
        App.class.getResourceAsStream("/message.txt")) {
    if (input == null) {
        throw new IllegalStateException("Missing resource");
    }
    String message = new String(
            input.readAllBytes(),
            java.nio.charset.StandardCharsets.UTF_8);
    System.out.println(message.strip());
}
```

Dấu `/` trong `getResourceAsStream("/message.txt")` biểu thị gốc classpath. Đó **không** phải ký hiệu gốc hệ thống file. Với file `src/main/resources/config/app.properties`, tên resource là `"/config/app.properties"`. Đoạn mã trên mang tính minh họa; ví dụ đầy đủ có thể biên dịch và chạy nằm ở mục 8.

So sánh:

- `Class.getResourceAsStream(...)` lấy tài nguyên từ classpath, kể cả khi tài nguyên ở bên trong JAR.
- `Path.of("src/main/resources/message.txt")` truy cập đường dẫn hệ thống file tương đối với thư mục làm việc. Nó có thể chạy trong môi trường phát triển nhưng thất bại sau đóng gói.

Gradle **không tự thay tất cả biến trong file resource**. Khi muốn lọc hay tạo file cấu hình theo biến của build, cần cấu hình task `processResources`. Đặc biệt, không nhúng mật khẩu và token thật vào `src/main/resources`: nội dung đó có thể bị đóng gói nguyên vẹn trong sản phẩm.

## 6. `src/test/java` và `src/test/resources`: thế giới của kiểm thử

`src/test/java` chứa lớp test, ví dụ `demo/AppTest.java`. `src/test/resources` chứa fixture (dữ liệu mẫu), file cấu hình test, JSON kỳ vọng hoặc dữ liệu kiểm thử khác.

Với JUnit 5, test nằm dưới `src/test/java` có thể dùng lớp chính và tài nguyên test. Dependency JUnit thường được khai báo bằng `testImplementation`, nghĩa là cần cho việc biên dịch/chạy test nhưng không nhất thiết cần trong sản phẩm chính.

Ví dụ một file `src/test/resources/test-only.txt` được đọc trong kiểm thử bằng `AppTest.class.getResourceAsStream("/test-only.txt")`. File này được xử lý bởi `processTestResources` rồi có mặt trên classpath kiểm thử. **JAR sản phẩm do task `jar` thông thường không đóng gói test class hoặc test resource.**

Điều đó mang lại hai lợi ích: người dùng cuối không nhận mã test không cần thiết, và dự án có thể dùng dữ liệu kiểm thử độc lập với dữ liệu ứng dụng. Tuy nhiên, test vẫn có thể truy cập `main` output nhờ classpath được cấu hình cho `test`.

Nếu một test phải đọc file bằng đường dẫn tuyệt đối của máy lập trình viên, hãy thay bằng resource test hoặc một thư mục tạm phù hợp. Nếu test ghi ngược lên `src/test/resources`, lần chạy tiếp theo có thể nhận trạng thái nguồn bị thay đổi; tốt hơn là sao chép dữ liệu ra vùng output/tạm trước khi ghi.

## 7. `build` chứa gì sau khi chạy Gradle?

Sau khi biên dịch, chạy test và tạo JAR, một cây output **có thể** trông như sau:

```text
build/
├── classes/
│   └── java/
│       ├── main/demo/App.class
│       └── test/demo/AppTest.class
├── resources/
│   ├── main/message.txt
│   └── test/test-only.txt
├── libs/
│   └── layout-demo.jar
├── reports/
│   └── tests/test/index.html
├── test-results/
│   └── test/TEST-demo.AppTest.xml
├── generated/                   (nếu có task sinh mã/file)
├── tmp/                         (tùy task)
└── distributions/               (nếu chạy task phân phối)
```

Tùy tác vụ đã chạy, không phải nhánh nào cũng xuất hiện. Ví dụ chỉ chạy `compileJava` không đảm bảo có báo cáo kiểm thử; plugin khác có thể thay đổi hình dạng của cây output.

| Thư mục | Ý nghĩa và nguồn tạo |
| --- | --- |
| `build/classes/java/main` | Bytecode của mã chính sau `compileJava` |
| `build/classes/java/test` | Bytecode của mã test sau `compileTestJava` |
| `build/resources/main` | Tài nguyên chính sau `processResources` |
| `build/resources/test` | Tài nguyên test sau `processTestResources` |
| `build/libs` | JAR hoặc artifact do task đóng gói tương ứng tạo |
| `build/test-results/test` | Kết quả test cho máy xử lý, thường chứa XML |
| `build/reports/tests/test` | Báo cáo HTML của task `test` khi được cấu hình tương ứng |
| `build/generated` | Output do task sinh mã/tài nguyên, nếu có |
| `build/tmp` | File tạm phục vụ task; không nên coi là API ổn định |

**`build` là output của một project Gradle**, không phải tên gọi của cả build script hoặc một source set. Task `clean` do Java/base plugin cung cấp thường xóa thư mục build được quản lý. Nếu dự án tùy biến vị trí output, hãy kiểm tra cấu hình thay vì áp cứng mọi đường dẫn ví dụ.

Các file `.class` không cần commit vào Git, vì Gradle có thể biên dịch lại từ `.java`. File JAR thông thường cũng được sinh lại qua `jar` hoặc task packaging tương ứng. Tránh coi `build` như nơi lưu nội dung có giá trị không thể tái tạo.

## 8. Ví dụ độc lập chạy được: ứng dụng dùng resource chính và JUnit dùng resource test

Ví dụ dùng **Gradle Groovy DSL, Java 17+ và JUnit Jupiter 5**. Plugin `application` áp dụng Java plugin và cung cấp task `run`; chương trình sẽ đọc resource qua classpath. Cây source cần tạo:

```text
layout-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   ├── java/demo/App.java
    │   └── resources/message.txt
    └── test/
        ├── java/demo/AppTest.java
        └── resources/test-only.txt
```

**`settings.gradle`:**

```groovy
rootProject.name = 'layout-demo'
```

**`build.gradle`:**

```groovy
plugins {
    id 'application'
}

application {
    mainClass = 'demo.App'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    testImplementation 'org.junit.jupiter:junit-jupiter:5.10.2'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher:1.10.2'
}

tasks.withType(JavaCompile).configureEach {
    options.encoding = 'UTF-8'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}
```

Java toolchain yêu cầu JDK 17 phù hợp (có sẵn hoặc đã cấu hình cơ chế cấp phát). Nếu dependency JUnit chưa được cache, Gradle cần truy cập Maven Central. `application.mainClass` cho biết task `run` khởi động lớp nào.

**`src/main/java/demo/App.java`:**

```java
package demo;

import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;

public final class App {
    private App() {
    }

    public static String message() {
        try (InputStream in = App.class.getResourceAsStream("/message.txt")) {
            if (in == null) {
                throw new IllegalStateException("Missing message.txt");
            }
            return new String(in.readAllBytes(), StandardCharsets.UTF_8).strip();
        } catch (IOException e) {
            throw new IllegalStateException("Cannot read message.txt", e);
        }
    }

    public static void main(String[] args) {
        System.out.println(message());
    }
}
```

**`src/main/resources/message.txt`:**

```text
Xin chào từ resources!
```

**`src/test/java/demo/AppTest.java`:**

```java
package demo;

import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

class AppTest {
    @Test
    void mainResourceIsAvailableDuringTest() {
        assertEquals("Xin chào từ resources!", App.message());
    }

    @Test
    void testOnlyResourceIsAvailableDuringTest() throws Exception {
        try (InputStream in =
                AppTest.class.getResourceAsStream("/test-only.txt")) {
            assertNotNull(in);
            String content =
                    new String(in.readAllBytes(), StandardCharsets.UTF_8).strip();
            assertEquals("Dữ liệu cho kiểm thử", content);
        }
    }
}
```

**`src/test/resources/test-only.txt`:**

```text
Dữ liệu cho kiểm thử
```

Nếu thư mục chưa có Wrapper, cần có bản Gradle tương thích với JDK trên máy để chạy `gradle wrapper` một lần và tạo `gradlew`, `gradlew.bat`, `gradle/wrapper/`. Sau đó, trên Linux/macOS:

```bash
./gradlew -q run
./gradlew test
./gradlew jar
```

Trên Windows PowerShell:

```powershell
.\gradlew.bat -q run
.\gradlew.bat test
.\gradlew.bat jar
```

Khi chạy `run` thành công, output do `App.main` in (với `-q` để giảm log Gradle) là:

```text
Xin chào từ resources!
```

Hai phương thức `@Test` sẽ chạy khi thực thi `test`. Không nên dự đoán chính xác toàn bộ log build vì các trạng thái task, download và thời gian khác nhau theo môi trường. Nếu test thành công, báo cáo thường có tại `build/reports/tests/test/index.html` và XML trong `build/test-results/test`.

Sau ba lệnh, kiểm tra output dự kiến theo đường dẫn mặc định:

```text
build/classes/java/main/demo/App.class
build/resources/main/message.txt
build/classes/java/test/demo/AppTest.class
build/resources/test/test-only.txt
build/libs/layout-demo.jar
```

Nếu JDK có lệnh `jar`, có thể kiểm tra nội dung artifact bằng:

```bash
jar tf build/libs/layout-demo.jar
```

Khi giữ cấu hình tên/version JAR mặc định của ví dụ, artifact chính thường chứa `demo/App.class` và `message.txt`. Nó không mặc định chứa `demo/AppTest.class` hoặc `test-only.txt`. Nếu thay đổi cấu hình artifact, hãy dùng tên file thực tế trong `build/libs`.

Lưu ý: plugin `application` cấu hình task `run` với `mainClass`, nhưng **không nên suy ra JAR chính chạy được trực tiếp bằng `java -jar`** nếu chưa kiểm tra manifest và dependency của JAR. Trong ví dụ, cách chạy đã xác định rõ là `./gradlew run`.

Tại sao bài thực hành này chứng minh cấu trúc thư mục có ý nghĩa?

1. `compileJava` nhận `App.java` từ `src/main/java` và xuất `App.class`.
2. `processResources` đưa `message.txt` vào output chính, giúp `App` đọc qua classpath.
3. `compileTestJava` nhận `AppTest.java` và dùng lớp `App` của `main`.
4. `processTestResources` đưa `test-only.txt` vào classpath test, không phải JAR chính.
5. `test` tạo kết quả kiểm thử; `jar` tạo sản phẩm thư viện/ứng dụng ở `build/libs` theo cấu hình.

## 9. Quan sát task để hiểu file nào xuất hiện

Một số lệnh giúp tự kiểm chứng bố cục thay vì đoán:

```bash
./gradlew tasks --all
./gradlew sourceSets
./gradlew classes
./gradlew testClasses
./gradlew test --dry-run
./gradlew clean build
```

- `tasks --all` liệt kê những task đã có trong project, kể cả task được plugin bổ sung.
- `sourceSets` của Java plugin hiển thị thông tin về tập nguồn và các đường dẫn/classpath đã cấu hình.
- `classes` chuẩn bị output chính, còn `testClasses` chuẩn bị output kiểm thử.
- `test --dry-run` cho xem kế hoạch task mà không chạy action; nó **không** tự tạo báo cáo test mới.
- `clean build` xóa output cũ rồi thực hiện vòng build được plugin định nghĩa, bao gồm việc kiểm thử theo cấu hình ví dụ.

Mô hình quan hệ thường gặp:

```text
compileJava + processResources --> classes --> jar / run
compileTestJava + processTestResources --> testClasses --> test
                                                 ^
                                  test cũng cần output của main
```

Không suy luận rằng mọi task được chọn đều thực hiện công việc ở mỗi lần chạy: Gradle có thể kết luận task `UP-TO-DATE` hoặc `NO-SOURCE` khi điều kiện tương ứng đúng. Lệnh `--dry-run` lại bỏ qua hành động có chủ ý, không có nghĩa task đã `UP-TO-DATE` trong lần chạy thật.

## 10. Khi nào cần đổi bố cục mặc định?

Các quy ước `src/main/java` và `src/test/java` giúp build script gọn, công cụ dễ tìm file. Nhưng với mã nguồn cũ hoặc mô hình nhiều nguồn, ta có thể **thêm** thư mục nguồn bằng `sourceSets`:

```groovy
// Đặt trong build.gradle của project đã có Java plugin.
sourceSets {
    main {
        java {
            srcDir 'src/shared/java'
        }
        resources {
            srcDir 'src/main/config'
        }
    }
}
```

`srcDir` trong ví dụ bổ sung một source root cho nhóm tương ứng; không có ý nghĩa là xóa `src/main/java` hay `src/main/resources` mặc định. Nếu cần khai báo đầu ra sinh tự động, nên đặt nó vào vùng output do Gradle quản lý và kết nối task sinh với task biên dịch qua cơ chế dependency/provider thay vì buộc người dùng chạy thủ công.

Cần phân biệt:

- **Thêm source root**: thay đổi nơi lấy mã/tài nguyên của source set hiện tại.
- **Thêm source set**: định nghĩa một tập nguồn khác, chẳng hạn `integrationTest`; thường phải cấu hình thêm dependency và task.
- **Thêm Gradle project**: tạo module/project con bằng `include` trong `settings.gradle`; mỗi project có thể có nhiều source set.

Đừng tạo thư mục `src/main/kotlin` hoặc `src/main/groovy` rồi mặc định cho rằng Java plugin biết biên dịch chúng. Với ngôn ngữ khác Java, cần plugin ngôn ngữ tương ứng và các cấu hình thích hợp.

## 11. Bố cục khi build có nhiều project

Build Gradle lớn thường có các project con. Ví dụ:

```text
workspace/
├── settings.gradle
├── build.gradle
├── app/
│   ├── build.gradle
│   ├── src/main/java/...
│   ├── src/main/resources/...
│   ├── src/test/java/...
│   └── build/
└── library/
    ├── build.gradle
    ├── src/main/java/...
    ├── src/test/java/...
    └── build/
```

Trong `settings.gradle`:

```groovy
rootProject.name = 'workspace'
include 'app', 'library'
```

Với Java plugin được áp dụng ở từng project, task có tên theo đường dẫn project, chẳng hạn `:app:compileJava` và `:library:test`. Chạy `./gradlew :app:test` chọn test của `app` cùng các task phụ thuộc cần thiết, không tự động có nghĩa chạy mọi test của `library`.

Nếu `app` cần mã từ `library`, trong `app/build.gradle` có thể khai báo dependency giữa project:

```groovy
dependencies {
    implementation project(':library')
}
```

Gradle sẽ dùng quan hệ dependency đó để giải quyết output/artifact giữa project. Hai thư mục đặt cạnh nhau không tự tạo quan hệ phụ thuộc. Mỗi project thường có `build` riêng; nhìn đường dẫn đầy đủ để biết file output thuộc module nào.

## 12. Git, IDE và quy tắc giữ cấu trúc sạch

Một `.gitignore` đơn giản cho Gradle:

```gitignore
.gradle/
build/
```

Thông thường nên commit `settings.gradle`, `build.gradle`, source code, resource cần thiết, test, và file Wrapper. Không nên commit những file `.class`, report test, file tạm hay cache. Tài nguyên trong `src/main/resources` và `src/test/resources` cũng là source, nhưng phải tránh lưu mật khẩu/token hoặc dữ liệu cá nhân thật.

IDE có thể có output riêng và thư mục cấu hình như `.idea`. Khi IDE và lệnh Gradle cho kết quả khác nhau, hãy kiểm tra source set thực tế qua `./gradlew sourceSets` và build bằng Wrapper. Không lấy đường dẫn do IDE tự sinh làm bằng chứng rằng Gradle đã cấu hình đúng.

Nếu resource không xuất hiện ở nơi chạy thật, kiểm tra lần lượt: file có nằm đúng source root không, task `processResources` có nhận nó không, output trong `build/resources/main` có nó không, và JAR/classpath cuối cùng có chứa nó không. Cách lần theo đường đi này hữu ích hơn việc chỉ kiểm tra file nguồn.

## 13. Lỗi phổ biến và hướng xử lý

| Triệu chứng | Nguyên nhân có thể | Cách sửa |
| --- | --- | --- |
| Class không được biên dịch | File `.java` đặt ngoài source root hoặc đường dẫn/package lệch quy ước | Đặt dưới `src/main/java` đúng package hoặc cấu hình source set |
| Resource đọc được ở IDE nhưng mất khi đóng gói | Đọc đường dẫn `src/main/resources` trực tiếp từ ổ đĩa | Dùng resource trên classpath và kiểm tra JAR |
| Test không tìm được file dữ liệu | File ở sai source root hoặc đường dẫn resource không đúng | Đặt ở `src/test/resources`, đọc với tên đúng |
| Mã sản phẩm cố import class từ `src/test/java` | Phụ thuộc ngược vào source set test | Chuyển mã dùng chung sang `main` hoặc module riêng phù hợp |
| JAR chứa dữ liệu test nhạy cảm | Đưa nhầm fixture vào `src/main/resources` hoặc cấu hình đóng gói sai | Đưa fixture sang `src/test/resources`; kiểm tra artifact |
| `clean` làm mất file quan trọng | Lưu file viết tay trong `build` | Chuyển file nguồn ra ngoài `build`; để task tạo output |
| Tạo `src/integrationTest/java` nhưng không chạy test | Chưa khai báo source set/task mới | Cấu hình `integrationTest` hoặc dùng plugin phù hợp |
| Thấy JAR nhưng chưa chắc test đã chạy | `jar` tập trung vào đóng gói | Chạy `test` hoặc `build` và xem kết quả |
| File Java ở `resources` không thành class | `resources` là thư mục tài nguyên, không phải Java source | Chuyển Java source tới `src/main/java` |
| Kết quả build giữa máy khác nhau | Dùng đường dẫn tuyệt đối hoặc cấu hình phụ thuộc môi trường | Dùng source sets, Wrapper, toolchain và resource trên classpath |

## 14. Tự thực hành

**Bài tập 1 — dự đoán output.** File `src/main/java/demo/Calculator.java` và `src/main/resources/config/app.properties` nằm ở đâu sau `classes`? Theo quy ước thông dụng: `build/classes/java/main/demo/Calculator.class` và `build/resources/main/config/app.properties`.

**Bài tập 2 — thử nguồn test.** Trong ví dụ mục 8, đổi tên `src/test/resources/test-only.txt` thành `fixture.txt` và sửa test theo tên mới. Chạy `test` rồi `jar`; chứng minh file fixture chỉ được đưa vào output test mà không nằm trong JAR chính.

**Bài tập 3 — quan sát vòng đời output.** Chạy `./gradlew clean build` và xem cây `build`; sau đó chạy `./gradlew clean`. Vì sao `src/main/java/demo/App.java` vẫn còn? Vì `clean` thao tác trên output, còn `src` là đầu vào của dự án.

**Bài tập 4 — nhiều project.** Vẽ `workspace` với `app`, `api`, `core`; chỉ rõ `src/main`, `src/test` và `build` thuộc project nào. Dự đoán ý nghĩa của `:app:test` so với `:core:test`.

**Câu hỏi tự kiểm tra:**

1. `src/main/java` và `src/main/resources` được Gradle xử lý khác nhau ra sao?
2. Tại sao classpath test có thể chứa cả output `main` và `test`?
3. Vì sao `src/test/resources` thường không đi vào JAR chính?
4. Khi ứng dụng nằm trong JAR, tại sao nên đọc resource bằng classpath?
5. `build/classes`, `build/resources`, `build/libs` và `build/reports` dùng làm gì?
6. Một source set khác một Gradle project ở đâu?
7. Vì sao nên commit Wrapper nhưng bỏ qua `build` trong Git?

**Ghi nhớ:** `src/main` là phần nguồn của ứng dụng, `src/test` là phần nguồn kiểm thử, `resources` chứa dữ liệu được đưa lên classpath của source set tương ứng, còn `build` giữ các kết quả do Gradle tạo. Java/application plugin nối những vùng này với các task biên dịch, sao chép tài nguyên, kiểm thử và đóng gói. Hiểu rõ quan hệ ấy sẽ giúp bạn đặt file đúng chỗ, tìm output nhanh và gỡ lỗi build có hệ thống.