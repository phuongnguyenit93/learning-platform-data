# Biên dịch biểu thức để tái sử dụng

## 1. Vì sao tách compile khỏi evaluate?

Một chương trình thường phải áp dụng cùng truy vấn XPath cho nhiều tài liệu XML hoặc nhiều nút ngữ cảnh:

```xpath
/catalog/book[price >= $minimum]
```

Cấu trúc truy vấn giữ nguyên; tài liệu và giá trị minimum có thể thay đổi.

Nếu ở mỗi lần xử lý đều đưa một chuỗi biểu thức cho XPath.evaluate, chương trình không thể hiện rõ việc chuẩn bị truy vấn một lần. API chuẩn cung cấp `compile` để tạo một `XPathExpression` có thể được đánh giá lại.

```text
Chuỗi biểu thức + cấu hình XPath
                 |
               compile
                 |
          XPathExpression
             /       \
 evaluate DOM A     evaluate DOM B
     + biến A          + biến B
        |                 |
    kết quả A          kết quả B
```

Biên dịch ở đây là chuẩn bị biểu thức cho bộ máy XPath. Nó không có nghĩa tạo mã máy hay một tệp class Java, cũng không tự xây chỉ mục cho toàn bộ dữ liệu XML.

Các API `javax.xml.xpath` có từ Java 5 và vẫn phù hợp trên Java hiện đại. Bài dùng XPath 1.0 theo hợp đồng API chuẩn và ví dụ Java 17+.

