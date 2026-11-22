# Constructor String nhận Charset: giải mã byte thành văn bản

## 1. Khái niệm: byte chưa tự mang ý nghĩa ký tự

Một mảng `byte[]` chỉ chứa các giá trị byte. Muốn hiểu nó là văn bản, cần biết **bảng mã (charset)** đã được dùng để tạo ra các byte đó.

Ví dụ, ký tự `é` có code point Unicode `U+00E9`. Khi mã hóa bằng UTF-8, nó được biểu diễn bởi hai byte `C3 A9`. Đọc hai byte này bằng một bảng mã khác có thể cho ra hai ký tự khác.

Constructor `String` nhận `Charset` thực hiện chiều:

```text
byte[] + quy tắc giải mã của Charset → String
```

Đây là **giải mã (decoding)**. Chiều ngược lại là mã hóa chuỗi thành byte, chẳng hạn qua `text.getBytes(charset)`.

Không nên nói “đổi chuỗi sang UTF-8” khi mã đang gọi `new String(bytes, charset)`: kết quả của thao tác này là một String, không phải một mảng byte UTF-8 mới.

Các constructor nhận đối tượng `Charset` được thêm từ Java 6 và vẫn phù hợp trên Java hiện đại. Ví dụ trong bài dùng JDK 17+ và các hằng `StandardCharsets` để biểu đạt rõ bảng mã.

## 2. Hai overload chính và cách chọn

```java
new String(byte[] bytes, Charset charset)
new String(byte[] bytes, int offset, int length, Charset charset)
```

Đây là các dạng lời gọi, không phải chương trình độc lập.

| Dạng | Phần dữ liệu được giải mã |
| --- | --- |
| `String(bytes, charset)` | Toàn bộ mảng |
| `String(bytes, offset, length, charset)` | `length` byte bắt đầu từ chỉ số `offset` |

Dùng dạng toàn bộ mảng khi mảng chứa đúng toàn bộ nội dung văn bản cần đọc. Dùng dạng phạm vi khi văn bản là một phần trong bộ đệm, chẳng hạn sau phần đầu của một bản tin.

Cả hai overload này có `Since: 1.6` trong Javadoc hiện hành. Đừng nhầm mốc này với:

- Mốc ra đời của lớp `String`.
- Mốc của `Charset`.
- Mốc của lớp chứa các hằng `StandardCharsets`.

`StandardCharsets` có từ Java 7. Vì vậy, một ví dụ dùng `StandardCharsets.UTF_8` là cách viết hiện đại cho API đã có từ Java 6, không phải mã nguồn nguyên văn chỉ dùng thư viện Java 6.

## 3. Charset là quy tắc giải mã, không phải nhãn gắn vào String

Ví dụ đơn giản:

```java
String text = new String(bytes, StandardCharsets.UTF_8);
```

Dòng này nói: **hãy hiểu các byte đầu vào theo UTF-8**.

Nó không làm các việc sau:

- Tự phát hiện bảng mã gốc.
- Kiểm tra phần mô tả HTTP hoặc metadata của một tệp.
- Gắn một thuộc tính “UTF-8” có thể đọc lại từ String.
- Biến mọi dữ liệu nhị phân thành văn bản có ý nghĩa.
- Sửa lại những byte đã hỏng từ trước.

Sau khi có String, các API như `length()`, `charAt()` và `codePoints()` làm việc với nội dung ký tự theo mô hình của String. Nếu cần xuất nó thành byte, phải chọn một bảng mã cho thao tác mã hóa mới.

### Cùng byte, khác bảng mã

Xét mảng có giá trị hex:

```text
43 61 66 C3 A9
```

- Giải mã UTF-8 tạo các code point `U+0043 U+0061 U+0066 U+00E9`, tức `Café`.
- Giải mã ISO-8859-1 tạo `U+0043 U+0061 U+0066 U+00C3 U+00A9`.

Dữ liệu ISO-8859-1 trong ví dụ vẫn có thể giải mã hợp lệ; kết quả chỉ sai so với ý nghĩa mà người gửi định truyền. Vì vậy, **không có ngoại lệ không chứng minh bảng mã đã đúng**.

Nguồn bảng mã phải đến từ hợp đồng dữ liệu: định dạng tệp, giao thức, cấu hình được xác định hoặc thỏa thuận giữa bên ghi và bên đọc. Không suy đoán chỉ vì một bảng mã đã cho ra chuỗi trông có vẻ đọc được.

