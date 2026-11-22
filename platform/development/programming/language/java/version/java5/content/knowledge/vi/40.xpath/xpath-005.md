# XPathFactory, XPath và XPathExpression

## 1. Ba đối tượng nằm ở ba bước khác nhau

Một chương trình Java muốn đọc dữ liệu XML bằng XPath cần phân biệt việc chuẩn bị bộ đánh giá, cấu hình môi trường và thực thi một biểu thức cụ thể.

Ba kiểu chính:

| Kiểu | Trách nhiệm |
| --- | --- |
| XPathFactory | Tạo các đối tượng XPath theo mô hình dữ liệu và khả năng của triển khai |
| XPath | Giữ môi trường đánh giá; đánh giá trực tiếp hoặc biên dịch một biểu thức |
| XPathExpression | Đại diện biểu thức đã biên dịch để đánh giá về sau |

Luồng sử dụng:

```text
XPathFactory
      ↓ newXPath()
XPath + cấu hình ngữ cảnh
      ├── evaluate(chuỗi biểu thức, dữ liệu, kiểu kết quả)
      └── compile(chuỗi biểu thức)
                 ↓
           XPathExpression
                 ↓ evaluate(dữ liệu, kiểu kết quả)
              Kết quả
```

Factory không đọc XML chỉ vì đã được tạo. Compile một XPath cũng không có nghĩa XML đã được phân tích.

Các kiểu này thuộc javax.xml.xpath trong module java.xml. API chuẩn hiện hành hỗ trợ XPath 1.0; không mặc định mọi cú pháp XPath 2.0 hoặc 3.x đều được triển khai mặc định của JDK hiểu. Những thao tác trong bài vẫn phù hợp với Java hiện đại và ví dụ chạy trên Java 17 trở lên.

## 2. XPathFactory: chọn triển khai và tạo môi trường

Cách quen thuộc:

```java
XPathFactory factory = XPathFactory.newInstance();
XPath xpath = factory.newXPath();
```

Cần import các kiểu tương ứng trong javax.xml.xpath.

newInstance không có đối số dùng mô hình đối tượng mặc định là W3C DOM, đồng thời đi qua cơ chế tìm triển khai theo JAXP. Môi trường có thể cung cấp triển khai thích hợp qua cấu hình hoặc nhà cung cấp.

Khi muốn dùng triển khai dựng sẵn của JDK trên Java hiện đại:

```java
XPathFactory factory = XPathFactory.newDefaultInstance();
```

Không nên tự ghi cứng tên lớp nội bộ của một JDK vào mã ứng dụng chỉ để tạo factory. Dùng điểm mở rộng công khai giúp mã không phụ thuộc tên triển khai không được cam kết ổn định.

Factory có các thiết lập như tính năng và bộ phân giải mặc định cho các XPath được tạo từ nó. Nên thiết lập những điều cần thiết trước khi tạo môi trường con:

```java
factory.setFeature(XMLConstants.FEATURE_SECURE_PROCESSING, true);
XPath xpath = factory.newXPath();
```

Đoạn minh họa cần XMLConstants và xử lý/khai báo lỗi cấu hình. Bật một tính năng phải có hiệu lực thực sự; không bắt rồi bỏ qua lỗi thiết lập nếu chương trình đang dựa vào giới hạn đó.

Một XPathFactory không phải DocumentBuilderFactory. Cái đầu tạo bộ đánh giá XPath; cái sau tạo bộ phân tích XML thành DOM. Hai quyết định có thể cần cấu hình riêng.

## 3. XPath: môi trường đánh giá và cấu hình

XPath cho phép:

- Đánh giá một chuỗi biểu thức ngay.
- Biên dịch một chuỗi thành XPathExpression.
- Thiết lập NamespaceContext.
- Thiết lập bộ phân giải biến.
- Thiết lập bộ phân giải hàm mở rộng khi thực sự cần.
- Đặt lại môi trường bằng reset theo hợp đồng.

