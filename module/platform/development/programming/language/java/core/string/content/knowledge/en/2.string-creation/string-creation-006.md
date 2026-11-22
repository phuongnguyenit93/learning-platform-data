# Tạo `String` từ `byte[]` với bộ mã ký tự trong Java

Khi nhận dữ liệu từ tệp, mạng, cơ sở dữ liệu hoặc một API, ta thường có một mảng byte (`byte[]`). Để biến dữ liệu đó thành văn bản, Java phải **giải mã các byte theo đúng bộ mã ký tự (charset)** mà bên tạo dữ liệu đã sử dụng. Cách thông dụng, rõ ràng và an toàn về tính nhất quán là `new String(bytes, StandardCharsets.UTF_8)`.

## 1. Phân biệt byte, ký tự và charset

- **`byte[]`** là dãy giá trị 8 bit. Bản thân mảng byte không nói đó là văn bản UTF-8, ảnh, tệp ZIP hay dữ liệu nhị phân khác.
- **Charset** quy định cách ánh xạ giữa chuỗi ký tự Unicode và byte khi *mã hóa* (encode), cũng như cách khôi phục văn bản từ byte khi *giải mã* (decode).
- **`String`** lưu văn bản theo mô hình Unicode của Java. Việc tạo `String` từ byte cần biết charset; không thể suy luận chính xác charset bất kỳ chỉ từ một `byte[]`.
- **UTF-8** là bộ mã phổ biến trên web, API, JSON và nhiều định dạng tệp. Một ký tự có thể chiếm từ 1 đến 4 byte trong UTF-8.

Luồng xử lý:

```text
String -- getBytes(charset) --> byte[]
String <-- new String(bytes, charset) -- byte[]
```

Hai chiều chỉ khôi phục nguyên vẹn khi dùng charset thích hợp và dữ liệu được mã hóa, truyền, giải mã hợp lệ. Không nên nhầm số **byte** với số **ký tự**: chẳng hạn `"é"` (U+00E9) trong UTF-8 chiếm 2 byte nhưng `String.length()` là 1; một emoji ngoài BMP thường chiếm 4 byte UTF-8 và 2 UTF-16 code unit trong `String.length()`.

## 2. API cần dùng

| Cách gọi | Ý nghĩa | Khi nào dùng |
| --- | --- | --- |
| `new String(bytes, StandardCharsets.UTF_8)` | Giải mã toàn bộ mảng bằng UTF-8 | Lựa chọn mặc định khi **đặc tả dữ liệu** xác định UTF-8 |
| `new String(bytes, offset, length, charset)` | Chỉ giải mã `length` byte bắt đầu tại chỉ số `offset` | Khi gói dữ liệu có header hoặc chỉ cần một đoạn byte hoàn chỉnh |
| `new String(bytes, Charset.forName("..."))` | Dùng tên charset được cấu hình hoặc quy định bởi giao thức | Khi giao thức bắt buộc charset khác các hằng thông dụng |
| `new String(bytes)` | Giải mã theo charset mặc định của môi trường Java | Chỉ khi giao thức thật sự quy định sử dụng default charset |
| `text.getBytes(charset)` | Mã hóa `String` trở lại `byte[]` | Khi cần ghi hoặc gửi văn bản ra ngoài |

Import thường dùng:

```java
import java.nio.charset.StandardCharsets;
```

`StandardCharsets.UTF_8`, `US_ASCII`, `ISO_8859_1`, `UTF_16` và `UTF_16LE`/`UTF_16BE` là các charset chuẩn sẵn có. Dùng hằng `Charset` giúp tránh lỗi đánh vần tên và làm hợp đồng mã hóa hiển nhiên hơn so với chuỗi `"UTF-8"`. Constructor `new String(byte[], String charsetName)` cũng tồn tại nhưng có thể báo `UnsupportedEncodingException`; trong ứng dụng hiện đại thường ưu tiên overload nhận `Charset`.

**Điểm mấu chốt:** Đừng chọn UTF-8 chỉ vì nó phổ biến nếu nguồn dữ liệu được khai báo là ISO-8859-1, UTF-16LE hay charset khác; phải làm theo định dạng tệp, header giao thức hoặc hợp đồng API.

## 3. Ví dụ đầy đủ: mã hóa rồi giải mã UTF-8

Lưu tệp sau dưới tên `DecodeBytesDemo.java` với UTF-8:

```java
import java.nio.charset.StandardCharsets;
import java.util.Arrays;

public class DecodeBytesDemo {
    public static void main(String[] args) {
        String original = "Tiếng Việt";
        byte[] payload = original.getBytes(StandardCharsets.UTF_8);

        String decoded = new String(payload, StandardCharsets.UTF_8);
        System.out.println(decoded);
        System.out.println(Arrays.equals(
                payload, decoded.getBytes(StandardCharsets.UTF_8)));

        byte[] packet = {88, 72, 105, 89}; // XHiY trong ASCII
        String middle = new String(
                packet, 1, 2, StandardCharsets.US_ASCII);
        System.out.println(middle);
    }
}
```

