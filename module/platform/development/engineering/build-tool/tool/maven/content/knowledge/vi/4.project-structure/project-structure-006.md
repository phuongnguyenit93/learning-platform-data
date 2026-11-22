# generated-sources, generated-test-sources và mã được sinh trong Maven

## 1. Khi mã Java không được viết hoàn toàn bằng tay

Một dự án Maven có thể chứa mã Java do con người viết và mã Java do công cụ sinh ra từ nguồn đầu vào khác. Ví dụ, OpenAPI Generator sinh client/model từ API specification, Protobuf sinh lớp từ file `.proto`, ANTLR sinh lexer/parser từ grammar, MapStruct sinh implementation của mapper qua annotation processing.

Nguồn sinh ra (*generated source*) vẫn là file `.java` và vẫn phải được trình biên dịch Java xử lý trước khi chương trình sử dụng nó. Tuy nhiên, **nguồn sự thật** của mã này là schema, template, annotation và cấu hình generator. Nếu sửa trực tiếp file được sinh, thay đổi có thể mất khi build lại.

Bài này tập trung vào cách Maven sắp xếp mã sinh ra trong cấu trúc dự án, phân biệt main/test generated sources, đăng ký source root, cấu hình phase, kiểm chứng bằng một ví dụ Java 17 và xử lý các lỗi hay gặp.

| Loại dữ liệu | Thư mục thường gặp | Kết quả |
| --- | --- | --- |
| Mã chính viết tay | `src/main/java` | Biên dịch thành class production |
| Mã chính được sinh | `target/generated-sources/<tên-generator>/` | Biên dịch cùng mã production |
| Mã test viết tay | `src/test/java` | Biên dịch vào classpath kiểm thử |
| Mã test được sinh | `target/generated-test-sources/<tên-generator>/` | Biên dịch cùng mã kiểm thử |
| Class production sau compile | `target/classes` | Bytecode được đóng gói vào JAR mặc định |
| Class kiểm thử sau test-compile | `target/test-classes` | Bytecode dùng để chạy test, không nằm trong JAR chính mặc định |

Các đường dẫn con như `openapi`, `protobuf`, `annotations` hay `tutorial` chỉ là ví dụ. Maven **không bắt buộc** mọi dự án có cùng các thư mục con dưới `target/generated-sources`. Một generator cũng có thể ghi vào thư mục khác nếu được cấu hình. `target/` thường được coi là thư mục output có thể tái tạo sau khi `mvn clean`.

## 2. Ba bước khác nhau: generate, register, compile

Cách hiểu quan trọng nhất là **tạo file**, **đăng ký đường dẫn** và **biên dịch file** là ba việc riêng biệt.

1. **Generate:** một goal đọc input (schema/template/annotation...) và tạo file `.java`.
2. **Register source root:** Maven được báo rằng thư mục mới là main source root hoặc test source root. Một số generator plugin làm việc này tự động; nếu không, có thể dùng Build Helper Maven Plugin.
3. **Compile:** Maven Compiler Plugin biên dịch source root đã đăng ký, tạo `.class` và đưa vào đúng classpath.

```text
ĐẦU VÀO                                MÃ ĐƯỢC SINH
  openapi.yaml / schema / template
                 |
                 v
       plugin generator
                 |
       +---------+-----------------------+
       |                                 |
       v                                 v
 target/generated-sources/...    target/generated-test-sources/...
       |                                 |
       | add-source / tự đăng ký         | add-test-source / tự đăng ký
       v                                 v
 main compile source roots       test compile source roots
       |                                 |
       v                                 v
 compiler:compile                compiler:testCompile
       |                                 |
       v                                 v
 target/classes                  target/test-classes
       |                                 |
       v                                 v
  JAR/WAR production             test runner như Surefire
```

**Chỉ có thư mục không có nghĩa Maven sẽ tự quét mọi file trong đó.** Thư mục cần xuất hiện trong source roots mà compiler sử dụng. Ngược lại, không thêm `build-helper` một cách máy móc nếu plugin generator đã đăng ký source root đúng: có thể làm cấu hình phức tạp và gây compile trùng.

### Main generated sources

Khi một lớp `demo.generated.GeneratedMessage` được tạo trong `target/generated-sources/tutorial` và code production import nó, thư mục này phải là **main source root**. Trong phase `compile`, Maven biên dịch nó cùng các file dưới `src/main/java`. File bytecode cuối cùng nằm trong `target/classes/demo/generated/GeneratedMessage.class` và thường được đóng gói vào artifact JAR chính.

