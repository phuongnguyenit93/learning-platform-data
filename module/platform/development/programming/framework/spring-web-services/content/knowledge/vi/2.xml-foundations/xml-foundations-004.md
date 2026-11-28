# Khai báo XML, bảng mã và xử lý ký tự đặc biệt

Khi xây dựng dịch vụ SOAP theo hướng **contract-first** với Spring Web Services (Spring-WS), XML không chỉ xuất hiện trong thông điệp gửi nhận mà còn là định dạng của XSD và WSDL. Một ký tự `&` chưa được escape, một tài liệu khai báo UTF-8 nhưng thực tế lưu theo bảng mã khác, hoặc một ký tự điều khiển không hợp lệ đều có thể làm việc phân tích cú pháp thất bại **trước khi request đến endpoint**.

Bài học này trình bày cách khai báo một tài liệu XML đúng chuẩn, chọn và kiểm soát bảng mã, xử lý ký tự đặc biệt và đưa các quy tắc đó vào quá trình thiết kế hợp đồng, ánh xạ JAXB, gửi nhận SOAP và chẩn đoán lỗi tích hợp.

## 1. Cấu trúc XML và khai báo ở đầu tài liệu

Một tài liệu XML *well-formed* có đúng một phần tử gốc, các thẻ mở/đóng khớp nhau, tên thẻ phân biệt chữ hoa chữ thường, giá trị thuộc tính được đặt trong dấu nháy, và mọi ký tự đặc biệt được xử lý theo quy tắc XML.

Ví dụ tài liệu biểu diễn yêu cầu tạo đơn hàng:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<ord:TaoDonHangRequest xmlns:ord="urn:example:orders:v1"
                       kenh="B2B">
    <ord:maDon>DH-2026-001</ord:maDon>
    <ord:nguoiNhan>Nguyễn Thị Ánh</ord:nguoiNhan>
    <ord:ghiChu>Giao trước 17:00 &amp; gọi khi đến.</ord:ghiChu>
</ord:TaoDonHangRequest>
~~~

Dòng đầu là **XML declaration**, có dạng:

~~~xml
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
~~~

| Thành phần | Ý nghĩa | Khuyến nghị |
| --- | --- | --- |
| `version` | Phiên bản quy tắc XML mà bộ phân tích cú pháp phải áp dụng. | Dùng `1.0` cho tích hợp SOAP thông thường; tránh chọn `1.1` nếu chưa xác nhận toàn bộ hệ thống hỗ trợ. |
| `encoding` | Tên bộ mã dùng để biến các byte của tài liệu thành ký tự. | Dùng `UTF-8` và bảo đảm byte thực tế cũng là UTF-8. |
| `standalone` | Cho biết tài liệu có phụ thuộc vào các khai báo đánh dấu bên ngoài có thể ảnh hưởng đến nội dung hay không. | Thường bỏ qua; không tự thêm `yes` nếu chưa hiểu DTD và các khai báo bên ngoài. |

Các điểm cần nhớ:

- XML declaration **không bắt buộc trong mọi tài liệu**, nhưng ghi rõ phiên bản và encoding giúp người đọc, công cụ và hệ thống tích hợp dễ kiểm tra hơn.
- Nếu có XML declaration, nó phải đứng ngay đầu tài liệu (sau BOM nếu có); không được có khoảng trắng, comment hay dữ liệu khác đứng trước nó. Thứ tự các thuộc tính giả trong declaration là `version`, `encoding`, rồi `standalone` nếu chúng xuất hiện.
- Ký hiệu `<?xml ... ?>` chỉ được dùng cho **đầu một tài liệu XML hoàn chỉnh**. Không chèn thêm declaration vào bên trong `soap:Body` hoặc một đoạn XML được lồng trong tài liệu khác.
- `xmlns:ord` khai báo namespace cho tên phần tử; namespace quyết định ý nghĩa tên XML trong hợp đồng, **không** quyết định bảng mã. Tiền tố `ord` có thể đổi, miễn URI namespace vẫn đúng.
- Cả tài liệu XSD, WSDL và SOAP Envelope đều tuân theo các quy tắc XML cơ bản này.

