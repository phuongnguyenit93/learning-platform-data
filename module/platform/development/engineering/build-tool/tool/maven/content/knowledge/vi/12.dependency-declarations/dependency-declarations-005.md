# Khai báo trực tiếp thư viện mà mã nguồn đang sử dụng trong Maven

## 1. Mục tiêu: dependency trực tiếp là một hợp đồng rõ ràng của dự án

Khi mã Java trong `src/main/java` hoặc `src/test/java` sử dụng class, interface, annotation hay API từ một thư viện bên ngoài JDK, dự án Maven cần một **dependency** phù hợp để compiler/test/runtime tìm được thư viện đó. Nguyên tắc thiết kế quan trọng là:

> **Thư viện nào được mã nguồn của module dùng trực tiếp thì module nên khai báo dependency đó trực tiếp trong `<dependencies>`**, thay vì dựa tình cờ vào dependency bắc cầu (transitive dependency) của một thư viện khác.

Nguyên tắc này không có nghĩa khai báo mọi JAR xuất hiện trong dependency tree. Maven tự giải quyết thư viện phụ cần thiết cho những dependency đã khai báo. Điều cần làm là phân biệt **API mà mã nguồn dự án tự sử dụng** với **API được sử dụng bên trong một thư viện khác**.

Lợi ích chính:

1. **Chính xác:** POM mô tả đúng API mà module phụ thuộc, không giấu dependency thực tế sau thư viện trung gian.
2. **Ổn định khi nâng cấp:** Nếu thư viện trung gian bỏ hoặc thay đổi một transitive dependency, build của module ít bị vỡ hơn vì dependency trực tiếp vẫn tồn tại.
3. **Dễ kiểm toán:** Reviewer nhìn `pom.xml` là biết module dùng những thư viện cấp một nào, phiên bản và scope nào.
4. **Kiểm soát scope và version:** Project chủ động chọn API cần có lúc compile, test hoặc runtime, thay vì hoàn toàn phụ thuộc vào graph bắc cầu.
5. **Dễ phân tích lỗi:** `dependency:tree` và `dependency:analyze` cho kết quả gần với mục đích thiết kế hơn.

Quy tắc trên được khuyến nghị ngay trong tài liệu [Maven Dependency Mechanism](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html).

## 2. Dependency trực tiếp và transitive dependency khác gì nhau?

Giả sử `app` khai báo thư viện `library-b`, còn POM của `library-b` khai báo `library-c`:

~~~text
app (project Maven của bạn)
  |
  +-- library-b           <-- DIRECT: app khai báo trong <dependencies>
        |
        +-- library-c     <-- TRANSITIVE: Maven lấy từ POM của library-b
~~~

Nếu `app` chỉ gọi class trong `library-b`, không tự import/call API của `library-c`, thường chỉ cần khai báo `library-b`. Maven sẽ giải quyết `library-c` theo dependency graph và scope.

Nhưng nếu file `App.java` có:

~~~java
import org.example.libraryc.SomeClass;
~~~

thì `app` **đang sử dụng library-c trực tiếp**. Cho dù hiện tại compiler vẫn tìm thấy `SomeClass` do transitive dependency, bạn nên thêm `library-c` vào `<dependencies>` của chính `app`:

~~~text
app
  |
  +-- library-b           <-- DIRECT
  |     |
  |     +-- library-c     <-- TRANSITIVE qua library-b
  |
  +-- library-c           <-- ALSO DIRECT: vì source của app dùng API của C
~~~

Maven sẽ hòa giải graph và chọn artifact/version hiệu lực; sơ đồ cho thấy **hai quan hệ khai báo** chứ không có nghĩa classpath chứa hai bản JAR cùng tên.

Nếu sau này `library-b` ngừng phụ thuộc vào `library-c`, mã nguồn `app` vẫn có đường dependency được công khai. Ngược lại, nếu dự án chỉ dựa vào transitive dependency cũ, việc nâng `library-b` có thể làm lỗi compile `package ... does not exist` dù bạn không sửa `App.java`.

**Không được hiểu nhầm:** Cơ chế dependency bắc cầu của Maven là tính năng đúng và cần thiết; chúng ta chỉ tránh **dựa vào nó để truy cập API mà mã nguồn của chính dự án đang dùng**.

## 3. Một dependency trực tiếp được khai báo ở đâu?

Các dependency thông thường thuộc mục `<project><dependencies>` trong `pom.xml`:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.apache.commons</groupId>
        <artifactId>commons-lang3</artifactId>
        <version>3.21.0</version>
        <scope>compile</scope>
    </dependency>
</dependencies>
~~~

Đây là một **mảnh XML** đặt bên trong POM hợp lệ, không phải toàn bộ POM. `commons-lang3` cung cấp những class như `org.apache.commons.lang3.StringUtils`. Phiên bản `3.21.0` là một phiên bản phát hành cụ thể để học; phiên bản sử dụng trong dự án thật cần được kiểm tra tương thích và chính sách cập nhật của nhóm. `compile` là scope mặc định, nên trong trường hợp này có thể bỏ dòng `<scope>compile</scope>` mà không đổi ý nghĩa.

