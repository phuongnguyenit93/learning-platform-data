# Build Helper, Exec hoặc Antrun: ranh giới sử dụng cho công việc đặc thù

## 1. Ba công cụ bổ trợ có vẻ giống nhau nhưng giải quyết ba vấn đề khác nhau

Một build Maven chuẩn đã có các phase và plugin chuyên trách để xử lý resources, biên dịch Java, chạy test, đóng gói và phát hành. Tuy nhiên, một dự án thực tế có thể có source code sinh từ công cụ bên ngoài, một thư mục resource không theo cấu trúc mặc định, một chương trình cần chạy trong build hoặc những bước Ant cũ chưa được chuyển thành Maven plugin.

Ba plugin hay được nhắc đến là:

- **Build Helper Maven Plugin** (`org.codehaus.mojo:build-helper-maven-plugin`): **đăng ký thêm** source roots, test source roots, resource roots hoặc gắn artifact bổ sung vào project. Nó không phải một bộ sinh mã hoặc shell runner.
- **Exec Maven Plugin** (`org.codehaus.mojo:exec-maven-plugin`): **chạy một Java main class** qua goal `exec:java`, hoặc **khởi chạy chương trình/tiến trình ngoài** qua goal `exec:exec`. Nó không tự thêm source directory vào mô hình Maven.
- **Apache Maven AntRun Plugin** (`org.apache.maven.plugins:maven-antrun-plugin`): **thực hiện Ant tasks** (copy, mkdir, echo, move, gọi Ant build file...) qua goal `antrun:run`. Nó hữu ích khi phải tích hợp những tác vụ Ant cũ hoặc tác vụ file nhỏ đặc thù; không phải lựa chọn mặc định thay mọi plugin Maven chuyên dụng.

Câu hỏi lựa chọn:

> **Tôi muốn Maven *nhận biết* thêm file/thư mục, muốn *chạy một chương trình*, hay muốn *thực hiện Ant tasks*?**

| Nhu cầu | Công cụ phù hợp | Vì sao? |
| --- | --- | --- |
| Thêm thư mục Java source ngoài `src/main/java` | `build-helper:add-source` | Đăng ký compile source root để Compiler Plugin thấy file |
| Thêm thư mục test Java | `build-helper:add-test-source` | Đăng ký test source root |
| Thêm thư mục resource | `build-helper:add-resource` | Đăng ký thêm nguồn resource để Resources Plugin xử lý |
| Thêm thư mục test resource | `build-helper:add-test-resource` | Đăng ký nguồn resource của test |
| Gắn file ZIP/tar/metadata như artifact kèm classifier | `build-helper:attach-artifact` | Gắn artifact để `install/deploy` xử lý cùng project |
| Chạy `public static void main` với dependency classpath của project | `exec:java` | Chạy Java class trong Maven JVM theo cơ chế của Exec Plugin |
| Chạy tool CLI, script, native executable hoặc `java` ở tiến trình riêng | `exec:exec` | Tạo process với executable/arguments/env/working dir |
| Thực thi tập lệnh Ant như `mkdir`, `copy`, `echo` | `antrun:run` | Dùng khả năng Ant bên trong Maven |
| Compile Java | **Maven Compiler Plugin** | Goal chuyên trách, không nên thay bằng Exec/AntRun |
| Copy/filter resources tiêu chuẩn | **Maven Resources Plugin** | Hỗ trợ resource roots, filtering, encoding |
| Sinh mã OpenAPI/Protobuf/JAXB có plugin chuyên dụng | **Plugin sinh mã chuyên dụng** | Biết input/output, phase, incremental/validation riêng |
| Chạy unit/integration tests | **Surefire/Failsafe** | Test reporting, fork JVM, test lifecycle |
| Tạo JAR/Javadoc/sources archive | **Jar/Source/Javadoc/Assembly/Shade plugins phù hợp** | Giữ đúng artifact metadata, reproducibility |

**Điểm quan trọng:** có thể dùng **kết hợp** các plugin trên vì chúng giải quyết những bước khác nhau. Chẳng hạn AntRun tạo file resource, Build Helper đăng ký thư mục chứa resource ấy, Resources Plugin copy nó vào `target/classes`, sau đó Exec Plugin gọi ứng dụng đọc resource. Bài thực hành phía dưới minh họa đúng chuỗi đó.

## 2. Hiểu lifecycle trước khi chọn plugin

Một phần thứ tự phase của **default lifecycle** Maven:

```text
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
process-test-resources
  |
test-compile
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
```

Khi chạy `mvn clean verify`, Maven chạy clean lifecycle rồi default lifecycle đến `verify`, bao gồm các phase đứng trước đó. Mỗi phase có thể có goals từ **packaging mặc định** và các plugin executions được khai trong POM.

Để sinh và dùng thêm source/resource:

```text
[Generator thực sự tạo file]
     |
     +-- trước compile nếu là .java
     +-- trước process-resources nếu là resource
     |
[Build Helper đăng ký source/resource root]
     |
[Compiler Plugin hoặc Resources Plugin xử lý]
     |
[JAR Plugin đóng gói]
     |
[Exec Plugin chạy chương trình nếu được gọi hoặc bind]
```

Sắp xếp sai thứ tự dẫn đến các lỗi thường gặp:

- Nếu generator tạo Java file **sau `compile`**, Compiler Plugin sẽ không thấy nó trong build ấy.
- Nếu tạo resource **sau `process-resources`**, resource có thể không được copy vào `target/classes`/JAR.
- Nếu gọi `exec:java` ở `validate` để chạy class thuộc **chính project đang build**, class còn chưa được biên dịch.
- Nếu đặt `build-helper:add-source` nhưng không có công cụ nào tạo file, Maven chỉ nhận thêm một source root rỗng.
- Nếu gắn `attach-artifact` trước khi file phụ tồn tại, goal có thể không gắn được artifact cần thiết.

**Đừng hiểu “goal có default phase” là tự chạy mỗi lần Maven đến phase đó.** Goal thường chỉ chạy khi đã có **execution** được bind/goal được packaging bind, hoặc khi gọi trực tiếp. Nếu muốn một goal chạy tại phase nhất định, hãy cấu hình execution rõ ràng trong `build/plugins`.

## 3. Build Helper: chỉnh mô hình build, không sinh nội dung

### 3.1. `build-helper:add-source`

Maven Compiler Plugin thông thường biên dịch Java từ `src/main/java`. Nếu project có thêm `src/extra/java` hoặc một generator ghi vào `target/generated-sources/client`, cần để Maven biết đây là **compile source root**.

Ví dụ:

```xml
<plugin>
    <groupId>org.codehaus.mojo</groupId>
    <artifactId>build-helper-maven-plugin</artifactId>
    <version>3.6.2</version>
    <executions>
        <execution>
            <id>include-extra-java</id>
            <phase>generate-sources</phase>
            <goals>
                <goal>add-source</goal>
            </goals>
            <configuration>
                <sources>
                    <source>${project.basedir}/src/extra/java</source>
                </sources>
            </configuration>
        </execution>
    </executions>
</plugin>
```

Đây là **đoạn plugin cần đặt trong `<build><plugins>`**, không phải POM đầy đủ.

