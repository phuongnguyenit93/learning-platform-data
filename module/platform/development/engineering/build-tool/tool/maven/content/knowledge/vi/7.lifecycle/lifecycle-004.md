# Maven generate-sources, process-sources và các bước xử lý mã nguồn

## 1. Mục tiêu của bài học

Khi làm việc với Maven, mã Java không phải lúc nào cũng được lập trình viên viết trực tiếp trong `src/main/java`. Một dự án có thể **sinh mã từ schema, API specification, template, mô hình dữ liệu hoặc annotation**, sau đó xử lý và đưa mã đó vào quá trình biên dịch. Hai phase **`generate-sources`** và **`process-sources`** là vị trí quan trọng để tích hợp những bước này với **default build lifecycle**.

Sau bài này, bạn sẽ có thể:

1. Phân biệt `generate-sources`, `process-sources`, `process-resources`, `compile` và `process-classes`.
2. Hiểu rằng phase là **điểm móc (hook)**, còn plugin goal mới thực hiện tác vụ thực tế; hiểu vì sao ở dự án `jar` thông thường hai phase đầu có thể không in ra công việc nào.
3. Tạo và kiểm tra một file Java trong `target/generated-sources/`, đăng ký nó làm **compile source root**, rồi biên dịch cùng mã trong `src/main/java`.
4. Chạy từng phase để quan sát kết quả, xử lý lỗi thiếu class được tạo, sai thứ tự plugin hoặc lẫn generated source vào Git.

Ví dụ hoàn chỉnh dùng **Java 17+**, Maven 3.x và ba plugin đã được phát hành: Maven AntRun Plugin 3.1.0, Build Helper Maven Plugin 3.6.0, Maven Compiler Plugin 3.14.1. Lần build đầu cần truy cập repository để tải plugin nếu máy chưa cache. Những phiên bản này được ghim nhằm cố định ví dụ; dự án thực tế có thể sử dụng phiên bản được nhóm kiểm chứng.

## 2. Vị trí của hai phase trong default lifecycle

Maven có ba lifecycle tích hợp là `clean`, `default` và `site`. Lệnh `mvn compile` hoặc `mvn package` là yêu cầu Maven chạy đến một **phase** thuộc default lifecycle, bao gồm mọi phase đứng trước phase được gọi, theo thứ tự.

Phần đầu của **default lifecycle** diễn ra như sau:

~~~text
validate
   |
initialize
   |
generate-sources
   |
process-sources
   |
generate-resources
   |
process-resources
   |
compile
   |
process-classes
   |
generate-test-sources
   |
process-test-sources
   |
generate-test-resources
   |
process-test-resources
   |
test-compile
   |
process-test-classes
   |
test
   |
package
   |
verify
   |
install
   |
deploy
~~~

Sơ đồ đã lược bỏ một số phase khác như `prepare-package` và các phase dành cho integration test. Điều quan trọng là thứ tự: **tạo mã → xử lý mã → xử lý resource → biên dịch → xử lý class đã biên dịch**. Những phase chuẩn bị test xuất hiện sau quá trình biên dịch mã chính.

| Phase | Trách nhiệm điển hình | Tạo ra / thay đổi gì? |
| --- | --- | --- |
| `generate-sources` | Chạy generator để tạo source Java/Kotlin hoặc mã khác từ input | File dưới `target/generated-sources/...`, tùy generator |
| `process-sources` | Kiểm tra, biến đổi hoặc đăng ký source directory trước compile | Source được chuẩn bị, thêm compile source root |
| `generate-resources` | Tạo resource dựa trên template/schema/cấu hình | Resource chưa qua bước copy chính |
| `process-resources` | Copy/filter resource của ứng dụng | `target/classes` nhận file cấu hình, dữ liệu, assets |
| `compile` | Biên dịch source đã đăng ký thành bytecode | `target/classes/**/*.class` |
| `process-classes` | Xử lý bytecode **sau** compile, chẳng hạn enhancement | Các file `.class` có thể được xử lý thêm |
| `generate-test-sources` / `process-test-sources` | Tạo và chuẩn bị mã test | Source được dùng ở `test-compile` |

