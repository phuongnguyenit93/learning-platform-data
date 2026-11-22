# XPath trong JAXP và truy vấn tài liệu XML

## 1. XPath giải quyết vấn đề gì?

Một tài liệu XML là cây các nút: phần tử, thuộc tính, văn bản và một số loại nút khác. Nếu muốn tìm các phần tử thỏa điều kiện, ta có thể tự đi qua cây DOM bằng các vòng lặp.

Ví dụ yêu cầu:

> Lấy những sách trong catalog có giá từ 20 trở lên, rồi đọc tiêu đề của từng sách.

Nếu tự duyệt DOM, mã phải kiểm tra phần tử cha, tên phần tử con, thuộc tính và nội dung văn bản. XPath cho phép mô tả **phần dữ liệu muốn chọn** bằng một biểu thức đường dẫn và điều kiện lọc.

```xpath
/catalog/book[number(price) >= 20]
```

Biểu thức này không chạy một truy vấn cơ sở dữ liệu. Nó được đánh giá trên cây XML trong ngữ cảnh mà chương trình cung cấp.

XPath cũng không tự sửa XML. Nó chọn nút hoặc tính một kết quả; nếu muốn cập nhật cây DOM, mã Java có thể thao tác các nút sau đó bằng API DOM.

## 2. JAXP đặt XPath ở đâu trong chương trình Java?

JAXP là Java API for XML Processing, bộ API xử lý XML của Java. Trong đó, gói `javax.xml.xpath` cung cấp API tạo, biên dịch và đánh giá biểu thức XPath.

Luồng cơ bản:

```text
XML đầu vào
    ↓ parser
Cây DOM: Document
    ↓ XPath + ngữ cảnh + biến/namespace
Đánh giá biểu thức
    ↓
Tập nút, một nút, chuỗi, số hoặc boolean
    ↓
Mã Java xử lý kết quả
```

Các API này vẫn nằm trong module `java.xml` trên JDK hiện đại. Tên gói `javax.xml.*` là tên API đúng trong Java SE; không tự đổi thành `jakarta.xml.*`.

