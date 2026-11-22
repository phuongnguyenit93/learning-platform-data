# Kiểm soát thư mục làm việc, môi trường và mã thoát của công cụ ngoài trong Maven

## 1. Bài toán: tool ngoài cũng là một phần của build

Một build Maven không chỉ gồm `javac`, Surefire và JAR Plugin. Đôi khi dự án phải gọi một chương trình bên ngoài để sinh Java từ schema, tạo resource, chạy native compiler, kiểm tra định dạng hoặc dùng một CLI mà không có Maven plugin chuyên dụng.

Ví dụ: trước khi đóng gói JAR, chương trình `BuildInfoGenerator` cần đọc `inputs/label.txt`, nhận mode từ environment, rồi tạo `build-info.properties`. Nếu thư mục làm việc sai, tool sẽ không tìm thấy input. Nếu environment sai, resource sẽ mang giá trị khác. Nếu tool gặp lỗi mà Maven vẫn tiếp tục, JAR có thể thiếu resource.

Ba điểm phải quản lý cùng lúc:

1. **Working directory:** process con chạy tại đâu, relative paths được giải thích thế nào?
2. **Environment và arguments:** tool nhìn thấy biến môi trường, phiên bản executable, arguments và dữ liệu đầu vào gì?
3. **Exit code và timeout:** khi công cụ trả nonzero, không khởi động được hoặc bị treo, Maven dừng build hay tiếp tục?

Bài dùng **MojoHaus Exec Maven Plugin** để minh họa. Ví dụ đầy đủ có Maven 3.9+, JDK 17+, một Java tool được chạy trong process riêng và một ứng dụng dùng resource được sinh. Các plugin version được pin; nếu chạy trong môi trường không có plugin/dependency cache, Maven cần repository khả dụng.

## 2. Maven process và child process là hai ranh giới khác nhau

~~~text
Terminal / IDE / CI
    |
    v
Maven JVM: mvn clean package
    |
    +-- đọc pom.xml và properties
    +-- dựng execution plan
    |
    +-- exec-maven-plugin:exec
    |      |
    |      +-- executable + argument vector
    |      +-- working directory
    |      +-- environment variables
    |      +-- child stdout / stderr
    |      +-- child exit code / timeout
    |
    +-- resources:resources
    +-- compiler:compile
    +-- surefire:test
    +-- jar:jar
~~~

Khi Maven chạy `exec:exec`, plugin khởi động **một process ngoài JVM Maven**. Child nhận những gì OS và plugin cung cấp. Sau khi child kết thúc, plugin xử lý kết quả để Maven có thể thực thi tiếp hoặc báo build failure.

Các khái niệm cần tách:

| Khái niệm | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| Terminal cwd | Thư mục trước khi gõ `mvn` | Có thể là root workspace hoặc vị trí bất kỳ |
| Module basedir | `${project.basedir}` | Thư mục dự án/module chứa POM |
| Build directory | `${project.build.directory}` | Thường là `target`, nơi chứa output |
| Child working directory | `<workingDirectory>` | Nơi process con giải quyết relative paths |
| Maven property | `-Dresource.mode=ci` | Được Maven dùng khi nội suy POM/plugin parameters |
| Child environment | `APP_MODE=ci` | Được tool đọc qua `System.getenv("APP_MODE")` |
| Child argument | `inputs/label.txt` | Một phần của argv gửi trực tiếp tới executable |
| Maven command exit | Exit status của `mvn` | Chỉ báo thành công/thất bại cho CI |
| Child exit | `System.exit(7)` | Mã do công cụ ngoài quyết định |

**Thay working directory của child không thay terminal cwd và không làm Maven di chuyển sang thư mục khác.** Thêm `APP_MODE` trong Exec Plugin không tự thay đổi environment của cả shell hoặc mọi goal khác.

## 3. exec:exec và exec:java không tương đương

MojoHaus Exec Maven Plugin cung cấp:

| Goal | Chạy ở đâu? | Khi nào nên dùng? |
| --- | --- | --- |
| `exec:exec` | **Process OS riêng** | Java launcher ngoài JVM Maven, Node, protoc, native CLI, generator |
| `exec:java` | **Trong Maven JVM** | Java utility muốn dùng Maven project/plugin classpath, không cần process OS riêng |

Với `exec:exec`:

- Có thể chỉ định một executable bằng tên hoặc path.
- Có thể kiểm soát `<workingDirectory>`.
- Có thể cung cấp child `<environmentVariables>`.
- Có thể theo dõi stdout/stderr và child exit code.
- Có thể giới hạn thời gian với `<timeout>`.
- Có thể chặn build khi child thất bại.

Với `exec:java`, Java main method chạy trong Maven JVM, nên **không có cùng ranh giới process/OS exit status**. Việc chạy Java code có `System.exit(...)` đòi hỏi xem các cơ chế bảo vệ của plugin, vì có nguy cơ ảnh hưởng Maven process. Đừng đổi từ `exec:exec` sang `exec:java` mà vẫn giả định mọi chính sách cwd/env/exit hoạt động y hệt.

Trong bài này chọn **`exec:exec`**, để xem rõ ba tham số cốt lõi của đề bài.

## 4. Nên gắn tool vào phase nào?

Maven default lifecycle có thứ tự (rút gọn các phase liên quan):

~~~text
validate
  -> initialize
  -> generate-sources
  -> process-sources
  -> generate-resources
  -> process-resources
  -> compile
  -> generate-test-sources
  -> process-test-sources
  -> generate-test-resources
  -> process-test-resources
  -> test-compile
  -> test
  -> package
  -> verify
  -> install
  -> deploy
~~~

Với `packaging=jar`, Maven mặc định gắn `resources:resources` ở **process-resources**, `compiler:compile` ở **compile**, `surefire:test` ở **test**, `jar:jar` ở **package**. Phase **generate-resources** thường là nơi thích hợp để tạo các tệp tài nguyên cần được copy tại process-resources.

Với generator tạo **Java source**, thường chọn **generate-sources**, đăng ký thư mục generated sources rồi compiler compile ở phase sau. Với generator tạo **resource**, thường chọn **generate-resources**, khai báo generated resource root để Resources Plugin copy ở **process-resources**.

