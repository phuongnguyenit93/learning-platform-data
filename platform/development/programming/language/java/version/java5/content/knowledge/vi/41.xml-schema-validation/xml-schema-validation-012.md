# Thiết kế kiểm thử cho XML hợp lệ, sai cấu trúc và có tài nguyên ngoài

## 1. Kiểm thử đúng hợp đồng, không chỉ kiểm tra có ngoại lệ

Một bộ kiểm tra XML Schema thường có nhiều tầng:

```text
Nguồn XML
    ↓
Bộ phân tích: XML có đúng cú pháp không?
    ↓
Bộ kiểm tra XSD: cấu trúc và kiểu có phù hợp không?
    ↓
Kiểm tra nghiệp vụ và sử dụng dữ liệu
```

Ngoài ra còn có quá trình chuẩn bị XSD, nơi include/import có thể cần phân giải tài nguyên khác.

Vì thế, một ca kiểm thử chỉ khẳng định “có lỗi” chưa đủ rõ. Nó cần xác định:

- Đầu vào đang thử ràng buộc nào?
- Kết quả mong đợi là chấp nhận, từ chối hay chặn một nguồn?
- Lỗi nên thuộc tầng nào?
- Có được phép truy cập tài nguyên ngoài không?
- Nếu bị từ chối, có dữ liệu hoặc tác dụng phụ nào đã được ghi nhận không?

Mục tiêu là có bằng chứng cho từng phần của hợp đồng. Bài dùng các API JAXP vẫn phù hợp trong Java hiện đại, với một chương trình kiểm chứng chạy trên JDK 17 trở lên.

## 2. Bắt đầu bằng một lược đồ và dữ liệu hợp lệ nhỏ

Không nên mở đầu bằng một tệp XML lớn từ sản xuất rồi sửa ngẫu nhiên. Hãy tạo một mẫu tối thiểu mà người đọc có thể giải thích vì sao nó hợp lệ.

Ví dụ hợp đồng order:

- Có thuộc tính id bắt buộc, thuộc kiểu xs:ID.
- Có sku, sau đó đến qty theo đúng thứ tự.
- Qty là xs:positiveInteger.

Một đầu vào tối thiểu hợp lệ:

```xml
<order id="o1">
  <sku>A</sku>
  <qty>1</qty>
</order>
```

Ca chấp nhận là đối chứng quan trọng. Nếu mọi ca đều bị từ chối, có thể bộ kiểm tra đang hỏng cấu hình, không mở được schema hoặc luôn báo lỗi; điều đó chưa chứng minh nó phân biệt đúng dữ liệu.

Các giá trị biên phải đến từ lược đồ thật. xs:string không tự có nghĩa “không được rỗng”; nếu muốn từ chối sku rỗng, XSD phải có ràng buộc tương ứng. Không viết expected theo suy đoán nghiệp vụ chưa được thể hiện trong hợp đồng kiểm thử.

## 3. Mỗi ca sai nên thay đổi một điều chính

Từ mẫu hợp lệ, tạo từng biến thể nhỏ:

| Ca | Thay đổi chính | Điều cần kiểm chứng |
| --- | --- | --- |
| Thiếu qty | Bỏ phần tử bắt buộc | Ràng buộc số lượng/cấu trúc |
| Đảo thứ tự | Đưa qty trước sku | xs:sequence thực sự được áp dụng |
| Sai kiểu | Qty là many | Chuyển đổi kiểu XSD không được chấp nhận |
| Giá trị biên sai | Qty bằng 0 | positiveInteger khác nonNegativeInteger |
| Thiếu id | Bỏ thuộc tính bắt buộc | use=required được áp dụng |
| XML chưa đóng | Thiếu thẻ kết thúc order | Parser từ chối XML sai cú pháp |
| Namespace sai | URI phần tử không đúng với schema có namespace | Không chỉ so tên cục bộ |

Ca namespace chỉ cần khi lược đồ thuộc phạm vi đó. Không buộc một schema không có target namespace phải có quy tắc của schema có namespace.

