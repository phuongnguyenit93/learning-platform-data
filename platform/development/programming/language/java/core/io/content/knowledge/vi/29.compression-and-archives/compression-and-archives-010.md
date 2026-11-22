# CRC32, Adler32 và giới hạn của checksum trong Java I/O

## 1. Checksum dùng để làm gì?

**Checksum** là một giá trị ngắn được tính từ dãy byte nhằm hỗ trợ phát hiện dữ liệu bị thay đổi trong lúc truyền, lưu trữ hoặc giải nén. Thay vì so sánh lại từng byte với bản gốc, bên nhận có thể tính checksum từ dữ liệu thực nhận rồi so với giá trị được lưu hoặc gửi trước đó.

Ví dụ:

~~~text
Người gửi:   "HELLO" --[tính checksum]--> số 32 bit X
               |                           |
               +----------- truyền --------+
                                           |
Người nhận:  "HELXO" --[tính checksum]--> số 32 bit Y
                                           |
                                 X != Y => phát hiện sai khác

Nếu X == Y: dữ liệu CÓ THỂ giống, nhưng KHÔNG được
             chứng minh chắc chắn giống dữ liệu gốc.
~~~

Trong Java Core I/O, `CRC32` và `Adler32` là hai checksum 32 bit thuộc gói `java.util.zip`. Chúng thường xuất hiện trong ngữ cảnh nén và đóng gói vì các định dạng như ZIP, GZIP và zlib dùng checksum để kiểm tra dữ liệu đã giải nén.

Ba ý cần nắm:

1. **Checksum hoạt động trên byte**, nên mã hóa ký tự, thứ tự byte và phạm vi byte đem tính phải được hai phía thống nhất.
2. **CRC32 và Adler32 phát hiện nhiều lỗi vô tình**, nhưng vì chỉ có 32 bit kết quả nên luôn tồn tại va chạm (*collision*): dữ liệu khác nhau nhưng checksum trùng nhau.
3. **Checksum không phải chữ ký số, HMAC hay cơ chế xác thực**. Đối thủ có thể sửa dữ liệu và tính lại checksum tương ứng, đặc biệt khi giá trị checksum nằm cùng một tệp không được bảo vệ.

## 2. So sánh CRC32 và Adler32

| Tiêu chí | CRC32 | Adler32 |
| --- | --- | --- |
| Lớp trong JDK | `java.util.zip.CRC32` | `java.util.zip.Adler32` |
| Độ dài giá trị | 32 bit | 32 bit |
| Cơ chế chính | Phép chia đa thức trên GF(2), triển khai phổ biến bằng bảng tra cứu hoặc phần cứng. | Hai tổng tích lũy modulo 65521, ghép thành số 32 bit. |
| Đặc tính | Được thiết kế để phát hiện nhiều kiểu lỗi bit, nhất là các mẫu lỗi theo cấu trúc truyền dữ liệu. | Công thức đơn giản, thường nhanh trên một số môi trường; tính phát hiện lỗi trên thông điệp ngắn có thể yếu hơn CRC32. |
| Liên hệ định dạng | ZIP entry và GZIP trailer dùng CRC32 kiểu IEEE. | zlib wrapper của luồng DEFLATE dùng Adler-32. |
| Java API | `update(...)`, `getValue()`, `reset()` | Cùng hợp đồng `Checksum`. |
| Bảo vệ chống sửa cố ý | Không | Không |

**Không có thuật toán nào “mạnh như SHA-256” chỉ vì cho ra số trông ngẫu nhiên.** Giá trị 32 bit không đủ làm định danh duy nhất hay kiểm tra tính toàn vẹn trước tác nhân có chủ đích; mục tiêu của các thuật toán này là **phát hiện sai hỏng thông thường** với chi phí thấp.

### 2.1. Checksum khác hash, CRC và chữ ký như thế nào?

Thuật ngữ *hash* đôi khi được dùng rộng cho mọi hàm ánh xạ dữ liệu sang giá trị ngắn. Nhưng khi thiết kế hệ thống, cần phân biệt:

- **Checksum không mật mã:** CRC32, Adler32; thích hợp đối chiếu dữ liệu sau truyền/giải nén.
- **Cryptographic hash:** SHA-256, SHA-512; chống tìm va chạm tốt hơn rất nhiều so với checksum 32 bit, nhưng tự nó **không chứng minh ai tạo dữ liệu** nếu attacker được sửa cả dữ liệu lẫn hash.
- **HMAC:** ví dụ HmacSHA256, dùng khóa bí mật chung để kiểm tra nội dung và nguồn phát biết khóa; cần quản lý khóa an toàn.
- **Digital signature:** dùng khóa riêng để ký và khóa công khai để xác minh; phục vụ xác thực nguồn gốc và phát hiện sửa đổi theo mô hình tin cậy phù hợp.

