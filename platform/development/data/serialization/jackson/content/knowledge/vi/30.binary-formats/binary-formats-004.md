# Làm việc với dữ liệu nhị phân mà không mặc định qua chuỗi

Dữ liệu nhị phân như ảnh, PDF, file nén, audio hoặc nội dung mã hóa không phải văn bản. Khi đưa nó vào JSON, Jackson thường biểu diễn mảng byte (byte[]) thành chuỗi Base64 vì JSON không có kiểu byte-string riêng. Điều đó không có nghĩa ứng dụng phải tự chuyển byte thành String trước khi gọi Jackson.

Với JSON, có thể để Jackson encode/decode Base64 trực tiếp từ byte[], hoặc dùng streaming API để đọc từ InputStream và ghi ra OutputStream mà không cần tạo một mảng byte lớn trong ứng dụng. Nếu giao thức cho phép dùng định dạng nhị phân như CBOR hoặc Smile, Jackson còn có thể ghi binary value dưới dạng native binary token thay vì Base64 text.

Lựa chọn phù hợp phụ thuộc vào hợp đồng truyền tải, kích thước dữ liệu, khả năng tương thích của consumer và giới hạn bộ nhớ.

## 1. Vì sao không nên biến byte tùy ý thành String?

Một file PNG, PDF hoặc ZIP là chuỗi byte theo một định dạng riêng. Các byte đó không nhất thiết là văn bản UTF-8.

Cách làm sai thường gặp:

~~~java
String text = new String(fileBytes, StandardCharsets.UTF_8);
String json = mapper.writeValueAsString(text);
~~~

Nếu byte không phải UTF-8 hợp lệ, quá trình giải mã có thể thay thế byte lỗi bằng ký tự thay thế hoặc tạo ra nội dung khác. Khi chuyển ngược String thành byte, dữ liệu gốc có thể đã mất.

Ví dụ, một file ảnh có thể chứa byte không tạo thành chuỗi UTF-8 hợp lệ. Charset decoder không có nhiệm vụ giữ nguyên mọi byte; nó diễn giải byte theo encoding văn bản.

Chỉ chuyển thành String khi dữ liệu thực sự là văn bản và encoding đã được xác định, ví dụ UTF-8 text file. Với nội dung binary, giữ nguyên byte[], stream hoặc một binary container.

## 2. JSON không có kiểu binary riêng

JSON chuẩn có các kiểu object, array, string, number, boolean và null. Không có kiểu byte[] hoặc binary blob.

Vì vậy, khi binary được nhúng vào JSON, ứng dụng thường dùng Base64 để biểu diễn byte thành các ký tự ASCII.

~~~json
{
  "fileName": "hello.txt",
  "contentType": "text/plain",
  "content": "SGVsbG8sIHdvcmxkIQ=="
}
~~~

Giá trị content là Base64 của các byte nội dung. Nó là JSON string về mặt cú pháp, nhưng ý nghĩa theo hợp đồng API là binary được encode.

Base64 là encoding, không phải encryption. Bất kỳ consumer nào có dữ liệu đều có thể decode nó. Không dùng Base64 để che giấu secret.

## 3. Để Jackson xử lý byte[] trực tiếp

Jackson Databind có serializer/deserializer tích hợp cho byte[]. Khi serialize một property kiểu byte[] trong JSON, Jackson thường ghi giá trị dưới dạng Base64 string. Khi deserialize, Jackson decode Base64 thành byte array.

DTO:

~~~java
public class Attachment {
    private String fileName;
    private String contentType;
    private byte[] content;

    public String getFileName() {
        return fileName;
    }

    public void setFileName(String fileName) {
        this.fileName = fileName;
    }

    public String getContentType() {
        return contentType;
    }

    public void setContentType(String contentType) {
        this.contentType = contentType;
    }

    public byte[] getContent() {
        return content;
    }

    public void setContent(byte[] content) {
        this.content = content;
    }
}
~~~

Serialize:

~~~java
ObjectMapper mapper = new ObjectMapper();

Attachment attachment = new Attachment();
attachment.setFileName("hello.txt");
attachment.setContentType("text/plain");
attachment.setContent("Hello, world!".getBytes(StandardCharsets.UTF_8));

