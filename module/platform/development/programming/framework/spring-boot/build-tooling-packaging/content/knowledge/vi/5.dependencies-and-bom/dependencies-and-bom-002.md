# Phạm vi `compile`, `runtime`, `provided` và `test` trong Maven

## 1. Mục tiêu và bối cảnh

Trong Maven, **dependency scope (phạm vi phụ thuộc)** quyết định một thư viện được đặt vào **classpath nào** của dự án ở từng giai đoạn và ảnh hưởng cách Maven xử lý các phụ thuộc bắc cầu (*transitive dependencies*). Đây là khái niệm quan trọng khi xây dựng ứng dụng Java/Spring Boot: ứng dụng có thể biên dịch thành công nhưng thiếu thư viện lúc chạy, hoặc gói thừa thư viện chỉ dùng trong test nếu khai báo sai scope.

Sau bài này, bạn có thể:

- Phân biệt chính xác bốn scope: `compile`, `runtime`, `provided` và `test`.
- Giải thích một dependency có mặt tại **biên dịch mã chính**, **chạy ứng dụng**, **biên dịch/chạy test** hay không.
- Chọn scope trong `pom.xml` cho starter, JDBC driver, thư viện do container cung cấp và công cụ kiểm thử.
- Phân biệt scope Maven tiêu chuẩn với hành vi đóng gói **JAR/WAR thông thường** và **Spring Boot executable JAR/WAR**.
- Hiểu scope được kết hợp ra sao khi Maven giải quyết dependencies bắc cầu và vai trò của `dependencyManagement`/BOM.
- Dùng Maven Wrapper và `dependency:tree` để kiểm tra kết quả thay vì suy đoán từ tên thư viện.

**Phạm vi bài:** các dependency do **Maven project** khai báo, trong bối cảnh ứng dụng Spring Boot sử dụng `pom.xml`. Gradle có các configuration khác như `implementation`, `runtimeOnly`, `compileOnly` và `testImplementation`; không nên đồng nhất trực tiếp chúng với bốn scope của Maven.

## 2. Dependency scope là gì?

Một dependency Maven thường có tọa độ `groupId`, `artifactId`, `version` (đôi khi được quản lý bởi BOM hoặc parent POM) và tùy chọn `scope`. Ví dụ đặt trực tiếp bên trong phần tử `<dependencies>` của `pom.xml`:

~~~xml
<dependency>
    <groupId>org.slf4j</groupId>
    <artifactId>slf4j-api</artifactId>
    <scope>compile</scope>
</dependency>
~~~

Đoạn XML trên là **một phần POM**, chưa phải `pom.xml` độc lập có thể chạy. Phiên bản của `slf4j-api` phải đến từ `dependencyManagement`/BOM hoặc một thẻ `<version>` được khai báo riêng. Trong dự án Spring Boot được tạo từ Spring Initializr, nhiều phiên bản thư viện đã được Spring Boot quản lý sẵn.

Nếu **không ghi `<scope>`**, Maven mặc định dùng **`compile`**:

~~~xml
<dependency>
    <groupId>org.slf4j</groupId>
    <artifactId>slf4j-api</artifactId>
</dependency>
~~~

Trong ví dụ này, khi không có cấu hình quản lý scope ghi đè, ý nghĩa đối với classpath giống `compile`. Scope không đơn thuần là “thư viện có được tải xuống không”: Maven thường phải tải artifact trước khi có thể biên dịch/kiểm thử; **scope quy định artifact nào tham gia từng classpath và sự lan truyền dependency**, không phải nhãn bật/tắt tải xuống.

### 2.1. Ba classpath cần phân biệt

1. **Compile classpath:** dùng biên dịch mã ứng dụng chính trong `src/main/java`.
2. **Runtime classpath:** dùng khi chạy ứng dụng ở môi trường runtime Maven tiêu chuẩn.
3. **Test classpath:** dùng biên dịch và chạy mã trong `src/test/java`; thường chứa cả dependencies của mã chính lẫn những dependency chỉ dành cho test.

Classpath có thể bao gồm cả dependencies trực tiếp và bắc cầu sau khi Maven giải quyết xung đột và phạm vi. Một dự án không phải web vẫn có runtime classpath; runtime không đồng nghĩa riêng với HTTP server.

## 3. Bảng tổng quan bốn scope

Với một dependency **được khai báo trực tiếp** trong project, bảng dưới mô tả cách Maven dùng nó theo classpath thông thường:

| Scope | Biên dịch `src/main/java` | Chạy ứng dụng | Biên dịch/chạy test | Ý nghĩa thực tế |
| --- | :---: | :---: | :---: | --- |
| **`compile`** | Có | Có | Có | Mã chính cần thư viện khi biên dịch và dùng nó khi chạy |
| **`runtime`** | Không | Có | Có | Không cần API của thư viện để biên dịch mã chính, nhưng cần implementation khi chạy |
| **`provided`** | Có | Không | Có | Biên dịch dựa vào API, nhưng kỳ vọng JDK/container hoặc môi trường thực thi cung cấp |
| **`test`** | Không | Không | Có | Chỉ phục vụ mã và công cụ kiểm thử |

**Hai lưu ý:**

- “Không có ở runtime” trong bảng là **runtime classpath tiêu chuẩn Maven**, chưa kết luận việc thư viện xuất hiện trong **Spring Boot repackaged JAR/WAR** hay không. Plugin đóng gói có quy tắc riêng, xem mục 8.
- “Có trong test classpath” không đồng nghĩa test sẽ tự động thành công: test còn cần dữ liệu, cấu hình, database, JVM và các dependency khác phù hợp.

Có thể ghi nhớ bằng ba câu hỏi:

1. **Mã chính có import/trực tiếp dùng kiểu của thư viện?** Thường cần `compile`; nếu runtime do container cung cấp thì cân nhắc `provided`.
2. **Mã chính chỉ cần một implementation khi chạy (còn API đã có từ JDK hoặc thư viện khác)?** Cân nhắc `runtime`.
3. **Chỉ mã test/công cụ kiểm thử cần thư viện?** Dùng `test`.

Bất cứ khi nào không rõ, kiểm tra code, classpath và cách triển khai thật; không đặt scope chỉ dựa vào tên dependency.

## 4. `compile`: phụ thuộc dùng cho mã chính

`compile` là scope **mặc định** và được đặt vào cả ba classpath. Ví dụ: mã ứng dụng cần trực tiếp gọi các type trong `slf4j-api`, hoặc một Spring Boot starter khai báo dependencies để bạn viết controller/service.

Ví dụ đoạn dependency trong `pom.xml` của dự án dùng Spring Boot dependency management:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.slf4j</groupId>
        <artifactId>slf4j-api</artifactId>
        <!-- Không ghi scope: Maven dùng compile -->
    </dependency>
</dependencies>
~~~

Một lớp Java độc lập trong `src/main/java/com/example/scopes/CompileExample.java` minh họa việc mã chính import và dùng API của thư viện:

~~~java
package com.example.scopes;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public final class CompileExample {
    private static final Logger LOG =
            LoggerFactory.getLogger(CompileExample.class);

    private CompileExample() {}

    public static void main(String[] args) {
        LOG.info("Maven compile scope works");
    }
}
~~~

Lớp này **có phương thức `main` đầy đủ** và biên dịch được với Java 17+ nếu project có `slf4j-api` hợp lệ trên compile classpath. Khi chạy cần một SLF4J provider phù hợp để thực sự ghi log theo cấu hình; dòng log, định dạng và thậm chí việc có log hay không phụ thuộc provider/log level, nên không khẳng định stdout cố định. Trong ứng dụng Spring Boot, logging provider thường được cung cấp qua starter phù hợp.

Nếu bạn đổi dependency chứa `org.slf4j.Logger` từ `compile` sang `runtime` mà mã chính vẫn import các type trên, lệnh biên dịch mã chính có thể báo lỗi “package org.slf4j does not exist” hoặc “cannot find symbol”, **trừ khi một dependency khác vẫn đưa API đó vào compile classpath**.

**Tính bắc cầu:** dependency ở `compile` của một thư viện thường được lan truyền tới project khác khi thư viện đó là dependency, tùy sơ đồ scope và quy tắc xung đột Maven. Đối với thư viện mà code công khai dùng type của dependency khác, khai báo đúng `compile` quan trọng cho consumer.

## 5. `runtime`: cần khi chạy, không cần để biên dịch mã chính

`runtime` dùng cho artifact cung cấp một implementation mà mã chính không phải import lúc biên dịch. Ví dụ dễ hiểu là **JDBC driver**, khi code dùng JDBC API thuộc JDK hoặc framework, còn driver được chọn và nạp ở runtime.

Trong dự án Spring Boot đã dùng dependency management của Boot và có kết nối PostgreSQL, khai báo minh họa:

~~~xml
<dependency>
    <groupId>org.postgresql</groupId>
    <artifactId>postgresql</artifactId>
    <scope>runtime</scope>
</dependency>
~~~

Code Java ứng dụng có thể dùng type thuộc **`java.sql`**, vốn có sẵn trong JDK:

~~~java
package com.example.scopes;

import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.SQLException;

public final class JdbcExample {
    private JdbcExample() {}

    public static void main(String[] args) throws SQLException {
        try (Connection connection = DriverManager.getConnection(
                "jdbc:postgresql://localhost:5432/demo",
                "demo_user",
                "demo_password")) {
            System.out.println(connection.isValid(2));
        }
    }
}
~~~