## 4. Vì sao nên truyền Charset tường minh?

### Giữ ý định ở ngay điểm đọc dữ liệu

So sánh:

```java
String implicit = new String(bytes);
String explicit = new String(bytes, StandardCharsets.UTF_8);
```

Đây là đoạn minh họa, giả sử đã có biến `bytes`.

Dòng thứ nhất dùng bảng mã mặc định của môi trường JVM. Dòng thứ hai ghi rõ hợp đồng UTF-8 tại nơi giải mã.

Ngay cả khi bảng mã mặc định hiện tại trùng UTF-8, lựa chọn tường minh vẫn có giá trị: người đọc mã biết rõ quy tắc dữ liệu và không phải suy từ cấu hình môi trường.

Không đặt một bảng mã toàn cục rồi dùng nó cho mọi đầu vào. Một tệp UTF-16LE và một bản tin UTF-8 có thể xuất hiện trong cùng ứng dụng; mỗi luồng dữ liệu cần đúng bảng mã của nó.

### Hằng chuẩn thay cho một tên dễ gõ sai

```java
StandardCharsets.UTF_8
StandardCharsets.ISO_8859_1
StandardCharsets.UTF_16LE
```

Các hằng này là những đối tượng `Charset` cho bảng mã chuẩn được nền tảng Java hỗ trợ. Trong phạm vi bài, UTF-8 là lựa chọn khi dữ liệu được xác định là UTF-8, không phải “bảng mã luôn đúng cho mọi byte”.

Overload nhận `Charset` không khai báo checked exception `UnsupportedEncodingException` như overload nhận một chuỗi tên bảng mã. Khi đã có đối tượng `Charset` hợp lệ, không cần bắt checked exception đó quanh lời gọi constructor này.

Điều đó không có nghĩa thao tác không thể lỗi: tham số null hoặc phạm vi sai vẫn có thể gây ngoại lệ.

Nếu tên bảng mã đến từ cấu hình động, có thể dùng `Charset.forName(name)` ở ranh giới đọc cấu hình. Việc tra tên có thể thất bại do tên không hợp lệ hoặc không được hỗ trợ; nên xử lý lỗi tại đó, thay vì giả định truyền tên từ người dùng luôn thành công.

`Charset` bất biến và có thể dùng chung giữa các luồng. `CharsetDecoder` là đối tượng có trạng thái và không được chia sẻ tùy ý cho nhiều luồng đồng thời; hai loại đối tượng có vai trò khác nhau.

## 5. Offset và length tính theo byte

Với:

```java
new String(packet, 1, 5, StandardCharsets.UTF_8)
```

JVM đọc vùng:

```text
packet[1], packet[2], packet[3], packet[4], packet[5]
```

`length=5` là số byte, **không phải chỉ số kết thúc** và **không phải số ký tự đầu ra**.

Phạm vi hợp lệ có thể biểu diễn bằng các điều kiện:

```text
offset >= 0
length >= 0
offset <= bytes.length - length
```

Dạng cuối tránh việc tự cộng hai số nguyên lớn rồi kiểm tra một tổng có thể tràn. Constructor kiểm tra phạm vi theo hợp đồng; không cần tự viết lại kiểm tra nếu không có lý do nghiệp vụ riêng.

Nếu các giá trị không hợp lệ, constructor ném một `IndexOutOfBoundsException`. Không phụ thuộc vào một thông điệp ngoại lệ cụ thể hay một lớp con cụ thể để xử lý phạm vi.

### Số byte và độ dài String có thể khác nhau

Ví dụ `Café` ở trên:

```text
Số byte UTF-8: 5
String.length(): 4
```

Với ký tự ngoài mặt phẳng Unicode cơ bản như `U+1F600`:

```text
Số byte UTF-8: 4
String.length(): 2
Số code point: 1
```

`String.length()` đếm đơn vị mã UTF-16, không đếm byte đầu vào và không phải phép đếm tổng quát các ký tự người dùng nhìn thấy.

Vì vậy, không dùng `text.length()` để suy ngược chắc chắn số byte cần đọc từ một giao thức UTF-8.

### Phạm vi mảng hợp lệ vẫn có thể cắt hỏng ký tự

Một vùng nằm hoàn toàn trong mảng không bảo đảm chứa một chuỗi mã hóa hoàn chỉnh.

