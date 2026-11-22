# Đường dẫn, trục, thuộc tính và lựa chọn nút XML

## 1. Nhìn XML như một cây nút

XPath là ngôn ngữ chọn các phần của tài liệu XML. Một biểu thức không chỉ tìm văn bản giống tên thẻ; nó đi theo cấu trúc cây, quan hệ giữa các nút và điều kiện lựa chọn.

Ví dụ cây nội dung:

```text
Document
└── catalog
    ├── section @id="s1"
    │   ├── book @id="b1" @lang="vi"
    │   │   └── title
    │   │       ├── text: "Java "
    │   │       └── em
    │   │           └── text: "Core"
    │   └── book @id="b2" @lang="en"
    │       └── title
    └── section @id="s2"
        └── book @id="b3" @lang="vi"
            └── title
```

Khi viết một đường dẫn, cần trả lời ba câu:

1. Bắt đầu từ nút nào?
2. Đi theo quan hệ nào?
3. Giữ lại những loại nút và điều kiện nào?

Java cung cấp javax.xml.xpath trong module java.xml. Hợp đồng chuẩn của API này hỗ trợ XPath 1.0; đó vẫn là khả năng có trong Java hiện đại. Bài dùng tập cú pháp đó, không mặc định các cú pháp của XPath 2.0/3.x cũng chạy trên bộ đánh giá mặc định.

## 2. Nút tài liệu khác phần tử gốc

Trong DOM, Document đại diện nút tài liệu. Phần tử `catalog` là phần tử gốc bên trong tài liệu, không phải cùng một nút với Document.

Trong XPath:

- `/` chọn nút gốc của cây tài liệu.
- `/catalog` chọn phần tử catalog nằm dưới nút gốc.
- `/catalog/section` chọn các phần tử section là con trực tiếp của catalog.
- `/catalog/section/book` chọn các book ở đúng chuỗi quan hệ đó.

Một đường dẫn có thể chọn nhiều nút. `/catalog/section/book` không chỉ lấy book đầu tiên mà lấy những book phù hợp ở các section được chọn.

XPath làm việc với mô hình nút, không phải chỉ với phần tử. Thuộc tính, nút văn bản, chú thích và chỉ dẫn xử lý cũng có thể được chọn. Khoảng trắng thụt lề của XML còn có thể tạo nút văn bản, tùy dữ liệu và cách phân tích.

## 3. Đường dẫn tuyệt đối và tương đối

### Bắt đầu từ gốc

Đường dẫn có dấu gạch chéo đầu là tuyệt đối trong cây chứa nút ngữ cảnh:

```xpath
/catalog/section/book
```

Nó không có nghĩa “bắt đầu từ phần tử hiện tại rồi tìm catalog”.

### Bắt đầu từ nút ngữ cảnh

Không có dấu gạch chéo đầu:

```xpath
book
```

thường được hiểu là chọn những book con trực tiếp của nút ngữ cảnh.

Nếu ngữ cảnh đang là một section, book có thể chọn các cuốn sách trong section đó. Nếu ngữ cảnh là Document, biểu thức này không tự xuyên qua catalog và section để tìm book.

Các ký hiệu ngắn thường dùng:

| Biểu thức | Ý nghĩa |
| --- | --- |
| `.` | Nút ngữ cảnh hiện tại |
| `..` | Nút cha theo mô hình XPath |
| `./book` | book con trực tiếp của ngữ cảnh |
| `.//book` | book ở các mức bên dưới ngữ cảnh |
| `//book` ở đầu biểu thức | Tìm book từ gốc cây chứa ngữ cảnh |

Đây là nguyên nhân một hàm đã truyền vào section nhưng vẫn lấy sách của cả tài liệu: nó dùng `//book` thay vì `.//book`.

## 4. Một dấu gạch chéo và hai dấu không cùng phạm vi

Dấu `/` giữa các bước nối các bước đường dẫn. Với tên phần tử không ghi trục, mỗi bước mặc định dùng trục child:

```xpath
/catalog/section/book
```

tương đương về ý định chọn phần tử với:

```xpath
/child::catalog/child::section/child::book
```

Cú pháp `//` là viết tắt có bước descendant-or-self. Chẳng hạn:

```xpath
/catalog//book
```

