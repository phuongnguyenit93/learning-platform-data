# Kiểm tra phụ thuộc thừa hoặc thiếu bằng Maven dependency:analyze

> Chủ đề: **Build Tool Maven** · Nhóm kiến thức: **Khai báo phụ thuộc**.

## 1. Tại sao phải phân tích dependencies khi Maven vẫn build được?

Maven cho phép dependency kéo theo những thư viện mà nó cần (*transitive dependencies*). Nhờ đó, ứng dụng có thể biên dịch dù trong `pom.xml` không liệt kê mọi JAR xuất hiện trên classpath. Cơ chế này tiện lợi nhưng đôi khi che giấu sai sót:

- Ứng dụng **dùng trực tiếp class của thư viện B** mà POM chỉ khai báo A; B tình cờ được A kéo vào. Khi A nâng cấp và không còn cần B, ứng dụng đột ngột không biên dịch.
- POM còn **khai báo thư viện C** sau khi mã đã ngừng sử dụng nó. Classpath trở nên khó quản lý, có thể kéo thêm transitive dependencies không cần thiết.
- Một số thư viện **được dùng ở runtime** qua reflection, Java ServiceLoader, annotation processor hoặc framework. Nếu chỉ dựa trên bytecode, công cụ phân tích có thể tưởng nhầm chúng không được dùng.

Goal **`dependency:analyze`** của **Maven Dependency Plugin** giúp phát hiện hai kiểu sai sót đầu tiên. Tuy nhiên, nó tạo ra **bằng chứng cần điều tra**, không phải lệnh xóa phụ thuộc tự động.

Bài này dùng **Maven 3.x, Java 17+ và Maven Dependency Plugin 3.11.0**; các phiên bản dependency của ví dụ được chọn cụ thể để bạn tái hiện cảnh báo. Mục tiêu là:

1. Hiểu sự khác nhau giữa `Used declared`, `Used undeclared` và `Unused declared`.
2. Chạy `dependency:analyze`, giải thích cảnh báo từ **phân tích bytecode**, không nhầm với `dependency:tree`.
3. Viết một dự án Java 17 biên dịch được nhưng có **dependency thiếu khai báo trực tiếp** và **dependency dư khai báo**.
4. Sửa POM an toàn, phân biệt dùng lúc compile/test/runtime và tránh xóa nhầm provider được tải động.
5. Bind `analyze-only` vào `verify` và bật `failOnWarning` để tạo quality gate trong CI.
6. Biết khi nào phải dùng ngoại lệ có kiểm chứng thay vì ignore hàng loạt warnings.

## 2. Direct dependency, transitive dependency và dependencyManagement

Một dependency được khai báo trực tiếp như sau:

~~~xml
<dependency>
    <groupId>org.apache.commons</groupId>
    <artifactId>commons-text</artifactId>
    <version>1.12.0</version>
</dependency>
~~~

Đoạn trên là **fragment** trong `<dependencies>` của một Maven POM. `commons-text:1.12.0` có dependency tới `org.apache.commons:commons-lang3:3.14.0`; vì vậy project dùng `commons-text` thường cũng nhận `commons-lang3` trên classpath thông qua dependency resolution.

~~~text
org.example:dependency-analysis-demo:jar:1.0.0
  |
  +-- org.apache.commons:commons-text:jar:1.12.0:compile
  |     |
  |     \-- org.apache.commons:commons-lang3:jar:3.14.0:compile
  |
  \-- org.apache.commons:commons-collections4:jar:4.4:compile
~~~

Sơ đồ đã giản lược để tập trung vào ba artifact của bài thực hành. `commons-text` và `commons-collections4` là **trực tiếp**; `commons-lang3` được kéo **chuyển tiếp** qua `commons-text`.

Nếu mã của project chỉ gọi API `StringEscapeUtils` thuộc `commons-text`, thì chưa cần direct declaration `commons-lang3` chỉ vì nó có mặt trong cây. Nhưng nếu mã project **import/call `org.apache.commons.lang3.StringUtils`**, `commons-lang3` đã trở thành dependency API **trực tiếp** và nên được khai báo rõ ràng.

**Khác biệt quan trọng:** `<dependencyManagement>` (kể cả BOM) quản lý phiên bản/scope của dependencies khi chúng được khai báo, nhưng **không tự thêm** JAR vào classpath. Khi module trực tiếp dùng API của B, bạn cần `<dependency>` ở module đó; nếu version đã được parent/BOM quản lý thì có thể không ghi lại `<version>` trong declaration.

### 2.1. Scope nào phù hợp?

| Scope | Ý nghĩa thực tế | Ví dụ |
| --- | --- | --- |
| `compile` (mặc định) | Cần khi biên dịch và chạy mã chính | Thư viện API gọi trực tiếp từ `src/main/java` |
| `provided` | Cần compile nhưng môi trường triển khai cung cấp runtime | Servlet API của container |
| `runtime` | Không cần để compile mã chính; implementation cần khi chạy | JDBC driver được chọn động |
| `test` | Cần cho mã hoặc framework test | JUnit, Mockito, AssertJ |
| `system` | Trỏ JAR trên máy qua `systemPath` | Ít portable, tránh nếu có thể |
| `import` | Import BOM (type `pom`) trong `dependencyManagement` | Quản lý versions |

