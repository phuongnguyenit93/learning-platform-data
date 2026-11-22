# Dữ liệu sai mã, ký tự thay thế và mất thông tin trong Java

## Mục tiêu bài học

Sau bài này, bạn có thể phân biệt dữ liệu byte không hợp lệ, dữ liệu bị đọc bằng sai bảng mã và dữ liệu đã mất ký tự trong lúc chuyển đổi; xác định thời điểm Java dùng ký tự thay thế; kiểm tra lỗi bằng `CharsetDecoder`/`CharsetEncoder`; và chọn cách xử lý để không âm thầm làm hỏng dữ liệu.

## 1. Từ byte đến chuỗi: lỗi xuất hiện ở đâu?

`byte[]` là các byte thô. `String` trong Java biểu diễn văn bản Unicode bằng các đơn vị mã UTF-16; nó không tự lưu thông tin rằng dữ liệu gốc đến từ UTF-8, UTF-16, ISO-8859-1 hay bảng mã nào khác. Khi trao đổi với tệp, mạng, cơ sở dữ liệu hoặc API, chương trình phải **giải mã** byte thành ký tự và **mã hóa** ký tự trở lại byte.

```text
byte[] --[giải mã bằng charset]--> String --[xử lý văn bản]-->
String --[mã hóa bằng charset]--> byte[]
```

Hai bên phải thống nhất bảng mã và tuân thủ quy tắc của bảng mã đó:

- **Malformed input (dữ liệu sai mã / cấu trúc mã không hợp lệ):** dãy byte không phải chuỗi byte hợp lệ theo charset đang dùng, chẳng hạn byte mở đầu UTF-8 thiếu byte tiếp theo; hoặc chuỗi Java chứa surrogate lẻ khi cần mã hóa Unicode.
- **Unmappable character (ký tự không biểu diễn được):** ký tự hợp lệ nhưng bảng mã đích không có biểu diễn tương ứng, chẳng hạn `€` hoặc `á` khi mã hóa bằng US-ASCII. Một số decoder cũng có thể báo unmappable khi charset không ánh xạ một chuỗi byte hợp lệ sang ký tự.
- **Mojibake (chữ bị sai do nhầm charset):** byte hợp lệ nhưng được giải mã theo charset khác với charset đã dùng để tạo chúng; kết quả vẫn là ký tự Unicode hợp lệ nhưng đọc thành chữ rác, ví dụ `café` thành `cafÃ©`.
- **Mất thông tin (lossy conversion):** byte hoặc ký tự gốc bị thay bằng ký tự khác, bỏ qua, hay bị biến đổi không thể đảo ngược. Dấu `�` (U+FFFD, REPLACEMENT CHARACTER) và dấu `?` là hai triệu chứng thường gặp, nhưng bản thân sự xuất hiện của chúng chưa chứng minh dữ liệu đã hỏng.

Cần phân biệt **byte không hợp lệ** với **ký tự trông có vẻ sai**. Một dãy byte có thể hợp lệ trong ISO-8859-1 nhưng không hợp lệ trong UTF-8; và văn bản `cafÃ©` không chứa byte UTF-8 sai cấu trúc sau khi đã thành `String`.

## 2. Những biểu hiện thường gặp

| Biểu hiện | Nguyên nhân thường gặp | Hướng kiểm tra |
| --- | --- | --- |
| `�` xuất hiện giữa câu | Decoder thay byte lỗi bằng U+FFFD; cũng có thể đó là ký tự có sẵn trong nguồn | Giữ byte gốc; xác minh charset; giải mã với chế độ `REPORT` |
| `?` thay chữ có dấu hoặc emoji | Encoder không biểu diễn được ký tự và dùng byte thay thế, thường là `0x3F` trong ASCII | Kiểm tra charset khi ghi và kiểm tra encoder với `REPORT` |
| `Ã©`, `Â`, `â€™` hoặc chữ rác nhưng không có `�` | Đọc byte bằng sai charset, hoặc mã hóa/giải mã nhiều lần | Truy nguồn charset ở từng bước, so sánh byte hex |
| Văn bản bị mất ký tự hoặc bị dính chữ | Hệ thống bỏ qua lỗi bằng `IGNORE`, cắt byte, cắt chuỗi hoặc xử lý stream sai | Kiểm tra chiều dài và ranh giới dữ liệu; tránh `IGNORE` |
| Ký tự đầu văn bản bất thường | BOM không được xử lý đúng hoặc bị hiểu như nội dung | Kiểm tra byte đầu, định dạng tệp và chính sách BOM |
| Một vài chữ giống nhau nhưng so sánh không bằng | Khác dãy code point Unicode (ví dụ ký tự dựng sẵn và tổ hợp) | In code point; xem xét chuẩn hóa Unicode khi nghiệp vụ cần |

