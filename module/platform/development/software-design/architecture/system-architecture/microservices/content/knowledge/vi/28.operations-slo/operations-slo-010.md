# Đo thời gian phát hiện, khôi phục và hiệu quả vận hành

**Nhóm kiến thức:** Vận hành và SLO trong System Architecture, Software Design và Microservices.

Một hệ thống có thể đạt thông lượng cao nhưng vẫn gây gián đoạn nghiêm trọng nếu đội ngũ phát hiện sự cố quá muộn, cảnh báo đến sai người, thiếu cách cô lập lỗi hoặc không biết khi nào giao dịch của người dùng thật sự phục hồi. Ngược lại, một hệ thống có các sự cố nhỏ được phát hiện và xử lý nhanh có thể có trải nghiệm tốt hơn, miễn là đo lường đúng mức ảnh hưởng và ngăn lỗi tái diễn.

Để cải thiện khả năng vận hành, các đội thường đo **MTTD** (Mean Time To Detect), **MTTA** (Mean Time To Acknowledge), thời gian **mitigation**, **MTTR** (Mean Time To Recover/Restore/Resolve theo quy ước), tỷ lệ phát hiện tự động, chất lượng alert, thời lượng người dùng chịu ảnh hưởng và nỗ lực trực vận hành. Những con số này chỉ có ý nghĩa khi tất cả mọi người thống nhất **mốc bắt đầu, mốc kết thúc, nguồn chứng cứ, đơn vị, mẫu số và cách xử lý dữ liệu thiếu**.

Bài học này thiết kế một quy trình đo lường sự cố có thể áp dụng cho microservices: dựng timeline, chọn SLI/SLO, đánh giá cảnh báo, đo khôi phục và tác động nghiệp vụ, viết dashboard, tính toán bằng SQL và Java, cải thiện runbook, diễn tập sự cố, phân tích postmortem và tránh những KPI tạo động cơ sai.

## 1. Đo điều gì để đưa ra quyết định tốt hơn?

Bắt đầu bằng những câu hỏi vận hành thật:

1. **Người dùng bắt đầu chịu ảnh hưởng khi nào?** Có thể là lần đầu giao dịch thất bại, tỷ lệ request tốt giảm hoặc một hàng đợi bắt đầu trễ deadline.
2. **Hệ thống phát hiện khi nào?** Alert tự động, synthetic probe, log, đối soát dữ liệu hay khách hàng báo?
3. **Ai nhận trách nhiệm và khi nào?** Alert được tạo, gửi thành công, ACK và bắt đầu điều tra là các mốc khác nhau.
4. **Khi nào tác động giảm?** Tắt feature flag, chuyển traffic, rollback, giảm concurrency hay xử lý dependency lỗi?
5. **Khi nào hành vi người dùng phục hồi?** Pod Running không bảo đảm checkout thành công hoặc dữ liệu đã đúng.
6. **Khi nào nguyên nhân gốc được sửa?** Có thể vài ngày sau khi hệ thống đã được khôi phục bằng workaround an toàn.
7. **Tác động rộng đến đâu?** Bao nhiêu request, tenant, user journey, business transaction và bản ghi dữ liệu bị ảnh hưởng?
8. **Cải tiến nào có thể rút ngắn lần sự cố sau?** Số liệu phải dẫn đến thay đổi đo được.

Mục tiêu không phải có dashboard “toàn màu xanh”, mà là giảm **mức độ và thời lượng tác động tới người dùng**, đồng thời làm phản ứng của đội ngũ đáng tin cậy và có thể lặp lại.

## 2. Phân biệt event, alert, incident và user impact

| Khái niệm | Định nghĩa | Ví dụ |
|---|---|---|
| **Event** | Một trạng thái hoặc thay đổi quan sát được | Pod restart, request 500 |
| **Signal** | Metric, log, trace hoặc probe phản ánh hoạt động | Checkout success rate giảm |
| **Alert** | Chính sách phát thông báo khi một điều kiện được thỏa | Error-budget burn vượt ngưỡng |
| **Incident** | Tình huống cần phối hợp ứng phó theo mức tác động/rủi ro | Thanh toán liên tục thất bại |
| **User impact** | Trải nghiệm hoặc dữ liệu người dùng bị suy giảm | Giao dịch không hoàn thành |
| **Mitigation** | Hành động giảm đáng kể tác động trước khi sửa tận gốc | Rollback canary, tắt feature flag |
| **Restoration** | Dịch vụ trở lại trạng thái phục vụ theo hợp đồng | Good checkout ratio đạt lại mức cho phép |
| **Resolution** | Vấn đề được xử lý/đóng theo quy trình | Bug được sửa và follow-up hoàn thành |
| **Root cause** | Cơ chế hoặc tập điều kiện gây sự cố | Retry storm làm cạn DB pool |

Không phải alert nào cũng là incident. Một spike CPU có thể bình thường; một lỗi business logic âm thầm có thể không có alert nào. Nếu chỉ tính incident được hệ thống alert mở, đội vận hành có thể vô tình **bỏ sót những sự cố không phát hiện tự động** và tạo ra MTTD thấp giả.

Khi ghi sự cố, nên lưu dịch vụ, severity, phạm vi, người phụ trách, nguồn phát hiện, loại lỗi, các mốc và bằng chứng. Không coi việc ticket được đóng là bằng chứng người dùng đã phục hồi.

## 3. Timeline chuẩn cho một sự cố

~~~mermaid
flowchart LR
    A["T0: bắt đầu tác động"] --> B["T1: phát hiện"]
    B --> C["T2: nhận trách nhiệm / ACK"]
    C --> D["T3: giảm tác động"]
    D --> E["T4: khôi phục mức phục vụ"]
    E --> F["T5: xử lý nguyên nhân và đóng"]
~~~

Một bộ thời lượng có thể định nghĩa như sau:

~~~text
Time to detect       = T1 - T0
Time to acknowledge  = T2 - thời điểm alert được chọn
Time to mitigate     = T3 - T0
Time to restore      = T4 - T0
Post-restoration     = T5 - T4
~~~

Có tổ chức định nghĩa time-to-mitigate từ lúc detect thay vì impact start; có tổ chức định nghĩa MTTR từ lúc incident declared. Những cách đo đó đều có thể hữu ích khi ghi rõ, nhưng **không trộn số đo khác định nghĩa trong cùng báo cáo**.

Các mốc bổ sung giúp tìm nút thắt:
- firstSignalAt, alertFiredAt, notificationDeliveredAt.
- acknowledgedAt, investigationStartedAt.
- mitigationStartedAt, mitigationEffectiveAt.
- restoredAt, recoveryConfirmedAt.
- backlogClearedAt, dataReconciledAt.
- closedAt, permanentFixDeployedAt.

Một incident không có alert sẽ không có mốc MTTA. Giá trị thiếu phải là **NULL/unknown/not applicable**, không tự điền 0 để làm trung bình đẹp hơn.

## 4. MTTD: thời gian phát hiện

**MTTD – Mean Time To Detect** thường là trung bình thời gian từ khi tác động bắt đầu đến khi tín hiệu đáng tin đầu tiên được nhận biết theo quy ước:

\[
MTTD = \frac{\sum_{i=1}^{N}(t_{\mathrm{detected},i}-t_{\mathrm{impactStart},i})}{N}
\]

N là số sự cố trong phạm vi có đủ mốc và hợp lệ. Cần công bố cả tổng số incident lẫn số có dữ liệu để tránh thiên lệch.

Ví dụ: một bug deploy lúc 09:00, lỗi checkout bắt đầu lúc 09:04, alert phát lúc 09:06 và người trực mở dashboard lúc 09:08. Nếu detect là first reliable alert, time to detect = 2 phút. Nếu detect chỉ tính khi con người nhận ra, time to detect = 4 phút. Không nên nói cả hai đều là MTTD mà không ghi định nghĩa.

### 4.1. T0 có thể không chính xác tuyệt đối

