# Chẩn đoán “invalid target release” và bytecode Java không tương thích khi build bằng Maven

## 1. Tình huống: build thất bại hay chỉ lỗi khi chạy?

Một nhóm phát triển dùng Maven để biên dịch dự án Java 17. Trên máy người A, lệnh `mvn clean package` chạy được; trên CI, lệnh tương tự báo:

~~~text
Fatal error compiling: error: invalid target release: 17
~~~

Hoặc thông điệp khác:

~~~text
error: release version 17 not supported
~~~

Ở tình huống thứ hai, CI build thành công, nhưng file JAR triển khai lên máy chủ chạy Java 11 lại thất bại:

~~~text
java.lang.UnsupportedClassVersionError:
  ... has been compiled by a more recent version of the Java Runtime
  (class file version 61.0), this version of the Java Runtime
  only recognizes class file versions up to 55.0
~~~

Ba thông báo có liên quan đến **mức Java**, nhưng xuất hiện ở **hai giai đoạn khác nhau** và có cách sửa khác nhau. Nếu chưa phân loại được, người học dễ đổi `<maven.compiler.target>` tùy tiện, làm ứng dụng không còn biên dịch, hoặc “hạ version cho hết lỗi” trong khi code dùng API Java mới.

**Mục tiêu bài học:** chẩn đoán đúng JDK đang chạy Maven, JDK thực sự biên dịch, mức Java được cấu hình, class-file major version sinh ra và JVM thật sự chạy ứng dụng. Sau đó đưa mọi môi trường về một **hợp đồng tương thích rõ ràng**: ví dụ “build bằng JDK 17 hoặc 21 có hỗ trợ `--release 17`; sản phẩm yêu cầu runtime Java 17 trở lên”.

Bài tập chính dùng **Maven 3.9.x, Java 17, Maven Compiler Plugin 3.14.1 và JUnit Jupiter 5**. Có thí nghiệm tùy chọn với JDK 11 và JDK 21, **chỉ thực hiện khi những JDK đó đã được cài sẵn**. Không cần thay đổi toàn bộ môi trường hệ điều hành để học phần lý thuyết.

## 2. Ba khái niệm thường bị nhầm: JDK build, target bytecode và JVM runtime

~~~text
pom.xml:
    maven.compiler.release = 17
                  |
                  v
           Maven build process
           (mvn -version)
                  |
          chọn javac thực tế
       (mặc định hoặc toolchain)
                  |
                  v
           javac --release 17
                  |
                  v
          *.class: major 61
                  |
        Maven đóng gói JAR
                  |
                  v
       Java runtime trên server
       (java -version ở server)
                  |
          hỗ trợ class 61?
             /          \
           Có          Không
            |              |
         nạp class     UnsupportedClassVersionError
~~~

Có ít nhất **bốn thông tin độc lập**:

1. **Java chạy Maven:** kết quả `mvn -version`. Maven là một chương trình Java, vì vậy nó có JVM runtime của chính nó.
2. **Java compiler được sử dụng:** thường là `javac` của JDK chạy Maven, nhưng có thể bị thay qua Maven Toolchains, forked compiler hoặc một cấu hình plugin đặc biệt.
3. **Mức Java mà compiler được yêu cầu tạo ra:** ví dụ `maven.compiler.release=17`, hoặc trong dự án cũ là `source`/`target`.
4. **JVM chạy artifact:** kết quả `java -version` trên máy/container **thực sự khởi động ứng dụng**. JVM này không nhất thiết trùng với JVM chạy Maven hay IDE.

Một JDK 21 **có thể** biên dịch mã cho Java 17 khi hỗ trợ `javac --release 17`. Nhưng một JDK 11 **không thể** dùng `javac --release 17` để tạo chương trình nhắm Java 17. Sau khi đã build ra class-file major 61, **Java 11 không thể chạy class đó**, dù tên JAR hoặc tọa độ Maven vẫn giống nhau.

### 2.1. Bộ từ vựng cần nhớ

| Từ khóa | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| JDK | Bộ công cụ phát triển, bao gồm `javac`, `java`, `javap` | JDK 17, JDK 21 |
| `javac` | Compiler tạo bytecode `.class` | `javac --release 17` |
| `java` | Launcher/JVM nạp và chạy class | `java -jar app.jar` |
| `source` | Mức cú pháp/ngôn ngữ được compiler chấp nhận | `-source 17` |
| `target` | Mức định dạng bytecode được compiler sinh | `-target 17` |
| `release` | Mức ngôn ngữ, bytecode **và API Java chuẩn** được compiler nhắm đến | `--release 17` |
| Class-file major version | Số phiên bản định dạng trong file `.class` | Java 17: **61** |
| Maven Compiler Plugin | Plugin Maven cấu hình compiler cho goal `compile`/`testCompile` | Version 3.14.1 |
| Maven Toolchains | Cơ chế chọn công cụ JDK không nhất thiết là JDK khởi động Maven | Chọn javac JDK 17 từ toolchain |
| Runtime compatibility | Điều kiện ứng dụng và thư viện nạp được trên JVM thật | Class 61 không chạy trên JVM 11 |

## 3. Lỗi 1: “invalid target release” xảy ra lúc biên dịch

Thông báo có thể thấy ở Maven build:

~~~text
[ERROR] Failed to execute goal
org.apache.maven.plugins:maven-compiler-plugin:3.14.1:compile
(default-compile) on project bytecode-demo:
Fatal error compiling: error: invalid target release: 17
~~~

Hoặc, khi plugin truyền `--release` cho một JDK thấp hơn:

~~~text
[ERROR] error: release version 17 not supported
~~~

**Ý nghĩa:** compiler thực tế được gọi **không hỗ trợ mức target/release được yêu cầu**. Trường hợp điển hình là POM yêu cầu Java 17 nhưng Maven đang chạy bằng JDK 11 và không có toolchain JDK 17 phù hợp. Với `--release 17`, JDK 11 sẽ từ chối vì đó là release trong tương lai so với chính compiler.

Dòng thông báo chính xác tùy:

- Phiên bản compiler/JDK.
- Plugin nhận `<release>` hay `<source>/<target>`.
- Compiler chạy trong Maven, forked `javac` hay qua toolchain.
- Cấu hình profile hoặc parent POM đang có hiệu lực.

Vì vậy **đừng chẩn đoán chỉ bằng việc copy nguyên văn câu lỗi**. Hãy xác định rõ compiler thực tế và effective configuration.

### 3.1. Bước kiểm tra đầu tiên

Trong đúng terminal/CI job đang lỗi:

~~~bash
mvn -version
java -version
javac -version
~~~

Giả sử đầu ra cho thấy:

~~~text
mvn -version       -> Java version: 11.x
java -version      -> 17.x
javac -version     -> javac 17.x
~~~

Đây là **mẫu tình huống minh họa**, không phải output nguyên văn của một Maven installation cụ thể. Nó cho thấy `java` và `javac` trong `PATH` có thể là JDK 17, nhưng Maven đang được khởi động bằng JDK 11, ví dụ qua `JAVA_HOME`. Khi plugin không chọn compiler khác, Maven có thể vẫn gọi compiler không đạt yêu cầu.

**Ưu tiên `mvn -version` để xác định JVM chạy Maven**. `java -version` một mình không chứng minh Maven đang dùng cùng JVM.

### 3.2. Kiểm tra cấu hình POM thực tế

Tìm các trường:

~~~xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
</properties>
~~~

hoặc:

~~~xml
<configuration>
    <release>17</release>
</configuration>
~~~

Trong một dự án cũ có thể gặp:

~~~xml
<properties>
    <maven.compiler.source>17</maven.compiler.source>
    <maven.compiler.target>17</maven.compiler.target>
</properties>
~~~

Nếu project có parent, profile hoặc `pluginManagement`, file `pom.xml` của module con **chưa phải toàn bộ effective configuration**. Sau khi môi trường có thể chạy Help Plugin, kiểm tra:

~~~bash
mvn help:effective-pom
mvn help:evaluate -Dexpression=maven.compiler.release -q -DforceStdout
~~~

Lệnh `help:evaluate` đọc **property**; nếu plugin ghi `<release>` tường minh hoặc bị profile/management ghi đè, phải đối chiếu **effective POM**, không xem riêng output property.

### 3.3. Cách sửa đúng cho dự án Java 17

Nếu ứng dụng thực sự dùng Java 17:

- Dùng JDK **17 trở lên** có compiler hỗ trợ release 17.
- Đảm bảo **Maven hoặc toolchain của Compiler Plugin** chọn đúng JDK đó.
- Giữ `maven.compiler.release=17` trong POM, thay vì hạ xuống 11 chỉ để lệnh build qua.
- Chuẩn hóa JDK ở CI, IDE và terminal; kiểm tra lại `mvn -version` sau khi chuyển JDK.
- Chạy `mvn clean verify` và kiểm tra class-file major version.

**Không** đổi `<target>11</target>` nếu source đang sử dụng Java 17 features, records hoặc API chỉ có ở Java 17. Target thấp hơn không tự dịch mã mới thành bytecode tương thích hay tự cung cấp API cũ.

## 4. Lỗi 2: “UnsupportedClassVersionError” xảy ra khi nạp class

Thông báo đặc trưng:

~~~text
java.lang.UnsupportedClassVersionError:
  vn/example/bytecode/App has been compiled by a more recent version
  of the Java Runtime (class file version 61.0),
  this version of the Java Runtime only recognizes
  class file versions up to 55.0
~~~

Thông điệp rút gọn ở trên minh họa **class 61.0 chạy trên Java 11 tối đa 55.0**. Tên class và phần mô tả chính xác sẽ phụ thuộc JVM/stack trace.

**Ý nghĩa:** JVM đang đọc một `.class` có major/minor version mà nó không hỗ trợ. Với một ứng dụng bình thường, điều này thường có nghĩa **runtime JVM cũ hơn compiler target**, không phải lỗi Maven đang phân giải plugin.

Lỗi có thể xuất hiện khi:

- Gọi `java -jar` trên máy chạy Java 11 với JAR biên dịch cho Java 17.
- Khởi động web container hoặc framework launcher dùng JVM cũ, dù người vận hành chạy `java -version` ở terminal khác và thấy JVM mới.
- Maven Surefire/Failsafe dùng một JVM để chạy test không tương thích với classes được biên dịch bằng compiler/toolchain khác.
- Lúc chạy, một **dependency JAR** chứa class có bytecode mới hơn runtime, mặc dù `App.class` của bạn đã nhắm đúng Java 17.
- Một plugin công cụ nạp Java class bằng JVM cũ trong quá trình build; khi đó stack trace chỉ ra class loader của plugin, không nhất thiết là application runtime.

### 4.1. Phải đọc đúng tên class trong lỗi

Nếu lỗi nêu `vn/example/bytecode/App`, hãy kiểm tra class của ứng dụng.

Nếu lỗi nêu `com/vendor/library/SomeImplementation`, kiểm tra **dependency cụ thể** chứa class đó. Không kết luận từ `App.class` có major 61 rằng mọi dependency chắc chắn cũng chỉ có major 61. Một dependency được build bằng Java 21 có thể mang major 65 và làm Java 17 không nạp được.

### 4.2. Cách sửa đúng

Có ba hướng tùy hợp đồng sản phẩm:

1. **Nâng JVM chạy ứng dụng** lên mức hỗ trợ bytecode của tất cả classes cần nạp, nếu môi trường triển khai cho phép.
2. **Biên dịch bằng release thấp hơn**, nhưng chỉ nếu code và các API/dependencies thật sự tương thích với release đó; kiểm tra lại đầy đủ.
3. **Chọn một dependency version tương thích hơn** hoặc thay dependency, nếu chính nó yêu cầu JVM cao hơn; không cố sửa ứng dụng bằng cách đổi một flag compilation không ảnh hưởng thư viện đã phát hành.

Đừng trộn ba hướng này thành “cài JDK mới ở laptop là đủ”. Runtime thật ở Docker image, server, IDE, test runner hoặc máy người dùng **phải thay đổi đúng nơi**.

## 5. Bảng class-file major version: tra lỗi mà không đoán

Java class files có một cặp số `major.minor` trong header. Các mốc phổ biến:

| Java SE/JDK target | Class-file major | Ví dụ hiển thị |
| --- | ---: | --- |
| Java 8 | 52 | `52.0` |
| Java 11 | 55 | `55.0` |
| Java 17 | 61 | `61.0` |
| Java 21 | 65 | `65.0` |

Đây là các giá trị chuẩn theo **Java Virtual Machine Specification**, không phải version Maven hay artifact version. Không chuyển `major=61` thành “Maven 6.1”; nó có nghĩa **định dạng class tương ứng Java 17**.

### 5.1. Ví dụ đọc stack trace

| Thông điệp | Phân tích |
| --- | --- |
| “class file version 61.0, recognizes up to 55.0” | Một class Java 17 đang được nạp trên JVM Java 11 |
| “class file version 65.0, recognizes up to 61.0” | Class Java 21 đang được nạp trên JVM Java 17 |
| “class file version 55.0, recognizes up to 61.0” | **Không** phải phiên bản quá mới; nếu lỗi xảy ra cần xem nguyên văn nguyên nhân khác |
| “Unsupported major.minor version 52.0” trên JVM cũ | Class Java 8 có thể đã vượt mức hỗ trợ của JVM đó |