### Test generated sources

Khi một lớp dữ liệu mẫu `demo.generated.GeneratedExpectation` chỉ phục vụ test, thư mục chứa nó phải là **test source root**, ví dụ `target/generated-test-sources/tutorial`. Maven biên dịch nó trong phase `test-compile` vào `target/test-classes`. Test có thể sử dụng các class production và dependency scope `test`, nhưng class test không được đưa vào JAR production mặc định.

Đặt test helper vào main root có thể kéo code chỉ dùng để kiểm thử vào artifact. Đặt class cần cho production vào test root có thể làm `compile` thất bại: tại thời điểm biên dịch main, test root chưa sẵn sàng.

## 3. Tại sao phải chọn đúng Maven lifecycle phase?

Default lifecycle đi qua các phase theo thứ tự. Những phase liên quan đến generated Java sources là:

| Phase | Mục đích |
| --- | --- |
| `generate-sources` | Thực thi generator tạo mã chính trước biên dịch |
| `process-sources` | Xử lý mã chính bổ sung nếu có plugin tương ứng |
| `compile` | Biên dịch main sources |
| `generate-test-sources` | Thực thi generator tạo mã kiểm thử |
| `process-test-sources` | Xử lý mã kiểm thử bổ sung nếu có |
| `test-compile` | Biên dịch test sources |
| `test` | Chạy unit test |
| `package` | Đóng gói artifact theo packaging |

Với generator chạy ngoài compiler, đặt goal sinh mã production ở `generate-sources` để output được tạo **trước `compile`**. Tương tự, đặt goal sinh mã test ở `generate-test-sources` để output được tạo **trước `test-compile`**. Không phải phase nào cũng có goal được gắn trong mọi dự án.

Các lệnh dễ nhầm:

- `mvn generate-sources` chạy đến phase sinh mã chính; **chưa đồng nghĩa** đã có class được biên dịch.
- `mvn compile` chạy qua `generate-sources` rồi biên dịch main; chưa chạy `generate-test-sources`.
- `mvn generate-test-sources` đi qua compile main và đến sinh mã test; chưa chạy `test-compile`.
- `mvn test` đi qua cả main/test generation và compilation, rồi chạy test.
- `mvn clean test` xóa output cũ bằng clean lifecycle trước khi build và test. Đây là cách tốt để kiểm tra generator đủ khả năng tái tạo mã mà không dựa vào file còn sót lại.
- `mvn clean verify` còn đi tới các kiểm tra bổ sung đã được cấu hình trong phase sau `test`.

## 4. Ví dụ Java 17: Maven sinh cả class chính lẫn test helper

Ví dụ bên dưới chạy được trong dự án Maven đơn giản với JDK 17+ và Maven 3.x phù hợp. Không cần cài generator chuyên dụng; chúng ta dùng **Maven Antrun Plugin** tạo file Java bằng tác vụ Ant `echo` để quan sát rõ cơ chế. Trong dự án thực, thường sẽ thay Antrun bằng plugin sinh mã từ schema hoặc annotation.

### 4.1. Các file bạn tự viết

Tạo một thư mục như sau:

```text
generated-code-demo/
├── pom.xml
└── src/
    ├── main/
    │   └── java/
    │       └── demo/
    │           └── App.java
    └── test/
        └── java/
            └── demo/
                └── AppTest.java
```

**Không tự tạo** `GeneratedMessage.java` hay `GeneratedExpectation.java`. Maven sẽ tạo chúng bên trong `target`.