**Phân biệt well-formed và valid:** Tài liệu trên có thể well-formed vì thẻ/escape đúng, nhưng vẫn *không hợp lệ với XSD* nếu hợp đồng không cho phép thuộc tính `kenh`, thiếu phần tử bắt buộc, hoặc sai kiểu dữ liệu. Bộ phân tích cú pháp kiểm tra tính well-formed; bước kiểm tra XSD xác nhận hợp đồng.

## 2. Encoding: từ byte trên đường truyền đến ký tự trong Java

### 2.1. Encoding thực chất giải quyết vấn đề gì?

XML là chuỗi ký tự có cấu trúc, nhưng file và gói tin HTTP chứa **byte**. Encoding quy định cách diễn giải các byte ấy thành ký tự Unicode, cũng như cách chuyển ký tự trở lại thành byte khi xuất dữ liệu.

Ví dụ chữ `Á` trong `Ánh` được biểu diễn bởi mã điểm Unicode U+00C1. Trong UTF-8, ký tự này chiếm hai byte `C3 81`; còn ký tự `&` (U+0026) chiếm byte `26`. Escape XML `&amp;` lại là **năm ký tự ASCII** thể hiện một ký tự `&` sau khi parser đọc xong. Encoding và escaping giải quyết hai tầng khác nhau.

| Tầng xử lý | Ví dụ | Việc cần bảo đảm |
| --- | --- | --- |
| File XML/XSD/WSDL | File lưu dạng UTF-8 | Byte trên đĩa khớp với declaration. |
| HTTP SOAP | `Content-Type: text/xml; charset=utf-8` | Charset công bố khớp byte của phần thân thông điệp. |
| Parser XML | Byte → mã điểm Unicode → cây XML | Không có byte lỗi, ký tự XML không hợp lệ hay cấu trúc sai. |
| Java/JAXB | `String` chứa `Nguyễn Thị Ánh` | Giá trị ký tự được giữ đúng; API Java thường thao tác theo đơn vị mã UTF-16. |
| Serializer XML | Cây đối tượng → XML → byte | Escape cú pháp đúng và xuất bằng encoding đã chọn. |

UTF-8 là lựa chọn phổ biến nhất cho tích hợp doanh nghiệp: tương thích ASCII ở các ký tự cơ bản, hỗ trợ toàn bộ Unicode, thuận tiện cho tiếng Việt và dữ liệu đa ngôn ngữ. UTF-16 cũng là encoding XML hợp lệ nhưng cần thống nhất cách xác định thứ tự byte; việc trộn UTF-8, UTF-16 hoặc các bảng mã cũ giữa các thành phần gây lỗi khó chẩn đoán. Các bảng mã như ISO-8859-1 không biểu diễn đầy đủ tiếng Việt.

### 2.2. XML declaration, BOM và HTTP Content-Type

Ba nguồn thông tin thường gặp khi đọc một thông điệp XML là:

1. **Byte thực tế**: nguồn dữ liệu cuối cùng mà parser phải giải mã.
2. **BOM** (*byte order mark*): có thể được dùng để nhận diện cách mã hóa, nhất là thứ tự byte của UTF-16. UTF-8 có thể có BOM, nhưng nhiều quy trình chọn UTF-8 **không BOM** để tránh rắc rối ở các công cụ xử lý văn bản.
3. **XML declaration và metadata của transport**: ví dụ `encoding="UTF-8"` và tham số `charset` trong HTTP `Content-Type`.

Không có một cách xử lý duy nhất cho mọi bộ parser, transport và API đầu vào. Quy tắc tích hợp an toàn là **đồng bộ encoding thực tế, XML declaration và charset của HTTP**; đừng dựa vào việc hệ thống tự đoán hoặc tự sửa khi chúng mâu thuẫn.

Ví dụ hai kiểu Content-Type thường gặp:

~~~http
Content-Type: text/xml; charset=utf-8
~~~

Dòng trên thường dùng cho SOAP 1.1. Với SOAP 1.2, kiểu media thường là:

~~~http
Content-Type: application/soap+xml; charset=utf-8
~~~

