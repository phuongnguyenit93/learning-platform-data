# Đánh giá độ tin cậy của assurance case: kết luận bảo mật đáng tin đến mức nào?

**Đánh giá độ tin cậy (confidence assessment)** trong một **assurance case** là hoạt động xác định mức độ hợp lý của các tuyên bố (*claim*), chất lượng của lập luận (*argument*), độ mạnh của bằng chứng (*evidence*), và những bất định hoặc phản chứng có thể làm suy yếu kết luận. Câu hỏi chính không phải “có bao nhiêu báo cáo PASS?” mà là **“ta có thể dựa vào lập luận này để quyết định điều gì, trong phạm vi nào, và tại sao?”**

Trong chương **Assurance case** thuộc module **SECURITY_SECURITY_ASSURANCE**, đánh giá độ tin cậy giúp kết nối mục tiêu bảo mật với phân tích rủi ro, security requirements, kiểm soát thiết kế và vận hành, kiểm thử, audit, khắc phục findings và các quyết định quản trị. Tuyên bố đạt một mục tiêu bảo mật chỉ đáng tin khi chuỗi liên kết từ yêu cầu đến bằng chứng có thể kiểm chứng và những hạn chế được trình bày trung thực.

Ví dụ, một API tuyên bố rằng người dùng tenant A không thể đọc dữ liệu của tenant B. Một bộ test báo PASS 100% chưa đủ để tạo độ tin cậy cao nếu chỉ kiểm tra 20 trong 48 endpoint, dùng build cũ, bỏ qua luồng export bất đồng bộ hoặc chưa kiểm tra các role có đặc quyền. **Chất lượng phạm vi và lý lẽ quan trọng không kém kết quả kiểm thử.**

## 1. Mục tiêu học tập

Sau bài học, người học có thể:

1. Phân biệt **độ tin cậy của một assurance case**, **tính đúng của claim**, **rủi ro còn lại** và **quyết định chấp nhận rủi ro**.
2. Đánh giá từng lớp **Claim–Argument–Evidence (CAE)**, gồm bối cảnh, tiêu chí, tiền đề và mối liên hệ.
3. Kiểm tra tính liên quan, đầy đủ, tin cậy, độc lập, nguyên vẹn, kịp thời và khả năng tái hiện của evidence.
4. Phát hiện thiếu sót trong lập luận, lấy mẫu, tập tài sản, giả định, phụ thuộc và các phản chứng (*defeaters*).
5. Xây dựng thang confidence định tính có tiêu chí và giới hạn; tránh đánh đồng tỷ lệ test PASS với xác suất hệ thống an toàn.
6. Lập báo cáo đánh giá có traceability, người chịu trách nhiệm, reviewer và trigger đánh giá lại.
7. Áp dụng phương pháp qua ví dụ bảo mật API, IAM, logging và disaster recovery.

---

## 2. Trước khi chấm độ tin cậy, phải biết đang tin điều gì

Một assurance case có cấu trúc nhằm hỗ trợ **một quyết định cụ thể**. Vì vậy, không thể chấm “độ tin cậy của toàn bộ hệ thống” khi chưa định nghĩa security objective, đối tượng và giới hạn.

Ví dụ một claim có phạm vi:

> **G0:** Đối với 48 endpoint xử lý hồ sơ khách hàng của release R trên production, mọi đường truy cập thuộc danh mục kiểm kê phải xác thực và kiểm tra quyền ở cấp tenant/tài nguyên trước khi trả dữ liệu, theo ma trận quyền phiên bản S và các vai trò đã xác định.

Phạm vi trên vẫn chưa tự bao gồm tài khoản DBA truy cập trực tiếp cơ sở dữ liệu, hệ thống phân tích nằm ngoài API hoặc các endpoint được bổ sung sau release R. Những yếu tố đó cần được kiểm toán hoặc ghi thành phần nằm ngoài phạm vi và đánh giá rủi ro riêng.

Cần tách bốn khái niệm:

| Khái niệm | Câu hỏi | Ví dụ |
|---|---|---|
| **Claim satisfaction** | Bằng chứng có hỗ trợ claim trong phạm vi không? | Tất cả đường API đã định có enforce authorization? |
| **Confidence in assessment** | Có cơ sở vững đến đâu để tin kết luận đánh giá là đúng? | Đã xác minh inventory, test version, log và nguồn độc lập? |
| **Residual risk** | Rủi ro nào còn tồn tại sau control? | Chiếm session, support role rộng, third-party dependency |
| **Acceptance decision** | Ai có thẩm quyền chấp nhận vận hành với rủi ro còn lại? | Business owner và security authority duyệt có điều kiện |

**Độ tin cậy cao không tự có nghĩa là hệ thống bảo mật tốt.** Người đánh giá có thể rất chắc chắn rằng claim đang **sai**, vì có bằng chứng tái hiện lỗi truy cập chéo tenant trên production. Ngược lại, không có finding không nhất thiết đồng nghĩa đủ bằng chứng để khẳng định claim đúng.

Cũng không nên coi một **risk acceptance** được ký là bằng chứng control đạt yêu cầu: phê duyệt rủi ro là quyết định quản trị, còn trạng thái claim vẫn phải phản ánh bằng chứng kỹ thuật và phạm vi.

## 3. Mô hình CAE và ba lớp chất lượng

**Claim–Argument–Evidence (CAE)** là cấu trúc nền tảng của nhiều assurance case. Khi dùng **Goal Structuring Notation (GSN)**, các nút Goal, Strategy, Context, Assumption, Justification và Solution giúp thể hiện các yếu tố tương ứng bằng sơ đồ. Ký pháp chỉ là phương tiện biểu diễn; giá trị thật nằm ở logic và bằng chứng.

### 3.1. Chất lượng claim

Một claim tốt cần:

- Chỉ rõ hệ thống, security property và mục đích.
- Có môi trường, release, thời điểm hoặc thời kỳ.
- Có tập asset, route, role, data flow hoặc quy trình cần bao phủ.
- Có tiêu chí đánh giá và điều kiện nghiệm thu.
- Nêu giả định và các phần nằm ngoài phạm vi.
- Có khả năng bị phản ví dụ bác bỏ nếu thực tế không đúng.

