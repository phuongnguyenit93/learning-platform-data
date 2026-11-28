# So khớp payload, namespace, header và action của lời gọi

## 1. Vì sao phải kiểm tra SOAP request thực sự được gửi đi?

Trong module **SPRING_WEB_SERVICES**, SOAP client được xây dựng theo hướng contract-first. XSD xác định payload; WSDL mô tả operations, messages, bindings và endpoint; JAXB ánh xạ Java object sang XML; Spring-WS dùng WebServiceTemplate, message factory, marshaller, sender và interceptors để gửi request.

Một method Java có thể nhận object hợp lệ nhưng XML trên wire vẫn sai contract vì namespace, QName, element order, SOAP version, SOAPAction, WS-Addressing Action hoặc security headers không khớp. Hai XML elements có cùng local name nhưng namespace URI khác nhau là hai QName khác nhau. SOAPAction HTTP header và WS-Addressing Action header cũng là hai cơ chế riêng.

Kiểm thử client cần chứng minh request cuối cùng sau marshal/interceptors có đúng Envelope, Body, QName, schema structure, headers, action, SOAP version và security metadata. Đồng thời phải xác minh client phân loại đúng SOAP Fault, HTTP error, timeout và transport failure.

### Mục tiêu học tập

1. Phân biệt Java type, XML element QName và XSD type.
2. Kiểm tra namespace URI, prefix, local name và schema imports.
3. So khớp payload, element order, attributes, cardinality, nil và absent.
4. Phân biệt SOAP 1.1/1.2, Content-Type, SOAPAction và WS-Addressing Action.
5. Kiểm tra SOAP headers, correlation và mustUnderstand.
6. Dùng MockWebServiceServer xác minh request từ WebServiceTemplate.
7. Kiểm tra marshalling, interceptors, WS-Security và message factory.
8. Thiết kế positive/negative fixtures, schema assertions và transport tests.
9. Tách request expectation tests khỏi TLS/interoperability tests.

## 2. Từ Java object đến SOAP wire message

~~~mermaid
flowchart TD
    A["Application request DTO"] --> B["JAXB / Marshaller"]
    B --> C["SOAP MessageFactory"]
    C --> D["WebServiceMessage"]
    D --> E["ClientInterceptor chain"]
    E --> F["SOAP headers / WS-Security"]
    F --> G["WebServiceMessageSender"]
    G --> H["HTTP or other transport"]
    H --> I["Remote SOAP provider"]
~~~

Đây là phân rã khái niệm. Interceptor có thể thay đổi message trước khi gửi hoặc kiểm tra response sau khi nhận. Message factory quyết định SOAP envelope version; marshaller tạo payload; sender thực hiện transport.

### 2.1. Object đúng chưa chắc payload đúng

~~~java
public record GetOrderRequest(String orderId) {}
~~~

DTO không tự chứa đủ thông tin XML contract. JAXB mapping có thể tạo element sai namespace, sai tên local, wrapper khác hoặc thiếu root element nếu schema/code generation không cung cấp global element mapping như mong muốn.

Không chỉ assert Java property:

~~~java
assertEquals("ORD-100", request.orderId());
~~~

Hãy assert XML sau marshal có đúng root QName và child structure.

### 2.2. Contract identity

Một request cần được xác định bởi namespace URI, local element name, declared XSD type, SOAP Envelope namespace, operation/action binding và required headers. Prefix như ord, o hay ns2 chỉ là alias. Prefix thay đổi nhưng namespace URI/local name giữ nguyên thì QName không đổi; URI thay đổi thì QName đổi.

## 3. QName và namespace

~~~xml
<ord:GetOrderRequest xmlns:ord="urn:example:orders:v1">
  <ord:orderId>ORD-100</ord:orderId>
</ord:GetOrderRequest>
~~~

QName root:

~~~text
{urn:example:orders:v1}GetOrderRequest
~~~

### 3.1. Prefix không phải contract identity

~~~xml
<ord:GetOrderRequest xmlns:ord="urn:example:orders:v1"/>
~~~

~~~xml
<o:GetOrderRequest xmlns:o="urn:example:orders:v1"/>
~~~

Hai documents có root QName tương đương. Một test bắt buộc prefix ord có thể fail dù XML hợp lệ. Dùng namespace-aware XML matcher, QName assertion hoặc XPath có namespace mapping.

