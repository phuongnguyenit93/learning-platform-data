# Theo dõi output khi biên dịch Java

## 1. Theo dõi output trong compilation pipeline

Khi biên dịch Java, compiler tạo ra nhiều loại output khác nhau. Muốn biết quá trình biên dịch có thành công hay không, cần quan sát đúng loại output và đúng giai đoạn.

Có thể chia output thành bốn nhóm:

1. **Compiler diagnostics:** lỗi, cảnh báo và ghi chú do compiler phát hiện trong source hoặc trong quá trình xử lý.
2. **Process output:** thông tin compiler hoặc build tool ghi ra standard output (stdout) và standard error (stderr).
3. **Generated artifacts:** file .class, source được annotation processor sinh ra, native header và các sản phẩm build khác.
4. **Build execution report:** trạng thái task, cache, thời gian thực thi và kết quả của Gradle, Maven hoặc CI.

Các nhóm này có liên quan nhưng không đồng nghĩa. Một lần biên dịch có thể không in gì ra terminal nhưng vẫn tạo file .class thành công. Ngược lại, log có nhiều dòng thông báo không có nghĩa compile đã thành công; cần kiểm tra diagnostics và exit code của tiến trình.

Luồng quan sát tổng quát:

~~~text
Java source files
      |
      v
Compiler / build task
      |
      +----> stdout / stderr / diagnostics
      |
      +----> generated source files
      |
      +----> .class files
      |
      +----> build task result and exit code
      |
      v
Inspect artifacts and verify behavior
~~~

Mục tiêu của việc theo dõi output là trả lời được: compiler đã chạy chưa, source nào được xử lý, có lỗi/cảnh báo nào, file nào được sinh ra, chúng nằm ở đâu và build có thực sự kết thúc thành công hay không.

## 2. Output mặc định của javac

Lệnh javac cơ bản:

~~~bash
javac Hello.java
~~~

Nếu source hợp lệ và compiler không cần thông báo bổ sung, javac thường không in thông báo thành công. File .class được tạo trong thư mục hiện tại hoặc vị trí được chỉ định bằng tùy chọn -d.

Sự im lặng sau một lệnh javac không có nghĩa compiler không chạy. Hãy kiểm tra exit code và artifact đầu ra.

Ví dụ file src/demo/Hello.java:

~~~java
package demo;

public class Hello {
    public static void main(String[] args) {
        System.out.println("Hello from compiled class");
    }
}
~~~

Biên dịch từ thư mục gốc dự án:

~~~bash
javac --release 17 -encoding UTF-8 -d out src/demo/Hello.java
~~~

Cấu trúc đầu ra:

~~~text
project/
├── src/
│   └── demo/
│       └── Hello.java
└── out/
    └── demo/
        └── Hello.class
~~~

Tùy chọn -d chỉ định thư mục gốc để lưu class file. Compiler tạo các thư mục con theo package của lớp. Vì vậy, class demo.Hello được lưu tại out/demo/Hello.class.

Chạy chương trình bằng classpath trỏ đến thư mục gốc chứa package:

~~~bash
java -cp out demo.Hello
~~~

Stdout của ứng dụng:

~~~text
Hello from compiled class
~~~

Cần phân biệt stdout của ứng dụng với output của compiler. Dòng Hello from compiled class xuất hiện khi JVM chạy chương trình, không phải khi javac biên dịch source.

## 3. Phân biệt stdout, stderr, diagnostics và exit code

Một tiến trình command-line có thể ghi dữ liệu ra hai luồng chuẩn:

- **stdout:** output thông thường, ví dụ kết quả chương trình hoặc thông tin mà công cụ chủ động in.
- **stderr:** thông báo lỗi, cảnh báo hoặc thông tin chẩn đoán. Công cụ có thể dùng stderr cho nhiều loại thông báo, không chỉ lỗi.
- **Exit code:** trạng thái kết thúc của tiến trình, thường là 0 khi thành công và khác 0 khi thất bại.

