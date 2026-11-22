# Mô hình đe dọa

## 1. Mô hình đe dọa là gì?

Mô hình đe dọa (threat modeling) là quy trình có cấu trúc để nhận diện tài sản cần bảo vệ, xác định tác nhân có thể gây hại, phân tích cách hệ thống có thể bị tấn công và lựa chọn biện pháp giảm thiểu rủi ro. Trong một hệ sinh thái DSL (Domain-Specific Language), mô hình đe dọa giúp nhóm phát triển hiểu những gì có thể xảy ra khi source, plugin, dependency, query, workflow hoặc dữ liệu đầu vào không đáng tin cậy đi qua compiler, workbench và runtime.

DSL thường không chỉ là một parser. Một hệ thống DSL có thể bao gồm:

- Grammar, lexer, parser và semantic analyzer.
- Compiler, interpreter, virtual machine và runtime.
- Plugin IDE, language server, formatter và debugger.
- Build tool, code generator và documentation generator.
- Query engine, workflow engine và connector tới service ngoài.
- Schema registry, package registry và dependency manager.
- Artifact repository, CI/CD pipeline và môi trường triển khai.
- File source, cấu hình, secret, dữ liệu nghiệp vụ và log.

Mỗi thành phần có tài sản, ranh giới tin cậy và bề mặt tấn công riêng. Một lỗi parser có thể gây crash hoặc resource exhaustion; một plugin có thể chạy code với quyền của IDE; một workflow có thể gọi nhầm service hoặc lặp side effect; một query có thể đọc dữ liệu ngoài phạm vi người dùng.

Mô hình đe dọa không phải danh sách lỗ hổng đã được chứng minh và cũng không bảo đảm hệ thống tuyệt đối an toàn. Nó là cách ghi lại giả định, kịch bản tấn công, tác động và quyết định bảo vệ để nhóm có thể ưu tiên công việc bảo mật dựa trên rủi ro.

## 2. Vì sao DSL cần mô hình đe dọa?

DSL thường biến văn bản hoặc cấu hình thành hành vi có thể thực thi. Điều đó tạo ra một ranh giới quan trọng: nội dung trông giống dữ liệu có thể trở thành lệnh, query, workflow hoặc code chạy trong hệ thống.

Ví dụ:

~~~text
workflow refundOrder {
    step loadOrder {
        call orderService.get(orderId)
    }

    step refund {
        call paymentService.refund(orderId)
    }
}
~~~

Nếu người dùng không có quyền tạo refund nhưng có thể sửa workflow và khiến runtime gọi paymentService.refund, vấn đề nằm ở authorization và execution policy, không phải ở cú pháp.

Mô hình đe dọa giúp:

1. Xác định dữ liệu và hành vi quan trọng cần bảo vệ.
2. Phát hiện trust boundary giữa source không tin cậy và compiler/runtime.
3. Nhận diện quyền quá rộng của plugin, worker hoặc connector.
4. Xem xét injection, deserialization, dependency và supply-chain risk.
5. Phân tích tác động của lỗi tới confidentiality, integrity và availability.
6. Chọn kiểm soát phù hợp thay vì chỉ thêm validation rời rạc.
7. Tạo yêu cầu bảo mật có thể kiểm thử.
8. Hỗ trợ review kiến trúc và thay đổi tính năng.
9. Ghi nhận rủi ro còn tồn tại và người chịu trách nhiệm.
10. Tái đánh giá khi grammar, runtime, API hoặc deployment model thay đổi.

Threat modeling có giá trị nhất khi được thực hiện sớm trong thiết kế và cập nhật khi kiến trúc thay đổi, thay vì chỉ làm một lần trước release.

## 3. Phạm vi mô hình hóa

Trước khi phân tích, cần xác định hệ thống nào và luồng nào nằm trong phạm vi.

Một phạm vi có thể gồm:

| Thành phần | Câu hỏi cần xem xét |
|---|---|
| DSL source | Ai tạo, sửa, review và gửi source? |
| Parser/compiler | Input nào được phân tích và quyền của process là gì? |
| Plugin/workbench | Plugin được phép đọc file, gọi network hoặc chạy process nào? |
| Build pipeline | Dependency và script nào được thực thi? |
| Artifact | Ai được tạo, đọc, thay thế hoặc triển khai artifact? |
| Runtime | DSL có thể đọc dữ liệu hoặc gọi chức năng nào? |
| Query engine | Quyền dữ liệu, quota và giới hạn truy vấn được áp dụng ở đâu? |
| Workflow engine | Side effect, retry, event và credential được quản lý thế nào? |
| External service | Dữ liệu nào đi qua connector và trust boundary nào? |
| Operations | Ai xem log, thay policy, deploy và xử lý sự cố? |

Phạm vi cần ghi rõ phần nào do nhóm phát triển kiểm soát, phần nào do nền tảng hoặc nhà cung cấp bên ngoài vận hành, và phần nào được giả định là đáng tin cậy.

Không nên mô hình hóa một hệ thống quá rộng đến mức mọi thứ đều trở thành tài sản và mọi người đều là attacker. Chọn một use case cụ thể, ví dụ "người dùng gửi DSL workflow để chạy trong tenant của mình", sau đó mở rộng dần theo các luồng liên quan.

## 4. Xác định tài sản cần bảo vệ

Asset là dữ liệu, chức năng hoặc thuộc tính hệ thống có giá trị và có thể bị ảnh hưởng bởi một mối đe dọa.

Trong DSL, tài sản có thể gồm:

### 4.1. Tài sản dữ liệu

- Source code và business rule độc quyền.
- Schema, metadata và cấu trúc dữ liệu.
- Dữ liệu khách hàng hoặc dữ liệu cá nhân.
- Secret, API key, certificate và credential.
- Query result, event history và workflow state.
- Build artifact, package và generated code.
- Log, trace và audit record.

### 4.2. Tài sản thực thi

