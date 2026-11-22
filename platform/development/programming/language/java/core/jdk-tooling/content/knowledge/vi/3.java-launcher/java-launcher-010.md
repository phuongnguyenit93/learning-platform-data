# Exit code của Java launcher

Exit code (còn gọi là exit status hoặc process exit status) là mã trạng thái mà một tiến trình trả về cho hệ điều hành khi kết thúc. Khi chạy ứng dụng bằng lệnh **java**, mã này cho biết tiến trình Java kết thúc thành công hay báo lỗi theo quy ước của ứng dụng. Shell, script triển khai, công cụ build và hệ thống CI có thể đọc mã trạng thái để quyết định bước tiếp theo.

Java launcher khởi động JVM và ứng dụng. Khi tiến trình kết thúc, trạng thái kết thúc của JVM được chuyển ra hệ điều hành. Vì vậy, để hiểu exit code cần biết ứng dụng Java kết thúc như thế nào và cách chương trình bên ngoài đọc trạng thái đó.

## 1. Quy ước của exit code

Quy ước phổ biến là:

- **0**: tiến trình kết thúc thành công.
- **Khác 0**: tiến trình báo lỗi hoặc một trạng thái đặc biệt do ứng dụng định nghĩa.

Hệ điều hành không áp đặt một bảng ý nghĩa chung cho mọi mã khác 0. Ứng dụng tự quy định mã nào biểu thị lỗi đầu vào, lỗi cấu hình, lỗi kết nối hoặc lỗi nghiệp vụ, rồi ghi rõ quy ước trong tài liệu.

Ví dụ, một chương trình có thể quy định:

| Exit code | Ý nghĩa do ứng dụng định nghĩa |
|---:|---|
| 0 | Thành công |
| 1 | Lỗi không phân loại |
| 2 | Thiếu hoặc sai tham số dòng lệnh |
| 3 | Không đọc được tệp cấu hình |

Đây chỉ là ví dụ. Một ứng dụng khác có thể gán ý nghĩa khác cho mã 2 hoặc 3. Khi tích hợp chương trình bên ngoài, hãy đọc tài liệu của chính chương trình đó.

Exit code khác với nội dung in ra màn hình. Một chương trình có thể in thông báo lỗi nhưng vẫn trả về 0; ngược lại, chương trình có thể không in gì nhưng kết thúc với mã khác 0. Vì vậy, script cần kiểm tra exit code thay vì chỉ tìm chữ “error” trong output.

## 2. Java launcher nhận exit code từ đâu?

Với cách chạy Java truyền thống, launcher **java** khởi động JVM, nạp lớp chính và gọi phương thức entry point, thường có dạng:

~~~java
public static void main(String[] args)
~~~

Phương thức **main** có kiểu trả về **void**. Giá trị trả về của phương thức main không được dùng làm exit code. Câu lệnh **return;** chỉ kết thúc phương thức; không thể viết **return 5;** để đặt mã trạng thái.

Khi ứng dụng kết thúc bình thường và JVM hoàn tất shutdown, exit code mặc định là **0**. Ứng dụng có thể chủ động đặt mã trạng thái bằng **System.exit(int status)**. Launcher cũng có thể trả về mã khác 0 khi không khởi chạy được ứng dụng, chẳng hạn không tìm thấy lớp chính, JAR hoặc module, hay có tùy chọn launcher không hợp lệ.

Có hai nguồn lỗi cần phân biệt:

1. **Lỗi khởi chạy:** launcher hoặc JVM không thể khởi động ứng dụng. Ví dụ: tên lớp sai, JAR không tồn tại, module không được tìm thấy hoặc tham số dòng lệnh không hợp lệ.
2. **Lỗi trong ứng dụng:** JVM khởi chạy được ứng dụng nhưng logic chương trình phát hiện lỗi và kết thúc với mã khác 0.

Trong cả hai trường hợp, bên gọi thường chỉ cần biết tiến trình có thành công hay không. Khi cần chẩn đoán, hãy đọc cả mã trạng thái và thông báo trên standard error.

## 3. Kết thúc bình thường

Nếu phương thức entry point chạy xong mà không yêu cầu kết thúc với mã lỗi, tiến trình Java thường kết thúc với mã **0** sau khi tất cả luồng non-daemon đã kết thúc.

Ví dụ, tạo tệp **HelloExit.java**:

~~~java
public class HelloExit {
    public static void main(String[] args) {
        System.out.println("Application completed.");
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac HelloExit.java
java HelloExit
~~~

Output:

~~~text
Application completed.
~~~

Trên Linux/macOS, đọc exit code ngay sau lệnh:

~~~bash
java HelloExit
status=$?
echo "Exit code: $status"
~~~

Kết quả:

~~~text
Application completed.
Exit code: 0
~~~

Trên Windows PowerShell:

~~~powershell
java HelloExit
$LASTEXITCODE
~~~

Kết quả là **0**.

JVM không nhất thiết kết thúc ngay khi phương thức main trả về. Nếu ứng dụng đã tạo các luồng non-daemon vẫn đang hoạt động, tiến trình còn sống cho tới khi các luồng đó kết thúc hoặc JVM được yêu cầu shutdown. Vì vậy, “main đã return” và “process đã exit” có thể là hai thời điểm khác nhau.

## 4. Chủ động đặt mã trạng thái bằng System.exit

**System.exit(int status)** yêu cầu JVM bắt đầu quá trình shutdown và kết thúc tiến trình với mã trạng thái được truyền vào.

- **System.exit(0)** thường biểu thị thành công.
- **System.exit(n)** với n khác 0 thường biểu thị lỗi hoặc một kết quả đặc biệt.
- Lời gọi này bắt đầu shutdown JVM và không trả quyền điều khiển về theo cách thông thường.

Ví dụ, tạo tệp **ExitCodeDemo.java**:

~~~java
public class ExitCodeDemo {
    public static void main(String[] args) {
        if (args.length != 1) {
            System.err.println("Usage: java ExitCodeDemo <name>");
            System.exit(2);
        }

        System.out.println("Hello, " + args[0]);
    }
}
~~~

Biên dịch:

~~~bash
javac ExitCodeDemo.java
~~~

Chạy với tham số hợp lệ:

~~~bash
java ExitCodeDemo Ada
~~~

Output:

~~~text
Hello, Ada
~~~

Exit code là **0** vì chương trình kết thúc bình thường.

Chạy thiếu tham số:

~~~bash
java ExitCodeDemo
~~~

Output trên standard error:

~~~text
Usage: java ExitCodeDemo <name>
~~~

Exit code là **2**, theo quy ước “sai cách sử dụng” của ví dụ.

Trong chương trình thực tế, nên tách phần xử lý nghiệp vụ khỏi quyết định kết thúc tiến trình:

~~~java
public class BatchApplication {
    public static void main(String[] args) {
        int status = runBatch(args);

        if (status != 0) {
            System.exit(status);
        }
    }

    private static int runBatch(String[] args) {
        if (args.length == 0) {
            System.err.println("Missing input file.");
            return 2;
        }

        // Thực hiện công việc và trả về mã trạng thái phù hợp.
        return 0;
    }
}
~~~

Cách tổ chức này giúp hàm nghiệp vụ có thể được kiểm thử độc lập. Điểm vào của ứng dụng chịu trách nhiệm chuyển kết quả thành exit code của tiến trình.

Không nên gọi **System.exit** tùy tiện bên trong thư viện hoặc lớp tiện ích dùng chung. Một thư viện có thể đang chạy bên trong IDE, máy chủ ứng dụng, test runner hoặc một tiến trình Java khác. Nếu thư viện tự gọi System.exit, nó có thể đóng toàn bộ JVM của chương trình chủ. Thư viện nên ném exception hoặc trả kết quả; ứng dụng ở tầng cao nhất mới quyết định mã thoát.

## 5. Exit code khi có exception

Một exception không được xử lý trong luồng chính thường khiến JVM in stack trace ra standard error và tiến trình Java launcher kết thúc với mã khác **0** (thông thường là **1**).

Ví dụ:

~~~java
public class UncaughtExceptionDemo {
    public static void main(String[] args) {
        throw new IllegalStateException("Unexpected state");
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac UncaughtExceptionDemo.java
java UncaughtExceptionDemo
~~~

Một phần output:

~~~text
Exception in thread "main" java.lang.IllegalStateException: Unexpected state
    at UncaughtExceptionDemo.main(UncaughtExceptionDemo.java:3)
~~~

Tiến trình kết thúc với mã khác 0. Với lỗi do launcher không thể nạp lớp hoặc khởi chạy ứng dụng, launcher cũng thường ghi thông báo lỗi ra standard error và trả mã khác 0. Không nên phụ thuộc vào một giá trị lỗi cụ thể cho mọi loại lỗi khởi chạy trên mọi phiên bản và nền tảng; hãy dựa vào quy ước của ứng dụng khi chính ứng dụng đặt mã.

Không phải exception ở bất kỳ luồng nào cũng làm exit code khác 0. Nếu một luồng phụ ném exception không được xử lý, handler mặc định thường in stack trace và kết thúc luồng đó; việc này tự nó không nhất thiết kết thúc toàn bộ JVM với mã lỗi. Nếu luồng chính và các luồng non-daemon còn lại kết thúc bình thường, tiến trình vẫn có thể kết thúc với mã **0**.

Nếu lỗi trong worker thread phải làm toàn bộ batch job thất bại, chương trình cần truyền lỗi về luồng điều phối, ghi nhận trạng thái thất bại và đặt exit code rõ ràng. Không nên dựa vào việc stack trace xuất hiện để hệ thống CI tự nhận biết lỗi.

Ví dụ chuyển exception thành trạng thái thất bại ở ranh giới ứng dụng:

~~~java
public class SafeBatch {
    public static void main(String[] args) {
        try {
            run(args);
        } catch (Exception e) {
            System.err.println("Batch failed: " + e.getMessage());
            System.exit(1);
        }
    }

    private static void run(String[] args) {
        if (args.length == 0) {
            throw new IllegalArgumentException("Input is required");
        }
        System.out.println("Batch completed.");
    }
}
~~~

Với ứng dụng lớn, nên phân loại exception và ánh xạ sang mã trạng thái theo hợp đồng đã tài liệu hóa, thay vì gom mọi lỗi vào một mã mà không có quy ước.

## 6. Shutdown hooks và Runtime.halt

Khi gọi **System.exit(status)**, JVM bắt đầu quy trình shutdown. Các shutdown hook đã đăng ký được chạy trong các luồng riêng. Chúng thường được dùng để đóng tài nguyên, flush dữ liệu hoặc thực hiện công việc dọn dẹp cuối cùng.

Ví dụ:

~~~java
public class ShutdownHookDemo {
    public static void main(String[] args) {
        Runtime.getRuntime().addShutdownHook(new Thread(() ->
            System.out.println("Shutdown hook executed.")
        ));

        System.exit(4);
    }
}
~~~

Khi chạy, chương trình in:

~~~text
Shutdown hook executed.
~~~

Exit code của tiến trình là **4**.

JVM không bảo đảm thứ tự thực thi giữa nhiều shutdown hook. Nếu hook bị treo, quá trình shutdown có thể bị kéo dài. Vì vậy, hook nên thực hiện công việc dọn dẹp ngắn gọn, có giới hạn và không phụ thuộc vào thứ tự của hook khác.

**System.exit** không bảo đảm các khối **finally** trên stack của luồng gọi sẽ được thực thi như khi phương thức trả về bình thường. Shutdown hook là cơ chế dọn dẹp trong quá trình shutdown; hãy đóng tài nguyên theo cấu trúc try-with-resources hoặc finally trước khi yêu cầu shutdown nếu cần bảo đảm thứ tự.

**Runtime.getRuntime().halt(status)** kết thúc JVM ngay lập tức, bỏ qua shutdown hooks và quá trình shutdown thông thường. Các khối finally cũng không được bảo đảm chạy. Đây là thao tác đặc biệt để dừng JVM khẩn cấp; ứng dụng thông thường nên dùng System.exit hoặc để chương trình kết thúc tự nhiên.

## 7. Đọc exit code trong các shell

Java launcher là một tiến trình con của terminal hoặc script. Mỗi hệ điều hành có cách truy xuất exit code khác nhau.

### Linux và macOS

Biến đặc biệt **$?** chứa exit status của lệnh gần nhất. Phải đọc ngay sau lệnh cần kiểm tra vì lệnh tiếp theo sẽ thay đổi giá trị này.

~~~bash
java ExitCodeDemo Ada
status=$?

if [ "$status" -eq 0 ]; then
    echo "Java application succeeded"
else
    echo "Java application failed with code $status"
fi
~~~

Có thể giữ lại output để điều tra:

~~~bash
java ExitCodeDemo Ada >app.log 2>&1
status=$?
cat app.log
echo "Exit code: $status"
~~~

Khi dùng pipe, cần chú ý: theo mặc định, trạng thái của pipeline trong shell POSIX thường là trạng thái của lệnh cuối cùng. Ví dụ:

~~~bash
java ExitCodeDemo Ada 2>&1 | tee app.log
~~~

Nếu Java thất bại nhưng **tee** ghi log thành công, mã trả về của pipeline có thể là 0. Với Bash, bật **pipefail** để pipeline trả về trạng thái lỗi phù hợp khi một lệnh trong pipeline thất bại:

~~~bash
set -o pipefail
java ExitCodeDemo Ada 2>&1 | tee app.log
status=$?
~~~

### Windows PowerShell

Với chương trình native như **java.exe**, PowerShell cung cấp biến **$LASTEXITCODE** để đọc mã thoát số nguyên của tiến trình vừa chạy:

~~~powershell
java ExitCodeDemo Ada
$status = $LASTEXITCODE

if ($status -eq 0) {
    Write-Output "Java application succeeded"
} else {
    Write-Error "Java application failed with code $status"
}
~~~

**$?** là trạng thái thành công/thất bại dạng Boolean của câu lệnh PowerShell gần nhất, không phải mã thoát số nguyên của tiến trình native. Khi cần mã số từ Java, hãy dùng **$LASTEXITCODE**.

Trong Command Prompt (**cmd.exe**), dùng biến **%ERRORLEVEL%**:

~~~bat
java ExitCodeDemo Ada
echo Exit code: %ERRORLEVEL%
~~~

Hãy lưu mã trạng thái ngay sau lệnh Java nếu script còn chạy những lệnh khác, vì các lệnh tiếp theo có thể làm thay đổi trạng thái mà shell báo cáo.

## 8. Exit code trong script, build và CI

Exit code là giao ước giữa chương trình Java và công cụ điều phối. Một script có thể dùng nó để dừng pipeline, đánh dấu job thất bại hoặc chọn bước khôi phục.

Ví dụ Bash:

~~~bash
#!/usr/bin/env bash
set -e

javac ExitCodeDemo.java
java ExitCodeDemo Ada
echo "Continue only if Java succeeded"
~~~

Với **set -e**, Bash thường dừng script khi một lệnh đơn giản trả về mã khác 0, trừ các ngữ cảnh ngoại lệ theo quy tắc của shell. Nếu cần xử lý từng mã lỗi, hãy dùng cấu trúc if hoặc kiểm tra $? rõ ràng thay vì phụ thuộc hoàn toàn vào set -e.

Trong CI, một lệnh chạy Java trả về khác 0 thường làm step/job thất bại. Điều này giúp phát hiện unit test hoặc integration test thất bại, batch import/export không hoàn tất, công cụ sinh mã gặp lỗi, ứng dụng không khởi động được trong smoke test hoặc script triển khai không hoàn thành bước bắt buộc.

Một chương trình Java cần trả exit code đáng tin cậy. Nếu bắt exception rồi chỉ in stack trace mà vẫn kết thúc bình thường, pipeline có thể đánh dấu job thành công dù công việc đã thất bại. Tương tự, script không kiểm tra exit code hoặc làm mất trạng thái lỗi qua pipe cũng có thể che giấu lỗi.

Trong Maven hoặc Gradle, hãy phân biệt exit code của lệnh build với exit code của ứng dụng được chạy như một phần của tác vụ. Build tool có thể báo build thất bại khi test task thất bại, kể cả khi tiến trình JVM dùng để chạy build vẫn hoạt động bình thường cho tới khi kết thúc. Hãy xem log và báo cáo test để xác định thành phần nào thất bại.

## 9. Lấy exit code của tiến trình Java con bằng ProcessBuilder

Một ứng dụng Java có thể khởi chạy một chương trình Java khác hoặc một tiến trình hệ điều hành thông qua **ProcessBuilder**. Phương thức **waitFor()** chờ tiến trình con kết thúc và trả về exit code của tiến trình đó.

Ví dụ:

~~~java
import java.io.IOException;

public class ProcessExitCodeDemo {
    public static void main(String[] args) throws IOException, InterruptedException {
        Process process = new ProcessBuilder("java", "-version")
                .inheritIO()
                .start();

        int childExitCode = process.waitFor();
        System.out.println("Child exit code: " + childExitCode);
    }
}
~~~

Trong ví dụ, **inheritIO()** chuyển standard input, standard output và standard error của tiến trình con sang các luồng tương ứng của tiến trình cha. **waitFor()** trả về khi tiến trình con kết thúc. Nếu tiến trình con không khởi chạy được, **start()** có thể ném IOException; nếu luồng bị interrupt khi đang chờ, waitFor() ném InterruptedException.

Dùng chuỗi lệnh tách thành từng phần tử như ví dụ giúp tránh tự ghép một command line dài theo quy tắc quoting của shell. Khi cần chạy một JDK cụ thể, hãy truyền đường dẫn đầy đủ tới executable Java mong muốn thay vì chỉ dùng tên **java**, vì tên đó vẫn được phân giải qua PATH của tiến trình cha.

Không dùng **Process.exitValue()** trước khi tiến trình kết thúc; phương thức này ném IllegalThreadStateException khi tiến trình vẫn đang chạy. Có thể gọi waitFor() để chờ, hoặc isAlive() để kiểm tra trước khi lấy exit value.

## 10. Thiết kế và kiểm thử exit code

Một chương trình dòng lệnh nên có hợp đồng exit code rõ ràng, ổn định và dễ sử dụng:

1. Dùng **0** cho thành công.
2. Dùng mã khác 0 cho lỗi hoặc kết quả đặc biệt cần bên gọi nhận biết.
3. Ghi tài liệu ý nghĩa từng mã, điều kiện phát sinh và cách xử lý.
4. In thông báo lỗi vào standard error; giữ standard output cho kết quả chính nếu output được dùng làm dữ liệu.
5. Không để exception quan trọng bị nuốt rồi trả về thành công.
6. Đặt quyết định kết thúc tiến trình ở tầng entry point; tránh để thư viện tự gọi System.exit.
7. Kiểm thử cả output, standard error và exit code, đặc biệt với đầu vào không hợp lệ và lỗi runtime.
8. Giữ mã trạng thái trong phạm vi dễ chuyển đổi giữa các hệ điều hành. Trên nhiều shell kiểu Unix, exit status được biểu diễn trong khoảng 0–255; không nên dựa vào việc truyền số âm hoặc số lớn sẽ được giữ nguyên giống nhau trên mọi nền tảng.

Có thể kiểm thử exit code của một chương trình Java bằng cách chạy nó như tiến trình con và dùng **Process.waitFor()** để lấy mã trả về. Đây cũng là cách kiểm thử phù hợp khi ứng dụng gọi System.exit, vì gọi trực tiếp main trong cùng JVM sẽ làm ảnh hưởng tiến trình kiểm thử.

Không có một bộ mã lỗi Java phổ quát bắt buộc cho mọi ứng dụng. Điều quan trọng là quy ước của ứng dụng phải nhất quán giữa mã nguồn, tài liệu, script, hệ thống giám sát và pipeline CI.

## 11. Các nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu đúng |
|---|---|
| main trả về int sẽ đặt exit code. | Entry point Java truyền thống trả về void; giá trị trả về của phương thức không phải exit code. |
| In dòng “ERROR” thì shell biết chương trình thất bại. | Shell thường dựa vào exit status; chương trình phải trả mã khác 0 khi cần báo lỗi. |
| Có exception ở bất kỳ thread nào thì JVM luôn trả mã khác 0. | Exception ở thread phụ thường chỉ kết thúc thread đó; ứng dụng cần truyền lỗi về luồng điều phối và đặt trạng thái tiến trình rõ ràng. |
| System.exit giống như return khỏi main. | return chỉ rời phương thức; System.exit bắt đầu shutdown toàn bộ JVM. |
| System.exit bảo đảm mọi khối finally chạy. | Không bảo đảm các stack frame được unwind; dùng try-with-resources/finally trước khi yêu cầu shutdown. |
| Runtime.halt là cách shutdown bình thường. | halt bỏ qua shutdown hooks và dừng JVM đột ngột. |
| $? trong PowerShell là exit code dạng số. | $? là Boolean; dùng $LASTEXITCODE cho tiến trình native như java.exe. |
| Pipeline ghi log thành công nghĩa là Java thành công. | Pipeline có thể trả mã của lệnh cuối; dùng pipefail trong Bash khi cần giữ lỗi của Java. |

## 12. Checklist cho ứng dụng Java dòng lệnh

Trước khi đưa ứng dụng vào script hoặc CI, kiểm tra các tình huống sau:

- Chạy với đầu vào hợp lệ và xác nhận exit code bằng **0**.
- Chạy thiếu hoặc sai tham số và xác nhận exit code khác **0**.
- Chạy với tệp cấu hình không tồn tại hoặc dependency bị thiếu; xác nhận lỗi được báo ra standard error.
- Tạo lỗi không được xử lý trong luồng chính và quan sát launcher trả trạng thái lỗi.
- Nếu có worker thread, xác minh lỗi từ worker được truyền về tiến trình chính và không bị che giấu.
- Chạy qua shell hoặc pipeline có ghi log để chắc chắn mã lỗi được giữ lại.
- Kiểm tra hành vi trong CI hoặc máy triển khai, nơi phiên bản Java và shell có thể khác máy phát triển.

Exit code là một phần của giao diện mà ứng dụng Java cung cấp cho hệ điều hành và các công cụ bên ngoài. Khi chương trình dùng 0 cho thành công, mã khác 0 cho lỗi có chủ đích, ghi thông báo đúng luồng và giữ nguyên trạng thái lỗi qua script, Java launcher có thể phối hợp đáng tin cậy với build tool, automation và CI.
