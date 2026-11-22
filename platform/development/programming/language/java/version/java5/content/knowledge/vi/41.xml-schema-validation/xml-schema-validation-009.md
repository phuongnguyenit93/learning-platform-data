# ValidatorHandler trong chuỗi xử lý SAX

## 1. Kiểm tra lược đồ ngay trên dòng sự kiện

SAX đọc XML bằng cách phát các sự kiện như bắt đầu phần tử, đoạn ký tự và kết thúc phần tử. Ứng dụng có thể xử lý những sự kiện đó mà không cần dựng toàn bộ cây DOM.

Nếu cần kiểm tra XML Schema trước khi sử dụng dữ liệu, ValidatorHandler có thể đứng giữa bộ phân tích SAX và handler của ứng dụng:

```text
Nguồn XML
    ↓
XMLReader
    ↓ sự kiện SAX
ValidatorHandler gắn với Schema
    ↓ sự kiện đã đi qua bước kiểm tra
ContentHandler của ứng dụng
```

ValidatorHandler là một bộ kiểm tra theo luồng sự kiện, đồng thời là một ContentHandler. Nó nhận sự kiện ở đầu vào và có thể chuyển tiếp kết quả sang một ContentHandler khác.

Tuy nhiên, một sự kiện đã được chuyển tiếp không chứng minh toàn tài liệu đã hợp lệ. Một lỗi có thể chỉ được phát hiện ở phần sau hoặc lúc kết thúc. Ứng dụng phải giữ ranh giới ghi nhận kết quả toàn tài liệu rõ ràng.

API này có từ Java 5 và vẫn phù hợp trong Java hiện đại. Ví dụ dưới đây chạy trên JDK 17 trở lên với bộ kiểm tra W3C XML Schema.

## 2. Schema, Validator và ValidatorHandler

Ba đối tượng thường gặp có vai trò khác nhau:

| Đối tượng | Vai trò |
| --- | --- |
| Schema | Tập ràng buộc đã được chuẩn bị từ lược đồ |
| Validator | API kiểm tra một nguồn XML theo thao tác mức cao |
| ValidatorHandler | Thành phần nhận và chuyển tiếp sự kiện SAX trong một chuỗi xử lý |

Tạo ValidatorHandler từ Schema:

```java
ValidatorHandler validator = schema.newValidatorHandler();
```

Đây là đoạn minh họa có schema đã được tạo.

Nếu nhu cầu chỉ là kiểm tra một tệp hoặc một nguồn rồi nhận kết quả thành công/lỗi, Validator có thể đủ. ValidatorHandler hữu ích khi ứng dụng đã dùng SAX hoặc muốn kết hợp bước kiểm tra với xử lý sự kiện.

Không cần phân tích XML lần đầu để kiểm tra rồi lần hai chỉ để xử lý, nếu mô hình một chuỗi sự kiện đáp ứng yêu cầu. Nhưng cách dùng một lượt phải xử lý đúng dữ liệu tạm và lỗi muộn, không được coi mọi callback là một cam kết cuối cùng.

Schema có thể được dùng chung theo hợp đồng bất biến và an toàn giữa các luồng. ValidatorHandler là trạng thái của một lần kiểm tra và không có cùng bảo đảm đó.

## 3. Nối chuỗi theo đúng chiều

Cách nối tối thiểu:

```java
reader.setContentHandler(validator);
validator.setContentHandler(applicationHandler);
reader.parse(input);
```

Trong đoạn minh họa:

- reader là XMLReader.
- validator là ValidatorHandler.
- applicationHandler là ContentHandler của ứng dụng.
- input là InputSource.

Lời gọi đầu đặt validator vào vị trí nhận sự kiện từ parser. Lời gọi thứ hai đặt handler ứng dụng ở phía sau validator.

Sai lầm phổ biến là nối validator rồi lại thay bằng handler ứng dụng:

```java
reader.setContentHandler(validator);
reader.setContentHandler(applicationHandler);
```

Lời gọi thứ hai thay thế đích thứ nhất. Handler ứng dụng giờ nhận trực tiếp sự kiện từ reader; ValidatorHandler không còn nằm trên đường đó.

