# Bảng mã trong Java: Tránh phụ thuộc bảng mã mặc định của môi trường

## 1. Vấn đề: cùng một chương trình, vì sao văn bản có thể bị sai ký tự?

Ứng dụng Java thường phải chuyển qua lại giữa **ký tự Unicode** trong `String` và **dãy byte** khi đọc/ghi file, kết nối mạng, nhận dữ liệu từ hệ thống khác hoặc lưu trữ. Để thực hiện chuyển đổi đó, chương trình cần biết **bảng mã ký tự** (*character encoding/charset*).

Nếu mã nguồn không chỉ rõ bảng mã, một số API sẽ sử dụng **default charset của JVM**. Cùng một chương trình, cùng những byte đầu vào nhưng chạy ở môi trường khác hoặc khi nâng JDK có thể nhận chuỗi khác; ngược lại, cùng `String` nhưng được ghi ra những byte khác nhau.

Ví dụ cách viết có phụ thuộc môi trường:

```java
byte[] bytes = message.getBytes();
String decoded = new String(bytes);
```

Hai phương thức trên dùng **default charset**. Chúng không nói với người đọc dữ liệu đang thuộc UTF-8, ISO-8859-1 hay charset nào khác.

Cách viết rõ ràng, phù hợp dữ liệu giao tiếp UTF-8:

```java
import java.nio.charset.StandardCharsets;

byte[] bytes = message.getBytes(StandardCharsets.UTF_8);
String decoded = new String(bytes, StandardCharsets.UTF_8);
```

Đây là **đoạn minh họa bên trong phương thức**, với `message` là biến `String` đã được định nghĩa. `StandardCharsets.UTF_8` là hằng số kiểu `Charset`, không phụ thuộc ngôn ngữ hệ điều hành.

**Quy tắc thực hành:** Chỉ định charset **tại ranh giới byte ↔ ký tự** theo hợp đồng dữ liệu. Với hệ thống mới chủ động lựa chọn định dạng văn bản, UTF-8 thường là lựa chọn phù hợp. Nếu hệ thống bên ngoài **định nghĩa charset khác**, phải dùng đúng charset đó; không tự ép mọi file thành UTF-8 chỉ vì UTF-8 phổ biến.

Bài này dùng kiến thức và API còn được hỗ trợ trong Java hiện đại (Java 17+), đồng thời giải thích chính xác sự thay đổi default charset từ JDK 18.

## 2. Phân biệt Unicode, `String`, byte và `Charset`

### 2.1. `String` không phải một mảng byte có bảng mã cố định

`String` của Java biểu diễn một chuỗi ký tự theo mô hình **Unicode**, các thao tác `char`/`length()` sử dụng đơn vị mã UTF-16 (*UTF-16 code units*). Dữ liệu bên trong JVM được tối ưu hoặc lưu trữ thế nào là chi tiết triển khai; **không nên suy từ cấu trúc lưu trữ nội bộ ra bảng mã của file**.

Một chuỗi:

```java
String name = "Cà phê";
```

không tự khai báo “được lưu dưới dạng UTF-8” mỗi khi bạn ghi ra file. Lệnh **mã hóa** `name.getBytes(charset)` mới xác định dãy byte sẽ được tạo.

Chiều ngược lại:

```java
String name = new String(bytes, charset);
```

là thao tác **giải mã**. Nếu `charset` sai, Java có thể biến các byte thành ký tự không mong muốn (*mojibake*) hoặc thay những chuỗi byte bất hợp lệ bằng ký tự thay thế.

### 2.2. Ba lớp cần phân biệt

| Thành phần | Ví dụ | Chịu trách nhiệm gì? |
| --- | --- | --- |
| Nội dung Unicode | `"Cà phê ☕"` | Ký tự cần biểu diễn |
| Charset | `StandardCharsets.UTF_8` | Quy tắc đổi ký tự thành byte và ngược lại |
| Byte sequence | `43 C3 A0 20 70 68 C3 AA 20 E2 98 95` | Dữ liệu thực trên file/network |

Ví dụ trên được tạo bằng UTF-8. Chuỗi `"Cà phê ☕"` có **8 UTF-16 code units** và khi mã hóa UTF-8 có **12 byte**. Số byte không bắt buộc bằng `String.length()`.

Vì sao khác nhau?

- `C`, khoảng trắng, `p`, `h` thuộc ASCII, mỗi ký tự chiếm 1 byte trong UTF-8.
- `à` và `ê` chiếm 2 byte mỗi ký tự trong UTF-8.
- `☕` chiếm 3 byte trong UTF-8.
- Các ký tự Unicode khác như nhiều emoji ngoài BMP có thể cần 4 byte UTF-8 và 2 code units UTF-16.

**Không dùng `String.length()` làm độ dài của payload UTF-8**, và đừng cắt byte ở giữa một chuỗi đa byte khi chia thông điệp. Nếu giao thức giới hạn số **byte**, hãy mã hóa bằng đúng charset rồi đo `bytes.length` hoặc dùng bộ mã hóa có kiểm soát.

### 2.3. Encoding không đồng nghĩa với locale hoặc normalization

- **Locale** (ví dụ `Locale.forLanguageTag("vi-VN")`) liên quan đến quy tắc ngôn ngữ/định dạng số-ngày và so sánh theo ngữ cảnh. Locale **không tự thay đổi charset** được truyền cho `new String(bytes, charset)`.
- **Unicode normalization** (NFC, NFD, …) quy định cách biểu diễn những chuỗi ký tự tương đương về mặt ngôn ngữ. Hai `String` nhìn giống nhau có thể chứa các code point khác nhau và do đó cho byte UTF-8 khác nhau.
- **Charset** giải quyết chuyển đổi ký tự ↔ byte. Nó không tự đảm bảo normalization, không tự chọn newline, và không tự sửa một file có dữ liệu đã bị hỏng.

Vì vậy, khi thiết kế định dạng bền vững cần quy định tường minh cả charset và những thuộc tính khác của dữ liệu nếu quan trọng.

## 3. `Charset.defaultCharset()` và sự thay đổi từ Java 18

### 3.1. Java 17 trở về trước

Trong JDK 17 và các phiên bản trước, **default charset thường phụ thuộc môi trường** khi JVM khởi chạy: cấu hình hệ điều hành, locale, code page và những lựa chọn triển khai.

Vì thế các API dùng mặc định có thể sinh byte khác nhau khi chạy trên:

- Một máy Windows có code page không phải UTF-8.
- Một máy Linux với locale UTF-8.
- Một container hoặc môi trường test có thiết lập locale khác môi trường phát triển.

Đoạn chẩn đoán:

```java
import java.nio.charset.Charset;

System.out.println(Charset.defaultCharset().name());
```

cho biết **default charset thực tế của JVM đang chạy**. Kết quả không được hard-code trong tài liệu như thể mọi môi trường Java 17 đều trả cùng một giá trị.

### 3.2. Java 18 trở đi: JEP 400 — UTF-8 by Default

Từ **JDK 18**, JEP 400 chuẩn hóa **UTF-8 làm default charset** cho các Java SE API vốn dùng default charset (với những khả năng cấu hình tương thích được JDK hỗ trợ). Điều này giảm khác biệt phổ biến giữa hệ điều hành và giúp nhiều ứng dụng hoạt động ổn định hơn.

**Nhưng kết luận “từ Java 18 không bao giờ cần chỉ định charset nữa” là sai**, vì:

1. Ứng dụng vẫn có thể phải chạy trên **JDK 17** hoặc môi trường tương thích được cấu hình khác.
2. Dữ liệu nguồn có thể là ISO-8859-1, UTF-16LE hoặc charset khác do **hợp đồng file/giao thức** quy định; default UTF-8 sẽ **giải mã sai**.
3. Một số API đặc thù có **charset cố định riêng** hoặc có quy tắc về console/standard streams, không đơn thuần tuân theo `Charset.defaultCharset()`.
4. Khi nâng từ JDK 17 lên 18+, hành vi của mã cũ đang dựa trên default charset có thể thay đổi dù code không sửa. Chỉ định tường minh tránh sự phụ thuộc này.
5. Charset mặc định là **cấu hình runtime**, không phải metadata tự động nằm trong dữ liệu. File đã ghi bằng charset A không thể được giải mã đúng bằng charset B chỉ vì JVM mới mặc định B.

JDK 18+ có cơ chế tương thích `-Dfile.encoding=COMPAT` theo tài liệu JDK để khảo sát cách mã hóa cũ phụ thuộc môi trường. Đây là **công cụ migration/chẩn đoán**, không phải giải pháp nên dựa vào để thiết kế giao thức mới. Với Java 17, không mặc định tuyên bố `file.encoding` là UTF-8 trên mọi máy.

**Quan trọng:** `System.out`/`System.err` và console có thể tuân theo những quy tắc mã hóa riêng, không nhất thiết giống default charset của file API. Đừng coi việc terminal hiển thị đúng hay sai tiếng Việt là bằng chứng duy nhất để kết luận file được mã hóa bằng charset nào.

### 3.3. Đừng sửa `file.encoding` ở giữa chương trình để “cứu” code

Ví dụ sau **không phải cách thiết kế nên dùng**:

```java
System.setProperty("file.encoding", "UTF-8");
byte[] bytes = text.getBytes(); // vẫn không tường minh theo hợp đồng dữ liệu
```

Đổi system property lúc chương trình đã chạy không phải cơ chế đáng tin để cập nhật những encoder/decoder hay default charset đã được xác định/cached bởi runtime và các thành phần khác. Hãy truyền đối tượng `Charset` **ngay tại API**:

```java
byte[] bytes = text.getBytes(StandardCharsets.UTF_8);
```

Nếu cần thay đổi hành vi của một ứng dụng có legacy defaults trong quá trình migration, phải kiểm tra đúng tài liệu và cấu hình tại **lúc khởi động JVM**, không giả định sửa property bất kỳ thời điểm nào đều có hiệu lực.

## 4. `StandardCharsets`: không phải tra cứu tên chuỗi thủ công

`java.nio.charset.StandardCharsets` cung cấp sẵn những charset chuẩn được Java hỗ trợ:

| Hằng số | Ý nghĩa | Khi nào dùng |
| --- | --- | --- |
| `StandardCharsets.UTF_8` | UTF-8 | Văn bản/JSON/file mới theo hợp đồng UTF-8 |
| `StandardCharsets.US_ASCII` | US-ASCII | Khi giao thức thật sự giới hạn 7-bit ASCII |
| `StandardCharsets.ISO_8859_1` | ISO-8859-1 (Latin-1) | Khi dữ liệu đã được định nghĩa rõ theo charset này |
| `StandardCharsets.UTF_16` | UTF-16 với quy tắc BOM/byte order tương ứng của charset | Chỉ khi định dạng chỉ rõ UTF-16 |
| `StandardCharsets.UTF_16BE` | UTF-16 big-endian | Khi byte order được quy định là BE |
| `StandardCharsets.UTF_16LE` | UTF-16 little-endian | Khi byte order được quy định là LE |

Các hằng số này có từ Java 7, vẫn hiện hành.

Ưu điểm:

- Tránh lỗi đánh máy như `"UTF8"`, `"utf-8"` không đồng nhất về cách viết hay mã hóa không tồn tại.
- Không cần xử lý việc tra cứu hỗ trợ ở mỗi lời gọi.
- Trình bày **ý định** rõ trong code review.
- Làm việc thuận tiện với các API nhận kiểu `Charset`.

Nếu bên tích hợp yêu cầu một charset được hỗ trợ nhưng không nằm trong danh sách chuẩn, có thể dùng:

```java
Charset cs = Charset.forName("windows-1252");
```

Đây là **minh họa** với import `java.nio.charset.Charset`; chỉ chọn tên charset đó nếu **hợp đồng dữ liệu thật sự yêu cầu** và môi trường chạy hỗ trợ. Đừng chọn một charset dựa trên suy đoán mã vùng hoặc font hiển thị.

**Ưu tiên overload nhận `Charset`** thay vì overload nhận `String charsetName` nếu cả hai đều có. Đối tượng `Charset` dễ kiểm soát và kiểm tra hơn khi truyền qua các tầng.

## 5. `String` ↔ `byte[]`: nơi thường mắc lỗi nhất

### 5.1. Không phụ thuộc default charset

```java
import java.nio.charset.StandardCharsets;
import java.util.Arrays;

String text = "Cà phê";
byte[] bytes = text.getBytes(StandardCharsets.UTF_8);

String restored = new String(bytes, StandardCharsets.UTF_8);
System.out.println(text.equals(restored)); // true
```

