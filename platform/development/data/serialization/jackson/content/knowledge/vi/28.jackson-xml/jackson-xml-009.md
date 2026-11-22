# Cấu hình bộ phân tích XML để hạn chế tài nguyên và thực thể ngoài

Jackson XML cho phép ánh xạ XML sang POJO thông qua XmlMapper. Nhưng XmlMapper không tự phân tích byte XML bằng một parser hoàn toàn riêng: nó dựa trên StAX, cụ thể là XMLInputFactory để tạo XMLStreamReader. Vì vậy, bảo vệ ứng dụng phải được đặt ở đúng tầng parser được XmlMapper sử dụng.

Một cấu hình Jackson chỉ kiểm soát kiểu Java và binding property không đủ để ngăn XML External Entity (XXE), DTD hoặc entity expansion. Cần cấu hình StAX để tắt DTD và external entity resolution, từ chối việc truy cập tài nguyên bên ngoài, đồng thời giới hạn kích thước và độ phức tạp của input. Nếu ứng dụng còn dùng SAX, DOM hoặc XSD validation ở nơi khác, các parser và factory đó cũng phải được bảo vệ riêng.

Bài này tập trung vào cách cấu hình XMLInputFactory an toàn, gắn factory đó vào XmlFactory/XmlMapper, giới hạn tài nguyên, xử lý schema và kiểm thử rằng XML độc hại không thể đọc file hoặc gọi ra mạng.

## 1. Luồng xử lý XML của Jackson

Trong Jackson Databind, ObjectMapper nhận JSON thông qua JsonFactory. Với XML, XmlMapper sử dụng XmlFactory và parser XML dựa trên StAX.

Luồng đọc khái quát:

~~~text
HTTP body / file / InputStream
          |
          v
     XmlMapper
          |
          v
      XmlFactory
          |
          v
   XMLInputFactory
          |
          v
    XMLStreamReader
          |
          v
 Jackson XML parser adapter
          |
          v
   Databinding vào POJO
~~~

XMLInputFactory quyết định parser StAX được tạo ra với chính sách nào về DTD, entity, resolver và một số đặc điểm xử lý XML. Nếu mapper tự tạo parser bằng một XMLInputFactory không được cấu hình, những thiết lập bảo mật trên một SAXParserFactory hoặc DocumentBuilderFactory khác sẽ không bảo vệ đường đọc này.

Điểm quan trọng: **hãy cấu hình đúng XMLInputFactory được truyền vào XmlFactory**. Không nên chỉ tắt XXE ở một parser khác rồi cho rằng XmlMapper cũng được bảo vệ.

### 1.1. XMLMapper không phải là một XML parser security policy

XmlMapper chịu trách nhiệm mapping giữa XML token và Java object. Nó không tự thay thế chính sách bảo mật của parser bên dưới.

Ví dụ, các annotation như XmlElement, JacksonXmlProperty, JsonProperty hoặc XmlRootElement chủ yếu mô tả cấu trúc dữ liệu. Chúng không phải cơ chế ngăn DTD hay chặn truy cập file.

Tương tự, DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES kiểm soát property mapping, không ngăn parser tải external entity. Bảo vệ parser và validate model là hai lớp khác nhau.

## 2. Những rủi ro XML cần hạn chế

XML có một số tính năng hữu ích cho tài liệu và tích hợp legacy nhưng có thể bị lạm dụng khi input đến từ bên ngoài.

| Rủi ro | Cách hoạt động | Tác động có thể có |
|---|---|---|
| External General Entity | Entity trỏ tới file hoặc URL bên ngoài | Đọc file cục bộ, SSRF, rò rỉ dữ liệu |
| External Parameter Entity | DTD tham chiếu tài nguyên bên ngoài trong quá trình khai báo | Tải tài nguyên ngoài, mở rộng bề mặt XXE |
| External DTD | DOCTYPE tham chiếu DTD từ file hoặc URL | Truy cập tài nguyên ngoài, thay đổi cách parse |
| Entity Expansion | Một entity mở rộng thành nhiều entity lồng nhau | Cạn CPU hoặc bộ nhớ |
| Billion Laughs | Nhiều tầng entity tạo lượng văn bản tăng theo cấp số nhân | DoS qua expansion |
| Deep Nesting | XML có độ sâu phần tử rất lớn | Tốn stack, CPU và bộ nhớ |
| Oversized Text/Attributes | Một node hoặc attribute chứa lượng ký tự rất lớn | Tăng heap và thời gian xử lý |
| Excessive Elements | Tài liệu có số phần tử hoặc attribute cực lớn | Tốn CPU, object allocation và bộ nhớ |
| External Schema/Include | XSD import/include hoặc resolver tải schema ngoài | Truy cập mạng hoặc phụ thuộc tài nguyên ngoài |
| XInclude | Một parser hỗ trợ XInclude chèn nội dung từ URI | Đọc tài nguyên ngoài nếu được bật |

Không phải mọi StAX provider đều hỗ trợ mọi tính năng XML theo cùng cách. Ví dụ, XInclude thường xuất hiện ở pipeline SAX/DOM hơn là StAX thuần. Tuy nhiên, nếu ứng dụng có bước tiền xử lý XML bằng parser khác, cần kiểm tra cả pipeline đó.

## 3. XXE là gì?

XML External Entity xảy ra khi tài liệu khai báo một entity tham chiếu đến tài nguyên bên ngoài. Parser có thể thay entity bằng nội dung của tài nguyên đó trong lúc đọc XML.

Ví dụ một tài liệu độc hại:

~~~xml
<?xml version="1.0"?>
<!DOCTYPE user [
  <!ENTITY secret SYSTEM "file:///path/to/secret.txt">
]>
<user>
  <name>&secret;</name>
</user>
~~~

