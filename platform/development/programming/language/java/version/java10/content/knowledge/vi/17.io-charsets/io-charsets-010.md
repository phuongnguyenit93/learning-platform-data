# Phân biệt tham số `Charset` với tên bộ mã dạng `String` trong Java I/O

*Chủ đề cha: Charset trong I/O (Java 10). Bài học giải thích đúng vai trò của đối tượng `java.nio.charset.Charset` so với chuỗi tên bộ mã `String` khi làm việc với `Reader`, `Writer`, `Files` và chuyển đổi `String` ↔ byte. Chỉ trình bày API và nguyên tắc còn được sử dụng trong Java hiện đại; các chương trình hoàn chỉnh chạy trên JDK 17 trở lên.*

## 1. Tư duy cốt lõi: tên bộ mã không phải đối tượng Charset

Khi đọc hoặc ghi **văn bản dưới dạng byte**, Java cần biết bộ mã (charset) để chuyển đổi:

```text
bytes -- CharsetDecoder --> các đơn vị char Java
các đơn vị char Java -- CharsetEncoder --> bytes
```

Có hai hình thức thường gặp để **chỉ định** bộ mã cho API:

1. **Đối tượng `Charset`**, ví dụ `StandardCharsets.UTF_8` hoặc kết quả `Charset.forName("UTF-8")`. Đây là một đối tượng thể hiện một bộ mã mà JVM hỗ trợ, được truyền trực tiếp vào API nhận tham số `Charset`.
2. **Tên bộ mã dạng `String`**, ví dụ `"UTF-8"` hoặc `"ISO-8859-1"`. Đây chỉ là văn bản đặt tên bộ mã. Một số constructor/phương thức Java chấp nhận tên đó và sẽ tự tra cứu charset tương ứng; một số API khác **chỉ chấp nhận `Charset`**.

Đặt cạnh nhau:

```java
// Cùng yêu cầu giải mã theo UTF-8 nhưng khác kiểu tham số:
var reader1 = new java.io.InputStreamReader(
        input, java.nio.charset.StandardCharsets.UTF_8); // Charset

var reader2 = new java.io.InputStreamReader(
        input, "UTF-8");                                  // String charsetName
```

Đây là **đoạn minh họa** với `input` là `InputStream` đã có. Không được tự tạo cả hai Reader trên cùng một input đang được đọc rồi đọc đan xen: bộ đệm và vị trí nguồn có thể làm dữ liệu bị đọc sai. Mỗi lời gọi trên thể hiện **một cách lựa chọn riêng**.

Sự khác biệt chính nằm ở **kiểu tham số, bước phân giải tên và loại ngoại lệ cần xử lý**, chứ không phải ở việc hai tên `UTF-8` có “bảng mã khác nhau”. Khi hai cách cùng chọn đúng UTF-8, quá trình decode tuân theo cùng bộ mã.

**Khuyến nghị:** Với charset được cố định trong mã nguồn, ưu tiên `StandardCharsets.UTF_8` hoặc hằng `StandardCharsets` phù hợp. Với tên lấy từ cấu hình, chuyển tên thành `Charset` qua `Charset.forName(...)` tại một ranh giới rõ ràng, kiểm tra lỗi cấu hình, rồi truyền đối tượng `Charset` cho các API I/O.

## 2. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt `Charset` object với `String` chứa tên mã hóa, tránh gán và truyền nhầm kiểu.
2. Biết những API I/O nào nhận `Charset`, những API nào còn hỗ trợ overload nhận tên `String`, và lúc nào không có overload `String`.
3. Dùng `StandardCharsets` khi charset cố định, `Charset.forName` khi tên charset được cung cấp động.
4. Hiểu tên **canonical**, **alias**, việc không phân biệt chữ hoa/thường và cách kiểm tra charset có được hỗ trợ.
5. Phân biệt `UnsupportedEncodingException` (checked ở một số overload `String`) với `UnsupportedCharsetException` và `IllegalCharsetNameException` (unchecked khi phân giải `Charset`).
6. Viết code đọc/ghi UTF-8 đúng ở hai ranh giới byte ↔ ký tự, xử lý file bằng `Files.newBufferedReader`/`newBufferedWriter`.
7. Nhận diện lỗi chọn sai charset gây mojibake, lỗi dữ liệu byte không hợp lệ và giới hạn của việc kiểm tra tên bộ mã.
8. Không suy luận số byte từ `String.length()` hoặc `Reader.transferTo`; kiểm thử cả văn bản có dấu và emoji.
9. Tránh phụ thuộc vào charset mặc định của môi trường khi giao thức/định dạng đã chỉ rõ mã hóa.

## 3. Các kiểu và giá trị liên quan

| Biểu thức | Kiểu Java | Vai trò |
| --- | --- | --- |
| `"UTF-8"` | `String` | Tên bộ mã, chưa phải đối tượng charset |
| `StandardCharsets.UTF_8` | `Charset` | Đối tượng UTF-8 chuẩn được Java SE cung cấp |
| `Charset.forName("UTF-8")` | `Charset` | Phân giải tên được cung cấp thành đối tượng Charset |
| `Charset.defaultCharset()` | `Charset` | Charset mặc định của JVM cho các API sử dụng mặc định |
| `charset.name()` | `String` | Tên canonical của đối tượng Charset |
| `charset.aliases()` | `Set<String>` | Các tên thay thế được implementation hỗ trợ |
| `Charset.isSupported(name)` | `boolean` | Kiểm tra tên hợp lệ có charset được hỗ trợ không |
| `String.getBytes(charset)` | `byte[]` | Mã hóa nội dung chuỗi ra byte |
| `new String(bytes, charset)` | `String` | Giải mã các byte thành chuỗi |

`Charset` thuộc package `java.nio.charset`. `StandardCharsets` là lớp chứa các đối tượng `Charset` được định nghĩa sẵn; **không** phải danh sách tên `String`. Ví dụ:

```java
import java.nio.charset.Charset;
import java.nio.charset.StandardCharsets;

Charset chosen = StandardCharsets.UTF_8;      // Hợp lệ
String name = chosen.name();                 // "UTF-8"
Charset dynamic = Charset.forName(name);     // Hợp lệ

// Charset invalid = "UTF-8";               // Không biên dịch
// String invalidName = StandardCharsets.UTF_8; // Không biên dịch
```

Các đoạn trên là ví dụ khai báo trong phạm vi lớp/phương thức thích hợp, không cần tạo cả một chương trình riêng để hiểu kiểu. **`Charset` là đối tượng đại diện bộ mã**, còn `String` là chuỗi tên phải được giải quyết thành bộ mã tương ứng ở nơi API cần nó.

### 3.1. Đối tượng Charset không tự encode/decode khi vừa được tạo

`Charset.forName("UTF-8")` chỉ tìm một đối tượng bộ mã được hỗ trợ. Nó **không** đọc file, không giải mã byte và không tự sửa chuỗi lỗi. Quá trình chuyển byte ↔ ký tự diễn ra khi bạn gọi một API mã hóa/giải mã, ví dụ:

```java
var charset = java.nio.charset.Charset.forName("UTF-8");
var bytes = "Java".getBytes(charset);
var decoded = new String(bytes, charset);
```

