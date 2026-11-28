# Kiểm tra marshalling, unmarshalling và ánh xạ lỗi về nghiệp vụ

Một SOAP client phải chuyển đúng dữ liệu Java thành XML theo XSD/WSDL, đọc response XML thành kiểu Java chính xác, sau đó phân loại Fault hoặc lỗi transport thành kết quả nghiệp vụ mà application hiểu được. Request có thể marshal thành công nhưng sai QName; response có thể well-formed nhưng không map được JAXB; partner có thể trả SOAP Fault; hoặc kết nối timeout sau khi giao dịch đã commit.

Bài này thuộc chương **Kiểm thử máy khách** của module **SPRING_WEB_SERVICES**, tập trung kiểm tra marshalling, unmarshalling và ánh xạ lỗi theo contract-first. Ví dụ dùng generated JAXB types từ XSD và Spring-WS 4.x / Spring Framework 6 / Java 17+ làm baseline. Các kiểu `SubmitPaymentRequest` và `SubmitPaymentResponse` là đại diện cho generated types của project.

## 1. Mục tiêu học tập

1. Phân biệt marshalling và unmarshalling.
2. Cấu hình `Jaxb2Marshaller` làm cả `Marshaller` và `Unmarshaller`.
3. Kiểm XML request có đúng QName, namespace, thứ tự và datatype.
4. Kiểm response thành đúng JAXB object và domain result.
5. Dùng `MockWebServiceServer` kiểm `WebServiceTemplate` mà không gọi HTTP thật.
6. Dùng `RequestMatchers` và `ResponseCreators` phù hợp.
7. Kiểm XSD validation, response sai schema và XML malformed.
8. Phân biệt SOAP Fault, HTTP/transport error và binding error.
9. Map Fault code/detail thành typed business exception.
10. Kiểm retry, idempotency và bảo vệ dữ liệu nhạy cảm.

## 2. Luồng dữ liệu

~~~mermaid
flowchart TD
    A["Domain command"] --> B["Request mapper"]
    B --> C["JAXB request"]
    C --> D["Marshaller"]
    D --> E["SOAP Body XML"]
    E --> F["WebServiceTemplate"]
    F --> G["Remote SOAP endpoint"]
    G --> H["Response or Fault"]
    H --> I["Unmarshaller / Fault resolver"]
    I --> J{"Result"}
    J -->|Response| K["JAXB response"]
    K --> L["Domain mapper"]
    L --> M["Business result"]
    J -->|Fault| N["SoapFaultClientException"]
    J -->|Transport| O["WebServiceException"]
    J -->|Invalid XML| P["Binding error"]
~~~

| Ranh giới | Câu hỏi test |
|---|---|
| Domain → JAXB | Amount/date/enum/optional field map đúng? |
| JAXB → XML | QName/namespace/element/type khớp contract? |
| XML → JAXB | Response deserialize đầy đủ? |
| SOAP/HTTP → domain error | Fault/transport/malformed response phân loại đúng? |

Mock toàn bộ `WebServiceTemplate` chỉ chứng minh client gọi method với object nào đó; không xác minh XML. `MockWebServiceServer` kiểm message do template gửi, còn HTTP integration test kiểm transport thật.

## 3. Marshalling và unmarshalling

**Marshalling** chuyển object thành XML:

~~~text
SubmitPaymentRequest
  -> JAXB Marshaller
  -> <pay:SubmitPaymentRequest>...</pay:SubmitPaymentRequest>
  -> SOAP Body
~~~

**Unmarshalling** chuyển XML response thành object:

~~~text
SOAP Body
  -> JAXB Unmarshaller
  -> SubmitPaymentResponse
  -> Domain mapper
  -> PaymentReceipt
~~~

Hai chiều có thể lỗi độc lập. Round-trip JAXB trong cùng JVM không chứng minh hai SOAP stacks độc lập cùng hiểu contract.

## 4. Cấu hình Jaxb2Marshaller

Một `Jaxb2Marshaller` có thể làm cả marshalling và unmarshalling:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.oxm.jaxb.Jaxb2Marshaller;