**Nó làm gì?** Bổ sung thư mục được chỉ định vào danh sách **compile source roots** của project trong Maven session. Compiler Plugin sẽ thấy các file `.java` phù hợp khi phase `compile` chạy.

**Nó không làm gì?** Không tạo file Java, không chạy OpenAPI generator, không copy thư mục và không bắt project phải dùng thêm một thư viện Java.

Khi source thực sự được sinh, hãy đặt goal sinh mã **trước compile** rồi gọi `add-source` nếu generator chưa tự đăng ký source root. Nhiều plugin code-generation chuyên dụng **đã tự thêm** generated source directory, nên không cần Build Helper thêm lần nữa. Đừng khai nguồn trùng lặp chỉ vì thấy project có thư mục `target/generated-sources`.

### 3.2. `build-helper:add-test-source`

Nếu test Java nằm trong `src/integration-test/java` hoặc thư mục bất thường:

```xml
<execution>
    <id>include-extra-test-java</id>
    <phase>generate-test-sources</phase>
    <goals>
        <goal>add-test-source</goal>
    </goals>
    <configuration>
        <sources>
            <source>${project.basedir}/src/extra-test/java</source>
        </sources>
    </configuration>
</execution>
```

Đây là **đoạn execution** thuộc Build Helper Plugin, không phải build độc lập. Nó thêm **test source root**, không có nghĩa test runner sẽ tự chọn/báo cáo tất cả test theo loại riêng: Surefire/Failsafe vẫn có quy tắc nhận diện test, phase và cấu hình của chính chúng.

### 3.3. `build-helper:add-resource`

Maven Resources Plugin thường copy `src/main/resources` vào `target/classes`. Nếu bạn có tài nguyên sinh tại `target/generated-resources/custom`, Build Helper có thể đăng ký thêm resource root:

```xml
<execution>
    <id>include-generated-resources</id>
    <phase>generate-resources</phase>
    <goals>
        <goal>add-resource</goal>
    </goals>
    <configuration>
        <resources>
            <resource>
                <directory>${project.build.directory}/generated-resources/custom</directory>
                <filtering>false</filtering>
            </resource>
        </resources>
    </configuration>
</execution>
```

**Khác `add-source`:** cấu trúc config gồm `<resources><resource><directory>...`, không phải `<sources><source>...`. Đặt goal ở `generate-resources` để nguồn mới được biết đến **trước** `process-resources`. Khi tới `process-resources`, Maven Resources Plugin mới thực hiện việc copy/processing theo resource model.

Nếu chỉ cần resource root tĩnh, bạn cũng có thể cấu hình trực tiếp `<build><resources>` trong POM. **Không cần Build Helper cho mọi thư mục tài nguyên phụ**; nó hữu ích nhất khi thư mục phát sinh động trong lifecycle hoặc khi muốn thêm root mà không thay thế cấu hình resources khác.

### 3.4. `build-helper:add-test-resource`

Tương tự, thêm test resources vào danh sách để goal `resources:testResources` xử lý ở `process-test-resources`. Với các file test config, phải hiểu `target/test-classes` có thể được đặt trước `target/classes` trên test classpath; resource trùng tên có thể che nhau.

### 3.5. `build-helper:attach-artifact`

Goal này **gắn file đã có** như artifact kèm theo của project, để `install`/`deploy` có thể xử lý. Ví dụ một ZIP do **công cụ khác tạo trước**:

```xml
<execution>
    <id>attach-extra-zip</id>
    <phase>package</phase>
    <goals>
        <goal>attach-artifact</goal>
    </goals>
    <configuration>
        <artifacts>
            <artifact>
                <file>${project.build.directory}/dist/data-bundle.zip</file>
                <type>zip</type>
                <classifier>data</classifier>
            </artifact>
        </artifacts>
    </configuration>
</execution>
```

Đây chỉ là **snippet**, yêu cầu file `target/dist/data-bundle.zip` tồn tại **trước khi attach**. Build Helper **không tạo ZIP**. `classifier=data` cho phép artifact được phân biệt với primary artifact của project. Hãy dùng plugin chuyên dụng nếu mục đích là tạo sources JAR, Javadoc JAR, assembly hay shaded JAR; các plugin ấy thường tự attach artifact đúng quy ước.

### 3.6. Khi không nên dùng Build Helper

- Chỉ muốn copy file `src/main/resources`: Resources Plugin đã hỗ trợ mặc định.
- Chỉ muốn đặt một thư mục source duy nhất khác mặc định: `<build><sourceDirectory>` là lựa chọn có thể cân nhắc, nhưng **thay** source root chính, khác với **thêm** root.
- Generator đã đăng ký source directory: khai thêm `add-source` có thể thừa và gây khó điều tra.
- Muốn chạy generator: Build Helper **không** thực hiện generator.
- Muốn có resources vào JAR nhưng chỉ khai `add-source`: source root không phải resource root.

## 4. Exec Plugin: thực thi chương trình, không tự chỉnh source roots

MojoHaus Exec Maven Plugin có hai goals chính với hành vi rất khác nhau.

### 4.1. `exec:java` — chạy Java main trong JVM đang chạy Maven

Ví dụ CLI (sau khi project đã compile):

```bash
mvn org.codehaus.mojo:exec-maven-plugin:3.7.0:java -Dexec.mainClass=demo.App
```

Với goal `exec:java`:

- Plugin nạp/chạy Java main class bằng cơ chế của nó **trong Maven JVM**, không tự tạo một JVM Java mới.
- Classpath thường được dựng từ output của project và project dependencies theo `classpathScope`. Mặc định của plugin hiện tại là `runtime`; có thể đặt `test` nếu muốn chạy một Java class phụ thuộc test scope.
- Plugin xử lý thread groups và class loaders theo cơ chế riêng; những chương trình tạo server/background thread hoặc gọi `System.exit` có thể gây hành vi không giống `java -cp` độc lập.
- Mọi JVM options liên quan tiến trình như heap size thường phải được đặt trên **JVM khởi động Maven** (ví dụ qua `MAVEN_OPTS`), không thể kỳ vọng `-Dexec.args=-Xmx...` tạo một Java VM mới.
- Khi job xử lý dữ liệu đặc biệt đáng tin và không cần isolation, `exec:java` có thể tiện để chạy một class trong build. Với process cần isolation, ưu tiên `exec:exec`.

Cấu hình trong POM:

```xml
<plugin>
    <groupId>org.codehaus.mojo</groupId>
    <artifactId>exec-maven-plugin</artifactId>
    <version>3.7.0</version>
    <configuration>
        <mainClass>demo.App</mainClass>
        <classpathScope>runtime</classpathScope>
    </configuration>
</plugin>
```

Chỉ đặt `<plugin>` dưới `build/plugins` chưa tự bind goal vào phase. Để chạy khi gọi `mvn exec:java`, cấu hình `mainClass` giúp không cần truyền lại trên command line. Nếu muốn chạy trong lifecycle, khai `<executions>` với phase/goal thích hợp **sau khi class đã compile**.

**Lưu ý an toàn:** chạy code trong Maven JVM có thể chạm tới system properties, threads và tài nguyên của build process; không nên coi nó là sandbox. Với chương trình dài hạn hoặc tool có thể gọi `System.exit`, dùng process ngoài thay vì tin rằng Exec Plugin sẽ cô lập mọi tác động.

