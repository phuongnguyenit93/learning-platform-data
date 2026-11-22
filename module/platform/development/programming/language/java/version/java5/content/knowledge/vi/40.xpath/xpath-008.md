# Kiểu kết quả qua XPathConstants

## 1. Chọn biểu thức chưa đủ; còn phải chọn cách nhận kết quả

Cùng biểu thức:

```xpath
/items/item/name
```

có thể được ứng dụng dùng theo những mục tiêu khác nhau:

- Lấy giá trị chuỗi của một tên.
- Lấy một Node để tiếp tục truy cập DOM.
- Lấy toàn bộ các tên.
- Chỉ kiểm tra có tên nào tồn tại không.

XPathConstants cho các overload evaluate biết kiểu kết quả Java mà người gọi muốn nhận. Nó không đơn thuần là một phép ép kiểu viết cho trình biên dịch; bộ đánh giá còn thực hiện quy tắc chuyển đổi của XPath trước khi trả kết quả.

Luồng xử lý:

```text
Biểu thức + ngữ cảnh
        ↓ đánh giá theo XPath
Kết quả của biểu thức
        ↓ chuyển theo kiểu yêu cầu
Đối tượng Java
        ↓ ép kiểu Java phù hợp
Mã ứng dụng sử dụng
```

Bài dùng API javax.xml.xpath chuẩn, với hệ kiểu XPath 1.0 mà Java hiện đại hỗ trợ. Những hằng và overload dưới đây vẫn có giá trị; chương trình chạy trên Java 17 trở lên.

## 2. Bảng ánh xạ năm hằng kết quả

| Hằng | Kiểu Java nhận về với mô hình DOM | Câu hỏi phù hợp |
| --- | --- | --- |
| XPathConstants.STRING | String | Giá trị chuỗi theo quy tắc XPath là gì? |
| XPathConstants.NUMBER | Double | Giá trị số là gì? |
| XPathConstants.BOOLEAN | Boolean | Điều kiện đúng hay sai theo quy tắc XPath? |
| XPathConstants.NODE | org.w3c.dom.Node | Một nút được chọn là nút nào? |
| XPathConstants.NODESET | org.w3c.dom.NodeList | Những nút nào được chọn? |

Các hằng kết quả là QName. Dùng đúng hằng công khai, không tự thay bằng chuỗi `"STRING"` hoặc `"NODESET"`.

XPathConstants còn có DOM_OBJECT_MODEL là URI của mô hình DOM. Nó không phải một kiểu kết quả thứ sáu để truyền thay cho NODESET.

NODE là cách API Java cung cấp một Node từ kết quả chọn nút. Nó không bổ sung một kiểu dữ liệu số/chuỗi mới cho ngôn ngữ XPath 1.0. NODE và NODESET đều liên quan đến kết quả tập nút, nhưng phục vụ nhu cầu Java khác nhau.

## 3. STRING: giá trị chuỗi, không phải toàn bộ XML

Ví dụ:

```java
String name = (String) xpath.evaluate(
        "/items/item/name",
        document,
        XPathConstants.STRING);
```

Đây là đoạn minh họa có xpath và document đã được tạo.

Nếu biểu thức chọn nhiều name, chuyển sang STRING không tự nối mọi tên. Quy tắc chuyển node-set sang chuỗi của XPath 1.0 dùng giá trị chuỗi của nút đầu theo thứ tự tài liệu.

Vì vậy nếu có Alpha và Beta, kết quả không tự trở thành `"Alpha, Beta"`. Muốn danh sách, yêu cầu NODESET rồi tự xử lý từng nút theo hợp đồng.

Giá trị chuỗi của một phần tử cũng không phải bản XML có đầy đủ thẻ. Chẳng hạn:

```xml
<name>Java <em>Core</em></name>
```

giá trị chuỗi của phần tử là `Java Core`, không phải một chuỗi có thẻ em. Nếu cần xuất XML, phải dùng cơ chế tuần tự hóa phù hợp.

