# JDK chạy Maven so với JDK dùng để biên dịch

## 1. Ba phiên bản Java cần phân biệt

Khi sử dụng Maven để xây dựng một dự án Java, câu “dự án dùng Java 17” **chưa đủ** để biết Maven đang chạy và biên dịch bằng môi trường nào. Có ít nhất ba khái niệm độc lập:

1. **JDK chạy chính Maven (*Maven runtime JDK*)**: JDK chứa JVM khởi động tiến trình Maven, nạp Maven core và thực thi những plugin chạy trong cùng JVM ấy.
2. **JDK dùng để biên dịch (*compiler JDK*)**: JDK cung cấp compiler `javac` cho Maven Compiler Plugin. Mặc định thường là JDK chạy Maven, nhưng có thể được thay bằng **Maven Toolchains** hoặc cấu hình compiler chạy external executable.
3. **Phiên bản Java mà bytecode/API nhắm tới (*target release*)**: ví dụ `--release 17`, tương ứng Java 17 language level, public JDK APIs và class file major version 61.

Ba giá trị **có thể trùng hoặc khác nhau**. Chẳng hạn:

```text
JDK 21 ── java ──> Maven 3.x (Maven runtime JDK)
                    │
                    ├── Maven Toolchains chọn JDK 17
                    │           │
                    │           └── javac 17
                    │                  │
                    │                  └── --release 17
                    │                         │
                    │                         └── App.class major 61
                    │
                    └── các Maven plugin khác
                         có thể chạy trong JVM 21
                         hoặc dùng toolchain nếu hỗ trợ
```

**Điểm quan trọng:** việc đổi `<maven.compiler.release>17</maven.compiler.release>` **không chuyển JVM đang chạy Maven sang JDK 17**; tương tự, việc `mvn -version` in “Java version: 21...” **không chứng minh** Compiler Plugin đã sử dụng `javac 21`.

### Mục tiêu học tập

Sau bài này, bạn sẽ biết:

- Kiểm tra JDK thực sự khởi động Maven bằng `mvn -version` và phân biệt với `java -version`, `javac -version` trên terminal.
- Giải thích vì sao mặc định Maven Compiler Plugin sử dụng JDK của tiến trình Maven, và khi nào hành vi đó thay đổi.
- Dùng `maven.compiler.release`/`--release` để nhắm Java 17 mà không nhầm thành cơ chế chọn JDK.
- Dùng `~/.m2/toolchains.xml` cùng Maven Toolchains Plugin để **biên dịch với JDK 17 trong khi Maven có thể chạy trên JDK 21**.
- Kiểm chứng kết quả bằng log Toolchains, `javap -verbose` và một chương trình Java 17 chạy được.
- Phân biệt JDK compile, JDK chạy unit/integration tests và JDK production; tránh lỗi compiler, runtime và CI.

## 2. JDK nào khởi động tiến trình Maven?

### 2.1. Kiểm tra đúng bằng `mvn -version`

Lệnh đầu tiên khi gặp lỗi môi trường là:

```bash
mvn -version
```

Một output **minh họa** khi dùng Maven 3.9.x với JDK 21 có thể chứa:

```text
Apache Maven 3.9.x (...)
Java version: 21.0.x, vendor: ...
Java home: /opt/jdks/jdk-21
Default locale: ...
OS name: ...
```

Đây **không phải stdout cố định**: Maven version, vendor, Java home và hệ điều hành phụ thuộc máy.

Dòng “Java version” cho biết **JVM mà tiến trình Maven đang chạy**. Dòng “Java home” cho biết môi trường Java của tiến trình đó. Không có dòng nào là bằng chứng tuyệt đối về compiler toolchain hoặc JDK mà Surefire sẽ dùng để fork test JVM.

### 2.2. `JAVA_HOME`, `PATH`, `java` và `javac` có thể không đồng nhất

Với terminal Linux/macOS (Bash):

```bash
echo "$JAVA_HOME"
command -v java
command -v javac
java -version
javac -version
mvn -version
```

Kết quả có thể khác nhau:

- `JAVA_HOME` là biến môi trường thường được Maven launcher script dùng để xác định Java installation.
- `java -version` cho biết chương trình `java` mà shell tìm thấy theo `PATH`, không nhất thiết là JVM mà Maven launcher dùng.
- `javac -version` cho biết `javac` trên `PATH`, **không tự chứng minh** đó là compiler đã được Maven Compiler Plugin chọn.
- `mvn -version` trực tiếp cho biết JDK đang chạy Maven; đây là điểm xuất phát đáng tin cho việc kiểm tra Maven runtime.

Ví dụ giả định: `JAVA_HOME=/opt/jdks/jdk-21` trong khi `PATH` còn trỏ vào Java 17. `java -version` có thể in 17, còn `mvn -version` có thể báo 21 tùy launcher script; do đó phải so sánh đầy đủ, không phán đoán từ một biến.

**Windows PowerShell:**

```powershell
$env:JAVA_HOME
Get-Command java
Get-Command javac
java -version
javac -version
mvn -version
```

Một số Windows Maven launcher kiểm tra `JAVA_HOME` trước khi chạy; các IDE, service wrappers hoặc CI agents có thể quản lý Java runtime theo cách riêng. Khi Maven được chạy từ **IntelliJ IDEA/Eclipse**, hãy kiểm tra **Maven runner JDK** trong IDE; Project SDK và Maven runner JDK không mặc nhiên là một.

### 2.3. Đổi JDK chạy Maven

Ví dụ trên **Linux/macOS** khi máy đã cài JDK 21 vào đường dẫn minh họa:

```bash
export JAVA_HOME=/opt/jdks/jdk-21
export PATH="$JAVA_HOME/bin:$PATH"
mvn -version
```

Ví dụ trên **Windows PowerShell** với đường dẫn minh họa:

```powershell
$env:JAVA_HOME = 'C:\JDKs\jdk-21'
$env:Path = "$env:JAVA_HOME\bin;$env:Path"
mvn -version
```

**Chỉ chạy những lệnh trên sau khi thay đường dẫn cho đúng máy.** Chúng đổi môi trường của **terminal hiện tại**; không tự cài JDK và không bảo đảm IDE/CI job khác nhận cùng cấu hình.