Nếu parser cho phép đọc external general entity, nội dung file có thể được chèn vào giá trị name. Nếu system identifier trỏ tới URL, parser có thể phát sinh request mạng từ máy chủ ứng dụng.

### 3.1. Local file disclosure

Một entity có thể tham chiếu file cục bộ mà tiến trình server có quyền đọc. Khi parser thay entity bằng nội dung file, response hoặc log có thể vô tình tiết lộ dữ liệu đó.

Không nên giả định attacker chỉ đọc được file nằm trong thư mục ứng dụng. Tiến trình Java có thể có quyền đọc cấu hình, credential, file mount hoặc tài liệu khác trên máy.

### 3.2. Server-Side Request Forgery

Nếu external entity trỏ tới URL, parser có thể tạo request từ mạng của server. Điều này có thể làm lộ endpoint nội bộ hoặc kích hoạt truy cập tới dịch vụ mà client bên ngoài không thể kết nối trực tiếp.

Một request XML nhỏ có thể khiến server thực hiện hoạt động mạng ngoài dự kiến. Vì thế, chặn external entity resolution là một biện pháp giảm SSRF ở tầng parser.

### 3.3. External parameter entity và DTD

Parameter entity được dùng bên trong DTD. Một DTD có thể tải thêm khai báo từ tài nguyên ngoài, rồi dùng các khai báo đó để tạo entity khác. Chỉ chặn một dạng external general entity mà vẫn cho phép DTD hoặc parameter entity có thể để lại đường tấn công.

Nếu ứng dụng không cần DTD, chính sách đơn giản và an toàn hơn là tắt hỗ trợ DTD hoàn toàn.

## 4. Entity expansion và Billion Laughs

XML cho phép định nghĩa entity có thể tham chiếu các entity khác. Một tài liệu được thiết kế độc hại có thể tạo nhiều tầng mở rộng, khiến một lượng input rất nhỏ sinh ra lượng văn bản cực lớn.

Ví dụ rút gọn về ý tưởng:

~~~xml
<!DOCTYPE lolz [
  <!ENTITY a "ha">
  <!ENTITY b "&a;&a;&a;&a;">
  <!ENTITY c "&b;&b;&b;&b;">
]>
<root>&c;</root>
~~~

Khi số tầng và số lần lặp tăng, lượng nội dung sau expansion có thể tăng rất nhanh. Đây là dạng tấn công thường được gọi là Billion Laughs.

Tắt DTD sẽ ngăn parser xử lý các khai báo entity trong DOCTYPE theo chính sách thông thường. Nếu hệ thống buộc phải hỗ trợ một tập DTD nội bộ, cần một thiết kế riêng với catalog hoặc resolver chỉ cho phép tài nguyên được kiểm soát, kèm giới hạn expansion của parser. Không nên bật DTD không giới hạn để đáp ứng một tài liệu legacy.

## 5. Tắt DTD và external entities trên XMLInputFactory

StAX định nghĩa hai property quan trọng:

- XMLInputFactory.SUPPORT_DTD: bật/tắt hỗ trợ DTD.
- XMLInputFactory.IS_SUPPORTING_EXTERNAL_ENTITIES: bật/tắt external entity resolution.

Đối với XML đến từ client hoặc nguồn không tin cậy, thường nên đặt cả hai thành false.

~~~java
XMLInputFactory inputFactory = XMLInputFactory.newFactory();

inputFactory.setProperty(XMLInputFactory.SUPPORT_DTD, false);
inputFactory.setProperty(
        XMLInputFactory.IS_SUPPORTING_EXTERNAL_ENTITIES,
        false
);
~~~

Không nên chỉ tắt external entity mà vẫn để DTD hoạt động nếu ứng dụng không có nhu cầu DTD. Tắt DTD giúp loại bỏ cả một nhóm khai báo và expansion không cần thiết.

### 5.1. Kiểm tra provider có hỗ trợ property

XMLInputFactory có thể được cung cấp bởi JDK hoặc thư viện StAX khác như Woodstox. Hành vi và tập property mở rộng có thể khác nhau.

Có thể kiểm tra property trước khi cấu hình:

~~~java
if (!inputFactory.isPropertySupported(XMLInputFactory.SUPPORT_DTD)) {
    throw new IllegalStateException("StAX provider không hỗ trợ tắt DTD");
}

inputFactory.setProperty(XMLInputFactory.SUPPORT_DTD, false);
~~~

Với hai property bảo mật cốt lõi, ứng dụng nên fail startup nếu provider không hỗ trợ hoặc không chấp nhận giá trị mong muốn. Không nên catch IllegalArgumentException rồi tiếp tục chạy như thể parser đã an toàn.

### 5.2. Xác minh lại giá trị đã đặt

Có thể đọc lại property sau khi cấu hình:

~~~java
Object dtdValue = inputFactory.getProperty(XMLInputFactory.SUPPORT_DTD);
Object externalValue = inputFactory.getProperty(
        XMLInputFactory.IS_SUPPORTING_EXTERNAL_ENTITIES
);

if (!Boolean.FALSE.equals(dtdValue)
        || !Boolean.FALSE.equals(externalValue)) {
    throw new IllegalStateException(
            "Không thể xác nhận cấu hình XML parser an toàn"
    );
}
~~~

Đây là kiểm tra cấu hình của provider. Nó vẫn cần được bổ sung bằng test thực tế trên XmlMapper, vì điều quan trọng là mapper đang dùng đúng factory đã được cấu hình.

## 6. Chặn truy cập external DTD bằng XMLConstants.ACCESS_EXTERNAL_DTD

Một số JAXP provider hỗ trợ property XMLConstants.ACCESS_EXTERNAL_DTD. Giá trị chuỗi rỗng có nghĩa không cho phép protocol nào được dùng để truy cập external DTD.

