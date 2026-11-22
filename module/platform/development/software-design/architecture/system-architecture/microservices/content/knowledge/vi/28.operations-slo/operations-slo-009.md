# Đánh giá sự cố và theo dõi hành động cải thiện

## 1. Mục tiêu

Trong một hệ thống Microservices, việc khôi phục dịch vụ sau sự cố là cần thiết nhưng chưa đủ. Nếu đội vận hành chỉ sửa triệu chứng, đóng incident ticket và quay lại phát triển tính năng, cùng một kiểu lỗi có thể tái diễn vào lần triển khai tiếp theo. Ngược lại, một cuộc họp hậu kiểm quá dài, tập trung vào việc tìm người chịu trách nhiệm hoặc tạo hàng chục việc không có người sở hữu cũng không giúp hệ thống tin cậy hơn.

**Đánh giá sự cố (incident review/postmortem)** là quá trình xây dựng lại điều đã xảy ra, nhận diện các điều kiện khiến sự cố phát sinh và lan rộng, đánh giá hiệu quả phát hiện/ứng phó, rồi rút ra hành động cải thiện có thể kiểm chứng.

**Theo dõi hành động cải thiện (corrective/preventive action tracking)** bảo đảm bài học không dừng ở tài liệu: mỗi hành động phải có người chịu trách nhiệm, mức ưu tiên, thời hạn, kết quả mong đợi và bằng chứng cho thấy rủi ro đã giảm.

Bài này thuộc nhóm **Vận hành và SLO**, tập trung vào cách biến dữ liệu vận hành và incident review thành cải thiện liên tục của kiến trúc và cách làm việc.

Sau khi học, người đọc có thể:

- Phân biệt sự cố, triệu chứng, tác động, sự kiện kích hoạt, nguyên nhân góp phần và lỗi hệ thống.
- Chuẩn bị cuộc đánh giá sự cố không đổ lỗi, dựa trên bằng chứng.
- Dựng timeline chính xác từ metrics, logs, traces, deployment events và báo cáo khách hàng.
- Đo ảnh hưởng bằng SLI/SLO, error budget, số người dùng và nghiệp vụ bị gián đoạn.
- Phân tích không chỉ nguyên nhân kỹ thuật mà cả các yếu tố làm tăng xác suất, phạm vi và thời gian sự cố.
- Nhóm hành động thành ngăn ngừa, phát hiện, giảm tác động, khôi phục và học hỏi.
- Viết hành động có DRI/owner, deadline, tiêu chí thành công, bằng chứng xác nhận và trạng thái.
- Đánh giá hiệu quả hành động qua test, dashboard, game day hoặc diễn tập phù hợp.
- Theo dõi các sự cố lặp lại và cải tiến quy trình phản ứng/triển khai.

## 2. Các khái niệm cần phân biệt

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| Event | Sự kiện có thể quan sát | Pod restart, HTTP 503 tăng |
| Alert | Tín hiệu cần chú ý theo rule | Checkout success dưới ngưỡng |
| Incident | Sự gián đoạn hoặc suy giảm dịch vụ cần phối hợp ứng phó | Người dùng không tạo được đơn |
| Symptom | Biểu hiện của sự cố | Timeout, p99 tăng, queue lag |
| Trigger | Sự kiện gần thời điểm khởi phát | Deploy cấu hình retry mới |
| Contributing factor | Điều kiện làm sự cố dễ xảy ra, nặng hơn hoặc khó phát hiện | Không có retry budget, thiếu cảnh báo |
| Root cause | Một hoặc nhiều cơ chế cốt lõi trong mô hình nhân quả cụ thể | Retry amplification vượt quota provider |
| Impact | Hậu quả đối với người dùng/nghiệp vụ | 9.000 checkout thất bại |
| Mitigation | Hành động giảm tác động nhanh | Tắt feature flag, chuyển traffic |
| Resolution | Sự cố đã không còn gây tác động theo tiêu chí xác định | Business success phục hồi |
| Corrective action | Khắc phục một điểm yếu đã bộc lộ | Giới hạn retry xuyên service |
| Preventive action | Giảm xác suất những biến thể lỗi tương tự | Chaos test phụ thuộc 429 trong CI |
| Follow-up | Công việc được theo dõi sau incident | Có owner, deadline, nghiệm thu |
| Postmortem | Bản ghi và phân tích sau sự cố | Timeline, impact, factors, actions |

**Incident không đồng nghĩa bug đơn lẻ.** Một sự cố có thể hình thành do nhiều hệ thống và điều kiện cùng kết hợp: code xử lý 429, cấu hình retry, lưu lượng tăng, giới hạn nhà cung cấp và một alert chưa đủ nhạy.

**Mitigated không đồng nghĩa nguyên nhân đã được sửa.** Đưa traffic về phiên bản cũ có thể dừng lỗi, nhưng nếu chính sách retries chung vẫn sai thì rủi ro còn đó.

**Closed ticket không đồng nghĩa rủi ro đã giảm.** Một action chỉ thật sự có giá trị khi tác động được chứng minh hoặc khi phần rủi ro tồn đọng được chấp nhận minh bạch.

## 3. Ba mục đích của incident review

### 3.1. Hiểu điều gì đã xảy ra

Dựng một mô tả chung, có bằng chứng: người dùng gặp vấn đề gì, các service và dependencies nào liên quan, hệ thống chuyển trạng thái ra sao, khi nào sự cố bắt đầu và kết thúc.

### 3.2. Hiểu vì sao hệ thống cho phép điều đó xảy ra

Đi xa hơn câu trả lời "do bản deploy mới". Cần hỏi vì sao một thay đổi có thể đi qua test, deployment và monitoring mà tạo hậu quả rộng; vì sao retries làm tăng tải; vì sao một lỗi dependency dẫn tới lỗi dây chuyền; vì sao phát hiện muộn.

### 3.3. Thay đổi khả năng phản ứng trong tương lai

Tạo ít hành động nhưng có tác động lớn: tăng khả năng ngăn ngừa, giảm blast radius, phát hiện sớm, khôi phục nhanh hoặc giúp đội ứng phó có đầy đủ dữ liệu. Sau đó theo dõi đến khi có bằng chứng.

Một postmortem dài 20 trang nhưng không có hành động khả thi thường kém hữu ích hơn một tài liệu ngắn, chuẩn xác với ba cải tiến có owner và tiêu chí xác minh.

## 4. Văn hóa không đổ lỗi (blameless)

Mục đích của incident review là cải thiện hệ thống, không phải tìm một người để quy trách nhiệm cá nhân. Trong điều kiện thực tế, con người ra quyết định dựa trên thông tin, áp lực thời gian, công cụ và quy trình đang có.

Ví dụ câu hỏi kém hiệu quả:

- "Tại sao kỹ sư A lại deploy sai?"
- "Ai quên xem dashboard?"
- "Ai phải chịu trách nhiệm vì service không hoạt động?"

Các câu hỏi nên dùng:

- "Tại thời điểm quyết định deploy, những tín hiệu nào đang hiển thị?"
- "Pipeline cho phép thay đổi này vì guardrail nào còn thiếu?"
- "Thông tin gì có thể giúp người trực phát hiện sớm hơn?"
- "Điều kiện nào khiến một thao tác hợp lý lúc đó tạo hậu quả lớn?"
- "Làm sao thiết kế hệ thống để lỗi tương tự khó xảy ra hoặc ít tác động hơn?"

Blameless **không có nghĩa không có trách nhiệm thực hiện hành động**. Mỗi follow-up cần một người chịu trách nhiệm (DRI) và quyết định rõ ràng. Trách nhiệm ở đây hướng tới cải tiến; không dùng postmortem làm hồ sơ kỷ luật.

Cần giữ dữ kiện kiểm chứng được, phân biệt facts với hypotheses và không viết lại câu chuyện bằng kiến thức chỉ xuất hiện sau sự cố.

## 5. Khi nào cần tổ chức incident review?

Không phải mọi alert nhỏ đều cần một cuộc họp lớn. Đặt tiêu chí dựa trên tác động/rủi ro, ví dụ:

- SLO quan trọng bị vi phạm hoặc error budget bị tiêu đáng kể.
- Người dùng không thể thực hiện nghiệp vụ trọng yếu.
- Có nguy cơ mất, sai hoặc lộ dữ liệu.
- Có sự cố an toàn, bảo mật, compliance hoặc tài chính.
- Thời gian phục hồi kéo dài hơn mục tiêu.
- Sự cố lặp lại với cùng failure mode.
- Một near miss có thể gây hậu quả lớn nếu điều kiện hơi khác.
- Một lỗi phức tạp liên quan nhiều service hoặc bên thứ ba cần học chung.
- Sự cố đã gây thay đổi đáng kể tới quy trình phát hành và vận hành.

Có thể dùng nhiều mức độ:

| Mức | Ví dụ | Hình thức đánh giá |
|---|---|---|
| Nghiêm trọng | Checkout ngừng hoạt động rộng, mất dữ liệu | Postmortem chính thức, đa nhóm |
| Trung bình | Một vùng hoặc cohort lỗi, phục hồi được | Review theo template |
| Nhỏ | Sự cố ngắn, tác động hạn chế | Review ngắn hoặc gộp theo xu hướng |
| Near miss | Guardrail bắt được lỗi trước khi người dùng bị ảnh hưởng | Đánh giá điều gì đã bảo vệ và điểm còn yếu |

Mức phân loại cụ thể do tổ chức quy định. Đừng tạo động lực để giảm cấp incident chỉ nhằm né cuộc họp hoặc tránh ghi nhận error budget.

## 6. Quy trình từ phát hiện tới xác minh cải tiến

Một vòng đời dễ quản lý:

~~~text
Phát hiện và xác nhận tác động
            |
            v
Tuyên bố incident, xác định severity
            |
            v
Ứng phó và giảm tác động
            |
            v
Khôi phục, xác nhận người dùng phục hồi
            |
            v
Thu thập bằng chứng, chốt timeline
            |
            v
Incident review không đổ lỗi
            |
            v
Tạo hành động có owner và tiêu chí thành công
            |
            v
Ưu tiên, triển khai, kiểm chứng
            |
            v
Theo dõi hiệu quả/recurrence
            |
            +----> Cập nhật runbook, SLO, kiến trúc, training
~~~

Không cần đợi tất cả câu hỏi về nguyên nhân được giải đáp mới phục hồi service. Trong incident, ưu tiên giảm tác động; phân tích sâu có thể diễn ra sau khi hệ thống ổn định và bằng chứng quan trọng đã được lưu.

## 7. Các vai trò trong quá trình xử lý và đánh giá

Một incident có thể có các vai trò, tùy quy mô team:

- **Incident Commander (IC):** điều phối ứng phó, thống nhất ưu tiên, quyết định escalation, bảo đảm có người chịu trách nhiệm từng luồng.
- **Technical Lead/Operations Lead:** dẫn điều tra kỹ thuật, triển khai mitigation/rollback và kiểm tra tính an toàn.
- **Communications Lead:** cập nhật nội bộ và khách hàng theo nhịp đã thống nhất.
- **Scribe/Timeline Owner:** ghi mốc, hành động, bằng chứng, giả thuyết và kết quả.
- **Service Owner:** cung cấp ngữ cảnh hệ thống, kiểm chứng và sở hữu hành động thuộc dịch vụ.
- **Review Facilitator:** điều hành hậu kiểm, giúp phân biệt bằng chứng với suy đoán, tránh quy lỗi cá nhân.
- **Action DRI:** một người chịu trách nhiệm đưa một hành động tới trạng thái đã kiểm chứng.

Không phải incident nào cũng cần bảy người khác nhau. Với team nhỏ, một người có thể làm nhiều vai trò, nhưng nên hạn chế để người đang sửa lỗi phải đồng thời chịu toàn bộ giao tiếp và ghi timeline khi sự cố nghiêm trọng.

Sự cố liên quan khách hàng, bảo mật hoặc nghĩa vụ pháp lý phải phối hợp với nhóm chức năng phù hợp; tài liệu kỹ thuật không tự thay thế quy trình thông báo bắt buộc.

## 8. Chuẩn bị bằng chứng trước buổi review

Bản đánh giá tốt dựa trên nhiều nguồn:

| Nguồn | Có thể xác nhận | Cảnh báo khi diễn giải |
|---|---|---|
| Metrics/SLIs | Tốc độ lỗi, latency, traffic, error budget | Phân biệt missing data và 0 |
| Distributed traces | Đường đi request, retries, dependency, critical path | Sampling và missing spans |
| Structured logs | Error classes, timestamps, correlation IDs | Log volume đổi theo version |
| Deploy events | Image/config/flag/schema đã thay đổi lúc nào | Deploy started khác traffic shifted |
| Change audit | Ai/cái gì thay policy, flag, infra | Không mặc định thay đổi gần nhất là nguyên nhân |
| Kubernetes events | Pod restart, readiness, scheduling | Event retention có thể ngắn |
| Database metrics | Pool wait, locks, query latency, saturation | Một DB span dài chưa chắc SQL chậm |
| Broker metrics | Lag, backlog, retries, DLQ | Queue delay khác processing delay |
| External provider status | 429, quota, outage, region | Thời điểm provider báo có thể trễ |
| Customer support | Hành trình người dùng bị lỗi và phạm vi | Báo cáo đến muộn hoặc không đại diện |
| Chat/incident notes | Quyết định và hành động ứng phó | Ký ức người tham gia có thể sai |

Cần lưu reference tới dashboard snapshot, trace IDs, deployment records, changelog, commit và các log được phép lưu. Không tạo một kho tài liệu chứa mật khẩu, token, dữ liệu thẻ hoặc PII chỉ để có postmortem chi tiết.

### 8.1. Bằng chứng cần được bảo toàn

Một số metrics có retention ngắn hoặc sampling; log có thể rotate; ephemeral pods biến mất; trạng thái rollout bị ghi đè. Người ghi timeline nên lưu các snapshot/links quan trọng theo quy định lưu giữ dữ liệu và quyền truy cập, tránh dựa vào trí nhớ sau vài ngày.

### 8.2. Nêu rõ điều chưa biết

Ví dụ:

~~~text
FACT: 14:12 error rate checkout tăng lên 12%.
FACT: Payment CLIENT spans xuất hiện ba attempts.
HYPOTHESIS: Retry amplification vượt quota provider.
UNKNOWN: Tác động của cache miss trong 4 phút đầu vì thiếu metric.
EVIDENCE NEEDED: Provider 429 by minute và retry attempts per request.
~~~

Cách phân loại này giúp review không biến một giả thuyết chưa kiểm chứng thành sự thật.

## 9. Dựng timeline theo thời gian tuyệt đối

Một timeline tốt ghi rõ ngày, timezone, nguồn và loại sự kiện. Dưới đây là tình huống minh họa, không phải dữ liệu hệ thống thực:

| Thời điểm (ICT, UTC+7) | Sự kiện | Bằng chứng |
|---|---|---|
| 14:00 | Deploy Checkout v2.4.1 bắt đầu | CI/CD deployment event |
| 14:05 | Canary 5% nhận traffic | Gateway traffic split |
| 14:10 | Canary tăng lên 50% | Rollout controller |
| 14:12 | Checkout errors bắt đầu tăng | Request error metric |
| 14:14 | Provider 429 tăng mạnh | Provider response metrics |
| 14:18 | Alert SLO burn rate kích hoạt | Alert rule |
| 14:21 | On-call xác nhận incident | Incident channel |
| 14:25 | Tạm dừng rollout | Rollout event |
| 14:29 | Đưa canary traffic về 0 | Gateway config |
| 14:33 | Request error rate giảm | Metrics theo version |
| 14:37 | Checkout business success phục hồi | Business SLI |
| 15:05 | Xác nhận backlog đã giảm | Queue/dashboard |
| 15:20 | Kết thúc incident, chuyển sang giám sát | Incident record |

Không trộn thời điểm **phát sinh** với thời điểm **phát hiện**. Ví dụ lỗi bắt đầu 14:12, alert lúc 14:18, on-call xác nhận 14:21, mitigation thực tế áp dụng lúc 14:29 và người dùng phục hồi lúc 14:37.

Một số bài học có thể đến từ khoảng cách giữa các mốc:

- Vì sao detection trễ 6 phút?
- Vì sao từ alert đến xác nhận 3 phút?
- Vì sao từ xác nhận đến traffic rollback mất 8 phút?
- Vì sao business success phục hồi chậm hơn traffic shift?
- Có hàng đợi, connection cũ hoặc lỗi dữ liệu còn kéo dài không?

Timeline nên ghi thêm mức chắc chắn nếu dữ liệu lệch đồng hồ giữa các host. Dùng timestamp gốc UTC khi có thể, rồi hiển thị theo một timezone thống nhất.

## 10. Định lượng tác động đối với người dùng

Tác động không nên chỉ viết "Checkout bị lỗi khoảng 25 phút". Cần hỏi **ai bị ảnh hưởng, lỗi gì, ở đâu, bao lâu và hậu quả nghiệp vụ thế nào**.

Các chiều tác động có thể gồm:

- Bắt đầu/kết thúc tác động người dùng (không chỉ mốc incident open/close).
- Số request thất bại hoặc chậm hơn deadline.
- Số người dùng/tenant/session duy nhất bị ảnh hưởng, khi đo hợp lệ.
- Region, API route, phương thức thanh toán, loại client hoặc cohort.
- Tỷ lệ checkout/payment/order thành công.
- Số giao dịch trùng, thiếu hoặc cần đối soát.
- Số event bị trễ hoặc bỏ vào DLQ.
- SLA/SLO và error budget bị tiêu.
- Support tickets và ảnh hưởng vận hành.
- Mức mất doanh thu nếu được phân tích bằng dữ liệu có cơ sở.
- Tính đúng đắn, privacy, security hoặc compliance nếu liên quan.

Không suy ra số người dùng bị ảnh hưởng chỉ bằng số request lỗi: một người có thể retry nhiều lần. Nếu không có cách deduplicate đúng, ghi rõ "9.000 failed requests" chứ không gọi đó là "9.000 khách hàng".

### 10.1. Technical impact và business impact

Một API trả 200 không đảm bảo người dùng thành công. Ví dụ:

~~~text
HTTP 2xx giữ ở 99,9%
Checkout completion giảm từ 98% còn 90%
Payment authorized nhưng Order chưa được tạo tăng mạnh
~~~

Nếu chỉ đo 5xx, sự cố nghiệp vụ có thể bị bỏ sót. Review cần dùng business events, reconciliation và data consistency để đánh giá.

### 10.2. Near miss cũng có giá trị

Một rollout canary tự dừng nhờ guardrail trước khi ảnh hưởng khách hàng có thể là thành công của cơ chế phòng vệ. Review nên phân tích điều gì đã hoạt động tốt, còn chỗ nào thiếu và khả năng cơ chế này chịu được tình huống tương tự ở quy mô khác hay không.

## 11. Kết nối tác động với SLI, SLO và error budget

### 11.1. SLI và SLO

**SLI** là chỉ số chất lượng đo được, ví dụ tỷ lệ request checkout hợp lệ hoàn tất đúng và dưới hai giây.

**SLO** là mục tiêu cho SLI trong một cửa sổ, ví dụ 99,9% request checkout đáp ứng tiêu chí trong 30 ngày.

**Error budget** cho phép một mức không đạt mục tiêu được xác định, ví dụ nếu SLO 99,9% thì ngân sách lỗi là 0,1% tổng số request hợp lệ trong cùng cửa sổ.

Ví dụ minh họa:

~~~text
SLO:                     99,9% good requests
Window:                  30 ngày
Eligible requests:       20.000.000
Error budget:            0,1% × 20.000.000 = 20.000 bad requests
Incident bad requests:    9.000
Phần ngân sách đã tiêu:   9.000 / 20.000 = 45%
~~~

Nếu trước incident đã tiêu 6.000 bad requests, tổng 15.000 tương đương 75% ngân sách của cửa sổ. Các con số ở đây là ví dụ, không phải dữ liệu thực.

Tỷ lệ request lỗi phải tuân theo cùng SLI definition, cùng cửa sổ và đúng tập eligible traffic. Không lấy tổng 5xx của một route bất kỳ rồi so trực tiếp với error budget được định nghĩa trên nhiều journey khác nhau.

### 11.2. SLO dựa trên request khác SLO dựa trên thời gian

Một SLO availability tính theo phút hoặc theo cửa sổ đo có error budget khác SLO request-based. Không tự quy đổi 0,1% số request thành cùng số phút downtime trừ khi giả định lưu lượng/phương pháp đo cho phép.

Với SLO 99,9% liên tục theo phút trong 30 ngày, tỷ lệ thời gian tương ứng là khoảng 43,2 phút, nhưng cách tính thực tế còn phụ thuộc định nghĩa "good minute" và cửa sổ. Mỗi tổ chức phải công bố mô hình đo.

### 11.3. Burn rate

**Error budget burn rate** mô tả tốc độ tiêu ngân sách so với tốc độ trung bình cho phép. Nếu burn rate cao kéo dài, một cảnh báo multi-window có thể giúp phát hiện sớm hơn so với chỉ xem tổng lỗi tháng.

Review cần hỏi:

- Alert kích hoạt lúc nào so với thời điểm SLI bắt đầu xấu?
- Có cảnh báo quá nhiễu hoặc báo muộn vì aggregation window?
- Chỉ báo có phân loại đúng journey/region/version không?
- Có bỏ lọt business correctness vì chỉ theo HTTP status?
- Người trực có nhìn thấy burn rate và tác động hay chỉ một giá trị CPU cao?

Không dùng một ngưỡng burn rate cố định cho mọi hệ thống khi SLO và mức độ rủi ro khác nhau.

## 12. Các mốc thời gian ứng phó và cách định nghĩa

Các chỉ số thường gặp:

- **Time to detect:** từ khi tác động bắt đầu đến lúc tín hiệu được phát hiện.
- **Time to acknowledge:** từ lúc alert/page đến lúc người chịu trách nhiệm xác nhận.
- **Time to mitigate:** từ mốc được chọn (ví dụ incident start hoặc declare) tới khi tác động giảm đến mức chấp nhận được.
- **Time to restore/recover:** tới khi service và business SLI phục hồi theo tiêu chí.
- **Time to resolution:** tới khi incident được đóng theo quy trình, có thể sau khi hệ thống đã hồi phục.
- **Time to learn/verify:** tới khi các hành động quan trọng đã được xác nhận có hiệu quả.

Các chữ viết tắt như MTTD, MTTA, MTTR đôi khi được tổ chức định nghĩa khác nhau, đặc biệt MTTR có thể là mean time to repair, restore hoặc resolve. **Luôn nêu định nghĩa và điểm bắt đầu/kết thúc**, không so số liệu của hai team dùng định nghĩa khác.

Tính trung bình thời gian phục hồi một cách máy móc có thể che những sự cố cực dài. Nên xem thêm phân bố, mức độ nghiêm trọng và các giai đoạn chậm nhất.

## 13. Sử dụng traces, logs và metrics để hiểu cơ chế lỗi

Một ví dụ trace:

~~~text
POST /checkout                Checkout v2.4.1       4.200 ms
  inventory.reserve          Inventory v1.9.0        200 ms
  payment.authorize          Payment v3.2.5        3.500 ms
    provider attempt 1       429                    250 ms
    retry.wait                                     500 ms
    provider attempt 2       429                    250 ms
    retry.wait                                   1.000 ms
    provider attempt 3       timeout              1.500 ms
  order.persist              không chạy
~~~

Câu hỏi cần trả lời:

- Vì sao Payment retry 429? Đây có phải lỗi retryable theo contract không?
- Retry có exponential backoff/jitter và tổng retry budget không?
- Upstream cũng retry một RPC Payment đã retry nội bộ không?
- Có một shared provider quota hay rate limit không?
- API Gateway/Checkout có deadline rõ để dừng retry không?
- Lỗi phát sinh trên bản mới hay cả stable?
- Hành vi trước deploy khác gì về attempts và thời gian chờ?
- Có transaction hoặc connection pool bị giữ khi chờ retry không?

Trace là nguồn xem một đường đi cụ thể; metrics mới giúp đo tỷ lệ toàn hệ thống. Nếu sampling giữ nhiều trace lỗi hơn trace thành công, không đếm trace để ước lượng error rate.

Logs cung cấp error class, response code, correlation ID và quyết định fallback. Deployment marker cung cấp thay đổi runtime. Cần tổng hợp cả ba trước khi xác nhận giả thuyết.

