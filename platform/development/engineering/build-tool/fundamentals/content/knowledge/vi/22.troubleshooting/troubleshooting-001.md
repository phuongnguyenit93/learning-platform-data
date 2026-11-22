# Đọc mã thoát, thông báo lỗi gốc và chuỗi nguyên nhân

Khi một lệnh Gradle kết thúc, terminal hoặc hệ thống CI nhận được **mã thoát** (process exit code) của tiến trình Gradle. Mã này cho biết lệnh build thành công hay thất bại ở cấp tiến trình. Nó không mô tả chi tiết lỗi là do biên dịch, dependency, kiểm thử, cấu hình hay môi trường.

Để tìm nguyên nhân, cần đọc nhiều lớp thông tin cùng nhau: mã thoát, dòng Gradle báo task thất bại, phần **What went wrong**, vị trí lỗi và chuỗi exception gồm **Caused by** hoặc **Suppressed**. Thông báo như **Execution failed for task** thường chỉ cho biết task nào thất bại; nguyên nhân cụ thể có thể nằm sâu hơn trong compiler output, lỗi kết nối, lỗi cấu hình hoặc exception gốc.

Bài này hướng dẫn cách đọc các dấu hiệu đó theo thứ tự, cách lấy thêm thông tin bằng tùy chọn Gradle, và cách chuyển kết quả thành bước điều tra có thể tái hiện trên máy phát triển hoặc CI.

## 1. Mã thoát là gì?

Mã thoát là một số nguyên mà tiến trình trả về cho hệ điều hành khi kết thúc. Shell hoặc hệ thống CI dùng mã này để quyết định bước tiếp theo.

Quy ước phổ biến:

- **0**: tiến trình hoàn thành thành công.
- **Khác 0**: tiến trình báo lỗi hoặc không hoàn thành theo yêu cầu.

Với Gradle, một build thành công thường trả về mã 0. Khi build thất bại, Gradle trả về mã khác 0, thường là 1. Không nên dựa vào một mã số cụ thể để phân biệt mọi loại lỗi Gradle; không có một bảng mã thoát ổn định kiểu “mã 2 là lỗi dependency, mã 3 là lỗi compile” cho mọi trường hợp.

Ví dụ:

~~~text
BUILD SUCCESSFUL in 4s
5 actionable tasks: 5 executed
Process finished with exit code 0
~~~

Và khi build thất bại:

~~~text
BUILD FAILED in 2s
3 actionable tasks: 2 executed, 1 failed
Process finished with exit code 1
~~~

Dòng **Process finished with exit code** có thể do IDE, terminal hoặc runner hiển thị. Còn **BUILD SUCCESSFUL** hoặc **BUILD FAILED** là thông báo kết quả do Gradle in ra.

Mã thoát là tín hiệu tổng quát cho shell/CI. Muốn biết thất bại ở đâu, cần đọc log và exception.

## 2. Mã thoát của Gradle khác trạng thái của task

Một build gồm nhiều task. Mỗi task có thể có trạng thái như:

| Task outcome | Ý nghĩa |
|---|---|
| **SUCCESS** hoặc không có hậu tố đặc biệt | Task action đã chạy và hoàn thành |
| **UP-TO-DATE** | Output hiện tại hợp lệ, không cần chạy action |
| **FROM-CACHE** | Output được khôi phục từ build cache |
| **NO-SOURCE** | Task được chọn nhưng không có source phù hợp |
| **SKIPPED** | Task được chọn nhưng action bị bỏ qua theo điều kiện |
| **FAILED** | Task thực thi thất bại |

Các trạng thái trên không phải mã thoát của tiến trình. Một task có thể là UP-TO-DATE trong khi toàn build vẫn thành công với mã 0. Một task có thể là SKIPPED nhưng build vẫn thành công. Nếu một task bắt buộc thất bại và lỗi không được xử lý, Gradle thường kết thúc build với mã khác 0.

Ngoài ra, build có thể thất bại trước khi bất kỳ task nào chạy, ví dụ settings script hoặc build script không biên dịch được, plugin không tìm thấy, hoặc dependency không phân giải được trong giai đoạn cấu hình.

Do đó, đừng kết luận loại lỗi chỉ từ mã thoát hoặc từ số task đã thực thi.

## 3. Shell và CI lấy mã thoát như thế nào?