String json = mapper.writeValueAsString(attachment);
~~~

JSON có dạng:

~~~json
{
  "fileName": "hello.txt",
  "contentType": "text/plain",
  "content": "SGVsbG8sIHdvcmxkIQ=="
}
~~~

Deserialize:

~~~java
Attachment restored = mapper.readValue(json, Attachment.class);
byte[] originalBytes = restored.getContent();
~~~

Không cần gọi Base64.getEncoder().encodeToString(...) trước khi serialize hoặc tự decode sau khi deserialize. Jackson thực hiện chuyển đổi theo kiểu byte[].

### 3.1. byte[] khác Byte[]

Java có cả primitive array byte[] và wrapper array Byte[]. Jackson có hỗ trợ chuyên biệt cho byte[] để biểu diễn binary dưới dạng Base64. Byte[] là array của object wrapper và có thể đi theo cách xử lý array thông thường thay vì binary serializer chuyên biệt.

Nếu mục đích là lưu byte của file, ưu tiên byte[]. Không đổi sang Byte[] chỉ để mong có JSON array các số; nếu API thật sự cần từng byte dưới dạng number, hãy định nghĩa representation đó rõ ràng và cân nhắc kích thước.

## 4. Base64 làm dữ liệu lớn thêm bao nhiêu?

Với Base64, mỗi 3 byte đầu vào được biểu diễn bằng 4 ký tự. Kích thước chuỗi gần bằng:

\[
4 \times \left\lceil \frac{n}{3} \right\rceil
\]

Trong đó n là số byte gốc. Vì vậy, Base64 thường làm nội dung lớn hơn khoảng một phần ba, chưa tính overhead JSON.

Ví dụ gần đúng:

| Byte gốc | Kích thước Base64 |
|---:|---:|
| 3 B | 4 ký tự |
| 1 KiB | khoảng 1,368 ký tự |
| 1 MiB | khoảng 1.33 MiB |
| 10 MiB | khoảng 13.33 MiB |

Nếu giữ đồng thời byte[], String Base64 và toàn bộ JSON String, ứng dụng có thể phải giữ nhiều bản sao dữ liệu trong heap. Với file lớn, đây là nguyên nhân dễ gây áp lực bộ nhớ và garbage collection.

byte[] thuận tiện cho payload nhỏ hoặc vừa. Với payload lớn, streaming hoặc tách binary ra khỏi JSON thường phù hợp hơn.

## 5. Ghi binary vào JSON bằng JsonGenerator.writeBinary

Jackson Core có API JsonGenerator.writeBinary(...). API này ghi byte dưới dạng Base64 string theo quy tắc của JSON generator. Ứng dụng không cần tự tạo một String Base64 trung gian.

Ví dụ với byte[]:

~~~java
import com.fasterxml.jackson.core.JsonFactory;
import com.fasterxml.jackson.core.JsonGenerator;

import java.io.ByteArrayOutputStream;
import java.io.IOException;

JsonFactory factory = new JsonFactory();
byte[] fileBytes = loadFileBytes();

try (ByteArrayOutputStream output = new ByteArrayOutputStream();
     JsonGenerator generator = factory.createGenerator(output)) {

    generator.writeStartObject();
    generator.writeStringField("fileName", "report.pdf");
    generator.writeFieldName("content");
    generator.writeBinary(fileBytes);
    generator.writeEndObject();
    generator.flush();

    byte[] jsonBytes = output.toByteArray();
}
~~~

writeBinary(fileBytes) ghi field value như JSON Base64 string. jsonBytes là byte của toàn bộ tài liệu JSON đã serialize; nó không phải byte gốc của file.

Khi cần ghi ra HTTP response hoặc file, có thể tạo generator trực tiếp trên OutputStream đích thay vì dùng ByteArrayOutputStream, tránh giữ toàn bộ JSON output trong bộ nhớ.

### 5.1. Chọn Base64 variant khi hợp đồng yêu cầu

Jackson có Base64Variants để chọn quy ước Base64:

~~~java
import com.fasterxml.jackson.core.Base64Variants;