### 4.2. Cấu hình `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>dev.example</groupId>
    <artifactId>generated-code-demo</artifactId>
    <version>1.0.0-SNAPSHOT</version>
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
                <artifactId>maven-antrun-plugin</artifactId>
                <version>3.1.0</version>
                <executions>
                    <execution>
                        <id>generate-main-class</id>
                        <phase>generate-sources</phase>
                        <goals>
                            <goal>run</goal>
                        </goals>
                        <configuration>
                            <target>
                                <mkdir dir="${project.build.directory}/generated-sources/tutorial/demo/generated"/>
                                <echo file="${project.build.directory}/generated-sources/tutorial/demo/generated/GeneratedMessage.java"><![CDATA[
package demo.generated;

public final class GeneratedMessage {
    private GeneratedMessage() {
    }

    public static String text() {
        return "Build sinh ma thanh cong";
    }
}
]]></echo>
                            </target>
                        </configuration>
                    </execution>

                    <execution>
                        <id>generate-test-helper</id>
                        <phase>generate-test-sources</phase>
                        <goals>
                            <goal>run</goal>
                        </goals>
                        <configuration>
                            <target>
                                <mkdir dir="${project.build.directory}/generated-test-sources/tutorial/demo/generated"/>
                                <echo file="${project.build.directory}/generated-test-sources/tutorial/demo/generated/GeneratedExpectation.java"><![CDATA[
package demo.generated;

public final class GeneratedExpectation {
    private GeneratedExpectation() {
    }

    public static String expected() {
        return "Build sinh ma thanh cong";
    }
}
]]></echo>
                            </target>
                        </configuration>
                    </execution>
                </executions>
            </plugin>

            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>build-helper-maven-plugin</artifactId>
                <version>3.6.2</version>
                <executions>
                    <execution>
                        <id>add-main-generated-root</id>
                        <phase>generate-sources</phase>
                        <goals>
                            <goal>add-source</goal>
                        </goals>
                        <configuration>
                            <sources>
                                <source>${project.build.directory}/generated-sources/tutorial</source>
                            </sources>
                        </configuration>
                    </execution>
                    <execution>
                        <id>add-test-generated-root</id>
                        <phase>generate-test-sources</phase>
                        <goals>
                            <goal>add-test-source</goal>
                        </goals>
                        <configuration>
                            <sources>
                                <source>${project.build.directory}/generated-test-sources/tutorial</source>
                            </sources>
                        </configuration>
                    </execution>
                </executions>
            </plugin>

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
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

Trong POM này có hai execution của Antrun: một execution **tạo mã chính** ở `generate-sources`, một execution **tạo helper kiểm thử** ở `generate-test-sources`. Plugin Build Helper đăng ký hai thư mục vừa tạo làm source roots với goal `add-source` và `add-test-source`.

Trong cùng một phase, các goal khai trong POM được thực hiện theo thứ tự plugin/execution áp dụng; ở đây Antrun được khai trước Build Helper để file/thư mục được tạo trước khi đăng ký. Sau đó Compiler Plugin được kích hoạt tại các phase biên dịch mặc định của packaging `jar`.

Cấu hình `maven.compiler.release=17` chỉ định mức API và bytecode Java; nó khác với version `1.0.0-SNAPSHOT` của artifact. JUnit được khai với `scope=test` để ứng dụng production không kéo dependency kiểm thử vào runtime classpath.

### 4.3. Mã ứng dụng viết tay

File `src/main/java/demo/App.java`:

```java
package demo;

import demo.generated.GeneratedMessage;

public final class App {
    private App() {
    }

    public static String message() {
        return GeneratedMessage.text();
    }

    public static void main(String[] args) {
        System.out.println(message());
    }
}
```

`GeneratedMessage` chưa có trong `src/main/java`. Java compiler vẫn biên dịch được `App.java` nếu generator đã chạy và source root `target/generated-sources/tutorial` được đăng ký đúng trước phase `compile`.

### 4.4. Unit test viết tay dùng helper kiểm thử được sinh

File `src/test/java/demo/AppTest.java`:

```java
package demo;

import demo.generated.GeneratedExpectation;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class AppTest {
    @Test
    void generatedSourcesAreAvailable() {
        assertEquals("Build sinh ma thanh cong", App.message());
        assertEquals(GeneratedExpectation.expected(), App.message());
    }
}
```

Test chứng minh hai điều: `App` dùng class **generated main source**; còn test có thể import `GeneratedExpectation` từ **generated test source**. Class này chỉ cần cho test, không cần đưa vào JAR của ứng dụng.

### 4.5. Chạy và kiểm tra output

Mở terminal tại thư mục chứa `pom.xml`:

```bash
mvn -version
mvn clean test
```

Nếu kết nối repository và môi trường hợp lệ, Maven sẽ tạo:

```text
target/
├── generated-sources/
│   └── tutorial/
│       └── demo/
│           └── generated/
│               └── GeneratedMessage.java
├── generated-test-sources/
│   └── tutorial/
│       └── demo/
│           └── generated/
│               └── GeneratedExpectation.java
├── classes/
│   └── demo/
│       ├── App.class
│       └── generated/
│           └── GeneratedMessage.class
└── test-classes/
    └── demo/
        ├── AppTest.class
        └── generated/
            └── GeneratedExpectation.class
```