Mã thoát cần được đọc ngay sau khi chạy lệnh Gradle. Nếu chạy thêm lệnh khác trước, biến trạng thái của shell có thể đã thay đổi.

### Bash hoặc shell tương tự

~~~bash
./gradlew build
status=$?

if [ "$status" -eq 0 ]; then
    echo "Build succeeded"
else
    echo "Build failed with exit code $status"
fi
~~~

Trong Bash, biến **$?** chứa mã thoát của lệnh gần nhất. Hãy gán nó ngay sau lệnh Gradle.

Nếu chuyển output qua pipe:

~~~bash
set -o pipefail
./gradlew build 2>&1 | tee build.log
status=$?
~~~

**pipefail** giúp pipeline trả về lỗi của một lệnh trong pipe thay vì chỉ phản ánh trạng thái của lệnh cuối. Nếu không bật pipefail, việc dùng tee có thể khiến script hiểu nhầm pipeline thành công dù Gradle thất bại.

### PowerShell trên Windows

~~~powershell
.\gradlew.bat build
$gradleExitCode = $LASTEXITCODE

if ($gradleExitCode -eq 0) {
    Write-Host "Build succeeded"
}
else {
    Write-Host "Build failed with exit code $gradleExitCode"
}
~~~

Với chương trình native như gradlew.bat, **$LASTEXITCODE** giữ mã thoát của tiến trình. Biến **$?** chỉ thể hiện trạng thái thành công/thất bại của lệnh PowerShell gần nhất, không thay thế cho mã số chi tiết.

### Command Prompt trên Windows

~~~bat
call gradlew.bat build
echo %ERRORLEVEL%
~~~

**%ERRORLEVEL%** chứa mã thoát của lệnh vừa chạy. Từ batch script, có thể dùng giá trị này để quyết định có tiếp tục các bước đóng gói hoặc phát hành hay không.

### Trong CI

Hầu hết CI runner coi process exit code khác 0 là một bước thất bại. Vì vậy, không nên bắt lỗi rồi trả về 0 nếu build thực tế thất bại, trừ khi pipeline có chủ đích xử lý lỗi và ghi nhận kết quả riêng.

Ví dụ, một script chạy Gradle rồi tiếp tục upload artifact dù build lỗi có thể làm pipeline báo xanh sai hoặc phát hành artifact cũ. Hãy giữ nguyên mã thoát của Gradle cho bước kiểm tra bắt buộc.

## 4. Đọc phần kết quả cuối của Gradle

Một log thất bại thường có dạng:

~~~text
> Task :app:compileJava FAILED

FAILURE: Build failed with an exception.

* What went wrong:
Execution failed for task ':app:compileJava'.
> Compilation failed; see the compiler output below.

* Try:
> Run with --stacktrace option to get the stack trace.
> Run with --info or --debug option to get more log output.
> Run with --scan to get full insights.

BUILD FAILED in 3s
~~~

Đọc theo thứ tự:

1. **Task path**: task nào thất bại, ví dụ **:app:compileJava**.
2. **What went wrong**: mô tả trực tiếp của Gradle về lỗi.
3. **Thông báo chi tiết phía dưới**: compiler, plugin hoặc thư viện có thể cung cấp lỗi cụ thể.
4. **Try**: gợi ý tùy chọn để lấy thêm thông tin.
5. **BUILD FAILED**: kết quả tổng thể của build.

Dòng **Execution failed for task** là thông tin quan trọng nhưng thường là lớp bọc của Gradle. Nó chưa chắc là nguyên nhân cuối cùng. Với lỗi biên dịch, thông tin hữu ích có thể nằm ở các dòng compiler diagnostic trước phần tổng kết. Với lỗi runtime hoặc plugin, nguyên nhân có thể nằm trong stack trace.

## 5. Phân biệt thông báo tổng quát và lỗi gốc

Ví dụ:

~~~text
Execution failed for task ':app:runIntegrationTest'.
> There were failing tests. See the report at: ...

OrderRepositoryIntegrationTest > connectsToDatabase FAILED
    java.net.ConnectException: Connection refused
~~~

Thông báo tổng quát là task integration test thất bại vì có test không qua. Nguyên nhân có thể là test không kết nối được database.

Nếu chỉ xử lý dòng **Execution failed for task**, ta biết task nào thất bại nhưng chưa biết phải sửa gì. Cần tìm diagnostic gần nhất có thể hành động:

- Test nào thất bại?
- Test đang kết nối host và port nào?
- Database có đang chạy không?
- Credential, network hoặc container có đúng không?
- Lỗi xuất hiện trước hay sau khi test gửi request?

Một ví dụ khác:

~~~text
Execution failed for task ':app:compileJava'.
> Compilation failed

/path/to/Main.java:18: error: cannot find symbol
    Customer customer = new Customer();
    ^
  symbol:   class Customer
  location: class Main
~~~

Ở đây, compiler diagnostic mới là thông tin cụ thể: không tìm thấy kiểu Customer tại dòng 18. Có thể thiếu import, source không nằm trong source set, project dependency chưa được khai báo hoặc class không có trên compile classpath.

Nguyên tắc là tìm thông báo đầu tiên chỉ ra điều kiện kỹ thuật bị vi phạm, rồi lần theo thông tin dẫn đến nó.

## 6. Exception chain và ý nghĩa của Caused by

Java exception có thể bọc một exception khác. Exception bên ngoài mô tả ngữ cảnh mà một lớp xử lý phát hiện lỗi; exception bên trong cho biết nguyên nhân được ném ra ở lớp thấp hơn.

Ví dụ:

~~~text
org.gradle.api.tasks.TaskExecutionException:
Execution failed for task ':app:run'.

Caused by: org.gradle.process.internal.ExecException:
Process 'command ...' finished with non-zero exit value 1

Caused by: java.net.ConnectException:
Connection refused
~~~

Có thể đọc chuỗi như sau:

- **TaskExecutionException**: Gradle báo task thất bại.
- **ExecException**: task chạy một tiến trình con và tiến trình đó trả về mã khác 0.
- **ConnectException**: chương trình con không kết nối được tới dịch vụ đích.

Trong ví dụ này, lỗi kết nối là nguyên nhân sâu nhất được hiển thị. Tuy nhiên, không phải lúc nào dòng Caused by cuối cùng cũng là điều duy nhất cần sửa. Cần đọc cả ngữ cảnh của các lớp bọc và thông tin ở task hoặc plugin.

### Root cause là gì?

Root cause là nguyên nhân nền tảng giải thích vì sao chuỗi thao tác thất bại. Trong exception chain, nó thường xuất hiện ở cause sâu nhất, nhưng có trường hợp exception gốc không được giữ lại hoặc lỗi được biểu diễn bằng diagnostic riêng thay vì exception.

Ví dụ:

- Compiler báo thiếu symbol: lỗi gốc là kiểu hoặc member không được resolve.
- HTTP request trả 401: lỗi gốc có thể là credential hoặc quyền truy cập.
- Database connection refused: dịch vụ không lắng nghe tại địa chỉ/port hoặc kết nối bị từ chối.
- NoSuchMethodError: runtime đang nạp phiên bản class không có method mà bytecode cần.
- Could not find plugin: plugin ID, version, repository hoặc plugin management configuration không phù hợp.

Không nên sửa exception wrapper ở tầng trên nếu nguyên nhân thật nằm ở cấu hình hoặc dependency phía dưới.

## 7. Caused by khác Suppressed như thế nào?

Java Throwable có thể chứa:

- **Cause**: exception gây ra exception hiện tại.
- **Suppressed exceptions**: exception phát sinh trong quá trình xử lý hoặc dọn dẹp một lỗi khác.

Ví dụ:

~~~java
try {
    useResource();
} catch (Exception primary) {
    throw new IllegalStateException("Operation failed", primary);
}
~~~

Exception gốc được gắn làm cause của IllegalStateException.

Với try-with-resources, nếu thân khối try đã ném exception và thao tác close cũng thất bại, exception khi close có thể được gắn vào danh sách suppressed để không che mất lỗi chính.

Khi đọc stack trace:

- **Caused by** thường giúp lần xuống nguyên nhân của exception hiện tại.
- **Suppressed** thường là lỗi phụ xảy ra trong lúc xử lý hoặc dọn dẹp.
- Không nên bỏ qua suppressed nếu nó cho biết tài nguyên không được đóng hoặc cleanup thất bại.
- Không nên coi suppressed đầu tiên là root cause nếu exception chính đã chỉ rõ lỗi ban đầu.

Ví dụ:

~~~text
java.lang.IllegalStateException: Request failed
    at com.example.Client.send(Client.java:42)
    Suppressed: java.io.IOException: Failed to close response
        at com.example.Client.close(Client.java:67)
