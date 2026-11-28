# Giữ WSDL, XSD, payload mẫu và kiểm thử tương thích làm mốc xác nhận

## 1. Vì sao cần một mốc xác nhận khi nâng cấp dịch vụ SOAP?

Trong hệ thống doanh nghiệp, một dịch vụ SOAP thường được nhiều ứng dụng gọi tới: hệ thống ERP, cổng đối tác, chương trình Java cũ, ứng dụng .NET hoặc công cụ tích hợp tạo mã client trực tiếp từ WSDL. Nâng cấp Java, Spring Framework, Spring Web Services, JAXB, máy chủ ứng dụng hay thư viện bảo mật có thể khiến server chạy thành công nhưng client hiện hữu vẫn bị lỗi.

Với **Spring Web Services (Spring-WS)**, cách tiếp cận *contract-first* đặt WSDL và XSD làm hợp đồng công khai, sau đó ánh xạ dữ liệu XML qua JAXB và xử lý tại endpoint. Trong một đợt nâng cấp hoặc di chuyển, bốn nhóm hiện vật cần được lưu thành **mốc xác nhận (baseline)**:

1. **WSDL đã công bố:** mô tả operation, message, binding, SOAPAction, service và port mà client nhìn thấy.
2. **XSD và toàn bộ schema phụ thuộc:** quy định namespace, tên phần tử, thứ tự, kiểu dữ liệu và ràng buộc của payload.
3. **Payload XML mẫu:** các request, response và SOAP Fault thực tế, có cả ca bình thường, biên và lỗi.
4. **Kiểm thử tương thích:** tái hiện hành vi của client cũ và kiểm tra cả cấu trúc XML lẫn ý nghĩa nghiệp vụ sau nâng cấp.

Chỉ so sánh việc endpoint trả HTTP 200 là chưa đủ: một phản hồi SOAP có thể trả HTTP 200 nhưng đổi namespace, thiếu phần tử hoặc trả trạng thái nghiệp vụ sai. Tương tự, cùng tên operation trên WSDL không bảo đảm hợp đồng tương thích nếu kiểu XSD đã thay đổi.

### Kết quả cần đạt

Sau bài này, người thực hiện có thể đóng băng một hợp đồng SOAP làm bản chuẩn, đánh giá thay đổi WSDL/XSD theo tác động lên consumer, xây bộ payload có thể chạy lặp lại và thiết lập điều kiện chấp nhận trước khi chuyển lưu lượng sang phiên bản Spring-WS mới.

## 2. Xác định phạm vi hợp đồng và chủ sở hữu

Hãy bắt đầu từ **giao diện mà consumer đang sử dụng**, không chỉ từ mã nguồn hiện tại. Một dự án có thể chứa XSD mới nhưng production vẫn xuất một WSDL cũ, hoặc WSDL sinh động từ `DefaultWsdl11Definition` có tên binding và đường dẫn khác so với file nguồn.

| Thành phần | Dữ liệu cần xác nhận trước nâng cấp | Lý do |
| --- | --- | --- |
| Địa chỉ công bố WSDL | URL WSDL thật, địa chỉ qua proxy/gateway, ngày thu thập | Đây là điểm client sinh mã hoặc truy vấn lại hợp đồng |
| WSDL và tập import | Tệp gốc, `wsdl:import`, `xsd:import`, `xsd:include` | Một tệp WSDL đơn lẻ có thể thiếu kiểu dữ liệu cần thiết |
| Danh tính XML | `targetNamespace`, QName của element/type/message/portType | Client JAXB/.NET thường ràng buộc theo QName |
| Giao thức | SOAP 1.1/1.2, document/literal, SOAPAction, HTTP headers | Thay đổi binding có thể làm dispatcher hoặc client từ chối |
| Thông điệp | Request, response, phần tử tùy chọn, attachment và fault | Định nghĩa và dữ liệu truyền thật phải tương ứng |
| Chính sách tích hợp | WS-Security, TLS, chữ ký, chứng chỉ, timeout, chính sách xác thực | Một hợp đồng XML đúng vẫn có thể thất bại ở lớp giao tiếp |
| Consumer | Danh sách ứng dụng, phiên bản client, người phụ trách, mức hỗ trợ | Dùng để chọn tổ hợp kiểm thử và xác nhận tác động |
| Hành vi nghiệp vụ | Ý nghĩa từng trạng thái và quy tắc xử lý lỗi | XML hợp lệ chưa chắc đáp ứng đúng kỳ vọng client |

Nếu có thể, lấy WSDL từ **endpoint production hoặc môi trường đối chứng đang phục vụ client thật** và ghi nhận cùng thời điểm lấy các XSD liên quan. Nếu hợp đồng được xuất động, đồng thời lưu bản WSDL đã trả cho client và nguồn XSD cấu hình server để đối chiếu.

Một cấu trúc lưu trữ tham khảo trong kho kiểm thử:

~~~text
contract-baseline/
  manifest.md
  wsdl/
    order-status-v1.wsdl
    order-status-v1.xsd
  samples/
    request-found.xml
    response-found.xml
    request-optional-absent.xml
    request-invalid-id.xml
    fault-not-found.xml
  expected/
    business-outcomes.yml
  reports/
    compatibility-matrix.md
~~~

