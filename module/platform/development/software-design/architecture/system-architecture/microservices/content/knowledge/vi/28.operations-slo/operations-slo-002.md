# Ngân sách lỗi và quyết định tốc độ thay đổi trong microservices

## 1. Vì sao độ tin cậy liên quan trực tiếp đến tốc độ phát hành?

Một hệ thống microservices không thể bảo đảm 100% mọi request đều thành công trong mọi thời điểm. Lỗi có thể xuất hiện do một bản triển khai mới, bug nghiệp vụ, database quá tải, broker unavailable, đối tác timeout hoặc mạng phân vùng. Nhưng nếu yêu cầu độ tin cậy tuyệt đối, tổ chức có thể ngừng mọi thay đổi và vẫn không đạt được mục tiêu. Nếu chỉ tối ưu tốc độ ra tính năng, tổ chức lại có thể tiêu hao độ tin cậy mà người dùng chấp nhận.

**Error budget (ngân sách lỗi)** là lượng lỗi tối đa được phép trong một khoảng thời gian nếu muốn vẫn đạt **Service Level Objective (SLO)** đã cam kết. Nó tạo một ngôn ngữ định lượng để các nhóm sản phẩm, phát triển, vận hành và lãnh đạo cân bằng **tốc độ thay đổi** với **độ tin cậy thực tế**.

Ví dụ: một API có SLO thành công ít nhất 99,9% request hợp lệ trong 30 ngày. Khi có 10 triệu request hợp lệ, budget tương ứng là tối đa khoảng 10.000 request không đạt tiêu chí. Nếu sau 20 ngày đã có 9.500 request lỗi và tỷ lệ tiếp tục xấu đi, việc tung liên tục tính năng rủi ro cao có thể không hợp lý. Ngược lại, nếu lỗi rất ít và service còn nhiều budget, nhóm có thể có dư địa thử nghiệm và phát hành nhanh hơn trong phạm vi chính sách.

**Điểm quan trọng:** error budget không phải “quyền được cố ý gây lỗi”. Nó là công cụ quản trị rủi ro dựa trên trải nghiệm người dùng, dùng để lựa chọn đầu tư vào thay đổi hay cải thiện độ tin cậy.

Sau bài học, bạn có thể:
1. Phân biệt SLI, SLO, SLA, reliability target và error budget.
2. Tính ngân sách lỗi theo số request hoặc theo thời gian mà không trộn lẫn hai đơn vị.
3. Hiểu burn rate, multi-window alerting và lý do nhìn budget còn lại chưa đủ.
4. Đề xuất chính sách phát hành khi budget khỏe, suy giảm hoặc đã cạn.
5. Đánh giá rủi ro của thay đổi bằng canary, blast radius, feature flags và compatibility.
6. Áp dụng error-budget policy cho luồng xuyên nhiều microservices và những dependency chung.
7. Thiết kế dashboard, incident review và cơ chế ra quyết định không biến SLO thành công cụ đổ lỗi.

## 2. Nền tảng: SLI, SLO và SLA

Ba khái niệm gần nhau nhưng khác mục đích:

| Thuật ngữ | Bản chất | Ví dụ |
| --- | --- | --- |
| **SLI – Service Level Indicator** | Chỉ số định lượng chất lượng mà người dùng nhận được | Tỷ lệ request checkout hoàn tất hợp lệ trong 2 giây |
| **SLO – Service Level Objective** | Giá trị mục tiêu cho một SLI trong một cửa sổ thời gian | Ít nhất 99,9% checkout requests tốt trong 30 ngày |
| **SLA – Service Level Agreement** | Cam kết/thỏa thuận có hậu quả khi vi phạm nếu được quy định | Hợp đồng quy định điều kiện hoàn tiền/service credit khi không đạt mục tiêu |
| **Error budget** | Phần không đạt SLO tối đa có thể chấp nhận | Với SLO 99,9%, phần lỗi cho phép là 0,1% |
| **Error-budget policy** | Quy tắc tổ chức về quyết định khi tiêu hao budget | Tạm dừng release rủi ro cao khi budget suy giảm nhanh |

Không phải mọi SLO đều là SLA. SLO thường được thiết lập như mục tiêu kỹ thuật/nội bộ và có thể **nghiêm ngặt hơn** một SLA hợp đồng. Một service có nhiều SLI/SLO riêng: availability, latency, freshness, correctness hoặc độ trễ hoàn tất workflow.

Một SLI phải nêu rõ:
- **Population:** những request/event/user journey nào được tính.
- **Good event:** điều kiện nào được xem là đáp ứng trải nghiệm mong muốn.
- **Bad event:** điều kiện nào bị xem là không đáp ứng; không phải mọi HTTP 4xx là lỗi của service.
- **Cửa sổ đánh giá:** 7 ngày, 28 ngày, 30 ngày hoặc lịch khác.
- **Nguồn dữ liệu và quy tắc đo:** edge metrics, server metrics, synthetic check, queue/event lifecycle, client telemetry.
- **Xử lý traffic thấp, missing telemetry và bảo trì:** không được tùy tiện loại bỏ dữ liệu xấu.

Ví dụ SLI:

```text
Checkout availability SLI =
  số request checkout đủ điều kiện có kết quả tốt
  ------------------------------------------------
  tổng request checkout đủ điều kiện

Good:
  - response được hợp đồng xác nhận thành công
  - hoặc trạng thái PENDING hợp lệ nếu SLO định nghĩa rõ

Bad:
  - 5xx, timeout, lỗi xử lý do hệ thống
  - kết quả không đáp ứng hợp đồng trong deadline

Không tự động tính:
  - 400 do client gửi dữ liệu sai
  - yêu cầu bị chặn hợp lệ bởi chính sách bảo mật
```

Quyết định phân loại phải bám vào **hành vi người dùng mong đợi**. Nếu hệ thống trả HTTP 200 nhưng thực ra không tạo đơn, đó không nên được coi là thành công chỉ vì status code là 200.

## 3. Công thức error budget căn bản

Với SLI request-based:

```text
SLO target:          T (ví dụ 99,9% = 0,999)
Error fraction:      E = 1 - T
Eligible requests:   N
Allowed bad requests = N × E

Observed bad requests = B
Remaining budget = N × E - B
Budget consumed = B / (N × E)
```

Khi tính số request thực, giá trị budget có thể cần quy tắc làm tròn rõ để dùng cho báo cáo hoặc release gate. N là số request **trong cùng cửa sổ đo**, không phải traffic dự báo tùy ý. Với rolling window, N và B sẽ thay đổi liên tục khi dữ liệu vào/ra cửa sổ.

Ví dụ SLO 99,9% và 10.000.000 eligible requests:

```text
E = 1 - 0,999 = 0,001 (0,1%)
Allowed bad requests = 10.000.000 × 0,001
                     = 10.000

Nếu B = 8.000:
  Consumed = 8.000 / 10.000 = 80%
  Remaining = 2.000 bad requests
```

Một cách diễn giải khác là budget còn 20% **ở thời điểm đo đó**. Nó không chứng minh an toàn để phát hành nếu service đang có sự cố làm burn rate rất cao ngay lúc này.

Với SLI time-based (ví dụ một endpoint được kiểm tra theo từng khoảng thời gian đủ điều kiện), ngân sách tính theo tổng thời gian:

```text
Allowed bad time =
  observation_window_duration × (1 - SLO_target)
```

Ví dụ 99,9% của 30 ngày:

```text
30 ngày = 43.200 phút
Allowed bad time = 43.200 × 0,001 = 43,2 phút
```

**Không được hoán đổi trực tiếp** “10.000 request lỗi” với “43,2 phút downtime”. Request-based SLI phụ thuộc số request và thời điểm có traffic; time-based SLI phụ thuộc cách lấy mẫu/phân loại thời gian. Trong 10 phút outage vào giờ cao điểm, số request xấu có thể rất lớn.

