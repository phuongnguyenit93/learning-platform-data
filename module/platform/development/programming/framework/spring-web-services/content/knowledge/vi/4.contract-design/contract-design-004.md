# Document/literal wrapped và bare: cấu trúc thông điệp và lựa chọn

> **Chương:** Thiết kế hợp đồng  
> **Phạm vi:** Thiết kế XSD/WSDL cho SOAP theo hướng contract-first với Spring Web Services (Spring-WS), hiểu cách JAX-WS và Apache CXF ánh xạ thông điệp sang Java, đồng thời bảo vệ tính tương thích khi tích hợp hệ thống doanh nghiệp.

## 1. Mục tiêu của bài học

Sau bài này, bạn có thể:

1. Phân biệt **document/literal** với **document/literal wrapped** và **document/literal bare**.
2. Đọc WSDL 1.1 để xác định XML nào thực sự nằm trong SOAP Body, thay vì đoán từ tên phương thức Java.
3. Tự thiết kế XSD, `wsdl:message`, `wsdl:portType` và `wsdl:binding` cho cả hai phương án.
4. Giải thích vì sao Spring-WS định tuyến theo phần tử payload, còn client JAX-WS/CXF có thể trình bày giao diện dưới dạng tham số Java.
5. Chọn kiểu hợp đồng hợp lý và kiểm thử tương thích, SOAP Fault, validation và WS-Security trước khi đưa vào tích hợp.

Một tiền đề xuyên suốt: **WSDL/XSD và XML trao đổi trên mạng là hợp đồng giữa hai hệ thống.** Java class, JAXB model, tên phương thức, endpoint adapter hay proxy chỉ là cách hiện thực hợp đồng đó.

## 2. Ba khái niệm dễ bị đặt nhầm cùng một cấp

Trong WSDL 1.1, SOAP binding quy định `style` và `use`; **wrapped/bare là cách tổ chức tài liệu và một quy ước ánh xạ**, không phải hai giá trị khác nhau của `soap:binding/@style`.

| Khái niệm | Ý nghĩa | Biểu hiện trong WSDL/SOAP |
|---|---|---|
| **Document style** | SOAP Body chứa các phần tử XML đại diện cho tài liệu; contract được xác định qua schema element | `<soap:binding style="document">` |
| **Literal use** | Nội dung SOAP được serialize theo XML Schema, không dùng cơ chế SOAP encoding cũ | `<soap:body use="literal">` |
| **Document/literal wrapped** | Một phần tử *wrapper* trong Body đại diện cho operation; các phần tử con thường ánh xạ thành tham số | XML root thường cùng local name với operation, response thường có hậu tố `Response` |
| **Document/literal bare** | Một phần tử tài liệu nghiệp vụ trực tiếp là payload của Body, không thêm operation wrapper theo quy ước wrapped | XML root thường là `GetOrderStatusRequest` hoặc một tên message nghiệp vụ riêng |

Sơ đồ tư duy:

~~~mermaid
flowchart TD
    A["WSDL 1.1 SOAP binding"] --> B["style = document"]
    B --> C["use = literal"]
    C --> D{"Hình dạng phần tử XML trong Body"}
    D --> E["Wrapped: getOrderStatus → orderId"]
    D --> F["Bare: GetOrderStatusRequest → orderId"]
    E --> G["Cùng là document/literal"]
    F --> G
~~~

Không được nhầm **SOAP Envelope** với **operation wrapper**. Mọi request SOAP đều có `Envelope` và `Body`; từ *wrapped* ở đây nói về phần tử XML **bên trong** Body, không phải sự tồn tại của Envelope.

Ví dụ cùng truy vấn trạng thái đơn hàng `ORD-1001`:

~~~text
SOAP Envelope
└── SOAP Body
    └── getOrderStatus                  ← wrapped: tên operation
        └── orderId = ORD-1001
~~~

~~~text
SOAP Envelope
└── SOAP Body
    └── GetOrderStatusRequest          ← bare: tên tài liệu nghiệp vụ
        └── orderId = ORD-1001
~~~

Hai thiết kế có thể phục vụ cùng use case, nhưng **khác QName của payload**; một client gửi request theo thiết kế này không tự nhiên tương thích với endpoint đang đợi thiết kế kia.

## 3. Các thành phần WSDL quyết định hình dạng thông điệp

Để hiểu wire format, đọc contract theo thứ tự:

1. **`wsdl:types` / XSD**: khai báo global XML element, namespace, kiểu và thứ tự các field.
2. **`wsdl:message`**: định nghĩa các `wsdl:part` cho input/output; với document/literal phổ biến và tương thích cao, mỗi SOAP Body có **một part** tham chiếu đến **global element** bằng thuộc tính `element`.
3. **`wsdl:portType`**: khai báo tên operation và nối các message input/output (cùng các fault nếu có).
4. **`wsdl:binding`**: chọn SOAP binding, `style="document"`, `use="literal"`, `soapAction` và các khai báo binding liên quan.
5. **`wsdl:service` / `wsdl:port`**: gắn binding với địa chỉ endpoint cụ thể.

