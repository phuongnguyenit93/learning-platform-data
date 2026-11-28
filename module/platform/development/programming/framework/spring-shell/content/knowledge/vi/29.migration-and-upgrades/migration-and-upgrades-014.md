# Chạy bộ kiểm thử hợp đồng CLI trên các script sử dụng thực tế

Một command có thể hoạt động đúng khi được gọi trực tiếp trong test của Spring Shell nhưng vẫn thất bại khi người dùng chạy ứng dụng từ launcher hoặc script triển khai. Nguyên nhân thường nằm ở ranh giới process: script truyền sai arguments, biến môi trường không được chuyển tiếp, working directory khác dự kiến, output bị trộn với log, exit code bị mất hoặc file kết quả được tạo sai vị trí.

Kiểm thử hợp đồng CLI xác minh hành vi mà người dùng, scheduler và script bên ngoài thực sự quan sát được. Thay vì chỉ gọi method Java hoặc mock parser, test khởi chạy artifact qua launcher thật, truyền arguments giống cách vận hành và kiểm tra exit code, stdout, stderr cùng các side effect được cam kết.

Trong module Spring Shell, cách kiểm thử này bổ sung cho các test command ở cấp ứng dụng. Nó đặc biệt hữu ích khi nâng cấp Spring Shell, đổi runner, thay đổi cách parse option, cập nhật launcher hoặc thay đổi quy trình đóng gói.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích hợp đồng công khai của một CLI và vì sao cần kiểm thử qua process thật.
- Phân biệt unit test, Spring Shell command test và end-to-end contract test.
- Chọn các kịch bản đại diện từ script và thao tác vận hành thực tế.
- Khởi chạy launcher bằng ProcessBuilder với từng argument riêng biệt.
- Kiểm tra exit code, stdout, stderr và timeout một cách độc lập.
- Xác minh file đầu ra, nội dung, encoding và đường dẫn được tạo.
- Kiểm thử biến môi trường, profile, working directory và đường dẫn có dấu cách.
- Viết fixture script an toàn, xác định và có thể chạy lặp lại.
- Tránh test phụ thuộc terminal tương tác hoặc dữ liệu production.
- Chạy cùng một contract suite trên Windows, Linux và macOS.
- Phát hiện thay đổi phá vỡ tương thích sau khi nâng cấp Spring Shell.
- Tạo báo cáo lỗi đủ thông tin để xác định hợp đồng nào bị vi phạm.

## 1. Hợp đồng CLI là gì?

Hợp đồng CLI là tập hợp những hành vi bên ngoài mà script, người dùng hoặc hệ thống tự động có thể dựa vào. Hợp đồng này thường ổn định lâu hơn phần triển khai bên trong.

Ví dụ, một công cụ Spring Shell cung cấp command:

~~~text
report export --format csv --output <file>
customer show --id <id>
backend status
~~~

Các script sử dụng thực tế có thể dựa vào những điều sau:

- Tên command và cách viết option.
- Option bắt buộc, option tùy chọn và giá trị mặc định.
- Cách xử lý argument không hợp lệ.
- Exit code cho thành công và thất bại.
- Nội dung output có thể được script phân tích.
- Diagnostic được ghi ra stderr.
- File được tạo, vị trí lưu và định dạng nội dung.
- Cách chọn môi trường qua profile hoặc biến môi trường.
- Hành vi khi chạy từ một working directory khác.
- Thời gian tối đa mà script chờ command hoàn tất.

Một thay đổi nội bộ không làm thay đổi các hành vi này thường không phá hợp đồng. Ngược lại, đổi --output thành --destination, đổi exit code hoặc thêm một dòng banner vào stdout có thể làm hỏng script dù command vẫn chạy thành công.

### 1.1. Ví dụ một hợp đồng có thể kiểm tra

Giả sử script gọi:

~~~bash
./bin/support-cli report export --format csv --output "$TEMP_DIR/customers.csv"
~~~

Hợp đồng có thể quy định:

| Thành phần | Cam kết |
|---|---|
| Command | report export |
| Option | --format csv, --output <path> |
| Thành công | Exit code 0 |
| Output thành công | Một thông báo ngắn có đường dẫn file |
| Error stream | Không có diagnostic khi thành công |
| Side effect | Tạo file CSV tại đúng đường dẫn |
| Nội dung | Có header và dữ liệu theo schema đã công bố |
| Lỗi validation | Exit code khác 0, thông báo lỗi có thể hiểu được |

Hợp đồng không nhất thiết phải cố định toàn bộ câu chữ output. Nếu script chỉ cần kiểm tra file được tạo và exit code, test nên tập trung vào hai điều đó. Chỉ cam kết định dạng stdout khi người dùng thực sự được phép phụ thuộc vào nó.

## 2. Ba tầng kiểm thử bổ sung cho nhau

Không có một loại test duy nhất phù hợp cho mọi lỗi.

