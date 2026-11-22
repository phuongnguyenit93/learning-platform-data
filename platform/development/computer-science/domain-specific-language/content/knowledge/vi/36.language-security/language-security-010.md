# Phản ứng sự cố

## 1. Phản ứng sự cố trong bảo mật DSL là gì?

Trong một nền tảng ngôn ngữ chuyên biệt miền (Domain-Specific Language — DSL), **sự cố bảo mật (security incident)** là một sự kiện làm lộ, thay đổi, phá hủy hoặc sử dụng trái phép source DSL, dữ liệu, compiler, runtime, plugin, host application hay hạ tầng thực thi.

**Phản ứng sự cố (incident response)** là quy trình có tổ chức để phát hiện, đánh giá, cô lập, loại bỏ nguyên nhân, khôi phục hoạt động và rút kinh nghiệm sau sự cố.

Một nền tảng DSL có những bề mặt tấn công riêng:

- Source DSL do người dùng hoặc tenant gửi lên.
- Lexer, parser, type checker và compiler.
- Plugin, extension và dependency.
- Runtime thực thi rule, workflow hoặc script.
- Host API kết nối với database, file, network và dịch vụ ngoài.
- Configuration, secret và policy.
- Artifact sinh ra như code, query, bytecode hoặc workflow plan.
- Editor, Language Server, build service và CI/CD.
- Registry, package repository và hệ thống phân phối extension.

Ví dụ, một DSL cho phép người dùng khai báo workflow. Một file độc hại có thể làm parser tiêu thụ quá nhiều bộ nhớ, gọi host function vượt quyền, đọc dữ liệu của tenant khác hoặc kích hoạt plugin đã bị thay thế. Phản ứng sự cố cần xử lý cả source, runtime, host và dữ liệu liên quan.

Mục tiêu của incident response:

1. Bảo vệ con người, dữ liệu và tài sản quan trọng.
2. Giới hạn phạm vi và tác động của sự cố.
3. Giữ bằng chứng đủ tin cậy để điều tra.
4. Loại bỏ nguyên nhân và đường xâm nhập.
5. Khôi phục dịch vụ an toàn.
6. Thông báo đúng người, đúng thời điểm.
7. Giảm khả năng sự cố tương tự tái diễn.

Phản ứng sự cố cần được chuẩn bị trước khi có sự cố. Một tổ chức không nên đợi đến khi runtime bị khai thác mới tìm cách xác định ai có quyền dừng execution hoặc thu hồi plugin.

## 2. Vòng đời phản ứng sự cố

Một quy trình phổ biến gồm các giai đoạn:

~~~text
Prepare
   |
   v
Detect and Report
   |
   v
Triage and Analyze
   |
   v
Contain
   |
   v
Eradicate
   |
   v
Recover
   |
   v
Lessons Learned
~~~

Các giai đoạn có thể lặp lại. Ví dụ, khi điều tra phát hiện thêm một tenant bị ảnh hưởng, nhóm ứng phó quay lại bước triage và mở rộng containment.

| Giai đoạn | Câu hỏi chính | Kết quả mong đợi |
|---|---|---|
| Prepare | Ai làm gì khi có sự cố? | Kế hoạch, công cụ, quyền và playbook |
| Detect | Có dấu hiệu nào bất thường? | Alert hoặc incident report |
| Triage | Mức độ và phạm vi ra sao? | Severity, owner và phạm vi ban đầu |
| Contain | Làm sao ngăn tác động lan rộng? | Hạn chế được đường tấn công |
| Eradicate | Nguyên nhân nào cần loại bỏ? | Thành phần bị xâm nhập được xử lý |
| Recover | Có thể mở lại dịch vụ an toàn chưa? | Hệ thống phục hồi và được giám sát |
| Learn | Điều gì cần thay đổi? | Hành động khắc phục có owner và deadline |

Không phải sự cố nào cũng cần dừng toàn bộ nền tảng. Cần chọn biện pháp tương xứng với rủi ro và bằng chứng.

## 3. Chuẩn bị trước sự cố

Giai đoạn chuẩn bị quyết định nhóm có thể phản ứng nhanh và an toàn hay không.

### 3.1 Xác định tài sản quan trọng

Lập danh mục:

- Source DSL và repository.
- Secret, signing key và credential.
- Compiler/runtime artifact.
- Plugin và dependency.
- Host API và service identity.
- Tenant data và persisted workflow state.
- Build pipeline, package registry và deployment system.
- Log, trace, audit và backup.

Gắn owner, mức độ quan trọng, vị trí lưu và dependency cho từng tài sản.

### 3.2 Xác định vai trò

Một mô hình vai trò có thể gồm:

| Vai trò | Trách nhiệm |
|---|---|
| Incident commander | Điều phối, đặt ưu tiên và quyết định escalation |
| Security responder | Điều tra dấu hiệu xâm nhập và phạm vi |
| DSL/platform engineer | Phân tích compiler, runtime, plugin và host API |
| Infrastructure operator | Cô lập network, compute, storage và identity |
| Data owner | Đánh giá dữ liệu bị ảnh hưởng |
| Communications lead | Điều phối thông báo nội bộ/ngoài tổ chức |
| Legal/privacy contact | Đánh giá nghĩa vụ hợp đồng và thông báo |