~~~java
if (inputFactory.isPropertySupported(XMLConstants.ACCESS_EXTERNAL_DTD)) {
    inputFactory.setProperty(XMLConstants.ACCESS_EXTERNAL_DTD, "");
}
~~~

Property này là lớp phòng vệ bổ sung. Nó không thay thế SUPPORT_DTD=false và IS_SUPPORTING_EXTERNAL_ENTITIES=false. Khả năng hỗ trợ property trên StAX phụ thuộc provider; nếu không được hỗ trợ, không nên giả định việc đặt property trên một SchemaFactory hoặc DocumentBuilderFactory khác có tác dụng lên XmlMapper.

Với parser security, nên áp dụng nhiều biện pháp tương thích ở đúng parser boundary và kiểm thử hành vi thật thay vì chỉ dựa trên một property.

## 7. Dùng XMLResolver để từ chối tài nguyên ngoài

XMLInputFactory cho phép gắn XMLResolver. Có thể cấu hình resolver từ chối mọi yêu cầu resolve external resource:

~~~java
inputFactory.setXMLResolver(
        (publicID, systemID, baseURI, namespace) -> {
            throw new XMLStreamException(
                    "External XML resource resolution is disabled"
            );
        }
);
~~~

Resolver là lớp phòng vệ bổ sung nếu parser thử phân giải tài nguyên. Kết hợp nó với việc tắt DTD và external entity giúp chính sách rõ ràng hơn.

Không nên trả null với kỳ vọng mọi provider đều xử lý giống nhau. Một số parser có thể fallback sang cơ chế resolution mặc định. Nếu mục tiêu là cấm tài nguyên ngoài, ném XMLStreamException là hành vi fail-closed rõ ràng.

### 7.1. Nếu cần một số tài nguyên nội bộ

Có hệ thống legacy cần một DTD hoặc entity catalog đã được kiểm soát. Trong trường hợp đó, không nên cho phép resolver truy cập URL hoặc file tùy ý.

Một resolver giới hạn nên:

- Chỉ nhận public/system ID đã được allowlist.
- Ánh xạ ID sang tài nguyên nội bộ đã đóng gói hoặc đường dẫn cố định.
- Không fallback ra network khi không tìm thấy.
- Từ chối mọi ID ngoài danh sách.
- Có giới hạn kích thước và version cho tài nguyên được phục vụ.

Nếu không có yêu cầu tương thích bắt buộc, tắt DTD và từ chối mọi external resource vẫn là lựa chọn đơn giản hơn.

## 8. Tạo XmlFactory và XmlMapper bằng factory đã bảo vệ

Cấu hình StAX chỉ có tác dụng nếu XmlMapper sử dụng chính XMLInputFactory đó.

Ví dụ hoàn chỉnh cho Jackson 2.x:

~~~java
import com.fasterxml.jackson.dataformat.xml.XmlFactory;
import com.fasterxml.jackson.dataformat.xml.XmlMapper;

import javax.xml.XMLConstants;
import javax.xml.stream.XMLInputFactory;
import javax.xml.stream.XMLStreamException;

public final class SecureXmlMapperFactory {

    private SecureXmlMapperFactory() {
    }

    public static XmlMapper create() {
        XMLInputFactory inputFactory = XMLInputFactory.newFactory();

        setRequiredBoolean(
                inputFactory,
                XMLInputFactory.SUPPORT_DTD,
                false
        );

        setRequiredBoolean(
                inputFactory,
                XMLInputFactory.IS_SUPPORTING_EXTERNAL_ENTITIES,
                false
        );

        if (inputFactory.isPropertySupported(
                XMLConstants.ACCESS_EXTERNAL_DTD
        )) {
            inputFactory.setProperty(
                    XMLConstants.ACCESS_EXTERNAL_DTD,
                    ""
            );
        }

        inputFactory.setXMLResolver(
                (publicID, systemID, baseURI, namespace) -> {
                    throw new XMLStreamException(
                            "External XML resources are disabled"
                    );
                }
        );

        XmlFactory xmlFactory = new XmlFactory(inputFactory);
        return new XmlMapper(xmlFactory);
    }

    private static void setRequiredBoolean(
            XMLInputFactory factory,
            String property,
            boolean expected
    ) {
        if (!factory.isPropertySupported(property)) {
            throw new IllegalStateException(
                    "StAX provider does not support property: " + property
            );
        }

        factory.setProperty(property, expected);

        Object actual = factory.getProperty(property);
        if (!Boolean.valueOf(expected).equals(actual)) {
            throw new IllegalStateException(
                    "StAX provider did not apply property: " + property
            );
        }
    }
}
~~~

Ở đây:

1. Tạo XMLInputFactory theo provider đang có trong runtime.
2. Tắt DTD và external entities.
3. Nếu provider hỗ trợ, cấm external DTD protocol.
4. Gắn resolver từ chối tài nguyên ngoài.
5. Truyền factory đã cấu hình vào XmlFactory.
6. Tạo XmlMapper dùng XmlFactory đó.

Một số constructor/builder có thể khác giữa các phiên bản Jackson XML. Hãy dùng API tương ứng với dependency của dự án, nhưng giữ nguyên nguyên tắc: factory được cấu hình phải là factory thực sự được XmlFactory dùng.

### 8.1. Không tạo một XmlMapper mặc định ở nơi khác

Nếu ứng dụng có một bean XmlMapper an toàn nhưng một module khác tự tạo new XmlMapper() để đọc file upload, đường đọc thứ hai có thể không dùng cấu hình bảo mật.

Nên tập trung tạo mapper tại composition root hoặc một factory duy nhất. Dependency injection giúp các service dùng cùng chính sách đã được kiểm soát.

