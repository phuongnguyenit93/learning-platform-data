# Auto-flush và các thao tác thực sự kích hoạt flush trong Java I/O

Khi ghi ra console, file hay socket, chương trình thường không chuyển ngay mọi ký tự hoặc byte tới nơi nhận. Một số lớp Java I/O dùng **bộ đệm** (*buffer*) để gom dữ liệu; thao tác **`flush()`** yêu cầu đẩy dữ liệu đang đệm xuống các tầng ghi bên dưới. **Auto-flush** là chế độ khiến một số thao tác nhất định tự kích hoạt flush.

Điểm quan trọng: **không có một quy tắc auto-flush áp dụng cho mọi lớp Java I/O**. `PrintWriter` và `PrintStream` có điều kiện kích hoạt khác nhau; `BufferedWriter.newLine()` tự nó không flush. Vì vậy “có ký tự xuống dòng” và “đã flush” không luôn tương đương.

## 1. `write`, `flush`, `close` khác nhau như thế nào?

- **`write`/`print`:** cung cấp dữ liệu cho luồng. Nếu có bộ đệm, dữ liệu có thể chưa chuyển tới tầng nhận kế tiếp.
- **`flush()`:** yêu cầu chuyển dữ liệu đã đệm xuống các tầng bên dưới; wrapper thường gọi tiếp `flush` của luồng được bọc. Điều này **không bảo đảm** byte đã bền vững trên ổ đĩa hoặc ứng dụng ở đầu bên kia mạng đã xử lý.
- **`close()`:** đóng luồng, thường hoàn tất dữ liệu còn đệm và giải phóng tài nguyên. Với luồng dùng chung như `System.out`, không đóng tùy tiện.

**Auto-flush** không có nghĩa “mọi lần `write` đều flush”, “mọi `\n` đều flush”, hoặc “không cần nghĩ đến buffering”. Phải xác định **kiểu đối tượng**, **constructor** và **phương thức thực sự được gọi**.

```text
Ứng dụng
    |
    | print/write/println/printf/format
    v
PrintWriter hoặc PrintStream
    |
    | có thể gọi flush nếu thỏa điều kiện autoFlush
    v
BufferedWriter / OutputStreamWriter / BufferedOutputStream
    |
    | flush xuống tầng thấp hơn
    v
OS buffer -> file / socket / terminal / thiết bị
```

Thời điểm dữ liệu hiển thị trong console hoặc tới ứng dụng khác còn phụ thuộc nhiều tầng. `flush()` là yêu cầu của API ghi, không phải ACK từ hệ thống nhận.

## 2. `PrintWriter`: các phương thức thực sự kích hoạt auto-flush

`PrintWriter` ghi **văn bản** qua một `Writer` hoặc `OutputStream`. Để bật auto-flush:

```java
PrintWriter out = new PrintWriter(destination, true);
```

Đây là đoạn mã minh họa: `destination` là `Writer` hoặc `OutputStream` đã có, với `import java.io.PrintWriter`. Cờ `true` bật auto-flush, `false` tắt. Các constructor thông thường không cung cấp `autoFlush` mặc định **tắt** chế độ này.

Theo hợp đồng `PrintWriter`, khi cờ auto-flush là `true`, các nhóm phương thức **kích hoạt flush**:

1. `println(...)`, kể cả `println()` không đối số;
2. `printf(...)`, ngay cả khi chuỗi format **không có** dấu xuống dòng;
3. `format(...)`, ngay cả khi chuỗi format **không có** dấu xuống dòng.

Ngược lại, chỉ gọi `print(...)`, `write(...)` hoặc `append(...)` **không kích hoạt auto-flush theo quy tắc của `PrintWriter`**, kể cả khi dữ liệu chứa `'\n'`.