Một JVM Java 21 thông thường có thể nạp class Java 17 thông thường vì 61 thuộc phạm vi hỗ trợ, nhưng không có đảm bảo ứng dụng sẽ chạy đúng nếu còn dependency/config/API/behavior khác biệt.

### 5.2. Trường hợp nâng cao: minor version 65535

Các class được biên dịch dùng **preview features** có thể dùng minor version `65535`, ví dụ `61.65535` với một preview feature ở Java 17. Đây **không tương đương** class Java 17 thông thường `61.0`. Preview class có yêu cầu đặc biệt về phiên bản JVM tương ứng và `--enable-preview`.

Nếu gặp lỗi nói về preview features hoặc minor version `65535`, phải kiểm tra các cờ preview ở **compile và runtime**, không đơn giản sửa `target` hoặc nâng JVM vô điều kiện. Bài thực hành chính **không dùng preview features**.

## 6. So sánh --release với -source và -target

### 6.1. --release: ưu tiên cho build target Java rõ ràng

Trong Maven Compiler Plugin 3.14.1:

~~~xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
</properties>
~~~

Khi dùng `javac` hiện đại hỗ trợ release, lựa chọn này có mục tiêu tương đương với:

~~~bash
javac --release 17 ...
~~~

`--release 17` giới hạn **cú pháp ngôn ngữ, định dạng class file và API Java/JDK chuẩn** theo release 17. Điều này quan trọng khi dùng JDK 21 để build sản phẩm phải chạy trên Java 17: nếu source tham chiếu API tiêu chuẩn chỉ có ở Java 21, compiler có thể phát hiện và chặn ngay tại build.

Đây là lý do các hướng dẫn Maven hiện đại khuyến nghị `maven.compiler.release`.

### 6.2. -source và -target: chưa đủ kiểm tra API cũ

Dự án cũ có thể khai:

~~~xml
<properties>
    <maven.compiler.source>17</maven.compiler.source>
    <maven.compiler.target>17</maven.compiler.target>
</properties>
~~~

`source` quy định ngữ pháp được chấp nhận; `target` quy định định dạng class file. Nhưng nếu build với **JDK mới hơn**, chỉ dùng `source`/`target` **không mặc nhiên chặn** mọi API Java chuẩn được giới thiệu sau version target.

Ví dụ ý tưởng (cần build bằng JDK 21 để quan sát): mã gọi API chỉ có từ Java 21 có thể biên dịch được với `-source 17 -target 17` nếu compiler nhìn thấy JDK 21 APIs; sau đó runtime Java 17 có thể lỗi **`NoSuchMethodError`** hoặc **`NoClassDefFoundError`**, thay vì `UnsupportedClassVersionError`. Dùng `--release 17` giúp phát hiện việc dùng API nền tảng quá mới ngay lúc compile.

**Không** cố truyền đồng thời `--release` và `-source/-target` trực tiếp cho cùng một lời gọi javac; JDK javac có quy tắc không cho phối hợp các lựa chọn mâu thuẫn. Trong POM hãy chọn một cấu hình thống nhất; với plugin/JDK hiện đại nên ưu tiên release.

### 6.3. --release không chọn JDK dùng để build

Khai `maven.compiler.release=17` **không tự cài JDK 17**, không đổi `JAVA_HOME` và không tự chọn javac 17. Nếu javac thực tế là JDK 11, `--release 17` vẫn không hợp lệ.

Ngược lại, nếu compiler là JDK 21, `--release 17` có thể tạo class major 61. Lúc triển khai, Java 17 trở lên (nếu dependencies tương thích) có thể chạy sản phẩm, dù **compiler thực tế là JDK 21**.

### 6.4. --release không kiểm soát mọi third-party dependency

`--release 17` giới hạn APIs của **nền tảng Java**, nhưng không tự chứng minh tất cả dependency JAR bên thứ ba cũng được biên dịch cho Java 17. Một JAR bên ngoài chứa major 65 có thể gây lỗi khi runtime Java 17 nạp nó.

Do vậy, chính sách tương thích cần kiểm tra cả:

- Application classes sinh từ source.
- Test classes nếu test dùng JVM khác.
- Dependencies được đưa vào runtime classpath/distribution.
- Các classes do annotation processor/code generator hoặc packaging plugin sinh ra.
- Nền tảng runtime thật (container, server, native launcher).

## 7. Dự án thực hành Java 17 có thể chạy

Ta tạo ứng dụng Maven `bytecode-demo`, dùng một **Java record** để bảo đảm source thật sự yêu cầu Java 16+ và chọn target **Java 17**. JUnit Jupiter 5 kiểm tra kết quả. Maven JAR Plugin ghi `Main-Class` để chạy trực tiếp bằng `java -jar`; mã chính chỉ dùng API JDK nên không cần external runtime dependency.

### 7.1. Cấu trúc dự án

~~~text
bytecode-demo/
├── pom.xml
└── src/
    ├── main/
    │   └── java/vn/example/bytecode/
    │       ├── Greeting.java
    │       └── App.java
    └── test/
        └── java/vn/example/bytecode/
            └── AppTest.java
~~~

Mọi command Maven dưới đây chạy từ thư mục `bytecode-demo` trừ khi ghi khác. Cần Maven 3.9.x, JDK 17+ và kết nối repository để tải JUnit/plugin nếu chưa cache.

### 7.2. pom.xml hoàn chỉnh

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>vn.example</groupId>
    <artifactId>bytecode-demo</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
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
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.1</version>
            </plugin>

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.5.4</version>
            </plugin>

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-jar-plugin</artifactId>
                <version>3.4.2</version>
                <configuration>
                    <archive>
                        <manifest>
                            <mainClass>vn.example.bytecode.App</mainClass>
                        </manifest>
                    </archive>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Điểm quan trọng:

- Project version là `1.0.0`, **không phải Java target version**.
- `maven.compiler.release=17` khiến Compiler Plugin truyền mức biên dịch tương ứng cho cả main/test theo cấu hình thông thường.
- Compiler Plugin `3.14.1` được ghim tường minh, không phụ thuộc bản plugin được chọn ngầm bởi installation.
- JUnit Jupiter `5.11.4` chỉ ở scope `test`; Surefire `3.5.4` thực thi test.
- JAR Plugin thêm `Main-Class`; **không tạo fat JAR** và không cần fat JAR vì mã chính không dùng thư viện bên ngoài.
- POM không khai Maven Toolchains, forked compiler hay profile override, nên với cấu hình mặc định compiler là JDK gắn với Maven. Nếu dự án thật có những cấu hình đó, cần kiểm tra riêng.

