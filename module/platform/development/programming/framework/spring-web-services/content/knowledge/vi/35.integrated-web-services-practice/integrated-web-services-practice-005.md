# Xây dựng validation và SOAP Fault nghiệp vụ có detail theo schema

## 1. Bối cảnh và kết quả cần đạt

Trong tích hợp doanh nghiệp bằng **Spring Web Services (Spring-WS)**, thông điệp SOAP cần tuân thủ hợp đồng XML đã công bố. Hệ thống đặt hàng phải phân biệt được hai nhóm sai lệch:

- **Sai hợp đồng (schema validation):** thiếu trường bắt buộc, sai kiểu dữ liệu, sai namespace, sai thứ tự phần tử hoặc giá trị không thỏa ràng buộc XSD. Ví dụ: số lượng bằng 0 khi XSD yêu cầu số nguyên dương.
- **Sai quy tắc nghiệp vụ (business validation):** thông điệp hợp lệ theo XSD nhưng vi phạm chính sách hệ thống. Ví dụ: yêu cầu 101 sản phẩm khi giới hạn nghiệp vụ là 100.

Bài thực hành tổng hợp thuộc module **SPRING_WEB_SERVICES** triển khai dịch vụ SOAP theo hướng *contract-first*: thiết kế XSD/WSDL, dùng JAXB và endpoint Spring-WS, chặn request sai cấu trúc bằng interceptor, phát sinh SOAP Fault có phần **detail** khớp schema và kiểm thử từ góc nhìn client. Quy trình này giúp các hệ thống khác xử lý lỗi bằng mã ổn định thay vì phải phân tích chuỗi thông báo.

Sau bài này, người học có thể:

1. Định nghĩa request, response và kiểu dữ liệu lỗi nghiệp vụ bằng XSD.
2. Công bố một WSDL có khai báo fault nghiệp vụ để client hiểu hợp đồng.
3. Bật validation XML ở biên dịch vụ và phân biệt nó với kiểm tra nghiệp vụ.
4. Chuyển ngoại lệ nghiệp vụ thành SOAP Fault theo chuẩn, trong đó detail có cấu trúc hợp lệ.
5. Viết ca kiểm thử cho đường thành công, request không hợp lệ và lỗi nghiệp vụ; kiểm tra tương thích SOAP 1.1/1.2 và JAXB.

> Phạm vi ví dụ: **Java 17+, Spring Boot 3.x và Spring-WS 4.x** (Jakarta XML/SOAP). Các ví dụ dưới đây dùng SOAP 1.1, một endpoint đặt hàng và SAAJ để tạo Fault detail. Nếu dự án dùng Boot 2.x/Spring-WS 3.x, các import javax/jakarta và cấu hình phụ thuộc sẽ khác.

## 2. Thiết kế contract-first và ranh giới validation

Một yêu cầu đặt hàng có hai trường: mã đơn hàng và số lượng. XSD kiểm soát mã đơn hàng có ký tự hợp lệ, độ dài 1–40 và số lượng dương; hệ thống kiểm tra bổ sung giới hạn 100 sản phẩm. Khi vi phạm giới hạn, dịch vụ trả mã lỗi **QUANTITY_LIMIT** cùng thông điệp an toàn và mã đối chiếu (**correlationId**).

| Tình huống | Lớp phát hiện | Kết quả mong đợi |
| --- | --- | --- |
| Thiếu orderId; quantity = 0 | XSD / PayloadValidatingInterceptor | SOAP Fault phía client (Client/Sender) |
| quantity = 101 | Dịch vụ nghiệp vụ | SOAP Fault phía client có BusinessFault detail, code = QUANTITY_LIMIT |
| orderId đã xử lý trước đó | Dịch vụ nghiệp vụ / lưu trữ | SOAP Fault có BusinessFault detail, code = ORDER_DUPLICATED |
| quantity = 100, orderId hợp lệ | Endpoint và service | PlaceOrderResponse thành công |
| Lỗi cơ sở dữ liệu hoặc sự cố nội bộ | Hạ tầng / xử lý lỗi máy chủ | SOAP Fault phía server (Server/Receiver), không để lộ stack trace |

Một hệ thống thực tế thường có ba lớp kiểm tra:

1. **XML well-formed + SOAP processing:** XML parser và SOAP stack xử lý cấu trúc envelope và cú pháp XML.
2. **XSD validation:** xác nhận payload thuộc vocabulary của hợp đồng công bố.
3. **Business validation:** kiểm tra trạng thái hệ thống, giới hạn, quyền nghiệp vụ, tính duy nhất và các quy tắc liên trường.

XSD không thay thế nghiệp vụ: số lượng 101 vẫn là một số nguyên dương hợp lệ. Ngược lại, đưa giới hạn kinh doanh thường xuyên thay đổi vào XSD có thể làm thay đổi contract và buộc client cập nhật không cần thiết.

