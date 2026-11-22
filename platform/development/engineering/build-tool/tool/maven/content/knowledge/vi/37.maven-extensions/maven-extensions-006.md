# Thiết kế goal Maven có đầu vào, đầu ra và thông báo lỗi rõ ràng

## 1. Mục tiêu học tập và bài toán

Một Maven plugin gồm một hoặc nhiều **goal**, mỗi goal được thực thi bởi một **Mojo**. Viết một phương thức `execute()` chạy được chỉ là bước đầu. Một goal có thể trở nên khó dùng nếu người gọi không biết:

- Goal **nhận dữ liệu gì**, lấy từ POM hay tham số `-D` nào, mặc định ra sao?
- Nó **tạo dữ liệu gì**, ghi ở đâu, định dạng nào, có ghi đè không?
- Khi thiếu đầu vào, dữ liệu không hợp lệ hoặc gặp lỗi I/O, goal **báo lỗi thế nào** và người dùng cần sửa gì?
- Nó có an toàn khi lặp lại, khi chạy nhiều module, khi dùng `mvn -T`, trong CI hay không?
- Một lần chạy thành công có cách **kiểm chứng được** ngoài một dòng “BUILD SUCCESS” không?

Mục tiêu là xây một hợp đồng rõ ràng cho goal, có ví dụ Java 17 và Maven 3 **đầy đủ, tự tạo được plugin JAR và gọi goal từ một project consumer riêng**. Goal ví dụ tên `summarize`, đọc file văn bản UTF-8, đếm tổng số dòng và số dòng không trống, rồi tạo report deterministic trong thư mục `target`.

Đầu vào ví dụ:

~~~text
alpha

beta
~~~

Đầu ra mong đợi:

~~~text
format=1
totalLines=3
nonBlankLines=2
~~~

Kết quả được tạo từ ba dòng: `alpha`, một dòng rỗng, `beta`. Dấu xuống dòng cuối file không làm xuất hiện một dòng thứ tư khi đọc bằng `BufferedReader.readLine()`.

**Phiên bản minh họa:** Maven 3.9.x, JDK 17+, Maven Plugin Tools `3.16.0`. Bài dùng những API Maven 3 đã được tài liệu hóa; Maven 4 có API/compatibility khác, không đánh đồng hai thế hệ. Các version plugin trong ví dụ là bản pin để dễ tái tạo, không có lời khẳng định luôn mới nhất về sau.

## 2. Goal, plugin, Mojo và lifecycle có quan hệ gì?

| Khái niệm | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| Maven plugin | Artifact Java có `packaging=maven-plugin`, chứa một hoặc nhiều goals. | `org.example.tools:summary-maven-plugin:1.0.0`. |
| Mojo | Java class hiện thực hợp đồng của một goal, thường kế thừa `AbstractMojo`. | `SummarizeMojo`. |
| Goal name | Tên do `@Mojo(name="...")` khai báo. | `summarize`. |
| Parameter | Dữ liệu Maven inject vào field/setter `@Parameter`. | `inputFile`, `outputFile`, `maxLines`, `skip`. |
| Goal invocation | Chạy trực tiếp một goal từ CLI. | `mvn group:artifact:version:summarize`. |
| Lifecycle phase | Giai đoạn như `generate-resources`, `compile`, `verify`. | Có thể bind goal trong `<executions>`. |
| Plugin descriptor | `META-INF/maven/plugin.xml` mô tả goals/parameters cho Maven. | Được Maven Plugin Plugin sinh. |
| Plugin help | Goal `help` tạo từ `helpmojo` để người dùng xem tham số. | `...:help -Ddetail=true`. |

Đừng gọi một Java method thường là “Maven goal” chỉ vì tên method là `execute`. Maven cần **plugin descriptor** đóng gói trong plugin artifact để biết class, goal name, parameters và các yêu cầu thực thi.

Tên plugin không thuộc Apache Maven nên chọn quy ước `<prefix>-maven-plugin`, ví dụ `summary-maven-plugin`. Quy ước `maven-<name>-plugin` được dành cho plugin chính thức Apache Maven và không nên dùng cho plugin bên thứ ba.

## 3. Hợp đồng đầu vào: cụ thể thay vì “có nhiều tùy chọn”

Goal tốt nên công bố tối thiểu: **tên tham số, kiểu dữ liệu, cách cấu hình, mặc định, required hay optional, ràng buộc, quyền tác động**.

Thiết kế của goal `summarize`:

| Parameter | Java type | CLI property | Default | Ràng buộc |
| --- | --- | --- | --- | --- |
| `inputFile` | `java.io.File` | `summary.inputFile` | `data/items.txt` trong basedir project | Phải là file thường, đọc được dưới UTF-8. |
| `outputFile` | `java.io.File` | `summary.outputFile` | `target/summary/summary.txt` trong project | Không trùng input, không được là thư mục. |
| `maxLines` | `int` | `summary.maxLines` | `1000` | Ít nhất 1, chặn input quá nhiều dòng. |
| `skip` | `boolean` | `summary.skip` | `false` | Nếu true, không đọc/ghi đầu vào/đầu ra. |

Mặc định về file phải rõ **path tương đối với cái gì**. Trong plugin mẫu, giá trị annotation dùng expressions `${project.basedir}` và `${project.build.directory}`. Vì thế consumer tự chạy với đúng project root/output directory của mình, không phụ thuộc cwd mơ hồ.

`required=true` trong `@Parameter` giúp Maven phát hiện cấu hình thiếu ở tầng injection; **không thay validation nghiệp vụ**: file có thể không tồn tại, đường dẫn là thư mục, maxLines không hợp lệ hoặc output trùng input. Những trường hợp này phải được plugin kiểm tra và giải thích.

Không nên thêm quá nhiều tham số khi không cần: mỗi option tăng chi phí tài liệu, compatibility và test cases. Bốn tham số này đủ minh họa mục đích.

## 4. Hợp đồng đầu ra: filename, format và tính lặp lại

Goal tạo một file text UTF-8:

~~~text
target/summary/summary.txt
~~~

Nội dung có ba dòng dạng `key=value`, thứ tự cố định, dùng ký tự xuống dòng LF:

~~~text
format=1
totalLines=3
nonBlankLines=2
~~~

Ý nghĩa:

- `format=1`: version nhỏ cho schema report nội bộ ví dụ, giúp consumer nhận biết định dạng.
- `totalLines`: số lần `BufferedReader.readLine()` trả một dòng, bao gồm dòng trắng.
- `nonBlankLines`: số dòng mà `String.isBlank()` trả false.
- Report có newline sau dòng cuối; không có timestamp ngẫu nhiên nên cùng input sẽ có cùng report bytes.
- Lệnh thành công **ghi đè** report cũ ở đúng output path, bằng cách tạo tệp tạm rồi thay thế đích.
- Plugin **không tự attach** report thành Maven artifact. Nếu cần publish report classifier, phải có chiến lược attachment riêng, không tự suy từ file tồn tại ở `target`.

**Lưu ý quan trọng:** nếu một lần chạy sau bị lỗi hoặc `skip=true`, file output từ **lần chạy trước** vẫn có thể tồn tại. CI không được coi “file tồn tại” là bằng chứng lần chạy gần nhất thành công. Phải dựa Maven exit status, log marker và cơ chế build sạch khi cần.

