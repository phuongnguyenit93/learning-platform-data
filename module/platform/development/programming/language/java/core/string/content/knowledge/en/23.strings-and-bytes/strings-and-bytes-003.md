# Giải mã `byte[]` thành `String` với `Charset` và giải mã một vùng byte

## Mục tiêu

Dữ liệu đọc từ tệp, socket, HTTP hoặc một giao thức nhị phân thường bắt đầu dưới dạng `byte[]`. Để biến các byte này thành văn bản Java, phải **giải mã (decode)** chúng theo đúng bảng mã đã dùng khi tạo dữ liệu. Hai constructor quan trọng là:

```java
new String(byte[] bytes, Charset charset)
new String(byte[] bytes, int offset, int length, Charset charset)
```

Sau bài này, bạn có thể chọn đúng `Charset`, hiểu chính xác `offset` và `length` tính theo **byte**, giải mã một phần mảng mà không tự cắt sai ranh giới ký tự Unicode, đồng thời nhận biết trường hợp dữ liệu bị lỗi.

## 1. Byte không tự mang ý nghĩa là ký tự

Java `String` lưu nội dung văn bản Unicode; `byte[]` lưu dãy byte. Các giá trị byte giống nhau có thể tạo ra văn bản khác nhau tùy bảng mã.

Ví dụ, ký tự `é` có dạng UTF-8 gồm hai byte `C3 A9`, còn trong ISO-8859-1 nó là một byte `E9`. Đọc `E9` như một ký tự UTF-8 hợp lệ sẽ không cho ra chữ `é`. Vì thế, **charset khi giải mã phải khớp charset khi mã hóa**; chỉ định UTF-8 không thể tự sửa dữ liệu vốn được tạo bằng một bảng mã khác.

`Charset` nằm trong package `java.nio.charset`. Với các charset phổ biến, dùng hằng số có sẵn trong `StandardCharsets`:

```java
import java.nio.charset.StandardCharsets;

byte[] bytes = "Chào Java".getBytes(StandardCharsets.UTF_8);
String text = new String(bytes, StandardCharsets.UTF_8);
System.out.println(text);
```

Kết quả:

```text
Chào Java
```

`getBytes(StandardCharsets.UTF_8)` là chiều **mã hóa (encode)** từ `String` sang `byte[]`; `new String(bytes, StandardCharsets.UTF_8)` là chiều **giải mã (decode)** ngược lại. Chúng tạo thành một vòng khứ hồi khi dữ liệu có thể được biểu diễn trong bảng mã đã chọn và không bị sửa đổi trên đường đi.

Nên chỉ định charset rõ ràng, đặc biệt với dữ liệu trao đổi giữa các chương trình. Constructor `new String(bytes)` dùng charset mặc định của môi trường Java đang chạy; không nên dựa vào mặc định khi giao thức hoặc định dạng tệp đã quy định một charset cụ thể.

## 2. Giải mã toàn bộ mảng: `new String(byte[], Charset)`

Cú pháp:

```java
String text = new String(bytes, StandardCharsets.UTF_8);
```

Trong đó:

- `bytes`: mảng byte chứa dữ liệu văn bản đã mã hóa.
- `StandardCharsets.UTF_8`: `Charset` dùng để diễn giải dãy byte.
- `text`: đối tượng `String` mới chứa văn bản đã giải mã.

Constructor giải mã **toàn bộ** mảng từ chỉ số `0` đến `bytes.length - 1`. Nếu mảng rỗng, kết quả là chuỗi rỗng `""`. Với `bytes` hoặc `charset` bằng `null`, lời gọi không hợp lệ và ném `NullPointerException`.

Ví dụ với dữ liệu UTF-8 xác định sẵn:

```java
byte[] encoded = {(byte) 0x43, (byte) 0x61, (byte) 0x66,
                  (byte) 0xC3, (byte) 0xA9};

String decoded = new String(encoded, StandardCharsets.UTF_8);
System.out.println(decoded);
```

Kết quả:

```text
Café
```

Các byte ASCII `43 61 66` cho `Caf`; cặp UTF-8 `C3 A9` cho `é`. Phép ép kiểu `(byte)` ở đây là cần thiết với các literal hex lớn hơn `0x7F`, vì kiểu `byte` trong Java có dấu (miền giá trị từ -128 đến 127). Dấu âm trong phần hiển thị của mảng byte không có nghĩa dữ liệu mã hóa đã thay đổi.

Sau khi constructor hoàn tất, thay đổi các phần tử của mảng đầu vào **không làm đổi nội dung của `String` đã tạo**. Điều này phù hợp với tính bất biến của `String`.