Không đổi tất cả sang `compile` chỉ để tránh warnings. Không đổi một dependency thành `runtime` chỉ vì code compile tình cờ có API ấy transitively. Scope phải khớp **thời điểm và hình thức dùng thật** của ứng dụng.

## 3. Maven Dependency Plugin và ba nhóm kết quả

Goal cụ thể:

~~~text
org.apache.maven.plugins:maven-dependency-plugin:3.11.0:analyze
~~~

Chạy trên dự án có `pom.xml`:

~~~bash
mvn dependency:analyze
~~~

Hoặc gọi đủ tọa độ khi muốn cố định version plugin:

~~~bash
mvn org.apache.maven.plugins:maven-dependency-plugin:3.11.0:analyze
~~~

**Theo tài liệu plugin 3.11.0**, `dependency:analyze` được thiết kế để chạy độc lập. Goal này **tự chạy lifecycle đến `test-compile`** trước khi kiểm tra, nhằm có bytecode của main/test classes. Nó dùng Maven Dependency Analyzer để đối chiếu **các lớp được bytecode tham chiếu** với dependency declarations và resolved artifacts.

Các nhóm thường gặp:

| Nhóm | Cách hiểu đúng | Hành động |
| --- | --- | --- |
| `Used and declared` | Mã dùng artifact và nó đã được khai báo | Giữ, kiểm tra scope và version |
| `Used but undeclared` | Mã dùng artifact nhưng nó không được khai báo trực tiếp | Thường **thêm direct dependency** |
| `Unused but declared` | Khai báo trực tiếp nhưng analyzer không thấy mã dùng nó | **Điều tra** rồi mới xóa hoặc giữ có lý do |
| Non-test scoped, test-only usage | Dependency chỉ dùng trong test nhưng scope có thể quá rộng | Kiểm tra đổi `test` hoặc ngoại lệ có lý do |

Output ví dụ của hai nhóm cảnh báo:

~~~text
[WARNING] Used undeclared dependencies found:
[WARNING]    org.apache.commons:commons-lang3:jar:3.14.0:compile
[WARNING] Unused declared dependencies found:
[WARNING]    org.apache.commons:commons-collections4:jar:4.4:compile
~~~

Đây là **mẫu các dòng chính**, không phải nguyên văn toàn bộ output Maven. Số phiên bản/đường dẫn có thể khác nếu project thật sử dụng dependencyManagement, conflict mediation hoặc exclusions.

Mặc định `failOnWarning=false`; vì vậy **có warnings vẫn có thể BUILD SUCCESS**. Muốn chặn CI, phải cấu hình nghiêm ngặt sau khi xử lý những cảnh báo thực và false positives.

### 3.1. Đừng nhầm analyze với tree

- `dependency:tree` cho biết **dependency nào được resolve và đến từ đường đi nào**; tree không kiểm tra API có thực sự được bytecode dùng không.
- `dependency:analyze` so sánh **mức độ sử dụng được bytecode phát hiện** với declarations; nó không tự thay POM.
- `dependency:analyze-only` phân tích tương tự nhưng **không chạy lại `test-compile`**; dùng khi bind vào lifecycle.
- `dependency:analyze-dep-mgt` tìm vấn đề giữa resolved dependencies và `dependencyManagement`, không phải công cụ phân loại used/unused.
- `dependency:analyze-duplicate` kiểm tra declarations trùng, không chứng minh một JAR được dùng.
- `dependency:analyze-report` tạo báo cáo site; thích hợp khi cần artifact báo cáo theo dự án.

## 4. Ví dụ Java 17 đầy đủ: cả thiếu lẫn thừa dependency

Dự án ví dụ **cố tình thiết kế POM chưa tối ưu**, nhưng vẫn biên dịch được:

1. `commons-text:1.12.0`: khai báo và dùng.
2. `commons-lang3:3.14.0`: mã **dùng trực tiếp** nhưng POM **chưa khai báo**; Maven tải transitively.
3. `commons-collections4:4.4`: POM khai báo nhưng mã **không dùng**.

Thông tin `commons-text:1.12.0 → commons-lang3:3.14.0` được xác nhận từ Maven Central POM của bản phát hành đó. Đây là những **version cố định phục vụ thí nghiệm**, không phải lời khuyên dùng nguyên các version này cho production thay vì bản đã được nhóm duyệt.

### 4.1. Cấu trúc thư mục

~~~text
dependency-analysis-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── org/
                └── example/
                    └── App.java
~~~

Máy cần JDK 17+ và Maven 3.x; lần chạy đầu có thể cần mạng tải plugin/dependencies.

### 4.2. File pom.xml — bản ban đầu có cảnh báo

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>org.example</groupId>
    <artifactId>dependency-analysis-demo</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.apache.commons</groupId>
            <artifactId>commons-text</artifactId>
            <version>1.12.0</version>
        </dependency>

        <dependency>
            <groupId>org.apache.commons</groupId>
            <artifactId>commons-collections4</artifactId>
            <version>4.4</version>
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
                <artifactId>maven-dependency-plugin</artifactId>
                <version>3.11.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Điểm sai **có chủ đích**: thiếu direct dependency `commons-lang3` và dư direct dependency `commons-collections4`.