### 7.3. Java record: Greeting.java

Tạo `src/main/java/vn/example/bytecode/Greeting.java`:

~~~java
package vn.example.bytecode;

public record Greeting(String subject, int release) {
    public String render() {
        return "Hello, " + subject.trim() + " | release=" + release;
    }
}
~~~

`record` là tính năng Java đã chính thức có trước Java 17. Đây là mã Java 17 hợp lệ, không cần preview flags. Nó khiến người học dễ nhận ra **hạ target xuống Java 11 mà giữ nguyên source không phải một lựa chọn hợp lệ**.

### 7.4. Lớp main: App.java

Tạo `src/main/java/vn/example/bytecode/App.java`:

~~~java
package vn.example.bytecode;

public final class App {
    private App() {
    }

    public static String message() {
        return new Greeting("Maven", 17).render();
    }

    public static void main(String[] args) {
        System.out.println(message());
    }
}
~~~

Stdout **chính xác của main**:

~~~text
Hello, Maven | release=17
~~~

Lưu ý `release=17` trong stdout ở đây là giá trị số **do code truyền vào constructor**, không phải cách JVM tự đọc class-file version. Ta sẽ dùng `javap` để kiểm tra bytecode thật.

### 7.5. JUnit test: AppTest.java

Tạo `src/test/java/vn/example/bytecode/AppTest.java`:

~~~java
package vn.example.bytecode;

import static org.junit.jupiter.api.Assertions.assertEquals;
import org.junit.jupiter.api.Test;

class AppTest {
    @Test
    void mainMessageIsStable() {
        assertEquals("Hello, Maven | release=17", App.message());
    }

    @Test
    void recordTrimsSubject() {
        assertEquals("Hello, Java | release=17",
                new Greeting(" Java ", 17).render());
    }
}
~~~

Với đúng POM và source, Maven Surefire dự kiến chạy **2 tests PASS**, không failure/error. Test đảm bảo chức năng ví dụ nhưng **chưa chứng minh** chương trình chạy được trên mọi JDK hay mọi môi trường deployment; đó là phần kiểm tra bổ sung.

## 8. Build đúng JDK rồi đọc bytecode thật

### 8.1. Kiểm tra công cụ

~~~bash
mvn -version
java -version
javac -version
~~~

Bảo đảm javac được dùng phù hợp mục tiêu Java 17. Nếu Maven đang chạy bằng JDK 17 và không cấu hình toolchain/fork khác, đó là môi trường đơn giản nhất cho bài thực hành.

### 8.2. Chạy Maven lifecycle

~~~bash
mvn clean verify
~~~

Nếu repository truy cập được, build đi qua compile/test/package/verify và tạo:

~~~text
target/
├── classes/
│   └── vn/example/bytecode/
│       ├── Greeting.class
│       └── App.class
├── test-classes/
│   └── vn/example/bytecode/AppTest.class
├── surefire-reports/
└── bytecode-demo-1.0.0.jar
~~~

Các metadata khác có thể tồn tại; bảng chỉ liệt kê file đáng kiểm tra.

Lệnh chạy ứng dụng:

~~~bash
java -jar target/bytecode-demo-1.0.0.jar
~~~

Stdout:

~~~text
Hello, Maven | release=17
~~~

Lệnh `mvn clean verify` tự biên dịch và test nhưng **không tự gọi `App.main`**. Stdout trên chỉ xuất hiện sau lệnh `java -jar`.

### 8.3. Dùng javap để xem class-file major version

~~~bash
javap -verbose -classpath target/classes vn.example.bytecode.Greeting
~~~

Ở phần đầu output tìm:

~~~text
major version: 61
~~~

Class `App.class` cũng phải có major 61 khi được biên dịch bằng cùng release:

~~~bash
javap -verbose -classpath target/classes vn.example.bytecode.App
~~~

Dùng `javap` của một JDK có khả năng đọc class-file format đang kiểm tra. `javap -verbose` in nhiều thông tin constant pool và bytecode; chỉ cần tìm **major version** cho bài này.

### 8.4. Chạy class trực tiếp không qua JAR

~~~bash
java -cp target/classes vn.example.bytecode.App
~~~

Lệnh trên chạy cùng classes trong `target/classes` thay vì JAR. Stdout vẫn là:

~~~text
Hello, Maven | release=17
~~~

Nếu `java -cp target/classes ...` thành công còn `java -jar ...` lỗi, hãy xem JAR có chứa class đúng không, manifest `Main-Class`, artifact có stale output hay command dùng JAR cũ. Không mặc định quy mọi khác biệt đó về JDK version.

## 9. Thí nghiệm lỗi “release version 17 not supported”

**Chỉ thực hiện nếu có một JDK 11 dùng cho môi trường thử nghiệm**, tránh làm hỏng cấu hình JDK đang phục vụ các project khác.

Kịch bản:

1. POM vẫn có `maven.compiler.release=17`.
2. Maven/Compiler Plugin dùng `javac` của JDK **11** (không có toolchain cao hơn).
3. Chạy `mvn clean compile`.

Compiler JDK 11 không hỗ trợ `--release 17`. Build dừng ở **compile phase** với lỗi dạng `release version 17 not supported` hoặc một thông báo target release tương đương. Nó **chưa tạo được một JAR Java 17 hợp lệ** trong lần build sạch.

### 9.1. Trước khi chạy, phải xác nhận JDK thật

~~~bash
mvn -version
javac -version
~~~

Nếu `mvn -version` nói Java 11 nhưng `javac -version` nói 17, vẫn phải xem Maven Compiler Plugin có dùng toolchain/fork/compiler khác không. **Không suy ra compiler đang dùng từ một câu `javac -version` ở shell** khi project có cấu hình riêng.

### 9.2. Không chữa bằng cách hạ release tùy tiện

Nếu đổi POM từ `17` sang `11`, source `Greeting.java` sử dụng Java record sẽ không được compiler chấp nhận theo target Java 11. Lỗi có thể thay thành một lỗi về syntax/feature. Muốn sản phẩm thật sự chạy trên Java 11, phải:

- Thiết kế source không dùng Java feature quá mới (ví dụ thay record bằng class Java 11).
- Tránh APIs nền tảng giới thiệu sau Java 11.
- Bảo đảm dependencies tương thích Java 11.
- Build với compiler hỗ trợ `--release 11`.
- Test runtime **trên Java 11 thật**.

Nếu yêu cầu sản phẩm là Java 17, **giải pháp đúng là chọn JDK compiler đáp ứng**, không hạ target.

## 10. Thí nghiệm lỗi “UnsupportedClassVersionError” trên runtime

