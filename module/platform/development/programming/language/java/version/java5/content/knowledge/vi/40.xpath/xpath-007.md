# Ngữ cảnh đánh giá và các dạng nguồn đầu vào

## 1. Một biểu thức cần biết đang đọc cây nào và bắt đầu ở đâu

Khi một truy vấn XPath không trả dữ liệu như mong đợi, nguyên nhân có thể không nằm ở cú pháp. Cùng một biểu thức tương đối có thể cho kết quả khác khi đánh giá trên:

- Toàn bộ `Document`.
- Phần tử gốc của tài liệu.
- Một phần tử nằm sâu trong cây.
- Một XML mới vừa được phân tích từ InputSource.

Cần tách hai khái niệm:

| Khái niệm | Câu hỏi |
| --- | --- |
| Nguồn đầu vào | Lấy dữ liệu XML từ chuỗi ký tự, byte, tệp hay URI nào? |
| Ngữ cảnh đánh giá | Sau khi có mô hình XML, XPath bắt đầu từ nút nào? |

Nguồn dữ liệu được phân tích thành cây; nút ngữ cảnh là điểm mà biểu thức dùng để định vị trong cây đó.

```text
Reader / InputStream / URI
          ↓ phân tích XML
        Document
          ↓ chọn một nút ngữ cảnh
   biểu thức XPath
          ↓
       kết quả
```

Không nhầm việc truyền một chuỗi chứa XML với việc truyền một nút cây đã được tạo.

## 2. Hai họ overload quan trọng của JAXP XPath

API có các dạng đánh giá chính:

```java
// Các chữ ký rút gọn để minh họa.
evaluate(String expression, Object item, QName returnType)
evaluate(String expression, InputSource source, QName returnType)
```

Dạng nhận Object dùng đối tượng làm ngữ cảnh theo mô hình mà bộ cung cấp hỗ trợ. Với mô hình DOM mặc định của JDK, thường truyền `Document` hoặc một `Node` DOM thích hợp.

Dạng nhận InputSource có thêm bước phân tích XML từ nguồn trước khi đánh giá. Nó không chỉ gói một Node đã có.