Ví dụ byte UTF-8 của `é` là `C3 A9`. Nếu hiểu chúng lần lượt là hai ký tự ISO-8859-1, ta nhận được `Ã©`. Đây là **sai diễn giải byte**, không phải một lỗi cú pháp UTF-8 đã được decoder phát hiện.

## 3. Một dãy UTF-8 sai mã trông như thế nào?

UTF-8 mã hóa một code point Unicode bằng một đến bốn byte. Byte tiếp diễn bắt đầu bằng bit `10`; một byte mở đầu nhiều byte phải được theo sau bởi đúng số byte tiếp diễn, đồng thời phải tuân thủ các giới hạn giá trị Unicode.

Ví dụ:

- `41` là ký tự `A` hợp lệ.
- `C3 A9` là `é` hợp lệ.
- `C3 28` **không hợp lệ**: `C3` cần một byte tiếp diễn nhưng `28` là dấu `(`, không có dạng `10xxxxxx`.
- `E2 82` **bị cắt cụt**: chưa đủ byte để hoàn thành chuỗi ba byte.
- Byte tiếp diễn đứng một mình như `80`, mã hóa quá dài (overlong), mã hóa vùng surrogate hoặc code point vượt `U+10FFFF` đều không phải UTF-8 hợp lệ.

Decoder có thể báo lỗi hoặc áp dụng một chính sách xử lý. Khi chọn **REPLACE**, decoder thay phần dữ liệu gây lỗi bằng chuỗi thay thế của decoder, phổ biến là U+FFFD với UTF-8; số ký tự `�` xuất hiện phụ thuộc cách phân đoạn lỗi, nên không dùng số dấu `�` để suy ra chính xác bao nhiêu byte đã hỏng.

Một `String` đã chứa U+FFFD có thể được mã hóa UTF-8 hoàn toàn hợp lệ thành ba byte `EF BF BD`. Việc mã hóa lại chuỗi này không khôi phục được byte lỗi ban đầu, và kiểm tra tính hợp lệ UTF-8 của byte vừa mã hóa **không thể chứng minh dữ liệu gốc chưa từng bị mất**.

## 4. Hành vi mặc định và ba chính sách xử lý lỗi

Trong Java:

- `new String(bytes, StandardCharsets.UTF_8)` chuyển byte thành văn bản và **thay thế** các đoạn byte không hợp lệ; vì vậy có thể không ném ngoại lệ.
- `text.getBytes(StandardCharsets.US_ASCII)` thay các ký tự không biểu diễn được bằng byte thay thế của charset, nên có thể trả về mảng byte dù văn bản đã mất ký tự.
- `CharsetDecoder` tạo từ `charset.newDecoder()` và `CharsetEncoder` tạo từ `charset.newEncoder()` cho phép đặt hai chính sách riêng bằng `onMalformedInput(...)` và `onUnmappableCharacter(...)`.

| `CodingErrorAction` | Hành vi | Dùng khi nào? |
| --- | --- | --- |
| `REPORT` | Báo lỗi thay vì tự sửa dữ liệu | Nhập liệu cần toàn vẹn, dữ liệu định danh, giao thức, kiểm thử |
| `REPLACE` | Dùng chuỗi/byte thay thế | Hiển thị nội dung bị lỗi khi chấp nhận mất mát và có ghi nhận |
| `IGNORE` | Bỏ qua phần lỗi | Rất hiếm khi hợp lý: có thể xóa dữ liệu mà không thấy dấu vết |

