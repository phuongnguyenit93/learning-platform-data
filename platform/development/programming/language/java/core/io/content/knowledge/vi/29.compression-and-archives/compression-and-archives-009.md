# Deflater, Inflater và phạm vi điều khiển mức nén trong Java

## 1. Vấn đề: nén và giải nén là hai chiều của một luồng dữ liệu

Trong `java.util.zip`, cặp lớp `Deflater` và `Inflater` cung cấp giao diện ở mức thấp cho thuật toán **DEFLATE**. DEFLATE nén byte bằng kỹ thuật kết hợp LZ77 và mã Huffman; mục tiêu là giảm số byte lưu trữ hoặc truyền đi khi dữ liệu có tính lặp.

~~~text
Dữ liệu gốc: byte[] hoặc ByteBuffer
                  |
                  v
            Deflater (nén)
        level + strategy + trạng thái
                  |
                  v
         Luồng byte đã nén
                  |
       lưu file / truyền mạng
                  |
                  v
            Inflater (giải nén)
                  |
                  v
             Byte gốc
~~~

Hai lớp xử lý **byte**, không hiểu trực tiếp ký tự, dòng văn bản hay object Java. Trước khi nén chuỗi, hãy mã hóa bằng charset cụ thể, ví dụ `StandardCharsets.UTF_8`. Khi giải nén xong, chỉ giải mã byte thành text nếu biết đúng charset.

**Câu hỏi chính của bài:** Java cho phép kiểm soát *mức nén* tới đâu, mức đó ảnh hưởng tới điều gì, và điều gì nằm ngoài khả năng bảo đảm của `Deflater`/`Inflater`?

Câu trả lời ngắn: **mức nén là một tham số của bên nén để cân bằng tốc độ CPU và khả năng giảm kích thước**. Nó không quyết định kích thước đầu ra tuyệt đối, không bảo đảm một tỷ lệ nén, không điều khiển giải nén theo các mức tương ứng và không tự biến luồng byte thành một tệp ZIP hay GZIP.

## 2. Phân biệt thuật toán DEFLATE với zlib, gzip và ZIP

Đây là bốn tên gần nhau nhưng **không đồng nghĩa**:

| Thuật ngữ | Bản chất | Điều cần nhớ |
| --- | --- | --- |
| DEFLATE | Thuật toán/định dạng mã hóa dữ liệu nén | Có thể sử dụng dưới dạng raw DEFLATE |
| zlib | Cách đóng gói DEFLATE với phần header/trailer và kiểm tra dữ liệu | `new Deflater(level)` tạo luồng có zlib wrapper; `new Inflater()` giải nén định dạng tương ứng |
| gzip | Định dạng có header/trailer gzip, hỗ trợ metadata thích hợp | Java cung cấp `GZIPOutputStream` và `GZIPInputStream` |
| ZIP | Định dạng archive gồm entry, metadata và bảng thư mục archive | Java cung cấp `ZipOutputStream`, `ZipInputStream`, `ZipFile` và ZIP filesystem |

Ví dụ:

~~~text
raw DEFLATE: [deflate payload]

zlib:        [zlib header][deflate payload][Adler-32]

gzip:        [gzip header][deflate payload][gzip trailer]

ZIP:         [local entry headers + data][central directory + metadata]
~~~

Sơ đồ giản lược, không mô tả đầy đủ mọi field hay biến thể định dạng.

**Không truyền nguyên một file `.gz` hoặc `.zip` vào `new Inflater()` và kỳ vọng giải nén thành công.** `Inflater()` mặc định mong luồng định dạng zlib, không tự đọc header gzip hoặc cấu trúc archive ZIP. Với gzip dùng `GZIPInputStream`; với archive ZIP dùng API ZIP phù hợp.

Nếu cần **raw DEFLATE** không có zlib header/checksum wrapper, có overload `new Deflater(level, true)` và `new Inflater(true)`. Hai đầu phải thống nhất định dạng. `nowrap=true` không có nghĩa tạo được gzip/ZIP hoàn chỉnh; các cấu trúc chứa vẫn phải được xử lý ở tầng thích hợp.

## 3. Các mức nén có thể lựa chọn

`Deflater` cho phép chỉ định mức nén khi khởi tạo hoặc thay đổi mức cho phần dữ liệu được nén tiếp theo:

~~~java
Deflater compressor = new Deflater(Deflater.BEST_SPEED);
compressor.setLevel(Deflater.BEST_COMPRESSION);
~~~

Đây là **mảnh Java minh họa**; phải import `java.util.zip.Deflater` và gọi `compressor.end()` sau khi không sử dụng nữa.

