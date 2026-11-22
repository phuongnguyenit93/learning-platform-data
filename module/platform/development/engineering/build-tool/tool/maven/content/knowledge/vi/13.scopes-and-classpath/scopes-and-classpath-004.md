# Maven dependency scope runtime: thư viện chỉ cần khi chạy và cách dựng runtime classpath

## 1. Tình huống: biên dịch thành công nhưng chạy chương trình lại thiếu thư viện

Một ứng dụng Java có thể **biên dịch hoàn toàn bình thường** với `mvn compile`, các unit test cũng vượt qua `mvn test`, nhưng khi chạy file JAR bằng lệnh `java` trên một máy khác lại gặp:

~~~text
java.sql.SQLException: No suitable driver found for jdbc:h2:mem:scope_demo
~~~

Hoặc, trong một ứng dụng khác:

~~~text
java.lang.NoClassDefFoundError: some/library/Implementation
~~~

Hai lỗi này có nhiều nguyên nhân; một nguyên nhân phổ biến là **runtime classpath không có thư viện cần thiết**. Maven đã tải dependency khi build nhưng lệnh chạy Java bên ngoài Maven không tự động lấy mọi JAR trong `~/.m2/repository`. Cũng có thể một thư viện được khai báo sai `scope` nên bị loại khỏi classpath ở giai đoạn cần dùng.

Trong Maven, dependency có `<scope>runtime</scope>` là thư viện **không cần đưa vào compile classpath của mã sản phẩm**, nhưng **phải có khi ứng dụng chạy** và **cũng xuất hiện trong test classpath**. Cách dùng điển hình: JDBC driver, logging backend/implementation được phát hiện động hoặc provider được tải qua `ServiceLoader`.

Bài học này giúp bạn:

1. Hiểu compile, runtime và test classpath là những tập khác nhau.
2. Chọn đúng giữa `compile`, `runtime`, `provided` và `test`, không dựa vào việc thư viện “chỉ được gọi trong `main`”.
3. Hiểu runtime scope và dependency transitiveness, các ngoại lệ của `provided`/`test`.
4. Tạo dự án **Maven 3.9.x + Java 17 + JDBC/H2 + JUnit 5**, dùng H2 đúng `runtime` mà mã chính không import lớp nào từ H2.
5. Build, test, chạy với/không với runtime JAR; phân biệt lỗi ở Maven, lỗi classpath và lỗi JDBC.
6. Dùng `dependency:tree` và `dependency:copy-dependencies` để kiểm tra và dựng một classpath khi triển khai.
7. Biết ranh giới của JAR thông thường, fat JAR, Maven test runtime và runtime do container cung cấp.

Phiên bản cụ thể trong ví dụ đã được ghim để bài thực hành có thể tái hiện. Đối với sản phẩm thật, cần chọn phiên bản thư viện được bảo trì và kiểm tra chính sách bảo mật phù hợp; một phiên bản minh họa không phải cam kết tương thích cho mọi hệ thống lâu dài.

## 2. Khái niệm scope: dependency đi vào classpath ở thời điểm nào?

### 2.1. Classpath là gì?

Classpath là tập **thư mục chứa class** và **file JAR** mà Java compiler hoặc JVM/class loader được phép tìm kiếm. Trong Maven, classpath có thể khác nhau giữa ba giai đoạn:

~~~text
Mã chính: src/main/java
      |
      | Maven compile classpath
      v
javac -> target/classes
      |
      +------------------+
      |                  |
      v                  v
Maven test classpath   Java runtime classpath
(bao gồm test deps)    (chạy ứng dụng thực tế)
      |                  |
      v                  v
src/test/java       java -cp ... Main
      |                  |
      v                  v
target/test-classes   thư viện runtime phải tồn tại
~~~

Đối với một project Java thông thường:

- **Compile classpath** dùng khi biên dịch `src/main/java`; thường gồm dependency scope `compile` và `provided`, nhưng **không gồm dependency thuần `runtime`**.
- **Runtime classpath** dùng khi chạy ứng dụng; thường gồm class sản phẩm và dependency `compile` + `runtime`, nhưng không gồm `provided` và `test`.
- **Test classpath** dùng cho biên dịch/chạy test; thường gồm mã sản phẩm, mã test, dependency `compile`, `runtime`, `provided` và `test`.

Sơ đồ này nói về **dependency classpaths theo scope chuẩn**, không tuyên bố Maven luôn tự khởi động ứng dụng sau khi build. Plugin có thể tạo process/fork hoặc thiết lập classpath riêng; khi dùng plugin, phải kiểm tra mục đích và cấu hình của plugin đó.

### 2.2. Bảng scope quan trọng

| Scope | Có ở compile classpath của mã chính? | Có ở runtime classpath? | Có ở test classpath? | Tình huống |
| --- | --- | --- | --- | --- |
| `compile` | Có | Có | Có | API/lớp bên thứ ba mà mã sản phẩm trực tiếp import và dùng |
| `runtime` | **Không** | **Có** | **Có** | JDBC driver, runtime provider/implementation |
| `provided` | Có | **Không** | Có | API được servlet container hoặc môi trường chạy cấp |
| `test` | Không | Không | Có | JUnit, Mockito, thư viện chỉ dùng trong test |

`compile` là scope mặc định khi một dependency **không khai báo `<scope>`**. Bảng nói về dependency trực tiếp và các classpath Maven tính sau khi giải quyết dependency; đối với dependency bắc cầu còn có bảng scope propagation ở phần sau.

Hai scope khác cần biết nhưng **không phải cách chọn runtime driver thông thường**:

- `system`: phụ thuộc JAR ở đường dẫn local `systemPath`, khó tái tạo và không được Maven tải từ repository; thường **không được khuyến nghị**. Với doanh nghiệp, đưa thư viện vào repository được quản lý thay vì phụ thuộc đường dẫn riêng của laptop.
- `import`: chỉ có ý nghĩa với dependency loại `pom` bên trong `dependencyManagement` để nhập BOM; không phải một dependency classpath thực tế.

### 2.3. Cách viết runtime trong pom.xml