**Gọi `mvn generate-sources` chỉ chạy đến phase tạo mã**, chưa tự động chạy `process-sources` hay `compile`. Gọi `mvn process-sources` chạy qua `generate-sources` rồi đến `process-sources`, **vẫn chưa biên dịch class**. Gọi `mvn compile` sẽ thực hiện cả hai phase trước khi Maven chạy goal compiler.

`mvn clean compile` gồm một phase của **clean lifecycle** và một phase của **default lifecycle**; `clean` thường xóa `target` cũ trước khi thực hiện lại các bước nguồn. Lệnh `mvn compile` một mình không tự dọn output cũ.

## 3. Phase không tự sinh mã: cần plugin goal

Có ba cấp độ phải phân biệt:

- **Lifecycle:** chuỗi phase có thứ tự, ví dụ default lifecycle.
- **Phase:** mốc `generate-sources` hoặc `process-sources`, bản thân không có logic “sinh Java” mặc định.
- **Plugin goal:** việc cụ thể, chẳng hạn `antrun:run`, `build-helper:add-source`, `compiler:compile` hoặc goal của plugin sinh OpenAPI client.

Với **`packaging=jar`**, Maven bind mặc định `resources:resources` ở `process-resources` và `compiler:compile` ở `compile`. Nó **không bind goal tạo/chỉnh sửa Java mặc định** ở `generate-sources` hay `process-sources`. Do đó, khi chưa khai báo execution cho hai phase này, Maven có thể đi qua chúng mà không tạo file nào. <em>Đây là hành vi bình thường.</em>

Để dùng hai phase, cấu hình plugin trong `<build><plugins>` với `<executions>`, `<phase>` và `<goals>`. Một số goal có default phase riêng nếu khai báo execution mà bỏ `<phase>`; để bài học rõ ràng và tránh phụ thuộc mặc định của từng plugin, ví dụ bên dưới **ghi tường minh phase**.

Ví dụ một execution (chỉ là fragment bên trong plugin, không phải một POM độc lập):

~~~xml
<execution>
    <id>create-sources</id>
    <phase>generate-sources</phase>
    <goals>
        <goal>run</goal>
    </goals>
</execution>
~~~

`<id>` giúp phân biệt execution, `<phase>` xác định thời điểm, `<goal>run</goal>` gọi goal `run` của plugin chứa đoạn cấu hình. Phải đọc cả `artifactId` plugin mới biết goal đó làm gì; chỉ nhìn `run` không đủ.

**Chú ý thứ tự:** phase trước luôn chạy trước phase sau; khi có nhiều goal cùng một phase, các goal từ lifecycle bindings được gọi trước goal khai báo trong POM, và các execution khai báo trong POM được tổ chức theo thứ tự cấu hình. Nếu generator và bước sử dụng output phụ thuộc lẫn nhau, thiết kế để generator chạy **trước** bước đăng ký/kiểm tra source; cách dễ đọc nhất là dùng hai phase kế tiếp như ví dụ.

## 4. Phân biệt source directory và resource directory

Một project Java thông thường có cấu trúc:

~~~text
src/
└── main/
    ├── java/                 # source Java do lập trình viên viết
    └── resources/            # .properties, .json, file văn bản, v.v.
target/
├── generated-sources/        # mã được sinh từ generator/plugin
└── classes/                  # .class và resource sau compile/copy
~~~

Theo cấu hình mặc định của Maven:

- `src/main/java` là **compile source root** chứa các file `.java`.
- `src/main/resources` chứa **resource** mà Maven Resources Plugin sao chép vào `target/classes`. File resource không tự biến thành class Java.
- `target/generated-sources/<generator>` là vị trí thường dùng để chứa file `.java` do plugin tạo. **Chỉ vì file tồn tại ở đây chưa đủ để đảm bảo compiler sẽ biên dịch nó.** Generator phải thêm source root vào MavenProject hoặc một plugin khác phải đăng ký thư mục đó.
- `target/classes` là nơi Maven Compiler Plugin ghi bytecode. Khi compile thành công, file `.java` trong generated source root thường tạo ra `.class` có đường dẫn package tương ứng ở đây.

Không nên dùng `maven-resources-plugin` thay cho bước generate code nếu đầu ra là source Java cần biên dịch, trừ khi bạn hiểu rõ plugin đó chỉ đang **copy template hợp lệ** và đã đăng ký source root đúng cách. Tương tự, **`process-sources` khác `process-resources`**: phase thứ hai thường làm công việc copy/filter resources thông qua goal mặc định; phase thứ nhất cần goal của riêng dự án.