Đây là chương trình Java 17+ có cú pháp hợp lệ, nhưng để chạy thành công phải có PostgreSQL JDBC driver **trên runtime classpath**, máy chủ PostgreSQL đang chạy tại URL ví dụ, database và tài khoản thật, cùng quyền truy cập mạng. **Không có stdout cố định** trong một môi trường chưa cấu hình database; khi kết nối thất bại `DriverManager.getConnection` ném `SQLException`. Ví dụ nhằm cho thấy code biên dịch dựa trên `java.sql` mà không import trực tiếp `org.postgresql.Driver`.

Khi dùng Spring Boot DataSource/JPA, việc chọn dependency runtime còn phụ thuộc cách Spring Boot auto-configuration phát hiện driver, connection URL, dependency pool và cấu hình `spring.datasource.*`.

**Không phải mọi JDBC driver đều luôn chỉ cần `runtime`:** nếu code chính import trực tiếp class riêng của driver (ví dụ `org.postgresql.PGConnection`) để gọi API đặc thù, nó cần API đó trên **compile classpath**, nên `runtime` có thể không phù hợp.

Một lỗi rất phổ biến là chuyển nhầm thư viện cần thiết ở runtime sang `test`: bộ kiểm thử có thể chạy được nhưng môi trường production lại thiếu driver hoặc provider khi ứng dụng khởi động.

## 6. `provided`: biên dịch được nhưng môi trường chịu trách nhiệm cung cấp

`provided` gần giống `compile` khi **biên dịch mã chính** và **chạy test**, nhưng **bị loại khỏi runtime classpath Maven thông thường**. Ý nghĩa thiết kế: thư viện/API sẽ được **JDK hoặc container/môi trường đích** cung cấp khi chạy.

Ví dụ điển hình: ứng dụng WAR triển khai vào **external Servlet container**, nơi container cung cấp các thành phần servlet/runtime theo hợp đồng triển khai. Đoạn POM minh họa:

~~~xml
<dependency>
    <groupId>jakarta.servlet</groupId>
    <artifactId>jakarta.servlet-api</artifactId>
    <scope>provided</scope>
</dependency>
~~~

Phiên bản `jakarta.servlet-api` phải phù hợp với nền tảng servlet container và có thể được quản lý bởi BOM/parent. Ví dụ trên **không phải chỉ dẫn để thêm servlet API thủ công cho mọi ứng dụng Spring Boot**: với Spring Boot starter, các API liên quan có thể đã được quản lý/bổ sung phù hợp.

**Ví dụ liên quan trực tiếp tới Spring Boot WAR:** nếu triển khai vào Tomcat bên ngoài, cấu hình WAR và đánh dấu embedded Tomcat dependency `provided` theo hướng dẫn triển khai tương ứng của dòng Spring Boot đang sử dụng:

~~~xml
<packaging>war</packaging>

<!-- Ví dụ trong <dependencies> -->
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-tomcat</artifactId>
    <scope>provided</scope>
</dependency>
~~~

Đây là **các đoạn POM**, không phải toàn bộ XML project. Tùy dòng Spring Boot và starter ứng dụng đã chọn, tên artifact/container phụ thuộc vào version và cấu hình. Mục đích của `provided` ở đây là tránh xung đột container nhúng với container ngoài khi triển khai WAR; cần kiểm tra hướng dẫn của dòng Boot thực tế.

**Cảnh báo về hành vi đóng gói:** Maven scope `provided` không bảo đảm một dependency luôn bị loại khỏi **mọi** file JAR/WAR được sinh ra. **Spring Boot Maven Plugin với goal `repackage` mặc định vẫn có thể đưa dependencies `provided` vào executable archive**. Với executable WAR, các thư viện `provided` được đặt trong `WEB-INF/lib-provided` để phục vụ `java -jar` mà không va chạm với thư viện của external container khi deploy. Xem mục 8 và tài liệu chính thức.

**Scope `provided` không phải “thư viện không quan trọng”**: nếu môi trường chạy thực tế không cấp implementation cần thiết, ứng dụng có thể gặp `ClassNotFoundException`, `NoClassDefFoundError` hoặc lỗi khởi tạo bean/classloader. Vì scope này **vẫn ở test classpath**, test chạy được trên máy phát triển chưa đủ để chứng minh external runtime đã cung cấp đúng thư viện.

## 7. `test`: phụ thuộc chỉ phục vụ kiểm thử

`test` xuất hiện ở classpath để **biên dịch và chạy test**, không có ở compile/runtime classpath của mã chính thông thường. Dùng cho JUnit, Mockito, AssertJ và công cụ kiểm thử khác chỉ cần trong `src/test/java`.

