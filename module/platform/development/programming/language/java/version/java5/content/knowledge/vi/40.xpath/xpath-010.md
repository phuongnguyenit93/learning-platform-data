# Không gian tên mặc định của XML và tiền tố trong truy vấn

## 1. Vì sao nhìn thấy phần tử nhưng XPath không tìm được?

Giả sử tài liệu có:

```xml
<catalog xmlns="urn:catalog">
  <book id="b1">
    <title>Core Java</title>
  </book>
</catalog>
```

Một truy vấn dễ được viết là:

```xpath
/catalog/book
```

Nhưng khi XML được phân tích có nhận biết namespace và đánh giá bằng XPath 1.0 của JAXP, truy vấn trên không khớp các phần tử đó.

Nguyên nhân không phải XML không có book. Nguyên nhân là:

- Phần tử book thuộc namespace `urn:catalog`.
- Tên `book` không prefix trong bước chọn phần tử của XPath 1.0 chỉ phần tử không có namespace.
- Namespace mặc định khai báo trong XML không tự trở thành namespace mặc định cho các tên không prefix của biểu thức XPath.

Cần nối đúng **danh tính phần tử trong XML** với **cách viết tên trong truy vấn**.

## 2. Danh tính phần tử gồm URI và tên cục bộ

Một tên mở rộng có thể hình dung bằng cặp:

```text
(namespace URI, local name)
```

Với:

```xml
<book xmlns="urn:catalog"/>
```

danh tính phần tử là:

```text
("urn:catalog", "book")
```

Còn:

```xml
<book/>
```

ở một ngữ cảnh không có namespace mặc định thì danh tính là:

```text
(không namespace, "book")
```

Hai phần tử cùng có tên cục bộ book nhưng không có cùng tên mở rộng.

