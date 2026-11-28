# Kiểm thử hợp đồng cũ, mới bằng bộ thông điệp đã được lưu làm mẫu

## 1. Vì sao cần bộ thông điệp SOAP đã lưu?

Một dịch vụ SOAP contract-first thường được nhiều đối tác sử dụng trong thời gian dài. Client có thể được generate từ WSDL cũ, chạy trên Java, .NET hoặc ESB khác nhau. Khi server thay XSD, WSDL, namespace, SOAPAction, header hay Fault detail, client đang hoạt động có thể đột nhiên không còn tương thích dù ứng dụng server vẫn build thành công.

**Message corpus** là tập hợp request, response, SOAP Fault và metadata được lưu có kiểm soát làm mẫu. Khi thay đổi contract hoặc implementation, team chạy lại corpus để kiểm tra hành vi cũ và đánh giá tương thích giữa producer/consumer ở các phiên bản khác nhau.

Module **SPRING_WEB_SERVICES** học phát triển SOAP contract-first, thiết kế XSD/WSDL, JAXB/OXM, endpoint và SOAP client, SOAP Fault, interceptor, XML security, WS-Security, chứng chỉ và kiểm thử tương thích. Bài thuộc chương **Kiểm thử tích hợp**, hướng dẫn xây dựng và vận hành message corpus để kiểm thử hợp đồng cũ và mới.

### Mục tiêu học tập

Sau bài này, bạn có thể phân biệt schema/contract/regression/compatibility tests; lập manifest cho fixture; so XML theo QName và semantics; kiểm SOAP 1.1/1.2, SOAPAction, headers, Fault, WS-Security, MTOM; xây old/new matrix; bảo vệ fixture khỏi PII/credentials; chạy corpus trong Spring-WS và CI; quản lý golden baseline có review.

## 2. Corpus khác gì thư mục XML mẫu?

Một thư mục XML chỉ trở thành corpus hữu ích khi mỗi fixture có **ý nghĩa kiểm thử và expected behavior**. Mỗi message cần biết contract version, WSDL/XSD, direction (request/response/Fault), SOAP version, operation, root QName, headers, security, attachments, expected outcome và nguồn dữ liệu.

Cấu trúc tham khảo:

~~~text
soap-message-corpus/
  manifest.yml
  contracts/
    shipment-v1/shipment.wsdl
    shipment-v1/shipment-types.xsd
    shipment-v2/shipment.wsdl
    shipment-v2/shipment-types.xsd
  messages/
    v1/create-request.xml
    v1/create-response.xml
    v2/create-request.xml
    faults/invalid-request.xml
    faults/access-denied.xml
    mtom/upload-request.mime
~~~

Đây là layout gợi ý. Fixture cần được version cùng manifest/schema identity; không suy version chỉ từ tên file.

## 3. Các loại kiểm thử cần phân biệt

| Loại test | Câu hỏi | Ví dụ |
| --- | --- | --- |
| Schema validation | XML có đúng XSD? | Required element, type, cardinality |
| Contract test | Message đúng WSDL binding? | QName, SOAPAction, Fault |
| Regression test | Behavior đã chấp nhận có bị hỏng? | JAXB mapping cũ vẫn đúng |
| Backward compatibility | Producer mới hiểu message consumer cũ? | v1 client gọi server v2 |
| Forward compatibility | Consumer mới đọc message producer cũ? | v2 client đọc response v1 |
| Interoperability | Stack khác nhau trao đổi đúng? | Java với .NET |
| End-to-end | Toàn pipeline hoạt động? | TLS, WSS4J, endpoint, database |

XML hợp lệ theo XSD vẫn có thể sai SOAP binding. Mock test pass không chứng minh mTLS, proxy, MIME wire format hoặc interoperability thật.

## 4. Golden message là baseline có chủ đích

**Golden fixture** là message đã được review và chấp nhận làm baseline. Ví dụ request v1:

~~~xml
<soapenv:Envelope
    xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
    xmlns:sh="urn:example:shipment:v1">
  <soapenv:Header/>
  <soapenv:Body>
    <sh:CreateShipmentRequest>
      <sh:requestId>REQ-TEST-1001</sh:requestId>
      <sh:accountId>ACCT-TEST-A</sh:accountId>
      <sh:orderReference>ORDER-TEST-55</sh:orderReference>
      <sh:destinationCode>HCM-01</sh:destinationCode>
    </sh:CreateShipmentRequest>
  </soapenv:Body>
