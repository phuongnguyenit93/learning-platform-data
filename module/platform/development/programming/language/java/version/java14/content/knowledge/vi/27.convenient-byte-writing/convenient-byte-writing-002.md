# Phân biệt ghi byte nguyên dạng với in ký tự trong Java 14+ (`PrintStream.writeBytes`)

## 1. Vấn đề: cùng là “ghi ra luồng”, nhưng dữ liệu có thể khác hoàn toàn

Trong Java, một luồng đầu ra có thể nhận **byte đã có sẵn** hoặc nhận **ký tự/giá trị** cần chuyển thành biểu diễn văn bản. Hai nhu cầu này thường bị nhầm khi dùng `System.out` hoặc một `PrintStream`:

- **Ghi byte nguyên dạng:** ứng dụng đã có một mảng `byte[]` và muốn các giá trị byte ấy đi tới luồng đầu ra **không qua bước mã hóa lại thành ký tự**. Chọn `PrintStream.writeBytes(byte[])` hoặc phương thức ghi byte tương ứng của `OutputStream`.
- **In ký tự hoặc giá trị:** ứng dụng có `String`, `char`, `int`, `boolean`, v.v. và muốn **dạng văn bản dễ đọc**. Chọn `print(...)`, `println(...)` hoặc API dành cho text; `PrintStream` sẽ chuyển các ký tự thành byte bằng **charset** của nó.
- **Chuyển văn bản thành byte theo định dạng được chỉ định:** ứng dụng phải chủ động chọn một charset như UTF-8, ví dụ `text.getBytes(StandardCharsets.UTF_8)`, rồi mới ghi các byte đã mã hóa nếu giao thức/file yêu cầu.

Mọi dữ liệu được đưa tới hệ thống dưới dạng byte cuối cùng đều là **byte**, nhưng *điểm chuyển từ ký tự sang byte* và *nội dung byte được tạo ra* là khác nhau. Vì vậy hai đoạn lệnh sau **không có nghĩa giống nhau**:

```java
out.writeBytes(payload);   // Gửi chính các byte đang có trong payload.
out.print(payload);        // In biểu diễn Object của mảng byte, KHÔNG ghi từng byte.
```

Trong ví dụ, `out` là `PrintStream` và `payload` là `byte[]`. `print(payload)` chọn overload in một đối tượng và thường tạo chuỗi kiểu `[B@...`, không phải nội dung nhị phân. Đây là một lỗi rất phổ biến khi chuyển từ làm việc với chuỗi sang file hoặc giao thức nhị phân.

**Liên hệ Java 14:** `java.io.PrintStream.writeBytes(byte[])` được bổ sung từ **Java 14** và hiện vẫn thuộc API Java SE. Bài sử dụng kiến thức còn áp dụng trên Java 17/21+; không dùng cơ chế preview hay API đã bị loại bỏ.

## 2. Ba tầng dữ liệu: ký tự, byte và cách hiển thị

Một **ký tự Unicode** không đồng nghĩa một byte. Ví dụ ký tự `é`:

```text
Văn bản:              "é"
UTF-8 bytes:          C3 A9
UTF-16 code unit:     00E9
Một byte riêng E9:    KHÔNG phải biểu diễn UTF-8 hợp lệ của "é"
```

Cần phân biệt:

1. **String/char ở Java:** biểu diễn nội dung văn bản; `String` là chuỗi đơn vị mã UTF-16, không phải mảng byte UTF-8 tự nhiên.
2. **Charset encoder:** chuyển văn bản thành chuỗi byte theo quy tắc, ví dụ UTF-8.
3. **OutputStream/PrintStream:** chuyển các byte ra nơi nhận như file, socket, memory buffer hoặc stdout. Với `print`, bước mã hóa nằm **bên trong** `PrintStream`; với `writeBytes`, ứng dụng phải đã có byte cần ghi.

Một dãy byte bất kỳ có thể là **dữ liệu nhị phân**, không nhất thiết là văn bản hợp lệ. Mảng chứa `00 FF 41` chẳng hạn có byte `FF` không hợp lệ khi đứng một mình trong UTF-8. Nếu ta cố **decode nó như text**, có thể thấy ký tự thay thế hoặc ký tự điều khiển; điều đó không có nghĩa `writeBytes` đã sửa các byte.

**Nguyên tắc:** muốn kiểm tra ghi byte nguyên dạng, so sánh **byte[] hoặc biểu diễn hex**, không dựa vào chữ xuất hiện trên màn hình terminal.

## 3. API chính: `PrintStream.writeBytes(byte[])`

Chữ ký phương thức:

```java
public void writeBytes(byte[] buf)
```

Đây là phương thức instance của `java.io.PrintStream`. Nó:

- Ghi **toàn bộ số byte** trong `buf`, theo thứ tự, không tự thêm BOM, newline, dấu cách, delimiter hay metadata.
- Gửi byte **nguyên dạng** xuống luồng đích; nó **không** gọi `toString()` trên mảng, không thực hiện UTF-8 encoding và không in giá trị thập phân của từng byte.
- Tương đương về thao tác ghi với `this.write(buf, 0, buf.length)`.
- Nếu `PrintStream` được tạo với `autoFlush = true`, thao tác viết cả mảng byte kích hoạt flush theo hợp đồng `PrintStream`.
- Không khai báo `throws IOException`, vì `PrintStream` ghi nhận lỗi I/O trong trạng thái nội bộ để người gọi có thể kiểm tra qua `checkError()`.
- Không biến chương trình thành transaction bền vững trên đĩa và cũng không tự kiểm soát giao thức nhiều người gửi.

Ví dụ một `PrintStream` ghi vào memory buffer:

```java
byte[] payload = {0x00, (byte) 0xFF, 0x41};
java.io.ByteArrayOutputStream sink =
        new java.io.ByteArrayOutputStream();

try (java.io.PrintStream out = new java.io.PrintStream(
        sink, true, java.nio.charset.StandardCharsets.UTF_8)) {
    out.writeBytes(payload);
}

byte[] result = sink.toByteArray();
// result chứa đúng 3 byte: 00 FF 41.
```

Đây là đoạn code **trong một phương thức**; các tên lớp đã được viết đầy đủ để dễ nhận diện. Dù tạo `PrintStream` với charset UTF-8, **`writeBytes` không mã hóa lại mảng `payload`**. Charset chỉ ảnh hưởng đến các thao tác **in ký tự**.

### Vì sao cast `(byte) 0xFF`?

Trong Java, `byte` có dấu và miền giá trị từ `-128` đến `127`. Một giá trị byte có các bit `11111111` có thể được biểu diễn trong code là `(byte) 0xFF`, và khi đọc qua `byte` nó có giá trị số học `-1`.

**Bit được ghi** vẫn là `FF`. Nếu muốn hiển thị byte theo miền unsigned `0..255`, dùng `b & 0xFF` hoặc `Byte.toUnsignedInt(b)`. Đừng vì thấy giá trị Java `-1` mà nghĩ luồng sẽ tự tạo dấu trừ và chữ số `1`.

## 4. `print` và `println`: chuyển giá trị thành văn bản

`PrintStream` có nhiều overload của `print` và `println` để tạo **biểu diễn ký tự** của các giá trị:

```java
out.print("Aé");     // In ký tự theo charset của PrintStream.
out.print(255);      // In ba chữ số '2', '5', '5'.
out.print('A');      // In ký tự 'A' được mã hóa.
out.println("OK");   // In "OK" rồi thêm line separator.
```

Đây là các lời gọi minh họa; `out` phải là `PrintStream` đã mở. Khi `out` dùng UTF-8:

- `print("Aé")` tạo ba byte `41 C3 A9`: `A` chiếm một byte, `é` chiếm hai byte.
- `print(255)` tạo ba byte ASCII/UTF-8 `32 35 35` của văn bản `255`.
- `print('A')` tạo byte `41`.
- `println("OK")` tạo byte của `OK` rồi **line separator của môi trường**, thường `0A` trên Unix-like hoặc `0D 0A` trên Windows. Không giả định `println` luôn chỉ thêm đúng một byte `0A`.

**Charset ảnh hưởng:** nếu không chỉ định charset khi khởi tạo, `PrintStream` sử dụng charset mặc định/thích hợp theo constructor/runtime. Charset mặc định của Java có lịch sử cấu hình phụ thuộc phiên bản và môi trường; để kết quả file/giao thức nhất quán, **chỉ định `StandardCharsets.UTF_8` hoặc charset do giao thức yêu cầu**.

Một cách rõ ràng:

```java
PrintStream out = new PrintStream(
        outputStream, true, StandardCharsets.UTF_8);
out.print("Hà Nội");
```

Trong ví dụ `outputStream` phải là `OutputStream` và hai tên lớp được import. Không dùng `Charset.defaultCharset()` để suy luận byte file giao thức nếu tiêu chuẩn đích đã quy định UTF-8.

## 5. Bảng so sánh các phương thức quan trọng

| Lời gọi với `PrintStream out` | Đầu vào | Dữ liệu ra | Có chuyển nội dung thành văn bản không? |
| --- | --- | --- | --- |
| `out.writeBytes(bytes)` | `byte[]` | Chính các byte của mảng | **Không** |
| `out.write(bytes, off, len)` | Một vùng `byte[]` | Chính các byte thuộc vùng | **Không** |
| `out.write(bytes)` | `byte[]` | Chính các byte của mảng | **Không**; khai báo checked `IOException` trong chữ ký |
| `out.write(intValue)` | Một `int` | **Tám bit thấp** của `intValue` thành **một byte** | **Không** |
| `out.print("text")` | `String` | Byte mã hóa text theo charset | **Có** |
| `out.print('é')` | `char` | Byte mã hóa ký tự theo charset | **Có** |
| `out.print(255)` | `int` | Các ký tự của số thập phân `255`, rồi encode | **Có** |
| `out.print(bytes)` | `byte[]` | Biểu diễn object của mảng như `[B@...` | **Có**, nhưng **không** phải nội dung byte |
| `out.println("text")` | `String` | Byte mã hóa text và line separator | **Có**, thêm kết thúc dòng |
| `out.printf(...)` | Format string và đối số | Văn bản đã format và encode | **Có** |