Đây là **đoạn minh họa trong phương thức**, không phải chương trình độc lập. `Arrays` không cần thiết trong đoạn minh họa này, có thể bỏ import đó.

Đầu vào và đầu ra được giải thích rõ:

- `getBytes(StandardCharsets.UTF_8)` mã hóa Unicode thành UTF-8.
- `new String(bytes, StandardCharsets.UTF_8)` giải mã UTF-8 về Unicode.
- Để round-trip đúng, dữ liệu byte phải thực sự đúng UTF-8 và không bị thay đổi trong quá trình truyền/lưu.

### 5.2. API gây phụ thuộc môi trường khi quên charset

```java
byte[] encoded = text.getBytes();  // default charset
String decoded = new String(bytes);// default charset
```

Các lời gọi không có charset là **hành vi có thật, hợp lệ**, nhưng không diễn đạt hợp đồng. Nếu upstream tạo byte bằng UTF-8 mà downstream lại đọc bằng default charset khác, lỗi có thể không xuất hiện với văn bản chỉ chứa ASCII, rồi bùng phát khi gặp tiếng Việt, ký tự đặc biệt hoặc emoji.

**Sai lầm hay gặp:** Kiểm thử bằng `"hello"` trên môi trường UTF-8 và kết luận code đã xử lý Unicode đúng. Nhiều charset đều mã hóa ASCII cơ bản như nhau, nên test đó không phát hiện sai bảng mã.

### 5.3. Không cần chuyển byte qua `String` nếu dữ liệu thật sự là nhị phân

Với ảnh, file ZIP, byte ký số, byte nén hoặc payload mã hóa, **không** làm thế này:

```java
String intermediate = new String(binaryData, StandardCharsets.UTF_8);
byte[] reconstructed = intermediate.getBytes(StandardCharsets.UTF_8);
```

Nếu `binaryData` không phải văn bản UTF-8 hợp lệ, bước giải mã có thể thay byte bất hợp lệ bằng ký tự thay thế, khiến dữ liệu nhị phân **mất tính nguyên vẹn**.

Hãy giữ `byte[]` hoặc `ByteBuffer` nếu API là binary. Nếu buộc đưa binary vào kênh chỉ nhận text, dùng một dạng encoding **dành cho dữ liệu nhị phân** như Base64 theo hợp đồng, thay vì coi byte tùy ý là UTF-8:

```java
String base64 = java.util.Base64.getEncoder().encodeToString(binaryData);
byte[] exactBytes = java.util.Base64.getDecoder().decode(base64);
```

Base64 là cách biểu diễn byte trong chuỗi ký tự, **không phải** charset dùng để giải mã văn bản. Đây là hai lớp encoding khác nhau, cần tránh nhầm lẫn.

## 6. Đọc/ghi stream: truyền `Charset` ngay tại `Reader`/`Writer`

### 6.1. `InputStreamReader`

`InputStream` cung cấp byte; `Reader` cung cấp ký tự Unicode. `InputStreamReader` là cầu nối.

Không tường minh:

```java
Reader reader = new InputStreamReader(inputStream);
```

Tường minh:

```java
Reader reader = new InputStreamReader(
        inputStream, StandardCharsets.UTF_8);
```

Hai đoạn trên là **minh họa**, với `inputStream` có kiểu `InputStream`. Nếu stream chứa UTF-8, chỉ cách thứ hai thể hiện đúng ý định mà không phụ thuộc default charset JVM.

Sử dụng `try-with-resources` khi **phương thức thực sự sở hữu stream** và cần đóng chúng:

```java
try (InputStream input = Files.newInputStream(path);
     Reader reader = new InputStreamReader(input, StandardCharsets.UTF_8)) {
    // Đọc ký tự từ reader.
}
```

Đây là **minh họa** với các import `java.io`, `java.nio.file`, `java.nio.charset`. Một số wrapper đóng cả stream bên dưới; khi tổ chức ownership, cần xác định ai chịu trách nhiệm đóng để tránh đóng lặp ngoài ý muốn. Trong trường hợp `Reader` sở hữu hoàn toàn `InputStream`, có thể chỉ đăng ký `Reader` trong `try-with-resources` theo contract của wrapper.

### 6.2. `OutputStreamWriter`

`OutputStream` nhận byte; `Writer` nhận ký tự.

Không tường minh:

```java
Writer writer = new OutputStreamWriter(outputStream);
```

Tường minh:

```java
Writer writer = new OutputStreamWriter(
        outputStream, StandardCharsets.UTF_8);
```

Nếu writer là lớp đệm (*buffered writer*), phải thực hiện flush/close theo hợp đồng trước khi kỳ vọng toàn bộ dữ liệu đã có ở bên dưới. Nhưng **đừng tự đóng stream do bên gọi sở hữu** nếu API chỉ được phép mượn stream; trong trường hợp này cần thiết kế ownership hoặc wrapper phù hợp, không phải mặc định đưa mọi stream vào `try-with-resources`.

### 6.3. `Scanner` và các API parsing khác

Một số constructor `Scanner` nhận `InputStream` mà không chỉ định charset cũng có thể dùng default charset:

```java
Scanner scanner = new Scanner(inputStream, StandardCharsets.UTF_8);
```

Đây là **minh họa Java 17+**, cần import `java.util.Scanner`. Chọn overload có charset khi nội dung byte có encoding rõ ràng. Cũng cần chú ý khi đóng `Scanner`, nếu underlying source triển khai `Closeable`, nó có thể bị đóng theo; giữ đúng quyền sở hữu của bên gọi.

Không phải mọi API xử lý văn bản đều dùng default charset khi bỏ tham số. Phải tra tài liệu overload **cụ thể**; phần sau nêu ví dụ đặc biệt quan trọng với `java.nio.file.Files`.

## 7. `Files`: một số overload không có `Charset` nhưng vẫn cố định UTF-8

### 7.1. `Files.readString(Path)` / `Files.writeString(Path, ...)`

Từ Java 11, các API sau dùng **UTF-8 theo tài liệu**, **không phụ thuộc** `Charset.defaultCharset()`:

```java
Files.writeString(path, "Cà phê");
String text = Files.readString(path);
```

Đây là mã minh họa cần import `java.nio.file.Files`, `java.nio.file.Path` và các exception tương ứng. Mặc dù không truyền tham số charset, đây **không phải** trường hợp nguy hiểm giống `new String(bytes)`.