Từ việc `charset` hợp lệ **không thể suy ra** dữ liệu byte nguồn thực sự được mã hóa UTF-8. Đầu vào và đích phải có hợp đồng định dạng riêng.

## 4. Những bộ mã chuẩn: `StandardCharsets`

Java SE yêu cầu hỗ trợ một số bộ mã thông dụng; lớp `StandardCharsets` cung cấp các hằng đối tượng:

| Hằng | Bộ mã | Ghi chú |
| --- | --- | --- |
| `StandardCharsets.UTF_8` | UTF-8 | Thông dụng cho văn bản hiện đại |
| `StandardCharsets.US_ASCII` | US-ASCII | Phù hợp dữ liệu giới hạn đúng ASCII |
| `StandardCharsets.ISO_8859_1` | ISO-8859-1 | Chỉ khi hợp đồng nguồn/đích yêu cầu |
| `StandardCharsets.UTF_16` | UTF-16 | Có quy tắc byte order/BOM riêng |
| `StandardCharsets.UTF_16LE` | UTF-16 little-endian | Hợp đồng không giống UTF-16 tổng quát |
| `StandardCharsets.UTF_16BE` | UTF-16 big-endian | Hợp đồng không giống UTF-16 tổng quát |

Ví dụ khuyến nghị:

```java
var bytes = text.getBytes(
        java.nio.charset.StandardCharsets.UTF_8);
var restored = new String(
        bytes, java.nio.charset.StandardCharsets.UTF_8);
```

Đây là đoạn minh họa với biến `text` đã có. Hằng `StandardCharsets.UTF_8` không cần phân tích tên ở thời điểm chạy và không đòi caller tự bảo vệ khỏi lỗi “charset UTF-8 không được JVM hỗ trợ”, vì UTF-8 là charset chuẩn bắt buộc của Java SE.

**Không chọn UTF-8 chỉ vì đó là mặc định tiện lợi nếu định dạng nguồn quy định khác.** Với file ISO-8859-1 thực sự, phải giải mã theo ISO-8859-1; sau khi đã có ký tự Java đúng, có thể chọn UTF-8 ở phía ghi để chuyển mã.

## 5. `Charset.forName(...)` dùng khi tên đến từ cấu hình

Một ứng dụng có thể nhận tên bộ mã từ một tệp cấu hình, tham số dòng lệnh hoặc metadata của giao thức. Khi đó tên ban đầu là `String`:

```java
String charsetName = "UTF-8";            // Tên, chưa phân giải
java.nio.charset.Charset charset =
        java.nio.charset.Charset.forName(charsetName);
```

Cách này hữu ích vì:

- Bạn giải quyết tên **một lần** tại biên cấu hình thay vì truyền chuỗi đi qua nhiều lớp.
- Các lớp xử lý dữ liệu dùng kiểu `Charset` rõ ràng và không phải tự quản lý tên bộ mã.
- Bạn có nơi tập trung để trả thông báo khi tên sai hoặc JVM không hỗ trợ.
- Sau khi đã chọn đối tượng Charset, cùng đối tượng có thể được truyền cho Reader, Writer và API chuyển đổi String ↔ byte.

Ví dụ helper hiện đại:

```java
// Đoạn minh họa bên trong một lớp:
static java.nio.charset.Charset resolveCharset(String requestedName) {
    java.util.Objects.requireNonNull(
            requestedName, "requestedName");

    try {
        return java.nio.charset.Charset.forName(requestedName);
    } catch (java.nio.charset.IllegalCharsetNameException |
             java.nio.charset.UnsupportedCharsetException ex) {
        throw new IllegalArgumentException(
                "Invalid or unsupported charset configuration", ex);
    }
}
```

`resolveCharset` không tự mở Reader/Writer. Nó chỉ chuyển một tên thành `Charset` hoặc báo lỗi rõ ở tầng cấu hình. Khi xử lý đầu vào từ người dùng/remote, cân nhắc **allowlist** charset mà hệ thống thật sự chấp nhận; việc JVM có hỗ trợ một charset không có nghĩa protocol hay format cho phép mọi charset.

### 5.1. Tên canonical, alias và chữ hoa/chữ thường

Java cho phép tên charset ở dạng canonical hoặc alias. Việc so sánh tên khi tra cứu **không phân biệt chữ hoa/thường**:

```java
var charset = java.nio.charset.Charset.forName("uTf-8");
System.out.println(charset.name()); // UTF-8
```

`"uTf-8"` và `"UTF-8"` đều nhận diện cùng charset chuẩn. `charset.name()` trả tên canonical; `charset.aliases()` trả các alias được hỗ trợ. Các alias có thể phụ thuộc vào implementation/nhà cung cấp charset; **không nên xây hợp đồng ứng dụng dựa vào một alias không được bảo đảm**.

Nếu cần kiểm tra hai giá trị charset có cùng ý nghĩa, dùng `charset.equals(StandardCharsets.UTF_8)` thay vì dựa vào `==` hoặc so sánh văn bản đầu vào có cùng kiểu chữ. Và không cố suy luận rằng việc so sánh chuỗi `"utf-8".equals("UTF-8")` sẽ tự bỏ qua khác biệt chữ hoa: đó chỉ là hai `String`.

### 5.2. `Charset.isSupported` không giải mã dữ liệu

```java
var ok = java.nio.charset.Charset.isSupported("UTF-8");
```

`ok` bằng `true` với Java SE. Tuy nhiên:

- `isSupported(name)` cho biết JVM có charset tương ứng hay không.
- Nó **không** bảo đảm bytes đang có được mã hóa theo charset đó hoặc bytes không bị hỏng.
- Với **tên sai cú pháp**, `isSupported` có thể ném `IllegalCharsetNameException` thay vì chỉ trả `false`. Không thay toàn bộ validation bằng `if (!Charset.isSupported(name))` mà bỏ qua ngoại lệ.
- Nếu định dùng charset đó ngay, `Charset.forName(name)` trực tiếp tại một điểm có xử lý lỗi thường rõ hơn việc kiểm tra trước rồi lại tra cứu.

### 5.3. Không tự tiện dùng fallback khi tên bị lỗi

Khi cấu hình nói dữ liệu là `"ISO-8859-1"` nhưng thực tế tên không được hỗ trợ hoặc gõ sai, âm thầm dùng UTF-8 có thể làm hỏng dữ liệu. Hãy quyết định theo hợp đồng: báo lỗi cấu hình, dừng nhập, hoặc dùng fallback **nếu định dạng thật sự quy định** một fallback. Phần xử lý “tên không tồn tại” khác với việc gặp byte không hợp lệ trong quá trình giải mã.

## 6. Hai nhóm overload và ngoại lệ: khác biệt quan trọng

Một số API cung cấp cả hai cách chỉ định charset:

```java
// Chữ ký của các constructor/method, chỉ để đọc API:
InputStreamReader(InputStream in, String charsetName)
        throws UnsupportedEncodingException;

InputStreamReader(InputStream in, Charset charset);

OutputStreamWriter(OutputStream out, String charsetName)
        throws UnsupportedEncodingException;

OutputStreamWriter(OutputStream out, Charset charset);
```