Nếu cần bảo vệ dữ liệu truyền qua mạng trước đối thủ, dùng các giao thức có xác thực và bảo vệ toàn vẹn như TLS, không chỉ gắn CRC32 vào cuối packet.

## 3. CRC32 hoạt động như thế nào?

CRC là viết tắt của **Cyclic Redundancy Check**. CRC coi chuỗi bit như một đa thức trên trường nhị phân `GF(2)` và thực hiện phép chia theo một đa thức sinh để lấy phần dư. Các phép cộng/trừ ở đây tương ứng phép XOR.

`java.util.zip.CRC32` cài CRC-32 được dùng phổ biến trong ZIP/GZIP (thường gọi CRC-32/ISO-HDLC, CRC-32/IEEE). Các tham số thông dụng của biến thể này gồm:

- Độ rộng: **32 bit**.
- Đa thức ở dạng chuẩn: `0x04C11DB7`; dạng phản chiếu dùng trong triển khai theo bit thấp trước: `0xEDB88320`.
- Giá trị khởi tạo nội bộ: `0xFFFFFFFF`.
- Input và output được phản chiếu theo biến thể CRC-32 thông dụng.
- Kết quả cuối được XOR với `0xFFFFFFFF`.

Không phải thuật toán nào có tên “CRC32” đều dùng cùng **tham số CRC**. Một biến thể khác như CRC32C (Castagnoli) có đa thức khác và thường cho checksum khác ngay cả khi byte đầu vào giống nhau. Khi đọc đặc tả giao thức, cần xác định **chính xác CRC variant**, không chỉ tên “CRC”.

### 3.1. Dữ liệu kiểm thử chuẩn

Với dãy byte ASCII:

~~~text
123456789
~~~

`CRC32` theo JDK cho ra:

~~~text
0xCBF43926
~~~

Đây là *test vector* rất phổ biến để phát hiện nhầm polynomial, initial value, reflection hoặc final XOR. Trong Java, `getValue()` trả `long` không âm chứa phần thấp 32 bit; dùng `%08X` nếu muốn hiển thị đúng tám chữ số hex có các số 0 đầu.

### 3.2. Khả năng phát hiện lỗi của CRC

CRC với đa thức được lựa chọn phù hợp có những tính chất phát hiện lỗi bit tốt hơn cách cộng byte đơn giản, nhất là trong các giao thức truyền/lưu trữ có lỗi dạng *burst*. Nhưng mức bảo đảm cụ thể còn phụ thuộc:

- Đa thức/biến thể CRC.
- Độ dài thông điệp tối đa.
- Phân bố lỗi; lỗi bit độc lập khác lỗi có cấu trúc.
- Số bit thay đổi và khoảng cách Hamming tối thiểu của bộ mã trên chiều dài thông điệp đang xét.

Không được mặc định “CRC32 luôn phát hiện mọi lỗi ba bit” hay “cứ đổi ít bit là chắc chắn phát hiện”, nếu chưa chứng minh thuộc tính đó cho đúng variant và chiều dài dữ liệu. CRC không được thiết kế để chống kẻ sửa dữ liệu có chủ đích.

## 4. Adler32 hoạt động như thế nào?

Adler-32 sử dụng **hai tổng modulo số nguyên tố 65521** trên các byte không dấu. Khởi tạo:

~~~text
A = 1
B = 0
MOD = 65521
~~~

Với mỗi byte có giá trị từ 0 đến 255:

~~~text
A = (A + byte) mod 65521
B = (B + A) mod 65521

Adler32 = (B << 16) | A
~~~

Trong mã Java minh họa, cần xử lý byte không dấu bằng `byteValue & 0xFF`. Hai tổng tích lũy bị ảnh hưởng bởi thứ tự byte; cùng tập byte đảo thứ tự có thể cho kết quả khác.

Ví dụ một byte ASCII `'A'` có giá trị 65:

~~~text
A = (1 + 65) mod 65521 = 66 = 0x0042
B = (0 + 66) mod 65521 = 66 = 0x0042
Adler32 = 0x00420042
~~~

Với chuỗi ASCII `123456789`:

~~~text
Adler32 = 0x091E01DE
~~~

Adler32 được chọn vì dễ tính nhanh, nhưng nó có phân bố kém hơn CRC32 trên nhiều thông điệp rất ngắn. Không kết luận nó luôn nhanh hơn trong mọi JDK/CPU hiện đại: hiệu năng phụ thuộc cách triển khai, SIMD/phần cứng, kích thước block và bộ nhớ.

