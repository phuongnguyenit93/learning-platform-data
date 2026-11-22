# Gắn công cụ sinh mã vào generate-sources hoặc generate-test-sources trong Maven

## 1. Vì sao cần gắn code generator vào lifecycle?

Một số dự án Java không viết tất cả mã nguồn bằng tay. Phần mã còn lại được sinh từ một nguồn mô tả có cấu trúc: OpenAPI specification, protobuf schema, XSD, cơ sở dữ liệu, DSL, hoặc một mô hình nghiệp vụ. Ngoài ra, dự án cũng có thể sinh những helper class **chỉ phục vụ kiểm thử**.

Vấn đề không nằm ở việc “có tạo được file `.java` không”. Muốn một clean build chạy được, Maven phải bảo đảm:

1. **Công cụ sinh mã chạy trước Java compiler** cần dùng output của nó.
2. **Các file `.java` được tạo ở thư mục xác định**, thường dưới `target`, không làm bẩn source do con người quản lý.
3. **Compiler biết source root chứa file mới sinh**. Chỉ tạo file không đủ nếu thư mục đó nằm ngoài các source root Maven nhận diện.
4. **Mã chính và mã test được tách biệt**; class hỗ trợ test không bị đóng vào JAR ứng dụng.
5. Lệnh chuẩn như `mvn clean test`, `mvn clean package` hoặc `mvn clean verify` tái tạo toàn bộ kết quả mà không cần chạy script thủ công trước.

Maven có hai phase phù hợp nhất để bắt đầu:

- **`generate-sources`**: sinh mã cần tham gia **main source set** và được biên dịch vào `target/classes`.
- **`generate-test-sources`**: sinh mã chỉ cần cho **test source set** và được biên dịch vào `target/test-classes`.

Hai phase là **mốc thời gian** trong default lifecycle; chúng **không tự sinh bất kỳ mã nào**. Một plugin goal cụ thể phải được bind vào phase đó và có cấu hình hợp lệ.

## 2. Đặt hai phase vào đúng trình tự

Một phần default lifecycle trên Maven 3.x:

~~~text
validate
   |
generate-sources          sinh mã Java chính
   |
process-sources
   |
generate-resources
   |
process-resources         copy/filter tài nguyên chính
   |
compile                   biên dịch main Java sources
   |
process-classes
   |
generate-test-sources     sinh mã Java chỉ dành cho test
   |
process-test-sources
   |
generate-test-resources
   |
process-test-resources
   |
test-compile              biên dịch test Java sources
   |
process-test-classes
   |
test                      chạy unit tests
   |
package                   tạo JAR/WAR...
   |
verify                    chạy các kiểm chứng đã được bind
~~~

Maven còn những phase trung gian không hiển thị trong sơ đồ này. Điểm quan trọng là:

- `generate-sources` nằm **trước** `compile`.
- `generate-test-sources` nằm **sau** main `compile` nhưng **trước** `test-compile`.
- `test` chạy sau khi cả mã chính và mã test đã được biên dịch.
- `package` và `verify` nằm quá muộn nếu mã sinh ra phải được dùng bởi compiler trong **cùng lần build**.

Một ví dụ dễ nhớ:

~~~text
input-schema.yaml
       |
       v
generator bind tại generate-sources
       |
       v
target/generated-sources/.../Client.java
       |
       v
main compiler (compile)
       |
       v
target/classes/.../Client.class
       |
       v
artifact JAR
~~~

Nếu generator là loại phục vụ test, thay `generate-sources` bằng `generate-test-sources`, `compile` bằng `test-compile`, và đích class bằng `target/test-classes`.

## 3. Khi nào chọn generate-sources, khi nào generate-test-sources?

| Câu hỏi | `generate-sources` | `generate-test-sources` |
| --- | --- | --- |
| Mục đích | Sinh mã Java của ứng dụng/thư viện | Sinh mã Java phục vụ kiểm thử |
| Ai sử dụng? | `src/main/java`, các class chính, có thể cả test | `src/test/java` và test runner |
| Phase compile tiếp theo | `compile` | `test-compile` |
| Source root điển hình | `target/generated-sources/<generator>` | `target/generated-test-sources/<generator>` |
| Class output điển hình | `target/classes` | `target/test-classes` |
| Được đóng vào JAR mặc định của project? | Class main được đóng gói thông thường | Không; test classes không nằm trong main JAR thông thường |
| Chạy khi `mvn compile`? | Có, nếu execution được bind và active | Chưa, vì chưa tới phase sinh mã test |
| Chạy khi `mvn test`? | Có | Có |
| Ví dụ | OpenAPI client, generated DTO, protobuf main model | Test fixtures, mock schema bindings, generated test cases |

**Không dùng `generate-test-sources` để sinh class mà `src/main/java` import.** Ở phase `compile`, file đó chưa được sinh/biên dịch; Java compiler sẽ báo `package ... does not exist` hoặc `cannot find symbol`.

**Không dùng `generate-sources` cho mã chỉ dùng trong unit test nếu không cần thiết.** Source được đăng ký làm main source có thể sinh ra class trong artifact phân phối, làm tăng API/footprint và có thể kéo dependency test vào mã chính.

## 4. Phân biệt generator, source root và compiler

Đây là ba trách nhiệm khác nhau:

| Thành phần | Công việc | Điều nó không tự bảo đảm |
| --- | --- | --- |
| **Code generator** | Tạo file `*.java` | Compiler sẽ tìm thấy thư mục chứa file |
| **Source-root registration** | Thêm thư mục generator vào danh sách source roots của Maven project | File đã được generator tạo ra, Java hợp lệ |
| **Maven Compiler Plugin** | Biên dịch các Java source mà nó nhận được | Tự chạy một generator riêng chưa được bind |

Maven Compiler Plugin thường biên dịch `src/main/java` và những source roots bổ sung được đăng ký. Thư mục dưới `target/generated-sources` **không nên được xem là tự động được Compiler Plugin quét trong mọi cấu hình**.

Có hai lựa chọn:

1. **Generator tự đăng ký source root** sau khi tạo mã. Nhiều plugin hiện đại cung cấp chức năng này.
2. **Dùng Maven Build Helper Plugin** để đăng ký thư mục sau/đồng thời với generator:
   - Goal `build-helper:add-source` cho main Java.
   - Goal `build-helper:add-test-source` cho test Java.

Chỉ dùng Build Helper **khi generator không tự làm việc này hoặc dự án cần đăng ký rõ ràng**. Đăng ký trùng source root thường không có ích và có thể gây nhầm khi chẩn đoán.

## 5. Cú pháp bind goal vào một phase

Một execution trong `pom.xml` mô tả phần “chạy goal nào, khi nào, với cấu hình gì”.

