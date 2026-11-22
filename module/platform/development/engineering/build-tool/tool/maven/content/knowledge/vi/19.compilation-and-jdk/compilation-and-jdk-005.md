# Maven Toolchains Plugin và tệp toolchains.xml

Một hệ thống Java có thể phải hỗ trợ Java 17 dù máy developer hoặc CI chạy Maven bằng JDK 21. Nếu cứ thay `JAVA_HOME` cho từng dự án hoặc hardcode đường dẫn `javac` trong `pom.xml`, build dễ khác nhau giữa Windows, Linux và CI.

**Maven Toolchains** tách **JDK chạy chính Maven** khỏi **JDK dùng bởi những plugin hiểu toolchain**, như Compiler, Surefire, Failsafe, Javadoc và một số plugin khác. Dự án yêu cầu một JDK trong POM; từng máy cung cấp vị trí JDK qua `~/.m2/toolchains.xml`, hoặc dùng cơ chế phát hiện JDK của Maven Toolchains Plugin từ phiên bản 3.2.0. Plugin lựa chọn và chia sẻ toolchain với các plugin hỗ trợ. Nó **không cài JDK mới**, **không thay JAVA_HOME của shell**, **không khởi động lại Maven trong một JVM khác** và **không bắt mọi plugin Java tự dùng JDK đã chọn**.

Bài học này đi từ mô hình, file XML, POM, lệnh CLI, hai cách lựa chọn, tới ví dụ **Java 17 chạy được**, kiểm thử JDK test thực tế, CI và xử lý lỗi.

## 1. Phân biệt Maven runtime JDK, toolchain JDK và Java target

Ba khái niệm phải được kiểm tra **độc lập**:

| Khái niệm | Chức năng | Cách quan sát |
| --- | --- | --- |
| JDK chạy Maven | JVM thực thi Maven Core và mã Java của Maven plugins | `mvn --version`; `JAVA_HOME`/launcher |
| JDK toolchain được chọn | Cung cấp `javac`, `java`, `javadoc`... cho plugin **toolchain-aware** | Log Toolchains Plugin, plugin configuration, test runtime |
| Java target/release | Phiên bản ngôn ngữ, Java API và class-file của artifact | Compiler Plugin `release`, `javap -verbose` |

Ví dụ một build:

```text
Maven Core       → chạy bằng JDK 21
Toolchains       → chọn JDK 17
Compiler Plugin  → dùng javac JDK 17 và --release 17
Surefire Plugin  → fork test JVM JDK 17
JAR output       → class-file major version 61
Production       → chạy trên JDK 17 (hoặc bản tương thích hơn)
```

Vì thế **`mvn --version` hiện Java 21 không chứng minh compile cũng chạy JDK 21**. Và ngược lại, `<release>17</release>` chỉ bảo đảm mục tiêu biên dịch tương ứng Java 17 khi compiler hỗ trợ, **không bảo đảm công cụ thực thi là JDK 17**. JDK 21 vẫn có thể tạo bytecode/API Java 17 bằng `--release 17`.

### 1.1. Toolchains khác Maven Wrapper

Maven Wrapper (`./mvnw`, `mvnw.cmd`) quản lý phiên bản Maven distribution. Toolchains quản lý **JDK/tool được dùng trong build**, không tải Maven distribution và không tự setup JDK. Có thể dùng cả hai: Maven Wrapper pin Maven 3.9.x, CI cung cấp JDK 21 chạy Maven, Toolchains chọn JDK 17 cho compiler/test.

### 1.2. Toolchains khác settings.xml

| File | Công dụng |
| --- | --- |
| `pom.xml` | Yêu cầu toolchain, version/plugin executions, source/target/release |
| `toolchains.xml` | Các JDK đã có trên máy và `jdkHome` tương ứng |
| `settings.xml` | Repositories, mirrors, proxy, credentials, local repository, profiles |
| `maven-wrapper.properties` | Maven distribution URL/version của Wrapper |

Không đặt `<toolchain>` vào `settings.xml`. Đường dẫn JDK cá nhân cũng không nên hardcode vào POM chung.

## 2. Toolchains hoạt động trong lifecycle ra sao?

Một cấu hình tiêu chuẩn có luồng:

```text
POM yêu cầu JDK [17,18)
    |
    v
maven-toolchains-plugin:toolchain (phase validate)
    |
    v
Đọc user/global toolchains.xml
    |
    +-- không có JDK match --> FAIL ở validate
    |
    +-- có JDK match --> lưu Toolchain trong MavenSession
                             |
                             +-- compiler:compile/testCompile
                             +-- surefire:test, failsafe:integration-test
                             +-- javadoc:javadoc
                             +-- các goal hỗ trợ toolchain khác
```

**Maven Core tiếp tục chạy trong JVM ban đầu.** Toolchains Plugin cung cấp cho toolchain-aware plugin một đối tượng có thể truy tìm executable, chẳng hạn `jdkHome/bin/javac`. Đối với plugin **không** hỗ trợ toolchains, không có cam kết nó sẽ dùng JDK đã chọn.

Goal `toolchains:toolchain` mặc định được gắn với phase `validate`, nhưng **cần khai báo execution hoặc gọi goal** để nó chạy. Chỉ việc đặt `~/.m2/toolchains.xml` lên máy không tự làm toàn bộ build đổi JDK.

Một số plugin Apache Maven hỗ trợ JDK toolchain từ các version nhất định: Compiler, Surefire, Failsafe, Javadoc, Jarsigner và một số plugin cho Jdeps, Jlink hoặc tạo metadata JAR. Với từng goal/phần chức năng, xem tài liệu **đúng plugin version**. Chẳng hạn JAR Plugin có hỗ trợ liên quan `Build-Jdk-Spec` manifest, không phải một compiler riêng.