Caused by: java.net.SocketTimeoutException: Read timed out
    at ...
~~~

Trong ví dụ này, timeout là nguyên nhân của request failure; lỗi close là vấn đề bổ sung cần điều tra riêng.

## 8. Dùng stack trace để tìm vị trí phát sinh lỗi

Stack trace là danh sách các frame thể hiện đường gọi hàm tại thời điểm exception được ném ra.

Ví dụ:

~~~text
Caused by: java.lang.IllegalArgumentException: Invalid customer id
    at com.example.CustomerService.load(CustomerService.java:54)
    at com.example.OrderService.create(OrderService.java:81)
    at com.example.app.Main.main(Main.java:22)
~~~

Đọc từ trên xuống trong cùng một stack trace:

- Dòng đầu của exception cho biết loại lỗi và thông điệp.
- Frame gần đầu thường là nơi exception được ném ra hoặc được phát hiện.
- Các frame phía dưới cho thấy đường gọi dẫn đến vị trí đó.
- Frame thuộc JDK hoặc framework có thể cho biết lỗi phát sinh trong thư viện, nhưng nguyên nhân dữ liệu sai có thể đến từ caller của ứng dụng.

Tìm file và số dòng thuộc source của dự án trước. Mở đúng dòng và kiểm tra giá trị đầu vào, trạng thái object và điều kiện trước khi gọi thư viện.

Stack trace không phải lúc nào cũng có dòng source của ứng dụng. Lỗi có thể xảy ra trong native code, compiler, daemon, worker process hoặc thư viện đã bị đóng gói mà không có source line.

## 9. Các giai đoạn có thể phát sinh lỗi trong Gradle

Không phải mọi lỗi đều là task execution failure. Có thể phân loại theo giai đoạn:

| Giai đoạn | Dấu hiệu thường gặp | Hướng điều tra |
|---|---|---|
| Wrapper/JVM startup | Không tìm thấy Java, không tải được Gradle distribution, JVM không khởi động | JAVA_HOME, PATH, wrapper properties, network |
| Settings evaluation | Lỗi trong settings.gradle(.kts), include project sai | Settings file và project path |
| Plugin resolution | Plugin không tìm thấy hoặc không tải được | Plugin ID/version, pluginManagement và repository |
| Build script compilation/evaluation | Lỗi cú pháp hoặc API trong build.gradle(.kts) | Dòng file được chỉ ra, plugin DSL và version |
| Dependency resolution | Could not resolve, Could not find, HTTP/SSL error | Tọa độ, repository, credential, metadata, network |
| Task execution | Task path FAILED, Execution failed for task | Task action, input/output, stack trace |
| Test execution | Test class/method FAILED, assertion hoặc exception | Test report, test logs và fixture |
| Packaging/runtime | Artifact tạo được nhưng không chạy | Manifest, classpath, resource, dependency và runtime |

Việc xác định đúng giai đoạn giúp chọn lệnh và file cần kiểm tra. Nếu settings evaluation thất bại, chạy dependencyInsight của một configuration có thể không giúp ích vì project chưa cấu hình xong.

## 10. Nhận diện lỗi dependency resolution

Một lỗi dependency thường có dạng:

~~~text
Could not resolve all files for configuration ':app:runtimeClasspath'.
> Could not find com.example:client:2.0.0.
  Searched in the following locations:
    ...
~~~

Hoặc:

~~~text
Could not GET 'https://repo.example.com/...'.
> Received status code 401 from server
~~~

Hãy phân biệt các nguyên nhân:

- **Could not find**: tọa độ hoặc version không tồn tại trong repository được tìm kiếm, hoặc repository không cung cấp metadata tương ứng.
- **401 Unauthorized**: credential thiếu hoặc không hợp lệ.
- **403 Forbidden**: tài khoản được nhận diện nhưng không có quyền truy cập.
- **404 Not Found**: URL/artifact không tồn tại hoặc repository trả 404 cho tài nguyên không được phép truy cập.
- **PKIX path building failed**: JVM không tin cậy certificate chain của máy chủ.
- **Connection timed out**: không nhận được phản hồi trong thời gian chờ.
- **Connection refused**: kết nối bị từ chối tại host/port đích.
- **No matching variant**: module có variant nhưng attributes của consumer không tương thích với variant được publish.

Các dòng phía dưới thông báo Gradle thường cho biết URL, repository, configuration hoặc variant liên quan. Không nên đổi version ngay nếu lỗi thực chất là xác thực hoặc mạng.

