# Dùng JDK khác khi build: kiểm soát phiên bản Java trong toàn bộ build

Bài học thuộc nhóm **Anti-pattern tooling**. Dùng một JDK khác nhau giữa máy developer, IDE, Maven/Gradle, CI và môi trường chạy ứng dụng không tự động là sai. Nó trở thành anti-pattern khi sự khác biệt xảy ra ngoài ý muốn, không được khai báo trong build và không được kiểm thử. Khi đó cùng một commit có thể biên dịch bằng API khác nhau, tạo bytecode khác nhau, chạy test trên runtime khác nhau hoặc chỉ build thành công trên máy của một người.

Cần phân biệt bốn phiên bản Java trong một quy trình:

1. **Build JVM:** JDK/JRE đang chạy Maven hoặc Gradle và các plugin của build tool.
2. **Compiler/test toolchain:** JDK cung cấp `javac`, `javadoc` và Java launcher cho test/task.
3. **Target release:** phiên bản Java mà source được phép dùng API và class file phải tương thích.
4. **Production runtime:** JRE/JDK thực sự chạy ứng dụng sau khi deploy.

Bốn giá trị này có thể khác nhau một cách có chủ đích. Ví dụ Maven/Gradle chạy trên JDK 24, compiler dùng JDK 24 với `--release 17`, còn ứng dụng được kiểm thử và triển khai trên Java 17. Điều quan trọng là mỗi vai trò phải được cấu hình, ghi nhận và kiểm thử rõ ràng.

Bài học dùng Java 17 làm target minh họa. Phần kiểm thử thực tế được chạy trên Windows 11 với Zulu/OpenJDK 24.0.2, Maven 3.9.12 và Gradle 9.2.1.

## 1. Anti-pattern là gì?

Một dự án có thể gặp các tình huống sau:

- Developer A dùng JDK 17, Developer B dùng JDK 21.
- IDE biên dịch bằng Project SDK 21 nhưng terminal chạy Maven bằng JDK 17.
- Maven chạy trên JDK 24, compiler plugin dùng JDK 17, còn test fork bằng JDK 21 mà không có chủ đích.
- Gradle daemon dùng JDK 21 nhưng project chưa khai báo toolchain, nên compiler tự dùng JDK đang chạy Gradle.
- CI dùng JDK 17 nhưng máy local dùng JDK 24; source vô tình gọi API chỉ có từ Java 19.
- Maven Wrapper hoặc Gradle Wrapper đã được commit, nhưng nhóm nghĩ wrapper cũng cố định JDK. Wrapper chỉ cố định phiên bản build tool.
- Máy có nhiều JDK trong `PATH`; `java` và `javac` được resolve từ hai thư mục khác nhau.
- `JAVA_HOME` trỏ tới một JDK nhưng IDE hoặc Gradle Tooling API lại khởi chạy build bằng JDK khác.

Hậu quả thường không xuất hiện ngay. Build có thể xanh ở local nhưng đỏ trên CI, test có thể qua trên JDK mới nhưng lỗi trên runtime tối thiểu, hoặc binary phát hành có bytecode/API cao hơn cam kết hỗ trợ.

**Anti-pattern cốt lõi là để môi trường tự chọn JDK một cách ngẫu nhiên.** Khai báo một JDK toolchain khác với JDK chạy build là thiết kế hợp lệ nếu có lý do và kiểm thử phù hợp.

## 2. Phân biệt bốn phiên bản Java

| Thành phần | Câu hỏi cần trả lời | Cách kiểm soát |
|---|---|---|
| Build JVM | Maven/Gradle đang chạy trên JDK nào? | `JAVA_HOME`, IDE runner, Gradle daemon JVM criteria |
| Compiler toolchain | `javac`/`javadoc` nào được gọi? | Maven Toolchains, Gradle Java Toolchains |
| Target release | Source được dùng API và tạo class file cho Java nào? | `javac --release`, Maven `maven.compiler.release`, Gradle `options.release` |
| Runtime | Ứng dụng và test chạy trên JDK nào? | Test launcher/toolchain, CI matrix, production image |

Ví dụ một policy hợp lệ:

| Công đoạn | JDK |
|---|---:|
| Chạy Gradle daemon | 17 |
| Biên dịch source | 21 |
| Target API/bytecode | 17 |
| Chạy unit test | 17 |
| Chạy production | 17 |

Ví dụ khác: Maven chạy trên JDK 24, compiler cũng dùng JDK 24, nhưng `--release 17` giới hạn API và bytecode về Java 17. Đây là cách build library hỗ trợ Java 17 từ một máy build mới hơn. Tuy nhiên, vẫn cần chạy test trên Java 17 để kiểm tra runtime thực tế.

