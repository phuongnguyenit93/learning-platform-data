# NamespaceContext và ánh xạ tiền tố trong XPath

## 1. Vì sao XPath thấy đúng tên mà vẫn không chọn được nút?

Giả sử XML có `<book>` nhưng biểu thức `/catalog/book` trả về tập rỗng. Một nguyên nhân thường gặp là phần tử thuộc **không gian tên (namespace)** mặc định. Tên thực của phần tử để so khớp không chỉ là chuỗi `book`: nó gồm cặp **namespace URI + tên cục bộ (local name)**.

Trong XML, tiền tố (prefix) là cách viết ngắn tham chiếu đến namespace URI. Trong biểu thức XPath, tiền tố cũng phải được giải nghĩa. `NamespaceContext` cung cấp bảng giải nghĩa đó cho bộ đánh giá XPath của Java; nó không sửa XML và không đổi tên các nút.

Hãy tách ba thứ trước khi viết truy vấn:

```text
Văn bản XML:   tiền tố của tài liệu → namespace URI của nút
DOM:          giữ namespace URI và local name của từng nút
Biểu thức:    tiền tố do người viết XPath chọn → cùng namespace URI
```

Nếu hai phía quy về cùng URI và cùng local name, tên có thể khớp dù tiền tố viết khác nhau. Ngược lại, cùng chuỗi tiền tố hoặc cùng local name nhưng khác URI không làm hai tên trở thành một.