Tuy nhiên, với code mà hợp đồng file cần nhìn rõ ngay tại lời gọi, có thể và thường nên viết:

```java
Files.writeString(path, "Cà phê", StandardCharsets.UTF_8);
String text = Files.readString(path, StandardCharsets.UTF_8);
```

Khi file từ đối tác được xác định bằng charset khác, cần dùng overload có `Charset` tương ứng. Không phải cứ không có tham số charset thì **mọi API** đều dùng default charset.

### 7.2. `Files.newBufferedReader` / `newBufferedWriter`

Các overload:

```java
BufferedReader reader = Files.newBufferedReader(
        path, StandardCharsets.UTF_8);

BufferedWriter writer = Files.newBufferedWriter(
        path, StandardCharsets.UTF_8);
```

diễn đạt rõ charset. Với các overload một tham số `newBufferedReader(path)` và `newBufferedWriter(path)`, **API chuẩn cũng định nghĩa UTF-8** chứ không dựa vào default charset.

Điều này cho thấy không thể chỉ tìm dấu ngoặc không có `Charset` rồi kết luận API đang phụ thuộc môi trường. Phải phân biệt **các constructor `java.io` dùng default** với **nhiều convenience API `Files` cố định UTF-8**.

### 7.3. `Files.readAllBytes` / `Files.write(byte[])`

```java
byte[] bytes = Files.readAllBytes(path);
Files.write(otherPath, bytes);
```

Hai API này làm việc **trực tiếp trên byte**, không thực hiện chuyển đổi ký tự. Chỉ cần quan tâm charset khi code **giải mã những byte đó thành `String`** hoặc **mã hóa `String` thành byte**.

Đừng thêm charset ở nơi API thuần binary không cần; hãy quản lý charset tại ranh giới văn bản.

### 7.4. Tránh nhầm charset với việc ghi đè file

Định dạng chữ phải đúng, nhưng file mode cũng cần đúng: `Files.writeString` mặc định tạo file nếu cần và ghi đè nội dung nếu đã có, trừ khi cung cấp các `OpenOption` khác theo API. Khi cần append, dùng `StandardOpenOption.APPEND` cùng các tùy chọn thích hợp; **không đổi charset giữa các lần append** vào cùng file nếu định dạng không cho phép.

Đây là một phần của hợp đồng dữ liệu bền vững, tách biệt với việc chọn UTF-8.

## 8. Đọc dữ liệu ngoài hệ thống: lấy charset từ hợp đồng, không đoán

### 8.1. Charset phải thuộc thông số của giao tiếp

Khi nhận dữ liệu từ file, HTTP, message queue hoặc hệ thống khác, hỏi:

- Dữ liệu đó là **text hay binary**?
- Nếu text, **charset nào** được hợp đồng quy định?
- Charset có được công bố trong metadata, ví dụ HTTP `Content-Type` hoặc mô tả định dạng file không?
- Charset có đi kèm BOM/byte-order rule hay không, và tầng nào xử lý?
- Nếu có byte không hợp lệ, hệ thống cần **báo lỗi** hay **thay thế** để tiếp tục?
- Có bắt buộc giữ nguyên toàn bộ nội dung byte để kiểm chứng hoặc chữ ký số không?

Với định dạng text hiện đại do mình kiểm soát, chuẩn hóa thành UTF-8 và **ghi quy ước đó trong hợp đồng** giúp giảm phụ thuộc. Với dữ liệu có sẵn, thay đổi charset mà không chuyển đổi nội dung đúng cách sẽ làm sai dữ liệu.

### 8.2. Ví dụ hai charset khác nhau cho cùng nội dung

Với chuỗi `"café"`:

```text
UTF-8:       63 61 66 C3 A9
ISO-8859-1:  63 61 66 E9
```

Nếu nhận byte `63 61 66 E9` vốn thuộc ISO-8859-1 nhưng giải mã bằng UTF-8:

```java
byte[] latin1Bytes = {(byte) 0x63, (byte) 0x61,
                      (byte) 0x66, (byte) 0xE9};

String wrong = new String(
        latin1Bytes, StandardCharsets.UTF_8);
```

`wrong` không bằng `"café"`, vì byte `E9` đứng một mình không phải dãy UTF-8 hợp lệ. Một bộ giải mã UTF-8 chọn **replace** có thể đưa ký tự thay thế `U+FFFD` vào chuỗi.

**Không dùng “thử vài charset rồi thấy nhìn có vẻ đúng” làm cách phát hiện encoding chính thức.** Charset-detection heuristic có thể hữu ích cho nhập dữ liệu không có metadata, nhưng cần xác minh, chính sách lỗi và nguồn thông tin; cách tốt nhất vẫn là có **contract**.

### 8.3. Tránh double encoding và double decoding

Một lỗi phổ biến là lấy bytes UTF-8, giải mã sai, sau đó lại mã hóa chuỗi đã sai thành UTF-8 để lưu:

```text
Byte UTF-8 đúng
   ↓ giải mã bằng charset sai
String ký tự sai
   ↓ mã hóa UTF-8
Byte UTF-8 biểu diễn chính nội dung sai
```

File kết quả có thể hoàn toàn **hợp lệ về mặt UTF-8** nhưng văn bản vẫn bị hỏng. Việc cuối cùng có UTF-8 không chứng minh những bước trước đó đã dùng đúng charset.

Hãy theo dõi rõ ở từng ranh giới: “đang có bytes theo charset X” hay “đang có Unicode String”. Khi lỗi xuất hiện, kiểm tra **byte nguồn thật** trước khi tự động chuyển đổi lại.

## 9. Dữ liệu không hợp lệ: `String` có thể thay thế ký tự mà không báo lỗi

### 9.1. Khi muốn tolerant decoding

`new String(bytes, StandardCharsets.UTF_8)` tiện lợi, nhưng theo API Java, khi dữ liệu có chuỗi byte malformed/unmappable, constructor nhận `Charset` có cơ chế **thay thế** bằng replacement character tương ứng.

Ví dụ:

```java
byte[] invalid = {(byte) 0xC3, (byte) 0x28};
String text = new String(invalid, StandardCharsets.UTF_8);

System.out.println(text.indexOf('\uFFFD') >= 0); // true
```

Hai byte `C3 28` không tạo thành một chuỗi UTF-8 hợp lệ. `U+FFFD` là **replacement character**, có thể xuất hiện nếu giải mã với chính sách thay thế.