| Tầng | Cách thực thi | Điều cần xác minh |
|---|---|---|
| Unit test | Gọi method Java và mock dependency | Quy tắc nghiệp vụ, validation, mapping |
| Spring Shell test | Dùng ShellTestClient hoặc test context | Đăng ký command, parse input, output của shell |
| CLI contract test | Khởi chạy launcher/artifact như process ngoài | Script, arguments, environment, exit code, stdout/stderr, filesystem |

Unit test nhanh và giúp tìm lỗi logic gần nơi phát sinh. Spring Shell test xác nhận command được đăng ký và thực thi theo framework. Contract test đi qua ranh giới process nên có thể phát hiện lỗi mà hai tầng trước không nhìn thấy.

Ví dụ:

- Unit test xác nhận ReportService tạo đúng dữ liệu CSV.
- Spring Shell test xác nhận report export --format csv gọi service và trả output mong đợi.
- Contract test chạy bin/support-cli hoặc support-cli.cmd và xác nhận file CSV thật sự xuất hiện tại đường dẫn script đã truyền.

Không thay tất cả unit test bằng process test. Khởi động JVM và Spring context nhiều lần tốn thời gian hơn. Dùng contract suite cho các đường chạy có giá trị cao, còn chi tiết logic vẫn nên được kiểm tra ở tầng thấp hơn.

## 3. Thu thập các script sử dụng thực tế

Hãy bắt đầu từ các script mà người dùng hoặc hệ thống vận hành đang gọi, chẳng hạn:

- Script xuất báo cáo hằng ngày.
- Script đồng bộ dữ liệu trước giờ làm việc.
- Script kiểm tra trạng thái backend.
- Script tạo hoặc cập nhật tài nguyên.
- Script chạy migration trong pipeline.
- Script gọi CLI trong scheduler hoặc container entrypoint.

Với mỗi script, ghi lại command line sau khi biến đã được mở rộng, working directory, environment variables, profile, timeout, exit code mong đợi và file đầu ra.

Không lấy toàn bộ script nội bộ làm hợp đồng nếu chúng chỉ là chi tiết triển khai có thể thay đổi. Hãy chọn những cách gọi mà người dùng bên ngoài module có thể dựa vào.

### 3.1. Lập bảng inventory

Ví dụ inventory:

| Script | Command | Điều quan trọng nhất | Mức ưu tiên |
|---|---|---|---|
| daily-export.sh | report export | File CSV, schema, exit code | Cao |
| health-check.ps1 | backend status | Exit code và output ngắn | Cao |
| sync-customers.cmd | customer sync | Profile, biến môi trường, lỗi kết nối | Cao |
| cleanup-local.sh | cache clear | Side effect trong thư mục test | Trung bình |

Từ inventory, chọn các ca test đại diện cho từng dạng input và side effect. Không cần chạy mọi tổ hợp option nếu chúng đã được kiểm tra ở tầng parser hoặc unit test.

### 3.2. Giữ lại script làm fixture có kiểm soát

Script có thể được đặt trong thư mục test resources:

~~~text
src/test/resources/cli-contract/
  scripts/
    daily-export.sh
    health-check.ps1
    sync-customers.cmd
  fixtures/
    customers.csv
    invalid-customers.csv
  expected/
    customers-header.txt
~~~

Fixture nên nhỏ, không chứa dữ liệu cá nhân hoặc secret thật. Đặt tên thể hiện mục đích và giữ nội dung đủ nhỏ để reviewer có thể hiểu test đang xác minh điều gì.

Nếu script hiện có chứa token, URL production hoặc đường dẫn cá nhân, hãy thay bằng placeholder và inject giá trị test từ environment hoặc cấu hình test.

## 4. Khởi chạy launcher thật bằng ProcessBuilder

ProcessBuilder cho phép test Java tạo process con với executable và danh sách arguments riêng. Đây là cách phù hợp để kiểm tra JAR hoặc launcher mà người dùng thực sự gọi.

Ví dụ helper chạy JAR, đồng thời redirect output vào hai file để tránh deadlock do pipe buffer:

~~~java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.concurrent.TimeUnit;

record CliResult(int exitCode, String stdout, String stderr, boolean timedOut) {}

final class CliProcess {

    static CliResult run(
            List<String> command,
            Path workingDirectory,
            Map<String, String> environment,
            Path stdoutFile,
            Path stderrFile,
            Duration timeout) throws Exception {

        ProcessBuilder builder = new ProcessBuilder(command);
        builder.directory(workingDirectory.toFile());
        builder.environment().putAll(environment);
        builder.redirectOutput(stdoutFile.toFile());
        builder.redirectError(stderrFile.toFile());

        Process process = builder.start();
        boolean finished = process.waitFor(timeout.toMillis(), TimeUnit.MILLISECONDS);

        if (!finished) {
            process.descendants().forEach(ProcessHandle::destroy);
            process.destroy();
            if (!process.waitFor(500, TimeUnit.MILLISECONDS)) {
                process.descendants().forEach(ProcessHandle::destroyForcibly);
                process.destroyForcibly();
                process.waitFor();
            }
        }

        String stdout = Files.exists(stdoutFile)
                ? Files.readString(stdoutFile, StandardCharsets.UTF_8) : "";
        String stderr = Files.exists(stderrFile)
                ? Files.readString(stderrFile, StandardCharsets.UTF_8) : "";

        return new CliResult(finished ? process.exitValue() : -1,
                stdout, stderr, !finished);
    }
}
~~~

