# Phân biệt classpath chính, classpath kiểm thử và classpath plugin trong Maven

## 1. Vì sao Maven có nhiều classpath?

Trong Java, **classpath** là tập các thư mục và tệp JAR mà compiler hoặc JVM dùng để tìm class và resource. Khi một project Maven chạy `compile`, `test`, `package` hoặc một plugin goal, không phải mọi công cụ đều sử dụng cùng một tập JAR.

Cần phân biệt bốn ngữ cảnh:

- **Main compile classpath:** thư viện dùng để biên dịch mã chính trong `src/main/java`.
- **Main runtime classpath:** thư viện và bytecode dùng để chạy ứng dụng sau khi build; tập này có thể khác tập compile.
- **Test compile/runtime classpath:** thư viện cho `src/test/java` và cho framework chạy test; thường chứa mã chính, mã test và dependency chỉ dành cho test.
- **Plugin class realm/classpath:** các JAR để Maven plugin **tự hoạt động** (Compiler, Surefire, Resources, Shade...) trong Maven; không phải classpath Java source của project.

Ba nhóm trong đề bài là **chính, kiểm thử, plugin**. Main compile và main runtime được tách riêng trong bài vì thiếu hiểu biết về sự khác biệt này dẫn tới một lỗi phổ biến: **Maven compile thành công nhưng lệnh `java` chạy ứng dụng lại báo thiếu class**.

Một nguyên tắc khác: Dependency khai báo dưới `<project><dependencies>` phục vụ code của project theo scope, còn dependency khai báo dưới `<plugin><dependencies>` được thêm vào môi trường của **plugin tương ứng**. Không đổi qua lại hai nơi như thể chúng tương đương.

## 2. Bản đồ thư mục và các classpath

Với layout Maven thông thường:

~~~text
project/
├── pom.xml
├── src/
│   ├── main/
│   │   ├── java/
│   │   └── resources/
│   └── test/
│       ├── java/
│       └── resources/
└── target/
    ├── classes/                 # class/resource chính sau build
    ├── test-classes/            # class/resource test
    ├── surefire-reports/        # kết quả test nếu Surefire thực thi
    └── project-1.0.0.jar        # artifact JAR chính nếu đóng gói JAR
~~~

Các classpath nhìn theo nhiệm vụ:

~~~text
MAIN COMPILE
  project dependencies thuộc compile/provided (và system legacy)
  --> biên dịch src/main/java --> target/classes

MAIN RUNTIME
  target/classes hoặc JAR chính
  + project dependencies thuộc compile/runtime
  --> chạy ứng dụng bằng JVM

TEST COMPILE
  target/classes
  + project dependencies phù hợp cho test (compile/provided/runtime/test)
  --> biên dịch src/test/java --> target/test-classes

TEST RUNTIME (ví dụ Surefire)
  target/test-classes
  + target/classes
  + project dependencies dành cho test
  + những phần tử bổ sung được plugin cấu hình
  --> chạy unit test

PLUGIN CLASS REALM
  JAR của plugin
  + thư viện plugin tự phụ thuộc
  + <plugin><dependencies> nếu khai báo
  + các Maven API/class realm imports thích hợp
  --> plugin thực thi goal của nó
~~~

Đây là sơ đồ khái niệm, không phải mô phỏng tuyệt đối thứ tự nạp class ở mọi plugin. **Plugin có thể yêu cầu Maven cung cấp project compile/test/runtime classpath rồi khởi tạo compiler hoặc JVM con**, nhưng cơ chế ấy khác với việc các JAR project tự động nằm trong chính class realm của plugin.

## 3. Scope của project dependencies: bảng cần nhớ

`<scope>` đặt ở một dependency của project điều khiển vị trí nó xuất hiện. Các scope cơ bản:

| Project dependency scope | Main compile | Main runtime | Test compile/runtime | Giải thích |
| --- | --- | --- | --- | --- |
| `compile` (mặc định) | Có | Có | Có | Main code import API trực tiếp, ví dụ Commons Lang. |
| `provided` | Có | Không trong runtime classpath do Maven chọn theo scope | Có | Runtime/container/JDK được kỳ vọng cấp thư viện, ví dụ servlet API. |
| `runtime` | Không | Có | Có | Implementation chỉ cần khi chạy, ví dụ JDBC driver được nạp động. |
| `test` | Không | Không | Có | JUnit, Mockito, test fixtures. |
| `system` | Dùng JAR tại `systemPath`, classpath kiểu legacy | Không nên dựa vào cơ chế runtime tự động của Maven | Có khi phục vụ compile/test | Khó tái lập; tránh khi có repository. |
| `import` | Không áp dụng | Không áp dụng | Không áp dụng | Chỉ hợp lệ cho BOM `type=pom` trong `dependencyManagement`. |

