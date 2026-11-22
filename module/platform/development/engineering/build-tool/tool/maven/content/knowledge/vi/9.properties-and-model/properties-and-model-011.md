# Phân biệt MAVEN_OPTS, tùy chọn Maven và tùy chọn JVM kiểm thử

## 1. Ba tầng cấu hình thường bị nhầm lẫn

Khi một dự án Java chạy `mvn test` hoặc `./mvnw verify`, có thể xuất hiện **nhiều thành phần xử lý tùy chọn**:

1. **JVM chạy chính Maven**: tiến trình Java khởi động Maven Core và các Maven plugins. Nó nhận các JVM startup options qua **MAVEN_OPTS** và, tùy phiên bản/cách khởi chạy, **.mvn/jvm.config**.
2. **Maven CLI / Maven session**: chương trình Maven phân tích các tùy chọn như **-B**, **-X**, **-q**, **-T**, **-P**, **-pl**, **-Dkey=value**; chúng điều khiển Maven, reactor, profiles, user properties và plugins.
3. **JVM chạy kiểm thử**: Maven Surefire hoặc Failsafe có thể **fork** một hay nhiều tiến trình Java mới. JVM mới có startup options riêng như **-Xmx**, **-ea**, **--add-opens** và **-Dtest.key=value**, thông thường được cấu hình qua **argLine** của plugin. Các system properties phục vụ test cũng có thể được cung cấp qua **systemPropertyVariables**.

Sơ đồ:

~~~text
Shell / CI environment
    |
    | MAVEN_OPTS, .mvn/jvm.config
    v
[JVM 1: Maven launcher + Maven Core + plugins]
    |
    | Maven CLI: -B, -X, -P, -T, -pl, -D...
    | POM: properties, profiles, Surefire/Failsafe configuration
    |
    +------ surefire:test / failsafe goals ------+
                                               |
                                               | forkCount > 0
                                               | argLine, systemPropertyVariables
                                               v
                                  [JVM 2...: chạy JUnit/test]
                                               |
                                               v
                                    Báo cáo test, kết quả build
~~~

**Không suy ra rằng nâng bộ nhớ cho Maven bằng MAVEN_OPTS sẽ nâng bộ nhớ cho JVM chạy test.** Trường hợp test được fork, nó là một tiến trình Java khác và cần cấu hình riêng. Ngược lại, khi không fork (`forkCount=0`), test chạy trong tiến trình Maven, nên ranh giới này thay đổi; xem phần ngoại lệ.

Đề bài cũng yêu cầu phân biệt **Maven property** với **Java system property**: cả hai có thể viết bằng cú pháp **-D**, nhưng **nơi đọc và thời điểm áp dụng** không nhất thiết giống nhau.

## 2. Bảng định hướng nhanh: viết ở đâu thì ảnh hưởng tới đâu?

| Cú pháp/cơ chế | Ai nhận? | Ví dụ | Tác động chính |
| --- | --- | --- | --- |
| **MAVEN_OPTS** | JVM chạy Maven khi Maven launcher hỗ trợ | `-Xmx1g` | Heap hoặc JVM startup settings của Maven |
| **.mvn/jvm.config** | JVM chạy Maven | `-Xmx768m` | JVM options theo dự án cho Maven |
| **.mvn/maven.config** | Maven CLI | `-B`, `-ntp` | Các tùy chọn Maven dùng lặp lại theo dự án |
| **MAVEN_ARGS** (Maven 3.9+) | Maven CLI | `-B -V` | Các tham số Maven bổ sung từ môi trường |
| **mvn -X** | Maven CLI | `mvn -X test` | Log Maven mức debug; **không** đặt max heap |
| **mvn -DskipTests** | Maven user property, được plugin đọc | `mvn -DskipTests package` | Có thể bỏ chạy test theo Surefire/Failsafe |
| **mvn -Pci** | Maven CLI | `mvn -Pci verify` | Kích hoạt profile Maven tên ci |
| **mvn -T 2C** | Maven CLI | `mvn -T 2C verify` | Song song hóa reactor theo số CPU core |
| **Surefire argLine** | JVM test *được fork* | `-Xmx512m -Ddemo.flag=on` | Startup options của test JVM |
| **Surefire systemPropertyVariables** | Test execution / system properties | `<demo.mode>local</demo.mode>` | Java `System.getProperty("demo.mode")` trong test |
| **forkCount / reuseForks** | Surefire/Failsafe plugin | `forkCount=1` | Có tạo JVM riêng không, số lượng và tái sử dụng |
| **JAVA_TOOL_OPTIONS / JDK_JAVA_OPTIONS** | Java launcher/JVM tương thích, không riêng Maven | `-Dfile.encoding=UTF-8` | Có thể ảnh hưởng **nhiều** Java processes, cần kiểm tra |

Các biến và tệp cấu hình trên **không thay thế nhau**: đổi một giá trị ở Maven CLI không tự biến nó thành JVM startup option của tiến trình test. Một số Maven user properties có thể được Surefire truyền sang test dưới dạng system properties; điều đó được giải thích riêng, không nên dùng làm quy tắc ngầm cho mọi option.

## 3. MAVEN_OPTS: JVM startup options cho tiến trình Maven

**MAVEN_OPTS** là biến môi trường chứa tham số cho **JVM khởi chạy Maven**. Các ví dụ phổ biến:

