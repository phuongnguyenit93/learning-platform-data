# Cấu hình toolchain Java 21 cho dự án Pattern Matching

## 1. Vì sao phải cấu hình toolchain, không chỉ viết code Java 21?

Java 21 đã chuẩn hóa **pattern matching for `switch`** (JEP 441) và **record patterns** (JEP 440). Các cú pháp như `case String s`, `case Point(int x, int y)`, guard `when`, `case null` và pattern switch trên sealed hierarchies có thể biên dịch **không cần `--enable-preview`** khi dùng đúng JDK/source level Java 21.

Nhưng code đúng cú pháp vẫn có thể build thất bại nếu một thành phần trong chuỗi công cụ chưa được cấu hình phù hợp:

- Terminal chạy `java` 21 nhưng `javac` thực tế là 17.
- Maven khởi động bằng JDK 17, compiler plugin dùng một `javac` khác hoặc chưa đặt `release`.
- Gradle chạy trên một JVM, JavaCompile sử dụng JVM/toolchain khác.
- IDE cho phép chọn Language Level 21 nhưng CI vẫn biên dịch bằng JDK 17.
- Build thành công bằng JDK 24 với `source`/`target` 21 nhưng vô tình gọi API chỉ có ở JDK 24.
- Ứng dụng được biên dịch thành bytecode Java 21 nhưng deploy trên JVM 17.
- Test chạy trên JVM không giống bản production, dẫn đến kết quả hoặc lỗi khác.

**Toolchain** là cách khai báo **JDK nào thực thi các công việc build** như biên dịch, chạy test, tạo Javadoc. Cấu hình tốt cần nhất quán giữa **JDK chọn để build**, **mức ngôn ngữ và API cần hỗ trợ**, **runtime thực thi**, **IDE**, và **CI**.

Đối với một dự án dùng pattern switch final của Java 21, cấu hình khuyến nghị gồm:

1. **Cung cấp JDK 21** (không chỉ JRE) cho Maven/Gradle hoặc hệ thống build.
2. **Khai báo toolchain Java 21** ở mức project.
3. **Biên dịch với `--release 21`** để khóa source language, JDK API và class-file target ở Java 21.
4. **Chạy test/integration bằng Java 21**; nếu production dùng bản JDK khác, kiểm thử thêm môi trường đó.
5. **Đồng bộ CI, IDE và Docker/runtime**, tránh các cấu hình ngầm khác nhau.
6. **Không bật preview vô cớ**: pattern switch và record patterns đã final từ Java 21.

*Phạm vi bài:* Cấu hình Java 21 cho dự án Java thuần dùng Maven/Gradle. Android Gradle Plugin, Spring Boot, Kotlin/JVM, Scala, native image và một số compiler/plugin có ma trận tương thích riêng; phải đối chiếu với phiên bản công cụ cụ thể, không tự suy ra tất cả hệ sinh thái đều dùng cùng ma trận.

## 2. Phân biệt bốn lớp phiên bản

Một lỗi phổ biến là nhìn thấy số `21` trong một file cấu hình rồi cho rằng mọi giai đoạn đã dùng Java 21.

| Thành phần | Ví dụ | Đảm bảo điều gì? | Không đảm bảo điều gì? |
| --- | --- | --- | --- |
| **JDK chạy build tool** | `mvn -version` hoặc `./gradlew --version` | JVM chạy Maven/Gradle và phần build logic | Không nhất thiết là JDK được compiler/test task chọn |
| **Java toolchain** | Maven Toolchains Plugin, Gradle `java.toolchain` | Chọn JDK để compile/test/javadoc nếu task/plugin hỗ trợ | Không tự giới hạn việc dùng API của Java cũ khi biên dịch bằng JDK mới |
| **`--release 21`** | Maven `maven.compiler.release=21`, Gradle `options.release=21` | Mức cú pháp, bytecode target và Java SE API nhìn thấy từ compiler | Không tải/cài JDK và không quyết định JVM chạy build tool |
| **Runtime** | `java -version` trong container/production | JVM sẽ thực thi class/JAR đã build | Không tự sửa mã đã compile sai API hoặc class-file target |

**Ví dụ có chủ đích:** Maven chạy dưới JDK 17 nhưng chọn **JDK 21 toolchain** để compile. Điều này có thể hoàn toàn hợp lệ nếu các plugin hỗ trợ toolchain. Ngược lại, `maven.compiler.release=21` đặt trong POM nhưng compiler đang là JDK 17 sẽ **không biến JDK 17 thành JDK 21**.