Đặc biệt:

~~~xml
<wsdl:message name="GetOrderStatusInput">
  <wsdl:part name="parameters" element="tns:getOrderStatus"/>
</wsdl:message>
~~~

Đoạn trên nói rằng **SOAP Body sẽ chứa phần tử `tns:getOrderStatus`** được định nghĩa trong XSD. Không thể suy ra đầy đủ cấu trúc Body chỉ từ tên `GetOrderStatusInput` hoặc tên operation trong `portType`. Cũng không nên hiểu `part name="parameters"` là một thẻ XML `<parameters>`: đó là tên part thuộc mô hình WSDL, không phải payload XML trên wire.

> **Quy tắc đọc nhanh:** trước tiên tìm `wsdl:part/@element` của input/output, rồi đi đến global element trong XSD. Đây là căn cứ chắc chắn hơn suy đoán từ code Java.

## 4. Thiết kế document/literal wrapped từ contract

Xét dịch vụ trả về trạng thái đơn hàng. Ta chọn một operation `getOrderStatus` với `orderId` là dữ liệu đầu vào và `status` là kết quả.

### 4.1. WSDL 1.1 minh họa đầy đủ

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<wsdl:definitions
    xmlns:wsdl="http://schemas.xmlsoap.org/wsdl/"
    xmlns:soap="http://schemas.xmlsoap.org/wsdl/soap/"
    xmlns:xs="http://www.w3.org/2001/XMLSchema"
    xmlns:tns="urn:demo:orders:v1"
    targetNamespace="urn:demo:orders:v1"
    name="OrderStatusWrappedService">

  <wsdl:types>
    <xs:schema targetNamespace="urn:demo:orders:v1"
               elementFormDefault="qualified">
      <xs:element name="getOrderStatus">
        <xs:complexType>
          <xs:sequence>
            <xs:element name="orderId" type="xs:string"/>
          </xs:sequence>
        </xs:complexType>
      </xs:element>

      <xs:element name="getOrderStatusResponse">
        <xs:complexType>
          <xs:sequence>
            <xs:element name="status" type="xs:string"/>
          </xs:sequence>
        </xs:complexType>
      </xs:element>
    </xs:schema>
  </wsdl:types>

  <wsdl:message name="GetOrderStatusInput">
    <wsdl:part name="parameters" element="tns:getOrderStatus"/>
  </wsdl:message>
  <wsdl:message name="GetOrderStatusOutput">
    <wsdl:part name="parameters" element="tns:getOrderStatusResponse"/>
  </wsdl:message>

  <wsdl:portType name="OrderStatusPortType">
    <wsdl:operation name="getOrderStatus">
      <wsdl:input message="tns:GetOrderStatusInput"/>
      <wsdl:output message="tns:GetOrderStatusOutput"/>
    </wsdl:operation>
  </wsdl:portType>

  <wsdl:binding name="OrderStatusBinding"
                type="tns:OrderStatusPortType">
    <soap:binding style="document"
                  transport="http://schemas.xmlsoap.org/soap/http"/>
    <wsdl:operation name="getOrderStatus">
      <soap:operation
          soapAction="urn:demo:orders:v1/getOrderStatus"/>
      <wsdl:input>
        <soap:body use="literal"/>
      </wsdl:input>
      <wsdl:output>
        <soap:body use="literal"/>
      </wsdl:output>
    </wsdl:operation>
  </wsdl:binding>

  <wsdl:service name="OrderStatusWrappedService">
    <wsdl:port name="OrderStatusPort"
               binding="tns:OrderStatusBinding">
      <soap:address location="https://api.example.test/soap/orders"/>
    </wsdl:port>
  </wsdl:service>
</wsdl:definitions>
~~~

Đây là **một hợp đồng độc lập** để minh họa wrapped. `example.test` là địa chỉ giả định; muốn chạy thật phải triển khai endpoint phù hợp, khai báo dependency và cấu hình runtime. Trong hệ thống thực tế, có thể đặt XSD ở file riêng rồi `xs:import`/`xs:include` đúng namespace; cách inline ở đây giúp theo dõi quan hệ giữa schema và message.

Điểm làm nên quy ước wrapped:

- Tên operation là `getOrderStatus`; global element input cũng là `getOrderStatus`.
- Output dùng global element `getOrderStatusResponse`.
- Mỗi message chỉ có một part tên `parameters`, dẫn đến phần tử wrapper qua `element`.
- Wrapper có `xs:complexType` chứa `xs:sequence` các field; các tool JAX-WS thường có thể diễn giải các field này như tham số.
- SOAP binding vẫn là **document + literal**; không có giá trị `wrapped` trong `soap:binding`.

