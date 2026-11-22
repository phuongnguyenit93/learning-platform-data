# LSResourceResolver và việc phân giải tài nguyên

## 1. Vấn đề: một XSD có thể cần đọc các XSD khác

Một schema thường được tách thành nhiều tệp. XSD gốc có thể dùng `xs:include` để đưa các khai báo cùng namespace vào, hoặc `xs:import` để tham chiếu schema thuộc namespace khác. Khi biên dịch, bộ xử lý cần biết lấy những tài nguyên phụ đó từ đâu.

`LSResourceResolver` là điểm để ứng dụng **quyết định cách cung cấp tài nguyên mà bộ xử lý XML đang yêu cầu**. Thay vì để bộ xử lý tự mở một URL, ứng dụng có thể trả nội dung đã đóng gói trong JAR, lấy từ một bộ nhớ đệm được kiểm soát hoặc từ chối yêu cầu.

Trong kiểm tra XML Schema bằng Java, nó giúp:

- Chạy ổn định khi không có mạng.
- Giữ phiên bản schema phụ đúng với phiên bản hợp đồng đang dùng.
- Ánh xạ địa chỉ logic sang tài nguyên do ứng dụng sở hữu.
- Ngăn việc tự động đọc tệp hoặc URL ngoài phạm vi cho phép.

Đây là API công khai trong module `java.xml`, thuộc gói `org.w3c.dom.ls`. Bài dùng Java 17+ và không cần truy cập lớp nội bộ của JDK.

## 2. Hợp đồng của resolveResource

Giao diện có phương thức:

```java
LSInput resolveResource(
        String type,
        String namespaceURI,
        String publicId,
        String systemId,
        String baseURI);
```

| Tham số | Ý nghĩa cần hiểu |
| --- | --- |
| `type` | Loại tài nguyên được yêu cầu; với XML Schema là URI `http://www.w3.org/2001/XMLSchema`, không phải tên tệp hoặc MIME type |
| `namespaceURI` | Namespace liên quan đến tài nguyên schema; không đồng nghĩa với địa chỉ tải |
| `publicId` | Định danh công khai nếu có; có thể `null` |
| `systemId` | Tham chiếu URI của tài nguyên, có thể tương đối hoặc tuyệt đối, hoặc `null` |
| `baseURI` | URI gốc của tài nguyên đang chứa tham chiếu; có thể `null` |

`namespaceURI` trả lời tài nguyên thuộc không gian tên nào; `systemId` và `baseURI` giúp xác định tài nguyên cụ thể. Một namespace có thể được triển khai bởi nhiều tệp XSD, nên chỉ dùng namespace làm khóa có thể chọn nhầm tệp.