Cũng không nên sửa trực tiếp các file nguồn gốc dưới `src/main/java` bằng generator khi có thể viết output vào `target/generated-sources`. Tách generated code giúp build tái lập, tránh commit file sinh tự động và tránh công cụ ghi đè code do lập trình viên sửa.

## 5. Ví dụ Java 17 chạy được: generate → process → compile

Ví dụ này dùng Maven AntRun Plugin để **tạo thực sự** một file Java ở `generate-sources`, kiểm tra file ở `process-sources`, rồi dùng Build Helper Maven Plugin để thêm thư mục generated code vào danh sách Java source root trước khi compiler chạy.

Trong dự án thật, AntRun có thể được thay bằng plugin generator chuyên dụng (OpenAPI Generator, JAXB, ANTLR, v.v.); cấu trúc phase và source root vẫn tương tự.

### 5.1. Cấu trúc ban đầu

~~~text
source-phases-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── org/
                └── example/
                    └── App.java
~~~

**Không tạo thủ công** thư mục `target/generated-sources`. Maven sẽ tạo trong lúc build.

### 5.2. File `pom.xml` đầy đủ

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>org.example</groupId>
    <artifactId>source-phases-demo</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-antrun-plugin</artifactId>
                <version>3.1.0</version>
                <executions>
                    <execution>
                        <id>generate-message-java</id>
                        <phase>generate-sources</phase>
                        <goals>
                            <goal>run</goal>
                        </goals>
                        <configuration>
                            <target>
                                <mkdir dir="${project.build.directory}/generated-sources/demo/org/example/generated"/>
                                <echo file="${project.build.directory}/generated-sources/demo/org/example/generated/GeneratedMessage.java"
                                      encoding="UTF-8"><![CDATA[
package org.example.generated;

public final class GeneratedMessage {
    private GeneratedMessage() {
    }

    public static String text() {
        return "Hello from generated sources";
    }
}
]]></echo>
                            </target>
                        </configuration>
                    </execution>

                    <execution>
                        <id>check-generated-java</id>
                        <phase>process-sources</phase>
                        <goals>
                            <goal>run</goal>
                        </goals>
                        <configuration>
                            <target>
                                <available file="${project.build.directory}/generated-sources/demo/org/example/generated/GeneratedMessage.java"
                                           property="generated.java.exists"/>
                                <fail unless="generated.java.exists"
                                      message="GeneratedMessage.java was not generated"/>
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
                        <id>register-generated-sources</id>
                        <phase>process-sources</phase>
                        <goals>
                            <goal>add-source</goal>
                        </goals>
                        <configuration>
                            <sources>
                                <source>${project.build.directory}/generated-sources/demo</source>
                            </sources>
                        </configuration>
                    </execution>
                </executions>
            </plugin>

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.1</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Phân tích ba plugin:

1. **Maven AntRun Plugin**, execution `generate-message-java` ở `generate-sources`: dùng Ant `mkdir` và `echo` để sinh file `target/generated-sources/demo/org/example/generated/GeneratedMessage.java`. Khối `CDATA` chứa Java nguồn; Ant tạo file trong thư mục build, không chép vào `src/main/java`. Trong POM, Maven nội suy thuộc tính `${project.build.directory}` thành đường dẫn build thực tế (mặc định `target`).
2. **Maven AntRun Plugin**, execution `check-generated-java` ở `process-sources`: dùng Ant `available` để kiểm tra file đã được tạo; nếu thiếu, `fail` dừng build trước khi compiler chạy. Đây là một ví dụ rõ ràng về *xử lý/kiểm tra source* tại phase `process-sources`. Bạn có thể thay bằng goal kiểm tra/biến đổi source phù hợp với quy trình thật.
3. **Build Helper Maven Plugin**, goal `add-source` ở `process-sources`: thêm thư mục `target/generated-sources/demo` vào compile source roots. **Không thêm chính thư mục cuối `org/example/generated`** vì source root phải là thư mục **phía trên đường dẫn package**. AntRun được khai báo trước Build Helper, nên bước kiểm tra hoàn tất trước bước thêm source root trong phase này. Việc chạy qua `process-sources` đảm bảo compile nhận được source mới.