@Configuration
public class SoapClientConfiguration {
    @Bean
    public Jaxb2Marshaller paymentMarshaller() {
        Jaxb2Marshaller marshaller = new Jaxb2Marshaller();
        marshaller.setContextPath("com.example.payments.ws");
        return marshaller;
    }
}
~~~

`contextPath` trỏ tới package JAXB generated chứa `ObjectFactory` và classes từ XSD. Một lựa chọn khác là `setClassesToBeBound(...)` với danh sách types. Chọn một cách nhất quán và bảo đảm mọi root element/type cần thiết nằm trong context.

### 4.1. Schema validation và XML hardening

~~~java
import org.springframework.core.io.ClassPathResource;
import org.springframework.oxm.jaxb.Jaxb2Marshaller;

Jaxb2Marshaller marshaller = new Jaxb2Marshaller();
marshaller.setContextPath("com.example.payments.ws");
marshaller.setSchemas(
    new ClassPathResource("contracts/payments.xsd")
);
marshaller.setSupportDtd(false);
marshaller.setProcessExternalEntities(false);
~~~

Nếu schema dùng include/import, kiểm resource được resolve từ classpath. Không mở external schema/DTD access ngoài chính sách. Schema validation kiểm XML structure/type; nó không thay business validation hoặc authorization.

## 5. WebServiceTemplate và client façade

`WebServiceTemplate` là entry point cho SOAP request/response:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.oxm.jaxb.Jaxb2Marshaller;
import org.springframework.ws.client.core.WebServiceTemplate;

@Configuration
public class PaymentTemplateConfiguration {
    @Bean
    public WebServiceTemplate paymentTemplate(
            Jaxb2Marshaller paymentMarshaller) {
        WebServiceTemplate template =
            new WebServiceTemplate(paymentMarshaller);
        template.setDefaultUri(
            "https://partner.example.test/soap/payments"
        );
        return template;
    }
}
~~~

Constructor nhận marshaller yêu cầu object implement cả `Marshaller` và `Unmarshaller`; `Jaxb2Marshaller` đáp ứng. Endpoint URI production lấy từ externalized config.

Đặt façade hướng domain phía trên template:

~~~java
public interface PaymentPartnerClient {
    PaymentReceipt submit(PaymentCommand command);
    PaymentStatus findStatus(String paymentId);
}
~~~

Facade map command sang JAXB request, gọi template, map response và chuyển Fault/transport/binding errors thành integration/business errors có semantics rõ.

## 6. MockWebServiceServer

`MockWebServiceServer` thuộc `org.springframework.ws.test.client`. Nó gắn với `WebServiceTemplate`, xác minh request message theo expectations và dựng response message trả về template.

~~~java
import org.springframework.ws.test.client.MockWebServiceServer;

MockWebServiceServer mockServer =
    MockWebServiceServer.createServer(webServiceTemplate);
~~~

Có thể tạo mock server từ `WebServiceTemplate`, `WebServiceGatewaySupport` hoặc `ApplicationContext`. Sau khi gọi client, luôn gọi `mockServer.verify()` để xác nhận expectations đã được đáp ứng. Đây là test message exchange in-process, không mở HTTP socket thật.

### 6.1. Vòng đời test

~~~mermaid
sequenceDiagram
    participant T as JUnit
    participant C as Client
    participant W as WebServiceTemplate
    participant M as MockWebServiceServer
    T->>M: createServer(template)
    T->>M: expect + andRespond
    T->>C: submit(command)
    C->>W: marshalSendAndReceive
    W->>M: SOAP request
    M->>M: Match request
    M-->>W: Synthetic response/Fault
    W-->>C: JAXB object/exception
    C-->>T: Domain result/error
    T->>M: verify()
~~~

Mỗi test nên có mock server/expectations riêng; không chia sẻ mutable state giữa test methods chạy song song.

## 7. Kiểm marshalling bằng payload matcher

`RequestMatchers.payload(Source)` so SOAP Body với XML mong đợi:

~~~java
import static org.springframework.ws.test.client.RequestMatchers.payload;
import static org.springframework.ws.test.client.ResponseCreators.withPayload;
import org.springframework.xml.transform.StringSource;

mockServer.expect(payload(new StringSource("""
    <pay:SubmitPaymentRequest
        xmlns:pay="urn:example:payments:v1">
        <pay:requestId>REQ-100</pay:requestId>
        <pay:tenantId>TENANT-A</pay:tenantId>
        <pay:accountId>ACC-100</pay:accountId>
        <pay:amount>250.00</pay:amount>
        <pay:currency>VND</pay:currency>
    </pay:SubmitPaymentRequest>
    """)))
    .andRespond(withPayload(new StringSource("""
        <pay:SubmitPaymentResponse
            xmlns:pay="urn:example:payments:v1">
            <pay:paymentId>PAY-900</pay:paymentId>
            <pay:status>ACCEPTED</pay:status>
        </pay:SubmitPaymentResponse>
        """)));
~~~

Matcher này kiểm Body, không tự kiểm SOAP Header, SOAPAction, WS-Security hay TLS. Thêm matcher phù hợp khi các phần đó thuộc contract.

QName gồm namespace URI và local name. Prefix chỉ là alias; prefix khác nhau không nhất thiết là lỗi nếu QName không đổi. Test nên kiểm values, decimal precision, date/time, enum lexical values, optional elements, xsi:nil và collection order/cardinality.

## 8. validPayload và RequestMatchers

`RequestMatchers.validPayload(Resource...)` kiểm payload request theo XSD:

~~~java
import static org.springframework.ws.test.client.RequestMatchers.validPayload;
import org.springframework.core.io.ClassPathResource;

mockServer.expect(validPayload(
    new ClassPathResource("contracts/payments.xsd")
));
~~~

Overload schema/resource cụ thể phụ thuộc test artifact version; kiểm Javadoc khi truyền nhiều schemas/imports.

Các matcher chính:

| Matcher | Mục đích |
|---|---|
| `anything()` | Không ràng buộc request |
| `payload(Source)` | So sánh Body |
| `validPayload(Resource...)` | Validate Body với XSD |
| `xpath(...)` | Kiểm XPath |
| `soapHeader(QName)` | Kiểm Header tồn tại |
| `soapEnvelope(Source)` | So sánh full Envelope |
| `connectionTo(URI/String)` | Kiểm endpoint URI |

`soapHeader(QName)` kiểm Header theo QName; muốn kiểm value/attributes, dùng XPath hoặc custom matcher. Các matcher có thể ghép bằng `andExpect(...)`. Không dùng `anything()` cho happy path khi mục tiêu là kiểm XML.

## 9. Kiểm unmarshalling bằng response payload

`ResponseCreators.withPayload(Source)` tạo response payload để unmarshaller thật xử lý:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.springframework.ws.test.client.RequestMatchers.payload;
import static org.springframework.ws.test.client.ResponseCreators.withPayload;
import org.springframework.xml.transform.StringSource;

@Test
void unmarshalsPartnerResponse() {
    mockServer.expect(payload(expectedRequest))
        .andRespond(withPayload(new StringSource("""
            <pay:SubmitPaymentResponse
                xmlns:pay="urn:example:payments:v1">
                <pay:paymentId>PAY-900</pay:paymentId>
                <pay:status>ACCEPTED</pay:status>
            </pay:SubmitPaymentResponse>
            """)));

    PaymentReceipt receipt = client.submit(command);

    assertEquals("PAY-900", receipt.paymentId());
    assertEquals(PaymentStatus.ACCEPTED, receipt.status());
    mockServer.verify();
}
~~~

Domain types, mappers và fixtures là dependencies của test. Test hữu ích khi response đi qua `WebServiceTemplate` và `Jaxb2Marshaller` thực, sau đó assert domain fields.

### 9.1. Response edge cases

| Response XML | Điều phải kiểm |
|---|---|
| Decimal 250.00 | Precision/scale |
| Optional element absent | Null/default semantics |
| Empty element | Khác absent |
| xsi:nil=true | Nullable theo schema |
| Date 2026-11-27 | Không lệch timezone |
| Timestamp có offset | Parse đúng policy |
| Enum không biết | Reject/fallback rõ |
| Root QName khác | Không map nhầm response |

