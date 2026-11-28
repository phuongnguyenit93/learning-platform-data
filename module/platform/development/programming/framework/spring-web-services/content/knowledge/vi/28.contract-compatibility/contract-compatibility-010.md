# Quy trình thông báo thay đổi, ngừng hỗ trợ và kiểm tra client phụ thuộc

## 1. Vì sao thay đổi một SOAP contract phải đi cùng kế hoạch cho consumer?

Trong module **SPRING_WEB_SERVICES**, dịch vụ SOAP được xây dựng theo hướng contract-first. XSD xác định cấu trúc và ràng buộc dữ liệu; WSDL mô tả operations, messages, bindings và endpoints; JAXB ánh xạ XML với Java; Spring-WS cung cấp endpoint và client. Contract trở thành thỏa thuận kỹ thuật giữa provider và mọi consumer đang phụ thuộc.

Khi provider thay schema, operation, SOAP action, namespace, fault, WS-Addressing header, security policy hoặc endpoint, thay đổi có thể ảnh hưởng client của nhiều đội và nền tảng. Client không nhất thiết được build hoặc deploy cùng nhịp với provider. Có client cũ chạy nhiều tháng, batch chỉ hoạt động cuối tháng, partner bên ngoài cần change approval, hoặc thiết bị tích hợp không thể cập nhật nhanh.

Quy trình phải trả lời:

- Thay đổi có tương thích ngược và xuôi không?
- Consumer nào đang sử dụng thành phần bị thay đổi?
- Khi nào provider thông báo, bắt đầu deprecation và kết thúc hỗ trợ?
- Consumer có cách kiểm tra và chứng minh đã migrate không?
- Provider có thể chạy song song phiên bản cũ/mới và rollback thế nào?
- Dựa vào dữ liệu nào để quyết định ngừng phiên bản cũ an toàn?

**Mục tiêu là tránh làm hỏng consumer đang hoạt động và tạo bằng chứng trước khi kết thúc hỗ trợ.** Một thông báo gửi đi hoặc WSDL mới được publish chưa chứng minh client đã sẵn sàng.

### Mục tiêu học tập

1. Phân loại thay đổi SOAP/WSDL/XSD thành compatible, conditionally compatible hoặc breaking.
2. Phân biệt backward compatibility, forward compatibility và interoperability.
3. Lập inventory consumer cùng owner, version, traffic và dependency.
4. Thiết kế versioning, parallel support và deprecation timeline.
5. Viết release/change notice có ngày hiệu lực, tác động, hành động và kênh hỗ trợ.
6. Xây consumer-driven contract tests và provider compatibility gates.
7. Theo dõi migration bằng telemetry và bằng chứng kỹ thuật.
8. Rollout/rollback thay đổi contract theo từng giai đoạn.
9. Quyết định go/no-go khi ngừng hỗ trợ contract cũ.
10. Lập migration playbook cho consumer nội bộ và partner bên ngoài.

## 2. Các thuật ngữ phải thống nhất

| Thuật ngữ | Ý nghĩa |
|---|---|
| Provider | Hệ thống công bố WSDL/XSD và cung cấp SOAP operations |
| Consumer | Client gọi operation hoặc phụ thuộc schema/fault/security policy |
| Contract version | Phiên bản quản lý của WSDL/XSD và policy liên quan |
| Compatible change | Thay đổi không làm hỏng consumer trong phạm vi cam kết |
| Breaking change | Thay đổi có thể khiến consumer không parse, bind hoặc thực hiện đúng |
| Deprecation | Thông báo thành phần sẽ ngừng khuyến nghị và có kế hoạch kết thúc hỗ trợ |
| End of support | Mốc provider dừng maintenance/support theo chính sách |
| Sunset | Thời điểm endpoint/operation/version cũ thực sự bị tắt |
| Migration | Consumer chuyển sang contract/behavior được hỗ trợ |
| Compatibility evidence | Test, traffic observation, acknowledgement hoặc artifact chứng minh migration |

Deprecation, end of support và sunset là ba mốc khác nhau. Không tuyên bố deprecated rồi tắt endpoint ngay nếu policy cam kết khoảng chuyển tiếp.

### 2.1. Backward và forward compatibility

**Backward compatibility** thường xét provider mới có tiếp tục phục vụ consumer cũ không.

**Forward compatibility** thường xét consumer hiện tại có chịu được contract/data mới không.

Hai khái niệm phụ thuộc hướng thay đổi, parser/JAXB configuration và semantics. Một thay đổi có thể backward compatible với một nhóm client nhưng không forward compatible với nhóm khác.

### 2.2. Compatibility không chỉ là XML parse được

Compatibility cần xét XML structure/namespace, WSDL binding, SOAP version, SOAPAction/Action, XSD types/cardinality/facets/order, SOAP Fault semantics, WS-Addressing, WS-Security, authentication/authorization, operation semantics, idempotency, timeout, payload size và availability.