Maven Compiler Plugin đã có goal `compiler:compile` bind mặc định với phase `compile` do `packaging=jar`. Ta chỉ ghim version và cấu hình `release=17`; không cần tạo execution compiler thủ công. File Java được tạo là mã nguồn hợp lệ nhưng **không chạy riêng**: chương trình entry point ở file `App.java` kế tiếp.

**Lưu ý về phiên bản AntRun 3.x:** Các tùy chọn `sourceRoot` cũ của AntRun đã bị loại bỏ; vì thế ví dụ sử dụng Build Helper để đăng ký source root tường minh. Nếu generator thực tế đã tự thêm compile source root, không thêm trùng bằng Build Helper.

### 5.3. File `src/main/java/org/example/App.java`

~~~java
package org.example;

import org.example.generated.GeneratedMessage;

public final class App {
    public static void main(String[] args) {
        System.out.println(GeneratedMessage.text());
    }
}
~~~

`App.java` tham chiếu class chưa tồn tại trước build. Sau khi `generate-sources` tạo `GeneratedMessage.java` và `process-sources` đăng ký thư mục chứa nó, compiler mới có đủ source để giải quyết lệnh `import org.example.generated.GeneratedMessage;`.

### 5.4. Chạy từng phase và quan sát

Mở terminal ở thư mục chứa `pom.xml`:

~~~bash
java -version
javac -version
mvn -version
~~~

Chỉ dùng **JDK 17+** cho ví dụ này. Lệnh `javac -version` giúp phân biệt JDK đầy đủ với Java runtime thiếu compiler.

**Lần A — dừng tại generate-sources:**

~~~bash
mvn clean generate-sources
~~~

Kết quả cần có file nguồn:

~~~text
target/generated-sources/demo/org/example/generated/GeneratedMessage.java
~~~

Trong lần A, Maven chưa chạy `process-sources` hay `compile`, nên **chưa kỳ vọng** có `target/classes/org/example/generated/GeneratedMessage.class`. Thư mục nguồn được tạo thực tế; việc đăng ký source root trong ví dụ được thực hiện ở phase kế tiếp.

**Lần B — dừng tại process-sources:**

~~~bash
mvn clean process-sources
~~~

Lệnh thực hiện lại `generate-sources`, rồi chạy execution kiểm tra file và `build-helper:add-source`. Sau lần B vẫn chưa chạy compiler; vì vậy file `.class` chưa phải output bắt buộc. Điều này giúp thấy **process-sources chỉ chuẩn bị source**, không mặc định biên dịch.

**Lần C — thực hiện compile và chạy class:**

~~~bash
mvn clean compile
java -cp target/classes org.example.App
~~~

Đây là **stdout chính xác của ứng dụng**:

~~~text
Hello from generated sources
~~~

Trong lần C, Maven thực hiện cả chuỗi `generate-sources` → `process-sources` → `process-resources` → `compile` (cùng các phase trung gian). Java Compiler biên dịch **cả source trong `src/main/java` lẫn source root được Build Helper thêm vào**.

Bạn sẽ thấy các file quan trọng:

~~~text
target/
├── generated-sources/
│   └── demo/
│       └── org/
│           └── example/
│               └── generated/
│                   └── GeneratedMessage.java
└── classes/
    └── org/
        └── example/
            ├── App.class
            └── generated/
                └── GeneratedMessage.class
~~~

Maven/Compiler Plugin còn có thể tạo `maven-status/` và các metadata khác; sơ đồ chỉ tập trung vào đường đi của source được sinh. Kết quả `mvn clean compile` thành công có thể chứa nhiều log Maven, nhưng **stdout của `java -cp ...`** chỉ in dòng thông báo ở trên.

**Lần D — đóng gói:**

~~~bash
mvn clean package
jar tf target/source-phases-demo-1.0.0.jar
java -cp target/source-phases-demo-1.0.0.jar org.example.App
~~~

JAR sẽ chứa class đã biên dịch, gồm `org/example/App.class` và `org/example/generated/GeneratedMessage.class`; stdout ứng dụng vẫn là `Hello from generated sources`. Ví dụ không cấu hình `Main-Class`, nên dùng `java -cp <jar> org.example.App`. Không mặc định dùng `java -jar` với JAR không có entry point manifest.