**Overload nhận `String charsetName` vẫn là API được hỗ trợ trong Java hiện đại**, không phải cú pháp đã bị xóa. Nhưng khi bạn biết charset hoặc đã phân giải nó, overload nhận đối tượng `Charset` giúp thiết kế an toàn kiểu và thường đơn giản hơn về checked exception.

| Cách gọi | Khi tên/bộ mã hợp lệ | Khi charset không tồn tại | Exception cần lưu ý |
| --- | --- | --- | --- |
| `new InputStreamReader(in, "UTF-8")` | Tạo Reader | Có thể thất bại ngay khi xây dựng | `UnsupportedEncodingException` (checked) |
| `new InputStreamReader(in, StandardCharsets.UTF_8)` | Tạo Reader | UTF-8 luôn được hỗ trợ theo Java SE | Không có `UnsupportedEncodingException` do tên |
| `new OutputStreamWriter(out, "UTF-8")` | Tạo Writer | Tên không được hỗ trợ | `UnsupportedEncodingException` (checked) |
| `new OutputStreamWriter(out, charset)` | Tạo Writer | `charset` đã được chọn trước | Không có `UnsupportedEncodingException` do tên |
| `Charset.forName(name)` | Trả đối tượng `Charset` | Tên hợp lệ nhưng không hỗ trợ | `UnsupportedCharsetException` (unchecked) |
| `Charset.forName(illegalName)` | Không tạo Charset | Tên sai cú pháp | `IllegalCharsetNameException` (unchecked) |

**Lưu ý:** việc dùng tham số `Charset` không bảo đảm mọi hoạt động I/O sau đó sẽ thành công. Khi đọc/ghi dữ liệu thật, vẫn có thể có `IOException`, lỗi malformed/unmappable data hoặc lỗi đóng luồng. Khác biệt được nhấn mạnh ở đây là **phân giải tên và ngoại lệ từ lựa chọn bộ mã**.

### 6.1. Checked vs unchecked là khác biệt ở API

`UnsupportedEncodingException` kế thừa `IOException`, là checked exception: code phải khai báo hoặc xử lý khi gọi overload `String` yêu cầu nó.

`UnsupportedCharsetException` và `IllegalCharsetNameException` là unchecked exception liên quan việc tra cứu `Charset`. Với `Charset.forName`, code có thể xử lý chúng tại **ranh giới cấu hình**, rồi mọi lớp xử lý I/O khác chỉ nhận `Charset` hợp lệ.

Đừng nói rằng “dùng Charset thì không còn exception” — điều đó không đúng. Ta chỉ chuyển việc nhận diện lỗi tên bộ mã sang một điểm có chủ đích, thay vì để mỗi lớp Reader/Writer tự xử lý tên chuỗi.

## 7. Chương trình Java 17+: cùng charset, hai dạng API

Tạo file **`CharsetVsNameDemo.java`**:

```java
import java.nio.charset.Charset;
import java.nio.charset.StandardCharsets;

public class CharsetVsNameDemo {
    public static void main(String[] args) throws Exception {
        // "Café 🌱" qua Unicode escape để mã nguồn có thể là ASCII.
        var text = "Caf\u00e9 \uD83C\uDF31";

        Charset expected = StandardCharsets.UTF_8;
        Charset fromName = Charset.forName("uTf-8");
        var bytes = text.getBytes(expected);

        System.out.println("canonical=" + fromName.name());
        System.out.println("sameCharset=" + expected.equals(fromName));
        System.out.println("supported="
                + Charset.isSupported("UTF-8"));
        System.out.println("sameText="
                + text.equals(new String(bytes, "UTF-8")));
        System.out.println("bytes=" + bytes.length);
        System.out.println("chars=" + text.length());
        System.out.println("codePoints="
                + text.codePointCount(0, text.length()));
    }
}
```

Chạy:

```bash
javac --release 17 CharsetVsNameDemo.java
java CharsetVsNameDemo
```

Stdout chính xác:

```text
canonical=UTF-8
sameCharset=true
supported=true
sameText=true
bytes=10
chars=7
codePoints=6
```

Giải thích:

- `fromName` là đối tượng `Charset` được phân giải từ `String "uTf-8"`; tên canonical trả về `UTF-8`.
- `StandardCharsets.UTF_8` và kết quả `Charset.forName(...)` biểu diễn cùng bộ mã.
- `new String(bytes, "UTF-8")` chọn overload nhận **tên dạng String**, hoạt động vì tên đúng và được hỗ trợ.
- Trong Java, chuỗi `Café 🌱` có **7 đơn vị `char` UTF-16** và **6 Unicode code point**; dạng UTF-8 dùng **10 byte**.
- `main` có `throws Exception` vì ví dụ gọi overload `new String(byte[], String charsetName)` có checked `UnsupportedEncodingException` trong chữ ký. Trong ứng dụng, có thể dùng `new String(bytes, StandardCharsets.UTF_8)` để tránh checked exception của **overload tên String**.

Không dựa vào việc console phải in chính ký tự emoji để kiểm tra: chương trình so sánh String và in các chỉ số ASCII, nên không phụ thuộc font/terminal encoding.

## 8. Chương trình Java 17+: lỗi khi tên bộ mã không hợp lệ

Tạo **`CharsetFailureDemo.java`**:

```java
import java.io.ByteArrayInputStream;
import java.io.InputStreamReader;
import java.io.UnsupportedEncodingException;
import java.nio.charset.Charset;
import java.nio.charset.IllegalCharsetNameException;
import java.nio.charset.UnsupportedCharsetException;

public class CharsetFailureDemo {
    public static void main(String[] args) throws Exception {
        var emptyBytes = new byte[0];

        try {
            new InputStreamReader(
                    new ByteArrayInputStream(emptyBytes),
                    "X-UNKNOWN-CHARSET");
        } catch (UnsupportedEncodingException ex) {
            System.out.println("string-overload="
                    + ex.getClass().getSimpleName());
        }

        try {
            Charset.forName("X-UNKNOWN-CHARSET");
        } catch (UnsupportedCharsetException ex) {
            System.out.println("object-lookup="
                    + ex.getClass().getSimpleName());
        }

        try {
            Charset.forName("BAD NAME!");
        } catch (IllegalCharsetNameException ex) {
            System.out.println("illegal-name="
                    + ex.getClass().getSimpleName());
        }
    }
}
```

Chạy:

```bash
javac --release 17 CharsetFailureDemo.java
java CharsetFailureDemo
```

Stdout:

```text
string-overload=UnsupportedEncodingException
object-lookup=UnsupportedCharsetException
illegal-name=IllegalCharsetNameException
```

Phân tích:

1. `"X-UNKNOWN-CHARSET"` có dạng tên hợp lệ nhưng không được hỗ trợ trong môi trường demo. Constructor nhận `String` của `InputStreamReader` báo `UnsupportedEncodingException`.
2. Với cùng tên đó, `Charset.forName` báo `UnsupportedCharsetException`.
3. `"BAD NAME!"` có khoảng trắng và dấu `!` không hợp lệ trong cú pháp tên Charset; `Charset.forName` báo `IllegalCharsetNameException`.
4. Hai nhánh sau là ngoại lệ unchecked; nhánh đầu là checked. Không gộp chúng thành cùng loại exception hoặc bắt mọi `Exception` rồi coi như “mã hóa sai”.