## 3. Định nghĩa XSD cho request, response và fault

Tạo tài nguyên minh họa **src/main/resources/xsd/orders.xsd**:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"
           xmlns:tns="urn:example:orders:v1"
           targetNamespace="urn:example:orders:v1"
           elementFormDefault="qualified">

    <xs:simpleType name="OrderIdType">
        <xs:restriction base="xs:string">
            <xs:minLength value="1"/>
            <xs:maxLength value="40"/>
            <xs:pattern value="[A-Z0-9-]+"/>
        </xs:restriction>
    </xs:simpleType>

    <xs:simpleType name="BusinessCodeType">
        <xs:restriction base="xs:string">
            <xs:enumeration value="QUANTITY_LIMIT"/>
            <xs:enumeration value="ORDER_DUPLICATED"/>
        </xs:restriction>
    </xs:simpleType>

    <xs:element name="PlaceOrderRequest">
        <xs:complexType>
            <xs:sequence>
                <xs:element name="orderId" type="tns:OrderIdType"/>
                <xs:element name="quantity" type="xs:positiveInteger"/>
            </xs:sequence>
        </xs:complexType>
    </xs:element>

    <xs:element name="PlaceOrderResponse">
        <xs:complexType>
            <xs:sequence>
                <xs:element name="accepted" type="xs:boolean"/>
                <xs:element name="trackingId" type="xs:string"/>
            </xs:sequence>
        </xs:complexType>
    </xs:element>

    <xs:element name="BusinessFault">
        <xs:complexType>
            <xs:sequence>
                <xs:element name="code" type="tns:BusinessCodeType"/>
                <xs:element name="message" type="xs:string"/>
                <xs:element name="correlationId" type="xs:string"/>
            </xs:sequence>
        </xs:complexType>
    </xs:element>
</xs:schema>
~~~

Một request hợp lệ về mặt cấu trúc:

~~~xml
<ord:PlaceOrderRequest xmlns:ord="urn:example:orders:v1">
    <ord:orderId>ORD-2026-001</ord:orderId>
    <ord:quantity>101</ord:quantity>
</ord:PlaceOrderRequest>
~~~

Request trên **qua XSD**, nhưng sẽ thất bại khi kiểm tra giới hạn nghiệp vụ. Nếu quantity bằng 0, sai kiểu xs:positiveInteger và interceptor có thể chặn trước khi endpoint chạy.

Cần chú ý các điểm sau:

- Namespace và tên phần tử tạo thành **QName**, ví dụ {urn:example:orders:v1}BusinessFault. Prefix ord chỉ là ký hiệu tùy chọn; namespace URI mới là phần xác định hợp đồng.
- Do elementFormDefault="qualified", các phần tử con code, message, correlationId trong Fault detail cũng phải thuộc namespace này.
- xs:sequence yêu cầu **đúng thứ tự** các phần tử, đồng thời mỗi trường xuất hiện đúng một lần khi không đặt minOccurs/maxOccurs.
- Không dùng message làm định danh lỗi máy đọc. Client nên nhánh xử lý theo code; message có thể được dịch hoặc diễn đạt lại.
- Khi mở rộng danh sách code enum, phải đánh giá tương thích với client sinh mã từ XSD. Nếu yêu cầu bổ sung mã linh hoạt, có thể chọn kiểu xs:string và công bố bộ mã lỗi riêng.

## 4. Liên kết fault trong WSDL

XSD định nghĩa dữ liệu; WSDL 1.1 xác định operation và thông điệp lỗi mà client có thể nhận. Một trích đoạn WSDL cho operation placeOrder:

~~~xml
<!-- Trong wsdl:definitions đã khai báo:
     xmlns:wsdl="http://schemas.xmlsoap.org/wsdl/"
     xmlns:soap="http://schemas.xmlsoap.org/wsdl/soap/"
     xmlns:tns="urn:example:orders:v1"
     targetNamespace="urn:example:orders:v1"
     và wsdl:types có import/nhúng orders.xsd. -->

<wsdl:message name="PlaceOrderInput">
    <wsdl:part name="parameters" element="tns:PlaceOrderRequest"/>
</wsdl:message>
<wsdl:message name="PlaceOrderOutput">
    <wsdl:part name="parameters" element="tns:PlaceOrderResponse"/>
</wsdl:message>
<wsdl:message name="PlaceOrderFaultMessage">
    <wsdl:part name="fault" element="tns:BusinessFault"/>
</wsdl:message>

<wsdl:portType name="OrdersPortType">
    <wsdl:operation name="placeOrder">
        <wsdl:input message="tns:PlaceOrderInput"/>
        <wsdl:output message="tns:PlaceOrderOutput"/>
        <wsdl:fault name="BusinessFault"
                    message="tns:PlaceOrderFaultMessage"/>
    </wsdl:operation>