### 3.2. Namespace URI khác là request khác

~~~xml
<ord:GetOrderRequest xmlns:ord="urn:example:orders:v1"/>
~~~

~~~xml
<ord:GetOrderRequest xmlns:ord="urn:example:orders:v2"/>
~~~

Local name giống nhau nhưng QName khác; server dispatch theo v1 có thể reject v2.

### 3.3. Default namespace và attributes

~~~xml
<GetOrderRequest xmlns="urn:example:orders:v1">
  <orderId>ORD-100</orderId>
</GetOrderRequest>
~~~

Default namespace áp dụng cho unprefixed elements trong scope. Unprefixed attributes không tự động thuộc default namespace. Test element QName và attribute QName riêng.

### 3.4. Element không namespace

~~~xml
<GetOrderRequest>
  <orderId>ORD-100</orderId>
</GetOrderRequest>
~~~

Nếu XSD yêu cầu target namespace, payload này không tương đương. Prefix thiếu tự nó không phải lỗi; namespace URI của mỗi element mới quyết định QName.

## 4. XSD global element, type và wrapper

~~~xml
<xs:schema
    xmlns:xs="http://www.w3.org/2001/XMLSchema"
    targetNamespace="urn:example:orders:v1"
    xmlns:ord="urn:example:orders:v1"
    elementFormDefault="qualified">

  <xs:element name="GetOrderRequest"
              type="ord:GetOrderRequestType"/>

  <xs:complexType name="GetOrderRequestType">
    <xs:sequence>
      <xs:element name="orderId" type="xs:string"/>
    </xs:sequence>
  </xs:complexType>
</xs:schema>
~~~

GetOrderRequestType là type; GetOrderRequest là global element. JAXB có thể generate class cho type cùng ObjectFactory method tạo JAXBElement cho global element tùy generation settings.

### 4.1. Test global element

Không chỉ kiểm Java class; kiểm root QName sau marshal. Spring-WS endpoint mapping thường dispatch theo root QName.

### 4.2. elementFormDefault

- qualified: local elements được qualify theo target namespace.
- unqualified: local elements có thể không namespace.
- form trên declaration có thể override default.

Prefix ở root không đảm bảo child có namespace đúng. Test nhiều child levels và attributes.

### 4.3. JAXBElement và ObjectFactory

~~~java
JAXBElement<GetOrderRequestType> element =
    objectFactory.createGetOrderRequest(requestType);
~~~

Tùy schema generation, truyền type object trực tiếp có thể không cung cấp root element metadata như mong muốn. Test code generation artifacts và XML root QName thực tế.

## 5. Payload structure, order và cardinality

XSD xs:sequence yêu cầu thứ tự element theo declaration. xs:choice và xs:all có semantics khác; không sắp xếp XML theo alphabet nếu schema khai sequence.

~~~xml
<ord:SubmitOrderRequest xmlns:ord="urn:example:orders:v1">
  <ord:orderId>ORD-200</ord:orderId>
  <ord:customerId>CUST-10</ord:customerId>
  <ord:quantity>2</ord:quantity>
</ord:SubmitOrderRequest>
~~~

### 5.1. Occurrence

- minOccurs=0: element có thể vắng.
- minOccurs=1: element phải có ít nhất một lần.
- maxOccurs=1: tối đa một occurrence.
- maxOccurs=unbounded: nhiều occurrence.

Test zero, one, boundary và multiple values. Java List rỗng và null có thể marshal khác nhau.

### 5.2. Attributes

XSD attribute có use=required/optional, qualification, default và fixed rules riêng. Assert presence, namespace và lexical value.

### 5.3. Absent, empty và value

~~~xml
<!-- Absent -->
<ord:Request xmlns:ord="urn:example:orders:v1"/>

<!-- Present but empty -->
<ord:Request xmlns:ord="urn:example:orders:v1">
  <ord:reference/>
</ord:Request>

<!-- Present with value -->
<ord:Request xmlns:ord="urn:example:orders:v1">
  <ord:reference>ABC-1</ord:reference>
</ord:Request>
~~~

Empty string có thể hợp xs:string nhưng fail minLength/pattern; absent có thể fail minOccurs=1.

