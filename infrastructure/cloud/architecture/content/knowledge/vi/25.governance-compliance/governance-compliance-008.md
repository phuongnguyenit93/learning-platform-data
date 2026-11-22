# Quản lý ngoại lệ, thời hạn khắc phục và chấp nhận rủi ro

> **Chương:** Quản trị và tuân thủ  
> **Phạm vi:** Thiết kế kiến trúc ứng dụng trên đám mây từ yêu cầu nghiệp vụ đến mạng, compute, dữ liệu và mô hình triển khai. Bài học tập trung vào cách quản trị các trường hợp kiến trúc hoặc cấu hình chưa đáp ứng tiêu chuẩn, đặt thời hạn khắc phục có căn cứ và chấp nhận rủi ro minh bạch, có thẩm quyền, có thời hạn và có thể kiểm toán.

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt security finding, nonconformity, risk, issue, exception, waiver và risk acceptance.
2. Thiết kế vòng đời quản lý ngoại lệ từ phát hiện, phân loại, đánh giá tác động, phê duyệt, kiểm soát bù trừ, khắc phục đến đóng hồ sơ.
3. Thiết lập remediation SLA theo mức độ nghiêm trọng, khả năng khai thác, mức phơi lộ, tính quan trọng của tài sản và nghĩa vụ tuân thủ.
4. Xác định người có thẩm quyền chấp nhận rủi ro, phạm vi quyết định, giới hạn thời gian, điều kiện từ chối và trách nhiệm theo dõi.
5. Xây dựng risk register, exception register, remediation plan, bằng chứng kiểm soát và audit trail.
6. Theo dõi rủi ro tồn đọng, ngoại lệ quá hạn, tái diễn và tác động của chúng tới Well-Architected, SLO, chi phí và năng lực vận hành.

## 1. Vì sao cần quản lý ngoại lệ và chấp nhận rủi ro?

Trong kiến trúc cloud, tiêu chuẩn và guardrail định nghĩa trạng thái mong muốn: dữ liệu nhạy cảm phải mã hóa, workload phải dùng danh tính riêng, backup phải phục hồi được, endpoint quản trị không được công khai và phiên bản runtime phải còn được hỗ trợ.

Thực tế không phải lúc nào cũng đáp ứng ngay. Ví dụ:

- Một hệ thống kế thừa chưa hỗ trợ workload identity và vẫn cần credential dài hạn.
- Database cũ chưa thể nâng phiên bản vì ứng dụng phụ thuộc driver chưa tương thích.
- Một bucket cần public trong thời gian ngắn để phát hành tài nguyên, nhưng chưa có cơ chế phân phối thay thế.
- Một lỗ hổng có bản vá nhưng cần kiểm thử regression trước khi triển khai.
- Một vùng cloud chưa có dịch vụ tương đương để đáp ứng yêu cầu mã hóa hoặc lưu trú dữ liệu.
- Một nhóm dự án muốn trì hoãn kiểm soát logging vì chi phí và ảnh hưởng hiệu năng chưa được đo.

Nếu không có quy trình quản trị, các trường hợp này dễ biến thành ngoại lệ vô thời hạn: không ai sở hữu, không có thời hạn, không có kiểm soát bù trừ và không được đánh giá lại khi bối cảnh thay đổi.

**Ngoại lệ là một quyết định quản trị có phạm vi và thời hạn, không phải trạng thái miễn tuân thủ mặc định.** Chấp nhận rủi ro là quyết định có trách nhiệm của người có thẩm quyền sau khi hiểu rủi ro còn lại và các phương án xử lý. Một ticket bị đóng hoặc một finding được chuyển sang trạng thái accepted không tự làm rủi ro biến mất.

Mục tiêu của governance là làm cho quyết định có thể giải thích, theo dõi và thay đổi khi bằng chứng mới xuất hiện; không phải tạo thêm thủ tục cho mọi thay đổi kỹ thuật.

## 2. Phân biệt các khái niệm

Các đội thường dùng lẫn lộn "finding", "risk", "issue", "exception" và "waiver". Phân biệt chúng giúp tránh việc một phát hiện kỹ thuật bị coi như quyết định chấp nhận rủi ro.

| Khái niệm | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **Finding** | Quan sát hoặc kết quả kiểm tra cho thấy điều kiện đáng xem xét | Scanner phát hiện image có CVE nghiêm trọng |
| **Nonconformity** | Không đáp ứng một yêu cầu, chính sách hoặc tiêu chuẩn đã xác định | Database không bật encryption at rest theo baseline |
| **Risk** | Khả năng và hậu quả của một sự kiện ảnh hưởng mục tiêu | Kẻ tấn công khai thác CVE để chiếm workload |
| **Issue** | Vấn đề đang tồn tại cần xử lý | Connector CDC đã mất log position |
| **Remediation** | Công việc giảm hoặc loại bỏ nguyên nhân/rủi ro | Nâng image base, cập nhật library và redeploy |
| **Exception** | Cho phép tạm thời sai lệch khỏi một yêu cầu cụ thể theo điều kiện đã phê duyệt | Tạm dùng một cơ chế xác thực thay thế trong 30 ngày |
| **Waiver** | Thuật ngữ tổ chức dùng cho miễn trừ/không áp dụng yêu cầu; phạm vi khác nhau giữa policy | Miễn một yêu cầu kiểm soát cho một môi trường đặc biệt |
| **Risk acceptance** | Quyết định chủ thể có thẩm quyền nhận phần rủi ro còn lại | Business risk owner chấp nhận nguy cơ gián đoạn có giới hạn trong thời gian migration |
| **Compensating control** | Kiểm soát thay thế/bổ sung giảm rủi ro khi kiểm soát chuẩn chưa thể áp dụng | Private network, IP allowlist và secret rotation thay cho một tính năng IAM chưa có |

Một finding có thể không dẫn tới exception nếu sửa ngay. Một exception có thể có nhiều finding liên quan. Một risk có thể tồn tại dù không có nonconformity, ví dụ phụ thuộc vào nhà cung cấp bên ngoài. Một waiver không nhất thiết đồng nghĩa với risk acceptance; phải dùng định nghĩa chính thức của tổ chức.

### 2.1. Bốn quyết định xử lý rủi ro

| Cách xử lý | Khi nào dùng | Ví dụ |
| --- | --- | --- |
| **Avoid** | Thay đổi hoạt động/thiết kế để loại bỏ nguồn rủi ro | Không triển khai public endpoint; bỏ tính năng không đáp ứng yêu cầu |
| **Mitigate / reduce** | Áp dụng kiểm soát giảm likelihood hoặc impact | Patch, segmentation, MFA, rate limit |
| **Transfer / share** | Chuyển/chia sẻ một phần hậu quả qua hợp đồng, bảo hiểm hoặc nhà cung cấp | Bảo hiểm cyber, điều khoản trách nhiệm với processor |
| **Accept / retain** | Chấp nhận rủi ro còn lại có chủ đích và đúng thẩm quyền | Chấp nhận downtime ngắn cho một báo cáo nội bộ |