**Maven Wrapper** (`./mvnw`, `mvnw.cmd`) thường giúp pin **phiên bản bản phân phối Maven**, **không tự pin một JDK** theo cùng cách. Wrapper vẫn cần một Java runtime phù hợp với Maven distribution đang dùng. Một dự án có thể yêu cầu Maven 3.9.x, JDK chạy Maven 21, nhưng compiler toolchain JDK 17.

### 2.4. Maven có yêu cầu JDK tối thiểu riêng

Maven và từng plugin có minimum Java/Maven requirements. Ví dụ **Maven 4 yêu cầu JDK 17 để chạy Maven**, nhưng điều đó **không** nói rằng mọi project xây với Maven 4 đều phải tạo bytecode Java 17. Khi dùng compiler phù hợp, có thể nhắm phiên bản Java cũ hơn; khi cần compiler khác, dùng Toolchains.

Đừng chọn JDK chạy Maven thấp hơn mức Maven distribution/plugin yêu cầu chỉ vì project muốn tạo bytecode cũ. Cách thiết kế thường đúng là **Maven chạy trên JDK được hỗ trợ** rồi compiler nhắm release phù hợp.

## 3. Mặc định: Maven Compiler Plugin dùng compiler nào?

Trong project Maven `jar` thông thường, plugin `maven-compiler-plugin` có goals được bind vào lifecycle:

- `compiler:compile` tại phase `compile`, biên dịch `src/main/java`.
- `compiler:testCompile` tại phase `test-compile`, biên dịch `src/test/java`.

Khi **không cấu hình toolchain hoặc external compiler đặc biệt**, Compiler Plugin mặc định sử dụng compiler `javac` liên quan đến **JDK đang thực thi Maven**. Vì vậy, Maven runtime JDK và compiler JDK thường trùng nhau trong dự án đơn giản.

Ví dụ:

```text
JAVA_HOME = /opt/jdk-21
mvn -version  → Java version 21
POM không chọn compiler toolchain
mvn compile  → Compiler Plugin mặc định dùng compiler của JDK 21
```

Nhưng khi khai Maven Toolchains hoặc `fork=true` với `executable`, plugin có thể sử dụng compiler khác. **Không dựa vào `mvn -version` để xác nhận compiler JDK sau khi đã có các cấu hình này.**

### Plugin khác có nhất thiết dùng compiler JDK?

Không. Maven core và nhiều plugin goals chạy trong JVM chứa Maven. Một số plugin hỗ trợ JDK Toolchains để chạy các công cụ bên ngoài (compiler, Javadoc, Surefire/Failsafe, Jarsigner...), và một số plugin có tham số chọn JDK/JVM riêng. Các plugin không hỗ trợ Toolchains vẫn có thể sử dụng JDK đang chạy Maven hoặc logic của chúng.

Đặc biệt, **Surefire/Failsafe và test runtime** cần được kiểm tra riêng: có thể dùng JDK toolchain, `jdkToolchain`, `jvm` hoặc cơ chế fork theo cấu hình/version plugin. Compile bằng JDK 17 **chưa chứng minh** unit tests đã chạy trên Java 17.

## 4. `--release 17` điều khiển cái gì và không điều khiển cái gì?

Trong POM Maven 3/model 4.0.0, cách thông dụng để nhắm Java 17:

```xml
<properties>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    <maven.compiler.release>17</maven.compiler.release>
</properties>
```

Hoặc cấu hình trực tiếp:

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-compiler-plugin</artifactId>
    <version>3.13.0</version>
    <configuration>
        <release>17</release>
    </configuration>
</plugin>
```

Cả hai là **đoạn cấu hình**, cần đặt trong `<project>`/`<build><plugins>` hợp lệ. Chọn một cách phù hợp với mô hình quản lý POM; không cần đặt hai giá trị mâu thuẫn nhau.

Khi compiler là JDK 17+, `javac --release 17` hướng đến:

1. **Java language level 17** — kiểm tra cú pháp Java 17 trở xuống.
2. **Java SE public APIs của release 17** — ngăn code tình cờ gọi các API JDK chỉ xuất hiện trong phiên bản cao hơn.
3. **Class file version phù hợp với Java 17** — major version **61**.

`--release` **không**:

- Cài đặt JDK 17.
- Chuyển `JAVA_HOME` hoặc JVM chạy Maven thành JDK 17.
- Chỉ định đường dẫn compiler executable nếu không có Toolchains/external compiler config.
- Bảo đảm mọi **thư viện bên thứ ba** tương thích Java 17; dependencies có thể chứa class file tạo cho JDK cao hơn.
- Bảo đảm code chạy thành công trên JDK 17 nếu logic, module flags, native libs, reflection, startup arguments hay runtime environment không phù hợp.
- Tự quyết định JDK chạy test, Maven plugin hoặc ứng dụng production.

### 4.1. Compiler JDK 21 có thể tạo bytecode Java 17

Giả sử:

```text
Maven runtime JDK   = 21
Compiler JDK        = 21
maven.compiler.release = 17
```

Compiler `javac 21` có thể tạo class files nhắm Java 17 và từ chối các API chuẩn chỉ xuất hiện sau Java 17. **Không nhất thiết phải cài JDK 17 chỉ để tạo bytecode Java 17**, nếu dùng compiler mới hơn và `--release 17` phù hợp.

Nhưng để **thử chạy thực tế trên Java 17**, bạn vẫn nên có Java 17 runtime trong test matrix. Ngoài ra, công cụ annotation processor/plugin, dependencies và build logic có thể có minimum JDK riêng.

### 4.2. Compiler JDK 17 không thể tự tạo `--release 21`

```text
Maven runtime JDK   = 21
Compiler JDK        = 17 (toolchain)
maven.compiler.release = 21
```

Cấu hình này **không hợp lệ** cho compiler `javac 17` vì nó không biết release 21. Lỗi thường giống:

```text
error: release version 21 not supported
```

Muốn tạo bytecode/API Java 21, phải chọn compiler thực sự hỗ trợ release 21 (chẳng hạn JDK 21), bất kể Maven đang chạy bằng JDK nào. Không thể sửa chỉ bằng cách nâng phiên bản Maven Plugin nếu compiler không hỗ trợ target ấy.

### 4.3. So sánh `--release` với `source` và `target`

Cách cũ:

```xml
<properties>
    <maven.compiler.source>8</maven.compiler.source>
    <maven.compiler.target>8</maven.compiler.target>