- `-Xms256m`: heap ban đầu.
- `-Xmx1024m`: giới hạn heap tối đa theo cấu hình.
- `-XX:MaxMetaspaceSize=256m`: giới hạn metaspace khi phù hợp với runtime/JDK.
- `-Duser.timezone=UTC`: Java system property trong JVM của Maven.
- `-Dhttps.protocols=TLSv1.2`: ví dụ Java system property (cần đánh giá yêu cầu bảo mật, không áp dụng bừa).

Trên Linux/macOS:

~~~bash
export MAVEN_OPTS="-Xms256m -Xmx1024m"
mvn clean verify
~~~

Trên Windows PowerShell:

~~~powershell
$env:MAVEN_OPTS = '-Xms256m -Xmx1024m'
mvn clean verify
~~~

Trên Windows Command Prompt:

~~~bat
set "MAVEN_OPTS=-Xms256m -Xmx1024m"
mvn clean verify
~~~

Ba lệnh thiết lập biến ở trên là **các phương án theo hệ điều hành**, không cần chạy liên tiếp.

**Những điều MAVEN_OPTS làm được:**

- Cho JVM chạy Maven nhiều heap hơn nếu Maven Core hoặc plugin chạy trong cùng JVM cần thêm bộ nhớ.
- Cấp startup system properties cho Maven runtime.
- Áp dụng cho những lần chạy Maven được khởi động từ môi trường shell đó, nếu launcher có đọc biến.

**Những điều MAVEN_OPTS không đảm bảo:**

- Không tự tăng heap cho JVM được Surefire/Failsafe fork.
- Không tự cấu hình Maven reactor parallelism (dùng Maven CLI `-T`).
- Không tự chọn Maven profile hoặc plugin goal (`-P`, `-pl`, goals/phase thuộc Maven).
- Không thay thế cấu hình JUnit, Surefire hoặc Failsafe.
- Không có nghĩa mọi tùy chọn Java hợp lệ đều dùng được trên mọi phiên bản JDK; ví dụ tùy chọn cũ đã bị loại khỏi JDK 17 có thể khiến JVM Maven không khởi động.

Nếu gặp **OutOfMemoryError** trong lúc Maven xử lý mô hình/build plugin, tăng heap JVM Maven có thể phù hợp. Nếu OOM xuất hiện trong tiến trình **forked test JVM**, cần xem **Surefire/Failsafe argLine** hoặc số lượng forks; chỉ sửa MAVEN_OPTS thường không giải quyết đúng chỗ.

### Phân biệt -X và -Xmx

~~~bash
mvn -X test
~~~

**-X** ở đây là **tùy chọn Maven** để bật debug logging.

~~~bash
export MAVEN_OPTS="-Xmx1024m"
mvn test
~~~

**-Xmx1024m** là **tùy chọn Java JVM** giới hạn heap của Maven. Không thể rút gọn `-Xmx` thành `-X` rồi coi cùng ý nghĩa.

## 4. .mvn/jvm.config: tùy chọn JVM cho Maven theo repository

Thay vì yêu cầu mọi thành viên tự thiết lập biến môi trường, dự án có thể commit một tệp:

~~~text
project-root/
└── .mvn/
    ├── jvm.config
    └── maven.config
~~~

Ví dụ nội dung **.mvn/jvm.config**:

~~~text
-Xms256m
-Xmx768m
-Duser.timezone=UTC
~~~

Tệp này mang tham số JVM cho **Maven launcher** khi launcher/phiên bản hỗ trợ. Nó **không** phải danh sách goals Maven, cũng không phải tự động là `argLine` của test JVM.

**Tương tác với MAVEN_OPTS** cần lưu ý:

- Tài liệu cấu hình Apache Maven nêu rằng nếu cùng một option được đặt cả trong **MAVEN_OPTS** và **.mvn/jvm.config**, **Maven 3** ưu tiên giá trị đến từ **MAVEN_OPTS**, còn **Maven 4** ưu tiên giá trị từ **jvm.config**. Cách phân tích và launcher khác nhau có thể ảnh hưởng trường hợp đặc biệt.
- Thay vì dựa vào thứ tự ưu tiên của hai khai báo `-Xmx` trùng nhau, hãy giữ một nguồn chuẩn cho mỗi JVM option và kiểm tra Maven thực tế dùng phiên bản nào.
- Với Maven 3, **không đặt dòng chú thích bắt đầu bằng # trong jvm.config**; tài liệu Maven nêu cú pháp comment được hỗ trợ ở Maven 4. Việc đưa dấu # vào Maven 3 có thể làm launcher cố coi nó là tham số JVM không hợp lệ.
- File này áp dụng cho **JVM chạy Maven**, kể cả khi test được fork sau đó. JVM test có cấu hình riêng.

Khi thiết kế CI, nên thống nhất có dùng **MAVEN_OPTS** từ image runner hay **.mvn/jvm.config** từ repository, tránh vô tình khai báo cùng một option với giá trị khác nhau.

## 5. Tùy chọn Maven CLI: điều khiển build, goals, profiles và properties

Đây là những tham số chương trình Maven xử lý **sau khi JVM Maven đã khởi động**.