- Tính toàn vẹn của compiler và runtime.
- Quyền gọi function hoặc connector.
- Quyền đọc/ghi database.
- Khả năng khởi chạy workflow hoặc job.
- Tính chính xác của policy và authorization.
- Tính sẵn sàng của editor, build service và runtime.

### 4.3. Tài sản chuỗi cung ứng

- Compiler, plugin và dependency đã được phê duyệt.
- Build script và CI credential.
- Package signing key.
- Artifact registry.
- Provenance, checksum và release manifest.

### 4.4. Tài sản vận hành

- Khả năng khôi phục workflow.
- Tính chính xác của audit trail.
- Quota và capacity của worker.
- Cấu hình bảo mật và policy version.
- Khả năng tái lập build và deployment.

Mỗi asset nên có owner, mức độ nhạy cảm, yêu cầu integrity/availability và nơi nó được lưu hoặc xử lý. Điều này giúp xác định tác động nếu asset bị đọc, sửa, xóa hoặc làm gián đoạn.

## 5. Xác định tác nhân và mức độ tin cậy

Threat actor là người hoặc tiến trình có khả năng tạo ra hành động gây hại, cố ý hoặc vô ý.

Các tác nhân có thể liên quan tới DSL:

- Developer hoặc author có quyền tạo DSL.
- Người dùng cuối gửi query hoặc workflow.
- Người dùng nội bộ có quyền rộng hơn mức cần thiết.
- Tenant khác cố truy cập dữ liệu ngoài phạm vi.
- Attacker từ bên ngoài khai thác endpoint hoặc package.
- Plugin hoặc dependency bị xâm nhập.
- Service account bị lộ credential.
- Build worker hoặc runner bị chiếm quyền.
- Operator cấu hình sai policy.
- External service trả dữ liệu không hợp lệ hoặc độc hại.

Không phải mọi tác nhân đều là người xấu. Lỗi cấu hình, dependency bị xâm nhập hoặc dữ liệu bất thường cũng có thể tạo ra threat scenario.

### 5.1. Trust level

Có thể phân loại nguồn đầu vào:

| Nguồn | Mức tin cậy mặc định |
|---|---|
| DSL source do người dùng gửi | Không tin cậy |
| Query parameter | Không tin cậy |
| File import từ bên ngoài | Không tin cậy |
| Plugin bên thứ ba | Không tin cậy cho tới khi được xác minh và sandbox |
| Dependency đã pin và xác minh | Tin cậy có điều kiện |
| Identity từ authentication provider | Tin cậy sau khi xác minh |
| Policy do owner có quyền quản lý | Tin cậy có điều kiện và cần audit |
| Database result | Phải kiểm tra schema và quyền |
| External API response | Không tin cậy cho tới khi validate |
| Compiler/runtime artifact đã xác minh | Tin cậy theo provenance và quy trình phát hành |

Trust không phải thuộc tính tuyệt đối. Một source nội bộ vẫn có thể chứa lỗi hoặc bị sửa trái phép; một package có checksum đúng vẫn có thể độc hại nếu nguồn phát hành bị xâm nhập.

## 6. Trust boundary

Trust boundary là ranh giới mà dữ liệu hoặc quyền đi từ miền tin cậy này sang miền khác. Khi đi qua boundary, hệ thống cần xác thực, kiểm tra, giới hạn hoặc chuyển đổi dữ liệu phù hợp.

Ví dụ tổng quát:

~~~mermaid
flowchart LR
    U["User / IDE"] -->|"DSL source"| G["API Gateway"]
    G -->|"authenticated request"| C["Compiler Service"]
    C -->|"validated artifact"| R["Artifact Registry"]
    R -->|"verified package"| W["Workflow Runtime"]
    W -->|"authorized call"| S["External Services"]
    W --> D["Database"]
~~~

Các boundary quan trọng:

- User workstation tới API gateway.
- Editor/plugin tới language server.
- Source file tới parser/compiler.
- Build worker tới package registry.
- Compiler tới artifact repository.
- Artifact repository tới runtime.
- Runtime tới database hoặc external service.
- Tenant boundary trong shared infrastructure.
- Admin console tới policy store.

### 6.1. Vì sao boundary quan trọng?

Một hệ thống có thể validate source ở editor nhưng người dùng vẫn có thể gửi request trực tiếp tới compiler API. Nếu compiler service tin rằng mọi source đã được editor kiểm tra, boundary này có thể bị vượt qua.

Mọi kiểm soát quan trọng phải được thực hiện tại điểm có thẩm quyền. Client validation giúp trải nghiệm tốt hơn; server-side validation và authorization bảo vệ hệ thống.

### 6.2. Luồng dữ liệu qua boundary

Với mỗi luồng, ghi:

- Dữ liệu nào đi qua?
- Ai tạo dữ liệu?
- Có thể sửa dữ liệu trên đường truyền không?
- Có xác thực và mã hóa không?
- Bên nhận kiểm tra gì?
- Có lưu dữ liệu sau khi nhận không?
- Có log nội dung hoặc secret không?

## 7. Attack surface của hệ sinh thái DSL

Attack surface là tập hợp điểm mà tác nhân có thể gửi input, gọi chức năng hoặc tác động tới hệ thống.

### 7.1. Parser và compiler

- Source file quá lớn hoặc lồng cấu trúc quá sâu.
- Token hoặc literal gây parser pathological behavior.
- Integer overflow trong source range hoặc constant evaluation.
- Parser recovery làm sai cấu trúc.
- Compiler plugin hoặc macro chạy code không tin cậy.
- Import path truy cập file ngoài workspace.

### 7.2. IDE và language server

- Plugin có quyền đọc workspace hoặc clipboard.
- Language server xử lý file độc hại.
- Completion hoặc hover tiết lộ metadata nhạy cảm.
- File watcher theo dõi path ngoài phạm vi.
- Debug adapter mở cổng hoặc chạy process.

### 7.3. Build và package