## 3. Quy trình thay đổi contract từ đầu đến cuối

~~~mermaid
flowchart TD
    A["Change request"] --> B["Classify schema, WSDL and behavior impact"]
    B --> C["Inventory affected consumers"]
    C --> D["Design compatibility and migration"]
    D --> E["Publish notice and migration artifacts"]
    E --> F["Run provider and consumer contract tests"]
    F --> G{"Evidence and approvals ready?"}
    G -->|"No"| H["Fix or extend transition"]
    H --> F
    G -->|"Yes"| I["Deploy parallel/new capability"]
    I --> J["Observe traffic and migration"]
    J --> K{"Exit criteria met?"}
    K -->|"No"| L["Support old path and resolve blockers"]
    L --> J
    K -->|"Yes"| M["Sunset old contract"]
~~~

### 3.1. Đề xuất

Change owner ghi lý do, thành phần, thời điểm, consumer bị tác động và deadline. Không bắt đầu từ một file XSD vừa sửa mà không có change record.

### 3.2. Phân tích

Xác định WSDL/XSD/policy diff, runtime behavior, inventory, compatibility classification và phương án rollback.

### 3.3. Chuẩn bị migration

Cung cấp contract, generated-client guidance, examples, test endpoint, deprecation dates và support channel.

### 3.4. Chuyển đổi

Consumer cập nhật client, chạy contract tests, xác nhận staging và rollout theo cohort. Provider theo dõi traffic/version/consumer state.

### 3.5. Sunset

Chỉ tắt contract cũ khi đạt exit criteria đã công bố, có xác nhận cần thiết và có quy trình exceptional consumers.

## 4. Phân loại thay đổi XSD

XSD quyết định element/attribute names, namespace, types, occurrence, order, facets và substitution rules. Thay đổi schema ảnh hưởng JAXB generation và runtime validation.

| Thay đổi | Đánh giá ban đầu | Rủi ro |
|---|---|---|
| Thêm optional element vào response | Có thể compatible | Strict validator/client không chịu unknown element |
| Thêm required element vào request | Breaking | Client cũ không gửi field mới |
| Xóa response element | Breaking | Client đang đọc field bị mất |
| Đổi namespace URI | Breaking | QName/generated classes đổi |
| Đổi element name/case | Breaking | JAXB/XPath không khớp |
| Nới minOccurs từ 1 xuống 0 | Conditional | Client giả định field luôn hiện diện |
| Siết maxLength/pattern | Conditional/breaking | Payload hiện tại không còn hợp lệ |
| Đổi string sang integer | Thường breaking | XML lexical value/JAXB type đổi |
| Thêm enum value | Conditional | Generated enum/strict parser có thể fail |
| Đổi sequence/order | Thường breaking | Schema validation/serializer đổi |
| Thêm optional request field | Có thể compatible | Provider mới phải xử lý field vắng |
| Đổi default/fixed value | Conditional | Business semantics thay đổi |

### 4.1. Optional response element chưa chắc an toàn

Schema cũ:

~~~xml
<xs:complexType name="OrderResponseType">
  <xs:sequence>
    <xs:element name="orderId" type="xs:string"/>
    <xs:element name="status" type="xs:string"/>
  </xs:sequence>
</xs:complexType>
~~~

Schema mới thêm optional field:

~~~xml
<xs:complexType name="OrderResponseType">
  <xs:sequence>
    <xs:element name="orderId" type="xs:string"/>
    <xs:element name="status" type="xs:string"/>
    <xs:element name="estimatedDelivery"
                type="xs:date" minOccurs="0"/>
  </xs:sequence>
</xs:complexType>
~~~

JAXB client generate từ XSD cũ có thể bỏ qua unknown element nếu binding không strict. Client khác validate response bằng schema cũ và reject. Cần test cả hai.

### 4.2. Optional request field có thể đổi semantics

Provider mới có thể chấp nhận field vắng, nhưng default behavior có thể khác business expectation. Optional trong XSD không có nghĩa optional về nghiệp vụ.

### 4.3. Thêm enum value

Giả sử response status enum có PENDING, COMPLETED và REJECTED. Thêm ON_HOLD có thể làm generated enum/parser client cũ fail hoặc map unknown value thành null/exception tùy binding. Test client thật, không chỉ compile XSD.

## 5. WSDL thay đổi ngay cả khi XSD giữ nguyên

WSDL mô tả messages, portType/interfaces, bindings, SOAP version, operation actions, service/port và endpoint address.

