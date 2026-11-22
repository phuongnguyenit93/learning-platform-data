# Cấu hình toolchain độc lập với JDK chạy công cụ build

Một dự án Java có thể chạy **Maven hoặc Gradle bằng JDK 21**, nhưng **biên dịch mã nguồn bằng JDK 17**, chạy unit tests bằng JDK 17 hoặc JDK 21, và phân phối artifact tương thích với Java 17. Khả năng này đến từ *Java toolchain*: cấu hình rõ phiên bản/bản cài đặt JDK dùng cho các tác vụ build, thay vì mặc nhiên lấy mọi công cụ từ `JAVA_HOME` hoặc JVM đang chạy build tool.

Bài học tập trung vào **tích hợp build và biên dịch**: phân biệt các JVM/JDK liên quan, thiết lập toolchain với Maven và Gradle, so sánh với `--release`, kiểm chứng version thực được dùng, và giữ build tái lập được giữa máy lập trình, CI và môi trường triển khai.

## 1. Ba khái niệm thường bị nhầm

~~~text
Terminal / CI / IDE
      |
      |  Chọn JVM chạy build tool (JAVA_HOME, IDE, daemon)
      v
Maven JVM hoặc Gradle daemon JVM
      |
      |  Đọc pom.xml / build.gradle(.kts)
      |  Giải dependency, lên lịch tasks, chạy plugins
      |
      +------------------------+
      | Java toolchain         |
      | Chọn JDK phục vụ task  |
      v                        v
JDK dùng javac             JDK dùng java cho Test/JavaExec
      |                        |
      v                        v
*.class + JAR               Test runtime / task runtime
      |
      |  target/release level; artifact và dependencies
      v
JDK của máy triển khai (có thể là bản cài thứ ba)
~~~

Một build có thể có các phiên bản sau, **không bắt buộc trùng nhau**:

| Tầng | Vai trò | Ví dụ |
| --- | --- | --- |
| **Build JVM** | Chạy Maven CLI, Gradle launcher/daemon, build scripts và plugins | JDK 21 |
| **Compiler toolchain** | Cung cấp `javac` và các công cụ xây dựng bytecode | JDK 17 |
| **Test launcher/toolchain** | Chạy JVM của các test tasks | JDK 17 hoặc 21, tùy cấu hình |
| **Javadoc/tool task** | Sinh tài liệu, chạy `javadoc`/`jarsigner` hoặc task khác | Toolchain được plugin hỗ trợ/chọn |
| **Target release** | Phiên bản source, Java platform APIs và class-file format mà artifact hướng tới | Java 17 |
| **Deployment JVM** | JVM thực sự chạy artifact khi triển khai | JDK/JRE tương thích Java 17+ |

**Không đồng nhất:** “Maven chạy bằng JDK 21” **không** có nghĩa `javac` của task compile cũng nhất thiết là JDK 21; “bytecode class version 61” **không** tự chứng minh nó đã được biên dịch bằng JDK 17. Một compiler mới hơn có thể sinh class files hướng tới Java 17.

## 2. Vì sao cần toolchain?

Không có toolchain được khai báo rõ, kết quả build có thể vô tình phụ thuộc môi trường:

- Máy A dùng JDK 17, máy B dùng JDK 21, đều chạy cùng lệnh `mvn package` hoặc `gradle build`.
- Một developer đổi `JAVA_HOME` để chạy IDE/plugin mới và compiler target của dự án cũng đổi không chủ ý.
- CI dùng JDK 21 để chạy một Gradle version mới, nhưng ứng dụng thư viện vẫn phải compile bằng JDK 17 cho người dùng cuối.
- Một task compile dùng JDK 17, trong khi test task âm thầm chạy bằng JDK khác. Kết quả test có thể không tái hiện được vấn đề ở runtime thực tế.
- Annotation processor, Javadoc hay code-generation tool phụ thuộc APIs của tool JDK, không phải chỉ phụ thuộc Java language level của source.

**Toolchain tạo một hợp đồng build**: project yêu cầu loại tool và version cụ thể; build system tìm hoặc provisioning bản cài JDK phù hợp rồi cấp công cụ cho task hỗ trợ toolchain.

Toolchain **không tự tải JDK trong mọi trường hợp**. Maven và Gradle có cơ chế tìm/cấp phát khác nhau. Build có thể thất bại khi không tìm thấy bản cài phù hợp; đó thường là hành vi tốt hơn việc âm thầm dùng một JDK sai.

## 3. Toolchain khác `--release` như thế nào?

Giả sử dùng JDK 21 để compile code phải chạy trên Java 17. Hai câu hỏi khác nhau:

1. **Dùng compiler nào?** → JDK toolchain (ví dụ JDK 21).
2. **Compiler bị giới hạn tạo artifact tương thích với release nào?** → `javac --release 17`.

| Cơ chế | Chọn JDK thực hiện compile? | Hạn chế ngôn ngữ? | Hạn chế Java platform APIs? | Class-file target? |
| --- | --- | --- | --- | --- |
| Toolchain JDK 17 | Có, compiler từ JDK 17 | Theo compiler đã chọn | Theo APIs compiler/JDK đó hỗ trợ | Mặc định theo compiler/options |
| Toolchain JDK 21 + `--release 17` | Có, JDK 21 | Mức Java 17 | Java platform API trong Java 17 theo cơ chế `--release` | Java 17 |
| `--release 17` đơn lẻ | Không chọn JDK; dùng compiler task đã chọn | Java 17 | Java platform API Java 17 | Java 17 |
| `-source 17 -target 17` | Không chọn JDK | Java 17 | **Không bảo đảm** chỉ dùng Java 17 APIs | Java 17 |
| `JAVA_HOME` | Có thể ảnh hưởng JVM chạy build, môi trường và tool discovery | Không tự khóa mức source | Không tự khóa API level | Không tự khóa class version |