Đánh giá trực tiếp:

```java
String name = xpath.evaluate(
        "string(/catalog/item[@id='a']/name)",
        document);
```

Đây là đoạn minh họa có document là DOM đã được chuẩn bị. Overload trả String thực hiện chuyển kết quả theo quy tắc XPath, không có nghĩa mọi biểu thức đều được biến thành một danh sách văn bản đầy đủ.

Nếu chỉ dùng một biểu thức một lần, đánh giá trực tiếp thường rõ ràng. Khi cùng biểu thức được sử dụng nhiều lần, compile thể hiện ý định dùng lại cấu trúc biểu thức.

Môi trường cũng quyết định ý nghĩa các tên có tiền tố và biến. XML có namespace không tự làm XPath hiểu mọi tiền tố của tài liệu; phải có ánh xạ đúng trong NamespaceContext của bộ đánh giá.

## 4. XPathExpression: biên dịch biểu thức, không lưu kết quả

Ví dụ:

```java
XPathExpression names =
        xpath.compile("/catalog/item/name");
```

Lần compile chuẩn bị biểu thức để đánh giá sau. Nó có thể phát hiện lỗi cú pháp trước khi chương trình bắt đầu xử lý hàng loạt tài liệu.

Sau đó:

```java
NodeList firstResult = (NodeList) names.evaluate(
        firstDocument, XPathConstants.NODESET);

NodeList secondResult = (NodeList) names.evaluate(
        secondDocument, XPathConstants.NODESET);
```

Đây là đoạn minh họa với các DOM đã có.

Cùng một XPathExpression có thể được đánh giá tuần tự trên các tài liệu phù hợp khác nhau. Nó không bị gắn cố định vào firstDocument ở lần gọi đầu.

Cần tránh ba hiểu nhầm:

1. Compile không phân tích tài liệu XML.
2. Compile không thực hiện truy vấn và lưu sẵn kết quả.
3. Compile không tự làm đối tượng an toàn để nhiều luồng cùng dùng.

Nếu dữ liệu ngữ cảnh đổi, một lần đánh giá mới tính kết quả trên ngữ cảnh mới. Nếu cây DOM bị chỉnh sửa, còn phải xét quy tắc cập nhật và đồng bộ của DOM; việc đã biên dịch biểu thức không đóng băng tài liệu.

Không khẳng định compile luôn làm mọi trường hợp nhanh hơn. Nó tránh lặp lại bước chuẩn bị biểu thức ở tầng API, nhưng chi phí đọc XML, dựng DOM và duyệt dữ liệu vẫn còn. Đo trên tải thực tế khi hiệu năng là yêu cầu quan trọng.

## 5. Cấu hình phải rõ trước lúc compile

Một biểu thức có biến:

```xpath
string(/catalog/item[@id=$wanted]/name)
```

cần bộ phân giải để lấy giá trị của wanted.

Điểm quan trọng của hợp đồng: XPathExpression dùng bộ phân giải biến đang có hiệu lực tại thời điểm compile. Không biên dịch trước, rồi thay bộ phân giải của XPath và mặc định đối tượng đã biên dịch tự nhận cấu hình mới.

Nhưng điều đó không có nghĩa mọi giá trị biến bị chụp cố định tại compile. Bộ phân giải có thể cung cấp giá trị cho từng lần đánh giá. Ví dụ một Map đứng sau bộ phân giải có thể đổi từ a sang b giữa hai lần gọi tuần tự.

Quy tắc cần giữ là **giá trị của một biến phải ổn định trong suốt một lần đánh giá**. Không để luồng khác cập nhật Map đang dùng giữa lúc evaluate chạy.

Biến giúp tách cấu trúc biểu thức khỏi dữ liệu cần tìm. Không cần ghép trực tiếp đầu vào người dùng vào mẫu như:

```java
// Rủi ro: input có thể thay đổi cú pháp hoặc điều kiện của biểu thức.
String query = "/catalog/item[@id='" + input + "']/name";
```

Đây là đoạn minh họa lỗi thiết kế khi input không được kiểm soát. Dùng một biểu thức có biến và bộ phân giải theo hợp đồng thường làm ranh giới rõ hơn.

NamespaceContext và bộ phân giải hàm cũng cần được thiết lập có chủ ý. Hàm chuẩn như string và count không đòi bạn tự viết bộ phân giải hàm mở rộng. Chỉ mở thêm khả năng gọi hàm khi nhu cầu và phạm vi cho phép rõ ràng.

## 6. Chọn kiểu trả về tại lần đánh giá

Các overload evaluate có thể nhận hằng kiểu kết quả:

| XPathConstants | Kiểu Java thường nhận với DOM | Mục tiêu |
| --- | --- | --- |
| STRING | String | Giá trị chuỗi theo quy tắc XPath |
| NUMBER | Double | Giá trị số của XPath 1.0 |
| BOOLEAN | Boolean | Kiểm tra điều kiện |
| NODE | org.w3c.dom.Node | Một nút |
| NODESET | org.w3c.dom.NodeList | Tập các nút |

Một XPathExpression có thể được đánh giá với kiểu kết quả phù hợp ở từng lần gọi. Không cần tạo một factory mới chỉ để đổi từ NODE sang NODESET.

Lưu ý:

- NODE có thể trả null khi không có nút phù hợp.
- NODESET có thể là danh sách rỗng.
- Chuyển một node-set sang STRING không tự nối văn bản của mọi nút; theo quy tắc có thể chỉ dùng nút đầu theo thứ tự tài liệu.
- NUMBER trong hệ XPath 1.0 là Double, không phải BigDecimal hay Integer tự động.
- Yêu cầu một kiểu không phù hợp có thể tạo lỗi chuyển đổi/đánh giá, không phải biến đổi tùy ý mọi biểu thức thành mọi kiểu.

Java hiện đại còn có các overload evaluateExpression trả kết quả theo kiểu lớp. Các overload evaluate với XPathConstants vẫn là API hiện hành và đủ cho mục tiêu so sánh ba đối tượng trong bài.

## 7. Ví dụ Java chạy được

Chương trình:

- Tạo factory và XPath.
- Đánh giá trực tiếp một lần.
- Biên dịch một biểu thức có biến.
- Dùng lại nó với hai giá trị và hai tài liệu.
- Yêu cầu những kiểu kết quả khác nhau.
- Kiểm chứng lỗi cú pháp ở bước compile.

Lưu thành `XPathObjectsDemo.java`:

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
import org.w3c.dom.Node;
import org.w3c.dom.NodeList;
import org.xml.sax.InputSource;

public class XPathObjectsDemo {
    private static Document parse(String xml) throws Exception {
        DocumentBuilderFactory parser =
                DocumentBuilderFactory.newDefaultInstance();
        parser.setNamespaceAware(true);
        parser.setFeature(XMLConstants.FEATURE_SECURE_PROCESSING, true);
        parser.setFeature(
                "http://apache.org/xml/features/disallow-doctype-decl", true);
        parser.setAttribute(XMLConstants.ACCESS_EXTERNAL_DTD, "");
        parser.setAttribute(XMLConstants.ACCESS_EXTERNAL_SCHEMA, "");

        try (StringReader reader = new StringReader(xml)) {
            return parser.newDocumentBuilder()
                    .parse(new InputSource(reader));
        }
    }