**Không ghép các lần A/B/C thành một lệnh kiểm thử duy nhất có nhiều `clean` không cần thiết** khi đang quan sát hiệu năng: các lệnh trên được minh họa độc lập để nhìn rõ từng phase. Trong build thông thường, `mvn clean package` hoặc `mvn clean verify` đủ chạy trọn chuỗi.

### 5.5. Xem file trên Windows, Linux và macOS

**PowerShell Windows:**

~~~powershell
Get-ChildItem .\target\generated-sources -Recurse
Get-Content .\target\generated-sources\demo\org\example\generated\GeneratedMessage.java
Get-ChildItem .\target\classes -Recurse
~~~

**Bash/Zsh trên Linux/macOS:**

~~~bash
find target/generated-sources -type f
cat target/generated-sources/demo/org/example/generated/GeneratedMessage.java
find target/classes -type f
~~~

Các lệnh `mvn` và `java -cp` trong ví dụ tương tự trên cả ba hệ điều hành. Chú ý đổi dấu đường dẫn tương ứng khi dùng `Get-Content` trên Windows.

## 6. Nếu không đăng ký generated source root thì sao?

Giả sử AntRun đã sinh ra `GeneratedMessage.java` nhưng **bạn xóa execution `build-helper:add-source`** trong POM. Maven Compiler Plugin mặc định biết đến `src/main/java`, nhưng **không nhất thiết tự dò mọi thư mục** bên trong `target/generated-sources`. Khi đó compile có thể dừng với lỗi tương đương:

~~~text
package org.example.generated does not exist
cannot find symbol: class GeneratedMessage
~~~

Đây là **dạng thông báo minh họa**; dòng lỗi và tiền tố log phụ thuộc JDK/Compiler Plugin. Nguyên nhân gốc là Java đã được sinh nhưng source root chưa được đưa vào danh sách compiler.

Cách xử lý:

- Kiểm tra file `GeneratedMessage.java` có thật ở đường dẫn dự kiến hay không.
- Kiểm tra goal `build-helper:add-source` được bound vào phase không muộn hơn `compile` (ở ví dụ là `process-sources`).
- Kiểm tra `<source>.../generated-sources/demo</source>` là **gốc package**, không phải path trỏ thẳng tới file `.java`.
- Kiểm tra tên `package org.example.generated;` và đường dẫn `org/example/generated/GeneratedMessage.java` khớp nhau.
- Nếu generator tự thêm source root vào MavenProject, không cấu hình Build Helper trùng lặp.

Một số plugin sinh code (OpenAPI, JAXB, protobuf, v.v.) có chức năng tự thêm source root; hãy đọc tài liệu của plugin đó trước khi bổ sung Build Helper. **Không nên ép Maven Compiler Plugin biên dịch tất cả thư mục bất kỳ**: chỉ đăng ký đúng output source cần tham gia build.

## 7. Process-sources có phải luôn chỉnh sửa file `.java`?

**Không.** Phase `process-sources` là điểm mở rộng giữa tạo source và xử lý resource/compile. Maven không tự làm sạch, format, rewrite hay filter mọi file `.java` tại phase này. Những công việc có thể bind theo nhu cầu dự án:

- Kiểm tra file generator bắt buộc đã xuất hiện, validate header hoặc quy ước đặt tên.
- Chạy bước preprocess template thành mã Java ở **output directory** khác.
- Đăng ký generated source directories vào compile source roots.
- Thực thi các goal phân tích hoặc chuẩn hóa source mà plugin hỗ trợ trước khi compiler chạy.

Ví dụ thực hành sử dụng `<available>` + `<fail>` để **validate generated file**, rồi `build-helper:add-source` để đăng ký source root. Đó là hai công việc có ý nghĩa tại `process-sources` dù chúng không sửa nội dung Java đã được tạo.

Nếu cần *thực sự* biến đổi Java source, phải chọn plugin hỗ trợ thao tác cụ thể, xác định rõ **input và output** và vị trí bind. Khuyến nghị tạo bản đã biến đổi dưới `target/generated-sources` để không ghi đè mã nguồn gốc hoặc phá hỏng những thay đổi đang được quản lý Git.

Khi plugin buộc phải thay đổi file dưới `src/main/java`, cần đánh giá tác động: `mvn clean` thường chỉ xóa `target`, **không phục hồi source** bị sửa trong `src`. Pipeline như thế có thể gây build không tái lập và khó kiểm soát diff.

