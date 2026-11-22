# Biến XPath qua XPathVariableResolver

## 1. Từ câu truy vấn cố định đến tham số dữ liệu

Giả sử ứng dụng cần tìm sách theo tên và giá tối thiểu. Cấu trúc truy vấn không đổi; tên sách, giá và điều kiện còn hàng thay đổi theo từng yêu cầu. Biến XPath giúp truyền các giá trị ấy vào biểu thức mà không phải ghép chúng thành mã truy vấn.

Trong Java, `XPathVariableResolver` nối tên biến XPath với giá trị do ứng dụng cung cấp. Ví dụ dưới đây dùng API chuẩn `javax.xml.xpath` và DOM, chạy trên Java 17+. Các API này vẫn có trong Java hiện hành; tên package `javax.xml.xpath` không phải lý do để đổi sang một package `jakarta.xml.xpath`.

Biểu thức mẫu:

```xpath
/catalog/book[title = $title and number(@price) >= $minPrice]/@id
```

- `$title`: tên sách cần tìm.
- `$minPrice`: giá tối thiểu.
- `title`: phần tử con của sách, không phải biến.
- `@id`: thuộc tính được chọn làm kết quả.

Biến là dữ liệu đầu vào của một biểu thức, không phải cơ chế thay thế chuỗi hoặc tạo đường dẫn động.

## 2. Vì sao không ghép giá trị trực tiếp?

Đoạn sau chỉ minh họa cách cần tránh:

```java
String query = "/catalog/book[title = '" + userTitle + "']/@id";
```

Tên sách chứa dấu nháy đơn có thể làm hỏng cú pháp. Nếu nhận đầu vào từ người dùng, cách ghép chuỗi còn có thể khiến dữ liệu trở thành điều kiện XPath ngoài ý muốn.

Thay vào đó, giữ nguyên cấu trúc:

```xpath
/catalog/book[title = $title]/@id
```

Ứng dụng cấp một `String` cho biến `title`. Dấu nháy trong giá trị không cần biến thành cú pháp XPath. Trong chương trình ở phần 4, tên sách chứa đồng thời dấu nháy đơn và dấu nháy kép; một chuỗi có dạng điều kiện XPath cũng được thử như dữ liệu bình thường.

Không đặt biến trong dấu nháy:

```xpath
/catalog/book[title = '$title']/@id
```

Biểu thức trên so sánh tên sách với chuỗi ký tự `$title`, không đọc biến.

## 3. Hợp đồng của bộ phân giải biến

Phương thức cần cài đặt:

```java
Object resolveVariable(QName variableName);
```

Với `$title`, bộ phân giải nhận `new QName("title")`: tên không chứa ký tự `$`. Khi không biết biến, trả `null`; đó là dấu hiệu không phân giải được, không phải giá trị XPath null hợp lệ. Tham số `variableName == null` phải gây `NullPointerException`.