Đoạn code dùng ProcessHandle, có từ Java 9. Nếu project cần hỗ trợ runtime cũ hơn, thay phần dừng process con bằng cơ chế tương thích phù hợp. Khi timeout, helper phải kết thúc process và thu thập output đã ghi được.

Redirect stdout và stderr ra file riêng giúp process tiếp tục ghi mà không bị chặn bởi buffer pipe chưa được đọc. Nếu dùng InputStream thay cho redirect file, phải đọc stdout và stderr đồng thời trong khi process chạy.

### 4.1. Truyền arguments riêng biệt

Không ghép một command line thành chuỗi:

~~~java
// Không nên: tự xử lý quoting cho từng hệ điều hành là dễ sai.
new ProcessBuilder("java -jar support-cli.jar --output C:\\Reports\\daily.csv");
~~~

Hãy truyền mỗi argument thành một phần tử:

~~~java
new ProcessBuilder(
        "java",
        "-jar",
        jar.toString(),
        "report",
        "export",
        "--output",
        output.toString());
~~~

Đường dẫn có dấu cách vẫn là một argument. ProcessBuilder không cần bạn tự thêm dấu nháy vào chuỗi đường dẫn. Việc thêm dấu nháy vào phần tử có thể khiến dấu nháy trở thành ký tự thực trong giá trị nhận được.

### 4.2. Không phụ thuộc PATH ngoài ý muốn

Test nên xác định executable Java đang dùng và artifact cần kiểm thử. Có thể lấy Java home từ system property:

~~~java
Path javaExecutable = Path.of(
        System.getProperty("java.home"),
        "bin",
        isWindows() ? "java.exe" : "java");
~~~

Helper isWindows() phải dựa trên os.name hoặc một abstraction của test harness. Nếu đang kiểm tra chính launcher .cmd hoặc shell script, test phải gọi launcher đó thay vì bỏ qua wrapper và chạy JAR trực tiếp.

## 5. Chạy script thực tế thay vì chỉ gọi JAR

Nếu người dùng vận hành qua bin/support-cli, support-cli.cmd hoặc support-cli.ps1, contract test nên gọi đúng file đó. Nếu chỉ gọi java -jar, test không xác minh được:

- Script tìm JAR tương đối với vị trí nào.
- Arguments có được chuyển tiếp đầy đủ không.
- Working directory có bị thay đổi không.
- Environment variables có được giữ không.
- Exit code của Java có được truyền lại không.
- Script có hoạt động khi đường dẫn chứa khoảng trắng không.

Ví dụ trên Linux/macOS:

~~~java
ProcessBuilder builder = new ProcessBuilder(
        script.toAbsolutePath().toString(),
        "report",
        "export",
        "--format",
        "csv",
        "--output",
        output.toString());
~~~

Script cần executable bit trong checkout hoặc artifact. Nếu test thất bại vì permission, kiểm tra mode 100755 trong Git và cách đóng gói launcher.

Ví dụ trên Windows CMD:

~~~java
ProcessBuilder builder = new ProcessBuilder(
        "cmd.exe",
        "/c",
        launcher.toAbsolutePath().toString(),
        "backend",
        "status");
~~~

Với PowerShell script:

~~~java
ProcessBuilder builder = new ProcessBuilder(
        "powershell.exe",
        "-NoProfile",
        "-NonInteractive",
        "-File",
        script.toAbsolutePath().toString(),
        "backend",
        "status");
~~~

Ví dụ PowerShell trên chỉ minh họa cách gọi trong môi trường CI đã được cấu hình policy phù hợp. Không yêu cầu người dùng production tắt Execution Policy. Trong pipeline thực tế, ưu tiên ký script hoặc dùng chính sách được tổ chức cho phép.

Không gọi một shell wrapper bằng sh -c hoặc cmd /c nếu không cần shell expansion. Gọi executable trực tiếp giúp giảm lớp quoting và tránh một số lỗi injection.

## 6. Kiểm tra exit code

Exit code là tín hiệu quan trọng nhất cho scheduler và pipeline. Script thường dựa vào exit code để quyết định bước tiếp theo:

~~~bash
if ./bin/support-cli backend status; then
  echo "Backend is available"
else
  echo "Backend check failed" >&2
  exit 1
fi
~~~

Test phải xác minh exit code đúng với hợp đồng. Không chỉ kiểm tra output có chữ success.

Ví dụ JUnit:

~~~java
@Test
void successfulHealthCheckReturnsZero() throws Exception {
    CliResult result = runCli("backend", "status");

    assertThat(result.timedOut()).isFalse();
    assertThat(result.exitCode()).isZero();
}
~~~