**Tình huống khác nhau:**

- Nếu yêu cầu “**phải dùng đúng javac 17**” để phát hiện vấn đề tương thích compiler/annotation processor, đặt toolchain 17.
- Nếu yêu cầu “**dùng javac 21 nhưng output hỗ trợ Java 17**”, dùng toolchain 21 **kết hợp** `--release 17`.
- Nếu chỉ viết `--release 17` mà chưa chọn toolchain, compiler thực tế vẫn có thể thay đổi giữa các máy.
- `--release` chủ yếu ràng buộc **Java platform**; không bảo đảm phiên bản thư viện bên thứ ba hoặc native APIs mà ứng dụng phụ thuộc cũng tương thích.

Không phải compiler mới hơn nào cũng hỗ trợ mọi release cũ; kiểm tra `javac --help` hoặc cấu hình toolchain/version được project sử dụng.

## 4. Ví dụ ứng dụng Java 17 để kiểm chứng build

Dùng cùng một source độc lập cho hai ví dụ Maven và Gradle bên dưới.

**File `src/main/java/edu/example/toolchain/BuildProbe.java`:**

~~~java
package edu.example.toolchain;

public final class BuildProbe {
    private record Greeting(String name) {}

    public static void main(String[] args) {
        Greeting greeting = new Greeting("Java");
        System.out.println("toolchain-ok:" + greeting.name());
    }
}
~~~

Record là ngôn ngữ Java chuẩn trước Java 17 và hoàn toàn hợp lệ với source/target Java 17. Dự án không cần thư viện ngoài.

Tự kiểm tra khi có JDK 17+:

~~~bash
javac --release 17 -d out src/main/java/edu/example/toolchain/BuildProbe.java
java -cp out edu.example.toolchain.BuildProbe
~~~

**Stdout chính xác:**

~~~text
toolchain-ok:Java
~~~

Một compiler hỗ trợ `--release 17` sẽ tạo các class files, trong đó có binary type cho nested record `Greeting`. Không nên đoán chỉ có `BuildProbe.class`: còn có `BuildProbe$Greeting.class`. Ví dụ này cũng giúp quan sát nhiều class outputs từ cùng source.

Để xem class-file target:

~~~bash
javap -verbose -classpath out edu.example.toolchain.BuildProbe
~~~

Tìm `major version: 61`, giá trị class-file version của Java 17. **Major version 61 chỉ chứng tỏ target class format**, không chứng tỏ compiler đã đến từ JDK 17 thay vì một toolchain JDK 21 có `--release 17`.

## 5. Maven: tách JVM chạy Maven khỏi JDK dùng cho build

Maven thường chạy bằng Java từ `JAVA_HOME`/launcher mà người dùng chọn. Lệnh:

~~~bash
mvn -version
~~~

hiển thị runtime Java mà Maven đang sử dụng, chẳng hạn Java 21. Đây **không phải phép đo trực tiếp** về JDK mà Maven Compiler Plugin chọn sau khi cấu hình toolchain.

Maven Toolchains Plugin cho phép một project **yêu cầu toolchain**, chọn từ các JDK được máy khai báo và đưa toolchain vào build context để những plugins *toolchain-aware* sử dụng.

### 5.1. Cài đặt cả hai JDK

Giả sử máy có:

~~~text
/opt/jdks/jdk-17/       # JDK 17 thật, có bin/java và bin/javac
/opt/jdks/jdk-21/       # JDK 21 thật, có bin/java và bin/javac
~~~

Các đường dẫn trên là **ví dụ**, phải thay bằng JDK installation paths có thật. Trên Windows, đường dẫn có thể có dạng `C:\Program Files\Java\jdk-17` và `C:\Program Files\Java\jdk-21`.

Có thể chọn JDK 21 để chạy Maven, nhưng yêu cầu JDK 17 để compile code. **JDK chạy Maven** vẫn phải tương thích với phiên bản Maven và plugins đang dùng; toolchain không cho phép build tool chạy trên một Java version mà chính build tool không hỗ trợ.

### 5.2. Khai báo JDK local ở `~/.m2/toolchains.xml`

**File `~/.m2/toolchains.xml`** (Windows thường là `%USERPROFILE%\.m2\toolchains.xml`):

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<toolchains>
  <toolchain>
    <type>jdk</type>
    <provides>
      <version>17</version>
    </provides>
    <configuration>
      <jdkHome>/opt/jdks/jdk-17</jdkHome>
    </configuration>
  </toolchain>
  <toolchain>
    <type>jdk</type>
    <provides>
      <version>21</version>
    </provides>
    <configuration>
      <jdkHome>/opt/jdks/jdk-21</jdkHome>
    </configuration>
  </toolchain>
</toolchains>
~~~

`<provides><version>17</version>` là thông tin nhận diện toolchain dùng để **match yêu cầu**. `<configuration><jdkHome>...` là đường dẫn root của bản cài. Các vendor tokens khác cũng có thể khai báo, nhưng nếu yêu cầu vendor trong POM thì local toolchain phải có token khớp.

**Đừng giả định Maven tự xác thực mọi thuộc tính như version/vendor từ tên directory.** Với cấu hình thủ công, hãy tự kiểm tra thực chất:

~~~bash
/opt/jdks/jdk-17/bin/java -version
/opt/jdks/jdk-17/bin/javac -version
/opt/jdks/jdk-21/bin/java -version
~~~

Đây là ví dụ lệnh Unix. Trên Windows, dùng các executable tương ứng từ `bin` và đặt đường dẫn trong dấu nháy khi có khoảng trắng.

**Không commit đường dẫn máy cá nhân vào `pom.xml`.** `toolchains.xml` thông thường là cấu hình **theo máy/CI**, còn POM khai báo yêu cầu phiên bản có thể chia sẻ trong repo.

### 5.3. POM đầy đủ yêu cầu JDK 17

**File `pom.xml`** trong thư mục gốc project chứa `src/main/java` từ phần 4:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>edu.example</groupId>
  <artifactId>toolchain-demo</artifactId>
  <version>1.0.0</version>

  <properties>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    <maven.compiler.release>17</maven.compiler.release>
  </properties>

  <build>
    <plugins>
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
              <version>17</version>
            </jdk>
          </toolchains>
        </configuration>
      </plugin>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-compiler-plugin</artifactId>
        <version>3.14.1</version>
        <configuration>
          <release>17</release>
        </configuration>
      </plugin>
    </plugins>
  </build>
</project>
~~~

**Tại sao có cả toolchain và `<release>17</release>`?**

- `maven-toolchains-plugin` chọn một JDK 17 từ các mục trong `toolchains.xml`. Goal `toolchain` được gắn theo mặc định với phase `validate` và đưa selection vào Maven build context.
- `maven-compiler-plugin` là plugin hỗ trợ JDK toolchains; nó có thể lấy `javac` từ toolchain thay vì mặc nhiên dùng JDK đã khởi chạy Maven.
- `<release>17</release>` yêu cầu compile theo Java 17 language/platform API/classfile release. Đây là **ràng buộc target**, không phải cơ chế chọn JDK.

Các versions plugin được ghi tường minh để build không phụ thuộc plugin version ngầm định của môi trường. Với dự án thực tế, chọn các versions đã được xác nhận tương thích với Maven/JDK của tổ chức. Ví dụ cần Maven có khả năng tải plugins/dependencies từ repository được cấu hình (thường Maven Central) hoặc cache đã có.

### 5.4. Biên dịch và kiểm chứng

Từ thư mục chứa `pom.xml`:

~~~bash
mvn -version
mvn clean package
java -cp target/classes edu.example.toolchain.BuildProbe
~~~

Đầu ra của `mvn clean package` gồm logs phụ thuộc phiên bản, cache và cấu hình Maven; không nên coi đó là stdout cố định. Chương trình `BuildProbe` chạy thành công sẽ in:

~~~text
toolchain-ok:Java
~~~

Nếu shell `java` đang trỏ đến JDK 21 thì chương trình được chạy bằng JDK 21. Điều đó **không thay đổi** việc compilation được yêu cầu dùng JDK 17. Để thử runtime 17 tường minh, dùng:

~~~bash
/opt/jdks/jdk-17/bin/java -cp target/classes edu.example.toolchain.BuildProbe
~~~

Trên Unix/Windows, thay path cho phù hợp. Lưu ý: lệnh cuối **không** chứng minh Maven đã chọn JDK 17 khi compile; nó chứng minh **artifact chạy bằng Java 17 runtime**. Để xác minh compiler toolchain, kiểm tra logs của Toolchains Plugin/Maven Compiler Plugin (dùng `mvn -X clean compile` khi cần), hoặc môi trường task đã chọn.

### 5.5. Không tìm được toolchain phù hợp

Nếu POM yêu cầu JDK 17 nhưng `toolchains.xml` chỉ có JDK 21, build có thể thất bại ở phase `validate` với chẩn đoán không tìm được matching toolchain. Đó là hành vi tốt: dự án từ chối compile ngầm bằng compiler khác.

Cách sửa:

1. Cài bản JDK 17 đúng yêu cầu.
2. Kiểm tra `jdkHome` trỏ đến **JDK home** chứ không phải folder `bin` hay một đường dẫn không tồn tại.
3. Khai báo đúng `version`/`vendor` tokens tương ứng trong `toolchains.xml`.
4. Chạy lại `mvn -version` để biết Maven JVM (chỉ để phân biệt tầng), rồi đọc log lựa chọn toolchain khi build.

**Không “sửa” bằng cách xóa plugin toolchains** chỉ để build tạm thành công trên JDK 21 nếu hợp đồng dự án thực sự cần compiler JDK 17.

## 6. Maven: chọn JDK theo discovery hoặc plugin-specific toolchain

### 6.1. Cơ chế discovery mới hơn

Maven Toolchains Plugin từ dòng 3.2.0 hỗ trợ **JDK discovery** và goal `select-jdk-toolchain`. Cơ chế này khác với việc tự viết `toolchains.xml` và dùng goal `toolchain`.

Một project có thể dùng goal discovery để chọn JDK phù hợp từ các bản cài được công cụ nhận biết. Tuy nhiên, automatic detection không có nghĩa mọi máy đều có JDK 17. Cần xem danh sách detected installations và yêu cầu match cụ thể; CI nên fail rõ khi thiếu JDK thay vì chọn ngầm bản khác.

Các goal hữu ích để chẩn đoán ở plugin hiện đại:

~~~bash
mvn toolchains:display-discovered-jdk-toolchains
~~~

Đầu ra phụ thuộc JDKs thực sự được tìm thấy. **Không cần kết hợp hai phương thức selection** một cách vô ý: ví dụ chính chọn kiểu thủ công `toolchains.xml`; dùng discovery là một phương án thay thế có cấu hình riêng.

