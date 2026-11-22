# Lỗi mojibake khi encode và decode không cùng charset

## 1. Mojibake là gì?

**Mojibake** là hiện tượng văn bản bị hiển thị thành những ký tự sai, lạ hoặc khó đọc vì **dữ liệu byte được giải mã (decode) bằng charset khác với charset đã dùng để mã hóa (encode)**, hoặc vì một bước chuyển đổi trung gian sử dụng charset không phù hợp.

Ví dụ điển hình:

- Dữ liệu đúng: `café`.
- Mã hóa theo UTF-8: byte `63 61 66 C3 A9`.
- Giải mã nhầm toàn bộ byte bằng ISO-8859-1: hiển thị `cafÃ©`.
- Giải mã **đúng** bằng UTF-8: hiển thị `café`.

Trong chủ đề Java I/O, điều cần ghi nhớ là **String trong bộ nhớ và byte trên đĩa/mạng nằm ở hai tầng khác nhau**. Charset quyết định cách chuyển qua lại giữa hai tầng.

~~~text
String "café"
    |
    | encode UTF-8
    v
Bytes: 63 61 66 C3 A9
    |
    +--- decode UTF-8 --------> "café"   (đúng)
    |
    +--- decode ISO-8859-1 ---> "cafÃ©" (mojibake)
~~~

Từ “mojibake” mô tả **triệu chứng chữ bị sai**, không phải tên của một charset hay một định dạng file riêng. Một văn bản có dấu tiếng Việt biến thành `Ã`, `Â`, `áº`, `á»`... là dấu hiệu thường gặp, nhưng **không thể kết luận chính xác lỗi chỉ từ vẻ ngoài của vài ký tự**.

Mojibake khác với lỗi font: nếu chuỗi ký tự bên trong đã sai vì decode sai, thay font thường không chữa được. Nếu code point đúng nhưng font thiếu glyph, vấn đề thuộc khâu hiển thị; cần kiểm tra để phân biệt.

## 2. Encode, decode và charset phải tương thích

**Encode** là chuyển ký tự Unicode thành byte theo charset; **decode** là chuyển byte thành ký tự theo charset.

Ví dụ Unicode code point của `é` là U+00E9:

| Charset | Byte biểu diễn `é` |
| --- | --- |
| UTF-8 | `C3 A9` |
| ISO-8859-1 | `E9` |
| UTF-16BE | `00 E9` |
| UTF-16LE | `E9 00` |

Một byte có thể mang nghĩa khác tùy charset. Khi decoder ISO-8859-1 nhận `C3 A9`, nó giải thích thành hai ký tự U+00C3 (`Ã`) và U+00A9 (`©`). Khi decoder UTF-8 nhận đúng hai byte đó, nó tạo một code point U+00E9 (`é`). Đây là cơ chế cụ thể đằng sau `é → Ã©`.

**Không có “charset của Java String” theo nghĩa charset file**: String là mô hình ký tự Unicode trong Java. Khi gọi `getBytes(charset)` để đưa String ra file/mạng, hoặc `new String(bytes, charset)` để đọc vào, ta mới chọn cách biến đổi. Java `char` là đơn vị mã UTF-16; `String.length()` đếm đơn vị UTF-16, không phải số byte UTF-8.

Cùng một thông điệp phải có **hợp đồng thống nhất**:

~~~text
Bên ghi                   Bên đọc
String --encode UTF-8--> Bytes --decode UTF-8--> String
~~~

Nếu bên ghi UTF-8 và bên đọc ISO-8859-1 hoặc Windows-1252, dữ liệu ký tự có thể sai dù các byte trong file hoặc gói tin vẫn nguyên vẹn. Nếu bên ghi ISO-8859-1 còn bên đọc UTF-8, byte như `E9` không hợp lệ dưới dạng một ký tự UTF-8 độc lập; decoder có thể báo lỗi hoặc sinh ký tự thay thế tùy API/chính sách.