Với lỗi:

~~~java
@Test
void invalidOptionReturnsNonZero() throws Exception {
    CliResult result = runCli("report", "export", "--unknown-option");

    assertThat(result.timedOut()).isFalse();
    assertThat(result.exitCode()).isNotZero();
    assertThat(result.stderr()).contains("unknown-option");
}
~~~

Chỉ cố định mã exit cụ thể khi đó là một phần hợp đồng được công bố. Nếu hợp đồng chỉ nói thành công là 0 và thất bại là khác 0, test không nên ràng buộc mọi lỗi phải dùng cùng một số.

### 6.1. Đảm bảo launcher truyền lại exit code

Một wrapper có thể vô tình che exit code:

~~~bash
# Không nên: lệnh echo trở thành lệnh cuối và làm thay đổi trạng thái trả về.
java -jar "$APP_JAR" "$@"
echo "Finished"
~~~

Có thể dùng exec:

~~~bash
exec java -jar "$APP_JAR" "$@"
~~~

Với CMD:

~~~bat
java -jar "%APP_JAR%" %*
exit /b %ERRORLEVEL%
~~~

Với PowerShell:

~~~powershell
& java -jar $jarPath @args
exit $LASTEXITCODE
~~~

Contract test qua launcher sẽ phát hiện wrapper trả mã thành công dù Java process đã thất bại.

## 7. Kiểm tra stdout và stderr độc lập

stdout thường dành cho kết quả mà script có thể sử dụng. stderr dành cho diagnostic, cảnh báo hoặc thông báo lỗi. Khi test gộp hai stream, khó xác định ứng dụng có làm bẩn dữ liệu đầu ra hay không.

Ví dụ command xuất CSV có thể cam kết:

- File CSV được ghi vào đường dẫn đã chỉ định.
- stdout chỉ chứa thông báo hoàn tất.
- stderr rỗng khi thành công.
- Lỗi validation được ghi ra stderr.

Test:

~~~java
@Test
void successfulExportKeepsStreamsSeparate() throws Exception {
    CliResult result = runCli(
            "report", "export",
            "--format", "csv",
            "--output", outputFile.toString());

    assertThat(result.exitCode()).isZero();
    assertThat(result.stdout()).contains("Export completed");
    assertThat(result.stderr()).isBlank();
}
~~~

Không nên assert toàn bộ banner hoặc màu ANSI nếu chúng không thuộc hợp đồng. Nếu ứng dụng hỗ trợ terminal màu, test có thể tắt màu bằng cấu hình test hoặc biến môi trường được tài liệu hóa.

Nếu script dùng stdout làm dữ liệu máy đọc được, ví dụ JSON hoặc CSV, không ghi banner, progress bar hoặc log vào cùng stream. Test cần kiểm tra output có parse được bằng parser tương ứng.

## 8. Kiểm tra arguments, quoting và đường dẫn

Các script thực tế thường có đường dẫn chứa khoảng trắng, ký tự Unicode hoặc được tạo từ biến môi trường. Contract suite cần có ít nhất một ca dùng thư mục tạm có tên không đơn giản.

Ví dụ:

~~~java
Path testRoot = Files.createTempDirectory("cli contract ");
Path outputFile = testRoot.resolve("Báo cáo tháng 11.csv");

CliResult result = runCli(
        "report", "export",
        "--format", "csv",
        "--output", outputFile.toString());

assertThat(result.exitCode()).isZero();
assertThat(outputFile).exists();
~~~

Test xác nhận launcher giữ nguyên một argument đường dẫn. Nếu wrapper tự ghép command line hoặc không quote đúng, output có thể bị tạo ở vị trí sai hoặc command báo thiếu option.

Các ca nên có:

- Đường dẫn tuyệt đối.
- Đường dẫn tương đối theo working directory.
- Đường dẫn có dấu cách.
- Đường dẫn có ký tự Unicode.
- Đường dẫn không tồn tại hoặc thư mục cha không có quyền ghi.
- Giá trị option bắt đầu bằng dấu gạch ngang nếu cú pháp cho phép.

Không giả định mọi filesystem phân biệt chữ hoa/chữ thường như nhau. Tên file cần kiểm thử theo nền tảng hỗ trợ và hợp đồng sản phẩm.

## 9. Kiểm tra side effect trên filesystem

Exit code 0 không chứng minh command tạo đúng file. Khi command tạo hoặc cập nhật tài nguyên, test cần xác minh side effect có thể quan sát được.

Ví dụ kiểm tra CSV:

~~~java
assertThat(outputFile).exists();
assertThat(Files.size(outputFile)).isGreaterThan(0);

List<String> lines = Files.readAllLines(
        outputFile,
        StandardCharsets.UTF_8);

assertThat(lines.get(0)).isEqualTo("id,name,status");
~~~

Kiểm tra thêm:

- Encoding đúng như hợp đồng.
- Header và cột đúng thứ tự.
- Số lượng record đúng.
- Không tạo file phụ ngoài thư mục được phép.
- File tạm được dọn khi command thất bại.
- Lần chạy thứ hai có hành vi được định nghĩa: ghi đè, từ chối hoặc tạo file mới.

