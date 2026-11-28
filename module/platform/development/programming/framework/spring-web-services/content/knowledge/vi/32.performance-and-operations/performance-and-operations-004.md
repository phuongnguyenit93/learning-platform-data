# Chi phí validation, biến đổi XSLT, ký và mã hóa

## 1. Vì sao XML security pipeline có thể trở thành nút thắt?

Trong module **SPRING_WEB_SERVICES**, ứng dụng SOAP theo hướng contract-first dùng XSD/WSDL để định nghĩa hợp đồng, JAXB/OXM để ánh xạ XML–Java, Spring-WS để xử lý endpoint và client. Với hệ thống doanh nghiệp, SOAP message còn có thể đi qua XML Schema validation, XSLT transformation, XML Signature và XML Encryption trước khi tới nghiệp vụ hoặc được gửi sang partner.

Mỗi bước có mục đích riêng nhưng đều có chi phí. Validation phải đọc cấu trúc và kiểm tra facets, cardinality, types, imports; XSLT parse source, xây execution context, evaluate template và serialize kết quả; ký XML phải xác định references, canonicalize các nodes rồi tính digest/signature; mã hóa phải canonicalize hoặc serialize phần tử được chọn, thực hiện cryptographic operation và cập nhật XML structure.

Chi phí không chỉ là thời gian CPU. Pipeline có thể tạo nhiều DOM nodes, byte arrays, intermediate strings, namespace maps và cryptographic objects. Khi payload lớn hoặc concurrency tăng, allocation/GC, lock contention và connection wait có thể làm latency tăng nhanh hơn tỷ lệ tải.

Bài tập trung vào bốn công đoạn và cách đo/tối ưu có kiểm soát:

- **Validation:** xác minh request/response theo XSD.
- **XSLT transformation:** chuyển đổi XML giữa contract hoặc partner formats.
- **XML Signature:** bảo đảm integrity và signer authenticity theo trust policy.
- **XML Encryption:** bảo vệ confidentiality cho elements/content được chọn.

Tối ưu phải giữ nguyên kết quả contract và security properties. Không bỏ validation, giảm signed parts, đổi thuật toán yếu hoặc bỏ encryption chỉ để làm benchmark đẹp hơn.

### Mục tiêu học tập

1. Giải thích chi phí CPU, allocation và latency của validation, XSLT, signature và encryption.
2. Phân biệt cold-start cost với steady-state cost.
3. Đo từng stage và toàn pipeline bằng benchmark có dữ liệu thực tế.
4. Hiểu DOM, streaming, canonicalization và serialization ảnh hưởng hiệu năng.
5. Tái sử dụng schema/stylesheet/crypto configuration một cách thread-safe.
6. Tối ưu XML processing mà không làm thay đổi semantics.
7. Đánh giá thuật toán, key size và provider theo security policy.
8. Kiểm soát payload size, concurrency, queueing, timeout và memory.
9. Xây performance regression tests và capacity model.
10. Xác minh tối ưu không làm giảm security/interoperability.

## 2. XML pipeline và các nguồn chi phí

Một request có thể đi qua pipeline:

~~~mermaid
flowchart LR
    A["SOAP bytes"] --> B["Parse XML"]
    B --> C["XSD validation"]
    C --> D["XSLT transform"]
    D --> E["Canonicalize selected nodes"]
    E --> F["XML Signature"]
    F --> G["XML Encryption"]
    G --> H["JAXB / endpoint"]
    H --> I["SOAP response"]
~~~

Đây là một pipeline minh họa; thứ tự ký/mã hóa và vị trí validation phụ thuộc message flow, policy và security processing order. Không phải service nào cũng chạy cả bốn stages trên cùng một direction.

| Stage | Công việc | Cost drivers thường gặp |
|---|---|---|
| XML parse | Tokenize XML, namespace, attributes, tree construction | Payload bytes, nesting, node count, parser features |
| XSD validation | Resolve declarations/types, check order/facets/identity constraints | Schema graph, XPath-like constraints, document size |
| XSLT | Parse stylesheet/source, compile/evaluate templates | Template complexity, XPath evaluation, sorting, key lookups |
| Canonicalization | Normalize namespace/attributes/nodes theo algorithm | Selected subtree size, namespace context, node traversal |
| Signature | Digest references và sign SignedInfo | Signed bytes, number of references, key/provider |
| Encryption | Generate key/IV, encrypt content/key transport | Plaintext size, cipher/provider, recipient key operations |
| Serialization | Produce output XML/bytes | Output size, encoding, namespace declarations |
| Network | Send/receive | RTT, throughput, TLS, connection reuse |

### 2.1. Phân biệt latency và throughput

Latency là thời gian một request hoàn tất; throughput là số requests xử lý mỗi giây. Tăng worker threads có thể tăng throughput đến giới hạn CPU/IO nhưng cũng có thể làm p95/p99 latency xấu đi vì contention và GC.

### 2.2. Chi phí cố định và chi phí theo payload

Một số chi phí gần fixed per request: tạo context, lookup policy, load configuration nếu làm sai cách. Các bước parse, canonicalization, digest và encryption thường tăng theo lượng dữ liệu/selected nodes. XSLT phụ thuộc cấu trúc và complexity của stylesheet chứ không chỉ byte size.

### 2.3. Chi phí của nhiều passes