Biên dịch và chạy bằng Java 17 trở lên:

```bash
javac -encoding UTF-8 DecodeBytesDemo.java
java DecodeBytesDemo
```

Kết quả:

```text
Tiếng Việt
true
Hi
```

Giải thích:

1. `getBytes(StandardCharsets.UTF_8)` tạo các byte UTF-8 từ văn bản gốc.
2. `new String(payload, StandardCharsets.UTF_8)` diễn giải đúng các byte và khôi phục `"Tiếng Việt"`.
3. `Arrays.equals(...)` so sánh nội dung mảng byte, xác nhận chuyến khứ hồi của dữ liệu hợp lệ ở ví dụ này (không thể dùng `payload.equals(...)` để so sánh nội dung hai mảng).
4. Ở overload có `offset`/`length`, `offset = 1` bắt đầu từ byte thứ hai (`H`), `length = 2` đọc đúng hai byte (`H`, `i`). `length` tính bằng **byte**, không phải số ký tự.

Điều kiện biên của đoạn mảng: `offset >= 0`, `length >= 0` và đoạn `[offset, offset + length)` phải nằm trong mảng; nếu không, Java ném `IndexOutOfBoundsException`. Nếu cắt giữa chừng một chuỗi byte của một ký tự UTF-8 nhiều byte, phần giải mã có thể trở thành dữ liệu lỗi và bị thay thế ký tự.

## 4. Chọn sai charset: lỗi chữ bị biến dạng (mojibake)

Các byte được mã hóa bằng UTF-8 cần được giải mã bằng UTF-8. Cùng một byte có thể được hiểu khác hẳn bởi charset khác:

```java
import java.nio.charset.StandardCharsets;

public class WrongCharsetDemo {
    public static void main(String[] args) {
        byte[] utf8Bytes = "Café".getBytes(StandardCharsets.UTF_8);

        System.out.println(new String(
                utf8Bytes, StandardCharsets.UTF_8));
        System.out.println(new String(
                utf8Bytes, StandardCharsets.ISO_8859_1));
    }
}
```

Kết quả:

```text
Café
CafÃ©
```

`"é"` được biểu diễn bởi hai byte UTF-8 `C3 A9`. Khi hai byte ấy bị đọc như hai ký tự ISO-8859-1 độc lập, kết quả thành `"Ã©"`. Đây là lỗi **giải mã sai charset**, khác với lỗi font hiển thị. Không có phép gọi `new String(...)` nào tự nhận diện đáng tin cậy tất cả các charset; cần tra nguồn gốc hoặc quy định của dữ liệu.

Trong hệ thống thực tế, hãy kiểm tra `Content-Type` và tham số `charset` của giao thức (nếu có), cấu hình định dạng tệp, đặc tả đối tác và bước mã hóa ở phía tạo byte. Không tự giải mã thử nhiều charset rồi coi chuỗi “trông có vẻ đúng” là bằng chứng chắc chắn.

## 5. Byte UTF-8 không hợp lệ: thay thế hay báo lỗi?

Một mảng byte có thể chứa chuỗi UTF-8 không hợp lệ, ví dụ `C3 28`: byte `C3` mở đầu một chuỗi hai byte nhưng `28` không phải byte tiếp nối hợp lệ.

Với constructor `new String(bytes, charset)`, Java **thay thế** chuỗi byte sai định dạng hoặc không ánh xạ được bằng ký tự thay thế của bộ giải mã; với UTF-8 thường là `�` (U+FFFD). Cách này tiện để hiển thị văn bản có lỗi nhưng có thể che mất việc dữ liệu đã hỏng.

Nếu bài toán yêu cầu phát hiện và từ chối byte lỗi (nhập dữ liệu quan trọng, kiểm tra tính toàn vẹn, đọc giao thức nghiêm ngặt), dùng `CharsetDecoder` với `CodingErrorAction.REPORT`:

```java
import java.nio.ByteBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CharsetDecoder;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;

public class StrictDecodeDemo {
    public static void main(String[] args) {
        byte[] invalidUtf8 = {(byte) 0xC3, (byte) 0x28};

        String lenient = new String(
                invalidUtf8, StandardCharsets.UTF_8);
        System.out.println(lenient.equals("\uFFFD("));

        CharsetDecoder strict = StandardCharsets.UTF_8.newDecoder()
                .onMalformedInput(CodingErrorAction.REPORT)
                .onUnmappableCharacter(CodingErrorAction.REPORT);

        try {
            strict.decode(ByteBuffer.wrap(invalidUtf8));
            System.out.println("Dữ liệu hợp lệ");
        } catch (CharacterCodingException e) {
            System.out.println(e.getClass().getSimpleName());
        }
    }
}
```