Nếu command thay đổi trạng thái backend, dùng test database hoặc stub server trong môi trường cô lập và kiểm tra trạng thái sau process. Không gọi endpoint production trong contract suite.

## 10. Kiểm tra environment, profile và working directory

Một script có thể dựa vào environment variable để chọn profile hoặc endpoint. Test nên tạo environment map riêng cho process con:

~~~java
ProcessBuilder builder = new ProcessBuilder(command);
builder.environment().put("SPRING_PROFILES_ACTIVE", "test");
builder.environment().put("SUPPORT_BACKEND_BASEURL", "http://127.0.0.1:18081");
builder.directory(testWorkingDirectory.toFile());
~~~

Không thay đổi environment toàn cục của test JVM nếu chỉ một process cần giá trị riêng. Mỗi test nên tự thiết lập environment và working directory để không ảnh hưởng test khác.

Kiểm thử các trường hợp:

- Không đặt profile và dùng default profile đã công bố.
- Đặt profile test.
- Đặt biến môi trường ghi đè cấu hình file.
- Biến môi trường bị thiếu.
- Working directory khác thư mục chứa launcher.
- Config file ngoài tồn tại hoặc bị thiếu theo chính sách.

Không đưa secret thật vào environment của CI. Dùng token giả hoặc secret tạm do test tạo và hủy sau khi chạy.

## 11. Timeout và dọn process

Process test phải có timeout hữu hạn. Nếu command treo do chờ input, deadlock hoặc dependency không phản hồi, test suite không được chờ vô hạn.

Khi timeout:

1. Ghi nhận test đã timeout.
2. Gửi terminate signal hoặc destroy process.
3. Chờ một khoảng ngắn để process thoát.
4. Nếu vẫn chạy, buộc kết thúc process.
5. Thu thập stdout/stderr đã ghi được.
6. Báo command line và working directory đã dùng.

Nếu ứng dụng tạo process con, chỉ dừng process cha có thể để lại process mồ côi. Trên Java có thể duyệt ProcessHandle.descendants() và dừng các process con trong fixture test nếu kiến trúc runner yêu cầu.

Không dùng timeout quá dài để che lỗi treo. Chọn timeout phù hợp với tác vụ trong môi trường CI và đặt timeout ở cả tầng test framework lẫn process.

## 12. Xử lý output lớn và deadlock pipe

Mỗi process có buffer hữu hạn cho stdout và stderr. Nếu test không đọc stream trong khi process ghi nhiều dữ liệu, buffer có thể đầy. Process bị chặn khi ghi và test lại đang chờ process kết thúc: đây là deadlock.

Không dùng cách:

~~~java
process.waitFor();
String stdout = new String(process.getInputStream().readAllBytes());
~~~

cho một command có thể ghi nhiều output.

Các lựa chọn:

- Đọc stdout và stderr đồng thời bằng hai task riêng.
- Redirect từng stream vào file tạm riêng rồi đọc sau.
- Dùng redirectErrorStream(true) nếu hợp đồng không cần phân biệt hai stream.
- Giới hạn output trong test fixture nếu chỉ kiểm tra command nhỏ.

Ví dụ redirect:

~~~java
Path stdoutFile = tempDirectory.resolve("stdout.log");
Path stderrFile = tempDirectory.resolve("stderr.log");

ProcessBuilder builder = new ProcessBuilder(command);
builder.redirectOutput(stdoutFile.toFile());
builder.redirectError(stderrFile.toFile());

Process process = builder.start();
~~~

Sau khi process kết thúc, đọc hai file bằng UTF-8 theo hợp đồng output. Với test cần xác minh stdout/stderr không bị trộn, luôn redirect riêng.

## 13. Kiểm thử interactive script

Một số script mở shell tương tác, gửi nhiều command hoặc trả lời prompt. Đây là dạng test phức tạp hơn process test một lần gọi.

Trước khi viết test, xác định liệu hợp đồng có thật sự yêu cầu interactive session hay không. Nếu script chỉ gọi command một lần, ưu tiên non-interactive invocation để giảm tính không xác định.

Với interactive script:

- Cấp input qua stdin hoặc test harness phù hợp.
- Không dùng sleep cố định để đoán prompt đã xuất hiện.
- Đợi prompt hoặc marker output bằng điều kiện có timeout.
- Gửi input theo đúng thứ tự.
- Kiểm tra trạng thái cuối cùng và exit code.
- Đóng stdin để ứng dụng biết không còn input.
- Đảm bảo terminal mode không bị kẹt sau test.

Không giả định ProcessBuilder tự cung cấp pseudo-terminal. Một số hành vi như password echo suppression, line editing hoặc JLine terminal detection có thể khác khi stdin/stdout là pipe thay vì TTY. Nếu cần xác minh trải nghiệm terminal thật, dùng môi trường pseudo-terminal phù hợp cho nền tảng CI hoặc kiểm tra thủ công trong release qualification.

