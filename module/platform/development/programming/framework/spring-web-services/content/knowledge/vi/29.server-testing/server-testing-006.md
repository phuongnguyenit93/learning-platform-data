
# Kiểm tra payload đúng XSD và các trường hợp không hợp lệ

> **Chương:** Kiểm thử máy chủ  
> **Module:** SPRING_WEB_SERVICES — phát triển dịch vụ SOAP theo hướng contract-first với Spring Web Services, thiết kế XSD/WSDL, ánh xạ JAXB và xây dựng endpoint cùng SOAP client; xử lý SOAP Fault, interceptor, XML security, WS-Security, chứng chỉ và kiểm thử tương thích trong tích hợp doanh nghiệp.

## 1. Vì sao phải kiểm tra XSD ngay tại SOAP server?

Một SOAP request có thể là XML well-formed, có Envelope đúng chuẩn SOAP và thậm chí JAXB có thể chuyển nó thành Java object, nhưng payload vẫn vi phạm XSD công bố. Ví dụ, XSD yêu cầu orderId, giới hạn quantity là số nguyên dương và quy định orderId xuất hiện trước quantity. Request thiếu orderId, gửi chữ vào quantity hoặc đảo thứ tự element đều không đáp ứng contract.

Nếu server không validate payload theo schema, request sai có thể đi sâu vào endpoint và tạo lỗi khó dự đoán ở business layer. Có hai hệ quả thường gặp: client hợp lệ bị từ chối muộn bằng lỗi nội bộ khó hiểu; hoặc payload sai được chấp nhận một phần, tạo dữ liệu thiếu, sai kiểu hay trạng thái nghiệp vụ không nhất quán.

Trong Spring Web Services, có thể kiểm tra payload qua XSD validator hoặc cấu hình interceptor như PayloadValidatingInterceptor. Mục tiêu là chứng minh **payload thỏa schema đúng version trước khi endpoint thực hiện nghiệp vụ**, đồng thời kiểm tra các payload phải bị từ chối.

Sau bài học, bạn có thể phân biệt XML well-formed, SOAP Envelope hợp lệ, XSD-valid payload và business-valid request; thiết kế positive/negative fixtures; kiểm tra QName, sequence, required/optional, occurrence, nil, datatype và facets; cấu hình request/response validation; viết JUnit và Spring-WS integration tests; xác minh request sai schema không tạo side effects; và đưa regression tests vào CI.

**Nguyên tắc:** test một payload hợp lệ chứng minh server có thể xử lý một trường hợp đúng. Test payload không hợp lệ chứng minh server thực sự từ chối các vi phạm contract. Cần cả hai nhóm.

## 2. Bốn tầng kiểm tra cần tách biệt

| Tầng | Câu hỏi | Ví dụ lỗi |
|---|---|---|
| XML parsing / well-formedness | XML có cú pháp hợp lệ? | Tag không đóng, attribute quote sai |
| SOAP protocol | Envelope/Header/Body có đúng SOAP version? | Envelope namespace sai, Body thiếu |
| XSD payload validation | QName, thứ tự, type, facets, cardinality có đúng? | Thiếu required field, enum lạ |
| Business validation | Request hợp schema nhưng có được phép/thỏa nghiệp vụ? | Order đã đóng, quota vượt giới hạn |

Một payload có thể vượt tầng trước nhưng fail ở tầng sau. Ví dụ XML sau well-formed nhưng sai XSD nếu quantity được khai báo xs:positiveInteger:

~~~xml
<ord:SubmitOrderRequest xmlns:ord="urn:example:orders:v1">
  <ord:orderId>ORD-1001</ord:orderId>
  <ord:quantity>many</ord:quantity>
</ord:SubmitOrderRequest>
~~~

Nếu quantity là 2 và XSD chấp nhận nhưng kho không còn đủ hàng, đó là business validation failure.

~~~mermaid
flowchart TD
    A["HTTP SOAP request"] --> B["XML parser"]
    B -->|Malformed| R1["Parse rejection"]
    B -->|Well formed| C["SOAP MessageFactory"]
    C -->|Invalid Envelope| R2["SOAP protocol rejection"]
    C -->|Valid SOAP| D["XSD payload validation"]
    D -->|Invalid payload| R3["Validation rejection"]
    D -->|XSD valid| E["Security / endpoint policy"]
    E -->|Denied| R4["Security rejection"]
    E -->|Allowed| F["Business validation"]
    F -->|Invalid state| R5["Business Fault"]
    F -->|Valid| G["Business operation"]
~~~

Đây là mô hình khái niệm. Thứ tự chính xác của WS-Security, payload validation và endpoint mapping phụ thuộc cấu hình/version. Điều phải chứng minh bằng test là payload không thỏa XSD không gây business side effect.