Một số công cụ JAX-WS áp dụng thêm các điều kiện cụ thể trước khi nhận diện wrapped, ví dụ cách đặt tên, phần tử global và cấu trúc complex type. Không nên tự tuyên bố mọi WSDL trông giống wrapped sẽ được mọi bộ sinh mã unwrap giống nhau.

### 4.2. SOAP request và response thực tế

Request SOAP 1.1:

~~~xml
<soapenv:Envelope
    xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
    xmlns:ord="urn:demo:orders:v1">
  <soapenv:Header/>
  <soapenv:Body>
    <ord:getOrderStatus>
      <ord:orderId>ORD-1001</ord:orderId>
    </ord:getOrderStatus>
  </soapenv:Body>
</soapenv:Envelope>
~~~

Response SOAP 1.1:

~~~xml
<soapenv:Envelope
    xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
    xmlns:ord="urn:demo:orders:v1">
  <soapenv:Body>
    <ord:getOrderStatusResponse>
      <ord:status>PROCESSING</ord:status>
    </ord:getOrderStatusResponse>
  </soapenv:Body>
</soapenv:Envelope>
~~~

QName của body root lần lượt là `{urn:demo:orders:v1}getOrderStatus` và `{urn:demo:orders:v1}getOrderStatusResponse`. Prefix `ord` chỉ là bí danh có thể thay đổi; **namespace URI cùng local name** mới xác định QName.

Một JAX-WS client ở chế độ wrapped có thể được sinh thành lời gọi gần giống:

~~~java
// Minh họa chữ ký client; tên thực tế do WSDL + bộ sinh mã quyết định.
String status = port.getOrderStatus("ORD-1001");
~~~

Tuy nhiên, **chữ ký Java không phải wire format**. Runtime vẫn xây XML `getOrderStatus` / `getOrderStatusResponse` như contract. Với các phương án binding khác, công cụ có thể giữ wrapper object thay vì chuyển thành đối số `String`.

## 5. Thiết kế document/literal bare từ contract

Vẫn là nghiệp vụ lấy trạng thái đơn hàng, lần này XML root là **tài liệu yêu cầu/phản hồi độc lập** với tên Java operation. Đây là một lựa chọn hữu ích khi contract đặt trọng tâm vào message nghiệp vụ hoặc được dùng bởi nhiều hệ thống và ngôn ngữ.

### 5.1. WSDL 1.1 minh họa đầy đủ

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<wsdl:definitions
    xmlns:wsdl="http://schemas.xmlsoap.org/wsdl/"
    xmlns:soap="http://schemas.xmlsoap.org/wsdl/soap/"
    xmlns:xs="http://www.w3.org/2001/XMLSchema"
    xmlns:tns="urn:demo:orders:v1"
    targetNamespace="urn:demo:orders:v1"
    name="OrderStatusBareService">

  <wsdl:types>
    <xs:schema targetNamespace="urn:demo:orders:v1"
               elementFormDefault="qualified">
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
            <xs:element name="status" type="xs:string"/>
          </xs:sequence>
        </xs:complexType>
      </xs:element>
    </xs:schema>
  </wsdl:types>

  <wsdl:message name="GetOrderStatusInput">
    <wsdl:part name="parameters" element="tns:GetOrderStatusRequest"/>
  </wsdl:message>
  <wsdl:message name="GetOrderStatusOutput">
    <wsdl:part name="parameters" element="tns:GetOrderStatusResponse"/>
  </wsdl:message>

  <wsdl:portType name="OrderStatusBarePortType">
    <wsdl:operation name="getOrderStatus">
      <wsdl:input message="tns:GetOrderStatusInput"/>
      <wsdl:output message="tns:GetOrderStatusOutput"/>
    </wsdl:operation>
  </wsdl:portType>

  <wsdl:binding name="OrderStatusBareBinding"
                type="tns:OrderStatusBarePortType">
    <soap:binding style="document"
                  transport="http://schemas.xmlsoap.org/soap/http"/>
    <wsdl:operation name="getOrderStatus">
      <soap:operation
          soapAction="urn:demo:orders:v1/getOrderStatus"/>
      <wsdl:input>
        <soap:body use="literal"/>
      </wsdl:input>
      <wsdl:output>
        <soap:body use="literal"/>
      </wsdl:output>
    </wsdl:operation>
  </wsdl:binding>

  <wsdl:service name="OrderStatusBareService">
    <wsdl:port name="OrderStatusBarePort"
               binding="tns:OrderStatusBareBinding">
      <soap:address location="https://api.example.test/soap/orders"/>
    </wsdl:port>
  </wsdl:service>
</wsdl:definitions>
~~~

