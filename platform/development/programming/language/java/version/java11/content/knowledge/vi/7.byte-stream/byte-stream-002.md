# Đọc đến EOF trước khi đủ số byte yêu cầu (Byte stream — Java 11+)

## 1. Bài toán: yêu cầu N byte nhưng nguồn kết thúc sớm

Khi đọc dữ liệu từ `InputStream`, ứng dụng có thể **muốn nhận đủ một số byte xác định**, chẳng hạn một bản ghi nhị phân dài 8 byte, một header dài 12 byte hoặc một payload mà protocol đã công bố độ dài. Tuy nhiên, nguồn có thể kết thúc (**EOF — End Of File/Stream**) trước khi cung cấp đủ số byte đó.

Ví dụ, luồng chỉ chứa ba byte ASCII tương ứng với `ABC`, nhưng chương trình yêu cầu đọc **5 byte**. Cách xử lý đúng tùy hợp đồng dữ liệu:

- **Đọc tối đa 5 byte, chấp nhận phần còn lại ngắn hơn:** nhận đủ ba byte `A`, `B`, `C` rồi kết thúc bình thường. `InputStream.readNBytes(5)` trả về mảng **dài 3**, không tự thêm byte 0 để đủ 5 byte.
- **Bắt buộc phải có chính xác 5 byte:** trường dữ liệu bị thiếu; chương trình phải nhận diện lỗi thiếu dữ liệu, ví dụ tự ném `EOFException` khi kết quả ngắn hơn dự kiến hoặc dùng `DataInputStream.readFully(...)`.
- **Không biết trước tổng số byte:** đọc theo các khối trong vòng lặp cho tới khi nhận tín hiệu EOF, hoặc dùng API đọc hết khi dữ liệu đủ nhỏ và có giới hạn phù hợp.

Đây là hành vi cơ bản của các byte stream Java đang được dùng hiện nay. **EOF không mặc nhiên là lỗi**: EOF là điều kiện kết thúc luồng. Nó trở thành lỗi nghiệp vụ khi định dạng dữ liệu **cam kết đủ N byte** mà nguồn kết thúc sớm.

## 2. Dấu hiệu EOF khác nhau giữa các phương thức

Các API phổ biến trong `java.io.InputStream` có cách báo hết luồng khác nhau:

| Phương thức | Kết quả khi gặp EOF | Điều cần hiểu |
| --- | --- | --- |
| `int read()` | Trả về `-1` nếu đã hết byte trước khi đọc | Nếu có byte, trả về giá trị `0..255`; byte có giá trị 0 không phải EOF |
| `int read(byte[] b)` | Với mảng không rỗng, trả `-1` khi không thể đọc byte nào do EOF | Có thể trả **ít byte hơn `b.length`** dù luồng chưa EOF |
| `int read(byte[] b, int off, int len)` | Với `len > 0`, trả `-1` tại EOF khi chưa đọc byte nào | Một lời gọi không được bảo đảm lấp đầy `len` byte |
| `byte[] readNBytes(int len)` | Trả mảng có **độ dài nhỏ hơn `len`** nếu EOF xuất hiện sớm; có thể dài `0` | Có từ **Java 11**; đọc đến đủ `len`, EOF hoặc lỗi I/O |
| `int readNBytes(byte[] b, int off, int len)` | Trả số byte thực đọc `0..len`; tại EOF trả `0` nếu `len > 0` và không còn byte | Có từ **Java 9**, vẫn dùng trong Java 11+ |
| `void DataInputStream.readFully(byte[] b)` | Ném `EOFException` khi không có đủ byte để điền toàn bộ mảng | Phù hợp khi bắt buộc đủ đúng số byte |
| `void DataInputStream.readFully(byte[] b, int off, int len)` | Ném `EOFException` khi thiếu byte trước khi điền đủ `len` byte | Hữu ích cho bản ghi nhị phân có độ dài cố định |

**Phân biệt cốt lõi:** một lần `read(byte[], ...)` trả về số byte **nhỏ hơn yêu cầu** chưa đủ để kết luận EOF, vì `read` được phép trả về sớm sau khi đã nhận một số byte. Ngược lại, theo hợp đồng của `readNBytes(...)`, phương thức chờ cho tới khi đọc đủ lượng được yêu cầu, gặp EOF hoặc ném ngoại lệ; nếu **trả về ít byte hơn yêu cầu và không có ngoại lệ**, tình huống đọc thông thường là đã chạm EOF.