Chuyển giao rủi ro không loại bỏ nghĩa vụ của tổ chức đối với khách hàng, dữ liệu hoặc cơ quan quản lý. Thuê cloud provider không có nghĩa provider nhận toàn bộ rủi ro ứng dụng và dữ liệu.

## 3. Vòng đời quản lý ngoại lệ

Một quy trình hiệu quả có trạng thái rõ ràng, điều kiện chuyển trạng thái và owner chịu trách nhiệm.

~~~mermaid
flowchart TD
    A["Phát hiện finding / yêu cầu ngoại lệ"] --> B["Ghi nhận tài sản, policy và evidence"]
    B --> C["Phân loại mức độ và đánh giá risk"]
    C --> D{"Có thể khắc phục ngay?"}
    D -->|"Có"| E["Lập remediation plan"]
    D -->|"Chưa thể"| F["Đề xuất exception + compensating controls"]
    F --> G{"Đúng thẩm quyền phê duyệt?"}
    G -->|"Không"| H["Từ chối / escalated / đổi thiết kế"]
    G -->|"Có"| I["Phê duyệt có thời hạn và điều kiện"]
    E --> J["Thực hiện và kiểm chứng"]
    I --> K["Theo dõi control, deadline và trigger"]
    K --> J
    J --> L{"Bằng chứng đạt yêu cầu?"}
    L -->|"Chưa"| M["Mở lại / gia hạn chỉ khi đủ điều kiện"]
    L -->|"Đạt"| N["Đóng finding và thu hồi exception"]
    M --> K
~~~

### 3.1. Các bước trong vòng đời

1. **Phát hiện:** từ scanner, audit, architecture review, pen test, incident, thay đổi luật/chính sách hoặc yêu cầu dự án.
2. **Ghi nhận:** liên kết finding với tài sản, service, environment, policy/control, evidence và owner.
3. **Đánh giá:** xác định threat scenario, likelihood, impact, exposure, blast radius, dependency và nghĩa vụ liên quan.
4. **Chọn treatment:** avoid, mitigate, transfer/share hoặc accept; nêu các phương án đã cân nhắc.
5. **Lập kế hoạch:** action, owner, deadline, dependency, test, rollback và tiêu chí hoàn thành.
6. **Phê duyệt:** đúng risk owner và cấp có thẩm quyền; Security/Compliance tư vấn hoặc xác nhận kiểm soát theo vai trò.
7. **Theo dõi:** trạng thái, kiểm soát bù trừ, telemetry, deadline, trigger và cảnh báo.
8. **Kiểm chứng:** thu bằng chứng sau remediation; không chỉ dựa vào lời xác nhận của người thực hiện.
9. **Đóng hoặc xem xét lại:** đóng khi rủi ro đã giảm theo tiêu chí; mở lại khi tái diễn; exception hết hạn phải chuyển về remediation, re-approval hoặc dừng hoạt động theo policy.

### 3.2. Trạng thái ngoại lệ tham khảo

| Trạng thái | Ý nghĩa | Điều kiện chuyển tiếp |
| --- | --- | --- |
| Draft | Đang thu thập thông tin | Đủ phạm vi, owner, risk scenario |
| Submitted | Đã gửi đánh giá/phê duyệt | Risk assessment hoàn chỉnh |
| Under review | Đang thẩm định | Có ý kiến và bằng chứng cần thiết |
| Approved | Được chấp thuận có thời hạn | Có approver, expiry, conditions |
| Rejected | Không được chấp thuận | Có hướng remediation/thiết kế khác |
| Active | Kiểm soát bù trừ đang vận hành | Có evidence và monitoring |
| Remediating | Đang triển khai khắc phục | Có plan, owner và ETA |
| Pending validation | Chờ kiểm chứng độc lập | Có evidence hoàn thành |
| Expired | Đã hết hạn | Không được tự tiếp tục dựa trên phê duyệt cũ |
| Closed | Đã khắc phục và xác nhận | Evidence đạt, quyền ngoại lệ đã thu hồi |
| Revoked | Bị thu hồi trước hạn | Trigger/điều kiện vi phạm hoặc risk tăng |

Không phải tổ chức nào cũng cần tất cả trạng thái. Quan trọng là không gộp "đã phê duyệt", "đã triển khai kiểm soát" và "đã khắc phục" vào một trạng thái duy nhất.

## 4. Đánh giá rủi ro trước khi xin ngoại lệ

Không thể phê duyệt có ý nghĩa nếu không biết điều gì có thể xảy ra, với tài sản nào, trong điều kiện nào và hậu quả gì.

### 4.1. Viết risk scenario cụ thể

Một risk statement hữu ích có cấu trúc:

**Do [điều kiện/nguyên nhân], [threat event] có thể xảy ra với [tài sản/quy trình], dẫn đến [hậu quả đối với mục tiêu].**

Ví dụ:
- Do API quản trị còn công khai và chỉ dùng password, kẻ tấn công có thể chiếm tài khoản vận hành, dẫn đến thay đổi cấu hình production và lộ dữ liệu tenant.
- Do database chạy phiên bản hết hỗ trợ, một lỗ hổng chưa được vá có thể bị khai thác, dẫn đến gián đoạn dịch vụ và truy cập trái phép.
- Do backup dùng cùng quyền xóa với production, ransomware hoặc tài khoản bị chiếm có thể phá cả dữ liệu chính lẫn bản sao phục hồi.

Tránh statement mơ hồ như "có rủi ro bảo mật" hoặc "cần nâng cấp hệ thống". Không có threat scenario thì khó đánh giá likelihood, impact và treatment.

### 4.2. Các yếu tố đánh giá

- **Asset criticality:** giá trị nghiệp vụ, dữ liệu, nghĩa vụ và khả năng thay thế.
- **Exposure:** public/private, reachable path, authentication và network segmentation.
- **Threat capability/intent:** tác nhân, mức độ phổ biến của exploit và khả năng bị nhắm tới.
- **Exploitability:** điều kiện cần, quyền cần có, mức độ dễ khai thác.
- **Vulnerability/control state:** phiên bản, cấu hình, safeguard hiện có và hiệu quả đã kiểm chứng.
- **Impact:** confidentiality, integrity, availability, tài chính, pháp lý, an toàn và uy tín.
- **Scope/blast radius:** số tenant, dữ liệu, region, service và downstream bị ảnh hưởng.
- **Detectability/recovery:** khả năng phát hiện, containment, backup và phục hồi.
- **Uncertainty:** chất lượng bằng chứng, giả định và điều chưa biết.