## 5. Hợp đồng lỗi: phân biệt vấn đề dữ liệu với lỗi hệ thống

Maven 3 dùng hai exception thường gặp cho Mojo:

- `MojoFailureException`: dùng khi **người dùng phải sửa input/cấu hình hoặc điều kiện kiểm tra của goal không đạt**. Ví dụ `maxLines=0`, input không tồn tại, input có quá nhiều dòng.
- `MojoExecutionException`: dùng khi **goal không thể thực hiện vì trục trặc khi thực thi**, ví dụ file I/O, permissions, charset decoding, không tạo được output directory.

Cả hai đều làm Maven command **thoát không thành công**; sự khác biệt giúp người dùng/CI xác định **cần sửa POM/đầu vào** hay **điều tra môi trường/infrastructure**.

Một lỗi tốt nên có mã nhận diện ổn định và hướng sửa:

~~~text
SUMMARY_INPUT_NOT_FILE: input is not a regular file: /work/app/data/items.txt; set -Dsummary.inputFile=<path>
SUMMARY_BAD_LIMIT: maxLines must be >= 1; received 0
SUMMARY_LIMIT_EXCEEDED: input has more than 2 lines; increase -Dsummary.maxLines or reduce input
SUMMARY_READ_FAILED: cannot read UTF-8 input /work/app/data/items.txt
SUMMARY_WRITE_FAILED: cannot write output /work/app/target/summary/summary.txt
~~~

Các path trên chỉ **minh họa**; plugin in path thực khi chạy. Đừng bịa các dòng này là nguyên văn Maven log; Maven còn thêm plugin coordinates/stack trace tùy mức log.

**Không đặt credentials, nội dung file nhạy cảm hay environment secrets vào exception messages.** Nếu path nội bộ cũng nhạy cảm, cần cơ chế log/redaction của tổ chức khi chia sẻ logs.

## 6. Hai project riêng: plugin producer và project consumer

Một cấu trúc demo rõ trách nhiệm:

~~~text
maven-goal-workshop/
├── summary-maven-plugin/
│   ├── pom.xml
│   └── src/main/java/org/example/tools/SummarizeMojo.java
└── summary-consumer/
    ├── pom.xml
    └── data/items.txt
~~~

Đây là **hai project Maven độc lập**, không cần parent reactor cho bài học. Thứ tự thao tác:

1. Build/install plugin producer vào Maven local repository.
2. Chạy consumer với plugin GAV đã install.
3. Đọc file output và kiểm đúng nội dung.
4. Dùng parameter override để kiểm các ca lỗi.
5. Tùy chọn bind goal vào một lifecycle phase ở consumer.

Không gọi goal của plugin trong source project trước khi `plugin.xml`/plugin JAR được sinh và install. Không giả định plugin có sẵn trên Maven Central: `org.example.tools` và tên plugin là tọa độ demo.

## 7. Plugin producer pom.xml đầy đủ

