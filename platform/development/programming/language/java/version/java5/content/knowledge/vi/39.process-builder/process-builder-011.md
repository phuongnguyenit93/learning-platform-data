# waitFor, exitValue và mã thoát

## 1. Từ ProcessBuilder đến trạng thái kết thúc

`ProcessBuilder` mô tả lệnh và môi trường cần khởi chạy. Gọi `start()` thành công trả về một `Process` đại diện cho tiến trình hệ điều hành đã được tạo.

Sau bước ấy, tiến trình có thể:

- Vẫn đang chạy.
- Đã kết thúc trước khi chương trình Java kịp kiểm tra.
- Kết thúc thành công hoặc báo lỗi theo quy ước riêng của công cụ.

```text
ProcessBuilder.start()
        |
        +-> không khởi chạy được: xử lý lỗi khởi chạy
        |
        +-> có Process
                |
             đang chạy
                |
             kết thúc
                |
             đọc mã thoát
```

`start()` thành công không có nghĩa công việc của tiến trình con đã thành công. Ta còn phải quan sát vòng đời và diễn giải **mã thoát (exit status/exit code)**.

`waitFor` và `exitValue` vẫn là các API phù hợp trên Java hiện đại. Các chương trình trong bài chạy với Java 17+.

## 2. Ba phương thức dễ nhầm

| Phương thức | Có chờ không? | Kết quả |
| --- | --- | --- |
| waitFor() | Chờ tới khi tiến trình kết thúc, trừ khi luồng đợi bị ngắt | int là mã thoát |
| waitFor(timeout, unit) | Chờ tối đa theo hợp đồng thời hạn | boolean: true nếu đã kết thúc, false nếu hết hạn mà chưa kết thúc |
| exitValue() | Không chờ tiến trình hoàn tất | int nếu đã kết thúc; IllegalThreadStateException nếu vẫn chạy |

Overload có thời hạn được bổ sung sau Java 5 và được dùng phổ biến trên các JDK hiện đại. Nó **không** trả mã thoát.

Ví dụ đọc đúng:

```java
boolean finished = process.waitFor(5, TimeUnit.SECONDS);
if (finished) {
    int code = process.exitValue();
}
```

Đây là đoạn minh họa cần biến process, import TimeUnit và xử lý InterruptedException. Không thể coi finished là “tiến trình thành công”: true chỉ nói tiến trình đã kết thúc.

Hợp đồng các phương thức nằm trong [Process](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Process.html).

## 3. waitFor() đợi kết thúc và trả mã thoát

```java
int code = process.waitFor();
```

Nếu tiến trình còn chạy, luồng gọi bị chặn cho đến khi tiến trình kết thúc hoặc luồng đợi bị ngắt. Nếu đã kết thúc, phương thức trả ngay mã thoát.

Điểm cần hiểu:

1. Nó không nhận kết quả nghiệp vụ trực tiếp từ stdout.
2. Nó không tự biến mã thoát khác 0 thành ngoại lệ Java.
3. Nó không tự có thời hạn.
4. Nó không tự đọc stdout/stderr để tránh đầy pipe.
5. Nó không chờ mọi công việc bên ngoài mà tiến trình từng kích hoạt.

Ví dụ một công cụ báo mã 7: waitFor có thể trả 7 hoàn toàn bình thường. Chính mã Java quyết định mã ấy có được chấp nhận hay phải chuyển thành kết quả thất bại.

Sau khi tiến trình đã kết thúc, có thể gọi lại waitFor hoặc exitValue để quan sát mã thoát; việc đọc không “tiêu thụ” mã và không chạy lại tiến trình.

### Bị ngắt khi đang đợi

waitFor có thể ném InterruptedException. Điều ấy nói về **luồng Java đang đợi**, không có nghĩa tiến trình con đã tự dừng.

Nếu tầng gọi không truyền tiếp ngoại lệ, thường cần khôi phục cờ ngắt bằng Thread.currentThread().interrupt() và đi theo chính sách hủy/cleanup phù hợp. Không bắt rồi tiếp tục dùng một mã thoát giả định.