### 4.1. Tại sao A bắt đầu bằng 1?

Nếu cả A và B bắt đầu bằng 0, một chuỗi chỉ gồm các byte 0 sẽ cho checksum 0 ở mọi độ dài và có nhiều tình huống suy biến không mong muốn. Khởi tạo A=1 giúp thay đổi đặc tính đó; đây là tham số của thuật toán Adler-32 chuẩn chứ không phải tùy chọn người gọi Java tự sửa.

## 5. API `Checksum` trong Java

Các lớp `CRC32` và `Adler32` triển khai interface `java.util.zip.Checksum`. Các phương thức thường dùng:

| API | Ý nghĩa |
| --- | --- |
| `update(int b)` | Cập nhật với **một byte**, lấy 8 bit thấp của tham số `int`. |
| `update(byte[] b)` | Cập nhật trên toàn bộ mảng byte. |
| `update(byte[] b, int off, int len)` | Cập nhật trên đoạn mảng từ offset, dài len byte. |
| `update(ByteBuffer buffer)` | Cập nhật với phần byte còn lại; thay đổi position của buffer theo hợp đồng API. |
| `getValue()` | Lấy checksum hiện tại kiểu `long`; với CRC32/Adler32, giá trị nằm trong dải 32 bit không dấu. |
| `reset()` | Đặt checksum về trạng thái khởi tạo để tính dữ liệu khác. |

Ví dụ nhanh:

~~~java
import java.nio.charset.StandardCharsets;
import java.util.zip.CRC32;

byte[] bytes = "abc".getBytes(StandardCharsets.US_ASCII);
CRC32 crc = new CRC32();
crc.update(bytes, 0, bytes.length);
long result = crc.getValue();
System.out.printf("CRC32=%08X%n", result);
~~~

Đây là **mảnh mã đặt trong một phương thức**. `getValue()` không reset trạng thái: có thể lấy giá trị tạm thời sau mỗi chunk. `update(...)` nhiều lần trên các đoạn liên tiếp tương đương tính trên toàn bộ chuỗi byte theo cùng thứ tự.

**Lưu ý quan trọng về `update(int)`:** `crc.update(256)` không nạp bốn byte của một số nguyên 256; theo hợp đồng, nó chỉ đưa byte thấp `0x00`. Muốn checksum của dữ liệu nhị phân chứa một số nguyên 32 bit, hãy quyết định byte order, chuyển thành đúng bốn byte, rồi cập nhật với mảng/ByteBuffer tương ứng.

## 6. Ví dụ Java 17+ hoàn chỉnh: CRC32, Adler32, chia chunk và phát hiện sửa đổi

Ví dụ dùng test vector `123456789`, cố ý đọc qua `ByteArrayInputStream` với buffer 4 byte để có ba chunk: 4 + 4 + 1. Sau đó đối chiếu giá trị khi tính một lần với giá trị khi tính dần, kiểm tra `reset()` và sửa một byte nhằm mô phỏng lỗi ngẫu nhiên.

Lưu file `ChecksumDemo.java`:

~~~java
import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.util.Locale;
import java.util.zip.Adler32;
import java.util.zip.CRC32;
import java.util.zip.Checksum;

public class ChecksumDemo {

    static long calculate(Checksum checksum, byte[] data, int chunkSize)
            throws IOException {
        checksum.reset();

        try (ByteArrayInputStream input = new ByteArrayInputStream(data)) {
            byte[] buffer = new byte[chunkSize];
            int n;
            while ((n = input.read(buffer)) != -1) {
                checksum.update(buffer, 0, n);
            }
        }
        return checksum.getValue();
    }

    static String hex32(long value) {
        return String.format(Locale.ROOT, "%08X", value);
    }

    public static void main(String[] args) throws IOException {
        byte[] original =
                "123456789".getBytes(StandardCharsets.US_ASCII);

        long crc = calculate(new CRC32(), original, 4);
        long adler = calculate(new Adler32(), original, 4);

        System.out.println("bytes=" + original.length);
        System.out.println("crc32=" + hex32(crc));
        System.out.println("adler32=" + hex32(adler));

        // Chunk khác nhau, nhưng thứ tự và nội dung byte giữ nguyên.
        long crcOneChunk =
                calculate(new CRC32(), original, original.length);
        long adlerOneByteAtATime =
                calculate(new Adler32(), original, 1);

        System.out.println("crcChunksEqual=" + (crc == crcOneChunk));
        System.out.println("adlerChunksEqual=" +
                (adler == adlerOneByteAtATime));

        byte[] changed = original.clone();
        changed[0] = (byte) 'X';

        long crcChanged = calculate(new CRC32(), changed, 4);
        long adlerChanged = calculate(new Adler32(), changed, 4);

        System.out.println("crcDetectsChange=" + (crc != crcChanged));
        System.out.println("adlerDetectsChange=" + (adler != adlerChanged));

        CRC32 reusable = new CRC32();
        reusable.update(changed, 0, changed.length);
        reusable.reset();
        reusable.update(original, 0, original.length);

        System.out.println("resetReusesInstance=" +
                (reusable.getValue() == crc));
    }
}
~~~