Không nên phân loại lỗi chỉ dựa trên luồng xuất. Một công cụ có thể ghi warning ra stderr nhưng vẫn trả exit code 0. Một số công cụ khác có thể ghi log thông thường ra stderr. Exit code cùng diagnostics và kết quả artifact mới cho thấy đầy đủ trạng thái.

Với javac, lỗi biên dịch thường đi kèm tên file, dòng, cột, thông báo và dấu chỉ vị trí. Ví dụ:

~~~java
public class Broken {
    public static void main(String[] args) {
        int count = "ten";
    }
}
~~~

Compiler sẽ báo lỗi không thể gán giá trị kiểu String cho biến int. Nội dung và cách định dạng chính xác của diagnostic có thể thay đổi theo JDK, locale và tùy chọn compiler.

Một lần compile cần được đánh giá theo ba câu hỏi:

1. Có diagnostic ERROR hay không?
2. Exit code của javac/build tool có bằng 0 không?
3. Artifact mong đợi có được tạo hoặc cập nhật đúng nơi không?

Nếu build tool trả về thành công nhưng artifact không xuất hiện, hãy kiểm tra output directory, cấu hình source set/module và task thực sự đã chạy. Nếu artifact tồn tại nhưng build trả lỗi, có thể một bước sau compile đã thất bại.

## 4. Ghi lại log và giữ đúng exit code

Khi chạy compile trong terminal hoặc CI, nên lưu log để có thể xem lại khi build thất bại. Cần giữ nguyên exit code trước khi chạy lệnh khác, vì một lệnh đọc log có thể làm thay đổi trạng thái exit code cuối cùng của shell.

### Bash trên Linux/macOS

~~~bash
javac --release 17 -encoding UTF-8 -d out src/demo/Hello.java > compile.stdout.log 2> compile.stderr.log
compile_status=$?

echo "javac exit code: $compile_status"
cat compile.stdout.log
cat compile.stderr.log

if [ "$compile_status" -ne 0 ]; then
    exit "$compile_status"
fi
~~~

Stdout và stderr được lưu riêng. Biến compile_status giữ exit code của javac ngay sau khi tiến trình kết thúc.

Nếu dùng pipe với tee để vừa xem vừa lưu log, cần lưu ý exit code mặc định của pipeline thường là exit code của lệnh cuối cùng. Trong Bash, có thể bật pipefail để lỗi của javac không bị che khuất bởi tee.

~~~bash
set -o pipefail
javac --release 17 -d out src/demo/Hello.java 2>&1 | tee compile.log
compile_status=$?
~~~

### PowerShell trên Windows

~~~powershell
javac --release 17 -encoding UTF-8 -d out src/demo/Hello.java *> compile.log
$compileStatus = $LASTEXITCODE

Write-Output "javac exit code: $compileStatus"
Get-Content compile.log

if ($compileStatus -ne 0) {
    exit $compileStatus
}
~~~

Với chương trình native như javac, PowerShell lưu exit code của tiến trình trong LASTEXITCODE. Hãy lấy giá trị đó ngay sau lệnh cần theo dõi, trước khi gọi Get-Content hoặc lệnh khác.

Không nên chỉ kiểm tra biến $? của PowerShell sau một chuỗi lệnh nếu mục tiêu là biết chính xác exit code của tiến trình native. $? thể hiện trạng thái thành công của lệnh PowerShell gần nhất; LASTEXITCODE giữ exit code của chương trình native gần nhất.

## 5. Theo dõi chi tiết hoạt động của javac

Khi cần biết compiler đang đọc file nào, xử lý classpath ra sao hoặc thực hiện những công việc gì, dùng tùy chọn -verbose:

~~~bash
javac -verbose --release 17 -d out src/demo/Hello.java
~~~

