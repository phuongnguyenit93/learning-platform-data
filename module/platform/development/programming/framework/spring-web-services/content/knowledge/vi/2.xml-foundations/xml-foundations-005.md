# Không có phần tử, phần tử rỗng và giá trị xsi:nil trong XML/SOAP

## 1. Vì sao phải phân biệt ba trạng thái?

Trong tích hợp SOAP theo hướng **contract-first** với Spring Web Services, một trường dữ liệu có thể **không xuất hiện**, **xuất hiện nhưng không có nội dung**, hoặc **xuất hiện và được đánh dấu nil**. Ba cách biểu diễn này có thể mang ba ý nghĩa nghiệp vụ khác nhau, dù ở phía Java chúng rất dễ bị quy về cùng một giá trị `null` hoặc chuỗi rỗng.

Ví dụ, với yêu cầu cập nhật hồ sơ khách hàng:

- Không gửi **nickname**: giữ nguyên biệt danh đang lưu.
- Gửi **nickname** rỗng: đặt biệt danh thành chuỗi `""`.
- Gửi **nickname** với `xsi:nil="true"`: xóa biệt danh, chuyển giá trị lưu trữ thành `null`.

**Đây là một quy ước nghiệp vụ minh họa, không phải ngữ nghĩa được XML Schema tự động gán.** XSD quy định dạng dữ liệu nào hợp lệ; tài liệu hợp đồng dịch vụ và mã xử lý quy định hệ thống phải làm gì với mỗi dạng.

Sau bài này, bạn cần nhận diện chính xác ba trạng thái trên tài liệu XML, thiết kế `minOccurs` và `nillable` trong XSD, hiểu tác động tới JAXB và kiểm thử bản tin SOAP ở mức XML thực tế.

## 2. Ba biểu diễn trên XML

Giả sử phần tử `nickname` thuộc namespace `urn:example:customer:v1`.

### 2.1. Không có phần tử (absent/omitted)

~~~xml
<c:UpdateCustomerRequest xmlns:c="urn:example:customer:v1">
    <c:customerId>C-101</c:customerId>
    <!-- Không có phần tử c:nickname -->
</c:UpdateCustomerRequest>
~~~

Trong cây XML, **không tồn tại node phần tử** `c:nickname`. Không thể suy từ đó rằng giá trị của nó là `""`, `null`, số 0 hoặc giá trị mặc định của ứng dụng. Một schema có thể cho phép sự vắng mặt bằng `minOccurs="0"`; nếu `minOccurs="1"` thì bản tin bị thiếu phần tử bắt buộc.

### 2.2. Có phần tử nhưng rỗng (present and empty)

~~~xml
<c:nickname xmlns:c="urn:example:customer:v1"/>
<c:nickname xmlns:c="urn:example:customer:v1"></c:nickname>
~~~

Hai cách viết này biểu diễn cùng một phần tử không có nội dung con. Với kiểu `xs:string` thông thường, không có ràng buộc cấm rỗng và không áp dụng schema default, giá trị của nó là **chuỗi rỗng**. Nó không tự động trở thành `null`.

Điểm cần chú ý:

- `<c:nickname> </c:nickname>` chứa một dấu cách, khác phần tử rỗng ở mức XML. Schema có thể chuẩn hóa khoảng trắng tùy kiểu dữ liệu.
- `<c:age/>` **không hợp lệ** nếu `age` có kiểu `xs:int` và không có cơ chế schema thích hợp cho giá trị mặc định: chuỗi rỗng không phải số nguyên.
- Một phần tử kiểu phức hợp như `<c:address/>` chỉ hợp lệ khi định nghĩa kiểu cho phép không có các phần tử con bắt buộc.
- XSD có thể khai báo `default` hoặc `fixed`; khi xác thực schema, cách xử lý giá trị mặc định của một phần tử rỗng cần được xét riêng. Không được mặc định mọi phần tử rỗng đều có giá trị `""` sau xác thực.

### 2.3. Có phần tử với `xsi:nil="true"` (present and nil)

~~~xml
<c:nickname
    xmlns:c="urn:example:customer:v1"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
    xsi:nil="true"/>
~~~

Phần tử vẫn **tồn tại** trong XML, nhưng thuộc tính đặc biệt `xsi:nil` thông báo rằng nó được đánh dấu *nilled*. Namespace `xsi` phải trỏ tới `http://www.w3.org/2001/XMLSchema-instance`; tên prefix có thể khác, nhưng namespace URI phải đúng.