**Không gắn tool tùy tiện vào `package`** nếu output của tool phải có trước compile hoặc resource processing. Một consumer chạy trước producer có thể không thấy file, hoặc dùng lại file stale từ lần build cũ.

## 5. Cấu hình exec:exec: executable, workingDirectory, arguments

Ví dụ mảnh cấu hình:

~~~xml
<plugin>
    <groupId>org.codehaus.mojo</groupId>
    <artifactId>exec-maven-plugin</artifactId>
    <version>3.7.0</version>
    <executions>
        <execution>
            <id>generate-build-resource</id>
            <phase>generate-resources</phase>
            <goals>
                <goal>exec</goal>
            </goals>
            <configuration>
                <executable>java</executable>
                <workingDirectory>${project.basedir}</workingDirectory>
                <arguments>
                    <argument>${project.basedir}/tools/BuildInfoGenerator.java</argument>
                    <argument>inputs/label.txt</argument>
                    <argument>${project.build.directory}/generated-resources</argument>
                </arguments>
            </configuration>
        </execution>
    </executions>
</plugin>
~~~

Đây là **mảnh plugin** đặt trong `<build><plugins>` của POM. Một POM đầy đủ nằm ở phần thực hành.

**`executable`** chỉ định chương trình OS cần gọi. Nếu chỉ viết `java`, plugin phải tìm được executable phù hợp qua cách phân giải của nó/PATH/toolchain. Nếu gọi một executable trên PATH khác với dự kiến, có thể chạy nhầm Java version hoặc công cụ native version.

**`workingDirectory`** đặt current directory của child process. Theo tài liệu Exec Plugin, khi không chỉ định, mặc định là **basedir**. Nhưng **việc ghi rõ** `${project.basedir}` giúp người đọc thấy hợp đồng và tránh giả định sai về terminal cwd.

**`arguments`** chứa danh sách từng argument; mỗi `<argument>` là một argv element. Không cần một shell đứng giữa chỉ để tách chuỗi. Một path có dấu cách được truyền như một argument duy nhất trong cấu hình dạng list.

**`id` và `phase`** xác định một Maven execution có tên, chạy tại phase cụ thể. Với project JAR, Exec Plugin không tự chạy generator của bạn; phải bind goal vào lifecycle hoặc gọi goal trực tiếp với cấu hình phù hợp.

### Relative paths đi theo working directory nào?

Nếu child chạy tại basedir:

~~~text
cwd = /workspace/external-tool-demo
argument #1 = inputs/label.txt
~~~

thì `Path.of("inputs/label.txt")` trong Java tool là file dưới **module root**. Nếu workingDirectory đổi sang `tools/`, path tương đối này sẽ trỏ tới `tools/inputs/label.txt` và có thể thất bại.

Có hai cách giảm rủi ro:

- Đặt cwd rõ ràng để tương thích với giao ước của external tool.
- Dùng absolute paths do Maven cung cấp cho input/output khi công cụ hỗ trợ.

Không nên dựa ngầm vào chỗ người dùng đứng khi chạy Maven qua IDE hoặc `-f`.

## 6. Kiểm soát môi trường con với environmentVariables

Thêm vào cấu hình của Exec Plugin:

~~~xml
<environmentVariables>
    <APP_MODE>${resource.mode}</APP_MODE>
</environmentVariables>
~~~

với POM property:

~~~xml
<properties>
    <resource.mode>demo</resource.mode>
</properties>
~~~

Khi gọi:

~~~bash
mvn -Dresource.mode=ci clean package
~~~

Maven áp dụng CLI user property `resource.mode=ci`, plugin nội suy nó thành chuỗi `ci`, rồi child nhận environment variable `APP_MODE=ci`. Java tool đọc bằng:

~~~java
String mode = System.getenv("APP_MODE");
~~~

Đây là **mapping tường minh**. Không có mapping thì `-Dresource.mode=ci` không tự xuất hiện trong `System.getenv("APP_MODE")`.

### Phân biệt ba loại -D và environment

| Cách truyền | Ví dụ | Bên sử dụng |
| --- | --- | --- |
| Maven user property | `mvn -Dresource.mode=ci package` | Maven POM/plugin configuration |
| Child OS env | `<APP_MODE>${resource.mode}</APP_MODE>` | `System.getenv` của child |
| Java child JVM system property | `<argument>-Dapp.mode=ci</argument>` trước class hoặc `-jar` | `System.getProperty` trong Java child |
| App command-line argument | `<argument>ci</argument>` sau tên chương trình | `String[] args` |

**`MAVEN_OPTS`** cấu hình JVM chạy Maven; không mặc định là JVM arguments của một Java child khi bạn gọi executable `java`. Nếu muốn `-Xmx512m` hay JVM system property cho child, truyền chúng vào **arguments của child trước main class/JAR**.

### Environment inherited và overridden

Child thường kế thừa nhiều biến môi trường từ Maven process; những entries trong `<environmentVariables>` có thể cung cấp hoặc ghi đè giá trị tương ứng cho child. Do đó:

- `PATH`, `JAVA_HOME`, `HOME`, proxy settings, locale và timezone có thể ảnh hưởng kết quả.
- Không nên giả định environment của developer giống CI.
- Không đưa credential không cần thiết vào environment của tool.
- Không in toàn bộ environment trong logs, vì có thể lộ tokens hoặc thông tin nhạy cảm.

Nếu muốn tham chiếu một environment variable có sẵn từ shell trong POM, Maven thường cho truy cập qua cú pháp `${env.NAME}`. Nếu nó không tồn tại, cần có default/validation rõ ràng; đừng coi mọi biến `env` chắc chắn tồn tại trên mọi platform.

## 7. PATH, JAVA_HOME và tính nhất quán tool version

`<executable>java</executable>` đơn giản nhưng có thể sử dụng Java launcher khác với JVM Maven đang chạy. Kiểm tra:

~~~bash
mvn -version
java -version
~~~

Nếu CLI trên terminal trả Java 17 nhưng CI PATH ưu tiên Java 11, **source-file generator dùng API Java 17 có thể lỗi** dù compiler main project được cấu hình Java 17.

Để build ổn định:

1. Pin JDK ở CI image hoặc toolchain.
2. Xác minh executable version mà plugin thực sự gọi.
3. Khi cần, cấu hình absolute path tới JDK do môi trường quản lý.
4. Không hardcode đường dẫn cá nhân như `C:\Users\someone\...` vào POM chung.
5. Với native CLI, ghi version được hỗ trợ và cách cài đặt/resolve nó.

Ví dụ có thể cân nhắc:

~~~xml
<executable>${java.home}/bin/java</executable>
~~~

`${java.home}` là Java system property của JVM Maven. Trên Windows có thể cần tên `java.exe` hoặc cấu hình toolchain phù hợp; đường dẫn ví dụ không phải cam kết hoạt động với mọi kiểu cài đặt/JDK distribution. Project demo dùng `java` trên PATH và công bố rõ tiền điều kiện Java 17+.

## 8. Return code: 0, nonzero, launch failure

External tool nên có giao ước exit rõ ràng:

- **0**: thành công, file output đáp ứng yêu cầu.
- **Nonzero**: lỗi hoặc trạng thái đặc biệt được tài liệu công cụ quy định.
- **Không khởi động được**: lỗi executable path, quyền thực thi, interpreter, OS; không phải chắc chắn tool đã trả một exit code.
- **Timeout**: tool bị ngắt do chạy quá hạn, plugin fail.

Trong Exec Plugin:

~~~xml
<successCodes>
    <successCode>0</successCode>
</successCodes>
~~~

cho phép **chỉ code 0** thành công. Mặc định trong trường hợp thường dùng, process trả 0 được coi thành công; `successCodes` cho phép bổ sung các mã **thật sự mang nghĩa thành công** theo hợp đồng của một executable đặc thù.

Ví dụ một công cụ trả code `2` cho “không có thay đổi nhưng kết quả hợp lệ” có thể cần cấu hình:

~~~xml
<successCodes>
    <successCode>0</successCode>
    <successCode>2</successCode>
</successCodes>
~~~

**Ví dụ này chỉ minh họa cơ chế**. Không áp dụng cho generator bên dưới: generator dùng code **2 để báo lỗi số arguments**, nên chỉ 0 được chấp nhận.

### Child code không phải Maven command code

Khi Java child gọi `System.exit(7)`, plugin nhận code 7 và fail goal. Shell/CI nhận **Maven command** kết thúc nonzero, nhưng không bắt buộc bằng 7. Bởi vậy pipeline nên kiểm tra Maven success/failure và đọc log để biết child tool trả mã nào.

Không nên “sửa” build đỏ bằng cách cho mọi nonzero vào successCodes. Làm như vậy có thể tạo JAR thiếu generated resources rồi chỉ phát hiện sau deploy.

### Exit code 0 cũng chưa phải kiểm tra output hoàn chỉnh

Một tool viết file rỗng rồi trả 0 có thể vẫn làm Maven pass bước exec. Nên kiểm tra generated file tồn tại, đúng schema/nội dung; thêm unit/integration test hoặc validation goal nếu dữ liệu là bắt buộc.

## 9. Timeout và async điều khiển quan hệ producer-consumer

Một generator có thể treo do network, file locks hoặc lỗi bên trong. Exec Plugin hỗ trợ:

~~~xml
<timeout>30000</timeout>
~~~

Giá trị tính bằng **milliseconds**, tức 30 giây. Giá trị `0` nghĩa là Exec Plugin không đặt timeout theo tham số này. Nếu tool vượt timeout dương, plugin cố kết thúc process và đánh dấu goal thất bại.

Nếu output của tool cần cho phase sau, giữ:

~~~xml
<async>false</async>
~~~

`async=false` là mặc định thông thường của exec:exec. Khi bật `async=true`, Maven có thể đi tiếp trong lúc tool chưa xong; `process-resources` có thể copy thư mục rỗng hoặc file chưa hoàn tất. **Không dùng async cho generator bắt buộc trước compile/package.**

Các script wrapper có thể spawn thêm process con, khiến cleanup khi timeout phức tạp. Không giả định timeout của process do Exec Plugin quản lý luôn kill mọi descendant trên mọi OS.

### stdout/stderr và logging

Các tùy chọn `outputFile`, `inheritIo`, `useMavenLogger` và `quietLogs` ảnh hưởng việc hiển thị child output. Khi debug:

- `stdout` thường chứa kết quả/thông tin chạy.
- `stderr` có thể chứa lỗi hoặc warning.
- **Exit code** mới là tín hiệu chính theo hợp đồng process.
- `outputFile` chuyển output ra tệp, có thể giảm thông tin ở terminal.
- stdout/stderr có buffering khác nhau, không đảm bảo thứ tự dòng tuyệt đối.
- Không xuất secrets hoặc `printenv` toàn bộ để chẩn đoán trên CI.

## 10. Demo đầy đủ: sinh resource bằng Java 17 ở child process

Bài thực hành sau dùng **một Maven project hoàn chỉnh**. Tool generator nằm ngoài `src/main/java`, chạy bằng Java launcher **source-file mode** (hỗ trợ từ Java 11), có working directory và environment riêng.

### 10.1. Cấu trúc thư mục

~~~text
external-tool-demo/
├── pom.xml
├── inputs/
│   └── label.txt
├── tools/
│   └── BuildInfoGenerator.java
└── src/
    ├── main/
    │   └── java/com/example/tooling/App.java
    └── test/
        └── java/com/example/tooling/AppTest.java
~~~

`tools/BuildInfoGenerator.java` là **build tool**, không phải Java source của ứng dụng. Plugin gọi trực tiếp `java path/to/BuildInfoGenerator.java ...`; Java 17 có thể biên dịch và chạy tệp nguồn này trong process con mà không cần module generator riêng.

### 10.2. Tệp inputs/label.txt

Tạo UTF-8 text file:

~~~text
Hello Maven
~~~

Tool sẽ dùng `.strip()` để bỏ whitespace ở hai đầu. Giữ label ASCII đơn giản để ví dụ không phải xử lý escaping phức tạp của `.properties`.