Không dùng một điểm CVSS, một scanner finding hay một nhãn "High" làm toàn bộ risk assessment. Severity kỹ thuật là đầu vào; risk phụ thuộc bối cảnh triển khai và business impact.

### 4.3. Ma trận likelihood và impact

Có thể dùng ma trận định tính để sàng lọc:

| Likelihood \ Impact | Thấp | Trung bình | Cao | Nghiêm trọng |
| --- | --- | --- | --- | --- |
| Rất thấp | Thấp | Thấp | Trung bình | Cao |
| Thấp | Thấp | Trung bình | Cao | Cao |
| Có thể | Trung bình | Cao | Cao | Rất cao |
| Cao | Cao | Cao | Rất cao | Rất cao |
| Gần chắc chắn | Cao | Rất cao | Rất cao | Rất cao |

Đây là ma trận minh họa, không phải thang đo chuẩn chung. Tổ chức phải định nghĩa thế nào là likelihood/impact, kỳ thời gian, risk appetite, cách xử lý trường hợp pháp lý bắt buộc và ngưỡng escalations.

### 4.4. Inherent risk và residual risk

- **Inherent risk:** mức rủi ro trước khi xét các kiểm soát.
- **Residual risk:** mức còn lại sau khi xét kiểm soát đang có và hiệu quả đã được chứng minh.
- **Target risk:** mức dự kiến sau khi hoàn thành các action đã cam kết.

Không được ghi residual risk dựa trên kiểm soát chỉ mới dự định triển khai. Nếu kiểm soát bù trừ chưa hoạt động hoặc chưa có evidence, phải phản ánh sự thật đó trong đánh giá và phê duyệt.

## 5. Phân loại mức độ và remediation SLA

Remediation SLA là thời hạn mục tiêu để xử lý một nhóm finding/rủi ro theo chính sách. Nó không phải lời hứa rằng mọi finding cùng một mức severity đều có cùng độ nguy hiểm trong mọi bối cảnh.

### 5.1. Xây policy thời hạn có căn cứ

Một policy có thể quy định thời hạn tối đa theo severity, sau đó áp dụng escalation theo asset criticality, exposure, exploitability và nghĩa vụ bên ngoài. Ví dụ minh họa:

| Nhóm finding | Thời hạn mục tiêu giả định | Cách xử lý |
| --- | ---: | --- |
| Critical, exploitable, public hoặc đã bị khai thác | 24–72 giờ để containment và kế hoạch xử lý khẩn | Incident/security escalation, ưu tiên vá/cô lập |
| High | 7–15 ngày | Owner và remediation plan có giám sát sát |
| Medium | 30–60 ngày | Xếp lịch theo rủi ro và dependency |
| Low | 90–180 ngày hoặc chu kỳ chuẩn | Gom theo release, theo dõi tồn đọng |
| End-of-life/unsupported critical platform | Theo kế hoạch migration riêng, có mốc interim | Đánh giá exposure, compensating controls và quyết định cấp cao |

Các con số chỉ là ví dụ chính sách, không phải quy định pháp luật hoặc tiêu chuẩn bắt buộc. Sự cố đang bị khai thác có thể cần containment ngay, bất kể finding ban đầu được xếp mức nào.

### 5.2. Tách containment, remediation và closure

Đặc biệt với finding nghiêm trọng, ba mốc cần phân biệt:

- **Containment deadline:** thời điểm phải giảm ngay khả năng bị khai thác hoặc giới hạn blast radius.
- **Remediation deadline:** thời điểm hoàn thành sửa nguyên nhân gốc, ví dụ patch, migration hoặc thay thiết kế.
- **Validation/closure deadline:** thời điểm có bằng chứng độc lập rằng sửa đổi hiệu quả và không làm phát sinh vấn đề mới.

Ví dụ một API quản trị public có thể được hạn chế ingress và buộc MFA trong vài giờ để containment; việc chuyển sang private endpoint và workload/admin identity hoàn tất trong sprint sau; Security xác minh negative tests trước khi đóng finding.

### 5.3. SLA theo risk-adjusted priority

Thời hạn có thể được rút ngắn khi:
- Exploit đã có trong thực tế hoặc có exploit code dễ sử dụng.
- Tài sản public-facing hoặc chứa dữ liệu nhạy cảm/critical.
- Có dấu hiệu compromise hoặc control đã bị bypass.
- Một finding ảnh hưởng nhiều service/tenant/region.
- Nghĩa vụ hợp đồng, luật hoặc policy nội bộ đặt deadline ngắn hơn.

Có thể có thời hạn dài hơn khi đã có containment hiệu quả, exploitability thấp, migration phức tạp và risk owner phê duyệt kế hoạch có mốc rõ. Việc gia hạn không được tự động chỉ vì nhóm kỹ thuật bận hoặc release window chưa thuận tiện.

### 5.4. Cảnh báo và escalation

Ví dụ escalation workflow:

| Mốc | Hành động |
| --- | --- |
| 50% thời gian còn lại | Nhắc owner, kiểm tra dependency và blocker |
| 75% | Thông báo manager/service owner, yêu cầu cập nhật bằng chứng |
| 90% | Security/GRC review risk, kiểm tra interim controls |
| Đến hạn | Escalate risk owner, không tự gia hạn |
| Quá hạn | Đánh dấu overdue, đánh giá lại risk và áp dụng policy escalation |
| Trigger nghiêm trọng | Reassess ngay, có thể revoke exception hoặc chuyển incident |

Các tỷ lệ là gợi ý để thiết kế cảnh báo, cần tùy chỉnh theo SLA thật. Đặc biệt, hệ thống phải tính thời gian theo múi giờ, ngày nghỉ, clock source và điểm bắt đầu rõ ràng.

## 6. Ngoại lệ tốt phải có phạm vi, lý do và thời hạn

Một yêu cầu exception nên trả lời tối thiểu:

1. **What:** yêu cầu/control nào chưa đáp ứng và bằng chứng nào chứng minh?
2. **Where:** account, environment, region, service, resource, tenant và version nào bị ảnh hưởng?
3. **Why:** lý do kỹ thuật/nghiệp vụ nào khiến chưa thể đáp ứng?
4. **Risk:** threat scenario, likelihood, impact và residual risk?
5. **Alternatives:** đã xem xét thay đổi kiến trúc, tắt chức năng hoặc phương án khác chưa?
6. **Controls:** kiểm soát bù trừ nào đang hoạt động, ai vận hành và đo bằng gì?
7. **Owner:** ai chịu trách nhiệm remediation và ai là risk owner chấp nhận rủi ro?
8. **Time:** bắt đầu, expiry, remediation milestone và review date?
9. **Evidence:** link tới ticket, policy, test, log, scan, architecture diagram?
10. **Triggers:** điều kiện nào buộc đánh giá lại hoặc thu hồi phê duyệt?