## 4. waitFor có thời hạn không phải lệnh hủy

```java
boolean finished = process.waitFor(2, TimeUnit.SECONDS);
if (!finished) {
    // Tiến trình chưa được xác nhận đã kết thúc trong lần đợi này.
}
```

false không tự gọi destroy, không đóng stdin và không bảo đảm tiến trình dừng sau khi phương thức trả về. Nó có thể tiếp tục tính toán, giữ tệp hoặc ghi dữ liệu.

Tiến trình cũng có thể kết thúc ngay sau false. Đó là một cuộc đua bình thường quanh thời điểm quan sát, không phải mâu thuẫn của API.

Khi hết hạn, chương trình cần chính sách rõ:

- Tiếp tục theo dõi nếu công việc nền vẫn được phép chạy.
- Yêu cầu kết thúc rồi đợi xác nhận.
- Ghi nhận thất bại có thời hạn và bàn giao quyền quản lý tiến trình cho thành phần khác.
- Thu thập output/chẩn đoán cần thiết trước khi cleanup.

Nếu nhiều bước cùng thuộc một yêu cầu có deadline chung, phải chia ngân sách còn lại. Cấp lại 2 giây cho mỗi lần chờ hoặc mỗi bước cleanup có thể khiến tổng thời gian vượt xa 2 giây.

Timeout cũng không phải bảo đảm thời gian thực cứng. Bộ lập lịch, thời gian thực thi xung quanh và cleanup có thể làm toàn bộ thao tác kéo dài hơn giá trị timeout được truyền.

## 5. exitValue() chỉ đọc kết quả đã có

```java
int code = process.exitValue();
```

Nếu tiến trình vẫn chạy, phương thức ném `IllegalThreadStateException`. Nó không trả -1, null hay một mã đặc biệt để báo “chưa xong”.

Không nhầm với `IllegalStateException` chung hay lỗi do chương trình con ném ra. Tên ngoại lệ có chữ Thread, nhưng ở đây nó được phương thức Process dùng để báo tiến trình chưa kết thúc.

Có thể dùng sau:

- waitFor() đã trả mã.
- waitFor(timeout, unit) đã trả true.
- Một cơ chế theo dõi hoàn tất khác đã xác nhận Process kết thúc.

Không nên quay liên tục gọi exitValue rồi bắt ngoại lệ để đợi tiến trình. Dùng API chờ phù hợp giúp biểu đạt đúng ý định và tránh vòng quay tiêu CPU.

### isAlive là ảnh chụp trạng thái

Nếu isAlive trả true, tiến trình có thể kết thúc ngay sau đó. Vì thế đoạn kiểm tra “còn sống rồi gọi exitValue” vẫn không phải một cơ chế chờ.

Khi cần đợi với giới hạn, waitFor có thời hạn diễn đạt trực tiếp hơn việc tự ghép nhiều lần kiểm tra trạng thái và sleep.

## 6. Mã thoát: quy ước của công cụ, không phải boolean chung

Quy ước phổ biến là 0 biểu thị kết thúc bình thường/thành công, còn giá trị khác 0 biểu thị một loại bất thường. Nhưng **nghĩa cụ thể của từng mã thuộc chương trình được chạy**.

Ví dụ có công cụ dùng một mã khác 0 để báo “không tìm thấy kết quả”, và một mã khác nữa để báo lỗi thao tác. Nếu “không tìm thấy” là kết quả nghiệp vụ hợp lệ, bên gọi có thể cần phân biệt nó với lỗi hệ thống.

Do đó:

```java
int code = process.waitFor();
if (code != 0) {
    // Chưa đủ thông tin để khẳng định mọi công cụ đều có cùng ý nghĩa lỗi.
}
```

Hãy tra hợp đồng của công cụ, thu stdout/stderr liên quan và ánh xạ mã vào kết quả ứng dụng.

Không suy ra thành công chỉ vì:

- stdout không rỗng.
- stderr rỗng.
- Tiến trình đã kết thúc.
- Không có ngoại lệ Java từ waitFor.
- Một tệp kết quả có tồn tại từ lần chạy trước.

Mã 0 cũng không tự chứng minh nội dung output đúng yêu cầu của ứng dụng. Nếu có hợp đồng dữ liệu hoặc artifact cần kiểm chứng, kiểm tra thêm theo hợp đồng ấy.

[System.exit](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/System.html#exit(int)) cho phép chương trình Java chỉ định trạng thái kết thúc. Việc giá trị được quan sát ra sao còn chịu quy tắc nền tảng; không dùng mã âm hoặc số rất lớn rồi giả định mọi hệ điều hành giữ nguyên toàn bộ ý nghĩa.

## 7. Phân biệt lỗi khởi chạy và kết thúc với mã lỗi

| Tình huống | Dấu hiệu chính |
| --- | --- |
| Không mở/khởi chạy được executable | start có thể ném IOException hoặc lỗi phù hợp theo hợp đồng |
| Executable đã chạy nhưng báo lỗi nghiệp vụ | Có Process, sau đó có mã thoát theo công cụ |
| Tiến trình vẫn chạy quá thời gian cho phép | waitFor(timeout, unit) có thể trả false |
| Luồng Java bị ngắt khi đợi | InterruptedException |
| Đọc mã thoát quá sớm | IllegalThreadStateException từ exitValue |

Một tiến trình Java con có thể được tạo thành công nhưng JVM con không tải được lớp main. Khi ấy phía cha vẫn có Process và nhận một mã kết thúc; đó không nhất thiết là lỗi start.

Nếu thông qua shell hoặc một chương trình trung gian, Process thường đại diện cho chương trình đã khởi chạy trực tiếp. Mã của shell có thể tuân theo quy tắc shell và không tự tổng hợp đúng tất cả tiến trình trong pipeline theo yêu cầu của bạn.

Với ví dụ học tập dưới đây, ta khởi chạy trực tiếp executable Java với danh sách đối số tách riêng, không qua shell. [ProcessBuilder](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ProcessBuilder.html) mô tả vai trò start, command và chuyển hướng I/O.

## 8. Thí nghiệm đầy đủ: mã 0, mã 7 và tiến trình chưa thoát

Một lớp được dùng ở hai vai:

- Không có đối số: tiến trình cha chạy thí nghiệm.
- Có đối số: tiến trình Java con thực hiện hành vi được yêu cầu.

Với chế độ hold, tiến trình con đợi dữ liệu/EOF từ stdin, nên cha kiểm tra được trạng thái chưa kết thúc mà không dựa vào một khoảng sleep may rủi.

Lưu thành `ProcessExitDemo.java`:

```java
import java.io.IOException;
import java.nio.file.Path;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

public class ProcessExitDemo {
    private static Process startChild(String mode) throws IOException {
        String executable =
                System.getProperty("os.name").startsWith("Windows")
                        ? "java.exe" : "java";

        String java = Path.of(
                System.getProperty("java.home"), "bin", executable)
                .toString();

        return new ProcessBuilder(
                java,
                "-cp", System.getProperty("java.class.path"),
                ProcessExitDemo.class.getName(),
                mode)
                .redirectOutput(ProcessBuilder.Redirect.DISCARD)
                .redirectError(ProcessBuilder.Redirect.INHERIT)
                .start();
    }

    private static int awaitExit(Process process) throws Exception {
        if (!process.waitFor(10, TimeUnit.SECONDS)) {
            throw new TimeoutException("child did not exit");
        }
        return process.exitValue();
    }

    private static void cleanup(Process process) throws Exception {
        try {
            if (process.isAlive()) {
                process.destroyForcibly();
                if (!process.waitFor(5, TimeUnit.SECONDS)) {
                    throw new IllegalStateException(
                            "child still alive after cleanup request");
                }
            }
        } finally {
            process.getOutputStream().close();
            process.getInputStream().close();
            process.getErrorStream().close();
        }
    }

    public static void main(String[] args) throws Exception {
        if (args.length == 1) {
            if ("hold".equals(args[0])) {
                System.in.read();
                System.exit(3);
            } else {
                System.exit(Integer.parseInt(args[0]));
            }
            return;
        }

        for (String status : new String[]{"0", "7"}) {
            Process child = startChild(status);
            try {
                child.getOutputStream().close();
                int code = awaitExit(child);

                System.out.println("Requested " + status
                        + " -> code " + code);
                System.out.println("Read again: " + child.exitValue());
            } finally {
                cleanup(child);
            }
        }

        Process held = startChild("hold");
        try {
            try {
                held.exitValue();
            } catch (IllegalThreadStateException e) {
                System.out.println("Early exitValue: "
                        + e.getClass().getSimpleName());
            }

            System.out.println("Finished at immediate check: "
                    + held.waitFor(0, TimeUnit.NANOSECONDS));

            held.getOutputStream().close();
            System.out.println("Code after stdin EOF: "
                    + awaitExit(held));
        } finally {
            cleanup(held);
        }
    }
}
```

Chạy bằng JDK 17+ trong thư mục chứa mã nguồn:

```shell
javac ProcessExitDemo.java
java ProcessExitDemo
```

Stdout khi tiến trình con được khởi chạy đúng và kết thúc trong thời hạn:

```text
Requested 0 -> code 0
Read again: 0
Requested 7 -> code 7
Read again: 7
Early exitValue: IllegalThreadStateException
Finished at immediate check: false
Code after stdin EOF: 3
```

Các mốc quan trọng:

1. Hai con đầu tự gọi System.exit với mã nhỏ, dễ quan sát.
2. Không có ngoại lệ từ việc con trả mã 7; cha chủ động in và diễn giải mã.
3. Con hold chưa thể hoàn tất bình thường vì stdin vẫn mở và chưa có dữ liệu.
4. exitValue gọi sớm báo tiến trình chưa kết thúc.
5. waitFor bằng 0 là phép kiểm tra ngay, trả false trong thí nghiệm này.
6. Cha đóng đầu ghi stdin của con, tạo EOF; con đọc xong và tự kết thúc với mã 3.
7. Mỗi Process đều được cleanup nếu đường xử lý thất bại.

System.exit trong nhánh có đối số chạy ở JVM con. Không đặt lệnh kết thúc JVM đó vào nhánh cha vì sẽ dừng chính chương trình điều phối.

Ví dụ lấy executable từ java.home và truyền classpath hiện hành. Nó giả định môi trường JDK có executable Java tại bin và lớp đã biên dịch nằm trong classpath được truyền. Nếu chuyển sang môi trường đóng gói khác, cần xác định lệnh/classpath theo cách triển khai thực tế.

## 9. Đừng chờ kết thúc trong khi con bị nghẽn stdout/stderr

Mặc định, stdout và stderr của tiến trình con có thể được nối qua pipe. Bộ đệm pipe có giới hạn.

Một vòng chờ thường gặp:

```text
Cha: waitFor đợi con kết thúc
Con: ghi quá nhiều output -> pipe đầy -> đợi cha đọc
Cha không đọc vì đang đợi con
```

waitFor không tự tháo nút thắt này. Có thể cần:

- Đọc/drain stdout và stderr đồng thời theo thiết kế.
- Chuyển hướng ra tệp.
- Kế thừa I/O phù hợp.
- Gộp hai luồng khi hợp đồng output cho phép, rồi đọc liên tục.

Trong thí nghiệm, stdout con được DISCARD và stderr được INHERIT, nên cha không giữ hai pipe output chưa đọc. Chuyển hướng ấy phục vụ một ví dụ chỉ quan tâm mã thoát; ứng dụng cần output phải thu đúng dữ liệu thay vì bỏ đi.

Cũng không thay bằng đọc toàn bộ stdout tới EOF rồi mới waitFor với timeout và nghĩ rằng toàn thao tác đã có thời hạn. Bước đọc trước đó có thể tự chặn lâu nếu con chưa đóng stream. Ngân sách và điều phối I/O cần bao phủ mọi bước chờ liên quan.

## 10. Dừng tiến trình và mã thoát sau khi dừng

destroy và destroyForcibly yêu cầu kết thúc tiến trình theo cơ chế được nền tảng hỗ trợ. Không giả định destroy luôn là “dừng mềm giống nhau” trên mọi hệ điều hành.

Sau yêu cầu dừng, cần đợi xác nhận kết thúc trước khi lấy mã. Ngay cả destroyForcibly cũng không phải bằng chứng Process đã dừng đúng tại thời điểm phương thức trả về.

Không khẳng định một mã cố định như 137, 143 hay 1 cho mọi JVM và mọi hệ điều hành sau khi dừng. Hãy ghi trạng thái thực tế và nguyên nhân yêu cầu dừng trong kết quả điều phối, tách khỏi quy ước mã của một lần hoàn tất bình thường.

Ngoài ra, dừng Process cha không tự bảo đảm mọi tiến trình con/cháu do nó sinh ra đã dừng. waitFor và exitValue áp dụng cho Process đang được theo dõi; quản lý cả cây tiến trình là một yêu cầu riêng.

Các thời hạn 10 và 5 giây trong mã chỉ phục vụ thí nghiệm. Helper cleanup minh họa yêu cầu dừng và xác nhận, không phải một thư viện quản lý mọi tình huống lỗi I/O, ngắt và cây tiến trình.

## 11. Thiết kế một kết quả chạy có ý nghĩa

Một kết quả điều phối thường cần nhiều hơn một int:

| Trường thông tin | Câu hỏi trả lời |
| --- | --- |
| Khởi chạy thành công chưa | Có thật sự tạo được Process không? |
| Đã kết thúc hay chưa | Có mã thoát cuối cùng chưa? |
| Mã thoát | Công cụ báo trạng thái nào? |
| Có hết hạn hoặc bị hủy không | Vì sao bên gọi kết thúc lần đợi? |
| Output/chẩn đoán | Công cụ giải thích gì, dữ liệu cần dùng là gì? |
| Cleanup đã được xác nhận chưa | Có còn công việc nền cần quản lý không? |

Đừng gán -1 làm “mã thoát giả” cho timeout rồi trộn với mã thật từ công cụ mà không có kiểu/kênh trạng thái phân biệt. Timeout là kết quả của chính sách chờ; mã thoát là kết quả của tiến trình đã kết thúc.

Nếu nghiệp vụ coi một số mã khác 0 là chấp nhận được, thể hiện tập mã đó rõ ràng thay vì rải nhiều điều kiện khó đối chiếu.

## 12. Tự kiểm tra

**waitFor(5, SECONDS) trả true có nghĩa thành công không?**  
Không. Nó xác nhận tiến trình đã kết thúc; cần đọc và diễn giải mã thoát.

**exitValue khi tiến trình đang chạy trả -1 không?**  
Không. Nó ném IllegalThreadStateException.

**Mã thoát 7 có tự làm waitFor ném IOException không?**  
Không. Lỗi khởi chạy và tiến trình đã chạy rồi báo mã 7 là hai tình huống khác nhau.

**Timeout có tự dừng tiến trình không?**  
Không. Cần chính sách quản lý tiếp hoặc yêu cầu dừng và xác nhận.

**Tiến trình đã kết thúc có nghĩa mọi output đã được ứng dụng xử lý xong không?**  
Không. Việc thu và xử lý output có vòng đời riêng, phải phối hợp theo thiết kế.

Cách đọc đúng là: waitFor dùng để xác nhận kết thúc, exitValue đọc mã của kết thúc đó, còn ý nghĩa thành công/thất bại thuộc hợp đồng công cụ và kết quả nghiệp vụ mà bên gọi cần kiểm chứng.