## 6. Optional, nillable và defaults

| XSD rule | XML form | Ý nghĩa |
|---|---|---|
| minOccurs=0 | Element absent | Không cung cấp |
| nillable=true | xsi:nil=true | Element có mặt nhưng nil |
| default=X | Element vắng hoặc schema default xử lý theo rules | Giá trị default |
| fixed=X | Giá trị theo fixed constraint | Không tùy biến |

~~~xml
<ord:middleName
    xmlns:ord="urn:example:person:v1"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
    xsi:nil="true"/>
~~~

### 6.1. JAXB null có thể tạo absent hoặc nil

Behavior phụ thuộc generated annotations, JAXBElement, nillable, wrapper và marshaller implementation. Java null không phải lúc nào cũng serialize thành xsi:nil; có thể element bị bỏ qua.

### 6.2. Test riêng từng case

1. Java property null.
2. Element omitted.
3. xsi:nil=true.
4. Empty element.
5. Value bình thường.
6. Value vi phạm pattern/min/max.

Các trường hợp này quan trọng khi business phân biệt unknown, not applicable và empty.

### 6.3. Decimal, date và timezone

Kiểm lexical XML:

- xs:decimal dùng dấu chấm, không dùng locale comma.
- xs:date và xs:dateTime phải theo lexical format XSD.
- Z/offset có thể thay đổi semantics.
- Precision, scale, rounding và boundary cần test.
- Không dựa default JVM locale/timezone khi serialize.

## 7. XSD validation phía client

Marshaller không phải lúc nào cũng tự validate payload theo XSD. Có thể cấu hình schema trên JAXB/Spring marshaller hoặc validate fixture bằng schema-aware tooling.

~~~java
marshaller.setSchema(
    schemaFactory.newSchema(
        new ClassPathResource("xsd/orders.xsd").getURL()
    )
);
~~~

API cụ thể phụ thuộc Jaxb2Marshaller/JAXB RI và Spring version.

### 7.1. Schema dependency closure

WSDL có thể import nhiều XSD; include/import dùng relative path và target namespace. Test phải resolve toàn bộ dependency closure, không chỉ root schema.

### 7.2. Invalid fixtures

Chuẩn bị cases thiếu required element, sai namespace, order sai, type/lexical sai, facet violation, enum unknown, nil không được phép, duplicate singleton và unknown element theo policy. Xác định lỗi phát sinh tại marshal/schema validation hay remote provider.

## 8. SOAP 1.1 và SOAP 1.2

| Thuộc tính | SOAP 1.1 | SOAP 1.2 |
|---|---|---|
| Envelope namespace | http://schemas.xmlsoap.org/soap/envelope/ | http://www.w3.org/2003/05/soap-envelope |
| HTTP Content-Type thường dùng | text/xml | application/soap+xml |
| Action | Thường qua SOAPAction header | Action parameter/WS-A tùy binding |
| Fault | faultcode/faultstring/detail | Code/Reason/Detail |

### 8.1. Message factory

WebServiceTemplate phải dùng message factory tương ứng WSDL binding. Không dùng SOAP 1.1 factory chỉ vì fixture test được viết theo SOAP 1.1 khi service yêu cầu SOAP 1.2.

### 8.2. Test Envelope và Content-Type

Assert Envelope QName, Header/Body placement, HTTP content type và binding trong transport integration tests. Mock payload test đơn thuần không chứng minh HTTP metadata thực.

## 9. SOAPAction và WS-Addressing Action khác nhau

### 9.1. SOAPAction

Trong SOAP 1.1 HTTP binding, SOAPAction thường là HTTP request header. WSDL binding có thể định nghĩa action URI cho operation.

### 9.2. WS-Addressing Action

~~~xml
<wsa:Action
    xmlns:wsa="http://www.w3.org/2005/08/addressing">
  urn:example:orders:GetOrder
</wsa:Action>
~~~

Đây là SOAP Header element, không phải HTTP SOAPAction. WS-Addressing Action có thể được ký nếu security policy yêu cầu.

### 9.3. Action consistency tests

Với mỗi operation, kiểm SOAPAction theo WSDL; WS-A Action khi binding dùng; Action khớp operation/Body QName; To/ReplyTo/MessageID đúng policy; không gửi Action operation khác; signed Action có trong signature references khi bắt buộc. Một giá trị không tự điền cả hai cơ chế.

