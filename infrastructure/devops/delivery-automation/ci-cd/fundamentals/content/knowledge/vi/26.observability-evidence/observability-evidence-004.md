# Phân biệt thông báo lỗi cần hành động với cập nhật trạng thái thông thường

Một pipeline CI/CD có thể phát ra hàng trăm sự kiện trong một lần chạy: job bắt đầu, dependency được tải, test hoàn tất, artifact được tạo, image được đẩy lên registry, deployment bắt đầu và health check kết thúc. Nếu mọi sự kiện đều gửi thành cảnh báo, người nhận sẽ bị ngập thông tin và dần bỏ qua cả những tín hiệu quan trọng. Ngược lại, nếu lỗi ảnh hưởng tới release hoặc production chỉ được ghi như một dòng trạng thái thông thường, nhóm có thể bỏ lỡ thời điểm cần can thiệp.

Vì vậy, cần phân biệt rõ **alert (thông báo cần hành động)** với **status notification (cập nhật trạng thái)**. Alert báo một điều kiện có ý nghĩa vận hành đang cần người hoặc hệ thống phản ứng. Status notification cho biết tiến độ, kết quả hoặc sự kiện đã xảy ra để người nhận theo dõi, nhưng không nhất thiết yêu cầu can thiệp.

Sự khác biệt không nằm ở việc thông báo có chữ ERROR hay màu đỏ. Nó nằm ở tác động, ngưỡng, thời hạn phản ứng, người chịu trách nhiệm và hành động tiếp theo. Một job thất bại nhưng đã được retry thành công có thể chỉ cần lưu vào lịch sử run; một deployment đang chạy đúng tiến độ chỉ cần cập nhật trạng thái; nhưng một release bị chặn vì vi phạm policy hoặc một dịch vụ production vượt ngưỡng lỗi cần được chuyển thành alert có owner và hướng xử lý.

Bài viết trình bày cách thiết kế hai loại tín hiệu trong CI/CD: phân loại theo tác động, đặt điều kiện alert, chọn kênh và người nhận, gom nhóm và chống trùng, quản lý escalation và silence, viết thông điệp có thể hành động, đồng thời giữ bằng chứng để điều tra và cải thiện hệ thống.

## 1. Alert và status notification phục vụ hai mục đích khác nhau

**Alert** là tín hiệu cho biết một điều kiện cần được đánh giá hoặc xử lý trong một khoảng thời gian xác định. Alert thường có mức độ nghiêm trọng, owner, ngữ cảnh, runbook và điều kiện kết thúc.

**Status notification** là thông tin về trạng thái hoặc sự kiện: pipeline đã bắt đầu, job đã hoàn tất, artifact đã được tạo, deployment đang chờ approval hoặc test đã pass. Người nhận có thể muốn biết thông tin này, nhưng không nhất thiết phải làm gì ngay.

| Tiêu chí | Alert cần hành động | Status notification |
|---|---|---|
| Mục tiêu | Kích hoạt phản ứng | Cung cấp thông tin tiến độ/kết quả |
| Điều kiện phát | Có tác động hoặc rủi ro vượt ngưỡng | Có sự kiện hoặc chuyển trạng thái |
| Người nhận | Owner/on-call/nhóm chịu trách nhiệm | Người theo dõi, tác giả, kênh dự án |
| Thời hạn | Có urgency hoặc response target | Thường không có deadline xử lý |
| Nội dung | Tác động, phạm vi, mức độ, hành động | Trạng thái, thời điểm, liên kết |
| Vòng đời | Open, acknowledged, resolved | Ghi nhận sự kiện, thường không cần acknowledge |
| Kênh | Pager, incident channel, ticket/alert console | Dashboard, feed, chat channel, email digest |
| Ví dụ | Production error budget burn nhanh | Build của branch feature đã hoàn tất |

Không nên biến mọi notification thành alert. Nếu một thông báo không cần người nhận phản ứng, nó thường nên ở dashboard, activity feed hoặc kênh cập nhật. Cũng không nên hạ một alert thành status chỉ để giảm số lượng tin nhắn.

## 2. Quyết định dựa trên tác động và hành động, không dựa vào nhãn log

Một dòng log có level ERROR không tự động là alert. Ví dụ, client có thể ghi ERROR khi gọi một endpoint phụ thất bại nhưng đã fallback thành công; lỗi đó không ảnh hưởng người dùng và không cần đánh thức on-call.

Ngược lại, một điều kiện không xuất hiện dưới dạng log ERROR vẫn có thể cần alert: queue backlog tăng liên tục, deployment không tiến triển, certificate sắp hết hạn hoặc error budget bị tiêu thụ quá nhanh.

Hãy đánh giá mỗi tín hiệu bằng bốn câu hỏi:

1. **Tác động là gì?** Có ảnh hưởng người dùng, dữ liệu, bảo mật, release hoặc SLO không?
2. **Có cần hành động không?** Có người hoặc hệ thống nào cần làm gì để giảm tác động?
3. **Khi nào cần hành động?** Nếu chờ tới lần review tiếp theo, thiệt hại có tăng không?
4. **Ai chịu trách nhiệm?** Có owner hoặc on-call rõ ràng để nhận tín hiệu không?

Nếu không xác định được hành động, owner hoặc thời hạn, tín hiệu đó có thể chưa đủ điều kiện để trở thành alert. Hãy bổ sung ngữ cảnh hoặc chuyển nó thành notification/metric để theo dõi.

## 3. Phân loại theo mức độ nghiêm trọng

Severity biểu thị mức tác động và tốc độ phản ứng cần thiết. Tên mức có thể khác nhau giữa tổ chức, nhưng cần có định nghĩa nhất quán.

| Mức | Ý nghĩa | Ví dụ CI/CD | Phản ứng |
|---|---|---|---|
| Critical / P1 | Dịch vụ chính ngừng hoạt động, mất dữ liệu hoặc rủi ro bảo mật nghiêm trọng | Release gây outage production diện rộng | On-call phản ứng ngay theo incident process |
| High / P2 | Một chức năng quan trọng suy giảm hoặc release bị chặn sát deadline | Error rate tăng vượt SLO sau deploy | Owner xử lý khẩn trong response window |
| Medium / P3 | Vấn đề có phạm vi giới hạn, có workaround | Một môi trường staging không ổn định | Nhóm phụ trách xử lý trong giờ làm việc |
| Low / P4 | Vấn đề nhỏ, chưa gây tác động đáng kể | Một job phụ thất bại nhưng pipeline chính vẫn đạt | Tạo ticket hoặc đưa vào backlog |

Severity không nên được suy ra chỉ từ loại lỗi. Một lỗi database có thể là P1 nếu làm production ngừng phục vụ, nhưng chỉ là P3 nếu xảy ra ở một môi trường test riêng và tự phục hồi.

Cần phân biệt **severity** (mức tác động) với **priority** (thứ tự xử lý theo bối cảnh). Một lỗi có severity cao nhưng đã được mitigation có thể giảm priority tạm thời; lịch sử severity và quyết định mitigation vẫn cần được lưu.

## 4. Phân biệt sự kiện, trạng thái, triệu chứng và alert

Một hệ thống quan sát tốt giữ riêng các khái niệm:

- **Event:** một việc đã xảy ra, chẳng hạn job bắt đầu hoặc deployment được tạo.
- **State:** trạng thái hiện tại, chẳng hạn RUNNING, WAITING_APPROVAL hoặc FAILED.
- **Metric:** phép đo theo thời gian, chẳng hạn error rate hoặc queue depth.
- **Log:** chi tiết có cấu trúc hoặc văn bản về hoạt động.
- **Trace:** đường đi của một request qua nhiều thành phần.
- **Symptom:** biểu hiện quan sát được, chẳng hạn latency tăng.
- **Root cause:** nguyên nhân gốc, có thể chưa biết khi alert được phát.
- **Alert:** điều kiện cần hành động được tạo từ event, state hoặc telemetry.

Không nên đợi biết root cause mới phát alert. Nếu tác động đã rõ và cần phản ứng, alert có thể được phát với nguyên nhân ở trạng thái "đang điều tra". Ngược lại, một exception riêng lẻ không nhất thiết là alert nếu chưa có tác động hoặc hành động cần thiết.

Ví dụ: một lần HTTP 503 trong quá trình retry có thể chỉ là event. Nếu tỷ lệ 503 duy trì trên ngưỡng và người dùng không thể hoàn tất giao dịch, đó là symptom đủ để tạo alert. Root cause có thể là database, network hoặc deployment; alert không nên đoán nguyên nhân khi chưa có bằng chứng.

## 5. Thiết kế điều kiện alert có ý nghĩa

Một alert rule nên biểu diễn điều kiện có ý nghĩa vận hành, không chỉ tìm một chuỗi trong log.

Một rule tốt thường có:

- Metric hoặc trạng thái đầu vào rõ ràng.
- Điều kiện và ngưỡng có cơ sở.
- Khoảng thời gian duy trì để tránh dao động ngắn.
- Severity.
- Owner/team.
- Runbook hoặc liên kết điều tra.
- Labels để phân nhóm.
- Annotations giải thích tác động và hành động.

Ví dụ alert cho tỷ lệ request lỗi cao:

~~~yaml
groups:
  - name: service-availability
    rules:
      - alert: HighRequestErrorRate
        expr: |
          (
            sum(rate(http_requests_total{status=~"5.."}[5m]))
            /
            clamp_min(sum(rate(http_requests_total[5m])), 0.001)
          ) > 0.05
          and sum(rate(http_requests_total[5m])) > 1
        for: 10m
        labels:
          severity: high
          team: platform
          service: order-api
        annotations:
          summary: "Tỷ lệ lỗi 5xx của order-api vượt ngưỡng"
          description: "Tỷ lệ 5xx trên 5% liên tục trong 10 phút."
          runbook_url: "https://runbooks.example.com/order-api/high-error-rate"
~~~

Ngưỡng 5% và thời gian 10 phút chỉ là ví dụ. Hệ thống thật cần dựa trên SLO, traffic baseline và mức độ ảnh hưởng. Nếu traffic thấp, tỷ lệ phần trăm có thể dao động mạnh; có thể cần điều kiện số request tối thiểu hoặc dùng burn rate của error budget.

## 6. Dùng SLI, SLO và error budget để quyết định alert

Alert nên phản ánh mức độ người dùng đang bị ảnh hưởng. Các chỉ số kỹ thuật riêng lẻ có thể không đại diện tốt cho trải nghiệm.

- **SLI:** chỉ số đo chất lượng dịch vụ, ví dụ tỷ lệ request thành công hoặc latency p95.
- **SLO:** mục tiêu chất lượng trong một cửa sổ thời gian, ví dụ 99,9% request thành công trong 30 ngày.
- **Error budget:** phần lỗi cho phép theo SLO trong cửa sổ đó.

Ví dụ, CPU 90% trong một phút chưa chắc cần pager nếu latency và error rate vẫn tốt. Ngược lại, error budget bị tiêu thụ nhanh có thể cần alert ngay cả khi CPU bình thường.

### Multi-window burn-rate alert

Có thể kết hợp cửa sổ ngắn và dài để phát hiện cả sự cố nghiêm trọng lẫn suy giảm kéo dài:

- Cửa sổ ngắn cho biết mức tiêu thụ error budget hiện tại.
- Cửa sổ dài giúp xác nhận vấn đề không chỉ là một spike ngắn.
- Mức burn rate càng cao thì thời gian phản ứng càng ngắn.

Không nên sao chép ngưỡng burn rate từ hệ thống khác mà không xét SLO, độ dài cửa sổ và lượng traffic. Alert phải hướng tới hành động giảm tác động, chẳng hạn rollback, giảm traffic, tắt feature hoặc khôi phục dependency.

## 7. Khi nào lỗi trong pipeline chỉ là status?

Không phải mọi lần job thất bại đều cần alert khẩn.

| Tình huống | Cách biểu diễn thường phù hợp |
|---|---|
| Unit test fail trên pull request | Status check đỏ, thông báo cho tác giả và reviewer |
| Job tải dependency lỗi một lần rồi retry thành công | Event trong run history; không cần pager |
| Pipeline bị chặn vì thiếu approval | Status WAITING_APPROVAL và nhắc reviewer theo deadline |
| Build branch thử nghiệm thất bại | Status notification tới nhóm phát triển |
| Security gate chặn release production | Alert/ticket tới security và release owner theo policy |
| Deploy staging thất bại nhưng môi trường có thể tự tạo lại | Notification hoặc ticket theo mức tác động |
| Production health check fail sau deploy và user impact vượt ngưỡng | Alert tới on-call |
| Runner pool hết capacity khiến release quan trọng trễ deadline | Alert tới CI platform owner nếu cần can thiệp |
| Một test flaky được retry và pass | Lưu cả hai attempt; có thể tạo trend/ticket, không nhất thiết pager |
| Secret production bị phát hiện trong log | Alert bảo mật theo incident policy |

Status check của PR vẫn cần rõ ràng và dễ thấy, nhưng không nhất thiết phải đánh thức đội trực. Alert được dành cho điều kiện có tác động cần phản ứng theo thời hạn.

## 8. Cảnh báo cho trạng thái pipeline bị kẹt

Pipeline có thể không thất bại nhưng cũng không tiến triển: job chờ runner, chờ approval, chờ lock hoặc chờ artifact.

Nên phân biệt các trạng thái:

- **Queued:** đang chờ tài nguyên.
- **Running:** job đang thực thi.
- **Waiting approval:** chờ người có quyền phê duyệt.
- **Blocked:** thiếu dependency hoặc điều kiện.
- **Stalled:** không có tiến triển vượt quá thời hạn hợp lý.
- **Failed:** job kết thúc lỗi.
- **Cancelled:** bị hủy.
- **Succeeded:** hoàn tất.

Một job chờ approval trong 2 phút có thể là trạng thái bình thường; chờ 24 giờ khi sắp tới release deadline có thể cần escalation. Một runner queue tăng trong giờ cao điểm có thể là notification tới dashboard; nếu release train quan trọng bị trễ và queue không giảm, đó có thể là alert cho owner của runner pool.