`REPORT` là lựa chọn an toàn khi **bắt buộc giữ nguyên nội dung**. `REPLACE` phù hợp hơn với mục tiêu hiển thị dễ đọc trong một luồng dữ liệu vốn đã có lỗi, với điều kiện không dùng kết quả đó làm bản gốc để lưu đè.

Lưu ý: hành vi thay thế của decoder và encoder không giống nhau. Decoder UTF-8 thường sinh `�` (Unicode U+FFFD). Encoder US-ASCII thường sinh byte `3F`, khi đọc lại thành ký tự `?`. `?` vốn có thể là ký tự hợp lệ do người dùng nhập, vì vậy chỉ nhìn `String` sau chuyển đổi không đủ phân biệt nguyên nhân.

## 5. Ví dụ Java 17+: phát hiện thay vì âm thầm mất dữ liệu

Lưu tệp `CharsetLossDemo.java` với mã nguồn UTF-8:

```java
import java.nio.ByteBuffer;
import java.nio.CharBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;

public class CharsetLossDemo {
    public static void main(String[] args) {
        byte[] invalidUtf8 = {0x43, 0x61, (byte) 0xC3, 0x28};
        System.out.println("Giải mã thay thế: "
                + new String(invalidUtf8, StandardCharsets.UTF_8));

        try {
            String strict = StandardCharsets.UTF_8.newDecoder()
                    .onMalformedInput(CodingErrorAction.REPORT)
                    .onUnmappableCharacter(CodingErrorAction.REPORT)
                    .decode(ByteBuffer.wrap(invalidUtf8))
                    .toString();
            System.out.println("UTF-8 hợp lệ: " + strict);
        } catch (CharacterCodingException e) {
            System.out.println("Báo lỗi: UTF-8 không hợp lệ");
        }

        String original = "Giá €";
        byte[] ascii = original.getBytes(StandardCharsets.US_ASCII);
        System.out.println("Mã hóa ASCII thay thế: "
                + new String(ascii, StandardCharsets.US_ASCII));

        try {
            StandardCharsets.US_ASCII.newEncoder()
                    .onMalformedInput(CodingErrorAction.REPORT)
                    .onUnmappableCharacter(CodingErrorAction.REPORT)
                    .encode(CharBuffer.wrap(original));
            System.out.println("ASCII biểu diễn được tất cả ký tự");
        } catch (CharacterCodingException e) {
            System.out.println("Báo lỗi: ASCII không biểu diễn được ký tự");
        }
    }
}
```

Biên dịch và chạy trong terminal có hỗ trợ UTF-8:

```bash
javac -encoding UTF-8 CharsetLossDemo.java
java CharsetLossDemo
```

Kết quả (dấu `�` là một ký tự Unicode, không phải dấu `?`):

```text
Giải mã thay thế: Ca�(
Báo lỗi: UTF-8 không hợp lệ
Mã hóa ASCII thay thế: Gi? ?
Báo lỗi: ASCII không biểu diễn được ký tự
```

**Giải thích:** hai byte đầu `43 61` thành `Ca`. Byte `C3` không có byte tiếp diễn hợp lệ nên constructor chuỗi thêm U+FFFD; `28` vẫn thành `(`. Decoder có `REPORT` ném một `CharacterCodingException` (trường hợp này là `MalformedInputException`). Tương tự, ký tự `á` và `€` nằm ngoài US-ASCII; `getBytes(US_ASCII)` thay cả hai bằng `?`, còn encoder nghiêm ngặt báo lỗi unmappable.

Không dùng `try/catch` để tiếp tục lưu bản thay thế như thể không có lỗi. Hãy ghi lại vị trí nguồn, charset mong đợi và loại lỗi; tùy hợp đồng dữ liệu mà yêu cầu nguồn gửi lại, từ chối bản ghi hoặc cách ly dữ liệu hỏng.

## 6. Sai charset nhưng byte vẫn hợp lệ: mojibake

Lưu `MojibakeDemo.java`:

```java
import java.nio.charset.StandardCharsets;

public class MojibakeDemo {
    public static void main(String[] args) {
        byte[] utf8 = "café".getBytes(StandardCharsets.UTF_8);
        String wrong = new String(utf8, StandardCharsets.ISO_8859_1);
        System.out.println("Sai charset: " + wrong);

        String recovered = new String(
                wrong.getBytes(StandardCharsets.ISO_8859_1),
                StandardCharsets.UTF_8);
        System.out.println("Khôi phục: " + recovered);
    }
}
```

```bash
javac -encoding UTF-8 MojibakeDemo.java
java MojibakeDemo
```

```text
Sai charset: cafÃ©
Khôi phục: café
```

Ở đây `wrong` chỉ có các ký tự Unicode hợp lệ. Decoder không thể tự biết tác giả byte vốn dùng UTF-8. Ta khôi phục được **trong tình huống cụ thể này** vì chuỗi sai vẫn giữ trọn từng giá trị byte theo ISO-8859-1 và chưa bị thay thế, cắt hoặc chuẩn hóa.

**Đừng áp dụng công thức đảo charset một cách mù quáng.** Nếu `�`, `?` hoặc thao tác lossy đã thay byte/ký tự gốc; nếu nội dung đã qua nhiều lần chuyển mã; hoặc nếu charset giả định sai, phép đảo không thể phục hồi dữ liệu đáng tin cậy và có thể làm hỏng thêm. Muốn sửa chính xác, ưu tiên quay về byte/tệp/bản ghi nguồn và thông tin charset thực tế.

## 7. Dữ liệu đã mất có phục hồi được không?

Phân biệt ba tình huống:

1. **Còn byte gốc, chưa bị ghi đè:** thường có thể thử giải mã lại đúng charset; dùng decoder `REPORT` để xác nhận tính hợp lệ. Nếu charset không tự mô tả, phải dựa vào metadata, quy định giao thức hoặc nhà cung cấp dữ liệu.
2. **Chỉ còn một `String` bị mojibake nhưng chuyển đổi vừa qua không mất thông tin:** đôi khi đảo chiều được như ví dụ `cafÃ©`, sau khi xác minh nguồn và chuỗi biến đổi.
3. **Byte/ký tự đã bị thay bằng `�`/`?`, bị bỏ qua, cắt mất hoặc ghi đè:** thường không thể suy ra chính xác dữ liệu ban đầu từ kết quả cuối. Cần lấy lại nguồn, bản sao lưu hoặc yêu cầu gửi lại; thuật toán đoán ký tự không bảo đảm toàn vẹn.

`U+FFFD` có thể xuất hiện **hợp lệ** trong tài liệu gốc, cũng như `?` có thể là dấu câu. Vì vậy không nên viết quy tắc kiểu “cứ thấy U+FFFD là xóa” hoặc “đổi mọi `?` thành chữ có dấu”. Nếu cần kiểm soát nhập liệu, hãy xác thực ngay lúc còn giữ mảng byte gốc.

Ngoài encoding, mất thông tin cũng có thể do tự ý chuẩn hóa Unicode, cắt chuỗi theo đơn vị UTF-16, cắt độ dài cột dữ liệu, loại dấu bằng quy tắc nghiệp vụ hoặc chuyển sang charset có miền ký tự nhỏ hơn. Những thao tác này phải được coi là chuyển đổi có chủ ý và được kiểm thử riêng, không gộp với xử lý byte sai mã.

## 8. Chẩn đoán lỗi từng bước

Khi thấy chữ lỗi, kiểm tra theo thứ tự sau:

1. **Khoanh đúng ranh giới gặp lỗi:** tệp đọc vào, byte response HTTP, thông điệp queue, bản ghi database, bước chuyển đổi CSV/JSON, ghi log hay xuất tệp. Đừng chỉ sửa giao diện nếu byte đã hỏng trước đó.
2. **Giữ nguyên byte trước khi giải mã:** lưu mẫu nhỏ ở dạng hex hoặc tệp nhị phân có kiểm soát; tránh đưa dữ liệu nhạy cảm vào log. Với `43 61 C3 28`, kiểm tra được chính xác byte `C3` thiếu continuation.
3. **Xác nhận charset theo hợp đồng:** thông số charset của tệp/API, HTTP Content-Type, cấu hình JDBC, encoding của bên tạo dữ liệu. Không dựa hoàn toàn vào charset mặc định của máy hoặc suy đoán từ vài ký tự.
4. **Giải mã nghiêm ngặt trước khi biến đổi:** `newDecoder().onMalformedInput(REPORT).onUnmappableCharacter(REPORT)` cho biết đầu vào có vi phạm charset đã chọn không. Decoder chỉ kiểm tra **tính hợp lệ với charset đang chọn**; nó không tự phát hiện mọi trường hợp chọn sai charset.
5. **So sánh code point và byte:** Java 17 có `HexFormat.of().formatHex(bytes)` để xem hex; `text.codePoints()` duyệt code point Unicode. `String.length()` đếm đơn vị UTF-16 nên có thể khác số code point, nhất là với emoji.
6. **Kiểm tra khứ hồi nếu phù hợp:** `decode(encode(text))` hoặc `encode(decode(bytes))` có thể giúp phát hiện việc mất thông tin, nhưng không chứng minh charset được chọn đúng; dữ liệu mojibake cũng có thể khứ hồi chính xác với một charset sai.
7. **Truy nguồn lần thay đổi đầu tiên:** nếu dữ liệu đã sai trước khi vào Java, sửa nguồn hoặc lớp tích hợp; nếu bị sai tại Java, thay đúng cấu hình/đoạn đọc-ghi và kiểm thử bằng byte thật.

Ví dụ chẩn đoán nhỏ, dùng như **đoạn mã bên trong một phương thức** (đã có biến `byte[] bytes`):

```java
System.out.println(java.util.HexFormat.of().formatHex(bytes));
String text = new String(bytes, StandardCharsets.UTF_8);
text.codePoints().forEach(cp ->
        System.out.printf("U+%04X ", cp));
System.out.println();
```

Lưu ý cần import `java.nio.charset.StandardCharsets` khi dùng đoạn trên. Hex của byte đầu vào và code point của chuỗi sau giải mã cung cấp **hai bằng chứng khác nhau**; không thể thay thế một bên bằng bên còn lại.

## 9. Đọc và ghi dữ liệu an toàn ở ranh giới I/O

**Đọc tệp:** nếu dữ liệu bắt buộc là UTF-8 hợp lệ, hãy cấu hình decoder báo lỗi trước khi tạo chuỗi. Khi làm việc với stream, dùng một decoder xuyên suốt luồng, chẳng hạn truyền `CharsetDecoder` có `REPORT` vào `InputStreamReader(InputStream, CharsetDecoder)`; xử lý `IOException`/`MalformedInputException` phù hợp. Tránh giải mã từng chunk `byte[]` độc lập vì một ký tự UTF-8 có thể nằm vắt qua ranh giới hai lần đọc.

**Ghi tệp:** đặt charset tường minh khi ghi, ví dụ `Files.writeString(path, text, StandardCharsets.UTF_8)` khi định dạng quy định UTF-8. Nếu phải xuất sang một charset hạn chế, dùng `CharsetEncoder` với `REPORT` để phát hiện ký tự không biểu diễn được trước khi ghi; kiểm soát việc ghi một phần và ghi đè.

**HTTP, JSON, cơ sở dữ liệu:** tuân thủ charset/định dạng đã thỏa thuận tại từng ranh giới. JSON qua các kênh UTF-8 hiện đại cần được xử lý nhất quán; dữ liệu truyền trong body HTTP phải phù hợp Content-Type và cấu hình thực tế. Không chữa lỗi ở frontend bằng các phép `new String(text.getBytes(...), ...)` tùy tiện. Với JDBC, ưu tiên API chuỗi Unicode thích hợp, kiểm tra charset/collation/driver kết nối và đường đi xuất nhập dữ liệu, thay vì áp dụng một charset “chữa cháy” sau truy vấn.