Trong nhóm nhỏ, một người có thể đảm nhiệm nhiều vai trò. Tuy nhiên, quyết định quan trọng và người chịu trách nhiệm cần được ghi nhận.

### 3.3 Chuẩn bị quyền khẩn cấp

Xác định trước ai được phép:

- Dừng một execution hoặc worker pool.
- Disable một DSL function hoặc capability.
- Thu hồi plugin hoặc package.
- Chặn một tenant hoặc API key.
- Rotate credential.
- Chuyển traffic sang chế độ read-only.
- Khôi phục từ backup.

Quyền khẩn cấp cần được bảo vệ, audit và kiểm tra định kỳ.

### 3.4 Chuẩn bị playbook

Playbook mô tả các bước thực hiện cho tình huống cụ thể. Mỗi playbook nên nêu trigger, owner, dữ liệu cần thu thập, quyết định containment, điều kiện khôi phục và đường escalation.

### 3.5 Diễn tập

Tabletop exercise giúp nhóm tập xử lý tình huống như plugin độc hại, lộ signing key, cross-tenant access hoặc parser denial of service trước khi sự cố thật xảy ra.

## 4. Phát hiện và báo cáo sự cố

Sự cố có thể được phát hiện qua alert tự động, người dùng báo cáo, audit review, nhà cung cấp thông báo hoặc kết quả kiểm tra bảo mật.

### 4.1 Dấu hiệu trong compiler và parser

- Parser crash với một source cụ thể.
- Thời gian parse tăng bất thường.
- Độ sâu AST hoặc số node vượt xa thông thường.
- Một file làm tăng CPU hoặc memory liên tục.
- Compiler tạo artifact không đúng với source.
- Diagnostic hoặc stack trace có dữ liệu bất thường.

### 4.2 Dấu hiệu trong runtime

- Một execution gọi host function không thường dùng.
- Tần suất đọc/ghi tài nguyên tăng đột biến.
- Nhiều execution bị timeout hoặc retry.
- Một tenant truy cập resource thuộc tenant khác.
- Workflow tạo side effect ngoài dự kiến.
- Worker khởi chạy process hoặc network connection lạ.

### 4.3 Dấu hiệu trong plugin ecosystem

- Package version hoặc checksum thay đổi ngoài lịch phát hành.
- Plugin yêu cầu capability mới không có lý do.
- Signature không hợp lệ.
- Dependency bị thay thế hoặc có cảnh báo compromise.
- Plugin gửi dữ liệu đến endpoint lạ.
- Extension tự đăng ký listener hoặc task không được khai báo.

### 4.4 Dấu hiệu trong identity và secret

- API key được dùng từ vị trí hoặc thời điểm bất thường.
- Secret bị đọc bởi service không liên quan.
- Token được sử dụng sau khi đã thu hồi.
- Một principal thay đổi policy hoặc quyền ngoài lịch sử thông thường.

### 4.5 Kênh báo cáo

Người dùng và kỹ sư cần biết nơi báo cáo, thông tin tối thiểu cần cung cấp và cách đánh dấu mức khẩn cấp. Không yêu cầu người báo cáo gửi secret hoặc dữ liệu cá nhân qua kênh không an toàn.

### 4.6 Phân biệt alert và incident

Alert là tín hiệu cần xem xét. Incident là tình huống đã được xác định hoặc có cơ sở hợp lý cần phối hợp ứng phó. Alert có thể là false positive, nhưng cần ghi nhận lý do đóng.

## 5. Triage và phân loại mức độ

Triage xác định mức độ ưu tiên, phạm vi ban đầu và bước tiếp theo.

### 5.1 Thông tin cần xác định

- Tài sản hoặc service bị ảnh hưởng.
- Thời điểm bắt đầu và thời điểm phát hiện.
- Tenant, user hoặc execution liên quan.
- Tính chất: confidentiality, integrity hay availability.
- Có bằng chứng truy cập trái phép hay chưa.
- Có credential hoặc signing key bị lộ không.
- Tác động còn đang diễn ra hay đã dừng.
- Có thể tái tạo hoặc xác minh sự kiện không.

### 5.2 Severity

Một cách phân loại minh họa:

| Mức | Tình huống | Phản ứng |
|---|---|---|
| SEV-1 Critical | Chiếm quyền diện rộng, lộ secret lớn, phá hoại dữ liệu hoặc nhiều tenant bị ảnh hưởng | Kích hoạt incident command ngay |
| SEV-2 High | Một tenant hoặc dịch vụ quan trọng bị xâm nhập, có khả năng lan rộng | Cô lập nhanh và escalation |
| SEV-3 Medium | Phạm vi hẹp, có dấu hiệu khai thác nhưng tác động được giới hạn | Điều tra và khắc phục theo playbook |
| SEV-4 Low | Alert đáng ngờ chưa có bằng chứng tác động | Theo dõi, xác minh và ghi nhận |

Đây là ví dụ. Tổ chức cần định nghĩa tiêu chí và thời gian phản hồi phù hợp với môi trường của mình.

### 5.3 Severity có thể thay đổi

Nếu phát hiện thêm tenant hoặc secret bị ảnh hưởng, cần nâng severity. Không giữ mức ban đầu chỉ vì incident đã được mở với mức thấp hơn.

