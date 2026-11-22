# Fork JVM, tái sử dụng tiến trình và cô lập trạng thái kiểm thử trong Maven

## 1. Tại sao Maven có thể chạy test trong JVM riêng?

Một bộ unit tests có thể chạy tốt khi đứng riêng nhưng thất bại khi chạy cùng các test khác. Nguyên nhân đôi khi không nằm ở assertion mà ở **trạng thái dùng chung**: biến `static`, JVM system properties, singleton cache, thread nền, locale, timezone, classloader hoặc tài nguyên bên ngoài như file và cổng mạng.

Maven Surefire Plugin cung cấp cách quản lý **JVM thực thi test**. Thay vì chạy tất cả test trong chính JVM đang chạy Maven, Surefire có thể tạo một hay nhiều **forked JVM processes**. Các tham số quan trọng nhất:

- `forkCount`: số **JVM chạy test đồng thời tối đa** cho một lần thực thi Surefire theo ngữ cảnh.
- `reuseForks`: mỗi forked JVM có được **tái sử dụng để chạy nhiều test classes** hay không.
- `argLine`: các **JVM options** dành cho tiến trình test **được fork**, chẳng hạn heap size hoặc system property.
- `systemPropertyVariables`: các system properties Surefire truyền vào bối cảnh thực thi test.
- `forkedProcessTimeoutInSeconds` và các tham số timeout khác: cách giám sát tiến trình bị treo; cần xem đúng tài liệu plugin version.

Trong Maven 3 và Surefire 3.5.4, mặc định phổ biến là **`forkCount=1`, `reuseForks=true`**: một forked JVM được khởi tạo cho module và có thể chạy nhiều test classes liên tiếp. Khi đặt `reuseForks=false`, Surefire tạo **JVM mới cho từng test class**, không phải từng phương thức `@Test`.

Bài học thuộc nhóm **Kiểm thử đơn vị** và hướng đến các mục tiêu:

1. Phân biệt **Maven JVM**, **forked test JVM**, **test class**, **test method** và **thread**.
2. Hiểu ý nghĩa, mặc định và các tổ hợp `forkCount`/`reuseForks` thông dụng.
3. Biết những loại trạng thái được cô lập bởi ranh giới JVM, những loại không được cô lập.
4. Thực hành Java 17, JUnit Jupiter và Surefire để nhìn thấy PID, fork number và biến `static`.
5. Điều khiển JVM options và system properties bằng `argLine`, `systemPropertyVariables`.
6. Chọn chiến lược theo tốc độ, RAM, độ ổn định và nguy cơ test flakiness.
7. Phân biệt **fork parallelism**, **JUnit thread parallelism** và **Maven reactor `-T`**.
8. Chẩn đoán lỗi fork crash, timeout, test output và classpath.

Phiên bản trong ví dụ được chốt để có thể tái hiện trong Java 17; không có khẳng định chúng là những phiên bản mới nhất của Maven, JUnit hoặc Surefire.

## 2. Những ranh giới thực thi khác nhau

Hãy hình dung:

~~~text
Terminal
  │
  └── mvn test
        │
        ▼
  JVM chạy Maven (Maven process)
        │
        ├── Compiler Plugin: compile main/test sources
        │
        └── Maven Surefire Plugin
               │
               ├── Forked JVM #1
               │     ├── AlphaTest
               │     └── BetaTest (nếu reuseForks=true)
               │
               └── Forked JVM #2 (nếu forkCount cho phép/cần)
                     ├── GammaTest
                     └── DeltaTest
~~~

Đây là sơ đồ **khái niệm**; số fork thực sự phụ thuộc cấu hình, số test classes và lịch chạy.

Phân biệt:

| Cấp | Ví dụ | Chia sẻ trạng thái với ai? |
| --- | --- | --- |
| **Maven process** | JVM chạy Maven core/plugins | Chính Maven và các tác vụ không fork; không đồng nhất với test JVM forked. |
| **Forked JVM** | JVM con do Surefire khởi tạo | Các test classes được phân về cùng tiến trình có thể chia sẻ JVM-wide state. |
| **Classloader** | Loader chứa test/application classes | Quyết định phạm vi một số `static`, không đồng nghĩa với process. |
| **Test class** | `AlphaTest` | Nhiều phương thức test trong cùng class; fork thường được phân theo **class**. |
| **Test instance** | Một đối tượng JUnit test | JUnit 5 mặc định tạo instance theo method, nhưng điều đó không reset `static`. |
| **Thread** | Thread chạy một test | Các thread trong cùng JVM chia sẻ heap, system properties và static state. |
| **OS/external resource** | File, DB, socket, service | Có thể bị chia sẻ giữa nhiều JVM độc lập. |

**Cô lập JVM không đồng nghĩa cô lập toàn bộ môi trường.** Hai test JVM có heap, static fields và system properties riêng, nhưng vẫn có thể cùng sửa một file `target/shared.txt`, dùng cùng bảng database hoặc tranh chấp cổng TCP.

### Fork khác thread

Forked JVM là **tiến trình Java mới**: có PID, heap, GC, system properties, classloaders và lifecycle riêng. Thread mới trong cùng JVM **không tạo heap hay biến `static` riêng**. Dùng `forkCount=2` và bật JUnit parallel execution là hai quyết định độc lập, cần phân biệt khi tìm nguyên nhân race conditions.

## 3. Tham số `forkCount`

Theo tài liệu Surefire, `forkCount` xác định **số forked JVM có thể chạy test song song tối đa**.

| Giá trị | Ý nghĩa |
| --- | --- |
| `0` | Không tạo fork: chạy test trong **JVM đang thực thi Maven** theo cơ chế của plugin. |
| `1` | Tối đa một forked JVM ở một thời điểm cho lần thực thi Surefire. |
| `2` | Tối đa hai forked JVM đồng thời; test classes được phân phát cho chúng. |
| `4` | Tối đa bốn JVM đồng thời; có thể tốn nhiều RAM hơn. |
| `1C` | Số JVM tối đa theo một hệ số tính trên số CPU cores mà Surefire sử dụng. |
| `1.5C` | Hệ số nhân theo cores; giá trị thập phân chỉ có ý nghĩa với hậu tố `C`. |

Ví dụ trong POM:

~~~xml
<configuration>
    <forkCount>2</forkCount>
</configuration>
~~~

Cấu hình này **không có nghĩa** Maven luôn tạo chính xác hai JVM cho mọi build. Nếu không có test hoặc số lượng công việc không cần hai fork, số tiến trình quan sát được có thể ít hơn. `forkCount` là một **giới hạn đồng thời**.

### `forkCount=0` có phải nhanh nhất?

Không nhất thiết. Không fork tránh startup chi phí của JVM con, nhưng cũng bỏ ranh giới tiến trình giữa Maven và test, tăng nguy cơ test thay đổi system properties hoặc trạng thái JVM mà Maven/plugins khác đang sử dụng. Chạy build đa module song song với `-T` và không fork có thể gây race conditions; tài liệu Surefire cảnh báo không kết hợp kiểu chạy này một cách tùy tiện.

**`argLine` chỉ có hiệu lực khi test được fork.** Khi `forkCount=0`, các JVM flags trong `argLine` **không được áp vào JVM Maven đã chạy từ trước**. Muốn cấu hình chính JVM Maven, dùng `MAVEN_OPTS`, `.mvn/jvm.config` hoặc công cụ khởi chạy theo mục đích thích hợp, không chờ Surefire thay đổi ngược dòng.