| Thay đổi WSDL | Rủi ro |
|---|---|
| Đổi targetNamespace | QName và interface identity đổi |
| Đổi operation name | Generated API đổi |
| Đổi input/output message parts | Serialization mapping đổi |
| Đổi SOAP 1.1 sang SOAP 1.2 | Envelope/content-type/protocol đổi |
| Đổi SOAPAction hoặc WS-Addressing Action | Routing/dispatch fail |
| Đổi endpoint address | Consumer gọi URL cũ |
| Đổi binding/style/use | Wire format/interoperability đổi |
| Xóa port/service | Generated client/runtime lookup fail |
| Đổi Fault message | Consumer không nhận diện lỗi |
| Thêm policy assertion bắt buộc | Client thiếu capability bị reject |

### 5.1. Endpoint URL

Một số consumer lấy endpoint từ external config; một số dùng address WSDL để generate/deploy client. Inventory cả endpoint configuration và generated artifacts.

### 5.2. SOAPAction và WS-Addressing Action

SOAPAction HTTP header trong SOAP 1.1 và WS-Addressing Action là hai cơ chế khác nhau. Thay giá trị có thể làm dispatch fail dù Body hợp XSD.

### 5.3. SOAP Fault là contract

Consumer có thể dựa Fault code/detail để retry hoặc hiển thị lỗi. Đổi fault QName, detail structure, HTTP status hoặc retry semantics có thể breaking dù request/response XSD không đổi.

## 6. Runtime behavior và security policy cũng là contract

Các thay đổi cần change review:

- Operation chuyển synchronous sang asynchronous acceptance.
- Response đổi từ final result sang Accepted + status query.
- Timeout/retry policy đổi.
- Duplicate request behavior hoặc idempotency requirement đổi.
- Authorization scope đổi.
- WS-Security signature/encryption parts/action order đổi.
- TLS/mTLS requirements hoặc certificate trust đổi.
- UsernameToken type, Timestamp TTL hoặc security algorithms đổi.
- Rate limits, payload limits, concurrency hoặc availability windows đổi.

Security tightening có thể breaking: bắt buộc ký thêm WS-Addressing headers khiến client cũ bị reject. Vẫn phải có notice, test endpoint, migration instructions và thời gian phối hợp; nếu là incident khẩn cấp thì dùng emergency path có audit.

## 7. Consumer inventory

| Trường | Mục đích |
|---|---|
| Consumer ID/name | Ứng dụng/partner |
| Owner/team/contact | Người chịu trách nhiệm |
| Environment | Dev/test/staging/production |
| Contract version | WSDL/XSD/policy đang dùng |
| Endpoint/operations | URL, actions, operations |
| Client stack | Java/JAX-WS, .NET, ESB, manual |
| Generated artifact version | JAXB/client library version |
| Security profile | TLS, WS-Security, cert identity |
| Traffic/last seen | Tần suất và lần cuối hoạt động |
| Criticality | Impact khi ngừng |
| Migration status | Not contacted/testing/migrated |
| Evidence | Test result/release/sign-off |

### 7.1. Nguồn inventory

Kết hợp gateway logs/metrics, endpoint telemetry, verified WS-Security signer identity, service registry/config repos, WSDL distribution records, partner registers, batch calendars, incidents và consumer contract test registry.

Không thấy traffic trong bảy ngày không chứng minh retired: batch monthly/quarterly, disaster recovery và seasonal jobs có thể ít xuất hiện.

### 7.2. Consumer chưa nhận diện

Không tự suy không có consumer. Trong transition có thể bổ sung authenticated identity, client certificate mapping, API client registration hoặc gateway metadata.

### 7.3. Privacy

Chỉ lưu metadata cần cho lifecycle/audit. Không thu raw SOAP payload hoặc credentials để identify consumer; dùng verified identity, operation, timestamps, version và aggregate metrics.

## 8. Change classification và versioning decision

| Level | Đặc điểm | Ví dụ | Governance |
|---|---|---|---|
| Documentation-only | Không đổi wire contract/semantics | Sửa mô tả | Review nhẹ |
| Compatible additive | Thêm capability optional đã test | Optional response field | Compatibility suite/notice |
| Conditionally compatible | Phụ thuộc parser/config | Thêm enum | Affected client tests |
| Breaking | Client cũ có thể fail/semantics đổi | Namespace/type/required field | Version/migration plan |
| Security-critical | Cần thay đổi vì risk/compliance | Revoke cert/disable weak algorithm | Incident/emergency process |

Security-critical không được miễn governance. Có thể rút ngắn transition nhưng phải ghi reason, consumers, mitigation và decision owner.

### 8.1. Version ở đâu?

Có thể version tại XML namespace, WSDL service/port/binding, endpoint path, SOAP action/operation identity, client package hoặc security policy. Không cần tăng mọi version đồng thời; cần quy tắc nhận dạng contract mà hai bên kiểm tra/lưu được.

### 8.2. Namespace versioning

~~~text
urn:example:orders:v1
urn:example:orders:v2
~~~

Namespace mới tạo XML identity mới, hỗ trợ hai schema tồn tại song song. Nó không tự tạo compatibility; mapping, endpoint, policy, generated classes và business semantics vẫn cần quản lý.