| Claim yếu | Điểm yếu | Claim được diễn đạt lại |
|---|---|---|
| “Hệ thống an toàn tuyệt đối” | Không có tiêu chí hoặc giới hạn | “Các đường API thuộc scope X thực thi chính sách authz Y ở release R” |
| “Dữ liệu đã mã hóa” | Không chỉ rõ trạng thái/loại dữ liệu | “Database D và backup B production mã hóa at rest với khóa K được quản lý” |
| “Không còn lỗ hổng critical” | Không rõ cách phát hiện và kỳ đánh giá | “Các finding critical trong tập kiểm tra F được sửa và retest theo tiêu chí C tại ngày T” |
| “DR phục hồi trong 4 giờ” | Thiếu T0, T1 và mức hoạt động | “Checkout đạt trạng thái phục hồi nghiệp vụ được duyệt ≤ 240 phút trong kịch bản S” |

Một phép kiểm tra hữu ích: **Có thể tưởng tượng một bằng chứng khiến claim sai không?** Nếu không, claim có thể là khẩu hiệu hoặc không đủ cụ thể.

### 3.2. Chất lượng argument

Lập luận phải cho thấy vì sao subclaims **cần thiết** và vì sao tập subclaim **đủ** để hỗ trợ claim cha trong phạm vi được chọn. Ví dụ G0 về tenant isolation cần:

- **G1:** Ma trận role, quyền và tenant ownership được phê duyệt.
- **G2:** Các đường truy cập đã kiểm kê thực thi object-level/tenant-level authorization ở server.
- **G3:** Các tình huống hợp lệ, bất hợp lệ, cross-tenant và role đặc biệt đã được kiểm thử.
- **G4:** Quyền, cấu hình, logging và giám sát vận hành theo chính sách trong thời kỳ được đánh giá.
- **G5:** Dependency, exception, các đường ngoài scope và residual risk đã được xem xét.

Nếu G2 thất bại trên một endpoint trọng yếu, bằng chứng tốt cho G1, G3 và G4 không đủ để kết luận G0 đã đạt, khi argument yêu cầu **tất cả điều kiện cùng đúng**.

### 3.3. Chất lượng evidence

Evidence phải hỗ trợ **đúng mệnh đề** và có thể kiểm chứng:

| Evidence | Có thể chứng minh | Chưa đủ chứng minh |
|---|---|---|
| Design review, threat model | Đã xem xét một thiết kế và threat trong scope | Control đã hoạt động trên production |
| IAM policy export | Cấu hình quyền tại mốc được lấy | Mọi phiên truy cập thực tế đều hợp lệ trong cả kỳ |
| Integration security test | Hành vi phù hợp trên các ca test, build và môi trường đã định | Không tồn tại đường tấn công chưa thử |
| Penetration test | Những kịch bản tấn công được kiểm tra có kết quả cụ thể | Hệ thống miễn nhiễm với mọi tấn công |
| Log và access review | Sự kiện và quy trình vận hành trong phạm vi thu thập | Sự kiện vắng mặt trong log chắc chắn chưa xảy ra |
| Báo cáo audit và retest | Control/finding được đánh giá theo criteria và period | Toàn bộ hệ thống đạt mọi tiêu chí ngoài audit |
| Risk acceptance có chữ ký | Có quyết định của người đủ thẩm quyền | Lỗ hổng kỹ thuật đã được khắc phục |

Một evidence record dù có nhãn PASS cũng cần kiểm tra dữ liệu nguồn, phương pháp, thời điểm và các điều kiện đã áp dụng.

## 4. Quy trình đánh giá confidence end-to-end

~~~mermaid
flowchart TD
    A["Xác định claim và mục đích quyết định"] --> B["Khóa scope, criteria, context và assumptions"]
    B --> C["Review cấu trúc argument / GSN"]
    C --> D["Xác minh evidence, coverage và provenance"]
    D --> E["Tìm defeaters, mâu thuẫn và lỗ hổng"]
    E --> F["Đánh giá từng subclaim"]
    F --> G{"Đủ bằng chứng và không có blocker trọng yếu?"}
    G -- "Chưa" --> H["NOT DEMONSTRATED / CONTRADICTED"]
    G -- "Có" --> I["SUPPORTED với confidence rationale"]
    H --> J["Action, retest và đánh giá lại"]
    I --> K["Independent review và quyết định theo rủi ro"]
    K --> J
    J --> A
~~~

**Bước 1 — Chốt mục tiêu quyết định.** Case phục vụ go-live, risk review, audit closure, DR readiness hay phê duyệt thay đổi? Ai sẽ dựa vào kết luận?

**Bước 2 — Chốt scope.** Nêu version, môi trường, thời gian, user role, asset, dependency, ranh giới dữ liệu và các trường hợp ngoài scope. Đưa threat model và security requirements đã duyệt vào context.

**Bước 3 — Review lập luận.** Kiểm tra quan hệ AND/OR, tiền đề, cách phân rã, mối quan hệ giữa claim và evidence, các đường tấn công hoặc phụ thuộc có thể bị bỏ sót.

**Bước 4 — Thẩm tra evidence.** Truy cập hiện vật gốc; xác minh nguồn, phương pháp thu thập, phiên bản, population, bộ lọc, kết quả và người kiểm tra.

**Bước 5 — Chủ động tìm phản chứng.** Xem failing test, audit findings, incident, security exception, thiếu log, dữ liệu mâu thuẫn hoặc bằng chứng trước khi có thay đổi lớn.

**Bước 6 — Đánh giá subclaims.** Ghi rõ điều đã hỗ trợ, chưa được chứng minh, bị trái hoặc nằm ngoài phạm vi. Không lấy trung bình nhiều nhánh PASS để bỏ qua một nhánh trọng yếu FAIL.

**Bước 7 — Đưa ra kết luận confidence.** Diễn giải độ mạnh của kết luận, những giới hạn, giả định nhạy cảm, mức kiểm chứng và các action cần thiết.

**Bước 8 — Review độc lập và duy trì hiệu lực.** Người có năng lực phù hợp phản biện case, người ra quyết định xử lý rủi ro; thay đổi hoặc phát hiện mới kích hoạt đánh giá lại.