Tạo `summary-maven-plugin/pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>org.example.tools</groupId>
    <artifactId>summary-maven-plugin</artifactId>
    <version>1.0.0</version>
    <packaging>maven-plugin</packaging>
    <name>Summary Maven Plugin Demo</name>
    <description>A file-input/file-output goal with explicit errors.</description>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <maven-plugin-tools.version>3.16.0</maven-plugin-tools.version>
        <maven-api.version>3.9.16</maven-api.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.apache.maven</groupId>
            <artifactId>maven-plugin-api</artifactId>
            <version>${maven-api.version}</version>
            <scope>provided</scope>
        </dependency>
        <dependency>
            <groupId>org.apache.maven.plugin-tools</groupId>
            <artifactId>maven-plugin-annotations</artifactId>
            <version>${maven-plugin-tools.version}</version>
            <scope>provided</scope>
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
                <artifactId>maven-plugin-plugin</artifactId>
                <version>${maven-plugin-tools.version}</version>
                <executions>
                    <execution>
                        <id>generate-help-goal</id>
                        <goals>
                            <goal>helpmojo</goal>
                        </goals>
                    </execution>
                </executions>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Các điểm chính:

- `packaging=maven-plugin` kích hoạt lifecycle/descriptor handling dành cho Maven plugin, không phải một JAR ứng dụng thông thường.
- `maven-plugin-api` cung cấp `AbstractMojo`, `MojoExecutionException` và `MojoFailureException`. Scope `provided` nghĩa là Maven runtime cung cấp API; không đóng kèm bản thứ hai vào plugin JAR.
- `maven-plugin-annotations` cung cấp `@Mojo` và `@Parameter` để Plugin Tools tạo descriptor. Scope `provided` là thích hợp cho annotations.
- `maven-plugin-plugin` `3.16.0` sinh `META-INF/maven/plugin.xml`; `helpmojo` tạo goal help để liệt kê parameters.
- Maven Compiler Plugin biên dịch source với `release=17`.
- `maven-api.version=3.9.16` là mốc API Maven 3 đang dùng trong demo; khi phân phối thật, xác định rõ **minimum Maven version** qua compatibility tests/metadata, không tự cam kết chạy được với mọi Maven 3 cũ.
- Version `1.0.0` là bản cài local phục vụ học; không public namespace `org.example.tools` thật khi chưa có quyền sử dụng.

Không chép pattern `maven-summary-plugin` vì cú pháp tên `maven-<name>-plugin` dành cho plugin do dự án Apache Maven duy trì.

## 8. @Mojo định nghĩa goal, không chỉ là tên class

Plugin sẽ có class:

~~~java
@Mojo(name = "summarize", requiresProject = true, threadSafe = false)
public final class SummarizeMojo extends AbstractMojo {
    // parameters and execute(...)
}
~~~

Đây là **mảnh để giải thích annotations**, code đầy đủ ở mục sau.

- `name="summarize"` tạo goal `summarize` trong descriptor.
- `requiresProject=true` yêu cầu Maven project context vì defaults phụ thuộc `project.basedir` và `project.build.directory`.
- `threadSafe=false` là lựa chọn trung thực trong bản demo: nếu consumer override nhiều modules cùng ghi một output path, có thể race/overwrite. Chỉ đổi sang true sau khi bảo đảm output isolation, shared state và concurrency tests.
- Không khai `defaultPhase` trong demo để goal **chỉ chạy khi gọi trực tiếp hoặc được consumer bind**. Một `defaultPhase` trong descriptor **không tự làm goal chạy ở mọi project**; consumer vẫn cần lifecycle binding hay cơ chế build tương ứng.
- Không yêu cầu dependency resolution vì goal chỉ đọc một file text và không cần app classpath.

Maven Plugin Tools annotations được xử lý khi build plugin, không phải Java reflection trực tiếp tự tìm class mỗi lần người dùng chạy `mvn`.

## 9. SummarizeMojo.java — source Java 17 hoàn chỉnh

Tạo `summary-maven-plugin/src/main/java/org/example/tools/SummarizeMojo.java`:

~~~java
package org.example.tools;

import java.io.BufferedReader;
import java.io.File;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.AtomicMoveNotSupportedException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;

import org.apache.maven.plugin.AbstractMojo;
import org.apache.maven.plugin.MojoExecutionException;
import org.apache.maven.plugin.MojoFailureException;
import org.apache.maven.plugins.annotations.Mojo;
import org.apache.maven.plugins.annotations.Parameter;

/**
 * Counts lines in a UTF-8 file and writes a stable text report.
 */
@Mojo(name = "summarize", requiresProject = true, threadSafe = false)
public final class SummarizeMojo extends AbstractMojo {

    /**
     * Input UTF-8 text file. Defaults to the project's data/items.txt.
     */
    @Parameter(
        property = "summary.inputFile",
        defaultValue = "${project.basedir}/data/items.txt",
        required = true
    )
    private File inputFile;

    /**
     * Output text file. Defaults to target/summary/summary.txt.
     */
    @Parameter(
        property = "summary.outputFile",
        defaultValue = "${project.build.directory}/summary/summary.txt",
        required = true
    )
    private File outputFile;

    /**
     * Maximum permitted number of input lines.
     */
    @Parameter(property = "summary.maxLines", defaultValue = "1000")
    private int maxLines;

    /**
     * Skip reading input and writing output.
     */
    @Parameter(property = "summary.skip", defaultValue = "false")
    private boolean skip;

    @Override
    public void execute()
            throws MojoExecutionException, MojoFailureException {

        if (skip) {
            getLog().info("SUMMARY_SKIPPED: summary.skip=true; no report written");
            return;
        }

        if (inputFile == null) {
            throw new MojoFailureException(
                "SUMMARY_INPUT_REQUIRED: configure inputFile or -Dsummary.inputFile");
        }
        if (outputFile == null) {
            throw new MojoFailureException(
                "SUMMARY_OUTPUT_REQUIRED: configure outputFile or -Dsummary.outputFile");
        }
        if (maxLines < 1) {
            throw new MojoFailureException(
                "SUMMARY_BAD_LIMIT: maxLines must be >= 1; received " + maxLines);
        }

        Path input = inputFile.toPath().toAbsolutePath().normalize();
        Path output = outputFile.toPath().toAbsolutePath().normalize();

        if (input.equals(output)) {
            throw new MojoFailureException(
                "SUMMARY_SAME_PATH: input and output must differ: " + input);
        }
        if (!Files.isRegularFile(input)) {
            throw new MojoFailureException(
                "SUMMARY_INPUT_NOT_FILE: input is not a regular file: " + input
                + "; set -Dsummary.inputFile=<path>");
        }
        if (Files.exists(output) && Files.isDirectory(output)) {
            throw new MojoFailureException(
                "SUMMARY_OUTPUT_IS_DIRECTORY: choose a file: " + output);
        }

        long totalLines = 0;
        long nonBlankLines = 0;

        try (BufferedReader reader =
                Files.newBufferedReader(input, StandardCharsets.UTF_8)) {
            String line;
            while ((line = reader.readLine()) != null) {
                totalLines++;
                if (totalLines > maxLines) {
                    throw new MojoFailureException(
                        "SUMMARY_LIMIT_EXCEEDED: input has more than "
                        + maxLines + " lines; increase -Dsummary.maxLines"
                        + " or reduce input");
                }
                if (!line.isBlank()) {
                    nonBlankLines++;
                }
            }
        } catch (IOException e) {
            throw new MojoExecutionException(
                "SUMMARY_READ_FAILED: cannot read UTF-8 input " + input
                + "; check file permissions and encoding", e);
        }

        String report = "format=1\n"
                + "totalLines=" + totalLines + "\n"
                + "nonBlankLines=" + nonBlankLines + "\n";

        Path temporary = null;
        try {
            Files.createDirectories(output.getParent());
            temporary = Files.createTempFile(
                output.getParent(), ".summary-", ".tmp");
            Files.writeString(temporary, report, StandardCharsets.UTF_8);

            try {
                Files.move(temporary, output,
                    StandardCopyOption.ATOMIC_MOVE,
                    StandardCopyOption.REPLACE_EXISTING);
            } catch (AtomicMoveNotSupportedException unsupported) {
                Files.move(temporary, output,
                    StandardCopyOption.REPLACE_EXISTING);
            }

            getLog().info(
                "SUMMARY_WRITTEN: totalLines=" + totalLines
                + ", nonBlankLines=" + nonBlankLines
                + ", output=" + output);
        } catch (IOException e) {
            throw new MojoExecutionException(
                "SUMMARY_WRITE_FAILED: cannot write output " + output
                + "; check directory permissions and free space", e);
        } finally {
            if (temporary != null) {
                try {
                    Files.deleteIfExists(temporary);
                } catch (IOException cleanup) {
                    getLog().warn(
                        "SUMMARY_TEMP_CLEANUP_FAILED: " + temporary
                        + "; check temporary directory cleanup");
                }
            }
        }
    }
}
~~~

**Source đầy đủ** dùng đúng `package org.example.tools` và path Java file tương ứng. Không cần thư viện ngoài JDK 17 và Maven Plugin API. Không copy một snippet đóng vai giả lập `execute()` mà thiếu imports/class/POM.

### Vì sao Java code được tổ chức như vậy?

1. **Không ghi output trước khi validate:** thiếu input, limit sai, cùng path, output là directory đều fail trước write.
2. **UTF-8 rõ ràng:** `Files.newBufferedReader(..., UTF_8)` không phụ thuộc default charset của runner.
3. **Bounded by line count:** quá `maxLines` ném `MojoFailureException` và không ghi report mới; phù hợp demo nhưng chưa giới hạn byte size hoặc độ dài mỗi dòng trong các file độc hại.
4. **I/O exception có cause:** `new MojoExecutionException(message, e)` giữ stack trace nguyên nhân cho debug khi cần.
5. **Atomic write khi filesystem hỗ trợ:** file tạm cùng output directory, sau đó move sang đích; nếu filesystem không hỗ trợ `ATOMIC_MOVE`, fallback sang `REPLACE_EXISTING`. Fallback **không còn bảo đảm atomic**, phải ghi rõ.
6. **Cleanup:** thử dọn temp khi I/O có lỗi; nếu cleanup fail sẽ có warning riêng.
7. **Idempotent theo input:** cùng input + maxLines + plugin version dẫn tới cùng report bytes. Goal không ghi timestamp ngẫu nhiên.
8. **Không log nội dung file hoặc credentials**, chỉ tổng số dòng và đường dẫn output. Đường dẫn vẫn có thể là metadata nội bộ; redact khi chia sẻ log ra ngoài.

**Giới hạn của ví dụ:** `Files.isRegularFile` theo symlinks và kiểm đường dẫn không đồng nghĩa sandbox filesystem; input có một dòng rất lớn vẫn có thể tiêu tốn bộ nhớ trong `readLine()`. Với dữ liệu không tin cậy, cần thêm maximum byte size, độ dài dòng, path allowlist và I/O security policy.

## 10. Tạo file dữ liệu của consumer

Tạo file `summary-consumer/data/items.txt` bằng UTF-8 với **đúng ba dòng** (line 1 `alpha`, line 2 rỗng, line 3 `beta`):

~~~text
alpha

beta
~~~

Khi dùng Windows Editor, lưu UTF-8 không có ký tự BOM nếu muốn giữ nội dung tối giản. Cả CRLF và LF đều được `BufferedReader.readLine()` nhận thành ba dòng theo ví dụ; kết quả output dùng LF cố định do Java code tạo.

Nếu bạn copy markdown fence vào file, **không** chép dấu `~~~text`/`~~~`; chỉ chép nội dung bên trong.

## 11. consumer pom.xml đầy đủ

Tạo `summary-consumer/pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>org.example.demo</groupId>
    <artifactId>summary-consumer</artifactId>
    <version>1.0.0</version>
    <packaging>pom</packaging>
    <name>Summary Goal Consumer Demo</name>

    <build>
        <plugins>
            <plugin>
                <groupId>org.example.tools</groupId>
                <artifactId>summary-maven-plugin</artifactId>
                <version>1.0.0</version>
                <configuration>
                    <inputFile>${project.basedir}/data/items.txt</inputFile>
                    <outputFile>${project.build.directory}/summary/summary.txt</outputFile>
                    <maxLines>1000</maxLines>
                    <skip>false</skip>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**Tại sao consumer `packaging=pom`?** Goal chỉ đọc/ghi file, không cần biên dịch một app. Dùng POM project giúp có `project.basedir` và `project.build.directory` mà không bắt consumer tạo Java code. Đặt plugin trong `<build><plugins>` giúp pin version và khai báo parameters. `<pluginManagement>` riêng **không làm plugin tự chạy**; với cấu hình này, goal chạy khi được gọi trực tiếp, hoặc nếu sau đó được bind vào phase.