**Chú ý:** Charset không phải định dạng file. JSON, CSV, XML, text log có quy tắc cú pháp riêng, đồng thời cần encoding để biến byte thành ký tự. Đọc đúng charset vẫn chưa tương đương parse đúng dữ liệu.

## 3. Ví dụ Java 17: tự tạo mojibake và phục hồi khi còn đủ thông tin

Tạo file **MojibakeDemo.java** (lưu mã nguồn dưới UTF-8):

~~~java
import java.nio.charset.StandardCharsets;
import java.util.Arrays;
import java.util.HexFormat;

public class MojibakeDemo {
    public static void main(String[] args) {
        String original = "café";
        byte[] bytes = original.getBytes(StandardCharsets.UTF_8);

        String correct = new String(bytes, StandardCharsets.UTF_8);
        String wrong = new String(bytes, StandardCharsets.ISO_8859_1);

        // Chỉ khả thi vì mapping ISO-8859-1 ở bước sai
        // vẫn giữ được giá trị của từng byte và String chưa bị sửa.
        byte[] recoveredBytes =
                wrong.getBytes(StandardCharsets.ISO_8859_1);
        String recovered =
                new String(recoveredBytes, StandardCharsets.UTF_8);

        System.out.println("utf8Hex=" + HexFormat.of().formatHex(bytes));
        System.out.println("correct=" + correct);
        System.out.println("wrong=" + wrong);
        System.out.println("recovered=" + recovered);
        System.out.println("sameBytes=" + Arrays.equals(bytes, recoveredBytes));
    }
}
~~~

Biên dịch và chạy với JDK 17 trở lên:

~~~bash
javac -encoding UTF-8 MojibakeDemo.java
java MojibakeDemo
~~~

Kết quả khi terminal hiển thị Unicode đúng:

~~~text
utf8Hex=636166c3a9
correct=café
wrong=cafÃ©
recovered=café
sameBytes=true
~~~

Giải thích từng bước:

1. `getBytes(UTF_8)` mã hóa `café` thành `63 61 66 C3 A9`.
2. `new String(bytes, UTF_8)` hiểu `C3 A9` là một ký tự `é`.
3. `new String(bytes, ISO_8859_1)` hiểu `C3` và `A9` là hai ký tự `Ã©`: mojibake.
4. Vì ISO-8859-1 ánh xạ lần lượt mọi giá trị byte 0–255 thành code point tương ứng, `wrong.getBytes(ISO_8859_1)` tái tạo được byte ban đầu.
5. Giải mã byte khôi phục bằng UTF-8 cho lại `café`. Mệnh đề `sameBytes=true` xác nhận điều này trong ví dụ.

**Không được tổng quát hóa thao tác sửa ở bước 4 cho mọi chuỗi bị lỗi.** Nó chỉ đúng khi biết chính xác lịch sử biến đổi và các byte vẫn được bảo toàn. Nếu hệ thống đã thay ký tự bằng `?`, ký tự thay thế U+FFFD (`�`), xóa dấu, chuẩn hóa hoặc thay đổi chuỗi, phép encode ngược có thể không khôi phục byte gốc.

Lưu ý thêm: in ra terminal cũng là một bước xuất ký tự ra byte. Nếu console chọn encoding/font không phù hợp, nội dung terminal có thể trông sai dù String trong Java hoàn toàn đúng. Nên kiểm tra byte hex và kết quả `equals` bên cạnh hình thức hiển thị.

## 4. Mojibake xuất hiện ở đâu trong luồng Java I/O?

Các lỗi thường xuất hiện tại **ranh giới String ↔ byte**, đặc biệt nếu một bên dùng charset ngầm định:

~~~text
Java String
   -> Writer / OutputStreamWriter / getBytes(charset)
   -> byte trên file, network, queue, DB driver
   -> Reader / InputStreamReader / new String(bytes, charset)
   -> Java String
   -> logger / terminal / browser
~~~

Nếu file ghi UTF-8 nhưng đọc lại bằng charset khác:

~~~java
// Mảnh code trong phương thức đã có Path path, xử lý IOException.
Files.writeString(path, "café", StandardCharsets.UTF_8);

String correct = Files.readString(path, StandardCharsets.UTF_8);
String wrong = Files.readString(path, StandardCharsets.ISO_8859_1);
~~~

`correct` chứa `café`, `wrong` chứa `cafÃ©`. Phương thức `readString` chỉ giải mã file, không tự phát hiện file đã được tạo bằng charset nào.

Đối với stream, đặt charset ở đúng cầu nối:

~~~java
// Mảnh code có InputStream input và Reader đóng theo phạm vi sử dụng.
try (var reader = new java.io.InputStreamReader(
        input, StandardCharsets.UTF_8)) {
    // Đọc các ký tự từ reader.
}
~~~

Chiều ghi dùng `OutputStreamWriter(output, StandardCharsets.UTF_8)`. Nếu làm việc hoàn toàn với byte để copy file, hãy dùng `InputStream`/`OutputStream` trực tiếp; không chuyển đổi sang String.

Với giao tiếp HTTP, phải kiểm tra `Content-Type`, tham số `charset` khi áp dụng, các quy tắc của media type và cách framework/SDK giải mã. Với CSV/export/import và các hệ thống cũ, cấu hình charset của bên phát và bên đọc phải nhất quán. **Đừng tự gán ISO-8859-1 hoặc UTF-8 chỉ vì hệ thống “thường dùng” charset đó.**

## 5. Các dấu hiệu và giới hạn của việc suy đoán lỗi

| Triệu chứng | Khả năng có thể xảy ra | Cần kiểm tra |
| --- | --- | --- |
| `é` thành `Ã©`; `à` thành `Ã ` | UTF-8 bị hiểu thành charset Latin-1/Windows-1252 | Byte nguồn, charset tại bước decode |
| Một số ký tự thành `�` | Decoder đã thay chuỗi byte lỗi bằng U+FFFD | Byte trước decode; chính sách xử lý lỗi |
| Chữ không hỗ trợ thành `?` | Encoder thay ký tự không biểu diễn được bằng `?` | Charset lúc encode và byte `3F` |
| Ký tự đầu file là `ï»¿` | BOM UTF-8 bị hiểu như ký tự Latin-1 | Ba byte đầu `EF BB BF`, chính sách BOM |
| Đúng trong file, sai trên terminal | Encoding hoặc font của console | Byte thực tế và String trước lúc in |
| Chữ đúng nhưng dấu hiển thị/ghép bất thường | Có thể là normalization, font/rendering hoặc thứ tự dấu | Code point thực tế, Unicode normalization |

Bảng trên là **manh mối chẩn đoán**, không phải bằng chứng quyết định: nhiều chuỗi lỗi khác nhau có thể có biểu hiện giống nhau. Ví dụ `Ã©` có thể đã được lưu *như nội dung thật* bởi một hệ thống trước đó; khi đó file UTF-8 hiện tại giải mã đúng nhưng bản thân văn bản đã bị làm sai từ bước trước.

**Mojibake và dữ liệu bị mất là hai vấn đề khác nhau:**

- Nếu byte gốc còn nguyên ở file/log/protocol, thường có thể đọc lại bằng charset đúng.
- Nếu chỉ còn String `cafÃ©` nhưng biết quá trình decode nhầm ISO-8859-1, đôi khi có thể tạo lại byte như ví dụ.
- Nếu hệ thống đã thay thế byte/ký tự không biểu diễn được bằng `?` hoặc `�`, nhiều giá trị ban đầu có thể rơi vào cùng một ký tự thay thế; việc phục hồi chính xác thường không thể bảo đảm mà không có bản gốc.
- Nếu dữ liệu đã trải qua nhiều lần encode/decode sai, cần dựng lại *từng bước* trước khi thử sửa; áp dụng công thức chung một cách mù quáng dễ làm hỏng dữ liệu lần nữa.