### 5.4 Incident record

Ghi incident ID, người điều phối, thời điểm, severity, hệ thống liên quan, giả thuyết hiện tại, quyết định và action owner. Phân biệt sự kiện đã xác minh với giả thuyết.

## 6. Phân tích phạm vi ảnh hưởng

Phạm vi (scope) xác định những gì đã hoặc có thể bị ảnh hưởng.

### 6.1 Xác định entry point

Đường xâm nhập có thể là source DSL không tin cậy, plugin hoặc package, Host API endpoint, credential của người dùng hoặc service, build pipeline, configuration hoặc dependency bên thứ ba.

### 6.2 Theo dõi luồng dữ liệu

~~~text
User / Tenant
    |
    v
DSL source upload
    |
    v
Parser and compiler
    |
    v
Compiled artifact
    |
    v
Runtime worker
    |
    v
Host API
    |
    v
Database / external service
~~~

Với mỗi chặng, xác định identity, quyền, log, nơi lưu và dữ liệu có thể bị ảnh hưởng.

### 6.3 Xác định phạm vi tenant

Kiểm tra tenant ID, workspace, process instance và resource ID trong log/audit. Không giả định một lỗi xảy ra trong một tenant thì chỉ tenant đó bị ảnh hưởng nếu service identity hoặc cache được chia sẻ.

### 6.4 Xác định khoảng thời gian

Tìm lần đầu tiên có dấu hiệu và lần cuối cùng có hoạt động đáng ngờ. Xét thời gian lưu log, backup, token lifetime và thời điểm phát hành artifact.

### 6.5 Xác định blast radius

Đánh giá số tenant và người dùng, số execution hoặc workflow, dữ liệu đã đọc/sửa/xóa, credential có thể bị truy cập, artifact hoặc plugin đã phân phối và hệ thống ngoài đã nhận request.

### 6.6 Không kết luận quá sớm

Thiếu log không đồng nghĩa không có truy cập. Ghi rõ giới hạn quan sát, thời gian lưu và nguồn dữ liệu chưa có.

## 7. Bảo toàn bằng chứng

Điều tra cần dữ liệu đủ tin cậy để dựng lại sự kiện.

### 7.1 Nguồn bằng chứng

- Application log và structured audit.
- Compiler diagnostics và execution trace.
- Host API access log.
- Identity provider và token audit.
- Network flow và gateway log.
- Plugin manifest, package checksum và signature.
- Build artifact, commit và release metadata.
- Database audit, backup và change history.
- Worker/container metadata.

### 7.2 Bảo toàn bản gốc

Giữ bản sao read-only của dữ liệu quan trọng. Ghi hash, thời điểm thu thập, nguồn và người thực hiện. Không chỉnh sửa bản gốc để thuận tiện phân tích.

### 7.3 Chain of custody

Với bằng chứng cần phục vụ điều tra chính thức, ghi lại Evidence ID, nguồn và vị trí, người thu thập, thời gian, hash/checksum, các lần chuyển giao và quyền truy cập.

### 7.4 Đồng bộ thời gian

Log từ nhiều service cần có timestamp đáng tin cậy. Ghi timezone, clock source và độ lệch nếu biết. Correlation ID thường giúp liên kết sự kiện khi đồng hồ không hoàn toàn đồng bộ.

### 7.5 Tránh làm thay đổi hiện trường

Không xóa container, plugin hoặc log ngay khi thấy dấu hiệu compromise nếu chưa cân nhắc việc thu thập bằng chứng. Tuy nhiên, nếu tác động đang diễn ra, containment có thể được ưu tiên; cần ghi lại hành động và thời điểm.

### 7.6 Dữ liệu nhạy cảm

Chỉ thu thập phần cần thiết, hạn chế người truy cập và bảo vệ bằng encryption. Không sao chép secret vào ticket hoặc kênh chat chung.

## 8. Containment: cô lập và giới hạn tác động

Containment ngăn sự cố lan rộng trong khi vẫn giữ đủ khả năng điều tra và phục hồi.

### 8.1 Containment ngắn hạn

Biện pháp có thể gồm:

- Dừng execution đang bị khai thác.
- Disable function hoặc capability có rủi ro.
- Chặn plugin/package bị nghi ngờ.
- Thu hồi token hoặc API key.
- Tạm ngừng endpoint hoặc route bị khai thác.
- Giới hạn queue, worker hoặc tenant.
- Chuyển một số thao tác sang read-only.

### 8.2 Containment dài hạn

Sau khi hiểu phạm vi hơn, có thể chuyển workload sang worker pool sạch, dùng bản runtime đã vá, thay credential và signing key, tách tenant hoặc service account, chặn dependency/endpoint độc hại và bổ sung policy tạm thời.

### 8.3 Chọn phạm vi cô lập

Không nên tắt toàn bộ DSL platform nếu chỉ một plugin có thể bị disable an toàn. Ngược lại, nếu host API dùng chung đang bị compromise, cô lập một worker đơn lẻ có thể không đủ.

### 8.4 Kill switch

Host nên có kill switch để ngừng nhận execution mới, dừng một nhóm function, disable một plugin, chặn một tenant hoặc thu hồi capability. Kill switch phải được bảo vệ và kiểm thử.