POM này có thể compile khi `commons-text` còn kéo theo `commons-lang3`. Tuy nhiên, dựa vào dependency chuyển tiếp như vậy không phải hợp đồng dependency tốt: một lần nâng cấp `commons-text` có thể bỏ `commons-lang3`, làm project tự nhiên lỗi dù mã `App.java` không đổi.

### 4.3. File src/main/java/org/example/App.java

~~~java
package org.example;

import org.apache.commons.lang3.StringUtils;
import org.apache.commons.text.StringEscapeUtils;

public final class App {
    private App() {
    }

    public static void main(String[] args) {
        String escaped =
                StringEscapeUtils.escapeHtml4("<b>Hello & Java</b>");
        String upper = StringUtils.upperCase("maven");

        System.out.println("escaped=" + escaped);
        System.out.println("upper=" + upper);
    }
}
~~~

`StringEscapeUtils` thuộc `commons-text`. `StringUtils` thuộc `commons-lang3`. **Không có API nào của `commons-collections4` được tham chiếu**. Mã Java hợp lệ cho JDK 17 (thực tế cũng tương thích một số JDK cũ hơn).

### 4.4. Build và chạy chương trình

Tại thư mục có `pom.xml`:

~~~bash
java -version
javac -version
mvn -version
mvn clean compile
~~~

Để chạy `App` với dependency classpath đã được Maven resolve, dùng Maven Exec Plugin trực tiếp (được ghim version; không cần sửa POM):

~~~bash
mvn -q compile org.codehaus.mojo:exec-maven-plugin:3.5.1:java -Dexec.mainClass=org.example.App
~~~

**Stdout chính xác của chương trình** (bỏ qua Maven/plugin logs nếu có):

~~~text
escaped=&lt;b&gt;Hello &amp; Java&lt;/b&gt;
upper=MAVEN
~~~

Tại sao không dùng ngay `java -cp target/classes org.example.App`? Vì Maven compiler thường đặt **code của project** ở `target/classes`, trong khi JAR dependencies nằm ở Maven repository. `java -cp target/classes` không tự thêm JAR ngoài. Maven Exec Plugin sử dụng project dependency classpath để chạy main class.

Tương tự, JAR tạo bởi `mvn package` trong ví dụ này là **thin JAR** thông thường, không tự nhúng toàn bộ dependencies và không khai báo Main-Class. Không mặc định dùng `java -jar` như thể đó là executable fat JAR.

### 4.5. Truy xuất cây dependency

~~~bash
mvn dependency:tree
mvn dependency:tree -Dincludes=org.apache.commons:commons-lang3
~~~

Đối với POM mẫu, cây cho thấy `commons-lang3:3.14.0` ở dưới `commons-text:1.12.0`, dù `App.java` đang import class của `commons-lang3` trực tiếp.

Đây chính là **rủi ro phụ thuộc bắc cầu**: compile hiện tại OK nhờ cấu hình của thư viện khác, nhưng source của module bạn đang có một sự phụ thuộc chưa được mô tả trong `pom.xml`.

### 4.6. Chạy analyzer và đọc cảnh báo

~~~bash
mvn dependency:analyze
~~~

Hoặc:

~~~bash
mvn org.apache.maven.plugins:maven-dependency-plugin:3.11.0:analyze
~~~

Kỳ vọng hai cảnh báo chính:

~~~text
[WARNING] Used undeclared dependencies found:
[WARNING]    org.apache.commons:commons-lang3:jar:3.14.0:compile

[WARNING] Unused declared dependencies found:
[WARNING]    org.apache.commons:commons-collections4:jar:4.4:compile
~~~

Các dòng trên là **trích mẫu của loại output** tương ứng, không phải toàn bộ log; phiên bản/tên artifact chỉ giữ đúng cho dự án mẫu. Nếu project thật có những phụ thuộc được tải do profile hoặc dependencyManagement khác, hãy đọc version thực tế từ resolved graph.

Giải nghĩa: `commons-lang3` được **used undeclared** vì bytecode của `App` tham chiếu `StringUtils` nhưng POM không khai báo nó trực tiếp. `commons-collections4` được **unused declared** vì nó được khai báo nhưng không có dấu vết sử dụng nào từ mã ví dụ.

## 5. Sửa POM: thêm đúng, xóa đúng

Trong file `pom.xml` ban đầu, **thay thế toàn bộ block `<dependencies>...</dependencies>`** bằng:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.apache.commons</groupId>
        <artifactId>commons-text</artifactId>
        <version>1.12.0</version>
    </dependency>

    <dependency>
        <groupId>org.apache.commons</groupId>
        <artifactId>commons-lang3</artifactId>
        <version>3.14.0</version>
    </dependency>
</dependencies>
~~~

**Phạm vi chỉnh sửa:** đây là fragment sửa file POM đầy đủ ở mục 4.2. Giữ nguyên thông tin project, compiler plugin và dependency plugin. Thực hiện:

1. Giữ `commons-text` vì mã dùng `StringEscapeUtils`.
2. Thêm `commons-lang3` làm **direct dependency** vì mã dùng `StringUtils`.
3. Xóa `commons-collections4` vì bài thực hành không có source, test hay cấu hình runtime cần thư viện ấy.
4. Giữ scope `compile` mặc định cho hai dependency gọi từ mã chính.
5. Không cần gắn exclusion để “ẩn” `commons-lang3`: nó vẫn có thể là transitive dependency của `commons-text`, nhưng Maven merge graph để lấy artifact phù hợp. Chúng ta đang **nói rõ phụ thuộc trực tiếp**, không thêm một bản JAR trùng vào classpath theo cách cơ học.