| Maven CLI | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| **-B** | `mvn -B verify` | Batch mode, phù hợp CI |
| **-q** | `mvn -q test` | Giảm log Maven |
| **-X** | `mvn -X test` | Bật debug log Maven |
| **-e** | `mvn -e test` | In stack trace khi có lỗi |
| **-U** | `mvn -U verify` | Buộc kiểm tra cập nhật snapshot và metadata liên quan theo chính sách Maven |
| **-o** | `mvn -o test` | Offline mode, chỉ dùng artifact/plugin đã khả dụng |
| **-P** | `mvn -Pci verify` | Chọn Maven profiles |
| **-T** | `mvn -T 2C verify` | Song song hóa multi-module reactor theo core multiplier |
| **-pl** | `mvn -pl module-a test` | Chỉ định module thuộc reactor |
| **-am** | `mvn -pl module-a -am test` | Kèm những module trong reactor mà module đã chọn cần |
| **-D** | `mvn -DskipTests package` | Gán Maven user property được Maven/plugin tiêu thụ |
| **-f** | `mvn -f path/to/pom.xml test` | Chọn POM cụ thể |
| **-ntp** | `mvn -ntp verify` | Không hiển thị transfer progress (trên Maven hỗ trợ) |

**-T** và **forkCount** là hai mức song song khác nhau: `-T` tác động đến cách Maven xử lý reactor modules, trong khi `forkCount` quy định số tiến trình JVM chạy test do Surefire/Failsafe quản lý. Kết hợp song song reactor với nhiều test forks có thể làm CPU/RAM tăng mạnh.

**-D** tại Maven CLI không có nghĩa đơn giản là mọi key đều là JVM startup flag. Ví dụ:

~~~bash
mvn -DskipTests package
mvn -Dmaven.test.skip=true package
mvn -Dtest=JvmScopeTest test
mvn -Dmaven.compiler.release=17 compile
~~~

- **-DskipTests** thường làm Surefire/Failsafe bỏ phần thực thi test nhưng các test sources vẫn có thể được biên dịch.
- **-Dmaven.test.skip=true** được các plugin liên quan hỗ trợ để bỏ cả test compilation và test execution; không dùng cách này để tuyên bố test đã pass.
- **-Dtest=JvmScopeTest** là tham số được Surefire hiểu để chọn lớp test cụ thể.
- **-Dmaven.compiler.release=17** là property dành cho cấu hình Maven Compiler Plugin, không phải tùy chọn `java -X...`.

Vì Maven user properties có thể được plugin dùng để nội suy POM hoặc chuyển tiếp sang test, phải đọc **plugin goal parameters và effective configuration** để biết chính xác hậu quả.

## 6. .mvn/maven.config và MAVEN_ARGS: mặc định cho Maven CLI

Một dự án có thể dùng **.mvn/maven.config** để tránh nhập lặp những CLI options:

~~~text
-B
-ntp
--fail-at-end
~~~

**Từ Maven 3.9.0**, mỗi argument nên nằm trên **một dòng riêng**. Tài liệu Maven cũng lưu ý: các dòng bắt đầu bằng **#** được hiểu là comment từ Maven **3.9.3**; không giả định mọi Maven 3.x đều hỗ trợ comment trong file này.

Các options trên là tùy chọn **Maven CLI**, không phải JVM startup flags. **Không đặt -Xmx1024m trong .mvn/maven.config** để mong Maven JVM có thêm RAM.

Tương tự, **MAVEN_ARGS** (được Apache Maven giới thiệu từ Maven 3.9.0) có thể chứa các đối số Maven được đặt trước CLI arguments. Ví dụ shell:

~~~bash
export MAVEN_ARGS="-B -V"
mvn test
~~~

Lệnh này ảnh hưởng **Maven session/CLI**; không biến `-B` hay `-V` thành tham số JVM. Khi tùy chọn xung đột giữa environment, maven.config và CLI, ưu tiên cách cấu hình rõ ràng, kiểm tra hành vi của phiên bản Maven cụ thể và tránh đặt giá trị trái nhau không cần thiết.

Với Maven Wrapper, script `./mvnw` có vai trò chuẩn bị bản Maven được pin cho dự án. Nó không biến tùy chọn **MAVEN_OPTS** thành `argLine` hoặc làm mọi tùy chọn trong **.mvn/maven.config** trở thành flags cho Java launcher.

## 7. JVM kiểm thử của Surefire/Failsafe là một tiến trình khác khi fork

**Maven Surefire Plugin** thường chạy unit tests ở phase **test**. **Maven Failsafe Plugin** thường hỗ trợ integration tests tại **integration-test/verify** khi dự án cấu hình tương ứng.

Khi Surefire/Failsafe có **forkCount lớn hơn 0**, plugin khởi động **JVM kiểm thử riêng**. JVM đó có classpath, memory, startup flags, system properties và vòng đời riêng. Với Surefire:

- **argLine**: chuỗi **JVM startup arguments** dùng để khởi chạy forked JVM. Ví dụ `-Xmx512m -Ddemo.fork=test`.
- **systemPropertyVariables**: hệ thống tên/giá trị Java system properties được chuyển đến test execution, thường đọc bằng `System.getProperty`.
- **forkCount**: số JVM fork mà plugin được phép sử dụng theo cấu hình (có thể dùng core multiplier).
- **reuseForks**: liệu các forked JVM có được tái sử dụng giữa các test classes.
- **jvm**: tùy chọn đường dẫn JVM executable cho fork, khi có yêu cầu chạy test trên JDK khác.