| Hằng số | Giá trị | Ý nghĩa |
| --- | ---: | --- |
| `Deflater.NO_COMPRESSION` | 0 | Không áp dụng chiến lược giảm kích thước DEFLATE thông thường; luồng vẫn có framing phù hợp |
| `Deflater.BEST_SPEED` | 1 | Ưu tiên tốc độ nén |
| Mức từ 2 tới 8 | 2–8 | Các lựa chọn đánh đổi giữa tốc độ và khả năng nén |
| `Deflater.BEST_COMPRESSION` | 9 | Ưu tiên khả năng nén |
| `Deflater.DEFAULT_COMPRESSION` | -1 | Để implementation dùng mức mặc định |

Constructor thông dụng:

~~~java
new Deflater();                              // Mức mặc định, zlib wrapper
new Deflater(Deflater.BEST_SPEED);           // Level 1, zlib wrapper
new Deflater(Deflater.BEST_COMPRESSION);     // Level 9, zlib wrapper
new Deflater(Deflater.NO_COMPRESSION);       // Level 0, zlib wrapper
new Deflater(6, true);                       // Raw DEFLATE với level 6
~~~

Những giá trị ngoài phạm vi được phép, chẳng hạn `-2` hoặc `10`, dẫn đến `IllegalArgumentException`. Giá trị `-1` là hằng số dành cho mặc định, **không phải mức nén mạnh hơn 9**.

### Level 0 có đồng nghĩa trả nguyên input không?

Không. `NO_COMPRESSION` dùng chế độ không nén payload theo lựa chọn DEFLATE, nhưng **đầu ra vẫn là một luồng nén được đóng gói** theo định dạng đã chọn. Với zlib wrapper, có overhead header/trailer và thông tin block. Byte đầu ra không mặc nhiên bằng đúng byte đầu vào; vẫn phải giải nén đúng định dạng để lấy byte gốc.

Với dữ liệu nhỏ hoặc khó nén, kết quả đầu ra có thể **lớn hơn input** vì overhead. Vì vậy mức nén 9 cũng **không bảo đảm** kích thước tệp sẽ nhỏ hơn mức 1 trong mọi trường hợp.

### Level 9 có luôn tạo file nhỏ nhất?

Không có bảo đảm phổ quát như vậy trong API. Kích thước phụ thuộc:

- Loại dữ liệu: text lặp lại thường dễ nén hơn dữ liệu đã nén/mã hóa ngẫu nhiên.
- Kích thước khối input và cách cung cấp dữ liệu theo thời gian.
- Phiên bản/thư viện zlib bên dưới và implementation.
- Mức nén, strategy và cách flush stream.
- Định dạng chứa, metadata và overhead.

Level 9 thường tiêu tốn nhiều CPU hơn để cố gắng giảm số byte, nhưng **không có cam kết tỷ lệ nén cụ thể**. Level 1 thường nhanh hơn, phù hợp khi độ trễ nén quan trọng, nhưng cũng không có cam kết thời gian cố định.

## 4. Ranh giới kiểm soát của mức nén

Cần phân biệt những thứ mức nén **có thể ảnh hưởng** và những thứ nó **không trực tiếp bảo đảm**:

| Khía cạnh | Mức nén có ảnh hưởng? | Giải thích |
| --- | --- | --- |
| Chi phí CPU khi nén | Có, thường rõ rệt | Mức cao thường tìm kiếm phương án nén nhiều hơn |
| Kích thước output | Có thể | Kết quả phụ thuộc dữ liệu, overhead, flush, implementation |
| Tốc độ giải nén | Có thể có khác biệt gián tiếp | Không có một mức giải nén đối xứng để chọn |
| Tính đúng đắn của dữ liệu giải nén | Không nên thay đổi | Luồng hợp lệ phải giải nén ra byte gốc |
| Charset/encoding của văn bản | Không | Encoder ký tự được chọn trước/ngoài bộ nén |
| Mã hóa bảo mật | Không | DEFLATE không phải encryption |
| Metadata ZIP/GZIP | Không | Định dạng chứa quyết định metadata |
| Bảo đảm archive có CRC và entries | Không | Được quản lý bởi container/API ZIP/GZIP |
| Dung lượng lớn nhất sau giải nén | Không | Phải tự áp hạn mức output để tránh decompression bomb |
| Kết quả byte nén giống nhau trên mọi JDK | Không | API không bảo đảm tính tái lập byte-for-byte giữa implementations |