Hãy dùng deadline theo loại công việc thay vì một ngưỡng chung cho tất cả job. Build lớn, deployment và manual approval có thời lượng kỳ vọng khác nhau.

## 9. Phân loại theo tác động của release

Thông báo CI/CD nên xét môi trường và mức quan trọng của thay đổi.

| Environment | Ví dụ sự kiện | Phản ứng thường phù hợp |
|---|---|---|
| Local/dev | Build hoặc test fail | Status cho developer |
| Pull request | Required check fail | Status check và notification cho tác giả |
| Staging | Deploy fail | Alert cho release owner nếu chặn kiểm thử hoặc deadline |
| Pre-production | Security gate fail | Alert/ticket cho security và release owner |
| Production | Post-deploy health check fail | Alert theo user impact/SLO |
| Production | Deployment hoàn tất, health tốt | Status notification |
| Production | Rollback hoàn tất và service phục hồi | Status update kèm evidence; incident chỉ resolve khi tiêu chí phục hồi đạt |

Không nên tự động hạ severity chỉ vì lỗi xảy ra ngoài production. Một secret bị lộ trong CI hoặc artifact bị giả mạo có thể là sự cố bảo mật nghiêm trọng dù chưa deploy.

## 10. Định tuyến thông báo tới đúng người

Alert không có owner thường trở thành tiếng ồn. Mỗi alert cần được định tuyến dựa trên service, environment, team hoặc loại tài nguyên.

Ví dụ:

- Service availability → service on-call.
- Runner capacity → CI platform team.
- Registry publishing → artifact platform owner.
- Security policy violation → security response team.
- Database migration lock → database owner và release owner.
- Approval chờ quá deadline → reviewer group hoặc release manager.

Không gửi mọi alert tới một kênh chung. Kênh chung có thể nhận bản sao để quan sát, nhưng phải có một nhóm chịu trách nhiệm chính.

### Ownership và escalation

Một policy nên xác định:

1. Primary owner nhận alert.
2. Thời gian acknowledge mục tiêu.
3. Người/nhóm thay thế nếu không phản hồi.
4. Điều kiện escalation.
5. Cách chuyển giao khi sự cố kéo dài.
6. Ai có quyền resolve hoặc đóng alert.

Nếu không có owner phù hợp, alert rule cần được sửa trước khi đưa vào production.

## 11. Chọn kênh theo urgency

Kênh truyền tải cần phù hợp mức độ và thời hạn phản ứng.

| Kênh | Phù hợp với | Hạn chế |
|---|---|---|
| Dashboard/activity feed | Theo dõi trạng thái và xu hướng | Người nhận phải chủ động mở |
| Pull request status/check | Kết quả kiểm tra gắn với commit | Chỉ người theo dõi PR thường thấy |
| Chat channel | Cập nhật nhóm, cảnh báo mức vừa | Dễ trôi trong luồng chat |
| Email | Báo cáo, digest, nhắc việc | Không phù hợp cho sự cố cần phản ứng tức thì |
| Ticket/issue | Công việc cần owner và theo dõi tiến độ | Không thay thế pager cho P1 |
| Pager/on-call alert | Sự cố cần phản ứng nhanh | Dùng quá mức gây alert fatigue |
| SMS/phone escalation | Trường hợp nghiêm trọng hoặc kênh chính lỗi | Chi phí và mức gián đoạn cao |

Có thể gửi một alert P1 tới pager và incident channel, đồng thời tạo ticket theo dõi. Một status build pass chỉ cần xuất hiện trên PR và activity feed.

## 12. Chống trùng bằng deduplication và grouping

Một sự cố có thể tạo ra hàng nghìn sự kiện: mỗi pod báo lỗi, mỗi request timeout, mỗi retry thất bại. Nếu gửi từng sự kiện riêng, người nhận khó nhìn thấy một vấn đề chung.

### Deduplication

Deduplication nhận diện các alert có cùng danh tính logic để không tạo nhiều bản giống nhau. Identity có thể dựa trên alert name và labels ổn định như service, environment, cluster hoặc deployment.

Không đưa timestamp, request ID hoặc pod ID biến động vào identity nếu mục tiêu là gom các bản sao của cùng một điều kiện. Các giá trị đó có thể nằm trong log/trace để điều tra.

### Grouping

Grouping gom các alert liên quan thành một thông báo. Ví dụ, 20 pod của order-api cùng lỗi có thể được nhóm thành một alert theo service/environment.

Grouping cần giữ đủ thông tin để xác định phạm vi. Không gom tất cả lỗi production thành một alert chung khiến người nhận không biết service nào đang gặp sự cố.

### Inhibition

