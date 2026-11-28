# Kiểm thử lại cú pháp, nhập xuất và mã thoát trên gói phân phối thực tế

Một ứng dụng Spring Shell có thể chạy tốt trong IDE nhưng gặp lỗi sau khi đóng gói: thiếu dependency runtime, chọn nhầm JAR thường thay vì executable JAR, cấu hình chỉ tồn tại trong máy phát triển, command không nhận đúng argument có dấu cách, output tiếng Việt bị lỗi hoặc process trả exit code sai.

Vì vậy, bước kiểm thử cuối phải chạy **đúng artifact sẽ phát hành** trong một thư mục phân phối riêng. Bài kiểm thử này xác nhận người dùng có thể khởi chạy ứng dụng bằng cách đã được tài liệu hóa, truyền đúng cú pháp, cung cấp input, đọc output và nhận mã thoát phù hợp.

Phạm vi bài gồm Spring Shell 4, Spring Boot 4 và executable JAR. Các nguyên tắc tương tự áp dụng cho executable WAR, image container hoặc native executable, nhưng mỗi loại artifact cần một quy trình khởi chạy và kiểm thử riêng.

## 1. Kiểm thử mã nguồn và kiểm thử gói phân phối trả lời hai câu hỏi khác nhau

Kiểm thử unit và kiểm thử Spring Shell trong application context xác nhận logic command, parser, validator hoặc service hoạt động đúng khi chạy trong môi trường test. Chúng chưa chứng minh gói phát hành chứa đúng class, dependency, resource và cấu hình cần thiết.

| Loại kiểm thử | Điều được xác nhận | Điều chưa được xác nhận |
|---|---|---|
| Unit test | Logic service, parser helper, validator | Cấu trúc JAR và runtime classpath |
| Spring Shell test | Command registration, cú pháp, kết quả và tương tác trong test context | Người dùng chạy được artifact đã phát hành |
| Build/package test | Plugin tạo được executable archive | Command thực tế có hoạt động đúng khi chạy |
| Artifact acceptance test | JAR được khởi chạy từ thư mục phân phối, nhận input và trả output/exit code | Môi trường của mọi máy khách nếu chưa thử trên các hệ điều hành mục tiêu |
| Smoke test sau cài đặt | Bộ file được cài đặt và wrapper chạy được | Toàn bộ tình huống biên và tải dài hạn |

Không dùng kết quả từ IDE hoặc Gradle test runtime để kết luận artifact đã sẵn sàng phát hành. Acceptance test cần gọi executable JAR bằng một tiến trình Java mới, chỉ với những file và cấu hình có trong gói phân phối.

## 2. Tạo đúng executable JAR

Spring Boot đóng gói ứng dụng cùng các dependency runtime vào executable JAR để chạy bằng **java -jar**. Với Gradle, task **bootJar** tạo executable archive. Với Maven, plugin **spring-boot-maven-plugin** thực hiện goal **repackage** trên JAR đã tạo trong phase package.

### 2.1. Gradle

Chạy:

~~~bash
./gradlew clean bootJar
~~~

Trên Windows:

~~~bat
gradlew.bat clean bootJar
~~~

Task **bootJar** tạo executable JAR. Task **assemble** được cấu hình phụ thuộc vào **bootJar**, vì vậy **build** cũng tạo executable archive. Tuy nhiên, dự án thường có thể tạo đồng thời JAR thường và executable JAR; cần chọn đúng file có cấu trúc Spring Boot để phân phối.

### 2.2. Maven

Chạy:

~~~bash
mvn clean package
~~~

Nếu dự án dùng **spring-boot-starter-parent**, goal **repackage** được cấu hình sẵn khi khai báo Spring Boot Maven plugin. Nếu không dùng parent này, cần cấu hình execution cho goal **repackage** trong plugin.

Không chỉ gọi **spring-boot:repackage** trên một thư mục trống. Goal này xử lý archive đã được tạo trong phase package; khi gọi trực tiếp từ command line, cần chạy cả phase package.

### 2.3. Chọn artifact được phát hành

Ví dụ đường dẫn thường gặp:

| Build tool | Executable JAR | JAR thường |
|---|---|---|
| Gradle | build/libs/task-cli-1.0.0.jar | build/libs/task-cli-1.0.0-plain.jar |
| Maven | target/task-cli-1.0.0.jar | target/task-cli-1.0.0.jar.original |

Tên thực tế phụ thuộc group, artifact, version và classifier của dự án. Không viết script phát hành dựa vào một tên file đoán trước; lấy đúng output do build tạo ra và kiểm tra nội dung của archive.

## 3. Kiểm tra cấu trúc archive trước khi chạy

Executable JAR của Spring Boot có launcher riêng trong manifest. Manifest thường có hai entry:

- **Main-Class:** bootstrap launcher của Spring Boot.
- **Start-Class:** class ứng dụng có phương thức main.

