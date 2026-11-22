# Giới hạn kích thước, độ phức tạp và quyền truy cập tài nguyên ngoài

## 1. Hợp lệ theo XSD không đồng nghĩa chi phí xử lý chấp nhận được

Một tài liệu XML có thể đúng cấu trúc nhưng quá lớn để ứng dụng xử lý trong tài nguyên cho phép. Ngược lại, parser có thể bị tiêu tốn tài nguyên trước khi Validator kịp báo tài liệu không hợp XSD.

Cần tách ba loại giới hạn:

| Loại | Mục tiêu |
| --- | --- |
| Kích thước đầu vào | Không đọc/giữ lượng dữ liệu vượt ngân sách |
| Độ phức tạp xử lý | Giới hạn độ sâu, thuộc tính, entity hoặc mô hình schema |
| Quyền truy cập tài nguyên ngoài | Không tự đọc tệp/mạng ngoài những gì ứng dụng cho phép |

Không có một giới hạn đơn lẻ thay thế cả ba.

```text
Nguồn XML/XSD
    ↓ giới hạn byte và chính sách nguồn
Parser / SchemaFactory
    ↓ giới hạn cấu trúc và quyền phân giải phụ thuộc
DOM hoặc Schema đã chuẩn bị
    ↓ Validator và chính sách lượt kiểm tra
Kết quả có kiểm soát
```

