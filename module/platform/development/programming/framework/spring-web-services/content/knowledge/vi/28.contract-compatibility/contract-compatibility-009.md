# WS-I Basic Profile và kiểm chứng khả năng tương tác ngoài Java

> **Chương:** Tương thích hợp đồng  
> **Module:** SPRING_WEB_SERVICES — phát triển dịch vụ SOAP theo hướng contract-first với Spring Web Services, thiết kế XSD/WSDL, ánh xạ JAXB, endpoint và SOAP client; xử lý SOAP Fault, interceptor, XML security, WS-Security, chứng chỉ và kiểm thử tương thích trong tích hợp doanh nghiệp.

## 1. Vì sao cần WS-I khi SOAP đã có tiêu chuẩn?

SOAP, WSDL, XML Schema và các WS-* specifications cung cấp nhiều lựa chọn hợp lệ. Hai implementation có thể cùng hỗ trợ SOAP 1.1 và WSDL 1.1 nhưng vẫn không trao đổi được do khác biệt về binding, document/literal, SOAP encoding, namespace, import, header, fault, attachment hoặc HTTP behavior.

Ví dụ, một WSDL có thể dùng RPC/encoded trong khi client khác chỉ hỗ trợ document/literal. Cả hai bên có thể tạo XML well-formed nhưng vẫn thất bại khi gọi nhau. Một service cũng có thể công bố schema hợp lệ nhưng đưa SOAP Header sai vị trí hoặc dùng SOAPAction khác với điều client generator mong đợi.

**WS-I Basic Profile** là tập hướng dẫn và ràng buộc interoperability cho các công nghệ Web Services phổ biến. Profile chọn và giới hạn một số cách sử dụng SOAP, WSDL, XML Schema và HTTP để giảm khác biệt giữa implementations. Profile không thay thế các standards nền tảng; nó giúp các bên sử dụng chúng theo một tập quy ước chung.

Sau bài học, bạn có thể:

1. Giải thích vai trò WS-I Basic Profile và phân biệt nó với SOAP, WSDL, XSD, WS-Security.
2. Chọn đúng profile/version theo SOAP version, WSDL binding và standards đối tác hỗ trợ.
3. Review WSDL/XSD để phát hiện pattern dễ gây lỗi liên vendor.
4. Kiểm chứng document/literal, SOAPAction, QName, namespace, imports/includes, headers, faults và attachments.
5. Xây dựng Spring-WS/JAXB contract rõ ràng, hạn chế phụ thuộc vào behavior riêng của Java.
6. Kiểm thử bằng ít nhất một SOAP stack độc lập ngoài Java.
7. Lưu request/response captures, assertions và môi trường để lỗi tái lập được.
8. Phân biệt unit test, Java-to-Java integration test và interoperability test thực sự.

**Nguyên tắc:** Một service chạy tốt với client do cùng toolchain generate chưa chứng minh nó tương thích ngoài Java. Cần một implementation độc lập, contract công khai và bằng chứng trao đổi trên wire.

## 2. WS-I Basic Profile nằm ở đâu trong bộ tiêu chuẩn?

Web Services Interoperability Organization (WS-I) xây dựng profiles và testing guidance để giảm những cách sử dụng standards gây không tương thích. Trong SOAP enterprise, Basic Profile tập trung vào các thành phần nền tảng như:

- SOAP messaging và HTTP binding.
- WSDL 1.1 service description.
- XML Schema types dùng trong WSDL.
- Quy ước cho SOAP headers, faults và message format.
- Ràng buộc giúp clients/servers từ nhiều vendors hiểu cùng contract.

Cần đọc đúng bản profile mà hợp đồng viện dẫn. Các thế hệ Basic Profile không có phạm vi giống hệt nhau; SOAP 1.1, SOAP 1.2, WSDL 1.1, attachments và các adjuncts có tài liệu/phạm vi tương ứng. Không ghi chung “WS-I compliant” rồi bỏ qua version, profile và phần mở rộng được dùng.

### 2.1. Profile không phải protocol mới

WS-I Basic Profile không tạo SOAP Envelope mới, không thêm một XML namespace business mới và không yêu cầu thay Spring-WS bằng framework riêng. Nó đặt constraints/guidance lên cách sử dụng standards hiện có.

~~~text
SOAP + WSDL + XSD + HTTP
          |
          v