SOAP 1.1 và SOAP 1.2 còn khác namespace của Envelope và cách biểu diễn action; vì vậy không chỉ đổi Content-Type mà xem như đã chuyển phiên bản SOAP.

**Lưu ý về BOM:** BOM UTF-8 hợp lệ ở đầu tài liệu XML và parser tuân thủ chuẩn có thể nhận ra nó. Tuy nhiên, việc một số công cụ đơn giản xử lý sai BOM hoặc nối nhiều tài liệu XML vào một luồng vẫn có thể gây lỗi. Trong quy trình mới, xuất UTF-8 không BOM và kiểm tra byte đầu file giúp giảm điểm khác biệt giữa môi trường.

### 2.3. Ký tự tiếng Việt, emoji và chuẩn hóa Unicode

Với UTF-8, văn bản như `Đặng Thị Hòa – giao hàng 🚚` hoàn toàn có thể được biểu diễn trong XML 1.0 nếu ứng dụng và cơ sở dữ liệu hỗ trợ các ký tự này. Ký tự ngoài mặt phẳng Unicode cơ bản, chẳng hạn emoji, thường chiếm bốn byte UTF-8 và được Java biểu diễn bằng cặp surrogate UTF-16 khi truy cập qua `char`.

Hai chuỗi nhìn giống nhau cũng chưa chắc bằng nhau theo mã điểm: `é` có thể là U+00E9 hoặc tổ hợp `e` + U+0301. XML không tự chuyển tất cả chuỗi sang NFC/NFD. Nếu nghiệp vụ cần chuẩn hóa để so sánh tên, tìm kiếm hoặc tạo chữ ký số, hãy quy định rõ tại tầng ứng dụng và bảo đảm bên gửi/bên nhận xử lý thống nhất.

## 3. Năm thực thể ký tự định sẵn trong XML

Trong nội dung XML, ký tự `&` bắt đầu một tham chiếu thực thể hoặc ký tự; dấu `<` bắt đầu thẻ. Muốn ghi chúng như dữ liệu thông thường phải escape.

| Ký tự mong muốn | Cách ghi trong XML | Trong nội dung phần tử | Trong thuộc tính |
| --- | --- | --- | --- |
| `&` | `&amp;` | Bắt buộc escape | Bắt buộc escape |
| `<` | `&lt;` | Bắt buộc escape | Bắt buộc escape |
| `>` | `&gt;` | Thường không bắt buộc; bắt buộc tránh chuỗi `]]>` trong dữ liệu ký tự | Có thể dùng trực tiếp, nhưng escape giúp nhất quán |
| `"` | `&quot;` | Thường không cần | Phải escape nếu thuộc tính bao bởi `"` |
| `'` | `&apos;` | Thường không cần | Phải escape nếu thuộc tính bao bởi `'` |

Đây là **năm tên thực thể có sẵn** trong XML. Các tên quen thuộc của HTML như `&nbsp;` không mặc nhiên tồn tại trong XML. Việc tự định nghĩa thực thể qua DTD không phải lựa chọn phù hợp cho SOAP vì tăng phụ thuộc và mở rộng bề mặt tấn công.

Ví dụ đúng:

~~~xml
<ord:ghiChu>R&amp;D: 3 &lt; 5, nhưng 5 &gt; 3.</ord:ghiChu>
<ord:nguoiNhan tenHienThi="Dương &quot;An&quot; &amp; cộng sự"/>
<ord:nguoiNhan tenHienThi='O&apos;Brien'/>
~~~

Sau khi parser xử lý, giá trị văn bản của `ord:ghiChu` là `R&D: 3 < 5, nhưng 5 > 3.`. Ở thuộc tính `tenHienThi`, phần `&quot;` khôi phục dấu nháy kép và `&apos;` khôi phục dấu nháy đơn.

Ví dụ sai:

~~~xml
<!-- Sai: dấu & chưa được escape -->
<ord:ghiChu>R&D & Sales</ord:ghiChu>

<!-- Sai: dấu < bị hiểu là mở một thẻ -->
<ord:ghiChu>Giá < 100000</ord:ghiChu>

<!-- Sai: dấu " kết thúc thuộc tính sớm -->
<ord:khach ten="Dương "An""/>
~~~