</properties>
```

Khi biên dịch bằng JDK mới hơn, chỉ đặt `source=8`, `target=8` **không bảo đảm** code chỉ sử dụng Java SE 8 APIs. Code có thể biên dịch sang bytecode major 52 mà vẫn tham chiếu một API JDK xuất hiện sau Java 8, dẫn đến lỗi runtime trên Java 8.

Nếu compiler hỗ trợ `--release 8`, nên dùng:

```xml
<properties>
    <maven.compiler.release>8</maven.compiler.release>
</properties>
```

để compiler đồng thời giới hạn language level, bytecode target và Java platform APIs. Đây là ví dụ khái niệm cho Java 8, **không phải thay đổi trực tiếp** đối với bài thực hành có code `record` Java 17 ở dưới.

**Ví dụ phát hiện API không tương thích:** `"hi".repeat(2)` là API xuất hiện từ Java 11. Nếu code dùng API này mà compiler mới nhận `--release 8`, compiler sẽ từ chối vì Java 8 không có method đó. Với chỉ source/target 8 trên compiler mới và classpath platform mặc định, lỗi có thể không được phát hiện đúng lúc compile.

## 5. Bảng các tổ hợp thường gặp

| Maven runtime JDK | Compiler JDK | `--release` | Kết quả kỳ vọng khi mọi plugin tương thích |
| --- | --- | --- | --- |
| 17 | 17 mặc định | 17 | Compile Java 17; bytecode major 61 |
| 21 | 21 mặc định | 17 | Vẫn có thể compile cho Java 17, major 61 |
| 21 | **17 qua Toolchains** | 17 | Maven chạy trên 21, compiler là 17, major 61 |
| 17 | **21 qua Toolchains** | 21 | Có thể compile Java 21 nếu plugin/Maven runtime hỗ trợ; major 65 |
| 21 | **17 qua Toolchains** | 21 | **Lỗi**: javac 17 không hỗ trợ release 21 |
| 17 | 17 mặc định | 11 | Compile cho Java 11 nếu source/APIs phù hợp; major 55 |
| 11 | **17 qua Toolchains** | 17 | Có thể trong Maven/plugin tương thích JDK 11; không suy rằng mọi plugin chạy được |

Các hàng trên mô tả nguyên lý, **không bảo đảm mọi bộ Maven/plugin/vendor chạy được trên mọi JDK**. Toolchain chỉ thay công cụ ở những plugin nhận biết toolchain, chứ không đổi JDK của tiến trình Maven.

Class file major version phổ biến:

| Java release | Major version |
| --- | --- |
| Java 8 | 52 |
| Java 11 | 55 |
| Java 17 | 61 |
| Java 21 | 65 |

**`javap -verbose` có thể xác minh bytecode**, còn `mvn -version` xác minh Maven runtime. Muốn biết compiler thực sự được chọn phải kiểm tra cấu hình/log Toolchains hoặc plugin compiler.

## 6. Maven Toolchains: chọn compiler JDK độc lập với Maven JVM

**Maven Toolchains** là cơ chế chính thức để project yêu cầu **công cụ xây dựng** cụ thể mà không gắn đường dẫn JDK cố định vào POM. Cấu hình thường gồm:

- **`pom.xml`**: khai toolchain requirements bằng Maven Toolchains Plugin và cho plugin ấy tham gia lifecycle.
- **`~/.m2/toolchains.xml`**: ánh xạ một toolchain phù hợp đến **đường dẫn JDK đã cài trên máy build**.
- **Toolchain-aware plugins**: như Compiler Plugin có thể dùng JDK đã được chọn thay vì JDK Maven đang chạy.

Luồng:

```text
pom.xml
  maven-toolchains-plugin
     requires jdk version=17, vendor=temurin
                   │
                   v
         ~/.m2/toolchains.xml
         entry <provides> matching requirement
         <configuration><jdkHome>...
                   │
                   v
           Selected JDK 17 toolchain
                   │
                   v
         maven-compiler-plugin
           uses compiler from JDK 17
                   │
                   v
         compile with --release 17
```

`toolchains.xml` chứa đường dẫn cục bộ theo từng máy. Không commit đường dẫn riêng của laptop vào POM chung. Nếu CI có cách cài đặt JDK khác, CI có thể tạo `toolchains.xml` thích hợp trước khi chạy Maven.

### 6.1. File `~/.m2/toolchains.xml`

Ví dụ dành cho máy Linux đã cài **Temurin JDK 17**:

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
</toolchains>
```

**Bắt buộc thay `/opt/jdks/temurin-17` thành đường dẫn JDK 17 thực sự.** Thư mục `jdkHome` là **root của JDK**, không phải thư mục `bin` và không phải đường dẫn đến file `javac`.

Với Windows, đường dẫn có thể là `C:\JDKs\jdk-17` (ghi đúng đường dẫn của máy) và đặt file tại `%USERPROFILE%\.m2\toolchains.xml`.

`<provides>` là metadata để toolchains plugin khớp requirement; `<configuration><jdkHome>` mới trỏ đến JDK thực tế. **Không cố ý khai “version 17” cho một JDK 21** để lừa bộ chọn. Plugin dựa trên metadata và trạng thái cài đặt; kiểm chứng compiler thực tế khi xử lý lỗi.

### 6.2. Toolchains Plugin trong POM

Đoạn cấu hình:

```xml
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
                <vendor>temurin</vendor>
            </jdk>
        </toolchains>
    </configuration>
</plugin>
```

Đoạn này cần nằm dưới `<build><plugins>` của POM hoàn chỉnh. Goal `toolchains:toolchain` có default phase `validate`, vì vậy execution không cần khai `<phase>validate</phase>` để được gọi đúng ở ví dụ này. Khi phase validate chạy, plugin tìm một JDK có metadata khớp trong toolchains.xml và đưa lựa chọn vào build context cho các plugin hỗ trợ.