## 3. Cú pháp toolchains.xml và nơi lưu

User toolchains file thông dụng:

```text
Linux/macOS:  ~/.m2/toolchains.xml
Windows:      C:\Users\<username>\.m2\toolchains.xml
```

Tệp này mô tả **các công cụ đã cài**; không phải danh sách dependencies hay POM. Ví dụ hoàn chỉnh:

```xml
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
</toolchains>
```

Đường dẫn `/opt/jdks/jdk-17` **chỉ minh họa**. Phải thay bằng root JDK 17 **thật** trên máy; root đó cần chứa `bin/java` và `bin/javac`. Trên macOS, đường dẫn JDK thường kết thúc bằng `Contents/Home`; trên Windows có thể là `C:\Java\jdk-17`.

| Phần tử | Ý nghĩa |
| --- | --- |
| `<toolchains>` | Root gồm các toolchain entries |
| `<toolchain>` | Một toolchain có thể được chọn |
| `<type>jdk</type>` | Loại JDK |
| `<provides>` | Nhãn đặc tính để so khớp yêu cầu từ POM |
| `<version>17</version>` | Nhãn version được công bố |
| `<vendor>temurin</vendor>` | Nhãn nhà cung cấp nếu muốn giới hạn |
| `<configuration><jdkHome>` | Thư mục gốc JDK hiện có |

Một `toolchains.xml` có thể khai báo **nhiều JDK**, ví dụ 17 và 21, để nhiều project cùng dùng mà không đổi `JAVA_HOME` liên tục.

### 3.1. Hai entries JDK 17 và 21

```xml
<?xml version="1.0" encoding="UTF-8"?>
<toolchains>
    <toolchain>
        <type>jdk</type>
        <provides>
            <version>17</version>
            <vendor>temurin</vendor>
        </provides>
        <configuration>
            <jdkHome>/opt/jdks/temurin-17</jdkHome>
        </configuration>
    </toolchain>
    <toolchain>
        <type>jdk</type>
        <provides>
            <version>21</version>
            <vendor>temurin</vendor>
        </provides>
        <configuration>
            <jdkHome>/opt/jdks/temurin-21</jdkHome>
        </configuration>
    </toolchain>
</toolchains>
```

Cả hai `jdkHome` trên chỉ là **đường dẫn ví dụ**, cần thay theo máy thật. Phần `vendor` tùy chọn: nó là nhãn để match, không phải một chữ ký đảm bảo JDK đến từ hãng đó. Nếu POM đòi `vendor=temurin` mà user toolchains chỉ khai báo `vendor=azul`, sẽ không match dù đều là Java 17.

### 3.2. Cấu hình trên Windows

```xml
<?xml version="1.0" encoding="UTF-8"?>
<toolchains>
    <toolchain>
        <type>jdk</type>
        <provides>
            <version>17</version>
        </provides>
        <configuration>
            <jdkHome>C:\Java\jdk-17</jdkHome>
        </configuration>
    </toolchain>
</toolchains>
```

Dấu `\` trong XML text không được escape giống Java string. Nếu root thật có khoảng trắng như `C:\Program Files\Java\...`, có thể đặt đầy đủ đường dẫn trong `<jdkHome>`. Khi truyền file XML bằng CLI, PowerShell cần quote đường dẫn có dấu cách.

**Cảnh báo:** Với toolchains thủ công, Maven so khớp nhãn trong `<provides>`, không tự xác minh một cách sâu rằng `<version>17</version>` thật sự trùng JDK ở `jdkHome`. Người dùng vẫn phải kiểm tra:

```bash
# Linux/macOS - thay đường dẫn bằng JDK 17 thực tế
/opt/jdks/jdk-17/bin/java -version
/opt/jdks/jdk-17/bin/javac -version
```

`java -version` và `javac -version` phải báo 17. Đừng ghi `version=17` nhưng trỏ `jdkHome` sang JDK 21 rồi nghĩ Maven sẽ đổi công cụ thành Java 17.

## 4. So khớp version và vendor: exact khác range

Trong POM, yêu cầu JDK 17 nên dùng:

```xml
<configuration>
    <toolchains>
        <jdk>
            <version>[17,18)</version>
        </jdk>
    </toolchains>
</configuration>
```

Đây là **đoạn XML của Maven Toolchains Plugin** theo goal truyền thống.

| Yêu cầu version | Ý nghĩa |
| --- | --- |
| `17` | So khớp **version nhãn** được khai báo, không tự đồng nghĩa với mọi JDK 17.x |
| `17.0.20` | Chọn nhãn version tương ứng nếu được khai báo y hệt |
| `[17,18)` | Mọi version thuộc nhánh Java 17, kể cả nhãn `17` hoặc `17.0.20` |
| `[17,)` | Java 17 **hoặc mới hơn**, có thể chọn JDK 21/25... |
| `[21,22)` | Nhánh Java 21 |

Trong `toolchains.xml` do tool discovery hoặc chương trình khác sinh, version có thể là patch version `17.0.20`, trong khi file người dùng viết tay chỉ khai `17`. **`[17,18)`** linh hoạt hơn `17` khi muốn chấp nhận mọi patch của Java 17.

Có thể yêu cầu cả vendor:

```xml
<configuration>
    <toolchains>
        <jdk>
            <version>[17,18)</version>
            <vendor>temurin</vendor>
        </jdk>
    </toolchains>