Inhibition tạm ngăn alert cấp thấp khi một alert cấp cao hơn đã giải thích cùng sự cố. Ví dụ cluster mất kết nối có thể khiến nhiều alert từng service cùng nổ; alert cluster có thể inhibit các alert service phụ thuộc trong cùng cluster.

Inhibition không được làm mất bằng chứng. Các điều kiện bị inhibit vẫn nên được lưu và có thể xem trong hệ thống quan sát.

## 13. Debounce, for-duration và hysteresis

Một metric có thể dao động quanh ngưỡng. Nếu alert ngay khi vượt ngưỡng trong một lần scrape, hệ thống có thể phát và resolve liên tục.

Các kỹ thuật giảm dao động:

- **For-duration:** điều kiện phải duy trì trong một khoảng thời gian mới firing.
- **Debounce:** chờ tín hiệu ổn định trước khi phát.
- **Hysteresis:** ngưỡng resolve thấp hơn hoặc khác ngưỡng firing để tránh bật/tắt liên tục.
- **Minimum sample count:** chỉ đánh giá tỷ lệ khi có đủ số mẫu.
- **Cooldown:** giới hạn tần suất thông báo lặp, nhưng vẫn giữ alert active.

Ví dụ, firing khi error rate trên 5% trong 10 phút và resolve khi xuống dưới 2% liên tục 5 phút. Ngưỡng thực tế cần phù hợp SLO và độ nhạy mong muốn.

Không dùng cooldown để che một alert vẫn đang gây tác động. Cooldown chỉ điều chỉnh thông báo lặp; trạng thái alert và dữ liệu gốc vẫn phải được lưu.

## 14. Alert lifecycle: firing, acknowledged, resolved

Alert cần có vòng đời rõ ràng:

~~~text
Condition detected
       |
       v
     FIRING
       |
       v
  Routed to owner
       |
       v
  ACKNOWLEDGED
       |
       +------ Investigate / mitigate
       |                 |
       |                 v
       |              RESOLVED
       |
       +------ No response before deadline
                         |
                         v
                     ESCALATED
                         |
                         v
                      RESOLVED
~~~

- **Firing:** điều kiện alert đang đúng.
- **Acknowledged:** người nhận xác nhận đã tiếp nhận.
- **Investigating:** đang tìm nguyên nhân hoặc đánh giá tác động.
- **Mitigated:** tác động đã được giảm nhưng chưa chắc điều kiện gốc đã hết.
- **Resolved:** điều kiện alert không còn đúng và tiêu chí phục hồi đã được xác minh.
- **Escalated:** đã chuyển tới cấp xử lý tiếp theo do quá hạn hoặc mức tác động tăng.

Acknowledged không có nghĩa đã giải quyết. Mitigated cũng không đồng nghĩa resolved. Ví dụ rollback có thể giảm lỗi, nhưng cần xác minh health check và user journey trước khi đóng incident.

## 15. Silence và maintenance window

Silence dùng để tạm ngăn thông báo trong một phạm vi và thời gian xác định. Nó hữu ích khi đang bảo trì có kế hoạch hoặc đã có incident cấp cao hơn bao phủ cùng điều kiện.

Một silence cần:

- Match labels cụ thể.
- Có lý do.
- Có người tạo.
- Có thời điểm bắt đầu và hết hạn.
- Có ticket/change record liên quan.
- Không rộng hơn phạm vi cần thiết.

Không silence toàn bộ production chỉ vì đang deploy. Một maintenance window có thể bỏ qua một số alert đã biết, nhưng vẫn cần giữ alert bảo mật hoặc các điều kiện ngoài phạm vi bảo trì.

### Silence không xóa alert hoặc metric

Silence chỉ ảnh hưởng việc gửi notification theo rule của hệ thống. Metric, log, trace và trạng thái alert vẫn nên được lưu để audit và điều tra. Khi silence hết hạn, nếu điều kiện vẫn đúng, alert có thể được gửi lại theo chính sách.

## 16. Thiết kế nội dung alert có thể hành động

Một alert tốt giúp người nhận trả lời nhanh:

- Điều gì đang xảy ra?
- Ảnh hưởng tới ai hoặc tài nguyên nào?
- Mức độ và thời gian bắt đầu?
- Vì sao cần hành động bây giờ?
- Ai chịu trách nhiệm?
- Nên kiểm tra hoặc làm gì trước?
- Link tới runbook, dashboard và incident.

Ví dụ thông điệp tốt:

~~~text
[HIGH] order-api production error rate vượt SLO

Impact:
Tỷ lệ HTTP 5xx đạt 8.2% trong 10 phút; checkout bị ảnh hưởng.

Started:
2026-11-18 09:42 UTC

Owner:
Service On-call

Next action:
1. Mở dashboard error-rate và deployment timeline.
2. Kiểm tra release mới nhất.
3. Nếu lỗi bắt đầu sau deploy và rollback criteria đạt, thực hiện rollback theo runbook.