Nếu consumer là JAR project thật, cùng plugin cấu hình vẫn dùng được; report không trở thành dependency runtime.

## 12. Build, install plugin trước; gọi goal từ consumer sau

Từ thư mục `maven-goal-workshop`:

~~~bash
mvn -B -ntp -f summary-maven-plugin/pom.xml clean install
~~~

Với project `packaging=maven-plugin`, Maven Plugin Plugin tạo descriptor và plugin JAR, sau đó install GAV vào local repository. Kiểm file trong producer:

~~~text
summary-maven-plugin/target/summary-maven-plugin-1.0.0.jar
~~~

Descriptor bên trong JAR phải có entry:

~~~text
META-INF/maven/plugin.xml
~~~

Có thể kiểm bằng JDK tool:

~~~bash
jar tf summary-maven-plugin/target/summary-maven-plugin-1.0.0.jar
~~~

Từ cùng thư mục root, gọi goal bằng tọa độ đầy đủ trên consumer:

~~~bash
mvn -B -ntp -f summary-consumer/pom.xml \
  org.example.tools:summary-maven-plugin:1.0.0:summarize
~~~

Lệnh trên dùng cách nối dòng của Bash/Linux/macOS. Trên Windows PowerShell có thể gõ một dòng:

~~~powershell
mvn -B -ntp -f summary-consumer/pom.xml org.example.tools:summary-maven-plugin:1.0.0:summarize
~~~

**Không cần cấu hình `settings.xml/pluginGroups` khi dùng full GAV**, và cũng không cần upload plugin lên remote. Local install đủ cho demo trên cùng máy. Nếu consumer chạy trên runner CI khác, plugin phải được publish tới repository mà runner đó có quyền đọc hoặc được build trong cùng reactor theo đúng quy trình.

### Output chính xác

Sau khi goal success, file:

~~~text
summary-consumer/target/summary/summary.txt
~~~

phải có nội dung:

~~~text
format=1
totalLines=3
nonBlankLines=2
~~~

Plugin viết thêm **một dòng log của chính nó**, dạng:

~~~text
SUMMARY_WRITTEN: totalLines=3, nonBlankLines=2, output=<absolute-path>
~~~

`<absolute-path>` đại diện cho đường dẫn thật theo máy, **không phải stdout cố định**. Không mô tả toàn bộ Maven console log là chính xác như trên: Maven thêm log prefix/plugin execution, timestamps và các dòng khác tùy môi trường.

## 13. Cách người dùng truyền tham số qua -D

Trong `@Parameter(property = "summary.maxLines")`, `property` cho phép CLI truyền:

~~~bash
mvn -B -ntp -f summary-consumer/pom.xml \
  org.example.tools:summary-maven-plugin:1.0.0:summarize \
  -Dsummary.maxLines=20
~~~

Với file ba dòng, report vẫn là:

~~~text
format=1
totalLines=3
nonBlankLines=2
~~~

Khi cấu hình plugin có `<maxLines>1000</maxLines>` và CLI có `-Dsummary.maxLines=20`, việc dùng property override tùy cơ chế parameter expression/configuration injection. **Để phép thử CLI override rõ ràng**, trong POM consumer nên **không hard-code cùng parameter ở `<configuration>`** khi muốn điều khiển bằng `-D`, hoặc đặt expression:

~~~xml
<maxLines>${summary.maxLines}</maxLines>
~~~

và định nghĩa property mặc định tương ứng trong project POM. Một cách khác là bỏ `<maxLines>` khỏi consumer POM để annotation `defaultValue`/`property` điều khiển giá trị. Ví dụ mục 11 tập trung minh họa POM explicit; trong thực tế hãy chọn **một nguồn cấu hình chủ đạo**, đừng tạo tranh chấp giữa literal configuration và CLI property.

**Quan trọng:** giá trị `maxLines` của ví dụ consumer POM đang cố định là 1000. Để thử trường hợp lỗi và các overrides đáng tin cậy mà không dựa vào thứ tự ưu tiên, hãy **xóa duy nhất thẻ `<maxLines>1000</maxLines>` trong consumer POM** rồi chạy các lệnh `-Dsummary.maxLines=...`. Tham số vẫn có default 1000 từ annotation.

Tương tự, các tham số `inputFile`/`outputFile` trong POM đang được set bằng expressions. Nếu cần override từ CLI một cách minh bạch, có thể bỏ cấu hình tương ứng trong POM và dùng `-Dsummary.inputFile=...`, `-Dsummary.outputFile=...`. Không kết luận Maven sẽ tự ưu tiên CLI hơn literal plugin configuration trong mọi tình huống.

## 14. Cấu hình gọn nhất cho CLI property overrides

Nếu không cần hard-code path/limit vào consumer POM, plugin declaration có thể chỉ giữ GAV:

~~~xml
<plugin>
    <groupId>org.example.tools</groupId>
    <artifactId>summary-maven-plugin</artifactId>
    <version>1.0.0</version>
</plugin>
~~~

Đây là **mảnh thay thế** cho `<plugin>` ở mục 11, không phải một POM độc lập. Khi ấy:

- `inputFile` dùng annotation default `${project.basedir}/data/items.txt`, nếu không có `summary.inputFile`.
- `outputFile` dùng default `${project.build.directory}/summary/summary.txt`.
- `maxLines` dùng default `1000`.
- `skip` dùng default `false`.
- CLI `-Dsummary.maxLines=2` hoặc `-Dsummary.skip=true` có cơ hội áp dụng trực tiếp qua mapping property đúng thiết kế.

Trong bài thực hành, có thể dùng mục 11 để kiểm output bình thường, sau đó dùng cấu hình tối giản ở mục 14 để thử override/failure. Giữ hai trường hợp tách biệt nhằm tránh diễn giải sai độ ưu tiên parameter binding.

## 15. Kiểm case lỗi: maxLines không hợp lệ

Với consumer POM đã dùng plugin configuration tối giản của mục 14:

~~~bash
mvn -B -ntp -f summary-consumer/pom.xml \
  org.example.tools:summary-maven-plugin:1.0.0:summarize \
  -Dsummary.maxLines=0
~~~

**Dự kiến:** Maven exit code khác 0, goal báo:

~~~text
SUMMARY_BAD_LIMIT: maxLines must be >= 1; received 0
~~~

Đây là lỗi **MojoFailureException**, không phải lỗi tải plugin hay lỗi charset. Nó cho biết người gọi cần đặt một số nguyên dương. Nếu truyền một chuỗi không thể chuyển thành `int`, Maven parameter conversion có thể fail **trước execute()** và thông báo thuộc tầng Maven configuration, không bắt buộc chứa mã `SUMMARY_BAD_LIMIT` của code.

## 16. Kiểm case lỗi: quá giới hạn dòng

Với file ba dòng và POM consumer plugin tối giản:

~~~bash
mvn -B -ntp -f summary-consumer/pom.xml \
  org.example.tools:summary-maven-plugin:1.0.0:summarize \
  -Dsummary.maxLines=2
~~~

**Dự kiến:** Maven exit code khác 0, thông báo từ goal:

~~~text
SUMMARY_LIMIT_EXCEEDED: input has more than 2 lines; increase -Dsummary.maxLines or reduce input
~~~

File input không bị sửa; plugin dừng **trước khi ghi report mới**. Nếu lần trước đã tạo `target/summary/summary.txt`, file đó có thể còn tồn tại và mang dữ liệu cũ. CI phải kiểm Maven exit code; không được đánh đồng “output file hiện diện” với lần chạy thành công.

Nếu muốn thử clean case, xóa `target` theo lifecycle `mvn clean` **trên chính consumer project** hoặc dùng một output path thử nghiệm riêng, không chạy lệnh xóa toàn bộ workspace.

## 17. Kiểm case lỗi: input không tồn tại hoặc là directory

Nếu input path được cấu hình đến file không tồn tại, goal ném:

~~~text
SUMMARY_INPUT_NOT_FILE: input is not a regular file: <absolute-path>; set -Dsummary.inputFile=<path>
~~~

Một file path có tên đúng nhưng là **thư mục** cũng bị từ chối vì `Files.isRegularFile(input)` false. Lỗi này khác `SUMMARY_READ_FAILED`: file tồn tại/được nhìn thấy là regular nhưng I/O/permission/encoding vẫn có thể thất bại lúc đọc.

Mục đích của thông báo là cho người dùng biết **đường dẫn nào phải sửa**. Không dùng chung thông báo mơ hồ như `Something went wrong` mà không có identifier/path/action.

Trong hệ thống đa tenant, tuyệt đối hóa path trong lỗi có thể lộ cấu trúc filesystem; tùy security policy, report ra public logs cần ẩn một phần path hoặc dùng relative path phù hợp.

## 18. Kiểm case lỗi: cùng input và output

Goal đối chiếu hai `Path.toAbsolutePath().normalize()`, nếu bằng nhau thì fail:

~~~text
SUMMARY_SAME_PATH: input and output must differ: <absolute-path>
~~~

Lý do: ghi report đè file input sẽ phá dữ liệu gốc. **Giới hạn:** normalize đường dẫn không chứng minh hai paths trỏ cùng file qua symlinks/hard links; muốn bảo vệ mạnh hơn, bổ sung `Files.isSameFile(...)` khi cả hai tồn tại và policy về symlink/output sandbox.

Plugin demo tránh case đơn giản, **không tự nhận** đã xử lý mọi race/symlink attack trong filesystem không đáng tin. Các plugin thao tác artifacts trong CI cần threat model phù hợp.

## 19. Kiểm case lỗi: ghi file thất bại

Nếu target directory không có quyền ghi, đĩa đầy, volume lỗi hoặc thư mục output bị khóa, các operations tạo directory/temp/write/move có thể ném `IOException`. Goal bọc bằng:

~~~text
SUMMARY_WRITE_FAILED: cannot write output <absolute-path>; check directory permissions and free space
~~~

và giữ exception gốc để Maven debug khi cần.

Nếu output path đã là **thư mục**, goal ném `SUMMARY_OUTPUT_IS_DIRECTORY` trước I/O. Nếu input UTF-8 chứa byte sequences không hợp lệ, `Files.newBufferedReader` có thể ném lỗi decoding, được bọc thành `SUMMARY_READ_FAILED`.

**Không nuốt exception** rồi chỉ `getLog().error(...)` và return bình thường; Maven có thể báo BUILD SUCCESS sai dù output không được tạo. Nếu goal chịu trách nhiệm sinh report, missing report phải làm invocation fail theo hợp đồng.

## 20. Case skip: thành công nhưng không ghi output mới

Với cấu hình tối giản:

~~~bash
mvn -B -ntp -f summary-consumer/pom.xml \
  org.example.tools:summary-maven-plugin:1.0.0:summarize \
  -Dsummary.skip=true
~~~

Goal log:

~~~text
SUMMARY_SKIPPED: summary.skip=true; no report written
~~~

Sau đó return bình thường; Maven goal có thể success dù **không tạo file**. Đây là semantics skip có chủ đích, cần được document và kiểm CI.

Nếu mục tiêu pipeline là **bắt buộc phải có report mới**, không bật skip ở release profile. Đặc biệt, output cũ có thể vẫn còn. Có thể thêm manifest/build marker hoặc clean job trước khi chạy nếu hệ thống cần xác nhận freshness.

Không lạm dụng `skip` để che lỗi `maxLines` hoặc không có input trên release bắt buộc report.

## 21. Error code nên nhất quán và có hành động rõ

| Mã | Phân loại | Phản ứng của người dùng |
| --- | --- | --- |
| `SUMMARY_INPUT_REQUIRED` | Config/input | Thêm `<inputFile>` hoặc `-Dsummary.inputFile`. |
| `SUMMARY_OUTPUT_REQUIRED` | Config/output | Thêm output path. |
| `SUMMARY_BAD_LIMIT` | Config | Đặt `maxLines >= 1`. |
| `SUMMARY_INPUT_NOT_FILE` | Input | Kiểm path và file thường tồn tại. |
| `SUMMARY_OUTPUT_IS_DIRECTORY` | Input/config | Chọn đường dẫn file, không phải directory. |
| `SUMMARY_SAME_PATH` | Input/config | Tách input và output. |
| `SUMMARY_LIMIT_EXCEEDED` | Input/policy | Giảm số dòng hoặc tăng limit có review. |
| `SUMMARY_READ_FAILED` | Execution | Kiểm permissions, UTF-8, filesystem. |
| `SUMMARY_WRITE_FAILED` | Execution | Kiểm output directory, disk, ACL. |
| `SUMMARY_TEMP_CLEANUP_FAILED` | Warning | Kiểm stale temp files và quyền cleanup. |
| `SUMMARY_SKIPPED` | Info | Không sinh report mới. |
| `SUMMARY_WRITTEN` | Info | Kiểm output file/path, đếm dòng. |

Một **mã lỗi riêng** giúp CI phân loại và documentation tìm kiếm; nhưng đừng coi toàn bộ Maven console output là một API ổn định để parse. Nếu automation cần dữ liệu, **đọc report file có schema** và exit status, không scrape log prefix bất định.