Đọc [hợp đồng LSResourceResolver](https://docs.oracle.com/en/java/javase/25/docs/api/java.xml/org/w3c/dom/ls/LSResourceResolver.html) khi triển khai cho một bộ xử lý cụ thể.

### Hai kết quả trả về có ý nghĩa rất khác nhau

- Trả một `LSInput`: ứng dụng cung cấp đầu vào thay thế cho tài nguyên.
- Trả `null`: yêu cầu bộ xử lý tiếp tục cơ chế phân giải thông thường.

**`null` không có nghĩa là từ chối truy cập.** Nếu cơ chế thông thường được phép mở mạng hoặc tệp, nó vẫn có thể làm như vậy. Khi chính sách yêu cầu chặn tài nguyên ngoài danh sách, bộ phân giải phải báo lỗi phù hợp và cấu hình truy cập ngoài phải được giữ chặt.

Phương thức này không khai báo checked exception. Trong ví dụ, yêu cầu bị cấm gây `SecurityException`, một ngoại lệ thời gian chạy; `SchemaFactory` dừng biên dịch khi bộ phân giải ném ngoại lệ đó.

## 3. LSInput chứa cả nội dung lẫn danh tính tài nguyên

`LSInput` không phải chỉ là đường dẫn tệp. Nó có thể chứa:

- Luồng ký tự qua `setCharacterStream(...)`.
- Luồng byte qua `setByteStream(...)`.
- Nội dung chuỗi qua `setStringData(...)`.
- `systemId`, `baseURI`, `publicId` và thông tin mã hóa khi phù hợp.

Nếu đã cung cấp luồng hoặc nội dung, bộ xử lý có thể đọc trực tiếp dữ liệu đó thay vì tải URI trong `systemId`. Nhưng vẫn nên giữ `systemId` đúng: nó cung cấp danh tính cho chẩn đoán lỗi và làm cơ sở cho những tham chiếu lồng nhau.

Ví dụ, các địa chỉ logic tạo thành cây:

```text
https://schemas.example.invalid/measurement/v1/root.xsd
    └─ parts/types.xsd
         └─ limits.xsd
```

Từ `root.xsd`, tham chiếu `parts/types.xsd` phải trở thành:

```text
https://schemas.example.invalid/measurement/v1/parts/types.xsd
```

Khi đọc `types.xsd`, tham chiếu `limits.xsd` phải được tính theo **địa chỉ của types.xsd**, dẫn đến:

```text
https://schemas.example.invalid/measurement/v1/parts/limits.xsd
```

Nếu trả nội dung `types.xsd` nhưng bỏ `systemId`, phụ thuộc lồng có thể được phân giải sai chỗ hoặc không có đủ địa chỉ gốc để giải quyết.

Trong Java, có thể tạo một `LSInput` bằng API chuẩn `DOMImplementationLS.createLSInput()`. Không cần dùng các lớp triển khai như `DOMInputImpl` thuộc gói nội bộ của JDK. Xem [LSInput](https://docs.oracle.com/en/java/javase/25/docs/api/java.xml/org/w3c/dom/ls/LSInput.html).

## 4. Ví dụ hoàn chỉnh: chỉ cho phép hai schema phụ trong bộ nhớ

Ví dụ có ba XSD được lưu dưới dạng chuỗi:

- Schema gốc định nghĩa `measurement` và cần `parts/types.xsd`.
- `types.xsd` định nghĩa cấu trúc có phần tử `value` và cần `limits.xsd`.
- `limits.xsd` định nghĩa số nguyên trong khoảng `0..100`.

Các URI `example.invalid` chỉ là địa chỉ logic để giải quyết tham chiếu. Nội dung thực tế nằm trong `Map<URI, String>` của chương trình; bộ phân giải không mở kết nối mạng.

Lưu thành `ResourceResolverDemo.java`:

```java
import java.io.StringReader;
import java.net.URI;
import java.util.Map;
import javax.xml.XMLConstants;
import javax.xml.transform.stream.StreamSource;
import javax.xml.validation.Schema;
import javax.xml.validation.SchemaFactory;
import javax.xml.validation.Validator;
import org.w3c.dom.bootstrap.DOMImplementationRegistry;
import org.w3c.dom.ls.DOMImplementationLS;
import org.w3c.dom.ls.LSInput;
import org.w3c.dom.ls.LSResourceResolver;
import org.xml.sax.SAXException;
import org.xml.sax.SAXParseException;
import org.xml.sax.helpers.DefaultHandler;

public class ResourceResolverDemo {
    private static final String NS = "urn:example:measurement:v1";
    private static final URI ROOT = URI.create(
            "https://schemas.example.invalid/measurement/v1/root.xsd");

    private static final String ROOT_XSD = """
            <xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"
                       xmlns:m="urn:example:measurement:v1"
                       targetNamespace="urn:example:measurement:v1">
              <xs:include schemaLocation="parts/types.xsd"/>
              <xs:element name="measurement" type="m:MeasurementType"/>
            </xs:schema>
            """;

    private static final String TYPES_XSD = """
            <xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"
                       xmlns:m="urn:example:measurement:v1"
                       targetNamespace="urn:example:measurement:v1"
                       elementFormDefault="qualified">
              <xs:include schemaLocation="limits.xsd"/>
              <xs:complexType name="MeasurementType">
                <xs:sequence>
                  <xs:element name="value" type="m:Reading"/>
                </xs:sequence>
              </xs:complexType>
            </xs:schema>
            """;

    private static final String LIMITS_XSD = """
            <xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"
                       targetNamespace="urn:example:measurement:v1">
              <xs:simpleType name="Reading">
                <xs:restriction base="xs:integer">
                  <xs:minInclusive value="0"/>
                  <xs:maxInclusive value="100"/>
                </xs:restriction>
              </xs:simpleType>
            </xs:schema>
            """;

    private static final Map<URI, String> ALLOWED = Map.of(
            ROOT.resolve("parts/types.xsd"), TYPES_XSD,
            ROOT.resolve("parts/limits.xsd"), LIMITS_XSD);

    private static final DefaultHandler STOP_ON_ERROR = new DefaultHandler() {
        @Override
        public void error(SAXParseException ex) throws SAXException {
            throw ex;
        }

        @Override
        public void fatalError(SAXParseException ex) throws SAXException {
            throw ex;
        }
    };

    private static LSResourceResolver resolver() throws Exception {
        var registry = DOMImplementationRegistry.newInstance();
        var implementation = registry.getDOMImplementation("LS");
        if (!(implementation instanceof DOMImplementationLS ls)) {
            throw new IllegalStateException("DOM Load and Save is unavailable");
        }

        return (type, namespaceURI, publicId, systemId, baseURI) -> {
            if (!XMLConstants.W3C_XML_SCHEMA_NS_URI.equals(type)
                    || systemId == null || baseURI == null) {
                throw new SecurityException("Unsupported resource request");
            }
            if (namespaceURI != null && !NS.equals(namespaceURI)) {
                throw new SecurityException("Namespace is not allowed");
            }

            URI requested = URI.create(baseURI).resolve(systemId).normalize();
            String content = ALLOWED.get(requested);
            if (content == null) {
                throw new SecurityException("Schema resource is not allowed");
            }

            LSInput input = ls.createLSInput();
            input.setPublicId(publicId);
            input.setSystemId(requested.toString());
            input.setBaseURI(requested.toString());
            input.setCharacterStream(new StringReader(content));
            return input;
        };
    }

    private static Schema compile(String rootText) throws Exception {
        SchemaFactory factory = SchemaFactory.newDefaultInstance();
        factory.setFeature(XMLConstants.FEATURE_SECURE_PROCESSING, true);
        factory.setProperty(XMLConstants.ACCESS_EXTERNAL_DTD, "");
        factory.setProperty(XMLConstants.ACCESS_EXTERNAL_SCHEMA, "");
        factory.setErrorHandler(STOP_ON_ERROR);
        factory.setResourceResolver(resolver());

        StreamSource root = new StreamSource(
                new StringReader(rootText), ROOT.toString());
        return factory.newSchema(root);
    }

    private static void check(Schema schema, String label, String xml)
            throws Exception {
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
        Schema schema = compile(ROOT_XSD);
        check(schema, "good",
                "<measurement xmlns=\"urn:example:measurement:v1\">"
                + "<value>25</value></measurement>");
        check(schema, "too-large",
                "<measurement xmlns=\"urn:example:measurement:v1\">"
                + "<value>101</value></measurement>");

        String forbidden = ROOT_XSD.replace("parts/types.xsd",
                "https://untrusted.example.invalid/other.xsd");
        try {
            compile(forbidden);
            throw new IllegalStateException("Unexpected resource acceptance");
        } catch (SecurityException ex) {
            System.out.println("unknown-resource=REJECTED");
        }
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 ResourceResolverDemo.java
java ResourceResolverDemo
```

Stdout:

```text
good=VALID
too-large=INVALID
unknown-resource=REJECTED
```

`good` hợp lệ vì giá trị `25` thuộc khoảng cho phép. `too-large` không hợp lệ vì `101` vượt giới hạn được khai báo trong schema phụ lồng sâu hơn. Điều này chứng minh rằng việc cung cấp các schema phụ vẫn giữ nguyên kiểm tra kiểu và ràng buộc của XSD.

Lần cuối thay tham chiếu từ `parts/types.xsd` thành một URI không thuộc bản đồ. Bộ phân giải từ chối nó ngay trong quá trình biên dịch schema. Nó không trả `null`, không trả schema rỗng và không tự tải tài nguyên thay thế.

Các nhãn stdout là nhãn do ví dụ tự đặt; chương trình không phụ thuộc thông báo lỗi chi tiết của một phiên bản JDK. Phần kiểm tra dữ liệu chỉ dùng hai XML cố định để làm rõ kết quả.

## 5. Đọc cơ chế của ví dụ theo đúng thứ tự

### 5.1. Ứng dụng tự cung cấp schema gốc

`compile(...)` truyền một `StreamSource` chứa `ROOT_XSD` vào `newSchema(...)`, kèm `ROOT` làm `systemId`. Bộ phân giải tài nguyên không phải là nơi tự chọn schema gốc cho ứng dụng.

Đặt địa chỉ logic cho nguồn gốc cũng không tự làm nó được tải từ mạng: dữ liệu gốc đã được cung cấp qua `StringReader`.

### 5.2. Gắn bộ phân giải trước khi biên dịch

Lời gọi:

```java
factory.setResourceResolver(resolver());
```

phải được thực hiện trước `factory.newSchema(root)` nếu các phụ thuộc cần được giải quyết trong quá trình biên dịch. Gắn bộ phân giải sau khi lần biên dịch đã thất bại không thể sửa ngược lần gọi cũ.

### 5.3. Tính URI cụ thể rồi đối chiếu danh sách cho phép

Mã dùng:

```java
URI requested = URI.create(baseURI).resolve(systemId).normalize();
String content = ALLOWED.get(requested);
```

`resolve` kết hợp địa chỉ gốc và tham chiếu; `normalize` chuẩn hóa các đoạn đường dẫn ở mức URI. Quyết định cho phép dựa trên đối chiếu **URI đầy đủ** trong bản đồ cố định.

Đừng coi `normalize()` là một cơ chế bảo mật hoàn chỉnh. Nó không kiểm tra quyền truy cập tệp, liên kết tượng trưng, chuyển hướng HTTP hoặc địa chỉ IP đích. Ví dụ không mở URL từ URI và không ghép đường dẫn trên đĩa; nó chỉ lấy chuỗi có sẵn từ bản đồ.

Đoạn mã yêu cầu có `systemId` và `baseURI` để giải quyết đúng đồ thị phụ thuộc cố định của bài. Đây là chính sách của ví dụ, không phải yêu cầu mọi bộ phân giải tổng quát phải từ chối mọi trường hợp tham số `null`. Nếu cần xử lý schema chỉ có gợi ý namespace, phải định nghĩa một ánh xạ rõ ràng cho trường hợp đó.

### 5.4. Giữ địa chỉ đúng cho phụ thuộc lồng

`LSInput` được gán `systemId` tuyệt đối của tài nguyên đã chọn, cùng một `StringReader` mới cho nội dung đó. Khi schema phụ chứa `limits.xsd`, bộ xử lý có đủ ngữ cảnh để yêu cầu tài nguyên tiếp theo ở thư mục `parts`.

Không dùng lại cùng một `Reader` đã đọc hết cho mọi lần callback. Có thể lưu nội dung bất biến hoặc byte trong bộ nhớ, nhưng mỗi yêu cầu cần một nguồn đọc mới.

### 5.5. Bộ phân giải và bộ biên dịch làm hai việc khác nhau

Bộ phân giải chọn **nguồn dữ liệu nào được cung cấp**. Bộ biên dịch schema vẫn kiểm tra nội dung XSD, tên kiểu, namespace và các quan hệ khai báo.

Ví dụ chỉ cho phép namespace `NS` khi thông tin namespace được cung cấp. Điều này không tự chứng minh nội dung một tệp có `targetNamespace` đúng; XSD vẫn phải được biên dịch và kiểm tra theo ngữ nghĩa của `include`/`import`.

## 6. Tài nguyên được phân giải ở giai đoạn nào?

| Nơi đặt bộ phân giải | Giai đoạn liên quan |
| --- | --- |
| `SchemaFactory.setResourceResolver(...)` | Giải quyết tài nguyên trong khi tạo `Schema`, chẳng hạn schema được include/import |
| `Validator.setResourceResolver(...)` | Giải quyết tài nguyên mà một lần validation có thể cần |

Không giả định bộ phân giải đặt trên factory tự được kế thừa sang mọi validator. [SchemaFactory.setResourceResolver](https://docs.oracle.com/en/java/javase/25/docs/api/java.xml/javax/xml/validation/SchemaFactory.html#setResourceResolver(org.w3c.dom.ls.LSResourceResolver)) quy định phạm vi của thiết lập này; [Validator](https://docs.oracle.com/en/java/javase/25/docs/api/java.xml/javax/xml/validation/Validator.html) có thiết lập riêng.

Trong ví dụ, toàn bộ hợp đồng đã được cung cấp lúc biên dịch. Mỗi validator dùng schema đó và tiếp tục chặn việc tự đọc tài nguyên ngoài; không cần tải thêm schema để xử lý hai XML mẫu.

Cũng cần phân biệt các giao diện phân giải theo công việc:

| Giao diện | Vai trò thường gặp |
| --- | --- |
| `LSResourceResolver` | Tài nguyên XML/schema trong các API liên quan, như biên dịch và kiểm tra XSD |
| SAX `EntityResolver` | Phân giải thực thể/DTD trong luồng đọc SAX và các bộ đọc dùng SAX |
| `URIResolver` | Tài nguyên URI trong xử lý biến đổi XSLT |

Việc cài một resolver cho schema không có nghĩa mọi bộ đọc XML hoặc bộ biến đổi khác trong ứng dụng tự sử dụng nó.

## 7. Kết hợp resolver với chính sách truy cập ngoài

Chương trình đặt:

```java
factory.setProperty(XMLConstants.ACCESS_EXTERNAL_DTD, "");
factory.setProperty(XMLConstants.ACCESS_EXTERNAL_SCHEMA, "");
```

Những thiết lập này chặn việc bộ xử lý tự truy cập các tài nguyên ngoài qua giao thức khi phân giải mặc định. Với tài nguyên được cho phép, bộ phân giải đã cung cấp luồng nội dung trực tiếp, nên không cần cho phép tải qua HTTP chỉ vì địa chỉ logic bắt đầu bằng `https`.

Điều đó không có nghĩa resolver là ngoại lệ an toàn tự động. Nếu sửa resolver thành `new URL(systemId).openStream()` mà không kiểm tra nguồn, mã ứng dụng có thể tự mở tài nguyên không mong muốn. Thuộc tính của bộ xử lý không tự kiểm soát mọi hành vi I/O do mã resolver tùy chỉnh thực hiện.

Các nguyên tắc áp dụng:

- Chọn schema gốc theo cấu hình đáng tin cậy của ứng dụng.
- Cho phép một tập tài nguyên phụ xác định rõ; không chỉ kiểm tra đuôi `.xsd` hoặc chuỗi bắt đầu bằng một tên miền.
- Từ chối tài nguyên không khớp thay vì cho phân giải dự phòng ngoài ý muốn.
- Kiểm soát toàn bộ phụ thuộc, kể cả schema phụ tiếp tục include/import các nguồn khác.
- Áp dụng giới hạn kích thước và xử lý tài nguyên phù hợp với hệ thống thực tế.

Ví dụ chỉ chứa XSD và XML cố định, không dùng DTD. Nếu tiếp nhận tài liệu bên ngoài, phải cấu hình cả bộ đọc XML và chính sách DTD/tài nguyên của luồng xử lý đó; một resolver cho XSD không thay mọi lớp bảo vệ. Xem [JAXP Security Guide](https://docs.oracle.com/en/java/javase/25/security/java-api-xml-processing-jaxp-security-guide.html).

## 8. Vòng đời tài nguyên và lựa chọn triển khai

### Tạo đầu vào mới cho mỗi lần yêu cầu

Ví dụ dùng `StringReader`, nên không giữ tệp hay kết nối đang mở. Nếu dùng luồng tệp/mạng thật, phải xác định rõ vòng đời và cách giải phóng chúng theo bộ xử lý đang dùng. Không đóng luồng trước khi trả `LSInput`, vì lúc đó bộ xử lý còn chưa đọc nội dung.

Nếu chia sẻ một resolver cho nhiều lần biên dịch/validation, dữ liệu ánh xạ và các thành phần bên trong phải đáp ứng cách dùng đồng thời thực tế. Không đặt một luồng đọc đang thay đổi trong một trường toàn cục rồi trả nó cho mọi yêu cầu.

### Dùng XML Catalog khi ánh xạ đã thành một hợp đồng tài nguyên

Khi số lượng ánh xạ lớn hoặc cần dùng cùng quy tắc cho nhiều API XML, Java có XML Catalog. `CatalogResolver` triển khai cả `LSResourceResolver` cùng một số giao diện phân giải khác; nó có thể thay bảng ánh xạ tự viết bằng cấu hình catalog.

Dù dùng catalog hay mã Java, vẫn phải xác định hành vi khi không có mục khớp và kiểm tra việc từ chối tài nguyên ngoài phạm vi. Catalog không tự làm mọi nguồn mà nó trỏ đến trở thành đáng tin cậy. Xem [CatalogResolver](https://docs.oracle.com/en/java/javase/25/docs/api/java.xml/javax/xml/catalog/CatalogResolver.html).

## 9. Lỗi thường gặp và cách kiểm chứng

| Hiện tượng | Điểm cần kiểm tra |
| --- | --- |
| XSD đầu tiên đọc được nhưng include lồng thất bại | `systemId` của `LSInput` đã trỏ đúng tài nguyên đang trả hay chưa |
| Chạy được tại máy này, lỗi tại máy khác | Mã có phụ thuộc thư mục làm việc hoặc mạng mặc định hay không |
| Tài nguyên không có trong bảng vẫn được tải | Nhánh không khớp có trả `null` và cho phép phân giải dự phòng hay không |
| Một namespace nhiều XSD nhưng chọn nhầm tệp | Có dùng namespace đơn lẻ thay cho định danh tài nguyên cụ thể hay không |
| Lần đầu chạy được, lần sau báo nguồn rỗng | Có tái sử dụng `Reader`/`InputStream` đã đọc hết hay không |
| Đã chặn truy cập ngoài nhưng mã vẫn tải URL | Resolver tùy chỉnh có tự mở URL ngoài chính sách hay không |

Có thể kiểm chứng ví dụ bằng các thay đổi độc lập:

1. Bỏ mục `parts/limits.xsd` khỏi `ALLOWED`: biên dịch phải bị từ chối dù `parts/types.xsd` vẫn được phép.
2. Bỏ `setSystemId(...)` và `setBaseURI(...)` trên `LSInput`: quan sát việc mất ngữ cảnh cho phụ thuộc lồng; không dựa vào một kiểu lỗi cụ thể trên mọi bộ xử lý.
3. Giữ danh sách tài nguyên nhưng sửa nội dung `LIMITS_XSD` thành XSD sai: bộ phân giải có thể cung cấp tài nguyên thành công, nhưng biên dịch vẫn phải thất bại.
4. Đổi giá trị XML từ `101` sang `100`: hợp đồng đã biên dịch phải chấp nhận giới hạn trên.

Mục tiêu là giải thích được vì sao **chọn đúng tài nguyên**, **cho phép truy cập tài nguyên** và **kiểm tra tính đúng đắn của schema** là ba trách nhiệm liên quan nhưng không thể thay thế cho nhau.