~~~xml
<dependencies>
    <dependency>
        <groupId>com.h2database</groupId>
        <artifactId>h2</artifactId>
        <version>2.3.232</version>
        <scope>runtime</scope>
    </dependency>
</dependencies>
~~~

Ở đây:

- `com.h2database` là Maven `groupId`.
- `h2` là `artifactId`.
- `2.3.232` là phiên bản thư viện cho bài thực hành.
- `runtime` yêu cầu Maven đưa artifact này vào runtime/test classpaths, nhưng không đưa nó vào compile classpath của mã chính.

**Không nên suy luận rằng `runtime` nghĩa là Maven chỉ tải dependency sau khi chạy chương trình.** Maven có thể giải quyết/tải dependency từ repository trong các goal build hoặc test. `scope` quy định **tập classpath và phạm vi truyền dependency**, không phải lịch tải chính xác theo đồng hồ.

## 3. Vì sao có thư viện “chỉ cần khi chạy”?

Một thư viện chỉ phù hợp `runtime` khi mã ứng dụng có thể **biên dịch dựa trên API đã có**, còn một implementation cụ thể được chọn/tải khi chạy.

Ví dụ tiêu biểu là JDBC:

~~~text
App.java
  |
  | import java.sql.Connection
  | import java.sql.DriverManager
  | import java.sql.ResultSet
  v
JDBC API từ JDK 17
  |
  | runtime: DriverManager tìm một JDBC driver
  v
H2 JDBC driver JAR
  |
  v
jdbc:h2:mem:scope_demo
~~~

Mã Java nhập `java.sql.Connection` và `java.sql.DriverManager` từ **JDK**, không cần import `org.h2.Driver`. Khi JVM thực thi, JDBC driver từ H2 JAR đăng ký/được phát hiện qua cơ chế JDBC hiện đại và xử lý URL `jdbc:h2:...`.

Đó là ví dụ đúng của **API ở compile time – implementation ở runtime**:

- API Java SQL: do JDK cung cấp, không cần dependency ngoài.
- Implementation H2: do Maven dependency `runtime` cung cấp.
- Test: cần driver thực để truy vấn nên runtime dependency cũng có mặt ở test classpath.

Một tình huống tương tự với logging: ứng dụng trực tiếp gọi **logging API** thì API nên ở `compile`; implementation/backend được lựa chọn khi chạy có thể ở `runtime` nếu không có import trực tiếp tới lớp implementation. Không phải mọi “logging library” đều thích hợp `runtime`: phải phân biệt phần API với backend.

## 4. Quy tắc quyết định scope: nhìn vào kiểu tham chiếu của mã nguồn

Sử dụng ba câu hỏi:

1. **Mã trong `src/main/java` có trực tiếp import hoặc dùng type của thư viện lúc biên dịch không?** Nếu có, nó thường cần `compile` hoặc `provided`; riêng `runtime` không đủ.
2. **Ứng dụng lúc chạy có cần implementation/provider từ thư viện đó không?** Nếu có, nó thường cần `compile` hoặc `runtime` (trừ khi runtime/container cung cấp bên ngoài và bạn cố ý dùng `provided`).
3. **Thư viện chỉ phục vụ lớp ở `src/test/java`?** Khi đó dùng `test`.

Ví dụ:

| Trường hợp | Scope thường phù hợp | Vì sao |
| --- | --- | --- |
| Mã sản phẩm import `org.apache.commons.lang3.StringUtils` | `compile` | Compiler phải thấy `StringUtils`; runtime cũng cần |
| Mã dùng `java.sql` của JDK, JDBC driver được phát hiện lúc chạy | `runtime` cho driver | Compiler không cần lớp cụ thể của driver |
| Test dùng `org.junit.jupiter.api.Test` | `test` | Không cần JUnit trong ứng dụng phát hành |
| WAR compile theo Servlet API nhưng container cấp Servlet API | `provided` | Compiler/test cần API, container sẽ cung cấp lúc chạy |
| Plugin build riêng như Maven Compiler Plugin | `build/plugins`, không phải project runtime dependency | Plugin chạy trong quá trình Maven build |
| Chỉ có một API bên thứ ba mà ứng dụng trực tiếp import | `compile` cho API | Không thể để API ở `runtime` rồi kỳ vọng `javac` tìm được |

Cần phân biệt `dependency` thuộc ứng dụng và `plugin dependency` thuộc plugin Maven. Khai báo một plugin ở `build/plugins` không tự đưa các JAR của plugin vào runtime classpath của ứng dụng.

### Phản ví dụ: runtime nhưng lại import implementation

Nếu đã đặt H2 `runtime` mà viết trong `src/main/java`:

~~~java
import org.h2.Driver;
~~~

và trực tiếp dùng type `Driver` trong mã, compiler thông thường không có lớp đó trong compile classpath. Lỗi như `package org.h2 does not exist` là điều có thể xảy ra.

Cách sửa **không phải luôn đổi `runtime` thành `compile`**. Hãy xem việc import implementation có cần thiết không; với JDBC chuẩn, bạn chỉ cần Java SQL API. Nếu thực sự phải dùng API đặc thù của driver ngay trong mã sản phẩm, scope `compile` mới có cơ sở. Cần đưa quyết định vào thiết kế thay vì sửa scope chỉ để làm lỗi biến mất.

## 5. Ví dụ độc lập: Maven + Java 17 + H2 runtime + JUnit test

Ví dụ nhỏ sau cố ý dùng API JDBC từ JDK để có thể compile **không cần H2 trên compile classpath**, nhưng phải có driver ở runtime.

### 5.1. Cây dự án

~~~text
runtime-scope-demo/
├── pom.xml
└── src/
    ├── main/java/vn/example/runtime/JdbcDemo.java
    └── test/java/vn/example/runtime/JdbcDemoTest.java
~~~

JDK: **17+**. Maven: **3.9.x**. H2: **2.3.232**. JUnit Jupiter: **5.11.4**. Để tải dependency/plugin lần đầu, Maven phải truy cập repository được cấu hình; khi hệ thống doanh nghiệp dùng mirror/proxy, dùng `settings.xml` hợp lệ do tổ chức cấp.