### 8.2. Hoàn tất cấu hình trước khi chia sẻ mapper

Jackson mapper có thể được tái sử dụng sau khi cấu hình hoàn tất. Không thay đổi factory properties hoặc đăng ký extension khi mapper đang được nhiều request dùng đồng thời.

XMLInputFactory và implementation provider có thể có đặc tính thread-safety riêng. Kiểm tra tài liệu của provider đang sử dụng; không sửa cấu hình sau khi bắt đầu parse. Nếu provider không đảm bảo sử dụng đồng thời an toàn, cần chọn cách tạo reader/factory theo mô hình được provider hỗ trợ và kiểm thử concurrency.

## 9. XMLMapper với DTO thông thường

Ví dụ DTO:

~~~java
public class UserXml {
    private String id;
    private String name;

    public UserXml() {
    }

    public String getId() {
        return id;
    }

    public void setId(String id) {
        this.id = id;
    }

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }
}
~~~

XML:

~~~xml
<user>
  <id>U-100</id>
  <name>An</name>
</user>
~~~

Đọc bằng mapper đã bảo vệ:

~~~java
XmlMapper mapper = SecureXmlMapperFactory.create();

UserXml user = mapper.readValue(xml, UserXml.class);
~~~

Việc mapping vẫn hoạt động như bình thường đối với XML không dùng DTD hoặc external entities. Chính sách parser không làm thay đổi mục tiêu của databinding; nó giới hạn những tính năng XML có thể tải tài nguyên hoặc tiêu thụ tài nguyên bất thường.

## 10. Giới hạn kích thước đầu vào trước khi parse

Tắt XXE chưa đủ để bảo vệ khỏi XML quá lớn. Một tài liệu không chứa DTD vẫn có thể có hàng triệu phần tử hoặc một text node rất dài.

Nên giới hạn byte đầu vào tại HTTP/file boundary trước khi đưa vào XmlMapper:

- Giới hạn Content-Length nếu có.
- Giới hạn số byte thực tế đọc được vì Content-Length có thể vắng mặt hoặc không đáng tin.
- Nếu request nén, giới hạn cả kích thước sau giải nén.
- Dùng timeout cho việc đọc body.
- Không đọc toàn bộ file không giới hạn vào byte[] hoặc String.
- Áp dụng giới hạn riêng cho batch/record nếu một tài liệu chứa nhiều item.

Ví dụ một InputStream có giới hạn byte:

~~~java
public final class LimitedInputStream extends FilterInputStream {
    private final long maxBytes;
    private long count;

    public LimitedInputStream(InputStream input, long maxBytes) {
        super(input);
        this.maxBytes = maxBytes;
    }

    @Override
    public int read() throws IOException {
        int value = super.read();
        if (value != -1) {
            count++;
            checkLimit();
        }
        return value;
    }

    @Override
    public int read(byte[] buffer, int offset, int length)
            throws IOException {
        int read = super.read(buffer, offset, length);
        if (read > 0) {
            count += read;
            checkLimit();
        }
        return read;
    }

    private void checkLimit() throws IOException {
        if (count > maxBytes) {
            throw new IOException("XML input exceeds configured size limit");
        }
    }
}
~~~

Có thể dùng stream giới hạn này khi đọc:

~~~java
try (InputStream raw = request.getInputStream();
     InputStream bounded = new LimitedInputStream(raw, 2_000_000)) {
    UserXml user = mapper.readValue(bounded, UserXml.class);
}
~~~

Đây là ví dụ minh họa. Trong ứng dụng web, giới hạn request body nên được thực thi sớm ở reverse proxy, server/container và framework; wrapper stream là lớp bổ sung để bảo vệ code đọc dữ liệu. Cần bảo đảm wrapper xử lý cả read(byte[]) và các overload khác nếu ứng dụng dùng mark/reset hoặc transferTo.

## 11. Giới hạn độ sâu, số phần tử và kích thước token

XML có thể gây tốn tài nguyên dù tổng byte không quá lớn. Một tài liệu có thể chứa:

- Nhiều tầng element lồng nhau.
- Rất nhiều sibling element.
- Nhiều attribute trên một element.
- Attribute hoặc text node cực dài.
- Nhiều namespace declaration.
- Các giá trị lặp khiến ứng dụng tạo số lượng object lớn.

StAX chuẩn không cung cấp một bộ giới hạn portable cho tất cả các thuộc tính này. Các giới hạn chi tiết thường phụ thuộc provider.

Nếu dùng Woodstox, hãy xem các giới hạn input của đúng phiên bản, chẳng hạn các thuộc tính tương ứng với:

- Maximum element depth.
- Maximum attributes per element.
- Maximum attribute size.
- Maximum children per element.
- Maximum element count.
- Maximum text length.

Các property thường có tên thuộc namespace com.ctc.wstx, ví dụ com.ctc.wstx.maxElementDepth hoặc com.ctc.wstx.maxTextLength. Tên, kiểu giá trị, default và mức hỗ trợ có thể thay đổi theo phiên bản Woodstox. Dùng hằng số từ WstxInputProperties nếu dependency cung cấp, kiểm tra tài liệu và xác minh property được áp dụng.

Không nên copy một danh sách property vào mọi XMLInputFactory rồi giả định chúng là chuẩn StAX. JDK StAX provider có thể không hiểu các property mở rộng của Woodstox.

### 11.1. Ví dụ cấu hình giới hạn provider-specific

Với Woodstox, ý tưởng cấu hình có thể như sau:

~~~java
XMLInputFactory inputFactory = XMLInputFactory.newFactory();

// Các property mở rộng phụ thuộc Woodstox và version đang dùng.
inputFactory.setProperty("com.ctc.wstx.maxElementDepth", 100);
inputFactory.setProperty("com.ctc.wstx.maxAttributesPerElement", 100);
inputFactory.setProperty("com.ctc.wstx.maxAttributeSize", 64_000);
inputFactory.setProperty("com.ctc.wstx.maxTextLength", 1_000_000);
~~~