Trong dự án Spring Boot có BOM/parent quản lý versions, ví dụ:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

Tệp `src/test/java/com/example/scopes/ArithmeticTest.java` minh họa JUnit Jupiter:

~~~java
package com.example.scopes;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertEquals;

class ArithmeticTest {

    @Test
    void twoPlusTwoEqualsFour() {
        assertEquals(4, 2 + 2);
    }
}
~~~

Code kiểm thử là một class Java hợp lệ cho môi trường Java 17+, dùng API JUnit Jupiter mà starter/test dependencies phải cung cấp. Trong dự án Maven Spring Boot cấu hình test thông thường, chạy:

~~~bash
./mvnw test
~~~

Trên Windows PowerShell:

~~~powershell
.\mvnw.cmd test
~~~

Khi môi trường đã tải dependencies và có test engine/compiler plugin phù hợp, test này phải pass; nó không in một dòng stdout cố định, Maven có thể hiển thị số lượng test hoặc phần tóm tắt khác nhau theo phiên bản. Nếu `@Test` hoặc `Assertions` không được nhận diện từ `src/main/java`, đó là **đúng với ý nghĩa scope `test`**: mã production không được thiết kế để phụ thuộc JUnit.

**Bẫy thường gặp:** test có đầy đủ runtime, compile, provided và test dependencies, nên đôi khi test vô tình che một thiếu hụt ở production. Ví dụ code chính gọi implementation chỉ được đặt ở `test` nhưng test injection/configuration khác đã bổ sung classpath; cần kiểm tra runtime artifact và đường chạy thực tế.

## 8. Scope ảnh hưởng đóng gói JAR/WAR như thế nào?

Phải phân biệt ba tầng:

1. **Scope Maven:** quyết định các classpath của Maven và sự lan truyền dependency.
2. **Plugin tạo archive thông thường:** quyết định file được đóng vào JAR/WAR theo quy tắc plugin.
3. **Spring Boot Maven Plugin `repackage`:** biến JAR/WAR thành executable archive với quy tắc sắp xếp dependencies riêng.

### 8.1. Maven JAR thông thường

`maven-jar-plugin` theo cấu hình thông thường chủ yếu đóng gói **class/resources của chính project**, **không tự nhúng tất cả dependency JAR** vào bên trong JAR. Vì vậy “scope `compile` nghĩa là sẽ nằm trong mọi file JAR” là sai. Để chạy JAR thông thường, cần cấu hình classpath hoặc cơ chế triển khai dependencies ngoài JAR.

### 8.2. Maven WAR truyền thống

Khi tạo WAR tiêu chuẩn để deploy lên servlet container, các dependency phục vụ ứng dụng khi chạy (thường compile/runtime) được đưa vào `WEB-INF/lib` theo cấu hình packaging. Dependency `provided` được loại khỏi `WEB-INF/lib` vì container kỳ vọng sẽ cung cấp thư viện đó; test dependencies không phục vụ WAR sản phẩm.

### 8.3. Spring Boot executable JAR/WAR

Khi Spring Boot Maven Plugin chạy **`repackage`**, executable archive chứa class ứng dụng, Spring Boot loader và các dependency mà plugin chọn đóng gói. Theo tài liệu plugin, **các dependency `provided` được khai báo trong project cũng được bao gồm theo mặc định**, trừ khi có cấu hình loại trừ/thay đổi thích hợp. Cụ thể:

| Archive | Vị trí thường gặp | Ý nghĩa |
| --- | --- | --- |
| Spring Boot executable JAR | `BOOT-INF/classes` và `BOOT-INF/lib` | Chứa class ứng dụng và thư viện cho cách chạy qua `java -jar` |
| Spring Boot executable WAR | `WEB-INF/classes`, `WEB-INF/lib` và `WEB-INF/lib-provided` | Phân biệt thư viện runtime WAR và các dependency provided để có thể deploy external container hoặc chạy executable WAR |
| WAR truyền thống (không repackage) | `WEB-INF/classes` và `WEB-INF/lib` | Provided dependency không nằm trong `WEB-INF/lib` theo quy ước WAR thông thường |

**Điểm cần nhớ:** `provided` không tương đương lệnh “loại khỏi Spring Boot executable artifact”. Nếu muốn loại một dependency khỏi executable JAR/WAR của Boot, cần xem **Spring Boot Maven Plugin exclusions** như `<excludes>` hoặc tùy chọn phù hợp, đồng thời bảo đảm runtime vẫn có class cần thiết. Phải kiểm tra artifact cuối cùng thay vì chỉ đọc `pom.xml`.

Ví dụ trong project đã cấu hình `spring-boot-maven-plugin` và binding `repackage` từ Spring Boot parent hoặc phần `<executions>`:

~~~bash
./mvnw clean package
~~~

Nếu dùng parent/generator phù hợp, lệnh `package` sẽ tạo executable archive trong `target/`. **Không mặc định mọi Maven project đều tự có goal `repackage`**: thiếu Spring Boot plugin/binding thì `package` chỉ làm theo cấu hình Maven thường.

Để xem nội dung một JAR đã được đóng gói và có thật (ví dụ file thực tế tên `scope-demo-0.0.1-SNAPSHOT.jar`):

~~~bash
jar tf target/scope-demo-0.0.1-SNAPSHOT.jar
~~~

Lệnh `jar tf` liệt kê entries; hãy tìm `BOOT-INF/lib`, tên driver, JAR API hoặc `WEB-INF/lib-provided` nếu đang kiểm tra WAR. Nếu artifact tên khác, **dùng tên chính xác trong `target/`**; không dựa vào giả định về `version` hoặc classifier. Có thể xem các dòng chọn lọc bằng `grep` trên Linux/macOS hoặc `Select-String` trên PowerShell, nhưng việc một class xuất hiện trong archive không tự chứng minh mọi đường chạy sẽ thành công.

Nguồn chính thức: https://docs.spring.io/spring-boot/maven-plugin/packaging.html và https://docs.spring.io/spring-boot/how-to/deployment/traditional-deployment.html

## 9. Scope và phụ thuộc bắc cầu (transitive dependencies)

Maven đọc POM của dependency trực tiếp và các dependency sâu hơn, sau đó tính scope hiệu dụng của chúng. Ví dụ:

~~~text
Ứng dụng A
  └── Thư viện B (compile)
        └── Thư viện C (runtime)
~~~

Đối với A, C thường xuất hiện với scope hiệu dụng **`runtime`**, không phải mặc định `compile`; mã chính của A không tự có C trên compile classpath chỉ vì A phụ thuộc B.

Một số quy tắc kết hợp điển hình theo tài liệu Maven:

| Scope B khai báo trực tiếp trong A | Scope C trong POM của B | Scope hiệu dụng của C ở A |
| --- | --- | --- |
| `compile` | `compile` | `compile` |
| `compile` | `runtime` | `runtime` |
| `compile` | `provided` hoặc `test` | Bỏ qua theo đường phụ thuộc đó |
| `runtime` | `compile` | `runtime` |
| `runtime` | `runtime` | `runtime` |
| `provided` | `compile` | `provided` |
| `test` | `compile` | `test` |

Bảng này mô tả **một đường phụ thuộc**, chưa xét các đường khác đến cùng artifact, explicit declarations, exclusions, optional và dependency mediation. Maven có quy tắc chọn version theo mức gần (“nearest definition”) trong cây dependencies; scope hiệu dụng và version là hai vấn đề liên quan nhưng không giống nhau.

### 9.1. “Provided/test không transitive” cần hiểu đúng

Maven mô tả `provided` và `test` là scope **không lan truyền đến project consumer theo cách compile/runtime**: ví dụ một thư viện X khai báo một dependency `test` thì project Y sử dụng X không tự lấy dependency test đó cho mã production. Tuy vậy, dependency ở đường gián tiếp phía sau **một direct provided/test dependency của chính project hiện tại** vẫn có thể tham gia classpath của project đó theo bảng kết hợp scope. Vì thế không nên diễn giải “không transitive” thành “Maven tuyệt đối không đọc bất kỳ dependency con nào”.

### 9.2. Scope khác `optional` và `exclusions`

- `scope` là cơ chế đặt dependency vào classpath và xác định cách scope truyền qua graph.
- `<optional>true</optional>` trên dependency của một thư viện cho biết consumer của thư viện đó **không tự nhận dependency optional theo đường transitive đó**; consumer có thể khai báo trực tiếp nếu cần.
- `<exclusions>` trên một đường dependency giúp loại artifact bắc cầu theo đường đó; một đường khác vẫn có thể mang artifact vào graph.

Không dùng `test` hoặc `provided` như một cách “chữa cháy” khi gặp xung đột version. Cần phân tích cây dependencies và giải quyết nguyên nhân.

## 10. Scope khác quản lý phiên bản: `dependencyManagement` và BOM

Đây là chỗ dễ nhầm trong Spring Boot: **BOM và parent POM chủ yếu giúp chọn tập phiên bản dependency tương thích**, còn `<dependencies>` quyết định dependency nào dự án thực sự dùng. Scope có thể được quản lý trong dependency management nếu được khai báo, nhưng việc một BOM liệt kê artifact **không tự biến artifact đó thành dependency của project**.