## 4. Cách chọn SLI theo trải nghiệm người dùng

Một lỗi chọn SLI có thể làm error budget bị vô nghĩa dù công thức đúng.

### Availability

Thường đo tỷ lệ request có kết quả tốt. Với API, cần quyết định trường hợp:
- 5xx và timeout là bad.
- 4xx có thể là expected behavior, nhưng 429 do service quá tải có thể là bad tùy hợp đồng.
- 401 do token hết hạn hợp lệ thường không phải bad, nhưng 401 hàng loạt do JWKS rotation lỗi có thể là bad.
- Request bị hủy bởi client có tính vào denominator không?
- Một request retry thành công nhưng người dùng đã bỏ đi có được xem là good không?

Kết quả nên được đo gần **ranh giới người dùng nhận dịch vụ**, chẳng hạn Gateway hoặc synthetic client, thay vì chỉ những request đã đến handler của service. Nếu gateway không route được request vào backend, metric backend có thể vẫn đẹp trong khi người dùng thất bại.

### Latency

Một SLI latency có thể là tỷ lệ request hợp lệ đáp ứng trong một ngưỡng:

```text
Good latency request =
  response tốt và thời gian end-to-end <= 500 ms

Latency SLI =
  số good latency requests / tổng eligible requests
```

Cần kết hợp correctness và latency đúng hợp đồng: trả HTTP 500 trong 10 ms không nên được xem là một request tốt chỉ vì nhanh. Ngoài phân phối p95/p99, threshold-based SLI thường có ý nghĩa trực tiếp cho error budget.

### Correctness và data freshness

Một service có thể luôn trả 200 nhưng dữ liệu sai:
- Đơn hàng hiển thị trạng thái CONFIRMED khi thanh toán chưa xác nhận.
- Dữ liệu search stale vượt ngưỡng.
- Worker bỏ sót event hoặc xử lý trùng side effect.
- Billing tính sai phí hoặc áp sai tỷ giá.

Các SLO correctness/freshness cần định nghĩa **đơn vị tác động**: giao dịch, bản ghi, event hoặc user journey. Đôi khi phải bổ sung data quality checks và business telemetry; metric HTTP không đủ.

### Asynchronous workflow

Với event-driven microservices, “consumer vẫn đọc Kafka” không chứng minh người dùng nhận kết quả. SLI có thể đo:

```text
Tỷ lệ shipment requests hoàn tất trong 2 phút =
   số operation có trạng thái terminal hợp lệ trong 2 phút
   -------------------------------------------------------
   tổng operation đến hạn cần hoàn tất trong cửa sổ đo
```

Cần dùng cohort và thời điểm đến hạn rõ ràng để tránh đánh dấu operation vừa được enqueue là lỗi trước khi deadline của nó tới. Nếu workflow có trạng thái PENDING hợp lệ, phải xác định PENDING được chấp nhận trong bao lâu.

## 5. Chọn SLO mục tiêu: quá thấp hoặc quá cao đều gây vấn đề

SLO là thỏa thuận về chất lượng có ý nghĩa đối với người dùng và chi phí để đạt chất lượng đó. Không nên chọn 99,999% cho mọi service chỉ vì con số trông ấn tượng.

Ví dụ:
- Checkout và thanh toán thường có rủi ro nghiệp vụ cao, cần SLO gắn với giao dịch.
- Recommendation service có thể chấp nhận lỗi mà trang sản phẩm vẫn hiển thị.
- Internal batch report có thể cần freshness “hoàn tất trước 7 giờ sáng” thay vì latency 100 ms.
- Search index projection có thể có SLO delay dưới vài phút, trong khi audit event delivery có yêu cầu khác.

SLO nên dựa vào:
1. Kỳ vọng của người dùng và ngưỡng họ nhận ra chất lượng kém.
2. Dữ liệu lịch sử khả dụng, các incident gần đây và pain points.
3. Điều kiện hệ thống: lỗi có thể tránh được, chi phí giảm lỗi và độ phức tạp.
4. Tính quan trọng của hành trình và những downstream bắt buộc.
5. Rủi ro pháp lý, hợp đồng hoặc bảo mật nếu có.
6. Mức ngân sách lỗi đủ để đưa ra quyết định thực tế.

Nếu chọn SLO thấp hơn mức người dùng cần, nhóm có thể “đạt SLO” nhưng trải nghiệm tệ. Nếu chọn cao hơn nhiều so với năng lực hoặc không dựa trên nhu cầu, budget luôn cạn và chính sách luôn khóa thay đổi, làm mất vai trò cân bằng.

## 6. Error budget là đơn vị kinh tế của độ tin cậy

Hãy hình dung hai cực đoan:

**Chỉ tối ưu release velocity:**
- Phát hành liên tục nhưng không giới hạn blast radius.
- Sự cố nhỏ xuất hiện thường xuyên; người dùng mất niềm tin.
- Team chạy theo rollback/hotfix, tốc độ thực tế về lâu dài giảm.

**Chỉ tối ưu uptime tuyệt đối:**
- Hạn chế hầu hết thay đổi dù reliability đã đủ tốt.
- Tính năng cải thiện trải nghiệm chậm được triển khai.
- Lỗi cơ bản từ hạ tầng, dependency hoặc drift vẫn xảy ra.
- Độ an toàn giảm vì hoãn vá bảo mật và refactor cần thiết.

Error budget tạo một câu hỏi cụ thể: **“Tổ chức còn bao nhiêu dư địa rủi ro, và thay đổi nào đáng dùng dư địa đó?”**

Quy trình không chỉ là phản ứng khi budget cạn. Nó còn phân bổ nguồn lực:
- Khi budget khỏe và ổn định: ưu tiên tính năng mới, tối ưu UX, thử nghiệm trong phạm vi kiểm soát.
- Khi budget giảm nhanh: giảm blast radius, tăng canary/gates, tập trung nguyên nhân lỗi.
- Khi budget cạn: ưu tiên giảm incident recurrence, capacity, automation, observability và những thay đổi làm phục hồi reliability.
- Khi một hạng mục có khả năng tăng reliability: không nên máy móc chặn chỉ vì là “deployment”.

**Ngân sách lỗi là công cụ cho cả Product và Engineering**, không phải KPI chỉ giao cho nhóm vận hành.

## 7. Rolling window và calendar window

### Calendar window

Ví dụ SLO 99,9% cho tháng 11. Mọi request từ ngày đầu tới cuối tháng được cộng vào N và B. Sang tháng mới, số liệu budget của cửa sổ mới bắt đầu lại.

Ưu điểm: dễ gắn báo cáo theo tháng. Hạn chế: khi gần cuối tháng, budget còn ít hay nhiều có thể khiến quyết định khác biệt mạnh so với đầu tháng; “đổi tháng là hết lỗi” không đúng với trải nghiệm người dùng.

### Rolling window

Ví dụ tại mọi thời điểm tính lại SLI trong **30 ngày gần nhất**:

```text
Ngày hiện tại - 30 ngày ----------------------> Hiện tại
      ^                                      ^
      dữ liệu cũ rời cửa sổ                  sự kiện mới vào
```

Ưu điểm: không có cliff nhân tạo ở ranh giới tháng; phản ánh chất lượng gần đây. Hạn chế: budget còn lại thay đổi cả vì các lỗi cũ dần ra khỏi cửa sổ, không chỉ vì lỗi mới. Dashboard phải diễn giải đúng.

Cần thống nhất:
- Ngày/giờ, timezone và cách chốt kỳ.
- Nguồn tính denominator và dữ liệu thiếu.
- Cách xử lý incident kéo dài qua cửa sổ.
- Cửa sổ báo cáo tổ chức và cửa sổ alerting vận hành có thể khác nhau.