</wsdl:portType>

<wsdl:binding name="OrdersBinding" type="tns:OrdersPortType">
    <soap:binding style="document"
                  transport="http://schemas.xmlsoap.org/soap/http"/>
    <wsdl:operation name="placeOrder">
        <soap:operation soapAction="urn:example:orders:v1/placeOrder"/>
        <wsdl:input><soap:body use="literal"/></wsdl:input>
        <wsdl:output><soap:body use="literal"/></wsdl:output>
        <wsdl:fault name="BusinessFault">
            <soap:fault name="BusinessFault" use="literal"/>
        </wsdl:fault>
    </wsdl:operation>
</wsdl:binding>
~~~

Đây là **trích đoạn**, chưa phải toàn bộ tệp WSDL triển khai được. WSDL thực tế còn cần phần wsdl:definitions, wsdl:types tham chiếu XSD và wsdl:service/wsdl:port cùng soap:address. Các URL import schema phải truy cập được từ môi trường sinh client.

Spring-WS có DefaultWsdl11Definition để sinh WSDL từ XSD theo quy ước suffix Request/Response/Fault. Tuy nhiên **không được mặc định suy ra** rằng một phần tử tên BusinessFault sẽ tự động được gắn vào operation placeOrder theo đúng ý định: cần kiểm tra WSDL thực sự đã phát hành. Với yêu cầu khai báo wsdl:fault rõ ràng và ổn định, cách dễ kiểm soát là cung cấp WSDL tĩnh đã duyệt bằng SimpleWsdl11Definition.

Ví dụ đăng ký WSDL tĩnh, có toàn bộ nội dung tại **src/main/resources/wsdl/orders.wsdl**:

~~~java
@Bean(name = "orders")
public SimpleWsdl11Definition ordersWsdl() {
    return new SimpleWsdl11Definition(
        new ClassPathResource("wsdl/orders.wsdl"));
}
~~~

Khi MessageDispatcherServlet được ánh xạ vào /ws/*, tài liệu thường được công bố tại **/ws/orders.wsdl**. Xác nhận endpoint thực tế, WSDL và schemaLocation trong môi trường chạy, thay vì chỉ dựa vào tên bean.

## 5. Cấu hình validation tại biên Spring-WS

Một cấu hình Spring-WS minh họa:

~~~java
import java.util.List;

import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.boot.web.servlet.ServletRegistrationBean;
import org.springframework.core.io.ClassPathResource;
import org.springframework.ws.config.annotation.EnableWs;
import org.springframework.ws.config.annotation.WsConfigurer;
import org.springframework.ws.server.EndpointInterceptor;
import org.springframework.ws.soap.server.endpoint.interceptor.PayloadValidatingInterceptor;
import org.springframework.ws.transport.http.MessageDispatcherServlet;
import org.springframework.xml.xsd.SimpleXsdSchema;
import org.springframework.xml.xsd.XsdSchema;
import org.springframework.ws.wsdl.wsdl11.SimpleWsdl11Definition;

@EnableWs
@Configuration
public class OrdersWsConfig implements WsConfigurer {

    @Bean
    public ServletRegistrationBean<MessageDispatcherServlet> soapServlet(
            ApplicationContext context) {
        MessageDispatcherServlet servlet = new MessageDispatcherServlet();
        servlet.setApplicationContext(context);
        servlet.setTransformWsdlLocations(true);
        return new ServletRegistrationBean<>(servlet, "/ws/*");
    }

    @Bean
    public XsdSchema ordersSchema() {
        return new SimpleXsdSchema(
            new ClassPathResource("xsd/orders.xsd"));
    }

    @Bean(name = "orders")
    public SimpleWsdl11Definition ordersWsdl() {
        return new SimpleWsdl11Definition(
            new ClassPathResource("wsdl/orders.wsdl"));
    }

    @Override
    public void addInterceptors(List<EndpointInterceptor> interceptors) {
        PayloadValidatingInterceptor validation =
            new PayloadValidatingInterceptor();
        validation.setXsdSchema(ordersSchema());
        validation.setValidateRequest(true);
        validation.setValidateResponse(true);
        interceptors.add(validation);
    }

    @Bean
    public BusinessFaultResolver businessFaultResolver() {
        return new BusinessFaultResolver();
    }
}
~~~

Các import và class còn lại được trình bày ở phần tiếp theo. Spring Boot có thể tự cấu hình MessageDispatcherServlet khi dùng starter web services; ví dụ trên cố ý chỉ rõ URL để người học nhìn thấy điểm vào SOAP. Khi áp dụng vào ứng dụng đang chạy, chọn **một** cơ chế đăng ký servlet để tránh ánh xạ chồng lấn.