Cũng không nối ngược thành một vòng callback. Chuỗi phải có hướng xử lý rõ ràng.

ValidatorHandler không tự gọi parse. Nguồn phát sự kiện vẫn là XMLReader hoặc một thành phần tạo sự kiện SAX đúng hợp đồng.

## 4. Namespace và hợp đồng sự kiện

ValidatorHandler cần các sự kiện tên phần tử, thuộc tính và ánh xạ namespace nhất quán.

Với SAX parser:

```java
SAXParserFactory factory = SAXParserFactory.newDefaultInstance();
factory.setNamespaceAware(true);
XMLReader reader = factory.newSAXParser().getXMLReader();
```

Đây là đoạn minh họa, chưa bao gồm các cấu hình giới hạn truy cập nguồn ngoài và xử lý lỗi của chương trình đầy đủ.

Nên so sánh theo URI namespace và localName khi định danh phần tử, thay vì chỉ dựa vào qName có thể chứa tiền tố. Tiền tố khác nhau có thể ánh xạ cùng một URI.

Ví dụ trong bài dùng XML không có target namespace để tập trung vào chuỗi xử lý, nhưng vẫn bật namespace-aware để parser cung cấp đúng ngữ nghĩa tên.

Nếu tự viết bộ phát sự kiện thay vì dùng parser, phải chuyển đúng các sự kiện startPrefixMapping/endPrefixMapping và tham số tên. ValidatorHandler không sửa được một dòng sự kiện vốn không tuân thủ mô hình namespace.

Bật validating của SAXParserFactory không phải cách thay thế cho việc gắn đúng ValidatorHandler với Schema đã chọn. Cần phân biệt kiểm tra DTD ở cấu hình parser với kiểm tra XSD trong chuỗi riêng.

## 5. ValidatorHandler có thể bổ sung thông tin

Bộ kiểm tra không chỉ là một cổng bỏ qua hoặc báo lỗi. Nó có thể bổ sung thông tin từ lược đồ vào sự kiện đầu ra, chẳng hạn thuộc tính có giá trị mặc định.

Với XSD quy định:

```xml
<xs:attribute name="status" type="xs:string" default="new"/>
```

và đầu vào:

```xml
<order><qty>2</qty></order>
```

handler phía sau có thể nhận thuộc tính status bằng new dù tài liệu không viết nó trực tiếp.

Điều này không có nghĩa chuỗi XML gốc đã bị sửa. Đây là thông tin được tăng cường trong dòng sự kiện chuyển tiếp.

TypeInfoProvider lấy từ ValidatorHandler cho phép truy cập thông tin kiểu và một số thông tin về thuộc tính. Với W3C XML Schema trong ví dụ, isSpecified có thể phân biệt thuộc tính được viết ở đầu vào với thuộc tính được validator thêm.

Phải đọc thông tin đó trong callback được API cho phép:

- Thông tin thuộc tính và isSpecified được xét trong startElement của handler phía sau.
- Thông tin kiểu phần tử có phạm vi callback startElement/endElement theo hợp đồng.

Không giữ một chỉ số thuộc tính rồi gọi isSpecified tùy ý sau khi parse đã kết thúc. Chỉ số gắn với Attributes của sự kiện hiện tại.

## 6. Ví dụ Java chạy được

Lược đồ yêu cầu qty là số nguyên dương và cung cấp status mặc định. Chương trình kiểm chứng:

1. XML hợp lệ thiếu status nhận giá trị mặc định.
2. XML hợp lệ ghi status giữ giá trị được ghi.
3. Giá trị qty bằng không bị từ chối.
4. Một phần tử thừa ở cuối cũng bị từ chối.

Lưu thành `SaxValidationPipelineDemo.java`:

```java
import java.io.StringReader;
import javax.xml.XMLConstants;
import javax.xml.parsers.SAXParserFactory;
import javax.xml.transform.stream.StreamSource;
import javax.xml.validation.Schema;
import javax.xml.validation.SchemaFactory;
import javax.xml.validation.TypeInfoProvider;
import javax.xml.validation.ValidatorHandler;
import org.xml.sax.Attributes;
import org.xml.sax.InputSource;
import org.xml.sax.SAXException;
import org.xml.sax.SAXParseException;
import org.xml.sax.XMLReader;
import org.xml.sax.helpers.DefaultHandler;

public class SaxValidationPipelineDemo {
    private static final String XSD = """
            <xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
              <xs:element name="order">
                <xs:complexType>
                  <xs:sequence>
                    <xs:element name="qty" type="xs:positiveInteger"/>
                  </xs:sequence>
                  <xs:attribute name="status"
                                type="xs:string" default="new"/>
                </xs:complexType>
              </xs:element>
            </xs:schema>
            """;

    record Result(String qty, String status, boolean defaulted) {}

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

    static final class Collector extends DefaultHandler {
        private final TypeInfoProvider types;
        private final StringBuilder qty = new StringBuilder();
        private boolean inQty;
        private String status;
        private boolean defaulted;

        Collector(TypeInfoProvider types) {
            this.types = types;
        }

        @Override
        public void startElement(
                String uri, String localName,
                String qName, Attributes attributes) {
            if (localName.equals("order")) {
                int index = attributes.getIndex("", "status");
                status = attributes.getValue(index);
                defaulted = !types.isSpecified(index);
            } else if (localName.equals("qty")) {
                inQty = true;
                qty.setLength(0);
            }
        }

        @Override
        public void characters(char[] ch, int start, int length) {
            if (inQty) {
                qty.append(ch, start, length);
            }
        }

        @Override
        public void endElement(
                String uri, String localName, String qName) {
            if (localName.equals("qty")) {
                inQty = false;
            }
        }

        Result result() {
            return new Result(qty.toString().trim(), status, defaulted);
        }
    }

    private static Schema schema() throws Exception {
        SchemaFactory factory =
                SchemaFactory.newInstance(XMLConstants.W3C_XML_SCHEMA_NS_URI);
        factory.setFeature(XMLConstants.FEATURE_SECURE_PROCESSING, true);
        factory.setProperty(XMLConstants.ACCESS_EXTERNAL_DTD, "");
        factory.setProperty(XMLConstants.ACCESS_EXTERNAL_SCHEMA, "");
        factory.setErrorHandler(new FailFast());
        try (StringReader reader = new StringReader(XSD)) {
            return factory.newSchema(new StreamSource(reader));
        }
    }

    private static Result validate(Schema schema, String xml)
            throws Exception {
        SAXParserFactory parserFactory =
                SAXParserFactory.newDefaultInstance();
        parserFactory.setNamespaceAware(true);
        parserFactory.setFeature(XMLConstants.FEATURE_SECURE_PROCESSING, true);
        parserFactory.setFeature(
                "http://apache.org/xml/features/disallow-doctype-decl", true);
        XMLReader reader = parserFactory.newSAXParser().getXMLReader();
        reader.setProperty(XMLConstants.ACCESS_EXTERNAL_DTD, "");
        reader.setProperty(XMLConstants.ACCESS_EXTERNAL_SCHEMA, "");

        ValidatorHandler validator = schema.newValidatorHandler();
        Collector collector = new Collector(validator.getTypeInfoProvider());

        reader.setErrorHandler(new FailFast());
        validator.setErrorHandler(new FailFast());
        reader.setContentHandler(validator);
        validator.setContentHandler(collector);

        try (StringReader input = new StringReader(xml)) {
            reader.parse(new InputSource(input));
        }
        return collector.result();
    }

    private static void rejected(Schema schema, String label, String xml)
            throws Exception {
        try {
            validate(schema, xml);
            throw new AssertionError("Invalid XML was accepted");
        } catch (SAXException e) {
            System.out.println(label + "=REJECTED");
        }
    }

    public static void main(String[] args) throws Exception {
        Schema schema = schema();

        Result first = validate(schema, "<order><qty>2</qty></order>");
        System.out.println("default=qty:" + first.qty()
                + ",status:" + first.status()
                + ",defaulted:" + first.defaulted());

        Result second = validate(schema,
                "<order status=\"ready\"><qty>5</qty></order>");
        System.out.println("explicit=qty:" + second.qty()
                + ",status:" + second.status()
                + ",defaulted:" + second.defaulted());

        rejected(schema, "invalid",
                "<order><qty>0</qty></order>");
        rejected(schema, "lateInvalid",
                "<order><qty>2</qty><extra/></order>");
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```shell
javac --release 17 SaxValidationPipelineDemo.java
java SaxValidationPipelineDemo
```

Stdout:

```text
default=qty:2,status:new,defaulted:true
explicit=qty:5,status:ready,defaulted:false
invalid=REJECTED
lateInvalid=REJECTED
```

### Những điểm có chủ ý trong chương trình

- Schema được tạo một lần và dùng cho nhiều lần kiểm tra.
- Mỗi lần validate tạo ValidatorHandler và Collector mới.
- Parser gửi sự kiện cho validator, rồi validator chuyển sang collector.
- Cả lỗi cú pháp XML ở reader và lỗi lược đồ ở validator đều có ErrorHandler được gắn rõ ràng.
- result chỉ được trả sau khi parse hoàn tất bình thường với chính sách dừng khi gặp error/fatalError.
- Collector giữ dữ liệu tạm trong bộ nhớ; nó không ghi hóa đơn, cơ sở dữ liệu hay gửi thông báo trong callback.

Collector dùng TypeInfoProvider của bộ kiểm tra XSD dựng sẵn đang chạy trong ví dụ. Khi tổng quát hóa cho một ngôn ngữ lược đồ hoặc triển khai khác, cần kiểm tra khả năng cung cấp thông tin kiểu theo hợp đồng, không mặc định mọi provider đều giống nhau.

Tên thông báo lỗi chi tiết có thể phụ thuộc triển khai. Chương trình kiểm tra việc từ chối thay vì gắn expected vào toàn bộ thông báo nội bộ của bộ phân tích.

## 7. ErrorHandler quyết định cách lần kiểm tra được đánh giá

ValidatorHandler có một ErrorHandler riêng. XMLReader cũng có ErrorHandler của parser.

Hai tầng phát hiện những loại vấn đề khác nhau:

| Tầng | Ví dụ vấn đề |
| --- | --- |
| XMLReader | XML sai cú pháp, cấu trúc đóng/mở không hợp lệ |
| ValidatorHandler | XML đúng cú pháp nhưng không thỏa kiểu hoặc cấu trúc XSD |
| Handler ứng dụng | Quy tắc nghiệp vụ ngoài phạm vi lược đồ |

Trong ví dụ, error và fatalError đều ném lại SAXParseException để dừng lần xử lý. Các cảnh báo theo chính sách mặc định của DefaultHandler không được biến thành lỗi bắt buộc của bài.

Nếu một ErrorHandler chỉ ghi log rồi trở về bình thường sau lỗi lược đồ, xử lý có thể tiếp tục theo khả năng phục hồi. Khi đó “parse không ném” không đủ để kết luận hợp lệ; ứng dụng phải lưu trạng thái lỗi và kiểm tra ở cuối.

Có hai chính sách hợp lý tùy nhu cầu:

- Dừng khi gặp lỗi đầu tiên: đường xử lý đơn giản, không tiếp tục tạo dữ liệu có thể không dùng được.
- Thu thập nhiều lỗi có kiểm soát: ghi nhận trạng thái không hợp lệ và chỉ chấp nhận khi không có lỗi theo chính sách.

Không trộn chúng theo cách handler ghi lỗi nhưng hàm vẫn trả kết quả thành công vô điều kiện.

Một SAXException cũng có thể xuất phát từ handler ứng dụng, không chỉ từ XSD. Bộ điều phối đầy đủ cần giữ nguồn gốc lỗi để chẩn đoán. Hai lời gọi rejected trong ví dụ dùng XML cố định sai lược đồ để kiểm chứng đường từ chối.

## 8. Dữ liệu nhận sớm vẫn có thể thuộc tài liệu sai

Giả sử ứng dụng đã nhận qty rồi sau đó mới xuất hiện phần tử extra không được XSD cho phép.

Các callback trước đó có thể đã được gửi tới collector. Validator không thể quay ngược thời gian để thu hồi các tác dụng phụ ứng dụng đã làm.

Vì vậy mẫu này có rủi ro:

```text
startElement/characters
       ↓
