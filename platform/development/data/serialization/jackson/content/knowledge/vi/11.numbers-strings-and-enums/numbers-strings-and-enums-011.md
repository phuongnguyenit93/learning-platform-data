# Đọc ghi dữ liệu nhị phân và quy ước Base64

Ứng dụng Java thường cần trao đổi dữ liệu không phải văn bản, chẳng hạn ảnh, tệp PDF, chữ ký số hoặc nội dung nhị phân của một tệp đính kèm. Trong Java, dữ liệu này thường được biểu diễn bằng `byte[]`, `InputStream` hoặc một kiểu dữ liệu tương tự. JSON lại là định dạng văn bản, không có kiểu giá trị riêng để chứa một dãy byte tùy ý.

Khi ánh xạ `byte[]` trong JSON, Jackson thường biểu diễn dữ liệu bằng **chuỗi Base64**. Khi đọc chuỗi Base64 vào `byte[]`, Jackson giải mã chuỗi đó thành các byte ban đầu. Nhờ vậy, một payload nhị phân có thể đi qua JSON mà không làm hỏng các byte không phải ký tự văn bản.

Để sử dụng đúng cơ chế này, cần hiểu Base64 là cách mã hóa dữ liệu nhị phân thành văn bản, biết cách Jackson xử lý `byte[]`, chọn đúng biến thể Base64 mà hai hệ thống thống nhất và cân nhắc kích thước payload khi dữ liệu lớn.

## 1. Vì sao JSON cần Base64 cho dữ liệu nhị phân?

JSON có các kiểu dữ liệu như object, array, string, number, boolean và null. Nó không định nghĩa một giá trị binary tùy ý tương đương `byte[]` trong Java.

Một dãy byte có thể chứa mọi giá trị từ `0x00` đến `0xFF`, bao gồm byte điều khiển hoặc byte không phải UTF-8 hợp lệ. Nếu đưa trực tiếp các byte này vào một chuỗi JSON như văn bản, dữ liệu có thể bị biến đổi hoặc không tạo thành JSON hợp lệ.

Base64 giải quyết vấn đề bằng cách chuyển mỗi nhóm byte thành các ký tự thuộc bảng chữ cái Base64. Kết quả là một chuỗi văn bản có thể đặt an toàn trong JSON.

Ví dụ, dãy byte:

```text
48 65 6C 6C 6F
```

tương ứng với các ký tự ASCII `Hello`. Dạng Base64 của nó là:

```text
SGVsbG8=
```

JSON có thể chứa chuỗi đó:

```json
{
  "fileName": "hello.txt",
  "content": "SGVsbG8="
}
```

Trường `content` trong JSON là một string. Jackson biết chuyển đổi string Base64 này thành `byte[]` khi kiểu Java đích được khai báo là `byte[]`.

## 2. Base64 hoạt động như thế nào?

Base64 mã hóa dữ liệu theo nhóm 3 byte, tức 24 bit, thành 4 ký tự, mỗi ký tự mang 6 bit thông tin. Bảng chữ cái Base64 thông dụng gồm:

```text
ABCDEFGHIJKLMNOPQRSTUVWXYZ
abcdefghijklmnopqrstuvwxyz
0123456789+/
```

Ký tự `=` được dùng làm padding để độ dài đầu ra là bội số của 4 trong biến thể Base64 có padding.

Ví dụ với từ `Man`:

```text
M        a        n
01001101 01100001 01101110
```

Ba byte tạo thành 24 bit. Chia 24 bit thành bốn nhóm 6 bit, sau đó mỗi nhóm ánh xạ vào một ký tự trong bảng Base64. Kết quả là `TWFu`.

Nếu số byte đầu vào không chia hết cho 3, Base64 có thể thêm padding:

| Dữ liệu gốc | Base64 chuẩn có padding |
| --- | --- |
| `M` | `TQ==` |
| `Ma` | `TWE=` |
| `Man` | `TWFu` |
| `Hello` | `SGVsbG8=` |