Không để default Java values biến field bắt buộc bị thiếu thành 0/false. Dùng schema validation khi ràng buộc nằm trong XSD.

## 10. Response sai schema hoặc malformed XML

Ví dụ XML well-formed nhưng decimal không hợp lệ:

~~~xml
<pay:SubmitPaymentResponse xmlns:pay="urn:example:payments:v1">
    <pay:paymentId>PAY-900</pay:paymentId>
    <pay:amount>not-a-decimal</pay:amount>
</pay:SubmitPaymentResponse>
~~~

Nếu schema validation được cấu hình, unmarshalling phải fail. Nếu không bật validation, JAXB chỉ enforce những ràng buộc từ binding; không mặc định mọi semantic rule XSD đều được kiểm. Malformed XML, unknown root QName, unsupported xsi:type hoặc schema import thiếu có thể gây binding/transform exception. Client không được trả domain success mặc định.

## 11. SOAP Fault và ResponseCreators

SOAP Fault là response message có cấu trúc riêng, không phải payload nghiệp vụ. `ResponseCreators` cung cấp creators cho MustUnderstand, Client/Sender, Server/Receiver, VersionMismatch; còn có `withError()` và `withException()` để mô phỏng lỗi response connection.

~~~java
import static org.springframework.ws.test.client.ResponseCreators.withClientOrSenderFault;

mockServer.expect(payload(expectedRequest))
    .andRespond(withClientOrSenderFault(
        "Invalid account state",
        Locale.ENGLISH
    ));
~~~

Receiver Fault:

~~~java
import static org.springframework.ws.test.client.ResponseCreators.withServerOrReceiverFault;

mockServer.expect(payload(expectedRequest))
    .andRespond(withServerOrReceiverFault(
        "Partner service unavailable",
        Locale.ENGLISH
    ));
~~~

Các overload chi tiết phụ thuộc Spring-WS test release. Dùng đúng Fault version tương ứng SOAP binding của client.

## 12. FaultMessageResolver và SoapFaultClientException

`WebServiceTemplate` xử lý SOAP Fault qua `FaultMessageResolver`. Default `SoapFaultMessageResolver` ném `SoapFaultClientException`. Client façade có thể map exception này:

~~~java
import org.springframework.ws.soap.client.SoapFaultClientException;

public PaymentReceipt submit(PaymentCommand command) {
    SubmitPaymentRequest request = requestMapper.toSoap(command);
    try {
        SubmitPaymentResponse response =
            (SubmitPaymentResponse) webServiceTemplate
                .marshalSendAndReceive(endpointUri, request);
        return responseMapper.toDomain(response);
    } catch (SoapFaultClientException ex) {
        throw faultMapper.toDomainException(ex);
    }
}
~~~

Generated types, mappers và template đã được inject. Không catch mọi RuntimeException rồi quy thành business rejection; lỗi cấu hình/lập trình cần được nhận diện riêng.

### Mapping theo code/detail

| Remote Fault | Domain outcome |
|---|---|
| Sender + INVALID_ACCOUNT | InvalidPaymentAccountException |
| Sender + LIMIT_EXCEEDED | PaymentLimitExceededException |
| Sender + DUPLICATE_REQUEST | DuplicatePaymentRequestException |
| Receiver | PartnerProcessing/UnavailableException |
| MustUnderstand | PartnerProtocolException |
| VersionMismatch | PartnerProtocolException |
| Detail không biết | UnknownPartnerFaultException |

Ưu tiên Fault code/subcode và structured Detail QName/schema. Fault reason có thể đổi theo ngôn ngữ/release; không parse arbitrary text như protocol ổn định. SOAP 1.1 có faultcode/faultstring/detail; SOAP 1.2 có Code/Reason/Detail và subcodes.

## 13. Transport errors không phải SOAP Fault