### 10.3. tools/BuildInfoGenerator.java

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public final class BuildInfoGenerator {
    private BuildInfoGenerator() {
    }

    public static void main(String[] args) {
        if (args.length != 2) {
            System.err.println("ERROR: expected INPUT and OUTPUT_DIRECTORY");
            System.exit(2);
            return;
        }

        String mode = System.getenv("APP_MODE");
        if (mode == null || !mode.matches("[A-Za-z0-9_-]+")) {
            System.err.println(
                    "ERROR: APP_MODE must match [A-Za-z0-9_-]+");
            System.exit(7);
            return;
        }

        try {
            String label = Files.readString(
                    Path.of(args[0]), StandardCharsets.UTF_8).strip();

            if (!label.matches("[A-Za-z0-9 ]+")) {
                System.err.println(
                        "ERROR: label must contain letters, numbers or spaces");
                System.exit(8);
                return;
            }

            Path outputDirectory = Path.of(args[1]);
            Files.createDirectories(outputDirectory);

            String content =
                    "mode=" + mode + "\n"
                    + "label=" + label + "\n";

            Files.writeString(
                    outputDirectory.resolve("build-info.properties"),
                    content,
                    StandardCharsets.UTF_8);

            System.out.println(
                    "Generator: mode=" + mode + ", label=" + label);
        } catch (IOException ex) {
            System.err.println(
                    "ERROR: cannot read/write resource: " + ex.getMessage());
            System.exit(9);
        }
    }
}
~~~

**Code đã hoàn chỉnh cho Java 17:** không dùng external libraries; `Files.readString`, `Files.writeString`, `Path` và `.strip()` đều được JDK 17 hỗ trợ.

Cơ chế:

1. `args[0]`: đường dẫn input file; là relative path thì được giải quyết theo child cwd.
2. `args[1]`: output directory; tool tự tạo directory nếu chưa có.
3. `System.getenv("APP_MODE")`: lấy environment của child.
4. `mode` bị giới hạn ký tự `[A-Za-z0-9_-]+`.
5. `label` bị giới hạn `[A-Za-z0-9 ]+`, tránh dấu dòng mới và ký tự đặc biệt trong `.properties`.
6. Nội dung output deterministic: mode + label + hai dòng newline LF.
7. Thành công thì main trả bình thường, process exit 0.
8. Sai cách gọi: `System.exit(2)`; mode sai: 7; label sai: 8; lỗi I/O: 9.

**Không mở rộng cách nối chuỗi này cho mọi input Unicode** nếu chưa có quy tắc escape `.properties`: demo chọn ASCII để kết quả chính xác và dễ kiểm chứng. Khi generator sản xuất dữ liệu thực tế, cần validate, escape và bảo đảm không ghi secret vào output.

### 10.4. pom.xml đầy đủ

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>external-tool-demo</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <resource.mode>demo</resource.mode>
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
        <resources>
            <resource>
                <directory>src/main/resources</directory>
                <filtering>false</filtering>
            </resource>
            <resource>
                <directory>${project.build.directory}/generated-resources</directory>
                <filtering>false</filtering>
            </resource>
        </resources>

        <plugins>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.7.0</version>
                <executions>
                    <execution>
                        <id>generate-build-resource</id>
                        <phase>generate-resources</phase>
                        <goals>
                            <goal>exec</goal>
                        </goals>
                        <configuration>
                            <executable>java</executable>
                            <workingDirectory>${project.basedir}</workingDirectory>

                            <arguments>
                                <argument>${project.basedir}/tools/BuildInfoGenerator.java</argument>
                                <argument>inputs/label.txt</argument>
                                <argument>${project.build.directory}/generated-resources</argument>
                            </arguments>

                            <environmentVariables>
                                <APP_MODE>${resource.mode}</APP_MODE>
                            </environmentVariables>

                            <successCodes>
                                <successCode>0</successCode>
                            </successCodes>
                            <timeout>30000</timeout>
                            <async>false</async>
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
                <version>3.5.2</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-jar-plugin</artifactId>
                <version>3.4.2</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**Đọc POM theo mục tiêu của bài:**

- `exec-maven-plugin` được pin version, không dựa vào plugin version tự thay đổi.
- Execution `generate-build-resource` chỉ chạy ở phase `generate-resources`.
- `executable=java` yêu cầu Java 17+ phù hợp có sẵn trong môi trường.
- `workingDirectory=${project.basedir}` cố định cwd của child.
- Path Java source được truyền bằng một `<argument>` riêng; `inputs/label.txt` được resolve theo cwd.
- Output được gửi tới `${project.build.directory}/generated-resources` thay vì ghi ngẫu nhiên vào project root.
- `environmentVariables` map Maven property `resource.mode` thành child `APP_MODE`.
- `successCodes` chỉ cho phép code 0; generator fail thì Maven fail.
- `timeout=30000` tránh generator nhỏ bị treo mãi.
- `async=false` bảo đảm bước generator hoàn tất trước khi Maven đi tới phase tiếp theo.
- `<resources>` bao gồm `src/main/resources` thông thường **và** directory generated; nếu tự khai báo resources mà bỏ resource root mặc định thì có thể làm mất resources từ source tree.
- Resources Plugin với jar packaging đã có **default binding** ở `process-resources`; chỉ pin version, không khai báo thêm một execution `resources:resources` dư thừa.
- Compiler/Surefire/JAR cũng dùng default bindings, không cần copy lại toàn bộ lifecycle bindings.

Đây là build kiểu **generate → copy → compile → test → package**, không có deploy ra bên ngoài.

### 10.5. src/main/java/com/example/tooling/App.java

~~~java
package com.example.tooling;

import java.io.IOException;
import java.io.InputStream;
import java.io.UncheckedIOException;
import java.util.Properties;

public final class App {
    private App() {
    }

    private static Properties readBuildInfo() {
        try (InputStream input =
                App.class.getResourceAsStream("/build-info.properties")) {

            if (input == null) {
                throw new IllegalStateException(
                        "Missing /build-info.properties");
            }

            Properties properties = new Properties();
            properties.load(input);
            return properties;

        } catch (IOException ex) {
            throw new UncheckedIOException(ex);
        }
    }

    public static String mode() {
        return readBuildInfo().getProperty("mode", "missing");
    }

    public static String label() {
        return readBuildInfo().getProperty("label", "missing");
    }