PayloadValidatingInterceptor kiểm tra **payload bên trong SOAP Body** theo XSD. Bật validateRequest để chặn đầu vào sớm; validateResponse giúp phát hiện response thành công bị sai schema trong quá trình phát triển và tích hợp. Việc này **không tự chứng minh** rằng cấu trúc Fault detail đã hợp lệ: phải kiểm tra Fault detail riêng bằng XSD trong test.

Interceptor kiểm tra cấu trúc; nó không tự động gọi kiểm tra nghiệp vụ hay tạo BusinessFault detail theo schema ở trên. Theo hành vi mặc định, lỗi XSD dẫn đến một SOAP Fault báo lỗi validation, nhưng không nhất thiết có BusinessFault detail. Nếu hợp đồng yêu cầu **mọi** lỗi client đều mang một detail chuẩn, cần mở rộng cơ chế xử lý validation errors của interceptor để phát ra kiểu fault thống nhất và viết kiểm thử cho đường đó.

## 6. Tạo nghiệp vụ và ngoại lệ có mã lỗi ổn định

Giả sử công cụ JAXB/XJC đã sinh các lớp PlaceOrderRequest và PlaceOrderResponse từ orders.xsd trong package example.orders.jaxb. Endpoint dưới đây nhận request đã được Spring-WS ánh xạ theo QName, áp dụng quy tắc 100 sản phẩm rồi trả response:

~~~java
import java.math.BigInteger;
import java.util.UUID;

import org.springframework.ws.server.endpoint.annotation.Endpoint;
import org.springframework.ws.server.endpoint.annotation.PayloadRoot;
import org.springframework.ws.server.endpoint.annotation.RequestPayload;
import org.springframework.ws.server.endpoint.annotation.ResponsePayload;

import example.orders.jaxb.PlaceOrderRequest;
import example.orders.jaxb.PlaceOrderResponse;

@Endpoint
public class OrdersEndpoint {
    private static final String NS = "urn:example:orders:v1";

    @PayloadRoot(namespace = NS, localPart = "PlaceOrderRequest")
    @ResponsePayload
    public PlaceOrderResponse placeOrder(
            @RequestPayload PlaceOrderRequest request) {

        if (request.getQuantity().compareTo(BigInteger.valueOf(100)) > 0) {
            throw new BusinessRuleException(
                "QUANTITY_LIMIT",
                "Số lượng tối đa cho một đơn là 100.",
                UUID.randomUUID().toString());
        }

        PlaceOrderResponse response = new PlaceOrderResponse();
        response.setAccepted(true);
        response.setTrackingId("TRACK-" + request.getOrderId());
        return response;
    }
}
~~~

Ngoại lệ nghiệp vụ tách rõ thông điệp công khai khỏi nguyên nhân nội bộ:

~~~java
public final class BusinessRuleException extends RuntimeException {
    private final String code;
    private final String publicMessage;
    private final String correlationId;

    public BusinessRuleException(
            String code, String publicMessage, String correlationId) {
        super(publicMessage);
        this.code = code;
        this.publicMessage = publicMessage;
        this.correlationId = correlationId;
    }

    public String code() { return code; }
    public String publicMessage() { return publicMessage; }
    public String correlationId() { return correlationId; }
}
~~~

Ở hệ thống thực, quy tắc và kiểm tra orderId trùng nên nằm trong **service** có giao dịch và repository, không đặt trực tiếp trong endpoint. Ví dụ trên giữ ngắn đường đi dữ liệu để tập trung vào Fault. Mã theo dõi đơn hàng và correlationId ở đây chỉ là dữ liệu minh họa; triển khai thực cần định danh có ý nghĩa, ghi log tương ứng và bảo đảm idempotency.

Một ngoại lệ nghiệp vụ phải chứa code nằm trong enum BusinessCodeType. Có thể dùng Java enum cho code để tránh nhập sai chính tả; khi thêm mã mới cần cập nhật contract theo quy trình versioning.

## 7. Ánh xạ BusinessRuleException thành SOAP Fault có detail

Trong SOAP 1.1, lỗi dữ liệu/điều kiện từ phía người gọi thường là **Client**; lỗi xử lý không mong đợi của server thường là **Server**. SOAP 1.2 dùng các mã tương ứng **Sender** và **Receiver**. Ở đây ta chọn Client cho QUANTITY_LIMIT vì request có cấu trúc hợp lệ nhưng không thể chấp nhận theo quy tắc nghiệp vụ.

Một EndpointExceptionResolver sẽ nhận ngoại lệ, thêm SOAP Fault vào response và tạo một phần tử **ord:BusinessFault** ngay dưới SOAP detail. Để thể hiện rõ thao tác DOM/SOAP và tránh biến đổi XML bằng nối chuỗi, ví dụ dùng SAAJ của Jakarta:

~~~java
import java.util.Locale;
import javax.xml.namespace.QName;

import jakarta.xml.soap.DetailEntry;
import jakarta.xml.soap.SOAPException;
import jakarta.xml.soap.SOAPFault;

import org.springframework.core.Ordered;
import org.springframework.ws.context.MessageContext;
import org.springframework.ws.server.EndpointExceptionResolver;
import org.springframework.ws.soap.saaj.SaajSoapMessage;

public final class BusinessFaultResolver
        implements EndpointExceptionResolver, Ordered {

    private static final String NS = "urn:example:orders:v1";

    @Override
    public boolean resolveException(
            MessageContext context, Object endpoint, Exception exception) {

        if (!(exception instanceof BusinessRuleException business)) {
            return false;
        }
        if (!(context.getResponse() instanceof SaajSoapMessage response)) {
            return false;
        }

        // Spring-WS sinh faultcode Client (SOAP 1.1)
        // hoặc Sender (SOAP 1.2), tùy phiên bản SOAP đang dùng.
        response.getSoapBody().addClientOrSenderFault(
            "Business rule rejected", Locale.ENGLISH);

        try {
            SOAPFault fault =
                response.getSaajMessage().getSOAPBody().getFault();
            DetailEntry detail = fault.addDetail().addDetailEntry(
                new QName(NS, "BusinessFault", "ord"));

            detail.addChildElement(new QName(NS, "code", "ord"))
                .addTextNode(business.code());
            detail.addChildElement(new QName(NS, "message", "ord"))
                .addTextNode(business.publicMessage());
            detail.addChildElement(new QName(NS, "correlationId", "ord"))
                .addTextNode(business.correlationId());
            return true;
        } catch (SOAPException cause) {
            throw new IllegalStateException(
                "Cannot create SOAP BusinessFault detail", cause);
        }
    }

    @Override
    public int getOrder() {
        return Ordered.HIGHEST_PRECEDENCE;
    }
}
~~~

Điểm quan trọng của cách xây dựng trên:

- BusinessFault là **phần tử gốc duy nhất** trong detail cho loại lỗi này. Ba phần tử con tuân thủ xs:sequence và cùng namespace với XSD.
- SAAJ tạo node XML, nên giá trị message được escape đúng; không ghép chuỗi XML từ ngoại lệ hoặc dữ liệu người dùng.
- Resolver chỉ xử lý BusinessRuleException. Nó trả false với ngoại lệ khác để cơ chế lỗi khác xử lý tiếp; tuyệt đối không chuyển mọi lỗi máy chủ thành QUANTITY_LIMIT.
- Ví dụ này giả định message factory là **SAAJ**. Nếu ứng dụng cấu hình Axiom hoặc công nghệ SOAP message khác, phải thay cách tạo detail bằng API trung lập hoặc implementation tương ứng.
- Mọi code và message công khai cần được kiểm soát: tránh đưa SQL, stack trace, token, chi tiết chứng chỉ hoặc thông tin hệ thống ra phản hồi. Ghi log nội bộ theo correlationId.

Nếu dùng SoapFaultMappingExceptionResolver, có thể map loại exception vào mã Fault và tùy biến phần detail ở customizeFault. Việc chọn một điểm xử lý lỗi thống nhất sẽ tránh nhiều resolver ghi đè cùng một response.

### SOAP Fault thực tế của tình huống quantity = 101

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<soapenv:Envelope
    xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
    xmlns:ord="urn:example:orders:v1">
    <soapenv:Body>
        <soapenv:Fault>
            <faultcode>soapenv:Client</faultcode>
            <faultstring>Business rule rejected</faultstring>
            <detail>
                <ord:BusinessFault>
                    <ord:code>QUANTITY_LIMIT</ord:code>
                    <ord:message>Số lượng tối đa cho một đơn là 100.</ord:message>
                    <ord:correlationId>662c1ad3-e1b1-48ed-8b78-a8fcf60ef164</ord:correlationId>
                </ord:BusinessFault>
            </detail>
        </soapenv:Fault>
    </soapenv:Body>
</soapenv:Envelope>
~~~

**Chỉ** trích phần tử ord:BusinessFault (và descendants) rồi kiểm tra với orders.xsd. Không dùng orders.xsd để validate toàn bộ SOAP Envelope: Envelope thuộc namespace và schema của chuẩn SOAP, không thuộc schema nghiệp vụ.

Trong SOAP 1.2, cấu trúc chuyển thành env:Fault/env:Code/env:Value, env:Reason/env:Text và env:Detail. Không được trả body Fault theo định dạng SOAP 1.1 trong một envelope SOAP 1.2. Ở các hệ thống dùng SOAP Fault qua HTTP, thường gặp HTTP 500 cho SOAP 1.1 fault; client cần đọc SOAP body thay vì chỉ xét mã HTTP.