## 5. Xác định độ bao phủ trước khi tin kết quả

Các số đo coverage chỉ có ý nghĩa khi tập **population** được xác minh đúng. Với claim “mọi tài khoản quản trị production có MFA”, population cần bao gồm mọi account có quyền cao, quyền kế thừa, tài khoản khẩn cấp và các cloud account liên quan; không chỉ tài khoản được xuất từ một bảng quản lý.

Một **scope/coverage matrix** có thể dùng:

| Chiều | Câu hỏi | Nguồn đối chiếu |
|---|---|---|
| Asset | Đã nhận diện mọi thành phần có thể xử lý hoặc lộ dữ liệu? | Asset inventory, IaC, runtime inventory |
| Route/flow | Có HTTP, export async, download, webhook, cache và version cũ? | Router, gateway, OpenAPI, tracing |
| Identity | Có end-user, support, admin, machine, break-glass? | IdP/IAM, role graph, approval |
| Environment | Staging có cùng policy và trust boundary với production? | Config diff, deployment manifests |
| Time | Evidence có đúng release/kỳ cần kết luận? | Audit trail, config history, release record |
| Threat | Có phản ánh đường tấn công và tài sản có tác động cao? | Threat model, attack tree, incident |
| Dependency | Có IdP, KMS, backup, nhà cung cấp và control plane? | Architecture, vendor assurance |

Ví dụ, bộ test chạm 47/48 endpoint được kiểm kê có **97,9% endpoint coverage theo inventory đó**. Nó không chứng minh độ an toàn 97,9%, cũng không cho phép kết luận cả 48 endpoint đều được bảo vệ. Endpoint chưa kiểm tra có thể là đường export với tác động lớn nhất.

### 5.1. Sampling và giới hạn suy luận

Nếu kiểm toán chọn 25 tài khoản trong population 120 tài khoản và thấy 3 exception, ta có bằng chứng về 3 trường hợp trong 25 mẫu. Không tự kết luận tỷ lệ vi phạm của toàn bộ 120 tài khoản là 12% nếu cách chọn mẫu không cho phép suy luận thống kê đó.

Lấy mẫu theo rủi ro giúp tìm đối tượng quan trọng nhưng có thể không đại diện; lấy mẫu xác suất có thể hỗ trợ ước lượng theo giả định thống kê xác định. **Khoảng tin cậy của tỷ lệ ngoại lệ** khác hoàn toàn **xác suất hệ thống không thể bị tấn công**.

Ngay cả khi test 100% đối tượng trong một bảng, phải xem bảng đó có **đầy đủ** không. Xác minh tính đầy đủ của population thường là một claim con cần evidence riêng.

## 6. Những sai lầm logic làm suy yếu argument

| Vấn đề | Ví dụ | Cách khắc phục |
|---|---|---|
| Thiếu tiền đề | Có MFA nên chắc chắn không bị truy cập trái quyền | Kiểm tra authz, session, role, exception, data path |
| Suy luận vòng | Control tốt vì audit PASS; audit PASS vì team cho biết control tốt | Dùng criteria và bằng chứng độc lập |
| Dùng sai evidence | Scan TLS để khẳng định phân quyền đúng | Gắn evidence với đúng thuộc tính bảo mật |
| Bỏ nhánh AND | Một trong ba luồng được bảo vệ nhưng G0 PASS | Viết rõ tất cả nhánh bắt buộc |
| Lập luận thiếu scope | Chỉ test user flow nhưng claim bao gồm admin | Nêu đường được kiểm tra và mở rộng |
| Dựa vào quyền uy | “Vendor nói đã compliant” | Xem report, phạm vi, kỳ, ngoại lệ, trách nhiệm chia sẻ |
| Nhân đôi nguồn | Ba dashboard cùng lấy một log thiếu dữ liệu | Ghi correlation, tìm nguồn kiểm tra độc lập |
| Bỏ qua phản chứng | Endpoint bypass còn tồn tại nhưng case ghi SUPPORTED | Đánh dấu claim bị challenge và retest sau fix |
| Evidence lỗi thời | Test ở release R-1 dùng cho claim release R | Kiểm tra thay đổi và thử lại |

Một bài kiểm tra hữu ích là giả định **mọi evidence đã nêu đều chính xác** rồi hỏi liệu claim còn có thể sai do đường khác không. Nếu có phản ví dụ quan trọng, argument có thể đang thiếu premise.

Đối với một claim về bí mật dữ liệu, chỉ chứng minh TLS và encryption at rest chưa đủ nếu một endpoint hợp lệ có thể bị lạm dụng để xuất dữ liệu tenant khác. Cần xét con đường tấn công end-to-end, không chỉ tính đúng của từng component.

## 7. Đánh giá chất lượng bằng chứng

Có thể sử dụng một bảng thuộc tính, ghi **đạt/chưa đạt/chưa đủ thông tin** với lời giải thích thay vì chỉ đếm hiện vật.

| Thuộc tính | Câu hỏi | Cách xác minh |
|---|---|---|
| **Relevance** | Bằng chứng có hỗ trợ đúng claim hoặc subclaim? | Mapping từng test/control tới criteria |
| **Sufficiency** | Số lượng và scope có đủ theo mức rủi ro? | So population, time window, scenario coverage |
| **Reliability** | Nguồn có đáng tin, có thể bị thao túng không? | Source system, quyền ghi, kiểm tra độc lập |
| **Accuracy** | Query, bộ lọc, nhãn, timestamp đúng? | Query/replay, so số record, chuẩn hóa timezone |
| **Integrity** | Có bị sửa/cắt sau khi thu thập? | Versioning, hash, audit trail, bảo quản phù hợp |
| **Timeliness** | Có phản ánh đúng release và kỳ đánh giá? | Deploy log, date, config change history |
| **Reproducibility** | Người khác có thể kiểm tra lại? | Test run ID, input, expected/actual, raw logs |
| **Independence** | Có lỗi chung hoặc tự đánh giá thiên lệch? | Kiểm tra lineage, reviewer độc lập |
| **Consistency** | Có evidence trái chiều? | Đối chiếu logs, scan, findings và incident |