Với Gradle, cần phân biệt **JVM chạy Gradle daemon** và **JDK cho các task Java**. Theo ma trận chính thức của Gradle, **Gradle 8.4** bắt đầu hỗ trợ Java 21 cho toolchain (compile/test), còn **Gradle 8.5** mới hỗ trợ **chạy Gradle trên JDK 21**. Vì thế, nếu `JAVA_HOME` trỏ JDK 21, không sử dụng Gradle Wrapper cũ hơn 8.5 để chạy trực tiếp trên Java 21 rồi kỳ vọng toolchain có thể cứu được Gradle daemon.

## 3. Cài và xác minh JDK 21

Có thể chọn bản phân phối JDK được dự án hỗ trợ, ví dụ **Eclipse Temurin 21** hoặc một bản OpenJDK 21 phù hợp. Team nên thống nhất major version và chính sách cập nhật security patch. Không cần ép tất cả người dùng về một path cài đặt giống nhau.

### 3.1. Kiểm tra command đang chạy

Trên terminal:

```bash
java -version
javac -version
```

Kết quả hợp lệ cho mục tiêu local JDK 21 có dạng:

```text
openjdk version "21.0.x" ...
javac 21.0.x
```

Dấu `...` và `x` chỉ là **minh họa định dạng output**, không phải stdout chính xác của một phiên bản patch. Output thực tế thay đổi theo nhà cung cấp và patch level.

Trên macOS/Linux:

```bash
command -v java
command -v javac
echo "$JAVA_HOME"
```

Trên PowerShell (Windows):

```powershell
Get-Command java
Get-Command javac
$env:JAVA_HOME
where.exe java
where.exe javac
```

Nếu `java` và `javac` không cùng JDK, kiểm tra `JAVA_HOME` và thứ tự các phần tử trong `PATH`. Một JRE có thể chạy chương trình nhưng không có `javac`; dự án phát triển cần **JDK**.

### 3.2. Đặt JAVA_HOME

Ví dụ macOS/Linux (thay đường dẫn bằng vị trí JDK 21 thật):

```bash
export JAVA_HOME=/absolute/path/to/jdk-21
export PATH="$JAVA_HOME/bin:$PATH"
java -version
javac -version
```

Ví dụ PowerShell (chỉ là **mẫu đường dẫn**, không chạy nếu chưa thay path):

```powershell
$env:JAVA_HOME = "C:\Path\To\jdk-21"
$env:Path = "$env:JAVA_HOME\bin;$env:Path"
java -version
javac -version
```

Các lệnh trên đặt biến **cho shell hiện tại**; cần cấu hình môi trường lâu dài bằng cơ chế của OS hoặc trình quản lý JDK nếu muốn áp dụng qua nhiều phiên. Trên Windows, một số ứng dụng terminal/IDE đang mở sẽ giữ biến môi trường cũ cho đến khi khởi động lại.

**Quan trọng:** `JAVA_HOME` là cơ chế toàn cục cho một phiên, không phải công cụ khóa mọi project vào JDK 21. Khi chạy nhiều dự án Java 17, 21 và 25 trên cùng máy, khai báo toolchain **theo project** đáng tin cậy hơn.

## 4. Maven: mức đơn giản nhất với JDK 21 và --release

Nếu nhóm chỉ có một JDK 21, có thể cho Maven chạy bằng JDK 21 rồi khóa `release`.

Ví dụ `pom.xml` tối thiểu của một ứng dụng Java:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>org.example</groupId>
    <artifactId>java21-patterns</artifactId>
    <version>1.0.0-SNAPSHOT</version>

    <properties>
        <maven.compiler.release>21</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.16.0</version>
            </plugin>
        </plugins>
    </build>
