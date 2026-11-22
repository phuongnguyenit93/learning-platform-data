# Một lần `read` không bảo đảm lấp đầy buffer trong Java

Trong **luồng byte** (Java I/O), kích thước mảng đệm là *sức chứa tối đa của một lần đọc*, không phải số byte chắc chắn nhận được. Khi gọi `InputStream.read(byte[])` hoặc `InputStream.read(byte[], off, len)`, hãy luôn dùng **giá trị trả về** để biết có bao nhiêu byte hợp lệ. Hiểu sai điểm này dễ dẫn đến mất dữ liệu, chèn byte cũ hoặc byte `0` vào kết quả, giải mã văn bản hỏng và lỗi khi đọc giao thức mạng.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích vì sao `read` trả về ít byte hơn số byte yêu cầu dù luồng chưa kết thúc.
- Phân biệt `n > 0`, `n == -1` và trường hợp `len == 0` theo hợp đồng của `InputStream`.
- Xử lý đúng `buffer[0..n)` hoặc `buffer[off..off+n)`; không xem phần còn lại của buffer là dữ liệu mới.
- Viết vòng lặp đọc đến EOF, đọc đúng N byte, hoặc đọc theo khung thông điệp.
- Chọn giữa `read`, `readNBytes`, `DataInputStream.readFully` và `readAllBytes` theo nhu cầu.

## 2. Hợp đồng của `InputStream.read`

Ba biến thể thường gặp:

~~~java
int one = input.read();                     // Một byte 0..255, hoặc -1 nếu EOF
int count = input.read(buffer);             // Tối đa buffer.length byte
int count2 = input.read(buffer, off, len);  // Tối đa len byte từ vị trí off
~~~

Với `read(byte[], off, len)` của một triển khai `InputStream` tuân thủ hợp đồng Java:

| Kết quả | Ý nghĩa | Xử lý |
| --- | --- | --- |
| `1..len` nếu `len > 0` | Số byte đã đọc; **có thể nhỏ hơn** `len` | Chỉ dùng `buffer[off]` đến `buffer[off + count - 1]` |
| `-1` | Đã đến **end of stream (EOF)** trước khi đọc byte nào | Kết thúc vòng lặp hoặc báo thiếu dữ liệu theo giao thức |
| `0` nếu `len == 0` | Yêu cầu đọc 0 byte | Không có dữ liệu mới |
| Ngoại lệ `IOException` | Lỗi trong quá trình I/O | Xử lý/đẩy ngoại lệ; không coi là EOF |

Khi `len > 0`, hợp đồng của `InputStream.read(byte[], off, len)` quy định hoặc đọc được ít nhất một byte, hoặc trả về `-1` khi EOF; cách diễn đạt này **không áp dụng nguyên xi cho mọi API đọc dữ liệu**. Chẳng hạn, `ReadableByteChannel.read(ByteBuffer)` của kênh ở chế độ non-blocking có thể trả về `0` dù vẫn còn dữ liệu sẽ đến sau.

Một lệnh gọi `read(buffer)` có thể chặn (block) để đợi **một phần dữ liệu**, nhưng điều đó **không có nghĩa** nó sẽ chờ đến khi đầy `buffer`. Tùy nguồn và triển khai, lệnh gọi có thể trả về ngay khi đọc được một số byte, kể cả khi tổng dữ liệu của luồng còn rất nhiều.

**Quan trọng:** buffer dài 4096 byte, `read` trả về `37` thì chỉ **37 byte** mới đọc là hợp lệ. 4059 vị trí còn lại không thuộc lần đọc ấy, dù chúng đang chứa giá trị `0` hoặc byte từ vòng trước.

## 3. Vì sao đọc thiếu buffer là bình thường?

Giả sử chương trình có `byte[] buffer = new byte[1024]` nhưng nguồn chỉ cung cấp 3 byte tại thời điểm hoàn thành thao tác đọc. Hàm có quyền trả về `3`; những lần gọi tiếp theo có thể tiếp tục lấy byte còn lại.

