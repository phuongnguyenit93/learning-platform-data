# Tổ chức mã nguồn, tài nguyên và ví dụ có thể chạy lại trong Java 17

Một ví dụ Java chỉ thực sự hữu ích khi người khác có thể lấy mã nguồn, dựng đúng môi trường, chạy cùng lệnh và quan sát được kết quả mong đợi. Muốn vậy, cần tổ chức rõ **mã nguồn ứng dụng**, **tài nguyên**, **mã kiểm thử**, **dữ liệu kiểm thử**, **cấu hình build** và **hướng dẫn chạy**.

Bài này xây dựng một dự án **Java 17 + Maven + JUnit Jupiter** hoàn chỉnh. Các API được dùng, chẳng hạn `InputStream.readAllBytes()`, `String.isBlank()`, `String.strip()` và `String.formatted()`, đều có trong Java 17. Các phiên bản công cụ được ghim để ví dụ có mốc build xác định; không mặc định coi chúng là bản mới nhất ở mọi thời điểm.

## 1. Thế nào là ví dụ “có thể chạy lại”?

Một ví dụ cần trả lời được năm câu hỏi:

1. **Chạy bằng JDK nào?** Ở đây là **JDK 17**, có cả `java` và `javac`.
2. **Dùng công cụ build nào?** Dự án dùng Maven và cung cấp Maven Wrapper.
3. **Mã nguồn, tài nguyên và test ở đâu?** Tuân theo cấu trúc thư mục chuẩn.
4. **Lệnh build, test và chạy là gì?** Ghi rõ lệnh dùng trên Windows, Linux và macOS.
5. **Đầu ra nào cho biết kết quả đúng?** Có test tự động và ví dụ output.

Nên phân biệt:

| Mục tiêu | Ý nghĩa | Cách đáp ứng |
| --- | --- | --- |
| Chạy lại cùng chức năng | Cùng đầu vào cho kết quả có ý nghĩa giống nhau | Ghi rõ dữ liệu, lệnh chạy và kỳ vọng |
| Dựng được trên máy khác | Máy khác biên dịch, test, đóng gói được | Ghim JDK mục tiêu, Maven, plugins, dependencies |
| Artifact giống từng byte | Tệp build ra trùng khớp qua các lần build | Kiểm soát thêm thời gian, môi trường, toolchain và bước build |

Bài thực hành đảm bảo nền tảng cho hai mục tiêu đầu. `project.build.outputTimestamp` giúp ổn định timestamp trong JAR, nhưng không tự nó bảo đảm mọi artifact giống hệt từng byte giữa mọi môi trường.

## 2. Cấu trúc thư mục nguồn chuẩn

~~~text
replay-demo/
├── .mvn/
│   └── wrapper/
│       └── maven-wrapper.properties   # Sinh bằng Maven Wrapper
├── mvnw                              # Wrapper trên Linux/macOS
├── mvnw.cmd                          # Wrapper trên Windows
├── pom.xml                           # Cấu hình Maven
├── README.md                         # Lệnh build, test, chạy
├── .gitignore
└── src/
    ├── main/
    │   ├── java/
    │   │   └── vn/example/replay/
    │   │       ├── App.java
    │   │       └── GreetingService.java
    │   └── resources/
    │       └── messages/
    │           └── greeting.txt
    └── test/
        ├── java/
        │   └── vn/example/replay/
        │       └── GreetingServiceTest.java
        └── resources/
            └── fixtures/
                └── person.txt
~~~

| Đường dẫn | Chức năng | Được đóng trong JAR ứng dụng? |
| --- | --- | --- |
| `src/main/java` | Mã Java của ứng dụng | Có, sau khi biên dịch thành `.class` |
| `src/main/resources` | File mẫu, dữ liệu tĩnh và resource cần lúc chạy | Có, trên classpath |
| `src/test/java` | Mã unit test | Không |
| `src/test/resources` | Fixture dùng khi test | Không |
| `pom.xml` | Khai báo build và dependencies | Không |
| `target/` | Kết quả biên dịch và đóng gói do Maven tạo | Không nên commit vào Git |

Thư mục `vn/example/replay` phản ánh tên package `vn.example.replay`. Với mã có nhiều lớp, dùng package rõ ràng thay vì đặt lớp vào *default package*. Có thể tạo thêm các package như `service`, `model`, `repository` khi ứng dụng lớn lên; với ví dụ nhỏ thì chia quá nhiều lớp thư mục sẽ khiến người học khó theo dõi.

