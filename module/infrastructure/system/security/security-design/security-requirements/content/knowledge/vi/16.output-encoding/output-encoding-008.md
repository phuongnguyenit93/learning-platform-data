# XML encoding

## 1. Mục tiêu của yêu cầu bảo mật

XML xuất hiện trong báo cáo, thông điệp tích hợp, cấu hình trao đổi và nhiều giao thức giữa các hệ thống. Một trường ghi chú có thể đi từ biểu mẫu, qua cơ sở dữ liệu rồi xuất thành XML cho đối tác. Nếu quá trình xuất biến nội dung trường đó thành thẻ hoặc thuộc tính mới, người nhập dữ liệu có thể tác động đến cấu trúc thông điệp mà hệ thống nhận xử lý.

Trong chương Output encoding, **XML encoding** được hiểu là biểu diễn dữ liệu an toàn tại vị trí dữ liệu của tài liệu XML. Cần phân biệt hai lớp:

- **Escaping theo cú pháp XML:** giữ ký tự trong vai trò dữ liệu khi tạo nội dung phần tử hoặc giá trị thuộc tính.
- **Character encoding:** chuyển ký tự thành byte, chẳng hạn UTF-8, để gửi hoặc lưu tài liệu.

Chọn UTF-8 không tự ngăn XML injection. Ngược lại, escaping đúng nhưng khai báo encoding khác byte thực tế vẫn có thể làm hỏng thông điệp.

Yêu cầu bảo mật cần diễn đạt được kết quả quan sát, thay vì chỉ ghi “phải escape XML”:

> Khi xuất trường văn bản do người dùng hoặc hệ thống ngoài cung cấp, dịch vụ phải tạo XML theo cấu trúc cố định. Sau khi bên nhận phân tích tài liệu, trường đó vẫn là dữ liệu trong đúng vị trí được chỉ định; nó không được sinh thêm phần tử, thuộc tính hoặc chỉ thị xử lý.

Mục tiêu này nối trực tiếp một rủi ro trong mô hình đe dọa với thiết kế serializer và tiêu chí nghiệm thu. Bài học sử dụng tình huống xuất báo cáo để minh họa cách đặc tả yêu cầu; các giới hạn dung lượng và tên trường là lựa chọn của ví dụ, cần điều chỉnh theo hợp đồng tích hợp thực tế.

## 2. Từ dữ liệu không tin cậy đến XML injection

Giả sử hệ thống xuất báo cáo theo cấu trúc sau:

```xml
<exportReport customerDisplayName="Công ty An Bình">
  <note>Giao hồ sơ trước thứ sáu</note>
  <approvalStatus>PENDING</approvalStatus>
</exportReport>
```

Tên hiển thị và ghi chú là dữ liệu người dùng được phép nhập. Trạng thái phê duyệt thuộc quyền quyết định của dịch vụ. Một cách dựng chuỗi dễ gây lỗi là:

```java
// Minh họa cách làm không đáp ứng yêu cầu bảo toàn cấu trúc.
String xml = "<exportReport customerDisplayName=\"" + displayName + "\">"
        + "<note>" + note + "</note>"
        + "<approvalStatus>PENDING</approvalStatus>"
        + "</exportReport>";
```

Với ghi chú sau:

```text
</note><approvalStatus>APPROVED</approvalStatus><note>
```

phép nối chuỗi tạo ra:

```xml
<exportReport customerDisplayName="Công ty An Bình">
  <note></note>
  <approvalStatus>APPROVED</approvalStatus>
  <note></note>
  <approvalStatus>PENDING</approvalStatus>
</exportReport>
```