Bài dùng JAXP `javax.xml.xpath` còn được hỗ trợ trên Java hiện hành. API chuẩn này hỗ trợ XPath 1.0; không tự áp quy tắc “default element namespace” của một bộ xử lý/ngôn ngữ XPath mới hơn vào ví dụ JAXP. [Phạm vi API XPath của Java](https://docs.oracle.com/en/java/javase/25/docs/api/java.xml/javax/xml/xpath/package-summary.html)

## 2. Nhận diện namespace trong tài liệu XML

Xét tài liệu:

```xml
<catalog xmlns="urn:catalog" xmlns:m="urn:meta">
    <book id="b1" m:status="active">
        <title>Java</title>
    </book>
    <other xmlns="urn:other">
        <book id="x"/>
    </other>
</catalog>
```

Các tên quan trọng là:

| Nút | Namespace URI | Local name |
| --- | --- | --- |
| Phần tử gốc `catalog` | `urn:catalog` | `catalog` |
| `book` con trực tiếp của gốc | `urn:catalog` | `book` |
| `title` trong book đó | `urn:catalog` | `title` |
| Thuộc tính `id` | Không có namespace | `id` |
| Thuộc tính `m:status` | `urn:meta` | `status` |
| Phần tử `other` và book bên trong | `urn:other` | `other`, `book` |

`xmlns="urn:catalog"` đặt namespace mặc định cho các phần tử không có tiền tố trong phạm vi của nó. Khai báo mặc định mới ở `other` thay phạm vi đó cho các phần tử bên dưới. Namespace mặc định **không áp cho thuộc tính không có tiền tố**, nên `id` không tự thuộc `urn:catalog`. [Namespaces in XML: phạm vi và namespace mặc định](https://www.w3.org/TR/xml-names/#defaulting)

Namespace URI là định danh so khớp, không phải yêu cầu tải nội dung từ mạng. `urn:catalog` là một định danh hợp lệ cho ví dụ; nếu dùng URI dạng HTTP, ánh xạ tiền tố cũng không có nghĩa `NamespaceContext` phải gọi HTTP để tìm schema. So sánh đúng chuỗi URI theo hợp đồng; không tùy ý đổi hoa/thường, thêm dấu `/` hoặc chuẩn hóa một URI thành URI khác rồi mong tên vẫn khớp.

## 3. Bảng ánh xạ của biểu thức độc lập với cách viết XML

Ta có thể chọn bảng sau cho các biểu thức của ứng dụng:

| Tiền tố XPath | Namespace URI |
| --- | --- |
| `c` | `urn:catalog` |
| `alias` | `urn:catalog` |
| `meta` | `urn:meta` |

Khi đó `/c:catalog/c:book/c:title` chọn title trong namespace catalog. Không có `xmlns:c` trong tài liệu vẫn không sao: `c` là tiền tố của **biểu thức**, do `NamespaceContext` cung cấp.

Tương tự, thuộc tính trong XML viết là `m:status`, nhưng biểu thức dùng `@meta:status`. Hai tiền tố cùng quy về `urn:meta`. Nếu bên phát hành đổi tài liệu từ namespace mặc định sang tiền tố `x` nhưng giữ URI và cấu trúc, biểu thức dùng `c` vẫn có thể làm việc như trước.

Đây là lợi ích của việc đặt tiền tố ứng dụng ổn định: truy vấn bám vào danh tính namespace, không phụ thuộc một lựa chọn viết tắt của nhà sản xuất XML. Tuy nhiên, thay URI từ `urn:catalog:v1` sang `urn:catalog:v2` là thay đổi tên; chỉ giữ local name không đủ để coi đó là cùng mô hình dữ liệu.

`NamespaceContext` được gắn bằng `xpath.setNamespaceContext(context)`. Các QName có tiền tố trong biểu thức được giải nghĩa dựa vào context này. [XPath và namespace context](https://docs.oracle.com/en/java/javase/25/docs/api/java.xml/javax/xml/xpath/XPath.html)

## 4. Bẫy namespace mặc định trong XPath 1.0

Trong một phép kiểm tra tên phần tử của XPath 1.0, tên không có tiền tố như `book` hướng đến tên không có namespace. Nó không tự thừa hưởng `xmlns` mặc định từ tài liệu XML. Vì vậy `/catalog/book` không chọn cặp phần tử thuộc `urn:catalog` của ví dụ.

Ngay cả khi `NamespaceContext.getNamespaceURI("")` trả `urn:catalog`, điều đó cũng không tự đổi các tên phần tử không có tiền tố trong XPath 1.0 thành tên có namespace. Cách rõ ràng với JAXP là đặt tiền tố riêng rồi viết `/c:catalog/c:book`. [Quy tắc node test của XPath 1.0](https://www.w3.org/TR/1999/REC-xpath-19991116/#node-tests)

Phân biệt hai câu:

- “Trong XML, `<book>` đang nằm trong namespace mặc định” nói về tên nút đã được parser tạo ra.
- “Trong XPath, `book` không có tiền tố” nói về tên được biểu thức tìm kiếm.

Nhầm hai môi trường này dễ khiến người viết tắt chế độ namespace của parser để truy vấn “có vẻ chạy”. Làm vậy đánh mất cách phân biệt các từ vựng XML; hãy giữ DOM nhận biết namespace và sửa ánh xạ/biểu thức cho đúng.

## 5. Hợp đồng đầy đủ của NamespaceContext

Interface không chỉ có một phương thức tra cứu xuôi. Một lớp cài đặt cần đáp ứng cả ba phương thức:

| Phương thức | Kết quả khi có ánh xạ | Khi không có ánh xạ |
| --- | --- | --- |
| `getNamespaceURI(prefix)` | URI được gắn với prefix | `XMLConstants.NULL_NS_URI`, tức chuỗi rỗng; không phải null |
| `getPrefix(uri)` | Một tiền tố gắn với URI | `null` |
| `getPrefixes(uri)` | Iterator các tiền tố gắn với URI | Iterator rỗng |

Đối số `null` của cả ba phương thức phải bị từ chối bằng `IllegalArgumentException`. Một URI có thể có nhiều tiền tố; `getPrefix` không hứa chọn một alias cụ thể. Thứ tự `getPrefixes` không được bảo đảm, và iterator không cho sửa bằng `remove`. [Hợp đồng NamespaceContext](https://docs.oracle.com/en/java/javase/25/docs/api/java.xml/javax/xml/namespace/NamespaceContext.html)

Còn có các ràng buộc được định nghĩa sẵn:

- `xml` ánh xạ đến `XMLConstants.XML_NS_URI`.
- `xmlns` ánh xạ đến `XMLConstants.XMLNS_ATTRIBUTE_NS_URI`.
- Tiền tố mặc định được biểu diễn bằng `XMLConstants.DEFAULT_NS_PREFIX`, tức chuỗi rỗng.

Không trả `null` cho một tiền tố lạ chỉ vì đó là cách `Map.get` làm việc. Cũng không cài `getPrefixes` bằng một iterator của map có thể sửa rồi vô tình cho bên ngoài thay context. Một lớp read-only nên giữ bản sao riêng của các ánh xạ và trả kết quả phù hợp với hợp đồng.

## 6. Chương trình hoàn chỉnh

Lưu thành `XPathNamespaceContextDemo.java`, biên dịch/chạy bằng JDK 17 trở lên. `FixedNamespaces` là bảng ánh xạ bất biến do ứng dụng cấp, không phải bộ tự dò mọi khai báo của một DOM. Ví dụ dùng các tiền tố được ứng dụng biết trước; nó không phải trình xác thực toàn bộ cú pháp NCName của tên tiền tố do người dùng tùy ý nhập.

```java
import java.io.StringReader;
import java.util.Iterator;
import java.util.LinkedHashMap;
import java.util.Map;
import javax.xml.XMLConstants;
import javax.xml.namespace.NamespaceContext;
import javax.xml.parsers.DocumentBuilderFactory;
import javax.xml.xpath.XPath;
import javax.xml.xpath.XPathConstants;
import javax.xml.xpath.XPathFactory;
import org.w3c.dom.Document;
import org.xml.sax.InputSource;

public class XPathNamespaceContextDemo {
    static final class FixedNamespaces implements NamespaceContext {
        private final Map<String, String> bindings;

        FixedNamespaces(Map<String, String> supplied) {
            if (supplied == null) {
                throw new IllegalArgumentException("bindings must not be null");
            }
            Map<String, String> copy = new LinkedHashMap<>();
            copy.put(XMLConstants.DEFAULT_NS_PREFIX, XMLConstants.NULL_NS_URI);
            copy.put(XMLConstants.XML_NS_PREFIX, XMLConstants.XML_NS_URI);
            copy.put(XMLConstants.XMLNS_ATTRIBUTE, XMLConstants.XMLNS_ATTRIBUTE_NS_URI);

            supplied.forEach((prefix, uri) -> {
                if (prefix == null || uri == null) {
                    throw new IllegalArgumentException("null binding");
                }
                if (prefix.equals(XMLConstants.XML_NS_PREFIX)
                        || prefix.equals(XMLConstants.XMLNS_ATTRIBUTE)) {
                    if (!uri.equals(copy.get(prefix))) {
                        throw new IllegalArgumentException("reserved prefix");
                    }
                } else if (uri.equals(XMLConstants.XML_NS_URI)
                        || uri.equals(XMLConstants.XMLNS_ATTRIBUTE_NS_URI)) {
                    throw new IllegalArgumentException("reserved namespace URI");
                }
                if (!prefix.isEmpty() && uri.isEmpty()) {
                    throw new IllegalArgumentException("empty URI for named prefix");
                }
                copy.put(prefix, uri);
            });
            bindings = Map.copyOf(copy);
        }

        @Override
        public String getNamespaceURI(String prefix) {
            requireNonNullArgument(prefix);
            return bindings.getOrDefault(prefix, XMLConstants.NULL_NS_URI);
        }

        @Override
        public String getPrefix(String namespaceURI) {
            Iterator<String> prefixes = getPrefixes(namespaceURI);
            return prefixes.hasNext() ? prefixes.next() : null;
        }

        @Override
        public Iterator<String> getPrefixes(String namespaceURI) {
            requireNonNullArgument(namespaceURI);
            return bindings.entrySet().stream()
                    .filter(entry -> entry.getValue().equals(namespaceURI))
                    .map(Map.Entry::getKey)
                    .toList().iterator();
        }

        private static void requireNonNullArgument(String value) {
            if (value == null) {
                throw new IllegalArgumentException("argument must not be null");
            }
        }
    }

    private static Document parse(String xml) throws Exception {
        DocumentBuilderFactory factory = DocumentBuilderFactory.newDefaultNSInstance();
        factory.setFeature(XMLConstants.FEATURE_SECURE_PROCESSING, true);
        factory.setFeature("http://apache.org/xml/features/disallow-doctype-decl", true);
        factory.setAttribute(XMLConstants.ACCESS_EXTERNAL_DTD, "");
        factory.setAttribute(XMLConstants.ACCESS_EXTERNAL_SCHEMA, "");
        factory.setXIncludeAware(false);
        return factory.newDocumentBuilder().parse(
                new InputSource(new StringReader(xml)));
    }

    private static int count(XPath xpath, String expression, Document document)
            throws Exception {
        return ((Double) xpath.evaluate(
                expression, document, XPathConstants.NUMBER)).intValue();
    }

    public static void main(String[] args) throws Exception {
        String xml = """
                <catalog xmlns="urn:catalog" xmlns:m="urn:meta">
                    <book id="b1" m:status="active">
                        <title>Java</title>
                    </book>
                    <other xmlns="urn:other">
                        <book id="x"/>
                    </other>
                </catalog>
                """;

        FixedNamespaces namespaces = new FixedNamespaces(Map.of(
                "", "urn:catalog",
                "c", "urn:catalog",
                "alias", "urn:catalog",
                "meta", "urn:meta"));

        XPath xpath = XPathFactory.newInstance().newXPath();
        xpath.setNamespaceContext(namespaces);
        Document document = parse(xml);

        System.out.println("plain=" + count(xpath, "count(/catalog/book)", document));
        System.out.println("qualified="
                + count(xpath, "count(/c:catalog/c:book)", document));
        System.out.println("title="
                + xpath.evaluate("/c:catalog/c:book/c:title", document));
        System.out.println("id="
                + xpath.evaluate("/c:catalog/c:book/@id", document));
        System.out.println("status="
                + xpath.evaluate("/c:catalog/c:book/@meta:status", document));
        System.out.println("local-name-count="
                + count(xpath, "count(//*[local-name()='book'])", document));
        System.out.println("namespace-count="
                + count(xpath, "count(//c:book)", document));

        String renamed = """
                <x:catalog xmlns:x="urn:catalog">
                    <x:book><x:title>Java</x:title></x:book>
                </x:catalog>
                """;
        System.out.println("renamed-title=" + xpath.evaluate(
                "/alias:catalog/alias:book/alias:title", parse(renamed)));
        System.out.println("unknown-prefix-empty="
                + namespaces.getNamespaceURI("missing").isEmpty());
        System.out.println("unknown-uri-prefix-null="
                + (namespaces.getPrefix("urn:missing") == null));

        try {
            namespaces.getNamespaceURI(null);
        } catch (IllegalArgumentException expected) {
            System.out.println("null-argument=rejected");
        }
        Iterator<String> prefixes = namespaces.getPrefixes("urn:meta");
        prefixes.next();
        try {
            prefixes.remove();
        } catch (UnsupportedOperationException expected) {
            System.out.println("iterator-remove=rejected");
        }
    }
}
```

Chạy:

```shell
javac XPathNamespaceContextDemo.java
java XPathNamespaceContextDemo
```

Stdout:

```text
plain=0
qualified=1
title=Java
id=b1
status=active
local-name-count=2
namespace-count=1
renamed-title=Java
unknown-prefix-empty=true
unknown-uri-prefix-null=true
null-argument=rejected
iterator-remove=rejected
```

### Vì sao parser phải nhận biết namespace?

`newDefaultNSInstance()` tạo factory DOM nhận biết namespace bằng bộ triển khai mặc định của JDK. Có thể dùng `newInstance()` rồi `setNamespaceAware(true)` trước khi tạo builder nếu muốn cơ chế chọn provider tương ứng. Đặt cấu hình ở factory **trước** khi parse; gắn `NamespaceContext` sau đó không sửa lại một DOM đã được parse không đúng chế độ. [DocumentBuilderFactory](https://docs.oracle.com/en/java/javase/25/docs/api/java.xml/javax/xml/parsers/DocumentBuilderFactory.html)

Hàm parse của ví dụ còn tắt DOCTYPE và truy cập DTD/schema bên ngoài; đây là cấu hình cho bộ parser JDK được chọn, không phải chức năng của `NamespaceContext`. Mã truyền tiếp lỗi cấu hình/parse thay vì bỏ qua rồi tiếp tục với một parser có hành vi khác. Phần XML trong bài là chuỗi có kiểm soát; khi tích hợp nguồn XML khác cần giữ chính sách parser phù hợp với nguồn đó.

### Đọc các kết quả chọn nút

- `plain=0`: `/catalog/book` tìm tên không có namespace, không khớp các phần tử catalog trong XML. Chương trình cố ý đã đặt ánh xạ tiền tố rỗng về `urn:catalog`, nhưng quy tắc XPath 1.0 vẫn giữ nguyên.
- `qualified=1`: `/c:catalog/c:book` dùng URI `urn:catalog`, chọn đúng book con của gốc.
- `title=Java`: các bước phần tử đều dùng tiền tố `c`; một bước còn thiếu tiền tố cũng có thể làm đường dẫn không khớp.
- `id=b1`: thuộc tính `id` không có namespace nên dùng `@id`.
- `status=active`: `@meta:status` chọn thuộc tính có URI `urn:meta` dù XML dùng tiền tố `m`.
- `renamed-title=Java`: tài liệu thứ hai dùng tiền tố `x`, còn biểu thức dùng `alias`. URI trùng nhau nên tên vẫn khớp.

`evaluate(expression, document)` trong ví dụ yêu cầu chuỗi. Khi truy vấn chọn nhiều nút, kết quả chuỗi không thay thế cho việc duyệt toàn bộ tập nút; tùy câu hỏi nên chọn `XPathConstants.NODESET`, `NODE`, `BOOLEAN` hoặc `NUMBER` phù hợp. Các phép `count(...)` trong ví dụ trả kiểu `Double` theo lựa chọn `XPathConstants.NUMBER` rồi chuyển sang `int` cho các số đếm nhỏ đã biết.

### Đọc các kết quả kiểm tra context

`unknown-prefix-empty=true` xác nhận tiền tố chưa đăng ký trả URI rỗng. `unknown-uri-prefix-null=true` xác nhận tra ngược URI không biết trả null. Hai chiều không dùng cùng một quy ước “không tìm thấy”. Hai dòng cuối kiểm chứng đối số null và iterator chỉ đọc.

Map có hai alias `c` và `alias` cùng URI; `getPrefixes("urn:catalog")` còn có thể chứa tiền tố rỗng vì chương trình đã đăng ký nó. Không kiểm tra thứ tự của iterator hoặc giả định `getPrefix("urn:catalog")` phải luôn trả `c`. Với hai URI dành riêng, lớp ngăn việc gán alias khác để giữ đúng hợp đồng dành cho `xml` và `xmlns`.

## 7. Vì sao local-name() không phải cách sửa mặc định?

`//*[local-name()='book']` bỏ qua URI. Nó chọn cả book thuộc `urn:catalog` và book thuộc `urn:other`, nên ví dụ in `local-name-count=2`. `//c:book` chỉ chọn book trong URI catalog, nên kết quả là `1`.

Đôi khi thật sự muốn tìm một local name qua nhiều namespace; khi đó việc bỏ URI có thể là chủ ý. Nhưng nếu mô hình dữ liệu chỉ cho phép một namespace, bỏ kiểm tra URI sẽ làm truy vấn nhận cả dữ liệu của từ vựng khác. Nó có thể che một lỗi ánh xạ hoặc thay đổi phiên bản tài liệu.

Nếu cần biểu thức không viết tiền tố nhưng vẫn kiểm tra tên đầy đủ, một cách minh họa là:

```xpath
//*[local-name()='book' and namespace-uri()='urn:catalog']
```

Biểu thức trên dài hơn và lặp URI; với các truy vấn ổn định, bảng `NamespaceContext` thường làm biểu thức dễ đọc và quản lý hơn. Không coi mẹo `local-name()` là lý do bỏ thiết lập namespace.

## 8. Phạm vi tài liệu khác với bảng tiền tố biểu thức

Một prefix XML có thể bị gắn lại URI ở một phần tử con. Ví dụ cùng ký tự `p` ở hai vùng khác nhau có thể quy về hai namespace khác nhau. Parser ghi nhận URI thực tế trên từng nút theo phạm vi khai báo; truy vấn dùng `c` vẫn tìm theo URI đã đăng ký trong môi trường biểu thức.

`NamespaceContext` không tự di chuyển cùng từng nút để đổi nghĩa tiền tố XPath ở mỗi bước. Với bảng cố định, `c` có một nghĩa thống nhất cho toàn biểu thức. Nếu tài liệu chứa hai URI khác nhau cùng local name, đăng ký hai tiền tố XPath khác nhau để truy vấn rõ từng loại.

DOM có `lookupNamespaceURI` để tra namespace có hiệu lực từ một nút, nhưng lấy nó từ gốc rồi dùng như bảng tự động cho mọi vùng tài liệu có thể bỏ qua việc che/gắn lại prefix ở con. Nếu xây context dựa trên DOM, phải chọn rõ nút/phạm vi làm nguồn và vẫn thực hiện hợp đồng đầy đủ của interface; không chỉ chuyển nguyên kết quả null của DOM sang `getNamespaceURI`. [DOM Node.lookupNamespaceURI](https://docs.oracle.com/en/java/javase/25/docs/api/java.xml/org/w3c/dom/Node.html#lookupNamespaceURI(java.lang.String))

Với dữ liệu theo một hợp đồng XML đã biết, đăng ký tiền tố ứng dụng theo các URI của hợp đồng thường dễ dự đoán hơn việc cố sao chép mọi prefix văn bản tài liệu.

## 9. Thiết lập trước khi compile và lưu ý dùng đồng thời

Đặt `NamespaceContext` trước khi `compile` hoặc `evaluate` biểu thức có tiền tố. Khi muốn dùng một bộ ánh xạ khác, tạo/cấu hình môi trường phù hợp và biên dịch lại theo môi trường đó; không dựa vào việc sửa một map đang được một biểu thức đã biên dịch sử dụng.

```java
// Đoạn đặt trong phương thức đã có namespaces và document.
XPath xpath = XPathFactory.newInstance().newXPath();
xpath.setNamespaceContext(namespaces);
var expression = xpath.compile("/c:catalog/c:book/c:title");
String title = expression.evaluate(document);
```

`XPath` và `XPathExpression` không được bảo đảm an toàn luồng hoặc tái nhập. Bảng namespace bất biến chỉ giúp riêng bảng ánh xạ không bị đổi; nó không biến đối tượng XPath dùng chung thành an toàn cho nhiều lời evaluate đồng thời. Quản lý từng môi trường/biểu thức theo phạm vi dùng phù hợp hoặc có cơ chế đồng bộ đúng. [XPathExpression](https://docs.oracle.com/en/java/javase/25/docs/api/java.xml/javax/xml/xpath/XPathExpression.html)

Giữ URI như cấu hình của hợp đồng truy vấn; tránh đổi ánh xạ tùy theo từng yêu cầu khi các lời gọi đang cùng dùng một `XPath`. Điều đó vừa làm khó chẩn đoán vừa có thể vi phạm giới hạn dùng đồng thời của API.

## 10. Trình tự chẩn đoán truy vấn không khớp

1. Xác nhận đúng tài liệu và node ngữ cảnh; đường tuyệt đối bắt đầu từ gốc, đường tương đối phụ thuộc nơi đánh giá.
2. Xác nhận DOM được parse có nhận biết namespace.
3. Xem `getNamespaceURI()` và `getLocalName()` của một nút thực tế cần chọn; đừng chỉ nhìn `getNodeName()` hoặc ký tự prefix.
4. Kiểm tra mọi prefix trong biểu thức đã được context gắn đúng URI trước compile/evaluate.
5. Tìm các bước phần tử bỏ sót prefix, đặc biệt khi XML dùng namespace mặc định.
6. Phân biệt thuộc tính có prefix với thuộc tính không có prefix.
7. Chọn kiểu kết quả đúng để phân biệt không có nút với nút có nội dung chuỗi rỗng.

Một prefix không được giải nghĩa trong biểu thức có thể khiến việc biên dịch/đánh giá báo `XPathExpressionException`; một prefix được giải nghĩa **sang URI sai** có thể vẫn là biểu thức hợp lệ nhưng chọn không được nút. Đó là hai nhóm lỗi khác nhau. Không sửa bằng cách bỏ hết prefix rồi vô tình mở rộng tập kết quả.

## 11. Lỗi phổ biến và tự kiểm tra

| Lỗi | Cách sửa |
| --- | --- |
| Map.get trả null cho prefix lạ | Trả `XMLConstants.NULL_NS_URI` theo interface |
| Nghĩ prefix XPath phải xuất hiện trong xmlns của tài liệu | Chọn alias ứng dụng và ánh xạ đúng URI |
| Gắn `"" → URI` rồi kỳ vọng `/catalog/book` tự có namespace | Dùng tiền tố tường minh trong XPath 1.0 |
| Viết `@c:id` cho id không prefix | Dùng `@id` khi thuộc tính không có namespace |
| Cài tra ngược bằng một prefix duy nhất, bỏ alias khác | getPrefixes phải trả mọi prefix trong context cho URI đó |
| Iterator có thể remove sửa map | Trả iterator không sửa được |
| Bỏ URI bằng local-name để hết lỗi | Xác định có thật sự muốn bỏ qua namespace hay không |
| Dùng context bất biến rồi chia sẻ XPath đồng thời | Tuân thủ riêng giới hạn thread-safety của XPath/XPathExpression |

1. **XML đổi từ `<m:book xmlns:m="urn:catalog">` sang `<x:book xmlns:x="urn:catalog">`; truy vấn `//c:book` có cần đổi không?** Không nếu `c` vẫn gắn `urn:catalog` và cấu trúc/ngữ cảnh truy vấn phù hợp.
2. **Hai phần tử cùng local name book nhưng URI khác nhau có phải cùng tên để truy vấn theo namespace không?** Không. URI là một phần danh tính tên.
3. **Vì sao `@id` vẫn không có tiền tố dù cha có namespace mặc định?** Namespace mặc định của XML không tự áp cho thuộc tính không prefix.
4. **getPrefix có được trả một alias khác c không?** Có, nếu alias ấy thực sự gắn URI đó; thứ tự lựa chọn không được bảo đảm. Muốn mọi alias, gọi getPrefixes.
5. **NamespaceContext có tự tải schema từ URI hay sửa tài liệu DOM không?** Không. Nó là bảng giải nghĩa namespace cho môi trường biểu thức; parse/validation và quản lý DOM là trách nhiệm khác.