ghi trực tiếp bản ghi nghiệp vụ
       ↓
phần cuối XML sai
       ↓
tài liệu bị từ chối nhưng tác dụng phụ đã xảy ra
```

Một thiết kế rõ hơn:

```text
Sự kiện → trạng thái tạm
              ↓
parse hoàn tất + chính sách lỗi cho phép
              ↓
kiểm tra nghiệp vụ → ghi nhận kết quả
```

Với tài liệu nhỏ, có thể giữ đối tượng tạm như trong ví dụ. Với dữ liệu lớn, cần thiết kế vùng lưu tạm, giao dịch hoặc cơ chế ghi nhận có thể hủy theo ranh giới phù hợp.

Không phải lúc nào cũng cần gom toàn tài liệu vào một đối tượng lớn. Nhưng phải có một câu trả lời cho việc “nếu lỗi xuất hiện sau phần đã xử lý thì làm gì?”, thay vì mặc định kiểm tra theo luồng đồng nghĩa mọi phần được chứng nhận vĩnh viễn ngay khi đi qua.

## 9. Callback SAX có vòng đời dữ liệu ngắn

Một đoạn văn bản có thể được chia thành nhiều lần characters. Không giả định một phần tử đơn giản luôn đến dưới dạng đúng một char[].

Trong Collector:

```java
qty.append(ch, start, length);
```

tích lũy từng đoạn được nhận. Gán qty mới cho mỗi lần characters sẽ có thể chỉ giữ đoạn cuối.

Các đối tượng và vùng đệm của callback cũng có thể được tái sử dụng. Nếu muốn xử lý sau hoặc gửi sang luồng khác:

- Sao chép đoạn ký tự hoặc chuyển thành giá trị do ứng dụng sở hữu.
- Sao chép thuộc tính cần thiết hoặc tạo một bản sao phù hợp của dữ liệu thuộc tính, thay vì giữ tham chiếu với giả định nó sẽ không đổi.
- Đọc TypeInfoProvider trong đúng callback rồi giữ lại thông tin cần dùng theo hợp đồng.

Ví dụ chỉ giữ String status và cờ defaulted, không giữ Attributes để đọc ở cuối.

Collector còn dựa vào lược đồ rất nhỏ với qty không có cấu trúc lồng phức tạp. Một bộ xử lý XML tổng quát có thể cần ngăn xếp trạng thái, không chỉ một boolean inQty.

## 10. Vòng đời và khả năng dùng lại

ValidatorHandler tự khởi tạo lại trạng thái kiểm tra khi nhận startDocument theo hợp đồng. Điều đó cho phép một số cách dùng lại tuần tự, nhưng không tự đặt lại trạng thái trong mọi handler ứng dụng bên dưới.

Nếu Collector đã giữ dữ liệu từ lần trước mà không tự reset, dùng lại cả chuỗi có thể làm lẫn kết quả dù validator đã bắt đầu tài liệu mới.

Tạo handler riêng cho mỗi lần xử lý thường là điểm bắt đầu dễ kiểm chứng:

```text
Schema dùng chung
    ├── ValidatorHandler A → Collector A → tài liệu A
    └── ValidatorHandler B → Collector B → tài liệu B
