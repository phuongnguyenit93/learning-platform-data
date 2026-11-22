# Charset, StandardCharsets và tên charset trong Java I/O

## 1. Charset là gì và giải quyết vấn đề nào?

File và luồng I/O lưu, truyền **byte**; còn `String` trong Java biểu diễn văn bản Unicode. Để đổi giữa hai dạng phải có một quy tắc mã hóa ký tự, gọi là **character encoding** hoặc **charset**.

- **Encode (mã hóa):** ký tự Unicode → dãy byte theo charset được chọn.
- **Decode (giải mã):** dãy byte → ký tự Unicode bằng chính quy tắc tương ứng.

Ví dụ, ký tự `é` (U+00E9) được biểu diễn:

| Charset | Byte hex của `é` |
| --- | --- |
| UTF-8 | `C3 A9` |
| ISO-8859-1 | `E9` |
| UTF-16BE | `00 E9` |
| UTF-16LE | `E9 00` |

Cùng một ký tự có các byte khác nhau giữa các charset. Ngược lại, cùng một dãy byte có thể được diễn giải ra ký tự khác nhau, hoặc trở thành dữ liệu không hợp lệ, khi chọn sai charset.

Ví dụ dãy `41 C3 A9` là chuỗi `Aé` khi giải mã bằng UTF-8, nhưng thành `AÃ©` theo ISO-8859-1. Đó là lỗi chữ bị biến dạng (*mojibake*), thường gặp khi ứng dụng gửi UTF-8 nhưng phía nhận lại giải mã theo charset khác.

**Charset không phải** thuật toán nén, mã hóa bảo mật hay định dạng tệp. Nó chỉ xác định cách ánh xạ giữa văn bản và byte. Cũng cần phân biệt charset với dấu tiếng Việt/Unicode normalization: hai chuỗi hiển thị giống nhau có thể dùng các chuỗi code point khác nhau; việc mã hóa không tự chuẩn hóa chúng.

## 2. `java.nio.charset.Charset`: đối tượng mô tả một bộ mã

`Charset` là lớp trong gói `java.nio.charset`, đại diện cho một cách chuyển đổi giữa chuỗi ký tự và byte. Trong Java, một đối tượng `Charset` thường được truyền trực tiếp cho API I/O thay vì tên dạng chuỗi.

Những phương thức hữu ích:

| API | Tác dụng |
| --- | --- |
| `Charset.forName("UTF-8")` | Tìm charset theo tên chuẩn hoặc tên khác được runtime nhận biết; ném ngoại lệ nếu tên không hợp lệ/không được hỗ trợ |
| `Charset.isSupported("UTF-8")` | Kiểm tra một tên hợp lệ có được hỗ trợ không |
| `charset.name()` | Lấy **tên chuẩn (canonical name)** của charset |
| `charset.aliases()` | Lấy các tên khác (*aliases*) mà provider công bố |
| `Charset.availableCharsets()` | Lấy danh sách charset khả dụng trên runtime dưới dạng map tên chuẩn → đối tượng |
| `Charset.defaultCharset()` | Xem charset mặc định của runtime |
| `charset.newEncoder()` và `charset.newDecoder()` | Tạo bộ chuyển đổi để kiểm soát cách xử lý ký tự/byte lỗi |

Không cần gọi `new Charset(...)`; đây là lớp trừu tượng, đối tượng thực tế do thư viện Java và các provider cung cấp.

### Tên chuẩn, tên khác và việc so sánh

Tên charset có dạng chuỗi, ví dụ `UTF-8`, `US-ASCII`, `ISO-8859-1`. Tên chuẩn là tên `charset.name()` trả về. Tên khác (*alias*) có thể dùng để tra cứu cùng charset; ví dụ nhiều JDK chấp nhận `UTF8` cho `UTF-8`, nhưng **tập alias ngoài tên chuẩn có thể phụ thuộc provider/runtime**.

Tra cứu tên charset **không phân biệt chữ hoa/chữ thường**, vì vậy `Charset.forName("uTf-8")` và `Charset.forName("UTF-8")` trỏ tới cùng charset về mặt ngữ nghĩa. Dùng `charset.equals(other)` để so sánh các đối tượng charset, hoặc chuẩn hóa qua `charset.name()` khi cần lưu tên; không dựa vào `==` hay so chuỗi alias tùy ý.

Các tên truyền vào phải đúng cú pháp mà `Charset` cho phép; ký tự không hợp lệ có thể làm `isSupported` ném `IllegalCharsetNameException` thay vì trả về `false`.