### 8.5 Tạm ngừng hay xóa

Disable hoặc quarantine thường bảo toàn bằng chứng tốt hơn xóa ngay. Quyết định xóa cần tính đến backup, forensic và khả năng khôi phục.

### 8.6 Theo dõi containment

Sau khi áp dụng biện pháp, xác nhận traffic, execution và side effect đáng ngờ thực sự dừng. Không coi thao tác gửi lệnh thành công là bằng chứng hệ thống đã được cô lập.

## 9. Eradication: loại bỏ nguyên nhân

Sau containment, cần loại bỏ đường xâm nhập và thành phần bị xâm phạm.

### 9.1 Source DSL độc hại

Xác định source, version, author/submitter và execution đã sử dụng. Disable hoặc quarantine source; sửa validator hoặc policy cho phép khai thác.

### 9.2 Parser/compiler vulnerability

Vá parser/compiler, cập nhật dependency, xây dựng artifact sạch và xác minh hash/signature. Xem xét cache hoặc artifact đã tạo bởi compiler bị xâm nhập.

### 9.3 Plugin compromise

Thu hồi package hoặc version, kiểm tra signing key, dependency và build provenance. Xây dựng lại plugin từ source tin cậy và rotate credential có thể bị lộ.

### 9.4 Host API abuse

Sửa authorization, capability mapping, tenant isolation hoặc validation. Xem xét mọi request đã được thực hiện bởi identity bị xâm phạm.

### 9.5 Secret compromise

Rotate secret, revoke token, thu hồi certificate và kiểm tra nơi credential đã được dùng. Cập nhật secret provider và các workload phụ thuộc.

### 9.6 Persistence mechanism

Kiểm tra scheduled task, startup hook, plugin registry, modified config, service account, deployment manifest và CI pipeline để phát hiện cơ chế duy trì truy cập.

### 9.7 Không chỉ xóa dấu hiệu

Xóa file độc hại mà không sửa quyền hoặc lỗ hổng đã cho phép nó xuất hiện sẽ khiến sự cố tái diễn.

## 10. Recovery: khôi phục an toàn

Recovery đưa hệ thống trở lại hoạt động có kiểm soát.

### 10.1 Chọn điểm phục hồi

Chọn artifact, dữ liệu và configuration từ nguồn tin cậy. Kiểm tra backup có được tạo trước thời điểm compromise và không bị sửa bởi cùng identity bị xâm nhập.

### 10.2 Clean rebuild

Với compiler, runtime hoặc plugin bị nghi ngờ, ưu tiên build lại từ source và dependency đã xác minh trong môi trường sạch.

### 10.3 Khôi phục dữ liệu

So sánh backup với audit/change log để xác định dữ liệu cần restore. Tránh ghi đè các giao dịch hợp lệ xảy ra sau backup.

### 10.4 Canary recovery

Mở lại một nhóm worker hoặc tenant nhỏ. Theo dõi error rate, quyền truy cập, resource consumption và dấu hiệu bất thường trước khi mở rộng.

### 10.5 Credential rotation

Chỉ khôi phục traffic sau khi credential cần thiết đã được rotate/revoke và các service dùng credential mới.

### 10.6 Reconcile side effects

Kiểm tra các giao dịch bên ngoài như thanh toán, email, webhook hoặc event. Có thể cần đối soát, deduplicate hoặc compensation.

### 10.7 Tăng cường giám sát

Trong giai đoạn sau phục hồi, đặt alert nhạy hơn cho indicator liên quan và theo dõi các execution có cùng dấu hiệu.

## 11. Phản ứng với sự cố source DSL độc hại

Source DSL có thể được gửi bởi người dùng không tin cậy. Nó có thể khai thác parser hoặc tạo hành vi nguy hiểm trong runtime.

### 11.1 Parser denial of service

Dấu hiệu gồm source lồng nhau rất sâu, chuỗi hoặc biểu thức cực dài, grammar gây backtracking/recursion lớn, AST node count tăng đột biến và compiler process tiêu thụ CPU/memory liên tục.

Phản ứng:

1. Xác định source và compiler version.
2. Giới hạn hoặc chặn source có liên quan.
3. Dùng parser/resource limit để giảm tác động.
4. Bảo toàn sample và trace.
5. Vá parser hoặc grammar.
6. Kiểm tra các request tương tự.

### 11.2 Injection vào generated code

Nếu DSL sinh SQL, shell, JavaScript hoặc template, input có thể tạo code ngoài dự kiến.

Phản ứng:

- Dừng phát hành artifact đáng ngờ.
- Xác định artifact và execution đã dùng.
- Kiểm tra output theo context encoding/parameterization.
- Tìm side effect đã xảy ra.
- Vá generator và tái tạo artifact từ source đã xác minh.

### 11.3 Bypass authorization

Nếu source có thể gọi function ngoài capability được cấp:

- Thu hồi capability hoặc disable function.
- Xác định execution và resource đã bị truy cập.
- Kiểm tra host API authorization tại runtime.
- Không chỉ dựa vào compiler check.
- Khắc phục policy và test tenant isolation.

### 11.4 Data exfiltration

Nếu DSL có thể đọc và gửi dữ liệu:

- Chặn outbound destination hoặc function gửi dữ liệu.
- Xác định data source và recipient.
- Kiểm tra log, network flow và audit.
- Rotate credential nếu có nguy cơ lộ.
- Đánh giá nghĩa vụ thông báo theo quy định và hợp đồng.

## 12. Phản ứng với plugin hoặc dependency bị compromise

Plugin có thể chạy trong cùng process hoặc có quyền gọi host API.

### 12.1 Xác định package

Ghi plugin ID, version, checksum, signature, repository, build provenance và dependency tree.

### 12.2 Quarantine

Ngừng phân phối và activation version bị ảnh hưởng. Nếu có thể, giữ package và metadata trong kho cách ly để điều tra.

### 12.3 Xác minh signing chain

Kiểm tra signing key, certificate, pipeline và người/identity có quyền phát hành. Nếu key bị lộ, revoke và phát hành key mới theo quy trình.

### 12.4 Kiểm tra plugin đã cài

Xác định host instance nào đã cài version bị ảnh hưởng, plugin nào đã load và capability nào đã được sử dụng.

### 12.5 Dependency compromise

Kiểm tra transitive dependencies, lockfile, package source và thời điểm artifact được tải. Một plugin sạch có thể bị ảnh hưởng bởi dependency độc hại.

### 12.6 Khôi phục

Chỉ phát hành plugin được build lại từ nguồn xác minh, có signature mới và đã kiểm tra dependency. Xem xét thu hồi cache hoặc artifact cũ.

## 13. Phản ứng với host API hoặc identity compromise

Host API là đường truy cập vào tài nguyên thực tế của ứng dụng.

### 13.1 Token hoặc API key bị lộ

- Revoke token hoặc key.
- Xác định identity và scope.
- Tìm request đã được xác thực bằng credential.
- Kiểm tra resource bị đọc/sửa.
- Cấp credential mới với scope tối thiểu.

### 13.2 Service account bị chiếm

Disable hoặc rotate identity, kiểm tra workload sử dụng account đó và phân biệt request hợp lệ với bất thường.

### 13.3 Authorization bypass

Tạm thời disable command hoặc giới hạn resource scope. Sửa kiểm tra quyền ở host boundary và xác nhận mọi adapter đều dùng policy mới.

### 13.4 Cross-tenant access

Cô lập các request path liên quan, xác định tenant nguồn và đích, kiểm tra cache key, database query, background worker context và shared service registry.

### 13.5 Host service bị compromise

Nếu service chính bị chiếm, cần xem xét downstream systems mà service có quyền truy cập. Rotate credential và kiểm tra lateral movement.

## 14. Quản lý dữ liệu và quyền riêng tư trong sự cố

Sự cố bảo mật có thể liên quan dữ liệu cá nhân, dữ liệu khách hàng hoặc bí mật thương mại.

### 14.1 Phân loại dữ liệu

Xác định loại dữ liệu: public, internal, confidential, personal data, secret hoặc regulated data.

### 14.2 Data minimization

Chỉ thu thập bằng chứng cần thiết. Hạn chế sao chép payload, source hoặc database dump đầy đủ nếu chỉ cần một phần.

### 14.3 Access control

Incident workspace cần quyền truy cập giới hạn. Ghi lại ai đã xem hoặc tải bằng chứng nhạy cảm.

### 14.4 Encryption

Bảo vệ bằng chứng và backup khi lưu trữ và truyền tải. Quản lý key tách biệt với dữ liệu được bảo vệ.

### 14.5 Retention

Giữ bằng chứng theo policy pháp lý, hợp đồng và điều tra. Không lưu vô thời hạn nếu không có căn cứ.

### 14.6 Notification assessment

Legal/privacy contact đánh giá nghĩa vụ thông báo cho khách hàng, cơ quan quản lý hoặc đối tác theo luật và hợp đồng áp dụng. Nhóm kỹ thuật cung cấp facts, không tự suy đoán thời hạn pháp lý.

## 15. Truyền thông trong thời gian xảy ra sự cố

Thông tin thiếu nhất quán có thể làm tình hình phức tạp hơn.

### 15.1 Single source of truth

Dùng một incident record hoặc kênh điều phối chính. Ghi quyết định, trạng thái, owner và thời điểm cập nhật.

### 15.2 Nội dung cập nhật

Một cập nhật hữu ích gồm điều đã xác minh, điều đang điều tra, tác động đã biết, biện pháp containment, dịch vụ/nhóm bị ảnh hưởng, việc cần làm tiếp theo và thời điểm cập nhật kế tiếp.

### 15.3 Phân biệt facts và hypotheses

Không trình bày giả thuyết như kết luận. Nếu chưa biết phạm vi, nói rõ điều gì chưa xác minh.

### 15.4 Người phát ngôn

Chỉ người được chỉ định mới phát ngôn ra ngoài. Nhân viên không tự công bố log, source hoặc chi tiết khai thác lên kênh công khai.

### 15.5 Thông báo người dùng

Thông báo nên nói rõ ảnh hưởng, hành động người dùng cần thực hiện và kênh hỗ trợ. Không tiết lộ chi tiết có thể giúp kẻ tấn công tái khai thác khi chưa được phép.

## 16. Playbook sự cố cho nền tảng DSL

Playbook là hướng dẫn thực thi cụ thể. Dưới đây là các mẫu để tổ chức tùy chỉnh.