Phạm vi này quyết định cách thiết kế API. Nếu muốn cho người dùng lựa chọn "nhanh" hay "nén kỹ", có thể map tới level 1 hoặc 9. Nhưng nếu nghiệp vụ yêu cầu kích thước không vượt 100 KiB, **chọn level 9 không thay thế việc kiểm tra dung lượng thực tế**.

Một thiết kế tốt nên đo thời gian CPU, output size và tỷ lệ nén với **chính loại dữ liệu ứng dụng** thay vì dựa vào nhãn mức nén để dự đoán tuyệt đối.

## 5. `Deflater` là bộ nén có trạng thái

Chu trình làm việc:

~~~text
new Deflater(level)
        |
        v
setInput(bytes)
        |
        v
deflate(outBuffer) ── trả số byte đã nén ra ──> lưu/chuyển đi
        |
        +── needsInput() ? cung cấp input kế tiếp
        |
        +── finish() khi không còn input
        |
        v
lặp deflate(...) cho đến finished() == true
        |
        v
end() giải phóng tài nguyên native
~~~

Các API quan trọng:

- `setInput(byte[])` hoặc overload có offset/length: đưa byte nguồn vào cho compressor.
- `needsInput()`: cho biết compressor đã tiêu thụ input hiện có và có thể cần thêm.
- `deflate(byte[])`, overload theo offset/length: ghi byte đã nén vào output và trả **số byte thực sự sinh ra**.
- `finish()`: báo **đã cung cấp hết input**, yêu cầu kết thúc luồng ở các lần `deflate` tiếp theo.
- `finished()`: chỉ đúng khi compressor đã kết thúc toàn bộ việc sinh output.
- `reset()`: reset trạng thái để bắt đầu một luồng nén mới với cùng object; không nối liền hai luồng cũ/mới như một luồng duy nhất.
- `end()`: giải phóng tài nguyên; không tiếp tục sử dụng sau khi kết thúc.

**`finish()` không tự trả ra toàn bộ byte nén.** Sau khi gọi `finish()` vẫn phải lặp `deflate(...)` cho đến `finished()`. Nếu output buffer nhỏ, nhiều lượt mới lấy đủ dữ liệu.

Tương tự, một lần `deflate(...)` không bảo đảm đã xử lý hết input hoặc ghi hết luồng nén. Kiểm tra số byte trả về và trạng thái compressor; không viết một chương trình chỉ gọi đúng một lần khi dữ liệu có thể lớn.

Khi cần nén theo streaming, thường gọi `setInput` mỗi lần `needsInput()` trở thành true, ghi toàn bộ output phát sinh ra tệp/mạng rồi lặp lại; khi nguồn EOF thì `finish()`, tiếp tục drain output. Trong ứng dụng nhỏ, có thể đưa toàn bộ byte input một lần như ví dụ ở phần sau.

## 6. `Inflater` giải nén như thế nào?

`Inflater` tiếp nhận **luồng byte đã nén** và tạo byte gốc. Nó không nhận một mức nén như `Deflater`.

~~~text
new Inflater()                  // zlib wrapper
        |
setInput(compressedBytes)
        |
inflate(uncompressedBuffer)
        |
        +── n > 0: có byte gốc mới
        |
        +── needsInput(): cần thêm input nén
        |
        +── needsDictionary(): cần dictionary phù hợp
        |
        +── DataFormatException: dữ liệu nén không hợp lệ
        |
        v
finished() == true
        |
        v
end()
~~~

Các trạng thái cần hiểu:

- `inflate(byte[])` trả số byte gốc được sinh ra trong lần gọi.
- `finished()` xác nhận đã đạt điểm kết thúc luồng nén.
- `needsInput()` nghĩa là Inflater không còn input nén để dùng; nếu nguồn file/mạng vẫn còn thì đưa thêm. Nếu nguồn đã EOF mà `finished()` chưa đúng, dữ liệu có thể bị cắt cụt.
- `needsDictionary()` báo luồng yêu cầu một preset dictionary; ứng dụng phải có đúng dictionary đã dùng lúc nén.
- `getRemaining()` cho biết số byte input nén còn nằm trong Inflater sau khi giải nén, hữu ích khi xử lý trailer hoặc nhiều phần dữ liệu nối tiếp.
- `DataFormatException` báo luồng không hợp lệ hoặc có vấn đề định dạng. Không đồng nhất mọi lỗi giải nén với lỗi charset.

**Không có `new Inflater(level)`**. Decoder phải đọc một luồng DEFLATE hợp lệ bất kể bên nén đã chọn mức 0, 1 hay 9. Mức nén không làm mất mát dữ liệu gốc; đây là cơ chế nén **lossless**.