## 3. Giải mã một vùng: `new String(byte[], offset, length, Charset)`

Nhiều bản tin có header, dữ liệu văn bản và phần đuôi nhị phân. Nếu chỉ phần giữa là văn bản, cần giải mã đúng vùng được chỉ định:

```java
String text = new String(bytes, offset, length, StandardCharsets.UTF_8);
```

**Ý nghĩa của các tham số:**

| Tham số | Ý nghĩa |
| --- | --- |
| `bytes` | Toàn bộ mảng byte nguồn |
| `offset` | Chỉ số **byte đầu tiên** của vùng cần đọc, bắt đầu từ 0 |
| `length` | **Số byte** cần giải mã, không phải chỉ số byte cuối |
| `charset` | Bảng mã của phần byte văn bản |

Vùng được chọn có chỉ số trong khoảng **`[offset, offset + length)`**: bao gồm byte tại `offset` và loại trừ byte tại `offset + length`. Đây là đúng kiểu khoảng nửa mở thường gặp trong Java.

```text
Mảng byte:  [H0] [H1] [C] [a] [f] [C3] [A9] [T]
Chỉ số:     0    1    2   3   4    5    6    7
                       <------ 5 byte ----->
                       offset=2, length=5
```

Ở minh họa này, `H0`/`H1` là header, `T` là trailer. Dãy byte từ vị trí 2 đến 6 tương ứng văn bản UTF-8 `Café`. Byte `C3` và `A9` phải cùng nằm trong vùng giải mã để tạo thành ký tự `é`.

Ví dụ:

```java
byte[] packet = {
        0x01, 0x02,             // Header
        0x43, 0x61, 0x66,
        (byte) 0xC3, (byte) 0xA9, // "Café" trong UTF-8
        0x7F                    // Trailer
};

String payload = new String(packet, 2, 5, StandardCharsets.UTF_8);
System.out.println(payload);
```

Kết quả:

```text
Café
```

Nếu chỉ cần giải mã, dùng constructor có vùng sẽ tiện hơn việc tạo một mảng tạm bằng `Arrays.copyOfRange(bytes, offset, offset + length)` rồi gọi `new String(... )`. Tuy nhiên, constructor vẫn cần xử lý và tạo chuỗi đầu ra; "không phải tự cắt mảng" **không đồng nghĩa với giải mã không cấp phát bộ nhớ**.

### Kiểm tra giới hạn vùng

`offset` và `length` phải không âm, và vùng phải nằm hoàn toàn trong `bytes`. Nếu vượt giới hạn, constructor ném `IndexOutOfBoundsException`. Ví dụ:

```java
byte[] data = {65, 66, 67}; // "ABC"
String value = new String(data, 1, 2, StandardCharsets.UTF_8);
// Kết quả: "BC"
```

`new String(data, 1, 3, StandardCharsets.UTF_8)` vượt quá độ dài mảng và gây lỗi. `offset=1, length=2` là chọn byte tại chỉ số 1 và 2, **không phải** "từ chỉ số 1 đến chỉ số 2" theo cách hiểu tham số `length` là điểm kết thúc.

`length=0` tạo chuỗi rỗng nếu `offset` hợp lệ (kể cả `offset == bytes.length`).

## 4. Chọn ranh giới byte phù hợp với charset

Với UTF-8, một ký tự Unicode có thể dùng từ một đến bốn byte. `offset` và `length` là tọa độ **byte**, vì vậy một vùng byte hợp lệ về giới hạn mảng vẫn có thể cắt ngang chuỗi mã hóa của một ký tự.

Ví dụ:

```java
byte[] eAcute = {(byte) 0xC3, (byte) 0xA9};

System.out.println(new String(eAcute, 0, 2, StandardCharsets.UTF_8));
System.out.println((int) new String(eAcute, 0, 1, StandardCharsets.UTF_8).charAt(0));
```

Kết quả:

```text
é
65533
```

Giải mã đủ hai byte cho ra `é`; chỉ lấy byte đầu `C3` khiến UTF-8 thiếu byte nối tiếp, nên constructor thay bằng ký tự thay thế Unicode **U+FFFD**, có giá trị thập phân 65533. Đây không phải lỗi chỉ số mảng, mà là **lỗi dãy byte sau khi chọn vùng**.

Nếu muốn tách một vùng theo số ký tự của **văn bản đã giải mã**, hãy giải mã phần dữ liệu hợp lệ trước, rồi dùng API xử lý `String` phù hợp. Đặc biệt, `String.length()` đếm đơn vị mã UTF-16, không phải byte và cũng không luôn bằng số Unicode code point.

