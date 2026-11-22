# Phân biệt truyền giá trị bằng biến với ghép biểu thức từ dữ liệu ngoài

## 1. Ranh giới cần giữ: cấu trúc truy vấn và giá trị tìm kiếm

Khi ứng dụng tìm một người theo tên trong XML, có hai thứ khác nhau:

- **Cấu trúc truy vấn** quyết định đi qua nút nào, so sánh thuộc tính nào và dùng toán tử nào.
- **Giá trị tìm kiếm** là dữ liệu cần so sánh, chẳng hạn `alice` hoặc `O'Reilly`.

Ứng dụng nên kiểm soát cấu trúc và truyền dữ liệu vào các vị trí biến. Nếu nối dữ liệu ngoài vào chuỗi XPath, bộ phân tích cú pháp không biết phần nào là tên người và phần nào là toán tử do người nhập thêm. Lỗi có thể chỉ là hỏng dấu nháy, nhưng cũng có thể làm thay đổi ý nghĩa truy vấn — chèn mã XPath (XPath injection).

So sánh hai cách viết:

```java
// Không an toàn: input trở thành một phần mã nguồn XPath.
String query = "/directory/person[@name='" + input + "']";
```

```xpath
/directory/person[@name=$name]
```

Ở cách thứ hai, chuỗi XPath giữ nguyên. Java cung cấp giá trị cho biến có tên `name` bằng `XPathVariableResolver`; giá trị không được chèn ngược vào chuỗi rồi phân tích lại như cú pháp.