Overload:

```java
String name = xpath.evaluate("/items/item/name", document);
```

trả String theo cơ chế tương ứng. Không có tham số kiểu không có nghĩa “tự suy ra một List”.

STRING tiện khi hợp đồng thực sự cần một giá trị văn bản. Nó có thể làm mất thông tin về số nút, loại nút và việc nút có tồn tại hay không.

## 4. NODE: giữ quyền truy cập cấu trúc DOM

```java
Node nameNode = (Node) xpath.evaluate(
        "/items/item/name",
        document,
        XPathConstants.NODE);

if (nameNode != null) {
    String value = nameNode.getTextContent();
}
```

NODE giúp ứng dụng giữ thông tin cấu trúc như tên nút, loại nút, thuộc tính hoặc quan hệ với các nút khác.

Nếu biểu thức chọn nhiều nút, lấy một Node không tự chứng minh chỉ có đúng một kết quả. Trong bộ DOM chuẩn dùng ở ví dụ, kết quả này là nút đầu phù hợp; các kết quả còn lại không được duyệt.

Nếu yêu cầu nghiệp vụ là “phải có đúng một phần tử”, dùng NODESET để kiểm tra số lượng hoặc một kiểm tra tương đương. Đừng biến việc lấy được một Node thành bằng chứng duy nhất.

Khi không có nút phù hợp, NODE có thể trả null. Kiểm tra trước khi gọi getTextContent hoặc thao tác DOM để tránh NullPointerException ở một chỗ khiến nguyên nhân thật khó nhận ra.

Đối với thuộc tính, biểu thức như `/items/item/@id` trả nút thuộc tính khi dùng NODE. Nó không biến thuộc tính thành một phần tử id.

## 5. NODESET: lấy tất cả các nút phù hợp

```java
NodeList names = (NodeList) xpath.evaluate(
        "/items/item/name",
        document,
        XPathConstants.NODESET);

for (int i = 0; i < names.getLength(); i++) {
    Node node = names.item(i);
    String value = node.getTextContent();
}
```

NodeList là giao diện DOM, không phải java.util.List<Node>. Nó có getLength và item; không mặc định có mọi thao tác của một Collection Java.

Các chỉ số cần phân biệt:

- Predicate vị trí trong XPath bắt đầu từ một, chẳng hạn `[1]`.
- Chỉ số NodeList.item trong Java bắt đầu từ không.

NODESET rỗng có getLength bằng không. Không cần dùng ngoại lệ như một cơ chế bình thường để biết “không có kết quả”.

Nếu muốn giữ các chuỗi tên để dùng tiếp, có thể sao chép sang một List<String> do ứng dụng sở hữu. Việc đó khác với giữ NodeList và các Node vẫn tham chiếu đến cây DOM.

Khi ứng dụng sửa DOM sau truy vấn, cần xét hợp đồng của mô hình và triển khai thay vì mặc định kết quả là một bản sao bất biến của dữ liệu. Tốt nhất xác định rõ giai đoạn đọc hoặc tạo ảnh chụp phù hợp.

## 6. NUMBER: Double của XPath, không phải số chính xác tùy ý

```java
Double count = (Double) xpath.evaluate(
        "count(/items/item)",
        document,
        XPathConstants.NUMBER);
```

Với ba item, kết quả có thể in là `3.0` vì kiểu Java là Double, dù hàm count mang giá trị nguyên.

Không ép trực tiếp Object nhận về sang Integer:

```java
// SAI: NUMBER ánh xạ thành Double.
Integer count = (Integer) xpath.evaluate(
        "count(/items/item)", document, XPathConstants.NUMBER);
```

Đoạn trên minh họa một lỗi ép kiểu ở Java. Muốn đưa vào kiểu nguyên, cần chuyển từ Double sau khi kiểm tra điều kiện phù hợp với miền giá trị, độ chính xác và giới hạn kiểu đích.