Lệnh biên dịch và chạy:

~~~bash
javac ChecksumDemo.java
java ChecksumDemo
~~~

**Stdout xác định cho dữ liệu trong chương trình:**

~~~text
bytes=9
crc32=CBF43926
adler32=091E01DE
crcChunksEqual=true
adlerChunksEqual=true
crcDetectsChange=true
adlerDetectsChange=true
resetReusesInstance=true
~~~

### 6.1. Giải thích code

1. `ByteArrayInputStream` trả dữ liệu từ mảng có chín byte. Buffer tạm 4 byte được đọc ba lượt; mỗi lần gọi `checksum.update(buffer, 0, n)` **chỉ sử dụng n byte thực nhận**.
2. `Checksum.reset()` trước khi xử lý bảo đảm không trộn dữ liệu của lượt tính trước vào lượt mới.
3. `crc32=CBF43926` và `adler32=091E01DE` khớp test vector chuẩn cho chuỗi ASCII `123456789`.
4. Cùng nội dung được đưa vào `update` theo các kích thước chunk khác nhau nhưng cùng thứ tự nên kết quả bằng nhau.
5. Đổi ký tự đầu tiên từ `'1'` sang `'X'` làm cả hai checksum trong **trường hợp cụ thể này** thay đổi. Điều đó minh họa phát hiện lỗi, **không phải chứng minh mọi thay đổi byte đều được phát hiện**.
6. `resetReusesInstance=true` xác nhận có thể dùng lại đối tượng `CRC32` sau `reset` mà không dính dữ liệu đã tính.

Trong ví dụ, hàm `calculate` nhận một đối tượng `Checksum` bất kỳ tương thích với interface này. Nhờ đó có thể dùng cùng logic streaming cho `CRC32` và `Adler32`, tránh viết hai vòng lặp khác nhau.

## 7. Tính checksum của một file lớn mà không nạp hết vào RAM

Đối với file thực tế, tránh `Files.readAllBytes(path)` khi tệp rất lớn vì nó cần bộ nhớ tương ứng toàn bộ nội dung. Tính theo luồng cho phép sử dụng một buffer cố định.

~~~java
import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.zip.Checksum;
import java.util.zip.CRC32;

public final class FileChecksumExample {
    public static long crc32(Path file) throws IOException {
        Checksum checksum = new CRC32();
        byte[] chunk = new byte[8192];

        try (InputStream input = Files.newInputStream(file)) {
            int n;
            while ((n = input.read(chunk)) != -1) {
                if (n > 0) {
                    checksum.update(chunk, 0, n);
                }
            }
        }

        return checksum.getValue();
    }
}
~~~

Đoạn này là **một lớp utility có thể biên dịch** sau khi lưu đúng tên `FileChecksumExample.java`; chưa có `main` nên không có lệnh `java FileChecksumExample` để chạy độc lập. Muốn dùng, gọi `FileChecksumExample.crc32(path)` trong chương trình phù hợp.

Quan trọng:

- Dùng `n` trả về thay vì luôn truyền `chunk.length`. Lượt đọc cuối có thể ít hơn 8192 byte; phần còn lại trong mảng là dữ liệu cũ.
- Bộ nhớ tạm là `O(chunkSize)`, không tăng theo kích thước file.
- Checksum được tính trên **những byte thực đọc được**. Nếu file bị thay đổi đồng thời khi đọc, kết quả có thể là dữ liệu trộn từ nhiều thời điểm; checksum không tạo snapshot nhất quán.
- Hàm tính lại checksum của cùng một tệp nhiều lần chỉ có giá trị khi dữ liệu được giữ ổn định hoặc quy trình chấp nhận điều kiện thay đổi.
- Nếu ứng dụng cần kiểm tra tệp được tải về, phải có giá trị checksum **kỳ vọng** đáng tin hoặc một nguồn xác thực khác. Việc vừa đọc tệp vừa tự tính checksum rồi lưu cùng chỗ không cho biết tệp đã đúng so với bản gốc.

## 8. Checksum và nén/đóng gói: ZIP, GZIP và zlib