Kiểm tra sau sửa:

~~~bash
mvn clean test-compile
mvn dependency:tree
mvn dependency:analyze
~~~

**Kỳ vọng:** không còn cảnh báo `Used undeclared` cho `commons-lang3` và `Unused declared` cho `commons-collections4`. Đừng lấy một câu log như `No dependency problems found` làm chuẩn so sánh cố định cho mọi plugin version; điều quan trọng là nhóm cảnh báo có nguyên nhân tương ứng đã được giải quyết.

Chạy lại main:

~~~bash
mvn -q compile org.codehaus.mojo:exec-maven-plugin:3.5.1:java -Dexec.mainClass=org.example.App
~~~

Stdout **không đổi**:

~~~text
escaped=&lt;b&gt;Hello &amp; Java&lt;/b&gt;
upper=MAVEN
~~~

Đây mới là quy trình đầy đủ: xác minh POM **và** hành vi chương trình. Ở hệ thống thực, còn cần unit tests, integration tests và smoke tests của ứng dụng để đảm bảo thư viện bị xóa không phải một runtime provider.

## 6. Ba nhãn kết quả: cần làm gì trong code review?

### 6.1. Used and declared

Đây là tình huống code tham chiếu class của dependency đã khai báo. Thường nên giữ nó và kiểm tra scope, version. Để có thêm thông tin về dependencies đang dùng:

~~~bash
mvn dependency:analyze -Dverbose=true
~~~

`verbose` có thể in những dependency analyzer đánh giá là used. Kết quả không phải danh sách import Java, mà là kết luận từ analyzer.

### 6.2. Used but undeclared

Phần lớn trường hợp giải quyết bằng **thêm direct dependency**. Khi xử lý:

- Đọc class/package nào project trực tiếp dùng.
- Dùng `dependency:tree` để truy ra artifact chứa class và tại sao nó có mặt.
- Khai báo dependency trực tiếp ở **module sử dụng nó** với scope thích hợp.
- Nếu version được BOM/parent quản lý, tham chiếu version quản lý thay vì tự ghi version khác.
- Chạy lại clean compile/test và analyzer.

**Tránh mẹo sai:** cấu hình `ignoredUsedUndeclaredDependencies` chỉ để tắt cảnh báo của một API project thật sự import trực tiếp, hoặc đổi dependency một cách ngẫu nhiên để version warning biến mất.

### 6.3. Unused but declared

Không được xem đây là lệnh “xóa ngay”. Analyzer bytecode có thể không thấy:

- Class được nạp bằng tên chuỗi qua `Class.forName(...)` hoặc framework reflection.
- Java `ServiceLoader` và providers từ `META-INF/services`.
- JDBC driver, logging backend, transport provider chọn theo config.
- Annotation có retention `SOURCE` và một số tool chạy ở compile time.
- Hằng số được compiler inline, không còn class reference trong bytecode.
- Test engines được test runner nạp động, generated code và cấu hình runtime.

Trước khi xóa, hãy trả lời: dependency được khai báo vì lý do nào? Có config/XML/properties/service descriptor nào yêu cầu không? Mã có chạy ở môi trường deploy hay CI path khác không? Bỏ JAR có làm test khởi động, JDBC connection, logging hoặc plugin discovery lỗi không?

Nếu thật sự thừa, xóa trong POM rồi chạy bộ test đủ bao phủ. Nếu **thật sự cần ở runtime** nhưng analyzer không thấy, giữ dependency và ghi rõ ngoại lệ hẹp (mục 8).

## 7. dependency:analyze và dependency:analyze-only khác nhau thế nào?

Theo tài liệu Maven Dependency Plugin:

| Goal | Có tự chạy đến `test-compile`? | Cách dùng |
| --- | --- | --- |
| `dependency:analyze` | **Có**, goal tự thực hiện lifecycle trước | Chạy **standalone** qua CLI |
| `dependency:analyze-only` | **Không**, cần bytecode đã được tạo | Bind vào `verify` trong POM/CI |

Để tự chạy phân tích sau khi sửa POM:

~~~bash
mvn dependency:analyze
~~~

Nếu bạn chạy riêng `mvn dependency:analyze-only` trong một project vừa `mvn clean` mà chưa compile, dữ liệu có thể không đầy đủ hoặc goal không có gì để phân tích. Nếu mục đích là tích hợp vào build, **bind `analyze-only` sau các phase biên dịch**, ví dụ tại `verify`.

### 7.1. Cấu hình plugin vào verify

**Thay thế** phần plugin `maven-dependency-plugin` hiện có trong `<build><plugins>` bằng fragment sau:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-dependency-plugin</artifactId>
    <version>3.11.0</version>

    <executions>
        <execution>
            <id>check-dependency-declarations</id>
            <phase>verify</phase>
            <goals>
                <goal>analyze-only</goal>
            </goals>
        </execution>
    </executions>

    <configuration>
        <failOnWarning>true</failOnWarning>
    </configuration>