Một số tình huống:

- **Socket TCP:** byte có thể đến qua nhiều đợt; TCP truyền một *dòng byte*, không giữ ranh giới các lần `write` của bên gửi. Một lần `read` không tương ứng chắc chắn với một lần gửi hay một thông điệp.
- **Luồng qua pipe hoặc filter:** phần dữ liệu hiện có hoặc cách lớp bọc triển khai `read` có thể khiến lần đọc chỉ trả về một đoạn.
- **File và buffered stream:** kết quả có thể bằng toàn bộ kích thước yêu cầu trong nhiều lần chạy, nhưng đó là hành vi quan sát được, **không phải điều kiện nên dựa vào**.
- **Điểm cuối thực sự:** nếu dữ liệu còn 7 byte mà buffer dài 100 byte, lần đọc có thể trả về 7; lần tiếp theo trả `-1`.

Cũng vì vậy, không thể suy ra “`count < buffer.length` nghĩa là EOF”. **Chỉ `-1`** báo EOF cho phương thức đọc mảng của `InputStream` với độ dài dương; còn trong trường hợp giao thức cố định N byte, EOF đến sớm là lỗi thiếu dữ liệu.

## 4. Ví dụ chạy được: một nguồn luôn trả tối đa 2 byte mỗi lần

`ByteArrayInputStream` tự nó thường đọc đủ phần dữ liệu đang có. Để thấy **short read** một cách lặp lại và không phụ thuộc thời điểm mạng, ví dụ sau đặt một `FilterInputStream` chỉ cho phép tối đa 2 byte ở mỗi lần đọc mảng.

Tạo file **`PartialReadDemo.java`**:

~~~java
import java.io.ByteArrayInputStream;
import java.io.FilterInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.util.Objects;

public class PartialReadDemo {
    static final class TwoAtATimeInputStream extends FilterInputStream {
        TwoAtATimeInputStream(InputStream source) {
            super(source);
        }

        @Override
        public int read(byte[] b, int off, int len) throws IOException {
            Objects.checkFromIndexSize(off, len, b.length);
            return super.read(b, off, Math.min(len, 2));
        }
    }

    public static void main(String[] args) throws IOException {
        byte[] source = "ABCDEFG".getBytes(StandardCharsets.US_ASCII);

        try (InputStream input =
                     new TwoAtATimeInputStream(new ByteArrayInputStream(source))) {
            byte[] buffer = new byte[5];
            int count;

            while ((count = input.read(buffer)) != -1) {
                String chunk = new String(
                        buffer, 0, count, StandardCharsets.US_ASCII);
                System.out.printf("count=%d; data=%s%n", count, chunk);
            }
        }
    }
}
~~~

Biên dịch và chạy bằng Java 17+:

~~~bash
javac PartialReadDemo.java
java PartialReadDemo
~~~

Kết quả chính xác:

~~~text
count=2; data=AB
count=2; data=CD
count=2; data=EF
count=1; data=G
~~~

Mảng có **5 ô**, nhưng các lần đọc lần lượt nhận `2, 2, 2, 1` byte. Luồng chỉ thực sự kết thúc khi vòng lặp gọi `read` thêm một lần và nhận `-1`. Đoạn mã dùng `new String(buffer, 0, count, US_ASCII)` vì nội dung kiểm thử là ASCII và chỉ giải mã những byte thực sự vừa nhận.

Trong stream bọc, `Math.min(len, 2)` chỉ thay đổi **số byte tối đa được yêu cầu**, còn `Objects.checkFromIndexSize` vẫn kiểm tra ranh giới của yêu cầu gốc. Đây là mô hình minh họa có chủ đích, không phản ánh số byte tối đa cố định của socket/file trong thực tế.

## 5. Lỗi phổ biến: bỏ qua số byte `read` đã trả về