Nếu đã giải nén hết một luồng và muốn dùng lại cùng object, gọi `reset()` rồi cấp input của **luồng mới** theo định dạng thích hợp. Không gọi `reset()` giữa một luồng đang xử lý dở.

## 7. Chương trình Java 17+ đầy đủ: nén nhiều mức và giải nén đúng dữ liệu

Chương trình này tạo dữ liệu ASCII lặp lại, nén cùng một payload với ba mức nén khác nhau, giải nén từng kết quả và so sánh byte-for-byte với nguồn.

Ví dụ cố ý **không in số byte compressed**, vì số byte cụ thể có thể khác giữa runtime/zlib implementation. Kết quả round-trip boolean mới là điều cần xác minh.

Lưu tên file `DeflaterInflaterDemo.java`:

~~~java
import java.io.ByteArrayOutputStream;
import java.io.EOFException;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.util.Arrays;
import java.util.zip.DataFormatException;
import java.util.zip.Deflater;
import java.util.zip.Inflater;

public class DeflaterInflaterDemo {
    private static final int MAX_DECOMPRESSED_BYTES = 1_000_000;

    static byte[] compress(byte[] input, int level) throws IOException {
        Deflater encoder = new Deflater(level); // zlib wrapper
        try {
            encoder.setInput(input);
            encoder.finish();

            ByteArrayOutputStream result = new ByteArrayOutputStream();
            byte[] buffer = new byte[128];

            while (!encoder.finished()) {
                int n = encoder.deflate(buffer);
                if (n == 0) {
                    throw new IOException("Deflater made no progress");
                }
                result.write(buffer, 0, n);
            }
            return result.toByteArray();
        } finally {
            encoder.end();
        }
    }

    static byte[] decompress(byte[] compressed)
            throws IOException, DataFormatException {
        Inflater decoder = new Inflater(); // zlib wrapper
        try {
            decoder.setInput(compressed);
            ByteArrayOutputStream result = new ByteArrayOutputStream();
            byte[] buffer = new byte[128];

            while (!decoder.finished()) {
                int n = decoder.inflate(buffer);

                if (n > 0) {
                    if (result.size() + n > MAX_DECOMPRESSED_BYTES) {
                        throw new IOException("Decompressed data too large");
                    }
                    result.write(buffer, 0, n);
                    continue;
                }

                if (decoder.needsDictionary()) {
                    throw new IOException("Preset dictionary required");
                }
                if (decoder.needsInput()) {
                    throw new EOFException("Compressed stream truncated");
                }
                throw new IOException("Inflater made no progress");
            }
            return result.toByteArray();
        } finally {
            decoder.end();
        }
    }

    public static void main(String[] args)
            throws IOException, DataFormatException {
        byte[] source = "JAVA-NIO-COMPRESSION;".repeat(500)
                .getBytes(StandardCharsets.UTF_8);

        byte[] noCompression =
                compress(source, Deflater.NO_COMPRESSION);
        byte[] fast = compress(source, Deflater.BEST_SPEED);
        byte[] dense = compress(source, Deflater.BEST_COMPRESSION);

        System.out.println("level 0 round-trip: "
                + Arrays.equals(source, decompress(noCompression)));
        System.out.println("level 1 round-trip: "
                + Arrays.equals(source, decompress(fast)));
        System.out.println("level 9 round-trip: "
                + Arrays.equals(source, decompress(dense)));
        System.out.println("same original bytes: "
                + Arrays.equals(decompress(fast), decompress(dense)));
        System.out.println("input bytes: " + source.length);
    }
}
~~~

Biên dịch và chạy với JDK 17+:

~~~bash
javac DeflaterInflaterDemo.java
java DeflaterInflaterDemo
~~~

Stdout:

~~~text
level 0 round-trip: true
level 1 round-trip: true
level 9 round-trip: true
same original bytes: true
input bytes: 10500
~~~

Lý giải kết quả:

1. Chuỗi ASCII `JAVA-NIO-COMPRESSION;` gồm **21 byte**; lặp 500 lần được **10.500 byte** input.
2. `NO_COMPRESSION` (level 0) vẫn tạo ra một **luồng zlib hợp lệ**, có thể giải nén lại thành đúng input.
3. `BEST_SPEED` (level 1) và `BEST_COMPRESSION` (level 9) tạo các luồng nén với ưu tiên khác nhau; cả hai phải khôi phục cùng payload.
4. `Arrays.equals` so sánh byte gốc, không chỉ kiểm tra kích thước hoặc text được giải mã.
5. Buffer output chỉ có 128 byte; cả compressor và decoder đều được gọi lặp, tránh giả định một lượt nén/giải nén luôn hoàn thành.
6. `end()` trong `finally` giải phóng tài nguyên kể cả khi có lỗi.
7. Phần giải nén giới hạn output ở 1.000.000 byte để minh họa phòng tránh việc nhận một luồng nén rất nhỏ nhưng giải nén thành dữ liệu quá lớn.