**Chú ý về `write(byte[])`:** từ Java 14, `PrintStream` có override ghi cả mảng byte nhưng chữ ký vẫn khai báo `throws IOException`. Trên một biến kiểu `PrintStream`, nếu gọi `out.write(bytes)`, tại vị trí biên dịch Java có thể phải xử lý checked exception; `out.writeBytes(bytes)` là lựa chọn tiện hơn khi muốn **viết cả mảng không khai báo checked IOException**. Hành vi lỗi thực tế của `PrintStream` được báo qua `checkError()`.

Không nhầm `PrintStream.writeBytes(byte[])` với `DataOutputStream.writeBytes(String)`: phương thức của `DataOutputStream` nhận **`String`**, ghi các **byte thấp** của từng ký tự, không phải bộ mã hóa UTF-8 chuẩn. Hai API có tên giống nhau nhưng ý nghĩa khác nhau; đừng dùng chúng thay thế nhau để lưu text Unicode.

## 6. Trường hợp rất dễ nhầm: `print(255)` khác `write(255)`

```java
out.print(255); // Ghi văn bản "255".
out.write(255); // Ghi đúng một byte 0xFF.
```

Nếu biểu diễn theo hex trên một `PrintStream` UTF-8:

```text
print(255) => 32 35 35
write(255) => FF
```

Giá trị số học `255` xuất hiện ở cả hai dòng mã, nhưng mục đích hoàn toàn khác nhau. Với `write(int)`, Java lấy **tám bit thấp** của số nguyên đầu vào. Vì vậy:

```java
out.write(0xFF);   // FF
out.write(0x1FF);  // FF: tám bit thấp cũng là FF
```

Đây là hai **lần ghi** riêng, mỗi lần ghi một byte. `write(int)` không ném overflow khi nhận giá trị lớn hơn `255`; nếu giao thức yêu cầu byte 0..255, ứng dụng nên kiểm tra miền trước, thay vì âm thầm cắt mất các bit cao.

Nếu muốn tạo **bốn byte của một số nguyên**, không dùng `print(int)` và cũng không dùng một lần `write(int)`. Hãy chọn định dạng nhị phân (ví dụ big-endian/little-endian) và các API như `DataOutputStream.writeInt` hoặc `ByteBuffer.putInt`, rồi mô tả rõ định dạng cho bên nhận.

## 7. Unicode cho thấy khác biệt giữa raw bytes và text

Xét chuỗi:

```java
String text = "Aé";
byte[] utf8 = text.getBytes(StandardCharsets.UTF_8);
```

Khi dùng `PrintStream` đã cấu hình UTF-8:

```java
out.print(text);
```

và:

```java
out.writeBytes(utf8);
```

**có thể tạo cùng dãy byte** `41 C3 A9`. Nhưng điểm khác biệt vẫn quan trọng:

- Với `print(text)`, **`PrintStream` thực hiện mã hóa text** thành byte bằng charset của nó.
- Với `writeBytes(utf8)`, **ứng dụng đã thực hiện mã hóa** thông qua `getBytes(UTF_8)`; stream chỉ ghi các byte đó.
- Hai cách chỉ cho kết quả bằng nhau khi **charset và cách mã hóa** đồng nhất. Nếu text được encode UTF-8 trước nhưng `PrintStream` được cấu hình UTF-16 hoặc một charset khác, chúng không tạo cùng dãy byte.
- Nếu input đã là **binary payload**, không nên decode sang `String` rồi encode lại chỉ để gọi `print`. Các byte không hợp lệ với charset có thể bị thay thế, dẫn đến **mất dữ liệu**.

Ví dụ một byte `FF` trong dữ liệu nhị phân không phải văn bản UTF-8 hợp lệ. Chuyển nó qua `new String(..., UTF_8)` rồi `getBytes(UTF_8)` có thể tạo byte khác do ký tự thay thế. Vì vậy **dữ liệu nhị phân nên đi từ `byte[]` tới output stream**, không đi vòng qua `String`.

### Độ dài ký tự khác độ dài byte

```java
String text = "é";
System.out.println(text.length()); // 1
System.out.println(text.getBytes(StandardCharsets.UTF_8).length); // 2
```