Server có thể không reachable, TLS handshake fail, proxy trả 502/503/504, timeout hoặc connection reset. Các lỗi này có thể xảy ra trước khi có SOAP Envelope.

~~~java
import static org.springframework.ws.test.client.ResponseCreators.withError;
import static org.springframework.ws.test.client.ResponseCreators.withException;

mockServer.expect(payload(expectedRequest))
    .andRespond(withError(new IOException("connection reset")));

mockServer.expect(payload(expectedRequest))
    .andRespond(withException(new IOException("read failed")));
~~~

Kiểm overload/exception type theo Spring-WS test release. Transport failure phải map thành communication/integration error, không phải InvalidPaymentAccountException.

## 14. Ma trận phân loại lỗi

| Nhóm | Ví dụ | Mapping |
|---|---|---|
| SOAP business Fault | Account invalid/limit exceeded | Typed business exception |
| SOAP protocol Fault | VersionMismatch/MustUnderstand | PartnerProtocolException |
| SOAP Receiver Fault | Remote processing failed | PartnerProcessingException |
| HTTP/transport | Timeout/503/TLS error | PartnerCommunicationException |
| XML binding | Wrong QName/type/schema | PartnerContractException |
| Marshalling local | JAXB cannot serialize | LocalClientSerializationException |
| Local validation | Amount âm | Domain validation trước network |

Sender Fault thường chỉ ra request sai; retry nguyên request không có ích. Receiver Fault cần policy theo code/partner. Transport timeout có thể để lại unknown outcome.

## 15. Idempotency và retry

Timeout sau SubmitPayment không chứng minh partner chưa nhận hoặc chưa commit. Retry mù có thể tạo payment trùng.

Dùng business `requestId` ổn định cho cùng ý định nghiệp vụ. Retry transport có thể mở connection mới, nhưng không tự tạo requestId mới. Contract partner cần định nghĩa duplicate request trả response cũ, Fault hay trạng thái query.

Test connect timeout, timeout sau khi gửi request, partner commit rồi response mất, retry cùng requestId, DuplicateRequest Fault và status reconciliation. Không retry mọi SOAP Fault hoặc non-idempotent operation mặc định.

## 16. Marshalling failure xảy ra trước khi request gửi

Marshalling có thể fail do JAXB type không nằm trong context, root element wrapper thiếu, invalid XML character, unsupported object type hoặc adapter ném exception. Nếu fail trước transport, mock expectation không được tiêu thụ.

Assert lỗi local serialization/contract được phân loại đúng, không có request ra partner, không tạo business result giả và không bị map nhầm thành remote rejection. Log operation/correlation ID, không dump payload nhạy cảm.

## 17. Unmarshalling/schema error không được biến thành success

Response có thể parse well-formed nhưng không map được vì root QName lạ, datatype sai, enum mới, required sequence vi phạm hoặc schema import thiếu. Test theo validator/binding thật của production.

Assert error category rõ, không retry vô hạn response contract-invalid và không log toàn XML nhạy cảm. Nếu partner thêm enum mới, policy phải reject hoặc hỗ trợ unknown value một cách có chủ đích.

## 18. Custom RequestMatcher và ResponseCreator

Khi matcher chuẩn không đủ, implement `RequestMatcher` để kiểm URI và WebServiceMessage:

~~~java
import java.io.IOException;
import java.net.URI;
import org.springframework.ws.WebServiceMessage;
import org.springframework.ws.test.client.RequestMatcher;

public final class HttpsEndpointMatcher implements RequestMatcher {
    @Override
    public void match(URI uri, WebServiceMessage request)
            throws IOException {
        if (!"https".equalsIgnoreCase(uri.getScheme())) {
            throw new AssertionError("Expected HTTPS endpoint");
        }
    }
}
~~~

Custom matcher nên kiểm requirement cụ thể. URI scheme trong mock test không chứng minh TLS handshake thật. Custom `ResponseCreator` tạo message qua `WebServiceMessageFactory`; dùng khi cần Fault detail/Header/attachment đặc biệt mà factory có sẵn không đủ.

## 19. Unit, mock và HTTP integration tests