Một message có thể bị parse nhiều lần: một lần cho schema validation, một lần cho transform, rồi security engine dựng DOM và canonicalize lần nữa. Có thể tối ưu bằng reuse object/context ở nơi API cho phép, nhưng không được bỏ bước kiểm tra độc lập hoặc dùng mutated tree sai thứ tự.

## 3. Validation: chi phí và điểm tối ưu

XSD validation kiểm document có phù hợp schema declarations, type constraints, sequence, occurrence, facets và identity constraints hay không.

Chi phí validation bị ảnh hưởng bởi:

- Kích thước XML và số lượng elements/attributes.
- Độ sâu và độ rộng của document tree.
- Số lượng schema imports/includes.
- Complex types, choices, substitutions và wildcards.
- Patterns, facets, keys/keyrefs/unique constraints.
- Parser implementation và việc có parse/validate lặp hay không.

### 3.1. Schema compilation khác validation từng document

Schema compilation/resolution là chi phí setup; validate mỗi request là chi phí runtime. Nếu mỗi request compile lại XSD, service trả thêm chi phí lớn và phụ thuộc filesystem/network. Compile schema một lần khi startup hoặc cache một immutable Schema object theo lifecycle phù hợp.

### 3.2. Không tải XSD qua network trên mỗi request

WSDL/XSD imports cần được resolve có kiểm soát lúc build/startup. Dùng classpath resources, local catalog hoặc resolver có allowlist. Không để mỗi SOAP request gọi internet tải schema; vừa tăng latency, vừa tạo availability/SSRF risk.

### 3.3. Reuse Schema, tạo Validator phù hợp

Trong Java XML Validation API, Schema thường là object dùng lại được; Validator là object cho một lần validation và không nên chia sẻ đồng thời nếu API/provider không cam kết thread-safe. Pattern an toàn thường là cache Schema bất biến rồi tạo Validator riêng cho mỗi operation/request.

~~~java
public final class OrderSchemaValidator {
    private final Schema schema;

    public OrderSchemaValidator(Schema schema) {
        this.schema = schema;
    }

    public void validate(Source source) throws SAXException, IOException {
        Validator validator = schema.newValidator();
        validator.validate(source);
    }
}
~~~

Đây là skeleton. Việc khởi tạo Schema, secure processing, resource resolver và error handler phải được cấu hình ở nơi tạo object. Không cache một Validator mutable rồi dùng concurrent mà không có bảo đảm từ provider.

### 3.4. Validation chỉ một lần hay nhiều lần?

Nếu trust boundary yêu cầu server validate inbound message, không được bỏ validation vì gateway đã validate trừ khi architecture/security contract xác định rõ gateway là enforcing boundary và payload không thể bị thay đổi sau đó. Tránh validate lặp vô ích trong cùng trust boundary nhưng không đánh đổi defense-in-depth không có bằng chứng.

### 3.5. Fail-fast và diagnostic cost

Dừng ở lỗi đầu tiên thường rẻ hơn thu thập mọi lỗi, nhưng developer diagnostics có thể cần nhiều validation events. Production nên trả lỗi giới hạn, không echo toàn XML hoặc tạo hàng nghìn error objects từ payload độc hại.

## 4. XSLT: chi phí compile và transform

XSLT thường gồm hai hoạt động:

1. Parse và compile stylesheet thành executable/template representation.
2. Transform từng source document bằng compiled templates.

Compile stylesheet theo từng request có thể phí CPU và allocation. Cache compiled Templates theo stylesheet identity/version và runtime configuration; tạo Transformer riêng cho mỗi lần chạy nếu API quy định Transformer mutable.

~~~java
public final class OrderTransformer {
    private final Templates templates;

    public OrderTransformer(Source stylesheet) throws TransformerConfigurationException {
        TransformerFactory factory = TransformerFactory.newInstance();
        this.templates = factory.newTemplates(stylesheet);
    }

    public void transform(Source input, Result output)
            throws TransformerException {
        Transformer transformer = templates.newTransformer();
        transformer.transform(input, output);
    }
}
~~~

Đây là pattern khái niệm theo JAXP. Cần cấu hình TransformerFactory secure processing, URIResolver, accessExternalDTD/accessExternalStylesheet theo policy và test với implementation thực tế.

### 4.1. Stylesheet complexity

Các yếu tố làm transform tốn kém:

- XPath expressions phải duyệt nhiều nodes.
- Nested template calls hoặc recursion sâu.
- Sorting với tập nodes lớn.
- Keys/indexes và lookup lặp.
- Tạo intermediate result tree.
- Extension functions hoặc external document calls.
- XSLT version features và implementation-specific optimizer.

### 4.2. Tránh document() ngoài allowlist

Stylesheet dùng document() hoặc URI resolution có thể truy cập tài nguyên ngoài. Điều này vừa thêm network/filesystem latency vừa tạo security risk. Chặn external access mặc định; chỉ cho phép URI được phê duyệt qua URIResolver.

### 4.3. Giảm transformation passes

Nếu có thể, hợp nhất mapping đơn giản vào một stylesheet hoặc map trực tiếp JAXB/domain model. Nhưng không tạo stylesheet khổng lồ khó kiểm thử và không trộn security-sensitive canonical XML transformations vào mapping tùy tiện.

### 4.4. XSLT streaming