### 8.3. Endpoint versioning

~~~text
/services/orders/v1
/services/orders/v2
~~~

Path riêng giúp chạy song song. Có thể dùng virtual host, port hoặc service deployments khác. Tránh dispatch dựa local name không namespace-qualified; dùng QName/binding đúng.

## 9. Consumer-driven contract tests

**Consumer-driven contract testing (CDC)** ghi nhận expectation thực tế của consumer, bổ sung cho provider-side schema validation và shared WSDL/XSD tests.

Consumer contract có thể ghi operation/action, request XML, response XML, QName/namespace, fields được dùng, Fault details, security headers/signatures, retry/idempotency expectations và business semantics.

### 9.1. Consumer expectation

~~~xml
<ord:GetOrderResponse xmlns:ord="urn:example:orders:v1">
  <ord:orderId>ORD-100</ord:orderId>
  <ord:status>PROCESSING</ord:status>
</ord:GetOrderResponse>
~~~

Consumer contract nên nói client phụ thuộc orderId/status, không giả định optional field khác phải hiện diện.

### 9.2. CDC không thay provider verification

CDC có thể bỏ sót unregistered consumers, WS-Security processing, load, network, parser differences và behavior chưa test. Kết hợp schema/WSDL, generated-client, security và runtime monitoring.

### 9.3. CDC không phải quyền veto

Provider vẫn có thể evolve service. CDC giúp nhận diện impact và thiết kế migration/versioning; không đóng băng mọi behavior hiện tại.

## 10. Provider compatibility gates trong CI

~~~mermaid
flowchart TD
    A["Pull request changes WSDL/XSD"] --> B["Normalize and diff artifacts"]
    B --> C["Classify breaking changes"]
    C --> D["Validate XSD/WSDL"]
    D --> E["Generate JAXB/client artifacts"]
    E --> F["Provider contract tests"]
    F --> G["Registered consumer contracts"]
    G --> H["SOAP/security interoperability tests"]
    H --> I{"Gate passed?"}
    I -->|"No"| J["Block release or approved exception"]
    I -->|"Yes"| K["Publish artifacts and change notice"]
~~~

### 10.1. Structural diff

So sánh normalized WSDL/XSD thay vì text diff. Prefix/formatting có thể đổi mà semantic không đổi. Tool cần resolve namespaces, imports/includes, WSDL references và schema dependencies.

### 10.2. JAXB generation gate

Generate classes với toolchain/version pin; build client fixtures để phát hiện Java type, enum, package, ObjectFactory và element declaration thay đổi.

### 10.3. Provider conformance gate

Test endpoint request/response/Fault, QName, SOAP version, action dispatch, headers và security policy.

### 10.4. Registered consumer gate

Chạy suites của consumer. Nếu test không chạy được, mark inconclusive, không coi pass; chỉ có exception owner/deadline mới được bypass có kiểm soát.

### 10.5. Fixture hygiene

Fixtures representative, không chứa production secrets, có positive/negative cases, version và owner. Consumer expectation changes phải được review.

## 11. Generated clients và compatibility traps

Consumer có thể dùng generated JAXB/JAX-WS DTOs/enums/ObjectFactory/JAXBElement; hand-written bindings; XPath/DOM/XSLT; shared libraries; ESB maps và custom SOAP headers/fault resolvers.

### 11.1. Regenerate không đồng nghĩa migration xong

Client generate thành công vẫn có thể gọi endpoint/action cũ hoặc serialize payload khác. Cần compile, wire tests, staging integration và rollout evidence.

### 11.2. Strict schema validation

Client validate response bằng XSD cũ có thể reject optional element mới, dù JAXB unmarshaller ở mode khác bỏ qua unknown element. Xác định parser behavior cụ thể.

### 11.3. Enum evolution

Thêm enum value mà không kiểm strict clients có thể làm unmarshal fail. Chỉ dùng unknown-value handler nếu contract và consumer đều hỗ trợ rõ.

### 11.4. absent, nil và default khác nhau

Element vắng mặt, element có xsi:nil=true và element có default/fixed value không luôn tương đương. JAXB/business logic có thể xử lý khác. Test từng trường hợp trước khi thay minOccurs/nillable/default.

## 12. Thông báo thay đổi contract

| Trường | Nội dung |
|---|---|
| Change ID | Mã duy nhất |
| Service/contract | Service, WSDL/XSD/policy version |
| Change summary | Điều gì đổi và vì sao |
| Classification | Compatible/conditional/breaking/security-critical |
| Affected components | Operations, elements, actions, faults, endpoints |
| Consumer impact | Client versions/partners bị ảnh hưởng |
| Required action | Update, regenerate, config, retest, certify |
| Artifacts | WSDL/XSD, release notes, migration guide |
| Test environment | Endpoint, test credentials/certs, schedule |
| Dates | Announcement, deprecation, end-of-support, sunset |
| Rollback | Cách duy trì/khôi phục |
| Owner/contact | Change owner và escalation |