Các con số trên chỉ là ví dụ để minh họa cách đặt giới hạn, không phải ngưỡng phù hợp cho mọi hệ thống. Chọn giá trị theo schema và kích thước payload hợp lệ thực tế. Nếu property không được provider hỗ trợ, ứng dụng cần phát hiện điều đó ở startup thay vì âm thầm bỏ qua.

### 11.2. Giới hạn ở nhiều tầng

Một cấu hình an toàn nên có nhiều lớp:

| Tầng | Giới hạn |
|---|---|
| Reverse proxy/API gateway | Request size, timeout, rate limit |
| Web server/framework | Body size, read timeout, decompression limit |
| InputStream wrapper | Byte count thực tế |
| StAX provider | Depth, element count, attribute/text size, entity limits |
| Jackson binding | Kiểu đích, unknown property policy, collection handling |
| Application | Số item tối đa, giới hạn nghiệp vụ, batch size |
| Runtime | Heap, CPU quota, concurrency và request timeout |

Không có một property duy nhất thay thế tất cả các lớp này.

## 12. Cấu hình Woodstox và lựa chọn StAX provider

Jackson XML có thể sử dụng StAX provider có sẵn trong JDK hoặc provider khác trên classpath. Woodstox thường được dùng trong các ứng dụng Jackson XML vì hiệu năng và khả năng cấu hình parser phong phú.

Nếu chọn Woodstox:

- Khai báo dependency tương thích với phiên bản Jackson XML.
- Kiểm tra provider thực tế được XMLInputFactory.newFactory() chọn.
- Đặt security properties trước khi tạo XmlFactory.
- Đặt các giới hạn provider-specific theo tài liệu phiên bản đang dùng.
- Test trên chính runtime production, không chỉ trên máy developer.
- Không giả định JDK provider và Woodstox có cùng property mở rộng.

Có thể kiểm tra provider:

~~~java
XMLInputFactory inputFactory = XMLInputFactory.newFactory();

System.out.println(inputFactory.getClass().getName());
~~~

Thông tin này hữu ích khi điều tra khác biệt giữa môi trường local, test và production. Không nên log toàn bộ cấu hình hoặc đường dẫn nội bộ nếu không cần thiết.

## 13. Dùng XMLResolver theo allowlist

Nếu ứng dụng cần load một số schema hoặc DTD nội bộ, có thể xây resolver chỉ phục vụ tài nguyên được kiểm soát. Ý tưởng:

~~~java
inputFactory.setXMLResolver(
        (publicID, systemID, baseURI, namespace) -> {
            if ("urn:example:trusted-types".equals(systemID)) {
                return getClass()
                        .getResourceAsStream("/xml/trusted-types.dtd");
            }

            throw new XMLStreamException(
                    "XML external identifier is not allowed"
            );
        }
);
~~~

Ví dụ này minh họa allowlist theo system ID. Cần kiểm tra null stream, đóng tài nguyên đúng vòng đời và không fallback tới resolver mặc định. Nếu có nhiều tài nguyên, dùng map allowlist bất biến thay vì điều kiện rải rác.

Không dùng prefix URL như https://trusted.example/ làm bằng chứng đủ an toàn nếu URL có thể redirect, DNS thay đổi hoặc server bị chiếm quyền. Tài nguyên đóng gói cục bộ thường dễ kiểm soát hơn. Nếu thật sự cần network resource, nên tải trước qua một cơ chế có kiểm soát, xác thực nội dung và cache theo version, thay vì để parser tự fetch trong lúc deserialize.

## 14. XSD validation cũng cần chính sách bảo mật riêng

Một số ứng dụng validate XML bằng XML Schema trước khi đưa vào XmlMapper. Schema validation là một parser/resource boundary khác. XSD có thể chứa import/include, và SchemaFactory có thể tải tài nguyên được tham chiếu.

Cấu hình SchemaFactory nên hạn chế external access:

~~~java
SchemaFactory schemaFactory = SchemaFactory.newInstance(
        XMLConstants.W3C_XML_SCHEMA_NS_URI
);

schemaFactory.setFeature(
        XMLConstants.FEATURE_SECURE_PROCESSING,
        true
);

schemaFactory.setProperty(XMLConstants.ACCESS_EXTERNAL_DTD, "");
schemaFactory.setProperty(XMLConstants.ACCESS_EXTERNAL_SCHEMA, "");

Schema schema = schemaFactory.newSchema(trustedSchemaSource);
~~~

Ở đây:

- FEATURE_SECURE_PROCESSING yêu cầu parser/schema processor áp dụng các biện pháp xử lý an toàn mà implementation hỗ trợ.
- ACCESS_EXTERNAL_DTD chặn truy cập DTD ngoài.
- ACCESS_EXTERNAL_SCHEMA chặn truy cập schema ngoài qua các protocol không được cho phép.

Nếu schema cần import/include, cung cấp tài nguyên đã kiểm soát qua catalog hoặc resolver cụ thể. Không mở lại mọi protocol chỉ để làm cho schema load thành công.

### 14.1. SchemaFactory không cấu hình XMLInputFactory

Đặt ACCESS_EXTERNAL_SCHEMA trên SchemaFactory không tự động cấu hình StAX factory mà XmlMapper sử dụng. Ngược lại, tắt DTD trên XMLInputFactory không thay thế cấu hình SchemaFactory.

Mỗi component có trách nhiệm riêng. Nếu pipeline có SAXSource, DOMSource, Transformer hoặc Validator, cần cấu hình security cho đúng factory tương ứng.