Đây là ví dụ về cách tổ chức **hiện vật kiểm thử**; tên file và đường dẫn thực tế phải nhất quán với quy ước của từng dự án.

Trong `manifest.md`, nên lưu phiên bản ứng dụng nguồn, commit/build, ngày thu thập, URL, danh sách phụ thuộc được giải quyết, phiên bản SOAP, checksum SHA-256 và người xác nhận. Checksum giúp biết tệp đã bị thay đổi; nó **không thay thế** phân tích tác động của một khác biệt hợp đồng.

## 3. Ví dụ contract-first: hợp đồng Order Status

Giả sử một doanh nghiệp có operation `GetOrderStatus`. Các đoạn mã dưới đây là hợp đồng giả định dùng xuyên suốt bài học. Namespace `urn:example:order:v1` biểu thị **phiên bản trên wire**, không phải phiên bản thư viện Spring-WS.

### 3.1. XSD làm nguồn sự thật cho payload

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<xs:schema
    xmlns:xs="http://www.w3.org/2001/XMLSchema"
    xmlns:tns="urn:example:order:v1"
    targetNamespace="urn:example:order:v1"
    elementFormDefault="qualified">

    <xs:simpleType name="OrderStatus">
        <xs:restriction base="xs:string">
            <xs:enumeration value="PENDING"/>
            <xs:enumeration value="CONFIRMED"/>
            <xs:enumeration value="CANCELLED"/>
        </xs:restriction>
    </xs:simpleType>

    <xs:element name="GetOrderStatusRequest">
        <xs:complexType>
            <xs:sequence>
                <xs:element name="orderId" type="xs:string"/>
            </xs:sequence>
        </xs:complexType>
    </xs:element>

    <xs:element name="GetOrderStatusResponse">
        <xs:complexType>
            <xs:sequence>
                <xs:element name="orderId" type="xs:string"/>
                <xs:element name="status" type="tns:OrderStatus"/>
                <xs:element name="description"
                            type="xs:string"
                            minOccurs="0"
                            nillable="true"/>
            </xs:sequence>
        </xs:complexType>
    </xs:element>
</xs:schema>
~~~

Các điểm mốc cần giữ ở đây là QName của hai phần tử gốc, tập giá trị hợp lệ của `OrderStatus`, tính bắt buộc của `orderId` và `status`, thứ tự của `xs:sequence`, cùng sự khác biệt giữa trường `description` **vắng mặt** và trường có `xsi:nil="true"`.

Hai dạng `description` dưới đây đều hợp lệ theo XSD trên, nhưng phía consumer có thể diễn giải khác nhau:

~~~xml
<!-- Phần tử tùy chọn vắng mặt hoàn toàn -->
<ord:GetOrderStatusResponse xmlns:ord="urn:example:order:v1">
    <ord:orderId>ORD-1001</ord:orderId>
    <ord:status>CONFIRMED</ord:status>
</ord:GetOrderStatusResponse>

<!-- Phần tử xuất hiện nhưng mang giá trị nil -->
<ord:GetOrderStatusResponse
    xmlns:ord="urn:example:order:v1"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
    <ord:orderId>ORD-1001</ord:orderId>
    <ord:status>CONFIRMED</ord:status>
    <ord:description xsi:nil="true"/>
</ord:GetOrderStatusResponse>
~~~

Không được mặc nhiên xem việc đổi từ vắng mặt sang `nil` là an toàn. Một consumer có thể kiểm tra sự hiện diện của element, hoặc JAXB có thể ánh xạ hai trường hợp sang các trạng thái khác nhau tùy cấu hình sinh mã.

### 3.2. WSDL ràng buộc operation và giao thức

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<wsdl:definitions
    xmlns:wsdl="http://schemas.xmlsoap.org/wsdl/"
    xmlns:soap="http://schemas.xmlsoap.org/wsdl/soap/"
    xmlns:xs="http://www.w3.org/2001/XMLSchema"
    xmlns:tns="urn:example:order:v1"
    targetNamespace="urn:example:order:v1"
    name="OrderStatusService">

    <wsdl:types>
        <xs:schema>
            <xs:import namespace="urn:example:order:v1"
                       schemaLocation="order-status-v1.xsd"/>
        </xs:schema>
    </wsdl:types>

    <wsdl:message name="GetOrderStatusInput">
        <wsdl:part name="parameters" element="tns:GetOrderStatusRequest"/>
    </wsdl:message>
    <wsdl:message name="GetOrderStatusOutput">
        <wsdl:part name="parameters" element="tns:GetOrderStatusResponse"/>
    </wsdl:message>

    <wsdl:portType name="OrderStatusPortType">
        <wsdl:operation name="GetOrderStatus">
            <wsdl:input message="tns:GetOrderStatusInput"/>
            <wsdl:output message="tns:GetOrderStatusOutput"/>
        </wsdl:operation>
    </wsdl:portType>

    <wsdl:binding name="OrderStatusSoap11Binding"
                  type="tns:OrderStatusPortType">
        <soap:binding transport="http://schemas.xmlsoap.org/soap/http"
                      style="document"/>
        <wsdl:operation name="GetOrderStatus">
            <soap:operation
                soapAction="urn:example:order:v1/GetOrderStatus"/>
            <wsdl:input><soap:body use="literal"/></wsdl:input>
            <wsdl:output><soap:body use="literal"/></wsdl:output>
        </wsdl:operation>
    </wsdl:binding>

    <wsdl:service name="OrderStatusService">
        <wsdl:port name="OrderStatusSoap11Port"
                   binding="tns:OrderStatusSoap11Binding">
            <soap:address location="https://api.example.test/ws"/>
        </wsdl:port>
    </wsdl:service>