</project>
```

`maven.compiler.release=21` là cách cấu hình `javac --release 21` qua Compiler Plugin. Đây là tham số ổn định được tài liệu Maven Compiler Plugin hỗ trợ. `--release` có ba hiệu ứng chính:

1. Compiler chấp nhận cú pháp ngôn ngữ Java 21, ví dụ pattern switch final và record patterns.
2. Compiler tạo **class-file version 65** (Java 21).
3. Compiler kiểm tra Java SE API theo Java 21; không vô tình dùng Java SE API chỉ tồn tại trên JDK mới hơn khi compiler được chạy từ JDK 24/25.

`sourceCompatibility/targetCompatibility` hoặc `-source/-target` đơn thuần không thay thế được ràng buộc Java API của `--release`.

Thực hiện ở root dự án có `pom.xml`:

```bash
mvn -version
mvn -B -ntp clean verify
```

Nếu dùng Maven Wrapper đã được dự án cung cấp:

```bash
./mvnw -B -ntp clean verify
```

Trên Windows PowerShell, dùng `.\mvnw.cmd -B -ntp clean verify`. Wrapper cần được tạo và quản lý trong repository trước đó; **bài này không giả định tự nhiên đã có file `mvnw`**.

**Giới hạn của cách đơn giản:** nếu Maven đang chạy bằng JDK 17, chỉ thêm property `release=21` có thể cho lỗi `release version 21 not supported`. Khi muốn **Maven JVM khác compiler JDK**, dùng Maven Toolchains Plugin ở mục sau.

## 5. Maven Toolchains Plugin: chọn JDK 21 độc lập với JVM chạy Maven

### 5.1. Chọn JDK bằng cơ chế discovery

Maven Toolchains Plugin **3.2.0+** hỗ trợ tự phát hiện JDK ở các vị trí thông dụng; plugin **3.3.0** cung cấp goal `select-jdk-toolchain`. Ví dụ POM **hoàn chỉnh cho lựa chọn này**:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>org.example</groupId>
    <artifactId>java21-toolchain</artifactId>
    <version>1.0.0-SNAPSHOT</version>

    <properties>
        <maven.compiler.release>21</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <!-- Chỉ nhận JDK từ major Java 21 -->
        <toolchain.jdk.version>[21,22)</toolchain.jdk.version>
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
                            <goal>select-jdk-toolchain</goal>
                        </goals>
                    </execution>
                </executions>
            </plugin>

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.16.0</version>
            </plugin>
        </plugins>
    </build>
</project>
```

**Giải thích:**

- `<toolchain.jdk.version>[21,22)</toolchain.jdk.version>` yêu cầu một JDK Java 21, chấp nhận các patch `21.0.x` và loại Java 22+.
- Goal `select-jdk-toolchain` được gắn vào phase `validate` theo mặc định, tìm JDK tương thích và đưa toolchain vào build context cho các plugin hỗ trợ.
- Nếu JVM đang chạy Maven **đã** phù hợp với ràng buộc, plugin mặc định có thể sử dụng ngay JDK đó mà không chọn một toolchain riêng, để tránh fork không cần thiết.
- `maven.compiler.release` vẫn cần thiết để thể hiện rõ Java language/API target ngay cả khi compiler được chọn từ JDK 21.
- Nếu không tìm thấy JDK phù hợp, build phải báo lỗi; không nên im lặng compile bằng JDK cũ.

Để xem các JDK được Maven phát hiện, dùng:

```bash
mvn org.apache.maven.plugins:maven-toolchains-plugin:3.3.0:display-discovered-jdk-toolchains
```

Thực thi trên thư mục có POM Maven. Khi debug sâu hơn, kiểm tra build log và JDK được compiler/test plugin sử dụng; chỉ nhìn `mvn -version` chưa đủ, vì nó nói về **JVM của Maven process**.

### 5.2. Cách thủ công bằng ~/.m2/toolchains.xml

Khi môi trường bị cô lập hoặc muốn khai báo JDK rõ ràng, dùng `toolchains.xml` ở thư mục Maven user home:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<toolchains>
    <toolchain>
        <type>jdk</type>
        <provides>
            <version>21</version>
            <vendor>temurin</vendor>
        </provides>
        <configuration>
            <jdkHome>/absolute/path/to/jdk-21</jdkHome>
        </configuration>
    </toolchain>
</toolchains>
```

**Thay** `/absolute/path/to/jdk-21` bằng thư mục JDK tồn tại trên máy. Trên Windows đường dẫn có thể là một thư mục trên ổ C; không dùng literal path ví dụ để chạy. `<version>` và `<vendor>` trong `<provides>` là **metadata do người khai báo**, nên phải trung thực với JDK thực tế.

Với cơ chế thủ công, Maven Toolchains Plugin có goal `toolchain` và cấu hình tương ứng:

```xml
<!-- Chỉ là đoạn <plugin> bên trong pom.xml -->
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
                <version>[21,22)</version>
            </jdk>
        </toolchains>
    </configuration>
</plugin>
```

**Không đặt cả hai cấu hình discovery và manual trong POM chỉ vì nhìn thấy hai ví dụ.** Chọn một chiến lược phù hợp. Discovery thường tiện hơn; manual phù hợp với môi trường có JDK path được quản trị chặt. Các goal tìm toolchain **không tự tải JDK 21** nếu không có JDK cài đặt hoặc nguồn tương ứng.

### 5.3. Toolchain compile và JVM chạy test

Maven Toolchains có thể được các plugin như Compiler, Surefire, Javadoc sử dụng để chọn JDK. Tuy nhiên không phải mọi plugin tùy biến đều toolchain-aware. Với test JVM, có thể cấu hình **Maven Surefire Plugin** tường minh nếu cần:

```xml
<!-- Đoạn <plugin> bên trong phần <build><plugins> -->
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-surefire-plugin</artifactId>
    <version>3.5.4</version>
    <configuration>
        <jdkToolchain>
            <version>[21,22)</version>
        </jdkToolchain>
    </configuration>