## 6. Ví dụ về mất dữ liệu: ký tự không nằm trong charset đích

Dùng US-ASCII để mã hóa `é` là sai nếu cần giữ nguyên dấu, vì US-ASCII không biểu diễn được code point đó. Một số API tiện lợi có thể dùng byte thay thế.

~~~java
// Mảnh code minh họa; StandardCharsets đã được import.
String original = "é";
byte[] bytes = original.getBytes(StandardCharsets.US_ASCII);
String after = new String(bytes, StandardCharsets.US_ASCII);

System.out.println(java.util.HexFormat.of().formatHex(bytes));
System.out.println(after);
~~~

Kết quả mặc định của `String.getBytes(StandardCharsets.US_ASCII)` với ký tự không biểu diễn được:

~~~text
3f
?
~~~

Byte `3F` biểu diễn dấu hỏi `?`. Không thể biết ký tự ban đầu là `é`, `€` hay một ký tự khác chỉ từ byte `3F`. Đây là **mất mát ở bước encode**, khác với trường hợp byte UTF-8 còn nguyên nhưng bị decode sai.

Khi cần **phát hiện** thay vì âm thầm thay thế, dùng `CharsetEncoder`/`CharsetDecoder` với `CodingErrorAction.REPORT`.

Tạo **StrictDecodeDemo.java**:

~~~java
import java.nio.ByteBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;