## 3. Khi nào dùng JDK khác nhau là hợp lý?

Dùng nhiều JDK có chủ đích trong các trường hợp:

- Dự án phải hỗ trợ nhiều runtime, ví dụ Java 17 và Java 21.
- JDK mới được dùng làm build JVM vì phiên bản Maven/Gradle hoặc plugin yêu cầu nó, nhưng sản phẩm vẫn hỗ trợ runtime cũ hơn.
- Compiler JDK mới cần dùng một tính năng của compiler, trong khi `--release` giữ API target ở mức thấp hơn.
- Test suite chạy trên nhiều runtime để phát hiện thay đổi hành vi JVM.
- Một task riêng cần JDK khác, ví dụ chạy `javadoc`, `jdeps`, `jlink`, `jpackage`, `jarsigner` hoặc kiểm thử native integration.
- Multi-release JAR có source set riêng cho các phiên bản Java khác nhau.

Mỗi khác biệt cần có mục tiêu cụ thể, cấu hình trong build hoặc CI, và log thể hiện JDK thực tế. Không nên chọn JDK theo thứ tự cài đặt trên máy hoặc theo cấu hình cá nhân không được chia sẻ.

## 4. Vì sao `source`/`target` không giải quyết hết vấn đề?

Các lựa chọn cũ:

~~~text
javac -source 17 -target 17 ...
~~~

`-source` chọn quy tắc cú pháp/ngôn ngữ; `-target` chọn định dạng class file. Khi dùng compiler JDK mới, hai lựa chọn này không tự giới hạn toàn bộ API của platform về phiên bản target.

Ví dụ compiler JDK 24 có thể nhìn thấy `Thread.threadId()`, một API xuất hiện từ Java 19. Nếu chỉ đặt `-source 17 -target 17`, source có thể vẫn tham chiếu API mới rồi biên dịch thành công, nhưng chạy trên Java 17 sẽ lỗi khi liên kết hoặc thực thi.

Với Java 9 trở lên, ưu tiên:

~~~text
javac --release 17 ...
~~~

`--release 17` kết hợp quy tắc ngôn ngữ, class file target và tập API được công bố cho Java 17. Nó không đổi JDK đang chạy `javac`; nó kiểm soát phiên bản platform mà source được biên dịch nhắm tới.

Không kết hợp `--release` với `-source` hoặc `-target` trong cùng lệnh. Chọn một cấu hình target rõ ràng.

## 5. Đọc đúng JDK trên máy

`java -version` chỉ cho biết executable `java` được shell tìm thấy đầu tiên. Nó chưa chắc là JDK mà IDE, Maven compiler hoặc Gradle toolchain đang dùng.

Trên Windows PowerShell:

~~~powershell
$env:JAVA_HOME
Get-Command java, javac
where.exe java
where.exe javac
java -version
javac -version
mvn -version
gradle -version
~~~

Trên Linux/macOS:

~~~sh
printf '%s\n' "$JAVA_HOME"
command -v java
command -v javac
java -version
javac -version
mvn -version
gradle -version
~~~

Trên macOS có thể liệt kê JDK đã cài:

~~~sh
/usr/libexec/java_home -V
/usr/libexec/java_home -v 17
~~~

Để xem JVM properties của process Java được gọi từ shell:

~~~text
java -XshowSettings:properties -version
~~~

Tìm `java.home`, `java.version`, `java.vendor` trong output. Đối với Maven và Gradle, hãy xem chính output `mvn -version` và `gradle -version`; không suy ra JDK build chỉ từ `java -version`.

## 6. `JAVA_HOME` và `PATH` có thể không khớp

`JAVA_HOME` thường được Maven, Gradle và các script Java dùng làm vị trí mặc định của JDK. `PATH` quyết định executable nào được gọi khi nhập `java` hoặc `javac`.

Một máy có thể ở trạng thái:

~~~text
JAVA_HOME = C:\jdks\jdk-17
PATH      = C:\jdks\jdk-24\bin;...
~~~

Khi đó `mvn` có thể chạy trên JDK 17 theo `JAVA_HOME`, trong khi `java -version` lại hiển thị JDK 24 từ `PATH`. Kết quả chẩn đoán tưởng như mâu thuẫn nhưng thực ra hai lệnh đang chọn Java theo hai cơ chế khác nhau.

Để đồng bộ trong một terminal PowerShell:

~~~powershell
$env:JAVA_HOME = 'C:\jdks\jdk-17'
$env:Path = "$env:JAVA_HOME\bin;$env:Path"

java -version
javac -version
mvn -version
gradle -version
~~~

Trong Bash:

~~~sh
export JAVA_HOME=/opt/jdks/jdk-17
export PATH="$JAVA_HOME/bin:$PATH"

java -version
javac -version
mvn -version
gradle -version
~~~

Đây là cấu hình cho process shell hiện tại. Cách đặt biến lâu dài tùy OS, shell và CI. Tránh commit đường dẫn JDK cá nhân vào build script.

## 7. Maven: JDK chạy Maven và JDK biên dịch là hai việc riêng

Maven thông thường khởi chạy trên JDK được chọn bởi `JAVA_HOME` hoặc launcher environment. Nếu không cấu hình toolchain, các plugin có thể sử dụng JDK của Maven process cho những công việc như compile, Javadoc, test hoặc signing.

Kiểm tra JVM chạy Maven:

~~~text
mvn -version
~~~

Ví dụ output:

~~~text
Apache Maven 3.9.12
Java version: 24.0.2, vendor: Azul Systems, Inc.
OS name: "windows 11", arch: "amd64"
~~~

Output này cho biết Maven process chạy trên Java 24. Nó không chứng minh rằng project đang tạo bytecode Java 24; compiler có thể được cấu hình `--release 17` hoặc dùng JDK toolchain khác.

Maven Wrapper (`mvnw`, `mvnw.cmd`) pin phiên bản Maven distribution. Nó không tự pin JDK chạy Maven. CI vẫn phải cài/chọn JDK phù hợp.

## 8. Maven: đặt target release bằng Compiler Plugin

Với Java library hỗ trợ Java 17, khai báo release rõ ràng trong POM:

~~~xml
<properties>
  <maven.compiler.release>17</maven.compiler.release>
  <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
</properties>

<build>
  <plugins>
    <plugin>
      <groupId>org.apache.maven.plugins</groupId>
      <artifactId>maven-compiler-plugin</artifactId>
      <version>3.13.0</version>
      <configuration>
        <release>17</release>
        <encoding>UTF-8</encoding>
      </configuration>
    </plugin>
  </plugins>
</build>
~~~

Có thể giữ `maven.compiler.release` ở properties để các module kế thừa cùng policy. Nếu cấu hình trực tiếp `<release>17</release>` trong plugin thì hãy tránh đặt một giá trị khác ở nơi khác.

Chạy:

~~~text
mvn -B -ntp clean verify
~~~

Compiler Plugin sẽ truyền release target tới compiler. Nếu Maven đang chạy trên JDK 24, compiler mặc định vẫn có thể là compiler của JDK 24; output phải được giới hạn về Java 17 nhờ `--release`.

## 9. Maven Toolchains: chọn JDK compile riêng

Khi cần compiler/Javadoc/test chạy bằng một JDK khác với JVM chạy Maven, dùng Maven Toolchains.

Có hai phần:

1. POM yêu cầu một toolchain.
2. Máy build cung cấp đường dẫn JDK trong `toolchains.xml`.

Ví dụ cấu hình trong `pom.xml`:

~~~xml
<build>
  <plugins>
    <plugin>
      <groupId>org.apache.maven.plugins</groupId>
      <artifactId>maven-compiler-plugin</artifactId>
      <version>3.13.0</version>
      <configuration>
        <release>17</release>
      </configuration>
    </plugin>

    <plugin>
      <groupId>org.apache.maven.plugins</groupId>
      <artifactId>maven-toolchains-plugin</artifactId>
      <version>3.3.0</version>
      <executions>
        <execution>
          <goals>
            <goal>toolchain</goal>
          </goals>
        </execution>
      </executions>
      <configuration>
        <toolchains>
          <jdk>
            <version>[17,18)</version>
          </jdk>
        </toolchains>
      </configuration>
    </plugin>
  </plugins>
</build>
~~~