**Sai:**

~~~java
byte[] buffer = new byte[1024];
int count = input.read(buffer);
if (count != -1) {
    output.write(buffer); // SAI: ghi cả 1024 byte
}
~~~

Nếu chỉ nhận 10 byte, `output.write(buffer)` vẫn ghi đủ 1024 byte. Đoạn dư có thể là byte `0` hoặc giá trị cũ từ lần trước. Đặc biệt nguy hiểm khi dùng lại cùng một buffer qua nhiều vòng.

**Đúng:**

~~~java
byte[] buffer = new byte[1024];
int count = input.read(buffer);
if (count != -1) {
    output.write(buffer, 0, count); // Chỉ ghi byte mới đọc
}
~~~

Các ví dụ trên là **mảnh mã** dùng hai biến `input` (`InputStream`) và `output` (`OutputStream`) đã được khai báo; chúng không phải chương trình độc lập. Khi dùng phương thức `read(buffer, off, len)`, phải xử lý đúng đoạn `buffer[off..off+count)`, không mặc định dữ liệu bắt đầu tại chỉ số 0.

Lỗi liên quan cũng thường xuất hiện khi viết:

~~~java
int count = input.read(buffer);
if (count < buffer.length) {
    // SAI: short read không chứng minh đã đến EOF
}
~~~

Hay:

~~~java
String text = new String(buffer, StandardCharsets.UTF_8);
// SAI: có thể giải mã byte chưa được ghi hoặc byte cũ
~~~

Dù có truyền `count`, không nên tự động chuyển **từng chunk bất kỳ** thành chuỗi UTF-8: một ký tự nhiều byte có thể bị tách qua hai lần `read`. Với dữ liệu văn bản, dùng `InputStreamReader`/`BufferedReader` cùng định nghĩa ranh giới bản ghi phù hợp, hoặc ghép đủ byte rồi giải mã. Một “chunk I/O” không nhất thiết là một ký tự, dòng hay thông điệp.

## 6. Mẫu chuẩn: đọc đến EOF khi chưa biết tổng độ dài

Khi định dạng quy định EOF chính là điểm kết thúc nội dung (ví dụ đọc toàn bộ file), lặp cho đến `-1` và chỉ xử lý `count` byte. Đoạn sau sao chép luồng theo từng khối, không cần chứa toàn bộ dữ liệu trong RAM:

~~~java
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;

public final class StreamCopy {
    private StreamCopy() {}

    public static long copy(InputStream input, OutputStream output)
            throws IOException {
        byte[] buffer = new byte[8192];
        long total = 0;
        int count;

        while ((count = input.read(buffer)) != -1) {
            output.write(buffer, 0, count);
            total += count;
        }
        return total;
    }
}
~~~

Đây là lớp có thể biên dịch nhưng **không có `main`**; gọi `StreamCopy.copy(input, output)` từ nơi sở hữu hai luồng. Người gọi quyết định thời điểm đóng tài nguyên, thường bằng `try-with-resources`. Phương thức `InputStream.transferTo(OutputStream)` (Java 9+) cung cấp cách sao chép đến EOF tương tự khi không cần tự xử lý từng chunk.

**Đừng dùng vòng lặp chờ “đủ một buffer”** nếu mục tiêu là đọc đến EOF. Kích thước 8192 chỉ là lựa chọn hiệu năng; không quyết định độ dài nội dung hoặc ý nghĩa thông điệp.

Nếu cần chứa kết quả trong bộ nhớ để xử lý, có thể ghi các đoạn vào `ByteArrayOutputStream` rồi gọi `toByteArray()`. Cách này phù hợp khi dữ liệu có kích thước được kiểm soát; với nội dung lớn hoặc không tin cậy, ưu tiên xử lý streaming và đặt giới hạn.

## 7. Mẫu chuẩn: cần **đúng N byte**, kể cả sau nhiều lần `read`