Để hợp lệ theo XSD, phần tử phải được khai báo **`nillable="true"`** và khi được đánh dấu nil thì không chứa nội dung ký tự hoặc phần tử con. Cách viết `xsi:nil="1"` cũng là biểu diễn boolean hợp lệ của giá trị true; thông thường nên dùng `"true"` cho dễ đọc.

Không nên nhầm lẫn:

| Dạng XML | Phần tử có xuất hiện? | Ý nghĩa cấu trúc |
| --- | --- | --- |
| Không có thẻ `nickname` | Không | Phần tử vắng mặt |
| `<nickname/>` | Có | Phần tử có nội dung rỗng |
| `<nickname></nickname>` | Có | Tương đương dạng tự đóng ở trên |
| `<nickname xsi:nil="true"/>` | Có | Phần tử hiện diện và được đánh dấu nil |
| `<nickname>Lan</nickname>` | Có | Phần tử có nội dung ký tự |

*Trong bảng, các ví dụ rút gọn đã bỏ qua khai báo namespace để tập trung vào hình dạng XML.*

## 3. `minOccurs` và `nillable`: hai quy tắc độc lập

`minOccurs` quy định **số lần phần tử phải xuất hiện** trong một nhóm nội dung XSD (thường là `xs:sequence`). `nillable` quy định **một phần tử đã xuất hiện có được phép mang `xsi:nil="true"` hay không**.

| Khai báo XSD | Bỏ hẳn phần tử | Xuất hiện với `xsi:nil="true"` |
| --- | :---: | :---: |
| `minOccurs="1" nillable="false"` | Không | Không |
| `minOccurs="1" nillable="true"` | Không | Có |
| `minOccurs="0" nillable="false"` | Có | Không |
| `minOccurs="0" nillable="true"` | Có | Có |

Nếu không khai báo, giá trị mặc định là `minOccurs="1"` và `nillable="false"`. Khả năng dùng phần tử rỗng thông thường phụ thuộc **kiểu dữ liệu và các facet** như `minLength`, `pattern`, không do riêng `nillable` quyết định.

Ví dụ XSD đầy đủ:

~~~xml
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"
           targetNamespace="urn:example:customer:v1"
           xmlns:tns="urn:example:customer:v1"
           elementFormDefault="qualified">

    <xs:element name="UpdateCustomerRequest">
        <xs:complexType>
            <xs:sequence>
                <!-- Bắt buộc có mã khách hàng, không được nil -->
                <xs:element name="customerId" type="xs:string"/>

                <!-- Có thể bỏ qua, để rỗng hoặc đánh dấu nil -->
                <xs:element name="nickname" type="xs:string"
                            minOccurs="0" nillable="true"/>

                <!-- Có thể bỏ qua hoặc nil; không thể gửi số nguyên rỗng -->
                <xs:element name="age" type="xs:int"
                            minOccurs="0" nillable="true"/>

                <!-- Bắt buộc xuất hiện nhưng được phép nil -->
                <xs:element name="comment" type="xs:string"
                            minOccurs="1" nillable="true"/>
            </xs:sequence>
        </xs:complexType>
    </xs:element>
</xs:schema>
~~~

Với schema này, bốn trường hợp sau cho riêng `nickname` đều hợp lệ: bỏ hẳn; `<c:nickname/>`; `<c:nickname xsi:nil="true"/>`; hoặc `<c:nickname>An</c:nickname>`. Với **age**, `<c:age/>` không hợp lệ, còn `<c:age xsi:nil="true"/>` hợp lệ. Với **comment**, bỏ hẳn là không hợp lệ dù có `nillable="true"`.

Ví dụ tài liệu XML thỏa schema, bao gồm phần tử `comment` bắt buộc:

~~~xml
<c:UpdateCustomerRequest
    xmlns:c="urn:example:customer:v1"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
    <c:customerId>C-101</c:customerId>
    <c:nickname xsi:nil="true"/>
    <c:age>28</c:age>
    <c:comment/>
</c:UpdateCustomerRequest>
~~~

Lưu ý thứ tự các phần tử ở ví dụ phải tuân theo `xs:sequence`. Nếu hợp đồng yêu cầu thứ tự `customerId`, `nickname`, `age`, `comment`, một client gửi sai thứ tự vẫn có thể bị từ chối khi xác thực XSD dù từng trường có kiểu đúng.

## 4. Trường hợp hợp lệ và không hợp lệ cần nhớ

Giả sử khai báo `nickname` là `xs:string minOccurs="0" nillable="true"`, `age` là `xs:int minOccurs="0" nillable="true"`, và `customerId` là `xs:string` bắt buộc, không nillable.