**Điều kiện khớp:** cả `version=17` và `vendor=temurin` phải phù hợp với thông tin trong `<provides>`. Với các vendor khác, hãy chọn tiêu chí phù hợp thay vì copy nguyên từ ví dụ.

**Quan trọng:** Maven Toolchains Plugin **không tự cài JDK**. Nếu chưa có JDK 17 đúng đường dẫn hoặc không có entry khớp, build có thể lỗi ở validate trước khi Compiler Plugin chạy.

### 6.3. Toolchain cụ thể cho Compiler Plugin

Nếu không muốn dùng một toolchain chung cho các plugin tương thích, Compiler Plugin cũng hỗ trợ cấu hình `jdkToolchain` riêng trong các phiên bản phù hợp:

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-compiler-plugin</artifactId>
    <version>3.13.0</version>
    <configuration>
        <release>17</release>
        <jdkToolchain>
            <version>17</version>
        </jdkToolchain>
    </configuration>
</plugin>
```

Đây là **đoạn cấu hình minh họa thay thế**, không cần thêm vào ví dụ POM bên dưới. `jdkToolchain` riêng của Compiler Plugin có thể **ưu tiên hơn** toolchain toàn build đã chọn, theo tài liệu của plugin. Cần có JDK matching/được cấu hình phù hợp trong toolchains; đây không phải lệnh download JDK.

Chỉ dùng nhiều cơ chế chọn JDK cùng lúc khi có chủ đích. Nếu Compiler dùng JDK khác trong khi Surefire/Javadoc vẫn dùng một JDK khác, bạn phải kiểm tra sự tương thích của cả pipeline.

## 7. Thực hành Java 17: Maven chạy JDK 21 nhưng compile bằng JDK 17

Dự án này **có thể chạy độc lập** với một module, JDK 17 đã cài, Maven 3.x tương thích với plugin versions, và local toolchains.xml. Nếu có thêm JDK 21, bạn có thể chạy Maven bằng JDK 21 để quan sát rõ hai phiên bản khác nhau. Nếu chỉ có JDK 17, vẫn build được và kiểm chứng bytecode 17, nhưng chưa minh họa sự khác nhau giữa hai JDK trên cùng máy.

### 7.1. Cấu trúc thư mục

```text
jdk-toolchain-lab/
├── pom.xml
└── src/main/java/demo/
    ├── Message.java
    └── App.java

# Ngoài project, trên máy người dùng:
~/.m2/toolchains.xml
```

Không có parent POM hay dependency ngoài trong ứng dụng Java; Maven chỉ cần tải các plugins build khi cần. File toolchains.xml là **cấu hình môi trường máy**, không phải source file cần được copy vào repository Git.

### 7.2. POM đầy đủ — `jdk-toolchain-lab/pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>dev.training</groupId>
    <artifactId>jdk-toolchain-lab</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

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
                            <vendor>temurin</vendor>
                        </jdk>
                    </toolchains>
                </configuration>
            </plugin>

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-jar-plugin</artifactId>
                <version>3.4.2</version>
            </plugin>

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.2.5</version>
            </plugin>
        </plugins>
    </build>
</project>
```

Giải thích các điểm then chốt:

1. `<maven.compiler.release>17</maven.compiler.release>` đặt **Java release đích**, không chọn JDK.
2. `maven-toolchains-plugin` tìm một JDK **version 17, vendor temurin** và làm toolchain ấy khả dụng cho các plugin hỗ trợ.
3. `maven-compiler-plugin` phiên bản `3.13.0` dùng compiler tương ứng khi toolchain đã được chọn.
4. `maven-jar-plugin` đóng gói class/resources thành JAR, không tự tạo fat JAR chứa dependency.
5. `maven-surefire-plugin` là test runner plugin; project không có test source nên không có output test ứng dụng cần chốt.
6. `<packaging>jar</packaging>` làm các compile/test/JAR goals phù hợp được bind theo default lifecycle.
7. Nếu Maven đang chạy JDK 21, plugin vẫn được JVM của Maven nạp/chạy; Toolchains chỉ chọn công cụ JDK cho những goals hỗ trợ.

### 7.3. Java source dùng tính năng Java 17

File `src/main/java/demo/Message.java`:

```java
package demo;

public record Message(String text) {
}
```

`record` được Java hỗ trợ chính thức từ Java 16, nên mã này được JDK 17 biên dịch với `--release 17`.

File `src/main/java/demo/App.java`:

```java
package demo;

public final class App {
    private App() {
    }