### 6.1. Không chấp nhận lý do không thể kiểm chứng

Lý do "legacy system", "chi phí cao", "ảnh hưởng performance" hoặc "đội chưa có thời gian" chưa đủ. Phải mô tả ràng buộc cụ thể: phiên bản phụ thuộc, benchmark, chi phí dự kiến, deadline migration và phương án giảm rủi ro trong thời gian chờ.

### 6.2. Scope phải cụ thể và có thể kiểm tra

Không phê duyệt "miễn encryption cho hệ thống". Nêu rõ:
- Một database cụ thể, environment và data classification nào.
- Dữ liệu nào không được chứa trong phạm vi ngoại lệ.
- Những consumer/replica/backup nào chịu ảnh hưởng.
- Control thay thế nào áp dụng cho traffic và storage.
- Cách phát hiện nếu scope mở rộng ngoài phê duyệt.

Khi resource mới được tạo hoặc scope thay đổi, phải đánh giá lại applicability. Exception cho staging không tự áp dụng cho production.

## 7. Compensating controls — kiểm soát bù trừ

Kiểm soát bù trừ không phải một danh sách tùy chọn để hợp thức hóa mọi ngoại lệ. Nó cần giảm một phần rủi ro bằng bằng chứng thực tế, có owner và có thời hạn.

### 7.1. Tiêu chí của kiểm soát bù trừ

Một compensating control tốt:
- Giảm likelihood hoặc impact của risk scenario cụ thể.
- Phủ đúng phạm vi resource/flow/identity đang được miễn.
- Có hiệu lực đo được và được giám sát.
- Không tạo một lỗ hổng tương đương hoặc điểm lỗi chung mới.
- Có owner, runbook, evidence và kiểm thử.
- Tồn tại trong suốt thời hạn exception.
- Có phương án khi chính control bù trừ gặp lỗi.

### 7.2. Ví dụ mapping

| Kiểm soát chuẩn chưa đáp ứng | Risk cần giảm | Ví dụ compensating controls | Bằng chứng |
| --- | --- | --- | --- |
| Chưa có workload identity | Credential bị đánh cắp và dùng lại | Secret riêng, scope tối thiểu, rotation ngắn, private network, audit retrieval | Secret rotation report, IAM policy, access log |
| Chưa nâng được OS/database | Exploit lỗ hổng trên phiên bản cũ | Isolate network, disable module dễ bị khai thác, WAF/signature, enhanced monitoring | Asset scan, firewall rule, test path |
| Chưa bật centralized audit cho một legacy app | Không truy vết được hành động | DB audit, OS log forwarder, immutable log sink và kiểm soát admin | Log completeness test, access audit |
| Chưa chuyển object storage sang private endpoint | Truy cập public ngoài ý muốn | Block public access ở account, signed access ngắn hạn, restrict bucket policy | Configuration test, access-denied evidence |
| Chưa hỗ trợ encryption feature chuẩn | Lộ dữ liệu khi storage bị truy cập | Application-level encryption hoặc tokenization theo thiết kế phù hợp | Key handling review, restore/decrypt test |

Kiểm soát bù trừ không nhất thiết tương đương hoàn toàn với kiểm soát gốc. Phải mô tả residual risk còn lại và không dùng nó để tuyên bố đã tuân thủ nếu yêu cầu bắt buộc không cho phép thay thế.

### 7.3. Kiểm tra kiểm soát bù trừ khi phê duyệt

Đánh giá:
- **Design effectiveness:** kiểm soát có được thiết kế để xử lý đúng threat không?
- **Operating effectiveness:** kiểm soát có thực sự chạy và có bằng chứng trong kỳ không?
- **Coverage:** có bao phủ mọi resource/tenant/region nằm trong scope không?
- **Failure behavior:** nếu log collector/secret manager/WAF bị lỗi thì sao?
- **Independence:** người vận hành control có tách biệt hợp lý với người đề nghị exception không?

## 8. Ai được quyền chấp nhận rủi ro?

Chấp nhận rủi ro phải do chủ thể chịu trách nhiệm cho mục tiêu bị ảnh hưởng và có thẩm quyền tương ứng quyết định. Security/GRC thường tư vấn, đánh giá hoặc xác minh; họ không mặc nhiên thay business owner chịu mọi hậu quả kinh doanh.

### 8.1. Vai trò tham khảo

| Vai trò | Trách nhiệm |
| --- | --- |
| Requester / service owner | Mô tả exception, scope, lý do và remediation plan |
| Technical owner | Thiết kế/triển khai kiểm soát, sửa kỹ thuật và cung cấp evidence |
| Security architect | Đánh giá threat, architecture control và compensating controls |
| GRC/Compliance | Kiểm tra policy, nghĩa vụ, hồ sơ và quy trình phê duyệt |
| Risk owner | Chịu trách nhiệm quyết định accept/decline residual risk trong thẩm quyền |
| Data owner | Phê duyệt theo rủi ro và phân loại dữ liệu thuộc trách nhiệm |
| SRE/Operations | Đánh giá SLO, recovery, monitoring và vận hành control |
| Legal/Privacy | Tư vấn điều khoản, quyền riêng tư và nghĩa vụ pháp lý khi liên quan |
| Approver cấp cao | Quyết định risk vượt ngưỡng của đội/dịch vụ |

RACI chính xác phụ thuộc governance model của tổ chức. Người đề nghị không nên tự phê duyệt ngoại lệ do chính mình tạo ra khi có xung đột lợi ích.

### 8.2. Approval threshold

Có thể quy định:
- Risk thấp: service owner trong giới hạn được ủy quyền.
- Risk trung bình: service owner + Security/GRC review.
- Risk cao: business risk owner hoặc lãnh đạo được chỉ định, kèm Security/Compliance.
- Risk rất cao/critical hoặc vi phạm yêu cầu bắt buộc: không được chấp nhận theo quy trình thông thường; phải escalated, thay đổi thiết kế hoặc dừng hoạt động nếu cần.

Ngưỡng phải khớp risk appetite và nghĩa vụ thực tế. Không được dùng exception nội bộ để bỏ qua pháp luật, hợp đồng hoặc yêu cầu bắt buộc.

### 8.3. Risk acceptance không phải ký tên cho xong