Bảng mô tả tập dependency trực tiếp/effective trong project thông thường, không bao quát mọi ngoại lệ JPMS, plugin override hoặc cơ chế đóng gói riêng. Maven còn tính **scope hiệu lực của transitive dependency** bằng quy tắc kết hợp scope; do vậy không mặc định tất cả transitive dependencies giữ nguyên scope ban đầu.

Ví dụ main code cần `org.apache.commons.lang3.StringUtils`:

~~~xml
<dependency>
    <groupId>org.apache.commons</groupId>
    <artifactId>commons-lang3</artifactId>
    <version>3.17.0</version>
</dependency>
~~~

Không có `<scope>` nghĩa là scope `compile`. Nếu `src/test/java` dùng JUnit:

~~~xml
<dependency>
    <groupId>org.junit.jupiter</groupId>
    <artifactId>junit-jupiter</artifactId>
    <version>5.11.4</version>
    <scope>test</scope>
</dependency>
~~~

Các đoạn trên là **mảnh XML của `<project><dependencies>`**, không phải POM đầy đủ. JUnit scope `test` không hiện diện trên main compile classpath chỉ vì nó đã được Maven tải về repository cục bộ.

## 4. Khi Maven chạy lifecycle, classpath được dùng lúc nào?

Với packaging `jar` mặc định:

| Phase | Hoạt động chính | Classpath liên quan |
| --- | --- | --- |
| `process-resources` | Copy/filter resource chính. | Resources Plugin cùng cấu hình và resource. |
| `compile` | Biên dịch `src/main/java` ra `target/classes`. | Main compile classpath. |
| `process-test-resources` | Copy/filter resource test. | Resources Plugin trong ngữ cảnh test. |
| `test-compile` | Biên dịch `src/test/java` ra `target/test-classes`. | Test compile classpath. |
| `test` | Chạy unit test khi Surefire được bind/cấu hình phù hợp. | Test runtime classpath. |
| `package` | Tạo artifact JAR/WAR... theo packaging. | Output build và packaging plugin. |
| `integration-test`/`verify` | Tác vụ integration test/verify nếu được gắn vào lifecycle. | Theo plugin, ví dụ Failsafe. |

Lệnh:

~~~bash
mvn -B -ntp clean test
~~~

xóa output của lần trước rồi chạy các phase cần thiết đến `test`. Còn:

~~~bash
mvn -B -ntp clean package
~~~

chạy tiếp đến `package`, trong lifecycle JAR thông thường có compile và test trước khi đóng gói.

Không suy ra “plugin Compiler có Commons Lang trong classpath riêng” chỉ vì Compiler Plugin biên dịch được main code import Commons Lang: plugin đã nhận **classpath của project** để biên dịch. Chúng là hai khái niệm khác nhau.

## 5. Main compile classpath: nơi mã nguồn chính tìm API

Mã trong `src/main/java` được compiler xử lý với những dependency mà Maven cho phép ở thời điểm compile. Ví dụ:

~~~java
package org.example;

import org.apache.commons.lang3.StringUtils;

public final class Labels {
    private Labels() {
    }

    public static String clean(String raw) {
        return StringUtils.trimToEmpty(raw);
    }
}
~~~

Đây là một class hợp lệ nếu project khai báo Commons Lang ở scope phù hợp. Nếu JAR này không ở main compile classpath, Java compiler có thể báo:

~~~text
package org.apache.commons.lang3 does not exist
~~~

Cách khắc phục là đặt dependency tương ứng tại **`<project><dependencies>`**, không phải trong plugin dependencies của Maven Compiler Plugin.

Nếu mã chính có:

~~~java
import org.junit.jupiter.api.Test;
~~~

nhưng POM chỉ khai báo JUnit với `scope=test`, main compile không nhìn thấy JUnit. Phần lớn trường hợp đây là do code test đặt nhầm vào `src/main/java`; cần chuyển code vào `src/test/java` thay vì đưa JUnit vào production scope một cách máy móc.

Maven không cần dependency riêng cho class standard library như `java.util.List` hoặc `java.util.Locale` nếu chúng được JDK đang dùng cung cấp. Java release/JDK version và dependency graph là hai vấn đề liên quan nhưng không đồng nhất.

## 6. Main runtime classpath: khác biệt làm phát sinh NoClassDefFoundError

Sau khi build, file `.class` của project nằm trong `target/classes`; JAR thường chứa class/resource của chính project. Lệnh:

~~~bash
java -cp target/classes org.example.ClasspathApp
~~~

không đọc `pom.xml` và không tự thêm các JAR phụ thuộc mà Maven đã dùng để compile. Nếu `ClasspathApp` gọi Commons Lang, JVM có thể báo:

~~~text
java.lang.NoClassDefFoundError: org/apache/commons/lang3/StringUtils
~~~

Maven compile **có thể đã thành công**: lỗi lúc này là thiếu JAR ở **runtime classpath** của lệnh `java` mới được khởi chạy.

Có hai thứ cần đưa vào runtime classpath:

- **Code của ứng dụng**: `target/classes` hoặc JAR của chính project.
- **Dependency runtime**: các project dependencies có scope compile/runtime hiệu lực (và các artifact phụ cần thiết theo graph).

Một JAR đóng gói theo lifecycle JAR chuẩn **không tự động là fat JAR**. Muốn chạy dạng `java -jar` với dependencies, cần thiết kế manifest/classpath riêng hoặc dùng plugin đóng gói phù hợp (Shade, Assembly, repackaging của framework...). Không giả định `java -jar target/app.jar` tự tải JAR từ Maven repository.

Có thể tạo thư mục runtime dependencies bằng Maven Dependency Plugin:

~~~bash
mvn -B -ntp org.apache.maven.plugins:maven-dependency-plugin:3.8.1:copy-dependencies -DincludeScope=runtime -DoutputDirectory=target/dependency
~~~

Bộ lọc `includeScope=runtime` của goal này bao gồm dependency scope **runtime và compile**, không bao gồm test-only/provided. Lệnh Java trên Unix:

~~~bash
java -cp "target/classes:target/dependency/*" org.example.ClasspathApp
~~~

Trên Windows PowerShell/CMD:

~~~text
java -cp "target\classes;target\dependency\*" org.example.ClasspathApp
~~~

Dấu `:` tách các classpath entries trên Unix, `;` trên Windows. Thành phần `*` là wildcard classpath JAR được Java launcher hiểu; quote classpath để shell không diễn giải sai. Các ví dụ đầy đủ nằm ở mục 10.

## 7. Test compile classpath: vì sao mã test nhìn thấy nhiều hơn mã chính?

Mã `src/test/java` thường cần:

1. Class chính đã được biên dịch trong `target/classes`.
2. Những thư viện mà main code phụ thuộc ở compile/runtime.
3. Test-only dependencies như JUnit, Mockito.
4. Những provided/system dependencies hợp lệ cho môi trường test.

Khi chạy `test-compile`, Maven Compiler Plugin biên dịch test ra `target/test-classes`. Các test classes này **không tự xuất hiện trong JAR chính**.

Ví dụ một test JUnit:

~~~java
package org.example;

import static org.junit.jupiter.api.Assertions.assertEquals;
import org.junit.jupiter.api.Test;

class ClasspathAppTest {
    @Test
    void verifiesMainCode() {
        assertEquals("Maven", ClasspathApp.normalize("  MAVEN  "));
    }
}
~~~

Test vừa truy cập `ClasspathApp` từ main output, vừa dùng JUnit từ test dependency. Đây là việc test classpath được thiết kế để hỗ trợ.

Không được đảo chiều kết luận: main code **không** mặc nhiên truy cập được `ClasspathAppTest` hoặc JUnit chỉ vì test có thể truy cập main code. Đó là sự phân tách một chiều hữu ích cho cấu trúc ứng dụng.

## 8. Test runtime classpath của Maven Surefire Plugin

Maven Surefire Plugin chạy unit test tại phase `test` trong nhiều project sử dụng lifecycle mặc định. Theo hướng dẫn chính thức về **classpath mặc định của Surefire**, thứ tự các nhóm phần tử khi thực thi test thường là:

1. `target/test-classes`.
2. `target/classes`.
3. **Project dependencies** trong các scope áp dụng cho test.
4. Các classpath elements bổ sung nếu được cấu hình.

Trong một số phiên bản, Surefire cho phép `additionalClasspathElements` hoặc `additionalClasspathDependencies`, nhưng cần biết rằng **thêm classpath chỉ cho test execution không nhất thiết giúp compiler biên dịch source test**. Nếu `src/test/java` import một API, hãy đảm bảo API đó có mặt ở **test compile classpath** bằng project dependency phù hợp.

Surefire có thể fork JVM, dùng provider để tìm/chạy JUnit tests, tạo XML/text reports dưới `target/surefire-reports`. Điều quan trọng là:

- **Plugin Surefire** tự chạy trong môi trường plugin của Maven.
- **Test code** chạy trong classpath/JVM được Surefire tạo ra.
- **JUnit** thường thuộc project test dependency graph, không phải một thư viện production cần đưa lên main runtime classpath.
- Những dependencies nội bộ để Surefire chạy goal không đồng nghĩa trở thành API của `src/main/java`.