- Dependency confusion hoặc typosquatting.
- Build script chạy command tùy ý.
- Package bị thay nội dung.
- Credential bị lộ trong log.
- Artifact bị thay thế sau khi build.
- CI runner dùng lại state không an toàn.

### 7.4. Runtime và workflow

- DSL gọi function không được phép.
- Expression gây CPU/memory exhaustion.
- Workflow tạo side effect không được phép.
- Retry gây lặp giao dịch.
- Deserialization dữ liệu không tin cậy.
- Event giả mạo hoặc replay.

### 7.5. Query engine và data connector

- SQL/command injection.
- Truy cập field hoặc row ngoài quyền.
- Tenant isolation bị bỏ qua trong join/subquery/cache.
- Query tốn kém gây denial of service.
- Connector dùng credential quá rộng.
- External response chứa dữ liệu sai định dạng.

### 7.6. API và operations

- Authentication hoặc authorization bị thiếu.
- Admin endpoint lộ ra ngoài.
- Policy update không được audit.
- Log chứa token hoặc dữ liệu cá nhân.
- Backup và artifact storage có quyền truy cập quá rộng.

## 8. STRIDE

STRIDE là phương pháp phân loại threat theo sáu nhóm. Nó hữu ích để rà soát từng thành phần và luồng dữ liệu.

| Nhóm | Ý nghĩa | Ví dụ trong DSL |
|---|---|---|
| Spoofing | Giả mạo danh tính | Workflow giả service identity hoặc giả tenant |
| Tampering | Sửa đổi trái phép | Thay DSL artifact sau khi ký |
| Repudiation | Chối bỏ hành động | Không có audit xác định ai đã chạy rule |
| Information Disclosure | Tiết lộ thông tin | Query đọc field nhạy cảm hoặc log lộ token |
| Denial of Service | Từ chối dịch vụ | Parser hoặc query gây CPU exhaustion |
| Elevation of Privilege | Nâng quyền | Plugin hoặc DSL gọi function admin |

STRIDE không phải checklist bảo đảm đầy đủ. Nó là cách gợi ý câu hỏi cho từng boundary và thành phần.

### 8.1. Spoofing

Kẻ tấn công giả danh user, service, package publisher hoặc workflow event.

Biện pháp có thể gồm:

- Xác thực bằng identity provider.
- Token có audience, expiry và scope rõ ràng.
- Mutual TLS cho service-to-service khi phù hợp.
- Xác minh chữ ký artifact.
- Không tin principal hoặc tenant do client tự khai báo.
- Correlation ID và event signature cho message nhạy cảm.

### 8.2. Tampering

Kẻ tấn công sửa source, policy, dependency, artifact hoặc dữ liệu workflow.

Biện pháp:

- Version control và review.
- Artifact checksum và signature.
- Immutable registry hoặc retention policy.
- Integrity check cho lockfile và manifest.
- Authorization khi cập nhật policy.
- Audit thay đổi và source provenance.

### 8.3. Repudiation

Người dùng hoặc service phủ nhận đã thực hiện hành động.

Biện pháp:

- Audit log có principal và request ID.
- Timestamp từ nguồn thời gian tin cậy.
- Ghi policy version và artifact digest.
- Bảo vệ log khỏi sửa/xóa trái phép.
- Đồng bộ trace và event history.

### 8.4. Information Disclosure

Dữ liệu hoặc metadata bị đọc bởi người không có quyền.

Biện pháp:

- Least privilege.
- Row/column-level security.
- Tenant isolation.
- Secret manager.
- Encryption in transit và at rest.
- Masking và data minimization.
- Kiểm soát completion, hover và diagnostic.

### 8.5. Denial of Service

Attacker làm cạn CPU, memory, thread, connection, queue hoặc storage.

Biện pháp:

- Input size và nesting limits.
- Parser/regex complexity limits.
- Query timeout và cost budget.
- Worker concurrency limits.
- Rate limiting và queue quotas.
- Cancellation và backpressure.
- Circuit breaker và bulkhead.

### 8.6. Elevation of Privilege

Một principal có quyền thấp đạt được quyền cao hơn qua plugin, function, workflow, policy hoặc connector.

Biện pháp:

- Authorization ở server/runtime.
- Capability allowlist.
- Sandbox và process isolation.
- Không chạy DSL bằng quyền admin mặc định.
- Kiểm tra quyền xuyên suốt subquery và workflow.
- Tách quyền quản lý policy khỏi quyền thực thi.

## 9. Threat scenario và attack path

Threat scenario mô tả cụ thể cách một tác nhân có thể khai thác một điểm yếu để ảnh hưởng tài sản.

Một scenario nên ghi:

- Actor.
- Asset mục tiêu.
- Entry point.
- Preconditions.
- Các bước tấn công.
- Trust boundary bị vượt qua.
- Tác động.
- Kiểm soát hiện có.
- Biện pháp bổ sung.
- Cách kiểm chứng.

Ví dụ:

~~~text
Scenario: Cross-tenant data access

Actor:
  authenticated user from tenant A

Entry point:
  query API

Attack path:
  1. Submit query against Orders.
  2. Add a predicate selecting tenant B.
  3. Exploit missing server-side tenant filter.
  4. Read records belonging to tenant B.

Impact:
  confidentiality breach across tenants

Mitigation:
  inject tenant policy from authenticated context;
  enforce row-level security at the data source;
  test joins, views, cache and exports.
~~~

### 9.1. Attack tree

Attack tree phân rã mục tiêu tấn công thành các cách thực hiện:

~~~mermaid
flowchart TD
    A["Đọc dữ liệu tenant khác"] --> B["Giả mạo tenant context"]
    A --> C["Bỏ qua row policy"]
    A --> D["Lấy kết quả từ cache sai scope"]
    B --> E["Tin tenant ID do client gửi"]
    C --> F["Policy không áp dụng trong subquery"]
    D --> G["Cache key thiếu tenant/policy version"]
~~~