Trong Spring Boot, phần lớn starter/artifact được Spring Boot dependency management kiểm soát version. Ví dụ khai báo PostgreSQL driver với `runtime` và không ghi version khi BOM đang quản lý artifact đó:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.postgresql</groupId>
        <artifactId>postgresql</artifactId>
        <scope>runtime</scope>
    </dependency>
</dependencies>
~~~

Nếu dự án không có dependency management cho PostgreSQL driver, cần cung cấp `<version>` hợp lệ. Maven không tự suy ra version chỉ từ `groupId` và `artifactId`.

Một BOM nhập vào `dependencyManagement` sử dụng `<type>pom</type>` và **`<scope>import</scope>`**, ví dụ rút gọn:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-dependencies</artifactId>
            <version>4.0.0</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

**`4.0.0` ở đây chỉ là ví dụ cú pháp, không phải khuyến nghị chọn version.** Dùng phiên bản Spring Boot đã được project hoặc team chốt. `import` **không phải** một trong bốn scope classpath của bài: nó chỉ có nghĩa đặc biệt đối với **dependency type `pom` trong `dependencyManagement`** để nhập danh sách managed dependencies từ BOM. Không đặt `import` vào một JAR dependency thông thường.

**Nếu dùng `spring-boot-starter-parent`**, parent đã tổ chức các cấu hình quản lý dependency/plugin tương ứng; không nên thêm lại BOM một cách máy móc. Khi dùng parent khác, có thể import Spring Boot BOM để dùng các version managed của Boot, nhưng plugin management và những thiết lập khác của parent Boot không tự được nhập giống hệt.

## 11. Thực hành kiểm chứng các scope bằng Maven Wrapper

Ví dụ này dành cho **một dự án Spring Boot Maven đã có từ Spring Initializr**, có `mvnw`/`mvnw.cmd`, `pom.xml` và JDK tương thích. Những đoạn XML ở các mục trước được đặt đúng bên trong `<dependencies>` của POM hiện có; không ghép chúng thành nhiều phần tử gốc `<dependencies>` trùng nhau.

### Bước 1 — Xác minh Maven đang chạy

Trên Linux/macOS:

~~~bash
java -version
./mvnw --version
~~~

Trên Windows PowerShell:

~~~powershell
java -version
.\mvnw.cmd --version
~~~

Maven Wrapper giữ phiên bản Maven theo cấu hình project, nhưng không tự đảm bảo đúng phiên bản JDK. Kiểm tra JDK dùng để biên dịch và Java version mà Spring Boot hỗ trợ.

### Bước 2 — Xem cây dependencies và scope

Linux/macOS:

~~~bash
./mvnw dependency:tree
./mvnw dependency:tree -Dincludes=org.postgresql:postgresql
~~~

Windows PowerShell:

~~~powershell
.\mvnw.cmd dependency:tree
.\mvnw.cmd dependency:tree "-Dincludes=org.postgresql:postgresql"
~~~

Lệnh thứ hai lọc dependency theo tọa độ `groupId:artifactId` nếu có trong cây. Plugin `maven-dependency-plugin` có thể được Maven tự giải quyết/tải ở lần đầu; cần mạng và repository nếu chưa cache.

Ví dụ **mô phỏng kiểu dòng hiển thị** (đây không phải output đảm bảo cho mọi project/version):

~~~text
[INFO] +- org.slf4j:slf4j-api:jar:2.x.y:compile
[INFO] +- org.postgresql:postgresql:jar:42.x.y:runtime
[INFO] \- org.junit.jupiter:junit-jupiter:jar:5.x.y:test
~~~

Trong output thật, version và thành phần dependency tree tùy `pom.xml`/BOM. Nhìn **scope ở cuối** dòng để thấy Maven đã giải quyết effective scope. Nếu có nhiều đường phụ thuộc hoặc phiên bản xung đột, đừng kết luận dựa trên một khai báo riêng lẻ.

### Bước 3 — Build và chạy test

Linux/macOS:

~~~bash
./mvnw clean test
./mvnw package
~~~

Windows PowerShell:

~~~powershell
.\mvnw.cmd clean test
.\mvnw.cmd package
~~~

`test` biên dịch và chạy test theo lifecycle/configuration. `package` thực hiện các giai đoạn trước nó của lifecycle (thường gồm test), sau đó tạo artifact. Sự thành công của lệnh không chứng minh được một external container, database hoặc server production đã cung cấp tất cả các dependency `provided` đúng phiên bản.

### Bước 4 — Xem dependency do parent/BOM quản lý

Khi cần xác định **version/scope hiệu dụng** sau kế thừa và dependency management:

~~~bash
./mvnw help:effective-pom
~~~

Output có thể rất dài; hãy tìm tọa độ artifact liên quan trong POM hiệu dụng và đối chiếu với `dependency:tree`. `dependencyManagement` giải thích nguồn version/default được quản lý; `dependency:tree` cho biết dependency thực sự được giải quyết trong graph. Đừng dùng một cách thay thế hoàn toàn cho cách kia.