</soapenv:Envelope>
~~~

Đây là fixture giả lập; cần validate bằng WSDL/XSD thật trước khi chấp nhận. Golden không bất biến vĩnh viễn. Có thể thay khi contract mới được duyệt hoặc fixture cũ sai; mỗi baseline update cần lý do, semantic diff, compatibility evidence và review. Không update expected snapshot chỉ để làm CI xanh.

## 5. Manifest mô tả fixture

~~~yaml
corpusVersion: 1
suite: shipment-soap-contract
fixtures:
  - id: v1-create-valid
    file: messages/v1/create-request.xml
    direction: request
    contract: shipment-v1
    soapVersion: "1.1"
    operation: CreateShipment
    payloadQName: "{urn:example:shipment:v1}CreateShipmentRequest"
    expected:
      outcome: accepted
      responseFixture: v1-create-response
    sensitivity: synthetic
    tags: [backward-compatibility, create]
  - id: v1-invalid-account
    file: messages/v1/invalid-account.xml
    direction: request
    contract: shipment-v1
    soapVersion: "1.1"
    operation: CreateShipment
    expected:
      outcome: soap-fault
      faultCode: CLIENT
~~~

Đây là manifest schema do dự án định nghĩa, không phải chuẩn Spring-WS. Validate manifest, ID uniqueness, fixture existence và đường dẫn nằm trong corpus root. Metadata tối thiểu gồm fixture ID, file, direction, contract, SOAP version, operation, QName, expected outcome, sensitivity/source, schema digest và tags.

## 6. QName và namespace là một phần contract

XML prefix không phải danh tính element. Hai payload dùng prefix khác nhưng cùng namespace URI/local name có thể cùng expanded QName. Ngược lại, giữ prefix nhưng đổi namespace URI từ v1 sang v2 là QName khác, có thể khiến endpoint Spring-WS định tuyến bằng @PayloadRoot không còn match.

Kiểm namespace URI, local name, element qualification, XSD sequence/order, cardinality, xsi:nil, absent/empty distinction và namespace của SOAP Envelope/Fault. Không phụ thuộc prefix trừ khi cần test workaround cho một consumer cụ thể.

Ví dụ:

~~~xml
<a:CreateShipmentRequest xmlns:a="urn:example:shipment:v1">
  <a:requestId>REQ-1</a:requestId>
</a:CreateShipmentRequest>
~~~

~~~xml
<shipment:CreateShipmentRequest
    xmlns:shipment="urn:example:shipment:v1">
  <shipment:requestId>REQ-1</shipment:requestId>
</shipment:CreateShipmentRequest>
~~~

Hai fragments có cùng QName root nếu namespace URI và local name giống nhau.

## 7. XSD/WSDL evolution và breaking changes

| Thay đổi | Rủi ro |
| --- | --- |
| Thêm optional response element | Thường tương thích nhưng phải thử client cũ |
| Thêm required request element | Client cũ không gửi, breaking |
| Đổi namespace | QName đổi, thường breaking |
| Đổi type string sang integer | Binding/serialization thay đổi |
| Thu hẹp enum | Client gửi giá trị cũ có thể bị reject |
| Mở rộng enum | Consumer strict có thể reject giá trị mới |
| minOccurs 0 thành 1 | Field trở thành required |
| Đổi nillable/absent semantics | JAXB mapping thay đổi |
| Đổi element order | XSD sequence có thể reject message cũ |
| Xóa Fault detail | Client error mapping có thể hỏng |
| Đổi SOAPAction/binding | Routing có thể thất bại |

Không có quy tắc “thêm field luôn tương thích”. Code generator, XSD validator và deserializer có thể xử lý unknown fields khác nhau. Compatibility phải được kiểm với consumer implementations và policy đã công bố.

## 8. Backward compatibility: client cũ với server mới

Backward compatibility thường có nghĩa producer/server mới vẫn hiểu message từ consumer/client cũ và trả response mà client cũ có thể xử lý.

| Message/client | Server cũ | Server mới |
| --- | --- | --- |
| Request v1 | Baseline | Backward compatibility |
| Request v2 | Không nhất thiết hỗ trợ | Native v2 |
| Invalid request v1 | Reject theo contract | Vẫn reject tương ứng |
| WS-Security v1 | Policy v1 | Không âm thầm nới policy |