Với integration tests, Failsafe có thể dùng test classes/dependencies tương tự nhưng goal/lifecycle khác; `mvn verify` không bảo đảm Failsafe chạy nếu project chưa cấu hình nó.

## 9. Plugin class realm: không phải classpath của ứng dụng

Maven sử dụng cơ chế **class realm/classloader isolation** (Plexus Classworlds) để chạy plugin và build extensions. Với một Maven plugin thông thường:

~~~text
Maven Core / API thích hợp
          |
          v
  plugin class realm
    ├── plugin JAR
    ├── plugin's own dependency JARs
    └── plugin dependencies do project khai báo thêm
          |
          v
     plugin goal được thực thi
~~~

Ví dụ Maven Compiler Plugin có thể dùng các library phục vụ compiler/Maven plugin bên trong realm của nó. Maven Surefire Plugin có bộ dependencies riêng để hỗ trợ việc chạy test. **Không nên mong những JAR này tự xuất hiện trên compile classpath của app**.

Plugin có thể hỏi MavenProject về project compile/test/runtime classpath, sau đó cấp tập classpath ấy cho compiler/JVM con. Cơ chế plugin “nhìn thấy danh sách dependency project qua API” **khác** với việc plugin realm trực tiếp chứa mọi JAR từ project graph.