Attack tree giúp nhóm tìm nhiều đường tấn công cho cùng một mục tiêu thay vì chỉ sửa điểm yếu đầu tiên được phát hiện.

## 10. Đánh giá rủi ro

Không phải mọi threat đều có mức ưu tiên giống nhau. Risk assessment ước lượng khả năng xảy ra và tác động để chọn thứ tự xử lý.

Một mô hình đơn giản:

~~~text
risk = likelihood × impact
~~~

Có thể chấm mỗi yếu tố từ 1 đến 5:

| Điểm | Likelihood | Impact |
|---|---|---|
| 1 | Hiếm, cần điều kiện khó | Ảnh hưởng nhỏ, dễ phục hồi |
| 2 | Ít có khả năng | Ảnh hưởng giới hạn |
| 3 | Có thể xảy ra | Ảnh hưởng đáng kể |
| 4 | Dễ xảy ra trong điều kiện thực tế | Ảnh hưởng lớn hoặc nhiều người dùng |
| 5 | Rất dễ khai thác hoặc đã quan sát | Ảnh hưởng nghiêm trọng, lan rộng |

Ví dụ risk score 4 × 5 = 20 có thể được ưu tiên cao hơn 1 × 2 = 2. Đây chỉ là công cụ sắp xếp; nhóm cần ghi rõ giả định và không xem con số là phép đo chính xác tuyệt đối.

### 10.1. Các yếu tố đánh giá

- Mức dễ khai thác.
- Yêu cầu quyền ban đầu.
- Mức độ phức tạp của attack path.
- Số tenant hoặc người dùng bị ảnh hưởng.
- Độ nhạy cảm của dữ liệu.
- Khả năng sửa đổi hoặc xóa dữ liệu.
- Thời gian phát hiện.
- Khả năng khôi phục.
- Rủi ro pháp lý hoặc vận hành.

### 10.2. Residual risk

Sau khi áp dụng kiểm soát, vẫn có thể còn rủi ro. Residual risk cần được ghi nhận cùng lý do chấp nhận, owner, biện pháp theo dõi và thời điểm đánh giá lại.

Không nên đánh dấu threat "đã xử lý" chỉ vì có một kiểm soát trên giấy. Cần xác định kiểm soát có được triển khai, bật trong môi trường thực tế và kiểm thử hay không.

## 11. STRIDE theo thành phần DSL

Có thể áp dụng STRIDE theo từng lớp:

| Thành phần | Threat đáng chú ý |
|---|---|
| Parser/compiler | DoS, tampering, path traversal, parser confusion |
| Plugin/workbench | Spoofing extension, privilege escalation, data disclosure |
| Build pipeline | Dependency tampering, credential theft, malicious build script |
| Artifact registry | Package replacement, unauthorized download, repudiation |
| Runtime | Arbitrary code execution, privilege escalation, resource exhaustion |
| Query engine | Injection, data disclosure, tenant bypass, expensive query |
| Workflow engine | Forged event, duplicate side effect, unauthorized action |
| Admin/policy service | Unauthorized policy change, audit tampering |
| Observability | Secret leakage, log tampering, excessive data retention |

Một threat có thể xuất hiện ở nhiều lớp. Ví dụ, spoofing có thể xảy ra ở API gateway, message broker hoặc connector; cần xác định nơi identity được tạo và nơi nó được xác minh.

## 12. Bảo vệ parser và compiler

Parser nhận input có thể do người dùng kiểm soát. Dù parser không thực thi source, lỗi xử lý input vẫn có thể gây crash, treo hoặc tạo AST sai.

Các threat:

- File cực lớn hoặc token cực dài.
- Nested expression sâu gây stack overflow.
- Regex có catastrophic backtracking.
- Integer literal hoặc constant expression gây overflow.
- Unicode normalization tạo tên nhìn giống nhau.
- Parser recovery làm mất ranh giới cú pháp.
- Import path đọc file ngoài workspace.
- Macro hoặc compile-time function thực thi code.

Biện pháp:

1. Giới hạn kích thước file, token và nesting depth.
2. Dùng parser có complexity được hiểu rõ.
3. Tránh regex backtracking không giới hạn.
4. Kiểm tra overflow và allocation size.
5. Chuẩn hóa và xử lý identifier Unicode theo policy.
6. Giữ parser error recovery an toàn.
7. Giới hạn import root và kiểm tra canonical path.
8. Chạy compile-time plugin trong sandbox nếu có thể thực thi code.
9. Có timeout và cancellation cho parse/compile request.
10. Fuzz parser và serializer bằng input bất thường.

### 12.1. Path traversal qua import

Một DSL có thể cho phép:

~~~text
import "./shared/types.dsl";
~~~

Nếu import path được ghép trực tiếp với workspace root mà không kiểm tra canonical path, attacker có thể thử đường dẫn như ../../secrets/config. Engine cần resolve symlink, normalize path và xác nhận file cuối cùng nằm trong allowlisted root.

### 12.2. Compile-time execution

Macro hoặc annotation processor có thể chạy trong lúc build. Nếu nó có quyền đọc file, network và environment của CI, dependency độc hại có thể đánh cắp credential.

Nên tách compile-time capability, chạy trong sandbox và chỉ cấp quyền cần thiết. Build từ pull request không tin cậy không nên nhận secret phát hành.

## 13. Bảo vệ interpreter và runtime

Runtime thực thi logic từ DSL nên cần kiểm soát rõ quyền và tài nguyên.

Threat scenario:

- DSL gọi function không được phép.
- Expression lặp vô hạn hoặc recursion sâu.
- Object graph lớn làm cạn memory.
- Reflection hoặc dynamic loading truy cập class nội bộ.
- File/network access vượt sandbox.
- Deserialization kích hoạt gadget hoặc object nguy hiểm.
- Error message tiết lộ path, secret hoặc internal state.

Biện pháp:

- Capability-based function registry.
- Allowlist operator và built-in.
- Execution timeout và cancellation.
- CPU, memory và recursion limits.
- Giới hạn collection, string và object size.
- Tắt reflection/dynamic loading nếu không cần.
- Schema validation trước deserialization.
- Không deserialize native object graph từ nguồn không tin cậy nếu không có cơ chế an toàn.
- Mask thông tin nhạy cảm trong error và log.

### 13.1. Sandbox

Sandbox có thể giới hạn:

- Filesystem access.
- Network access.
- Process creation.
- Environment variables.
- Runtime reflection.
- Memory và CPU.
- Function và connector capability.

Sandbox cần được kiểm tra từ bên ngoài; không nên chỉ dựa vào lời hứa của DSL source rằng chương trình sẽ không truy cập tài nguyên.

### 13.2. Defense in depth

Nếu runtime allowlist một function, service đích vẫn cần authorization. Nếu sandbox giới hạn network, network policy cũng nên giới hạn egress. Nhiều lớp kiểm soát giúp giảm tác động khi một lớp cấu hình sai.

## 14. Bảo vệ query DSL và dữ liệu

Query DSL có thể biến biểu thức thành truy vấn tới database, search engine hoặc service.

Threats:

- Injection do nối chuỗi.
- Đọc row hoặc field ngoài quyền.
- Tenant isolation bị bỏ qua.
- Query scan quá lớn.
- Join hoặc recursion gây resource exhaustion.
- Side channel qua count, sort hoặc aggregation.
- Cache trả dữ liệu của principal khác.
- Schema discovery tiết lộ metadata.

Biện pháp:

1. Parameter binding thay cho string concatenation.
2. Authorization trên source, action và field.
3. Row-level và column-level policy.
4. Tenant context từ identity provider.
5. Query cost budget, timeout và result limit.
6. Cache key có security scope và policy version.
7. Hạn chế function và backend capability.
8. Audit query nhạy cảm.
9. Kiểm soát export và chia sẻ kết quả.
10. Kiểm thử join, subquery, view và aggregate.

Không nên dựa vào filter do client tự thêm để cô lập dữ liệu. Policy phải được áp dụng ở server hoặc backend tin cậy.

## 15. Bảo vệ workflow DSL và side effect

Workflow DSL có thể gọi API, tạo giao dịch, gửi message hoặc thay đổi trạng thái bên ngoài.

Threats:

- Workflow giả mạo event hoặc correlation ID.
- Caller gọi activity không được cấp quyền.
- Retry tạo side effect trùng.
- Replay event kích hoạt hành động lần nữa.
- Secret bị ghi vào workflow state hoặc log.
- Workflow bị sửa sau khi được phê duyệt.
- Timeout/cancellation bị hiểu nhầm là rollback.
- Worker nhận task của tenant khác.

Biện pháp:

- Authentication cho event và service call.
- Authorization theo activity/capability.
- Idempotency key cho side effect.
- Event schema validation và signature khi cần.
- Version và integrity của workflow artifact.
- Tenant context được truyền xuyên suốt.
- Secret reference thay cho secret literal.
- Audit state transition và activity execution.
- Deadline, retry budget và compensation rõ ràng.
- Worker queue phân vùng hoặc xác minh tenant.

Workflow definition nên được coi là executable policy. Quyền sửa và deploy workflow có thể ảnh hưởng trực tiếp đến tiền, dữ liệu hoặc quy trình vận hành, vì vậy cần review và kiểm soát release.

## 16. Bảo vệ plugin, extension và language server

Plugin có thể chạy trong process IDE hoặc workbench với quyền truy cập rộng. Language server có thể đọc source, workspace file, schema và metadata.

Threats:

- Plugin độc hại đọc file hoặc credential.
- Extension tự tải executable không xác minh.
- Language server theo dõi path ngoài workspace.
- Completion/hover tiết lộ symbol hoặc schema private.
- Debug adapter mở port không được bảo vệ.
- Plugin dùng dependency bị xâm nhập.
- Protocol message kích hoạt parser lỗi hoặc resource exhaustion.

Biện pháp:

- Chỉ cài extension từ nguồn được phê duyệt.
- Xác minh publisher, signature và version.
- Khai báo quyền plugin và giới hạn capability.
- Tách process nếu cần.
- Giới hạn file watcher và workspace root.
- Xác thực debug endpoint.
- Không gửi secret vào language server nếu không cần.
- Kiểm tra quyền metadata trước completion.
- Khóa dependency và kiểm soát update channel.

Plugin nên được xem là code có thể thực thi trong môi trường developer, không phải chỉ là giao diện trang trí.

## 17. Bảo vệ build pipeline và supply chain

Build pipeline thường có quyền truy cập source, package registry, signing key và deployment credential. Một dependency hoặc build script bị xâm nhập có thể ảnh hưởng toàn bộ release.

Threats:

- Dependency confusion hoặc typosquatting.
- Package bị thay nội dung.
- Build plugin chạy lệnh độc hại.
- CI secret bị đọc từ log hoặc environment.
- Artifact bị thay sau khi build.
- Cache poisoning.
- Untrusted pull request chạy trong runner có secret.
- Signing key bị lộ.

Biện pháp:

1. Pin version và checksum.
2. Dùng registry tin cậy và namespace rõ ràng.
3. Xác minh signature/provenance khi có.
4. Tách runner cho pull request không tin cậy.
5. Không cấp secret phát hành cho build không được phê duyệt.
6. Giới hạn quyền và network của build process.
7. Bảo vệ signing key bằng secret manager hoặc signing service.
8. Tạo SBOM và provenance.
9. Dùng artifact registry có kiểm soát truy cập.
10. Kiểm tra cache key và output integrity.

## 18. Bảo vệ serialization và artifact format

DSL có thể serialize AST, IR, workflow state hoặc compiled bundle để lưu trữ và trao đổi.

Threats:

- Input quá lớn gây memory exhaustion.
- Length field hoặc nesting depth gây allocation bất thường.
- Schema confusion hoặc type confusion.
- Native deserialization kích hoạt constructor hoặc gadget nguy hiểm.
- Artifact bị sửa để thay đổi code hoặc policy.
- Version downgrade hoặc replay artifact cũ.

Biện pháp:

- Dùng format có schema và parser được duy trì.
- Giới hạn kích thước, depth và số phần tử.
- Validate version, type và invariant.
- Tránh native object deserialization từ nguồn không tin cậy.
- Ký hoặc hash artifact theo trust model.
- Kiểm tra signature và version trước load.
- Không tin metadata chỉ vì nó nằm trong artifact.
- Tách data serialization khỏi executable artifact khi có thể.

## 19. Bảo vệ secret và credential

DSL có thể cần credential để gọi database hoặc service. Secret không nên được ghi trực tiếp trong source:

~~~text
connector payment {
    endpoint: "https://payments.example"
    credential: secretRef("payment-api-key")
}
~~~

Runtime lấy secret từ secret manager theo identity của workload. Source chỉ giữ reference và không chứa giá trị bí mật.

Các nguyên tắc:

- Least privilege cho credential.
- Secret rotation và expiry.
- Không in secret vào error hoặc debug output.
- Không serialize secret vào workflow history nếu không cần.
- Mask parameter trong tracing.
- Tách secret theo môi trường và tenant.
- Giới hạn ai có quyền đọc secret reference hoặc thay binding.
- Không truyền credential qua command line nếu dễ lộ trong process list.

## 20. Logging, tracing và audit

Observability có thể trở thành một bề mặt rò rỉ dữ liệu. DSL source, query parameter, workflow payload và stack trace có thể chứa thông tin nhạy cảm.

Log nên ưu tiên:

- Request ID và correlation ID.
- Principal hoặc service identity đã được xác minh.
- Artifact/workflow version.
- Policy decision.
- Error code và source location.
- Duration và resource usage.
- Dependency identity.

Tránh ghi:

- Token, password và API key.
- Full query result nhạy cảm.
- Personal data không cần thiết.
- Secret trong environment.
- Payload đầy đủ khi chỉ cần hash hoặc metadata.

Audit log cần có retention và access policy riêng. Người có quyền đọc dữ liệu nghiệp vụ không nhất thiết có quyền sửa audit record.

## 21. Security requirements và control mapping

Sau khi nhận diện threat, chuyển chúng thành yêu cầu có thể triển khai và kiểm thử.

| Threat | Yêu cầu bảo vệ | Cách xác minh |
|---|---|---|
| Tenant spoofing | Tenant lấy từ authenticated context | Thử sửa tenant trong query |
| Query injection | Parameter binding | Fuzz parameter với cú pháp đặc biệt |
| Parser DoS | Input/depth/time limits | Stress và fuzz test |
| Plugin privilege escalation | Capability allowlist/sandbox | Kiểm tra quyền process và filesystem |
| Artifact tampering | Signature/digest verification | Sửa artifact và xác nhận bị từ chối |
| Secret disclosure | Secret manager và log masking | Scan log/output với test secret |
| Workflow replay | Idempotency và event validation | Gửi duplicate event |
| Dependency compromise | Lockfile/checksum/provenance | Thay package content và xác nhận fail |

Mỗi requirement nên có:

- ID duy nhất.
- Threat hoặc risk liên quan.
- Owner.
- Thành phần áp dụng.
- Trạng thái triển khai.
- Test hoặc bằng chứng xác minh.
- Residual risk.

## 22. Secure-by-design và defense in depth

Mô hình đe dọa nên dẫn tới quyết định kiến trúc, không chỉ tạo danh sách rủi ro.

Các nguyên tắc thiết kế:

### 22.1. Least privilege

Mỗi process, plugin, worker và service chỉ có quyền cần thiết. Compiler không cần database production credential; formatter không cần network access; query worker không cần quyền sửa policy.

### 22.2. Secure defaults

Nếu không có policy hoặc capability rõ ràng, hành vi mặc định nên từ chối thao tác nhạy cảm. Cấu hình an toàn nên là mặc định thay vì yêu cầu người dùng nhớ bật từng kiểm soát.

### 22.3. Validate at trust boundaries

Kiểm tra input ở server và data source, không chỉ trong editor. Validate schema, size, type, encoding, identity và authorization.

### 22.4. Fail safely

Nếu authorization service, signature verification hoặc policy store không khả dụng, cần hành vi được định nghĩa. Không tự động cấp quyền chỉ vì một thành phần bảo mật bị lỗi.

### 22.5. Minimize attack surface

Không export function, endpoint, plugin API hoặc built-in không cần thiết. Tắt dynamic loading và network capability nếu use case không yêu cầu.

### 22.6. Defense in depth

Kết hợp kiểm soát ở gateway, compiler, runtime, database, operating system và deployment. Không một lớp nào được giả định là đủ.

## 23. Fuzzing và kiểm thử bảo mật

Threat model cần được chuyển thành kiểm thử có thể chạy lặp lại.

### 23.1. Parser fuzzing

Sinh input ngẫu nhiên hoặc mutation từ DSL hợp lệ để tìm crash, hang, stack overflow, assertion failure và parser state corruption.

### 23.2. Property-based testing

Kiểm tra các thuộc tính như:

- Parse/format/parse giữ semantics.
- Serializer round-trip không làm mất dữ liệu hợp lệ.
- Giới hạn input luôn được tôn trọng.
- Policy filter không thể bị bỏ qua qua rewrite.
- Query plan sau optimization giữ kết quả theo contract.

### 23.3. Authorization negative tests

Tạo principal thiếu quyền và xác nhận mọi đường truy cập đều bị từ chối: source trực tiếp, join, subquery, view, export, cache và background task.

### 23.4. Sandbox escape tests

Thử truy cập file ngoài workspace, mở network connection, tạo process hoặc đọc environment variable ngoài allowlist.

### 23.5. Supply-chain tests

