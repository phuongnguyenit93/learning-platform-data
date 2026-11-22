# `System.err` cho thông báo chẩn đoán trong Java

## 1. `System.err` là gì?

Java cung cấp sẵn hai luồng xuất thường dùng trên console:

- **`System.out`**: luồng xuất chuẩn (*standard output*, **stdout**). Thường dùng để in **kết quả chính** mà người dùng hoặc chương trình khác cần nhận.
- **`System.err`**: luồng lỗi chuẩn (*standard error*, **stderr**). Thường dùng để in **thông báo lỗi, cảnh báo và thông tin chẩn đoán** về những vấn đề đã xảy ra khi xử lý.

Cả hai đều là đối tượng **`java.io.PrintStream`**, nên có các phương thức quen thuộc như `print(...)`, `println(...)` và `printf(...)`. Ví dụ:

```java
System.out.println("Ket qua: 42");
System.err.println("Canh bao: cau hinh thieu");
```

Nếu chạy trên terminal bình thường, bạn có thể nhìn thấy cả hai dòng trên **cùng một màn hình**. Điều đó không biến chúng thành một luồng: về mặt kỹ thuật, stdout và stderr vẫn được phân biệt. Trình gọi, terminal hoặc công cụ shell có thể chuyển hướng chúng tới hai nơi riêng biệt.

**Quy tắc thực hành:** gửi **dữ liệu kết quả** tới stdout; gửi **thông tin về vấn đề hoặc chẩn đoán** tới stderr. Nhờ đó một chương trình khác đọc stdout không phải lọc những câu cảnh báo chen giữa dữ liệu hợp lệ.

## 2. `System.err` có các phương thức in tương tự `System.out`

```java
System.err.print("WARN: ");
System.err.println("Gia tri khong hop le");
System.err.printf("ERROR: ma=%d%n", 400);
```

- `print()` **không tự thêm** dấu xuống dòng.
- `println()` in nội dung rồi thêm dấu kết thúc dòng.
- `printf()` in theo **mẫu định dạng**; muốn xuống dòng dùng `%n` hoặc ký tự newline thích hợp trong format.
- `%s`, `%d`, `%.2f` và các ký hiệu định dạng khác hoạt động theo API `PrintStream` như khi dùng `System.out.printf`.

Nếu định dạng số phụ thuộc vùng miền, có thể chỉ định `Locale`:

```java
System.err.printf(java.util.Locale.US,
        "WARN: he so=%.2f%n", 12.5);
```

Kết quả được gửi vào **stderr** là `WARN: he so=12.50` rồi xuống dòng. Chỉ định `Locale.US` giúp ví dụ dùng dấu chấm thập phân nhất quán, không phụ thuộc locale mặc định của máy.

### `System.err` có tự ném ngoại lệ hay dừng chương trình không?

**Không.** Chỉ in bằng `System.err.println(...)` không phải hành động `throw`, cũng không tự đổi exit code của tiến trình thành mã thất bại.

```java
System.err.println("Loi du lieu");
System.out.println("Chuong trinh van chay");
```

Nếu không có lệnh hoặc lỗi khác khiến chương trình kết thúc, cả hai dòng vẫn có thể được in. Muốn thông báo lỗi trở thành một tình huống được xử lý theo luồng điều khiển, hãy dùng cơ chế ngoại lệ hoặc kiểm tra điều kiện thích hợp. Nếu là lỗi nghiêm trọng không thể tiếp tục, điểm vào chương trình cần quyết định cách kết thúc và **exit status** phù hợp; không nên cho rằng việc viết stderr tự động báo thất bại cho script gọi chương trình.

## 3. So sánh `System.out` và `System.err`

| Đặc điểm | `System.out` | `System.err` |
| --- | --- | --- |
| Tên luồng | Standard output | Standard error |
| Mục tiêu thường gặp | Kết quả, báo cáo, dữ liệu chính | Lỗi, cảnh báo, chẩn đoán |
| Kiểu Java | `PrintStream` | `PrintStream` |
| Phương thức in | `print`, `println`, `printf` | `print`, `println`, `printf` |
| Chuyển hướng thông dụng trong shell | `>` hoặc `1>` | `2>` |
| Chỉ in vào luồng có khiến chương trình thất bại? | Không | Không |

**Lưu ý:** số hiệu **1** cho stdout và **2** cho stderr là cách shell/hệ điều hành thường biểu diễn các luồng chuẩn. Đây **không phải chỉ số mảng Java** và cũng không phải tên file do `System` tự tạo.

