# Đọc ma trận tương thích trước khi thay đổi JDK, Boot, Spring-WS hoặc WSS4J

Một dự án Spring Web Services hiếm khi chỉ có một dependency. Runtime SOAP thường kết hợp JDK, Spring Boot, Spring Framework, Spring-WS, JAXB, SAAJ hoặc Axiom, WSS4J, Apache Santuario, XML Security provider, HTTP client và thư viện logging/observability. Nâng riêng một thành phần có thể làm thay đổi API, namespace, provider được chọn, cách parse XML, TLS defaults hoặc thuật toán bảo mật.

Vì vậy, trước khi đổi JDK, Boot, Spring-WS hay WSS4J, hãy đọc **ma trận tương thích của cả release train**. Một version có thể tồn tại trên Maven Central không có nghĩa nó tương thích với các thành phần còn lại hoặc được vendor hỗ trợ. Build thành công cũng chưa đủ chứng minh SOAP interoperability.

Bài học thuộc chương **Nâng cấp và di chuyển** của module `SPRING_WEB_SERVICES`. Module học phát triển SOAP theo contract-first với Spring Web Services, thiết kế XSD/WSDL, JAXB, endpoint/client, SOAP Fault, interceptor, XML security, WS-Security, chứng chỉ và kiểm thử tương thích. Migration phải đánh giá **binary/source compatibility, XML/JAXB behavior, SOAP wire format, cryptographic policy và vận hành**.

Ví dụ hướng tới Java 17+ và các thế hệ Spring Framework/Spring-WS dùng Jakarta APIs; Java baseline cụ thể phải lấy từ release notes và system requirements của đúng version đang chọn. Snippet Maven/Gradle là mẫu cấu trúc, cần thay bằng release train đã xác minh. Không có SPECIAL_NOTE bổ sung cho bài này.

## Mục tiêu học tập

1. Lập compatibility matrix trước khi nâng JDK, Boot, Framework, Spring-WS và WSS4J.
2. Phân biệt version tồn tại, version tương thích và version được hỗ trợ.
3. Hiểu tác động của `javax.*` sang `jakarta.*`, JAXB runtime, SAAJ provider và XML security libraries.
4. Dùng Spring Boot BOM/dependency management để tránh trộn release train.
5. Phát hiện dependency convergence, transitive overrides và duplicate providers.
6. Lập migration sequence theo từng thay đổi có thể kiểm chứng.
7. Kiểm tra WS-Security signature, encryption, UsernameToken, certificates và algorithm policy sau nâng cấp.
8. Thiết kế test gates cho build, contract, SOAP interoperability, TLS, performance và rollback.
9. Tách lỗi dependency migration khỏi lỗi contract/application change.

## 1. Vì sao phải đọc compatibility matrix trước?

~~~mermaid
flowchart TD
    A["JDK / JVM"] --> B["Spring Boot platform"]
    B --> C["Spring Framework"]
    C --> D["Spring Web Services"]
    D --> E["SOAP message factory"]
    E --> F["SAAJ provider / Axiom"]
    D --> G["JAXB API + runtime"]
    D --> H["WSS4J"]
    H --> I["XML Security / Santuario"]
    H --> J["Crypto provider / keystore"]
    D --> K["HTTP transport / client"]
    C --> L["Servlet container"]
    E --> M["XML parser / Transformer"]
~~~

Mỗi cạnh có ràng buộc riêng:

- JDK quyết định class-file level, APIs có trong JDK, TLS provider, crypto defaults và module behavior.
- Spring Boot quản lý dependency versions qua BOM; Spring Framework và Spring-WS phải thuộc release train tương thích.
- Spring-WS cần SOAP API/provider phù hợp với thế hệ `javax` hay `jakarta`.
- JAXB API và implementation phải tương thích namespace, runtime và generated code.
- WSS4J phụ thuộc XML Security/Santuario, StAX, cryptographic libraries và cách parse/process security headers.
- SAAJ/Axiom quyết định message model, MIME handling, caching và serialization.
- Container/HTTP stack quyết định servlet namespace, TLS, connection pool và request limits.

Lỗi `NoSuchMethodError` có thể do binary mismatch dù source compile; `ClassNotFoundException` có thể do thiếu provider/runtime; SOAP Fault `InvalidSecurity` có thể xuất hiện dù application code không đổi vì WSS4J/Santuario thay đổi cách xử lý token hoặc thuật toán.

## 2. Compatibility matrix phải có những chiều nào?

Không lập bảng chỉ gồm artifact và version. Matrix cần tối thiểu:

| Thành phần | Điều cần xác minh | Nguồn chính |
| --- | --- | --- |
| JDK | Supported Java versions, bytecode target, TLS/crypto behavior | Vendor system requirements, JDK release notes |
| Spring Boot | Supported JDK, managed Framework line, dependency BOM | Boot reference/release notes |
| Spring Framework | Compatible Boot line, Jakarta baseline, deprecations | Framework release notes |
| Spring-WS | Supported Framework/Java line, SOAP API, SAAJ/Axiom | Spring-WS reference/release notes |
| JAXB | `javax` hay `jakarta`, API/runtime alignment, XJC generated code | Jakarta XML Binding/provider docs |
| SAAJ | SOAP API namespace, implementation/provider selection | Spring-WS/provider docs |
| Axiom | Spring-WS adapter and Axiom core version compatibility | Spring-WS/Axiom release notes |
| WSS4J | Spring-WS integration, Java baseline, supported security actions | WSS4J release notes |
| Santuario/XML Security | WSS4J transitive range, XML Signature/Encryption behavior | Apache Santuario docs |
| Crypto provider | JDK/provider algorithm availability and policy | Provider/JDK documentation |
| Servlet container | Jakarta Servlet version and Boot compatibility | Boot/container docs |
| HTTP client | TLS, timeout, pooling, proxy, streaming behavior | Client library docs |

### 2.1. Version có thể tải không đồng nghĩa version tương thích

Ba khái niệm phải phân biệt:

- **Available:** artifact được publish và repository có thể resolve.
- **Compatible:** upstream documentation/test matrix chỉ ra các thành phần có thể hoạt động cùng nhau.
- **Supported:** tổ hợp nằm trong support policy của vendor/project và còn nhận security/bug fixes.

Một combination có thể build bằng cách ép transitive version nhưng không được upstream test/support. Khi có sự cố, override dependency có thể khiến maintainer khó tái hiện.

### 2.2. Kiểm release train theo một nguồn quản lý phiên bản

Nếu dùng Spring Boot, ưu tiên version do Boot BOM quản lý. Không tự nâng `spring-core`, `spring-context`, `spring-ws-core` hoặc WSS4J từng cái theo phiên bản mới nhất. Nếu cần override, phải có compatibility evidence và regression test giải thích rõ.

Với Spring Framework/Spring-WS dùng độc lập Boot, tự quản lý matrix: Framework line, WS line, SOAP API/provider, JAXB runtime, WSS4J và Java baseline.

### 2.3. Mẫu matrix cho dự án

| Dimension | Current baseline | Target candidate | Evidence | Gate |
| --- | --- | --- | --- | --- |
| JDK | Version production hiện tại | JDK mục tiêu | Vendor supported matrix | Compile + runtime tests |
| Spring Boot | BOM hiện tại | BOM mới | Boot release notes | Context + integration tests |
| Spring Framework | BOM-managed | Version do target BOM chọn | Framework compatibility | No linkage errors |
| Spring-WS | Version hiện tại | Version target được hỗ trợ | WS reference/release notes | SOAP contract suite |
| JAXB API/runtime | Provider hiện tại | API + runtime đồng bộ | Namespace/provider docs | Generated clients |
| SAAJ/Axiom | Message factory hiện tại | Provider mới hoặc giữ nguyên | Provider docs | SOAP 1.1/1.2 + MTOM |
| WSS4J/Santuario | Dependency graph hiện tại | Bộ transitive được xác minh | WSS4J release notes | WS-Security interop |
| Servlet/container | Runtime hiện tại | Container tương thích target Boot/JDK | Container matrix | HTTP/TLS integration |
| Partner clients | Java/.NET stack đã xác nhận | Không đổi hoặc có plan | Partner test evidence | Certification/UAT |

Điền version/tag và link evidence cho **đúng target release**. Nếu một ô không có bằng chứng, đánh dấu UNKNOWN và xem là điều kiện chặn trước production, thay vì đoán.

## 3. Đổi JDK: không chỉ thay sourceCompatibility

### 3.1. Kiểm tra Java baseline của toàn release train

Đọc system requirements của Boot, Framework, Spring-WS, WSS4J và các provider. Thành phần có baseline cao nhất có thể quyết định minimum runtime. Đồng thời kiểm plugin build, compiler, test runner, JAXB/XJC toolchain, Maven/Gradle wrapper và container image.

Phân biệt:

- **Build JDK:** JVM chạy Maven/Gradle và compiler plugins.
- **Compile target/release:** bytecode/API level mà source được compile.
- **Runtime JDK:** JVM chạy ứng dụng production.
- **Toolchain JDK:** JVM/tool được dùng cho XJC, test hoặc code generation.

Có thể compile target thấp hơn JDK chạy build, nhưng không thể gọi API chỉ có trong runtime mới nếu app phải chạy trên runtime cũ.

### 3.2. Kiểm tra TLS và cryptographic defaults

Đổi JDK có thể thay default TLS protocols/cipher suites, truststore behavior, disabled algorithms, provider ordering và certificate path validation. Với SOAP secured bằng HTTPS/mTLS hoặc WS-Security X.509, kiểm:

- Server/client certificate chain và hostname verification.
- TLS protocol/cipher compatibility với partner.
- Key algorithm/key size và certificate signature algorithm.
- Keystore format/type và alias lookup.
- Trust anchor, intermediate certificate và expiry handling.
- Algorithms bị JDK security policy disable.
- XML Signature canonicalization/digest/signature algorithms được partner hỗ trợ.

Không hạ security properties toàn JVM để làm partner legacy hoạt động nếu chưa có risk approval, scope isolation và migration plan.

### 3.3. Build tool và generated sources

Nâng JDK cần kiểm Maven/Gradle wrapper, compiler plugin, test plugin, annotation processors, XJC và code-generation tasks. Generated source có thể khác khi JAXB tool version thay đổi dù XSD không đổi. Lưu generated source diff và kiểm API/QName/annotations thay vì regenerate rồi commit mà không review.

## 4. Nâng Spring Boot và Spring Framework theo release train

### 4.1. Boot BOM là tập hợp version đã được quản lý cùng nhau

Spring Boot dependency management chọn version cho các thư viện thuộc platform. Khi đổi Boot version, hãy xem diff dependency graph vì nhiều artifact có thể đổi dù bạn không sửa trực tiếp dependency declaration.

Không dùng chiến lược “Boot mới + giữ vài Spring Framework jars cũ + Spring-WS mới nhất”. Trừ khi có chỉ dẫn upstream rõ ràng, hãy giữ Spring Framework modules trong cùng line mà Boot target quản lý. Một số lỗi runtime chỉ xuất hiện khi code gọi method mới hơn API đang thực sự được nạp.

### 4.2. Phân biệt upgrade Boot với upgrade application dependencies

| Thay đổi | Rủi ro điển hình | Cần kiểm |
| --- | --- | --- |
| Boot parent/BOM | Nhiều transitive versions đổi | Dependency diff + integration suite |
| Spring Framework | API/deprecation, proxy/transactions, Servlet integration | Compile + context + endpoint tests |
| Spring-WS | Message factory/interceptor/client behavior | SOAP contract + wire tests |
| Servlet container | Jakarta Servlet baseline, filters, error handling | HTTP integration/TLS |
| Logging/APM | Pattern/encoder/agent thay đổi | Redaction/security tests |

Không gộp mọi major upgrade trong một commit nếu cần dễ xác định regression. Có thể nâng Boot platform trước, sau đó xử lý compile/runtime migrations và SOAP provider issues bằng những commits riêng.

### 4.3. Maven: dùng parent hoặc BOM nhất quán

Ví dụ dùng Boot parent (placeholder version phải thay bằng release đã xác minh):

~~~xml
<parent>
  <groupId>org.springframework.boot</groupId>
  <artifactId>spring-boot-starter-parent</artifactId>
  <version>${boot.version}</version>
  <relativePath/>
</parent>

<dependencies>
  <dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web-services</artifactId>
  </dependency>
</dependencies>
~~~

Nếu không dùng Boot parent, import `spring-boot-dependencies` BOM trong `dependencyManagement` và vẫn khai báo các dependency versionless cho những artifact do BOM quản lý. Tránh đặt version thủ công trùng với BOM nếu không có lý do.

### 4.4. Gradle: dùng platform/BOM

~~~kotlin
dependencies {
    implementation(platform("org.springframework.boot:spring-boot-dependencies:${bootVersion}"))
    implementation("org.springframework.boot:spring-boot-starter-web-services")
}
~~~

Đây là ví dụ Kotlin DSL. Nếu plugin Boot đã cấu hình dependency management, đừng import platform trùng lặp theo cách tạo ra precedence khó hiểu. Kiểm resolution result thực tế bằng Gradle dependency insight.

## 5. javax sang jakarta: migration của namespace và ecosystem

### 5.1. Không phải rename package đơn giản

Jakarta EE APIs trước đây dưới namespace `javax.*` đã chuyển nhiều API enterprise sang `jakarta.*`. Thay đổi này là binary incompatible ở type level: `javax.xml.bind.JAXBContext` và `jakarta.xml.bind.JAXBContext` là hai class khác nhau. Một thư viện compile với API namespace cũ không thể được coi là thay thế trực tiếp cho thư viện mới namespace.

Đặc biệt kiểm:

- JAXB annotations/runtime và generated source imports.
- SAAJ SOAP APIs/provider packages.
- Servlet API và Spring Boot generation.
- Validation API/implementation nếu SOAP request dùng Bean Validation.
- Activation/DataHandler APIs cho attachments/MTOM.
- JAX-WS/JAXB code generation tool và plugin version nếu project dùng.

### 5.2. Source code có thể trộn hai namespace nhưng runtime dễ vỡ