## 3. XSD contract dùng làm cơ sở kiểm thử

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<xs:schema
    xmlns:xs="http://www.w3.org/2001/XMLSchema"
    xmlns:tns="urn:example:orders:v1"
    targetNamespace="urn:example:orders:v1"
    elementFormDefault="qualified">

  <xs:simpleType name="OrderId">
    <xs:restriction base="xs:string">
      <xs:minLength value="1"/>
      <xs:maxLength value="30"/>
      <xs:pattern value="[A-Z0-9-]+"/>
    </xs:restriction>
  </xs:simpleType>

  <xs:complexType name="SubmitOrderRequestType">
    <xs:sequence>
      <xs:element name="orderId" type="tns:OrderId"/>
      <xs:element name="quantity" type="xs:positiveInteger"/>
      <xs:element name="note" type="xs:string"
                  minOccurs="0" nillable="true"/>
      <xs:element name="tags" type="xs:string"
                  minOccurs="0" maxOccurs="3"/>
    </xs:sequence>
  </xs:complexType>

  <xs:element name="SubmitOrderRequest"
              type="tns:SubmitOrderRequestType"/>
</xs:schema>
~~~

Schema minh họa quy định orderId bắt buộc, dài 1–30 ký tự và chỉ nhận chữ hoa/số/dấu gạch nối; quantity bắt buộc là số nguyên dương; note optional và nillable; tags có thể vắng hoặc xuất hiện tối đa ba lần; local elements thuộc target namespace.

### 3.1. Payload hợp lệ

~~~xml
<ord:SubmitOrderRequest xmlns:ord="urn:example:orders:v1">
  <ord:orderId>ORD-1001</ord:orderId>
  <ord:quantity>2</ord:quantity>
  <ord:note>Deliver after 5 PM</ord:note>
  <ord:tags>priority</ord:tags>
  <ord:tags>gift</ord:tags>
</ord:SubmitOrderRequest>
~~~

Đây là positive fixture có đầy đủ thứ tự và values hợp lệ.

### 3.2. Payload hợp lệ với optional fields vắng mặt

~~~xml
<ord:SubmitOrderRequest xmlns:ord="urn:example:orders:v1">
  <ord:orderId>ORD-1002</ord:orderId>
  <ord:quantity>1</ord:quantity>
</ord:SubmitOrderRequest>
~~~

Schema cho phép bỏ note và tags. Test này phát hiện mapping vô tình coi optional field là required.

### 3.3. Payload hợp lệ với nil

~~~xml
<ord:SubmitOrderRequest
    xmlns:ord="urn:example:orders:v1"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <ord:orderId>ORD-1003</ord:orderId>
  <ord:quantity>1</ord:quantity>
  <ord:note xsi:nil="true"/>
</ord:SubmitOrderRequest>
~~~

note hiện diện nhưng nil, khác với absence và empty element. JAXB mapping phải được test trên runtime thực.

## 4. Negative fixtures theo từng vi phạm

Một test tốt thay đổi một điều kiện tại một thời điểm. Nếu một XML vừa sai namespace, thiếu field và sai datatype thì không biết validator phát hiện vi phạm nào trước.

### 4.1. Thiếu required element

~~~xml
<ord:SubmitOrderRequest xmlns:ord="urn:example:orders:v1">
  <ord:quantity>2</ord:quantity>
</ord:SubmitOrderRequest>
~~~

orderId bắt buộc bị thiếu; payload phải bị từ chối.

### 4.2. Sai thứ tự sequence

~~~xml
<ord:SubmitOrderRequest xmlns:ord="urn:example:orders:v1">
  <ord:quantity>2</ord:quantity>
  <ord:orderId>ORD-1001</ord:orderId>
</ord:SubmitOrderRequest>
~~~

XML well-formed nhưng không theo xs:sequence, vì vậy fail XSD validation.

### 4.3. Sai datatype/value space

~~~xml
<ord:SubmitOrderRequest xmlns:ord="urn:example:orders:v1">
  <ord:orderId>ORD-1001</ord:orderId>
  <ord:quantity>two</ord:quantity>
</ord:SubmitOrderRequest>
~~~

two không phải lexical value hợp lệ của xs:positiveInteger. Cần test riêng 0, số âm, decimal fraction và giá trị ngoài range.

### 4.4. Vi phạm facets

~~~xml
<ord:SubmitOrderRequest xmlns:ord="urn:example:orders:v1">
  <ord:orderId>bad_code!</ord:orderId>
  <ord:quantity>1</ord:quantity>
</ord:SubmitOrderRequest>
~~~

orderId vi phạm pattern. Thêm fixtures cho empty value, lowercase, vượt maxLength và ký tự không được phép.

### 4.5. Vượt maxOccurs