| Thao tác với `PrintWriter` autoFlush=true | Có kích hoạt auto-flush theo hợp đồng? |
| --- | --- |
| `out.print("Hello")` | Không |
| `out.print("Hello\n")` | Không |
| `out.write("Hello\n")` | Không |
| `out.write('\n')` | Không |
| `out.append('\n')` | Không |
| `out.println("Hello")` | **Có** |
| `out.println()` | **Có** |
| `out.printf("n=%d", 7)` | **Có**, dù không có `%n` |
| `out.format("n=%d", 7)` | **Có**, dù không có `%n` |
| `out.flush()` | Chủ động flush, bất kể autoFlush |
| `out.close()` | Hoàn tất và đóng luồng |

**Bẫy quan trọng:** `out.println("x")` có thể vừa ghi ký tự kết thúc dòng của nền tảng vừa tự flush; `out.print("x\n")` chỉ ghi chuỗi có LF, **không tự flush** theo hợp đồng `PrintWriter`. Hai cách có thể nhìn giống nhau trên Linux nhưng khác lúc dữ liệu được đẩy xuống tầng dưới.

Khi `autoFlush=false`, `println`/`printf`/`format` **không tự kích hoạt flush bởi cờ đó**. Dữ liệu vẫn có thể được chuyển đi nếu buffer đầy, tầng dưới có cơ chế riêng, hoặc ta gọi `flush()` hay đóng luồng. Tắt auto-flush không có nghĩa dữ liệu hoàn toàn đứng yên cho đến lúc đóng.

## 3. Ví dụ Java 17+ chạy được: đo `flush()` của luồng đích

Thay vì dự đoán từ việc chữ xuất hiện trên terminal, ta tạo một `Writer` giả lập để đếm số lần `flush()` được gọi. Chương trình dùng `PrintWriter` với `autoFlush=true` và `BufferedWriter` không có auto-flush.

Lưu file tên **`AutoFlushDemo.java`**:

```java
import java.io.BufferedWriter;
import java.io.IOException;
import java.io.PrintWriter;
import java.io.Writer;

public class AutoFlushDemo {

    public static void main(String[] args) throws IOException {
        SpyWriter printTarget = new SpyWriter();

        try (PrintWriter out = new PrintWriter(printTarget, true)) {
            out.print("A");
            System.out.println("PrintWriter after print: "
                    + printTarget.flushCount);

            out.write("\n");
            System.out.println("PrintWriter after write LF: "
                    + printTarget.flushCount);

            out.println("B");
            System.out.println("PrintWriter after println: "
                    + printTarget.flushCount);

            out.printf("n=%d", 7);
            System.out.println("PrintWriter after printf: "
                    + printTarget.flushCount);

            out.format(" m=%d", 8);
            System.out.println("PrintWriter after format: "
                    + printTarget.flushCount);

            out.flush();
            System.out.println("PrintWriter after explicit flush: "
                    + printTarget.flushCount);
        }

        SpyWriter bufferedTarget = new SpyWriter();
        try (BufferedWriter out = new BufferedWriter(bufferedTarget)) {
            out.write("C");
            out.newLine();
            System.out.println("BufferedWriter after newLine: "
                    + bufferedTarget.flushCount);

            out.flush();
            System.out.println("BufferedWriter after explicit flush: "
                    + bufferedTarget.flushCount);
        }
    }

    static final class SpyWriter extends Writer {
        private final StringBuilder characters = new StringBuilder();
        int flushCount;

        @Override
        public void write(char[] chars, int offset, int length) {
            characters.append(chars, offset, length);
        }

        @Override
        public void flush() {
            flushCount++;
        }

        @Override
        public void close() {
            // Nguồn đích giả lập chỉ dùng để quan sát flush.
        }
    }
}
```

Biên dịch và chạy với JDK 17+:

```bash
javac -encoding UTF-8 AutoFlushDemo.java
java AutoFlushDemo
```

**Stdout đã kiểm chứng:**