Đây có thể là lựa chọn chấp nhận được ở giao diện hiển thị văn bản không tin cậy khi đã có chính sách rõ ràng, nhưng không phù hợp với trường hợp phải **giữ nguyên dữ liệu** hoặc **từ chối đầu vào không đúng định dạng**.

### 9.2. Khi muốn strict decoding: `CharsetDecoder` và `REPORT`

Với dữ liệu cần kiểm tra nghiêm ngặt:

```java
import java.nio.ByteBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;

static String decodeUtf8Strict(byte[] bytes)
        throws CharacterCodingException {
    return StandardCharsets.UTF_8.newDecoder()
            .onMalformedInput(CodingErrorAction.REPORT)
            .onUnmappableCharacter(CodingErrorAction.REPORT)
            .decode(ByteBuffer.wrap(bytes))
            .toString();
}
```

Đây là **phương thức minh họa**. Khi input có chuỗi byte không hợp lệ, bộ giải mã có thể ném `MalformedInputException`, là một subtype của `CharacterCodingException`. Caller phải xử lý hoặc truyền exception theo hợp đồng. `REPORT` không sửa bytes, mà từ chối giải mã không hợp lệ.

Có những trường hợp dù bytes hợp lệ theo charset, nội dung vẫn **không đúng định dạng ứng dụng** (ví dụ JSON sai cú pháp). Kiểm tra encoding **không thay thế** việc kiểm tra cú pháp và nội dung nghiệp vụ.

### 9.3. Strict encoding với `CharsetEncoder`

Ở chiều `String → byte[]`, `text.getBytes(charset)` cũng có cơ chế thay thế khi ký tự không biểu diễn được bằng charset đích. Điều này rất quan trọng với `US_ASCII`, `ISO_8859_1` hoặc các charset hạn chế.

Nếu ứng dụng **không cho phép mất ký tự**, hãy dùng `CharsetEncoder` với `CodingErrorAction.REPORT`:

```java
import java.nio.ByteBuffer;
import java.nio.CharBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.Charset;

static ByteBuffer encodeStrict(String text, Charset charset)
        throws CharacterCodingException {
    return charset.newEncoder()
            .onMalformedInput(CodingErrorAction.REPORT)
            .onUnmappableCharacter(CodingErrorAction.REPORT)
            .encode(CharBuffer.wrap(text));
}
```

Kết quả là một `ByteBuffer` chứa bytes đã encode, sẵn sàng để đọc từ `position` đến `limit` theo cách dùng buffer; hãy chuyển ra byte array nếu API cần. Nếu có ký tự không mã hóa được, method báo lỗi thay vì tự chèn `?` hoặc replacement khác.

**Quy tắc:** Chọn charset đúng trước; sau đó chọn chính sách dữ liệu sai (reject/replace) theo độ nghiêm ngặt của hệ thống. Hai quyết định này độc lập nhau.

## 10. Ví dụ Java 17+ chạy độc lập, không phụ thuộc default charset

Chương trình sau dùng **một chuỗi có dấu tiếng Việt và biểu tượng Unicode**, nhưng chỉ in các thông tin ASCII và giá trị kiểm tra để stdout không phụ thuộc khả năng hiển thị Unicode của terminal.

Nó kiểm tra:

1. `String.getBytes(UTF_8)` tạo đúng dãy byte.
2. `new String(bytes, UTF_8)` khôi phục nội dung.
3. `Files.writeString`/`Files.readString` với charset chỉ định.
4. `Files.readString(path)` mặc định **UTF-8 theo API** (khác với `new String(bytes)` dùng default charset).
5. `OutputStreamWriter` và `InputStreamReader` dùng UTF-8 rõ ràng.
6. Dữ liệu ISO-8859-1 bị giải mã sai bằng UTF-8 cho kết quả khác.
7. `CharsetDecoder` strict từ chối byte UTF-8 không hợp lệ, trong khi constructor `String` với `Charset` thay thế ký tự.

Tệp **`ExplicitCharsetDemo.java`**:

```java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStreamReader;
import java.io.OutputStreamWriter;
import java.io.Reader;
import java.io.Writer;
import java.nio.ByteBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Arrays;
import java.util.HexFormat;

public final class ExplicitCharsetDemo {

    static void check(boolean condition, String label) {
        if (!condition) {
            throw new AssertionError(label);
        }
    }

    public static void main(String[] args) throws Exception {
        String message = "C\u00E0 ph\u00EA \u2615";

        byte[] utf8 = message.getBytes(StandardCharsets.UTF_8);
        String decoded = new String(utf8, StandardCharsets.UTF_8);
        check(message.equals(decoded), "UTF-8 round trip");

        System.out.println("utf8.hex="
                + HexFormat.of().withUpperCase().formatHex(utf8));
        System.out.println("utf8.bytes=" + utf8.length);
        System.out.println("chars=" + message.length());
        System.out.println("roundTrip=" + message.equals(decoded));

        Path temp = Files.createTempFile("encoding-demo-", ".txt");

        try {
            Files.writeString(temp, message, StandardCharsets.UTF_8);
            System.out.println("file.explicit=" + message.equals(
                    Files.readString(temp, StandardCharsets.UTF_8)));
            System.out.println("file.noArgUtf8="
                    + message.equals(Files.readString(temp)));
            System.out.println("file.bytesMatch=" + Arrays.equals(
                    utf8, Files.readAllBytes(temp)));
        } finally {
            Files.deleteIfExists(temp);
        }

        ByteArrayOutputStream out = new ByteArrayOutputStream();

        try (Writer writer = new OutputStreamWriter(
                out, StandardCharsets.UTF_8)) {
            writer.write(message);
        }

        StringBuilder text = new StringBuilder();

        try (Reader reader = new InputStreamReader(
                new ByteArrayInputStream(out.toByteArray()),
                StandardCharsets.UTF_8)) {
            char[] buf = new char[3];
            int n;
            while ((n = reader.read(buf)) != -1) {
                text.append(buf, 0, n);
            }
        }

        System.out.println("stream.roundTrip="
                + message.contentEquals(text));

        String latinText = "caf\u00E9";
        byte[] latin1 = latinText.getBytes(
                StandardCharsets.ISO_8859_1);
        System.out.println("latin1.hex="
                + HexFormat.of().withUpperCase().formatHex(latin1));
        System.out.println("wrongCharset.equal="
                + latinText.equals(new String(
                    latin1, StandardCharsets.UTF_8)));

        byte[] malformedUtf8 = {(byte) 0xC3, (byte) 0x28};

        try {
            StandardCharsets.UTF_8.newDecoder()
                    .onMalformedInput(CodingErrorAction.REPORT)
                    .onUnmappableCharacter(CodingErrorAction.REPORT)
                    .decode(ByteBuffer.wrap(malformedUtf8));
            throw new AssertionError("malformed input should fail");
        } catch (CharacterCodingException expected) {
            System.out.println("invalidUtf8=REJECTED");
        }

        System.out.println("replacementCharacter="
                + (new String(malformedUtf8, StandardCharsets.UTF_8)
                    .indexOf('\uFFFD') >= 0));

        System.out.println("checks=PASS");
    }
}
```

