# Hàm mở rộng qua XPathFunctionResolver

## 1. Vai trò: nối biểu thức XPath với quy tắc do ứng dụng định nghĩa

XPath dùng để chọn và kiểm tra dữ liệu trong cây XML. Khi điều kiện chọn cần một quy tắc riêng của ứng dụng, ta có thể cung cấp **hàm mở rộng**: biểu thức gọi tên hàm, còn Java thực hiện phép tính và trả kết quả về bộ xử lý XPath.

Ví dụ, danh mục sản phẩm quy định mã hợp lệ gồm hai chữ cái ASCII viết hoa, dấu gạch nối và bốn chữ số: `BK-0001`. Thay vì đưa toàn bộ việc duyệt cây về Java, ta muốn giữ đường dẫn chọn sản phẩm trong XPath:

```xpath
/catalog/product[ext:valid-sku(string(@sku))]
```

Trong biểu thức này, XPath xác định từng `product`; hàm Java chỉ quyết định mã của sản phẩm có đúng quy tắc hay không. Đây là một ranh giới trách nhiệm nhỏ và rõ ràng.

`javax.xml.xpath.XPathFunctionResolver` là giao diện JAXP vẫn được cung cấp trong module `java.xml` của Java hiện đại. Tên gói vẫn là `javax.xml.xpath`, không đổi thành `jakarta.xml.xpath`. Việc API xuất hiện từ Java 5 không có nghĩa phải dùng JDK 5 hoặc cách truy cập lớp nội bộ của JDK. Bài sử dụng API công khai và cú pháp Java 17+.