### 4.2. `exec:exec` — khởi chạy tiến trình ngoài

Ví dụ gọi lệnh Java để hiển thị version:

```bash
mvn org.codehaus.mojo:exec-maven-plugin:3.7.0:exec -Dexec.executable=java -Dexec.args=-version
```

Lệnh này **phụ thuộc `java` trên PATH/executable discovery của môi trường**, có thể không trùng JDK mà Maven dùng hoặc compiler toolchain. Output của `java -version` thường đi ra stderr; không coi đó là stdout cố định của một bản JDK cụ thể.

Một cấu hình POM dùng danh sách arguments tách biệt:

```xml
<plugin>
    <groupId>org.codehaus.mojo</groupId>
    <artifactId>exec-maven-plugin</artifactId>
    <version>3.7.0</version>
    <configuration>
        <executable>java</executable>
        <arguments>
            <argument>-version</argument>
        </arguments>
    </configuration>
</plugin>
```

Trong trường hợp này, Exec Plugin chạy **một process ngoài**, không phải class loader trong Maven JVM. Có thể cấu hình `workingDirectory`, `environmentVariables`, `arguments`, timeout và xử lý exit code theo khả năng của plugin/version; kiểm tra documentation goal thật trước khi dùng.

**Vì sao khai từng `<argument>` tốt hơn ghép command string?** Giảm lỗi quoting/escaping khi path có dấu cách và tránh phụ thuộc vào cách shell tự tách tham số. Exec Plugin không mặc định chạy câu lệnh thông qua Bash/PowerShell như người dùng gõ trong terminal, trừ khi bạn **chủ động gọi shell làm executable**. Không gửi nguyên các chuỗi command do đầu vào không tin cậy cung cấp vào shell.

### 4.3. So sánh `exec:java` và `exec:exec`

| Thuộc tính | `exec:java` | `exec:exec` |
| --- | --- | --- |
| Chạy cái gì | Java main class | Executable bên ngoài, có thể là `java` hoặc tool khác |
| JVM/process | Chạy trong Maven JVM | Spawn process riêng |
| JVM version | JVM chạy Maven | Theo executable được chọn, có thể khác |
| Classpath | Plugin dựng từ project output/dependencies | Do cấu hình exec:exec, arguments và launcher |
| Thích hợp | Job Java ngắn cần project classpath, demo, tool in-process | CLI/codegen ngoài, Java cần JVM riêng, native tool |
| Rủi ro | Thread/System.exit/system properties ảnh hưởng Maven process | PATH, shell quoting, executable availability, exit code, portability |
| Phụ thuộc Maven lifecycle | Goal cần được gọi/bind | Goal cần được gọi/bind |

**Không dùng `exec:java` để thay Compiler Plugin** chỉ vì nó có chữ “java”: class của project phải được compile trước thì main class mới có thể chạy.

### 4.4. `classpathScope` và generated code

`exec:java` có tham số `classpathScope`, ví dụ `runtime`, `compile` hoặc `test`:

```bash
mvn org.codehaus.mojo:exec-maven-plugin:3.7.0:java -Dexec.mainClass=demo.App -Dexec.classpathScope=runtime
```

`classpathScope` quyết định **dependency classpath** khi chạy Java main, không quyết định thư mục source nào Compiler Plugin biên dịch. Một class chưa compile không xuất hiện chỉ vì bạn đổi scope thành `test`. Nếu cần chạy Java code generator trước `compile`, nên đóng gói generator thành artifact có sẵn hoặc dùng plugin chuyên dụng; **không trông chờ class generator nằm trong source chưa compile của chính module đó**.

## 5. AntRun Plugin: nhúng Ant tasks trong Maven

AntRun giúp chạy một số tác vụ Ant khi Maven chưa có plugin thích hợp hoặc dự án cần duy trì logic Ant cũ.

Ví dụ:

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-antrun-plugin</artifactId>
    <version>3.2.0</version>
    <executions>
        <execution>
            <id>create-banner</id>
            <phase>generate-resources</phase>
            <goals>
                <goal>run</goal>
            </goals>
            <configuration>
                <target>
                    <mkdir dir="${project.build.directory}/generated-resources/banner"/>
                    <echo file="${project.build.directory}/generated-resources/banner/message.txt"
                          message="generated-by-AntRun"
                          encoding="UTF-8"/>
                </target>
            </configuration>
        </execution>
    </executions>
</plugin>
```

Đây là plugin snippet, chưa phải POM đầy đủ. Khi đến `generate-resources`:

1. Maven gọi `antrun:run`.
2. Ant `mkdir` tạo thư mục trong `target`.
3. Ant `echo` tạo file resource.
4. **Chỉ khi có một cơ chế resource root thích hợp**, Maven Resources Plugin ở phase `process-resources` mới đưa resource đó vào output/JAR. Trong bài thực hành, Build Helper đảm nhiệm đăng ký root.

### Tại sao AntRun không thay Build Helper?

AntRun tạo file, copy file, chạy Ant tasks; việc đó **không tự đăng ký** source root cho Compiler Plugin hay resource root cho Maven Resources Plugin. Trong AntRun 3.x, các tham số cũ `sourceRoot` và `testSourceRoot` đã bị loại bỏ; tài liệu chính thức hướng dẫn dùng **Build Helper** cho trường hợp thêm source roots.

### `target` thay `tasks` từ AntRun 3.x

Nếu thấy cấu hình cũ:

```xml
<configuration>
    <tasks>
        <!-- Legacy AntRun configuration: không dùng cho AntRun 3.x -->
    </tasks>
</configuration>
```

đừng copy vào AntRun 3.x: tham số `tasks` đã bị loại bỏ, thay bằng `<target>`. Phần Ant lớn/khó đọc nên tách sang `build.xml` và gọi Ant task `<ant>`, hoặc cân nhắc chuyển sang plugin Maven chuyên dụng.

### Chọn AntRun có giới hạn

Dùng tốt cho:

- Một số file operations ngắn như `mkdir`, `copy`, `move`, `echo` phục vụ quá trình migrate từ Ant.
- Logic Ant có sẵn mà hiện chưa thể chuyển hết và có test rõ ràng.
- Tạo một file text/resource đơn giản trước khi Maven Resources Plugin copy.

Không nên ưu tiên AntRun cho:

- Compile, test, package, install, deploy — Maven lifecycle/plugins chuyên dụng làm tốt hơn.
- Sinh mã phức tạp có tool riêng và input/output schema.
- Chạy shell commands đặc thù Bash/PowerShell mà Ant không bảo đảm portability; khi bắt buộc dùng CLI, Exec Plugin rõ trách nhiệm hơn.
- Xử lý file bằng script không có quản lý lỗi/đầu ra, gây build “thành công giả”.
- Ghi file vào `src/main/java` hay `src/main/resources` trong build, làm working tree bị sửa sau mỗi lần chạy. Ưu tiên `target/generated-*`.

## 6. Ví dụ chạy được Java 17: AntRun tạo resource, Build Helper đăng ký, Exec chạy App

Ví dụ xây dựng **một project Maven** không phụ thuộc thư viện Java bên ngoài. Chúng ta cố ý đặt một Java class vào `src/extra/java` và tạo một resource ở `target/generated-resources/banner` để quan sát vai trò riêng của từng plugin.

### 6.1. Cấu trúc file

```text
special-work-lab/
├── pom.xml
├── src/
│   ├── main/java/dev/lab/app/Main.java
│   └── extra/java/dev/lab/extra/Feature.java
└── target/                              # tạo khi build
    ├── generated-resources/banner/
    │   └── demo/message.txt
    ├── classes/
    │   ├── dev/lab/app/Main.class
    │   ├── dev/lab/extra/Feature.class
    │   └── demo/message.txt
    └── special-work-lab-1.0.0.jar