| Layer | Công cụ | Mục đích |
|---|---|---|
| Mapper unit | JUnit | Domain ↔ JAXB |
| Marshalling unit | JAXB/Jaxb2Marshaller | Binding/schema local |
| Client integration | MockWebServiceServer | XML request/response/Fault |
| HTTP integration | Embedded server/HTTP stub | Status, headers, framing |
| TLS integration | HTTPS fixture | Truststore, hostname, mTLS |
| Contract interop | Partner sandbox | WSDL/XSD/SOAP compatibility |
| Resilience | Fault/timeout injection | Retry/idempotency/unknown outcome |

MockWebServiceServer kiểm message exchange nhưng không mở socket; nó không chứng minh TLS, proxy, DNS, HTTP pooling hay partner interoperability. Dùng HTTP tests cho những tiêu chí đó.

## 20. Ví dụ test tích hợp client

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.springframework.ws.test.client.RequestMatchers.payload;
import static org.springframework.ws.test.client.ResponseCreators.withPayload;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.ws.test.client.MockWebServiceServer;
import org.springframework.xml.transform.StringSource;

class PaymentPartnerClientTest {
    private MockWebServiceServer mockServer;
    private PaymentPartnerClient client;

    @BeforeEach
    void setUp() {
        // Inject WebServiceTemplate thật có Jaxb2Marshaller.
        mockServer = MockWebServiceServer.createServer(webServiceTemplate);
        client = new DefaultPaymentPartnerClient(
            webServiceTemplate, endpointUri, requestMapper,
            responseMapper, faultMapper
        );
    }

    @Test
    void marshalsAndUnmarshalsPayment() {
        mockServer.expect(payload(new StringSource("""
            <pay:SubmitPaymentRequest
                xmlns:pay="urn:example:payments:v1">
                <pay:requestId>REQ-100</pay:requestId>
                <pay:amount>250.00</pay:amount>
                <pay:currency>VND</pay:currency>
            </pay:SubmitPaymentRequest>
            """)))
            .andRespond(withPayload(new StringSource("""
                <pay:SubmitPaymentResponse
                    xmlns:pay="urn:example:payments:v1">
                    <pay:paymentId>PAY-900</pay:paymentId>
                    <pay:status>ACCEPTED</pay:status>
                </pay:SubmitPaymentResponse>
                """)));

        PaymentReceipt receipt = client.submit(command);

        assertEquals("PAY-900", receipt.paymentId());
        assertEquals(PaymentStatus.ACCEPTED, receipt.status());
        mockServer.verify();
    }
}
~~~

Đây là skeleton: các dependencies, generated types và domain fixtures phải được inject/khởi tạo trong test context. Dùng template và marshaller thật, chỉ thay transport bằng MockWebServiceServer.

## 21. Ma trận test cases

| ID | Scenario | Expected |
|---|---|---|
| M01 | JAXB request hợp lệ | QName/values đúng |
| M02 | Decimal/date/enum | Lexical/semantic values đúng |
| M03 | Optional element absent | XML đúng contract |
| M04 | SOAP Header/Action | Header đúng |
| M05 | Request validate XSD | validPayload pass |
| U01 | Response hợp lệ | Unmarshal/domain mapping đúng |
| U02 | Optional/nil response | Nullable semantics đúng |
| U03 | Enum/date/decimal | Mapping chính xác |
| U04 | Unknown root QName | Contract error |
| U05 | Sai datatype/schema | Không business success |
| F01 | Sender Fault invalid account | Typed business exception |
| F02 | Sender Fault limit | Limit exception |
| F03 | Receiver Fault | Partner processing error |
| F04 | MustUnderstand/VersionMismatch | Protocol error |
| F05 | Unknown Fault detail | Safe fallback |
| T01 | Connection error | Communication error |
| T02 | Read timeout | Unknown outcome |
| T03 | TLS trust failure | Security/transport error |
| R01 | Retry cùng requestId | Không duplicate |
| R02 | DuplicateRequest Fault | Reconcile |
| L01 | Local marshal fail | Không request gửi đi |
| L02 | Malformed response | Unmarshal/contract error |
| O01 | Endpoint URI sai | Matcher fail |
| S01 | Error logging | Không lộ PII/credentials |