### Bước 5 — Kiểm tra thứ được phát hành

Với Spring Boot Maven Plugin, xác nhận `repackage` có hoạt động, sau đó dùng `jar tf` để kiểm tra executable JAR/WAR thật. Đối với dịch vụ triển khai WAR vào external Tomcat, kiểm tra **cả cách deploy WAR** lẫn **nội dung `WEB-INF/lib` và `WEB-INF/lib-provided`** nếu archive được Boot repackage. Đây mới là phép thử gắn với môi trường triển khai thực tế.

## 12. Quy tắc chọn scope theo tình huống

| Tình huống | Scope thường phù hợp | Vì sao |
| --- | --- | --- |
| Code ứng dụng import type của thư viện (ví dụ SLF4J API) | `compile` | Compiler cần API, runtime cũng thường cần thư viện |
| PostgreSQL driver được framework/JDBC nạp lúc chạy, code chính không import driver | `runtime` | Cần implementation khi chạy, không cần khi biên dịch main |
| Servlet API/container được external Servlet container thực sự cung cấp | `provided` | Biên dịch với API, container chịu trách nhiệm runtime |
| Embedded Tomcat khi đóng WAR truyền thống để deploy vào external Tomcat | `provided` (theo hướng dẫn Boot/WAR) | Tránh mang container nhúng vào `WEB-INF/lib` triển khai ngoài |
| JUnit Jupiter, Mockito, AssertJ chỉ dùng trong test | `test` | Không đưa test API vào classpath mã chính |
| Thư viện vừa được code chính import vừa thực sự cần khi ứng dụng chạy độc lập | Thường `compile` | `runtime` sẽ thiếu trên main compile classpath; `provided` chỉ đúng nếu môi trường cấp đủ |
| Thư viện chỉ có trong Docker/test profile nhưng runtime production dùng cấu hình khác | Phải đánh giá theo runtime thực tế | Scope không thay thế cấu hình profile và quy trình triển khai |

Không có scope “tốt nhất cho mọi project”. Một artifact có thể được khai báo `compile` ở ứng dụng này nhưng `test` ở ứng dụng khác, vì **cách dùng** quyết định classpath cần có.

## 13. Sai lầm phổ biến và cách sửa

### Lỗi 1 — Gắn mọi dependency thành `compile`

Hệ quả: dependencies không cần thiết có thể xuất hiện trên nhiều classpath và được truyền tiếp sang consumer, làm tăng độ phức tạp và đôi khi tăng bề mặt tấn công hoặc chi phí đóng gói. **Sửa:** đánh giá dependency nào chỉ dùng lúc test, runtime hoặc container cung cấp; đặt scope theo contract thật.

### Lỗi 2 — Dùng `runtime` cho thư viện mà mã chính import

Triệu chứng: Maven không tìm thấy package/class ở phase compile. **Sửa:** khi mã `src/main/java` trực tiếp cần type từ artifact, dùng `compile` (hoặc `provided` khi runtime có bên cung cấp); kiểm tra xem đã khai báo đúng artifact nào cung cấp type đó chưa.

### Lỗi 3 — Dùng `provided` để “giảm dung lượng executable JAR Spring Boot”

Triệu chứng: dependency vẫn xuất hiện trong executable JAR/WAR hoặc runtime khác với dự tính. **Sửa:** đọc cấu hình `spring-boot-maven-plugin`, quy tắc `repackage` và các tùy chọn exclusions. Trong Spring Boot, provided dependency thường vẫn được đóng gói theo quy tắc executable archive; đừng dựa vào scope Maven một mình.

### Lỗi 4 — Dùng `test` cho implementation production

Triệu chứng: test pass nhưng `java -jar` gặp lỗi thiếu driver/class/provider khi chạy thật. **Sửa:** kiểm tra chức năng của dependency; nếu ứng dụng production cần nó tại runtime, dùng `runtime` hoặc `compile` phù hợp, sau đó kiểm tra artifact đã đóng gói.

### Lỗi 5 — Dùng `provided` nhưng không có container thực sự cung cấp thư viện

Triệu chứng: local test qua Maven hoạt động, deploy lên server thì lỗi `NoClassDefFoundError`, `ClassNotFoundException` hoặc classloading conflicts. **Sửa:** xác minh container, version API, deployment contract và classpath; tránh giả định JDK chứa thư viện từng có trong Java EE/Jakarta EE.

### Lỗi 6 — Nhầm `dependencyManagement` với `dependencies`