## 14. Từ "root cause" đến mô hình nhiều yếu tố

Một cách giải thích yếu:

> Root cause: Developer quên cấu hình retry đúng.

Cách giải thích có cơ sở hệ thống hơn:

~~~text
TRIGGER
  Checkout rollout thay timeout và bật đường thanh toán mới
        |
        v
MECHANISM
  Client retry 429 + Payment retry ở tầng downstream
        |
        v
AMPLIFICATION
  Nhiều attempts cho một checkout, provider quota bị tiêu nhanh
        |
        v
USER IMPACT
  Checkout timeout / payment authorizations thất bại
        |
        +-- Phát hiện muộn do chỉ alert theo HTTP 5xx
        +-- Canary tăng 5% -> 50% khi chưa đủ business samples
        +-- Rollback chậm do thiếu thao tác traffic shift một bước
        +-- Dữ liệu in-flight cần đối soát sau phục hồi
~~~

Trong mô hình này có:

- **Sự kiện kích hoạt:** thay đổi trong rollout.
- **Cơ chế trực tiếp:** retry amplification vượt khả năng provider.
- **Điều kiện góp phần:** policy nhiều tầng thiếu ngân sách, quota chung.
- **Điểm yếu phát hiện:** alert không bắt được business success sớm.
- **Điểm yếu ứng phó:** rollback chưa được chuẩn hóa.
- **Hậu quả kéo dài:** queue và giao dịch cần reconciliation.

Không nhất thiết phải chọn đúng một "root cause" duy nhất. Với hệ thống phức tạp, một tập các điều kiện góp phần cho phép tạo các hành động cải thiện tại nhiều lớp phòng vệ.

## 15. Kỹ thuật phân tích nguyên nhân

### 15.1. Five Whys: dùng như gợi ý, không ép thành một chuỗi

Ví dụ:

1. Vì sao checkout timeout? Payment request vượt deadline.
2. Vì sao Payment vượt deadline? Có retry nhiều lần và backoff.
3. Vì sao retry quá mức? Cả Checkout và Payment đều áp retry.
4. Vì sao cả hai đều retry? Không có policy end-to-end và retry budget thống nhất.
5. Vì sao policy chưa có? Không có tiêu chí resilience/contract test cho dependency quota.

Đây là một nhánh điều tra, không chứng minh rằng chỉ có một nguyên nhân. Có thể song song xem provider outage, load spike, quota và alerting.

### 15.2. Fault tree hoặc causal graph

Vẽ các điều kiện **và/hoặc** dẫn đến tác động. Ví dụ "Checkout lỗi" có thể xảy ra nếu Payment timeout và không có fallback, hoặc Order DB outage. Causal graph giúp không bỏ sót nhánh mà một chuỗi Five Whys đơn tuyến không thấy.

### 15.3. Counterfactual

Hỏi điều gì sẽ xảy ra **nếu một lớp phòng vệ khác tồn tại**:

- Nếu có max attempts/budget chung, provider 429 có còn khuếch đại không?
- Nếu canary dừng ở 5%, blast radius có giảm không?
- Nếu alert theo business completion, đội có phát hiện trước 14:18 không?
- Nếu rollback có runbook tự động, thời gian khôi phục có giảm không?

Đây là công cụ đánh giá đòn bẩy cải thiện, không phải khẳng định chắc chắn một lịch sử chưa xảy ra.

### 15.4. Phân biệt bằng chứng và giả thuyết

Mỗi kết luận nên có evidence link hoặc mốc dữ liệu hỗ trợ. Khi không đủ dữ liệu, ghi "likely" hoặc "unresolved", xác định đo lường còn thiếu và tác động của độ bất định lên quyết định.

## 16. Đánh giá cách phản ứng, không chỉ lỗi kỹ thuật

Một incident review nên xem từng giai đoạn:

| Giai đoạn | Câu hỏi quan trọng |
|---|---|
| Detection | Tín hiệu đầu tiên là gì? Vì sao alert có sớm/muộn? |
| Triage | Có xác định nhanh phạm vi, severity và owner không? |
| Diagnosis | Dashboard/trace/runbook có chỉ đúng nơi nghẽn không? |
| Mitigation | Có phương án giảm tác động an toàn và nhanh không? |
| Communication | Team/người dùng nhận cập nhật rõ ràng không? |
| Recovery | Đã xác nhận business SLI và side effects chưa? |
| Handoff | Có bỏ sót backlog, customer support hoặc reconciliation không? |
| Learning | Hành động cải thiện có người sở hữu và được xác minh không? |

Nên ghi cả những điều **đã hoạt động tốt**: ví dụ canary traffic split có thể chuyển về 0 nhanh; trace ID xuyên service giúp điều tra; đội hỗ trợ có cách liên hệ đúng. Giữ và nhân rộng các cơ chế hiệu quả cũng là cải thiện.

### 16.1. Alert fatigue

Nếu người trực nhận hàng trăm cảnh báo CPU không liên quan trước khi cảnh báo business success xuất hiện, vấn đề không chỉ là "cần chú ý hơn". Cần giảm alert noise, định tuyến theo actionable symptom và liên kết alert với runbook.

### 16.2. Quy trình thông tin

Một cập nhật incident hữu ích ghi: tác động hiện tại, phạm vi, mốc thời gian, hành động đang thực hiện, bước tiếp theo và mức độ chắc chắn. Tránh hứa giờ phục hồi khi chưa có cơ sở. Sau incident, ghi những chỗ thông tin chậm hoặc thiếu để cải thiện mà không cá nhân hóa lỗi.

## 17. Phân loại hành động cải thiện

Không phải mọi việc sau incident đều là "sửa bug". Một kế hoạch cân bằng nên xem các lớp:

### 17.1. Ngăn lỗi xảy ra (prevention)

- Thay đổi retry contract và idempotency.
- Thêm compatibility tests cho API/event/schema.
- Cấu hình safer defaults và giới hạn concurrency.
- Kiểm tra input/config trước khi rollout.
- Giảm coupling hoặc thiết kế bulkhead.

### 17.2. Phát hiện sớm (detection)

- Thêm SLI business completion.
- Tạo alert multi-window burn rate.
- Gắn version/deployment markers và trace context.
- Đo queue oldest age và dependency rate limits.
- Bổ sung synthetic transaction có kiểm soát.

### 17.3. Giới hạn tác động (containment)

- Canary với guardrails và pause tự động theo policy.
- Rate limiting, circuit breaker, backpressure.
- Retry budget và load shedding.
- Phân vùng tài nguyên/tenant hoặc region.
- Fallback an toàn theo hợp đồng nghiệp vụ.

### 17.4. Khôi phục nhanh (recovery)

- Runbook chuyển traffic và rollback.
- Feature flag kill switch có kiểm thử.
- Restore/reconciliation scripts có kiểm soát.
- Cơ chế replay queue/idempotent consumer.
- Diễn tập chuyển vùng hoặc phục hồi dependency.

### 17.5. Tăng khả năng học (learning)

- Mẫu incident timeline rõ ràng.
- Dashboard service dependency và owner.
- Kiểm thử resilience/chaos có giới hạn.
- Hướng dẫn on-call và chia sẻ failure modes.
- Định kỳ xem lại các action quá hạn và sự cố lặp.

Không nhất thiết có ít nhất một action ở mọi nhóm. Chọn hành động theo nguyên nhân và rủi ro thực, tránh tạo checklist đẹp nhưng không mang lại hiệu quả.

## 18. Chọn hành động dựa trên rủi ro và đòn bẩy

Một action tốt là thay đổi **hệ thống hoặc cách làm** để giảm xác suất, phạm vi hoặc thời gian ảnh hưởng. Ưu tiên theo:

- Mức nghiêm trọng của failure mode (người dùng, dữ liệu, tài chính).
- Xác suất tái diễn và tần suất đã quan sát.
- Khả năng phát hiện trước khi tác động lớn.
- Số service/tenant/region có thể bị ảnh hưởng.
- Mức giảm rủi ro dự kiến của hành động.
- Chi phí triển khai và chi phí vận hành về sau.
- Độ phức tạp, rủi ro khi triển khai chính hành động.
- Sự phụ thuộc vào team khác hoặc vendor.
- Thời gian còn có thể chấp nhận rủi ro.