## 8. Phân biệt với annotation processing và generated test sources

### 8.1. Annotation processing khi compile

Java annotation processors (ví dụ processor sinh implementation hoặc metadata) thường được Java Compiler chạy **trong phase `compile`** theo cấu hình Maven Compiler Plugin và phiên bản JDK/plugin. Processor có thể tạo Java source dưới thư mục như `target/generated-sources/annotations`.

Điều này **không có nghĩa annotation processor mặc định chạy tại `generate-sources`**. Thời điểm sinh mã thuộc về plugin/goal được bind và cấu hình compiler. Trên các phiên bản JDK mới, việc khám phá và kích hoạt annotation processor có thể khác Java 17; hãy cấu hình processor rõ ràng theo hướng dẫn của Compiler Plugin thay vì dựa vào phát hiện tự động.

Các file sinh bởi annotation processor có thể được compiler quản lý trực tiếp, nên không mặc định thêm thư mục `target/generated-sources/annotations` vào Build Helper một lần nữa. Hãy kiểm tra hành vi plugin đang dùng.

### 8.2. Generate test sources

Maven có các phase riêng cho test:

~~~text
generate-test-sources
    |
process-test-sources
    |
generate-test-resources
    |
process-test-resources
    |
test-compile
    |
test
~~~

Nếu generator sinh **mã test**, thường đặt vào `target/generated-test-sources/<generator>` và đăng ký làm **test source root**, chẳng hạn qua `build-helper:add-test-source`. Không dùng `add-source` cho test một cách tùy tiện vì nó có thể khiến mã test bị compile như mã sản phẩm, kéo dependency test vào classpath không mong muốn.

Tương tự, `process-test-sources` xử lý/đăng ký source test trước `test-compile`, chứ không tự chạy unit tests. Goal `surefire:test` thường được bind tại phase `test` cho `packaging=jar`; không nên nhầm phase sinh mã test với phase chạy test.

## 9. Cách xác minh Maven đã chạy những goal nào

Chạy trong project có POM:

~~~bash
mvn -version
mvn clean compile
~~~

Log Maven sẽ có các dòng nhận diện goal, chẳng hạn `maven-antrun-plugin:3.1.0:run`, `build-helper-maven-plugin:3.6.0:add-source`, `maven-resources-plugin:...:resources` và `maven-compiler-plugin:3.14.1:compile`. Số phiên bản plugin tài nguyên có thể khác, nên không lấy một log từ máy khác làm tiêu chuẩn duy nhất.

Trong ví dụ, thứ tự quan trọng có thể đọc như sau:

~~~text
generate-sources: antrun:run              -> viết GeneratedMessage.java
process-sources:  antrun:run              -> kiểm tra file tồn tại
process-sources:  build-helper:add-source -> đăng ký source root
process-resources: resources:resources   -> chuẩn bị resources
compile:           compiler:compile      -> tạo các file .class
~~~

Các chú thích `generate-sources:` trên chỉ là **sơ đồ giải thích**, không phải bản sao chính xác output log Maven (log thực tế khác theo phiên bản).

Các lệnh hữu ích khi cần kiểm tra cấu hình:

~~~bash
mvn help:effective-pom -Doutput=effective-pom.xml
mvn -X compile
~~~

`help:effective-pom` cho thấy plugin và execution sau kế thừa, profile và cấu hình. `-X` cho log debug, thường dùng khi cần tìm đường dẫn source hoặc thứ tự goal; không cần chạy mọi lần vì log dài. Một số goal thêm source root **khi chạy**, nên chỉ đọc effective POM chưa chứng minh source root đã được đăng ký động: cần xem log và file `target/classes` thật.

## 10. Tình huống lỗi thường gặp