Approver cần nhìn thấy:
- Risk scenario và residual risk.
- Phương án tránh/giảm rủi ro đã được xem xét.
- Bằng chứng controls và giới hạn của chúng.
- Consequence nếu rủi ro xảy ra.
- Deadline và nguồn lực remediation.
- Trigger/review/expiry.
- Ai chịu trách nhiệm nếu điều kiện thay đổi.

Quyết định nên có rationale ngắn, rõ, không dùng các cụm "business accepted" mà không nêu người/role có thẩm quyền và phạm vi.

## 9. Thời hạn, gia hạn và thu hồi ngoại lệ

### 9.1. Exception expiry khác remediation target

Expiry là ngày phê duyệt tạm thời chấm dứt hiệu lực. Remediation target là hạn hoàn thành công việc kỹ thuật. Một ngoại lệ có thể hết hạn trước ngày dự kiến hoàn thành nếu risk appetite yêu cầu; khi đó phải có phương án chuyển đổi, dừng hoạt động hoặc phê duyệt mới trước expiry.

Không để một exception có expiry trùng với ngày dự án dự kiến xong mà không có buffer cho validation và rollback.

### 9.2. Gia hạn không tự động

Yêu cầu gia hạn phải:
- Được gửi trước expiry đủ sớm.
- Cập nhật risk assessment, evidence và lý do chậm.
- Chứng minh compensating controls vẫn hiệu quả.
- Đưa ra milestone cụ thể, owner và nguồn lực.
- Nêu thay đổi bối cảnh/threat/asset exposure.
- Được đúng risk owner và cấp tương đương hoặc cao hơn phê duyệt theo policy.

Gia hạn lặp đi lặp lại là tín hiệu của remediation plan không khả thi, thiếu owner hoặc tổ chức đang chấp nhận một rủi ro dài hạn dưới nhãn ngoại lệ tạm thời. Cần xem lại thiết kế hoặc chuyển thành quyết định risk treatment dài hạn có governance phù hợp.

### 9.3. Trigger thu hồi ngay

Một exception nên được xem xét lại hoặc thu hồi khi:
- Có exploit mới, incident hoặc dấu hiệu compromise liên quan.
- Asset được chuyển sang public exposure hoặc phạm vi dữ liệu tăng.
- Compensating control bị tắt, lỗi hoặc không có evidence.
- Tenant/customer/regulation mới làm thay đổi nghĩa vụ.
- Threat likelihood/impact tăng vượt ngưỡng phê duyệt.
- Owner rời tổ chức hoặc không còn chịu trách nhiệm.
- Scope/version/config thực tế khác scope được phê duyệt.
- Expiry đến hạn mà không có quyết định mới.

Khi thu hồi, phải có hành động rõ: đóng endpoint, cô lập resource, rotate credential, disable feature, patch khẩn hoặc dừng xử lý dữ liệu. Không chỉ chuyển trạng thái trên GRC tool.

## 10. Remediation plan có thể thực thi

Một plan tốt gắn finding với thay đổi kỹ thuật, người chịu trách nhiệm, mốc và cách chứng minh hoàn thành.

### 10.1. Nội dung remediation

| Trường | Câu hỏi |
| --- | --- |
| Root cause | Nguyên nhân gốc là gì: thiếu guardrail, thiết kế sai, dependency hay quy trình? |
| Action | Thay đổi cụ thể nào cần thực hiện? |
| Owner | Ai trực tiếp làm, ai chịu trách nhiệm cuối cùng? |
| Dependency | Cần team, vendor, maintenance window hay migration nào? |
| Milestone | Containment, design, implementation, test, rollout, validation? |
| Deadline | Hạn từng mốc và hạn cuối? |
| Test | Cách chứng minh control hoạt động và không làm hỏng nghiệp vụ? |
| Rollback | Có cách trở lại trạng thái an toàn nếu deploy lỗi? |
| Evidence | Scan, config, log, test report, approval, architecture update? |
| Residual risk | Rủi ro còn lại sau remediation là gì? |

### 10.2. Phân rã công việc

Thay vì ticket duy nhất "fix security", tách:
1. Containment và giảm exposure.
2. Root-cause analysis.
3. Thiết kế giải pháp đích.
4. Migration/implementation.
5. Security/functional/performance test.
6. Rollout có kiểm soát.
7. Validation độc lập.
8. Thu hồi exception và cập nhật kiến trúc/tài liệu.

### 10.3. Ví dụ kế hoạch database legacy

- Ngày 0: ghi nhận database hết hỗ trợ, xác định public/private, data classification và access.
- Trong 24 giờ: chặn public ingress, kiểm tra IAM và backup; áp monitoring tăng cường.
- Trong 5 ngày: hoàn tất compatibility test với phiên bản hỗ trợ.
- Trong 20 ngày: triển khai staging, load test, restore và failover test.
- Trong 30 ngày: rollout production theo wave, xác minh replication và query behavior.
- Sau rollout: scan lại, kiểm chứng patch level, xóa credential cũ, đóng exception.

Mốc này chỉ là ví dụ lập kế hoạch. Hệ thống quan trọng hơn có thể cần containment nhanh hơn; migration phức tạp hơn cần milestones khác và phê duyệt residual risk.

## 11. Ghi nhận và quản lý bằng risk register/exception register

Không nên chỉ dùng email hoặc chat để giữ các quyết định. Cần một hồ sơ có cấu trúc, có tìm kiếm, quyền truy cập và lịch sử thay đổi.

### 11.1. Các trường tối thiểu

| Nhóm | Trường |
| --- | --- |
| Identity | Exception ID, title, status, created date |
| Scope | Service, resource, account, environment, region, tenant, version |
| Policy | Control ID, policy/version, requirement, finding reference |
| Risk | Scenario, likelihood, impact, inherent/residual risk |
| Ownership | Requester, technical owner, service owner, risk owner, approver |
| Treatment | Accept/mitigate/avoid/transfer, compensating controls |
| Schedule | Start date, containment deadline, remediation due, expiry, review date |
| Evidence | Scan, ticket, architecture diagram, test result, log, approval record |
| Monitoring | Control health, alert, last review, trigger |
| Closure | Validation owner, completion evidence, closed date, exception revoked |

### 11.2. Ví dụ bản ghi JSON

~~~json
{
  "exception_id": "EXC-2026-0142",
  "title": "Legacy worker chưa hỗ trợ workload identity",
  "status": "active",
  "scope": {
    "service": "booking-worker",
    "environment": "production",
    "region": "region-a",
    "version": "2.4.x"
  },
  "control": {
    "id": "IAM-WORKLOAD-03",
    "requirement": "Mỗi workload dùng identity riêng"
  },
  "risk": {
    "scenario": "Credential dài hạn bị lộ và dùng để truy cập dữ liệu booking",
    "inherent": "high",
    "residual": "medium"
  },
  "owner": {
    "technical": "team-booking",
    "risk": "business-service-owner"
  },
  "controls": [
    "secret riêng cho workload",
    "rotation mỗi 7 ngày",
    "private egress allowlist",
    "audit secret retrieval"
  ],
  "schedule": {
    "approved_at": "2026-11-18",
    "remediation_due": "2026-12-15",
    "expires_at": "2026-12-20",
    "review_at": "2026-11-25"
  }
}
~~~