Có thể dùng ma trận định tính:

| Mức | Ví dụ | Hành động |
|---|---|---|
| P0/Critical | Nguy cơ mất tiền/dữ liệu hoặc vi phạm an toàn | Giảm tác động ngay, ưu tiên cao nhất |
| P1/High | Lỗi SLO nghiêm trọng có khả năng lặp | Owner và deadline gần, escalation |
| P2/Medium | Tăng rủi ro hoặc làm khôi phục chậm | Lên kế hoạch trong chu kỳ phù hợp |
| P3/Low | Tối ưu phụ trợ, ít ảnh hưởng | Backlog có lý do và kỳ xem lại |

Định nghĩa P0–P3 tùy tổ chức; đây chỉ là mẫu. Không chấm điểm tất cả follow-up theo "độ dễ" để chỉ làm các việc nhỏ, trong khi điểm yếu nền tảng còn nguyên.

## 19. Hành động tốt phải cụ thể và kiểm chứng được

Một action yếu:

> Tăng monitoring cho Payment Service.

Một action tốt hơn:

> Thêm metric số retry attempts trên mỗi checkout, tỷ lệ provider HTTP 429 theo version và business completion SLI; cấu hình alert khi burn rate vượt ngưỡng đã thống nhất; test bằng mô phỏng provider 429; owner nhóm Payment; hoàn thành trước kỳ rollout tiếp theo.

Một action khác:

> Áp dụng retry budget tối đa 2 attempts cho đường Payment trong phạm vi overall deadline, xác minh bằng integration test khi provider trả 429 hoặc timeout; bảo đảm idempotency key giữ nguyên giữa attempts và tải provider không tăng quá giới hạn kiểm thử.

Tiêu chí chất lượng của action:

1. **Một kết quả rõ ràng:** điều gì phải thay đổi.
2. **Một DRI cụ thể:** ai chịu trách nhiệm đến cùng.
3. **Deadline hoặc mốc ràng buộc:** khi nào hoàn thành.
4. **Ưu tiên và lý do:** failure mode/rủi ro nào được giảm.
5. **Tiêu chí nghiệm thu:** đo hoặc thử gì để biết thành công.
6. **Evidence:** link PR, dashboard, test report, runbook hoặc exercise.
7. **Dependency:** những nhóm/hệ thống cần phối hợp.
8. **Phương án khi trễ:** escalation, mitigation tạm và quyết định risk acceptance.

"Đã merge PR" chỉ chứng minh code được hợp nhất, chưa chứng minh thay đổi đã deploy hoặc guardrail hoạt động ở production.

## 20. Action register: dữ liệu tối thiểu cần quản lý

Có thể dùng issue tracker, ticket system hoặc bảng theo dõi; công cụ không quan trọng bằng cấu trúc dữ liệu và cách vận hành.

| Trường | Mục đích |
|---|---|
| Action ID | Định danh để tham chiếu và tránh trùng |
| Incident ID | Sự cố nguồn hoặc các sự cố liên quan |
| Title | Hành động ngắn, rõ, có động từ |
| Failure mode | Rủi ro/hậu quả cần giảm |
| Category | Prevent/Detect/Contain/Recover/Learn |
| Priority | Mức quan trọng đã thống nhất |
| DRI | Một người chịu trách nhiệm |
| Supporting teams | Nhóm hỗ trợ và dependencies |
| Due date | Hạn hoàn thành hoặc mốc rollout |
| Status | Trạng thái quy định rõ |
| Success criteria | Điều kiện chứng minh có hiệu quả |
| Evidence links | PR, test, dashboard, runbook, deploy |
| Risk remaining | Rủi ro còn lại nếu chưa đạt |
| Verified by/date | Người và thời điểm xác minh |
| Notes | Quyết định, blockers, thay đổi scope |

Tránh tạo một action khổng lồ "Cải thiện độ tin cậy của Checkout" với 15 việc không cùng kết quả; nên chia thành deliverable độc lập nhưng liên kết vào cùng mục tiêu.

Đồng thời không tạo quá nhiều ticket vụn chỉ để tăng số lượng việc đã đóng. Follow-up nên đại diện cho thay đổi có ý nghĩa vận hành.

## 21. Ví dụ action register sau incident

Giả sử sự cố INC-2026-042 là Checkout giảm business success do retry amplification trong một lần canary. Các dòng minh họa:

| ID | Hành động | Nhóm | DRI | Ưu tiên | Hạn | Tiêu chí nghiệm thu | Trạng thái |
|---|---|---|---|---|---|---|---|
| ACT-101 | Giới hạn retry Payment trong overall deadline | Prevention | Payment lead | P1 | 20/11 | Test 429/timeout không vượt attempt budget | Planned |
| ACT-102 | Thêm business SLI cho checkout completion | Detection | Observability lead | P1 | 18/11 | Dashboard và alert bắt được test incident | In progress |
| ACT-103 | Chặn canary tăng khi guardrail chưa đủ mẫu | Containment | Platform lead | P1 | 25/11 | Rollout controller pause trong simulation | Planned |
| ACT-104 | Runbook rollback traffic một bước | Recovery | SRE lead | P2 | 30/11 | Game day chuyển traffic, đo time-to-mitigate | Planned |
| ACT-105 | Reconcile các giao dịch thời gian incident | Recovery | Finance/Order lead | P0 | 13/11 | Không còn payment thiếu/đơn trùng chưa xử lý | In progress |

Các ngày là ví dụ cho một kịch bản, không phải deadline đang thực tế được giao. Nếu action có ảnh hưởng dữ liệu/tài chính, cần xác định nguồn sự thật, quyền truy cập và quy trình phê duyệt theo tổ chức.

Mỗi action nên liên kết tới incident, evidence và dashboard phù hợp. DRI không cần tự làm mọi công việc, nhưng chịu trách nhiệm cập nhật tình trạng và đưa ra bằng chứng trước khi đóng.

## 22. Vòng đời của một hành động

Một quy trình trạng thái minh bạch:

~~~text
PROPOSED
   |
   v
TRIAGED
   |
   +--> REJECTED / ACCEPTED_RISK (có lý do và approver)
   |
   v
PLANNED
   |
   v
IN_PROGRESS
   |
   +--> BLOCKED (có blocker, owner, next step)
   |
   v
IMPLEMENTED
   |
   v
VERIFICATION_PENDING
   |
   +--> FAILED_VERIFICATION --> IN_PROGRESS
   |
   v
VERIFIED
   |
   v
CLOSED
~~~

**IMPLEMENTED không phải VERIFIED.** Một giới hạn retry được merge vào main nhưng chưa deploy hoặc test trong điều kiện provider 429 thì chưa chứng minh giảm rủi ro.

**BLOCKED** cần lý do, ảnh hưởng tới deadline và bước tháo gỡ. Không cho ticket ở trạng thái blocked vô thời hạn mà không ai cập nhật.

**ACCEPTED_RISK** không phải cách đổi tên "bỏ qua". Phải nêu rủi ro, người phê duyệt có thẩm quyền, thời hạn xem lại và biện pháp tạm thời nếu có.

### 22.1. Thay đổi scope

Khi phát hiện giải pháp ban đầu không phù hợp, có thể điều chỉnh action nhưng phải lưu quyết định, lý do và tác động lên failure mode. Không đóng action cũ bằng một việc không tương đương chỉ để báo tiến độ.

## 23. Theo dõi hành động để không bị bỏ quên

Một hệ thống theo dõi nên có nhịp kiểm tra nhất quán:

- Trong buổi review: chốt danh sách, DRI, ưu tiên và deadline tạm.
- Sau review: service owners xác nhận khả năng thực hiện và dependencies.
- Định kỳ hàng tuần hoặc theo sprint: xem P0/P1, blockers, overdue và verification.
- Trước đợt release có rủi ro: kiểm tra các action nào là điều kiện bắt buộc.
- Hàng tháng/quý: xem recurrence, tuổi action chưa đóng và rủi ro chấp nhận.
- Khi hoàn tất: xác minh bằng evidence và ghi trạng thái VERIFIED/CLOSED.

Nhịp cụ thể phụ thuộc mức độ nghiêm trọng; không cần họp mỗi ngày chỉ để đọc lại ticket không đổi.