~~~xml
<plugin>
    <groupId>com.example.build</groupId>
    <artifactId>my-codegen-maven-plugin</artifactId>
    <version>1.0.0</version>
    <executions>
        <execution>
            <id>generate-main-model</id>
            <phase>generate-sources</phase>
            <goals>
                <goal>generate</goal>
            </goals>
            <configuration>
                <!-- Tham số thật phụ thuộc plugin đang dùng -->
            </configuration>
        </execution>
    </executions>
</plugin>
~~~

**Đây là đoạn cấu trúc minh họa, không phải plugin có thật được bảo đảm tồn tại trên Central.** Để sử dụng, cần thay bằng artifact/goal/parameter chính xác theo tài liệu plugin của công cụ sinh mã.

Bốn phần quan trọng:

- `<id>generate-main-model</id>`: tên execution, giúp nhận diện trong log.
- `<phase>generate-sources</phase>`: gắn execution vào phase.
- `<goals><goal>generate</goal></goals>`: chọn một goal của plugin.
- `<configuration>`: đường dẫn schema, output directory, ngôn ngữ, template hoặc tùy chọn generator.

Không đặt `<phase>generate-sources</phase>` trực tiếp dưới `<plugin>`; phase của một execution được khai báo **bên trong `<execution>`**.

Một plugin có thể có hai executions:

~~~xml
<executions>
    <execution>
        <id>generate-main</id>
        <phase>generate-sources</phase>
        <goals><goal>generate</goal></goals>
    </execution>
    <execution>
        <id>generate-test</id>
        <phase>generate-test-sources</phase>
        <goals><goal>generate</goal></goals>
    </execution>
</executions>
~~~

Ở đây hai goal và ID chỉ là minh họa. **Không tự giả định cùng một plugin hỗ trợ cả hai output hoặc cùng cấu hình cho hai phase.** Cần kiểm tra tài liệu goal để chắc chắn.

## 6. Thực hành đầy đủ Java 17: tạo hai class ở hai source set

Để tránh phụ thuộc vào OpenAPI server hoặc schema bên ngoài, bài thực hành dùng **Maven AntRun Plugin** sinh ra hai file Java một dòng bằng Ant `echo`. Đây là một *code generator tối giản* nhằm quan sát lifecycle; dự án sản xuất có thể thay AntRun bằng OpenAPI Generator, JAXB/XJC, protobuf compiler hoặc công cụ do tổ chức cung cấp.

Ta tạo:

- **Generated main class** `demo.generated.GeneratedGreeting` tại `generate-sources`.
- **Generated test helper** `demo.generatedtest.ExpectedMessage` tại `generate-test-sources`.
- **Main code do người viết** `demo.app.App` import/generated main class.
- **Unit test do người viết** `demo.app.AppTest` import/generated test class.
- **Build Helper Plugin** đăng ký source roots tương ứng, để compiler có thể nhìn thấy cả hai.

### 6.1. Cấu trúc dự án

Chỉ cần tạo các file do người viết:

~~~text
maven-codegen-lab/
├── pom.xml
└── src/
    ├── main/
    │   └── java/
    │       └── demo/app/App.java
    └── test/
        └── java/
            └── demo/app/AppTest.java
~~~

**Không tạo bằng tay** `GeneratedGreeting.java` hay `ExpectedMessage.java`. Maven sẽ tạo chúng trong `target` khi chạy lifecycle.

Sau build, một phần cấu trúc đầu ra dự kiến:

~~~text
target/
├── generated-sources/
│   └── tutorial/
│       └── demo/generated/GeneratedGreeting.java
├── generated-test-sources/
│   └── tutorial/
│       └── demo/generatedtest/ExpectedMessage.java
├── classes/
│   ├── demo/app/App.class
│   └── demo/generated/GeneratedGreeting.class
├── test-classes/
│   ├── demo/app/AppTest.class
│   └── demo/generatedtest/ExpectedMessage.class
└── maven-codegen-lab-1.0.0.jar
~~~

Điểm cần chứng minh: **generated test helper nằm trong `target/test-classes`, không trong main JAR**.

### 6.2. `pom.xml` hoàn chỉnh

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>demo.codegen</groupId>
    <artifactId>maven-codegen-lab</artifactId>
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
                <version>3.2.5</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-jar-plugin</artifactId>
                <version>3.4.2</version>
            </plugin>

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-antrun-plugin</artifactId>
                <version>3.1.0</version>
                <executions>
                    <execution>
                        <id>generate-main-java</id>
                        <phase>generate-sources</phase>
                        <goals>
                            <goal>run</goal>
                        </goals>
                        <configuration>
                            <target>
                                <mkdir dir="${project.build.directory}/generated-sources/tutorial/demo/generated"/>
                                <echo
                                    file="${project.build.directory}/generated-sources/tutorial/demo/generated/GeneratedGreeting.java"
                                    encoding="UTF-8"
                                    message='package demo.generated; public final class GeneratedGreeting { private GeneratedGreeting() {} public static String text() { return "generated-main"; } }'/>
                            </target>
                        </configuration>
                    </execution>

                    <execution>
                        <id>generate-test-java</id>
                        <phase>generate-test-sources</phase>
                        <goals>
                            <goal>run</goal>
                        </goals>
                        <configuration>
                            <target>
                                <mkdir dir="${project.build.directory}/generated-test-sources/tutorial/demo/generatedtest"/>
                                <echo
                                    file="${project.build.directory}/generated-test-sources/tutorial/demo/generatedtest/ExpectedMessage.java"
                                    encoding="UTF-8"
                                    message='package demo.generatedtest; public final class ExpectedMessage { private ExpectedMessage() {} public static String value() { return "Hello generated-main"; } }'/>
                            </target>
                        </configuration>
                    </execution>
                </executions>
            </plugin>

            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>build-helper-maven-plugin</artifactId>
                <version>3.6.0</version>
                <executions>
                    <execution>
                        <id>register-generated-main-source</id>
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
                        <id>register-generated-test-source</id>
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
        </plugins>
    </build>
</project>
~~~

**Giải thích kỹ cấu hình:**