Một số XSLT processors hỗ trợ streaming với điều kiện/version-specific. Streaming có thể giảm memory cho document lớn nhưng giới hạn phép XPath/navigation và stylesheet design. Đo compatibility và semantics của processor trước khi chọn.

## 5. XML Signature: canonicalization và digest là phần đáng kể

XML Signature không ký raw source text tùy ý. Reference transforms có thể chọn node-set, áp dụng transforms và canonicalization, sau đó tính digest; SignedInfo cũng được canonicalize trước khi ký.

Các cost drivers:

- Số lượng references.
- Kích thước và độ phức tạp của mỗi referenced subtree.
- Canonicalization algorithm.
- Enveloped-signature, XPath hoặc transforms khác.
- Digest algorithm.
- Signature key type/size và crypto provider.
- XML parser/DOM allocation và ID resolution.

### 5.1. Canonicalization

Canonicalization tạo biểu diễn XML chuẩn hóa để hai bên có thể tính cùng digest dù có những khác biệt serialization không mang ý nghĩa. Việc duyệt nodes, namespace declarations, attributes và text có thể tốn thời gian theo kích thước subtree.

### 5.2. Ký đúng parts, không ký ít hơn để tăng tốc

Security policy có thể yêu cầu ký SOAP Body, Timestamp, WS-Addressing Action, To hoặc các headers khác. Không bỏ SignedInfo references chỉ để giảm CPU. Thay đổi signed parts là thay đổi security contract và cần threat review/interoperability certification.

### 5.3. Tránh ký lại cùng message nhiều lần

Nếu một message bị ký ở nhiều interceptor/layer, CPU tăng và signature IDs/headers có thể duplicate. Xác định rõ component nào chịu trách nhiệm outbound signing; kiểm interceptor chain và final message.

### 5.4. Key loading và provider setup

Không đọc keystore, parse certificate chain hoặc tạo cryptographic configuration phức tạp trên mỗi request nếu có thể tạo/caching immutable configuration lúc startup. Tuy nhiên key rotation và certificate validity phải được quản lý; cache không được giữ private key đã bị revoke hoặc dùng quá thời gian policy.

## 6. XML Encryption: chi phí phụ thuộc payload và recipients

XML Encryption có thể mã hóa element/content bằng symmetric data encryption key, sau đó mã hóa key bằng recipient public key hoặc key agreement mechanism theo profile. Chi phí bao gồm:

- Serialize/canonicalize selected XML content.
- Symmetric encryption theo số byte.
- Generate IV/nonce theo algorithm.
- Key wrapping/transport cho mỗi recipient.
- Parse và decrypt ở receiver.
- Reconstruct XML tree và namespace context.

### 6.1. Symmetric và asymmetric costs

Symmetric encryption thường phù hợp xử lý payload lớn; asymmetric cryptography thường dùng bảo vệ/trao đổi data key. Không mã hóa cả XML payload trực tiếp bằng RSA-style operation. Thực hiện đúng profile XML Encryption và WS-Security policy của hai bên.

### 6.2. Nhiều recipients

Nếu cùng một encrypted data key cần được bảo vệ cho nhiều recipients, có thể phát sinh thêm key wrapping operations và EncryptedKey structures. Đo theo số recipients; đừng assume chi phí chỉ phụ thuộc payload bytes.

### 6.3. Chọn phần tử cần mã hóa

Chỉ encrypt parts theo confidentiality policy; không encrypt mọi header/body indiscriminately vì tăng payload/CPU và có thể làm routing/monitoring không hoạt động. Ngược lại, không bỏ encryption cho data nhạy cảm. Policy phải chỉ rõ phần nào được mã hóa và phần nào phải để router đọc.

### 6.4. Signature/encryption order

Sign-then-encrypt và encrypt-then-sign có semantics khác nhau về những phần intermediary có thể đọc và phần nào được xác minh. Thứ tự actions phải thống nhất giữa client/server policy; không tự đảo thứ tự để benchmark.

## 7. DOM, SAX, StAX và memory pressure

DOM giữ document tree trong memory, thuận tiện cho XPath, XSLT và XML Signature APIs nhưng có thể cần nhiều heap hơn kích thước wire XML do object overhead. SAX/StAX xử lý theo event/stream, có thể giảm memory nhưng không phải mọi transform/signature workflow đều hỗ trợ streaming trực tiếp.

| Model | Điểm mạnh | Giới hạn |
|---|---|---|
| DOM | Random access, namespace/node navigation, dễ tích hợp nhiều XML security APIs | Memory/allocation cao cho document lớn |
| SAX | Event-driven, ít giữ tree | Stateful, khó quay lại node trước |
| StAX | Pull parsing, có thể pipeline stream | API consumers phải xử lý forward-only |
| Streaming XSLT | Có thể giảm intermediate tree | Phụ thuộc processor/version và stylesheet constraints |

### 7.1. Không chọn streaming chỉ vì benchmark micro

Nếu signature library vẫn dựng DOM đầy đủ sau khi StAX parse, memory saving có thể không còn. Benchmark end-to-end trên đúng message security policy và SOAP stack.

### 7.2. Giới hạn payload và nesting

Đặt giới hạn cho request bytes, depth, node count, attributes, text length, attachment size và transform execution time. Đây là bảo vệ availability đồng thời làm cost có upper bound.

### 7.3. Avoid multiple materializations