Một project có thể compile nếu cả hai API jars cùng nằm trên classpath, nhưng không có nghĩa object model/interceptors có thể trao đổi types giữa chúng. Generated class mang annotation namespace khác với marshaller runtime có thể không được nhận diện hoặc bị binding lỗi.

Không giải quyết bằng cách thêm cả hai API dependency rồi hy vọng provider tự hiểu. Chốt namespace target, nâng đúng provider và regenerate/migrate code có kiểm soát.

### 5.3. XSD/WSDL không nhất thiết đổi namespace khi Java package đổi

XML namespace trong contract là QName trên wire; package Java generated là mapping implementation. Thay package import từ `javax` sang `jakarta` không tự yêu cầu đổi XSD `targetNamespace` hay QName operations. Giữ nguyên contract wire nếu chỉ migration runtime và contract không đổi; xác nhận bằng golden SOAP fixtures trước/sau.

### 5.4. Generated classes và binding customizations

Khi đổi JAXB/XJC generation:

1. Pin tool version, binding files và catalog/resolver inputs.
2. Generate vào thư mục sạch để tránh generated source cũ còn sót.
3. Diff class names, imports, annotations, element QNames, enum constants và adapter mappings.
4. Compile client/server trong đúng namespace runtime.
5. Marshal/unmarshal fixtures cũ và mới; so XML infoset/QNames, không chỉ string formatting.
6. Kiểm schema validation/default/nillable/presence behavior.

Không sửa tay generated source để làm build pass nếu bước generate tiếp theo sẽ ghi đè. Đưa customization vào XJB/binding file hoặc mapper riêng.

## 6. Nâng WSS4J và XML Security libraries

### 6.1. WSS4J và Santuario cần được xem như một cụm

WSS4J xử lý WS-Security actions/token profiles và phụ thuộc các thư viện XML Security/cryptographic. Nâng riêng Santuario hoặc WSS4J có thể thay đổi XML Signature/Encryption parsing, algorithm support, secure validation defaults, ID resolution hoặc exception behavior.

Quy tắc thực hành:

- Đọc WSS4J release notes và dependency requirements của phiên bản mục tiêu.
- Ưu tiên transitive versions mà WSS4J release quản lý/test.
- Không override XML Security/Santuario một cách độc lập chỉ vì scanner báo version mới; xác định version fix tương thích.
- Kiểm Java security provider, Bouncy Castle hoặc provider khác nếu ứng dụng dùng.
- Kiểm policy algorithm và certificate/key strength với partner.

### 6.2. Những WS-Security behaviors cần kiểm thử lại

| Capability | Regression cần chạy |
| --- | --- |
| UsernameToken PasswordText | Callback/password validation, encoding, timestamp freshness |
| UsernameToken PasswordDigest | Nonce, Created, replay cache, shared secret semantics |
| X.509 Signature | Trust chain, key selection, signature verification và signed parts |
| XML Encryption | Key transport, data encryption, decrypt order và content type |
| Timestamp | Clock skew, expiry, created/expiry semantics |
| Derived keys / tokens | Profile/action compatibility nếu đang sử dụng |
| SOAP 1.1/1.2 | Fault mapping, SOAP headers và action behavior |
| WS-Addressing | Action/To/MessageID và endpoint routing |

Nếu version mới reject signature partner đang dùng, đừng vội bật insecure algorithm globally. Thu thập algorithm URI, key/cert properties từ metadata an toàn; xác nhận policy/vendor support, sau đó xây migration plan với partner.

### 6.3. XML Signature không chỉ là kiểm tra chữ ký

Signature verification phụ thuộc canonicalization transform, digest algorithm, signature algorithm, ID attributes, reference resolution, namespace handling và phần tử thực sự được ký. Regression phải phát hiện XML Signature Wrapping (XSW), ID ambiguity và trường hợp Body được verify nhưng endpoint đọc một node khác.

Kiểm rằng security engine xác minh đúng SOAP Body/Header cần thiết và application xử lý đúng chính các nodes đã xác minh. Không chỉ test một chữ ký thành công; cần test sửa Body, duplicate IDs, wrapping, external reference và key không trusted đều bị reject.

### 6.4. TLS và WS-Security có lớp bảo vệ khác nhau

JDK/provider upgrade có thể ảnh hưởng TLS handshake và certificate path; WSS4J upgrade có thể ảnh hưởng message-level signature/encryption. Chạy riêng:

- HTTP TLS/mTLS tests với truststore/client cert production-like.
- WS-Security signing/encryption interop tests qua HTTP transport thật.
- End-to-end test với partner Java/.NET hoặc golden signed fixtures.
- Test rotate/expire cert, unknown CA, weak algorithm và clock skew.

Đừng coi TLS handshake pass là bằng chứng XML Signature pass, hoặc ngược lại.

## 7. Đọc dependency graph thay vì đoán từ build file

