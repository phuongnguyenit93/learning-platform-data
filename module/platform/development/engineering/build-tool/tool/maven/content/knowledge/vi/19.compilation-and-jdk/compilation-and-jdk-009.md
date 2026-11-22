# Mã sinh tự động, thứ tự biên dịch và thư mục nguồn bổ sung trong Maven

## 1. Bài toán: mã Java chưa có khi bắt đầu build

Một dự án Java có thể cần các lớp **không được lập trình viên viết sẵn** trong `src/main/java`. Thay vào đó, công cụ sinh mã (code generator) tạo file `.java` từ một đầu vào khác hoặc từ annotation trong source. Các tình huống thường gặp:

- Công cụ Protobuf sinh Java từ tệp `.proto`.
- OpenAPI Generator sinh API client/server stub từ một đặc tả OpenAPI.
- JAXB hoặc công cụ schema sinh Java từ XSD/WSDL.
- MapStruct, Dagger, Lombok, Immutables và các annotation processor xử lý annotation trong quá trình biên dịch, với cơ chế và đầu ra khác nhau tùy công cụ.
- Một plugin nội bộ tạo DTO, protocol class, source chứa metadata hoặc adapter từ tệp cấu hình được quản lý.
- Một repository cũ có Java source ở `src/generated/java` hoặc một đường dẫn ngoài cấu trúc Maven chuẩn.

Điểm khó không phải chỉ là **tạo ra file Java**. Maven phải thực hiện đủ ba việc, theo đúng trình tự:

1. **Tạo mã** tại bước phù hợp, trước khi các lớp cần nó được biên dịch (trừ trường hợp annotation processing chạy ngay trong compiler).
2. **Đưa thư mục chứa mã đã tạo vào danh sách source roots** mà Maven Compiler Plugin sử dụng.
3. **Biên dịch và kiểm thử trong cùng một build có thể tái lập**, bảo đảm CI sạch cũng tạo được source, không phụ thuộc file tình cờ còn trên laptop.

Ví dụ, `src/main/java/demo/app/Application.java` có:

```java
import demo.generated.BuildInfo;
```

Nếu `BuildInfo.java` chưa được tạo hoặc thư mục chứa nó chưa được khai báo là source root, Maven Compiler Plugin có thể báo `package demo.generated does not exist` hoặc `cannot find symbol`.

**Mục tiêu bài học:** hiểu các phase Maven, cách generator đăng ký nguồn, phân biệt source Java với class output, phối hợp generated sources và annotation processors, tránh lỗi thứ tự và thực hành một dự án Java 17 có thể build/test/chạy từ trạng thái sạch.

## 2. Quy ước thư mục source và output

Một Maven project Java phổ biến có các vị trí sau:

| Vai trò | Đường dẫn thường gặp | Có nên commit? |
| --- | --- | --- |
| Java source chính, viết tay | `src/main/java` | Có |
| Java source test, viết tay | `src/test/java` | Có |
| Resources sản phẩm | `src/main/resources` | Có |
| Resources test | `src/test/resources` | Có |
| Java source tự sinh trước compile | `target/generated-sources/<ten-generator>` | Thường không |
| Java source do annotation processor sinh | `target/generated-sources/annotations` | Thường không |
| Java test source tự sinh | `target/generated-test-sources/<ten-generator>` | Thường không |
| Class sản phẩm đã biên dịch | `target/classes` | Không |
| Class test đã biên dịch | `target/test-classes` | Không |
| Artifact JAR và báo cáo test | `target/*.jar`, `target/surefire-reports` | Thường không |

Các thư mục dưới `target` là **output của build**, có thể bị xóa bởi `mvn clean`. Không được bắt build trên CI phải dựa vào việc ai đó đã commit/chép sẵn các file đó vào workspace.

### 2.1. Source root không phải output directory

- **Source root** là thư mục mà Maven/Compiler Plugin xem như điểm bắt đầu quét source Java, ví dụ `src/main/java` hoặc `target/generated-sources/demo`.
- **Output directory** của các class được biên dịch là `target/classes`, theo cấu hình Maven tiêu chuẩn.
- Source `target/generated-sources/demo/demo/generated/BuildInfo.java` thường sinh ra class `target/classes/demo/generated/BuildInfo.class`, không có nghĩa Maven chép chính tệp `.java` vào JAR.
- **Test source root** thường biên dịch vào `target/test-classes`, không vào `target/classes`.

Giá trị `package demo.generated;` trong file Java quyết định tên package của lớp. Đường dẫn tương đối dưới source root nên khớp đường dẫn package, ví dụ `demo/generated/BuildInfo.java`. Nhầm cấp source root với thư mục con `demo/generated` sẽ khiến IDE hoặc công cụ khác tổ chức package sai và rất khó đọc.

### 2.2. Thêm một thư mục vào filesystem chưa đủ

Chỉ tạo:

```text
target/generated-sources/demo/demo/generated/BuildInfo.java
```

không đảm bảo Maven Compiler Plugin quét đường dẫn đó. Compiler Plugin chủ yếu nhận danh sách `project.compileSourceRoots`; nếu generator **không tự đăng ký** thư mục, phải dùng plugin/goal như `build-helper:add-source` để thêm root, hoặc cấu hình theo cách được plugin sinh mã chính thức hỗ trợ.

Ngược lại, một số generator hoặc compiler/annotation processor **đã tự quản lý source root hoặc file sinh ra**. Thêm Build Helper chồng lên một root đã đăng ký có thể tạo tình trạng dư cấu hình, duplicate scanning hoặc rủi ro IDE xử lý khác đi. Trước khi thêm plugin, cần đọc tài liệu của generator cụ thể.

## 3. Các phase liên quan và thứ tự bắt buộc

Maven có **default lifecycle** gồm những phase chạy theo thứ tự cố định. Những phase đáng chú ý:

| Phase | Việc nên diễn ra | Quan hệ với generated Java |
| --- | --- | --- |
| `validate` | Xác nhận cấu hình project | Chưa phải nơi compile mã |
| `initialize` | Chuẩn bị trạng thái chung | Có thể chuẩn bị thông số đầu vào |
| `generate-sources` | Sinh source chính | Thường bind generator ở đây |
| `process-sources` | Xử lý source trước compile | Có thể đăng ký thư mục source generator vừa tạo |
| `generate-resources` | Sinh resource sản phẩm | Phân biệt resource với Java source |
| `process-resources` | Xử lý/copy resource | Resources Plugin thường chạy ở đây |
| `compile` | Biên dịch Java source chính | Compiler phải thấy source đã tạo và root đã đăng ký |
| `process-classes` | Xử lý class sau compile | Không thể sửa thiếu Java source ở phase này rồi kỳ vọng compile trước đã nhận |
| `generate-test-sources` | Sinh source dành cho test | Sinh test classes từ schema/fixture nếu cần |
| `process-test-sources` | Xử lý hoặc đăng ký test source | Có thể chạy `build-helper:add-test-source` |
| `generate-test-resources` | Sinh test resources | Không đồng nghĩa tạo Java test source |
| `process-test-resources` | Copy/xử lý test resources | Test resource đi vào test classpath |
| `test-compile` | Biên dịch test sources | Compiler test phải thấy generated test roots |
| `test` | Chạy unit tests theo plugin cấu hình | Các class đã được compile mới có thể chạy |
| `package` | Tạo artifact, ví dụ JAR | Generated `.class` có thể vào JAR |
| `verify` | Kiểm tra kết quả build theo các goal đã cấu hình | Không tự động chạy mọi loại integration test nếu plugin chưa gắn |

Lệnh:

```bash
mvn -B clean verify
```

gọi clean lifecycle rồi chạy default lifecycle **qua tất cả phase tới `verify`**, vì vậy generator ở `generate-sources`, việc đăng ký root ở `process-sources` và Compiler ở `compile` đều có cơ hội chạy theo thứ tự.

Lệnh:

```bash
mvn -B compile
```

cũng chạy những phase trước `compile` của default lifecycle, gồm `generate-sources` và `process-sources`. Tuy nhiên, gọi trực tiếp **một plugin goal** như `mvn compiler:compile` không tương đương gọi lifecycle phase `compile`; nó không tự thực thi toàn bộ các generator đã bind ở phase trước. Đó là nguyên nhân thường gặp khi lệnh của IDE/script hoạt động khác `mvn compile`.

**Nguyên tắc:** chọn **phase trước khi cần dùng output**, không chọn phase sau chỉ vì tên goal nghe giống công việc mong muốn.

## 4. Một lần Maven session: phân biệt phase và thứ tự execution

Khi nhiều execution ở **các phase khác nhau**, lifecycle tạo một thứ tự rõ ràng:

```text
generate-sources
    └─ generator tạo BuildInfo.java
process-sources
    └─ build-helper:add-source đăng ký target/generated-sources/demo
process-resources
    └─ resources:resources
compile
    └─ compiler:compile thấy cả src/main/java và target/generated-sources/demo
test-compile
    └─ compiler:testCompile
test
    └─ surefire:test
package
    └─ jar:jar
```

Đây là **sơ đồ logic**, không phải toàn bộ log Maven. Trên một project thực, thứ tự còn liên quan các goal do packaging mặc định gắn, plugin executions trong POM, parent/profile và các ràng buộc lifecycle khác.

### 4.1. Nếu generator và đăng ký root nằm cùng phase thì sao?

Maven có quy tắc về thứ tự các plugin execution được gắn vào cùng phase, chịu ảnh hưởng từ lifecycle bindings và thứ tự khai báo trong POM. Nhưng nếu không thật sự cần, **đừng làm build phụ thuộc vào một thứ tự khó thấy**.

Ví dụ bài này cố ý:

- Tạo file ở **`generate-sources`**.
- Đăng ký root ở **`process-sources`**.
- Biên dịch ở **`compile`**.

Như vậy dù người đọc không biết chi tiết sorting goal trong cùng phase, họ vẫn hiểu vì sao generated Java đã tồn tại trước khi Compiler Plugin chạy.

Không phải lúc nào `process-sources` cũng cần đăng ký source root: Build Helper `add-source` theo tài liệu mặc định gắn với `generate-sources`, và plugin generator chuyên dụng có thể vừa sinh mã vừa tự đăng ký root trong một execution. Trong **ví dụ được thiết kế có chủ đích**, ta đặt registration ở phase sau để thứ tự hiển nhiên và dễ học.

### 4.2. Reactor khác lifecycle phase

Trong multi-module project, Maven Reactor sắp xếp **thứ tự xây module** theo dependency graph. Còn lifecycle quyết định **thứ tự goal/phase bên trong mỗi module**.

```text
root
├── schema-model    (định nghĩa API hoặc schema)
├── generated-api   (sinh và biên dịch Java)
└── service         (dùng class từ generated-api)
```

Nếu `service` dùng artifact `generated-api`, `service` phải khai báo dependency vào artifact đó. Root chỉ liệt kê cả hai trong `<modules>` không tự đưa class generated-api vào compile classpath của service.

Khi chạy từ root:

```bash
mvn -B -pl :service -am clean verify
```

`-pl` chọn module service, còn `-am` cho phép Reactor xây thêm các module cần thiết. Mỗi module được chọn vẫn đi qua lifecycle của nó. **Thêm Build Helper vào service không chữa được lỗi thiếu dependency sang module generated-api** nếu mã đang nằm trong artifact riêng.

## 5. Hai nhóm sinh mã khác nhau: generator trước compile và annotation processor trong compile

### 5.1. Plugin chạy trước compile

Nhiều generator đọc DSL/schema và ghi Java source khi Maven đến `generate-sources` hoặc `generate-test-sources`:

```text
src/main/proto/customer.proto
      │
      ▼ generator:generate (generate-sources)
target/generated-sources/protobuf/.../Customer.java
      │
      ▼ source root được đăng ký
compiler:compile (compile)
      │
      ▼
target/classes/.../Customer.class
```

Ví dụ tên plugin/goal thật tùy hệ sinh thái (protobuf, JAXB, OpenAPI, GraphQL...). Đây là pipeline khái niệm: không có một plugin `generator:generate` chung hoạt động cho mọi schema.

Ưu điểm là mã sinh ra **tồn tại trước `compiler:compile`**; có thể xem file `.java` sau `mvn generate-sources`. Rủi ro là generator có thể ghi sai thư mục, không đăng ký source root, hoặc phụ thuộc một file schema chưa sẵn sàng.

### 5.2. Annotation processing chạy ngay trong javac

Annotation processor được Maven Compiler Plugin phối hợp với Java compiler. Trong một lần `compiler:compile`, processor có thể đọc annotation và sinh thêm các file `.java` ở một hoặc nhiều **rounds** xử lý; compiler có thể biên dịch cả mã viết tay và mã được processor sinh ra trong compilation đó.

Maven Compiler Plugin 3.13.0 công bố parameter:

- `annotationProcessorPaths`: nơi khai báo các processor JAR và dependency của chúng trên processor path.
- `annotationProcessors`: chỉ định processor class cụ thể khi cần.
- `generatedSourcesDirectory`: vị trí file source do annotation processing tạo, mặc định `${project.build.directory}/generated-sources/annotations`.
- `proc`: kiểm soát chế độ annotation processing `none`, `only` hoặc `full`, với chi tiết phụ thuộc JDK/compiler.

Ví dụ cấu hình **minh họa**, nếu một dự án đã dùng MapStruct thật sự và có thêm đúng thư viện annotation/API mà source yêu cầu:

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-compiler-plugin</artifactId>
    <version>3.13.0</version>
    <configuration>
        <release>17</release>
        <annotationProcessorPaths>
            <path>
                <groupId>org.mapstruct</groupId>
                <artifactId>mapstruct-processor</artifactId>
                <version>1.5.5.Final</version>
            </path>
        </annotationProcessorPaths>
    </configuration>
</plugin>
```

Đây là **đoạn plugin configuration**, không phải POM hoàn chỉnh và **không thuộc ví dụ runnable ở phần 8**. Nó chưa tạo mã nếu dự án không có `@Mapper`/API/dependencies phù hợp. Với một project thực, cần kiểm tra yêu cầu JDK, MapStruct và processor versions đồng bộ.

**Điểm khác:** khi generated Java do **annotation processor của javac** tạo ngay trong compile, không mặc nhiên cần bind thêm `build-helper:add-source` như generator chạy trước compile. Compiler Plugin và javac đã quản lý output processing theo cơ chế đó.

### 5.3. JDK mới có thể thay đổi cách phát hiện processor

Không nên dựa vào việc `javac` luôn tự phát hiện mọi processor tình cờ nằm trên compile classpath. Hành vi mặc định và yêu cầu khai báo rõ annotation processing đã thay đổi giữa các đời JDK, trong đó các JDK mới chú trọng giảm việc tự thực thi processor không được chỉ định.

Với build nghiêm túc, **pin Compiler Plugin, processor version và cấu hình processor path/processor names rõ ràng**, rồi kiểm tra trên JDK thật của CI. Không gắn processor JAR không tin cậy vào build: annotation processor **thực thi code ngay trong quá trình biên dịch**, có thể truy cập tài nguyên mà tiến trình build được cấp quyền.

Ở Maven Compiler Plugin 3.x, `<annotationProcessorPaths>` hữu ích để tách processor path khỏi classpath code ứng dụng; ở các plugin/Maven thế hệ khác, tham số và khuyến nghị có thể khác. Luôn tra tài liệu **đúng phiên bản plugin đang dùng** trước khi nâng cấp.

## 6. Thêm source root bằng Build Helper Maven Plugin

Khi một generator viết file Java nhưng không tự khai báo thư mục nguồn, goal `build-helper:add-source` thêm đường dẫn vào `project.compileSourceRoots` để Compiler Plugin thấy source.

Ví dụ một module có root source bổ sung:

```xml
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
```

Đây là **mảnh plugin** để đặt trong `<build><plugins>` của project. Thư mục `target/generated-sources/demo` là **source root**, bên dưới nó mới chứa thư mục package `demo/generated/...`.

**Lưu ý:** goal `add-source` có default phase `generate-sources` theo tài liệu Build Helper, nhưng việc chỉ rõ `process-sources` trong XML ở trên là có chủ đích: generator của ví dụ chạy ở `generate-sources` trước nó. Một dự án khác có thể dùng default phase hoặc cho generator đăng ký root tự động nếu thứ tự rõ ràng.

Để thêm **source viết tay** ngoài layout chuẩn, cũng có thể dùng `add-source`:

```xml
<configuration>
    <sources>
        <source>${project.basedir}/src/legacy/java</source>
    </sources>