WS-I Basic Profile constraints / guidance
          |
          v
Contract có ít lựa chọn gây mơ hồ hơn
          |
          v
Test giữa implementations độc lập
~~~

### 2.2. Basic Profile và các phạm vi liên quan

| Phạm vi | Mục đích |
|---|---|
| WS-I Basic Profile | Interoperability của core SOAP/WSDL/XSD/HTTP usage |
| Attachments-related profile/guidance | Cách trao đổi MIME attachments trong phạm vi tương ứng |
| Basic Security Profile | Interoperability của một số cách sử dụng WS-Security |
| WS-Addressing | Định danh action, destination và correlation; là specification riêng |
| WS-SecurityPolicy | Mô tả security assertions/policy; không đồng nghĩa Basic Profile |

Không mặc định Basic Profile là đủ cho MTOM, WS-Security, WS-Addressing hay reliable messaging. Lập danh sách standards/profile thực sự dùng trong WSDL, policy và transport.

## 3. Chọn phiên bản profile đúng cách

Trong SOAP legacy và hiện đại có thể gặp tham chiếu WS-I Basic Profile 1.1, 1.2 hoặc 2.0. Chúng được phát triển cho phạm vi và standards khác nhau; không coi các version là tên gọi thay thế được.

### 3.1. Các câu hỏi cần xác định

| Câu hỏi | Vì sao quan trọng |
|---|---|
| SOAP 1.1 hay SOAP 1.2? | Envelope namespace, HTTP content type, fault model và binding khác |
| WSDL version nào? | Profile và tooling phải khớp description |
| Document/literal hay RPC/encoded? | Client generators hỗ trợ không đồng đều |
| Có MTOM/MIME attachments không? | Cần test attachment profile riêng |
| Có WS-Addressing không? | Action/To/ReplyTo và namespace cần thống nhất |
| Có WS-Security không? | Cần security profile và signed parts riêng |
| Có vendor extensions không? | Consumer độc lập có thể không hiểu |

### 3.2. Đừng lựa chọn version chỉ dựa trên năm phát hành

Một stack cũ có thể hỗ trợ tốt SOAP 1.1/WSDL 1.1 theo profile mà đối tác yêu cầu; một nền tảng mới hỗ trợ SOAP 1.2 không tự động tương thích với contract cũ. Cần đạt đúng subset và binding mà hai bên thực sự triển khai.

Khi WSDL import policy hoặc extension, ghi rõ URI/specification/version, required hay optional, consumer nào cần hiểu, fallback behavior và test chứng minh interoperability.

### 3.3. Viết claim có thể kiểm chứng

~~~text
Service contract: Orders SOAP API
WSDL: WSDL 1.1
Binding: SOAP 1.1, document/literal
Profile target: WS-I Basic Profile version agreed with partner
Schema set: version 3
Interop clients: vendor stack A, non-Java stack B
Evidence: request/response captures + contract tests + environment record
Known exclusions: MTOM and optional WS-Addressing tested separately
~~~

Đây là mẫu báo cáo, không phải chứng nhận tự động. Nếu tổ chức yêu cầu formal conformance, phải tuân thủ quy trình đánh giá cụ thể của họ.

## 4. Document/literal và tránh SOAP encoding

Một quyết định quan trọng khi thiết kế WSDL interoperable là sử dụng **document/literal** theo hướng contract-first.

### 4.1. Document/literal

WSDL binding mô tả message body là XML document theo schema. Payload có thể là:

~~~xml
<ord:SubmitOrderRequest xmlns:ord="urn:example:orders:v1">
  <ord:orderId>ORD-1001</ord:orderId>
  <ord:amount>125.50</ord:amount>
</ord:SubmitOrderRequest>
~~~

WSDL message tham chiếu global XSD element; SOAP Body mang element đó. Consumer validate/unmarshal theo QName và schema.

### 4.2. RPC/encoded

RPC/encoded mô tả lời gọi và serialization theo SOAP encoding rules. Client generators, serializer và runtimes có lịch sử hỗ trợ không đồng đều với SOAP encoding. Nhiều hệ thống enterprise ưu tiên document/literal để giữ XML Schema contract rõ ràng.

Đừng kết luận WSDL interoperable chỉ vì parser đọc được file. Hãy xem soap:binding, soap:body, use, message parts và global element references.