Các dạng không truyền returnType thường trả String. Việc chọn kiểu kết quả là một quyết định riêng với việc chọn nguồn và ngữ cảnh. Xem [các overload của XPath](https://docs.oracle.com/en/java/javase/21/docs/api/java.xml/javax/xml/xpath/XPath.html).

Với `XPathExpression` đã biên dịch cũng có các dạng đánh giá nhận ngữ cảnh hoặc InputSource. Biên dịch biểu thức không đồng nghĩa đã phân tích và lưu lại nội dung của mọi nguồn sẽ được đưa vào sau đó.

## 3. Document không phải phần tử gốc

Với XML:

```xml
<library>
  <section id="a">
    <book><title>A1</title></book>
  </section>
</library>
```

DOM có cấu trúc khái quát:

```text
Document
    └─ Element library
           └─ Element section
                  └─ Element book
                         └─ Element title
```

Phần tử gốc là `document.getDocumentElement()`, trong ví dụ là library. Bản thân Document là nút bao toàn tài liệu, không phải cùng một nút với library.

Do đó:

```xpath
section
```

- Đánh giá trên Document: tìm section là con trực tiếp của Document; không có trong ví dụ.
- Đánh giá trên Element library: tìm section là con trực tiếp của library; có dữ liệu.

Dùng dấu `/` rõ ràng khi cần đường dẫn từ gốc tài liệu:

```xpath
/library/section
```

Nhưng không thêm dấu đó vào một biểu thức vốn phải bắt đầu từ một book hoặc section đang xử lý.

## 4. Đường dẫn tương đối và tuyệt đối

Giả sử chương trình đã chọn section b làm ngữ cảnh.

### Tương đối từ nút đang truyền vào

```xpath
book
```

chọn các book là con trực tiếp của section b.

```xpath
./book/title
```

cũng diễn đạt việc đi từ ngữ cảnh hiện tại qua book rồi title.

```xpath
@id
```

chọn thuộc tính id của phần tử section đang làm ngữ cảnh.

### Tuyệt đối từ gốc của cây

```xpath
/library/section/book
```

đi từ gốc tài liệu, nên có thể chọn các book ở cả section a lẫn b, dù ngữ cảnh ban đầu đang là section b.

Truyền một Element sâu trong DOM không tạo ra một “tài liệu con độc lập” để đường dẫn tuyệt đối bị giới hạn bên dưới Element đó. Nó vẫn là một nút trong cây mà chương trình đã phân tích.

Nếu cần một cây độc lập, phải chủ động tạo mô hình tài liệu phù hợp; không chỉ thay tham số ngữ cảnh rồi giả định các quan hệ gốc đã thay đổi.

## 5. Phân biệt .// và //

Với section b làm ngữ cảnh:

```xpath
.//book
```

tìm book bên dưới ngữ cảnh đó theo các bước rút gọn tương ứng.

Trong khi:

```xpath
//book
```

bắt đầu từ gốc cây theo cách viết đường dẫn tuyệt đối rút gọn và có thể tìm book ngoài section b.

Điểm này đặc biệt quan trọng khi xử lý từng bản ghi:

```java
// Mã minh họa: section là Element đang xử lý.
NodeList localBooks = (NodeList) xpath.evaluate(
        ".//book", section, XPathConstants.NODESET);
```

Thay nhầm bằng `//book` có thể khiến mỗi lần lặp đều lấy lại sách của toàn tài liệu. Kết quả trông như dữ liệu bị lặp, nhưng lỗi thực sự là phạm vi truy vấn.

Hãy chọn rõ giữa con trực tiếp `book`, hậu duệ `.//book` và truy vấn từ gốc `//book`.

## 6. Dùng DOM có sẵn khi cần kiểm soát parser hoặc truy vấn nhiều lần

Quy trình chủ động:

1. Tạo và cấu hình `DocumentBuilderFactory`.
2. Phân tích nguồn thành `Document`.
3. Tạo XPath và cấu hình namespace/biến nếu cần.
4. Đánh giá nhiều biểu thức trên Document hoặc các nút đã chọn.

```java
// Mã minh họa.
Document document = builder.parse(source);
Node selected = (Node) xpath.evaluate(
        "/library/section[@id='b']", document, XPathConstants.NODE);

String title = xpath.evaluate("string(book/title)", selected);
```

Cần kiểm tra selected có null không nếu dữ liệu thật không bảo đảm section b tồn tại.

Một tập NodeList không tự được dùng như “ngữ cảnh đánh giá trên từng phần tử”. Nếu muốn xử lý từng nút, duyệt tập và truyền mỗi Node cho lần đánh giá tương ứng.

Theo hợp đồng API, DocumentFragment được xử lý như một nút Document khi đánh giá. Đây là quy tắc cho mô hình ngữ cảnh, không phải việc API tự phân tích một chuỗi XML rời thành fragment. Xem [ngữ cảnh của XPathExpression](https://docs.oracle.com/en/java/javase/21/docs/api/java.xml/javax/xml/xpath/XPathExpression.html).

## 7. InputSource mô tả nguồn, không phải cây DOM

`org.xml.sax.InputSource` có thể chứa:

- Luồng ký tự Reader.
- Luồng byte InputStream.
- System identifier, thường là URI nguồn.
- Thông tin encoding và public identifier khi phù hợp.

Thứ tự chọn nguồn theo hợp đồng:

```text
Có character stream?
    → đọc ký tự từ Reader

Nếu không, có byte stream?
    → đọc byte và xử lý encoding tương ứng

Nếu không có cả hai?
    → thử mở nguồn được systemId chỉ tới
```

Xem [InputSource](https://docs.oracle.com/en/java/javase/21/docs/api/java.xml/org/xml/sax/InputSource.html).

### Chuỗi XML trong bộ nhớ

```java
InputSource source = new InputSource(new StringReader(xmlText));
```

`xmlText` là nội dung XML, còn StringReader biến nó thành nguồn ký tự.

Không viết:

```java
// Ví dụ sai nếu xmlText là nội dung "<library>...</library>".
InputSource source = new InputSource(xmlText);
```

Constructor nhận String ở đây dùng String làm **system identifier**, không phải nội dung XML. Việc tạo InputSource chưa tự đọc dữ liệu; parser sẽ quyết định cách mở/đọc khi xử lý nguồn.

### Dữ liệu XML dạng byte

```java
InputSource source = new InputSource(inputStream);
```

Parser đọc byte rồi giải mã theo encoding được cung cấp hoặc cơ chế nhận biết encoding của XML.

Đừng truyền InputStream trực tiếp vào tham số Object của evaluate và mặc định API tự chọn đường parse. Hãy dùng đúng overload InputSource hoặc chủ động parse thành DOM.

## 8. Reader và InputStream khác nhau ở thời điểm giải mã

Nếu truyền Reader, dữ liệu đã được chuyển thành ký tự trước khi XML parser nhận nó. Parser không dùng một khai báo encoding trong nội dung để đảo ngược hoặc sửa cách các byte đã được giải mã.

```text
Byte → lớp giải mã do ứng dụng chọn → Reader → parser XML
```

Nếu truyền InputStream:

```text
Byte → parser XML xác định/dùng encoding → ký tự → cây DOM
```

Điều này giúp quyết định nơi cần sửa khi văn bản bị sai dấu:

- Với Reader, kiểm tra charset dùng ở bước tạo Reader.
- Với InputStream, kiểm tra byte nguồn, BOM, khai báo encoding và cấu hình encoding có được cung cấp không.

Nếu chuyển một String sang byte để tạo lại XML, phải giữ encoding của byte và khai báo trong XML nhất quán. Không dùng một charset bất kỳ rồi giữ nguyên một khai báo encoding mâu thuẫn.

Khi dùng StringReader cho một String đã đúng, không cần mã hóa thành byte rồi giải mã lại chỉ để parser nhận được dữ liệu.

## 9. Tệp, URI và systemId

Với một tệp đã có Path, có thể chủ động mở stream:

```java
// Mã minh họa trong phương thức có thể ném IOException và lỗi parse.
try (InputStream input = Files.newInputStream(path)) {
    InputSource source = new InputSource(input);
    source.setSystemId(path.toUri().toString());
    Document document = builder.parse(source);
    // Đánh giá XPath trên document.
}
```

SystemId có thể cung cấp định danh nguồn và cơ sở để phân giải các tham chiếu tương đối theo cấu hình parser. Nó không phải một Node của tài liệu và không thay đổi điểm bắt đầu của biểu thức tương đối sau parse.

Nếu chỉ cung cấp systemId mà không có Reader/InputStream, parser có thể tự mở URI đó. Vì vậy không truyền một chuỗi URI từ bên ngoài mà chưa có chính sách cho nguồn được phép đọc.

Dùng `Path.toUri()` để biểu diễn URI tệp rõ ràng thay vì tự ghép tiền tố hoặc tự thay dấu gạch chéo của đường dẫn hệ điều hành.

Cấu hình hạn chế DTD/schema ngoài không đồng nghĩa mọi đường API tự mở **nguồn XML chính** đều đã bị chặn. Kiểm soát nguồn chính và kiểm soát tài nguyên mà XML tham chiếu là hai phần cần được xác định riêng.

## 10. Ví dụ đầy đủ: so sánh ngữ cảnh và dạng nguồn

Tệp `XPathContextInputDemo.java`, chạy trên JDK 17 trở lên, không cần thư viện ngoài:

```java
import java.io.ByteArrayInputStream;
import java.io.StringReader;
import java.nio.charset.StandardCharsets;
import javax.xml.XMLConstants;
import javax.xml.parsers.DocumentBuilderFactory;
import javax.xml.xpath.XPath;
import javax.xml.xpath.XPathConstants;
import javax.xml.xpath.XPathExpressionException;
import javax.xml.xpath.XPathFactory;
import org.w3c.dom.Document;
import org.w3c.dom.Element;
import org.xml.sax.InputSource;

public class XPathContextInputDemo {
    private static Document parse(InputSource source) throws Exception {
        DocumentBuilderFactory factory =
                DocumentBuilderFactory.newDefaultInstance();
        factory.setNamespaceAware(true);
        factory.setFeature(XMLConstants.FEATURE_SECURE_PROCESSING, true);
        factory.setAttribute(XMLConstants.ACCESS_EXTERNAL_DTD, "");
        factory.setAttribute(XMLConstants.ACCESS_EXTERNAL_SCHEMA, "");
        return factory.newDocumentBuilder().parse(source);
    }

    public static void main(String[] args) throws Exception {
        String xml = """
                <library>
                  <section id="a">
                    <book><title>A1</title></book>
                    <book><title>A2</title></book>
                  </section>
                  <section id="b">
                    <book><title>B1</title></book>
                  </section>
                </library>
                """;

        Document document = parse(new InputSource(new StringReader(xml)));
        XPath xpath = XPathFactory.newDefaultInstance().newXPath();
        Element section = (Element) xpath.evaluate(
                "/library/section[@id='b']", document, XPathConstants.NODE);

        System.out.println("documentRelative=" + xpath.evaluate(
                "count(section)", document, XPathConstants.NUMBER));
        System.out.println("rootRelative=" + xpath.evaluate(
                "count(section)", document.getDocumentElement(),
                XPathConstants.NUMBER));
        System.out.println("sectionRelative=" + xpath.evaluate(
                "count(book)", section, XPathConstants.NUMBER));
        System.out.println("sectionAbsolute=" + xpath.evaluate(
                "count(/library/section/book)", section, XPathConstants.NUMBER));
        System.out.println("sectionDescendants=" + xpath.evaluate(
                "count(.//book)", section, XPathConstants.NUMBER));
        System.out.println("globalDescendants=" + xpath.evaluate(
                "count(//book)", section, XPathConstants.NUMBER));

        byte[] bytes = xml.getBytes(StandardCharsets.UTF_8);
        Document fromBytes;
        try (ByteArrayInputStream input = new ByteArrayInputStream(bytes)) {
            fromBytes = parse(new InputSource(input));
        }
        System.out.println("byteInput=" + xpath.evaluate(
                "string(/library/section[@id='b']/book/title)", fromBytes));

        // This separate evaluation parses a fresh, trusted in-memory source.
        String direct = xpath.evaluate(
                "string(/library/section[@id='b']/book/title)",
                new InputSource(new StringReader(xml)));
        System.out.println("directInputSource=" + direct);

        System.out.println("constant=" + xpath.evaluate(
                "2 + 3", (Object) null, XPathConstants.NUMBER));
        try {
            xpath.evaluate("/library", (Object) null, XPathConstants.NODE);
        } catch (XPathExpressionException expected) {
            System.out.println("nullTree=XPathExpressionException");
        }
    }
}
```

Biên dịch và chạy:

```shell
javac XPathContextInputDemo.java
java XPathContextInputDemo
```

Kết quả:

```text
documentRelative=0.0
rootRelative=2.0
sectionRelative=1.0
sectionAbsolute=3.0
sectionDescendants=1.0
globalDescendants=3.0
byteInput=B1
directInputSource=B1
constant=5.0
nullTree=XPathExpressionException
```

Diễn giải:

- Document không có section là con trực tiếp; phần tử library có hai section.
- Section b có một book.
- Đường tuyệt đối vẫn tìm được ba book của cả tài liệu.
- `.//book` giữ phạm vi section, còn `//book` tìm từ gốc.
- Nguồn byte được parse thành DOM rồi truy vấn cho B1.
- Overload nhận InputSource cũng cho B1 khi parse một nguồn ký tự mới.
- Biểu thức hằng có thể không cần cây ngữ cảnh.
- Biểu thức truy vấn cây không thể dùng ngữ cảnh Object null trong trường hợp đó.

XML trong ví dụ là nội dung cố định, không có tài nguyên ngoài.

### Một điểm quan trọng về parser trong ví dụ

Hàm `parse` chủ động cấu hình parser nhận biết namespace và giới hạn truy cập DTD/schema ngoài.

Riêng lời gọi `xpath.evaluate(..., new InputSource(...))` minh họa một đường parse khác do API XPath quản lý. Nó **không dùng lại DocumentBuilderFactory cục bộ của hàm parse chỉ vì cả hai nằm trong cùng chương trình**.

Với dữ liệu cần chính sách parser cụ thể, nên chọn một đường mà chính sách đó được cấu hình và xác minh rõ, thường là parse chủ động thành DOM rồi evaluate.

## 11. Không tái sử dụng một stream như một tài liệu chưa đọc

InputSource là đối tượng mô tả; nó không tự lưu toàn bộ XML để phát lại cho mọi lần evaluate.

Sau khi parser đã đọc Reader hoặc InputStream:

- Vị trí đọc có thể đã ở cuối.
- Stream còn có thể đã được parser đóng theo quy trình parse.
- Lần đánh giá tiếp theo trên cùng stream không tự quay lại đầu.

Hợp đồng InputSource nêu việc đóng các stream là một phần thông thường của dọn dẹp cuối parse; không nên cố dùng lại stream đã bàn giao cho parser.

Nếu muốn đánh giá nhiều lần:

- Parse một lần thành Document và dùng lại cây theo giao thức phù hợp.
- Hoặc tạo một InputSource mới với một Reader/InputStream mới cho từng lần parse.

Không chỉ tạo một InputSource mới nhưng vẫn trỏ đến cùng stream đã tiêu thụ rồi coi dữ liệu đã được làm mới.

Với stream tệp do ứng dụng mở, `try-with-resources` vẫn giúp thể hiện vòng đời và dọn dẹp ngay cả khi lỗi xảy ra trước khi parser xử lý xong. Không giả định stream dùng chung với một tác vụ khác sẽ còn mở sau parse.

## 12. Null và các đối tượng “nguồn XML” khác

### Ngữ cảnh null chỉ dùng khi biểu thức không cần nó

```java
// Mã minh họa: ép Object để chọn đúng overload ngữ cảnh.
Object value = xpath.evaluate(
        "2 + 3", (Object) null, XPathConstants.NUMBER);
```

Biểu thức không cần cây nên có thể được đánh giá theo hợp đồng này.

Nhưng:

```java
// Ví dụ lỗi: đường dẫn cần cây tài liệu.
xpath.evaluate("/library", (Object) null, XPathConstants.NODE);
```

không có một Document rỗng tự sinh để truy vấn; có thể nhận XPathExpressionException.

Literal null còn có thể làm người đọc nhầm giữa overload Object và InputSource. Nếu đang kiểm tra hành vi null, viết kiểu ép tường minh để biểu đạt đúng đường API.

### Không phải mọi Source của JAXP đều là InputSource của XPath

JAXP còn có các kiểu như DOMSource, StreamSource và SAXSource trong gói `javax.xml.transform`. Chúng phục vụ hợp đồng nguồn của API biến đổi, không đồng nghĩa mọi đối tượng đó được evaluate(Object) chấp nhận như ngữ cảnh DOM.

Ví dụ, nếu đã có DOMSource, lấy Node thích hợp mà nó chứa để dùng với mô hình DOM; nếu có nguồn byte/ký tự, chuyển qua đường InputSource hoặc parse rõ ràng.

Tên Object trong chữ ký không có nghĩa “mọi đối tượng đều tự được nhận dạng và parse”. Xem [Source trong API transform](https://docs.oracle.com/en/java/javase/21/docs/api/java.xml/javax/xml/transform/Source.html).

## 13. Các yếu tố đi cùng ngữ cảnh

Điểm bắt đầu là một phần của môi trường đánh giá, cùng với:

- NamespaceContext: ánh xạ prefix trong biểu thức sang URI.
- XPathVariableResolver: cung cấp giá trị biến.
- Hàm mở rộng nếu bộ cung cấp và chính sách cho phép.
- Kiểu kết quả mà Java yêu cầu.

Nếu chọn đúng Node mà kết quả vẫn rỗng, hãy kiểm tra namespace thay vì chỉ đổi đường dẫn. Một phần tử có namespace mặc định không tự khớp với tên không prefix của XPath 1.0.

Nếu dùng lại biểu thức đã biên dịch, cần giữ các cấu hình và giá trị biến theo hợp đồng. XPath và XPathExpression không có bảo đảm chia sẻ đồng thời tùy ý; một stream đầu vào cũng không phải tài nguyên có thể cho nhiều lần parse đọc đua.

Với XML bên ngoài, cấu hình giới hạn tài nguyên và quyền truy cập phải áp dụng ở **đường parse thật sự đang chạy**. Xem [JAXP Security Guide](https://docs.oracle.com/en/java/javase/21/security/java-api-xml-processing-jaxp-security-guide.html).

## 14. Bài tập kiểm tra

1. Đổi section được chọn từ b sang a: `count(book)` trở thành 2, nhưng đường tuyệt đối vẫn đếm 3.
2. Đổi ngữ cảnh từ Document sang phần tử library khi đánh giá `count(section)`: vì sao kết quả thay đổi dù cây không đổi?
3. Tạo InputSource bằng `new InputSource(xml)` với xml là nội dung: vì sao không phải cách parse nội dung String?
4. Đánh giá hai lần từ cùng một InputStream đã được bàn giao cho parser: vì sao không được coi đó là nguồn có thể phát lại?
5. Chỉ cấu hình một DocumentBuilderFactory rồi gọi evaluate với InputSource ở nơi khác: cấu hình cục bộ có tự áp dụng cho đường parse ẩn đó không? Không.
6. Cùng một Node section, so sánh `book`, `.//book` và `//book` để chỉ ra phạm vi chọn.

Khi kiểm tra một lời gọi evaluate, hãy ghi rõ **overload đang dùng, nguồn dữ liệu thật, bước parse, nút ngữ cảnh và biểu thức tương đối hay tuyệt đối**. Năm thông tin đó thường giải thích được phần lớn nhầm lẫn về đầu vào.