NUMBER còn tuân theo quy tắc chuyển số của XPath:

- Một tập nút có thể được chuyển qua giá trị chuỗi của nút đầu.
- Chuỗi không có biểu diễn số hợp lệ có thể cho NaN.
- Một tập nút rỗng chuyển sang số cũng có thể cho NaN.
- `count` của một tập rỗng là 0.0; điều này khác với chuyển chính tập rỗng đó thành NUMBER.

NaN không phải ngoại lệ để tự bị bắt bằng catch. Kiểm tra bằng Double.isNaN hoặc phương thức isNaN của đối tượng Double. So sánh `value == Double.NaN` không phải phép kiểm tra đúng.

NUMBER của XPath 1.0 dùng số dấu phẩy động. Nó không phải công cụ giữ độ chính xác thập phân tùy ý cho số tiền. Nếu cần BigDecimal, có thể lấy nội dung chuỗi của nút đã xác minh rồi phân tích và áp dụng quy tắc nghiệp vụ phù hợp ở Java.

Cú pháp số của XPath cũng không phải cú pháp tùy locale người dùng. Chuỗi có dấu phẩy thập phân hoặc dấu phân nhóm không tự được hiểu như một bộ phân tích số bản địa hóa.

## 7. BOOLEAN: sự tồn tại khác với nội dung true/false

Đây là bẫy dễ gặp nhất:

```xml
<active>false</active>
```

Nếu đánh giá đường dẫn chọn nút active và yêu cầu BOOLEAN, kết quả là true vì tập nút không rỗng. Bộ đánh giá không tự phân tích nội dung `false` thành Boolean.FALSE của ứng dụng.

So sánh:

```xpath
/items/item[@id='a']/active
```

với kiểu BOOLEAN trả lời “có nút active phù hợp không?”.

Còn:

```xpath
/items/item[@id='a']/active = 'true'
```

trả lời điều kiện so sánh nội dung theo biểu thức đã viết.

Trong XPath 1.0, một số quy tắc chuyển BOOLEAN quan trọng là:

| Giá trị nguồn | Kết quả chuyển boolean |
| --- | --- |
| Node-set không rỗng | true |
| Node-set rỗng | false |
| Chuỗi không rỗng, kể cả `"false"` hoặc `"0"` | true |
| Chuỗi rỗng | false |
| Số bằng không hoặc NaN | false |
| Số khác không và không phải NaN | true |

Hàm false() tạo giá trị boolean sai. Chuỗi ký tự 'false' là một đối tượng thuộc loại chuỗi, nên quy tắc chuyển boolean khác.

Khi XML biểu diễn boolean nghiệp vụ, xác định rõ miền dữ liệu được chấp nhận: true/false, có cho 1/0 không, có bỏ khoảng trắng hay phân biệt hoa/thường không. Không để một phép chuyển BOOLEAN ngầm quyết định tất cả quy tắc đó.

## 8. Thiếu nút và nút có nội dung rỗng

Hai trường hợp:

```xml
<name/>
```

và không có phần tử name không giống nhau về cấu trúc, nhưng đều có thể cho String rỗng khi yêu cầu STRING.

Đối chiếu:

| Trường hợp | NODE | NODESET | STRING |
| --- | --- | --- | --- |
| Không có nút phù hợp | null | Độ dài 0 | Chuỗi rỗng |
| Có một phần tử rỗng | Một Node | Độ dài 1 | Chuỗi rỗng |

Nếu dữ liệu bắt buộc phải có phần tử, chỉ kiểm tra String rỗng không đủ để phân loại “thiếu” và “có nhưng trống”.

Tương tự, với thuộc tính bắt buộc, lấy NODE hoặc NODESET có thể giúp xác nhận sự hiện diện trước khi kiểm tra giá trị. Sau đó áp quy tắc nội dung riêng, chẳng hạn có được rỗng hoặc chỉ chứa khoảng trắng hay không.