Thí nghiệm này chỉ dùng khi bạn có **cả JDK 21 và JDK 17**, và có thể chỉ định rõ runtime nào được dùng. Đừng thực hiện trên hệ thống production.

### 10.1. Tạo bytecode Java 21 một cách có chủ đích

Khi Maven đang dùng compiler **JDK 21**, chạy:

~~~bash
mvn -Dmaven.compiler.release=21 clean verify
~~~

Lệnh truyền user property để **tạm thời** thay release cho build này. JDK 21 có thể biên dịch Java record của ví dụ; các classes sinh ra sẽ có major **65**.

Kiểm tra:

~~~bash
javap -verbose -classpath target/classes vn.example.bytecode.App
~~~

Tìm:

~~~text
major version: 65
~~~

Nếu Maven/parent có cấu hình `<release>` tường minh ưu tiên khác hoặc dùng toolchain compiler không phải JDK 21, phải kiểm tra effective POM/actual javac; lệnh trên chỉ cho kết quả dự kiến với **POM mẫu không override**.

### 10.2. Chạy JAR đó trên một Java 17 thật

Trong một terminal hoặc container dùng **Java 17** làm launcher `java`, chạy:

~~~bash
java -version
java -jar target/bytecode-demo-1.0.0.jar
~~~

Nếu `java -version` thật sự là Java 17, JVM này chỉ hỗ trợ class-file major thông thường đến **61**. Khi nạp `App.class` major **65**, nó phải báo `UnsupportedClassVersionError` dạng:

~~~text
... class file version 65.0 ...
... only recognizes class file versions up to 61.0
~~~

Không nên ghi cứng toàn bộ stack trace vào bài kiểm thử: path, class name, wording và nguồn gọi tùy JVM. **Major 65 so với tối đa 61** mới là bằng chứng cốt lõi.

### 10.3. Cách khôi phục

Trở về Maven/JDK hỗ trợ `--release 17` và chạy:

~~~bash
mvn clean verify
javap -verbose -classpath target/classes vn.example.bytecode.App
~~~

Khi không truyền `-Dmaven.compiler.release=21` nữa, POM trở lại yêu cầu Java 17. Major phải về **61**. Chạy JAR bằng Java 17:

~~~bash
java -jar target/bytecode-demo-1.0.0.jar
~~~

Stdout:

~~~text
Hello, Maven | release=17
~~~

**Tại sao cần `clean`?** Compiler incremental build hoặc file còn lại trong `target` có thể gây nhầm giữa class-file version cũ/mới. Build sạch cô lập lần thử; một JAR từ lần trước không phải kết quả của POM và JDK vừa đổi.

## 11. Quy trình chẩn đoán trong 7 bước

Khi nhận log lỗi từ developer, IDE hoặc CI, đi theo thứ tự sau.

### Bước 1 — Xác định lỗi thuộc giai đoạn nào

| Dấu hiệu | Giai đoạn nhiều khả năng |
| --- | --- |
| `invalid target release: 17` | Java compilation |
| `release version 17 not supported` | Java compilation |
| `bad class file: ... has wrong version 65.0, should be 61.0` | Compiler không đọc được một dependency/class quá mới |
| `UnsupportedClassVersionError` | JVM/class loader nạp một class không hỗ trợ |
| `NoSuchMethodError`/`NoClassDefFoundError` | Có thể là API/classpath incompatibility, không nhất thiết major version |
| `invalid source release` | Mức source syntax không được compiler chấp nhận |
| `Source option ... is no longer supported` | Compiler mới không còn hỗ trợ source/target cũ, không giống compiler quá cũ cho target mới |

Đầu tiên đọc **stack trace/goal**: `maven-compiler-plugin:compile`, `surefire:test`, `exec:java` hay khởi động server. Không sửa POM trước khi phân loại.

### Bước 2 — Ghi lại phiên bản công cụ từ đúng môi trường lỗi

~~~bash
mvn -version
java -version
javac -version
~~~

Ghi nhận Maven version, Java runtime đang chạy Maven, JDK vendor và path nếu được in. Trên Unix-like:

~~~bash
printf '%s\n' "$JAVA_HOME"
command -v java
command -v javac
~~~

Trên Windows PowerShell:

~~~powershell
$env:JAVA_HOME
where.exe java
where.exe javac
~~~

**PATH và JAVA_HOME có thể trỏ tới các JDK khác nhau.** Trong IDE có thể có “Project SDK”, “Maven runner JRE”, “Gradle JVM”, “Run configuration JRE” và “terminal Java” riêng; chỉ sửa một ô IDE không bảo đảm toàn bộ chúng thay đổi.

### Bước 3 — Xác định compiler thực tế

Nếu POM không có toolchains/fork, mặc định Compiler Plugin thường dùng compiler gắn với JDK chạy Maven. Nhưng nếu có:

- `maven-toolchains-plugin`.
- Compiler Plugin `jdkToolchain`.
- Compiler Plugin `fork=true` với `executable`.
- Một compiler implementation khác.
- Build plugin sinh mã hoặc chạy một JVM/compiler riêng.

thì **JDK của Maven và javac thực tế có thể khác**. Hãy xem effective POM, cấu hình toolchains và log compiler; khi cần mới dùng `mvn -X` với chú ý bí mật.

### Bước 4 — Xem mức Java được yêu cầu

~~~bash
mvn help:effective-pom
mvn help:evaluate -Dexpression=maven.compiler.release -q -DforceStdout
~~~

Nếu mô-đun nằm trong reactor, chọn đúng project (ví dụ trong reactor có artifactId `app`):

~~~bash
mvn -pl :app help:effective-pom
~~~

Không dùng selector `:app` trong dự án `bytecode-demo` đơn của mục 7 vì mẫu đó **không có module tên app**. Trong project nhiều module, parent `pluginManagement` hoặc profile có thể xác định `release` mà POM con không ghi trực tiếp.

### Bước 5 — Nếu đã biên dịch, kiểm tra class thật

~~~bash
javap -verbose -classpath target/classes vn.example.bytecode.App
~~~

Tìm `major version`. Nếu cần kiểm tra một JAR thay vì thư mục classes, dùng đúng classpath:

~~~bash
javap -verbose -classpath target/bytecode-demo-1.0.0.jar vn.example.bytecode.App
~~~

Đừng kết luận từ file `pom.xml` một mình rằng JAR cũ trên server chứa bytecode đúng mức; có thể app đã được build ở runner khác hoặc artifact chưa được deploy.

### Bước 6 — So sánh với Java runtime thực tế

Chạy `java -version` ở **đúng nơi khởi động ứng dụng**. Nếu container chạy image Java 11, Java 17 trên laptop không liên quan. Kiểm tra Docker image base, entrypoint, service unit, IDE run configuration, k8s deployment hoặc server/container JVM theo môi trường đang dùng.