Một sai lầm thường gặp là escape hai lần. Nếu dữ liệu gốc là `R&D`, XML serializer cần tạo `R&amp;D`. Nếu lập trình viên tự thay `&` thành `&amp;` trong `String` rồi lại chuyển `String` qua JAXB, serializer có thể tạo `R&amp;amp;D`; bên nhận đọc được `R&amp;D` thay vì `R&D`.

**Nguyên tắc:** giữ dữ liệu ở dạng ký tự thuần trong mô hình Java; để thư viện JAXB/XML serializer thực hiện escaping đúng một lần khi xuất XML. Không ghép SOAP Envelope bằng cách nối chuỗi lấy trực tiếp từ input.

## 4. Tham chiếu ký tự số và CDATA

### 4.1. Tham chiếu thập phân và thập lục phân

Ngoài năm thực thể có tên, XML cho phép tham chiếu ký tự theo mã điểm Unicode:

~~~xml
<ghiChu>Giá: 100&#160;000 VNĐ</ghiChu>
<ghiChu>Giá: 100&#xA0;000 VNĐ</ghiChu>
<ghiChu>Dòng 1&#10;Dòng 2</ghiChu>
~~~

`&#160;` và `&#xA0;` đều biểu diễn U+00A0 (khoảng trắng không ngắt dòng). `&#10;` là U+000A (xuống dòng). Tham chiếu ký tự phù hợp khi cần biểu diễn một ký tự Unicode cụ thể trong XML, nhưng không nên lạm dụng cho tiếng Việt: UTF-8 có thể ghi trực tiếp `Đ`, `ộ`, `ữ` một cách rõ ràng.

Một tham chiếu số **không thể hợp pháp hóa mã điểm bị XML cấm**. Ví dụ `&#0;`, `&#x0;` đều sai trong XML 1.0; parser phải báo lỗi ngay cả khi các byte của file được mã hóa UTF-8 đúng.

### 4.2. CDATA: giữ nguyên ký hiệu cú pháp trong một đoạn văn bản

CDATA có dạng `<![CDATA[...]]>`. Bên trong CDATA, `<` và `&` được xem như văn bản thường, không bắt đầu thẻ hay thực thể:

~~~xml
<ord:ghiChu><![CDATA[
  Bên nhận muốn hiển thị: A < B && C > D
]]></ord:ghiChu>
~~~

CDATA chỉ là cách viết khác của **text node**. Sau khi parse, ứng dụng nhận nội dung ký tự; không có bảo đảm rằng serializer sẽ giữ nguyên việc dùng CDATA khi xuất lại XML.

Giới hạn quan trọng:

- Chuỗi `]]>` không thể nằm nguyên vẹn trong một đoạn CDATA vì nó là dấu kết thúc đoạn; phải tách đoạn hoặc biểu diễn bằng văn bản XML được escape.
- CDATA không cho phép các mã điểm Unicode bị XML 1.0 cấm.
- CDATA không thay thế validation theo XSD, quy định bảo mật hay escaping ở các tầng khác như SQL/HTML.
- Với SOAP/JAXB, cách thông thường là giữ nội dung ở `String` và cho serializer tự escape; hiếm khi cần tự tạo CDATA.

## 5. Ký tự nào được phép trong XML 1.0?

XML 1.0 cho phép các mã điểm sau trong nội dung tài liệu:

- U+0009 (TAB), U+000A (LF) và U+000D (CR).
- U+0020 đến U+D7FF.
- U+E000 đến U+FFFD.
- U+10000 đến U+10FFFF.

Các khoảng này **không** bao gồm U+0000 (NUL), nhiều ký tự điều khiển như U+0001 và U+001F, hoặc các mã surrogate U+D800–U+DFFF xuất hiện đơn lẻ. Một số mã điểm ít dùng dù thuộc khoảng cho phép cũng được chuẩn XML khuyến cáo tránh sử dụng.