**Trường hợp `len == 0`:** `readNBytes(0)` trả mảng rỗng; `readNBytes(b, off, 0)` trả `0` mà không cần đọc. Vì thế, giá trị `0` không chứng minh EOF khi yêu cầu đọc 0 byte.

## 3. `readNBytes(int len)`: chỉ nhận số byte còn lại

Cú pháp:

```java
byte[] actual = input.readNBytes(expectedLength);
```

Các đặc điểm:

1. `input` là `InputStream` chưa đóng; `expectedLength` phải không âm.
2. Phương thức cố đọc **tối đa `expectedLength` byte**, chờ cho tới khi đủ, EOF hoặc lỗi I/O.
3. Mảng trả về dài **bằng số byte thực nhận**; khi gặp EOF sớm, mảng **ngắn hơn yêu cầu**, không có padding.
4. Nếu stream đã ở EOF và `expectedLength > 0`, trả về mảng rỗng `byte[0]`.
5. Nếu đọc đủ `expectedLength` byte, mảng có đúng độ dài đó, nhưng **điều này không khẳng định sau mảng không còn byte nào**: dữ liệu tiếp theo có thể vẫn còn trong stream.
6. Phương thức **không tự đóng** `InputStream` và có thể ném `IOException` hoặc `OutOfMemoryError` với yêu cầu cấp phát lớn.

Ví dụ thu gọn:

```java
byte[] source = {65, 66, 67}; // ASCII: A, B, C
try (java.io.InputStream in = new java.io.ByteArrayInputStream(source)) {
    byte[] data = in.readNBytes(5);
    System.out.println(java.util.Arrays.toString(data)); // [65, 66, 67]
    System.out.println(data.length);                      // 3
}
```

Ở đây `len = 5` là **giới hạn số byte yêu cầu**, không phải cam kết rằng mảng kết quả luôn dài 5. Chương trình cần kiểm tra `data.length` khi logic tiếp theo đòi hỏi đủ số byte.

## 4. `readNBytes(byte[] b, int off, int len)`: giữ buffer và số byte đọc

Overload này ghi vào một mảng byte do người gọi cấp phát:

```java
byte[] buffer = new byte[10];
int actualCount = input.readNBytes(buffer, 2, 5);
```

Nếu trả về `3`, chỉ có `buffer[2]`, `buffer[3]`, `buffer[4]` là ba byte hợp lệ mới đọc. Các phần còn lại của mảng, kể cả các vị trí trong vùng yêu cầu chưa được điền, **giữ nguyên giá trị trước đó** khi kết thúc bình thường do EOF. Không được xử lý vô điều kiện cả 5 byte vì sẽ lẫn dữ liệu cũ hoặc byte mặc định.

Quy tắc:

- `off` là vị trí bắt đầu trong `buffer`; `len` là **số byte muốn đọc**.
- Cặp `off, len` phải nằm trong giới hạn mảng (`off >= 0`, `len >= 0`, `len <= buffer.length - off`).
- Khi đọc bình thường, kết quả là số nguyên trong đoạn `0..len`. Trái với `read()`, overload này **không trả `-1` tại EOF**.
- Đặt `len = 0` trả về `0` mà không dùng dữ liệu; nếu `len > 0` và stream đã EOF, cũng trả về `0`.
- Nếu có `IOException`, **không giả định** buffer hay vị trí stream còn nguyên trạng thái trước lời gọi; một số byte có thể đã được đọc/cập nhật trước khi lỗi xảy ra.

Ví dụ chính ở mục 6 tạo buffer chứa các dấu chấm (ASCII 46), đọc 5 byte từ nguồn chỉ có `ABC` và nhận lại `3`, sau đó minh họa chính xác phần buffer không thay đổi.

## 5. `read(byte[])` có thể trả thiếu byte dù chưa EOF

Một lời gọi `read(buffer)` hoặc `read(buffer, off, len)` **không phải thao tác “đọc chắc chắn đúng len byte”**. Nó được phép trả về khi đã nhận một số byte, tùy loại stream và cách triển khai.