</plugin>
~~~

Fragment không phải một `pom.xml` mới; tránh khai báo **hai plugin cùng groupId:artifactId** trong một danh sách `<plugins>`. Nó chạy analysis khi Maven đi đến phase `verify`, sau các phase compile/test-compile/package theo default lifecycle.

Chạy:

~~~bash
mvn clean verify
~~~

Với bản POM đã **sửa đúng** ở mục 5, quality gate kỳ vọng **không có dependency warning**. Nếu khôi phục POM cố tình sai ở mục 4.2, `failOnWarning=true` khiến `verify` thất bại khi analyzer phát hiện warnings.

**Lưu ý:** `mvn test` chưa đi đến `verify`, nên execution này không chạy. Muốn CI chặn dựa trên analysis, pipeline phải chạy phase phù hợp, ví dụ `mvn clean verify`.

### 7.2. Fail khi warning mà không sửa POM

Muốn thử strict mode trực tiếp:

~~~bash
mvn dependency:analyze -DfailOnWarning=true
~~~

`failOnWarning` có default `false`, vì vậy tham số trên biến một warning thành lỗi goal. Đây là **policy kiểm soát chất lượng**, không phải bằng chứng Maven compiler thực sự cần tất cả JAR tại runtime.

## 8. Runtime dependencies và các ngoại lệ có chủ đích

Maven Dependency Analyzer mặc định làm việc ở **bytecode level**, vì thế có trường hợp declared-but-unused là false positive. Mục tiêu là **giữ đúng thư viện bắt buộc**, không che khuất mọi cảnh báo.

### 8.1. Ví dụ ServiceLoader hoặc JDBC driver

Ứng dụng có thể dùng:

~~~java
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.SQLException;

public final class DatabaseProbe {
    public static Connection open(String url,
                                  String user,
                                  String password)
            throws SQLException {
        return DriverManager.getConnection(url, user, password);
    }
}
~~~

Đây là **fragment minh họa một lớp Java** (không phải chương trình tự chạy nếu không có database). Code chỉ tham chiếu Java SQL API; driver có thể được tìm động qua service discovery. Nếu ứng dụng dùng PostgreSQL, JAR `org.postgresql:postgresql` có thể cần tại runtime nhưng analyzer không thấy code gọi trực tiếp class của driver.

Với nhu cầu thật, khai báo driver phù hợp, thường dùng `runtime` scope nếu mã không import API của driver. Một ví dụ dependency:

~~~xml
<dependency>
    <groupId>org.postgresql</groupId>
    <artifactId>postgresql</artifactId>
    <version>42.7.4</version>
    <scope>runtime</scope>
</dependency>
~~~

Đây là **fragment minh họa**; version chỉ dùng để chỉ cấu trúc POM, project thật chọn phiên bản được duyệt. Việc chạy cần database URL, credentials và service thật; ví dụ không giả định có server PostgreSQL trên máy bạn.

### 8.2. usedDependencies: buộc analyzer tính là used

Nếu driver đã được **xác minh sử dụng ở runtime** nhưng analyzer báo unused:

~~~xml
<configuration>
    <usedDependencies>
        <usedDependency>org.postgresql:postgresql</usedDependency>
    </usedDependencies>
</configuration>
~~~

Đoạn trên đặt trong **maven-dependency-plugin configuration**; không phải nơi khai báo dependency của ứng dụng. Tham số `usedDependencies` dùng cặp `groupId:artifactId`. Nó **chỉ báo analyzer cách đánh giá**, không tự thêm JAR vào classpath, không thiết lập scope và không chứng minh runtime đúng.

### 8.3. ignoredUnusedDeclaredDependencies: bỏ qua đúng warning

Một lựa chọn khác là bỏ qua riêng cảnh báo unused-declared của provider đã xác minh:

~~~xml
<configuration>
    <ignoredUnusedDeclaredDependencies>
        <ignoredUnusedDeclaredDependency>org.postgresql:postgresql</ignoredUnusedDeclaredDependency>
    </ignoredUnusedDeclaredDependencies>
</configuration>
~~~

Các fragment `<configuration>` này là **hai lựa chọn riêng**, không dán thành hai block configuration trùng trong cùng plugin. Nếu thực sự kết hợp nhiều tham số, gộp chúng vào một cấu hình.

### 8.4. Những tham số khác phải dùng cẩn trọng

| Tham số | Tác dụng | Rủi ro nếu dùng bừa |
| --- | --- | --- |
| `usedDependencies` | Ép G:A được tính là used | Che dependency không còn dùng thật |
| `ignoredUnusedDeclaredDependencies` | Bỏ qua unused-declared của artifact chỉ định | Giữ JAR thừa mãi mà không ai kiểm tra |
| `ignoredUsedUndeclaredDependencies` | Bỏ cảnh báo used-undeclared cụ thể | Có thể duy trì phụ thuộc trực tiếp chưa khai báo |
| `ignoredNonTestScopedDependencies` | Bỏ cảnh báo non-test-scoped nhưng chỉ dùng trong test | Giữ dependency với scope rộng hơn cần thiết |
| `ignoredDependencies` | Bỏ nhiều loại warning cho artifact/filter | Che các nhóm lỗi khác nhau cùng lúc |
| `ignoreUnusedRuntime` | Bỏ unused warnings cho runtime-scope | Bỏ sót runtime dependencies thật sự không cần |
| `ignoreNonCompile` | Bỏ unused warnings cho runtime/provided/test/system | Rất rộng, hạn chế tín hiệu của analyzer |
| `failOnWarning` | Fail build nếu warning | Nên áp sau khi phân loại false positives |
| `verbose` | In thêm thông tin dependencies được dùng | Chỉ hỗ trợ chẩn đoán |