Các định dạng nén thường thêm metadata để phát hiện dữ liệu hỏng sau quá trình giải nén. CRC32 và Adler32 **không phải thuật toán nén**: chúng không làm dữ liệu nhỏ hơn; chúng chỉ tính dấu kiểm ngắn.

### 8.1. ZIP: CRC32 cho từng entry

Trong định dạng ZIP, mỗi entry có metadata gồm CRC32 của **dữ liệu chưa nén**, kích thước đã nén và kích thước chưa nén. Java hỗ trợ ZIP qua `ZipOutputStream`, `ZipInputStream`, `ZipFile` và `ZipEntry`.

~~~text
archive.zip
   |
   +-- notes.txt
   |     CRC32 = checksum của bytes notes.txt sau giải nén
   |
   +-- image.bin
         CRC32 = checksum của bytes image.bin sau giải nén
~~~

Với `ZipOutputStream` dùng phương thức DEFLATED, JDK có thể tính CRC32 của dữ liệu entry trong lúc ghi. Với entry kiểu STORED (không nén), caller phải cung cấp metadata cần thiết như size/CRC trước khi ghi entry theo yêu cầu API.

`ZipInputStream` kiểm tra CRC/size của entry khi đã đọc hết nội dung entry và hoàn tất kiểm tra entry tương ứng. Nếu chỉ đọc một phần rồi bỏ dở, không được mặc định quá trình kiểm tra dữ liệu toàn entry đã diễn ra. `ZipFile` cung cấp truy cập ngẫu nhiên tới entry, nhưng nếu quy trình yêu cầu xác minh nghiêm ngặt, ứng dụng nên chủ động đối chiếu dữ liệu đã đọc với checksum kỳ vọng của entry theo hợp đồng API đang dùng.

### 8.2. Ví dụ tạo ZIP và tự đối chiếu CRC32

~~~java
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.util.zip.CRC32;
import java.util.zip.ZipEntry;
import java.util.zip.ZipOutputStream;

byte[] text = "hello".getBytes(StandardCharsets.UTF_8);
CRC32 expected = new CRC32();
expected.update(text);

ByteArrayOutputStream archive = new ByteArrayOutputStream();
try (ZipOutputStream zip = new ZipOutputStream(archive)) {
    ZipEntry entry = new ZipEntry("hello.txt");
    zip.putNextEntry(entry);
    zip.write(text);
    zip.closeEntry();
}

System.out.printf("uncompressed-crc=%08X%n", expected.getValue());
~~~

Đây là **mảnh minh họa đặt trong một phương thức**, có các import cần thiết. `expected` được tính từ byte gốc; `ZipOutputStream` tự tạo metadata CRC phù hợp cho entry DEFLATED. Không cần tự thêm checksum bytes vào nội dung `hello.txt`. Ví dụ không in kích thước archive vì nó có thể phụ thuộc metadata và lựa chọn của runtime.

### 8.3. GZIP dùng CRC32

Luồng GZIP có trailer bao gồm CRC32 của **dữ liệu chưa nén** và giá trị ISIZE (kích thước chưa nén modulo `2^32`), với cách lưu các trường nhiều byte theo định dạng GZIP. `GZIPOutputStream` tạo luồng GZIP; `GZIPInputStream` giải nén và kiểm tra checksum/trailer khi đọc đủ.

Không lấy CRC32 của **file .gz đã nén** rồi so với giá trị CRC lưu trong GZIP trailer. Trailer bảo vệ dữ liệu **trước khi nén**; hai dãy byte đó khác nhau.

### 8.4. zlib wrapper dùng Adler32

Một luồng theo định dạng zlib thường gồm header, dữ liệu DEFLATE và trường **ADLER32** của dữ liệu chưa nén. Trong Java, `DeflaterOutputStream`/`InflaterInputStream` có thể làm việc với dạng được `Deflater`/`Inflater` cấu hình; phân biệt:

- **Raw DEFLATE**: luồng nén lõi, không tự kèm trường checksum của wrapper.
- **zlib wrapper**: chứa metadata wrapper và Adler32.
- **GZIP wrapper**: chứa metadata GZIP và CRC32; không đổi chỗ với Adler32.
- **ZIP archive**: cấu trúc nhiều entry, mỗi entry có CRC32 và metadata riêng.

Lẫn lộn *wrapper format* thường tạo lỗi “incorrect header check” hoặc “incorrect data check” khi giải nén. Phải chọn đúng lớp/định dạng, không chỉ đoán theo tên “DEFLATE”.

## 9. Checksum có giới hạn gì?

### 9.1. Không thể bảo đảm dữ liệu khác nhau sẽ cho checksum khác