    public static void main(String[] args) {
        System.out.println("Mode: " + mode());
        System.out.println("Label: " + label());
    }
}
~~~

App đọc resource **trên classpath**, không phụ thuộc vào path của workspace. Khi JAR được chuyển tới nơi khác, nó vẫn đọc resource đã được đóng gói.

`Properties.load(InputStream)` đọc theo quy tắc Java Properties; giá trị demo chỉ là ASCII nên không có vấn đề encoding. Không nên xem cách đọc này là parser UTF-8 tổng quát cho mọi file tùy ý.

### 10.6. src/test/java/com/example/tooling/AppTest.java

~~~java
package com.example.tooling;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;

class AppTest {

    @Test
    void generatedResourceHasExpectedLabel() {
        assertEquals("Hello Maven", App.label());
        assertFalse(App.mode().isBlank());
    }
}
~~~

Test xác nhận file đã được copy vào test runtime classpath, label đúng và mode không trống. Nó không hardcode mode `demo` để vẫn chạy được khi CI chọn mode `ci`.

Nếu generator không tạo file nhưng trả exit code 0, test vẫn có thể phát hiện resource thiếu; đó là lý do không chỉ tin vào exit status.

### 10.7. Chạy build bình thường

Từ thư mục `external-tool-demo`:

~~~bash
mvn -version
java -version
mvn -B clean package
~~~

Generator sẽ in một dòng từ chính code Java:

~~~text
Generator: mode=demo, label=Hello Maven
~~~

Maven log bao quanh dòng này có plugin headings và logs phụ thuộc phiên bản. Tool tạo:

~~~text
target/generated-resources/build-info.properties
~~~

với nội dung chính xác:

~~~properties
mode=demo
label=Hello Maven
~~~

Resources Plugin copy sang:

~~~text
target/classes/build-info.properties
~~~

Sau build thành công, chạy:

~~~bash
java -cp target/external-tool-demo-1.0.0.jar com.example.tooling.App
~~~

**Stdout chính xác của App:**

~~~text
Mode: demo
Label: Hello Maven
~~~

POM demo không thêm `Main-Class` vào manifest, nên dùng `java -cp ... com.example.tooling.App` thay vì tự giả định `java -jar` sẽ biết main class.

Có thể kiểm tra JAR:

~~~bash
jar tf target/external-tool-demo-1.0.0.jar
~~~

Trong output phải có những entries sau (không phải toàn bộ danh sách):

~~~text
build-info.properties
com/example/tooling/App.class
~~~

### 10.8. Đổi mode bằng Maven CLI

~~~bash
mvn -B -Dresource.mode=ci clean package
java -cp target/external-tool-demo-1.0.0.jar com.example.tooling.App
~~~

Stdout của generator trong Maven log:

~~~text
Generator: mode=ci, label=Hello Maven
~~~

Stdout của App:

~~~text
Mode: ci
Label: Hello Maven
~~~

Chuỗi truyền giá trị:

~~~text
-Dresource.mode=ci
      |
      v
Maven property resource.mode
      |
      v
Exec plugin environmentVariables
      |
      v
Child OS environment APP_MODE=ci
      |
      v
BuildInfoGenerator.java -> target/generated-resources
      |
      v
resources:resources -> target/classes -> JAR
~~~

Điều này minh họa **build-time resource variant**. Hai JAR dev/ci có thể cùng tên GAV nhưng mang bytes khác nhau. Nếu mục tiêu chỉ là đổi endpoint/secret khi triển khai ứng dụng, thường nên dùng **runtime configuration** để áp dụng mô hình build once, deploy many.

### 10.9. Thử lỗi exit code 7

Trong bản demo không có side effects bên ngoài, chạy:

~~~bash
mvn -B -Dresource.mode=invalid.mode clean package
~~~

`invalid.mode` chứa dấu chấm, bị Java generator từ chối. Dòng **stderr chính xác từ generator**:

~~~text
ERROR: APP_MODE must match [A-Za-z0-9_-]+
~~~

Generator gọi `System.exit(7)`. Vì `successCodes` chỉ chứa 0, Exec Plugin báo goal thất bại, và Maven dừng trước các phase tiêu thụ resource. Maven command trả status nonzero cho shell/CI; nó **không bắt buộc trả cùng số 7**.

Log của Maven có thể nói process exited with error 7 hoặc một thông báo tương đương tùy phiên bản. Chỉ có dòng stderr ở khối trên là được xác định nguyên văn từ code demo.

Lệnh có `clean` để output build cũ không che lỗi. Không gọi kết quả của lần chạy thất bại là một artifact đã tạo thành công.

### 10.10. Lỗi input và timeout

Nếu xóa `inputs/label.txt` trong **bản copy của demo**, generator sẽ gặp lỗi I/O, in thông báo bắt đầu bằng `ERROR: cannot read/write resource:` và trả code 9. Phần chi tiết exception có thể thay đổi theo OS, nên không khẳng định toàn bộ dòng stderr chính xác.

Nếu tool thật sự chạy quá 30 giây, Exec Plugin timeout và Maven fail. Demo nhỏ thường kết thúc nhanh; đây là policy để bảo vệ CI, không phải cách kiểm tra tốc độ bằng một test nhân tạo.

Khi hết thử nghiệm, khôi phục input file và chạy clean package để có output hợp lệ.

## 11. `mvn -f` và module basedir

Giả sử cấu trúc:

~~~text
workspace/
  external-tool-demo/
    pom.xml
    inputs/label.txt
    tools/BuildInfoGenerator.java
~~~

Khi đứng ở `workspace`, chạy:

~~~bash
mvn -f external-tool-demo/pom.xml clean package
~~~

Terminal cwd vẫn là `workspace`, nhưng `${project.basedir}` của module là `workspace/external-tool-demo`. Bởi vậy `workingDirectory` được chọn rõ và tool đọc đúng `inputs/label.txt`.

Nếu bạn viết shell script `cd inputs` một cách ngầm, hoặc plugin lấy `.` theo vị trí terminal mà không hiểu module root, build dễ lỗi khi chạy bằng `-f` hoặc từ IDE.

**Một module không nên phụ thuộc vào “developer luôn chạy Maven từ thư mục X”** trừ khi workflow thực sự được thiết kế/kiểm soát như vậy.