### 12.1. Change notice mẫu

~~~text
Change: ORD-SOAP-2026-04
Service: Orders SOAP
New contract: Orders v2
Change type: Breaking
Affected operations: SubmitOrder, GetOrder
Required action: Regenerate/update client and run v2 certification tests
Test endpoint: https://test.example.invalid/services/orders/v2
Deprecation notice: 2026-12-01
Old contract end of support: 2027-03-01
Planned sunset: 2027-04-01
Owner: Orders Integration Team
~~~

URL/ngày trên là ví dụ, không phải lịch thật. Notice thực cần timezone, môi trường, contact và dates đã phê duyệt.

### 12.2. Nhiều kênh thông báo

Dùng integration portal, email groups, release notes, partner portal, support tickets và change board theo plan. Một email không đủ nếu owner list chưa xác thực hoặc notice không được acknowledge.

### 12.3. Consumer acknowledgement

Với breaking/security changes quan trọng, yêu cầu owner xác nhận đã nhận notice, người phụ trách và migration plan. Acknowledgement không chứng minh đã migrate; cần test/production evidence.

## 13. Deprecation timeline

~~~mermaid
gantt
    title SOAP contract migration lifecycle (illustrative)
    dateFormat YYYY-MM-DD
    section Provider
    Publish notice and v2 artifacts :a1, 2026-12-01, 14d
    Run parallel v1 and v2 :a2, 2026-12-15, 60d
    Review migration evidence :a3, 2027-02-01, 28d
    End v1 support :milestone, m1, 2027-03-01, 0d
    Sunset v1 :milestone, m2, 2027-04-01, 0d
    section Consumer
    Impact assessment :b1, 2026-12-01, 21d
    Client update and tests :b2, 2026-12-15, 45d
    Production migration :b3, 2027-02-01, 28d
~~~

Mốc minh họa, phải điều chỉnh theo business criticality, partner agreements, release cadence, batch windows, freeze periods và approvals.

### 13.1. Các mốc khác nhau

- Announcement date: publish notice.
- Deprecation effective date: component được đánh dấu deprecated.
- Migration deadline: mục tiêu consumer hoàn tất chuyển đổi.
- End-of-support date: dừng maintenance/support theo policy.
- Sunset date: dừng endpoint/operation/version cũ.

### 13.2. Chọn transition window

Cân nhắc criticality, số lượng/loại consumer, partner external, release cadence, certificate/security approvals, batch seasonality, contractual/regulatory notice periods và thời gian parallel testing/rollback.

### 13.3. Emergency security change

Nếu cert compromise hoặc algorithm không còn chấp nhận được, provider có thể phải revoke/remove sớm. Dùng emergency path có incident owner, risk rationale, affected consumers, mitigation, urgent notice và audit. Không dùng timeline bình thường để trì hoãn containment.

## 14. Versioning và parallel support

~~~text
Orders provider
  /services/orders/v1 -> schema v1 and behavior v1
  /services/orders/v2 -> schema v2 and behavior v2
~~~

### 14.1. Chia sẻ business core

Provider có thể map v1/v2 vào cùng domain service rồi map result theo contract. Nhưng giữ behavior semantics riêng nếu khác; không để v1 vô tình nhận semantics v2.

### 14.2. Parallel support cần nhiều hơn hai WSDL files

Cần endpoint/binding, JAXB/schema validation, Fault/security policies, contract tests, traffic attribution, monitoring/runbooks, support dates và rollback.

### 14.3. Version routing

Dùng endpoint path, namespace, WSDL port, deployment hoặc routing config. Dispatch phải dựa QName/binding rõ ràng.

### 14.4. Chống drift

Fix business core cần xác định v1/v2 có nhận fix không. Old version có thể giữ wire contract nhưng vẫn cần security/critical bug fixes theo support promise.

## 15. Consumer migration playbook

1. **Inventory/owner:** xác nhận app, team, contact, env, operation và contract version.
2. **Impact assessment:** đọc WSDL/XSD diff, migration guide, security policy.
3. **Regenerate/update:** pin codegen tools; review generated API diff.
4. **Adapt application:** sửa mapping, enum, optional/nil, SOAPAction, Fault, timeout, security.
5. **Contract tests:** xác minh QName, cardinality, Fault và behavior.
6. **Integration tests:** test endpoint, TLS/WS-Security, action, timeout, retry.
7. **Staging/certification:** partner/provider xác nhận compatibility.
8. **Production rollout:** canary/cohort, theo dõi errors/latency/version, có rollback.
9. **Evidence/closeout:** ghi build ID, test results, observation window, traffic drain và owner acknowledgement.

## 16. Theo dõi migration bằng telemetry