| Dữ liệu đầu vào | Hợp lệ trong XML 1.0? | Ghi chú |
| --- | --- | --- |
| `Xin chào, Hà Nội` | Có | Ghi trực tiếp với UTF-8. |
| `A & B` | Có, nếu xuất thành `A &amp; B` | Dấu `&` thô làm hỏng cú pháp. |
| Dấu xuống dòng LF (U+000A) | Có | Parser có quy tắc chuẩn hóa xuống dòng. |
| Emoji 🚚 (U+1F69A) | Có | Cần đường truyền UTF-8 và hệ thống đích hỗ trợ. |
| NUL (U+0000) | Không | Không sửa được bằng `&#0;` hoặc CDATA. |
| Surrogate đơn lẻ (U+D800) | Không | Thường phát sinh từ chuỗi Java bị cắt sai vị trí. |

Ví dụ hàm kiểm tra mã điểm trước khi gửi dữ liệu tới hệ thống XML. Hàm dùng `codePoints()` thay vì duyệt từng `char` để không chặn nhầm cặp surrogate hợp lệ của emoji:

~~~java
public final class Xml10Characters {
    private Xml10Characters() {}

    public static boolean isAllowed(int codePoint) {
        return codePoint == 0x09
                || codePoint == 0x0A
                || codePoint == 0x0D
                || (codePoint >= 0x20 && codePoint <= 0xD7FF)
                || (codePoint >= 0xE000 && codePoint <= 0xFFFD)
                || (codePoint >= 0x10000 && codePoint <= 0x10FFFF);
    }

    public static void requireValid(String value) {
        value.codePoints().forEach(codePoint -> {
            if (!isAllowed(codePoint)) {
                throw new IllegalArgumentException(
                        "Ky tu khong hop le trong XML 1.0: U+"
                        + Integer.toHexString(codePoint).toUpperCase()
                );
            }
        });
    }
}
~~~

Khi gặp ký tự không hợp lệ từ file import, cơ sở dữ liệu cũ hoặc hệ thống đối tác, nên **tìm nguyên nhân và xác định chính sách xử lý rõ ràng** (từ chối dữ liệu, làm sạch theo quy tắc nghiệp vụ, hoặc thông báo cho bên gửi). Xóa ký tự âm thầm có thể khiến nội dung đơn hàng bị sai lệch, đặc biệt với trường mô tả có giá trị pháp lý.

### 5.1. Khoảng trắng cũng có ngữ nghĩa

XML có quy tắc chuẩn hóa các dạng xuống dòng trong lúc parse; trong giá trị thuộc tính, các ký tự tab/xuống dòng được ghi trực tiếp còn chịu quy tắc chuẩn hóa thuộc tính. Lớp XSD có thể tiếp tục chuẩn hóa:

- `xs:string`: về cơ bản giữ khoảng trắng của giá trị sau khi XML parser đã xử lý.
- `xs:normalizedString`: thay TAB/LF/CR bằng khoảng trắng theo facet `whiteSpace`.
- `xs:token`: thay và gộp chuỗi khoảng trắng, đồng thời bỏ khoảng trắng ở hai đầu.

Vì thế, cùng dữ liệu “nhìn giống nhau” có thể khác về mặt nghiệp vụ giữa `xs:string` và `xs:token`. Hãy chọn kiểu XSD theo ý nghĩa trường: ghi chú tự do thường cần `xs:string`; mã định danh được chuẩn hóa có thể hợp với kiểu hạn chế hơn.

## 6. Áp dụng vào SOAP contract-first với Spring Web Services

### 6.1. XSD xác định cấu trúc và kiểu dữ liệu

Giả sử dịch vụ tạo đơn hàng có phần tử yêu cầu `TaoDonHangRequest` trong namespace `urn:example:orders:v1`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"
           targetNamespace="urn:example:orders:v1"
           xmlns:ord="urn:example:orders:v1"
           elementFormDefault="qualified">
    <xs:element name="TaoDonHangRequest">
        <xs:complexType>
            <xs:sequence>
                <xs:element name="maDon" type="xs:string"/>
                <xs:element name="ghiChu" type="xs:string"
                            minOccurs="0"/>
            </xs:sequence>
        </xs:complexType>
    </xs:element>
</xs:schema>
~~~