Đây là **phương án thay thế độc lập** với ví dụ wrapped, không phải yêu cầu đưa cả hai bản WSDL vào cùng service/endpoint. Quan sát rằng:

- Operation vẫn tên `getOrderStatus`.
- Input root chuyển thành `GetOrderStatusRequest`; output root là `GetOrderStatusResponse`.
- `wsdl:message` vẫn có **một part tham chiếu đến global element**.
- Binding vẫn ghi `style="document"` và `use="literal"`.
- Bản thân `GetOrderStatusRequest` vẫn chứa `xs:sequence` và các field; *bare* **không** có nghĩa là không được sử dụng complex type hoặc không được chứa nhiều dữ liệu.

### 5.2. SOAP request và response thực tế

Request:

~~~xml
<soapenv:Envelope
    xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
    xmlns:ord="urn:demo:orders:v1">
  <soapenv:Body>
    <ord:GetOrderStatusRequest>
      <ord:orderId>ORD-1001</ord:orderId>
    </ord:GetOrderStatusRequest>
  </soapenv:Body>
</soapenv:Envelope>
~~~

Response:

~~~xml
<soapenv:Envelope
    xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
    xmlns:ord="urn:demo:orders:v1">
  <soapenv:Body>
    <ord:GetOrderStatusResponse>
      <ord:status>PROCESSING</ord:status>
    </ord:GetOrderStatusResponse>
  </soapenv:Body>
</soapenv:Envelope>
~~~

Với client JAX-WS/CXF dùng mô hình bare, bạn thường gặp chữ ký giữ nguyên request/response object:

~~~java
// Chữ ký minh họa, không thay cho SEI thực tế do tool sinh.
GetOrderStatusResponse response =
        port.getOrderStatus(new GetOrderStatusRequest("ORD-1001"));
~~~

Constructor nhận `String` ở trên chỉ là ví dụ nếu DTO có constructor như vậy; JAXB-generated class phổ biến dùng constructor không tham số và setter. Để code sát với JAXB model được sinh, cách gọi thường là:

~~~java
GetOrderStatusRequest request = new GetOrderStatusRequest();
request.setOrderId("ORD-1001");
GetOrderStatusResponse response = port.getOrderStatus(request);
~~~

Trong project thật, hãy đọc interface sinh bởi `wsdl2java`/`wsimport`: package, chữ ký và tên phương thức tùy WSDL, customization và phiên bản runtime.

## 6. So sánh chính xác trên wire

| Đặc điểm | Document/literal wrapped | Document/literal bare |
|---|---|---|
| `soap:binding/@style` | `document` | `document` |
| `soap:body/@use` | `literal` | `literal` |
| Tên `wsdl:operation` trong ví dụ | `getOrderStatus` | `getOrderStatus` |
| Global element input | `getOrderStatus` | `GetOrderStatusRequest` |
| Global element output | `getOrderStatusResponse` | `GetOrderStatusResponse` |
| Part của input message | `element="tns:getOrderStatus"` | `element="tns:GetOrderStatusRequest"` |
| XML đầu tiên trong SOAP Body | `<ord:getOrderStatus>` | `<ord:GetOrderStatusRequest>` |
| Hình thức thường thấy ở client | Tham số Java có thể được *unwrap* | Request/response DTO thường được giữ nguyên |
| Điểm mạnh | Thân thiện giao diện operation/method | Thể hiện rõ tài liệu nghiệp vụ và schema riêng |
| Cần lưu ý | Wrapper name gắn chặt với tên operation, quy tắc unwrap của tooling | Khả năng sinh mã và tham số có thể kém “giống method Java” hơn |

**Cả hai đều là document/literal.** Không thể dựa vào dòng `<soap:binding style="document">` để kết luận wrapped hay bare. Cũng không nên dựa vào SOAPAction: HTTP header `SOAPAction` mô tả mục đích hành động trong SOAP 1.1 tùy binding, nhưng không quyết định phần tử XML gốc. SOAP 1.2 có binding và media type khác; các ví dụ WSDL ở đây dùng **WSDL 1.1 SOAP 1.1 HTTP binding**.

### Một lưu ý về tính “bọc” của bare

Nếu một bare request có dạng:

~~~xml
<ord:GetOrderStatusRequest>
  <ord:orderId>ORD-1001</ord:orderId>
  <ord:includeHistory>false</ord:includeHistory>
</ord:GetOrderStatusRequest>
~~~

thì `GetOrderStatusRequest` vẫn là một thẻ chứa nhiều phần tử con. Nó chỉ **không phải wrapper được xác lập theo quy ước operation-wrapped**. Đừng đếm số tầng XML để quyết định wrapped/bare; hãy xem quan hệ giữa operation, `wsdl:part`, element và quy ước ánh xạ.