| Metric | Mục đích |
|---|---|
| SOAP request count by contract version | Mức dùng mỗi version |
| Requests by verified consumer identity | Consumer nào còn phụ thuộc |
| Operation count by version | Operation cũ còn hoạt động |
| Last-seen per consumer | Lần cuối thấy consumer |
| SOAP Fault rate by client/version | Regression |
| Schema validation failures | Payload incompatibility |
| WS-Security validation failures | Security policy mismatch |
| HTTP/SOAP latency/errors | Runtime health |
| v1/v2 traffic ratio | Tiến độ migration |
| Unknown consumer traffic | Dependency chưa định danh |

### 16.1. Consumer identity

Ưu tiên verified certificate identity, gateway client identity hoặc partner registration. IP/User-Agent đơn lẻ có thể đổi hoặc dùng chung.

### 16.2. Last seen không chứng minh retired

Consumer có batch tuần/tháng/quý, DR hoặc seasonal workloads. Phải xét chu kỳ business và observation window.

### 16.3. Traffic giảm chưa đủ để sunset

Kết hợp owner sign-off, deployment record, certification, traffic drain, support records và observation period. Nếu unknown traffic còn lại, điều tra hoặc có risk-approved exception.

## 17. Release gates

- Contract artifacts version/checksum rõ.
- XSD compile/schema validation pass.
- WSDL parse/resolve imports/includes.
- JAXB generation/build pass.
- Provider request/response/Fault tests pass.
- Registered consumer contract suites pass.
- SOAP 1.1/1.2 và Action dispatch tests theo binding.
- WS-Security/TLS/certificate tests nếu policy đổi.
- Negative tests cho Fault/security behavior.
- Performance/payload/timeout tests phù hợp.
- Deployment, monitoring, rollback và support owner sẵn sàng.

### 17.1. Gate theo change type

| Change type | Minimum gates |
|---|---|
| Documentation-only | Review, artifact consistency |
| Compatible additive | Schema/WSDL, representative consumer tests |
| Conditional | Inventory, strict parser/codegen tests |
| Breaking | Versioning/parallel support, migration evidence, rollback |
| Security-critical | Security review, interoperability, emergency communications |

Không hạ breaking change xuống compatible chỉ vì internal happy-path pass.

## 18. Rollout và rollback

### 18.1. Canary theo consumer cohort

Triển khai v2 cho consumer nội bộ/partner thử nghiệm. Đo schema errors, security failures, Faults, latency và business outcomes trước khi tăng cohort.

### 18.2. Dual-run không tạo side effect hai lần

Không gửi hai lệnh SubmitOrder/ChargePayment để so sánh nếu gây side effect. Shadow bằng read-only operations, isolated test tenant, synthetic fixtures hoặc replay đã sanitize.

### 18.3. Rollback không chỉ đổi WSDL

Consumer có thể đã chuyển sang semantics v2. Kiểm tra compatibility matrix old/new provider với old/new clients.

### 18.4. Forward fix hay rollback

Nếu v2 đã ghi dữ liệu hoặc phát event schema mới, binary v1 có thể không đọc được. Cần dual-read, migration, forward fix hoặc routing riêng. Đánh giá data compatibility trước deploy.

## 19. Điều kiện sunset contract cũ

1. Mỗi critical consumer có owner và migration disposition.
2. Consumer cần hỗ trợ đã certification.
3. Production traffic đã chuyển sang version mới.
4. Không còn v1 traffic trong observation window hoặc exception owner đã phê duyệt.
5. Batch/seasonal workloads đã qua chu kỳ kiểm tra.
6. Fault/error metrics ổn định, không còn incident migration mở.
7. Partner approvals/contractual notice đạt yêu cầu.
8. Rollback/traffic routing plan xác nhận.
9. Support/security/product owners phê duyệt.
10. Final notice và support contacts đã gửi.

### 19.1. Critical consumer không phản hồi

Silence không phải consent. Escalate, tìm business owner và đánh giá impact. Có thể giữ exception tạm thời hoặc giới hạn traffic theo risk decision, phải có decision owner và expiry.

### 19.2. Không có traffic nhưng vẫn có declaration

Xác minh scheduler/DR/contingency deployment và artifact references với owner. Không dựa duy nhất dashboard.

### 19.3. Sunset decision record

Ghi version/endpoint, last seen, consumers, exceptions, tests, approvals, shutdown time, rollback path và post-sunset monitoring.

## 20. Quản lý WSDL/XSD artifacts và generated packages

~~~text
contracts/
  orders/
    v1/
      orders.wsdl
      schemas/orders.xsd
      policy/ws-security-policy.xml
      examples/
    v2/
      orders.wsdl
      schemas/orders.xsd
      policy/ws-security-policy.xml
      examples/
~~~

Đây là convention minh họa. Artifacts cần immutable theo release version/checksum.