Khi kết quả rỗng bất ngờ, còn phải kiểm tra biểu thức, ngữ cảnh và namespace trước khi kết luận dữ liệu không tồn tại.

## 9. Ví dụ Java chạy được

Chương trình minh chứng cả năm kiểu, trường hợp thiếu/rỗng và một lỗi yêu cầu Node từ giá trị số.

Lưu thành `XPathResultTypesDemo.java`:

```java
import java.io.StringReader;
import java.util.StringJoiner;
import javax.xml.XMLConstants;
import javax.xml.parsers.DocumentBuilderFactory;
import javax.xml.xpath.XPath;
import javax.xml.xpath.XPathConstants;
import javax.xml.xpath.XPathExpressionException;
import javax.xml.xpath.XPathFactory;
import org.w3c.dom.Document;
import org.w3c.dom.Node;
import org.w3c.dom.NodeList;
import org.xml.sax.InputSource;

public class XPathResultTypesDemo {
    private static Document parse() throws Exception {
        String xml = """
                <items>
                  <item id="a">
                    <name>Alpha</name>
                    <price>10.50</price>
                    <active>false</active>
                  </item>
                  <item id="b">
                    <name>Beta</name>
                    <price>20</price>
                  </item>
                  <item id="c"><name/></item>
                </items>
                """;

        DocumentBuilderFactory factory =
                DocumentBuilderFactory.newDefaultInstance();
        factory.setNamespaceAware(true);
        factory.setFeature(XMLConstants.FEATURE_SECURE_PROCESSING, true);
        factory.setFeature(
                "http://apache.org/xml/features/disallow-doctype-decl", true);
        factory.setAttribute(XMLConstants.ACCESS_EXTERNAL_DTD, "");
        factory.setAttribute(XMLConstants.ACCESS_EXTERNAL_SCHEMA, "");

        try (StringReader reader = new StringReader(xml)) {
            return factory.newDocumentBuilder()
                    .parse(new InputSource(reader));
        }
    }

    public static void main(String[] args) throws Exception {
        Document document = parse();
        XPath xpath = XPathFactory.newDefaultInstance().newXPath();

        String text = (String) xpath.evaluate(
                "/items/item/name", document, XPathConstants.STRING);
        System.out.println("string=" + text);

        Node first = (Node) xpath.evaluate(
                "/items/item/name", document, XPathConstants.NODE);
        System.out.println("node=" + first.getNodeName()
                + ":" + first.getTextContent());

        NodeList names = (NodeList) xpath.evaluate(
                "/items/item/name", document, XPathConstants.NODESET);
        StringJoiner joined = new StringJoiner(" | ");
        for (int i = 0; i < names.getLength(); i++) {
            joined.add("[" + names.item(i).getTextContent() + "]");
        }
        System.out.println("nodes=" + joined);

        Double count = (Double) xpath.evaluate(
                "count(/items/item)", document, XPathConstants.NUMBER);
        Double total = (Double) xpath.evaluate(
                "sum(/items/item/price)", document, XPathConstants.NUMBER);
        System.out.println("count=" + count);
        System.out.println("sum=" + total);

        Boolean presence = (Boolean) xpath.evaluate(
                "/items/item[@id='a']/active",
                document, XPathConstants.BOOLEAN);
        Boolean trueValue = (Boolean) xpath.evaluate(
                "/items/item[@id='a']/active = 'true'",
                document, XPathConstants.BOOLEAN);
        Boolean nonemptyString = (Boolean) xpath.evaluate(
                "'false'", document, XPathConstants.BOOLEAN);
        System.out.println("activeExists=" + presence);
        System.out.println("activeIsTrue=" + trueValue);
        System.out.println("booleanOfFalseText=" + nonemptyString);

        Node missing = (Node) xpath.evaluate(
                "/items/missing", document, XPathConstants.NODE);
        NodeList missingNodes = (NodeList) xpath.evaluate(
                "/items/missing", document, XPathConstants.NODESET);
        String missingText = (String) xpath.evaluate(
                "/items/missing", document, XPathConstants.STRING);
        String emptyText = (String) xpath.evaluate(
                "/items/item[@id='c']/name",
                document, XPathConstants.STRING);
        Double missingNumber = (Double) xpath.evaluate(
                "/items/missing", document, XPathConstants.NUMBER);

        System.out.println("missingNode=" + (missing == null));
        System.out.println("missingSize=" + missingNodes.getLength());
        System.out.println("missingString=<" + missingText + ">");
        System.out.println("emptyString=<" + emptyText + ">");
        System.out.println("missingIsNaN=" + missingNumber.isNaN());

        try {
            xpath.evaluate("count(/items/item)",
                    document, XPathConstants.NODE);
            throw new AssertionError("Scalar cannot become a DOM node");
        } catch (XPathExpressionException e) {
            System.out.println("invalidNode="
                    + e.getClass().getSimpleName());
        }
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```shell
javac --release 17 XPathResultTypesDemo.java
java XPathResultTypesDemo
```

Stdout:

```text
string=Alpha
node=name:Alpha
nodes=[Alpha] | [Beta] | []
count=3.0
sum=30.5
activeExists=true
activeIsTrue=false
booleanOfFalseText=true
missingNode=true
missingSize=0
missingString=<>
emptyString=<>
missingIsNaN=true
invalidNode=XPathExpressionException
```

Những khác biệt quan trọng:

- STRING của đường dẫn nhiều name chỉ cho Alpha, còn NODESET giữ cả ba phần tử, kể cả name rỗng.
- activeExists là true dù nội dung là false.
- Chuỗi 'false' không rỗng nên chuyển BOOLEAN thành true.
- missingString và emptyString in giống nhau, nhưng NODE/NODESET cho phép phân biệt cấu trúc.
- count của ba item là 3.0; chuyển một đường dẫn không có nút thành NUMBER cho NaN.
- Một giá trị scalar như kết quả count không được tự dựng thành một DOM Node.

Parser trong ví dụ được cấu hình không nhận DOCTYPE và không truy cập DTD/schema bên ngoài. Đó là ranh giới dựng DOM; XPathConstants chỉ quyết định kiểu nhận kết quả, không tự thay thế cấu hình bộ phân tích XML.

## 10. Chuyển đổi XPath và ép kiểu Java là hai bước khác nhau

Ví dụ:

```java
Object result = xpath.evaluate(
        "count(/items/item)", document, XPathConstants.NUMBER);