Trên máy developer, tạo `~/.m2/toolchains.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<toolchains>
  <toolchain>
    <type>jdk</type>
    <provides>
      <version>17.0.12</version>
    </provides>
    <configuration>
      <jdkHome>C:\jdks\temurin-17</jdkHome>
    </configuration>
  </toolchain>
</toolchains>
~~~

Đường dẫn `jdkHome` phải trỏ tới root của một JDK có `bin/java` và `bin/javac`, không phải thư mục `bin` và không phải một JRE thiếu compiler.

POM dùng version range `[17,18)` để nhận JDK 17 với patch version khác nhau. Nếu dùng version literal, giá trị `<version>` trong toolchains metadata phải khớp đúng theo quy tắc matching của Maven. Có thể thêm `<vendor>` khi muốn ràng buộc nhà cung cấp; token này được so khớp chính xác theo metadata, nên phải kiểm tra giá trị thực.

`toolchains.xml` thường chứa đường dẫn cục bộ và không nên commit vào source repository. CI cần cài JDK rồi tạo/cấu hình toolchains tương ứng.

## 10. Maven Toolchains không đổi JVM chạy Maven

Sau khi chọn toolchain, Maven process vẫn chạy trên JVM đã khởi động Maven. Toolchain được chuyển cho các plugin hiểu Maven Toolchains, ví dụ Compiler, Surefire, Failsafe và Javadoc Plugin.

Điều này cho phép:

- Maven chạy trên JDK 24.
- Compiler dùng JDK 17.
- Surefire chạy test bằng JDK 17 nếu plugin nhận toolchain.
- Javadoc dùng JDK 17 nếu plugin nhận toolchain.

Không phải mọi plugin bên thứ ba đều hỗ trợ toolchain. Một plugin không nhận toolchain có thể tiếp tục dùng JVM đang chạy Maven hoặc cần cấu hình executable riêng. Hãy đọc tài liệu plugin và kiểm tra log.

Maven Compiler Plugin cũng có tham số `jdkToolchain` riêng. Khi cấu hình, toolchain riêng của compiler có thể ghi đè toolchain chung được chọn bởi `maven-toolchains-plugin`. Chỉ dùng khi thực sự cần một compiler khác cho một plugin/execution cụ thể; nếu không, chọn một toolchain chung để compile/test/Javadoc nhất quán.

## 11. Gradle: phân biệt Client JVM, Daemon JVM và project toolchain

Gradle có ít nhất ba vai trò JVM cần phân biệt:

- **Client JVM:** process khởi chạy lệnh `gradle` hoặc `gradlew`.
- **Daemon JVM:** process nền thực thi build và giữ cache/configuration state.
- **Project toolchain:** JDK dùng cho task compile, test, JavaExec và Javadoc.

Client và daemon có thể dùng JDK khác nhau. Project toolchain cũng có thể khác cả hai.

`gradle -version` hiển thị thông tin JVM của Gradle. Trong output mới có thể thấy `Launcher JVM` và `Daemon JVM`. Khi build chạy từ IDE, Tooling API/IDE có thể quyết định daemon JVM, vì vậy terminal và IDE có thể chọn daemon khác nhau.

Không lấy `java -version` làm bằng chứng duy nhất cho JDK compile của Gradle. Hãy kiểm tra `gradle -version`, toolchain cấu hình trong build script và danh sách toolchain mà Gradle phát hiện.

## 12. Gradle Java Toolchains: pin JDK project

Ví dụ `build.gradle` dùng JDK 17 cho các task Java mặc định:

~~~groovy
plugins {
    id 'java-library'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}
~~~

Java Plugin sẽ dùng toolchain này cho compile, test launcher và Javadoc tasks mà plugin quản lý. Gradle có thể phát hiện JDK đã cài hoặc tải JDK phù hợp nếu toolchain provisioning được cấu hình.

Nếu cần compiler JDK 21 nhưng muốn giữ Java 17 API/bytecode:

~~~groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 17
    options.encoding = 'UTF-8'
}
~~~

Đây là cấu hình hợp lệ: toolchain chọn compiler JDK 21; `options.release` giới hạn target API và class file về Java 17. Không dùng `sourceCompatibility`/`targetCompatibility` thay thế khi cần strict API compatibility.

## 13. Gradle: chọn runtime cho test riêng

Có thể dùng JDK khác cho test launcher mà không đổi compiler toolchain:

~~~groovy
tasks.withType(Test).configureEach {
    javaLauncher = javaToolchains.launcherFor {
        languageVersion = JavaLanguageVersion.of(17)
    }
}
~~~

Ví dụ compile bằng JDK 21 với `options.release = 17`, nhưng chạy unit test trên JDK 17. Đây là cách hữu ích để kiểm tra thư viện thực sự hoạt động trên runtime tối thiểu.

Nếu cần test trên Java 17 và 21, tạo hai `Test` tasks hoặc dùng CI matrix. Mỗi test task nên chỉ rõ launcher để kết quả không phụ thuộc JDK mặc định của máy.

Gradle cũng cho phép task riêng lấy `JavaCompiler`, `JavaLauncher` hoặc `JavadocTool` từ `javaToolchains`. Dùng cách này khi custom task cần gọi đúng JDK thay vì tự ghép đường dẫn `JAVA_HOME/bin`.

## 14. Gradle Daemon JVM: kiểm soát JDK chạy build

`org.gradle.java.home` trong `gradle.properties` có thể chỉ định JVM cho Gradle daemon:

~~~properties
org.gradle.java.home=C:/jdks/temurin-17
~~~

Giá trị đường dẫn tuyệt đối phù hợp hơn với cấu hình máy cá nhân hoặc môi trường build được quản lý; không nên commit một đường dẫn chỉ tồn tại trên một workstation.

Các phiên bản Gradle hỗ trợ Daemon JVM criteria có thể tạo `gradle/gradle-daemon-jvm.properties` bằng task:

~~~text
./gradlew updateDaemonJvm --jvm-version=17
~~~

File criteria có thể được commit để nhóm và CI dùng chung yêu cầu JVM chạy Gradle. Gradle sẽ chọn daemon JVM phù hợp theo criteria; khi dùng criteria, nó có ưu tiên cao hơn `JAVA_HOME` và `org.gradle.java.home`.

Khi thay đổi JDK hoặc cấu hình daemon, có thể dừng daemon cũ:

~~~text
./gradlew --stop
~~~

Sau đó chạy lại build và kiểm tra `./gradlew -version`. Đừng dừng daemon như cách chữa mọi lỗi compiler; chỉ dùng khi cần loại bỏ process daemon đang giữ cấu hình JVM cũ hoặc để chẩn đoán.

## 15. IDE có thể dùng JDK khác terminal

IDE thường có nhiều thiết lập Java độc lập:

- Project SDK: JDK dùng để index/compile project trong IDE.
- Maven Runner JRE: JVM khởi chạy Maven từ IDE.
- Gradle JVM: JVM khởi chạy Gradle daemon qua IDE.
- Module language level: mức ngôn ngữ source mà IDE kiểm tra.
- Build delegation: IDE tự build hay ủy quyền build cho Maven/Gradle.

Một project có thể compile thành công bằng nút Build trong IDE nhưng fail với `./mvnw verify` hoặc `./gradlew check` ở terminal.

Cách cấu hình:

- Đặt Project SDK theo JDK mà project hỗ trợ.
- Đặt Maven Runner JRE tương thích với Maven và build configuration.
- Đặt Gradle JVM phù hợp với Gradle version/daemon criteria.
- Để Maven/Gradle toolchain quyết định compiler/test runtime của project.
- Dùng lệnh wrapper từ terminal để xác minh build độc lập với IDE.

IDE setting không thay thế build configuration. Các thành viên khác và CI không thể dựa vào cấu hình IDE cá nhân của bạn.

## 16. Maven Wrapper và Gradle Wrapper không pin JDK

Maven Wrapper lưu Maven distribution và Gradle Wrapper lưu Gradle distribution. Hai wrapper không tự cài/chọn cùng một JDK cho mọi máy.

Ví dụ:

~~~text
Windows:
mvnw.cmd -version
gradlew.bat -version

Linux/macOS:
./mvnw -version
./gradlew -version
~~~

Wrapper giúp nhóm dùng cùng phiên bản Maven/Gradle, nhưng kết quả build vẫn có thể khác nếu JDK, toolchain, OS, architecture hoặc dependency khác nhau.

Để reproducible hơn, kết hợp:

- Wrapper được commit và kiểm tra checksum distribution.
- JDK/toolchain version được khai báo.
- `--release` được đặt rõ.
- Plugin/build logic được pin version.
- Dependency được khóa hoặc kiểm soát version.
- CI dùng cùng policy với developer.

## 17. CI: pin JDK rõ ràng

Ví dụ GitHub Actions chạy Maven trên Java 17:

~~~yaml
name: Java 17 build

on:
  pull_request:
  push:
    branches: [main]

jobs:
  verify:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '17'
          cache: maven

      - name: Show Java and Maven
        run: |
          java -version
          javac -version
          ./mvnw -version

      - name: Verify
        run: ./mvnw -B -ntp clean verify
~~~

Với Gradle, thay bước verify bằng:

~~~yaml
      - name: Verify
        run: ./gradlew --no-daemon clean check
~~~

Nếu thư viện hỗ trợ nhiều runtime, tạo CI matrix chạy test trên từng JDK được hỗ trợ, ví dụ 17 và 21. Giữ target release ở mức tương thích thấp nhất đã cam kết; test matrix kiểm tra hành vi runtime trên các phiên bản đó.

Không chỉ cài JDK mới nhất rồi để build tự chọn. Ghi rõ vendor/version, hiển thị `java -version`, `mvn -version` hoặc `gradle -version` trong log. Với self-hosted runner, kiểm tra daemon cũ và toolchain cache sau khi đổi JDK.

## 18. Kiểm tra API target và bytecode

Một file `.class` có major version tương ứng với Java release. Ví dụ Java 17 tạo class file major version `61`. Dùng `javap` để kiểm tra:

~~~text
javap -verbose -classpath target/classes com.example.ToolchainDemo
~~~

Tìm dòng:

~~~text
major version: 61
~~~

Điều này xác nhận class file có target Java 17. Nó không tự chứng minh toàn bộ dependency trong ứng dụng cũng hỗ trợ Java 17; cần kiểm tra dependency bytecode và runtime.

Có thể kiểm tra một JAR bằng:

~~~text
jar --describe-module --file target/library.jar
jdeps --multi-release 17 --jdk-internals target/library.jar
~~~

`jdeps` hỗ trợ phân tích dependency ở cấp class/module. Nó bổ sung cho kiểm tra `--release`; nó không thay thế test trên runtime đích.

## 19. Ví dụ kiểm soát JDK bằng javac

Tạo `ToolchainDemo.java`:

~~~java
public final class ToolchainDemo {
    private ToolchainDemo() {
    }

    public static void main(String[] args) {
        System.out.println(
                "JAVA_RUNTIME_FEATURE=" + Runtime.version().feature());
        System.out.println(
                "STRING_IS_BLANK=" + "   ".isBlank());
    }
}
~~~

Biên dịch cho Java 17 bằng compiler đang cài:

~~~text
javac --release 17 -encoding UTF-8 -Xlint:all -Werror -d out ToolchainDemo.java
~~~

Chạy:

~~~text
java -cp out ToolchainDemo
~~~

Nếu chạy bằng JDK 24:

~~~text
JAVA_RUNTIME_FEATURE=24
STRING_IS_BLANK=true
~~~

Kiểm tra bytecode:

~~~text
javap -verbose -classpath out ToolchainDemo
~~~

Kết quả phải có:

~~~text
major version: 61
~~~

Runtime feature hiển thị 24 vì executable `java` đang chạy là JDK 24; class file vẫn được biên dịch cho Java 17. Khi chạy bằng Java 17, dòng đầu sẽ là `JAVA_RUNTIME_FEATURE=17`.

## 20. Negative test: phát hiện API mới hơn target

`Thread.threadId()` được bổ sung từ Java 19. Tạo một fixture riêng:

~~~java
public final class NewApiProbe {
    public static void main(String[] args) {
        System.out.println(Thread.currentThread().threadId());
    }
}
~~~

Compile với JDK mới nhưng target Java 17:

~~~text
javac --release 17 NewApiProbe.java
~~~

Compiler phải báo không tìm thấy `threadId()` trong `Thread`, vì API đó không thuộc Java 17.

Compile cùng source bằng compiler JDK 24 không giới hạn release:

~~~text
javac NewApiProbe.java
~~~

Lệnh này có thể thành công, nhưng class file sẽ nhắm tới JDK hiện tại và không phù hợp với runtime Java 17. Đây là lỗi thường gặp khi chỉ kiểm tra build trên JDK mới.

Negative test này hữu ích để chứng minh `--release` đang được áp dụng. Đặt fixture trong test riêng hoặc thư mục kiểm thử compile-failure; không đặt nó vào source set chính vì nó phải thất bại khi target là Java 17.

## 21. Kiểm tra build thực tế

Đối chiếu các kết quả:

| Lệnh | Thông tin cần xác nhận |
|---|---|
| `java -version` | Runtime được shell tìm thấy |
| `javac -version` | Compiler được shell tìm thấy |
| `mvn -version` | Maven distribution và JVM chạy Maven |
| `gradle -version` | Gradle version, launcher JVM và daemon JVM |
| `./gradlew -q javaToolchains` | Các JDK Gradle phát hiện |
| `javap -verbose` | Class file major version |
| `jar --describe-module` | Module descriptor trong JAR |

Đối với Maven Toolchains, xem log goal `toolchain` và cấu hình `toolchains.xml`; `mvn -version` chỉ hiển thị JVM chạy Maven. Đối với Gradle, xem project `java.toolchain` và daemon JVM riêng biệt.

Ghi lại các phiên bản quan trọng trong build log hoặc build scan để khi so sánh local/CI có đủ bằng chứng.

## 22. Những lỗi phổ biến và cách xử lý

### `UnsupportedClassVersionError`

**Nguyên nhân:** Runtime thấp hơn phiên bản bytecode của class hoặc dependency.

**Cách xử lý:** kiểm tra `javap -verbose`, xác nhận target release, kiểm tra toàn bộ dependency và chạy trên runtime tối thiểu được hỗ trợ.

### `NoSuchMethodError` hoặc `NoClassDefFoundError` trên runtime cũ

**Nguyên nhân:** Compile thành công với API mới nhưng runtime không có method/class đó, hoặc dependency runtime khác dependency compile.

**Cách xử lý:** dùng `--release`, kiểm tra dependency tree và chạy test trên runtime đích.

### IDE build thành công nhưng Maven/Gradle CLI thất bại

**Nguyên nhân:** Project SDK, Maven Runner JRE hoặc Gradle JVM khác cấu hình terminal.

**Cách xử lý:** xem riêng từng IDE setting, chạy wrapper từ terminal, kiểm tra `mvn -version`/`gradle -version` và cấu hình toolchain trong build.

### `JAVA_HOME` đúng nhưng `java -version` sai

**Nguyên nhân:** `PATH` có JDK khác đứng trước `JAVA_HOME/bin`.

**Cách xử lý:** kiểm tra `where.exe java` hoặc `command -v java`, sắp xếp lại PATH và mở terminal mới.

### Maven chạy đúng JDK nhưng compiler dùng sai JDK

**Nguyên nhân:** Maven Toolchains chưa được chọn, plugin không nhận toolchain hoặc cấu hình `jdkToolchain` riêng ghi đè toolchain chung.

**Cách xử lý:** kiểm tra `toolchains.xml`, POM, plugin version và log selection. Xác nhận compiler, Surefire/Failsafe và Javadoc có hỗ trợ toolchain.

### Gradle dùng daemon JVM cũ

**Nguyên nhân:** IDE/daemon còn process chạy từ cấu hình trước hoặc daemon criteria khác `JAVA_HOME`.

**Cách xử lý:** xem `gradle -version`, kiểm tra `gradle.properties` và daemon criteria, chạy `./gradlew --stop` rồi build lại.

### Build local xanh nhưng CI đỏ

**Nguyên nhân:** local dùng JDK mới hơn, CI dùng target runtime cũ hơn; hoặc vendor, patch, OS, architecture khác nhau.

**Cách xử lý:** pin JDK/toolchain, giữ `--release`, thêm runtime matrix và in phiên bản trong log CI.

### `mvnw`/`gradlew` vẫn dùng JDK không mong muốn

**Nguyên nhân:** Wrapper chỉ chọn build tool distribution.

**Cách xử lý:** cấu hình `JAVA_HOME`, Maven Toolchains, Gradle Daemon JVM criteria và project toolchain theo từng vai trò.

### Annotation processor hoặc plugin chỉ hoạt động trên một JDK

**Nguyên nhân:** processor/plugin chạy trong JVM/compiler environment riêng và có thể phụ thuộc API nội bộ hoặc JDK cụ thể.

**Cách xử lý:** pin version processor/plugin, kiểm tra compatibility matrix của nhà cung cấp, cấu hình toolchain đúng và kiểm thử trên JDK CI thực tế.

## 23. Ma trận hỗ trợ JDK nên được ghi thành policy

Một bảng policy giúp developer và CI dùng cùng một hợp đồng:

| Thuộc tính | Ví dụ policy |
|---|---|
| Build tool | Maven Wrapper 3.9.12 |
| Build JVM | JDK 17 |
| Compiler toolchain | JDK 17 |
| `--release` | 17 |
| Unit test runtime | JDK 17 và 21 |
| Production runtime | JDK 17 |
| JDK vendor | Temurin hoặc vendor được tổ chức phê duyệt |
| Architecture | x86_64 và AArch64 nếu sản phẩm hỗ trợ |
| Encoding | UTF-8 |
| CI | Matrix theo runtime được hỗ trợ |

Nếu build JVM bắt buộc phải mới hơn vì Gradle/Maven/plugin, ghi riêng build JVM và project toolchain. Không ép tất cả vai trò phải dùng cùng một số version khi có lý do kỹ thuật rõ ràng.

## 24. Reproducibility: đừng chỉ pin số major

Cùng major version chưa chắc đồng nghĩa môi trường giống hệt. Khi cần build tái lập, cân nhắc:

- JDK vendor và patch version.
- OS và CPU architecture.
- Maven/Gradle Wrapper version.
- Plugin version và dependency resolution.
- Compiler flags, annotation processors và encoding.
- Locale, timezone, file permissions và line endings.
- Environment variables được build script sử dụng.
- Docker base image hoặc runner image.
- Build timestamp và generated metadata.

Với thư viện phổ thông, thường chỉ cần pin major/toolchain và kiểm thử matrix. Với native build, signing, byte-for-byte reproducible build hoặc compliance, cần pin vendor/patch/architecture và image digest chặt hơn.

Không ghi absolute JDK path của workstation vào POM hoặc `build.gradle`. Dùng toolchain requirements và để từng máy/CI cung cấp installation path phù hợp.

## 25. Quy trình đề xuất khi đổi JDK

1. Đọc compatibility của Maven/Gradle wrapper và plugin.
2. Chọn JDK chạy build tool.
3. Chọn compiler/test/Javadoc toolchain.
4. Khai báo target release rõ ràng.
5. Cấu hình IDE cùng policy với command line.
6. Cập nhật CI JDK và runtime matrix.
7. Chạy compile, test, Javadoc, packaging và static analysis.
8. Kiểm tra bytecode bằng `javap`, dependency bằng `jdeps` khi cần.
9. Chạy consumer/application trên runtime tối thiểu.
10. Ghi lại version/toolchain trong release log.

Khi đổi JDK, xóa hoặc rebuild output/cache chỉ khi cần xử lý stale compiled classes hoặc daemon state; không mặc định xóa toàn bộ cache là cách sửa đúng. Trước tiên xác định process nào đang dùng JDK cũ.

## 26. Checklist chống JDK mismatch

- [ ] Đã phân biệt build JVM, compiler toolchain, target release và production runtime.
- [ ] `JAVA_HOME`, `PATH` và IDE settings không mâu thuẫn ngoài ý muốn.
- [ ] `mvn -version` hoặc `gradle -version` được kiểm tra trong log.
- [ ] Maven/Gradle Wrapper được commit và pin version.
- [ ] Maven Toolchains hoặc Gradle Java Toolchains được cấu hình khi cần JDK riêng.
- [ ] `--release` được đặt rõ thay vì chỉ dựa vào `source`/`target`.
- [ ] Test chạy trên runtime tối thiểu được hỗ trợ.
- [ ] CI có matrix cho các JDK runtime đã cam kết.
- [ ] JDK vendor/patch/architecture được ghi rõ nếu có yêu cầu.
- [ ] Compiler, test, Javadoc và plugin thực sự dùng đúng toolchain.
- [ ] Không commit absolute path JDK của máy cá nhân.
- [ ] Class file và dependency đã được kiểm tra khi nâng JDK.
- [ ] Release artifact được chạy thử trên runtime production.

## 27. Tài liệu tham khảo

- Oracle JDK 24 — `javac --release`, source/target và cross-compilation: https://docs.oracle.com/en/java/javase/24/docs/specs/man/javac.html
- Apache Maven — Guide to Using Toolchains: https://maven.apache.org/guides/mini/guide-using-toolchains
- Apache Maven — Compiling Sources Using a Different JDK: https://maven.apache.org/plugins/maven-compiler-plugin/examples/compile-using-different-jdk.html
- Apache Maven — Maven Toolchains Plugin: https://maven.apache.org/plugins/maven-toolchains-plugin/
- Apache Maven — Maven Compiler Plugin: https://maven.apache.org/plugins/maven-compiler-plugin/
- Gradle — Toolchains for JVM Projects: https://docs.gradle.org/current/userguide/toolchains.html
- Gradle — Gradle Daemon and Daemon JVM Criteria: https://docs.gradle.org/current/userguide/gradle_daemon.html
- Gradle — Java Plugin: https://docs.gradle.org/current/userguide/java_plugin.html
- Gradle — Gradle Wrapper: https://docs.gradle.org/current/userguide/gradle_wrapper.html
- GitHub Actions — Building and testing Java with Maven: https://docs.github.com/en/actions/use-cases-and-examples/building-and-testing/building-and-testing-java-with-maven

Dùng JDK khác khi build là hợp lệ nếu khác biệt được chủ động cấu hình. Anti-pattern là để shell, IDE, Maven, Gradle, CI và production tự chọn các JDK không đồng nhất mà không có policy. Hãy pin toolchain cho từng công đoạn, dùng `--release` để khóa API/bytecode target và chạy test trên runtime thực sự được hỗ trợ.