</wsdl:definitions>
~~~

WSDL này dùng SOAP 1.1, kiểu document/literal và operation đồng bộ có request/response. URL ví dụ không phải địa chỉ dịch vụ đang hoạt động. Trong môi trường thật, địa chỉ endpoint có thể thay đổi do proxy hoặc cấu hình triển khai; cần định nghĩa rõ **phần nào được phép đổi theo môi trường** và phần nào thuộc hợp đồng bắt buộc giữ nguyên.

Với Spring-WS, nếu hợp đồng cũ được phát hành dưới dạng WSDL tĩnh, có thể dùng `SimpleWsdl11Definition` để công bố tệp WSDL cố định. Nếu đang dùng `DefaultWsdl11Definition` để sinh WSDL từ XSD, sau nâng cấp phải truy xuất lại **WSDL được phát ra thực tế** rồi so sánh đầy đủ, vì đổi cách đặt tên port, binding, service hoặc SOAPAction cũng ảnh hưởng consumer. `MessageDispatcherServlet` có thể biến đổi địa chỉ WSDL theo request khi bật `transformWsdlLocations`; hãy kiểm tra URL qua đúng gateway/proxy và môi trường mà client sẽ truy cập.

### 3.3. Payload mẫu trên wire

SOAP 1.1 request:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<env:Envelope
    xmlns:env="http://schemas.xmlsoap.org/soap/envelope/"
    xmlns:ord="urn:example:order:v1">
    <env:Header/>
    <env:Body>
        <ord:GetOrderStatusRequest>
            <ord:orderId>ORD-1001</ord:orderId>
        </ord:GetOrderStatusRequest>
    </env:Body>
</env:Envelope>
~~~

Phản hồi thành công tương ứng:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<env:Envelope
    xmlns:env="http://schemas.xmlsoap.org/soap/envelope/"
    xmlns:ord="urn:example:order:v1">
    <env:Body>
        <ord:GetOrderStatusResponse>
            <ord:orderId>ORD-1001</ord:orderId>
            <ord:status>CONFIRMED</ord:status>
            <ord:description>Đơn đã được xác nhận</ord:description>
        </ord:GetOrderStatusResponse>
    </env:Body>
</env:Envelope>
~~~

Đối với SOAP 1.1 qua HTTP, kiểm thử transport cần lưu cả `Content-Type: text/xml; charset=utf-8` và giá trị `SOAPAction` mà client thực tế gửi. Ví dụ cURL để tái hiện request trên:

~~~bash
curl --request POST "https://api.example.test/ws" \
  --header 'Content-Type: text/xml; charset=utf-8' \
  --header 'SOAPAction: "urn:example:order:v1/GetOrderStatus"' \
  --data-binary @request-found.xml
~~~

Kiểm thử bằng `MockWebServiceClient` giúp kiểm tra dispatch và payload trong application context nhưng không tự động bảo đảm hành vi HTTP, TLS, proxy, các header hoặc khả năng kết nối của client sinh mã. Cần thêm kiểm thử tích hợp qua mạng.

## 4. Đóng băng WSDL/XSD như một hợp đồng có phiên bản

### 4.1. Lấy trọn bộ tài liệu XML

Quy trình đề xuất:

1. Truy xuất WSDL ở địa chỉ client đang sử dụng, ghi ngày giờ, môi trường và phiên bản dịch vụ.
2. Giải quyết mọi `wsdl:import`, `xsd:import`, `xsd:include` và `xsd:redefine` nếu có; lưu nguyên văn các tệp và sơ đồ phụ thuộc.
3. Kiểm tra tất cả schema tham chiếu đã truy cập được trong môi trường kiểm thử cô lập, tránh phụ thuộc URL ngoài không ổn định.
4. Ghi checksum và khóa phiên bản baseline trong quản lý phiên bản; yêu cầu review khi cập nhật baseline.
5. Thu payload từ test case/consumer đã được phê duyệt và ẩn mã định danh, token, dữ liệu nhạy cảm trước khi đưa vào kho.
6. Sinh hoặc biên dịch lại client bằng chính WSDL baseline để biết nó còn đủ để tạo client độc lập.

Không tự động ghi đè baseline mỗi khi pipeline chạy. Nếu luôn lấy WSDL/XSD mới từ server vừa build rồi dùng chúng làm mốc, một thay đổi phá vỡ hợp đồng có thể vô tình được coi là hợp lệ.

### 4.2. Những thay đổi cần soi đến cấp QName