## 10. SOAP headers

Headers có thể mang routing, correlation, authentication, transaction context hoặc partner metadata; chúng cũng thuộc contract.

~~~xml
<ord:ClientContext
    xmlns:ord="urn:example:orders:headers:v1">
  <ord:correlationId>corr-100</ord:correlationId>
  <ord:clientVersion>2.4.0</ord:clientVersion>
</ord:ClientContext>
~~~

Test header QName, namespace, cardinality, đúng vị trí Header chứ không nằm trong Body, không duplicate, correlation propagation và không ghi đè security-managed fields.

### 10.1. mustUnderstand

SOAP header có thể đánh dấu mustUnderstand. Receiver phải xử lý theo SOAP version semantics; nếu không hiểu required header, có thể trả Fault. Client chỉ gửi header khi contract/server hỗ trợ.

## 11. WebServiceTemplate pipeline

~~~java
@Bean
public WebServiceTemplate ordersWebServiceTemplate(
        Jaxb2Marshaller marshaller,
        WebServiceMessageSender sender,
        ClientInterceptor[] interceptors) {

    WebServiceTemplate template = new WebServiceTemplate();
    template.setMarshaller(marshaller);
    template.setUnmarshaller(marshaller);
    template.setMessageSender(sender);
    template.setInterceptors(interceptors);
    return template;
}
~~~

Đây là skeleton; endpoint URI, message factory, SOAP version, timeout, error resolver và credentials cần cấu hình riêng.

### 11.1. Marshalling

Test object-to-XML, root QName, field names, attributes, namespace qualification, dates/decimals và nil behavior.

### 11.2. Client interceptors

ClientInterceptor có thể thêm/check SOAP headers, log metadata, ký/mã hóa message hoặc xử lý response/Fault. Kiểm thứ tự chain và output cuối sau toàn bộ interceptors.

### 11.3. Message callback

WebServiceMessageCallback có thể thiết lập SOAPAction/header bổ sung. Test callback output sau marshal; không ghi đè header do security policy quản lý.

### 11.4. Sender

Sender chịu trách nhiệm transport. Mock request test không chứng minh timeout, TLS, mTLS, hostname verification, proxy hoặc HTTP header behavior. Cần transport integration tests.

## 12. MockWebServiceServer

MockWebServiceServer thuộc Spring-WS client testing support. Nó gắn expectations vào WebServiceTemplate, kiểm request gửi ra và trả response giả lập.

~~~java
@ExtendWith(SpringExtension.class)
@ContextConfiguration(classes = OrdersClientTestConfig.class)
class OrdersClientTest {

    @Autowired
    WebServiceTemplate webServiceTemplate;

    MockWebServiceServer mockServer;

    @BeforeEach
    void setUp() {
        mockServer = MockWebServiceServer
            .createServer(webServiceTemplate);
    }

    @Test
    void sendsGetOrderWithExpectedPayload() {
        Source request = new StringSource("""
            <ord:GetOrderRequest
                xmlns:ord="urn:example:orders:v1">
              <ord:orderId>ORD-100</ord:orderId>
            </ord:GetOrderRequest>
            """);

        mockServer.expect(payload(request))
            .andRespond(withPayload(new StringSource("""
                <ord:GetOrderResponse
                    xmlns:ord="urn:example:orders:v1">
                  <ord:orderId>ORD-100</ord:orderId>
                  <ord:status>PROCESSING</ord:status>
                </ord:GetOrderResponse>
                """)));

        ordersClient.getOrder("ORD-100");
        mockServer.verify();
    }
}
~~~

Skeleton minh họa; imports, matchers, client và configuration phụ thuộc Spring-WS version.

### 12.1. Expectations và verify

Khai báo expectations, thực hiện operation rồi gọi verify() để bảo đảm request thực sự được gửi. Nếu method không gọi template, test không verify có thể pass giả.

### 12.2. Exact XML hay XML-aware matcher?

Exact string comparison có thể fail vì whitespace/prefix. Ưu tiên XML matchers, XPath có namespace mapping hoặc custom RequestMatcher. Giữ exact fixture khi serialization detail thực sự là một phần contract.