Ý nghĩa các trường:

| Trường | Vai trò | Khi nào khai báo? |
| --- | --- | --- |
| `groupId` | Nhóm phát hành artifact, ví dụ `org.apache.commons`. | Cần cho dependency. |
| `artifactId` | Tên artifact, ví dụ `commons-lang3`. | Cần cho dependency. |
| `version` | Phiên bản artifact được giải quyết. | Cần giá trị hiệu lực; có thể bỏ trong khai báo dependency nếu được quản lý trong `dependencyManagement`/BOM. |
| `scope` | Quyết định classpath và khả năng transitive. | Bỏ qua khi dùng mặc định `compile`. |
| `type` | Loại artifact, thường mặc định `jar`. | Dùng khi cần artifact kiểu khác. |
| `classifier` | Phân biệt biến thể artifact cùng tọa độ, ví dụ `tests`. | Chỉ khi thư viện được phát hành với classifier và dự án thật sự cần. |
| `optional` | Quy định tính tùy chọn với dependency transitively được tiêu thụ bởi dự án khác. | Chủ yếu quan trọng khi **phát hành thư viện**. |
| `exclusions` | Chặn một dependency bắc cầu không mong muốn ở nhánh cụ thể. | Dùng có chủ đích sau khi kiểm tra graph; không thay thế việc khai báo API sử dụng. |

**Package Java không phải Maven coordinates.** Tên import `org.apache.commons.lang3.StringUtils` **không** đồng nghĩa `groupId=org.apache.commons.lang3`. Phải tìm tọa độ dependency từ tài liệu thư viện, POM phát hành hoặc repository tin cậy.

Không đặt thư viện của ứng dụng trong `<build><plugins>`: plugin Maven là công cụ build, không phải dependency Java của mã ứng dụng. Cũng không đặt dependency chính của ứng dụng trong `<plugin><dependencies>`, vì phần đó chỉ làm thay đổi **classpath của plugin**.

## 4. Chọn đúng scope cho nơi mã nguồn sử dụng thư viện

Maven có các scope chính, quyết định dependency tham gia classpath của dự án:

| Scope | Trường hợp hợp lý | Classpath thông thường |
| --- | --- | --- |
| `compile` (mặc định) | `src/main/java` trực tiếp import/call API của thư viện. | Compile, runtime và test; có thể lan truyền transitively theo quy tắc Maven. |
| `test` | `src/test/java` dùng JUnit, Mockito hoặc test utility mà main code không dùng. | Test compile và test run; không vào classpath compile/runtime của ứng dụng thông thường. |
| `runtime` | Ứng dụng cần implementation khi chạy nhưng không trực tiếp dùng API đó ở compile (ví dụ một JDBC driver được load lúc runtime). | Runtime và test; không nằm trong compile classpath. |
| `provided` | Main code cần API khi compile nhưng runtime/container sẽ cấp thư viện đó (ví dụ servlet API trong một số container). | Compile và test, không thuộc runtime classpath do Maven tạo cho project; không lan truyền như compile dependency. |
| `system` | JAR lấy từ đường dẫn máy cục bộ. | Maven hỗ trợ nhưng **không khuyến nghị** vì khó tái lập build; thay bằng private artifact repository. |
| `import` | Nhập bảng quản lý version từ một BOM POM. | **Chỉ dùng cho dependency `type=pom` trong `dependencyManagement`**, không phải scope dành cho mã nguồn dùng thư viện. |

Các scope còn tác động đến **transitivity**; bảng trên tóm tắt classpath của chính module. Không nên suy luận rằng mọi dependency có scope `compile` trong một thư viện sẽ luôn giữ nguyên scope khi xuất hiện gián tiếp trong project khác: Maven có quy tắc kết hợp scope.

Ví dụ module có mã main dùng `StringUtils` và test dùng `@Test` của JUnit:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.apache.commons</groupId>
        <artifactId>commons-lang3</artifactId>
        <version>3.21.0</version>
    </dependency>
    <dependency>
        <groupId>org.junit.jupiter</groupId>
        <artifactId>junit-jupiter</artifactId>
        <version>5.11.4</version>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

Cả hai là **dependency trực tiếp** của module, nhưng chúng phục vụ **hai tập mã nguồn khác nhau** và được chọn scope khác nhau.

**Lưu ý:** Nếu mã main import `org.junit.jupiter.api.Test`, lỗi không được sửa bằng cách thay test scope thành compile một cách máy móc. Hãy kiểm tra xem annotation/test code đã được đặt đúng `src/test/java` chưa.

## 5. Bài toán phiên bản: dependency có thể được quản lý mà vẫn cần khai báo trực tiếp

Trong tổ chức đa module, parent POM hoặc BOM thường quản lý phiên bản tập trung. Đây là giải pháp tốt để tránh copy `<version>` nhiều lần; nhưng nó **không** có nghĩa module con tự sử dụng tất cả dependency đã được quản lý.

Trong parent POM:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.apache.commons</groupId>
            <artifactId>commons-lang3</artifactId>
            <version>3.21.0</version>
        </dependency>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>5.11.4</version>
            <scope>test</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