### 20.1. Pin code generation toolchain

Lưu plugin, JDK, JAXB runtime, binding files và catalog versions. Không generate production client từ mutable WSDL URL mà không lưu artifact identity.

### 20.2. WSDL import/include closure

Nếu imported XSD đổi, contract đã đổi dù root WSDL không đổi. Release phải capture toàn bộ dependency closure và tránh imports trỏ mutable/unversioned URLs.

### 20.3. XML catalog và external resolution

Dùng XML catalog/offline resolution để build tái lập. Hạn chế external schema tải không kiểm soát và bảo vệ parser XML.

## 21. Case study: thêm trường bắt buộc vào SubmitOrder

Contract v1:

~~~xml
<xs:element name="SubmitOrderRequest">
  <xs:complexType>
    <xs:sequence>
      <xs:element name="orderId" type="xs:string"/>
      <xs:element name="customerId" type="xs:string"/>
    </xs:sequence>
  </xs:complexType>
</xs:element>
~~~

Provider muốn thêm salesChannel bắt buộc để audit.

### 21.1. Vì sao sửa trực tiếp v1 là rủi ro?

Client generate từ schema cũ không gửi salesChannel. Provider mới bật validation và reject request. Đây là breaking change.

### 21.2. Hướng thiết kế

- **Option A — Optional trước:** thêm salesChannel với minOccurs 0, định nghĩa behavior khi vắng, provider đọc cả request cũ/mới. Sau migration có thể đưa required field vào v2.
- **Option B — v2:** namespace/WSDL v2 có required field; chạy v1/v2 song song.
- **Option C — Server-side derivation:** nếu xác định salesChannel từ verified caller identity/routing thì derive tại server, với mapping minh bạch và đáng tin.

### 21.3. Test

- v1 request thiếu salesChannel vẫn chạy trên v1.
- v2 request có field hợp lệ chạy trên v2.
- v2 request thiếu field bị reject theo Fault/schema contract.
- v1 endpoint không dispatch nhầm sang v2.
- Generated clients của stack hỗ trợ compile và wire-test.
- Caller không thể giả mạo salesChannel ngoài quyền.

## 22. Partner change notice mẫu

~~~text
Subject: Planned migration — Orders SOAP contract v1 to v2
Change ID: ORD-SOAP-2026-04
Reason: Add required salesChannel and align payment status semantics.
Affected: Orders WSDL/XSD v1, SubmitOrder and GetOrder
Classification: Breaking
Artifacts: Orders v2 WSDL/XSD, WS-Security policy, examples, migration guide
Required actions: Regenerate client, update mapping, run certification tests, deploy v2
Announcement: 2026-12-01
Deprecation: 2026-12-15
End of support v1: 2027-03-01
Planned sunset v1: 2027-04-01
Test environment: Separate partner endpoint and credentials
Support: Named integration owner and escalation channel
Rollback: Continue v1 routing during approved transition
~~~

Mẫu giả định; notice thật cần contact, endpoint, timezone và dates đã phê duyệt.

## 23. Lỗi quản trị thường gặp

| Anti-pattern | Hậu quả | Phòng tránh |
|---|---|---|
| Sửa XSD public trực tiếp | Consumer fail bất ngờ | Version, diff gate, notice |
| Chỉ test client mới | Bỏ sót client cũ | Inventory/CDC |
| Thêm enum không test | JAXB/client parse fail | Strict client tests |
| Coi optional luôn compatible | Strict validators reject | Test parser modes |
| Đổi SOAPAction im lặng | Dispatch fail | Action regression tests |
| Bỏ Fault details | Retry/handling sai | Fault contract tests |
| Chỉ gửi email, không theo dõi ack | Owner không biết | Change register/evidence |
| Coi last-seen 0 là retired | Bỏ quên batch/DR | Seasonal/owner checks |
| Sunset còn critical consumer | Incident/breach | Exit criteria/exceptions |
| Dual-run side-effect calls | Duplicate charge/order | Shadow read-only/isolated data |
| Rollback không xét data v2 | New data không đọc được | Compatibility matrix |
| WSDL URL mutable | Build không reproducible | Immutable artifacts |

## 24. Bài thực hành: quản trị breaking SOAP change

Bối cảnh: Orders SOAP v1 có SubmitOrder/GetOrder. Provider muốn thêm required salesChannel, đổi status semantics sang Accepted/Completed, yêu cầu ký WS-Addressing Action và chuyển endpoint v2.

### Nhiệm vụ