</configuration>
```

Version và vendor **đều phải khớp**. Ngoài `version`, các token trong `<provides>` là nhãn cho việc matching, không nhất thiết mang semantics kỹ thuật nâng cao. Dùng vendor chỉ khi có policy cụ thể; với nhiều đội dùng các JDK17 distribution đã được test, giới hạn vendor tùy tiện có thể làm giảm portability.

## 5. Khai báo Maven Toolchains Plugin trong POM

Một cấu hình lựa chọn thủ công ở `<build><plugins>`:

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-toolchains-plugin</artifactId>
    <version>3.3.0</version>
    <executions>
        <execution>
            <id>require-jdk17</id>
            <phase>validate</phase>
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
```

Các ý chính:

- `<goal>toolchain</goal>` làm plugin **thực thi**, không chỉ được khai báo.
- `<phase>validate</phase>` chọn toolchain sớm trước compile/test.
- `<toolchains><jdk><version>` mô tả **yêu cầu**, không chứa đường JDK thật.
- `toolchains.xml` nằm riêng trên từng máy và cung cấp `jdkHome`.
- Nếu không tìm được toolchain phù hợp, build **thất bại ở lựa chọn toolchain**, thay vì âm thầm biên dịch sai JDK.

**Đừng chỉ đặt đoạn trên trong `<pluginManagement>` rồi kết luận nó sẽ chạy**. `pluginManagement` quản lý version/configuration cho plugin khi được sử dụng; actual plugin declaration hoặc lifecycle binding mới làm goal thực thi.

### 5.1. Chọn toolchains file khác bằng -t

Từ Maven 3.3.1, có thể sử dụng `-t`/`--toolchains`:

```bash
# Linux/macOS, thay bằng file thật
mvn -t /path/to/toolchains.xml -B clean verify
```

```powershell
# Windows PowerShell
mvn.cmd -t "C:\CI\toolchains.xml" -B clean verify
```

Theo hướng dẫn Maven, file user mặc định ở `${user.home}/.m2/toolchains.xml`. Tùy chọn `-gt`/`--global-toolchains` chỉ định global toolchains file. Với Maven 4, tên hiện đại là `-it`/`--install-toolchains` cho installation toolchains; `-gt` vẫn có thể xuất hiện nhưng được đánh dấu deprecated.

Phân biệt:

| Lệnh | Chọn file |
| --- | --- |
| `mvn -f path/to/pom.xml` | POM/project |
| `mvn -s path/to/settings.xml` | Maven settings |
| `mvn -t path/to/toolchains.xml` | Maven toolchains |
| `mvn --version` | Chỉ in Maven runtime/JDK host |

Không dùng `-s` để chọn toolchains, cũng không dùng `-t` để chọn POM.

## 6. Ví dụ Java 17 hoàn chỉnh: build và unit test bằng JDK17 toolchain

Bài thực hành có thể chạy trên Maven 3.9.x và JDK17+ đã cài. **Maven có thể chạy bằng JDK21**, nhưng các plugin toolchain-aware sẽ nhận **JDK17** từ `toolchains.xml`. Ta sẽ:

1. Lựa chọn toolchain theo version range `[17,18)`.
2. Biên dịch code bằng Compiler Plugin 3.13.0 và `release=17`.
3. Chạy JUnit Jupiter tests với Surefire Plugin 3.5.2, xác minh JVM **thực sự dùng Java 17**.
4. Đóng JAR và chạy Java main, kiểm tra stdout chính xác.

### 6.1. Cấu trúc thư mục

```text
jdk-toolchain-demo/
├── pom.xml
└── src/
    ├── main/java/vn/example/toolchain/App.java
    └── test/java/vn/example/toolchain/AppTest.java

# File ngoài source project:
~/.m2/toolchains.xml
```

Dùng toolchains.xml ở mục 3, sửa `jdkHome` cho đúng root JDK 17 có thật. Trên Windows dùng user toolchains file tại `C:\Users\<username>\.m2\toolchains.xml`.

### 6.2. POM đầy đủ

File `jdk-toolchain-demo/pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>vn.example</groupId>
    <artifactId>jdk-toolchain-demo</artifactId>
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
            <version>5.11.0</version>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-toolchains-plugin</artifactId>
                <version>3.3.0</version>
                <executions>
                    <execution>
                        <id>select-java17</id>
                        <phase>validate</phase>
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
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-resources-plugin</artifactId>
                <version>3.3.1</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
                <configuration>
                    <release>${maven.compiler.release}</release>
                </configuration>
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
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-clean-plugin</artifactId>
                <version>3.3.2</version>
            </plugin>
        </plugins>
    </build>
</project>
```

Giải thích:

- Goal Toolchains Plugin được bind vào `validate`.
- Compiler có hai ràng buộc riêng: **JDK được chọn** và **`release=17`**. Dù compiler dùng JDK17, vẫn nên pin release rõ ràng.
- Surefire được pin version hỗ trợ JDK toolchain. Theo tài liệu Surefire, khi main toolchain đã được cấu hình, Surefire mặc định dùng nó để khởi chạy test JVM.
- JUnit Jupiter chỉ ở `test` scope; JAR ứng dụng không cần JUnit trong runtime.
- Các plugin versions được pin nhằm tránh thay đổi bất ngờ giữa lần build.

### 6.3. Mã Java ứng dụng

File `src/main/java/vn/example/toolchain/App.java`:

```java
package vn.example.toolchain;

public final class App {
    private App() {
    }

    public static String message() {
        return "Toolchains: JDK 17 build OK";
    }

    public static void main(String[] args) {
        System.out.println(message());
    }
}
```