Kiểm tra package signature, checksum, provenance và lockfile. Thử package không đúng digest hoặc nguồn không được phép.

### 23.6. Abuse/load tests

Thử file lớn, query tốn kém, recursion, concurrency cao, message flood và retry storm. Xác nhận timeout, quota và cancellation hoạt động.

Kiểm thử nên chạy trong môi trường cô lập và dùng dữ liệu giả lập. Không thực hiện fuzzing hoặc load test phá hoại trên production.

## 24. Quy trình threat modeling

Một quy trình thực tế có thể gồm:

1. **Chọn use case và phạm vi.** Xác định luồng DSL cụ thể cần phân tích.
2. **Vẽ kiến trúc và data flow.** Ghi process, storage, external service và trust boundary.
3. **Liệt kê tài sản.** Phân loại dữ liệu, chức năng, credential và yêu cầu bảo mật.
4. **Xác định actor.** Bao gồm người dùng, service, dependency và lỗi vận hành.
5. **Tìm entry point.** API, file import, plugin, package, event, query và admin endpoint.
6. **Áp dụng STRIDE.** Xem xét từng thành phần và luồng.
7. **Viết threat scenario.** Mô tả attack path và tác động cụ thể.
8. **Ước lượng risk.** Đánh giá likelihood, impact và giả định.
9. **Chọn mitigation.** Gắn kiểm soát với threat và enforcement point.
10. **Tạo security requirement.** Xác định owner và test evidence.
11. **Ghi residual risk.** Nêu phần chưa xử lý và lý do chấp nhận.
12. **Cập nhật mô hình.** Rà soát khi kiến trúc, dependency hoặc use case thay đổi.

### 24.1. Người tham gia

Threat modeling thường hiệu quả khi có:

- Architect hoặc người hiểu kiến trúc.
- Developer compiler/runtime.
- Người phụ trách data/security.
- DevOps hoặc platform engineer.
- Product/domain owner.
- Người vận hành workflow hoặc query.

Không cần mọi vai trò tham gia mọi buổi. Cần có đủ hiểu biết về data flow, quyền và hành vi nghiệp vụ trong phạm vi được xem xét.

### 24.2. Artifact đầu ra

Một threat model có thể lưu:

- Architecture/data-flow diagram.
- Asset inventory.
- Actor và trust assumptions.
- Threat register.
- Risk ranking.
- Mitigation/control mapping.
- Security requirements.
- Test evidence.
- Residual risk và owner.

## 25. Ví dụ threat register

Một bảng threat register đơn giản:

| ID | Threat scenario | Impact | Mitigation | Verification |
|---|---|---|---|---|
| T-01 | Query truy cập tenant khác | Data disclosure | Server-side tenant policy | Cross-tenant test |
| T-02 | Parser input gây treo | Availability | Size/depth/time limits | Fuzz and stress test |
| T-03 | Plugin đọc secret local | Credential theft | Process isolation, least privilege | Sandbox test |
| T-04 | Artifact bị thay sau build | Integrity compromise | Signature and digest | Tampered artifact test |
| T-05 | Workflow retry charge hai lần | Financial impact | Idempotency key | Duplicate request test |
| T-06 | Dependency độc hại vào CI | Supply-chain compromise | Lockfile, provenance, isolated runner | Dependency verification |

Risk score và status có thể được thêm theo quy trình của tổ chức. Không nên dùng bảng này thay cho mô tả attack path; mỗi threat quan trọng cần có chi tiết về precondition và trust boundary.

## 26. Ví dụ end-to-end: threat model cho workflow DSL

Giả sử ứng dụng cho phép khách hàng tạo workflow xử lý đơn hàng. Workflow được gửi qua API, compile thành bundle, lưu vào registry và chạy trên worker. Worker có thể gọi inventory service và payment service.

### 26.1. Data flow

~~~mermaid
flowchart LR
    A["Tenant user"] --> B["Workflow API"]
    B --> C["Compiler service"]
    C --> D["Artifact registry"]
    D --> E["Workflow worker"]
    E --> F["Inventory service"]
    E --> G["Payment service"]
    E --> H["Order database"]
    I["Identity and policy service"] --> B
    I --> E
~~~

Trust boundary nằm giữa tenant user và API, compiler và registry, registry và worker, worker và từng service, cùng ranh giới dữ liệu giữa các tenant.

### 26.2. Assets

- Workflow source và artifact.
- Tenant order data.
- Payment credential.
- Inventory state.
- Workflow execution history.
- Policy và service identity.

### 26.3. Threat scenarios

**T-01: Tenant sửa workflow để gọi payment action ngoài quyền.**

Attacker thêm activity refund hoặc charge vào source. Nếu compiler chỉ kiểm tra cú pháp và runtime cho phép mọi function, workflow có thể thực hiện thao tác tài chính trái phép.

Mitigation: function registry, capability policy, authorization theo tenant và approval cho workflow có side effect.

**T-02: Workflow artifact bị thay sau khi review.**

Attacker thay bundle trong registry trước khi worker tải.

Mitigation: artifact digest, signature, immutable version và worker verification trước load.

**T-03: Duplicate event làm charge hai lần.**

Message được phát lại sau timeout và workflow thực hiện payment activity lần nữa.

Mitigation: event authentication, idempotency key, deduplication và audit state transition.

**T-04: Worker dùng credential quá rộng.**

Một workflow trong tenant A khai thác worker credential để đọc dữ liệu tenant B.

Mitigation: short-lived credential, tenant-scoped capability, row-level policy và network isolation.

**T-05: Workflow gây cạn worker.**

Một workflow tạo loop hoặc task đồng thời không giới hạn.

Mitigation: execution budget, concurrency limit, timeout, cancellation và quota theo tenant.

### 26.4. Security requirements

- Mọi workflow được compile và authorize trước khi deploy.
- Worker chỉ load artifact có digest/signature hợp lệ.
- Mọi activity có side effect yêu cầu capability.
- Tenant context được lấy từ identity đã xác thực.
- Payment operation có idempotency key.
- Workflow có timeout và resource budget.
- Audit ghi actor, artifact version, activity và policy decision.