~~~xml
<ord:SubmitOrderRequest xmlns:ord="urn:example:orders:v1">
  <ord:orderId>ORD-1001</ord:orderId>
  <ord:quantity>1</ord:quantity>
  <ord:tags>a</ord:tags>
  <ord:tags>b</ord:tags>
  <ord:tags>c</ord:tags>
  <ord:tags>d</ord:tags>
</ord:SubmitOrderRequest>
~~~

Schema cho tối đa ba tags, nên bốn occurrences phải bị reject.

### 4.6. Nil khi không được phép

Với element khai báo nillable=false hoặc không cho nil, fixture có xsi:nil=true phải bị reject. Không dùng nil test trên note của schema ví dụ vì note được khai báo nillable=true.

### 4.7. Sai namespace

~~~xml
<SubmitOrderRequest xmlns="urn:example:orders:v2">
  <orderId>ORD-1001</orderId>
  <quantity>1</quantity>
</SubmitOrderRequest>
~~~

Schema v1 yêu cầu urn:example:orders:v1. Cùng local name không làm QName tương đương.

### 4.8. Element không được khai báo

~~~xml
<ord:SubmitOrderRequest xmlns:ord="urn:example:orders:v1">
  <ord:orderId>ORD-1001</ord:orderId>
  <ord:quantity>1</ord:quantity>
  <ord:unexpected>extra</ord:unexpected>
</ord:SubmitOrderRequest>
~~~

Nếu schema không có wildcard mở rộng, element dư phải bị reject. Đừng giả định mọi JAXB unmarshaller tự từ chối element unknown khi không bật validation.

## 5. Ma trận positive/negative payload

| Nhóm | Fixture | Kỳ vọng |
|---|---|---|
| Cấu trúc tối thiểu | Required fields đúng | Accept |
| Optional absent | Bỏ note/tags | Accept |
| Nillable | note có xsi:nil=true | Accept |
| Required missing | Bỏ orderId | Reject |
| Sequence | Đảo orderId/quantity | Reject |
| Datatype | quantity là chữ | Reject |
| Value range | quantity bằng 0 | Reject |
| Pattern | orderId có ký tự cấm | Reject |
| Length | orderId dài quá 30 | Reject |
| Cardinality | Bốn tags | Reject |
| Namespace | QName thuộc v2 | Reject với XSD v1 |
| Unknown child | Thêm element chưa khai báo | Reject |
| Nil prohibited | Nil trên element không nillable | Reject |
| Malformed XML | Tag không đóng | Parse rejection |
| Wrong SOAP version | Envelope không hỗ trợ | Protocol rejection |
| Valid XSD, invalid business | Order không tồn tại/đã đóng | Business rejection |

Đặt tên fixture theo mục tiêu: submit-order-valid-minimal.xml, submit-order-missing-order-id.xml, submit-order-wrong-namespace.xml. Không dùng payload sai schema nhưng mong đợi business Fault; đó là tầng kiểm tra khác.

## 6. Dùng JAXP Schema/Validator kiểm tra XSD độc lập

Trước khi kiểm tra Spring-WS wiring, test schema bằng JAXP. Việc này phân biệt fixture sai với interceptor không được cấu hình.

### 6.1. Validator helper

~~~java
import javax.xml.XMLConstants;
import javax.xml.transform.stream.StreamSource;
import javax.xml.validation.Schema;
import javax.xml.validation.SchemaFactory;
import javax.xml.validation.Validator;
import java.io.InputStream;
import java.io.StringReader;

public final class OrderSchemaValidator {
    private final Schema schema;

    public OrderSchemaValidator(InputStream xsd) throws Exception {
        SchemaFactory factory = SchemaFactory.newInstance(
                XMLConstants.W3C_XML_SCHEMA_NS_URI);
        factory.setProperty(XMLConstants.ACCESS_EXTERNAL_DTD, "");
        factory.setProperty(XMLConstants.ACCESS_EXTERNAL_SCHEMA, "");
        this.schema = factory.newSchema(new StreamSource(xsd));
    }

    public void validate(String xml) throws Exception {
        Validator validator = schema.newValidator();
        validator.setProperty(XMLConstants.ACCESS_EXTERNAL_DTD, "");
        validator.setProperty(XMLConstants.ACCESS_EXTERNAL_SCHEMA, "");
        validator.validate(new StreamSource(new StringReader(xml)));
    }
}
~~~

Đây là helper minh họa. Production phải quản lý resource lifecycle và schema imports/includes qua resolver đã duyệt. Nếu provider không hỗ trợ security properties bắt buộc, không bỏ qua lỗi cấu hình; chọn provider/configuration phù hợp và kiểm thử behavior theo XML security policy.

### 6.2. JUnit positive/negative tests