Nếu dữ liệu đến theo nhiều khối từ mạng và một ký tự UTF-8 nằm trên ranh giới hai khối, không được giải mã mỗi khối độc lập rồi mong kết quả luôn chính xác. Hãy ghép đủ byte trước khi giải mã, hoặc dùng `CharsetDecoder` theo cơ chế giải mã tăng dần, giữ trạng thái giữa các khối.

## 5. Byte không hợp lệ và chế độ kiểm soát lỗi

Hai constructor `String` dùng `Charset` ở trên sẽ **thay các dãy byte sai hoặc không thể biểu diễn bằng chuỗi thay thế mặc định của charset**. Với UTF-8, thường thấy ký tự thay thế `�` (`U+FFFD`) trong đầu ra.

```java
byte[] badUtf8 = {(byte) 0xC3, (byte) 0x28};
String text = new String(badUtf8, StandardCharsets.UTF_8);

System.out.println((int) text.charAt(0));
System.out.println(text.charAt(1));
```

Kết quả:

```text
65533
(
```

Byte `C3` cần byte tiếp nối UTF-8 hợp lệ, nhưng `28` không đáp ứng; byte lỗi được thay bằng `U+FFFD`, còn `28` được hiểu thành dấu `(`. Hành vi thay thế giúp tiếp tục hiển thị dữ liệu có lỗi, nhưng có thể **che giấu việc đầu vào bị hỏng**.

Khi yêu cầu kiểm soát chặt, ví dụ đọc mã định danh, thông điệp giao thức hoặc dữ liệu cần xác minh, dùng `CharsetDecoder` và yêu cầu báo lỗi:

```java
import java.nio.ByteBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CharsetDecoder;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;

byte[] badUtf8 = {(byte) 0xC3, (byte) 0x28};

CharsetDecoder decoder = StandardCharsets.UTF_8.newDecoder()
        .onMalformedInput(CodingErrorAction.REPORT)
        .onUnmappableCharacter(CodingErrorAction.REPORT);

try {
    String text = decoder.decode(ByteBuffer.wrap(badUtf8)).toString();
    System.out.println(text);
} catch (CharacterCodingException error) {
    System.out.println("Dữ liệu UTF-8 không hợp lệ");
}
```

Kết quả:

```text
Dữ liệu UTF-8 không hợp lệ
```

Đây là **đoạn mã minh họa** để đặt trong một phương thức hoặc `main`; các lệnh `import` đặt ở đầu tệp. `REPORT` yêu cầu báo lỗi thay vì âm thầm thay ký tự. Khi chỉ muốn giải mã một vùng với decoder, dùng `ByteBuffer.wrap(bytes, offset, length)` để tạo buffer có vị trí và giới hạn tương ứng vùng byte. `CharsetDecoder` có trạng thái và không nên dùng chung một instance giữa các luồng nếu không đồng bộ đúng cách.

## 6. Chương trình Java 17+ chạy hoàn chỉnh

Tạo tệp **`ByteDecodingDemo.java`** với nội dung:

```java
import java.nio.ByteBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CharsetDecoder;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;

public class ByteDecodingDemo {
    public static void main(String[] args) {
        byte[] prefix = {0x01, 0x02, 0x03};
        byte[] content = "Chào Java".getBytes(StandardCharsets.UTF_8);
        byte[] suffix = {0x7F};
        byte[] packet = new byte[prefix.length + content.length + suffix.length];

        System.arraycopy(prefix, 0, packet, 0, prefix.length);
        System.arraycopy(content, 0, packet, prefix.length, content.length);
        System.arraycopy(suffix, 0, packet,
                prefix.length + content.length, suffix.length);

        String allTextBytes = new String(content, StandardCharsets.UTF_8);
        String selectedText = new String(
                packet, prefix.length, content.length, StandardCharsets.UTF_8);

        System.out.println("Giải mã đầy đủ: " + allTextBytes);
        System.out.println("Giải mã vùng: " + selectedText);
        System.out.println("Số đơn vị UTF-16: " + selectedText.length());
        System.out.println("Số byte UTF-8: " + content.length);

        byte[] invalid = {(byte) 0xC3, (byte) 0x28};
        String replaced = new String(invalid, StandardCharsets.UTF_8);
        System.out.println("Mã ký tự thay thế: " + (int) replaced.charAt(0));

        CharsetDecoder strict = StandardCharsets.UTF_8.newDecoder()
                .onMalformedInput(CodingErrorAction.REPORT)
                .onUnmappableCharacter(CodingErrorAction.REPORT);

        try {
            strict.decode(ByteBuffer.wrap(invalid));
            System.out.println("Dữ liệu hợp lệ");
        } catch (CharacterCodingException ex) {
            System.out.println("Dữ liệu không hợp lệ");
        }
    }
}
```