```text
PrintWriter after print: 0
PrintWriter after write LF: 0
PrintWriter after println: 1
PrintWriter after printf: 2
PrintWriter after format: 3
PrintWriter after explicit flush: 4
BufferedWriter after newLine: 0
BufferedWriter after explicit flush: 1
```

Giải thích:

- `print("A")` và `write("\n")` không auto-flush, nên bộ đếm vẫn 0.
- `println("B")` tự flush, đưa bộ đếm lên 1.
- `printf("n=%d", 7)` và `format(" m=%d", 8)` mỗi lệnh flush thêm một lần dù không có newline.
- `flush()` trực tiếp tăng bộ đếm lên 4.
- `BufferedWriter.newLine()` chỉ viết dấu kết thúc dòng; `flush()` tường minh mới khiến `SpyWriter` nhận được lệnh flush.

`SpyWriter` chỉ đo lời gọi `flush()` vào **writer đích**, không đo độ bền vật lý của file hay độ trễ nhận dữ liệu qua mạng. Ví dụ in kết quả **trước khi wrapper đóng** để không gộp hoạt động close vào phép đo.

## 4. `PrintStream`: quy tắc khác `PrintWriter`

`PrintStream` là lớp xuất byte có các phương thức in văn bản; `System.out` và `System.err` có kiểu `PrintStream`. Ta có thể tạo với auto-flush tường minh:

```java
import java.io.OutputStream;
import java.io.PrintStream;
import java.nio.charset.StandardCharsets;

// Giả sử đã có OutputStream destination:
PrintStream out = new PrintStream(
        destination, true, StandardCharsets.UTF_8
);
```

Theo tài liệu API, khi cờ auto-flush của `PrintStream` bật, các sự kiện có thể kích hoạt flush xuống luồng byte bên dưới là:

- **Ghi mảng byte**, như `write(byte[])`, `write(byte[], off, len)` hoặc `writeBytes(byte[])`;
- **Gọi `println(...)`**;
- **Ghi ký tự hoặc byte newline `'\n'`**.

Như vậy, `PrintStream.write('\n')` **kích hoạt auto-flush**, trong khi `PrintWriter.write("\n")` **không kích hoạt auto-flush theo hợp đồng riêng của `PrintWriter`**.

| Thao tác với `PrintStream` autoFlush=true | Kết luận |
| --- | --- |
| `out.write('X')` | Không có trigger newline byte |
| `out.write('\n')` | **Có** trigger newline byte |
| `out.write(new byte[] {65, 66})` | **Có** trigger ghi byte array |
| `out.writeBytes(new byte[] {65, 66})` | **Có** trigger ghi byte array |
| `out.println("X")` | **Có** trigger `println` |
| `out.print("X\n")` | Có newline character trong dữ liệu |
| `out.print("X")` | Không dùng riêng lời gọi này như cam kết flush khi tương tác |
| `out.printf("n=%d", 7)` | Không lấy tên `printf` làm trigger riêng; xét byte/newline thực sự ghi |
| `out.flush()` | Chủ động flush bất kể cấu hình |

`PrintStream` có thể mã hóa ký tự thành byte qua các bước nội bộ. Vì thế, không nên khẳng định *số lần flush chính xác* của mọi `print(...)` hoặc `printf(...)` chỉ từ bảng API; hãy quan tâm những sự kiện được đặc tả và gọi `flush()` nếu thời điểm là yêu cầu thiết kế.

Ví dụ:

```java
byte[] payload = {65, 66};
out.write(payload);   // PrintStream autoFlush=true: ghi mảng byte.
out.write('\n');      // PrintStream autoFlush=true: newline byte.
```

`out` ở đây là `PrintStream` đã mở. `write` ghi **byte thô**; không tự chuyển payload thành văn bản có charset. Nếu `out` là `BufferedOutputStream` hoặc một `OutputStream` khác, không thể áp dụng quy tắc auto-flush của `PrintStream` cho nó.

## 5. `BufferedWriter.newLine()` và `BufferedOutputStream`