Dòng in ở đây là literal trong code để có output kiểm chứng ổn định. **Nó không tự phát hiện JDK runtime**; để xác nhận JDK thật sự được chọn, cần log/toolchain/test bên dưới.

### 6.4. JUnit test kiểm tra test JVM

File `src/test/java/vn/example/toolchain/AppTest.java`:

```java
package vn.example.toolchain;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class AppTest {
    @Test
    void messageIsStable() {
        assertEquals("Toolchains: JDK 17 build OK", App.message());
    }

    @Test
    void testsRunOnSelectedJdk() {
        assertEquals("17", System.getProperty("java.specification.version"));
    }
}
```

Test `testsRunOnSelectedJdk` được chạy trong **JVM của Surefire**, có thể khác JVM đang chạy Maven. Test này fail nếu test thực sự chạy JDK21 (và không bị sửa assertion), giúp nhận diện một build không dùng test JDK đúng quy định.

Nếu project có cấu hình Surefire `<jdkToolchain>` hoặc `<jvm>` riêng, phải kiểm tra nó có ghi đè session toolchain hay không trước khi kết luận.

### 6.5. Kiểm tra cài JDK và chạy build

Từ `jdk-toolchain-demo`:

```bash
java -version
mvn --version
mvn -B clean verify
java -cp target/jdk-toolchain-demo-1.0.0.jar vn.example.toolchain.App
```

Điều kiện là file user toolchains ở đúng chỗ, `jdkHome` trỏ tới **JDK 17 thật**, các dependencies/plugins tải được và Maven runtime dùng một JVM phù hợp plugin. Build Maven chạy qua validate, resources, compile, test, package, verify; Surefire chạy hai test rồi JAR được tạo.

**Stdout chính xác của lệnh `java -cp` cuối cùng** trên một JVM đủ mới (Java17+):

```text
Toolchains: JDK 17 build OK
```

Đây **không phải toàn bộ log Maven**. Log Maven có thêm thông tin toolchain selection, plugin execution, test reports và repository activity.

Một lưu ý quan trọng: lệnh `java -cp` **ngoài Maven** dùng lệnh `java` của shell (thường từ `PATH`). Toolchains Plugin không tự thay đổi `JAVA_HOME` của terminal sau build. Nếu shell dùng JDK11, chạy class Java17 có thể báo `UnsupportedClassVersionError`; đó không phải bằng chứng Toolchains Plugin thất bại.

### 6.6. Kiểm tra bytecode Java 17

Sau khi build:

```bash
javap -verbose -classpath target/classes vn.example.toolchain.App
```

Tìm dòng:

```text
major version: 61
```

Major version 61 tương ứng class-file Java 17. Lệnh `javap` cũng có thể chạy từ JDK21 để đọc class Java17; không dùng phiên bản của chính `javap` làm bằng chứng compiler đã dùng JDK17.

Để xác minh toàn diện, đối chiếu:

- Log Maven cho biết goal `toolchains:toolchain` chọn JDK/path nào.
- Compiler Plugin có compile theo toolchain hoặc path `javac` không.
- Surefire test `java.specification.version` bằng 17.
- Bytecode main class có major version 61.
- Java runtime khi triển khai có hỗ trợ class-file Java17.

## 7. Cơ chế mới từ 3.2.0: JDK discovery và select-jdk-toolchain

Maven Toolchains Plugin **3.2.0+** có cơ chế phát hiện JDK cài đặt tự động, dựa trên những đường dẫn quen thuộc và biến môi trường. Mục đích là giảm nhu cầu viết tay `toolchains.xml` ở từng máy.

Trong Plugin 3.3.0:

| Goal | Vai trò |
| --- | --- |
| `toolchains:toolchain` | Dùng yêu cầu POM để chọn từ các toolchains đã khai báo trong `toolchains.xml` |
| `toolchains:select-jdk-toolchain` | Chọn JDK từ **discovered JDKs và các toolchain đã đăng ký**, theo constraints |
| `toolchains:display-discovered-jdk-toolchains` | Hiển thị danh sách JDK mà plugin phát hiện |
| `toolchains:generate-jdk-toolchains-xml` | Sinh nội dung file XML từ danh sách phát hiện để bạn xem/copy |

Điều này không có nghĩa plugin cài JDK. Nếu không có JDK17 trên máy, **dù discovery hay file thủ công đều không biến máy thành JDK17**.

### 7.1. Xem JDK nào được phát hiện

```bash
mvn org.apache.maven.plugins:maven-toolchains-plugin:3.3.0:display-discovered-jdk-toolchains
```

Thông tin thường gồm `version`, `runtime.name`/`runtime.version`, `vendor`, `current` (JDK Maven đang dùng), `lts` và `env` (những biến môi trường trỏ đến JDK). Phát hiện là **heuristic**: không bảo đảm tìm được JDK ở mọi vị trí đặc biệt; nếu thiếu, cấu hình file thủ công là lựa chọn đáng tin.

### 7.2. Cấu hình goal discovery thay thế goal toolchain

Để dùng discovery cho bài thực hành, **thay thế** đoạn `maven-toolchains-plugin` trong POM ở mục 6.2 bằng đoạn sau (không bind cả hai cơ chế với requirements mâu thuẫn):

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-toolchains-plugin</artifactId>
    <version>3.3.0</version>
    <executions>
        <execution>
            <id>discover-jdk17</id>
            <phase>validate</phase>
            <goals>
                <goal>select-jdk-toolchain</goal>
            </goals>
        </execution>
    </executions>
    <configuration>
        <version>[17,18)</version>
        <useJdk>Never</useJdk>
    </configuration>