Double count = (Double) result;
```

Bước đầu bộ đánh giá tạo kết quả Double theo hằng NUMBER. Bước sau Java kiểm tra phép ép kiểu Object sang Double.

Nếu thay thành Integer, đó là lỗi ép kiểu Java. Nếu yêu cầu NODE cho biểu thức trả số, bộ đánh giá có thể ném XPathExpressionException ở bước chuyển kiểu XPath trước khi Java nhận được Node.

Một hằng kiểu không được API hỗ trợ có thể làm evaluate báo IllegalArgumentException. Dùng đúng các hằng công khai giúp tránh nhầm giữa tên kiểu, kiểu Java và QName mà API nhận.

Đừng sửa một lỗi ép kiểu bằng cách gọi toString trên mọi kết quả rồi phân tích lại nếu điều đó làm mất thông tin. Chọn đúng kiểu ngay từ ranh giới đánh giá thường rõ và dễ kiểm thử hơn.

## 11. XPathExpression đã compile dùng cùng hợp đồng kiểu

Các quy tắc không chỉ áp dụng cho XPath.evaluate trực tiếp.

```java
XPathExpression expression =
        xpath.compile("/items/item/name");

NodeList names = (NodeList) expression.evaluate(
        document, XPathConstants.NODESET);

String firstValue = (String) expression.evaluate(
        document, XPathConstants.STRING);