### 6.2. Compiler Plugin `<jdkToolchain>`

Trong một số trường hợp, Maven Compiler Plugin có cấu hình `<jdkToolchain>` riêng để yêu cầu JDK trực tiếp cho chính plugin đó, ví dụ đoạn cấu hình minh họa:

~~~xml
<configuration>
  <release>17</release>
  <jdkToolchain>
    <version>17</version>
  </jdkToolchain>
</configuration>
~~~

Đây **không phải POM độc lập** và không nên chép đè vào POM đã dùng global toolchain nếu không có lý do. Cơ chế plugin-specific có thể **ghi đè selection toolchain của session** cho compiler plugin, còn plugin khác như Surefire/Javadoc có thể dùng selection khác. Nếu cần test/javadoc cũng chạy với một JDK cố định, nên chọn/sắp xếp toolchains cho **toàn pipeline**, không chỉ compiler.

## 7. Gradle: Java toolchain khác JVM chạy Gradle daemon

Trong Gradle, **JVM dùng chạy Gradle** được chọn qua môi trường, IDE hoặc *Daemon JVM criteria* tùy phiên bản Gradle. **Java toolchain của project** là cấu hình khác.

Ví dụ Gradle daemon chạy bằng JDK 21 nhưng một project sử dụng:

~~~kotlin
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}
~~~

Khi Java plugin được áp dụng, Gradle có thể dùng JDK 17 cho `JavaCompile`, `Test` và `Javadoc` mặc định theo project toolchain, dù daemon vẫn dùng JDK 21. Đây không phải một bước “Gradle tự hạ JVM của nó về Java 17”; Gradle chỉ cấp công cụ phù hợp cho tasks cần chúng.

**Lưu ý phiên bản Gradle:** phiên bản Gradle được chọn phải chạy được trên JVM dùng cho daemon, đồng thời hỗ trợ JDK toolchain muốn dùng. Nếu Gradle cần Java version cao hơn để chạy chính nó, chỉ nên thay daemon JVM khi điều đó đáp ứng yêu cầu runtime của Gradle; không ép daemon dùng một JDK cũ chỉ vì application target cũ.

### 7.1. Gradle Kotlin DSL đầy đủ

Giả sử cùng `src/main/java/edu/example/toolchain/BuildProbe.java` ở phần 4.

**File `settings.gradle.kts`:**

~~~kotlin
rootProject.name = "toolchain-demo"
~~~

**File `build.gradle.kts`:**

~~~kotlin
plugins {
    application
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.release.set(17)
    options.encoding = "UTF-8"
}

application {
    mainClass = "edu.example.toolchain.BuildProbe"
}
~~~

Giải thích:

- `application` áp dụng Java plugin và cung cấp task `run`, trong đó main class được khai báo.
- `java.toolchain.languageVersion` yêu cầu **JDK 17** cho những Java tasks hỗ trợ toolchain. Không yêu cầu daemon của Gradle chạy bằng JDK 17.
- `options.release.set(17)` bổ sung ràng buộc Java 17 language/API/classfile target cho các `JavaCompile` tasks.
- `application.mainClass` xác định entry point cho task `run`.

Chạy trong project bằng **Gradle Wrapper được dự án quản lý** (nếu wrapper đã được tạo):

~~~bash
./gradlew --version
./gradlew clean build
./gradlew run
~~~

Trên Windows thường dùng `gradlew.bat`. Nếu project chưa có Gradle Wrapper, tạo bằng một bản Gradle đã cài phù hợp, ví dụ `gradle wrapper`, rồi commit wrapper files để đồng đội/CI dùng cùng Gradle distribution. Không tự tạo Gradle wrapper JAR bằng cách giả lập nội dung.

`./gradlew run` thực hiện application bằng Java launcher được Gradle cấu hình cho project/toolchain (khi các task/plugin hỗ trợ). **Stdout do ứng dụng in**:

~~~text
toolchain-ok:Java
~~~

Gradle có thể thêm logging task/status quanh kết quả; vì vậy toàn bộ terminal output của `gradlew run` không nhất thiết chỉ một dòng.

### 7.2. Gradle Groovy DSL tương đương

Nếu project dùng `build.gradle` thay vì Kotlin DSL:

~~~groovy
plugins {
    id 'application'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 17
    options.encoding = 'UTF-8'
}

application {
    mainClass = 'edu.example.toolchain.BuildProbe'
}
~~~

Chỉ chọn **một DSL phù hợp project**, không giữ đồng thời hai file Gradle config làm hai nguồn chân lý trái nhau.

## 8. Gradle: kết hợp JDK 21 compiler với target Java 17

Trong một số dự án, mục tiêu là **compiler từ JDK 21** nhưng output được phép sử dụng **Java 17 API/language**.

~~~kotlin
plugins {
    java
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.release.set(17)
}
~~~

Đây là một cấu hình Gradle Kotlin DSL minh họa có thể dùng trong project **đã cài Java 21 toolchain**. Compiler tool là JDK 21; `--release 17` ràng buộc source/API/classfile. Unit tests mặc định dùng project toolchain JDK 21 nếu không override; **chúng không mặc nhiên chứng minh ứng dụng đã được thử trên runtime Java 17**.

Nếu production tối thiểu là Java 17, cần thêm một test task/CI job chạy Java 17 để tránh bỏ sót khác biệt runtime và third-party dependencies. Không kết luận chỉ từ bytecode major version.

### 8.1. Dùng JDK 17 cho test dù compile bằng JDK 21