Dữ liệu hoàn toàn giả định. Tên người, email, hệ thống GRC và ngày thực tế cần lấy từ hồ sơ chính thức. Không đưa credential, token hoặc dữ liệu khách hàng vào register.

### 11.3. Audit trail

Mỗi thay đổi cần ghi actor, timestamp, field changed, old/new value (nếu được phép), rationale và approval reference. Cần bảo vệ audit log khỏi người có quyền sửa exception record. Việc thay approver, expiry, risk score hoặc scope là thay đổi quan trọng phải được lưu dấu.

## 12. Governance cho cloud architecture

Quản lý ngoại lệ không thể tách khỏi architecture governance, landing zone, policy-as-code và shared responsibility.

### 12.1. Các lớp policy

- **Organization guardrails:** region, account, public exposure, encryption, logging và identity.
- **Platform baseline:** network, container, database, backup, key management, monitoring.
- **Workload requirements:** SLO, data classification, threat model, access và recovery.
- **Project exception:** sai lệch có scope, owner, expiry và risk acceptance cụ thể.

Guardrail có thể là preventative (chặn), detective (phát hiện) hoặc corrective (tự sửa/đưa về trạng thái chuẩn). Không phải mọi policy đều nên dùng chế độ chặn ngay; cần thử nghiệm, đo false positives và có safe rollout.

### 12.2. Policy-as-code

Policy-as-code giúp kiểm tra cấu hình trong CI/CD hoặc khi tạo resource. Ví dụ kiểm tra một resource storage không được public hoặc workload production phải dùng image từ registry được chấp thuận.

~~~text
POLICY: prod-storage-private

WHEN resource.environment == "production"
AND resource.type == "object-storage"

REQUIRE:
  public_access == false
  encryption_at_rest == true
  audit_access == true

ON_VIOLATION:
  block_deployment
  emit_finding
  attach_policy_id
~~~

Đây là pseudo-policy, không phải cú pháp của một engine cụ thể. Cần quyết định finding nào chặn deployment, finding nào chỉ cảnh báo, cách quản lý exception có scope và ai được phép cập nhật policy.

### 12.3. Exception không được vô hiệu hóa guardrail rộng

Nếu một service cần ngoại lệ, giới hạn đúng resource, environment, version và thời gian. Không tạo global allowlist hoặc tắt toàn bộ policy để xử lý một trường hợp. Dùng tag/metadata đáng tin cậy để liên kết resource với hồ sơ exception; kiểm tra tag không thể do workload tự ghi tùy ý để tự cấp quyền.

## 13. Liên kết với Well-Architected và risk appetite

Một quyết định chấp nhận rủi ro có thể ảnh hưởng nhiều trụ cột cùng lúc.

| Trụ cột | Câu hỏi khi xử lý exception |
| --- | --- |
| Operational Excellence | Có owner, runbook, evidence, review và quy trình đóng/mở lại không? |
| Security | Có threat scenario, least privilege, controls bù trừ và audit không? |
| Reliability | Ngoại lệ có làm giảm redundancy, backup, recovery hoặc SLO không? |
| Performance Efficiency | Kiểm soát mới có gây latency/throughput impact không? |
| Cost Optimization | Chi phí xử lý, kiểm soát bù trừ và trì hoãn remediation ra sao? |
| Sustainability | Tài nguyên legacy hoặc logging/replication dư thừa có được quản lý không? |

Risk appetite là mức và loại rủi ro tổ chức sẵn sàng giữ để đạt mục tiêu. Nó cần được định nghĩa theo loại hậu quả, mức độ và phạm vi, có thể khác nhau giữa dữ liệu công khai và dữ liệu cá nhân, giữa analytics và payment, giữa development và production.

Không thể dùng một điểm risk appetite chung để chấp nhận mọi vấn đề. Một rủi ro bảo mật có thể được cân nhắc về mặt kinh doanh nhưng nghĩa vụ pháp lý hoặc hợp đồng vẫn không cho phép miễn.

## 14. Đo lường hiệu quả governance

Đo số exception đang mở là chưa đủ. Cần biết tuổi, mức độ, scope, nguyên nhân, chất lượng kiểm soát và xu hướng.

| Metric | Cách tính/thể hiện | Câu hỏi quản trị |
| --- | --- | --- |
| Open exceptions | Số hồ sơ Active/Approved | Có bao nhiêu sai lệch còn tồn tại? |
| Overdue remediation | Số action quá hạn / tổng action | Kế hoạch có thực thi đúng hạn? |
| Exception age | Ngày hiện tại trừ ngày mở | Ngoại lệ nào đang trở thành trạng thái lâu dài? |
| Expired active exceptions | Exception còn active sau expiry | Có vi phạm quy trình phê duyệt? |
| Repeat findings | Finding tái diễn theo control/service | Nguyên nhân gốc đã được xử lý? |
| High residual risk | Số risk high/critical đang được accept | Có phù hợp appetite và thẩm quyền? |
| Compensating control health | Tỷ lệ control có evidence/monitoring hợp lệ | Kiểm soát bù trừ có thực sự chạy? |
| Remediation lead time | Thời gian từ finding đến validation/closure | Năng lực xử lý có được cải thiện? |
| Extension rate | Tỷ lệ hồ sơ cần gia hạn | Deadline/plan có thực tế? |
| Policy violation trend | Finding theo baseline/control qua thời gian | Guardrail có giảm tái diễn? |

Không khuyến khích tối ưu bằng cách đóng finding sớm, hạ severity hoặc tạo nhiều exception nhỏ để làm đẹp dashboard. Metric phải có định nghĩa, nguồn dữ liệu, owner và phân nhóm theo severity, service, environment và data classification.

### 14.1. Dashboard quản trị

Một dashboard có ích nên cho phép drill-down:
- Risk critical/high đang mở và người có thẩm quyền.
- Exception sắp hết hạn/quá hạn.
- Finding liên quan public exposure, data classification hoặc exploit đang hoạt động.
- Các compensating control không có heartbeat/evidence.
- Remediation milestone bị chặn bởi dependency/vendor.
- Tỷ lệ finding tái diễn và các nguyên nhân gốc nổi bật.
- Distribution theo team, platform, cloud account và region.