    public static void main(String[] args) throws Exception {
        Document first = parse("""
                <catalog>
                  <item id="a"><name>Alpha</name></item>
                  <item id="b"><name>Beta</name></item>
                </catalog>
                """);
        Document second = parse("""
                <catalog>
                  <item id="b"><name>Beta2</name></item>
                </catalog>
                """);

        XPathFactory factory = XPathFactory.newDefaultInstance();
        factory.setFeature(XMLConstants.FEATURE_SECURE_PROCESSING, true);
        XPath xpath = factory.newXPath();

        Map<QName, Object> variables = new HashMap<>();
        QName wanted = new QName("wanted");
        xpath.setXPathVariableResolver(variables::get);

        System.out.println("direct=" + xpath.evaluate(
                "string(/catalog/item[@id='a']/name)", first));

        XPathExpression byId = xpath.compile(
                "string(/catalog/item[@id=$wanted]/name)");

        variables.put(wanted, "a");
        System.out.println("compiledA=" + byId.evaluate(first));

        variables.put(wanted, "b");
        System.out.println("compiledB=" + byId.evaluate(first));
        System.out.println("other=" + byId.evaluate(second));

        XPathExpression count = xpath.compile("count(/catalog/item)");
        Double number = (Double) count.evaluate(
                first, XPathConstants.NUMBER);
        System.out.println("count=" + number);

        XPathExpression names = xpath.compile("/catalog/item/name");
        Node firstName = (Node) names.evaluate(first, XPathConstants.NODE);
        System.out.println("first=" + firstName.getTextContent());

        NodeList allNames = (NodeList) names.evaluate(
                first, XPathConstants.NODESET);
        StringJoiner joined = new StringJoiner(" | ");
        for (int i = 0; i < allNames.getLength(); i++) {
            joined.add(allNames.item(i).getTextContent());
        }
        System.out.println("all=" + joined);

        Boolean exists = (Boolean) xpath.evaluate(
                "boolean(/catalog/item[@id='b'])",
                first, XPathConstants.BOOLEAN);
        System.out.println("exists=" + exists);

        try {
            xpath.compile("/catalog/item[");
            throw new AssertionError("Invalid expression was accepted");
        } catch (XPathExpressionException e) {
            System.out.println("invalid=" + e.getClass().getSimpleName());
        }
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```shell
javac --release 17 XPathObjectsDemo.java
java XPathObjectsDemo
```

Stdout:

```text
direct=Alpha
compiledA=Alpha
compiledB=Beta
other=Beta2
count=2.0
first=Alpha
all=Alpha | Beta
exists=true
invalid=XPathExpressionException
```

Lập luận về kết quả:

1. Direct dùng chuỗi biểu thức trên XPath nên trả Alpha ngay.
2. Biểu thức byId được compile một lần với bộ phân giải đã thiết lập.
3. Biến wanted đổi giữa các lần đánh giá tuần tự, nên compiledA và compiledB khác nhau.
4. Cùng biểu thức trên tài liệu second tìm được Beta2; nó không giữ kết quả Beta của tài liệu first.
5. NUMBER cho kết quả Double nên in count bằng 2.0.
6. NODE lấy một nút, còn NODESET cho phép duyệt cả hai tên.
7. Biểu thức thiếu phần đóng predicate bị từ chối; chương trình chỉ in tên loại lỗi, không phụ thuộc thông báo riêng của triển khai.

Map trong ví dụ chỉ được một luồng thao tác. Nó không phải mẫu dùng chung biến giữa nhiều yêu cầu đồng thời.

Bộ phân tích XML và bộ đánh giá XPath được cấu hình riêng. XML được phân tích từ StringReader trong phạm vi rõ ràng; sau đó các lần evaluate dùng DOM đã có thay vì đọc lại nguồn XML.

## 8. DOM đã có và InputSource là hai đường khác nhau

XPath và XPathExpression có thể nhận một đối tượng ngữ cảnh hoặc một InputSource theo overload tương ứng.

Với DOM đã phân tích:

```text
Nguồn XML → bộ phân tích được cấu hình → Document
                                        ↓
                         nhiều biểu thức/đánh giá
```

Với InputSource:

```text
Nguồn XML → evaluate qua overload InputSource
                ↓
        API dựng mô hình rồi đánh giá
```

Điều cần hiểu là compile không loại bỏ bước dựng mô hình dữ liệu nếu mỗi lần evaluate vẫn nhận một nguồn XML mới. Nó chỉ chuẩn bị biểu thức.

Nếu cần thực hiện nhiều truy vấn trên cùng một tài liệu, phân tích một lần thành DOM thường giúp ranh giới chi phí và cấu hình bộ phân tích rõ ràng hơn.

Đặc biệt, cấu hình an toàn cho một DocumentBuilderFactory do bạn tạo không tự truyền sang một đường phân tích XML khác bên trong một overload InputSource. Hãy chọn đường xử lý mà bạn thực sự kiểm soát theo yêu cầu ứng dụng.

Một stream hoặc reader đầu vào cần chủ sở hữu vòng đời riêng. Factory, XPath và XPathExpression không cung cấp một phương thức close để thay việc đóng nguồn I/O bên ngoài.

## 9. Dùng lại tuần tự khác dùng chung đồng thời

Các hợp đồng của XPathFactory, XPath và XPathExpression không cho phép mặc định coi chúng an toàn giữa nhiều luồng. Chúng cũng có giới hạn về việc gọi lồng lại trong lúc một thao tác đang chạy.

Vì vậy:

```java
// Không tự an toàn chỉ vì final hoặc đã compile.
static final XPathExpression SHARED = createExpression();
```

không đủ để chứng minh mọi yêu cầu có thể gọi evaluate đồng thời. Đây là đoạn cấu trúc minh họa, với createExpression đại diện phần khởi tạo.

Một đối tượng final chỉ giữ tham chiếu không bị gán lại; nó không thay đổi hợp đồng đồng thời của đối tượng được tham chiếu.

Các lựa chọn cần đánh giá theo tải:

- Tạo môi trường và biểu thức theo phạm vi một lần xử lý.
- Giữ đối tượng riêng theo luồng hoặc theo thành phần có quyền sử dụng độc quyền.
- Dùng một cơ chế cho mượn có kiểm soát nếu chi phí tạo đáng kể.
- Đồng bộ truy cập nếu chấp nhận việc tuần tự hóa và đã xét cả trạng thái phụ thuộc.

Không chỉ bảo vệ XPathExpression mà quên Map biến, bộ phân giải, NamespaceContext khả biến hoặc DOM được sửa đồng thời. Một phép đánh giá phụ thuộc cả tập trạng thái đó.

Giới hạn không gọi lồng lại còn quan trọng nếu một bộ phân giải hoặc hàm tùy biến gọi lại cùng bộ đánh giá từ bên trong lần evaluate hiện tại. Cùng luồng không đồng nghĩa an toàn cho kiểu gọi đó.

## 10. Lưu biểu thức dùng lại phải tính đến cấu hình

Nếu ứng dụng muốn lưu các biểu thức đã compile để dùng lại, không chỉ xem chuỗi XPath là toàn bộ danh tính cấu hình.

Cùng chuỗi:

```xpath
/c:item
```

có thể mang nghĩa khác nhau nếu tiền tố c được ánh xạ sang URI khác. Bộ phân giải biến và hàm cũng có thể mang trạng thái riêng.

Một cơ chế lưu dùng lại cần xác định:

- Cấu hình namespace và các khả năng được cho phép.
- Cách cấp giá trị biến cho từng lần gọi.
- Ai được quyền sử dụng biểu thức tại một thời điểm.
- Giới hạn số biểu thức được lưu.
- Khi nào cấu hình thay đổi thì tạo biểu thức mới.

Không nhận vô hạn chuỗi biểu thức từ bên ngoài rồi compile và giữ mãi. Ngoài chi phí bộ nhớ còn có yêu cầu giới hạn độ phức tạp và phạm vi truy vấn theo bài toán.

Đây là vấn đề thiết kế sử dụng API; việc XPathExpression không có close không có nghĩa mọi bộ nhớ mà ứng dụng giữ tham chiếu tới nó được giải phóng tự động ngay khi không còn cần về mặt nghiệp vụ.

## 11. Phân biệt lỗi cấu hình, lỗi biểu thức và kết quả rỗng

| Tình huống | Cách hiểu |
| --- | --- |
| Không tạo được factory theo mô hình yêu cầu | Vấn đề chọn/cấu hình triển khai |
| Thiết lập tính năng không được hỗ trợ | Vấn đề cấu hình; cần quyết định có được tiếp tục không |
| Compile biểu thức sai cú pháp | Lỗi biểu thức, có thể nhận XPathExpressionException |
| Biến không được giải quyết hoặc trả null | Có thể lỗi lúc đánh giá |
| Biểu thức đúng nhưng không có nút khớp | Kết quả rỗng/null tùy kiểu; không nhất thiết ngoại lệ |
| XML không phân tích được | Lỗi dữ liệu/nguồn ở tầng dựng mô hình |

Không bắt tất cả lỗi rồi trả String rỗng nếu String rỗng còn là một kết quả hợp lệ. Làm vậy khiến người gọi không phân biệt được “không có dữ liệu” với “truy vấn chưa từng chạy thành công”.

Khi báo lỗi, ghi đủ biểu thức hoặc mã truy vấn, kiểu kết quả và ngữ cảnh cấu hình cần thiết. Không ghi toàn bộ XML nhạy cảm hay giá trị bí mật chỉ để chẩn đoán một lỗi compile.

Việc reset XPath đưa môi trường về cấu hình ban đầu theo hợp đồng. Nó không phải thao tác chỉnh cú pháp hoặc làm mới dữ liệu của mọi XPathExpression mà ứng dụng đã giữ. Khi cấu hình sử dụng thay đổi, nên quản lý việc tạo môi trường và biểu thức mới một cách rõ ràng.

## 12. Tự kiểm tra

1. Factory có tự phân tích tài liệu XML khi newXPath không?
2. Compile trả kết quả truy vấn hay đối tượng biểu thức?
3. Có thể dùng một biểu thức đã compile lần lượt trên hai Document không?
4. Đổi wanted giữa hai lần evaluate có bắt buộc compile lại nếu dùng cùng bộ phân giải đã thiết kế cho việc đó không?
5. Vì sao final XPathExpression không đủ để chứng minh an toàn khi nhiều luồng cùng dùng?
6. NODE và NODESET khác nhau ở điều gì?
7. Compile có loại bỏ chi phí đọc XML nếu mỗi lần evaluate vẫn nhận một InputSource mới không?

Đáp án:

1. Không.
2. Trả XPathExpression.
3. Có, với mô hình ngữ cảnh được triển khai hỗ trợ.
4. Không; giá trị có thể khác giữa hai lần, nhưng phải ổn định trong mỗi lần.
5. Final không thay hợp đồng đồng thời của đối tượng và trạng thái phụ thuộc.
6. Một nút so với danh sách các nút.
7. Không; chuẩn bị biểu thức và dựng mô hình XML là hai bước khác nhau.

Hãy tạo đúng môi trường, cấu hình trước khi compile và chọn kiểu kết quả ở ranh giới đánh giá. Sau đó quản lý quyền sử dụng biểu thức và dữ liệu ngữ cảnh như một phần của thiết kế ứng dụng.

## Tài liệu đối chiếu

- [XPathFactory — Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.xml/javax/xml/xpath/XPathFactory.html): tạo triển khai và XPath.
- [XPath — Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.xml/javax/xml/xpath/XPath.html): môi trường, compile, evaluate và bộ phân giải.
- [XPathExpression — Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.xml/javax/xml/xpath/XPathExpression.html): biểu thức đã biên dịch và hợp đồng đánh giá.