Với HTTP 5xx, có thể lấy request đầu tiên xấu hoặc điểm SLI lệch rõ. Với lỗi dữ liệu âm thầm, hệ thống có thể chỉ biết lỗi phát sinh trong khoảng 09:00–10:00 vì job đối soát chạy mỗi giờ.

Các nguồn ước lượng T0:
- Metric good/bad events trong bucket thời gian.
- Synthetic probe đầu tiên lỗi và lần cuối cùng còn tốt.
- Log request, trace và sự kiện nghiệp vụ.
- Dữ liệu reconciliation với record sớm nhất sai.
- Thời điểm phát hành config/code được xác minh có liên quan.
- Dữ liệu từ hệ thống đối tác hoặc báo cáo khách hàng.

Nếu thời điểm bắt đầu chỉ có thể nằm trong một khoảng, hãy lưu **độ bất định và cách ước lượng**, không bịa mốc chính xác đến từng giây. Đối với lỗi được phát hiện trước khi ảnh hưởng người dùng bằng canary, nên theo dõi **near miss/prevented incident** riêng; không tính thời lượng âm để kéo MTTD xuống.

### 4.2. T1 khác với lúc alert hiển thị

Alert có thể được chờ thêm nhiều phút để xác nhận điều kiện, bị routing sai, bị suppression hoặc không đến được thiết bị on-call. Nên lưu riêng:
- Tín hiệu đầu tiên thể hiện lỗi.
- Alert rule fired.
- Pager nhận/đưa thông báo.
- Người trực ACK.
- Người trực bắt đầu điều tra.

Chúng giúp phân biệt **vấn đề quan sát** với **vấn đề chuyển thông báo** hoặc **vấn đề phối hợp**.

## 5. MTTA: nhận trách nhiệm sự cố

**MTTA – Mean Time To Acknowledge** thường đo từ lúc alert phát/gửi đến khi người trực ACK:

\[
MTTA = \frac{\sum_i(t_{\mathrm{ack},i}-t_{\mathrm{alert},i})}{N_{\mathrm{ack}}}
\]

Nếu alert fired 10:00, notification delivered 10:01, ACK 10:04 thì time-to-ACK là 4 phút tính từ fired hoặc 3 phút tính từ delivered. Chính sách đo phải chọn một mốc rõ ràng.

**ACK không phải là khắc phục.** Một người có thể bấm ACK trong 10 giây nhưng chờ thêm 30 phút mới có dữ liệu điều tra hoặc quyền rollback. Vì thế nên theo dõi thêm:
- Thời gian từ ACK đến bắt đầu triage.
- Tỷ lệ page sai người.
- Số lần escalation và handoff.
- Tỷ lệ alert không được ACK.
- Thời gian đến quyết định mitigation đầu tiên.

Nếu chỉ ép người trực ACK càng nhanh càng tốt, MTTA có thể giảm mà tác động người dùng không thay đổi.

## 6. Thời gian mitigation: giảm tác động trước khi sửa tận gốc

Mitigation có thể là:
- Dừng rollout hoặc rollback image/config.
- Tắt tính năng có thể tắt an toàn.
- Chuyển traffic khỏi region hỏng.
- Giảm concurrency để bảo vệ dependency.
- Cô lập tenant hoặc tác vụ gây tải bất thường.
- Tắt chức năng tùy chọn trong khi giữ chức năng cốt lõi.
- Tạm chuyển sang chế độ chỉ đọc nếu hợp đồng cho phép.

Ví dụ một sự cố:
- 10:00 checkout lỗi 80%.
- 10:05 phát hiện.
- 10:10 tắt nhánh tính năng lỗi, tỷ lệ lỗi giảm còn 20%.
- 10:20 phục hồi đường thanh toán, lỗi trở lại baseline.

Mốc 10:10 là **first meaningful mitigation**, nhưng chưa phải restored. Nếu chọn time to mitigate từ impactStart, kết quả là 10 phút; time to restore là 20 phút.

Hãy định nghĩa mitigation là **khi tác động thực sự giảm** theo metric/đánh giá đã định, không chỉ khi lệnh rollback bắt đầu chạy. Có thể lưu nhiều mitigation event với phạm vi giảm tác động ở từng giai đoạn.

## 7. MTTR: chữ R có thể có nhiều nghĩa

| Tên đầy đủ | Kết thúc tại | Mục đích |
|---|---|---|
| Mean Time To **Respond** | Bắt đầu phản ứng | Hiệu quả paging/triage |
| Mean Time To **Repair** | Thành phần được sửa | Thời gian sửa tài nguyên |
| Mean Time To **Restore/Recover** | Dịch vụ phục vụ lại theo hợp đồng | Phục hồi đối với người dùng |
| Mean Time To **Resolve** | Ticket/incident được đóng | Quy trình xử lý toàn bộ |

Trong bài này, **MTTRestore** là trung bình khoảng từ impact start đến restored, nhằm tránh mơ hồ.

\[
MTTRestore = \frac{\sum_{i=1}^{N}(t_{\mathrm{restored},i}-t_{\mathrm{impactStart},i})}{N}
\]

Cần nhấn mạnh: rollback làm checkout bình thường sau 12 phút, còn code fix được merge sau hai ngày. Thời gian phục hồi tác động là 12 phút; thời gian sửa tận gốc không nên gộp vào metric đó.

### 7.1. Phục hồi phải dựa trên trải nghiệm, không dựa trên Pod Running

Những trạng thái sau chưa đủ chứng minh restored:
- Container khởi động được nhưng readiness không đạt.
- API trả HTTP 200 nhưng payload sai.
- Consumer chạy lại nhưng tồn 100.000 message quá hạn.
- Giao dịch mới thành công nhưng giao dịch cũ chưa được đối soát.
- Region A khỏe nhưng region B vẫn lỗi.
- Cache vẫn trả dữ liệu stale vượt giới hạn được phép.

Restoration nên được xác nhận qua **SLI và critical user journey**. Nếu cần cửa sổ xác minh (ví dụ SLI ổn định trong nhiều phút với đủ traffic), ghi rõ quy tắc và có thể lưu cả mốc first-healthy lẫn confirmed-recovery.

### 7.2. Một sự cố tái phát sau vài phút

Nếu trạng thái healthy kéo dài 30 giây rồi lỗi trở lại, có nên coi là hai incident? Cần chính sách ổn định, ví dụ recovery confirmation window hoặc liên kết các pha lỗi cùng nguyên nhân. Không tách/gộp tùy ý chỉ để cải thiện MTTR.

## 8. Tính mean, median, tail và quy mô mẫu

Giả sử năm thời gian khôi phục: 5, 6, 8, 10, 180 phút.

~~~text
Mean   = (5 + 6 + 8 + 10 + 180) / 5 = 41,8 phút
Median = 8 phút
Max    = 180 phút
~~~

Mean cho thấy sự cố dài ảnh hưởng đáng kể đến tổng thời gian; median cho biết incident điển hình. Cả hai đều hữu ích. Khi đủ mẫu, thêm p75, p90, p95; với rất ít sự cố, percentile cao không đáng tin để diễn giải như xu hướng.

Một báo cáo nên ghi:
- Mean, median, max và count.
- Số incident có/thiếu timestamp hợp lệ.
- Incident còn mở trong kỳ.
- Severity và dịch vụ/critical journey.
- Nguồn phát hiện và nhóm nguyên nhân.
- Phạm vi tác động và business impact.

**Survivorship/censoring bias:** nếu chỉ tính incident đã đóng trong tháng và bỏ một incident kéo dài chưa phục hồi, trung bình có thể thấp giả. Cần báo incident còn mở và thời gian tác động tính đến cuối kỳ, không tự gán restoredAt.

## 9. Tính toán ví dụ ba sự cố