generator.writeBinary(
    Base64Variants.getDefaultVariant(),
    fileBytes,
    0,
    fileBytes.length
);
~~~

Producer và consumer cần thống nhất variant. Với JSON string, thông thường nên dùng variant không chèn line break để output tương thích rộng. Không tự đổi sang URL-safe Base64 nếu API chưa công bố điều đó.

Nếu dùng byte[] Databind serializer mặc định, Jackson áp dụng variant mặc định của mapper/generator. Chỉ tùy biến variant khi có yêu cầu hợp đồng cụ thể.

## 6. Stream file vào JSON mà không nạp toàn bộ file vào byte[]

Với file lớn, dùng overload nhận InputStream:

~~~java
import com.fasterxml.jackson.core.Base64Variants;
import com.fasterxml.jackson.core.JsonFactory;
import com.fasterxml.jackson.core.JsonGenerator;

import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.file.Files;
import java.nio.file.Path;

public void writeAttachment(Path file, OutputStream output)
        throws IOException {

    JsonFactory factory = new JsonFactory();

    try (JsonGenerator generator = factory.createGenerator(output);
         InputStream input = Files.newInputStream(file)) {

        generator.writeStartObject();
        generator.writeStringField("fileName", file.getFileName().toString());
        generator.writeFieldName("content");

        // -1 yêu cầu đọc binary input đến EOF.
        generator.writeBinary(
            Base64Variants.getDefaultVariant(),
            input,
            -1
        );

        generator.writeEndObject();
    }
}
~~~

Generator encode dữ liệu từ stream và ghi ra output theo từng phần. Ứng dụng không cần gọi Files.readAllBytes() để tạo một byte[] có kích thước bằng file.

Overload này nhận int dataLength; truyền độ dài đã biết nếu phù hợp với giới hạn kiểu int, hoặc -1 để đọc đến EOF theo API. Với stream lớn hơn giới hạn kích thước mà API/transport của ứng dụng hỗ trợ, nên dùng giao thức upload/download streaming riêng hoặc chia thành các object độc lập theo contract thay vì tạo một JSON document chứa blob khổng lồ.

Đóng stream đúng ownership. Trong ví dụ, method sở hữu InputStream nên đóng nó. JsonGenerator thường đóng output target khi đóng generator; nếu caller cần giữ output stream mở, cấu hình auto-close target theo API Jackson version hoặc dùng wrapper phù hợp để tách quyền sở hữu.

## 7. Đọc Base64 từ JSON vào OutputStream

Nếu dùng DTO có field byte[], Jackson sẽ materialize toàn bộ binary vào mảng. Với file lớn, có thể dùng streaming parser để decode trực tiếp ra OutputStream.

JSON:

~~~json
{
  "fileName": "report.pdf",
  "content": "JVBERi0xLjQK..."
}
~~~

Ví dụ:

~~~java
import com.fasterxml.jackson.core.Base64Variants;
import com.fasterxml.jackson.core.JsonFactory;
import com.fasterxml.jackson.core.JsonParser;
import com.fasterxml.jackson.core.JsonToken;

import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;

public void readAttachment(InputStream input, OutputStream fileOutput)
        throws IOException {

    JsonFactory factory = new JsonFactory();

    try (JsonParser parser = factory.createParser(input)) {
        if (parser.nextToken() != JsonToken.START_OBJECT) {
            throw new IOException("Expected an attachment object");
        }

        while (parser.nextToken() != JsonToken.END_OBJECT) {
            String fieldName = parser.currentName();
            JsonToken valueToken = parser.nextToken();

            if ("content".equals(fieldName)) {
                if (valueToken != JsonToken.VALUE_STRING) {
                    throw new IOException("content must be a Base64 string");
                }

                parser.readBinaryValue(
                    Base64Variants.getDefaultVariant(),
                    fileOutput
                );
            } else {
                parser.skipChildren();
            }
        }
    }
}
~~~

readBinaryValue(...) đọc Base64 value hiện tại và ghi byte đã decode vào OutputStream. Cách này tránh tạo một byte[] ứng dụng có kích thước bằng toàn bộ file.