| Thay đổi | Ảnh hưởng có thể xảy ra | Cách xử lý |
| --- | --- | --- |
| Đổi `targetNamespace` hoặc QName element | Client cũ không marshal/unmarshal hoặc không match `@PayloadRoot` | Xem là thay đổi hợp đồng lớn; cân nhắc namespace/operation phiên bản mới |
| Đổi operation, message, portType, binding hoặc tên part | Mã proxy sinh từ WSDL cũ có thể không còn gọi được | So sánh WSDL và chạy lại client cũ |
| Đổi SOAP 1.1 sang SOAP 1.2 | Khác namespace Envelope, MIME type và cách SOAPAction được truyền | Duy trì binding cũ hoặc nâng cấp client có kế hoạch |
| Đổi `document/literal` sang kiểu binding khác | Cấu trúc trên wire và mã sinh thay đổi | Giữ binding hiện hành cho consumer cũ |
| Tăng `minOccurs` từ 0 lên 1 | Request cũ thiếu trường trở thành không hợp lệ | Tránh áp dụng trên phiên bản hợp đồng cũ |
| Giảm `maxOccurs` hoặc đổi thứ tự `xs:sequence` | XML hợp lệ trước đây có thể bị từ chối | Giữ ràng buộc cũ hoặc phiên bản hóa |
| Đổi type/facet: length, pattern, decimal, enum | Dữ liệu hợp lệ trước đây có thể thành lỗi; client JAXB bị ảnh hưởng | Kiểm thử ca biên và so sánh giới hạn |
| Thêm trường tùy chọn vào response | Consumer strict validation hoặc mã sinh cũ có thể không hiểu trường mới | Thử trên client cũ trước khi xem là tương thích |
| Đổi Fault detail hoặc faultcode | Consumer có thể phân loại lỗi sai | Lưu ca SOAP Fault và xác nhận quy tắc xử lý |
| Đổi địa chỉ `soap:address` | Khả năng kết nối phụ thuộc cấu hình client, DNS và gateway | Đặt trong danh sách ngoại lệ theo môi trường nếu được chấp thuận |

**Tương thích ngược** thường có nghĩa là client cũ tiếp tục hoạt động với server mới. **Tương thích xuôi** có thể được dùng để chỉ client mới làm việc với server cũ; hai chiều cần được kiểm tra độc lập. Một thay đổi XML trông như “chỉ thêm trường tùy chọn” không mặc nhiên an toàn vì parser, generated client và quy tắc nghiệp vụ của mỗi consumer khác nhau.

### 4.3. So sánh đúng ngữ nghĩa, không chỉ byte

Nên thực hiện **hai lớp so sánh**:

- **So sánh nguyên bản:** checksum và diff chỉ ra thay đổi thực sự của WSDL/XSD.
- **So sánh cấu trúc có nhận biết XML namespace:** kiểm tra QName, operation, message, binding, SOAPAction, các import và ràng buộc XSD. Chuẩn hóa những khác biệt được duyệt như `soap:address` thay đổi giữa staging và production.

XML cho phép khác prefix hoặc cách xuống dòng mà vẫn trỏ tới cùng QName; vì vậy diff chuỗi thuần có thể báo động giả. Ngược lại, chuẩn hóa quá tay, ví dụ sắp xếp lại phần tử trong `xs:sequence`, có thể che giấu thay đổi phá vỡ hợp đồng. XML canonicalization giúp giảm một số khác biệt cú pháp, nhưng **không đủ** để quyết định tương thích WSDL/XSD, đặc biệt khi khác prefix, schema import và ý nghĩa ràng buộc.

## 5. Thiết kế bộ payload mẫu đủ sức phát hiện lỗi

Mỗi mẫu nên đi kèm `caseId`, operation, phiên bản hợp đồng, điều kiện đầu vào, kết quả kỳ vọng và nguồn xác nhận. Nên tạo dữ liệu kiểm thử ổn định (seed database, stub service phụ thuộc hoặc fixture) để một request có cùng kết quả sau mỗi lần chạy.

| Nhóm ca | Ví dụ | Điều cần khẳng định |
| --- | --- | --- |
| Thành công điển hình | `ORD-1001` có trạng thái `CONFIRMED` | Đúng QName, thứ tự, giá trị và ánh xạ JAXB |
| Phần tử tùy chọn | `description` vắng mặt; rỗng; `xsi:nil="true"` | Phân biệt các biểu diễn mà hợp đồng cho phép |
| Đầu vào biên | ID dài nhất được phép, chuỗi Unicode, khoảng trắng, ký tự XML phải escape | Không sai encoding, validation hoặc xử lý giá trị |
| Dữ liệu lặp | Danh sách item có 0/1/n phần tử nếu XSD cho phép | Giữ `minOccurs`, `maxOccurs` và thứ tự |
| Sai schema | Thiếu `orderId`, sai namespace, sai kiểu dữ liệu | Từ chối có kiểm soát; không trả response thành công giả |
| Lỗi nghiệp vụ | Không tìm thấy đơn, quyền truy cập không đủ | Đúng SOAP Fault, mã lỗi, detail và hành vi retry |
| Tích hợp bảo mật | Chữ ký đúng/sai, token hết hạn, chứng chỉ hết hạn | Interceptor xử lý đúng và không bỏ qua kiểm tra |
| Hành vi vận hành | Timeout, request trùng, gọi đồng thời, dependency lỗi | Đúng cam kết idempotency, timeout và phân loại lỗi |

Không phải module nào cũng có attachment MTOM, WS-Addressing, WS-ReliableMessaging hoặc WS-Security. Chỉ thêm các ca này khi chúng thực sự nằm trong hợp đồng/tích hợp hiện hành; nếu có, phải giữ cả header, attachment và chính sách liên quan.