Đây là đoạn đặt trong một phương thức. `String.length()` đếm **UTF-16 code units**, không đếm UTF-8 bytes; với một số ký tự Unicode nằm ngoài Basic Multilingual Plane, số code units cũng khác số Unicode code points.

Với giao thức nhị phân có trường độ dài **theo byte**, dùng `encoded.length` sau khi mã hóa, không dùng `text.length()` để lập độ dài payload.

## 8. Chương trình Java hoàn chỉnh: xem sự khác biệt qua hex

Để tránh phụ thuộc terminal, ví dụ ghi mọi biến thể vào `ByteArrayOutputStream` rồi đổi kết quả thành **hex**. Các kết quả vì vậy độc lập với font terminal và không gửi byte nhị phân lạ trực tiếp ra `System.out`.

Lưu toàn bộ code vào **`Main.java`**:

```java
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.OutputStream;
import java.io.PrintStream;
import java.nio.charset.StandardCharsets;
import java.util.Arrays;
import java.util.function.Consumer;

public class Main {
    static byte[] capture(Consumer<PrintStream> operation) {
        ByteArrayOutputStream sink = new ByteArrayOutputStream();
        try (PrintStream out =
                new PrintStream(sink, true, StandardCharsets.UTF_8)) {
            operation.accept(out);
            if (out.checkError()) {
                throw new IllegalStateException("Output error");
            }
        }
        return sink.toByteArray();
    }

    static String hex(byte[] bytes) {
        StringBuilder result = new StringBuilder();
        for (byte b : bytes) {
            result.append(String.format("%02X", b & 0xFF));
        }
        return result.toString();
    }

    static class FailingOutputStream extends OutputStream {
        @Override
        public void write(int b) throws IOException {
            throw new IOException("simulated failure");
        }
    }

    public static void main(String[] args) {
        byte[] payload = {0x00, (byte) 0xFF, 0x41};
        byte[] raw = capture(out -> out.writeBytes(payload));
        byte[] text = capture(out -> out.print("Aé"));
        byte[] encoded = capture(out ->
                out.writeBytes("Aé".getBytes(StandardCharsets.UTF_8)));
        byte[] numericPrint = capture(out -> out.print(255));
        byte[] numericWrite = capture(out -> out.write(255));
        byte[] numericWriteHigh = capture(out -> out.write(0x1FF));
        byte[] arrayText = capture(out -> out.print(payload));
        byte[] line = capture(out -> out.println("A"));
        byte[] ranged = capture(out ->
                out.write(payload, 0, payload.length));

        boolean error;
        try (PrintStream out = new PrintStream(
                new FailingOutputStream(), false, StandardCharsets.UTF_8)) {
            out.writeBytes(new byte[] {1});
            error = out.checkError();
        }

        System.out.println("RAW_HEX=" + hex(raw));
        System.out.println("RAW_LENGTH=" + raw.length);
        System.out.println("TEXT_UTF8_HEX=" + hex(text));
        System.out.println("ENCODED_EQUALS_PRINT=" +
                Arrays.equals(text, encoded));
        System.out.println("PRINT_255_HEX=" + hex(numericPrint));
        System.out.println("WRITE_255_HEX=" + hex(numericWrite));
        System.out.println("WRITE_LOW8_BITS=" +
                Arrays.equals(numericWrite, numericWriteHigh));
        System.out.println("PRINT_ARRAY_OBJECT=" +
                new String(arrayText, StandardCharsets.UTF_8)
                        .startsWith("[B@"));
        System.out.println("PRINTLN_SEPARATOR_MATCHES=" + Arrays.equals(
                line,
                ("A" + System.lineSeparator())
                        .getBytes(StandardCharsets.UTF_8)));
        System.out.println("RANGE_EQUALS_WRITE_BYTES=" +
                Arrays.equals(raw, ranged));
        System.out.println("CHECK_ERROR_ON_FAILURE=" + error);
    }
}
```

Biên dịch và chạy:

```bash
javac --release 17 -encoding UTF-8 Main.java
java Main
```

**Stdout chính xác đã được kiểm chứng:**

```text
RAW_HEX=00FF41
RAW_LENGTH=3
TEXT_UTF8_HEX=41C3A9
ENCODED_EQUALS_PRINT=true
PRINT_255_HEX=323535
WRITE_255_HEX=FF
WRITE_LOW8_BITS=true
PRINT_ARRAY_OBJECT=true
PRINTLN_SEPARATOR_MATCHES=true
RANGE_EQUALS_WRITE_BYTES=true
CHECK_ERROR_ON_FAILURE=true
```

**Kiểm tra phiên bản:** chương trình cũng đã biên dịch thành công bằng `javac --release 14`, vì các API nó sử dụng, kể cả `PrintStream.writeBytes(byte[])`, đều có trong Java 14. Mã dùng phong cách Java cơ bản phù hợp Java 17+ hiện tại, không cần preview.

## 9. Phân tích từng dòng kết quả