```

**Chỉ tạo ba file source ở trên**: `pom.xml`, `Main.java` và `Feature.java`. Không tạo trước nội dung dưới `target/`; build sẽ tạo chúng.

- `Feature.java` chứng minh Build Helper đã thêm một source root ngoài mặc định.
- `message.txt` được **AntRun sinh ra**, không có trong Git.
- `Build Helper:add-resource` cho Maven Resources Plugin biết phải copy từ `target/generated-resources/banner`.
- `Main.java` đọc cả `Feature` và resource để kiểm chứng.
- `Exec:java` có thể gọi main class đã compile sau khi build.

### 6.2. POM hoàn chỉnh — `special-work-lab/pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>dev.lab</groupId>
    <artifactId>special-work-lab</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <maven.compiler.release>17</maven.compiler.release>
    </properties>

    <build>
        <plugins>
            <!-- AntRun thực sự tạo resource trước process-resources -->
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-antrun-plugin</artifactId>
                <version>3.2.0</version>
                <executions>
                    <execution>
                        <id>generate-banner-resource</id>
                        <phase>generate-resources</phase>
                        <goals>
                            <goal>run</goal>
                        </goals>
                        <configuration>
                            <target>
                                <mkdir dir="${project.build.directory}/generated-resources/banner/demo"/>
                                <echo file="${project.build.directory}/generated-resources/banner/demo/message.txt"
                                      message="generated-by-AntRun"
                                      encoding="UTF-8"/>
                            </target>
                        </configuration>
                    </execution>
                </executions>
            </plugin>

            <!-- Build Helper chỉ đăng ký đường dẫn -->
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>build-helper-maven-plugin</artifactId>
                <version>3.6.2</version>
                <executions>
                    <execution>
                        <id>register-extra-java</id>
                        <phase>generate-sources</phase>
                        <goals>
                            <goal>add-source</goal>
                        </goals>
                        <configuration>
                            <sources>
                                <source>${project.basedir}/src/extra/java</source>
                            </sources>
                        </configuration>
                    </execution>
                    <execution>
                        <id>register-generated-resource</id>
                        <phase>generate-resources</phase>
                        <goals>
                            <goal>add-resource</goal>
                        </goals>
                        <configuration>
                            <resources>
                                <resource>
                                    <directory>${project.build.directory}/generated-resources/banner</directory>
                                    <filtering>false</filtering>
                                </resource>
                            </resources>
                        </configuration>
                    </execution>
                </executions>
            </plugin>

            <!-- Compiler vẫn là công cụ biên dịch Java -->
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>

            <!-- Pin version của plugin đóng gói JAR -->
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-jar-plugin</artifactId>
                <version>3.4.2</version>
            </plugin>

            <!-- Exec:java sẽ được gọi trực tiếp sau khi build -->
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.7.0</version>
                <configuration>
                    <mainClass>dev.lab.app.Main</mainClass>
                    <classpathScope>runtime</classpathScope>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

**Phân tích thứ tự chạy** trong POM:

1. Ở `generate-sources`, Build Helper `add-source` đăng ký `src/extra/java`.
2. Ở `generate-resources`, AntRun tạo `demo/message.txt` trong output; Build Helper `add-resource` đăng ký thư mục gốc của resource. Các executions cùng phase có thể chịu ảnh hưởng của thứ tự khai plugin trong POM; ở đây AntRun được liệt kê trước Build Helper. Tuy nhiên, **cả hai đều hoàn tất trước `process-resources`**, nên việc resource được copy mới là điều cần kiểm tra.
3. Ở `process-resources`, plugin resources theo lifecycle `jar` copy `message.txt` vào `target/classes/demo/message.txt`.
4. Ở `compile`, Maven Compiler Plugin compile Java từ cả source roots `src/main/java` và `src/extra/java`.
5. Ở `package`, Jar Plugin tạo `target/special-work-lab-1.0.0.jar` gồm classes và resource.
6. **Exec Plugin không tự chạy ở `package`**, vì chúng ta không gắn goal `java` vào lifecycle. Nó được gọi chủ động sau khi build để tránh nhầm lẫn “khai plugin = tự động chạy”.

Ở đây phần plugin configuration dùng ba plugin với **vai trò rạch ròi**. Nếu không có `build-helper:add-resource`, resource được sinh tại `target/generated-resources/...` chưa chắc xuất hiện trong output/JAR. Nếu không có `build-helper:add-source`, Compiler Plugin không thấy `Feature.java` từ source root phụ.

### 6.3. Source phụ — `src/extra/java/dev/lab/extra/Feature.java`

```java
package dev.lab.extra;

public final class Feature {
    private Feature() {
    }

    public static String describe() {
        return "extra-source-OK";
    }
}
```

Đây là một Java class độc lập, không có external dependency. Lưu đúng path theo package. Nếu bạn đặt nhầm ở `src/main/extra` nhưng POM đăng ký `src/extra/java`, compile không tìm thấy class.

### 6.4. Source chính — `src/main/java/dev/lab/app/Main.java`

```java
package dev.lab.app;

import dev.lab.extra.Feature;
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;

public final class Main {
    private Main() {
    }

    public static void main(String[] args) throws IOException {
        System.out.println("EXTRA=" + Feature.describe());

        try (InputStream in = Main.class.getClassLoader()
                .getResourceAsStream("demo/message.txt")) {
            if (in == null) {
                throw new IOException("Missing resource demo/message.txt");
            }
            String message = new String(
                    in.readAllBytes(), StandardCharsets.UTF_8
            ).trim();
            System.out.println("RESOURCE=" + message);
        }
    }
}
```

Giải thích:

- `import dev.lab.extra.Feature` khiến compiler phải thực sự nhận `src/extra/java`.
- `getResourceAsStream("demo/message.txt")` dùng đường dẫn **từ classpath root**, không phải `target/generated-resources/banner/demo/message.txt`.
- Nếu `in == null`, chương trình báo lỗi rõ thay vì `NullPointerException`.
- `trim()` tránh khác biệt xuống dòng cuối resource do cách Ant echo ghi file.
- `readAllBytes()` và `StandardCharsets.UTF_8` có sẵn trong Java 17.

### 6.5. Build toàn bộ project

Yêu cầu:

- JDK **17+**, Maven 3.x tương thích các plugin versions đã pin.
- Maven có thể resolve các plugin từ Maven Central/mirror. Source Java không cần thêm thư viện bên ngoài.
- Đứng tại thư mục `special-work-lab/` có POM.

```bash
mvn -version
mvn -B -ntp clean verify
```