| ID | Impact start | Detected/alert | ACK | Mitigation | Restored |
|---|---|---|---|---|---|
| INC-101 | 09:00 | 09:03 | 09:05 | 09:12 | 09:20 |
| INC-102 | 13:00 | 13:10 | 13:12 | 13:20 | 13:30 |
| INC-103 | 17:00 | 17:02 | 17:03 | 17:07 | 17:10 |

Giả sử trong ví dụ detectedAt = alertFiredAt cho cả ba, ta có:

| ID | Detect | ACK | Mitigate từ impact | Restore |
|---|---:|---:|---:|---:|
| INC-101 | 3 phút | 2 phút | 12 phút | 20 phút |
| INC-102 | 10 phút | 2 phút | 20 phút | 30 phút |
| INC-103 | 2 phút | 1 phút | 7 phút | 10 phút |
| **Mean** | **5 phút** | **1,67 phút** | **13 phút** | **20 phút** |

~~~text
MTTD = (3 + 10 + 2) / 3 = 5 phút
MTTA = (2 + 2 + 1) / 3 ≈ 1,67 phút
MTTM = (12 + 20 + 7) / 3 = 13 phút
MTTRestore = (20 + 30 + 10) / 3 = 20 phút
~~~

Đây là dữ liệu minh họa, không phải ngưỡng chuẩn. Nếu INC-102 ảnh hưởng toàn bộ thanh toán trong khi hai incident còn lại chỉ liên quan một tenant thử nghiệm, kết quả mean chưa phản ánh độ rộng tác động. Cần phân tích theo severity/scope.

Lưu timestamp có timezone hoặc dạng **Instant UTC**; không trừ chuỗi giờ địa phương nếu incident đi qua nửa đêm hoặc timezone. Đồng bộ đồng hồ và lưu nguyên gốc của từng mốc khi có chỉnh sửa.

## 10. SLI, SLO và error budget

**SLI** là phép đo hành vi dịch vụ, ví dụ tỷ lệ request tốt, độ trễ, độ tươi mới dữ liệu hoặc tỷ lệ job hoàn thành đúng hạn.

**SLO** là mục tiêu cho một SLI trong cửa sổ xác định, ví dụ tỷ lệ checkout tốt đạt ít nhất 99,9% trong 30 ngày.

**Error budget** là tỷ lệ/số lượng lỗi cho phép tương ứng với mục tiêu đó. Ví dụ:

\[
SLI = \frac{\mathrm{Good\ eligible\ attempts}}{\mathrm{All\ eligible\ attempts}}
\]

Định nghĩa **eligible** và **good** phải được chốt theo nghiệp vụ. HTTP 4xx do người dùng nhập sai không nhất thiết là lỗi dịch vụ; HTTP 200 nhưng payment không được ghi có thể là bad event.

Với SLO=99,9%:

~~~text
Allowed bad fraction = 1 - 0,999 = 0,001 = 0,1%
~~~

Nếu minh họa availability theo thời gian liên tục với tháng 30 ngày:

~~~text
30 ngày = 43.200 phút
43.200 × 0,001 = 43,2 phút tương đương downtime
~~~

Đây là **phép quy đổi đơn giản**. Nếu SLI theo request, error budget tương ứng số request xấu trên tổng request đủ điều kiện và phụ thuộc lưu lượng. Năm phút outage giờ cao điểm có thể tiêu hao budget nhiều hơn năm phút giờ ít traffic.

### 10.1. MTTD/MTTR không thay thế SLO

Một tháng có 2 sự cố, tháng khác có 40 sự cố. Dù MTTD và MTTR trung bình đều giống nhau, mức độ ảnh hưởng tới người dùng rất khác. Do đó cần đo đồng thời:
- Availability/latency/data correctness SLI.
- Error budget consumed/remaining.
- Incident count và severity.
- Thời gian phát hiện/khôi phục.
- Phạm vi tác động.

Ngược lại, SLO đạt trong một tháng ít sự cố không chứng minh hệ thống phát hiện tốt một lỗi hiếm khi xảy ra.

## 11. Burn rate: cảnh báo theo tốc độ tiêu hao budget

**Burn rate** thể hiện tốc độ lỗi so với mức lỗi cho phép để tiêu đều budget:

~~~text
Burn rate = observed bad-event fraction
            / allowed bad-event fraction
~~~

Ví dụ allowed bad fraction=0,001; observed bad fraction=0,01:

~~~text
Burn rate = 0,01 / 0,001 = 10
~~~

Burn rate=10 trong cửa sổ xét nghĩa là budget đang được tiêu nhanh gấp 10 lần mức đều tương ứng. Nó không nói trực tiếp incident sẽ kéo dài bao lâu.

Alert có thể kết hợp **cửa sổ ngắn và dài** nhằm phát hiện các đợt lỗi lớn nhanh mà không page liên tục vì spike ngắn. Cần cân nhắc tổng sample, traffic, missing series và độ tin cậy của metric. API chỉ vài request/giờ có thể cần synthetic probe hoặc tín hiệu khác thay vì dùng tỷ lệ lỗi 5 phút với mẫu rất nhỏ.

Không nên đặt một burn-rate threshold “chuẩn” cho mọi dịch vụ. Ngưỡng page phụ thuộc SLO, thời gian quan sát, mức nghiêm trọng và việc có hành động ngay hay không.

## 12. Cảnh báo tốt phải có hành động cụ thể

Một alert nên trả lời:

- Dịch vụ, môi trường, region và SLI nào đang bị ảnh hưởng?
- Điều kiện nào đã vượt ngưỡng, bao lâu và có bao nhiêu mẫu?
- Có dashboard, trace, deployment marker hoặc runbook liên quan không?
- Ai là người trực chịu trách nhiệm, escalation tiếp theo ra sao?
- Bước triage đầu tiên nên làm gì?
- Có thể dừng rollout, rollback hoặc tắt tính năng an toàn không?
- Điều kiện nào xác nhận restored?

Ví dụ alert:

~~~text
Checkout availability budget burn HIGH

service: checkout
environment: production
region: ap-southeast-1
bad-event ratio: 2,6% trong cửa sổ quan sát
allowed bad fraction: 0,1%
primary on-call: checkout-oncall

First action:
- Xác nhận SLI/synthetic theo region, cohort và version.
- Kiểm tra deploy/config gần nhất.
- Kiểm tra Payment timeout và DB pool wait.
- Dùng runbook để dừng rollout hoặc giảm tác động an toàn.
~~~

Số liệu chỉ minh họa. Tránh đưa token, dữ liệu cá nhân hoặc payload thô vào alert. Chỉ dẫn xử lý nên cụ thể nhưng không khuyến khích tắt TLS, mở quyền admin hoặc xóa dữ liệu để chữa nhanh.

### 12.1. Page, ticket và informational event

**Page** khi cần phản ứng ngay để giảm tác động hiện tại, có người trực và hành động khả thi.

**Ticket** khi vấn đề chưa cần phản ứng tức thì nhưng cần sửa theo kế hoạch.

**Informational event** khi lưu sự kiện thay đổi trạng thái phục vụ phân tích, không cần làm phiền on-call.

Cảnh báo CPU >80% có thể hữu ích trong một số tình huống, nhưng nếu CPU cao vẫn phục vụ trong SLO và không có nguy cơ saturation, việc page liên tục có thể gây noise. Ưu tiên cảnh báo kết quả người dùng và saturation có liên hệ rõ.

## 13. Đo chất lượng alert

| Chỉ số | Ý nghĩa | Thực hành |
|---|---|---|
| **Detection coverage** | Tỷ lệ incident thật có cảnh báo đúng | Cần danh sách incident từ nhiều nguồn |
| **Precision** | Bao nhiêu page có hành động hợp lý | Phân loại false/true actionable page |
| **Recall** | Bao nhiêu incident thuộc phạm vi page được phát hiện | Không bỏ sót lỗi âm thầm |
| **False-page rate** | Mức nhiễu làm phiền on-call | Xem theo rule và người nhận |
| **Pages per shift** | Gánh nặng trực theo ca | Không chỉ tổng theo tháng |
| **Escalation rate** | Bao nhiêu alert phải chuyển nhóm | Phát hiện ownership sai |
| **Repeated pages per incident** | Một sự cố gây bao nhiêu alert | Giảm duplication |
| **Time to actionable context** | Từ page đến có thông tin định vị | Cải thiện dashboard/runbook |