</plugin>
```

**Khác biệt cú pháp:** goal truyền thống đặt version ở `<toolchains><jdk><version>`, còn goal `select-jdk-toolchain` nhận constraint `<version>` **trực tiếp trong `<configuration>`**. Đó không phải hai thẻ có thể đổi chỗ tùy ý.

`<useJdk>Never</useJdk>` yêu cầu plugin thực hiện selection ngay cả khi JDK host thỏa constraints, phù hợp khi muốn thấy rõ đường toolchain được chọn. Nếu JDK17 không có trong danh sách discovered hoặc user toolchains, vẫn sẽ không có match.

### 7.3. Ba giá trị useJdk

| Giá trị | Ý nghĩa |
| --- | --- |
| `IfMatch` (mặc định) | Nếu JDK chạy Maven đã thỏa yêu cầu, có thể **không chọn** toolchain riêng để tiết kiệm overhead |
| `IfSame` | Tránh chọn toolchain nếu toolchain được lựa chọn chính là runtime JDK hiện tại |
| `Never` | Luôn chọn một toolchain từ các JDK phù hợp |

Nếu Maven đang chạy bằng JDK17 và request `[17,18)`, `IfMatch` có thể không tạo một selection riêng. **Không đồng nghĩa goal bị lỗi**; host JDK đã phù hợp. Nếu Maven chạy JDK21 mà request `[17,18)`, JDK21 không match, goal phải tìm JDK17 khác.

### 7.4. Các constraints và user properties

Goal discovery cung cấp những tham số có thể cấu hình qua XML hoặc user property:

- `toolchain.jdk.version`: version hoặc range, chẳng hạn `[17,18)`.
- `toolchain.jdk.vendor`: tên vendor nhận diện khi discovery.
- `toolchain.jdk.env`: yêu cầu tương ứng biến môi trường cụ thể như `JAVA17_HOME`.
- `toolchain.jdk.runtime.name` và `toolchain.jdk.runtime.version`: ràng buộc thông tin runtime.
- `toolchain.jdk.mode`: chế độ `IfMatch`, `IfSame` hoặc `Never`.
- `toolchain.jdk.comparator`: thứ tự ưu tiên nếu nhiều JDK match.
- `toolchain.jdk.discover`: bật/tắt phát hiện JDK.

Lệnh minh họa kết hợp goal + build phase trong cùng Maven invocation:

```bash
mvn org.apache.maven.plugins:maven-toolchains-plugin:3.3.0:select-jdk-toolchain -Dtoolchain.jdk.version="[17,18)" compile
```

Dấu quote quanh range giúp tránh shell diễn giải ký tự đặc biệt. Để chọn một JDK được tham chiếu từ biến `JAVA17_HOME`, có thể dùng `-Dtoolchain.jdk.env=JAVA17_HOME` khi biến và JDK tồn tại.

### 7.5. comparator và các JDK phù hợp

Khi constraint cho phép nhiều JDK như `[17,)`, goal discovery có thể chọn theo `comparator`. Giá trị mặc định là:

```text
lts,current,env,version,vendor
```

Các tiêu chí gồm ưu tiên bản LTS, bản đang chạy Maven, bản có environment variable, bản version cao hơn, rồi vendor để ổn định thứ tự. Vì vậy nếu **phải** chạy Java17 chính xác, đừng dùng `[17,)` rồi mong comparator luôn chọn 17; nên request `[17,18)`.

### 7.6. Sinh toolchains.xml từ JDK được phát hiện

```bash
mvn org.apache.maven.plugins:maven-toolchains-plugin:3.3.0:generate-jdk-toolchains-xml
```

Goal tạo nội dung XML theo các JDK đã phát hiện để xem/copy. **Không giả định nó tự ghi đè an toàn** `~/.m2/toolchains.xml` cũ. Kiểm tra output rồi quyết định cập nhật file. Plugin có thể cache discovery ở file riêng `~/.m2/discovered-jdk-toolchains-cache.xml` để tăng tốc; file đó **khác** user `toolchains.xml`.

Nếu muốn goal discovery **chỉ** xét toolchains do tổ chức đăng ký thay vì heuristic, có thể cấu hình `<discoverToolchains>false</discoverToolchains>` và bảo đảm file `toolchains.xml` đã có entries phù hợp.

## 8. jdkToolchain của Compiler Plugin: chọn theo plugin, không phải toàn session

Ngoài global toolchain được Maven Toolchains Plugin lựa chọn, Compiler Plugin 3.6+ hỗ trợ một **`jdkToolchain` riêng**. Ví dụ trong Compiler Plugin 3.13.0:

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-compiler-plugin</artifactId>
    <version>3.13.0</version>
    <configuration>
        <release>17</release>
        <jdkToolchain>
            <version>[17,18)</version>
        </jdkToolchain>
    </configuration>
</plugin>
```

Điều này có thể **ghi đè global session toolchain cho việc compile**, nếu project chủ ý dùng compiler khác các plugin khác. So sánh:

- `maven-toolchains-plugin`: thiết lập toolchain **dùng chung** cho các plugin biết dùng toolchain.
- `maven-compiler-plugin/jdkToolchain`: chọn **riêng compiler**.
- `maven-compiler-plugin/release`: mục tiêu API/bytecode.
- `JAVA_HOME`: thường chọn JDK **khởi động Maven**, không phải khai báo compiler toolchain.