Java 17 cũng hỗ trợ **Java Platform Module System (JPMS)** qua `module-info.java`. Dự án mẫu chủ động chạy trên **classpath**, nên không cần `module-info.java`. Nếu chọn module path cho một dự án lớn hơn, hãy cấu hình và khai báo các module nhất quán với dependencies của nó.

## 3. Viết chương trình có resource đóng gói

Ví dụ sẽ nạp một mẫu lời chào từ `src/main/resources`, nhận tên từ tham số dòng lệnh và in ra câu hoàn chỉnh.

### 3.1. Tách logic khỏi lớp `main`

Tạo **`src/main/java/vn/example/replay/GreetingService.java`**:

~~~java
package vn.example.replay;

public final class GreetingService {
    private GreetingService() {
        // Lớp tiện ích, không cần tạo đối tượng.
    }

    public static String greet(String template, String name) {
        if (template == null || template.isBlank()) {
            throw new IllegalArgumentException("Mẫu lời chào không được trống");
        }
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("Tên không được trống");
        }
        return template.formatted(name.strip());
    }
}
~~~

Lớp này chỉ xử lý chuỗi và không phụ thuộc vào console hoặc filesystem, nên có thể kiểm thử độc lập. `String.strip()` bỏ khoảng trắng bao quanh tên; `String.formatted()` định dạng lời chào theo placeholder `%s`.

Ví dụ dùng template do dự án kiểm soát, chứa đúng một placeholder `%s`. Nếu template lấy từ nguồn tùy ý, phải kiểm tra định dạng và xử lý lỗi định dạng thay vì mặc định nội dung luôn hợp lệ.

### 3.2. Đọc resource từ classpath

Tạo **`src/main/java/vn/example/replay/App.java`**:

~~~java
package vn.example.replay;

import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;

public final class App {
    private App() {
    }

    public static void main(String[] args) throws IOException {
        String name = args.length == 0 ? "Java 17" : args[0];

        try (InputStream stream =
                     App.class.getResourceAsStream("/messages/greeting.txt")) {
            if (stream == null) {
                throw new IllegalStateException(
                        "Không tìm thấy resource /messages/greeting.txt");
            }

            String template = new String(
                    stream.readAllBytes(), StandardCharsets.UTF_8).strip();

            System.out.println(GreetingService.greet(template, name));
        }
    }
}
~~~

Tạo **`src/main/resources/messages/greeting.txt`**, lưu file theo UTF-8:

~~~text
Xin chào, %s! Đây là ví dụ Java 17.
~~~

Ba điểm cần hiểu:

- `App.class.getResourceAsStream("/messages/greeting.txt")` tìm resource từ **gốc classpath**; dấu `/` ở đầu là quan trọng khi dùng `Class.getResourceAsStream`.
- Nếu resource không tồn tại, phương thức trả về `null`. Kiểm tra và báo lỗi rõ ràng giúp dễ phát hiện việc đặt nhầm thư mục hoặc đóng gói thiếu file.
- `try-with-resources` đóng luồng; `StandardCharsets.UTF_8` giúp đọc tiếng Việt ổn định trên các máy có charset mặc định khác nhau.

**Không** đọc file này bằng đường dẫn `src/main/resources/messages/greeting.txt` trong code chạy. Đường dẫn ấy thuộc cây mã nguồn, còn khi ứng dụng chạy từ JAR, resource nằm bên trong archive và được nạp qua classpath.

## 4. Viết test và fixture riêng

Tạo **`src/test/java/vn/example/replay/GreetingServiceTest.java`**:

~~~java
package vn.example.replay;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import org.junit.jupiter.api.Test;

class GreetingServiceTest {

    @Test
    void formatsAndTrimsName() {
        String actual =
                GreetingService.greet("Xin chào, %s!", "  An  ");

        assertEquals("Xin chào, An!", actual);
    }

    @Test
    void rejectsBlankName() {
        assertThrows(
                IllegalArgumentException.class,
                () -> GreetingService.greet("Xin chào, %s!", "   "));
    }

    @Test
    void readsFixtureFromTestClasspath() throws IOException {
        try (InputStream stream =
                     getClass().getResourceAsStream("/fixtures/person.txt")) {
            assertNotNull(stream, "Thiếu fixture /fixtures/person.txt");

            String name = new String(
                    stream.readAllBytes(), StandardCharsets.UTF_8).strip();

            assertEquals(
                    "Xin chào, Bình!",
                    GreetingService.greet("Xin chào, %s!", name));
        }
    }
}
~~~