Công thức minh họa:

~~~text
Precision = actionable true-positive pages / all pages in scope
Recall = alerted incidents requiring a page
         / all incidents requiring a page in scope
~~~

Đội cần định nghĩa nhất quán “actionable” và “incident requiring a page” để người đánh giá không tùy tiện đổi nhãn. Một sự cố sinh 20 page không trở thành 20 incident.

**Alert fatigue** làm việc phát hiện nhanh trở nên khó khăn: người trực phải xử lý nhiều thông báo ít giá trị, dễ bỏ qua tín hiệu quan trọng. Mục tiêu giảm noise phải đi kèm bảo vệ recall để không giảm phiền nhiễu bằng cách tắt mọi cảnh báo.

## 14. Synthetic monitoring và business SLI

Nhiều lỗi không làm HTTP 5xx tăng:
- API trả 200 nhưng giao dịch chưa được ghi.
- Payment callback bị mất.
- Order event không được phát ra broker.
- Cache hiển thị trạng thái sai.
- Đối soát tài chính không khớp.
- Queue vẫn nhận message nhưng không hoàn thành đúng deadline.

Nên kết hợp:

1. **Black-box synthetic:** chạy hành trình đại diện từ phía ngoài, ví dụ login, tìm kiếm, checkout thử có kiểm soát.
2. **White-box telemetry:** lỗi ứng dụng, saturation, dependency timeout, consumer lag.
3. **Business events:** thành công theo nghiệp vụ, transaction state, đơn hoàn tất đúng hạn.
4. **Reconciliation:** phát hiện thiếu/sai record khi API/log đều có vẻ bình thường.
5. **Client-side telemetry:** đo trải nghiệm theo thiết bị, quốc gia, region và CDN.

Synthetic phải dùng dữ liệu thử, không gây giao dịch thực ngoài ý muốn. Nếu probe chạy mỗi 60 giây, lỗi xảy ra ngay sau probe tốt có thể chờ gần 60 giây mới được nhìn thấy. Thêm quy tắc “ba lần liên tiếp thất bại” có thể giảm nhiễu nhưng làm TTD dài hơn. Chọn tần suất theo SLO, rủi ro và chi phí.

## 15. Phân loại sự cố để báo cáo công bằng

Nên nhóm incident theo:

- Service/critical journey: checkout, login, search, payment, inventory.
- Severity dựa trên tác động nghiệp vụ, không dựa vào độ khó sửa.
- Region, tenant, cohort hoặc tỷ lệ request bị ảnh hưởng.
- Nguồn phát hiện: SLO alert, synthetic, reconciliation, customer support.
- Nhóm nguyên nhân: code deploy, config, capacity, dependency, data correctness, security, provider.
- Cơ chế phục hồi: rollback, feature flag, traffic shift, manual workaround, failover, data repair.
- Incident xảy ra giờ cao điểm hay ít traffic.
- Mức chắc chắn của các timestamp: observed, estimated, unknown.

Ví dụ tổng MTTR=25 phút có thể che: median cho lỗi config=8 phút, median lỗi data migration=90 phút, incident nhà cung cấp mất quyền điều khiển trực tiếp. Kết luận hữu ích là cải tiến từng loại, không ép một con số cho tất cả.

Tránh dùng MTTR thô để xếp hạng cá nhân/nhóm khi hệ thống, scope và mức khó rất khác nhau. Mục tiêu là tìm **điểm nghẽn có thể sửa**.

## 16. Phạm vi tác động: không chỉ đo số phút

Một outage 20 phút ảnh hưởng 100% checkout khác với 20 phút lỗi 1% người dùng thử nghiệm. Nên ghi thêm:

- Bad requests/eligible attempts.
- Số lượng giao dịch thất bại và số giao dịch cần retry.
- Số tenant hoặc người dùng bị ảnh hưởng nếu có thể đếm đáng tin.
- Message age, backlog và số công việc xử lý muộn.
- Bản ghi dữ liệu sai/cần đối soát.
- Thời lượng tác động theo region hoặc nhóm đối tượng.
- Ước lượng customer-minutes/user-minutes nếu phương pháp đủ rõ.
- Mức mất doanh thu hoặc chi phí nghiệp vụ khi có cơ sở dữ liệu.

Không tự suy số người dùng duy nhất từ số request. Một user gửi nhiều request có thể làm số request cao nhưng số user thấp. Tránh xây bảng chứa PII thô nếu chỉ cần kết quả tổng hợp.

Với SLI theo request, **số bad events và error budget tiêu hao** thường phản ánh impact tốt hơn công thức uptime đơn giản.

## 17. RTO, RPO khác với MTTR

**RTO – Recovery Time Objective** là mục tiêu thời gian khôi phục theo kế hoạch liên tục kinh doanh/DR.

**RPO – Recovery Point Objective** là mục tiêu mức mất dữ liệu tối đa tính theo khoảng thời gian.

**MTTRestore** là thống kê những lần phục hồi đã xảy ra.

| Khái niệm | Loại | Ví dụ |
|---|---|---|
| RTO | Mục tiêu khôi phục | Trong 60 phút |
| RPO | Mục tiêu dữ liệu | Không mất quá 5 phút dữ liệu |
| MTTRestore | Thống kê thực | Mean 22 phút cho incident được đo |
| Recovery drill time | Kết quả diễn tập | DB failover sau 18 phút |
| Availability SLO | Mục tiêu phục vụ | 99,9% good requests |

MTTR trung bình dưới RTO không bảo đảm mọi incident đạt RTO. Một sự cố 4 giờ vẫn có thể bị che bởi nhiều sự cố 2 phút. RTO đạt nhưng RPO không đạt vẫn có thể là thất bại nghiêm trọng.

Chỉ có snapshot backup chưa đủ để chứng minh RPO; cần thử restore và kiểm tra **dữ liệu thật có thể sử dụng**. Đừng ghi restoredAt khi DB chỉ khởi động mà giao dịch vẫn lỗi hoặc dữ liệu còn không nhất quán.

## 18. Phân biệt khôi phục và sửa nguyên nhân

~~~text
Triage
   |
Mitigation: giảm phạm vi người dùng chịu lỗi
   |
Restoration: SLI/journey trở lại mức phục vụ
   |
Permanent fix: sửa cơ chế gốc
   |
Prevention: test, runbook, alert, kiến trúc mới
~~~

Khi có rollback an toàn, không nhất thiết phải chờ tìm đủ root cause mới giảm tác động. Sau khi restored, vẫn cần điều tra nguyên nhân để giảm sự cố tái diễn.

Theo dõi action item với owner, deadline và cách xác minh, không chỉ số bài postmortem đã tạo. Một mục “cải thiện monitoring” không có tiêu chí cụ thể sẽ khó kiểm chứng. Một mục tốt: “Synthetic checkout phát cảnh báo trong bài diễn tập dưới ngưỡng TTD đã duyệt mà không tăng false pages quá ngân sách”.

## 19. Runbook: giảm phụ thuộc vào trí nhớ người trực

Ví dụ runbook:

~~~markdown
# Runbook: Checkout SLO giảm

## Tín hiệu
- Checkout good-event ratio giảm
- Error-budget burn tăng
- Payment timeout, DB pool wait hoặc retries tăng

## Triage
1. Xác nhận tác động bằng SLI và synthetic.
2. So sánh theo region, version, tenant và dependency.
3. Kiểm tra deploy/config gần nhất.
4. Xác định bottleneck từ trace, metric và log.

## Mitigation
- Dừng rollout nghi vấn.
- Rollback nếu tương thích schema và dữ liệu.
- Tắt feature flag tùy chọn nếu an toàn.
- Giảm concurrency hoặc chuyển traffic theo chính sách.