CRC32 và Adler32 có **2^32** giá trị đầu ra tối đa. Trong khi đó số dãy byte có thể có dài hơn vài byte lớn hơn rất nhiều, nên theo nguyên lý Dirichlet chắc chắn tồn tại hai đầu vào khác nhau cùng checksum.

~~~text
Dữ liệu A  -> CRC32 X
Dữ liệu B  -> CRC32 X   (collision)
A != B nhưng CRC32(A) == CRC32(B)
~~~

Đối với dữ liệu lỗi ngẫu nhiên được mô hình hóa gần đồng đều, xác suất trùng một checksum 32 bit cố định thường được mô tả xấp xỉ **1 / 2^32**. Nhưng đây **không phải một bảo đảm độc lập với dữ liệu, loại lỗi hoặc cơ chế tạo lỗi**. Cụ thể với CRC, các đặc tính phát hiện lỗi phụ thuộc cấu trúc đa thức và độ dài thông điệp.

Nếu tạo nhiều đối tượng rồi gán checksum làm ID duy nhất, nguy cơ có **ít nhất một cặp va chạm** tăng nhanh do hiện tượng *birthday paradox*. Với output 32 bit gần đồng đều, ở quy mô khoảng vài chục nghìn đối tượng nguy cơ đã không còn nhỏ; ước lượng gần 50% khi có khoảng 77 nghìn mẫu độc lập. CRC/Adler thực tế không bắt buộc tuân theo giả định phân bố đều trong mọi tập dữ liệu.

### 9.2. Không chống sửa đổi có chủ đích

Nếu attacker sửa một file ZIP và cập nhật metadata CRC32 tương ứng, phép kiểm tra CRC có thể vẫn qua. Không có bí mật nào trong công thức CRC32 hay Adler32: ai biết byte dữ liệu đều có thể tính lại checksum.

~~~text
Tệp gốc + CRC32(gốc)
          |
       attacker sửa payload
          |
Tệp đã sửa + CRC32(mới)
          |
       Kiểm tra CRC32 vẫn KHỚP
       nhưng tính toàn vẹn/an toàn KHÔNG được bảo đảm.
~~~

Do đó:

- Với mục tiêu phát hiện lỗi bit do truyền/lưu trữ, CRC32 hoặc Adler32 có thể phù hợp.
- Với chống sửa trái phép, dùng HMAC/digital signature hoặc một giao thức xác thực như TLS, tùy mô hình tin cậy.
- Với gói cài đặt hoặc bản phát hành, kiểm tra signature từ nguồn đáng tin quan trọng hơn việc chỉ đối chiếu checksum được đăng trên cùng kênh không đáng tin.

### 9.3. Không sửa lỗi và không chỉ ra byte hỏng

Checksum thông báo **có khả năng dữ liệu không trùng**, chứ không cho biết byte nào sai hoặc tự sửa dữ liệu. Các mã phát hiện/sửa lỗi như ECC/FEC có mục tiêu và cấu trúc khác.

Một số giao thức kết hợp checksum với cơ chế truyền lại dữ liệu; việc truyền lại là phần của giao thức, không phải khả năng của `CRC32`/`Adler32`.

### 9.4. Không đảm bảo thứ tự hay đúng phạm vi byte

Nếu bên gửi tính CRC của payload nhưng bên nhận tính cả header; hoặc một bên dùng UTF-8, bên kia dùng UTF-16LE; kết quả có thể khác dù nội dung hiển thị giống nhau. Phải thống nhất:

- Dãy byte gốc và charset.
- Bao gồm hay loại trừ header, padding, delimiters, metadata.
- Thứ tự byte và serialization đối với số nguyên.
- Thuật toán/variant và cách biểu diễn trường checksum trong định dạng.
- Thời điểm tính: trên dữ liệu nén hay dữ liệu chưa nén.

Trong ZIP/GZIP/zlib, nên dùng API đúng định dạng và hiểu **checksum của nội dung nào** thay vì tự tính theo một giả định không được tài liệu bảo đảm.

## 10. Khi nào chọn thuật toán nào?