1. **AntRun có hai executions cùng goal `run`** nhưng mỗi execution gắn vào một phase khác nhau. Cả hai không chạy ngay khi Maven đọc POM; chúng chạy khi lifecycle đi tới phase tương ứng.
2. Ant `mkdir` tạo thư mục package, sau đó `echo` ghi nội dung file Java. Thuộc tính XML `message='...'` dùng dấu nháy đơn để nội dung Java được phép chứa dấu nháy kép `"generated-main"` mà không phá cú pháp XML.
3. Bản Java main sinh dưới `target/generated-sources/tutorial`. Build Helper `add-source` đăng ký **thư mục source root** này để compiler có thể quét package `demo/generated`.
4. Bản Java test sinh dưới `target/generated-test-sources/tutorial`. Build Helper `add-test-source` đăng ký nó làm **test source root**, không làm main source root.
5. **Build Helper không sinh file**: nó chỉ đăng ký root. Nếu AntRun không được thực thi, đường dẫn có thể được đăng ký mà không có Java source cần dùng.
6. AntRun được khai báo trước Build Helper trong phần `<plugins>`. Trên Maven 3, các executions cùng phase từ POM thường theo thứ tự khai báo; với ví dụ này, generator thực hiện trước bước đăng ký root. Dù compiler chỉ dùng source root ở phase sau, thứ tự rõ ràng giúp người học đọc log.
7. Maven Compiler Plugin được ghim version và dùng `maven.compiler.release=17`. Java 17+ cần có trong môi trường build.
8. JUnit Jupiter chỉ dùng cho test nên scope `test`. Surefire chạy test khi lifecycle tới phase `test`.
9. Nếu thay AntRun bằng code generator chuyên dụng **tự đăng ký generated source roots**, không nhất thiết cần Build Helper nữa. Đọc tài liệu plugin trước khi nhân đôi cấu hình.

Các phiên bản plugin trên là phiên bản ví dụ để thực hành ổn định, **không mang nghĩa mới nhất**.

### 6.3. `src/main/java/demo/app/App.java`

~~~java
package demo.app;

import demo.generated.GeneratedGreeting;

public final class App {
    private App() {
    }

    public static String message() {
        return "Hello " + GeneratedGreeting.text();
    }

    public static void main(String[] args) {
        System.out.println(message());
    }
}
~~~

Đây là class **do người viết**. Nó import `GeneratedGreeting`, trong khi class đó chưa tồn tại trước build. Vì thế dự án **phụ thuộc vào việc generator chạy trước compile**.

Nếu generator chỉ chạy ở `generate-test-sources`, `App.java` không thể compile tại phase `compile`. Đây là ví dụ trực quan về **vì sao main source phải dùng `generate-sources`**.

### 6.4. `src/test/java/demo/app/AppTest.java`

~~~java
package demo.app;

import static org.junit.jupiter.api.Assertions.assertEquals;

import demo.generatedtest.ExpectedMessage;
import org.junit.jupiter.api.Test;

class AppTest {
    @Test
    void mainCodeUsesGeneratedClass() {
        assertEquals("Hello generated-main", App.message());
    }

    @Test
    void testCodeUsesGeneratedTestHelper() {
        assertEquals(ExpectedMessage.value(), App.message());
    }
}
~~~

Bài kiểm thử thứ nhất xác nhận ứng dụng dùng được class main được sinh. Bài thứ hai xác nhận class `ExpectedMessage` thuộc generated **test** sources đã được Maven tạo và test compiler nhận thấy.

Điểm quan trọng: `ExpectedMessage` **không** được import ở `App.java`; chỉ code trong `src/test/java` sử dụng nó.

## 7. Chạy build từ trạng thái sạch

Từ thư mục chứa `pom.xml`, yêu cầu có JDK 17+ và Maven có quyền tải dependencies/plugins từ repository hợp lệ.

~~~bash
mvn -version
mvn -B -ntp clean test
~~~

Với project như trên, Maven đi qua các phase theo thứ tự:

~~~text
clean
generate-sources
  ├─ antrun:run (generate-main-java)
  └─ build-helper:add-source (register-generated-main-source)
compile
  └─ compiler:compile
generate-test-sources
  ├─ antrun:run (generate-test-java)
  └─ build-helper:add-test-source (register-generated-test-source)
test-compile
  └─ compiler:testCompile
test
  └─ surefire:test
~~~

Mô tả này **chỉ nêu những bước quan trọng**; Maven còn qua các phase rỗng và các goal như `resources:resources`, `resources:testResources`. Output thực tế có version plugin, execution ID và log nhiều hơn.

Nếu mọi file đúng, JUnit báo đại ý:

~~~text
Tests run: 2, Failures: 0, Errors: 0, Skipped: 0
BUILD SUCCESS
~~~

Đây là trích đoạn rút gọn của báo cáo test. Một Maven build có thể in thêm thông tin về thời gian, paths, test class và plugin goals.

**Vì sao `mvn clean test` là thử nghiệm có ý nghĩa?** Nếu generator không được bind hoặc source roots không được đăng ký, project này sẽ compile/test fail từ `target` sạch; không có generated files cũ để vô tình che lỗi.

## 8. Chạy ứng dụng và kiểm tra artifact

Để tạo JAR:

~~~bash
mvn -B -ntp clean package
~~~

Sau lệnh này, JAR chính thông thường là:

~~~text
target/maven-codegen-lab-1.0.0.jar
~~~

Chạy ứng dụng từ compiled classes:

~~~bash
java -cp target/classes demo.app.App
~~~

**Stdout chính xác:**

~~~text
Hello generated-main
~~~

Không cần thêm runtime JAR cho class chính vì `App` và `GeneratedGreeting` chỉ dùng Java standard library. `JUnit` và các Maven plugins **không** cần nằm trên runtime classpath để chạy `App`.

Kiểm tra JAR:

~~~bash
jar tf target/maven-codegen-lab-1.0.0.jar
~~~

Trong danh sách entry, bạn phải thấy các class main:

~~~text
demo/app/App.class
demo/generated/GeneratedGreeting.class
~~~

Nhưng **không** thấy:

~~~text
demo/app/AppTest.class
demo/generatedtest/ExpectedMessage.class
~~~

Hai class test nằm trong `target/test-classes`, không thuộc main JAR mặc định. Nếu bạn chủ động dùng Maven Test JAR Plugin hoặc đóng gói đặc thù, artifact test riêng có thể chứa chúng; điều đó khác với JAR chính trong ví dụ.

### 8.1. Kiểm tra bằng javap

Sau khi đã build:

~~~bash
javap -classpath target/classes demo.generated.GeneratedGreeting
javap -classpath target/test-classes demo.generatedtest.ExpectedMessage
~~~

Công cụ `javap` của JDK giúp xác định class đã được biên dịch đúng nơi. Nếu thử:

~~~bash
javap -classpath target/classes demo.generatedtest.ExpectedMessage
~~~

thông thường sẽ không tìm thấy test class, vì class này chỉ nằm trong `target/test-classes`. Đó là kết quả **đúng**, không phải lỗi generator.

## 9. Ba lệnh Maven không tương đương