Nguyên tắc này vẫn áp dụng với JAXP hiện đại trong `javax.xml.xpath`. Không cần một API nội bộ của JDK hoặc tự xây dựng bộ thay thế dấu nháy. Hướng phòng ngừa được nêu tại [OWASP XPath Injection Prevention](https://cheatsheetseries.owasp.org/cheatsheets/XPath_Injection_Prevention_Cheat_Sheet.html).

## 2. Tại sao nối chuỗi làm thay đổi truy vấn?

Giả sử chương trình tạo truy vấn theo mẫu:

```java
String query = "/directory/person[@name='" + input + "']";
```

Với `input` bằng `alice`, nó tạo biểu thức hợp lệ:

```xpath
/directory/person[@name='alice']
```

Nhưng với tên hợp lệ `O'Reilly`, kết quả là:

```xpath
/directory/person[@name='O'Reilly']
```

Dấu nháy trong họ đã đóng chuỗi sớm, khiến biểu thức sai cú pháp. Đây là lỗi chức năng ngay cả khi người nhập không có ý định gây hại.

Nếu dữ liệu là chuỗi sau:

```text
' or '1'='1
```

biểu thức ghép trở thành:

```xpath
/directory/person[@name='' or '1'='1']
```

Điều kiện bên phải `or` luôn đúng, nên truy vấn chọn mọi `person` dưới `directory`, bất kể tên. Đây không còn là lỗi dấu nháy đơn thuần: người cung cấp dữ liệu đã điều khiển toán tử và điều kiện.

Với biểu thức cố định `[@name=$name]`, cùng chuỗi đó chỉ là một tên cần tìm. Nếu không có người tên chính xác như vậy, kết quả rỗng. Bộ xử lý không hiểu từ `or` nằm bên trong giá trị biến là toán tử. Tình huống cho thấy cơ chế của [XPath injection](https://community.owasp.org/attacks/XPATH_Injection).

## 3. Truyền giá trị bằng XPathVariableResolver trong Java

Cơ chế JAXP gồm ba bước:

1. Viết XPath cố định với tham chiếu biến như `$name`.
2. Gắn bộ phân giải biến trước khi biên dịch biểu thức.
3. Khi đánh giá, bộ phân giải cung cấp giá trị đúng kiểu cho tên biến được yêu cầu.

Phương thức của bộ phân giải là:

```java
Object resolveVariable(QName variableName);
```

`$` thuộc cú pháp tham chiếu biến; nó không thuộc tên trong `QName`. Với `$name` không có tiền tố, dùng `new QName("name")`. Không dùng `new QName("$name")`.

Bộ phân giải nên chỉ nhận những tên biến mà ứng dụng định nghĩa. Nếu không có biến tương ứng, trả `null`; khi biểu thức cần biến mà không tìm được giá trị, JAXP báo `XPathExpressionException`. Đừng biến lỗi cấu hình thành một truy vấn rộng hơn hoặc bỏ điều kiện lọc.

Đối với bài này, hợp đồng dữ liệu là `String`, nên giá trị có dấu nháy vẫn là chuỗi bình thường. `""` là chuỗi rỗng hợp lệ về mặt kỹ thuật; `null` không phải một cách biểu diễn chuỗi rỗng cho bộ phân giải. Nếu nghiệp vụ cấm chuỗi rỗng hoặc chỉ chứa khoảng trắng, hãy kiểm tra riêng trước khi truy vấn.

Giá trị một biến phải giữ nguyên trong suốt **một lần đánh giá**. Không lấy giá trị từ một đối tượng đang bị luồng khác sửa. Hợp đồng này được mô tả trong [XPathVariableResolver](https://docs.oracle.com/en/java/javase/25/docs/api/java.xml/javax/xml/xpath/XPathVariableResolver.html).

## 4. Ví dụ hoàn chỉnh: dữ liệu bình thường, dấu nháy và chuỗi có hình thức toán tử

Lưu chương trình thành `XPathBindingDemo.java`. Ví dụ dùng dữ liệu danh bạ giả lập trong bộ nhớ; phương thức nối chuỗi cố ý không an toàn chỉ dùng để quan sát khác biệt. Trong mã ứng dụng, dùng nhánh truyền biến.

```java
import java.io.StringReader;
import java.util.Objects;
import javax.xml.XMLConstants;
import javax.xml.namespace.QName;
import javax.xml.parsers.DocumentBuilderFactory;
import javax.xml.xpath.XPath;
import javax.xml.xpath.XPathConstants;
import javax.xml.xpath.XPathExpressionException;
import javax.xml.xpath.XPathFactory;
import org.w3c.dom.Document;
import org.w3c.dom.NodeList;
import org.xml.sax.InputSource;

public class XPathBindingDemo {
    private static final String QUERY = "/directory/person[@name=$name]";
    private static final QName NAME = new QName("name");

    private static XPath newXPath() throws Exception {
        XPathFactory factory = XPathFactory.newDefaultInstance();
        factory.setFeature(XMLConstants.FEATURE_SECURE_PROCESSING, true);
        return factory.newXPath();
    }

    private static int boundCount(Document document, String input)
            throws Exception {
        String value = Objects.requireNonNull(input, "name");
        XPath xpath = newXPath();
        xpath.setXPathVariableResolver(variable ->
                NAME.equals(variable) ? value : null);
        var expression = xpath.compile(QUERY);
        NodeList nodes = (NodeList) expression.evaluate(
                document, XPathConstants.NODESET);
        return nodes.getLength();
    }

    // Deliberately unsafe: only for comparison in this local example.
    private static String concatenatedCount(Document document, String input)
            throws Exception {
        String query = "/directory/person[@name='" + input + "']";
        try {
            var expression = newXPath().compile(query);
            NodeList nodes = (NodeList) expression.evaluate(
                    document, XPathConstants.NODESET);
            return Integer.toString(nodes.getLength());
        } catch (XPathExpressionException ex) {
            return "ERROR";
        }
    }

    private static void compare(Document document, String label, String input)
            throws Exception {
        System.out.println(label
                + ": concatenated=" + concatenatedCount(document, input)
                + ", bound=" + boundCount(document, input));
    }

    public static void main(String[] args) throws Exception {
        String xml = """
                <directory>
                  <person name="alice"/>
                  <person name="O'Reilly"/>
                  <person name="Sam &quot;S&quot; O'Reilly"/>
                </directory>
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

        compare(document, "normal", "alice");
        compare(document, "apostrophe", "O'Reilly");
        compare(document, "both-quotes", "Sam \"S\" O'Reilly");
        compare(document, "syntax-text", "' or '1'='1");
        compare(document, "empty", "");
    }
}
```

Biên dịch và chạy trong thư mục chứa tệp:

```shell
javac --release 17 -encoding UTF-8 XPathBindingDemo.java
java XPathBindingDemo
```

Stdout:

```text
normal: concatenated=1, bound=1
apostrophe: concatenated=ERROR, bound=1
both-quotes: concatenated=ERROR, bound=1
syntax-text: concatenated=3, bound=0
empty: concatenated=0, bound=0
```

Ý nghĩa từng trường hợp:

- `normal`: dữ liệu đơn giản làm cả hai cách có vẻ đúng; vì vậy thử riêng chữ và số chưa phát hiện được lỗi.
- `apostrophe`: một họ có dấu nháy đơn làm nối chuỗi sai cú pháp; biến vẫn so sánh chính xác và tìm được một người.
- `both-quotes`: tên chứa cả nháy đơn lẫn nháy kép vẫn được truyền nguyên vẹn bằng biến.
- `syntax-text`: cách nối chuỗi chọn cả ba người; cách truyền biến tìm một tên không có trong dữ liệu và trả về không nút nào.
- `empty`: không có `person` mang thuộc tính `name` rỗng trong dữ liệu mẫu, nên cả hai kết quả bằng `0`.

`ERROR` là nhãn chương trình tự in khi bắt `XPathExpressionException`, không phải thông báo lỗi chuẩn của JDK. Nhánh truyền biến không nuốt lỗi: nếu cấu hình sai, chương trình sẽ báo lỗi để sửa.

### Vì sao tên chứa dấu nháy kép được tìm đúng?

Trong XML, `&quot;` là cách biểu diễn ký tự `"` bên trong thuộc tính đang dùng dấu nháy kép. Bộ đọc XML đã chuyển nó thành ký tự nháy thật trong cây DOM. Phía Java, `\"` chỉ là cách viết ký tự nháy trong mã nguồn chuỗi Java. Khi so sánh, cả hai bên đều chứa cùng ký tự `"`.

Ba lớp cú pháp — Java, XML và XPath — có quy tắc riêng. Truyền biến giúp dữ liệu không phải đi qua thêm một lớp ghép chuỗi literal XPath.

## 5. Các cách tưởng tương đương nhưng không giữ được ranh giới

| Cách làm | Vấn đề |
| --- | --- |
| Nối dữ liệu rồi gọi `compile()` | Biên dịch chính biểu thức đã bị dữ liệu thay đổi |
| Dùng `String.format`, `formatted` hoặc thư viện thay thế `${...}` | Vẫn đưa dữ liệu vào chuỗi mã nguồn XPath |
| Viết `[@name='$name']` | `$name` nằm trong dấu nháy, trở thành chuỗi literal chứ không phải biến |
| Chỉ đổi nháy đơn bao quanh thành nháy kép | Dữ liệu có thể chứa nháy kép hoặc cả hai loại nháy |
| Thay `'` thành `\'` hoặc `''` theo thói quen Java/SQL | Không phải cơ chế thoát dấu nháy của literal XPath 1.0 |
| Thay dấu nháy bằng `&apos;` trong chuỗi truyền thẳng cho JAXP | Không có bước phân tích XML để tự chuyển entity đó thành dấu nháy |
| Chỉ cấm từ `or`, dấu `/` hoặc một vài ký tự | Không tạo ra ranh giới dữ liệu/cú pháp, đồng thời dễ làm hỏng dữ liệu hợp lệ |

**`compile()` là bước xử lý biểu thức, không phải cơ chế làm sạch dữ liệu.** Viết sẵn một biểu thức có biến rồi cung cấp giá trị riêng mới giữ dữ liệu khỏi trở thành cú pháp. Tên phương thức có chữ `compile` không chứng minh đầu vào đã an toàn.

Trong XPath 1.0, literal dùng một trong hai loại dấu nháy để bao chuỗi; không có quy tắc dấu gạch chéo ngược như Java. Nếu buộc phải dựng một literal trong công cụ không hỗ trợ biến, cần một cơ chế tạo literal đúng chuẩn cho mọi trường hợp, kể cả cả hai loại dấu nháy. Với JAXP có `XPathVariableResolver`, hãy dùng khả năng sẵn có thay vì tự duy trì thuật toán đó. Xem [quy tắc biểu thức và chuỗi của XPath 1.0](https://www.w3.org/TR/1999/REC-xpath-19991116/#section-Expressions).

## 6. Biến truyền giá trị, không truyền mảnh cấu trúc truy vấn

`$name` có thể cung cấp một chuỗi để so sánh; nó không thay chỗ cho tên phần tử, tên thuộc tính, toán tử, dấu `/` hoặc một đoạn điều kiện.

Ví dụ, không thiết kế giao diện nhận một tham số `predicate` rồi ghép nó vào `"/directory/person[" + predicate + "]"` với hy vọng các biến khác sẽ bảo vệ toàn truy vấn. Phần `predicate` vẫn là cú pháp do bên ngoài kiểm soát.

Nếu người dùng cần chọn tìm theo tên hoặc mã định danh, ánh xạ lựa chọn thành **cả biểu thức cố định** do ứng dụng định nghĩa. Đoạn sau minh họa lựa chọn biểu thức, không phải chương trình độc lập:

```java
String query = switch (field) {
    case "name" -> "/directory/person[@name=$value]";
    case "id" -> "/directory/person[@id=$value]";
    default -> throw new IllegalArgumentException("Unsupported search field");
};
```

Ở đây người dùng chỉ chọn một chế độ được phép; các đường dẫn, thuộc tính và phép so sánh đều do mã ứng dụng viết sẵn. Bộ phân giải sẽ cung cấp giá trị cho biến `value` như cách làm với biến `name` trong ví dụ hoàn chỉnh.

Cũng không truyền chuỗi `"@name='alice'"` vào `$condition` rồi mong XPath tự thực thi nó. Một chuỗi là một giá trị. Đặc biệt, nếu đặt một biến chuỗi đơn lẻ vào điều kiện `[$condition]`, chuỗi không rỗng có thể được chuyển thành Boolean đúng, khiến bộ lọc giữ mọi nút. Hãy viết phép so sánh cụ thể trong biểu thức.

## 7. Kiểu dữ liệu, vòng đời và các lớp kiểm tra khác

### Giữ hợp đồng kiểu dữ liệu rõ ràng

Truyền biến không có nghĩa bỏ qua quy tắc chuyển kiểu của XPath. Ví dụ chính luôn cung cấp `String`, nên `@name=$name` là phép so sánh tên với chuỗi. Nếu vô tình cung cấp `Boolean.TRUE`, quy tắc so sánh có thể khác hoàn toàn ý định tìm tên.

Với đầu vào số, hãy kiểm tra định dạng và miền giá trị theo nghiệp vụ, rồi quyết định truyền kiểu số hay chuỗi. Nếu so sánh chuỗi bằng chuỗi, đừng tự đổi giá trị thành số chỉ vì chúng có dạng chữ số; mã `001` và `1` có thể là hai định danh khác nhau. Giữ nguyên ý nghĩa dữ liệu quan trọng hơn việc ép mọi dữ liệu sang cùng kiểu.

### Cấu hình trước khi biên dịch và tránh chia sẻ trạng thái giữa các yêu cầu

Ví dụ tạo bộ phân giải giữ một `String` cục bộ không thay đổi, gắn nó trước `compile()` và đánh giá ngay. Cách này ưu tiên làm rõ tính độc lập giữa từng lần tra cứu.

Nếu cần tái sử dụng biểu thức đã biên dịch, phải thiết kế cả nơi lưu giá trị và phạm vi truy cập: chỉ thay giá trị giữa các lần đánh giá, không thay trong một lần đánh giá. Không giả định gắn một bộ phân giải mới lên đối tượng `XPath` sẽ thay bộ phân giải mà mọi biểu thức cũ đang dùng; bộ phân giải có hiệu lực lúc biên dịch là một phần của ngữ cảnh liên quan. Xem [XPath.compile](https://docs.oracle.com/en/java/javase/25/docs/api/java.xml/javax/xml/xpath/XPath.html#compile(java.lang.String)).

`XPathExpression` không bảo đảm an toàn khi dùng đồng thời từ nhiều luồng và không hỗ trợ gọi lồng trở lại cùng biểu thức đang đánh giá. Một biến toàn cục dùng để lưu tên tìm kiếm có thể làm dữ liệu yêu cầu này rò sang yêu cầu khác. Dùng phạm vi theo yêu cầu/luồng phù hợp hoặc đồng bộ hóa có chủ đích; không coi việc biên dịch một lần là đủ để dùng chung tự do. Xem [XPathExpression](https://docs.oracle.com/en/java/javase/25/docs/api/java.xml/javax/xml/xpath/XPathExpression.html).

### Phân biệt kiểm tra dữ liệu, phân quyền và đọc XML

- **Kiểm tra dữ liệu** xác nhận kiểu, độ dài, trường được phép và quy tắc nghiệp vụ. Nó bổ sung cho truyền biến, không thay thế việc truyền biến.
- **Phân quyền** quyết định người đang gọi có được xem những nút kết quả hay không. Việc tên được truyền an toàn không tự tạo quyền đọc bản ghi.
- **Cấu hình bộ đọc XML** xử lý rủi ro như truy cập thực thể ngoài. Biến XPath không tự vô hiệu hóa DTD hay chặn việc đọc tài nguyên ngoài.

Ví dụ bật xử lý an toàn cho cả DOM và XPath, đồng thời cấm `DOCTYPE` và truy cập DTD/schema ngoài ở bước tạo DOM. Các cấu hình đó không sửa được phép ghép chuỗi: kết quả `syntax-text` vẫn chứng minh cấu trúc điều kiện bị thay đổi trong nhánh cố ý không an toàn. Ngược lại, thay phép nối bằng biến cũng không tự cấu hình bộ đọc XML.

## 8. Cách tự kiểm chứng khi sửa mã có sẵn

Khi gặp một truy vấn XPath trong Java, lần theo dữ liệu từ nơi nhận đến lúc gọi `compile()`/`evaluate()`:

1. Đánh dấu mọi phần của chuỗi biểu thức chịu ảnh hưởng từ dữ liệu ngoài, kể cả dữ liệu lấy từ tệp cấu hình hoặc cơ sở dữ liệu.
2. Chuyển các **giá trị so sánh** sang biến; giữ biểu thức dưới quyền kiểm soát của ứng dụng.
3. Với lựa chọn làm thay đổi cấu trúc, ánh xạ sang tập biểu thức cố định và từ chối lựa chọn không được hỗ trợ.
4. Kiểm tra với chuỗi thường, chuỗi có một hoặc cả hai loại nháy, chuỗi có hình thức toán tử, chuỗi rỗng và dữ liệu Unicode.
5. Xác minh đồng thời số lượng nút và nội dung bản ghi được chọn; đừng chỉ kiểm tra chương trình không ném ngoại lệ.

Trong ví dụ, có thể thêm một người thật sự có tên chính xác bằng chuỗi dữ liệu của trường hợp `syntax-text`. Cách truyền biến phải chọn đúng người đó, thay vì từ chối chỉ vì tên chứa chữ `or`. Đây là cách phân biệt rõ nhất giữa **xử lý dữ liệu nguyên vẹn** và **để dữ liệu điều khiển cú pháp**.