Tạo **`src/test/resources/fixtures/person.txt`**, dùng UTF-8:

~~~text
Bình
~~~

Trong chu kỳ test của Maven:

- `src/main/java` được biên dịch vào `target/classes`; `src/main/resources` được sao chép vào cùng vị trí để có thể đọc từ classpath.
- `src/test/java` được biên dịch vào `target/test-classes`; `src/test/resources` cũng được sao chép vào đó.
- Test có thể truy cập mã ứng dụng và fixture, nhưng fixture không xuất hiện trong JAR ứng dụng thông thường.

Fixture nên nhỏ, ổn định, có ý nghĩa với mục tiêu test. Kết quả phải được **assert** để tự động xác định đúng/sai; chỉ gọi `System.out.println()` trong test rồi so sánh bằng mắt sẽ khó chạy lại một cách đáng tin cậy.

## 5. Cấu hình Maven cho JDK 17 và JUnit

Tạo **`pom.xml`** ở thư mục gốc:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>vn.example</groupId>
    <artifactId>replay-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <project.reporting.outputEncoding>UTF-8</project.reporting.outputEncoding>
        <project.build.outputTimestamp>2026-01-01T00:00:00Z</project.build.outputTimestamp>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>5.11.4</version>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-clean-plugin</artifactId>
                <version>3.4.1</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-resources-plugin</artifactId>
                <version>3.3.1</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.0</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.5.2</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-jar-plugin</artifactId>
                <version>3.4.2</version>
                <configuration>
                    <archive>
                        <manifest>
                            <mainClass>vn.example.replay.App</mainClass>
                        </manifest>
                    </archive>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Ý nghĩa các thành phần:

- `maven.compiler.release=17` yêu cầu mã nguồn và API đích tương thích với Java 17, đồng thời tạo bytecode phù hợp.
- `project.build.sourceEncoding=UTF-8` đặt charset cho quá trình xử lý nguồn và tài nguyên theo các plugin tương ứng.
- Dependency JUnit có `scope=test`, chỉ phục vụ kiểm thử, không đưa vào runtime của chương trình.
- `maven-surefire-plugin` chạy các test theo quy ước đặt tên, chẳng hạn `GreetingServiceTest`.
- `maven-jar-plugin` tạo manifest với `Main-Class` để có thể chạy `java -jar`.
- Phiên bản plugin được ghim rõ để tránh hành vi build thay đổi bất ngờ khi môi trường tự chọn plugin mới.

Bản mẫu không có dependency ngoài lúc chạy, vì thế JAR thông thường có thể khởi động trực tiếp. Trong ứng dụng có thư viện runtime, **JAR mặc định không tự kèm toàn bộ dependency**. Khi đó phải khai báo cách phân phối phù hợp: classpath kèm thư viện, bundle ứng dụng hoặc plugin đóng gói đã được cấu hình và kiểm thử.

## 6. Dùng Maven Wrapper để tránh lệ thuộc Maven cài sẵn

Maven Wrapper là tập script `mvnw`/`mvnw.cmd` và metadata chọn bản Maven cho dự án. Người tải repo vẫn cần JDK phù hợp, nhưng không phải tự đoán bản Maven.

Nếu đang khởi tạo dự án trên máy có Maven, tạo wrapper **một lần** tại thư mục gốc:

~~~bash
mvn -N org.apache.maven.plugins:maven-wrapper-plugin:3.3.4:wrapper -Dmaven=3.9.11
~~~

Commit các script và file trong `.mvn/wrapper` được tạo ra. Từ đó các thành viên gọi wrapper của dự án. Maven 3.9.11 ở đây là **phiên bản ghim của ví dụ**, không phải tuyên bố về bản Maven mới nhất.

### 6.1. Windows PowerShell

Chạy từ thư mục chứa `pom.xml` và `mvnw.cmd`:

~~~powershell
java -version
javac -version
.\mvnw.cmd --version
.\mvnw.cmd clean verify
java -jar .\target\replay-demo-1.0.0.jar
java -jar .\target\replay-demo-1.0.0.jar Lan
~~~

### 6.2. Linux và macOS

~~~bash
java -version
javac -version
./mvnw --version
./mvnw clean verify
java -jar target/replay-demo-1.0.0.jar
java -jar target/replay-demo-1.0.0.jar Lan
~~~

Nếu script `mvnw` chưa có quyền chạy trên Unix, thực hiện `chmod +x mvnw` và lưu permission trong Git.