### 4.3. Document/literal wrapped

Document/literal wrapped là convention thường gặp: SOAP Body có một wrapper element đại diện operation, bên trong là parameters theo schema. Pattern này tiện cho code generation, nhưng phải giữ QName và schema ổn định. Đổi wrapper name/namespace là thay đổi wire contract.

## 5. Review WSDL 1.1

WSDL 1.1 mô tả types, messages, portType, binding, service và port. Mỗi phần có vai trò khác nhau; lỗi thường xuất hiện khi chúng không nhất quán.

### 5.1. WSDL fragment rút gọn

~~~xml
<wsdl:definitions
    xmlns:wsdl="http://schemas.xmlsoap.org/wsdl/"
    xmlns:soap="http://schemas.xmlsoap.org/wsdl/soap/"
    xmlns:xs="http://www.w3.org/2001/XMLSchema"
    xmlns:tns="urn:example:orders:v1"
    targetNamespace="urn:example:orders:v1">

  <wsdl:types>
    <xs:schema targetNamespace="urn:example:orders:v1"
               elementFormDefault="qualified">
      <xs:element name="SubmitOrderRequest">
        <xs:complexType>
          <xs:sequence>
            <xs:element name="orderId" type="xs:string"/>
          </xs:sequence>
        </xs:complexType>
      </xs:element>
    </xs:schema>
  </wsdl:types>

  <wsdl:message name="SubmitOrderInput">
    <wsdl:part name="parameters"
               element="tns:SubmitOrderRequest"/>
  </wsdl:message>

  <wsdl:portType name="OrdersPortType">
    <wsdl:operation name="SubmitOrder">
      <wsdl:input message="tns:SubmitOrderInput"/>
    </wsdl:operation>
  </wsdl:portType>

  <wsdl:binding name="OrdersSoapBinding"
                type="tns:OrdersPortType">
    <soap:binding style="document"
                  transport="http://schemas.xmlsoap.org/soap/http"/>
    <wsdl:operation name="SubmitOrder">
      <soap:operation soapAction="urn:example:orders:v1/SubmitOrder"/>
      <wsdl:input>
        <soap:body use="literal"/>
      </wsdl:input>
    </wsdl:operation>
  </wsdl:binding>

  <wsdl:service name="OrdersService">
    <wsdl:port name="OrdersPort" binding="tns:OrdersSoapBinding">
      <soap:address location="https://soap.example.test/orders"/>
    </wsdl:port>
  </wsdl:service>
</wsdl:definitions>
~~~

Đây là fragment minh họa quan hệ giữa WSDL components; WSDL production cần output/fault messages nếu operation có response/fault, imports/schema locations, namespaces, binding và service addresses khớp thực tế.

### 5.2. Checklist review WSDL

- wsdl:part dùng element hay type phải phù hợp document/rpc style và binding.
- soap:body use="literal" nhất quán với schema-driven message.
- Operation trong binding tương ứng operation trong portType.
- soapAction khớp client/endpoint mapping và HTTP request thực.
- soap:address là URL môi trường được công bố, không phải hostname nội bộ/dev.
- QName trong message, binding, portType, element trỏ namespace đúng.
- wsdl:import và xs:import/include resolve được từ consumer.
- SOAP headers/faults được mô tả đúng nếu contract yêu cầu.

### 5.3. WSDL compile được chưa đủ

WSDL parser có thể đọc file nhưng code generator ở vendor khác không hỗ trợ extension, schema layout hoặc binding convention cụ thể. Generate/consume WSDL bằng ít nhất một toolchain độc lập với toolchain tạo service và kiểm tra client thực gọi được.

## 6. Namespace và QName

XML prefix chỉ là alias; namespace URI và local name tạo thành QName. Hai XML có prefix khác nhau vẫn tương đương nếu QName giống nhau. Cùng local name nhưng namespace khác là element khác.

~~~xml
<ord:SubmitOrderRequest xmlns:ord="urn:example:orders:v1"/>
~~~

~~~xml
<ord:SubmitOrderRequest xmlns:ord="urn:example:orders:v2"/>
~~~

Hai payload không tương đương chỉ vì prefix/local name giống nhau.

### 6.1. elementFormDefault