## Recovery verification
- Critical journey và SLO trở lại ngưỡng.
- Backlog/retry/data consistency được kiểm tra riêng.
- Đủ thời gian và số mẫu xác nhận phục hồi.

## Escalation
- Checkout on-call, Payment/DB/platform owner.
- Quy tắc gọi incident commander và truyền thông.
~~~

Runbook phải có quyền thực thi phù hợp; một lệnh đòi cluster-admin mà on-call không được cấp có thể kéo dài mitigation. Không mở quyền tùy tiện để “chữa” nhanh. Định kỳ diễn tập và sửa đường dẫn, ví dụ lệnh rollback cũng phải xét schema DB, config và secret đã thay.

## 20. Những thay đổi kiến trúc làm giảm thời gian tác động

| Kỹ thuật | Khâu chủ yếu được cải thiện | Đánh đổi cần xem xét |
|---|---|---|
| User-centric SLI và synthetic | Detection | False page, chi phí probe |
| Distributed tracing và correlation ID | Triage | Instrumentation, sampling |
| Deployment/config marker | Triage | Cần version có thể truy vết |
| Canary + auto-stop rollout | Giảm phạm vi tác động | Cần guardrail đáng tin |
| Feature flag/kill switch | Mitigation | Có thể không đảo ngược side effect |
| Blue/green và rollback | Restore | DB/schema/secret có thể không tương thích |
| Circuit breaker/bulkhead | Cô lập lỗi | Fallback không được làm sai nghiệp vụ |
| Multi-zone và failover | Restore khi hạ tầng lỗi | RTO/RPO, replication, split-brain |
| Idempotency, outbox, DLQ | Khôi phục dữ liệu và backlog | Hợp đồng retry và replay |
| Runbook/on-call ownership | Triage và mitigation | Cần diễn tập, bảo trì |
| Data reconciliation | Phát hiện lỗi âm thầm | Có độ trễ và chi phí |

**Ưu tiên theo dữ liệu:** Nếu 80% thời lượng sự cố nằm trước detect, thêm alert có chất lượng. Nếu detect trong 1 phút nhưng rollback mất 90 phút, đầu tư đường khôi phục. Nếu restored nhanh nhưng lỗi tái diễn hàng tuần, cải thiện phòng ngừa.

## 21. Dashboard vận hành nên trả lời gì?

Một dashboard hiện trạng nên trả lời lần lượt:

1. Có user impact ngay bây giờ không? SLI, latency p95/p99, success rate, message freshness.
2. Phạm vi ở đâu? Region, version, tenant/cohort được phép.
3. Incident nào đang mở? Severity, owner, timeline.
4. Thay đổi gần nhất? Deploy, flag, config, DB migration, network policy.
5. Dependency nào đang nghẽn? Connection pool, queue age, retry, saturation.
6. Đường phục hồi khả dụng? Runbook, rollback version, traffic shift.
7. Hệ thống có đủ quan sát để xác nhận restored không?

Một báo cáo xu hướng tháng nên thể hiện thêm:
- Incident count và số còn mở.
- MTTD, MTTA, MTTM, MTTRestore theo service/severity.
- Mean/median/tail và số mẫu thiếu.
- Error budget consumed, outage/business impact.
- Alert precision/recall/pages per shift.
- Repeated incidents và action items đã kiểm chứng.
- RTO/RPO drill result và toil.

Đừng lẫn dashboard khẩn cấp với báo cáo thành tích. Trong incident, **cần hành động rõ** quan trọng hơn biểu đồ đẹp.

## 22. Thiết kế incident record có thể tính toán

~~~json
{
  "incidentId": "INC-2026-104",
  "service": "checkout",
  "severity": "SEV2",
  "region": "ap-southeast-1",
  "impactStartAt": "2026-11-12T02:00:00Z",
  "firstSignalAt": "2026-11-12T02:02:00Z",
  "alertFiredAt": "2026-11-12T02:03:00Z",
  "notificationDeliveredAt": "2026-11-12T02:03:30Z",
  "detectedAt": "2026-11-12T02:03:00Z",
  "acknowledgedAt": "2026-11-12T02:05:00Z",
  "mitigationEffectiveAt": "2026-11-12T02:12:00Z",
  "restoredAt": "2026-11-12T02:20:00Z",
  "closedAt": "2026-11-13T08:00:00Z",
  "detectionSource": "SLO_ALERT",
  "mitigationType": "ROLLBACK",
  "timestampsQuality": "OBSERVED"
}
~~~

Đây là schema minh họa; trong thực tế có thể cần nhiều impact intervals hoặc nhiều mitigation. Mỗi mốc phải có bằng chứng:
- Metric query hoặc synthetic result.
- Alert/pager event ID.
- Người xác nhận.
- Deployment/config revision.
- Recovery verification query.
- Phương pháp ước lượng nếu timestamp không được quan sát trực tiếp.

Giữ audit khi sửa mốc hoặc severity. Không lưu secret, PII hoặc raw payload trong incident record chỉ để có “bằng chứng đầy đủ”.

## 23. Một incident có nhiều pha tác động

~~~text
10:00 Checkout lỗi 50% tại region A
10:05 Alert
10:10 Rollback làm lỗi giảm còn 15%
10:20 Một vùng traffic vẫn lỗi
10:30 Giao dịch mới hồi phục
11:00 Backlog giao dịch cũ xử lý hết
11:15 Data reconciliation xác nhận kết quả
~~~

Có thể ghi các mốc:
- First meaningful mitigation: 10:10.
- Online traffic restored: 10:30.
- Backlog cleared: 11:00.
- Data reconciled: 11:15.

Nếu có nhiều interval, lưu từng khoảng với scope/tỷ lệ tác động thay vì một biến outageDuration đơn giản. Một tác vụ trả HTTP 200 trở lại lúc 10:30 chưa chắc có nghĩa mọi khách hàng bị ảnh hưởng trước đó đã được khôi phục dữ liệu.

Điều kiện nào là restored phụ thuộc vào **SLO và hợp đồng nghiệp vụ**. Có thể báo nhiều mốc, không cần ép mọi tình trạng vào một chữ “resolved”.

## 24. SQL minh họa tính MTTD và MTTRestore

Giả sử bảng PostgreSQL **incidents** có các cột incident_id, service, severity, impact_start_at, detected_at, alert_at, acknowledged_at, restored_at, kiểu thời gian TIMESTAMPTZ.

~~~sql
WITH measured AS (
    SELECT
        incident_id,
        service,
        severity,
        EXTRACT(EPOCH FROM (detected_at - impact_start_at)) / 60.0
            AS detect_minutes,
        EXTRACT(EPOCH FROM (acknowledged_at - alert_at)) / 60.0
            AS ack_minutes,
        EXTRACT(EPOCH FROM (restored_at - impact_start_at)) / 60.0
            AS restore_minutes
    FROM incidents
    WHERE impact_start_at >= TIMESTAMPTZ '2026-11-01 00:00:00+00'
      AND impact_start_at <  TIMESTAMPTZ '2026-12-01 00:00:00+00'
)
SELECT
    service,
    COUNT(*) AS incident_count,
    COUNT(detect_minutes) AS measured_detect_count,
    ROUND(AVG(detect_minutes)::numeric, 2) AS mttd_minutes,
    ROUND(
      PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY detect_minutes)::numeric,
      2
    ) AS median_detect_minutes,
    COUNT(restore_minutes) AS restored_count,
    ROUND(AVG(restore_minutes)::numeric, 2) AS mttr_minutes,
    ROUND(
      PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY restore_minutes)::numeric,
      2
    ) AS median_restore_minutes
FROM measured
GROUP BY service
ORDER BY service;
~~~