Links:
Dashboard: ...
Runbook: ...
Deployment: ...
Trace sample: ...
~~~

Thông điệp yếu:

~~~text
ERROR: deployment failed!!!
~~~

Thông điệp yếu thiếu service, environment, tác động, owner, thời gian và hành động. Người nhận phải tự tìm lại toàn bộ ngữ cảnh.

Không đưa secret, access token, nội dung payload nhạy cảm hoặc dữ liệu cá nhân vào alert. Dùng correlation ID và link tới hệ thống có kiểm soát quyền truy cập.

## 17. Status notification nên ngắn và không tạo áp lực giả

Status notification có thể gồm:

- Pipeline started.
- Build completed.
- Unit tests passed.
- Artifact published.
- Deployment waiting for approval.
- Deployment completed.
- Rollback completed.
- Scheduled maintenance started/ended.

Một status notification nên có run ID, commit SHA, branch hoặc release, trạng thái và link tới run. Không cần gửi toàn bộ log vào chat.

Ví dụ:

~~~text
[DEPLOYMENT] order-api production completed

Release: 2.8.1
Commit: a1b2c3d4
Artifact: sha256:...
Result: healthy
Duration: 6m 24s

Details: <deployment run link>
~~~

Không dùng từ "healthy" nếu chỉ có lệnh deploy trả thành công mà chưa chạy health check. Trạng thái phải phản ánh đúng mức bằng chứng hiện có.

## 18. Kết hợp logs, metrics, traces và deployment events

Alert cần dẫn người nhận tới bằng chứng liên quan. Một thông báo chỉ có thể hành động nếu người nhận có thể kiểm tra nhanh dữ liệu gốc.

- **Logs:** chi tiết lỗi, exception, context và operation ID.
- **Metrics:** xu hướng, tỷ lệ, số lượng, latency, queue depth và SLO.
- **Traces:** đường đi request qua các service và dependency.
- **Deployment events:** commit, artifact digest, environment, rollout và rollback.
- **CI job reports:** test results, scan findings, build metadata và runner details.

### Correlation ID

Mỗi pipeline run, deployment operation hoặc request nên có định danh để liên kết các nguồn dữ liệu. Ví dụ:

- pipeline_run_id
- job_id và attempt
- commit_sha
- artifact_digest
- deployment_id
- trace_id hoặc correlation_id
- environment
- service

Không dùng một ID chung cho mọi lần chạy. Các ID cần phân biệt pipeline run, attempt và deployment operation để điều tra đúng lần thực thi.

### Timeline

Khi có alert sau deploy, timeline nên cho biết:

1. Commit được merge.
2. Artifact được build và scan.
3. Approval được cấp.
4. Deployment bắt đầu.
5. Traffic chuyển sang version mới.
6. Error rate tăng.
7. Alert firing.
8. Rollback hoặc mitigation bắt đầu.
9. Health check phục hồi.
10. Alert resolved.

Timeline giúp liên hệ thay đổi với tác động mà không phải suy đoán từ một log đơn lẻ.

## 19. Phân biệt alert theo lỗi kỹ thuật và rủi ro release

Một pipeline có thể thất bại vì lỗi kỹ thuật, nhưng điều quan trọng là tác động tới khả năng phát hành.

| Tín hiệu | Phân loại gợi ý | Hành động |
|---|---|---|
| Một runner mất kết nối, job tự retry pass | Event/status | Theo dõi runner health |
| Nhiều runner cùng offline làm release train dừng | Alert cho CI platform owner | Khôi phục runner capacity |
| Required security scan phát hiện policy violation | Alert/ticket security | Điều tra finding, block release |
| Artifact registry từ chối publish do quota | Alert cho artifact platform nếu release bị chặn | Giải phóng quota hoặc sửa policy |
| Approval chờ gần hết deadline | Reminder/status escalation | Nhắc reviewer hoặc release owner |
| Production canary vượt error threshold | Alert cho service on-call | Pause rollout/rollback theo runbook |
| Test staging flaky một lần rồi pass | Status/evidence | Ghi attempt, theo dõi xu hướng |
| Provenance hoặc signature không hợp lệ | Alert security/release owner | Block promotion và điều tra |

Một release bị chặn có thể cần alert dù production chưa bị ảnh hưởng, vì có deadline hoặc rủi ro chuỗi cung ứng. Severity phải phản ánh tác động thực tế và chính sách của tổ chức.

## 20. Quản lý notification delivery và lỗi kênh gửi

Alert có thể được tạo đúng nhưng không tới người nhận do chat API lỗi, email delay, webhook hết hạn hoặc pager provider gián đoạn.

Hệ thống nên phân biệt:

- Alert condition created.
- Notification enqueued.
- Delivery attempted.
- Delivery accepted.
- Delivery failed.
- Acknowledgement received.

Một webhook HTTP 200 chỉ chứng minh endpoint đã phản hồi theo hợp đồng, không nhất thiết người trực đã đọc. Với alert quan trọng, cần acknowledgement và escalation theo chính sách.

### Retry gửi notification

Retry delivery có thể tạo tin nhắn trùng nếu provider đã nhận nhưng response bị mất. Dùng notification ID ổn định hoặc provider idempotency nếu hỗ trợ. Nếu không, grouping và deduplication ở receiver giúp giảm trùng.

Không retry vô hạn vào một kênh lỗi. Cần retry budget, fallback channel và alert riêng cho notification delivery failure nếu việc mất thông báo tạo rủi ro vận hành.

### Fallback channel

Ví dụ, nếu chat webhook không hoạt động, alert P1 vẫn phải đi qua pager hoặc kênh on-call độc lập. Không nên để mọi đường cảnh báo phụ thuộc vào cùng một dịch vụ chat.

## 21. Alert fatigue và cách giảm nhiễu

Alert fatigue xảy ra khi số lượng alert quá lớn, nhiều alert không cần hành động hoặc cùng một sự cố phát ra nhiều thông báo lặp. Người nhận dần bỏ qua, mute hoặc phản ứng chậm.

Cách giảm nhiễu:

- Chỉ alert khi có hành động rõ.
- Dùng SLO và user impact thay vì ngưỡng tài nguyên tùy tiện.
- Gom nhóm theo service/environment/incident.
- Deduplicate theo identity ổn định.
- Dùng for-duration, debounce và hysteresis.
- Inhibit alert con khi alert gốc đã giải thích sự cố.
- Tách notification tiến độ khỏi pager.
- Đặt owner và runbook.
- Review alert không được acknowledge hoặc thường xuyên resolve tự động.
- Loại bỏ alert không còn phù hợp với kiến trúc.

Không giảm nhiễu bằng cách tăng ngưỡng đến mức bỏ sót sự cố. Sau mỗi thay đổi, cần kiểm tra dữ liệu lịch sử và đánh giá false positive lẫn false negative.

## 22. Bảo mật và quyền truy cập trong thông báo

Alert và status notification thường được gửi qua hệ thống chat, email hoặc ticket có phạm vi người xem rộng. Không nên coi mọi kênh đều là nơi lưu dữ liệu nhạy cảm.

Không đưa vào nội dung:

- Secret, token, private key hoặc credential.
- Database connection string.
- Payload chứa dữ liệu cá nhân.
- Nội dung request/response nhạy cảm.
- URL có credential hoặc signed query parameter chưa được bảo vệ.
- Log đầy đủ có thể chứa dữ liệu bí mật.

Thay vào đó:

- Dùng resource ID, correlation ID và link có kiểm soát quyền.
- Redact dữ liệu trước khi gửi.
- Phân quyền dashboard/runbook.
- Giữ audit ai tạo, nhận, acknowledge, silence hoặc resolve alert.
- Đặt retention theo chính sách dữ liệu và điều tra.

Alert cần đủ ngữ cảnh để hành động nhưng không được mở rộng quyền truy cập dữ liệu ngoài ý muốn.

## 23. Kiểm thử alert rule và notification policy

Alert rule cũng là code vận hành và cần được kiểm thử.

### Kiểm thử logic rule

- Metric bình thường không tạo alert.
- Metric vượt ngưỡng trong thời gian ngắn không firing nếu có for-duration.
- Metric vượt ngưỡng đủ lâu tạo alert đúng severity.
- Metric phục hồi theo hysteresis thì resolve.
- Traffic thấp không tạo tỷ lệ lỗi giả do mẫu quá nhỏ.
- Labels đủ để route và grouping.
- Missing data được xử lý theo policy rõ ràng.

### Kiểm thử notification lifecycle

- Alert được route tới đúng owner.
- Duplicate được gom đúng.
- Inhibition không che mất alert gốc.
- Silence có scope và expiry đúng.
- Không acknowledge thì escalation hoạt động.
- Delivery failure kích hoạt fallback.
- Resolved notification chỉ phát khi điều kiện phục hồi đã xác minh.

### Kiểm thử CI/CD

Có thể dùng test environment hoặc dữ liệu giả lập để mô phỏng:

- Build/test failure.
- Runner pool unavailable.
- Registry quota exceeded.
- Security gate violation.
- Deployment rollout stalled.
- Post-deploy error rate tăng.
- Rollback thành công nhưng health check chưa phục hồi.
- Alert provider bị mất kết nối.

Không tạo sự cố thật trên production chỉ để kiểm thử rule. Dùng synthetic metrics, staging hoặc game day đã được phê duyệt.