elementFormDefault="qualified" ảnh hưởng cách local elements được namespace-qualified trong instance XML. Nếu schema/server/client hiểu khác qualification, JAXB-generated XML có thể khác QName mà validator mong đợi.

Kiểm tra targetNamespace, elementFormDefault, attributeFormDefault, global/local elements, form override, imports và JAXB annotations như XmlSchema/XmlElement.

### 6.2. Tránh so prefix trong code

Đừng so chuỗi prefix như ord:SubmitOrderRequest. Hãy so namespace URI + local part hoặc dùng Spring-WS @PayloadRoot(namespace=..., localPart=...). Prefix có thể khác giữa serializers mà QName vẫn giống nhau.

## 7. SOAPAction, HTTP headers và transport

Với SOAP 1.1 over HTTP, SOAPAction thường được dùng để chỉ operation intent theo binding. Các client stacks có thể gửi header quoted URI hoặc empty value tùy binding. SOAP 1.2 có quy ước action liên quan content type/action parameter; không áp quy tắc SOAP 1.1 máy móc cho SOAP 1.2.

### 7.1. Capture trên wire

Kiểm tra HTTP method/path, Content-Type đúng SOAP version, charset, SOAPAction/action parameter, Content-Length/transfer encoding, status code, Fault behavior và redirect/proxy/auth challenge.

### 7.2. SOAPAction không phải security proof

SOAPAction là routing/binding metadata do client gửi. Không dùng nó để xác thực caller hoặc quyết định bỏ WS-Security. Authentication, signature verification và authorization là những lớp riêng.

### 7.3. Spring-WS endpoint

~~~java
@Endpoint
public class OrdersEndpoint {
    private static final String NS = "urn:example:orders:v1";

    @PayloadRoot(namespace = NS,
                 localPart = "SubmitOrderRequest")
    @ResponsePayload
    public SubmitOrderResponse submit(
            @RequestPayload SubmitOrderRequest request) {
        return service.submit(request);
    }
}
~~~

Nếu mapping dùng SOAPAction hoặc WS-Addressing Action, kiểm thử bằng request HTTP thật do client độc lập tạo. @PayloadRoot không tự xác minh action hay WS-Security.

## 8. SOAP 1.1 và SOAP 1.2

Hai version khác Envelope namespace, fault model, HTTP binding/content type và một số header conventions. Client hỗ trợ SOAP 1.2 không tự động gọi được SOAP 1.1 endpoint chỉ bằng đổi Content-Type.

| Thành phần | SOAP 1.1 | SOAP 1.2 |
|---|---|---|
| Envelope namespace | http://schemas.xmlsoap.org/soap/envelope/ | http://www.w3.org/2003/05/soap-envelope |
| HTTP media type thường dùng | text/xml | application/soap+xml |
| Fault | faultcode, faultstring, detail | Code, Reason, Detail và subcode |
| Action | SOAPAction HTTP header thường gặp | action parameter theo SOAP 1.2 binding |
| mustUnderstand | SOAP 1.1 lexical rules | SOAP 1.2 boolean semantics |

Đây là khác biệt khái quát; implementation phải theo SOAP binding/specification và WSDL contract. Nếu hỗ trợ cả hai, coi đó là hai wire protocols cần test riêng.

## 9. XSD design cho consumers ngoài Java

XSD không nên dựa vào behavior chỉ JAXB mới hiểu. Consumer khác có thể generate classes hoặc parse XML bằng stack khác.

Ưu tiên global elements cho document/literal message roots; namespace/qualification nhất quán; scalar types và facets rõ; minOccurs/maxOccurs/nillable tường minh khi quan trọng; tránh type quá sâu, wildcards quá rộng và recursive shapes khó generate. Ghi rõ timezone, decimal precision, units và enum semantics. Không đưa custom Java class names vào wire contract.

### 9.1. Absent, empty, nil và default

- Absent: element không xuất hiện.
- Empty: element hiện diện nhưng text rỗng.
- Nil: element có xsi:nil="true" và declaration cho phép nillable.
- Default/fixed: semantics của schema; application mapping nên làm rõ.

Đừng kỳ vọng JAXB, .NET, PHP, C++ và integration brokers ánh xạ các trường hợp này giống nhau nếu chưa test.

### 9.2. Enumeration mở rộng