## 3. `StandardCharsets`: dùng hằng thay cho tên chuỗi

`java.nio.charset.StandardCharsets` cung cấp sẵn các đối tượng `Charset` cho sáu bộ mã được **mọi triển khai Java SE bảo đảm hỗ trợ**:

| Hằng | Tên chuẩn | Điểm cần biết |
| --- | --- | --- |
| `StandardCharsets.UTF_8` | `UTF-8` | Unicode, mã hóa biến độ dài 1–4 byte/code point; lựa chọn mặc định cho giao tiếp/tệp văn bản mới nếu không có đặc tả khác |
| `StandardCharsets.US_ASCII` | `US-ASCII` | 7 bit; chỉ biểu diễn trực tiếp U+0000 đến U+007F |
| `StandardCharsets.ISO_8859_1` | `ISO-8859-1` | Một byte cho mỗi ký tự U+0000 đến U+00FF; không chứa phần lớn ký tự tiếng Việt |
| `StandardCharsets.UTF_16` | `UTF-16` | Unicode UTF-16, khi encode thường ghi BOM để chỉ byte order; decoder có thể nhận BOM |
| `StandardCharsets.UTF_16BE` | `UTF-16BE` | UTF-16 thứ tự byte lớn trước; không tự thêm BOM |
| `StandardCharsets.UTF_16LE` | `UTF-16LE` | UTF-16 thứ tự byte nhỏ trước; không tự thêm BOM |

**Tên hằng Java** như `UTF_8` dùng dấu gạch dưới do quy tắc identifier; **tên charset chuẩn** như `UTF-8` dùng dấu gạch ngang. Không truyền chuỗi `"UTF_8"` và mặc định nó đồng nghĩa với `"UTF-8"`; hãy sử dụng hằng hoặc tên chuẩn chính xác.

Ưu tiên:

```java
byte[] bytes = text.getBytes(StandardCharsets.UTF_8);
String decoded = new String(bytes, StandardCharsets.UTF_8);
```

Thay vì tự tra cứu mỗi lần bằng chuỗi:

```java
Charset charset = Charset.forName("UTF-8");
```

Hai đoạn trên **là đoạn mã minh họa**: `text` và `bytes` phải được khai báo trong ngữ cảnh thích hợp. Khi charset cố định tại thời điểm viết chương trình, hằng `StandardCharsets` giúp tránh sai chính tả, tránh xử lý ngoại lệ tên không hỗ trợ và nói rõ ý định ngay trong mã nguồn.

Nếu tên charset đến từ cấu hình bên ngoài, chuỗi HTTP hoặc tệp metadata, `Charset.forName(name)` vẫn hữu ích; chỉ cần kiểm tra tên và xử lý lỗi. `StandardCharsets` không chứa toàn bộ các charset mà một JDK có thể hỗ trợ.

## 4. Ví dụ Java 17+: tra cứu tên, encode và decode

Tạo tệp **`CharsetNamesDemo.java`**:

```java
import java.nio.charset.Charset;
import java.nio.charset.StandardCharsets;
import java.util.HexFormat;

public class CharsetNamesDemo {
    public static void main(String[] args) {
        Charset utf8 = StandardCharsets.UTF_8;
        Charset fromName = Charset.forName("uTf-8");

        String original = "Aé";
        byte[] bytes = original.getBytes(utf8);

        System.out.println("Tên chuẩn: " + utf8.name());
        System.out.println("Cùng charset: " + utf8.equals(fromName));
        System.out.println("UTF-8 hex: " + HexFormat.of().formatHex(bytes));
        System.out.println("Giải mã UTF-8: " + new String(bytes, utf8));
        System.out.println("Giải mã Latin-1: "
                + new String(bytes, StandardCharsets.ISO_8859_1));
        System.out.println("Hỗ trợ UTF-8: " + Charset.isSupported("UTF-8"));
    }
}
```

Biên dịch và chạy bằng Java 17 trở lên:

```bash
javac -encoding UTF-8 CharsetNamesDemo.java
java CharsetNamesDemo
```

Kết quả logic/Unicode của chương trình:

```text
Tên chuẩn: UTF-8
Cùng charset: true
UTF-8 hex: 41c3a9
Giải mã UTF-8: Aé
Giải mã Latin-1: AÃ©
Hỗ trợ UTF-8: true
```

Giải thích:

1. `Charset.forName("uTf-8")` có thể tra cứu UTF-8 bất kể chữ hoa/thường, nên `equals` trả `true`.
2. Chữ `A` được mã hóa thành `41`; `é` thành `C3 A9`. `HexFormat` có trong Java 17, mặc định in chữ hex thường.
3. Giải mã đúng cùng UTF-8 tái lập `Aé`. Giải mã nhầm Latin-1 cho `AÃ©` vì hai byte `C3`, `A9` được diễn giải thành hai ký tự Latin-1 khác.
4. `UTF-8` thuộc bộ mã Java SE bắt buộc hỗ trợ, nên `isSupported("UTF-8")` trả `true`.

Lưu mã nguồn với UTF-8 để các ký tự có dấu được biên dịch đúng. `javac -encoding UTF-8` làm rõ charset của **tệp mã nguồn**; nó không tự chọn charset cho `getBytes` hay `new String`. Việc hiển thị tiếng Việt/`é` trên terminal cũng cần terminal/font hỗ trợ Unicode.

## 5. Tên charset động, hỗ trợ và ngoại lệ

Với charset đến từ cấu hình, cần hiểu sự khác nhau giữa “tên sai cú pháp” và “tên hợp lệ nhưng runtime không hỗ trợ”.

```java
import java.nio.charset.Charset;
import java.nio.charset.IllegalCharsetNameException;
import java.nio.charset.UnsupportedCharsetException;

public class ResolveCharsetDemo {
    public static void main(String[] args) {
        for (String name : new String[]{"UTF-8", "x-demo-unknown-charset", "bad name!"}) {
            try {
                Charset charset = Charset.forName(name);
                System.out.println(name + " => " + charset.name());
            } catch (IllegalCharsetNameException e) {
                System.out.println(name + " => tên không hợp lệ");
            } catch (UnsupportedCharsetException e) {
                System.out.println(name + " => không được hỗ trợ");
            }
        }
    }
}
```

Đây là chương trình độc lập, nhưng `"x-demo-unknown-charset"` chỉ là tên minh họa: phần mềm có provider charset tự bổ sung có thể hỗ trợ tên đó, vì vậy không coi đầu ra cho tên giả là bất biến trên mọi runtime.

- `IllegalCharsetNameException`: chuỗi tên vi phạm cú pháp hợp lệ (ví dụ chứa dấu cách hoặc dấu chấm than không được phép ở vị trí đó).
- `UnsupportedCharsetException`: tên có cú pháp hợp lệ nhưng không tìm được provider hỗ trợ.
- `Charset.isSupported(name)`: có thể kiểm tra trước với **tên đúng cú pháp**, nhưng vẫn phải xử lý lỗi cú pháp và không giả định mọi tên đều có mặt trên mọi môi trường.
- `NullPointerException`: có thể xảy ra khi đưa `null` vào API tra cứu tên.

Nếu chương trình chỉ hỗ trợ UTF-8 theo giao thức, có thể **kiểm tra tên được cho phép** rồi dùng `StandardCharsets.UTF_8`; không nhất thiết phải chấp nhận mọi charset mà máy chủ tình cờ có. Khi lưu cấu hình, ưu tiên `charset.name()` làm dạng biểu diễn chuẩn và ghi rõ charset trong metadata/giao thức.

## 6. Chuyển đổi đúng ở ranh giới I/O

### Chuỗi, mảng byte và file

Các API sau nhận `Charset` trực tiếp:

| Mục đích | Ví dụ |
| --- | --- |
| String → byte[] | `text.getBytes(StandardCharsets.UTF_8)` |
| byte[] → String | `new String(bytes, StandardCharsets.UTF_8)` |
| Đọc file thành String | `Files.readString(path, StandardCharsets.UTF_8)` |
| Ghi String vào file | `Files.writeString(path, text, StandardCharsets.UTF_8)` |
| Byte stream → reader | `new InputStreamReader(input, StandardCharsets.UTF_8)` |
| Writer → byte stream | `new OutputStreamWriter(output, StandardCharsets.UTF_8)` |

Ví dụ sử dụng `Files`, với `path` là `Path` hợp lệ và `text` là `String`:

```java
Files.writeString(path, text, StandardCharsets.UTF_8);
String restored = Files.readString(path, StandardCharsets.UTF_8);
```

Đây là **đoạn mã minh họa**, không phải chương trình độc lập; cần import `java.nio.file.Files`, `java.nio.file.Path` và xử lý `IOException`. Với file vừa ghi, thao tác ghi mặc định có thể tạo hoặc cắt ngắn file đích; tránh dùng trên dữ liệu quan trọng khi chưa xác định đường dẫn.

