# ProcessBuilder và mô hình tạo tiến trình con

## 1. Vì sao cần tiến trình con?

Một chương trình Java đôi khi cần dùng một công cụ có sẵn ngoài JVM: trình chuyển đổi tệp, công cụ dòng lệnh hoặc một chương trình Java khác. Khi đó, thay vì viết lại công cụ, chương trình cha có thể yêu cầu hệ điều hành khởi chạy một **tiến trình con (child process)**.

`ProcessBuilder` mô tả cách khởi chạy; `Process` là đối tượng Java dùng để theo dõi và điều khiển tiến trình đã được tạo. Hai đối tượng có vai trò khác nhau:

```text
ProcessBuilder: cấu hình lệnh, đối số, môi trường, thư mục, luồng dữ liệu
        |
        | start()
        v
Hệ điều hành khởi chạy chương trình con
        |
        v
Process: theo dõi tiến trình, trao đổi dữ liệu, chờ kết thúc, lấy mã thoát
```

Chỉ tạo `new ProcessBuilder(...)` chưa làm chương trình bên ngoài chạy. Điểm phát sinh tác động là `start()`.

## 2. Tiến trình con khác luồng Java

| Nội dung | Luồng trong JVM hiện tại | Tiến trình con |
|---|---|---|
| Nơi thực thi | Trong cùng tiến trình JVM | Một tiến trình hệ điều hành khác |
| Đối tượng Java | Có thể dùng chung đối tượng trong heap, cần đồng bộ thích hợp | Không tự dùng chung heap với tiến trình cha |
| Điểm bắt đầu | Một tác vụ Java như `Runnable` | Một chương trình thực thi và các đối số |
| Kết quả/lỗi | Theo cơ chế gọi hàm, tác vụ và ngoại lệ Java | Qua đầu ra, mã thoát hoặc giao thức trao đổi |
| Vòng đời | Gắn với cơ chế luồng của tiến trình hiện tại | Cần theo dõi riêng vòng đời tiến trình con |

Nếu chạy `java` làm chương trình con, hệ điều hành tạo một JVM khác. Biến `static`, đối tượng đang sống và ngoại lệ trong JVM con không tự trở thành trạng thái hay ngoại lệ của JVM cha.

Ví dụ, một công cụ con gặp lỗi rồi thoát với mã 2. JVM cha vẫn có thể đang chạy bình thường; cha phải đọc mã thoát để biết công cụ không hoàn thành như mong đợi. Ngược lại, không tìm thấy tệp thực thi có thể làm chính lời gọi `start()` thất bại ngay từ đầu.

Không mặc định tiến trình con có cùng vòng đời với đối tượng `Process`. Bỏ tham chiếu Java không phải là thao tác dừng tiến trình. Xem [API Process](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Process.html).

## 3. ProcessBuilder là một bản cấu hình có thể thay đổi

Các nhóm cấu hình chính gồm:

| Thuộc tính | Ý nghĩa |
|---|---|
| Lệnh và danh sách đối số | Chương trình cần chạy và dữ liệu truyền khi khởi động |
| Thư mục làm việc | Nơi tiến trình con dùng làm điểm xuất phát cho các đường dẫn tương đối |
| Biến môi trường | Các cặp tên–giá trị mà tiến trình con nhận lúc khởi động |
| Đầu vào chuẩn | Tiến trình con đọc dữ liệu từ đâu |
| Đầu ra chuẩn và đầu ra lỗi | Dữ liệu tiến trình con ghi sẽ đi đâu |

Ban đầu, builder có một bản sao môi trường của tiến trình hiện tại. Thư mục làm việc mặc định là thư mục làm việc hiện tại. Thay đổi cấu hình builder ảnh hưởng đến những lần `start()` tiếp theo; không sửa ngược tiến trình đã chạy hoặc môi trường của JVM cha. Cùng một builder có thể gọi `start()` nhiều lần, mỗi lần tạo một tiến trình mới. Xem [API ProcessBuilder](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ProcessBuilder.html).

Có thể hình dung:

```text
builder với cấu hình A → start() → tiến trình P1 dùng A
đổi builder sang B    → start() → tiến trình P2 dùng B

P1 vẫn dùng cấu hình đã nhận khi được tạo.
```

