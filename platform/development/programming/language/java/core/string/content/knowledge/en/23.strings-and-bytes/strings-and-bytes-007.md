# CharsetEncoder, CharsetDecoder và chính sách REPORT trong Java

Khi trao đổi dữ liệu với tệp, mạng hoặc hệ thống khác, ứng dụng phải chuyển đổi giữa chuỗi ký tự Unicode và dãy byte. `CharsetEncoder`, `CharsetDecoder` cho phép thực hiện chuyển đổi này một cách có kiểm soát; `CodingErrorAction.REPORT` yêu cầu **phát hiện và báo lỗi dữ liệu không thể chuyển đổi**, thay vì âm thầm thay thế hoặc bỏ ký tự. Đây là lựa chọn phù hợp khi tính toàn vẹn dữ liệu quan trọng.

## 1. Nền tảng: ký tự, byte và charset

- `String` chứa văn bản Unicode dưới dạng các đơn vị mã UTF-16 của Java. Một ký tự ngoài BMP có thể chiếm hai `char` (surrogate pair), vì vậy một `char` không luôn tương đương một ký tự Unicode hoàn chỉnh.
- `Charset` mô tả quy tắc ánh xạ giữa ký tự và byte, ví dụ `StandardCharsets.UTF_8` hoặc `StandardCharsets.US_ASCII`.
- **Encoding** (mã hóa văn bản): `CharBuffer` → `CharsetEncoder` → `ByteBuffer`.
- **Decoding** (giải mã byte): `ByteBuffer` → `CharsetDecoder` → `CharBuffer`.
- `ByteBuffer` và `CharBuffer` có `position`, `limit`, `capacity`. Bộ mã hóa/giải mã đọc từ `position` hiện tại của đầu vào và ghi tại `position` hiện tại của đầu ra. Sau khi ghi thủ công, gọi `flip()` trước khi đọc; trước khi ghi tiếp vào buffer đã đọc dở, dùng `compact()` nếu cần giữ dữ liệu chưa xử lý.

Cùng một dãy byte có thể mang ý nghĩa khác nhau dưới các charset khác nhau. Vì vậy phải biết charset từ giao thức hoặc hợp đồng dữ liệu; không thể suy ra charset chính xác chỉ bằng `REPORT`.

## 2. Vai trò của các API

| API | Vai trò |
| --- | --- |
| `Charset.newEncoder()` | Tạo bộ mã hóa ký tự thành byte cho charset đã chọn. |
| `Charset.newDecoder()` | Tạo bộ giải mã byte thành ký tự cho charset đã chọn. |
| `CodingErrorAction.REPORT` | Dừng và báo lỗi khi gặp dữ liệu malformed hoặc unmappable. |
| `CodingErrorAction.REPLACE` | Dùng chuỗi/byte thay thế khi gặp lỗi, tiếp tục xử lý. |
| `CodingErrorAction.IGNORE` | Bỏ qua dữ liệu gây lỗi, tiếp tục xử lý. |
| `CharacterCodingException` | Lớp ngoại lệ chung cho lỗi chuyển đổi bằng các phương thức tiện ích có kiểm tra. |
| `MalformedInputException` | Đầu vào không hợp lệ về cấu trúc mã hóa. |
| `UnmappableCharacterException` | Đầu vào hợp lệ nhưng không có ánh xạ sang bảng mã đích. |
| `CoderResult` | Kết quả từng bước chuyển đổi: `UNDERFLOW`, `OVERFLOW`, malformed hoặc unmappable. |

### Malformed và unmappable khác nhau thế nào?

| Chiều chuyển đổi | Malformed | Unmappable |
| --- | --- | --- |
| Decode (byte → char) | Byte vi phạm cấu trúc của charset; ví dụ `C3 28` không phải chuỗi UTF-8 hợp lệ. | Chuỗi byte có cấu trúc hợp lệ theo charset nhưng không ánh xạ được thành ký tự Unicode; tùy charset mà trường hợp này có thể xảy ra. |
| Encode (char → byte) | Đầu vào ký tự UTF-16 sai cấu trúc, ví dụ một high surrogate đứng lẻ (`U+D800`). | Ký tự Unicode hợp lệ nhưng charset đích không biểu diễn được; ví dụ ký tự `€` với US-ASCII. |

Cấu trúc lỗi được xác định theo charset đang dùng. Không phải mọi charset đều sinh ra cả hai loại lỗi trong thực tế.

## 3. Cấu hình REPORT đúng cách

Tạo bộ mã hóa và bộ giải mã với charset tường minh; cấu hình cả **malformed input** và **unmappable character**:

~~~java
CharsetDecoder decoder = StandardCharsets.UTF_8.newDecoder()
    .onMalformedInput(CodingErrorAction.REPORT)
    .onUnmappableCharacter(CodingErrorAction.REPORT);

