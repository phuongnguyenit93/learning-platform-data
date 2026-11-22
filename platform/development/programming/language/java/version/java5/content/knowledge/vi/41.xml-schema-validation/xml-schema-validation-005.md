# Đầu vào Source và đầu ra Result

## 1. Source và Result mô tả cách dữ liệu đi qua bộ xác thực

Khi kiểm tra XML bằng `Validator`, có hai nhu cầu khác nhau:

- Chỉ kiểm tra tài liệu có đáp ứng schema hay không.
- Kiểm tra và tiếp tục nhận dữ liệu đầu ra để ghi, giữ trong DOM hoặc chuyển sang một bước xử lý khác.

Hai lời gọi tương ứng là:

```java
validator.validate(source);
validator.validate(source, result);
```

`Source` mô tả nơi và dạng cung cấp XML. `Result` mô tả nơi và dạng nhận XML đầu ra. Chúng nằm trong các package `javax.xml.transform.*`, nhưng cũng được API xác thực XML sử dụng; không có nghĩa gọi `validate` là đang chạy một stylesheet XSLT.

```text
Schema đã được chuẩn bị
          ↓ tạo Validator
Source → Validator → Result, nếu cần nhận đầu ra
             ↓
       lỗi/ngoại lệ xác thực
```

**Result không phải một đối tượng chứa boolean “hợp lệ/không hợp lệ”.** Lỗi được báo qua cơ chế xử lý lỗi và ngoại lệ của validator. Nếu chỉ cần kiểm tra, dùng `validate(source)`, tương đương truyền `null` cho result.

Bài dùng API Java hiện hành và ví dụ biên dịch được với Java 17+.

## 2. Chọn loại Source theo dữ liệu đang có

| Loại | Dữ liệu được bọc | Khi phù hợp |
|---|---|---|
| `StreamSource` | `InputStream`, `Reader`, tệp hoặc URI nguồn | Có XML dạng byte/ký tự và muốn bộ xử lý đọc nó |
| `DOMSource` | Một cây hoặc nút DOM | Ứng dụng đã phân tích XML thành DOM |
| `SAXSource` | SAX `InputSource`, có thể kèm `XMLReader` | Muốn dùng luồng sự kiện SAX và parser được quản lý rõ |
| `StAXSource` | `XMLStreamReader` hoặc `XMLEventReader` | Chuỗi xử lý đã dùng cách đọc kéo của StAX |