    public static void main(String[] args) {
        Message message = new Message("Build targets Java 17");
        System.out.println(message.text());
    }
}
```

Các tên package, class, file trùng khớp: `demo.Message` ở `Message.java` và `demo.App` ở `App.java`. Không cần dependency ngoài để biên dịch/chạy.

### 7.4. Chuẩn bị JDK 17 toolchain và Maven runtime

Trước tiên đảm bảo `~/.m2/toolchains.xml` chứa entry JDK 17 đã minh họa ở mục 6.1; đường dẫn `jdkHome` phải tồn tại và có chương trình `bin/javac`.

Kiểm tra JDK 17 trực tiếp trên **Linux/macOS** bằng đường dẫn bạn đã cấu hình:

```bash
/opt/jdks/temurin-17/bin/java -version
/opt/jdks/temurin-17/bin/javac -version
```

Đây là **đường dẫn minh họa**, thay theo máy. `java -version` và `javac -version` thường in version ra stderr/stdout tùy lệnh.

Để **Maven chạy trên JDK 21** trong terminal Bash đã cài JDK 21:

```bash
export JAVA_HOME=/opt/jdks/temurin-21
export PATH="$JAVA_HOME/bin:$PATH"
mvn -version
```

Kỳ vọng `mvn -version` cho thấy Maven runtime Java 21. Tuy nhiên toolchains.xml vẫn **chỉ JDK 17** đã khai ở `jdkHome`; Maven JVM và compiler JDK vì vậy có thể khác nhau.

Nếu không có JDK 21, **không cần cài thêm chỉ để hoàn thành bài**: chạy Maven trên JDK 17 cũng hợp lệ, miễn `toolchains.xml` chọn đúng JDK và release là 17.

### 7.5. Build

Tại thư mục `jdk-toolchain-lab/` chứa POM:

```bash
mvn -B -ntp clean verify
```

Giải thích:

- `-B` dùng batch mode, `-ntp` giảm log transfer progress.
- `clean` dọn output `target/` trước khi build.
- `verify` đi qua lifecycle tới verify, gồm compile, test và package.
- Goal `toolchains:toolchain` được gọi ở `validate`, trước goal `compiler:compile`.
- Compiler Plugin chọn compiler thông qua toolchain JDK 17 đã được setup.
- `maven.compiler.release=17` yêu cầu compiler biên dịch cho Java 17.

Bạn có thể thấy thông điệp trong log gần giống:

```text
Required toolchain: jdk [ version='17' vendor='temurin' ]
Found matching toolchain for type jdk: JDK[/opt/jdks/temurin-17]
```

Đây là **minh họa thông tin cần tìm**, không phải toàn bộ stdout cố định hoặc cam kết log giống hệt giữa các phiên bản Maven.

Nếu Maven báo không tìm được toolchain, **không đổi release thành 21 để né lỗi**; hãy kiểm tra `~/.m2/toolchains.xml`, vendor/version khai báo và `jdkHome` đúng.

### 7.6. Chạy chương trình Java

Sau build, đứng tại `jdk-toolchain-lab/`:

```bash
java -cp target/classes demo.App
```

**Stdout chính xác của `App.main`:**

```text
Build targets Java 17
```

Nếu terminal `java` hiện tại là JDK 21, JVM 21 vẫn chạy được class files target Java 17 (trong điều kiện ứng dụng không phụ thuộc môi trường khác không tương thích). Để kiểm tra **JDK 17 runtime thực sự**, dùng đường dẫn Java 17:

```bash
/opt/jdks/temurin-17/bin/java -cp target/classes demo.App
```

Stdout **cũng** là:

```text
Build targets Java 17
```

Đường dẫn Java 17 cần thay theo máy. Chương trình chỉ dùng JDK standard library, không cần thêm JAR dependency vào classpath.

**Windows PowerShell** với JDK 17 tại `C:\JDKs\jdk-17`:

```powershell
& 'C:\JDKs\jdk-17\bin\java.exe' -cp target\classes demo.App
```

Đây là ví dụ đường dẫn Windows, phải sửa nếu máy cài JDK ở nơi khác.

### 7.7. Kiểm tra class file major version

Lệnh sau đọc class file do compiler tạo, không dựa vào việc Maven in version nào:

```bash
javap -verbose target/classes/demo/App.class
```

Trong output dài, tìm dòng:

```text
major version: 61
```

**61** là class file major version của Java 17. Trên Bash có thể lọc:

```bash
javap -verbose target/classes/demo/App.class | grep "major version"
```

Windows PowerShell:

```powershell
javap -verbose target\classes\demo\App.class | Select-String 'major version'
```

Kết quả là bằng chứng bytecode target Java 17. Tuy nhiên **nó chưa đủ chứng minh compiler JDK là 17**: JDK 21 cũng có thể tạo major 61 qua `--release 17`. Để xác minh **compiler được chọn**, xem log Toolchains/Compiler Plugin và path `jdkHome` đã cấu hình.

### 7.8. Kiểm tra Maven runtime và release là hai giá trị khác

Vẫn trong project:

```bash
mvn -version
mvn -q help:evaluate -Dexpression=java.version -DforceStdout
mvn -q help:evaluate -Dexpression=maven.compiler.release -DforceStdout
```

- `mvn -version`: JDK chạy Maven.
- `java.version` khi đánh giá trong Maven là Java system property của JVM Maven; nếu Maven chạy JDK 21, giá trị có thể là `21.0.x` (phụ thuộc vendor/build).
- `maven.compiler.release`: kỳ vọng **17** do POM khai.

Một giá trị `java.version` là 21 cùng `maven.compiler.release` là 17 **không phải cấu hình lỗi**. Chúng trả lời **hai câu hỏi khác nhau**.

Nếu không muốn tải Maven Help Plugin chỉ để đọc properties, có thể xem `mvn -version` và `pom.xml`; ở build thực tế, effective POM cũng giúp xác định cấu hình release cuối cùng.

## 8. Không dùng Toolchains: chỉ chọn Java release

Trường hợp phổ biến: máy/CI chỉ cần một JDK 21 và ứng dụng phải chạy trên Java 17. Có thể dùng POM đơn giản hơn:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>dev.training</groupId>
    <artifactId>release-only-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <maven.compiler.release>17</maven.compiler.release>
    </properties>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
        </plugins>
    </build>
</project>
```

Nếu đây là POM của một project có `src/main/java` chứa code **phù hợp Java 17**, Maven Compiler Plugin sẽ nhắm release 17 với compiler mặc định của JDK Maven (ví dụ JDK 21). **Không có toolchain selection** trong POM này.

**Khi nào đủ?** Khi muốn tạo bytecode đúng version/API và không cần một compiler vendor/version riêng.

**Khi nào cần Toolchains?** Khi bộ xây dựng phải dùng **chính JDK được chọn** khác JDK chạy Maven (ví dụ compiler JDK 17, Maven JVM 21), hoặc khi nhiều toolchain-aware plugins cùng cần nhất quán công cụ JDK.

## 9. Cách khác: `fork=true` và chỉ định `javac` bên ngoài

Maven Compiler Plugin còn hỗ trợ dùng compiler bên ngoài bằng cấu hình `fork` và `executable`:

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-compiler-plugin</artifactId>
    <version>3.13.0</version>
    <configuration>
        <fork>true</fork>
        <executable>${env.JDK17_HOME}/bin/javac</executable>
        <release>17</release>
    </configuration>