**Không tự reset budget để tuyên bố service khỏe** sau một incident nếu trải nghiệm hiện tại vẫn suy giảm. Rolling SLO là một thước đo, không phải bộ nhớ incident hay cơ chế xóa trách nhiệm khôi phục.

## 8. Burn rate: tốc độ tiêu hao budget

**Burn rate** đo tốc độ lỗi hiện tại so với tốc độ lỗi trung bình được phép để vừa chạm ngưỡng SLO ở cả cửa sổ.

Với SLO request-based có error allowance `E = 1 - T`:

```text
Observed bad-event fraction over short window = p
Burn rate = p / E
```

Ví dụ SLO 99,9%, E = 0,001:
- Error rate 0,1% → burn rate = 1.
- Error rate 0,2% → burn rate = 2.
- Error rate 1,44% → burn rate = 14,4.
- Error rate 0,01% → burn rate = 0,1.

**Burn rate 1** nghĩa là đang tiêu budget đúng tốc độ trung bình cho phép; nếu duy trì suốt cửa sổ thì chạm ngưỡng SLO. Burn rate 14,4 nghĩa là tốc độ hiện tại cao gấp 14,4 lần mức được phép. Nó không nói budget hiện còn bao nhiêu.

Một biểu diễn gần đúng về **phần budget bị tiêu trong khoảng Δt** khi traffic tương đối đều và SLI request-based:

```text
Fraction of budget spent ≈ burn_rate × (Δt / SLO_window)
```

Với rolling 30 ngày = 720 giờ:
- Burn 14,4 duy trì 1 giờ → khoảng 2% budget.
- Burn 6 duy trì 6 giờ → khoảng 5% budget.
- Burn 1 duy trì 24 giờ → khoảng 3,33% budget.

Những con số này dựa trên giả định lưu lượng phân bố gần đều. Nếu traffic tập trung mạnh theo giờ, **budget request-based tiêu theo số eligible requests**, không tiêu đều theo thời gian. Dashboard phải đo cả error fraction và request counts thay vì chỉ nhân burn rate theo thời gian.

### Burn rate cao nhưng budget còn nhiều

Service mới chạy tốt 28 ngày, còn 95% budget. Một deploy bắt đầu gây 15% request lỗi trong 10 phút. Budget còn nhiều không phải lý do tiếp tục rollout: **burn rate rất cao** cho thấy cần can thiệp trước khi user impact lan rộng.

### Burn rate thấp nhưng budget đã cạn

Service vừa qua incident lớn, hiện error rate ổn định trở lại. Burn rate thấp cho biết sự cố đã chấm dứt, nhưng 30-day rolling budget có thể vẫn âm. Chính sách nên ưu tiên tránh tái phát và phục hồi trust, không phải tự động coi mỗi phút ổn định là đủ để phát hành mọi thay đổi rủi ro cao.

## 9. Multi-window, multi-burn-rate alerting

Alert chỉ dựa vào “budget còn dưới 10%” thường phát hiện chậm khi một outage đột ngột xảy ra. Alert chỉ dựa vào error rate 5 phút thường nhiều nhiễu do sampling, traffic thấp và burst nhỏ.

**Multi-window burn-rate** kết hợp một cửa sổ dài để xác nhận ảnh hưởng liên tục và một cửa sổ ngắn để xác nhận lỗi đang xảy ra. Ví dụ mô hình tham khảo cho SLO 99,9% trong rolling 30 ngày:

| Mức | Cửa sổ dài | Cửa sổ ngắn | Burn threshold | Ý nghĩa vận hành |
| --- | --- | --- | --- | --- |
| Nhanh, nghiêm trọng | 1 giờ | 5 phút | 14,4 | Tốc độ cao; cần phản ứng nhanh |
| Chậm, kéo dài | 6 giờ | 30 phút | 6 | Lỗi không quá đột ngột nhưng ăn budget đáng kể |

Cả **hai cửa sổ** nên vượt threshold trước khi alert thuộc nhóm tương ứng kích hoạt, theo quy tắc được thiết kế. Đây là ví dụ phổ biến để suy luận; tổ chức phải điều chỉnh thời gian, mức burn, routing và traffic theo SLO cụ thể.

Với 30-day window và giả định traffic đều:
- Burn 14,4 trong một giờ tương đương khoảng 2% budget.
- Burn 6 trong sáu giờ tương đương khoảng 5% budget.

Tần suất đánh giá, hoạt động của recording rules, missing metrics và lượng request phải được kiểm chứng. Một API ít traffic có thể có tỷ lệ lỗi 100% chỉ vì một request xấu, nên có thể cần điều kiện tối thiểu về volume hoặc một SLI bổ sung để giảm nhiễu. Nhưng **không được lọc bỏ tất cả request thấp traffic** nếu mỗi request đều cực kỳ quan trọng.

### Phản ứng khi alert

- **Page khẩn cấp:** khi burn đủ cao và ongoing, cần người phản ứng theo on-call.
- **Ticket/working-hours:** khi burn nhỏ nhưng kéo dài và chưa đến ngưỡng page.
- **Release guardrail:** dùng burn rate và budget còn lại để giảm rollout speed.
- **Root-cause:** liên kết alert với operation, dependency, change ID, trace và runbook.

Alert là tín hiệu để xử lý nguy cơ SLO; không nên tạo một trang cho mỗi service khi cùng một lỗi hạ tầng khiến hàng chục SLO cùng burn. Cần dedup và incident coordination.

## 10. Còn bao nhiêu budget? Hai góc nhìn cần hiển thị

Một dashboard ra quyết định nên hiển thị **tồn kho** và **tốc độ tiêu**:

```text
Error budget remaining:       25%
Burn rate 5m:                0.4
Burn rate 1h:                0.7
Burn rate 6h:                1.1
Eligible requests 30d: 10,000,000
Bad requests 30d:          7,500
Allowed bad requests:     10,000
Current release version: checkout@2.18.4
```

Số liệu chỉ minh họa. Nếu budget còn 25% nhưng burn tăng từ 0,4 lên 15 sau canary, cần đánh giá rollout ngay. Nếu còn 5% nhưng burn ≈0 và sự cố đã xử lý, có thể cần giảm rủi ro phát hành trong thời gian khôi phục thay vì tiếp tục động tác chữa cháy không có giá trị.

Ba câu hỏi:
1. **Còn bao nhiêu dư địa lỗi?** Budget remaining và các incident còn tác động trong cửa sổ.
2. **Đang tiêu nhanh hay chậm?** Burn rate theo nhiều khoảng đo.
3. **Nguồn lỗi thuộc đâu và có thể kiểm soát thế nào?** Endpoint, dependency, deploy, config, resource saturation, security outage.

Không nên ra quyết định chỉ bằng một phần trăm budget còn lại mà không hiểu người dùng nào bị ảnh hưởng và liệu vấn đề đã dừng.

## 11. Error-budget policy: từ số liệu thành quyết định

Một chính sách phải **được thống nhất trước khi xảy ra sự cố**, có owner, mức ngưỡng, thời gian hiệu lực và ngoại lệ. Bảng sau là ví dụ để tùy chỉnh, không phải chuẩn bắt buộc:

| Trạng thái gợi ý | Dữ kiện tham khảo | Hướng hành động |
| --- | --- | --- |
| **Bình thường** | Budget còn nhiều, burn ổn định dưới ngưỡng | Triển khai theo pipeline thường, canary/rollback chuẩn |
| **Thận trọng** | Budget giảm nhanh hoặc một burn alert đang kéo dài | Giảm batch release, tăng kiểm tra contract/canary, hạn chế thay đổi rủi ro |
| **Ưu tiên reliability** | Budget gần cạn, incident lặp lại hoặc burn vượt ngưỡng đáng kể | Hoãn feature release rủi ro cao; ưu tiên fix lỗi, capacity, resilience và telemetry |
| **Budget đã vượt** | SLO của cửa sổ không đạt hoặc tiếp tục có user impact lớn | Điều tra, áp dụng release exception review, tập trung phục hồi và chống tái phát |