Đây không phải “khởi động lại P1” hoặc “gửi lệnh mới cho P1”. Muốn trao đổi khi một tiến trình đang chạy phải dùng luồng dữ liệu hoặc một giao thức mà chương trình con hỗ trợ.

Vì builder có trạng thái thay đổi được và không tự đồng bộ mọi truy cập, cách dễ kiểm soát là tạo một builder riêng cho mỗi lần thực thi trong mã ứng dụng. Không để nhiều luồng đồng thời sửa cùng một builder.

## 4. Lệnh là danh sách chương trình và đối số

Với một chương trình Java con, có thể xây danh sách như sau; đây là minh họa cấu trúc, không phải chương trình độc lập:

```java
ProcessBuilder builder = new ProcessBuilder(
        javaExecutable,
        "-cp", classPath,
        "MyChildProgram",
        "hello child");
```

Phần tử đầu là chương trình thực thi. Các phần tử sau là đối số theo thứ tự. Chuỗi `"hello child"` là một phần tử, nên biểu diễn một đối số có khoảng trắng.

Không ghép toàn bộ thành `"java -cp ... MyChildProgram hello child"` rồi kỳ vọng builder tự tách như một trình thông dịch lệnh. Cũng không tự thêm dấu ngoặc kép vào giá trị đối số chỉ để xử lý đường dẫn có khoảng trắng. Hãy truyền đường dẫn và đối số thành từng phần tử; cách công cụ đích xử lý đối số vẫn phải theo giao diện của công cụ đó.

### Builder không mặc định là một shell

Các dấu như `|`, `>` hoặc `&&` không tự biến thành đường ống, chuyển hướng hay chuỗi lệnh shell. Những lệnh dựng sẵn của shell cũng không nhất thiết là tệp thực thi độc lập.

Nếu chủ động khởi chạy một shell, ta đã thêm một tầng phân tích cú pháp và hành vi phụ thuộc hệ điều hành. Với nhu cầu chạy một chương trình cụ thể, việc giữ danh sách đối số tường minh giúp tránh nhiều lỗi ghép chuỗi. Dù vậy, dữ liệu truyền vào vẫn có thể là tùy chọn có ý nghĩa với công cụ đích, nên cần kiểm tra theo hợp đồng của công cụ; danh sách đối số không tự thay thế việc kiểm tra dữ liệu.

## 5. Start thành công chưa có nghĩa tác vụ thành công

Một vòng đời tối thiểu gồm:

1. Xây cấu hình.
2. Gọi `start()`.
3. Xử lý đầu vào/đầu ra theo lựa chọn.
4. Chờ hoặc theo dõi kết thúc.
5. Kiểm tra mã thoát và kết quả.
6. Dọn tài nguyên, xử lý quá thời gian nếu cần.

Ba trạng thái sau khác nhau:

| Trạng thái | Dấu hiệu | Hướng xử lý |
|---|---|---|
| Không khởi chạy được | `start()` có thể ném `IOException` | Kiểm tra đường dẫn, thư mục, quyền và điều kiện hệ điều hành |
| Đã chạy nhưng báo thất bại | Tiến trình kết thúc với mã thoát không được công cụ coi là thành công | Đọc chẩn đoán, xử lý theo giao diện công cụ |
| Chưa kết thúc trong thời gian cho phép | `waitFor(timeout, unit)` trả `false` | Quyết định dừng hoặc theo dõi tiếp; không đọc mã thoát như thể đã xong |

`start()` trả về một `Process` sau khi khởi chạy; nó không có nhiệm vụ chờ toàn bộ công việc con hoàn tất. Tiến trình có thể còn chạy hoặc đã kết thúc rất nhanh trước khi cha bắt đầu quan sát.

`waitFor()` chặn **luồng đang gọi** đến khi tiến trình kết thúc. Nó không phải phép “chạy chương trình”: chương trình đã được khởi chạy trước đó. Dạng có thời hạn chờ trả boolean; mã thoát lấy sau khi đã biết tiến trình kết thúc. Gọi `exitValue()` khi tiến trình còn sống gây `IllegalThreadStateException`.

Mã 0 thường biểu thị thành công, nhưng phải đọc quy ước của chương trình đích. Không coi mọi mã khác 0 là cùng một loại lỗi và không coi thông báo in ra là bằng chứng đủ thay cho hợp đồng kết quả.