Nếu runtime thấp hơn class-file major được yêu cầu, hoặc dependency đòi Java cao hơn, phải thay build target/dependency hoặc runtime theo chính sách.

### Bước 7 — Xác minh sau sửa

~~~bash
mvn clean verify
java -jar target/bytecode-demo-1.0.0.jar
~~~

Chạy thêm `javap` và smoke test bằng runtime tối thiểu được hỗ trợ, không chỉ bằng JDK build. Ở CI, lưu Maven/JDK versions, release target, class-file major, dependency tree, test results và checksum artifact để đối chiếu.

## 12. Maven Toolchains: khi JDK chạy Maven khác JDK dùng compile

**Maven Toolchains** cho phép một số plugin lựa chọn công cụ JDK đã đăng ký thay vì bắt buộc dùng JDK khởi động Maven. Đây là phương án được khuyến nghị khi tổ chức cần build theo một JDK cụ thể trong khi Maven chạy trên JDK khác.

Với Maven Compiler Plugin, có thể cấu hình **jdkToolchain cho riêng plugin**:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-compiler-plugin</artifactId>
    <version>3.14.1</version>
    <configuration>
        <jdkToolchain>
            <version>17</version>
        </jdkToolchain>
        <release>17</release>
    </configuration>
</plugin>
~~~

Đây là **trích đoạn**, không phải POM hoàn chỉnh. Nó chỉ có thể hoạt động khi có **toolchain JDK 17 phù hợp** được khai báo và Maven tìm được nó (ví dụ qua `~/.m2/toolchains.xml` của người chạy). `<version>17</version>` ở `jdkToolchain` là **điều kiện chọn JDK**, còn `<release>17</release>` là **mức code/bytecode/API mục tiêu**. Chúng là hai quyết định khác nhau.

### 12.1. Toolchains có thể làm gì?

- Máy chạy Maven bằng JDK 21 nhưng compiler chọn JDK 17 để tạo class major 61.
- Máy chạy Maven bằng JDK 11 nhưng compiler chọn một JDK 17 đã được cài và khai trong toolchains.
- CI ghi rõ JDK nào chịu trách nhiệm build artifact.

### 12.2. Toolchains không giải quyết điều gì?

- Không tự **cài JDK** hoặc tạo một đường dẫn JDK hợp lệ nếu máy chưa có.
- Không bảo đảm **mọi plugin** đều dùng cùng toolchain. Plugin cần hỗ trợ toolchains.
- Không tự chọn JVM **chạy production application**.
- Không thay thế `--release` khi bạn muốn JDK mới tạo bytecode/API của release thấp hơn.

Plugin Compiler cũng có thể cấu hình fork/executable để gọi một `javac` riêng, nhưng nếu dùng path cứng phụ thuộc máy thì build khó portable. Với hệ thống nhiều developer, ưu tiên **Toolchains + CI JDK policy + build logs** thay cho đường dẫn tuyệt đối đặt trực tiếp trong source-controlled POM.

### 12.3. Test JVM cũng có thể khác

Maven Surefire/Failsafe có hỗ trợ chọn JDK toolchain cho test JVM trong những cấu hình phù hợp. Nếu compiler dùng JDK 21 và tạo classes major 65 nhưng Surefire chạy test JVM 17, **test có thể bị `UnsupportedClassVersionError`**, kể cả khi Maven chính đang chạy trên JDK 21.

Với dự án cần hỗ trợ Java 17, nên chạy ít nhất một **test/smoke test trên Java 17 thật**; đừng chỉ thấy test PASS trên Java 21 rồi khẳng định JVM 17 chắc chắn chạy được.

## 13. Khi class của ứng dụng đúng nhưng một dependency lại quá mới

Giả sử `App.class` có major 61 (Java 17), nhưng ứng dụng cần một library trong runtime JAR có class major 65 (Java 21). Trên Java 17, lúc class loader nạp library ấy, lỗi có thể xuất hiện ngay dù application class tương thích.

### 13.1. Cách xác minh có căn cứ

1. Đọc **tên class** được nêu trong `UnsupportedClassVersionError`.
2. Xác định nó nằm ở JAR nào bằng dependency tree, thông tin lỗi, classpath hoặc nội dung archive.
3. Đọc release notes và **minimum Java version** của dependency được chọn.
4. Dùng `javap -verbose -classpath` với JAR và class đó bằng JDK đủ mới để kiểm tra major.
5. So sánh với runtime JVM mục tiêu.
6. Chọn một dependency version tương thích hoặc nâng runtime nếu chính sách cho phép.

Xem dependency graph:

~~~bash
mvn dependency:tree
~~~

Lưu ý `dependency:tree` cho version/scope Maven đã giải quyết, **không in class-file major version của từng JAR**. Một dependency có scope runtime vẫn có thể đưa bytecode Java 21 vào ứng dụng Java 17.

### 13.2. Class file version khác lỗi thiếu API

| Hiện tượng | Khả năng |
| --- | --- |
| `UnsupportedClassVersionError` | JVM không hỗ trợ định dạng class đang nạp |
| `NoSuchMethodError` | Binary API/linkage mismatch, có thể compile với API khác runtime |
| `NoClassDefFoundError` | Class thiếu khi load/initialize hoặc nguyên nhân linkage trước đó |
| `ClassNotFoundException` | Class loader không tìm thấy class được yêu cầu |
| `bad class file ... wrong version` trong javac | Compiler đang đọc class dependency quá mới |
| `NoSuchFieldError` | Mã liên kết với field không tồn tại trong class được load |

**Không sửa mọi lỗi bằng cách nâng JDK.** Nếu một class bị thiếu khỏi runtime classpath hoặc artifact version xung đột, nâng JDK chưa chắc giải quyết. Phải đọc **tên class, phase, major và classpath thực tế**.

## 14. Cảnh báo về Java 8 và Compiler Plugin hiện đại

Java 8 **không hỗ trợ** option `javac --release`. Tuy nhiên, từ Maven Compiler Plugin **3.13.0** (với compiler `javac` mặc định), cấu hình `release` có cơ chế tương thích: trên JDK 8, plugin có thể chuyển yêu cầu `release=8` thành `source/target=8`.

Điều này **không** có nghĩa một JDK 8 có thể build target Java 17: khi mục tiêu cao hơn khả năng compiler, nó vẫn không có compiler/API cần thiết.

Bài dùng Compiler Plugin 3.14.1 và target Java 17; không cần profile có điều kiện dành riêng cho JDK 8. Nếu bảo trì hệ thống Java 8, hãy đọc tài liệu **đúng phiên bản** Compiler Plugin và test trên JDK/JRE mục tiêu, thay vì copy mọi option từ POM Java 17.