Cú pháp ignore filter của plugin hỗ trợ các phần `groupId:artifactId:type:version` với wildcard tùy chọn; chỉ ignore một artifact chính xác là cách dễ hiểu và an toàn hơn ignore mọi JAR trong group. Nếu một thư viện chỉ dùng bởi reflection/SPI hoặc một annotation `SOURCE`, hãy ghi chú lý do ngay bên cạnh cấu hình ngoại lệ và bổ sung test để phòng hồi quy.

## 9. Cảnh báo chỉ dùng trong test và quản lý scope

Phiên bản plugin hiện đại có thể phát hiện **dependency không test-scoped nhưng chỉ xuất hiện trong test bytecode**. Ví dụ nếu chỉ test code dùng JUnit/AssertJ, đặt scope `test` là hợp lý:

~~~xml
<dependency>
    <groupId>org.junit.jupiter</groupId>
    <artifactId>junit-jupiter</artifactId>
    <version>5.11.4</version>
    <scope>test</scope>
</dependency>
~~~

Đây là fragment ví dụ; để chạy JUnit 5 thật cần test source và Surefire/JUnit engine tương thích. Không dùng fragment này trong project runnable ở mục 4 nên không làm thay đổi kết quả warnings của bài chính.

Với dependency `compile` chỉ dùng trong unit tests, thay scope thành `test` **khi đúng bản chất**. Nếu một API được dùng trong cả main/test, giữ scope phục vụ mã chính. Với API do container cung cấp, cân nhắc `provided`. Với implementation nạp runtime qua ServiceLoader, cân nhắc `runtime`.

**Không đổi scope để làm vừa lòng tool mà bỏ qua thực tế runtime.** Scope thay đổi classpath của các phase và việc đóng gói; phải chạy lại integration tests/smoke tests.

## 10. Các lệnh bổ trợ để điều tra dependency graph

### 10.1. Tree để xác định vì sao JAR có mặt

~~~bash
mvn dependency:tree
mvn dependency:tree -Dincludes=org.apache.commons:commons-lang3
~~~

Câu hỏi đúng: `commons-lang3` đến từ dependency nào và version nào được chọn? Nếu có xung đột version, exclusions hoặc dependencyManagement, tree giúp xác định đường đi. Nó **không** kết luận có thể xóa artifact.

### 10.2. Phân tích dependencyManagement

~~~bash
mvn dependency:analyze-dep-mgt
~~~

Goal này xem những điểm không khớp giữa resolved dependencies và quản lý versions; khác `dependency:analyze` vốn dùng bytecode.

### 10.3. Tìm khai báo trùng

~~~bash
mvn dependency:analyze-duplicate
~~~

Goal này tìm duplicates trong `<dependencies>` / `<dependencyManagement>`. Hai khai báo trùng không giống “unused declared”; phân biệt triệu chứng trước khi sửa.

### 10.4. Project nhiều module

Ở reactor multi-module, kết luận phải được đưa ra **cho module đang có bytecode được phân tích**. Module `core` có thể dùng `commons-lang3`, nhưng module `web` có thể không; không cần copy direct dependency vào mọi module chỉ vì chúng dùng chung parent.

- Parent `packaging=pom` thường không có bytecode, nên analyzer có thể bỏ qua (plugin có danh sách ignored packagings).
- `<dependencyManagement>` trong parent **không tự làm mọi module dùng artifact**.
- Với build ở root, xác nhận module có test/source đầy đủ đã chạy trước analysis.
- Sử dụng `-pl` / `-am` khi cần build đúng module và các module mà nó phụ thuộc.
- Không giải quyết một warning ở module này bằng cách thêm dependency vào một module khác rồi dựa vào reactor classpath của IDE.

## 11. Khi analyzer không thấy usage: cần nhìn cả source và runtime

### 11.1. Reflection

~~~java
Class<?> pluginType =
        Class.forName("org.example.plugins.FormatProvider");
Object provider = pluginType.getDeclaredConstructor().newInstance();
~~~

Đây chỉ là fragment, không phải chương trình đầy đủ; class đó phải tồn tại lúc chạy. Bytecode lưu **string class name**, không nhất thiết có type reference tĩnh tới JAR của implementation. Vì vậy analyzer có thể coi JAR provider là unused dù runtime thật cần.

### 11.2. ServiceLoader và config metadata

`ServiceLoader` đọc metadata service provider; nhiều framework cũng tìm plugin/implementation qua annotations, tên cấu hình hoặc scanning. Nơi sử dụng có thể là `META-INF/services` hoặc XML/property files, không phải lời gọi class tĩnh từ source chính. Kết hợp kiểm tra resource/config/deployment, không chỉ xem phần `import` trong Java.

### 11.3. Annotation retention và compile-time constants