được mở rộng thành:

```xpath
/catalog/descendant-or-self::node()/child::book
```

Nó cho phép tìm book ở nhiều độ sâu dưới catalog, không chỉ đúng dưới section.

Hai dấu gạch chéo tiện lợi khi cấu trúc trung gian thực sự không quan trọng. Nhưng dùng chúng ở mọi bước có thể chọn rộng hơn hợp đồng dữ liệu và làm khó phát hiện cấu trúc XML đã thay đổi.

Nếu yêu cầu chỉ chấp nhận `catalog → section → book`, viết đường dẫn cụ thể giúp thể hiện yêu cầu đó. Nếu cấu trúc cho phép nhiều tầng chứa book, dùng tìm hậu duệ là quyết định có chủ ý.

## 5. Một bước gồm trục, phép kiểm tra nút và bộ lọc

Dạng khái quát:

```text
axis::node-test[predicate]
```

Ví dụ:

```xpath
child::book[@lang='vi']
```

Đọc lần lượt:

1. Đi theo trục child.
2. Chọn phần tử tên book.
3. Giữ lại các phần tử có thuộc tính lang bằng vi.

Những trục thực dụng:

| Trục | Quan hệ được xét |
| --- | --- |
| `child` | Con trực tiếp |
| `parent` | Cha |
| `self` | Chính nút ngữ cảnh |
| `descendant` | Các nút ở dưới qua quan hệ con nhiều mức |
| `descendant-or-self` | Chính nó và các nút bên dưới |
| `ancestor` | Các tổ tiên đi lên |
| `ancestor-or-self` | Chính nó và các tổ tiên |
| `following-sibling` | Những nút cùng cha nằm sau |
| `preceding-sibling` | Những nút cùng cha nằm trước |
| `attribute` | Thuộc tính của phần tử |

Thuộc tính không phải phần tử con. Đi qua child hoặc descendant không tự chọn các thuộc tính như @id.

Hai trục `following` và `preceding` có phạm vi rộng hơn sibling: chúng đi theo vị trí trong tài liệu, không chỉ cùng cha. Chúng cũng có quy tắc loại trừ như following không gồm hậu duệ, preceding không gồm tổ tiên, và không chọn các nút thuộc tính/namespace theo cách đi đó. Khi chỉ muốn cuốn sách cùng section, dùng sibling thể hiện phạm vi rõ hơn.

## 6. Thuộc tính, phần tử và văn bản là các kết quả khác nhau

Chọn phần tử:

```xpath
/catalog/section/book/title
```

Chọn thuộc tính:

```xpath
/catalog/section/book/@id
```

`@` là viết tắt của trục attribute. Dạng dài của `@id` là `attribute::id`.

Chọn các thuộc tính của book:

```xpath
/catalog/section/book/@*
```

Chọn phần tử con bất kỳ:

```xpath
/catalog/section/book/*
```

Ở trục child, dấu sao chọn phần tử, không tự gồm mọi loại nút. Để xét mọi loại nút con theo trục đó, dùng `node()`.

Một số phép kiểm tra nút:

| Phép kiểm tra | Mục tiêu |
| --- | --- |
| `book` | Phần tử đúng tên trên trục phù hợp |
| `*` trên child | Phần tử con bất kỳ |
| `text()` | Nút văn bản |
| `comment()` | Nút chú thích |
| `processing-instruction()` | Nút chỉ dẫn xử lý |
| `node()` | Nút bất kỳ thuộc trục đang xét |

Với:

```xml
<title>Java <em>Core</em></title>
```

`title/text()` chọn các text node con trực tiếp của title; nó không tự lấy text nằm trong em.

Nếu cần giá trị chuỗi tổng hợp của title, `string(title)` theo ngữ cảnh thích hợp cho giá trị nối từ các text node hậu duệ. Trong ví dụ này nó tạo `Java Core`.

Chọn một nút và lấy giá trị chuỗi của nó là hai thao tác có liên hệ, nhưng không nên viết text() như cách thay thế máy móc cho mọi nhu cầu lấy nội dung.

## 7. Bộ lọc điều kiện và vị trí

Lọc theo thuộc tính:

```xpath
/catalog/section/book[@lang='vi']
```

Chọn book có id cụ thể:

```xpath
/catalog/section/book[@id='b2']
```

Kiểm tra thuộc tính tồn tại:

```xpath
/catalog/section/book[@lang]
```

Trong XPath, vị trí bắt đầu từ một:

```xpath
/catalog/section/book[1]
```

chọn book đầu tiên theo bước lựa chọn tại mỗi section, không phải mặc định một book duy nhất cho cả tài liệu.

Khác biệt quan trọng:

| Biểu thức | Với hai section trong ví dụ |
| --- | --- |
| `//book[1]/@id` | b1 và b3: book đầu tiên của từng cha phù hợp |
| `(//book)[1]/@id` | b1: lấy phần tử đầu của toàn kết quả được nhóm |

Không đặt ngoặc chỉ để “dễ đọc hơn” nếu chưa hiểu nó đổi phạm vi áp dụng predicate.

Vị trí còn phụ thuộc hướng trục. Chẳng hạn `preceding-sibling::book[1]` chọn book anh em gần nhất phía trước. Với trục ancestor, `ancestor::*[1]` chọn phần tử tổ tiên gần nhất; nếu bọc tập tổ tiên thành `(ancestor::*)[1]`, việc lấy vị trí đầu theo nhóm lại có thể chọn phần tử tổ tiên ngoài cùng.

Đây là quy tắc của bước trục và predicate, không phải do chỉ số mảng Java. NodeList.item(0) trong Java dùng chỉ số không; đừng trộn nó với [1] của XPath.

## 8. Ví dụ Java chạy được

Chương trình phân tích một XML cố định thành DOM, rồi đánh giá các biểu thức bằng NODESET hoặc NODE theo nhu cầu.

Lưu thành `XPathSelectionDemo.java`:

```java
import java.io.StringReader;
import java.util.StringJoiner;
import javax.xml.XMLConstants;
import javax.xml.parsers.DocumentBuilderFactory;
import javax.xml.xpath.XPath;
import javax.xml.xpath.XPathConstants;
import javax.xml.xpath.XPathFactory;
import org.w3c.dom.Document;
import org.w3c.dom.Node;
import org.w3c.dom.NodeList;
import org.xml.sax.InputSource;

public class XPathSelectionDemo {
    private static Document parse(String xml) throws Exception {
        DocumentBuilderFactory factory =
                DocumentBuilderFactory.newDefaultInstance();
        factory.setNamespaceAware(true);
        factory.setFeature(XMLConstants.FEATURE_SECURE_PROCESSING, true);
        factory.setFeature(
                "http://apache.org/xml/features/disallow-doctype-decl", true);
        factory.setAttribute(XMLConstants.ACCESS_EXTERNAL_DTD, "");
        factory.setAttribute(XMLConstants.ACCESS_EXTERNAL_SCHEMA, "");
        factory.setXIncludeAware(false);
        factory.setExpandEntityReferences(false);

        try (StringReader reader = new StringReader(xml)) {
            return factory.newDocumentBuilder()
                    .parse(new InputSource(reader));
        }
    }

    private static void show(
            XPath xpath,
            Node context,
            String label,
            String expression) throws Exception {
        NodeList nodes = (NodeList) xpath.evaluate(
                expression, context, XPathConstants.NODESET);
        StringJoiner values = new StringJoiner(" | ");
        for (int i = 0; i < nodes.getLength(); i++) {
            values.add(nodes.item(i).getTextContent());
        }
        System.out.println(label + "=" + values);
    }

    public static void main(String[] args) throws Exception {
        String xml = """
                <catalog>
                  <section id="s1">
                    <book id="b1" lang="vi">
                      <title>Java <em>Core</em></title>
                    </book>
                    <book id="b2" lang="en">
                      <title>Deep Java</title>
                    </book>
                  </section>
                  <section id="s2">
                    <book id="b3" lang="vi">
                      <title>XML Basics</title>
                    </book>
                  </section>
                </catalog>
                """;

        Document document = parse(xml);
        XPath xpath = XPathFactory.newInstance().newXPath();

        show(xpath, document, "titles", "/catalog/section/book/title");
        show(xpath, document, "ids", "/catalog/section/book/@id");
        show(xpath, document, "perParentFirst", "//book[1]/@id");
        show(xpath, document, "globalFirst", "(//book)[1]/@id");
        show(xpath, document, "previous",
                "//book[@id='b2']/preceding-sibling::book[1]/@id");
        show(xpath, document, "next",
                "//book[@id='b1']/following-sibling::book[1]/@id");
        show(xpath, document, "section",
                "//book[@id='b2']/ancestor::section/@id");

        Node firstSection = (Node) xpath.evaluate(
                "/catalog/section[@id='s1']",
                document, XPathConstants.NODE);

        show(xpath, firstSection, "relative", ".//book/@id");
        show(xpath, firstSection, "fromRoot", "//book/@id");

        System.out.println("titleValue=" + xpath.evaluate(
                "string(/catalog/section/book[@id='b1']/title)",
                document));
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```shell
javac --release 17 XPathSelectionDemo.java
java XPathSelectionDemo
```

Stdout:

```text
titles=Java Core | Deep Java | XML Basics
ids=b1 | b2 | b3
perParentFirst=b1 | b3
globalFirst=b1
previous=b1
next=b2
section=s1
relative=b1 | b2
fromRoot=b1 | b2 | b3
titleValue=Java Core
```

Những điều chương trình kiểm chứng:

- Cùng một đường dẫn có thể trả nhiều phần tử hoặc nhiều thuộc tính.
- Hai cách dùng [1] có phạm vi khác nhau.
- Trục sibling và ancestor chọn theo quan hệ của nút đang xét.
- Cùng truyền firstSection làm ngữ cảnh nhưng .// và // tạo phạm vi khác nhau.
- Giá trị chuỗi của title bao gồm cả Core bên trong em.

Hàm show chỉ lấy textContent để trình bày những phần tử/thuộc tính được chọn trong bài. Nó không phải bộ tuần tự hóa XML, và không giữ nguyên thẻ em trong dạng văn bản in ra.

Phần parse cấu hình bộ phân tích DOM dựng sẵn của JDK để không cho DOCTYPE và truy cập DTD/schema ngoài. Điều đó giữ ví dụ ở phạm vi dữ liệu XML đã đưa vào thay vì vô tình mở thêm nguồn ngoài. Không bỏ qua lỗi cấu hình rồi vẫn tiếp tục phân tích với giả định các giới hạn đã có hiệu lực.

## 9. Chọn kiểu kết quả đúng với mục tiêu

Khi cần tất cả nút phù hợp:

```java
NodeList nodes = (NodeList) xpath.evaluate(
        expression, document, XPathConstants.NODESET);
```

Khi hợp đồng cần một nút:

```java
Node node = (Node) xpath.evaluate(
        expression, document, XPathConstants.NODE);
```

Đây là các đoạn minh họa với biến đã có. Nếu biểu thức không chọn được nút, kết quả NODE có thể là null; phải xử lý trước khi gọi phương thức trên nó.

Đừng dùng một lần evaluate trả String rồi cho rằng đã thu toàn bộ các nút. Quy tắc chuyển node-set sang chuỗi có thể chỉ lấy giá trị của nút đầu theo thứ tự tài liệu. Khi cần danh sách, yêu cầu NODESET rồi duyệt.

Kết quả rỗng không tự chứng minh XML không có dữ liệu. Còn phải kiểm tra ngữ cảnh, namespace, tên phân biệt hoa/thường, trục và predicate.

Nếu một id phải là duy nhất theo hợp đồng ứng dụng, việc dùng NODE để lấy một kết quả không tự xác minh tính duy nhất. Có thể cần kiểm tra số lượng nút phù hợp trước khi xử lý.

## 10. Namespace thay đổi ý nghĩa tên trong đường dẫn

Xét một tài liệu có namespace mặc định:

```xml
<catalog xmlns="urn:books">
  <section id="s1">
    <book id="b1"/>
  </section>