CharsetEncoder encoder = StandardCharsets.UTF_8.newEncoder()
    .onMalformedInput(CodingErrorAction.REPORT)
    .onUnmappableCharacter(CodingErrorAction.REPORT);
~~~

Đoạn trên là ví dụ cấu hình bên trong phương thức hoặc chương trình đã import `java.nio.charset.*`; xem chương trình đầy đủ ở phần tiếp theo.

Một encoder/decoder mới trong Java vốn có chính sách lỗi mặc định `REPORT`; vẫn nên khai báo tường minh để thể hiện hợp đồng dữ liệu và tránh việc bỏ sót khi tái sử dụng đối tượng đã đổi cấu hình. Cả hai nhánh cần được đặt bởi có hai nguyên nhân lỗi độc lập.

**Khác biệt quyết định giữa hai kiểu API:**

- Với `encoder.encode(CharBuffer)` và `decoder.decode(ByteBuffer)` (phương thức tiện ích một lần), lỗi `REPORT` được chuyển thành `CharacterCodingException`, thường là một trong hai lớp con ở bảng trên.
- Với `encoder.encode(in, out, endOfInput)` và `decoder.decode(in, out, endOfInput)` (API từng bước), lỗi `REPORT` **trả về một `CoderResult` lỗi**. Người gọi phải kiểm tra `result.isError()`, rồi gọi `result.throwException()` hoặc có cơ chế xử lý rõ ràng. Chỉ cấu hình `REPORT` mà bỏ qua `CoderResult` vẫn có thể khiến ứng dụng không xử lý đúng lỗi.
- `REPLACE` và `IGNORE` làm thay đổi dữ liệu. Dùng chúng khi nghiệp vụ chủ động chấp nhận mất thông tin; không dùng để kiểm chứng đầu vào nguyên vẹn.

## 4. Chương trình Java 17+: báo lỗi rõ ràng

Lưu đoạn sau thành **StrictCharsetDemo.java** (UTF-8). Ví dụ dùng bộ mã hóa và giải mã riêng cho từng lượt, cố ý tạo ba dạng đầu vào để quan sát ngoại lệ.

~~~java
import java.nio.ByteBuffer;
import java.nio.CharBuffer;
import java.nio.charset.*;

public class StrictCharsetDemo {
    static CharsetDecoder strictDecoder(Charset charset) {
        return charset.newDecoder()
            .onMalformedInput(CodingErrorAction.REPORT)
            .onUnmappableCharacter(CodingErrorAction.REPORT);
    }

    static CharsetEncoder strictEncoder(Charset charset) {
        return charset.newEncoder()
            .onMalformedInput(CodingErrorAction.REPORT)
            .onUnmappableCharacter(CodingErrorAction.REPORT);
    }