Tùy chọn -verbose yêu cầu compiler in thông tin về các hoạt động nội bộ như đọc source/class và ghi class file. Đây là log chẩn đoán, không phải output của ứng dụng. Chi tiết và nội dung log phụ thuộc JDK, classpath, source và môi trường nên không nên dùng nguyên văn log verbose làm tiêu chí kiểm thử ổn định.

Có thể kết hợp verbose với redirect để lưu lại:

~~~bash
javac -verbose --release 17 -d out src/demo/Hello.java > javac-verbose.log 2>&1
~~~

Dùng verbose khi cần tìm hiểu:

- Compiler có tìm thấy source file cần biên dịch không?
- Compiler đang nạp class nào từ classpath hoặc module path?
- Class file được ghi vào thư mục nào?
- Một dependency được tìm thấy từ thư mục, JAR hay module nào?
- Vì sao một lần compile có thời gian hoặc hoạt động khác thường?

Không bật verbose cho mọi build CI nếu không cần thiết. Log có thể rất dài, làm khó tìm lỗi chính và tăng dung lượng lưu trữ.

## 6. Theo dõi warning và error

Compiler diagnostics giúp phát hiện lỗi cú pháp, kiểu dữ liệu, API deprecated và nhiều vấn đề khác. Có thể điều chỉnh mức cảnh báo bằng các tùy chọn javac.

### -Xlint

Tùy chọn -Xlint bật các nhóm cảnh báo bổ sung:

~~~bash
javac -Xlint:all --release 17 -d out src/demo/Hello.java
~~~

Có thể chọn một nhóm cảnh báo cụ thể thay vì tất cả. Ví dụ:

~~~bash
javac -Xlint:deprecation -Xlint:unchecked --release 17 -d out src/demo/Hello.java
~~~

Một số nhóm thường gặp:

| Nhóm | Nội dung |
|---|---|
| deprecation | Sử dụng API đã được đánh dấu deprecated. |
| unchecked | Thao tác generic có kiểm tra kiểu không đầy đủ. |
| rawtypes | Sử dụng raw type thay vì khai báo type parameter. |
| serial | Vấn đề liên quan đến serialization và serialVersionUID. |
| fallthrough | Trường hợp switch có thể rơi tiếp sang case kế tiếp. |
| finally | Một số cấu trúc finally có thể làm mất kết quả điều khiển hoặc exception. |
| path | Vấn đề liên quan đến đường dẫn tìm kiếm. |

Nhóm cảnh báo và chi tiết cụ thể phụ thuộc phiên bản compiler. Có thể xem danh sách hỗ trợ bằng tài liệu javac của đúng JDK hoặc chạy javac -X.

### -Werror và -Xdiags

Có thể yêu cầu compiler xem warning là lỗi:

~~~bash
javac -Xlint:all -Werror --release 17 -d out src/demo/Hello.java
~~~

Khi dùng -Werror, một warning có thể khiến compilation thất bại. Điều này hữu ích trong CI nếu dự án có chính sách không chấp nhận warning, nhưng cần thống nhất với nhóm và xử lý các warning có chủ đích trước khi bật.

Tùy chọn -Xdiags:verbose yêu cầu định dạng diagnostic chi tiết hơn trên những compiler hỗ trợ:

~~~bash
javac -Xdiags:verbose --release 17 -d out src/demo/Hello.java
~~~

Định dạng chi tiết giúp chẩn đoán một số lỗi kiểu hoặc overload, nhưng thông điệp không nên bị parse bằng script như một API ổn định. Nếu cần tích hợp chương trình, hãy ưu tiên Java Compiler API và Diagnostic API.

## 7. Theo dõi nơi lưu class file và generated source

Javac có nhiều tùy chọn để điều khiển output directory. Việc tách các loại artifact giúp build dễ kiểm soát và tránh nhầm source do con người viết với source do compiler hoặc annotation processor sinh ra.