Consumer generated enum có thể không biết giá trị mới. Nếu state thường xuyên thay đổi, định nghĩa unknown-value strategy, deprecation/versioning hoặc representation phù hợp. Test consumer ngoài Java với enum mới.

## 10. WSDL imports/includes và publication

WSDL có thể import XSD từ file/URL khác. Client generator ở đối tác phải resolve được toàn schema graph; không dùng path chỉ có trên máy build.

- Dùng relative paths hoặc stable public URLs.
- Công bố mọi XSD/WSDL dependencies.
- Không để schema trỏ localhost, private host, workspace path hoặc dev environment.
- Test download WSDL và toàn bộ imports/includes từ network boundary như client.
- Pin versions/checksums của contract artifacts.
- Bảo vệ server khỏi external schema fetch do input không tin cậy bằng resolver whitelist.

### 10.1. Test WSDL từ góc nhìn consumer

1. Download WSDL qua public endpoint.
2. Theo toàn bộ wsdl:import, xsd:import và xsd:include.
3. Xác minh URI reachable và content type phù hợp.
4. Generate client bằng toolchain khác.
5. Gọi endpoint test bằng generated client.
6. Lưu WSDL/XSD đã nhận làm artifact để tái lập.

## 11. SOAP headers, faults và extensions

### 11.1. Headers có semantics rõ

Mỗi header cần QName/namespace ổn định, actor/role nếu có, mustUnderstand semantics, người tạo/người đọc, security requirements, quy tắc duplicate/missing/unknown và versioning. WS-Addressing, WS-Security và custom correlation header phải có namespace/version/action thống nhất. Vendor extension không khai báo có thể làm client khác từ chối hoặc bỏ qua.

### 11.2. Fault là một phần contract

Kiểm fault code/subcode theo SOAP version, reason không chứa stack trace/secret, detail schema và namespace, action nếu WS-Addressing dùng, HTTP status và khả năng parse bằng client độc lập. Không chỉ test success response.

### 11.3. Không serialize Java exception

Không đưa stack trace hoặc Java exception class name thẳng vào SOAP detail. Dùng fault DTO/schema ổn định, code/message kiểm soát và correlation ID cho điều tra nội bộ.

## 12. Attachments và MTOM

SOAP có thể mang attachments qua MIME/MTOM. Body XML có xop:Include tham chiếu Content-ID, bytes nằm ở MIME part khác. XSD validation không đủ để kiểm interoperability attachment.

Kiểm MTOM/XOP profile, SOAP version, MIME boundary, Content-Type, Content-ID, root part/start-info, attachment sizes, streaming/spooling, filename encoding, integrity/signing nếu policy yêu cầu, retries và cleanup temporary files. Client ngoài Java phải đọc đúng bytes.

Không giả định JAXB byte[] mapping giống streaming behavior của mọi toolchain; test peak memory và transport behavior với file lớn.

## 13. Spring-WS không tự bảo đảm WS-I conformance

Spring-WS hỗ trợ xây dựng SOAP endpoint contract-first, nhưng không tự chứng nhận mọi WSDL/schema hoặc mọi response tuân thủ WS-I profile.

### 13.1. Các điểm cấu hình cần review

- WSDL được review và version hóa như public API.
- XSD set đóng gói với đường dẫn ổn định.
- Request/response validation đúng version.
- SOAP message factory khớp SOAP version.
- Endpoint mappings namespace-aware.
- SOAPAction/WS-Addressing mapping được test.
- Fault handling theo contract.
- Security interceptors không bị bypass qua mappings khác.

### 13.2. JAXB là binding tool

Generated JAXB classes chỉ là Java representation của XML contract. Consumer ngoài Java không cần tái tạo Java getter/setter, package/class hierarchy, enum hay annotations. Họ cần hiểu WSDL/XSD và wire messages. Không đưa Java serialization hoặc JAXB metadata riêng vào SOAP payload.

### 13.3. Adapter giữa contract và domain

~~~text
SOAP XML
   → XSD validation
   → JAXB DTO
   → Contract mapper
   → Internal command/domain
   → Business service
   → Response mapper
   → JAXB DTO
   → SOAP XML
~~~

Giữ domain model độc lập generated DTO để thay đổi wire contract không lan toàn hệ thống. Mapper chuẩn hóa defaults/optional fields và semantics version cũ.

## 14. Kiểm thử liên vendor