Ngoài các file liệt kê, Maven có thể tạo metadata, resource hoặc báo cáo trong `target/`. `mvn clean test` phải chạy test `AppTest` và báo build thành công nếu assertion đúng.

Sau đó chạy:

```bash
mvn package
java -cp target/generated-code-demo-1.0.0-SNAPSHOT.jar demo.App
```

**Stdout từ `App.main` chính xác là:**

```text
Build sinh ma thanh cong
```

Lệnh chạy dùng `-cp` và tên class vì JAR thông thường chưa có cấu hình `Main-Class` trong manifest; không mặc định chạy được với `java -jar`. Dự án này chỉ dùng JDK cho runtime, nên không phải cung cấp thư viện ngoài lúc chạy `demo.App`.

Muốn xem JAR có những class nào:

```bash
jar tf target/generated-code-demo-1.0.0-SNAPSHOT.jar
```

Đầu ra liệt kê class production như `demo/App.class` và `demo/generated/GeneratedMessage.class`. Trong JAR chính mặc định **không có** `demo/AppTest.class` hoặc `demo/generated/GeneratedExpectation.class`. Những class test vẫn ở `target/test-classes`, không phải source đầu vào của plugin đóng gói JAR production.

### 4.6. Thử dừng ở các phase khác nhau

| Lệnh | Điều nên quan sát sau khi `clean` |
| --- | --- |
| `mvn clean generate-sources` | Có `GeneratedMessage.java`; chưa có `GeneratedExpectation.java`; main chưa compile. |
| `mvn clean compile` | Có generated main source và class main; chưa có generated test helper. |
| `mvn clean generate-test-sources` | Đã compile main, đã có generated test source; chưa test-compile. |
| `mvn clean test` | Có generated main/test source, class main/test và unit test được chạy. |

Đây là cách kiểm tra thứ tự Maven lifecycle trực tiếp từ thư mục `target`. Nếu chỉ `mvn test` nhiều lần mà không `clean`, file output còn sót lại có thể che đi một cấu hình generator bị thiếu. Vì vậy, kiểm tra bằng build sạch đặc biệt hữu ích khi CI lỗi nhưng máy cá nhân vẫn PASS.

## 5. Annotation processing: một trường hợp đặc biệt

Không phải mọi mã sinh đều xuất hiện ngay ở phase `generate-sources`. Một **annotation processor** có thể chạy khi Compiler Plugin gọi `javac` trong phase `compile` hoặc `test-compile`. Processor đọc annotation và có thể tạo thêm file Java khi trình biên dịch đang hoạt động.

Trong **Maven Compiler Plugin 3.x**, mặc định:

| Xử lý | Output source mặc định |
| --- | --- |
| Main annotation processing | `${project.build.directory}/generated-sources/annotations` |
| Test annotation processing | `${project.build.directory}/generated-test-sources/test-annotations` |

Ví dụ với công cụ mapper tương thích, một interface có annotation có thể dẫn đến class implementation mới ở `target/generated-sources/annotations`. Trường hợp này khác với ví dụ Antrun: processor và compiler phối hợp ngay khi biên dịch; không cần giả lập source generation ở phase riêng.

Một số công cụ (chẳng hạn Lombok) can thiệp vào cách compiler nhìn thấy AST và **không nhất thiết tạo một file Java độc lập**. Vì vậy, không suy ra rằng cứ dùng annotation processor là phải thấy file `.java` ở output.

Trong Compiler Plugin 3.x, `annotationProcessorPaths` thường dùng để chỉ rõ artifact của processor. Trong nhánh Maven Compiler Plugin 4.x/Maven 4, cách khai processor có những thay đổi. Khi cấu hình processor, hãy kiểm tra **đúng phiên bản plugin** và JDK của dự án. Với generator đã tích hợp việc đăng ký output/compile, không tự bổ sung cùng root bằng Build Helper nếu không có nhu cầu.

## 6. Phân biệt generated Java source với generated resource

Generator cũng có thể tạo `.json`, `.xml`, `.properties`, file SQL hoặc dữ liệu nhị phân. Các file đó là **resource**, không phải Java source. Chúng thường cần cấu hình Maven Resources Plugin hoặc resource root riêng, chứ không phải `add-source`.