| Lệnh | Generator main | Generator test | Main compile | Test compile/run |
| --- | :---: | :---: | :---: | :---: |
| `mvn clean generate-sources` | Có | Không | Không | Không |
| `mvn clean compile` | Có | Không | Có | Không |
| `mvn clean test` | Có | Có | Có | Có |
| `mvn clean package` | Có | Có | Có | Có, rồi đóng gói |
| `mvn clean verify` | Có | Có | Có | Có, cùng các goal verify được bind |

Bảng đúng với **POM ví dụ** và các lifecycle bindings thông dụng. Chú ý: `mvn clean generate-test-sources` cũng đi qua `compile` trước khi tới `generate-test-sources`; không có chuyện “chạy generator test nhưng bỏ qua biên dịch main” khi gọi phase theo lifecycle thông thường.

### 9.1. Nếu chỉ gọi compiler goal trực tiếp

~~~bash
mvn -B -ntp clean compiler:compile
~~~

Goal compiler được gọi trực tiếp, không đồng nghĩa đã chạy phase `generate-sources`. Từ trạng thái sạch, `App.java` import `demo.generated.GeneratedGreeting` nên compiler có thể báo:

~~~text
package demo.generated does not exist
cannot find symbol
~~~

Đây là lỗi **có chủ đích nếu bạn bỏ qua generator**, không phải Maven/Java 17 tự làm sai. Cách thông thường để build là gọi phase:

~~~bash
mvn -B -ntp clean compile
~~~

Maven sẽ chạy generator, Build Helper và compiler theo lifecycle.

Một số plugin goal có metadata fork lifecycle hoặc thực hiện chuẩn bị riêng; vì vậy không nói mọi direct goal *tuyệt đối* không chạy gì khác. Nhưng với ví dụ Compiler Plugin, không nên coi `compiler:compile` là tên khác của phase `compile`.

### 9.2. Nếu chỉ gọi generate-test-sources

~~~bash
mvn -B -ntp clean generate-test-sources
~~~

Lệnh chạy các phase đến `generate-test-sources`, bao gồm biên dịch main trước đó. Bản generated test source đã được tạo và đăng ký, nhưng phase `test-compile` **chưa chạy**; do đó chưa nên kỳ vọng có `ExpectedMessage.class` trong `target/test-classes`.

Muốn biên dịch test:

~~~bash
mvn -B -ntp test-compile
~~~

Muốn chạy test:

~~~bash
mvn -B -ntp test
~~~

Để kiểm chứng từ đầu, nên dùng `mvn -B -ntp clean test` hoặc `clean verify` theo mục tiêu.

## 10. Vai trò của Build Helper Plugin

Maven Build Helper Plugin có nhiều goals. Hai goal quan trọng cho chủ đề này:

**`build-helper:add-source`**

~~~xml
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
~~~

**`build-helper:add-test-source`**

~~~xml
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
~~~

Hai đoạn trên là **trích đoạn execution** thuộc `org.codehaus.mojo:build-helper-maven-plugin`, không phải POM độc lập.

Các đường dẫn phải trỏ đến **thư mục gốc của package hierarchy**, không phải chính file `.java`. Với `package demo.generated;`, source root là:

~~~text
target/generated-sources/tutorial
~~~

và file là:

~~~text
target/generated-sources/tutorial/demo/generated/GeneratedGreeting.java
~~~

Nếu đặt source root thành `target/generated-sources/tutorial/demo/generated` thì package-relative path không còn đúng theo quy ước Java source layout, làm IDE hoặc compiler xử lý khó đoán.

**Lưu ý:** Goal Build Helper chỉ thêm source root vào Maven project model trong phiên build. Nó không tự tạo source, không tự biên dịch Java, và không biến generated main source thành test source chỉ vì tên file chứa từ “test”.

## 11. Generator có thể tự đăng ký nguồn: khi nào bỏ Build Helper?

Ví dụ các Maven plugins sinh mã thực tế thường có những tham số kiểu:

- `outputDirectory` — nơi ghi file.
- `sourceRoot` hoặc `generatedSourcesDirectory` — thư mục chứa mã Java sinh ra.
- Cờ `addCompileSourceRoot`, `addTestCompileSourceRoot` hoặc tính năng tương tự, **tùy plugin**.
- `skip`/`skipIfSpecIsUnchanged` để giảm chi phí sinh mã trong một số tình huống.
- Đường dẫn schema, namespace/package name, generatorName hoặc template.

**Không giả định tất cả các plugin dùng cùng tên parameter.** Xem tài liệu và plugin descriptor của đúng goal/version:

~~~bash
mvn -B -ntp help:describe -Dplugin=org.codehaus.mojo:build-helper-maven-plugin -Dgoal=add-source -Ddetail
~~~

Có thể dùng:

~~~bash
mvn -B -ntp help:describe -Dplugin=org.apache.maven.plugins:maven-compiler-plugin -Dgoal=compile -Ddetail
~~~

để xem parameters của Compiler Plugin.

Nếu plugin tự thêm source root, giữ Build Helper có thể khiến danh sách root bị lặp hoặc log khó đọc. Cách chốt là kiểm tra **đường dẫn generated source có trong compile/testCompile source roots không**, rồi build từ clean.

## 12. Ví dụ gần thực tế: sinh OpenAPI client

Một project dùng OpenAPI có thể cần client Java để `src/main/java` gọi API. Khi đó generator nên chạy **trước main compile**, thường ở `generate-sources`. Ví dụ đoạn plugin **chỉ mang tính minh họa cấu hình**, yêu cầu file OpenAPI spec thực tế tại `src/main/openapi/service.yaml`:

~~~xml
<plugin>
    <groupId>org.openapitools</groupId>
    <artifactId>openapi-generator-maven-plugin</artifactId>
    <version>7.9.0</version>
    <executions>
        <execution>
            <id>generate-api-client</id>
            <phase>generate-sources</phase>
            <goals>
                <goal>generate</goal>
            </goals>
            <configuration>
                <inputSpec>${project.basedir}/src/main/openapi/service.yaml</inputSpec>
                <generatorName>java</generatorName>
                <apiPackage>demo.client.api</apiPackage>
                <modelPackage>demo.client.model</modelPackage>
                <output>${project.build.directory}/generated-sources/openapi</output>
            </configuration>
        </execution>
    </executions>
</plugin>
~~~

**Đây không phải bài thực hành có thể chạy độc lập như ở mục 6**: nó cần file OpenAPI spec có nội dung hợp lệ; generated client có thể cần các dependencies bổ sung tùy library, transport, serialization options và generator version. Cần đọc tài liệu OpenAPI Generator để biết source root thực tế của generated Java và cơ chế tự đăng ký nó.

Điểm muốn minh họa không phải mọi parameter của OpenAPI Generator, mà là **đúng phase**: client code được sinh trước khi compiler cần import và biên dịch nó. Nếu spec chỉ phục vụ test, cân nhắc một execution/generator phù hợp và phase `generate-test-sources`, với test source root rõ ràng.