| Biểu hiện | Nguyên nhân có thể | Cách khắc phục |
| --- | --- | --- |
| `mvn generate-sources` không tạo file | Chưa bind goal generator vào phase, cấu hình sai hoặc generator không có input | Xem `build/plugins/executions`, log và đường dẫn input/output |
| Có file Java trong `target/generated-sources` nhưng compile báo không tìm thấy class | Chưa đăng ký source root hoặc đăng ký sai cấp thư mục | Kiểm tra Build Helper `add-source`/generator tự đăng ký và tên package |
| `mvn process-sources` không có `.class` | Chưa chạy đến phase `compile` | Chạy `mvn compile` hoặc `mvn package` |
| `GeneratedMessage.java was not generated` | Execution kiểm tra chạy nhưng file nguồn không có | Kiểm tra AntRun ở `generate-sources`, đường dẫn output, lỗi ở log trước đó |
| `java -cp target/classes ...` báo class không tồn tại | Compile chưa thành công hoặc tên package/class sai | Kiểm tra `target/classes`, compile log và tên đầy đủ main class |
| `mvn package` chạy được còn IDE báo unresolved import | IDE chưa đánh dấu generated source root hoặc chưa đồng bộ cấu hình Maven | Reload/Reimport Maven project và kiểm tra cấu hình generated sources của IDE |
| IDE chạy được nhưng `mvn clean compile` thất bại | IDE tự thêm source root, file sinh cũ còn trong workspace, hoặc POM thiếu execution | Coi build sạch từ terminal/CI là nguồn kiểm chứng; khai báo đầy đủ plugin trong POM |
| Build sạch xóa mất mã đã tạo | Mã sinh nằm dưới `target` và chưa được tạo lại | Đảm bảo generator được bind vào lifecycle, có input nguồn được quản lý |
| Có nhiều lần sinh cùng một class và bị `duplicate class` | Hai generator ghi trùng package/class, hoặc thêm trùng source root | Tách output generator, tránh biên dịch cùng class từ nhiều đường dẫn |
| Cấu hình plugin trong `pluginManagement` nhưng không chạy | `pluginManagement` quản lý cấu hình, không tự kích hoạt execution | Khai báo plugin thực thi đúng trong `build/plugins` |
| Chạy `mvn antrun:run` trực tiếp nhưng không giống build toàn lifecycle | Gọi goal trực tiếp khác với chạy phase và execution cụ thể | Dùng `mvn generate-sources`/`process-sources`/`compile` để chạy đúng chuỗi |
| `mvn clean compile` gọi generator nhiều lần ngoài mong đợi | Execution bind trùng phase, chạy nhiều build liên tiếp hoặc profile bổ sung | Xem effective POM và log của từng execution; bảo đảm generator idempotent |
| Build lỗi khi dùng JDK khác Java 17 | Maven/Compiler Plugin hoặc source release không tương thích | Xem `mvn -version`, `java -version` và `maven.compiler.release` |

**Khác biệt giữa `pluginManagement` và `plugins`:** một plugin chỉ xuất hiện trong `pluginManagement` thường định nghĩa version/cấu hình dùng chung; nó không tự chạy goal của riêng project. Muốn tạo mã tại phase cụ thể, phải có plugin/execution được kích hoạt thực tế, qua `build/plugins` hoặc cơ chế kế thừa/lifecycle tương ứng.

Đối với generator có output thay đổi theo input, chú ý việc **build incremental**: file sinh cũ có thể không được xóa khi schema đổi tên class. `mvn clean compile` là bước chẩn đoán tốt để loại bỏ output cũ; trong CI nên kiểm chứng build sạch có thể tạo lại tất cả source cần thiết.

## 11. Cách tổ chức pipeline đáng tin cậy

Để generated code có thể được build ổn định trên máy đồng đội và CI:

1. **Lưu input và cấu hình generator trong Git:** schema, API spec, template, plugin version và các tham số tạo mã. Generated output dưới `target` thường nằm trong `.gitignore`.
2. **Định nghĩa đường dẫn output duy nhất:** ví dụ `target/generated-sources/openapi` hoặc `target/generated-sources/demo`; tránh ghi đè `src/main/java`.
3. **Bind generator đủ sớm:** thường ở `generate-sources`; bước xử lý/đăng ký source ở `process-sources` hoặc tại phase phù hợp trước `compile`.
4. **Đăng ký đúng compile source root:** nếu generator đã làm việc này, không thêm trùng; nếu chưa, dùng `build-helper:add-source` hoặc cơ chế mà plugin hỗ trợ.
5. **Kiểm tra đầu ra và lỗi sớm:** nếu schema/input bắt buộc bị thiếu hoặc generator tạo file không hợp lệ, thất bại ngay trước `compile` cho thông báo dễ hiểu.
6. **Ghim phiên bản plugin:** build trên máy mới không nên vô tình thay đổi generator theo phiên bản mới nhất.
7. **Thử build sạch:** chạy `mvn clean verify` hoặc pipeline CI phù hợp, rồi đối chiếu class, test và artifact. Build trong IDE một lần không thay cho kiểm tra Maven từ trạng thái sạch.