## 7. Phân biệt wrapped và bare khi chỉ được đưa một WSDL

Quy trình kiểm tra contract của đối tác:

1. Mở `wsdl:binding` và xác nhận `style="document"`; mở `wsdl:input/wsdl:output` để kiểm tra `soap:body use="literal"`.
2. Từ `wsdl:binding/wsdl:operation` tra về `wsdl:portType/wsdl:operation` và xác định `wsdl:input/@message`, `wsdl:output/@message`.
3. Trong các `wsdl:message`, tìm `wsdl:part` nằm trong SOAP Body; truy theo `element="prefix:LocalName"` đến global element đúng namespace.
4. So sánh local name của input element với tên operation, output với `OperationNameResponse`; kiểm tra wrapper là complex type có các thành phần theo quy ước của công cụ đang dùng.
5. Sinh thử Java client/SEI bằng tool dự kiến và **kiểm tra XML thực** qua request capture/test; không dựa duy nhất vào số tham số trên method.

**Wrapped là quy ước có các điều kiện nhận diện**, không phải một thuộc tính quy phạm riêng trong WSDL 1.1. Một bare service hoàn toàn có thể tình cờ đặt global element trùng tên operation; việc phân loại phải xét cả cấu trúc schema và quy tắc của tooling, không chỉ một chuỗi ký tự.

Để có khả năng tương thích liên nền tảng tốt, contract document/literal nên ưu tiên **một body part tham chiếu một global XSD element cho mỗi input/output**. Các WSDL có nhiều body part hoặc binding phức tạp có thể tạo ra hành vi không đồng nhất giữa bộ sinh mã; cần kiểm thử theo WS-I Basic Profile tương ứng và theo yêu cầu đối tác.

## 8. Ranh giới trong Spring Web Services: payload root là điểm vào

Trong Spring-WS, `MessageDispatcherServlet` chuyển SOAP request đến `MessageDispatcher` và endpoint mapping. Khi dùng `@PayloadRoot`, điểm nhận diện chính là **QName của phần tử gốc trong SOAP Body**; framework không nhất thiết “unwrap” thành các tham số method như một số client JAX-WS.

### 8.1. Endpoint cho wrapped

~~~java
import org.springframework.ws.server.endpoint.annotation.Endpoint;
import org.springframework.ws.server.endpoint.annotation.PayloadRoot;
import org.springframework.ws.server.endpoint.annotation.RequestPayload;
import org.springframework.ws.server.endpoint.annotation.ResponsePayload;

@Endpoint
public class WrappedOrderEndpoint {
    private static final String NS = "urn:demo:orders:v1";

    @PayloadRoot(namespace = NS, localPart = "getOrderStatus")
    @ResponsePayload
    public GetOrderStatusResponse handle(
            @RequestPayload GetOrderStatus request) {
        GetOrderStatusResponse response = new GetOrderStatusResponse();
        response.setStatus("PROCESSING");
        return response;
    }
}
~~~

Ở đây `GetOrderStatus` là JAXB model dành cho **global element `getOrderStatus`** của thiết kế wrapped; nó chứa `orderId`. Method tên `handle` vẫn hợp lệ vì dispatch dựa trên annotation, không dựa trên `handle`. Các import của JAXB model và package tùy bản sinh mã.

### 8.2. Endpoint cho bare

~~~java
@Endpoint
public class BareOrderEndpoint {
    private static final String NS = "urn:demo:orders:v1";

    @PayloadRoot(namespace = NS, localPart = "GetOrderStatusRequest")
    @ResponsePayload
    public GetOrderStatusResponse handle(
            @RequestPayload GetOrderStatusRequest request) {
        GetOrderStatusResponse response = new GetOrderStatusResponse();
        response.setStatus("PROCESSING");
        return response;
    }
}
~~~

Điểm khác về dispatch nằm ở `localPart`, còn luồng xử lý XML → JAXB → business service → JAXB → XML tương tự. Ví dụ giả định lớp JAXB phù hợp có `@XmlRootElement` hoặc được adapter giải quyết; một số mã sinh dùng `JAXBElement` và cần ký hiệu/adapter tương ứng. **Không dán cả hai ví dụ vào một ứng dụng rồi tự nhận là chúng cùng một hợp đồng**: chúng minh họa hai lựa chọn wire contract độc lập.

Phía client Spring-WS, `WebServiceTemplate` gửi **payload object** qua marshalling:

~~~java
// template đã được cấu hình JAXB marshaller/unmarshaller và transport.
GetOrderStatusRequest req = new GetOrderStatusRequest();
req.setOrderId("ORD-1001");

GetOrderStatusResponse res = (GetOrderStatusResponse)
        template.marshalSendAndReceive(
                "https://api.example.test/soap/orders", req);
~~~