Base64 không phải mã hóa bảo mật. Bất kỳ ai có chuỗi Base64 đều có thể giải mã về byte ban đầu mà không cần khóa. Nó chỉ thay đổi cách biểu diễn dữ liệu để phù hợp với môi trường văn bản.

## 3. Jackson tự chuyển byte[] thành Base64 khi ghi JSON

Với Jackson Databind, `byte[]` là một kiểu đặc biệt. Khi serialize một thuộc tính `byte[]` trong object hoặc serialize trực tiếp một mảng byte, Jackson ghi dữ liệu dưới dạng JSON string Base64 theo biến thể đang được cấu hình.

Ví dụ DTO:

```java
public record Attachment(String fileName, byte[] content) {}
```

Serialize:

```java
import com.fasterxml.jackson.databind.ObjectMapper;

public class BinaryWriteExample {
    public static void main(String[] args) throws Exception {
        ObjectMapper mapper = new ObjectMapper();

        byte[] content = "Hello".getBytes(java.nio.charset.StandardCharsets.UTF_8);
        Attachment attachment = new Attachment("hello.txt", content);

        String json = mapper.writeValueAsString(attachment);
        System.out.println(json);
    }
}
```

JSON được tạo có dạng:

```json
{
  "fileName": "hello.txt",
  "content": "SGVsbG8="
}
```

Bạn không cần tự gọi `Base64.getEncoder()` chỉ để Jackson có thể ghi một property `byte[]`. Serializer của Jackson đã thực hiện bước Base64 encoding.

Nếu serialize trực tiếp `byte[]`:

```java
byte[] bytes = {72, 101, 108, 108, 111};
String json = mapper.writeValueAsString(bytes);
```

Kết quả là một JSON string chứa Base64, ví dụ:

```json
"SGVsbG8="
```

Điều này khác với một mảng JSON gồm các số `[72,101,108,108,111]`. Jackson xử lý `byte[]` theo quy ước binary/Base64; nếu hợp đồng API yêu cầu một array số nguyên, cần thiết kế kiểu dữ liệu hoặc serializer riêng thay vì mặc định dùng `byte[]`.

## 4. Jackson tự giải mã Base64 thành byte[] khi đọc JSON

Khi property Java đích có kiểu `byte[]`, Jackson đọc JSON string và giải mã Base64 thành các byte.

```java
import com.fasterxml.jackson.databind.ObjectMapper;

public class BinaryReadExample {
    public static void main(String[] args) throws Exception {
        String json = """
                {
                  "fileName": "hello.txt",
                  "content": "SGVsbG8="
                }
                """;

        ObjectMapper mapper = new ObjectMapper();
        Attachment attachment = mapper.readValue(json, Attachment.class);

        String text = new String(
                attachment.content(),
                java.nio.charset.StandardCharsets.UTF_8
        );

        System.out.println(text); // Hello
    }
}
```

Jackson trả về byte gốc trong `attachment.content()`. Nếu dữ liệu gốc là văn bản UTF-8, bạn có thể tạo lại `String` bằng đúng charset. Nếu dữ liệu là ảnh, PDF hoặc tệp nhị phân khác, không nên chuyển byte thành `String`; hãy ghi byte ra tệp hoặc chuyển cho API xử lý binary tương ứng.

### 4.1. Đọc trực tiếp một giá trị byte[] ở cấp cao nhất

JSON có thể là một string Base64 ở cấp gốc, không nhất thiết phải nằm trong một object:

```java
String json = "\"SGVsbG8=\"";
byte[] bytes = mapper.readValue(json, byte[].class);
```

Kiểu đích `byte[].class` cho Jackson biết string JSON cần được giải mã thành binary data.

## 5. Phân biệt byte[] với String Base64

Hai kiểu Java sau có ý nghĩa khác nhau:

```java
byte[] content;
String encodedContent;
```