Một giao thức có thể quy định phần đầu hoặc payload dài đúng N byte. Khi ấy, một `read(buffer)` là không đủ. Lặp đến khi tổng byte tích lũy bằng N hoặc báo lỗi nếu EOF đến trước.

~~~java
import java.io.EOFException;
import java.io.IOException;
import java.io.InputStream;

public final class FixedLengthReader {
    private FixedLengthReader() {}

    public static byte[] readExactly(InputStream input, int size)
            throws IOException {
        if (size < 0) {
            throw new IllegalArgumentException("size must be >= 0");
        }

        byte[] result = new byte[size];
        int filled = 0;

        while (filled < size) {
            int count = input.read(result, filled, size - filled);
            if (count == -1) {
                throw new EOFException(
                        "Expected " + size + " bytes but got " + filled);
            }
            filled += count;
        }
        return result;
    }
}
~~~

Đây là lớp tiện ích có thể biên dịch, không có `main`. Trong mỗi lần lặp, vùng còn thiếu bắt đầu tại `filled` và dài `size - filled`. Với `InputStream` tuân thủ hợp đồng, khi độ dài yêu cầu dương, `count` là số dương hoặc `-1` nên `filled` tăng dần. Trường hợp `size == 0` sẽ trả về mảng rỗng mà không đọc.

**Giới hạn quan trọng:** nếu `size` do phía bên ngoài cung cấp, phải kiểm tra giới hạn kích thước trước khi cấp phát; `new byte[size]` có thể tốn nhiều RAM. Nếu ứng dụng có timeout/huỷ thao tác, hãy cấu hình phù hợp với nguồn dữ liệu (ví dụ socket timeout), vì một lần đọc có thể chặn trong lúc chờ dữ liệu.

### API có sẵn cho nhu cầu đọc đủ byte

| API | Dùng khi nào | Khi không đủ byte |
| --- | --- | --- |
| `InputStream.read(byte[], off, len)` | Chủ động xử lý từng chunk, streaming | Có thể trả về ít byte hơn `len` trong một lần |
| `InputStream.readNBytes(int len)` (Java 9+) | Muốn tối đa `len` byte dưới dạng mảng mới | Trả mảng ngắn hơn nếu EOF trước `len`; cần tự kiểm tra `length` |
| `InputStream.readNBytes(byte[], off, len)` (Java 9+) | Muốn tích lũy vào buffer có sẵn | Trả số byte thực đọc, có thể nhỏ hơn `len` khi EOF |
| `DataInputStream.readFully(byte[])` hoặc `readFully(byte[],off,len)` | **Bắt buộc** đủ N byte, nếu thiếu phải lỗi | Ném `EOFException` nếu EOF trước khi đủ |
| `InputStream.readAllBytes()` (Java 9+) | Đọc hết đến EOF và dữ liệu đủ nhỏ | Không có “N cần đủ”; có thể tốn lượng RAM lớn |
| `InputStream.transferTo(output)` (Java 9+) | Chuyển dữ liệu đến EOF sang output | Trả số byte chuyển; không tự biết ranh giới bản tin |

`readNBytes`/`readFully` có thể thực hiện **nhiều lần đọc nội bộ**, và vẫn có thể chặn hoặc ném `IOException`. Các phương thức này **không biến TCP thành giao thức có ranh giới thông điệp**; chúng chỉ đáp ứng một số chiến lược lấy byte.

### Ví dụ độc lập: `readNBytes` khác `readFully`

Tạo **`ExactLengthDemo.java`**:

~~~java
import java.io.ByteArrayInputStream;
import java.io.DataInputStream;
import java.io.EOFException;
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;