Ví dụ cấu hình Kotlin DSL khi application bytecode được compile với `--release 17`:

~~~kotlin
val java17Launcher = javaToolchains.launcherFor {
    languageVersion.set(JavaLanguageVersion.of(17))
}

tasks.withType<Test>().configureEach {
    javaLauncher.set(java17Launcher)
}
~~~

Đoạn này đặt trong `build.gradle.kts` **đã áp dụng Java plugin**, với JDK 17 có thể được Gradle tìm thấy. Việc override test launcher **không đổi compiler toolchain**, chỉ đổi Java process chạy tests. Với task `JavaExec` tuỳ biến, có thuộc tính `javaLauncher` tương ứng khi task hỗ trợ.

Có thể dùng các launchers khác nhau cho test matrix, nhưng phải tránh biến một task trùng tên `test` thành nhiều runtime test không có phân biệt output. Tạo task riêng cho mỗi runtime hoặc CI jobs rõ ràng.

## 9. Gradle tìm JDK toolchain ở đâu?

Gradle có cơ chế **tự phát hiện JDKs đã cài** từ một số vị trí và môi trường, và có thể **auto-provision** khi cấu hình đúng repository/toolchain resolver. Các điều kiện cần nhớ:

- `languageVersion = JavaLanguageVersion.of(17)` đặt **yêu cầu**, không cam kết “mọi máy sẽ tự tải JDK 17 ngay cả khi offline hoặc chưa cấu hình resolver”.
- Gradle có thể xem những JDK installations khác nhau và chọn bản thỏa yêu cầu; nếu nhiều vendor/phân phối cùng version, kết quả chọn có thể khác nếu không thêm ràng buộc.
- Có thể khai báo vendor, implementation/JVM options theo toolchain specification khi cần. Không đặt tiêu chí thừa nếu không cần thiết; ví dụ chỉ yêu cầu Java 17 có thể chấp nhận nhiều phân phối JDK 17 phù hợp.
- JDK dùng **chạy Gradle daemon** và JDK **cung cấp toolchain** thường cùng xuất hiện trong danh sách, nhưng là hai quyết định độc lập.
- Việc provisioning/caching toolchains phụ thuộc cấu hình Gradle version, repository và chính sách mạng/CI; không dựa vào hành vi tải xuống ngầm khi build phải tái lập offline.

Kiểm tra JDK được Gradle phát hiện:

~~~bash
./gradlew javaToolchains
~~~

Đây là task hỗ trợ chẩn đoán các Java installations với Gradle version phù hợp. Đầu ra có thể liệt kê JDK vendor/version/path và trạng thái detection. Nó **không thay thế** việc nhìn logs của task compile/test để biết công cụ nào đã được chọn.

Có thể chỉ định thêm paths bằng các cấu hình Gradle properties khi auto-detection không thấy JDK cài đặc biệt. Một phương án minh họa trong `gradle.properties`:

~~~properties
org.gradle.java.installations.paths=/opt/jdks/jdk-17,/opt/jdks/jdk-21
~~~

Đây là **đường dẫn ví dụ Unix**, không dùng nguyên văn trên mọi máy. Đối với portable project, ưu tiên cấu hình JDK installations ở cấp CI/máy hoặc theo chính sách của tổ chức thay vì commit absolute paths vào repo.

### 9.1. `JAVA_HOME` còn tác dụng gì?

`JAVA_HOME` có thể quyết định JVM khởi chạy Gradle/Maven khi không có thiết lập khác, hoặc được build tool dùng trong discovery. Nhưng khi project **đã yêu cầu toolchain riêng**, đừng suy ra changing `JAVA_HOME` sẽ đổi compiler/task JDK thành cùng version. Nếu cả JVM của Gradle và toolchain đang dùng vô tình trùng JDK thì đó là trùng cấu hình, không phải hợp đồng bắt buộc.

IDE (IntelliJ, Eclipse...) có thể có **Gradle JVM** riêng. Một project thấy Gradle daemon 21 trong IDE và 17 ngoài terminal có thể vẫn compile bằng JDK 17 qua toolchain; điều cần xác minh là *toolchain selection*, không chỉ nhãn Gradle JVM trên IDE.

## 10. Một project có thể dùng nhiều JDK trong cùng pipeline

Ví dụ quy trình phát hành thư viện phải chạy trên Java 17:

~~~text
CI runner:
    JDK 21 ---> chạy Gradle daemon / Maven build engine
    JDK 21 ---> javac biên dịch --release 17
    JDK 17 ---> chạy test compatibility
    JDK 21 ---> chạy test forward-compatibility
    JDK 21 ---> javadoc hoặc công cụ static analysis
    Java 17+ --> đối tượng triển khai dự kiến
~~~

Mô hình này có ích khi Java 21 cần cho build tooling mới nhưng thư viện vẫn cam kết hỗ trợ runtime 17. Đổi lại, yêu cầu nhiều JDK installations, CI caching và kiểm tra paths/vendoring.

**Không hạ target chỉ bằng một con số trong POM/Gradle và coi là xong:** binary dependencies có thể được compile ở class-file version cao hơn, hoặc một thư viện bên thứ ba có thể gọi API chỉ tồn tại trong Java 21. Compiler target của **mã nguồn đang biên dịch** không kiểm tra hết mọi đường chạy của dependency graph.

### 10.1. Annotation processor và plugins dùng JDK nào?

Maven/Gradle có thể chạy plugin/build script bằng **build JVM**; riêng Java compilation task có thể dùng **toolchain javac**. Annotation processors thường chạy trong môi trường/compiler process tương ứng cách plugin gọi compiler, nên việc thay toolchain có thể ảnh hưởng xử lý annotation.