Nếu ký tự `é` dùng hai byte `C3 A9`, cắt vùng kết thúc sau `C3` sẽ để lại một chuỗi UTF-8 chưa hoàn chỉnh. Đây không phải lỗi chỉ số mảng; đó là lỗi dữ liệu theo bảng mã.

Hai loại lỗi cần được tách rõ:

- Vượt biên mảng: sai phạm vi.
- Cắt giữa một chuỗi byte nhiều byte: phạm vi có thể đúng nhưng dữ liệu giải mã bị lỗi.

## 6. Constructor xử lý byte lỗi như thế nào?

Hai overload nhận `Charset` dùng **chuỗi thay thế mặc định của bảng mã** khi gặp dữ liệu malformed hoặc unmappable.

Với UTF-8 trong ví dụ:

```text
Đầu vào: C3 28
Kết quả code point: U+FFFD U+0028
```

`C3` không được theo sau bởi một byte tiếp tục UTF-8 phù hợp. Constructor dùng ký tự thay thế cho phần lỗi và vẫn giải mã dấu ngoặc `(` của byte `28`.

Điểm quan trọng:

- Constructor có thể trả một String dù đầu vào không hợp lệ.
- Không nên dùng việc tạo String thành công như một phép xác thực UTF-8 nghiêm ngặt.
- Ký tự thay thế không khôi phục được thông tin gốc đã mất.
- Không có quy tắc chung “mỗi byte sai luôn tạo một U+FFFD” cho mọi chuỗi lỗi và mọi bảng mã; cần theo hợp đồng và thuật toán giải mã.

Nếu dữ liệu dùng cho định danh, phân tích cú pháp hoặc lưu trữ cần giữ chính xác, cần quyết định chính sách lỗi rõ ràng thay vì âm thầm chấp nhận thay thế.

### Muốn báo lỗi thay vì thay thế: dùng CharsetDecoder

Có thể tạo decoder với chính sách `REPORT`:

```java
String decoded = StandardCharsets.UTF_8.newDecoder()
        .onMalformedInput(CodingErrorAction.REPORT)
        .onUnmappableCharacter(CodingErrorAction.REPORT)
        .decode(ByteBuffer.wrap(bytes))
        .toString();
```

Đây là đoạn minh họa, cần các import tương ứng và xử lý `CharacterCodingException`.

Decoder mới mặc định đã dùng REPORT cho hai loại lỗi; viết tường minh trong ví dụ giúp thể hiện chính sách mà mã đang yêu cầu.

Việc dùng decoder nghiêm ngặt chỉ chứng minh byte hợp lệ theo bảng mã đã chọn. Nó không chứng minh bảng mã đó là bảng mã mà bên gửi định dùng, và cũng không kiểm tra các quy tắc nghiệp vụ của văn bản.

## 7. Ví dụ chạy được: đúng bảng mã, đúng phạm vi và chính sách lỗi

Tệp `StringCharsetDemo.java`:

```java
import java.nio.ByteBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.util.Locale;
import java.util.stream.Collectors;

public final class StringCharsetDemo {
    private static String codePoints(String value) {
        return value.codePoints()
                .mapToObj(cp -> String.format(Locale.ROOT, "U+%04X", cp))
                .collect(Collectors.joining(" "));
    }

    public static void main(String[] args) {
        byte[] bytes = {
                0x43, 0x61, 0x66, (byte) 0xC3, (byte) 0xA9
        };
        String text = new String(bytes, StandardCharsets.UTF_8);
        System.out.println("utf8=" + codePoints(text));
        System.out.println("bytes=" + bytes.length + " chars=" + text.length());

        String wrong = new String(bytes, StandardCharsets.ISO_8859_1);
        System.out.println("latin1=" + codePoints(wrong));
        System.out.println("same=" + text.equals(wrong));

        byte[] packet = {
                0x7C, 0x43, 0x61, 0x66, (byte) 0xC3, (byte) 0xA9, 0x7C
        };
        String slice = new String(packet, 1, 5, StandardCharsets.UTF_8);
        System.out.println("slice=" + codePoints(slice));
        String cut = new String(packet, 1, 4, StandardCharsets.UTF_8);
        System.out.println("cut=" + codePoints(cut));

        bytes[0] = 0x58;
        System.out.println("afterMutation=" + codePoints(text));

        byte[] invalid = {(byte) 0xC3, 0x28};
        String replaced = new String(invalid, StandardCharsets.UTF_8);
        System.out.println("replace=" + codePoints(replaced));
        try {
            StandardCharsets.UTF_8.newDecoder()
                    .onMalformedInput(CodingErrorAction.REPORT)
                    .onUnmappableCharacter(CodingErrorAction.REPORT)
                    .decode(ByteBuffer.wrap(invalid));
            System.out.println("strict=accepted");
        } catch (CharacterCodingException expected) {
            System.out.println("strict=CharacterCodingException");
        }

        byte[] emojiBytes = {
                (byte) 0xF0, (byte) 0x9F, (byte) 0x98, (byte) 0x80
        };
        String emoji = new String(emojiBytes, StandardCharsets.UTF_8);
        System.out.println("emoji bytes=" + emojiBytes.length
                + " chars=" + emoji.length()
                + " codePoints=" + emoji.codePointCount(0, emoji.length()));

        try {
            new String(packet, -1, 2, StandardCharsets.UTF_8);
        } catch (IndexOutOfBoundsException expected) {
            System.out.println("range=IndexOutOfBoundsException");
        }
    }
}
```