Không chuyển DOM sang String, String sang byte[], rồi parse lại DOM nếu không cần. Mỗi materialization tạo allocation/copy và có thể làm tăng peak heap. Dùng Source/Result hoặc streaming API phù hợp, giữ encoding rõ ràng.

## 8. Chi phí kết hợp: không thể cộng đơn giản từng stage

Nếu validation, XSLT, signature và encryption chạy tuần tự, latency tổng là tổng stage times cộng queue/network/other work. Nhưng khi nhiều requests chạy đồng thời, GC, CPU saturation và lock contention có thể khiến mỗi stage chậm hơn so với benchmark đơn lẻ.

Ví dụ minh họa:

| Stage | p50 time (ms) | p95 time (ms) |
|---|---:|---:|
| Parse + XSD validation | 3 | 8 |
| XSLT | 2 | 6 |
| Signature | 5 | 15 |
| Encryption | 2 | 5 |
| Serialization/transport overhead | 3 | 9 |
| Tổng không đồng thời xấp xỉ | 15 | Không thể cộng p95 độc lập thành p95 tổng |

Bảng không phải số đo thực tế. p95 của tổng request phải đo trên transaction boundary; tổng p95 các stages không nhất thiết bằng p95 tổng do phân phối và tương quan latency.

### 8.1. Bottleneck dịch chuyển

Sau khi cache Templates, XSLT có thể rẻ hơn và signature trở thành bottleneck. Sau khi tối ưu signature, GC do DOM allocation có thể thống trị. Profile lại sau mỗi thay đổi; không tối ưu stage đã không còn chiếm đáng kể thời gian.

### 8.2. Amdahl's law

Tối ưu một stage nhỏ chỉ cải thiện tổng latency giới hạn theo tỷ trọng stage đó. Nếu signature chiếm 50% CPU, giảm 20% cost của signature không làm toàn request nhanh hơn 20%; tổng effect nhỏ hơn.

## 9. Benchmark đúng cách

Benchmark phải đại diện workload và security policy production. Tránh đo một XML bé, chỉ chạy một thread rồi suy ra throughput production.

### 9.1. Tách benchmark theo câu hỏi

- Microbenchmark từng stage để hiểu CPU/allocation.
- Component benchmark với Spring-WS/JAXB/WSS4J thật.
- End-to-end load test qua transport, proxy, TLS và partner simulator.
- Soak test đủ dài để phát hiện memory/GC/cache growth.

### 9.2. Warm-up và JIT

JVM có class loading, JIT compilation, provider initialization và cache population. Bỏ warm-up có thể khiến kết quả cold-start bị lẫn với steady-state. Đo cold startup riêng nếu latency sau restart là yêu cầu.

### 9.3. Payload corpus

Chuẩn bị nhiều payload: nhỏ/trung bình/lớn, nesting sâu vừa phải, số references khác nhau, optional fields, namespace complexity, XSLT branches và encrypted recipient counts. Dùng synthetic data có distribution gần thực tế.

### 9.4. Concurrency levels

Đo 1, 2, 4, 8… workers hoặc mức phù hợp deployment, đồng thời ghi CPU, heap, GC, queue depth và connection pool wait. Tăng concurrency đến khi throughput plateau hoặc tail latency/error rate vượt SLO.

### 9.5. Tránh dead-code benchmark

Đảm bảo output của transform/signature/encryption được tiêu thụ/verify trong benchmark. Nếu kết quả không được quan sát, harness hoặc JIT có thể làm phép đo không đại diện.

## 10. Metrics cần thu thập

| Metric | Dùng để phân tích |
|---|---|
| End-to-end latency p50/p95/p99 | User-visible performance |
| Per-stage duration | Xác định bottleneck |
| CPU time/utilization | Compute saturation |
| Allocation rate | Temporary object pressure |
| Heap after GC | Retained memory |
| GC pause/frequency | Tail latency và throughput |
| Document bytes/node count | Workload complexity |
| XSLT compile/cache hit | Setup overhead |
| Schema compile/cache hit | Validation setup cost |
| Signature references/time | Crypto/XML transform cost |
| Encryption bytes/recipients/time | Payload/key wrapping cost |
| Queue wait and thread utilization | Concurrency pressure |
| Timeout/fault rate | Reliability |

### 10.1. Instrument stages

Dùng timer/metrics wrapper quanh từng stage; giữ labels cardinality thấp như operation, contract version, security profile. Không dùng raw customer ID/order ID/certificate serial làm metric labels.

### 10.2. Correlation

Gắn correlation/trace ID vào logs/spans theo policy, nhưng không ghi raw XML hoặc security tokens. Trace cần thể hiện stage boundaries để nhận diện request chậm nằm ở parser, transform, crypto, network hay partner.

### 10.3. Percentiles

Average latency có thể tốt trong khi một nhóm payload lớn làm p99 xấu. Theo dõi percentiles và phân nhóm theo payload-size bucket/security profile mà không làm lộ dữ liệu.

## 11. Caching: lợi ích và ranh giới an toàn

Các đối tượng thường đáng cache:

- Immutable compiled Schema.
- Compiled XSLT Templates.
- Parsed trust anchors/certificate metadata.
- Crypto/provider configuration không chứa mutable request state.
- WSDL/XSD artifacts có version/checksum.

Không cache indiscriminately:

- Validator/Transformer mutable nếu không thread-safe.
- Per-request DOM/message.
- Authorization decisions không xét context/expiry.
- Revocation status hoặc certificate trust vượt freshness policy.
- Secrets/private key state sau rotation/revocation mà không có invalidation.

### 11.1. Cache key cần bao hàm version

Schema/stylesheet cache key phải phản ánh URI/version/checksum/resolver configuration và relevant processor settings. Không chỉ cache bằng filename nếu cùng tên có schema khác ở environments.

### 11.2. Cache invalidation và rotation

Khi deploy contract mới hoặc rotate trust/certificates, reload configuration theo quy trình xác định. Cần test cache eviction/refresh, không để node cũ tiếp tục dùng policy đã retire.

### 11.3. Thread safety

Schema/compiled Templates thường được thiết kế để tạo execution object riêng; Validator/Transformer thường mutable theo từng lần dùng. Đọc API/provider contract trước khi chia sẻ. Nếu không chắc, dùng instance per operation hoặc pool có giới hạn.

## 12. Crypto algorithm và hardware/provider

Signature/encryption time phụ thuộc thuật toán, key type/size, provider implementation, hardware acceleration và input size. Benchmark phải dùng algorithms được security policy cho phép.

### 12.1. Không downgrade thuật toán vì hiệu năng

Nếu RSA signature chậm hơn một lựa chọn khác, không tự đổi digest/signature algorithm sang yếu hoặc deprecated. Review algorithm suite, interoperability với partner và organization security policy trước thay đổi.

### 12.2. Provider initialization

Một số crypto providers tải native libraries, entropy hoặc initialize key stores. Đo startup và steady-state riêng. Tránh tạo Provider/configuration mới mỗi request nếu không cần.

### 12.3. Hardware acceleration

HSM hoặc hardware-backed key có thể tăng security và thay đổi latency/throughput; signing calls có thể bị giới hạn bởi remote HSM throughput hoặc session pool. Đo queueing, HSM latency và failure behavior; không chỉ đo CPU JVM.

### 12.4. Key size và operation count

RSA signing cost thường khác RSA verify; encryption key wrapping và symmetric bulk encryption cũng khác. Đo đúng operation direction (client sign/server verify; server encrypt/client decrypt) thay vì chỉ một crypto primitive.

## 13. XSLT optimization an toàn

Một số hướng tối ưu:

1. Compile stylesheet một lần, tạo Transformer riêng cho mỗi request.
2. Tránh XPath expressions lặp quét document; dùng xsl:key khi phù hợp.
3. Hạn chế sorting/recursive templates trên tập dữ liệu lớn.
4. Loại bỏ intermediate tree không cần thiết.
5. Chặn external document access, dùng URIResolver allowlisted.
6. Dùng streaming chỉ khi processor và stylesheet support đúng semantics.
7. Version hóa stylesheet và benchmark trước/sau bằng corpus cố định.

### 13.1. Không đổi business mapping

Một stylesheet có thể có behavior về whitespace, namespace, default values, ordering và date formats. Output nhỏ hơn hoặc nhanh hơn không chứng minh tương đương. So sánh XML theo contract-aware semantic assertions và business regression fixtures.

### 13.2. Parameter validation

Validate transform parameters; không để caller tùy ý cung cấp URI/path cho external document. Giới hạn input và recursion theo policy.

## 14. Validation optimization an toàn

- Compile schema trước startup hoặc lazy-once có synchronization.
- Dùng immutable Schema cache theo version.
- Tạo Validator phù hợp từng request.
- Dùng resolver allowlisted để xử lý imports.
- Giới hạn payload/nesting và diagnostic collection.
- Tránh parse lại document nếu pipeline có API an toàn để tái sử dụng parsed representation.
- Giữ validation tại trust boundary đã xác định.

Không bỏ facets/identity constraints hoặc dùng schema “relaxed” trong production chỉ để benchmark nhanh hơn. Nếu contract validation không cần trên một flow nội bộ, thay đổi phải có architecture/security decision và tests chứng minh không bỏ mất trust boundary.

## 15. Signature optimization an toàn

- Cache trust/key configuration đúng lifecycle.
- Tránh ký lặp do interceptor duplication.
- Giảm số references chỉ khi threat model/policy cho phép và được review.
- Tránh transforms quá phức tạp nếu contract không cần.
- Dùng stable ID resolution và namespace handling.
- Chọn crypto provider/algorithm theo approved policy.
- Measure canonicalization và digest riêng nếu library hỗ trợ instrumentation.

Không bỏ Timestamp/Action/Body khỏi signed parts theo suy đoán. Security policy phải là nguồn quyết định.

## 16. Encryption optimization an toàn

- Chọn đúng encrypted parts theo confidentiality policy.
- Reuse provider/configuration, không reuse IV/nonce trái yêu cầu thuật toán.
- Dùng hybrid encryption theo WS-Security/XML Encryption profile.
- Tránh mã hóa lại cùng data trong nhiều interceptor.
- Đo recipient key wrapping riêng với symmetric payload encryption.
- Giảm payload thừa trước khi encryption nếu contract cho phép.
- Kiểm decrypted result bằng schema/business tests và test unauthorized disclosure.

Không tự tạo custom crypto protocol hoặc tái sử dụng key/IV sai cách để giảm cost.

## 17. Payload size và attachment strategy