Trong child có sử dụng hai thư viện:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.apache.commons</groupId>
        <artifactId>commons-lang3</artifactId>
    </dependency>
    <dependency>
        <groupId>org.junit.jupiter</groupId>
        <artifactId>junit-jupiter</artifactId>
    </dependency>
</dependencies>
~~~

Khi child kế thừa đúng dependency management từ parent, các khai báo trên nhận version tương ứng; JUnit cũng có thể nhận scope `test` từ dependency management. **Mấu chốt:** Child vẫn khai báo trong `<dependencies>` để thể hiện **mình thật sự dùng** hai thư viện. Một mục chỉ xuất hiện trong `<dependencyManagement>` không tự thêm JAR vào classpath.

Nếu child tự chỉ định version/scope cụ thể, Maven dùng các quy tắc merge/override tương ứng. Do đó phải xem `help:effective-pom` hoặc `dependency:tree` để biết phiên bản cuối thực sự được chọn, nhất là khi nhiều parent/profile/BOM cùng tác động.

### BOM import không phải parent dependency

Một BOM (*Bill of Materials*) là POM chuyên cung cấp các bản ghi `dependencyManagement`. Cú pháp nhập một BOM:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.example.platform</groupId>
            <artifactId>platform-bom</artifactId>
            <version>1.0.0</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

Đây là **mảnh cấu hình minh họa**; tọa độ `org.example.platform:platform-bom:1.0.0` chỉ là tên ví dụ, không khẳng định repository công khai có artifact ấy. BOM nhập version management, **không tự thêm dependency để dùng** và không đưa build/plugins của BOM vào POM như một parent. Nếu một module import API từ một thư viện do BOM quản lý, module vẫn cần dependency trực tiếp ở `<dependencies>`.

## 6. Ví dụ hoàn chỉnh: Java 17 dùng Apache Commons Lang trực tiếp

Ví dụ sau có thể xây dựng bằng Maven trên JDK 17+, gồm:

- Một thư viện ứng dụng **direct**: `org.apache.commons:commons-lang3` để mã trong `src/main/java` import `StringUtils`.
- Một thư viện test **direct**: `org.junit.jupiter:junit-jupiter` cho mã trong `src/test/java` import `Test`/`Assertions`.
- Compiler Plugin và Surefire Plugin có phiên bản cố định, để hành vi build/test rõ ràng.
- Lệnh chạy ứng dụng có **classpath chứa dependency**; không chỉ dùng riêng `target/classes` khi mã cần JAR ngoài JDK.

Cấu trúc:

~~~text
direct-deps-demo/
├── pom.xml
└── src/
    ├── main/
    │   └── java/
    │       └── org/example/TextApp.java
    └── test/
        └── java/
            └── org/example/TextAppTest.java
~~~

### 6.1. Tệp pom.xml hoàn chỉnh

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>org.example</groupId>
    <artifactId>direct-deps-demo</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <!-- Main source imports org.apache.commons.lang3.StringUtils -->
        <dependency>
            <groupId>org.apache.commons</groupId>
            <artifactId>commons-lang3</artifactId>
            <version>3.21.0</version>
        </dependency>

        <!-- Test source imports org.junit.jupiter.api.Test/Assertions -->
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
            </plugin>
        </plugins>
    </build>
</project>
~~~

Dự án này **không cần khai báo Maven JAR Plugin riêng** để hiểu direct dependency; packaging `jar` dùng lifecycle Maven tiêu chuẩn. Khi chạy `package`, JAR chính thường chứa class/resource do dự án biên dịch, **không mặc định gộp tất cả thư viện ngoài vào bên trong**. Đó là lý do phần chạy chương trình cần classpath có Commons Lang.

### 6.2. Java source: TextApp.java

Tệp `src/main/java/org/example/TextApp.java`:

~~~java
package org.example;

import java.util.Locale;
import org.apache.commons.lang3.StringUtils;

public final class TextApp {
    private TextApp() {
    }

    public static String normalize(String input) {
        if (StringUtils.isBlank(input)) {
            return "(empty)";
        }
        String trimmed = StringUtils.trim(input);
        return StringUtils.capitalize(trimmed.toLowerCase(Locale.ROOT));
    }

    public static void main(String[] args) {
        System.out.println("label=" + normalize("  MAVEN  "));
        System.out.println("blank=" + normalize("   "));
    }
}
~~~

Giải thích:

- `java.util.Locale` thuộc JDK, **không cần dependency Maven riêng**.
- `org.apache.commons.lang3.StringUtils` thuộc Commons Lang, nên `commons-lang3` cần được **khai báo trực tiếp** trong POM.
- `StringUtils.isBlank("   ")` trả `true`, nên nhánh rỗng trả `(empty)`.
- Chuỗi `"  MAVEN  "` được trim → `MAVEN`, đổi về chữ thường bằng `Locale.ROOT` → `maven`, capitalize → `Maven`.

Mã dùng API thực tế của Commons Lang, Java 17 và JDK standard library, không phải một class minh họa chưa tồn tại.