Chạy `javac -encoding UTF-8 StrictDecodeDemo.java` rồi `java StrictDecodeDemo`, nhận:

```text
true
MalformedInputException
```

`lenient` chứa U+FFFD rồi đến `(` nên phép so sánh trả về `true`. Trái lại, decoder cấu hình `REPORT` ném `MalformedInputException` (lớp con của `CharacterCodingException`). `onUnmappableCharacter(REPORT)` còn xử lý trường hợp byte hợp lệ về mặt cấu trúc nhưng không ánh xạ được trong charset cụ thể. Nếu cần chính sách khác, `CodingErrorAction.REPLACE` chủ động thay thế và `IGNORE` bỏ qua dữ liệu lỗi; việc bỏ qua có nguy cơ mất thông tin.

## 6. Các bẫy thường gặp và cách xử lý

- **Quên chỉ định charset:** `new String(bytes)` phụ thuộc default charset của runtime. Từ Java 18, UTF-8 là mặc định theo JEP 400 trong phần lớn cấu hình, nhưng các phiên bản cũ và tùy chọn runtime có thể khác. Với dữ liệu trao đổi giữa hệ thống, hãy chỉ định charset tường minh.
- **Nhầm dữ liệu nhị phân với văn bản:** ảnh, nội dung nén, dữ liệu mã hóa và byte ngẫu nhiên không nên tùy tiện đưa qua `new String(...)` rồi `getBytes(...)`; phép biến đổi có thể làm thay đổi byte. Dùng `byte[]`/stream để giữ nguyên binary; Base64 chỉ khi cần biểu diễn nhị phân dưới dạng ký tự.
- **Cắt một ký tự nhiều byte:** `new String(bytes, offset, length, UTF_8)` chỉ đúng khi đoạn được chọn là dãy byte mã hóa hoàn chỉnh. Đừng chia các chunk mạng rồi giải mã riêng nếu ranh giới chunk có thể nằm giữa ký tự UTF-8.
- **Giải mã dữ liệu lớn một lần:** với luồng văn bản, dùng `InputStreamReader(input, StandardCharsets.UTF_8)` bọc `BufferedReader` khi phù hợp. Reader xử lý giải mã xuyên ranh giới các lần đọc; với xử lý `ByteBuffer` từng phần, dùng `CharsetDecoder` duy trì trạng thái giữa các chunk.
- **So sánh độ dài sai:** `bytes.length`, `String.length()` và `codePointCount(...)` đo ba thứ khác nhau: byte, đơn vị mã UTF-16 và Unicode code point. Không dùng `String.length()` để tính byte length của giao thức.
- **Tái mã hóa dữ liệu hỏng:** một lần giải mã sai và chứa ký tự thay thế không thể tự khôi phục byte gốc. Sửa từ phía xác định charset/nguồn byte; lưu dữ liệu gốc khi cần chẩn đoán.
- **BOM/tiền tố định dạng:** nếu nguồn có byte order mark hoặc header, xác định đó là phần mã hóa cần xử lý hay một phần giao thức. Không tùy tiện cắt ba byte đầu mọi dữ liệu UTF-8; dữ liệu có thể không có BOM.

## 7. Quy trình áp dụng

1. **Xác minh đó là văn bản** và biết nơi sinh byte (file, HTTP response, database, message queue, v.v.).
2. **Đọc hợp đồng mã hóa**: dùng charset được giao thức/định dạng công bố; ưu tiên `StandardCharsets.UTF_8` khi nguồn thực sự dùng UTF-8.
3. **Lấy đủ dãy byte của đoạn văn bản**, tránh cắt giữa các ký tự mã hóa nhiều byte.
4. **Giải mã:** trường hợp thông thường dùng `new String(bytes, charset)`; khi dữ liệu lỗi phải bị phát hiện, dùng `CharsetDecoder` và `REPORT`.
5. **Kiểm thử với chữ có dấu, ký tự ngoài ASCII và dữ liệu sai:** không chỉ thử văn bản ASCII vì nhiều charset đều cho cùng kết quả ASCII.
6. **Khi ghi/truyền ngược**, sử dụng `getBytes(charset)` cùng charset đã được định nghĩa cho phía nhận; đừng ngầm dùng charset mặc định.

**Ghi nhớ:** `byte[]` chỉ là các byte; **charset là hợp đồng bắt buộc để hiểu chúng thành văn bản**. Đối với byte UTF-8 hợp lệ, `new String(bytes, StandardCharsets.UTF_8)` là cách trực tiếp; đối với dữ liệu không đáng tin cậy cần từ chối byte lỗi, dùng decoder với chính sách `REPORT`.