1. **`RAW_HEX=00FF41`:** `writeBytes(payload)` giữ chính ba byte gốc, kể cả byte `00` và `FF` không phù hợp để coi là văn bản thông thường.
2. **`RAW_LENGTH=3`:** không thêm newline, separator, header hay encoding.
3. **`TEXT_UTF8_HEX=41C3A9`:** `print("Aé")` mã hóa ký tự theo UTF-8, với `A` một byte và `é` hai byte.
4. **`ENCODED_EQUALS_PRINT=true`:** với cùng UTF-8, mã hóa trước bằng `getBytes` rồi `writeBytes` cho cùng byte như để `print` mã hóa; điều này **không** biến `writeBytes` thành một hàm mã hóa text.
5. **`PRINT_255_HEX=323535`:** `print(255)` in ba ký tự số thập phân.
6. **`WRITE_255_HEX=FF`:** `write(255)` ghi một byte có các bit bằng `FF`.
7. **`WRITE_LOW8_BITS=true`:** `write(0x1FF)` và `write(0xFF)` cho cùng byte thấp `FF`, vì `write(int)` không in dạng số.
8. **`PRINT_ARRAY_OBJECT=true`:** truyền `byte[]` cho `print` không ghi nội dung; mã kiểm tra tiền tố biểu diễn object `[B@` thay vì so sánh toàn bộ chuỗi có hash có thể khác giữa các lần chạy.
9. **`PRINTLN_SEPARATOR_MATCHES=true`:** `println("A")` thêm line separator đúng theo `System.lineSeparator()`; kiểm tra hoạt động trên cả Windows và Linux/macOS thay vì cố định `\n`.
10. **`RANGE_EQUALS_WRITE_BYTES=true`:** `write(bytes, 0, bytes.length)` và `writeBytes(bytes)` ghi cùng nội dung.
11. **`CHECK_ERROR_ON_FAILURE=true`:** một `OutputStream` cố tình ném `IOException` đã làm `PrintStream` đánh dấu trạng thái lỗi; người gọi kiểm tra bằng `checkError()`.

Bài test cố ý **không in dãy byte raw ra terminal**, tránh để ký tự điều khiển hoặc byte ngoài encoding làm méo đầu ra. Đây là phương pháp kiểm chứng phù hợp hơn cho file nhị phân và protocol payload.

## 10. Vì sao `print(byte[])` không phải `writeBytes(byte[])`?

Java chọn overload của `print` theo kiểu tham số ở thời điểm biên dịch. Có các overload dành cho `String`, `char[]`, `Object`, v.v., nhưng **không có overload `print(byte[])` chuyên để in nội dung byte**.

Vì `byte[]` là một đối tượng Java và không phù hợp `char[]`, lời gọi:

```java
byte[] bytes = {65, 66};
out.print(bytes);
```

được xử lý theo overload in `Object`. Nó áp dụng `String.valueOf(...)`/`toString()` và tạo một chuỗi kiểu:

```text
[B@1a2b3c4d
```

**Dòng trên chỉ minh họa dạng chuỗi**; phần địa chỉ/hash không có giá trị ổn định và **không được kiểm thử bằng so sánh nguyên văn**. Nó **không** in `AB` và cũng không tạo `41 42`.

Nếu mục tiêu là **xem các giá trị byte** khi debug:

```java
System.out.println(java.util.Arrays.toString(bytes)); // [65, 66]
```

Nếu mục tiêu là **chuyển byte đã được biết là văn bản hợp lệ** sang text:

```java
String decoded = new String(bytes, StandardCharsets.UTF_8);
out.print(decoded);
```

Nếu mục tiêu là **gửi đúng hai byte 0x41, 0x42**:

```java
out.writeBytes(bytes);
```

Đó là ba yêu cầu khác nhau; đừng chọn `print(byte[])` chỉ vì từ “print” nghe như “ghi ra màn hình”.

## 11. `writeBytes`, `write` và vấn đề checked `IOException`

Java 14 có hai cách thuận tiện trên `PrintStream` khi muốn ghi **toàn bộ mảng byte**:

```java
out.writeBytes(bytes);
out.write(bytes, 0, bytes.length);
```

Hai cách trên không bắt người gọi khai báo checked `IOException`, và theo hợp đồng tạo cùng byte output. Trong khi đó chữ ký:

```java
out.write(bytes);
```

trên `PrintStream` **vẫn khai báo `throws IOException`**. Java kiểm tra checked exceptions theo **chữ ký API** tại compile time, dù tài liệu nêu rằng triển khai `PrintStream` không thực sự ném `IOException` từ thao tác này mà dùng **error flag**. Đây là lý do `writeBytes` hữu ích khi muốn ghi cả mảng mà không phải viết `try/catch` chỉ vì chữ ký method.

### Đừng nhầm “không ném checked IOException” với “không thể ghi lỗi”