Namespace URI là định danh, không phải một yêu cầu tự tải nội dung từ mạng. Một URI namespace cũng không tự là địa chỉ schema cần đọc. Các khái niệm này được phân biệt trong [Namespaces in XML](https://www.w3.org/TR/xml-names/).

Khi so khớp namespace, cần URI đúng theo định danh của dữ liệu. Không tự thêm dấu gạch chéo, đổi chữ hoa/thường hoặc “chuẩn hóa URL” rồi coi vẫn là cùng namespace.

## 3. Prefix là tên viết tắt, không phải danh tính cuối cùng

Ba phần tử sau có thể mang cùng danh tính namespace và tên cục bộ:

```xml
<book xmlns="urn:catalog"/>
```

```xml
<a:book xmlns:a="urn:catalog"/>
```

```xml
<x:book xmlns:x="urn:catalog"/>
```

Prefix `a` và `x` chỉ là các ánh xạ trong tài liệu tới cùng URI.

Vì vậy một truy vấn không cần sao chép prefix tài liệu. Có thể tự chọn prefix `c`:

```xpath
/c:catalog/c:book
```

miễn là môi trường XPath biết:

```text
c → urn:catalog
```

Đây là lợi ích quan trọng: nếu bên cung cấp XML đổi cách viết từ namespace mặc định sang prefix x nhưng giữ nguyên URI và cấu trúc, truy vấn dùng c vẫn có thể giữ nguyên.

Nếu URI đổi thật, đó là thay đổi danh tính dữ liệu; không coi việc giữ nguyên local name là đủ để truy vấn tiếp tục đúng.

## 4. Tại sao đặt namespace mặc định trong NamespaceContext chưa đủ?

Một nhầm lẫn phổ biến là chỉ ánh xạ prefix rỗng trong NamespaceContext:

```text
"" → urn:catalog
```

rồi tiếp tục dùng `/catalog/book`.

Với name test không prefix của XPath 1.0, namespace mặc định không được áp dụng như cách XML áp dụng cho tên phần tử. Muốn chọn phần tử có namespace, dùng một prefix thực sự trong biểu thức và ánh xạ prefix đó.

```text
XML:
xmlns="urn:catalog"
        ↓ phần tử có namespace URI

XPath:
c:catalog
        ↓ tra c qua NamespaceContext
urn:catalog + catalog
```

Quy tắc tên trong XPath 1.0 được nêu trong [Node Tests của XPath](https://www.w3.org/TR/1999/REC-xpath-19991116/#node-tests). Đây là ngữ nghĩa vẫn áp dụng cho bộ máy XPath 1.0 của JAXP hiện hành.

Không suy ra khả năng đặt namespace mặc định cho biểu thức của một công cụ XPath phiên bản khác cũng tồn tại giống hệt trong API đang dùng.

## 5. Cấu hình đúng ở hai tầng

### Tầng parser: tạo DOM có nhận biết namespace

```java
DocumentBuilderFactory parser =
        DocumentBuilderFactory.newDefaultInstance();
parser.setNamespaceAware(true);

Document document = parser.newDocumentBuilder().parse(source);
```

Phải đặt cấu hình trước khi tạo parser và phân tích tài liệu. Đổi cấu hình factory sau khi đã có Document không tự dựng lại các namespace của cây cũ.

Xem [DocumentBuilderFactory.setNamespaceAware](https://docs.oracle.com/en/java/javase/21/docs/api/java.xml/javax/xml/parsers/DocumentBuilderFactory.html#setNamespaceAware(boolean)).

### Tầng XPath: ánh xạ prefix của truy vấn

```java
// Mã minh họa: namespaces triển khai NamespaceContext.
XPath xpath = XPathFactory.newDefaultInstance().newXPath();
xpath.setNamespaceContext(namespaces);

NodeList books = (NodeList) xpath.evaluate(
        "/c:catalog/c:book",
        document,
        XPathConstants.NODESET);
```

Cấu hình parser không tự cài prefix c cho XPath. NamespaceContext của XPath cũng không sửa được một cây đã được phân tích mà mất thông tin namespace.

Nên hoàn tất ánh xạ trước khi compile biểu thức. Khi thay đổi cấu hình, tạo hoặc biên dịch lại biểu thức theo môi trường mới thay vì dựa vào giả định mọi biểu thức đã có tự thay đổi theo ý muốn.

Xem [XPath.setNamespaceContext](https://docs.oracle.com/en/java/javase/21/docs/api/java.xml/javax/xml/xpath/XPath.html#setNamespaceContext(javax.xml.namespace.NamespaceContext)).

## 6. Thuộc tính không prefix là trường hợp khác

Xét:

```xml
<book xmlns="urn:catalog"
      xmlns:m="urn:metadata"
      id="b1"
      m:status="active"/>
```

Danh tính tương ứng:

| Tên viết trong XML | Namespace URI | Tên cục bộ |
| --- | --- | --- |
| book | `urn:catalog` | book |
| id | Không namespace | id |
| m:status | `urn:metadata` | status |

Namespace mặc định áp dụng cho tên phần tử không prefix, nhưng không tự áp dụng cho thuộc tính không prefix như id.

Vì vậy truy vấn phù hợp là:

```xpath
/c:catalog/c:book/@id
```

và, nếu ánh xạ meta tới `urn:metadata`:

```xpath
/c:catalog/c:book/@meta:status
```

Dùng `@c:id` sẽ yêu cầu một thuộc tính id thuộc `urn:catalog`, khác với thuộc tính id trong XML trên.

Cũng không mặc định thuộc tính status cùng namespace với phần tử book chỉ vì nó nằm trên cùng một thẻ. Prefix của thuộc tính xác định namespace riêng của thuộc tính đó.

## 7. NamespaceContext phải tuân thủ hợp đồng

Một NamespaceContext cài cho XPath cung cấp việc tra prefix ↔ URI. Hợp đồng có những điểm quan trọng:

- `getNamespaceURI(prefix)` nhận prefix không có ánh xạ thì trả `XMLConstants.NULL_NS_URI`, tức chuỗi rỗng, không tự bịa một URI.
- Prefix hoặc URI null ở các phương thức tương ứng phải bị từ chối bằng `IllegalArgumentException`.
- Prefix dành riêng `xml` và `xmlns` có URI chuẩn trong XMLConstants.
- `getPrefix(uri)` có thể trả một prefix phù hợp, hoặc null khi không có.
- `getPrefixes(uri)` trả iterator của các prefix phù hợp; không cho người gọi sửa ánh xạ qua iterator đó.

Một URI có thể có nhiều prefix, còn một prefix trong cùng môi trường ánh xạ tới một URI. Xem [NamespaceContext](https://docs.oracle.com/en/java/javase/21/docs/api/java.xml/javax/xml/namespace/NamespaceContext.html).

Trong truy vấn ứng dụng, ánh xạ tường minh, ổn định thường dễ kiểm tra hơn việc cố suy ra prefix từ một thẻ bất kỳ trong XML. Prefix trong XML có phạm vi và có thể bị gán lại ở vùng con.

## 8. Ví dụ đầy đủ: namespace mặc định, thuộc tính và vùng hủy namespace

Tệp `DefaultNamespaceXPathDemo.java`, chạy trên JDK 17 trở lên, không cần thư viện ngoài:

```java
import java.io.StringReader;
import java.util.Iterator;
import java.util.Map;
import javax.xml.XMLConstants;
import javax.xml.namespace.NamespaceContext;
import javax.xml.parsers.DocumentBuilderFactory;
import javax.xml.xpath.XPath;
import javax.xml.xpath.XPathConstants;
import javax.xml.xpath.XPathFactory;
import org.w3c.dom.Document;
import org.xml.sax.InputSource;

public class DefaultNamespaceXPathDemo {
    private static final class QueryNamespaces implements NamespaceContext {
        private final Map<String, String> bindings = Map.of(
                "", XMLConstants.NULL_NS_URI,
                "c", "urn:catalog",
                "meta", "urn:metadata",
                XMLConstants.XML_NS_PREFIX, XMLConstants.XML_NS_URI,
                XMLConstants.XMLNS_ATTRIBUTE, XMLConstants.XMLNS_ATTRIBUTE_NS_URI);

        @Override
        public String getNamespaceURI(String prefix) {
            if (prefix == null) {
                throw new IllegalArgumentException("prefix must not be null");
            }
            return bindings.getOrDefault(prefix, XMLConstants.NULL_NS_URI);
        }

        @Override
        public String getPrefix(String namespaceURI) {
            Iterator<String> prefixes = getPrefixes(namespaceURI);
            return prefixes.hasNext() ? prefixes.next() : null;
        }

        @Override
        public Iterator<String> getPrefixes(String namespaceURI) {
            if (namespaceURI == null) {
                throw new IllegalArgumentException("namespace URI must not be null");
            }
            return bindings.entrySet().stream()
                    .filter(entry -> entry.getValue().equals(namespaceURI))
                    .map(Map.Entry::getKey)
                    .toList().iterator();
        }
    }

    public static void main(String[] args) throws Exception {
        String xml = """
                <catalog xmlns="urn:catalog" xmlns:m="urn:metadata">
                  <book id="b1" m:status="active">
                    <title>Core Java</title>
                  </book>
                  <plain xmlns="">
                    <book id="b2"><title>Unqualified Book</title></book>
                  </plain>
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
        xpath.setNamespaceContext(new QueryNamespaces());

        System.out.println("withoutPrefix=" + xpath.evaluate(
                "count(/catalog/book)", document, XPathConstants.NUMBER));
        System.out.println("withPrefix=" + xpath.evaluate(
                "count(/c:catalog/c:book)", document, XPathConstants.NUMBER));
        System.out.println("title=" + xpath.evaluate(
                "string(/c:catalog/c:book/c:title)", document));
        System.out.println("id=" + xpath.evaluate(
                "string(/c:catalog/c:book/@id)", document));
        System.out.println("status=" + xpath.evaluate(
                "string(/c:catalog/c:book/@meta:status)", document));
        System.out.println("wrongAttributeNamespace=" + xpath.evaluate(
                "count(/c:catalog/c:book/@c:id)",
                document, XPathConstants.NUMBER));
        System.out.println("resetNamespace=" + xpath.evaluate(
                "string(/c:catalog/plain/book/title)", document));
    }
}
```

Biên dịch và chạy:

```shell
javac DefaultNamespaceXPathDemo.java
java DefaultNamespaceXPathDemo
```

Kết quả:

```text
withoutPrefix=0.0
withPrefix=1.0
title=Core Java
id=b1
status=active
wrongAttributeNamespace=0.0
resetNamespace=Unqualified Book
```

Giải thích:

1. `/catalog/book` không chọn phần tử thuộc `urn:catalog`.
2. `/c:catalog/c:book` chọn đúng một book có namespace đó.
3. `c:title` cũng phải dùng namespace của phần tử title.
4. `@id` không prefix khớp thuộc tính id không namespace.
5. Tài liệu viết m:status nhưng truy vấn dùng meta:status; cùng URI nên vẫn khớp.
6. `@c:id` không khớp vì yêu cầu sai namespace thuộc tính.
7. Phần tử plain có `xmlns=""`, nên plain, book và title trong vùng đó không mang namespace mặc định catalog.

Mỗi số đếm in dạng Double theo kiểu kết quả NUMBER của API, nên thấy `1.0` thay vì một Integer.

Ví dụ dùng XML cố định không cần DTD/schema ngoài. Các cấu hình parser về truy cập ngoài phục vụ nguồn dữ liệu đó và không thay thế việc thiết kế chính sách cho mọi loại XML khác.

## 9. Phạm vi của namespace mặc định có thể thay đổi trong cây

Namespace mặc định được kế thừa trong vùng XML cho đến khi có một khai báo khác.

Ví dụ:

```xml
<catalog xmlns="urn:catalog">
  <book/>
  <section xmlns="urn:special">
    <book/>
  </section>
  <plain xmlns="">
    <book/>
  </plain>
</catalog>
```

Ba phần tử book có danh tính khác nhau:

```text
urn:catalog + book
urn:special + book
không namespace + book
```

Nếu truy vấn chỉ có c ánh xạ tới `urn:catalog`, `c:book` không tự khớp cả ba.

Có thể cài thêm prefix s cho `urn:special` và viết đường dẫn đúng vùng:

```xpath
/c:catalog/s:section/s:book
```

Với vùng không namespace:

```xpath
/c:catalog/plain/book
```

Do đó không có quy tắc “tệp có một xmlns ở đầu thì mọi tên trong tệp dùng cùng prefix”. Phải kiểm tra cấu trúc và phạm vi namespace thực tế.

## 10. Các bước đường dẫn đều cần đúng danh tính

Một lỗi thường gặp là chỉ thêm prefix ở nút gốc:

```xpath
/c:catalog/book/title
```

Nếu book và title vẫn thuộc namespace catalog, biểu thức trên đang tìm các con **không namespace** bên dưới catalog có namespace, nên không khớp cấu trúc đó.

Phải viết:

```xpath
/c:catalog/c:book/c:title
```

Điều tương tự áp dụng trong predicate:

```xpath
/c:catalog/c:book[c:title='Core Java']
```

`title` trong điều kiện cũng là một bước chọn phần tử, không tự nhận namespace từ c:book.

Nhưng thuộc tính id vẫn là:

```xpath
/c:catalog/c:book[@id='b1']
```

Không thêm prefix hàng loạt vào mọi tên mà chưa phân biệt phần tử với thuộc tính và URI của từng tên.

## 11. Vì sao không chỉ dùng local-name()?

Có thể gặp cách viết:

```xpath
//*[local-name()='book']
```

Nó tìm theo tên cục bộ và bỏ qua việc book thuộc namespace nào. Trong tài liệu có nhiều loại dữ liệu, nó có thể chọn nhầm phần tử cùng tên nhưng khác ý nghĩa.

Nếu thật sự cần nhận diện bằng các hàm này, phải xét cả namespace:

```xpath
//*[local-name()='book' and namespace-uri()='urn:catalog']
```

Ngay cả vậy, dấu `//` vẫn mở rộng phạm vi tìm. Nếu yêu cầu cấu trúc cụ thể, đường dẫn dùng prefix thường rõ hơn và giúp thể hiện cả quan hệ cha–con.

`local-name()` và `namespace-uri()` có ích cho chẩn đoán hoặc các truy vấn được thiết kế để nhận nhiều tên, nhưng không phải mẹo mặc định để né cấu hình namespace.

Tương tự, không dùng `name()='m:book'` để gắn ngữ nghĩa vào một prefix chỉ là cách viết. Bên cung cấp có thể đổi m thành x mà vẫn giữ nguyên dữ liệu theo namespace.

## 12. Chẩn đoán truy vấn rỗng theo đúng thứ tự

Nếu XPath không chọn được dữ liệu:

1. Kiểm tra DOM đã được parse với namespaceAware trước khi tạo cây chưa.
2. Xem `node.getNamespaceURI()` và `node.getLocalName()` của phần tử thật.
3. Xác định URI ở từng vùng cây, gồm các khai báo mặc định mới hoặc `xmlns=""`.
4. Kiểm tra NamespaceContext đang ánh xạ prefix của truy vấn tới đúng URI.
5. Kiểm tra từng bước và từng tên trong predicate.
6. Phân biệt thuộc tính có prefix với thuộc tính không prefix.
7. Kiểm tra ngữ cảnh tương đối/tuyệt đối và kiểu kết quả yêu cầu.

Prefix chưa được ánh xạ có thể gây lỗi phân giải biểu thức. Prefix đã được ánh xạ nhưng tới URI không đúng lại có thể tạo một truy vấn hợp lệ trả tập rỗng. Hai tình huống cần cách sửa khác nhau.

Không chuyển parser sang chế độ không nhận biết namespace chỉ để truy vấn cũ chạy lại. Cách đó làm mất sự phân biệt tên mà tài liệu đang dùng, có thể khiến các dữ liệu khác namespace bị gộp nhầm.

## 13. Thực hành kiểm tra tính ổn định

- Đổi tài liệu từ namespace mặc định sang `x:catalog`, `x:book`, `x:title` cùng URI. Truy vấn dùng prefix c không cần đổi chỉ vì cách viết prefix của XML đổi.
- Đổi m:status thành z:status nhưng giữ URI metadata: truy vấn meta:status vẫn đúng.
- Đổi URI catalog thành `urn:catalog:v2`: truy vấn c với URI cũ không còn chỉ cùng danh tính. Cần xem đây có phải thay đổi phiên bản dữ liệu cần hỗ trợ không.
- Bỏ `xmlns=""` trên plain: các phần tử trong vùng đó lại kế thừa namespace mặc định catalog; đường dẫn không prefix cũ không còn phù hợp.
- Đặt một thuộc tính `c:id` có namespace bên cạnh id không namespace trong một tài liệu hợp lệ: chúng là hai tên thuộc tính khác nhau theo tên mở rộng.

Điểm cần giữ rõ là **namespace của XML xác định danh tính; prefix trong XPath chỉ là cách tham chiếu danh tính đó qua một ánh xạ được cấu hình**.