Trong Java, `byte` là kiểu có dấu. Các literal hex như `0xC3` lớn hơn giá trị dương tối đa của byte nên ví dụ ép kiểu bằng `(byte)`. Giá trị bit được dùng cho giải mã vẫn là byte `C3`; không cần “chuyển byte âm thành ký tự” bằng phép ép kiểu sang `char`.

Hàm `codePoints` in mã Unicode thay vì dựa vào cách console vẽ ký tự. `Locale.ROOT` giữ cách định dạng ổn định cho ví dụ.

Biên dịch và chạy bằng JDK 17+:

```powershell
javac --release 17 -d out StringCharsetDemo.java
java -cp out StringCharsetDemo
```

Chỉ chạy sau khi biên dịch thành công.

Stdout:

```text
utf8=U+0043 U+0061 U+0066 U+00E9
bytes=5 chars=4
latin1=U+0043 U+0061 U+0066 U+00C3 U+00A9
same=false
slice=U+0043 U+0061 U+0066 U+00E9
cut=U+0043 U+0061 U+0066 U+FFFD
afterMutation=U+0043 U+0061 U+0066 U+00E9
replace=U+FFFD U+0028
strict=CharacterCodingException
emoji bytes=4 chars=2 codePoints=1
range=IndexOutOfBoundsException
```

Ví dụ đã được biên dịch với `--release 17` và chạy kiểm tra bằng JDK 24.0.2.

### Đọc kết quả

- `utf8`: toàn bộ năm byte được giải mã thành bốn code point của `Café`.
- `latin1`: cùng byte tạo nội dung khác khi chọn bảng mã khác.
- `slice`: phạm vi bắt đầu tại byte 1, lấy năm byte nên bỏ được hai dấu `|` bao ngoài.
- `cut`: lấy bốn byte cắt thiếu byte cuối của ký tự UTF-8, dẫn tới ký tự thay thế.
- `afterMutation`: sửa mảng sau khi constructor đã hoàn tất không thay nội dung String đã tạo.
- `replace`: constructor xử lý dữ liệu UTF-8 lỗi theo chính sách thay thế.
- `strict`: decoder REPORT báo lỗi qua `CharacterCodingException`.
- `emoji`: số byte, số đơn vị mã UTF-16 và số code point không giống nhau.
- `range`: offset âm gây lỗi phạm vi, là lỗi khác với dữ liệu mã hóa lỗi.

Tên `chars` trong stdout của ví dụ dùng cho giá trị `String.length()`, tức số đơn vị mã UTF-16; không dùng nó làm định nghĩa “số ký tự nhìn thấy”.

## 8. Mảng đầu vào, String bất biến và xử lý đồng thời

Sau khi tạo xong, String có nội dung bất biến. Mảng nguồn vẫn là một đối tượng mutable riêng; sửa mảng về sau không phải cách sửa String đã tạo.

Nhưng không được để một luồng sửa chính mảng byte trong lúc một luồng khác đang gọi constructor để giải mã. Javadoc không đặc tả một kết quả ổn định cho tình huống đầu vào bị thay đổi trong thời gian dựng chuỗi.

Khi dùng bộ đệm được tái sử dụng, cần có quyền sử dụng dữ liệu rõ ràng:

```text
Nhận đủ phần byte cần đọc
    ↓
Bảo đảm phần byte đó không bị ghi đè trong lúc giải mã
    ↓
Tạo String
    ↓
Sau khi hoàn tất mới tái sử dụng bộ đệm
```

Không suy luận từ tính bất biến của **kết quả** thành tính an toàn của việc sửa đồng thời **đầu vào**.

Dạng offset/length giúp chọn một phần mảng mà không cần tự tạo một mảng con trước. Tuy nhiên, kết quả vẫn là một String; không mô tả nó như một “view” văn bản có thể cập nhật theo mảng nguồn hoặc một thao tác luôn không cấp phát.

## 9. Các giới hạn cần biết khi áp dụng

### Không giải mã từng mảnh mạng tùy ý như các chuỗi độc lập

Một ký tự UTF-8 có thể bị chia giữa hai lần đọc dữ liệu. Nếu gọi constructor riêng trên từng phần rồi nối String, phần đầu có thể bị thay thế trước khi byte còn thiếu xuất hiện.

Ví dụ về ranh giới:

```text
Lần đọc 1: 43 61 66 C3
Lần đọc 2: A9
```

Cả chuỗi ghép byte là UTF-8 hợp lệ của `Café`. Nhưng mỗi mảnh không phải một đoạn văn bản UTF-8 hoàn chỉnh độc lập ở ranh giới đó.

Với dữ liệu văn bản dạng luồng, dùng cơ chế đọc ký tự hoặc decoder có trạng thái phù hợp để giữ phần byte chưa hoàn chỉnh. Constructor phù hợp khi đã có một vùng byte hoàn chỉnh theo hợp đồng.

### Chọn đúng byte order với UTF-16

`UTF_16`, `UTF_16LE` và `UTF_16BE` là các lựa chọn khác nhau. Nếu định dạng quy định little-endian, hãy dùng đúng lựa chọn đó; không coi hai byte bất kỳ là một ký tự mà bỏ qua thứ tự byte.

Việc xử lý BOM phụ thuộc bảng mã và định dạng đầu vào. Không giả định mọi constructor tự nhận diện hoặc bỏ mọi BOM theo cùng một cách. Đọc hợp đồng charset khi làm với dữ liệu có dấu hiệu byte order.

### Giải mã không tự chuẩn hóa Unicode

Constructor chuyển byte thành nội dung ký tự theo bảng mã. Nó không tự bảo đảm mọi cách biểu diễn tương đương của một chữ đều được chuẩn hóa về một chuỗi code point duy nhất.

Nếu hệ thống cần so sánh/tìm kiếm theo một quy tắc chuẩn hóa, đó là bước có chủ đích sau giải mã, không phải tác dụng ngầm của việc truyền UTF-8.

### Dữ liệu nhị phân cần biểu diễn thích hợp

Một ảnh hoặc một tệp nén không tự thành văn bản chỉ vì `new String` trả về được một giá trị. Nếu cần biểu diễn byte trong log hoặc văn bản, dùng biểu diễn có ý nghĩa như hex/Base64 theo mục tiêu.

Ép byte nhị phân qua một charset có thay thế lỗi có thể làm mất thông tin và không bảo đảm mã hóa lại thu được byte gốc.

## 10. Lỗi phổ biến

| Lỗi | Vì sao sai | Cách sửa |
| --- | --- | --- |
| Truyền charset tùy ý cho tới khi “trông đọc được” | Byte có thể hợp lệ trong nhiều charset | Lấy charset từ hợp đồng dữ liệu |
| Dùng `length` như chỉ số kết thúc | Constructor cần số byte | Tính số lượng từ ranh giới đã xác định |
| Dùng số ký tự thay cho số byte | Ký tự nhiều byte làm hai số khác nhau | Xác định phạm vi trên dữ liệu byte |
| Bắt `UnsupportedEncodingException` quanh overload nhận Charset | Overload này không khai báo checked exception đó | Dùng hằng chuẩn hoặc xử lý tra tên tại điểm cấu hình |
| Coi String tạo thành công là UTF-8 đã được xác thực | Constructor có chính sách thay thế lỗi | Dùng decoder REPORT khi cần từ chối dữ liệu lỗi |
| Sửa mảng từ luồng khác trong lúc dựng String | Đầu vào không ổn định | Quản lý quyền sử dụng bộ đệm |
| Decode từng phần đọc mạng riêng rồi nối | Có thể cắt giữa một chuỗi byte | Giữ trạng thái giải mã hoặc gom đủ phần dữ liệu |
| Encode/decode nhiều lần để “sửa font” | Có thể tạo thêm mất mát và che lỗi nguồn | Xác định byte gốc và charset đúng tại ranh giới |