Các cơ chế JAXP hiện hành được mô tả trong [JAXP Security Guide](https://docs.oracle.com/en/java/javase/21/security/java-api-xml-processing-jaxp-security-guide.html). Khi dùng một JDK hoặc bộ cung cấp khác, phải xác minh các thuộc tính thật sự được hỗ trợ.

## 2. Bảo vệ ở cả lúc biên dịch XSD và lúc kiểm tra XML

Có ít nhất hai đầu vào khác nhau:

1. XSD chính cùng các include/import.
2. XML cần kiểm tra cùng các cấu trúc tham chiếu có liên quan.

`SchemaFactory.newSchema(...)` là bước biên dịch quy tắc, không phải thao tác miễn chi phí. Nếu XSD được cung cấp từ bên ngoài, nó cũng cần giới hạn và chính sách nguồn.

`Validator.validate(...)` là bước kiểm tra tài liệu. Nếu nguồn là StreamSource, nó còn có hoạt động phân tích XML theo đường xử lý của validator. Nếu nguồn là DOMSource, XML đã được parse trước đó.

Vì vậy:

- Cấu hình factory để quản lý việc tải/biên dịch schema.
- Cấu hình đúng parser tạo DOM hoặc SAXSource nếu ứng dụng tự parse.
- Cấu hình Validator theo chính sách của lượt kiểm tra.
- Giới hạn nguồn chính ngay ở nơi ứng dụng đọc nó.

Cài property lên Validator sau khi một DOM lớn đã được tạo không hoàn tác chi phí hoặc việc đọc tài nguyên ngoài đã xảy ra trước đó.

## 3. Giới hạn byte trước khi tích lũy dữ liệu

Không đọc toàn bộ tài liệu vào một mảng rồi mới kiểm tra độ dài nếu mục tiêu là bảo vệ bộ nhớ trong lúc nhận dữ liệu.

Với nguồn thực tế:

```text
InputStream nguồn
    ↓ bộ đọc có đếm và giới hạn
Parser
```

Bộ đọc phải báo lỗi khi có dữ liệu vượt hạn mức, không chỉ giả vờ trả EOF ở đúng vị trí giới hạn.

### Vì sao cắt về EOF không đủ?

Một bộ đọc trả `-1` khi đạt giới hạn có thể che việc nguồn còn dữ liệu. Nếu phần đã đọc tình cờ là một XML hoàn chỉnh và phần dư là khoảng trắng hoặc dữ liệu khác, ứng dụng có thể nhầm “đã đọc đúng tài liệu” với “đã cắt nguồn dài”.

Một cách rõ ràng là cho phép đọc thêm tối đa một byte để xác định vượt hạn mức rồi ném IOException.

Phân biệt các ngân sách:

- Byte truyền vào.
- Byte sau giải nén.
- Ký tự sau giải mã.
- Bộ nhớ cây DOM.
- Dữ liệu đầu ra hoặc danh sách lỗi tích lũy.

Giới hạn Content-Length hoặc kích thước nén không tự giới hạn dữ liệu sau giải nén. Giới hạn byte cũng không biến chi phí DOM thành đúng cùng số byte, vì các đối tượng cây có phần chi phí riêng.

## 4. FEATURE_SECURE_PROCESSING là điểm bắt đầu

Cấu hình tường minh:

```java
factory.setFeature(XMLConstants.FEATURE_SECURE_PROCESSING, true);
```

chỉ thị cho bộ xử lý áp dụng cơ chế xử lý có kiểm soát theo mô hình bảo vệ của nó.

Không xem đó là một thời hạn CPU, một hạn mức byte toàn tài liệu hay một bằng chứng mọi đường phân giải tài nguyên của ứng dụng đã được kiểm soát.

Với quyền truy cập ngoài, nên đặt các External Access Properties rõ theo yêu cầu, thay vì dựa vào việc một môi trường trước đây có giá trị mặc định phù hợp.

Giá trị mặc định và các giới hạn triển khai có thể khác theo phiên bản hoặc bộ cung cấp. Khi một ngưỡng quan trọng thuộc hợp đồng của dịch vụ, cấu hình và kiểm tra nó tường minh.

## 5. Các giới hạn xử lý của JDK có vai trò khác nhau

Một số thuộc tính triển khai JDK thường gặp:

| Thuộc tính | Điều được giới hạn |
| --- | --- |
| `jdk.xml.maxElementDepth` | Độ sâu lồng phần tử |
| `jdk.xml.elementAttributeLimit` | Số thuộc tính trên một phần tử |
| `jdk.xml.entityExpansionLimit` | Số lần mở rộng entity |
| `jdk.xml.totalEntitySizeLimit` | Tổng kích thước của các entity được tính theo quy tắc bộ xử lý |
| `jdk.xml.maxGeneralEntitySizeLimit` | Kích thước một general entity |
| `jdk.xml.maxParameterEntitySizeLimit` | Kích thước một parameter entity |
| `jdk.xml.entityReplacementLimit` | Số nút trong các phần thay thế entity |
| `jdk.xml.maxXMLNameLimit` | Kích thước tên XML theo phạm vi property |
| `jdk.xml.maxOccurLimit` | Chi phí số nút mô hình nội dung khi xây grammar cho các cấu trúc maxOccurs tương ứng |

Những thuộc tính `jdk.xml.*` này là giới hạn của triển khai JDK, không phải mọi bộ cung cấp JAXP đều bắt buộc hỗ trợ cùng cách.

Cách đặt phụ thuộc loại đối tượng:

```java
// Mã minh họa cho DOM parser factory.
documentFactory.setAttribute("jdk.xml.maxElementDepth", "64");

// Mã minh họa cho schema factory.
schemaFactory.setProperty("jdk.xml.maxOccurLimit", "1000");
```

Các con số là ví dụ cấu hình, không phải ngưỡng chuẩn phù hợp mọi hệ thống. Chọn đủ cho dữ liệu hợp lệ lớn nhất đã xác định và kiểm tra trên tải thực tế.

### Không nhầm phạm vi giới hạn

- `totalEntitySizeLimit` không phải giới hạn tổng byte XML.
- `maxElementDepth` không giới hạn một văn bản cực dài ở độ sâu nhỏ.
- `maxOccurLimit` không đơn giản là “XML chỉ được có tối đa N phần tử lặp”.
- Một ngưỡng về entity không thay thế giới hạn toàn bộ tài liệu khi không có entity nào.

Với các processing limit được JDK mô tả, giá trị không dương có thể có nghĩa không giới hạn. Vì vậy không đặt 0 rồi suy ra đã cấm cấu trúc đó. Kiểm tra hợp đồng property và triển khai đích.

## 6. Quyền truy cập ngoài là danh sách giao thức, không phải danh sách tệp cụ thể

Các hằng chuẩn quan trọng:

```java
XMLConstants.ACCESS_EXTERNAL_DTD
XMLConstants.ACCESS_EXTERNAL_SCHEMA
```

Ví dụ chặn các tham chiếu ngoài theo hai nhóm:

```java
schemaFactory.setProperty(XMLConstants.ACCESS_EXTERNAL_DTD, "");
schemaFactory.setProperty(XMLConstants.ACCESS_EXTERNAL_SCHEMA, "");

validator.setProperty(XMLConstants.ACCESS_EXTERNAL_DTD, "");
validator.setProperty(XMLConstants.ACCESS_EXTERNAL_SCHEMA, "");
```

Giá trị chuỗi rỗng cấm truy cập ngoài trong phạm vi property. Một danh sách như `file` hoặc `file,https` cho phép các giao thức tương ứng. Từ khóa `all` mở mọi giao thức trong phạm vi đó. Xem [XMLConstants External Access Properties](https://docs.oracle.com/en/java/javase/21/docs/api/java.xml/javax/xml/XMLConstants.html).

Điểm quan trọng:

> Cho phép giao thức file không đồng nghĩa chỉ cho phép một thư mục XSD tin cậy.

Tương tự, cho phép https không tự giới hạn máy chủ, đường dẫn, kích thước tải hoặc thời hạn kết nối.

Nếu nhu cầu là “chỉ đọc các schema đóng gói cùng ứng dụng”, cần thêm ánh xạ tài nguyên hoặc resolver/catalog có chính sách cụ thể, thay vì chỉ mở file hoặc https cho toàn bộ nguồn đầu vào.

Các thuộc tính này cũng không thay việc ứng dụng kiểm soát **nguồn chính** mà nó đã tự mở trước khi truyền vào JAXP.

## 7. Resolver là một phần của ranh giới quyền truy cập

`LSResourceResolver` cho phép ứng dụng phân giải hoặc thay thế tài nguyên schema. Nó có thể hữu ích để ánh xạ một định danh schema vào dữ liệu cục bộ đã tin cậy. Xem [LSResourceResolver](https://docs.oracle.com/en/java/javase/21/docs/api/java.xml/org/w3c/dom/ls/LSResourceResolver.html).

Nhưng nếu resolver tự tải một URL tùy ý hoặc mở tệp tùy ý rồi trả stream cho bộ xử lý, chính callback đó đã thực hiện truy cập. Không nên mặc định External Access Properties sẽ kiểm soát hộ mọi I/O mà mã ứng dụng tự thực hiện trong resolver.

Một resolver có chính sách cần xác định:

- Tập định danh được phép.
- Cách xử lý systemId/baseURI và tham chiếu tương đối.
- Tài nguyên chính xác được trả.
- Giới hạn kích thước và vòng đời của nguồn trả về.
- Hành vi khi không tìm thấy ánh xạ.

Trả null thường có nghĩa để bộ xử lý tiếp tục cơ chế phân giải mặc định, không tự có nghĩa “cấm tài nguyên này”. Hành vi từ chối phải được thiết kế và kiểm tra cùng các giới hạn truy cập đã cấu hình.

Nếu dùng catalog, cấu hình đúng tập ánh xạ và chính sách khi không khớp. Không tự nới mọi giao thức chỉ để include/import chạy lại.

## 8. Khi tài liệu không cần DTD, có thể từ chối DOCTYPE

Chặn truy cập DTD ngoài không giống với cấm mọi DOCTYPE. Một DTD nội bộ vẫn là một cấu trúc khác cần được xét theo chính sách.

Nếu miền dữ liệu không cần DTD, parser có thể được cấu hình từ chối DOCTYPE ngay từ đầu. Với parser mặc định JDK dùng trong ví dụ:

```java
parserFactory.setFeature(
        "http://apache.org/xml/features/disallow-doctype-decl",
        true);
```

Đây là một feature theo triển khai được kiểm tra với parser mặc định trong ví dụ, không phải một cờ có bảo đảm cùng tên trên mọi parser tùy chọn.

Nếu ứng dụng thật cần DTD, không áp dụng mù quáng cách cấm toàn bộ đó. Cần thiết kế giới hạn entity và cách phân giải tài nguyên phù hợp với yêu cầu thực tế.

Không bắt lỗi “không hỗ trợ feature” rồi tiếp tục như thể chính sách cấm đã có hiệu lực. Nếu một giới hạn là bắt buộc, lỗi cấu hình phải được đưa lên ở khởi tạo hoặc ranh giới xử lý phù hợp.

## 9. Ví dụ đầy đủ: giới hạn byte, độ sâu và từ chối DOCTYPE

Ví dụ dùng:

- Một XSD nhỏ đã tin cậy, được biên dịch trước.
- Giới hạn đọc 256 byte cho tài liệu XML.
- Độ sâu tối đa 8 và số thuộc tính tối đa 8 cho parser.
- Các giới hạn entity bổ sung và cấm DOCTYPE.
- Không cho truy cập DTD/schema ngoài.
- Parse XML có giới hạn trước, rồi đưa DOM sang Validator.

Tệp `BoundedSchemaValidationDemo.java`, chạy trên JDK 17 trở lên với bộ cung cấp mặc định JDK:

```java
import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.StringReader;
import java.nio.charset.StandardCharsets;
import java.util.Objects;
import javax.xml.XMLConstants;
import javax.xml.parsers.DocumentBuilder;
import javax.xml.parsers.DocumentBuilderFactory;
import javax.xml.transform.dom.DOMSource;
import javax.xml.transform.stream.StreamSource;
import javax.xml.validation.Schema;
import javax.xml.validation.SchemaFactory;
import javax.xml.validation.Validator;
import org.xml.sax.SAXException;
import org.xml.sax.SAXParseException;
import org.xml.sax.helpers.DefaultHandler;

public class BoundedSchemaValidationDemo {
    private static final class LimitedInput extends InputStream {
        private final InputStream input;
        private final long limit;
        private long count;

        LimitedInput(InputStream input, long limit) {
            if (limit < 1 || limit == Long.MAX_VALUE) {
                throw new IllegalArgumentException("Unsupported limit");
            }
            this.input = input;
            this.limit = limit;
        }

        private void check() throws IOException {
            if (count > limit) {
                throw new IOException("Input byte limit exceeded");
            }
        }

        @Override
        public int read() throws IOException {
            check();
            int value = input.read();
            if (value != -1) {
                count++;
                check();
            }
            return value;
        }

        @Override
        public int read(byte[] bytes, int offset, int length) throws IOException {
            Objects.checkFromIndexSize(offset, length, bytes.length);
            if (length == 0) {
                return 0;
            }
            check();
            int requested = (int) Math.min((long) length, limit - count + 1);
            int received = input.read(bytes, offset, requested);
            if (received > 0) {
                count += received;
                check();
            }
            return received;
        }

        @Override
        public void close() throws IOException {
            input.close();
        }
    }

    private static Schema schema() throws SAXException {
        String xsd = """
                <xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
                  <xs:element name="root">
                    <xs:complexType>
                      <xs:sequence>
                        <xs:any minOccurs="0" maxOccurs="unbounded"
                                processContents="skip"/>
                      </xs:sequence>
                    </xs:complexType>
                  </xs:element>
                </xs:schema>
                """;
        SchemaFactory factory = SchemaFactory.newDefaultInstance();
        factory.setFeature(XMLConstants.FEATURE_SECURE_PROCESSING, true);
        factory.setProperty(XMLConstants.ACCESS_EXTERNAL_DTD, "");
        factory.setProperty(XMLConstants.ACCESS_EXTERNAL_SCHEMA, "");
        factory.setProperty("jdk.xml.maxOccurLimit", "1000");
        return factory.newSchema(new StreamSource(new StringReader(xsd)));
    }

    private static void validate(Schema schema, String xml) throws Exception {
        DocumentBuilderFactory factory =
                DocumentBuilderFactory.newDefaultInstance();
        factory.setNamespaceAware(true);
        factory.setFeature(XMLConstants.FEATURE_SECURE_PROCESSING, true);
        factory.setFeature(
                "http://apache.org/xml/features/disallow-doctype-decl", true);
        factory.setAttribute(XMLConstants.ACCESS_EXTERNAL_DTD, "");
        factory.setAttribute(XMLConstants.ACCESS_EXTERNAL_SCHEMA, "");
        factory.setAttribute("jdk.xml.maxElementDepth", "8");
        factory.setAttribute("jdk.xml.elementAttributeLimit", "8");
        factory.setAttribute("jdk.xml.entityExpansionLimit", "100");
        factory.setAttribute("jdk.xml.totalEntitySizeLimit", "10000");

        DocumentBuilder parser = factory.newDocumentBuilder();
        parser.setErrorHandler(new DefaultHandler() {
            @Override
            public void error(SAXParseException error) throws SAXException {
                throw error;
            }

            @Override
            public void fatalError(SAXParseException error) throws SAXException {
                throw error;
            }
        });

        Validator validator = schema.newValidator();
        validator.setProperty(XMLConstants.ACCESS_EXTERNAL_DTD, "");
        validator.setProperty(XMLConstants.ACCESS_EXTERNAL_SCHEMA, "");

        byte[] bytes = xml.getBytes(StandardCharsets.UTF_8);
        try (InputStream input = new LimitedInput(
                new ByteArrayInputStream(bytes), 256)) {
            validator.validate(new DOMSource(parser.parse(input)));
        }
    }

    private static void check(Schema schema, String label, String xml) {
        try {
            validate(schema, xml);
            System.out.println(label + "=ACCEPTED");
        } catch (Exception rejected) {
            System.out.println(label + "=REJECTED");
        }
    }

    public static void main(String[] args) throws Exception {
        Schema schema = schema();
        check(schema, "small", "<root><item/></root>");
        check(schema, "large", "<root><item>" + "x".repeat(300) + "</item></root>");
        check(schema, "deep",
                "<root>" + "<n>".repeat(10) + "</n>".repeat(10) + "</root>");
        check(schema, "doctype",
                "<!DOCTYPE root [<!ENTITY word 'hello'>]>"
                        + "<root><item>&word;</item></root>");
    }
}
```

Biên dịch và chạy:

```shell
javac BoundedSchemaValidationDemo.java
java BoundedSchemaValidationDemo
```

Kết quả đã kiểm tra:

```text
small=ACCEPTED
large=REJECTED
deep=REJECTED
doctype=REJECTED
```

Giải thích:

- small phù hợp XSD và nằm trong các giới hạn.
- large có phần văn bản làm tài liệu vượt 256 byte.
- deep nhỏ về byte nhưng lồng phần tử sâu hơn 8.
- doctype bị từ chối ngay tại chính sách parser, dù entity trong ví dụ chỉ là nội bộ.

Các dữ liệu thử đều nằm trong chương trình; không có thao tác đọc tệp hoặc kết nối mạng từ các tài liệu này.

### Ý nghĩa của LimitedInput

Bộ đọc đếm byte thực tế. Nó đọc thăm thêm tối đa một byte ngoài hạn mức để nhận biết dữ liệu vượt giới hạn, rồi báo IOException thay vì trả EOF giả.

Đích parse vẫn có thể đọc theo khối; wrapper không tích toàn bộ dữ liệu thành một chuỗi mới để đếm.

Trong bài, String và byte[] thử nghiệm đã được tạo sẵn để chương trình tự chạy. Với đầu vào thực tế, đặt bộ giới hạn quanh stream nhận dữ liệu ở đúng ranh giới, trước khi ứng dụng tự đọc hết vào bộ nhớ. Đừng sao chép bước tạo một byte[] không giới hạn rồi coi bộ nhớ đã được bảo vệ.

### XSD trong ví dụ không phải bộ quy tắc nghiệp vụ hoàn chỉnh

`xs:any` với `processContents="skip"` cho phép nội dung con linh hoạt để các ca thử độ sâu và kích thước không bị một quy tắc nghiệp vụ khác từ chối trước.

Không dùng XSD minh họa này thay cho kiểm tra cấu trúc thật của sản phẩm. Mục tiêu là quan sát các giới hạn xử lý.

### Cách báo lỗi trong chương trình chỉ để minh họa

Phương thức check bắt Exception để in một kết quả ngắn cho các ca thử. Trong ứng dụng, phải tách lỗi cấu hình, vượt giới hạn, XML không hợp lệ và lỗi đọc nguồn; không gom mọi lỗi thành một lý do dữ liệu không hợp XSD.

Lỗi cấu hình cần thiết không được bỏ qua để thử lại với ít giới hạn hơn. Việc small phải được chấp nhận cũng là kiểm tra rằng cấu hình minh họa hoạt động trên môi trường chạy.

## 10. Đặt giới hạn trước phần chi phí cần ngăn

Nếu nguồn là DOMSource, cây đã nằm trong bộ nhớ. Validator không thể quay ngược để áp dụng giới hạn byte cho quá trình nhận tài liệu trước đó.

Nếu nguồn là SAXSource với XMLReader do ứng dụng cung cấp, các giới hạn parse phải có trên chính reader đó. Không mặc định một property đặt ở một factory khác sẽ tự tác động tới reader đang dùng.

Nếu nguồn là StreamSource và Validator tự phân tích, cần cấu hình đường xử lý đó phù hợp và giới hạn stream đầu vào trước khi truyền.

Với XSD có include/import, thiết kế quyền truy cập ở giai đoạn biên dịch. Việc Validator dùng một Schema đã biên dịch không sửa được lần biên dịch XSD trước đó đã tải phụ thuộc không mong muốn.

Các dạng nguồn và giai đoạn kiểm tra được mô tả trong [SchemaFactory](https://docs.oracle.com/en/java/javase/21/docs/api/java.xml/javax/xml/validation/SchemaFactory.html) và [Validator](https://docs.oracle.com/en/java/javase/21/docs/api/java.xml/javax/xml/validation/Validator.html).

## 11. Giới hạn cấu trúc không phải thời hạn thực thi tuyệt đối

Một tài liệu hoặc XSD vẫn có thể có phần việc đắt mà những ngưỡng đã chọn chưa mô tả hết: nhiều ràng buộc, mô hình nội dung phức tạp, danh sách lỗi lớn hoặc việc phân giải tài nguyên chậm.

Cần xét thêm:

- Lượng tài liệu được kiểm tra đồng thời.
- Kích thước và độ phức tạp của XSD được chấp nhận.
- Giới hạn số lỗi lưu/ghi log.
- Thời hạn đọc dữ liệu từ mạng nếu có.
- Ngân sách CPU/bộ nhớ cho toàn bộ tác vụ.

Một Future hết thời gian chờ không chứng minh parser hoặc validator đã dừng. `cancel(true)` gửi yêu cầu ngắt theo cơ chế Future, nhưng không tạo bảo đảm mọi bộ xử lý XML sẽ đáp ứng tức thời tại mọi điểm.

Nếu yêu cầu cô lập có giới hạn cứng với mã/bộ xử lý không thể hủy đáng tin cậy, cần chọn môi trường thực thi và cơ chế giới hạn ở cấp phù hợp. Không quảng bá một timeout ở luồng gọi như khả năng thu hồi chắc chắn mọi tài nguyên.

## 12. Chọn và kiểm chứng ngưỡng bằng dữ liệu biên

Một cấu hình cần có bằng chứng ở cả hai phía:

- Tài liệu lớn nhất hợp lệ vẫn được xử lý.
- Ngay trên giới hạn byte bị từ chối rõ.
- XML nhỏ nhưng quá sâu bị từ chối.
- Quá nhiều thuộc tính bị từ chối.
- Tài nguyên ngoài không được phép không bị đọc.
- XSD hợp lệ dùng phụ thuộc đã cho phép vẫn hoạt động.
- Bộ cung cấp không hỗ trợ một cấu hình bắt buộc làm khởi tạo thất bại rõ.

Không thử “bom XML” khổng lồ trong môi trường dùng chung để kiểm tra. Các ca nhỏ với ngưỡng minh họa thấp đủ chứng minh đường từ chối mà không cần tạo khối lượng tài nguyên lớn.

Khi đổi JDK hoặc provider, chạy lại các ca biên. Không chỉ kiểm tra setter không ném ngoại lệ; cần xác nhận cấu trúc vượt ngưỡng thật sự bị chặn theo chính sách.

## 13. Thực hành tự kiểm tra

1. Tăng giới hạn byte của ví dụ nhưng giữ maxElementDepth bằng 8: deep vẫn bị từ chối. Điều đó chứng minh hai ngưỡng không thay thế nhau.
2. Giảm độ sâu của deep xuống mức cho phép: kiểm tra nó đi qua parser và vẫn được XSD minh họa chấp nhận.
3. Chỉ đặt `totalEntitySizeLimit` nhưng bỏ giới hạn byte: vì sao văn bản dài không dùng entity vẫn chưa được khống chế bởi một hạn mức toàn tài liệu?
4. Cho phép giao thức file: vì sao chưa đủ để khẳng định chỉ một thư mục schema được phép đọc?
5. Parse DOM bằng một parser không được cấu hình, rồi mới tạo Validator có giới hạn: những chi phí hoặc truy cập nào đã xảy ra quá sớm để Validator ngăn?
6. Nếu resolver tự tải dữ liệu, ai chịu trách nhiệm áp dụng giới hạn và chính sách cho thao tác tải đó? Chính mã resolver và tầng nguồn của ứng dụng.

Một thiết kế kiểm tra XML có kiểm soát đặt **giới hạn dữ liệu ở đầu vào, giới hạn xử lý tại đúng bộ xử lý và quyền truy cập tại mọi đường phân giải thật sự được dùng**.