Dùng JDK 17 hoặc mới hơn:

```bash
javac -encoding UTF-8 ExplicitCharsetDemo.java
java ExplicitCharsetDemo
```

**Stdout đã được chạy kiểm chứng:**

```text
utf8.hex=43C3A0207068C3AA20E29895
utf8.bytes=12
chars=8
roundTrip=true
file.explicit=true
file.noArgUtf8=true
file.bytesMatch=true
stream.roundTrip=true
latin1.hex=636166E9
wrongCharset.equal=false
invalidUtf8=REJECTED
replacementCharacter=true
checks=PASS
```

### 10.1. Tại sao ví dụ dùng escape Unicode ở vài string?

Trong Java source, `\u00E0`, `\u00EA` và `\u2615` biểu diễn lần lượt `à`, `ê` và `☕`. Java xử lý Unicode escapes ở tầng ngôn ngữ khi đọc source. Viết như vậy giúp ví dụ giữ nguyên nội dung dù người học copy qua một số trình soạn thảo hoặc terminal có thiết lập hiển thị khác.

**Không nhầm encoding của source code với encoding của dữ liệu runtime.** Tùy chọn `javac -encoding UTF-8` hướng dẫn compiler đọc **tệp mã nguồn** theo UTF-8; nó không tự đổi charset mà `String.getBytes()` không tham số hay `InputStreamReader(InputStream)` sử dụng trong chương trình.

### 10.2. Vì sao in hex thay vì in tiếng Việt trực tiếp?

Output terminal có thể phụ thuộc console và đường truyền dữ liệu đến terminal. In chuỗi hex của **byte[] đã mã hóa** giúp xác nhận nội dung byte ổn định, không dựa trên khả năng render ký tự của shell.

Các assertions `roundTrip=true` và `stream.roundTrip=true` kiểm tra tính toàn vẹn nội dung Unicode; `file.bytesMatch=true` kiểm tra **đúng byte** được ghi ra disk.

### 10.3. `Files.readString(path)` không phải một lỗi phụ thuộc default charset

`file.noArgUtf8=true` không có nghĩa JVM hiện tại tình cờ dùng default UTF-8. `Files.readString(Path)` **được Java API quy định dùng UTF-8**, nên kết quả đúng ngay cả khi một API khác mặc định charset khác.

Ngược lại, nếu thay dòng giải mã bằng `new String(Files.readAllBytes(temp))`, code lại phụ thuộc default charset của JVM. Cùng một file, **lựa chọn API** quyết định có đang phụ thuộc môi trường hay không.

### 10.4. Giải thích dữ liệu Latin-1 và lỗi nghiêm ngặt

`latin1.hex=636166E9` là dãy ISO-8859-1 của `"café"`. Vì `E9` không đứng một mình hợp lệ trong UTF-8, giải mã bằng UTF-8 không trả lại chuỗi ban đầu.

`invalidUtf8=REJECTED` xác nhận decoder với `REPORT` ném checked exception; `replacementCharacter=true` cho thấy constructor `String` tiện lợi dùng chính sách replacement. Trong hệ thống yêu cầu dữ liệu tuyệt đối không được sửa âm thầm, hãy dùng strict decoder phù hợp.

`HexFormat` có từ Java 17, nên lựa chọn JDK 17+ cho chương trình độc lập này là có chủ đích. Các API charset nền tảng như `StandardCharsets.UTF_8` đã hiện hữu từ Java 7.

## 11. Checklist migrate và kiểm thử chạy đa môi trường

Để tìm những vị trí có nguy cơ phụ thuộc charset, xem **các ranh giới text ↔ bytes** trong code của chính dự án:

- `new String(byte[])` hoặc `new String(byte[], offset, length)` mà không có `Charset`.
- `String.getBytes()` không tham số.
- `new InputStreamReader(input)`, `new OutputStreamWriter(output)` thiếu charset.
- `new FileReader(...)`/`new FileWriter(...)` dạng không chỉ định charset.
- `Scanner`/`Formatter`/`PrintStream`/`PrintWriter` constructor có thể dùng default charset tùy overload và phiên bản.
- `ByteArrayOutputStream.toString()` không charset (đọc bytes thành text theo default charset).
- Thư viện hoặc helper có thể che giấu chuyển đổi text ↔ bytes ở tầng bên trong.

**Đừng sửa máy móc mọi lời gọi không truyền charset.** `Files.readString(Path)`, `Files.writeString(Path,...)` và nhiều overload `Files` đã cố định UTF-8. Những API thuần byte như `Files.readAllBytes` không thực hiện chuyển đổi ký tự. Phải phân loại đúng từng method trước khi sửa.

### 11.1. Chiến lược kiểm thử có giá trị

1. **Test byte chính xác:** so `Arrays.equals(expectedUtf8, actualBytes)` hoặc biểu diễn hexa cố định.
2. **Test round-trip:** giải mã bằng cùng charset; xác nhận `String.equals`.
3. **Test dữ liệu phi ASCII:** tiếng Việt có dấu, ký tự tiền tệ, emoji, chuỗi hỗn hợp.
4. **Test input có charset khác UTF-8:** nếu hợp đồng cho phép, chọn dữ liệu biết trước và xác nhận decoder tương ứng.
5. **Test bytes malformed:** chọn chính sách reject hay replace, kiểm tra đúng.
6. **Test file/stream:** kiểm tra nội dung byte ngoài đường đi dùng `String` tiện ích.
7. **Test migration JDK:** so hành vi dưới JDK 17 và 18+ nếu sản phẩm hỗ trợ cả hai, nhất là các constructor dùng default charset.
8. **Test giao tiếp liên hệ:** khi service A tạo text UTF-8, service B phải biết đọc UTF-8 theo header/contract.
9. **Test thiếu metadata:** xác định nên báo lỗi, áp chính sách fallback có tài liệu, hay yêu cầu người dùng chọn encoding.
10. **Test newline và BOM nếu định dạng có ràng buộc:** đây là vấn đề riêng với charset và byte order.