### 16.1 Parser hoặc compiler bị khai thác

Trigger: parser crash bất thường, source gây resource exhaustion hoặc compiler tạo output trái phép.

Các bước:

1. Mở incident và xác định compiler version.
2. Thu thập source sample, request ID, trace và worker metadata.
3. Giới hạn upload hoặc disable đường xử lý bị ảnh hưởng.
4. Tìm các execution/source tương tự.
5. Xác định lỗ hổng và vá parser/compiler.
6. Build lại artifact trong môi trường sạch.
7. Canary và theo dõi resource usage.

### 16.2 Plugin độc hại

Trigger: signature sai, package bị thay đổi hoặc plugin gọi capability bất thường.

Các bước:

1. Ghi plugin ID, version và checksum.
2. Quarantine package và ngừng activation.
3. Xác định host instance đã cài.
4. Thu thập audit của capability và network.
5. Revoke signing key nếu có nguy cơ compromise.
6. Build và ký lại package từ nguồn tin cậy.
7. Cập nhật plugin registry và theo dõi.

### 16.3 Secret bị lộ

Trigger: secret xuất hiện trong log, repository hoặc được dùng bất thường.

Các bước:

1. Xác định secret, scope và service sử dụng.
2. Revoke/rotate credential.
3. Kiểm tra access log trong khoảng thời gian liên quan.
4. Tìm nơi secret đã được copy hoặc cache.
5. Xóa hoặc redact bản sao theo quy trình evidence.
6. Cập nhật secret provider và kiểm tra service.
7. Bổ sung scan và redaction.

### 16.4 Cross-tenant access

Trigger: một execution đọc hoặc ghi resource ngoài tenant context.

Các bước:

1. Tạm ngừng route hoặc function liên quan.
2. Xác định tenant, execution, resource và identity.
3. Bảo toàn access log, query trace và cache metadata.
4. Kiểm tra context propagation và cache key.
5. Sửa authorization tại host boundary.
6. Kiểm thử tenant isolation.
7. Đối soát dữ liệu đã truy cập hoặc thay đổi.

### 16.5 Runtime tạo side effect trái phép

Trigger: DSL execution gửi email, thanh toán hoặc thay đổi dữ liệu không được yêu cầu.

Các bước:

1. Dừng execution hoặc capability liên quan.
2. Xác định source, compiled artifact, runtime version và host function.
3. Đối chiếu execution trace với business audit.
4. Ngăn retry hoặc replay tự động nếu có thể tạo thêm side effect.
5. Đối soát hệ thống ngoài và thực hiện compensation có kiểm soát.
6. Sửa policy/function mapping.
7. Kiểm tra idempotency và replay protection.

## 17. Evidence timeline và incident report

Timeline giúp tái dựng thứ tự sự kiện.

| Thời điểm UTC | Sự kiện | Nguồn | Mức xác minh |
|---|---|---|---|
| 01:10 | Plugin version mới được phát hành | Registry audit | Đã xác minh |
| 01:22 | Host tải package | Deployment log | Đã xác minh |
| 01:30 | Function nhạy cảm được gọi tăng đột biến | Host API log | Đã xác minh |
| 01:35 | Alert được tạo | Monitoring | Đã xác minh |
| 01:42 | Plugin bị disable | Incident record | Đã xác minh |

Không sửa timestamp để làm các nguồn log trông đồng bộ. Ghi rõ nguồn timezone và độ lệch nếu cần.

Incident report sau xử lý nên có executive summary, thời gian và phạm vi, tài sản/tenant bị ảnh hưởng, root cause và contributing factors, dữ liệu hoặc credential có thể bị tác động, containment/eradication/recovery actions, bằng chứng và giới hạn điều tra, thông báo đã thực hiện, hành động phòng ngừa cùng owner và deadline.

## 18. Khôi phục và xác minh sau sự cố

Trước khi đóng incident, cần xác nhận:

- Entry point đã được đóng hoặc kiểm soát.
- Runtime/compiler/plugin đang chạy là artifact tin cậy.
- Secret bị ảnh hưởng đã được revoke hoặc rotate.
- Policy và permission đã được sửa.
- Dữ liệu đã được đối soát hoặc khôi phục.
- Không còn execution hoặc scheduled task đáng ngờ.
- Alert và monitoring đang hoạt động.
- Chủ sở hữu hệ thống chấp nhận trạng thái phục hồi.

### 18.1 Increased monitoring

Trong một khoảng thời gian sau recovery, theo dõi indicator đã xuất hiện trong incident và các hành vi tương tự.

### 18.2 Reopen criteria

Định nghĩa điều kiện mở lại incident, chẳng hạn cùng indicator xuất hiện, phát hiện thêm tenant bị ảnh hưởng hoặc credential cũ tiếp tục được dùng.

### 18.3 Close không đồng nghĩa mọi vấn đề đã hết

Incident có thể được đóng khi tác động đã được kiểm soát, trong khi các hành động dài hạn vẫn được theo dõi riêng với owner và deadline.

## 19. Post-incident review và cải tiến

Sau khi ổn định, tổ chức cần tìm hiểu vì sao sự cố có thể xảy ra và cách giảm khả năng tái diễn.

### 19.1 Blameless review