Tài liệu này vẫn có thể phân tích được về mặt cú pháp. Tuy nhiên, nó đã có thêm trường trạng thái. Hậu quả phụ thuộc vào bên nhận: từ chối, lấy giá trị đầu, lấy giá trị cuối hoặc xử lý cả hai. Vì vậy, “XML parse thành công” chưa chứng minh dữ liệu không tác động đến cấu trúc. Việc thử ký tự phân cách và chèn thẻ là những cách kiểm tra XML injection được mô tả trong [OWASP Web Security Testing Guide](https://wstg.owasp.org/v4.2/4-Web_Application_Security_Testing/07-Input_Validation_Testing/07-Testing_for_XML_Injection/).

Nếu tên hiển thị chứa dấu nháy rồi một thuộc tính mới, phép nối chuỗi còn có thể làm thay đổi tập thuộc tính của phần tử gốc. Vấn đề nằm tại ranh giới giữa dữ liệu và cú pháp, không phụ thuộc việc nguồn dữ liệu là request hiện tại hay bản ghi đã lưu từ nhiều tháng trước.

Yêu cầu cũng không được ngầm cho phép lấy trạng thái phê duyệt từ người dùng chỉ vì chuỗi đã được escape. Encoding bảo vệ cấu trúc thông điệp; kiểm soát quyền thay đổi trạng thái vẫn thuộc nghiệp vụ và phân quyền.

## 3. Phải xác định đúng ngữ cảnh đầu ra

### 3.1. Nội dung phần tử và giá trị thuộc tính

Hai vị trí dữ liệu thông dụng là:

```xml
<note>DỮ LIỆU VĂN BẢN</note>
<customer displayName="DỮ LIỆU THUỘC TÍNH"/>
```

Một bảng đối chiếu giúp phân biệt ký tự nguồn và biểu diễn XML:

| Ký tự dữ liệu | Biểu diễn thường gặp | Ý nghĩa tại vị trí dữ liệu |
| --- | --- | --- |
| `&` | `&amp;` | Không mở một entity reference ngoài ý muốn |
| `<` | `&lt;` | Không mở thẻ mới |
| `>` | `&gt;` | Có thể được serializer escape; cần lưu ý chuỗi `]]>` trong character data |
| `"` | `&quot;` | Bảo vệ dấu phân cách của thuộc tính dùng nháy kép |
| `'` | `&apos;` | Bảo vệ dấu phân cách của thuộc tính dùng nháy đơn |

Không cần ép mọi serializer tạo đúng một cách viết entity. Điều cần nghiệm thu là giá trị nhận lại và cấu trúc tài liệu. Ví dụ, tên người dùng `An & Bình` có thể được xuất thành:

```xml
<customer displayName="An &amp; Bình"/>
```

Bên nhận phân tích thuộc tính thành `An & Bình`; chuỗi `&amp;` là biểu diễn trên đường truyền, không phải dữ liệu tên khách hàng cần lưu vào cơ sở dữ liệu.

Với Java StAX, `writeCharacters` chịu trách nhiệm escape nội dung văn bản, còn `writeAttribute` xử lý giá trị thuộc tính. API không bảo đảm tự kiểm tra mọi điều kiện well-formedness của đầu vào. Vì vậy, không suy từ việc dùng writer rằng mọi ký tự, tên thẻ hoặc thứ tự lời gọi đều đã hợp lệ. Xem hợp đồng của [XMLStreamWriter trong Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.xml/javax/xml/stream/XMLStreamWriter.html).

### 3.2. Tên và cấu trúc XML

Các vị trí sau không được coi là trường văn bản thông thường:

| Vị trí | Chính sách thiết kế trong ví dụ |
| --- | --- |
| Tên phần tử | Hằng số trong mã hoặc ánh xạ từ một tập lựa chọn đã phê duyệt |
| Tên thuộc tính | Hằng số; không nhận trực tiếp tên từ request |
| Namespace URI và prefix | Do hợp đồng tích hợp kiểm soát |
| DOCTYPE, khai báo entity | Không được tạo từ dữ liệu người dùng |
| Processing instruction | Không dùng để chứa ghi chú hoặc tên khách hàng |
| Comment | Không dùng làm nơi mang trường nghiệp vụ tùy ý |
| XML fragment được chèn nguyên dạng | Không chấp nhận qua API vốn chỉ cho phép văn bản |

Ví dụ, đổi một chuỗi tùy ý thành tên thẻ bằng `writeStartElement(userInput)` không phải là bảo vệ đầu ra theo ngữ cảnh text. Ngay cả khi tên được tạo hợp lệ về cú pháp, người dùng vẫn có thể chọn một tên làm thay đổi ý nghĩa nghiệp vụ. Nếu cần xuất các loại trường khác nhau, ứng dụng phải ánh xạ enum nội bộ sang tên cố định.

Một tên như `p:item` còn liên quan tới namespace binding. Không cho người dùng tùy ý lựa chọn prefix rồi coi việc escape giá trị là đủ. Khi namespace có ý nghĩa trong giao thức, tiêu chí nghiệm thu phải đối chiếu cả namespace URI và local name; chỉ nhìn chuỗi prefix không xác định đầy đủ danh tính phần tử.

## 4. Đặc tả yêu cầu có phạm vi và bằng chứng

Yêu cầu tốt nêu rõ nguồn dữ liệu, điểm xuất, hành vi bắt buộc và cách chứng minh. Bộ dưới đây dành cho chức năng xuất báo cáo của ví dụ, không phải bộ mã yêu cầu bắt buộc áp dụng nguyên dạng cho mọi dự án.

| Mã | Yêu cầu | Bằng chứng nghiệm thu dự kiến |
| --- | --- | --- |
| XML-OUT-01 | Mọi giá trị văn bản động trong chức năng xuất phải đi qua API tạo text hoặc attribute của serializer được chọn | Kiểm kê điểm xuất và kiểm thử từng trường động |
| XML-OUT-02 | Người dùng không được thay đổi tên phần tử, thuộc tính, namespace, DOCTYPE hoặc processing instruction | Kiểm thử dữ liệu có cú pháp XML và đối chiếu cây kết quả |
| XML-OUT-03 | Báo cáo phải có đúng cấu trúc đã đặc tả; trạng thái xuất phải lấy từ nguồn nghiệp vụ được phép | So sánh tập phần tử, số lần xuất hiện và giá trị trạng thái |
| XML-OUT-04 | Chuỗi chứa ký tự không hợp lệ cho profile XML 1.0 phải bị từ chối trước khi phát hành báo cáo | Ca kiểm thử ký tự cấm và xác nhận không có artifact thành công |
| XML-OUT-05 | Dữ liệu Unicode được chấp nhận phải được giữ theo chính sách chuẩn hóa đã công bố | Ca tiếng Việt, ký tự ngoài BMP và đối chiếu sau parse |
| XML-OUT-06 | Byte đầu ra, XML declaration và metadata truyền tải phải thống nhất UTF-8 | Đọc byte thực tế tại biên HTTP, message hoặc file |
| XML-OUT-07 | Giá trị được đưa vào serializer là dữ liệu nghiệp vụ, không phải chuỗi đã escape sẵn | Ca chứa `&`, entity dạng chữ và kiểm tra không decode thủ công |
| XML-OUT-08 | Lỗi validation hoặc serialization không được tạo báo cáo thành công một phần | Kiểm thử đường lỗi, trạng thái tác vụ và khả năng tải artifact |
| XML-OUT-09 | Phải áp dụng giới hạn đầu vào và đầu ra đã thống nhất với bên nhận | Ca tại biên độ dài và kích thước byte |

Nên gắn mỗi yêu cầu với chủ sở hữu. Nhóm nghiệp vụ quyết định trường nào được xuất; nhóm phát triển sở hữu serializer; nhóm tích hợp thống nhất profile XML và charset; nhóm kiểm thử thực hiện ca nghiệm thu. Nếu mọi trách nhiệm chỉ được ghi chung là “đội bảo mật”, yêu cầu dễ thiếu người thực hiện.

Ví dụ diễn đạt chưa đủ rõ:

> Hệ thống phải chống XML injection bằng thư viện an toàn.

Diễn đạt cụ thể hơn:

> Với mọi báo cáo xuất qua chức năng Export Report v1, trường `note` phải được ghi vào một text node của phần tử `note` bằng serializer đã chọn. Dữ liệu chứa thẻ đóng, khai báo entity hoặc chuỗi kết thúc CDATA phải không tạo thêm phần tử hay thuộc tính. Dữ liệu bị cấm theo profile XML 1.0 phải gây lỗi trước khi có artifact tải xuống.

Để tránh tuyên bố phạm vi quá rộng, danh mục điểm xuất phải bao gồm cả xuất trực tiếp, tác vụ nền, xuất lại báo cáo cũ và nhánh định dạng dành cho từng đối tác. Một endpoint được bảo vệ không đủ để kết luận toàn bộ module đã đáp ứng yêu cầu.

## 5. Dữ liệu gốc, escaping và ranh giới xử lý

### 5.1. Một ranh giới tuần tự hóa có trách nhiệm rõ ràng

Luồng thiết kế có thể được mô tả như sau:

```text
Request / dữ liệu đã lưu / phản hồi đối tác
                    |
                    v
      Validation nghiệp vụ + chính sách Unicode
                    |
                    v
      Mô hình dữ liệu được phép xuất
                    |
                    v
      XML serializer với cấu trúc cố định
                    |
                    v
      Byte UTF-8 + metadata truyền tải phù hợp
```

Validation xác định dữ liệu có được phép tham gia thao tác hay không. Serializer quyết định cách biểu diễn dữ liệu trong XML. Không chuyển trách nhiệm escaping cho cơ sở dữ liệu hoặc bộ lọc request chung, vì cùng một giá trị có thể còn xuất ra JSON, HTML hay CSV.

Ví dụ, dữ liệu nghiệp vụ là:

```text
A & B
```

Nếu một lớp đổi nó thành `A &amp; B`, rồi lớp xuất tiếp tục coi đó là dữ liệu thường, tài liệu có thể chứa:

```xml
<note>A &amp;amp; B</note>
```

Bên nhận đọc thành `A &amp; B`, khác dữ liệu ban đầu. Không sửa lỗi này bằng cách unescape toàn bộ XML sau khi serialize: thao tác đó có thể đưa các ký tự cấu trúc trở lại vị trí đang được bảo vệ.

### 5.2. Chuỗi trông giống entity vẫn có thể là dữ liệu hợp lệ

Người dùng có thể thực sự muốn ghi sáu ký tự `&lt;` trong tài liệu hướng dẫn. Với đầu vào đó, kết quả chứa `&amp;lt;` có thể hoàn toàn đúng: sau khi parse, trường văn bản phải vẫn là `&lt;`.

Vì vậy, không dùng quy tắc “thấy `&amp;lt;` là double encoding” cho mọi trường hợp. Cần đối chiếu với giá trị nguồn. Phân biệt hai sự kiện:

- Hệ thống đã thay đổi dữ liệu nghiệp vụ thành chuỗi escape trước khi tới serializer: thiết kế trách nhiệm có vấn đề.
- Dữ liệu nghiệp vụ vốn chứa các ký tự tạo thành tên entity: serializer phải giữ đúng dữ liệu đó.

Một yêu cầu có thể ghi: “Tại ranh giới xuất XML, serializer nhận dữ liệu chưa escape cho XML; bộ xử lý sau serializer không thực hiện unescape hoặc thay thế chuỗi để khôi phục markup.” Điều này rõ hơn việc yêu cầu một hàm escape có tính idempotent, vì escaping thông thường không có hợp đồng đó.

## 6. Ví dụ Java: dựng cấu trúc bằng StAX

Đoạn mã sau minh họa một serializer nhỏ cho Java 17 trở lên. Nó giữ tên cấu trúc cố định, kiểm tra ký tự đầu vào và chỉ trả byte sau khi tạo xong tài liệu trong bộ nhớ. Hai giới hạn theo code point là ví dụ hợp đồng của chức năng, không phải giới hạn của XML.

Trong profile minh họa, tên hiển thị không nhận tab hoặc ký tự xuống dòng. Ghi chú cho phép nhiều dòng nhưng chuẩn hóa CRLF/CR thành LF trước khi xuất. Chính sách này giúp việc đối chiếu sau parse không phụ thuộc cách mỗi bên xử lý xuống dòng của chuỗi nguồn.

```java
import java.io.ByteArrayOutputStream;
import java.nio.charset.StandardCharsets;
import java.util.Objects;
import javax.xml.stream.XMLOutputFactory;
import javax.xml.stream.XMLStreamException;
import javax.xml.stream.XMLStreamWriter;

public final class ReportXmlWriter {
    private ReportXmlWriter() {
    }

    public record ExportReport(String customerDisplayName, String note) {
    }

    public static byte[] serialize(ExportReport report)
            throws XMLStreamException {
        Objects.requireNonNull(report, "report");

        String displayName = requireXml10(
                report.customerDisplayName(), "customerDisplayName", 120);
        if (displayName.indexOf('\t') >= 0
                || displayName.indexOf('\n') >= 0
                || displayName.indexOf('\r') >= 0) {
            throw new IllegalArgumentException(
                    "customerDisplayName must be a single-line value");
        }

        // Kiểm tra đầu vào gốc trước khi chuẩn hóa theo hợp đồng.
        String rawNote = requireXml10(report.note(), "note", 2_000);
        String note = rawNote.replace("\r\n", "\n").replace('\r', '\n');

        ByteArrayOutputStream output = new ByteArrayOutputStream();
        XMLOutputFactory factory = XMLOutputFactory.newFactory();
        XMLStreamWriter writer = factory.createXMLStreamWriter(
                output, StandardCharsets.UTF_8.name());

        try {
            writer.writeStartDocument(StandardCharsets.UTF_8.name(), "1.0");
            writer.writeStartElement("exportReport");
            writer.writeAttribute("customerDisplayName", displayName);

            writer.writeStartElement("note");
            writer.writeCharacters(note);
            writer.writeEndElement();

            writer.writeStartElement("approvalStatus");
            writer.writeCharacters("PENDING");
            writer.writeEndElement();

            writer.writeEndElement();
            writer.writeEndDocument();
            writer.flush();
        } finally {
            writer.close();
        }

        return output.toByteArray();
    }

    private static String requireXml10(
            String value, String field, int maxCodePoints) {
        Objects.requireNonNull(value, field);

        // Mỗi code point cần ít nhất một UTF-16 code unit.
        // Chặn sớm chuỗi chắc chắn quá dài trước khi quét nội dung.
        if (value.length() > 2 * maxCodePoints) {
            throw new IllegalArgumentException(field + " is too long");
        }

        int count = 0;
        for (int offset = 0; offset < value.length();) {
            int cp = value.codePointAt(offset);
            if (!isXml10Character(cp)) {
                throw new IllegalArgumentException(
                        field + " contains a disallowed XML character");
            }
            if (++count > maxCodePoints) {
                throw new IllegalArgumentException(field + " is too long");
            }
            offset += Character.charCount(cp);
        }
        return value;
    }

    private static boolean isXml10Character(int cp) {
        return cp == 0x9 || cp == 0xA || cp == 0xD
                || (cp >= 0x20 && cp <= 0xD7FF)
                || (cp >= 0xE000 && cp <= 0xFFFD)
                || (cp >= 0x10000 && cp <= 0x10FFFF);
    }
}
```

Các nhánh tạo XML đều truyền dữ liệu vào `writeCharacters` hoặc `writeAttribute`, không vào API tạo tên thẻ hoặc khai báo DTD. Phần `approvalStatus` cố định chỉ để làm rõ ranh giới tin cậy của ví dụ; trong ứng dụng thực tế, nó phải lấy từ trạng thái nghiệp vụ có nguồn và quyền thay đổi rõ ràng.

Một số điểm cần đưa vào thiết kế khi sử dụng mẫu này:

- Nếu `null` có ý nghĩa khác chuỗi rỗng, hợp đồng phải quy định bỏ phần tử, dùng giá trị mặc định hay báo lỗi. Ví dụ hiện tại từ chối `null`.
- `isXml10Character` kiểm tra phạm vi ký tự XML 1.0; không kiểm tra tính hợp lệ nghiệp vụ của tên khách hàng hay nội dung ghi chú.
- Surrogate đơn lẻ trong Java `String` không đi qua điều kiện kiểm tra. Một cặp surrogate hợp lệ đại diện cho ký tự ngoài BMP vẫn có thể được chấp nhận.
- Không trả hoặc ghi `output` ra response trước khi `serialize` kết thúc thành công.
- Lớp HTTP cần ánh xạ lỗi phù hợp, giới hạn request trước khi cấp phát chuỗi lớn và áp dụng giới hạn byte đầu ra. Giới hạn code point trong hàm không thay thế toàn bộ các giới hạn đó.

Các phạm vi ký tự trong hàm theo profile [XML 1.0, mục Characters](https://www.w3.org/TR/xml/#charsets). XML 1.1 có hợp đồng khác; không thay declaration thành `1.1` để né một ca lỗi mà chưa thống nhất với bên nhận.

Đây là ví dụ triển khai để đọc và đối chiếu yêu cầu. Khi tích hợp vào sản phẩm, cần kiểm chứng bằng provider XML và môi trường chạy thực tế, đặc biệt nếu dependency có thể thay đổi implementation của factory.

## 7. Ký tự cấm, CDATA và các vị trí dễ nhầm

### 7.1. Ký tự cấm không được cứu bằng numeric reference

Một lỗi thiết kế phổ biến là cho rằng mọi giá trị Unicode đều có thể chuyển thành `&#...;`. Với profile XML 1.0, NUL không hợp lệ; viết `&#0;` không biến nó thành dữ liệu được phép. Hợp đồng cần chọn hành vi rõ ràng: từ chối hoặc chuyển đổi có kiểm soát, thay vì để thư viện âm thầm loại ký tự.

Trong báo cáo nghiệp vụ, từ chối thường dễ kiểm toán hơn việc mất dữ liệu mà không thông báo. Nếu cần thay thế một ký tự vì yêu cầu tương thích, phải chỉ rõ ký tự thay thế, tác động đến đối chiếu và cách người dùng nhận biết. Không ghi chung “làm sạch dữ liệu” rồi để từng dịch vụ tự chọn.

### 7.2. CDATA không phải đường tắt bảo mật

CDATA có dấu kết thúc `]]>`. Bọc nguyên chuỗi người dùng bằng dấu mở và đóng CDATA sẽ hỏng khi dữ liệu chứa dấu kết thúc đó. Các quy tắc về CDATA được mô tả tại [W3C XML 1.0, CDATA Sections](https://www.w3.org/TR/xml/#sec-cdata-sect).

Ví dụ ghép chuỗi cần tránh:

```java
String xml = "<note><![CDATA[" + note + "]]></note>";
```

Nếu yêu cầu chỉ là vận chuyển văn bản, `writeCharacters(note)` đơn giản hơn. Nếu một giao thức thật sự yêu cầu CDATA, cần dùng implementation có hành vi đã kiểm chứng đối với `]]>` và kiểm tra giá trị sau parse. Không giả định mọi lệnh `writeCData` tự chia section hoặc từ chối nội dung giống nhau.

Không nên đặt yêu cầu rằng chuỗi `]]>` phải bị cấm trong mọi ghi chú. Đây có thể là nội dung hợp lệ của một tài liệu kỹ thuật; hệ thống cần giữ nó như text bằng cách tuần tự hóa phù hợp.

### 7.3. Comment và processing instruction

Ghi chú nghiệp vụ nên nằm trong phần tử dữ liệu, không trong comment hoặc processing instruction. Hai vị trí đó có cú pháp và ý nghĩa riêng; dùng hàm escape text cho chúng không tạo ra một hợp đồng an toàn tương đương.

Chẳng hạn, đẩy nội dung người dùng vào processing instruction khai báo stylesheet có thể liên quan đến việc lựa chọn tài nguyên được tải hoặc cách trình bày tài liệu. Chính sách của ví dụ loại bỏ nhu cầu đó: serializer không nhận các chỉ thị do người dùng cung cấp. Nếu sản phẩm có tính năng riêng cho stylesheet hoặc XML template, phải có mô hình đe dọa và yêu cầu riêng cho tính năng đó.

## 8. Tính toàn vẹn dữ liệu và character encoding

### 8.1. Hợp đồng Unicode phải đủ cụ thể

Với văn bản nhiều dòng, yêu cầu “giữ nguyên đầu vào” cần định nghĩa giữ nguyên ở lớp nào. Một chuỗi nguồn có CRLF có thể không giữ cùng biểu diễn sau vòng serialize/parse thông thường. Thuộc tính cũng không nên được chọn cho dữ liệu mà khoảng trắng chính xác có ý nghĩa nhưng hợp đồng chưa quy định cách bảo toàn.

Trong ví dụ Java:

- `customerDisplayName` là một dòng và không chứa tab.
- `note` nhận văn bản nhiều dòng, chuẩn hóa xuống dòng thành LF.
- Các ký tự còn lại được đối chiếu theo chuỗi Unicode sau chính sách trên.

Nếu hợp đồng cần bảo toàn chính xác một dãy byte, chẳng hạn tệp đính kèm, hãy đặc tả một trường nhị phân với encoding như Base64, giới hạn byte và cách giải mã tương ứng. Base64 ở đây là định dạng vận chuyển, không cấp quyền tin cậy cho nội dung sau giải mã và không thay thế mã hóa bảo mật.

Chữ tiếng Việt có thể được biểu diễn theo nhiều chuỗi code point. Không tự ý áp dụng NFC/NFD tại serializer nếu hợp đồng chưa cho phép; thay đổi chuẩn hóa có thể tác động đến đối chiếu, chữ ký hoặc định danh. Nếu có chuẩn hóa, phải thực hiện tại một vị trí được xác định và đưa nó vào expected value của kiểm thử.

### 8.2. Byte, declaration và metadata truyền tải

Ví dụ đầu ra HTTP có thể dùng:

```http
Content-Type: application/xml; charset=UTF-8
```

với byte được tạo bằng UTF-8 và declaration tương ứng:

```xml
<?xml version="1.0" encoding="UTF-8"?>
```

Đây là một hợp đồng nhất quán cho ví dụ. Với SOAP hoặc một định dạng chuyên biệt, media type phải theo giao thức tương ứng; không áp dụng cứng `application/xml` cho mọi thông điệp có XML bên trong.

Nếu dùng `StringWriter`, declaration chỉ là văn bản trong chuỗi, chưa quyết định cách chuỗi được chuyển thành byte sau đó. Vì vậy, cần xác minh điểm thực sự ghi ra stream hoặc gửi qua message broker. Một bước `getBytes()` không chỉ định charset, hoặc một lớp trung gian tái encode sai, có thể phá vỡ hợp đồng dù serializer ban đầu đúng.

Giới hạn dung lượng cũng phải ghi đơn vị rõ ràng. Hai nghìn code point không bằng hai nghìn byte UTF-8. Một biểu diễn chứa nhiều entity có thể dài hơn dữ liệu nguồn. Yêu cầu vận hành nên đặt cả giới hạn trường, tổng số bản ghi và tổng byte artifact thay vì dựa vào một con số “độ dài” không có đơn vị.

## 9. Những rủi ro XML encoding không tự giải quyết

### 9.1. XML injection và XXE là hai ranh giới khác nhau

Trong bài này, serializer ngăn dữ liệu văn bản trở thành cấu trúc do ứng dụng xuất ra. Khi hệ thống tiếp nhận một tài liệu XML hoàn chỉnh, parser còn có thể xử lý DTD, external entity hoặc tài nguyên bên ngoài. Đây là phạm vi khác.

Yêu cầu nhập XML phải kiểm soát DTD, external entity, external resource và giới hạn tài nguyên theo parser cụ thể. Không giả định chức năng xuất đã escape đúng thì mọi chức năng nhập cũng an toàn. [OWASP XML External Entity Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/XML_External_Entity_Prevention_Cheat_Sheet.html) hướng dẫn tắt DTD khi có thể, chặn truy cập ngoài và coi cấu hình bảo mật không được hỗ trợ là lỗi cấu hình.

Hàm kiểm thử dùng để đọc lại XML cũng cần cấu hình parser an toàn. Không tạo một lỗ hổng tại công cụ kiểm thử hoặc tác vụ kiểm tra artifact chỉ vì tài liệu được gọi là “do hệ thống sinh ra”.

### 9.2. XPath, schema và nghiệp vụ

XML escaping không phải XPath parameterization. Nếu một giá trị được lấy ra từ XML rồi nối vào biểu thức XPath, đó là một điểm sử dụng mới cần bảo vệ riêng. Tương tự, một URL nằm trong thuộc tính vẫn có thể trỏ tới đích không được phép dù thuộc tính đã được escape chính xác.

Schema validation có thể kiểm tra cấu trúc, số lượng và kiểu dữ liệu theo schema được chọn. Nó không tự chứng minh người xuất có quyền xem báo cáo, số tài khoản thuộc về ai hoặc trạng thái phê duyệt là hợp lệ. Schema của hợp đồng cũng không nên được tải tùy ý từ địa chỉ do người dùng cung cấp; cấu hình validation cần kiểm soát nguồn tài nguyên. Các rủi ro về schema và tài nguyên XML được trình bày trong [OWASP XML Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/XML_Security_Cheat_Sheet.html).

### 9.3. Tái sử dụng dữ liệu XML trong trình duyệt

Sau khi parser đọc một text node, giá trị như `<script>...</script>` lại là chuỗi văn bản bình thường. Nếu giao diện lấy chuỗi đó gán vào `innerHTML`, nó đi vào một ngữ cảnh mới. Escaping đã thực hiện trên đường truyền XML không bảo vệ lần sử dụng HTML này.

SVG và XHTML còn có thể mang ngữ nghĩa chủ động trong môi trường trình duyệt. Một tài liệu XML well-formed không đồng nghĩa một tài liệu phù hợp để nhúng hoặc thực thi. Với nội dung văn bản trên giao diện, chọn API hiển thị text và áp dụng bảo vệ theo ngữ cảnh đích. Nguyên tắc dùng safe sink và bảo vệ theo ngữ cảnh được giải thích trong [OWASP Cross Site Scripting Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross_Site_Scripting_Prevention_Cheat_Sheet.html).

### 9.4. Chữ ký và bảo mật đường truyền

Escaping không mã hóa bí mật và không xác thực người gửi. Nếu báo cáo chứa dữ liệu nhạy cảm, vẫn cần phân quyền, bảo vệ đường truyền, chính sách lưu artifact và thời hạn tải xuống.

Nếu dùng XML Signature, việc chọn chính xác phần được ký và phần được xử lý là một yêu cầu riêng. Không unescape, pretty-print hoặc chỉnh chuỗi sau bước ký rồi mặc định chữ ký vẫn có ý nghĩa như trước. Bộ yêu cầu về chữ ký cần nêu rõ phạm vi dữ liệu, quy trình xác minh và hành vi khi thất bại; nó không được thay bằng yêu cầu “escape XML”.

## 10. Thiết kế tiêu chí nghiệm thu

Các ca dưới đây mô tả kế hoạch nghiệm thu cho chức năng minh họa. Chúng không phải tuyên bố rằng một hệ thống thực tế đã được kiểm thử.

| Trường hợp | Dữ liệu đại diện | Kết quả cần quan sát |
| --- | --- | --- |
| Văn bản thông thường | `Công ty An Bình` | Giữ đúng giá trị sau parse |
| Ký tự cú pháp | `A & B < C > D` | Là dữ liệu của đúng một trường, không thêm node |
| Dấu nháy trong thuộc tính | `An "Bình" 'Minh'` | Không phát sinh thuộc tính mới |
| Chèn phần tử nghiệp vụ | `</note><approvalStatus>APPROVED</approvalStatus><note>` | Chỉ là text; có đúng một phần tử trạng thái do dịch vụ tạo |
| Chuỗi giống entity | `&lt;`, `&#65;`, `&unknown;` | Giữ đúng chuỗi người dùng đã nhập, không decode tùy ý |
| Chuỗi kết thúc CDATA | `trước ]]> sau` | Được vận chuyển như text hợp lệ |
| Unicode ngoài BMP | Một emoji hợp lệ | Không mất ký tự hoặc tách hỏng surrogate pair |
| Ký tự không được phép | NUL hoặc surrogate đơn lẻ | Từ chối trước khi có artifact thành công |
| Nhiều dòng | CRLF, CR và LF trong ghi chú | Kết quả theo chính sách chuẩn hóa LF |
| Độ dài biên | 120/121 code point cho tên; 2.000/2.001 cho ghi chú | Chấp nhận hoặc từ chối theo đúng giới hạn đã đặc tả |
| Lỗi trong đường xuất | Serializer hoặc nơi lưu artifact lỗi | Không có response/tác vụ thành công với tệp thiếu |
| Truyền qua kênh thực tế | Văn bản tiếng Việt và ký tự nhiều byte | Byte và metadata đúng UTF-8 sau mọi lớp trung gian |

### 10.1. Kiểm tra cấu trúc thay vì chỉ tìm chuỗi

Một ca kiểm tra không nên chỉ tìm `&lt;` trong kết quả. Cách đó có thể bỏ sót một đường xuất khác hoặc đánh trượt một cách tuần tự hóa hợp lệ bằng character reference.

Với ví dụ báo cáo, tiêu chí mạnh hơn là:

1. Parse byte kết quả bằng parser đã cấu hình an toàn.
2. Xác nhận đúng phần tử gốc và namespace của hợp đồng.
3. Xác nhận tập thuộc tính của gốc chỉ có các thuộc tính được phép.
4. Xác nhận đúng một `note`, đúng một `approvalStatus`, và không có phần tử ngoài hợp đồng.
5. Xác nhận `note` không có phần tử con do dữ liệu đầu vào tạo ra.
6. Đối chiếu giá trị text/attribute sau parse với dữ liệu sau chính sách Unicode và xuống dòng.
7. Xác nhận giá trị trạng thái xuất phát từ nguồn nghiệp vụ mong đợi.

Cần kiểm tra quan hệ cha–con và namespace, không chỉ đếm mọi thẻ trùng tên trên toàn tài liệu. Với profile có namespace, một phần tử cùng local name nhưng namespace khác không được coi là phần tử hợp lệ của hợp đồng.

### 10.2. Thuộc tính bất biến cho kiểm thử sinh dữ liệu

Có thể bổ sung kiểm thử sinh nhiều chuỗi Unicode trong phạm vi được phép. Một bất biến hữu ích là:

```text
parse(serialize(report)).note == normalizeLineEndings(report.note)
```

với điều kiện đầu vào thỏa giới hạn và profile ký tự. Đồng thời, số lượng và danh tính các phần tử/thuộc tính được phép phải giữ nguyên. Đối với tên hiển thị, expected value là chuỗi đã được chấp nhận theo chính sách một dòng.

Bất biến cần đi kèm kiểm thử âm cho đầu vào bị cấm; nếu bộ sinh chỉ tạo ký tự hợp lệ thì không thể chứng minh đường từ chối hoạt động. Kiểm thử vòng serialize/parse cũng không thay thế ca tích hợp với đối tác, vì bên nhận có thể áp dụng quy tắc riêng hoặc kỳ vọng khác về namespace, khoảng trắng và giới hạn.

### 10.3. Bằng chứng phục vụ truy vết yêu cầu

Với mỗi mã yêu cầu, lưu được tên ca kiểm thử, phiên bản serializer/provider, kết quả quan sát và phạm vi chức năng đã kiểm. Những thông tin này cho phép xác định việc nâng JDK hoặc đổi XML library có đòi hỏi chạy lại ca liên quan hay không.

Tỷ lệ “100% ca kiểm thử đã chạy thành công” chỉ có ý nghĩa đối với tập ca đã xác định. Nó không tự chứng minh mọi điểm xuất đều được bao phủ. Vì vậy, phải có danh mục điểm xuất để liên kết XML-OUT-01 với thực tế triển khai, tránh biến một tỷ lệ đẹp thành bằng chứng quá mức.

## 11. Lỗi, dung lượng và artifact xuất một phần

Gửi trực tiếp XML ra HTTP stream có ưu điểm ít tốn bộ nhớ, nhưng nếu lỗi xuất hiện sau khi response đã bắt đầu thì khó đổi sang một phản hồi lỗi nguyên vẹn. Yêu cầu an toàn cần lựa chọn theo kích thước tài liệu và cơ chế vận hành.

Với tài liệu nhỏ như ví dụ, tạo hoàn chỉnh trong bộ nhớ trước khi phát hành là một lựa chọn. Với tác vụ xuất lớn, có thể ghi vào artifact tạm có kiểm soát, chỉ chuyển trạng thái “sẵn sàng tải” khi serialization và lưu trữ hoàn tất. Không để người dùng tải tệp đang ghi rồi mặc định đó là báo cáo thành công.

Một hợp đồng lỗi nên trả lời rõ:

- Ai nhận được lỗi và mã lỗi nào phân biệt dữ liệu không hợp lệ với sự cố hệ thống?
- Có tồn tại đường dẫn tải xuống hoặc bản ghi thành công sau thất bại không?
- Tác vụ có được retry không, và retry có tạo artifact trùng hay dùng nhầm dữ liệu cũ không?
- Artifact tạm được thu hồi theo thời hạn nào và ai có quyền truy cập?

Thông điệp lỗi không cần chứa nguyên chuỗi ghi chú hoặc toàn bộ XML. Có thể ghi mã yêu cầu, tên trường, loại lỗi và định danh tác vụ theo chính sách logging. Việc log cả payload nhạy cảm chỉ để chẩn đoán encoding có thể tạo thêm một điểm lộ dữ liệu hoặc một ngữ cảnh đầu ra cần bảo vệ.

Các giới hạn nên được áp dụng ở nhiều lớp phù hợp: request size trước khi xử lý, độ dài trường trong mô hình, số bản ghi trong báo cáo và tổng byte tại đầu ra. Nếu một giới hạn bị vượt, phải kết thúc tác vụ theo đường lỗi đã quy định; không cắt chuỗi XML ở một số byte tùy ý vì có thể làm hỏng cả ký tự UTF-8 lẫn cấu trúc tài liệu.

## 12. Cách dùng bài học khi thiết kế yêu cầu

Khi phân tích một chức năng xuất XML, bắt đầu từ dữ liệu và người nhận: trường nào có nguồn bên ngoài, trường nào do hệ thống quyết định, người nhận dùng chúng để hiển thị hay ra quyết định nghiệp vụ. Sau đó xác định đúng vị trí dữ liệu, serializer và profile XML; viết tiêu chí nghiệm thu cho cả cấu trúc, giá trị và đường lỗi.

Một hồ sơ thiết kế có thể đủ gọn nhưng vẫn truy vết được:

```text
Tài sản: tính toàn vẹn báo cáo xuất cho đối tác.
Đe dọa: ghi chú hoặc tên hiển thị làm phát sinh cấu trúc XML mới.
Ranh giới: dữ liệu nghiệp vụ -> XML serializer -> kênh truyền.
Biện pháp: cấu trúc cố định; API text/attribute; profile XML 1.0;
           byte UTF-8; không unescape sau serialize.
Kiểm chứng: đối chiếu cây và giá trị sau parse; ca ký tự cấm;
            ca giới hạn; kiểm tra artifact không hoàn tất.
Giới hạn: parser đầu vào, phân quyền, XPath và ngữ cảnh trình duyệt
          có bộ yêu cầu riêng.
```

Điểm cốt lõi là bảo toàn quyền kiểm soát cấu trúc thông điệp của ứng dụng, đồng thời vận chuyển đúng dữ liệu mà hợp đồng cho phép. Khi yêu cầu nêu rõ ngữ cảnh, cấu trúc, chính sách Unicode và bằng chứng nghiệm thu, XML encoding trở thành một kiểm soát có thể thiết kế và kiểm chứng, thay vì một nhãn chung gắn vào bất kỳ hàm escape nào.