**Giới hạn của ví dụ:** trước khi tổng hợp, cần kiểm tra timestamp trống, trật tự không hợp lệ và dữ liệu nhập tay. PostgreSQL AVG bỏ NULL; cần có số mẫu để người xem biết thiếu dữ liệu bao nhiêu. Sự cố đang mở không có restoredAt phải được báo riêng thay vì bị biến thành sự cố 0 phút.

Ngoài ra, cần chọn cohort theo **impactStartAt** hoặc **restoredAt** và ghi rõ. Incident kéo dài qua ranh giới tháng sẽ khác kết quả tùy phương pháp nhóm. Khi tính tác động trong một tháng, hãy cắt các khoảng impact theo cửa sổ thay vì chỉ dựa tháng bắt đầu.

## 25. Java 21: tính khoảng thời gian an toàn

~~~java
import java.time.Duration;
import java.time.Instant;
import java.util.Objects;
import java.util.Optional;

record IncidentTimeline(
        String incidentId,
        Instant impactStartedAt,
        Instant detectedAt,
        Instant alertFiredAt,
        Instant acknowledgedAt,
        Instant mitigatedAt,
        Instant restoredAt) {

    IncidentTimeline {
        Objects.requireNonNull(incidentId);
        Objects.requireNonNull(impactStartedAt);
    }

    Optional<Duration> timeToDetect() {
        return duration(impactStartedAt, detectedAt);
    }

    Optional<Duration> timeToAcknowledge() {
        return duration(alertFiredAt, acknowledgedAt);
    }

    Optional<Duration> timeToMitigate() {
        return duration(impactStartedAt, mitigatedAt);
    }

    Optional<Duration> timeToRestore() {
        return duration(impactStartedAt, restoredAt);
    }

    private static Optional<Duration> duration(Instant start, Instant end) {
        if (start == null || end == null || end.isBefore(start)) {
            return Optional.empty();
        }
        return Optional.of(Duration.between(start, end));
    }
}
~~~

Đây là ví dụ đơn giản: nếu mốc thiếu hoặc đảo thứ tự, không tạo Duration âm và không mặc định 0. Trong production, cần phân biệt **missing** với **invalid** cùng reason code để không làm mất dấu lỗi dữ liệu.

### 25.1. Unit test

~~~java
import static org.junit.jupiter.api.Assertions.*;
import java.time.Duration;
import java.time.Instant;
import org.junit.jupiter.api.Test;

final class IncidentTimelineTest {
    @Test
    void durationUsesExplicitMilestones() {
        Instant start = Instant.parse("2026-11-12T02:00:00Z");
        IncidentTimeline incident = new IncidentTimeline(
            "INC-1",
            start,
            start.plusSeconds(180),
            start.plusSeconds(180),
            start.plusSeconds(300),
            start.plusSeconds(720),
            start.plusSeconds(1200)
        );

        assertEquals(Duration.ofMinutes(3),
            incident.timeToDetect().orElseThrow());
        assertEquals(Duration.ofMinutes(2),
            incident.timeToAcknowledge().orElseThrow());
        assertEquals(Duration.ofMinutes(12),
            incident.timeToMitigate().orElseThrow());
        assertEquals(Duration.ofMinutes(20),
            incident.timeToRestore().orElseThrow());
    }

    @Test
    void missingAndBackwardDatesDoNotBecomeZero() {
        Instant start = Instant.parse("2026-11-12T02:00:00Z");
        IncidentTimeline incident = new IncidentTimeline(
            "INC-2", start, start.minusSeconds(30),
            null, null, null, null
        );
        assertTrue(incident.timeToDetect().isEmpty());
        assertTrue(incident.timeToRestore().isEmpty());
    }
}
~~~

**Đồng hồ:** Dùng monotonic clock như System.nanoTime để đo khoảng thời gian trong cùng tiến trình; không trừ nanoTime của hai tiến trình khác nhau. Incident timeline xuyên service cần timestamp UTC từ nguồn có đồng bộ thời gian, lưu clock uncertainty và origin khi cần.

## 26. PromQL minh họa SLI và burn rate

Giả sử ứng dụng xuất hai counter đã được thiết kế theo business definition:

~~~text
checkout_attempts_total{result="good"}
checkout_attempts_total{result="bad"}
~~~

Tỷ lệ bad attempts trong 5 phút:

~~~promql
sum(rate(checkout_attempts_total{result="bad"}[5m]))
/
sum(rate(checkout_attempts_total{result=~"good|bad"}[5m]))
~~~

Với allowed bad fraction=0,001, burn rate:

~~~promql
(
  sum(rate(checkout_attempts_total{result="bad"}[5m]))
  /
  sum(rate(checkout_attempts_total{result=~"good|bad"}[5m]))
) / 0.001
~~~

Tên metric và label chỉ là ví dụ. Query production phải xử lý denominator quá nhỏ hoặc bằng 0, missing series, reset counter, scrape gap, tỷ lệ traffic theo region và điều kiện tối thiểu số mẫu. Không coi tình trạng "No Data" mặc nhiên là khỏe.

Khi alert có điều kiện chờ qua nhiều evaluation cycles, alertFiredAt muộn hơn thời điểm lỗi đầu tiên. Vì vậy **không dùng alertFiredAt làm T0 và T1 cùng lúc** khi tính MTTD.

## 27. Instrumentation trong microservices

Một hệ thống quan sát có thể kết hợp:

**Metrics:** good/bad-event ratio, p95/p99, saturation, DB pool wait, rate limit, retry attempts, circuit breaker, consumer lag, queue age, error-budget burn.

**Logs:** service, environment, version, traceId, action result và mã lỗi có cấu trúc; tránh log raw token hoặc PII.

**Traces:** các span xuyên HTTP/gRPC, message broker, database; xem đường tới hạn, fan-out và dependency bị chậm.

**Business events:** OrderCreated, PaymentConfirmed, InvoiceGenerated, JobCompleted; kiểm tra số lượng và tính đúng của quá trình xử lý.

**Change markers:** image digest, deployment revision, feature flag và schema/config version, kèm thời điểm.

Một API có thể khỏe trong dashboard HTTP nhưng consumer đã kẹt. Hãy dùng SLI về **freshness** của event và giới hạn deadline xử lý thay vì chỉ theo CPU, Pod Running hoặc message received.

Tăng log/tracing không kiểm soát có thể làm tốn tài nguyên và lộ dữ liệu; dùng sampling, retention, phân quyền và nhãn metric có cardinality hợp lý.

## 28. Sự cố hàng đợi: phục hồi consumer khác với phục hồi nghiệp vụ

Ví dụ:
- 09:00 consumer dừng tiến triển, backlog bắt đầu tăng.
- 09:05 tuổi message vượt ngưỡng.
- 09:07 alert tới on-call.
- 09:12 worker restart thành công.
- 09:15 throughput tăng nhưng backlog vẫn lớn.
- 09:40 backlog trở lại mức freshness cho phép.

Nếu SLO là **90% event xử lý trong 2 phút**, restoredAt có thể gắn với mốc freshness phục hồi, không phải Pod Ready lúc 09:12. Nên lưu:
- Processing resumed.
- Queue age restored.
- Backlog cleared.
- Dữ liệu đã đối soát nếu cần.

Scale worker để xử lý backlog phải giới hạn concurrency để không nghẽn DB. Nếu tăng replica gây rebalance liên tục hoặc gửi retry storm, một thao tác khôi phục có thể tạo incident thứ hai.

## 29. Lỗi dữ liệu âm thầm cần đo thời gian phát hiện riêng

Một lỗi kiểu:
- PaymentCompleted phát trước khi DB commit.
- Số dư cập nhật sai đơn vị.
- Order event bị mất nhưng HTTP trả 200.
- Dữ liệu được ghi vào sai tenant.
- Report không đầy đủ trong nhiều giờ.

Có thể không làm 5xx tăng. Cần invariant và reconciliation:
- Order được commit ↔ event đã xuất bản.
- Payment gateway xác nhận ↔ trạng thái nội bộ.
- Đơn hàng có transition hợp lệ trong state machine.
- Số tiền/đơn vị khớp hợp đồng.
- Job hoặc event hoàn thành trước deadline.

