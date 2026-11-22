# Biên dịch XSD thành Schema

## 1. Biên dịch schema là chuẩn bị hợp đồng để dùng lại

Tệp XSD là văn bản XML mô tả các ràng buộc của tài liệu đầu vào. Trước khi kiểm tra nhiều tài liệu theo cùng hợp đồng, Java cần đọc các khai báo đó, kiểm tra tính nhất quán và chuẩn bị một biểu diễn trong bộ nhớ.

Trong JAXP, bước này được gọi là **biên dịch schema**:

```text
XSD và các schema phụ được phép
    → SchemaFactory.newSchema(...)
    → Schema
    → schema.newValidator()
    → kiểm tra từng tài liệu XML
```

`SchemaFactory` là bộ biên dịch; `Schema` giữ tập ràng buộc đã chuẩn bị; `Validator` thực hiện một lần kiểm tra. Biên dịch XSD không tạo tệp `.class`, không chạy `javac` cho XSD và không tự sinh các lớp mô hình Java.

Việc tách hai bước có ý nghĩa thực tế: ứng dụng có thể phát hiện hợp đồng sai ngay lúc khởi tạo, biên dịch một lần và kiểm tra nhiều tài liệu sau đó. Không cần đọc và phân tích cùng một XSD cho mỗi yêu cầu.