## 15. Tình huống thực tế: ngoại lệ workload identity cho hệ thống kế thừa

### 15.1. Bối cảnh

Một worker xử lý booking chạy production trên cloud. Ứng dụng cũ chỉ hỗ trợ database username/password được lưu trong secret manager; chưa hỗ trợ workload identity. Team đang migration sang cơ chế identity mới nhưng cần 6 tuần vì thư viện database và lịch phát hành.

Tài sản có dữ liệu booking và thông tin khách hàng; worker chỉ cần đọc/ghi một số bảng. Credential hiện dùng chung cho nhiều instance và có thời hạn dài. Đây là một finding mức cao theo baseline IAM nội bộ.

### 15.2. Đánh giá rủi ro

**Risk scenario:** nếu một container hoặc pipeline bị compromise, credential dùng chung có thể bị lấy và dùng để truy cập database từ phạm vi rộng hơn chức năng worker cần.

Các yếu tố:
- Exposure: workload private, nhưng pipeline/secret access là đường đáng quan tâm.
- Impact: dữ liệu booking/khách hàng và toàn vẹn trạng thái đơn.
- Current controls: secret manager, TLS database connection, private subnet.
- Gaps: credential dùng chung, thời hạn dài, quyền DB rộng và khả năng attribution hạn chế.
- Inherent risk: high theo ma trận nội bộ giả định.
- Residual risk sau controls dự kiến: giảm nhưng vẫn cần được risk owner đánh giá.

### 15.3. Compensating controls đề xuất

- Credential riêng theo service/environment; loại bỏ credential dùng chung.
- Scope DB chỉ tới schema/table và operation cần thiết.
- Rotation theo lịch ngắn hơn, có overlap và kiểm tra khả năng rollback.
- Secret access theo identity workload hiện có; audit retrieval và alert bất thường.
- Private network/egress restriction; chỉ cho phép kết nối đến DB endpoint.
- Tách pipeline deploy khỏi quyền đọc secret production.
- Quét image, pin digest và hạn chế shell/exec production.
- Theo dõi query/audit log và phát hiện truy cập ngoài pattern.

Các biện pháp này giảm một phần nguy cơ nhưng không thay workload identity; phải kiểm chứng coverage và failure behavior.

### 15.4. Lộ trình và approval

| Mốc | Hành động | Owner |
| --- | --- | --- |
| Ngày 0–2 | Thay credential dùng chung bằng credential riêng, thu hẹp DB grants | Database + application owner |
| Ngày 0–3 | Bật alert và audit secret access, egress restrictions | Platform/Security |
| Ngày 7 | Kiểm thử rotation, restart, failover và rollback | SRE + application team |
| Ngày 14 | Hoàn thành prototype workload identity | Application team |
| Ngày 28 | Staging migration, security test, load test | Platform + Security |
| Ngày 35 | Rollout theo wave, theo dõi production | Service owner |
| Ngày 42 | Xác minh credential cũ bị thu hồi, đóng exception | Independent validator |

Risk owner có thể cân nhắc exception trong thời gian migration theo authority matrix; hồ sơ phải nêu expiry không vượt giới hạn policy, điều kiện thu hồi và người phê duyệt cụ thể. Nếu controls không đạt hoặc có dấu hiệu compromise, cần containment/revoke ngay thay vì chờ lịch migration.

## 16. Tình huống thực tế thứ hai: database hết hỗ trợ

Một database production đang chạy phiên bản hết hỗ trợ. Ứng dụng cần thay driver và kiểm thử tương thích; không thể nâng cấp ngay trong maintenance window sắp tới.

### Quyết định cần phân tích

- Đây có phải yêu cầu pháp lý/hợp đồng cấm sử dụng phiên bản hết hỗ trợ không?
- Database public hay private? Có dữ liệu confidential/restricted?
- Có exploit đang được khai thác không? Vendor còn cung cấp extended support?
- Có thể isolate network, thu hẹp role, chặn extension nguy hiểm, tăng monitoring và hạn chế export không?
- Backup/PITR có được restore test trên phiên bản mục tiêu?
- Migration có kế hoạch rollback và data compatibility?
- Deadline có owner, milestone và resource được cấp không?

### Kết quả governance mong đợi

1. Risk scenario và phạm vi DB được ghi rõ.
2. Critical exposure được containment ngay.
3. Migration plan có milestone, test và deadline.
4. Interim controls có owner và evidence.
5. Risk owner đúng cấp chấp nhận residual risk trong giới hạn policy nếu cho phép.
6. Expiry và review trước hạn được ghi trên register.
7. Sau migration, independent validation xác nhận patch/support status, security configuration, data consistency và backup restore trước khi đóng.

Nếu quy định bắt buộc yêu cầu dừng phiên bản đó, exception nội bộ không thể thay thế nghĩa vụ này. Cần escalated để đổi kế hoạch hoặc dừng xử lý bị ảnh hưởng.

## 17. Architecture Decision Record mẫu

~~~markdown
# ADR-083: Quản lý ngoại lệ cho workload chưa hỗ trợ workload identity

Trạng thái: Chấp thuận có điều kiện
Owner: Booking service owner
Risk owner: Business owner được ủy quyền
Security/GRC reviewer: Theo authority matrix
Ngày: YYYY-MM-DD

Bối cảnh:
- Worker legacy dùng database credential dài hạn.
- Migration sang workload identity cần 6 tuần.
- Baseline yêu cầu mỗi workload có identity riêng.

Risk scenario:
- Credential bị lấy từ workload/pipeline và dùng để đọc/ghi
  dữ liệu booking ngoài phạm vi cần thiết.

Phạm vi:
- Service: booking-worker
- Environment: production
- Version: 2.4.x
- Expiry: YYYY-MM-DD

Phương án:
A. Dừng worker cho tới khi migration xong.
B. Giữ hoạt động với compensating controls có thời hạn.
C. Thiết kế lại worker hoặc thay runtime ngay.

Quyết định:
- Chọn B chỉ khi controls được triển khai và kiểm chứng.
- Credential riêng, DB grants tối thiểu, rotation, egress restriction,
  secret access audit và image provenance.
- Migration workload identity có milestones rõ.

Điều kiện:
- Owner và validator được chỉ định.
- Review định kỳ và theo trigger compromise/exposure/control failure.
- Không tự gia hạn khi expiry đến.
- Revoke credential cũ sau migration.

Bằng chứng đóng:
- Workload identity hoạt động production.
- Negative access tests, rotation/restart tests và audit.
- Credential cũ đã thu hồi; exception đã hết hiệu lực.

Rủi ro còn lại:
- Credential tạm thời vẫn có thể bị lạm dụng trong thời hạn.
~~~