### 7.1. Maven: kiểm dependency tree và convergence

~~~powershell
mvn -DskipTests dependency:tree
mvn -DskipTests dependency:tree -Dincludes=org.springframework,org.springframework.ws,org.apache.wss4j,org.apache.santuario
mvn help:effective-pom
~~~

Kiểm version được resolve, dependency path và exclusions. Dùng Maven Enforcer (ví dụ dependency convergence/require upper bound theo policy) để phát hiện version lệch. Enforcer rule cần cấu hình phù hợp; không bật rule một cách máy móc nếu BOM có intentional dependency mediation.

### 7.2. Gradle: dependencyInsight

~~~powershell
.\gradlew dependencies --configuration runtimeClasspath
.\gradlew dependencyInsight --dependency spring-ws-core --configuration runtimeClasspath
.\gradlew dependencyInsight --dependency wss4j-ws-security-common --configuration runtimeClasspath
.\gradlew dependencyInsight --dependency xmlsec --configuration runtimeClasspath
~~~

Đọc cả compile và runtime configurations. Một dependency có thể compile đúng nhưng runtimeClasspath lại kéo implementation/provider khác do transitive dependency hoặc constraint.

### 7.3. Phát hiện duplicate API/provider

Những thứ cần tìm:

- Cùng một Spring Framework module xuất hiện nhiều version.
- Cùng JAXB API namespace có nhiều implementation/provider.
- SAAJ API và implementation mismatch hoặc provider discovery chọn provider ngoài dự kiến.
- Cả `javax` và `jakarta` API jars cùng được đưa vào classpath ngoài chủ đích.
- WSS4J/Santuario versions bị override so với dependency range của WSS4J.
- Hai XML parser/Transformer providers thay đổi provider selection.
- BC/provider jars khác version trên classpath so với security configuration.

Dependency tree là bước đầu; khi runtime vẫn chọn provider bất ngờ, kiểm classloader/provider discovery và effective runtime image/container. Không log secret/system properties để debug classpath.

## 8. Quy trình migration có thể kiểm chứng

### 8.1. Tách migration thành các bước có baseline

~~~mermaid
flowchart TD
    A["Freeze current baseline"] --> B["Capture dependency graph + test results"]
    B --> C["Choose target release train"]
    C --> D["Verify official compatibility evidence"]
    D --> E["Upgrade JDK/build tool"]
    E --> F["Upgrade Boot/Framework platform"]
    F --> G["Align Spring-WS + JAXB/SAAJ/Axiom"]
    G --> H["Align WSS4J + Santuario/providers"]
    H --> I["Run SOAP and security regression suites"]
    I --> J{"All gates pass?"}
    J -- "No" --> K["Isolate incompatibility or rollback"]
    J -- "Yes" --> L["Canary / partner certification"]
    L --> M["Production rollout + monitor"]
~~~

Không phải mọi dự án cần đúng thứ tự này; có thể bị ràng buộc bởi minimum JDK của Boot target hoặc vendor. Ý chính là mỗi bước có baseline, dependency diff và test result riêng để xác định thay đổi nào gây regression.

### 8.2. Capture baseline trước khi sửa

Ghi lại:

- JDK vendor/version, JVM args và security properties liên quan.
- Boot/Framework/Spring-WS/WSS4J/Santuario resolved versions.
- SOAP WSDL/XSD artifacts và hashes.
- JAXB generated source/API snapshot.
- Test fixtures cho SOAP 1.1/1.2, WS-Addressing, UsernameToken, X.509, signature/encryption và MTOM.
- TLS trust/key material **chỉ bằng metadata/fingerprint**, không copy private keys vào report.
- Throughput, p95/p99, heap/RSS/GC và fault distribution.
- Partner/client versions và integration sign-off hiện tại.

Baseline giúp phân biệt regression do migration với behavior đã có từ trước.

### 8.3. Nâng dependency theo nhóm có quan hệ

Nhóm platform (JDK + Boot/Framework) trước; sau đó căn Spring-WS và message factory; sau đó JAXB/SAAJ/Axiom; cuối cùng WSS4J/Santuario/crypto provider nếu không bị BOM ép cùng lúc. Nếu Boot BOM nâng toàn bộ transitive đồng thời, sử dụng dependency diff và test gates để khoanh vùng; không cố ép mọi artifact về version cũ trái với platform.

Giữ mỗi commit/PR có một mục tiêu rõ: toolchain, namespace migration, provider replacement, WSS4J policy adjustment hoặc application API cleanup.

## 9. Test gates sau migration

### 9.1. Gate build và runtime

- Compile với target JDK; kiểm source/generated classes không còn reference namespace cũ ngoài chủ đích.
- Chạy unit tests và context startup trên đúng runtime JDK/container image.
- Kiểm classpath/linkage: không `NoSuchMethodError`, `NoClassDefFoundError`, `ClassCastException` do duplicate classloader types.
- Kiểm dependency convergence/exclusions và provider discovery.
- Chạy native/container packaging và startup command production-like.