### 6.3. Test source: TextAppTest.java

Tệp `src/test/java/org/example/TextAppTest.java`:

~~~java
package org.example;

import static org.junit.jupiter.api.Assertions.assertEquals;
import org.junit.jupiter.api.Test;

class TextAppTest {
    @Test
    void normalizesTextUsingCommonsLang() {
        assertEquals("Maven", TextApp.normalize("  MAVEN  "));
        assertEquals("(empty)", TextApp.normalize("   "));
    }
}
~~~

Test này trực tiếp dùng `org.junit.jupiter.api.Test` và `Assertions.assertEquals`, nên JUnit phải có **dependency trực tiếp scope test**. Mã test có thể truy cập `TextApp` và Commons Lang vì test classpath cũng nhận compile dependencies của dự án.

### 6.4. Build và chạy test

Trên Linux/macOS, ở thư mục chứa `pom.xml`:

~~~bash
mvn -B -ntp clean verify
~~~

Nếu dependency/plugin có sẵn ở repository và các điều kiện môi trường phù hợp, Maven biên dịch class, chạy **1 test method** rồi đóng gói JAR. Các tệp quan trọng:

~~~text
target/
├── classes/org/example/TextApp.class
├── test-classes/org/example/TextAppTest.class
├── surefire-reports/
│   ├── TEST-org.example.TextAppTest.xml
│   └── org.example.TextAppTest.txt
└── direct-deps-demo-1.0.0.jar
~~~

Đây là cây đầu ra **rút gọn**; Maven có thể tạo các thư mục/tệp khác. Kết quả chạy test là log Maven nên không gán một stdout cố định cho toàn bộ lệnh `mvn`.

### 6.5. Chạy main đúng cách: đưa dependency vào classpath

**Đừng chỉ chạy**:

~~~bash
java -cp target/classes org.example.TextApp
~~~

Lệnh này có thể tạo `NoClassDefFoundError: org/apache/commons/lang3/StringUtils` vì JVM chạy `TextApp` chưa có Commons Lang JAR trong classpath, dù `mvn compile` trước đó thành công.

Có thể dùng Maven Dependency Plugin để copy các JAR cần cho runtime vào `target/dependency`:

~~~bash
mvn -B -ntp org.apache.maven.plugins:maven-dependency-plugin:3.8.1:copy-dependencies -DincludeScope=runtime -DoutputDirectory=target/dependency
~~~

Với goal `copy-dependencies`, bộ lọc `includeScope=runtime` bao gồm dependency scope **runtime và compile**, không lấy các thư viện chỉ dành cho test/provided. Đây là cú pháp của Maven Dependency Plugin; các tùy chọn chỉ có tác dụng với goal đó. Lần đầu có thể phải tải plugin.

Trên **Bash/Zsh**:

~~~bash
java -cp "target/classes:target/dependency/*" org.example.TextApp
~~~

Trên **PowerShell hoặc CMD ở Windows**:

~~~powershell
java -cp "target\classes;target\dependency\*" org.example.TextApp
~~~

Trong classpath, `:` là ký tự phân tách entry trên Linux/macOS, còn `;` được dùng trên Windows. `*` trong một thành phần classpath được Java launcher dùng để mở rộng các JAR trong thư mục; quote toàn classpath để shell không tự phân tích dấu đặc biệt. Đừng nhầm wildcard classpath với việc Maven tự tạo fat JAR.

**Stdout chính xác của riêng lệnh `java`**, khi build và copy dependency thành công:

~~~text
label=Maven
blank=(empty)
~~~

Chương trình là độc lập ở mức mã nguồn và chạy được khi dependency ngoài JDK có trên classpath. Kết quả trên không yêu cầu `java -jar` vì POM không khai báo `Main-Class` trong manifest; `java -cp ... org.example.TextApp` là cách chạy có đủ thông tin classpath.

## 7. Tại sao không nên “xài ké” transitive dependency để import class?

Giả sử dự án dùng một thư viện JSON. API xử lý đối tượng JSON ở một artifact, còn API parser/streaming nằm ở artifact khác. Khi thư viện đối tượng kéo theo thư viện parser, mã nguồn của dự án có thể tạm thời import cả hai mà chỉ khai báo artifact đối tượng.

Đó là tình huống nguy hiểm nếu **mã của bạn trực tiếp gọi API parser**:

~~~text
app
  +-- json-object-lib          (direct)
        +-- json-parser-lib    (transitive)
~~~

Nếu `App.java` import một class thuộc `json-parser-lib`, hãy khai báo `json-parser-lib` trực tiếp. Thư viện object có thể thay phiên bản parser, chọn bản khác hoặc dừng sử dụng nó trong tương lai. Tên ở sơ đồ chỉ minh họa; muốn áp dụng với Jackson, Gson hoặc thư viện khác, phải tra **tọa độ artifact và tương thích phiên bản thực tế**, không suy từ tên package.