ADR là quyết định kiến trúc; exception record trong hệ thống GRC có thể chứa approval, expiry và evidence chi tiết. Cần liên kết hai hồ sơ bằng ID để tránh lệch dữ liệu.

## 18. Sai lầm thường gặp

| Sai lầm | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Exception không có expiry | Sai lệch tạm thời trở thành vĩnh viễn | Bắt buộc expiry và review date |
| Requester tự chấp nhận rủi ro của mình | Xung đột lợi ích, thiếu accountability | Risk owner độc lập theo authority matrix |
| Dùng severity scanner làm risk score duy nhất | Ưu tiên sai theo exposure/business impact | Threat scenario, asset context và exploitability |
| Chỉ ghi "legacy system" làm lý do | Không có evidence hay kế hoạch chuyển đổi | Ghi dependency, alternative, milestone và owner |
| Compensating control chỉ nằm trên giấy | Rủi ro không được giảm thực tế | Test design/operating effectiveness và monitor |
| Chấp nhận rủi ro thay cho remediation | Nợ bảo mật tích lũy và tái diễn | Treatment plan, deadline và trigger xem lại |
| Gia hạn tự động | Không đánh giá bối cảnh và risk mới | Reassessment, evidence và re-approval |
| Đóng ticket khi deploy xong | Chưa chứng minh cấu hình/hiệu quả | Independent validation và closure evidence |
| Ngoại lệ phạm vi quá rộng | Có thể che giấu resource mới hoặc tenant mới | Scope cụ thể, inventory và policy linkage |
| Không phân biệt containment/remediation | Exposure cao kéo dài trong khi chờ migration | Deadline riêng cho từng mốc |
| Ngoại lệ bỏ qua nghĩa vụ bắt buộc | Vi phạm luật/hợp đồng | Legal/Compliance review; không dùng waiver nội bộ |
| Register không có audit trail | Không truy được ai thay đổi quyết định | Immutable history, actor, timestamp và rationale |
| Dashboard chỉ đếm số exception | Không thấy tuổi, residual risk và expiry | Đo overdue, age, repeat, control health |
| Không kiểm soát ngoại lệ của ngoại lệ | Guardrail bị vô hiệu hóa trên diện rộng | Policy-as-code, scope hẹp, review và expiry |

## 19. Bài tập thực hành

Một nền tảng cloud có ba phát hiện:

- **Finding A:** API quản trị production có một endpoint legacy chưa hỗ trợ MFA; endpoint chỉ truy cập được qua network quản trị nhưng vẫn dùng password.
- **Finding B:** Database production chứa dữ liệu khách hàng chạy phiên bản sắp hết hỗ trợ; migration cần 45 ngày và có thay đổi driver.
- **Finding C:** Một bucket log không bật object lock theo baseline; log chứa audit event và hiện được lưu trong cùng account với ứng dụng.

Hãy thực hiện:

1. Viết risk scenario cho từng finding, nêu asset, threat event, impact, scope và uncertainty.
2. Phân biệt finding, nonconformity, risk, exception, compensating control và risk acceptance.
3. Đánh giá inherent/residual risk; giải thích tại sao severity kỹ thuật không đủ để xếp ưu tiên.
4. Đề xuất treatment cho từng finding: avoid, mitigate, transfer/share hoặc accept; nêu phương án đã loại bỏ và lý do.
5. Chọn containment, remediation và validation deadline; giải thích cơ sở và escalation.
6. Thiết kế compensating controls cho từng trường hợp, gồm owner, metric, evidence và behavior khi control lỗi.
7. Xác định risk owner/approver theo authority matrix; chỉ ra trường hợp phải có Legal/Compliance review.
8. Tạo exception register có scope, start, expiry, review, risk score, approvals và evidence link.
9. Viết remediation plan và trigger thu hồi/gia hạn; giải thích vì sao gia hạn không tự động.
10. Viết ADR cho một quyết định kiến trúc và mô tả phép kiểm tra độc lập trước khi đóng.

**Tiêu chí tự đánh giá:** lời giải tốt tạo được quyết định có thể kiểm toán, deadline có căn cứ, owner đúng thẩm quyền, kiểm soát bù trừ được chứng minh và không dùng ngoại lệ để bỏ qua nghĩa vụ bắt buộc.

## 20. Checklist trước khi phê duyệt hoặc đóng exception

- [ ] Finding liên kết đúng policy/control, asset, service, environment và version.
- [ ] Threat scenario mô tả nguyên nhân, sự kiện, hậu quả và phạm vi.
- [ ] Inherent risk, current controls và residual risk được đánh giá có bằng chứng.
- [ ] Đã xem xét avoid/mitigate/transfer/accept và các phương án thay thế.
- [ ] Phân biệt rõ containment, remediation và validation deadline.
- [ ] SLA phản ánh exploitability, exposure, asset criticality và nghĩa vụ bên ngoài.
- [ ] Compensating controls có design/operating evidence, owner và monitoring.
- [ ] Requester, technical owner, risk owner, approver và validator được chỉ định.
- [ ] Thẩm quyền phê duyệt phù hợp mức risk; Legal/Privacy/Compliance tham gia khi cần.
- [ ] Scope được giới hạn theo resource, account, region, tenant, environment và version.
- [ ] Có start date, expiry, review date, remediation milestones và alert/escalation.
- [ ] Gia hạn phải reassess và re-approve; không tự động kéo dài.
- [ ] Trigger compromise, exposure, control failure hoặc thay đổi nghĩa vụ được xác định.
- [ ] Exception record và audit trail giữ actor, timestamp, rationale, approval và evidence.
- [ ] Policy-as-code/guardrail không bị vô hiệu hóa quá phạm vi.
- [ ] Validation độc lập xác nhận remediation và kiểm soát còn hiệu lực.
- [ ] Exception được thu hồi, credential/temporary access được dọn và kiến trúc được cập nhật.
- [ ] Metrics theo dõi age, overdue, expiry, repeat finding, residual risk và control health.

## Ghi nhớ

Quản lý ngoại lệ là cách xử lý minh bạch những sai lệch có lý do và có giới hạn. Remediation SLA đặt kỳ vọng về thời gian containment, sửa chữa và kiểm chứng. Risk acceptance chỉ hợp lệ khi người có thẩm quyền hiểu residual risk, chấp thuận phạm vi cụ thể, có rationale, điều kiện, thời hạn và cơ chế xem xét lại.

Một governance process hiệu quả kết nối **finding → risk scenario → treatment → approval → compensating controls → remediation → independent validation → closure**. Không có ngoại lệ nào tự làm mất rủi ro hoặc thay thế nghĩa vụ bắt buộc. Mọi quyết định phải có owner, bằng chứng và khả năng thu hồi khi bối cảnh thay đổi.