### 9.2. Gate contract và SOAP interoperability

| Test | Điều cần xác minh |
| --- | --- |
| WSDL/XSD publication | WSDL URL, imports/includes, QName và schema hashes ổn định |
| SOAP 1.1 | Envelope namespace, SOAPAction, headers, faults |
| SOAP 1.2 | Content-Type/action parameter, fault code/reason/detail |
| JAXB | Marshal/unmarshal old/new golden fixtures, nil/default/order |
| Spring-WS endpoint | PayloadRoot mapping, interceptors, validation, resolvers |
| Spring-WS client | WebServiceTemplate, sender, timeout, faults, response extraction |
| WS-Addressing | Action/To/MessageID và routing |
| MTOM/SwA | Content-ID, DataHandler/attachments, streaming và size limits |
| Partner clients | Generated Java/.NET client từ WSDL đã phát hành |

Không chỉ assert Java object bằng nhau; kiểm wire-level SOAP Envelope, QName, HTTP headers và Fault behavior.

### 9.3. Gate WS-Security và certificate

Test ít nhất:

- UsernameToken PasswordText/PasswordDigest hợp lệ và sai.
- Timestamp expiry, clock skew và replay detection.
- X.509 trusted/untrusted/expired certificate, rotation và chain validation.
- Signature đúng, signature tampered, Body/header không được ký, duplicate ID và wrapping attempts.
- Encryption/decryption, algorithm allowlist, unsupported/weak algorithm rejection.
- TLS server certificate, hostname, client certificate/mTLS và truststore.
- Cross-version interop với WSS4J/partner stack đang production.

Test security âm tính quan trọng tương đương happy path: invalid message phải bị reject trước business side effect.

### 9.4. Gate performance và observability

Compare baseline/target với cùng payload size, concurrency và data fixtures:

- p50/p95/p99 latency, throughput và timeout rate.
- Heap/RSS, allocation, GC pauses và temp attachment storage.
- Connection pool, in-flight requests và thread utilization.
- SOAP Fault distribution và parser/security rejection category.
- Log redaction/trace propagation không thay đổi; không xuất hiện secret/PII mới.

Không tăng timeout hoặc tăng heap chỉ để che regression trước khi xác định bottleneck.

## 10. Canary rollout, partner certification và rollback

### 10.1. Rollout theo nhóm traffic

1. Deploy vào test/staging với production-like certificates, WSDLs và partner fixtures.
2. Chạy smoke/interoperability tests với một nhóm partner/client đại diện.
3. Canary traffic giới hạn, theo dõi fault category, TLS failures, latency, CPU/heap và WSS4J validation outcomes.
4. Mở rộng theo partner hoặc endpoint, có owner và rollback trigger.
5. Giữ compatibility với old client/contract trong thời gian deprecation đã công bố.

### 10.2. Rollback phải bao gồm cả binary và config

Rollback không chỉ đổi container image. Cần biết liệu migration có thay:

- Database/schema/config secrets hoặc keystore/truststore formats.
- JAXB generated artifacts/WSDL publication.
- Security algorithms, certificate aliases hoặc key rotation state.
- Message factory behavior, attachment cache/storage và temp directory.
- Contract response shape hay endpoint routing.

Nếu migration đã đổi keystore format hoặc rotate keys, binary rollback cũ có thể không đọc được keystore mới. Giữ bản backup/format tương thích, dual trust trong cửa sổ migration nếu policy cho phép và rollback playbook đã diễn tập.

### 10.3. Rollback trigger

Đặt trước ngưỡng có thể đo:

- Partner WS-Security failures vượt baseline threshold.
- TLS/mTLS handshake failure tăng bất thường.
- SOAP Fault hoặc HTTP 5xx tăng theo operation.
- p95/p99 latency, timeout hoặc memory/GC vượt budget.
- WSDL/client interop regression hoặc contract validation failure.
- Security redaction/provider validation không đạt.

Rollback không thay thế điều tra root cause; ghi release ID, dependency manifest, partner cohort và thời điểm bắt đầu regression để phân tích.

## 11. Anti-pattern khi nâng cấp SOAP stack