Khi lỗi đã có nguyên nhân từ JDK/filesystem, giữ exception cause. Tuy nhiên log không được rò rỉ secrets hoặc nội dung nhạy cảm của input.

## 22. Gắn goal vào lifecycle hay gọi trực tiếp?

Bản demo `@Mojo(name="summarize")` không có `defaultPhase` và project consumer ở mục 11 **không có `<executions>`**. Vì vậy:

~~~bash
mvn -B -ntp -f summary-consumer/pom.xml package
~~~

**không tự động** gọi `summarize` chỉ vì plugin có trong `<build><plugins>`. Để gọi trực tiếp, dùng full GAV goal như mục 12.

Nếu cần chạy mỗi lần tới `generate-resources`, thêm vào **đúng plugin declaration của consumer**:

~~~xml
<executions>
    <execution>
        <id>generate-summary</id>
        <phase>generate-resources</phase>
        <goals>
            <goal>summarize</goal>
        </goals>
    </execution>
</executions>
~~~

Đây là **mảnh cấu hình bên trong `<plugin>`**, không phải một project POM mới. Với execution binding này, `mvn generate-resources` hoặc phase sau thích hợp chạy goal theo lifecycle.

Lựa chọn phase tùy mục đích:

- `generate-resources`: report được tạo sớm, nếu dùng như generated resource.
- `process-resources`: khi cần sau bước xử lý resources.
- `verify`: khi report chỉ dùng để kiểm chất lượng trước publication.

Không đặt goal quá sớm nếu cần compiled classes, quá muộn nếu output là input của compiler. Mục tiêu bài dùng file raw trong `data/` nên `generate-resources` hợp lý.

## 23. @Mojo(defaultPhase=...) không tự bind một plugin bên ngoài

Một nhầm lẫn:

~~~java
@Mojo(name = "summarize", defaultPhase = LifecyclePhase.GENERATE_RESOURCES)
~~~

Đây là **mảnh annotation minh họa**, không thuộc full Java source ở mục 9. Nó ghi metadata về phase mặc định của goal, nhưng **không bảo đảm mọi project consumer tự chạy goal** chỉ vì plugin có trên classpath.

Trong usage thông thường, muốn chạy tự động hãy khai báo `<executions>` với phase và goal trong consumer. Phần `@Mojo` nên nói chính xác goal cần project hay online, có cần dependency resolution, thread safe ra sao; không lạm dụng annotations để thay cách cấu hình build lifecycle.

Với goal file-only, không cần `requiresDependencyResolution=...`. Khai thừa runtime/compile dependency resolution sẽ kéo thêm graph, tăng thời gian và có thể gây lỗi trước khi xử lý input file.

## 24. Tạo help goal và kiểm descriptor tự sinh

Plugin producer ở mục 7 cấu hình Maven Plugin Plugin `helpmojo`. Sau `mvn clean install`, gọi từ consumer:

~~~bash
mvn -B -ntp -f summary-consumer/pom.xml \
  org.example.tools:summary-maven-plugin:1.0.0:help \
  -Ddetail=true -Dgoal=summarize
~~~

Mục tiêu: xem goal description và các parameters do plugin descriptor/help generator tạo. Thông tin help phụ thuộc comment/annotation và generated descriptor, **không** phải một file README được Maven tự đọc.

Các bước xác minh:

1. Plugin JAR được build với `packaging=maven-plugin`.
2. `META-INF/maven/plugin.xml` có entry `<goal>summarize</goal>` và implementation đúng.
3. Thông tin `inputFile`/`outputFile`/`maxLines`/`skip` có tên và kiểu chính xác.
4. Generated help được tạo nếu execution `helpmojo` chạy và project compile.
5. CLI GAV đầy đủ resolve được plugin.
6. Kết quả consumer report khớp expected bytes.

Nếu Maven nói `No plugin descriptor found`, thường do sai packaging, không sinh descriptor, plugin JAR không có `plugin.xml`, annotations/process lifecycle bị lỗi hoặc đang gọi **nhầm artifact/version**. Đừng thử rename một JAR tùy ý thành `*-maven-plugin.jar` rồi kỳ vọng Maven tự nhận.

## 25. Unit test vs integration test của một Mojo

Một plugin goal cần ít nhất các loại kiểm thử sau:

| Loại | Thứ được kiểm | Ví dụ |
| --- | --- | --- |
| Unit test logic thuần | Thuật toán đếm dòng, blanks, format report. | Input ba dòng → 3/2. |
| Mojo test harness | Parameter injection, lookup mojo, Maven context cơ bản. | Không truyền input hoặc maxLines sai. |
| Integration test | Build plugin, chạy Maven goal trong consumer thật. | `mvn ...:summarize` sinh report. |
| Negative integration test | Exit code và thông báo lỗi khi config sai. | `maxLines=0` → fail. |
| Idempotence test | Chạy hai lần cùng input, report bytes giống nhau. | Hash report trước/sau. |
| Cross-platform | LF/CRLF, Windows paths và shell quoting. | PowerShell gọi full GAV. |
| Parallel/reactor | Output isolation khi đa module. | Không claim `threadSafe=true` khi chưa test. |

Apache Maven Plugin Testing Harness hiện hỗ trợ JUnit 5 extension; có thể dùng `@MojoTest` và `@InjectMojo` với test POM. Maven Invoker Plugin thường phù hợp để chạy integration tests trong môi trường Maven thật.

**Demo trong bài kiểm qua command và expected report**, chưa nhúng sẵn harness test classes vào producer POM. Nếu bạn thêm test suite production, pin harness/invoker versions và tạo fixture project riêng. Không giả vờ rằng một test được trình bày dưới dạng câu lệnh đã được CI thật sự chạy.

## 26. Thiết kế goal an toàn với multi-module reactor

Một reactor:

~~~text
parent/
├── pom.xml
├── module-a/pom.xml
└── module-b/pom.xml
~~~

Nếu cả hai modules bind `summarize` và giữ defaults `${project.build.directory}/summary/summary.txt`, mỗi module thường có output dưới **target riêng**, tránh ghi đè trực tiếp.

Nhưng nếu CI override:

~~~text
-Dsummary.outputFile=/shared/reports/summary.txt
~~~

cả hai module có thể cố gắng ghi cùng file, đặc biệt khi chạy `mvn -T`. Vì thế demo đánh dấu `threadSafe=false`; Maven có thể cảnh báo plugin không thread-safe trong parallel build.

Để tiến tới thread-safe:

1. Output path phải định danh module/GAV hoặc được bảo đảm unique.
2. Không dùng mutable static/shared state.
3. Temp files phải unique và cleanup đúng.
4. Không ghi vào project root/shared path ngoài kiểm soát.
5. Kiểm parallel execution và các đường dẫn bị override.
6. Chỉ sau đó mới khai `threadSafe=true` với bằng chứng.

Một goal chỉ cần chạy **một lần cho reactor** có thể cân nhắc `aggregator=true` và dựa vào MavenSession/reactorProjects theo API phù hợp, nhưng behavior aggregation cần thiết kế/test riêng; không đổi flag chỉ vì muốn một report tổng mà không biết module ownership.

## 27. Output file và Maven artifact attachment là hai việc khác nhau