**Hash** giúp phát hiện thay đổi nội dung tệp kể từ khi băm, không chứng minh nguồn dữ liệu đã đúng hoặc đủ trước khi băm. **Screenshot** thường chỉ mô tả một thời điểm, chưa đủ chứng minh vận hành liên tục. **Log không có sự kiện** chưa chứng minh sự kiện không xảy ra nếu chưa xác minh việc ghi log đúng nguồn, đúng kỳ và không bị thất lạc.

### 7.1. Mẫu evidence record

~~~yaml
evidence_id: EV-AUTHZ-014
claim_id: G2
type: security-integration-test
artifact_ref: "restricted/evidence/authz-report-014"
collected_at_utc: "2026-09-30T08:15:00Z"
system: customer-records-api
release: R-2026-09
environment: production-like
scope:
  endpoint_inventory_ref: "restricted/inventory/routes-2026-09"
  endpoints_total: 48
  endpoints_tested: 47
  roles: [customer, support, tenant-admin]
  cases: [own-tenant, cross-tenant, missing-token, expired-token]
source:
  test_run_id: SEC-AUTHZ-014
  collector_role: security-test-engineer
known_gap:
  - async-export-not-tested
review:
  independent_reviewer: pending
  integrity_record_ref: "restricted/evidence/hash-manifest"
~~~

Đây là ví dụ **giả định**, không phải evidence thật. Một record như trên giúp truy xuất, nhưng người đánh giá còn phải mở kết quả test, kiểm tra định nghĩa “tested”, các endpoint bị bỏ sót, phiên bản build thực tế và các limit của môi trường.

## 8. Bất định, giả định và defeaters

**Uncertainty** là những điều chưa biết hoặc chưa có độ chắc chắn cần thiết. Không phải mọi bất định đều khiến claim sai, nhưng phải đánh giá xem chúng có ảnh hưởng đến quyết định hay không.

| Nguồn bất định | Ví dụ | Hướng xử lý |
|---|---|---|
| Scope | Inventory chưa có async export | Đối chiếu router/runtime, mở rộng case |
| Threat model | Không xét session theft | Review attack scenarios và trust boundaries |
| Measurement | Log lệch múi giờ, timeout không ổn định | Đồng bộ thời gian, chuẩn hóa phép đo |
| Implementation | Test trên staging khác policy production | Config diff, production-safe verification |
| Temporal | Evidence trước đổi IdP/IAM | Impact analysis và retest |
| Supplier | Bên thứ ba không cung cấp scope audit phù hợp | Vendor assurance, test tích hợp, quản lý rủi ro |
| Sampling | Mẫu không đại diện nhóm quyền cao | Phân tầng, mở rộng hoặc ghi giới hạn |
| Adversarial | Đối thủ đổi attack strategy, xuất hiện CVE mới | Threat intelligence, security testing, monitoring |

### 8.1. Assumption không phải chứng cứ

Giả định “IdP cung cấp token hợp lệ theo cấu hình đã duyệt” cần có owner, lý do và điều kiện kiểm tra lại. Nếu claim đang cố chứng minh mọi endpoint dùng authorization middleware, **không thể giả định luôn điều đó**. Đây là lỗi lập luận vòng.

### 8.2. Ba loại defeater hữu ích

- **Rebutting defeater:** bằng chứng trực tiếp trái claim. Ví dụ endpoint export trả dữ liệu chéo tenant.
- **Undercutting defeater:** bằng chứng có thể đúng nhưng không hỗ trợ kết luận như dự tính. Ví dụ suite PASS trên build R-1 nhưng claim về release R.
- **Undermining defeater:** nguồn hoặc tiền đề bị nghi ngờ. Ví dụ log bị lọc thiếu account hoặc inventory không đầy đủ.

| Loại | Điều cần làm | Kết quả có thể |
|---|---|---|
| Rebutting | Sửa control, retest, đánh giá tác động | Claim vẫn CONTRADICTED tới khi có evidence mới hoặc scope hợp lệ |
| Undercutting | Chứng minh mối nối evidence–claim hoặc thu thập evidence đúng | Nếu chưa giải quyết: NOT DEMONSTRATED |
| Undermining | Sửa nguồn, xác minh population, kiểm tra độc lập | Evidence không đủ tin cậy cho tới khi kiểm chứng |

**Tạo ticket không đồng nghĩa giải quyết defeater.** Một finding ảnh hưởng trực tiếp claim phải tiếp tục được phản ánh cho đến khi đã sửa, thử lại và đánh giá phù hợp. Risk acceptance có thể cho phép ra quyết định có điều kiện, nhưng không tự chuyển claim sai thành đúng.

## 9. Độc lập và tương quan của bằng chứng

Ba báo cáo khác nhau có thể cùng được tạo từ một pipeline và cùng mang lỗi cấu hình. Số lượng báo cáo không tương đương số nguồn xác minh độc lập.

~~~text
Authorization unit tests -----+
                               +--> cùng code, fixtures và test oracle
CI coverage report ------------+

Runtime synthetic check -------> request qua đường API thực tế
Cloud IAM audit log ------------> identity control plane
Independent review ------------> phản biện threat model, route và test
~~~

Nguồn khác nhau có thể tăng khả năng phát hiện lỗi, nhưng vẫn phải xét điểm chung: synthetic check có dùng token đặc biệt khác user thật không, logging có bao phủ mọi account không, reviewer có kiểm tra hiện vật gốc hay chỉ đọc dashboard không?

**Độc lập thực sự có giá trị khi giảm khả năng sai cùng một nguyên nhân.** Không cần yêu cầu mọi artifact từ một nhà cung cấp khác, nhưng phải nhìn rõ lineage, xung đột lợi ích và quyền can thiệp vào nguồn.

## 10. Mức confidence: dùng thang định tính có giải thích

Không có thang confidence duy nhất áp dụng mặc định cho mọi assurance case. Tổ chức có thể dùng thang định tính phù hợp mục đích và mức rủi ro. Ví dụ:

| Mức | Ý nghĩa | Điều kiện điển hình |
|---|---|---|
| **High** | Lập luận và bằng chứng đủ mạnh trong scope, không còn khoảng trống trọng yếu chưa xử lý | Claim rõ, phân rã đủ, nguồn đáng tin, coverage phù hợp, review độc lập |
| **Moderate** | Có cơ sở hỗ trợ nhưng còn giới hạn đã được định rõ và quản lý | Một số kịch bản ít tác động chưa test, cần theo dõi hoặc bổ sung |
| **Low** | Thiếu premise, coverage hoặc evidence quan trọng | Chỉ có screenshot, thiếu nguồn độc lập hoặc chưa thử production |
| **Undetermined** | Chưa đủ dữ liệu để đánh giá | Không biết population, thiếu criteria hoặc nguồn không truy xuất được |

**Trạng thái claim cần ghi riêng**:

- **SUPPORTED:** evidence và lập luận hiện hỗ trợ claim trong scope.
- **NOT DEMONSTRATED:** chưa đủ bằng chứng để kết luận.
- **CONTRADICTED/CHALLENGED:** có phản chứng trực tiếp hoặc nghi vấn trọng yếu.
- **OUT OF SCOPE:** không phải mệnh đề đang đánh giá.

Hai trục này tránh nhầm lẫn. Ví dụ:

| Claim assessment | Confidence in assessment | Diễn giải |
|---|---|---|
| SUPPORTED | High | Có nền tảng bằng chứng mạnh hỗ trợ claim trong scope |
| SUPPORTED | Low | Kết luận tích cực dựa trên bằng chứng còn yếu; cần xem lại |
| NOT DEMONSTRATED | High | Rất chắc rằng bằng chứng hiện tại không đủ |
| CONTRADICTED | High | Có phản chứng đáng tin, tái hiện được |
| NOT DEMONSTRATED | Undetermined | Ngay cả nguồn hoặc phương pháp đánh giá cũng chưa đủ rõ |

Một field “confidence: HIGH” **không đủ rõ** nếu không nói đang tin **claim đúng** hay tin **kết luận assessment đúng**.

### 10.1. Tiêu chí cổng trước khi kết luận tích cực với confidence cao

Có thể đặt các cổng như:

1. Claim, criteria, scope, version và thời kỳ được chốt.
2. Không có tiền đề vòng hoặc nhánh bắt buộc bị thiếu.
3. Evidence khớp phiên bản, có nguồn gốc và khả năng truy xuất.
4. Đã xác minh population và coverage của các tài sản/luồng có rủi ro cao.
5. Phản chứng ảnh hưởng claim được xử lý hoặc claim được thay đổi minh bạch.
6. Bằng chứng có review, dependency và residual risk được giải thích.

Nếu thiếu **một cổng trọng yếu**, nhiều bằng chứng không liên quan không thể bù trừ. Đây là một quy tắc quản trị minh họa, cần điều chỉnh theo tiêu chí assurance của từng tổ chức.

## 11. Chỉ số định lượng: đừng tạo độ chính xác giả

Một đội có thể muốn tổng hợp các phần trăm:

~~~text
Security test pass: 100%
SAST checks pass: 100%
Benchmark checks pass: 100%

Trung bình = 100%
~~~

Điều này **không có nghĩa 100% xác suất hệ thống an toàn**. Các tỷ lệ đo những tập kiểm tra khác nhau; có thể cùng bỏ sót threat, cùng dùng version cũ hoặc cùng phụ thuộc một giả định sai. Không có mô hình xác suất đáng tin cho phép chuyển trung bình tỷ lệ PASS thành xác suất claim đúng.

Phương pháp Bayesian, reliability model hoặc thống kê có thể hỗ trợ khi định nghĩa rõ biến, dữ liệu, giả định độc lập/phụ thuộc, prior, likelihood và kiểm tra độ nhạy. Trong bảo mật, attacker chủ động thích nghi, lỗ hổng ít được quan sát và dữ liệu có thể bị thiếu; vì thế **một con số confidence tuyệt đối cần được giải thích đặc biệt cẩn trọng**.

### 11.1. Phân tích độ nhạy

Thường hữu ích hơn là đặt câu hỏi:

- Nếu thiếu một endpoint thuộc nhóm export, top-level claim còn đứng vững?
- Nếu IdP không ghi log 7 ngày, nhánh operating effectiveness đổi ra sao?
- Nếu role support có quyền rộng hơn threat model, kết luận bị ảnh hưởng đến đâu?
- Nếu kết quả test không đúng build production, evidence còn liên quan không?

Giả định nào khi thay đổi làm đảo ngược kết luận nên được đánh dấu **trọng yếu**, có owner và kế hoạch kiểm chứng.

### 11.2. Không suy luận thống kê sai

30/30 test PASS cho biết 30 tình huống đã được thử đạt theo tiêu chí, không chứng minh mọi input hay mọi hành vi tấn công đều an toàn. Khoảng tin cậy cho tỷ lệ lỗi trong một population được lấy mẫu đúng phương pháp vẫn không phải xác suất “hệ thống không có lỗ hổng”.

Khi một số liệu hỗ trợ quyết định, báo cáo nên nêu mẫu số, tập đối tượng, kỳ, phương pháp chọn, điều kiện PASS, dữ liệu nguồn và giới hạn.

## 12. Ví dụ end-to-end: đánh giá độ tin cậy của API đa tenant

Tình huống dưới đây là **giả định học tập**, không phải đánh giá một hệ thống thật.

### 12.1. Context và top-level claim

Một nền tảng SaaS có 48 endpoint hồ sơ khách hàng, vai trò customer, support và tenant-admin. Hệ thống có API gateway, backend service, asynchronous export và IdP.

**G0:** Đối với release R trên production, toàn bộ đường API trong inventory kiểm tra authz theo tenant/tài nguyên trước khi trả dữ liệu, theo requirement AUTHZ-01.

Các nhánh bắt buộc:

| Claim | Nội dung | Evidence |
|---|---|---|
| G1 | Quyền/role được định nghĩa và phê duyệt | Role matrix, policy version |
| G2 | Enforcement có mặt ở mọi đường thuộc scope | Inventory, code/config review, runtime test |
| G3 | Kịch bản tấn công trọng yếu được thử đúng build | Authz test, negative cases, pen test |
| G4 | Quyền, cấu hình, logging vận hành theo chính sách | IAM log, change events, access review |
| G5 | Các ngoại lệ, dependency và residual risk được đánh giá | Threat model, risk register, decision |