Đừng suy luận rằng “mọi Maven/Gradle plugin đã chuyển sang JDK 17” sau khi chọn toolchain 17. Chỉ những **tasks/plugins toolchain-aware** mới sử dụng toolchain theo hợp đồng của chúng. Ví dụ một plugin bất kỳ tự đọc `System.getProperty("java.home")` có thể vẫn thấy Java home của build JVM.

Nếu một annotation processor dùng APIs `jdk.compiler` nội bộ hoặc phụ thuộc compiler AST, hãy test processor với đúng compiler JDK đã chọn, không chỉ thay `--release`.

## 11. Toolchain và khả năng tái lập của build

Để biến toolchain thành hợp đồng đáng tin cậy, cần quản lý **nhiều lớp phiên bản**:

| Lớp | Cần khóa/ghi nhận |
| --- | --- |
| Build tool | Maven/Gradle wrapper hoặc version chuẩn của tổ chức |
| JVM chạy build | Version hỗ trợ cho build tool, IDE/CI daemon criteria khi cần |
| Java toolchain | Major version, vendor/implementation khi có yêu cầu |
| Target API/bytecode | `--release 17` hoặc property tương ứng |
| Dependencies | Version Java libraries, annotation processors, build plugins |
| Test runtime | JDK tối thiểu và JDK mới hơn cần hỗ trợ |
| Container/CI image | JDK installations thực tế có sẵn, build cache, đường dẫn |
| Binary artifact | `.class` version, JAR contents, runtime startup validation |

**Toolchain không làm build bit-for-bit reproducible một cách tự động.** Hai JDK 17 từ vendor khác nhau hoặc hai minor/patch releases có thể khác compiler fixes, diagnostics hoặc behavior, dù cùng languageVersion. Nếu dự án cần artifact reproducibility nghiêm ngặt, còn phải kiểm soát plugin versions, timestamps, archives, locale/timezone, file ordering, dependencies và build parameters.

### 11.1. JDK path và tính portable

- **Maven:** `~/.m2/toolchains.xml` có `jdkHome` local; POM yêu cầu version/vendor và **không hardcode home path**. CI tạo toolchains config hoặc dùng discovery theo chính sách dự án.
- **Gradle:** project khai báo `java.toolchain`; installations có thể được phát hiện/cung cấp theo cấu hình máy/CI và repository resolver. Không commit absolute `/home/user/...` hoặc `C:\Users\...\jdk` vào shared build script.
- **Docker/CI:** cung cấp đúng JDKs từ image hoặc cache provisioning, sau đó chạy kiểm tra chọn toolchain. Không dựa vào version của shell `java` để kết luận compiler toolchain đã đúng.

## 12. Kịch bản CI điển hình

Giả sử Maven chạy bằng JDK 21 trên agent có cả JDK 17 và JDK 21:

~~~text
CI setup
  install JDK 21 (build JVM)
  install JDK 17 (compiler/test toolchain)
  create ~/.m2/toolchains.xml with JDK homes
  verify Maven toolchain selection
  run: mvn -B clean verify
  run smoke test with JDK 17
  publish JAR only after checks pass
~~~

Đây là **pseudocode kế hoạch CI**, không phải YAML cho GitHub Actions/GitLab CI hay pipeline có thể copy y nguyên. Từng CI provider có task/action cài JDK và quản lý cache riêng.

Với Gradle:

~~~text
CI setup
  install JDK 21 (Gradle daemon JVM)
  install/configure JDK 17 (project toolchain)
  use checked-in Gradle Wrapper
  run: ./gradlew --version
  run: ./gradlew javaToolchains
  run: ./gradlew clean check
  verify Java 17 runtime compatibility
  publish only after checks pass
~~~

Tích hợp thường cần phân biệt **verification job** và **publication job** để không phát hành một artifact chỉ vì đã compile thành công.

## 13. Kiểm tra compiler thật sự đã dùng version nào

Đây là câu hỏi trọng tâm của bài: muốn xác nhận toolchain **độc lập** với JDK chạy tool, phải quan sát đúng tầng.

### 13.1. Các lệnh thường gặp và điều chúng chứng minh

| Lệnh/nguồn quan sát | Cho biết | Không chứng minh trực tiếp |
| --- | --- | --- |
| `java -version` ở shell | Java executable hiện được shell chọn | JDK compiler của Maven/Gradle |
| `javac -version` ở shell | javac hiện được shell chọn | javac thực được plugin chọn |
| `mvn -version` | Java runtime đang chạy Maven | JDK toolchain của compiler plugin |
| `./gradlew --version` | Version Gradle và runtime/daemon JVM tùy cách hiển thị | JDK tất cả compile/test tasks |
| `./gradlew javaToolchains` | Những JDK Gradle nhận diện và thuộc tính | Chắc chắn task đã chọn một JDK cụ thể |
| Maven Toolchains Plugin logs | Toolchain được chọn trong build context | Mọi plugin đều dùng selection đó |
| Gradle compile/test task logs (khi bật info) | Compiler/launcher dùng cho task | Production deployment JVM |
| `javap -verbose` major version | Bytecode target class-file version | JDK compiler và runtime dùng lúc build |
| Chạy test với binary cụ thể `/path/to/jdk-17/bin/java` | Artifact thực sự được test trên JVM đó | Code runtime ở mọi môi trường khác |

### 13.2. Maven logs

~~~bash
mvn -X clean compile
~~~