Test QName routing, SOAP version, WSS4J actions, JAXB mapping, business command và response/Fault shape. Kiểm response server mới bằng consumer model cũ: server có thể nhận request v1 nhưng serialize response mới khiến client cũ lỗi.

## 9. Forward compatibility: client mới với server cũ

Forward compatibility thường mô tả consumer/client mới xử lý message từ producer/server cũ, hữu ích trong rolling deployments.

| Response/message | Consumer cũ | Consumer mới |
| --- | --- | --- |
| Response v1 | Baseline | Forward compatibility |
| Response v2 | Có thể không hỗ trợ | Native v2 |
| Fault v1 | Baseline | Client mới map lỗi cũ |
| Missing optional field | Theo contract | Phải xử lý rõ |

Client v2 có thể đọc response v1 thiếu field mới nếu semantics cho phép. Không tự gán default business-critical nếu contract không định nghĩa. Compatibility window phải nêu version được hỗ trợ, deprecation deadline, endpoint routing và thời điểm retire.

## 10. Ma trận old/new producer-consumer

| Producer | Consumer | Mục đích |
| --- | --- | --- |
| Old | Old | Historical baseline |
| New | Old | Backward compatibility |
| Old | New | Forward compatibility |
| New | New | Native contract |
| New | Unsupported old client | Rejection có kiểm soát |

Test report cần ghi rõ ai phát và ai nhận message. Với request, consumer thường tạo request/provider nhận; với response, provider phát/consumer nhận. Chỉ ghi old/new passed mà không nêu direction dễ gây hiểu sai.

## 11. SOAP 1.1, SOAP 1.2 và Fault fixtures

Envelope namespaces khác nhau:

- SOAP 1.1: http://schemas.xmlsoap.org/soap/envelope/
- SOAP 1.2: http://www.w3.org/2003/05/soap-envelope

Ngoài namespace, content type, action parameter, binding và Fault structure cũng khác. SOAP 1.1 Fault có faultcode/faultstring/detail; SOAP 1.2 Fault có Code/Reason/Detail theo cấu trúc namespace riêng.

Corpus cần fixtures cho Sender/Client, Receiver/Server, authentication/authorization, business validation, transient dependency failure và sanitized internal error. Test protocol, Fault QName/code, public reason, detail element QName/fields, HTTP status/content type và client exception mapping. Không lộ stack trace, SQL, secret, file path hoặc tenant data. Không gom mọi lỗi thành một generic Fault fixture.

## 12. WS-Addressing và custom headers

Nếu contract dùng WS-Addressing, kiểm Action, To, MessageID, RelatesTo và Fault addressing. MessageID có thể đổi mỗi attempt nên semantic compare cần normalize hoặc dùng fixture value cố định.

Với custom headers, kiểm QName, namespace version, mustUnderstand, signed coverage, unknown-header behavior và mapping. Header Role/TenantId do client gửi không tự tạo authority hoặc chứng minh identity. Nếu header được ký, test certificate trust và message parts thực sự được ký.

## 13. WS-Security fixtures không nên replay vô hạn

WS-Security có UsernameToken, Timestamp, XML Signature và Encryption. Raw production envelopes không phù hợp làm golden tests vì timestamp hết hạn, nonce bị replay cache từ chối, signature phụ thuộc signed bytes, certificate hết hạn và secret không được lưu trong repo.

Tách **business payload fixtures** khỏi security runtime headers. Mỗi test tạo UsernameToken, nonce, timestamp và signature mới bằng test-only credentials rồi gửi qua WSS4J. Khi test signature verification, giữ nguyên fixture đã ký; nếu sửa nội dung phải ký lại bằng test key.

Security replay cache chống replay message/token; nó không thay business idempotency hoặc contract corpus.

## 14. So sánh XML theo semantics

Raw string comparison dễ fail do prefix, indentation, line endings, attribute order hoặc XML declaration. Dùng XML parser an toàn, QName/XPath assertions, XSD validation hoặc semantic projection.

Không normalize mọi whitespace: text nodes, mixed content và xml:space preserve có thể có ý nghĩa. XML canonicalization có rules riêng và không tương đương business normalization.

So theo lớp:

1. Envelope: SOAP version, Header, Body, Fault.
2. Contract: QName, cardinality, XSD types.
3. Business payload: fields và domain semantics.
4. Security: token, signature, timestamp, trust policy.
5. Transport: content type, action, status, MIME attachments.