Đây là **tài liệu XSD độc lập**, nên có XML declaration riêng ở đầu file. WSDL tham chiếu hoặc nhúng schema này cũng là tài liệu XML và cần được lưu/gửi với encoding đúng. XSD mô tả phần tử `ghiChu` có kiểu `xs:string`, nhưng giá trị truyền trên dây vẫn phải tuân theo quy tắc cú pháp và mã điểm của XML.

### 6.2. XML trên dây trong SOAP Envelope

Một request SOAP 1.1 hợp lệ đối với phần tử XSD nói trên có thể là:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<soap:Envelope
    xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"
    xmlns:ord="urn:example:orders:v1">
    <soap:Header/>
    <soap:Body>
        <ord:TaoDonHangRequest>
            <ord:maDon>DH-2026-001</ord:maDon>
            <ord:ghiChu>Giao cho A &amp; B; tránh &lt;cửa sau&gt;.</ord:ghiChu>
        </ord:TaoDonHangRequest>
    </soap:Body>
</soap:Envelope>
~~~

Trong Java, nội dung của `ghiChu` sau unmarshalling là `Giao cho A & B; tránh <cửa sau>.`. Không có thẻ `<cửa sau>` nào xuất hiện trong cây XML vì dấu `<` đã được escape.

Lưu ý rằng XML declaration ở đầu thuộc **toàn bộ SOAP Envelope**. Nếu tạo payload XML như một fragment để Spring-WS đưa vào `soap:Body`, không thêm declaration cho fragment đó. Spring-WS xác định payload theo tên phần tử và namespace, không theo tiền tố hiển thị như `ord` hay `soap`.

### 6.3. JAXB tự thực hiện XML escaping

Trong hệ thống sử dụng Spring-WS hiện đại với Jakarta JAXB, đối tượng request có thể được ánh xạ từ XSD sang class Java. Ví dụ dưới đây minh họa marshalling một đối tượng có `@XmlRootElement` thành tài liệu XML độc lập:

~~~java
import jakarta.xml.bind.JAXBContext;
import jakarta.xml.bind.Marshaller;
import java.io.OutputStream;
import java.nio.file.Files;
import java.nio.file.Path;

// TaoDonHangRequest la class JAXB da duoc tao/anh xa tu XSD,
// co @XmlRootElement phu hop voi phan tu goc trong contract.
TaoDonHangRequest request = new TaoDonHangRequest();
request.setMaDon("DH-2026-001");
request.setGhiChu("Giao cho A & B; tránh <cửa sau>.");

JAXBContext context = JAXBContext.newInstance(TaoDonHangRequest.class);
Marshaller marshaller = context.createMarshaller();
marshaller.setProperty(Marshaller.JAXB_ENCODING, "UTF-8");
marshaller.setProperty(Marshaller.JAXB_FORMATTED_OUTPUT, true);

try (OutputStream out = Files.newOutputStream(Path.of("request.xml"))) {
    marshaller.marshal(request, out);
}
~~~

Trong file xuất ra, JAXB sẽ biểu diễn ký tự `&` và `<` theo cú pháp XML phù hợp. Không gọi `replace("&", "&amp;")` trên dữ liệu trước khi `setGhiChu`. Nếu class tạo từ XSD sử dụng `JAXBElement` thay vì `@XmlRootElement`, có thể cần đối tượng từ `ObjectFactory` tương ứng để marshal đúng root element.

Ở ứng dụng Spring-WS, `Jaxb2Marshaller` thường được dùng cùng `WebServiceTemplate` (client) hoặc cơ chế chuyển đổi payload ở endpoint. Nó đảm nhiệm ánh xạ object/XML; **SOAP Envelope, các header và charset HTTP** còn phụ thuộc cấu hình message factory và tầng gửi nhận. Thuộc tính `Marshaller.JAXB_ENCODING` trong ví dụ file độc lập không mặc nhiên thay thế cấu hình transport.

Với Spring-WS phiên bản cũ sử dụng JAXB `javax.xml.bind`, cách quản lý encoding và escape vẫn tương tự; chỉ khác namespace Java API và các phụ thuộc thư viện.

### 6.4. Kiểm tra ở những tầng nào?