Parser vẫn phải đọc và giải mã nội dung JSON text. Nó có thể dùng buffer nội bộ; streaming giúp tránh việc ứng dụng materialize thêm toàn bộ binary vào một mảng lớn, chứ không có nghĩa mọi tầng đều hoàn toàn không buffer.

Nếu field content bị thiếu, null hoặc sai kiểu, ứng dụng cần từ chối theo hợp đồng. Ví dụ trên minh họa luồng đọc; code production nên kiểm tra field bắt buộc, giới hạn tổng byte được ghi, xử lý duplicate property và chỉ commit file sau khi toàn bộ JSON document hợp lệ.

## 8. Không dùng writeRaw để chèn byte tùy ý vào JSON

Không nên cố ghi binary thô vào JSON bằng:

~~~java
generator.writeRaw(binaryData);
~~~

JSON text yêu cầu dữ liệu tuân theo cú pháp UTF-8 JSON. Một dãy byte tùy ý có thể chứa ký tự điều khiển, byte không hợp lệ hoặc ký tự phá vỡ cấu trúc JSON.

writeRaw(...) dành cho nội dung JSON text đã được đảm bảo hợp lệ theo đúng vị trí, không phải API upload binary. Dùng writeBinary(...) để Jackson encode byte thành JSON string Base64.

Tương tự, không nối chuỗi thủ công:

~~~java
String json = "{\"content\":\"" + base64 + "\"}";
~~~

Cách nối chuỗi dễ tạo lỗi escaping, quote, encoding và vô tình ghi dữ liệu không đúng vị trí. Dùng JsonGenerator hoặc Databind để quản lý cấu trúc JSON.

## 9. byte[] và streaming parser có thể được kết hợp với DTO

Với file nhỏ/vừa, DTO có byte[] thường là lựa chọn đơn giản:

~~~java
Attachment attachment = mapper.readValue(
    requestBody,
    Attachment.class
);
~~~

Với file lớn, không nên deserialize toàn bộ DTO nếu field binary làm tăng heap đáng kể. Có thể:

1. Dùng JsonParser để đọc metadata từng field.
2. Khi đến field binary, gọi readBinaryValue(...) để ghi ra file tạm hoặc object storage stream.
3. Parse đến hết document và kiểm tra không có trailing content.
4. Validate metadata như filename, content type và kích thước thực tế.
5. Commit file tạm sau khi document hợp lệ; xóa file tạm nếu parse thất bại.

~~~text
JSON request stream
        |
        v
    JsonParser
        |
        +---- metadata ----> DTO nhỏ / biến Java
        |
        +---- content -----> readBinaryValue(OutputStream)
                                  |
                                  v
                              temp file
                                  |
                                  v
                       parse + validate thành công?
                           |              |
                          Có             Không
                           |              |
                           v              v
                         commit         delete
~~~

Cách này tránh phải giữ cả request body, Base64 String và binary byte[] cùng lúc.

## 10. Dùng định dạng nhị phân native: CBOR

Nếu cả producer và consumer có thể dùng binary protocol, CBOR là một lựa chọn chuẩn hóa. CBOR có major type byte string nên binary được biểu diễn như dữ liệu nhị phân trực tiếp, không cần chuyển thành Base64 text.

Jackson hỗ trợ CBOR qua artifact:

~~~text
com.fasterxml.jackson.dataformat:jackson-dataformat-cbor
~~~

Ví dụ:

~~~java
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.dataformat.cbor.CBORFactory;

public record BinaryMessage(String name, byte[] content) {}

CBORFactory factory = new CBORFactory();
ObjectMapper cborMapper = new ObjectMapper(factory);

BinaryMessage message = new BinaryMessage(
    "image.bin",
    fileBytes
);

byte[] cborDocument = cborMapper.writeValueAsBytes(message);

BinaryMessage restored = cborMapper.readValue(
    cborDocument,
    BinaryMessage.class
);
~~~

Property content được ghi dưới dạng CBOR byte string theo định dạng CBOR, không phải JSON Base64 string.

cborDocument vẫn là byte array chứa toàn bộ tài liệu CBOR đã mã hóa. Nó bao gồm cấu trúc document, field name và binary payload; không phải chỉ payload gốc.