### 12.3. Headers và HTTP metadata

Custom matcher có thể inspect SOAP message/header mà harness cung cấp. HTTP headers thực tế cần HTTP/transport integration; không suy mọi HTTP metadata đều nằm trong SOAP object.

## 13. Namespace-aware assertions

XPath test cần prefix-to-URI mapping rõ ràng:

~~~java
Map<String, String> namespaces = Map.of(
    "ord", "urn:example:orders:v1"
);
~~~

Prefix trong XPath có thể khác request; điều quan trọng là namespace URI.

### 13.1. Cardinality và value

~~~text
count(/ord:GetOrderRequest/ord:orderId) = 1
count(/ord:GetOrderRequest/ord:tenantId) = 0
string(/ord:GetOrderRequest/ord:orderId) = 'ORD-100'
~~~

XPath engine phải được cấu hình NamespaceContext.

### 13.2. Order và attributes

Đọc DOM child element QNames và assert sequence theo XSD. Không dựa index text nodes/whitespace. Assert attribute namespace URI riêng vì unprefixed attributes không thuộc default namespace.

## 14. SOAPAction và transport metadata tests

| Test | SOAP version | Action/header | Kỳ vọng |
|---|---|---|---|
| S1 | SOAP 1.1 | SOAPAction đúng | Định tuyến đúng |
| S2 | SOAP 1.1 | SOAPAction thiếu/sai | Binding/provider behavior |
| S3 | SOAP 1.2 | Content-Type đúng | SOAP 1.2 binding |
| S4 | SOAP 1.2 | Action parameter sai | Reject/dispatch Fault |
| S5 | Theo policy | WS-A Action đúng | Dispatch đúng |
| S6 | Theo policy | WS-A Action khác Body | Reject nếu contract yêu cầu |
| S7 | WS-A enabled | To/ReplyTo sai | Addressing Fault/policy reject |
| S8 | Signed headers | Action đổi sau ký | Signature validation fail |

MockWebServiceServer có thể kiểm message-level data; HTTP header thật cần transport-level integration.

## 15. WS-Security trong outbound request tests

Không chỉ assert Security header có ds:Signature. Kiểm:

- Timestamp tồn tại, TTL đúng.
- Signature references đúng SOAP Body và required headers.
- Signer certificate/key identifier đúng.
- Encryption target/recipient đúng.
- Protection order và algorithms theo policy.
- Không có credentials bị ghi đè.
- Securement failure không phát request không bảo vệ.

Dùng WSS4J test fixtures để thực sự verify signature/decrypt với test truststore/key material độc lập. Không dùng trust-all hoặc chỉ compare SignatureValue XML string. Logs/test reports không được in passwords, private keys hoặc plaintext nhạy cảm.

## 16. Response, Fault và lỗi transport

Kiểm normal SOAP response, Fault Detail, HTTP 4xx/5xx, malformed response, unexpected SOAP version/content type, timeout và connection reset.

### 16.1. Fault fixture

Tạo fixture SOAP 1.1 hoặc SOAP 1.2 theo binding. Assert error code/detail và business exception mapping bằng XML-aware assertions để tránh brittle prefix/format comparison.

### 16.2. Retry classification

Chỉ retry transient failure đã định nghĩa. Validation Fault, authentication failure và business rejection thường không retry vô hạn. Side-effecting operation cần idempotency key.

### 16.3. No Body response

Một số binding/operation có response patterns đặc thù. Không coi mọi response thiếu JAXB payload là success nếu contract không quy định.

## 17. Negative request tests

| ID | Điều kiện | Kỳ vọng |
|---|---|---|
| C01 | Required field null/absent | Local validation/marshal fail nếu schema yêu cầu |
| C02 | Namespace URI sai | Matcher/schema test fail |
| C03 | Root QName sai | Contract test bắt mismatch |
| C04 | Element order sai | XSD validation fail |
| C05 | Enum/lexical value invalid | Fail trước send nếu validation bật |
| C06 | SOAP version sai | Message factory/binding fail |
| C07 | SOAPAction sai | Request matcher fail |
| C08 | WS-A Action không khớp | Header/contract test fail |
| C09 | Required SOAP header thiếu | Local test fail |
| C10 | Signing alias thiếu | Securement fail, không gửi plaintext |
| C11 | Signature thiếu required parts | Crypto verification fail |
| C12 | Recipient certificate sai | Receiver interoperability test fail |
| C13 | Timeout | Exception/retry policy đúng |
| C14 | SOAP Fault | Exception mapping đúng |
| C15 | Malformed response XML | Unmarshal failure, không trả object giả |