**Tránh làm test thành phụ thuộc mặc định môi trường:** không viết `assertEquals("UTF-8", Charset.defaultCharset().name())` nếu mục tiêu chỉ là chứng minh hàm đọc file đúng. Test đúng thường cần **assert nội dung hoặc byte**, không assert máy chạy có đúng một charset cụ thể.

### 11.2. Lệnh kiểm tra môi trường để chẩn đoán

Có thể chạy:

```bash
java -XshowSettings:properties -version
```

và xem các thuộc tính liên quan encoding tùy JDK. Đọc trực tiếp `Charset.defaultCharset()` trong code sẽ cho thông tin chính xác hơn khi đang điều tra runtime. Trên Java 18+ có thể dùng cấu hình migration `-Dfile.encoding=COMPAT` theo tài liệu JEP 400, nhưng **không sử dụng nó như thay thế** cho việc sửa code có default charset ngầm định.

Đừng kết luận “cùng máy nghĩa là cùng charset”: container, service launcher, locale, JDK version và cấu hình khởi chạy có thể làm môi trường JVM khác nhau.

## 12. Quy ước thiết kế API khi cần ghi/đọc văn bản

### 12.1. Hai cách tách trách nhiệm hợp lý

**Cách A — API nhận/ trả về `String`:** Nếu component làm việc ở mức nội dung, hãy trao đổi `String` và chỉ chuyển bytes ở tầng thực hiện I/O. Charset là trách nhiệm **adapter giao tiếp**:

```java
static void writeUtf8(Path path, String text) throws IOException {
    Files.writeString(path, text, StandardCharsets.UTF_8);
}

static String readUtf8(Path path) throws IOException {
    return Files.readString(path, StandardCharsets.UTF_8);
}
```

**Cách B — API nhận bytes:** Nếu component truyền dữ liệu binary hoặc proxy payload, giữ `byte[]`/`ByteBuffer`, không biến bytes thành text rồi ngược lại chỉ để “đơn giản” hóa code:

```java
static void copyBytes(Path source, Path target) throws IOException {
    Files.write(target, Files.readAllBytes(source));
}
```

Các đoạn trên là **phương thức minh họa trong lớp** với import `java.nio.file.Files`, `java.nio.file.Path`, `java.nio.charset.StandardCharsets` và `java.io.IOException`. Trong dữ liệu rất lớn, thay vì đọc toàn bộ file vào RAM có thể dùng stream/copy API phù hợp; đây không phải vấn đề riêng của charset.

### 12.2. Khi buộc hỗ trợ nhiều charset

Nếu một chức năng import cho phép người dùng chọn bảng mã, truyền `Charset` như một tham số rõ ràng:

```java
static String readText(Path path, Charset charset)
        throws IOException {
    return Files.readString(
            path, java.util.Objects.requireNonNull(charset, "charset"));
}
```

Ở tầng gọi, truyền `StandardCharsets.UTF_8` hoặc charset đã được xác định từ cấu hình/metadata; đừng lấy `Charset.defaultCharset()` làm giá trị ngầm định không được ghi lại nếu tính đúng đắn của dữ liệu phụ thuộc vào lựa chọn ấy.

Cần thống nhất chính sách với file thiếu charset: nếu không có metadata, **không có cách chung bảo đảm** đoán chính xác encoding của mọi dãy byte. Nếu có fallback, hãy ghi lại quyết định và cảnh báo người dùng khi cần.

### 12.3. Lưu ý về BOM, newline và source file

- **BOM** (*byte order mark*) có thể xuất hiện ở đầu một số định dạng Unicode. Sự có/không có BOM cần theo hợp đồng file. Đừng mặc định mọi API Java đều tự bỏ BOM theo cách bạn mong muốn.
- **Newline** có thể là `LF`, `CRLF` hoặc chuỗi khác tùy nguồn. Chọn UTF-8 không đồng nghĩa chọn một kiểu xuống dòng; các phương thức dòng như `readLine()` có thể bỏ ký tự kết thúc dòng.
- **Encoding của tệp `.java`** khác với encoding của file data. Chỉ định `javac -encoding UTF-8` khi biên dịch mã nguồn UTF-8 giúp quy trình build rõ ràng, nhưng không thay thế tham số charset ở runtime.
- **JSON, CSV, HTTP, XML** có quy tắc byte/charset riêng theo định dạng và chuẩn đang được dùng. Không thể cho mọi API tên `readText` là mặc định tùy ý mà không xem quy ước của format.

## 13. Những lỗi phổ biến và cách sửa

| Lỗi | Tác động | Cách đúng |
| --- | --- | --- |
| `text.getBytes()` khi gửi giao thức UTF-8 | Bytes phụ thuộc default charset | `text.getBytes(StandardCharsets.UTF_8)` |
| `new String(bytes)` khi nhận UTF-8 | Decode sai khi default khác UTF-8 | `new String(bytes, StandardCharsets.UTF_8)` |
| `new InputStreamReader(input)` | Ngầm dùng default charset | Truyền `StandardCharsets.UTF_8` hoặc charset hợp đồng |
| `new OutputStreamWriter(output)` | Ngầm dùng default charset | Truyền `Charset` |
| Cho rằng Java 17 default luôn UTF-8 | Sai với nhiều môi trường JDK 17 | Xác minh runtime và sửa code rõ charset |
| Cho rằng Java 18+ khiến tham số charset không cần thiết | Vẫn có dữ liệu charset khác và tính tương thích | Quy định charset theo định dạng, không theo máy chạy |
| Cho rằng `Files.readString(path)` dùng default charset | API quy định UTF-8 | Dựa vào đặc tả; có thể truyền UTF-8 tường minh |
| Chỉ test ASCII | Không phát hiện phần lớn lỗi encoding | Test tiếng Việt, emoji, bytes mẫu |
| Dùng `text.length()` làm số byte UTF-8 | Sai khi ký tự đa byte | Đo `text.getBytes(UTF_8).length` |
| Coi dữ liệu nhị phân là UTF-8 text | Có thể làm mất bytes | Giữ bytes hoặc Base64 theo contract |
| Dùng constructor `String` mặc định thay thế trên đầu vào cần strict | Có thể che dữ liệu lỗi | `CharsetDecoder` với `REPORT` |
| Mã hóa Latin-1 khi văn bản có ký tự không biểu diễn được | Có thể bị replacement | `CharsetEncoder` với `REPORT` hoặc đổi contract |
| Sửa `file.encoding` giữa runtime | Không phải cơ chế chuyển đổi đáng tin | Truyền `Charset` ngay tại API |
| Dùng `ByteArrayOutputStream.toString()` khi dữ liệu là UTF-8 | Có thể decode theo default charset | `toString(StandardCharsets.UTF_8)` |
| Cho rằng terminal lỗi font là file mã hóa sai | Console charset là vấn đề riêng | Kiểm tra bytes và reader thực, tách I/O với hiển thị |
| Tự đổi toàn bộ file thành UTF-8 mà không biết charset gốc | Có thể phá dữ liệu | Xác định nguồn trước khi chuyển mã |