## 11. Nhận diện lỗi biên dịch và lỗi kiểm thử

### Lỗi biên dịch

Compiler diagnostic thường có file, dòng, cột và mô tả:

~~~text
Main.java:18: error: cannot find symbol
Main.java:24: error: incompatible types
Main.java:31: error: method ... cannot be applied to given types
~~~

Đây là thông tin cụ thể hơn exception wrapper của task compileJava. Kiểm tra import, kiểu dữ liệu, method signature, source set, module readability và compile classpath.

### Lỗi kiểm thử

Khi task test thất bại, Gradle có thể in:

~~~text
> Task :test FAILED

Some tests failed. See the report at:
file:///.../build/reports/tests/test/index.html
~~~

Mở báo cáo để xác định class, method, assertion và exception. Phân biệt:

- Assertion failure: kết quả thực tế khác kỳ vọng.
- Exception trong test: code hoặc fixture ném exception.
- Test infrastructure failure: database, port, container hoặc service không sẵn sàng.
- Test discovery failure: framework không tìm thấy hoặc không khởi chạy test theo cấu hình.

Task test thất bại không có nghĩa mọi test đều thất bại. Báo cáo cho biết số lượng passed, failed và skipped.

## 12. Các tùy chọn Gradle để lấy thêm thông tin

Có thể tăng mức thông tin theo từng bước, tránh bật log quá chi tiết ngay từ đầu.

| Tùy chọn | Tác dụng |
|---|---|
| **--stacktrace** | In stack trace cho exception |
| **--full-stacktrace** | In stack trace đầy đủ hơn, gồm nhiều frame nội bộ |
| **--info** | In thêm thông tin về quá trình build và task |
| **--debug** | Log rất chi tiết, hữu ích khi điều tra sâu |
| **--console=plain** | Dùng output dạng văn bản ổn định, phù hợp lưu log CI |
| **--warning-mode all** | Hiển thị tất cả deprecation warning |
| **--continue** | Tiếp tục chạy các task độc lập sau khi một task thất bại nếu graph cho phép |
| **--scan** | Tạo Build Scan để xem thông tin build chi tiết trên dịch vụ được cấu hình |

Ví dụ bắt đầu với stack trace:

~~~bash
./gradlew build --stacktrace --console=plain
~~~

Nếu chưa đủ thông tin:

~~~bash
./gradlew build --info --stacktrace --console=plain
~~~

Khi cần điều tra sâu:

~~~bash
./gradlew build --debug --stacktrace --console=plain
~~~

Log debug có thể chứa đường dẫn nội bộ, thông tin repository, header hoặc dữ liệu nhạy cảm tùy plugin và môi trường. Không đăng nguyên log debug lên nơi công khai nếu chưa kiểm tra và loại bỏ secret.

Build Scan có thể gửi thông tin build đến dịch vụ scan. Chỉ sử dụng theo chính sách của tổ chức, đặc biệt với repository riêng, tên project nội bộ, thông tin môi trường và dữ liệu nhạy cảm.

## 13. --continue giúp gì khi có nhiều lỗi?

Mặc định, khi một task thất bại, Gradle có thể dừng các task phụ thuộc vào task đó. Các task độc lập có thể không được chạy nếu build dừng sớm.

Tùy chọn:

~~~bash
./gradlew build --continue
~~~

cho phép Gradle tiếp tục chạy những task không phụ thuộc vào task đã thất bại, trong phạm vi graph và các điều kiện còn lại cho phép. Cuối cùng build vẫn báo thất bại nếu có task thất bại.

Điều này hữu ích khi muốn thu thập nhiều lỗi độc lập trong một lần chạy, ví dụ nhiều subproject có test riêng.

Không nên dùng --continue để che lỗi hoặc coi build thành công. Nó thay đổi cách Gradle tiếp tục thực thi sau failure, không biến task FAILED thành task thành công.

## 14. Đọc lỗi trong multi-project build

Trong multi-project build, task path đầy đủ giúp xác định project gây lỗi.

Ví dụ:

~~~text
> Task :services:api:compileJava FAILED
> Task :libraries:domain:test
~~~

Task **:services:api:compileJava** thuộc project services:api. Dấu hai chấm đầu tiên biểu thị root, các thành phần tiếp theo biểu thị project path và task.

Khi điều tra:

1. Ghi lại task path đầy đủ.
2. Chạy riêng task đó bằng project path.
3. Kiểm tra dependency của configuration liên quan trong project đó.
4. Xem project dependency nào cung cấp class hoặc artifact bị thiếu.
5. Xác định lỗi xuất hiện ở producer hay consumer.

Ví dụ:

~~~bash
./gradlew :services:api:compileJava --stacktrace --info
~~~

Xem dependency của project:

~~~bash
./gradlew :services:api:dependencies --configuration compileClasspath
~~~

Truy nguyên một dependency:

~~~bash
./gradlew :services:api:dependencyInsight --dependency domain --configuration compileClasspath
~~~

Project consumer có thể báo lỗi do output của project producer không phù hợp. Cần xác định project tạo ra class/artifact và project sử dụng nó, không chỉ sửa build script ở task đang báo FAILED.

## 15. Phân biệt deprecation warning với build failure

Gradle có thể hiển thị warning như:

~~~text
Deprecated Gradle features were used in this build,
making it incompatible with a future Gradle version.
~~~

Warning này cho biết build đang dùng API hoặc behavior đã bị deprecated. Nó không nhất thiết làm build hiện tại thất bại.

Có thể xem tất cả warning:

~~~bash
./gradlew build --warning-mode all
~~~

Cần phân biệt:

- **Warning**: cảnh báo về hành vi hoặc API cần được xử lý.
- **Error**: lỗi khiến một phần cấu hình hoặc task không thể hoàn thành.
- **Build failure**: kết quả tổng thể khi có lỗi không được xử lý.

Một warning có thể trở thành lỗi sau khi nâng cấp Gradle nếu API bị loại bỏ. Vì vậy, nên xử lý deprecation trước khi nâng cấp major version, nhưng không nên nhầm warning với nguyên nhân của một task FAILED hiện tại.

## 16. Đọc log daemon và lỗi môi trường

Gradle daemon chạy nền và có log riêng trong Gradle User Home, thường dưới thư mục:

~~~text
.gradle/daemon/<gradle-version>/
~~~

Tên file log có thể chứa process ID. Log daemon hữu ích khi lỗi liên quan đến JVM, daemon crash, worker hoặc quá trình giao tiếp với daemon.

Một số bước kiểm tra:

- Xác nhận JDK đang được dùng bằng lệnh java -version.
- Kiểm tra JAVA_HOME và Gradle toolchain.
- Chạy lại với --no-daemon để so sánh nếu nghi ngờ daemon.
- Kiểm tra daemon log khi terminal chỉ hiển thị lỗi giao tiếp.
- Xác nhận quyền đọc/ghi thư mục project và Gradle User Home.
- Kiểm tra bộ nhớ, disk space và tiến trình bị hệ điều hành dừng.

Lệnh xem daemon:

~~~bash
./gradlew --status
~~~

Dừng daemon đang chạy:

~~~bash
./gradlew --stop
~~~

Không nên xóa toàn bộ Gradle cache như bước đầu tiên. Trước tiên hãy lấy log và xác định có dấu hiệu cache hỏng hay không.

## 17. Quy trình đọc lỗi theo thứ tự

Khi build thất bại, có thể đi theo quy trình sau:

**Bước 1: Ghi lại lệnh và mã thoát**

Lưu command đầy đủ, thư mục chạy, phiên bản Gradle/JDK và mã thoát. Điều này giúp tái hiện đúng bối cảnh.

**Bước 2: Xác định build thất bại ở giai đoạn nào**

Xem lỗi xuất hiện khi wrapper khởi động, settings, plugin resolution, build script evaluation, dependency resolution hay task execution.

**Bước 3: Tìm task path nếu có**

Ghi lại task có hậu tố FAILED, ví dụ **:app:compileJava** hoặc **:service:test**. Nếu không có task path, lỗi có thể xảy ra trước execution phase.

**Bước 4: Đọc What went wrong**

Tìm mô tả trực tiếp của Gradle. Xác định đây là lỗi compiler, test, dependency, plugin, filesystem hay tiến trình con.

**Bước 5: Lần theo exception chain**

Đọc từng Caused by. Tìm exception hoặc diagnostic cụ thể nhất có thể giải thích lỗi. Xem cả suppressed exception nếu nó cho biết cleanup hoặc tài nguyên phụ cũng thất bại.

**Bước 6: Mở đúng file và dòng**