`clean verify` loại bỏ output build cũ, xử lý nguồn và resources, chạy test rồi đóng gói artifact. Lần đầu wrapper hoặc Maven tải bản phân phối/dependencies chưa có trong cache có thể cần mạng.

Kết quả tương ứng hai lệnh `java -jar`:

~~~text
Xin chào, Java 17! Đây là ví dụ Java 17.
Xin chào, Lan! Đây là ví dụ Java 17.
~~~

Khi test pass, Maven báo build thành công. Nội dung log, đường dẫn tải gói và thời gian chạy có thể khác giữa máy; kết quả cần kiểm chứng là các assertion đều pass và chương trình xuất đúng chuỗi đã nêu.

Dùng công cụ `jar` của JDK 17 để liệt kê nội dung artifact:

~~~bash
jar --list --file target/replay-demo-1.0.0.jar
~~~

Trong danh sách nên có `vn/example/replay/App.class`, `vn/example/replay/GreetingService.class` và `messages/greeting.txt`. Fixture `fixtures/person.txt` chỉ phục vụ kiểm thử nên không được đóng vào JAR ứng dụng.

## 7. Phân biệt resource trong JAR với file ngoài

Đây là khác biệt thường làm một ví dụ chỉ chạy được trong IDE.

**Resource đóng gói:** file do dự án quản lý, chỉ đọc, phát hành cùng code. Đọc qua classpath.

~~~java
// Class.getResourceAsStream: dấu "/" nghĩa là gốc classpath.
InputStream a = App.class.getResourceAsStream("/messages/greeting.txt");

// ClassLoader.getResourceAsStream: không có "/" ở đầu.
InputStream b = App.class.getClassLoader()
        .getResourceAsStream("messages/greeting.txt");
~~~

**File ngoài:** dữ liệu có thể được tạo hoặc sửa khi chương trình chạy, chẳng hạn CSV nhập từ người dùng, báo cáo hoặc cấu hình dành cho từng môi trường. Đọc bằng `Path`/`Files`:

~~~java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

Path input = Path.of("data", "input.txt");
String content = Files.readString(input, StandardCharsets.UTF_8);
~~~

`Path.of("data", "input.txt")` là đường dẫn **tương đối với working directory của tiến trình**, không mặc nhiên tương đối với vị trí file `.java` hoặc JAR. Nếu ví dụ yêu cầu file ngoài, README phải mô tả nơi đặt file hoặc cách truyền đường dẫn bằng tham số.

Không nên đóng gói dữ liệu nhạy cảm như khóa API, mật khẩu, token vào `src/main/resources`. Sử dụng biến môi trường hoặc dịch vụ quản lý secret tùy môi trường chạy.

## 8. Các yếu tố ảnh hưởng khả năng chạy lại

**Phiên bản:** ghi rõ JDK mục tiêu, sử dụng wrapper, ghim phiên bản dependencies/plugins. Khi nâng cấp, thay đổi có chủ đích và chạy lại test. Tránh dùng version range động cho ví dụ cần tái hiện ổn định.

**Dữ liệu:** lưu fixture cùng repo khi phù hợp; cung cấp các ví dụ đầu vào không chứa dữ liệu riêng tư. Test nên dùng dữ liệu tự chứa và không phụ thuộc file nằm trên máy của tác giả.

**Charset và xuống dòng:** lưu file văn bản UTF-8, dùng `StandardCharsets.UTF_8` lúc đọc và ghi. Khi test chuỗi nhiều dòng trên nhiều hệ điều hành, xét đến khác biệt `\n` và `\r\n` hoặc chuẩn hóa xuống dòng trước khi so sánh nếu yêu cầu.

**Thời gian, ngẫu nhiên và locale:** các test phụ thuộc `Instant.now()`, `LocalDate.now()`, `Random` không có seed, timezone mặc định, định dạng số/ngày theo locale hoặc gọi dịch vụ mạng có thể cho kết quả khác nhau. Với logic cần kết quả cố định, truyền `Clock`, `ZoneId`, seed và `Locale` thích hợp từ bên ngoài; dùng fake/stub cho dependency bên ngoài ở cấp unit test.

**Build output:** không sửa tệp trong `target/` vì chúng sẽ bị ghi đè. Chỉnh file trong `src` hoặc `pom.xml` rồi build lại. Không commit cache, log và artifact sinh ra khi không có lý do phân phối rõ ràng.