Ví dụ, trong ứng dụng mạng hoặc lớp stream tùy chỉnh, một lần đọc có thể nhận 2 byte mặc dù vẫn còn dữ liệu. Việc thấy số trả về nhỏ hơn chiều dài buffer **không phải** bằng chứng rằng đã tới EOF. Chỉ `-1` là tín hiệu EOF của `read(...)` với yêu cầu đọc có độ dài dương.

Một triển khai tùy chỉnh trong ví dụ bên dưới giới hạn mỗi lượt `read(byte[], off, len)` nhận tối đa 2 byte. Vì vậy:

- Lần `read(buffer)` đầu trả `2`, dù còn ký tự `C` chưa đọc.
- Lần `read()` tiếp theo trả `67` (mã của `C`), chứng minh lần trước chưa tới EOF.
- Nếu thay bằng `readNBytes(5)` với nguồn chỉ chứa `ABC`, API tiếp tục các lượt đọc và cuối cùng trả mảng dài `3` khi gặp EOF.

**Hệ quả:** nếu bạn cần đúng `N` byte, không được chỉ gọi `read(buffer)` một lần rồi sử dụng toàn bộ buffer.

## 6. Chương trình Java 11 hoàn chỉnh: EOF đến sớm và ba cách xử lý

Tạo tệp **`EarlyEofDemo.java`**:

```java
import java.io.ByteArrayInputStream;
import java.io.DataInputStream;
import java.io.EOFException;
import java.io.FilterInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.util.Arrays;

public class EarlyEofDemo {
    static final byte[] PAYLOAD = "ABC".getBytes(StandardCharsets.US_ASCII);

    // Chỉ cho mỗi lần read(byte[], off, len) nhận tối đa 2 byte.
    static class ChunkedInputStream extends FilterInputStream {
        ChunkedInputStream(byte[] data) {
            super(new ByteArrayInputStream(data));
        }

        @Override
        public int read(byte[] b, int off, int len) throws IOException {
            return super.read(b, off, Math.min(len, 2));
        }
    }

    // Hợp đồng: bắt buộc nhận đủ count byte, nếu không báo lỗi.
    static byte[] requireExactly(InputStream in, int count) throws IOException {
        byte[] data = in.readNBytes(count);
        if (data.length != count) {
            throw new EOFException(
                    "Expected " + count + ", received " + data.length);
        }
        return data;
    }

    public static void main(String[] args) throws IOException {
        try (InputStream in = new ByteArrayInputStream(PAYLOAD)) {
            byte[] bytes = in.readNBytes(5);
            System.out.println("readNBytes(5): " + Arrays.toString(bytes));
            System.out.println("length: " + bytes.length);
            System.out.println("read() after EOF: " + in.read());
            System.out.println("readNBytes(5) after EOF: " + in.readNBytes(5).length);
        }

        try (InputStream in = new ByteArrayInputStream(PAYLOAD)) {
            byte[] buffer = new byte[6];
            Arrays.fill(buffer, (byte) '.');
            int count = in.readNBytes(buffer, 1, 5);
            System.out.println("buffered count: " + count);
            System.out.println("buffered content: " + Arrays.toString(buffer));
            System.out.println("buffered next: " + in.readNBytes(buffer, 1, 5));
        }

        try (InputStream in = new ChunkedInputStream(PAYLOAD)) {
            byte[] buffer = new byte[5];
            int count = in.read(buffer);
            System.out.println("single read: " + count);
            System.out.println("next byte: " + in.read());
        }

        try (InputStream in = new ChunkedInputStream(PAYLOAD)) {
            System.out.println(
                    "chunked readNBytes(5) length: " + in.readNBytes(5).length);
        }

        try (InputStream in = new ByteArrayInputStream(PAYLOAD)) {
            try {
                requireExactly(in, 5);
                System.out.println("exact: success");
            } catch (EOFException expected) {
                System.out.println("exact: " + expected.getMessage());
            }
        }

        try (DataInputStream in =
                     new DataInputStream(new ByteArrayInputStream(PAYLOAD))) {
            try {
                in.readFully(new byte[5]);
                System.out.println("readFully: success");
            } catch (EOFException expected) {
                System.out.println("readFully: EOFException");
            }
        }

        try (InputStream in = new ByteArrayInputStream(new byte[0])) {
            System.out.println("empty source readNBytes: " + in.readNBytes(5).length);
        }
    }
}
```