Với byte stream, nên chỉ rõ charset ở **bước chuyển byte ↔ ký tự**. Ví dụ khi nhận HTTP response hoặc đọc socket, việc đọc `InputStream` chỉ tạo ra byte; đến khi tạo `InputStreamReader` hay giải mã dữ liệu mới cần áp dụng charset phù hợp với giao thức. `BufferedReader` và `BufferedWriter` chỉ bổ sung bộ đệm/tiện ích xử lý dòng, không tự sửa được lỗi dùng sai charset.

### Không lệ thuộc charset mặc định

Các API không truyền charset có thể sử dụng **charset mặc định của môi trường hoặc hợp đồng riêng của API**. Trên Java 17, charset mặc định thường phụ thuộc cấu hình hệ điều hành và JVM; từ Java 18, JEP 400 quy định UTF-8 là mặc định trong phần lớn trường hợp, với một số ngoại lệ/chế độ tương thích. Vì vậy không nên coi việc chạy đúng trên máy cá nhân là bảo đảm khi chuyển sang máy khác.

`Charset.defaultCharset()` dùng để **quan sát** lựa chọn mặc định; không nên lấy nó thay một charset được giao thức/tệp quy định. Với nội dung mới do ứng dụng kiểm soát, thống nhất rõ UTF-8 ở cả phía ghi và phía đọc.

Một số định dạng/giao thức có charset quy định riêng, hoặc thông tin BOM/metadata. Khi đọc nội dung có sẵn, cần tuân theo chuẩn cụ thể của định dạng thay vì áp đặt UTF-8 chỉ vì đó là lựa chọn tốt cho file mới.

## 7. Mã hóa ký tự không thể biểu diễn và dữ liệu byte sai

Sự khác nhau giữa hai tình huống:

- **Unmappable character:** chuỗi Unicode có ký tự không thể được biểu diễn trong charset đích. Ví dụ `é` không thể mã hóa trong US-ASCII.
- **Malformed input:** dãy byte không tuân theo quy tắc mã hóa khi decode. Ví dụ `C3 28` không phải chuỗi byte UTF-8 hợp lệ, vì `C3` cần một byte tiếp nối `80..BF` nhưng `28` không phải byte tiếp nối.

Những API tiện lợi như `String.getBytes(Charset)` và `new String(bytes, Charset)` thường **thay dữ liệu lỗi bằng ký tự/byte thay thế**. Điều này giúp xử lý đơn giản nhưng có thể âm thầm làm mất hoặc đổi dữ liệu. Khi cần phát hiện lỗi thay vì thay thế, dùng `CharsetEncoder`/`CharsetDecoder` cùng `CodingErrorAction.REPORT`.

Ví dụ độc lập **`StrictCharsetDemo.java`**:

```java
import java.nio.ByteBuffer;
import java.nio.CharBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;

public class StrictCharsetDemo {
    public static void main(String[] args) {
        byte[] invalidUtf8 = {(byte) 0xC3, 0x28};
        String replaced = new String(invalidUtf8, StandardCharsets.UTF_8);
        System.out.println("Có ký tự thay thế: "
                + (replaced.codePointAt(0) == 0xFFFD));

        try {
            StandardCharsets.UTF_8.newDecoder()
                    .onMalformedInput(CodingErrorAction.REPORT)
                    .onUnmappableCharacter(CodingErrorAction.REPORT)
                    .decode(ByteBuffer.wrap(invalidUtf8));
            System.out.println("Decode thành công");
        } catch (CharacterCodingException e) {
            System.out.println("UTF-8 không hợp lệ");
        }

        try {
            StandardCharsets.US_ASCII.newEncoder()
                    .onUnmappableCharacter(CodingErrorAction.REPORT)
                    .encode(CharBuffer.wrap("é"));
            System.out.println("Encode thành công");
        } catch (CharacterCodingException e) {
            System.out.println("ASCII không mã hóa được é");
        }
    }
}
```

Chạy bằng Java 17+:

```bash
javac -encoding UTF-8 StrictCharsetDemo.java
java StrictCharsetDemo
```

Đầu ra:

```text
Có ký tự thay thế: true
UTF-8 không hợp lệ
ASCII không mã hóa được é
```

Chữ thay thế Unicode **U+FFFD** xuất hiện khi decode chuỗi byte UTF-8 lỗi bằng `new String(bytes, UTF_8)`. Khi bật `REPORT`, `decode` ném `CharacterCodingException` (hoặc lớp con) để chương trình tự quyết định cách xử lý. Với encoder ASCII, `é` không được biểu diễn nên báo lỗi thay vì âm thầm thay thành `?`.