Chương trình minh họa hai **cách phân giải tên**, không cố giải mã dữ liệu byte nào vì input chỉ là mảng rỗng. Để kiểm tra bộ mã có thực sự dùng được cho dữ liệu hay không, cần bước đọc/ghi và kiểm thử byte/text thật.

## 9. Chọn `Charset` ở nơi mở Reader/Writer, không tại `transferTo`

Với byte stream:

```java
var charset = java.nio.charset.StandardCharsets.UTF_8;

try (var reader = new java.io.InputStreamReader(
             inputStream, charset);
     var writer = new java.io.OutputStreamWriter(
             outputStream, charset)) {
    long units = reader.transferTo(writer);
}
```

Đây là **đoạn minh họa trong method** với `inputStream`, `outputStream` có sẵn. `Reader.transferTo(Writer)` (Java 10+) chỉ chuyển các đơn vị ký tự Java; **không có tham số charset**. Charset đã được đặt ở hai lớp bridge: `InputStreamReader` đọc bytes → chars và `OutputStreamWriter` ghi chars → bytes.

So sánh:

```java
// Tên bộ mã String, yêu cầu caller xử lý UnsupportedEncodingException:
new java.io.InputStreamReader(inputStream, "UTF-8");

// Đối tượng Charset, không cần phân giải tên trong constructor:
new java.io.InputStreamReader(
        inputStream, java.nio.charset.StandardCharsets.UTF_8);
```

Sự khác biệt không phải là `Reader.transferTo` với tham số String sẽ copy byte, còn Charset thì copy ký tự. **Cả hai tạo Reader làm việc với ký tự sau khi decode**. Nếu chọn cùng một bộ mã, nội dung ký tự đã giải mã tương ứng như nhau theo hợp đồng charset.

### 9.1. Ví dụ hoàn chỉnh: byte ↔ char ↔ byte

Tạo **`StreamCharsetDemo.java`**:

```java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.InputStreamReader;
import java.io.OutputStreamWriter;
import java.nio.charset.Charset;
import java.nio.charset.StandardCharsets;
import java.util.Arrays;

public class StreamCharsetDemo {
    public static void main(String[] args) throws Exception {
        var text = "Caf\u00e9 \uD83C\uDF31";
        var source = text.getBytes(StandardCharsets.UTF_8);
        var output = new ByteArrayOutputStream();

        long charUnits;
        try (var reader = new InputStreamReader(
                     new ByteArrayInputStream(source),
                     StandardCharsets.UTF_8);
             var writer = new OutputStreamWriter(
                     output,
                     Charset.forName("UTF-8"))) {
            charUnits = reader.transferTo(writer);
        }

        System.out.println("charUnits=" + charUnits);
        System.out.println("outputBytes=" + output.size());
        System.out.println("equalText=" + text.equals(
                new String(output.toByteArray(),
                        StandardCharsets.UTF_8)));
        System.out.println("equalBytes="
                + Arrays.equals(source, output.toByteArray()));
    }
}
```

Chạy:

```bash
javac --release 17 StreamCharsetDemo.java
java StreamCharsetDemo
```

Stdout:

```text
charUnits=7
outputBytes=10
equalText=true
equalBytes=true
```

Ở ví dụ này, reader dùng hằng `StandardCharsets.UTF_8` còn writer dùng `Charset.forName("UTF-8")`. Hai cách cùng tạo đối tượng Charset mô tả UTF-8, nên nội dung text được giữ nguyên.

Lý do lấy `output.toByteArray()` **sau** khối try: Writer có bộ đệm/máy mã hóa; đóng/flush Writer giúp byte đầu ra được hoàn thành. `transferTo` không tự chịu trách nhiệm đóng Reader/Writer.

**Số ký tự trả về là `7`, số byte UTF-8 là `10`**; charset không biến mỗi ký tự thành đúng một byte. Với các ký tự ngoài BMP, một Unicode code point có thể được biểu diễn bởi hai đơn vị `char` UTF-16.

## 10. `Files.newBufferedReader`/`newBufferedWriter` nhận `Charset`, không nhận tên String

Đây là nguồn lỗi biên dịch rất thường gặp khi chuyển từ constructor `InputStreamReader` sang NIO. Các overload quan trọng:

```java
// Chữ ký đọc API, không phải chương trình độc lập:
Files.newBufferedReader(Path path, Charset cs);
Files.newBufferedWriter(Path path, Charset cs, OpenOption... options);
```

**Không có overload `Files.newBufferedReader(Path, String charsetName)`** hoặc `Files.newBufferedWriter(Path, String charsetName)` tương đương. Vì vậy:

```java
// Giả sử path là Path:
// Files.newBufferedReader(path, "UTF-8"); // Lỗi biên dịch
Files.newBufferedReader(path, java.nio.charset.StandardCharsets.UTF_8);

// Với cấu hình dạng String:
var cs = java.nio.charset.Charset.forName("UTF-8");
Files.newBufferedReader(path, cs); // Đúng
```

Những dòng trên là ví dụ trong một phương thức có xử lý `IOException` và đóng Reader. Trong code thật, nên đặt Reader trong `try-with-resources` thay vì tạo rồi bỏ qua như đoạn minh họa.

**Điểm cần biết:** `Files.newBufferedReader(path)` và `Files.newBufferedWriter(path)` không truyền `Charset` vẫn dùng **UTF-8 theo chính hợp đồng của Files API**. Do đó, một chương trình Java 17 dùng đúng hai overload này đã dùng UTF-8; không nên nói rằng chúng luôn theo charset mặc định nền tảng.

### 10.1. Chương trình file đầy đủ

Tạo **`FileCharsetDemo.java`**:

```java
import java.nio.charset.Charset;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;

public class FileCharsetDemo {
    public static void main(String[] args) throws Exception {
        var dir = Files.createTempDirectory("charset-name-demo-");
        var source = dir.resolve("source.txt");
        var target = dir.resolve("target.txt");

        var text = "Caf\u00e9 \uD83C\uDF31";
        Charset charset = Charset.forName("UTF-8");

        try {
            Files.writeString(source, text, charset);

            long chars;
            try (var reader = Files.newBufferedReader(source, charset);
                 var writer = Files.newBufferedWriter(target, charset)) {
                chars = reader.transferTo(writer);
            }

            System.out.println("fileChars=" + chars);
            System.out.println("fileEqual=" + text.equals(
                    Files.readString(target, StandardCharsets.UTF_8)));
        } finally {
            Files.deleteIfExists(target);
            Files.deleteIfExists(source);
            Files.deleteIfExists(dir);
        }
    }
}
```

Chạy:

```bash
javac --release 17 FileCharsetDemo.java
java FileCharsetDemo
```

Stdout:

```text
fileChars=7
fileEqual=true
```