Trong output có thể quan sát thông tin về selected toolchain/JDK path của plugins. Log dài có thể chứa đường dẫn và arguments mang dữ liệu nội bộ; khi chia sẻ ngoài tổ chức nên xóa thông tin nhạy cảm. Không dùng một dòng warning version như chứng cứ duy nhất nếu compiler/plugin có override riêng.

### 13.3. Gradle logs

~~~bash
./gradlew --info compileJava test
./gradlew javaToolchains
~~~

Nếu task reports không đủ để chứng minh compiler, kiểm tra cấu hình task `javaCompiler` hoặc thêm một task diagnostic **chỉ đọc** được thiết kế riêng (trong môi trường build có quyền chỉnh script), thay vì chạy `java -version` rồi suy đoán.

### 13.4. Đối chiếu class-file target

Compile xong với target Java 17, class file thông thường có:

~~~text
major version: 61
~~~

Nhưng đây chỉ là class-file version của **một class cụ thể**. Nếu JAR chứa dependencies hoặc multi-release JAR, cần kiểm tra các class entries phù hợp; target của project không tự biến mọi dependency class version thành 61.

## 14. Các lỗi cấu hình thường gặp

| Triệu chứng | Nguyên nhân hay gặp | Cách sửa |
| --- | --- | --- |
| Maven compile bằng JDK chạy Maven, không phải JDK 17 | Không cấu hình toolchain goal hoặc compiler plugin không lấy toolchain | Kiểm tra POM executions và selected toolchain logs |
| Maven báo không tìm thấy matching JDK | `toolchains.xml` thiếu entry, version/vendor không match, `jdkHome` sai | Kiểm tra file local và version thật của JDK |
| Gradle báo không tìm thấy toolchain cho Java 17 | Máy chưa cài JDK 17, discovery không thấy, provisioning chưa cấu hình | Cài JDK, điều chỉnh detection hoặc resolver phù hợp |
| `Unsupported class file major version` | JVM đang chạy gặp class format từ Java mới hơn | Kiểm tra runtime JVM thực và target/dependency bytecode |
| `invalid target release` / `release version not supported` | Compiler được chọn quá cũ hoặc yêu cầu target không được nó hỗ trợ | Xác định compiler toolchain và release phù hợp |
| `NoSuchMethodError` / `ClassNotFoundException` ở runtime | Dependency/runtime API không tương thích, không nhất thiết do toolchain | Kiểm tra dependency versions, runtime classpath, module graph |
| Toolchain đúng nhưng test dùng JDK khác | Plugin/task không hỗ trợ hoặc chưa được cấu hình launcher | Cấu hình test runtime toolchain/launcher riêng |
| IDE build OK, CI fail | IDE chọn khác JVM/Gradle daemon hoặc CI thiếu JDK toolchain | So sánh môi trường và selection logs, dùng wrapper |
| Annotation processor fail khi đổi JDK | Processor phụ thuộc APIs/compiler implementation khác | Test processor với đúng compiler JDK và version hỗ trợ |
| Build tải JDK trên máy A nhưng offline fail máy B | Provisioning/cache/repository chưa được khai báo đầy đủ | Dùng image cài sẵn JDK hoặc resolver và cache rõ ràng |
| Bytecode Java 17 chạy trên Java 17 vẫn lỗi linkage | Third-party dependency hoặc code dùng reflection/native/behavior mới | Integration test trên runtime và dependency graph thật |
| `JAVA_HOME` đổi nhưng compile vẫn theo JDK khác | Toolchain cấu hình riêng là lựa chọn có chủ đích | Xác minh JVM build và toolchain độc lập; không xóa option tùy tiện |

## 15. Các hiểu lầm phổ biến

**“Dùng JDK 21 để chạy Maven thì project chắc chắn compile bằng Java 21.”** Không đúng khi compiler plugin dùng toolchain 17.

**“Đặt `maven.compiler.release=17` là đã chọn JDK 17.”** Không đúng; nó đặt target, không chọn JDK/compiler executable.

**“Đặt toolchain JDK 21 nhưng `--release 17` thì không thể chạy trên Java 17.”** Sai: source/API/classfile được giới hạn tương ứng, miễn các dependencies và hành vi runtime cũng tương thích. Cần kiểm thử thực tế.

**“`sourceCompatibility=17` và `targetCompatibility=17` đủ để ngăn gọi API Java 21.”** Không bảo đảm; nên dùng `--release` khi muốn hạn chế Java platform API.

**“`mvn -version` hoặc `gradle --version` xác nhận compiler version.”** Không; chúng chủ yếu xác định JVM đang chạy build engine, không phải selected compiler toolchain của từng task.

**“Khai báo JDK toolchain thì Maven/Gradle luôn tự tải JDK.”** Không; cơ chế provisioning/discovery phụ thuộc công cụ và cấu hình. Build cần fail rõ khi thiếu bản cài.

**“Toolchain JDK 17 nghĩa mọi plugin cũng chạy trong JVM 17.”** Không; build engine và các plugins thường vẫn chạy trên build JVM. Những tasks/toolchain-aware plugins chọn executable/JDK tương ứng.

**“Chạy được trên JDK 21 chứng tỏ chạy được trên JDK 17.”** Không; Java 17 là runtime tối thiểu thì phải kiểm tra trên JDK 17 và dependencies thật.

## 16. Bài tập tự kiểm tra

**1. Maven chạy trên JDK 21, compiler plugin chọn JDK 17: có mâu thuẫn không?**  
Không. Build JVM thực thi Maven/logic plugins; JDK 17 toolchain cung cấp compiler cho compilation task.