Nguồn: [XPath.compile](https://docs.oracle.com/en/java/javase/21/docs/api/java.xml/javax/xml/xpath/XPath.html#compile(java.lang.String)), [javax.xml.xpath](https://docs.oracle.com/en/java/javase/21/docs/api/java.xml/javax/xml/xpath/package-summary.html).

## 2. Các đối tượng có trách nhiệm khác nhau

| Thành phần | Vai trò |
| --- | --- |
| XPathFactory | Tạo môi trường/provider XPath phù hợp |
| XPath | Cấu hình và chuẩn bị việc đánh giá biểu thức |
| XPathExpression | Biểu thức đã compile để đánh giá lại |
| Document/Node | Dữ liệu và nút ngữ cảnh của một lần đánh giá |
| XPathVariableResolver | Cung cấp giá trị cho biến |
| Kết quả evaluate | NodeList, Node, String, Boolean, Double… theo kiểu yêu cầu |

Ví dụ tối giản:

```java
XPath xpath = XPathFactory.newInstance().newXPath();
XPathExpression query = xpath.compile("/catalog/book");
NodeList books = (NodeList) query.evaluate(
        document, XPathConstants.NODESET);
```

Đây là đoạn minh họa cần import và Document đã được tạo. compile nằm trước evaluate; document chỉ được dùng ở bước đánh giá.

Không đổi vai các thành phần:

- Biểu thức không phải một bản sao của Document.
- Compile không tự chạy truy vấn để giữ kết quả đầu tiên.
- NodeList kết quả không phải bộ máy dùng để áp truy vấn sang tài liệu tiếp theo.

## 3. Thứ gì được chuẩn bị, thứ gì vẫn thay đổi?

### Có thể giữ lại cấu trúc truy vấn

Với truy vấn cố định, có thể chuẩn bị XPathExpression một lần rồi dùng nó cho những lần evaluate theo giao thức sở hữu đối tượng.

```java
XPathExpression query = xpath.compile("/catalog/book");

NodeList first = (NodeList) query.evaluate(
        firstDocument, XPathConstants.NODESET);

NodeList second = (NodeList) query.evaluate(
        secondDocument, XPathConstants.NODESET);
```

Đây là minh họa tuần tự, không phải hai lời gọi đồng thời.

### Context vẫn được truyền ở mỗi lần

firstDocument và secondDocument có thể là hai DOM khác nhau. Kết quả truy vấn đi theo dữ liệu và context của lần gọi đó.

Đường dẫn tương đối còn phụ thuộc việc context là Document hay một phần tử cụ thể. Biên dịch trước không biến một đường dẫn tương đối thành đường dẫn tuyệt đối.

### Kết quả không tự được cache

Nếu dữ liệu DOM thay đổi và gọi evaluate lại, đó là một lần đánh giá mới trên context hiện tại theo mô hình dữ liệu. Không mặc định XPathExpression trả kết quả cũ.

Ngược lại, nếu ứng dụng tự giữ một kết quả NodeList từ lần trước, việc dùng lại NodeList ấy không thay thế cho lần evaluate mới. Hành vi chi tiết của các đối tượng kết quả theo DOM/provider phải được xem theo hợp đồng tương ứng.

### Parse XML vẫn là một bước riêng

Biên dịch biểu thức không parse XML thay ứng dụng. Nếu mỗi lần evaluate qua InputSource lại cần xây mô hình tài liệu, chi phí đó vẫn tồn tại.

Nếu có nhiều truy vấn trên cùng XML, có thể parse thành Document một lần rồi áp dụng những biểu thức phù hợp, với điều kiện vòng đời/bộ nhớ và cấu hình parser đáp ứng yêu cầu.

Không dùng lại một InputStream đã đọc hết rồi kỳ vọng compile giúp tua nguồn. Biểu thức và nguồn dữ liệu là hai vòng đời khác nhau.

## 4. Cấu hình namespace và resolver trước compile

Biểu thức không chỉ phụ thuộc vào chuỗi ký tự. Nó còn gắn với môi trường đánh giá:

- Prefix được NamespaceContext ánh xạ tới URI nào.
- Biến được resolver nào cung cấp.
- Hàm mở rộng được resolver/provider nào hỗ trợ.
- Object model và cấu hình bảo mật của hệ thống XPath.

Quy trình dễ kiểm soát:

```text
Tạo XPath
  -> thiết lập NamespaceContext/resolver phù hợp
  -> compile
  -> evaluate theo vòng đời đã quy định
```

Khi thay một chính sách namespace/provider/resolver quan trọng, đừng tự mặc định biểu thức cũ sẽ được “cập nhật” đúng như mong muốn chỉ vì sửa XPath gốc. Chuẩn bị lại bộ đối tượng theo cấu hình mới và kiểm tra kết quả.

Với XML có namespace mặc định, các tên không có prefix trong XPath 1.0 không tự nhận namespace của XML. Việc compile thành công không chứng minh tên nút sẽ khớp tài liệu.

Vì vậy, cache chỉ theo một String biểu thức có thể không đủ nếu cùng chuỗi xuất hiện trong nhiều môi trường namespace hoặc resolver khác nhau.

## 5. Tái sử dụng biểu thức có biến

Thay vì ghép một số mới vào chuỗi rồi compile lại:

```text
/catalog/book[price >= 20]
/catalog/book[price >= 30]
/catalog/book[price >= 40]
```

có thể giữ cấu trúc:

```xpath
/catalog/book[price >= $minimum]
```

và cung cấp giá trị qua XPathVariableResolver.

Biến giữ vai trò dữ liệu. Giá trị của biến không tự trở thành một phần đường dẫn hoặc một đoạn mã XPath. Nếu ứng dụng cần thay đổi cấu trúc truy vấn, đó là quyết định khác, nên dùng các biểu thức đã biết hoặc một cơ chế dựng có kiểm soát.

Theo [XPathVariableResolver](https://docs.oracle.com/en/java/javase/21/docs/api/java.xml/javax/xml/xpath/XPathVariableResolver.html), giá trị biến có thể thay đổi **giữa** các lần evaluate, nhưng không được thay đổi trong suốt một lần đánh giá.

Điều này có hai hệ quả:

1. Có thể dùng lại cùng biểu thức với minimum khác ở những lần chạy tuần tự.
2. Không cho yêu cầu khác sửa cùng nguồn biến trong khi biểu thức đang evaluate.

Dùng ConcurrentHashMap hoặc AtomicReference cho nguồn biến không tự đáp ứng điều kiện thứ hai. Từng lần đọc nguyên tử không bảo đảm một giá trị giữ nguyên cho cả quá trình đánh giá, và bản thân XPathExpression cũng có giới hạn đồng thời riêng.

Kiểu biến phải phù hợp với biểu thức. Trong ví dụ so sánh giá, chương trình dùng Double làm giá trị số theo mô hình XPath 1.0, không tùy ý đổi sang String rồi kỳ vọng mọi phép chuyển đổi ở mọi vị trí đều giống nhau.

## 6. Ví dụ hoàn chỉnh: compile một lần, đánh giá nhiều lần

Hai tài liệu có cấu trúc giống nhau nhưng dữ liệu khác. Chương trình compile hai biểu thức:

- Chọn các book có price không nhỏ hơn minimum.
- Lấy title đầu tiên của các book thỏa điều kiện.

Cả hai biểu thức được dùng lại với hai Document; sau đó minimum được đổi giữa các lần evaluate và Document A được truy vấn lại.

Lưu thành `CompiledXPathDemo.java`:

```java
import java.io.StringReader;
import java.util.HashMap;
import java.util.Map;
import java.util.StringJoiner;
import javax.xml.XMLConstants;
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

public class CompiledXPathDemo {
    private static final QName MINIMUM = new QName("minimum");

    private static Document parse(String xml) throws Exception {
        DocumentBuilderFactory factory =
                DocumentBuilderFactory.newInstance();
        factory.setNamespaceAware(true);
        factory.setFeature(
                XMLConstants.FEATURE_SECURE_PROCESSING, true);
        factory.setAttribute(XMLConstants.ACCESS_EXTERNAL_DTD, "");
        factory.setAttribute(XMLConstants.ACCESS_EXTERNAL_SCHEMA, "");

        try (StringReader reader = new StringReader(xml)) {
            return factory.newDocumentBuilder().parse(
                    new InputSource(reader));
        }
    }

    private static void show(
            String label,
            Document document,
            XPathExpression selection,
            XPathExpression firstTitle) throws Exception {

        NodeList books = (NodeList) selection.evaluate(
                document, XPathConstants.NODESET);

        StringJoiner ids = new StringJoiner(", ", "[", "]");
        for (int i = 0; i < books.getLength(); i++) {
            ids.add(books.item(i).getAttributes()
                    .getNamedItem("id").getNodeValue());
        }

        System.out.println(label + " ids: " + ids);
        System.out.println(label + " first title: "
                + firstTitle.evaluate(document));
    }

    public static void main(String[] args) throws Exception {
        Document first = parse("""
                <catalog>
                  <book id="b1">
                    <title>Java Basics</title><price>10</price>
                  </book>
                  <book id="b2">
                    <title>Concurrency</title><price>25</price>
                  </book>
                </catalog>
                """);

        Document second = parse("""
                <catalog>
                  <book id="c1">
                    <title>XML Intro</title><price>8</price>
                  </book>
                  <book id="c2">
                    <title>XPath Guide</title><price>30</price>
                  </book>
                </catalog>
                """);

        Map<QName, Object> variables = new HashMap<>();
        variables.put(MINIMUM, 20.0);

        XPath xpath = XPathFactory.newInstance().newXPath();
        xpath.setXPathVariableResolver(variables::get);

        XPathExpression selection = xpath.compile(
                "/catalog/book[price >= $minimum]");
        XPathExpression firstTitle = xpath.compile(
                "string((/catalog/book[price >= $minimum]/title)[1])");

        show("A min=20", first, selection, firstTitle);
        show("B min=20", second, selection, firstTitle);

        variables.put(MINIMUM, 5.0);
        show("A min=5", first, selection, firstTitle);

        try {
            xpath.compile("/catalog/book[");
        } catch (XPathExpressionException e) {
            System.out.println("Invalid expression rejected: true");
        }

        variables.remove(MINIMUM);
        if (!variables.containsKey(MINIMUM)
                || variables.get(MINIMUM) == null) {
            System.out.println("Missing variable rejected before evaluate: true");
        }
    }
}
```

Chạy:

```shell
javac CompiledXPathDemo.java
java CompiledXPathDemo
```

Stdout:

```text
A min=20 ids: [b2]
A min=20 first title: Concurrency
B min=20 ids: [c2]
B min=20 first title: XPath Guide
A min=5 ids: [b1, b2]
A min=5 first title: Java Basics
Invalid expression rejected: true
Missing variable rejected before evaluate: true
```

Điểm cần đối chiếu:

- selection và firstTitle chỉ được compile một lần trước các lần show.
- Cùng selection chọn b2 trong tài liệu A và c2 trong tài liệu B.
- Đổi minimum giữa các lần gọi làm kết quả A thay đổi mà không tạo chuỗi XPath mới.
- minimum không bị sửa trong lúc bất kỳ evaluate nào đang chạy.
- Một biểu thức sai cú pháp bị từ chối ở bước compile.
- Khi biến không còn được cung cấp, chương trình phát hiện trước evaluate thay vì tiếp tục đánh giá một yêu cầu thiếu dữ liệu.

Mọi thao tác ở ví dụ chạy tuần tự trên main. HashMap ở đây là nguồn giá trị do một luồng sở hữu, không phải một mẫu chia sẻ biến giữa nhiều yêu cầu đồng thời.

XML hoàn toàn nằm trong chương trình; parser được cấu hình hạn chế truy cập tài nguyên ngoài. Trong ứng dụng thực tế, chính sách parse XML là một phần riêng của vòng đời dữ liệu, không được thay thế bằng việc compile XPath.

## 7. Compile thành công chưa chứng minh mọi lần evaluate thành công

| Giai đoạn | Ví dụ vấn đề |
| --- | --- |
| Tạo/configure provider | Provider/object model hoặc khả năng cấu hình không phù hợp |
| Compile | Cú pháp sai, prefix hoặc biểu thức không được hỗ trợ theo cấu hình |
| Parse XML | XML không hợp lệ, lỗi I/O hoặc truy cập ngoài bị chặn |
| Evaluate | Thiếu biến, hàm không có resolver, context không phù hợp |
| Dùng kết quả | Ép kiểu sai, giả định luôn có một nút, dereference kết quả rỗng |

`XPathExpressionException` có thể xuất hiện ở compile hoặc evaluate theo nguyên nhân. Cần ghi nhận giai đoạn và nguyên nhân, không gộp thành một lỗi “XML sai” duy nhất.

Tài liệu XPathExpression mô tả lỗi thiếu resolver/biến trả null bằng XPathExpressionException. Trong lần kiểm chứng trên JDK 17.0.15 của ví dụ, resolver trả null trong một truy vấn NODESET lại làm lộ RuntimeException từ provider. Đây là khác biệt quan sát được giữa hợp đồng tài liệu và hành vi triển khai ấy. Vì vậy ví dụ kiểm tra biến trước evaluate; khi triển khai, cần kiểm thử cả đường lỗi với đúng JDK/provider đang dùng, không phụ thuộc tên lớp nội bộ trong stack trace.

Biểu thức /catalog/book hoàn toàn hợp lệ khi tài liệu không có book. Kết quả rỗng không tự là một ngoại lệ. Nếu nghiệp vụ bắt buộc có đúng một book, kiểm tra số lượng/kết quả theo yêu cầu ấy.

Compile cũng không xác nhận rằng một title hay price tồn tại và đúng kiểu trong tất cả tài liệu tương lai. Đó là điều kiện dữ liệu của từng lần đánh giá.

## 8. Chọn kiểu kết quả rõ ràng

```java
NodeList nodes = (NodeList) query.evaluate(
        document, XPathConstants.NODESET);
```

phù hợp khi biểu thức trả tập nút.

Một số kiểu yêu cầu phổ biến trong API truyền thống:

| XPathConstants | Kiểu Java tương ứng |
| --- | --- |
| NODESET | NodeList |
| NODE | Node |
| STRING | String |
| BOOLEAN | Boolean |
| NUMBER | Double |

Gọi evaluate(context) không có tham số kiểu trả về là yêu cầu String, không phải mặc định NodeList.

Có thể dùng cùng một biểu thức theo nhiều kiểu kết quả khi conversion được hỗ trợ, nhưng không phải mọi tổ hợp đều có ý nghĩa. Ví dụ một biểu thức count trả số không nên bị ép sang NODESET chỉ vì ứng dụng đang có một vòng duyệt NodeList.

Đối với một node-set, chuyển sang String không có nghĩa nối toàn bộ văn bản của tất cả nút. Nếu cần duyệt mọi kết quả, yêu cầu NODESET và xử lý từng nút.

Hợp đồng đánh giá và conversion được mô tả trong [XPathExpression](https://docs.oracle.com/en/java/javase/21/docs/api/java.xml/javax/xml/xpath/XPathExpression.html).

## 9. XPathExpression không tự an toàn cho nhiều luồng

Biểu thức đã compile **không được API chuẩn bảo đảm thread-safe và không reentrant**.

Không đặt một XPathExpression static final rồi cho nhiều request gọi evaluate đồng thời chỉ vì tham chiếu là final.

Final chỉ bảo vệ việc gán lại tham chiếu theo quy tắc Java. Nó không làm đối tượng evaluator, resolver hay DOM phía sau thành bất biến/an toàn đồng thời.

Các mô hình sở hữu có thể cân nhắc:

| Mô hình | Điều kiện cần kiểm soát |
| --- | --- |
| Mỗi tác vụ/yêu cầu sở hữu bộ biểu thức riêng | Không chia sẻ evaluator đang dùng; có thể tái sử dụng nhiều lần trong tác vụ |
| Một luồng sở hữu bộ biểu thức | Quản lý vòng đời và dữ liệu biến của luồng |
| Tuần tự hóa truy cập một bộ biểu thức | Bảo vệ toàn bộ evaluate và nguồn biến liên quan; chấp nhận giảm song song |
| Pool hữu hạn bộ evaluator | Cấp–trả quyền sở hữu rõ ràng, không rò dữ liệu giữa yêu cầu |

Synchronized chỉ quanh lời gọi evaluate có thể chưa đủ nếu một luồng khác sửa Map biến ở ngoài khóa. Một lần sử dụng phải bao gồm toàn bộ trạng thái mà lần đánh giá phụ thuộc.

Tính không reentrant cũng có nghĩa không gọi lại evaluate trên chính đối tượng ấy từ một callback/resolver trong khi lần evaluate trước còn đang chạy, ngay cả khi dùng cùng một luồng.

DOM còn có quy tắc đồng thời riêng. Việc tách expression theo luồng không tự cho phép một luồng sửa cùng Document trong khi luồng khác đang truy vấn nó.

## 10. Cache biểu thức ở đúng phạm vi

Nếu có một số biểu thức cố định, bộ biểu thức được chuẩn bị theo cấu hình rõ ràng thường dễ quản lý hơn cache toàn cục nhận mọi chuỗi đầu vào.

Khi thật sự cần cache, cần xác định:

- Tập biểu thức và kích thước tối đa.
- NamespaceContext, provider, object model và resolver liên quan.
- Mô hình độc quyền sử dụng mỗi XPathExpression.
- Cách cấp giá trị biến cho từng lần chạy.
- Vòng đời thay cấu hình và giải phóng bộ cache.

Không để mỗi chuỗi do người dùng gửi vào tạo một mục cache vĩnh viễn. Số lượng truy vấn không giới hạn có thể làm bộ nhớ tăng dù từng lần compile đều thành công.

Không nhầm **cache biểu thức** với **cache kết quả**. Cache kết quả còn phải tính danh tính/phiên bản tài liệu, context, biến và mọi yếu tố ảnh hưởng giá trị; nó là một bài toán khác.

Một object resolver giữ tham chiếu tới dữ liệu yêu cầu cũ cũng có thể làm kéo dài vòng đời dữ liệu. Sở hữu rõ từng evaluator giúp tránh giữ nhầm dữ liệu chỉ vì muốn tái sử dụng truy vấn.

## 11. Lợi ích hiệu năng phải được đặt đúng chỗ

Compile một lần giúp tránh yêu cầu ứng dụng chuẩn bị lại cùng cấu trúc biểu thức một cách không cần thiết. Nhưng mức lợi ích thực tế phụ thuộc provider, số lần lặp, độ lớn XML và loại truy vấn.

Tổng chi phí có thể gồm:

```text
Đọc dữ liệu
  + parse XML
  + chuẩn bị biểu thức
  + duyệt/đánh giá
  + chuyển kiểu kết quả
  + xử lý kết quả
```

Nếu parse XML hoặc duyệt một DOM rất lớn chiếm phần lớn thời gian, tái sử dụng expression không tự làm toàn bộ công việc nhanh hơn một mức cố định.

Không đưa ra số lần tăng tốc chỉ từ một ví dụ nhỏ hoặc một lần đo bằng nanoTime. Khi tối ưu thực tế, cần đo có khởi động JVM, dữ liệu đại diện, vòng đời DOM và chính sách dùng lại tương đương.

Truy vấn có cấu trúc rõ, context hẹp phù hợp và chỉ lấy dữ liệu cần dùng có thể quan trọng không kém việc compile trước.

## 12. Những lỗi thường gặp

- Compile bên trong chính vòng lặp rồi gọi đó là tái sử dụng biểu thức.
- Dùng lại InputStream đã hết và tưởng expression giữ nội dung XML.
- Ghép giá trị vào chuỗi XPath ở mỗi lần dù có thể dùng biến.
- Thay nguồn biến trong khi evaluate còn chạy.
- Cache theo String nhưng quên cấu hình namespace/provider.
- Chia sẻ expression đồng thời vì cho rằng compiled nghĩa là immutable/thread-safe.
- Giữ NodeList cũ rồi tưởng đó là lần truy vấn mới trên tài liệu mới.
- Compile thành công nên bỏ qua kiểm tra kết quả rỗng hoặc dữ liệu thiếu.
- Đưa XPath 2.0/3.x vào provider XPath 1.0 mà không kiểm tra khả năng hỗ trợ.

## 13. Tự kiểm tra

**Compile một biểu thức có gắn cố định nó vào một Document không?**  
Không. Document/context được truyền cho từng evaluate.

**Đổi minimum giữa hai lần evaluate có cần compile lại không?**  
Không nếu cùng cấu trúc biểu thức và resolver cung cấp giá trị đúng theo hợp đồng; giá trị phải ổn định trong mỗi lần chạy.

**Một biểu thức đã compile có thể thất bại khi evaluate không?**  
Có. Thiếu biến, hàm/context không phù hợp hoặc lỗi dữ liệu là những nguyên nhân cần xử lý riêng.

**Static final XPathExpression có dùng đồng thời ở mọi request được không?**  
Không theo bảo đảm API chuẩn; cần mô hình sở hữu/đồng bộ phù hợp.

**Compile trước có cache kết quả của truy vấn không?**  
Không. Đó là chuẩn bị biểu thức để đánh giá lại.

Tái sử dụng đúng nghĩa là giữ cấu trúc truy vấn đã chuẩn bị trong một phạm vi sở hữu rõ ràng, rồi truyền context và dữ liệu biến phù hợp cho từng lần đánh giá.