Nếu có đường dẫn source hoặc build script, mở đúng dòng và kiểm tra input, configuration hoặc lời gọi gây lỗi.

**Bước 7: Chạy task nhỏ nhất có thể tái hiện lỗi**

Ví dụ:

~~~bash
./gradlew :app:compileJava --stacktrace --info
~~~

Chạy task nhỏ giúp log ngắn và loại bỏ các task không liên quan.

**Bước 8: Thay đổi một nguyên nhân tại một thời điểm**

Ví dụ sửa repository credential, dependency version hoặc source code riêng biệt. Nếu đổi nhiều yếu tố cùng lúc, sẽ khó biết thay đổi nào thực sự giải quyết lỗi.

**Bước 9: Chạy lại và so sánh**

Kiểm tra mã thoát, task outcome và thông báo mới. Một lỗi có thể được giải quyết nhưng làm lộ ra lỗi tiếp theo; hãy tiếp tục theo chuỗi cho đến khi build hoàn tất.

**Bước 10: Xác nhận trong môi trường tương đương CI**

Nếu lỗi xảy ra trên CI, kiểm tra cùng JDK, biến môi trường, credential scope, working directory và lệnh Gradle. Build thành công trên máy cá nhân chưa chứng minh CI đã được sửa.

## 18. Ví dụ đọc một chuỗi nguyên nhân hoàn chỉnh

Giả sử CI báo:

~~~text
> Task :app:integrationTest FAILED

FAILURE: Build failed with an exception.

* What went wrong:
Execution failed for task ':app:integrationTest'.
> There were failing tests. See the report at:
  file:///workspace/app/build/reports/tests/integrationTest/index.html

* Try:
> Run with --stacktrace option to get the stack trace.

BUILD FAILED in 42s
Process finished with exit code 1
~~~

Bước đầu ta biết:

- Process Gradle thất bại và trả mã khác 0.
- Task path là **:app:integrationTest**.
- Gradle báo có test thất bại.
- Báo cáo HTML chứa tên test và exception cụ thể.

Mở report, giả sử thấy:

~~~text
OrderRepositoryIntegrationTest > savesOrder FAILED

org.springframework.jdbc.CannotGetJdbcConnectionException:
Failed to obtain JDBC Connection

Caused by: org.postgresql.util.PSQLException:
Connection to localhost:5432 refused
~~~

Chuỗi nguyên nhân:

1. Task integrationTest thất bại vì test không qua.
2. Test không lấy được JDBC connection.
3. PostgreSQL driver báo kết nối localhost:5432 bị từ chối.
4. Cần kiểm tra database test có chạy, port mapping có đúng, service readiness và cấu hình connection string trong CI.

Việc tăng stack trace có thể giúp xem đường gọi sâu hơn, nhưng report và thông báo kết nối đã cung cấp nguyên nhân có thể hành động. Không cần sửa logic repository nếu database chưa sẵn sàng.

## 19. Ví dụ lỗi có mã thoát khác 0 nhưng không có task FAILED

Giả sử build script có lỗi cú pháp:

~~~text
Could not compile build file 'build.gradle.kts'.
> ... Unexpected tokens ...
~~~

Trong trường hợp này:

- Gradle process trả mã khác 0.
- Build thất bại.
- Không nhất thiết có task nào hiển thị FAILED vì task graph có thể chưa được tạo.
- Cần sửa build script tại vị trí compiler chỉ ra.

Một ví dụ khác là plugin không được tìm thấy trong plugin repository. Đây là lỗi plugin resolution, xảy ra trong quá trình cấu hình. Chạy riêng task test hoặc compileJava cũng không giải quyết được vì Gradle chưa hoàn thành cấu hình project.

Điều này cho thấy mã thoát khác 0 chỉ nói lệnh thất bại. Không có task FAILED không có nghĩa shell báo sai; lỗi có thể xảy ra trước khi task bắt đầu.

## 20. Ghi log có ích cho CI

Một log CI tốt nên giữ:

- Lệnh Gradle chính xác.
- Gradle Wrapper version và JDK version.
- Process exit code.
- Task path hoặc giai đoạn thất bại.
- Phần What went wrong.
- Stack trace phù hợp.
- Test report hoặc dependency report nếu liên quan.
- Thông tin môi trường cần thiết nhưng không chứa secret.

Có thể dùng:

~~~bash
./gradlew build --stacktrace --console=plain
~~~

Nếu cần log chi tiết hơn:

~~~bash
./gradlew build --info --stacktrace --console=plain
~~~

Không nên bật --debug cho mọi build CI vì log rất lớn và có thể chứa dữ liệu nhạy cảm. Hãy chỉ dùng khi điều tra có mục tiêu, kiểm tra log trước khi chia sẻ và lưu theo chính sách bảo mật của tổ chức.

Nếu dùng Build Scan, xác nhận dữ liệu nào được gửi và ai có quyền truy cập. Scan rất hữu ích để xem timeline, task và dependency, nhưng không nên upload thông tin nội bộ trái với chính sách của dự án.

## 21. Những lỗi thường gặp khi đọc mã thoát và exception

| Hiểu nhầm hoặc biểu hiện | Thực tế | Cách xử lý |
|---|---|---|
| Exit code 1 cho biết lỗi compile | Mã thoát không phân loại nguyên nhân | Đọc task path, What went wrong và diagnostic |
| Execution failed for task là root cause | Thường là exception wrapper của Gradle | Tìm compiler output hoặc Caused by cụ thể |
| Không có task FAILED nghĩa build thành công | Lỗi có thể xảy ra trong settings hoặc configuration | Xác định giai đoạn build thất bại |
| Caused by cuối cùng luôn là điều duy nhất cần sửa | Cause sâu nhất có thể chỉ là biểu hiện thấp tầng | Đọc toàn bộ chain và ngữ cảnh task |
| Suppressed exception là nguyên nhân chính | Thường là lỗi phụ khi cleanup | Xác định exception chính và kiểm tra suppressed riêng |
| UP-TO-DATE là task bị lỗi | Nó có nghĩa output còn hợp lệ | Đọc task outcome chính xác |
| --continue làm build thành công dù có lỗi | Build vẫn thất bại nếu có task thất bại | Dùng để thu thập thêm lỗi độc lập |
| Warning deprecation là nguyên nhân của mọi build failure | Warning có thể không làm build hiện tại thất bại | Tìm thông báo ERROR hoặc task FAILED cụ thể |
| Pipe qua tee luôn giữ exit code Gradle | Shell có thể trả mã của lệnh cuối trong pipe | Dùng pipefail hoặc lưu mã thoát đúng cách |
| Xóa cache là cách đầu tiên để sửa lỗi | Có thể mất dữ liệu chẩn đoán và không giải quyết nguyên nhân | Thu thập log, xác định cache có liên quan trước |

## 22. Những nguyên tắc cần nhớ

- Exit code 0 thường biểu thị Gradle process thành công; mã khác 0 báo build hoặc quá trình khởi động thất bại.
- Mã thoát không cho biết loại lỗi cụ thể và không phải mã trạng thái của từng task.
- **Execution failed for task** xác định task thất bại nhưng nguyên nhân có thể nằm sâu hơn.
- Đọc **What went wrong**, task path, compiler/test diagnostic và exception chain.
- **Caused by** thể hiện nguyên nhân được bọc; **Suppressed** thể hiện lỗi phụ được đính kèm.
- Root cause thường nằm sâu trong chain nhưng phải đọc ngữ cảnh, không chỉ lấy dòng cuối.
- Lỗi có thể xảy ra trước task execution trong wrapper, settings, plugin resolution, build script hoặc dependency resolution.
- Dùng **--stacktrace**, **--info** và **--console=plain** để lấy thông tin có mục tiêu; chỉ bật **--debug** khi cần và bảo vệ log.
- Dùng **--continue** để chạy thêm task độc lập sau failure, không phải để biến build lỗi thành thành công.
- Trong multi-project build, ghi lại task path đầy đủ để xác định đúng project.
- Đọc mã thoát ngay sau lệnh Gradle; chú ý cách Bash, PowerShell, Command Prompt và CI truyền trạng thái.
- Tái hiện lỗi bằng task nhỏ nhất, thay đổi từng nguyên nhân và xác nhận lại trên môi trường tương đương CI.

Mã thoát cho biết kết quả của tiến trình Gradle ở cấp hệ điều hành. Thông báo task và exception chain cho biết lỗi xảy ra ở đâu và vì sao. Khi đọc đúng thứ tự từ kết quả tổng thể đến diagnostic cụ thể, người phát triển có thể tìm ra nguyên nhân thực tế, sửa đúng tầng cấu hình hoặc mã nguồn và giữ cho CI phản ánh chính xác trạng thái build.