## 14. Câu hỏi tự kiểm tra

**Câu 1.** Vì sao `new String(data)` có thể đúng trên máy phát triển nhưng sai trên máy khác?  
**Đáp án:** Nó dùng default charset của JVM. Đầu vào là bytes nhưng mã nguồn không chỉ rõ quy tắc giải mã; các môi trường hoặc JDK cũ có thể dùng charset khác.

**Câu 2.** `StandardCharsets.UTF_8` có phụ thuộc locale Windows/Linux không?  
**Đáp án:** Không. Đây là một charset chuẩn cố định, dùng cho chuyển đổi text/bytes theo UTF-8.

**Câu 3.** Trên Java 18+, đã có JEP 400 thì có nên bỏ `StandardCharsets.UTF_8` khỏi mọi API không?  
**Đáp án:** Không. Dữ liệu có thể thuộc charset khác theo hợp đồng, app có thể chạy JDK khác, và chỉ định tường minh giúp người đọc hiểu định dạng.

**Câu 4.** `Files.readString(path)` không nhận `Charset` có dùng default charset không?  
**Đáp án:** Không. API `Files.readString(Path)` được định nghĩa dùng UTF-8; khác với `new String(byte[])`.

**Câu 5.** Vì sao một file toàn ASCII thường không phát hiện lỗi charset?  
**Đáp án:** Nhiều charset biểu diễn ASCII cơ bản bằng cùng một byte, nên quá trình sai charset có thể chưa lộ lỗi cho đến khi gặp ký tự ngoài ASCII.

**Câu 6.** Nếu bytes ISO-8859-1 `63 61 66 E9` bị đọc như UTF-8 thì sao?  
**Đáp án:** Chúng không giải mã đúng `"café"`; byte `E9` đứng đơn lẻ không hợp lệ trong UTF-8. Chọn charset đúng hoặc reject input theo chính sách.

**Câu 7.** `new String(bytes, UTF_8)` có luôn ném exception với bytes UTF-8 malformed?  
**Đáp án:** Không. Constructor nhận `Charset` dùng replacement cho dữ liệu không hợp lệ. Muốn từ chối phải dùng `CharsetDecoder` có `CodingErrorAction.REPORT`.

**Câu 8.** Khi cần giữ nguyên nội dung file nhị phân, có nên qua `new String(bytes, UTF_8)` để copy không?  
**Đáp án:** Không. Byte tùy ý có thể không phải text UTF-8 và bị biến đổi. Dùng API binary.

**Câu 9.** `javac -encoding UTF-8` có tự làm cho mọi `new InputStreamReader(input)` tại runtime dùng UTF-8 không?  
**Đáp án:** Không. Tùy chọn compiler chỉ xử lý **encoding của source file**. Runtime I/O vẫn theo charset được truyền hoặc mặc định của API.

**Câu 10.** `String.length()` có bằng số byte UTF-8 cần gửi không?  
**Đáp án:** Không nhất thiết. Với `"Cà phê ☕"`, `length()==8` nhưng UTF-8 có `12` byte.

## 15. Tóm tắt và tài liệu chính thức còn hiệu lực

**Ghi nhớ chính:**

- **Văn bản Unicode không tự mang charset của file**; charset là quyết định ở ranh giới chuyển đổi `String` ↔ `byte[]`.
- **Dùng `StandardCharsets.UTF_8` khi hợp đồng yêu cầu UTF-8** thay vì dựa vào default charset của môi trường.
- **Không đánh đồng mọi overload không có `Charset`:** `String.getBytes()` và `new String(bytes)` phụ thuộc default, nhưng `Files.readString(Path)` và `Files.writeString(Path, ...)` đã được Java quy định UTF-8.
- **JDK 17 và trước có thể có default charset theo môi trường; JDK 18+ mặc định UTF-8 theo JEP 400**, nhưng vẫn phải đọc dữ liệu theo encoding thật của nguồn.
- **Xử lý malformed input có chủ đích:** cơ chế replacement thích hợp cho một số hiển thị tolerant; `CharsetDecoder/CharsetEncoder` với `REPORT` thích hợp khi không cho phép âm thầm mất dữ liệu.
- **Kiểm thử bằng bytes và Unicode ngoài ASCII**, không chỉ nhìn stdout terminal.

Tài liệu Oracle/OpenJDK:

- [Java SE 17 — `java.nio.charset.StandardCharsets`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/StandardCharsets.html): các hằng số charset chuẩn.
- [Java SE 17 — `java.nio.charset.Charset` và `defaultCharset()`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/Charset.html): charset được JVM dùng khi một API thật sự chọn mặc định.
- [Java SE 17 — `java.lang.String`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html): `getBytes(Charset)` và các constructor giải mã có/không có charset.
- [Java SE 17 — `java.nio.file.Files`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html): `readString`, `writeString`, `newBufferedReader` và các overload UTF-8.
- [OpenJDK — JEP 400: UTF-8 by Default](https://openjdk.org/jeps/400): thay đổi từ JDK 18 và cấu hình tương thích.
- [Java SE 17 — `CharsetDecoder`, `CharsetEncoder` và `CodingErrorAction`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/package-summary.html): kiểm soát việc reject/replace dữ liệu sai encoding.