**BOM và Unicode:** BOM là tín hiệu nhận dạng đầu tệp trong một số định dạng; không phải mọi API tự loại bỏ BOM, và UTF-8 không bắt buộc có BOM. Phân biệt U+FEFF đầu chuỗi với dữ liệu bị sai mã, chỉ xử lý theo đặc tả tệp. Khác biệt NFC/NFD là vấn đề chuẩn hóa Unicode, không đồng nghĩa với byte UTF-8 không hợp lệ.

## 10. Sai lầm cần tránh

- Dựa vào `Charset.defaultCharset()` hoặc constructor không truyền charset ở ranh giới trao đổi dữ liệu; môi trường khác nhau có thể dẫn tới diễn giải khác nhau.
- Cho rằng Java luôn ném lỗi khi `new String(bytes, UTF_8)` gặp byte sai: constructor này có thể thay thế mà không báo.
- Dùng `CodingErrorAction.IGNORE` để “làm sạch”: byte lỗi biến mất, vị trí từ ngữ có thể bị nối sai và khó điều tra.
- Lưu lại chuỗi đã chứa dấu thay thế lên dữ liệu nguồn, làm mất cơ hội giải mã lại byte gốc.
- Nhầm `�` với dấu `?` hoặc tự động thay tất cả bằng một ký tự đoán từ ngữ cảnh.
- Coi “không có `�`” hoặc “khứ hồi byte bằng nhau” là bằng chứng chắc chắn charset đúng. Mojibake có thể xảy ra mà không có exception.
- Chia byte stream theo chunk rồi decode từng chunk, hoặc cắt `String` giữa cặp surrogate; cả hai có thể sinh lỗi ở ranh giới.
- Gộp ba công việc khác nhau — xác thực byte, chuyển mã văn bản và chuẩn hóa nội dung — thành một thao tác không có kiểm thử.

## 11. Quy tắc lựa chọn và bài tập tự kiểm tra

| Tình huống | Hành động phù hợp |
| --- | --- |
| Nhận dữ liệu nhị phân được khai báo UTF-8, yêu cầu chính xác tuyệt đối | Giữ byte nguồn, giải mã `REPORT`, từ chối hoặc cách ly khi lỗi |
| Chỉ cần hiển thị thông báo cũ đã hỏng | Có thể `REPLACE`, nhưng ghi nhận và không dùng kết quả thay cho bản gốc |
| Xuất chữ Unicode sang US-ASCII | Kiểm tra `CharsetEncoder` với `REPORT`; đổi định dạng sang UTF-8 hoặc xử lý chuyển tự có chủ đích |
| Thấy `cafÃ©` | Tìm charset tạo byte và charset đã đọc; khôi phục từ byte gốc khi có thể |
| Chỉ còn `?` thay cho chữ gốc | Kiểm tra bản sao lưu/nguồn ban đầu; không giả định có thể khôi phục từ dấu `?` |

Tự luyện tập:

1. Thay dãy byte ví dụ thành `E2 82` và `C3 A9`. Dự đoán trường hợp nào `REPORT` ném lỗi, trường hợp nào cho ra `é`; sau đó chạy kiểm chứng.
2. Thử mã hóa `"Xin chào 👋"` bằng `US_ASCII` và `UTF_8`. Xác định bước nào có nguy cơ mất dữ liệu, rồi kiểm tra lại bằng encoder nghiêm ngặt.
3. Mô phỏng gửi byte UTF-8 nhưng đọc bằng ISO-8859-1. Ghi lại hex gốc, văn bản sai, văn bản được đọc lại đúng; giải thích điều kiện cần để phục hồi.
4. Viết một hàm đọc UTF-8 từ `InputStream` với decoder `REPORT` và kiểm thử trường hợp chuỗi nhiều byte bị chia ở biên buffer.

**Nguyên tắc:** byte gốc và charset theo hợp đồng là điểm tựa để chẩn đoán. Kiểm tra lỗi **trước** khi thay thế hoặc bỏ qua; chỉ chấp nhận biến đổi lossy khi đó là quyết định có chủ đích và đã được kiểm thử.