Biên dịch và chạy bằng **JDK 11 trở lên**. Nếu đang dùng JDK mới, `--release 11` kiểm tra khả năng biên dịch tương thích Java 11:

```bash
javac --release 11 -encoding UTF-8 EarlyEofDemo.java
java EarlyEofDemo
```

**Đầu ra chính xác:**

```text
readNBytes(5): [65, 66, 67]
length: 3
read() after EOF: -1
readNBytes(5) after EOF: 0
buffered count: 3
buffered content: [46, 65, 66, 67, 46, 46]
buffered next: 0
single read: 2
next byte: 67
chunked readNBytes(5) length: 3
exact: Expected 5, received 3
readFully: EOFException
empty source readNBytes: 0
```

Giải thích theo thứ tự:

1. `PAYLOAD` chứa ba byte ASCII `A=65`, `B=66`, `C=67`. `readNBytes(5)` trả đúng 3 byte khi EOF xuất hiện; lần `read()` sau trả `-1`, trong khi `readNBytes(5)` sau EOF trả mảng rỗng (độ dài `0`).
2. Buffer được điền dấu `'.'` tương ứng byte `46`. Khi gọi `readNBytes(buffer, 1, 5)`, phương thức chỉ sửa ba vị trí `1, 2, 3` thành `65, 66, 67`; vị trí `0, 4, 5` vẫn là `46`. Lần gọi tiếp theo nhận `0` vì đã EOF.
3. `ChunkedInputStream` minh họa một stream có **partial read**: `read(buffer)` lần đầu nhận 2 byte, dù byte `C` vẫn còn và lần `read()` tiếp theo trả `67`.
4. `readNBytes(5)` tiếp tục đọc qua các khối, rồi trả mảng chỉ dài 3 vì EOF đến trước khi đủ 5.
5. `requireExactly(...)` dùng độ dài mảng để chuyển sự kiện “EOF đến sớm” thành `EOFException` theo hợp đồng ứng dụng. `DataInputStream.readFully` thực hiện cùng chính sách “phải đủ byte” mà không yêu cầu tự viết kiểm tra độ dài.
6. Luồng rỗng trả mảng rỗng khi gọi `readNBytes(5)`; kết quả này là hợp lệ đối với phép đọc “tối đa 5 byte”, nhưng là thiếu dữ liệu nếu định dạng bắt buộc có 5 byte.

Ví dụ sử dụng `ByteArrayInputStream` để kết quả luôn xác định và không phụ thuộc hệ điều hành, tập tin hay mạng. Kết luận về EOF/partial read vẫn áp dụng cho `FileInputStream` và nhiều loại `InputStream` khác theo hợp đồng của phương thức.

## 7. Khi nào trả thiếu byte là hợp lệ và khi nào phải coi là lỗi?

### 7.1. Tệp hoặc payload **có độ dài cố định**

Ví dụ protocol nhị phân quy định 4 byte đầu là header. Nếu chưa đủ 4 byte mà đã EOF, đó là **dữ liệu bị cắt cụt (truncated)**. Khi ấy có thể dùng:

```java
static byte[] readHeader(InputStream in) throws IOException {
    byte[] header = in.readNBytes(4);
    if (header.length != 4) {
        throw new EOFException(
                "Truncated header: expected 4 bytes, got " + header.length);
    }
    return header;
}
```

Đây là đoạn phương thức minh họa; trong file thực tế phải có `import java.io.InputStream;`, `IOException`, `EOFException`. Không được điền thêm byte `0` rồi xem như dữ liệu hợp lệ, vì byte `0` có thể là giá trị dữ liệu thực và sẽ làm mất khả năng phát hiện cắt cụt.

Nếu đã có buffer kích thước chính xác, `DataInputStream` cũng phù hợp:

```java
// Minh họa trong phạm vi có InputStream in và xử lý IOException.
DataInputStream data = new DataInputStream(in);
byte[] header = new byte[4];
data.readFully(header); // Ném EOFException nếu EOF đến sớm.
```

Khi `readFully` ném ngoại lệ, một phần buffer có thể đã bị thay đổi và các byte của stream có thể đã bị tiêu thụ; **không dùng buffer đó như một bản ghi hoàn chỉnh**.

### 7.2. Luồng có độ dài biến đổi, EOF là điểm kết thúc bình thường