Ví dụ Surefire config:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-surefire-plugin</artifactId>
    <version>3.5.2</version>
    <configuration>
        <forkCount>1</forkCount>
        <reuseForks>true</reuseForks>
        <argLine>-Xmx512m -Ddemo.fork=from-argline</argLine>
        <systemPropertyVariables>
            <demo.mode>from-surefire</demo.mode>
        </systemPropertyVariables>
    </configuration>
</plugin>
~~~

Đây là **mảnh plugin configuration** cần đặt trong **pom.xml** hợp lệ. Các thông số:

- **-Xmx512m** đặt heap limit cho forked test JVM, **không phải** heap limit cho Maven Core.
- **-Ddemo.fork=from-argline** truyền Java system property **trước lúc forked JVM khởi động**.
- **demo.mode** được Surefire đưa thành system property để test đọc, **không yêu cầu** viết Java startup flag trực tiếp.
- **forkCount=1** bảo đảm ví dụ dùng mô hình có fork, để **argLine** thực sự áp dụng.
- **reuseForks=true** cho phép tái sử dụng fork nhằm giảm overhead.

Không giả định mỗi phương thức `@Test` có một JVM mới. Với `forkCount=1` và `reuseForks=true`, các test classes có thể dùng chung một fork theo quyết định của plugin.

## 8. -D trong Maven CLI có thể đi tới test: ngoại lệ quan trọng

Một cách diễn giải quá đơn giản là “Maven -D hoàn toàn không ảnh hưởng test JVM”. Điều đó **không chính xác**.

Surefire có cơ chế chuyển một số properties từ Maven session sang system properties của test. Theo tài liệu Surefire, những nguồn cung cấp effective system properties có thể gồm:

1. Java startup properties từ **argLine** (với forked JVM).
2. **systemProperties** kiểu cũ, ít được khuyến nghị.
3. **systemPropertiesFile**.
4. **systemPropertyVariables**.
5. **Maven session user properties** (thường được đặt bằng `mvn -Dkey=value`) nếu **promoteUserPropertiesToSystemProperties** được bật.

Trong cơ chế merge này, nguồn sau có thể ghi đè nguồn trước đối với cùng tên property, tùy cấu hình plugin. Vì vậy:

~~~bash
mvn -Ddemo.mode=from-cli test
~~~

có thể khiến test đọc **System.getProperty("demo.mode") = "from-cli"**, dù POM đặt **demo.mode=from-surefire**, khi Surefire đang bật chuyển Maven user properties vào test (hành vi mặc định của phiên bản Surefire hiện hành).

**Nhưng việc truyền Maven user property không đồng nghĩa mọi thứ là JVM startup option.** Các flags cần có hiệu lực khi Java VM được tạo, đặc biệt `-Xmx`, `--add-opens`, và một số VM system properties, phải được đặt đúng chỗ, thường là **argLine** đối với forked JVM.

**Hai loại `-D` cần phân biệt theo nơi xuất hiện:**

- **`mvn -Ddemo.mode=ci test`**: Maven nhận một **user property**; plugin có thể dùng hoặc chuyển tiếp.
- **`<argLine>-Ddemo.fork=on</argLine>`**: Java launcher của **forked test JVM** nhận system property khi JVM bắt đầu.

Tên giống nhau nhưng lối đi khác; với các plugin, properties có thể tương tác và ghi đè nhau. Để tránh cấu hình bất ngờ, đừng dùng cùng một key ở nhiều nguồn nếu không có mục đích và test kiểm chứng.

## 9. Ví dụ hoàn chỉnh Java 17 + JUnit Jupiter

Ví dụ sau được thiết kế để chứng minh ba tầng:

- Maven JVM có thể nhận bộ nhớ từ **MAVEN_OPTS** hoặc **.mvn/jvm.config**.
- Maven CLI nhận goals và options, ví dụ `-B`, `-Dtest=...`.
- Surefire tạo một test JVM riêng với heap **512m**, property `demo.fork` từ **argLine** và `demo.mode` từ **systemPropertyVariables**.

### 9.1. Cấu trúc thư mục

~~~text
maven-option-scope/
├── pom.xml
├── .mvn/
│   ├── jvm.config
│   └── maven.config
└── src/
    ├── main/java/com/example/scope/App.java
    └── test/java/com/example/scope/JvmScopeTest.java
~~~

**.mvn/jvm.config** (cho JVM chạy Maven):

~~~text
-Xms256m
-Xmx768m
~~~

**.mvn/maven.config** (cho Maven CLI, ví dụ Maven 3.9+):

~~~text
-B
-ntp
~~~

Không đặt **-Xmx512m** của JVM kiểm thử vào hai file trên; cấu hình test fork nằm trong plugin Surefire.

### 9.2. pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>maven-option-scope</artifactId>
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
                <version>3.13.0</version>
            </plugin>

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.5.2</version>
                <configuration>
                    <forkCount>1</forkCount>
                    <reuseForks>true</reuseForks>
                    <argLine>-Xmx512m -Ddemo.fork=from-argline</argLine>
                    <systemPropertyVariables>
                        <demo.mode>from-surefire</demo.mode>
                    </systemPropertyVariables>
                </configuration>
            </plugin>

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-jar-plugin</artifactId>
                <version>3.4.2</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**Đọc POM đúng phạm vi:**