### Lưu ý về null và overload

`bytes` hoặc `charset` bằng null không phải cách yêu cầu “tự chọn” hay tạo chuỗi rỗng; đó là dữ liệu tham số không hợp lệ.

Lời gọi `new String(bytes, null)` còn có thể không biên dịch do không xác định được muốn dùng overload nhận `String` hay `Charset`. Đừng dùng null làm dấu hiệu bảng mã mặc định. Nếu cần mặc định theo thiết kế, chọn nó một cách tường minh trước khi gọi.

### Không thể sửa mất mát chỉ bằng encode/decode lại

Một khi byte lỗi đã bị thay bằng `U+FFFD`, thông tin gốc không còn đầy đủ trong String. Gọi `getBytes` sau đó không có một phép đảo ngược tổng quát để lấy lại byte trước khi mất.

Cách xử lý đúng thường bắt đầu từ việc giữ hoặc đọc lại byte gốc và xác định bảng mã/chính sách lỗi đúng, không thêm một chuỗi biến đổi ngẫu nhiên.

## 11. Chọn công cụ theo yêu cầu

| Yêu cầu | Công cụ phù hợp |
| --- | --- |
| Có toàn bộ byte văn bản, biết charset, chấp nhận thay thế lỗi | Constructor `String(bytes, charset)` |
| Cần một vùng byte hoàn chỉnh trong bộ đệm | Constructor có offset/length |
| Cần từ chối dữ liệu mã hóa lỗi | `CharsetDecoder` với REPORT |
| Cần giải mã liên tục qua nhiều khối byte | Decoder có trạng thái hoặc cơ chế đọc ký tự phù hợp |
| Cần biến String thành byte để gửi/ghi | `getBytes(charset)` hoặc encoder nếu cần chính sách lỗi riêng |
| Cần giữ byte nhị phân chính xác | Giữ `byte[]`/buffer; chỉ chuyển sang hex/Base64 khi cần biểu diễn văn bản |

Sự khác biệt chủ yếu là chính sách và ranh giới dữ liệu, không phải constructor “luôn đủ tốt” hay decoder “luôn cần thiết”.

## 12. Bài tập tự kiểm chứng

1. Đổi phạm vi `packet` từ `(1,5)` thành `(1,4)` và giải thích vì sao không có lỗi chỉ số nhưng xuất hiện `U+FFFD`.
2. Đổi charset của cùng năm byte thành ISO-8859-1. Giải thích vì sao không có ngoại lệ vẫn có thể là văn bản sai.
3. Truyền mảng rỗng cùng UTF-8. Dự đoán `String.length()` và so sánh với trường hợp mảng null.
4. Dùng decoder REPORT cho vùng byte bị cắt. So sánh quyết định xử lý lỗi với constructor, không chỉ so loại đối tượng trả về.
5. Giải thích vì sao sửa `bytes[0]` sau khi tạo chuỗi không sửa String, nhưng sửa đồng thời trong lúc constructor đang chạy lại không phải tình huống được bảo đảm.
6. Với bốn byte UTF-8 của `U+1F600`, nêu riêng số byte, số code point và giá trị `String.length()`.
7. Thiết kế nơi lấy charset trong một bản tin có header ghi bảng mã. Đừng để constructor tự suy đoán thông tin ngoài mà nó không nhận được.

Điều cần nắm là **constructor nhận Charset giải mã một vùng byte theo quy tắc đã chọn; phạm vi tính theo byte, kết quả là nội dung String, và dữ liệu lỗi được thay thế trừ khi chọn một cơ chế kiểm soát nghiêm ngặt hơn**.

## Tài liệu đối chiếu

- [String — Javadoc Java SE 27](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/String.html): hai constructor nhận Charset, mốc 1.6, phạm vi và thay thế lỗi.
- [Charset](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/nio/charset/Charset.html): ý nghĩa bảng mã, tra tên và quy tắc byte order.
- [StandardCharsets](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/nio/charset/StandardCharsets.html): hằng bảng mã chuẩn và mốc 1.7.
- [CharsetDecoder](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/nio/charset/CharsetDecoder.html): chính sách lỗi, giải mã có trạng thái và giới hạn dùng đồng thời.