Lệnh `clean verify` sẽ chạy clean lifecycle rồi default lifecycle đến `verify`. Những output cần xuất hiện sau khi Maven báo `BUILD SUCCESS`:

```text
target/generated-resources/banner/demo/message.txt
target/classes/demo/message.txt
target/classes/dev/lab/extra/Feature.class
target/classes/dev/lab/app/Main.class
target/special-work-lab-1.0.0.jar
```

Đây là **các path dự kiến**, không phải stdout Maven nguyên văn. Nếu plugin resolve lỗi vì network/proxy/permission, phải xử lý repository trước khi kết luận cú pháp Maven sai.

### 6.6. Chạy bằng Java trực tiếp, xác minh stdout

Từ `special-work-lab/` trên Linux/macOS hoặc Windows (đường path dùng dấu `/` thường cũng được Java chấp nhận):

```bash
java -cp target/classes dev.lab.app.Main
```

**Stdout chính xác của chương trình:**

```text
EXTRA=extra-source-OK
RESOURCE=generated-by-AntRun
```

Đây là **stdout của `Main.main()`**, không phải toàn bộ log Maven, vì Maven build có các dòng plugin và trạng thái riêng. Khi Java launcher dùng `target/classes`, nó đọc resource đã được Resources Plugin copy.

### 6.7. Chạy cùng chương trình qua Exec Plugin

Vẫn tại root project, sau `mvn clean verify`:

```bash
mvn -q org.codehaus.mojo:exec-maven-plugin:3.7.0:java
```

Vì POM đã đặt `<mainClass>dev.lab.app.Main</mainClass>`, Exec Plugin không cần `-Dexec.mainClass`. Trên một môi trường bình thường, **hai dòng stdout do Java main phát ra** vẫn là:

```text
EXTRA=extra-source-OK
RESOURCE=generated-by-AntRun
```

Các cảnh báo/diagnostic logs do Maven/Exec Plugin nếu có **không được coi** là stdout của chương trình và có thể khác nhau. Trong ví dụ này, Java main không có daemon thread hay `System.exit` nên `exec:java` phù hợp để quan sát.

**Khác biệt quan trọng:** `java -cp` dùng một JVM mới, còn `exec:java` thực thi trong Maven JVM. Hai command có thể cho cùng output nhưng **không tương đương về process isolation, JVM options hoặc class loader/thread behavior**.

### 6.8. Xác nhận resource đã nằm trong JAR

Chạy:

```bash
jar tf target/special-work-lab-1.0.0.jar
```

Tìm ít nhất ba entry:

```text
dev/lab/app/Main.class
dev/lab/extra/Feature.class
demo/message.txt
```

Đây là các **entry cần tìm trong danh sách dài**, không phải toàn bộ output của `jar tf`. Sau đó có thể chạy bằng JAR trên classpath:

```bash
java -cp target/special-work-lab-1.0.0.jar dev.lab.app.Main
```

Stdout dự kiến vẫn:

```text
EXTRA=extra-source-OK
RESOURCE=generated-by-AntRun
```

Không dùng `java -jar ...` ở đây vì POM không cấu hình `Main-Class` trong manifest. JAR vẫn hoàn toàn hợp lệ khi chạy bằng `-cp` với tên class chính.

### 6.9. Tự thí nghiệm để hiểu ranh giới

Thí nghiệm A — **bỏ execution `register-extra-java`** rồi chạy `mvn clean compile`. Vì `Main.java` import `Feature` nhưng source root phụ không được đăng ký, compiler sẽ gặp lỗi kiểu không tìm thấy package/class `dev.lab.extra`. Đây là hệ quả dự kiến; thông báo cụ thể tùy Compiler/JDK version.

Thí nghiệm B — **bỏ execution `register-generated-resource`** nhưng giữ AntRun. Maven vẫn tạo `target/generated-resources/banner/demo/message.txt`, nhưng không tự biết phải copy thư mục đó vào `target/classes`. Sau `mvn clean verify`, chạy `Main` sẽ không tìm thấy `demo/message.txt` và ném `IOException`. Thí nghiệm cho thấy **file được tạo** khác với **file được đưa lên classpath**.

Thí nghiệm C — **bỏ AntRun** nhưng giữ Build Helper `add-resource`. Thư mục đã đăng ký nhưng sau `clean` nó trống/chưa tồn tại, nên không có `message.txt` để copy; không thể kỳ vọng Build Helper tự sinh resource.

Thí nghiệm D — **bỏ Exec Plugin** trong POM. `mvn clean verify` vẫn có thể compile và package ứng dụng, vì Exec **không** phải plugin cần thiết của default Java build ở đây. Bạn vẫn có thể chạy bằng `java -cp`, hoặc gọi Exec Plugin qua đầy đủ tọa độ và truyền `-Dexec.mainClass=...` nếu plugin khả dụng.

Chỉ thực hiện các thí nghiệm như **biến thể riêng**, không sửa POM chuẩn trong khi kiểm chứng stdout chuẩn và rồi lấy log sai làm bằng chứng.

## 7. Khi generator thật sự sinh Java source

Ví dụ trên dùng `src/extra/java` có sẵn để chứng minh `add-source`. Trong project thực tế, nguồn bổ sung thường **được tạo bởi generator** ở mỗi build. Giả sử công cụ OpenAPI sinh file Java vào:

```text
target/generated-sources/openapi/
    dev/lesson/client/ApiClient.java
```

Một pipeline đúng có thể là:

```text
generate-sources:
    (1) chạy plugin generator chuyên dụng
    (2) nếu plugin chưa tự làm: build-helper:add-source
compile:
    (3) maven-compiler-plugin compile cả Java sinh ra
```

Khai Build Helper (nếu thực sự cần):

```xml
<execution>
    <id>register-generated-openapi</id>
    <phase>generate-sources</phase>
    <goals>
        <goal>add-source</goal>
    </goals>
    <configuration>
        <sources>
            <source>${project.build.directory}/generated-sources/openapi</source>
        </sources>
    </configuration>
</execution>
```

**Đây chỉ là một execution fragment** của Build Helper Plugin, không phải một cấu hình OpenAPI generator. Bạn phải có plugin/tool tạo thật các Java files trước `compile`. Phần lớn generator được bảo trì tốt có thể tự cấu hình source roots; hãy đọc tài liệu generator trước khi thêm Build Helper.

### Dùng Exec để gọi code generator ngoài

Nếu generator là một **CLI executable độc lập** chưa có Maven plugin phù hợp, dùng `exec:exec` với execution ở `generate-sources` để gọi CLI ấy. Sau đó `build-helper:add-source` có thể đăng ký thư mục output. Điều kiện cần:

- Exe đã được cài/cấp trong CI và có version pin.
- Paths/arguments được truyền một cách tường minh, tránh shell injection.
- Input schema/source được quản lý trong repo hoặc artifact ổn định.
- Tool ghi output **dưới `target/generated-sources`**.
- Execution được chạy đúng **trước** Compile Plugin.
- Failure exit code được Maven nhận diện và fail build.
- File sinh ra không xóa/sửa ngược source chính hoặc secrets.

Nếu generator yêu cầu cả Docker, Python, Node, protoc..., hãy cân nhắc plugin chuyên trách hoặc containerized build step. Không mặc định một lệnh `exec:exec` là portable trên Linux/Windows/CI.