Không dùng `CodingErrorAction.REPLACE` nếu tác vụ đòi hỏi bảo toàn dữ liệu chính xác; ngược lại, nếu nghiệp vụ cho phép thay thế, cần ghi rõ cách xử lý dữ liệu lỗi.

## 8. UTF-8, UTF-16, BOM và giới hạn của `String.length()`

UTF-8 lưu mỗi Unicode code point bằng 1–4 byte. UTF-16 lưu một code point trong một hoặc hai **đơn vị mã 16 bit**. Một `char` Java là một **UTF-16 code unit**, không phải lúc nào cũng là một ký tự Unicode hoàn chỉnh.

Chẳng hạn ký tự biểu tượng nằm ngoài Basic Multilingual Plane có thể có `String.length() == 2` (cặp surrogate) trong khi mã UTF-8 gồm 4 byte. Không dùng `String.length()` làm số byte của bản mã hóa; muốn biết dung lượng thực tế phải encode và kiểm tra `byte[].length`.

**BOM (Byte Order Mark)** có thể đánh dấu thứ tự byte trong một số dạng Unicode. `StandardCharsets.UTF_16` xử lý BOM theo quy tắc của UTF-16, trong khi `UTF_16BE`/`UTF_16LE` quy định byte order tường minh. UTF-8 **không yêu cầu BOM**; một file UTF-8 có BOM có thể mở đầu bằng ba byte `EF BB BF`. Tùy bộ đọc, BOM UTF-8 có thể xuất hiện như ký tự `U+FEFF` trong chuỗi kết quả thay vì tự động bị bỏ đi. Nếu định dạng cho phép hoặc yêu cầu BOM, cần xử lý theo hợp đồng cụ thể của định dạng đó.

Không dựa vào việc “nhìn thấy tiếng Việt đúng” để chứng minh hai phía dùng cùng charset: văn bản thuần ASCII nhiều khi cho đầu ra giống nhau dưới nhiều charset. Hãy kiểm tra với ký tự ngoài ASCII và so sánh byte khi chẩn đoán lỗi.

## 9. Sai lầm thường gặp và cách phòng tránh

| Sai lầm | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Ghi UTF-8, đọc ISO-8859-1 | Văn bản sai dấu, ví dụ `é` thành `Ã©` | Thống nhất charset lúc ghi và lúc đọc |
| Chuyển chuỗi sang byte không truyền charset | Phụ thuộc hợp đồng API/cấu hình runtime | Truyền `StandardCharsets.UTF_8` nếu định dạng cho phép |
| Dùng `StandardCharsets.UTF_8.toString()` để suy luận cú pháp bất kỳ | Nhầm tên charset với tên hằng hoặc alias | Dùng `name()` và tên chuẩn `UTF-8` |
| Xem `String.length()` là số byte | Sai với ký tự không ASCII/emoji | Dùng `text.getBytes(charset).length` |
| Dùng ASCII/Latin-1 cho văn bản Unicode tùy ý | Ký tự ngoài bộ mã bị thay hoặc báo lỗi | Dùng UTF-8 hoặc chọn bộ mã đúng yêu cầu |
| Decode byte lỗi bằng API thay thế nhưng không kiểm tra | Mất thông tin đầu vào mà không biết | Dùng `CharsetDecoder` với `REPORT` khi cần nghiêm ngặt |
| Tưởng mọi alias đều được hỗ trợ | Chạy được ở máy này nhưng không ở máy khác | Dùng sáu charset bắt buộc của `StandardCharsets` và tên chuẩn |
| Lẫn BOM UTF-8 với ký tự nội dung | Chuỗi có thêm `U+FEFF` đầu chuỗi | Đọc và xử lý BOM đúng quy định của file |

**Bài thực hành:** Encode `"Aé"` bằng `UTF_8` và `ISO_8859_1`. So sánh byte: UTF-8 là `41 C3 A9`, ISO-8859-1 là `41 E9`. Sau đó decode mỗi mảng bằng đúng charset của nó để nhận lại `"Aé"`; thử decode sai charset để quan sát kết quả. Đổi `é` thành ký tự tiếng Việt hoặc emoji và thử xem charset nào không thể biểu diễn ký tự đó.

**Ghi nhớ:** `Charset` là đối tượng mô tả bộ mã; `StandardCharsets` cung cấp sáu bộ mã bảo đảm có sẵn; tên charset có **tên chuẩn** và có thể có **alias**. Muốn bảo toàn văn bản khi I/O, chỉ rõ và thống nhất charset ở cả phía **encode** và **decode**; khi dữ liệu phải chính xác, xử lý malformed/unmappable một cách tường minh.