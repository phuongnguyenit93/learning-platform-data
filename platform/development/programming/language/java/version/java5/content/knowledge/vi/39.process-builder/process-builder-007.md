# Khởi động bằng start và xử lý lỗi tạo tiến trình

`ProcessBuilder` mô tả cách một tiến trình sẽ được tạo. Chỉ khi gọi `start()`, Java mới yêu cầu hệ điều hành khởi chạy chương trình theo cấu hình đó.

Điểm cần phân biệt là **không tạo được tiến trình** và **đã tạo được tiến trình nhưng chương trình chạy thất bại**. Hai tình huống xảy ra ở thời điểm khác nhau, cung cấp thông tin khác nhau và cần cách xử lý khác nhau.

Bài dùng các API vẫn áp dụng trong Java hiện đại; ví dụ chạy bằng Java 17 trở lên.

## 1. Từ cấu hình đến Process

```java
// Đoạn minh họa bên trong một phương thức có xử lý IOException.
ProcessBuilder builder = new ProcessBuilder("tool", "--version");
Process process = builder.start();
```

Dòng đầu tạo đối tượng cấu hình trong JVM. Nó chưa chứng minh `tool` tồn tại, có quyền thực thi hoặc chạy được trong thư mục đã chọn.

Dòng thứ hai thực hiện thao tác khởi chạy. Nếu thành công, kết quả là một `Process` dùng để theo dõi và giao tiếp với tiến trình con.

```text
Tạo ProcessBuilder
        |
        v
Cấu hình lệnh, thư mục, môi trường, luồng
        |
        v
Gọi start()
        |
        +-- ném ngoại lệ -> xử lý lỗi cấu hình/khởi chạy
        |
        +-- trả Process -> theo dõi tiến trình đã được khởi chạy
                                |
                                v
                         lấy kết quả sau khi kết thúc
```