```

Đây là đoạn minh họa với các import và biến đã có. Cùng biểu thức chọn nút nhưng mỗi lần yêu cầu một hình thức nhận kết quả khác nhau.

Compile không tạo sẵn NodeList và không đóng băng nội dung DOM. Kiểu kết quả được yêu cầu tại evaluate; không cần compile lại chỉ để nhận STRING thay cho NODESET nếu phép chuyển có nghĩa.

Không dùng điều này để suy ra rằng mọi kiểu đều chuyển được sang nhau. Biểu thức scalar vẫn không tự trở thành cây DOM. Đồng thời, việc compile cũng không tạo bảo đảm an toàn khi nhiều luồng cùng gọi một XPathExpression.

## 12. Chọn kiểu theo hợp đồng của hàm ứng dụng

| Hàm ứng dụng cần gì? | Kiểu nhận nên xét |
| --- | --- |
| Kiểm tra một phần tử có tồn tại | BOOLEAN của biểu thức chọn nút |
| Đọc giá trị văn bản đã xác định duy nhất | STRING, hoặc NODE nếu cần kiểm tra sự hiện diện |
| Kiểm tra đúng một nút rồi xử lý cấu trúc | NODESET để kiểm tra số lượng, sau đó lấy Node |
| Duyệt mọi phần tử phù hợp | NODESET |
| Lấy một nút đã có quy tắc lựa chọn rõ | NODE |
| Tính count/sum theo ngữ nghĩa XPath | NUMBER, có kiểm tra miền giá trị cần thiết |
| Giữ số thập phân chính xác theo nghiệp vụ | Chuỗi/Node phù hợp rồi phân tích bằng công cụ Java tương ứng |

Đặt tên hàm theo ý nghĩa, chẳng hạn existsActiveElement khác với readActiveValue. Cùng dùng BOOLEAN nhưng hai hàm có thể đòi biểu thức khác nhau.

Nếu hàm hứa trả “một mã bắt buộc”, hãy kiểm tra thiếu, rỗng và nhiều kết quả theo hợp đồng, thay vì để STRING tự bỏ bớt thông tin. Kiểu nhận là một công cụ; ứng dụng vẫn chịu trách nhiệm xác thực dữ liệu.

## 13. Tự kiểm tra

1. NUMBER ánh xạ thành Integer hay Double?
2. STRING của một node-set nhiều phần tử có tự nối mọi giá trị không?
3. Một phần tử active có chữ false có làm BOOLEAN của đường dẫn chọn nó thành false không?
4. Vì sao chuỗi rỗng chưa đủ để phân biệt nút thiếu và phần tử rỗng?
5. NODE có chứng minh chỉ tồn tại đúng một kết quả không?
6. NaN có cần kiểm tra bằng phép bằng với Double.NaN không?
7. NODESET có phải java.util.List<Node> không?

Đáp án:

1. Double.
2. Không; cần NODESET nếu muốn duyệt mọi nút.
3. Không; đường dẫn tạo tập nút không rỗng.
4. Cả hai trường hợp có thể cùng chuyển thành String rỗng.
5. Không; phải kiểm tra số lượng nếu cần tính duy nhất.
6. Không; dùng isNaN.
7. Không; nó ánh xạ thành NodeList của DOM.

Hãy chọn kiểu để giữ đủ thông tin mà hợp đồng ứng dụng cần, rồi phân biệt rõ chuyển đổi XPath, ép kiểu Java và kiểm tra nghiệp vụ.

## Tài liệu đối chiếu

- [XPathConstants — Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.xml/javax/xml/xpath/XPathConstants.html): ánh xạ các hằng sang kiểu Java.
- [XPathExpression — Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.xml/javax/xml/xpath/XPathExpression.html): đánh giá và yêu cầu kiểu trả về.
- [XPath 1.0 — W3C](https://www.w3.org/TR/1999/REC-xpath-19991116/): quy tắc chuyển chuỗi, số và boolean được API chuẩn sử dụng.