`BufferedWriter` tối ưu ghi ký tự; `BufferedOutputStream` tối ưu ghi byte. Cả hai có `flush()` và `close()` nhưng **không có cờ autoFlush=true như `PrintWriter`/`PrintStream`**.

```java
writer.write("Dòng 1");
writer.newLine();
writer.write("Dòng 2");
writer.flush();
```

Đoạn minh họa giả định `writer` là `BufferedWriter` đã mở. `newLine()` chỉ ghi line separator theo nền tảng: trên nhiều hệ Unix dùng LF, còn Windows thường dùng CRLF. Nó **không tự flush**.

Với byte stream:

```java
output.write(bytes);
output.flush();
```

`output` là `BufferedOutputStream` đã mở và `bytes` là byte array. Buffer có thể chuyển dữ liệu khi đầy hoặc theo cơ chế nội bộ, nhưng việc ghi ký tự `'\n'` vào buffered stream **không mang theo quy tắc auto-flush của `PrintStream`**.

Điểm dễ nhầm: `BufferedWriter.newLine()` và `PrintWriter.println()` có thể tạo cùng dấu kết thúc dòng. Nhưng `println()` của `PrintWriter` có auto-flush nếu cờ bật; `newLine()` của `BufferedWriter` thì không.

## 6. Console: hiển thị prompt trước khi đọc input

Ví dụ một chương trình cần in lời nhắc không kết thúc dòng, rồi chờ người dùng:

```java
import java.util.Scanner;

System.out.print("Nhập tên: ");
System.out.flush();  // Đẩy prompt trước khi chờ người dùng.

Scanner scanner = new Scanner(System.in);
String name = scanner.nextLine();
System.out.println("Xin chào, " + name);
```

Đây là đoạn minh họa cần đặt trong `main` và có import `Scanner`. Lệnh `flush()` giúp mã **chủ động** xác định thời điểm đẩy prompt. Không chỉ dựa vào giả định “console tự hiển thị ngay”, vì ứng dụng có thể chạy trong IDE, pipe, terminal, test harness hoặc chuyển hướng `stdout`.

`System.out` là `PrintStream`, nhưng không nên dựa vào cấu hình auto-flush chưa được xác minh để quyết định lúc hiển thị prompt; chương trình hoặc framework còn có thể thay `System.out` qua `System.setOut(...)`. Khi cần flush rõ ràng, gọi `System.out.flush()`.

Không đóng `System.in`/`System.out` ở giữa ứng dụng chỉ để đẩy prompt: chúng là tài nguyên dùng chung. Tùy quyền sở hữu, cũng cần cân nhắc trước khi đóng `Scanner` bọc `System.in`.

## 7. `printf`, `format` và `%n`

Với `PrintWriter` autoFlush=true, **`printf`/`format` tự flush ngay cả khi format không có newline**:

```java
writer.printf("Tiến độ: %d%%", 75);
writer.format(" | Tổng: %d", 100);
```

`writer` ở đây là `PrintWriter` bật auto-flush. Trong format, `%%` là dấu phần trăm literal.

Ba cơ chế cần phân biệt:

- **`"\n"`:** ký tự LF cố định, không nhất thiết là line separator theo nền tảng.
- **`"%n"`:** format specifier tạo dấu xuống dòng theo nền tảng.
- **`println(...)`:** phương thức in một dòng và kết thúc dòng; với `PrintWriter` bật auto-flush, còn trigger flush.

Ví dụ:

```java
writer.print("OK\n");     // Không auto-flush theo PrintWriter.
writer.printf("OK");      // Auto-flush, dù không xuống dòng.
writer.printf("OK%n");    // Vừa xuống dòng, vừa auto-flush.
```

Các đoạn trên không có ý nghĩa giống hệt nhau trên mọi loại `Writer` hoặc `PrintStream`. Luôn xác định API đang thực sự gọi.

## 8. `flush()` có phải “ghi thành công” không?