## 8. Thử request với client SOAP

Gói request vào SOAP 1.1 Envelope:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<soapenv:Envelope
    xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
    xmlns:ord="urn:example:orders:v1">
    <soapenv:Header/>
    <soapenv:Body>
        <ord:PlaceOrderRequest>
            <ord:orderId>ORD-2026-001</ord:orderId>
            <ord:quantity>101</ord:quantity>
        </ord:PlaceOrderRequest>
    </soapenv:Body>
</soapenv:Envelope>
~~~

Lưu nội dung vào **business-invalid.xml** và gửi tới servlet đã cấu hình:

~~~bash
curl -i http://localhost:8080/ws \
  -H "Content-Type: text/xml; charset=utf-8" \
  -H 'SOAPAction: "urn:example:orders:v1/placeOrder"' \
  --data-binary @business-invalid.xml
~~~

Kết quả mong đợi: SOAP Fault có mã Client và BusinessFault/code = QUANTITY_LIMIT. Với quantity = 100, nhận PlaceOrderResponse có accepted = true. Với quantity = 0, interceptor XSD trả lỗi validation trước khi thực thi nghiệp vụ. SOAPAction trong ví dụ phù hợp WSDL minh họa; dispatch theo @PayloadRoot dựa vào QName của payload.

Client Spring-WS dùng WebServiceTemplate thường nhận lỗi SOAP thông qua **SoapFaultClientException**. Có thể đọc fault code/reason và sau đó kiểm tra detail bằng QName/schema để đổi thành loại lỗi domain tương ứng:

~~~java
try {
    Object response = webServiceTemplate.marshalSendAndReceive(request);
    // Xử lý PlaceOrderResponse...
} catch (SoapFaultClientException ex) {
    QName faultCode = ex.getFaultCode();
    String reason = ex.getFaultStringOrReason();
    // Đọc ex.getSoapFault().getFaultDetail(), xác nhận
    // phần tử {urn:example:orders:v1}BusinessFault, rồi parse
    // code/correlationId theo contract đã công bố.
}
~~~

Trong đoạn minh họa trên, webServiceTemplate và request được khởi tạo trong client; cần import org.springframework.ws.soap.client.SoapFaultClientException và javax.xml.namespace.QName. Không nên quyết định nghiệp vụ dựa trên reason/message vì chúng có thể thay đổi theo ngôn ngữ hoặc cấu hình server.

## 9. Kiểm thử tự động và xác nhận tính tương thích

Test ở cấp Spring-WS có thể dùng MockWebServiceClient để đưa payload vào MessageDispatcher mà không cần chạy HTTP server. Ví dụ tối giản:

~~~java
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.ws.test.server.MockWebServiceClient;
import org.springframework.xml.transform.StringSource;

import static org.springframework.ws.test.server.RequestCreators.withPayload;
import static org.springframework.ws.test.server.ResponseMatchers.clientOrSenderFault;

@SpringBootTest
class OrdersSoapTest {
    @Autowired ApplicationContext applicationContext;
    private MockWebServiceClient client;

    @BeforeEach
    void setup() {
        client = MockWebServiceClient.createClient(applicationContext);
    }

    @Test
    void rejectedBySchema() {
        String payload = """
            <ord:PlaceOrderRequest xmlns:ord="urn:example:orders:v1">
              <ord:orderId>ORD-1</ord:orderId>
              <ord:quantity>0</ord:quantity>
            </ord:PlaceOrderRequest>
            """;
        client.sendRequest(withPayload(new StringSource(payload)))
            .andExpect(clientOrSenderFault());
    }

    @Test
    void rejectedByBusinessRule() {
        String payload = """
            <ord:PlaceOrderRequest xmlns:ord="urn:example:orders:v1">
              <ord:orderId>ORD-2</ord:orderId>
              <ord:quantity>101</ord:quantity>
            </ord:PlaceOrderRequest>
            """;
        client.sendRequest(withPayload(new StringSource(payload)))
            .andExpect(clientOrSenderFault());
    }
}
~~~

Hai test trên mới chứng minh có Fault đúng phía, **chưa** chứng minh nội dung detail đúng hợp đồng. Với kiểm thử tích hợp HTTP/SAAJ, đọc SOAP Envelope phản hồi, tìm node theo QName {urn:example:orders:v1}BusinessFault rồi đưa riêng node đó vào javax.xml.validation.Validator:

~~~java
import javax.xml.XMLConstants;
import javax.xml.validation.Schema;
import javax.xml.validation.SchemaFactory;
import javax.xml.transform.dom.DOMSource;
import org.w3c.dom.Element;

// detailRoot: Element BusinessFault lấy từ SOAP Fault response.
Schema schema = SchemaFactory
    .newInstance(XMLConstants.W3C_XML_SCHEMA_NS_URI)
    .newSchema(new java.io.File("src/main/resources/xsd/orders.xsd"));