### SOAP Fault là một phần của baseline

Ví dụ khung SOAP 1.1 Fault:

~~~xml
<env:Envelope xmlns:env="http://schemas.xmlsoap.org/soap/envelope/">
    <env:Body>
        <env:Fault>
            <faultcode>env:Client</faultcode>
            <faultstring>Invalid order identifier</faultstring>
            <detail>
                <error xmlns="urn:example:errors:v1">
                    <code>INVALID_ORDER_ID</code>
                </error>
            </detail>
        </env:Fault>
    </env:Body>
</env:Envelope>
~~~

Đây chỉ là **ví dụ minh họa**: SOAP Fault thực tế phải tuân theo policy, mapping exception và fault contract đang công bố. Trong Spring-WS, kiểm tra các `SoapFaultMappingExceptionResolver`, `@SoapFault`, interceptor và cơ chế tự tạo `SoapFault` nếu dự án sử dụng. Cùng một exception sau nâng cấp có thể bị ánh xạ thành `Server` thay cho `Client`, hoặc mất `detail`; consumer thường dựa vào những giá trị này để retry hay hiển thị thông báo.

Cần lưu response fault trên wire kèm HTTP status theo thực tế triển khai; SOAP Fault không đồng nghĩa với cùng mã HTTP cho mọi phiên bản SOAP và mọi cấu hình transport.

## 6. Xây các tầng kiểm thử tương thích

Một bộ kiểm thử đáng tin cậy thường chia làm bốn tầng, từ nhanh đến sát thực tế:

### Tầng A — Kiểm tra tài liệu hợp đồng

- Mọi WSDL/XSD đều well-formed và resolve được tập import/include.
- WSDL được phát bởi phiên bản mới so với baseline theo quy tắc diff đã duyệt.
- Các QName, operation, binding, SOAPAction, schema constraint quan trọng được giữ nguyên.
- Có thể dùng hợp đồng baseline để sinh client theo toolchain thật của consumer (nếu doanh nghiệp sử dụng JAXB/XJC, JAX-WS `wsimport`, Apache CXF hoặc .NET tooling).

Đặc biệt với di chuyển từ `javax.xml.bind` sang `jakarta.xml.bind`, việc tên class hoặc package Java thay đổi là vấn đề triển khai; điều kiện tương thích bên ngoài vẫn phải kiểm tra **XML thực sự phát ra và nhận vào**. Nếu giữ cùng QName, serializer đúng cấu trúc và hành vi đúng, phần mã Java có thể được thay thế mà không buộc client từ xa đổi theo.

### Tầng B — Kiểm tra schema và payload

Dùng XML Schema validator để xác nhận các request/response hợp lệ. Ví dụ Java tiêu chuẩn:

~~~java
import java.io.File;
import javax.xml.XMLConstants;
import javax.xml.validation.Schema;
import javax.xml.validation.SchemaFactory;
import javax.xml.validation.Validator;

SchemaFactory factory =
        SchemaFactory.newInstance(XMLConstants.W3C_XML_SCHEMA_NS_URI);
Schema schema = factory.newSchema(new File("contract-baseline/wsdl/order-status-v1.xsd"));
Validator validator = schema.newValidator();

// Truyền phần tử payload gốc của SOAP Body, không truyền cả Envelope
validator.validate(new javax.xml.transform.stream.StreamSource(
        new File("contract-baseline/samples/response-payload.xml")));
~~~

File `response-payload.xml` trong ví dụ phải chứa phần tử `GetOrderStatusResponse` làm root. Nếu fixture chứa cả SOAP Envelope thì cần tách `SOAP Body` trước, hoặc dùng matcher/validator chuyên dụng biết cấu trúc SOAP. Validator chỉ xác nhận cấu trúc; vẫn phải so sánh giá trị nghiệp vụ, QName chính xác và các trường cần giữ ổn định.

Đối với mẫu sai schema, test cần **kỳ vọng validation thất bại**; không đưa mọi fixture vào cùng một vòng “phải hợp lệ”.

### Tầng C — Kiểm tra dispatch và endpoint Spring-WS

Một endpoint contract-first thường ánh xạ theo namespace và local part:

~~~java
@Endpoint
public class OrderStatusEndpoint {
    private static final String NS = "urn:example:order:v1";

    @PayloadRoot(namespace = NS, localPart = "GetOrderStatusRequest")
    @ResponsePayload
    public GetOrderStatusResponse getStatus(
            @RequestPayload GetOrderStatusRequest request) {
        // Gọi nghiệp vụ và trả object JAXB đã được sinh từ XSD.
        return orderStatusService.lookup(request.getOrderId());
    }
}
~~~

Đoạn mã giả định `GetOrderStatusRequest` và `GetOrderStatusResponse` là các kiểu JAXB phù hợp được sinh từ XSD; hình thức wrapper hoặc `JAXBElement` thực tế phụ thuộc cách sinh mã. Mấu chốt là **QName request được xử lý** và **QName response được serialize** phải khớp baseline.

Với Spring-WS Test, có thể dùng `MockWebServiceClient` để gửi phần tử payload đến application context và xác nhận response không phải Fault, hợp lệ theo schema:

~~~java
import static org.springframework.ws.test.client.RequestCreators.withPayload;
import static org.springframework.ws.test.client.ResponseMatchers.noFault;
import static org.springframework.ws.test.client.ResponseMatchers.validPayload;