**2. Cặp `toolchain 21 + --release 17` khác `toolchain 17 + --release 17` ở đâu?**  
Cả hai nhắm language/API/classfile Java 17, nhưng sử dụng **javac từ hai JDK khác nhau**, nên khác compiler version và có thể khác behavior/tooling bugs.

**3. Vì sao Maven cần `toolchains.xml` khi dùng lựa chọn thủ công?**  
POM chứa **yêu cầu** JDK, còn file local cung cấp **đường dẫn installation** đáp ứng yêu cầu đó. POM không cần hardcode path máy.

**4. Vì sao Gradle cần `java.toolchain` khi `JAVA_HOME` đã trỏ JDK 21?**  
Để compiler/test launcher task có thể được cấp JDK khác theo hợp đồng project; không phụ thuộc việc mỗi máy thay `JAVA_HOME`.

**5. `javap` thấy major 61. Có kết luận toolchain JDK 17 đã được dùng không?**  
Không. JDK 21 với `--release 17` cũng có thể tạo class file major 61.

**6. Nếu `--release 17` được đặt, dự án có được tự động bảo đảm mọi dependency chạy trên Java 17 không?**  
Không. Phải xác thực binary dependencies và chạy integration tests trên runtime Java 17.

**7. Nếu Gradle daemon dùng JDK 21 và Test task launcher dùng JDK 17, unit tests chạy ở đâu?**  
JVM JDK 17 theo launcher của Test task, trong khi Gradle daemon vẫn chạy JDK 21.

**8. Khi Maven không tìm thấy toolchain thì nên sửa `maven.compiler.release` từ 17 thành 21 để build xanh?**  
Không nếu hợp đồng project yêu cầu JDK 17; cần cài JDK đúng và cấu hình discovery/toolchains matching.

**9. Toolchain có bắt buộc cùng vendor trên developer/CI?**  
Không theo mặc định chỉ chọn major version. Nếu tính tái lập/vendor-specific bugs quan trọng, thêm constraint vendor/implementation và xác nhận thực tế.

**10. Vì sao CI nên test trên cả JDK tối thiểu và JDK mới hơn?**  
JDK tối thiểu xác nhận backward compatibility; JDK mới giúp phát hiện vấn đề forward compatibility, dependencies và thay đổi runtime.

## 17. Checklist thực hành

- [ ] Ghi rõ **build JVM**, **compiler toolchain**, **test runtime** và **minimum deployment JDK**.
- [ ] Chọn build tool version chạy được trên JVM được cấp cho daemon/Maven.
- [ ] Dùng toolchain để chọn JDK thực thi compile/test/Javadoc tasks hỗ trợ.
- [ ] Dùng `--release` khi cần bảo đảm language level, Java platform APIs và class target.
- [ ] Với Maven, `pom.xml` chứa requirements; `toolchains.xml` local hoặc JDK discovery cung cấp JDK thực.
- [ ] Với Gradle, `java.toolchain.languageVersion` và task-specific launcher được cấu hình rõ.
- [ ] Không mặc định `JAVA_HOME` quyết định mọi Java task khi toolchain được dùng.
- [ ] Đảm bảo CI có JDKs phù hợp hoặc provisioning resolver được cấu hình, có chính sách offline/cache.
- [ ] Xác minh selection qua Maven/Gradle task logs; không chỉ nhìn `mvn -version`.
- [ ] Kiểm tra class-file target và test trên JDK tối thiểu với dependency graph thực.
- [ ] Quản lý Gradle wrapper/Maven version, plugin versions và dependencies cùng với toolchain.
- [ ] Kiểm tra annotation processors, Javadoc, test tools và plugins có toolchain-aware không.
- [ ] Giữ đường dẫn JDK cá nhân khỏi source control, dùng config theo máy hoặc CI.
- [ ] Không coi toolchain là sandbox, không coi nó tự chứng minh build bit-for-bit reproducible.

## 18. Tài liệu chính thức

- [Apache Maven — Guide to Using Toolchains](https://maven.apache.org/guides/mini/guide-using-toolchains): phân biệt JDK chạy Maven với JDK do toolchain cấp cho plugins.
- [Apache Maven Toolchains Plugin](https://maven.apache.org/plugins/maven-toolchains-plugin/): goal `toolchain`, discovery và các công cụ hỗ trợ.
- [Maven Toolchains — JDK Toolchain](https://maven.apache.org/plugins/maven-toolchains-plugin/toolchains/jdk.html): `toolchains.xml`, `jdkHome`, version/vendor matching.
- [Maven Toolchains — `toolchain` goal](https://maven.apache.org/plugins/maven-toolchains-plugin/toolchain-mojo.html): selection goal và phase `validate`.
- [Gradle — Toolchains for JVM projects](https://docs.gradle.org/current/userguide/toolchains.html): project/task toolchains, compile/test/Javadoc, detection, provisioning.
- [Gradle — Building Java projects](https://docs.gradle.org/current/userguide/building_java_projects.html): toolchain, `options.release` và mức target.
- [Oracle JDK 17 — `javac` command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html): ý nghĩa `--release`, `-source`, `-target`.

**Kết luận:** Toolchain xác định **JDK cung cấp các công cụ build cụ thể**; JVM chạy Maven/Gradle được chọn độc lập; `--release` quy định **đầu ra Java tương thích phiên bản nào**. Muốn build đáng tin, hãy cấu hình cả ba tầng, kiểm chứng đúng executable được task sử dụng, và chạy tests trên runtime tối thiểu cùng dependencies thực tế — thay vì chỉ dựa vào `JAVA_HOME` hoặc nhãn phiên bản trên file `.class`.
