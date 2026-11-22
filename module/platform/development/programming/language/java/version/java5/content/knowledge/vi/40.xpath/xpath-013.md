# XPathExpressionException và lỗi đánh giá

## 1. Lỗi XPath xảy ra ở đâu?

Một phép truy vấn XML thường đi qua ba công việc khác nhau:

```text
Đọc XML thành DOM
        ↓
Biên dịch chuỗi XPath thành XPathExpression
        ↓
Đánh giá biểu thức trên DOM và nhận kết quả
```

`XPathExpressionException` là ngoại lệ có kiểm tra của Java, kế thừa `XPathException`, dùng để báo lỗi liên quan đến biểu thức XPath. Vì vậy, phương thức gọi API có thể bắt nó hoặc khai báo `throws`. Nó không chỉ xuất hiện khi viết sai cú pháp: biểu thức đã biên dịch vẫn có thể thất bại khi đánh giá. [Định nghĩa XPathExpressionException](https://docs.oracle.com/en/java/javase/21/docs/api/java.xml/javax/xml/xpath/XPathExpressionException.html).

Cần phân biệt ba câu hỏi:

1. **Biểu thức có hợp lệ để biên dịch không?**
2. **Có đủ điều kiện để đánh giá và chuyển kết quả sang kiểu yêu cầu không?**
3. **Kết quả có đáp ứng điều kiện nghiệp vụ không?**

Không có nút phù hợp thường là một kết quả hợp lệ, không phải lỗi đánh giá. Ngược lại, lỗi đánh giá không nên bị biến thành “không tìm thấy dữ liệu”.

Bài dùng API chuẩn `javax.xml.xpath` trên Java 17+, vẫn được cung cấp trong Java hiện hành; không dựa vào lớp triển khai nội bộ của JDK.

## 2. Phân loại trước khi xử lý

| Tình huống | Giai đoạn | Cách nhận diện |
|---|---|---|
| `/catalog/book[` thiếu phần kết thúc | Biên dịch | `XPathExpressionException` |
| Biểu thức dùng biến nhưng không phân giải được biến | Đánh giá | `XPathExpressionException` |
| Biểu thức trả số nhưng yêu cầu chuyển sang tập nút | Đánh giá/chuyển kiểu XPath | `XPathExpressionException` trong ví dụ |
| Truyền `null` cho chuỗi cần biên dịch | Kiểm tra tham số API | `NullPointerException` |
| Truyền một `QName` không phải kiểu kết quả được API hỗ trợ | Kiểm tra tham số API | `IllegalArgumentException` |
| Biểu thức đúng nhưng không chọn nút nào | Đánh giá thành công | `NodeList` có độ dài 0 khi yêu cầu `NODESET` |
| Đọc XML sai cấu trúc bằng `DocumentBuilder.parse` | Phân tích XML trước XPath | Lỗi phân tích XML, thường là `SAXException` |
| Đọc tệp XML thất bại trước XPath | Đọc dữ liệu | `IOException` |
| Ép một `String` kết quả thành `NodeList` ở mã ứng dụng | Sau đánh giá | `ClassCastException`, không phải lỗi cú pháp XPath |

`XPath.compile` khai báo lỗi biên dịch bằng `XPathExpressionException`; `XPath.evaluate` và `XPathExpression.evaluate` cũng có thể báo ngoại lệ này khi không đánh giá được. Đối với overload nhận `Object` làm ngữ cảnh, `null` không luôn bị cấm: biểu thức không phụ thuộc ngữ cảnh có thể dùng nó, còn biểu thức cần ngữ cảnh không được đánh giá theo cách đó. [Hợp đồng XPath](https://docs.oracle.com/en/java/javase/21/docs/api/java.xml/javax/xml/xpath/XPath.html), [Hợp đồng XPathExpression](https://docs.oracle.com/en/java/javase/21/docs/api/java.xml/javax/xml/xpath/XPathExpression.html).

Không gộp mọi hàng trong bảng thành một khối `catch (XPathExpressionException e)`. Mỗi lỗi có nguồn và cách khắc phục khác nhau.

## 3. Chương trình hoàn chỉnh: lỗi thật và kết quả rỗng hợp lệ

Lưu thành `XPathErrorsDemo.java`. Chương trình không cần dependency ngoài JDK.

```java
import java.io.StringReader;
import javax.xml.namespace.QName;
import javax.xml.parsers.DocumentBuilderFactory;
import javax.xml.xpath.XPath;
import javax.xml.xpath.XPathConstants;
import javax.xml.xpath.XPathExpression;
import javax.xml.xpath.XPathExpressionException;
import javax.xml.xpath.XPathFactory;
import org.w3c.dom.Document;
import org.w3c.dom.NodeList;
import org.xml.sax.InputSource;

public class XPathErrorsDemo {
    @FunctionalInterface
    interface CheckedAction {
        void run() throws Exception;
    }

    static void expect(String label, Class<? extends Throwable> expected,
                       CheckedAction action) throws Exception {
        try {
            action.run();
        } catch (Exception failure) {
            if (!expected.isInstance(failure)) {
                throw new AssertionError(label + ": unexpected exception", failure);
            }
            System.out.println(label + " -> " + expected.getSimpleName());
            return;
        }
        throw new AssertionError(label + ": expected " + expected.getSimpleName());
    }

    public static void main(String[] args) throws Exception {
        String xml = "<catalog><book price='12.5'>Java</book></catalog>";
        DocumentBuilderFactory factory = DocumentBuilderFactory.newInstance();
        factory.setNamespaceAware(true);
        Document document = factory.newDocumentBuilder()
                .parse(new InputSource(new StringReader(xml)));

        XPath xpath = XPathFactory.newDefaultInstance().newXPath();

        expect("compile-syntax", XPathExpressionException.class,
                () -> xpath.compile("/catalog/book["));

        XPathExpression missingVariable =
                xpath.compile("/catalog/book[@price > $minimum]");
        expect("evaluate-variable", XPathExpressionException.class,
                () -> missingVariable.evaluate(document, XPathConstants.NODESET));

        XPathExpression scalar = xpath.compile("count(/catalog/book)");
        expect("evaluate-conversion", XPathExpressionException.class,
                () -> scalar.evaluate(document, XPathConstants.NODESET));

        expect("null-expression", NullPointerException.class,
                () -> xpath.compile(null));

        XPathExpression books = xpath.compile("/catalog/book");
        expect("unsupported-return-type", IllegalArgumentException.class,
                () -> books.evaluate(document, new QName("urn:demo", "unknown")));

        NodeList none = (NodeList) xpath.evaluate(
                "/catalog/magazine", document, XPathConstants.NODESET);
        System.out.println("valid-empty -> " + none.getLength());

        String noText = xpath.evaluate("string(/catalog/missing)", document);
        System.out.println("valid-empty-string -> [" + noText + "]");

        double invalidNumber = (Double) xpath.evaluate(
                "number('not-a-number')", document, XPathConstants.NUMBER);
        System.out.println("valid-NaN -> " + Double.isNaN(invalidNumber));

        String title = xpath.evaluate("string(/catalog/book[1])", document);
        if (!"Java".equals(title)) {
            throw new AssertionError("Unexpected title: " + title);
        }
        System.out.println("valid-title -> " + title);
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 XPathErrorsDemo.java
java XPathErrorsDemo
```

Stdout:

```text
compile-syntax -> XPathExpressionException
evaluate-variable -> XPathExpressionException
evaluate-conversion -> XPathExpressionException
null-expression -> NullPointerException
unsupported-return-type -> IllegalArgumentException
valid-empty -> 0
valid-empty-string -> []
valid-NaN -> true
valid-title -> Java
```

Hàm `expect` chỉ phục vụ minh chứng: nó kiểm tra đúng lớp ngoại lệ mong đợi và làm chương trình thất bại nếu hành vi khác dự kiến. Đây không phải mẫu “bắt mọi ngoại lệ rồi tiếp tục” cho mã nghiệp vụ.

### 3.1. Sai cú pháp bị phát hiện khi biên dịch

`/catalog/book[` thiếu điều kiện và dấu `]`. Không có biểu thức hợp lệ để sử dụng tiếp. Nếu truy vấn là hằng do lập trình viên viết, cần sửa mã hoặc cấu hình, không thử lại cùng dữ liệu nhiều lần.

Không dùng chuỗi thông báo cụ thể của JDK để quyết định đây là lỗi gì. Câu chữ có thể khác theo bộ thực thi và phiên bản.

### 3.2. Biên dịch thành công không bảo đảm đánh giá thành công

Trong chương trình, biểu thức có `$minimum` được biên dịch nhưng lần đánh giá không có bộ phân giải biến thích hợp. Lỗi nằm ở môi trường đánh giá, không phải thiếu dấu ngoặc.

Với API chuẩn, biến không được phân giải hoặc resolver trả `null` có thể làm phép đánh giá thất bại. Trong ứng dụng, kiểm tra đầy đủ tham số trước khi gọi, thay vì coi thiếu biến là kết quả rỗng.

### 3.3. Kiểu kết quả cần phù hợp với biểu thức

`count(/catalog/book)` tạo ra số. Yêu cầu `NODESET` buộc bộ thực thi chuyển số đó thành tập nút; chương trình minh họa lỗi chuyển đổi này.

Phân biệt với trường hợp sau, chỉ là đoạn minh họa trong phương thức:

```java
Object value = xpath.evaluate(
        "string(/catalog/book[1])", document, XPathConstants.STRING);
NodeList nodes = (NodeList) value; // ClassCastException o ma Java.
```

Ở đây XPath đã trả về đúng kiểu được yêu cầu là `String`. Phép ép kiểu sai do ứng dụng thực hiện sau đó không được sửa bằng cách bắt `XPathExpressionException`.

### 3.4. Rỗng và NaN có thể là kết quả hợp lệ

Trong dữ liệu mẫu:

- `/catalog/magazine` không chọn nút nào nên độ dài tập nút bằng 0.
- `string(/catalog/missing)` tạo chuỗi rỗng.
- `number('not-a-number')` cho `NaN`; kiểm tra bằng `Double.isNaN`.
- `string(/catalog/book[1])` cho `Java`.

Không dùng `value == Double.NaN` để kiểm tra NaN. Một phép đánh giá kết thúc bình thường vẫn cần được kiểm tra theo hợp đồng dữ liệu của ứng dụng.

Ví dụ, nếu cấu hình bắt buộc có đúng một `book`, cần đánh giá số nút rồi kiểm tra bằng 1. Đừng chỉ lấy kết quả kiểu `STRING` và xem chuỗi rỗng là bằng chứng chắc chắn rằng phần tử không tồn tại: phần tử tồn tại nhưng không có nội dung cũng có thể cho chuỗi rỗng.

## 4. Tách lỗi XML khỏi lỗi XPath

Ví dụ chính phân tích một chuỗi XML hằng trước khi biên dịch truy vấn. Khi dùng XML bên ngoài, lỗi có thể xuất hiện trước khi XPath chạy:

```java
// Doan minh hoa trong phuong thuc co documentBuilder va inputStream.
Document document = documentBuilder.parse(inputStream);
XPathExpression expression = xpath.compile("/catalog/book");
NodeList books = (NodeList) expression.evaluate(document, XPathConstants.NODESET);
```

Nếu muốn phân loại rõ, xử lý từng giai đoạn tại ranh giới tương ứng:

- Tạo cấu hình parser: có thể gặp `ParserConfigurationException`.
- Phân tích XML: xử lý `SAXException` và `IOException` theo nguồn dữ liệu.
- Biên dịch/đánh giá XPath: xử lý `XPathExpressionException`.

[DocumentBuilder.parse và các lỗi đọc/phân tích XML](https://docs.oracle.com/en/java/javase/21/docs/api/java.xml/javax/xml/parsers/DocumentBuilder.html#parse(java.io.InputStream)), [DocumentBuilderFactory.newDocumentBuilder](https://docs.oracle.com/en/java/javase/21/docs/api/java.xml/javax/xml/parsers/DocumentBuilderFactory.html#newDocumentBuilder()).

Nếu gọi overload XPath nhận `InputSource`, bộ thực thi còn phải tạo mô hình XML bên trong lời gọi đánh giá. Khi ấy, đừng mặc định lỗi ngoài cùng luôn nói được nguyên nhân đầu tiên; hãy đọc chuỗi `getCause()`. Cấu trúc bọc lỗi cụ thể có thể phụ thuộc bộ thực thi.

Nếu đã biết DOM không được tạo thành công, không tiếp tục truy vấn trên một giá trị thay thế không rõ nghĩa. Ngoài ra, biến XPath và xử lý ngoại lệ không thay thế việc cấu hình parser phù hợp cho XML không tin cậy.

## 5. Giữ nguyên nguyên nhân khi chuyển ngoại lệ

Ngoại lệ ngoài cùng trả lời “phép truy vấn thất bại ở đâu”; nguyên nhân bên trong giúp biết “vì sao”. Khi chuyển lỗi sang ranh giới của ứng dụng, giữ `cause`:

```java
// Phuong thuc co the dat ben trong lop xu ly truy van.
static NodeList findBooks(XPathExpression expression, Document document) {
    try {
        return (NodeList) expression.evaluate(document, XPathConstants.NODESET);
    } catch (XPathExpressionException failure) {
        throw new IllegalStateException(
                "Cannot evaluate query catalog.books", failure);
    }
}
```

Thông báo có mã truy vấn ổn định `catalog.books` để người vận hành biết nơi cần kiểm tra; không cần nhét toàn bộ XML hoặc dữ liệu người dùng vào đó.

Tránh làm mất nguyên nhân:

```java
// Doan minh hoa cach lam mat thong tin chan doan.
throw new IllegalStateException(failure.getMessage());
```

Cách này chỉ sao chép thông báo, bỏ quan hệ nguyên nhân và vị trí lỗi ban đầu. Trong bài thực hành nhỏ, có thể gọi `printStackTrace()` để quan sát. Trong ứng dụng, ghi lỗi qua cơ chế logging tại ranh giới chịu trách nhiệm xử lý; tránh mỗi tầng vừa ghi đầy đủ stack trace vừa ném tiếp làm một lỗi xuất hiện nhiều lần. [XPathException.getCause và stack trace](https://docs.oracle.com/en/java/javase/21/docs/api/java.xml/javax/xml/xpath/XPathException.html).

Bản thân `XPathExpressionException` có constructor nhận `String` và constructor nhận `Throwable`. Cả hai không nhận tham số `null` hợp lệ. Khi chỉ cần truyền lỗi lên trên mà không bổ sung ngữ cảnh, có thể khai báo `throws XPathExpressionException` thay vì bọc thêm một lớp không mang ý nghĩa. [Constructor của XPathExpressionException](https://docs.oracle.com/en/java/javase/21/docs/api/java.xml/javax/xml/xpath/XPathExpressionException.html).

## 6. Chẩn đoán theo thứ tự có thể kiểm chứng

1. **Xác định giai đoạn.** Lỗi ở `parse`, `compile` hay `evaluate`? Tách các lời gọi khi đang điều tra để tránh đoán.
2. **Thu nhỏ dữ liệu và biểu thức.** Dùng XML tối thiểu cùng một truy vấn đơn giản như `/catalog/book`, rồi thêm dần predicate.
3. **Kiểm tra tên và namespace.** Một đường dẫn sai tên nhưng vẫn đúng cú pháp có thể chỉ trả rỗng. XML có default namespace cần đường dẫn XPath được ánh xạ namespace đúng; không chờ ngoại lệ phát hiện giúp.
4. **Kiểm tra môi trường đánh giá.** Có đủ biến, kiểu giá trị, hàm mở rộng và ngữ cảnh cần thiết không? Thiết lập resolver trước khi biên dịch.
5. **Kiểm tra kiểu yêu cầu.** `NODESET`, `NODE`, `STRING`, `NUMBER`, `BOOLEAN` diễn đạt các nhu cầu khác nhau. Đừng sửa bằng cách đổi ép kiểu tùy tiện.
6. **Đọc cause và vị trí gọi.** Ghi mã truy vấn, giai đoạn, lớp ngoại lệ và thông tin ngữ cảnh tối thiểu cần thiết.
7. **Kiểm tra kết quả theo nghiệp vụ.** Phân biệt rỗng hợp lệ, số nút sai kỳ vọng, chuỗi trống và NaN.

Thông báo của bộ thực thi có ích để chẩn đoán, nhưng không phải mã lỗi ổn định để chương trình so sánh bằng `contains(...)`. Các thử nghiệm nên dựa vào loại ngoại lệ hoặc kết quả theo hợp đồng, như hàm `expect` trong ví dụ.

## 7. Những cách xử lý dễ che lỗi

### Trả danh sách rỗng sau mọi lỗi

Nếu biểu thức sai hoặc thiếu biến, trả danh sách rỗng khiến tầng gọi tưởng truy vấn đã thành công. Chỉ dùng kết quả rỗng khi phép đánh giá thành công và không tìm thấy nút; các tình huống nghiệp vụ khác cần cách biểu diễn riêng.

### Tự động thử lại lỗi cố định

Thiếu dấu ngoặc, thiếu khai báo namespace, sai kiểu kết quả hoặc thiếu biến không tự hết sau vài trăm mili giây. Khắc phục cấu hình, truy vấn hoặc đầu vào. Chỉ áp dụng thử lại cho điều kiện tạm thời có thể xác định được ở hệ thống bên ngoài; việc đọc XML thất bại do kết nối là một tầng khác với lỗi cú pháp XPath.

### Dùng catch quá rộng làm luồng bình thường

`catch (Exception e)` có thể gom lẫn lỗi XML, XPath và lỗi lập trình. Nếu cần bắt rộng ở ranh giới ngoài cùng để chuyển thành phản hồi, vẫn phải giữ nguyên nguyên nhân và không báo thành công giả. Mã xử lý trực tiếp nên bắt loại lỗi mà nó biết cách xử lý.

### Dùng chung biểu thức không kiểm soát giữa nhiều luồng

`XPath` và `XPathExpression` không bảo đảm an toàn luồng và không cho gọi đánh giá đệ quy trên cùng đối tượng đang hoạt động. Lỗi do dùng chung sai cách không nhất thiết luôn được báo bằng một loại ngoại lệ dễ dự đoán. Quản lý đối tượng theo từng yêu cầu hoặc bảo đảm truy cập độc quyền; đồng thời giữ biến và DOM ổn định trong lúc đánh giá. [Giới hạn sử dụng XPathExpression](https://docs.oracle.com/en/java/javase/21/docs/api/java.xml/javax/xml/xpath/XPathExpression.html).

## 8. Thực hành phân biệt kết quả và thất bại

Thử từng thay đổi độc lập trên chương trình chính:

1. Sửa biểu thức sai thành `/catalog/book`. Kỳ vọng biên dịch thành công; vì vậy bài kiểm tra cũ phải thất bại với thông báo “expected XPathExpressionException”.
2. Gắn bộ phân giải cho biến `minimum` trước khi biên dịch, trả về `10.0`. Kỳ vọng truy vấn chọn được sách thay vì ném lỗi.
3. Đổi kiểu kết quả của `count(/catalog/book)` sang `NUMBER`. Kỳ vọng có `Double` bằng `1.0`.
4. Đổi `/catalog/magazine` thành `/catalog/Book`. Kỳ vọng vẫn rỗng vì tên phân biệt hoa/thường, không phải lỗi cú pháp.
5. Thêm phần tử `<missing/>` vào XML. So sánh kết quả chuỗi của `string(/catalog/missing)` với số nút của `/catalog/missing` để thấy “không có phần tử” và “phần tử rỗng” cần cách kiểm tra khác nhau.
6. Viết một phương thức yêu cầu đúng một sách. Đánh giá `NODESET`, kiểm tra số nút rồi tạo lỗi nghiệp vụ riêng nếu khác 1; giữ lỗi XPath là lỗi đánh giá, không đổi nó thành kết quả không tìm thấy.
