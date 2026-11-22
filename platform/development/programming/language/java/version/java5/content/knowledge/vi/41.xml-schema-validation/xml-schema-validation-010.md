# Kiểm soát external DTD, external schema và xử lý an toàn

## 1. Kiểm tra đúng schema chưa đồng nghĩa xử lý an toàn

Một XML có thể tham chiếu DTD bên ngoài. Một XSD có thể include hoặc import XSD khác. Trong quá trình kiểm tra dữ liệu, bộ xử lý có thể phải đọc các tài nguyên đó nếu chính sách cho phép.

Vì vậy, ngoài câu hỏi “XML có hợp XSD không?”, cần hỏi:

- Ai được chọn schema và những tài nguyên mà schema phụ thuộc?
- Bộ xử lý có được mở mạng hoặc đọc tệp ngoài phạm vi không?
- Có cho phép DOCTYPE và entity không?
- Dữ liệu có bị giới hạn kích thước, mức lồng và chi phí xử lý không?
- Khi cấu hình bảo vệ không được hỗ trợ, hệ thống có tiếp tục chạy không?

Mô hình các giai đoạn:

```text
XSD do ứng dụng lựa chọn
    -> SchemaFactory đọc/biên dịch XSD và các phụ thuộc được phép
    -> Schema

XML đầu vào
    -> parser đọc XML theo chính sách
    -> Validator kiểm tra theo Schema
    -> kết quả hợp lệ hoặc lỗi
```

Cần kiểm soát đúng nơi đọc tài nguyên ở từng giai đoạn. Chỉ đặt một thuộc tính trên Validator không thể sửa lại việc một parser trước đó đã đọc tệp hoặc truy cập mạng.

Bài dùng các cơ chế JAXP hiện hành trên Java 17+, không dựa vào SecurityManager hay cấu hình lỗi thời.

## 2. External DTD và external schema là hai đường truy cập khác nhau

| Đường tham chiếu | Có thể xuất hiện ở đâu? | Thuộc tính kiểm soát tiêu biểu |
| --- | --- | --- |
| DTD bên ngoài, entity ngoài | DOCTYPE/khai báo entity khi parse XML hoặc tài liệu liên quan | ACCESS_EXTERNAL_DTD |
| include/import schema, vị trí schema được xử lý | Khi nạp/biên dịch XSD hoặc trong quá trình validation phù hợp | ACCESS_EXTERNAL_SCHEMA |

Một tệp XML không có external DTD vẫn có thể dẫn tới truy cập schema ngoài nếu pipeline cho phép lấy schema theo tham chiếu. Ngược lại, đã chọn một XSD cục bộ không tự ngăn parser xử lý DOCTYPE của XML đầu vào.

Namespace URI như `http://www.w3.org/2001/XMLSchema` là định danh ngôn ngữ/schema namespace; chỉ việc thấy một URI namespace không có nghĩa phải tải nội dung tại URI ấy. Phải phân biệt namespace name với một systemId/schemaLocation dùng để định vị tài nguyên.