Ví dụ, `target/generated-resources/config.json` không thể “biên dịch” chỉ bằng cách đưa thư mục vào `compileSourceRoots`. Muốn đưa resource vào JAR, cần đảm bảo nó được sao chép đến `target/classes` qua các bước xử lý resource hoặc plugin thích hợp.

Các nhóm thường được kiểm tra độc lập: generated Java → `.class`, generated resource → vị trí resource trong artifact, generated test data → classpath test và báo cáo test.

## 7. Quản lý mã sinh sao cho build lặp lại được

Thông thường nên **commit input và cấu hình generator, không commit output dưới `target`**. Ví dụ:

| Nên quản lý trong Git | Thường bỏ qua trong Git |
| --- | --- |
| `pom.xml`, cấu hình plugin và version | `target/generated-sources` |
| Schema, template, file `.proto`, đặc tả OpenAPI | `target/generated-test-sources` |
| Java source viết tay, unit test viết tay | `target/classes`, `target/test-classes` |
| Maven Wrapper của dự án nếu có | File build tạm, report có thể tái tạo |

`.gitignore` thường có:

```gitignore
/target/
```

Một số dự án cố ý commit generated code vì consumer không chạy generator hoặc để phân phối SDK. Khi làm vậy cần quy ước rõ: bản nào là nguồn sự thật, cách regenerate, ai kiểm tra diff và tránh cùng class nằm ở hai source root dẫn đến lỗi `duplicate class`.

Những nguyên tắc làm build ổn định:

1. Pin version generator plugin và những dependency liên quan. Cùng một schema với version generator khác có thể sinh API khác.
2. Quản lý spec/template/processor config trong source control; tránh phụ thuộc input tạm trên máy cá nhân.
3. Đặt file output dưới `${project.build.directory}` khi phù hợp; không để generator vô tình ghi đè mã viết tay.
4. Sắp thứ tự goal sao cho generator chạy trước consumer; với nhiều generator phụ thuộc nhau cần nêu rõ luồng input/output.
5. Xác minh build sạch bằng `mvn clean verify` trong CI; đừng dựa vào source đã sinh từ lần chạy cũ.
6. Tránh timestamp, đường dẫn máy cá nhân, thứ tự ngẫu nhiên hoặc locale không được kiểm soát trong mã sinh nếu muốn build tái lập.
7. Có test cho hành vi/contract của output; “do công cụ sinh ra” không bảo đảm không có lỗi.

Khi đổi schema hoặc phiên bản plugin, hãy kiểm thử cả mã ứng dụng sử dụng generated API. Thay đổi input có thể tạo tên lớp, kiểu dữ liệu hoặc package mới, khiến code viết tay không còn biên dịch.

## 8. Chẩn đoán lỗi theo ba câu hỏi

**(1) File Java đã được sinh chưa?** Kiểm tra đường dẫn thực tế trong `target/generated-sources` hoặc `target/generated-test-sources`, và xem log generator đã chạy ở phase nào. Nếu thiếu file, kiểm tra input, version plugin và execution binding.

**(2) Maven đã đăng ký đúng source root chưa?** Kiểm tra generator có tự đăng ký không, hoặc `build-helper:add-source`/`add-test-source`. Main root phải được sử dụng cho `compile`, test root phải được sử dụng cho `test-compile`.

**(3) File đã được compile và đưa vào classpath đúng chưa?** Tìm class trong `target/classes` hoặc `target/test-classes`. Nếu test PASS nhưng JAR thiếu class production, kiểm tra root bị đặt sai, exclusions, và nội dung JAR.

| Hiện tượng | Nguyên nhân đáng kiểm tra |
| --- | --- |
| `cannot find symbol` hoặc `package ... does not exist` | Generator chưa chạy, source root không đăng ký, mã sinh bị lỗi package, hoặc thứ tự phase sai. |
| `duplicate class` | Cùng FQCN xuất hiện ở nhiều thư mục, vừa commit mã sinh vừa sinh lại, hoặc đăng ký root trùng với source khác. |
| Maven PASS nhưng IDE báo không tìm thấy class | IDE chưa import generated source root, chưa reload Maven project hoặc dùng JDK/config khác. |
| Test class compile thất bại nhưng main compile PASS | `generated-test-sources` chưa sẵn sàng/không được đăng ký, hoặc thiếu dependency scope `test`. |
| Code chạy local nhưng `mvn clean verify` lỗi | File generator còn sót lại trong `target`, input ngoài repo, hoặc plugin/dependency chưa pin và resolve ổn định. |
| Class test nằm trong JAR chính | Thư mục test được đăng ký nhầm là main root hoặc có cấu hình packaging không như dự định. |
| Test không chạy dù `target/test-classes` có class | Xem naming/provider, plugin test runner, skip flags và `target/surefire-reports`. |