| Tình huống | Lựa chọn hợp lý | Lý do |
| --- | --- | --- |
| Đọc/ghi entry ZIP theo chuẩn | CRC32 qua ZIP API | Metadata ZIP quy định CRC32 cho entry. |
| Đọc/ghi GZIP theo chuẩn | CRC32 qua GZIP API | Trailer GZIP quy định CRC32. |
| Làm việc với zlib wrapper | Adler32 theo định dạng | zlib wrapper sử dụng Adler32 cho dữ liệu chưa nén. |
| Giao thức nội bộ cần phát hiện lỗi ngẫu nhiên, không có adversary | Checksum theo **đặc tả giao thức**, có thể CRC32/CRC32C hoặc loại khác. | Chọn đồng bộ thuật toán và độ dài thông điệp. |
| Cần đối chiếu bản tải khi checksum đến từ cùng kênh đáng tin | SHA-256 hoặc checksum theo đặc tả; vẫn xét nguồn xác thực. | Mức độ rủi ro và cơ chế phân phối quyết định. |
| Cần xác nhận người gửi và nội dung không bị sửa | HMAC hoặc chữ ký số, TLS phù hợp | CRC32 và Adler32 không có khóa/chứng thực. |
| Dùng checksum làm ID duy nhất cho nhiều đối tượng | Không nên | Chỉ 32 bit, va chạm là không tránh khỏi. |
| Dữ liệu có thể bị sửa đồng thời khi đọc | Đảm bảo snapshot/locking/versioning trước | Checksum không giải quyết consistency khi đọc. |

Nếu giao thức yêu cầu **CRC32C**, dùng `java.util.zip.CRC32C` (có từ Java 9), không dùng `CRC32` và hy vọng kết quả tương đương. Trong Java 17, cả hai đều có lớp triển khai riêng.

## 11. Những lỗi lập trình phổ biến

### 11.1. Quên `reset()` khi dùng lại đối tượng

~~~java
CRC32 crc = new CRC32();
crc.update(firstBytes);
long first = crc.getValue();

crc.update(secondBytes); // Tính trên firstBytes + secondBytes.
long combined = crc.getValue();
~~~

Nếu cần CRC riêng cho secondBytes thì phải `crc.reset()` trước khi cập nhật chúng, hoặc tạo một instance mới. `getValue()` chỉ lấy giá trị hiện tại; không làm trạng thái quay về ban đầu.

### 11.2. Luôn cập nhật cả buffer thay vì số byte thực nhận

~~~java
int n = input.read(chunk);
checksum.update(chunk); // Sai nếu n < chunk.length.
~~~

Cách đúng là `checksum.update(chunk, 0, n)` sau khi kiểm tra `n > 0`. Đoạn minh họa trên không phải chương trình độc lập: `input`, `chunk` và `checksum` đã được tạo ở chỗ khác.

Nếu không kiểm tra n, phần mảng không được ghi trong lượt đọc cuối vẫn chứa byte của lượt trước, khiến checksum sai.

### 11.3. So sánh với kết quả âm của int

CRC32 là 32 bit không dấu; Java `int` là signed, trong khi `getValue()` trả `long` trong khoảng 0 tới `0xFFFFFFFFL`. Nếu metadata lưu trong một `int` có bit dấu bật, phải chuyển đúng cách:

~~~java
long unsigned = Integer.toUnsignedLong(storedInt);
boolean matches = (checksum.getValue() == unsigned);
~~~

Không so sánh trực tiếp signed int âm với long không âm mà quên chuyển dạng.

### 11.4. Nhầm CRC của file nén với CRC dữ liệu đã giải nén

Trong ZIP/GZIP, checksum metadata thường được định nghĩa cho **uncompressed bytes**. Nếu gọi `CRC32.update` trên toàn bộ byte của `archive.zip` hoặc `file.gz`, kết quả thường không phải CRC của một ZIP entry hay GZIP trailer.

### 11.5. Nhầm CRC32 với CRC32C

Hai biến thể này có polynomial khác; cùng payload cho checksum khác. Đọc trường checksum 32 bit mà không biết biến thể khiến kiểm tra luôn báo lỗi sai hoặc mã hóa giao thức không tương thích.

### 11.6. Dùng checksum làm bảo mật

Không dùng checksum làm “chữ ký” cho file tải từ nguồn không đáng tin. Cần nguồn tin cậy cho expected value và cơ chế authentication như HMAC hoặc chữ ký số.

### 11.7. Giả định checksum bằng nhau thì bytes chắc chắn bằng nhau

Kết quả bằng nhau **không phải chứng minh đồng nhất**. Với dữ liệu quan trọng, tùy yêu cầu có thể cần kiểm tra độ dài, hash mật mã, so sánh byte-by-byte hoặc signature.

### 11.8. Trộn ByteBuffer state với phạm vi checksum

Khi gọi `checksum.update(ByteBuffer)`, chỉ **các byte còn lại từ position tới limit** được dùng. Nếu buffer vừa được `put` để ghi dữ liệu, cần `flip()` trước khi tính checksum của phần đã ghi; nếu không có thể tính nhầm vùng còn trống. Và vì update có thể tiến vị trí buffer, nếu vẫn cần đọc nội dung đó, hãy dùng `duplicate()` hoặc quản lý position có chủ đích.

### 11.9. Chia dữ liệu thành chunk rồi reset giữa chừng