Một số mismatch chỉ provider phát hiện. Khi đó integration test cần chứng minh provider reject đúng.

## 18. Marshalling edge cases

| Data | Fixtures |
|---|---|
| String | Empty, whitespace, maxLength, Unicode, pattern |
| Decimal | Min/max, precision, scale, negative/zero |
| Integer | Min/max, overflow |
| Date | Leap day, boundaries, invalid date |
| DateTime | UTC, offset, fractional seconds, timezone |
| Boolean | XML lexical true/false |
| Enumeration | All supported values, unknown value |
| Binary/base64 | Empty, small, size limit |
| Collection | Empty, one, max, repeated |
| Optional/nillable | Absent, nil, empty, value |

### 18.1. Locale independence

Serialize decimal/date không phụ thuộc default locale. Chạy fixtures dưới locale khác để phát hiện formatter mặc định thay XML lexical mapping.

### 18.2. Deterministic time

Nếu request chứa Timestamp/date, inject Clock/time provider khi phù hợp. Test TTL/clock skew không phụ thuộc thời điểm chạy.

## 19. Custom callback, interceptor order và concurrency

Ví dụ thiết lập SOAPAction:

~~~java
webServiceTemplate.marshalSendAndReceive(
    request,
    message -> {
        SoapMessage soapMessage = (SoapMessage) message;
        soapMessage.setSoapAction(
            "urn:example:orders:GetOrder"
        );
    }
);
~~~

Ví dụ này đặt SOAPAction; WS-Addressing Action cần integration thích hợp riêng.

### 19.1. Test callback

Xác minh callback được gọi và header đúng; không duplicate security header, sai namespace hoặc ghi đè mustUnderstand ngoài ý muốn.

### 19.2. Interceptor order

Nếu interceptor thêm custom header rồi interceptor khác ký message, signature phải chạy sau khi parts cần bảo vệ đã có. Verify final outbound XML/signature thực, không chỉ test mỗi interceptor độc lập.

### 19.3. Thread safety

Không lưu per-request mutable state dùng chung trong callback/interceptor. Chạy concurrent calls và kiểm headers/correlation không bị leak giữa requests.

## 20. Chẩn đoán request mismatch

| Triệu chứng | Nguyên nhân có thể | Kiểm tra |
|---|---|---|
| Unknown operation | Root QName/Action sai | URI, local name, dispatch |
| XSD validation fail | Type/order/cardinality sai | Sequence/facets |
| Child không được nhận | elementFormDefault/namespace | QName từng child |
| JAXB không marshal root | Thiếu global element/JAXBElement | ObjectFactory/annotations |
| Nil biến thành absent | Mapping nillable/null | Generated metadata |
| SOAP 1.2 endpoint reject | Envelope/content type 1.1 | MessageFactory/sender |
| Wrong action | SOAPAction và WS-A khác nhau | WSDL binding/headers |
| WS-Security reject | Signature parts/cert/key ID | WSS4J fixtures |
| Fault unmarshal fail | Fault QName/schema mismatch | SOAP version/detail |
| Chỉ production fail | Proxy/header/TLS khác mock | Transport tests |

### 20.1. Quy trình debug

1. Xác nhận endpoint URI và SOAP version.
2. Capture sanitized request ở test environment.
3. Kiểm Envelope namespace.
4. Kiểm Body root QName.
5. Kiểm child/attribute QNames và order.
6. Validate với đúng XSD closure.
7. Kiểm SOAPAction và WS-Addressing Action.
8. Kiểm required headers/mustUnderstand.
9. Verify WS-Security bằng test keys.
10. Kiểm HTTP Content-Type/headers và sender.
11. Đối chiếu provider Fault.
12. Lưu regression fixture.

Không log Authorization headers, UsernameToken, private keys, decrypted payload hoặc production data.

## 21. Contract fixtures và version control