### 14.2. XMLConstants.FEATURE_SECURE_PROCESSING không phải property StAX universal

FEATURE_SECURE_PROCESSING thường được dùng với các JAXP factory như SchemaFactory, SAXParserFactory, DocumentBuilderFactory hoặc TransformerFactory tùy implementation. Không nên giả định mọi XMLInputFactory đều hỗ trợ feature này.

Với StAX, hãy dùng các property StAX chuẩn cho DTD và external entities, XMLResolver, cùng giới hạn provider-specific. Kiểm tra API và provider thực tế.

## 15. Nếu ứng dụng dùng SAX hoặc DOM ở nơi khác

Một ứng dụng có thể dùng XmlMapper cho một endpoint nhưng dùng DocumentBuilderFactory hoặc SAXParserFactory để tiền xử lý XML ở endpoint khác. Cấu hình an toàn phải được áp dụng ở từng đường đi.

Ví dụ cho DOM parser:

~~~java
DocumentBuilderFactory factory = DocumentBuilderFactory.newInstance();

factory.setFeature(XMLConstants.FEATURE_SECURE_PROCESSING, true);
factory.setFeature(
        "http://apache.org/xml/features/disallow-doctype-decl",
        true
);
factory.setFeature(
        "http://xml.org/sax/features/external-general-entities",
        false
);
factory.setFeature(
        "http://xml.org/sax/features/external-parameter-entities",
        false
);
factory.setXIncludeAware(false);
factory.setExpandEntityReferences(false);

factory.setAttribute(XMLConstants.ACCESS_EXTERNAL_DTD, "");
factory.setAttribute(XMLConstants.ACCESS_EXTERNAL_SCHEMA, "");
~~~

Các feature URI và attribute có thể khác theo parser implementation. Nếu parser không hỗ trợ một feature bảo mật bắt buộc, fail startup hoặc chọn provider có hỗ trợ; không bỏ qua exception rồi tiếp tục parse XML không tin cậy.

Đoạn code DOM này không cấu hình XmlMapper. Nó chỉ áp dụng nếu ứng dụng thực sự dùng DocumentBuilderFactory. Jackson XML cần cấu hình StAX như các phần trước.

## 16. XInclude và Transformer

XInclude là cơ chế có thể chèn nội dung từ tài nguyên khác vào XML khi parser hỗ trợ và được bật. StAX không có một property portable phổ biến tương đương mọi cấu hình XInclude của SAX/DOM. Nếu pipeline có parser hỗ trợ XInclude, tắt tính năng đó khi không cần.

Tương tự, TransformerFactory có thể xử lý external stylesheet hoặc document function trong XSLT tùy implementation. Nếu XML được transform trước khi đưa vào XmlMapper, cần cấu hình TransformerFactory riêng:

- Bật secure processing.
- Hạn chế external DTD và stylesheet access.
- Không cho stylesheet tự do truy cập network hoặc file.
- Dùng resolver allowlist nếu có dependency bắt buộc.

Không nên cho rằng cấu hình StAX sẽ bảo vệ một bước transform diễn ra trước đó.

## 17. Streaming và xử lý XML lớn

Đọc XML bằng XmlMapper không nhất thiết phải giữ toàn bộ raw XML thành String trước khi parse. Có thể đọc từ InputStream để tránh tạo một bản sao chuỗi lớn:

~~~java
try (InputStream input = Files.newInputStream(path)) {
    UserXml user = secureXmlMapper.readValue(input, UserXml.class);
}
~~~

Với tài liệu lớn có nhiều record độc lập, cân nhắc thiết kế XML dạng stream hoặc xử lý từng phần tử bằng XMLStreamReader. Tuy nhiên, khi tự điều khiển StAX, ứng dụng phải quản lý trạng thái parser và giới hạn số phần tử.

Không nên đọc toàn bộ XML vào String rồi mới parse nếu kích thước không được giới hạn:

~~~java
String xml = Files.readString(path);
UserXml user = mapper.readValue(xml, UserXml.class);
~~~

Cách này tạo allocation lớn và giữ raw document cùng object graph trong bộ nhớ. Nếu payload được nén, cần giới hạn kích thước sau giải nén vì một file nén nhỏ có thể bung thành lượng XML rất lớn.

### 17.1. Một XML document có thể chứa quá nhiều object

Ngay cả khi mỗi phần tử nhỏ, một root có thể chứa hàng triệu record. Giới hạn byte không đủ để kiểm soát số object tạo ra. Hãy đặt giới hạn item count và batch size ở application layer, hoặc dùng streaming để xử lý từng record rồi giải phóng tham chiếu.

### 17.2. Không để parser đọc vô hạn từ network

Với stream network, cần timeout và giới hạn thời gian đọc. Một client có thể gửi dữ liệu rất chậm hoặc dừng giữa một tag, giữ thread và connection trong thời gian dài.

Parser limits kiểm soát cấu trúc dữ liệu; timeout và concurrency limits kiểm soát tài nguyên vận hành. Hai nhóm này bổ sung cho nhau.

## 18. Null, encoding và các quy tắc input khác

Bảo mật parser không thay thế việc kiểm soát encoding và cấu trúc đầu vào.

- Ưu tiên XML UTF-8 nếu hợp đồng cho phép.
- Kiểm tra encoding declaration và byte stream phù hợp.
- Không tự bỏ qua lỗi decode.
- Giới hạn độ dài text/attribute.
- Xử lý namespace theo schema đã định nghĩa.
- Xác định rõ root element mong đợi.
- Bật strict mapping nếu field lạ phải bị từ chối.
- Không để parser tự tải DTD/schema từ URI do input điều khiển.

Nếu API chỉ nhận một schema XML cụ thể, validate root name, namespace và version trước hoặc trong pipeline phù hợp. Một XML well-formed vẫn có thể sai schema hoặc vi phạm nghiệp vụ.