</plugin>
```

Cấu hình này yêu cầu JDK trong phạm vi 21 cho JVM test khi Surefire chọn toolchain tương ứng. Phải bảo đảm dependency test (JUnit/JUnit Platform nếu dùng) cũng được khai báo và version plugin phù hợp hệ thống. Trong project có integration tests hoặc custom fork/plugin, kiểm tra **riêng** JVM thực thi từng nhóm test.

**Không nhầm:** toolchain giải quyết vấn đề chọn **JDK**, không đảm bảo mọi dependency đã hỗ trợ Java 21; code generation, annotation processors, framework và thư viện vẫn cần các version tương thích.

## 6. Gradle: Java 21 toolchain và options.release

### 6.1. build.gradle.kts (Kotlin DSL)

Đây là ví dụ cho một Java project dùng Gradle:

```kotlin
plugins {
    java
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.release = 21
    options.encoding = "UTF-8"
}
```

**Giải thích:**

- `java.toolchain.languageVersion=21` cho Gradle biết các Java tasks cần JDK 21.
- `options.release=21` cho `JavaCompile` yêu cầu `javac --release 21`, giới hạn Java 21 language/API/bytecode.
- `options.encoding="UTF-8"` thống nhất encoding của source; không phải giải pháp cho mọi vấn đề encoding của dữ liệu runtime.
- Với cấu hình `java` toolchain, Gradle cũng điều phối JDK cho các task Java như test và Javadoc theo hành vi hỗ trợ của task.
- Các plugin bên ngoài có thể tự tạo JavaExec/worker tasks; cần kiểm tra chúng có sử dụng toolchain hay không.

### 6.2. build.gradle (Groovy DSL)

Tương đương:

```groovy
plugins {
    id 'java'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 21
    options.encoding = 'UTF-8'
}
```

**Không** dùng cú pháp Kotlin DSL `tasks.withType<JavaCompile>()` trong `build.gradle` Groovy, hoặc sao chép syntax Groovy `id 'java'` vào Kotlin DSL rồi mong compile. Chọn đúng file DSL của dự án.

### 6.3. Gradle Wrapper và ngưỡng tương thích

Gradle có hai cột tương thích riêng:

| Cần làm | Ngưỡng Gradle được ghi nhận hỗ trợ Java 21 |
| --- | --- |
| Biên dịch/chạy test dùng **Java 21 toolchains**, dù Gradle daemon có thể chạy trên JDK khác | **Gradle 8.4+** |
| Cho **Gradle process chạy trên JDK 21** | **Gradle 8.5+** |

Nguồn: [Gradle Java Compatibility Matrix](https://docs.gradle.org/current/userguide/compatibility.html).

Nếu `JAVA_HOME=JDK 21` mà wrapper quá cũ, có thể thấy lỗi từ Groovy/ASM/Gradle build logic **trước khi** JavaCompile chạy. Nên dùng bản Gradle Wrapper được bảo trì phù hợp với JDK của team và tất cả plugin. Đừng tự động nâng một build đang có Android/Spring/Kotlin plugin lên Gradle mới nhất mà không kiểm tra ma trận tương thích của plugin.

Kiểm tra (ở root có Gradle Wrapper):

```bash
./gradlew --version
./gradlew -q javaToolchains
./gradlew --no-daemon clean test
```

Trên Windows PowerShell, thay `./gradlew` bằng `.\gradlew.bat` khi phù hợp.

`javaToolchains` liệt kê JDK được Gradle phát hiện, trong khi `--version` hiển thị JVM đang chạy Gradle. Hai lệnh **không nhất thiết đưa ra cùng một JDK**.

### 6.4. JDK thiếu: auto-detection và auto-provisioning

Gradle có thể tự phát hiện JDK đã cài đặt. Nếu không tìm được JDK 21, cơ chế auto-provisioning **chỉ hoạt động khi đã cấu hình toolchain download repository** (ví dụ plugin resolver phù hợp), và hệ thống có quyền tải xuống. Không thể chỉ khai báo `languageVersion=21` rồi bảo đảm mọi máy offline tự tải đúng JDK.

Một tùy chọn được Gradle hỗ trợ là **Foojay Toolchains Resolver Convention** (cấu hình ở `settings.gradle.kts`):

```kotlin
plugins {
    id("org.gradle.toolchains.foojay-resolver-convention") version "1.0.0"
}
```

Đây là **ví dụ về cơ chế resolver** theo tài liệu Gradle; khi áp dụng thật, xác nhận version plugin tương thích với Gradle Wrapper và chính sách cung cấp JDK của tổ chức. Nếu build phải offline, hãy cài và chỉ rõ JDK 21 thay vì trông chờ tải từ network.

Khi chỉ muốn dùng JDK đã cài, có thể khai báo biến môi trường hoặc đường dẫn được Gradle phát hiện. Ví dụ trong `gradle.properties` (minh họa):

```properties
org.gradle.java.installations.fromEnv=JAVA21_HOME
```

Và đặt `JAVA21_HOME` trỏ vào thư mục cài JDK 21. Thuộc tính này **bổ sung** nguồn JDK để Gradle tìm kiếm; không thay thế định nghĩa `java.toolchain.languageVersion` trong project.

## 7. Mã Java 21 smoke test để phát hiện cấu hình sai

Khi đã cấu hình toolchain, đừng chỉ tin vào build file. Hãy dùng một class có **Java 21 syntax thật** để kiểm chứng compiler, test và runtime.

Lưu file **`Java21ToolchainSmoke.java`** ở `src/main/java` của Maven/Gradle project (nếu dự án dùng package có tên, bổ sung dòng `package` và đặt đúng thư mục). Ví dụ dưới đây không cần dependency ngoài:

```java
public class Java21ToolchainSmoke {
    sealed interface Result permits Ok, Error {}