| Tùy chọn | Output |
|---|---|
| -d directory | Thư mục gốc chứa class file được biên dịch. |
| -s directory | Thư mục gốc chứa source file được annotation processor sinh ra. |
| -h directory | Thư mục gốc chứa native header được sinh cho JNI khi biên dịch phù hợp. |

Ví dụ:

~~~bash
javac --release 17 -d build/classes -s build/generated/sources -h build/generated/headers src/demo/Hello.java
~~~

Nếu không có annotation processor sinh source hoặc khai báo native cần header, các thư mục tương ứng có thể không xuất hiện. Không nên suy ra rằng một tùy chọn bị bỏ qua chỉ từ việc thư mục rỗng; hãy xác định loại source và processor có thực sự yêu cầu artifact đó không.

Với annotation processing, có thể quan sát các processing round và processor được gọi bằng các tùy chọn javac mở rộng:

~~~bash
javac -XprintRounds -XprintProcessorInfo -d build/classes -s build/generated/sources src/demo/UseGeneratedType.java
~~~

Các tùy chọn -XprintRounds và -XprintProcessorInfo hữu ích khi kiểm tra processor có được phát hiện và chạy hay không. Đây là tùy chọn mở rộng của javac; hãy kiểm tra hỗ trợ trên JDK đang dùng.

Một số chế độ annotation processing:

- -proc:none: không chạy annotation processing.
- -proc:only: chỉ thực hiện annotation processing, không thực hiện compilation thông thường.
- Mặc định: compiler có thể chạy annotation processing nếu tìm thấy processor phù hợp trên processor path hoặc classpath theo cấu hình.

Nếu source do processor sinh ra không đúng, hãy kiểm tra processor path, phiên bản processor, processing rounds, thư mục -s và diagnostics. Không chỉnh sửa trực tiếp generated source nếu quy trình build sẽ sinh lại file đó.

## 8. Kiểm tra nội dung file .class

Sau khi compile, có thể dùng javap để xem thông tin bên trong class file. javap là công cụ đi kèm JDK, giúp quan sát cấu trúc class, method, bytecode và metadata.

Ví dụ:

~~~bash
javap -classpath out demo.Hello
~~~

Lệnh này hiển thị khai báo class và các thành viên công khai mà javap trình bày.

Để xem bytecode:

~~~bash
javap -classpath out -c demo.Hello
~~~

Tùy chọn -c in các lệnh bytecode của method. Để xem thông tin chi tiết hơn:

~~~bash
javap -classpath out -verbose demo.Hello
~~~

Verbose của javap là chế độ chi tiết của công cụ javap, khác với javac -verbose. Kết quả có thể gồm constant pool, flags, descriptor, attribute và thông tin debug có trong class file.

Có thể dùng javap để kiểm tra:

- Class file có đúng package và tên lớp không?
- Method mong đợi có được sinh ra không?
- Bytecode có chứa lệnh hoặc lời gọi dự kiến không?
- Class file có metadata như line number, generic signature hoặc annotation phù hợp không?
- Compiler có dùng release/target mà dự án yêu cầu không?

Để quan sát thông tin phiên bản class file và constant pool, dùng javap -verbose. Không nên chỉ nhìn một vài dòng bytecode để kết luận toàn bộ ứng dụng tương thích; cần kiểm tra cả dependency, runtime và hành vi khi chạy.

## 9. Theo dõi output qua Gradle và Maven

Khi dùng build tool, javac thường được gọi bên trong task/plugin. Vì vậy, log terminal còn chứa output điều phối của build tool, trạng thái task và thông tin dependency.

### Gradle

Đối với dự án dùng Java plugin, task compileJava biên dịch source set main:

~~~bash
./gradlew compileJava --console=plain
~~~

Trên Windows có thể dùng:

~~~powershell
.\gradlew.bat compileJava --console=plain
~~~

Thêm --info để có thêm thông tin khi cần chẩn đoán:

~~~bash
./gradlew compileJava --info --console=plain
~~~

Các trạng thái thường thấy:

- **UP-TO-DATE:** output hiện tại được xem là hợp lệ theo input và trạng thái task; Gradle không cần thực thi lại task.
- **FROM-CACHE:** Gradle lấy output tương ứng từ build cache.
- **NO-SOURCE:** task không có source phù hợp để xử lý.
- **EXECUTED:** task đã thực thi trong lần build đó.

Output mặc định của Java plugin thường nằm trong build/classes/java/main đối với main source set và build/classes/java/test đối với test source set. Dự án có thể tùy chỉnh đường dẫn này.

Nếu task UP-TO-DATE, không thấy javac chạy ở terminal là bình thường. Nếu cần kiểm tra vì sao task được hoặc không được thực thi, xem input/output, task outcome và log --info. Chỉ dùng --rerun-tasks khi thực sự cần ép task chạy lại và đã hiểu tác động của các task liên quan.

### Maven

Đối với Maven, phase compile biên dịch source chính:

~~~bash
mvn compile
~~~

Để có thêm thông tin chẩn đoán:

~~~bash
mvn -X compile
~~~

Tùy chọn -X bật debug log rất chi tiết; không nên bật thường xuyên trong CI hoặc chia sẻ log công khai nếu có thể chứa đường dẫn nội bộ, thông tin repository hay dữ liệu nhạy cảm. Tùy chọn -e in stack trace khi Maven gặp lỗi.

Output mặc định của Maven thường nằm trong target/classes. Source sinh bởi plugin có thể nằm trong target/generated-sources hoặc thư mục được plugin cấu hình.

Cần phân biệt phase compile với test và package. Một lần mvn compile thành công xác nhận bước compile đã hoàn thành; nó không chứng minh test đã chạy hoặc JAR cuối cùng đã được đóng gói.

## 10. Phân biệt output mới, output cũ và cache

Một file .class tồn tại không đủ để chứng minh lần compile vừa rồi đã sinh ra file đó. File có thể được giữ lại từ lần build trước, được lấy từ cache hoặc đến từ một source/output directory khác.

Các tình huống thường gặp:

- Build tool báo UP-TO-DATE hoặc FROM-CACHE: task không nhất thiết gọi javac trong tiến trình hiện tại.
- Xóa hoặc đổi tên một source class: file .class cũ tương ứng có thể còn tồn tại nếu output directory không được làm sạch.
- Thay đổi cấu hình compiler, toolchain, processor hoặc classpath: có thể làm thay đổi input của task và yêu cầu compile lại.
- Dùng chung output directory cho nhiều cấu hình build: class file của lần build trước có thể bị nhầm với kết quả hiện tại.

Để kiểm tra đáng tin cậy, hãy xác định output directory của đúng task, quan sát task outcome, kiểm tra timestamp hoặc nội dung artifact và thực hiện clean build theo quy trình dự án khi cần so sánh. Clean task thường xóa generated build output; chỉ chạy khi hiểu rằng các artifact đó sẽ được tạo lại.

Trong CI, nên lưu log và artifact của đúng job/build ID. Không trộn file .class từ nhiều job hoặc nhiều commit vào cùng một thư mục mà không có quy ước phân biệt.

## 11. Tổ chức theo dõi output trong CI

Một pipeline compile có thể thu thập các bằng chứng sau:

1. **Build identity:** commit, branch, build number, JDK vendor/version, hệ điều hành và kiến trúc.
2. **Compiler configuration:** release, encoding, classpath/module path, annotation processor và các compiler flags.
3. **Diagnostics:** stdout/stderr hoặc log đã hợp nhất, trạng thái warning/error và exit code.
4. **Artifact inventory:** đường dẫn, kích thước, checksum và loại artifact được tạo.
5. **Task outcome:** task nào chạy, task nào lấy cache, task nào bỏ qua vì không có source.
6. **Verification:** chạy test phù hợp hoặc kiểm tra class/JAR đầu ra bằng công cụ tương ứng.