### 26.5. Verification

- Thử submit workflow gọi activity ngoài allowlist.
- Thử thay artifact sau khi ký.
- Gửi duplicate payment event.
- Thử truy cập order của tenant khác.
- Chạy workflow loop vô hạn và đo resource limit.
- Kiểm tra audit record và secret masking.

Ví dụ cho thấy threat modeling liên kết kiến trúc, hành vi nghiệp vụ, quyền và kiểm thử. Một mitigation cần gắn với điểm thực thi cụ thể, không chỉ nằm trong tài liệu.

## 27. Duy trì threat model theo vòng đời

Threat model sẽ lỗi thời nếu hệ thống thay đổi mà mô hình không được cập nhật.

Nên xem xét lại khi:

- Thêm syntax hoặc feature có thể thực thi code.
- Thêm connector, plugin hoặc dependency.
- Thay authentication hoặc authorization.
- Thay cách lưu artifact hoặc workflow state.
- Mở rộng multi-tenant.
- Thêm backend hoặc external service.
- Thay deployment architecture.
- Có incident hoặc vulnerability mới.
- Thay đổi data classification hoặc compliance requirement.

Có thể gắn threat model review vào architecture review, security review hoặc pull request có thay đổi trust boundary. Không cần viết lại toàn bộ mô hình cho mỗi thay đổi nhỏ; cập nhật phần bị ảnh hưởng và ghi lý do.

## 28. Những lỗi thường gặp khi threat modeling

### Chỉ liệt kê lỗ hổng kỹ thuật

Nhóm tập trung vào parser bug mà bỏ qua quyền workflow, tenant isolation và supply chain. Bắt đầu từ tài sản, actor, data flow và trust boundary để bao quát hệ thống.

### Không xác định phạm vi

Cuộc thảo luận trở nên quá rộng và không tạo ra quyết định. Chọn use case và ranh giới rõ ràng.

### Tin mọi thành phần nội bộ

Plugin, build worker hoặc service account nội bộ vẫn có thể bị xâm nhập. Xác định trust dựa trên kiểm soát và bằng chứng.

### Chỉ bảo vệ ở client

Editor validation có thể bị bỏ qua bằng API trực tiếp. Thực thi kiểm soát tại server và data source.

### Chỉ dùng một lớp bảo vệ

Một filter hoặc một sandbox có thể cấu hình sai. Dùng defense in depth phù hợp với rủi ro.

### Không gắn threat với test

Mitigation tồn tại trên giấy nhưng không được xác minh. Mỗi yêu cầu quan trọng cần test hoặc bằng chứng vận hành.

### Chấm điểm rủi ro thiếu giả định

Con số likelihood/impact không giải thích được vì sao chọn. Ghi điều kiện, dữ liệu và owner của đánh giá.

### Không ghi residual risk

Những threat chưa xử lý biến mất khỏi tầm nhìn. Ghi owner, lý do chấp nhận và thời điểm xem xét lại.

### Không cập nhật sau thay đổi kiến trúc

Trust boundary và attack surface mới không được phân tích. Đưa threat model vào vòng đời phát triển.

## 29. Checklist câu hỏi dùng trong workshop

Các câu hỏi dưới đây giúp nhóm bắt đầu phân tích cho một thành phần DSL:

**Assets**

- Source, artifact, dữ liệu và credential nào có giá trị?
- Tài sản nào cần confidentiality, integrity hoặc availability?
- Ai sở hữu và phân loại tài sản?

**Actors**

- Ai có thể gửi source, query, event hoặc package?
- Có service account hoặc plugin nào chạy thay người dùng?
- Dependency và external service nào có thể bị xâm nhập?

**Trust boundaries**

- Dữ liệu đi qua những process hoặc network nào?
- Identity được tạo và xác minh ở đâu?
- Có luồng nào tin dữ liệu từ client mà không kiểm tra lại?

**Threats**

- Có thể giả mạo identity hoặc event không?
- Có thể sửa source, policy hoặc artifact không?
- Có thể đọc dữ liệu ngoài quyền không?
- Có thể làm cạn tài nguyên không?
- Có thể gọi chức năng quyền cao hơn không?
- Có thể chối bỏ hành động do thiếu audit không?

**Controls**

- Validation và authorization nằm ở đâu?
- Có least privilege và sandbox không?
- Có timeout, quota và cancellation không?
- Có integrity verification và provenance không?
- Có log an toàn và audit không?

**Verification**

- Threat quan trọng nào có test?
- Có test negative và abuse case không?
- Residual risk nào được chấp nhận và bởi ai?

## 30. Kết luận

Mô hình đe dọa giúp nhóm phát triển DSL hiểu tài sản cần bảo vệ, tác nhân có thể gây hại, trust boundary và đường tấn công trong toàn bộ vòng đời từ editor, compiler, build pipeline tới runtime, query engine và workflow service. STRIDE cung cấp cách phân loại threat; attack scenario và risk assessment giúp xác định tác động và ưu tiên; security requirement cùng test evidence biến phân tích thành hành động cụ thể.

Một threat model hiệu quả không chỉ tập trung vào parser hoặc source code. Nó cần xem xét identity, plugin, dependency, artifact, secret, data access, side effect, resource exhaustion, audit và deployment. Các biện pháp như least privilege, server-side authorization, sandbox, input limits, parameter binding, artifact verification, idempotency và observability nên được gắn với trust boundary phù hợp.

Threat modeling là hoạt động liên tục. Khi DSL có thêm cú pháp, connector, plugin, backend hoặc cách triển khai mới, attack surface và giả định tin cậy cũng thay đổi. Duy trì mô hình cùng yêu cầu bảo mật, owner và kiểm thử giúp hệ thống phát triển có kiểm soát và giảm rủi ro trước khi chúng trở thành sự cố.