MockWebServiceClient client = MockWebServiceClient.createClient(applicationContext);

Source request = new StreamSource(
        new StringReader(
            "<ord:GetOrderStatusRequest xmlns:ord='urn:example:order:v1'>"
          + "<ord:orderId>ORD-1001</ord:orderId>"
          + "</ord:GetOrderStatusRequest>"));

client.sendRequest(withPayload(request))
      .andExpect(noFault())
      .andExpect(validPayload(
          new ClassPathResource("contract/order-status-v1.xsd")));
~~~

Các `import` cần thiết và khởi tạo `applicationContext` được lược bỏ để làm nổi bật ý tưởng kiểm thử; đây là đoạn minh họa trong lớp test Spring. Nên bổ sung matcher XPath có nhận biết namespace hoặc so sánh nội dung response theo expected fixture để xác nhận `status=CONFIRMED`, không chỉ xác nhận schema hợp lệ.

Bên cạnh ca thành công, hãy kiểm tra fault resolver, interceptor kiểm tra XSD, logging, xác thực và lỗi unmarshalling. Với JAXB, lỗi thường xuất hiện khi thay đổi `@XmlRootElement`, `@XmlElement`, `Jaxb2Marshaller`, context path hoặc package namespace.

### Tầng D — Kiểm tra qua HTTP với client cũ

Tạo một server mới trong môi trường thử nghiệm và chạy **bản client đã phát hành trước nâng cấp**, giữ nguyên stub/proxy và cấu hình của phiên bản cũ càng nhiều càng tốt. Kiểm tra:

- Client kết nối đúng endpoint, TLS và chính sách xác thực; nếu có chữ ký WS-Security, kiểm tra cả dữ liệu đã ký.
- Request được dispatch đúng SOAPAction, namespace và local part.
- Response deserialize thành công, giữ đúng kiểu dữ liệu và giá trị.
- Fault đi qua client và được phân loại theo nghiệp vụ đúng như trước.
- Mã HTTP, Content-Type, charset, timeout và phản hồi qua gateway đúng cấu hình đã cam kết.

Nếu dự án sử dụng cả SOAP 1.1 và SOAP 1.2 thì xây test riêng cho từng binding; không lấy kết quả SOAP 1.1 để suy ra SOAP 1.2.

## 7. Ma trận xác nhận trước và sau nâng cấp

Nên phân biệt hai trục: **phiên bản server** và **phiên bản client**. Ví dụ:

| Client | Server | Mục đích | Kỳ vọng |
| --- | --- | --- | --- |
| Cũ | Cũ | Đối chứng, xác nhận fixture có thể chạy | PASS theo hợp đồng đang triển khai |
| Cũ | Mới | Kiểm tra tương thích ngược — đường quan trọng nhất | PASS với các use case đã cam kết hỗ trợ |
| Mới | Mới | Kiểm tra hành vi của phiên bản mới | PASS theo hợp đồng mục tiêu |
| Mới | Cũ | Kiểm tra tương thích xuôi nếu cần rollout lệch phiên bản | PASS nếu tuyên bố hỗ trợ; nếu không, ghi rõ giới hạn |

Mỗi ô cần chạy các nhóm case phù hợp: hợp lệ, thiếu trường tùy chọn, fault, bảo mật và dữ liệu biên. Đừng biến ma trận thành một dấu “PASS” duy nhất: giữ danh sách case, phiên bản client, build server, WSDL hash, thời gian chạy và log lỗi có thể truy vết.

Nếu server cũ không còn vận hành, có thể dùng môi trường đối chứng đã đóng băng hoặc stub được xác nhận từ dữ liệu cũ, nhưng phải ghi rõ mức độ đại diện. Stub chỉ phản hồi theo mẫu không chứng minh được mọi hành vi của hệ thống thật.

### Cách xử lý khi test thất bại

**Tình huống:** client cũ gửi `GetOrderStatusRequest`, server mới trả SOAP Fault “No endpoint mapping found”.

1. So sánh QName payload request thực tế, kể cả namespace.
2. Đối chiếu `@PayloadRoot` và cấu hình endpoint mapping sau nâng cấp.
3. Kiểm tra SOAP version, servlet mapping, đường URL và nội dung SOAP Body.
4. Sửa mapping/cấu hình hoặc hợp đồng theo đúng baseline; chạy lại ca này và các ca cùng operation.

**Tình huống:** response XSD hợp lệ nhưng consumer cũ báo lỗi enum.

1. So sánh giá trị enum trong response với baseline, không chỉ kiểu chuỗi.
2. Kiểm tra JAXB và mapper nghiệp vụ có thêm trạng thái mà client cũ chưa biết.
3. Khôi phục giá trị được hỗ trợ trong phiên bản cũ hoặc công bố operation/namespace có phiên bản mới.
4. Thêm ca này thành regression fixture để lần sau phát hiện tự động.

**Tình huống:** WSDL diff chỉ phát hiện thay đổi `soap:address`.

1. Xác nhận khác biệt chỉ là hostname/path được cho phép theo môi trường.
2. Dùng chính URL gateway người dùng cuối truy cập để kiểm tra khả năng tải WSDL và import.
3. Chỉ miễn trừ khác biệt đã định danh; không bỏ qua toàn bộ `wsdl:service`.