    record Customer(String name) {}
    record Ok(Customer customer) implements Result {}
    record Error(int code) implements Result {}

    static String describe(Result result) {
        return switch (result) {
            case Ok(Customer(String name))
                    when name != null && !name.isBlank() ->
                    "OK:" + name;

            case Ok(var customer) ->
                    "OK_NO_NAME";

            case Error(int code) when code >= 500 ->
                    "SERVER_ERROR";

            case Error(int code) ->
                    "ERROR:" + code;

            case null -> "MISSING";
        };
    }

    public static void main(String[] args) {
        System.out.println(describe(
                new Ok(new Customer("Ada"))));
        System.out.println(describe(
                new Ok(new Customer(" "))));
        System.out.println(describe(new Ok(null)));
        System.out.println(describe(new Error(503)));
        System.out.println(describe(new Error(404)));
        System.out.println(describe(null));
    }
}
```

Biên dịch trực tiếp bằng JDK 21 hoặc JDK mới hơn có hỗ trợ `--release 21`:

```bash
javac --release 21 Java21ToolchainSmoke.java
java Java21ToolchainSmoke
```

**Stdout chính xác:**

```text
OK:Ada
OK_NO_NAME
OK_NO_NAME
SERVER_ERROR
ERROR:404
MISSING
```

Mã minh họa đã được thực thi bằng JDK 24 JShell theo cú pháp Java 21, cho ra sáu dòng trên. Nó dùng:

- **Sealed interface** để xác định tập `Result`.
- **Record patterns lồng** `Ok(Customer(String name))`.
- **Guard `when`**.
- **Fallback cụ thể** `Ok(var customer)` để xử lý customer null hoặc tên blank.
- **`case null`** ở cấp selector.
- **Switch expression exhaustive**, không cần `default` vì các biến thể `Result` đã được xử lý.

Một điều cần kiểm tra trong môi trường thật: `case Ok(Customer(String name))` **không khớp** khi chính `Customer` là null, nhưng `case Ok(var customer)` vẫn bắt được `Ok(null)`. Giữ nhánh fallback này tránh lỗi runtime do record pattern lồng không khớp.

### 7.1. Kiểm tra class-file version

Khi code đã biên dịch bằng `--release 21`, class file chính có **major version 65**. Kiểm tra bằng JDK tools:

```bash
javap -verbose Java21ToolchainSmoke
```

Trong output có dòng:

```text
major version: 65
```

Lệnh này giả định đang ở thư mục chứa class file; đối với Maven, class chính thường nằm trong `target/classes`, còn với Gradle thường trong `build/classes/java/main`. Nếu kiểm tra JAR, dùng classpath thích hợp với `javap -classpath ...`. `javap` phải dùng JDK đủ mới để đọc class file.

**Không nhầm:** class-file 65 cho biết bytecode Java 21; nó không bảo đảm ứng dụng đã được test trên Java 21, cũng không chứng minh mọi dependency đều chạy được trên JVM 21.

### 7.2. Vì sao demo này mạnh hơn một “Hello World”?

Một `Hello World` Java 8 vẫn biên dịch được với nhiều mức compiler nên không phát hiện IDE hoặc CI đang dùng nhầm Java 17. Một class có `switch` type patterns và `when` sẽ **không compile như source Java 17 final**; nếu pipeline thiếu Java 21 toolchain, lỗi thường xuất hiện ngay.

Tuy nhiên smoke test là một **phép kiểm tra nhanh**, không thay thế unit/integration tests về exception, nullable nested record, sealed exhaustive switch, domain logic và khả năng tương thích dependency.

## 8. IDE: đồng bộ Project SDK và build toolchain

Dù dùng IntelliJ IDEA, Eclipse hay VS Code, cần tách ba cài đặt:

- **Project SDK/JDK**: IDE dùng để phân tích code, autocomplete, compiler nội bộ.
- **Language level / source level**: IDE chấp nhận cú pháp Java 21 hay không.
- **Build tool settings**: Maven/Gradle có thể dùng JDK riêng. Cấu hình trong `pom.xml` hoặc `build.gradle(.kts)` nên là nguồn chuẩn được version control.

Hướng kiểm tra:

1. Đảm bảo IDE đã nhận diện một **JDK 21** và bật ngôn ngữ Java 21 cho module tương ứng.
2. Nếu dùng Maven, xem **Maven Runner JRE** và quá trình import project; nó có thể khác Project SDK. Nếu POM có Maven Toolchains, vẫn phải xác nhận JDK compiler thực sự được chọn.
3. Nếu dùng Gradle, xem **Gradle JVM** (JVM chạy Gradle daemon) và toolchain `java { ... }`. Không lấy một dropdown Gradle JVM làm bằng chứng rằng mọi `JavaCompile` dùng đúng JDK.
4. **Reimport/sync** project sau khi sửa build file. Nếu IDE vẫn báo `patterns in switch are not supported`, kiểm tra mức source language thay vì chỉ restart IDE.
5. Không chỉnh cấu hình IDE bằng tay mà bỏ qua việc cập nhật POM/Gradle: người khác và CI sẽ mất cấu hình.

**Tránh preview toggle ngẫu nhiên.** Khi code chỉ dùng pattern switch/record patterns final Java 21, IDE và build không cần `--enable-preview`. Nếu IDE nhắc preview, có thể project đang đặt source level cũ hoặc code sử dụng một tính năng preview khác.

## 9. CI: GitHub Actions khóa Java 21

CI cần chứng minh môi trường build **tái lập được** mà không phụ thuộc vào JDK có sẵn trên máy lập trình viên.

Ví dụ workflow Maven (đặt tại `.github/workflows/java21.yml`):

```yaml
name: Java 21 Verify