Một vòng lặp với buffer phù hợp khi đọc đến EOF mà không biết tổng số byte:

```java
// Mã minh họa: xử lý n byte hợp lệ được đọc trong mỗi lượt.
byte[] buffer = new byte[8192];
int n;
while ((n = input.read(buffer)) != -1) {
    if (n > 0) {
        // Chỉ xử lý buffer[0] tới buffer[n - 1].
    }
}
```

Đoạn trên cần biến `input` là `InputStream` hợp lệ và thay comment bằng logic xử lý thực tế. Mỗi lượt chỉ xử lý **`n` byte vừa nhận**, không xử lý cả buffer một cách mặc định.

Đối với luồng **nhỏ và đáng tin cậy**, `input.readAllBytes()` có thể tiện hơn; nhưng không đọc vô hạn dữ liệu chưa xác định kích thước vào bộ nhớ. Với dữ liệu lớn hoặc có nguồn ngoài, dùng buffer và kiểm soát giới hạn bộ nhớ/byte phù hợp.

### 7.3. Chọn theo contract dữ liệu

| Contract của dữ liệu | Cách xử lý phù hợp |
| --- | --- |
| “Cho tôi **tối đa** `N` byte, có bao nhiêu nhận bấy nhiêu” | `readNBytes(N)`, sau đó kiểm tra `byte[].length` |
| “Điền vào buffer, cần biết thực sự đọc bao nhiêu” | `readNBytes(buffer, off, N)`, chỉ xử lý `N_thực_đọc` |
| “Bắt buộc có **đủ đúng** `N` byte” | `DataInputStream.readFully` hoặc `readNBytes(N)` rồi kiểm tra độ dài, ném `EOFException` nếu thiếu |
| “Từng khối bất kỳ cho tới EOF” | Vòng lặp `read(buffer)` cho tới `-1` |
| “Đọc toàn bộ dữ liệu nhỏ, đã biết an toàn về kích thước” | `readAllBytes()`, nhưng phải cân nhắc bộ nhớ |

## 8. Những điểm dễ nhầm và cách sửa

| Hiểu sai hoặc lỗi thường gặp | Hành vi đúng và cách khắc phục |
| --- | --- |
| “`readNBytes(5)` luôn trả mảng 5 byte” | Có thể trả ngắn hơn khi EOF đến sớm; kiểm tra `result.length` |
| “`read(buffer)` trả ít hơn buffer.length tức đã EOF” | Chưa chắc; `read` có thể short read khi còn byte; tiếp tục đọc nếu cần |
| “Tất cả phương thức đọc trả `-1` tại EOF” | `read()`/`read(byte[])` dùng `-1`; `readNBytes(int)` dùng mảng ngắn/rỗng và overload nhận buffer dùng `0` |
| “`readNBytes` ném `EOFException` khi thiếu byte” | Không tự ném chỉ vì EOF sớm; kết quả ngắn là bình thường theo API |
| “`DataInputStream.readFully` trả số byte đã đọc” | Trả về `void` nếu đủ; ném `EOFException` khi thiếu |
| “Buffer chưa được ghi chắc chắn có giá trị 0” | Byte chưa được ghi giữ giá trị cũ; dùng đúng `actualCount` |
| “`input.available() == 0` có nghĩa EOF” | `available()` là ước lượng lượng byte có thể đọc mà không block, không phải cách xác nhận EOF |
| “`read() == 0` nghĩa EOF” | `0` có thể là byte dữ liệu hợp lệ; `-1` mới là EOF của `read()` |
| “`readNBytes(0)` trả mảng rỗng tức nguồn đã hết” | Yêu cầu 0 byte sẽ có kết quả rỗng ngay, ngay cả khi stream còn dữ liệu |
| “Đã gặp IOException thì cứ coi như EOF” | `IOException` là lỗi I/O; stream/buffer có thể đã thay đổi một phần, cần xử lý lỗi và đóng stream |
| “`readAllBytes()` luôn tốt hơn vòng lặp” | Đọc toàn bộ luồng vào bộ nhớ có thể tốn nhiều RAM; dùng buffer cho dữ liệu lớn hoặc không giới hạn |

## 9. Quản lý tài nguyên, lỗi I/O và giới hạn bộ nhớ