Spring Shell có test API ở cấp ứng dụng để kiểm tra interactive session và input. Dùng các test này để xác minh prompt, completion và xử lý input bên trong shell; vẫn cần ít nhất một process contract test để xác minh launcher mà script thực tế gọi.

## 14. Tạo contract suite với JUnit

Một cách tổ chức đơn giản là tạo lớp test chuyên biệt:

~~~java
@Tag("cli-contract")
class SupportCliContractTests {

    @Test
    void helpCommandIsAvailable() throws Exception {
        CliResult result = runCli("help");

        assertThat(result.timedOut()).isFalse();
        assertThat(result.exitCode()).isZero();
        assertThat(result.stdout()).contains("AVAILABLE COMMANDS");
    }

    @Test
    void missingRequiredOptionFails() throws Exception {
        CliResult result = runCli("report", "export");

        assertThat(result.timedOut()).isFalse();
        assertThat(result.exitCode()).isNotZero();
        assertThat(result.stderr()).contains("output");
    }

    @Test
    void exportCreatesCsvAtRequestedPath() throws Exception {
        Path output = tempDirectory.resolve("report output.csv");

        CliResult result = runCli(
                "report", "export",
                "--format", "csv",
                "--output", output.toString());

        assertThat(result.timedOut()).isFalse();
        assertThat(result.exitCode()).isZero();
        assertThat(output).exists();
        assertThat(Files.size(output)).isPositive();
    }
}
~~~

Các method runCli() và tempDirectory là fixture của test suite, không phải API của Spring Shell. Có thể dùng JUnit @TempDir để tạo thư mục riêng cho từng test và xóa tự động sau khi test kết thúc.

Tách tag giúp chạy riêng:

~~~bash
./mvnw -Dgroups=cli-contract verify
~~~

hoặc cấu hình task/tag tương ứng với build tool của dự án. Không giả định tên profile Maven/Gradle có sẵn; hãy khai báo test task/tag trong build configuration của repository.

## 15. Dùng Spring Shell test API ở tầng command

Spring Shell 4.x có @ShellTest, ShellTestClient và ShellAssertions để kiểm tra command mà không phải khởi chạy executable ngoài cho mọi test.

Ví dụ:

~~~java
@ShellTest
class ReportCommandTests {

    @Autowired
    ShellTestClient client;

    @Test
    void reportHelpIsAvailable() throws Exception {
        ShellScreen screen = client.sendCommand("help");

        ShellAssertions.assertThat(screen)
                .containsText("AVAILABLE COMMANDS");
    }
}
~~~

Test này kiểm tra command ở trong Spring Shell context. Nó không xác minh wrapper .sh, .cmd hoặc .ps1, không kiểm tra cách wrapper truyền exit code và không chứng minh artifact đã được đóng gói đúng.

Kết hợp hai tầng:

1. Shell test cho command registration, parsing và output nội bộ.
2. Contract test cho launcher, process arguments, environment, exit status và side effect.

Không dùng process test để thay thế toàn bộ test của ShellTestClient, vì mỗi process test cần khởi động JVM và Spring context mới.

## 16. Kiểm tra tương thích khi nâng cấp Spring Shell

Khi nâng cấp Spring Shell, các thay đổi có thể ảnh hưởng đến hợp đồng script:

- Tên command hoặc alias.
- Cách parse option và argument.
- Giá trị mặc định.
- Cách báo lỗi khi thiếu option.
- Runner interactive/non-interactive.
- Cách hiển thị help.
- Exit code khi command thất bại.
- Output hoặc diagnostic.
- Cách ứng dụng nhận environment/profile.

Trước khi nâng cấp, chạy contract suite trên phiên bản hiện tại và lưu kết quả baseline. Sau khi nâng cấp, chạy lại cùng các script và fixture.

Không cập nhật snapshot chỉ để làm test xanh. Khi có khác biệt:

1. Xác định khác biệt có chủ đích hay ngoài ý muốn.
2. Kiểm tra script thực tế có phụ thuộc vào hành vi cũ không.
3. Nếu thay đổi hợp đồng, cập nhật tài liệu và migration note.
4. Nếu thay đổi không được mong đợi, sửa implementation hoặc launcher.
5. Giữ lại test để ngăn regression.

### 16.1. So sánh output có chọn lọc

Output có thể chứa timestamp, thời gian thực thi hoặc đường dẫn tạm. Không snapshot toàn bộ output nếu những phần đó không ổn định.

Có thể kiểm tra marker và cấu trúc:

~~~java
assertThat(result.stdout())
        .contains("Export completed")
        .contains("records:");
~~~

Với JSON, parse và so sánh field thay vì so sánh chuỗi thô. Với CSV, parse header và record thay vì chỉ kiểm tra file có tồn tại.

Nếu output chính là giao diện máy đọc được, ví dụ JSON/CSV trên stdout, khi đó có thể so sánh cấu trúc hoặc canonicalized representation theo schema đã công bố.