    public static void main(String[] args) throws CharacterCodingException {
        ByteBuffer bytes = strictEncoder(StandardCharsets.UTF_8)
            .encode(CharBuffer.wrap("Cà phê"));
        String text = strictDecoder(StandardCharsets.UTF_8)
            .decode(bytes).toString();
        System.out.println("Round-trip UTF-8: " + text);

        try {
            strictDecoder(StandardCharsets.UTF_8)
                .decode(ByteBuffer.wrap(
                    new byte[] {(byte) 0xC3, (byte) 0x28}));
        } catch (MalformedInputException ex) {
            System.out.println(
                "Malformed UTF-8: " + ex.getClass().getSimpleName());
        }

        try {
            strictEncoder(StandardCharsets.US_ASCII)
                .encode(CharBuffer.wrap("A€B"));
        } catch (UnmappableCharacterException ex) {
            System.out.println(
                "Unmappable ASCII: " + ex.getClass().getSimpleName());
        }

        try {
            strictEncoder(StandardCharsets.UTF_8)
                .encode(CharBuffer.wrap(new char[] {'\uD800'}));
        } catch (MalformedInputException ex) {
            System.out.println(
                "Malformed surrogate: " + ex.getClass().getSimpleName());
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 StrictCharsetDemo.java
java StrictCharsetDemo
~~~

Kết quả chuẩn:

~~~text
Round-trip UTF-8: Cà phê
Malformed UTF-8: MalformedInputException
Unmappable ASCII: UnmappableCharacterException
Malformed surrogate: MalformedInputException
~~~

**Giải thích:** Văn bản “Cà phê” được UTF-8 biểu diễn đầy đủ nên khôi phục đúng. Byte `C3` mở đầu một chuỗi hai byte trong UTF-8 nhưng `28` không phải byte tiếp diễn, nên decoder báo malformed. Ký tự `€` hợp lệ nhưng US-ASCII không mã hóa được, nên encoder báo unmappable. Một high surrogate đứng lẻ không tạo thành chuỗi UTF-16 hợp lệ, nên encoder UTF-8 báo malformed. Ngoại lệ được bắt riêng để chỉ rõ loại hỏng; trong ứng dụng thật nên ghi thêm ngữ cảnh như nguồn dữ liệu và vị trí xử lý, tránh xuất dữ liệu nhạy cảm ra log.

## 5. Giải mã theo luồng: phân biệt thiếu byte tạm thời và dữ liệu hỏng

Một ký tự UTF-8 có thể bị chia giữa hai lần nhận byte. Nếu chunk đầu chứa `E2 82` (hai byte đầu của `€`), decoder chưa thể kết luận hỏng khi **còn dữ liệu sẽ đến**. Hãy gọi `decode(..., false)` để nhận `UNDERFLOW`, giữ hai byte chưa dùng, nạp thêm `AC`, rồi gọi `decode(..., true)` khi biết đã hết đầu vào. Cuối cùng gọi `flush(...)`.

Chương trình độc lập **IncrementalDecodeDemo.java** minh họa đường đi này trên bộ đệm đủ lớn để không sinh `OVERFLOW`:

~~~java
import java.nio.*;
import java.nio.charset.*;

public class IncrementalDecodeDemo {
    public static void main(String[] args)
            throws CharacterCodingException {
        CharsetDecoder decoder = StandardCharsets.UTF_8.newDecoder()
            .onMalformedInput(CodingErrorAction.REPORT)
            .onUnmappableCharacter(CodingErrorAction.REPORT);
        ByteBuffer input = ByteBuffer.allocate(8);
        CharBuffer output = CharBuffer.allocate(8);

        input.put(new byte[] {(byte) 0xE2, (byte) 0x82});
        input.flip();
        CoderResult first = decoder.decode(input, output, false);
        if (first.isError()) first.throwException();
        System.out.println(
            "Lần 1: " + first
            + ", bytes còn lại: " + input.remaining());

        input.compact(); // Giữ hai byte chưa giải mã.
        input.put((byte) 0xAC);
        input.flip();
        CoderResult last = decoder.decode(input, output, true);
        if (last.isError()) last.throwException();
        if (!last.isUnderflow()) {
            throw new IllegalStateException("Output buffer quá nhỏ");
        }

        CoderResult flushed = decoder.flush(output);
        if (flushed.isError()) flushed.throwException();
        if (!flushed.isUnderflow()) {
            throw new IllegalStateException("Output buffer quá nhỏ");
        }

        output.flip();
        System.out.println("Kết quả: " + output);
    }
}
~~~

~~~bash
javac -encoding UTF-8 IncrementalDecodeDemo.java
java IncrementalDecodeDemo
~~~

~~~text
Lần 1: UNDERFLOW, bytes còn lại: 2
Kết quả: €
~~~

Ở lần đầu, decoder không tiêu thụ hai byte dang dở; `compact()` dời chúng về đầu buffer, để lại chỗ cho byte mới. Sau khi nhận `AC` và thông báo hết đầu vào, bộ giải mã hoàn thành ký tự `€`. Nếu báo `endOfInput=true` ngay ở chunk đầu, hai byte dang dở sẽ được coi là đầu vào lỗi ở cuối luồng và `REPORT` báo lỗi.

### Quy trình cho bộ đệm kích thước hữu hạn

Ví dụ trên chỉ có một ký tự và buffer đủ chứa. Với dữ liệu dài hoặc bộ đệm nhỏ, cần vòng lặp theo `CoderResult`:

1. Nạp byte, `flip()` đầu vào, rồi gọi `decode(input, output, endOfInput)`.
2. Nếu `isError()` thì gọi `throwException()` hoặc xử lý rõ ràng theo chính sách lỗi; không bỏ qua.
3. Nếu `isOverflow()` thì xuất các ký tự đang có trong `output` (thường `flip()`, đọc, rồi `clear()` hoặc `compact()`) và tiếp tục decode cùng phần đầu vào còn lại.
4. Nếu `isUnderflow()` và chưa kết thúc luồng, giữ byte chưa giải mã bằng `input.compact()` rồi nạp thêm; không loại bỏ các byte ở cuối chunk. Nếu đã kết thúc luồng, chuyển sang `flush(output)` và cũng xử lý `OVERFLOW` cho tới khi flush trả `UNDERFLOW`.
5. Khi muốn dùng cùng decoder cho **một phiên chuyển đổi mới**, gọi `reset()` trước khi bắt đầu. Không dùng chung một encoder/decoder đang có trạng thái giữa các thread.

Bộ mã hóa từng bước có cấu trúc tương tự với `encode(CharBuffer, ByteBuffer, endOfInput)`, sau đó là `flush(ByteBuffer)`. Đừng nhầm `UNDERFLOW` với “chuyển đổi thành công toàn bộ”: khi `endOfInput=false`, nó còn có thể biểu thị dữ liệu cuối chunk chưa đủ để tạo ký tự.

## 6. REPORT so với chuyển đổi tiện ích thường gặp

~~~java
String text = new String(bytes, StandardCharsets.UTF_8);
byte[] raw = text.getBytes(StandardCharsets.UTF_8);
~~~

Hai lời gọi tiện ích này tiện cho văn bản tin cậy, nhưng các trường hợp malformed/unmappable có thể được **thay thế** âm thầm theo hợp đồng API. Chúng không cung cấp lựa chọn `CodingErrorAction.REPORT`. Với dữ liệu cần kiểm chứng nghiêm ngặt, dùng `newDecoder()` / `newEncoder()` và thiết lập cả hai chính sách lỗi.

Nếu đọc từ `InputStream`, có thể cấp một decoder đã cấu hình cho `InputStreamReader(InputStream, CharsetDecoder)`. Tương tự, `OutputStreamWriter(OutputStream, CharsetEncoder)` nhận encoder đã cấu hình. Cách này giúp tích hợp chính sách nghiêm ngặt vào việc đọc/ghi luồng; vẫn phải xử lý `IOException` phù hợp và đóng/flush stream đúng cách.

## 7. Lỗi phổ biến và cách tránh

| Lỗi | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Không truyền charset tường minh | Kết quả phụ thuộc cấu hình/hợp đồng môi trường và có thể sai giữa các hệ thống. | Dùng charset đã thống nhất, thường là `StandardCharsets.UTF_8`. |
| Dùng `REPLACE` khi cần bảo toàn byte/ký tự | Dữ liệu bị thay thế mà không báo cho nghiệp vụ. | Chọn `REPORT` và xử lý ngoại lệ/kết quả lỗi. |
| Chỉ đặt `onMalformedInput(REPORT)` | Có thể bỏ qua chính sách cho lỗi unmappable. | Cấu hình cả `onMalformedInput` và `onUnmappableCharacter`. |
| Nghĩ `decode(in, out, ...)` luôn ném lỗi ngay | Với API từng bước, `REPORT` trả `CoderResult` lỗi. | Kiểm tra `isError()` và gọi `throwException()`. |
| Đánh dấu kết thúc luồng quá sớm | Ký tự đa byte bị chia chunk bị coi là malformed. | Dùng `endOfInput=false` cho chunk chưa cuối; giữ byte còn lại. |
| Bỏ qua `OVERFLOW` | Output buffer không đủ, dữ liệu chưa được xử lý hết. | Xả buffer đầu ra và gọi tiếp. |
| Quên `flip()/compact()/flush()/reset()` | Sai `position`/`limit`, mất byte, sót ký tự hoặc sai trạng thái phiên. | Tuân thủ vòng đời buffer và bộ chuyển đổi. |
| Xem `REPORT` là cách tự nhận biết sai charset | Byte có thể hợp lệ trong charset sai nhưng nội dung vẫn vô nghĩa. | Dùng thông tin charset từ hợp đồng/giao thức, BOM khi được định nghĩa, và kiểm tra nội dung ở tầng nghiệp vụ. |

## 8. Gợi ý áp dụng và tự kiểm tra

- **Import CSV/JSON nghiêm ngặt:** Quy định UTF-8, giải mã bằng decoder dùng `REPORT`, từ chối file có byte malformed trước khi parse nội dung. Lưu ý UTF-8 hợp lệ vẫn có thể chứa dữ liệu sai schema; cần kiểm tra schema riêng.
- **Xuất sang hệ thống dùng charset hạn chế:** Encode bằng `REPORT` để biết chính xác văn bản có ký tự không xuất được; yêu cầu chỉnh dữ liệu hoặc thỏa thuận charset khác, thay vì mất ký tự.
- **Nhận dữ liệu qua socket:** Giữ các byte dang dở giữa các lần đọc, chỉ đặt `endOfInput=true` khi thông điệp hoặc luồng thật sự kết thúc theo giao thức.

Tự trả lời ba câu hỏi: (1) Vì sao `C3 28` khiến UTF-8 decoder báo `MalformedInputException`? (2) Vì sao `€` tạo `UnmappableCharacterException` với US-ASCII encoder? (3) Nếu nhận `E2 82` rồi `AC` ở hai lần đọc khác nhau, vì sao phải giữ byte dư và không đặt `endOfInput=true` ở lần đầu?

**Điểm cần nhớ:** `REPORT` giúp dữ liệu lỗi trở nên quan sát và xử lý được. Với phương thức một lần, xử lý `CharacterCodingException`; với API từng bước, xử lý `CoderResult`, trạng thái buffer và vòng đời `decode/encode → flush → reset` đúng cách.