## 19. Kiểm thử XXE trên chính XmlMapper

Không nên chỉ test rằng XMLInputFactory trả về false cho một property. Cần kiểm tra XmlMapper thực sự sử dụng factory đó và không tiết lộ dữ liệu ngoài.

Ví dụ test dùng file tạm chứa một marker bí mật:

~~~java
@Test
void shouldNotExpandExternalFileEntity() throws Exception {
    Path secretFile = tempDir.resolve("secret.txt");
    Files.writeString(secretFile, "DO_NOT_DISCLOSE");

    XmlMapper mapper = SecureXmlMapperFactory.create();

    String xml = """
            <?xml version="1.0"?>
            <!DOCTYPE user [
              <!ENTITY secret SYSTEM "%s">
            ]>
            <user>
              <id>U-1</id>
              <name>&secret;</name>
            </user>
            """.formatted(secretFile.toUri());

    assertThrows(
            JsonProcessingException.class,
            () -> mapper.readValue(xml, UserXml.class)
    );
}
~~~

Tùy StAX provider và cách nó phản ứng khi DTD bị tắt, parser có thể ném lỗi vì DOCTYPE hoặc entity không được khai báo. Mục tiêu bảo mật là marker trong file không bao giờ xuất hiện trong giá trị được deserialize. Nếu provider có hành vi khác, viết assertion phù hợp nhưng vẫn phải xác nhận không có truy cập file.

### 19.1. Kiểm thử SSRF bằng local server

Có thể khởi động một HTTP server cục bộ trên port ngẫu nhiên và tạo XML external entity trỏ tới server đó. Sau khi parse, xác nhận request counter vẫn bằng 0.

Không cần gửi request ra Internet trong test. Local server đủ để xác minh parser không thực hiện external fetch. Test phải chạy với cùng provider và dependency như production.

### 19.2. Kiểm thử DTD và entity expansion

Thêm test cho:

- DOCTYPE có external general entity.
- External parameter entity.
- External DTD URL.
- Internal entity expansion.
- XML lồng quá sâu.
- Text node vượt giới hạn.
- Quá nhiều element hoặc attribute.
- Input bị truncate giữa tag.
- XML hợp lệ thông thường vẫn đọc được.

Các test giới hạn phụ thuộc provider. Hãy xác nhận parser từ chối đúng ngưỡng đã cấu hình, không chỉ kiểm tra property được set.

## 20. Kiểm thử cấu hình factory

Có thể viết một test kiểm tra property cốt lõi:

~~~java
@Test
void shouldDisableDtdAndExternalEntities() {
    XMLInputFactory factory = XMLInputFactory.newFactory();

    factory.setProperty(XMLInputFactory.SUPPORT_DTD, false);
    factory.setProperty(
            XMLInputFactory.IS_SUPPORTING_EXTERNAL_ENTITIES,
            false
    );

    assertEquals(
            Boolean.FALSE,
            factory.getProperty(XMLInputFactory.SUPPORT_DTD)
    );

    assertEquals(
            Boolean.FALSE,
            factory.getProperty(
                    XMLInputFactory.IS_SUPPORTING_EXTERNAL_ENTITIES
            )
    );
}
~~~

Đây chỉ là test cấu hình factory. Test quan trọng hơn vẫn là parse payload tấn công qua XmlMapper đã được tạo từ factory đó.

Nếu ứng dụng chọn Woodstox, thêm test cho các property mở rộng và kiểm tra class provider thực tế. Không để test local chạy bằng Woodstox nhưng production lại dùng provider JDK khác mà không có kiểm tra.

## 21. Xử lý lỗi khi parser từ chối XML

Khi DTD hoặc external entity bị chặn, parser có thể ném XMLStreamException; Jackson XML thường bọc lỗi này trong exception thuộc Jackson Core/Databind tùy thời điểm phát sinh.

Ở tầng API, nên:

- Trả thông báo XML không hợp lệ hoặc chứa cấu trúc không được hỗ trợ.
- Không trả stack trace hoặc đường dẫn file nội bộ.
- Không tiết lộ URL/system ID đầy đủ nếu nó chứa dữ liệu nhạy cảm.
- Log exception type, correlation ID và vị trí parser nếu có.
- Phân biệt lỗi input với lỗi cấu hình parser của server.
- Không tự retry bằng một mapper yếu bảo mật hơn.

Nếu một tài liệu hợp lệ theo schema nghiệp vụ nhưng bị từ chối vì DTD, cần xác định DTD có thực sự bắt buộc không. Nếu có, dùng catalog/resolver allowlist và giới hạn tài nguyên, không bật lại external access toàn cục.

## 22. Cấu hình an toàn theo từng ranh giới dữ liệu

Một ứng dụng có thể có nhiều loại XML:

| Nguồn XML | Chính sách gợi ý |
|---|---|
| Upload từ người dùng | DTD và external entities tắt; giới hạn body, depth, text, element count |
| Webhook từ đối tác | Tắt external resolution; allowlist schema/version; timeout và rate limit |
| File batch nội bộ | Tắt DTD nếu không cần; giới hạn kích thước và số record |
| Tài liệu legacy cần DTD | Resolver/catalog allowlist, tài nguyên local cố định, parser limits và kiểm thử riêng |
| XML có XSD | SchemaFactory chặn external DTD/schema; schema import/include được quản lý |
| XML qua SAX/DOM/Transformer | Cấu hình secure processing và external access trên từng factory riêng |

Không nên dùng một parser policy permissive chỉ vì một nguồn legacy cần DTD. Nếu có thể, tách pipeline hoặc mapper theo trust boundary và mục đích sử dụng.

## 23. Các lỗi cấu hình thường gặp