### 12.2. Evidence và các điểm yếu

| Evidence | Quan sát | Ý nghĩa |
|---|---|---|
| E1 | Role matrix v3 được phê duyệt | Hỗ trợ G1 |
| E2 | Inventory có 48 route; test chỉ chạy 47 | G2/G3 chưa đủ coverage |
| E3 | 47 route test PASS nhưng trên build R-1 | Undercutting: không khớp release R |
| E4 | Log IAM chỉ đủ 23/30 ngày | G4 chưa được chứng minh cho cả kỳ |
| E5 | Pen test tái hiện đọc dữ liệu chéo tenant qua export | Rebutting đối với G2 và G0 |
| E6 | Có ticket “fix merged” cho export | Chưa chứng minh deployment và retest |
| E7 | Có risk exception cho support role | Chứng minh quyết định rủi ro; chưa chứng minh G0 đạt |

### 12.3. Đánh giá lần đầu

~~~text
G1: SUPPORTED theo role matrix được duyệt.
G2: CONTRADICTED bởi lỗi chéo tenant ở export.
G3: NOT DEMONSTRATED đối với release R.
G4: NOT DEMONSTRATED cho cả kỳ vì thiếu log 7 ngày.
G5: PENDING_REVIEW đối với quyền support và dependency.

G0: CONTRADICTED trong phạm vi claim ban đầu.
Positive assurance cho G0: không có cơ sở kết luận High.

Confidence rằng endpoint export có lỗi:
  Có thể High nếu test tái hiện, đúng môi trường, độc lập kiểm chứng.

Decision: escalate tới owner có thẩm quyền, mở CAP và risk assessment.
~~~

Điểm đặc biệt: độ tin cậy vào **kết luận lỗi tồn tại** có thể cao, trong khi độ tin cậy vào **tuyên bố bảo mật G0** rất thấp. Không nên cố cộng các nhánh PASS để bù cho phản chứng trực tiếp.

### 12.4. Hành động và bằng chứng cần có

1. Sửa kiểm tra tenant/object ở bước tạo export job **và** khi nhận kết quả, bao gồm support/admin.
2. Đối chiếu router, OpenAPI, gateway và background jobs để xác nhận đủ đường đi.
3. Chạy security tests trên artifact R đã triển khai với cấu hình phù hợp, gồm unauthorized, missing token, cross-tenant và alternate roles.
4. Sửa logging ingestion, test event end-to-end và xác định phạm vi 7 ngày đã mất không thể khôi phục.
5. Đối chiếu IAM role với thực tế production; xem xét exception và đường đặc quyền.
6. Retest độc lập, ghi run ID, evidence link, người kiểm tra, timestamp và kết quả từng claim.
7. Cập nhật claim status và confidence rationale; không tự động đóng khi ticket chuyển “Done”.

### 12.5. Diễn giải kết quả sau khi sửa

Giả sử nhóm có:

- Deployment evidence xác nhận build R mới chứa bản sửa.
- 48/48 route được kiểm tra theo danh mục đã xác minh; có ca test cho async export và role đặc biệt.
- Pen-test retest không tái hiện lỗi cross-tenant theo các cách thử được mô tả.
- Logging hoạt động đầy đủ trong **cửa sổ kiểm tra mới**, có kiểm tra nguồn.
- Reviewer độc lập xác nhận test, coverage, assumptions và residual risks.

Có thể nâng kết luận cho các nhánh kỹ thuật tương ứng. Tuy nhiên, **log đầy đủ trong tháng 10 không chứng minh log đầy đủ trong 7 ngày thiếu của tháng 9**. Nếu G4 vẫn nói về tháng 9, trạng thái NOT DEMONSTRATED phải được giữ hoặc cần bằng chứng lịch sử khác đáng tin; không âm thầm thay giai đoạn để có PASS.

Một kết luận hợp lý:

> Trong release R và cửa sổ xác minh mới, các đường API thuộc inventory đã được kiểm tra theo tập kịch bản nêu rõ và không tái hiện truy cập chéo tenant; role policy, thay đổi và logging đã được xác minh theo evidence được dẫn chiếu. Kết luận giới hạn ở phiên bản, đường truy cập và cách thử được mô tả. Khoảng trống log 7 ngày của kỳ trước vẫn được quản lý như một hạn chế assurance chưa thể xác nhận lại.

Đó là kết luận có giá trị ra quyết định hơn câu “hệ thống đã an toàn 100%”.

## 13. Áp dụng cho IAM, data protection, DR và audit

### 13.1. Identity và Access Control

**Claim:** các tài khoản đặc quyền tương tác trên production phải có MFA và được phê duyệt trước khi cấp quyền.

Evidence cần: population từ nhiều nguồn, cấu hình enforcement của mọi đường đăng nhập, approval tickets, IAM change logs, exception register và các test tạo account qua luồng bình thường/khẩn cấp. Một screenshot MFA của một user chưa đủ cho toàn bộ account hoặc một quý.

### 13.2. Data Protection

**Claim:** dữ liệu nhóm nhạy cảm của DB D và backup B được mã hóa bằng khóa được quản lý, trong scope và thời kỳ T.

Evidence cần: inventory dữ liệu, KMS/HSM policy, cấu hình storage, key usage logs, test decrypt/restore, quyền quản trị khóa, giám sát thay đổi. Bằng chứng mã hóa DB không tự chứng minh backup có thể restore hoặc key không bị lộ.

### 13.3. Disaster Recovery

**Claim:** checkout đạt RTO 240 phút và RPO 15 phút trong kịch bản mất vùng chính với điều kiện nghiệp vụ và bảo mật đã phê duyệt.

Evidence cần: BIA, runbook, dependency map, timestamp T0/T1, failover log, độ mới dữ liệu, test giao dịch, integrity, IAM/KMS/logging và sign-off. Restore database 90 phút chỉ hỗ trợ một nhánh kỹ thuật; nếu diễn tập end-to-end kéo dài 320 phút, đó là phản chứng cần phản ánh trực tiếp.

### 13.4. Audit và evidence

**Claim:** quyền production được rà soát hằng quý và những quyền không còn cần thiết được thu hồi.