`flush()` có thể chuyển byte khỏi bộ đệm ở tầng Java nhưng **không tương đương**:

- “File đã được ghi bền vững lên thiết bị lưu trữ”: hệ điều hành và thiết bị vẫn có thể đệm. Nếu cần yêu cầu đồng bộ file, phải chọn API và giới hạn phù hợp, ví dụ `FileChannel.force(...)`.
- “Đã đến tận ứng dụng bên kia mạng”: socket/network và ứng dụng nhận có trạng thái riêng. Muốn biết phía nhận đã **xử lý**, cần xác nhận ở tầng giao thức.
- “Không có lỗi I/O”: lời gọi ghi có thể lỗi, và cách báo lỗi tùy lớp.

### `close()` là kết thúc vòng đời

Thông thường dùng `try-with-resources`:

```java
try (BufferedWriter writer = Files.newBufferedWriter(
        path, StandardCharsets.UTF_8)) {
    writer.write("Nội dung");
    writer.newLine();
}
```

Đây là phương thức/khối minh họa cần biến `path` và import `BufferedWriter`, `Files`, `StandardCharsets`. `close()` thường hoàn tất phần đệm còn lại và đóng tài nguyên. Nếu cần **tiếp tục ghi**, hãy `flush()` khi cần, đừng `close()`.

### Lỗi và `checkError()`

`PrintWriter` và `PrintStream` không báo `IOException` trực tiếp từ các phương thức in thông thường; chúng ghi nhận lỗi nội bộ. Có thể kiểm tra:

```java
writer.println("Đã ghi");
if (writer.checkError()) {
    throw new IllegalStateException("Không thể ghi đầu ra");
}
```

`writer` ở đây là `PrintWriter`. **`checkError()` có thể tự gọi flush trước khi kiểm tra trạng thái lỗi**. Do đó khi đo đạc “phương thức nào đã trigger flush”, đừng chen `checkError()` giữa các phép đo mà bỏ qua tác dụng phụ này.

Khác với hai lớp Print, `BufferedWriter.write()` và `BufferedWriter.flush()` có thể ném `IOException`, cho phép ứng dụng xử lý ngoại lệ theo hợp đồng thông thường.

## 9. Auto-flush và hiệu năng

Auto-flush phù hợp với tương tác khi bên nhận cần thấy dữ liệu sớm, nhưng flush quá nhiều có thể làm mất lợi ích của buffering.

Ví dụ:

```java
for (int i = 0; i < 10_000; i++) {
    writer.println(i);
}
```

Nếu `writer` là `PrintWriter` với auto-flush bật, **mỗi lần `println` đều kích hoạt flush**. Với file hoặc mạng, điều này có thể tạo nhiều lượt xử lý I/O không cần thiết.

Khi ghi lượng lớn dữ liệu và không cần thấy ngay từng dòng, cân nhắc `BufferedWriter` hoặc `PrintWriter` tắt auto-flush, kết hợp flush theo đợt và đóng đúng. Ngược lại, với prompt hoặc giao thức hai chiều đang chờ dữ liệu, trì hoãn flush có thể khiến cả hai phía cùng chờ.

**Không có một cấu hình “luôn nhanh nhất”.** Chọn các mốc flush theo nhu cầu giao tiếp và đo đạc hiệu năng với ứng dụng thực tế.

## 10. Bảng đối chiếu nhanh

| Lớp/kiểu luồng | Khi nào flush? | Điều không nên suy luận |
| --- | --- | --- |
| `BufferedWriter` | `flush()`, đóng, hoặc cơ chế chuyển buffer | `newLine()` không tự flush |
| `BufferedOutputStream` | `flush()`, đóng, hoặc buffer được chuyển đi | Ghi newline không tạo trigger riêng |
| `PrintWriter` autoFlush=false | Flush chủ động/đóng hoặc tầng dưới xử lý | `println` không auto-flush khi cờ tắt |
| `PrintWriter` autoFlush=true | **`println`, `printf`, `format`**, flush chủ động/đóng | `print("\n")` và `write("\n")` không tự flush |
| `PrintStream` autoFlush=true | **Ghi byte array, `println`, newline**, flush chủ động/đóng | Không áp dụng y nguyên bảng của `PrintWriter` |
| `System.out` | Tùy `PrintStream` thực tế và cách dùng; có `flush()` | Không mặc định mọi lần `print` đều flush ngay |