</plugin>
```

Đây là **đoạn minh họa cần đặt trong `build/plugins`**, dành cho môi trường kiểu Unix. Bạn cần set `JDK17_HOME` đúng đường dẫn JDK trước khi chạy Maven:

```bash
export JDK17_HOME=/opt/jdks/temurin-17
mvn clean compile
```

Khi `fork=true`, Compiler Plugin có thể gọi `javac` từ `<executable>` thay cho compiler in-process mặc định. Đây là cách có thể dùng khi cần tùy biến riêng compiler nhưng **không** tự cấu hình Javadoc/Surefire/Jarsigner cùng dùng JDK ấy.

Với nhiều plugin, **Toolchains thường dễ quản lý và ít hardcode đường dẫn hơn**. Trong Windows, đường dẫn executable cần `javac.exe` và separator Windows thích hợp; không copy đường dẫn `/bin/javac` nguyên sang Windows.

Không nên đồng thời khai Toolchains và `executable` với kỳ vọng hai JDK độc lập cùng dùng cho một compile goal. Nếu có nhiều cơ chế, hãy đọc documentation/plugin effective configuration để xác định đường compiler thực tế.

## 10. Maven runtime, compiler và JDK chạy tests

Một project có thể:

```text
JDK chạy Maven          = 21
JDK compile main source = 17
JDK test compilation    = 17
JDK thực thi unit tests = 21 hoặc 17 (tùy Surefire/toolchain/fork)
JDK production runtime  = 17
```

Đây là **các trục cần xác minh riêng**.

### 10.1. Surefire/Failsafe có toolchain-aware

Maven Surefire/Failsafe có hỗ trợ JDK Toolchains trong các phiên bản phù hợp. Nếu đã chọn default JDK toolchain tại `validate`, các plugin toolchain-aware có thể dùng nó, nhưng kết quả còn tùy plugin version và cấu hình fork. Một số trường hợp bạn cần chọn riêng JDK qua `jdkToolchain` hoặc cấu hình `jvm` của test plugin.

Ví dụ **đoạn cấu hình Surefire** để yêu cầu JDK 17 (chỉ dùng khi phiên bản plugin hỗ trợ tham số):

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-surefire-plugin</artifactId>
    <version>3.2.5</version>
    <configuration>
        <jdkToolchain>
            <version>17</version>
        </jdkToolchain>
    </configuration>
</plugin>
```

Đoạn này **không phải POM độc lập**. Nó minh họa cách yêu cầu riêng toolchain test runner, không bắt buộc phải thêm vào demo một module ở trên vì demo không có unit tests.

Nếu thực sự cần chứng minh tests chạy trên Java 17, viết một test kiểm tra `Runtime.version().feature()` hoặc `System.getProperty("java.version")` rồi chạy trong **test runner được cấu hình đúng**. Chỉ xem `mvn -version` không đủ.

### 10.2. Chạy thử trên JDK đích là bước độc lập

Ngay cả khi compiler tạo bytecode major 61 và dùng `--release 17`, nên chạy integration/smoke test trên **JDK 17 runtime**:

- Classpath dependencies có thể chứa bytecode target Java 21 khiến Java 17 không load được.
- Reflection, agent, native code hoặc startup flags có thể thay đổi giữa releases.
- Java 17 và Java 21 có thể có khác biệt về hành vi/hệ sinh thái khi app chạy thật.
- Unit tests chạy trong Maven JVM 21 có thể bỏ sót lỗi chỉ xuất hiện trên JDK 17.

Nên phân biệt **compile compatibility** và **runtime compatibility**. Compiler là lớp kiểm tra rất cần thiết, nhưng không thay thế test trên runtime target.

### 10.3. Maven Enforcer Plugin kiểm tra Java version gì?

Rule `requireJavaVersion` của Maven Enforcer Plugin thông thường kiểm tra **Java version của môi trường Maven đang chạy**, không mặc nhiên kiểm tra compiler toolchain đã chọn. Nếu bạn đặt rule yêu cầu `[17,18)` trong khi Maven chạy JDK 21 nhưng toolchain compiler là JDK 17, rule có thể fail dù compile target chính xác.

Dùng Enforcer để bảo vệ **minimum JDK cần cho Maven/plugin** khi có chủ đích, và dùng Toolchains/Compiler Plugin để quản lý **compiler và release**. Đừng dùng Enforcer rule để suy ra chắc chắn `javac` toolchain version.

## 11. CI và IDE: các nguồn khác biệt thường thấy

### 11.1. Trong CI

Ở CI, có thể có nhiều nơi chọn Java:

- CI image hoặc base container có JDK mặc định.
- Step setup JDK đặt `JAVA_HOME`/`PATH` cho Maven.
- Maven Wrapper chọn Maven distribution version.
- `toolchains.xml` được tạo/sao chép tại user home của runner.
- Maven Toolchains Plugin chọn JDK compiler.
- Surefire/Failsafe có thể chọn test JVM riêng.
- Production image/host có runtime JDK/JRE khác.

Nếu workflow **chỉ cài JDK 21** nhưng POM yêu cầu Toolchains **JDK 17**, bước toolchains có thể fail vì không tìm thấy JDK 17. Cài cả hai JDK, cấu hình `toolchains.xml` khớp đường dẫn thực, rồi chạy Maven. Không nhầm “đã cài Java 17” với “Java 17 đã được khai làm toolchain cho project”.

**Pipeline thực tế nên kiểm tra:**

```bash
mvn -version
mvn -B -ntp clean verify
javap -verbose target/classes/demo/App.class
```

Sau đó chạy ứng dụng/test trên JDK target. Nếu dự án nhiều module, chọn đúng module/class để `javap` kiểm tra.

### 11.2. Trong IntelliJ IDEA/Eclipse

Các khái niệm IDE có thể khác nhau:

- Project SDK / language level của editor.
- JDK chạy Maven import/runner.
- JDK dùng IDE compiler khi build qua IDE.
- JDK thực thi unit tests qua IDE.
- Maven Toolchains configuration khi build bằng Maven.

Một project có thể highlight cú pháp Java 17 nhưng Maven runner dùng JDK 11; build Maven báo “release version 17 not supported”. Hoặc IDE tự build thành công bằng JDK 21 nhưng CI Maven dùng JDK 17 và fail do source đã dùng Java 21 API.