Evidence cần: population quyền, danh sách review, quyết định owner, biên bản, ticket thu hồi, trạng thái thực tế sau sửa, kết quả kiểm thử vận hành. Một biên bản họp review không tự chứng minh action đã hoàn thành.

## 14. Mẫu báo cáo confidence assessment

Báo cáo có ích cho người duyệt nên nêu:

| Trường | Nội dung |
|---|---|
| Case/Claim ID và version | Đúng claim đang xét |
| Decision context | Ai sẽ dùng đánh giá cho quyết định gì |
| Scope, period, assumptions | Ranh giới, dependency, điều kiện |
| Criteria/argument strategy | Yêu cầu và logic phân rã |
| Evidence index | Hiện vật gốc, nguồn, thời điểm, phương pháp |
| Defeaters & uncertainties | Phản chứng, thiếu coverage, giả định trọng yếu |
| Claim assessment | SUPPORTED / NOT DEMONSTRATED / CONTRADICTED |
| Confidence in assessment | Mức định tính và giải thích |
| Residual risks | Rủi ro, người có thẩm quyền, thời hạn |
| Decision & conditions | Chấp nhận, hoãn, hoặc điều kiện |
| Owner/reviewer | Người bảo trì và người xác minh |
| Review triggers | Thay đổi cần kiểm tra lại |

~~~yaml
confidence_assessment:
  case_id: AC-EXAMPLE-2026
  case_version: "2.0"
  claim_id: G0
  release: R
  environment: production
  assessed_at_utc: "2026-10-15T09:30:00Z"
  objective: "Tenant-level API authorization"
  criteria_ref: "restricted/requirements/AUTHZ-01"
  evidence:
    - id: E8
      role: deployment-proof
      result: VERIFIED
    - id: E9
      role: authorization-test
      result: VERIFIED
    - id: E11
      role: logging-operation
      result: PARTIAL
  subclaims:
    G1: SUPPORTED
    G2: SUPPORTED
    G3: SUPPORTED
    G4: NOT_DEMONSTRATED
    G5: PENDING_REVIEW
  overall_claim_status: NOT_DEMONSTRATED
  confidence_in_assessment: HIGH
  rationale: >
    Technical evidence supports the scoped implementation.
    Historical operation is not demonstrated for the full period.
  material_limitations:
    - historical-log-gap
    - support-role-review-pending
  open_defeaters:
    - finding_id: LOG-EXAMPLE-004
      disposition: tracked
  reviewer_role: INDEPENDENT_SECURITY_REVIEWER
  decision: "No unrestricted assurance endorsement"
  next_review_triggers:
    - IAM-policy-change
    - new-data-export-route
    - material-incident
~~~

Trong ví dụ, **HIGH** là mức tin cậy vào nhận định **NOT DEMONSTRATED**, không phải xác suất hệ thống an toàn cao. Tất cả tên, số liệu, timestamp và đường dẫn đều là placeholder học tập; cần liên kết bằng chứng thật khi sử dụng.

## 15. Phản biện độc lập và điều kiện nâng confidence

Một reviewer nên chọn vài nhánh quan trọng và **thử bác bỏ** lập luận:

1. Đọc top claim, hỏi về đối tượng, version, scope và điều kiện nghiệm thu.
2. Kiểm tra strategy AND/OR và hỏi subclaims nào còn thiếu để chống threat đã biết.
3. Tìm một đường tấn công có thể làm claim sai dù mọi evidence hiện tại đều đúng.
4. Kiểm tra ngẫu nhiên có chủ đích những evidence gốc, run IDs, query, timestamp, version.
5. Xác minh population completeness bằng nguồn thứ hai.
6. Tìm nguồn chung khiến nhiều dashboard/test có thể sai giống nhau.
7. Kiểm tra mọi finding, incident và exception ảnh hưởng claim.
8. Xem xét residual risk, thẩm quyền phê duyệt và hạn điều kiện.
9. Kiểm tra trigger khiến evidence hoặc assumption không còn hiệu lực.
10. Ghi phát hiện, owner, hành động, deadline và yêu cầu retest.

Không cần đòi hỏi bằng chứng cho “mọi kịch bản trên thế giới” để chấp nhận case. Mục tiêu là **mức assurance tương xứng với rủi ro và quyết định**, cùng giới hạn được phát biểu chính xác. Review không nên chỉ đếm file hay số ô xanh.

## 16. Confidence trong SDLC và vận hành liên tục

Độ tin cậy có thể giảm **mà không cần sửa một chữ trong case** khi production đã thay đổi.

Các trigger điển hình:

- Thêm endpoint, user role, dữ liệu nhạy cảm, cloud account hoặc nhà cung cấp.
- Thay IAM, IdP, KMS, network, TLS, routing hoặc trust boundary.
- Có vulnerability, incident, audit finding, failing test hay log gap mới.
- Mở rộng dung lượng hoặc tải khiến DR drill cũ không đại diện.
- Quá hạn freshness của evidence hoặc audit period đã khác.
- Thay đổi security requirements, risk tolerance hoặc threat model.
- Tool, test suite, policy-as-code hoặc nguồn telemetry không còn bao phủ đối tượng.

~~~text
Change / finding / incident
          ↓
Tìm các claim và evidence bị ảnh hưởng
          ↓
Đánh giá impact tới scope, premises và defeaters
          ↓
Đánh dấu NEEDS_REVIEW / invalidated nếu cần
          ↓
Thu thập và xác minh evidence mới
          ↓
Independent review và cập nhật assessment
          ↓
Versioned decision + điều kiện giám sát
~~~

Một test của release R-1 có thể **hoàn toàn đúng đối với R-1** nhưng không còn đủ cho claim release R. Traceability từ control, cấu hình, test, evidence và version tới claim giúp xác định chính xác phần cần đánh giá lại thay vì duyệt lại mọi thứ vô điều kiện.

Có thể theo dõi số claim trọng yếu NOT DEMONSTRATED, số defeater chưa đóng, tỷ lệ evidence quá hạn, thay đổi chưa có impact assessment và lần retest thất bại. Đây là **chỉ số về chất lượng chương trình assurance**, không tự tạo thành một xác suất an toàn tổng thể.

