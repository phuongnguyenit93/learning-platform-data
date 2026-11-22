# Điều kiện lọc và vị trí phần tử trong biểu thức XPath

## 1. Predicate thu hẹp tập nút, không chỉ tìm chuỗi

Một đường dẫn XPath có thể chọn nhiều phần tử. **Điều kiện lọc (predicate)** đặt trong dấu ngoặc vuông giúp giữ lại những nút thỏa mãn yêu cầu:

```xpath
/catalog/shelf/book[@active='true']
```

Đường dẫn chọn các book là con trực tiếp của shelf trong catalog; predicate giữ những book có thuộc tính active bằng chuỗi true.

Cần phân biệt:

- Đường dẫn xác định tập nút ứng viên và ngữ cảnh duyệt.
- Predicate quyết định nút nào được giữ.
- Predicate vị trí phụ thuộc vào tập ứng viên tại đúng bước đó, không mặc định là số thứ tự toàn tài liệu.

Bài sử dụng **XPath 1.0**, phiên bản được API chuẩn `javax.xml.xpath` của Java hiện đại hỗ trợ. Việc Java 5 đã có API này không làm các quy tắc predicate trở thành kiến thức lỗi thời. Không mặc định các hàm hay cú pháp XPath 2.0/3.x dùng được trên provider chuẩn mà chưa kiểm tra.