## 8. Kiểm tra JAXB, SOAP Fault và bảo mật khi di chuyển nền tảng

Spring-WS kết hợp với JAXB để marshal/unmarshal XML tại biên của dịch vụ. Chuyển JDK, Spring-WS hoặc Jakarta XML Binding có thể làm thay đổi class Java sinh ra và cách đăng ký JAXB context. Để giữ hợp đồng:

- Sinh mã JAXB từ XSD baseline khi kiểm thử client cũ, và từ XSD mục tiêu cho phiên bản mới nếu thật sự cần đổi hợp đồng.
- Kiểm tra QName gốc, `elementFormDefault`, namespace, thứ tự, các enum, `BigDecimal`, ngày giờ và giá trị `null` được marshal thành gì.
- Không mặc định object equality tương đương XML equality. Kiểm tra XML trên wire; ví dụ số thập phân `10.0` và `10.00` có thể bằng nhau về giá trị nhưng consumer có thể kỳ vọng biểu diễn cụ thể.
- Khi thay cấu hình `Jaxb2Marshaller`, kiểm tra `contextPath`, `classesToBeBound`, `packagesToScan` và adapters đang dùng.
- Giữ nguyên mapping exception sang SOAP Fault, bao gồm code/subcode theo phiên bản SOAP, faultstring/reason và `detail`.

Nếu tích hợp có **WS-Security**, baseline cần đại diện cho chữ ký XML, phần được ký, timestamp, UsernameToken (nếu có), bảo vệ chống replay, thuật toán và truststore/keystore. Việc đổi chứng chỉ có thể hợp lệ theo kế hoạch vận hành nhưng phải kiểm tra chuỗi tin cậy và tương tác với client cũ. Đừng lưu private key, mật khẩu, token thật hay chữ ký từ production chưa ẩn dữ liệu vào kho fixture.

Ở mức XML Security, cần xác nhận parser được cấu hình an toàn và không tải external entities ngoài ý muốn. Các thay đổi an toàn parser có thể làm một payload cũ bị từ chối; xác định payload đó có hợp lệ và được phép theo chính sách hiện hành hay không trước khi quyết định thay đổi ràng buộc.

## 9. Đưa các mốc xác nhận vào pipeline CI/CD

Pipeline nên dùng **baseline đã được phê duyệt** từ kho nguồn hoặc kho hiện vật bất biến. Một chuỗi kiểm tra điển hình:

~~~mermaid
flowchart TD
    A[Baseline WSDL, XSD, payload và kỳ vọng] --> B[Build dịch vụ Spring-WS mới]
    B --> C[Kiểm tra WSDL và XSD]
    C --> D[Schema validation và regression payload]
    D --> E[Test Spring-WS endpoint và SOAP Fault]
    E --> F[Test HTTP với client cũ]
    F --> G{Tất cả cổng bắt buộc PASS?}
    G -->|Có| H[Phê duyệt release theo quy trình]
    G -->|Không| I[Ghi diff, log và chặn release]
~~~

Các bước tối thiểu nên tạo báo cáo có thể đọc lại:

1. **Contract diff report:** chỉ rõ changed XPath/QName, binding, SOAPAction, schema constraint và danh sách ngoại lệ được duyệt.
2. **Fixture report:** case nào chạy, kết quả XML validation, assertion nghiệp vụ và expected/actual khi lỗi.
3. **Consumer report:** phiên bản client cũ nào chạy thành công, môi trường, HTTP/SOAP version và chứng chỉ thử nghiệm.
4. **Traceability:** commit/build server, baseline ID/checksum, phiên bản JDK/Spring-WS/JAXB, thời gian và người duyệt.

Có thể phân cấp điều kiện CI:

| Cổng | Điều kiện đạt | Khi không đạt |
| --- | --- | --- |
| Contract integrity | WSDL/XSD đọc được; các import đầy đủ; diff đã phân loại | Dừng kiểm tra tương thích, báo lỗi hợp đồng |
| Schema & serialization | Mẫu hợp lệ qua validation; mẫu sai bị từ chối; QName đúng | Chặn bản build và chỉ ra XML/đường dẫn lỗi |
| Endpoint & fault | Operation, response, Fault và interceptor theo expected fixture | Chặn bản build hoặc chuyển QA xử lý theo mức ảnh hưởng |
| Consumer compatibility | Bộ client cũ trong phạm vi hỗ trợ chạy đạt | Chặn triển khai vào đối tượng consumer liên quan |
| Security & transport | TLS, SOAPAction, HTTP headers, policy và chữ ký theo yêu cầu | Chặn rollout nếu vi phạm ràng buộc tích hợp |

Không nên đặt cơ chế tự cập nhật expected response khi test thất bại. Thay đổi baseline phải là quyết định có review, kèm lý do và phân tích consumer bị ảnh hưởng.

## 10. Khi nào có thể cập nhật hợp đồng?

Đóng băng baseline **không có nghĩa là cấm thay đổi WSDL/XSD mãi mãi**. Nó giúp phân biệt một thay đổi dự kiến với lỗi hồi quy. Khi cần thêm dữ liệu hoặc thay ngữ nghĩa:

1. Lập danh sách consumer, phiên bản và khả năng chấp nhận thay đổi.
2. Đánh giá xem sửa đổi có an toàn với client hiện hữu qua test thực tế hay không; không chỉ dựa vào suy đoán từ XSD.
3. Nếu không thể bảo đảm tương thích, giữ endpoint/binding/namespace cũ trong thời gian chuyển tiếp và xuất phiên bản hợp đồng mới có đường di chuyển rõ ràng.
4. Phát hành WSDL/XSD mới cùng sample và test tương ứng; thiết lập ngày kết thúc hỗ trợ phiên bản cũ theo thỏa thuận.
5. Chỉ tạo baseline mới sau review và xác nhận tác động. Giữ baseline cũ để hồi quy cho đến khi mọi consumer liên quan đã chuyển đổi.

Ví dụ, thêm giá trị `ON_HOLD` vào enum `OrderStatus` có thể khiến client JAXB cũ gặp trạng thái không nhận ra. Dù XSD mới hợp lệ, thay đổi này vẫn cần kiểm tra consumer hoặc có kế hoạch versioning. Tương tự, thêm phần tử mới cuối `xs:sequence` với `minOccurs=0` không bảo đảm client validate theo XSD cũ sẽ chấp nhận response có phần tử mới.

## 11. Tình huống thực tế: nâng cấp Spring-WS nhưng giữ consumer ERP cũ

**Bối cảnh:** một ERP dùng client Java được sinh từ WSDL v1 nhiều năm trước. Nhóm dịch vụ nâng cấp Spring-WS, JAXB và JDK, đồng thời chuyển dịch vụ sau reverse proxy mới.

**Mốc trước thay đổi:** thu WSDL thực tế, các XSD import, request `GetOrderStatus` từ ERP, response với ba trạng thái đã hỗ trợ, Fault cho ID sai và trường hợp thiếu quyền. Ghi chính xác SOAP 1.1, SOAPAction, namespace, thời gian và chứng chỉ thử nghiệm.

**Thực hiện:** cấu hình endpoint mới để xử lý QName v1; xác nhận WSDL mới chỉ thay hostname được duyệt. Chạy schema test, request/response fixtures, SOAP Fault và client ERP đã biên dịch từ trước qua môi trường staging. Dùng dữ liệu seed để response `ORD-1001` giữ `CONFIRMED`.

**Sự cố được phát hiện:** sau nâng cấp JAXB, phản hồi bắt đầu xuất `<description xsi:nil="true"/>` thay vì bỏ element. XSD vẫn cho phép cả hai, nhưng ERP phân biệt “không có mô tả” với “mô tả có giá trị null”. Kiểm thử nội dung payload thất bại, dù kiểm thử schema đã đạt.

**Cách sửa:** điều chỉnh mapping/serialization để giữ hành vi đã cam kết, bổ sung hai fixtures cho trường hợp vắng mặt và nil, sau đó chạy lại test bằng ERP client thật. Khi cả payload, Fault, HTTP và bảo mật đạt, mới cho phép chuyển lưu lượng theo kế hoạch.

Bài học của ca này là **bản hợp đồng + mẫu wire + kiểm thử consumer** bổ sung cho nhau. Tệp XSD chỉ nói điều gì hợp lệ về mặt cấu trúc; fixture và assertion xác nhận điều gì thực tế được hỗ trợ.

## 12. Tiêu chí hoàn thành một đợt nâng cấp

Trước khi xác nhận tương thích, người phụ trách có thể dùng checklist sau:

- [ ] Đã lưu WSDL đúng bản consumer đang sử dụng và toàn bộ XSD/import phụ thuộc.
- [ ] Đã ghi phiên bản, nguồn lấy, checksum và các ngoại lệ môi trường được cho phép.
- [ ] Đã so sánh QName, operation, SOAP version, binding, SOAPAction và mọi ràng buộc XSD quan trọng.
- [ ] Đã có payload request/response/Fault đại diện cho hành vi hiện hành và các trường hợp biên.
- [ ] Đã kiểm tra XML schema **và** assertion giá trị nghiệp vụ, bao gồm optional/nil/enum.
- [ ] Đã kiểm tra endpoint mapping, JAXB marshalling/unmarshalling và fault resolver của Spring-WS.
- [ ] Đã chạy client cũ thực tế qua HTTP/TLS/gateway với đủ tình huống trong phạm vi hỗ trợ.
- [ ] Đã kiểm tra WS-Security, chứng chỉ và interceptor nếu chúng thuộc hợp đồng triển khai.
- [ ] Mọi khác biệt được phê duyệt, có lý do, consumer bị ảnh hưởng và bài regression đi kèm.
- [ ] CI lưu kết quả đủ để truy nguyên build, fixture, baseline và quyết định phát hành.
- [ ] Có phương án rollback/duy trì endpoint cũ nếu thử nghiệm canary phát hiện incompatibility.

**Tiêu chí quyết định:** chỉ coi đợt nâng cấp là giữ tương thích khi các ca kiểm thử dựa trên baseline đã duyệt đạt trên phiên bản server mới, đặc biệt là **client đã phát hành trước nâng cấp**. Nếu hợp đồng được chủ động thay đổi, kết quả phải được ghi nhận là **phiên bản hợp đồng mới có kế hoạch di chuyển consumer**, không gắn nhãn “tương thích” chỉ vì server mới tự kiểm thử thành công.