### 14.1. Các cấp kiểm thử

| Cấp | Ví dụ | Bằng chứng |
|---|---|---|
| Schema unit test | Compile XSD, validate fixtures | XSD rules pass |
| WSDL lint/review | Binding, imports, message parts | Contract structure |
| JAXB round trip | Java marshal/unmarshal | Java mapping |
| Spring-WS integration | MockWebServiceClient | Dispatch/endpoint logic |
| HTTP integration | MessageDispatcherServlet + WebServiceTemplate | Servlet/transport |
| Cross-stack interoperability | Non-Java SOAP client gọi Java server và ngược lại | Wire compatibility độc lập |
| Partner UAT | Client thật và environment gần production | Acceptance |

Chỉ cross-stack tests mới phát hiện nhiều differences mà Java-to-Java tests bỏ sót. Dùng test certificates và endpoint sandbox, không production credentials.

### 14.2. Chọn implementation độc lập

Có thể dùng .NET SOAP client/WCF tooling, PHP SOAP extension, Python SOAP client library hoặc enterprise integration platform. Đây là ví dụ về độc lập implementation, không bảo đảm mọi version của các toolkit hỗ trợ cùng profile. Chọn stack đối tác thực dùng hoặc implementation khác vendor, pin version và lưu environment.

### 14.3. Hai chiều kiểm thử

**Non-Java client → Spring-WS server:** download WSDL, generate proxy, gửi request document/literal, validate response/Fault, kiểm SOAPAction/content type/header/namespace.

**Spring-WS client → non-Java server:** WebServiceTemplate tạo request, gọi endpoint sandbox, kiểm body/header/action, parse response/fault và kiểm MTOM/security nếu contract dùng.

Test cả hai chiều: một implementation có thể serialize kiểu bên kia chấp nhận nhưng deserialize response lại khác.

## 15. Bộ test interoperability tái lập

Lưu WSDL và XSD dependencies theo version, request/response fixtures, SOAP Fault fixtures, HTTP headers/captures, SOAP 1.1/1.2 test profiles, client generator/tool versions, test certificates, assertions QName/sequence/cardinality/nil/decimal/actions và expected business outcomes.

### 15.1. Ma trận test

| Ca test | Assertion |
|---|---|
| WSDL download | HTTP success, đúng service/port/address |
| Import graph | Mọi imports/includes resolve |
| Basic request | Client độc lập marshal đúng QName/body |
| Response | Client độc lập parse đúng values/collection/decimal |
| SOAPAction | Header/action match binding |
| Header absent/unknown | Hành vi đúng contract |
| SOAP 1.1 Fault | Consumer parse faultcode/faultstring/detail |
| SOAP 1.2 Fault | Consumer parse Code/Reason/Detail |
| Optional/nil | Absent/empty/nil semantics thống nhất |
| Enumeration | Known và unknown-value policy |
| Repeated values | Không mất item, đúng thứ tự |
| MTOM | Bytes và Content-ID đúng |
| Security | Signature/certificate/required actions theo policy |
| Invalid payload | Reject trước business side effects |
| Timeout/connection close | Không corrupt stream, retry có kiểm soát |

### 15.2. Wire capture quan trọng hơn log DTO

Lưu HTTP/SOAP capture đã redaction cho các ca quan trọng. Java logs chỉ cho biết DTO sau unmarshal, có thể che namespace URI, thứ tự XML, header thiếu, SOAPAction sai, content type, MIME parts hoặc Fault shape.

Capture phải loại password/token, signature values nhạy cảm, PII, private paths và dữ liệu nhạy cảm khác. Phân quyền/retention cho test artifacts.

### 15.3. So QName trong test

Đừng assert prefix literal. Dùng namespace-aware XPath/NamespaceContext để assert namespace URI + local part. Consumer khác Java cũng nên so QName thay vì so XML prefix text.