Các lớp bên dưới có thể đẩy dữ liệu sớm khi buffer đầy; bảng nêu **điểm trigger theo hợp đồng**, không phải thời gian vật lý byte được hiển thị hoặc gửi đi.

## 11. Những lỗi thường gặp

| Sai lầm | Hậu quả/giải thích | Cách làm |
| --- | --- | --- |
| “`print("\n")` như `println()` về auto-flush” | Sai với `PrintWriter` | Gọi `println` hoặc `flush()` |
| “`BufferedWriter.newLine()` tự flush” | Chỉ viết line separator | Gọi `flush()` ở mốc cần đồng bộ |
| “`printf` phải có `%n` mới flush” | `PrintWriter` trigger trên lời gọi `printf` | Phân biệt format và auto-flush |
| “`PrintStream` và `PrintWriter` giống nhau” | Trigger của `PrintStream` gồm cả byte array/newline | Xem đúng API của lớp |
| “Flush nghĩa là file an toàn nếu mất điện” | OS/thiết bị còn trạng thái riêng | Dùng kỹ thuật đồng bộ file nếu cần |
| “Flush nghĩa là server đã xử lý” | Không có ACK của bên nhận | Thiết kế giao thức xác nhận |
| “Không thấy prompt tức là dữ liệu đã mất” | Có thể còn buffering hoặc chuyển hướng stdout | Flush chủ động và kiểm tra môi trường |
| “Dùng close để hiển thị prompt” | Close kết thúc luồng, không thể tiếp tục ghi | Dùng `flush()` |
| “`checkError` chỉ đọc trạng thái” | Có thể gọi flush | Tính tới tác dụng phụ |
| “Auto-flush luôn tăng hiệu năng” | Flush liên tục có overhead | Chọn tần suất flush hợp lý |

## 12. Tự kiểm tra

1. `new PrintWriter(target, true)` rồi `print("A\n")` có auto-flush không? **Không**.
2. Cùng writer gọi `printf("x=%d", 3)` không có newline có auto-flush không? **Có**.
3. `BufferedWriter.newLine()` có tự flush không? **Không**.
4. `PrintStream` autoFlush=true gọi `write('\n')` có trigger không? **Có**, do newline byte.
5. `PrintStream` autoFlush=true gọi `write(new byte[]{1, 2})` có trigger không? **Có**, do ghi mảng byte.
6. Vì sao nên `System.out.flush()` sau `print("Nhập: ")` trước `Scanner.nextLine()`? **Để chủ động đẩy prompt** trước khi chờ input.
7. `flush()` có chứng minh byte được ghi bền vững vào đĩa hoặc server đã xử lý không? **Không**.
8. `PrintWriter.checkError()` có thể ảnh hưởng số lần flush không? **Có**, vì phương thức có thể gọi flush khi kiểm tra.
9. Với một triệu dòng không cần cập nhật tức thời, auto-flush mỗi dòng có thể gây gì? **Tăng overhead I/O**.

**Ghi nhớ:** `PrintWriter` auto-flush khi gọi **`println`, `printf`, `format`** (nếu bật); `PrintStream` auto-flush theo **`println`, ghi mảng byte và newline** (nếu bật); `BufferedWriter` cần **`flush()` chủ động** ở mốc cần đẩy dữ liệu. Khi yêu cầu thời điểm quan trọng, gọi `flush()` rõ ràng và đừng nhầm với bảo đảm lưu bền vững hay bên nhận đã xử lý.