public class StrictDecodeDemo {
    public static void main(String[] args) {
        // E9 là 'é' trong ISO-8859-1 nhưng không tự tạo
        // thành một ký tự UTF-8 hợp lệ khi đứng một mình.
        byte[] sourceBytes = {(byte) 0xE9};

        var decoder = StandardCharsets.UTF_8.newDecoder()
                .onMalformedInput(CodingErrorAction.REPORT)
                .onUnmappableCharacter(CodingErrorAction.REPORT);
        try {
            decoder.decode(ByteBuffer.wrap(sourceBytes));
            System.out.println("valid UTF-8");
        } catch (CharacterCodingException exception) {
            System.out.println("invalid UTF-8");
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 StrictDecodeDemo.java
java StrictDecodeDemo
~~~

Stdout:

~~~text
invalid UTF-8
~~~

Một byte `E9` không đủ tạo chuỗi UTF-8 hợp lệ; decoder báo lỗi. Thay vì tiếp tục xử lý dữ liệu bị thay thế ký tự, cách này cho phép chương trình dừng và báo sai hợp đồng encoding sớm.

**Lưu ý:** kiểm tra UTF-8 hợp lệ chỉ trả lời “có giải mã được theo UTF-8 hay không”. Nó không chứng minh file chắc chắn là văn bản, vì dữ liệu nhị phân bất kỳ có thể tình cờ chứa byte UTF-8 hợp lệ.

## 7. Double encoding: vì sao đôi khi xuất hiện nhiều tầng ký tự sai?

Mojibake có thể bị **lưu lại như một String** rồi encode thành file UTF-8 mới. Khi đó file mới là UTF-8 hợp lệ, nhưng nội dung lại là các ký tự sai của lần decode trước.

Ví dụ một ký tự `é`:

~~~text
Bản gốc:           é
UTF-8 gốc:         C3 A9
Decode nhầm Latin-1: Ã©
Lưu "Ã©" bằng UTF-8: C3 83 C2 A9
Đọc file mới bằng UTF-8: Ã©  (vẫn sai về ngữ nghĩa)
~~~

Nếu lại tiếp tục diễn giải sai những byte UTF-8 đó, chuỗi có thể méo thêm một tầng nữa. Đây là lý do có những log hoặc bản export chứa các cụm `Ãƒ`, `Â` lặp lại. Mỗi tầng xử lý sai cần được xác định từ log/byte thực tế; chỉ đổi charset của bước đọc cuối sẽ không tự sửa nội dung đã lưu sai ở bước trước.

Khi đọc một file xuất hiện `cafÃ©` nhưng byte của file hiện tại là mã hóa UTF-8 của chính chuỗi `cafÃ©`, ứng dụng đã đọc **đúng** byte hiện tại. Lỗi xảy ra trước khi lưu, nên cần truy về thời điểm String bị tạo từ byte bằng charset sai.

## 8. Quy trình điều tra và sửa lỗi có kiểm soát

**Bước 1 — Lưu lại byte gốc.** Trước khi sửa, giữ file gốc hoặc bản sao bất biến. Tránh mở rồi Save bằng text editor với charset phỏng đoán. Với dữ liệu mạng, lưu payload byte hoặc hex dump tại ranh giới I/O phù hợp.

**Bước 2 — Xác định nơi text còn đúng.** So sánh String trước encode, byte sau encode, byte trước decode, String sau decode, và cuối cùng là nơi hiển thị. Nếu String đúng trước `System.out.println` nhưng terminal sai, đừng sửa logic đọc file vội.

**Bước 3 — Đo byte và charset thực sự.** Dùng `HexFormat` trong Java 17 để xem byte; xác minh `StandardCharsets.UTF_8`, `ISO_8859_1`, charset do API/framework sử dụng, HTTP `charset`, thiết lập xuất CSV, decoder/encoder của bên tích hợp. Không dùng `String.length()` làm số byte.

**Bước 4 — Tái hiện với dữ liệu nhỏ.** Một từ như `café`, `cà phê` hoặc tên có dấu đủ giúp tách lỗi. Đối chiếu cả chuỗi hiển thị và hex của byte trước/sau mỗi bước.

**Bước 5 — Sửa tại ranh giới sai.** Nếu file UTF-8 bị đọc như Latin-1, thay lựa chọn charset ở *bước đọc*. Nếu nguồn tạo byte sai, sửa encoder/thiết lập export. Nếu file đã chứa String mojibake được lưu dưới UTF-8, phục hồi từ bản gốc hoặc xác minh lịch sử biến đổi trước khi lập công cụ migration.

**Bước 6 — Kiểm chứng và phòng ngừa.** Kiểm tra round-trip ký tự tiếng Việt, dấu, ký tự ngoài ASCII và trường hợp malformed input. So sánh byte khi yêu cầu không thay đổi dữ liệu; với text, kiểm tra chuỗi Unicode sau parse. Đặt test tích hợp qua đúng luồng (file → service → API → consumer) để bắt mismatch giữa các hệ thống.

Một cách chẩn đoán chủ động trong Java:

~~~java
// Mảnh code khi đã có byte[] payload và String candidate.
String hex = java.util.HexFormat.of().formatHex(payload);
String decoded = new String(payload, StandardCharsets.UTF_8);
boolean same = candidate.equals(decoded);
// Ghi hex/charset vào log kỹ thuật phù hợp, không log dữ liệu nhạy cảm.
~~~

Hex chỉ mô tả byte; nó không tự cho biết byte cần được giải mã bằng charset nào. Khi sản phẩm phải xử lý dữ liệu người dùng, cần cân nhắc không ghi nội dung cá nhân hoặc payload nhạy cảm vào log.

## 9. Thiết kế ứng dụng tránh mojibake

- **Chỉ định charset ở điểm chuyển đổi.** Với text UTF-8 dùng `StandardCharsets.UTF_8` cùng `Files.readString`, `Files.writeString`, `InputStreamReader`, `OutputStreamWriter` hoặc `String.getBytes`/`new String`.
- **Định nghĩa rõ encoding trong hợp đồng tích hợp.** File CSV, email, API HTTP, queue message, database import/export cần thỏa thuận charset và metadata tương ứng.
- **Phân biệt text và binary.** Đối với file ảnh, ZIP hoặc payload nhị phân, truyền byte trực tiếp; đừng dùng String làm container tùy ý cho byte.
- **Ưu tiên Unicode xuyên suốt.** Giữ String ở tầng nghiệp vụ, chỉ encode khi ra I/O và chỉ decode khi vào I/O; tránh encode/decode thừa không có mục đích.
- **Không phụ thuộc charset mặc định một cách vô thức.** Java hiện đại có thay đổi về mặc định giữa phiên bản và môi trường; charset được chỉ định rõ sẽ dễ kiểm soát hơn.
- **Báo lỗi khi yêu cầu bảo toàn dữ liệu.** Dùng `CharsetDecoder`/`CharsetEncoder` với `CodingErrorAction.REPORT` khi cần từ chối đầu vào sai hoặc ký tự không biểu diễn được.
- **Thử với dữ liệu đa ngôn ngữ.** Đừng chỉ test ASCII: ASCII có cùng byte trong UTF-8 và nhiều charset khác, nên không phát hiện mismatch; thêm tiếng Việt, ký tự có dấu và trường hợp không thuộc charset legacy.
- **Tránh “sửa” dữ liệu bằng phép chuyển đổi mù.** Trước khi encode lại một String sai, xác minh charset gốc, bước hỏng, khả năng đảo ngược và ảnh hưởng đến các bản ghi vốn đã đúng.

## 10. Bài tập tự kiểm tra

**Câu 1.** Dữ liệu đúng là `café`; sau khi nhận được `cafÃ©` thì có thể khẳng định bộ dữ liệu gốc đã mất không?  
**Đáp án:** Chưa. Nếu byte UTF-8 `63 61 66 C3 A9` còn nguyên và chỉ decode nhầm ISO-8859-1, có thể decode lại đúng. Nếu ký tự đã bị thay thế và byte gốc không còn thì có thể đã mất thông tin.

**Câu 2.** Vì sao `new String(bytes, StandardCharsets.UTF_8)` chỉ đúng khi biết `bytes` là UTF-8?  
**Đáp án:** Vì decoder diễn giải byte theo quy tắc UTF-8. Nếu byte được encode bằng charset khác, kết quả có thể sai hoặc phát sinh lỗi; constructor không tự tìm ra charset gốc.

**Câu 3.** Ký tự `é` được encode bằng US-ASCII thành `?`. Encode lại `?` bằng UTF-8 có sửa được không?  
**Đáp án:** Không. Ký tự gốc đã bị thay thế thành `?` ở bước encode đầu; UTF-8 chỉ mã hóa đúng ký tự `?` hiện có.

**Câu 4.** File UTF-8 hiện tại chứa chuỗi `cafÃ©`. Đổi `readString(path, UTF_8)` thành `readString(path, ISO_8859_1)` có luôn sửa được không?  
**Đáp án:** Không. File có thể đã lưu đúng byte UTF-8 của chuỗi mojibake từ một bước trước. Phải lần theo lịch sử dữ liệu, xác định byte gốc và charset của từng bước.

**Câu 5.** Vì sao nên kiểm tra hex byte thay vì chỉ nhìn chữ hiển thị?  
**Đáp án:** Console/font có thể khiến chữ trông sai ngay cả khi String đúng; hex cho biết byte thực tế đã đi qua ranh giới I/O, giúp xác định encode hay decode sai.

**Câu 6.** Khi cần từ chối byte sai UTF-8 thay vì hiển thị `�`, nên dùng API nào?  
**Đáp án:** `CharsetDecoder` với `CodingErrorAction.REPORT`, rồi xử lý `CharacterCodingException`.

**Kết luận học tập:** Mojibake thường xuất hiện khi bên ghi và bên đọc **không dùng cùng charset**, hoặc vì một khâu trung gian đã lưu lại String bị giải mã sai. Muốn sửa chính xác, phải phân biệt **byte gốc**, **String đã giải mã**, **charset ở từng ranh giới I/O** và khả năng **mất dữ liệu do thay thế ký tự**. Với Java, ưu tiên charset tường minh và kiểm tra byte/round-trip trước khi can thiệp dữ liệu thực tế.