CBOR phù hợp khi hệ sinh thái consumer hỗ trợ CBOR và API có thể công bố media type/schema tương ứng. Không gửi CBOR bytes cho client đang chờ JSON rồi kỳ vọng nó đọc được.

## 11. Dùng Smile để truyền dữ liệu nhị phân theo hệ sinh thái Jackson

Smile là một định dạng nhị phân JSON-like của Jackson. Nó hỗ trợ các kiểu cấu trúc tương tự JSON và có cách biểu diễn binary value mà không cần chuyển nội dung thành Base64 text.

Artifact:

~~~text
com.fasterxml.jackson.dataformat:jackson-dataformat-smile
~~~

Ví dụ:

~~~java
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.dataformat.smile.SmileFactory;

SmileFactory factory = new SmileFactory();
ObjectMapper smileMapper = new ObjectMapper(factory);

byte[] smileDocument = smileMapper.writeValueAsBytes(message);

BinaryMessage restored = smileMapper.readValue(
    smileDocument,
    BinaryMessage.class
);
~~~

Smile hữu ích trong hệ thống Java/Jackson hoặc môi trường đã thống nhất format này. Nó không phải JSON text và không thể đọc bằng JSON parser thông thường. Producer/consumer phải thống nhất codec, version compatibility, framing và content type.

## 12. JSON Base64, CBOR và Smile khác nhau thế nào?

| Tiêu chí | JSON + Base64 | CBOR | Smile |
|---|---|---|---|
| Dạng tài liệu | Text JSON | Binary | Binary |
| Binary field | Base64 string | Native byte string | Native binary value |
| Overhead Base64 | Có, khoảng 33% | Không cần Base64 | Không cần Base64 |
| Dễ debug bằng text editor | Cao hơn | Thấp | Thấp |
| Tương thích với client JSON phổ thông | Cao | Cần CBOR support | Cần Smile support |
| Jackson hỗ trợ | Databind/Core | jackson-dataformat-cbor | jackson-dataformat-smile |
| Phù hợp | API web phổ biến, file nhỏ/vừa | Binary protocol cần chuẩn mở | Hệ sinh thái đã dùng Smile |

Không có lựa chọn nào luôn tốt nhất. JSON Base64 dễ tương thích nhưng tăng kích thước và chi phí encode/decode. CBOR có binary type chuẩn, còn Smile phù hợp khi các bên chủ động chọn định dạng của Jackson.

## 13. Binary trong JSON khác với JSON document được ghi thành byte[]

Hai thao tác dễ bị nhầm:

~~~java
byte[] fileBytes = Files.readAllBytes(path);
byte[] jsonBytes = mapper.writeValueAsBytes(attachment);
~~~

- fileBytes: byte nội dung file gốc.
- jsonBytes: byte UTF-8 của JSON document đã serialize; binary field bên trong JSON đã được chuyển thành Base64 string.

Nếu gửi jsonBytes, HTTP body vẫn là JSON text. Việc method trả về byte[] không làm media type trở thành binary format.

Ngược lại, với CBOR:

~~~java
byte[] cborBytes = cborMapper.writeValueAsBytes(attachment);
~~~

cborBytes là tài liệu CBOR binary. Phân biệt theo JsonFactory/codec và content type, không chỉ dựa vào kiểu Java byte[].

## 14. Khi nào nên lưu binary riêng và chỉ gửi reference trong JSON?

Với file rất lớn hoặc cần tải xuống nhiều lần, thường tốt hơn nếu lưu blob trong file/object storage và để JSON mang metadata/reference:

~~~json
{
  "fileId": "file_8f31",
  "fileName": "archive.zip",
  "contentType": "application/zip",
  "size": 524288000,
  "sha256": "…"
}
~~~

Luồng:

1. Client upload binary qua endpoint hoặc object storage upload.
2. Server kiểm tra kích thước, checksum và quyền.
3. Binary được lưu trong blob storage.
4. JSON resource chỉ lưu file ID, metadata và trạng thái.
5. Consumer tải binary qua endpoint riêng hoặc URL có thời hạn.

Lợi ích:

- Không cần Base64 encode/decode trên mỗi lần đọc JSON.
- Metadata có thể cache riêng với nội dung file.
- Binary có thể được stream trực tiếp.
- Dễ áp dụng quota, retention, checksum và access control.
- Không phải deserialize một DTO chứa file lớn chỉ để đọc metadata.

Nếu dùng URL ký có thời hạn, không log URL đầy đủ vì query parameter có thể chứa credential tạm thời. Reference file cũng cần được kiểm tra quyền truy cập; biết file ID không đồng nghĩa được phép tải.

## 15. Kiểm tra kích thước và tính toàn vẹn

Dù dùng Base64, CBOR hay stream, binary input vẫn cần validation.

Các kiểm tra phổ biến:

- Giới hạn kích thước trước và trong lúc đọc.
- Không tin Content-Length, tên file hoặc MIME type do client gửi.
- Kiểm tra file signature/magic bytes khi loại file có yêu cầu.
- Tính checksum như SHA-256 nếu cần kiểm tra tính toàn vẹn.
- Không dùng filename trực tiếp làm path trên filesystem.
- Quét malware hoặc áp dụng policy xử lý file theo môi trường.
- Ghi file tạm và chỉ commit sau khi toàn bộ request hợp lệ.
- Xóa file tạm khi parse, validation hoặc downstream thất bại.

Ví dụ giới hạn byte khi stream:

~~~java
import java.io.FilterOutputStream;
import java.io.IOException;
import java.io.OutputStream;

public final class LimitedOutputStream extends FilterOutputStream {
    private final long maxBytes;
    private long count;

    public LimitedOutputStream(OutputStream delegate, long maxBytes) {
        super(delegate);
        this.maxBytes = maxBytes;
    }

    @Override
    public void write(int value) throws IOException {
        ensureCapacity(1);
        out.write(value);
        count++;
    }

    @Override
    public void write(byte[] data, int offset, int length)
            throws IOException {
        ensureCapacity(length);
        out.write(data, offset, length);
        count += length;
    }

    private void ensureCapacity(int additional) throws IOException {
        if (additional > maxBytes - count) {
            throw new IOException("Binary payload exceeds configured limit");
        }
    }

    public long getCount() {
        return count;
    }
}
~~~

Bọc file output:

~~~java
try (OutputStream file = Files.newOutputStream(tempFile);
     OutputStream limited = new LimitedOutputStream(file, maxBytes)) {

    parser.readBinaryValue(
        Base64Variants.getDefaultVariant(),
        limited
    );
}
~~~

Giới hạn output decoded bytes bảo vệ dung lượng file và storage. Vẫn cần giới hạn kích thước HTTP body/JSON text ở tầng transport vì Base64 input lớn hơn dữ liệu đã decode.

## 16. Kiểm tra Base64 sai định dạng và payload không hợp lệ

Nếu JSON có Base64 string sai padding hoặc ký tự không thuộc alphabet được chấp nhận, Jackson có thể ném lỗi parse/mapping khi decode.

Không nên bắt lỗi rồi dùng một phần byte đã đọc như file hoàn chỉnh. Nếu streaming trực tiếp ra file tạm, khi decode lỗi phải xóa file tạm hoặc đánh dấu nó là incomplete.

Cũng không nên chỉ dựa vào việc Base64 decode thành công để kết luận file an toàn. Bất kỳ byte sequence nào cũng có thể encode thành Base64; cần kiểm tra định dạng file và policy nghiệp vụ riêng.

Nếu API nhận Base64 string từ nhiều nguồn, công bố rõ variant và chính sách whitespace/padding. Tránh chấp nhận nhiều biến thể hơn cần thiết vì có thể gây khác biệt giữa consumer và server.

## 17. Kiểm thử binary serialization

Test với byte có giá trị ngoài ASCII để chắc chắn code không lỡ decode thành text:

~~~java
import static org.junit.jupiter.api.Assertions.assertArrayEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;

class BinaryJsonTest {
    private final ObjectMapper mapper = new ObjectMapper();

    @Test
    void roundTripsArbitraryBytesThroughBase64() throws Exception {
        byte[] original = new byte[] {
            0x00, 0x01, 0x7F, (byte) 0x80, (byte) 0xFF
        };

        String json = mapper.writeValueAsString(original);
        byte[] decoded = mapper.readValue(json, byte[].class);

        assertArrayEquals(original, decoded);
    }