Lệnh hỗ trợ:

```bash
mvn clean generate-sources
mvn clean generate-test-sources
mvn clean test
mvn help:effective-pom
mvn -X clean test
```

Dùng `mvn -X` khi cần log debug nhiều thông tin; không coi đó là lệnh bắt buộc cho mọi lần chạy. `help:effective-pom` giúp xác định execution/plugin có thực sự tồn tại sau khi hợp nhất cấu hình từ parent và profiles.

## 9. Những nhầm lẫn thường gặp

**“Tất cả file dưới `target/generated-sources` tự được compile.”** Không. Thư mục có tên đúng chưa đủ; cần generator tích hợp hoặc Maven được cấu hình source root tương ứng.

**“`generated-test-sources` chỉ là cách đặt tên đẹp hơn.”** Không. Ý nghĩa thực tế là nó phải được đăng ký vào **test** source roots; class được compile vào test output và không nằm trong JAR production mặc định.

**“Code generated luôn xuất hiện trước `compile`.”** Không hẳn. Annotation processor có thể tạo file ngay trong compiler invocation. Đây là lý do phải biết generator thuộc loại nào.

**“Sửa file sinh trong `target` là sửa source.”** Thay đổi đó sẽ mất sau khi generator chạy lại hoặc `mvn clean`. Cần sửa input, template hoặc cấu hình generator.

**“Chạy `mvn generate-sources` rồi `java` là đủ.”** Không. Source `.java` cần được compile thành `.class` trước khi JVM chạy.

**“Mã kiểm thử được sinh luôn được đóng gói cùng JAR.”** Không. Test roots thường compile vào `target/test-classes`; JAR chính lấy class main. Test JAR, nếu có, là một artifact bổ sung được cấu hình riêng.

**“Có generated source nên không cần test.”** Không. Schema sai, template lỗi, công cụ nâng version hay contract thay đổi đều có thể gây lỗi. Luôn kiểm tra hành vi cuối cùng.

## 10. Checklist cho dự án thực tế

- [ ] Biết đầu vào gốc (schema, template, annotation...) và plugin version.
- [ ] Chọn đúng vị trí output: main source hay test source.
- [ ] Generator được bind đến phase phù hợp, trước phase compile của consumer.
- [ ] Source roots được đăng ký đúng **một cách rõ ràng** (tự động hoặc Build Helper).
- [ ] Source sinh có package hợp lệ, không trùng FQCN với mã viết tay.
- [ ] Build sạch có thể tái tạo tất cả file mà không cần chỉnh thủ công trong `target`.
- [ ] Compiler biên dịch main/test vào đúng `target/classes` và `target/test-classes`.
- [ ] Test xác nhận API/hành vi, JAR chỉ chứa những class production dự định.
- [ ] CI quản lý version generator và input để giảm khác biệt giữa môi trường.

**Ghi nhớ:** `generated-sources` phục vụ **main compile**, `generated-test-sources` phục vụ **test compile**. Để mã sinh hoạt động, hãy kiểm tra **nguồn gốc file → phase tạo file → source root → compiler → classpath/JAR** theo đúng thứ tự.

## Tài liệu chính thức

- [Apache Maven — Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html)
- [Maven Compiler Plugin — compiler:compile](https://maven.apache.org/plugins/maven-compiler-plugin/compile-mojo.html)
- [Maven Compiler Plugin — compiler:testCompile](https://maven.apache.org/plugins/maven-compiler-plugin/testCompile-mojo.html)
- [Build Helper Plugin — add-source](https://www.mojohaus.org/build-helper-maven-plugin/add-source-mojo.html)
- [Build Helper Plugin — add-test-source](https://www.mojohaus.org/build-helper-maven-plugin/add-test-source-mojo.html)
- [Build Helper Plugin — Usage](https://www.mojohaus.org/build-helper-maven-plugin/usage.html)
- [Maven Antrun Plugin — Introduction](https://maven.apache.org/plugins/maven-antrun-plugin/)