Large binary content có thể làm XML envelope phình to nếu base64 inline. MTOM/XOP có thể gửi binary như MIME attachment và XML tham chiếu, giảm base64 expansion trong một số transports. Nhưng WS-Security attachment protection và partner support phải được xác minh; không phải mọi stack xử lý MTOM/security giống nhau.

### 17.1. Đo wire size và processing size

Theo dõi compressed/uncompressed HTTP size, SOAP XML bytes, decoded attachments và in-memory representation. Gzip giảm network bytes nhưng tăng CPU và không giảm parse/crypto work trên logical XML content.

### 17.2. Compression và security

Nén payload trước encryption có thể không hiệu quả nếu ciphertext không nén được; compression sau encryption thường không có lợi. Tránh compression oracle/data mixing risks khi secrets và attacker-controlled input được nén chung. Chỉ bật theo threat review và gateway policy.

## 18. Concurrency, queueing và backpressure

XML signature/encryption là CPU-intensive trong nhiều workloads; XSLT/validation có thể tạo allocation đáng kể. Nếu để quá nhiều concurrent transforms/security operations, CPU saturation và GC làm latency tăng.

### 18.1. Giới hạn concurrency

Thiết lập bounded executors/queues ở integration worker nếu xử lý async. Với servlet synchronous requests, cấu hình container thread pool và downstream pools cân đối. Không dùng unbounded queue vì chỉ chuyển overload thành memory growth và latency.

### 18.2. Backpressure

Khi worker/crypto service quá tải, từ chối hoặc throttle có kiểm soát theo API policy thay vì nhận vô hạn. Với JMS, điều chỉnh consumer concurrency/prefetch/redelivery theo broker và processing capacity.

### 18.3. Pooling

Pool HTTP connections, HSM sessions hoặc expensive resources theo library support. Không pool mutable XML Validator/Transformer hoặc security message objects theo cách gây cross-request state leakage.

### 18.4. Bulkhead theo loại công việc

Một partner/stylesheet/payload lớn không nên chiếm hết worker pool làm các SOAP operations khác đói tài nguyên. Có thể tách pool/limits theo operation class, partner hoặc cost tier nhưng tránh metric/tenant isolation sai.

## 19. Timeout budget và failure behavior

Một timeout end-to-end phải tính thời gian parse/validation, transform, signature/encryption, network, partner processing và response mapping.

~~~text
total deadline
  = queue wait
  + XML processing
  + cryptographic processing
  + network/partner time
  + response processing
~~~

Không đặt timeout riêng từng stage cộng lại vượt caller deadline. Truyền deadline/correlation theo flow nếu architecture hỗ trợ.

### 19.1. Timeout không được làm security bypass

Nếu validation hoặc signature verification vượt budget, fail theo policy; không bỏ qua security stage để trả response nhanh. Timeout nên tạo error có thể phân loại và metric theo stage.

### 19.2. Cancellation

Một client timeout không đảm bảo CPU work phía server tự dừng. Cần kiểm cancellation behavior của HTTP worker, transform/crypto libraries và async executor. Tránh tasks tiếp tục giữ heap/thread sau khi caller đã rời đi.

### 19.3. Retry

Không retry một signature/encryption failure như lỗi transient. Retry network errors có thể an toàn hơn nhưng side-effecting operation cần idempotency key. Không tạo nonce/timestamp reuse trái WS-Security policy khi retry.

## 20. Capacity planning

Để ước lượng tài nguyên, cần workload profile:

- Requests per second theo operation.
- Payload size distribution.
- Tỷ lệ request cần XSLT.
- Tỷ lệ dùng signature/encryption và số references/recipients.
- Concurrent requests/partner.
- p95/p99 latency target.
- CPU/memory budget và GC.
- HSM/provider throughput nếu có.
- Peak bursts, batch windows và retries.

### 20.1. CPU demand

Đo CPU time trung bình trên request cho từng workload class. CPU cores cần thiết phụ thuộc arrival rate × CPU-seconds/request, cộng headroom cho GC, runtime và bursts. Không lấy wall-clock latency làm CPU demand nếu nhiều thời gian chờ network/HSM.

### 20.2. Memory demand

Đo peak live heap và allocation rate dưới concurrency. DOM/intermediate trees có thể làm memory per in-flight request cao hơn nhiều so wire size. Sizing cần tính concurrency × per-request working set cộng baseline/cache.

### 20.3. Headroom

Không sizing sát 100% steady-state CPU. Cần reserve capacity cho bursts, JIT/GC, downstream slowdown, failover và deployment rolling restarts. Headroom dựa trên observed load profile/SLO, không một percentage cố định cho mọi service.

## 21. Profiling và phân tích GC

Dùng JVM profiling/APM hoặc Java Flight Recorder theo policy để xác định CPU hot methods, allocation sites, lock contention, thread states và GC pauses.

### 21.1. CPU profile

Tìm xem thời gian ở XML parser, schema validator, XSLT engine, canonicalizer, MessageDigest/Signature/Cipher, TLS hoặc business code. Không suy bottleneck chỉ từ một counter.

### 21.2. Allocation profile

Theo dõi DOM Node objects, byte arrays, char arrays, Strings, Transformer contexts và SOAP message wrappers. Một optimization giảm CPU nhưng tăng retained heap có thể làm p99 xấu hơn khi full GC.

### 21.3. GC correlation