Tránh một mẫu vừa thiếu thuộc tính, vừa đảo thứ tự, vừa sai kiểu nếu mục tiêu là kiểm tra một ràng buộc cụ thể. Nó có thể bị từ chối vì lỗi đầu tiên mà chưa chạm tới điều bạn muốn kiểm chứng.

Cũng không gắn expected vào toàn bộ thông báo lỗi nội bộ. Thông báo có thể khác theo phiên bản hoặc triển khai. Ưu tiên loại kết quả, giai đoạn xử lý và thông tin vị trí cần thiết; chỉ kiểm tra mã chẩn đoán cụ thể nếu API ứng dụng đã cam kết nó.

## 4. Tài nguyên ngoài cần chính sách kiểm thử riêng

“Tài nguyên ngoài” có thể xuất hiện ở những nơi khác nhau:

| Nơi tham chiếu | Thành phần liên quan | Ví dụ |
| --- | --- | --- |
| XML khai báo DTD/entity | Parser XML | External entity |
| XSD include/import | SchemaFactory và bộ phân giải lược đồ | Một XSD phụ thuộc XSD khác |
| Gợi ý schema trong XML | Cách tạo Schema/Validator và chính sách phân giải | schemaLocation |
| Cơ chế ghép nội dung | Cấu hình parser | XInclude |

Không gộp mọi tình huống thành một test XXE rồi mặc định toàn bộ quá trình đã được bao phủ.

Trước khi viết test, chốt chính sách:

- Cấm hoàn toàn DOCTYPE hay cho phép DTD theo danh sách?
- XSD phụ thuộc được nạp từ kho đã biết hay có thể ra mạng?
- Một URI không nằm trong danh sách được phép phải bị chặn hay được bỏ qua?
- Các gợi ý schema trong tài liệu có được dùng để chọn ràng buộc không?

Trong ví dụ, chính sách là: XML không được có DOCTYPE; schema phụ thuộc chỉ được lấy từ đúng URI trong bộ nhớ. Không có lời gọi mạng hoặc đọc tệp bí mật để chạy thử.

## 5. Quan sát việc phân giải, không dùng sự cố mạng làm expected

Một test yếu có thể đưa vào URL không tồn tại, rồi coi lỗi kết nối là bằng chứng hệ thống đã chặn nguồn ngoài.

Nhưng thất bại vì DNS, tường lửa hoặc tệp không tồn tại không giống thất bại do chính sách của ứng dụng. Ngày mai môi trường khác có thể làm cùng test thay đổi hành vi.

Nên dùng các điểm quan sát do ứng dụng kiểm soát:

- EntityResolver có bộ đếm và từ chối nếu bị gọi ngoài ý định.
- LSResourceResolver trả nội dung từ một kho trong bộ nhớ cho URI được phép.
- URI không được phép ném một lỗi đánh dấu riêng.
- Nếu cần kiểm tra truy cập thực tế ở ranh giới hệ thống, dùng tài nguyên giả cục bộ được kiểm soát và xác minh số lượt truy cập, không dùng dịch vụ bên ngoài bất định.

Nếu chính sách là cấm DOCTYPE từ đầu, expected hợp lý là parser từ chối trước khi resolver entity được gọi. Không cần thật sự tạo tệp nằm sau một URI chỉ để chứng minh không được đọc.

Với LSResourceResolver, trả null có thể yêu cầu bộ xử lý tiếp tục cách phân giải mặc định. Vì vậy “không biết URI thì return null” không tự có nghĩa “cấm URI”. Một bộ phân giải theo danh sách phải thực thi rõ đường từ chối.

## 6. Chương trình kiểm chứng chạy được

Chương trình sau có:

- Một XSD gốc include một XSD được cung cấp trong bộ nhớ.
- Một resolver chỉ cho phép URI đã định.
- Parser từ chối DOCTYPE.
- Validator kiểm tra cấu trúc và kiểu.
- Các kiểm tra tường minh bằng AssertionError, không cần bật -ea.

Lưu thành `XmlValidationTestDemo.java`:

```java
import java.io.StringReader;
import javax.xml.XMLConstants;
import javax.xml.parsers.DocumentBuilder;
import javax.xml.parsers.DocumentBuilderFactory;
import javax.xml.transform.dom.DOMSource;
import javax.xml.transform.stream.StreamSource;
import javax.xml.validation.Schema;
import javax.xml.validation.SchemaFactory;
import javax.xml.validation.Validator;
import org.w3c.dom.Document;
import org.w3c.dom.bootstrap.DOMImplementationRegistry;
import org.w3c.dom.ls.DOMImplementationLS;
import org.w3c.dom.ls.LSInput;
import org.xml.sax.InputSource;
import org.xml.sax.SAXException;
import org.xml.sax.SAXParseException;
import org.xml.sax.helpers.DefaultHandler;

public class XmlValidationTestDemo {
    private static final String TYPES = """
            <xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
              <xs:complexType name="OrderType">
                <xs:sequence>
                  <xs:element name="sku" type="xs:string"/>
                  <xs:element name="qty" type="xs:positiveInteger"/>
                </xs:sequence>
                <xs:attribute name="id" type="xs:ID" use="required"/>
              </xs:complexType>
            </xs:schema>
            """;

    static final class BlockedResource extends RuntimeException {
        BlockedResource(String systemId) {
            super("Blocked resource: " + systemId);
        }
    }

    static final class FailFast extends DefaultHandler {
        @Override
        public void error(SAXParseException e) throws SAXException {
            throw e;
        }

        @Override
        public void fatalError(SAXParseException e) throws SAXException {
            throw e;
        }
    }

    private static void check(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    private static Schema compile(String include, int[] allowedLoads)
            throws Exception {
        SchemaFactory factory =
                SchemaFactory.newInstance(XMLConstants.W3C_XML_SCHEMA_NS_URI);
        factory.setFeature(XMLConstants.FEATURE_SECURE_PROCESSING, true);
        factory.setProperty(XMLConstants.ACCESS_EXTERNAL_DTD, "");
        factory.setProperty(XMLConstants.ACCESS_EXTERNAL_SCHEMA, "");
        factory.setErrorHandler(new FailFast());

        DOMImplementationLS dom = (DOMImplementationLS)
                DOMImplementationRegistry.newInstance()
                        .getDOMImplementation("LS 3.0");
        check(dom != null, "DOM LS implementation is required");

        factory.setResourceResolver(
                (type, namespaceURI, publicId, systemId, baseURI) -> {
                    if (!"memory:/types.xsd".equals(systemId)) {
                        throw new BlockedResource(systemId);
                    }
                    allowedLoads[0]++;
                    LSInput input = dom.createLSInput();
                    input.setSystemId(systemId);
                    input.setStringData(TYPES);
                    return input;
                });

        String root = """
                <xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
                  <xs:include schemaLocation="%s"/>
                  <xs:element name="order" type="OrderType"/>
                </xs:schema>
                """.formatted(include);

        try (StringReader reader = new StringReader(root)) {
            StreamSource source = new StreamSource(reader);
            source.setSystemId("memory:/root.xsd");
            return factory.newSchema(source);
        }
    }

    private static void validate(
            Schema schema, String xml, int[] entityCalls) throws Exception {
        DocumentBuilderFactory factory =
                DocumentBuilderFactory.newDefaultInstance();
        factory.setNamespaceAware(true);
        factory.setXIncludeAware(false);
        factory.setExpandEntityReferences(false);
        factory.setFeature(XMLConstants.FEATURE_SECURE_PROCESSING, true);
        factory.setFeature(
                "http://apache.org/xml/features/disallow-doctype-decl", true);
        factory.setAttribute(XMLConstants.ACCESS_EXTERNAL_DTD, "");
        factory.setAttribute(XMLConstants.ACCESS_EXTERNAL_SCHEMA, "");

        DocumentBuilder builder = factory.newDocumentBuilder();
        builder.setErrorHandler(new FailFast());
        builder.setEntityResolver((publicId, systemId) -> {
            entityCalls[0]++;
            throw new SAXException("Unexpected entity resolution");
        });

        Document document;
        try (StringReader reader = new StringReader(xml)) {
            document = builder.parse(new InputSource(reader));
        }

        Validator validator = schema.newValidator();
        validator.setProperty(XMLConstants.ACCESS_EXTERNAL_DTD, "");
        validator.setProperty(XMLConstants.ACCESS_EXTERNAL_SCHEMA, "");
        validator.setErrorHandler(new FailFast());
        validator.validate(new DOMSource(document));
    }

    private static void reject(
            Schema schema, String label, String xml, int[] entityCalls)
            throws Exception {
        try {
            validate(schema, xml, entityCalls);
            throw new AssertionError(label + " was accepted");
        } catch (SAXException e) {
            System.out.println(label + "=REJECTED");
        }
    }

    public static void main(String[] args) throws Exception {
        int[] allowedLoads = {0};
        Schema schema = compile("memory:/types.xsd", allowedLoads);
        check(allowedLoads[0] == 1, "Allowed schema was not resolved once");
        System.out.println("allowedSchemaLoads=" + allowedLoads[0]);

        int[] entityCalls = {0};
        validate(schema,
                "<order id=\"o1\"><sku>A</sku><qty>1</qty></order>",
                entityCalls);
        System.out.println("valid=PASS");

        reject(schema, "missingQty",
                "<order id=\"o1\"><sku>A</sku></order>", entityCalls);
        reject(schema, "wrongOrder",
                "<order id=\"o1\"><qty>1</qty><sku>A</sku></order>",
                entityCalls);
        reject(schema, "wrongType",
                "<order id=\"o1\"><sku>A</sku><qty>many</qty></order>",
                entityCalls);
        reject(schema, "zeroQty",
                "<order id=\"o1\"><sku>A</sku><qty>0</qty></order>",
                entityCalls);
        reject(schema, "missingId",
                "<order><sku>A</sku><qty>1</qty></order>", entityCalls);
        reject(schema, "malformed",
                "<order id=\"o1\"><sku>A</sku><qty>1</qty>",
                entityCalls);

        reject(schema, "externalEntity", """
                <!DOCTYPE order [
                  <!ENTITY probe SYSTEM "file:///not-read/private.txt">
                ]>
                <order id="o1"><sku>&probe;</sku><qty>1</qty></order>
                """, entityCalls);
        check(entityCalls[0] == 0,
                "DOCTYPE should be rejected before entity resolution");
        System.out.println("entityResolverCalls=" + entityCalls[0]);

        try {
            compile("memory:/denied.xsd", new int[1]);
            throw new AssertionError("Unknown schema resource was accepted");
        } catch (BlockedResource e) {
            System.out.println("unknownSchema=BLOCKED");
        }
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```shell
javac --release 17 XmlValidationTestDemo.java
java XmlValidationTestDemo
```

Stdout:

```text
allowedSchemaLoads=1
valid=PASS
missingQty=REJECTED
wrongOrder=REJECTED
wrongType=REJECTED
zeroQty=REJECTED
missingId=REJECTED
malformed=REJECTED
externalEntity=REJECTED
entityResolverCalls=0
unknownSchema=BLOCKED
```

Chương trình không mở URI file trong fixture và không cần URL mạng hoạt động. Các chuỗi memory là định danh được resolver ánh xạ trực tiếp sang nội dung XSD trong bộ nhớ; không phải một giao thức mà chương trình nhờ hệ điều hành mở.

Hai URI include truyền cho compile là dữ liệu fixture do chương trình kiểm soát. Việc tạo XSD mẫu bằng formatted ở đây không phải một khuyến nghị ghép đầu vào không tin cậy vào XSD trong ứng dụng.

## 7. Mỗi kết quả trong chương trình chứng minh điều gì?

### Schema phụ thuộc được phép

allowedSchemaLoads bằng một và tài liệu hợp lệ được chấp nhận chứng minh đường include được giải quyết bằng nội dung đã cung cấp, không phải vì ứng dụng bỏ qua phần phụ thuộc.

Resolver trả LSInput chứa String cho đúng URI. Các giới hạn truy cập ngoài vẫn được đặt, nhưng nội dung được ứng dụng cung cấp qua resolver là một đường được cho phép có chủ ý.

### Các ca sai cấu trúc và kiểu

Mỗi fixture chỉ thay một điều chính từ cấu trúc hợp lệ. Hàm reject đòi SAXException; nếu lời gọi validate trở về bình thường thì test ném AssertionError.

Lỗi cấu hình không bị gom thành REJECTED một cách tùy tiện. Các lỗi tạo parser hoặc thiết lập tính năng theo kiểu ngoại lệ khác vẫn làm chương trình thất bại.

Trong một thư viện có mô hình lỗi công khai chi tiết hơn, có thể kiểm tra riêng giai đoạn parser và validator thay vì chỉ loại SAXException ở ranh giới minh họa.

### XML sai cú pháp

Mẫu thiếu thẻ đóng không thể trở thành Document hợp lệ nên bị parser từ chối trước bước validate DOM. Đây là một lớp lỗi khác với qty bằng 0 trong XML đúng cú pháp.

### External entity

Parser được cấu hình từ chối DOCTYPE, nên fixture bị chặn trước bước phân giải entity. Bộ đếm entityResolverCalls bằng không xác minh điểm này trong đường chạy.

Bộ phân giải entity còn có đường ném lỗi nếu bất ngờ bị gọi, nên ngay cả một cấu hình sai cũng không được phép tự đọc URI thử nghiệm trong chương trình.

### Schema ngoài danh sách

Một URI include lạ tạo lỗi BlockedResource của chính resolver. Expected không dựa vào việc URI đó không truy cập được, mà dựa vào nhánh chính sách đã được thực thi.

Các ca này kiểm tra chính sách cấm DOCTYPE và resolver theo danh sách. Chúng không phải bằng chứng độc lập cho mọi thuộc tính JAXP hoặc mọi giao thức mạng có thể có trong một hệ thống khác.

## 8. Đừng nhầm kiểm thử resolver với kiểm thử giới hạn truy cập mặc định

Trong ví dụ, bộ phân giải lược đồ chủ động trả nội dung hoặc chủ động từ chối. Đây là đường ứng dụng đã can thiệp vào cách nạp tài nguyên.

Nếu mục tiêu riêng là kiểm chứng ACCESS_EXTERNAL_SCHEMA hoặc ACCESS_EXTERNAL_DTD ở đường mặc định, cần thiết kế một ca đi đúng đường đó, với nguồn thử được kiểm soát và không dựa vào lỗi mạng ngẫu nhiên.

Tương tự, một parser đã chặn mọi DOCTYPE sẽ không đi tới resolver entity. Muốn kiểm tra chính sách cho phép một DTD cụ thể trong một cấu hình khác, cần một nhóm ca riêng với đối chứng được phép và không được phép.

Viết rõ phạm vi của mỗi nhóm test giúp tránh kết luận quá mạnh. Một test có số lượt resolver bằng không chỉ có ý nghĩa khi ta biết tại sao nó phải bằng không và đường xử lý trước đó có được chạm tới hay chưa.

## 9. Kiểm thử cấu hình và lỗi chuẩn bị schema

Trước các ca dữ liệu XML, nên có kiểm tra cho bước chuẩn bị ràng buộc:

1. XSD hợp lệ biên dịch thành Schema.
2. XSD sai cú pháp hoặc tham chiếu kiểu không tồn tại bị từ chối.
3. Include/import được phép thực sự được nạp.
4. Include/import không được phép bị chặn theo chính sách.
5. Lỗi thiết lập tính năng không bị bỏ qua rồi tiếp tục với cấu hình yếu hơn yêu cầu.

Một helper bắt Exception rồi trả false có thể che lỗi “không tạo được Schema” thành “XML không hợp lệ”. Hai kết quả không tương đương.

Chọn rõ ranh giới:

```text
Lỗi chuẩn bị lược đồ
    → không bắt đầu kiểm tra dữ liệu theo một schema chưa sẵn sàng