`PrintStream` theo thiết kế thường **không ném `IOException` khi đang ghi**: lỗi ghi vào luồng đích làm thay đổi **trạng thái lỗi** để đọc qua:

```java
out.writeBytes(bytes);
if (out.checkError()) {
    throw new IllegalStateException("Writing bytes failed");
}
```

Đoạn này **không bắt mọi lỗi có thể xảy ra**. Ví dụ, đối số `null` hoặc thao tác bất hợp lệ vẫn có thể ném unchecked exception; lỗi khi **tạo/mở** stream cũng có thể khác với lỗi khi ghi.

Nếu yêu cầu ứng dụng là xử lý **checked IOException rõ ràng** để báo lỗi ghi file/socket, cân nhắc sử dụng `OutputStream` hoặc `Files` trực tiếp thay vì dùng `PrintStream`. `PrintStream` rất tiện cho văn bản/log nhưng error-flag semantics không luôn thích hợp cho dữ liệu nhị phân quan trọng.

## 12. `autoFlush` không phải commit dữ liệu bền vững

Một `PrintStream` có thể được tạo:

```java
new PrintStream(outputStream, true, StandardCharsets.UTF_8)
```

Giá trị `true` kích hoạt `autoFlush` theo các điều kiện được tài liệu quy định, bao gồm khi **ghi byte array** bằng `writeBytes` và khi `println` kết thúc dòng. Điều này có thể giúp đẩy dữ liệu **qua buffer của stream**, nhưng:

- Không có nghĩa mọi byte đã được xử lý bởi phía nhận socket.
- Không tạo một transaction gồm nhiều lời gọi ghi.
- Không thay thế các cơ chế sync/durability đặc thù của file system/storage khi cần chống mất điện.
- Không nhất thiết buộc một lần `print("text")` chưa có newline phải flush theo đúng thời điểm bạn đoán.

`out.flush()` và `out.checkError()` có vai trò riêng. `checkError()` cũng thực hiện flush khi phù hợp rồi trả trạng thái lỗi. Khi đóng `PrintStream`, luồng đích cũng được đóng theo vòng đời của nó.

**Lưu ý:** Không tự đóng `System.out` trong thư viện hay một hàm tiện ích chung; `System.out` là luồng dùng chung của tiến trình. Hãy đóng những `PrintStream` do ứng dụng **tự tạo và sở hữu**.

## 13. Dữ liệu nhị phân nên dùng API nào?

`PrintStream.writeBytes` là tiện ích hợp lệ, nhưng nếu mục đích chính là **lưu byte của file hoặc giao thức**, các API byte-oriented có hợp đồng lỗi rõ hơn thường phù hợp hơn.

### Lưu file nhị phân

```java
import java.nio.file.Files;
import java.nio.file.Path;

Path path = Path.of("payload.bin");
byte[] payload = {0x00, (byte) 0xFF, 0x41};

Files.write(path, payload);
byte[] restored = Files.readAllBytes(path);
System.out.println(java.util.Arrays.equals(payload, restored)); // true
```

Đây là đoạn **trong một phương thức có `throws IOException` hoặc xử lý IOException**. Nó ghi file ở working directory hiện tại; trong ứng dụng thực tế nên chọn đường dẫn dữ liệu thích hợp và kiểm soát quyền ghi. `Files.write` ở đây không tự tạo transaction chống mất điện hoặc bảo đảm cập nhật file nguyên tử.

### Ghi vào một OutputStream

```java
try (java.io.OutputStream out = java.nio.file.Files.newOutputStream(path)) {
    out.write(payload);
}
```

Đây là code đặt trong phương thức có `path` và `payload` đã khai báo. `OutputStream.write(byte[])` gửi byte nguyên dạng nhưng thường khai báo `IOException`, thuận tiện khi cần phản ứng trực tiếp với lỗi ghi. Không cần bọc thêm `PrintStream` nếu không hề có nhu cầu in văn bản.

### Lưu văn bản với charset rõ ràng

```java
java.nio.file.Files.writeString(
        java.nio.file.Path.of("message.txt"),
        "Xin chào",
        java.nio.charset.StandardCharsets.UTF_8);
```

Đoạn này dùng `Files.writeString` để ghi **văn bản**. Đây là lựa chọn rõ ràng khi mục đích là file text UTF-8, không phải gửi một mảng byte giao thức đã được chuẩn bị.

### Mã hóa thủ công rồi gửi byte

```java
String message = "Xin chào";
byte[] utf8 = message.getBytes(StandardCharsets.UTF_8);
out.writeBytes(utf8);
```

Đây cũng là cách hợp lệ **nếu `out` là `PrintStream`** và bạn cố ý quyết định bộ mã hóa bên ngoài. Đừng thực hiện mã hóa **hai lần** hoặc chuyển dãy byte nhị phân sang text không rõ charset chỉ để dùng `print`.

## 14. Giao thức pha text và binary: phải quy định ranh giới