Biên dịch tệp được lưu bằng UTF-8 và chạy:

```bash
javac -encoding UTF-8 ByteDecodingDemo.java
java ByteDecodingDemo
```

Đầu ra hiển thị trên console hỗ trợ Unicode:

```text
Giải mã đầy đủ: Chào Java
Giải mã vùng: Chào Java
Số đơn vị UTF-16: 9
Số byte UTF-8: 10
Mã ký tự thay thế: 65533
Dữ liệu không hợp lệ
```

Giải thích: `"Chào Java"` gồm 9 đơn vị UTF-16 nhưng 10 byte UTF-8, vì chữ `à` được mã hóa bằng hai byte. `packet` chứa ba byte header, mười byte văn bản, một byte trailer. Constructor bốn tham số chỉ lấy đúng mười byte văn bản; hai phần nhị phân không đi vào kết quả. Đoạn cuối phân biệt hành vi thay thế ký tự của constructor với cơ chế báo lỗi của decoder.

## 7. Lưu ý thực tế và lỗi thường gặp

| Tình huống | Nguyên nhân hoặc cách xử lý |
| --- | --- |
| Chữ tiếng Việt biến thành `�` hoặc ký tự lạ | Kiểm tra charset nguồn và tính hợp lệ của byte, đừng đoán UTF-8 nếu định dạng thực tế khác |
| Lấy nhầm phần header hoặc trailer | Tính `offset` từ đầu mảng và `length` là số byte thực sự của payload |
| Cắt giữa ký tự đa byte | Chọn ranh giới mã hóa đúng, hoặc giải mã dạng streaming bằng decoder giữ trạng thái |
| `IndexOutOfBoundsException` | Rà lại chỉ số byte, độ dài và giới hạn mảng |
| Dữ liệu lỗi nhưng chương trình không ném ngoại lệ | Constructor `String` đang dùng cơ chế thay thế; chuyển sang `CharsetDecoder` với `REPORT` nếu cần |
| Đếm `String.length()` để tính kích thước bản tin | Độ dài `String` là số đơn vị UTF-16; dùng độ dài `byte[]` khi giao thức cần số byte |
| Tệp UTF-8 bắt đầu bằng BOM | Các byte `EF BB BF` biểu diễn `U+FEFF`; khi giải mã UTF-8 với `String`, hãy kiểm tra và xử lý dấu này nếu định dạng tệp yêu cầu bỏ BOM |
| Đưa dữ liệu của người dùng vào `new String(bytes)` không nêu charset | Nêu charset theo giao thức, ví dụ `StandardCharsets.UTF_8`, để dữ liệu có ý nghĩa nhất quán |

Không được nhầm `new String(bytes, 2, 5, UTF_8)` với `substring(2, 5)`: `substring` nhận vị trí trong văn bản Java sau khi giải mã và đối số thứ hai là **chỉ số kết thúc loại trừ**; constructor vùng byte nhận **số byte**. Hai thao tác có đơn vị và ý nghĩa khác nhau.

## 8. Tự kiểm tra

**Câu 1.** Cho `byte[] data = {65, 66, 67, 68};`. Giá trị của `new String(data, 1, 2, StandardCharsets.US_ASCII)` là gì?

**Đáp án:** `"BC"`. Vùng giải mã gồm byte chỉ số 1 và 2, ứng với mã ASCII 66 và 67.

**Câu 2.** Vì sao `new String(utf8, 0, 1, UTF_8)` có thể tạo `�` dù chỉ số `0` và độ dài `1` đều hợp lệ?

**Đáp án:** Một byte đầu có thể là phần đầu của ký tự UTF-8 hai đến bốn byte. Vùng byte không chứa đủ dãy mã hóa nên đầu vào không hợp lệ với decoder.

**Câu 3.** Khi nào nên dùng `CharsetDecoder` thay cho constructor `String`?

**Đáp án:** Khi cần phát hiện dữ liệu không hợp lệ thay vì tự động thay ký tự, hoặc cần giải mã dữ liệu nhiều đợt với trạng thái duy trì giữa các lần nhận byte.

## Ghi nhớ

Dùng **`new String(bytes, charset)`** để giải mã toàn bộ dãy byte và **`new String(bytes, offset, length, charset)`** để giải mã đúng vùng byte thuộc payload. `offset` là vị trí byte đầu, `length` là **số byte**, và bảng mã phải khớp dữ liệu nguồn. Với UTF-8, đặc biệt chú ý ranh giới ký tự nhiều byte và sử dụng `CharsetDecoder` nếu cần xác thực lỗi đầu vào.