**Chỉ đặt compiler-specific jdkToolchain không bảo đảm Surefire/Javadoc sẽ dùng cùng JDK**. Muốn kiểm thử bằng JDK17, vẫn cần session toolchain hoặc cấu hình riêng cho Surefire.

### 8.1. Tình huống compile Java17, test Java21

Có thể tạo class Java17 bằng Compiler Toolchain JDK17 rồi chạy tests bằng JDK21 để xác minh tương thích forward. Surefire cũng hỗ trợ `jdkToolchain` riêng, ví dụ:

```xml
<configuration>
    <jdkToolchain>
        <version>[21,22)</version>
    </jdkToolchain>
</configuration>
```

Đây là **đoạn Surefire configuration**, không phải một POM hoàn chỉnh. Nếu dùng Java21 chạy test, cần sửa test `assertEquals("17", ...)` ở mục 6.4 hoặc xây ma trận test riêng.

**Điểm quan trọng:** test Java21 thành công **không chứng minh** artifact chạy Java17. Nếu production Java17, cần ít nhất một test/integration run trên Java17, không chỉ compile `--release 17`.

## 9. Phân biệt Toolchains, --release, source/target và Enforcer

| Cơ chế | Kiểm soát | Không tự bảo đảm |
| --- | --- | --- |
| `<release>17</release>` | API và class-file target Java17 khi compiler hỗ trợ | Không tự chuyển compiler executable sang JDK17 |
| `<source>17</source>` + `<target>17</target>` | Syntax/class-file version | Không hạn chế hoàn chỉnh API của JDK mới như `--release` |
| Toolchains Plugin | JDK sẵn có được công bố cho plugin toolchain-aware | Không restart Maven JVM hoặc mọi plugin Java |
| Compiler Plugin `jdkToolchain` | Compiler riêng dùng JDK theo yêu cầu | Không tự buộc Surefire dùng JDK đó |
| Surefire `jdkToolchain` | Test JVM theo JDK yêu cầu | Không thay JDK chạy Maven |
| Enforcer `requireJavaVersion` | Phiên bản JDK của JVM đang chạy Maven | Không xác minh trực tiếp toolchain-selected JDK |
| Maven Wrapper | Maven distribution version | Không tự tải JDK17 |
| CI setup JDK | Cài JDK thực trên runner | Không cấu hình toolchain goal nếu POM chưa có |

Nếu đội muốn Maven chạy JDK21, nhưng biên dịch/test trên Java17, cần **hai kiểm soát**:

1. CI/launcher/Enforcer xác minh Maven runtime JDK21 nếu policy yêu cầu.
2. Toolchains chọn JDK17, Compiler đặt `release=17`, Surefire test trên JDK17 và assert runtime.

Đừng sử dụng Enforcer `requireJavaVersion` như một cách thay thế `toolchains.xml`; rule mặc định xem JDK chạy **Maven**, không phải JDK toolchain.

## 10. Parent POM, pluginManagement và reactor nhiều module

Đội có nhiều service có thể đặt Toolchains Plugin ở **parent POM** để các module dùng policy JDK chung. Nếu parent khai báo execution trong `<build><plugins>` và child kế thừa bình thường, goal có thể chạy trong child.

Ví dụ parent chỉ **quản lý** Toolchains Plugin:

```xml
<build>
    <pluginManagement>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-toolchains-plugin</artifactId>
                <version>3.3.0</version>
                <executions>
                    <execution>
                        <id>select-jdk17</id>
                        <phase>validate</phase>
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
    </pluginManagement>
</build>
```

**Đoạn này chỉ thuộc `pluginManagement`**, nên không tự kích hoạt Toolchains Plugin. Child phải có actual plugin declaration hoặc parent khai báo actual execution trong `<build><plugins>`.

**Aggregation khác inheritance**: root có `<modules>` giúp Maven reactor build nhiều module, còn child kế thừa khi có `<parent>`. Một module không tự kế thừa Toolchains Plugin chỉ vì nó nằm trong `<modules>` của aggregator.

Nếu có module cần JDK17 và module cần JDK21, không nên đoán session toolchain dùng cho tất cả một cách đúng đắn. Có thể:

- Chạy hai invocation Maven/CI jobs riêng với constraints khác nhau.
- Cấu hình toolchain theo module/goal được kiểm chứng.
- Sử dụng `jdkToolchain` theo từng plugin khi cần compiler/test khác nhau.
- Kiểm tra effective POM và MavenSession thực tế trong reactor.

**Lưu ý song song:** goal `select-jdk-toolchain` 3.3.0 theo tài liệu **không được đánh dấu thread-safe**; khi dùng `mvn -T`, phải kiểm tra tính an toàn theo phiên bản goal và dự án.

## 11. CI setup: có JDK thực và file toolchains rõ ràng

Một pipeline tốt nên:

1. Pin Maven version (có thể dùng Maven Wrapper).
2. Cài JDK runtime chạy Maven và JDK toolchain yêu cầu trước khi build.
3. Tạo `toolchains.xml` bằng đường dẫn thật của runner, hoặc dùng discovery đã kiểm soát.
4. Chạy `mvn --version` và `<jdkHome>/bin/javac -version` trước build.
5. Chạy `mvn -B clean verify` và kiểm tra output/test trên JDK đích.
6. Giữ log chọn toolchain, Java/Javac version, Maven version, dependency/plugin versions để audit.

### 11.1. Ví dụ trên Linux CI

**Đoạn shell minh họa**; runner thực tế cần cài JDK tại đường dẫn tương ứng trước:

```bash
# Giả sử CI đã cài JDK 21 và 17
export JAVA_HOME=/opt/jdks/jdk-21
export PATH="$JAVA_HOME/bin:$PATH"

mkdir -p "$HOME/.m2"
cat > "$HOME/.m2/toolchains.xml" <<'XML'
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
</toolchains>
XML

mvn --version
/opt/jdks/jdk-17/bin/javac -version
mvn -B clean verify
```

Các path `/opt/jdks/...` **không phải tên mặc định của mọi Linux**. Hãy dùng output thực của bước setup JDK ở CI, hoặc tạo file dưới workspace rồi dùng `mvn -t ...`.

### 11.2. Windows PowerShell CI

Nếu JDK17 thật ở `C:\Java\jdk-17` và `toolchains.xml` ở user folder:

```powershell
& "C:\Java\jdk-17\bin\javac.exe" -version
mvn.cmd --version
mvn.cmd -t "$env:USERPROFILE\.m2\toolchains.xml" -B clean verify
```

Thay đường dẫn nếu JDK được cài trong `Program Files` hoặc thư mục do CI runner quản lý. PowerShell dùng `&` để chạy executable có đường dẫn được quote.

### 11.3. Cân nhắc discovery trên CI

Với plugin 3.3.0, có thể không cần tạo toolchains XML nếu discovery nhận đúng JDK. Nhưng cần constraints **chặt** như `[17,18)`, ghi lại JDK đã chọn và test runtime thật. Khi tổ chức đòi một vendor được phê duyệt, thêm vendor/env constraints và đảm bảo runner cài bản phù hợp.

Toolchains Plugin tự tìm JDK, nhưng **không bảo đảm nguồn cung, checksum hay security patch** của JDK. Những thứ này thuộc quản trị CI image/JDK installation.

## 12. Bảng chẩn đoán lỗi phổ biến

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| `No toolchain matched from ... found for type jdk` | Không có entry khớp version/vendor | Kiểm tra `provides`, POM và file `-t` |
| `Cannot find matching toolchain definitions` | File không được đọc, type sai hoặc labels không khớp | Kiểm tra path, `type=jdk`, provides |
| `mvn --version` vẫn hiện Java21 | Maven Core dùng JDK21 như thiết kế | Kiểm tra riêng log compiler/Surefire |
| `javac: invalid target release: 21` | Toolchain compiler JDK17 nhưng release=21 | Chọn compiler JDK21 hoặc giảm release |
| `UnsupportedClassVersionError` khi chạy JAR | Runtime quá cũ so với class-file version | Dùng JDK17+ cho bytecode 61 |
| Test JVM không đúng Java17 | Surefire có `jdkToolchain`/`jvm` override, session toolchain thiếu | Kiểm tra Surefire config/test report |
| `toolchains.xml` version17 nhưng dùng javac21 | `jdkHome` sai hoặc nhãn provides giả | Đối chiếu `bin/javac -version` |
| Discovery không tìm ra JDK17 | JDK ở vị trí ngoài heuristic hoặc chưa cài | Cấu hình environment variable hoặc XML thủ công |
| Javadoc dùng JDK khác Compiler | Javadoc Plugin version/goal không nhận/đang override toolchain | Kiểm tra plugin cụ thể |
| Module A đúng, B sai | Inheritance/pluginManagement/execution khác | Xem effective POM từng module |
| Toolchains chỉ trong `pluginManagement` | Plugin goal chưa thực thi | Khai actual plugin execution |
| Dùng `-s` tưởng chọn toolchains | `-s` dành cho Maven settings | Chọn `-t toolchains.xml` |
| Vendor không match | Vendor trong toolchains và POM khác nhau | Đồng bộ nhãn hoặc bỏ vendor nếu không cần |
| Toolchains Plugin không tải được | Lỗi Maven repository/mirror/credential | Sửa settings/repositories, không phải JDK path |
| Goal mới hoạt động khác goal cũ | `select-jdk-toolchain` dùng discovery và XML structure khác | Kiểm tra goal docs theo version |

### 12.1. Quy trình kiểm chứng

**Bước 1:** Xem Maven runtime:

```bash
mvn --version
```

**Bước 2:** Xác minh JDK theo `jdkHome` thực tế:

```bash
/opt/jdks/jdk-17/bin/java -version
/opt/jdks/jdk-17/bin/javac -version
```

**Bước 3:** Xem goal Toolchains có chạy ở `validate` không:

```bash
mvn -B validate
mvn help:effective-pom -Doutput=target/effective-pom.xml
```

`help:effective-pom` sử dụng Help Plugin, có thể phải tải plugin. Effective POM cho biết cấu hình sau parent/profile/merge, nhưng không thay thế log lựa chọn JDK thật.

**Bước 4:** Test trên artifact:

```bash
mvn -B clean verify
javap -verbose -classpath target/classes vn.example.toolchain.App
```

Tìm `major version: 61`; xem Surefire result và assertion JDK17. Nếu lỗi khác, dùng debug trong môi trường có quyền:

```bash
mvn -B -X verify
```

**Cảnh báo bảo mật:** `-X` có thể lộ URL, local paths và metadata hạ tầng. Lọc secrets/log trước khi chia sẻ.

## 13. Những hiểu nhầm nên tránh