~~~java
import static org.junit.jupiter.api.Assertions.*;
import java.io.InputStream;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;

class OrderSchemaValidatorTest {
    private static OrderSchemaValidator validator;

    @BeforeAll
    static void setUp() throws Exception {
        InputStream xsd = OrderSchemaValidatorTest.class
                .getResourceAsStream("/xsd/orders-v1.xsd");
        assertNotNull(xsd);
        validator = new OrderSchemaValidator(xsd);
    }

    @Test
    void acceptsValidMinimalRequest() throws Exception {
        String xml = """
            <ord:SubmitOrderRequest
                xmlns:ord="urn:example:orders:v1">
              <ord:orderId>ORD-1001</ord:orderId>
              <ord:quantity>2</ord:quantity>
            </ord:SubmitOrderRequest>
            """;
        assertDoesNotThrow(() -> validator.validate(xml));
    }

    @Test
    void rejectsMissingRequiredOrderId() {
        String xml = """
            <ord:SubmitOrderRequest
                xmlns:ord="urn:example:orders:v1">
              <ord:quantity>2</ord:quantity>
            </ord:SubmitOrderRequest>
            """;
        assertThrows(Exception.class,
                () -> validator.validate(xml));
    }

    @Test
    void rejectsWrongQuantityType() {
        String xml = """
            <ord:SubmitOrderRequest
                xmlns:ord="urn:example:orders:v1">
              <ord:orderId>ORD-1001</ord:orderId>
              <ord:quantity>many</ord:quantity>
            </ord:SubmitOrderRequest>
            """;
        assertThrows(Exception.class,
                () -> validator.validate(xml));
    }
}
~~~

Trong suite production, bắt validation exception cụ thể như SAXException thay vì Exception tổng quát để test không vô tình pass do lỗi đọc file, schema setup hoặc lỗi hạ tầng. Có thể tạo helper assertInvalidFixture và ghi diagnostics đã redaction.

### 6.3. Không chia sẻ Validator giữa threads

Schema có thể tái sử dụng; Validator là object stateful cho mỗi lần validation và không nên dùng chung đồng thời. Tạo Validator mới theo lần gọi hoặc dùng pool an toàn đã kiểm chứng. Không giữ Validator singleton rồi gọi từ nhiều servlet threads.

## 7. Cấu hình PayloadValidatingInterceptor trong Spring-WS

Spring-WS cung cấp PayloadValidatingInterceptor để validate request/response bằng XSD. Interceptor phải được gắn vào đúng EndpointInterceptor chain.

### 7.1. Bean schema và validator

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.ClassPathResource;
import org.springframework.ws.soap.server.endpoint.interceptor.PayloadValidatingInterceptor;
import org.springframework.xml.xsd.SimpleXsdSchema;
import org.springframework.xml.xsd.XsdSchema;

@Configuration
public class SoapValidationBeans {

    @Bean
    XsdSchema ordersSchema() throws Exception {
        return new SimpleXsdSchema(
                new ClassPathResource("xsd/orders-v1.xsd"));
    }

    @Bean
    PayloadValidatingInterceptor payloadValidator(
            XsdSchema ordersSchema) {
        PayloadValidatingInterceptor interceptor =
                new PayloadValidatingInterceptor();
        interceptor.setSchema(ordersSchema);
        interceptor.setValidateRequest(true);
        interceptor.setValidateResponse(true);
        return interceptor;
    }
}
~~~

Đăng ký chính bean này vào Spring-WS interceptor chain:

~~~java
import java.util.List;
import org.springframework.context.annotation.Configuration;
import org.springframework.ws.config.annotation.EnableWs;
import org.springframework.ws.config.annotation.WsConfigurer;
import org.springframework.ws.server.EndpointInterceptor;
import org.springframework.ws.soap.server.endpoint.interceptor.PayloadValidatingInterceptor;

@Configuration
@EnableWs
public class SoapEndpointConfiguration implements WsConfigurer {
    private final PayloadValidatingInterceptor validator;

    public SoapEndpointConfiguration(
            PayloadValidatingInterceptor validator) {
        this.validator = validator;
    }

    @Override
    public void addInterceptors(
            List<EndpointInterceptor> interceptors) {
        interceptors.add(validator);
    }
}
~~~

Hai class minh họa có thể là hai file trong cùng application. Tránh tạo một instance validator khác trong addInterceptors; bean được cấu hình schema phải là bean thực sự được đăng ký. Xác minh đúng MessageDispatcherServlet/application context, tránh nhiều WsConfigurer không rõ thứ tự hoặc mapping thiếu interceptor.

### 7.2. Request và response validation là hai hướng riêng