- `byte[] content` biểu diễn dữ liệu nhị phân gốc. Jackson tự encode/decode Base64 khi ánh xạ qua JSON.
- `String encodedContent` biểu diễn các ký tự văn bản. Jackson ghi và đọc string như văn bản thông thường; nó không tự giải mã Base64 chỉ vì tên biến có chữ `encoded`.

Ví dụ:

```java
byte[] content = "Hello".getBytes(StandardCharsets.UTF_8);
String encoded = Base64.getEncoder().encodeToString(content);

String jsonFromBytes = mapper.writeValueAsString(content);
String jsonFromString = mapper.writeValueAsString(encoded);
```

Cả hai có thể tạo JSON string chứa cùng ký tự Base64, nhưng con đường xử lý khác nhau. Với `byte[]`, Jackson thực hiện encoding. Với `String`, chuỗi đã được mã hóa từ trước và Jackson chỉ ghi văn bản.

Nếu đọc JSON vào `String.class`, kết quả là chuỗi Base64; nếu đọc vào `byte[].class`, Jackson giải mã nó thành byte. Tránh encode hai lần: nếu dữ liệu đã là chuỗi Base64 nhưng lại chuyển nó thành byte UTF-8 rồi serialize như `byte[]`, Jackson sẽ mã hóa các ký tự của chuỗi đó thêm một lần nữa.

## 6. Các biến thể Base64 và quy ước tương thích

Base64 có nhiều biến thể. Hai bên giao tiếp cần thống nhất bảng ký tự, padding và quy tắc whitespace.

### 6.1. Base64 chuẩn

Base64 chuẩn theo bảng chữ cái thông dụng sử dụng `+` và `/`, thường có padding `=` để độ dài chuỗi là bội số của 4. Java cung cấp encoder/decoder tương ứng:

```java
import java.util.Base64;

String encoded = Base64.getEncoder().encodeToString(bytes);
byte[] decoded = Base64.getDecoder().decode(encoded);
```

Jackson mặc định sử dụng biến thể Base64 không chèn line break, có bảng chữ cái chuẩn và padding. Vì vậy, dữ liệu Base64 do `Base64.getEncoder()` của Java tạo ra thường tương thích với quy ước mặc định này.

### 6.2. URL-safe Base64

Trong URL hoặc tên file, các ký tự `+` và `/` có thể gây bất tiện. URL-safe Base64 thay chúng bằng `-` và `_`:

```java
String encodedUrl = Base64.getUrlEncoder()
        .withoutPadding()
        .encodeToString(bytes);

byte[] decodedUrl = Base64.getUrlDecoder().decode(encodedUrl);
```

Java encoder trên không thêm padding. Nếu API sử dụng URL-safe Base64, cả producer và consumer cần thống nhất biến thể đó. Không nên gửi URL-safe Base64 rồi giả định mọi decoder đang dùng bảng chữ cái chuẩn sẽ tự xử lý đúng.

Jackson có biến thể `Base64Variants.MODIFIED_FOR_URL` cho URL-safe Base64. Có thể đặt biến thể trên mapper:

```java
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.core.Base64Variants;

ObjectMapper mapper = new ObjectMapper();
mapper.setBase64Variant(Base64Variants.MODIFIED_FOR_URL);
```

Khi mapper sử dụng biến thể URL-safe, quá trình ghi và đọc `byte[]` sẽ theo bảng chữ cái URL-safe của biến thể đó. Biến thể modified-for-URL của Jackson không dùng padding; hãy kiểm tra quy ước cụ thể mà hệ thống bên ngoài yêu cầu trước khi chọn.

### 6.3. MIME Base64 và line break

MIME Base64 được thiết kế cho một số ngữ cảnh truyền tải văn bản và có thể chèn line break theo quy ước MIME. Java có encoder MIME:

```java
String mimeEncoded = Base64.getMimeEncoder().encodeToString(bytes);
```

Jackson có các biến thể MIME và MIME không xuống dòng trong `Base64Variants`. Mặc định của Jackson là biến thể không chèn line break, phù hợp với JSON string thông thường. Không nên tùy tiện đưa line break vào payload Base64 nếu hợp đồng không cho phép hoặc consumer không chấp nhận.