Nếu reconciliation chạy hàng giờ, MTTD có giới hạn theo chu kỳ kiểm tra. Muốn phát hiện sớm hơn, đưa các invariant quan trọng gần đường xử lý, thêm tín hiệu event missing hoặc tăng cadence có kiểm soát.

Một bản fix dừng ghi sai dữ liệu mới khác với việc sửa record đã sai. Ghi **bad writes stopped**, **online service restored** và **data reconciled** riêng khi nghiệp vụ yêu cầu.

## 30. Hiệu quả on-call và toil

Đội có thể đạt MTTA ngắn nhưng bị hàng chục page vô ích mỗi đêm. Đo thêm:
- Pages per on-call shift và tỷ lệ ngoài giờ.
- Tỷ lệ page cần hành động.
- Escalation và số lần chuyển nhóm.
- Thời gian từ page đến thông tin hữu ích đầu tiên.
- Số lỗi lặp cùng nguyên nhân.
- Số thao tác thủ công cần cho rollback.
- Giờ công dành cho toil so với cải tiến lâu dài.
- Số runbook đã diễn tập và còn chính xác.
- Tỷ lệ action item hoàn thành **và được xác minh**.

**Toil** là công việc vận hành lặp lại, chủ yếu thủ công, mang tính phản ứng và có xu hướng tăng theo quy mô. Không phải mọi thao tác thủ công đều xấu; những thao tác phá hủy hoặc nhạy cảm có thể cần phê duyệt. Mục tiêu là tự động hóa ở nơi giúp **giảm rủi ro và thời lượng tác động**, không chạy automation mù.

### 30.1. Self-healing không tự động có nghĩa reliability tốt

Một Pod tự restart 50 lần/ngày có thể không tạo incident lớn, nhưng nó chỉ ra bug hoặc resource limit không phù hợp. Theo dõi:
- Restart count và lý do.
- User impact mỗi lần restart.
- Idempotency khi message được xử lý lại.
- Tần suất tự phục hồi vượt mức.
- Chi phí và tải downstream do autoscaling/retry.
- Có action item xử lý nguyên nhân tái diễn hay không.

Một hệ thống restart nhanh nhưng thường xuyên gây timeout không nên được đánh giá là “vận hành hiệu quả” chỉ vì restoration time thấp.

## 31. Postmortem: học từ timeline, không đổ lỗi cá nhân

Một postmortem nên trả lời:
1. Điều gì xảy ra với người dùng và dữ liệu?
2. Timeline nào được chứng minh bằng metric, log, deploy và pager?
3. Vì sao tín hiệu phát hiện không xuất hiện sớm hơn?
4. Hành động nào giảm tác động và mất bao lâu để thực hiện?
5. Những điều kiện hệ thống/quy trình nào làm lỗi lan rộng?
6. Phương án rollback, data migration và recovery path có vấn đề gì?
7. Cần thay đổi test, alert, runbook hoặc kiến trúc nào?
8. Ai sở hữu, deadline và điều kiện kiểm chứng của từng action item?

Tránh kết luận kiểu “người trực phản ứng sai” mà không hỏi vì sao dashboard thiếu dữ liệu, quyền rollback không đủ hoặc quy trình lệnh lỗi. Tập trung vào điều kiện cho phép một quyết định sai xảy ra và xây rào cản có thể kiểm chứng.

## 32. Game day và diễn tập phục hồi

| Kịch bản | Detection mong đợi | Mitigation/restore cần thử | Metric |
|---|---|---|---|
| Kill một replica | Readiness/traffic redistribution | Tự thay instance | User impact và thời gian |
| Payment API chậm | SLI burn, downstream timeout | Circuit breaker, deadline | TTD, retry amplification |
| DB pool cạn | Pool wait và error rate | Giảm concurrency/rollback | Thời gian triage |
| Mất một zone | Synthetic theo vùng | Traffic shift/failover | RTO thực |
| Kafka consumer kẹt | Queue age/lag | Xử lý poison/restart | Freshness restored |
| Cấu hình mới lỗi | Canary SLI | Dừng rollout, rollback revision | Thời gian và phạm vi |
| Backup cần restore | Drill theo mất dữ liệu | Restore/validate/reconcile | RTO và RPO thực |

Diễn tập phải có owner, phạm vi, blast radius, điều kiện dừng, quyền thực thi và phương án phục hồi. Không tạo sự cố trong production ngoài quy trình đã được duyệt.

**Lưu ý:** khi đội chủ động tạo lỗi đúng thời điểm, không thể coi detection latency của game day là bằng chứng MTTD production cho sự cố bất ngờ. Ghi rõ kết quả diễn tập và kiểm tra khả năng lặp.

## 33. Case study: checkout suy giảm sau deployment

Giả sử:
- 10:00 deploy v2 bắt đầu.
- 10:04 checkout error rate tăng.
- 10:06 SLO alert fired.
- 10:07 notification delivered.
- 10:09 on-call ACK và triage.
- 10:12 phát hiện retry storm theo version mới.
- 10:13 dừng rollout và bắt đầu rollback.
- 10:17 rollback có hiệu lực, lỗi giảm.
- 10:21 checkout SLO trở lại ngưỡng sau xác minh.
- 10:35 backlog giao dịch cũ được xử lý và đối soát.

Nếu detectedAt=10:06, impactStart=10:04, alertAt=10:06, ACK=10:09:

~~~text
Time to detect      = 2 phút
Time to ACK         = 3 phút
Time to mitigate    = 13 phút (từ 10:04 đến 10:17)
Time to restore     = 17 phút (từ 10:04 đến 10:21)
Backlog clear delay = 31 phút (từ 10:04 đến 10:35)
~~~

Không kết luận incident restored lúc 10:13 chỉ vì lệnh rollback đã được gửi. Cũng không dùng thời điểm merge fix ngày hôm sau làm mốc phục hồi người dùng.

Cải tiến phù hợp:
- Retry budget và backoff cho Payment.
- Trace/metric theo version.
- Canary guardrail tự dừng rollout.
- Runbook rollback có điều kiện dữ liệu tương thích.
- Điều kiện restored bao gồm dữ liệu/backlog khi SLO yêu cầu.

## 34. Kịch bản đặc biệt: online đã khỏe nhưng dữ liệu vẫn sai

Một bản mới làm tăng tỷ lệ ghi sai đơn. Rollback lúc 15:00 khiến giao dịch mới đúng, nhưng 3.000 bản ghi sai từ trước cần xử lý đến 16:30.

Nếu chỉ dựa HTTP success rate, hệ thống “khỏe” lúc 15:00. Nếu SLO bao gồm **tính đúng của trạng thái đơn hàng**, tác động có thể chưa chấm dứt. Nên ghi:
- New traffic restored: 15:00.
- Bad writes stopped: 15:00.
- Existing records reconciled: 16:30.
- Customer remediation completed: mốc khác nếu cần.

Có thể quản lý hai mục tiêu restoration riêng, nhưng phải giải thích rõ: phục hồi online, phục hồi dữ liệu và đóng incident là ba trạng thái khác nhau.

## 35. Những sai lầm đo lường thường gặp