### 5.2. File pom.xml hoàn chỉnh

Tạo `runtime-scope-demo/pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>vn.example</groupId>
    <artifactId>runtime-scope-demo</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <!-- H2 chỉ cần cho việc thực thi JDBC, không import org.h2 trong mã chính -->
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <version>2.3.232</version>
            <scope>runtime</scope>
        </dependency>

        <!-- JUnit chỉ dùng khi biên dịch và chạy unit test -->
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
            </plugin>

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-dependency-plugin</artifactId>
                <version>3.8.1</version>
                <configuration>
                    <includeScope>runtime</includeScope>
                    <outputDirectory>${project.build.directory}/runtime-libs</outputDirectory>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Phân tích POM:

- `maven.compiler.release=17` chọn mức Java để Compiler Plugin biên dịch. Nó không tự cài JDK.
- `com.h2database:h2` có `runtime`: không cần để compile `JdbcDemo.java`, nhưng có mặt khi Surefire chạy test và khi runtime classpath được lắp đúng.
- `junit-jupiter` có `test`: test code và Surefire cần nó, nhưng JUnit không cần trong ứng dụng chạy sau khi đóng gói.
- `maven-dependency-plugin` được ghim phiên bản và cấu hình goal `copy-dependencies` để copy dependency cần cho runtime vào `target/runtime-libs`. **Chỉ cấu hình plugin như thế không tự chạy goal tại package**; ta sẽ gọi nó rõ ràng sau bước build.
- `<includeScope>runtime</includeScope>` trong **Dependency Plugin** là *scope threshold*: goal sẽ copy dependency thuộc **compile và runtime**; nó **không có nghĩa chỉ copy dependency mà POM viết đúng chữ `runtime`**. Trong ví dụ không có external compile dependency, nên chủ yếu copy H2.

Cấu hình này chỉ phục vụ thí nghiệm. Một ứng dụng production có thể dùng bộ đóng gói/deployment được tổ chức lựa chọn thay vì copy JAR vào thư mục thủ công.

### 5.3. Mã Java ứng dụng: chỉ import API JDK

Tạo `src/main/java/vn/example/runtime/JdbcDemo.java`:

~~~java
package vn.example.runtime;

import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Statement;

public final class JdbcDemo {
    private JdbcDemo() {
    }

    public static int queryScore() throws SQLException {
        try (Connection connection = DriverManager.getConnection(
                "jdbc:h2:mem:scope_demo");
             Statement statement = connection.createStatement()) {

            statement.executeUpdate(
                    "CREATE TABLE scores (id INT PRIMARY KEY, points INT NOT NULL)");
            statement.executeUpdate(
                    "INSERT INTO scores (id, points) VALUES (1, 7)");

            try (ResultSet results = statement.executeQuery(
                    "SELECT points FROM scores WHERE id = 1")) {
                if (!results.next()) {
                    throw new SQLException("Expected score not found");
                }
                return results.getInt("points");
            }
        }
    }

    public static void main(String[] args) throws SQLException {
        System.out.println("score=" + queryScore());
    }
}
~~~

Đây là một chương trình Java **độc lập về mã nguồn**: mọi `import` đều thuộc `java.sql` trong JDK, không có `import org.h2...`. Khi runtime cung cấp H2 JAR, JDBC driver xử lý URL `jdbc:h2:mem:scope_demo`.

H2 `mem` tạo database trong bộ nhớ. Theo thiết lập mặc định của H2, khi kết nối cuối cùng đóng, database có thể bị hủy; do mỗi lần gọi `queryScore()` mở và đóng một kết nối, ví dụ có thể chạy lặp lại trong một tiến trình JVM mà không vướng lỗi bảng `scores` còn sót từ lần trước. Đây là ứng dụng ví dụ, không phải hướng dẫn thiết kế database production.

Nếu runtime có driver, stdout **chính xác** từ `main` là:

~~~text
score=7
~~~

Các dòng log của Maven không thuộc stdout của `JdbcDemo.main`.

### 5.4. Mã unit test

Tạo `src/test/java/vn/example/runtime/JdbcDemoTest.java`:

~~~java
package vn.example.runtime;

import static org.junit.jupiter.api.Assertions.assertEquals;

import java.sql.SQLException;
import org.junit.jupiter.api.Test;

class JdbcDemoTest {
    @Test
    void loadsDriverAndQueriesScore() throws SQLException {
        assertEquals(7, JdbcDemo.queryScore());
    }
}
~~~

JUnit ở scope `test` được đưa vào test compile/test runtime; H2 ở scope `runtime` **cũng được đưa vào test runtime**. Vì vậy Surefire có thể chạy test trên cơ sở dữ liệu H2, dù Compiler Plugin khi biên dịch mã chính không cần H2.

### 5.5. Kiểm tra Java/Maven trước khi chạy

~~~bash
java -version
mvn -version
~~~

Cả hai nên xác nhận JDK 17+ được sử dụng phù hợp. Sau đó, từ thư mục chứa `pom.xml`:

~~~bash
mvn clean compile
mvn test
mvn package
~~~

Quan sát:

1. `mvn clean compile` biên dịch `JdbcDemo.java` vào `target/classes/vn/example/runtime/JdbcDemo.class`. Điều này chứng minh mã chính không cần H2 trên **compile classpath**.
2. `mvn test` chạy `JdbcDemoTest` bằng Surefire; báo cáo dự kiến có **1 test PASS, 0 failures, 0 errors**. H2 có mặt ở test classpath.
3. `mvn package` đi qua các phase cần thiết và tạo `target/runtime-scope-demo-1.0.0.jar` nếu test vẫn PASS.

Có thể gộp bước build sạch thành:

~~~bash
mvn clean package
~~~

Đây là cách tốt để tránh nhầm với kết quả JAR/test còn lại từ lần chạy cũ. Nó vẫn chạy các phase chuẩn trước `package`, gồm compile và test, nếu không bật tùy chọn skip.

## 6. Câu hỏi quan trọng: JAR vừa đóng gói có chứa H2 không?

Chạy:

~~~bash
jar tf target/runtime-scope-demo-1.0.0.jar
~~~

Trong kết quả liệt kê, bạn sẽ thấy entry tương tự:

~~~text
vn/example/runtime/JdbcDemo.class
~~~

**Không nên mong đợi mặc định có `h2-2.3.232.jar` nằm trong JAR của dự án.** Maven JAR Plugin chuẩn đóng gói class/resource từ output project; nó **không biến runtime dependency thành fat JAR** chỉ vì POM khai báo `runtime`.

Thử chạy chỉ với JAR ứng dụng:

~~~bash
java -cp target/runtime-scope-demo-1.0.0.jar vn.example.runtime.JdbcDemo
~~~

Nếu không có H2 ở classpath và không có một JDBC driver nào khác xử lý URL `jdbc:h2:...`, bạn sẽ nhận lỗi thuộc dạng:

~~~text
java.sql.SQLException: No suitable driver found for jdbc:h2:mem:scope_demo
~~~

Lỗi này thường có stack trace phía dưới và mã thoát khác 0. **Đây là thí nghiệm thất bại có chủ đích**, không phải một command được khuyến nghị để chạy ứng dụng production.

Điều quan trọng: `mvn package` thành công **không** chứng minh lệnh `java -cp app.jar ...` đơn độc sẽ có đủ dependency. Test có runtime H2 vì Maven/Surefire đã tạo test classpath; lệnh `java` tự chạy là một tiến trình mới, không dùng lại classpath test của Maven.

## 7. Dựng runtime classpath chính xác rồi chạy ứng dụng

### 7.1. Copy dependency cần cho runtime

Sau khi đã build:

~~~bash
mvn dependency:copy-dependencies
~~~

Vì POM cấu hình `maven-dependency-plugin`:

~~~xml
<configuration>
    <includeScope>runtime</includeScope>
    <outputDirectory>${project.build.directory}/runtime-libs</outputDirectory>
</configuration>
~~~

plugin sẽ copy những dependency thuộc **runtime classpath** vào `target/runtime-libs`. Với dự án mẫu, file quan trọng nhất là:

~~~text
target/runtime-libs/h2-2.3.232.jar
~~~

JUnit có `test` nên **không được đưa vào thư mục runtime-libs** qua lựa chọn `includeScope=runtime`. Nếu trong một dự án khác có dependency `compile`, các dependency ấy **cũng được copy**. Đừng hiểu sai câu “include runtime” thành “loại compile”.

### 7.2. Linux/macOS

Chạy trên terminal trong thư mục dự án:

~~~bash
java -cp "target/classes:target/runtime-libs/*" vn.example.runtime.JdbcDemo
~~~

Hoặc chạy từ JAR:

~~~bash
java -cp "target/runtime-scope-demo-1.0.0.jar:target/runtime-libs/*" vn.example.runtime.JdbcDemo
~~~

Dấu `:` phân tách các phần classpath trên Unix. Dấu `*` ở cuối `runtime-libs/*` là **wildcard classpath của Java launcher** để nạp các JAR ngay trong thư mục; đặt toàn bộ classpath trong dấu nháy để shell không tự mở rộng wildcard theo cách ngoài dự định.

### 7.3. Windows PowerShell/CMD

Chạy từ thư mục dự án:

~~~bat
java -cp "target\classes;target\runtime-libs\*" vn.example.runtime.JdbcDemo
~~~

Hoặc:

~~~bat
java -cp "target\runtime-scope-demo-1.0.0.jar;target\runtime-libs\*" vn.example.runtime.JdbcDemo
~~~

Trên Windows, dấu `;` phân cách các thành phần classpath. Dấu `\*` được Java launcher hiểu là wildcard JAR trong thư mục. Dùng đường dẫn kiểu Windows khi thao tác trong CMD/PowerShell.

Với cả hai hệ điều hành, stdout **đúng** từ ứng dụng:

~~~text
score=7
~~~

Bạn đã chứng minh:

- Mã **compile** được mà không cần import H2.
- Maven **test** được do H2 nằm trong test classpath.
- Chương trình **runtime** thành công khi classpath có H2 JAR.
- Nếu bỏ H2 khỏi runtime classpath, chương trình có thể không tìm thấy JDBC driver.

### 7.4. Không nhầm local Maven repository với Java classpath

Maven thường cache H2 tại một đường dẫn tương tự:

~~~text
~/.m2/repository/com/h2database/h2/2.3.232/h2-2.3.232.jar
~~~

Nhưng `java -cp target/classes ...` **không tự quét** toàn bộ `~/.m2/repository`. Bạn có thể trỏ thủ công đến đường dẫn JAR trong repository để thử, nhưng cách triển khai đó phụ thuộc thư mục máy người dùng và khó vận chuyển; thư mục `target/runtime-libs` giúp minh họa cách tập hợp JAR rõ ràng hơn.

Trong hệ thống thật, hãy dùng cơ chế phân phối dependency chuẩn của ứng dụng/CI (distribution package, container image, application server, framework launcher hoặc fat JAR được xây dựng đúng cách) thay vì kỳ vọng máy đích có cùng Maven cache.

## 8. Runtime scope có đi vào test classpath không?

**Có.** Đó là một điểm quan trọng và đôi khi gây hiểu nhầm.

Với bài thực hành:

~~~text
Compile classpath:
  JDK APIs + classpath compile/provided (không cần H2)

Test classpath:
  target/classes + target/test-classes
  + H2 runtime
  + JUnit Jupiter test
  + dependency bắc cầu phù hợp

Application runtime classpath:
  target/classes hoặc app JAR
  + H2 runtime
  + mọi dependency compile/runtime cần thiết
  (không cần JUnit test)
~~~

Khi Surefire thực thi `JdbcDemoTest`, driver H2 có mặt trong test classpath. Do đó test có thể PASS. Tuy nhiên một lần chạy Java bên ngoài Maven thiếu H2 vẫn FAIL.

### 8.1. Tại sao test PASS không bảo đảm deployment đúng?

Một unit/integration test chỉ chứng minh chương trình hoạt động với **classpath mà test runner cung cấp**. Production launcher có thể không có cùng classpath, đặc biệt khi:

- Copy mỗi JAR ứng dụng mà không copy các dependency JAR.
- Container image thiếu thư mục lib.
- Start script dùng sai dấu `:`/`;`.
- Build pipeline copy nhầm chỉ compile scope hoặc chỉ JUnit.
- Application server/container cung cấp một số API nhưng không cung cấp implementation thực tế.

Vì vậy nên có **smoke test chạy artifact theo đúng cách deployment**. Trong ví dụ, lệnh `java -cp "app.jar:runtime-libs/*" ...` là smoke test tối thiểu. Một dự án lớn cần kiểm thử sâu hơn về cấu hình/mạng/dữ liệu và health check.

### 8.2. Điều gì xảy ra nếu đổi H2 sang test scope?

Nếu đổi POM thành:

~~~xml
<scope>test</scope>
~~~

thì Surefire test vẫn có thể chạy vì H2 nằm ở test classpath, **nhưng runtime classpath của sản phẩm không còn H2**. Khi gọi `dependency:copy-dependencies` với `includeScope=runtime`, H2 sẽ bị loại. Nếu mã chính vẫn cần H2 lúc ứng dụng chạy, cấu hình này **sai mục đích**.

Đây là nguyên nhân thường gặp khi developer nhận thấy “H2 chỉ để chạy test trên laptop” rồi để `test`, nhưng chương trình chính thực tế cũng dùng H2. Nếu ứng dụng chỉ dùng H2 trong test và production dùng driver khác, thì dùng H2 scope `test` **lại có thể đúng**; hãy dựa vào kiến trúc thực sự.

## 9. Hiểu dependency bắc cầu: runtime có thể lan truyền

Maven có cơ chế **transitive dependencies**: dự án A phụ thuộc B, còn B phụ thuộc C, thì C có thể xuất hiện trong dependency graph của A theo **quy tắc scope kết hợp**.

Giả sử project A khai báo:

~~~text
A --(compile)--> B --(runtime)--> C
~~~

Theo bảng scope propagation của Maven, C đi vào dependency graph của A với **scope runtime**. Nghĩa là mã A thường không có C ở compile classpath, nhưng khi chạy A thì C có thể cần.

Một số trường hợp:

| Scope từ A đến B | Scope của C do B khai báo | Scope kết quả của C ở A |
| --- | --- | --- |
| `compile` | `compile` | `compile` |
| `compile` | `runtime` | `runtime` |
| `runtime` | `compile` | `runtime` |
| `runtime` | `runtime` | `runtime` |
| `test` | `compile` | `test` |
| `test` | `runtime` | `test` |
| `compile` | `provided` | Thường bị loại khỏi graph bắc cầu này |
| `compile` | `test` | Bị loại |

Quy tắc bắc cầu giải thích vì sao runtime classpath có thể chứa JAR mà bạn **không thấy khai trực tiếp** trong POM. Không được xóa “JAR lạ” khỏi bản đóng gói chỉ vì ứng dụng không import nó: nó có thể là implementation/binary cần bởi một dependency khác.

### 9.1. Dùng dependency:tree thay vì đoán

~~~bash
mvn dependency:tree
~~~

Trong ví dụ bạn sẽ thấy node:

~~~text
com.h2database:h2:jar:2.3.232:runtime
~~~

và JUnit ở scope `test` cùng những thư viện test liên quan. Thứ tự/thông tin của cây có thể khác nhau theo phiên bản plugin, nhưng mỗi node có tọa độ và scope. Có thể lọc theo artifact:

~~~bash
mvn dependency:tree -Dincludes=com.h2database:h2
~~~

Lọc giúp thấy nguồn dependency, nhưng khi debug xung đột version bạn nên xem **toàn bộ cây** và dependency management thực tế.

### 9.2. Khi nên khai báo trực tiếp một dependency

Nếu `src/main/java` trực tiếp import API của C nhưng C chỉ đến qua dependency bắc cầu của B, thiết kế đang phụ thuộc vào cấu trúc dependency của B. Một lần nâng version B có thể bỏ C và làm A không còn compile. Maven khuyến nghị khai báo trực tiếp dependency mà mã nguồn sử dụng trực tiếp.

Với một runtime provider như JDBC driver, nếu ứng dụng chịu trách nhiệm lựa chọn H2 ở runtime thì việc khai báo **H2 trực tiếp với `runtime`** cũng là một cách minh bạch hóa quyết định vận hành, dù không import lớp `org.h2`.

### 9.3. Optional và exclusions

Dependency có `<optional>true</optional>` là **optional đối với project phụ thuộc phía sau**, không phải cờ nói rằng thư viện không cần trong runtime của chính project khai báo. Khi một downstream không nhận provider tùy chọn, nếu cần nó thật sự, downstream phải khai báo trực tiếp.

`<exclusions>` cắt một đường dependency bắc cầu; dùng sai có thể làm runtime thiếu implementation và phát sinh `NoClassDefFoundError`. Không nên thêm exclusions chỉ để “làm dependency tree gọn hơn” mà không chạy lại test/runtime smoke test.

## 10. Runtime scope với provided scope khác nhau thế nào?

Hai scope này thường bị nhầm vì đều nói đến thời điểm chạy, nhưng ý nghĩa là **ngược nhau** ở việc ai cung cấp thư viện.

### `runtime`

“Ứng dụng cần thư viện khi chạy; **bộ phân phối runtime của ứng dụng phải có nó**.”

Ví dụ ứng dụng Java thuần dùng H2 JDBC driver: người đóng gói/triển khai phải đưa H2 vào runtime classpath, trừ khi platform đã có cách cung cấp đã được kiểm soát riêng.

### `provided`

“Mã cần một API lúc compile và test, nhưng **môi trường triển khai sẽ tự cung cấp** nó lúc chạy.”

Ví dụ mã web application dùng Servlet API khi đóng gói WAR cho một servlet container tương thích. Container cung cấp API/implementation khi chạy; bundle thêm một bản Servlet API khác vào gói triển khai có thể gây xung đột.

| So sánh | `runtime` | `provided` |
| --- | --- | --- |
| Dùng khi biên dịch mã chính? | Không | Có |
| Thuộc Maven application runtime classpath? | Có | Không |
| Có mặt khi Maven chạy test? | Có | Có |
| Ai chịu trách nhiệm cung cấp khi triển khai? | Bản runtime/distribution của ứng dụng | Container/JDK/platform bên ngoài theo hợp đồng |
| Ví dụ | H2 driver của app độc lập | Servlet API do container cung cấp |

**Không đặt JDBC driver thành provided chỉ vì “database chạy ở server khác”.** JDBC driver là thư viện Java chạy **trong tiến trình ứng dụng**, trong khi database server là dịch vụ tách biệt. Chỉ dùng provided cho driver nếu môi trường chạy thực sự cấp JAR driver cho process và cơ chế đó đã được xác nhận rõ.

## 11. Dependency:copy-dependencies là công cụ học classpath, không phải fat-JAR builder

Plugin `maven-dependency-plugin` có goal `copy-dependencies` cho phép copy dependency từ local repository về một thư mục.

Trong POM mẫu đã dùng:

~~~xml
<includeScope>runtime</includeScope>
<outputDirectory>${project.build.directory}/runtime-libs</outputDirectory>
~~~

Theo tài liệu chính thức, `includeScope` là **ngưỡng lọc classpath**:

| includeScope của copy-dependencies | Các dependency thường được chọn |
| --- | --- |
| `runtime` | `compile` và `runtime` |
| `compile` | `compile`, `provided` và `system` |
| `test` | Tất cả các scope thích hợp với test, theo logic lọc của goal |
| `provided` | `provided` |
| `system` | `system` |

Mẫu này đặc biệt hữu ích để chứng minh tại sao chỉ copy compile scope có thể làm thiếu JDBC driver H2. Để thử, có thể chạy riêng:

~~~bash
mvn dependency:copy-dependencies -DincludeScope=compile -DoutputDirectory=target/compile-libs
~~~

Nếu plugin nhận các user properties như trong tài liệu, lệnh trên chọn compile threshold; H2 được khai `runtime` nên không vào `target/compile-libs`. Hãy dùng một thư mục output **khác** để không lẫn với `target/runtime-libs` từ lần chạy trước.

**Lưu ý thực tế:** copy các JAR vào một thư mục phẳng có thể gặp xung đột tên file giữa dependency khác tọa độ nhưng trùng tên JAR. Đối với distribution quy mô lớn, nên dùng quy tắc đóng gói và kiểm thử artifact được thiết kế chuyên biệt.

### 11.1. Maven build classpath khác Java launcher classpath

- `mvn test`: Maven/Surefire chuẩn bị test classpath chứa H2 và JUnit.
- `mvn package`: Maven đóng JAR ứng dụng theo `packaging=jar`; không tự tạo executable fat JAR.
- `java -cp ...`: chính bạn quyết định JAR/thư mục nào nằm trong classpath của ứng dụng.
- `java -jar app.jar`: cần manifest `Main-Class` hợp lệ; và dù có manifest, external dependency vẫn phải được giải quyết qua cách đóng gói/manifest/launcher tương ứng.

Đừng gọi một JAR đơn giản là “self-contained” chỉ vì `mvn package` thành công. Hãy thử start nó bằng chính cách sẽ dùng ở môi trường triển khai.

### 11.2. Fat JAR và service provider

Một số ứng dụng dùng Maven Shade Plugin hoặc framework packaging để gộp dependency thành JAR thực thi. Đây là **một lựa chọn khác** với thư mục `runtime-libs`. Khi gộp thư viện sử dụng `META-INF/services` (như JDBC providers), phải lưu ý việc **merge service descriptors** bằng cấu hình đóng gói phù hợp; nếu không, service loader có thể không tìm thấy implementation dù class đã nằm trong JAR.

Không đưa đoạn cấu hình Shade tùy ý vào POM bài này chỉ để có một JAR duy nhất. Người học cần hiểu mô hình classpath trước, sau đó mới quyết định hình thức phân phối.

## 12. Checklist từng giai đoạn và đầu ra dự kiến

Với toàn bộ mẫu không thay đổi:

| Thao tác | Kết quả quan sát đúng |
| --- | --- |
| `mvn clean compile` | Có `target/classes/.../JdbcDemo.class`; compiler không cần import H2 |
| `mvn test` | `JdbcDemoTest` chạy qua Surefire và PASS; H2 có ở test runtime |
| `mvn package` | Có `target/runtime-scope-demo-1.0.0.jar` |
| `jar tf ...` | Có `JdbcDemo.class`, **không phải** bản H2 JAR lồng vào |
| `java -cp "target/classes" ...` | Có thể báo “No suitable driver” vì H2 vắng mặt |
| `mvn dependency:copy-dependencies` | Có `target/runtime-libs/h2-2.3.232.jar` |
| `java -cp "target/classes:target/runtime-libs/*" ...` trên Unix | In `score=7` |
| `java -cp "target\\classes;target\\runtime-libs\\*" ...` trên Windows | In `score=7` |
| `mvn dependency:tree` | H2 là `runtime`, JUnit là `test` |

Hãy bắt đầu với `clean` để giảm khả năng đầu ra cũ làm sai kết luận. Nếu từng thực hành đổi scope, xóa JAR thử nghiệm hoặc chạy một command với option khác, cần khôi phục đúng POM trước khi đối chiếu bảng này.

## 13. Những lỗi thường gặp và cách giải quyết

| Lỗi hoặc triệu chứng | Nguyên nhân hay gặp | Cách kiểm tra có cơ sở |
| --- | --- | --- |
| `No suitable driver found for jdbc:h2:...` | H2 JAR không có trong runtime classpath, URL sai hoặc driver không được nạp | Kiểm tra JAR H2, classpath, JDBC URL; chạy với `runtime-libs/*` |
| `ClassNotFoundException: org.h2.Driver` | Cố tải lớp H2 nhưng JAR vắng mặt | Thêm đúng runtime JAR; kiểm tra class loader |
| `NoClassDefFoundError` tại production | Thiếu dependency runtime hoặc bản đóng gói/copy không đủ | `dependency:tree`, archive contents, launcher/container classpath |
| `package org.h2 does not exist` lúc compile | Mã nguồn import H2 trong khi dependency chỉ có `runtime` | Dùng API JDBC chuẩn hoặc chuyển scope nếu thật sự cần API H2 lúc compile |
| Test PASS nhưng chạy JAR FAIL | Test có runtime dependency, Java launcher chưa có | Smoke test với đúng classpath deployment |
| H2 có trong `~/.m2` nhưng `java -cp app.jar` vẫn lỗi | Maven cache không tự là runtime classpath | Dùng `-cp` có H2 hoặc distribution đã đóng gói |
| `mvn package` thành công nhưng `java -jar ...` lỗi “no main manifest attribute” | JAR chưa có `Main-Class` | Dùng `java -cp ... FullyQualifiedMain` hoặc cấu hình manifest có chủ đích |
| H2 chỉ có ở test, không có runtime-libs | POM khai H2 `test` hoặc copy filtering khác runtime | Kiểm tra scope, goal `copy-dependencies` và output |
| JUnit xuất hiện trong production lib folder | Copy không lọc test scope | Dùng `includeScope=runtime`, kiểm tra nội dung distribution |
| Hai phiên bản của một thư viện khác nhau ở test và runtime | Dependency mediation/management, exclusion, scope khác | Đọc `dependency:tree`, effective POM và quy tắc version |
| Plugin không tải được artifact | Repository/mirror/proxy hoặc tọa độ sai | Phân biệt lỗi resolution với lỗi Java runtime |
| `release version 17 not supported` | Maven đang chạy bằng JDK quá cũ | `mvn -version`, `JAVA_HOME`, thiết lập compiler release |
| Test bị bỏ mà log vẫn BUILD SUCCESS | Có `-DskipTests`/`-Dmaven.test.skip` hoặc discovery sai | Đọc Surefire reports và số test thực chạy |
| Dùng `java -cp` trên Windows nhưng tách bằng `:` | Sai ký tự phân cách classpath | Windows dùng `;`, Linux/macOS dùng `:` |
| Build có JAR cũ sau `mvn compile` | `compile` không tự tạo JAR, file từ lần package trước | Dùng `mvn clean compile` để xác minh đầu ra sạch |

### 13.1. Quy trình gỡ lỗi trong 5 bước

1. **Tìm class hoặc service đang thiếu.** Với JDBC, đọc thông báo `No suitable driver` và kiểm tra URL `jdbc:h2:...`. Với class khác, ghi lại tên class đầy đủ từ stack trace.
2. **Kiểm tra dependency graph** bằng `mvn dependency:tree`: thư viện có tồn tại không, phiên bản nào, scope gì, đến trực tiếp hay bắc cầu?
3. **Xác định phase lỗi**: compile, test, package hay chỉ lỗi khi `java` chạy sau build? Scope đưa JAR vào từng classpath khác nhau.
4. **Kiểm tra classpath tại chính điểm lỗi.** Đừng kết luận từ việc file có trong Maven cache. Xem script khởi động, `-cp`, container/distribution và những JAR thực tế đi cùng sản phẩm.
5. **Chạy lại smoke test** đúng cách triển khai; nếu dùng một bản package mới, loại đầu ra cũ để không kiểm tra nhầm JAR.

Không nên sửa mọi dependency thành `compile` để né lỗi runtime. Việc này làm compile classpath phình ra, khiến mã chính có thể phụ thuộc implementation không cần thiết, và không giải quyết được sai sót trong bước phân phối runtime libraries.

## 14. Sự khác nhau giữa Maven Dependency và runtime của framework/container

Trong ứng dụng không dùng framework, `java -cp` là cách dễ thấy nhất để hiểu runtime classpath. Nhưng nhiều hệ thống thực tế có thêm lớp đóng gói:

- **Spring Boot executable JAR**: plugin đóng gói có thể sắp xếp dependencies thành cấu trúc bên trong ứng dụng và dùng launcher riêng; không thể kiểm tra như một JAR Maven đơn giản.
- **Servlet container/WAR**: một số API `provided` do container cấp, còn thư viện ứng dụng cần ở runtime có thể được gói dưới `WEB-INF/lib` tùy cách WAR plugin/packager xử lý.
- **Application server/module system**: server có thể cấp thư viện theo classloader riêng; cần phân biệt scope Maven với tập JAR thực sự có trên server.
- **Docker/OCI image**: file JAR, thư mục `lib`, entrypoint và working directory đều ảnh hưởng classpath lúc chạy.
- **Gradle hoặc công cụ khác**: tên cấu hình runtime khác nhau; không chuyển máy móc `scope=runtime` của Maven sang cấu hình của công cụ khác.

Trong mọi trường hợp, quy tắc chung vẫn là: **runtime implementation phải được cung cấp cho tiến trình sử dụng nó**, nhưng cách cung cấp có thể là external JARs, fat JAR, framework launcher hoặc container tùy kiến trúc.

### 14.1. Runtime driver và database server không giống nhau

H2 trong ví dụ chạy **in-memory cùng tiến trình Java**. Với PostgreSQL/MySQL thực, driver JDBC vẫn là thư viện trong tiến trình ứng dụng, còn database server là dịch vụ bên ngoài trên mạng.

Đừng nói “database nằm trên server nên driver phải là provided”. Cần hỏi **JDBC driver JAR nằm ở đâu khi tiến trình Java chạy**. Nếu deployment thực sự cấp driver qua app server và hợp đồng classloader, đó mới là một lý do cân nhắc `provided`; còn app standalone thông thường vẫn cần driver trong runtime distribution.

### 14.2. Không đưa credentials vào POM

Phần hướng dẫn dùng JDBC URL in-memory không cần tài khoản. Với cơ sở dữ liệu thật, username/password, endpoint hoặc secret nên lấy từ cấu hình runtime/secret manager theo chính sách công ty. Đừng hardcode mật khẩu vào `pom.xml`, Java source hay resource được filtering vào JAR để “chạy nhanh”.

Scope chỉ giải quyết **thư viện nào có trong classpath**, không quyết định database connection string, xác thực, firewall hay migration.

## 15. Bài tập thực hành: dự đoán rồi kiểm chứng

### Bài tập A — Phân biệt compile và runtime

Giữ H2 ở `runtime`. Chạy `mvn clean compile`, kiểm tra `JdbcDemo.class`. Thử thêm một import `org.h2.Driver` vào mã chính và biên dịch lại để thấy sự khác biệt, sau đó **xóa import** để khôi phục thiết kế dùng API JDBC chuẩn.

**Câu hỏi:** Nếu trình biên dịch không thấy `org.h2.Driver`, tại sao test JDBC vẫn có thể chạy? Trả lời bằng hai từ khóa **compile classpath** và **test classpath**.

### Bài tập B — Chứng minh thiếu driver

Sau `mvn clean package`, thử:

~~~bash
java -cp target/classes vn.example.runtime.JdbcDemo
~~~

Ghi lại lỗi phù hợp khi không có H2. Sau đó gọi `mvn dependency:copy-dependencies` và chạy lại Java với runtime-libs như hướng dẫn trên hệ điều hành của bạn. Xác nhận stdout `score=7`.

### Bài tập C — Chứng minh scope của test dependency

Mở `target/runtime-libs` và kiểm tra H2 có mặt còn JUnit không. Thử đổi H2 sang `test`, build/test lại rồi chạy `copy-dependencies` trong **thư mục đích mới hoặc sau khi clean** để không thấy nhầm JAR cũ. Giải thích vì sao test có thể PASS nhưng runtime không có H2. Khôi phục `runtime` cuối bài.

### Bài tập D — So sánh với provided

Trình bày sự khác biệt nếu cùng dependency H2 được đặt `provided`. Với Maven thông thường, liệu `JdbcDemo.java` có compile được không? Test có được cấp driver không? Runtime distribution bằng `includeScope=runtime` có chứa H2 không? Khi ứng dụng chạy standalone mà không có driver, điều gì xảy ra?

### Bài tập E — Đọc dependency tree

Chạy `mvn dependency:tree` và xác định H2 thuộc `runtime`, JUnit thuộc `test`. Với một dependency khác có API import trực tiếp từ source, giải thích vì sao nên dùng `compile` thay vì dựa vào một dependency bắc cầu tình cờ.

### Bài tập F — Tính scope bắc cầu

Vẽ đồ thị `A -(compile)-> B -(runtime)-> C`. Dự đoán scope của C ở A. Tiếp theo đổi `A -(runtime)-> B -(compile)-> C`, dự đoán scope của C ở A. Đối chiếu bảng scope propagation Maven: trong cả hai trường hợp này, C đi vào A dưới `runtime`.

### Bài tập G — Lập checklist deployment

Giả sử một pipeline copy `target/runtime-scope-demo-1.0.0.jar` vào Docker image nhưng không copy H2. Test của pipeline đã PASS. Hãy nêu chính xác những file cần có, command launcher cần dùng hoặc cách packaging khác để ứng dụng thực sự start được trong image.

## 16. Checklist khi hoàn thành

Bạn hiểu đúng chủ đề khi có thể nói:

- `runtime` loại thư viện khỏi **compile classpath của mã chính**, nhưng có trong **runtime và test classpaths**.
- `compile` là mặc định cho API/lớp mã sản phẩm import trực tiếp; `test` dành cho test; `provided` dành cho API mà môi trường chạy cấp.
- **Scope không tự tạo fat JAR**. Maven `package` thành công không đồng nghĩa `java -jar` hoặc `java -cp app.jar` đã có đủ runtime dependencies.
- Một JDBC driver có thể nằm ở `runtime` vì mã chính chỉ import `java.sql` của JDK và driver được phát hiện khi chạy.
- `includeScope=runtime` của Maven Dependency Plugin **gồm compile và runtime dependencies**, không phải chỉ các dependency viết `runtime`.
- Maven cache `~/.m2/repository` không tự được đưa vào Java launcher classpath.
- Test PASS không thay thế smoke test triển khai có runtime classpath thực.
- `dependency:tree`, test report, nội dung JAR và lệnh `java -cp` là những nguồn bằng chứng bổ sung nhau.
- Trước khi đổi scope, phải biết lỗi xảy ra **khi compile, khi Maven test hay khi JVM ứng dụng chạy**.

Thông điệp cuối: **Chọn dependency scope dựa trên nhu cầu của từng classpath, rồi kiểm tra riêng cách đưa thư viện đến tiến trình lúc chạy.** Với thư viện chỉ cần khi chạy, `runtime` là mô hình phù hợp — miễn là runtime distribution thực sự cung cấp implementation đó.

## 17. Tài liệu tham khảo chính thức

- [Apache Maven — Introduction to the Dependency Mechanism](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html): định nghĩa `compile`, `runtime`, `provided`, `test` và bảng transitive scope.
- [Apache Maven Dependency Plugin — copy-dependencies goal](https://maven.apache.org/plugins/maven-dependency-plugin/copy-dependencies-mojo.html): `includeScope`, `outputDirectory` và cách copy JAR.
- [Apache Maven Dependency Plugin — Copying project dependencies](https://maven.apache.org/plugins/maven-dependency-plugin/examples/copying-project-dependencies.html): ví dụ copy trực tiếp/transitive dependencies.
- [Apache Maven Dependency Plugin — dependency:tree](https://maven.apache.org/plugins/maven-dependency-plugin/tree-mojo.html): xem dependency graph và phạm vi dependency.
- [Apache Maven — Introduction to the Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html): compile, test, package và plugin bindings.
- [Maven Central — com.h2database:h2:2.3.232](https://central.sonatype.com/artifact/com.h2database/h2/2.3.232): artifact H2 được dùng trong bài thực hành.