Không dùng một comparator duy nhất cho cả năm lớp.

## 15. XSD validation và JAXB generated models

Validate fixture theo đúng schema version và import/include closure. Kiểm entrypoint, resolver/catalog và namespace; không cho parser tải external schema tùy tiện.

JAXB model phải generate từ đúng version XSD. Regenerate code không tự chứng minh compatibility. Corpus nên có fixtures cho element absent, xsi:nil, empty element, optional/required, unknown enum, repeated element/order, date/time và choice/substitution groups nếu có.

JAXB provider có thể biểu diễn absent và nil khác nhau. Test object mapping chứ không chỉ XML validation.

## 16. SOAPAction và HTTP transport

WSDL binding có thể định nghĩa SOAPAction (SOAP 1.1) hoặc action parameter trong content type (SOAP 1.2). Wire-level tests cần kiểm HTTP method/path, Content-Type/charset, SOAPAction, envelope version, HTTP status cho success/Fault, redirect/proxy, compression/chunking nếu dùng và TLS hostname/SAN/mTLS.

Mock payload không xác minh HTTP headers. Dùng HTTP server fixture, transport recorder hoặc partner sandbox.

## 17. MTOM và MIME attachments

Một SOAP body có xop:Include không đủ nếu thiếu MIME parts. MTOM corpus cần giữ multipart/related content type/boundary, SOAP part, Content-ID, XOP href, attachment content type/length, binary bytes/checksum và policy MTOM.

Boundary có thể đổi theo lần serialize; semantic compare nên map MIME parts theo Content-ID và kiểm bytes/checksum, không so raw multipart string. Dùng synthetic attachments, giới hạn số parts/size/memory và có thể tách smoke suite với extended attachment suite.

## 18. Sanitize dữ liệu trước khi lưu corpus

Production capture có thể chứa PII, account/order IDs, Authorization, UsernameToken, SAML assertions, certificate metadata, correlation IDs, hostnames, IPs và attachment documents. Không commit raw production SOAP messages chỉ vì cần regression tests.

Data-minimize, dùng synthetic values, review redaction và xác định quyền sử dụng. Thay string tùy tiện có thể làm signature, XSD pattern, checksum hoặc cross-field relationship hỏng. Tách structural fixtures không có credentials; sanitized business fixture được ký lại bằng test keys; restricted forensic captures lưu ngoài source corpus với access/retention riêng.

Không lưu test secret trong fixture; dùng test keystore/provider tách biệt.

## 19. Metadata bảo mật và versioning baseline

Manifest có thể ghi sensitivity, source, redaction đã làm, usesTestCertificate, containsRuntimeSignature và review date. Đây là metadata dự án tự định nghĩa; không đánh dấu sanitized theo cảm tính.

Version hóa cùng nhau WSDL/XSD/policy dependencies, fixtures/manifest, runner/comparator và expected outcomes. Có thể lưu SHA-256 digest để xác định artifact bytes; digest không chứng minh contract đã được approve.

Mỗi baseline update cần nêu fixture ID, contract version, behavior thay đổi, old/new matrix, sanitizer change và reviewer. Không tự động ghi actual output thành golden snapshot trong CI.

## 20. Nhiều contract versions và anti-corruption mapping

Nếu v1/v2 cùng tồn tại, giữ JAXB DTO theo từng version:

~~~text
SOAP v1 DTO -> V1 mapper -> Application command
SOAP v2 DTO -> V2 mapper -> Application command
Application result -> V1 response mapper -> v1 response
Application result -> V2 response mapper -> v2 response
~~~

Fixture v1/v2 có thể cùng đại diện một business intent. Test mapper để không mất semantics. Không để generated DTO mới lan vào domain service và vô tình đổi logic cũ.

## 21. Corpus runner

Runner nên nạp manifest, validate metadata/digest, resolve path trong corpus root, parse XML an toàn, validate XSD, gửi message tới in-memory context hoặc HTTP integration endpoint, kiểm response/Fault, so semantic output và tạo fixture-level report.

~~~java
public interface SoapCorpusCase {
    String id();
    String contractVersion();
    Path requestFixture();
    ExpectedOutcome expected();
}
~~~