    @Test
    void serializesByteArrayPropertyAsBase64String() throws Exception {
        Attachment attachment = new Attachment();
        attachment.setFileName("data.bin");
        attachment.setContent(originalBytes());

        JsonNode json = mapper.readTree(
            mapper.writeValueAsString(attachment)
        );

        assertTrue(json.get("content").isTextual());
        assertArrayEquals(
            originalBytes(),
            mapper.treeToValue(json.get("content"), byte[].class)
        );
    }

    private byte[] originalBytes() {
        return new byte[] { 0x00, 0x10, (byte) 0xFE, (byte) 0xFF };
    }
}
~~~

Với streaming API, test nên xác nhận:

- Output JSON có Base64 string hợp lệ.
- Đọc lại stream tạo đúng byte sequence.
- File vượt giới hạn bị từ chối.
- Base64 sai định dạng không tạo file hoàn chỉnh.
- Parser lỗi sau field binary không làm file tạm được commit.
- Stream được đóng theo ownership đã quy định.

Với CBOR/Smile, test nên kiểm tra bằng mapper đúng factory và đọc lại bằng cùng định dạng. Không dùng JSON mapper để đọc binary document.

## 18. Các lỗi thường gặp

**Dùng new String(bytes, UTF_8) cho file bất kỳ.** Charset decoding có thể làm thay đổi byte; chỉ làm vậy với nội dung thực sự là text UTF-8.

**Tự Base64 thành String trước khi đưa cho Jackson.** Với byte[], Jackson đã có binary serializer. Chuyển thủ công có thể tạo thêm bản sao lớn trong heap.

**Dùng DTO byte[] cho file quá lớn.** Deserialization sẽ materialize toàn bộ nội dung thành mảng. Dùng parser streaming hoặc upload/download stream.

**Cho rằng writeValueAsBytes() luôn trả binary payload.** Với JSON mapper, nó trả byte của JSON document; binary field vẫn là Base64 text.

**Dùng writeRaw() để chèn byte vào JSON.** JSON text không hỗ trợ byte tùy ý; dùng writeBinary().

**Nhầm JSON Base64 với CBOR/Smile.** Base64 là String trong JSON; CBOR/Smile có native binary representation và cần codec tương ứng.

**Không thống nhất Base64 variant.** URL-safe và MIME variant có alphabet/padding khác nhau; producer và consumer cần cùng quy ước.

**Không giới hạn decoded size.** Một Base64 payload có thể tiêu tốn bộ nhớ hoặc dung lượng đĩa lớn; giới hạn ở cả transport và output stream.

**Commit file trước khi JSON document hợp lệ hoàn toàn.** Lỗi ở field sau có thể khiến ứng dụng lưu file từ một request lỗi. Dùng temporary file và commit sau validation.

## 19. Ghi nhớ

- Không chuyển byte tùy ý thành String; charset decoding chỉ phù hợp khi dữ liệu thực sự là text với encoding đã biết.
- Trong JSON, Jackson serialize byte[] thành Base64 string và deserialize trực tiếp về byte array.
- JsonGenerator.writeBinary(...) encode binary mà không cần tự tạo Base64 String.
- JsonParser.readBinaryValue(...) decode trực tiếp ra OutputStream, hữu ích cho file lớn.
- Base64 làm payload tăng khoảng một phần ba và vẫn là text trong JSON.
- writeValueAsBytes() với JSON mapper trả byte của toàn bộ JSON document, không phải byte gốc của field binary.
- CBOR và Smile hỗ trợ binary value native; dùng CBORFactory hoặc SmileFactory và thống nhất codec/media type với consumer.
- Với dữ liệu lớn, ưu tiên streaming hoặc lưu blob riêng rồi gửi reference/metadata qua JSON.
- Giới hạn decoded bytes, kiểm tra checksum/file signature và chỉ commit file sau khi request hợp lệ.
- Kiểm thử với byte ngoài ASCII, Base64 lỗi, stream lớn và các đường lỗi/cleanup.

