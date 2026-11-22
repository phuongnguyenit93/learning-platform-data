# Giới hạn an toàn luồng của đối tượng XPath

## 1. Vì sao một truy vấn chỉ đọc XML vẫn có vấn đề dùng đồng thời?

Một dịch vụ có thể lưu `XPath` vào trường `static final`, rồi để nhiều yêu cầu cùng gọi `evaluate`. Lập luận thường gặp là “biểu thức chỉ đọc tài liệu, đối tượng đã được khởi tạo xong nên có thể dùng chung”. Lập luận này bỏ qua hợp đồng của bộ đánh giá: việc đánh giá có thể cần trạng thái nội bộ ngoài những trường cấu hình mà ứng dụng nhìn thấy.

Theo API JAXP, **một đối tượng `XPath` không an toàn luồng và không tái nhập**. Ứng dụng phải bảo đảm không có nhiều luồng dùng cùng đối tượng ở cùng thời điểm; cũng không gọi lại phép đánh giá trên chính đối tượng khi một lần đánh giá của nó còn đang hoạt động. [Hợp đồng XPath](https://docs.oracle.com/en/java/javase/25/docs/api/java.xml/javax/xml/xpath/XPath.html)

Điều cần quản lý là **ai sở hữu mỗi đối tượng trong lúc sử dụng**. Có thể mỗi tác vụ sở hữu riêng, hoặc nhiều tác vụ dùng tuần tự qua một lớp bao có kiểm soát. Không cần biến mọi tài liệu XML thành tuần tự chỉ vì XPath có giới hạn; cần xác định đúng đối tượng nào đang được chia sẻ.

Bài học dùng API còn áp dụng trên Java hiện hành, với chương trình chạy Java 17 trở lên. Nó không dựa vào một provider tình cờ cho kết quả đúng trong một phép thử cạnh tranh.

## 2. An toàn luồng và tái nhập là hai câu hỏi khác nhau

**Dùng đồng thời từ nhiều luồng:** A gọi `evaluate` trên đối tượng X, trong khi B cũng gọi `evaluate`, `compile` hoặc đổi cấu hình X trước khi A hoàn tất. Hợp đồng không cho phép giả định việc đó an toàn.

**Tái nhập (reentrancy):** chỉ một luồng, nhưng trong quá trình X đang đánh giá, một callback như hàm mở rộng hoặc resolver lại gọi một lần đánh giá khác trên chính X trước khi lần ngoài kết thúc. Không có hai luồng cũng vẫn có thể vi phạm giới hạn.

```text
Luồng A → X.evaluate(...)
               → callback do ứng dụng cung cấp
                     → X.evaluate(...)  ← lần ngoài chưa kết thúc
```

Một khóa `synchronized` thông thường cho phép cùng luồng lấy lại khóa mà nó đang giữ. Vì thế, thêm khóa có thể ngăn A/B chạy song song, nhưng không tự ngăn callback gọi lồng trên X. Cần tránh chu trình callback đó hoặc có lớp bao từ chối rõ việc gọi lại khi đang đánh giá.

Không được suy rằng “chỉ có một luồng đang dùng” đồng nghĩa “không thể tái nhập”. Hai điều kiện cần được xét riêng trong thiết kế.

## 3. Cả đối tượng đã compile và factory đều có hợp đồng riêng

| Đối tượng/thành phần | Điều cần quản lý |
| --- | --- |
| `XPathFactory` | Không chia sẻ cùng instance để dùng đồng thời; factory cũng có giới hạn tái nhập riêng |
| `XPath` | Cấu hình, compile và evaluate phải tuân thủ một chủ sở hữu hoặc cơ chế sử dụng tuần tự |
| `XPathExpression` | Biên dịch xong vẫn không được bảo đảm dùng đồng thời hoặc tái nhập |
| `NamespaceContext`, resolver, hàm mở rộng | Mọi trạng thái mà callback truy cập phải phù hợp với vòng đời đánh giá |
| DOM/nguồn đầu vào | Có quy tắc sở hữu và truy cập riêng; khóa một biểu thức không tự bảo vệ toàn bộ cây |

`compile()` tạo một biểu thức có thể tái sử dụng theo hợp đồng, không tạo ra một giá trị bất biến được bảo đảm an toàn cho mọi lời gọi song song. Hãy phân biệt **dùng lại qua các lần đánh giá liên tiếp** với **dùng chung đồng thời**. [XPathExpression](https://docs.oracle.com/en/java/javase/25/docs/api/java.xml/javax/xml/xpath/XPathExpression.html), [XPathFactory](https://docs.oracle.com/en/java/javase/25/docs/api/java.xml/javax/xml/xpath/XPathFactory.html)

Việc gọi `XPathFactory.newInstance()` hoặc `newDefaultInstance()` riêng cho mỗi tác vụ là tạo các instance khác nhau, không phải cho nhiều tác vụ cùng sử dụng một factory đã lưu trong trường tĩnh. Trong thiết kế muốn dùng lại factory, bảo vệ riêng việc dùng instance đó hoặc giới hạn nó trong một chủ sở hữu.

## 4. Những cách chia sẻ trông an toàn nhưng chưa đủ

### final chỉ cố định tham chiếu

```java
// Minh họa cách dùng cần tránh trong một dịch vụ nhiều luồng.
private static final XPath SHARED =
        XPathFactory.newInstance().newXPath();
```

`final` không biến đối tượng thành bất biến. Nó không bổ sung bảo đảm đồng thời mà API XPath đã không cung cấp. Tương tự, để biến tham chiếu là `volatile` không tuần tự hóa các thao tác trên đối tượng đó.

### Map đồng thời không bảo vệ giá trị chứa bên trong

```java
// Map quản lý truy cập cache; chưa bảo vệ việc evaluate mỗi expression.
Map<String, XPathExpression> cache = new ConcurrentHashMap<>();
```

Một map có khả năng dùng đồng thời có thể bảo vệ phép thêm/tìm entry. Nó không tự khiến `XPathExpression` được lấy ra an toàn cho nhiều luồng cùng gọi. Cache chuỗi biểu thức là một việc khác với cache một instance evaluator dùng chung. [ConcurrentHashMap](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html)

### Khóa từng setter rời rạc chưa tạo một thao tác nguyên tử

Giả sử A đặt resolver cho tham số A, rồi chuẩn bị đánh giá; B chen vào đặt resolver cho tham số B. Dù từng setter được bọc khóa riêng, A vẫn có thể chạy với cấu hình không phải cấu hình mà nó định dùng. Khi cần cấu hình theo lời gọi, phạm vi bảo vệ phải bao phủ **thiết lập → đánh giá → dọn/khôi phục** như một đơn vị nhất quán, hoặc tốt hơn là không dùng chung môi trường theo cách đó.

Không sửa một map của resolver đang được đọc trong lần đánh giá khác. Với biến XPath, giá trị của một biến phải giữ nguyên trong một lần đánh giá; dùng map đồng thời không tự cung cấp tính nhất quán ấy. [XPathVariableResolver](https://docs.oracle.com/en/java/javase/25/docs/api/java.xml/javax/xml/xpath/XPathVariableResolver.html)

## 5. Phương án đơn giản: mỗi lời gọi sở hữu trọn môi trường

Đây thường là điểm bắt đầu dễ kiểm tra:

```text
Một lời gọi xử lý:
    tạo parser và DOM riêng
    tạo XPathFactory riêng
    tạo XPath riêng
    gắn resolver/cấu hình riêng
    compile biểu thức riêng
    evaluate và chuyển kết quả thành dữ liệu cần trả
    kết thúc phạm vi sở hữu
```

Các lời gọi vẫn có thể chạy song song vì chúng không chia sẻ cùng evaluator, parser, DOM hoặc resolver có thể đổi. Chuỗi XML đầu vào và chuỗi biểu thức có thể dùng chung nếu chúng là các giá trị bất biến; điều đó không kéo theo việc dùng chung những đối tượng xử lý.

Chi phí tạo/parse/compile có thể cao hơn cách tái sử dụng theo một chủ sở hữu. Trước hết chọn một thiết kế đúng và rõ; chỉ đổi cách quản lý vòng đời khi có dữ liệu đo và nhu cầu thực tế.

## 6. Chương trình hoàn chỉnh: tác vụ độc lập và biến riêng

Yêu cầu: bốn tác vụ truy vấn cùng mẫu XML với các ngưỡng giá khác nhau. Mỗi tác vụ phải dùng đúng ngưỡng của mình, không nhìn nhầm resolver hoặc DOM của tác vụ khác.

Lưu thành `XPathThreadSafetyDemo.java`:

```java
import java.io.StringReader;
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import javax.xml.XMLConstants;
import javax.xml.namespace.QName;
import javax.xml.parsers.DocumentBuilderFactory;
import javax.xml.xpath.XPath;
import javax.xml.xpath.XPathConstants;
import javax.xml.xpath.XPathExpression;
import javax.xml.xpath.XPathFactory;
import org.w3c.dom.Document;
import org.xml.sax.InputSource;

public class XPathThreadSafetyDemo {
    private static final String XML = """
            <items>
                <item price="10"/>
                <item price="20"/>
                <item price="30"/>
                <item price="40"/>
            </items>
            """;
    private static final String QUERY =
            "count(/items/item[number(@price) > $minimum])";

    private static int countAbove(String xml, int minimum) throws Exception {
        DocumentBuilderFactory domFactory =
                DocumentBuilderFactory.newDefaultNSInstance();
        domFactory.setFeature(XMLConstants.FEATURE_SECURE_PROCESSING, true);
        domFactory.setFeature(
                "http://apache.org/xml/features/disallow-doctype-decl", true);
        domFactory.setAttribute(XMLConstants.ACCESS_EXTERNAL_DTD, "");
        domFactory.setAttribute(XMLConstants.ACCESS_EXTERNAL_SCHEMA, "");
        domFactory.setXIncludeAware(false);
        Document document = domFactory.newDocumentBuilder().parse(
                new InputSource(new StringReader(xml)));

        XPathFactory xpathFactory = XPathFactory.newDefaultInstance();
        XPath xpath = xpathFactory.newXPath();
        final Double boundMinimum = (double) minimum;
        final QName minimumName = new QName("", "minimum");
        xpath.setXPathVariableResolver(name -> {
            Objects.requireNonNull(name, "variable name");
            return minimumName.equals(name) ? boundMinimum : null;
        });
        XPathExpression expression = xpath.compile(QUERY);
        Double result = (Double) expression.evaluate(
                document, XPathConstants.NUMBER);
        return result.intValue();
    }

    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newFixedThreadPool(2);
        try {
            List<Future<Integer>> results = new ArrayList<>();
            for (int minimum : List.of(10, 20, 30, 40)) {
                results.add(pool.submit(() -> countAbove(XML, minimum)));
            }
            for (int i = 0; i < results.size(); i++) {
                int minimum = (i + 1) * 10;
                System.out.println("above-" + minimum + "="
                        + results.get(i).get(10, TimeUnit.SECONDS));
            }
        } finally {
            pool.shutdownNow();
        }
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```shell
javac XPathThreadSafetyDemo.java
java XPathThreadSafetyDemo
```

Stdout khi các tác vụ hoàn thành trong thời hạn thí nghiệm:

```text
above-10=3
above-20=2
above-30=1
above-40=0
```

### Đọc ví dụ theo quyền sở hữu

`XML` và `QUERY` là các chuỗi bất biến dùng chung. Mỗi lần `countAbove` tự tạo `DocumentBuilderFactory`, builder, DOM, `XPathFactory`, `XPath`, resolver và `XPathExpression`. Hai worker có thể xử lý các lời gọi khác nhau mà không dùng chung các đối tượng này.

Resolver giữ `boundMinimum`, một `Double` riêng và không đổi của lần gọi. Nó chỉ trả giá trị đó cho QName không namespace tên `minimum`. Không có biến `currentMinimum` dùng chung phải được cập nhật trước mỗi evaluate.

Truy vấn dùng `$minimum`, nên ngưỡng là một giá trị được phân giải theo hợp đồng biến, không phải chuỗi được nối vào nội dung XPath. Với dữ liệu giá 10, 20, 30, 40 và điều kiện lớn hơn nghiêm ngặt, các số đếm lần lượt là 3, 2, 1, 0.

Luồng chính đọc các `Future` theo thứ tự đã gửi để stdout ổn định. Thứ tự in không chứng minh thứ tự tác vụ thực sự bắt đầu/kết thúc; các lời gọi trong pool có thể xen kẽ khác nhau. Thời hạn 10 giây chỉ giới hạn việc đợi của thí nghiệm, không phải chuẩn chung cho mọi dữ liệu XML.

Factory DOM được cấu hình nhận biết namespace và hạn chế nguồn bên ngoài trước khi tạo parser. Đó là chính sách parse của ví dụ, tách khỏi quy tắc dùng đồng thời của XPath. Việc parser xử lý XML an toàn không tự làm đối tượng XPath được phép chia sẻ; ngược lại, mỗi tác vụ có XPath riêng cũng không thay thế cấu hình parser phù hợp. [Cấu hình JAXP hiện hành](https://docs.oracle.com/en/java/javase/25/security/java-api-xml-processing-jaxp-security-guide.html)

Chương trình minh chứng một thiết kế sở hữu rõ ràng và kết quả cần có. Nó không cố tạo một chương trình sai rồi yêu cầu lỗi cạnh tranh phải xuất hiện để “chứng minh” hợp đồng. Một lần chạy chia sẻ XPath tình cờ đúng không thay đổi giới hạn API.

## 7. Nếu muốn dùng chung tuần tự: bao kín đối tượng và bảo vệ toàn bộ đường dùng

Có thể dùng một biểu thức qua các lần gọi nối tiếp nếu toàn bộ đường sử dụng được bảo vệ nhất quán. Lớp bao cần giữ evaluator kín, không đưa tham chiếu ra ngoài rồi để một lời gọi khác vượt qua khóa.

Ví dụ lớp trợ giúp dưới đây đặt trong một tệp Java có các import tương ứng. Đây không phải chương trình độc lập; `Document` được truyền vào phải tuân thủ quy tắc sở hữu/truy cập riêng. Nó dùng biểu thức cố định, không resolver và từ chối tái nhập qua API của chính lớp bao:

```java
final class SerializedTitleQuery {
    private final Object lock = new Object();
    private final XPathExpression expression;
    private boolean evaluating;

    SerializedTitleQuery() throws XPathExpressionException {
        XPath xpath = XPathFactory.newDefaultInstance().newXPath();
        expression = xpath.compile("string(/book/title)");
    }

    String evaluate(Document document) throws XPathExpressionException {
        synchronized (lock) {
            if (evaluating) {
                throw new IllegalStateException("recursive evaluation");
            }
            evaluating = true;
            try {
                return expression.evaluate(document);
            } finally {
                evaluating = false;
            }
        }
    }
}
```

Các import cần có là `javax.xml.xpath.XPath`, `XPathExpression`, `XPathExpressionException`, `XPathFactory` và `org.w3c.dom.Document`. Sau khi khởi tạo, đối tượng lớp bao phải được công bố cho các luồng theo cơ chế Java phù hợp, chẳng hạn trường `final` của dịch vụ được khởi tạo/công bố đúng hoặc truyền qua công cụ đồng thời.

Mọi lời gọi evaluate đi qua cùng khóa; `evaluating` được đọc/ghi bên trong khóa để phát hiện trường hợp cùng luồng gọi lồng. Trong ví dụ không có callback nên đường tái nhập không được tạo ra, nhưng mẫu guard chỉ rõ trách nhiệm nếu API lớp bao được phát triển thêm.

Thiết kế này tuần tự hóa các lần đánh giá của **instance lớp bao đó**. Tạo hai lớp bao khác nhau thì có hai biểu thức khác nhau. Tạo hai khóa khác nhau rồi cùng bảo vệ một biểu thức là sai: các lời gọi vẫn có thể chạy song song trên cùng evaluator.

Nếu nhận kết quả là `Node`/`NodeList` hoặc một đối tượng gắn với DOM, việc rời khóa rồi trả nó cho nhiều bên không tự an toàn. Chuyển kết quả thành dữ liệu bất biến cần thiết trong phạm vi sở hữu hoặc quy định rõ cách truy cập cây sau đó. Ví dụ trả chuỗi nên không làm rò tham chiếu DOM từ kết quả.

## 8. DOM, nguồn đầu vào và callback là một phần của bài toán

Hai XPath riêng vẫn có thể cùng đi vào một DOM dùng chung. Không coi “chúng tôi chỉ đọc” là bảo đảm portable rằng mọi triển khai DOM hỗ trợ truy cập đồng thời. Có thể giữ cây riêng cho mỗi tác vụ hoặc tổ chức khóa đúng với triển khai và toàn bộ người dùng cây; một khóa chỉ nằm ở lớp XPath không có tác dụng với người khác sửa DOM ngoài lớp đó. [Hướng dẫn đồng thời của DOM Xerces](https://xerces.apache.org/xerces2-j/faq-dom.html)

Cùng nguyên tắc đó áp dụng cho parser/builder, `InputStream`, `Reader` và `InputSource`: không phân phối một đối tượng có trạng thái đọc chung cho nhiều tác vụ rồi chỉ tạo XPath mới. Trong chương trình chính, `StringReader` và tài liệu đều được tạo riêng.

Với `NamespaceContext`, có thể chia sẻ một bảng ánh xạ bất biến nếu bản thân lớp đó hỗ trợ cách dùng tương ứng, nhưng XPath sử dụng nó vẫn có giới hạn riêng. Với resolver/hàm mở rộng, tránh các trường “tham số của yêu cầu hiện tại” dùng chung; callback có thể vô tình đọc dữ liệu của yêu cầu khác dù evaluator đã được tách.

Đặc biệt, callback không nên đánh giá lồng trên chính XPath/biểu thức đang hoạt động. Nếu cần một truy vấn phụ, thiết kế thành bước xử lý độc lập với đối tượng riêng và xem xét lại mọi phụ thuộc dữ liệu/khóa; đừng chỉ trông cậy vào một khóa có khả năng tái nhập.

## 9. ThreadLocal và pool: có thể dùng, nhưng cần vòng đời rõ

`ThreadLocal` cho mỗi luồng một giá trị riêng. Có thể dùng nó để giữ môi trường XPath theo worker khi có lý do tái sử dụng; nó **không** cấp một môi trường riêng cho mỗi tác vụ nếu nhiều tác vụ lần lượt dùng cùng worker. [ThreadLocal](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/ThreadLocal.html)

Trước khi chọn cách này, cần trả lời:

- Có lời gọi lồng trên cùng luồng không? Nếu có, chúng vẫn nhận cùng môi trường ThreadLocal và có thể tái nhập.
- Resolver/context có giữ trạng thái của yêu cầu trước không? Một worker phục vụ nhiều tác vụ, nên không để dữ liệu cũ bị dùng lại.
- Có bao nhiêu luồng có thể tạo giá trị riêng? Mỗi luồng mới có thể làm tăng số môi trường/biểu thức được lưu; với nhiều luồng ngắn hạn không mặc nhiên có lợi tái sử dụng.
- Khi nào loại bỏ giá trị bằng `remove` hoặc giải phóng tài nguyên theo vòng đời? Nếu remove sau mỗi tác vụ, lợi ích giữ lại cho tác vụ tiếp theo cũng không còn theo cùng cách.

Pool các môi trường là một lựa chọn khác: một lần mượn phải sở hữu độc quyền đối tượng, không để tham chiếu thoát ra và luôn trả đúng trong `finally`. Cần giới hạn dung lượng, xử lý lỗi/tái cấu hình và xác định đối tượng nào cần loại bỏ sau lỗi. Chỉ dùng map chứa nhiều evaluator chưa tạo thành cơ chế cho mượn độc quyền.

Không mặc định pool nhanh hơn tạo mới. Chờ mượn, khóa, dọn cấu hình và giữ bộ nhớ đều có chi phí; đo trong tải đại diện trước khi thêm các cơ chế này.

## 10. Compile/cache đúng phạm vi

Có thể cache **chuỗi biểu thức/cấu hình bất biến** dùng chung, rồi biên dịch trong môi trường có chủ sở hữu riêng. Nếu cache instance `XPathExpression`, cache phải đi kèm chính sách ai được evaluate instance đó tại một thời điểm, giới hạn số lượng và vòng đời.

Không lấy một biểu thức đã biên dịch theo resolver A rồi kỳ vọng mọi thay đổi setter ở một XPath khác sẽ sửa môi trường của biểu thức đó. Cấu hình resolver tại compile có vai trò theo hợp đồng API; thiết kế dữ liệu biến và vòng đời biểu thức cần thống nhất. [XPath.compile](https://docs.oracle.com/en/java/javase/25/docs/api/java.xml/javax/xml/xpath/XPath.html#compile(java.lang.String))

Nếu cache theo chuỗi mà namespace/context khác nhau giữa các miền dữ liệu, chỉ cùng chuỗi chưa đủ chứng minh đó là cùng truy vấn về ngữ nghĩa. Cần xác định những cấu hình nào ảnh hưởng kết quả và đưa chúng vào chính sách tạo/cache phù hợp. Đồng thời tránh cache không giới hạn các chuỗi do đầu vào bên ngoài tự tạo.

`reset()` cũng là một thao tác thay cấu hình theo hợp đồng của XPath; không gọi trong lúc một lời evaluate còn chạy, và không dùng nó như một phép đồng bộ giữa các luồng. Việc dùng lại đối tượng sau reset phải bảo đảm các cấu hình cần thiết được thiết lập đúng trước lần sử dụng kế tiếp.

## 11. Kiểm chứng mà không dựa vào lỗi ngẫu nhiên

Đánh giá thiết kế từ quan hệ sở hữu trước:

1. Tìm các `XPathFactory`, `XPath`, `XPathExpression` nằm trong trường tĩnh, singleton, cache và ThreadLocal.
2. Lần theo mọi đường gọi compile/evaluate/setter/reset và xác định liệu hai đường có thể chồng thời gian trên cùng instance không.
3. Lần theo callback để tìm nguy cơ tái nhập và dữ liệu tham số dùng chung.
4. Kiểm tra DOM, nguồn đọc và các đối tượng kết quả còn giữ tham chiếu đến cây.
5. Sau đó kiểm thử nhiều yêu cầu với giá trị đầu vào khác nhau và xác minh kết quả của từng yêu cầu, không chỉ đếm số ngoại lệ.

Lỗi đồng thời có thể xuất hiện như kết quả sai, dữ liệu lẫn giữa yêu cầu, ngoại lệ hoặc một hành vi khó lặp lại. Một kiểm thử chỉ khẳng định “không ném lỗi” bỏ qua nguy cơ trả nhầm kết quả. Khi kiểm thử trả đúng, kết luận chỉ nằm trong điều kiện đã kiểm thử; nó không cho phép vi phạm hợp đồng JAXP.

Với phương án khóa, thử cả đường ngoại lệ để chắc chắn trạng thái guard và khóa được giải phóng; nếu lớp có callback, kiểm tra trường hợp gọi lồng được từ chối/được thiết kế riêng như đặc tả. Với phương án mỗi tác vụ riêng, xác nhận không có resolver hoặc parser tĩnh dùng chung bị bỏ sót.

## 12. Tự kiểm tra

1. **XPathExpression đã compile và đặt final có được nhiều luồng evaluate đồng thời không?** Không được giả định. Nó có giới hạn an toàn luồng và tái nhập riêng theo API.
2. **ConcurrentHashMap chứa expression có giải quyết vấn đề không?** Chỉ việc quản lý map; giá trị expression vẫn cần chính sách sử dụng phù hợp.
3. **Một synchronized quanh evaluate có ngăn mọi kiểu tái nhập không?** Không. Cùng luồng có thể lấy lại monitor; cần tránh callback gọi lồng hoặc có guard thích hợp.
4. **Mỗi tác vụ tạo XPath riêng nhưng dùng chung map currentVariables có đủ chưa?** Chưa. Resolver có thể nhìn thấy tham số thay đổi của tác vụ khác; giá trị biến cần ổn định trong từng lần đánh giá.
5. **Tại sao ví dụ tạo DOM riêng dù chủ đề là XPath?** Tách evaluator không tự giải quyết việc dùng chung cây/nguồn đầu vào; ví dụ giữ toàn bộ chuỗi xử lý trong quyền sở hữu từng lời gọi.
6. **Chạy stress nhiều lần đều đúng có chứng minh chia sẻ một XPath được phép không?** Không. Hợp đồng vẫn yêu cầu tránh dùng đồng thời/tái nhập; kiểm thử hỗ trợ đánh giá một thiết kế tuân thủ hợp đồng.