Ví dụ dùng input đã biết và không cần dictionary, nên không phát sinh các trường hợp lỗi dictionary hay truncated stream khi chạy bình thường. Nếu tự sửa compressed bytes hoặc cắt giữa dòng, decoder có thể ném `DataFormatException`, `EOFException` hoặc ngoại lệ liên quan, thay vì in đủ năm dòng.

**Vì sao không in "level 9 chắc chắn nhỏ hơn level 1"?** Trên dữ liệu này thường có khác biệt kích thước, nhưng API không bảo đảm thứ tự tuyệt đối cho mọi input và mọi implementation. Nếu đang tối ưu hệ thống, hãy đo `compressed.length` thực tế và thời gian nén trên bộ dữ liệu đại diện.

## 8. `setLevel()` thay đổi những gì?

`Deflater.setLevel(int level)` cho phép điều chỉnh level của **những phần dữ liệu sẽ được nén tiếp theo**. Cách làm đúng là hiểu object Deflater là một state machine:

~~~java
Deflater encoder = new Deflater(Deflater.BEST_SPEED);
try {
    encoder.setInput(firstChunk);
    // Drain dữ liệu được tạo theo quy trình streaming.
    // Sau khi xử lý đầu vào này, có thể đổi ưu tiên:
    encoder.setLevel(Deflater.BEST_COMPRESSION);
    encoder.setInput(nextChunk);
    // Tiếp tục deflate(...) cho đến khi hết.
} finally {
    encoder.end();
}
~~~

Đây là **pseudocode dạng mảnh Java**, không phải chương trình chạy độc lập: `firstChunk`, `nextChunk` và hàm drain cần được định nghĩa. Không sao chép nguyên đoạn mà bỏ qua các bước tiêu thụ input, kiểm tra `needsInput()` và lấy output.

Các giới hạn quan trọng:

- `setLevel` không nén lại các byte đã được sinh ra trước đó; nó ảnh hưởng tới quá trình nén tiếp theo.
- Thay level không tự chuyển codec, không thay zlib sang gzip và không tự tạo một ZIP entry mới.
- Một luồng DEFLATE hợp lệ vẫn giải nén được mà không cần truyền mức nén cho `Inflater`.
- Khi đang thay level giữa luồng, cần tuân thủ thứ tự cấp input/deflate và flush phù hợp để không làm rối state; không dùng setter như lệnh "đã áp dụng ngay cho mọi byte trước đó".
- Nếu nhu cầu là "mỗi tệp một level" trong một archive ZIP, dùng API archive hỗ trợ level cho các entry theo đúng ngữ nghĩa, không đơn giản ghép các luồng Deflater tùy ý vào tệp ZIP.

Trong thực tế, **lựa chọn một mức nén khi bắt đầu luồng** rồi giữ cố định thường dễ kiểm thử hơn thay đổi liên tục. Thay level giữa một luồng chỉ khi đã xác định nhu cầu streaming và đo hiệu quả.

## 9. Strategy không đồng nghĩa mức nén

Ngoài `setLevel`, `Deflater` có `setStrategy(int strategy)`. Các strategy thường dùng:

| Strategy | Mục tiêu |
| --- | --- |
| `DEFAULT_STRATEGY` | Lựa chọn mặc định cho dữ liệu tổng quát |
| `FILTERED` | Có thể hữu ích với một số dữ liệu đã qua bộ lọc hoặc có phân bố ký hiệu đặc thù |
| `HUFFMAN_ONLY` | Sử dụng mã Huffman, không dựa trên tìm kiếm chuỗi lặp kiểu LZ77 như strategy mặc định |

Ví dụ:

~~~java
Deflater encoder = new Deflater(Deflater.BEST_SPEED);
try {
    encoder.setStrategy(Deflater.FILTERED);
    // Nén dữ liệu phù hợp bằng setInput/deflate/finish.
} finally {
    encoder.end();
}
~~~

Đây là mảnh code minh họa, không nén dữ liệu hoàn chỉnh. Strategy **không thay thế level**: có thể có level cao nhưng strategy không phù hợp khiến kết quả kém hơn kỳ vọng.