```

Không dùng một ValidatorHandler đồng thời cho hai luồng hoặc gọi lồng lại nó khi lần xử lý hiện tại chưa kết thúc. Nó không an toàn giữa nhiều luồng và không hỗ trợ kiểu sử dụng lồng lại đó.

Một Schema dùng chung không cấp bảo đảm đồng thời cho XMLReader, ValidatorHandler hoặc Collector được tạo từ nó. Mỗi thành phần có vòng đời và hợp đồng riêng.

## 11. Kiểm tra theo luồng không có nghĩa không dùng bộ nhớ

SAX và ValidatorHandler cho phép tránh dựng DOM toàn bộ trong mô hình như ví dụ. Nhưng không nên khẳng định việc kiểm tra luôn dùng một lượng bộ nhớ hằng số.

Bộ kiểm tra có thể giữ trạng thái cần thiết cho ràng buộc của schema. Những ràng buộc về khóa, tham chiếu hoặc quan hệ dữ liệu có thể cần thông tin từ các phần đã đọc. Handler ứng dụng cũng có thể tự tích lũy dữ liệu lớn.

Hãy xem bộ nhớ ở cả ba nơi:

1. Bộ phân tích và bộ đệm đầu vào.
2. Trạng thái kiểm tra lược đồ.
3. Dữ liệu tạm của ứng dụng.

Chọn chuỗi SAX vì phù hợp quan hệ xử lý theo sự kiện, rồi đo tải thực tế nếu kích thước tài liệu lớn. Đừng chỉ thay DOM bằng SAX nhưng vẫn giữ toàn bộ nội dung trong một StringBuilder không giới hạn mà coi đã giải quyết bộ nhớ.

## 12. Kiểm soát nguồn ngoài ở đúng tầng

Có hai thời điểm liên quan đến nguồn ngoài:

- Chuẩn bị Schema, nơi XSD có thể tham chiếu lược đồ hoặc tài nguyên khác.
- Phân tích tài liệu XML, nơi parser có thể gặp cấu trúc tham chiếu ngoài theo cấu hình.

Ví dụ chỉ dùng XSD và XML đã có trong bộ nhớ. Nó giới hạn truy cập ngoài ở SchemaFactory và ở reader, đồng thời từ chối DOCTYPE.

Cấu hình ở một factory không tự chứng minh mọi thành phần khác trong chuỗi đã có cùng giới hạn. Không nuốt lỗi thiết lập rồi vẫn giả định chương trình đang chạy với chính sách mong muốn.

Nếu ứng dụng thực sự cần import/include lược đồ, dùng chính sách phân giải tài nguyên được cho phép rõ ràng; không mở toàn bộ mạng hoặc hệ thống tệp chỉ để một tài liệu mẫu chạy được.

Nguồn Reader/InputStream vẫn cần chủ sở hữu đóng. ValidatorHandler làm việc trên sự kiện nên không có một lệnh close để thay nghĩa vụ đóng nguồn I/O của phía tạo parser.

## 13. Tự kiểm tra

1. ValidatorHandler phát sinh sự kiện từ XML hay nhận sự kiện từ XMLReader?
2. Phải gắn handler ứng dụng vào reader hay vào validator để nó ở sau bước kiểm tra?
3. Một callback qty đã tới ứng dụng có chứng minh toàn tài liệu hợp lệ không?
4. Vì sao phải tích lũy nhiều lần characters?
5. Nếu ErrorHandler chỉ ghi log rồi trở về, có thể chỉ nhìn việc parse không ném để kết luận hợp lệ không?
6. Schema an toàn giữa nhiều luồng có làm một ValidatorHandler dùng chung cũng an toàn không?
7. Có được gọi isSpecified sau khi parse xong với chỉ số thuộc tính cũ không?

Đáp án:

1. Nhận sự kiện; XMLReader thực hiện parse và phát.
2. Gắn vào ValidatorHandler, còn reader gửi cho validator.
3. Không; lỗi có thể được phát hiện muộn.
4. SAX có thể chia văn bản thành nhiều đoạn.
5. Không; cần xét trạng thái lỗi theo chính sách.
6. Không; hai kiểu có hợp đồng khác nhau.
7. Không; phải dùng trong callback phù hợp.

Một chuỗi SAX đúng cần hướng nối rõ, chính sách lỗi rõ và một ranh giới ghi nhận kết quả sau khi tài liệu được chấp nhận. ValidatorHandler cung cấp bước kiểm tra trong chuỗi đó, còn ứng dụng quyết định cách giữ dữ liệu tạm và xử lý thất bại.

## Tài liệu đối chiếu

- [ValidatorHandler — Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.xml/javax/xml/validation/ValidatorHandler.html): chuỗi SAX, sự kiện bổ sung và vòng đời.
- [Schema — Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.xml/javax/xml/validation/Schema.html): tạo bộ kiểm tra và khả năng dùng chung.
- [TypeInfoProvider — Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.xml/javax/xml/validation/TypeInfoProvider.html): phạm vi callback và thông tin thuộc tính.