Goal tạo:

~~~text
target/summary/summary.txt
~~~

Nhưng Maven **không tự publish file này** khi chạy `mvn install` hoặc `mvn deploy`. Maven Project có main artifact theo packaging, còn attached artifacts cần plugin/API khác hoặc code attach explicit.

Nếu người dùng yêu cầu report xuất bản cùng JAR:

- Chọn classifier và extension rõ ràng.
- Có bước attach artifact vào MavenProject (theo API plugin phù hợp) hoặc dùng plugin phụ trợ thích hợp.
- Đảm bảo file tồn tại trước install/deploy.
- Review repository policy, checksums và content sensitivity.
- Viết test consumer có thể tải đúng classifier.

**Không âm thầm attach report** chỉ vì goal viết file dưới `target`. Tác dụng phụ của goal phải được mô tả công khai: file nào được tạo, có bị ghi đè không, có sửa POM/source không, có gửi network không.

Goal mẫu là offline/file-only, không cần network cho hoạt động xử lý file (nhưng Maven có thể cần mạng để tải plugin dependencies nếu chưa cache).

## 28. Idempotency, incremental build và output freshness

Khi một goal tạo file từ input, nhiều lần chạy cần kết quả có thể dự đoán:

- **Deterministic:** input text giống nhau → output string giống nhau.
- **Idempotent về nội dung:** chạy lại không làm tăng dòng report hoặc tạo file vô hạn.
- **Atomic khi hỗ trợ:** ghi temp rồi move để giảm nguy cơ người đọc thấy file mới chỉ ghi một nửa.
- **Fail-closed:** có lỗi I/O thì throw exception, Maven không báo success sai.
- **Freshness:** báo cáo cũ sau `skip` hoặc failure không được dùng nhầm làm kết quả mới.
- **No hidden side effects:** không tự xóa source, không tải URL lạ, không sửa dependencies/POM.

Nếu muốn tối ưu incremental build, có thể so input hash/mtime và report schema version rồi skip khi còn đúng. Nhưng cần chắc cả tool version/options đều góp vào cache key; dựa mtime đơn thuần dễ sai trên CI restore. Demo **luôn tính lại** khi `skip=false` để đơn giản và dễ xác minh.

Một plugin tạo output cho downstream compiler nên ghi tại phase đủ sớm và đăng ký resource/source root phù hợp. Chỉ tạo file ở `target` không tự khiến compiler đóng gói nó vào JAR.

## 29. Giới hạn bảo mật của tham số kiểu File

Một input hoặc output `java.io.File` linh hoạt nhưng có thể tạo rủi ro khi config đến từ nguồn không tin cậy:

- Đường dẫn output nằm ngoài workspace hoặc trỏ đến file cần giữ.
- Symlink/hard link giúp input/output trỏ cùng file dù strings khác.
- Một dòng đầu vào cực lớn tiêu tốn RAM khi `readLine()`.
- Tệp bí mật bị chọn làm input rồi nội dung/metadata vô tình được log.
- File permission/umask ảnh hưởng output và file tạm.
- Build chạy song song trong shared folder gây overwrite/race.

Plugin demo chỉ đọc input và ghi **tổng số dòng**, không sao chép nội dung. Mặc định output ở `project.build.directory` giảm tác động ngoài ý muốn; người dùng vẫn có thể override. Trong production, giới hạn input size bytes, path allowlist, symlink policy, file ownership, quota và sandbox khi threat model cần.

Không đặt credentials trực tiếp trong parameters và không log raw input. Khi build từ PR không tin cậy, Maven plugin chạy với quyền runner; least-privilege runner và protected release jobs vẫn thiết yếu.

## 30. Chẩn đoán lỗi thường gặp khi phát triển plugin goal

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| `Unknown packaging: maven-plugin` | Lifecycle extension/plugin infrastructure không có hoặc môi trường Maven lỗi. | Kiểm Maven distribution và plugin packaging. |
| `No plugin descriptor found` | Descriptor không được sinh/đóng gói vào JAR. | Kiểm `maven-plugin-plugin`, `plugin.xml`, plugin JAR. |
| `Goal 'summarize' not found` | Sai `@Mojo(name)`, descriptor cũ hoặc gọi nhầm version. | Kiểm generated descriptor, reinstall và full GAV. |
| `Plugin ... could not be resolved` | Plugin chưa install/publish, repo/pluginRepositories sai. | Install plugin trước hoặc khai báo repo đúng. |
| `No such file` | Default input path khác basedir kỳ vọng. | Kiểm `project.basedir` và `inputFile`. |
| `SUMMARY_BAD_LIMIT` | `maxLines <= 0`. | Đổi thành số nguyên dương. |
| `SUMMARY_LIMIT_EXCEEDED` | Input vượt ngưỡng. | Review file/threshold, không bypass bừa. |
| `SUMMARY_READ_FAILED` | Permissions, UTF-8 hoặc I/O. | Kiểm charset/ACL/file integrity. |
| `SUMMARY_WRITE_FAILED` | Không tạo được output/temp hoặc move fail. | Kiểm path, filesystem và disk. |
| Maven BUILD SUCCESS nhưng không có file mới. | `skip=true`, output path khác, goal chưa được gọi/bind. | Đọc log, POM/executions, path và goal status. |
| File report có từ lần cũ dù build fail. | Output chưa bị xóa trong failure path. | Dựa exit code, chạy clean khi cần. |
| `-Dsummary.maxLines=2` không có tác dụng. | `<maxLines>1000</maxLines>` literal ở plugin config. | Dùng cấu hình tối giản hoặc property expression rõ ràng. |
| Goal chạy hai lần trong reactor. | Goal được bind nhiều executions/module. | Kiểm effective POM, inheritance và lifecycle bindings. |
| Parallel build ghi đè report. | Các modules override chung output path. | Unique paths và thread-safety testing. |
| Mất nonblank count khi có whitespace Unicode. | Khác định nghĩa “trống”, encoding hoặc xử lý dòng. | Document `String.isBlank()` và UTF-8. |
| Report không được publish cùng artifact. | File tạo ra nhưng chưa attach classifier. | Thiết kế attachment rõ và test deploy. |

**Thứ tự debug:** Plugin GAV/version → descriptor/goal → effective parameters → input path/data → validation → I/O/output path → lifecycle binding → parallel/CI context.

## 31. Checklist review một goal trước khi phát hành