Tùy input, thay strategy có thể tăng/giảm tốc độ hoặc output size. Không nên chọn `FILTERED` hay `HUFFMAN_ONLY` chỉ vì tên nghe nhanh hơn hoặc "nén sâu" hơn. Hãy benchmark trên dữ liệu thực và dùng strategy mặc định nếu chưa có lý do rõ ràng.

## 10. Flush mode cũng ảnh hưởng hiệu quả nén

`Deflater` có các overload `deflate(...)` nhận một flush mode, ví dụ:

- `NO_FLUSH`: trạng thái thông thường; ưu tiên tiếp tục khai thác dữ liệu có sẵn trong stream.
- `SYNC_FLUSH`: làm output có thể được đồng bộ/giải nén tới ranh giới phù hợp mà không bắt buộc kết thúc stream.
- `FULL_FLUSH`: ngoài việc flush, reset thông tin nén cần thiết để bên giải nén có thể khôi phục từ ranh giới thích hợp; có thể làm giảm tỷ lệ nén.

Đây là **điều khiển quá trình streaming**, không phải ba mức nén mới. Flush quá thường xuyên tạo thêm overhead và giảm khả năng khai thác dữ liệu lặp xuyên ranh giới chunk.

Một số ứng dụng truyền dữ liệu realtime muốn giảm độ trễ bằng flush thường xuyên; ứng dụng lưu trữ tệp lớn muốn size tốt hơn thường tránh flush không cần thiết. Việc lựa chọn phải dựa vào giao thức phía nhận, latency mục tiêu và benchmark.

**Phân biệt `finish()` với flush:** `finish()` báo chấm dứt input và cuối stream. `SYNC_FLUSH`/`FULL_FLUSH` phục vụ tạo điểm đồng bộ trong **một stream còn tiếp tục**; chúng không thay thế `finish()`.

## 11. Dictionary là một cơ chế khác

Với dữ liệu có các mẫu lặp nhỏ và biết trước, DEFLATE hỗ trợ **preset dictionary** ở những dạng stream phù hợp. Phía nén có thể dùng `Deflater.setDictionary(...)`; phía giải nén có thể gặp `Inflater.needsDictionary()` rồi cần gọi `Inflater.setDictionary(...)` với đúng dữ liệu từ điển.

Việc đặt mức nén 9 **không tự truyền dictionary** cho decoder. Nếu decoder thiếu dictionary cần thiết, một luồng có thể không được giải nén dù payload không bị hỏng.

Trong thiết kế giao thức:

1. Xác định dictionary có dùng hay không.
2. Phía nhận phải biết cùng phiên bản dictionary, bằng cấu hình chung hoặc metadata/giao thức riêng.
3. Xử lý `needsDictionary()` rõ ràng.
4. Đừng kỳ vọng chiến lược dictionary áp dụng được nguyên vẹn cho mọi container/định dạng; ví dụ ZIP entry thông thường có những ràng buộc riêng.

Preset dictionary là tối ưu nâng cao, không phải yêu cầu mặc định của phần lớn nhu cầu nén Java.

## 12. DeflaterOutputStream và các API mức cao

Nếu chỉ muốn nén dữ liệu ghi ra stream, `DeflaterOutputStream` giúp quản lý chu trình input/output:

~~~java
import java.io.ByteArrayOutputStream;
import java.util.zip.Deflater;
import java.util.zip.DeflaterOutputStream;

ByteArrayOutputStream destination = new ByteArrayOutputStream();
Deflater encoder = new Deflater(Deflater.BEST_SPEED);

try (DeflaterOutputStream compressed =
        new DeflaterOutputStream(destination, encoder)) {
    compressed.write(payload);
}

// Dữ liệu nén có trong destination.toByteArray().
// Quản lý vòng đời Deflater theo hợp đồng của stream/constructor.
~~~

Đây là **mảnh code minh họa** dùng biến `payload` phải được tạo trước; nó không phải một chương trình độc lập. Khi tự truyền object Deflater cho stream, hãy xác định ai chịu trách nhiệm đóng/`end()` theo overload đang dùng, tránh bỏ quên native resource. `close()` hoặc `finish()` trên stream phải hoàn tất output nén trước khi đọc kết quả cuối.

Để giải nén stream zlib tương ứng, có `InflaterInputStream`. Với định dạng gzip hãy dùng `GZIPOutputStream`/`GZIPInputStream`. Với định dạng ZIP, dùng `ZipOutputStream` hoặc `ZipFile`/`ZipInputStream`.

### Điều khiển mức nén khi đóng gói ZIP

`ZipOutputStream` có `setLevel(int)` để chọn mức nén của các **entry DEFLATED tiếp theo** theo ngữ nghĩa API. Nó khác với việc tạo một `Deflater` độc lập rồi ghi raw bytes thẳng vào archive.