Khi thay đổi graph, Maven có thể dùng **dependency mediation** để chọn một phiên bản giữa nhiều đường dẫn. Một dependency trực tiếp thường có đường dẫn ngắn hơn transitive, do đó cũng giúp bạn thể hiện ý định version rõ ràng hơn. Nhưng điều này **không** thay thế quản lý version tập trung, kiểm tra binary compatibility hoặc dependency convergence.

Sử dụng `mvn dependency:tree` để quan sát:

~~~bash
mvn dependency:tree
mvn dependency:tree -Dincludes=org.apache.commons:commons-lang3
~~~

`dependency:tree` cho bạn thấy đường đi và scope/phiên bản hiệu lực. Nó **không tự chứng minh mã nguồn có dùng class của dependency đó hay không**; cần kết hợp đọc import, mã nguồn và công cụ phân tích.

## 8. Dùng dependency:analyze để phát hiện “used undeclared” và “unused declared”

Maven Dependency Plugin có goal `dependency:analyze`; nó kiểm tra bytecode của project để tìm các nhóm:

- **Used and declared**: mã dự án dùng class của thư viện và POM khai báo dependency tương ứng.
- **Used but undeclared**: mã dự án dùng class từ một artifact có trên classpath nhưng POM **không khai báo trực tiếp**; thường do dùng API của transitive dependency.
- **Unused but declared**: có dependency khai báo nhưng phân tích bytecode không thấy mã dùng trực tiếp.

Lệnh:

~~~bash
mvn -B -ntp org.apache.maven.plugins:maven-dependency-plugin:3.8.1:analyze
~~~

Goal này sẽ thực hiện các phase cần thiết đến `test-compile` trước khi phân tích. Khi muốn gắn phân tích vào lifecycle `verify` đã có bước compile, cân nhắc goal `dependency:analyze-only` thay vì chạy `analyze` như một execution tùy tiện.

Ví dụ đầu ra **minh họa dạng cảnh báo**, không phải stdout bảo đảm từ dự án ở mục 6:

~~~text
[WARNING] Used undeclared dependencies found:
[WARNING]    example:json-parser-lib:jar:1.0.0:compile
~~~

Ý nghĩa: có thể mã của bạn đã dùng class từ `json-parser-lib` thông qua một dependency bắc cầu. Cần xác minh artifact thực sự chứa class, sau đó **thêm dependency trực tiếp** với version/scope hợp lý và chạy lại build.

### Phân tích bytecode không phải bằng chứng tuyệt đối

`dependency:analyze` có giới hạn vì phần lớn dựa trên class references trong bytecode. Nó có thể báo sai hoặc thiếu trong các trường hợp:

- Library chỉ được nạp bằng reflection hoặc `Class.forName`.
- JDBC driver, Java `ServiceLoader`/SPI hoặc plugin runtime được chọn bằng tên cấu hình.
- Annotation processor/code generation hoặc framework tạo class động.
- Dependency cần cho runtime nhưng mã không có tham chiếu compile trực tiếp.
- Artifact cung cấp resource, native code hoặc chức năng kích hoạt từ cấu hình thay vì import Java.
- Một số dạng metadata/test helper không được analyzer nhận diện hết.

Vì vậy **không xóa dependency chỉ vì xuất hiện “unused declared”**. Trước khi xóa, kiểm tra runtime behavior, test tích hợp, resource/configuration và chính sách deployment. Có thể cấu hình analyzer cho các ngoại lệ có cơ sở nhưng không biến nó thành công cụ bỏ qua mọi cảnh báo.

## 9. Các tình huống cần trực tiếp khai báo dù không có import rõ ràng

Nguyên tắc “import thì khai báo trực tiếp” là tiêu chí dễ thấy, nhưng **không phải điều kiện cần duy nhất**. Có những dependency ứng dụng thực sự cần ở runtime dù mã Java không import API cụ thể của chúng.

### 9.1. JDBC driver

Mã có thể chỉ dùng `java.sql.Connection` và `DriverManager` từ JDK. Nhưng nếu hệ thống kết nối tới PostgreSQL qua JDBC, driver PostgreSQL là một runtime implementation phải được cung cấp bằng dependency hoặc container/classpath thích hợp:

~~~xml
<dependency>
    <groupId>org.postgresql</groupId>
    <artifactId>postgresql</artifactId>
    <version>42.7.4</version>
    <scope>runtime</scope>
</dependency>
~~~

Đây là **ví dụ tọa độ và phiên bản cụ thể**, không hàm ý đây là phiên bản nên dùng cho hệ thống production hiện tại. Hãy kiểm tra advisory và khả năng tương thích. Dự án không trực tiếp import class driver mà vẫn cần JAR ở runtime để `DriverManager` tìm provider qua cơ chế phù hợp.

### 9.2. Logging provider

Mã ứng dụng có thể import API `org.slf4j.Logger` và khai báo trực tiếp `slf4j-api`. Backend logging (ví dụ implementation được chọn cho môi trường chạy) có thể là một dependency runtime, không cần source code import backend class. Đừng xóa provider chỉ vì công cụ bytecode báo “unused”.

### 9.3. Annotation processor hoặc code generation