## 13. JAXB, protobuf, database và annotation processing

Không phải mọi công cụ sinh Java nên được bind giống hệt.

- **JAXB/XJC** sinh classes từ XSD/schema: thường chạy ở `generate-sources` nếu main code cần dùng các class được sinh; hoặc sinh vào test source set nếu chỉ test.
- **Protobuf** có compiler `protoc` và Maven plugin hỗ trợ main/test generation; cần cấu hình schema paths, output roots và platform/toolchain thích hợp.
- **Database schema generator** có thể cần database/service đang chạy. Phải cân nhắc tái lập build, quyền truy cập CI, môi trường offline và tránh biến build thành phụ thuộc vào database production.
- **Annotation processors** như một số công cụ sinh code qua javac có thể chạy **ngay trong phase compile hoặc testCompile**, theo Maven Compiler Plugin, không nhất thiết cần một execution riêng ở `generate-sources`. Không tự gắn annotation processor vào AntRun trước compiler nếu công cụ được thiết kế hoạt động như javac annotation processor.
- **Generator sinh resource, không phải Java**: thường phù hợp `generate-resources` hoặc `generate-test-resources`, rồi được Resources Plugin copy vào classpath.

Cần xác định **công cụ sinh ra file gì, vào lúc nào và plugin nào tiêu thụ nó**. Không ép mọi generator vào `generate-sources` chỉ vì có chữ “generate”.

## 14. Thứ tự giữa generator và source-root registration

Hai executions có thể cùng phase `generate-sources`, nhưng thuộc hai plugin khác nhau:

~~~text
generate-sources:
    1. antrun:run       → tạo GeneratedGreeting.java
    2. build-helper:add-source → đăng ký generated-sources/tutorial

compile:
    3. compiler:compile → nhận source và biên dịch
~~~

Trong demo, thứ tự plugin declaration làm log dễ hiểu. Với Maven 3, các executions trong POM thường theo thứ tự khai báo trong cùng phase sau bindings mặc định từ packaging. Tuy vậy:

- Nếu generator có **default phase khác**, cần bind tường minh.
- Nếu parent POM/profile chèn execution, thứ tự hiệu lực có thể thay đổi.
- Nếu Maven chạy Reactor song song, không để nhiều modules ghi vào **cùng một output directory**.
- Nếu build cần thứ tự chặt chẽ, kiểm tra actual execution plan và log; đừng chỉ dựa vào việc folder đã tồn tại từ build trước.

Trong ví dụ, đăng ký source root ngay trước khi tạo file vẫn có thể hoạt động vì compiler chạy ở phase sau; nhưng việc thể hiện producer trước registration giúp dễ quan sát và giảm nhầm lẫn khi thay bằng generator phức tạp.

Một **quy tắc thiết kế tốt hơn** là generator tự quản lý output/source roots khi nó hỗ trợ, hoặc ít nhất dùng những phase riêng phù hợp khi có producer/consumer khác nhau.

## 15. Chạy đúng trên một module trong multi-module reactor

Giả sử project:

~~~text
enterprise-system/
├── pom.xml                   (packaging pom)
├── api-client/
│   └── pom.xml               (packaging jar)
├── service/
│   └── pom.xml               (packaging jar)
└── tests/
    └── pom.xml               (packaging jar)
~~~

Nếu generator chỉ cần cho `api-client`, nên đặt execution ở module đó hoặc quản lý inheritance một cách có chủ đích. Đặt cùng execution trong parent `<build><plugins>` có thể khiến nó chạy cả trong module `service`, `tests` hoặc parent package `pom`.

Lựa chọn:

1. Dùng parent `<pluginManagement>` để ghim plugin version/configuration **mà không tự áp dụng execution lên mọi module**.
2. Đặt `<build><plugins>` và execution thực ở các module cần generator.
3. Nếu parent cần plugin nhưng không muốn child kế thừa, xem thuộc tính `<inherited>false</inherited>` theo vị trí phù hợp.
4. Dùng `${project.build.directory}` để mỗi module ghi vào `target` của chính nó, không ghi chung một thư mục ở Reactor root trừ khi có cơ chế đồng bộ rõ ràng.
5. Kiểm tra goal có phải aggregator hay cần chạy mỗi module; không suy ra từ tên plugin.

Chạy một module cùng các dependency reactor cần thiết:

~~~bash
mvn -B -ntp -pl :service -am clean test
~~~

Đây là **lệnh mẫu** cho project có module artifactId `service`; không dùng nguyên lệnh này trong dự án một module ở mục 6. `-am` yêu cầu Maven chọn/build thêm các module dự án đang phụ thuộc khi phù hợp. Nó không tự sửa source root hoặc làm generator của module sai bỗng hoạt động đúng.

## 16. Kết hợp với profiles và cấu hình theo môi trường

Có thể gắn generator vào profile nếu chỉ một số mục tiêu cần sinh mã:

~~~xml
<profiles>
    <profile>
        <id>generate-client</id>
        <build>
            <plugins>
                <!-- Khai báo plugin generator và execution phù hợp -->
            </plugins>
        </build>
    </profile>
</profiles>
~~~

Đây là **đoạn cấu trúc minh họa**, không phải POM hoàn chỉnh.

Khi chạy:

~~~bash
mvn -B -ntp -Pgenerate-client clean compile
~~~

profile góp cấu hình vào effective POM nếu được kích hoạt. Nhưng nếu mã chính **luôn** import generated class, generator không thể chỉ tồn tại trong profile được bật tùy ý trừ khi có giải pháp thay thế. Một lần CI quên `-Pgenerate-client` sẽ fail.

Hãy phân biệt:

- Profile dùng để thay đổi **generator input/output hoặc tính năng tùy chọn**.
- Execution cần thiết cho **mọi clean build** thường nên nằm trong POM nền, thay vì chỉ có trong profile ít người biết.
- Nếu generator bị skip trên CI, cần kiểm tra cả profile activation và plugin-specific skip properties.

Khi so sánh local/CI, dùng cùng `-P`, `-D`, `-s`, JDK, Maven version và working directory. Đừng kết luận đơn giản rằng “trên IDE import được thì Maven CLI cũng thấy”.

## 17. IDE và generated source roots

IDE có thể nhận ra hoặc không nhận ra generated source roots ngay khi mở project. Có IDE chỉ đánh dấu thư mục sau khi Maven import hoặc chạy phase `generate-sources`/`generate-test-sources`.

Một quy trình an toàn:

1. Chạy `mvn clean test` từ CLI để kiểm tra build **không phụ thuộc IDE**.
2. Đồng bộ/reimport Maven project trong IDE.
3. Kiểm tra thư mục generated main được đánh dấu như source root, generated test được đánh dấu test source root.
4. Đảm bảo IDE không commit generated Java dưới `target` như mã viết tay.
5. Nếu IDE báo lỗi đỏ nhưng CLI PASS, phân biệt vấn đề **project model trong IDE** với vấn đề Maven lifecycle.
6. Nếu CLI FAIL, không chữa bằng cách chỉ “Mark Directory as Sources Root” trong IDE; POM/goal registration phải đúng để CI cũng thành công.

Một số generator plugins có tích hợp IDE qua lifecycle mapping đặc thù hoặc cần hỗ trợ IDE-specific configuration. Đó là lớp tích hợp bổ sung, không thay thế POM sạch và tái lập.

## 18. Incremental build, cache và nguồn sinh cũ

Một lỗi nguy hiểm: generator bị gắn sai phase nhưng developer vẫn build được vì file `GeneratedGreeting.java` hoặc `GeneratedGreeting.class` còn từ lần chạy trước.

Thực hành:

~~~bash
mvn -B -ntp clean test
~~~

là phép kiểm tra đơn giản để loại bỏ nhiều dạng stale output dưới `target`. Nếu cần chứng minh generator hoạt động đúng:

- Kiểm tra log execution `generate-main-java` và `generate-test-java`.
- Kiểm tra timestamp/hash của generated output.
- Đảm bảo schema/template chính xác nằm trong source-controlled inputs.
- Đảm bảo generator deterministic nếu build yêu cầu reproducible artifacts.
- Xác định cơ chế skip hoặc incremental logic nếu plugin có hỗ trợ, kể cả cách nó phát hiện thay đổi schema.
- Không sửa generated output bằng tay rồi dựa vào file đó để build.

Nếu plugin sinh mã từ nguồn bên ngoài không bất biến (database remote, API live, schema URL không khóa version), clean build vẫn có thể cho kết quả khác nhau. Muốn tái lập, quản lý inputs, version và mạng phù hợp.

Maven Wrapper giúp khóa **Maven distribution** mà dự án dùng; nhưng bạn vẫn cần ghim **generator/plugin version**, compiler/JDK/toolchains và inputs cần thiết. Một wrapper không tự khóa mọi version của tất cả plugins.

## 19. Có cần phân biệt skipTests với maven.test.skip?

Có. Khi test generator được bind vào `generate-test-sources`:

- `-DskipTests` thường khiến Surefire **bỏ qua việc thực thi test**, nhưng vẫn cho phép Maven đi qua các phase và biên dịch test sources theo cấu hình bình thường.
- `-Dmaven.test.skip=true` được một số plugins như Compiler/Surefire hỗ trợ để **bỏ qua cả biên dịch test** hoặc test execution; tuy vậy một generator tùy biến bind ở `generate-test-sources` **không tự biết** cờ này trừ khi bạn cấu hình skip cho chính goal/plugin ấy.
- `-DskipTests` và `-Dmaven.test.skip=true` **không giống nhau**; cũng không nên dùng làm giải pháp “sửa” lỗi generator hoặc test.
- Nếu code sinh ra chỉ phục vụ test nhưng quá tốn thời gian, hãy thiết kế skip riêng có cơ chế/flag thống nhất, thay vì ngầm cho rằng mọi plugin đều hiểu cờ của Surefire.

Ví dụ so sánh:

~~~bash
mvn -B -ntp clean package -DskipTests
mvn -B -ntp clean package -Dmaven.test.skip=true
~~~

Hai lệnh có thể tạo kết quả test-class/test-run khác nhau, tùy plugin và cấu hình. Trong bài lab, **hãy chạy không skip trước** để có bằng chứng hai loại source đều được tạo, biên dịch và kiểm thử.

## 20. Những lỗi thường gặp và cách sửa

| Triệu chứng | Nguyên nhân khả dĩ | Cách kiểm tra/sửa |
| --- | --- | --- |
| `package demo.generated does not exist` khi compile | Generator chưa chạy, sai phase, bị skip hoặc main source root chưa đăng ký | Chạy `clean compile`; xem log `generate-sources` và `build-helper:add-source` |
| `package demo.generatedtest does not exist` khi testCompile | Test generator/registration chưa chạy hoặc đường dẫn sai | Xem `generate-test-sources` và `add-test-source`; dùng `clean test` |
| File `.java` tồn tại nhưng javac không nhìn thấy | Source root không đúng, package/path sai, plugin chưa đăng ký root | Kiểm tra root ở parent của `demo/...` và execution Build Helper |
| Generated main class xuất hiện trong `target/test-classes` | Main generator bị gắn nhầm test phase/root | Chuyển sang `generate-sources` và `add-source` |
| Generated test helper xuất hiện trong main JAR | Test code sinh dưới main source root | Đưa sang `generated-test-sources` và `add-test-source` |
| `mvn compiler:compile` fail nhưng `mvn compile` PASS | Gọi trực tiếp compiler bỏ qua generator lifecycle | Gọi phase `compile`; đừng dùng direct goal thay toàn build |
| CLI PASS, IDE báo thiếu class | IDE chưa import generated roots hoặc chưa chạy generator | Reimport Maven, chạy phase, kiểm tra IDE source-root model |
| Chỉ build được khi không clean | Output cũ còn trong `target` | Rà lại binding/order, chạy clean build trên CI |
| Maven báo `Failed to execute goal ... antrun:run` | Ant target không tạo được file, path/permissions sai | Đọc lỗi Ant đầu tiên, kiểm tra output directory |
| Generator chạy nhiều lần trên reactor | Execution bị kế thừa vào nhiều modules | Đặt ở module phù hợp, quản lý inheritance |
| Version generator khác giữa CI và local | Không ghim plugin, Maven/profile/settings khác nhau | Ghim version và đồng bộ môi trường |
| Test generator bị bỏ qua ở lệnh `mvn compile` | `generate-test-sources` nằm sau `compile` | Dùng `mvn test` hoặc `test-compile` |
| POM có `<pluginManagement>` nhưng không sinh file | Plugin chưa được áp dụng/executed | Khai báo plugin execution trong `<build><plugins>` |
| Sinh source bị ghi thẳng vào `src/main/java` | Generator output đặt ở source tree | Dời về `target/generated-sources`; tránh ghi đè source thủ công |
| Code sinh ra compile lỗi dù file có mặt | Generator sinh cú pháp Java sai hoặc thiếu dependency cho source mới | Đọc file sinh, dùng đúng generator version/options và dependencies |

**Đọc lỗi đầu tiên** trong log. Nếu lỗi là `PluginResolutionException`, Maven chưa tải được plugin; sửa `pluginRepositories`/repository/settings hoặc version. Nếu plugin chạy thành công nhưng compiler không thấy class, vấn đề thường là phase, source root, output hoặc code sinh ra. Đây là hai nhóm lỗi khác nhau.