Đây là abstraction dự án tự định nghĩa, không phải Spring-WS API. Path cần được resolve trong corpus root và bảo vệ directory traversal. Runner phải fail nếu manifest thiếu, XML không parse được hoặc schema không tồn tại; không nuốt exception rồi báo pass.

## 22. MockWebServiceServer kiểm SOAP client

Spring-WS có MockWebServiceServer để kiểm request tạo bởi WebServiceTemplate và trả response fixture:

~~~java
import static org.springframework.ws.test.client.RequestMatchers.payload;
import static org.springframework.ws.test.client.ResponseCreators.withPayload;
import org.springframework.core.io.ClassPathResource;
import org.springframework.ws.test.client.MockWebServiceServer;

MockWebServiceServer server =
        MockWebServiceServer.createServer(webServiceTemplate);

server.expect(payload(new ClassPathResource(
        "corpus/v1/get-status-request-payload.xml")))
    .andRespond(withPayload(new ClassPathResource(
        "corpus/v1/get-status-response-payload.xml")));

GetShipmentStatusResponse response =
        client.getStatus("SHP-TEST-1");

server.verify();
~~~

Đây là mẫu API định hướng; template/client/JAXB classes cần cấu hình trong test. payload matcher kiểm payload; nếu cần full Envelope, headers, SOAPAction, MTOM hoặc WS-Security cần custom matcher/transport tests. MockWebServiceServer không chứng minh TCP reset, TLS, proxy hoặc cross-runtime interoperability.

## 23. MockWebServiceClient kiểm SOAP server

Spring-WS có MockWebServiceClient gửi payload vào application context:

~~~java
import static org.springframework.ws.test.server.RequestCreators.withPayload;
import static org.springframework.ws.test.server.ResponseMatchers.noFault;
import static org.springframework.ws.test.server.ResponseMatchers.payload;
import org.springframework.core.io.ClassPathResource;
import org.springframework.ws.test.server.MockWebServiceClient;

MockWebServiceClient client =
        MockWebServiceClient.createClient(applicationContext);

client.sendRequest(withPayload(new ClassPathResource(
        "corpus/v1/create-request.xml")))
    .andExpect(noFault())
    .andExpect(payload(new ClassPathResource(
        "corpus/v1/create-response.xml")));
~~~

Context phải có đúng MessageDispatcher, endpoints, interceptors, marshaller và exception resolvers. Nếu kiểm WS-Security, xác nhận request đi qua WSS4J interceptor; payload-only test bỏ Envelope/Header không chứng minh security chain.

Có cả positive và negative fixtures: required field thiếu, unknown namespace, mustUnderstand header không hỗ trợ, XML quá lớn, token invalid/expired và unauthorized resource.

## 24. Security negative corpus và parser hardening

Có thể lưu negative fixtures cho malformed XML, DTD/external entity, XInclude, deep nesting, huge text, duplicate IDs, signature wrapping, invalid timestamp/replay, malformed MIME boundary và attachment quá lớn.

Chạy trong sandbox có resource limits, network-deny harness và expected rejection. Với XXE/SSRF, dùng mock resolver/blocked network để xác minh parser không truy cập host ngoài. Không replay payload khai thác vào production.

## 25. CI pipeline nhiều tầng

~~~mermaid
flowchart TD
    A[Pull request] --> B[Manifest and fixture integrity]
    B --> C[Compile WSDL and XSD versions]
    C --> D[Schema and XML security checks]
    D --> E[Fast corpus tests]
    E --> F[Old consumer with new provider]
    F --> G[New consumer with old provider]
    G --> H[SOAP Fault and header tests]
    H --> I[HTTP TLS and MTOM integration]
    I --> J[Partner sandbox tests]
    J --> K[Compatibility report]
~~~

Gợi ý phân tầng: PR fast chạy manifest/schema/in-memory corpus; nightly/merge chạy old/new matrix, DB, security và transport; release candidate chạy TLS/mTLS, attachment, cross-runtime và partner sandbox. Nếu skip fixtures, report phải nêu ID/lý do/pipeline chạy sau. Không báo pass toàn suite khi một phần bị skip mà không nêu.

## 26. Report incompatibility và review golden update

Ví dụ report:

~~~text
Fixture: v1-create-valid
Producer under test: server-v2
Consumer model: client-v1
Result: FAIL
Layer: SOAP payload QName
Expected: {urn:example:shipment:v1}CreateShipmentResponse
Actual:   {urn:example:shipment:v2}CreateShipmentResponse
Impact: old client cannot route/unmarshal response
Classification: BREAKING
Evidence: corpus report + WSDL/XSD digest
~~~