### Nếu vừa generator vừa Build Helper ở cùng `generate-sources`

Khi cùng phase, thứ tự execution có thể phụ thuộc **thứ tự khai plugin/executions** và các default lifecycle bindings. Để dễ hiểu và tái lập, đặt generator **trước** Build Helper trong POM; xác minh bằng Maven log và `help:effective-pom`. Cách an toàn hơn là tổ chức để generator hoàn thành trước `compile` và không làm Build Helper phụ thuộc nội dung thư mục được sinh vào một thời điểm không chắc chắn.

## 8. Dùng tài nguyên sinh mã đúng cách

Không phải file output nào cũng cần đăng ký resource root:

- Code Java `.java` → **source root** để Compiler Plugin biên dịch.
- File `.properties`, `.xml`, `.json`, templates được dùng khi chạy → **resource root** để Resources Plugin copy vào classpath/JAR.
- File test data → **test resource root**.
- ZIP/tar/metadata được publish kèm project → **attached artifact** nếu build/release policy cần.
- File báo cáo, logs, HTML test results → thường chỉ là **build output** trong `target`, không cần đóng gói làm resource.

Ví dụ dự án cần dữ liệu sinh từ API schema:

```text
target/
├── generated-sources/api/       # Java source
├── generated-resources/api/     # JSON schema/config runtime
└── reports/api-check/           # báo cáo phân tích
```

Nếu tất cả bị đăng ký làm source root, Compiler Plugin có thể cố xử lý sai nội dung; nếu tất cả bị đăng ký làm resource root, code Java có thể bị copy nguyên `.java` vào JAR mà không compile thành `.class`. Phân loại đúng theo **ngữ nghĩa file**, không chỉ theo tên thư mục.

### Cảnh báo về filtering và encoding

Với `add-resource`, tham số `filtering` có thể khiến Resources Plugin thay placeholder trong file. Với dữ liệu JSON/YAML/binary hoặc files có cú pháp chứa `${...}`, filtering không kiểm soát có thể làm hỏng nội dung. Trong ví dụ, chúng ta dùng `<filtering>false</filtering>` để resource được copy nguyên bytes tương ứng.

Với files sinh bởi một tool, xác minh encoding (UTF-8 khi phù hợp), line endings, deterministic ordering và không chứa absolute paths/timestamps ngẫu nhiên nếu cần reproducible builds.

## 9. Phân biệt `pluginManagement` và `plugins`

Nhiều project quản lý phiên bản ba plugin này ở parent:

```xml
<build>
    <pluginManagement>
        <plugins>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>build-helper-maven-plugin</artifactId>
                <version>3.6.2</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.7.0</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-antrun-plugin</artifactId>
                <version>3.2.0</version>
            </plugin>
        </plugins>
    </pluginManagement>
</build>
```

`pluginManagement` cung cấp version/configuration **khi plugin được sử dụng**. Nó **không tự bind** các goals `add-source`, `exec` hoặc `antrun:run` vào lifecycle trong mọi module.

Nếu child muốn AntRun chạy khi build, nó cần sử dụng plugin trong `build/plugins` với execution thích hợp (hoặc nhận execution đã khai theo cơ chế inheritance từ parent `build/plugins`). Khai một plugin trong `pluginManagement` chỉ là chính sách chung.

**Cẩn thận:** các plugin như Compiler/Jar/Resources đã có default lifecycle bindings với packaging `jar`. Điều này không áp dụng tương tự cho Build Helper, Exec hoặc AntRun như “tự chạy mọi goal”. Bạn phải khai execution hoặc gọi goal trực tiếp.

### Execution ID và tính tái lập

Mỗi execution nên có `id` thể hiện công dụng, ví dụ:

- `register-extra-java`
- `register-generated-resource`
- `generate-banner-resource`
- `run-codegen-cli`

Khi parent và child dùng cùng execution ID, Maven có thể merge/override cấu hình theo effective POM. Khi dùng ID khác, có nguy cơ cả hai execution cùng chạy. Với code generation, chạy lặp có thể tạo file trùng, ghi đè hoặc làm kết quả không ổn định.

## 10. Cách chọn phase cho một tác vụ đặc thù

| Tác vụ | Phase gợi ý | Điều kiện quan trọng |
| --- | --- | --- |
| Kiểm tra input/config trước build | `validate` | Không cần class của project vừa biên dịch |
| Sinh Java source | `generate-sources` | Hoàn tất trước `compile` |
| Đăng ký Java source root | `generate-sources` | Không đợi đến `package` |
| Sinh resource dùng khi chạy | `generate-resources` | Hoàn tất trước `process-resources` |
| Đăng ký resource root | `generate-resources` | Nguồn sẵn sàng trước copy/packaging |
| Sinh test source | `generate-test-sources` | Hoàn tất trước `test-compile` |
| Đăng ký test resource | `generate-test-resources` | Hoàn tất trước `process-test-resources` |
| Chạy Java utility cần class của module | Sau `compile` hoặc trong goal chủ động sau build | Không gọi ở `validate` nếu class chưa build |
| Tạo ZIP phụ rồi attach | Tạo trước; attach ở/ trước `package` khi file đã sẵn | Không attach file chưa tồn tại |
| Chạy report/verification | `verify` | Phải có input/test outputs tương ứng |

Đây là **gợi ý thiết kế**, không phải hợp đồng cố định cho mọi plugin: các goals có default phase/requirements riêng. Hãy chọn phase dựa trên thứ tự dữ liệu được sinh và tiêu thụ.

**Đặc biệt:** `generate-resources` đứng **trước** `process-resources`, còn `generate-sources` đứng trước `compile`. Đó là lý do source/resource generation nên được đặt ở các phase sớm thay vì viết vào thư mục output sau khi JAR đã đóng gói.

## 11. Khi nào nên viết Maven plugin riêng thay vì Exec/AntRun?

Một đoạn Ant/Exec một lần có thể dễ hiểu. Nhưng khi tổ chức dùng lại tác vụ trên nhiều project, nó sẽ gây vấn đề:

- Không có contract input/output rõ ràng.
- Version và phân phối của CLI tool phụ thuộc máy.
- Không có caching/incremental build awareness phù hợp.
- Platform quoting khác nhau.
- Goal bị gọi trong sai phase hoặc chạy lặp.
- Khó test, khó logging chuẩn Maven, khó dùng với reactor song song.
- Khó quản lý errors/secrets/credentials đúng tiêu chuẩn.

**Cân nhắc plugin riêng** hoặc generator plugin có sẵn nếu logic trở thành năng lực build thường xuyên: ví dụ tạo schema, kiểm tra mã nguồn, sinh API clients, biên dịch DSL, đóng gói tài nguyên theo định dạng đặc thù. Một Maven plugin chuyên dụng có goal/parameters/metadata rõ ràng và có thể tự đăng ký source roots phù hợp qua Maven APIs.

**Không cần viết plugin riêng** cho việc thêm một source directory có sẵn hoặc copy một file cấu hình; Build Helper hoặc Resources Plugin đủ phù hợp.

### Cấu trúc quyết định thực tế