## 21. Cách kiểm tra cấu hình hiệu lực

### 21.1. Effective POM

~~~bash
mvn -B -ntp help:effective-pom -Doutput=effective-pom.xml
~~~

Tìm:

- `maven-antrun-plugin` và executions `generate-main-java`, `generate-test-java`.
- `<phase>generate-sources</phase>` và `<phase>generate-test-sources</phase>`.
- `build-helper-maven-plugin`, goals `add-source` và `add-test-source`.
- Các output paths dưới `${project.build.directory}`.
- Các parent/profile overrides có thể làm thay version, phase hoặc skip.

**Effective POM mô tả cấu hình**, không chứng minh goal đã chạy. Cần đối chiếu log và file output.

### 21.2. Maven build log

~~~bash
mvn -B -ntp clean test
~~~

Quan sát những execution IDs:

~~~text
... antrun:3.1.0:run (generate-main-java) ...
... build-helper:3.6.0:add-source (register-generated-main-source) ...
... compiler:3.13.0:compile (default-compile) ...
... antrun:3.1.0:run (generate-test-java) ...
... build-helper:3.6.0:add-test-source (register-generated-test-source) ...
... compiler:3.13.0:testCompile (default-testCompile) ...
... surefire:3.2.5:test (default-test) ...
~~~

Đây chỉ là **trích đoạn log minh họa**, không phải transcript được chạy trên máy cụ thể. Maven có thể in version/format khác hoặc thông tin goal bổ sung. Hãy xem **thứ tự tương đối và ID**, không chỉ chuỗi text.

### 21.3. Lệnh kiểm tra Java bytecode

Sau `mvn clean test`:

~~~bash
javap -classpath target/classes demo.generated.GeneratedGreeting
javap -classpath target/test-classes demo.generatedtest.ExpectedMessage
~~~

Nếu class đầu chỉ có trong test-classes, bạn đã đăng ký sai source root. Nếu class thứ hai nằm trong main classes, bạn có thể đã làm lộ test helper vào artifact chính.

### 21.4. Xem generated file và thông báo compiler

Trong project thực, có thể bật chi tiết log Maven với `mvn -X` để điều tra source roots khi cần. Nhưng debug log có thể chứa URL repository, đường dẫn hoặc thông tin nhạy cảm; chỉ chia sẻ sau khi lọc. Với generated file, dùng IDE hoặc trình đọc text kiểm tra package declaration và tên class, không chỉ tin vào tên thư mục.

## 22. Source generation không đồng nghĩa resource generation

Một lỗi lập kế hoạch phổ biến là trộn file `.java` với `.properties` hoặc `.json`.

**Mã Java sinh ra** cần compiler xử lý:

~~~text
generate-sources → compile
generate-test-sources → test-compile
~~~

**Resource sinh ra** cần được đưa vào resource/classpath:

~~~text
generate-resources → process-resources
generate-test-resources → process-test-resources
~~~

Nếu generator tạo file cấu hình `build-info.properties`, chạy ở `generate-sources` có thể vẫn tạo file nhưng không có nghĩa Resources Plugin biết để copy nó. Cần chọn phase và resource directory đúng. Ngược lại, một Java class không tự được biên dịch vì bạn đặt file trong `target/generated-resources`.

Không thể quyết định phase chỉ dựa vào tên plugin `generate`; phải biết **định dạng output và consumer tiếp theo**.

## 23. Quản lý bảo mật và chất lượng của mã sinh

Generated source cũng là **mã sẽ được build/chạy**, nên không được xem nó là kết quả “vô hại” chỉ vì không do người viết trực tiếp.

- **Nguồn schema/template** phải có nguồn gốc rõ ràng và version được kiểm soát.
- **Generator plugin** là mã thực thi trên build runner; ghim phiên bản và dùng repository đáng tin.
- **Không nhúng secret** như API token, password, private key vào Java source hoặc artifact.
- **Không để generator ghi file tùy ý ngoài `target`** trừ khi đã review side effects.
- **Không kéo schema sống từ production** trong mỗi build nếu có thể khiến build không tái lập hoặc lộ dữ liệu.
- **Không commit generated files một cách thiếu quy tắc**; nếu tổ chức quyết định commit, phải có quy trình đồng bộ rõ ràng để tránh xung đột giữa source và generated output.
- **Sử dụng namespace/package riêng** cho mã sinh để giảm trùng class với source viết tay.
- **Kiểm tra lỗi compiler và test** trên generated code; output parse được chưa chắc dùng đúng API/runtime.
- **Kiểm tra khác biệt giữa generator versions**, đặc biệt nếu serialization model hoặc API signatures thay đổi.
- **Tái lập trong CI sạch** với JDK/toolchain, Maven và input files như build release.

Một hệ thống dùng OpenAPI, protobuf hoặc annotation processor cần xét thêm yêu cầu license, binary compatibility và bảo vệ thông tin nội bộ. Việc plugin generator chạy tại `generate-sources` không thay thế những bước đánh giá đó.

## 24. Bài tập thực hành có đáp án

1. **Ứng dụng import class được sinh từ OpenAPI schema. Chọn `generate-sources` hay `generate-test-sources`?**  
   **Đáp án:** `generate-sources`, vì main compiler cần class trước `compile`.

2. **Unit test cần helper class sinh từ test schema; ứng dụng không dùng class này. Chọn phase nào?**  
   **Đáp án:** `generate-test-sources` và test source root, để helper đi vào `target/test-classes`.

3. **File Java được sinh dưới `target/generated-sources/custom` nhưng compiler báo không tìm thấy package. Kiểm tra gì?**  
   **Đáp án:** Goal generator đã chạy chưa, path/package có khớp không và source root đã được đăng ký qua generator hoặc `build-helper:add-source` chưa.

4. **`build-helper:add-source` có sinh file Java không?**  
   **Đáp án:** Không, chỉ đăng ký thư mục nguồn bổ sung.

5. **`build-helper:add-test-source` đưa file vào main JAR không?**  
   **Đáp án:** Không theo packaging JAR thông thường; nó thêm test source root để test compiler biên dịch.

6. **`mvn clean compile` có chạy generator bind ở `generate-test-sources` không?**  
   **Đáp án:** Không; phase ấy nằm sau `compile`.

7. **`mvn clean test` có chạy cả hai generator trong demo không?**  
   **Đáp án:** Có, vì lifecycle đi qua cả `generate-sources` và `generate-test-sources`.

8. **Vì sao `mvn clean compiler:compile` có thể fail trong demo?**  
   **Đáp án:** Gọi riêng compiler goal không mặc nhiên chạy generator và source-root registration trước đó.