### 23.1. Dashboard cho action tracking

Các chiều hữu ích:

| Chỉ số | Câu hỏi |
|---|---|
| Open P0/P1 actions | Có rủi ro nghiêm trọng chưa xử lý? |
| Overdue actions | Những action nào đã trễ và vì sao? |
| Age by priority | Công việc quan trọng có tồn đọng lâu không? |
| Verified / implemented ratio | Có bao nhiêu việc được kiểm chứng, không chỉ merge? |
| Blocked by dependency | Nhóm/hệ thống nào đang cản việc? |
| Repeated failure modes | Có incident tái diễn cùng kiểu lỗi? |
| Risk accepted | Rủi ro nào đang được chấp nhận có chủ đích? |
| Time to verification | Bao lâu từ review tới khi kiểm chứng hiệu quả? |

Tránh dùng số ticket đóng làm thước đo duy nhất: một đội đóng 100 ticket nhỏ không nhất thiết giảm rủi ro nhiều hơn đội sửa một lỗi kiến trúc nghiêm trọng.

### 23.2. Escalation

Khi P1 quá hạn, cần rõ người điều phối/escalation, hành động tạm thời và quyết định có tiếp tục release hay không. Không tự động coi mọi quá hạn là lý do chặn production, nhưng nếu failure mode có thể gây mất dữ liệu và chưa có biện pháp giảm thiểu, phải đánh giá release risk rõ ràng.

## 24. Kiểm chứng hiệu quả hành động

Hành động nên có một phép kiểm tra độc lập với việc "người phát triển nói đã xong".

### 24.1. Kiểm thử có thể lặp lại

Ví dụ action giới hạn retry:

~~~text
Given: Provider trả 429 trong 60 giây
When: 100 checkout requests hợp lệ tới Payment
Then:
  - Không request nào vượt max attempts theo policy
  - Overall deadline được tuân thủ
  - Không payment duplicate do retry
  - Provider call volume nằm trong giới hạn đã thiết kế
  - Checkout trả lỗi/fallback có nghĩa theo contract
~~~

Có thể kiểm chứng trong integration/load test và một canary có giám sát. Không cần hoặc không nên gây outage production để chứng minh test.

### 24.2. Đánh giá dashboard/alert bằng giả lập

Nếu thêm alert business success, không chỉ nhìn rule tồn tại. Dùng dữ liệu test/synthetic phù hợp để xác nhận rule nhận tín hiệu đúng, alert routing đúng người và link runbook mở được. Kiểm tra cả false positives và missing data.

### 24.3. Game day hoặc resilience exercise

Ví dụ: giả lập một provider chậm, một queue backlog tăng hoặc một service không sẵn sàng trong môi trường kiểm soát. Đo detection time, response path và kết quả khôi phục. Các diễn tập có ảnh hưởng production cần phê duyệt, giới hạn blast radius, stop conditions và người chịu trách nhiệm; không tiến hành chaos experiment vô kiểm soát.

### 24.4. Quan sát dài hạn

Một lần test pass không bảo đảm lỗi sẽ không bao giờ lặp. Theo dõi incident recurrence, provider 429/retry rate, burn rate, latency và những signal liên quan sau khi action deploy. Đặt mốc review định kỳ và điều chỉnh giả thuyết nếu dữ liệu mới mâu thuẫn.

## 25. Xác nhận phục hồi nghiệp vụ sau incident

Trong nhiều hệ thống, hồi phục API không có nghĩa hậu quả đã xử lý hết. Với checkout/payment, có thể có:

- Payment được authorize nhưng không tạo Order.
- Order đã tạo nhưng event không tới fulfillment.
- Request timeout khiến client retry và tạo duplicate.
- Message tồn tại trong DLQ.
- Cache chứa dữ liệu không còn đúng.
- Batch job đang chạy phải được resume hoặc replay.
- Khách hàng đã bỏ thao tác và cần được hỗ trợ.

Sau mitigation, tạo workstream reconciliation với tiêu chí hoàn tất riêng. Không tuyên bố toàn bộ hậu quả đã khắc phục chỉ vì HTTP 5xx giảm. Nếu cần giữ incident mở cho đến khi hoàn tất remediation theo policy, phải định nghĩa rõ giữa **service restored** và **customer impact fully remediated**.

### 25.1. Idempotency và reconciliation

Khi xử lý lại các giao dịch, dùng idempotency keys, nguồn dữ liệu có thẩm quyền và audit trail. Script sửa dữ liệu phải có dry-run, phân quyền, kiểm soát thay đổi và kế hoạch rollback/compensation nếu phù hợp. Không tự chạy bulk update production từ postmortem mà thiếu quy trình an toàn.

## 26. Mẫu Markdown postmortem có thể tái sử dụng

~~~markdown
# Incident Review: [INC-ID] [Tiêu đề ngắn]

## Thông tin chung
- Severity:
- Incident commander:
- Services / regions:
- Bắt đầu tác động:
- Phát hiện:
- Khôi phục service:
- Kết thúc business remediation:
- SLI/SLO liên quan:
- Trạng thái kết luận (confirmed / likely / unresolved):

## Tóm tắt
Mô tả 3-5 câu: điều gì xảy ra, người dùng bị ảnh hưởng ra sao,
cách giảm tác động và trạng thái sau phục hồi.

## Tác động
- Số lượng request bị lỗi hoặc chậm:
- Người dùng/tenant bị ảnh hưởng (nếu đo được):
- Business outcomes:
- Error budget đã tiêu:
- Data integrity / compliance impact:
- Giới hạn và sai số của phép đo:

## Timeline (một timezone thống nhất)
| Time | Event | Evidence |
|---|---|---|
| ... | ... | ... |

## Kết quả điều tra
### Những sự kiện đã được xác nhận
### Cơ chế trực tiếp và yếu tố góp phần
### Điều chưa biết / bằng chứng còn thiếu
### Vì sao các lớp phòng vệ không ngăn được ảnh hưởng

## Phản ứng và phục hồi
- Detection:
- Triage:
- Mitigation:
- Recovery:
- Điều đã làm tốt:
- Điểm cần cải thiện:

## Hành động theo dõi
| ID | Action | Failure mode | DRI | Priority | Due | Verify |
|---|---|---|---|---|---|---|

## Tài liệu tham chiếu
- Dashboard:
- Logs / trace IDs:
- Deployment / change records:
- Runbook:
- Related incidents:

## Quyết định về rủi ro còn lại
- Rủi ro:
- Biện pháp tạm:
- Người phê duyệt:
- Ngày xem lại:
~~~

Template cần được điều chỉnh theo severity và chính sách dữ liệu của tổ chức; không cần mọi incident nhỏ có toàn bộ trường. Quan trọng là facts, impact, factors, actions và bằng chứng phải rõ.

## 27. Ví dụ bài học: Retry amplification trong Microservices

Giả sử mô hình:

~~~text
Client
   |
   v
API Gateway
   |
   v
Checkout Service ----> Payment Service ----> Payment Provider
       |                      |
       +--- retries           +--- retries
~~~

### 27.1. Điều đã xảy ra

Checkout v2.4.1 được đưa vào canary với cấu hình timeout mới. Khi provider bắt đầu trả một phần HTTP 429, Payment retry nội bộ; Checkout cũng retry toàn bộ lời gọi Payment. Số attempts tăng theo nhiều tầng, tiếp tục tiêu quota và làm latency/timeout tăng.

Canary được tăng traffic từ 5% lên 50% trước khi business completion SLI đủ mẫu. Alert kỹ thuật dựa trên HTTP 5xx kích hoạt muộn hơn thời điểm tỷ lệ checkout hoàn tất giảm. Team giảm traffic canary về 0; service phục hồi, nhưng còn một số yêu cầu cần đối soát.

### 27.2. Các yếu tố góp phần

- Không có retry budget end-to-end.
- Quy ước retry với HTTP 429 không nhất quán.
- Không đo attempts trên mỗi nghiệp vụ.
- Không có guardrail business success cho canary.
- Pipeline cho tăng stage theo thời gian, không đủ kiểm chứng.
- Runbook rollback chưa ghi cách xác minh provider quota/backlog.
- Reconciliation cho giao dịch in-flight chưa tự động.

### 27.3. Các action ưu tiên