Một ZIP archive còn có entry names, timestamps, metadata, CRC và central directory. `Deflater` đơn thuần không tạo các cấu trúc đó. Đối với dữ liệu chỉ cần nén thành một blob zlib, `Deflater` phù hợp; đối với nhiều file trong cùng archive, hãy dùng API archive.

## 13. An toàn dữ liệu và hiệu năng khi giải nén

Nén mạnh không đồng nghĩa giải nén an toàn với dữ liệu không tin cậy. Một payload compressed nhỏ có thể tạo output cực lớn. Nếu ứng dụng nhận dữ liệu nén từ bên ngoài, cần giới hạn:

- **Kích thước output sau giải nén** tính bằng byte, không chỉ giới hạn compressed input.
- **Thời gian/CPU** tối đa cho việc giải nén theo chính sách.
- **Dung lượng bộ nhớ**, kích thước các buffer và số tác vụ đồng thời.
- **Số luồng hoặc entry archive** được phép xử lý nếu input là container ZIP.
- **Độ sâu giải nén lồng nhau** nếu giao thức chấp nhận nhiều lớp nén.

Ví dụ ở trên giới hạn output ở 1.000.000 byte. Trong hệ thống thực tế, ngưỡng phụ thuộc domain, có thể phải dùng streaming ra nơi lưu trữ và dừng ngay khi vượt quota thay vì giữ toàn bộ output trong RAM.

Kiểm tra kết quả `Inflater.finished()`. Nếu hết input mà chưa finished, có thể dữ liệu bị cắt cụt; nếu `DataFormatException` thì input/định dạng không hợp lệ. Ngoài ra, nếu giao thức yêu cầu **toàn bộ compressed buffer phải được tiêu thụ**, kiểm tra `getRemaining()` hoặc kiểm tra trailer/container theo chuẩn đang dùng; đừng bỏ qua byte dư tùy tiện.

**Nén không phải bảo mật.** DEFLATE không mã hóa và không xác thực người gửi. Khi cần confidentiality/integrity, kết hợp giao thức mã hóa/xác thực riêng, không kỳ vọng mức nén cao giúp che giấu nội dung.

Trong giao thức có bí mật và dữ liệu do kẻ tấn công điều khiển nằm chung trong một ngữ cảnh nén, kích thước output còn có thể làm lộ thông tin; hãy đánh giá rủi ro compression side-channel theo kiến trúc cụ thể.

## 14. Cách chọn level trong ứng dụng

| Nhu cầu | Điểm khởi đầu nên thử | Điều vẫn phải đo |
| --- | --- | --- |
| Độ trễ thấp, CPU giới hạn | `BEST_SPEED` | Latency, CPU, số byte truyền |
| File lưu trữ lớn và ít thay đổi | `BEST_COMPRESSION` hoặc level trung bình-cao | Thời gian nén, tỉ lệ nén, chi phí lưu trữ |
| Dữ liệu đã nén hoặc khó nén | Level thấp hoặc bỏ qua nén | Overhead, kích thước có tăng không |
| Cân bằng thông thường | `DEFAULT_COMPRESSION` | Dữ liệu thật, khả năng CPU của hệ thống |
| Streaming realtime | Level thấp/trung bình và flush có chủ đích | Độ trễ từng chunk, overhead flush |
| Đóng gói nhiều file | API ZIP với level cho entry phù hợp | Metadata/CRC/archive, CPU và size từng entry |

Đây là **điểm bắt đầu để thử**, không phải kết luận tuyệt đối. Nên đo trên dữ liệu đại diện: tổng byte trước/sau, thời gian nén, thời gian giải nén, RAM peak và tính đúng đắn của round-trip.

Ví dụ với log văn bản lặp lại, level cao có thể giảm dung lượng đáng kể; với JPEG, MP4 hoặc dữ liệu đã nén, level cao có thể ít lợi ích mà tăng CPU. Bỏ qua nén hoàn toàn ở tầng ứng dụng đôi khi tiết kiệm tài nguyên hơn.

## 15. Lỗi thường gặp

**Lỗi 1 — Nghĩ Inflater cần được cấu hình cùng level.** Decoder không có tham số level đối xứng. Chọn `Inflater` đúng **format wrapper và dictionary** mới là điều quan trọng.

**Lỗi 2 — Nghĩ level 9 luôn cho output nhỏ hơn level 1.** Không có đảm bảo chung. Phải đo output size trên dữ liệu cụ thể.