## 15. CI, IDE và container: ba nơi thường lệch JDK

### 15.1. CI runner

Một pipeline có thể có JDK 17 cài sẵn, nhưng một job lại đặt `JAVA_HOME` sang JDK 11 hoặc dùng image Maven với Java 11. Dấu hiệu là `mvn -version` trong job có Java 11 dù build artifact trước trên laptop bằng Java 17.

**Cách xử lý:** chọn runner/image JDK đã được phê duyệt, xuất version vào log build, và không dựa vào thứ tự tool installation trên PATH. Nếu sử dụng Maven Wrapper, wrapper giúp ghim phiên bản **Maven**, không tự tải/ghim JDK nếu không có workflow riêng.

### 15.2. IDE

IDE thường có các thiết lập độc lập:

- Project SDK/Java language level.
- Java compiler bytecode target.
- Maven runner JRE/JDK.
- JDK/JVM của test run configuration.
- JDK/JVM của ứng dụng khi bấm Run.
- JDK tích hợp mà terminal IDE nhìn thấy.

Do đó một dự án **compile trong IDE nhưng fail khi `mvn`**, hoặc build bằng Maven PASS nhưng Run trong IDE lỗi version, không nhất thiết do POM. Hãy đối chiếu **JDK thực tế của lệnh đang thất bại**; không chỉ nhìn Project SDK.

### 15.3. Docker/container

Nếu CI build bằng Java 21 với target Java 21 nhưng Docker runtime base image chứa Java 17, artifact có thể build/test PASS trong stage builder rồi fail ở stage chạy.

Mô hình cần kiểm soát:

~~~text
builder: JDK 21 + --release 17 → classes major 61
runtime: Java 17                → hỗ trợ major 61

builder: JDK 21 + --release 21 → classes major 65
runtime: Java 17               → không hỗ trợ major 65
~~~

Đây là **sơ đồ**, không phải Dockerfile runnable. Với multi-stage image, phải kiểm tra base image/tag/digest của **stage runtime**, không chỉ stage build. Thư viện được copy vào image cũng phải tương thích.

### 15.4. Maven đa mô-đun

Trong reactor, parent có thể quản lý `<maven.compiler.release>17</maven.compiler.release>`, nhưng child lại có plugin config hoặc profile override thành `21`. Khi chỉ một module bị `UnsupportedClassVersionError`, hãy đọc **effective POM của module đó** và class-file major của JAR nó tạo ra.

Không chỉ kiểm tra effective POM của aggregator và khẳng định tất cả child đã dùng cùng release. Nếu project có module Java 11 và Java 17 hợp lệ cùng reactor, cần **tài liệu hợp đồng runtime cho từng module**.

## 16. Không dùng mẹo chữa lỗi sai bản chất

### Sai cách 1: hạ target 17 xuống 11 khi chưa review source

Tác hại: Java record hoặc APIs mới có thể không compile; nếu dùng `source/target` thay vì `release`, class có thể mang bytecode thấp nhưng vẫn liên kết APIs mới rồi lỗi runtime.

**Đúng:** xác định runtime tối thiểu trước; nếu thật sự phải hỗ trợ Java 11 thì sửa code/dependency cho Java 11, dùng compiler phù hợp và test Java 11.

### Sai cách 2: thấy `java -version` là 17 thì kết luận Maven cũng dùng 17

**Sai:** `JAVA_HOME`, PATH, IDE/CI runner và toolchains có thể khiến Maven/Compiler Plugin chọn Java khác. **Đúng:** `mvn -version` + effective toolchain/compiler selection.

### Sai cách 3: đổi `project.version` của Maven artifact

`<version>1.0.0</version>` của project không chọn Java target. Đổi artifact version không chữa `invalid target release` hay `UnsupportedClassVersionError`.

### Sai cách 4: chỉ kiểm tra `App.class`, bỏ qua dependencies

`App.class` major 61 không chứng minh mọi JAR được nạp đều Java 17. Dependency có thể major 65. **Đúng:** kiểm tra class được nêu **trong lỗi** và artifact chứa nó.

### Sai cách 5: build lại trên server production

Build lại cùng source trên máy server với JDK khác có thể tạo artifact khác và làm mất tính truy vết. **Đúng:** build một artifact trên CI, kiểm tra compatibility, lưu checksum và triển khai **chính artifact đó**.

### Sai cách 6: chỉ chạy `mvn compile`, không test runtime tối thiểu

Compile thành công không có nghĩa `java -jar` trên JVM mục tiêu sẽ chạy được. **Đúng:** chạy test, package và smoke test trên JVM thấp nhất được hỗ trợ.

### Sai cách 7: nhìn file JAR cũ sau khi build lỗi

`mvn compile` không tạo JAR mới; khi lần build sau fail, `target` có thể còn kết quả của lần trước nếu không clean. **Đúng:** dùng `mvn clean verify` cho phép đo có căn cứ và kiểm tra timestamp/checksum artifact.

### Sai cách 8: nghĩ `-U` hoặc xóa ~/.m2 sẽ sửa JDK

`-U` ảnh hưởng việc Maven kiểm tra cập nhật metadata/SNAPSHOT, không đổi JDK compiler; xóa cache dependency chỉ làm Maven tải lại artifact. **Đúng:** phân loại lỗi JDK/bytecode trước, sửa đúng toolchain/runtime.

## 17. Bộ kiểm tra trước khi mở issue hoặc xin hỗ trợ

Khi báo lỗi cho đồng đội, ghi dữ liệu tối thiểu:

~~~text
Maven goal/phase thất bại:
  compile / test / package / java -jar / service startup

Maven runtime:
  kết quả mvn -version

Compiler thực tế:
  default JDK / toolchain / forked javac

Java target:
  maven.compiler.release hoặc effective compiler configuration

Ứng dụng runtime:
  java -version ở đúng nơi chạy

Class liên quan:
  tên class trong lỗi + JAR chứa nó

Bytecode:
  major version từ javap

Dependency:
  tọa độ/version/scope của JAR gây lỗi, nếu là thư viện

Kết quả sau khi sửa:
  clean verify, test count, smoke test, artifact checksum
~~~

Không công khai secrets, private repository URLs, tokens hay nội dung đầy đủ của Maven debug logs nếu chưa rà soát.

### Quy trình quyết định nhanh

~~~text
Có lỗi "invalid target release" hoặc "release ... not supported"?
    |
    +-- Có --> Kiểm tra javac thực tế so với release yêu cầu
    |            |
    |            +-- javac cũ? -> đổi JDK/compiler/toolchain
    |            +-- không cũ? -> xem POM/profile, flags và plugin
    |
    +-- Không --> Có UnsupportedClassVersionError?
                 |
                 +-- Có --> Đọc class major + runtime max
                 |           |
                 |           +-- major cao hơn? -> đổi runtime,
                 |           |   build target hoặc dependency
                 |           +-- major không cao hơn? -> đọc kỹ
                 |               minor/preview và stack trace
                 |
                 +-- Không --> Chẩn đoán lỗi classpath/API/
                             test/plugin theo thông điệp thật