Một tổ chức có thể dùng các ngưỡng như **25%** hoặc **10% budget còn lại** để kích hoạt thảo luận, nhưng đây chỉ là điểm khởi đầu. Các hệ thống ít request hoặc sự cố tác động mạnh tới nhóm khách hàng quan trọng có thể cần quy tắc khác.

Chính sách không nên là “đến 0% thì cấm merge mọi commit”. Được phép thực hiện thay đổi giúp **phục hồi hoặc tăng độ tin cậy**, bản vá bảo mật bắt buộc, thay certificate sắp hết hạn, migration phòng mất dữ liệu và các sửa chữa an toàn đã được đánh giá.

### Quyền quyết định

Một governance rõ ràng nên xác định:
- Service owner chịu trách nhiệm tín hiệu SLO và tình trạng vận hành.
- Product owner tham gia ưu tiên giữa chức năng và reliability.
- SRE/Platform hỗ trợ chuẩn SLI, tooling, capacity và incident review.
- Release approver/incident commander xử lý ngoại lệ khẩn cấp.
- Trường hợp nào được rollback tự động, trường hợp nào cần người quyết định.

Không để một dashboard trở thành nguồn quyền tuyệt đối nếu telemetry hỏng hoặc bị thiếu dữ liệu. Mọi ngoại lệ có thể có lý do, thời hạn và kế hoạch giám sát.

## 12. Tốc độ thay đổi là gì và vì sao cần quản lý?

“Change velocity” không chỉ là số commit hay số lần deploy. Nó gồm khả năng đưa giá trị tới người dùng an toàn, ví dụ:
- Lead time từ PR đến release có ích.
- Tần suất phát hành một service độc lập.
- Thời gian phát hiện lỗi sau triển khai.
- Thời gian khôi phục khi release gây sự cố.
- Change failure rate và user impact của thay đổi.
- Tỷ lệ release chỉ sửa một service mà không cần lockstep toàn hệ thống.

Một tổ chức có nhiều deployment nhưng rollback liên tục có thể có velocity biểu kiến cao, còn **effective delivery** thấp. Error budget giúp đưa chi phí user impact vào thảo luận về velocity.

Đừng đo năng suất cá nhân bằng “số request lỗi do commit của developer X” hoặc “số budget tiêu cho nhóm Y”. Reliability là hệ quả của nhiều yếu tố: kiến trúc, hạ tầng, traffic, quy trình, tests và quyết định product. Nếu biến budget thành chỉ tiêu đổ lỗi, team có thể giấu lỗi, đổi định nghĩa metric hoặc không dám triển khai bản sửa cần thiết.

## 13. Quyết định theo loại thay đổi, không chỉ trạng thái budget

Hai release cùng ngày không có rủi ro giống nhau:

| Loại thay đổi | Rủi ro | Guardrail phù hợp |
| --- | --- | --- |
| Sửa nội dung giao diện không tác động backend | Thường nhỏ, tùy phạm vi | CI, canary/feature flag khi cần |
| Đổi nghiệp vụ checkout | Cao với doanh thu và correctness | Contract, integration, canary, business SLI, rollback |
| Đổi schema database | Có nguy cơ phá mixed versions/rollback | Expand–migrate–contract, migration tests, data backup |
| Đổi event schema | Có thể phá consumer cũ và DLQ | Schema compatibility, consumer-driven tests, staged emission |
| Nâng runtime/library nền tảng | Ảnh hưởng nhiều service | Affected-target CI, phased rollout |
| Tối ưu performance/DB index | Có thể cải thiện hoặc gây lock | Load test, query analysis, safe migration |
| Vá lỗi security khẩn cấp | Trì hoãn cũng có rủi ro lớn | Fast-track với canary/rollback và giám sát cao |
| Rotation certificate/secret sắp hết hạn | Không làm cũng gây outage | Overlap, readiness, staged rollout, validation |

Trong trạng thái budget thấp:
- Hoãn thay đổi tính năng lớn có blast radius rộng khi không cấp thiết.
- Ưu tiên sửa incident recurrence, load shedding, retry budget hoặc data corruption.
- Nếu phải deploy một change risk cao, cần mitigation: canary nhỏ, feature flag tắt mặc định, deploy ngoài peak, owner theo dõi trực tiếp, rollback plan.
- Dùng telemetry để quyết định dừng/tiếp tục theo **user impact**, không chỉ tỷ lệ pod Ready.

**Thay đổi được trì hoãn cũng mang rủi ro.** Tránh policy vô tình khóa bản vá CVE, migration chống mất dữ liệu hoặc sửa một lỗi đang làm budget burn.

## 14. Canary và progressive delivery giúp bảo toàn budget

Canary giảm phạm vi ảnh hưởng trước khi triển khai toàn bộ:

```text
New version
     |
     v
1% traffic → đánh giá SLI/business metrics
     |
     v
5% traffic → đánh giá với lượng mẫu đủ
     |
     v
25% traffic → kiểm tra theo tenant/region/endpoint
     |
     v
100% traffic hoặc rollback
```

Các tỷ lệ là **ví dụ minh họa**, không là cấu hình mặc định. 1% traffic có thể quá ít để kết luận đối với API lưu lượng thấp hoặc lỗi hiếm. Khi rủi ro xảy ra ở một nhóm tenant, phân phối traffic ngẫu nhiên có thể bỏ sót nhóm đó.

Canary cần:
1. Baseline ổn định của version cũ, hoặc cách so sánh điều chỉnh traffic.
2. Nhóm metric phù hợp: error, latency, correctness, business conversion, DB saturation.
3. Tính đến sample size và variance; không tuyên bố thành công vì 3 request đều 200.
4. Deadline đánh giá rõ, xử lý missing metrics.
5. Rollback dựa trên ngưỡng và mức độ chắc chắn phù hợp.
6. Tương thích schema/event khi old/new cùng hoạt động.
7. Audit quyết định tiếp tục hay dừng rollout.

Một canary giảm blast radius nhưng **không biến thay đổi phá schema toàn cục thành an toàn**. Nếu migration database chạy trước canary và xóa cột, mọi pod cũ có thể hỏng ngay dù chỉ 1% traffic dùng version mới.

## 15. Feature flags, kill switches và giảm phạm vi sự cố

Feature flag cho phép deploy code nhưng chưa bật đường nghiệp vụ mới. Khi error budget còn ít, mô hình này giúp tách **phát hành artifact** khỏi **kích hoạt rủi ro**.

```text
Deploy code có feature mới → Flag OFF
            |
            v
Bật flag cho internal tenant
            |
            v
Bật một nhóm user nhỏ
            |
            v
Theo dõi business SLI và error budget
            |
            +→ Nếu xấu: Flag OFF / rollback
            |
            v
Mở rộng theo đợt
```

Guardrail:
- Không để flag trở thành đường bypass authentication/authorization.
- Có owner, expiry/deletion plan để tránh nợ kỹ thuật.
- Kiểm thử cả flag ON/OFF và mixed-version behavior.
- Cấu hình fallback an toàn nếu feature flag service unavailable.
- Ghi rõ telemetry nào đo cohort bật flag.
- Với thao tác đã có side effect (thanh toán, ghi dữ liệu), tắt flag không tự đảo ngược các thao tác đã thực hiện; cần reconciliation/compensation.

Nếu flag chỉ ảnh hưởng 5% request, SLI tổng thể có thể che lỗi nghiêm trọng của cohort. Cần đo cả **SLO tổng** và **đường triển khai có rủi ro** để không “lấy số lớn che số nhỏ”.

## 16. Microservices: một hành trình có thể đốt nhiều budget

Ví dụ luồng checkout:

```text
Client
  |
  v
Gateway → Checkout → Inventory → Payment
                       |             |
                    Database       Provider
```

Mỗi service có SLO riêng, nhưng người dùng quan tâm **checkout có hoàn tất đúng và đúng hạn** hay không. Nếu một lời gọi Payment timeout, cả checkout có thể thất bại dù Gateway và Checkout vẫn “up”.

Một số hướng:
- Đặt **journey SLI** cho hành động checkout qua điểm vào gần người dùng.
- Đặt SLI riêng cho Checkout, Inventory, Payment để chẩn đoán.
- Gắn trace và correlation ID để xác định dependency gây ảnh hưởng.
- Đo timeout ở edge, cả khi downstream không trả error metric.
- Không nhân đôi một user journey thất bại thành nhiều “bad user requests” chỉ vì các service retry; nhưng mỗi service có thể có chỉ số riêng cho thao tác nó sở hữu.
- Phân biệt impact ở user level với internal request-level khi báo cáo.

### Một phép tính lý thuyết

Nếu ba service bắt buộc trong đường đồng bộ mỗi cái có availability 99,9% và giả định các lỗi độc lập, xác suất cả ba đồng thời sẵn sàng là:

```text
0,999 × 0,999 × 0,999 ≈ 0,997003
                              ≈ 99,7003%
```

Đây là phép tính minh họa, không phải ước lượng production nếu có lỗi chung, retries, cache, async processing hoặc correlated failures. Nó cho thấy **SLO từng service không tự bảo đảm SLO của hành trình**.

Vì thế cần quyết định error budget ở ít nhất hai mức: user journey quan trọng và các service/dependency phục vụ nó. Các mức phải nhất quán về định nghĩa, không mặc nhiên cộng/trừ ngân sách của các service như một quỹ tiền chung.

## 17. Phân bổ error budget giữa service và dependency

Giả sử Checkout SLO 99,9%, trong đó nhiều thành phần cùng đóng góp lỗi. Có thể lập bảng nguyên nhân incident:

| Nguồn ảnh hưởng | Bad checkout requests (ví dụ) | Quan sát |
| --- | ---: | --- |
| Checkout code | 1.200 | Bug sau deploy |
| Inventory timeout | 2.300 | Connection pool cạn |
| Payment provider outage | 3.500 | External dependency |
| Gateway routing | 500 | Config sai |
| Unknown/other | 500 | Cần cải thiện tracing |
| **Tổng** | **8.000** | Trong cửa sổ ví dụ có 10.000 budget |

Các số liệu này minh họa cách phân nhóm nguyên nhân và giả định **không đếm trùng** các request. Trong thực tế, một request có thể bị ảnh hưởng bởi nhiều nguyên nhân; quy tắc phân loại nên có primary cause hoặc cách phân bổ nhất quán. **Journey error budget là số lỗi người dùng**, không phải phép cộng đơn giản từ dashboard của từng service.

Một service không thể chỉ tuyên bố “lỗi do provider, không tính vào SLO” nếu người dùng thực sự không hoàn tất được nghiệp vụ và hợp đồng không cho phép loại trừ. Phân tích root cause giúp phân công sửa chữa, không phải xóa user impact.

Có thể:
- Thương lượng SLO phụ thuộc khi chọn provider.
- Có fallback hoặc trạng thái pending hợp lệ nếu nghiệp vụ cho phép.
- Giảm synchronous dependencies không cần thiết.
- Dùng circuit breaker/bulkhead để tránh lỗi lan rộng.
- Xây reconciliation khi kết quả thanh toán không xác định.
- Đề xuất business continuity plan khi dependency quan trọng outage.

## 18. Ví dụ đầy đủ: budget còn 20% trước release lớn

Một hệ checkout dùng request-based SLO 99,9% trên 30 ngày, tại thời điểm đánh giá có:

```text
Eligible requests 30 ngày: 10.000.000
Allowed bad:             10.000
Observed bad:             8.000
Remaining:                2.000 (20%)
Current burn rate 1h:       0,8
Next change:      đổi logic pricing và cấu hình retry
```

Release mới được dự kiến triển khai cho 100% traffic, nhưng phần thay đổi retry có thể làm nhiều request tới Payment hơn khi provider chậm.

Một cuộc họp quyết định nên xem:
1. **Change risk:** có đụng payment correctness, idempotency và concurrency không?
2. **User impact potential:** nếu có lỗi thì bao nhiêu transaction/tenant bị ảnh hưởng?
3. **Mitigation:** feature flag, canary, deadline và rollback đã kiểm chứng chưa?
4. **Reliability debt:** 8.000 lỗi vừa qua đến từ đâu; có lỗi đang lặp lại không?
5. **Urgency:** feature mới có deadline không thể bỏ hay là cải tiến có thể hoãn?
6. **Budget forecast:** nếu lỗi tăng trong một giờ cao điểm thì còn bao nhiêu dư địa?
7. **Ownership:** ai trực dashboard, ai có quyền dừng rollout?

Một quyết định hợp lý có thể là:
- Triển khai riêng phần sửa retry budget/guardrail nếu nó giảm rủi ro.
- Hoãn hoặc giảm phạm vi bật logic pricing mới nếu không cấp thiết.
- Bật canary nhỏ, có tiêu chí dừng theo checkout SLI và payment anomaly.
- Không thay đổi schema phá vỡ hoặc tắt đường xử lý cũ khi chưa chứng minh compatibility.
- Sau release, ghi kết quả so với baseline để cải thiện policy.

Đây là ví dụ quyết định có cân nhắc, **không phải quy tắc tự động** rằng budget 20% thì luôn cấm phát hành.

## 19. Khi budget đã âm hoặc SLO đã vi phạm

Nếu tổng bad requests đã vượt allowed budget:

```text
Allowed bad: 10.000
Observed bad: 12.500
Remaining: -2.500
Budget consumed: 125%
SLO trong cửa sổ đang bị vi phạm
```

Cần tách ba việc:
- **Chặn tình trạng lỗi đang diễn ra:** rollback, toggle off, scale/capacity, fix dependency.
- **Giảm nguy cơ tái phát:** incident review, test gaps, contract validation, fault isolation.
- **Khôi phục chính sách phát hành:** quy định khi nào có thể resume, dưới những guardrail nào.

Trong rolling window, budget có thể trở lại dương khi dữ liệu incident cũ rời cửa sổ và hệ thống ổn định. Điều đó **không tự chứng minh** đã sửa nguyên nhân. Vì vậy cần thêm điều kiện như mitigation đã triển khai, hành động quan trọng có owner, burn ổn định và business SLI hồi phục.

Một số thay đổi nên được ưu tiên **ngay cả khi budget âm**:
- Fix bug gây lỗi hiện tại.
- Vá bảo mật nghiêm trọng.
- Rotation key/chứng chỉ tránh outage sắp tới.
- Cải thiện idempotency, bulkhead, timeout, circuit breaker.
- Migration chống mất dữ liệu hoặc sửa khả năng rollback.

Chính sách tốt hạn chế **rủi ro không cần thiết**, không chặn công việc giảm rủi ro.

## 20. Khi traffic ít hoặc phân bố rất lệch

Một API admin mỗi ngày chỉ có 20 request không nên dùng cùng alerting policy như Checkout 100.000 request/phút mà không điều chỉnh.

Với 20 request và một request lỗi, error rate là 5%. Burn rate so với SLO 99,9% là 50, nhưng một mẫu có thể rất nhiễu. Ngược lại, nếu đó là thao tác chuyển tiền lớn, một lần lỗi có thể rất quan trọng dù traffic thấp.