Ví dụ tạo thư mục/file tạm, copy nội dung văn bản UTF-8 qua Reader/Writer rồi xóa sau khi dùng. `Files.writeString`, `newBufferedReader`, `newBufferedWriter` và `readString` đều nhận đối tượng `Charset`.

Với file thực tế, hãy quyết định rõ có cho phép tạo mới, ghi đè hay thêm nội dung. `Files.newBufferedWriter` có các `OpenOption` để kiểm soát hành vi; điều này **khác** việc chọn bộ mã. Không vì tên charset đã đúng mà coi chính sách ghi đè file cũng đúng.

## 11. `String.getBytes` và `new String(byte[], ...)`: cũng có hai overload

Hình thức truyền charset cho phép thực hiện chuyển byte ↔ ký tự ngay trong bộ nhớ:

```java
// Đoạn minh họa:
var text = "Caf\u00e9";

// Charset object: không có checked UnsupportedEncodingException do tên.
var bytes = text.getBytes(
        java.nio.charset.StandardCharsets.UTF_8);
var decoded = new String(
        bytes, java.nio.charset.StandardCharsets.UTF_8);

// String charset name: overload riêng, chữ ký có checked exception.
var bytes2 = text.getBytes("UTF-8");
var decoded2 = new String(bytes2, "UTF-8");
```

Hai dòng cuối cần nằm trong method khai báo `throws UnsupportedEncodingException`, hoặc trong khối xử lý thích hợp. Không nhầm `String.getBytes(Charset)` với `String.getBytes(String charsetName)` chỉ vì cùng có vẻ “UTF-8”.

**Không phải cứ viết tên charset dưới dạng String thì nội dung được mã hóa sai.** Khi tên được hỗ trợ và đúng với hợp đồng, kết quả có thể hoàn toàn chính xác. Sự khác nhau ở đây chủ yếu là **kiểu tham số, bước tra cứu tên và hành vi báo lỗi**.

### 11.1. `Charset` không phải `String` chứa byte UTF-8

Chú ý ba đối tượng rất khác:

```java
var charsetName = "UTF-8";                         // String
var charset = java.nio.charset.StandardCharsets.UTF_8; // Charset
var encodedData = "Hello".getBytes(charset);        // byte[]
```

`charsetName` không chứa văn bản đang được mã hóa; nó chỉ là nhãn. `charset` không phải các byte đã mã hóa; nó là thông tin/logic bộ mã. `encodedData` mới là byte của chuỗi `"Hello"` theo charset được chọn.

Đây là lỗi tư duy dễ xảy ra khi biến tên `encoding` được dùng mơ hồ cho cả tên, đối tượng và dãy byte. Đặt tên `charsetName`, `charset` và `utf8Bytes` theo đúng vai trò sẽ giúp đọc code rõ ràng hơn.

## 12. Chọn sai charset: tên đúng cú pháp vẫn có thể cho ký tự sai

`Charset.forName("ISO-8859-1")` là lời gọi **hợp lệ** và tạo một Charset được hỗ trợ. Nhưng nếu nguồn bytes là UTF-8, dùng ISO-8859-1 để giải mã có thể tạo **mojibake** — ký tự nhìn sai nhưng không nhất thiết có exception.

Tạo **`WrongCharsetDemo.java`**:

```java
import java.nio.charset.StandardCharsets;

public class WrongCharsetDemo {
    public static void main(String[] args) {
        var text = "Caf\u00e9";
        var bytes = text.getBytes(StandardCharsets.UTF_8);

        var correct = new String(bytes, StandardCharsets.UTF_8);
        var wrong = new String(bytes, StandardCharsets.ISO_8859_1);

        System.out.println("correct=" + correct.equals(text));
        System.out.println("wrong=" + wrong.equals(text));
        System.out.println("name=" + StandardCharsets.UTF_8.name());
    }
}
```

Chạy:

```bash
javac --release 17 WrongCharsetDemo.java
java WrongCharsetDemo
```

Stdout:

```text
correct=true
wrong=false
name=UTF-8
```

Ở đây cả hai `Charset` đều tồn tại và tên hợp lệ. Khác biệt đến từ việc **bytes ban đầu được mã hóa bằng UTF-8**; đọc như ISO-8859-1 không khôi phục đúng String gốc. Do vậy:

- **Tên hợp lệ** chưa chứng minh bộ mã **đúng với dữ liệu**.
- `Charset.isSupported(name) == true` chưa có nghĩa byte nguồn không bị hỏng.
- Thay writer sang UTF-8 sau khi đã decode nhầm không tự sửa các ký tự sai.
- Để kiểm thử encoding, dùng văn bản có dấu, emoji hoặc ký tự nằm ngoài ASCII thay vì chỉ `"ABC"`.
- Nếu cần bảo toàn bytes nguyên gốc (ảnh, ZIP, file binary), dùng API byte-oriented như `Files.copy` hoặc `InputStream.transferTo(OutputStream)`, không bọc Reader/Writer để giải mã tùy tiện.

## 13. Charset và tên bộ mã không giống chính sách lỗi ký tự

Ngay cả khi xác định đúng charset, input vẫn có thể chứa **byte malformed** theo charset đó, hoặc output chứa ký tự **không biểu diễn được** trong charset đích. Đây là lỗi dữ liệu/codec, **khác** “charset name không tồn tại”.

Cần phân biệt ba tầng:

| Tầng | Ví dụ lỗi | Cách xử lý |
| --- | --- | --- |
| Cú pháp tên mã | `"BAD NAME!"` | `IllegalCharsetNameException` khi gọi `Charset.forName` |
| Tên hợp lệ nhưng không hỗ trợ | `"X-UNKNOWN-CHARSET"` | `UnsupportedCharsetException` hoặc `UnsupportedEncodingException` tùy API |
| Dữ liệu thực tế không phù hợp | Byte UTF-8 malformed, ký tự không biểu diễn được bằng ISO-8859-1 | `CharsetDecoder`/`CharsetEncoder` với `CodingErrorAction` theo hợp đồng |

Nếu ứng dụng cần **báo lỗi thay vì thay ký tự**, sử dụng `CharsetDecoder` hoặc `CharsetEncoder` với `CodingErrorAction.REPORT` ở nơi chuyển byte ↔ char:

```java
// Đoạn minh họa:
var decoder = java.nio.charset.StandardCharsets.UTF_8
        .newDecoder()
        .onMalformedInput(
                java.nio.charset.CodingErrorAction.REPORT);

var reader = new java.io.InputStreamReader(inputStream, decoder);
```

`inputStream` là biến có sẵn và Reader cần được đóng theo quyền sở hữu tài nguyên. Một số constructor codec có thể thay các chuỗi lỗi bằng ký tự thay thế khi sử dụng mặc định, tùy API/cách cấu hình. **Không dùng khả năng phân giải tên String hay Charset object làm biện pháp bảo đảm mọi dữ liệu đều hợp lệ.**

Tương tự, một encoder của ISO-8859-1 với `onUnmappableCharacter(CodingErrorAction.REPORT)` có thể từ chối emoji không có biểu diễn trong charset đích. Nếu cần chuyển mã không mất dữ liệu, hãy xác định charset nguồn và đích, kiểm soát malformed/unmappable input, rồi validate dữ liệu đầu ra.