[Hướng dẫn bảo mật JAXP](https://docs.oracle.com/en/java/javase/21/security/java-api-xml-processing-jaxp-security-guide.html) mô tả các cấu trúc có thể tham chiếu tài nguyên ngoài, gồm DTD, entity và schema include/import.

## 3. Giá trị của các thuộc tính external access

Các hằng được định nghĩa trong XMLConstants:

```java
XMLConstants.ACCESS_EXTERNAL_DTD
XMLConstants.ACCESS_EXTERNAL_SCHEMA
```

Giá trị thuộc tính là chuỗi giao thức được phép, không phải một boolean:

| Giá trị | Ý nghĩa |
| --- | --- |
| "" | Không cho truy cập tham chiếu ngoài theo các giao thức |
| "file" | Chỉ cho giao thức file theo hợp đồng thuộc tính |
| "http,https" | Cho những giao thức được liệt kê |
| "all" | Cho mọi giao thức |

Danh sách có quy tắc riêng, gồm trường hợp jar kết hợp giao thức; phải xem hợp đồng thay vì tự so chuỗi theo suy đoán.

### Cho phép file không có nghĩa chỉ cho một thư mục

`"file"` là quyền ở mức giao thức, không phải allowlist đường dẫn. Nó không tự giới hạn vào thư mục schema của ứng dụng.

Tương tự, cho http/https không tự giới hạn hostname, không có nghĩa đã kiểm tra quyền truy cập tới từng URL.

Nếu chỉ cần bộ XSD đã triển khai cùng ứng dụng, chính sách thường dễ kiểm soát là chặn truy cập ngoài mặc định rồi cung cấp những phụ thuộc đã biết qua một cơ chế phân giải có phạm vi rõ.

Không dùng `"all"` để “sửa lỗi không tìm thấy schema” mà bỏ qua lý do nguồn đang yêu cầu một tài nguyên mới.

Hợp đồng giá trị và cách biểu diễn giao thức nằm trong [XMLConstants — external access properties](https://docs.oracle.com/en/java/javase/21/docs/api/java.xml/javax/xml/XMLConstants.html).

## 4. Cấu hình SchemaFactory trước khi đọc XSD

```java
SchemaFactory factory = SchemaFactory.newInstance(
        XMLConstants.W3C_XML_SCHEMA_NS_URI);

factory.setFeature(XMLConstants.FEATURE_SECURE_PROCESSING, true);
factory.setProperty(XMLConstants.ACCESS_EXTERNAL_DTD, "");
factory.setProperty(XMLConstants.ACCESS_EXTERNAL_SCHEMA, "");

Schema schema = factory.newSchema(trustedSchemaSource);
```

Đây là đoạn minh họa cần import, nguồn XSD và xử lý ngoại lệ. Cấu hình phải có hiệu lực trước newSchema, vì chính bước biên dịch schema có thể gặp include/import hoặc tài nguyên ngoài.

Một schema do ứng dụng lựa chọn rõ ràng khác với việc dùng `newSchema()` không tham số rồi để hành vi xác định schema phụ thuộc vào nguồn validation theo hợp đồng API. Nếu không có nhu cầu đó, đừng vô tình mở thêm cách để dữ liệu đầu vào quyết định schema.

XSD cần được quản lý như cấu hình có ảnh hưởng tới việc xử lý dữ liệu. Một tài liệu XSD hợp cú pháp không tự là một nguồn tin cậy về mạng, tệp hay chi phí xử lý.

[SchemaFactory](https://docs.oracle.com/en/java/javase/21/docs/api/java.xml/javax/xml/validation/SchemaFactory.html) là điểm biên dịch schema và cung cấp thuộc tính, feature, resolver cho giai đoạn ấy.

## 5. Cấu hình Validator và parser là hai trách nhiệm

### Validator

Từ Schema đã chuẩn bị:

```java
Validator validator = schema.newValidator();
validator.setFeature(XMLConstants.FEATURE_SECURE_PROCESSING, true);
validator.setProperty(XMLConstants.ACCESS_EXTERNAL_DTD, "");
validator.setProperty(XMLConstants.ACCESS_EXTERNAL_SCHEMA, "");
```

Đây là phần cấu hình minh họa trước validate. Không mặc định một cấu hình đặt trên một đối tượng bất kỳ sẽ tự bao phủ mọi parser, nguồn và provider được lắp vào pipeline.

Nếu reset hoặc lấy lại đối tượng từ pool, xác định lại cấu hình nào được khôi phục và cấu hình nào cần áp dụng trước lần dùng mới.

### Parser

Với DOMSource, XML đã được parse trước khi Validator nhận DOM. Mọi external access xảy ra trong lần parse trước đó đã nằm ngoài khả năng ngăn chặn hồi tố của Validator.

Với SAXSource có XMLReader do ứng dụng tạo, cần cấu hình chính reader đó. Có thể chủ động cấm DOCTYPE nếu hợp đồng dữ liệu không cần DTD.

Với StAXSource, parser StAX cũng có các quy tắc/cờ riêng về DTD và external entity. Không chuyển những tên feature SAX sang StAX rồi giả định hiệu lực giống nhau.

Chọn một pipeline rõ ràng, kiểm thử pipeline ấy với đúng kiểu Source thay vì gắn nhiều cờ không biết đối tượng nào thực sự đọc XML.

[Validator](https://docs.oracle.com/en/java/javase/21/docs/api/java.xml/javax/xml/validation/Validator.html) mô tả các kiểu Source và cơ chế xử lý tương ứng.

## 6. Chặn external access không giống cấm DOCTYPE

Hai chính sách này liên quan nhưng khác nhau:

- Chặn external DTD: không cho bộ xử lý tự lấy DTD/entity ngoài qua giao thức bị cấm.
- Cấm DOCTYPE: từ chối ngay tài liệu có khai báo DOCTYPE theo khả năng parser được cấu hình.

Một DTD nội bộ không cần mạng hay tệp ngoài nhưng vẫn có thể khai báo entity và tạo công việc mở rộng dữ liệu. Vì thế chỉ đặt ACCESS_EXTERNAL_DTD="" không đồng nghĩa mọi xử lý entity nội bộ đã bị vô hiệu hóa.

Nếu định dạng ứng dụng không cần DTD, cấm DOCTYPE là một lựa chọn rõ. Với parser JDK dựa trên Xerces, feature thường dùng là:

```text
http://apache.org/xml/features/disallow-doctype-decl
```

Đây là URI feature của họ parser/provider tương ứng, không phải mọi provider XML trên thế giới đều bắt buộc hỗ trợ. Phải kiểm tra khi cấu hình; nếu chính sách yêu cầu cấm mà provider không thực hiện được, không tiếp tục xử lý như đã được bảo vệ.

Tắt mở rộng entity trong một API DOM riêng cũng không được coi là thay thế phổ quát cho việc chặn truy cập ngoài ở đúng nơi.

## 7. FEATURE_SECURE_PROCESSING là một lớp, không phải toàn bộ chính sách

FEATURE_SECURE_PROCESSING yêu cầu chế độ xử lý có các biện pháp giới hạn an toàn theo JAXP/provider. Nhưng không nên diễn giải nó thành:

- Mọi loại external access ở mọi thành phần đều chắc chắn bị cấm.
- Mọi giới hạn kích thước và độ sâu đã phù hợp với dịch vụ.
- Resolver tùy biến không thể mở mạng.
- Tác vụ có một deadline chạy cứng.
- XML có schema thì không thể gây cạn tài nguyên.

Đặt các external access properties tường minh giúp chính sách cụ thể, dễ kiểm tra hơn là phụ thuộc cấu hình mặc định môi trường.

Với JDK hiện đại, hướng dẫn JAXP còn mô tả các giới hạn xử lý như mở rộng entity, độ sâu phần tử và kích thước/tổng số cấu trúc liên quan. Tên, phạm vi, giá trị mặc định và cơ chế ưu tiên cần được đối chiếu với JDK/provider triển khai, không sao chép một bộ số không biết tác dụng.

Ngoài parser, ứng dụng còn cần giới hạn dung lượng đầu vào, số tác vụ đồng thời, lượng lỗi ghi nhận và ngân sách xử lý theo nhu cầu.

## 8. Resolver là một phần của ranh giới tin cậy

EntityResolver và LSResourceResolver cho phép ứng dụng cung cấp tài nguyên thay cho cơ chế phân giải mặc định.

Điều quan trọng là external access property không tự hạn chế mọi I/O do **mã resolver của ứng dụng** chủ động thực hiện. Nếu resolver tự mở URL rồi trả stream, chính resolver đã thực hiện truy cập.

Tương tự, nếu mã ứng dụng tự mở URL/tệp đầu vào rồi mới truyền stream vào JAXP, các thuộc tính external access không quay lại cấm thao tác I/O đã do ứng dụng thực hiện. Nguồn XML/XSD cấp đầu phải được chọn và đọc theo quyền truy cập riêng của ứng dụng.

Vì vậy:

1. Chỉ nhận diện những namespace/systemId được phép.
2. Ánh xạ sang tài nguyên đã quản lý, chẳng hạn bản XSD đóng gói.
3. Không tải tùy ý từ systemId do XML/XSD cung cấp.
4. Quy định rõ hành vi khi không có ánh xạ.

Trả null thường mang nghĩa để bộ xử lý tiếp tục theo cơ chế phân giải mặc định, không có nghĩa “đã từ chối tài nguyên”. Phải đọc hợp đồng resolver và kết hợp với external access mặc định bị chặn.

Nếu chọn dùng XML Catalog, catalog cũng phải là cấu hình tin cậy với chính sách xử lý trường hợp không khớp rõ ràng. Đừng để một catalog được người ngoài sửa biến thành bộ chuyển tiếp ra mạng.

Việc cho phép một tập phụ thuộc XSD cục bộ là một nhu cầu hợp lệ; mục tiêu là cung cấp đúng tập đó thay vì mở toàn bộ giao thức cho tiện.

## 9. Ví dụ chạy độc lập: XSD cố định, chặn DOCTYPE và include ngoài

Ví dụ gồm:

- Một XSD do chương trình kiểm soát, yêu cầu amount là positiveInteger.
- XML hợp lệ.
- XML sai giá trị.
- XML có DOCTYPE nội bộ vô hại nhưng bị chính sách từ chối.
- Một XSD thử include tài nguyên ngoài, bị external schema policy chặn.

Không dùng dữ liệu thật hoặc tệp nhạy cảm. URI trong phép thử include chỉ phục vụ kiểm tra chính sách, không phải nguồn tài nguyên cần tải.

Lưu thành `SafeSchemaValidationDemo.java`:

```java
import java.io.StringReader;
import javax.xml.XMLConstants;
import javax.xml.parsers.SAXParserFactory;
import javax.xml.transform.sax.SAXSource;
import javax.xml.transform.stream.StreamSource;
import javax.xml.validation.Schema;
import javax.xml.validation.SchemaFactory;
import javax.xml.validation.Validator;
import org.xml.sax.InputSource;
import org.xml.sax.SAXException;
import org.xml.sax.SAXParseException;
import org.xml.sax.XMLReader;
import org.xml.sax.helpers.DefaultHandler;

public class SafeSchemaValidationDemo {
    private static final DefaultHandler STRICT = new DefaultHandler() {
        @Override
        public void error(SAXParseException error) throws SAXException {
            throw error;
        }

        @Override
        public void fatalError(SAXParseException error)
                throws SAXException {
            throw error;
        }
    };

    private static SchemaFactory secureSchemaFactory()
            throws SAXException {
        SchemaFactory factory = SchemaFactory.newInstance(
                XMLConstants.W3C_XML_SCHEMA_NS_URI);

        factory.setFeature(XMLConstants.FEATURE_SECURE_PROCESSING, true);
        factory.setProperty(XMLConstants.ACCESS_EXTERNAL_DTD, "");
        factory.setProperty(XMLConstants.ACCESS_EXTERNAL_SCHEMA, "");
        factory.setErrorHandler(STRICT);
        return factory;
    }

    private static XMLReader secureReader() throws Exception {
        SAXParserFactory factory = SAXParserFactory.newInstance();
        factory.setNamespaceAware(true);
        factory.setXIncludeAware(false);
        factory.setFeature(XMLConstants.FEATURE_SECURE_PROCESSING, true);
        factory.setFeature(
                "http://apache.org/xml/features/disallow-doctype-decl",
                true);

        XMLReader reader = factory.newSAXParser().getXMLReader();
        reader.setProperty(XMLConstants.ACCESS_EXTERNAL_DTD, "");
        reader.setProperty(XMLConstants.ACCESS_EXTERNAL_SCHEMA, "");
        reader.setErrorHandler(STRICT);
        return reader;
    }

    private static boolean isRejected(Schema schema, String xml)
            throws Exception {
        Validator validator = schema.newValidator();
        validator.setFeature(XMLConstants.FEATURE_SECURE_PROCESSING, true);
        validator.setProperty(XMLConstants.ACCESS_EXTERNAL_DTD, "");
        validator.setProperty(XMLConstants.ACCESS_EXTERNAL_SCHEMA, "");
        validator.setErrorHandler(STRICT);

        XMLReader reader = secureReader();

        try (StringReader input = new StringReader(xml)) {
            SAXSource source = new SAXSource(
                    reader, new InputSource(input));
            try {
                validator.validate(source);
                return false;
            } catch (SAXException e) {
                return true;
            }
        }
    }

    public static void main(String[] args) throws Exception {
        String xsd = """
                <xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
                  <xs:element name="invoice">
                    <xs:complexType>
                      <xs:sequence>
                        <xs:element name="amount"
                                    type="xs:positiveInteger"/>
                      </xs:sequence>
                    </xs:complexType>
                  </xs:element>
                </xs:schema>
                """;

        SchemaFactory schemaFactory = secureSchemaFactory();
        Schema schema;
        try (StringReader input = new StringReader(xsd)) {
            schema = schemaFactory.newSchema(new StreamSource(input));
        }

        String valid = "<invoice><amount>10</amount></invoice>";
        String invalid = "<invoice><amount>-2</amount></invoice>";
        String withDoctype = """
                <!DOCTYPE invoice [<!ENTITY value "10">]>
                <invoice><amount>&value;</amount></invoice>
                """;

        System.out.println("Valid XML accepted: "
                + !isRejected(schema, valid));
        System.out.println("Invalid XML rejected: "
                + isRejected(schema, invalid));
        System.out.println("DOCTYPE rejected: "
                + isRejected(schema, withDoctype));

        String externalInclude = """
                <xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
                  <xs:include
                      schemaLocation="https://example.invalid/blocked.xsd"/>
                </xs:schema>
                """;

        SchemaFactory includeFactory = secureSchemaFactory();
        boolean includeRejected = false;

        try (StringReader input = new StringReader(externalInclude)) {
            try {
                includeFactory.newSchema(new StreamSource(input));
            } catch (SAXException e) {
                includeRejected = true;
            }
        }

        System.out.println("External schema include rejected: "
                + includeRejected);
    }
}
```

Chạy trên JDK 17+ có hỗ trợ feature parser đã cấu hình:

```shell
javac SafeSchemaValidationDemo.java
java SafeSchemaValidationDemo
```

Stdout của lần kiểm chứng:

```text
Valid XML accepted: true
Invalid XML rejected: true
DOCTYPE rejected: true
External schema include rejected: true
```

Điểm cần chú ý:

- Mọi cấu hình bắt buộc được thực hiện trước khối catch dùng để phân loại tài liệu bị từ chối. Lỗi không hỗ trợ feature/property không bị nuốt như một XML sai thông thường.
- XSD được compile sau khi SchemaFactory đã bị giới hạn external access.
- Mỗi lần kiểm tra có Validator và XMLReader được cấu hình rõ.
- DOCTYPE mẫu chỉ chứa entity nội bộ nhỏ; nó bị chặn vì chính sách không cho DTD.
- Include dùng HTTPS bị chặn bởi thuộc tính external schema ở giai đoạn newSchema trong môi trường kiểm chứng.
- ErrorHandler ném lại error/fatalError; không chỉ ghi log rồi giả định quá trình kiểm tra thành công.
- Hàm isRejected gộp lỗi xử lý XML/schema thành boolean để thí nghiệm ngắn. Ứng dụng cần phân loại nguyên nhân và giữ thông tin lỗi phù hợp, không dùng boolean đó làm toàn bộ giao thức báo lỗi.

## 10. Không coi mọi lỗi là “XML không hợp lệ”

Các lỗi có ý nghĩa vận hành khác nhau:

| Giai đoạn | Ví dụ | Phản ứng cần phân biệt |
| --- | --- | --- |
| Cấu hình | Provider không hỗ trợ cờ bắt buộc | Dừng khởi tạo/không nhận việc theo chính sách |
| Nạp schema | XSD sai hoặc phụ thuộc bị chặn | Lỗi cấu hình/bộ schema, không đổ cho XML người dùng |
| Parse | XML sai cú pháp hoặc có DOCTYPE bị cấm | Từ chối theo hợp đồng đầu vào |
| Validate | Giá trị/cấu trúc không hợp XSD | Báo lỗi dữ liệu |
| I/O | Nguồn nhập lỗi hoặc bị cắt | Xử lý lỗi đọc riêng |
| Tài nguyên | Vượt dung lượng/giới hạn xử lý | Từ chối/giới hạn tải, quan sát nguyên nhân |

Không catch Exception quanh mọi thứ rồi in “validation failed” và tiếp tục pipeline như có kết quả tin cậy.

Một ErrorHandler chỉ thu thập lỗi nhưng không ném lại có thể làm luồng điều khiển khác với giả định “validate trả bình thường tức là không có lỗi nào”. Nếu thu thập nhiều lỗi, phải giữ cờ/tập kết quả và quyết định thành công theo hợp đồng handler.

Giới hạn số lỗi và kích thước thông báo để một tài liệu sai không tạo log tăng không kiểm soát. Khi trả lỗi ra ngoài, chỉ cung cấp thông tin cần sửa dữ liệu; đường dẫn nội bộ, thông tin mạng hay cấu hình vận hành cần được quản lý theo quyền truy cập.

## 11. Những cấu hình không thay thế cho nhau

| Cách làm | Điều chưa được bảo đảm |
| --- | --- |
| XML có XSD | Không tự ngăn external access hoặc cạn tài nguyên |
| Chỉ set FEATURE_SECURE_PROCESSING | Không tự thể hiện toàn bộ chính sách của mọi thành phần |
| Chỉ chặn external schema | Không tự chặn external DTD |
| Chỉ chặn external DTD | Không tự cấm DTD nội bộ hay mọi include schema |
| Chỉ cấu hình Validator | Không sửa lần parse DOM đã diễn ra trước |
| Đặt file vào danh sách protocol | Không tự giới hạn thư mục/tệp cụ thể |
| Có resolver | Không tự an toàn nếu resolver tải systemId tùy ý |
| Tắt một tính năng rồi bỏ qua ngoại lệ cấu hình | Không chứng minh tính năng đã được tắt |
| Chạy validation trong Future có timeout | Không tự dừng mọi công việc parser/I/O khi hết hạn |

Cấu hình phải đi cùng kiểm thử âm: đầu vào có DTD không được phép, schema có tham chiếu không được phép, dữ liệu vượt giới hạn và nguồn I/O lỗi. Chỉ một XML hợp lệ đi qua chưa chứng minh chính sách chặn hoạt động.

Dùng đúng provider/JDK trong môi trường triển khai để kiểm chứng, vì feature riêng của provider và cấu hình hệ thống có thể thay đổi hành vi.

## 12. Khi nghiệp vụ thật sự cần DTD hoặc nhiều XSD

Không cần mở mọi tài nguyên ngoài chỉ vì dữ liệu hợp lệ có một phụ thuộc.

Có thể thiết kế:

- Bộ schema được kiểm duyệt và đóng gói cùng ứng dụng.
- Catalog hoặc resolver ánh xạ hữu hạn tới tài nguyên tin cậy.
- Cấm tải mạng trong thời gian xử lý yêu cầu.
- Giới hạn đệ quy/phụ thuộc, dung lượng và phạm vi thư mục.
- Tách việc cập nhật bộ schema khỏi việc nhận XML của người dùng.

Nếu thật sự phải lấy schema qua mạng, cần một quy trình quản lý nguồn, quyền truy cập, kiểm tra nội dung và giới hạn I/O riêng. Không giao quyền chọn URL tùy ý cho một schemaLocation rồi coi đó là yêu cầu tự nhiên của validator.

Mục tiêu là một tập tài nguyên được phép rõ ràng và có vòng đời, không phải một danh sách giao thức mở rộng vô hạn sau mỗi lỗi.

## 13. Tự kiểm tra

**SchemaFactory cần cấu hình trước hay sau newSchema?**  
Trước, vì giai đoạn compile XSD có thể đọc các tham chiếu ngoài.

**ACCESS_EXTERNAL_DTD="" có cấm mọi DOCTYPE không?**  
Không tự đồng nghĩa với cấm DOCTYPE. Cần chính sách parser riêng nếu không cho DTD.

**Cho file có giới hạn vào thư mục schema của ứng dụng không?**  
Không. Đó là quyền ở mức giao thức, không phải allowlist đường dẫn.

**Validator an toàn có sửa được external access đã xảy ra khi tạo DOM không?**  
Không. Parser tạo DOM phải được kiểm soát từ trước.

**Resolver trả null có nghĩa đã từ chối tài nguyên không?**  
Không nên hiểu như vậy; thường nó cho cơ chế mặc định tiếp tục theo hợp đồng resolver.

Xử lý XML Schema an toàn là một pipeline có chính sách nhất quán: nguồn schema do ứng dụng kiểm soát, quyền truy cập ngoài bị giới hạn, parser được cấu hình đúng, resolver có phạm vi và lỗi cấu hình không bị bỏ qua.