## 17. Ma trận kiểm thử đa nền tảng

Nếu Spring Shell CLI tuyên bố hỗ trợ Windows, Linux và macOS, cần chạy launcher tương ứng trên từng hệ điều hành.

| Hạng mục | Windows | Linux | macOS |
|---|---|---|---|
| Launcher | .cmd hoặc .ps1 | .sh | .sh |
| Shell invocation | cmd.exe/PowerShell | Bash/POSIX shell | Bash/zsh |
| Argument có dấu cách | Kiểm tra quoting Windows | Kiểm tra "$@" | Kiểm tra "$@" |
| Exit code | %ERRORLEVEL%/$LASTEXITCODE | $? | $? |
| Working directory | Drive/path Windows | Path POSIX | Path POSIX |
| Line ending | CRLF cho batch | LF cho shell | LF cho shell |
| Permission | Execution policy/file type | Git mode/chmod | Git mode/chmod |
| Encoding | Console và file output | UTF-8 | UTF-8 |
| Unicode path | Tên thư mục có dấu | Tên thư mục có dấu | Tên thư mục có dấu |

CI nên dùng runner native cho mỗi OS. Test Windows chạy trên Bash giả lập không thay thế được test launcher CMD/PowerShell; tương tự, test Linux không chứng minh shell script tương thích macOS.

Nếu một nền tảng không nằm trong phạm vi hỗ trợ, ghi rõ trong tài liệu phát hành thay vì để người dùng tự suy đoán.

## 18. Tránh các test không xác định

Contract test thường thất bại ngẫu nhiên nếu phụ thuộc môi trường ngoài hoặc dữ liệu thay đổi.

Các nguyên tắc:

- Dùng fixture dữ liệu cố định.
- Dùng thư mục tạm riêng cho mỗi test.
- Không gọi API production.
- Không phụ thuộc thứ tự test.
- Không dùng port cố định nếu có thể cấp port động.
- Không dựa vào đồng hồ hệ thống hoặc timestamp chính xác.
- Đặt timeout hữu hạn.
- Thu thập output và diagnostic khi lỗi.
- Dọn process con, file tạm và server giả sau test.
- Kiểm soát locale, timezone và profile.

Nếu command gọi backend, dùng test server hoặc container được quản lý trong CI. Chỉ dùng mock HTTP ở tầng phù hợp; contract test process nên vẫn đi qua HTTP thật trong môi trường cô lập nếu HTTP là một phần hành vi mà script phụ thuộc.

Không retry test thất bại một cách mặc định để che flaky behavior. Retry có thể hữu ích cho một số dependency bên ngoài, nhưng cần ghi nhận lần thất bại đầu tiên và nguyên nhân.

## 19. Báo lỗi contract test có thể hành động

Khi test thất bại, cần cung cấp đủ thông tin để tái hiện:

- Command executable và arguments.
- Working directory.
- Environment variables đã đặt, ngoại trừ secret.
- Exit code hoặc trạng thái timeout.
- stdout và stderr.
- Đường dẫn file dự kiến.
- Trạng thái file thực tế.
- OS, JDK và phiên bản Spring Shell đang được kiểm thử.

Không in toàn bộ environment vì có thể chứa credential. Dùng allowlist tên biến được phép hiển thị và thay secret bằng <redacted>.

Ví dụ thông báo lỗi:

~~~text
CLI contract failed: report export
OS: Linux
JDK: 21
Working directory: /tmp/cli-contract-381
Command: bin/support-cli report export --format csv --output "/tmp/cli-contract-381/report output.csv"
Expected exit code: 0
Actual exit code: 2
Timed out: false
stdout:
Export started
stderr:
Cannot create output file: permission denied
Expected file:
/tmp/cli-contract-381/report output.csv
~~~

Thông tin này giúp phân biệt lỗi parser, lỗi permission, lỗi launcher và lỗi service.

## 20. Một quy trình contract test hoàn chỉnh

Một test cho script xuất báo cáo có thể đi theo trình tự:

~~~mermaid
flowchart TD
    A[Chuẩn bị artifact và script] --> B[Tạo temp directory]
    B --> C[Thiết lập environment và working directory]
    C --> D[Khởi chạy launcher thật]
    D --> E{Process kết thúc trước timeout?}
    E -- Không --> F[Terminate process và thu diagnostics]
    E -- Có --> G[Đọc exit code, stdout, stderr]
    G --> H{Exit code đúng?}
    H -- Không --> I[Test thất bại với process details]
    H -- Có --> J[Kiểm tra file và nội dung]
    J --> K{Side effect đúng?}
    K -- Không --> I
    K -- Có --> L[Contract test PASS]
~~~

Thứ tự này giúp test kiểm tra cả kết quả process lẫn side effect. Không dừng ở exit code 0 nếu hợp đồng còn cam kết file hoặc trạng thái dữ liệu.

## 21. Checklist trước khi merge hoặc phát hành