Một giao thức truyền file có thể gồm header văn bản và payload nhị phân. Trong trường hợp đó, không thể chỉ gọi `println(header)` rồi `writeBytes(data)` một cách tùy tiện mà không định nghĩa:

- **Charset** của header (ví dụ ASCII hoặc UTF-8).
- **Line separator** trên giao thức (ví dụ bắt buộc CRLF, không dùng mặc định OS).
- **Độ dài payload** tính theo **byte**, không theo số ký tự.
- Cách phân biệt kết thúc header với bắt đầu payload.
- Cách phía nhận kiểm tra đủ byte và xử lý lỗi/đứt kết nối.
- Quy tắc đồng bộ nếu nhiều thread cùng ghi vào một luồng.

Ví dụ một header UTF-8 có nội dung `"length=3\n"` phải được **quy định cụ thể** trong protocol. Nếu protocol yêu cầu LF, đừng dùng `println` với line separator phụ thuộc OS rồi giả định luôn là LF. Có thể tạo bytes rõ ràng:

```java
byte[] header = "length=3\n".getBytes(StandardCharsets.UTF_8);
byte[] body = {0x00, (byte) 0xFF, 0x41};

out.writeBytes(header);
out.writeBytes(body);
```

Đây là ví dụ tối giản về **framing**, không phải một protocol production đầy đủ. Người nhận phải biết trước quy ước ký tự của header, cách đọc đúng ba byte payload và xử lý lỗi. Việc dùng hai lần `writeBytes` **không** làm hai lần ghi trở thành atomic delivery.

**Tách trách nhiệm:** codec quyết định cách biến text/số thành bytes; transport quyết định cách gửi bytes; application protocol quyết định cấu trúc message. `writeBytes` chỉ thực hiện phần **gửi các bytes được cấp**.

## 15. Không dùng console để kiểm tra độ đúng của binary payload

Nếu ghi:

```java
System.out.writeBytes(new byte[] {0, (byte) 0xFF, 65});
```

hệ thống nhận **ba byte nguyên dạng**; nhưng terminal có thể ẩn `00`, hiển thị ký tự thay thế cho `FF` hoặc xử lý các byte điều khiển đặc biệt. Không thể nhìn màn hình rồi suy ra có bao nhiêu byte thực sự được xuất.

**Cách kiểm chứng tốt hơn:**

1. Ghi vào `ByteArrayOutputStream` hoặc file test.
2. So sánh bằng `Arrays.equals(expected, actual)`.
3. Nếu cần log, hiển thị hex hoặc một biểu diễn có escape phù hợp; không log chuỗi nhị phân như thể luôn UTF-8 hợp lệ.
4. Test cả byte `0x00`, `0x7F`, `0x80`, `0xFF`; test dữ liệu dài và mảng rỗng nếu ứng dụng có thể gửi.
5. Test đường lỗi bằng một `OutputStream` giả lập lỗi như `FailingOutputStream` trong chương trình chạy.
6. Nếu dữ liệu là text, test charset cố định và sự khác nhau giữa `print`, `println` và `writeBytes(text.getBytes(charset))`.

Một kết quả bằng nhau khi chỉ dùng ký tự ASCII như `"ABC"` **chưa đủ** để phát hiện nhầm lẫn encoding, bởi ASCII trùng byte trong nhiều charset phổ biến. Hãy thêm ký tự đa byte như `é`, `ắ` hoặc emoji khi kiểm thử văn bản Unicode.

## 16. Lỗi và nhầm lẫn thường gặp

| Lỗi/nhận định sai | Vì sao sai | Cách sửa |
| --- | --- | --- |
| “`print(byte[])` ghi nội dung byte” | In `Object.toString()` của mảng | `writeBytes(byte[])` hoặc `OutputStream.write(byte[])` |
| “`writeBytes` chuyển String sang UTF-8” | Nó nhận **byte[]** và không encode | `text.getBytes(UTF_8)` trước khi ghi |
| “`print(255)` và `write(255)` giống nhau” | Một bên in chữ số `255`; một bên ghi byte `FF` | Chọn theo định dạng cần xuất |
| “Byte `FF` là một ký tự UTF-8” | Byte đơn `FF` không hợp lệ trong UTF-8 | Đừng decode dữ liệu nhị phân tùy tiện |
| “`write(0x1FF)` ghi hai byte” | `write(int)` chỉ ghi tám bit thấp | Dùng API ghi nhiều byte với encoding và byte order rõ ràng |
| “`println` luôn thêm `\n` một byte” | Dùng line separator theo nền tảng | Theo protocol dùng newline bytes cụ thể |
| “`byte[]` có dấu nên không thể biểu diễn `FF`” | `(byte)0xFF` giữ đúng tám bit `FF` | Đổi sang unsigned khi hiển thị bằng `& 0xFF` |
| “Đã có UTF-8 ở mảng rồi thì `print(mảng)` vẫn giữ UTF-8” | `print(byte[])` không hiểu mảng là text | `writeBytes` hoặc decode rõ ràng nếu mục tiêu là text |
| “`autoFlush` nghĩa là dữ liệu đã ghi bền trên đĩa” | Flush stream không phải transaction/storage sync | Dùng cơ chế phù hợp với storage |
| “`PrintStream` không ném IOException nên luôn ghi thành công” | Lỗi có thể được lưu ở error flag | `checkError()`; cân nhắc OutputStream cho binary |
| “`String.length()` bằng số byte UTF-8” | String đếm UTF-16 units | Dùng `getBytes(UTF_8).length` |
| “`DataOutputStream.writeBytes(String)` giống `PrintStream.writeBytes(byte[])`” | Một API nhận String và lấy byte thấp từng char; một API nhận byte[] nguyên dạng | Phân biệt class, signature và định dạng |
| “Ghi binary ra console rồi nhìn thấy đúng là đã test xong” | Terminal có thể diễn giải/hide/control byte | So sánh mảng byte hoặc file bằng hex |
| “Ghi text và binary liên tiếp sẽ tự có ranh giới” | Luồng chỉ là chuỗi bytes | Định nghĩa framing, charset và length rõ ràng |