Một request có thể bị từ chối ở nhiều thời điểm khác nhau:

1. **Giải mã byte / parse XML:** lỗi charset, thực thể không hợp lệ, ký tự bị cấm hoặc cấu trúc thẻ sai. Endpoint thường chưa được gọi.
2. **Kiểm tra XSD:** XML đã well-formed nhưng thiếu `maDon`, sai namespace hoặc kiểu dữ liệu. Trong Spring-WS có thể dùng interceptor kiểm tra schema khi cấu hình phù hợp.
3. **Unmarshal JAXB:** cấu trúc XML không ánh xạ được vào class/kiểu đã định nghĩa.
4. **Xử lý nghiệp vụ tại endpoint:** giá trị đã parse được nhưng vi phạm quy tắc ứng dụng, ví dụ ghi chú vượt giới hạn cho phép.

Một lỗi ở các tầng này có thể dẫn đến SOAP Fault tùy cấu hình của server và cách ánh xạ ngoại lệ. Cần xem log ở tầng tương ứng thay vì mặc định rằng lỗi encoding là lỗi logic của endpoint.

## 7. XML security và WS-Security liên quan đến nội dung ký tự

**Entity và DTD:** ngoài năm thực thể định sẵn, XML có thể hỗ trợ khai báo DTD và thực thể tùy chỉnh. Đối với SOAP tích hợp hệ thống, nên cấu hình các parser xử lý XML không tin cậy theo hướng hạn chế DTD, external entity và tài nguyên ngoài để giảm rủi ro XXE và entity expansion. Với Java, các tùy chọn như `XMLConstants.FEATURE_SECURE_PROCESSING`, `XMLConstants.ACCESS_EXTERNAL_DTD`, `XMLConstants.ACCESS_EXTERNAL_SCHEMA` và các cờ riêng của SAX/DOM/StAX cần được cấu hình theo API/parser đang dùng; không giả định mặc định là an toàn.

**XML Signature / WS-Security:** chữ ký số thường áp dụng các phép biến đổi và XML Canonicalization (C14N). Việc đổi cách xuống dòng, thêm/sửa namespace, serialize lại tài liệu đã ký hoặc chuẩn hóa Unicode không thống nhất có thể làm kiểm tra chữ ký thất bại, dù người đọc thấy thông điệp gần giống. Không chỉnh sửa thủ công XML đã ký; dùng các thư viện WS-Security tương thích, cấu hình thuật toán canonicalization đúng theo hợp đồng và xử lý nội dung trước khi ký.

**Chứng chỉ không giải quyết encoding:** TLS và chữ ký số xác thực/bảo vệ kênh hoặc thông điệp, nhưng không làm cho byte sai charset, `&` không escape hay U+0000 trở thành XML hợp lệ. An toàn truyền thông và well-formed XML là các yêu cầu độc lập đều phải đạt.

## 8. Chẩn đoán lỗi thường gặp

| Triệu chứng | Nguyên nhân đáng kiểm tra | Hướng xử lý |
| --- | --- | --- |
| `Content is not allowed in prolog` | Byte/ký tự lạ trước tài liệu, file bị ghép nội dung, hoặc dữ liệu không phải XML. | Kiểm tra byte đầu, BOM, nội dung HTTP thực tế và bảo đảm declaration ở vị trí đầu. |
| `Invalid byte ... of ... UTF-8 sequence` | Dữ liệu được ghi theo encoding khác nhưng parser đang giải mã UTF-8, hoặc byte bị hỏng. | So sánh raw byte, declaration và HTTP charset; xuất UTF-8 nhất quán. |
| `The entity name must immediately follow the '&'` | Dấu `&` xuất hiện thô trong text hoặc attribute. | Dùng `&amp;` hoặc để serializer XML escape tự động. |
| `The element type ... must be terminated` | Dấu `<` thô bị hiểu là thẻ, hoặc thẻ mở/đóng không khớp. | Parse bằng XML parser, escape `<` trong dữ liệu và sửa cấu trúc thẻ. |
| `An invalid XML character (Unicode: 0x0)` | Chuỗi chứa NUL hay mã điểm bị XML 1.0 cấm. | Kiểm tra nguồn dữ liệu và từ chối/làm sạch theo chính sách có kiểm soát. |
| `Undeclared entity 'nbsp'` (hoặc tương tự) | Dùng entity HTML trong XML không có định nghĩa. | Dùng ký tự UTF-8 trực tiếp hoặc `&#160;` nếu cần U+00A0. |
| JAXB nhận `R&amp;D` thay vì `R&D` | Escape hai lần trước khi marshal. | Đưa `String` nguyên bản vào JAXB; kiểm tra XML đầu ra. |
| SOAP Fault về validation/namespace | Phần tử namespace sai hoặc nội dung không khớp XSD. | So lại QName (URI namespace + local name), XSD, WSDL và thông điệp thực tế. |
| Lỗi verify WS-Security signature sau khi proxy sửa XML | Nội dung/phép biến đổi được ký không còn khớp. | Không sửa SOAP đã ký và kiểm tra chuỗi xử lý canonicalization. |