Hướng xử lý:
- Chọn cửa sổ phù hợp và đảm bảo sample size cho quyết định thống kê.
- Có alert cho **sự kiện quan trọng tuyệt đối** ngoài error-rate alert.
- Sử dụng synthetic tests và business transaction checks khi traffic quá thấp.
- Không làm mất lỗi bằng cách gộp quá nhiều endpoint không cùng criticality.
- Cân nhắc request weighted SLI hoặc phân tầng customer journey nếu được thống nhất rõ.
- Nêu tình trạng telemetry missing; “không thấy lỗi” không bằng “đã đo được mọi request”.
- Có guardrail thủ công cho những thao tác chỉ xảy ra vài lần nhưng hậu quả lớn.

Một SLI service-wide có thể rất đẹp trong khi 100% request của một khách hàng enterprise bị lỗi. Do đó có thể cần phân tách theo region, class of customer hoặc critical operation ở tầng điều tra, không nhất thiết đặt user ID làm label time series.

## 21. Tác động của latency và partial failure đến budget

Không phải sự cố nào cũng làm HTTP 500. Một service có thể:
- Trả 200 sau 30 giây trong khi client timeout sau 3 giây.
- Trả 202 và để workflow treo quá hạn.
- Trả thiếu một phần dữ liệu mà UI không thể sử dụng.
- Retry rồi thành công, nhưng charge khách hàng hai lần.
- Xử lý duplicate event khiến trạng thái báo cáo sai.

Với latency SLO “99% request hợp lệ được hoàn tất dưới 500 ms”, mỗi request đáp ứng quá 500 ms là **bad event** cho SLO latency dù HTTP 200. Với correctness SLO, request nhanh nhưng sai cũng bad.

Nhiều SLO có thể cùng tồn tại, ví dụ:
- Availability ≥ 99,9%.
- Latency under 500 ms ≥ 99%.
- Order payment correctness ≥ 99,99% theo định nghĩa nghiệp vụ.
- Event-to-effect completion within 2 min ≥ 99,5%.

Không tùy tiện cộng ngân sách của các SLO này thành một con số. Mỗi SLO có population, target và đơn vị riêng. Một lỗi có thể vi phạm nhiều SLO và cần được nhìn từ mỗi góc độ, trong khi incident review vẫn tránh đếm trùng người dùng bị tác động.

## 22. Thu thập telemetry trong môi trường microservices

### SLI tốt nên đo tại đâu?

- **Edge/Gateway:** phù hợp với request success/latency người dùng nhưng có thể không thấy kết quả bất đồng bộ.
- **Service ingress:** phù hợp với ranh giới riêng một service, giúp phân tích lỗi.
- **Client/SDK:** cho biết timeout hoặc error mà client thực sự thấy.
- **Workflow state store:** phù hợp với đơn hàng/shipments/payments hoàn tất sau nhiều event.
- **Synthetic probes:** bổ sung cho những luồng ít traffic và kiểm tra deployment.
- **Partner telemetry:** giúp chẩn đoán sự cố ngoài phạm vi, nhưng không thay user journey SLI.

Metric cần:
- Operation/route ổn định, status/error class, region, deployment version.
- Đủ độ phân giải để xem burst, đồng thời lưu aggregate đủ dài cho SLO window.
- Sampling strategy phù hợp: metrics không nên chỉ dựa vào traces bị sample mà không hiệu chỉnh.
- Xử lý ingestion delay, counter reset và telemetry gaps.
- Không chứa secrets, bearer token, giá trị thanh toán nhạy cảm hoặc user ID ở labels.

### Ví dụ bộ đếm minh họa

```text
checkout_requests_total{
  route="/checkout",
  outcome="good"
}

checkout_requests_total{
  route="/checkout",
  outcome="bad"
}
```

`outcome` phải được gắn theo quy tắc SLI đã định nghĩa, không tùy tiện dựa riêng vào HTTP status. Với cùng một operation, tổng good+bad phải phản ánh đúng số request eligible trong population đã chọn. Các label values phải nhất quán để truy vấn không bỏ mất một subset traffic.

## 23. PromQL minh họa cho request-based SLI

Ví dụ có metric:

```text
checkout_requests_total{outcome="good"}
checkout_requests_total{outcome="bad"}
```

Tính tỷ lệ bad trong cửa sổ 5 phút bằng PromQL minh họa:

```promql
sum(rate(checkout_requests_total{outcome="bad"}[5m]))
/
clamp_min(
  sum(rate(checkout_requests_total[5m])),
  1e-9
)
```

Với SLO 99,9%, burn rate trong 5 phút:

```promql
(
  sum(rate(checkout_requests_total{outcome="bad"}[5m]))
  /
  clamp_min(sum(rate(checkout_requests_total[5m])), 1e-9)
)
/
0.001
```

Với cửa sổ một giờ, thay `[5m]` bằng `[1h]`. Multi-window alert yêu cầu xây recording rules phù hợp và so sánh **cả cửa sổ dài lẫn ngắn** theo chính sách. Các snippet ở đây minh họa nguyên tắc, không phải cấu hình alert production hoàn chỉnh.

Lưu ý:
- `rate` trên counter có tính đến counter reset theo cơ chế Prometheus, nhưng query vẫn cần xử lý missing series và low traffic.
- Denominator phải là toàn bộ **eligible requests**, không gộp endpoint ngoài SLO.
- Nếu histogram/metric đã có labels region/route, aggregation cần giữ hoặc loại labels đúng mục đích.
- Nếu ở một khoảng không có request, chia cho epsilon có thể trả giá trị 0 thay vì “thiếu dữ liệu”; phải xử lý trường hợp này trong policy và alert.
- Dữ liệu Prometheus 30 ngày đòi retention/recording đủ, và rolling budget report cần hiểu chênh lệch sampling/retention.

### Latency threshold SLI

Với histogram `http_server_request_duration_seconds` và threshold 0,5 giây, tỷ lệ request dưới ngưỡng có thể được tính bằng histogram bucket:

```promql
sum(rate(http_server_request_duration_seconds_bucket{
  route="/checkout",le="0.5"
}[5m]))
/
clamp_min(
  sum(rate(http_server_request_duration_seconds_count{
    route="/checkout"
  }[5m])),
  1e-9
)
```

Đây mới là tỷ lệ theo latency histogram. Nếu metric bao gồm cả request 5xx thì cần điều chỉnh để đo **good result AND within threshold**, chứ không coi một lỗi nhanh là request tốt. Việc instrument histogram và label conventions phụ thuộc framework và version; phải đối chiếu với telemetry thực tế.

## 24. Thiết kế SLO recording và dashboard ra quyết định

Một dashboard dành cho đội vận hành/đội phát hành nên có:

| Thành phần | Mục đích |
| --- | --- |
| SLO name và owner | Biết trách nhiệm và population |
| Target + rolling window | Thấy mục tiêu định lượng |
| Eligible events 30 ngày | Biết volume thực |
| Good/bad events | Xác minh cách tính |
| Budget allowed/consumed/remaining | Biết dư địa rủi ro |
| Burn rate 5m/1h/6h | Phát hiện tốc độ lỗi |
| Current incident status | Phân biệt lỗi đang xảy ra và đã kết thúc |
| Recent deployments/change IDs | Correlate với sự cố |
| Top offending operations/regions | Khoanh vùng blast radius |
| Dependency errors/latency | Xác định nguyên nhân bắc cầu |
| Release policy state | Quyết định được rút ra theo guardrail |
| Telemetry health | Phát hiện missing metrics và data delay |

Đừng đặt “budget remaining” mà không có link tới SLI specification. Không thể đưa ra quyết định nếu team không biết trường hợp nào được coi là bad.

Với microservices, dashboard per service là cần thiết để chẩn đoán, nhưng nên có tổng quan **critical journeys** như checkout, đăng nhập, hoàn tiền, nhận thông báo đúng hạn.

## 25. Incident response theo tốc độ tiêu budget

Khi burn-rate alert kích hoạt:

1. **Xác nhận user impact:** SLI nào giảm, operation/region/tenant nào, bao nhiêu request hoặc workflow bị ảnh hưởng.
2. **Kiểm tra thay đổi gần đây:** deploy, config, feature flag, DB migration, certificate/secret rotation, DNS, provider release.
3. **Giới hạn blast radius:** rollback/canary stop/flag off nếu an toàn; giảm retry, load shed, circuit breaker.
4. **Phân biệt nguyên nhân:** upstream/downstream, DB saturation, message lag, auth failures, timeout.
5. **Điều phối owner:** gọi đúng service owner và platform/dependency owner.
6. **Theo dõi burn phục hồi:** xác minh error rate và SLI quay về baseline, không chỉ pod Healthy.
7. **Kiểm tra hậu quả bất đồng bộ:** backlog, pending operations, DLQ, side effects trùng, dữ liệu không nhất quán.
8. **Ghi sự kiện và quyết định phát hành:** phiên bản nào bị dừng, điều kiện resume là gì.

Một lỗi nặng đã dừng có thể vẫn khiến rolling budget âm. Trong incident review, phải mô tả cả *đã dừng tiêu budget nhanh chưa* và *đã xây được biện pháp chống tái phát chưa*.

Không chờ budget về 0% rồi mới xử lý một sự cố hiện hành có tốc độ tiêu rất cao.

## 26. Error-budget review và postmortem không đổ lỗi

Error budget dùng tốt nhất trong một quy trình review định kỳ:

```text
SLO results for last 30 days
          |
          v
Top user-impact incidents
          |
          v
What exhausted budget?
          |
          v
Action items by risk reduction
          |
          v
Release policy for next iteration
          |
          v
Owner + deadline + verification
```

Một phiên review có thể hỏi:
- Những incident nào tiêu nhiều budget nhất?
- Phần bao nhiêu xuất phát từ thay đổi mới, phần nào từ dependency/hạ tầng/capacity?
- SLI có phản ánh đúng trải nghiệm người dùng không?
- Tín hiệu burn rate có báo kịp không?
- Guardrail nào thiếu: contract tests, canary, rollback, monitoring, timeout, idempotency?
- Cần cải thiện latency tail hay availability hay correctness?
- Sau mitigation, test nào chứng minh lỗi không tái phát?
- Những việc reliability nào nên ưu tiên trước feature release tiếp theo?

Không cần “phạt” team vì sử dụng error budget cho một đổi mới có giá trị trong phạm vi được chấp nhận. Cần học từ lỗi, giảm xác suất và blast radius, đồng thời giữ trách nhiệm minh bạch về user impact.

## 27. Chi phí cơ hội: đầu tư độ tin cậy nào mang lại nhiều giá trị?

Khi budget thấp, không phải tất cả công việc reliability đều có hiệu quả như nhau.

Ví dụ:
- Bổ sung timeout end-to-end có thể ngăn thread pool bị giữ khi provider chậm.
- Tách bulkhead cho API Recommendations tránh làm hỏng Checkout.
- Tối ưu query DB giảm p99 và connection saturation.
- Cải thiện automatic rollback giảm thời gian incident từ 20 phút xuống 3 phút.
- Thêm idempotency/reconciliation giảm lỗi charge trùng.
- Cải thiện alert burn-rate giúp phát hiện sự cố nhanh hơn.
- Chuyển notification sang async nếu nghiệp vụ không cần đồng bộ.
- Kiểm thử migration trước rollout tránh outage toàn bộ consumer.

Để chọn, đánh giá:
1. Tần suất failure mode.
2. Blast radius và mức nghiêm trọng.
3. Thời gian phát hiện/phục hồi hiện tại.
4. Khả năng giảm bad events dự kiến.
5. Chi phí phát triển, vận hành và độ phức tạp mới.
6. Rủi ro do chính thay đổi reliability mang lại.

Đừng mặc định mỗi lần budget cạn phải “làm thêm một tuần infrastructure”. Hãy ưu tiên hành động dựa trên sự cố gây user impact thật và đo kết quả sau triển khai.

## 28. Khi thay đổi nhằm nâng reliability cũng có rủi ro

Một bản fix circuit breaker có thể vô tình mở breaker quá sớm; một migration index có thể khóa bảng; một thay đổi timeout có thể khiến nhiều request bị từ chối. Vì vậy “reliability change” không được miễn kiểm thử và canary.

Một policy trưởng thành phân biệt **mục đích** và **rủi ro thực thi**:
- Chấp nhận fast-track một fix làm giảm incident đang diễn ra.
- Đòi test/fallback/rollback tương xứng với blast radius.
- Nếu không thể rollback do schema, cần forward-fix hoặc migration strategy.
- Theo dõi SLI sau thay đổi, không kết luận thành công vì PR được merge.
- Có owner và escalation nếu fix làm burn rate cao hơn.

Tốc độ thay đổi trong giai đoạn cạn budget không nhất thiết về 0; nó nên chuyển trọng tâm sang **thay đổi có lợi ích reliability cao và rủi ro được kiểm soát**.

## 29. Thay đổi nhiều service: không nên khóa cả tổ chức bằng một SLO

Nếu Payments đang tiêu budget nghiêm trọng nhưng Docs Service có SLO khỏe, việc cấm mọi release toàn công ty có thể không cần thiết. Ngược lại, nếu nhiều service chia sẻ chung một deployment platform đang lỗi, phát hành bất kỳ service nào dùng platform đó đều có rủi ro.

Một policy theo **blast radius và dependency graph**:
- Gắn SLO policy cho service hoặc user journey cụ thể.
- Nếu dependency chung suy giảm, áp guardrail cho những service thực sự phụ thuộc.
- Các thay đổi không ảnh hưởng đường lỗi có thể tiếp tục với bằng chứng phù hợp.
- Đổi shared library, API Gateway, service mesh hoặc DB schema cần phạm vi review rộng hơn.
- Không làm ngơ lỗi Journey SLO chỉ vì từng service SLO riêng còn đạt.
- Khuyến khích service ownership nhưng duy trì incident coordination liên nhóm.

Một change an toàn ở service A có thể vẫn tăng tải vào dependency B đang bão hòa; “A có budget khỏe” không đủ để bỏ đánh giá hệ thống.

## 30. Rolling deploy, contract và budget

Independent deployment có ích cho velocity, nhưng môi trường thực có old/new service versions đồng thời:

```text
Checkout v2 → Payment v1   (trong canary)
Checkout v2 → Payment v2   (sau provider rollout)
Checkout v1 → Payment v2   (khi rollback)
```

Nếu API/event contract không tương thích, chỉ một đợt rollout có thể tiêu nhiều budget trong vài phút. Vì vậy:
- Contract tests nên chạy giữa các version được hỗ trợ.
- Schema migration theo expand–migrate–contract.
- Feature flag kiểm soát thời điểm phát ra field/enum mới.
- Canary có đủ lưu lượng đại diện cho các consumer.
- Rollback được kiểm tra với dữ liệu/event đã phát.
- Release records ghi image digest, schema version và producer/consumer versions.
- SLO monitoring phân theo deployment version/cohort khi có đủ cardinality budget.

Đừng coi “một commit green” đồng nghĩa “an toàn deploy 100%”. CI chứng minh một số tính chất; error budget và canary giúp quan sát hành vi hệ thống thật.

## 31. Rủi ro đo lường: metric đẹp không có nghĩa hệ thống tốt

Một số anti-pattern làm số liệu mất giá trị:

**Loại 5xx khỏi denominator:** số request ít hơn và tỷ lệ good có thể tăng giả tạo.

**Chỉ đo backend:** gateway hoặc DNS lỗi khiến client không tới được backend, SLI backend vẫn đẹp.

**Chỉ đo average latency:** p99 có thể tệ dù average tốt.

**Tính HTTP 200 là thành công tuyệt đối:** workflow chưa hoàn tất hoặc dữ liệu sai vẫn làm người dùng thất bại.