Một số công cụ dùng `generate-sources` để sinh model từ OpenAPI, JAXB schema, gRPC/protobuf hoặc ANTLR grammar; số lượng, vị trí file và cách đăng ký source root là **tùy theo plugin**. Không suy đoán rằng mọi generator đều tạo cùng cấu trúc hay tự đăng ký source root giống nhau.

## 12. Tự kiểm tra

**Câu 1:** Gọi `mvn generate-sources` đã có thể chạy `App.class` chưa?  
**Đáp án:** Chưa, vì phase `compile` chưa chạy. Trong ví dụ, mới có `GeneratedMessage.java` ở `target/generated-sources`.

**Câu 2:** `mvn process-sources` có tự format/filter source Java trong một dự án `jar` chưa cấu hình plugin không?  
**Đáp án:** Không. Phase tồn tại trong lifecycle nhưng không tự có goal xử lý source mặc định.

**Câu 3:** Có file `GeneratedMessage.java` dưới `target/generated-sources/demo/org/example/generated` nhưng `App.java` import không được. Cần kiểm tra gì đầu tiên?  
**Đáp án:** File có thật không, package có khớp đường dẫn không, và **`target/generated-sources/demo` đã được đăng ký làm compile source root** trước phase `compile` chưa.

**Câu 4:** `process-resources` và `process-sources` có cùng chức năng không?  
**Đáp án:** Không. `process-resources` của JAR thường bind `resources:resources` để copy/filter resource vào `target/classes`; `process-sources` dành cho các goal xử lý source do project cấu hình.

**Câu 5:** Annotation processor tạo Java khi compiler chạy có bắt buộc phải bind ở `generate-sources` không?  
**Đáp án:** Không. Annotation processing thường diễn ra trong quá trình `compile`; hành vi phụ thuộc compiler plugin/JDK, và output/source root thường được compiler quản lý.

**Câu 6:** Nếu đổi tên generated class nhưng `mvn compile` vẫn báo class cũ tồn tại thì làm gì?  
**Đáp án:** Kiểm tra generated output còn sót từ build trước, chạy `mvn clean compile` để kiểm tra khả năng tái lập, rồi sửa generator và cấu hình source root nếu vẫn sai.

## 13. Checklist hoàn thành bài thực hành

- Maven và JDK 17+ hoạt động (`mvn -version`, `javac -version`).
- `pom.xml` cấu hình AntRun generate source tại `generate-sources`, xác minh file và Build Helper `add-source` tại `process-sources`.
- `mvn clean generate-sources` tạo `target/generated-sources/demo/org/example/generated/GeneratedMessage.java`.
- `mvn clean process-sources` đi qua hai bước chuẩn bị mà chưa kỳ vọng có bytecode.
- `mvn clean compile` tạo `App.class` và `GeneratedMessage.class` dưới `target/classes`.
- `java -cp target/classes org.example.App` in **`Hello from generated sources`**.
- `mvn clean package` tạo `target/source-phases-demo-1.0.0.jar` chứa cả hai class; `java -cp target/source-phases-demo-1.0.0.jar org.example.App` chạy được.
- Có thể xóa `target` rồi chạy build lại để tạo tất cả source từ input/config đã được quản lý, không cần chép file `.java` sinh thủ công.

**Tài liệu tham khảo chính thức:**

- [Apache Maven — Introduction to the Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html)
- [Apache Maven — Configuring Plugins](https://maven.apache.org/guides/mini/guide-configuring-plugins.html)
- [Maven AntRun Plugin 3.1.0 — Usage](https://maven.apache.org/plugins-archives/maven-antrun-plugin-3.1.0/usage.html)
- [Build Helper Maven Plugin — add-source](https://www.mojohaus.org/build-helper-maven-plugin/add-source-mojo.html)
- [Maven Compiler Plugin — Compile](https://maven.apache.org/plugins/maven-compiler-plugin/compile-mojo.html)