Annotation với `RetentionPolicy.SOURCE` bị bỏ khỏi bytecode; plugin phân tích bytecode có thể không thấy nó dù source đang dùng. Tương tự, Java compiler có thể inline public static final compile-time constants, khiến dấu vết tham chiếu đến thư viện cung cấp constant biến mất.

Với annotation processor, kapt hoặc generated code, cần chắc chắn phase tạo source/compile đã hoàn tất. `dependency:analyze` không đồng nghĩa chạy tất cả nhánh build đặc biệt nếu bạn chưa kích hoạt profile/plugin phù hợp.

### 11.4. Không phải công cụ scan bảo mật hoặc license

`dependency:analyze` **không** phát hiện CVE, license conflict, dependency freshness hay mọi runtime classloader problem. Đó là các câu hỏi cần công cụ/kiểm thử khác. “No dependency problems found” trong analyzer không bảo đảm thư viện an toàn hoặc build reproducible.

## 12. Quy trình xử lý warnings đúng cách trong nhóm

1. **Cố định môi trường:** dùng Maven/JDK version và profiles giống CI; kiểm tra `mvn -version`.
2. **Build sạch:** `mvn clean test-compile` hoặc chạy trực tiếp `dependency:analyze`; bảo đảm generated source/test đã được sinh.
3. **Thu thập warnings theo module:** phân biệt used undeclared, unused declared và test scope warnings.
4. **Với Used undeclared:** xác định class nguồn, tìm artifact qua tree, khai báo direct dependency với scope/version phù hợp.
5. **Với Unused declared:** tìm use qua source, reflection, SPI, config, annotation, runtime; chỉ xóa khi đã kiểm chứng.
6. **Kiểm tra phiên bản:** BOM, dependencyManagement và nearest-wins có thể quyết định version thực tế.
7. **Chạy test sau sửa:** unit tests, integration tests, smoke tests cho các nhánh runtime/load động.
8. **Chạy lại analyzer:** đảm bảo warning tương ứng biến mất, không phát sinh classpath regressions.
9. **Bật quality gate:** bind `analyze-only` tại `verify`, dùng `failOnWarning=true` khi baseline đã được xử lý.
10. **Ghi chú ngoại lệ:** chỉ ignore artifact thực sự cần thiết, giải thích tại sao analyzer không thể thấy usage.

Nếu project lâu năm có hàng chục warnings, có thể tách hai giai đoạn: ban đầu thu thập/report mà **chưa fail CI**, sau khi làm sạch mới bật strict gate. Đừng chặn build quá sớm rồi dùng wildcard ignore toàn bộ để “làm xanh” dashboard.

## 13. Lỗi thường gặp và cách khắc phục

| Biểu hiện | Nguyên nhân | Khắc phục |
| --- | --- | --- |
| Compile thành công, báo Used undeclared | API được dùng từ transitive dependency | Khai báo dependency trực tiếp tại module |
| `commons-lang3` trong tree nhưng không có trong POM | Bị kéo theo qua `commons-text` | Thêm direct declaration khi source import API |
| Báo Unused declared cho JDBC driver | Driver dùng qua SPI/reflection | Xác minh runtime; giữ và ignore hẹp nếu cần |
| Báo Unused declared cho annotation | SOURCE retention/bytecode không thấy | Kiểm tra processor, source và giải thích ngoại lệ |
| Warning nhưng BUILD SUCCESS | `failOnWarning=false` mặc định | Bật strict mode nếu đã kiểm soát false positives |
| `analyze-only` chạy độc lập cho kết quả trống/lạ | Chưa compile hoặc output cũ | Bind `verify` hoặc chạy `test-compile` trước |
| Build chậm khi bind `analyze` | Goal tự fork lifecycle đến test-compile | Dùng `analyze-only` trong lifecycle |
| Xóa dependency unused rồi runtime ClassNotFoundException | Implementation chỉ được tải động | Hoàn nguyên, thêm runtime tests và ngoại lệ có mục tiêu |
| `java -cp target/classes` không tìm thấy Commons classes | Thiếu external JARs trên runtime classpath | Chạy qua Maven Exec goal hoặc tạo classpath đúng |
| POM có dependencyManagement nhưng Used undeclared | Management không tự khai báo dependency | Thêm dependency vào `<dependencies>` |
| CI và IDE ra warnings khác nhau | Khác profile/bytecode/source roots/classpath | Kiểm chứng Maven từ clean checkout |
| Sửa scope nhưng test/runtime lỗi | Chọn scope theo warning, không theo use thật | Xác định compile/test/runtime needs và chạy tests |
| Multi-module nhận kết luận khác nhau | Từng module có source và POM riêng | Phân tích theo module; đừng copy khai báo mù |
| Tree cho version khác bản kỳ vọng | BOM, mediation hoặc exclusions | Đọc resolved tree/effective POM |
| Đổi version upstream làm thiếu dependency | Đang dựa vào API transitively | Khai báo direct dependency ngay khi có use |
| QA fail dù code compile tốt | Bật failOnWarning và còn warnings | Điều tra, sửa khai báo hoặc ngoại lệ hẹp |
| Dùng ignore wildcard rộng làm tất cả xanh | Tắt tín hiệu phân tích thật | Thu hẹp ignore và ghi lý do |
| `mvn test` không chạy dependency gate | Gate bound ở `verify` | Chạy `mvn clean verify` |