1. Giới hạn retry và deadline, tích hợp idempotency.
2. Thêm metric retry attempts và business completion.
3. Chặn rollout tăng stage khi guardrail/traffic sample chưa đạt tiêu chí.
4. Chuẩn hóa runbook rollback và xác minh phục hồi.
5. Xử lý các giao dịch tồn đọng có bằng chứng hoàn tất.
6. Tạo resilience test có provider 429 và mạng chậm.

### 27.4. Cần xác minh gì?

Không chỉ test "Payment trả 200". Phải đo số provider calls trên mỗi checkout, tỷ lệ duplicate, timeout, latency, business success và behavior khi provider 429 kéo dài. Cần đảm bảo request bị fail nhanh, đúng semantics và không gây thêm traffic vô hạn.

## 28. Theo dõi những sự cố lặp lại

Nếu incident tương tự lặp trong các service khác nhau, nguyên nhân có thể nằm ở một thư viện hoặc chính sách platform dùng chung.

Ví dụ:

~~~text
INC-041: Checkout retry storm -> Payment provider
INC-057: Notification retry storm -> Email provider
INC-066: Inventory retry storm -> Warehouse API
~~~

Dù service khác nhau, failure mode giống nhau: retry layering thiếu budget, không tôn trọng rate limit. Hành động hiệu quả hơn có thể là **retry client library chuẩn**, default policies, deadline propagation, test suite chung và dashboard theo service; không chỉ sửa từng service.

Gắn nhãn recurring failure modes (retry storm, DB pool exhaustion, cache stampede, schema incompatibility, queue poison, missing alert, rollback delay) để nhận diện pattern. Tránh dùng category quá rộng đến mức không hành động được.

### 28.1. Incident recurrence rate

Có thể theo dõi số lần tái diễn trong một cửa sổ theo nhóm failure mode. Nhưng cần chú ý thay đổi cách phân loại incident hoặc độ nhạy alert có thể làm số incident tăng dù reliability thực cải thiện. Kết hợp recurring incidents với user impact, SLO budget và time-to-recovery.

### 28.2. Learning across teams

Một bài học về timeout và retry của Payment có thể áp dụng cho Checkout, Inventory, Search và batch workers. Tài liệu review nên có tóm tắt failure mode mang tính tái sử dụng, hành động platform-level và người chịu trách nhiệm phân phối kiến thức.

## 29. Quản lý giao tiếp và việc công bố postmortem

Không phải mọi phần của postmortem đều nên công khai. Chọn mức chia sẻ theo hợp đồng, bảo mật, privacy và pháp lý:

- **Nội bộ kỹ thuật:** dữ liệu chi tiết đủ điều tra, hạn chế secret/PII.
- **Nhóm quản lý và chủ sản phẩm:** user impact, risk, SLO, quyết định và tiến độ.
- **Khách hàng:** phạm vi tác động, thời gian, cách giảm ảnh hưởng, những hành động có thể công bố.
- **Đối tác/nhà cung cấp:** các phần cần phối hợp, không chia sẻ quá mức dữ liệu nội bộ.

Nội dung giao tiếp nên chính xác và nêu độ bất định. Nếu nguyên nhân chưa được xác minh, nói rõ đang điều tra; không đưa một giả thuyết thành kết luận chắc chắn chỉ để có bản báo cáo sớm.

Postmortem là tài liệu học tập, nhưng vẫn phải có access control, retention, redaction và cách tham chiếu trace/log phù hợp. Không sao chép raw headers chứa token hay giao dịch cá nhân vào tài liệu.

## 30. Kỹ thuật tự động hóa action tracking

Một tích hợp cơ bản giữa incident management, issue tracker và observability có thể hỗ trợ:

~~~text
Incident được đánh dấu Restored
        |
        v
Tạo bản nháp review + link timeline/dashboards
        |
        v
Facilitator chốt factors và actions
        |
        v
Mỗi action tạo ticket với DRI, due date và verify criteria
        |
        v
Dashboard tổng hợp theo priority/status/age
        |
        v
Nhắc quá hạn và escalation phù hợp
        |
        v
Khi implement -> yêu cầu evidence để verify
        |
        v
Đóng action và cập nhật incident record
~~~

Không nên tự tạo hàng chục ticket từ mỗi bullet của postmortem mà không có triage; điều đó dẫn đến backlog và làm mất tập trung.

### 30.1. Một schema dữ liệu mẫu

~~~json
{
  "action_id": "ACT-101",
  "incident_id": "INC-2026-042",
  "title": "Bound Payment retries within one end-to-end deadline",
  "failure_mode": "retry-amplification",
  "category": "prevention",
  "priority": "P1",
  "owner": "payment-team-dri",
  "due_date": "2026-11-20",
  "status": "verification_pending",
  "success_criteria": [
    "No more than configured attempts per checkout",
    "429 simulation does not amplify provider requests",
    "Idempotency retained across retries"
  ],
  "evidence": [
    "integration-test-report",
    "canary-metric-dashboard"
  ]
}
~~~

Các ID, ngày và owner là ví dụ mô hình, không phải dữ liệu thật. Hệ thống tracker nên kiểm soát trường bắt buộc và phân quyền cập nhật. Khi status đổi tới VERIFIED, yêu cầu evidence đủ để người khác kiểm tra; không chỉ nhập một chuỗi "done".

### 30.2. Thông báo theo sự kiện có ý nghĩa

Thay vì gửi reminder liên tục, nên thông báo khi:

- Action P0/P1 tới hạn hoặc quá hạn.
- Blocker tồn tại quá lâu mà chưa có bước xử lý.
- Verification fail và action quay lại IN_PROGRESS.
- Một incident mới có failure mode giống action chưa hoàn tất.
- Một release phụ thuộc action đang chuẩn bị được triển khai.

Đặt owner và người nhận thông báo rõ; tránh alert fatigue chuyển từ incident system sang ticket system.

## 31. Cách đo hiệu quả của chương trình học từ sự cố

Không nên tối ưu "số postmortem được viết" hoặc "số action đóng" một cách đơn lẻ. Các thước đo hữu ích hơn:

| Chỉ số | Điều cần hiểu |
|---|---|
| User-impacting incidents | Số sự cố thực sự tác động người dùng có giảm không? |
| Error budget consumed | Mức độ ảnh hưởng tới SLO qua các chu kỳ |
| Time to detect/mitigate | Phát hiện và giảm tác động có nhanh hơn không? |
| Repeat incidents | Các failure mode đã sửa có tái diễn không? |
| Open high-risk actions | Có rủi ro nghiêm trọng chưa giảm? |
| Verification completion | Việc đã làm có được kiểm chứng không? |
| Action age/overdue | Bài học có bị mắc lại trong backlog không? |
| Rollback/recovery time | Khả năng phục hồi có cải thiện không? |
| Alert precision | Alert có actionable và ít nhiễu hơn không? |
| Correctness/consistency | Dữ liệu và hành vi nghiệp vụ có tốt hơn không? |

Cần giải thích tác động của cách phân loại sự cố, mức độ quan sát, traffic và thay đổi sản phẩm khi so sánh qua thời gian. Sự tăng số incident nhỏ được phát hiện có thể do detection tốt hơn, không nhất thiết hệ thống trở nên kém tin cậy.

Một chương trình tốt cân bằng **phát hiện sớm, giảm tác động và sửa tận gốc**, thay vì chỉ cố giảm con số incident ticket.

## 32. Bài tập tình huống

Giả sử trong 30 ngày, Checkout có SLO 99,9% trên 20 triệu request hợp lệ. Một incident làm 9.000 request không đáp ứng mục tiêu và tạo 250 giao dịch cần đối soát. Theo timeline:

~~~text
14:02  Config retry mới được áp dụng
14:07  Provider 429 tăng
14:11  Checkout completion giảm
14:17  Alert HTTP 5xx kích hoạt
14:22  On-call xác nhận incident
14:30  Bắt đầu rollback flag
14:35  HTTP metrics phục hồi
14:42  Business completion phục hồi
16:00  250 giao dịch đã được phân loại để reconciliation
~~~

**Câu hỏi 1 — Error budget:** Incident đã dùng bao nhiêu phần ngân sách lỗi theo request-based SLO đã nêu?