on:
  push:
  pull_request:

jobs:
  verify:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7

      - uses: actions/setup-java@v6
        with:
          distribution: temurin
          java-version: '21'
          cache: maven

      - name: Check Java
        run: |
          java -version
          javac -version
          ./mvnw -version

      - name: Build and test
        run: ./mvnw -B -ntp clean verify
```

Đoạn workflow giả định repository **đã có Maven Wrapper `mvnw` có quyền thực thi** và cấu hình POM ở mục trước. Nếu dự án không có wrapper, có thể dùng `mvn` có sẵn trên runner hoặc tạo/commit wrapper qua quy trình chuẩn của team.

Workflow trên dùng `actions/setup-java@v6` vì đây là thế hệ action stable mới tại thời điểm viết; nếu dùng self-hosted runner, phải kiểm tra phiên bản GitHub Actions Runner tương thích với Node runtime của actions v6. GitHub-hosted runner có thể được cập nhật mà không cần người học tự quản lý. Nếu dự án đã pin commit SHA của actions vì yêu cầu supply-chain security, tiếp tục dùng SHA được team phê duyệt thay vì đổi theo tên tag.

**Gradle variant:** thay `cache: maven` bằng `cache: gradle`, và chạy:

```bash
./gradlew --version
./gradlew -q javaToolchains
./gradlew --no-daemon clean test
```

Ở CI Gradle, nên dùng **Gradle Wrapper** đã khóa phiên bản, còn Gradle JVM/toolchain Java 21 phải được cấu hình theo mục 6. Nếu có tests cần JDK 21, xác minh Gradle test task sử dụng toolchain đó.

### 9.1. CI cần kiểm tra những gì?

- `java -version` và `javac -version` để kiểm tra PATH/JAVA_HOME trên runner.
- `mvn -version` hoặc `./gradlew --version` để biết JVM của build tool.
- Maven Toolchains/Gradle `javaToolchains` để biết JDK có thể chọn và JDK đang được dùng cho task.
- Compilation của class dùng **pattern switch + record patterns**, không chỉ class Java cũ.
- Unit/integration tests bằng Java 21.
- Artifact cuối (JAR, class file, container image) thực sự chạy trên JVM 21.
- Dependency cache tăng tốc build, **không** phải bằng chứng về việc version JDK đã đúng.

Có thể thêm job chạy bản JDK khác để kiểm tra compatibility, nhưng chỉ khi đó là mục tiêu hỗ trợ thật. **Không** chạy JAR Java 21 trên JVM 17 rồi coi thất bại là lỗi test không ổn định.

## 10. Docker và runtime thực thi

Build container và runtime container là hai môi trường tách biệt. Dự án Java 21 cần nhất quán cả hai:

```dockerfile
# Ví dụ cấu trúc multi-stage, cần điều chỉnh theo dự án.
FROM eclipse-temurin:21-jdk AS build
WORKDIR /workspace
COPY . .
RUN ./mvnw -B -ntp clean package