Annotation như Lombok, MapStruct, Dagger... có thể yêu cầu processor riêng trong compiler configuration. Không phải mọi processor nên được đưa vào `compile` dependencies không giới hạn; Maven Compiler Plugin có cơ chế cấu hình processor path hoặc processor dependencies tùy phiên bản, và JDK mới có yêu cầu rõ ràng hơn về annotation processing. Phải đọc hướng dẫn của **chính processor và compiler plugin** thay vì suy diễn từ import annotation.

Kết luận: dependency nên được khai báo tường minh khi **mã nguồn hoặc vận hành của module** cần artifact đó, nhưng **scope và cơ chế cung cấp** phải đúng với mục đích.

## 10. Đặt dependency đúng module, không chỉ đúng repository

Trong dự án đa module:

~~~text
root/pom.xml
├── common-utils/pom.xml
│   └── src/main/java/...
└── web-service/pom.xml
    └── src/main/java/...
~~~

Nếu `common-utils` trực tiếp dùng Commons Lang, khai báo `commons-lang3` trong `common-utils/pom.xml`. Nếu `web-service` cũng trực tiếp import `StringUtils`, khai báo Commons Lang trực tiếp trong **`web-service/pom.xml`**, kể cả khi nó có dependency vào `common-utils` và đã thấy Commons Lang transitively.

Một parent POM có thể quản lý version cho tất cả modules:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.apache.commons</groupId>
            <artifactId>commons-lang3</artifactId>
            <version>3.21.0</version>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

Từng module dùng API vẫn khai báo:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.apache.commons</groupId>
        <artifactId>commons-lang3</artifactId>
    </dependency>
</dependencies>
~~~

Việc parent có `<modules>` hoặc cùng reactor **không tự làm mã của module này truy cập được dependency của module kia**. POM inheritance, reactor aggregation và project dependency là **ba mối quan hệ khác nhau**.

Lệnh kiểm tra theo module:

~~~bash
mvn -pl :common-utils dependency:tree
mvn -pl :web-service dependency:tree
mvn -pl :web-service help:effective-pom
~~~

Các tên module là minh họa; muốn chạy thật phải có artifactId và reactor tương ứng. `-pl` chọn project để Maven thao tác. Nếu một module cần build thêm module nó phụ thuộc, có thể dùng `-am` khi thực sự có quan hệ dependency trong reactor.

## 11. Version mediation và đường dẫn ngắn nhất

Khi hai dependency trực tiếp/gián tiếp kéo cùng artifact khác phiên bản, Maven phải chọn phiên bản hiệu lực. Một nguyên tắc trong Maven 3 là **nearest definition**: phiên bản trên đường dependency gần root nhất thường được chọn; nếu cùng độ sâu, thứ tự khai báo có thể quyết định.

Ví dụ khái niệm:

~~~text
app
  |-- lib-a:1.0
  |     \-- shared-lib:1.5
  |
  |-- lib-b:2.0
        \-- shared-lib:2.0
~~~

Hai đường `shared-lib` cùng độ sâu, nên bạn không nên dựa vào thứ tự tình cờ để quyết định API nào được dùng. Nếu mã nguồn `app` **trực tiếp sử dụng shared-lib**, khai báo nó trực tiếp với version mong muốn và kiểm tra tương thích:

~~~xml
<dependency>
    <groupId>org.example</groupId>
    <artifactId>shared-lib</artifactId>
    <version>2.0</version>
</dependency>
~~~

`org.example:shared-lib` trong ví dụ này là **tọa độ giả định** để minh họa mediation, không phải artifact được xác minh trên repository công khai.

**Trực tiếp khai báo không bảo đảm mọi thư viện bắc cầu sẽ tương thích** với version bạn chọn. Nếu `lib-a` chỉ chạy với `shared-lib:1.5`, chọn `2.0` có thể gây `NoSuchMethodError` hoặc lỗi linkage ở runtime. Phải kiểm tra compatibility, test và dependency graph.

`dependencyManagement` có thể giúp ép version transitive theo chính sách dự án, nhưng nó không tự sửa incompatibility. Tránh giải quyết xung đột bằng cách thêm `exclusions` hàng loạt trước khi hiểu dependency path.

## 12. Khi nào dùng exclusions và optional?

### Exclusions

`<exclusions>` dùng để chặn một transitive dependency ở một nhánh cụ thể khi biết rõ nguyên nhân, chẳng hạn một thư viện cũ không tương thích hoặc một implementation không được phép dùng.

~~~xml
<dependency>
    <groupId>org.example</groupId>
    <artifactId>integration-client</artifactId>
    <version>1.0.0</version>
    <exclusions>
        <exclusion>
            <groupId>org.example</groupId>
            <artifactId>legacy-logging</artifactId>
        </exclusion>
    </exclusions>
</dependency>
~~~

Đây là ví dụ tọa độ **giả định**, không phải dependency copy/paste có sẵn trên Maven Central. Exclusion là **theo đường dẫn/nhánh**, không mặc nhiên loại artifact đó khỏi mọi nơi khác trong dependency graph. Sau khi exclude, phải xem lại `dependency:tree` và test runtime. Nếu ứng dụng vẫn cần API/thư viện bị exclude, cần khai báo giải pháp thay thế hoặc version trực tiếp phù hợp.