JAXP XPath tiêu chuẩn làm việc với mô hình XPath 1.0. Cung cấp một hàm Java không tự nâng ngôn ngữ thành XPath 2.0/3.1; đừng suy ra rằng biểu thức sẽ có sẵn mọi hàm của các phiên bản đó. Xem [tổng quan javax.xml.xpath](https://docs.oracle.com/en/java/javase/17/docs/api/java.xml/javax/xml/xpath/package-summary.html).

## 2. Ba thành phần phải phối hợp

| Thành phần | Trách nhiệm trong ví dụ |
| --- | --- |
| `NamespaceContext` | Ánh xạ tiền tố `ext` thành URI `urn:example:catalog-functions:v1` |
| `XPathFunctionResolver` | Tìm hàm theo `QName` và số đối số |
| `XPathFunction` | Nhận các giá trị đối số đã được XPath đánh giá, kiểm tra và trả kết quả Java |

Luồng xử lý khái niệm là: gặp `ext:valid-sku(...)` → tra URI của `ext` → tạo tên mở rộng `{URI}valid-sku` → tìm hàm có một đối số → đánh giá đối số → gọi hàm → dùng kết quả trong điều kiện lọc.

### 2.1. Định danh hàm bằng URI, tên cục bộ và số đối số

Phương thức cốt lõi của bộ phân giải là:

```java
XPathFunction resolveFunction(QName functionName, int arity);
```

`arity` là số đối số, không phải kiểu dữ liệu. Với `ext:valid-sku(string(@sku))`, nó bằng `1`. Cùng tên hàm nhưng hai đối số là một yêu cầu khác. Bộ phân giải không cung cấp cơ chế chọn hàm dựa trên kiểu đối số như nạp chồng phương thức Java.

`QName` biểu diễn tên đủ điều kiện. So sánh tên theo **namespace URI và local part**, không so sánh chuỗi tiền tố `ext`. Hai tiền tố khác nhau cùng trỏ tới một URI có thể gọi cùng hàm. Ngược lại, cùng chữ `valid-sku` nhưng URI khác phải được xem là tên khác.

Nếu không có hàm tương ứng, trả `null`. Không trả một hàm mặc định làm mọi trường hợp trở thành thành công. Bộ phân giải chỉ dành cho hàm trong namespace mở rộng được gọi bằng tiền tố; nó không thay thế các hàm có sẵn như `count()` hoặc `string()`. Xem [hợp đồng XPathFunctionResolver](https://docs.oracle.com/en/java/javase/25/docs/api/java.xml/javax/xml/xpath/XPathFunctionResolver.html).

### 2.2. Namespace của hàm không phải namespace của dữ liệu

URI `urn:example:catalog-functions:v1` ở đây chỉ định danh thư viện hàm; nó không cần được tải qua mạng. XML mẫu có các phần tử không thuộc namespace, nên đường dẫn là `/catalog/product`. Việc đăng ký `ext` không làm các phần tử XML tự thuộc namespace của hàm.

Tiền tố dùng trong chuỗi XPath phải được khai báo trong `NamespaceContext` của đối tượng `XPath`; đừng dựa vào việc trong XML tình cờ có một khai báo `xmlns:ext`. Một triển khai `NamespaceContext` cần xử lý cả tiền tố không tồn tại, tham số `null` và các tiền tố chuẩn `xml`, `xmlns`. Xem [NamespaceContext](https://docs.oracle.com/en/java/javase/17/docs/api/java.xml/javax/xml/namespace/NamespaceContext.html).

## 3. Hợp đồng đối số và kết quả

`XPathFunction` có một phương thức:

```java
Object evaluate(List<?> args) throws XPathFunctionException;
```

Danh sách chứa **giá trị sau khi đánh giá đối số**, không chứa chuỗi mã nguồn XPath. Trong ví dụ, `string(@sku)` làm rõ rằng hàm nhận chuỗi; nếu thiếu thuộc tính thì chuỗi là `""`, vì vậy mẫu mã sẽ không khớp.

Trong mô hình DOM với XPath 1.0, cần phân biệt:

| Đối số trong XPath | Dữ liệu cần dự kiến ở phía Java |
| --- | --- |
| `string(@sku)` hoặc `'BK-0001'` | `String` |
| `number(@amount)` hoặc `2` | Số XPath, thường là `Double` |
| `boolean(@enabled)` hoặc `true()` | `Boolean` |
| `@sku` hoặc `/catalog/product` | Tập nút, thường là `NodeList` với bộ xử lý DOM của JDK |

`@sku` không đồng nghĩa với `String`. Nếu hợp đồng hàm yêu cầu chuỗi, cách gọi có `string(...)` giúp tránh ép một tập nút thành chuỗi bằng phép ép kiểu Java sai. Tương tự, không ép một số XPath trực tiếp thành `Integer`. Hàm nên kiểm tra số đối số và kiểu nhận được, rồi chuyển đổi theo hợp đồng đã chọn.

Trong ví dụ, kết quả Java là `Boolean`: `true` giữ lại sản phẩm, `false` loại bỏ. Đừng trả chuỗi `"false"` thay cho `Boolean.FALSE`; theo quy tắc XPath, chuỗi không rỗng có thể được chuyển thành giá trị đúng. Cũng cần cẩn thận nếu trả số trong dấu `[...]`, vì điều kiện dạng số có ý nghĩa liên quan đến vị trí nút, không đơn thuần là đúng/sai.

Kết quả của hàm Java và kiểu yêu cầu khi gọi `XPathExpression.evaluate(..., XPathConstants.NODESET)` là hai lớp khác nhau. Hàm trả Boolean cho điều kiện; toàn biểu thức chọn ra tập sản phẩm, nên phía Java nhận `NodeList`. Các kiểu kết quả chuẩn và quy tắc chuyển đổi được mô tả trong [XPath API](https://docs.oracle.com/en/java/javase/25/docs/api/java.xml/javax/xml/xpath/XPath.html).

## 4. Ví dụ hoàn chỉnh chạy trên Java 17+

Lưu thành `XPathFunctionDemo.java`. Chương trình không cần thư viện ngoài. Nó dùng triển khai mặc định của JDK, đọc XML cố định trong bộ nhớ, đăng ký đúng một hàm và in những mã hợp lệ.

Quy tắc mã trong bài là quy tắc minh họa do ứng dụng tự đặt: `[A-Z]{2}-[0-9]{4}`. Hàm dùng `matches()`, vì vậy toàn bộ chuỗi phải khớp; khoảng trắng, chữ thường và thiếu ký tự đều không hợp lệ.

```java
import java.io.StringReader;
import java.util.Collections;
import java.util.Iterator;
import java.util.List;
import java.util.Map;
import java.util.regex.Pattern;
import javax.xml.XMLConstants;
import javax.xml.namespace.NamespaceContext;
import javax.xml.namespace.QName;
import javax.xml.parsers.DocumentBuilderFactory;
import javax.xml.xpath.XPath;
import javax.xml.xpath.XPathConstants;
import javax.xml.xpath.XPathFunction;
import javax.xml.xpath.XPathFunctionException;
import javax.xml.xpath.XPathFunctionResolver;
import javax.xml.xpath.XPathFactory;
import org.w3c.dom.Document;
import org.w3c.dom.Element;
import org.w3c.dom.NodeList;
import org.xml.sax.InputSource;

public class XPathFunctionDemo {
    private static final String NS = "urn:example:catalog-functions:v1";
    private static final QName VALID_SKU = new QName(NS, "valid-sku");
    private static final Pattern SKU = Pattern.compile("[A-Z]{2}-[0-9]{4}");

    private static final XPathFunction VALID_SKU_FUNCTION = args -> {
        if (args == null || args.size() != 1
                || !(args.get(0) instanceof String text)) {
            throw new XPathFunctionException(
                    "valid-sku requires exactly one string argument");
        }
        return SKU.matcher(text).matches();
    };

    private static final XPathFunctionResolver FUNCTIONS = (name, arity) -> {
        if (VALID_SKU.equals(name) && arity == 1) {
            return VALID_SKU_FUNCTION;
        }
        return null;
    };

    private static final class Namespaces implements NamespaceContext {
        private final Map<String, String> bindings = Map.of(
                "ext", NS,
                XMLConstants.XML_NS_PREFIX, XMLConstants.XML_NS_URI,
                XMLConstants.XMLNS_ATTRIBUTE, XMLConstants.XMLNS_ATTRIBUTE_NS_URI
        );

        @Override
        public String getNamespaceURI(String prefix) {
            if (prefix == null) {
                throw new IllegalArgumentException("prefix is null");
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
                throw new IllegalArgumentException("namespaceURI is null");
            }
            List<String> prefixes = bindings.entrySet().stream()
                    .filter(e -> namespaceURI.equals(e.getValue()))
                    .map(Map.Entry::getKey)
                    .toList();
            return Collections.unmodifiableList(prefixes).iterator();
        }
    }

    public static void main(String[] args) throws Exception {
        String xml = """
                <catalog>
                  <product sku="BK-0001"/>
                  <product sku="bad-code"/>
                  <product sku="AB-0123"/>
                  <product/>
                </catalog>
                """;

        DocumentBuilderFactory dom = DocumentBuilderFactory.newDefaultInstance();
        dom.setNamespaceAware(true);
        dom.setFeature(XMLConstants.FEATURE_SECURE_PROCESSING, true);
        dom.setFeature(
                "http://apache.org/xml/features/disallow-doctype-decl", true);
        dom.setAttribute(XMLConstants.ACCESS_EXTERNAL_DTD, "");
        dom.setAttribute(XMLConstants.ACCESS_EXTERNAL_SCHEMA, "");
        dom.setXIncludeAware(false);
        Document document = dom.newDocumentBuilder().parse(
                new InputSource(new StringReader(xml)));

        XPathFactory factory = XPathFactory.newDefaultInstance();
        // Only this trusted, application-authored XPath uses extension functions.
        factory.setFeature(XMLConstants.FEATURE_SECURE_PROCESSING, false);

        XPath xpath = factory.newXPath();
        xpath.setNamespaceContext(new Namespaces());
        xpath.setXPathFunctionResolver(FUNCTIONS);

        var expression = xpath.compile(
                "/catalog/product[ext:valid-sku(string(@sku))]");
        NodeList products = (NodeList) expression.evaluate(
                document, XPathConstants.NODESET);

        System.out.println("valid=" + products.getLength());
        for (int i = 0; i < products.getLength(); i++) {
            Element product = (Element) products.item(i);
            System.out.println(product.getAttribute("sku"));
        }

        boolean known = FUNCTIONS.resolveFunction(VALID_SKU, 1) != null;
        boolean wrongArity = FUNCTIONS.resolveFunction(VALID_SKU, 2) == null;
        System.out.println("known=" + known);
        System.out.println("wrong-arity-rejected=" + wrongArity);
    }
}
```

Biên dịch và chạy trong thư mục chứa tệp:

```shell
javac --release 17 -encoding UTF-8 XPathFunctionDemo.java
java XPathFunctionDemo
```

Stdout:

```text
valid=2
BK-0001
AB-0123
known=true
wrong-arity-rejected=true
```

`bad-code` không khớp mẫu. `product` thiếu `sku` cung cấp chuỗi rỗng, nên cũng bị loại. Hai dòng cuối xác nhận bộ phân giải tìm thấy đúng tên với một đối số và từ chối cùng tên với hai đối số. Chúng không khẳng định bộ xử lý XPath đã gọi bộ phân giải bao nhiêu lần.

Điểm cần đọc trong mã:

1. `VALID_SKU` lưu tên mở rộng; `QName.equals()` giúp tránh gắn hành vi vào chữ `ext`.
2. `FUNCTIONS` chỉ chấp nhận đúng tên và số đối số. `VALID_SKU_FUNCTION` vẫn kiểm tra danh sách lúc thực thi để bảo vệ hợp đồng của chính hàm.
3. Namespace và bộ phân giải được gắn trước `compile()`. Cấu hình đầy đủ trước khi biên dịch, thay vì hy vọng sửa cấu hình về sau sẽ cập nhật mọi biểu thức đã có.
4. `Pattern` được tái sử dụng, còn mỗi lần gọi tạo `Matcher` riêng. Hàm không sửa cây XML và không phụ thuộc vào thứ tự gọi.
5. Cấu hình bộ đọc DOM và cấu hình `XPathFactory` là hai việc riêng. Lý do bật/tắt `FEATURE_SECURE_PROCESSING` khác nhau được giải thích ngay bên dưới.

## 5. Bảo mật: hàm mở rộng là quyền gọi mã Java

Theo hợp đồng `XPathFactory.setFeature`, khi `XMLConstants.FEATURE_SECURE_PROCESSING` bằng `true`, việc tham chiếu hàm mở rộng bị chặn; bộ xử lý không được gọi `XPathFunctionResolver` và phải báo `XPathFunctionException`. Đây có thể là lý do hàm đã đăng ký đúng vẫn không chạy. Xem [hợp đồng cấu hình XPathFactory](https://docs.oracle.com/en/java/javase/17/docs/api/java.xml/javax/xml/xpath/XPathFactory.html#setFeature(java.lang.String,boolean)).

Ví dụ đặt `false` **chỉ cho factory tạo XPath dành cho biểu thức cố định do ứng dụng kiểm soát**. Quyết định này mở quyền dùng hàm mở rộng, không phải một thiết lập nên áp dụng đại trà cho mọi truy vấn XML. Nếu yêu cầu hệ thống bắt buộc giữ chế độ xử lý an toàn và không cho hàm mở rộng, hãy chọn dữ liệu bằng XPath có sẵn rồi kiểm tra mã sản phẩm bằng Java bên ngoài XPath.

Bộ đọc DOM trong ví dụ vẫn bật xử lý an toàn, từ chối `DOCTYPE`, chặn truy cập DTD/schema bên ngoài và tắt XInclude. Việc tắt xử lý an toàn trên factory XPath không tự thay đổi một DOM đã được đọc bằng factory riêng. Ngược lại, tắt hàm mở rộng không tự giải quyết mọi rủi ro của bước đọc XML. Các biện pháp cho bước phân tích XML được trình bày trong [JAXP Security Guide](https://docs.oracle.com/en/java/javase/25/security/java-api-xml-processing-jaxp-security-guide.html).

Khi dùng hàm mở rộng trong ứng dụng:

- Giữ một danh sách hàm được phép nhỏ và rõ, như phép so khớp `QName` cùng `arity` trong ví dụ.
- Không biến tên hàm/đối số từ người dùng thành tên lớp hay phương thức gọi qua reflection.
- Không ghép dữ liệu nhập vào thành cú pháp XPath. Dùng biểu thức cố định và biến XPath khi cần truyền giá trị; biến truyền dữ liệu, bộ phân giải hàm cung cấp hành vi.
- Ưu tiên hàm tính toán thuần, thời gian chạy có giới hạn; tránh đọc tệp, truy cập mạng, gửi thư, ghi giao dịch hoặc sửa dữ liệu từ bên trong hàm.
- Kiểm thử trên JDK và bộ cung cấp XPath thực tế của ứng dụng; cấu hình bổ sung của từng bộ cung cấp không phải hợp đồng chung của JAXP.

Không dựa vào một cờ toàn JVM để lặng lẽ vượt qua chính sách xử lý an toàn. Cấu hình cho phép hàm phải là quyết định rõ ràng tại nơi tạo bộ xử lý và được đánh giá cùng mức độ tin cậy của biểu thức.

## 6. Lỗi thường gặp và cách phân biệt

| Hiện tượng | Nguyên nhân cần kiểm tra | Cách xử lý |
| --- | --- | --- |
| Tiền tố `ext` không được nhận diện | Chưa gắn `NamespaceContext` hoặc URI ánh xạ sai | Đăng ký ngữ cảnh trước khi biên dịch; đối chiếu đúng URI |
| Không tìm thấy hàm | Sai local part, namespace URI hoặc số đối số; bộ phân giải trả `null` | Kiểm tra ba thông tin định danh, không chỉ chuỗi tên hiển thị |
| Hàm không được gọi dù tên đúng | Chế độ xử lý an toàn chặn hàm mở rộng | Kiểm tra cấu hình và chính sách; cân nhắc xử lý Java sau truy vấn |
| Lỗi ép kiểu trong hàm | Truyền tập nút hoặc số trong khi mã đòi chuỗi | Sửa hợp đồng và dùng chuyển đổi XPath rõ ràng như `string(...)` |
| Trả `"false"` nhưng nút vẫn được chọn | Hàm trả chuỗi không rỗng | Trả `Boolean`, không trả chữ mô tả Boolean |
| Kết quả phụ thuộc thứ tự/thời điểm gọi | Hàm có tác dụng phụ hoặc phụ thuộc trạng thái thay đổi | Chuyển phần tác dụng phụ ra ngoài bước đánh giá XPath |

Nếu đối số không đáp ứng hợp đồng, ném `XPathFunctionException` với thông báo rõ. Ở biên đánh giá biểu thức, xử lý `XPathExpressionException` và kiểm tra nguyên nhân khi cần chẩn đoán; `XPathFunctionException` là một lớp con của nó. Đừng ghi cứng thông báo lỗi của một JDK làm giao kèo của ứng dụng, và đừng nuốt lỗi để trả `true`.

Thời điểm phát hiện lỗi có thể phụ thuộc bộ xử lý và đường gọi: cấu hình phải có trước biên dịch, nhưng vẫn cần xử lý lỗi lúc đánh giá. Không thiết kế nghiệp vụ dựa trên giả định rằng mọi lỗi hàm đều chắc chắn xuất hiện tại `compile()`.

Javadoc của `XPathFunction` không đảm bảo thứ tự hay số lần gọi hàm mở rộng. Vì vậy, đếm số lần gọi để cập nhật tiền, ghi nhật ký nghiệp vụ bắt buộc hoặc phát sinh mã định danh trong hàm là thiết kế dễ sai. Xem [XPathFunction.evaluate](https://docs.oracle.com/en/java/javase/25/docs/api/java.xml/javax/xml/xpath/XPathFunction.html#evaluate(java.util.List)).

`XPath` và `XPathExpression` không bảo đảm an toàn khi nhiều luồng dùng đồng thời và không hỗ trợ gọi lồng trở lại cùng bộ đánh giá. Trong dịch vụ, tạo đối tượng theo phạm vi xử lý phù hợp hoặc đồng bộ hóa có chủ đích; không chia sẻ một biểu thức duy nhất cho mọi luồng chỉ vì đã biên dịch nó một lần.

## 7. Tự kiểm chứng

Thay đổi từng điểm một trong ví dụ, rồi giải thích kết quả trước khi chạy:

1. Đổi `BK-0001` thành `bk-0001`: số mã hợp lệ còn `1`, vì quy tắc yêu cầu chữ hoa.
2. Đổi `string(@sku)` thành `@sku`: hàm đang yêu cầu `String`, nên cần báo lỗi hợp đồng đối số thay vì ép kiểu mù.
3. Đổi `ext:valid-sku(...)` thành `ext:valid-sku(..., 'extra')`: bộ phân giải không có hàm hai đối số.
4. Đổi URI của tiền tố `ext` nhưng giữ nguyên `VALID_SKU`: tên mở rộng không còn khớp, dù local part vẫn là `valid-sku`.
5. Bật `FEATURE_SECURE_PROCESSING` trên `XPathFactory`: lời gọi hàm mở rộng phải bị chặn theo hợp đồng API.

Tiêu chí hoàn thành là giải thích được ai chọn nút, ai tìm hàm, ai đánh giá quy tắc, và vì sao kết quả Boolean của hàm làm bộ lọc giữ hoặc loại từng sản phẩm.