Ví dụ một tiện ích có nhiệm vụ trả về danh sách số hợp lệ sẽ hữu ích hơn nếu in danh sách đó trên stdout và in lỗi đầu vào trên stderr. Một chương trình khác có thể dùng dữ liệu stdout mà không bị lẫn thông báo như `WARN` hoặc `ERROR`.

## 4. Ví dụ Java 17+ hoàn chỉnh: dữ liệu hợp lệ và cảnh báo

Tạo tệp **`StdErrDemo.java`**:

```java
import java.util.Locale;

public class StdErrDemo {
    static int parsePositive(String input) {
        final int value;
        try {
            value = Integer.parseInt(input);
        } catch (NumberFormatException ex) {
            throw new IllegalArgumentException("not an integer", ex);
        }

        if (value <= 0) {
            throw new IllegalArgumentException("must be positive");
        }
        return value;
    }

    public static void main(String[] args) {
        System.out.println("START");

        String[] inputs = {"12", "abc", "-3"};
        for (String input : inputs) {
            try {
                int value = parsePositive(input);
                System.out.printf(Locale.ROOT,
                        "accepted=%d%n", value);
            } catch (IllegalArgumentException ex) {
                System.err.printf(Locale.ROOT,
                        "WARN input=%s reason=%s%n",
                        input, ex.getMessage());
            }
        }

        System.out.println("END");
    }
}
```

Dùng **JDK 17 trở lên**, mở terminal ở thư mục chứa `StdErrDemo.java`:

```bash
javac -encoding UTF-8 StdErrDemo.java
java StdErrDemo
```

Lệnh `javac` thành công sẽ không in thông báo. Trong lần chạy bình thường, cả stdout và stderr có thể cùng hiển thị trên console; **không nên dựa vào thứ tự trộn giữa hai luồng** để kiểm thử. Để xác minh chính xác, hãy xem kết quả của từng luồng riêng biệt:

**Nội dung stdout:**

```text
START
accepted=12
END
```

**Nội dung stderr:**

```text
WARN input=abc reason=not an integer
WARN input=-3 reason=must be positive
```

Giải thích:

1. Chương trình in `START` vào stdout.
2. `"12"` chuyển được thành `12` và dương, nên in `accepted=12` vào stdout.
3. `"abc"` không chuyển được thành số nguyên, nên phương thức `parsePositive` ném `IllegalArgumentException` với thông điệp `not an integer`; `catch` in cảnh báo vào stderr.
4. `"-3"` là số nguyên nhưng không dương, nên in cảnh báo `must be positive` vào stderr.
5. Các lỗi đã được `catch` xử lý; vòng lặp tiếp tục và `END` được in vào stdout.

Vì lỗi ở đây được xem là các **đầu vào bị bỏ qua**, chương trình không chủ động đặt exit code khác 0. Nếu đặc tả yêu cầu **bất kỳ đầu vào sai nào cũng phải làm toàn bộ công việc thất bại**, cần thiết kế cách báo trạng thái thất bại cho bên gọi, không chỉ in `WARN`.

## 5. Tách stdout và stderr bằng chuyển hướng của shell

Các shell phổ biến cho phép lưu hai luồng ra hai tệp. Sau khi biên dịch chương trình ở mục 4, chạy:

```bash
java StdErrDemo 1> normal.txt 2> diagnostics.txt
```

Cách chuyển hướng này thông dụng trong Windows CMD/PowerShell và shell như bash/zsh. Hai tệp sẽ nhận riêng nội dung tương ứng (chi tiết mã hóa văn bản và cách thể hiện newline trên đĩa có thể phụ thuộc shell/hệ điều hành).

**Tệp `normal.txt`** có nội dung các dòng stdout:

```text
START
accepted=12
END
```

**Tệp `diagnostics.txt`** có nội dung các dòng stderr:

```text
WARN input=abc reason=not an integer
WARN input=-3 reason=must be positive
```

Dấu `>` thường là dạng ngắn của `1>`, nghĩa là chuyển hướng stdout. Dấu `2>` chuyển hướng stderr. Không cần sửa bất kỳ dòng Java nào khi chuyển hướng các luồng bằng shell.

### Chỉ chuyển hướng stdout

```bash
java StdErrDemo > normal.txt
```

Đầu ra chuẩn đi vào `normal.txt`; stderr vẫn có thể hiển thị trực tiếp trên terminal. Đây là lý do quan trọng để viết cảnh báo vào **đúng luồng** thay vì in tất cả bằng `System.out`.

### Chuyển hướng cả hai luồng vào cùng một tệp

Trên những shell hỗ trợ cú pháp chuyển hướng file descriptor tương ứng, có thể dùng:

```bash
java StdErrDemo > combined.txt 2>&1
```

Cú pháp `2>&1` làm stderr đi theo đích của stdout trong cách viết này. **Không coi thứ tự dòng trong file gộp là cam kết về thứ tự thời gian của các thao tác trên hai luồng độc lập**: buffering và môi trường chạy có thể ảnh hưởng trình tự quan sát. Khi cần một chuỗi sự kiện có thứ tự nhất quán, nên thiết kế một cơ chế logging hoặc một đích ghi phù hợp thay vì ghép stdout/stderr tùy tiện.

Trên PowerShell, hành vi biểu diễn/chuyển hướng native stderr có thể có khác biệt theo phiên bản. Lệnh tách riêng `1>` và `2>` là cách thực hành thông dụng để quan sát hai luồng, nhưng việc đối chiếu byte/encoding chính xác của tệp cần xem phiên bản shell đang dùng.

## 6. Khi nào nên ghi thông tin gì vào stderr?

Các thông báo chẩn đoán có ích khi chúng giúp người dùng hoặc người vận hành **hiểu nguyên nhân và lựa chọn bước tiếp theo**.

Những trường hợp thường phù hợp:

- Dữ liệu đầu vào không hợp lệ: thiếu tham số, định dạng số sai, giá trị ngoài khoảng cho phép.
- Tệp cấu hình không tồn tại hoặc không đọc được.
- Một thao tác bị từ chối, thất bại hoặc được bỏ qua có chủ đích.
- Cảnh báo về hành vi dự phòng (*fallback*) mà người dùng nên biết.
- Thông điệp debug ngắn khi đang thử nghiệm chương trình console.

Ví dụ:

```java
String filename = "";
if (filename.isBlank()) {
    System.err.println("ERROR: file path is required");
}
```

Đoạn này chỉ **báo lỗi**; muốn thật sự ngừng thao tác hoặc yêu cầu nhập lại, cần thêm logic điều khiển thích hợp.

Thông báo nên rõ **điều gì xảy ra**, **đầu vào nào liên quan** (nếu an toàn) và **người dùng có thể làm gì**. Tránh in thông tin bí mật như mật khẩu, access token hoặc toàn bộ dữ liệu cá nhân vào stderr; log lỗi vẫn có thể bị lưu, thu thập hoặc chia sẻ.

## 7. Ngoại lệ, `printStackTrace` và `System.err`

Một ngoại lệ (*exception*) có thể được xử lý bằng `try-catch`. Khi muốn chẩn đoán tại sao xảy ra lỗi, có thể in thông điệp ngắn hoặc stack trace.

```java
try {
    int number = Integer.parseInt("invalid");
    System.out.println(number);
} catch (NumberFormatException ex) {
    System.err.println("ERROR: input is not a valid integer");
}
```

Đoạn mã này minh họa đặt trong một phương thức. Khi cần thông tin chi tiết hơn:

```java
try {
    Integer.parseInt("invalid");
} catch (NumberFormatException ex) {
    ex.printStackTrace(System.err);
}
```

`printStackTrace(System.err)` in tên ngoại lệ, thông điệp và các dòng vị trí gọi hàm ra stderr. **`ex.printStackTrace()` không đối số cũng ghi vào luồng lỗi chuẩn** theo API thông thường. Stack trace phụ thuộc JDK, tên phương thức và số dòng mã thực tế, nên **không nên mô tả nó bằng một stdout cố định**.

Việc in stack trace là thao tác **xuất thông tin**; nó không làm ngoại lệ tự được xử lý đúng nghiệp vụ. Nếu ứng dụng không thể khôi phục, cần báo lỗi cho tầng gọi hoặc cho chương trình kết thúc theo chính sách lỗi. Không nên lạm dụng `printStackTrace()` trong sản phẩm lớn: dùng công cụ logging thích hợp để có mức độ, nguồn gốc sự kiện và cách thu thập thống nhất.

### In ra stderr không tương đương với ném ngoại lệ

```java
System.err.println("ERROR: invalid input");
```

Dòng này chỉ in nội dung chẩn đoán. Ngược lại:

```java
throw new IllegalArgumentException("invalid input");
```

Dòng thứ hai **thay đổi luồng điều khiển** bằng cách ném ngoại lệ. Nếu ngoại lệ không được xử lý, Java runtime thường báo stack trace và chương trình có thể kết thúc không thành công. Hai thao tác phục vụ hai mục đích khác nhau; chúng có thể đi cùng nhau khi thiết kế xử lý lỗi, nhưng không thay thế nhau.