### Optional

Khi **bạn phát hành một thư viện**, `<optional>true</optional>` trên một dependency của thư viện làm cho dependency đó **không tự lan truyền** sang project tiêu thụ trong một số trường hợp. Project tiêu thụ muốn dùng chức năng bổ sung phải tự thêm dependency cần thiết.

Ví dụ code của consumer trực tiếp dùng một plugin/driver mà dependency upstream đánh dấu optional, consumer cần khai báo **trực tiếp** thư viện đó; không dựa vào việc upstream có tên nó trong POM. Optional không có nghĩa Maven không cần dependency khi build **chính module khai báo nó**.

Đừng dùng `optional` để sửa compile error hoặc cố giảm dung lượng mà không phân tích API public, runtime và tài liệu thư viện. Mục tiêu của bài là hợp đồng phụ thuộc rõ ràng, không phải tối thiểu hóa số dòng XML bằng mọi giá.

## 13. Các lỗi liên quan đến dependency trực tiếp

| Hiện tượng | Nguyên nhân thường gặp | Hướng kiểm tra |
| --- | --- | --- |
| `package org.apache.commons.lang3 does not exist` | Không có dependency Commons Lang phù hợp trên compile classpath, tọa độ/version sai hoặc bị exclude. | Kiểm tra `pom.xml`, `mvn dependency:tree`, scope và repository. |
| `cannot find symbol: StringUtils` | Import sai hoặc dependency chưa được compiler nhìn thấy. | So package với tài liệu thư viện và scope `compile`. |
| Compile thành công nhưng `NoClassDefFoundError` khi chạy Java | JAR ngoài JDK không nằm trên **runtime classpath**. | Copy runtime dependencies hoặc dùng cơ chế chạy/đóng gói có classpath phù hợp. |
| `mvn dependency:tree` thấy thư viện nhưng POM không có dòng khai báo | Thư viện tới từ một dependency bắc cầu. | Nếu source trực tiếp import API đó, thêm direct dependency. |
| `dependency:analyze` báo “used undeclared” | Mã dùng class từ transitive JAR. | Xác minh artifact chứa class, thêm dependency với scope/version phù hợp. |
| `dependency:analyze` báo “unused declared” cho JDBC driver | Runtime load qua ServiceLoader/reflection; bytecode không tham chiếu trực tiếp. | Kiểm tra integration test và dependency runtime trước khi xóa. |
| Test compile lỗi vì JUnit không có | JUnit thiếu `scope=test` hợp lệ hoặc dependency chưa resolve. | Thêm direct JUnit dependency scope test vào đúng module. |
| Main code không import được thư viện `scope=test` | Test dependency không nằm trên main compile classpath. | Chuyển code test về `src/test/java` hoặc xem lại scope thật cần. |
| Version “đúng” nhưng runtime có `NoSuchMethodError` | Dependency mediation chọn version nhị phân không tương thích. | Xem graph đầy đủ, version jar và kiểm tra compatibility. |
| Parent đã quản lý dependency nhưng child vẫn không import được | `dependencyManagement` chỉ quản lý version, chưa tạo dependency. | Thêm dependency vào `<dependencies>` của child. |
| Maven không tải được artifact | Tọa độ sai, repo offline, proxy/auth, repository thiếu artifact. | Xem tọa độ chính xác, kết nối/repository và log resolution. |
| Thêm thư viện vào plugin dependencies mà Java code vẫn lỗi | Chỉ sửa plugin classpath, không phải project classpath. | Đưa dependency của ứng dụng vào `project/dependencies`. |

**Phương pháp chẩn đoán:** xác định class được import thuộc artifact nào → xác định mã nằm ở `src/main` hay `src/test` → kiểm tra POM **của đúng module** → xem scope/version hiệu lực qua dependency tree → chạy lại build sạch → chạy ứng dụng/test với classpath thực tế.

## 14. Quy trình thêm một thư viện mới vào Maven đúng cách

Giả sử một developer muốn dùng một class bên ngoài JDK trong một module:

1. **Xác định class/API thật sự đang dùng**, ví dụ `org.apache.commons.lang3.StringUtils`; đừng đoán artifact từ IDE import suggestion mà không xác minh.
2. **Tra tọa độ Maven chính thức** (groupId/artifactId) từ tài liệu thư viện hoặc repository đáng tin; kiểm tra module/variant đúng, tránh nhầm artifact cũ hay package đổi tên.
3. **Chọn phiên bản được dự án hỗ trợ**. Nếu dùng parent/BOM, kiểm tra version management để tránh khai báo trùng và làm lệch nền tảng.
4. **Khai báo trực tiếp trong `<dependencies>` của module**, chọn scope theo nơi sử dụng: main compile, test, runtime, provided theo ngữ cảnh.
5. **Build sạch và chạy test** với JDK, Maven, plugin versions mà CI dùng; xác nhận không còn lỗi compile và test.
6. **Chạy `dependency:tree`** để xem JAR đã được resolve qua đường nào, version nào, có xung đột hoặc transitive bất ngờ không.
7. **Cân nhắc `dependency:analyze`** để nhận diện used-but-undeclared; điều tra ngoại lệ của analyzer trước khi xóa bất cứ dependency nào.
8. **Kiểm tra chạy ứng dụng thật**: jar thường không tự chứa dependencies; container, server, classpath, Spring Boot repackage, shade hoặc launcher phải có cơ chế cung cấp các JAR cần thiết.
9. **Review license và bảo mật của thư viện** theo quy trình dự án; kiểm tra advisory và cập nhật có kiểm soát, không chỉ chọn bản “mới nhất” theo cảm tính.
10. **Commit POM/khóa phiên bản và mã nguồn**, không commit ngẫu nhiên `~/.m2/repository` hoặc `target/dependency`. CI phải có khả năng lấy lại dependency từ repository phù hợp.