- setValidateRequest(true): kiểm tra payload request theo schema trước khi endpoint thực hiện nghiệp vụ, theo interceptor lifecycle của version.
- setValidateResponse(true): kiểm tra payload response do endpoint tạo trước khi gửi về client.

Nếu chỉ bật request validation, server có thể nhận request đúng nhưng trả response sai WSDL. Nếu chỉ bật response validation, payload sai từ client có thể đi vào nghiệp vụ. Test cả hai hướng khi contract yêu cầu.

### 7.3. Nhiều schema/version

Một service có thể nhận nhiều namespaces/contracts. Không giả định một schema duy nhất áp dụng đúng mọi endpoint. Dùng schema set/imports hoặc validator phù hợp endpoint/version; không validate v1 bằng v2. Kiểm tra imports/includes và resolver đúng version.

### 7.4. Validator không thay parser hardening

PayloadValidatingInterceptor chỉ xử lý payload sau khi SOAP message đã được tạo. Nó không thay thế bảo vệ SOAP MessageFactory/parser chống DTD/XXE hay giới hạn request size. Kiểm soát parser/transport là lớp riêng.

## 8. Kiểm thử qua Spring-WS thay vì chỉ gọi Validator

JAXP unit test chứng minh schema và fixtures, chưa chứng minh interceptor được gắn đúng vào Spring-WS server. Cần endpoint integration test.

### 8.1. MockWebServiceClient

~~~java
@SpringBootTest
class SubmitOrderEndpointValidationTest {
    @Autowired
    ApplicationContext applicationContext;

    @Autowired
    OrderServiceSpy orderService;

    @Test
    void acceptsXsdValidRequest() {
        MockWebServiceClient client =
                MockWebServiceClient.createClient(applicationContext);

        Source request = new StringSource("""
            <ord:SubmitOrderRequest
                xmlns:ord="urn:example:orders:v1">
              <ord:orderId>ORD-1001</ord:orderId>
              <ord:quantity>2</ord:quantity>
            </ord:SubmitOrderRequest>
            """);

        client.sendRequest(withPayload(request))
              .andExpect(noFault());

        assertEquals(1, orderService.submitCalls());
    }

    @Test
    void rejectsXsdInvalidRequestBeforeBusiness() {
        MockWebServiceClient client =
                MockWebServiceClient.createClient(applicationContext);

        Source request = new StringSource("""
            <ord:SubmitOrderRequest
                xmlns:ord="urn:example:orders:v1">
              <ord:quantity>many</ord:quantity>
            </ord:SubmitOrderRequest>
            """);

        client.sendRequest(withPayload(request))
              .andExpect(soapFault());

        assertEquals(0, orderService.submitCalls());
    }
}
~~~

Imports cần Spring Test/JUnit và static imports phù hợp của MockWebServiceClient, RequestCreators.withPayload, ResponseMatchers.noFault cùng matcher SOAP Fault của version sử dụng. Tên/cách cung cấp fault matcher có thể khác theo Spring-WS release. Nếu version không có soapFault helper, viết ResponseMatcher kiểm tra SoapMessage.getSoapBody().hasFault(), hoặc assert exception/result theo behavior thực.

OrderServiceSpy là test helper của dự án, không phải Spring-WS class. Có thể thay bằng spy/mock phù hợp application context. Điều cần chứng minh: valid request gọi nghiệp vụ đúng một lần; invalid request không gọi nghiệp vụ.

### 8.2. Tránh test pass giả

Negative fixture chỉ thay một vi phạm schema. Đừng dùng orderId không tồn tại để test XSD sai vì payload có thể hợp schema và bị business service từ chối. Business-invalid test phải dùng payload XSD-valid.

### 8.3. Response validation

Để test setValidateResponse(true), tạo test endpoint trả response vi phạm schema, ví dụ thiếu required response element hoặc sai type. Assert response không được gửi như success hợp lệ. Kiểm behavior/Fault mapping trên Spring-WS version thực; đừng chỉ validate DTO trước marshal vì lỗi có thể xuất hiện ở XML output.

## 9. HTTP end-to-end test trên servlet thật

MockWebServiceClient hữu ích nhưng không chứng minh toàn HTTP stack: Servlet mapping, SOAP MessageFactory, content type, transport, parser, filter chain và TLS. Với service quan trọng, cần test server HTTP(S) thật hoặc Spring Boot test dùng random port.

Kiểm tra:
1. SOAP hợp lệ qua URL công bố đến đúng endpoint.
2. Payload vi phạm XSD bị từ chối trước side effects.
3. Content-Type và SOAP version đúng.
4. SOAPAction/QName/namespace được mapping đúng.
5. Response/Fault đúng wire contract.
6. Security interceptors vẫn chạy.
7. Parser không tải external resources và body/MTOM quotas được áp dụng.
8. Error response không echo raw XML/PII.