Classification có thể là COMPATIBLE, CONDITIONALLY_COMPATIBLE, BREAKING hoặc UNVERIFIED. Không đổi breaking thành compatible chỉ bằng cách sửa expected snapshot.

Quy trình fixture update: thêm/sửa có mô tả; validate XML/manifest/schema; review sanitizer; hiển thị semantic diff; chạy old/new matrix; contract owner review; chỉ cập nhật baseline khi behavior được chấp thuận; giữ fixture versions còn được hỗ trợ.

## 27. Anti-pattern

- So raw XML string: prefix/indentation gây false failure. So QName/semantics.
- Chỉ validate XSD: bỏ sót binding, Fault, security, business mapping. Thêm test theo lớp.
- Chỉ lưu happy path: thiếu Fault/edge/security fixtures. Lưu negative cases.
- Commit production capture: lộ PII/token. Sanitize/review.
- Replay signed envelope vô hạn: timestamp/nonce hết hạn. Generate headers mới.
- Auto-update golden: che breaking changes. Cần semantic diff/approval.
- Chỉ test new/new: bỏ sót client cũ. Chạy old/new matrix.
- Fixture thiếu schema version: không biết validate bằng XSD nào. Gắn artifact identity.
- Tách MTOM XML khỏi binary: mất MIME/CID. Giữ multipart fixture.
- Nuốt lỗi runner: CI xanh giả. Missing fixture/schema phải fail.
- Coi thêm field luôn non-breaking: strict clients/enums/sequence có thể fail. Test consumer.
- Log raw XML: lộ dữ liệu. Report XPath/metadata đã redacted.

## 28. Quy trình triển khai đề xuất

1. Liệt kê contract versions, endpoints/bindings và consumer owners.
2. Thu thập synthetic/sandbox messages; xin phê duyệt trước khi giữ capture.
3. Sanitize PII, tokens, security material, hostnames và attachments.
4. Tạo manifest ghi fixture ID, direction, operation, contract và SOAP version.
5. Version WSDL/XSD cùng imports/includes và digest.
6. Validate fixture bằng đúng schema version.
7. Tách semantic compare khỏi security/transport validation.
8. Tạo negative fixtures cho Fault/header/invalid field/security.
9. Xây old/new matrix theo compatibility promise.
10. Dùng MockWebServiceServer/MockWebServiceClient cho in-memory tests.
11. Bổ sung HTTP/TLS/MTOM integration khi cần wire-level evidence.
12. Dùng test credentials và runtime-generated WS-Security headers.
13. Chạy fast/nightly/release-candidate suite trong CI.
14. Report fixture-level outcome, không log raw SOAP.
15. Review golden updates và deprecate fixture theo contract lifecycle.

## 29. Bài tập thực hành

1. **Tạo corpus v1:** tạo WSDL/XSD cho GetShipmentStatus/CreateShipment; lưu request, response, Fault và manifest.
2. **Đổi namespace v2:** chạy v1 request với server v2; xác định route/reject và compatibility strategy.
3. **Optional response element:** thêm estimatedDeliveryAt optional, thử consumer v1; sau đó thêm required field để thấy breaking change.
4. **Absent/nil/empty:** tạo ba fixtures và kiểm XSD/JAXB mapping.
5. **SOAP Fault 1.1/1.2:** kiểm code/reason/detail và exception mapping.
6. **Semantic comparator:** đổi prefix/indentation phải pass; đổi namespace URI phải fail.
7. **WS-Security:** tạo timestamp/nonce/signature mới bằng test keys và kiểm replay.
8. **MTOM:** kiểm Content-ID, XOP, checksum, boundary normalization và size limit.
9. **Old/new matrix:** report cả hai chiều consumer/provider.
10. **CI baseline review:** tạo QName regression, sau đó review update với compatibility evidence.

## 30. Checklist trước khi phát hành