9. **Khi `GeneratedGreeting.java` được sinh ở `generate-test-sources` nhưng `App.java` import nó, lỗi gì dễ xảy ra?**  
   **Đáp án:** Main compile thiếu class vì test generator chạy quá muộn.

10. **Một generator đã tự add main source root. Có nhất thiết dùng Build Helper không?**  
    **Đáp án:** Không. Tránh đăng ký trùng khi không cần.

11. **Generated test helper có thể chứa JUnit API mà không làm JUnit thành main runtime dependency không?**  
    **Đáp án:** Có, nếu helper thuộc test source set và JUnit scope `test`; không đưa helper vào main source set.

12. **Làm sao kiểm tra mã sinh chỉ dành cho test không vào main artifact?**  
    **Đáp án:** Dùng `jar tf` xem main JAR; kiểm tra class có trong `target/test-classes` chứ không trong `target/classes`.

13. **Generator chạy được trên IDE nhưng CI không. Nên kiểm tra điều gì trước?**  
    **Đáp án:** CLI clean build, POM execution phase, source root, plugin version, profiles và schema input.

14. **Lệnh `mvn test-compile` có đi qua `generate-test-sources` không?**  
    **Đáp án:** Có, khi gọi theo phase thông thường của default lifecycle.

15. **Một plugin có goal `generate`. Có nên mặc định bind nó vào `generate-sources`?**  
    **Đáp án:** Không. Cần biết nó tạo mã Java chính, mã test, resources hay thứ khác và xem defaultPhase của goal.

16. **Generator chỉ được khai báo trong `<pluginManagement>`. Điều gì xảy ra?**  
    **Đáp án:** Nó không tự tạo một execution mới; phải được áp dụng qua plugin/lifecycle phù hợp.

17. **Thêm `-DskipTests` có chắc test generator không chạy?**  
    **Đáp án:** Không. Cờ của test runner không tự là cờ skip của generator.

18. **Cách dễ nhất để phát hiện generated files cũ che lỗi phase?**  
    **Đáp án:** Chạy `mvn clean test` từ output sạch và kiểm tra log/output của generator.

19. **Nếu generator thực sự là annotation processor chạy trong javac, có nhất thiết bind vào `generate-sources`?**  
    **Đáp án:** Không. Dùng cấu hình annotation processing phù hợp của compiler plugin; tránh chạy generator sai thời điểm.

20. **Nếu generator tạo `.properties`, phase nào thích hợp?**  
    **Đáp án:** Thường `generate-resources` hoặc `generate-test-resources`, cộng cấu hình Resources Plugin để copy vào classpath.

## 25. Checklist khi thêm code generator vào Maven

- [ ] Tôi biết generator sinh **main Java**, **test Java** hay **resource**.
- [ ] Tôi chọn `generate-sources` cho mã chính và `generate-test-sources` cho mã test khi phù hợp.
- [ ] Tôi đã xác định schema, template và inputs mà generator cần.
- [ ] Tôi đã ghim version Maven plugin/generator thích hợp.
- [ ] Tôi đã khai báo plugin trong `<build><plugins>` và execution ID rõ ràng.
- [ ] Tôi đã kiểm tra goal name, `<phase>` và plugin-specific parameters.
- [ ] Tôi dùng output path dưới `${project.build.directory}`, tránh ghi vào source do con người quản lý.
- [ ] Tôi đã xác định generator có tự đăng ký source root hay cần Build Helper.
- [ ] Nếu cần, đã dùng `add-source` hoặc `add-test-source` đúng source set.
- [ ] Source root trỏ tới thư mục cha của package hierarchy.
- [ ] Tôi không vô tình làm test helper xuất hiện trong main artifact.
- [ ] Tôi đã chạy `mvn clean test` từ trạng thái sạch và xem hai nguồn mã được compile.
- [ ] Tôi đã kiểm tra output bằng `javap` hoặc `jar tf` khi cần.
- [ ] Tôi không dùng direct `compiler:compile` thay cho phase `compile` nếu generator là prerequisite.
- [ ] Tôi hiểu hành vi skip tests có thể khác hành vi skip generator.
- [ ] Tôi đã kiểm tra profiles, plugin inheritance và module scope trong Reactor.
- [ ] Tôi đã đồng bộ generated source roots với IDE theo project Maven.
- [ ] Generator không dùng secret hoặc nguồn dữ liệu production không kiểm soát.
- [ ] Tôi đã rà soát generated code/API compatibility và test thực tế.
- [ ] Tôi đã xác minh build tái lập trên CI với JDK/Maven/settings thích hợp.

## Tài liệu Maven chính thức và tài liệu plugin

- [Apache Maven — Introduction to the Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html): thứ tự `generate-sources`, `generate-test-sources`, `compile`, `test-compile`, và mối quan hệ phase/goal.
- [Apache Maven — Guide to Configuring Plugins](https://maven.apache.org/guides/mini/guide-configuring-plugins.html): `<executions>`, `<phase>`, plugin configuration và default phase.
- [Apache Maven — POM Reference](https://maven.apache.org/pom.html): `<build><plugins>`, pluginManagement, inheritance và build directories.
- [Maven Build Helper Plugin — add-source](https://www.mojohaus.org/build-helper-maven-plugin/add-source-mojo.html): đăng ký source roots bổ sung cho main compile.
- [Maven Build Helper Plugin — add-test-source](https://www.mojohaus.org/build-helper-maven-plugin/add-test-source-mojo.html): đăng ký test source roots bổ sung.
- [Maven AntRun Plugin 3.1.0 — Usage](https://maven.apache.org/plugins-archives/maven-antrun-plugin-3.1.0/usage.html): chạy Ant target trong Maven lifecycle.
- [Maven Compiler Plugin — Examples](https://maven.apache.org/plugins/maven-compiler-plugin/examples/): cấu hình Java compiler và source/annotation processing.
- [Maven Surefire Plugin](https://maven.apache.org/surefire/maven-surefire-plugin/): chạy JUnit tests ở phase `test`.
- [OpenAPI Generator — Maven Plugin](https://openapi-generator.tech/docs/plugins/): ví dụ cấu hình plugin sinh API client từ OpenAPI specs.

**Kết luận:** Việc gắn công cụ sinh mã vào Maven gồm **hai quyết định tách biệt**: **chọn phase đúng** để generator chạy trước consumer, và **đăng ký source root đúng** để compiler nhìn thấy Java được sinh. Dùng `generate-sources` cho mã chính, `generate-test-sources` cho mã chỉ phục vụ test; kiểm tra bằng một `mvn clean test` để loại trừ stale output. Khi hai phần này rõ ràng, IDE, CI và build phân phối sẽ dễ tái lập và chẩn đoán hơn.