XML không hợp lệ theo schema đã sẵn sàng
    → từ chối bản dữ liệu cụ thể
```

Nếu ứng dụng có cơ chế lưu Schema dùng lại, test còn cần xác định phiên bản schema và thời điểm thay đổi. Một tài liệu được chấp nhận bằng schema cũ không chứng minh nó phù hợp schema mới.

## 10. ErrorHandler và tác dụng phụ cần có ca riêng

Một ErrorHandler chỉ ghi log rồi trở về có thể cho bộ xử lý tiếp tục theo khả năng phục hồi. Khi đó, việc lời gọi parse hoặc validate không ném không đủ để khẳng định không có lỗi.

Bộ test nên kiểm tra đúng chính sách mà ứng dụng chọn:

- Dừng ngay: handler ném lỗi và kết quả không được trả là thành công.
- Thu thập lỗi: trạng thái lỗi được giữ lại và kết quả cuối bị đánh dấu không hợp lệ.
- Cảnh báo: được phân loại riêng theo yêu cầu, không tự gộp mọi cảnh báo thành lỗi hoặc ngược lại.

Nếu dùng ValidatorHandler trong chuỗi SAX, bổ sung ca lỗi xuất hiện muộn. Ví dụ phần đầu đã được handler ứng dụng nhìn thấy nhưng phần cuối có phần tử thừa. Expected phải xác minh dữ liệu chưa được ghi nhận vĩnh viễn hoặc được hủy theo cơ chế đã định.

Không chỉ kiểm tra loại ngoại lệ mà bỏ qua tác dụng phụ. Một tài liệu bị REJECTED sau khi đã ghi một đơn hàng sai vào cơ sở dữ liệu vẫn là một lỗi thiết kế.

## 11. Test phải dùng đúng đường xử lý của ứng dụng

Nếu ứng dụng thực tế validate trực tiếp từ StreamSource nhưng test lại luôn parse DOM bằng một helper an toàn riêng, test có thể chưa đi qua cùng bộ phân tích.

Cần xác định đường chạy thật:

| Đường ứng dụng | Điều test cần giữ tương ứng |
| --- | --- |
| DOM được chuẩn bị trước | Cấu hình parser và bước validate DOM |
| Validator nhận nguồn XML trực tiếp | Cách dựng nguồn và cấu hình của đường validate đó |
| Chuỗi SAX có ValidatorHandler | Việc nối handler, ErrorHandler và dữ liệu tạm |
| Schema theo kho tài nguyên | Resolver và quy tắc URI/base URI |
| XML có namespace | Cấu hình namespace và fixture URI đúng/sai |

Một test đơn vị có thể dùng nguồn trong bộ nhớ để cô lập ràng buộc. Nhưng cần test tích hợp cho cách mở nguồn, charset, systemId và resolver mà ứng dụng thật sử dụng.

Với tham chiếu tương đối, base URI là một phần dữ liệu đầu vào của việc phân giải. Fixture nên chỉ định systemId có chủ ý để không phụ thuộc thư mục làm việc của máy chạy.

## 12. Tính ổn định của bộ kiểm thử

Những thực hành giúp test lặp lại được:

- Giữ XML/XSD fixture nhỏ và rõ nguồn gốc.
- Dùng nguồn trong bộ nhớ cho ca không cần hệ thống tệp.
- Khi cần tệp, tạo tệp tạm do test sở hữu rồi đóng/xóa đúng phạm vi.
- Không cần internet cho các ca kiểm thử thường lệ.
- Dùng kiểm tra tường minh, không chỉ in log rồi để test luôn thành công.
- Không so nguyên thông báo lỗi phụ thuộc triển khai nếu đó không phải hợp đồng cần giữ.
- Không thay thuộc tính toàn cục JVM trong các test chạy song song nếu có thể cấu hình từng đối tượng.
- Tạo Validator riêng cho mỗi lần kiểm tra hoặc quản lý quyền sử dụng độc quyền theo hợp đồng.

Schema có thể được dùng chung theo hợp đồng của nó; Validator không tự trở thành an toàn giữa các luồng chỉ vì được tạo từ một Schema dùng chung.

Khi kiểm tra giới hạn tài nguyên, dùng mẫu có quy mô kiểm soát và thời hạn/bộ nhớ phù hợp môi trường test. Không chạy một tải không giới hạn chỉ để xem JVM có bị cạn tài nguyên hay không.

Ghi nhận phiên bản JDK và triển khai JAXP trong chẩn đoán khi nâng môi trường, nhất là nếu test có dựa vào khả năng cấu hình cụ thể của provider.

## 13. Ma trận tối thiểu để rà soát phạm vi

Một ma trận thực tế nên đánh dấu từng yêu cầu thay vì chỉ đếm số fixture:

| Nhóm | Đối chứng chấp nhận | Ca từ chối | Bằng chứng thêm |
| --- | --- | --- | --- |
| Cấu trúc | XML tối thiểu hợp lệ | Thiếu/thừa/đảo thứ tự | Đúng ràng buộc đang thử |
| Kiểu và miền | Giá trị biên hợp lệ | Sai kiểu, ngoài miền | Không bị nhầm với lỗi parse |
| Cú pháp XML | Cấu trúc đóng/mở đúng | XML không well-formed | Parser từ chối |
| Namespace | URI đúng | URI sai hoặc thiếu theo hợp đồng | Không chỉ so tên cục bộ |
| Nguồn phụ thuộc | Tài nguyên được phép | URI ngoài danh sách | Resolver/hệ thống ghi nhận đúng |
| Tác dụng phụ | Kết quả hợp lệ được ghi nhận | Lỗi muộn không được ghi nhận | Trạng thái đầu ra sau thất bại |

Không phải sản phẩm nào cũng có mọi nhóm. Nhưng nhóm bị bỏ phải do hợp đồng không có nhu cầu đó, không phải vì một ca “XML sai” chung đã bị coi là thay thế tất cả.

## 14. Tự kiểm tra

1. Một URL không tồn tại có chứng minh chính sách truy cập ngoài đã chặn nó không?
2. Vì sao cần một XML hợp lệ làm đối chứng?
3. XML sai cú pháp và XML đúng cú pháp nhưng sai XSD có cùng giai đoạn lỗi không?
4. Resolver trả null cho URI lạ có luôn nghĩa là từ chối không?
5. Nếu parse không ném nhưng ErrorHandler đã ghi nhận lỗi, có nên chấp nhận vô điều kiện không?
6. Test DOM có tự chứng minh đường validate trực tiếp một StreamSource khác cũng có cùng cấu hình không?
7. Một tài liệu bị từ chối muộn có cần kiểm tra đầu ra nghiệp vụ không?

Đáp án:

1. Không; đó có thể chỉ là lỗi môi trường.
2. Để chứng minh hệ thống không chỉ từ chối mọi đầu vào.
3. Không; parser và validator có vai trò khác nhau.
4. Không; có thể dẫn tới phân giải mặc định.
5. Không; phải xét chính sách và trạng thái lỗi.
6. Không; cần đi qua đường ứng dụng thật.
7. Có; lỗi không tự hoàn tác tác dụng phụ đã xảy ra.

Một bộ test tốt chứng minh được dữ liệu đúng được chấp nhận, dữ liệu sai bị từ chối vì lý do phù hợp và tài nguyên chỉ được xử lý theo chính sách đã xác định.

## Tài liệu đối chiếu

- [JAXP Security Guide — Java SE 25](https://docs.oracle.com/en/java/javase/25/security/java-api-xml-processing-jaxp-security-guide.html): các ranh giới nguồn ngoài và thuộc tính kiểm soát.
- [SchemaFactory — Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.xml/javax/xml/validation/SchemaFactory.html): chuẩn bị schema, resolver và tính năng.
- [LSResourceResolver — Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.xml/org/w3c/dom/ls/LSResourceResolver.html): hợp đồng phân giải và ý nghĩa của null.