schema.newValidator().validate(new DOMSource(detailRoot));
~~~

Đây là đoạn khẳng định schema: test cần **tự lấy** detailRoot từ phản hồi thực tế và assert trước rằng node tồn tại, namespace URI và localName đều khớp. Test cũng nên assert code đúng QUANTITY_LIMIT và correlationId có giá trị; nếu không, có thể xảy ra false positive khi chỉ kiểm tra faultcode.

### Ma trận test khuyến nghị

| Ca kiểm thử | Payload / điều kiện | Assertion |
| --- | --- | --- |
| Thành công | orderId hợp lệ, quantity = 1 và 100 | Không có Fault; response khớp XSD |
| Thiếu trường | Thiếu orderId | Client/Sender Fault trước endpoint |
| Sai kiểu | quantity = chữ hoặc 0 | Client/Sender Fault từ validation |
| Sai QName | Sai namespace PlaceOrderRequest | Endpoint không nhận như hợp đồng; kiểm tra phản hồi lỗi theo cấu hình dispatcher |
| Sai thứ tự | quantity trước orderId | Validation thất bại bởi xs:sequence |
| Quy tắc nghiệp vụ | quantity = 101 | Client/Sender Fault, BusinessFault detail qua XSD, QUANTITY_LIMIT |
| Đơn trùng | Repository báo đã xử lý | BusinessFault detail, ORDER_DUPLICATED |
| Sự cố hệ thống | Service ném lỗi hạ tầng | Server/Receiver Fault, không lộ thông tin nhạy cảm |
| SOAP version | Client 1.1 và 1.2 được cấu hình tương ứng | Envelope/Fault đúng phiên bản, detail vẫn đúng QName |
| Client code generation | Sinh stub từ WSDL công bố | Stub thấy operation và wsdl:fault, giải mã được mã lỗi |

Nếu dùng API tự sinh từ WSDL, kiểm thử thật với ít nhất một client khác ngôn ngữ (ví dụ .NET hoặc JAX-WS/Jakarta XML WS) để kiểm tra phần tử fault, prefix/namespace và cách map exception. Lưu cả request/response mẫu trong test fixture như hợp đồng tương thích.

## 10. Các lỗi triển khai thường gặp

**(1) Có detail nhưng sai schema.** Người viết thêm trực tiếp code và message dưới phần detail, thiếu phần tử gốc BusinessFault; hoặc quên namespace cho con; hoặc thêm con sai thứ tự. Cách khắc phục là kiểm tra detailRoot độc lập với XSD và assert QName.

**(2) XSD và WSDL mất đồng bộ.** XSD có BusinessFault nhưng WSDL không khai báo wsdl:fault, khiến client sinh code không nhận kiểu fault này. Cần phát hành và review WSDL thực tế sau khi build, đồng thời bảo đảm import schema truy cập được.

**(3) Interceptor chỉ validate request.** Server có thể trả payload sai schema mà không phát hiện. Có thể bật validateResponse và thêm test phản hồi; tùy yêu cầu môi trường, cân nhắc chi phí và cách xử lý lỗi phản hồi. Fault detail vẫn cần test riêng.

**(4) Coi mọi lỗi là Client/Sender.** Lỗi database, lỗi ký XML hoặc sự cố nội bộ không phải do dữ liệu nghiệp vụ của caller. Phân loại đúng giúp hệ thống đối tác quyết định có retry, cảnh báo hay yêu cầu sửa request.

**(5) Lộ thông tin trong faultstring/detail.** Không phản chiếu raw exception hoặc nội dung XML người dùng gửi. Chỉ công bố mã và thông điệp an toàn, dùng correlationId để tra log.

**(6) Coi JAXB unmarshalling là kiểm tra mọi ràng buộc XSD.** JAXB mapping chỉ ánh xạ XML; nhiều ràng buộc như pattern/minLength và quy tắc nghiệp vụ cần validation được cấu hình rõ. Kiểm thử riêng từng lớp và bảo đảm client có thể thực hiện schema validation nếu cần.

**(7) Nhầm SOAP Fault với mã HTTP.** SOAP Fault là nội dung giao thức. Mã HTTP phụ thuộc SOAP version và transport; client phải phân tích envelope, không chỉ coi mọi phản hồi HTTP khác 2xx là lỗi không có body.

**(8) Thay đổi contract không quản lý phiên bản.** Đổi namespace, đổi thứ tự xs:sequence, đổi tên code hoặc bỏ phần tử có thể phá client cũ. Cần versioning namespace và kiểm thử tương thích trước khi triển khai.

## 11. Vận hành an toàn trong tích hợp doanh nghiệp