Để điều tra, chạy **chính Maven command** trong terminal hoặc IDE Maven tool window, kiểm tra `mvn -version` của môi trường đó, effective POM và compiler selection. Không trộn kết quả IDE-built classes với Maven-built classes khi đối chiếu.

### 11.3. Maven Daemon (`mvnd`) hoặc build service dài hạn

Một số công cụ build giữ JVM/process tồn tại để tái sử dụng, vì vậy thay `JAVA_HOME` trong terminal **không nhất thiết đổi JVM của daemon đã khởi động từ trước**. Khi nghi môi trường bị giữ lại, kiểm tra trạng thái daemon và chạy Maven process mới với JDK mong muốn theo hướng dẫn công cụ. Không tự gán mọi lỗi compiler là do Maven core.

## 12. Các lỗi đặc trưng và cách đọc đúng

| Lỗi/triệu chứng | Giải thích thường gặp | Cách xử lý |
| --- | --- | --- |
| `release version 17 not supported` | Compiler được chọn thấp hơn JDK 17, hoặc compiler khác không hỗ trợ release | Xác nhận compiler path/version; chọn JDK 17+ hoặc sửa release |
| `release version 21 not supported` | Đang dùng `javac 17` nhưng yêu cầu release 21 | Dùng JDK 21 compiler hoặc giảm target khi source phù hợp |
| `No toolchain matched... jdk [ version='17' ]` | Thiếu entry/toolchain, vendor không khớp, hoặc jdkHome sai | Kiểm tra `~/.m2/toolchains.xml`, đường dẫn thực, version/vendor |
| `invalid target release: 17` | Compiler không hỗ trợ target 17 | Kiểm tra compiler JDK/đường executable |
| `UnsupportedClassVersionError` | Runtime JVM quá cũ so với bytecode của một class được load | Dùng JVM đủ mới hoặc biên dịch/rebuild đúng release |
| `NoSuchMethodError` sau khi chạy trên JDK cũ | Có thể tham chiếu API/library không tương thích, hoặc dependency conflict | Kiểm tra `--release`, dependency versions và runtime classpath |
| `cannot find symbol` khi giảm release | Mã dùng API/cú pháp không có ở release cũ | Sửa code hoặc nâng release mục tiêu |
| `The JAVA_HOME environment variable is not defined correctly` | Launcher không tìm được Java home hợp lệ | Sửa `JAVA_HOME` về JDK root, không phải `bin` hay `java.exe` |
| `mvn -version` in 21 nhưng `javap` major 61 | Maven chạy Java 21, bytecode nhắm Java 17 | Bình thường nếu `--release 17`; kiểm tra toolchain để biết compiler |
| `javac -version` in 21 nhưng Toolchains chọn 17 | Compiler trên shell PATH khác compiler Maven chọn | Không nhất thiết là lỗi; xem log Toolchains/Compiler |
| Test pass JDK 21, chạy JDK 17 lỗi | Runtime tests dùng JDK khác hoặc dependency/API không tương thích | Chạy test/smoke trên JDK 17 thực; kiểm tra dependencies |
| Maven/plugin không khởi động trên JDK cũ | Maven distribution hoặc plugin đòi JDK tối thiểu cao hơn | Đổi JDK chạy Maven; giữ compiler target độc lập khi cần |
| IDE build OK, CLI build FAIL | IDE JDK và Maven runner/toolchain khác nhau | So sánh Java runtime/compile settings ở cả hai |

**Cách đọc lỗi:** lấy **dòng lỗi gốc + version compiler thực sự được chọn**, không chỉ số Java trong `pom.xml`. Nếu có toolchains, câu hỏi đầu tiên là toolchain nào được chọn và `jdkHome` có trỏ đúng JDK hay không.

## 13. Quy trình chẩn đoán có thứ tự

### Bước 1 — xác định đúng Maven CLI đang chạy

```bash
mvn -version
```

Ghi lại Maven version, Java version, Java home và OS. Nếu project dùng Wrapper, chạy `./mvnw -version` (hoặc `mvnw.cmd -version` trên Windows) để kiểm tra Maven distribution và JVM theo lối chạy thật của dự án.

### Bước 2 — đối chiếu shell Java với Maven

```bash
echo "$JAVA_HOME"
java -version
javac -version
```

Đừng coi `javac -version` là kết luận cuối nếu POM có Toolchains hoặc `fork/executable`. Nó chỉ là một dữ kiện để so sánh.

### Bước 3 — xem effective POM

```bash
mvn help:effective-pom
```

Tìm `maven.compiler.release`, Compiler Plugin, Toolchains Plugin, `jdkToolchain`, `fork`, `executable`, các profiles và plugin management. Ở multi-module project, dùng `-f path/to/pom.xml` hoặc chọn module phù hợp để không xem nhầm POM aggregator.

### Bước 4 — xem toolchain selection trong log

```bash
mvn -B -ntp clean compile
```

Nếu Toolchains Plugin chạy, tìm “Required toolchain” và “Found matching toolchain”. Nếu cần nhiều thông tin hơn:

```bash
mvn -B -ntp -e clean compile
```

Khi thật sự cần debug sâu, `-X` cho thêm thông tin cấu hình; log có thể chứa local paths, repository URL và dữ liệu nhạy cảm khác, nên redact trước khi chia sẻ. Không bật debug chung trên CI có credentials nếu không có lý do.

### Bước 5 — xác minh bytecode, không đoán từ POM

```bash
javap -verbose target/classes/demo/App.class
```

Kỳ vọng major 61 với Java 17 release. Lưu ý `javap` có thể đọc class được tạo từ build **cũ** nếu bạn không chạy `clean`; hãy kiểm tra timestamp và dọn `target/` đúng cách khi muốn chứng minh output mới.

### Bước 6 — chạy trên runtime mục tiêu

```bash
/opt/jdks/temurin-17/bin/java -cp target/classes demo.App
```

Thay đường dẫn theo máy. Với project có dependency ngoài, `target/classes` một mình có thể không đủ; cần runtime classpath đầy đủ hoặc launcher/package phù hợp.

### Bước 7 — xác minh test runtime và production