Nếu muốn checksum toàn file, chỉ `reset()` **một lần trước khi bắt đầu**. Reset ở mỗi chunk khiến kết quả cuối chỉ tương ứng chunk cuối cùng, không còn phản ánh toàn file.

### 11.10. Giải nén ZIP mà không kiểm soát lượng dữ liệu

CRC không ngăn **ZIP bomb** hoặc nội dung có kích thước giải nén cực lớn. Khi nhận archive từ nguồn không đáng tin, cần giới hạn số entry, kích thước tổng sau giải nén, tỉ lệ nén, độ sâu/thời gian xử lý, và kiểm soát đường dẫn entry để tránh Zip Slip. Checksum hợp lệ không có nghĩa file an toàn.

## 12. Bài thực hành và câu hỏi tự kiểm tra

1. **CRC32/Adler32 có phải hai thuật toán nén không?** Không. Chúng là checksum của dãy byte và không làm giảm dung lượng dữ liệu.
2. **Khi tính checksum cho “123456789” dưới dạng ASCII, CRC32 bằng gì?** `CBF43926`.
3. **Adler32 cho test vector đó bằng gì?** `091E01DE`.
4. **Tính CRC theo chunk 4, 4, 1 byte có khác tính một lần 9 byte không?** Không, nếu thứ tự và byte giống nhau, chỉ reset ở đầu.
5. **`getValue()` tự reset checksum không?** Không. Phải gọi `reset()` hoặc tạo instance mới.
6. **`update(0x12345678)` nạp bao nhiêu byte?** Một byte thấp `0x78`, không phải bốn byte.
7. **GZIP trailer dùng checksum gì?** CRC32 của dữ liệu chưa nén.
8. **zlib wrapper dùng checksum gì?** Adler32 của dữ liệu chưa nén.
9. **CRC32 của một ZIP entry được tính trên byte đã nén hay chưa nén?** Dữ liệu **chưa nén** của entry.
10. **Hai tệp có cùng CRC32 có bắt buộc giống nhau không?** Không, luôn có thể có collision.
11. **Một kẻ sửa file rồi tính lại checksum có thể vượt qua kiểm tra checksum không?** Có; vì checksum không có khóa hoặc cơ chế xác thực.
12. **Nếu cần kiểm chứng nguồn phát và chống sửa đổi, nên cân nhắc gì?** HMAC, chữ ký số hoặc giao thức có xác thực như TLS, cùng quy trình quản lý khóa tin cậy.
13. **Vì sao `Files.readAllBytes` không phải cách mặc định cho file rất lớn?** Nó cần bộ nhớ tương ứng toàn nội dung; streaming qua buffer cố định tiết kiệm RAM hơn.
14. **Tại sao đọc file liên tục đang bị writer khác chỉnh sửa có thể cho checksum không đáng tin?** Những byte đọc được có thể thuộc các phiên bản khác nhau; checksum không tạo snapshot.
15. **Có nên dùng CRC32 cho mã nhận diện duy nhất của hàng triệu tệp?** Không, số giá trị 32 bit quá ít, nguy cơ trùng lớn.
16. **CRC32 và CRC32C có hoán đổi được không?** Không, đó là hai biến thể khác nhau.
17. **Đọc một phần ZIP entry rồi dừng có chứng minh checksum entry đã được kiểm tra đầy đủ?** Không. Phải đọc hết và kiểm tra theo hợp đồng của thư viện/định dạng.
18. **Checksum có giúp chống file ZIP chứa payload nguy hiểm không?** Không. Cần validate nội dung, giới hạn tài nguyên và bảo vệ path extraction.

## 13. Tài liệu Java 17 tham khảo

- [Checksum](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/zip/Checksum.html): `update`, `getValue`, `reset`.
- [CRC32](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/zip/CRC32.html) và [CRC32C](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/zip/CRC32C.html): phân biệt hai biến thể CRC.
- [Adler32](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/zip/Adler32.html): checksum Adler-32.
- [ZipInputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/zip/ZipInputStream.html), [ZipOutputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/zip/ZipOutputStream.html), [GZIPInputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/zip/GZIPInputStream.html): thao tác định dạng nén tương ứng.

**Ghi nhớ:** `CRC32` và `Adler32` là checksum 32 bit để phát hiện nhiều lỗi dữ liệu không chủ ý, không phải cơ chế bảo mật. Chúng cùng triển khai `Checksum` nên có thể tính incrementally trên stream; ZIP/GZIP thường dùng CRC32, còn zlib wrapper dùng Adler32. Luôn đối chiếu **đúng dãy byte, đúng variant, đúng expected value**, và dùng HMAC/chữ ký số khi cần chống sửa đổi có chủ đích.