`.gitignore` tối thiểu:

~~~gitignore
target/
*.log
.idea/
*.iml
.vscode/
~~~

Không bỏ qua `mvnw`, `mvnw.cmd` hay toàn bộ `.mvn/wrapper/`: đó là bộ phận giúp người khác sử dụng đúng trình build đã chọn.

## 9. README là một phần của ví dụ

Tạo `README.md` với chỉ dẫn ngắn nhưng tự chứa. Chẳng hạn:

~~~markdown
# replay-demo

Ví dụ Java 17 đọc resource từ classpath và có JUnit test.

## Yêu cầu
- JDK 17.
- Có kết nối mạng cho lần đầu Maven Wrapper tải các thành phần còn thiếu.

## Build và test
Windows PowerShell: .\mvnw.cmd clean verify
Linux/macOS: ./mvnw clean verify

## Chạy
java -jar target/replay-demo-1.0.0.jar
java -jar target/replay-demo-1.0.0.jar Lan

## Kết quả
Xin chào, Java 17! Đây là ví dụ Java 17.
Xin chào, Lan! Đây là ví dụ Java 17.

## Vị trí file
- src/main/java: mã ứng dụng
- src/main/resources: resource đi cùng JAR
- src/test/java: mã kiểm thử
- src/test/resources: dữ liệu thử nghiệm
~~~

README cần cho biết **thư mục chạy lệnh**, yêu cầu cài đặt, cách build, cách test, cách khởi động, tham số và kết quả mong đợi. Nếu ví dụ có nhiều lệnh khác nhau cho các hệ điều hành, ghi riêng các biến thể thay vì giả định mọi môi trường dùng cùng cú pháp.

Với repository nhiều ví dụ, có thể dùng `examples/` hoặc module riêng cho từng chủ đề. Mỗi ví dụ nên có điểm vào và lệnh chạy xác định; mã dùng chung cần được đưa vào module/thư viện có dependency rõ ràng, thay vì copy thủ công rồi để các bản sao lệch nhau.

## 10. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân điển hình | Hướng xử lý |
| --- | --- | --- |
| IDE chạy được, `java -jar` báo không tìm thấy file | Code đọc trực tiếp `src/main/resources` như filesystem | Dùng `getResourceAsStream` và kiểm tra nội dung JAR |
| `getResourceAsStream` trả về `null` | Đường dẫn sai hoặc resource không nằm trên classpath | Kiểm tra dấu `/` và vị trí `src/main/resources` |
| Test không nhận ra `org.junit.jupiter.api` | Thiếu dependency JUnit hoặc test đặt sai thư mục | Khai báo `junit-jupiter` với `scope=test`, đặt test đúng `src/test/java` |
| Chạy trên máy khác lỗi Java version | Sai JDK hoặc compiler target | Kiểm tra `java -version`, `javac -version` và `release=17` |
| File tiếng Việt bị lỗi ký tự | Charset không thống nhất | Lưu và đọc bằng UTF-8, cấu hình encoding trong Maven |
| Test lúc pass lúc fail | Phụ thuộc thời gian, timezone, ngẫu nhiên, mạng | Làm chủ đầu vào và thay dependency ngoài ở mức unit test |
| JAR chạy nhưng thiếu thư viện | JAR thường không mang theo toàn bộ runtime dependencies | Định nghĩa cách đóng gói/phân phối dependencies |
| Git đầy file biên dịch và log | Commit `target/` hay file IDE | Bổ sung `.gitignore` phù hợp |

## 11. Bài tập mở rộng

1. Tạo `src/main/resources/messages/farewell.txt`, đọc bằng classpath và in lời tạm biệt. Kiểm tra bản JAR đã build vẫn tìm được file.
2. Thêm test sử dụng một fixture mới trong `src/test/resources`, so sánh kết quả bằng `assertEquals`.
3. Thêm tùy chọn nhận tên file văn bản từ tham số, đọc bằng `Files.readString`, và hướng dẫn cách truyền đường dẫn trong README.
4. Chỉnh sửa `greeting.txt`, chạy lại `clean verify` và quan sát nội dung thay đổi sau khi đóng gói JAR mới.

**Kết quả mong muốn:** Một người chỉ cần repository, JDK 17 và chỉ dẫn trong README có thể cài các thành phần còn thiếu, chạy `clean verify`, chạy JAR và quan sát đầu ra đã mô tả, không cần đường dẫn riêng của máy tác giả hay thao tác thủ công trong IDE.