### `forkCount=1C` và hiệu ứng CPU

Giả sử môi trường có bốn CPU cores theo cách Maven/Surefire nhận diện, `forkCount=1C` có thể cho phép tối đa bốn test JVM đồng thời. Nhưng:

- Số cores nhìn thấy trong container có thể không phản ánh quota CPU thực.
- Mỗi fork có heap, native memory, metaspace và thread riêng.
- Test dùng DB/HTTP service vẫn có thể nghẽn ở tài nguyên chung.
- Khi build reactor song song, tổng số JVM có thể tăng thêm theo số module cùng chạy.

Đừng chọn `2C` hay `4C` chỉ vì có nhiều cores. Đo thời gian, RAM và độ ổn định của CI rồi điều chỉnh.

## 4. Tham số `reuseForks`

`reuseForks` quyết định **vòng đời các forked JVM** khi có nhiều test classes.

### `reuseForks=true`

Surefire có thể duy trì tối đa `forkCount` JVM và **tái sử dụng** chúng để chạy các test classes tiếp theo. Ví dụ:

~~~text
forkCount=1, reuseForks=true

Maven JVM
  └── Test JVM PID=4101
        ├── AlphaTest
        ├── BetaTest
        └── GammaTest
  -> forked JVM kết thúc khi đợt test hoàn thành
~~~

PID `4101` là **ví dụ**, không phải đầu ra cố định.

Ưu điểm:

- Ít tạo JVM mới, giảm thời gian startup.
- Có thể tận dụng khởi tạo classloader/framework/context trong cùng JVM.
- Thích hợp khi test classes sạch trạng thái và không phụ thuộc thứ tự.

Nhược điểm:

- `static` fields, singleton, JVM system properties và thread nền có thể tồn tại giữa các test classes trong cùng fork.
- Test lỗi có thể làm bẩn JVM dùng cho các lớp test đến sau.
- Không đảm bảo một test được chạy trong JVM “mới tinh” khi đến lượt nó.

### `reuseForks=false`

Surefire tạo **JVM mới cho mỗi test class**, rồi kết thúc fork sau khi class đó chạy xong.

~~~text
forkCount=1, reuseForks=false

Maven JVM
   ├── Test JVM PID=5101 -> AlphaTest -> kết thúc
   ├── Test JVM PID=5102 -> BetaTest  -> kết thúc
   └── Test JVM PID=5103 -> GammaTest -> kết thúc
~~~

Đây là mức cô lập **theo test class**. Trong một class có nhiều `@Test`, các phương thức đó vẫn chạy **trong cùng JVM** của class; không có quy tắc một fork mới trên mỗi method.

Ưu điểm:

- Hạn chế rò rỉ static state giữa test classes.
- Mỗi class bắt đầu với heap/system properties mới ở cấp JVM.
- Hữu ích khi hệ thống cũ có test stateful hoặc third-party libraries khó reset.

Nhược điểm:

- JVM startup lặp lại cho từng test class; có thể chậm đáng kể.
- Tốn CPU và memory churn, nhất là số classes lớn.
- **Không khắc phục** lỗi chia sẻ file/DB/cổng ngoài JVM.
- Không đảm bảo phương thức trong một class độc lập với nhau.

### Bảng lựa chọn cơ bản

| `forkCount` | `reuseForks` | Hành vi | Tốc độ / cô lập |
| --- | --- | --- | --- |
| `0` | Không có fork để tái sử dụng | Test trong JVM Maven. | Ít khởi tạo process, cô lập tiến trình thấp. |
| `1` | `true` | Một JVM tái sử dụng giữa các test classes trong module. | Thường cân bằng giữa tốc độ và cô lập. |
| `1` | `false` | JVM mới cho mỗi test class, tuần tự. | Cô lập class tốt hơn nhưng thường chậm nhất. |
| `2` | `true` | Tối đa hai JVM, mỗi JVM chạy nhiều classes. | Có parallelism giữa forks, static có thể sống giữa các classes cùng fork. |
| `2` | `false` | Tối đa hai JVM đồng thời, mỗi JVM dành cho một test class. | Tăng cô lập và mức song song, chi phí startup cao. |

**Mặc định Surefire 3.5.4:** `forkCount=1` và `reuseForks=true`. Hãy kiểm tra version thực của project, không dựa vĩnh viễn vào defaults của một phiên bản plugin khác.

## 5. Những gì fork cách ly được và không cách ly được

Đặt hai test classes vào **hai JVM khác nhau** sẽ cô lập những yếu tố như:

- Biến `static` được nạp trong JVM của từng fork.
- System properties được thay đổi trong một JVM bằng `System.setProperty`.
- JVM heap và các object singleton nằm trong tiến trình.
- Classloaders và những class initializers chạy trong JVM đó.
- GC, heap pressure và một phần cấu hình JVM process.
- Process-local native state.

Nhưng **không tự cô lập**:

- Database schema và các bản ghi.
- File trên filesystem mà nhiều JVM cùng truy cập.
- Cổng mạng TCP cố định.
- Redis, Kafka, service HTTP, external queues.
- Environment variables đã được copy từ parent mà các fork cùng sử dụng.
- Shared directories, logs, report paths hoặc các singleton phía server.
- Các test methods **bên trong cùng một test class**.

Ví dụ hai classes dùng cùng database:

~~~text
AlphaTest (JVM #1) -> TRUNCATE TABLE accounts
BetaTest  (JVM #2) -> SELECT FROM accounts
~~~

Dù JVM riêng biệt, test vẫn có thể flake do dùng chung DB. Giải pháp là test data isolation, transaction rollback, unique schema/database, Testcontainers hoặc service sandbox, chứ không chỉ đổi `reuseForks`.

### Biến static và phạm vi classloader

`static` thuộc **class được nạp bởi một classloader**. Trong ví dụ JUnit/Surefire thông dụng, các test classes cùng fork có thể thấy cùng static state của helper class. Tuy nhiên một runner/provider đặc biệt có thể dùng classloader isolation khác. Do đó khi so sánh trạng thái static qua classes, nên **quan sát PID lẫn counter**, thay vì coi mọi tình huống classloader đều hoạt động y hệt.

**Không dùng kỳ vọng “biến static luôn trở về 0 trước mỗi `@Test`”.** JUnit Jupiter mặc định tạo test instance mới theo method, nhưng không tự reset class static fields.

## 6. `argLine`, `systemPropertyVariables` và cấu hình JVM test

### `argLine`

`argLine` chuyển **JVM options** cho forked test process. Ví dụ:

~~~xml
<configuration>
    <forkCount>1</forkCount>
    <reuseForks>true</reuseForks>
    <argLine>-Xmx256m -Ddemo.origin=argLine</argLine>
</configuration>
~~~

Trong test:

~~~java
String origin = System.getProperty("demo.origin", "<none>");
~~~

Khi có fork, giá trị có thể là `argLine`. Khi `forkCount=0`, `argLine` **không khởi động lại Maven JVM** để đặt property/heap, nên không dự đoán giá trị đó sẽ tự xuất hiện.

Những JVM flags thường thấy:

| Tùy chọn | Mục đích | Lưu ý |
| --- | --- | --- |
| `-Xmx256m` | Giới hạn Java heap của mỗi fork. | Không giới hạn tổng RSS/native memory của tiến trình. |
| `-Ddemo.mode=test` | Set JVM system property. | Tránh truyền secret theo cách này. |
| `--add-opens=...` | Mở package/module cho reflective access khi thật sự cần. | Dựa vào tài liệu library và JDK; không mở tràn lan. |
| `-ea` | Bật Java assertions. | JUnit assertions độc lập với Java `assert` keyword. |

Nếu có `forkCount=4` và mỗi JVM dùng `-Xmx1g`, tổng heap cap của các fork có thể lên tới khoảng 4 GiB **chưa tính Maven JVM** và native memory. Đừng đặt `-Xmx` chỉ theo RAM của một fork.

### `systemPropertyVariables`

Khi cần truyền property vào test process mà không yêu cầu JVM flag tùy ý, Surefire hỗ trợ:

~~~xml
<configuration>
    <systemPropertyVariables>
        <demo.mode>unit</demo.mode>
        <feature.flag>true</feature.flag>
    </systemPropertyVariables>
</configuration>
~~~

Trong Java:

~~~java
String mode = System.getProperty("demo.mode");
~~~

Properties trong XML có thể tham chiếu Maven expressions, nhưng không phải mọi kiểu dữ liệu/đối tượng đều được chuyển thành chuỗi như bạn mong đợi. Đối với dữ liệu phức tạp, đọc tài liệu goal và xác minh giá trị thực.

**Đừng nhầm ba tầng:**

1. `-Dtest.forkCount=2` là **Maven user property**, nếu POM tham chiếu nó để cấu hình `forkCount`.
2. `<systemPropertyVariables>` truyền **JVM system properties** vào bối cảnh chạy test.
3. `System.getProperty(...)` là **Java API** đọc property trong JVM test đang thực thi.

Một option truyền vào Maven CLI không có nghĩa mọi goal sẽ dùng nó: nó phải được tham chiếu hoặc là user property hợp lệ của parameter/plugin.

### Placeholder `${surefire.forkNumber}`

Surefire hỗ trợ placeholder `${surefire.forkNumber}` để gán số fork cho các giá trị như `argLine`, system properties hoặc environment variables theo phiên bản hỗ trợ.

Ví dụ:

~~~xml
<argLine>-Xmx256m -Ddemo.forkNumber=${surefire.forkNumber}</argLine>
~~~

Với `forkCount=2`, giá trị thường được thay bằng các số nhận diện fork, chẳng hạn `1` hoặc `2`. **Không coi forkNumber là PID**. Nó là chỉ số do Surefire gán để phục vụ việc phân vùng tài nguyên; PID do OS quyết định.

Trong reactor có `mvn -T ...`, phạm vi fork numbers có thể tính theo đồng thời của module executions và không đơn giản chỉ là 1 đến `forkCount`. Đừng hard-code port/tên file theo kỳ vọng một thứ tự cố định nếu còn có các module chạy đồng thời.

### Late property replacement với `@{argLine}`

Khi kết hợp Surefire với plugin thay đổi property `argLine` trong quá trình build, chẳng hạn JaCoCo Maven Plugin `prepare-agent`, tài liệu Surefire mô tả **late property replacement** bằng `@{argLine}`:

~~~xml
<argLine>@{argLine} -Xmx512m</argLine>
~~~

Điều này cho phép đọc property `argLine` **tại lúc goal Surefire được thực thi**, thay vì quá sớm khi Maven model được nội suy. Chỉ sử dụng khi cấu hình plugin thực sự cần; nên khởi tạo property rỗng hoặc theo tài liệu plugin để tránh truyền placeholder chưa được thay thế vào Java launcher.

**Không thêm snippet này vào POM runnable trong bài**: ví dụ chính không dùng JaCoCo và có `argLine` tường minh phục vụ quan sát fork.

## 7. Ví dụ Maven + JUnit 5 + Java 17 hoàn chỉnh

Ta tạo một module Maven nhỏ có:

- Một lớp Java ứng dụng để test kết quả.
- Một helper test lưu bộ đếm `static` và in PID.
- Hai lớp test độc lập `AlphaTest` và `BetaTest`.
- Surefire Plugin 3.5.4 và JUnit Jupiter 5.11.4.
- Cấu hình fork điều khiển bằng hai Maven properties để thay đổi chế độ **mà không sửa POM**.

### 7.1. Cây thư mục

~~~text
surefire-fork-demo/
├── pom.xml
└── src/
    ├── main/
    │   └── java/
    │       └── demo/
    │           └── Calculator.java
    └── test/
        ├── java/
        │   └── demo/
        │       ├── StateProbe.java
        │       ├── AlphaTest.java
        │       └── BetaTest.java
        └── resources/
            └── junit-platform.properties
~~~

File `junit-platform.properties` sẽ tắt thread parallelism của JUnit để chúng ta tập trung vào cách Surefire fork JVM. Dù vậy, **thứ tự test classes không được dựa vào như một giả định**.

### 7.2. POM đầy đủ

Tạo `pom.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>demo</groupId>
    <artifactId>surefire-fork-demo</artifactId>
    <version>1.0-SNAPSHOT</version>
    <packaging>jar</packaging>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <test.forkCount>1</test.forkCount>
        <test.reuseForks>true</test.reuseForks>
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
                <version>3.5.4</version>
                <configuration>
                    <forkCount>${test.forkCount}</forkCount>
                    <reuseForks>${test.reuseForks}</reuseForks>
                    <argLine>-Xmx256m -Ddemo.origin=argLine -Ddemo.forkNumber=${surefire.forkNumber}</argLine>
                    <systemPropertyVariables>
                        <demo.mode>unit</demo.mode>
                    </systemPropertyVariables>
                    <failIfNoTests>true</failIfNoTests>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Giải thích:

- `<maven.compiler.release>17</maven.compiler.release>` yêu cầu Compiler Plugin biên dịch tương thích Java 17.
- `junit-jupiter` có `scope=test`: Jupiter API và engine được tải vào test classpath.
- Surefire 3.5.4 có thể thực thi JUnit Jupiter tests qua JUnit Platform provider.
- `<forkCount>${test.forkCount}</forkCount>` và `<reuseForks>${test.reuseForks}</reuseForks>` lấy giá trị từ Maven properties. CLI có thể override `test.forkCount`/`test.reuseForks` của POM mẫu.
- `argLine` giới hạn heap mỗi fork và đặt system properties để quan sát việc fork.
- `systemPropertyVariables` đặt `demo.mode=unit` cho bối cảnh test.
- `failIfNoTests=true` giúp build thất bại nếu Surefire không tìm thấy test nào. Mặc định của goal không nhất thiết giống lựa chọn này.

**Chú ý:** tên `test.forkCount` và `test.reuseForks` là **Maven properties riêng của POM ví dụ**, không phải tên bất biến của Surefire. Surefire còn có các user properties trực tiếp của goal như `forkCount` và `reuseForks`; dùng các property tự đặt giúp demo thể hiện rõ cách POM truyền giá trị.

### 7.3. Java class dùng làm đối tượng kiểm thử

Tạo `src/main/java/demo/Calculator.java`:

~~~java
package demo;

public final class Calculator {
    private Calculator() {
    }

    public static int add(int left, int right) {
        return left + right;
    }

    public static void main(String[] args) {
        System.out.println("2 + 4 = " + add(2, 4));
    }
}
~~~

Đây là Java 17 hợp lệ, không dùng thư viện ngoài JDK.

Sau build có thể chạy:

~~~bash
java -cp target/classes demo.Calculator
~~~

**Stdout chính xác:**

~~~text
2 + 4 = 6
~~~

### 7.4. Helper quan sát process và static state

Tạo `src/test/java/demo/StateProbe.java`:

~~~java
package demo;

import java.util.concurrent.atomic.AtomicInteger;

final class StateProbe {
    private static final AtomicInteger EVENTS = new AtomicInteger();

    private StateProbe() {
    }

    static void report(String label) {
        int count = EVENTS.incrementAndGet();
        long pid = ProcessHandle.current().pid();
        String forkNumber =
                System.getProperty("demo.forkNumber", "<none>");
        String origin =
                System.getProperty("demo.origin", "<none>");
        String mode =
                System.getProperty("demo.mode", "<none>");

        System.out.printf(
                "%s pid=%d event=%d fork=%s origin=%s mode=%s%n",
                label, pid, count, forkNumber, origin, mode);
    }
}
~~~

`ProcessHandle.current().pid()` hoạt động từ Java 9+, nên hợp lệ với Java 17. `AtomicInteger` giúp tăng bộ đếm an toàn nếu thread parallelism được bật về sau; tuy vậy nó **không biến mọi trạng thái bên ngoài thành thread-safe**.

`EVENTS` là biến static nằm trong JVM/classloader đã nạp `StateProbe`. Khi lớp test khác chạy trong cùng JVM và cùng loader, nó có thể thấy count tiếp tục tăng; khi dùng JVM mới, biến này bắt đầu lại từ đầu.

Chương trình **không đưa assertion vào giá trị chính xác của PID, event count hoặc fork number**. Những giá trị đó phụ thuộc môi trường và lịch phân phối test classes; đặt assertion cứng sẽ tạo test không ổn định.

### 7.5. Test class thứ nhất

Tạo `src/test/java/demo/AlphaTest.java`:

~~~java
package demo;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class AlphaTest {
    @Test
    void additionWorks() {
        StateProbe.report("AlphaTest.additionWorks");
        assertEquals(6, Calculator.add(2, 4));
        assertTrue(ProcessHandle.current().pid() > 0);
    }

    @Test
    void additionWithZeroWorks() {
        StateProbe.report("AlphaTest.additionWithZeroWorks");
        assertEquals(9, Calculator.add(9, 0));
    }
}
~~~

Các assertions kiểm tra **hành vi thực của ứng dụng**, không phụ thuộc thứ tự chạy hoặc count của helper.

### 7.6. Test class thứ hai

Tạo `src/test/java/demo/BetaTest.java`:

~~~java
package demo;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class BetaTest {
    @Test
    void negativeNumbersWork() {
        StateProbe.report("BetaTest.negativeNumbersWork");
        assertEquals(-4, Calculator.add(-2, -2));
        assertTrue(ProcessHandle.current().pid() > 0);
    }

    @Test
    void orderDoesNotChangeTheSum() {
        StateProbe.report("BetaTest.orderDoesNotChangeTheSum");
        assertEquals(Calculator.add(4, 2), Calculator.add(2, 4));
    }
}
~~~

Hai lớp có tên `*Test` nên phù hợp các quy tắc tìm test class thông dụng của Surefire. Tổng cộng có **4 test methods**.

### 7.7. Tắt JUnit thread parallelism trong bài

Tạo `src/test/resources/junit-platform.properties`:

~~~properties
junit.jupiter.execution.parallel.enabled=false
~~~

Đây là cấu hình của **JUnit Jupiter**, không phải `forkCount` của Surefire. Tắt parallelism ở tầng JUnit giúp tập trung quan sát JVM forks. **Không suy ra** tắt parallelism nội bộ sẽ khiến `forkCount=2` hết khả năng tạo hai JVM cho các test classes khác nhau.

### 7.8. Build và chạy mặc định

Trong thư mục chứa `pom.xml`:

~~~bash
mvn --version
java -version
mvn clean test
~~~

Nếu JDK, Maven và repositories phù hợp, Surefire chạy 4 test methods không lỗi. Ví dụ phần thống kê của plugin **về mặt ý nghĩa**:

~~~text
Tests run: 4, Failures: 0, Errors: 0, Skipped: 0
BUILD SUCCESS
~~~

Đây là **đoạn tóm tắt**, không phải toàn bộ stdout cố định vì log có thể chứa tên lớp, thời gian, PID, thứ tự test và đường dẫn.

Sau lệnh trên:

~~~bash
java -cp target/classes demo.Calculator
~~~

stdout chính xác của lệnh Java:

~~~text
2 + 4 = 6
~~~

## 8. Thí nghiệm 1 — một JVM được tái sử dụng

POM mặc định tương đương:

~~~xml
<forkCount>1</forkCount>
<reuseForks>true</reuseForks>
~~~

Có thể chạy tường minh:

~~~bash
mvn -Dtest.forkCount=1 -Dtest.reuseForks=true clean test
~~~

Với một Maven module, Surefire thông thường dùng một test JVM để chạy cả `AlphaTest` và `BetaTest`. Các dòng `StateProbe.report` có thể nhìn thấy:

~~~text
AlphaTest.additionWorks pid=4101 event=1 fork=1 origin=argLine mode=unit
BetaTest.negativeNumbersWork pid=4101 event=3 fork=1 origin=argLine mode=unit
~~~

**Đây là ví dụ định dạng**, không phải stdout phải khớp: PID và thứ tự methods/classes không cố định; event count gắn với thứ tự thực thi. Điều cần tìm là:

- **Cùng PID** trong hai test classes vì dùng lại forked JVM.
- `origin=argLine` chứng tỏ JVM forked nhận property trong `argLine`.
- `fork=1` phù hợp khi chỉ có một fork trong module thông thường.
- Bộ đếm static `EVENTS` có thể tăng qua nhiều test methods/classes trong cùng classloader.

Dù JUnit thường tạo instance mới cho mỗi method, `static` vẫn tồn tại cho đến khi classloader/JVM bị giải phóng. **Test independence phải đến từ thiết kế test**, không chỉ từ việc JUnit khởi tạo instance mới.

## 9. Thí nghiệm 2 — JVM mới cho mỗi test class

Chỉ đổi config bằng Maven user properties:

~~~bash
mvn -Dtest.forkCount=1 -Dtest.reuseForks=false clean test
~~~

Với hai test classes, Surefire tạo JVM riêng cho `AlphaTest` và `BetaTest` theo chính sách không tái sử dụng. Dòng log minh họa:

~~~text
AlphaTest.additionWorks pid=5101 event=1 fork=1 origin=argLine mode=unit
BetaTest.negativeNumbersWork pid=5102 event=1 fork=1 origin=argLine mode=unit
~~~

**Kỳ vọng trọng tâm:** hai classes có **PID khác nhau**. `event=1` là ví dụ khi đó là sự kiện đầu tiên của mỗi class trong fork mới; vì mỗi class có hai methods và thứ tự methods không cố định, không nên gắn một method cụ thể với event=1 trong assertion.

Điểm đáng nhớ:

- `forkCount=1` giới hạn mức đồng thời **một JVM một lúc**.
- `reuseForks=false` vẫn có thể tạo **nhiều JVM nối tiếp nhau**, mỗi class một JVM.
- Số lần khởi động process tăng theo số test classes, nên thời gian có thể tăng đáng kể.
- **Hai test methods trong cùng `AlphaTest` vẫn dùng chung JVM**. Nếu method 1 làm bẩn static hoặc system properties, method 2 vẫn có thể chịu ảnh hưởng.

Nếu bạn đang điều tra một bộ test bị lỗi ngẫu nhiên, chạy riêng từng class trong JVM mới có thể là phép thử chẩn đoán tốt; nhưng cấu hình đó **không sửa nguyên nhân gốc** của trạng thái dùng chung.

## 10. Thí nghiệm 3 — hai JVM có thể chạy đồng thời

Chạy:

~~~bash
mvn -Dtest.forkCount=2 -Dtest.reuseForks=true clean test
~~~

Surefire có thể tạo tối đa hai forked JVM; các lớp test được phân phát giữa những fork này.

Có thể nhìn thấy:

~~~text
AlphaTest.additionWorks pid=6101 event=1 fork=1 origin=argLine mode=unit
BetaTest.negativeNumbersWork pid=6102 event=1 fork=2 origin=argLine mode=unit
~~~

Đây chỉ là **ví dụ**, vì không có bảo đảm class nào gán cho fork nào, có đúng hai JVM được tạo trong mọi lần chạy, hay log xuất hiện theo thứ tự nào.

Khi dùng nhiều forks:

- Hai tiến trình có heap/static riêng.
- Chúng có thể chạy đồng thời, cần tránh đụng file/port/DB.
- Tổng memory của các fork tăng theo số JVM thực.
- `${surefire.forkNumber}` có ích để tạo **tên thư mục/file/DB schema riêng theo fork** trong các hệ thống hỗ trợ, nhưng không thay cho test cleanup.

Nếu nhiều test classes chỉ tốn vài mili-giây, tạo JVM mới và phân phối có thể tốn thời gian hơn lợi ích concurrency. Phải benchmark trên CI thật.

### Tùy chọn `forkCount=1C`

Có thể thử:

~~~bash
mvn -Dtest.forkCount=1C -Dtest.reuseForks=true test
~~~

`1C` tính theo số cores, không phải “một JVM duy nhất”. Cách tính số cores có thể chịu ảnh hưởng container/JDK. Đối với laptop hoặc CI runner giới hạn RAM, giá trị lớn có thể dẫn đến memory pressure. Không chọn giá trị theo một benchmark duy nhất không đại diện.

## 11. Thí nghiệm 4 — tắt fork để hiểu khác biệt

Chạy:

~~~bash
mvn -Dtest.forkCount=0 -Dtest.reuseForks=true clean test
~~~

Với `forkCount=0`, test không được chạy trong forked JVM con của Surefire mà thực thi trong JVM Maven. Vì vậy:

- `ProcessHandle.current().pid()` có thể trùng PID của Maven process.
- Các option `-Xmx256m`, `-Ddemo.origin=argLine` và `-Ddemo.forkNumber=...` trong `argLine` **không có tác dụng đặt giá trị cho Maven JVM đã khởi động**.
- `StateProbe` vẫn có static state trong classloader của bối cảnh test, nhưng ranh giới process với Maven biến mất.
- Nếu `origin` được in là `<none>`, đó là điều hợp lý cho môi trường chưa set property bên ngoài. Nếu Maven đã được chạy với một property cùng tên, giá trị có thể khác; không dùng một dòng log để khẳng định tuyệt đối.

**Không bắt buộc test phải thất bại trong mode này.** Bốn assertions về `Calculator` vẫn đúng và test có thể PASS; mục đích là quan sát môi trường, không cố tình làm hỏng chương trình.

### Khi nào không nên dùng `forkCount=0`?

- Khi test thay đổi system properties hoặc thread state có thể làm bẩn Maven JVM.
- Khi test dùng Java agent/JVM flags riêng qua `argLine`.
- Khi dự án cần giới hạn heap riêng cho test.
- Khi build có nhiều modules chạy song song bằng `-T`.
- Khi test có native library, app server hoặc instrumentation có thể ảnh hưởng lâu dài tới process.

Đặt `forkCount=0` không phải “tối ưu luôn tốt hơn”; hãy kiểm chứng trạng thái, tính ổn định và lợi ích về thời gian.

## 12. Cô lập theo class không có nghĩa cô lập theo method

Một hiểu nhầm thường gặp:

> “Tôi đã đặt `reuseForks=false`, nên mỗi `@Test` chạy trong JVM mới.”

Điều này **sai**. Chính sách này tạo fork mới **theo test class**. Các methods của một class vẫn có thể chia sẻ:

- Static fields của class và helper classes.
- JVM system properties mà một method vừa sửa.
- Temp files và database records.
- Threads, caches, singleton.
- Các resources được nạp bởi classloader của class.

Ví dụ **cố ý dễ bị lỗi**:

~~~java
class BadTest {
    private static int counter;

    @Test
    void first() {
        counter++;
        assertEquals(1, counter);
    }

    @Test
    void second() {
        counter++;
        assertEquals(1, counter);
    }
}
~~~

Đoạn trên là **minh họa một anti-pattern**, không phải file test trong demo. Hai methods cùng cộng biến static và đều kỳ vọng 1; dù tạo fork riêng cho `BadTest`, chúng vẫn chạy trong cùng JVM đó, nên một assertion có thể thất bại, phụ thuộc thứ tự.

Cách tốt hơn là dùng fixture có phạm vi rõ:

~~~java
class BetterTest {
    private int counter;

    @Test
    void first() {
        counter++;
        assertEquals(1, counter);
    }

    @Test
    void second() {
        counter++;
        assertEquals(1, counter);
    }
}
~~~

Với JUnit Jupiter lifecycle mặc định **`PER_METHOD`**, mỗi method có một test instance mới, nên instance field có thể bắt đầu lại từ 0. Nếu đổi sang `@TestInstance(PER_CLASS)`, quy tắc chia sẻ instance thay đổi; vì vậy cũng phải đọc cấu hình JUnit thật.

**Cách cô lập đúng:** chọn đúng fixture lifecycle, reset state, test data independence, cleanup trong `@AfterEach`/`@AfterAll`, không phụ thuộc vào test order. Forking chỉ là một tầng bảo vệ bổ sung.

## 13. System properties, môi trường và trạng thái có thể rò rỉ

### 13.1. System properties dùng chung trong một JVM

~~~java
System.setProperty("app.mode", "test-A");
~~~

Lời gọi trên thay đổi một property cấp JVM. Nếu hai test classes chạy trong cùng fork khi `reuseForks=true`, class chạy sau có thể thấy giá trị đã bị thay bởi class trước. Nếu mỗi class chạy JVM mới, giá trị sửa ở JVM cũ không được mang sang chỉ vì chúng có cùng POM.

Một pattern reset có kiểm soát:

~~~java
String oldValue = System.getProperty("app.mode");
try {
    System.setProperty("app.mode", "test-A");
    // Đoạn gọi logic cần kiểm thử
} finally {
    if (oldValue == null) {
        System.clearProperty("app.mode");
    } else {
        System.setProperty("app.mode", oldValue);
    }
}
~~~

Đây là **mảnh mã minh họa**, phải đặt trong một test method/fixture phù hợp. Nó giảm nguy cơ rò rỉ property giữa tests tuần tự, nhưng **không an toàn nếu các tests song song cùng sửa một key**. Khi parallelism được bật, cần test isolation mạnh hơn hoặc resource locks theo framework.

### 13.2. Environment variables khác system properties

- `System.getProperty("key")` đọc JVM system property.
- `System.getenv("KEY")` đọc environment variable của process.
- `-Dkey=value` trong Java launcher đặt system property.
- `<environmentVariables>` của Surefire có thể cấu hình environment cho forked process theo khả năng plugin version.

System properties có thể được sửa bằng Java API; environment variables thông thường không nên được coi là một map có thể sửa tùy ý từ Java code trong cùng process.

Nhiều forked JVM có thể **kế thừa cùng environment** ban đầu, nên không tự tạo các credential, cổng hoặc schema khác nhau nếu bạn không cấu hình.

### 13.3. Không dùng chung cổng/file giữa forks

Giả sử test mở server trên port `8080`:

~~~text
fork #1 -> bind localhost:8080  (thành công)
fork #2 -> bind localhost:8080  (BindException)
~~~

Đặt `forkCount=2` không giải quyết tranh chấp này. Các chiến lược tốt hơn:

- Bind vào cổng hệ điều hành tự cấp (`port 0`) nếu thư viện hỗ trợ, rồi lấy cổng thực.
- Cấp port range riêng cho fork theo cấu hình có kiểm soát.
- Dùng thư mục tạm riêng mỗi test class/fork, chẳng hạn JUnit `@TempDir`.
- Tạo schema/database hoặc resource namespace riêng cho mỗi fork.
- Đặt resource locks/serialization cho những tests không thể chạy đồng thời.
- Cleanup trong khối `finally` hoặc hook phù hợp.

Nếu dùng `${surefire.forkNumber}` để đặt tên output, nhớ các module khác trong build parallel cũng có thể ảnh hưởng phạm vi đánh số. Đừng xem fork number là ID toàn cục vĩnh viễn giữa các lần build.

## 14. Fork parallelism khác JUnit parallelism và Maven `-T`

Có **ba tầng song song** thường bị nhầm:

| Tầng | Ai điều khiển? | Song song ở đâu? |
| --- | --- | --- |
| **Maven reactor** | Maven CLI `-T 2`, `-T 1C` | Các module/project có thể build đồng thời. |
| **Surefire forks** | `forkCount` và `reuseForks` | Các test JVM processes trong một hoặc nhiều module. |
| **Test framework threads** | Cấu hình JUnit Jupiter/TestNG/JUnit 4 tương ứng | Nhiều test tasks/threads trong cùng JVM. |

Cùng một CI runner có thể vừa build hai modules bằng `mvn -T 2 test`, mỗi module cho phép hai forks, và mỗi fork lại có nhiều threads nếu bật JUnit parallelism. Tổng tài nguyên tiêu thụ có thể lớn hơn dự đoán chỉ từ một con số `forkCount`.

### JUnit Jupiter parallelism

Bài demo dùng:

~~~properties
junit.jupiter.execution.parallel.enabled=false
~~~

Để **không** bật song song ở JUnit thread layer. Với một dự án thật, JUnit Jupiter có các cấu hình concurrency và synchronization riêng. Đừng dùng mỗi tham số `<parallel>methods</parallel>` của Surefire rồi giả định nó tự điều khiển mọi kiểu JUnit 5 test giống JUnit 4.

Nếu bật JUnit parallelism:

- Các methods/classes có thể chạy đồng thời trong một JVM.
- Trạng thái `static`/system properties có thể bị truy cập từ nhiều threads.
- `reuseForks=false` không nhất thiết giải quyết race conditions giữa methods **trong cùng class**.
- Phải dùng test fixtures thread-safe, JUnit resource locks hoặc disable parallelism cho nhóm test không hỗ trợ.

### Ví dụ đánh giá tài nguyên

Giả sử:

~~~text
Maven -T 2: tối đa 2 modules đồng thời
Mỗi module forkCount=2: tối đa 2 JVM/module
Mỗi fork -Xmx256m
~~~

Trong kịch bản tải đầy, hệ thống có thể có **tối đa khoảng 4 test forks** cùng lúc ngoài các JVM/process khác. Heap cap cộng lại có thể lên tới 1 GiB, nhưng RSS thực có thể cao hơn vì metaspace, thread stacks, code cache và native allocations. Đây chỉ là phép tính minh họa cho **giới hạn tối đa**, không phải dự báo số JVM hoặc RAM thực tế mọi lúc.

**Kết luận vận hành:** thay đổi một tầng parallelism có thể khuếch đại tải ở tầng khác. Hãy đo số PID, RAM, CPU, thời gian và flake rate trên CI runner đang dùng.

## 15. Chọn cấu hình theo mục tiêu kiểm thử

### Trường hợp A — bộ unit tests thuần, không dùng tài nguyên ngoài

Khởi đầu hợp lý:

~~~xml
<forkCount>1</forkCount>
<reuseForks>true</reuseForks>
~~~

Đây là lựa chọn thường cân bằng giữa hiệu năng và ranh giới JVM. Nếu bộ test chạy nhanh, chưa chắc tăng forks sẽ nhanh hơn.

### Trường hợp B — test cũ bị rò rỉ static state giữa classes

Để khoanh vùng nguyên nhân:

~~~xml
<forkCount>1</forkCount>
<reuseForks>false</reuseForks>
~~~

Nếu lỗi biến mất, đây là bằng chứng đáng điều tra về **shared state giữa classes hoặc vấn đề lifecycle**. Nhưng không kết luận tất cả lỗi flake đều là static, và không dừng ở việc đổi setting nếu có thể sửa cleanup/fixture.

### Trường hợp C — nhiều test classes độc lập và CI có RAM

Có thể benchmark:

~~~xml
<forkCount>2</forkCount>
<reuseForks>true</reuseForks>
~~~

Quan sát tốc độ có cải thiện hay không. Nếu test dùng cùng DB/cổng, cần cô lập external resources trước khi bật nhiều forks.

### Trường hợp D — mỗi test class cần JVM sạch

~~~xml
<forkCount>2</forkCount>
<reuseForks>false</reuseForks>
~~~

Tối đa hai JVM đồng thời, từng class được gán vào process mới. Đây có thể hữu ích cho test có bootstrap nặng hoặc hệ thống native state đặc biệt, nhưng cũng **rất tốn thời gian** nếu mỗi class khởi động JVM/framework.

### Trường hợp E — môi trường hạn chế RAM

Có thể giảm `forkCount`, giảm `-Xmx` theo nhu cầu thực và tránh phối hợp nhiều mức parallelism. Đặt `forkCount=0` chỉ để tiết kiệm memory **không tự động an toàn**, nhất là nếu test có agent/system property đặc thù.

## 16. Khi nào chạy test trong Surefire, khi nào dùng Failsafe?

Surefire thường chạy **unit tests** ở lifecycle phase `test`. Maven Failsafe Plugin thường dành cho **integration tests**, với goals `integration-test` và `verify` trong một lifecycle phù hợp.

| Thành phần | Thường dùng | Report/output |
| --- | --- | --- |
| Maven Surefire Plugin | Unit tests, goal `surefire:test`, phase `test`. | `target/surefire-reports`. |
| Maven Failsafe Plugin | Integration tests, goals `failsafe:integration-test` và `failsafe:verify`. | `target/failsafe-reports`. |

Failsafe cũng có các tùy chọn liên quan fork và test process, nhưng **không coi cấu hình Surefire trong POM tự động áp dụng cho Failsafe**. Nếu integration tests cần database/container/network riêng, hãy cấu hình Failsafe, fixture setup/teardown và vòng đời test phù hợp.

**Không dùng `mvn integration-test` đơn lẻ như một quy trình integration test hoàn chỉnh** nếu Failsafe đã được bind để xác nhận kết quả tại `verify`. Thông thường nên chạy `mvn verify` để Failsafe có thể xử lý báo cáo và cleanup theo lifecycle.

## 17. Chẩn đoán lỗi thường gặp

| Triệu chứng | Nguyên nhân khả dĩ | Hướng điều tra |
| --- | --- | --- |
| Unit tests fail ngẫu nhiên khi chạy cả suite. | Chia sẻ static state, system properties, file/DB hoặc thứ tự test. | Chạy riêng class, quan sát PID/state, kiểm tra cleanup và parallelism. |
| Test pass khi `reuseForks=false` nhưng fail khi `true`. | State rò rỉ giữa test classes trong fork tái sử dụng. | Tìm `static`, singleton, threads, property mutation và test order dependency. |
| Hai test methods trong cùng class vẫn ảnh hưởng nhau. | `reuseForks=false` chỉ tách **classes**, không tách từng method. | Dùng JUnit fixture/per-method lifecycle, reset state. |
| `forkCount=2` nhưng chỉ thấy một PID. | Không đủ workload, cấu hình không áp dụng hoặc nhìn thiếu logs. | Kiểm tra effective POM, Surefire goal, số classes và báo cáo. |
| `forkCount=0` không thấy `-Ddemo.origin=argLine`. | `argLine` chỉ áp dụng trong forked JVM. | Kiểm tra JVM Maven options khác nếu cần. |
| `@{argLine}` hiện nguyên văn thành lỗi launcher. | Late replacement property chưa được thiết lập/không được plugin xử lý. | Xác minh plugin execution và khởi tạo property theo docs. |
| Test fork bị `OutOfMemoryError`. | Heap quá nhỏ, nhiều forks hoặc memory leak. | Kiểm tra `-Xmx` mỗi fork, số concurrent JVM và memory ngoài heap. |
| Fork kết thúc bất thường. | Test gọi `System.exit`, native crash, OOM kill hoặc runtime lỗi. | Xem Surefire dump files, crash logs, OS/container events. |
| Thông báo “The forked VM terminated without properly saying goodbye”. | Forked process chết hoặc mất liên lạc với Surefire. | Xem dump/report, exit code, process checker, agent/VM flags. |
| Fork treo sau khi tests chạy. | Thread non-daemon, shutdown hook, deadlock, thư viện native hoặc lỗi communication. | Thêm timeouts có chủ đích, thread dump và resource cleanup. |
| CI chậm hơn khi tăng `forkCount`. | Startup overhead, thiếu CPU/RAM, tranh chấp DB/network. | So thời gian/CPU/RAM với cấu hình ít forks. |
| Fail chỉ khi dùng `mvn -T`. | Nhiều modules cùng dùng file/port/DB, hoặc fork-less shared JVM state. | Kiểm tra reactor parallelism và tên resources theo module/fork. |
| JUnit tests không được tìm. | Thiếu engine, đặt tên file khác pattern, test classpath/provider không phù hợp. | Kiểm tra Surefire version, `*Test`, Jupiter engine và reports. |
| `-Dtest=AlphaTest` chạy được nhưng cả suite fail. | Các test classes có thể tương tác hoặc data cleanup chưa tốt. | Quan sát fork PID và isolated resources; không phụ thuộc test order. |
| Property trong test khác dự kiến. | `argLine`/`systemPropertyVariables`/CLI/environment trùng tên. | Xác định nguồn cấu hình, dùng log và output test. |

### Các file để điều tra

Sau khi chạy `mvn test`, xem:

~~~text
target/surefire-reports/
    demo.AlphaTest.txt
    demo.BetaTest.txt
    TEST-demo.AlphaTest.xml
    TEST-demo.BetaTest.xml
    [các file .dump, .dumpstream nếu phát sinh sự cố]
~~~

Danh sách trên mang tính **minh họa** về convention report file names. Một project/plugin version có thể ghi log stdout theo cách khác hoặc tạo thêm file. Khi fork chết, `*.dump` và `*.dumpstream` có thể giúp tìm thông tin; không đảm bảo sự cố nào cũng sinh đủ chúng.

Có thể dùng:

~~~bash
mvn -Dtest=AlphaTest test
mvn -Dtest=BetaTest test
mvn -e test
mvn -X test
~~~

`-e` cho stack trace, `-X` cho debug logs. **Không chia sẻ nguyên debug logs nếu chúng chứa credentials, nội bộ repository URLs hoặc dữ liệu nhạy cảm**.

### Khi fork bị treo

Surefire có các tham số giám sát forked process và thời gian chờ tùy version, chẳng hạn `forkedProcessTimeoutInSeconds`. Không chọn timeout quá thấp rồi kết luận test “chậm bất thường”: CI có thể chịu cold start, tải dependency, CPU throttling và GC pause. Bắt đầu bằng quan sát thread dump/log và thời gian chạy thực tế.

Nếu test tạo thread hoặc executor, nên đóng tài nguyên bằng `try-with-resources` khi API phù hợp, hoặc `shutdown()/awaitTermination()` trong fixture cleanup; đảm bảo timeout và interruption được xử lý. Chỉ kill JVM là biện pháp hạn chế tác động, không phải thiết kế test đúng.

## 18. Các hiểu nhầm quan trọng

### “Mỗi test method được fork thành một JVM mới”

Sai. `reuseForks=false` là JVM mới **cho mỗi test class**, không phải mỗi phương thức. Điều này giúp giảm state leak giữa classes, nhưng các methods trong class vẫn có thể chia sẻ static/system state.

### “`forkCount=2` nghĩa là luôn có chính xác hai JVM”

Sai. Đây là **mức đồng thời tối đa**. Số tiến trình thực tùy số test classes, lịch phân phối, reactor và thời điểm quan sát.

### “`reuseForks=true` có nghĩa tất cả tests share một JVM”

Chỉ đúng trong cấu hình có **một fork** cho module. Với `forkCount>1`, các test classes được phân vào nhiều JVM, và chỉ các classes cùng fork mới có thể chia sẻ process-local state.

### “Đặt `-Dfoo=bar` trên Maven CLI luôn giống `-Dfoo=bar` của test JVM”

Không. Maven user property và Java system property trong fork là các tầng khác nhau. Surefire có các cơ chế chuyển/ghi đè, nhưng hành vi cụ thể cần đọc cấu hình plugin, `argLine` và `systemPropertyVariables`.

### “Tắt fork sẽ làm test hoàn toàn cô lập khỏi build”

Ngược lại. `forkCount=0` chạy trong JVM Maven nên giảm một ranh giới cô lập. Nó có thể có ích cho một số project nhẹ, nhưng làm tăng khả năng tương tác giữa test và Maven runtime.

### “Có nhiều forks thì không còn race condition”

Sai. Forks vẫn chia sẻ database, network, filesystem và các services khác. Các tests có thể cần resource locking hoặc data isolation ngoài JVM.

### “Thêm forks chắc chắn làm build nhanh hơn”

Sai. JVM startup, classloading, Spring context/bootstrap, JIT và GC có chi phí. Nếu tests nhẹ hoặc runner thiếu tài nguyên, thêm forks có thể làm chậm build hoặc tăng flakiness.

## 19. Checklist lựa chọn cấu hình cho CI

Trước khi nâng mức parallelism hoặc đổi reuse:

- [ ] Đúng Maven/Surefire/JDK version và đúng module/POM.
- [ ] Đã biết test framework: JUnit Jupiter, JUnit 4, TestNG hay tổ hợp khác.
- [ ] `forkCount` được xác định theo core/RAM/quota thực của runner.
- [ ] `reuseForks` được chọn theo mức cô lập **test class**, không nhầm test method.
- [ ] `argLine` và `systemPropertyVariables` không xung đột với nhau hoặc với JaCoCo/agents.
- [ ] Các test không phụ thuộc thứ tự chạy; static state được reset/loại bỏ khi có thể.
- [ ] Không dùng chung file/port/DB schema vô tình giữa các forks hoặc modules.
- [ ] Có timeout và cleanup hợp lý cho threads, sockets, containers và databases.
- [ ] Đã thử baseline `forkCount=1,reuseForks=true` để so sánh hiệu năng.
- [ ] Đã chạy clean test suite nhiều lần trên CI-like environment để tìm flake rate.
- [ ] Đã kiểm tra Surefire reports và lỗi fork/process để phân biệt test assertion với hỏng JVM.
- [ ] Nếu dùng Maven reactor `-T`, đã tính lại mức đồng thời tổng thể.
- [ ] Không in secrets vào test output, system properties hoặc debug logs.

**Ưu tiên sửa test independence trước khi tăng chi phí isolation.** `reuseForks=false` có thể là công cụ chẩn đoán hoặc giải pháp vận hành tạm thời, nhưng làm rõ root cause thường giúp bộ test vừa nhanh vừa ổn định hơn.

## 20. Bài tập thực hành

### Bài A — Dự đoán PID và static state

Với hai classes `AlphaTest` và `BetaTest`:

1. `forkCount=1, reuseForks=true`: có bao nhiêu forked JVM đồng thời? Hai classes thường cùng PID hay khác PID?
2. `forkCount=1, reuseForks=false`: hai classes có thể cùng PID không theo cấu hình chuẩn? Vì sao JVM startup tăng?
3. `forkCount=2, reuseForks=true`: nếu hai classes chạy ở hai forks, có share `StateProbe.EVENTS` không?
4. `forkCount=0`: vì sao `argLine` của Surefire không tạo `-Xmx256m` cho JVM Maven?
5. `reuseForks=false`: hai methods trong `AlphaTest` có ở hai JVM riêng không?

**Đáp án:** (1) tối đa một forked JVM, thường cùng PID; (2) mỗi class JVM mới nên PID khác; (3) không, vì khác process; (4) Maven JVM đã khởi động, không được tạo bởi `argLine` của Surefire; (5) không, isolation theo class.

### Bài B — Chạy dự án Java 17

1. Tạo `pom.xml` và bốn class Java/test resources như mục 7.
2. Chạy `mvn clean test`; xác nhận có 4 tests PASS.
3. Chạy `java -cp target/classes demo.Calculator`; xác nhận `2 + 4 = 6`.
4. Chạy `mvn -Dtest.forkCount=1 -Dtest.reuseForks=true clean test`; ghi PID và count giữa classes.
5. Chạy `mvn -Dtest.forkCount=1 -Dtest.reuseForks=false clean test`; xác minh PID khác giữa classes.
6. Chạy `mvn -Dtest.forkCount=2 -Dtest.reuseForks=true clean test`; ghi lại những fork thực sự được tạo, không đòi luôn đủ hai.
7. Chạy `mvn -Dtest.forkCount=0 -Dtest.reuseForks=true clean test`; quan sát `origin` và `fork`.
8. Đọc `target/surefire-reports` để xem summary, không suy luận từ thứ tự các dòng output.
9. Giải thích tại sao có thể dùng `-Dtest.forkCount` mà không sửa cấu hình POM.
10. Nêu một ví dụ database/file có thể bị tranh chấp dù mỗi class chạy JVM khác.

### Bài C — Sửa một test phụ thuộc trạng thái

Bạn có hai test methods cùng sửa biến static `counter` và mỗi method kỳ vọng counter bắt đầu bằng 0. Hãy:

1. Giải thích tại sao `reuseForks=false` không giúp nếu cả hai methods cùng class.
2. Chuyển counter thành instance field với JUnit Jupiter `PER_METHOD` hoặc reset trong `@BeforeEach` nếu phù hợp.
3. Thử chạy suite nhiều lần với `forkCount=1` rồi `2` để xác minh test independence.
4. Nếu test dùng file tạm, dùng JUnit `@TempDir` để tránh path cố định dùng chung.
5. Nếu test dùng port, đề xuất cách lấy port động thay vì hard-code.
6. Chỉ bật JUnit method-level parallelism khi fixture đã thread-safe.

### Câu hỏi tự đánh giá

- Forked JVM và thread trong cùng JVM khác nhau thế nào?
- `forkCount=0` có cô lập test khỏi Maven JVM không?
- `reuseForks=false` tạo process mới cho class hay method?
- `forkCount=2` có buộc Maven chạy đúng hai process không?
- Vì sao static state có thể rò rỉ khi `reuseForks=true`?
- `@TestInstance(PER_METHOD)` có tự reset static state không?
- `argLine` có hiệu lực khi tắt fork không?
- `${surefire.forkNumber}` có phải PID không?
- Vì sao `-T 2` có thể nhân mức song song của Surefire ở reactor?
- Nếu test thay đổi file/database, có đủ để bật nhiều forks không?
- Vì sao một test suite PASS không tự chứng minh nó ổn định ở CI?

## 21. Kết luận

**Surefire forking là công cụ điều khiển ranh giới tiến trình cho việc chạy test.**

- `forkCount` đặt **giới hạn số forked JVM chạy đồng thời**.
- `reuseForks=true` tái sử dụng JVM giữa test classes để giảm chi phí.
- `reuseForks=false` tạo JVM mới **cho mỗi test class** để tăng cô lập.
- `forkCount=0` tắt fork, đưa test vào JVM Maven.
- `argLine` áp dụng JVM options cho **forked processes**, không thể thay đổi ngược lại JVM Maven.
- `systemPropertyVariables` cung cấp properties trong ngữ cảnh test.
- Forks cô lập heap/static/system properties theo process nhưng **không cô lập database/file/port**.

Với Maven + JUnit 5, hãy thiết kế tests độc lập trước, sau đó benchmark lựa chọn fork theo runner thật. Khi điều tra flakiness, ghi nhận PID, fork number, static state, JUnit parallelism và tài nguyên ngoài JVM. **Một cấu hình nhanh nhưng gây race condition không phải là cấu hình tốt.**

## Tài liệu chính thức

- Maven Surefire Plugin — Fork Options and Parallel Test Execution: https://maven.apache.org/surefire-archives/surefire-3.5.4/maven-surefire-plugin/examples/fork-options-and-parallel-execution.html
- Maven Surefire Plugin 3.5.4 — `surefire:test` parameters: https://maven.apache.org/surefire-archives/surefire-3.5.4/maven-surefire-plugin/test-mojo.html
- Maven Surefire Plugin — Using JUnit 5 Platform: https://maven.apache.org/surefire-archives/surefire-3.5.4/maven-surefire-plugin/examples/junit-platform.html
- Maven Surefire Plugin — Frequently Asked Questions: https://maven.apache.org/surefire/maven-surefire-plugin/faq.html
- Maven Surefire Plugin — Class Loading and Forking: https://maven.apache.org/surefire/maven-surefire-plugin/examples/class-loading.html
- Maven Failsafe Plugin — Introduction: https://maven.apache.org/surefire/maven-failsafe-plugin/
- JUnit 5 User Guide — Parallel Execution: https://junit.org/junit5/docs/current/user-guide/#writing-tests-parallel-execution