| Đầu vào | Tầng dự kiến từ chối | Assertion |
|---|---|---|
| XML malformed | XML parser | Không business call |
| SOAP Envelope sai version | MessageFactory/protocol | Không business call |
| Body sai QName | Endpoint mapping/validation | Không gọi operation khác |
| Thiếu required field | XSD validation | Không side effect |
| Đúng XSD, sai business | Business validator | Business Fault |
| Đúng schema/authorization | Endpoint/business | Success |
| Payload oversized | Proxy/container limits | Reject trước endpoint |
| WS-Security sai | Security layer | Không endpoint business |

## 10. Assertions chứng minh từ chối đúng cách

Không chỉ kiểm tra HTTP 500 hay SOAP Fault. Phải khẳng định lý do ở đúng tầng và endpoint không thực hiện side effects.

### 10.1. Business invocation counter

- Payload hợp lệ: service method gọi đúng một lần.
- Payload sai XSD: service method không được gọi.
- Payload hợp XSD nhưng sai nghiệp vụ: business validator từ chối, không ghi thành công.
- Lỗi parser/protocol: không có business invocation.

### 10.2. Response theo contract

Tùy SOAP version, Spring-WS exception resolver và transport, validation rejection có thể thành SOAP Fault, HTTP error hoặc lỗi transport. Test theo behavior được công bố, tránh hardcode status nếu profile cho phép khác biệt. Tuy nhiên phải assert không trả success giả, không leak stack trace/raw payload, Fault detail đúng contract nếu có, correlation ID dùng được và không side effects.

### 10.3. Tách technical và business outcome

| Test category | Assertion kỹ thuật | Assertion nghiệp vụ |
|---|---|---|
| XSD-valid | Validator pass | Operation được phép gọi |
| XSD-invalid | Validator reject | Không side effect |
| Business-invalid | Validator pass | Business rule deny |
| Security-invalid | Schema có thể pass | Security deny trước protected method |
| Protocol-invalid | Parser/message factory reject | Không dispatch |

## 11. Negative test catalog

### 11.1. Simple types

Kiểm integer chữ cái, decimal fraction khi cần integer, min/max inclusive/exclusive, decimal totalDigits/fractionDigits, date/time lexical form, boolean value, string empty/length/pattern, enum ngoài tập khai báo và union/list types.

### 11.2. Complex types

Kiểm element required thiếu, unknown element, sai sequence, choice có nhiều nhánh, attribute required thiếu, attribute lạ, type derivation sai, substitution group hoặc xsi:type không được policy chấp nhận.

### 11.3. Occurrence và nil

Test số occurrences bằng zero, min, max và max+1; optional absent; required absent; nil hợp lệ và nil bị cấm; empty element; default/fixed semantics trên XML và Java mapping.

### 11.4. Namespace và schema graph

Test namespace sai dù local name đúng, child element thiếu namespace, attribute qualification sai, import/include thiếu hoặc base URI sai, version schema route nhầm. Prefix khác nhưng cùng namespace URI cần được accept.

## 12. Boundary testing và property-based tests

Với maxLength=30: length 0 invalid nếu minLength=1; length 1 và 30 valid; length 31 invalid.

Với maxOccurs=3: zero occurrences valid nếu minOccurs=0; một và ba valid; bốn invalid.

~~~java
@ParameterizedTest
@ValueSource(strings = {
    "A", "ORD-1", "ABC123"
})
void acceptsOrderIdMatchingPattern(String orderId) {
    assertValid(buildSubmitOrderXml(orderId, "1"));
}

@ParameterizedTest
@ValueSource(strings = {
    "", "lowercase", "bad code", "bad_code!"
})
void rejectsOrderIdOutsidePattern(String orderId) {
    assertInvalid(buildSubmitOrderXml(orderId, "1"));
}
~~~

Các helper phải nối tới đúng schema. Tránh nối raw value trực tiếp vào XML builder; dùng XML builder hoặc escape values để test không vô tình tạo malformed XML thay vì XSD violation.

Property-based testing cần seed tái lập, payload size/depth giới hạn, schema/provider versions, phân biệt parser failure với validation failure và shrinking để tạo minimal counterexample. Resource exhaustion tests cần sandbox riêng, không chạy payload lớn trên shared CI.

## 13. Schema imports và XML security khi validate

XSD validation có thể nạp imported schemas hoặc external resources. Với schema set nội bộ:
- Đóng gói dependencies tin cậy cùng artifact.
- Dùng catalog/resolver whitelist khi cần.
- Hạn chế ACCESS_EXTERNAL_DTD và ACCESS_EXTERNAL_SCHEMA.
- Không tin xsi:schemaLocation từ caller để thay schema server.
- Fail startup nếu schema required không compile/resolve.
- Test offline để bảo đảm assets đủ.
- Test DOCTYPE/external entities qua HTTP endpoint thật.