`Source` là giao diện trừu tượng, không tự biến mọi dạng dữ liệu thành một bản sao bất biến. Bọc một DOM không có nghĩa đã sao chép DOM; bọc một reader không có nghĩa đã đọc hết nội dung vào bộ nhớ. [Giao diện Source](https://docs.oracle.com/en/java/javase/25/docs/api/java.xml/javax/xml/transform/Source.html), [DOMSource](https://docs.oracle.com/en/java/javase/25/docs/api/java.xml/javax/xml/transform/dom/DOMSource.html), [SAXSource](https://docs.oracle.com/en/java/javase/25/docs/api/java.xml/javax/xml/transform/sax/SAXSource.html).

### StreamSource: phân biệt nội dung với vị trí

Để kiểm tra XML đang nằm trong một chuỗi:

```java
StreamSource input = new StreamSource(new StringReader(xmlText));
```

Không viết:

```java
StreamSource input = new StreamSource(xmlText);
```

Constructor nhận `String` coi chuỗi ấy là system ID/URI nguồn, không phải nội dung XML. Nếu `xmlText` bắt đầu bằng `<invoice>`, chương trình có thể cố hiểu nó như vị trí cần mở và báo lỗi không đúng điều người viết mong đợi.

Khi có byte từ tệp hoặc kết nối, dùng `InputStream` để parser còn có thông tin mã hóa XML. Khi đã có `StringReader`, dữ liệu đã là ký tự Java; việc giải mã byte phải được làm đúng từ bước trước.

`StreamSource` gắn với luồng/reader thường chỉ dùng được một lượt. Muốn xác thực hai lần, tạo reader hoặc mở luồng mới; tạo hai wrapper quanh cùng một luồng đã bị đọc không khôi phục nội dung. [Hợp đồng StreamSource](https://docs.oracle.com/en/java/javase/25/docs/api/java.xml/javax/xml/transform/stream/StreamSource.html).

### DOMSource: không cần đọc lại chuỗi XML

Nếu đã có `Document document`:

```java
DOMSource input = new DOMSource(document);
```

Không cần tuần tự hóa DOM thành chuỗi chỉ để tạo `StreamSource` nếu bước kiểm tra chấp nhận DOM. DOM phải được tạo với cấu hình namespace và phân tích XML phù hợp ngay từ đầu.

### SAXSource và StAXSource: giữ nguyên kiểu chuỗi xử lý

Với `SAXSource`, có thể cung cấp parser SAX và `InputSource` thay vì để nguồn byte đi qua một parser không được ứng dụng quản lý rõ. Với `StAXSource`, reader phải ở trạng thái khởi đầu phù hợp như `START_DOCUMENT` hoặc `START_ELEMENT`; không bọc tùy tiện một reader đã đọc hết.

`StAXSource` bị tiêu thụ trong quá trình xử lý và không dùng lại như một tài liệu DOM. System ID của nó được xác định từ reader, không đặt lại bằng `StAXSource.setSystemId`. [Hợp đồng StAXSource](https://docs.oracle.com/en/java/javase/25/docs/api/java.xml/javax/xml/transform/stax/StAXSource.html).

## 3. Chọn Result theo dạng cần nhận

| Loại | Đích nhận |
|---|---|
| `StreamResult` | `OutputStream`, `Writer`, tệp hoặc URI đầu ra |
| `DOMResult` | Nút/cây DOM đầu ra |
| `SAXResult` | Bộ nhận sự kiện SAX |
| `StAXResult` | `XMLStreamWriter` hoặc `XMLEventWriter` |
| `null` | Không yêu cầu nhận XML đầu ra |

Ví dụ giữ nội dung văn bản trong bộ nhớ:

```java
StringWriter buffer = new StringWriter();
StreamResult output = new StreamResult(buffer);
// Sau khi xu ly thanh cong, doc buffer.toString().
```

`StreamResult` giữ đích ghi, không tự cung cấp một `getXml()` hoặc một báo cáo lỗi. Nếu muốn đọc chuỗi đã ghi, giữ tham chiếu đến `StringWriter` như trên. Constructor `StreamResult(String)` mô tả vị trí ghi, không phải “chuỗi đầu ra ban đầu”. [StreamResult](https://docs.oracle.com/en/java/javase/25/docs/api/java.xml/javax/xml/transform/stream/StreamResult.html).

Với `DOMResult`, có thể tạo đích rỗng rồi đọc `getNode()` sau khi xử lý thành công. Đừng đọc nó trước khi bộ xử lý đã tạo kết quả. Nếu cung cấp nút đích, nút ấy phải phù hợp để chứa nội dung con. [DOMResult](https://docs.oracle.com/en/java/javase/25/docs/api/java.xml/javax/xml/transform/dom/DOMResult.html).

`StAXResult` bọc một writer StAX đã có; nó không phải đường tắt để đổi mọi Source sang StAX. [StAXResult](https://docs.oracle.com/en/java/javase/25/docs/api/java.xml/javax/xml/transform/stax/StAXResult.html).

## 4. Validator không cho ghép tùy ý mọi Source với mọi Result

Ma trận các cặp được chấp nhận:

| Source \ Result | `null` | `StreamResult` | `DOMResult` | `SAXResult` | `StAXResult` |
|---|---|---|---|---|---|
| `StreamSource` | Có | Có | Không | Không | Không |
| `DOMSource` | Có | Không | Có | Không | Không |
| `SAXSource` | Có | Không | Không | Có | Không |
| `StAXSource` | Có | Không | Không | Không | Có |

Cặp không khớp gây `IllegalArgumentException`; đó là lỗi cách gọi API, không phải bằng chứng XML vi phạm schema. Ví dụ, `StreamSource → DOMResult` không được chấp nhận trực tiếp bởi `Validator.validate`.

Nếu cần đổi dạng, bổ sung bước chuyển đổi rõ ràng: chẳng hạn phân tích XML thành DOM rồi dùng `DOMSource → DOMResult`, hoặc xác thực và tuần tự hóa ở các bước riêng. Không lấy khả năng chuyển đổi của `Transformer` rồi suy ra validator có cùng quy tắc. [Ma trận Source/Result của Validator](https://docs.oracle.com/en/java/javase/25/docs/api/java.xml/javax/xml/validation/Validator.html#validate(javax.xml.transform.Source,javax.xml.transform.Result)).

Cùng một giao diện `Source` cũng được dùng ở `SchemaFactory.newSchema(source)`. Trong lời gọi ấy, nội dung là **schema**; ở `validator.validate(source)`, nội dung là **tài liệu cần kiểm tra**. Wrapper giống nhau không làm hai vai trò này thay thế cho nhau.

## 5. Chương trình hoàn chỉnh: chỉ kiểm tra, xuất luồng và xuất DOM

Lưu thành `ValidationSourceResultDemo.java`. Chương trình chỉ dùng thư viện chuẩn JDK.

```java
import java.io.StringReader;
import java.io.StringWriter;
import javax.xml.XMLConstants;
import javax.xml.parsers.DocumentBuilderFactory;
import javax.xml.transform.dom.DOMResult;
import javax.xml.transform.dom.DOMSource;
import javax.xml.transform.stream.StreamResult;
import javax.xml.transform.stream.StreamSource;
import javax.xml.validation.Schema;
import javax.xml.validation.SchemaFactory;
import javax.xml.validation.Validator;
import org.w3c.dom.Document;
import org.w3c.dom.Element;
import org.w3c.dom.Node;
import org.xml.sax.InputSource;

public class ValidationSourceResultDemo {
    static final String XSD = """
            <xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
              <xs:element name="invoice">
                <xs:complexType>
                  <xs:sequence>
                    <xs:element name="amount" type="xs:positiveInteger"/>
                  </xs:sequence>
                  <xs:attribute name="currency" type="xs:string" default="VND"/>
                </xs:complexType>
              </xs:element>
            </xs:schema>
            """;
    static final String XML = "<invoice><amount>7</amount></invoice>";

    static StreamSource streamSource(String text) {
        return new StreamSource(new StringReader(text));
    }

    static Validator validator(Schema schema) throws Exception {
        Validator validator = schema.newValidator();
        validator.setProperty(XMLConstants.ACCESS_EXTERNAL_DTD, "");
        validator.setProperty(XMLConstants.ACCESS_EXTERNAL_SCHEMA, "");
        return validator;
    }

    static Document parseXml(String xml) throws Exception {
        DocumentBuilderFactory factory =
                DocumentBuilderFactory.newDefaultInstance();
        factory.setNamespaceAware(true);
        factory.setFeature(XMLConstants.FEATURE_SECURE_PROCESSING, true);
        factory.setFeature(
                "http://apache.org/xml/features/disallow-doctype-decl", true);
        factory.setAttribute(XMLConstants.ACCESS_EXTERNAL_DTD, "");
        factory.setAttribute(XMLConstants.ACCESS_EXTERNAL_SCHEMA, "");
        return factory.newDocumentBuilder()
                .parse(new InputSource(new StringReader(xml)));
    }

    static Element root(Node node) {
        return node instanceof Document document
                ? document.getDocumentElement() : (Element) node;
    }

    static String currency(Node node) {
        String value = root(node).getAttribute("currency");
        String amount = root(node).getElementsByTagName("amount").item(0).getTextContent();
        if (!"7".equals(amount)) {
            throw new AssertionError("Unexpected amount: " + amount);
        }
        return value.isEmpty() ? "<absent>" : value;
    }

    public static void main(String[] args) throws Exception {
        SchemaFactory factory = SchemaFactory.newDefaultInstance();
        factory.setFeature(XMLConstants.FEATURE_SECURE_PROCESSING, true);
        factory.setProperty(XMLConstants.ACCESS_EXTERNAL_DTD, "");
        factory.setProperty(XMLConstants.ACCESS_EXTERNAL_SCHEMA, "");
        Schema schema = factory.newSchema(streamSource(XSD));

        validator(schema).validate(streamSource(XML));
        System.out.println("check-only: VALID");

        StringWriter textOutput = new StringWriter();
        validator(schema).validate(
                streamSource(XML), new StreamResult(textOutput));
        Document streamedResult = parseXml(textOutput.toString());
        System.out.println("stream.currency: " + currency(streamedResult));

        Document inputDom = parseXml(XML);
        DOMResult domOutput = new DOMResult();
        validator(schema).validate(new DOMSource(inputDom), domOutput);
        System.out.println("dom.currency: " + currency(domOutput.getNode()));

        try {
            validator(schema).validate(streamSource(XML), new DOMResult());
            throw new AssertionError("Mismatched Source/Result accepted");
        } catch (IllegalArgumentException expected) {
            System.out.println("stream-to-dom: IllegalArgumentException");
        }
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 ValidationSourceResultDemo.java
java ValidationSourceResultDemo
```

Stdout khi chạy với bộ thực thi có sẵn trong JDK 24:

```text
check-only: VALID
stream.currency: <absent>
dom.currency: VND
stream-to-dom: IllegalArgumentException
```

Cách đọc ví dụ:

1. Schema yêu cầu một `invoice` có `amount` nguyên dương và khai báo thuộc tính `currency` với mặc định `VND`.
2. XML đầu vào không ghi thuộc tính `currency`.
3. Lần đầu chỉ xác thực, không tạo Result.
4. Lần thứ hai dùng đúng cặp `StreamSource → StreamResult`. Nội dung được ghi vào `StringWriter`, sau đó đọc lại để kiểm tra dữ liệu.
5. Lần thứ ba dùng `DOMSource → DOMResult`, lấy nút đầu ra qua `getNode()`.
6. Hàm `currency` đồng thời kiểm tra nội dung `amount` vẫn là `7`; không chỉ in một giá trị không được kiểm chứng.
7. Lần cuối cố ý ghép sai `StreamSource → DOMResult` và kiểm tra ngoại lệ dự kiến.
8. Mỗi lần dùng nguồn luồng, hàm `streamSource` tạo một `StringReader` mới.

Chương trình không ghi tệp hoặc truy cập mạng. Các chuỗi schema và XML được kiểm soát trong mã; parser DOM chặn DOCTYPE và truy cập ngoài để cách tạo DOM được thể hiện rõ.

### Đừng hứa rằng mọi đầu ra đều được bổ sung giống nhau

Kết quả trên minh họa một hành vi quan trọng: với bộ thực thi JDK 24 đã chạy thử, `DOMResult` nhận thuộc tính mặc định `VND`, còn `StreamResult` không có thuộc tính ấy.

API mô tả đầu ra có thể được bổ sung thông tin sau xác thực; không nên mặc định rằng mọi dạng Result luôn có cùng mức bổ sung hoặc cùng hình dạng tài liệu. Nếu ứng dụng phụ thuộc thuộc tính mặc định, hãy kiểm thử đúng cặp Source/Result và bộ thực thi đang triển khai, rồi sử dụng dữ liệu đầu ra thực tế hoặc chuẩn hóa mặc định rõ ràng trong ứng dụng.

Ví dụ giữ stdout gắn với môi trường đã kiểm chứng; không biến sự vắng mặt của thuộc tính trong StreamResult thành một điều kiện bắt buộc đối với mọi provider.

## 6. systemId là ngữ cảnh vị trí, không phải nội dung

System ID có thể giúp thông báo lỗi chỉ ra nguồn và làm URI gốc để phân giải tham chiếu tương đối. Ví dụ minh họa khi ứng dụng đã có đường dẫn schema:

```java
// schemaPath la Path cua nguon schema do ung dung quan ly.
StreamSource schemaSource = new StreamSource(schemaInputStream);
schemaSource.setSystemId(schemaPath.toUri().toString());
```

Ở đây `schemaInputStream` cung cấp nội dung; system ID cho biết ngữ cảnh vị trí. Nếu chỉ truyền URI mà không có luồng hoặc reader, bộ xử lý có thể phải mở nguồn từ vị trí ấy.

Việc đặt system ID không cấp hoặc thu hồi quyền truy cập. Nếu schema có `include`/`import`, cần chính sách resolver và quyền tài nguyên tương ứng. Cũng không truyền một địa chỉ do người dùng tùy ý cung cấp rồi cho rằng wrapper `Source` tự tạo vùng cô lập.

Với Result, system ID có thể mô tả đích hoặc ngữ cảnh đầu ra, tùy loại. Nó không phải một nơi để lấy boolean xác thực hoặc lưu thông báo lỗi. [Ngữ nghĩa system ID của Source](https://docs.oracle.com/en/java/javase/25/docs/api/java.xml/javax/xml/transform/Source.html), [Giao diện Result](https://docs.oracle.com/en/java/javase/25/docs/api/java.xml/javax/xml/transform/Result.html).

## 7. Vòng đời luồng, DOM và đầu ra thất bại

### Chủ động quản lý tài nguyên mà ứng dụng mở

`Source` và `Result` là wrapper, không phải cơ chế quản lý vòng đời chung cho mọi tài nguyên bên trong. Khi ứng dụng mở tệp, dùng `try-with-resources` cho luồng tương ứng; không coi việc tạo wrapper là đã nhận trách nhiệm đóng luồng giúp mình.

Với `StringReader`/`StringWriter` trong ví dụ, dữ liệu ở bộ nhớ. Với tệp hoặc kết nối, còn cần kiểm soát kích thước và thời hạn đọc/ghi.

Không dùng lại một reader đã bị tiêu thụ cho phép xác thực thứ hai. Ngược lại, DOM còn tồn tại trong bộ nhớ, nhưng các nút có thể thay đổi; không đồng thời sửa cây mà validator đang đọc.

### DOMResult không hứa tạo bản sao độc lập

Trong xác thực DOM, bộ thực thi có thể chuyển tiếp cùng nút, sao chép cây hoặc thay đổi nút đầu vào. Nếu cần giữ bản gốc phục vụ mục đích khác, thiết kế sao chép hoặc vòng đời dữ liệu rõ ràng; không chỉ thấy tên `DOMResult` rồi suy ra đầu vào luôn nguyên trạng.

### Có Result không đồng nghĩa đầu ra đã hợp lệ

Quá trình xác thực có thể đã ghi một phần trước khi phát hiện lỗi. Nếu ghi thẳng vào tệp hoặc gửi tiếp cho hệ thống khác, không được coi dữ liệu đã xuất là một tài liệu hợp lệ chỉ vì đích ghi đã có nội dung.

Với tài liệu nhỏ đã giới hạn, có thể ghi vào bộ đệm rồi chỉ sử dụng sau khi xác thực thành công. Với dữ liệu lớn, thiết kế đầu ra tạm và bước công nhận kết quả phù hợp; không giữ mọi tài liệu lớn vô hạn trong `StringWriter`.

Nếu có `ErrorHandler` tùy chỉnh thu thập lỗi mà không ném ngoại lệ, cần kiểm tra trạng thái lỗi đã thu thập trước khi công nhận kết quả. Không chỉ dựa vào việc lời gọi không ném.

### Đầu ra XML không phải bản sao byte của đầu vào

Dù dữ liệu logic tương đương, khai báo XML, khoảng trắng, cách đặt dấu nháy, tiền tố hoặc thứ tự thuộc tính có thể thay đổi khi tuần tự hóa. Không dùng `StreamResult` để hứa bảo toàn nguyên văn một tệp, chữ ký theo byte hoặc định dạng do con người soạn.

Nếu sản phẩm cần một định dạng tuần tự hóa cụ thể, thiết kế bước xuất với cấu hình phù hợp và kiểm thử riêng; `Validator` trước hết có nhiệm vụ xác thực.

## 8. Chọn cặp phù hợp với nhu cầu

| Nhu cầu | Lựa chọn bắt đầu |
|---|---|
| Chỉ kiểm tra XML đọc từ luồng | `StreamSource` và `validate(source)` |
| Kiểm tra rồi nhận XML dạng ký tự | `StreamSource → StreamResult(StringWriter)` |
| Đã có DOM và cần xử lý DOM tiếp | `DOMSource`, có thể kèm `DOMResult` |
| Chuỗi xử lý dùng sự kiện SAX | `SAXSource → SAXResult` |
| Chuỗi xử lý dùng StAX | `StAXSource → StAXResult` hoặc result `null` |
| Có StreamSource nhưng cần một cây DOM | Tạo DOM ở bước riêng, rồi chọn cặp DOM thích hợp |
| Cần boolean hoặc danh sách lỗi | Viết lớp kết quả ứng dụng dựa trên cơ chế lỗi, không dùng Result như báo cáo |

Lựa chọn bắt đầu này không thay thế cấu hình parser, resolver và giới hạn tài nguyên. Nó giúp mỗi bước nhận đúng dạng dữ liệu cần xử lý và tránh chuyển đổi không cần thiết.

## 9. Thực hành

1. Đổi XML thành `<invoice currency="USD"><amount>7</amount></invoice>`. Quan sát thuộc tính được chỉ định rõ ở cả đầu ra luồng và DOM.
2. Bỏ Result ở hai nhánh xuất. Xác định khi nào ứng dụng không còn cần cấp phát bộ đệm hoặc cây đích.
3. Thay `StreamResult` bằng `DOMResult` ở nhánh dùng `StreamSource`. Giải thích vì sao đây là lỗi ghép kiểu API.
4. Cố dùng lại một `StreamSource` có cùng `StringReader` đã đọc. Sau đó sửa bằng cách tạo reader mới, không chỉ tạo wrapper mới.
5. Đổi `amount` thành `0`, xử lý lỗi xác thực và bảo đảm ứng dụng không công nhận đầu ra đã ghi dở là kết quả hợp lệ.
6. Nếu cần giữ nguyên DOM đầu vào, bổ sung bước sao chép có chủ đích và kiểm tra cây gốc sau khi xác thực, thay vì giả định `DOMResult` luôn độc lập.