- **maven.compiler.release=17** điều khiển Maven Compiler Plugin cho Java 17; nó không chọn kích thước heap cho Maven hoặc test fork.
- **junit-jupiter** có scope **test**, không đưa API JUnit vào main runtime classpath.
- **Surefire argLine** chỉ áp dụng tới JVM kiểm thử do Surefire fork trong cấu hình này.
- **systemPropertyVariables** cấp giá trị test-specific; có thể chịu quy tắc merge với CLI Maven user properties nếu cùng tên.
- **forkCount=1** giúp tránh hiểu nhầm test đang chạy ngay trong Maven JVM.

Các phiên bản được pin để ví dụ có tính lặp lại. Khi tích hợp vào dự án dùng parent POM/BOM, cần kiểm tra chính sách phiên bản chung.

### 9.3. Java class sản phẩm

Tạo file **src/main/java/com/example/scope/App.java**:

~~~java
package com.example.scope;

public final class App {
    private App() {
    }

    public static String message() {
        return "Product runs";
    }

    public static void main(String[] args) {
        System.out.println(message());
    }
}
~~~

Class này hoàn toàn không phụ thuộc vào Surefire/JUnit. Khi chạy như ứng dụng sản phẩm, nó không nhận **demo.mode** chỉ vì POM có Surefire configuration; để có system property cho *ứng dụng production*, phải truyền vào tiến trình Java ứng dụng hoặc cấu hình runtime của ứng dụng theo cơ chế riêng.

### 9.4. JUnit test kiểm tra JVM fork

Tạo **src/test/java/com/example/scope/JvmScopeTest.java**:

~~~java
package com.example.scope;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

class JvmScopeTest {

    @Test
    void receivesStartupPropertyFromArgLine() {
        assertEquals(
                "from-argline",
                System.getProperty("demo.fork")
        );
    }

    @Test
    void receivesPropertyFromSurefireConfiguration() {
        assertEquals(
                "from-surefire",
                System.getProperty("demo.mode")
        );
        assertNotNull(System.getProperty("java.version"));
    }

    @Test
    void canCallProductionCode() {
        assertEquals("Product runs", App.message());
    }
}
~~~

Với POM minh họa, test có **3 phương thức @Test**. Không dùng `MAVEN_OPTS` để cấp **demo.fork**: system property đó đến từ **argLine**. Test **receivesPropertyFromSurefireConfiguration** cố ý giả định **không có người dùng/CI đặt Maven user property demo.mode khác**; nếu gọi `mvn -Ddemo.mode=...` và Surefire đang promote user properties, giá trị có thể đổi và assertion fail đúng như phần 8 giải thích.

### 9.5. Chạy ví dụ và xác nhận kết quả

Yêu cầu: JDK 17+ và Maven 3.9+; nếu chưa có dependencies/plugins trong cache, cần truy cập repository được cấu hình.

Từ thư mục **maven-option-scope**:

~~~bash
mvn -version
mvn clean test
~~~

Trong môi trường không đặt property `demo.mode` trùng tên ngoài POM, test phải có:

~~~text
Tests run: 3, Failures: 0, Errors: 0, Skipped: 0
~~~

Đây là **dòng tóm tắt dự kiến** của Surefire; tiền tố/số dòng log khác có thể khác theo phiên bản và cấu hình. Nếu tất cả goals thành công, Maven báo build thành công.

Chạy riêng một class test thông qua Maven CLI:

~~~bash
mvn -Dtest=JvmScopeTest test
~~~

**-Dtest=JvmScopeTest** là user property được **Surefire** dùng để chọn test. Nó không phải một Java VM flag yêu cầu JVM tìm class có tên `JvmScopeTest` để chạy bằng `java`.

Chạy sản phẩm độc lập sau compile:

~~~bash
java -cp target/classes com.example.scope.App
~~~

Stdout chính xác của lệnh Java là:

~~~text
Product runs
~~~

Bạn cũng có thể chạy:

~~~bash
mvn clean package
java -cp target/maven-option-scope-1.0.0.jar com.example.scope.App
~~~

Lệnh Java từ JAR cũng in **Product runs**. POM không khai báo **Main-Class** trong manifest nên đừng mặc định lệnh `java -jar` hoạt động.

### 9.6. Kiểm tra thay đổi heap Maven và heap test là hai việc khác nhau

Ở ví dụ, file **.mvn/jvm.config** khai báo **-Xmx768m** cho Maven JVM. POM Surefire khai báo **-Xmx512m** cho test fork. Đây là **hai giới hạn khác nhau**.

Để thử đặt Maven heap qua môi trường, có thể tạm sử dụng:

~~~bash
export MAVEN_OPTS="-Xmx1024m"
mvn test
~~~

Lưu ý khai báo **-Xmx** này trùng với giá trị trong **.mvn/jvm.config**. Với Maven 3, tài liệu cấu hình nêu **MAVEN_OPTS ưu tiên**; nên thử trên runner riêng rồi thống nhất một nguồn cấu hình. Không dùng ví dụ này để suy ra test JVM đã tăng từ **512m** lên **1024m**: **argLine** trong POM vẫn đặt test fork heap **512m**.

Nếu test OOM, xem stack trace, Surefire reports/dump, **forkCount**, **argLine**, giới hạn memory container và bộ nhớ của JDK thực tế. Tăng Maven heap chỉ vì thấy lệnh `mvn test` thất bại là chẩn đoán sai tầng.