~~~

Dùng lưu đồ này để **chọn lớp nguyên nhân**, không dùng nó thay cho log và kiểm chứng thực tế.

## 18. Bài tập thực hành

### Bài A — Phân biệt bốn phiên bản

Giả sử `mvn -version` báo Java 11, `javac -version` trong terminal báo 17, POM dùng `maven.compiler.release=17`, runtime server là Java 11. Hãy nêu **các biến còn phải kiểm tra** trước khi kết luận compiler nào chạy, và phân biệt lỗi có thể xảy ra lúc build với lỗi có thể xảy ra lúc runtime.

### Bài B — Class-file major

Không tra cứu trong lúc trả lời, ghép Java 8/11/17/21 với major 52/55/61/65. Từ log `class file version 65.0, recognizes up to 61.0`, giải thích vì sao khả năng cao JAR Java 21 đang chạy trên Java 17.

### Bài C — Build bản đúng Java 17

Tạo đúng project `bytecode-demo` ở mục 7. Chạy `mvn clean verify`. Xác nhận hai test PASS, JAR được tạo, `java -jar` in `Hello, Maven | release=17` và `javap` cho class major 61.

### Bài D — Thử compiler JDK 11

Nếu có JDK 11 trong môi trường học, đặt Maven/compiler thực sự dùng JDK 11 nhưng giữ POM release 17. Dự đoán kết quả compile. Giải thích vì sao việc đổi `release` thành 11 **không tự chữa** source dùng record.

### Bài E — Tạo bytecode Java 21

Nếu có JDK 21, chạy `mvn -Dmaven.compiler.release=21 clean verify`. Kiểm tra major 65. Dùng Java 17 thật để chạy file JAR vừa tạo và giải thích lỗi; sau đó quay lại `mvn clean verify` target 17.

### Bài F — --release và source/target

Giải thích tại sao JDK 21 chạy `--release 17` là lựa chọn tốt cho sản phẩm Java 17, trong khi `-source 17 -target 17` chưa đủ giới hạn việc gọi API nền tảng của JDK 21.

### Bài G — Dependency quá mới

Giả sử `App.class` là 61.0 nhưng stack trace nêu class từ thư viện có 65.0. Nêu ba cách xác minh dependency/JAR chứa class đó, và hai hướng sửa hợp lý theo hợp đồng Java 17.

### Bài H — CI và Toolchains

Thiết kế pipeline ghi lại `mvn -version`, compiler/toolchain, effective release, `javap` class major, test result và runtime smoke test. Vì sao có toolchain mà vẫn phải kiểm tra Java runtime ở bước triển khai?

### Bài I — IDE khác terminal

IDE chạy app trên Java 21, terminal Maven chạy bằng Java 11, production Java 17. Lập bảng cài đặt cần kiểm tra: Maven runner JDK, Project SDK, application run JDK, `JAVA_HOME`, PATH và compiler release.

### Bài J — Lỗi không liên quan bytecode

Một ứng dụng build major 61, runtime Java 17 cũng hỗ trợ 61, nhưng lỗi `NoClassDefFoundError`. Vì sao không nên ngay lập tức nâng Java 21? Hãy điều tra runtime classpath, JAR dependency, phiên bản và class loader.

## 19. Checklist kết luận

Trước khi coi sự cố Java version đã xử lý xong:

- [ ] Xác định lỗi ở **compile**, **test JVM**, **runtime application** hay plugin/class loader.
- [ ] Đọc `mvn -version` trong đúng terminal/CI job; không thay bằng mỗi `java -version`.
- [ ] Kiểm tra compiler thực tế: default, Toolchains hoặc forked javac.
- [ ] Đọc `maven.compiler.release` và effective POM của đúng module.
- [ ] Chọn `--release` nhất quán với runtime tối thiểu và API của source.
- [ ] Kiểm tra major của class bằng `javap -verbose`.
- [ ] Với runtime failure, đọc **tên class bị lỗi**, có thể thuộc dependency chứ không phải app.
- [ ] Kiểm tra bytecode/API của mọi dependency được triển khai.
- [ ] Chạy `mvn clean verify` và kiểm tra số test thật sự chạy.
- [ ] Smoke test trên JVM tối thiểu được hỗ trợ, không chỉ trên JDK build.
- [ ] Không hạ target tùy tiện, không dùng stale JAR và không build lại tùy máy trong production.
- [ ] Lưu commit, Maven/JDK/toolchain versions, class major và artifact checksum để truy vết.

**Ghi nhớ:** `invalid target release` thường có nghĩa **compiler chưa đủ mới cho Java target**, còn `UnsupportedClassVersionError` có nghĩa **JVM đang nạp class không hỗ trợ được**. Chẩn đoán chính xác đòi nhìn **JDK chạy Maven, javac thật, release target, bytecode major và JVM runtime** như những thứ **có thể khác nhau**.

## 20. Tài liệu chính thức

- [Apache Maven — Guide to Targeting a Java Version](https://maven.apache.org/guides/mini/guide-java-target.html): `--release` so với `source/target` và giới hạn API của release mục tiêu.
- [Apache Maven Compiler Plugin 3.14.1 — Setting the --release of the Java Compiler](https://maven.apache.org/components/plugins-archives/maven-compiler-plugin-3.14.1/examples/set-compiler-release.html): `maven.compiler.release`, tham số `release` và trường hợp JDK 8.
- [Apache Maven Compiler Plugin — Setting -source and -target](https://maven.apache.org/components/plugins/maven-compiler-plugin/examples/set-compiler-source-and-target.html): giới hạn của `source/target` và khuyến nghị dùng release.
- [Apache Maven — Guide to Using Toolchains](https://maven.apache.org/guides/mini/guide-using-toolchains.html): chọn JDK toolchain khác với JDK chạy Maven.
- [Maven Surefire Plugin — Using Maven Toolchains](https://maven.apache.org/surefire/maven-surefire-plugin/examples/toolchains): lựa chọn test JVM khác và yêu cầu plugin tương ứng.
- [Java Virtual Machine Specification — Class File Format](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-4.html): `major_version/minor_version`, bảng Java 8/11/17/21 và preview class files.
- [Java SE 21 API — UnsupportedClassVersionError](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/UnsupportedClassVersionError.html): định nghĩa lỗi JVM gặp định dạng class không được hỗ trợ.