</configuration>
```

Nhưng chỉ thêm một đường dẫn khi nó thật sự chứa Java source phù hợp. Tránh quét cả project root hoặc `target` như một source root, vì dễ biên dịch lại output, kéo file không liên quan hoặc tạo duplicate classes.

### 6.1. Tại sao không cứ sửa sourceDirectory?

Trong POM, phần `<build><sourceDirectory>...` thường được xem như **một nguồn chính**. Thay nó bằng thư mục generated có thể vô tình bỏ đường dẫn mặc định `src/main/java` khỏi cấu hình mong muốn.

Khi cần **nhiều** Java source roots, Build Helper hoặc chính plugin generator là lựa chọn minh bạch hơn so với thay một đường dẫn duy nhất. Kiểm tra Compiler Plugin parameter `compileSourceRoots` của project sau các plugin setup để xác định danh sách source thật sự được compile.

### 6.2. Generated resources không phải Java source

Nếu công cụ sinh `.properties`, `.json`, template hay file khác để copy vào JAR, thường cần cấu hình resources/`build-helper:add-resource` hoặc Resources Plugin, không phải `add-source`.

Nếu nó sinh file `.java`, dùng source root. Nếu sinh `.class` đã biên dịch, cần cân nhắc output/packaging theo đúng plugin, không chỉ cho Compiler Plugin quét file class như source.

## 7. Generated test sources: pipeline tương tự nhưng classpath khác

Nếu công cụ sinh Java **dành riêng cho test**, không nên thêm nó vào compile source roots của ứng dụng. Dùng các phase và goal riêng:

```text
generate-test-sources  →  sinh target/generated-test-sources/demo
process-test-sources   →  đăng ký test source root
test-compile           →  compiler:testCompile
test                   →  surefire:test
```

Ví dụ đăng ký test sources:

```xml
<plugin>
    <groupId>org.codehaus.mojo</groupId>
    <artifactId>build-helper-maven-plugin</artifactId>
    <version>3.6.0</version>
    <executions>
        <execution>
            <id>register-generated-tests</id>
            <phase>process-test-sources</phase>
            <goals>
                <goal>add-test-source</goal>
            </goals>
            <configuration>
                <sources>
                    <source>${project.build.directory}/generated-test-sources/demo</source>
                </sources>
            </configuration>
        </execution>
    </executions>
</plugin>
```

Đây là **đoạn cấu hình bổ sung**, không cần thêm vào ví dụ runnable nếu không có công cụ sinh test source. Goal `add-test-source` thường được tài liệu gắn mặc định với `generate-test-sources`, nhưng ta có thể chọn phase sau nó để rõ thứ tự khi công cụ khác đã tạo tệp.

Mã nguồn ở `target/generated-test-sources/demo` chỉ dành cho test, được biên dịch vào `target/test-classes`. Nó không nên trở thành API sản phẩm trong `target/classes` chỉ để một bài test compile thành công.

## 8. Ví dụ đầy đủ, chạy được: sinh Java bằng Maven AntRun, đăng ký root rồi compile

Ví dụ sau minh họa **một pipeline code generation trước compile** mà không yêu cầu schema compiler bên ngoài. Maven AntRun Plugin tạo một file Java cố định ở `generate-sources`; Build Helper đăng ký thư mục vào `project.compileSourceRoots` ở `process-sources`; Compiler Plugin biên dịch cả source viết tay lẫn source sinh ra ở `compile`.

**Điều kiện:** Maven 3 tương thích với các plugin được pin, JDK 17+, quyền tải plugin và JUnit Jupiter khi cache chưa có. AntRun được dùng **chỉ để minh họa lifecycle**; trong production, hãy dùng code generator chuyên dụng thay vì sinh Java bằng task `echo`.

### 8.1. Cây thư mục trước khi build

```text
codegen-lab/
├── pom.xml
└── src/
    ├── main/java/demo/app/Application.java
    └── test/java/demo/app/ApplicationTest.java