**Bỏ qua một tenant bị lỗi:** aggregation toàn hệ thống che nhóm nhỏ bị ảnh hưởng nghiêm trọng.

**Chỉ báo budget remaining:** không thấy incident đang đốt budget rất nhanh.

**Cấm release khi thiếu metrics mà không có phương án xử lý:** telemetry outage cần trạng thái “unknown” và quy trình ra quyết định có guardrail, không tự coi là good hay bad tùy tiện.

**Đổi định nghĩa SLI sau incident để “lấy lại budget”:** phá lòng tin của chính sách. Nếu định nghĩa sai thật, cần versioning, ghi rõ thời điểm và điều chỉnh minh bạch.

**Dùng budget để xếp hạng cá nhân:** khuyến khích giấu incident và làm lệch phân loại lỗi.

Mục tiêu là đo trải nghiệm người dùng và điều chỉnh rủi ro, không tạo một bảng điểm đẹp.

## 32. Một mẫu SLO và error-budget policy bằng Markdown

```markdown
# SLO: Checkout API

Owner: Commerce Platform / Checkout
Service: checkout-api
SLI:
  Good = eligible checkout request hoàn tất đúng hợp đồng
         trong <= 2 giây
  Bad  = timeout, 5xx, sai business outcome, hoặc chậm hơn 2 giây
Population:
  Các checkout requests từ người dùng hợp lệ tại API edge
  theo quy định, trừ invalid client requests được loại rõ ràng
Target: 99,9%
Window: rolling 30 days
Error allowance: 0,1% eligible requests

Alert policy:
  Fast burn: 14,4 qua 1h AND 5m -> page
  Slow burn: 6 qua 6h AND 30m -> page/ticket theo mức ảnh hưởng

Release policy:
  - Normal: SLO khỏe, không có burn alert nghiêm trọng
  - Caution: budget giảm nhanh -> canary nhỏ + xem xét release
  - Restricted: budget gần/cạn -> hoãn thay đổi rủi ro không thiết yếu
  - Exceptions: urgent security/reliability fixes được review riêng

Data sources:
  Edge request metrics
  Checkout workflow business metrics
  Distributed traces
Runbook:
  Link tới dashboard, canary stop và rollback procedure
```

Mẫu minh họa, cần bổ sung owner cụ thể, endpoint, query logic, evidence và version. **Dấu AND của alert cần phản ánh hai cửa sổ cùng vượt ngưỡng** và phù hợp traffic, không triển khai y nguyên khi chưa kiểm tra telemetry.

## 33. Bài tập thực hành

### Bài 1 — Tính ngân sách theo request

SLO = 99,9%, cửa sổ có 12.000.000 eligible requests và 7.200 bad requests. Tính allowed bad requests, phần budget đã tiêu, phần còn lại và giải thích vì sao trạng thái budget chưa đủ để kết luận nên rollout.

### Bài 2 — Tính theo thời gian

SLO time-based 99,95% trong 30 ngày. Tính ngân sách downtime theo phút. Giải thích vì sao không thể chuyển trực tiếp số phút này thành số HTTP request lỗi nếu không biết traffic distribution.

### Bài 3 — Burn rate

Với SLO 99,9%, error rate trong 1 giờ qua là 1,44%. Tính burn rate và ước lượng phần budget 30 ngày tiêu trong 1 giờ nếu traffic đều. Hãy so sánh với alert có cửa sổ ngắn 5 phút nhưng error rate đã trở lại bình thường.

### Bài 4 — SLI đúng cho async

Shipment workflow nhận request và trả 202, sau đó consumer xử lý trong tối đa 2 phút. Định nghĩa good/bad events theo operation deadline, tránh tính 202 là hoàn tất nghiệp vụ. Nêu cách đo backlog age và late completion.

### Bài 5 — Ra quyết định release

Checkout còn 8% budget, burn rate 6h là 7, Payments vừa có outage. Team đề xuất release refactor pricing lớn. Hãy đưa quyết định có điều kiện và nêu những bằng chứng cần xem trước canary.

### Bài 6 — Ngoại lệ hợp lý

Budget đã âm nhưng certificate TLS của Gateway sẽ hết hạn trong hai ngày. Hãy lập kế hoạch staged certificate rotation, trust validation, canary, monitoring và owner thay vì hoãn mọi thay đổi.

### Bài 7 — Multi-service journey

Gateway, Orders và Payments đều đạt SLO riêng nhưng checkout user journey không đạt. Nêu ít nhất ba nguyên nhân có thể xảy ra, thiết kế SLI ở edge và phân tích correlation giữa các service.

### Bài 8 — Dashboard sai

Một dashboard chỉ hiển thị uptime pod và HTTP 200 của Checkout backend. Người dùng vẫn báo không thể thanh toán. Hãy bổ sung các tín hiệu và điều kiện good event thực sự.

### Bài 9 — Canary giảm blast radius

New deployment có thể gây tăng timeout ở 5% traffic. Thiết kế metric theo cohort, thời gian quan sát, tiêu chí rollback và cách tính bad events phát sinh từ canary trong budget chung.

### Bài 10 — Chính sách tổ chức

Viết policy ngắn cho 3 trạng thái normal/caution/restricted. Xác định owner, release exceptions, rollback authority, metrics tối thiểu và cơ chế review định kỳ không đổ lỗi.

## 34. Ghi nhớ

- **SLI đo chất lượng thực; SLO đặt mục tiêu; error budget đo khoảng sai lệch được chấp nhận trong cửa sổ.**
- **Error budget giúp quyết định đánh đổi giữa đổi mới và reliability**, không phải giấy phép cố ý gây lỗi.
- **Request-based và time-based budgets không hoán đổi tùy tiện**; luôn nêu denominator và cửa sổ đo.
- **Burn rate là tốc độ tiêu budget, không phải số budget còn lại.** Phải xem cả hai để phản ứng kịp.
- **Alert multi-window** giúp phân biệt incident đột ngột với lỗi kéo dài; cần điều chỉnh theo traffic và hành vi thực tế.
- **Release policy phải được thống nhất trước incident** và có ngoại lệ rõ cho security/reliability fixes.
- **Canary, feature flags, rollback và contract compatibility** giảm rủi ro mỗi thay đổi; không thay thế đúng đắn của business logic.
- **SLO theo hành trình người dùng có thể khác SLO từng service**, nhất là khi có timeout bắc cầu và dependency chung.
- **Mục tiêu không phải 100% uptime bằng mọi giá**, mà là mức chất lượng người dùng cần với tốc độ cải tiến bền vững.
- **Dùng incident và budget review để học và đầu tư vào reliability**, không để trừng phạt cá nhân hay che giấu sự cố.

### Tài liệu tham khảo

- Google SRE Book — Service Level Objectives: https://sre.google/sre-book/service-level-objectives/
- Google SRE Book — Embracing Risk: https://sre.google/sre-book/embracing-risk/
- Google SRE Workbook — Implementing SLOs: https://sre.google/workbook/implementing-slos/
- Google SRE Workbook — Alerting on SLOs: https://sre.google/workbook/alerting-on-slos/
- Google SRE Workbook — Error Budget Policy: https://sre.google/workbook/error-budget-policy/
- Prometheus — Querying Functions: https://prometheus.io/docs/prometheus/latest/querying/functions/
- OpenTelemetry — Metrics: https://opentelemetry.io/docs/concepts/signals/metrics/
- Kubernetes — Deployments: https://kubernetes.io/docs/concepts/workloads/controllers/deployment/

Các công thức, ví dụ số và chính sách phát hành trong bài dùng để mô tả nguyên tắc. Khi áp dụng cần kiểm chứng SLI specification, traffic distribution, PromQL/query semantics và nhu cầu vận hành của hệ thống thực tế trước khi dùng làm production gate.