Giá trị của mỗi biến phải giữ nguyên trong suốt một lần đánh giá. Có thể thay bộ giá trị giữa hai lần đánh giá đã kết thúc. Không dựa vào giả định rằng bộ phân giải chỉ được gọi đúng một lần cho mỗi biến. [Hợp đồng XPathVariableResolver](https://docs.oracle.com/en/java/javase/21/docs/api/java.xml/javax/xml/xpath/XPathVariableResolver.html).

Trình tự sử dụng là tạo `XPath`, gắn bộ phân giải, rồi biên dịch biểu thức. Biểu thức đã biên dịch dùng bộ phân giải có hiệu lực khi biên dịch; thay bộ phân giải trên đối tượng `XPath` sau đó không phải cách cập nhật một biểu thức đã có. [XPath.compile và cấu hình biến](https://docs.oracle.com/en/java/javase/21/docs/api/java.xml/javax/xml/xpath/XPath.html#compile(java.lang.String)).

## 4. Chương trình hoàn chỉnh: ba biến và một biểu thức tái sử dụng

Lưu toàn bộ mã sau thành `XPathVariablesDemo.java`. Chương trình chỉ dùng thư viện chuẩn JDK, không cần dependency bên ngoài.

```java
import java.io.StringReader;
import java.util.Map;
import java.util.Objects;
import javax.xml.namespace.QName;
import javax.xml.parsers.DocumentBuilderFactory;
import javax.xml.xpath.XPath;
import javax.xml.xpath.XPathConstants;
import javax.xml.xpath.XPathExpression;
import javax.xml.xpath.XPathExpressionException;
import javax.xml.xpath.XPathFactory;
import javax.xml.xpath.XPathVariableResolver;
import org.w3c.dom.Document;
import org.w3c.dom.NodeList;
import org.xml.sax.InputSource;

public class XPathVariablesDemo {
    private static final QName TITLE = new QName("title");
    private static final QName MIN_PRICE = new QName("minPrice");
    private static final QName AVAILABLE = new QName("available");

    static final class Bindings implements XPathVariableResolver {
        private Map<QName, Object> values;

        Bindings(Map<QName, Object> values) {
            replace(values);
        }

        void replace(Map<QName, Object> next) {
            values = Map.copyOf(next);
        }

        @Override
        public Object resolveVariable(QName variableName) {
            return values.get(Objects.requireNonNull(variableName, "variableName"));
        }
    }

    static Map<QName, Object> parameters(String title, double minPrice) {
        return Map.of(TITLE, title, MIN_PRICE, minPrice, AVAILABLE, true);
    }

    static void printIds(String label, XPathExpression expression,
                         Document document) throws XPathExpressionException {
        NodeList ids = (NodeList) expression.evaluate(document, XPathConstants.NODESET);
        StringBuilder result = new StringBuilder();
        for (int i = 0; i < ids.getLength(); i++) {
            if (i > 0) {
                result.append(", ");
            }
            result.append(ids.item(i).getNodeValue());
        }
        System.out.println(label + ": " + ids.getLength() + " [" + result + "]");
    }

    public static void main(String[] args) throws Exception {
        String xml = """
                <catalog>
                  <book id="b1" price="35" available="true">
                    <title>O'Reilly "Java"</title>
                  </book>
                  <book id="b2" price="50" available="true">
                    <title>XPath Foundations</title>
                  </book>
                  <book id="b3" price="75" available="true">
                    <title>O'Reilly "Java"</title>
                  </book>
                </catalog>
                """;

        // XML co dinh trong ma nguon, chi phuc vu vi du.
        DocumentBuilderFactory factory = DocumentBuilderFactory.newInstance();
        factory.setNamespaceAware(true);
        Document document = factory.newDocumentBuilder()
                .parse(new InputSource(new StringReader(xml)));

        Bindings bindings = new Bindings(parameters("O'Reilly \"Java\"", 30.0));
        XPath xpath = XPathFactory.newDefaultInstance().newXPath();
        xpath.setXPathVariableResolver(bindings);

        XPathExpression expression = xpath.compile(
                "/catalog/book[title = $title"
                + " and number(@price) >= $minPrice"
                + " and (@available = 'true') = $available]/@id");

        printIds("minPrice=30", expression, document);

        bindings.replace(parameters("O'Reilly \"Java\"", 60.0));
        printIds("minPrice=60", expression, document);

        bindings.replace(parameters("' or 1 = 1 or '", 0.0));
        printIds("input-as-data", expression, document);

        bindings.replace(Map.of(MIN_PRICE, 0.0, AVAILABLE, true));
        try {
            expression.evaluate(document, XPathConstants.NODESET);
            throw new AssertionError("Expected missing-variable failure");
        } catch (XPathExpressionException expected) {
            System.out.println("missing-title: XPathExpressionException");
        }
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 XPathVariablesDemo.java
java XPathVariablesDemo
```

Kết quả:

```text
minPrice=30: 2 [b1, b3]
minPrice=60: 1 [b3]
input-as-data: 0 []
missing-title: XPathExpressionException
```

Cách đọc ví dụ:

1. `parameters(...)` cung cấp tên sách bằng `String`, giá bằng `Double` do tự đóng hộp `double`, và tình trạng còn hàng bằng `Boolean`.
2. `Bindings` giữ một bản sao không cho sửa cấu trúc bằng `Map.copyOf`. Các giá trị trong ví dụ đều bất biến.
3. Bộ phân giải được gắn trước `compile`. Chương trình chỉ biên dịch một biểu thức rồi dùng lại theo thứ tự.
4. Lần đầu, cả `b1` giá 35 và `b3` giá 75 đạt ngưỡng 30.
5. Sau khi lần đánh giá trước kết thúc, `replace` đổi sang ngưỡng 60; chỉ `b3` phù hợp. Tham chiếu đến đối tượng `Bindings` vẫn giữ nguyên.
6. Chuỗi `' or 1 = 1 or '` không trùng tên sách nào. Nó không được phân tích như một đoạn biểu thức, nên kết quả rỗng.
7. Lần cuối cố ý bỏ biến `title`. Bộ phân giải trả `null`; chương trình bắt lỗi dự kiến để minh họa rõ sự khác nhau giữa “không có sách phù hợp” và “thiếu tham số”.

`Map.copyOf` là bản sao nông: nếu đưa vào giá trị có thể thay đổi như DOM hoặc bộ sưu tập tự tạo, bản thân các đối tượng đó không tự trở thành bất biến. Lớp `Bindings` ở đây phục vụ việc đánh giá tuần tự, không dùng chung giữa các luồng.

XML trong chương trình là hằng do tác giả kiểm soát. Khi nhận XML bên ngoài, cấu hình an toàn của trình phân tích XML là trách nhiệm riêng; biến XPath không thay thế cấu hình ấy.

## 5. Kiểu biến khác với kiểu kết quả

Trong ví dụ, `XPathConstants.NODESET` yêu cầu kết quả là `NodeList`. Nó không quy định mọi biến đầu vào phải có kiểu `NodeList`.

API chuẩn hướng đến XPath 1.0. Với mô hình DOM của JDK, nên bắt đầu bằng các kiểu đơn giản:

| Dữ liệu truyền vào | Biểu diễn trong ví dụ | Cách dùng |
|---|---|---|
| Văn bản | `String` | `title = $title` |
| Số | `Double` | `number(@price) >= $minPrice` |
| Đúng/sai | `Boolean` | `(@available = 'true') = $available` |

Không mặc định mọi đối tượng Java như `List<String>`, `LocalDate` hay một đối tượng nghiệp vụ đều có phép chuyển đổi chuẩn sang XPath. Với biến chứa nút hoặc tập nút, cần chọn kiểu phù hợp với mô hình dữ liệu và bộ thực thi đang dùng. [Các kiểu dữ liệu và mô hình XPath của Java](https://docs.oracle.com/en/java/javase/21/docs/api/java.xml/javax/xml/xpath/package-summary.html).

Có hai điểm dễ gây sai kết quả:

- `boolean(@available)` kiểm tra thuộc tính có tồn tại hay không. Thuộc tính `available="false"` vẫn tồn tại. Ví dụ dùng `@available = 'true'` để đọc quy ước giá trị của tài liệu.
- Một số đứng trực tiếp trong predicate biểu thị vị trí. `/catalog/book[$n]` với `$n = 2.0` chọn sách thứ hai; nó không có nghĩa “số 2 là true nên lấy mọi sách”. Viết `[position() = $n]` nếu muốn thể hiện ý định chọn vị trí rõ hơn.

Số của XPath 1.0 dùng mô hình dấu phẩy động; không coi phép so sánh giá trong ví dụ là giải pháp tính toán tiền tệ chính xác. Đây là dữ liệu minh họa với giá nguyên nhỏ. [Quy tắc predicate, boolean và number của XPath 1.0](https://www.w3.org/TR/1999/REC-xpath-19991116/).

## 6. Tên biến có namespace

`QName` gồm namespace URI và tên cục bộ. Tên biến không có tiền tố như `$title` thuộc namespace rỗng. Nếu biểu thức dùng `$arg:title`, cần:

1. Gắn `NamespaceContext` cho `XPath` trước khi biên dịch, ánh xạ tiền tố `arg` sang URI, chẳng hạn `urn:example:query-parameters`.
2. Trong bộ tham số, dùng khóa `new QName("urn:example:query-parameters", "title")`.
3. Không dùng `new QName("arg:title")`: đó là tên cục bộ chứa dấu hai chấm, không phải cặp URI/tên mong muốn.

Tiền tố là cách viết trong biểu thức. Hai tiền tố được ánh xạ về cùng URI và cùng tên cục bộ chỉ cùng một tên biến. Vì vậy, tra bằng `Map<QName, Object>` thường rõ hơn tra riêng `variableName.getLocalPart()`, vốn có thể làm lẫn các biến ở namespace khác nhau.

Namespace của biến không tự khai báo namespace cho phần tử XML. Khi XML có namespace, đường dẫn chọn phần tử cũng phải được cấu hình và viết đúng tương ứng. Ví dụ ở phần 4 dùng XML không có namespace để tập trung vào cơ chế biến. [QName và quy tắc so sánh tên](https://docs.oracle.com/en/java/javase/21/docs/api/java.xml/javax/xml/namespace/QName.html), [NamespaceContext](https://docs.oracle.com/en/java/javase/21/docs/api/java.xml/javax/xml/namespace/NamespaceContext.html).

## 7. Giới hạn và lỗi phổ biến

| Hiện tượng | Nguyên nhân cần kiểm tra | Cách xử lý |
|---|---|---|
| Không phân giải được biến | Chưa gắn resolver, sai `QName`, hoặc thiếu khóa | Kiểm tra tên, namespace và đủ tham số trước khi đánh giá |
| Kết quả rỗng khi tưởng đã truyền tên | Viết `'$title'` | Dùng `$title` không có dấu nháy |
| Thay resolver nhưng biểu thức cũ vẫn dùng cấu hình cũ | Resolver gắn sau `compile` | Gắn trước khi biên dịch; quản lý vòng đời biểu thức rõ ràng |
| Kết quả thay đổi khó tái hiện | Giá trị biến hoặc DOM bị sửa trong lúc đánh giá | Giữ ổn định toàn bộ dữ liệu của lần đánh giá |
| Lọc boolean sai | Nhầm sự tồn tại của thuộc tính với nội dung của nó | So sánh với quy ước văn bản như `'true'` |
| Lỗi ép kiểu kết quả | Xin kết quả `STRING` rồi ép thành `NodeList` | Chọn `NODESET` nếu cần danh sách nút |

Nếu một biến cần thiết không được phân giải, việc đánh giá có thể báo `XPathExpressionException`; không nên bắt lỗi rồi tự trả danh sách rỗng, vì sẽ che lỗi cấu hình. `XPath` và `XPathExpression` không bảo đảm an toàn khi nhiều luồng dùng đồng thời và không cho đánh giá đệ quy trên cùng đối tượng đang hoạt động. Trong dịch vụ web, nên tách đối tượng theo yêu cầu hoặc có cơ chế quản lý độc quyền thích hợp. [Hợp đồng đánh giá XPathExpression](https://docs.oracle.com/en/java/javase/21/docs/api/java.xml/javax/xml/xpath/XPathExpression.html).

Biến chỉ biểu diễn giá trị, không thay thế tùy ý cú pháp truy vấn. Không thể truyền chuỗi `"book"` rồi kỳ vọng `/catalog/$element` tự biến thành `/catalog/book`. Với nhu cầu chọn tên phần tử, có thể thiết kế một biểu thức cố định như `/catalog/*[local-name() = $local and namespace-uri() = $uri]`, hoặc chọn trong tập biểu thức do ứng dụng kiểm soát. Chỉ dùng `local-name()` mà bỏ namespace có thể ghép nhầm các phần tử khác nghĩa.

Tách tham số khỏi biểu thức chỉ bảo vệ phần dữ liệu được truyền qua biến. Nếu ứng dụng vẫn nối một phần đầu vào khác thành toán tử, tên trục hoặc cả biểu thức, phần đó vẫn là mã truy vấn cần kiểm soát.

## 8. Thực hành

Dùng chương trình ở phần 4 để kiểm tra từng thay đổi độc lập:

1. Đổi ngưỡng 60 thành 80. Kỳ vọng không sách nào phù hợp.
2. Truyền `AVAILABLE = false` nhưng giữ cả ba sách có `available="true"`. Kỳ vọng không sách nào phù hợp.
3. Đổi riêng sách `b3` thành `available="false"`, đặt ngưỡng 60 và biến `AVAILABLE = false`. Kỳ vọng chọn `b3`.
4. Đổi khóa `new QName("title")` thành `new QName("Title")` mà vẫn giữ `$title`. Giải thích vì sao đây là thiếu biến, không phải một truy vấn hợp lệ có kết quả rỗng.
5. Trước khi bổ sung truy vấn mới, chỉ ra phần nào là cấu trúc cố định và phần nào cần thành biến. Kiểm tra ít nhất dữ liệu có dấu nháy, không có kết quả và thiếu tham số.