public class ExactLengthDemo {
    public static void main(String[] args) throws IOException {
        byte[] payload = "abc".getBytes(StandardCharsets.US_ASCII);

        try (InputStream input = new ByteArrayInputStream(payload)) {
            byte[] result = input.readNBytes(5);
            System.out.printf("readNBytes=%d; data=%s%n",
                    result.length,
                    new String(result, StandardCharsets.US_ASCII));
        }

        try (DataInputStream input =
                     new DataInputStream(new ByteArrayInputStream(payload))) {
            input.readFully(new byte[5]);
            System.out.println("readFully=ok");
        } catch (EOFException exception) {
            System.out.println("readFully=EOFException");
        }
    }
}
~~~

Chạy:

~~~bash
javac ExactLengthDemo.java
java ExactLengthDemo
~~~

Kết quả:

~~~text
readNBytes=3; data=abc
readFully=EOFException
~~~

Nguồn chỉ có ba byte `abc`. `readNBytes(5)` trả về ba byte thực có trước EOF; `readFully(new byte[5])` cần đúng năm byte, nên báo thiếu. Với `readFully`, nếu EOF xảy ra giữa chừng thì buffer đích có thể đã được ghi một phần; không sử dụng như payload hoàn chỉnh sau khi bắt ngoại lệ.

## 8. Phân biệt **buffer**, **EOF** và **ranh giới bản tin**

Hãy đặt ba câu hỏi khác nhau:

1. **Buffer chứa được bao nhiêu byte?** Đây là giới hạn lưu trữ cho một thao tác (`buffer.length` hoặc `len`).
2. **Lần `read` vừa trả về bao nhiêu byte?** Đây là số byte hợp lệ trong lần đọc (`count`).
3. **Ứng dụng biết một thông điệp kết thúc lúc nào?** Câu trả lời phải đến từ định dạng/giao thức: số byte cố định, trường độ dài, ký tự phân tách, hoặc EOF nếu quy ước cho phép.

Ví dụ: bên gửi TCP thực hiện hai lần ghi `"HELLO"` và `"WORLD"`. Bên nhận **không có bảo đảm** sẽ nhận đúng hai lần đọc, mỗi lần năm byte. Nó có thể nhận `"HE"`, `"LLOW"`, `"ORLD"`; hoặc `"HELLOWORLD"` trong một lần đọc. Vì vậy ứng dụng cần framing, ví dụ tiền tố độ dài và phần payload, chứ không dùng “một lần đọc = một message”.

Với thông điệp có **header 4 byte chỉ độ dài payload**:

- Đọc **đủ 4 byte header** trước, dùng đúng thứ tự byte (endianness) mà giao thức quy định.
- Giải mã độ dài, kiểm tra không âm, không vượt mức tối đa cho phép.
- Đọc **đúng số byte payload** đã khai báo; EOF đến sớm là thông điệp bị cắt.
- Nếu còn thông điệp tiếp theo trên cùng connection, tiếp tục đọc header; không giả định phần buffer còn trống hoặc một lần `read` kế tiếp bắt đầu đúng message mới.

Nếu định dạng dùng dấu xuống dòng, có thể sử dụng `BufferedReader.readLine()` khi dữ liệu thực sự là văn bản với charset xác định và lưu ý giới hạn kích thước dòng. Nếu là byte nhị phân, không tùy tiện diễn giải byte thành ký tự để tìm delimiter.

## 9. `available()` không giải quyết vấn đề

Cách làm sau **không đáng tin cậy** để xác định kích thước dữ liệu:

~~~java
int expected = input.available();
byte[] buffer = new byte[expected];
input.read(buffer);
~~~

`InputStream.available()` chỉ đưa ra **ước tính** số byte có thể đọc (hoặc bỏ qua) mà không bị chặn tại thời điểm gọi; nó **không phải tổng độ dài nội dung**, không dự báo các byte mạng sẽ đến sau, cũng không bảo đảm một lệnh `read` sẽ lấp đầy mảng. Với nhiều stream, giá trị có thể là `0` ngay cả khi EOF chưa đến. Không dựa vào `available() == 0` để kết luận hết dữ liệu.