## 24. Quy trình review và cải tiến alert

Alert cần được review định kỳ vì service, SLO, team ownership và dependency có thể thay đổi.

Trong review, hỏi:

- Alert này đã từng yêu cầu hành động thực tế chưa?
- Có owner/on-call đúng không?
- Thời gian acknowledge và resolve có phù hợp không?
- Có nhiều alert cùng biểu diễn một sự cố không?
- Có alert nào thường xuyên bị mute hoặc bỏ qua không?
- Có trường hợp user impact xảy ra nhưng alert không firing không?
- Ngưỡng có dựa trên SLO hoặc baseline không?
- Runbook còn đúng với kiến trúc hiện tại không?
- Kênh notification có hoạt động và có fallback không?
- Alert có chứa thông tin nhạy cảm không?

Sau incident, ghi lại alert nào hữu ích, alert nào thiếu hoặc quá nhiễu. Thay đổi rule nên có owner, lý do và kiểm thử hồi quy.

## 25. Anti-pattern thường gặp

| Anti-pattern | Hệ quả | Cách cải thiện |
|---|---|---|
| Mỗi log ERROR đều gửi pager | Alert fatigue | Phân loại theo impact và actionability |
| Mọi job fail đều là P1 | Mất ý nghĩa severity | Gắn severity với tác động và urgency |
| Chỉ gửi "deployment failed" | Người nhận thiếu ngữ cảnh | Thêm service, environment, run ID, impact và runbook |
| Gửi mọi status update vào on-call | Làm loãng tín hiệu quan trọng | Tách status feed khỏi alert channel |
| Không có owner | Alert không ai xử lý | Route theo team/service và escalation |
| Alert firing/resolve liên tục | Nhiễu và mất tin cậy | For-duration, hysteresis và grouping |
| Mỗi pod tạo một alert riêng | Một sự cố thành hàng trăm tin nhắn | Group theo service/cluster/incident |
| Silence không có expiry | Có thể che sự cố kéo dài | Bắt buộc lý do, owner và thời hạn |
| Acknowledge được coi là resolved | Incident bị đóng quá sớm | Tách acknowledged, mitigated và resolved |
| Dùng CPU làm proxy duy nhất cho user impact | Có thể bỏ sót lỗi thực | Kết hợp SLI/SLO và user journey |
| Alert không có runbook | Tốn thời gian triage | Gắn hướng dẫn và dashboard |
| Notification delivery không được giám sát | Alert có thể không tới người trực | Theo dõi delivery, ack và fallback |
| Gửi secret vào chat | Rò rỉ thông tin | Redact và dùng link có kiểm soát quyền |

## 26. Checklist phân biệt alert và status notification

### Điều kiện alert

- [ ] Có tác động hoặc rủi ro vận hành được mô tả.
- [ ] Có hành động cần thực hiện.
- [ ] Có urgency hoặc response window.
- [ ] Có severity và owner.
- [ ] Có runbook/dashboard/evidence link.
- [ ] Ngưỡng dựa trên SLO, baseline hoặc policy.
- [ ] Có điều kiện firing và resolve rõ.

### Status notification

- [ ] Cho biết sự kiện hoặc trạng thái chính xác.
- [ ] Không dùng ngôn ngữ khẩn cấp nếu không cần hành động.
- [ ] Có run ID/commit/release và liên kết chi tiết.
- [ ] Gửi tới người thực sự cần theo dõi.
- [ ] Có thể gom vào activity feed hoặc digest.
- [ ] Không tạo thông báo lặp không cần thiết.

### Vòng đời và vận hành

- [ ] Deduplication và grouping theo identity ổn định.
- [ ] Inhibition và silence có scope rõ.
- [ ] Silence có lý do, owner và expiry.
- [ ] Có acknowledge, escalation và resolve.
- [ ] Delivery failure có retry budget và fallback.
- [ ] Có audit cho thao tác alert.
- [ ] Rule được kiểm thử và review định kỳ.
- [ ] Nội dung không chứa secret hoặc dữ liệu nhạy cảm.

## Kết luận

Alert là tín hiệu yêu cầu phản ứng; status notification là thông tin giúp theo dõi tiến độ và kết quả. Hãy phân biệt chúng bằng tác động, hành động, urgency và ownership thay vì dựa vào log level hoặc màu sắc. Alert cần ngưỡng có cơ sở, severity, routing, runbook, deduplication, escalation và điều kiện resolve; status nên ngắn, chính xác và được gửi qua kênh ít gây gián đoạn. Khi kết hợp SLI/SLO, logs, metrics, traces và deployment timeline, nhóm có thể nhận biết sự cố cần xử lý mà vẫn giữ được lịch sử hoạt động đầy đủ, giảm alert fatigue và cải thiện khả năng điều tra CI/CD.