- [ ] Corpus có manifest và fixture IDs ổn định.
- [ ] Fixture ghi direction, operation, contract version và SOAP version.
- [ ] WSDL/XSD dependency closure được version hóa.
- [ ] Request/response/Fault validate bằng schema đúng version.
- [ ] QName được kiểm theo namespace URI/local name.
- [ ] SOAP 1.1/1.2, content type và action được kiểm riêng.
- [ ] Optional/required/nillable/absent/empty/enum/cardinality có fixture.
- [ ] Fault detail QName/code được version hóa.
- [ ] WS-Addressing/custom headers/mustUnderstand có test.
- [ ] WS-Security dùng test credentials và runtime timestamp/nonce/signature.
- [ ] Không lưu production envelope hoặc commit secret/token.
- [ ] Production-derived fixtures được sanitize và review.
- [ ] MTOM giữ MIME parts, Content-ID và binary checksum.
- [ ] XML comparison theo semantic layers.
- [ ] Volatile fields normalize có chủ đích.
- [ ] Old consumer + new producer được test.
- [ ] New consumer + old producer được test theo compatibility promise.
- [ ] New/new baseline và negative cases đều chạy.
- [ ] Mock tests không bị coi là thay HTTP/TLS interoperability.
- [ ] Missing fixture/schema làm test fail, không silently skip.
- [ ] Golden update có semantic diff, review và evidence.
- [ ] CI report fixture-level failures/skips.
- [ ] Logs không chứa PII/credentials/raw sensitive SOAP.
- [ ] Có retention/deprecation policy.

## 31. Tài liệu tham khảo

- [Spring Web Services — Reference](https://docs.spring.io/spring-ws/reference/): contract-first, WSDL/XSD, endpoints, interceptors và clients.
- [Spring Web Services — Testing](https://docs.spring.io/spring-ws/reference/testing.html): MockWebServiceServer, MockWebServiceClient và test support.
- [WebServiceTemplate Javadoc](https://docs.spring.io/spring-ws/docs/current/api/org/springframework/ws/client/core/WebServiceTemplate.html): marshal/send/receive và fault handling.
- [W3C — XML Schema 1.1](https://www.w3.org/TR/xmlschema11-1/): element/type/cardinality, nil và validation.
- [W3C — Namespaces in XML](https://www.w3.org/TR/xml-names/): namespace URI, prefix và expanded QName.
- [W3C — SOAP 1.2](https://www.w3.org/TR/soap12-part1/): Envelope, processing model và Fault.
- [W3C — SOAP 1.1](https://www.w3.org/TR/2000/NOTE-SOAP-20000508/): Envelope, binding và Fault.
- [W3C — XML Canonicalization](https://www.w3.org/TR/xml-c14n11/): canonical XML.
- [W3C — SOAP MTOM](https://www.w3.org/TR/soap12-mtom/): MTOM/XOP.
- [OASIS — WS-Security 1.1.1](https://docs.oasis-open.org/wss-m/wss/v1.1.1/os/wss-SOAPMessageSecurity-v1.1.1-os.html): SOAP tokens, signatures và encryption.
- [OWASP — Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html): redaction và bảo vệ log.
- [OWASP — Secrets Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html): secret lifecycle/access control.
- [IETF RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110): HTTP semantics.

Ví dụ dùng Spring-WS theo hướng minh họa. Đối chiếu Spring-WS, JAXB provider, WSS4J, SOAP stack và WSDL/XSD thực tế. Manifest, runner và comparator là thành phần dự án tự xây, không phải tính năng tự động của Spring-WS.

## 32. Tổng kết

**Message corpus biến các tương tác SOAP đã được chấp thuận thành một mạng lưới regression và compatibility tests có thể chạy lại.** Một fixture hữu ích phải xác định contract version, operation/QName, SOAP version, expected outcome và mức độ sanitize.

Khi phát hành contract mới, kiểm cả hai chiều theo compatibility promise: **consumer cũ với producer mới** để đánh giá backward compatibility và **consumer mới với producer cũ** để đánh giá forward compatibility. XSD/WSDL là nền tảng, nhưng còn phải kiểm binding/action, namespace, headers, Fault, JAXB semantics, WS-Security, MTOM và transport.

Trong **SPRING_WEB_SERVICES**, kết hợp MockWebServiceServer/MockWebServiceClient cho in-memory tests với HTTP/TLS/partner integration khi cần. So theo QName và business semantics, bảo vệ corpus khỏi PII/credentials, review mọi golden baseline update và report rõ fixture pass/fail/skip. Khi corpus được version hóa và chạy trong CI, mỗi thay đổi WSDL/XSD có evidence tương thích trước khi đến hệ thống đối tác.