| XML đang xét | Hợp lệ theo khai báo trên? | Giải thích |
| --- | :---: | --- |
| Bỏ `nickname` | Có | `minOccurs=0` |
| `<c:nickname/>` | Có | `xs:string` chấp nhận chuỗi rỗng |
| `<c:nickname xsi:nil="true"/>` | Có | `nillable=true` |
| `<c:nickname xsi:nil="true">An</c:nickname>` | Không | Phần tử nil không được chứa nội dung |
| `<c:age/>` | Không | Rỗng không phải giá trị `xs:int` |
| `<c:age xsi:nil="true"/>` | Có | Nil khác số nguyên rỗng |
| Bỏ `customerId` | Không | Mặc định `minOccurs=1` |
| `<c:customerId xsi:nil="true"/>` | Không | Mặc định `nillable=false` |

Các kết luận trên là về **xác thực XSD**. Một XML parser chỉ kiểm tra tài liệu well-formed có thể vẫn đọc được một thông điệp không hợp lệ theo XSD. Vì vậy cần phân biệt ba cấp: XML well-formed, XSD-valid và được nghiệp vụ chấp nhận.

## 5. Ba trạng thái đi vào SOAP như thế nào?

SOAP dùng XML làm định dạng bản tin. `xsi:nil` ở đây vẫn là cơ chế của XML Schema; nó **không phải** một thuộc tính riêng của giao thức SOAP.

Ví dụ SOAP 1.1 gửi yêu cầu xóa biệt danh theo quy ước nghiệp vụ đã nêu:

~~~xml
<soap:Envelope
    xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"
    xmlns:c="urn:example:customer:v1"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
    <soap:Header/>
    <soap:Body>
        <c:UpdateCustomerRequest>
            <c:customerId>C-101</c:customerId>
            <c:nickname xsi:nil="true"/>
            <c:comment/>
        </c:UpdateCustomerRequest>
    </soap:Body>
</soap:Envelope>
~~~

Nếu bỏ dòng `<c:nickname xsi:nil="true"/>` thì yêu cầu có thể mang nghĩa **giữ nguyên** biệt danh; nếu thay bằng `<c:nickname/>` thì có thể mang nghĩa **đặt thành chuỗi rỗng**. Ba hành vi đó phải được quy định rõ trong mô tả operation, tài liệu API hoặc quy tắc nghiệp vụ; chỉ nhìn WSDL/XSD chưa thể suy ra hết.

Không nên dùng `xsi:nil` để thông báo lỗi xử lý. Một lỗi xử lý SOAP đúng nghĩa cần được diễn đạt bằng **SOAP Fault** theo hợp đồng dịch vụ; giá trị nil chỉ mô tả trạng thái của phần tử dữ liệu hợp lệ.

## 6. Từ XSD sang JAXB trong Spring Web Services

Trong quy trình contract-first, nhóm phát triển thiết kế XSD trước, công bố WSDL tham chiếu tới schema rồi sinh các lớp Java bằng JAXB/XJC hoặc cấu hình tương đương. Spring Web Services nhận payload XML và có thể dùng JAXB để ánh xạ request/response qua `@RequestPayload`, `@ResponsePayload` và `Jaxb2Marshaller`.

### 6.1. Vì sao Java `null` đôi khi chưa đủ?

Với một thuộc tính Java thông thường:

~~~java
private String nickname;
~~~

Giá trị `null` của thuộc tính không tự chứa thông tin phần tử trong XML **đã vắng mặt** hay **đã xuất hiện với `xsi:nil="true"`**. Tùy annotation, schema và công cụ sinh lớp:

- `@XmlElement(nillable = true)` có thể khiến marshaller ghi giá trị null dưới dạng `xsi:nil="true"`.
- Một thuộc tính có `minOccurs="0"` nhưng không nillable có thể bị bỏ khỏi XML khi null.
- Khi trường **vừa tùy chọn vừa nillable**, mã sinh JAXB thường có thể dùng `JAXBElement<T>` cùng `@XmlElementRef` để giữ trạng thái phần tử có xuất hiện hay không.

Đây là các kiểu ánh xạ **phụ thuộc phiên bản JAXB, cách sinh mã và binding customization**. Cần kiểm tra chính class đã được sinh trong dự án thay vì giả định mọi schema đều sinh đúng một kiểu getter.

### 6.2. Phân biệt trạng thái khi dùng `JAXBElement<String>`