Đoạn client này tương ứng với **bare**. Đối với wrapped, payload cần là wrapper model `GetOrderStatus` tương ứng `getOrderStatus`; đổi object ở phía client mà không đổi wire contract sẽ gây mismatch QName hoặc schema. Nếu công cụ JAXB sinh `ObjectFactory` và `JAXBElement`, hãy truyền đúng JAXB root object cho marshaller.

### Vậy có cần CXF/JAX-WS khi dùng Spring-WS không?

Không bắt buộc. Spring-WS có dispatch, endpoint adapter, `WebServiceTemplate`, JAXB integration, validation và SOAP fault resolver của riêng mình. JAX-WS là API lập trình service/port; Apache CXF là một runtime có triển khai JAX-WS và bộ công cụ WSDL-first. Client CXF/JAX-WS **vẫn có thể gọi** server Spring-WS khi hai phía nhất trí về WSDL, SOAP message, transport và policy bảo mật. Đây là cách thiết kế contract-first phục vụ tích hợp đa công nghệ.

## 9. Java binding của JAX-WS/CXF: wrapped/bare ảnh hưởng những gì?

Trên interface JAX-WS có khái niệm parameter style:

~~~java
import jakarta.jws.WebService;
import jakarta.jws.soap.SOAPBinding;

// Các ví dụ annotation riêng biệt, minh họa lựa chọn code-first.
// Không đảm bảo tự tạo WSDL trùng hai hợp đồng đã nêu.
@WebService(targetNamespace = "urn:demo:orders:v1")
@SOAPBinding(parameterStyle = SOAPBinding.ParameterStyle.WRAPPED)
public interface WrappedOrdersPort {
    String getOrderStatus(String orderId);
}
~~~

~~~java
@WebService(targetNamespace = "urn:demo:orders:v1")
@SOAPBinding(parameterStyle = SOAPBinding.ParameterStyle.BARE)
public interface BareOrdersPort {
    GetOrderStatusResponse getOrderStatus(GetOrderStatusRequest request);
}
~~~

Đây là **mô tả ý tưởng**: bản code-first thực tế cần `@WebMethod`, `@WebParam`, `@WebResult` và có thể `@RequestWrapper`/`@ResponseWrapper` cùng data binding để kiểm soát đúng QNames và schema. Không lấy hai interface ở trên làm đặc tả thay cho WSDL chính thức.

Trong dự án **WSDL-first**, luồng phù hợp hơn là:

~~~text
WSDL/XSD chuẩn được chốt
       ↓
CXF wsdl2java / công cụ JAX-WS tương thích
       ↓
Service Endpoint Interface (SEI) + JAXB model + client proxy
       ↓
Server implementation / client implementation
       ↓
Kiểm tra SOAP thực với contract gốc
~~~

Khi tool nhận diện wrapped, chữ ký Java **có thể** trải các field trong wrapper thành tham số; ở chế độ bare, chữ ký thường dùng một đối tượng request/response. Nhưng cách sinh mã chịu ảnh hưởng từ tool, tùy chọn binding, tên phần tử, kiểu trả về và phiên bản JAXB/JAX-WS. Đặc biệt lưu ý hai hệ sinh thái package `javax.*` và `jakarta.*`: chọn dependency và CXF/runtime cùng thế hệ, không trộn import khác đời.

## 10. Thiết kế schema: điều gì dễ bị phá vỡ?

Trong SOAP contract-first, sự ổn định không chỉ đến từ wrapped hay bare mà còn từ các ràng buộc XSD.

### 10.1. Namespace, QName và thứ tự

Hai phần tử sau **không tương đương**, dù cùng viết `getOrderStatus`:

~~~xml
<a:getOrderStatus xmlns:a="urn:demo:orders:v1"/>
<b:getOrderStatus xmlns:b="urn:demo:orders:v2"/>
~~~

Tương tự, thay `elementFormDefault="qualified"` có thể đổi namespace của các phần tử con trong payload. Với `xs:sequence`, thứ tự các field có ý nghĩa đối với validation; XML có đủ field nhưng sai thứ tự vẫn có thể bị từ chối.

### 10.2. Tùy chọn và giá trị null

Các khai báo sau biểu đạt điều khác nhau:

~~~xml
<xs:element name="note" type="xs:string" minOccurs="0"/>
<xs:element name="comment" type="xs:string" nillable="true"/>
~~~

- `minOccurs="0"` cho phép **bỏ hẳn phần tử**.
- `nillable="true"` cho phép phần tử mang `xsi:nil="true"` nếu đáp ứng quy tắc schema.
- Phần tử rỗng `<note/>` là một trường hợp XML khác với **vắng mặt** và **nil**.

Thay các ràng buộc này có thể ảnh hưởng cả JAXB-generated model lẫn khách hàng .NET. Nếu muốn thêm field tùy chọn, cần kiểm tra version contract, độ chấp nhận của client hiện có và schema validation thực tế, thay vì mặc định “thêm trường là tương thích”.