Các ví dụ Java chạy với Java 17+. Nguồn API: [javax.xml.xpath](https://docs.oracle.com/en/java/javase/21/docs/api/java.xml/javax/xml/xpath/package-summary.html).

## 2. Dữ liệu dùng xuyên suốt bài

```xml
<catalog>
  <shelf id="A">
    <book id="b1" active="false"><price>50</price></book>
    <book id="b2" active="true"><price>120</price></book>
    <book id="b3" active="true"><price>80</price></book>
  </shelf>
  <shelf id="B">
    <book id="b4" active="true"><price>60</price></book>
    <book id="b5" active="false"><price>150</price></book>
  </shelf>
</catalog>
```

Thứ tự tài liệu của các book là b1, b2, b3, b4, b5. Nhưng dưới shelf A có ba book, còn dưới shelf B có hai book. Chính hai nhóm con này làm các biểu thức vị trí có thể khác nhau.

XML trong bài không có namespace để tập trung vào predicate. Nếu tài liệu thật có namespace, biểu thức còn phải dùng tên đã được giải quyết namespace đúng cách.

## 3. Ngữ cảnh của một lần đánh giá predicate

Khi kiểm tra một nút ứng viên, XPath có các thành phần ngữ cảnh quan trọng:

| Thành phần | Ý nghĩa |
| --- | --- |
| Nút ngữ cảnh | Nút hiện đang được kiểm tra |
| Vị trí ngữ cảnh | Vị trí của nút trong tập ứng viên ở bước đó |
| Kích thước ngữ cảnh | Số nút của tập ứng viên đang được lọc |

Trong predicate của book:

- `@active` nói tới thuộc tính của book hiện tại.
- `price` nói tới phần tử price con của book hiện tại.
- `position()` trả vị trí ngữ cảnh.
- `last()` trả kích thước ngữ cảnh, không phải chỉ số cuối của một mảng Java.

Ví dụ:

```xpath
/catalog/shelf/book[price >= 100]
```

Tại từng book, XPath đọc price tương ứng và so sánh số theo quy tắc XPath 1.0. Kết quả trên dữ liệu mẫu là b2, b5.

Trong XPath, vị trí bắt đầu từ **1**. Nếu Java trả một NodeList, `item(0)` lại là phần tử đầu theo API NodeList. Đây là hai quy ước khác nhau.

## 4. Các loại điều kiện thường dùng

### Thuộc tính bằng giá trị

```xpath
//book[@active='true']
```

Kết quả: b2, b3, b4.

Thuộc tính XML ở đây là chuỗi. Tên active không tự làm nó thành boolean theo ngữ nghĩa Java.

### Thuộc tính có tồn tại

```xpath
//book[@active]
```

Kết quả: cả b1 đến b5, vì tất cả đều có thuộc tính active, kể cả những thuộc tính có giá trị false.

`[@active]` không có nghĩa giá trị thuộc tính phải là true. Trong điều kiện boolean XPath 1.0, node-set chứa thuộc tính là true vì nó không rỗng.

Tương tự, `[price]` kiểm tra có price con, không kiểm tra giá lớn hơn 0.

### Điều kiện số

```xpath
//book[price >= 100]
```

Kết quả: b2, b5.

Khi so sánh với số, XPath 1.0 áp dụng quy tắc chuyển đổi số cho các giá trị liên quan. Một price không chuyển thành số hợp lệ có thể dẫn tới NaN và không thỏa phép so sánh thứ tự; XPath không tự báo lỗi xác thực miền giá ở mọi trường hợp.

Nếu dữ liệu bắt buộc phải có đúng một price là số hợp lệ, đó còn là yêu cầu chất lượng/schema của XML, không chỉ là việc thêm một predicate.

### Kết hợp and, or và not

```xpath
//book[@active='true' and price >= 100]
```

Kết quả: b2.

```xpath
//book[@id='b1' or @id='b5']
```

Kết quả: b1, b5.

```xpath
//book[not(@active='true')]
```

Trên dữ liệu mẫu, kết quả là b1, b5. Nếu có book không mang thuộc tính active, biểu thức not đó cũng cần được hiểu theo quy tắc boolean; không mặc định nó giống một bộ kiểm tra schema “active bắt buộc là false”.

Khi điều kiện gồm nhiều phần, thêm ngoặc để thể hiện ý định rõ thay vì để người đọc phải nhớ mọi mức ưu tiên toán tử.

## 5. Predicate số là phép chọn vị trí

Trong predicate XPath 1.0, nếu kết quả biểu thức là một số, nút được giữ khi vị trí ngữ cảnh bằng số ấy.

Vì vậy:

```xpath
book[2]
```

tương đương về ý định chọn vị trí với:

```xpath
book[position() = 2]
```

Nó chọn book thứ hai trong tập tại bước đó; không có nghĩa “book có nội dung bằng 2”.

Một số đối chiếu:

| Predicate | Ý nghĩa |
| --- | --- |
| [1] | Vị trí đầu |
| [last()] | Vị trí cuối trong ngữ cảnh |
| [position() <= 2] | Hai vị trí đầu nếu có |
| [position() mod 2 = 1] | Các vị trí lẻ |
| [0] | Không có nút có vị trí 0 |

Một giá trị số khác 0 không được tự hiểu như boolean true khi nó là kết quả trực tiếp của predicate số. Chẳng hạn [2] không giữ tất cả nút chỉ vì số 2 khác 0.

Nếu dùng biến động trong predicate, kiểu giá trị của biến cũng quan trọng. Một số 2 và một chuỗi không rỗng "2" không có cùng quy tắc khi làm toàn bộ kết quả predicate. Với chỉ số do chương trình cung cấp, viết điều kiện vị trí tường minh và kiểm tra miền giá trị sẽ dễ hiểu hơn.

## 6. //book[1] khác với (//book)[1]

### Chọn book đầu dưới từng cha liên quan

```xpath
//book[1]
```

Trên dữ liệu mẫu, kết quả là b1 và b4.

Ký hiệu // là dạng viết tắt của một đường dẫn qua các nút hậu duệ. Predicate [1] ở đây gắn với bước chọn book con theo ngữ cảnh của từng cha tương ứng. Nó không tự gom mọi book của tài liệu thành một danh sách duy nhất rồi lấy phần tử đầu.

### Chọn một book đầu từ kết quả đã gom

```xpath
(//book)[1]
```

Kết quả chỉ là b1.

Ngoặc tạo một biểu thức kết quả chung; predicate ở bên ngoài lọc kết quả đó theo thứ tự phù hợp của biểu thức lọc. Đây là cách diễn đạt “book đầu tiên trong toàn bộ kết quả //book” của ví dụ.

Tương tự:

| Biểu thức | Kết quả |
| --- | --- |
| //book[last()] | b3, b5 |
| (//book)[last()] | b5 |
| //book[position() <= 2] | b1, b2, b4, b5 |
| (//book)[position() <= 2] | b1, b2 |

Không thêm hoặc bỏ ngoặc chỉ để “nhìn gọn hơn”. Chúng có thể làm đổi tập ngữ cảnh dùng cho vị trí.

Các quy tắc predicate và dạng viết tắt được quy định trong [XPath 1.0](https://www.w3.org/TR/1999/REC-xpath-19991116/).

## 7. Thứ tự nhiều predicate có thể đổi kết quả

Hai biểu thức sau không tương đương:

```xpath
//book[@active='true'][1]
```

```xpath
//book[1][@active='true']
```

### Lọc active trước, rồi chọn vị trí đầu

`//book[@active='true'][1]` cho b2 và b4:

- Shelf A có các book active là b2, b3; vị trí đầu sau lọc là b2.
- Shelf B có book active là b4; vị trí đầu là b4.

### Chọn vị trí đầu trước, rồi kiểm tra active

`//book[1][@active='true']` chỉ cho b4:

- Book đầu của shelf A là b1, nhưng active=false nên bị loại.
- Book đầu của shelf B là b4 và active=true nên được giữ.

Mỗi predicate phía sau nhận tập đã được predicate phía trước thu hẹp. Vị trí và kích thước ngữ cảnh được xác định theo giai đoạn lọc tương ứng.

Nếu ý định là **một** book active đầu tiên của toàn bộ tài liệu:

```xpath
(//book[@active='true'])[1]
```

Kết quả là b2.

Hai điều kiện chỉ kiểm tra thuộc tính của từng nút thường có thể kết hợp bằng and để rõ ý. Nhưng khi có position/last hoặc phụ thuộc thứ tự, không biến đổi tùy ý chuỗi predicate thành một biểu thức mà chưa kiểm tra ngữ nghĩa.

## 8. Trục ngược: [1] có thể là nút gần nhất

Predicate vị trí trên một bước trục phụ thuộc thứ tự của trục đó.

Với book b3:

```xpath
//book[@id='b3']/preceding-sibling::book[1]
```

Kết quả là b2: book anh em đứng trước **gần nhất**. preceding-sibling là trục ngược, nên vị trí 1 của bước đó không phải book sớm nhất theo thứ tự tài liệu.

Thêm ngoặc:

```xpath
(//book[@id='b3']/preceding-sibling::book)[1]
```

Kết quả là b1: predicate bên ngoài lọc tập kết quả của biểu thức, chọn nút đầu theo ngữ cảnh lọc tương ứng.

Đây là một lý do khác không nên đọc [1] đơn giản thành “đầu file” ở mọi nơi.

Khi dùng ancestor, preceding hoặc preceding-sibling, hãy hỏi rõ ý định là “gần nút hiện tại nhất” hay “sớm nhất theo tài liệu”. Chọn vị trí predicate và ngoặc theo ý định đó.

## 9. So sánh node-set trong XPath 1.0 cần đọc kỹ

Một book có thể có nhiều phần tử con cùng tên. Trong XPath 1.0, so sánh node-set với một giá trị có thể mang nghĩa tồn tại một nút có giá trị thỏa điều kiện.

Ví dụ một book có hai tag, java và xml:

```xpath
book[tag='java' and tag='xml']
```

có thể giữ book ấy, vì mỗi phần điều kiện có thể được thỏa bởi một tag khác nhau. Nó không yêu cầu một tag duy nhất đồng thời có cả hai chuỗi giá trị.

Tương tự, `tag != 'java'` không luôn là phần bù của `tag = 'java'` khi có nhiều tag. Một tag có thể bằng java và tag khác không bằng java, khiến hai biểu thức so sánh đều true.

Nếu muốn “không có tag nào bằng java”, diễn đạt:

```xpath
book[not(tag='java')]
```

Không chuyển trực giác so sánh một biến String Java sang mọi phép so sánh node-set của XPath.

Với dữ liệu nhiều nút con, hãy xác định rõ điều kiện là tồn tại, không tồn tại hay yêu cầu cấu trúc nào khác, rồi chọn biểu thức theo quy tắc phiên bản XPath đang sử dụng.

## 10. Chương trình Java kiểm chứng các nhóm vị trí

Lưu thành `XPathPredicateDemo.java`:

```java
import java.io.StringReader;
import java.util.StringJoiner;
import javax.xml.XMLConstants;
import javax.xml.parsers.DocumentBuilderFactory;
import javax.xml.xpath.XPath;
import javax.xml.xpath.XPathConstants;
import javax.xml.xpath.XPathFactory;
import org.w3c.dom.Document;
import org.w3c.dom.NodeList;
import org.xml.sax.InputSource;

public class XPathPredicateDemo {
    private static final String XML = """
            <catalog>
              <shelf id="A">
                <book id="b1" active="false"><price>50</price></book>
                <book id="b2" active="true"><price>120</price></book>
                <book id="b3" active="true"><price>80</price></book>
              </shelf>
              <shelf id="B">
                <book id="b4" active="true"><price>60</price></book>
                <book id="b5" active="false"><price>150</price></book>
              </shelf>
            </catalog>
            """;

    private static void show(
            XPath xpath, Document document, String expression)
            throws Exception {
        NodeList nodes = (NodeList) xpath.evaluate(
                expression, document, XPathConstants.NODESET);

        StringJoiner ids = new StringJoiner(", ", "[", "]");
        for (int i = 0; i < nodes.getLength(); i++) {
            ids.add(nodes.item(i).getAttributes()
                    .getNamedItem("id").getNodeValue());
        }

        System.out.println(expression + " -> " + ids);
    }

    public static void main(String[] args) throws Exception {
        DocumentBuilderFactory factory =
                DocumentBuilderFactory.newInstance();
        factory.setNamespaceAware(true);
        factory.setFeature(
                XMLConstants.FEATURE_SECURE_PROCESSING, true);
        factory.setAttribute(XMLConstants.ACCESS_EXTERNAL_DTD, "");
        factory.setAttribute(XMLConstants.ACCESS_EXTERNAL_SCHEMA, "");

        Document document = factory.newDocumentBuilder().parse(
                new InputSource(new StringReader(XML)));
        XPath xpath = XPathFactory.newInstance().newXPath();

        String[] expressions = {
                "//book[@active]",
                "//book[@active='true']",
                "//book[price >= 100]",
                "//book[@active='true' and price >= 100]",
                "//book[1]",
                "(//book)[1]",
                "//book[last()]",
                "(//book)[last()]",
                "//book[position() <= 2]",
                "(//book)[position() <= 2]",
                "//book[@active='true'][1]",
                "//book[1][@active='true']",
                "(//book[@active='true'])[1]",
                "//book[@id='b3']/preceding-sibling::book[1]",
                "(//book[@id='b3']/preceding-sibling::book)[1]"
        };

        for (String expression : expressions) {
            show(xpath, document, expression);
        }
    }
}
```

Chạy:

```shell
javac XPathPredicateDemo.java
java XPathPredicateDemo
```

Stdout:

```text
//book[@active] -> [b1, b2, b3, b4, b5]
//book[@active='true'] -> [b2, b3, b4]
//book[price >= 100] -> [b2, b5]
//book[@active='true' and price >= 100] -> [b2]
//book[1] -> [b1, b4]
(//book)[1] -> [b1]
//book[last()] -> [b3, b5]
(//book)[last()] -> [b5]
//book[position() <= 2] -> [b1, b2, b4, b5]
(//book)[position() <= 2] -> [b1, b2]
//book[@active='true'][1] -> [b2, b4]
//book[1][@active='true'] -> [b4]
(//book[@active='true'])[1] -> [b2]
//book[@id='b3']/preceding-sibling::book[1] -> [b2]
(//book[@id='b3']/preceding-sibling::book)[1] -> [b1]
```

Dữ liệu nằm hoàn toàn trong chương trình; không cần tải XML hoặc DTD ngoài. Phần cấu hình parser giới hạn truy cập tài nguyên ngoài cho thí nghiệm. Với XML đầu vào thực tế, cấu hình phân tích và giới hạn tài nguyên phải được thiết kế theo nguồn dữ liệu, không chỉ theo các biểu thức XPath.

Helper show giả định mọi nút được chọn đều là book có thuộc tính id, đúng với mảng biểu thức của ví dụ. Nó không phải hàm in mọi loại kết quả XPath.

## 11. Các điểm cần lưu ý khi đưa vào Java

### Chọn kiểu kết quả phù hợp

Muốn xem đầy đủ những book được chọn, ví dụ yêu cầu `XPathConstants.NODESET` và duyệt NodeList. Nếu yêu cầu STRING hoặc NODE đơn lẻ, việc chỉ thấy một giá trị không chứng minh predicate chỉ chọn đúng một nút.

### Context đầu vào cũng thay đổi ý nghĩa

Đánh giá một đường dẫn tương đối trên Document khác với đánh giá nó trên một shelf cụ thể. Dấu / ở đầu chỉ ra đường dẫn tuyệt đối theo mô hình tài liệu, còn bước tương đối xuất phát từ nút ngữ cảnh được truyền.

Đừng nhìn một biểu thức tách khỏi đối tượng context và mặc định kết quả giống nhau ở mọi nơi.

### Namespace không tự biến mất khi thêm predicate

Nếu XML có namespace mặc định, tên book không có prefix trong XPath 1.0 không tự nhận namespace mặc định của tài liệu. Cần cấu hình NamespaceContext và dùng prefix phù hợp.

Việc [1] hoặc [@active='true'] không trả gì đôi khi bắt đầu từ bước chọn tên nút không khớp namespace, không phải predicate vị trí sai.

### Dữ liệu động không nên ghép thành cú pháp

Với điều kiện so sánh giá trị do bên ngoài cung cấp, cân nhắc biến XPath qua XPathVariableResolver thay vì ghép thẳng dữ liệu vào dấu nháy của biểu thức. Nguồn biến và kiểu của nó cần rõ ràng trong một lần đánh giá.

[XPath](https://docs.oracle.com/en/java/javase/21/docs/api/java.xml/javax/xml/xpath/XPath.html) mô tả context, resolver, kiểu kết quả và các giới hạn sử dụng đối tượng XPath. Không chia sẻ tùy ý một XPath đang evaluate giữa nhiều luồng.

## 12. Quy trình đọc một predicate vị trí

1. Xác định nút context đầu vào.
2. Xác định bước đường dẫn và trục đang dùng.
3. Xác định tập ứng viên tại bước đó.
4. Áp dụng từng predicate theo đúng thứ tự.
5. Với predicate số/position/last, xác định lại vị trí và kích thước ngữ cảnh.
6. Kiểm tra ngoặc có tạo một kết quả chung để lọc bên ngoài không.
7. Đối chiếu các nút kết quả bằng dữ liệu nhỏ có nhiều cha/nhóm.

Dữ liệu chỉ có một shelf hoặc một book thường che sự khác nhau giữa //book[1] và (//book)[1]. Muốn kiểm chứng vị trí, cần mẫu có đủ cấu trúc để bộc lộ phạm vi lọc.

## 13. Tự kiểm tra

**XPath [1] dùng chỉ số như NodeList.item(1) không?**  
Không. Vị trí XPath bắt đầu từ 1; item của NodeList bắt đầu từ 0.

**[@active] có loại thuộc tính active="false" không?**  
Không. Nó kiểm tra tồn tại nút thuộc tính.

**//book[1] có luôn trả đúng một book không?**  
Không. Nó có thể trả book đầu dưới nhiều cha liên quan.

**Lọc active rồi lấy [1] có giống lấy [1] rồi lọc active không?**  
Không khi vị trí được tính trên các tập ứng viên khác nhau.

**preceding-sibling::book[1] là book đứng trước xa nhất không?**  
Không. Với trục ngược này, nó chọn book đứng trước gần nhất.

Điểm quyết định của predicate là ngữ cảnh: cùng một điều kiện vị trí có thể cho kết quả khác khi thay đổi bước đường dẫn, trục, ngoặc hoặc thứ tự lọc.