Giả sử lớp Java được sinh có phương thức `getNickname()` trả về `JAXBElement<String>`. Trong endpoint, cách xử lý có thể là:

~~~java
JAXBElement<String> nickname = request.getNickname();

if (nickname == null) {
    // Phần tử vắng mặt: không cập nhật biệt danh.
} else if (nickname.isNil()) {
    // Phần tử hiện diện và xsi:nil=true: xóa biệt danh.
} else {
    String value = nickname.getValue();
    // value có thể bằng "", và đó là một giá trị được gửi có chủ ý.
    // Cập nhật biệt danh thành value.
}
~~~

Đây là ví dụ về **logic xử lý trạng thái**, không phải lớp endpoint hoàn chỉnh. Tên kiểu request và getter phải đối chiếu với mã sinh từ XSD. Ở các dự án dùng JAXB thế hệ cũ, package là `javax.xml.bind`; ở các dự án Jakarta, package tương ứng là `jakarta.xml.bind`. Ý nghĩa XML không thay đổi vì khác package Java.

Khi chủ động tạo yêu cầu ở SOAP client, cần phân biệt:

| Mong muốn ở dây XML | Ý tưởng ánh xạ với một trường kiểu `JAXBElement<String>` |
| --- | --- |
| Bỏ `nickname` | Không gắn phần tử vào request (wrapper `null`) |
| Gửi `<nickname/>` | Có wrapper và giá trị Java là `""` |
| Gửi `<nickname xsi:nil="true"/>` | Có wrapper được đánh dấu nil, thường với giá trị Java `null` |
| Gửi `<nickname>An</nickname>` | Có wrapper và giá trị `"An"` |

Đối với các lớp sinh bằng JAXB, nên dùng các phương thức tạo `JAXBElement` trong **`ObjectFactory`** do công cụ sinh ra, vì tên phần tử, namespace và scope của `QName` phải khớp với khai báo XSD. Trước khi tích hợp thực tế, marshal ra XML và xác nhận đúng hình dạng mong muốn; chỉ xem trạng thái object Java là chưa đủ.

### 6.3. Vị trí của Spring-WS

Một SOAP endpoint thường dùng `@Endpoint` và `@PayloadRoot` để chọn operation từ phần tử gốc trong SOAP Body. Sau khi chuyển payload sang Java, tầng dịch vụ quyết định áp dụng ba trạng thái ra sao. `WebServiceTemplate` cùng `Jaxb2Marshaller` có thể được dùng ở phía client để gửi object JAXB.

Điều quan trọng là **marshaller không định nghĩa quy tắc cập nhật dữ liệu**. Schema quyết định hình thức hợp lệ; JAXB biểu diễn các trạng thái thành object; endpoint/service quyết định nghiệp vụ. Cấu hình `PayloadValidatingInterceptor` có thể giúp kiểm tra request/response so với XSD, nhưng không nên giả định mọi ứng dụng Spring-WS tự động bật xác thực XSD.

## 7. Thiết kế hợp đồng cho API cập nhật

Khi định nghĩa một operation kiểu cập nhật một phần (partial update), có thể chọn mô hình sau nếu bên cung cấp và bên tiêu thụ cùng thống nhất:

| Trường hợp | Ví dụ payload `nickname` | Quy tắc nghiệp vụ minh họa |
| --- | --- | --- |
| Không truyền | Không có phần tử | Giữ nguyên dữ liệu |
| Truyền rỗng | `<nickname/>` | Ghi chuỗi rỗng |
| Truyền nil | `<nickname xsi:nil="true"/>` | Xóa dữ liệu (ghi `null`) |
| Truyền giá trị | `<nickname>An</nickname>` | Ghi `"An"` |

Quy tắc cần ghi cụ thể trong tài liệu hợp đồng, đặc biệt khi tích hợp với .NET, Java hoặc hệ thống ESB có cách biểu diễn optional/nillable khác nhau. Với trường không hỗ trợ xóa, nên tránh công bố `nillable="true"` nếu endpoint không có ý định chấp nhận nil. Nếu chuỗi rỗng bị cấm, hãy diễn đạt ràng buộc bằng facet XSD phù hợp (chẳng hạn `minLength`) và thông báo lỗi rõ ràng.

Một số nguyên tắc quan trọng:

1. **Không đồng nhất absent với nil** trong code cập nhật nếu nghiệp vụ cần phân biệt giữ nguyên và xóa.
2. **Không đồng nhất rỗng với nil** cho string, và không gửi thẻ rỗng cho kiểu số/ngày khi schema không cho phép.
3. **Không diễn giải namespace theo prefix chữ viết**: `c:nickname` và `x:nickname` là cùng tên mở rộng nếu cả `c` và `x` cùng trỏ một namespace URI.
4. **Không suy diễn hợp lệ từ XML well-formed**: cần kiểm tra với XSD chứa chính khai báo `minOccurs`, `nillable` và kiểu dữ liệu.
5. **Không thay đổi tùy tiện XSD/WSDL đang công bố**: đổi `minOccurs`, `nillable` hoặc quy ước nghiệp vụ có thể làm client cũ diễn giải payload khác đi.

## 8. Kiểm thử tương thích ở mức XML

Với Spring-WS, có thể dùng **`MockWebServiceClient`** để kiểm thử xử lý SOAP ở server và **`WebServiceTemplate`** hoặc kiểm thử marshal/unmarshal JAXB để kiểm tra client. Nên xác thực XML theo XSD trước khi kiểm tra nghiệp vụ, rồi so sánh namespace, trạng thái phần tử và phản hồi.

Một bộ kiểm thử tối thiểu gồm:

| Ca kiểm thử | Mục đích kiểm chứng |
| --- | --- |
| Không có phần tử optional | Được schema chấp nhận; endpoint hiểu là vắng mặt |
| Optional string rỗng | Được chấp nhận; không tự động đổi thành nil |
| Optional string nil | Được chấp nhận khi `nillable=true`; endpoint nhận diện nil |
| Optional string có nội dung | Giá trị được giữ nguyên sau unmarshalling |
| `xsi:nil="true"` khi `nillable=false` | Bộ xác thực XSD phải từ chối |
| Phần tử nil nhưng có nội dung ký tự/con | Bộ xác thực XSD phải từ chối |
| Kiểu `xs:int` dùng thẻ rỗng | Bộ xác thực XSD phải từ chối |
| Bỏ phần tử required | Bộ xác thực XSD phải từ chối |
| Marshal rồi unmarshal cả ba trạng thái | Không mất thông tin absent/empty/nil khi hợp đồng yêu cầu phân biệt |
| Gửi thông điệp từ client khác công nghệ | Phản hồi và trạng thái trên dây đúng với thỏa thuận WSDL/XSD |

Khi viết assertion, hãy kiểm tra **XML thực tế sau marshal**. Một kiểm tra chỉ so sánh `getNickname() == null` dễ bỏ sót sự khác biệt giữa phần tử vắng mặt và phần tử nil. Đồng thời, phép so sánh chuỗi XML thuần túy có thể báo sai vì thứ tự namespace declaration, tiền tố namespace hay cách viết thẻ rỗng khác nhau nhưng vẫn tương đương; nên kiểm tra theo cấu trúc XML và namespace.

## 9. Tự kiểm tra nhanh

Giả sử XSD có khai báo:

~~~xml
<xs:element name="note" type="xs:string"
            minOccurs="0" nillable="true"/>
~~~

Hãy thử trả lời trước khi xem đáp án:

1. Không gửi `note` có hợp lệ không?
2. `<note/>` và `<note xsi:nil="true"/>` có giống nhau không?
3. Thay `xs:string` bằng `xs:int` thì `<note/>` có còn hợp lệ không?
4. Nếu thay `minOccurs="0"` bằng `minOccurs="1"`, có được bỏ `note` không?
5. Nếu giữ `minOccurs="0"` nhưng đổi thành `nillable="false"`, có gửi `xsi:nil="true"` được không?

**Đáp án:** (1) Có; (2) Không — một cái là phần tử rỗng, một cái được đánh dấu nil; (3) Không, vì chuỗi rỗng không phải số nguyên; (4) Không, phần tử phải xuất hiện; (5) Không, vì schema cấm nil.

## 10. Ghi nhớ

- **Absent** là không có node phần tử trong XML; tính hợp lệ phụ thuộc `minOccurs`.
- **Empty** là phần tử có mặt nhưng không có nội dung; tính hợp lệ phụ thuộc kiểu và ràng buộc schema.
- **Nil** là phần tử có mặt với `xsi:nil="true"`; muốn hợp lệ phải có `nillable="true"` và phần tử không mang nội dung.
- Trong SOAP contract-first, **XSD/WSDL**, **JAXB** và **nghiệp vụ endpoint** đảm nhiệm các vai trò khác nhau. Chỉ một hợp đồng mô tả rõ ba trạng thái và phép thử trên XML thực tế mới giúp các hệ thống doanh nghiệp trao đổi dữ liệu ổn định.