| Nhận định sai | Cách hiểu đúng |
| --- | --- |
| “Toolchains Plugin tự cài JDK 17.” | Nó chỉ **chọn JDK đã cài**, không tự install/download |
| “Maven sẽ chạy lại bằng JDK trong toolchains.” | Maven Core tiếp tục chạy trong JVM launcher |
| “`--release 17` có nghĩa compiler là JDK17.” | Compiler JDK21 vẫn có thể target Java17 |
| “Có `toolchains.xml` thì mọi plugin đều dùng nó.” | Chỉ plugin toolchain-aware khi được cấu hình và goal đã chạy |
| “`provides.version=17` tự chứng minh jdkHome là JDK17.” | Cần kiểm tra executable JDK thật |
| “`version=17` chắc chắn match `17.0.20`.” | Dùng range `[17,18)` cho nhánh 17.x |
| “`[17,)` luôn chọn đúng JDK17.” | JDK21+ cũng thỏa điều kiện |
| “Goal discovery bắt buộc có toolchains.xml.” | Nó có thể dùng JDK được tự phát hiện |
| “`toolchain` và `select-jdk-toolchain` dùng XML y hệt.” | Các goal có parameter cấu trúc khác nhau |
| “Surefire chắc chắn dùng JDK giống Compiler override.” | Compiler-specific toolchain không tự ép Surefire |
| “Maven Wrapper thay thế Toolchains.” | Wrapper chọn Maven, Toolchains chọn JDK/tool cho plugins |
| “Enforcer requireJavaVersion kiểm tra toolchain JDK.” | Nó chủ yếu kiểm tra runtime JDK của Maven |
| “`java -cp` sau build luôn dùng toolchain.” | Java ngoài Maven lấy từ shell/PATH |
| “Build ra major 61 đủ chứng minh tests chạy Java17.” | Cần test JVM assertion/log riêng |

## 14. Bài tập kiểm tra kiến thức và đáp án

**Câu 1.** Maven chạy bằng JDK21, POM đặt `maven.compiler.release=17` nhưng không cấu hình Toolchains. Unit test có chắc chạy Java17 không?

**Đáp án:** Không. Release điều khiển compiler target. Không có toolchain hoặc cấu hình test JVM riêng, Surefire có thể dùng JDK runtime Maven.

**Câu 2.** `toolchains.xml` có `version=17.0.20` nhưng POM đặt `<version>17</version>`. Tại sao không match?

**Đáp án:** Goal truyền thống so version label theo exact match nếu không dùng range. `17` khác `17.0.20`; dùng `[17,18)`.

**Câu 3.** Trong file toolchains, version=17 nhưng jdkHome trỏ JDK21. Có được Maven tự phát hiện lỗi nội dung không?

**Đáp án:** Metadata thủ công không phải kiểm tra version thực. Cần xác minh `java/javac -version` tại root JDK và sửa file.

**Câu 4.** Parent chỉ đặt plugin với execution trong `pluginManagement`. Child không khai báo actual plugin. Goal Toolchains có tự chạy không?

**Đáp án:** Không. `pluginManagement` chỉ cung cấp quản lý; muốn goal chạy cần khai actual plugin/lifecycle execution.

**Câu 5.** Làm sao xem JDK nào được Toolchains Plugin 3.3.0 phát hiện khi chưa viết toolchains.xml?

**Đáp án:** Chạy `toolchains:display-discovered-jdk-toolchains`, sau đó dùng `select-jdk-toolchain` với constraints thích hợp.

**Câu 6.** Vì sao không nên dùng `[17,)` khi test bắt buộc chạy chính xác Java17?

**Đáp án:** Nó chấp nhận mọi JDK từ 17 trở lên, có thể chọn JDK21. Dùng `[17,18)` và xác minh test JVM.

**Câu 7.** Chạy `java -cp ...` sau khi Maven build bằng toolchain JDK17 có tự dùng JDK17 không?

**Đáp án:** Không. Lệnh Java chạy từ shell/IDE phụ thuộc runtime riêng, trừ khi chỉ rõ đường dẫn executable JDK17.

**Câu 8.** Compiler Plugin đặt `jdkToolchain` Java17, còn Surefire không có cấu hình JDK. Có thể kết luận tests chạy Java17 không?

**Đáp án:** Không thể kết luận. Compiler-specific toolchain không tự truyền sang Surefire; cần session toolchain hoặc Surefire-specific configuration và test.

## Tài liệu chính thức

- [Apache Maven — Guide to Using Toolchains](https://maven.apache.org/guides/mini/guide-using-toolchains)
- [Maven Toolchains Plugin — Introduction & Goals](https://maven.apache.org/plugins/maven-toolchains-plugin/)
- [Maven Toolchains Plugin — Usage](https://maven.apache.org/plugins/maven-toolchains-plugin/usage.html)
- [Maven Toolchains Plugin — toolchain goal](https://maven.apache.org/plugins/maven-toolchains-plugin/toolchain-mojo.html)
- [Maven Toolchains Plugin — select-jdk-toolchain goal](https://maven.apache.org/plugins/maven-toolchains-plugin/select-jdk-toolchain-mojo.html)
- [Maven Toolchains Plugin — JDK discovery](https://maven.apache.org/plugins/maven-toolchains-plugin/toolchains/jdk-discovery.html)
- [Maven Toolchains Plugin — JDK toolchain descriptor](https://maven.apache.org/plugins/maven-toolchains-plugin/toolchains/jdk.html)
- [Maven Compiler Plugin — Using a Different JDK](https://maven.apache.org/plugins/maven-compiler-plugin/examples/compile-using-different-jdk.html)
- [Maven Compiler Plugin — Setting release](https://maven.apache.org/plugins/maven-compiler-plugin/examples/set-compiler-release.html)
- [Maven Surefire Plugin — Using Maven Toolchains](https://maven.apache.org/surefire/maven-surefire-plugin/examples/toolchains)