```text
Cần xử lý thêm dữ liệu trong build?
│
├─ Chỉ cần Maven nhìn thấy thêm source/resource?
│  ├─ Source Java -> build-helper:add-source
│  └─ Resource    -> build-helper:add-resource
│
├─ Cần tạo nội dung mới?
│  ├─ Có plugin chuyên dụng đáng tin? -> Ưu tiên plugin ấy
│  ├─ Có CLI tool độc lập?            -> exec:exec, giới hạn quyền/version
│  └─ Có Ant task/Ant build cũ?       -> antrun:run
│
├─ Cần chạy Java main class?
│  ├─ Chấp nhận chạy trong Maven JVM? -> exec:java
│  └─ Cần JVM/process riêng?          -> exec:exec với executable Java
│
└─ Cần gắn file phụ đã được tạo để install/deploy?
   └─ build-helper:attach-artifact hoặc plugin chuyên dụng
```

Một giải pháp có thể đi qua **hai nhánh**: tạo file bằng AntRun/Exec rồi đăng ký bằng Build Helper. Không nên ép một plugin làm tất cả.

## 12. Các lỗi thường gặp và chẩn đoán

| Triệu chứng | Nguyên nhân hay gặp | Kiểm tra/sửa |
| --- | --- | --- |
| `cannot find symbol` cho class ở `src/extra/java` | Quên `add-source` hoặc khai sai source path | Xem Compiler source roots, POM, file path/package, chạy `clean compile` |
| Generated Java file tồn tại nhưng không compile | Generator chạy quá muộn hoặc nguồn chưa được đăng ký | Đặt generate-sources trước compile, kiểm tra plugin đã tự add-source chưa |
| `getResourceAsStream` trả `null` | File chưa sinh, chưa add-resource hoặc sai resource path | Xem `target/classes` và `jar tf`, kiểm tra phase `process-resources` |
| Resource được sinh nhưng không có trong JAR | Chỉ có AntRun, chưa đăng ký resource root | Dùng Build Helper hoặc `build/resources`, kiểm tra output |
| `ClassNotFoundException` khi `exec:java` | Project chưa compile, mainClass sai hoặc classpathScope không phù hợp | Chạy build trước, kiểm tra class và exec config |
| `exec:exec` báo executable not found | Tool không có trên PATH hoặc path sai | Pin/cài CLI tool trong CI, dùng executable đầy đủ khi cần |
| `exec:exec` fail exit code khác 0 | Tool ngoài thất bại | Đọc stderr/log của tool, không ẩn lỗi |
| Java main gọi `System.exit` làm build bất thường | `exec:java` chạy trong Maven JVM | Dùng `exec:exec` khi cần process isolation |
| AntRun `tasks` không còn hợp lệ | Cấu hình AntRun cũ dùng API đã bị bỏ | Chuyển sang `<target>` trên AntRun 3.x |
| AntRun tạo Java file nhưng Maven không thấy | AntRun không hỗ trợ `sourceRoot` theo cách cũ | Dùng Build Helper `add-source` |
| Plugin được khai nhưng `mvn verify` không gọi goal | Không có execution/phase tương ứng, chỉ có pluginManagement hoặc direct-goal config | Xem effective POM và lifecycle log |
| Plugin chạy hai lần | Default binding và custom execution/ID trùng mục đích | Kiểm tra phase, goals, execution IDs |
| Plugin chạy trên máy A nhưng CI không có output | Khác hệ điều hành, CLI/path/env hoặc quyền | Dùng plugin portable, pin tool, ghi rõ requirements |
| Build ra file khác nhau giữa các lần chạy | Generator dùng thời gian/current directory/random data không kiểm soát | Làm deterministic, chạy clean build kiểm chứng |
| Artifact phụ không được deploy | File attach sai phase/path/classifier hoặc không có output | Xác nhận file trước attach, install/deploy log |

### Các lệnh xác minh hữu ích

```bash
mvn -version
mvn help:effective-pom
mvn -B -ntp clean verify
jar tf target/special-work-lab-1.0.0.jar
```

Khi cần nhiều log:

```bash
mvn -B -ntp -e clean verify
```

`-e` giúp có stacktrace. Dùng `-X` khi thật sự cần debug plugin parameters/classpath, nhưng **log debug có thể chứa file paths, repository URLs, environment-derived values hoặc secrets**. Không đưa log nguyên trạng lên ticket công khai.

## 13. Portability, bảo mật và hiệu năng

### 13.1. Tránh phụ thuộc shell không cần thiết

Một snippet `exec:exec` có executable `bash` có thể chạy trên Linux CI nhưng không chạy trên Windows. Tương tự, lệnh `cmd.exe` không có trên Linux. Nếu chỉ muốn tạo/copy file, AntRun hoặc Maven Resources Plugin thường portable hơn.

Khi bắt buộc chạy CLI:

- Dùng `<executable>` và các `<argument>` riêng biệt.
- Pin version của CLI, container image hoặc tool distribution.
- Truyền đường dẫn output bằng Maven properties như `${project.build.directory}`.
- Định nghĩa working directory rõ ràng nếu tool dùng path tương đối.
- Không giả định PATH hoặc environment trên CI giống laptop.
- Đảm bảo exit code khác 0 khiến job thất bại, không tắt lỗi để “build xanh”.
- Thử trên hệ điều hành và JDK thực sự được hỗ trợ.

### 13.2. Không lộ secrets

Exec/AntRun có thể đọc environment variables và chạy tiến trình dưới quyền của CI runner. Chúng có thể vô tình in credential qua command-line arguments, `echo`, Maven debug logs hoặc stack traces.

Nguyên tắc:

- Secrets phải đến từ CI secret store/credential provider phù hợp.
- Không ghi token/password vào `pom.xml`, resource được đóng gói hay source Git.
- Không in `env` hoặc debug full command khi có secrets.
- Ưu tiên công cụ có cơ chế secret injection an toàn và least privilege.
- Không thực thi shell command lấy trực tiếp từ input không tin cậy.
- Khi dùng tool ngoài trong build, thẩm định nguồn/phân phối và quyền của runner.

### 13.3. Incremental build và reproducibility

Maven không tự biết input/output dependency graph của mọi Ant task hoặc CLI tùy ý. Nếu tool mỗi lần build đều ghi lại file với timestamp, build cache và artifact reproducibility có thể bị ảnh hưởng.

Tối thiểu:

- Output nằm trong `target/generated-sources`, `target/generated-resources` hoặc thư mục thuộc build directory.
- `mvn clean` có thể dọn được output; không phải sửa repository source.
- Generator có input/version ổn định và fail khi input không hợp lệ.
- Tránh lấy dữ liệu web “latest” không được pin trong build.
- Có integration/smoke test xác nhận JAR cuối chứa đúng source/resource.
- Nếu chạy Maven reactor song song với `-T`, tránh nhiều module ghi cùng một folder chung.
- Khi dùng additional artifact, bảo đảm attached file được tạo đúng một lần và có classifier không gây collision.

### 13.4. Khi dùng IDE

IDE có thể không tự chạy mọi custom Maven execution khi sử dụng chế độ build riêng. Nếu source được tạo bằng Exec/AntRun lúc `generate-sources` nhưng IDE compiler không chạy phase ấy, editor có thể báo “unresolved class” dù `mvn clean verify` thành công.