Tập trung vào điều kiện hệ thống, quy trình và quyết định đã dẫn đến sự cố. Không dùng review để đổ lỗi cho một cá nhân.

### 19.2 Root cause và contributing factors

Phân biệt root cause, contributing factor, detection gap và response gap. Ghi rõ nguyên nhân cốt lõi, yếu tố làm tăng tác động, lý do phát hiện chậm và lý do containment/recovery chậm.

### 19.3 Five whys

Đặt câu hỏi tại sao nhiều lần để đi từ triệu chứng đến nguyên nhân hệ thống. Không dừng ở câu trả lời "người dùng cấu hình sai" nếu UI, validation hoặc permission đã cho phép lỗi đó.

### 19.4 Corrective actions

Hành động có thể gồm sửa parser/runtime, giới hạn host capability, cải thiện tenant isolation, bổ sung signing/provenance, rotate hoặc giảm scope secret, thêm alert/audit, cập nhật playbook và diễn tập lại.

### 19.5 Owner và deadline

Mỗi action cần owner, priority, deadline và cách xác nhận hoàn tất. Không để kết luận review chỉ là một danh sách ý tưởng không có người chịu trách nhiệm.

### 19.6 Chia sẻ bài học

Chia sẻ thông tin hữu ích cho engineering và operations nhưng loại bỏ secret, dữ liệu cá nhân và chi tiết khai thác không được phép công bố.

## 20. Metrics cho incident response

Metrics giúp đánh giá khả năng phát hiện và phản ứng.

| Metric | Ý nghĩa |
|---|---|
| MTTD | Mean Time to Detect: thời gian trung bình để phát hiện |
| MTTA | Mean Time to Acknowledge: thời gian từ alert đến khi có người nhận xử lý |
| MTTC | Mean Time to Contain: thời gian trung bình để giới hạn tác động |
| MTTR | Mean Time to Recover/Resolve: thời gian trung bình để phục hồi hoặc xử lý |
| Reopen rate | Tỷ lệ incident phải mở lại |
| False-positive rate | Tỷ lệ alert không phải incident |
| Action completion rate | Tỷ lệ corrective action hoàn thành đúng hạn |

Định nghĩa điểm bắt đầu và kết thúc của từng metric cần thống nhất. Không tối ưu số liệu bằng cách đóng incident sớm trong khi tác động chưa được kiểm soát.

## 21. Tích hợp incident response vào kiến trúc DSL

Incident response hiệu quả cần được hỗ trợ bởi kiến trúc ngay từ đầu.

### 21.1 Kill switch và policy enforcement

Runtime nên có khả năng ngừng execution mới, disable capability và giới hạn tenant mà không cần thay đổi source DSL.

### 21.2 Audit có cấu trúc

Ghi execution ID, tenant, principal, DSL version, compiler/runtime version, function ID, capability và resource được tác động.

### 21.3 Artifact provenance

Mỗi artifact nên gắn source revision, compiler version, plugin version, dependency identity và build provenance để xác định nguồn gốc.

### 21.4 Immutable execution record

Lưu trạng thái quan trọng và policy đã áp dụng cho execution. Tránh để log bị ghi đè hoặc mất khi worker restart.

### 21.5 Resource isolation

Chạy DSL không tin cậy trong worker có resource limit, network policy và identity riêng. Không dùng quyền host process rộng hơn mức cần thiết.

### 21.6 Safe defaults

Nếu authorization service hoặc policy store không khả dụng, quyết định với thao tác nhạy cảm cần fail closed theo contract. Không tự cấp quyền vì dependency bị lỗi.

### 21.7 Replay control

Cho phép replay có kiểm soát, có identity và audit riêng. Không replay command có side effect nếu chưa xác minh idempotency hoặc có kế hoạch compensation.

## 22. Những sai lầm thường gặp

### Chỉ phản ứng ở tầng infrastructure

Container đã được khởi động lại nhưng source độc hại, plugin bị compromise hoặc token vẫn còn hiệu lực.

**Cách khắc phục:** điều tra toàn bộ chuỗi source, compiler, artifact, runtime, host API và identity.

### Xóa bằng chứng quá sớm

Log, package hoặc worker bị xóa trước khi xác định phạm vi.

**Cách khắc phục:** bảo toàn bản sao và metadata trước khi cleanup, trừ khi cần hành động khẩn cấp để ngăn tác động đang diễn ra.

### Thu hồi một token nhưng quên token liên quan

Credential có thể được copy sang pipeline, plugin hoặc worker khác.

**Cách khắc phục:** truy vết secret theo nơi cấp, nơi lưu, consumer và scope.

### Chỉ vá compiler

Artifact độc hại đã được phát hành vẫn có thể tiếp tục chạy.

**Cách khắc phục:** xác định và xử lý artifact, cache, execution và plugin đã tạo từ phiên bản bị ảnh hưởng.

### Không kiểm tra side effect bên ngoài

Workflow đã bị dừng nhưng payment, email hoặc event đã được xử lý.

**Cách khắc phục:** đối soát hệ thống ngoài, deduplicate và thực hiện compensation phù hợp.

### Không có owner cho corrective action

Review kết thúc nhưng lỗ hổng vẫn tồn tại.

**Cách khắc phục:** mỗi action có owner, deadline và bằng chứng hoàn thành.