Các class và resource của ứng dụng nằm trong **BOOT-INF/classes/**, còn dependency runtime nằm trong **BOOT-INF/lib/**. Đây là cấu trúc quan trọng để launcher nạp nested JAR.

Liệt kê nội dung:

~~~bash
jar tf build/libs/task-cli-1.0.0.jar
~~~

Kiểm tra nhanh các vùng quan trọng:

~~~bash
jar tf build/libs/task-cli-1.0.0.jar | grep -E '^(META-INF/MANIFEST.MF|BOOT-INF/classes/|BOOT-INF/lib/)'
~~~

Trên PowerShell:

~~~powershell
jar tf build/libs/task-cli-1.0.0.jar |
    Select-String '^(META-INF/MANIFEST.MF|BOOT-INF/classes/|BOOT-INF/lib/)'
~~~

Đọc manifest. Trên môi trường có **unzip**:

~~~bash
unzip -p build/libs/task-cli-1.0.0.jar META-INF/MANIFEST.MF
~~~

Kiểm tra:

1. Có **META-INF/MANIFEST.MF**.
2. **Main-Class** trỏ đến launcher phù hợp với layout.
3. **Start-Class** trỏ đến class ứng dụng.
4. Có class command, cấu hình và resource cần thiết trong **BOOT-INF/classes/**.
5. Các dependency runtime quan trọng có trong **BOOT-INF/lib/**.
6. Không vô tình phát hành JAR thường, JAR test hoặc artifact của module khác.

Không cần sửa manifest thủ công để thay thế cấu hình của Spring Boot Maven hoặc Gradle plugin. Nếu main class không được nhận diện đúng, hãy cấu hình mainClass trong plugin và build lại artifact.

## 4. Tạo thư mục staging giống cấu trúc phát hành

Sau khi build, tạo một thư mục staging chỉ chứa các file sẽ được giao cho người dùng. Ví dụ:

~~~text
release/
└── task-cli/
    ├── task-cli.jar
    ├── config/
    │   └── application.yaml
    ├── scripts/
    │   ├── run.sh
    │   └── nightly.commands
    └── README.txt
~~~

Copy executable JAR vừa build vào thư mục này. Chỉ thêm file cấu hình, script và tài liệu thực sự thuộc gói phát hành. Không copy thư mục build, thư mục source, class output của IDE hoặc dependency test vào staging.

Sau đó chạy test từ thư mục staging, không chạy từ project root:

~~~bash
cd release/task-cli
java -Dspring.shell.interactive.enabled=false -jar task-cli.jar help
~~~

Mục tiêu là phát hiện sự phụ thuộc vô tình vào:

- File chỉ tồn tại trong source tree.
- Relative path đang đúng vì IDE đặt working directory ở project root.
- Environment variable chỉ được cấu hình trên máy developer.
- Classpath hoặc dependency do IDE tự thêm.
- File cấu hình local không được đóng gói hoặc không được chuyển cùng artifact.

Thực hiện thêm một lượt từ thư mục có tên chứa dấu cách hoặc ký tự tiếng Việt. Điều này giúp phát hiện wrapper hoặc script xử lý path không đúng.

## 5. Xác nhận môi trường Java trên máy chạy

Trước khi chạy artifact, kiểm tra Java runtime:

~~~bash
java -version
~~~

Đối chiếu phiên bản Java với yêu cầu của phiên bản Spring Boot và Spring Shell mà ứng dụng sử dụng. Máy build có thể dùng JDK mới hơn máy chạy; artifact phải được thử với runtime tối thiểu được công bố trong tài liệu phân phối.

Kiểm tra thêm:

- Kiến trúc CPU và hệ điều hành nằm trong phạm vi hỗ trợ.
- Java executable được tìm thấy qua PATH hoặc wrapper dùng đường dẫn được cấu hình.
- Thư mục làm việc và thư mục cấu hình có quyền đọc/ghi phù hợp.
- Các dependency native hoặc chương trình ngoài (nếu có) tồn tại trên máy đích.
- Locale và terminal có thể hiển thị nội dung mà CLI phát ra.

Không mặc định máy người dùng có Gradle, Maven hoặc IDE. Executable JAR phải chạy được bằng Java runtime và các thành phần bên ngoài được liệt kê trong yêu cầu cài đặt.

## 6. Kiểm thử cú pháp command trên artifact

Spring Shell 4 hỗ trợ option dạng dài và ngắn. Option dạng dài có thể viết **--key=value** hoặc **--key value**; option ngắn có thể viết **-k=value** hoặc **-k value**. Argument vị trí được đánh chỉ số từ 0. Option và argument có thể xuất hiện theo các thứ tự được parser hỗ trợ.

Trong interactive shell, parser tách từ theo khoảng trắng. Giá trị chứa khoảng trắng cần đặt trong dấu nháy đơn hoặc nháy kép. Dấu nháy bao ngoài được loại bỏ; dấu nháy cùng loại bên trong cần escape bằng backslash. Dấu nháy không cân bằng phải bị từ chối.

Ví dụ kiểm thử:

~~~text
task create --title="Báo cáo cuối kỳ"
task create --title='Báo cáo cuối kỳ'
task create --title="He said \"Hello\""
task list --status OPEN
task list --status=OPEN
~~~

Với mỗi command quan trọng, kiểm thử các trường hợp sau bằng chính artifact:

| Nhóm | Ca kiểm thử | Kết quả cần xác nhận |
|---|---|---|
| Tên command | Tên đầy đủ và alias | Đúng command được gọi |
| Option | Dạng dài và dạng ngắn | Bind đúng giá trị |
| Dấu phân cách | Dùng dấu bằng hoặc khoảng trắng | Hai cách hợp lệ cho kết quả tương đương |
| Thứ tự | Đổi vị trí option và argument | Parser vẫn bind đúng theo hợp đồng |
| Khoảng trắng | Giá trị có dấu cách và Unicode | Không bị tách thành nhiều giá trị |
| Dấu nháy | Nháy đơn, nháy kép, escape | Giá trị sau parse đúng |
| Dấu nháy lỗi | Thiếu dấu đóng | Có lỗi cú pháp rõ ràng |
| Argument | Thiếu, thừa hoặc sai vị trí | Báo usage error |
| Option | Thiếu option bắt buộc hoặc option không biết | Báo lỗi, không gọi nghiệp vụ |
| Kiểu dữ liệu | Số, boolean, enum, path sai định dạng | Conversion/validation từ chối đúng |
| Help | Help toàn cục và help command | Nội dung trợ giúp đúng artifact |

Khi chạy từ command line của hệ điều hành, cần phân biệt quoting của shell bên ngoài với quoting của Spring Shell. Bash, PowerShell và CMD có quy tắc riêng để chuyển một command line thành mảng argument của JVM. Không sao chép nguyên văn chuỗi test của REPL sang ProcessBuilder rồi giả định parser nhận cùng dữ liệu.

Với **ProcessBuilder**, mỗi phần tử trong danh sách là một argument riêng; không thêm dấu nháy shell quanh phần tử. Khi test command có giá trị chứa dấu cách, hãy truyền đúng một phần tử Java chứa toàn bộ giá trị đó và kiểm tra kết quả trên artifact.

## 7. Kiểm thử validation và lỗi chuyển đổi

Spring Shell 4 tích hợp Bean Validation cho command parameter. Constraint được kiểm tra trước khi phương thức command thực thi. Điều này cần được xác nhận trên JAR đã đóng gói, vì dependency validation hoặc cấu hình runtime thiếu có thể khiến hành vi khác với test context.

Ví dụ command:

~~~java
import jakarta.validation.constraints.Size;

import org.springframework.shell.core.command.annotation.Command;
import org.springframework.shell.core.command.annotation.Option;
import org.springframework.stereotype.Component;

@Component
public class LabelCommands {

    @Command(name = "label set")
    public String set(
            @Option(longName = "value", required = true)
            @Size(min = 3, max = 30) String value) {
        return "Đã đặt nhãn.";
    }
}
~~~

Trong acceptance test, chạy ít nhất:

- Giá trị hợp lệ nằm trong giới hạn.
- Giá trị ngắn hơn giới hạn tối thiểu.
- Giá trị dài hơn giới hạn tối đa.
- Không truyền option bắt buộc.
- Truyền một giá trị không chuyển được sang kiểu tham số.
- Truyền option không tồn tại.

Xác nhận command không thực hiện side effect khi parser hoặc validator từ chối input. Output lỗi phải đủ rõ cho người dùng, nhưng không chứa stack trace, secret hoặc dữ liệu nhạy cảm trong chế độ phát hành thông thường.

## 8. Kiểm thử chế độ interactive và non-interactive riêng biệt

Spring Shell 4 mặc định chạy interactive mode, kể cả khi có command-line arguments. Muốn chạy command từ đối số tiến trình, đặt **spring.shell.interactive.enabled=false**. Khi đó Spring Shell dùng **NonInteractiveShellRunner**.

Có thể đặt thuộc tính trong file cấu hình phát hành:

~~~yaml
spring:
  shell:
    interactive:
      enabled: false
~~~

Hoặc truyền dưới dạng JVM system property trước tham số **-jar**:

~~~bash
java -Dspring.shell.interactive.enabled=false -jar task-cli.jar task list
~~~

Trên Windows:

~~~bat
java -Dspring.shell.interactive.enabled=false -jar task-cli.jar task list
~~~

Không đặt tùy chọn **-D** sau tên JAR vì khi đó JVM không còn xem nó là system property. Nếu thuộc tính được đưa vào command arguments với cú pháp **--...**, cần bảo đảm Spring Boot và Spring Shell nhận nó ở đúng lớp mà ứng dụng dự định.

Kiểm thử hai chế độ:

| Chế độ | Cách chạy | Điều cần xác nhận |
|---|---|---|
| Interactive | Khởi chạy trong terminal thật | Prompt, help, completion, nhập nhiều command và thoát |
| Non-interactive | Truyền command khi khởi chạy | Command thực thi một lần rồi process kết thúc |
| Script | Truyền argument bắt đầu bằng **@** | Các dòng trong script được đọc và thực thi đúng |

**ProcessBuilder** với pipe stdin/stdout không tạo terminal tương tác. Vì vậy, test process thông thường phù hợp với non-interactive command và I/O theo hợp đồng của ứng dụng. Muốn kiểm thử prompt, JLine key binding, completion hoặc hành vi terminal, dùng pseudo-terminal (PTY/ConPTY) hoặc chạy smoke test trong terminal thật.

## 9. Kiểm thử script trên thư mục phân phối

Spring Shell non-interactive runner hỗ trợ chạy file script bằng tiền tố **@**. Ví dụ:

~~~text
task list --status=OPEN
task create --title="Kiểm thử gói phân phối"
task list --status=OPEN
~~~

Lưu nội dung vào **scripts/nightly.commands** với encoding UTF-8, rồi chạy từ thư mục staging:

~~~bash
java -Dspring.shell.interactive.enabled=false -jar task-cli.jar @scripts/nightly.commands
~~~

Kiểm tra:

1. Script được tìm thấy theo working directory hoặc đường dẫn tuyệt đối.
2. Dòng lệnh có dấu cách và dấu nháy được parse đúng.
3. Nhiều command được chạy theo đúng thứ tự.
4. Lỗi của một command được xử lý theo chính sách runner và phiên bản đang dùng.
5. Kết quả cuối cùng và process exit code phù hợp với hợp đồng của CLI.
6. Script không tồn tại, không đọc được hoặc có dòng cú pháp lỗi tạo tín hiệu lỗi rõ ràng.

Kiểm thử thêm file script có CRLF nếu hỗ trợ Windows và LF nếu hỗ trợ Linux/macOS. Không giả định mọi file script được tạo trên một hệ điều hành sẽ có line ending phù hợp trên hệ điều hành khác.

Với Spring Shell 4.0.4, issue #1391 ghi nhận trường hợp lỗi parse command hoặc lỗi mở/đọc file script có thể chỉ được log và process kết thúc với code 0. Hãy kiểm thử riêng các trường hợp này trên đúng phiên bản phát hành, theo dõi release chứa bản sửa và không suy ra exit code của lỗi script từ test command execution failure.

## 10. Kiểm thử stdout, stderr và encoding

Một CLI thường có ba loại output:

- **Kết quả command:** nội dung mà người dùng hoặc script cần đọc.
- **Thông báo lỗi:** lý do command không thể hoàn tất.
- **Log chẩn đoán:** thông tin vận hành và debug.

Xác định rõ output nào thuộc stdout, output nào thuộc stderr và output nào chỉ xuất hiện khi bật debug. Không để log startup, banner hoặc ANSI color làm hỏng định dạng JSON/CSV mà script tiêu thụ.

Trong acceptance test:

- Ghi stdout và stderr ra hai file riêng nếu cần xác nhận từng stream.
- Dùng **redirectErrorStream(true)** nếu test chỉ cần kiểm tra output tổng hợp.
- Đọc file output bằng UTF-8.
- So sánh các chuỗi ổn định hoặc cấu trúc dữ liệu, không phụ thuộc toàn bộ banner và timestamp.
- Kiểm tra nội dung tiếng Việt có dấu, ký tự ngoài ASCII và tên file có dấu cách.
- Kiểm tra ANSI escape sequence nếu command có màu; tắt màu hoặc loại bỏ sequence trước khi so sánh output máy đọc.
- Giới hạn kích thước output trong test để tránh ghi file không giới hạn.

Ví dụ PowerShell đọc output:

~~~powershell
Get-Content .\stdout.txt -Raw -Encoding UTF8
Get-Content .\stderr.txt -Raw -Encoding UTF8
~~~

Không kết luận encoding đúng chỉ vì output hiển thị đúng trong IDE. Chạy từ terminal và runtime tương tự môi trường phát hành. Java có thể xử lý file bằng UTF-8 nhưng terminal vẫn có font hoặc cấu hình hiển thị không phù hợp.

## 11. Kiểm thử stdin khi command hỗ trợ dữ liệu từ pipe

Không phải command Spring Shell nào cũng đọc stdin. Nếu ứng dụng định nghĩa một command nhận dữ liệu từ standard input, acceptance test phải gửi input qua process stream và đóng stream sau khi ghi.

Ví dụ trong Java:

~~~java
byte[] input = "task-one\ncông việc thứ hai\n"
        .getBytes(StandardCharsets.UTF_8);

try (var processInput = process.getOutputStream()) {
    processInput.write(input);
    processInput.flush();
}
~~~

Đóng stream báo cho tiến trình con biết input đã kết thúc (EOF). Nếu không đóng, command đọc đến EOF có thể chờ mãi và test bị treo.

Kiểm tra:

- Input rỗng.
- Một dòng và nhiều dòng.
- Dòng cuối có hoặc không có newline.
- Dữ liệu tiếng Việt UTF-8.
- Input lớn hơn kích thước buffer thông thường.
- Input không hợp lệ hoặc kết thúc giữa một bản ghi.
- Command báo lỗi và trả mã khác 0 khi dữ liệu không hợp lệ.

Nếu command không hỗ trợ stdin, đừng gửi dữ liệu giả định và mong Spring Shell tự chuyển nó thành argument. Hãy kiểm thử đúng hợp đồng input mà command đã công bố.

## 12. Kiểm thử exit code của tiến trình thật

Kiểm tra output không chứng minh process exit code đúng. Hãy khởi chạy artifact bằng **ProcessBuilder**, chờ process kết thúc với timeout rồi đọc **exitValue()**.

Ví dụ JUnit dưới đây chạy JAR từ thư mục staging. System property **app.jar** trỏ đến executable JAR được build; **distribution.dir** trỏ đến thư mục staging đã chứa JAR và file cấu hình bên ngoài:

~~~java
import static org.assertj.core.api.Assertions.assertThat;
import static org.junit.jupiter.api.Assertions.fail;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

class DistributedArtifactTests {

    @TempDir
    Path tempDir;

    @Test
    void packagedCommandReturnsExpectedOutputAndExitCode() throws Exception {
        boolean windows = System.getProperty("os.name")
                .toLowerCase()
                .contains("win");

        Path java = Path.of(
                System.getProperty("java.home"),
                "bin",
                windows ? "java.exe" : "java"
        );
        Path jar = Path.of(System.getProperty("app.jar"))
                .toAbsolutePath()
                .normalize();
        Path distribution = Path.of(System.getProperty("distribution.dir"))
                .toAbsolutePath()
                .normalize();
        Path output = tempDir.resolve("stdout.txt");
        Path errors = tempDir.resolve("stderr.txt");

        ProcessBuilder builder = new ProcessBuilder(
                java.toString(),
                "-Dspring.shell.interactive.enabled=false",
                "-jar",
                jar.toString(),
                "task",
                "list",
                "--status=OPEN"
        );
        builder.directory(distribution.toFile());
        builder.environment().put(
                "SPRING_CONFIG_ADDITIONALLOCATION",
                "optional:file:./config/"
        );
        builder.redirectOutput(output.toFile());
        builder.redirectError(errors.toFile());

        Process process = builder.start();
        boolean finished = process.waitFor(30, TimeUnit.SECONDS);

        if (!finished) {
            process.destroy();
            if (!process.waitFor(2, TimeUnit.SECONDS)) {
                process.destroyForcibly();
                process.waitFor();
            }
            fail("CLI không kết thúc trong thời gian cho phép.");
        }

        String stdout = Files.readString(output, StandardCharsets.UTF_8);
        String stderr = Files.readString(errors, StandardCharsets.UTF_8);

        assertThat(process.exitValue()).isZero();
        assertThat(stdout).contains("OPEN");
        assertThat(stderr).doesNotContain("Exception");
    }
}
~~~

Ví dụ dùng redirect file để test không bị deadlock do pipe stdout/stderr đầy trong lúc test đang chờ process. Nếu cần đọc output trực tiếp từ pipe, phải tiêu thụ stdout và stderr đồng thời trong khi process chạy.

Ví dụ giả định dữ liệu test đã có ít nhất một bản ghi ở trạng thái OPEN. Khi chạy trong CI, truyền **app.jar** và **distribution.dir** vào test task để chúng trỏ đến artifact và staging directory vừa tạo; không dùng đường dẫn JAR cố định từ máy developer.

Để kiểm thử lỗi, chạy command làm phát sinh một lỗi nghiệp vụ đã được định nghĩa và xác nhận:

- Process exit code khác 0.
- Output có thông báo ổn định cho người dùng.
- Không có thông tin nhạy cảm hoặc stack trace ngoài chính sách.
- Không có side effect ngoài dự kiến.

Test process cần chạy trên JAR đã build, không khởi chạy class main bằng test classpath. Nếu test chạy JAR từ thư mục build mà không copy các file staging, vẫn có thể bỏ sót lỗi do cấu trúc phát hành thiếu file.

## 13. Kiểm thử script launcher của gói phân phối

Nếu gói cung cấp wrapper như **run.sh**, **run.cmd** hoặc **run.ps1**, cần kiểm thử wrapper thay vì chỉ kiểm thử lệnh Java tương đương.

Một wrapper Unix đơn giản:

~~~bash
#!/usr/bin/env sh
set -eu

APP_HOME=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
exec java -Dspring.shell.interactive.enabled=false \
  -jar "$APP_HOME/task-cli.jar" "$@"
~~~

Wrapper xác định thư mục chứa chính nó, dùng đường dẫn tuyệt đối đến JAR và chuyển tiếp từng argument. Dấu nháy quanh **APP_HOME** và **"$@"** giữ nguyên đường dẫn có dấu cách và ranh giới argument.

Kiểm thử wrapper với:

- Đường dẫn cài đặt có dấu cách.
- Argument có dấu cách, tiếng Việt và ký tự đặc biệt.
- Java không có trong PATH.
- JAR bị thiếu hoặc không đọc được.
- Process trả mã lỗi khác 0.
- Script được gọi từ một working directory khác.
- Quyền thực thi của file wrapper trên Linux/macOS.
- Line ending và encoding của wrapper trên hệ điều hành đích.

Với Windows, tạo wrapper phù hợp với cách phân phối của ứng dụng và kiểm tra quy tắc quoting của CMD hoặc PowerShell. Không giả định wrapper Bash có thể chạy trực tiếp trên Windows.

## 14. Kiểm thử cấu hình ngoài JAR và biến môi trường

Spring Boot hỗ trợ cấu hình từ file YAML/properties, environment variable, Java system property và command-line property. Cấu hình bên ngoài JAR có thể ghi đè cấu hình đóng gói; vì vậy acceptance test phải xác nhận ứng dụng đang đọc đúng file cấu hình của gói phân phối.

Ví dụ cấu trúc:

~~~text
task-cli/
├── task-cli.jar
└── config/
    └── application.yaml
~~~

Chạy từ thư mục staging với environment variable:

~~~bash
SPRING_CONFIG_ADDITIONALLOCATION=optional:file:./config/ \
SPRING_SHELL_INTERACTIVE_ENABLED=false \
java -jar task-cli.jar task list
~~~

Trong PowerShell:

~~~powershell
$env:SPRING_CONFIG_ADDITIONALLOCATION = "optional:file:./config/"
$env:SPRING_SHELL_INTERACTIVE_ENABLED = "false"
java -jar .\task-cli.jar task list
~~~

Kiểm tra:

1. File cấu hình ngoài JAR được nạp.
2. Giá trị environment có thể override giá trị mặc định đúng như thiết kế.
3. Profile hoặc endpoint được chọn đúng môi trường.
4. Thiếu cấu hình bắt buộc tạo lỗi rõ ràng.
5. Secret không nằm trong archive hoặc log.
6. Chạy từ thư mục khác không vô tình đọc nhầm file cấu hình local.

Khi dùng biến môi trường, Spring Boot chuyển property name bằng cách đổi dấu chấm thành dấu gạch dưới, bỏ dấu gạch ngang và viết hoa. Ví dụ **spring.shell.interactive.enabled** tương ứng **SPRING_SHELL_INTERACTIVE_ENABLED**.

## 15. Kiểm thử đường dẫn và working directory

Các lỗi chỉ xuất hiện sau khi phát hành thường liên quan đến relative path. Ví dụ ứng dụng đọc **./config/data.csv** có thể chạy trong IDE vì working directory là project root, nhưng thất bại khi người dùng chạy JAR từ thư mục Downloads.

Chạy acceptance test từ ít nhất ba vị trí:

1. Thư mục gốc của gói phân phối.
2. Một thư mục khác nhưng gọi JAR bằng đường dẫn tuyệt đối.
3. Một đường dẫn cài đặt chứa dấu cách và ký tự Unicode.

Xác nhận ứng dụng xác định file cấu hình, script và file dữ liệu theo hợp đồng đã công bố. Nếu file được xác định tương đối với working directory, ghi rõ điều đó trong README. Nếu file phải nằm cạnh JAR, hãy tính đường dẫn từ vị trí ứng dụng thay vì dựa vào thư mục hiện tại.

Không chỉ test trên Windows nếu sản phẩm cũng hỗ trợ Linux/macOS. Path separator, quyền file, symlink, case sensitivity và line ending có thể làm thay đổi kết quả.

## 16. Kiểm tra nội dung và tính toàn vẹn của gói

Sau khi build, kiểm tra checksum của artifact để có thể đối chiếu file đã test với file đã phát hành:

~~~bash
sha256sum task-cli.jar
~~~

Trên PowerShell:

~~~powershell
Get-FileHash .\task-cli.jar -Algorithm SHA256
~~~

Lưu checksum cùng release metadata hoặc artifact manifest. Khi upload hoặc copy sang máy test, tính lại checksum để chắc chắn không chạy nhầm một file cũ.

Kiểm tra archive không chứa:

- File cấu hình local có password hoặc token.
- Private key, certificate private hoặc credential của developer.
- Test fixture, file dump hoặc dữ liệu cá nhân.
- Dependency debug hoặc công cụ phát triển không cần trong runtime.
- JAR cũ hoặc plain JAR bị đặt tên giống executable JAR.

Nếu phát hành layered JAR để xây Docker image, vẫn cần kiểm tra và chạy executable JAR cuối cùng. Việc layer archive thành công không chứng minh image hoặc container command đã đúng.

## 17. Ma trận acceptance test trước khi phát hành

Nên ghi kết quả test theo từng artifact version, runtime Java và hệ điều hành:

| Nhóm | Tình huống | Kết quả mong đợi |
|---|---|---|
| Package | Executable JAR có manifest và nested dependencies | Khởi chạy bằng java -jar |
| Runtime | Java version thấp nhất được hỗ trợ | Ứng dụng khởi động thành công |
| Syntax | Command hợp lệ | Command được gọi đúng |
| Syntax | Option dạng dài/ngắn, có/không có dấu bằng | Bind đúng |
| Syntax | Giá trị có dấu cách và dấu nháy | Không bị tách hoặc biến đổi sai |
| Syntax | Argument thiếu, option lạ, quote lỗi | Báo lỗi cú pháp |
| Validation | Giá trị hợp lệ và không hợp lệ | Chỉ giá trị hợp lệ đi vào nghiệp vụ |
| Help | Help toàn cục và theo command | Tài liệu hiển thị đúng |
| Input | File UTF-8 và stdin nếu được hỗ trợ | Đọc đúng nội dung |
| Output | Stdout, stderr và Unicode | Đúng stream, đúng encoding |
| Script | File @script có nhiều command | Thực thi theo thứ tự |
| Script | Script thiếu hoặc không đọc được | Báo lỗi và exit code theo hợp đồng |
| Exit code | Command thành công | 0 |
| Exit code | Lỗi nghiệp vụ | Mã khác 0 theo quy ước |
| Config | File ngoài JAR và environment | Được nạp đúng |
| Path | Working directory thay đổi | Tìm file theo hợp đồng |
| Wrapper | Chạy từ path có dấu cách | Chuyển tiếp argument đúng |
| Cleanup | Command kết thúc hoặc timeout | Process và resource được giải phóng |
| Integrity | Checksum artifact | File được test trùng file phát hành |

Lưu lại phiên bản JAR, checksum, phiên bản Java, hệ điều hành, command test, exit code và kết quả. Báo cáo này giúp tái hiện lỗi khi người dùng báo rằng bản phân phối của họ chạy khác môi trường phát triển.

## 18. Quy trình phát hành đề xuất

~~~mermaid
flowchart TD
    A["Chạy unit và Spring Shell tests"] --> B["Build executable JAR"]
    B --> C["Kiểm tra manifest và BOOT-INF"]
    C --> D["Tạo staging distribution"]
    D --> E["Tính checksum"]
    E --> F["Chạy command syntax tests"]
    F --> G["Kiểm tra input, output và UTF-8"]
    G --> H["Kiểm tra script và config ngoài JAR"]
    H --> I["Kiểm tra process exit code"]
    I --> J{"Tất cả test đạt?"}
    J -->|Không| K["Sửa lỗi và build lại"]
    K --> B
    J -->|Có| L["Đóng gói và phát hành đúng artifact đã test"]
~~~

Quy trình nên chạy trong CI với artifact được lưu lại sau khi acceptance test thành công. Không build lại một artifact khác sau khi test rồi phát hành file mới mà chưa xác minh checksum hoặc chưa chạy lại test.

## 19. Lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Chạy JAR báo thiếu class | Phân phối plain JAR hoặc thiếu dependency runtime | Chọn executable JAR có launcher và BOOT-INF/lib |
| Chạy được trong IDE nhưng không chạy bằng java -jar | IDE bổ sung classpath hoặc config local | Test trong thư mục staging chỉ chứa file phát hành |
| Command không chạy khi truyền arguments | Interactive mode vẫn bật | Đặt spring.shell.interactive.enabled=false |
| Giá trị có dấu cách bị tách | Nhầm quoting của OS với parser Spring Shell | Test riêng REPL, process argv và script |
| Validation khác giữa test và artifact | Thiếu Bean Validation runtime hoặc cấu hình | Kiểm tra dependency và chạy test trên JAR |
| Output tiếng Việt bị lỗi | Encoding file hoặc terminal không tương thích | Dùng UTF-8 và kiểm tra terminal đích |
| Script chạy sai dòng | Line ending, encoding hoặc path tương đối | Test LF/CRLF và working directory |
| Process test bị treo | Interactive runner chờ terminal hoặc stdin chưa đóng | Dùng non-interactive và đóng stdin khi gửi EOF |
| Test treo khi đọc output | Pipe stdout/stderr đầy | Redirect ra file hoặc drain hai stream đồng thời |
| Exit code khác dự kiến | Chỉ test output hoặc không kiểm tra process | Dùng ProcessBuilder và assert exitValue |
| Cấu hình local bị phát hành | Copy nhầm file từ máy developer | Kiểm tra staging và checksum |
| Chạy sai JAR | Plain JAR hoặc artifact cũ cùng tên | Kiểm tra manifest và checksum trước khi test |
| Wrapper lỗi khi path có dấu cách | Không quote APP_HOME hoặc argument | Quote đường dẫn và chuyển tiếp argument theo từng phần tử |

## 20. Checklist ký nhận gói phân phối

- [ ] Đã build đúng executable JAR bằng bootJar hoặc Maven repackage.
- [ ] Đã xác minh manifest, Main-Class, Start-Class và BOOT-INF.
- [ ] Đã chọn đúng artifact, không nhầm plain JAR.
- [ ] Đã kiểm tra runtime Java tối thiểu được hỗ trợ.
- [ ] Đã tạo staging folder chỉ gồm file phân phối.
- [ ] Đã chạy JAR từ thư mục staging ngoài project root.
- [ ] Đã kiểm tra command, option, argument, quoting và help.
- [ ] Đã kiểm tra Bean Validation và lỗi chuyển đổi.
- [ ] Đã kiểm tra interactive mode bằng terminal hoặc PTY.
- [ ] Đã kiểm tra non-interactive command và script @file.
- [ ] Đã kiểm tra stdin nếu command hỗ trợ input stream.
- [ ] Đã kiểm tra stdout, stderr, Unicode và ANSI output.
- [ ] Đã kiểm tra process exit code bằng ProcessBuilder.
- [ ] Đã kiểm tra file cấu hình ngoài JAR và environment.
- [ ] Đã kiểm tra relative path, working directory và wrapper.
- [ ] Đã kiểm tra script trên các hệ điều hành mục tiêu.
- [ ] Đã tính checksum và xác nhận file phát hành trùng file đã test.
- [ ] Đã loại bỏ secret và file chỉ dành cho phát triển khỏi gói.

Gói phân phối chỉ được xem là sẵn sàng khi người dùng có thể chạy chính artifact đó trong môi trường gần với môi trường cài đặt, nhập cú pháp được tài liệu hóa, nhận đúng output và process exit code. Kiểm thử cuối trên staging distribution giúp phát hiện những lỗi mà unit test hoặc IDE không thể nhìn thấy.

## Tài liệu tham khảo

- [Spring Boot 4 — Packaging Executable Archives (Gradle)](https://docs.spring.io/spring-boot/4.0/gradle-plugin/packaging.html) — task bootJar, executable JAR và cấu trúc archive.
- [Spring Boot 4 — Packaging Executable Archives (Maven)](https://docs.spring.io/spring-boot/4.0/maven-plugin/packaging.html) — goal repackage, manifest và executable JAR.
- [Spring Boot — Launching Executable Jars](https://docs.spring.io/spring-boot/specification/executable-jar/launching.html) — Main-Class, Start-Class, launcher và nested dependencies.
- [Spring Boot — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html) — thứ tự cấu hình, environment variable, system property và file bên ngoài JAR.
- [Spring Shell 4 — Execution](https://docs.spring.io/spring-shell/reference/execution.html) — interactive, non-interactive và NonInteractiveShellRunner.
- [Spring Shell 4 — Command Syntax](https://docs.spring.io/spring-shell/reference/commands/syntax.html) — option, argument, quoting, escaping và quy tắc parser.
- [Spring Shell 4 — Option Validation](https://docs.spring.io/spring-shell/reference/commands/validation.html) — Bean Validation trên command parameter.
- [Spring Shell 4 — Testing](https://docs.spring.io/spring-shell/reference/testing.html) — ShellTest, ShellTestClient và kiểm thử command.
- [Spring Shell issue #1391](https://github.com/spring-projects/spring-shell/issues/1391) — lỗi process exit code khi command parser hoặc file script gặp lỗi.
- [Spring Shell pull request #1393](https://github.com/spring-projects/spring-shell/pull/1393) — đề xuất xử lý lỗi parser và lỗi đọc script như command execution failure.
- [Java SE — ProcessBuilder](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ProcessBuilder.html) — khởi chạy process với danh sách argument, working directory, environment và redirect stream.
- [Java SE — Process](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Process.html) — chờ process, timeout, exit value và stream I/O.