## 6. Nhìn các luồng từ phía chương trình cha

Tên getter của `Process` được đặt theo thao tác của **cha**, không phải thao tác của con:

| Luồng của tiến trình con | Cha dùng gì khi cấu hình mặc định là pipe? |
|---|---|
| stdin — con đọc | Cha ghi qua `process.getOutputStream()` |
| stdout — con ghi đầu ra | Cha đọc qua `process.getInputStream()` |
| stderr — con ghi chẩn đoán | Cha đọc qua `process.getErrorStream()` |

Điều này giải thích vì sao `getOutputStream()` lại đưa dữ liệu **vào** chương trình con.

Các pipe có bộ đệm hữu hạn. Nếu con ghi nhiều mà cha không đọc, con có thể bị chặn; nếu cha lại chỉ chờ con thoát, cả hai có thể chờ nhau. Vì vậy, ngay trong bài mô hình, cần chọn đường đi cho dữ liệu thay vì bỏ qua đầu ra.

Ví dụ dưới chuyển đầu ra tới nơi stdout của cha đang đi, đồng thời gộp stderr vào stdout. Nhờ đó cha không cần tự đọc pipe đầu ra trong ví dụ. Khi cần thu thập nội dung đầu ra để xử lý, phải thiết kế việc đọc đồng thời và giới hạn dung lượng phù hợp.

## 7. Ví dụ đầy đủ: JVM cha khởi chạy một JVM con

Lưu tệp `ProcessBuilderModelDemo.java` và dùng JDK 17 trở lên. Chương trình xác định tệp `java` từ `java.home`, không phụ thuộc việc lệnh `java` của con có xuất hiện trong `PATH` hay không.

```java
import java.nio.file.Path;
import java.util.Locale;
import java.util.concurrent.TimeUnit;

public class ProcessBuilderModelDemo {
    public static void main(String[] args) throws Exception {
        if (args.length == 2 && args[0].equals("--child")) {
            System.out.println("child argument=" + args[1]);
            return;
        }

        boolean windows = System.getProperty("os.name")
                .toLowerCase(Locale.ROOT).startsWith("windows");
        Path javaExecutable = Path.of(
                System.getProperty("java.home"),
                "bin", windows ? "java.exe" : "java");

        ProcessBuilder builder = new ProcessBuilder(
                javaExecutable.toString(),
                "-cp", System.getProperty("java.class.path"),
                ProcessBuilderModelDemo.class.getName(),
                "--child", "hello child");
        builder.redirectErrorStream(true);
        builder.redirectOutput(ProcessBuilder.Redirect.INHERIT);

        Process child = builder.start();
        try {
            child.getOutputStream().close();
            boolean finished = child.waitFor(10, TimeUnit.SECONDS);
            if (!finished) {
                child.destroyForcibly();
                child.waitFor(5, TimeUnit.SECONDS);
                throw new IllegalStateException("Child process timed out");
            }
            int exitCode = child.exitValue();
            if (exitCode != 0) {
                throw new IllegalStateException(
                        "Child failed with exit code " + exitCode);
            }
            System.out.println("child exit=" + exitCode);
            System.out.println("parent finished");
        } finally {
            if (child.isAlive()) {
                child.destroyForcibly();
                child.waitFor(5, TimeUnit.SECONDS);
            }
        }
    }
}
```

Biên dịch và chạy từ thư mục chứa tệp:

```shell
javac -encoding UTF-8 --release 17 ProcessBuilderModelDemo.java
java ProcessBuilderModelDemo
```

Stdout khi tiến trình con khởi chạy và hoàn thành trong thời hạn:

```text
child argument=hello child
child exit=0
parent finished
```

### Giải thích luồng chạy

- JVM cha không có đối số `--child`, nên đi vào nhánh xây builder.
- Builder gọi chính tệp thực thi Java trong bản Java hiện dùng, truyền classpath hiện tại và tên lớp cần chạy.
- JVM con nhận hai đối số `--child` và `hello child`, in một dòng rồi kết thúc. Nhờ nhánh `return`, nó không tiếp tục tạo một JVM con khác.
- Cha chờ con xong, kiểm tra mã 0 rồi mới in hai dòng còn lại. Việc chờ này làm thứ tự đầu ra của ví dụ có thể đối chiếu được.