**Lỗi 3 — Gọi finish() rồi không drain hết output.** `finish()` không tự xuất toàn bộ byte; tiếp tục `deflate(...)` đến `finished()`.

**Lỗi 4 — Chỉ gọi deflate/inflate một lần.** Buffer đích có thể nhỏ hơn dữ liệu. Phải lặp theo trạng thái và số byte trả về.

**Lỗi 5 — Nhầm zlib wrapper với gzip hoặc ZIP archive.** `new Deflater(level)` không tạo file `.gz` hoặc `.zip` hoàn chỉnh.

**Lỗi 6 — Một bên nowrap=true, bên kia nowrap=false.** Hai phía dùng định dạng không tương thích có thể giải nén thất bại.

**Lỗi 7 — Coi NO_COMPRESSION là giữ nguyên từng byte input.** Dù không nén payload, stream vẫn có framing/overhead.

**Lỗi 8 — Quên end().** `Deflater` và `Inflater` có thể nắm tài nguyên native; dùng `finally` hoặc cấu trúc lifecycle phù hợp.

**Lỗi 9 — Không xử lý needsInput/needsDictionary.** Decoder có thể cần thêm compressed input hoặc dictionary; quay vòng inflate khi liên tục trả 0 sẽ treo CPU.

**Lỗi 10 — Giải nén input không tin cậy không giới hạn kích thước.** Nguy cơ decompression bomb gây cạn RAM/CPU.

**Lỗi 11 — Flush mọi chunk để mong file nhỏ hơn.** Flush thường xuyên tạo overhead, có thể giảm hiệu quả nén.

**Lỗi 12 — Cho rằng mức nén thay thế checksum hoặc encryption.** Tính bảo mật và độ toàn vẹn thuộc tầng khác; wrapper như zlib chỉ có kiểm tra lỗi dữ liệu ở mức định dạng, không phải mã xác thực an toàn trước tấn công.

## 16. Tự kiểm tra

1. `BEST_SPEED` và `BEST_COMPRESSION` có giá trị bao nhiêu? **1** và **9**.
2. `DEFAULT_COMPRESSION` có giá trị bao nhiêu? **-1**, biểu diễn cấu hình mặc định.
3. `NO_COMPRESSION` có trả lại đúng nguyên input bytes không? **Không nhất thiết**, vì output vẫn có framing.
4. `Inflater` có cần biết level đã dùng khi nén? **Không**.
5. Vì sao phải lặp `deflate` sau `finish()`? **Vì output nén có thể còn trong compressor**, chưa được drain hết.
6. `needsDictionary()` có nghĩa gì? **Input nén cần một preset dictionary**, không phải yêu cầu thử level lớn hơn.
7. `nowrap=true` có tạo file gzip không? **Không**; nó chọn raw DEFLATE không có zlib wrapper, còn gzip có header/trailer riêng.
8. `setStrategy(HUFFMAN_ONLY)` có giống `setLevel(9)` không? **Không**; strategy và level là hai điều khiển khác nhau.
9. Nén xong 100 KiB thành 4 KiB có chứng minh giải nén luôn dưới 100 KiB RAM không? **Không**; còn nhiều overhead và cần giới hạn output thực tế.
10. Một luồng bị cắt cụt khiến `Inflater.needsInput() == true` nhưng chưa `finished()`. Nên làm gì? **Thử đọc thêm nếu nguồn còn dữ liệu; nếu EOF thật thì báo lỗi input chưa hoàn chỉnh**.
11. Nếu muốn archive nhiều file, có nên tự nối nhiều output `Deflater` thành file `.zip` không? **Không**; dùng API ZIP tạo entry và metadata hợp lệ.
12. Nếu level 9 nén được ít hơn chỉ 1% nhưng tốn CPU gấp nhiều lần, lựa chọn thực tế ra sao? **Đo theo ngân sách CPU, latency, băng thông và chi phí lưu trữ của ứng dụng**, không mặc định level cao nhất là tốt nhất.

**Ghi nhớ:** `Deflater` điều khiển quá trình nén DEFLATE, trong đó **level 0–9 hoặc DEFAULT_COMPRESSION** chủ yếu điều chỉnh đánh đổi tốc độ/khả năng giảm byte. `Inflater` giải nén luồng hợp lệ **không cần biết level**. Ngoài level còn có strategy, flush, dictionary và format wrapper, mỗi yếu tố có hợp đồng riêng. Luôn hoàn tất chu trình `setInput → deflate → finish/finished → end`, giải nén có giới hạn và xác minh round-trip; không lấy mức nén làm cam kết kích thước, hiệu năng hay bảo mật.