```

**Không tạo trước** `target/generated-sources/demo/.../BuildInfo.java`. Chính Maven sẽ tạo nó để chứng minh cả build trên môi trường sạch vẫn hoạt động.

### 8.2. pom.xml hoàn chỉnh

Tệp `codegen-lab/pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">

    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>codegen-lab</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <maven.compiler.release>17</maven.compiler.release>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>5.10.2</version>
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
                        <id>generate-build-info-java</id>
                        <phase>generate-sources</phase>
                        <goals>
                            <goal>run</goal>
                        </goals>
                        <configuration>
                            <target>
                                <mkdir dir="${project.build.directory}/generated-sources/demo/demo/generated"/>
                                <echo file="${project.build.directory}/generated-sources/demo/demo/generated/BuildInfo.java"
                                      encoding="UTF-8"><![CDATA[package demo.generated;

public final class BuildInfo {
    private BuildInfo() {
    }

    public static String message() {
        return "Hello from generated code";
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
                <version>3.6.0</version>
                <executions>
                    <execution>
                        <id>add-generated-java-source-root</id>
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
                <artifactId>maven-resources-plugin</artifactId>
                <version>3.3.1</version>
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
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-jar-plugin</artifactId>
                <version>3.4.2</version>
            </plugin>
        </plugins>
    </build>
</project>
```

**Những điểm phải đọc kỹ:**

- `maven-antrun-plugin:3.1.0:run` sử dụng `<target>` theo cú pháp AntRun 3.x. Không dùng `<tasks>`, `sourceRoot` hoặc `testSourceRoot` của cú pháp AntRun cũ đã bị loại bỏ.
- Ant task `mkdir` tạo package directory dưới `target/generated-sources/demo`; task `echo` ghi một file Java hợp lệ, dùng UTF-8.
- Mã Java được đặt trong `<![CDATA[...]]>` để văn bản Java không bị giải thích như XML markup. Nội dung là Java `package demo.generated;`, phù hợp đường dẫn.
- `build-helper:add-source` chạy ở `process-sources` và thêm **`target/generated-sources/demo`**, không phải đường dẫn tới chính file `BuildInfo.java`.
- Compiler Plugin gắn với `compile` của `jar` packaging, đọc `project.compileSourceRoots` đã được bổ sung, biên dịch source viết tay và source được tạo vào `target/classes`.
- JUnit Jupiter chỉ dùng ở `scope=test`, Surefire chạy sau test-compile.
- Các plugin có version cố định để thay đổi hành vi không phụ thuộc metadata chọn bản plugin mới ngoài chủ đích.

### 8.3. Source viết tay: Application.java

Tệp `src/main/java/demo/app/Application.java`:

```java
package demo.app;

import demo.generated.BuildInfo;

public final class Application {
    private Application() {
    }

    public static String message() {
        return BuildInfo.message();
    }

    public static void main(String[] args) {
        System.out.println(message());
    }
}
```

File này **cố ý import một class chưa có** trong repository lúc ban đầu. Nếu bỏ generator hoặc việc đăng ký source root, `mvn clean compile` không còn thấy `BuildInfo` và sẽ báo lỗi compile. Chính sự phụ thuộc này giúp kiểm tra rõ thứ tự sinh mã trong lifecycle.

### 8.4. Mã JUnit 5: ApplicationTest.java

Tệp `src/test/java/demo/app/ApplicationTest.java`:

```java
package demo.app;

import demo.generated.BuildInfo;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class ApplicationTest {

    @Test
    void mainCodeUsesGeneratedClass() {
        assertEquals("Hello from generated code", Application.message());
    }

    @Test
    void generatedTypeHasExpectedName() {
        assertEquals("demo.generated.BuildInfo", BuildInfo.class.getName());
    }
}
```

Hai test có ý nghĩa khác nhau: test đầu kiểm tra hành vi ứng dụng dùng generated class; test sau kiểm tra generated class có mặt và đúng fully-qualified name trên test classpath. Trong CI bình thường, cả hai phải pass sau khi chạy đủ lifecycle.

### 8.5. Kiểm tra riêng giai đoạn sinh mã

Từ thư mục `codegen-lab/`:

```bash
mvn -B clean process-sources
```

Đây là lệnh chạy các phase từ đầu tới **`process-sources`**, sau khi clean. Nó phải:

1. Chạy goal AntRun tại `generate-sources` để tạo file Java.
2. Chạy goal Build Helper tại `process-sources` để đăng ký nguồn.
3. **Chưa** chạy Compiler Plugin ở `compile`.

Sau lệnh này, tệp được tạo là:

```text
target/generated-sources/demo/demo/generated/BuildInfo.java
```

Nội dung Java do AntRun tạo có ý nghĩa:

```java
package demo.generated;

public final class BuildInfo {
    private BuildInfo() {
    }

    public static String message() {
        return "Hello from generated code";
    }
}
```

Đây là chính mã chứa trong `CDATA` ở POM, được in lại để dễ quan sát. Không cần tự ghi tệp này vào repository; nếu thấy nó tồn tại sau `process-sources` thì generator đã hoàn thành phần tạo file.

### 8.6. Build đầy đủ và xác minh test

Tiếp tục từ project root:

```bash
mvn -B clean verify
```

Trong cấu hình mẫu và môi trường có plugin/JDK phù hợp, Maven dự kiến:

- Xóa thư mục `target` cũ.
- Sinh `BuildInfo.java`.
- Đăng ký source root vừa tạo.
- Biên dịch `BuildInfo.java` và `Application.java`.
- Biên dịch `ApplicationTest.java`.
- Surefire chạy **2 test, 0 failures, 0 errors**.
- JAR Plugin tạo `target/codegen-lab-1.0.0.jar`.

Các đầu ra quan trọng:

```text
target/
├── generated-sources/
│   └── demo/demo/generated/BuildInfo.java
├── classes/
│   ├── demo/generated/BuildInfo.class
│   └── demo/app/Application.class
├── test-classes/
│   └── demo/app/ApplicationTest.class
├── surefire-reports/
│   └── ...
└── codegen-lab-1.0.0.jar
```

Sơ đồ là **các path quan trọng**, không liệt kê mọi tệp Maven plugin tạo. Đọc `target/surefire-reports` để xác nhận test thật sự chạy; `BUILD SUCCESS` một mình không chứng minh test không bị skip.

### 8.7. Chạy class sản phẩm

Trong thư mục `codegen-lab`, trên Linux/macOS:

```bash
java -cp target/classes demo.app.Application
```

Trên Windows PowerShell, cú pháp classpath tương tự:

```powershell
java -cp target\classes demo.app.Application
```

**Stdout của riêng lệnh Java**:

```text
Hello from generated code
```

Vì ví dụ chỉ dùng các lớp Java trong `target/classes` và JDK, không cần JAR dependency ngoài cho lệnh này. Nếu generated code thật sự phụ thuộc library bên ngoài, phải cấu hình runtime classpath hoặc đóng gói phù hợp.

Kiểm tra class đã vào JAR:

```bash
jar tf target/codegen-lab-1.0.0.jar
```

Trong danh sách entry, tìm:

```text
demo/app/Application.class
demo/generated/BuildInfo.class
```

Lệnh `jar tf` thường còn liệt kê manifest, thư mục và metadata khác; đừng kỳ vọng toàn bộ output chỉ gồm đúng hai dòng. JAR trong ví dụ là **JAR thường**, chưa gắn `Main-Class` để chạy `java -jar`.

### 8.8. Thử làm sai thứ tự để thấy lỗi

Nếu sửa AntRun execution từ:

```xml
<phase>generate-sources</phase>
```

thành:

```xml
<phase>process-classes</phase>
```

thì generator sẽ chạy **sau `compile`**. Sau một lượt `mvn clean compile`, file `BuildInfo.java` chưa được tạo vào thời điểm compiler cần nó; dự kiến sẽ báo thiếu `demo.generated.BuildInfo`. Đây là phép thử lý thuyết để hiểu thứ tự phase, **không phải cấu hình nên giữ trong dự án**.

Ngay cả khi chạy `mvn verify` và generator cuối cùng có cơ hội chạy ở `process-classes`, nó vẫn đã **quá muộn đối với lần compile trước đó**. Maven không tự quay lại phase `compile` chỉ vì một file `.java` mới xuất hiện sau đó.

Khôi phục `generate-sources`, chạy lại:

```bash
mvn -B clean verify
```

`clean` giúp xóa tệp generated/class cũ vốn có thể che lỗi thứ tự trong một incremental build trên laptop.

## 9. Tại sao IDE thấy mã sinh ra nhưng Maven CLI không thấy — hoặc ngược lại?

IDE thường có mô hình source root riêng, có thể tự đánh dấu thư mục generated-sources, tự chạy annotation processor hoặc lưu trạng thái source roots từ các lần import trước. Do đó:

- IntelliJ/Eclipse nhìn thấy class trong editor **không bảo đảm** Maven CLI ở CI cũng compile được nếu POM thiếu generator/plugin binding.
- `mvn clean verify` thành công nhưng IDE hiện chữ đỏ có thể do IDE chưa import lại Maven project, chưa nhận generated root, hoặc chưa cho phép annotation processing theo thiết lập của IDE.
- IDE tự sinh code bằng extension riêng có thể làm local chạy được, còn CI thiếu plugin tương ứng.
- Maven compile pass với source sinh từ snapshot cũ trong `target` nếu không clean; môi trường CI sạch dễ phơi bày lỗi.

Cách xử lý nên theo thứ tự:

1. **Ưu tiên build bằng Maven CLI** trên checkout sạch để xem nguồn cấu hình chuẩn của dự án có đầy đủ không.
2. Chạy `mvn clean process-sources` hoặc `mvn clean generate-sources` phù hợp để tạo file cần thiết.
3. Kiểm tra chính xác đường dẫn, package, source root và phase.
4. Import lại dự án Maven trong IDE; xác nhận IDE nhận generated source root hoặc bật annotation processing nếu dự án thực sự dùng.
5. Không “chữa” Maven build bằng việc đánh dấu source root bằng tay **chỉ trong IDE** nếu POM chưa được sửa.

## 10. Nhiều generator cùng tồn tại: tách namespace và quyền sở hữu file

Một dự án lớn có thể sinh Java từ protobuf, OpenAPI, annotation processor và generator nội bộ. Nên phân chia output rõ ràng:

```text
target/generated-sources/
├── protobuf/
│   └── ...
├── openapi/
│   └── ...
├── internal/
│   └── ...
└── annotations/
    └── ...
```

Mỗi generator nên **sở hữu thư mục riêng** hoặc ít nhất có quy tắc tránh đè lên file của generator khác. Nếu hai generator cùng xuất class có cùng package và tên, Compiler Plugin có thể báo duplicate class, hoặc một generator âm thầm ghi đè kết quả của generator kia.

Các lưu ý:

- Không đặt output generated Java vào `src/main/java` nếu không có yêu cầu đặc biệt; dễ lẫn code viết tay với code sinh tự động.
- Không commit file dưới `target` chỉ để hỗ trợ IDE. Thay vào đó, commit **đầu vào** của generator và cấu hình phiên bản generator.
- Nếu policy dự án yêu cầu commit generated source vì lý do audit hoặc người dùng không có generator, cần quy định nguồn sự thật và bước **kiểm tra generated output không bị stale**; đây là thiết kế khác, không phải mặc định của Maven.
- Nếu code generator ghi thêm resource (JSON, descriptor, service file), cần khai báo **resources** tương ứng; thêm Java source root không tự đóng gói mọi resource.
- Không gọi generator từ một shell script riêng trước Maven rồi bỏ plugin khỏi POM nếu muốn `mvn clean verify` tự chạy được trên CI.

## 11. Generated test sources và test fixture trong multi-module

Trong một dự án lớn, generated test fixtures có thể được tạo từ schema để kiểm tra serialization, API contract hoặc dữ liệu mẫu. Chúng có thể nằm trong `target/generated-test-sources/...` và được đăng ký bằng `build-helper:add-test-source`.

**Nhưng đừng nhầm với việc chia sẻ test code giữa các module.** Nếu module service cần test fixture từ module common-test, phải quyết định đóng gói artifact/test-jar hoặc tổ chức thư viện hỗ trợ test đúng cách, khai báo dependency/scope phù hợp. Thêm một source root ở service **không tự mang source** từ module khác sang classpath.

Ví dụ Reactor:

```text
contract-schema
    │
    ▼
api-generated       ← generator trong module này
    │ jar dependency
    ▼
service             ← service dùng API đã biên dịch
```

`service` phụ thuộc vào artifact `api-generated`, không nên cấu hình Build Helper của service trỏ trực tiếp sang thư mục `../api-generated/target/generated-sources/...`. Cách trỏ ngang vào `target` của module khác làm build phụ thuộc thứ tự và layout filesystem, thiếu tính độc lập của artifact.

## 12. JDK, --release và annotation processor compatibility

Maven Compiler Plugin thông thường biên dịch với JDK đang chạy Maven, trừ khi cấu hình Toolchains hoặc compiler khác. `maven.compiler.release=17` đặt mục tiêu ngôn ngữ/API/bytecode được Compiler Plugin hỗ trợ, **không tự cài JDK 17**.

```bash
mvn -version
java -version
javac -version
```

Trong dự án dùng Java 17, cần kiểm tra:

- **JDK chạy Maven** có đáp ứng yêu cầu plugin/generator không?
- **JDK biên dịch** có bị Toolchains Plugin chọn khác runtime Maven không?
- Generator hoặc annotation processor version có tương thích JDK và Maven Compiler Plugin không?
- Java release của generated code có tương thích mục tiêu `--release`? Generator có thể sinh cú pháp Java mới hơn release đã chọn.
- Nếu Java source chính tham chiếu code sinh ra ở cùng compile step, processor/generator có sẵn trong lúc compile không?
- Khi chuyển JDK, các internal Java compiler APIs (`com.sun.tools.javac.*`) mà processor bên thứ ba dùng có thể thay đổi/đòi mở module; ưu tiên processor bản được nhà cung cấp hỗ trợ thay vì tắt các kiểm tra an toàn tùy tiện.

Khi build phát hành, pin version **generator plugin, compiler plugin, annotation processor, JDK/Toolchain** và những dependency đầu vào. Một generator sinh Java 21 syntax nhưng compiler nhắm release 17 sẽ thất bại dù source root được đăng ký chính xác.

### 12.1. Không trộn processor path và runtime classpath tùy tiện

Annotation processor là **công cụ build-time**, thường không cần có mặt trên runtime classpath của ứng dụng. Nếu dự án chỉ dùng processor để tạo implementation, đặt processor JAR riêng trong `annotationProcessorPaths` theo tài liệu phiên bản plugin sẽ rõ ràng hơn việc vô tình đặt nó vào `compile` hoặc `runtime` dependencies.

Đôi khi annotation API/library cần trong source và cả processor thực thi codegen — ví dụ MapStruct annotation API và processor artifact là hai vai trò khác nhau. Chỉ đưa vào classpath ứng dụng những gì mã thực sự cần, còn processor path giữ những dependency thực thi trong compiler.

## 13. Incremental build và các file generated bị stale

Một lỗi rất khó thấy trên laptop là **mã sinh cũ còn tồn tại** dưới `target/generated-sources`. Ví dụ schema đã xóa field `oldName`, nhưng generator không xóa `OldType.java` từ lần trước. Maven compile trên máy ấm có thể vẫn tìm `OldType`, còn CI sạch không có nó.

Để chẩn đoán, so sánh:

```bash
mvn -B compile
mvn -B clean compile
```

Nếu một lệnh pass và một lệnh fail, có thể generator hoặc incremental compiler đang dựa vào output cũ. Điều tra:

1. Generator có **xóa/ghi đè** file khi schema đổi không?
2. Output directory có trộn generated files từ nhiều nguồn không?
3. `clean` có xóa đúng thư mục output không (mặc định dưới `target`)?
4. Generator có hỗ trợ incremental inputs/outputs một cách chính xác không?
5. Một file cũ có vô tình được compile dù schema mới không còn sinh ra nó?
6. IDE có giữ thêm source root/class cache riêng ngoài Maven không?

Không nên chữa tình trạng stale bằng cách commit `target`. Tốt hơn là generator idempotent, có chính sách xóa output cũ phù hợp, nguồn cấu hình rõ ràng và CI có một **clean build** làm phép kiểm chứng.

**Tính tái lập:** nếu generator nhúng timestamp, username, đường dẫn máy hoặc truy cập dịch vụ ngoài không được pin vào Java source, hai build cùng commit có thể sinh byte khác nhau. Pin version, inputs, locale/timezone cần thiết và hạn chế nguồn dữ liệu không ổn định.

## 14. Quan sát POM và nguồn biên dịch thật sự

### 14.1. Xem effective POM

```bash
mvn -B org.apache.maven.plugins:maven-help-plugin:3.4.0:effective-pom
```

Xem plugin được kế thừa từ parent/profile, execution đã gắn vào phase nào và version goal. Trong một Reactor, kiểm tra effective POM của **đúng module cần compile**.

**Giới hạn:** effective POM mô tả model/configuration, nhưng danh sách `compileSourceRoots` có thể được plugin **cập nhật động trong Maven session**. Vì vậy, chỉ đọc file effective POM không chứng minh `add-source` đã thực thi và thêm đường dẫn thành công. Cần quan sát log plugin và kết quả compile.

### 14.2. Kiểm tra các goal cụ thể trong log

```bash
mvn -B clean compile
```

Trong ví dụ, thứ tự có ý nghĩa:

```text
antrun:run             → generate-sources
build-helper:add-source→ process-sources
resources:resources    → process-resources
compiler:compile       → compile
```

Sơ đồ này là **danh sách goal kỳ vọng**, không phải output Maven nguyên văn. Nếu thấy Compiler chạy trước generator hoặc generator không chạy, kiểm tra phase/execution ở POM, lệnh có gọi lifecycle hay goal trực tiếp, profile có active hay không.

### 14.3. Kiểm tra output tại đúng thời điểm

Với demo:

```text
Sau process-sources: target/generated-sources/demo/demo/generated/BuildInfo.java tồn tại
Sau compile:         target/classes/demo/generated/BuildInfo.class tồn tại
Sau test:            target/test-classes/demo/app/ApplicationTest.class tồn tại
Sau package:         target/codegen-lab-1.0.0.jar chứa BuildInfo.class
```

Đây là cách kiểm tra thực tế hơn việc chỉ tìm thấy một thư mục có tên `generated-sources`. Một folder trống không chứng minh generator đã tạo đúng class hoặc source root đã được compiler đọc.

### 14.4. Không bỏ qua test

```bash
mvn -B clean verify
```

Với bài demo, đọc `target/surefire-reports`: dự kiến **2 test** được thực thi. Đừng dùng `-DskipTests` để kết luận codegen hoạt động vì điều đó bỏ qua một lớp xác minh quan trọng. Nếu generator chỉ tạo mã sản phẩm đúng nhưng test compiler không nhận được generated type, lỗi sẽ xuất hiện ở `test-compile` hoặc `test`.

## 15. Những lỗi thường gặp và cách khoanh vùng

| Triệu chứng | Nguồn sai có khả năng | Kiểm tra/sửa |
| --- | --- | --- |
| `package demo.generated does not exist` | Generated Java chưa tạo, root chưa đăng ký hoặc package/path sai | Chạy `clean process-sources`, kiểm tra tệp và `add-source` |
| `cannot find symbol BuildInfo` | Generator chạy quá muộn, output không chứa class mong đợi | So phase với `compile` và nội dung file generated |
| Source có trên đĩa nhưng Maven không compile | Chưa thêm source root, thêm root ở quá sâu hoặc plugin chỉ đăng ký test root | Xem `project.compileSourceRoots`/plugin logs; sửa root path |
| Maven build được ở IDE nhưng fail CI | IDE có generated root/cache riêng, Maven POM thiếu binding | Chạy `mvn clean verify` trên checkout sạch |
| `duplicate class: ...` | Hai generator/nguồn cùng tạo FQCN hoặc copy generated source vào `src/main/java` | Tách output namespace, loại file trùng |
| `invalid source release: 17` | JDK/compiler đang dùng không hỗ trợ Java 17 | Kiểm tra `mvn -version`, Toolchains và `--release` |
| `class file has wrong version` | Generated/precompiled dependency dùng bytecode mới hơn runtime/compiler | So JDK, plugin và release của generator |
| Compile Java pass nhưng testCompile fail | Chưa đăng ký test generated sources hoặc test code dùng class không có ở test classpath | Dùng `add-test-source` và phase test phù hợp |
| Mã generated stale sau khi đổi schema | Generator incremental không dọn file cũ hoặc build không clean | So `compile` với `clean compile`, kiểm tra generator output |
| `mvn compiler:compile` fail nhưng `mvn compile` pass | Gọi trực tiếp goal bỏ qua phase generator/bind source roots | Gọi lifecycle `compile` hoặc phase cao hơn |
| AntRun báo `tasks/sourceRoot removed` | Dùng cấu hình AntRun 1.x với 3.x | Dùng `<target>` và Build Helper như ví dụ |
| Annotation processor không chạy | Processor path/processor class/JDK policy/proc configuration không phù hợp | Kiểm tra Compiler Plugin version và docs processor |
| Generated classes không nằm trong JAR | Source chưa compile vào `target/classes` hoặc packaging khác | Xem `target/classes` và `jar tf` |
| Plugin chỉ có trong `pluginManagement` | Không có execution/binding ở project thực | Khai báo plugin + execution hoặc dùng goal lifecycle đúng |
| Module service không thấy generated-api | Thiếu dependency nội bộ, dù aggregator liệt kê hai module | Khai báo `dependencies` và dùng Reactor `-am` |
| CI dùng file generated khác local | Generator version, schema, encoding, biến môi trường, cache khác | Pin inputs/plugins/JDK, so clean output và báo cáo CI |

## 16. Checklist thiết kế một bước code generation trong Maven

Trước khi chấp nhận thay đổi POM:

- [ ] **Nguồn đầu vào** của generator đã được quản lý, có thể tái lập trên checkout sạch?
- [ ] **Generator/plugin/processor version** được pin và tương thích với Maven/JDK đã chọn?
- [ ] Goal sinh Java được bind vào **phase trước `compile`**, nếu không phải annotation processor chạy trong compiler?
- [ ] Nếu generator không tự đăng ký, **source root đúng cấp** đã được thêm vào `project.compileSourceRoots`?
- [ ] Generated Java dành cho test có đi qua `generate-test-sources`/`add-test-source`/`test-compile` thay vì compile source roots chính?
- [ ] **Package declaration** trong file Java khớp cấu trúc thư mục dưới source root?
- [ ] Generated source và class output được đặt trong thư mục riêng, thường dưới `target`, tránh trùng với source viết tay?
- [ ] Các resources do generator tạo có được khai báo/đóng gói đúng kiểu, không nhầm với Java sources?
- [ ] Nếu generator nằm trong module khác, dependency/Reactor order đã được thiết kế đúng?
- [ ] `mvn clean verify` chạy được từ môi trường sạch và **test thật sự chạy**?
- [ ] JAR/đầu ra cuối cùng chứa **generated class** và runtime classpath đúng?
- [ ] IDE import được generated source root mà không đòi chỉnh tay chỉ có trên máy cá nhân?
- [ ] Build không phụ thuộc output stale, timestamp, file path hoặc nguồn dữ liệu bên ngoài không kiểm soát?
- [ ] Annotation processors có nguồn gốc đáng tin, processor path rõ ràng, không tải plugin tùy ý?
- [ ] Script CI gọi **lifecycle phase** cần thiết, không chỉ một direct goal bỏ qua codegen?

**Kết luận:** với Maven, source Java tự sinh phải xuất hiện **đúng thời điểm** và được **đăng ký đúng source root** trước khi Compiler Plugin biên dịch, trừ trường hợp annotation processing được quản lý ngay trong `javac`. Hãy phân biệt thứ tự **phase của một module**, thứ tự **Reactor giữa các module**, và thứ tự **annotation processing bên trong compiler**. Một thiết kế đúng cho phép `mvn clean verify` tái tạo file Java, compile, test và package từ source/schema gốc mà không dựa vào các file `target` có sẵn.

### Tài liệu tham khảo chính thức

- [Apache Maven — Introduction to the Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html)
- [Apache Maven — POM Reference](https://maven.apache.org/pom.html)
- [Apache Maven Compiler Plugin 3.13.0 — compiler:compile](https://maven.apache.org/plugins-archives/maven-compiler-plugin-3.13.0/compile-mojo.html)
- [Apache Maven AntRun Plugin 3.1.0 — Usage](https://maven.apache.org/plugins-archives/maven-antrun-plugin-3.1.0/usage.html)
- [Apache Maven AntRun Plugin 3.1.0 — antrun:run](https://maven.apache.org/plugins-archives/maven-antrun-plugin-3.1.0/run-mojo.html)
- [MojoHaus Build Helper Maven Plugin — add-source](https://www.mojohaus.org/build-helper-maven-plugin/add-source-mojo.html)
- [MojoHaus Build Helper Maven Plugin — Usage](https://www.mojohaus.org/build-helper-maven-plugin/usage.html)
- [Apache Maven — Guide to Working with Multiple Modules](https://maven.apache.org/guides/mini/guide-multiple-modules.html)
- [Apache Maven Surefire Plugin — JUnit Platform](https://maven.apache.org/surefire/maven-surefire-plugin/examples/junit-platform.html)