## 14. UTF-8 mặc định trong Java hiện đại: không suy đoán

Một vấn đề hay gây nhầm là “không truyền charset”:

```java
// Đều không truyền charset, nhưng hợp đồng ở tầng API khác nhau:
new java.io.InputStreamReader(inputStream);

java.nio.file.Files.newBufferedReader(path);
```

- `InputStreamReader(InputStream)` dùng **default charset** của runtime. Trên **JDK 17 và trước đó**, default charset có thể phụ thuộc hệ điều hành/locale; **từ JDK 18**, JEP 400 xác định UTF-8 là default charset cho các Java SE API liên quan (có các cơ chế tương thích và quy tắc ngoại lệ được tài liệu hóa).
- `Files.newBufferedReader(Path)` lại có hợp đồng riêng: **UTF-8**. Điều này đã đúng trên JDK 17; không phụ thuộc việc default charset của JVM ở runtime là gì.
- Từ khóa `var` không quyết định charset. Nó chỉ suy luận kiểu của biến, chẳng hạn `InputStreamReader`, `BufferedReader` hoặc `Charset`.
- Nếu file hoặc giao thức của bạn quy định mã hóa, hãy **chọn tường minh** thay vì dựa vào default không cần thiết.

`Charset.defaultCharset()` trả một đối tượng `Charset` cho default của JVM. Nó hữu ích khi ứng dụng **thật sự cần dùng default charset theo chính sách**, không phải khi format đã quy định UTF-8 hay một charset cụ thể. Trong các chương trình có yêu cầu tương thích đa môi trường, ghi rõ charset tại ranh giới I/O vẫn là cách dễ kiểm tra nhất.

Một lưu ý về console: cách terminal hiển thị Unicode còn phụ thuộc encoding của stdin/stdout, font và môi trường chạy. Nó **không nhất thiết** phản ánh charset bạn đã dùng để đọc/ghi file. Vì thế các chương trình trong bài ưu tiên kiểm tra String/byte và in giá trị boolean.

## 15. Cách chọn `Charset` theo kiến trúc ứng dụng

### 15.1. Charset cố định theo định dạng

Nếu mọi file trong hệ thống đều được định nghĩa là UTF-8:

```java
private static final java.nio.charset.Charset DATA_CHARSET =
        java.nio.charset.StandardCharsets.UTF_8;
```

Đây là một trường ví dụ bên trong một class. Khi đọc và ghi:

```java
// Trong method có Path source và target:
try (var reader = java.nio.file.Files.newBufferedReader(
             source, DATA_CHARSET);
     var writer = java.nio.file.Files.newBufferedWriter(
             target, DATA_CHARSET)) {
    reader.transferTo(writer);
}
```

Ưu điểm là hợp đồng charset hiện rõ, chỉ chọn một nơi và các API nhận cùng đối tượng. Tên `DATA_CHARSET` không chứa byte của file; nó là cấu hình kiểu `Charset`.

### 15.2. Charset đến từ cấu hình

Giả sử cấu hình chứa `"UTF-8"`:

```java
var configuredName = "UTF-8";          // String
var configuredCharset =
        java.nio.charset.Charset.forName(configuredName); // Charset
```

Dùng `configuredCharset` ở các lớp I/O. Nếu cấu hình bị gõ sai, xử lý lỗi ngay khi khởi động hoặc tại lúc đọc cấu hình. Tránh lưu chuỗi qua nhiều tầng rồi để các constructor khác nhau tự phân giải và ném ngoại lệ khác nhau.

Với dữ liệu không tin cậy, chọn whitelist charset theo giao thức trước khi gọi `Charset.forName`, tránh việc cho phép những bộ mã hợp lệ với JVM nhưng không hợp lệ cho format của bạn.

### 15.3. Charset nguồn và đích khác nhau

Dữ liệu vào ISO-8859-1 và cần xuất UTF-8:

```java
var sourceCharset =
        java.nio.charset.StandardCharsets.ISO_8859_1;
var targetCharset =
        java.nio.charset.StandardCharsets.UTF_8;

try (var reader = new java.io.InputStreamReader(
             inputStream, sourceCharset);
     var writer = new java.io.OutputStreamWriter(
             outputStream, targetCharset)) {
    reader.transferTo(writer);
}
```

Đây là code minh họa trong method với hai stream đã có. `Reader.transferTo` chuyển ký tự; lớp đọc/ghi bên ngoài quyết định charset hai đầu. Số byte đầu ra có thể khác số byte đầu vào, dù nội dung ký tự được bảo toàn nếu mọi ký tự biểu diễn được và dữ liệu hợp lệ.

Đừng chọn một `Charset` duy nhất chỉ vì muốn “tránh nhầm” nếu hợp đồng thật có hai encoding khác nhau. Tên biến rõ như `sourceCharset` và `targetCharset` giúp biểu đạt ý định chuyển mã.

## 16. Cần truyền tham số `String` hay `Charset` trong API mới?

Với code mới có thể lựa chọn:

- Ưu tiên **`Charset`** khi API cung cấp overload này; có kiểu rõ và xử lý việc tra cứu cấu hình ở một chỗ.
- Ưu tiên **`StandardCharsets`** với các charset chuẩn được định nghĩa cố định.
- Dùng **`Charset.forName(name)`** nếu tên thật sự đến từ cấu hình hoặc protocol; bắt lỗi tên sai/không hỗ trợ ở đúng ranh giới.
- Dùng overload **`String charsetName`** khi codebase hoặc API cụ thể yêu cầu nó. Nó vẫn được hỗ trợ, nhưng cần xử lý checked `UnsupportedEncodingException` theo chữ ký.
- Với `Files.newBufferedReader`/`newBufferedWriter`, **bắt buộc truyền `Charset`** nếu chỉ định mã hóa bằng đối số; tên `String` không khớp kiểu tham số.
- Không tự viết mã chuyển đổi kiểu mơ hồ bằng cast. `(Charset) "UTF-8"` không hợp lệ; phải chọn hằng hoặc phân giải tên.

**Không có quy tắc “String luôn sai, Charset luôn đúng dữ liệu”.** Cả hai cách có thể chọn đúng UTF-8, nhưng việc chọn bộ mã phải dựa vào hợp đồng dữ liệu, và đối tượng `Charset` làm việc với API hiện đại gọn, rõ hơn.

## 17. Debug lỗi tên charset và lỗi encoding: đi theo từng lớp

Nếu gặp dữ liệu có dấu bị biến thành ký tự lạ hoặc exception, kiểm tra theo thứ tự:

1. **Kiểm tra chữ ký API:** tham số là `Charset` hay `String charsetName`? Lỗi biên dịch vì `Files.newBufferedReader(path, "UTF-8")` không liên quan đến byte bị hỏng.
2. **Xem tên đã được phân giải chưa:** cấu hình `"UTF-8"` là String, `Charset.forName(...)` mới tạo đối tượng.
3. **Nhận diện ngoại lệ:** `UnsupportedEncodingException` ở overload String, `UnsupportedCharsetException` ở `Charset.forName` khi tên không hỗ trợ, `IllegalCharsetNameException` khi tên sai cú pháp.
4. **Đọc hợp đồng byte nguồn:** file thực sự là UTF-8, ISO-8859-1 hay một encoding khác? Không suy ra từ `Charset.isSupported`.
5. **Xác nhận Reader dùng charset nào:** đọc sai ở đây sẽ tạo mojibake trước khi Writer kịp ghi.
6. **Xác nhận Writer dùng charset nào:** charset đích phải hỗ trợ các ký tự cần xuất, hoặc có chính sách xử lý lỗi rõ.
7. **Kiểm tra bộ đệm và vòng đời:** Writer có thể cần flush/close để đưa hết bytes xuống output. `try-with-resources` phù hợp khi method sở hữu luồng.
8. **Phân biệt char/byte:** `String.length()` và `Reader.transferTo` không phải kích thước tệp; đo byte từ mảng byte hoặc `Files.size`.
9. **Có BOM, newline, Unicode normalization không?** Chúng liên quan định dạng/decoder và biến đổi nội dung, không phải lỗi do tên `Charset` đơn thuần.
10. **Kiểm thử dữ liệu không ASCII:** mẫu chỉ có chữ cái cơ bản khó phát hiện charset mismatch.
11. **Xem môi trường Java:** JDK 17 khác default charset của các API không truyền charset so với Java 18+ trong một số môi trường; `Files` có hợp đồng UTF-8 riêng.
12. **Tách lỗi định dạng khỏi lỗi mã hóa:** CSV, JSON, XML còn có cú pháp và quy tắc riêng; UTF-8 hợp lệ không có nghĩa dữ liệu hợp lệ với parser.
13. **Kiểm tra đầu ra bằng decode đúng charset**, không chỉ tin console hiển thị.
14. **Không thử các charset ngẫu nhiên rồi chọn cái “nhìn giống đúng”** nếu có đặc tả hoặc metadata đáng tin cậy.

## 18. Nhầm lẫn thường gặp

| Nhầm lẫn | Thực tế |
| --- | --- |
| “`"UTF-8"` là kiểu `Charset`.” | Đây là `String`; dùng `StandardCharsets.UTF_8` hoặc `Charset.forName("UTF-8")` để có `Charset` |
| “`Charset.forName` sẽ giải mã file ngay lập tức.” | Nó chỉ phân giải bộ mã; decode diễn ra ở Reader/String decoder |
| “Mọi API nhận tên charset dưới dạng String.” | Không; `Files.newBufferedReader(path, cs)` yêu cầu `Charset` |
| “Mọi API chỉ nhận Charset.” | Không; `InputStreamReader`/`OutputStreamWriter` còn overload `String charsetName` |
| “Tên sai luôn báo cùng một ngoại lệ.” | String overload có `UnsupportedEncodingException`; `Charset.forName` có `UnsupportedCharsetException`/`IllegalCharsetNameException` |
| “Dùng Charset object thì không thể có `IOException`.” | I/O và lỗi dữ liệu vẫn xảy ra khi đọc/ghi |
| “Tên `utf-8` khác tên `UTF-8` nên là hai bộ mã.” | Tra cứu Charset không phân biệt hoa/thường |
| “Alias nào cũng được mọi JVM hỗ trợ như nhau.” | Hỗ trợ alias phụ thuộc quy tắc/implementation; dùng tên canonical khi cần hợp đồng rõ |
| “`Charset.isSupported(name)` xác nhận dữ liệu byte đúng.” | Chỉ xác nhận JVM hỗ trợ bộ mã theo tên đó |
| “Chỉ cần đặt Writer là UTF-8 thì input sẽ đúng.” | Decode sai ở Reader không được Writer tự sửa |
| “`String.getBytes()` không tham số luôn UTF-8 trên Java 17.” | Default charset trên JDK 17 có thể phụ thuộc môi trường |
| “`Files.newBufferedReader(path)` luôn lấy default locale.” | Không: overload không Charset của Files dùng UTF-8 |
| “`Reader.transferTo` có tham số Charset.” | Không: Reader/Writer bao ngoài chọn encoding |
| “`transferTo` trả số byte.” | Nó trả số đơn vị char đã chuyển; byte tính ở tầng I/O byte |
| “UTF-8 cần đúng 1 byte cho mỗi ký tự.” | Sai với ký tự ngoài ASCII; emoji có thể dài nhiều byte |
| “Dữ liệu không gây exception thì charset đã đúng.” | Chọn sai charset có thể tạo ký tự sai nhưng vẫn decode được |
| “`Charset.defaultCharset()` phải dùng cho mọi file.” | Chỉ dùng nếu hợp đồng thực sự chọn default JVM |
| “Dùng `var charset = "UTF-8"` sẽ tự thành Charset.” | `var` suy luận String, không chuyển đổi kiểu |

## 19. Bài tập có đáp án

### Bài 1 — Xác định kiểu

```java
var a = "UTF-8";
var b = java.nio.charset.StandardCharsets.UTF_8;
var c = java.nio.charset.Charset.forName(a);
```

**Đáp án:** `a` có kiểu `String`; `b` và `c` đều có kiểu `Charset`. `var` không tự chuyển `a` thành đối tượng charset.

### Bài 2 — Vì sao code không biên dịch?

```java
// Giả sử path là java.nio.file.Path:
 // Files.newBufferedReader(path, "UTF-8");
```

**Đáp án:** overload của `Files.newBufferedReader` nhận `Charset`, không nhận `String` ở vị trí tham số thứ hai. Sửa `Files.newBufferedReader(path, StandardCharsets.UTF_8)` hoặc `Files.newBufferedReader(path, Charset.forName("UTF-8"))`, đồng thời xử lý `IOException` và đóng Reader.

### Bài 3 — Unsupported vs illegal name

```java
java.nio.charset.Charset.forName("X-UNKNOWN-CHARSET");
java.nio.charset.Charset.forName("BAD NAME!");
```

**Đáp án:** tên đầu có dạng hợp lệ nhưng không có charset tương ứng, nên `UnsupportedCharsetException` trong môi trường như ví dụ. Tên thứ hai sai cú pháp do khoảng trắng và `!`, nên `IllegalCharsetNameException`.

### Bài 4 — Cùng charset, overload khác nhau

Hai cách:

```java
new InputStreamReader(input, "UTF-8");
new InputStreamReader(input, StandardCharsets.UTF_8);
```

**Đáp án:** cả hai chọn UTF-8 khi tên được hỗ trợ và đúng; khác ở kiểu tham số và checked `UnsupportedEncodingException` của overload String. Các đoạn là minh họa độc lập, không nên tạo hai Reader cùng đọc đan xen trên một `InputStream` đã mở.

### Bài 5 — Mã hóa từ cấu hình

Bạn nhận chuỗi `charsetName` từ configuration. Nên làm gì trước khi mở file?

**Đáp án:** validate chính sách charset được phép, phân giải `Charset charset = Charset.forName(charsetName)` tại biên cấu hình, xử lý lỗi `IllegalCharsetNameException` và `UnsupportedCharsetException`, sau đó truyền `charset` vào Reader/Writer. Không cần lặp lại chuỗi tên qua mọi lớp I/O.