Nếu module ngừng dùng một thư viện, đừng vội xóa direct dependency chỉ vì không còn import Java: xem có cần runtime, SPI, config resource, reflection hoặc test fixtures hay không. Sau khi xác minh đầy đủ, hãy xóa những dependency không còn cần.

## 15. Câu hỏi tự kiểm tra

1. **App trực tiếp import class từ thư viện C, nhưng C đã xuất hiện do B phụ thuộc C; app có nên khai báo C không?**  
   Có. Đây là nguyên tắc direct dependency giúp POM phản ánh API mà source dùng và tránh vỡ build khi B đổi graph.

2. **Mã `src/main/java` dùng `StringUtils`, có thể chỉ khai báo Commons Lang với `scope=test` không?**  
   Không. Test dependency không có trên compile classpath của main code; dùng `compile` hoặc scope khác thật sự phù hợp mục đích.

3. **Parent có `commons-lang3` trong `dependencyManagement`, child có dùng `StringUtils` nhưng không có dependency; đã đủ chưa?**  
   Chưa. Management chỉ quản lý phiên bản; child vẫn phải khai báo direct dependency.

4. **Tại sao `mvn compile` thành công nhưng `java -cp target/classes ...` thất bại?**  
   Vì JVM runtime không được cung cấp Commons Lang JAR. Phải đưa runtime dependencies vào classpath hoặc đóng gói/chạy bằng cơ chế phù hợp.

5. **`dependency:analyze` báo JDBC driver là “unused declared”, có nên xóa ngay?**  
   Không. Driver có thể được nạp động qua ServiceLoader và vẫn bắt buộc ở runtime.

6. **`optional=true` ở một dependency của thư viện upstream có tự làm consumer nhận nó không?**  
   Không. Khi cần chức năng phụ thuộc đó, consumer phải tự quyết định thêm dependency tương ứng.

7. **Cùng parent POM hoặc cùng reactor có khiến mọi module dùng được class/dependency của nhau?**  
   Không. Mỗi module phải khai báo project dependencies và third-party dependencies phù hợp, không suy từ quan hệ aggregation.

8. **Vì sao dùng trực tiếp dependency vẫn cần kiểm tra transitive dependency tree?**  
   Vì mediation/scope/conflict và compatibility của các thư viện bên dưới vẫn có thể ảnh hưởng runtime; direct declaration không bảo đảm đồ thị luôn nhất quán.

## 16. Tài liệu tham khảo

- [Apache Maven — Introduction to the Dependency Mechanism](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html) — direct vs transitive, scopes, optional, exclusions, dependency management.
- [Apache Maven — POM Reference: Dependencies](https://maven.apache.org/pom.html) — cấu trúc `dependencies` và các trường tọa độ.
- [Apache Maven Dependency Plugin — dependency:tree](https://maven.apache.org/plugins/maven-dependency-plugin/tree-mojo.html) — xem dependency graph và scopes.
- [Apache Maven Dependency Plugin — dependency:analyze](https://maven.apache.org/plugins/maven-dependency-plugin/analyze-mojo.html) — tìm used-undeclared và unused-declared, giới hạn phân tích bytecode.
- [Apache Maven Dependency Plugin — dependency:copy-dependencies](https://maven.apache.org/plugins/maven-dependency-plugin/copy-dependencies-mojo.html) — copy runtime JARs để chạy ví dụ.
- [Apache Commons Lang — Release Notes](https://commons.apache.org/proper/commons-lang/changes.html) — thông tin các bản phát hành, Java compatibility.
- [Apache Maven — Guide to Working with Multiple Modules](https://maven.apache.org/guides/mini/guide-multiple-modules.html) — reactor và project dependencies.

**Ghi nhớ:** Maven giúp kéo transitive dependencies, nhưng **module nên khai báo trực tiếp mỗi thư viện mà mã nguồn của nó dùng trực tiếp**. Đặt dependency ở đúng `pom.xml`, scope đúng, version được quản lý minh bạch; dùng `dependency:tree` để xem graph, `dependency:analyze` để phát hiện thiếu/thừa có giới hạn, và kiểm tra runtime classpath để bảo đảm chương trình thật sự chạy được.