</catalog>
```

Trong XPath 1.0, tên không có tiền tố trong biểu thức không tự nhận namespace mặc định của XML. Vì vậy `/catalog/section/book` có thể không chọn được những phần tử này dù nhìn tên rất giống.

Cần:

1. Phân tích XML với namespace-aware.
2. Ánh xạ một tiền tố trong ngữ cảnh XPath tới URI `urn:books`.
3. Dùng tiền tố đó trong phép chọn:

```xpath
/c:catalog/c:section/c:book/@id
```

Tiền tố c trong biểu thức không bắt buộc trùng một tiền tố xuất hiện trong tài liệu; URI ánh xạ mới quyết định tên mở rộng.

Thuộc tính id không có tiền tố trong XML trên không tự nhận namespace mặc định của phần tử, nên @id vẫn là tên không namespace.

Bài không triển khai NamespaceContext vì trọng tâm là đường dẫn và trục, nhưng khi XML thật có namespace thì cấu hình này là một phần bắt buộc của việc chọn đúng nút. Không sửa bằng cách bỏ qua namespace toàn bộ nếu nhiều từ vựng XML có thể dùng cùng tên cục bộ.

## 11. Những lỗi thường gặp khi chọn nút

- Dùng `//` khi chỉ muốn con trực tiếp: chọn rộng hơn cấu trúc được chấp nhận.
- Dùng `//book` trong một hàm đáng ra chỉ xét section được truyền vào: phạm vi quay về gốc.
- Dùng `book/id` thay `book/@id`: nhầm phần tử con với thuộc tính.
- Dùng `*` rồi tưởng có cả văn bản hoặc chú thích: cần xét node test.
- Dùng `text()` để lấy mọi nội dung hỗn hợp: chỉ chọn đúng text node trên trục đang xét.
- Cho rằng [0] là phần tử đầu: XPath dùng vị trí bắt đầu từ một.
- Không kiểm tra namespace khi kết quả rỗng.
- Ghép đầu vào người dùng vào predicate bằng chuỗi tùy ý: có thể làm thay đổi biểu thức thay vì chỉ thay giá trị cần so sánh.

Khi điều kiện đến từ dữ liệu bên ngoài, giữ biểu thức có cấu trúc do chương trình kiểm soát và dùng cơ chế biến của XPath với bộ phân giải phù hợp, hoặc một cách xây dựng biểu thức đã được kiểm soát đúng hợp đồng. Không coi việc thêm dấu nháy đơn quanh đầu vào là đủ cho mọi giá trị.

Việc chọn nút không sửa XML. Nếu ứng dụng cần cập nhật DOM, đó là bước khác với quyền sửa và quy tắc hợp lệ riêng; không suy ra từ kết quả lựa chọn rằng tài liệu đã được biến đổi.

## 12. Tự kiểm tra

1. /catalog chọn Document hay phần tử catalog?
2. Với ngữ cảnh là section, .//book và //book có nhất thiết cùng kết quả không?
3. Thuộc tính id có được chọn bằng child::id không?
4. Vì sao //book[1] có thể trả nhiều book?
5. preceding-sibling::book[1] chọn nút gần nhất hay xa nhất phía trước?
6. title/text() có tự lấy văn bản bên trong mọi phần tử con không?
7. Tài liệu có namespace mặc định có tự khiến tên không tiền tố trong XPath nhận namespace đó không?

Đáp án:

1. Chọn phần tử catalog dưới nút gốc tài liệu.
2. Không; một biểu thức tương đối theo section, biểu thức kia bắt đầu từ gốc.
3. Không; dùng @id hoặc attribute::id.
4. Predicate áp dụng trong các bước chọn theo từng cha phù hợp.
5. Gần nhất.
6. Không; cần phân biệt text node trực tiếp với giá trị chuỗi tổng hợp.
7. Không trong mô hình XPath 1.0 đang dùng.

Mỗi biểu thức cần được đọc theo điểm bắt đầu, hướng quan hệ, loại nút và phạm vi bộ lọc. Khi bốn phần đó rõ, kết quả chọn XML trở nên dễ giải thích và kiểm thử hơn.

## Tài liệu đối chiếu

- [javax.xml.xpath — Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.xml/javax/xml/xpath/package-summary.html): khả năng XPath và kiểu kết quả trong Java.
- [XPath 1.0 — W3C](https://www.w3.org/TR/1999/REC-xpath-19991116/): đường dẫn, trục, node test và predicate mà API Java chuẩn hỗ trợ.
- [DocumentBuilderFactory — Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.xml/javax/xml/parsers/DocumentBuilderFactory.html): DOM và cấu hình bộ phân tích.