Tài liệu [Guide to Maven Classloading](https://maven.apache.org/guides/mini/guide-maven-classloading.html) là nguồn chính để hiểu phân biệt giữa Maven core, project realms, plugin realms và build extensions.

### Plugin dependencies có cú pháp riêng

Một ví dụ **mảnh cấu hình** bổ sung thư viện cho Maven Antrun Plugin:

~~~xml
<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-antrun-plugin</artifactId>
            <version>3.1.0</version>
            <dependencies>
                <dependency>
                    <groupId>commons-io</groupId>
                    <artifactId>commons-io</artifactId>
                    <version>2.16.1</version>
                </dependency>
            </dependencies>
        </plugin>
    </plugins>
</build>
~~~

Đây **không phải plugin bắt buộc** của project ví dụ ở mục 10 và đoạn trên không tự bind goal Antrun vào lifecycle. Nó chỉ minh họa cách thêm Commons IO vào **plugin realm** của Antrun.

Nếu mã `src/main/java` cần `org.apache.commons.io.FileUtils`, code **không được tự thấy** Commons IO chỉ vì snippet trên. Hãy khai báo thư viện ấy trong **`<project><dependencies>`** với scope phù hợp. Ngược lại, khai báo Commons IO ở project scope compile **không bảo đảm** Antrun Plugin tự nạp nó vào realm nội bộ nếu plugin cần library này để chạy.

Phân biệt vị trí:

| Vị trí XML | Hệ quả |
| --- | --- |
| `project/dependencies` | Tạo project dependencies, dùng để xây main/test/runtime classpaths theo scope. |
| `project/dependencyManagement` | Quản lý version/scope, không tự thêm JAR vào project classpath. |
| `build/plugins/plugin/dependencies` | Thêm dependency vào realm của **một plugin cụ thể**. |
| `build/pluginManagement` | Quản lý plugin version/config; không tự kích hoạt một goal bất kỳ. |
| `build/extensions` | Build extensions theo cơ chế riêng, không phải cách khai báo API cho source project. |

## 10. Ví dụ Java 17 chạy được: main + test + plugin

Đây là ví dụ độc lập, gồm **mã Java 17**, JUnit 5 test, Maven Compiler Plugin, Maven Surefire Plugin. Mã main dùng Commons Lang; mã test dùng JUnit.

Cấu trúc:

~~~text
classpath-realm-demo/
├── pom.xml
└── src/
    ├── main/java/org/example/ClasspathApp.java
    └── test/java/org/example/ClasspathAppTest.java
~~~

### 10.1. pom.xml hoàn chỉnh

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>org.example</groupId>
    <artifactId>classpath-realm-demo</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.apache.commons</groupId>
            <artifactId>commons-lang3</artifactId>
            <version>3.17.0</version>
        </dependency>
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

Đây là **POM đầy đủ**, với project dependencies và build plugins tách riêng. Không có Maven Antrun Plugin của mảnh minh họa mục 9. Chạy với JDK 17+, Maven 3.9.x tương thích, và có thể truy cập repository để tải những artifact chưa cache.

### 10.2. src/main/java/org/example/ClasspathApp.java

~~~java
package org.example;

import java.util.Locale;
import org.apache.commons.lang3.StringUtils;

public final class ClasspathApp {
    private ClasspathApp() {
    }

    public static String normalize(String input) {
        String text = StringUtils.trimToEmpty(input);
        return text.isEmpty()
                ? "(empty)"
                : StringUtils.capitalize(text.toLowerCase(Locale.ROOT));
    }

    public static void main(String[] args) {
        System.out.println("main=" + normalize("  MAVEN  "));
        System.out.println("blank=" + normalize(" \t "));
    }
}
~~~

Giải thích: `Locale` thuộc JDK; `StringUtils` thuộc Commons Lang, là project dependency scope compile. `trimToEmpty` bỏ các ký tự khoảng trắng ASCII ở đầu/cuối chuỗi ví dụ; `toLowerCase(Locale.ROOT)` rồi `capitalize` đưa `MAVEN` thành `Maven`.

### 10.3. src/test/java/org/example/ClasspathAppTest.java

~~~java
package org.example;

import static org.junit.jupiter.api.Assertions.assertEquals;
import org.junit.jupiter.api.Test;

class ClasspathAppTest {
    @Test
    void normalizesText() {
        assertEquals("Maven", ClasspathApp.normalize("  MAVEN  "));
        assertEquals("(empty)", ClasspathApp.normalize(" \t "));
    }
}
~~~

Test biên dịch được vì test classpath có class chính và JUnit. Test có **một test method** chứa hai assertions. Nếu JUnit chỉ là plugin dependency và không có project `scope=test`, nguồn test không tự nhìn thấy `@Test`.

### 10.4. Build và kiểm tra đầu ra

Trong thư mục project, chạy:

~~~bash
mvn -B -ntp clean verify
~~~

Khi build thành công, các output trọng tâm:

~~~text
target/
├── classes/org/example/ClasspathApp.class
├── test-classes/org/example/ClasspathAppTest.class
├── surefire-reports/
│   ├── TEST-org.example.ClasspathAppTest.xml
│   └── org.example.ClasspathAppTest.txt
└── classpath-realm-demo-1.0.0.jar
~~~

Đây là cây rút gọn; Maven có thể sinh thêm thư mục và metadata. Surefire test được phát hiện và chạy khi môi trường/plugin phù hợp. Không coi danh sách file trên là đầy đủ mọi đầu ra.

### 10.5. Runtime classpath thật sự để chạy Java

Đầu tiên copy các dependency cần cho runtime:

~~~bash
mvn -B -ntp org.apache.maven.plugins:maven-dependency-plugin:3.8.1:copy-dependencies -DincludeScope=runtime -DoutputDirectory=target/dependency
~~~

Sau đó trên Linux/macOS:

~~~bash
java -cp "target/classes:target/dependency/*" org.example.ClasspathApp
~~~

Hoặc Windows PowerShell/CMD:

~~~text
java -cp "target\classes;target\dependency\*" org.example.ClasspathApp
~~~

**Stdout chính xác của riêng lệnh `java`**:

~~~text
main=Maven
blank=(empty)
~~~

Maven có log riêng, không được mô tả bằng đoạn stdout trên.

Nếu chạy `java -cp target/classes ...` mà không thêm `target/dependency/*`, JVM không tự có Commons Lang. Nếu chạy `java -jar target/classpath-realm-demo-1.0.0.jar`, POM mẫu không khai báo `Main-Class` trong manifest và cũng không đóng gói runtime dependencies vào cùng JAR; do đó không dùng lệnh ấy như phương pháp chạy mẫu.

## 11. Nhìn classpath bằng Maven Dependency Plugin

Dùng goal `dependency:tree` để xem **project dependency graph**:

~~~bash
mvn org.apache.maven.plugins:maven-dependency-plugin:3.8.1:tree
~~~

Kết quả phụ thuộc version/transitive graph, nhưng trong POM mẫu sẽ có project dependency compile Commons Lang và test JUnit cùng dependencies liên quan. **Không** mong cây này liệt kê toàn bộ JAR nội bộ mà Compiler/Surefire Plugin dùng trong plugin realms.

Để tạo chuỗi classpath chỉ cho **project dependencies**, có goal `dependency:build-classpath`:

~~~bash
mvn org.apache.maven.plugins:maven-dependency-plugin:3.8.1:build-classpath -DincludeScope=compile -Dmdep.outputFile=target/compile-deps.txt
mvn org.apache.maven.plugins:maven-dependency-plugin:3.8.1:build-classpath -DincludeScope=runtime -Dmdep.outputFile=target/runtime-deps.txt
mvn org.apache.maven.plugins:maven-dependency-plugin:3.8.1:build-classpath -DincludeScope=test -Dmdep.outputFile=target/test-deps.txt
~~~

Ý nghĩa của `includeScope` ở goal này:

| Giá trị | Tập dependencies được chọn |
| --- | --- |
| `compile` | compile + provided + system. |
| `runtime` | compile + runtime. |
| `test` | tất cả project dependencies phù hợp, gồm test. |

Các file `target/*-deps.txt` chứa đường dẫn JAR trong local repository, **không mặc định bao gồm `target/classes` và `target/test-classes`**. Muốn dựng đầy đủ classpath cho một tiến trình Java, phải thêm thư mục output đúng theo nhiệm vụ.

Lưu ý: `-Dmdep.outputFile=...` là user property của goal `build-classpath`; các goal khác có tên parameter/property riêng. Không giả định `-DincludeScope` là cách thay đổi scope được khai báo trong `pom.xml`; nó chỉ điều khiển bộ lọc của goal Dependency Plugin trong các lệnh trên.

Có thể xem các output directories thực tế của project:

~~~bash
mvn -q -Dexpression=project.build.outputDirectory -DforceStdout help:evaluate
mvn -q -Dexpression=project.build.testOutputDirectory -DforceStdout help:evaluate
~~~

Với cấu hình Maven thông thường, chúng trỏ tới `target/classes` và `target/test-classes` của **module hiện tại**; nếu POM chỉnh build directories thì phải dùng giá trị thực tế.

## 12. Kiểm tra plugin realm và gỡ lỗi plugin

Nếu lỗi xảy ra trong **mã của Maven plugin**, hãy kiểm tra:

~~~bash
mvn help:effective-pom
mvn -X test
~~~

`help:effective-pom` giúp xem version/configuration của plugin và mục `<plugin><dependencies>` sau khi hợp nhất parent/profile. Log `-X` có thể hiển thị thông tin tạo/plugin class realm và danh sách artifact tương ứng, tùy Maven version.

Nhưng **`help:effective-pom` chưa chắc chứng minh goal đã thực thi**; cần đọc log lifecycle và execution thực tế. `-X` có thể chứa thông tin nhạy cảm; không đăng nguyên log lên kênh công khai khi có secret, proxy, repository URLs hoặc user properties nội bộ.

Bảng phân loại lỗi:

| Lỗi gặp ở đâu? | Nơi cần kiểm tra trước |
| --- | --- |
| Compiler báo không tìm thấy import của `src/main/java`. | **Project main compile classpath**, dependency scope/tọa độ. |
| Test compiler không tìm thấy JUnit hoặc class main. | **Test compile classpath**, main output, test dependencies. |
| Test chạy lỗi `ClassNotFoundException`/provider. | **Test execution classpath**, Surefire/Failsafe, fork/provider/config. |
| Lệnh `java` sau package báo `NoClassDefFoundError`. | **Main runtime classpath**, `java -cp` và packaging. |
| Maven plugin tự ném `ClassNotFoundException` bên trong stack trace plugin. | **Plugin class realm**, plugin version, plugin dependencies và API compatibility. |

Không sửa main `<dependencies>` khi lỗi thực ra là plugin realm, và không sửa plugin realm khi lỗi là import Java source.

## 13. Test plugin có thể có classpath riêng cho quá trình thực thi

Surefire có hỗ trợ cấu hình thêm classpath elements khi chạy test, nhưng điều đó làm phát sinh một ranh giới nữa:

- **Test compilation classpath** được Maven Compiler Plugin dùng để biên dịch `src/test/java`.
- **Test execution classpath** do Surefire dựng để chạy test, có thể khác vì thêm/bớt JAR hoặc resource bằng cấu hình plugin.
- **Surefire plugin realm** dùng để thực thi logic plugin, không mặc định trùng test runtime classpath.

Ví dụ, nếu thêm một đường dẫn vào `additionalClasspathElements` của Surefire, đường dẫn đó có thể xuất hiện **khi test chạy**, nhưng test source biên dịch trước đó vẫn có thể thiếu API cần thiết. Nếu mã test trực tiếp import API, hãy đặt dependency hợp lệ ở project test dependencies.

Maven Surefire docs còn giải thích thứ tự mặc định của test runtime classpath: **test-classes → classes → project dependencies → additional elements**. Một vài plugin/version có các cơ chế exclude hoặc module path; khi dự án dùng JPMS hoặc customized providers, hãy xem tài liệu đúng phiên bản.

Với test tích hợp, Failsafe có lifecycle `integration-test` và `verify` riêng; plugin phải được cấu hình/bind phù hợp. Việc build có Surefire không làm cho Failsafe tự chạy mọi integration test.

## 14. Dự án nhiều module: classpath thuộc từng module

Trong Maven reactor:

~~~text
root/pom.xml
├── core/pom.xml
│   └── src/main/java/...
└── app/pom.xml
    ├── src/main/java/...
    └── src/test/java/...
~~~

- `core` có project dependency graph và compile/test/runtime classpaths riêng.
- `app` có classpaths riêng; nếu code app dùng class từ core, `app/pom.xml` cần khai báo dependency `core`, không chỉ dựa vào cùng `<modules>` của root.
- Root có `<dependencyManagement>` quản lý version không tự làm mọi dependency được đưa vào classpath của child.
- `core/src/test/java` không tự xuất hiện khi app phụ thuộc JAR chính của core; muốn dùng test fixture chung cần module hoặc test-jar có tọa độ/classifier phù hợp.
- Plugin configuration có thể được kế thừa từ parent, nhưng đó là build/plugin layer, không phải cơ chế “mọi module dùng chung một Java classpath”.

Có thể kiểm tra từng module bằng:

~~~bash
mvn -pl :core dependency:tree
mvn -pl :app dependency:tree
mvn -pl :app -am test
~~~

Đây là những lệnh **minh họa** cho reactor thực sự có artifactId `core` và `app`, không phải lệnh dành cho project đơn module ở mục 10.

## 15. Java 17, JPMS và module path: lưu ý nâng cao

Từ Java 9, Java Platform Module System (JPMS) bổ sung **module path** bên cạnh classpath. Nếu project có `module-info.java`:

- Dependency được khai báo trong POM vẫn có scope Maven (compile/runtime/test).
- Java compiler/launcher có thể đặt JAR lên **module path** thay vì classpath theo module declarations và plugin configuration.
- Named modules cần thỏa `requires`, `exports` và các quy tắc visibility; vì vậy một JAR được Maven resolve không đồng nghĩa mọi package đều import được trong named module.
- Surefire có khả năng xử lý JPMS và các tùy chọn như `useModulePath`; kiểm tra đúng plugin/JDK version.

Ví dụ module-info **minh họa riêng**, không phải tệp của project mẫu:

~~~java
module org.example.app {
    requires org.apache.commons.lang3;
}
~~~

Tên module trong mã `requires` phải được xác minh theo artifact/module metadata thực tế, không đoán từ `artifactId`; trên classpath truyền thống của project mẫu không cần `module-info.java`.

**Khi gặp lỗi visibility trên Java 17**, đừng tự động đổi scope hoặc thêm cùng dependency vào plugin dependencies: cần xác định JVM/compiler đang dùng classpath hay module path.

## 16. Sai lầm thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân thường gặp | Cách kiểm tra |
| --- | --- | --- |
| `package org.apache.commons.lang3 does not exist` khi compile. | Thiếu Commons Lang trên main compile classpath, sai scope/tọa độ. | Kiểm tra `project/dependencies`, `mvn dependency:tree`. |
| `package org.junit.jupiter.api does not exist` khi test-compile. | Thiếu JUnit scope test hoặc JUnit chưa resolve. | Kiểm tra dependency test và plugin Compiler/Surefire. |
| Main source import JUnit không thành công. | JUnit scope test không vào main compile. | Đặt test code trong `src/test/java`. |
| Build thành công nhưng `java -cp target/classes` báo thiếu `StringUtils`. | Thiếu runtime JAR trên lệnh Java. | Dùng runtime classpath đúng hoặc packaging phù hợp. |
| `dependency:tree` không hiển thị compiler/surefire plugin JAR. | Đang xem project graph, không phải plugin realm. | Xem `build/plugins`, plugin docs và debug log có kiểm soát. |
| Thêm JAR dưới `<plugin><dependencies>` nhưng main import vẫn lỗi. | Plugin dependency không tự thành project dependency. | Khai báo thư viện ở project `<dependencies>`. |
| Thêm JAR project scope compile mà plugin vẫn ClassNotFound. | Plugin realm có thể thiếu JAR cần cho chính nó. | Xem stack trace, plugin version/dependencies. |
| Test compile được nhưng execution lỗi. | Test runtime classpath/fork/provider khác compilation. | Kiểm tra Surefire classpath/config, reports. |
| Đổi scope sang provided rồi ứng dụng production thiếu class. | Môi trường chạy không thật sự cung cấp JAR. | Xem container/runtime dependencies. |
| Test hoặc app có `NoSuchMethodError`. | Version conflict/binary incompatibility, có thể do dependency mediation. | Xem `dependency:tree`, version class được nạp và compatibility. |
| Multi-module cùng parent nhưng app thiếu class core. | Aggregation/kế thừa không tự tạo dependency. | Thêm project dependency app → core. |
| Có `module-info.java` và Java báo module/package không thấy. | Module path/readability/export khác classpath thông thường. | Kiểm tra module descriptors và Maven plugin JPMS settings. |

**Quy trình debug ngắn:** xác định lỗi ở **compile main → compile test → run test → run app → chạy plugin**; tìm **classloader/classpath tương ứng**; đọc effective POM, dependency tree hoặc log plugin; chỉ sửa đúng scope/cấu hình rồi build sạch. Tránh hard-code JAR trong `~/.m2/repository` vào CI vì không đảm bảo cùng đường dẫn giữa các máy.

## 17. Checklist và câu hỏi tự kiểm tra

Checklist trước khi kết luận build đúng:

- [ ] Main code chỉ import API từ JDK hoặc project dependencies hợp lệ cho main compile.
- [ ] JUnit/Mockito/test fixture được khai báo cho test classpath, không vô cớ đưa vào runtime production.
- [ ] `target/classes` và `target/test-classes` được xem là hai đầu ra khác nhau.
- [ ] Khi chạy Java trực tiếp, main runtime classpath chứa cả project output lẫn runtime JARs.
- [ ] Không nhầm `dependency:tree` của project với plugin class realm.
- [ ] Không dùng `plugin/dependencies` như giải pháp thay `project/dependencies`.
- [ ] Đã kiểm tra Surefire test execution classpath khi test chạy khác compile.
- [ ] Các Maven plugin và JDK đã được pin/phối hợp theo cấu hình dự án.
- [ ] Nếu có reactor đa module, đã xác minh dependency của từng module.
- [ ] Nếu dùng JPMS, đã kiểm tra classpath/module path và tên module thực tế.

Tự kiểm tra:

1. **Vì sao test import được JUnit nhưng main source thì không?** Vì JUnit ở scope test, chỉ có trong test compile/run classpath.
2. **Maven compile thành công nhưng Java báo NoClassDefFoundError khi chạy: chắc compiler sai không?** Không. Hãy kiểm tra runtime `-cp` và JAR dependency.
3. **Đặt Commons IO vào `<plugin><dependencies>` của Antrun có làm main code import được `FileUtils`?** Không. Đó là plugin realm, không phải project compile classpath.
4. **`dependency:tree` cho biết plugin realm chứa toàn bộ gì không?** Không. Nó cho project dependency graph.
5. **Test của Surefire thấy mã chính bằng cách nào?** Test runtime classpath bao gồm `target/test-classes`, `target/classes`, project dependencies và phần tử bổ sung nếu cấu hình.
6. **Tại sao scope runtime không phù hợp cho API được main code import trực tiếp?** Scope runtime không có trên main compile classpath.
7. **Ở đa module, chỉ cần cùng root reactor để dùng class của module khác không?** Không. Module dùng class cần project dependency phù hợp.
8. **Một dependency có trên Maven classpath có luôn đọc được qua Java named module không?** Không; JPMS còn xét module path, requires/exports và quy tắc module visibility.

## 18. Tài liệu tham khảo

- [Apache Maven — Introduction to the Dependency Mechanism](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html) — dependency scopes và classpaths.
- [Apache Maven — Guide to Maven Classloading](https://maven.apache.org/guides/mini/guide-maven-classloading.html) — Maven core/plugin class realms.
- [Apache Maven Surefire Plugin — Configuring the Classpath](https://maven.apache.org/surefire/maven-surefire-plugin/examples/configuring-classpath.html) — test runtime classpath.
- [Apache Maven Dependency Plugin — build-classpath](https://maven.apache.org/plugins/maven-dependency-plugin/build-classpath-mojo.html) — `includeScope`, `mdep.outputFile`.
- [Apache Maven Dependency Plugin — copy-dependencies](https://maven.apache.org/plugins/maven-dependency-plugin/copy-dependencies-mojo.html) — copy runtime dependencies.
- [Apache Maven Dependency Plugin — dependency:tree](https://maven.apache.org/plugins/maven-dependency-plugin/tree-mojo.html) — project dependency graph.
- [Apache Maven Compiler Plugin — compiler:compile](https://maven.apache.org/plugins/maven-compiler-plugin/compile-mojo.html) — compiler configuration.
- [Apache Maven Surefire Plugin — surefire:test](https://maven.apache.org/surefire/maven-surefire-plugin/test-mojo.html) — unit tests.
- [Apache Maven — Introduction to the POM](https://maven.apache.org/guides/introduction/introduction-to-the-pom.html) — project dependencies và build plugins.

**Ghi nhớ:** **Main compile** dùng để biên dịch mã ứng dụng; **main runtime** để chạy ứng dụng; **test classpath** để biên dịch và chạy test; **plugin realm** để Maven plugin tự hoạt động. Chúng có thể sử dụng các JAR từ cùng repository nhưng **không phải một classpath chung**. Phải xác định đúng nơi class đang thiếu trước khi chỉnh dependency, scope, runtime launcher hoặc plugin configuration.