## 10. Lưu ý khi dùng NIO channel hoặc văn bản

**NIO channels:** `ReadableByteChannel.read(ByteBuffer)` cũng trả số byte thực đọc hoặc `-1` tại EOF. Với channel ở chế độ non-blocking, `0` là kết quả bình thường; ứng dụng phải đợi sự kiện sẵn sàng (ví dụ `Selector`) hay quản lý tiến độ phù hợp. Không dùng vòng lặp bận chạy liên tục khi nhận `0`. Chú ý `ByteBuffer.position()`, `limit()`, `remaining()` và `flip()` trước khi chuyển sang đọc dữ liệu trong buffer.

**Văn bản UTF-8:** một ký tự có thể cần nhiều byte. Các mảng byte được chia tùy ý theo `read` không bảo toàn ranh giới ký tự. Với dữ liệu text hãy ghép đủ byte cho một đơn vị hoàn chỉnh rồi giải mã, hoặc sử dụng `InputStreamReader` để bộ giải mã duy trì trạng thái qua nhiều lần đọc. `Reader.read(char[])` cũng có thể trả về ít ký tự hơn độ dài mảng; việc dùng số lượng trả về vẫn cần thiết.

**Tài nguyên và lỗi:** đóng luồng khi sở hữu nó (thường dùng `try-with-resources`); không nuốt `IOException` rồi coi như EOF; tránh cấp phát theo độ dài do nguồn không tin cậy cung cấp; đặt giới hạn và timeout hợp lý cho luồng có thể chờ vô hạn.

## 11. Checklist khi review mã đọc byte

- [ ] Có lưu và sử dụng **`count`** từ mỗi lệnh `read`?
- [ ] Với `count > 0`, chỉ xử lý đúng đoạn `[off, off + count)`?
- [ ] Chỉ dừng khi nhận `-1` (nếu đọc đến EOF), hoặc khi đã đạt đúng số byte theo framing?
- [ ] Có tránh suy luận `count < len` nghĩa là EOF hay kết thúc bản tin?
- [ ] Nếu cần **đúng N byte**, đã lặp để tích lũy đủ hoặc dùng `readFully`, đồng thời xử lý EOF sớm?
- [ ] Có tránh dùng `available()` làm tổng kích thước, và tránh giải mã từng khúc UTF-8 tùy ý?
- [ ] Với socket/giao thức, có giới hạn kích thước payload và xác định rõ khung thông điệp?
- [ ] Với NIO non-blocking, có xử lý `read == 0` bằng cơ chế chờ phù hợp?

### Câu hỏi tự kiểm tra

**1.** Buffer dài 100, `read(buffer)` trả `12`. Bao nhiêu byte vừa đọc hợp lệ?  
**Đáp án:** 12 byte đầu. Không dùng 88 byte còn lại như dữ liệu mới.

**2.** `read(buffer)` trả `8` khi buffer dài 64. Có khẳng định EOF được không?  
**Đáp án:** Không. Cần đọc tiếp; với `InputStream`, `-1` mới báo EOF.

**3.** Header giao thức yêu cầu chính xác 8 byte; `read(buffer)` trả `3`. Phải làm gì?  
**Đáp án:** Tiếp tục đọc 5 byte còn thiếu vào đúng offset; nếu EOF đến trước khi đủ 8 byte thì báo lỗi, không giải mã header chưa hoàn chỉnh.

**4.** Khi nào dùng `readAllBytes`?  
**Đáp án:** Khi muốn đọc hết stream và kích thước được kiểm soát, phù hợp bộ nhớ. Với nguồn lớn/không biết trước, dùng streaming.

**Ghi nhớ:** `read` trả về **số byte thực nhận**, buffer thể hiện **sức chứa**, còn ranh giới dữ liệu nghiệp vụ do **giao thức** xác định. Ba đại lượng này độc lập với nhau.