Khi đưa bài thực hành vào môi trường tích hợp thật, hãy tách trách nhiệm và giữ một quy ước lỗi nhất quán:

- **Quy tắc XML và bảo mật:** giới hạn kích thước SOAP request, cấu hình parser chống DTD/XXE, tránh XML bomb; giới hạn độ dài trường và số lượng phần tử; đặt timeout cho client/downstream. XSD validation không thay thế các biện pháp này.
- **WS-Security và chứng chỉ:** áp dụng kiểm tra chữ ký, timestamp, token/chứng chỉ qua interceptor trước khi xử lý dữ liệu nghiệp vụ. Lỗi xác thực/ủy quyền cần chính sách Fault riêng, không trá hình thành QUANTITY_LIMIT; không công bố khóa hay chi tiết xác minh mật mã.
- **Khả năng truy vết:** correlationId nên đi xuyên suốt request, log, service call và phản hồi; kiểm tra độ dài/định dạng nếu nhận từ caller. Không dùng ID nhạy cảm làm correlationId.
- **Bền vững hợp đồng:** giới hạn bộ mã lỗi được công bố; quản lý tương thích cho enum code, WSDL fault và XML schema. Test xuyên phiên bản trước khi chuyển đối tác.
- **Idempotency và retry:** QUANTITY_LIMIT là lỗi nghiệp vụ cần sửa dữ liệu, không retry nguyên trạng. ORDER_DUPLICATED có thể liên quan yêu cầu lặp; quy định rõ cách xử lý idempotency. Lỗi hạ tầng có thể retry theo chính sách backoff khi thao tác an toàn.
- **Quan sát vận hành:** đo số request sai XSD, số Fault theo code, latency validation, tỷ lệ Server/Receiver Fault; log có cấu trúc nhưng che dữ liệu nhạy cảm.

Một luồng xử lý mong đợi:

~~~mermaid
flowchart TD
    A[SOAP request] --> B[XML parser và SOAP message]
    B --> C{Payload khớp XSD?}
    C -- Không --> D[Client hoặc Sender Fault do validation]
    C -- Có --> E[JAXB và endpoint]
    E --> F{Đạt quy tắc nghiệp vụ?}
    F -- Không --> G[BusinessRuleException]
    G --> H[BusinessFaultResolver]
    H --> I[SOAP Fault có BusinessFault detail]
    F -- Có --> J[PlaceOrderResponse]
    J --> K[Validate response theo XSD]
    K --> L[SOAP response thành công]
~~~

Sơ đồ tập trung vào đường đi chuẩn. Ngoại lệ parsing, bảo mật và lỗi hạ tầng cần các nhánh xử lý riêng theo cấu hình service.

## 12. Bài tập mở rộng và tiêu chí hoàn thành

**Bài tập A — thêm lỗi ORDER_DUPLICATED.** Mô phỏng repository phát hiện orderId trùng. Ném BusinessRuleException với code ORDER_DUPLICATED, dùng đúng BusinessFault detail hiện có, không tạo biến thể XML tùy tiện. Kiểm thử lời gọi lặp lại và xác định yêu cầu idempotency.

**Bài tập B — chuẩn hóa lỗi schema.** Mặc định lỗi do PayloadValidatingInterceptor tạo ra có thể khác BusinessFault detail. Đặt yêu cầu mọi lỗi đầu vào đều có fault detail theo contract, bổ sung code VALIDATION_ERROR vào XSD và điều chỉnh xử lý validation errors; kiểm thử rằng message công khai không lộ chuỗi parser nội bộ. Cập nhật WSDL và client trước khi áp dụng thay đổi hợp đồng.

**Bài tập C — kiểm tra client liên nền tảng.** Sinh client từ WSDL thực tế rồi gửi các request 0, 100 và 101. Xác minh client nhận faultcode, detail QName, code và correlationId; làm thêm trường hợp SOAP 1.2 nếu hai bên hỗ trợ.

Một bài triển khai đạt yêu cầu khi:

1. XSD định nghĩa request, response và BusinessFault có code và correlationId, được versioning rõ.
2. WSDL công bố operation và khai báo wsdl:fault tương ứng, client sinh mã thành công.
3. Request sai schema bị chặn trước xử lý nghiệp vụ.
4. Request đúng XSD nhưng vi phạm giới hạn được trả Client/Sender Fault với phần detail kiểm chứng được bằng XSD.
5. Request hợp lệ được phản hồi đúng schema; ngoại lệ máy chủ được phân loại riêng.
6. Test tự động kiểm tra cả faultcode, **nội dung detail theo QName/XSD**, và khả năng giải mã từ client.

Kết quả mong đợi là một dịch vụ Spring Web Services có hợp đồng lỗi minh bạch, có thể mở rộng, kiểm thử được và đủ ổn định để tích hợp với hệ thống doanh nghiệp.