Đọc cấu hình Surefire/Failsafe/toolchains và thực thi test matrix trên phiên bản Java mà production yêu cầu. Với Docker, kiểm tra runtime image JDK/JRE/tag; không mặc định image compiler và image runtime là một.

## 14. Bài tập suy luận

**Bài 1:** `mvn -version` in Java 21. POM có `maven.compiler.release=17` và **không có Toolchains**. Compiler Plugin mặc định dùng JDK nào?

**Đáp án:** Thông thường compiler của JDK chạy Maven là **21**, nhưng compiler nhận target `--release 17` và tạo bytecode major 61 (nếu source/dependencies tương thích). `--release` không tự chuyển sang `javac 17`.

**Bài 2:** Maven chạy trên JDK 21; POM có Toolchains yêu cầu JDK 17 và `toolchains.xml` trỏ đúng JDK 17. `mvn -version` sẽ in gì?

**Đáp án:** Vẫn in **Java 21** của Maven JVM. Toolchains chọn **JDK 17** cho compiler/toolchain-aware goals tương ứng; `mvn -version` không đổi.

**Bài 3:** Bạn có JDK 17 compiler, nhưng POM đặt `<release>21</release>`. Có thể build Java 21 bằng cách chỉ nâng Maven version?

**Đáp án:** Không. Compiler thực tế phải hỗ trợ release 21. Maven version không tự biến `javac 17` thành `javac 21`.

**Bài 4:** Compiler tạo major version 61. Có thể kết luận compiler chạy trên JDK 17?

**Đáp án:** Không. JDK 21 với `--release 17` cũng có thể tạo major 61. Phải kiểm tra compiler selection/log/toolchain.

**Bài 5:** Một library bên thứ ba chứa class major 65, còn ứng dụng được compile `--release 17`. Chạy trên Java 17 có chắc chắn thành công?

**Đáp án:** Không. Một dependency đã build cho Java 21 có thể không load được trên Java 17, bất kể class của ứng dụng target 17.

**Bài 6:** Surefire tests chạy trên Java 21, production Java 17. Compile `--release 17` đã đủ an toàn chưa?

**Đáp án:** Chưa. Cần test runtime Java 17 trong CI/smoke/integration, kiểm tra dependencies, native integration, reflection và runtime options.

**Bài 7:** Lỗi “No toolchain matched” có thể sửa bằng cách chỉ thay `<maven.compiler.release>21</maven.compiler.release>` không?

**Đáp án:** Không. Toolchain selection đang thiếu/mismatch JDK; đổi target không tự cài JDK hoặc sửa `toolchains.xml`.

## 15. Checklist trước khi kết luận project đang dùng đúng Java

- [ ] Tôi đã chạy `mvn -version` của **chính terminal/CI/IDE runner** đang build.
- [ ] Tôi phân biệt Java runtime của Maven với Java trên shell PATH và `JAVA_HOME`.
- [ ] Tôi biết Compiler Plugin đang dùng compiler mặc định, Toolchains hay `fork/executable`.
- [ ] Nếu có Toolchains, `~/.m2/toolchains.xml` trỏ đúng JDK cài thật và version/vendor khớp.
- [ ] Tôi đã chọn release mục tiêu bằng `maven.compiler.release` hoặc plugin configuration.
- [ ] Tôi hiểu `--release` không tự cài/chọn JDK và không nâng khả năng compiler cũ.
- [ ] Tôi đã kiểm tra `javap -verbose` thấy class file major đúng release mong muốn.
- [ ] Tôi không suy rằng bytecode đúng major là bằng chứng compiler JDK đúng version.
- [ ] Tôi đã kiểm tra JDK test runner (Surefire/Failsafe) riêng với Maven JVM nếu cần.
- [ ] Tôi đã thử chạy trên **runtime JDK** mà ứng dụng sẽ thực sự sử dụng.
- [ ] Tôi đã kiểm tra bytecode của dependencies bên thứ ba khi có lỗi `UnsupportedClassVersionError`.
- [ ] Tôi đã pin Maven/plugin versions hợp lý và ghi nhận JDK minimum requirements.
- [ ] Tôi không để path riêng của một máy thành yêu cầu hardcoded trong POM của cả nhóm.
- [ ] Trên CI, các JDK cần thiết được cài và cung cấp trong cùng job theo đúng quyền/cấu hình.
- [ ] Sau khi đổi Java version, tôi chạy `mvn clean verify` và smoke/integration tests phù hợp.

**Tóm tắt:** `JAVA_HOME`/Maven launcher quyết định **JVM khởi động Maven**; Maven Compiler Plugin mặc định có thể dùng compiler của JVM đó, nhưng **Toolchains** hoặc external `javac` cho phép chọn **JDK biên dịch độc lập**. `maven.compiler.release` xác định **ngôn ngữ, API chuẩn và bytecode đích**, không phải lựa chọn JDK. Để xác minh đúng, kết hợp **`mvn -version` + log Compiler/Toolchains + `javap` + thử chạy trên runtime mục tiêu**.

## Tài liệu Apache Maven và Java chính thức

- [Apache Maven — Guide to Using Toolchains](https://maven.apache.org/guides/mini/guide-using-toolchains.html)
- [Apache Maven Toolchains Plugin — Usage](https://maven.apache.org/plugins/maven-toolchains-plugin/usage.html)
- [Apache Maven Toolchains Plugin — JDK Toolchain](https://maven.apache.org/plugins/maven-toolchains-plugin/toolchains/jdk.html)
- [Apache Maven Compiler Plugin — Compiling Sources Using a Different JDK](https://maven.apache.org/plugins/maven-compiler-plugin/examples/compile-using-different-jdk.html)
- [Apache Maven Compiler Plugin — Setting the --release Option](https://maven.apache.org/plugins/maven-compiler-plugin/examples/set-compiler-release.html)
- [Apache Maven — Guide to Targeting a Java Version](https://maven.apache.org/guides/mini/guide-java-target.html)
- [Apache Maven — What's New in Maven 4](https://maven.apache.org/whatsnewinmaven4.html)
- [OpenJDK/Oracle Java SE 17 — javac Documentation](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html)
- [OpenJDK/Oracle Java SE 17 — javap Documentation](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javap.html)