Để điều tra:

1. Chạy Maven CLI thật để xem build có đúng không.
2. Kiểm tra IDE đang import Maven project và source roots ra sao.
3. Nếu generator plugin hỗ trợ IDE integration, dùng cơ chế phù hợp.
4. Không commit generated Java chỉ để che lỗi IDE khi quy trình project chủ đích sinh chúng từ đầu vào được version hóa.

## 14. Câu hỏi tự kiểm tra

**Câu 1.** Một tool sinh `ApiClient.java` vào `target/generated-sources/openapi`. Bạn chỉ dùng Build Helper `add-source`, nhưng chưa có generator. Điều gì xảy ra?

**Đáp án:** Build Helper chỉ thêm source root; **không có file được sinh**. Cần generator thực sự (ưu tiên plugin chuyên dụng) hoàn thành trước compile.

**Câu 2.** Bạn dùng AntRun tạo `target/generated-resources/banner/demo/message.txt`. Tại sao file chưa có trong JAR?

**Đáp án:** Maven Resources Plugin chỉ xử lý các resource roots được cấu hình/đăng ký. Cần khai resource root `target/generated-resources/banner` qua `build/resources` hoặc `build-helper:add-resource` trước `process-resources`.

**Câu 3.** Chương trình Java main cần heap settings riêng và phải không ảnh hưởng JVM của Maven. Chọn `exec:java` hay `exec:exec`?

**Đáp án:** `exec:exec` để khởi chạy JVM ngoài với executable/arguments cụ thể; `exec:java` chạy trong Maven JVM, nên không cho isolation như một process riêng.

**Câu 4.** Một script cũ dùng Ant `mkdir`, `copy` và chạy trong Maven ở `generate-resources`. Công cụ nào trực tiếp chạy Ant tasks?

**Đáp án:** `maven-antrun-plugin:run` với cấu hình `<target>`. Nếu resource tạo ra cần được đóng gói, phải bảo đảm nguồn resource được Maven biết đến.

**Câu 5.** Tại sao không nên dùng `exec:exec` gọi `javac` thay vì Maven Compiler Plugin?

**Đáp án:** Compiler Plugin đã gắn đúng lifecycle, source roots, compiler config, classpath, test compiler và output của Maven; chạy `javac` thủ công dễ bỏ sót những phần đó và tạo build khó bảo trì.

**Câu 6.** Khai một AntRun execution ở `pluginManagement` của parent có khiến mọi child tự chạy AntRun không?

**Đáp án:** Không chỉ vì nằm trong management. Child cần plugin usage/managed execution được kích hoạt, hoặc parent phải khai plugin thực sự trong `build/plugins` và được kế thừa phù hợp.

**Câu 7.** Build Helper `attach-artifact` có tạo file ZIP không?

**Đáp án:** Không. File phải tồn tại trước khi attach; goal chỉ gắn artifact vào project để install/deploy có thể xử lý.

**Câu 8.** Khi exec tool thành công trên laptop nhưng CI báo command not found, nên sửa gì?

**Đáp án:** Xác minh CLI đã được cài, version pin, PATH/executable, container/OS và working dir của CI; không giấu lỗi bằng ignore exit code.

## 15. Checklist chọn plugin đúng trách nhiệm

- [ ] Tôi đã phân biệt **tạo nội dung** và **đăng ký nội dung vào Maven model**.
- [ ] Java sources dùng source root; resources dùng resource root; test files dùng test roots.
- [ ] Không dùng Build Helper để chạy generator hoặc copy dữ liệu.
- [ ] Nếu generator có Maven plugin chuyên dụng, đã xem nó có tự đăng ký generated source chưa.
- [ ] Nếu dùng `exec:java`, đã hiểu nó chạy trong Maven JVM và classpathScope phù hợp.
- [ ] Nếu dùng `exec:exec`, đã kiểm soát executable, arguments, env, working dir, exit code và OS portability.
- [ ] Nếu dùng AntRun 3.x, đã dùng `<target>` thay vì `<tasks>` hoặc sourceRoot API cũ.
- [ ] Generated source hoàn tất trước `compile`; generated resource hoàn tất trước `process-resources`.
- [ ] Plugin được khai dưới `build/plugins` với execution/phase cần thiết, không chỉ nằm trong `pluginManagement`.
- [ ] Đã kiểm tra paths trong `target` và output cuối cùng bằng `jar tf`.
- [ ] Đã chạy `mvn clean verify` để tránh cache output cũ che lỗi.
- [ ] Có tests hoặc smoke checks cho source/resource được sinh.
- [ ] Build không ghi secrets hay machine-specific absolute paths vào JAR.
- [ ] Có giải pháp để CI cài và pin version external tools khi dùng Exec.
- [ ] Với logic phát triển lớn và tái sử dụng nhiều, đã cân nhắc viết Maven plugin riêng.

**Kết luận:** **Build Helper = đăng ký source/resource/artifact**, **Exec = chạy Java main hoặc process ngoài**, **AntRun = chạy Ant tasks**. Chúng có thể phối hợp, nhưng không nên dùng như ba lựa chọn tùy tiện thay thế cho mọi việc. Trong Maven, hãy ưu tiên plugin chuyên trách, đặt execution đúng phase, giữ generated files dưới `target` và **kiểm tra artifact cuối cùng**, không chỉ nhìn log plugin báo thành công.

## Tài liệu chính thức

- [MojoHaus Build Helper Maven Plugin — Goals](https://www.mojohaus.org/build-helper-maven-plugin/)
- [Build Helper — Usage, add-source/add-resource](https://www.mojohaus.org/build-helper-maven-plugin/usage.html)
- [Build Helper — add-source goal](https://www.mojohaus.org/build-helper-maven-plugin/add-source-mojo.html)
- [Build Helper — add-resource goal](https://www.mojohaus.org/build-helper-maven-plugin/add-resource-mojo.html)
- [Build Helper — attach-artifact goal](https://www.mojohaus.org/build-helper-maven-plugin/attach-artifact-mojo.html)
- [MojoHaus Exec Maven Plugin — Usage](https://www.mojohaus.org/exec-maven-plugin/usage.html)
- [Exec Maven Plugin — exec:java goal](https://www.mojohaus.org/exec-maven-plugin/java-mojo.html)
- [Exec Maven Plugin — exec:exec goal](https://www.mojohaus.org/exec-maven-plugin/exec-mojo.html)
- [Apache Maven AntRun Plugin — Introduction](https://maven.apache.org/plugins/maven-antrun-plugin/)
- [Apache Maven AntRun Plugin — Usage](https://maven.apache.org/plugins/maven-antrun-plugin/usage.html)
- [Apache Maven — Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html)
- [Apache Maven — Guide to Configuring Plugins](https://maven.apache.org/guides/mini/guide-configuring-plugins.html)

*Các phiên bản plugin trong ví dụ được pin để nhất quán và tương ứng tài liệu tham khảo: Build Helper 3.6.2, Exec 3.7.0, AntRun 3.2.0, Compiler 3.13.0, Jar 3.4.2. Khi áp dụng trong hệ thống thực, xác minh Maven/JDK tối thiểu và chính sách cập nhật phiên bản của tổ chức.*