- Sử dụng `try-with-resources` để **đóng stream** khi hoàn tất, nhất là với tệp và socket. `readNBytes(...)` tự nó **không đóng stream**.
- `readNBytes(...)` là thao tác **có thể block** cho tới khi đủ byte, EOF hoặc lỗi I/O. Với nguồn mạng, cân nhắc timeout và cơ chế quản lý kết nối phù hợp, tránh chờ vô thời hạn.
- Không cấp phát buffer theo con số độ dài nhận từ dữ liệu bên ngoài mà **chưa kiểm tra giới hạn**. Ví dụ một header khai báo payload vài gigabyte có thể khiến `readNBytes(len)` tiêu tốn bộ nhớ rất lớn; hãy xác thực `len` trước khi đọc.
- `readNBytes(int)` yêu cầu `len >= 0`; truyền số âm ném `IllegalArgumentException`. Với overload nhận buffer, `off`, `len` ngoài giới hạn mảng ném `IndexOutOfBoundsException`.
- Nếu gặp `IOException` trong khi đọc, có thể một phần dữ liệu đã được tiêu thụ và một phần buffer đã được ghi. Không tái sử dụng mù quáng trạng thái cũ; đóng stream hoặc thực hiện chính sách khôi phục có định nghĩa rõ.
- Đừng nhầm số byte đọc với số ký tự Unicode. `InputStream` xử lý **byte**, còn việc chuyển sang `String` cần xác định encoding, chẳng hạn `UTF-8`. Một đoạn byte kết thúc giữa ký tự đa byte có thể không tạo thành văn bản hợp lệ, dù số byte đọc được là dương.

## 10. Câu hỏi ôn tập

**Câu 1:** Luồng chỉ có 3 byte nhưng gọi `readNBytes(5)`. Kết quả là gì?  
**Trả lời:** Mảng dài 3 byte; không tự đệm thêm 2 byte, cũng không tự ném `EOFException` chỉ vì thiếu byte.

**Câu 2:** Gọi `readNBytes(buffer, 0, 5)` khi stream đang ở EOF và `buffer` đủ lớn trả gì?  
**Trả lời:** `0`; nó **không trả `-1`**.

**Câu 3:** Nếu `read(buffer)` trả `2` khi `buffer.length == 5`, có chắc nguồn đã EOF?  
**Trả lời:** Không. Đó có thể chỉ là một lượt đọc ngắn; phải tiếp tục đọc theo contract nếu còn cần byte.

**Câu 4:** Nếu protocol yêu cầu đủ 16 byte, nên kiểm tra gì?  
**Trả lời:** Dùng `readNBytes(16)` rồi kiểm tra `result.length == 16`, hoặc dùng `DataInputStream.readFully(new byte[16])`; thiếu byte phải được báo là truncated/incomplete.

**Câu 5:** `readNBytes(0).length == 0` có đủ chứng minh EOF?  
**Trả lời:** Không. Gọi với `len = 0` luôn không đọc byte nào.

## 11. Ghi nhớ

- **EOF là điều kiện hết byte của luồng**, không phải lúc nào cũng là lỗi; lỗi xảy ra khi nghiệp vụ đòi **đủ một độ dài xác định**.
- Trong Java 11+, `InputStream.readNBytes(int)` trả **mảng dài bằng số byte thực nhận**, có thể **ngắn hơn yêu cầu** nếu gặp EOF.
- `InputStream.readNBytes(byte[], off, len)` trả **số byte thực đọc**; tại EOF là `0` với `len > 0`, và chỉ vùng `off ... off + count - 1` của buffer mới có dữ liệu đọc mới.
- `read(byte[], ...)` có thể trả ngắn **trước EOF**; chỉ `-1` xác nhận EOF khi đang yêu cầu số byte dương.
- Với yêu cầu **bắt buộc đủ byte**, dùng `DataInputStream.readFully` hoặc kiểm tra độ dài rồi ném `EOFException`. Với dữ liệu không biết tổng độ dài, lặp `read` đến `-1`.
- Luôn kiểm soát **giới hạn độ dài, tài nguyên, lỗi I/O** và byte encoding khi xử lý byte stream.

**Tài liệu chính thức (vẫn hiện hành):** [Java 11 — InputStream, read và readNBytes](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/io/InputStream.html); [Java 11 — DataInputStream.readFully](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/io/DataInputStream.html); [Java 26 — InputStream API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/io/InputStream.html).