~~~text
src/test/resources/contracts/orders/v1/
  wsdl/orders.wsdl
  xsd/orders.xsd
  requests/get-order.xml
  requests/submit-order.xml
  responses/get-order.xml
  faults/order-not-found.xml
  security/signed-get-order.xml
~~~

Đây là convention minh họa. Fixture thay đổi phải review cùng contract version; không update expected request chỉ để test pass khi chưa xác định contract change.

### 21.1. Schema closure

Lưu toàn bộ WSDL import/XSD include dependencies hoặc XML catalog. Build không phụ thuộc schema URL mutable ngoài kiểm soát.

### 21.2. Secret hygiene

Fixtures dùng synthetic IDs/certificates. Không commit production credentials/private keys. Test key material chỉ ở nơi được phép và có owner/rotation policy.

### 21.3. Signed XML canonicalization

Không normalize XML làm đổi signature semantics. Với signed XML, dùng XML Signature-aware verification/canonicalization thay regex strip whitespace/prefix.

## 22. Interoperability với SOAP stack khác

MockWebServiceServer xác minh Spring-WS client integration, không thay provider thực. Khác biệt có thể đến từ JAXB RI/MOXy, .NET/WCF, SOAP 1.1/1.2, WS-Addressing version, WS-Security profile/algorithms, canonicalization, MTOM, charset, Fault detail, proxy và HTTP content type.

### 22.1. Partner certification

Tạo positive/negative fixtures được partner chấp nhận và test staging với test certificates/identities.

### 22.2. Consumer compatibility

Khi provider thay WSDL/XSD, regenerate/test client và so request wire-level. Build pass không chứng minh runtime dispatch/security pass.

### 22.3. Production-like environment

Dùng SOAP version, message factory, TLS, WS-Security, proxy và sender settings gần deployment. Dùng secrets test riêng.

## 23. CI strategy và release gates

| Stage | Tests |
|---|---|
| Unit | DTO mapping, QName metadata, callback |
| Component | Marshalling, WebServiceTemplate request, headers/actions |
| Contract | XSD/WSDL, fixtures, bindings |
| Security | WS-Security signatures/parts, redaction |
| Transport | HTTP headers, Content-Type, TLS/mTLS, timeout |
| Integration | Provider endpoint, Fault mapping, partner fixtures |
| Compatibility | Generated clients với contract release pin |

Fail build khi root QName sai, required element thiếu, order invalid, SOAP version/action sai, required header thiếu/duplicate, signature thiếu parts, securement failure vẫn gửi request, Fault mapping sai, secrets lọt logs hoặc imports không resolve.

Khi fail, lưu sanitized request/response, contract version/checksum, SOAP version, operation QName, matcher path và interceptor phase. Không lưu credentials/raw sensitive production message.

## 24. Bài thực hành: kiểm thử Orders SOAP client

Xây client dùng WSDL/XSD namespace urn:example:orders:v1 với WebServiceTemplate.

### Nhiệm vụ

1. Pin WSDL/XSD và toàn bộ imports/includes.
2. Generate JAXB classes từ schema.
3. Xây GetOrder và SubmitOrder requests.
4. Cấu hình Jaxb2Marshaller, message factory và WebServiceTemplate.
5. Dùng MockWebServiceServer kiểm payload.
6. Assert root QName/namespace URI, không phụ thuộc prefix.
7. Assert child QNames và sequence theo XSD.
8. Test optional/required/nillable/empty.
9. Test decimal/date/timezone/enum boundaries.
10. Assert SOAP 1.1/1.2 Envelope đúng WSDL.
11. Kiểm SOAPAction riêng WS-Addressing Action.
12. Kiểm custom headers và correlation ID.
13. Kiểm interceptor order và final outbound message.
14. Verify signature/required parts bằng WSS4J fixture nếu có WS-Security.
15. Test SOAP Fault, HTTP error, timeout và malformed response.
16. Test HTTP Content-Type/headers/TLS bằng transport integration nếu cần.
17. Chạy interoperability với provider/partner stack.
18. Lưu sanitized fixtures và contract release identity.

**Tiêu chí đạt:** Client gửi đúng QName, payload, headers, action, SOAP version; invalid values được bắt theo validation policy; security parts đúng; Fault/transport errors không bị nhầm business success.

### 24.1. Tình huống tự kiểm

