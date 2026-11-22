# Hàm xử lý chuỗi, số và điều kiện trong XPath

## 1. Hàm giúp biến đường dẫn thành một truy vấn có ý nghĩa

Đường dẫn XPath chọn nút, nhưng nhiều yêu cầu cần thêm xử lý:

- Bỏ khoảng trắng dư trong tên trước khi so khớp.
- Tìm tên có chứa một từ.
- Chuyển nội dung giá thành số để so sánh.
- Tính tổng, đếm hoặc kiểm tra sự tồn tại.
- Kết hợp nhiều điều kiện để chọn đúng phần tử.

Ví dụ:

```xpath
/catalog/item[
  contains(normalize-space(name), 'Java')
  and number(stock) > 0
  and @active = 'true'
]
```

Biểu thức đọc theo ý nghĩa:

> Chọn item có tên sau chuẩn hóa chứa Java, tồn kho lớn hơn 0 và thuộc tính active có nội dung true.

Các hàm trong bài thuộc tập hàm XPath 1.0 được API JAXP hiện hành hỗ trợ. Không giả định một hàm của XPath phiên bản khác tự có sẵn chỉ vì chương trình dùng JDK mới. Xem [mức hỗ trợ của javax.xml.xpath](https://docs.oracle.com/en/java/javase/21/docs/api/java.xml/javax/xml/xpath/package-summary.html).

## 2. Mỗi hàm làm việc với một kiểu giá trị

XPath 1.0 có các nhóm giá trị cơ bản liên quan trực tiếp:

- Tập nút.
- Chuỗi.
- Số.
- Boolean.

Một đối số như `name` thường là tập nút được chọn từ ngữ cảnh. Khi một hàm cần chuỗi hoặc số, XPath có thể chuyển kiểu theo quy tắc của ngôn ngữ.

Điều này tiện lợi nhưng dễ che nhầm lẫn:

```xpath
contains(name, 'Java')
```

không có nghĩa “chạy contains trên từng name rồi trả một danh sách boolean”. Trong XPath 1.0, chuyển tập nút thành chuỗi dùng giá trị chuỗi của nút đầu theo thứ tự tài liệu.

Nếu ngữ cảnh là từng item và mỗi item có một name, cách viết đó phù hợp. Nếu một item có nhiều name, cần xác định rõ điều kiện muốn kiểm tra trên những nút nào.

Vì vậy luôn đọc biểu thức theo chuỗi: **đường dẫn chọn gì → hàm cần kiểu nào → chuyển kiểu nào xảy ra → kết quả được dùng làm gì**.

## 3. Nhóm hàm chuỗi thường dùng

| Hàm | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `string(value)` | Chuyển giá trị thành chuỗi | `string(@id)` |
| `normalize-space(s)` | Bỏ khoảng trắng đầu/cuối và gộp các dãy khoảng trắng XML | `normalize-space(name)` |
| `contains(s, part)` | Kiểm tra có chứa chuỗi con | `contains(name, 'Java')` |
| `starts-with(s, prefix)` | Kiểm tra tiền tố | `starts-with(@id, 'book-')` |
| `concat(a, b, ...)` | Nối các chuỗi | `concat(@id, ':', name)` |
| `string-length(s)` | Độ dài chuỗi theo mô hình XPath | `string-length(normalize-space(name))` |
| `substring(s, start, length)` | Lấy một phần chuỗi | `substring('Java', 2, 2)` |
| `substring-before(s, separator)` | Phần trước lần xuất hiện đầu của chuỗi phân cách | `substring-before('a:b', ':')` |
| `substring-after(s, separator)` | Phần sau lần xuất hiện đầu của chuỗi phân cách | `substring-after('a:b', ':')` |
| `translate(s, from, to)` | Ánh xạ hoặc loại ký tự theo vị trí trong các chuỗi ánh xạ | `translate('ABC', 'ABC', 'abc')` |

Đây là các hàm ngôn ngữ XPath, không phải lời gọi phương thức String của Java. Tên và số đối số phải theo hợp đồng XPath.

### normalize-space không phải mọi dạng chuẩn hóa văn bản

Với:

```xml
<name>  Java   Basics </name>
```

```xpath
normalize-space(name)
```

tạo `Java Basics`.

Hàm xử lý các ký tự khoảng trắng XML tương ứng như dấu cách, tab và ký tự xuống dòng. Nó không tự đổi chữ hoa/thường, không bỏ dấu tiếng Việt và không có nghĩa mọi ký tự trông như khoảng trắng trong Unicode đều được xử lý giống nhau.

Nếu tên có phần tử con:

```xml
<name>Java <em>Core</em> Guide</name>
```

giá trị chuỗi của phần tử name bao gồm văn bản hậu duệ theo thứ tự. Dùng `normalize-space(name)` để xét toàn bộ giá trị đó khác với việc chỉ lấy một nút `text()` đầu tiên.

### contains có phân biệt hoa/thường

```xpath
contains('Java', 'Java')
```

là true, còn:

```xpath
contains('Java', 'java')
```

là false.

`translate` có thể hỗ trợ một bảng ánh xạ cố định, chẳng hạn A–Z sang a–z cho dữ liệu ASCII đã xác định. Nó không phải giải pháp đổi hoa/thường theo mọi ngôn ngữ hoặc chuẩn hóa Unicode tổng quát.

Không sao chép các hàm như `lower-case()`, `matches()` hoặc `ends-with()` của phiên bản XPath khác rồi mặc định JAXP XPath 1.0 hỗ trợ chúng. Khi yêu cầu vượt tập hàm đang dùng, xử lý phần đó ở Java hoặc chọn bộ máy XPath có hợp đồng phù hợp.

## 4. substring đánh số từ 1

```xpath
substring('Java', 2, 2)
```

cho kết quả:

```text
av
```

Ký tự đầu tiên của XPath có vị trí 1. Đây không phải chỉ số bắt đầu 0 như `String.substring` của Java.

Tham số thứ ba là độ dài theo mô hình hàm, không phải chỉ số kết thúc của Java. Vì vậy không chuyển máy móc cặp tham số của một phương thức Java sang XPath.

Các tham số vị trí của XPath còn có quy tắc số và làm tròn riêng. Với truy vấn nghiệp vụ thông thường, nên dùng các vị trí nguyên dương rõ ràng và kiểm tra các trường hợp biên.

Nếu chuỗi phân cách không xuất hiện, `substring-before` hoặc `substring-after` có thể tạo chuỗi rỗng. Chuỗi rỗng đó không tự nói dữ liệu đầu vào hợp lệ; nếu dấu phân cách là bắt buộc, cần kiểm tra điều kiện tồn tại.

## 5. Nhóm hàm số và phép toán

| Hàm/phép toán | Ý nghĩa |
| --- | --- |
| `number(value)` | Chuyển sang số theo quy tắc XPath |
| `sum(nodes)` | Cộng các giá trị số của các nút trong tập |
| `count(nodes)` | Đếm số nút |
| `floor(n)` | Số nguyên lớn nhất không vượt quá n |
| `ceiling(n)` | Số nguyên nhỏ nhất không nhỏ hơn n |
| `round(n)` | Làm tròn theo quy tắc XPath |
| `+`, `-`, `*` | Cộng, trừ, nhân |
| `div` | Chia |
| `mod` | Phần dư |

`div` và `mod` là toán tử, không phải tên hàm phải gọi bằng dấu ngoặc.

```xpath
number(price) * number(stock)
```

có thể tính giá trị dựa trên price và stock của item đang làm ngữ cảnh.

Đừng dùng dấu `/` thay cho phép chia: trong biểu thức đường dẫn, ký tự đó có vai trò khác.

### Không phải văn bản trông giống số nào cũng được chuyển thành số

Nội dung `10.5` phù hợp với ví dụ số thập phân. Một chuỗi như `"oops"`, `"$10"` hoặc dữ liệu theo quy ước hiển thị riêng không tự được phân tích như người đọc mong muốn.

Chuyển đổi không hợp lệ có thể cho **NaN** (Not a Number), không nhất thiết ném ngoại lệ parse Java.

NaN không bằng chính nó và các so sánh thứ tự với nó không hoạt động như một giá thông thường. Trong Java, có thể kiểm tra một kết quả Double bằng `Double.isNaN(...)` khi miền dữ liệu yêu cầu.

### sum không âm thầm bỏ mọi dữ liệu hỏng

Nếu một nút price trong tập chuyển thành NaN, kết quả sum có thể thành NaN. Không coi nó như 0 trừ khi ứng dụng đã có chính sách dữ liệu rõ ràng.

Với dữ liệu tài chính hoặc cần độ chính xác thập phân, mô hình số dấu phẩy động XPath 1.0 không thay thế mọi yêu cầu của `BigDecimal`. Có thể dùng XPath chọn nút rồi kiểm tra và tính bằng Java theo quy tắc miền.

## 6. round có quy tắc cần kiểm tra ở điểm giữa

Với XPath 1.0, khi hai số nguyên gần như nhau về khoảng cách, `round` chọn số gần dương vô cùng hơn:

```xpath
round(1.5)
```

cho 2, còn:

```xpath
round(-1.5)
```

cho -1.

Do đó không mô tả chung là “luôn làm tròn ra xa 0” hoặc áp dụng một quy tắc tài chính chưa được yêu cầu.

Các hàm cốt lõi và quy tắc chuyển kiểu được đặc tả trong [XPath 1.0 Core Function Library](https://www.w3.org/TR/1999/REC-xpath-19991116/#corelib). Đặc tả này xác định ngữ nghĩa mà API XPath 1.0 trong bài đang sử dụng.

## 7. Điều kiện: and, or và not

Một số cách kết hợp:

```xpath
/catalog/item[number(stock) > 0 and @active='true']
```

```xpath
/catalog/item[@kind='book' or @kind='course']
```

```xpath
/catalog/item[not(@disabled)]
```

- `and`: cả hai điều kiện đúng.
- `or`: ít nhất một điều kiện đúng.
- `not(value)`: phủ định sau chuyển giá trị sang boolean.

Dùng dấu ngoặc khi điều kiện dài để ý nghĩa rõ:

```xpath
/catalog/item[
  (@kind='book' or @kind='course')
  and number(stock) > 0
]
```

XPath dùng `=` để so sánh bằng, không phải `==` của Java. Các toán tử logic là `and` và `or`, không phải `&&` và `||`.

Dấu `|` dùng để hợp các tập nút, không phải toán tử boolean or thay thế.

Nếu biểu thức nằm trong một thuộc tính XML, còn cần quy tắc escape XML, chẳng hạn ký tự `<` trong thuộc tính. Nếu biểu thức là literal Java, lại cần escape theo Java. Không trộn các lớp cú pháp này.

## 8. Chuyển sang boolean có thể khác ý nghĩa nội dung

Quy tắc quan trọng:

| Giá trị | Chuyển thành boolean |
| --- | --- |
| Tập nút rỗng | false |
| Tập nút có ít nhất một nút | true |
| Chuỗi rỗng | false |
| Chuỗi khác rỗng, kể cả `"false"` hoặc `"0"` | true |
| Số 0 hoặc NaN | false |
| Số khác 0, không NaN | true |

Ví dụ:

```xpath
boolean('false')
```

là true vì chuỗi đó không rỗng. Đây không phải một hàm phân tích chuỗi cấu hình thành boolean.

Tương tự:

```xpath
/catalog/item[@active]
```

chọn những item **có thuộc tính active**, kể cả:

```xml
<item active="false"/>
```

Nếu cần kiểm tra nội dung:

```xpath
/catalog/item[@active='true']
```

mới biểu đạt phép so sánh văn bản cần dùng trong mô hình dữ liệu này.

Nếu dữ liệu cho phép nhiều cách viết boolean hoặc có quy tắc schema riêng, ứng dụng phải xác định cách kiểm tra tương ứng; không suy ra nó từ việc thuộc tính có tồn tại.

## 9. Predicate số không đồng nghĩa “lớn hơn 0”

Một predicate có kết quả số có quy tắc vị trí:

```xpath
/catalog/item[2]
```

chọn theo vị trí 2 trong tập tương ứng.

Do đó:

```xpath
/catalog/item[number(stock)]
```

không phải cách viết gọn an toàn cho “stock là số dương”. Kết quả number trong predicate được dùng theo quy tắc vị trí.

Hãy diễn đạt điều kiện boolean rõ:

```xpath
/catalog/item[number(stock) > 0]
```

Tương tự, `position()` và `last()` làm việc với tập nút/ngữ cảnh của bước lọc. Nếu yêu cầu là giá trị nghiệp vụ, hãy dùng phép so sánh nghiệp vụ thay vì để một số rơi vào vị trí predicate một cách vô tình.

## 10. So sánh tập nút không phải luôn giống so sánh hai biến đơn

Giả sử một phần tử có:

```xml
<tags>
  <tag>java</tag>
  <tag>xml</tag>
</tags>
```

Với ngữ cảnh tags:

```xpath
tag = 'java'
```

đúng vì có tag bằng java.

Nhưng:

```xpath
tag != 'java'
```

cũng có thể đúng vì có tag khác java, cụ thể là xml.

Vì vậy hai biểu thức trên không phải luôn là hai giá trị phủ định nhau khi bên trái là tập nút.

Nếu muốn nói “không có tag nào bằng java”, dùng:

```xpath
not(tag = 'java')
```

Nếu muốn nói “có tag và mọi tag đều bằng java”, cần diễn đạt cả sự tồn tại và việc không có tag khác:

```xpath
boolean(tag) and not(tag != 'java')
```

Đây là một lý do quan trọng để xác định kiểu giá trị của từng vế trước khi đọc điều kiện như mã Java thông thường.

## 11. Ví dụ đầy đủ: chuỗi, số và điều kiện trên cùng tài liệu

Tệp `XPathFunctionsDemo.java`, chạy trên JDK 17 trở lên, không cần thư viện ngoài:

```java
import java.io.StringReader;
import javax.xml.XMLConstants;
import javax.xml.parsers.DocumentBuilderFactory;
import javax.xml.xpath.XPath;
import javax.xml.xpath.XPathConstants;
import javax.xml.xpath.XPathFactory;
import org.w3c.dom.Document;
import org.w3c.dom.Element;
import org.w3c.dom.NodeList;
import org.xml.sax.InputSource;

public class XPathFunctionsDemo {
    public static void main(String[] args) throws Exception {
        String xml = """
                <catalog>
                  <item id="a" active="true">
                    <name>  Java   Basics </name>
                    <price>10.5</price><stock>2</stock>
                  </item>
                  <item id="b" active="false">
                    <name>XML Guide</name>
                    <price>20</price><stock>0</stock>
                  </item>
                  <item id="c">
                    <name>Java Tools</name>
                    <price>oops</price><stock>5</stock>
                  </item>
                </catalog>
                """;

        DocumentBuilderFactory parser =
                DocumentBuilderFactory.newDefaultInstance();
        parser.setFeature(XMLConstants.FEATURE_SECURE_PROCESSING, true);
        parser.setAttribute(XMLConstants.ACCESS_EXTERNAL_DTD, "");
        parser.setAttribute(XMLConstants.ACCESS_EXTERNAL_SCHEMA, "");
        parser.setNamespaceAware(true);
        Document document = parser.newDocumentBuilder().parse(
                new InputSource(new StringReader(xml)));
        XPath xpath = XPathFactory.newDefaultInstance().newXPath();

        System.out.println("normalized=" + xpath.evaluate(
                "normalize-space(/catalog/item[@id='a']/name)", document));
        System.out.println("substring=" + xpath.evaluate(
                "substring('Java', 2, 2)", document));
        System.out.println("joined=" + xpath.evaluate(
                "concat('book', '-', 'a')", document));
        System.out.println("sumValid=" + xpath.evaluate(
                "sum(/catalog/item[@id='a' or @id='b']/price)",
                document, XPathConstants.NUMBER));
        System.out.println("sumAll=" + xpath.evaluate(
                "sum(/catalog/item/price)", document, XPathConstants.NUMBER));
        System.out.println("nonEmptyFalseText=" + xpath.evaluate(
                "boolean('false')", document, XPathConstants.BOOLEAN));
        System.out.println("hasActiveAttribute=" + xpath.evaluate(
                "count(/catalog/item[@active])",
                document, XPathConstants.NUMBER));
        System.out.println("roundNegativeHalf=" + xpath.evaluate(
                "round(-1.5)", document, XPathConstants.NUMBER));

        NodeList selected = (NodeList) xpath.evaluate(
                "/catalog/item[contains(normalize-space(name), 'Java')"
                        + " and number(stock) > 0 and @active='true']",
                document, XPathConstants.NODESET);
        for (int i = 0; i < selected.getLength(); i++) {
            Element item = (Element) selected.item(i);
            System.out.println("selected=" + item.getAttribute("id"));
        }
    }
}
```

Biên dịch và chạy:

```shell
javac XPathFunctionsDemo.java
java XPathFunctionsDemo
```

Kết quả:

```text
normalized=Java Basics
substring=av
joined=book-a
sumValid=30.5
sumAll=NaN
nonEmptyFalseText=true
hasActiveAttribute=2.0
roundNegativeHalf=-1.0
selected=a
```

Giải thích:

- `normalize-space` gộp khoảng trắng của tên item a.
- `substring` bắt đầu từ vị trí 2 của Java nên lấy av.
- `concat` nối thành book-a.
- Hai price được chọn rõ là 10.5 và 20 nên tổng bằng 30.5.
- Tổng mọi price gặp giá trị oops nên thành NaN.
- Chuỗi false khác rỗng nên chuyển thành true.
- Có hai item có thuộc tính active, dù một thuộc tính chứa false.
- `round(-1.5)` cho -1 theo quy tắc điểm giữa.
- Chỉ item a thỏa đồng thời tên chứa Java, stock dương và active đúng văn bản true.

`sumValid` là tổng của một tập được chọn tường minh trong ví dụ, không phải lời khuyên bỏ mọi bản ghi hỏng ra khỏi tổng nghiệp vụ. Nếu mọi giá là bắt buộc hợp lệ, cần báo dữ liệu lỗi thay vì bỏ qua c.

Parser được cấu hình cho XML cố định không dùng tài nguyên ngoài. Nội dung bài tập trung vào hàm XPath; xử lý XML từ bên ngoài vẫn cần chính sách parser phù hợp.

## 12. Chọn kiểu kết quả Java theo biểu thức

Khi gọi API JAXP:

- `XPathConstants.STRING` trả String.
- `XPathConstants.NUMBER` trả Double.
- `XPathConstants.BOOLEAN` trả Boolean.
- `XPathConstants.NODESET` trả NodeList.

Xem [XPathConstants](https://docs.oracle.com/en/java/javase/21/docs/api/java.xml/javax/xml/xpath/XPathConstants.html).

Vì count trả số theo mô hình XPath nên ví dụ in `2.0`, không phải một Integer. Đó không có nghĩa tài liệu có “hai nút rưỡi”; chỉ là cách biểu diễn kiểu số trả về.

Nếu không truyền returnType, dạng evaluate thông thường trả String. Một lỗi thường gặp là thấy chữ `"false"` rồi dùng phép kiểm tra chuỗi khác rỗng ở Java và kết luận true. Nếu cần điều kiện, hãy yêu cầu kiểu BOOLEAN để nhận trực tiếp giá trị Boolean phù hợp.

API mới cũng có các dạng kết quả khác; dù dùng dạng nào, vẫn cần phân biệt kiểu giá trị XPath và kiểu Java yêu cầu. Xem [XPath.evaluate](https://docs.oracle.com/en/java/javase/21/docs/api/java.xml/javax/xml/xpath/XPath.html).

## 13. Kiểm tra dữ liệu và tách giá trị đầu vào

Nếu một từ tìm kiếm hoặc ngưỡng giá đến từ bên ngoài, truyền nó như biến XPath qua resolver thay vì nối vào cú pháp biểu thức.

Ví dụ cấu trúc truy vấn:

```xpath
/catalog/item[
  contains(normalize-space(name), $keyword)
  and number(price) >= $minPrice
]
```

Các biến cung cấp giá trị; chúng không tự là một mảnh đường dẫn hoặc một biểu thức được thực thi lại.

Cũng cần xác định:

- keyword rỗng có được phép không? `contains(s, '')` là true.
- price vắng mặt có là lỗi không?
- Giá trị không phải số có được báo thay vì chỉ làm điều kiện false không?
- Nhiều name hoặc price dưới cùng item có hợp lệ không?
- Dữ liệu có namespace cần cấu hình cho đường dẫn không?

Một hàm trả false có thể do điều kiện không đạt, dữ liệu thiếu hoặc chuyển số thành NaN. Nếu nghiệp vụ cần phân biệt, đừng ép tất cả thành một kết quả “không chọn”.

## 14. Bài tập tự kiểm tra

1. Đổi name của a thành nhiều dòng có khoảng trắng XML: `normalize-space` vẫn đưa về dạng gọn phù hợp.
2. Đổi từ Java trong contains thành java: vì sao a không còn khớp? So sánh chuỗi ở đây có phân biệt hoa/thường.
3. Đổi price của c từ oops thành 5: tổng toàn bộ price trở thành 35.5.
4. So sánh số item của `[@active]` và `[@active='true']`: một biểu thức kiểm tra có thuộc tính, biểu thức kia kiểm tra giá trị.
5. Thử `[number(stock)]` và `[number(stock) > 0]`: chúng không có cùng ý nghĩa vì predicate số liên quan vị trí.
6. Với hai tag java và xml, kiểm tra `tag='java'`, `tag!='java'` và `not(tag='java')`.

Khi biểu thức cho kết quả bất ngờ, hãy kiểm tra **kiểu đầu vào của hàm, quy tắc chuyển kiểu, ngữ cảnh của predicate và điều kiện nghiệp vụ thật sự muốn diễn đạt**.