### 13.1. Gợi ý debug

~~~bash
mvn -version
mvn clean test-compile
mvn dependency:tree
mvn dependency:analyze -Dverbose=true
mvn help:effective-pom -Doutput=effective-pom.xml
~~~

Khi cần tìm nguyên nhân sâu hơn:

~~~bash
mvn -X dependency:analyze
~~~

`-X` in nhiều log và có thể chứa cấu hình nhạy cảm; cân nhắc trước khi chia sẻ toàn bộ output công khai.

## 14. Tự kiểm tra kiến thức

**1.** `App.java` dùng `StringUtils` từ `commons-lang3`. POM chỉ khai báo `commons-text`, compile vẫn OK. Sai ở đâu?  
**Đáp án:** Có `Used undeclared`: code trực tiếp dùng API của artifact chưa khai báo, dù nó được resolve transitively.

**2.** `dependency:tree` thấy một JAR. Điều đó có chứng minh source dùng JAR không?  
**Đáp án:** Không. Tree mô tả resolved graph, không phân tích bytecode usage.

**3.** Plugin báo unused cho một JDBC driver. Có thể xóa ngay?  
**Đáp án:** Không. Driver có thể được tìm qua SPI, phải test runtime.

**4.** Vì sao `dependency:analyze` có thể chạy trên project chưa có `target/classes`?  
**Đáp án:** Goal này tự chạy lifecycle đến `test-compile` trước khi phân tích.

**5.** Khi bind analysis ở phase `verify`, nên dùng goal nào?  
**Đáp án:** `analyze-only` để không fork lại `test-compile`.

**6.** Làm sao khiến CI fail khi có warning?  
**Đáp án:** Đặt `failOnWarning=true` trong Maven Dependency Plugin hoặc truyền parameter thích hợp.

**7.** BOM đã quản lý version `commons-lang3`. Module dùng `StringUtils` có còn cần `<dependency>` không?  
**Đáp án:** Có. BOM quản lý version, không tự thêm JAR trực tiếp vào module.

**8.** Vì sao annotation `RetentionPolicy.SOURCE` có thể bị báo unused?  
**Đáp án:** Nó không tồn tại trong class bytecode mà analyzer quét.

**9.** `usedDependencies` có tự thêm JDBC driver vào classpath?  
**Đáp án:** Không. Nó chỉ chỉnh kết luận của analyzer, còn runtime dependency phải được khai báo thật.

**10.** Sau khi dependency:analyze không còn warnings, có chắc production chạy được không?  
**Đáp án:** Không. Phải có tests, kiểm tra SPI/reflection/config, packaging và deploy runtime.

## 15. Checklist hoàn thành thực hành

- [ ] JDK 17+ và Maven chạy đúng; xác nhận `mvn -version`.
- [ ] POM ban đầu có `commons-text:1.12.0` và `commons-collections4:4.4`, chưa khai báo direct `commons-lang3`.
- [ ] File `App.java` import `StringEscapeUtils` và `StringUtils`, không import collections4.
- [ ] `mvn clean compile` thành công; chạy Exec Maven Plugin in đúng `escaped=...` và `upper=MAVEN`.
- [ ] `mvn dependency:tree` cho thấy `commons-lang3:3.14.0` đến từ `commons-text`.
- [ ] `mvn dependency:analyze` phát hiện cả `Used undeclared` và `Unused declared`.
- [ ] Sửa POM: thêm `commons-lang3` trực tiếp, xóa `commons-collections4` không dùng.
- [ ] Chạy lại analyze và ứng dụng, kết quả đúng và cảnh báo mục tiêu biến mất.
- [ ] Hiểu `dependency:analyze` khác `dependency:analyze-only` và `dependency:tree`.
- [ ] Nếu bật CI gate, `verify` chạy `analyze-only` với `failOnWarning=true`.
- [ ] Không xóa dependency được tải động chỉ dựa trên bytecode; có integration tests và ignore hẹp nếu cần.

## 16. Tài liệu tham khảo

1. [Apache Maven Dependency Plugin 3.11.0 — dependency:analyze](https://maven.apache.org/plugins/maven-dependency-plugin/analyze-mojo.html)
2. [Apache Maven Dependency Plugin — Usage](https://maven.apache.org/plugins/maven-dependency-plugin/usage.html)
3. [Apache Maven Dependency Plugin — Excluding Dependencies from Analysis](https://maven.apache.org/plugins/maven-dependency-plugin/examples/exclude-dependencies-from-dependency-analysis.html)
4. [Apache Maven Dependency Plugin — Fail the Build on Warnings](https://maven.apache.org/plugins/maven-dependency-plugin/examples/failing-the-build-on-dependency-analysis-warnings.html)
5. [Apache Maven — Dependency Mechanism](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html)
6. [Maven Central — commons-text 1.12.0 POM](https://central.sonatype.com/artifact/org.apache.commons/commons-text/1.12.0)
7. [Maven Central — commons-collections4 4.4](https://central.sonatype.com/artifact/org.apache.commons/commons-collections4/4.4)
8. [MojoHaus Exec Maven Plugin — exec:java](https://www.mojohaus.org/exec-maven-plugin/java-mojo.html)