## 8. Exit code và thông báo lỗi là hai tín hiệu riêng

Khi một tiện ích dòng lệnh hoàn thành, script gọi nó thường xem **exit code** để quyết định công việc thành công hay thất bại.

- Mã **0** thường biểu thị thành công.
- Mã **khác 0** thường biểu thị thất bại theo quy ước của ứng dụng.
- `System.err.println(...)` **không tự làm exit code khác 0**.
- `System.exit(1)` có thể chủ động kết thúc JVM với mã 1, nhưng không nên dùng bừa bãi trong mã thư viện hoặc giữa quy trình cần dọn dẹp tài nguyên.

Ví dụ chương trình tối giản dành cho tiện ích CLI, đặt trong phương thức `main`:

```java
if (args.length == 0) {
    System.err.println("Usage: java Tool <name>");
    System.exit(2);
}
```

Đây là đoạn minh họa, **không phải chương trình độc lập**. Nó báo cách dùng trên stderr và chỉ rõ mã thoát khi thiếu đối số. Trong một ứng dụng thực tế, cũng có thể tổ chức hàm `run` trả về mã lỗi cho tầng `main` để tách logic nghiệp vụ khỏi việc kết thúc JVM.

Lưu ý: khi một ngoại lệ không được bắt làm JVM báo lỗi, stack trace mặc định thường xuất hiện trên stderr. Nhưng không nên chỉ dựa vào việc có/không có chữ trên stderr để suy ra exit code: một cảnh báo hợp lệ có thể được in khi chương trình vẫn thành công.

## 9. `System.err` và công cụ logging

`System.err` phù hợp cho **bài học nhập xuất, chương trình console nhỏ hoặc lỗi khởi động đơn giản**. Với ứng dụng lớn cần theo dõi lâu dài, một giải pháp logging có cấu trúc thường thích hợp hơn:

- Phân mức: DEBUG, INFO, WARN, ERROR.
- Ghi thời điểm và thành phần phát sinh sự kiện.
- Kiểm soát đầu ra, luân chuyển tệp và bộ lọc.
- Tránh trùng thông báo hoặc in đi in lại stack trace ở nhiều tầng.
- Giảm nguy cơ rò rỉ dữ liệu bí mật trong chẩn đoán.

Java có API chuẩn `java.util.logging`; nhiều dự án còn sử dụng các facade/framework logging phù hợp. **Logging không thay thế việc xử lý ngoại lệ** và cũng không làm dữ liệu sai thành hợp lệ. `System.err` là luồng thấp hơn; không tự cung cấp mức log, timestamp hoặc lưu trữ có cấu trúc.

## 10. Các lỗi thường gặp

| Nhầm lẫn | Cách hiểu đúng |
| --- | --- |
| “Gọi `System.err.println` là chương trình thất bại.” | Chỉ ghi vào stderr; kết quả thực thi/exit code là chuyện khác. |
| “`System.err` không có `printf`.” | Có, vì cũng là `PrintStream`. |
| “Khi nhìn thấy hai loại dòng trên console, chúng là cùng một luồng.” | Console có thể hiển thị cả stdout và stderr nhưng hai luồng vẫn riêng. |
| “Cứ dùng `System.out` cho mọi thứ cũng được.” | Dữ liệu kết quả sẽ bị trộn cảnh báo; bất tiện khi script chuyển hướng stdout. |
| “Dòng in ở stdout luôn xuất hiện trước dòng in ở stderr nếu gọi trước.” | Không nên phụ thuộc thứ tự quan sát của hai luồng độc lập khi gộp/hiển thị. |
| “`printStackTrace()` in một chuỗi cố định cho mọi Java.” | Thông tin phụ thuộc ngữ cảnh chạy, phiên bản JDK và vị trí mã. |
| “Thông báo stderr có thể tùy tiện chứa thông tin nhạy cảm.” | Nên hạn chế dữ liệu chẩn đoán; stderr có thể được thu thập và lưu lại. |
| “Dùng stderr thay `throw` hoặc `catch`.” | Xuất thông tin và điều khiển lỗi là hai nhiệm vụ khác nhau. |

**Ghi nhớ:** **`System.out` dành cho kết quả chính, `System.err` dành cho thông báo chẩn đoán.** Cả hai đều có `print`, `println` và `printf`, nhưng có thể chuyển hướng riêng. In ra stderr giúp làm rõ lỗi và giữ stdout sạch, còn việc phục hồi, ném ngoại lệ hay đặt exit code vẫn cần được thiết kế riêng theo yêu cầu chương trình.