PayloadValidatingInterceptor không thay parser hardening của SOAP MessageFactory. Nếu SOAP Envelope được parse trước validator, XML security phải được cấu hình tại parser/message factory tương ứng.

## 14. Response validation và contract của server

Server phải trả response đúng XSD, không chỉ reject bad request.

~~~xml
<xs:element name="SubmitOrderResponse">
  <xs:complexType>
    <xs:sequence>
      <xs:element name="orderId" type="xs:string"/>
      <xs:element name="accepted" type="xs:boolean"/>
    </xs:sequence>
  </xs:complexType>
</xs:element>
~~~

Server trả thiếu accepted hoặc trả boolean lexical value sai sau transformation phải được phát hiện trước khi message gửi nếu response validation được bật.

Test response đúng, missing field, wrong namespace/order, enum/cardinality boundaries và modeled business Fault nếu WSDL định nghĩa. Validate XML đã marshal qua Spring-WS pipeline, không chỉ Java DTO.

## 15. XSD validation không thay kiểm soát khác

| Kiểm tra | XSD xử lý? | Ví dụ |
|---|---|---|
| Required element | Có | orderId phải có |
| XML order | Có nếu sequence | orderId trước quantity |
| Datatype/facets | Có | positiveInteger, pattern |
| Cardinality | Có | tối đa ba tags |
| Nillability | Có | note có thể nil |
| Authentication | Không | mTLS/UsernameToken |
| Signature integrity | Không | WSS4J |
| Tenant authorization | Không | order thuộc partner |
| Inventory | Không | đủ hàng |
| Idempotency | Không | không tạo đơn trùng |
| Database state | Không | orderId đã tồn tại |

Payload hợp XSD không có nghĩa được quyền thực hiện operation. Business validation không thay XSD validation vì không kiểm soát đầy đủ cấu trúc, namespace và cardinality.

## 16. Case study: endpoint chấp nhận payload thiếu required field

### 16.1. Triệu chứng

Endpoint SubmitOrder công bố XSD yêu cầu orderId và quantity. Client gửi chỉ quantity, nhưng server vẫn nhận Java DTO và service ghi order với ID rỗng/null. Nhóm phát triển nghĩ JAXB generate từ XSD thì đương nhiên validate schema.

### 16.2. Nguyên nhân có thể

1. PayloadValidatingInterceptor chưa đăng ký vào interceptor chain.
2. Bean được cấu hình schema nhưng chain dùng instance khác.
3. validateRequest chưa bật.
4. Endpoint mapping/servlet khác không có interceptor.
5. Jaxb2Marshaller unmarshal không được gắn schema validation.
6. Schema resource không phải version WSDL công bố.
7. Imports/includes không resolve.
8. Test chỉ gọi endpoint method trực tiếp, bỏ qua server chain.
9. Business code gán default orderId rỗng, che lỗi mapping.

### 16.3. Khắc phục dựa trên bằng chứng

~~~mermaid
flowchart TD
    A["Payload thiếu orderId"] --> B["Capture SOAP Body"]
    B --> C["Kiểm schema version/checksum"]
    C --> D["Kiểm XSD resource/imports"]
    D --> E{"Validator thực chạy?"}
    E -->|Không| F["Gắn đúng bean vào chain"]
    E -->|Có| G["Kiểm request validation và mapping"]
    F --> H["Gửi lại cùng payload"]
    G --> H
    H --> I{"Business method được gọi?"}
    I -->|Có| J["Tìm bypass, fail test"]
    I -->|Không| K["Assert rejection và no side effect"]
~~~

Không sửa business method để lặng lẽ bỏ request thiếu ID; sửa validation boundary và thêm regression test.

### 16.4. Bằng chứng đóng lỗi

- Payload hợp lệ vẫn được xử lý.
- Payload thiếu orderId bị từ chối qua HTTP endpoint thật.
- Business call counter bằng zero.
- Schema version và interceptor wiring được xác nhận.
- Fault không có raw input/stack trace.
- Regression test chạy trong CI cùng schema version/checksum.

## 17. Bài tập tự luyện kèm đáp án

**Bài 1 — XML well-formed:** Quantity chứa many nhưng tag đóng đúng. Parser chứng minh payload valid?

**Đáp án:** Không. XML well-formed; XSD positiveInteger validation từ chối.

**Bài 2 — JAXB tạo object:** Request thiếu orderId vẫn unmarshal. Kết luận XSD sai?

**Đáp án:** Chưa. Unmarshal không mặc định bật schema validation; kiểm interceptor và schema version.

**Bài 3 — Đảo sequence:** DOM parse thành công nhưng quantity đứng trước orderId. Có hợp XSD?