1. Thu thập WSDL/XSD/policy v1 và lưu artifact version/checksum.
2. Tạo structural diff schema, WSDL, actions, faults và security policy.
3. Phân loại compatible/conditional/breaking/security-critical.
4. Lập consumer inventory có owner, stack, environment, traffic, criticality.
5. Thiết kế v2 namespace/endpoint và parallel support.
6. Định nghĩa request/response/Fault semantics trong v2.
7. Viết CDC expectations cho consumers.
8. Tạo JAXB generation/compile gates.
9. Tạo provider tests cho SOAP version, QName, Action và Fault.
10. Tạo WS-Security negative tests cho client thiếu signed Action.
11. Soạn notice có actions, artifacts, dates, owner.
12. Publish test endpoint và migration guide.
13. Certification/staging cho cohort đầu.
14. Canary rollout và theo dõi errors/traffic theo consumer.
15. Mô phỏng rollback khi v2 gặp schema/security issue.
16. Đặt riêng deprecation/end-of-support/sunset.
17. Xác định exit criteria xét traffic, owner evidence và seasonal jobs.
18. Tạo exception path cho critical consumers.
19. Ghi decision record cho sunset.
20. Kiểm post-sunset monitoring/runbook.

**Tiêu chí đạt:** Consumer critical được định danh; v1/v2 có compatibility tests; migration evidence audit được; sunset chỉ sau exit criteria được phê duyệt.

### 24.1. Tình huống

**A:** Dashboard không thấy v1 traffic 10 ngày, nhưng partner chạy batch ngày cuối tháng. Có thể sunset không? Cần evidence gì?

**B:** Thêm optional response element khiến JAXB client mới chạy nhưng strict XSD client cũ reject. Phân loại và xử lý thế nào?

**C:** Provider bắt buộc ký WS-Addressing Action vì security finding; một số client chưa hỗ trợ. Khi nào dùng emergency path?

**D:** Provider v2 đã ghi data mới; rollback binary v1 có an toàn không? Cần kiểm data compatibility gì?

## 25. Checklist trước khi thông báo và sunset

- [ ] Change request có owner, reason, scope.
- [ ] WSDL/XSD imports/includes/policies được diff đầy đủ.
- [ ] Compatibility classification có rationale.
- [ ] Runtime semantics, Action, Fault, auth và timeout được review.
- [ ] Consumer inventory có owner, version, operations và criticality.
- [ ] Consumer identity được xác minh đáng tin.
- [ ] Artifacts có version/checksum và codegen toolchain pin.
- [ ] CDC/provider suites đã đăng ký và chạy.
- [ ] Change notice có actions, artifacts, test environment, contacts.
- [ ] Announcement/deprecation/end-of-support/sunset phân biệt.
- [ ] Parallel endpoints/policies đã test.
- [ ] Migration có certification và production evidence.
- [ ] Traffic observation xét batch/seasonal/DR.
- [ ] Canary, rollback, data compatibility và runbooks sẵn sàng.
- [ ] Exceptions có owner, risk acceptance, expiry.
- [ ] Sunset exit criteria có sign-off/audit.

## 26. Ghi nhớ

- WSDL/XSD là contract provider-consumer; thay đổi phải xét **wire format và business semantics**.
- Optional response element vẫn có thể phá strict validators; enum mới có thể phá generated clients.
- SOAPAction, WS-Addressing Action, SOAP version, Fault và WS-Security policy thuộc compatibility review.
- Không có consumer inventory thì không có cơ sở chắc chắn để sunset.
- Deprecation, end-of-support và sunset là các mốc riêng.
- CDC/provider gates cần chạy cùng schema, codegen, security và integration tests.
- Migration cần owner, test evidence và production observation.
- Parallel support gồm endpoints, policies, faults, monitoring và rollback.
- Traffic không thấy trong khoảng ngắn không chứng minh client retired.
- Sunset sau exit criteria, critical consumer sign-off và exception review.

**Câu hỏi tự kiểm tra:** Provider thêm required element vào XSD v1, đổi SOAPAction và yêu cầu ký WS-Addressing Action. Dashboard không thấy v1 traffic trong 10 ngày nhưng inventory có partner chạy batch hàng tháng. Hãy phân loại changes, giải thích breaking risks, lập notice/timeline, xác định consumer tests/evidence và đề xuất exit criteria trước sunset v1.

## 27. Tài liệu tham khảo để đối chiếu

- W3C XML Schema 1.0/1.1: element/type/occurrence/facets và schema composition.
- W3C WSDL 1.1 Note và SOAP 1.1/1.2 specifications: service, binding, operation và message exchange.
- Spring Web Services Reference: WSDL publishing, endpoint mappings, client/server testing và SOAP transports.
- Jakarta XML Binding (JAXB) specification/API: XML-to-Java mapping, schema generation và binding behavior.
- Consumer-driven contract testing documentation và provider-specific compatibility tooling.
- Organization change-management, partner SLA và certificate/security policies.

Tool defaults và behavior có thể khác theo JDK, JAXB, Spring-WS và SOAP stack. Pin toolchain, capture toàn bộ WSDL/XSD imports, và kiểm chứng bằng client thực tế của các consumer được hỗ trợ.