| Anti-pattern | Vì sao nguy hiểm | Cách xử lý |
| --- | --- | --- |
| Lấy mọi dependency version mới nhất | Trộn release trains và transitive APIs | Dùng BOM/matrix được xác minh |
| Ép riêng Spring Framework module | Tạo binary mismatch | Giữ cùng release line do platform quản lý |
| Override Santuario để xử lý CVE mà không kiểm WSS4J | Có thể phá signature/encryption behavior | Chọn bản fix tương thích từ upstream guidance |
| Chỉ chạy unit tests | Không kiểm HTTP/SOAP/provider/partner behavior | SOAP integration + interop suite |
| Compile trên JDK mới nhưng chạy JDK cũ chưa test | Runtime APIs/class-file mismatch | Test đúng runtime/container target |
| Trộn javax và jakarta API | Hai type systems không tương thích | Chọn một namespace runtime nhất quán |
| Regenerate JAXB rồi bỏ qua diff | Thay QNames, adapters, enum/presence mapping | Pin XJC và review generated diff |
| Tắt secure algorithm validation để partner pass | Hạ bảo mật toàn cục | Scope policy migration và partner upgrade |
| Chỉ test signature hợp lệ | Bỏ sót wrapping/duplicate ID/tampering | Negative security tests |
| Nâng provider trong production trực tiếp | Khó isolate regression | Staging, canary, rollback |
| Bỏ WSDL fixture/schema hash | Không phát hiện contract drift | Pin published artifacts và wire tests |
| Sửa nhiều major components trong một thay đổi | Không truy được nguyên nhân regression | Chia migration thành bước có gate |

## 12. Quy tắc ra quyết định khi matrix chưa đầy đủ

### 12.1. Go/no-go

| Trạng thái evidence | Quyết định |
| --- | --- |
| JDK/Boot/Framework/WS official matrix rõ; dependency graph sạch; SOAP và security suites pass | Có thể vào canary theo kế hoạch |
| Artifact resolve nhưng không tìm được compatibility evidence | Chưa production; tạo spike/compatibility test hoặc hỏi maintainer/vendor |
| Có override dependency ngoài BOM nhưng chưa có regression evidence | No-go cho rollout rộng |
| JAXB namespace/provider chưa đồng nhất | No-go; xử lý type/runtime alignment trước |
| Partner security interop chưa test | Chỉ staging; chưa bật traffic secured production |
| Có lỗi security negative test hoặc signature coverage | No-go tuyệt đối tới khi sửa |
| Performance vượt budget hoặc rollback chưa diễn tập | Chưa rollout rộng |

### 12.2. Lưu compatibility evidence cùng release

Mỗi lần nâng cấp nên lưu:

- Compatibility matrix có version đầy đủ và ngày kiểm tra.
- Link release notes/system requirements cho các thành phần chính.
- Dependency tree/lockfile/SBOM của runtime artifact.
- WSDL/XSD hash và generated client version.
- Test reports: contract, TLS, WS-Security positive/negative, partner interop, load.
- Exception/override rationale và người phê duyệt.
- Canary metrics, rollback trigger và kết quả rehearsal.

Đây là hồ sơ kỹ thuật để tái hiện đúng release; không đưa private key, passwords, raw tokens hay production payloads vào artifacts.

## 13. Checklist trước khi nâng cấp

### Compatibility

- Đã chọn target JDK và xác minh minimum/maximum supported versions?
- Boot BOM, Framework, Spring-WS và Servlet container thuộc tổ hợp được hỗ trợ?
- JAXB API/runtime/codegen dùng cùng namespace và provider?
- SAAJ/Axiom provider đã xác định, không có duplicate implementations?
- WSS4J/Santuario/crypto provider dùng dependency versions tương thích?
- Không có dependency override chưa được chứng minh?

### Migration

- Đã capture current dependency graph, runtime config và baseline test?
- Có kế hoạch chia bước và xác định owner của từng regression?
- Generated JAXB diff và wire contract diff đã review?
- TLS/certificate/keystore migration có rehearsal và rollback?
- Có old/new WSDL clients và partner certification tests?

### Release

- Build/context startup trên JDK/container đích pass?
- SOAP 1.1/1.2, faults, WS-Addressing, MTOM và contract fixtures pass?
- WS-Security positive/negative, X.509, timestamp/replay và algorithm policy pass?
- Performance/heap/GC/latency trong budget?
- Logs/traces vẫn redacted, không lộ secrets?
- Canary, alert thresholds, rollback binary/config/key đã diễn tập?

## 14. Bài tập vận dụng

**Bài 1.** Một ứng dụng resolve được Spring-WS version mới nhưng không tìm thấy release matrix xác nhận Framework/Boot combination. Vì sao “Maven build pass” chưa đủ để nâng production?

**Bài 2.** Boot BOM nâng Spring Framework và JAXB transitive versions. Hãy nêu các artifacts cần kiểm ngoài dependency khai báo trực tiếp.

**Bài 3.** Dự án có generated classes dùng `javax.xml.bind.annotation`, nhưng runtime mới cung cấp Jakarta JAXB. Có thể chỉ thêm cả hai API JAR để khắc phục không? Giải thích.

**Bài 4.** Sau khi đổi JDK, HTTPS call tới partner thành công nhưng WS-Security signature bị reject. Hãy phân tách các lớp cần điều tra.