`javax.xml.validation` vẫn là API công khai của module `java.xml` trên Java hiện đại. Bài dùng Java 17+ và XSD 1.0, không dùng lớp nội bộ của bộ xử lý XML. Xem [vai trò SchemaFactory](https://docs.oracle.com/en/java/javase/25/docs/api/java.xml/javax/xml/validation/SchemaFactory.html).

## 2. Chọn đúng bộ biên dịch và cấu hình trước khi tạo Schema

Đối với XSD, hai cách tạo factory thường gặp là:

```java
SchemaFactory factory = SchemaFactory.newDefaultInstance();
```

hoặc:

```java
SchemaFactory factory = SchemaFactory.newInstance(
        XMLConstants.W3C_XML_SCHEMA_NS_URI);
```

Cách thứ nhất chọn triển khai mặc định tích hợp của JDK. Cách thứ hai yêu cầu bộ cung cấp hỗ trợ ngôn ngữ W3C XML Schema thông qua cơ chế tìm bộ cung cấp của JAXP; thư viện trên đường dẫn lớp hoặc cấu hình môi trường có thể ảnh hưởng đến triển khai được chọn.

`XMLConstants.W3C_XML_SCHEMA_NS_URI` xác định **ngôn ngữ schema**, không phải đường dẫn tải tệp XSD của ứng dụng. Cũng không thay nó bằng `targetNamespace` của hợp đồng đang viết.

JAXP chỉ bắt buộc hỗ trợ W3C XML Schema 1.0. Không mặc định rằng dùng một JDK mới sẽ khiến mọi tính năng XSD 1.1 như các khai báo assertion được hỗ trợ. Nếu hợp đồng yêu cầu ngôn ngữ/phiên bản khác, cần chọn và kiểm thử bộ cung cấp thích hợp.

Trước khi gọi `newSchema(...)`, thiết lập:

- Chính sách giới hạn xử lý bằng `FEATURE_SECURE_PROCESSING`.
- Chính sách truy cập tài nguyên ngoài của XSD.
- Cách xử lý lỗi trong quá trình biên dịch.
- Cách phân giải `include`/`import` nếu schema có phụ thuộc.

Đổi cấu hình factory sau khi đã nhận được `Schema` không phải cách cập nhật hợp đồng đã biên dịch. Muốn một tập ràng buộc khác, biên dịch lại đầu vào phù hợp và thay đối tượng schema theo vòng đời của ứng dụng.

## 3. Ví dụ hoàn chỉnh: biên dịch từ tệp và từ chuỗi trong bộ nhớ

Ví dụ tạo hợp đồng cho số đo `reading` là số nguyên từ `0` đến `100`. Chương trình biên dịch tệp XSD, kiểm tra hai XML rồi cố biên dịch một bản XSD đã bị sửa để tham chiếu đến kiểu không tồn tại.

### 3.1. Tệp sensor.xsd

Tạo tệp `sensor.xsd` với nội dung:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"
           xmlns:m="urn:example:meter:v1"
           targetNamespace="urn:example:meter:v1">
  <xs:simpleType name="Level">
    <xs:restriction base="xs:integer">
      <xs:minInclusive value="0"/>
      <xs:maxInclusive value="100"/>
    </xs:restriction>
  </xs:simpleType>
  <xs:element name="reading" type="m:Level"/>
</xs:schema>
```

`Level` là kiểu do schema định nghĩa. `m:Level` tham chiếu đến kiểu đó bằng namespace `urn:example:meter:v1`; nó không phải kiểu dựng sẵn thuộc namespace `xs`.

### 3.2. Tệp SchemaCompileDemo.java

Lưu chương trình sau trong cùng thư mục:

```java
import java.io.IOException;
import java.io.InputStream;
import java.io.StringReader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import javax.xml.XMLConstants;
import javax.xml.transform.stream.StreamSource;
import javax.xml.validation.Schema;
import javax.xml.validation.SchemaFactory;
import javax.xml.validation.Validator;
import org.xml.sax.SAXException;
import org.xml.sax.SAXParseException;
import org.xml.sax.helpers.DefaultHandler;

public class SchemaCompileDemo {
    private static final DefaultHandler STOP_ON_ERROR = new DefaultHandler() {
        @Override
        public void error(SAXParseException error) throws SAXException {
            throw error;
        }

        @Override
        public void fatalError(SAXParseException error) throws SAXException {
            throw error;
        }
    };

    private static SchemaFactory compiler() throws SAXException {
        SchemaFactory factory = SchemaFactory.newDefaultInstance();
        factory.setFeature(XMLConstants.FEATURE_SECURE_PROCESSING, true);
        factory.setProperty(XMLConstants.ACCESS_EXTERNAL_DTD, "");
        factory.setProperty(XMLConstants.ACCESS_EXTERNAL_SCHEMA, "");
        factory.setErrorHandler(STOP_ON_ERROR);
        return factory;
    }

    private static Schema compileFile(Path file)
            throws IOException, SAXException {
        Path absolute = file.toAbsolutePath().normalize();
        try (InputStream bytes = Files.newInputStream(absolute)) {
            StreamSource source = new StreamSource(
                    bytes, absolute.toUri().toString());
            return compiler().newSchema(source);
        }
    }

    private static Schema compileText(String xsd, String baseUri)
            throws SAXException {
        StreamSource source = new StreamSource(new StringReader(xsd), baseUri);
        return compiler().newSchema(source);
    }

    private static void check(Schema schema, String label, String xml)
            throws IOException, SAXException {
        Validator validator = schema.newValidator();
        validator.setFeature(XMLConstants.FEATURE_SECURE_PROCESSING, true);
        validator.setProperty(XMLConstants.ACCESS_EXTERNAL_DTD, "");
        validator.setProperty(XMLConstants.ACCESS_EXTERNAL_SCHEMA, "");
        validator.setErrorHandler(STOP_ON_ERROR);
        try {
            validator.validate(new StreamSource(new StringReader(xml)));
            System.out.println(label + "=VALID");
        } catch (SAXException ex) {
            System.out.println(label + "=INVALID");
        }
    }

    public static void main(String[] args) throws Exception {
        Path file = Path.of(args.length == 0 ? "sensor.xsd" : args[0]);
        Schema schema = compileFile(file);
        System.out.println("compiled=" + (schema != null));

        check(schema, "reading-5",
                "<reading xmlns=\"urn:example:meter:v1\">5</reading>");
        check(schema, "reading-101",
                "<reading xmlns=\"urn:example:meter:v1\">101</reading>");

        String brokenXsd = Files.readString(file, StandardCharsets.UTF_8)
                .replace("m:Level", "m:Missing");
        try {
            compileText(brokenXsd, file.toAbsolutePath().toUri().toString());
            throw new IllegalStateException("Broken XSD unexpectedly compiled");
        } catch (SAXException ex) {
            System.out.println("broken-xsd=COMPILE_ERROR");
        }
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 SchemaCompileDemo.java
java SchemaCompileDemo sensor.xsd
```

Stdout:

```text
compiled=true
reading-5=VALID
reading-101=INVALID
broken-xsd=COMPILE_ERROR
```

Giải thích kết quả:

1. `compiled=true`: tệp XSD được đọc và tạo thành một đối tượng `Schema`.
2. `reading-5=VALID`: số đo `5` thuộc miền giá trị mà schema quy định.
3. `reading-101=INVALID`: schema vẫn là schema đúng; tài liệu XML này vi phạm giới hạn trên.
4. `broken-xsd=COMPILE_ERROR`: bản sao XSD trỏ đến `m:Missing`, nhưng không định nghĩa kiểu đó. Lỗi xảy ra khi gọi `newSchema(...)`, trước khi có thể dùng bản schema này để kiểm tra XML.

Các nhãn kết quả do chương trình tự in; không dựa vào câu chữ thông báo lỗi cụ thể của từng JDK. Nhánh kiểm tra `check(...)` chỉ minh họa hai XML cố định; trong một dịch vụ thực tế phải phân biệt thêm lỗi cấu hình, tài nguyên và lỗi dữ liệu để báo đúng nguyên nhân.

### 3.3. Những điểm quan trọng trong phương thức biên dịch

`compileFile(...)` mở tệp bằng `InputStream`, giữ nguyên dữ liệu byte để bộ đọc XML xử lý khai báo mã hóa. `try-with-resources` đóng luồng sau khi `newSchema(...)` hoàn tất. Đối tượng `Schema` đã tạo không phụ thuộc vào việc giữ luồng đầu vào đó mở.

`compileText(...)` dùng `StringReader` vì dữ liệu đã là chuỗi ký tự Java. Không dùng `new StreamSource(xsd)` để truyền nội dung XSD: constructor nhận một `String` ở vị trí đó hiểu chuỗi là **system identifier/URI**, không phải văn bản XML. Xem [các dạng StreamSource](https://docs.oracle.com/en/java/javase/25/docs/api/java.xml/javax/xml/transform/stream/StreamSource.html).

`STOP_ON_ERROR` ném lại lỗi `error` và `fatalError`. Bộ biên dịch không được coi là thành công về mặt ứng dụng chỉ vì một bộ xử lý lỗi tùy chỉnh đã ghi thông báo rồi cho chạy tiếp.

## 4. Chọn dạng nguồn XSD và giữ địa chỉ gốc

| Nguồn đang có | Cách cung cấp phù hợp | Lưu ý |
| --- | --- | --- |
| Tệp XSD | `newSchema(file)` hoặc `StreamSource` từ tệp/luồng | Cần địa chỉ gốc nếu có tham chiếu tương đối |
| URL tài nguyên do ứng dụng kiểm soát | `newSchema(url)` hoặc `StreamSource` có URI | Việc đọc nguồn gốc và các phụ thuộc phải nằm trong chính sách cho phép |
| Chuỗi XSD trong bộ nhớ | `StreamSource(new StringReader(text), baseUri)` | Chuỗi là nội dung; `baseUri` cung cấp ngữ cảnh địa chỉ |
| Dữ liệu byte đã mở | `StreamSource(inputStream, baseUri)` | Ứng dụng quản lý vòng đời luồng |

### systemId là gì và vì sao cần thiết?

Trong chương trình, `absolute.toUri().toString()` tạo một URI tuyệt đối cho nguồn XSD. `systemId` có hai vai trò hữu ích:

- Cung cấp địa chỉ gốc để giải quyết đường dẫn tương đối trong schema.
- Đưa danh tính nguồn vào chẩn đoán lỗi.

Giả sử một schema chứa:

```xml
<xs:include schemaLocation="types.xsd"/>
```

`types.xsd` được hiểu tương đối với địa chỉ của schema đang tham chiếu, không nên phụ thuộc tình cờ vào thư mục làm việc của tiến trình Java. Nếu đọc nội dung bằng `StringReader` rồi bỏ mất `systemId`, bộ biên dịch có thể không biết `types.xsd` ở đâu.

Một URI dạng `file:/.../schemas/root.xsd` có thể làm địa chỉ gốc cho tệp; tài nguyên đóng gói trong JAR cần giữ URI phù hợp của chính tài nguyên đó. Không dùng một đường dẫn Windows chưa chuyển sang URI làm cơ sở bằng cách nối chuỗi tùy tiện.

**Có systemId không đồng nghĩa với có quyền truy cập.** Trong ví dụ, `ACCESS_EXTERNAL_SCHEMA` bằng chuỗi rỗng, nên bộ biên dịch không được tự đọc schema phụ qua giao thức ngoài. Bổ sung `xs:include` vào tệp mẫu mà chưa có cơ chế phân giải hợp lệ sẽ không được giải quyết chỉ bằng việc đặt URI gốc.

Với `StreamSource` dựa trên `Reader`/`InputStream`, hãy tạo nguồn mới cho mỗi lần biên dịch. Luồng đã đọc hết không tự quay về đầu chỉ vì nó vẫn nằm trong cùng một đối tượng `StreamSource`.

## 5. XSD có include/import: biên dịch cả tập phụ thuộc được cho phép

Một đối tượng `Schema` có thể đại diện cho ràng buộc tạo nên từ nhiều tài liệu XSD. Không nên hiểu rằng biên dịch một tệp gốc chỉ quan tâm các ký tự có trong đúng tệp đó.

- `xs:include` thường dùng để ghép các khai báo trong cùng namespace, hoặc đưa schema không có target namespace vào ngữ cảnh thích hợp.
- `xs:import` dùng khi tham chiếu khai báo thuộc namespace khác.

Những ràng buộc về namespace vẫn phải đúng. Có đủ tệp trên đĩa không sửa được việc `type="m:Level"` trỏ sai URI hoặc local name.

Với một tập XSD đóng gói cùng ứng dụng, hướng triển khai là xác định rõ các tài nguyên phụ được phép rồi phân giải chúng bằng `LSResourceResolver` hoặc XML Catalog phù hợp. Bộ phân giải có thể ánh xạ một URI logic sang tài nguyên cục bộ đáng tin cậy, thay vì tải từ mạng tùy ý.

`LSResourceResolver` nhận các thông tin như namespace, `systemId` và `baseURI`. Nếu trả `null`, nó yêu cầu bộ xử lý thử cơ chế phân giải thông thường; **`null` không phải lệnh từ chối**. Nếu cần chặn một yêu cầu ngoài danh sách được phép, cơ chế phân giải và chính sách truy cập phải thực sự từ chối yêu cầu đó. Xem [hợp đồng LSResourceResolver](https://docs.oracle.com/en/java/javase/25/docs/api/java.xml/org/w3c/dom/ls/LSResourceResolver.html).

JAXP cũng có `newSchema(Source[])` để tạo một schema từ nhiều nguồn. Đây không phải phép nối văn bản các tệp XSD. Ngữ nghĩa kết hợp phụ thuộc ngôn ngữ schema, và có khác biệt được phép giữa các bộ cung cấp khi nhiều nguồn/import cùng namespace. Với một hợp đồng có tệp gốc và các quan hệ `include`/`import` rõ, hãy giữ đúng đồ thị phụ thuộc đó thay vì đưa tùy tiện mọi XSD tìm thấy vào một mảng.

### Đừng sửa lỗi phụ thuộc bằng cách mở tất cả truy cập

`ACCESS_EXTERNAL_DTD=""` chặn việc bộ xử lý tự truy cập DTD ngoài; `ACCESS_EXTERNAL_SCHEMA=""` chặn việc tự truy cập schema ngoài qua các giao thức. Chính sách này phù hợp với ví dụ một tệp XSD không phụ thuộc.

Nếu ứng dụng cần tệp phụ, hãy bổ sung cơ chế truy cập có kiểm soát. Đổi thành `"all"` chỉ để thông báo lỗi biến mất có thể khiến việc biên dịch tải tài nguyên từ nơi không dự định.

Bộ phân giải tùy chỉnh cũng có trách nhiệm bảo mật: nếu chính nó đọc URL hoặc tệp từ dữ liệu không tin cậy rồi trả nội dung, việc đặt thuộc tính chặn truy cập mặc định không tự làm đoạn mã đó an toàn. Chọn schema gốc và nguồn phụ phải do ứng dụng kiểm soát. Xem [cấu hình tài nguyên XML trong JAXP](https://docs.oracle.com/en/java/javase/25/security/java-api-xml-processing-jaxp-security-guide.html).

## 6. Phân biệt lỗi biên dịch hợp đồng với lỗi kiểm tra tài liệu

| Thời điểm | Ví dụ nguyên nhân | Cách hiểu |
| --- | --- | --- |
| Tạo factory/cấu hình | Không có bộ cung cấp thích hợp; feature không được hỗ trợ | Cấu hình môi trường/bộ cung cấp không đáp ứng yêu cầu |
| Mở nguồn XSD | Tệp không tồn tại, không có quyền đọc | Không lấy được đầu vào để biên dịch |
| `newSchema(...)` | XSD sai cú pháp; tham chiếu kiểu không tồn tại; phụ thuộc bị chặn | Chưa có một hợp đồng đã biên dịch dùng được theo cấu hình dự định |
| `validator.validate(...)` | Giá trị XML ngoài miền, thiếu phần tử bắt buộc | Tài liệu không thỏa hợp đồng đã chuẩn bị, hoặc lần kiểm tra gặp lỗi cần chẩn đoán |

`SAXParseException` thường cho thêm `systemId`, số dòng và số cột. Trong chẩn đoán, giữ thông tin nguồn và nguyên nhân gốc thay vì chỉ thông báo “XML sai”. Khi một tệp được ứng dụng tự mở bằng `Files.newInputStream`, lỗi mở tệp là `IOException`; nếu bộ xử lý tự mở tài nguyên trong lúc đọc schema, lỗi có thể nằm trong chuỗi nguyên nhân của lỗi SAX.

Đừng làm ba việc sau:

- Bắt mọi ngoại lệ rồi trả `null`, khiến nơi sử dụng tiếp tục với một schema không có thật.
- Khi biên dịch schema mới thất bại, tự thay bằng một schema dễ dãi hơn mà không có chính sách rõ ràng.
- Gộp lỗi XSD do ứng dụng cung cấp thành lỗi dữ liệu của mọi người gửi XML.

Một `ErrorHandler` chỉ ghi lỗi rồi trả về có thể khiến `newSchema(...)` trả một đối tượng sau khi đã báo lỗi, nhưng hợp đồng API không đảm bảo đối tượng đó có ý nghĩa để sử dụng. Nếu muốn thu thập nhiều lỗi thay vì dừng ở lỗi đầu, hãy lưu chúng và chỉ công bố schema mới khi không có lỗi thuộc mức phải từ chối.

Handler đặt trên `SchemaFactory` xử lý lỗi **biên dịch schema**; nó không tự được kế thừa sang từng `Validator`. Vì vậy ví dụ đặt handler riêng cho factory và cho mỗi validator.

## 7. Dùng lại Schema và cập nhật khi hợp đồng thay đổi

`Schema` là biểu diễn ràng buộc bất biến và an toàn để chia sẻ giữa các luồng. Một schema có thể tạo nhiều `Validator`; mỗi validator có trạng thái của lần kiểm tra và không được dùng đồng thời tùy tiện. `SchemaFactory` cũng không bảo đảm an toàn cho nhiều luồng cùng biên dịch.

Trong ứng dụng, vòng đời thường là:

```text
Khởi tạo hoặc cập nhật hợp đồng
    → biên dịch schema thành công
    → công bố Schema dùng chung
Mỗi lần tiếp nhận XML
    → tạo Validator riêng
    → cấu hình handler/chính sách cần thiết
    → kiểm tra tài liệu
```

Xem [hợp đồng bất biến và chia sẻ của Schema](https://docs.oracle.com/en/java/javase/25/docs/api/java.xml/javax/xml/validation/Schema.html).

Nếu sửa tệp XSD trên đĩa, một đối tượng `Schema` đã tạo không tự thay tập ràng buộc thành nội dung mới. Cần biên dịch lại rồi thay tham chiếu schema. Khi thay ở hệ thống đang chạy, chỉ công bố bản mới sau khi nó biên dịch thành công và đạt các kiểm tra cần thiết.

Nếu có bộ nhớ đệm, chỉ dùng đường dẫn tệp gốc làm khóa có thể giữ nhầm phiên bản: nội dung tệp hoặc schema phụ đã thay đổi nhưng tên vẫn như cũ. Phải gắn việc làm mới với phiên bản/nội dung của cả tập hợp đồng và cấu hình phân giải liên quan.

Không dựa vào `Schema.equals()` để xác định hai bản XSD có nội dung giống nhau. API không định nghĩa nó là phép so sánh tương đương của hợp đồng. Cũng không có định dạng lưu/đọc `Schema` biên dịch dùng chung giữa mọi bộ cung cấp do JAXP chuẩn quy định; thường lưu XSD và biên dịch lại theo vòng đời phù hợp.

## 8. Các nhầm lẫn dễ gặp

| Nhầm lẫn | Cách hiểu đúng |
| --- | --- |
| Tạo `SchemaFactory` là đã có schema | Phải cung cấp nguồn và gọi `newSchema(...)` |
| Gọi `newSchema()` không đối số là biên dịch tệp XSD hiện có | Với W3C XML Schema, đây là đối tượng đặc biệt dùng các gợi ý vị trí schema trong tài liệu; khác với biên dịch hợp đồng được chỉ định |
| `new StreamSource(text)` nhận nội dung XSD | Chuỗi ở constructor này là URI/system identifier; nội dung văn bản cần `Reader` |
| Biên dịch XSD thành công nghĩa là mọi XML sẽ hợp lệ | Vẫn phải kiểm tra từng XML bằng validator từ schema đó |
| Có systemId thì include chắc chắn chạy | Còn phụ thuộc URI, namespace, tài nguyên và chính sách truy cập |
| Đã đặt handler trên factory thì validator tự có cùng handler | Cần thiết lập handler ở đúng giai đoạn |
| Chỉnh cấu hình factory hoặc sửa tệp sẽ cập nhật schema cũ | Tập ràng buộc đã tạo cần được thay bằng một schema biên dịch mới |

Đặc biệt, đừng dùng `newSchema()` không đối số làm phương án dự phòng cho lỗi biên dịch XSD. Nó thay đổi cách lựa chọn schema, không sửa nguồn XSD sai.

## 9. Tự kiểm chứng

Thử từng thay đổi độc lập:

1. Đổi `maxInclusive` trong tệp từ `100` sang `10`, biên dịch lại rồi kiểm tra giá trị `50`: lần kiểm tra phải dùng giới hạn mới sau khi tạo schema mới.
2. Đổi `m:Level` thành `m:Missing`: lỗi phải xuất hiện tại bước biên dịch XSD, không phải chờ dữ liệu XML.
3. Truyền nguyên nội dung XSD vào constructor `StreamSource(String)`: giải thích vì sao đó không phải cách truyền văn bản; sửa bằng `StringReader`.
4. Bổ sung `xs:include` trỏ đến một tệp khác: xác định cả địa chỉ gốc và chính sách phân giải trước khi cho phép phụ thuộc đó.
5. Biên dịch một lần rồi kiểm tra nhiều XML bằng các validator riêng: xác định đối tượng nào dùng chung và đối tượng nào thuộc từng lần xử lý.

Mục tiêu là tách được ba thứ: văn bản XSD làm đầu vào, `Schema` giữ hợp đồng đã biên dịch, và `Validator` áp dụng hợp đồng đó lên từng tài liệu.