## 12. Multi-module và build song song

Trong reactor:

~~~text
root/
├── pom.xml
├── service-a/
│   ├── pom.xml
│   └── inputs/label.txt
└── service-b/
    ├── pom.xml
    └── inputs/label.txt
~~~

Với execution được kế thừa xuống cả hai module, `${project.basedir}` khác nhau theo module. Điều này có thể tốt nếu mỗi module có tool và output riêng, nhưng sai nếu tool chỉ tồn tại ở root.

Cần trả lời:

- Execution chạy ở **parent**, **child**, hay mỗi module?
- Tool executable/script nằm ở module hay root?
- Có cần `inherited=false` ở một execution chỉ dành cho parent?
- Mỗi module có output directory riêng không?
- Có shared file/native cache/licensing resource cần serializing không?
- Reactor `-T` có thể làm hai child processes chạy đồng thời không?

Mặc dù Exec Plugin có thể hỗ trợ parallel Maven builds, **external executable và các file nó ghi không đương nhiên thread-safe**.

Tránh để hai module cùng ghi một hardcoded path như `/tmp/generated.properties`. Dùng `${project.build.directory}` của từng module hoặc một mô hình output có khóa/phân vùng rõ ràng.

## 13. Không gọi shell trừ khi cần

Một cấu hình an toàn, dễ kiểm chứng:

~~~xml
<executable>java</executable>
<arguments>
    <argument>tools/BuildInfoGenerator.java</argument>
    <argument>inputs/label.txt</argument>
    <argument>target/generated-resources</argument>
</arguments>
~~~

Mỗi argument là một đơn vị riêng. Không cần nối toàn bộ câu lệnh thành `sh -c` hay `cmd /c`.

Nếu dùng shell:

~~~text
sh -c "tool --input $USER_INPUT | tee generated.log"
~~~

thì có thêm những vấn đề:

- Shell khác trên Windows, Linux, macOS.
- Escaping, quoting và ký tự đặc biệt khác nhau.
- Input từ người dùng có thể dẫn đến shell injection nếu nối không an toàn.
- Pipeline có thể không trả status của tất cả command; cần hiểu `pipefail`/exit policy tương ứng.
- `cd` trong shell con không thay đổi cwd của Maven process.
- Script wrapper tạo nhiều process con khiến timeout/cleanup khó hơn.

Một script version-controlled có thể phù hợp khi tool thật sự cần shell semantics, nhưng nên có contract rõ về input/output và exit codes. Không dùng shell chỉ để “cho tiện ghép argument”.

## 14. Output resource và output Java source không giống nhau

**Generated resource** của demo:

~~~text
target/generated-resources/build-info.properties
~~~

được `maven-resources-plugin` copy vào `target/classes` nhờ `<build><resources>`. Không cần compiler biết resource như một Java source root.

**Generated Java source**:

~~~text
target/generated-sources/my-generator/com/example/Generated.java
~~~

cần được tạo trước compile và được compiler nhận như source root. Thường dùng generator plugin có hỗ trợ source roots hoặc `build-helper-maven-plugin:add-source`. **Không nên chỉ thêm generated Java directory vào `<resources>`**, bởi như vậy file `.java` sẽ được copy như resource chứ không nhất thiết được compile.

Nếu tool cần đọc các class của project đã compile, không thể tự nhiên bind ở generate-sources rồi kỳ vọng `target/classes` đã có; phải tách producer/consumer, module hoặc phase thích hợp.

Nếu tool chỉ kiểm tra chất lượng artifact đã package, `verify` có thể phù hợp hơn `generate-resources`. Luôn chọn phase theo **dữ liệu cần có trước và dữ liệu tool tạo ra sau**.

## 15. Stale output và clean build

Một ví dụ sai dễ bỏ qua:

1. Generator chạy một lần, tạo file `target/generated-resources/build-info.properties`.
2. Sau đó developer tắt generator hoặc plugin skip goal.
3. Maven không clean và vẫn có file cũ.
4. Resources Plugin copy file cũ vào JAR.
5. Build xanh nhưng artifact không phản ánh inputs hiện hành.

Để phát hiện, chạy:

~~~bash
mvn -B clean package
~~~

Sau đó kiểm tra:

~~~text
target/generated-resources/build-info.properties
target/classes/build-info.properties
target/external-tool-demo-1.0.0.jar
~~~

Không commit file build từ `target/` như một cách workaround nếu có thể tái sinh nó theo build. Đặt output dưới `${project.build.directory}` giúp Maven Clean quản lý vòng đời output.

Một generator tốt nên ghi output **deterministic** và trả nonzero khi output không tạo được. Một test đọc generated resource như AppTest còn giúp phát hiện trường hợp tool trả 0 nhưng không tạo file.

## 16. Environment portability: Windows, Linux và CI

Những khác biệt có thể xảy ra:

| Yếu tố | Ví dụ khác biệt | Cách giảm rủi ro |
| --- | --- | --- |
| Executable name | `java` / `java.exe`, native tool extensions | Pin tool path/versions, thử trên OS mục tiêu |
| Path separator | `/`, `\` | Dùng Maven/Java Path APIs; tránh string concat thủ công |
| PATH | Tool phiên bản khác hoặc không tồn tại | Kiểm tra executable resolution |
| Shell | Bash, PowerShell, cmd.exe | Truyền `<arguments>` thay vì shell string khi có thể |
| Encoding | Locale mặc định khác | Đọc/ghi file UTF-8 tường minh |
| Locale | Decimal/Date format khác | Dùng locale cố định hoặc format invariant |
| Timezone | Giờ khác nhau | Không ghi timestamp ngẫu nhiên vào artifact |
| Permissions | File/script không executable | Kiểm tra ACL/chmod phù hợp |
| Filesystem | Case sensitivity, locking | Tránh hardcode case/caching sai |
| CI environment | Credentials/proxies/temporary paths | Least privilege và input validation |
| Multi-module | Basedir khác ở từng module | Dùng `${project.basedir}` đúng phạm vi |

Maven properties như `${project.basedir}` và `${project.build.directory}` giúp đồng bộ layout giữa môi trường. Chúng không thay thế việc tool có hỗ trợ OS tương ứng hay không.

### Maven và child JVM không chắc giống nhau

Trong ví dụ, `mvn -version` có thể hiển thị một JDK, còn `<executable>java</executable>` tìm Java khác trên PATH. Nếu CI cần Java 17 chính xác, phải kiểm soát toolchain/PATH, không suy ra từ `maven.compiler.release=17` rằng external generator chắc chắn dùng Java 17.

## 17. Exit code và output validation cần kết hợp

| Tình huống | Child status | File output | Build nên làm gì? |
| --- | --- | --- | --- |
| Generator hợp lệ | 0 | Có, đúng nội dung | Tiếp tục |
| Mode sai | 7 | Không nên có file hợp lệ mới | Fail ngay |
| Input thiếu | 9 theo demo | Không tạo mới | Fail ngay |
| Tool trả 0 nhưng không tạo output | 0 | Thiếu | Validation/test phải fail |
| Tool bị timeout | Không có completion bình thường | Có thể dở dang | Fail, không đóng gói |
| Executable không tìm thấy | Không spawn được | Không có | Fail do launch error |
| Async generator chưa xong | Chưa có exit status cuối | Output chưa hoàn thành | Không chạy consumer trước |

**Exit code không bảo đảm dữ liệu output hợp lệ; output tồn tại không bảo đảm được tạo từ input mới; checksum/output validation không thay thế quyền tin cậy vào executable.** Thiết kế build nghiêm túc cần cả ba lớp kiểm soát.

Với tool có side effects như deploy hoặc migration database, không tự chạy lại trong CI chỉ vì retry thuận tiện. Phải có idempotency, sandbox và quyền triển khai cụ thể.

## 18. Các vấn đề bảo mật khi thực thi tool ngoài

External executable là **code chạy với quyền của process build**. Nó có thể đọc workspace, environment variables và secrets mà runner có quyền truy cập.

Các thực hành cần có:

1. Pin phiên bản executable và xác minh nguồn download.
2. Không chạy script không tin cậy với quyền publish artifact.
3. Dùng permission tối thiểu cho build worker.
4. Không nhúng passwords/tokens vào POM được commit.
5. Không ghi credentials vào `build-info.properties` hoặc JAR.
6. Không đưa user input vào `sh -c` hoặc `cmd /c` bằng chuỗi nối không escape.
7. Không log toàn bộ environment của CI.
8. Không mở network access rộng cho generator nếu không cần.
9. Kiểm tra hashes/signatures/provenance theo repository policy.
10. Khi cần runtime config thay đổi theo môi trường, ưu tiên inject lúc chạy thay vì rebuild JAR với secrets.

Demo chỉ đọc `APP_MODE` và label ASCII, không cần secret hay network. Đó là lựa chọn có chủ đích để tập trung vào working directory/env/exit code.

## 19. Các lỗi thường gặp và cách sửa

| Triệu chứng | Nguyên nhân thường gặp | Cách kiểm tra/sửa |
| --- | --- | --- |
| Tool báo không thấy input | cwd khác module root | Đặt workingDirectory, kiểm tra path |
| Maven từ IDE chạy được, `-f` fail | Phụ thuộc terminal cwd | Dùng project.basedir và absolute arguments |
| Output nằm ngoài `target/` | Tool ghi vào `.` | Truyền build directory tường minh |
| Không thấy resource trong JAR | Thiếu `<resources>` hoặc phase sai | Đặt generated-resources vào resource roots |
| `mvn generate-resources` xong mà App không đọc được | Chưa process-resources | Chạy phase tiếp theo hoặc package |
| Tool nhận mode mặc định dù có `-D` | Chưa map Maven property vào child env | Cấu hình environmentVariables |
| Child Java dùng JDK sai | PATH khác với Maven JVM | Kiểm tra Java launcher được gọi |
| Tool timeout | Bị treo hoặc threshold quá nhỏ | Debug root cause, chọn timeout có căn cứ |
| Tool báo lỗi mà Maven xanh | successCodes quá rộng hoặc async true | Chỉ allow-list success thật, dùng sync |
| Tool trả 0 nhưng output thiếu | Tool contract chưa tốt, không có QA file | Thêm validation/test resource |
| Hai module ghi cùng một file | Hardcoded shared output path | Dùng project.build.directory mỗi module |
| Lỗi shell trên Windows | Script POSIX-only | Dùng executable cross-platform hoặc script OS-specific |
| Arguments bị gộp sai | Dùng commandlineArgs/quotes không đúng | Dùng từng `<argument>` |
| Lệnh `mvn compile tool:goal` chạy lặp | Gọi cả phase và goal trực tiếp | Chỉ gọi phase đủ dùng |
| File cũ che lỗi generator | Không clean | Dùng clean build để xác nhận |
| Log thiếu child output | outputFile/inheritIo/logger routing | Kiểm tra config ghi log |
| Generator ghi secrets vào JAR | Dùng environment values không kiểm soát | Chỉ cho phép generated fields không nhạy cảm |
| CI vẫn dùng artifact cũ khi build fail | Pipeline không dừng/không clean | Dừng pipeline trên Maven nonzero, kiểm tra artifact provenance |
| Maven báo child exit 7, CI thấy Maven exit 1 | Hai tầng status khác nhau | CI theo Maven status, log theo child code |

## 20. Quy trình debug ngắn, có thể lặp lại

**Bước 1:** xác định đúng tool và JDK:

~~~bash
mvn -version
java -version
~~~

**Bước 2:** xem POM/config hiệu lực:

~~~bash
mvn help:effective-pom
mvn help:active-profiles
~~~

Tìm Exec Plugin, execution id, phase, executable, workingDirectory, environmentVariables, arguments, timeout, successCodes và các profile đang active.

**Bước 3:** xác minh producer riêng:

~~~bash
mvn -B clean generate-resources
~~~

Với demo, phải có file `target/generated-resources/build-info.properties`. Không mong `target/classes` có resource ngay tại phase này.

**Bước 4:** chạy đầy đủ producer→consumer:

~~~bash
mvn -B clean package
~~~

Kiểm tra file ở `target/generated-resources`, `target/classes`, và file bên trong JAR. Đọc test reports nếu Surefire fail.

**Bước 5:** thử một lỗi có chủ đích trên bản demo:

~~~bash
mvn -B -Dresource.mode=invalid.mode clean package
~~~

Phải thấy stderr của generator và Maven build failure. **Không cho code 7 vào successCodes để test qua**.

**Bước 6:** thử khi Maven được gọi từ thư mục khác:

~~~bash
mvn -f external-tool-demo/pom.xml clean package
~~~

Lệnh này phù hợp khi đứng ở thư mục cha của project; kiểm tra một child có còn đọc đúng `inputs/label.txt` hay không.

**Bước 7:** không chia sẻ logs có secrets. Nếu lỗi xảy ra trong CI, so tool versions, PATH, Maven properties, permissions, environment allow-list và output path; tránh thay đổi nhiều biến cùng lúc.

## 21. Bài tập tự kiểm tra

**Câu 1.** Vì sao dùng `${project.basedir}` cho workingDirectory đáng tin hơn dựa vào nơi gõ `mvn`?

**Đáp:** `project.basedir` chỉ module có POM, vẫn đúng khi IDE, `mvn -f` hoặc reactor dùng terminal cwd khác.

**Câu 2.** Có thể đọc Maven CLI property `-Dresource.mode=ci` trong child bằng `System.getenv("APP_MODE")` ngay khi chưa map không?

**Đáp:** Không. Cần `<environmentVariables><APP_MODE>${resource.mode}</APP_MODE></environmentVariables>` hoặc một cơ chế truyền tường minh khác.

**Câu 3.** `exec:java` và `exec:exec` đều chắc chắn tạo Java child OS process?

**Đáp:** Không. `exec:exec` chạy process riêng; `exec:java` chạy trong Maven JVM.

**Câu 4.** Tool trả code 7 trong khi chỉ code 0 được phép. Maven có tiếp tục package không?

**Đáp:** Không theo cấu hình chuẩn; Exec Plugin fail goal và Maven dừng lifecycle.

**Câu 5.** Maven command exit status có chắc bằng exit code của child?

**Đáp:** Không. Maven trả status của lệnh Maven, thường nonzero khi goal fail; đọc log để thấy child code.

**Câu 6.** Vì sao `async=true` không phù hợp cho generator mà phase sau cần file?

**Đáp:** Maven có thể đi tiếp trước khi generator tạo xong file, gây race hoặc resource thiếu.

**Câu 7.** `timeout=30000` là bao lâu?

**Đáp:** 30 giây, bởi đơn vị là milliseconds.

**Câu 8.** `mvn generate-resources` đã tạo file mà classpath vẫn không có resource. Có sai không?

**Đáp:** Chưa chắc. `process-resources` chưa chạy để copy resource vào `target/classes`.

**Câu 9.** Generator sinh `.java` thì khai báo file đó trong `<resources>` là đủ để compile?

**Đáp:** Không. Generated Java cần được compiler biết như source root; thông thường bind generator ở `generate-sources` và đăng ký source root thích hợp.

**Câu 10.** Cùng POM nhưng CI và laptop có JAR khác nhau, do đâu?

**Đáp:** Tool/executable version, environment, locale, timezone, input files, profiles hoặc snapshot dependencies có thể khác. Cần chốt những inputs đó.

**Câu 11.** Có nên cho `successCodes` mọi nonzero để tránh build đỏ không?

**Đáp:** Không. Chỉ thêm codes mà tài liệu công cụ xác nhận là thành công hợp lệ.

**Câu 12.** Đưa token thật vào `<environmentVariables>` commit trong POM có an toàn không?

**Đáp:** Không. Dùng secret management của CI, tối thiểu quyền, tránh log và không embed token vào artifact.

## 22. Checklist áp dụng vào CI

1. Chọn plugin chuyên dụng khi thích hợp, hoặc `exec:exec` khi cần chạy CLI tổng quát.
2. Pin version của Exec Plugin và executable.
3. Cấu hình workingDirectory xác định, thường `${project.basedir}`.
4. Truyền input/output paths rõ ràng; output vào `${project.build.directory}` khi có thể.
5. Truyền từng argument riêng thay vì shell string không kiểm soát.
6. Chỉ cung cấp child environment cần thiết; không lộ secrets.
7. Map Maven properties thành environment/args một cách tường minh.
8. Xác định exit codes được phép; với generator bắt buộc thường chỉ 0.
9. Đặt timeout phù hợp, chặn build khi timeout.
10. Để `async=false` khi phase sau tiêu thụ output.
11. Gắn generator vào phase producer chính xác.
12. Đăng ký generated resource/source roots để consumer tìm được.
13. Kiểm tra output tồn tại, đúng nội dung, không stale.
14. Test build sạch với `mvn clean package`.
15. Test invocation qua `mvn -f` và trên OS/CI mục tiêu.
16. Kiểm soát multi-module inheritance và output paths khi build song song.
17. Không nhân đôi default resource/compile executions không cần thiết.
18. Không nhúng runtime secrets trong generated files.
19. Log đủ stdout/stderr và child exit status để debug nhưng có redaction.
20. Bảo đảm tool failure làm pipeline dừng, không publish artifact cũ/sai.

## Tài liệu tham khảo chính thức

- [MojoHaus Exec Maven Plugin — Introduction](https://www.mojohaus.org/exec-maven-plugin/)
- [MojoHaus Exec Maven Plugin — exec:exec parameters](https://www.mojohaus.org/exec-maven-plugin/exec-mojo.html)
- [MojoHaus Exec Maven Plugin — Usage](https://www.mojohaus.org/exec-maven-plugin/usage.html)
- [MojoHaus Exec Maven Plugin — exec:java](https://www.mojohaus.org/exec-maven-plugin/java-mojo.html)
- [MojoHaus Exec Maven Plugin — Running Java programs with exec:exec](https://www.mojohaus.org/exec-maven-plugin/examples/example-exec-for-java-programs.html)
- [Apache Maven — Introduction to the Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html)
- [Apache Maven — Guide to Configuring Plugins](https://maven.apache.org/guides/mini/guide-configuring-plugins.html)
- [Apache Maven Resources Plugin — resources goal](https://maven.apache.org/plugins/maven-resources-plugin/resources-mojo.html)
- [Java 17 — Java Launcher](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html)