## 17. Tự kiểm tra nhanh

**Câu 1.** Hai lời gọi nào sau đây ghi cùng một bộ ba byte `00 FF 41`?

```java
byte[] payload = {0x00, (byte) 0xFF, 0x41};
// A: out.writeBytes(payload);
// B: out.write(payload, 0, payload.length);
// C: out.print(payload);
```

**Đáp án:** A và B. C in biểu diễn `Object` của mảng.

**Câu 2.** Với `PrintStream` UTF-8, `print("é")` tạo byte gì? `write(0xE9)` có giống không?

**Đáp án:** `print("é")` tạo **`C3 A9`**, còn `write(0xE9)` tạo **một byte `E9`**. Chúng không giống nhau.

**Câu 3.** Khi cần gửi đúng một byte có giá trị unsigned 255, dùng `print(255)` có đúng không?

**Đáp án:** Không. `print(255)` in chuỗi chữ số `255`. Dùng `write(255)` hoặc `writeBytes(new byte[]{(byte)0xFF})` tùy cấu trúc code.

**Câu 4.** Hai lần `println("OK")` chạy trên Windows và Linux có bảo đảm cùng bytes không?

**Đáp án:** Không. Line separator có thể khác. Nếu giao thức yêu cầu bytes chính xác, tự encode terminator theo giao thức.

**Câu 5.** Đã gọi `PrintStream.writeBytes` và không thấy ngoại lệ checked `IOException`. Có chắc ghi thành công không?

**Đáp án:** Không. `PrintStream` thường lưu lỗi I/O vào trạng thái nội bộ; kiểm tra `checkError()` hoặc dùng `OutputStream` phù hợp với hợp đồng lỗi ứng dụng.

**Câu 6.** Vì sao `"é".length() == 1` nhưng `"é".getBytes(UTF_8).length == 2`?

**Đáp án:** `String.length()` đếm UTF-16 units; UTF-8 dùng hai byte để mã hóa ký tự `é`.

**Câu 7.** Nếu một protocol yêu cầu payload có độ dài chính xác, nên tính độ dài trước hay sau khi chuyển text sang byte?

**Đáp án:** **Sau khi mã hóa** theo charset protocol, rồi truyền `byte[].length`; không dùng số ký tự làm byte length.

**Ghi nhớ:** `PrintStream.writeBytes(byte[])` được thêm trong Java 14 để **ghi nguyên một mảng byte** tiện lợi, không cần catch checked `IOException` theo chữ ký API. `print` và `println` lại biến **ký tự/giá trị thành văn bản**, rồi mã hóa bằng charset của stream. Chọn thao tác dựa trên **thứ mà hệ thống nhận cần: dãy byte chính xác hay dạng chữ có thể đọc**. Dữ liệu nhị phân cần kiểm bằng byte/hex; dữ liệu text cần charset rõ ràng.

### Tài liệu chính thức

- [Oracle Java SE 14 — PrintStream, `writeBytes(byte[])` (Since: 14)](https://docs.oracle.com/en/java/javase/14/docs/api/java.base/java/io/PrintStream.html).
- [Oracle Java SE 21 — PrintStream (writeBytes, print, println, write, checkError)](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/io/PrintStream.html).
- [Oracle Java SE 21 — OutputStream](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/io/OutputStream.html).
- [Oracle Java SE 21 — Files.write / writeString](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/Files.html).
- [Oracle Java SE 21 — StandardCharsets](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/charset/StandardCharsets.html).
- [Oracle Java SE 21 — ByteArrayOutputStream](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/io/ByteArrayOutputStream.html).