## 22. Troubleshooting

| Triệu chứng | Nguyên nhân | Hướng kiểm |
|---|---|---|
| Payload mismatch | JAXB annotations/namespace/wrapper | Generated QName/context |
| Unknown JAXB element | Thiếu ObjectFactory/type | contextPath/classesToBeBound |
| Marshal fail trước HTTP | Request graph/adapter/type | Root wrapper/schema |
| Unmarshal fail | QName/type/order sai | Response fixture/XSD |
| Decimal mất precision | Dùng double | BigDecimal |
| Date lệch ngày | LocalDate đổi instant/timezone | XSD ↔ Java type |
| Fault thành raw exception | Fault resolver/custom mapping | FaultMessageResolver |
| Sender Fault retry vô hạn | Retry mọi exception | Fault category |
| Timeout duplicate payment | Thiếu idempotency | requestId/reconciliation |
| verify fail | Client không gọi template/URI lệch | Branch/default URI |
| Mock pass, partner fail | Mock không kiểm TLS/HTTP | Wire/sandbox test |
| Logs lộ XML | Raw payload logging | Metadata-only logging |

## 23. Bài thực hành: client thanh toán contract-first

**Bối cảnh:** partner cung cấp payments.wsdl và payments.xsd. JAXB classes sinh trong package `com.example.payments.ws`. Operation SubmitPayment nhận requestId/account/amount/currency và trả paymentId/status hoặc SOAP Fault detail.

### Nhiệm vụ

1. Cấu hình Jaxb2Marshaller context path và XSD schemas.
2. Tạo WebServiceTemplate với endpoint URI externalized.
3. Tạo PaymentPartnerClient nhận PaymentCommand và trả PaymentReceipt.
4. Viết MockWebServiceServer test kiểm payload.
5. Kiểm QName, decimal precision, date, optional fields và namespace.
6. Dùng validPayload kiểm XSD.
7. Test unmarshalling và domain response mapping.
8. Test SOAP Header/Action bằng matcher.
9. Tạo Sender Fault invalid account và map typed exception.
10. Tạo Receiver Fault và map partner processing error.
11. Test malformed response/unknown QName/schema failure.
12. Test withError/withException theo API version.
13. Kiểm local marshalling failure không gửi request.
14. Test timeout và retry cùng requestId.
15. Kiểm logs không chứa PII, credentials hoặc raw payload.
16. Bổ sung HTTP/TLS test cho truststore và Content-Type.

### Câu hỏi tự kiểm tra

1. Marshalling và unmarshalling khác nhau thế nào?
2. Vì sao Jaxb2Marshaller dùng được hai chiều?
3. Payload matcher khác schema validation ra sao?
4. QName gồm phần nào?
5. Prefix khác nhau có luôn là lỗi không?
6. MockWebServiceServer thay phần nào của template?
7. Vì sao gọi verify()?
8. validPayload có kiểm Header không?
9. soapHeader matcher kiểm được gì?
10. SOAP Fault khác HTTP 503 ra sao?
11. Default FaultMessageResolver ném exception nào?
12. Vì sao không map mọi Receiver Fault thành retryable?
13. Timeout sau payment có chứng minh chưa commit không?
14. Vì sao malformed response không được tạo default success?
15. Khi nào cần HTTP/TLS test ngoài mock?
16. Vì sao không catch mọi RuntimeException thành InvalidPayment?

### Đáp án tham khảo