### 10.3. Quy ước đặt tên

- Wrapped thường gắn request root với **tên operation**. Đổi tên operation có thể kéo theo đổi wrapper QName, gây breaking change.
- Bare có thể giữ tên **document nghiệp vụ** ổn định độc lập với tên method/operation, nhưng đổi tên global element vẫn là breaking change.
- Không nên đặt tên kiểu `Request`/`Response` rồi nghĩ đã thành bare: phải kiểm tra message part + schema + quy tắc của tool.

## 11. SOAP Fault, interceptor và bảo mật không biến mất khi đổi kiểu

**SOAP Fault** là một loại thông điệp lỗi ở mức SOAP. WSDL có thể khai báo fault bằng `wsdl:fault`, message/element lỗi tương ứng và binding fault. Dù contract dùng wrapped hay bare, lỗi cần có cấu trúc fault ổn định theo thỏa thuận; không trả Java stack trace như một giao diện công khai.

Trong Spring-WS:

- `PayloadValidatingInterceptor` có thể kiểm tra request/response payload theo XSD; JAXB unmarshalling thành công **không thay thế** schema validation đầy đủ.
- `EndpointInterceptor` hỗ trợ các xử lý xuyên suốt; `SoapFaultMappingExceptionResolver` hoặc resolver tùy chỉnh ánh xạ lỗi sang SOAP Fault.
- Module Spring-WS Security dùng cơ chế tích hợp WSS4J để xử lý các yêu cầu như chữ ký XML, timestamp và token theo cấu hình phù hợp.

Trong Apache CXF, interceptor, WSS4J và hỗ trợ policy là trách nhiệm **runtime** chứ không tự phát sinh từ annotation `@SOAPBinding` của JAX-WS.

Một lưu ý thiết thực: **chuyển wrapped → bare sẽ đổi nội dung được ký** nếu chữ ký bao phủ SOAP Body, vì tên element gốc và bytes XML thay đổi. TLS bảo vệ đường truyền nhưng không thay cho chữ ký thông điệp theo yêu cầu WS-Security. Khi tích hợp doanh nghiệp, phải kiểm thử cả QName, canonicalization, signature reference, chứng chỉ, timestamp, truststore và policy, cùng với nghiệp vụ.

## 12. Khi nào chọn wrapped, khi nào chọn bare?

| Bối cảnh thực tế | Thiên về | Lý do |
|---|---|---|
| Thiết kế SOAP mới, nhiều operation nhỏ và client Java/.NET mong interface gần kiểu method | **Wrapped** | Quy ước operation wrapper thường hỗ trợ ánh xạ tham số thân thiện |
| Hợp đồng lấy XML document nghiệp vụ làm đơn vị tích hợp, schema được quản lý độc lập | **Bare** | Payload là message/document có tên nghiệp vụ rõ ràng |
| Đối tác đã cung cấp WSDL/XSD và client đang chạy | **Theo contract hiện hữu** | Thay wrapped/bare thường thay QName payload, là thay đổi phá vỡ tương thích |
| Dùng Spring-WS contract-first, endpoint mapping theo payload | **Cả hai đều khả thi** | `@PayloadRoot` có thể map đến root XML của cả hai lựa chọn |
| Dùng CXF/JAX-WS, muốn code generation mượt | **Thử công cụ với WSDL thật** | Sự tiện dụng phụ thuộc quy tắc wrapped detection và binding tool |
| Contract có WS-SecurityPolicy, fault, headers phức tạp | **Chọn theo contract/policy** | Wrapped/bare không tự giải quyết các yêu cầu bảo mật hay vận hành |

Không có quy tắc “wrapped luôn tốt hơn bare” hoặc ngược lại. Với tích hợp doanh nghiệp, **contract đã được chấp nhận bởi các bên** thường là ràng buộc lớn nhất. Nếu vẫn đang thiết kế mới, cân nhắc tính ổn định của XML schema, nhu cầu sinh client từ WSDL, tên operation và cách version hóa.

### Tình huống quyết định

Một hệ thống thanh toán nhận từ ngân hàng phần tử `<pay:PaymentStatusRequest>` trong namespace `urn:bank:payments:v3`. Code Java phía bạn đặt tên method `getStatus`. Vì operation và tên global element khác nhau, **không tự ý đổi SOAP Body thành `<pay:getStatus>`** chỉ để “giống wrapped”. Thiết kế endpoint Spring-WS theo root `PaymentStatusRequest` và sinh client tương thích WSDL của ngân hàng.

## 13. Checklist kiểm thử trước khi bàn giao