Hợp đồng chi tiết được mô tả trong [ProcessBuilder.start](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/ProcessBuilder.html#start()).

### start không đợi công việc hoàn thành

`start()` không có nghĩa là “chạy xong”. Khi nhận `Process`, chương trình con có thể đang chạy, hoặc đã kết thúc rất nhanh.

Do đó:

- Không mặc nhiên cho rằng `process.isAlive()` luôn là `true` ngay sau `start()`.
- Không gọi `exitValue()` với giả định tiến trình đã kết thúc.
- Không coi việc nhận được `Process` là bằng chứng tác vụ nghiệp vụ thành công.

Muốn biết mã thoát sau khi tiến trình kết thúc, dùng cơ chế chờ hoặc theo dõi phù hợp.

## 2. Những lỗi nào có thể xảy ra ngay khi start?

| Nhóm tình huống | Ví dụ | Cách hiểu |
| --- | --- | --- |
| Không tìm thấy chương trình | Đường dẫn sai, chương trình chưa cài | Không khởi chạy được chương trình đã cấu hình |
| Không được phép chạy | Quyền hệ điều hành không cho phép | Cần sửa quyền hoặc môi trường triển khai |
| Thư mục làm việc không hợp lệ | Thư mục không tồn tại | Cấu hình tiến trình không dùng được |
| Tài nguyên I/O không mở được | Tệp chuyển hướng không mở được | Khởi chạy bị chặn bởi cấu hình hoặc tài nguyên |
| Đối số không hợp lệ với hệ điều hành | Chuỗi chứa ký tự NUL | Dữ liệu không biểu diễn được cho lệnh native |
| Danh sách lệnh không hợp lệ | Rỗng hoặc có phần tử null | Lỗi cấu hình trong mã Java |

Các lỗi I/O hoặc lỗi khởi chạy phụ thuộc hệ điều hành thường được báo bằng `IOException` hoặc lớp con. Không giả định lúc nào Java cũng trả đúng `FileNotFoundException`, kể cả khi nguyên nhân là thiếu tệp.

Cấu hình danh sách rỗng được `start()` báo bằng `IndexOutOfBoundsException`; phần tử null được báo bằng `NullPointerException`. Đây là lỗi cấu hình lập trình, khác với một tệp thực thi bị thiếu.

`UnsupportedOperationException` có thể xuất hiện khi nền tảng không hỗ trợ tạo tiến trình. Không phải mọi môi trường chạy Java đều có cùng khả năng hệ điều hành.

Một số kiểm tra chỉ diễn ra khi gọi `start()`. Không suy ra rằng “constructor không báo lỗi” thì cấu hình đã hợp lệ.

## 3. Lỗi khởi chạy khác mã thoát khác 0

Xét hai tình huống:

### Không có tệp thực thi

```text
Java gọi start()
        |
        v
IOException
```

Không có giá trị `Process` được trả về cho lời gọi đó. Không có mã thoát để đọc từ một biến `Process` chưa được gán.

### Chương trình chạy rồi báo lỗi

```text
Java gọi start()
        |
        v
Nhận Process
        |
        v
Chương trình kiểm tra dữ liệu và kết thúc với mã 7
        |
        v
waitFor() trả 7
```

`start()` không phải ném `IOException` chỉ vì chương trình con chọn mã thoát 7.

Mã 0 thường biểu thị kết thúc bình thường, nhưng ý nghĩa cụ thể của mã thoát phải theo hợp đồng công cụ. Một số chương trình dùng mã khác 0 cho một kết quả truy vấn thông thường, không chỉ cho lỗi hạ tầng.

Nếu khởi chạy shell hoặc một trình bao, việc shell khởi chạy thành công cũng không chứng minh lệnh bên trong tồn tại. Shell có thể trả mã khác 0 và ghi thông tin vào stderr. Vì vậy cần xác định tiến trình mà `Process` đang đại diện.

## 4. Ví dụ đầy đủ: quan sát cả hai phía của ranh giới start

Lưu thành **ProcessStartDemo.java**. Chương trình tự khởi chạy một JVM con nên không phụ thuộc công cụ dòng lệnh cài thêm.

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Arrays;
import java.util.List;

public class ProcessStartDemo {
    static String javaExecutable() {
        boolean windows = System.getProperty("os.name").startsWith("Windows");
        return Path.of(System.getProperty("java.home"),
                "bin", windows ? "java.exe" : "java").toString();
    }

    static ProcessBuilder childBuilder(int exitCode) {
        return new ProcessBuilder(
                javaExecutable(),
                "-cp",
                System.getProperty("java.class.path"),
                ProcessStartDemo.class.getName(),
                "--child",
                Integer.toString(exitCode)
        ).redirectOutput(ProcessBuilder.Redirect.DISCARD)
                .redirectError(ProcessBuilder.Redirect.DISCARD);
    }

    static void runChild(String label, ProcessBuilder builder)
            throws IOException, InterruptedException {
        Process process = builder.start();
        System.out.println(label + ": start returned Process");
        process.getOutputStream().close();
        int code = process.waitFor();
        System.out.println(label + ": exit = " + code);
    }

    public static void main(String[] args) throws Exception {
        if (args.length == 2 && args[0].equals("--child")) {
            System.exit(Integer.parseInt(args[1]));
            return;
        }

        Path temporary = Files.createTempDirectory("process-start-demo-");
        try {
            ProcessBuilder missing = new ProcessBuilder(
                    temporary.resolve("missing-program.exe").toString());
            System.out.println("missing program: builder created");
            try {
                missing.start();
                throw new AssertionError("Expected start failure");
            } catch (IOException ex) {
                System.out.println("missing program: IOException");
            }

            ProcessBuilder badDirectory = childBuilder(0)
                    .directory(temporary.resolve("missing-directory").toFile());
            try {
                badDirectory.start();
                throw new AssertionError("Expected directory failure");
            } catch (IOException ex) {
                System.out.println("missing directory: IOException");
            }

            try {
                new ProcessBuilder(List.of()).start();
                throw new AssertionError("Expected empty command failure");
            } catch (IndexOutOfBoundsException ex) {
                System.out.println("empty command: rejected");
            }

            try {
                new ProcessBuilder(Arrays.asList(
                        javaExecutable(), (String) null)).start();
                throw new AssertionError("Expected null argument failure");
            } catch (NullPointerException ex) {
                System.out.println("null argument: rejected");
            }

            ProcessBuilder reusable = childBuilder(0);
            runChild("first", reusable);
            runChild("second", reusable);
            runChild("nonzero", childBuilder(7));
        } finally {
            Files.delete(temporary);
        }
    }
}
```

Biên dịch và chạy trong thư mục chứa tệp:

```shell
javac --release 17 ProcessStartDemo.java
java ProcessStartDemo
```

Stdout:

```text
missing program: builder created
missing program: IOException
missing directory: IOException
empty command: rejected
null argument: rejected
first: start returned Process
first: exit = 0
second: start returned Process
second: exit = 0
nonzero: start returned Process
nonzero: exit = 7
```

Ví dụ tạo một thư mục tạm rỗng. Đường dẫn chương trình và thư mục làm việc dùng trong hai tình huống lỗi chắc chắn chưa được tạo trong thư mục đó. Cuối cùng, thư mục tạm rỗng được xóa.

Không in thông báo gốc của hệ điều hành vào stdout mẫu vì nội dung phụ thuộc Windows/Linux, ngôn ngữ và đường dẫn trên máy. Trong mã thật, vẫn giữ ngoại lệ gốc để chẩn đoán.

Các JVM con trong ví dụ không tạo nội dung cần giữ nên stdout/stderr được chuyển sang `DISCARD`. Đây là lựa chọn cho thí nghiệm nhỏ, không phải đề xuất bỏ thông tin chẩn đoán của mọi công cụ thực tế.

## 5. Cách đặt ranh giới xử lý ngoại lệ

Đặt `try/catch` quanh đúng thao tác mà thông báo lỗi mô tả:

```java
// Đoạn bên trong một phương thức đã có biến builder.
Process process;
try {
    process = builder.start();
} catch (IOException ex) {
    throw new IllegalStateException(
            "Cannot start document converter", ex);
}
```

Lớp bọc trên giữ nguyên `ex` làm nguyên nhân. Nhờ vậy, tầng gọi có ngữ cảnh nghiệp vụ còn thông tin lỗi native không bị bỏ mất.

Không làm:

```java
// Minh họa cách sai: che mất nguyên nhân và giả vờ đã xử lý.
try {
    builder.start();
} catch (IOException ex) {
    System.out.println("Something went wrong");
}
```

Nếu chương trình tiếp tục như tác vụ đã chạy, người gọi sẽ nhận trạng thái thành công giả.

Cũng không dùng một `catch (IOException)` bao quanh cả khởi chạy, ghi stdin, đọc stdout và lưu kết quả rồi gán nhãn tất cả là “không tạo được tiến trình”. Một lỗi đọc luồng sau khi `start()` đã trả về xảy ra ở giai đoạn khác; lúc đó tiến trình có thể vẫn tồn tại và cần được quản lý.

### Phân biệt lỗi có thể phục hồi và lỗi cấu hình

- Đường dẫn chương trình thiếu trong triển khai: thường cần sửa cấu hình hoặc cài phụ thuộc.
- Thư mục đầu ra được phép tạo nhưng chưa có: có thể chuẩn bị thư mục theo chính sách ứng dụng rồi thực hiện.
- Danh sách rỗng hoặc chứa null: nên sửa nơi xây dựng cấu hình, không thử lại y nguyên.
- Mã thoát công cụ khác 0: xử lý theo hợp đồng của công cụ và thông tin đầu ra.

Không tự động chạy lại vô hạn một lệnh chỉ vì có ngoại lệ.

## 6. Kiểm tra trước có ích nhưng start vẫn là nơi quyết định

Có thể kiểm tra đường dẫn và thư mục để báo lỗi sớm, nhưng các kiểm tra đó không chứng minh lần khởi chạy sau chắc chắn thành công.

Giữa lúc kiểm tra và lúc `start()`:

- Tệp có thể bị di chuyển hoặc thay quyền.
- Thư mục có thể bị xóa.
- Tài nguyên hệ thống có thể thay đổi.
- Môi trường tiến trình thực có thể khác với môi trường đang dùng để chẩn đoán.

Vì vậy, kể cả sau khi `Files.exists` hoặc một phép kiểm tra quyền trả kết quả thuận lợi, vẫn phải xử lý `IOException` từ `start()`.

Dùng đường dẫn thực thi rõ ràng giúp giảm phụ thuộc vào cách tìm chương trình qua môi trường. Tách chương trình và từng đối số thành các phần tử; không đưa cả một dòng lệnh shell vào phần tử đầu rồi kết luận lỗi là do thiếu công cụ.

Nếu ứng dụng cấu hình chuyển hướng vào tệp, việc chuẩn bị/khởi chạy có thể đã tạo hoặc tác động tệp chuyển hướng trước khi một bước khác báo lỗi. Đừng coi `start()` như một giao dịch có cơ chế tự hoàn tác mọi tác động đến hệ thống tệp.

## 7. Sau khi start thành công, trách nhiệm mới bắt đầu

Một `Process` cho phép quản lý tiến trình con; nó không tự hoàn tất toàn bộ vòng đời thay ứng dụng.

Các việc cần quyết định bao gồm:

1. Tiến trình có cần dữ liệu trên stdin không; nếu không, khi nào đóng đầu ghi.
2. Stdout/stderr được đọc, chuyển hướng hay bỏ có chủ đích.
3. Chờ bao lâu và xử lý khi chưa kết thúc.
4. Diễn giải mã thoát và đầu ra theo hợp đồng công cụ.
5. Xử lý gián đoạn của luồng Java đang chờ.

Không đợi tiến trình tùy ý kết thúc trong khi bỏ đọc các luồng mà nó có thể ghi đầy. Chuyển hướng hoặc đọc luồng đồng thời phải phù hợp với chương trình được gọi. Các API quản lý vòng đời và luồng nằm trong [Process](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Process.html).

`waitFor()` có thể ném `InterruptedException`. Đây là việc luồng Java đang chờ bị gián đoạn, không phải `IOException` của `start()`, cũng không chứng minh tiến trình con đã dừng.

Nếu tầng hiện tại không thể xử lý gián đoạn, thường truyền nó lên theo hợp đồng phương thức. Nếu bắt rồi không truyền tiếp, cần khôi phục cờ gián đoạn bằng `Thread.currentThread().interrupt()` và thực hiện chính sách dọn dẹp tiến trình phù hợp. Không nuốt ngoại lệ rồi coi công việc đã hoàn tất.

Ví dụ đầy đủ phía trên để ngoại lệ gián đoạn truyền lên; đó là một chương trình minh họa ngắn, không phải bộ quản lý tiến trình tổng quát cho tác vụ dài.

## 8. Có thể gọi start nhiều lần không?

Có. Mỗi lần thành công tạo một tiến trình mới; `ProcessBuilder` không bị “tiêu thụ” sau lần đầu.

Trong ví dụ, `reusable` được dùng hai lần, nên có hai JVM con khác nhau dù cấu hình giống nhau.

Sau khi tiến trình đã được tạo, thay đổi builder chỉ ảnh hưởng các lần khởi chạy sau; nó không sửa chương trình, đối số hoặc môi trường của tiến trình đang tồn tại.

Điều này cũng có nghĩa là một thao tác thử lại có thể tạo **một lần thực thi mới** với tác động nghiệp vụ mới. Cần phân biệt:

- `start()` chưa trả về được `Process`: có lỗi ở ranh giới khởi chạy.
- Đã nhận `Process`, rồi mất kết nối hoặc lỗi đọc kết quả: chưa chắc công việc bên ngoài chưa được thực hiện.

Không thử lại tác vụ có tác động bên ngoài chỉ vì Java không đọc được kết quả. Phải biết tác vụ có thể lặp an toàn hoặc có cơ chế chống thực hiện lặp hay không.

`ProcessBuilder` cũng không đồng bộ hóa truy cập cấu hình cho nhiều luồng. Không dùng chung một builder đang bị sửa đổi đồng thời rồi mong mọi lần `start()` nhận cấu hình nhất quán.

## 9. Thông tin chẩn đoán nên giữ

Khi một lần khởi chạy thất bại, các thông tin hữu ích là:

- Giai đoạn: đang cấu hình, gọi `start`, đọc/ghi luồng hay chờ.
- Đường dẫn hoặc tên công cụ dự định chạy.
- Thư mục làm việc.
- Loại ngoại lệ và nguyên nhân gốc.
- Mã thoát nếu đã có tiến trình và tiến trình đã kết thúc.

Thông báo hệ điều hành hỗ trợ chẩn đoán nhưng không nên được phân tích bằng cách so khớp một câu tiếng Anh cố định: câu chữ, mã lỗi và định dạng có thể khác giữa nền tảng.

Khi ghi đối số vào nhật ký, chỉ giữ phần cần cho chẩn đoán; đối số hoặc môi trường có thể chứa dữ liệu nhạy cảm. Có thể ghi tên thao tác và vị trí đối số thay cho toàn bộ giá trị.

## 10. Lỗi thường gặp và thực hành

| Lỗi | Vì sao sai | Cách xử lý |
| --- | --- | --- |
| Constructor thành công nghĩa là chạy được | Nhiều kiểm tra diễn ra tại start | Xử lý lỗi ở ranh giới start |
| start trả về nghĩa là công việc xong | Chỉ có tiến trình được khởi chạy | Theo dõi kết thúc và kết quả |
| Mã thoát khác 0 phải gây IOException | Là kết quả của chương trình đã chạy | Kiểm tra mã thoát riêng |
| Bắt mọi Exception rồi trả thành công | Che lỗi cấu hình và vận hành | Phân loại theo giai đoạn |
| Lấy exitValue ngay lập tức | Tiến trình có thể chưa kết thúc | Chờ hoặc kiểm tra trạng thái đúng |
| Chỉ kiểm tra tệp tồn tại rồi bỏ catch | Trạng thái có thể thay đổi | Vẫn xử lý IOException |
| Thử lại tác vụ không biết trạng thái | Có thể lặp tác động bên ngoài | Xác định tính lặp an toàn |
| Sửa builder để điều khiển tiến trình cũ | Builder chỉ chi phối lần start sau | Dùng Process cho tiến trình đã tạo |

Thực hành:

1. Chỉ ra dòng nào trong ví dụ chứng minh tạo builder chưa kiểm tra tệp thực thi.
2. Đổi mã thoát con từ 7 thành 3. Dự đoán vì sao `start()` vẫn trả `Process`.
3. Phân loại lỗi danh sách rỗng, thư mục thiếu và lỗi đọc stdout sau khi khởi chạy.
4. Thiết kế thông báo lỗi có tên thao tác nhưng vẫn giữ ngoại lệ gốc.
5. Giải thích vì sao kiểm tra tồn tại của chương trình không thay thế xử lý ngoại lệ tại `start()`.

Mục tiêu là xác định đúng **ranh giới khởi chạy**, rồi xử lý riêng kết quả của chương trình đã được tạo.