Overlay GC pauses với p95/p99 request latency, queue depth và throughput. Nếu latency spikes cùng allocation bursts, tối ưu object churn/payload/concurrency có thể hiệu quả hơn tinh chỉnh GC flags trước.

## 22. Performance tests và security regression tests phải đi cùng nhau

Một tối ưu được chấp nhận khi cả performance và correctness/security gates đều pass.

| Thay đổi | Performance evidence | Security/correctness evidence |
|---|---|---|
| Cache Schema | Compile cost không lặp | Schema version/invalidation đúng |
| Cache XSLT Templates | Compile latency giảm | Output fixtures tương đương |
| Giảm DOM passes | Heap/CPU giảm | Signed nodes và QName giữ nguyên |
| Chọn crypto provider | Sign/verify throughput cải thiện | Algorithm/provider approved, interoperability |
| Giảm references | Ít canonicalization hơn | Security policy review và threat coverage |
| Bật streaming | Heap giảm ở payload lớn | Transform/sign/encrypt semantics tương đương |
| MTOM | Wire bytes giảm | Attachment protection/interoperability pass |
| Tăng concurrency | Throughput tăng | p99, memory, isolation và failure behavior pass |

### 22.1. Differential XML testing

So sánh output trước/sau theo semantics: QName, values, order, nil/default, business result và security references. Không chỉ compare byte-for-byte nếu serializer có thể đổi prefix/whitespace hợp lệ.

### 22.2. Negative security tests

Sau optimization, chạy lại tests cho invalid schema, tampered signed body, missing required signed header, untrusted certificate, replay, unauthorized disclosure và XXE protections. Hiệu năng tăng không đủ nếu security regression xuất hiện.

### 22.3. Performance regression budgets

Đặt baseline theo workload class, JVM/runtime version và security policy. Alert/block khi latency, allocation hoặc throughput regress vượt ngưỡng đã chọn sau khi xét noise. Không dùng một threshold cho mọi payload size.

## 23. Ví dụ kiến trúc component với cache an toàn

~~~java
@Configuration
public class XmlProcessingConfiguration {

    @Bean
    public OrderTransformer orderTransformer(
            ResourceLoader resourceLoader) throws Exception {
        Resource stylesheet =
            resourceLoader.getResource("classpath:xslt/order-to-partner.xsl");

        TransformerFactory factory = TransformerFactory.newInstance();
        factory.setFeature(XMLConstants.FEATURE_SECURE_PROCESSING, true);
        factory.setAttribute(XMLConstants.ACCESS_EXTERNAL_DTD, "");
        factory.setAttribute(XMLConstants.ACCESS_EXTERNAL_STYLESHEET, "");

        Templates templates = factory.newTemplates(
            new StreamSource(stylesheet.getInputStream())
        );

        return new OrderTransformer(templates);
    }
}
~~~

Đây là ví dụ cấu trúc. TransformerFactory attributes/features được hỗ trợ khác nhau theo provider; configure resolver, close resource stream và kiểm secure-processing behavior trên implementation thực tế.

### 23.1. Per-request Transformer

~~~java
public final class OrderTransformer {
    private final Templates templates;

    public OrderTransformer(Templates templates) {
        this.templates = templates;
    }

    public void transform(Source source, Result result)
            throws TransformerException {
        Transformer transformer = templates.newTransformer();
        transformer.transform(source, result);
    }
}
~~~

Compiled Templates được giữ dùng chung nếu implementation xác nhận an toàn; Transformer mới cho mỗi lần xử lý để tránh chia sẻ mutable state.

### 23.2. Startup validation

Compile schema/stylesheet khi startup hoặc health initialization. Nếu không thể compile policy-critical stylesheet, fail startup/mark readiness false thay vì để request đầu tiên nhận lỗi bất ngờ. Có thể lazy load có kiểm soát nếu service yêu cầu.

## 24. Bài thực hành: benchmark XML security pipeline

Thiết kế một Spring-WS flow nhận SubmitOrder, validate XSD, transform sang partner XML, ký SOAP Body/Timestamp/Action và encrypt phần payment data theo security policy.

### Nhiệm vụ

1. Tạo synthetic payload nhỏ, vừa, lớn và nhiều namespace/nodes.
2. Pin XSD, XSLT, WSS4J và crypto provider versions.
3. Đo schema compile một lần so với compile mỗi request để định lượng setup cost.
4. Đo validation latency và allocation theo payload size.
5. Đo XSLT compile và transform riêng.
6. Đo canonicalization/digest/signature theo reference count và subtree size.
7. Đo encryption theo payload bytes và recipient count.
8. Đo full pipeline end-to-end theo SOAP operation.
9. Chạy warm-up rồi benchmark steady-state.
10. Chạy concurrency levels và ghi CPU, heap, GC, p95/p99.
11. Profile CPU/allocation để xác định bottleneck thực tế.
12. Thử cache immutable Schema và Templates.
13. Tạo Validator/Transformer per request; kiểm thread safety.
14. Thử DOM/streaming approach nếu stack hỗ trợ.
15. Chạy regression fixtures so sánh XML/business output.
16. Verify Signature và decrypt message bằng receiver test configuration.
17. Chạy negative tests: schema invalid, tampered Body, missing signed Action, untrusted signer, replay.
18. Test external XSLT URI/DTD bị chặn.
19. Đặt payload, nesting, concurrency và timeout limits.
20. Viết performance report nêu workload, environment, baseline, result và security gates.