| Câu | Trả lời |
|---|---|
| 1 | Object → XML là marshal; XML → object là unmarshal. |
| 2 | Nó implement cả Marshaller và Unmarshaller. |
| 3 | Payload matcher so XML; schema matcher validate XSD. |
| 4 | Namespace URI và local name. |
| 5 | Không nếu QName vẫn giống. |
| 6 | Transport exchange được mock; template vẫn marshal/unmarshal. |
| 7 | Xác nhận expectations đã đáp ứng. |
| 8 | Không; validPayload kiểm Body. |
| 9 | Presence theo QName; value chi tiết cần XPath/custom matcher. |
| 10 | Fault là SOAP message-level; 503 là HTTP status. |
| 11 | SoapFaultClientException trong default resolver path. |
| 12 | Receiver Fault có thể permanent hoặc transient; cần code/policy. |
| 13 | Không; partner có thể commit rồi mất response. |
| 14 | Tạo false success và che contract violation. |
| 15 | Khi cần kiểm TLS, HTTP headers/status, proxy hoặc wire framing. |
| 16 | Che programming/config errors và sai domain semantics. |

## 24. Checklist production-quality

- [ ] JAXB types được generate từ đúng XSD/WSDL version.
- [ ] Jaxb2Marshaller context và schema resources đúng.
- [ ] Parser không xử lý DTD/external entities ngoài policy.
- [ ] Request tests kiểm QName, values, datatype và optional fields.
- [ ] validPayload kiểm outbound XML theo XSD.
- [ ] SOAP Header/Action được kiểm riêng.
- [ ] Response fixtures có edge cases.
- [ ] Unmarshal tests kiểm date/decimal/enum/nil/collections.
- [ ] Invalid response không tạo domain success.
- [ ] Sender/Receiver/Protocol Fault được phân loại riêng.
- [ ] Fault mapping dựa code/detail, không parse reason text tùy tiện.
- [ ] Transport/TLS errors có mapping riêng.
- [ ] Retry policy không retry mọi Fault.
- [ ] Payment retry dùng requestId/idempotency ổn định.
- [ ] Local marshalling failure không gửi request.
- [ ] MockWebServiceServer.verify() luôn được gọi.
- [ ] Fixtures không reuse mutable streams/messages.
- [ ] Logs không ghi raw SOAP, credentials, tokens hoặc PII.
- [ ] HTTP/TLS/proxy behavior được test riêng.
- [ ] Contract compatibility có fixtures/sandbox version hóa.

## 25. Tổng kết

Kiểm thử SOAP client cần xác minh **cả hai chiều chuyển đổi dữ liệu** và cách hệ thống phản ứng với lỗi. `Jaxb2Marshaller` biến generated JAXB request thành XML và response XML thành object; `MockWebServiceServer` kiểm message thực sự do `WebServiceTemplate` tạo bằng payload/schema/XPath/Header/Envelope matchers, rồi dựng response hoặc Fault để test client. Gọi `verify()` để chắc expectations đã được thực hiện.

Phân loại lỗi theo tầng: **marshalling error** xảy ra tại client trước transport; **unmarshalling/schema error** xảy ra khi response không khớp binding; **SOAP Fault** là message-level response của partner; **transport error** thuộc HTTP/TLS/connection. Map chúng thành domain exceptions/results có semantics rõ, dựa Fault code/detail theo contract và có fallback cho lỗi chưa biết. Đừng biến mọi exception thành business rejection hoặc retry mọi Fault.

Với operation có side effect, timeout có thể để lại **unknown outcome**. Dùng requestId/idempotency và reconciliation để tránh giao dịch trùng. Kết hợp mapper unit tests, `MockWebServiceServer`, XML/XSD assertions, SOAP Fault/transport tests và HTTP/TLS integration tests giúp client giữ đúng contract-first mapping và cung cấp lỗi nghiệp vụ đáng tin cậy.

## Tài liệu tham khảo

- [Spring Web Services Reference Documentation — Client-side API and Testing](https://docs.spring.io/spring-ws/docs/4.0.x/reference/html/#client)
- [Spring Web Services Reference Documentation — Client-side Testing](https://docs.spring.io/spring-ws/docs/4.0.x/reference/html/#client-testing)
- [MockWebServiceServer API](https://docs.spring.io/spring-ws/docs/4.0.x/api/org/springframework/ws/test/client/MockWebServiceServer.html)
- [Spring-WS 4.1.4 Reference Documentation](https://docs.spring.io/spring-ws/docs/4.1.4/reference/html/)