Khi điều tra lỗi, lưu một bản thông điệp thử nghiệm đã loại bỏ dữ liệu nhạy cảm và **so sánh cả raw byte, HTTP Content-Type và kết quả parser**. Chỉ nhìn vào văn bản đã được log hoặc console tự giải mã có thể che khuất nguyên nhân encoding.

## 9. Quy trình thực hành và tự kiểm tra

Hãy dùng cùng một XSD và request SOAP ở mục 6 để thử các tình huống sau:

| Ca thử | Dữ liệu `ghiChu` ban đầu | Kỳ vọng |
| --- | --- | --- |
| 1 — Ký tự đặc biệt | `R&D < nhóm ưu tiên > 1` | JAXB xuất XML well-formed; unmarshalling khôi phục đúng chuỗi ban đầu. |
| 2 — Tiếng Việt và Unicode | `Giao tới Đà Nẵng 🚚` | Gửi/nhận qua UTF-8 không mất dấu hoặc emoji. |
| 3 — Ký tự cấm | Chuỗi có U+0000 | Bị phát hiện trước khi gửi hoặc parser từ chối; `&#0;` không giải quyết lỗi. |
| 4 — Escape lặp | Đưa `R&amp;D` vào `String` thay vì `R&D` | Phát hiện giá trị bị đổi sau vòng marshal/unmarshal; sửa tại tầng tạo dữ liệu. |
| 5 — Sai hợp đồng | Đổi namespace request sang URI khác | XML vẫn có thể well-formed nhưng không còn khớp contract/XSD/endpoint. |
| 6 — Sai encoding | File lưu bảng mã khác trong khi khai báo `UTF-8` | Parser thất bại hoặc dữ liệu hiển thị sai; sửa đồng bộ byte và metadata. |

Một luồng kiểm thử hữu ích là **tạo dữ liệu Java → marshal XML → parse XML → validate XSD → unmarshal → so sánh chuỗi**. Sau đó kiểm thử tích hợp với SOAP client/server thực tế để phát hiện vấn đề từ HTTP header, message factory, interceptor và WS-Security. Với trường hợp lỗi ký tự, xác minh cả kết quả round-trip lẫn nội dung byte thực tế.

### Ghi nhớ để triển khai

- Với SOAP/XSD/WSDL, ưu tiên **XML 1.0 + UTF-8 thống nhất** từ file đến đường truyền.
- **Encoding** chuyển giữa byte và ký tự; **escaping XML** biểu diễn ký tự có ý nghĩa cú pháp. Một cơ chế không thay cho cơ chế kia.
- Năm thực thể định sẵn: `&amp;`, `&lt;`, `&gt;`, `&quot;`, `&apos;`. Tham chiếu số và CDATA vẫn phải tuân thủ tập ký tự hợp lệ của XML.
- Dùng **JAXB/Spring-WS** để tạo và đọc payload; giữ `String` là dữ liệu thuần, tránh nối chuỗi XML hoặc escape thủ công.
- Kiểm tra **well-formed XML, XSD, namespace, transport charset và bảo mật parser** như các lớp riêng; theo dõi lỗi đúng tầng để tìm nguyên nhân nhanh.