**A:** Test string fail vì prefix đổi ord sang ns2, namespace URI/local name giống nhau. Có phải contract bị phá? Assertion nào phù hợp?

**B:** SOAPAction đúng nhưng WS-Addressing Action sai. Vì sao không thể coi hai giá trị là một?

**C:** JAXB null tạo absent, trong khi XSD cho phép xsi:nil=true. Làm sao test phân biệt?

**D:** MockWebServiceServer pass nhưng partner reject Content-Type và TLS profile. Cần thêm test loại nào?

## 25. Checklist trước khi release SOAP client

- [ ] WSDL/XSD version và imports/includes được pin.
- [ ] Root QName đúng namespace/local name.
- [ ] Child elements/attributes có namespace đúng.
- [ ] Element order/cardinality/facets hợp XSD.
- [ ] Absent/nil/empty/default được test riêng.
- [ ] Decimal/date/timezone/enum lexical values đúng.
- [ ] SOAP 1.1/1.2 Envelope/message factory đúng.
- [ ] HTTP Content-Type/SOAPAction đúng binding.
- [ ] WS-Addressing Action/To/ReplyTo/MessageID đúng policy.
- [ ] Custom headers/correlation/mustUnderstand đúng.
- [ ] Client interceptors/callback chạy đúng order.
- [ ] WS-Security bảo vệ đúng parts.
- [ ] MockWebServiceServer expectations được verify.
- [ ] SOAP Fault/HTTP error/timeout/malformed response được phân loại.
- [ ] TLS/mTLS/HTTP headers được integration test khi cần.
- [ ] Test không phụ thuộc prefix/whitespace vô nghĩa.
- [ ] Fixtures sanitized và version hóa.
- [ ] Không có credentials/private keys trong logs/artifacts.
- [ ] Có interoperability evidence khi cần.

## 26. Ghi nhớ

- **Java object đúng chưa chứng minh XML request đúng.** Kiểm payload sau marshal.
- **QName = namespace URI + local name; prefix chỉ là alias.**
- **XSD type khác global element;** JAXB có thể cần ObjectFactory/JAXBElement.
- **Absent, empty và xsi:nil khác nhau.** Test riêng.
- **Element order/cardinality/facets** phải đúng schema.
- **SOAP 1.1 và SOAP 1.2** khác Envelope namespace, Content-Type và Fault.
- **SOAPAction khác WS-Addressing Action.** Kiểm cả hai theo binding/policy.
- **MockWebServiceServer** test WebServiceTemplate request, không thay TLS/HTTP/interoperability.
- **Chỉ thấy ds:Signature chưa đủ.** Verify signer, references và required parts.
- **Wire fixtures và transport tests** bắt lỗi mà DTO unit tests không thấy.

**Câu hỏi tự kiểm tra:** Spring-WS client marshal đúng object GetOrder nhưng server báo unknown operation. Body root có local name GetOrderRequest, prefix ord và SOAPAction đúng, nhưng namespace URI là urn:example:orders:v2 trong khi WSDL dùng v1; WS-Addressing Action cũng trỏ v2. Hãy giải thích QName mismatch, phân biệt hai action, đề xuất MockWebServiceServer assertions và các transport/interoperability tests cần thiết.

## 27. Tài liệu tham khảo để đối chiếu

- Spring Web Services Reference: WebServiceTemplate, marshalling, client interceptors, client testing, SOAP message factories.
- Spring Framework Reference: OXM/JAXB support và schema resources.
- Jakarta XML Binding API/specification: global elements, JAXBElement, namespaces và marshalling.
- W3C XML Namespaces/XML Schema: QName, targetNamespace, elementFormDefault, occurrence/facets.
- W3C SOAP 1.1/1.2 và WSDL 1.1: envelope, HTTP binding, SOAPAction và Fault.
- OASIS WS-Addressing/WS-Security: Action/header semantics, signature và token profiles.
- Apache WSS4J documentation: outbound actions, signature parts, Crypto và validation.
- Provider/partner contract: SOAP binding, headers, certificates và interoperability.

API names, matchers, default SOAP version và security behavior khác theo Spring-WS/JAXB/WSS4J version. Pin dependencies, kiểm đúng WSDL/XSD release và xác minh bằng fixtures cùng transport integration trên stack thực tế.

