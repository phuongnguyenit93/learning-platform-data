# Vai trò của schema trong kiểm tra tính hợp lệ XML

## 1. XML đọc được chưa chắc là dữ liệu ứng dụng chấp nhận được

Một tài liệu XML có thể có đủ thẻ mở, thẻ đóng và thuộc tính viết đúng cú pháp, nhưng vẫn thiếu trường bắt buộc, có phần tử lạ hoặc chứa số lượng bằng `0` trong khi giao thức yêu cầu số lượng dương.

**Schema** là bản mô tả những cấu trúc và giá trị được chấp nhận cho một loại tài liệu XML. Kiểm tra theo schema là đối chiếu một tài liệu cụ thể với các ràng buộc đó. Schema đóng vai trò hợp đồng dữ liệu giữa bên tạo XML và bên tiếp nhận XML.

Trong bài này, schema được viết bằng **W3C XML Schema**, thường gọi là **XSD**. Có các ngôn ngữ schema khác, nhưng không cần học đồng thời tất cả để hiểu vai trò của bước kiểm tra. Java hiện đại vẫn cung cấp API công khai `javax.xml.validation` trong module `java.xml`; không đổi tên gói này thành `jakarta.xml.validation`. Xem [khái niệm validation trong JAXP](https://docs.oracle.com/en/java/javase/25/docs/api/java.xml/javax/xml/validation/package-summary.html).

Ví dụ, hai hệ thống trao đổi đơn mua hàng có thể thống nhất rằng mỗi tài liệu phải có:

- Phần tử gốc `purchase` thuộc namespace đã quy định.
- Thuộc tính `id` bắt buộc.
- Một phần tử `sku`, sau đó một phần tử `quantity`.
- `quantity` là số nguyên dương.

Khi những yêu cầu này được viết thành XSD, cả hai bên có thể kiểm tra bằng máy thay vì dựa vào lời mô tả rải rác hoặc chờ lỗi xảy ra sâu trong nghiệp vụ.

## 2. Ba mức kiểm tra có trách nhiệm khác nhau

| Mức kiểm tra | Điều cần xác định | Ví dụ lỗi |
| --- | --- | --- |
| Đúng cú pháp XML — well-formed | Tài liệu có tuân thủ cú pháp XML để đọc được hay không | Thẻ đóng không khớp, hai phần tử gốc, thuộc tính không được bao nháy |
| Hợp lệ theo XSD — schema-valid | Cây XML và giá trị có thỏa schema được chọn hay không | Thiếu `id`, sai thứ tự phần tử, `quantity` bằng `0` |
| Hợp lệ về nghiệp vụ | Dữ liệu có đáp ứng quy tắc ứng dụng và trạng thái thực tế hay không | Mã hàng không tồn tại, số lượng vượt tồn kho, người gọi không có quyền đặt hàng |

Trong quy trình đọc XML thông thường, tài liệu sai cú pháp bị từ chối trước khi có thể hoàn tất việc kiểm tra theo XSD. Nhưng tài liệu đúng cú pháp vẫn có thể không hợp lệ theo schema.

Ngay cả khi hợp lệ theo schema, đơn hàng vẫn có thể bị nghiệp vụ từ chối. Ví dụ `quantity=2` thỏa kiểu số nguyên dương, nhưng kho chỉ còn `1` sản phẩm. XSD không tự truy vấn kho hàng hiện tại để quyết định đơn có được thực hiện.

Kết luận kiểm tra phải được diễn đạt đủ điều kiện: **hợp lệ theo schema nào, phiên bản nào**. Một tài liệu có thể hợp lệ theo schema cho phép trường tùy chọn nhưng không hợp lệ theo schema khác yêu cầu trường đó.

## 3. Những gì schema mô tả được

Với XSD, hợp đồng có thể bao gồm:

- **Tên và cấu trúc:** phần tử/thuộc tính được phép, phần tử cha–con, thứ tự nội dung.
- **Số lần xuất hiện:** bắt buộc hay tùy chọn, một hay nhiều lần.
- **Kiểu dữ liệu:** chuỗi, số nguyên, số thập phân, ngày tháng và các kiểu khác được hỗ trợ.
- **Miền giá trị:** độ dài, giá trị tối thiểu/tối đa, tập giá trị cho phép hoặc mẫu ký tự.
- **Một số quan hệ trong tài liệu:** ràng buộc tính duy nhất, khóa và tham chiếu khóa khi được khai báo.

Khả năng biểu đạt phụ thuộc ngôn ngữ và phiên bản schema; ứng dụng chỉ được bảo vệ bởi những ràng buộc thực sự đã viết. Khai báo một trường là `xs:string` không tự có nghĩa là chuỗi phải khác rỗng, phải là mã hàng đã tồn tại hoặc phải thuộc về người đang đăng nhập.

Không nên nói rằng schema chỉ kiểm tra tên thẻ; cũng không nên nói schema kiểm tra được mọi quy tắc nghiệp vụ. Việc chia trách nhiệm phải dựa vào từng ràng buộc cụ thể. [W3C XML Schema Primer](https://www.w3.org/TR/xmlschema-0/) giới thiệu các thành phần cấu trúc, kiểu và ràng buộc này.

## 4. Đọc một hợp đồng XSD nhỏ

XSD sau mô tả đơn mua hàng của ví dụ:

```xml
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"
           targetNamespace="urn:example:purchase:v1"
           elementFormDefault="qualified">
  <xs:element name="purchase">
    <xs:complexType>
      <xs:sequence>
        <xs:element name="sku" type="xs:string"/>
        <xs:element name="quantity" type="xs:positiveInteger"/>
      </xs:sequence>
      <xs:attribute name="id" type="xs:string" use="required"/>
    </xs:complexType>
  </xs:element>
</xs:schema>
```

Cách diễn giải hợp đồng:

1. `targetNamespace` xác định namespace của phần tử `purchase` được khai báo.
2. `elementFormDefault="qualified"` yêu cầu các phần tử cục bộ `sku` và `quantity` trong ví dụ cũng thuộc namespace đó.
3. `xs:sequence` quy định thứ tự: `sku` trước, `quantity` sau.
4. Không khai báo `minOccurs`/`maxOccurs` cho hai phần tử này nên mỗi phần tử xuất hiện đúng một lần theo giá trị mặc định.
5. `xs:positiveInteger` không chấp nhận `0` hoặc số âm.
6. `use="required"` bắt buộc có thuộc tính `id`. Trong schema này, nó vẫn là chuỗi; chưa có yêu cầu về mẫu mã hoặc tính duy nhất.

Tài liệu phù hợp với hợp đồng:

```xml
<purchase xmlns="urn:example:purchase:v1" id="P-1">
  <sku>BOOK-1</sku>
  <quantity>2</quantity>
</purchase>
```

Namespace mặc định ở phần tử gốc áp dụng cho cả `purchase`, `sku` và `quantity` không có tiền tố. Nó không tự áp dụng cho thuộc tính `id` không có tiền tố. Điều đó phù hợp với khai báo thuộc tính cục bộ trong XSD này.

Không nhất thiết phải dùng một tiền tố cố định cho dữ liệu. Viết các phần tử với tiền tố khác nhưng cùng namespace URI vẫn có thể biểu diễn cùng tên mở rộng; đổi URI thành namespace khác thì không còn là cùng hợp đồng.

### Cùng đúng cú pháp nhưng khác kết quả hợp lệ

| Thay đổi với tài liệu mẫu | Đọc cú pháp XML | Hợp lệ theo XSD này |
| --- | --- | --- |
| Giữ nguyên | Thành công | Có |
| Đổi `quantity` thành `0` | Thành công | Không: sai miền giá trị |
| Đổi `quantity` thành `abc` | Thành công | Không: sai kiểu |
| Bỏ thuộc tính `id` | Thành công | Không: thiếu thuộc tính bắt buộc |
| Đưa `quantity` lên trước `sku` | Thành công | Không: sai thứ tự |
| Đổi namespace URI | Thành công | Không: không khớp khai báo phần tử |
| Viết thẻ đóng `sku` thành `purchase` | Thất bại | Không đi đến kết luận kiểm tra XSD |

Một bộ đọc XML không cấu hình schema có thể đọc thành công những trường hợp ở giữa bảng. Đó là lý do kết quả `parse()` thành công không chứng minh dữ liệu đã được kiểm tra theo XSD.

## 5. Minh chứng bằng Java 17+

Chương trình sau làm rõ hai bước: đọc XML thành DOM, rồi kiểm tra DOM bằng schema đã được ứng dụng chọn. XSD được nhúng để ví dụ chạy độc lập, không cần tệp phụ hoặc tải schema từ mạng.

Lưu thành `SchemaRoleDemo.java`:

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
import org.xml.sax.SAXException;
import org.xml.sax.SAXParseException;
import org.xml.sax.InputSource;
import org.xml.sax.helpers.DefaultHandler;

public class SchemaRoleDemo {
    private static final String XSD = """
            <xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"
                       targetNamespace="urn:example:purchase:v1"
                       elementFormDefault="qualified">
              <xs:element name="purchase">
                <xs:complexType>
                  <xs:sequence>
                    <xs:element name="sku" type="xs:string"/>
                    <xs:element name="quantity" type="xs:positiveInteger"/>
                  </xs:sequence>
                  <xs:attribute name="id" type="xs:string" use="required"/>
                </xs:complexType>
              </xs:element>
            </xs:schema>
            """;

    private static final DefaultHandler FAIL_ON_ERROR = new DefaultHandler() {
        @Override
        public void error(SAXParseException error) throws SAXException {
            throw error;
        }

        @Override
        public void fatalError(SAXParseException error) throws SAXException {
            throw error;
        }
    };

    private static Document parse(String xml) throws Exception {
        DocumentBuilderFactory factory = DocumentBuilderFactory.newDefaultInstance();
        factory.setNamespaceAware(true);
        factory.setFeature(XMLConstants.FEATURE_SECURE_PROCESSING, true);
        factory.setFeature(
                "http://apache.org/xml/features/disallow-doctype-decl", true);
        factory.setAttribute(XMLConstants.ACCESS_EXTERNAL_DTD, "");
        factory.setAttribute(XMLConstants.ACCESS_EXTERNAL_SCHEMA, "");
        factory.setXIncludeAware(false);
        DocumentBuilder builder = factory.newDocumentBuilder();
        builder.setErrorHandler(FAIL_ON_ERROR);
        return builder.parse(new InputSource(new StringReader(xml)));
    }

    private static void check(Schema schema, String label, String xml)
            throws Exception {
        Document document;
        try {
            document = parse(xml);
        } catch (SAXException ex) {
            System.out.println(label + ": PARSE_REJECTED");
            return;
        }

        Validator validator = schema.newValidator();
        validator.setProperty(XMLConstants.ACCESS_EXTERNAL_DTD, "");
        validator.setProperty(XMLConstants.ACCESS_EXTERNAL_SCHEMA, "");
        validator.setErrorHandler(FAIL_ON_ERROR);
        try {
            validator.validate(new DOMSource(document));
            System.out.println(label + ": WELL_FORMED, SCHEMA_VALID");
        } catch (SAXException ex) {
            System.out.println(label + ": WELL_FORMED, SCHEMA_INVALID");
        }
    }

    public static void main(String[] args) throws Exception {
        SchemaFactory factory = SchemaFactory.newDefaultInstance();
        factory.setFeature(XMLConstants.FEATURE_SECURE_PROCESSING, true);
        factory.setProperty(XMLConstants.ACCESS_EXTERNAL_DTD, "");
        factory.setProperty(XMLConstants.ACCESS_EXTERNAL_SCHEMA, "");
        factory.setErrorHandler(FAIL_ON_ERROR);
        Schema schema = factory.newSchema(
                new StreamSource(new StringReader(XSD)));

        String valid = """
                <purchase xmlns="urn:example:purchase:v1" id="P-1">
                  <sku>BOOK-1</sku>
                  <quantity>2</quantity>
                </purchase>
                """;

        check(schema, "valid", valid);
        check(schema, "zero-quantity",
                valid.replace("<quantity>2</quantity>", "<quantity>0</quantity>"));
        check(schema, "wrong-order",
                "<purchase xmlns=\"urn:example:purchase:v1\" id=\"P-1\">"
                + "<quantity>2</quantity><sku>BOOK-1</sku></purchase>");
        check(schema, "wrong-namespace",
                valid.replace("urn:example:purchase:v1", "urn:example:other"));
        check(schema, "broken-tag", "<purchase><sku>BOOK-1</purchase>");
    }
}
```

Biên dịch và chạy trong thư mục chứa tệp:

```shell
javac --release 17 -encoding UTF-8 SchemaRoleDemo.java
java SchemaRoleDemo
```

Stdout:

```text
valid: WELL_FORMED, SCHEMA_VALID
zero-quantity: WELL_FORMED, SCHEMA_INVALID
wrong-order: WELL_FORMED, SCHEMA_INVALID
wrong-namespace: WELL_FORMED, SCHEMA_INVALID
broken-tag: PARSE_REJECTED
```

Ba trường hợp `zero-quantity`, `wrong-order`, `wrong-namespace` chứng minh rằng đúng cú pháp chưa đủ. Bộ đọc tạo được DOM, nhưng bộ kiểm tra từ chối nó theo hợp đồng XSD.

`broken-tag` bị từ chối ngay khi đọc vì thẻ không khớp. Nhãn `PARSE_REJECTED` trong mã chỉ báo bước đọc thất bại; trong ứng dụng tổng quát, bước đọc cũng có thể từ chối một tài liệu do chính sách bảo mật, không chỉ vì cú pháp sai. Nhãn kết quả là do chương trình tự đặt, không phải thông báo chuẩn mà mọi JDK phải in.

### Vai trò của các đối tượng Java trong ví dụ

| Đối tượng | Vai trò |
| --- | --- |
| `DocumentBuilder` | Đọc XML thành DOM với cấu hình namespace và bảo mật |
| `SchemaFactory` | Đọc và biên dịch bản XSD |
| `Schema` | Giữ tập ràng buộc đã được chuẩn bị |
| `Validator` | Kiểm tra một tài liệu cụ thể theo tập ràng buộc đó |

`SchemaFactory.newSchema(...)` có thể thất bại nếu chính XSD sai. Đây là lỗi hợp đồng/cấu hình, khác với việc một tài liệu đầu vào không thỏa một schema đúng. Ví dụ để lỗi tạo schema truyền ra ngoài thay vì giả vờ đó là lỗi của từng đơn hàng.

Java chỉ bắt buộc bộ cung cấp schema tiêu chuẩn hỗ trợ W3C XML Schema 1.0. Ví dụ dùng những tính năng XSD 1.0; đừng mặc định rằng mọi cú pháp XSD 1.1 đều được bộ kiểm tra mặc định của JDK chấp nhận. Xem [SchemaFactory](https://docs.oracle.com/en/java/javase/25/docs/api/java.xml/javax/xml/validation/SchemaFactory.html).

`FAIL_ON_ERROR` ném lại lỗi kiểm tra thay vì chỉ ghi thông báo rồi bỏ qua. Điều này làm kết quả chương trình rõ ràng: một lỗi validation khiến lần kiểm tra thất bại. Nếu viết một `ErrorHandler` chỉ thu thập lỗi và không ném ngoại lệ, ứng dụng phải tự xem danh sách lỗi; không được suy ra `validate()` trả về bình thường nghĩa là tài liệu không có lỗi. Xem [hợp đồng Validator.validate](https://docs.oracle.com/en/java/javase/25/docs/api/java.xml/javax/xml/validation/Validator.html).

## 6. Schema đứng ở đâu trong quy trình tiếp nhận dữ liệu?

Một quy trình hợp lý có dạng:

```text
Chọn hợp đồng/schema đáng tin cậy của ứng dụng
    → đọc XML theo chính sách tài nguyên và bảo mật
    → kiểm tra cấu trúc, kiểu và ràng buộc bằng schema
    → ánh xạ dữ liệu cần dùng
    → kiểm tra nghiệp vụ và phân quyền
    → thực hiện thao tác có tác dụng phụ
```

Trong ví dụ, đọc DOM và kiểm tra XSD được tách để dễ quan sát. JAXP cũng hỗ trợ tích hợp một `Schema` vào bộ đọc XML. Sự khác biệt triển khai không làm mất đi hai trách nhiệm: đọc đúng cú pháp và kiểm tra đúng hợp đồng.

Đặt bước kiểm tra trước khi thực hiện thao tác nghiệp vụ giúp phát hiện lỗi sớm và trả thông tin đúng tầng. Nếu số lượng đã sai kiểu, không nên để đến lúc trừ tồn kho mới phát sinh lỗi ép kiểu.

Schema cũng giúp thử nghiệm tương thích: bên tạo dữ liệu có thể kiểm tra mẫu đầu ra, bên nhận có thể kiểm tra đầu vào, và cả hai dùng cùng phiên bản hợp đồng. Tuy nhiên, thêm trường mới không tự động tương thích; schema hiện tại có thể từ chối phần tử chưa khai báo. Việc nâng phiên bản cần được thiết kế và kiểm thử.

### Ứng dụng phải biết mình đang kiểm tra bằng schema nào

Đuôi tệp `.xml`, khai báo `xmlns`, tên namespace có chữ `v1` hoặc thuộc tính `xsi:schemaLocation` không tự khiến mọi lần đọc XML được kiểm tra.

`xsi:schemaLocation` có thể cung cấp gợi ý vị trí schema; nó không thay thế việc ứng dụng lựa chọn hợp đồng đáng tin cậy và cấu hình bộ kiểm tra. Ví dụ không cần thuộc tính đó vì ứng dụng đã truyền XSD trực tiếp cho `SchemaFactory`.

Đừng để một tài liệu không đáng tin cậy tự chọn một schema dễ dãi hơn rồi dùng kết quả đó làm căn cứ chấp nhận dữ liệu. Kết quả validation chỉ có ý nghĩa khi schema được chọn đúng với giao thức và phiên bản dự định.

## 7. Giới hạn cần hiểu đúng

### Hợp lệ theo schema không đồng nghĩa với an toàn hoặc được phép

XSD đúng không chứng minh nguồn gửi là ai, chữ ký có hợp lệ hay không, người gửi có quyền thực hiện yêu cầu hay không hoặc dữ liệu có trung thực hay không. Những việc đó thuộc các cơ chế kiểm tra riêng.

Kiểm tra XSD cũng không phải phép làm sạch để đưa dữ liệu vào SQL, XPath, HTML hoặc lệnh hệ điều hành. Một chuỗi hợp lệ theo `xs:string` vẫn phải được xử lý đúng ngữ cảnh khi đi vào hệ thống tiếp theo.

Ví dụ bật `FEATURE_SECURE_PROCESSING`, chặn truy cập DTD/schema bên ngoài và từ chối `DOCTYPE` ở bước đọc DOM. Những thiết lập này kiểm soát cách xử lý tài nguyên XML; chúng không được thay thế chỉ bằng một câu “tài liệu đã qua schema”. Nếu ứng dụng thực sự cần các schema phụ, phải có chính sách phân giải tài nguyên được phép thay vì tùy tiện mở truy cập mạng. Xem [JAXP Security Guide](https://docs.oracle.com/en/java/javase/25/security/java-api-xml-processing-jaxp-security-guide.html).

### Schema chỉ kiểm tra những gì đã khai báo

Trong XSD mẫu, `<sku/>` vẫn chứa giá trị chuỗi rỗng hợp lệ về kiểu `xs:string`. Muốn cấm rỗng cần khai báo ràng buộc tương ứng hoặc kiểm tra nghiệp vụ. Tương tự, thuộc tính `id` là bắt buộc có mặt nhưng chưa có nghĩa phải duy nhất trên toàn hệ thống.

Không nên kéo mọi ràng buộc động vào XSD. Quan hệ với tồn kho, tài khoản hoặc thời điểm hiện tại thường cần dữ liệu ngoài và phải được kiểm tra trong nghiệp vụ. Một số quan hệ nội bộ của tài liệu có thể diễn đạt bằng XSD; lựa chọn đúng nơi đặt quy tắc giúp tránh vừa thiếu kiểm tra vừa lặp quy tắc không cần thiết.

### Đừng nhầm đối tượng có thể dùng lại với bộ xử lý dùng chung đồng thời

`Schema` là biểu diễn ràng buộc bất biến và có thể được chia sẻ để tránh biên dịch lại XSD cho từng tài liệu. `Validator` không bảo đảm an toàn khi nhiều luồng dùng đồng thời. Ví dụ tạo một `Validator` mới cho mỗi lần kiểm tra. Xem [Schema](https://docs.oracle.com/en/java/javase/25/docs/api/java.xml/javax/xml/validation/Schema.html).

## 8. Tự kiểm chứng vai trò của schema

Thực hiện từng thay đổi rồi dự đoán tầng nào sẽ từ chối:

1. Đổi `quantity` từ `2` sang `-1`: XML vẫn đọc được, nhưng không thỏa kiểu số nguyên dương.
2. Xóa thuộc tính `id`: cú pháp vẫn đúng, hợp đồng yêu cầu thuộc tính nên kiểm tra XSD thất bại.
3. Thay `BOOK-1` thành mã không có trong kho: schema mẫu vẫn chấp nhận; ứng dụng cần kiểm tra nghiệp vụ.
4. Đổi `<sku>BOOK-1</sku>` thành `<sku/>`: schema mẫu vẫn chấp nhận chuỗi rỗng, qua đó thấy rõ giới hạn ràng buộc đã viết.
5. Giữ nguyên tài liệu hợp lệ nhưng bỏ lời gọi `validator.validate(...)`: việc đọc DOM thành công không chứng minh đã kiểm tra schema.

Khi giải thích được vì sao mỗi thay đổi đi qua hoặc bị chặn ở từng tầng, người học đã nắm đúng vai trò của schema: một hợp đồng dữ liệu có thể kiểm tra bằng máy, nằm giữa cú pháp XML và các quyết định nghiệp vụ của ứng dụng.