Ví dụ giữ nguyên thư mục làm việc. Nếu sau này đổi `builder.directory(...)`, các mục classpath tương đối cũng có thể được hiểu theo thư mục mới; khi đó phải chuẩn bị classpath phù hợp thay vì sao chép mù quáng cấu hình cũ.

### Vì sao đóng đầu vào của con?

Mã không gửi dữ liệu qua stdin, nên cha đóng `child.getOutputStream()` để báo hết đầu vào. Một công cụ khác có thể chờ đọc stdin đến hết trước khi hoàn thành; không đóng có thể khiến nó chờ mãi.

Trong ví dụ, stdout và stderr đã được cấu hình gộp/chuyển tiếp, nên không gọi `getInputStream()` để thu thập đầu ra nữa. Việc dữ liệu hiện trên màn hình là kết quả của cấu hình chuyển hướng, không phải `waitFor` tự in nó.

### Thời hạn chờ và dừng tiến trình

Nếu quá 10 giây, mã yêu cầu dừng cưỡng bức rồi chờ thêm một khoảng hữu hạn. `destroyForcibly()` không nên được hiểu là “đã chắc chắn dừng ngay tại dòng gọi”. Muốn xác nhận kết thúc phải quan sát hoặc chờ; nếu thời gian dọn dẹp cũng hết thì hệ thống thật cần chính sách xử lý tiếp.

Khối `finally` cố dọn tiến trình còn sống khi nhánh xử lý rời đi. Ví dụ chỉ tạo một tiến trình con đơn giản; nó không phải công cụ quản lý cả cây tiến trình nếu chương trình con lại tự sinh nhiều tiến trình khác.

`main` khai báo `throws Exception` để ví dụ tập trung vào mô hình. Trong dịch vụ thực tế, cần xử lý riêng lỗi khởi chạy, lỗi kết quả và `InterruptedException`; khi bắt ngắt mà không truyền tiếp, phải giữ đúng chính sách ngắt của luồng, thường bằng cách khôi phục cờ ngắt.

## 8. Những nhầm lẫn dễ gặp

| Nhầm lẫn | Điều xảy ra thực tế |
|---|---|
| Tạo builder là chương trình đã chạy | Chưa chạy cho đến `start()` |
| Sửa builder sẽ đổi tiến trình đang chạy | Chỉ tác động các lần khởi chạy sau |
| `Process` chính là một luồng Java | Nó đại diện cho tiến trình hệ điều hành |
| Tiến trình con ném ngoại lệ thì cha tự bắt được | Cha cần quan sát đầu ra, mã thoát hoặc giao thức trao đổi |
| `waitFor` sẽ tự xử lý stdout/stderr | Không; dữ liệu phải được đọc hoặc chuyển hướng |
| Bỏ đối tượng `Process` thì con tự dừng | Vòng đời tiến trình không phụ thuộc như vậy |
| Dừng tiến trình được theo dõi sẽ luôn dừng mọi hậu duệ | Cần quản lý cây tiến trình riêng theo yêu cầu thực tế |

## 9. Bài thực hành

1. Đổi `"hello child"` thành một chuỗi có nhiều khoảng trắng. Xác nhận nó vẫn là một đối số; giải thích vai trò của danh sách lệnh.
2. Thêm một nhánh trong JVM con cố ý kết thúc với mã khác 0. Quan sát vì sao cha vào nhánh kiểm tra mã thoát thay vì `start()` thất bại.
3. Cho JVM con chờ lâu hơn thời hạn, rồi kiểm tra nhánh quá thời gian. Giữ việc dọn tiến trình trong `finally`.
4. Mô tả trước khi viết mã: nếu đầu ra con lớn, bạn sẽ chuyển ra tệp, chuyển tiếp hay đọc để xử lý? Chỉ ra ai chịu trách nhiệm tiêu thụ dữ liệu.

Mô hình cần nắm là builder giữ cấu hình, `start()` tạo tiến trình và `Process` giúp cha quản lý tiến trình đó. Kết quả công việc chỉ được xác nhận sau khi xem đúng đầu ra, mã thoát và điều kiện kết thúc của chương trình con.