Không nên lưu log vô thời hạn nếu log chứa thông tin nhạy cảm hoặc có dung lượng lớn. Áp dụng retention phù hợp, che token/secret và giới hạn quyền truy cập artifact. Không in toàn bộ environment variables hoặc command line có chứa mật khẩu vào log.

Khi compile thất bại, log nên giúp người đọc xác định nhanh source file, diagnostic đầu tiên, compiler version, command/flags và task gây lỗi. Khi compile thành công, artifact phải được liên kết với đúng commit và build identity để có thể truy vết.

## 12. Lỗi thường gặp khi theo dõi output

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| javac chạy nhưng không in gì | Compile thành công và javac không có thông báo mặc định. | Kiểm tra exit code và file .class. |
| Có log nhưng build vẫn thất bại | Log có thể chỉ là verbose output; một diagnostic hoặc task sau đó đã fail. | Tìm ERROR và kiểm tra exit code cuối cùng của build. |
| Không thấy file .class | Sai output directory, source chưa được compile hoặc compile thất bại. | Kiểm tra -d, task outcome và diagnostics. |
| File .class cũ vẫn còn | Output directory chứa artifact từ lần build trước. | Kiểm tra timestamp/build ID và clean theo quy trình khi cần. |
| Warning không làm build fail | Compiler mặc định có thể chỉ phát cảnh báo. | Dùng -Xlint phù hợp; cân nhắc -Werror theo chính sách dự án. |
| Không thấy annotation processor chạy | Processor không được phát hiện, processor path sai hoặc processing bị tắt. | Kiểm tra processor path, -proc và -XprintRounds/-XprintProcessorInfo. |
| Gradle không gọi compiler | Task UP-TO-DATE, FROM-CACHE hoặc NO-SOURCE. | Xem task outcome và input/output. |
| Maven compile thành công nhưng không có JAR | Phase compile chưa chạy package. | Chạy phase package theo quy trình dự án nếu cần artifact JAR. |
| CI báo thành công dù javac lỗi | Script làm mất exit code, pipeline chỉ lấy trạng thái tee hoặc lệnh sau che lỗi. | Lưu exit code ngay sau tiến trình; dùng pipefail trong Bash. |
| Log verbose quá lớn | Bật chế độ chẩn đoán chi tiết cho mọi build. | Chỉ bật khi điều tra và giới hạn retention. |

## 13. Checklist theo dõi output compile

- [ ] Đã xác nhận đúng JDK/compiler version và lệnh compile được thực thi.
- [ ] Đã phân biệt stdout, stderr, diagnostics và exit code.
- [ ] Đã giữ exit code trước khi chạy lệnh xử lý log tiếp theo.
- [ ] Đã xác nhận vị trí output bằng -d hoặc cấu hình build tool.
- [ ] Đã kiểm tra class file hoặc generated source mong đợi.
- [ ] Đã đọc warning/error và bật -Xlint phù hợp khi cần.
- [ ] Đã dùng -verbose hoặc build-tool debug/info mode chỉ khi có mục đích chẩn đoán.
- [ ] Đã phân biệt output mới với artifact cũ hoặc output từ cache.
- [ ] Đã xác nhận annotation processor và generated output nếu dự án sử dụng.
- [ ] Đã lưu log/artifact theo build identity và bảo vệ dữ liệu nhạy cảm.
- [ ] Đã kiểm tra test/package riêng nếu mục tiêu yêu cầu các bước đó.

Theo dõi output hiệu quả là kết hợp log, diagnostics, exit code và artifact. Khi mỗi loại bằng chứng được kiểm tra đúng vai trò, có thể xác định chính xác compiler đã làm gì, vì sao build thất bại và file nào thực sự được tạo ra.