### Bài 6 — Chữ có dấu bị sai

Một byte array là UTF-8 của chuỗi `"Café"`. Đọc bằng ISO-8859-1 có chắc tạo chuỗi gốc?

**Đáp án:** không. ISO-8859-1 có thể giải mã byte thành ký tự, nhưng kết quả không giống văn bản gốc. Chỉ dùng charset theo đặc tả byte nguồn; chọn charset hợp lệ chưa đủ.

### Bài 7 — Dùng `Reader.transferTo`

```java
try (var reader = new InputStreamReader(input, StandardCharsets.UTF_8);
     var writer = new OutputStreamWriter(output, StandardCharsets.UTF_8)) {
    long count = reader.transferTo(writer);
}
```

**Đáp án:** Reader chọn UTF-8 đầu vào; Writer chọn UTF-8 đầu ra; `transferTo` chuyển ký tự giữa hai đối tượng, trả số `char` được chuyển, không trả số byte.

### Bài 8 — Charset không mặc định

Vì sao `InputStreamReader(input)` và `Files.newBufferedReader(path)` có thể khác hợp đồng charset trên JDK 17?

**Đáp án:** `InputStreamReader` không tham số Charset dùng default JVM (có thể theo môi trường trên JDK 17). `Files.newBufferedReader(path)` dùng UTF-8 theo hợp đồng API. Khi nguồn được quy định mã hóa cụ thể, truyền Charset tường minh sẽ dễ kiểm tra.

### Bài 9 — Ký tự ngoài ASCII

Chuỗi `"Caf\u00e9 \uD83C\uDF31"` có bao nhiêu `char` Java và bao nhiêu byte UTF-8?

**Đáp án:** 7 đơn vị `char`, 6 Unicode code point và 10 byte UTF-8. Tên bộ mã hay đối tượng Charset chỉ quy định cách mã hóa/giải mã, không làm ba khái niệm này đồng nhất.

### Bài 10 — Null và fallback

Nếu `charsetName` đến từ cấu hình và bị sai, có nên tự dùng UTF-8 cho mọi trường hợp?

**Đáp án:** không. Chỉ fallback nếu protocol/định dạng có hợp đồng fallback như vậy. Nếu không, báo lỗi cấu hình rõ ràng; việc dùng charset khác có thể âm thầm làm hỏng văn bản.

### Bài 11 — Đọc file từ API nào?

Bạn có `Path path` và charset chuẩn UTF-8. Viết cách đọc hiện đại, rõ nghĩa?

**Đáp án:**

```java
try (var reader = java.nio.file.Files.newBufferedReader(
        path, java.nio.charset.StandardCharsets.UTF_8)) {
    // Xử lý ký tự ở đây.
}
```

Không cần chuyển `StandardCharsets.UTF_8` thành String `"UTF-8"` để truyền vào Files.

## 20. Checklist trước khi đưa vào production

1. **Đầu vào là bytes hay ký tự?** Chỉ cần Charset khi đi qua ranh giới byte ↔ text.
2. **Định dạng/protocol quy định charset gì?** Chọn theo hợp đồng, không theo thói quen.
3. **Đã phân biệt `String` tên bộ mã với đối tượng `Charset` chưa?**
4. **Có hằng `StandardCharsets` phù hợp không?** Nếu cố định, ưu tiên hằng thay vì String.
5. **Tên đến từ config?** Gọi `Charset.forName` và xử lý lỗi tên sai/không hỗ trợ một lần.
6. **API có overload nhận `String` không?** Không tự truyền String cho `Files.newBufferedReader`.
7. **Có checked exception từ overload String không?** Xem chữ ký `UnsupportedEncodingException`.
8. **Đã phân biệt lỗi tên với lỗi dữ liệu charset?** Một tên hợp lệ không bảo đảm bytes hợp lệ.
9. **Cần nghiêm ngặt với malformed/unmappable data?** Dùng decoder/encoder có `CodingErrorAction.REPORT` nếu hợp đồng yêu cầu.
10. **Nguồn và đích có cùng charset không?** Nếu không, cấu hình riêng `sourceCharset`/`targetCharset`.
11. **Có phụ thuộc charset mặc định?** JDK 17/18+ và từng API có khác biệt quan trọng.
12. **Có đóng/flush Reader, Writer đúng không?** Charset không giải quyết ownership tài nguyên.
13. **Đang copy văn bản hay byte nguyên trạng?** Với binary chọn `Files.copy` hoặc I/O byte.
14. **Có kiểm thử văn bản phi ASCII?** Ít nhất gồm chữ có dấu và ký tự ngoài BMP khi domain hỗ trợ.
15. **Có định dùng `Charset.isSupported` để validate data?** Không: đó chỉ là kiểm tra hỗ trợ tên.
16. **Tên biến có rõ vai trò?** `charsetName` khác `charset`, `sourceBytes` khác `decodedText`.
17. **Có so sánh charset theo tên tùy tiện?** Dùng object `Charset`, `name()` và alias theo hợp đồng; tránh `==`.
18. **Có xử lý đúng lỗi runtime?** Phân biệt tên sai, codec lỗi, `IOException` và input bất hợp lệ.
19. **Có phụ thuộc stdout console để xác nhận dữ liệu?** Ưu tiên round-trip string/byte qua charset chỉ định.
20. **Có ghi rõ policy fallback?** Đừng âm thầm chuyển sang UTF-8 khi tên config sai nếu không được cho phép.

## 21. Tổng kết

Trong Java I/O, **`"UTF-8"` là một `String` đặt tên bộ mã**, còn **`StandardCharsets.UTF_8` và `Charset.forName("UTF-8")` là các đối tượng `Charset`**. Các overload nhận tên String còn được Java hỗ trợ, nhưng có bước tra cứu tên và một số chữ ký dùng checked `UnsupportedEncodingException`. Các API nhận đối tượng `Charset` giúp thể hiện kiểu rõ ràng; `Charset.forName` là công cụ phân giải cấu hình và có các lỗi tên không hợp lệ/không hỗ trợ riêng.

Đối tượng `Charset` chỉ đại diện bộ mã. Việc giải mã và mã hóa diễn ra khi `InputStreamReader`, `OutputStreamWriter`, `Files` hoặc phương thức chuyển đổi bytes/String được sử dụng; `Reader.transferTo` chỉ chuyển các đơn vị ký tự và không chọn encoding. **Hãy quyết định bộ mã theo hợp đồng nguồn và đích, ưu tiên `StandardCharsets` nếu cố định, dùng `Charset.forName` nếu cấu hình động, và kiểm thử dữ liệu thực tế** thay vì suy rằng một tên hợp lệ chắc chắn cho văn bản đúng.

### Tài liệu API tham khảo

- [Charset — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/Charset.html)
- [StandardCharsets — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/StandardCharsets.html)
- [InputStreamReader — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/InputStreamReader.html)
- [OutputStreamWriter — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/OutputStreamWriter.html)
- [Files — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html)
- [JEP 400: UTF-8 by Default](https://openjdk.org/jeps/400)