## 10. forkCount=0: khi test không nằm trong JVM riêng

Surefire/Failsafe hỗ trợ cấu hình không fork:

~~~xml
<configuration>
    <forkCount>0</forkCount>
</configuration>
~~~

Khi **forkCount=0**, test chạy trong tiến trình Maven. Do không tạo forked JVM mới, **argLine** không được dùng để khởi tạo một JVM test riêng; những startup options như **-Xmx** của JVM Maven có thể trở thành giới hạn áp dụng cho các test đang chạy cùng process.

Điều này làm ranh giới đơn giản “MAVEN_OPTS chỉ cho Maven, argLine chỉ cho test” có một **ngoại lệ quan trọng**: nếu không fork, test dùng **cùng JVM với Maven**. Tuy nhiên, không nên coi việc tắt fork là cách thay thế thông thường cho cấu hình bộ nhớ test:

- Test cùng JVM có thể làm nhiễm system properties/static state, tăng rủi ro side effects với Maven process và các plugins.
- Một số tính năng test startup phụ thuộc fork mới hoạt động như kỳ vọng; **argLine** cho fork sẽ không có tác dụng.
- Build song song reactor với `-T` kết hợp `forkCount=0` có các rủi ro không an toàn liên quan system properties, được tài liệu Surefire cảnh báo.
- Với thử nghiệm cần `--add-opens`, Java agents hoặc bộ nhớ riêng, nên dùng forked JVM nếu môi trường cho phép.

**Khi cần debug test**, trước tiên xác nhận `forkCount` và plugin đang chạy. Không suy ra cấu hình test fork từ việc chỉ thấy một process Java.

## 11. Khi cần JVM arguments khác biệt cho Failsafe integration tests

Surefire và Failsafe là **hai plugin khác nhau**. Một POM có thể dùng Surefire cho unit tests và Failsafe cho integration tests. Nếu Failsafe tạo forked JVM riêng, nó cũng có cấu hình tương tự như **argLine** và **systemPropertyVariables**.

Ví dụ mảnh cấu hình Failsafe (chỉ minh họa khi dự án có integration tests và đã khai báo executions):

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-failsafe-plugin</artifactId>
    <version>3.5.2</version>
    <configuration>
        <forkCount>1</forkCount>
        <argLine>-Xmx1024m -Ddemo.integration=true</argLine>
        <systemPropertyVariables>
            <test.scope>integration</test.scope>
        </systemPropertyVariables>
    </configuration>
    <executions>
        <execution>
            <goals>
                <goal>integration-test</goal>
                <goal>verify</goal>
            </goals>
        </execution>
    </executions>
</plugin>
~~~

Cấu hình này **không nằm trong ví dụ chạy độc lập ở phần 9**; nó chỉ là một lựa chọn khi dự án thực sự cần integration tests. Vì hai plugin có configuration riêng, điều chỉnh **Surefire argLine** không tự bảo đảm Failsafe nhận cùng giới hạn heap.

Nên đặt mức RAM theo nhu cầu của từng nhóm test, tính tới số lượng test forks song song và giới hạn RAM thực tế của runner.

## 12. Khi nào dùng argLine và khi nào dùng systemPropertyVariables?

| Yêu cầu | Vị trí nên cấu hình cho test fork | Lý do |
| --- | --- | --- |
| Giới hạn heap của test JVM | **argLine: -Xmx...** | Java VM đọc khi khởi động |
| Mở module Java để reflection khi thật sự cần | **argLine: --add-opens ...** | JVM startup module-access option |
| Bật assertions của JVM | **argLine: -ea** | Java launcher option |
| Gắn Java agent cho test | **argLine: -javaagent:...** / cấu hình chuyên dụng | JVM agent cần có từ lúc khởi động |
| Đặt property nghiệp vụ `demo.mode` | **systemPropertyVariables** | Test đọc qua **System.getProperty** |
| Property phải áp dụng từ VM startup | **argLine: -D...** | Một số properties được VM cache trước khi test bắt đầu |
| Chọn class test | **Maven CLI -Dtest=...** hoặc Surefire config | Đây là chức năng discovery của Surefire |
| Chọn test reports/tham số plugin | **Surefire configuration hoặc Maven user property plugin hỗ trợ** | Không cần đổi JVM startup |
| Tăng bộ nhớ Maven Core | **MAVEN_OPTS/.mvn/jvm.config** | Đúng tiến trình Maven |

Theo tài liệu Surefire, một số properties như **file.encoding**, **java.library.path** có thể phải được cung cấp bằng **argLine** nếu muốn chúng có tác dụng khởi tạo JVM test, chứ không chỉ thêm bằng systemPropertyVariables sau khi JVM đã được tạo.

### Tránh đè argLine của công cụ coverage

Một số plugin, như **JaCoCo prepare-agent**, có thể ghi Java agent options vào property **argLine**. Nếu Surefire lại đặt `<argLine>-Xmx512m</argLine>` tĩnh, cấu hình đó có thể **bỏ mất Java agent** được plugin coverage dự tính.

Surefire hỗ trợ late property evaluation dạng **@{argLine}** để lấy property được đặt bởi goal chạy trước:

~~~xml
<properties>
    <argLine></argLine>
</properties>
...
<configuration>
    <argLine>@{argLine} -Xmx512m</argLine>
</configuration>
~~~