FROM eclipse-temurin:21-jre
WORKDIR /app
COPY --from=build /workspace/target/app.jar /app/app.jar
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
```

Đây là **Dockerfile template**, không phải bản build độc lập: cần một `mvnw` trong repo, POM có cấu hình package thành **executable JAR**, và output thật đúng tên `target/app.jar`. Nếu Maven sinh JAR tên khác, phải sửa đường dẫn `COPY`. Với dịch vụ production, cần áp dụng chính sách pin image digest, security updates và quản trị base image của team.

**Lưu ý:** build stage cần **JDK** vì có compiler; runtime stage có thể dùng **JRE Java 21** nếu ứng dụng không cần công cụ biên dịch lúc chạy. Runtime Java 17 sẽ không chạy được class Java 21 có **major version 65**.

Một bộ CI tốt nên test trực tiếp image cuối trong điều kiện phù hợp, vì JAR chạy trên host không tự chứng minh Docker image chứa đúng runtime.

## 11. Các lỗi build hay gặp và cách sửa

| Triệu chứng | Nguyên nhân phổ biến | Cách chẩn đoán và sửa |
| --- | --- | --- |
| `release version 21 not supported` hoặc `invalid target release: 21` | Compiler `javac` quá cũ | Kiểm tra `javac -version`, Maven/Gradle toolchain; chọn JDK 21+ |
| `patterns in switch statements are a preview feature` | Compiler/source level đang là Java 17–20 hoặc cấu hình preview cũ | Nếu mục tiêu Java 21 final, nâng JDK và `release=21`; không bật preview để né cấu hình sai |
| `No matching toolchain` (Maven) | Không tìm thấy JDK đạt điều kiện | Kiểm tra `toolchains.xml`/discovery, `jdkHome`, version range, vendor |
| `No matching toolchains found for requested specification` (Gradle) | Gradle không tìm thấy JDK 21 hoặc resolver chưa cấu hình | Chạy `./gradlew -q javaToolchains`; cài JDK 21 hoặc cấu hình provisioning |
| `Unsupported class file major version 65` trong build | Gradle/Groovy/ASM/plugin quá cũ để đọc bytecode Java 21 | Nâng Gradle Wrapper và các plugin tương thích |
| `UnsupportedClassVersionError` khi chạy JAR | JVM runtime thấp hơn class-file target | Kiểm tra `java -version` trong máy/container thật; chạy JVM 21+ |
| IDE báo lỗi `case Type variable`, CLI build lại thành công | IDE đang đặt Project SDK/language level cũ | Sync project, đặt module language level 21, kiểm tra plugin/IDE version |
| Build dùng được API Java 24 nhưng production Java 21 lỗi | Chỉ đặt `-source`/`-target` 21 bằng JDK mới | Dùng `--release 21`, kiểm tra dependencies và runtime |
| Một máy build được, máy khác thiếu JDK | `JAVA_HOME`/toolchain discovery khác nhau, thiếu cấu hình khai báo | Pin toolchain ở project; ghi rõ JDK provisioning; dùng wrapper và CI |
| Test bị lỗi dù compile thành công | Test JVM khác, plugin test không toolchain-aware hoặc dependency không tương thích | Kiểm tra Surefire/Gradle Test task, plugin/test dependency và JVM thực chạy |
| Bật `--enable-preview` nhưng vẫn báo syntax | Tính năng preview không thuộc đúng release/JDK hoặc syntax đã đổi | Xác định target release, dùng syntax final Java 21 cho pattern switch |

**Hai lỗi hay bị đánh đồng:**

- `Unsupported class file major version 65` có thể là **build tool/plugin** không đọc được bytecode Java 21, không nhất thiết là JVM production từ chối chạy ứng dụng.
- `UnsupportedClassVersionError` do JVM runtime không hỗ trợ phiên bản class file; ví dụ Java 17 chỉ hỗ trợ đến major 61, trong khi Java 21 là major 65.

Cần đọc **stack trace và giai đoạn lỗi**: import IDE, compile, test, package hay startup. Không sửa bằng cách hạ mọi `target` xuống 17 nếu source thật sự đang sử dụng Java 21 pattern matching.

## 12. Cấu hình release trong dự án đa module

Một repository có thể có module legacy Java 17 và module mới Java 21:

- Module Java 17 cần `--release 17`, compiler/JDK phù hợp và không import API Java 21.
- Module Java 21 cần `--release 21` và các plugin xử lý source/bytecode Java 21.
- Nếu module Java 17 **phụ thuộc vào class Java 21**, cần thiết kế lại ranh giới dependency; một module chạy trên JVM 17 không thể tải class file Java 21.
- Khi biên dịch source Java 17 bằng JDK 21, `--release 17` giúp giới hạn API Java SE 17, nhưng phải kiểm tra **dependency thư viện ngoài** cũng có bytecode phù hợp.
- Không đặt `release=21` ở POM cha nếu các module con vẫn phải phát hành bytecode Java 17 mà không có override có chủ đích.

Với Maven có thể khai báo `maven.compiler.release` theo module hoặc profile, nhưng profile không nên làm môi trường build thay đổi một cách khó thấy. Với Gradle, từng subproject có thể cấu hình `java.toolchain` và `options.release` riêng. Test/cross-module dependency phải phản ánh đúng **ma trận runtime cần hỗ trợ**.

**Nguyên tắc:** version Java ở build file là **hợp đồng hỗ trợ**, không phải thông số chỉ để build xanh trên máy hiện tại.

## 13. Checklist trước khi merge cấu hình Java 21

- [ ] JDK **21** đã cài và `java -version` / `javac -version` hợp lệ trong môi trường local hoặc toolchain discovery.
- [ ] Maven `maven.compiler.release=21` hoặc Gradle `options.release=21` được đặt rõ ràng.
- [ ] Maven Toolchains Plugin hoặc Gradle `java.toolchain.languageVersion=21` chọn đúng JDK, không chỉ đổi `JAVA_HOME`.
- [ ] Gradle Wrapper tương thích với **JVM chạy Gradle** (ít nhất 8.5 nếu daemon chạy JDK 21).
- [ ] Compiler/test/Javadoc/codegen plugins tương thích với Java 21.
- [ ] IDE đã sync JDK, language level và bản build tool; CI không lệ thuộc cài đặt IDE.
- [ ] CI cài JDK 21, in log phiên bản và chạy unit/integration tests.
- [ ] Runtime/container thật dùng Java 21+ và đã kiểm tra artifact có **class-file major 65**.
- [ ] Pattern switch/record patterns final Java 21 **không phụ thuộc `--enable-preview`**.
- [ ] Có smoke test Java 21 với `case Type`, `when`, record pattern, null và sealed exhaustiveness.
- [ ] Không vô tình đổi API/runtime target của các module vẫn cần hỗ trợ Java 17.
- [ ] Build dùng Maven/Gradle Wrapper và chính sách pin dependency/plugin version để tái lập trong team.

**Kết luận:** Cấu hình đúng Java 21 toolchain không chỉ là chọn “Project SDK = 21”. Hãy khai báo **JDK build** (Maven Toolchains/Gradle Java Toolchains), **language + API target** (`--release 21`), **JVM chạy test và production**, rồi xác minh bằng một class có **Java 21 pattern switch thật**. Cách này giúp code JEP 440/441 build nhất quán giữa máy lập trình viên, IDE, CI và container, đồng thời phát hiện sớm lỗi từ toolchain, plugin và runtime không tương thích.

### Tài liệu tham khảo

- Oracle Java 21 — Pattern Matching for switch: https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html
- OpenJDK JEP 441 — Pattern Matching for switch: https://openjdk.org/jeps/441
- OpenJDK JEP 440 — Record Patterns: https://openjdk.org/jeps/440
- Apache Maven Compiler Plugin — Setting --release: https://maven.apache.org/plugins/maven-compiler-plugin/examples/set-compiler-release.html
- Apache Maven Toolchains Plugin — JDK Discovery: https://maven.apache.org/plugins/maven-toolchains-plugin/toolchains/jdk-discovery.html
- Apache Maven — Guide to Using Toolchains: https://maven.apache.org/guides/mini/guide-using-toolchains
- Apache Maven Surefire — Test JVM toolchain: https://maven.apache.org/surefire/maven-surefire-plugin/test-mojo
- Gradle — Toolchains for JVM projects: https://docs.gradle.org/current/userguide/toolchains.html
- Gradle — Java Compatibility Matrix: https://docs.gradle.org/current/userguide/compatibility.html
- GitHub Actions — setup-java: https://github.com/actions/setup-java