**Tiêu chí đạt:** Có baseline per-stage và end-to-end; tối ưu giảm latency/allocation trên workload đại diện; output/contract giữ nguyên; security tests không suy giảm; cache/threading không gây cross-request leakage.

### 24.1. Câu hỏi tình huống

**A:** p95 cao khi request có 20 references được ký, trong khi schema validation chỉ chiếm phần nhỏ CPU. Nên profile những gì trước khi đổi policy?

**B:** Team compile XSLT mỗi request và định cache Templates. Object nào có thể share, object nào nên tạo per request và cần kiểm tra provider guarantees nào?

**C:** Chuyển sang streaming làm memory giảm nhưng XML Signature library vẫn dựng DOM. Benchmark nào chứng minh optimization có lợi end-to-end?

**D:** Bỏ signed WS-Addressing Action làm latency giảm. Tại sao đây không phải optimization được chấp nhận nếu security policy yêu cầu ký Action?

## 25. Checklist trước khi tối ưu production

- [ ] Đã xác định schema/XSLT/signature/encryption stages thực tế trong flow.
- [ ] Có baseline latency p50/p95/p99, throughput, CPU và allocation.
- [ ] Đo cold-start và steady-state riêng.
- [ ] Payload corpus đại diện size, nesting, references và recipients.
- [ ] Schema compile không lặp trên mỗi request nếu không cần.
- [ ] XSLT Templates được cache theo version/configuration đúng.
- [ ] Validator/Transformer mutable không bị share unsafe giữa threads.
- [ ] External schema/stylesheet resolution có allowlist.
- [ ] DOM/streaming choice được benchmark end-to-end.
- [ ] XML Signature canonicalization và references đã được profile.
- [ ] Không giảm signed parts hoặc downgrade crypto vì hiệu năng.
- [ ] XML Encryption vẫn bảo vệ đúng parts/recipients.
- [ ] Payload/depth/attachment/concurrency có giới hạn.
- [ ] Crypto provider/HSM throughput và key rotation được tính.
- [ ] Timeout budget/cancellation/retry policy rõ.
- [ ] Metrics không chứa identifiers/secrets nhạy cảm.
- [ ] Heap/GC/queueing được theo dõi dưới tải.
- [ ] Performance tests đi cùng security regression tests.
- [ ] Output XML/business semantics được kiểm tra trước/sau.
- [ ] Release report có workload, environment, result và exception approvals.

## 26. Ghi nhớ

- **Validation, XSLT, signature và encryption đều có cost setup và cost per request.** Tách hai loại này khi đo.
- **Schema và compiled XSLT templates có thể được reuse theo lifecycle an toàn; Validator và Transformer mutable nên được quản lý theo request/provider guarantees.**
- **Canonicalization và signed references có thể là phần tốn kém của XML Signature.** Không bỏ required parts để tăng tốc.
- **XML Encryption cost phụ thuộc payload, recipient count và crypto operations.** Dùng hybrid profile đúng chuẩn.
- **DOM tiện cho XML security nhưng có thể tạo heap/allocation lớn; streaming chỉ có lợi khi toàn pipeline hỗ trợ.**
- **Benchmark phải có warm-up, payload corpus, concurrency và end-to-end measurements.**
- **Tối ưu stage không phải bottleneck có thể không cải thiện SLO.** Profile lại sau mỗi thay đổi.
- **Cache cần versioning, invalidation, rotation và thread-safety rõ.**
- **Giới hạn payload/concurrency và backpressure** bảo vệ availability khi XML processing tốn tài nguyên.
- **Performance gain chỉ được chấp nhận khi contract, signature, encryption và negative security tests vẫn pass.**

**Câu hỏi tự kiểm tra:** Một service SOAP p99 tăng mạnh khi xử lý payload lớn. Profile cho thấy DOM allocation cao, XSLT được compile mỗi request và signature canonicalization chiếm CPU đáng kể. Hãy thiết kế benchmark tách từng stage, đề xuất cache Schema/Templates đúng thread-safety, đánh giá DOM/streaming, giải thích vì sao không được giảm signed parts hoặc downgrade encryption để cải thiện số đo, rồi định nghĩa security/performance release gates.

## 27. Tài liệu tham khảo để đối chiếu

- Spring Web Services Reference: message processing, interceptors, marshalling và SOAP security integration.
- Java API for XML Processing (JAXP): SchemaFactory, Schema, Validator, TransformerFactory, Templates, Transformer và secure processing.
- W3C XML Schema specifications: validation, schema composition và constraints.
- W3C XSL Transformations (XSLT) specifications: stylesheet processing, XPath evaluation và streaming support theo version.
- W3C XML Signature and XML Encryption specifications: references, transforms, canonicalization, digest, signature và encrypted data/key.
- Apache WSS4J documentation: security actions, signed/encrypted parts, Crypto configuration và processor behavior.
- Java Cryptography Architecture/JCA provider documentation: Signature, Cipher, MessageDigest, provider selection và key handling.
- JVM/JFR/GC documentation: CPU profiling, allocation, heap và pause analysis.

Thread-safety, streaming support, secure-processing properties và performance của provider phụ thuộc implementation/version. Pin JDK, Spring-WS, JAXB, XSLT processor, WSS4J và crypto provider; benchmark trên đúng stack deploy thay vì suy từ microbenchmark riêng lẻ.