## 16. Lỗi liên vendor thường gặp

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Client generate proxy lỗi | WSDL extension/import không hỗ trợ | Rút gọn WSDL, dùng pattern portable |
| HTTP 415 | Content-Type/SOAP version sai | Đối chiếu binding và request |
| Operation không dispatch | SOAPAction/QName/namespace mismatch | Capture wire, kiểm mapping |
| XSD validation fail | Sequence, namespace, import hoặc occurrence | Validate raw payload theo XSD |
| Java chạy, .NET fail | Behavior phụ thuộc Java/toolchain | Non-Java generator và portable contract |
| Response parse fail | QName/order/type/enum không tương thích | Capture response, fixture tests |
| SOAPAction quoted khác kỳ vọng | Binding convention khác | Chốt contract và test client |
| Fault không parse | SOAP version/fault detail sai | Fault fixtures từng version |
| Schema import inaccessible | URL nội bộ/relative path sai | Publish schema graph ổn định |
| MTOM attachment rỗng | Content-ID/root part/stream sai | MIME captures và byte assertions |
| Signature verify fail | Canonicalization/coverage/algorithm khác | Security profile và cross-tool tests |
| Đối tác reject response | Validation khác hoặc XML không theo contract | Consumer validator độc lập |

### 16.1. Quy trình điều tra

1. Thu request/response capture đã redaction.
2. Xác định HTTP status, content type, SOAP version và SOAPAction.
3. Kiểm Envelope/Header/Body QName và namespace.
4. Validate raw Body/Fault theo XSD.
5. Kiểm WSDL binding/messages/parts.
6. Kiểm XSD import/include graph.
7. Tách security/MTOM/WS-Addressing để khoanh vùng nhưng không tắt trong production.
8. Reproduce bằng hai implementations với versions đã pin.
9. Ghi nguyên nhân, contract diff và regression fixture.

Không sửa ngẫu nhiên JAXB annotations, SOAPAction và WSDL cùng lúc; nhiều thay đổi đồng thời làm khó tìm root cause.

## 17. Case study: Java client chạy, vendor khác không gọi được

### 17.1. Hiện tượng

Spring-WS service công bố WSDL, Java client generate từ cùng XSD gọi thành công. Đối tác dùng SOAP toolkit khác generate proxy nhưng nhận HTTP 415 hoặc không dispatch operation.

### 17.2. Giả thuyết

- WSDL binding/pattern không được tool đối tác hỗ trợ.
- soapAction khác với request thực.
- SOAP 1.1/1.2 content type không khớp.
- Imported XSD trỏ hostname private hoặc không reachable.
- element qualification/namespace khác kỳ vọng.
- Response có sequence/choice/enum value client cũ không chấp nhận.

### 17.3. Xử lý

1. Thu WSDL mà đối tác thực download và lưu checksum.
2. Thu HTTP request capture của client độc lập đã redaction.
3. So Content-Type, SOAPAction, Envelope namespace và Body QName với binding.
4. Validate raw Body theo XSD công bố.
5. Generate client bằng toolchain độc lập trong CI.
6. Chọn document/literal và schema patterns mà consumers cùng hiểu.
7. Nếu thay đổi wire contract, phát hành version/endpoint mới hoặc rollout có backward support.
8. Chạy regression bằng Java và consumer độc lập.

### 17.4. Tiêu chí đóng

- WSDL tải được từ network boundary của đối tác.
- Imports/includes resolve.
- Client độc lập generate proxy và gọi operation.
- Server/client hiểu response/Fault đúng SOAP version.
- SOAPAction, namespace, sequence, optional/nil semantics đúng.
- Có captures redacted và tests trong CI.
- Không bắt đối tác phụ thuộc Java/JAXB-specific behavior.

## 18. Bài tập và checklist nghiệm thu

### 18.1. Bài tập

**Bài 1 — Java-to-Java pass:** Client JAXB cùng XSD gọi Spring-WS thành công. Đã chứng minh liên vendor?

**Đáp án:** Chưa. Cùng toolchain có thể chia sẻ assumptions/bugs; cần consumer độc lập và wire tests.

**Bài 2 — Prefix khác:** Client dùng prefix o, server dùng ord. Có lỗi namespace?

**Đáp án:** Không nếu namespace URI và local name giống nhau.

**Bài 3 — SOAPAction:** Body đúng nhưng không dispatch. Cần capture gì?

**Đáp án:** Content-Type, SOAPAction/action parameter, Envelope namespace, Body QName, binding và endpoint mapping.

**Bài 4 — WSDL import:** WSDL mở trong IDE nhưng đối tác không generate được. Vì sao?

**Đáp án:** XSD/WSDL import không reachable, relative base URI sai, private hostname hoặc extension không hỗ trợ.