**Đáp án:** Không nếu xs:sequence quy định orderId trước quantity.

**Bài 4 — Optional field:** note minOccurs=0 và bị bỏ. Kỳ vọng?

**Đáp án:** Accept nếu constraints khác đúng; mapper xử lý absence theo contract.

**Bài 5 — Nil và absent:** note optional/nillable. xsi:nil khác vắng mặt?

**Đáp án:** Có. Nil là element hiện diện mang nil value; absent là element không xuất hiện.

**Bài 6 — maxOccurs:** Schema maxOccurs=3, request gửi bốn tags?

**Đáp án:** Reject tại XSD validation, không gọi business.

**Bài 7 — Namespace:** Local name đúng nhưng namespace v2 khi endpoint v1?

**Đáp án:** QName khác; mapping/validation từ chối.

**Bài 8 — Valid XSD, invalid business:** Kho hết hàng nhưng quantity hợp schema?

**Đáp án:** Business validation từ chối, không phải XSD error.

**Bài 9 — JAXP test:** Validator unit test pass chứng minh interceptor Spring-WS chạy?

**Đáp án:** Không. Cần endpoint integration test.

**Bài 10 — HTTP 500:** Invalid payload trả 500 là đủ?

**Đáp án:** Không. Assert rejection, fault contract và no side effects; HTTP status tùy SOAP binding/transport.

**Bài 11 — Response validation:** Request đúng nhưng response thiếu required field?

**Đáp án:** Bật response validation và test XML đã marshal qua Spring-WS.

**Bài 12 — External schema:** Import fail offline, bật external access all?

**Đáp án:** Không. Đóng gói schema hoặc dùng resolver/catalog whitelist.

## 18. Checklist kiểm thử payload XSD tại SOAP server

### Schema và fixtures
- [ ] Pin đúng XSD/WSDL version của endpoint.
- [ ] Xác minh global element, targetNamespace và elementFormDefault.
- [ ] Có positive fixture tối thiểu và đầy đủ.
- [ ] Có optional-absent, nil và empty fixtures khi được phép.
- [ ] Có negative fixtures riêng cho missing required, order, datatype, range, pattern và length.
- [ ] Test min/maxOccurs boundary và extra element.
- [ ] Test namespace mismatch và prefix-equivalent QName.
- [ ] Test enum, attributes, choice, nested types và imports/includes.

### Server configuration
- [ ] PayloadValidatingInterceptor dùng đúng schema.
- [ ] Request validation bật.
- [ ] Response validation bật khi contract yêu cầu.
- [ ] Đúng interceptor bean được đăng ký vào endpoint chain.
- [ ] Mọi servlet/mapping/version được kiểm tra, không có bypass.
- [ ] Validator/provider không bị dùng chung sai giữa concurrent requests.
- [ ] Schema imports/includes resolve từ packaged artifact và resolver an toàn.
- [ ] SOAP MessageFactory/parser hardening được test riêng.

### Assertions
- [ ] Valid request tới endpoint và business method đúng số lần.
- [ ] Invalid XSD request bị từ chối trước business side effects.
- [ ] Business-invalid nhưng XSD-valid được phân loại riêng.
- [ ] Malformed XML và invalid SOAP Envelope được phân loại riêng.
- [ ] Response XML được validate theo contract.
- [ ] SOAP Fault/detail không leak raw XML, stack trace hoặc secrets.
- [ ] Test assert rejection và không có DB/event/payment side effects.

### CI và vận hành
- [ ] Có JAXP schema tests và Spring-WS integration tests.
- [ ] Có HTTP end-to-end tests cho servlet/message factory/transport.
- [ ] Lưu fixtures và kết quả theo schema version/checksum.
- [ ] Chạy lại tests khi nâng JDK, Spring-WS, JAXB hoặc XML provider.
- [ ] Không dùng production secrets/certificates trong fixtures.
- [ ] Có body size/depth/attachment limits và XXE tests riêng.
- [ ] Không chạy resource exhaustion payload lớn trên shared CI/prod.
- [ ] Theo dõi rejection bằng reason code, không log toàn payload.

**Ghi nhớ:** Kiểm thử payload theo XSD phải chứng minh cả hai phía: dữ liệu đúng được chấp nhận và dữ liệu sai bị từ chối đúng tầng. Với Spring Web Services, validate request/response bằng schema đúng version, kiểm namespace, sequence, datatypes, facets, occurrence và nil semantics, rồi gửi payload qua chính interceptor chain/HTTP endpoint thực. Quan trọng nhất, assert request không hợp XSD không thể gọi business method hoặc tạo side effect; đồng thời giữ tests riêng cho parser/SOAP protocol, WS-Security và business rules.