Triệu chứng: POM đã import BOM nhưng lệnh `dependency:tree` không xuất hiện artifact mong muốn. **Sửa:** nếu thực sự cần dùng artifact, khai báo dependency ở `<dependencies>`. BOM thường chỉ cung cấp thông tin quản lý version và những defaults được khai báo; bản thân nó không tự đưa tất cả artifact vào classpath.

### Lỗi 7 — Đoán scope từ dependency bắc cầu

Triệu chứng: dependency C xuất hiện `runtime` dù thư viện B trực tiếp là `compile`. **Sửa:** xem đường từ A → B → C trong `dependency:tree`, bảng kết hợp scopes và các đường khác đến C, dependency mediation/management, exclusions và optional.

## 14. Bài tập vận dụng

**Bài 1.** Mã chính dùng `java.sql.Connection` và `DriverManager`, còn PostgreSQL driver chỉ được nạp theo JDBC URL lúc chạy. Chọn scope nào cho driver?  
**Đáp án:** thường là `runtime`, vì code chính biên dịch dựa trên API `java.sql` có sẵn trong JDK, nhưng runtime cần driver. Nếu code import trực tiếp API riêng của PostgreSQL driver thì xem lại `compile`.

**Bài 2.** Dự án dùng Mockito chỉ trong `src/test/java`. Chọn scope nào?  
**Đáp án:** `test`, vì production code không cần API Mockito.

**Bài 3.** Một thư viện có `provided`. Test pass có chứng minh production runtime sẽ có nó không?  
**Đáp án:** **Không**. Test classpath có dependency provided, còn Maven runtime classpath tiêu chuẩn không có. Cần xác nhận container/runtime cung cấp và kiểm tra artifact đóng gói cụ thể.

**Bài 4.** Với Spring Boot executable WAR đã chạy `repackage`, dependency embedded Tomcat `provided` có thể nằm ở đâu?  
**Đáp án:** `WEB-INF/lib-provided` theo quy tắc WAR layout của Spring Boot Maven Plugin; điều này giúp WAR vẫn chạy bằng `java -jar` khi cần, đồng thời tránh conflict với container ngoài.

**Bài 5.** Một dependency `compile` kéo theo dependency con `runtime`. Dependency con có scope hiệu dụng gì theo đường đó?  
**Đáp án:** `runtime`; không tự trở thành `compile` chỉ vì parent là compile.

**Bài 6.** POM import Spring Boot BOM nhưng không khai báo một driver cụ thể trong `<dependencies>`. Driver tự có trên classpath không?  
**Đáp án:** **Không chỉ vì import BOM**; cần dependency được khai báo trực tiếp hoặc được kéo vào qua một đường transitive hợp lệ.

## 15. Checklist trước khi chốt `pom.xml`

- [ ] Với từng dependency, xác định **source sử dụng**: `src/main` hay `src/test`.
- [ ] Xác định có cần type của dependency khi biên dịch mã chính hay chỉ cần implementation runtime.
- [ ] Nếu dùng `provided`, biết rõ **ai cung cấp nó khi chạy**, đúng phiên bản và đúng môi trường.
- [ ] Với Spring Boot executable artifact, đã kiểm tra quy tắc `repackage` trước khi kết luận dependency nào sẽ được đóng gói.
- [ ] Với WAR triển khai container ngoài, đã xác minh servlet API và embedded container không xung đột.
- [ ] Đã phân biệt dependency được khai báo thực tế với dependency chỉ xuất hiện trong BOM/`dependencyManagement`.
- [ ] Đã xem `dependency:tree` để kiểm chứng effective scope và đường phụ thuộc bắc cầu khi có nghi vấn.
- [ ] Đã chạy test, build và một đường chạy gần production để phát hiện thiếu dependency runtime.

## Tài liệu chính thức

- Maven — Introduction to the Dependency Mechanism: https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html
- Maven — POM Reference (`dependencies` và `dependencyManagement`): https://maven.apache.org/pom.html
- Maven — Maven Dependencies và scope: https://maven.apache.org/repositories/dependencies.html
- Apache Maven Dependency Plugin — dependency tree: https://maven.apache.org/plugins/maven-dependency-plugin/tree-mojo.html
- Spring Boot Maven Plugin — Packaging Executable Archives: https://docs.spring.io/spring-boot/maven-plugin/packaging.html
- Spring Boot — Traditional Deployment: https://docs.spring.io/spring-boot/how-to/deployment/traditional-deployment.html

**Điểm cần nhớ:** `compile` cho mã chính và runtime, `runtime` cho implementation chỉ cần khi chạy, `provided` cho API được môi trường đích cung cấp và `test` cho kiểm thử. Luôn đối chiếu **classpath do Maven giải quyết** với **nội dung artifact do Spring Boot plugin đóng gói** trước khi kết luận thư viện sẽ có mặt hay vắng mặt lúc triển khai.