Đáp án: ngân sách = 0,1% × 20.000.000 = 20.000 bad requests. Incident dùng 9.000, tương đương **45%** ngân sách của kỳ nếu tất cả 9.000 request thuộc SLI.

**Câu hỏi 2 — Detection:** Nếu lấy thời điểm tác động business bắt đầu 14:11 và alert xuất hiện 14:17, time to detect là bao lâu?

Đáp án: **6 phút** theo định nghĩa đã chọn. Nếu đội lấy thời điểm provider 429 tăng từ 14:07 thì kết quả khác; phải nêu phạm vi đo.

**Câu hỏi 3 — Recovery:** Tại sao không kết thúc đánh giá tác động ở 14:35?

Đáp án: HTTP metrics đã phục hồi nhưng business completion chỉ phục hồi ở 14:42, còn 250 giao dịch cần đối soát. User impact và remediation có thể kéo dài sau khi API trông khỏe.

**Câu hỏi 4 — Factors:** Có thể chốt "root cause = config retry" chỉ từ timeline không?

Đáp án: chưa đủ. Cần biết cơ chế retry, attempts per request, provider quota, feature/config changes khác và các phản chứng. Timeline chỉ cho thấy mối liên hệ thời gian.

**Câu hỏi 5 — Action:** Viết một follow-up cho detection.

Gợi ý: thêm business completion SLI và alert burn rate phù hợp, có test dữ liệu giả lập completion giảm, owner Observability, deadline, dashboard và bằng chứng alert routing.

**Câu hỏi 6 — Action:** Viết một follow-up cho prevention.

Gợi ý: thống nhất overall retry budget và idempotency giữa Checkout/Payment; test 429/timeout ở nhiều tầng; xác minh số provider requests không bị khuếch đại.

**Câu hỏi 7 — Verification:** Tại sao merge PR giới hạn retries chưa đủ để đóng ticket?

Đáp án: code chưa chắc đã deploy đúng môi trường, chạy với config thực hoặc qua được test failure mode. Cần bằng chứng integration/canary test và metric sau triển khai.

**Câu hỏi 8 — Prioritization:** Nên xử lý giao dịch chưa đối soát hay tinh chỉnh mẫu postmortem trước?

Đáp án: việc có khả năng ảnh hưởng tiền/dữ liệu khách hàng cần ưu tiên và quy trình an toàn hơn công việc cải thiện tài liệu mang tính phụ trợ.

## 33. Checklist dành cho người điều hành review

### Trước buổi đánh giá

- [ ] Incident đã có ID, severity, owner và tình trạng phục hồi.
- [ ] Đã xác định user/business impact và SLO bị ảnh hưởng.
- [ ] Có timeline với timezone thống nhất và nguồn bằng chứng.
- [ ] Có dashboard, traces, logs, deployment/flag/config events liên quan.
- [ ] Facts và hypotheses đã được đánh dấu khác nhau.
- [ ] Có dữ liệu về detection, mitigation, recovery và side effects.
- [ ] Mời đúng service owners, người xử lý, support/đối tác nếu cần.
- [ ] Đã loại bỏ secret/PII khỏi tài liệu chia sẻ.
- [ ] Facilitator nhắc mục tiêu học hỏi, không quy trách nhiệm cá nhân.

### Trong buổi đánh giá

- [ ] Mô tả sự cố theo góc nhìn người dùng.
- [ ] Xác minh các mốc quan trọng, ghi rõ điều chưa chắc chắn.
- [ ] Phân tích điều kiện kích hoạt, góp phần và các lớp phòng vệ.
- [ ] Xem cả điều làm tốt và cơ hội cải thiện ứng phó.
- [ ] Liên kết nguyên nhân với những action có thể giảm rủi ro.
- [ ] Ưu tiên theo severity, recurrence, blast radius và chi phí.
- [ ] Mỗi action có DRI, deadline, success criteria và evidence.
- [ ] Xác định những rủi ro không xử lý ngay, có owner/approver.
- [ ] Phân biệt service restored với remediation của khách hàng/dữ liệu.

### Sau buổi đánh giá

- [ ] Postmortem được lưu và chia sẻ đúng quyền.
- [ ] Actions được tạo trong tracker, liên kết incident.
- [ ] DRI xác nhận trách nhiệm và kế hoạch.
- [ ] Có nhịp xem overdue, blockers và verification.
- [ ] P0/P1 được escalation khi trễ hoặc thay đổi rủi ro.
- [ ] Hành động được triển khai rồi kiểm chứng bằng test/metrics phù hợp.
- [ ] Runbook, alerts, dashboards và tài liệu sở hữu service được cập nhật.
- [ ] Business side effects được giải quyết hoặc theo dõi riêng.
- [ ] Các incident lặp lại được nối với failure mode và action chung.
- [ ] Đã ghi nhận phần rủi ro còn lại và thời điểm review tiếp theo.

## 34. Những sai lầm phổ biến

1. **Chỉ tìm người làm sai:** làm giảm chia sẻ dữ kiện và che các điểm yếu hệ thống.
2. **Chỉ ghi một "root cause" đơn giản:** bỏ qua các yếu tố làm tăng blast radius và thời gian phục hồi.
3. **Thiếu timeline:** tranh luận dựa trên trí nhớ và hindsight.
4. **Không tách fact/hypothesis:** kết luận nguyên nhân khi chưa đủ chứng cứ.
5. **Đếm request lỗi thành số người dùng lỗi:** sai định nghĩa impact.
6. **Chỉ đo HTTP 5xx:** bỏ qua business completion, data corruption hoặc queue lag.
7. **Không xem SLO/error budget:** khó ưu tiên rủi ro giữa các sự cố.
8. **Đóng incident khi API hồi phục nhưng dữ liệu chưa đối soát:** bỏ sót hậu quả nghiệp vụ.
9. **Action mơ hồ như "tăng monitoring":** không có điều kiện xác minh.
10. **Action không có DRI hoặc deadline:** không ai chịu trách nhiệm kết thúc.
11. **Chỉ đóng theo PR merge:** chưa chứng minh code deploy và failure mode được xử lý.
12. **Tạo quá nhiều ticket nhỏ:** backlog mất trọng tâm.
13. **Không xem sự cố lặp lại:** sửa nhiều service cùng một lỗi platform mà không tổng hợp.
14. **Không làm rõ risk acceptance:** dùng "won't fix" như cách né trách nhiệm.
15. **Không đo effectiveness:** không biết incident program có giúp giảm rủi ro.
16. **Không ghi cách rollback/mitigate:** sự cố lần sau vẫn chậm khôi phục.
17. **Không kiểm soát quyền chia sẻ dữ liệu:** postmortem vô tình chứa secret hoặc dữ liệu khách hàng.
18. **Xem postmortem là thủ tục sau sự cố:** không đưa bài học thành thay đổi hệ thống.

## 35. Ghi nhớ

Incident review là công cụ học hỏi từ hành vi thực của hệ thống dưới điều kiện khó, không phải phiên tòa tìm lỗi cá nhân. Một đánh giá tốt bắt đầu bằng **tác động tới người dùng**, xây dựng **timeline có bằng chứng**, nhận diện **cơ chế và những yếu tố góp phần**, rồi đánh giá vì sao các lớp phát hiện, giới hạn và khôi phục chưa đủ.

SLO và error budget giúp chuyển tác động kỹ thuật thành rủi ro có thể so sánh, nhưng phải dùng đúng SLI definition và cửa sổ đo. Metrics cho biết quy mô, traces mô tả đường đi, logs cung cấp sự kiện chi tiết, change timeline chỉ ra các thay đổi gần thời điểm phát sinh.

Một bài học chỉ có giá trị lâu dài khi chuyển thành **hành động rõ ràng, có một DRI, mức ưu tiên, hạn, tiêu chí thành công và bằng chứng kiểm chứng**. Implemented không đồng nghĩa verified; service restored không đồng nghĩa hậu quả nghiệp vụ đã được khắc phục hoàn toàn.

**Nguyên tắc cốt lõi: không chỉ hỏi "Vì sao sự cố này xảy ra?", mà còn hỏi "Hệ thống sẽ phát hiện sớm hơn, giới hạn tác động tốt hơn và phục hồi an toàn hơn thế nào vào lần tới?" — rồi theo dõi cho đến khi có bằng chứng rằng khả năng đó đã thật sự cải thiện.**