- [ ] Goal name ngắn, rõ hành động, tránh gây nhầm với goal Apache Maven chính thức.
- [ ] Plugin artifactId dùng quy ước `<prefix>-maven-plugin`.
- [ ] `@Mojo` mô tả project requirement, thread-safety và lifecycle hợp lý.
- [ ] `@Parameter` có Java type, property name, default, required và Javadoc rõ.
- [ ] Bảng contract input/output giải thích đường dẫn và schema.
- [ ] Có kiểm thiếu input, sai kiểu, invalid ranges và conflicting paths.
- [ ] Lỗi người dùng tách `MojoFailureException` với lỗi I/O `MojoExecutionException`.
- [ ] Exceptions có message actionable và giữ cause khi cần.
- [ ] Không swallow exception rồi return success sai.
- [ ] Trạng thái skip được document; không nhầm report cũ với output mới.
- [ ] Output deterministic khi có thể, schema/encoding rõ.
- [ ] Không ghi đè file quan trọng hoặc phát hành artifact ngoài ý muốn.
- [ ] Không log secret/raw sensitive input.
- [ ] Output parent directory/permissions/cleanup/atomic fallback được xét.
- [ ] Goal không yêu cầu dependency resolution hoặc online khi không cần.
- [ ] Multi-module/parallel behavior được định nghĩa, không khai threadSafe sai.
- [ ] Maven Plugin Plugin tạo `META-INF/maven/plugin.xml` đúng.
- [ ] Help goal/docs mô tả đầy đủ parameters, cách gọi và errors.
- [ ] Có ít nhất một consumer integration test chạy goal thật và kiểm output.
- [ ] Có negative tests cho validation, maxLines, permissions, skip, stale output.
- [ ] Plugin API/tools versions và Maven/JDK minimum compatibility được xác minh.
- [ ] CI kiểm Maven exit code và report, không scrape console output.
- [ ] Publication GAV/namespace, licenses/SCM, signatures và repo policy được review.

## 32. Câu hỏi tự kiểm tra

1. **Có `execute()` mà không có `plugin.xml` đã đủ để Maven gọi goal chưa?** Chưa; Maven cần descriptor được build/packaged.
2. **Vì sao dùng `packaging=maven-plugin`?** Để Maven áp lifecycle và descriptor generation phù hợp plugin.
3. **`@Mojo(name="summarize")` và Java class name có phải giống nhau không?** Không; annotation quyết định goal name.
4. **`@Parameter(property="summary.maxLines")` cho phép gì?** Mapping giá trị từ Maven property/CLI `-D`.
5. **`required=true` có đảm bảo input file tồn tại không?** Không; cần validation runtime.
6. **Đường dẫn default nên được giải thích theo đâu?** Theo `project.basedir`, `project.build.directory` hoặc quy tắc cụ thể.
7. **Vì sao ném `MojoFailureException` cho maxLines=0?** Đây là cấu hình/đầu vào vi phạm contract.
8. **Khi file system không cho tạo output, nên trả gì?** `MojoExecutionException` với cause và hành động kiểm tra I/O.
9. **Tại sao không chỉ `getLog().error` và return?** Maven có thể báo success sai khi report chưa được tạo.
10. **Output file có thuộc Maven artifact tự động không?** Không; cần attach nếu muốn publish như classifier.
11. **Goal có `defaultPhase` thì mọi POM sẽ tự chạy goal không?** Không; thường cần executions/lifecycle binding.
12. **`mvn -T` an toàn chỉ vì class không có biến static?** Chưa; output path có thể trùng giữa modules.
13. **Skip true có xóa report cũ không?** Không trong demo; job phải kiểm freshness.
14. **Vì sao phải test cả consumer?** Để kiểm plugin GAV, descriptor, injection, output và lifecycle thực.
15. **`-Dsummary.maxLines=2` có luôn thắng literal `<maxLines>1000</maxLines>` trong POM không?** Không nên phụ thuộc; chọn một nguồn cấu hình rõ.
16. **File UTF-8 có CRLF có làm count khác không?** Với ba dòng tương đương và `readLine()`, tổng vẫn ba.
17. **Atomic move fallback có còn atomic không?** Không; khi fallback REPLACE_EXISTING không bảo đảm atomic.
18. **Input file có một dòng nhiều GB có được cap bằng maxLines không?** Không đầy đủ; cần size/line-length limit.
19. **Maven build pass nhưng path report khác expected thì cần làm gì?** Kiểm effective parameter outputFile và basedir.
20. **Mục tiêu cao nhất của contract goal là gì?** Có thể cấu hình, quan sát, kiểm chứng và sửa lỗi mà không đoán.

## 33. Tài liệu chính thức

- [Apache Maven — Guide to Developing Java Plugins](https://maven.apache.org/guides/plugin/guide-java-plugin-development.html): Mojo, packaging, project POM, parameters, CLI invocation và lifecycle.
- [Apache Maven — Mojo API Specification (Maven 3)](https://maven.apache.org/developers/mojo-api-specification.html): hợp đồng `execute`, parameter injection và môi trường chạy.
- [Apache Maven Plugin Tools — Annotations](https://maven.apache.org/plugin-tools/maven-plugin-tools-annotations/index.html): `@Mojo`, `@Parameter` và semantics.
- [Apache Maven Plugin Tools — @Parameter API](https://maven.apache.org/plugin-tools/maven-plugin-annotations/apidocs/org/apache/maven/plugins/annotations/Parameter.html): property, defaultValue, required và readonly.
- [Apache Maven Plugin Tools — @Mojo API](https://maven.apache.org/plugin-tools/maven-plugin-annotations/apidocs/org/apache/maven/plugins/annotations/Mojo.html): requiresProject, defaultPhase, threadSafe, requiresOnline.
- [Apache Maven — Maven Plugin Plugin Usage](https://maven.apache.org/plugin-tools/maven-plugin-plugin/usage.html): descriptor/helpmojo generation và packaging.
- [Apache Maven — Plugin Descriptor Generation](https://maven.apache.org/plugin-tools/maven-plugin-plugin/examples/generate-descriptor.html): `plugin.xml` và goal metadata.
- [Apache Maven — Help Mojo Generation](https://maven.apache.org/plugin-tools/maven-plugin-plugin/examples/generate-help.html): cách tạo help goal.
- [Apache Maven — Plugin Documentation Standard](https://maven.apache.org/guides/development/guide-plugin-documentation.html): parameter docs và mô tả goal.
- [Apache Maven — Plugin Testing Harness](https://maven.apache.org/plugin-testing/maven-plugin-testing-harness/): JUnit 5/`@MojoTest`.
- [Apache Maven — Plugin Testing Guide](https://maven.apache.org/plugin-developers/plugin-testing.html): kiểm MoJo và fixtures.
- [Apache Maven — Configuring Plugins](https://maven.apache.org/guides/mini/guide-configuring-plugins.html): `<configuration>`, `<executions>`, phase và pluginManagement.
- [Apache Maven — Introduction to Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html): phases và plugin goals.
- [Apache Maven — Maven Plugin API](https://maven.apache.org/components/ref/3-LATEST/maven-plugin-api/apidocs/org/apache/maven/plugin/package-summary.html): `AbstractMojo`, `MojoExecutionException` và `MojoFailureException`.
- [Apache Maven — Plugin Prefix Mapping](https://maven.apache.org/guides/introduction/introduction-to-plugin-prefix-mapping.html): short prefix vs full plugin coordinates.

**Kết luận:** Một Maven goal chất lượng phải có **đầu vào định nghĩa rõ (tham số, defaults, validation), đầu ra định nghĩa rõ (path, format, side effects, idempotency) và lỗi có ý nghĩa (mã, nguyên nhân, cách sửa, Maven exit failure)**. Việc tạo Java class chỉ là bước đầu; cần plugin descriptor, helper docs, CLI/lifecycle semantics, consumer test và kiểm compatibility/parallel/supply-chain. Trong demo, goal `summarize` có đủ từ Java 17 source đến plugin JAR, POM consumer và lệnh chạy, nhằm biến “goal chạy được” thành “goal người khác có thể sử dụng và chẩn đoán được”.