**Bài 5.** Dependency tree hiển thị WSS4J và Santuario đã bị override. Cần thu thập evidence nào trước khi giữ override đó?

**Bài 6.** Vì sao phải test JAXB generated output với old SOAP fixtures thay vì chỉ assert Java model compile?

**Bài 7.** Thiết kế regression matrix cho UsernameToken PasswordDigest, X.509 signature, XML encryption và timestamp sau nâng WSS4J.

**Bài 8.** Một partner dùng thuật toán chữ ký cũ bị JDK security policy mới từ chối. Nêu quy trình xử lý an toàn thay vì hạ disabled algorithms toàn JVM.

**Bài 9.** Khi nào nên giữ SAAJ/Axiom provider hiện tại dù Spring-WS được nâng cấp? Những compatibility evidence nào cần có?

**Bài 10.** Đề xuất Maven/Gradle checks để tìm duplicate Spring modules, JAXB providers và XML security versions.

**Bài 11.** Một migration làm thay đổi keystore format và alias. Vì sao rollback chỉ bằng cách redeploy image cũ có thể thất bại?

**Bài 12.** Lập thứ tự canary rollout cho SOAP server có ba partner Java/.NET và WS-Security certificate riêng.

**Bài 13.** Phân biệt binary compatibility, source compatibility, wire compatibility và operational compatibility qua ví dụ SOAP.

**Bài 14.** Một signature valid test pass, nhưng tampered Body cũng được endpoint chấp nhận. Điều gì cần dừng ngay và test nào còn thiếu?

**Bài 15.** Tạo một compatibility matrix có cột Current, Target, Evidence, Owner, Gate và Rollback trigger cho một dự án Spring-WS bạn biết.

### Gợi ý trả lời cốt lõi

- **1–2:** Cần upstream compatibility evidence và resolved dependency diff, không chỉ khả năng tải/compile.
- **3:** Hai namespace là hai type khác nhau; align generated sources, API và runtime, không trộn tùy tiện.
- **4–5:** Kiểm TLS/JDK và WSS4J/Santuario/XML Signature riêng; override cần upstream guidance, tests và rationale.
- **6–7:** Generated model/QName/presence và WS-Security actions là wire behavior, cần golden/interoperability fixtures.
- **8–9:** Security owner/vendor/partner cần thống nhất thuật toán thay thế; provider change phải có matrix/test riêng.
- **10–12:** Dependency insight/tree, provider discovery, artifact rollback, canary theo partner cohort.
- **13–15:** Kiểm source/API, XML wire payload, runtime/provider/security và vận hành độc lập; matrix phải gắn evidence với gate.

## Tài liệu tham khảo

- [Spring Boot Reference Documentation](https://docs.spring.io/spring-boot/reference/) — system requirements, dependency management, build systems và migration guides.
- [Spring Boot Supported Versions](https://spring.io/projects/spring-boot) — release lines và support lifecycle của Boot.
- [Spring Framework Reference](https://docs.spring.io/spring-framework/reference/) — framework requirements, Jakarta baseline và upgrade guidance.
- [Spring Web Services Reference 4.1.x](https://docs.spring.io/spring-ws/docs/4.1.4/reference/html/) — Spring-WS configuration, message factories, SOAP clients, endpoints và WS-Security integration.
- [Apache WSS4J](https://ws.apache.org/wss4j/) — supported versions, configuration và WS-Security actions.
- [Apache Santuario XML Security for Java](https://santuario.apache.org/javaindex.html) — XML Signature/Encryption implementation và release information.
- [Jakarta XML Binding](https://jakarta.ee/specifications/xml-binding/) — JAXB API/specification, providers và generated binding model.
- [Jakarta SOAP with Attachments](https://jakarta.ee/specifications/soap-attachments/) — SAAJ API và release information.
- [Apache Axiom](https://ws.apache.org/axiom/) — SOAP/XML object model và streaming support.
- [Maven Dependency Plugin](https://maven.apache.org/plugins/maven-dependency-plugin/) — dependency tree và dependency analysis.
- [Gradle Dependency Management](https://docs.gradle.org/current/userguide/dependency_management.html) — platforms, constraints và dependency insight.
- [OWASP Transport Layer Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Transport_Layer_Security_Cheat_Sheet.html) — TLS protocol/certificate configuration.

**Ghi nhớ:** nâng cấp SOAP stack là thay đổi của một dependency graph, không phải thay một version đơn lẻ. Chọn release train được hỗ trợ, chốt JDK và namespace, giữ Spring Boot BOM nhất quán, xem WSS4J/Santuario cùng nhau, pin JAXB/provider và kiểm chứng bằng SOAP wire fixtures, partner clients, TLS và security negative tests. Chỉ rollout khi có evidence, metrics và rollback đã diễn tập.