Đoạn trên là **minh họa các phần POM bổ sung**, không phải XML độc lập. Khai báo property rỗng giúp tránh placeholder không được thay khi plugin agent không có mặt. Khi có JaCoCo hoặc plugin instrumentation khác, kiểm tra chính xác propertyName mà plugin tạo, thứ tự execution, và run tests để chắc chắn agent options không bị mất.

## 13. Quan sát cấu hình được áp dụng thực tế

Không chỉ nhìn vào `MAVEN_OPTS` hoặc POM nguồn; nên kiểm tra theo từng tầng.

**Tầng 1 – Maven process/JVM:**

~~~bash
mvn -version
mvn -X validate
~~~

`mvn -version` xác nhận Maven/JDK được dùng; `-X` cho debug log về cấu hình Maven nhưng có thể rất dài. Trên máy thử nghiệm, dùng các công cụ JVM như **jcmd** hoặc process inspector có thể hỗ trợ kiểm tra JVM arguments của tiến trình Maven khi tiến trình đang sống.

**Tầng 2 – Maven CLI/model:**

~~~bash
mvn help:effective-pom
mvn help:active-profiles
mvn -Dtest=JvmScopeTest test
~~~

`help:effective-pom` cho biết cấu hình POM hiệu lực (theo profile và inheritance), nhưng **không phải trình xem đầy đủ biến môi trường của JVM fork**. `-Dtest` điều khiển test selection của Surefire trong ví dụ.

**Tầng 3 – test fork:**

~~~bash
mvn -Dtest=JvmScopeTest test
~~~

Test có thể gọi:

~~~java
System.getProperty("demo.fork");
System.getProperty("demo.mode");
Runtime.getRuntime().maxMemory();
~~~

Ba dòng trên là **các biểu thức minh họa bên trong một JVM đang chạy**, không phải chương trình Java độc lập. Hai dòng đầu đọc Java system properties; dòng cuối giúp quan sát bộ nhớ heap tối đa ước tính tại runtime. Không so sánh `maxMemory()` với `-Xmx` như một phép so sánh số byte tuyệt đối trên mọi JVM vì cơ chế runtime/heap alignment có thể làm trị số quan sát khác đôi chút.