- [ ] Đã liệt kê script và command line được sử dụng thực tế.
- [ ] Đã xác định phần nào là hợp đồng công khai.
- [ ] Có unit test cho logic nghiệp vụ.
- [ ] Có Spring Shell test cho command registration và parsing.
- [ ] Contract test chạy launcher hoặc script thật.
- [ ] Arguments được truyền thành từng phần tử riêng.
- [ ] Exit code thành công và thất bại được xác minh.
- [ ] stdout và stderr được kiểm tra riêng.
- [ ] Có timeout hữu hạn và cleanup process.
- [ ] Output file được kiểm tra cả vị trí, encoding và schema.
- [ ] Có test path chứa dấu cách và Unicode.
- [ ] Có test working directory và environment/profile.
- [ ] Không sử dụng secret hoặc dữ liệu production.
- [ ] Có kiểm thử cho script interactive nếu đó là hợp đồng được hỗ trợ.
- [ ] Artifact được chạy sau khi đóng gói/giải nén.
- [ ] CI chạy trên mọi hệ điều hành được công bố hỗ trợ.
- [ ] Output động được so sánh có chọn lọc.
- [ ] Diagnostics không làm lộ environment secret.
- [ ] Khác biệt sau nâng cấp được đánh giá trước khi cập nhật baseline.

## 22. Tự kiểm tra

**Câu 1.** Vì sao gọi trực tiếp method command không đủ để kiểm tra hợp đồng của script?

**Gợi ý trả lời:** Nó bỏ qua launcher, process arguments, working directory, environment, exit code và filesystem mà script thực sự tương tác.

**Câu 2.** Khi nào nên gọi launcher thật thay vì gọi JAR bằng ProcessBuilder?

**Gợi ý trả lời:** Khi launcher là entrypoint được người dùng hoặc scheduler sử dụng và việc chuyển tiếp arguments, environment, working directory hoặc exit status là một phần hợp đồng.

**Câu 3.** Vì sao nên giữ stdout và stderr riêng?

**Gợi ý trả lời:** stdout có thể là dữ liệu cho script tiêu thụ; stderr dành cho diagnostic. Gộp chúng có thể làm bẩn output máy đọc được và che lỗi phân luồng.

**Câu 4.** Vì sao ProcessBuilder nên nhận một list arguments?

**Gợi ý trả lời:** Mỗi phần tử giữ nguyên ranh giới argument, tránh lỗi quoting và giảm nguy cơ injection khi đường dẫn hoặc giá trị chứa khoảng trắng.

**Câu 5.** Exit code 0 có đủ chứng minh lệnh export thành công không?

**Gợi ý trả lời:** Không nếu hợp đồng còn yêu cầu file phải được tạo, đúng vị trí, encoding và schema. Phải kiểm tra side effect.

**Câu 6.** Vì sao test cần timeout và cleanup process?

**Gợi ý trả lời:** Command có thể treo vì prompt, deadlock hoặc dependency. Timeout và cleanup ngăn test suite bị kẹt và để lại process mồ côi.

**Câu 7.** Contract test và Spring Shell test API khác nhau ở đâu?

**Gợi ý trả lời:** Spring Shell test API kiểm tra command trong context; contract test khởi chạy executable/launcher thật để kiểm tra ranh giới process và script.

**Câu 8.** Vì sao phải chạy test trên từng OS được hỗ trợ?

**Gợi ý trả lời:** Launcher, shell quoting, line ending, permission, path và console khác nhau giữa Windows, Linux và macOS.

## Kết luận

Kiểm thử hợp đồng CLI xác nhận công cụ Spring Shell hoạt động đúng theo cách script và người dùng thực sự gọi nó. Hãy bắt đầu từ script sử dụng thực tế, xác định command line và các cam kết về exit code, output, environment, working directory cùng side effect. Dùng Spring Shell test cho command ở trong context và dùng process contract test để chạy launcher hoặc artifact thật.

Một contract suite đáng tin cậy phải truyền arguments đúng ranh giới, kiểm tra stdout/stderr riêng, có timeout, dọn process và xác minh file hoặc trạng thái được tạo. Chạy suite trên mọi hệ điều hành đã công bố hỗ trợ và so sánh hành vi trước/sau khi nâng cấp. Khi hợp đồng được kiểm tra tự động, thay đổi framework hoặc launcher sẽ dễ phát hiện regression trước khi script vận hành thật bị ảnh hưởng.

## Tài liệu tham khảo

- [Spring Shell 4.0.3 — Testing](https://docs.spring.io/spring-shell/reference/testing.html)
- [Spring Shell 4.0.3 — ShellTestClient API](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/test/ShellTestClient.html)
- [Spring Shell 4.0.3 — ShellAssertions API](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/test/ShellAssertions.html)
- [Java SE 21 — ProcessBuilder API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ProcessBuilder.html)
- [Java SE 21 — Process API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Process.html)
- [JUnit 5 — User Guide](https://junit.org/junit5/docs/current/user-guide/)
- [Git — gitattributes and line endings](https://git-scm.com/docs/gitattributes.html)