| Sai lầm | Hậu quả | Cách khắc phục |
|---|---|---|
| Đặt impactStart = alertAt | MTTD gần 0 giả tạo | Ước lượng từ SLI/synthetic/record |
| Chỉ tính incident được alert phát hiện | Bỏ lỗi âm thầm | Thu nhận cả incident từ support/reconciliation |
| Gộp Restore và Resolve | Metric phụ thuộc thời gian đóng ticket | Mốc rõ theo user journey |
| Chỉ tính incident đã đóng | Bỏ outage dài đang mở | Báo censoring và open incidents |
| Chỉ báo mean | Sự cố tail bị che hoặc số đo lệch | Median/max/count và phân nhóm |
| Tách outage để giảm trung bình | KPI sai | Quy tắc gộp/tách nhất quán |
| Hạ severity khi xử lý khó | So sánh lệch | Severity theo tác động |
| ACK thật nhanh nhưng không triage | MTTA đẹp, người dùng không hưởng lợi | Đo mitigation/restoration |
| Tắt nhiều alert để giảm noise | Recall giảm, MTTD tăng | Đo precision và recall |
| Chỉ đo HTTP 5xx | Bỏ lỗi giao dịch 200 sai | Business SLI và reconciliation |
| Xem Pod Running là restored | Backlog/data vẫn lỗi | Recovery verification |
| MTTR dưới RTO nghĩa là luôn đạt | Một outage dài vẫn vượt RTO | Phân phối, max, RTO violations |
| Drill chỉ ở staging rất nhẹ | Kết quả quá lạc quan | Tải, dữ liệu, failure mode đại diện |
| Không lưu nguồn timestamp | Không audit được | Evidence và cách ước lượng |
| Tự động restart liên tục được khen là tốt | Lỗi lặp bị che | Theo dõi recurrence/toil |
| Chỉ so sánh các nhóm bằng một KPI | Không phản ánh scope khác nhau | SLO, impact và incident cohort |

## 36. Bài tập thực hành

**Bài A — timeline:** Với ba sự cố ở phần 9, tính MTTD, MTTA, thời gian mitigation và restore. Thử thay định nghĩa detectedAt từ alert fired thành thời điểm con người xác nhận rồi giải thích vì sao hai báo cáo không thể ghép.

**Bài B — incident còn mở:** Trong tháng có bốn sự cố restored sau 5, 10, 30, 60 phút và một sự cố vẫn mở sau 8 giờ. Tính mean chỉ trên incident đã đóng; giải thích thiên lệch và cách báo cáo mẫu chưa hoàn tất.

**Bài C — SLI:** API checkout trả 200 nhưng Payment callback mất. Thiết kế good-event SLI và synthetic journey có thể phát hiện lỗi, nêu nguồn T0 và điều kiện recovery.

**Bài D — alert quality:** Một ca có 50 page, chỉ 5 page cần hành động. Tính precision trong phạm vi quy ước, đề xuất giảm noise mà vẫn bảo vệ recall và cách kiểm chứng sau thay đổi.

**Bài E — RTO/RPO:** DB có RTO 60 phút và RPO 5 phút. Diễn tập restore sau 40 phút nhưng mất 12 phút thay đổi dữ liệu. Đánh giá từng mục tiêu và kế hoạch kiểm tra record cuối cùng.

**Bài F — queue:** Consumer dừng lúc 09:00, restart lúc 09:10, backlog hết lúc 09:45. Định nghĩa restored khi SLO yêu cầu event xử lý trong 2 phút; phân biệt process resumed và freshness restored.

**Bài G — SQL:** Viết query nhóm MTTD/MTTR theo service và severity, báo count valid/invalid/unknown. Xử lý incident qua ranh giới tháng và những incident chưa restored.

**Bài H — runbook:** Viết runbook cho DB pool cạn gồm SLI, trace, triage, mitigation, rollback, xác nhận restored và escalation.

**Bài I — game day:** Thiết kế bài diễn tập Payment API latency tăng 10 lần, xác định deadline và guardrail, điểm dừng, rollback và cách ghi dữ liệu TTD/MTTM mà không giả vờ tương đương production.

**Bài J — dữ liệu sai:** Một incident ghi sai số dư trong 3 giờ, được phát hiện qua đối soát lúc 15:00, ngăn ghi sai lúc 15:10, sửa record xong lúc 16:30. Chọn mốc restored cho online SLO và data correctness SLO.

**Bài K — thực thi cải tiến:** Phân tích 12 incident, 8 incident phát hiện muộn do thiếu synthetic. Thiết kế thay đổi, metric bảo vệ false pages, thử trong game day và cách so sánh hai cohort sau triển khai.

**Bài L — bền vững vận hành:** On-call có MTTA thấp nhưng 30 page mỗi ca và phải restart thủ công. Thiết kế kế hoạch giảm toil, nâng chất lượng alert, thêm auto-recovery có giới hạn và theo dõi recurrence.

## 37. Checklist áp dụng cho dự án

1. **Xác định critical user journey** và good/bad events.
2. **Đặt SLO và error budget** có owner và cửa sổ tính rõ ràng.
3. **Định nghĩa incident** và severity trước khi dùng KPI.
4. **Thống nhất mốc timeline**: impact, detect, alert, ACK, mitigate, restore, close.
5. **Lưu timestamp có timezone**, nguồn bằng chứng và độ bất định nếu cần.
6. **Tách khôi phục online, backlog và dữ liệu** nếu nghiệp vụ yêu cầu.
7. **Dùng alert có hành động**, routing và escalation rõ, kèm runbook.
8. **Đo alert precision/recall** bằng incident đến từ nhiều nguồn.
9. **Instrument metrics/logs/traces/business events** và deployment/config markers.
10. **Báo cả mean, median, max, count và missing data**.
11. **Xem incident còn mở** để không làm đẹp kết quả.
12. **So theo cohort** service, severity, region, failure mode.
13. **Theo dõi SLO/error-budget impact** cùng MTTD/MTTR.
14. **Chuẩn bị đường rollback, failover, feature flag và quyền thực thi**.
15. **Diễn tập sự cố đáng kể** theo RTO/RPO và SLO.
16. **Chuyển postmortem thành action item có owner, hạn và test xác nhận**.
17. **Theo dõi toil, recurrence và pages per shift** để bảo vệ hiệu quả trực.
18. **Bảo vệ dữ liệu nhạy cảm** trong alert, ticket và dashboard.
19. **Ghi version định nghĩa metric** khi thay rule hoặc cách nhóm incident.
20. **Đánh giá lại thường xuyên** khi traffic, dependency hoặc kiến trúc thay đổi.

## 38. Ghi nhớ

- **MTTD** đo thời gian từ tác động đến phát hiện; **MTTA** đo tiếp nhận cảnh báo; **time to mitigate** đo lúc tác động giảm; **time to restore** đo khi hành vi phục vụ được khôi phục.
- **MTTR có nhiều cách hiểu** (Respond/Repair/Restore/Recover/Resolve). Muốn so sánh, luôn ghi công thức và mốc.
- **Mean không đủ**; cần median, tail, số sự cố, phạm vi, severity và incident chưa hoàn tất.
- **SLI/SLO và error budget** phản ánh người dùng, còn timeline giúp tìm nút thắt vận hành. Hai nhóm metric bổ trợ nhau.
- **Alert chất lượng** phải đến đúng người, có hành động, đủ coverage nhưng ít noise; đo precision, recall và gánh nặng ca trực.
- **Mitigation khác restoration; restoration khác permanent fix.** Backlog và data reconciliation có thể có timeline riêng.
- **RTO/RPO là mục tiêu**, MTTR và drill result là số liệu thực; bảo đảm cả tính sẵn sàng lẫn tính đúng dữ liệu.
- **Runbook, canary, rollback, circuit breaker, failover, tracing và synthetic** là đòn bẩy làm ngắn thời gian tác động.
- **Postmortem/game day** chuyển dữ liệu thời gian thành thay đổi được kiểm chứng, tránh KPI hình thức.
- **Chỉ khẳng định phục hồi khi critical journey và SLO hồi phục thật**, không chỉ khi alert tắt hoặc Pod đã Running.

Hiệu quả vận hành của một hệ thống phân tán không được quyết định bởi việc có bao nhiêu dashboard. Nó thể hiện ở khả năng **biết người dùng đang chịu ảnh hưởng gì, phát hiện đúng và đủ sớm, giảm tác động an toàn, khôi phục đúng hợp đồng dữ liệu, rồi dùng bằng chứng của mỗi incident để ngăn lỗi tái diễn**.