## 17. Các sai lầm thường gặp

| Sai lầm | Hệ quả | Hướng sửa |
|---|---|---|
| “100% test PASS = 100% an toàn” | Tạo độ chính xác giả | Báo scope, scenario, version và giới hạn |
| Claim không có đối tượng/thời kỳ | Không xác minh được | Chốt asset, môi trường, release và criteria |
| Một control xanh làm cả G0 xanh | Bỏ qua các nhánh bắt buộc | Kiểm tra logic phân rã và dependency |
| Dùng scan phù hợp sai claim | Lập luận không hợp lệ | Ánh xạ từng evidence tới thuộc tính |
| Chỉ đo coverage trên inventory thiếu | Bỏ sót tài sản | Đối chiếu inventory từ nguồn độc lập |
| Đếm nhiều dashboard chung một log là độc lập | Không nhận ra lỗi nguồn chung | Kiểm tra lineage và correlation |
| Screenshot cuối kỳ thay toàn bộ bằng chứng lịch sử | Không chứng minh vận hành liên tục | Thêm config history và event logs |
| Bỏ finding còn mở vì đã có CAP | Phản chứng vẫn còn | Giữ trạng thái challenged tới khi retest |
| Nhầm risk accepted với compliant | Báo cáo sai tình trạng control | Tách quyết định quản trị và claim assessment |
| Thay scope sau FAIL mà không ghi nhận | Kết luận bị làm đẹp | Version hóa, công bố giới hạn và phê duyệt |
| Tin vào một điểm confidence không có công thức | Khó kiểm tra hoặc phản biện | Thang có tiêu chí, rationale, điều kiện chặn |
| Không review sau thay đổi | Evidence lỗi thời | Trigger impact review, retest, update |
| Tự đánh giá mọi evidence do chính nhóm tạo | Thiên lệch khó phát hiện | Review độc lập tương xứng rủi ro |
| Thiếu evidence được diễn giải thành chắc chắn có vi phạm | Suy luận vượt dữ liệu | Phân biệt NOT DEMONSTRATED và CONTRADICTED |

## 18. Bài tập thực hành

### Tình huống A — Claim quá rộng

Nhóm dự án báo cáo: “Hệ thống an toàn vì SAST xanh, pen test không có critical và TLS đã bật.”

1. Viết lại một claim có security property, release, môi trường, scope và criteria rõ.
2. Nêu từng evidence có thể hỗ trợ những thuộc tính nào; thuộc tính nào chưa chứng minh?
3. Phân rã claim thành ít nhất bốn nhánh và gắn evidence plan.
4. Nêu ba defeater có thể làm claim sai dù tất cả thông tin trên là thật.
5. Đề xuất mức confidence có lý do và các bước nâng mức ấy.

### Tình huống B — Coverage và role

API có 60 route, bộ security test chạy 54 route và đều PASS; một endpoint export và một support role có quyền rộng chưa được thử. Inventory còn thiếu xác minh một cloud account.

1. Kết luận chính xác từ 54/60 test là gì?
2. Vì sao 90% route coverage không tương đương 90% mức an toàn?
3. Cần evidence bổ sung về population, flow và role nào?
4. Phân biệt một lỗi export (rebutting), test build sai (undercutting) và inventory thiếu (undermining).
5. Management chấp nhận support-role risk có làm claim “mọi truy cập chéo tenant đều bị chặn” thành PASS không?

### Tình huống C — Evidence sau sửa

Claim nói “tất cả sự kiện quản trị production được gửi SIEM trong quý III”. Audit tìm thấy logging thiếu 9 ngày tháng 8. Sau khi sửa, tháng 10 có đầy đủ log và test alert PASS.

1. Claim về quý III được đánh giá thế nào?
2. Có thể viết claim mới cho tháng 10 với điều kiện nào?
3. Phân biệt evidence về control hiện hoạt động và evidence về kỳ cũ.
4. Lập một assessment record gồm status, confidence rationale, open limitations và reviewer.
5. Chọn trigger review khi có thêm cloud account.

### Tình huống D — Phản biện scoring

Một đội tính: unit tests PASS 100%, SAST PASS 100%, benchmark PASS 100%; trung bình bằng 100%, do đó “confidence 100%, mọi release tương lai đều an toàn”.

Hãy phản biện về logic xác suất, sự tương quan giữa nguồn, thiếu scope/threat, độ đại diện của test, yếu tố vận hành production và điều kiện cần đánh giá lại.

**Gợi ý:** Đánh giá đúng phải phân biệt **evidence có thật hay không**, **evidence có liên quan và đủ hay không**, **argument có dẫn đến claim không** và **người ra quyết định chấp nhận những rủi ro còn lại nào**.

## 19. Ghi nhớ

**Đánh giá độ tin cậy của assurance case** là xem xét có phương pháp rằng một claim được hỗ trợ bởi **lập luận có cấu trúc và bằng chứng đúng, đủ phạm vi, đáng tin, còn hiệu lực**, đồng thời mọi giả định, khoảng trống và phản chứng trọng yếu được xử lý minh bạch.

Khi review một case, hãy hỏi: **Claim đang nói gì và áp dụng ở đâu? Argument có đầy đủ không? Evidence có chứng minh đúng thuộc tính không? Population có đủ không? Có nguồn lỗi chung, dữ liệu lỗi thời hay phản chứng chưa giải quyết? Confidence là về tính đúng của claim hay về sự đáng tin của kết luận đánh giá? Khi nào phải đánh giá lại?**

Trong **SECURITY_SECURITY_ASSURANCE**, chuỗi ra quyết định đáng tin là:

**Mục tiêu bảo mật / rủi ro → claim có phạm vi → argument có thể phản biện → evidence được thẩm tra → đánh giá bất định và defeaters → kết luận có confidence rationale → quyết định có thẩm quyền → retest và cập nhật liên tục.**

Mức bảo đảm không được tạo ra bằng nhiều ô xanh hoặc điểm số không giải thích được. Nó được tạo ra bằng khả năng **chỉ ra vì sao kết luận đáng tin đến mức nào, dựa trên bằng chứng nào, còn thiếu gì và điều gì sẽ làm kết luận cần xem xét lại**.