### 6.4. Bảng so sánh biến thể

| Biến thể | Ký tự 62/63 | Padding | Đặc điểm |
| --- | --- | --- | --- |
| Base64 chuẩn | `+` và `/` | Thường có `=` | Phổ biến cho dữ liệu nhị phân trong JSON |
| URL-safe Base64 | `-` và `_` | Có thể bỏ padding tùy quy ước | Phù hợp với URL hoặc token |
| MIME Base64 | `+` và `/` | Có `=` | Có thể chèn line break theo quy ước MIME |
| Jackson `MIME_NO_LINEFEEDS` | `+` và `/` | Có `=` | Biến thể mặc định phổ biến của Jackson, không chèn line break |

## 7. Dùng Base64 trực tiếp với JsonGenerator và JsonParser

`ObjectMapper` thuận tiện khi dữ liệu có thể được ánh xạ thành object hoàn chỉnh. Với luồng xử lý JSON ở mức thấp, Jackson Core cung cấp API binary chuyên biệt.

### 7.1. Ghi binary bằng JsonGenerator

`JsonGenerator.writeBinary(...)` ghi dữ liệu byte thành Base64 string trong JSON:

```java
import com.fasterxml.jackson.core.JsonFactory;
import com.fasterxml.jackson.core.JsonGenerator;

import java.io.StringWriter;

StringWriter output = new StringWriter();
JsonFactory factory = new JsonFactory();

try (JsonGenerator generator = factory.createGenerator(output)) {
    generator.writeStartObject();
    generator.writeStringField("fileName", "hello.txt");
    generator.writeFieldName("content");
    generator.writeBinary("Hello".getBytes(java.nio.charset.StandardCharsets.UTF_8));
    generator.writeEndObject();
}

String json = output.toString();
```

Generator đảm nhiệm Base64 encoding và ghi một JSON string hợp lệ. Bạn không phải tự tạo dấu nháy hoặc tự escape Base64.

### 7.2. Đọc binary bằng JsonParser

`JsonParser.getBinaryValue(...)` giải mã Base64 string thành `byte[]`:

```java
import com.fasterxml.jackson.core.Base64Variants;
import com.fasterxml.jackson.core.JsonFactory;
import com.fasterxml.jackson.core.JsonParser;
import com.fasterxml.jackson.core.JsonToken;

import java.io.ByteArrayOutputStream;

JsonFactory factory = new JsonFactory();

try (JsonParser parser = factory.createParser(json)) {
    while (parser.nextToken() != null) {
        if (parser.currentToken() == JsonToken.FIELD_NAME
                && "content".equals(parser.currentName())) {
            parser.nextToken();
            byte[] content = parser.getBinaryValue(Base64Variants.getDefaultVariant());
            System.out.println(content.length);
        }
    }
}
```

Khi biết rõ field đang ở vị trí nào trong cấu trúc JSON, hãy điều khiển parser theo cấu trúc đó thay vì tìm tên field một cách tùy tiện. Ví dụ trên minh họa việc giải mã trường `content` trong object.

### 7.3. Giải mã ra OutputStream

Nếu dữ liệu nhị phân lớn, `JsonParser.readBinaryValue(...)` có thể ghi các byte đã giải mã trực tiếp ra `OutputStream`. Cách này tránh phải tạo thêm một `byte[]` lớn chỉ để chứa toàn bộ nội dung đã giải mã:

```java
import com.fasterxml.jackson.core.Base64Variants;
import com.fasterxml.jackson.core.JsonFactory;
import com.fasterxml.jackson.core.JsonParser;
import com.fasterxml.jackson.core.JsonToken;

import java.io.OutputStream;
import java.nio.file.Files;
import java.nio.file.Path;

try (JsonParser parser = new JsonFactory().createParser(jsonInput)) {
    while (parser.nextToken() != null) {
        if (parser.currentToken() == JsonToken.FIELD_NAME
                && "content".equals(parser.currentName())) {
            parser.nextToken();
            try (OutputStream file = Files.newOutputStream(Path.of("attachment.bin"))) {
                parser.readBinaryValue(Base64Variants.getDefaultVariant(), file);
            }
            break;
        }
    }
}
```