**Tắt external entities trên SAXParserFactory nhưng XmlMapper vẫn dùng StAX mặc định.** Cấu hình phải áp dụng trên XMLInputFactory được truyền vào XmlFactory.

**Chỉ tắt external entities nhưng vẫn bật DTD không cần thiết.** Tắt cả SUPPORT_DTD và IS_SUPPORTING_EXTERNAL_ENTITIES cho input không tin cậy.

**Bỏ qua IllegalArgumentException khi set security property.** Parser có thể vẫn chạy với cấu hình yếu. Với property bắt buộc, fail startup nếu provider không hỗ trợ.

**Cho rằng ACCESS_EXTERNAL_DTD được hỗ trợ ở mọi StAX provider.** Đây là lớp phòng vệ bổ sung; kiểm tra isPropertySupported và dùng các property StAX chuẩn.

**Cho rằng XMLResolver trả null luôn chặn resource.** Hành vi fallback phụ thuộc provider. Nếu cấm external access, resolver nên từ chối rõ ràng.

**Dùng FEATURE_SECURE_PROCESSING như một property chung cho mọi factory.** Cấu hình này thuộc các JAXP processor tương ứng; StAX cần property và resolver riêng.

**Chỉ giới hạn request bytes.** Một XML nhỏ vẫn có thể rất sâu hoặc có nhiều entity/element. Cần giới hạn cấu trúc ở provider và application layer.

**Cấu hình SchemaFactory nhưng quên XmlMapper.** Schema validation và StAX databinding là hai thành phần khác nhau.

**Kiểm thử factory nhưng không kiểm thử mapper.** Cần parse XXE fixture qua đúng XmlMapper được ứng dụng sử dụng.

**Dùng mapper mặc định ở một đường code khác.** Mọi endpoint đọc XML không tin cậy phải dùng factory đã bảo vệ.

**Bật DTD chỉ để hỗ trợ một file cũ.** Nếu cần, cô lập luồng đó và dùng allowlist resolver thay vì bật external access cho mọi input.

## 24. Quy trình triển khai

Khi đưa XML parsing vào một endpoint hoặc batch pipeline:

1. Xác định parser thực tế: XmlMapper/StAX, SAX, DOM, XSD validator hay Transformer.
2. Chọn StAX provider và kiểm tra provider production.
3. Tắt SUPPORT_DTD và IS_SUPPORTING_EXTERNAL_ENTITIES trên XMLInputFactory.
4. Cấu hình ACCESS_EXTERNAL_DTD nếu provider hỗ trợ.
5. Gắn XMLResolver từ chối external resource hoặc chỉ phục vụ allowlist nội bộ.
6. Truyền factory đã cấu hình vào XmlFactory rồi tạo XmlMapper.
7. Giới hạn request bytes, decompressed bytes, timeout và concurrency.
8. Đặt provider-specific limits cho depth, element count, attribute và text size.
9. Nếu dùng XSD, cấu hình SchemaFactory riêng với external access bị chặn.
10. Nếu dùng SAX/DOM/XSLT ở nơi khác, cấu hình từng factory tương ứng.
11. Viết test XXE, SSRF, entity expansion, deep nesting và oversized input trên runtime production.
12. Phân loại lỗi parser an toàn, không fallback sang parser ít bảo vệ hơn.

## 25. Kết luận

Jackson XML dựa trên StAX để đọc XML, vì vậy việc hạn chế DTD và external entities phải được cấu hình trên XMLInputFactory mà XmlFactory sử dụng. Với input không tin cậy, tắt SUPPORT_DTD và IS_SUPPORTING_EXTERNAL_ENTITIES, bổ sung ACCESS_EXTERNAL_DTD nếu provider hỗ trợ, và đặt XMLResolver từ chối mọi external resource. Sau đó truyền factory đã cấu hình vào XmlFactory để tạo XmlMapper.

Bảo vệ XXE chỉ là một phần của XML security. XML vẫn có thể tiêu thụ quá nhiều tài nguyên qua tài liệu lớn, nesting sâu, số phần tử lớn hoặc text/attribute quá dài. Hãy kết hợp giới hạn body và decompression ở tầng transport, giới hạn parser theo StAX provider, streaming khi phù hợp và validation ở application layer. Nếu dùng XSD, SAX, DOM hoặc Transformer, cấu hình bảo mật riêng cho từng factory. Quan trọng nhất là kiểm thử payload XXE qua chính XmlMapper đang chạy trong production, để xác nhận parser thực sự không đọc file hoặc truy cập mạng ngoài.

## Tài liệu tham khảo

- [Jackson Dataformat XML](https://github.com/FasterXML/jackson-dataformat-xml)
- [Jackson Dataformat XML — XmlFactory API](https://javadoc.io/doc/com.fasterxml.jackson.dataformat/jackson-dataformat-xml/latest/com/fasterxml/jackson/dataformat/xml/XmlFactory.html)
- [Jackson Dataformat XML — XmlMapper API](https://javadoc.io/doc/com.fasterxml.jackson.dataformat/jackson-dataformat-xml/latest/com/fasterxml/jackson/dataformat/xml/XmlMapper.html)
- [Java XMLInputFactory API](https://docs.oracle.com/en/java/javase/17/docs/api/java.xml/javax/xml/stream/XMLInputFactory.html)
- [Java XMLResolver API](https://docs.oracle.com/en/java/javase/17/docs/api/java.xml/javax/xml/stream/XMLResolver.html)
- [Java XMLConstants API](https://docs.oracle.com/en/java/javase/17/docs/api/java.xml/javax/xml/XMLConstants.html)
- [OWASP XML External Entity Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/XML_External_Entity_Prevention_Cheat_Sheet.html)
- [Woodstox StAX implementation](https://github.com/FasterXML/woodstox)