1. **Kiểm tra hợp đồng:** khóa phiên bản WSDL/XSD; kiểm tra namespace, global elements, input/output part, binding và endpoint.
2. **Kiểm tra XML request/response:** capture SOAP thật cho cả tình huống thành công và lỗi; xác minh first child của Body đúng QName mà `wsdl:part/@element` khai báo.
3. **Kiểm tra schema:** validate đủ cả field bắt buộc, `minOccurs`, `nillable`, thứ tự `xs:sequence` và giới hạn dữ liệu.
4. **Kiểm tra code generation:** tạo thử client độc lập (CXF/JAX-WS hoặc .NET) và so sánh wire format, không chỉ nhìn chữ ký Java.
5. **Kiểm tra binding:** xác minh SOAP 1.1/1.2 đúng hợp đồng, HTTP Content-Type, SOAPAction nếu được yêu cầu, endpoint URI và reverse proxy.
6. **Kiểm tra lỗi:** đối chiếu SOAP Fault code, reason/detail, modeled faults và behavior HTTP theo profile đối tác.
7. **Kiểm tra bảo mật:** HTTPS, WS-Security headers, signature/encryption, chứng chỉ, clock skew/timestamp, replay protection và giới hạn XML parser để giảm nguy cơ XXE.
8. **Kiểm tra tương thích khi nâng cấp:** so sánh WSDL đã công bố và mẫu XML trước/sau thay đổi runtime, JAXB, CXF hoặc Spring-WS.

Đặc biệt khi muốn đổi wrapped ↔ bare ở một dịch vụ đã vận hành, hãy xem đó là **thay đổi contract**. Lộ trình an toàn thường là công bố một phiên bản operation/namespace/endpoint mới, duy trì hỗ trợ client cũ theo thỏa thuận và thực hiện migration có kiểm thử.

## 14. Bài tập ứng dụng có đáp án gợi ý

### Bài 1. Nhận diện wire contract

Cho đoạn WSDL:

~~~xml
<wsdl:operation name="submitInvoice">
  <wsdl:input message="tns:SubmitInvoiceMessage"/>
</wsdl:operation>

<wsdl:message name="SubmitInvoiceMessage">
  <wsdl:part name="parameters" element="tns:InvoiceSubmission"/>
</wsdl:message>
~~~

Giả sử SOAP binding là document/literal và `InvoiceSubmission` là global element hợp lệ. Câu hỏi: SOAP Body request có bắt buộc chứa `<tns:submitInvoice>` không?

**Gợi ý:** Không. Part trỏ đến `tns:InvoiceSubmission`; đó là payload root cần được kiểm tra trong XSD. Tên operation `submitInvoice` không tự sinh thêm element trên wire.

### Bài 2. Phân tích thay đổi

Đội server đổi global element từ `getOrderStatus` thành `GetOrderStatusRequest`, giữ nguyên `wsdl:operation name="getOrderStatus"` và `soapAction`. Client cũ có tiếp tục hoạt động chắc chắn không?

**Gợi ý:** Không. QName của phần tử trong SOAP Body đã đổi. Endpoint mapping, JAXB, generated proxy và chữ ký SOAP có thể chịu ảnh hưởng.

### Bài 3. Chọn mô hình và endpoint

Bạn sở hữu WSDL được đối tác cấp với input root `{urn:partner:inventory:v2}InventoryLookup`. Viết `@PayloadRoot` cho Spring-WS:

~~~java
@PayloadRoot(
    namespace = "urn:partner:inventory:v2",
    localPart = "InventoryLookup")
@ResponsePayload
public InventoryLookupResponse lookup(
        @RequestPayload InventoryLookup request) {
    // Gọi business service và tạo XML response đúng XSD.
    return ...;
}
~~~

**Gợi ý:** Tên Java method `lookup` không cần trùng local part. Tên lớp JAXB, import và adapter phải đúng với model sinh từ schema.

### Bài 4. Tự giải thích

Vì sao cả hai WSDL minh họa trong bài đều có `soap:binding style="document"` và `soap:body use="literal"`, nhưng SOAP Body khác nhau?

**Đáp án:** Vì `style`/`use` nói về loại SOAP binding và việc dùng literal XML; XML root được xác định bằng **global element mà message part tham chiếu**. Wrapped/bare là quy ước tổ chức element và ánh xạ operation, không phải giá trị `style`/`use` khác nhau.

---

**Ghi nhớ:** Khi thiết kế SOAP contract-first trong Spring Web Services, hãy bắt đầu từ **XSD global element → WSDL message part → SOAP Body QName → endpoint mapping**, rồi mới xem Java method, JAXB model và SOAP client. Document/literal wrapped và bare đều có thể đúng; lựa chọn tốt là lựa chọn được biểu diễn nhất quán trong hợp đồng, được sinh/đọc chính xác bởi các client và vượt qua kiểm thử tương thích cùng các chính sách bảo mật của hệ thống doanh nghiệp.