**Bài 5 — SOAP 1.2:** Đổi Content-Type là đủ chuyển SOAP 1.1 sang 1.2?

**Đáp án:** Không. Envelope namespace, binding, action convention và fault model phải phù hợp.

**Bài 6 — Fault:** Chỉ test successful response đủ không?

**Đáp án:** Không. Fault structure/detail và SOAP version là nguồn lỗi riêng.

**Bài 7 — JAXB:** Consumer .NET không có JAXBElement. Contract có cần đổi giống Java class?

**Đáp án:** Không. Contract là XML/WSDL/XSD; Java classes chỉ là binding implementation.

**Bài 8 — MTOM:** XSD pass nhưng attachment 0 byte. Kiểm gì?

**Đáp án:** MIME boundary/root part, Content-ID, xop:Include, stream lifecycle và HTTP capture.

**Bài 9 — WS-Security:** Basic Profile test pass có chứng minh WS-Security interoperability?

**Đáp án:** Không. Cần test profile riêng, signed parts, canonicalization, certificates, algorithms và implementation độc lập.

**Bài 10 — Compliance claim:** Báo cáo “WS-I compliant” cần gì?

**Đáp án:** Profile/version, SOAP/WSDL binding, scope/exclusions, tools/versions, test matrix, wire captures và evidence độc lập.

### 18.2. Checklist contract review

- [ ] Ghi WS-I Basic Profile version/scope hai bên thống nhất.
- [ ] Nêu SOAP version và WSDL version/binding.
- [ ] Document/literal và use="literal" đúng.
- [ ] WSDL messages/parts/portType/binding/service/port nhất quán.
- [ ] SOAPAction/action parameter được test.
- [ ] QName/namespace/qualification ổn định.
- [ ] XSD types/facets/cardinality portable.
- [ ] Imports/includes reachable, không phụ thuộc máy dev.
- [ ] SOAP headers có QName/role/mustUnderstand/security semantics.
- [ ] Fault và modeled detail thuộc contract.
- [ ] MTOM/WS-Addressing/WS-Security được test theo profile riêng.
- [ ] Endpoint công bố address đúng môi trường.

### 18.3. Checklist interoperability

- [ ] Có ít nhất một client/toolchain độc lập ngoài Java.
- [ ] Test hai chiều theo phạm vi tích hợp.
- [ ] Client độc lập download WSDL và resolve schema graph.
- [ ] Client generate proxy không dựa custom Java extensions.
- [ ] Có HTTP/SOAP captures đã redaction.
- [ ] Assert Content-Type, SOAPAction, QName, sequence và namespace.
- [ ] Test normal response và Fault từng version.
- [ ] Test optional/nil/enumeration/repeated values.
- [ ] Test MTOM bytes nếu sử dụng.
- [ ] Test TLS/WS-Security riêng nếu contract dùng.
- [ ] Invalid payload bị reject trước business side effects.
- [ ] Lưu tool/runtime versions và contract checksum.

### 18.4. Checklist CI và vận hành

- [ ] WSDL/XSD lint/static validation chạy khi contract thay đổi.
- [ ] Schema compatibility tests với versions được hỗ trợ.
- [ ] Generate/compile consumer client bằng stack độc lập.
- [ ] Cross-stack request/response smoke tests trong pipeline.
- [ ] Contract artifacts version hóa và release cùng checksum.
- [ ] Có regression fixtures cho interoperability defects.
- [ ] Logs không lưu raw credentials, signatures, PII hoặc attachments.
- [ ] Dependency/tool upgrades chạy lại interoperability matrix.
- [ ] Định kỳ xác nhận partners vẫn dùng contract/profile đã thống nhất.

**Ghi nhớ:** WS-I Basic Profile giúp thu hẹp các lựa chọn SOAP/WSDL dễ gây khác biệt, nhưng nhãn profile hay file WSDL hợp lệ không tự chứng minh interoperability. Với Spring Web Services, giữ contract document/literal rõ ràng, namespace và binding nhất quán, schema graph có thể tải từ client, mô tả Fault/header/attachments chính xác và kiểm thử bằng SOAP stack độc lập ngoài Java. Lưu request/response captures đã redaction cùng tool versions và test fixtures để mọi tuyên bố tương thích có thể tái lập và kiểm tra lại.