API XPath chuẩn của JAXP hỗ trợ mô hình XPath 1.0. Không mặc định rằng JDK mới hơn sẽ tự hiểu mọi biểu thức XPath 2.0 hoặc 3.1. Nếu cần tính năng của một phiên bản khác, phải chọn và kiểm tra bộ máy xử lý tương ứng. Xem [gói javax.xml.xpath](https://docs.oracle.com/en/java/javase/21/docs/api/java.xml/javax/xml/xpath/package-summary.html).

Với một ứng dụng dùng module khai báo, cấu hình tương ứng có thể cần:

```java
module xpath.demo {
    requires java.xml;
}
```

Ví dụ chạy bằng classpath bên dưới không cần tạo `module-info.java`.

## 3. Những đối tượng chính

| Đối tượng | Trách nhiệm |
| --- | --- |
| `DocumentBuilderFactory` | Cấu hình parser tạo cây DOM |
| `Document` | Cây XML đã được phân tích |
| `XPathFactory` | Tạo đối tượng XPath |
| `XPath` | Môi trường đánh giá: namespace, biến và biểu thức |
| `XPathExpression` | Biểu thức đã được biên dịch |
| `XPathConstants` | Các kiểu kết quả cho API evaluate truyền thống |

Ví dụ tạo môi trường XPath bằng bộ cung cấp mặc định của JDK:

```java
XPath xpath = XPathFactory.newDefaultInstance().newXPath();
```

`newInstance()` cũng là API hợp lệ và có cơ chế tìm bộ cung cấp theo cấu hình JAXP. `newDefaultInstance()` chọn triển khai mặc định tích hợp, giúp ví dụ không phụ thuộc một bộ cung cấp khác được cài ngoài ý muốn.

Việc tạo XPath không thay cho việc phân tích XML. Trong ví dụ, chương trình chủ động tạo DOM trước rồi truy vấn lại cây đó nhiều lần.

## 4. Đọc các thành phần của một biểu thức

Giả sử tài liệu có dạng:

```xml
<catalog>
  <book id="b1">
    <title>Java Basics</title>
    <price>15</price>
  </book>
  <book id="b2">
    <title>Java Concurrency</title>
    <price>35</price>
  </book>
</catalog>
```

Một số biểu thức:

| Biểu thức | Ý nghĩa |
| --- | --- |
| `/catalog/book` | Chọn các book là con trực tiếp của catalog ở gốc |
| `/catalog/book/title` | Chọn các phần tử title của những book đó |
| `/catalog/book[@id='b2']` | Chọn book có thuộc tính id bằng b2 |
| `/catalog/book[number(price) >= 20]` | Chọn book có giá chuyển thành số và đạt điều kiện |
| `count(/catalog/book)` | Đếm số book |
| `string(/catalog/book[@id='b2']/title)` | Lấy giá trị chuỗi của title được chọn |
| `boolean(/catalog/book[@id='b2'])` | Kiểm tra tập nút có phần tử không |

Trong đó:

- `/` phân tách bước đường dẫn; dấu đầu tiên chỉ đường dẫn bắt đầu từ gốc.
- `book`, `title` là tên phần tử, có phân biệt hoa/thường.
- `@id` chọn thuộc tính.
- `[...]` là điều kiện lọc.
- `number`, `string`, `count`, `boolean` là các hàm XPath.

Đây là cú pháp XPath 1.0 đang được JAXP hỗ trợ, không phải cú pháp Java. Chuỗi Java chứa biểu thức phải tuân thủ cả quy tắc literal Java và quy tắc XPath bên trong.

## 5. Ngữ cảnh quyết định điểm bắt đầu

Mỗi lần đánh giá có một đối tượng ngữ cảnh, thường là `Document` hoặc một `Node` trong DOM.

Với ngữ cảnh là toàn Document:

```xpath
/catalog/book
```

chọn các sách theo đường dẫn tuyệt đối.

Với ngữ cảnh là một phần tử book đã tìm được:

```xpath
string(title)
```

đọc tiêu đề nằm dưới **book hiện tại**.

Không thêm dấu `/` vào mọi biểu thức theo thói quen. Một đường dẫn tuyệt đối quay về gốc của cây; đường dẫn tương đối bắt đầu từ nút ngữ cảnh.

Cũng phân biệt:

- `title`: title là con trực tiếp của ngữ cảnh.
- `.//title`: title ở các cấp hậu duệ bên dưới ngữ cảnh.
- `//title`: cách viết tìm từ gốc theo các bước rút gọn tương ứng, không chỉ một con trực tiếp.

Dùng `//` ở mọi nơi có thể chọn thêm những phần tử cùng tên ở vùng không mong muốn. Khi cấu trúc tài liệu đã rõ, đường dẫn cụ thể thường dễ kiểm tra hơn.

Không truyền ngữ cảnh null cho một biểu thức cần cây tài liệu rồi mong XPath tự tìm XML. Xem [hợp đồng ngữ cảnh của XPath](https://docs.oracle.com/en/java/javase/21/docs/api/java.xml/javax/xml/xpath/XPath.html).

## 6. Chọn đúng kiểu kết quả

API `evaluate(expression, context, returnType)` truyền thống nhận một hằng trong `XPathConstants`:

| returnType | Kiểu Java thường nhận | Khi dùng |
| --- | --- | --- |
| `NODESET` | `NodeList` | Cần duyệt mọi nút khớp |
| `NODE` | `Node` | Cần một nút, có thể không có |
| `STRING` | `String` | Cần giá trị chuỗi |
| `NUMBER` | `Double` | Cần kết quả số theo XPath |
| `BOOLEAN` | `Boolean` | Cần kết quả logic |

Nếu gọi dạng `evaluate(expression, context)` không khai báo kiểu kết quả, kết quả là String.

Một khác biệt quan trọng:

```java
// Mã minh họa.
String title = xpath.evaluate("/catalog/book/title", document);
```

Dòng này không trả về danh sách mọi tiêu đề. Việc chuyển một tập nút thành chuỗi trong XPath 1.0 lấy giá trị chuỗi của nút đầu theo quy tắc thứ tự tài liệu. Nếu cần mọi tiêu đề, hãy lấy `NODESET` rồi duyệt.

Khi không có nút phù hợp:

- Kết quả `NODESET` là tập rỗng.
- Kết quả `NODE` có thể là null.
- Chuyển tập rỗng thành String cho chuỗi rỗng.
- Chuyển tập rỗng thành Boolean cho false.

Do đó chuỗi rỗng không tự phân biệt “không tìm thấy title” với “đã tìm thấy title nhưng nội dung rỗng”. Nếu việc tồn tại quan trọng, truy vấn sự tồn tại hoặc nút trước rồi đọc nội dung.

Số theo XPath 1.0 dùng mô hình số dấu phẩy động. Với giá trị thập phân cần quy tắc tài chính chính xác, nên lấy văn bản và chuyển sang kiểu số miền nghiệp vụ thay vì coi kết quả Double là phép tính tiền tệ chính xác.

## 7. Ví dụ đầy đủ: phân tích một lần, truy vấn nhiều kiểu

Tệp `JaxpXPathDemo.java`, chạy trên JDK 17 trở lên và không cần thư viện ngoài:

```java
import java.io.StringReader;
import java.util.Map;
import javax.xml.XMLConstants;
import javax.xml.namespace.QName;
import javax.xml.parsers.DocumentBuilderFactory;
import javax.xml.xpath.XPath;
import javax.xml.xpath.XPathConstants;
import javax.xml.xpath.XPathExpression;
import javax.xml.xpath.XPathFactory;
import org.w3c.dom.Document;
import org.w3c.dom.Element;
import org.w3c.dom.NodeList;
import org.xml.sax.InputSource;

public class JaxpXPathDemo {
    public static void main(String[] args) throws Exception {
        String xml = """
                <catalog>
                  <book id="b1">
                    <title>Java Basics</title>
                    <price>15</price>
                  </book>
                  <book id="b2">
                    <title>Java Concurrency</title>
                    <price>35</price>
                  </book>
                  <book id="b3">
                    <title>XML in Java</title>
                    <price>25</price>
                  </book>
                </catalog>
                """;

        DocumentBuilderFactory parser =
                DocumentBuilderFactory.newDefaultInstance();
        parser.setNamespaceAware(true);
        parser.setFeature(XMLConstants.FEATURE_SECURE_PROCESSING, true);
        parser.setAttribute(XMLConstants.ACCESS_EXTERNAL_DTD, "");
        parser.setAttribute(XMLConstants.ACCESS_EXTERNAL_SCHEMA, "");
        Document document = parser.newDocumentBuilder().parse(
                new InputSource(new StringReader(xml)));

        XPath xpath = XPathFactory.newDefaultInstance().newXPath();
        Map<QName, Object> variables = Map.of(
                new QName("minPrice"), 20.0,
                new QName("id"), "b2");
        xpath.setXPathVariableResolver(variables::get);

        XPathExpression selection = xpath.compile(
                "/catalog/book[number(price) >= $minPrice]");
        NodeList books = (NodeList) selection.evaluate(
                document, XPathConstants.NODESET);

        XPathExpression title = xpath.compile("string(title)");
        for (int i = 0; i < books.getLength(); i++) {
            Element book = (Element) books.item(i);
            System.out.println("selected=" + book.getAttribute("id")
                    + ":" + title.evaluate(book));
        }

        Double count = (Double) xpath.evaluate(
                "count(/catalog/book)", document, XPathConstants.NUMBER);
        Boolean found = (Boolean) xpath.evaluate(
                "/catalog/book[@id=$id]", document, XPathConstants.BOOLEAN);
        String missing = xpath.evaluate(
                "string(/catalog/book[@id='missing']/title)", document);

        System.out.println("total=" + count.intValue());
        System.out.println("found=" + found);
        System.out.println("missing=[" + missing + "]");
    }
}
```

Biên dịch và chạy:

```shell
javac JaxpXPathDemo.java
java JaxpXPathDemo
```

Kết quả:

```text
selected=b2:Java Concurrency
selected=b3:XML in Java
total=3
found=true
missing=[]
```

Giải thích:

- Biến `minPrice` bằng 20; b2 giá 35 và b3 giá 25 được chọn.
- `selection` trả NodeList để duyệt cả hai sách.
- `title.evaluate(book)` dùng mỗi book làm ngữ cảnh tương đối.
- Hàm `count` trả số 3; ví dụ nhỏ chuyển kết quả đếm sang int để in.
- Biến `id` bằng b2, nên truy vấn boolean trả true.
- Sách có id missing không tồn tại; chuyển tập title rỗng thành chuỗi cho `""`, được in giữa hai dấu ngoặc thành `[]`.

Mã dùng text block Java để giữ XML dễ đọc. XML ở đây là dữ liệu cố định trong chương trình.

## 8. Biến XPath giữ dữ liệu tách khỏi cấu trúc biểu thức

Thay vì nối trực tiếp dữ liệu vào câu truy vấn:

```java
// Mã minh họa cần tránh với giá trị đầu vào tùy ý.
String expression = "/catalog/book[@id='" + inputId + "']";
```

có thể viết biểu thức cố định:

```xpath
/catalog/book[@id=$id]
```

và cung cấp biến qua `XPathVariableResolver`.

Trong ví dụ:

```java
Map<QName, Object> variables = Map.of(
        new QName("minPrice"), 20.0,
        new QName("id"), "b2");
xpath.setXPathVariableResolver(variables::get);
```

Dữ liệu như dấu nháy trong id không tự trở thành cú pháp của biểu thức khi được truyền như một giá trị biến.

Biến là giá trị, không phải một mảnh đường dẫn được chèn vào cú pháp. Không truyền một chuỗi `"book/title"` vào biến rồi mặc định XPath sẽ thực thi nó như một đường dẫn.

Nếu biểu thức tham chiếu một biến mà resolver không cung cấp, việc đánh giá có thể ném `XPathExpressionException`. Giá trị biến phải ổn định trong suốt một lần đánh giá; xem [cơ chế biến của XPath](https://docs.oracle.com/en/java/javase/21/docs/api/java.xml/javax/xml/xpath/XPath.html).

## 9. Namespace là một phần danh tính phần tử

Một tài liệu khác có thể dùng namespace mặc định:

```xml
<catalog xmlns="urn:books">
  <book id="b1">
    <title>Java Basics</title>
  </book>
</catalog>
```

Lúc này tên phần tử gồm cả namespace URI `urn:books`. Với XPath 1.0, đường dẫn không prefix:

```xpath
/catalog/book
```

không tự có nghĩa “dùng namespace mặc định của XML”.

Cần:

1. Phân tích DOM với `namespaceAware=true`.
2. Cài `NamespaceContext` cho XPath để ánh xạ một prefix, ví dụ `b`, tới `urn:books`.
3. Viết đường dẫn dùng prefix:

```xpath
/b:catalog/b:book
```

Prefix trong XPath do môi trường truy vấn đặt; nó không bắt buộc trùng với một prefix viết trong tài liệu. Điều cần khớp là namespace URI và tên cục bộ.

Thuộc tính không prefix như `id` trong ví dụ không tự mang namespace mặc định của phần tử. Vì vậy điều kiện thường vẫn là `[@id='b1']`.

Không loại bỏ namespace khỏi dữ liệu chỉ để một biểu thức cũ trả kết quả. Nếu truy vấn rỗng bất ngờ, namespace là một trong những thông tin đầu tiên cần kiểm tra.

## 10. Parser và XPath có trách nhiệm khác nhau

XPath được đánh giá sau khi XML đã được phân tích thành mô hình dữ liệu. Nó không thay thế việc kiểm soát parser.

Ví dụ chủ động cấu hình:

- Nhận biết namespace.
- Bật `FEATURE_SECURE_PROCESSING`.
- Không cho parser truy cập DTD hoặc schema bên ngoài qua các thuộc tính truy cập tương ứng.

Các lựa chọn này phù hợp với XML minh họa không cần tài nguyên ngoài. Chúng không phải lời khẳng định mọi loại XML hoặc mọi nguồn dữ liệu đều có cùng yêu cầu.

Nếu ứng dụng xử lý XML bên ngoài, cần giới hạn kích thước/độ phức tạp và xác định rõ có cho phép DTD, schema hoặc tham chiếu tài nguyên nào không. Cấu hình parser đúng không sửa được biểu thức XPath sai; biểu thức đúng cũng không sửa được cấu hình phân tích XML thiếu kiểm soát. Xem [JAXP Security Guide](https://docs.oracle.com/en/java/javase/21/security/java-api-xml-processing-jaxp-security-guide.html).

Khi một cấu hình cần thiết không được hỗ trợ, không bắt lỗi rồi bỏ qua để tiếp tục với giả định cấu hình đã có hiệu lực. Ví dụ để lỗi cấu hình đi lên rõ ràng.

Với nhiều truy vấn trên cùng tài liệu, phân tích DOM một lần còn giúp các lần đánh giá dùng cùng một cây. Đánh giá trực tiếp từ InputSource nhiều lần có thể dẫn đến việc phân tích lại và cần quản lý cấu hình parser theo đường API đó.

## 11. Lỗi, hiệu năng và vòng đời đối tượng

### Không tìm thấy dữ liệu không nhất thiết là ngoại lệ

Tập kết quả rỗng có thể là kết quả hợp lệ. Nếu ứng dụng bắt buộc có đúng một phần tử, hãy kiểm tra số lượng và báo thiếu hoặc trùng theo yêu cầu.

Không dùng chuỗi rỗng để âm thầm thay thế mọi trường bắt buộc.

### Biểu thức sai hoặc biến chưa có

Cú pháp XPath không hợp lệ, biến thiếu hoặc chuyển kết quả không phù hợp có thể tạo `XPathExpressionException`. Cần giữ biểu thức hoặc định danh truy vấn để chẩn đoán cùng thông tin ngữ cảnh phù hợp.

Ngoài ra, XML không hợp lệ có thể lỗi ngay ở bước parse, trước khi có bất kỳ lần đánh giá XPath nào.

### Compile có ích khi dùng lại, nhưng không làm đối tượng tự an toàn đồng thời

`XPathExpression` là biểu thức đã biên dịch, có thể dùng lại theo giao thức hợp lệ. Tuy nhiên XPath và XPathExpression không có hợp đồng dùng chung đồng thời tùy ý hoặc gọi lồng tái nhập.

Không đặt một XPathExpression trong biến static rồi để mọi request cùng gọi evaluate mà không có thiết kế đồng bộ hoặc phân chia đối tượng. Xem [hợp đồng XPathExpression](https://docs.oracle.com/en/java/javase/21/docs/api/java.xml/javax/xml/xpath/XPathExpression.html).

Việc cây DOM có được đọc/sửa đồng thời an toàn hay không cũng cần được xác định riêng.

### DOM giữ cây trong bộ nhớ

XPath trên DOM thuận tiện cho các truy vấn lặp trên một cây vừa phải. Với XML rất lớn, phải xét chi phí phân tích và giữ toàn bộ cây; một mô hình đọc luồng có thể phù hợp hơn nếu chỉ cần xử lý tuần tự.

Dùng XPath không tự làm việc đọc XML trở thành xử lý luồng hoặc miễn chi phí bộ nhớ.

## 12. Thực hành kiểm tra truy vấn

1. Đổi `minPrice` thành 30: chỉ b2 được chọn.
2. Đổi `id` thành một id không tồn tại: truy vấn boolean trả false.
3. Thêm hai book cùng một id: vì sao một truy vấn String không đủ để xác nhận tính duy nhất? Nó chỉ tạo một giá trị chuỗi theo quy tắc chuyển đổi, không tự kiểm tra số phần tử.
4. Thêm namespace mặc định vào catalog: đường dẫn không prefix không còn có cùng nghĩa; cần cấu hình namespace của truy vấn.
5. Đổi giá thành văn bản không phải số: `number(price)` không biến dữ liệu đó thành giá hợp lệ. Cần kiểm tra dữ liệu nếu giá là trường bắt buộc.
6. Dùng `string(title)` với mỗi book và với toàn Document: kết quả khác vì ngữ cảnh bắt đầu khác.

Mỗi truy vấn nên được kiểm tra theo chuỗi **cây XML thật → namespace → ngữ cảnh → biểu thức → kiểu kết quả → điều kiện tồn tại/số lượng mà ứng dụng yêu cầu**.