Trong ứng dụng thật, hãy dùng đường dẫn đích đã được kiểm soát, giới hạn kích thước dữ liệu và xử lý lỗi ghi file. Ví dụ dùng default variant; nếu parser phải đọc URL-safe Base64, hãy truyền đúng `Base64Variant` tương ứng.

`JsonGenerator` cũng có API ghi binary từ `InputStream` với độ dài được cung cấp. API này hữu ích khi nguồn dữ liệu là stream và không muốn tự tạo một `byte[]` trung gian. Khi dùng, cần cung cấp độ dài phù hợp theo hợp đồng API của phiên bản Jackson đang dùng và bảo đảm stream được quản lý/đóng đúng cách.

## 8. Kích thước payload Base64

Base64 làm dữ liệu dài hơn dữ liệu nhị phân gốc. Với biến thể có padding, độ dài chuỗi Base64 xấp xỉ:

\[
L = 4 \times \left\lceil \frac{N}{3} \right\rceil
\]

Trong đó `N` là số byte gốc và `L` là số ký tự Base64. Vì vậy, dung lượng tăng khoảng một phần ba, chưa tính dấu nháy JSON, tên trường và các phần metadata khác.

Ví dụ gần đúng:

| Dữ liệu nhị phân | Base64 có padding |
| ---: | ---: |
| 3 byte | 4 ký tự |
| 1 KB | khoảng 1.34 KB |
| 1 MB | khoảng 1.33 MB |
| 10 MB | khoảng 13.33 MB |

Nếu API gửi ảnh hoặc tệp lớn trong JSON, payload có thể tăng đáng kể. Ngoài chi phí truyền mạng, ứng dụng có thể phải giữ đồng thời chuỗi JSON, dữ liệu Base64 và mảng byte đã giải mã trong bộ nhớ.

Với file lớn, cân nhắc `multipart/form-data`, upload trực tiếp đến object storage hoặc một endpoint binary chuyên biệt. JSON Base64 phù hợp hơn với dữ liệu nhỏ, metadata gắn với binary hoặc hợp đồng tích hợp đã quy định Base64.

## 9. Base64 không thay thế mã hóa bảo mật

Base64 không mã hóa bí mật và không xác thực tính toàn vẹn. Nó chỉ biến byte thành chuỗi ký tự. Nếu dữ liệu nhạy cảm, cần bảo vệ bằng TLS khi truyền, cơ chế kiểm soát quyền truy cập, mã hóa phù hợp khi lưu trữ và quy trình quản lý khóa.

Khi nhận Base64 từ client, ứng dụng cũng cần:

- Giới hạn độ dài chuỗi và kích thước byte sau giải mã.
- Bắt lỗi khi chuỗi Base64 sai cú pháp hoặc không đúng biến thể đã thỏa thuận.
- Kiểm tra định dạng tệp thực tế bằng nội dung byte; không tin tuyệt đối vào tên file hoặc MIME type client gửi.
- Không ghi nội dung nhị phân nhạy cảm vào log.
- Quét hoặc kiểm tra tệp theo yêu cầu bảo mật của hệ thống trước khi sử dụng.
- Tránh giải mã các payload quá lớn có thể gây cạn bộ nhớ hoặc tài nguyên xử lý.

Một chuỗi Base64 hợp lệ không đồng nghĩa với tệp an toàn. Nó chỉ cho biết chuỗi có thể được giải mã theo quy tắc Base64.

## 10. Những trường hợp đặc biệt

### 10.1. Mảng byte rỗng và null

`byte[0]` và `null` là hai trạng thái khác nhau:

- Mảng byte rỗng biểu diễn dữ liệu binary có độ dài bằng 0; khi ghi JSON, nó được biểu diễn thành chuỗi Base64 rỗng `""`.
- Giá trị `byte[]` null biểu diễn không có giá trị; khi ghi JSON, nó được biểu diễn thành `null` theo cấu hình null thông thường.
- Property bị thiếu trong JSON có thể giữ giá trị khởi tạo của object nếu quá trình tạo object và ánh xạ không gán property đó.

API nên quy định rõ file không có nội dung khác với file chưa được cung cấp hay trường bị null.

### 10.2. Dữ liệu văn bản và charset

Base64 chỉ mã hóa byte, không biết dữ liệu gốc là UTF-8, UTF-16, ảnh PNG hay PDF. Nếu byte đại diện cho văn bản, hai phía cần thống nhất charset. Khi chuyển `String` thành byte, hãy chỉ rõ charset:

```java
byte[] bytes = text.getBytes(StandardCharsets.UTF_8);
String restored = new String(bytes, StandardCharsets.UTF_8);
```

Không dùng charset mặc định của máy vì kết quả có thể khác giữa môi trường chạy.

### 10.3. byte[] và Byte[]

`byte[]` là kiểu binary mà Jackson xử lý đặc biệt theo Base64 trong JSON. `Byte[]` là mảng các object wrapper `Byte`; cách ánh xạ có thể khác và thường được xử lý như một array giá trị thay vì một binary scalar. Nếu mục đích là truyền nội dung nhị phân, `byte[]` là lựa chọn thông dụng và rõ ràng hơn.

## 11. JSON và các định dạng nhị phân của Jackson

Base64 đặc biệt cần thiết khi dùng JSON vì JSON không có kiểu binary nguyên thủy. Trong hệ sinh thái Jackson còn có các dataformat module như Smile hoặc CBOR, có thể biểu diễn dữ liệu nhị phân theo khả năng của định dạng đó mà không nhất thiết phải biến mọi byte thành chuỗi Base64 văn bản.

Tuy nhiên, việc dùng một định dạng nhị phân đòi hỏi cả producer và consumer hỗ trợ cùng format, thống nhất content type và công cụ vận hành có khả năng quan sát payload. JSON/Base64 thường dễ tích hợp hơn với hệ thống web phổ biến; binary dataformat có thể phù hợp trong một hệ thống kiểm soát được cả hai đầu và có yêu cầu riêng về biểu diễn dữ liệu.

## 12. Ghi nhớ

- JSON không có kiểu binary tùy ý; Jackson biểu diễn `byte[]` thành Base64 string khi serialize JSON.
- Khi deserialize JSON string vào `byte[]`, Jackson giải mã Base64 thành byte gốc.
- `byte[]` và `String` chứa Base64 khác nhau: kiểu đầu được Jackson tự encode/decode; kiểu sau chỉ là văn bản.
- Base64 chuẩn dùng `+` và `/`; URL-safe dùng `-` và `_`; padding và line break phải theo hợp đồng hai bên.
- `ObjectMapper.setBase64Variant(...)` cho phép chọn biến thể Base64 phù hợp.
- `JsonGenerator.writeBinary(...)` và `JsonParser.getBinaryValue(...)`/`readBinaryValue(...)` hỗ trợ xử lý binary ở mức streaming.
- Base64 làm payload lớn hơn khoảng một phần ba; file lớn thường phù hợp với multipart hoặc endpoint binary hơn.
- Base64 không phải mã hóa bảo mật. Hãy giới hạn kích thước, kiểm tra tệp và bảo vệ dữ liệu theo yêu cầu hệ thống.

Khi thiết kế API có dữ liệu nhị phân, hãy thống nhất kiểu trường, Base64 variant, padding, giới hạn kích thước và cách xử lý null/empty. Sau đó chọn object binding hoặc streaming phù hợp với kích thước payload để việc trao đổi dữ liệu an toàn và hiệu quả.