Báo cáo Surefire thường ở **target/surefire-reports/**. Nếu forked VM không khởi động hoặc bị kill, có thể có dump/log hữu ích tùy phiên bản plugin và kiểu lỗi.

**Bảo mật:** log mức `-X`, process command line và các tham số `-Dpassword=...` có thể lộ dữ liệu. Không đưa secret thật vào POM, `.mvn/jvm.config`, `.mvn/maven.config` hoặc command line nếu có cơ chế secret manager/environment phù hợp.

## 14. Chẩn đoán thường gặp: sửa đúng tiến trình

| Triệu chứng | Khả năng liên quan | Cách kiểm tra |
| --- | --- | --- |
| Maven process OOM trước hoặc trong plugin goals, test chưa fork | Heap của **Maven JVM** | **MAVEN_OPTS**, `.mvn/jvm.config`, JDK/container memory |
| Surefire báo forked VM bị kill hoặc OOM | Heap/flags của **forked test JVM** | Surefire **argLine**, **forkCount**, **reuseForks**, RAM runner |
| `mvn -X test` tạo log quá lớn | Maven debug option **-X** | Bỏ `-X`, chỉ bật khi chẩn đoán |
| Đặt `-Xmx` sau lệnh mvn gây lỗi option | Đã đưa JVM startup option vào **Maven CLI** | Chuyển sang MAVEN_OPTS/jvm.config hoặc Surefire argLine đúng chỗ |
| Test không nhận `demo.fork` | **argLine** không áp dụng hoặc test không fork | Xem forkCount, effective plugin config và log |
| Test đọc property khác POM `systemPropertyVariables` | CLI **-D** cùng key được Surefire promote | Kiểm tra user properties, promote setting và thứ tự override |
| Unit test pass nhưng integration test OOM | Failsafe có cấu hình riêng | Kiểm tra Failsafe fork/argLine |
| `.mvn/maven.config` báo lỗi tham số | Đặt JVM flag trong file Maven CLI hoặc cú pháp không đúng bản Maven | Đưa JVM flag sang jvm.config; mỗi argument một dòng ở Maven 3.9+ |
| Maven 3 khởi động lỗi tại `#` trong jvm.config | Comment không được hỗ trợ trong Maven 3 | Bỏ dòng comment hoặc nâng cấp/cấu hình theo tài liệu |
| Heap thực tế khác giá trị mong đợi | Trùng MAVEN_OPTS và jvm.config hoặc giới hạn container | Kiểm tra Maven version, launcher, effective JVM args |
| Thêm `-DskipTests` nhưng test vẫn compile | Skip execution không mặc định skip compilation | Xem `maven.test.skip` khi cần bỏ cả compile (không phải QA pass) |
| `-T` khiến CI quá tải | Reactor parallelism nhân với test forks | Xem cả `-T`, `forkCount` và số modules |
| Coverage bỗng biến mất | `argLine` tĩnh đè agent options | Kiểm tra JaCoCo late property evaluation |
| Build local chạy được, CI lỗi khác JDK | Maven Java, test JVM executable hoặc startup args khác | So sánh `mvn -version`, CI image, Surefire `jvm` và logs |

Một câu hỏi hữu ích khi gặp OOM là: **“Tiến trình Java nào đã hết bộ nhớ?”** Nếu không biết PID/stack trace của tiến trình lỗi, việc tăng `MAVEN_OPTS` hoặc `argLine` theo cảm tính có thể che đi vấn đề nhưng không sửa nguyên nhân.

## 15. Quy trình chọn nơi đặt tùy chọn

1. Nếu tùy chọn điều khiển **cách Maven gọi build**, ví dụ profiles, reactor, debug, offline, chọn **Maven CLI**, `.mvn/maven.config` hoặc MAVEN_ARGS khi phù hợp.
2. Nếu tùy chọn điều khiển **JVM đang chạy Maven**, đặc biệt heap, chọn **MAVEN_OPTS** hoặc `.mvn/jvm.config`.
3. Nếu tùy chọn là **JVM startup flag của test fork**, chọn **Surefire/Failsafe argLine**, không dựa vào MAVEN_OPTS.
4. Nếu tùy chọn là **giá trị test đọc bằng System.getProperty**, chọn **systemPropertyVariables** hoặc một cơ chế user property có chủ đích, nhưng hiểu rõ precedence.
5. Nếu không tạo test fork (`forkCount=0`), nhận biết test đang chạy trong **Maven JVM** và `argLine` không phát huy vai trò tạo VM mới.
6. Nếu plugin coverage/debug/instrumentation có Java agent, kiểm tra việc hợp nhất **argLine** và options của agent.
7. Khi cấu hình ở nhiều nguồn, kiểm tra phiên bản Maven/Surefire, effective POM, active profiles, môi trường và **log của đúng JVM**.
8. Thử build ở runner sạch có giới hạn CPU/RAM giống production CI; không lấy việc laptop chạy được làm bằng chứng đủ.
9. Không commit secrets hoặc in toàn bộ command line có mật khẩu ra log.
10. Ghi trong README dự án **tùy chọn nào thuộc tầng nào** để đồng đội không nhầm `-X`, `-Xmx`, Maven `-D` với Java `-D`.

## 16. Bài tập phân biệt ba loại option

**Tình huống A:** Build nhiều module OOM ngay lúc Maven tạo effective model, chưa chạy unit test.

Đáp án: tập trung vào **Maven process/JVM** (`MAVEN_OPTS`, `.mvn/jvm.config`), kích thước reactor, plugin workload và giới hạn runner. Thay Surefire `argLine` có thể hoàn toàn không ảnh hưởng.

**Tình huống B:** `mvn test` chạy compiler thành công, sau đó Surefire báo JVM fork bị OutOfMemoryError.

Đáp án: xem **forkCount**, **argLine -Xmx...** và số JVM fork; cần đánh giá tổng RAM của tiến trình Maven cộng các forks.

**Tình huống C:** Muốn bật Maven debug log để biết profile nào active.

Đáp án: **`mvn -X test`** hoặc Help Plugin phù hợp. **-Xmx** là giới hạn heap, không bật Maven debug.

**Tình huống D:** Muốn test JUnit đọc `System.getProperty("demo.mode")` là `ci` mà không động tới startup flags.

Đáp án: cấu hình `<systemPropertyVariables><demo.mode>ci</demo.mode></systemPropertyVariables>` trong Surefire/Failsafe, hoặc chủ động cung cấp Maven user property nếu plugin đang hỗ trợ promote. Kiểm tra sự trùng tên và precedence.

**Tình huống E:** Trong CI đã đặt `MAVEN_OPTS=-Xmx2g`, test fork vẫn chỉ có heap khoảng `512m`.

Đáp án: hoàn toàn hợp lý khi Surefire **argLine** đặt **-Xmx512m** và **forkCount>0**. Hai JVM khác nhau.

**Tình huống F:** Dự án đặt `-B` trong `.mvn/jvm.config` rồi JVM Maven không khởi động.

Đáp án: **-B** thuộc **Maven CLI**, chuyển sang `.mvn/maven.config` hoặc lệnh `mvn -B ...`.

**Tình huống G:** Một Java agent JaCoCo không xuất hiện ở test fork sau khi thêm `<argLine>-Xmx512m</argLine>`.

Đáp án: kiểm tra cơ chế `argLine` được JaCoCo chuẩn bị và dùng late evaluation `@{argLine}`/cơ chế plugin hỗ trợ thay vì ghi đè tĩnh.

## Tài liệu tham khảo

- [Apache Maven — Configuring Apache Maven (MAVEN_OPTS, MAVEN_ARGS, jvm.config, maven.config)](https://maven.apache.org/configure)
- [Apache Maven — Command Line Options](https://maven.apache.org/ref/current/maven-embedder/cli.html)
- [Maven Surefire Plugin — Fork Options and Parallel Test Execution](https://maven.apache.org/surefire/maven-surefire-plugin/examples/fork-options-and-parallel-execution.html)
- [Maven Surefire Plugin — Using System Properties](https://maven.apache.org/surefire/maven-surefire-plugin/examples/system-properties.html)
- [Maven Surefire Plugin — surefire:test goal parameters](https://maven.apache.org/surefire/maven-surefire-plugin/test-mojo.html)
- [Maven Failsafe Plugin — Introduction](https://maven.apache.org/surefire/maven-failsafe-plugin/)
- [Maven Surefire Plugin — Java agents and argLine](https://maven.apache.org/surefire/maven-surefire-plugin/faq.html)