### Đóng incident khi chỉ alert đã biến mất

Alert không còn xuất hiện nhưng persistence hoặc credential compromise vẫn tồn tại.

**Cách khắc phục:** dùng recovery criteria và xác minh nguyên nhân đã được loại bỏ.

## 23. Quy trình xử lý sự cố mẫu cho nền tảng DSL

Khi nhận một báo cáo có dấu hiệu thực thi DSL trái phép, có thể tiến hành:

1. **Mở incident:** tạo ID, chọn commander và ghi thời điểm.
2. **Xác định severity:** dựa trên dữ liệu, quyền và phạm vi tenant.
3. **Tạo timeline:** thu thập alert, execution ID, source revision và host API log.
4. **Xác định entry point:** source, plugin, credential, build pipeline hoặc host service.
5. **Giới hạn tác động:** dừng execution, disable capability hoặc quarantine package.
6. **Bảo toàn evidence:** lưu log, artifact, checksum và metadata.
7. **Xác định blast radius:** tenant, resource, secret, workflow và hệ thống ngoài.
8. **Loại bỏ nguyên nhân:** vá, revoke, rotate, rebuild và sửa policy.
9. **Đối soát side effect:** kiểm tra database, payment, event và notification.
10. **Khôi phục có kiểm soát:** canary, theo dõi và mở rộng traffic.
11. **Truyền thông:** cập nhật người liên quan theo facts đã xác minh.
12. **Review:** ghi root cause, contributing factors và corrective actions.

## 24. Ví dụ tổng hợp: plugin DSL gửi dữ liệu trái phép

Giả sử một host application cài plugin mới để cung cấp function host.customer.export. Sau một đợt phát hành, monitoring phát hiện plugin gửi lượng dữ liệu lớn đến một endpoint chưa được phê duyệt.

### 24.1 Detect

Alert xuất phát từ network egress monitor và số lần gọi function export tăng bất thường.

### 24.2 Triage

Nhóm xác định plugin ID, version, checksum, host instance, tenant và thời gian hoạt động. Severity được đặt theo phạm vi dữ liệu có thể đã rời hệ thống.

### 24.3 Contain

Host disable plugin version bị nghi ngờ và thu hồi capability export. Worker liên quan bị ngừng nhận execution mới. Nhóm giữ package và log để điều tra.

### 24.4 Analyze

Kiểm tra manifest, dependency, signing metadata, function invocation trace và network flow. Xác định plugin có thể đã dùng một service identity để đọc customer data.

### 24.5 Eradicate

Quarantine package, thu hồi signing key nếu có bằng chứng compromise, rotate credential và build lại plugin từ source đã xác minh. Sửa allowlist để export cần capability riêng.

### 24.6 Recover

Triển khai plugin sạch cho một nhóm host nhỏ. Theo dõi egress, function invocation và error rate. Sau đó mở rộng theo tenant.

### 24.7 Lessons learned

Nhóm bổ sung package provenance, alert cho outbound destination mới, giới hạn export theo tenant, yêu cầu approval cho capability nhạy cảm và diễn tập lại playbook plugin compromise.

## 25. Câu hỏi tự kiểm tra

1. Sự cố bảo mật trong nền tảng DSL có thể ảnh hưởng những thành phần nào?
2. Các giai đoạn chính của incident response là gì?
3. Vì sao cần chuẩn bị vai trò, quyền khẩn cấp và playbook trước sự cố?
4. Dấu hiệu nào có thể cho thấy parser hoặc runtime đang bị khai thác?
5. Triage cần xác định những thông tin nào?
6. Severity nên thay đổi khi có bằng chứng mới như thế nào?
7. Làm sao xác định blast radius theo tenant và execution?
8. Evidence preservation và chain of custody có vai trò gì?
9. Containment ngắn hạn khác eradication như thế nào?
10. Vì sao disable plugin thường tốt hơn xóa ngay package bị nghi ngờ?
11. Khi nào cần rotate secret hoặc revoke signing key?
12. Phản ứng với parser denial of service khác plugin compromise ở điểm nào?
13. Vì sao cần kiểm tra side effect ở hệ thống ngoài sau khi dừng workflow?
14. Những tiêu chí nào cần có trước khi khôi phục dịch vụ?
15. Incident commander và technical responder có trách nhiệm gì?
16. Blameless post-incident review tập trung vào điều gì?
17. MTTD, MTTA, MTTC và MTTR đo lường những khoảng thời gian nào?
18. Kill switch, audit và artifact provenance hỗ trợ ứng phó ra sao?
19. Vì sao thiếu log không đồng nghĩa không có truy cập?
20. Một corrective action cần những thông tin nào để theo dõi đến khi hoàn thành?

Phản ứng sự cố là năng lực vận hành thiết yếu của một nền tảng DSL an toàn. Khi tổ chức chuẩn bị vai trò và playbook, phát hiện được dấu hiệu trong source/compiler/runtime/plugin/host, bảo toàn bằng chứng, cô lập đúng phạm vi và phục hồi có kiểm soát, sự cố có thể được xử lý nhanh hơn và ít gây tác động hơn. Bài học sau mỗi sự cố cần chuyển thành thay đổi cụ thể trong kiến trúc, policy và quy trình.
