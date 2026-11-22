# Đánh giá false positive và alert fatigue

## 1. Vì sao chất lượng alert quan trọng?

Một hệ thống monitoring có thể phát hiện rất nhiều sự kiện nhưng vẫn không giúp đội vận hành xử lý rủi ro tốt hơn. Nếu mỗi lần user nhập sai mật khẩu đều tạo một page Critical, nếu một đợt retry tạo hàng nghìn thông báo giống nhau hoặc nếu alert không nói rõ principal, endpoint và hành động cần kiểm tra, người trực sẽ dần bỏ qua cảnh báo.

False positive là cảnh báo được kích hoạt nhưng sau điều tra không có hành vi hoặc điều kiện rủi ro mà detection định tìm. Alert fatigue là trạng thái đội vận hành bị quá tải bởi cảnh báo quá nhiều, lặp lại, thiếu ngữ cảnh hoặc không thể hành động. Hai vấn đề liên quan nhưng không đồng nhất: một alert có thể đúng nhưng vẫn gây fatigue nếu bị gửi lặp, có severity quá cao hoặc không có owner.

Trong bảo mật API, các status 401, 403, 404 và 429 thường xuất hiện trong hoạt động hợp lệ. Một client hết hạn token, một user truy cập nhầm object, một mobile app cũ gọi route đã retire hoặc một tenant chạm quota có thể tạo hàng loạt event. Nếu detection không xét ngữ cảnh, các sự kiện này sẽ bị hiểu nhầm là credential stuffing, BOLA/IDOR probing, endpoint scanning hoặc abuse.

Trong phạm vi **SECURITY_API_SECURITY**, mục tiêu là duy trì detection đủ nhạy với hành vi nguy hiểm nhưng vẫn có tỷ lệ cảnh báo hữu ích cao. Cần đo chất lượng, thu feedback từ triage, điều chỉnh logic có kiểm soát và giữ khả năng phát hiện các tình huống ít xảy ra nhưng tác động lớn.

Sau bài học này, người học có thể:

1. Phân biệt false positive, false negative, duplicate alert và alert không actionable.
2. Đo precision, recall và các chỉ số chất lượng vận hành.
3. Phân loại nguyên nhân false positive theo route, principal, tenant, client và thay đổi hệ thống.
4. Điều chỉnh threshold, time window, baseline, correlation và severity.
5. Dùng deduplication, grouping, inhibition và suppression đúng phạm vi.
6. Quản lý exception/allowlist có owner, scope và expiry.
7. Đánh giá detection bằng historical replay, backtest, shadow mode và test case.
8. Thiết lập feedback loop để giảm alert fatigue mà không làm mù hệ thống.

## 2. Phân biệt false positive, false negative và alert noise

Các khái niệm này cần được phân biệt trước khi tuning.

| Khái niệm | Ý nghĩa | Ví dụ trong API security |
|---|---|---|
| True positive (TP) | Alert phát hiện đúng hành vi cần điều tra | Một principal thử truy cập nhiều tenant/object ngoài scope |
| False positive (FP) | Alert kích hoạt nhưng không có hành vi mục tiêu | Batch job hợp lệ tạo spike 404 đã biết |
| False negative (FN) | Hành vi nguy hiểm xảy ra nhưng detection không cảnh báo | Attacker phân tán credential stuffing dưới threshold từng IP |
| True negative (TN) | Không có hành vi mục tiêu và không phát alert | Traffic bình thường không kích hoạt detection |
| Duplicate alert | Nhiều alert cùng phản ánh một incident | Mỗi pod gửi cùng alert cho một đợt 401 |
| Non-actionable alert | Alert có thể đúng về mặt metric nhưng không gợi ý hành động hữu ích | “403 tăng” không có route, owner, principal cohort hoặc runbook |
| Alert noise | Tổng hợp các thông báo ít giá trị, lặp hoặc không cần phản ứng | Warning lặp liên tục khi quota bình thường bị chạm |

Một false positive không nhất thiết có nghĩa metric sai. Có thể metric ghi đúng 401 nhưng detection diễn giải sai thành brute force. Một duplicate alert có thể là true positive nhưng vẫn làm tăng noise. Một alert non-actionable có thể không được phân loại FP/FN vì nó không có mục tiêu phát hiện đủ rõ.

### 2.1. Phân biệt false positive rate và false discovery rate

Trong thống kê:

\[
FPR = \frac{FP}{FP + TN}
\]

Đây là tỷ lệ trường hợp âm tính bị phân loại nhầm thành dương tính. Trong vận hành alert, đội thường quan tâm thêm:

\[
FDR = \frac{FP}{TP + FP}
\]

FDR là tỷ lệ alert được điều tra nhưng không xác nhận hành vi mục tiêu. Nhiều dashboard gọi nhầm FDR là “false positive rate”. Khi báo cáo, ghi rõ mẫu số và định nghĩa.

Precision:

\[
Precision = \frac{TP}{TP + FP}
\]

Recall:

\[
Recall = \frac{TP}{TP + FN}
\]

Precision cao giúp giảm alert không hữu ích. Recall cao giúp ít bỏ sót hành vi mục tiêu. Không nên tối ưu một chỉ số riêng lẻ: detection có precision 100% nhưng chỉ phát hiện một phần rất nhỏ cuộc tấn công vẫn có thể không đạt mục tiêu.

### 2.2. Không thể đo recall chỉ từ alert đã phát

Muốn biết false negative, cần nguồn evidence độc lập với detection: incident đã xác nhận, red-team exercise, replay dữ liệu có nhãn, threat simulation hoặc kiểm tra thủ công có phương pháp.

Nếu chỉ nhìn các alert đã được phát, bạn biết một phần precision nhưng không biết các cuộc tấn công mà hệ thống không báo. Không coi “không có alert” là bằng chứng “không có tấn công”.

## 3. Alert fatigue hình thành như thế nào?

Alert fatigue thường tích lũy qua nhiều vòng:

1. Detection được triển khai với threshold quá thấp.
2. Traffic hợp lệ tạo nhiều alert.
3. Alert không có context nên tốn thời gian điều tra.
4. Cùng một sự kiện tạo alert từ nhiều instance hoặc nhiều rule.
5. On-call bắt đầu acknowledge nhanh, defer hoặc mute.
6. Alert thật xuất hiện trong cùng kênh và bị bỏ qua.
7. Thời gian phát hiện và phản ứng với incident tăng lên.

Dấu hiệu trong vận hành:

- Nhiều alert bị đóng với lý do “expected behavior” hoặc “known noise”.
- Alert bị acknowledge nhưng không có investigation hoặc ticket.
- Một rule thường xuyên bị mute hoặc silence dài hạn.
- On-call không biết owner của rule.
- Nhiều alert trùng cùng service, route hoặc principal.
- Alert Critical nhưng không có impact hoặc confidence rõ.
- Tỷ lệ page ngoài giờ tăng mà số incident xác nhận không tăng.
- Đội ngũ chuyển thông báo sang channel ít được theo dõi.
- Runbook không còn đúng với kiến trúc hiện tại.

Fatigue không chỉ là vấn đề trải nghiệm. Nó làm giảm xác suất người trực nhận ra tín hiệu quan trọng, kéo dài dwell time và khiến các biện pháp bảo vệ mất hiệu quả thực tế.

## 4. Đặt mục tiêu chất lượng trước khi tuning

Mỗi detection rule cần mô tả hành vi cần phát hiện và hành động mà alert phải dẫn tới.

Ví dụ:

| Detection | Mục tiêu | Hành động mong đợi |
|---|---|---|
| Credential stuffing | Nhiều account bị thử credential trong một pattern đáng ngờ | Xác minh source/client, success sau failure, bảo vệ account |
| BOLA probing | Một principal thử nhiều object/tenant ngoài scope | Kiểm tra object access, principal và side effect |
| Route scanning | Một nguồn dò nhiều route không tồn tại | Xác minh scanner, WAF/gateway logs và endpoint exposure |
| Retry storm | Client retry liên tục sau 429 | Xác định client/version, sửa backoff và bảo vệ capacity |
| Authorization regression | Nhiều user hợp lệ bị deny sau deploy | Kiểm tra policy/config và rollback nếu cần |

Trước khi chọn threshold, hãy trả lời:

- Alert đại diện cho một request, một principal, một campaign hay một incident?
- Ai chịu trách nhiệm điều tra?
- Cần context nào để xác nhận hoặc loại trừ?
- Hành động nào có thể thực hiện an toàn?
- Alert cần page ngay hay chỉ tạo ticket/dashboard signal?
- Điều kiện nào để resolve?
- Detection có thể bỏ sót kiểu tấn công nào?

Nếu chưa trả lời được các câu hỏi này, rule có thể chưa đủ rõ để gửi page.

## 5. Phân loại nguyên nhân false positive

Không nên sửa threshold ngay khi một alert bị đóng là false positive. Trước hết xác định nguyên nhân.

Các nhóm phổ biến:

| Nhóm nguyên nhân | Ví dụ | Cách xử lý thường phù hợp |
|---|---|---|
| Baseline không phù hợp | Batch cuối tháng tạo nhiều 404 | Baseline theo lịch/route |
| Threshold quá thấp | Một vài 401 tạo page | Kết hợp count, rate và minimum volume |
| Context thiếu | Không phân biệt human user với service account | Thêm principal type/client context |
| Route classification sai | 404 object bị gộp với route scan | Chuẩn hóa outcome/reason code |
| Correlation yếu | Một IP NAT bị coi là một attacker | Kết hợp principal, client và network |
| Deploy/config change | JWKS rotation gây 401 đồng loạt | Correlate release và identity events |
| Client behavior | Retry ngay sau 429 | Sửa client backoff, nhận diện retry sequence |
| Duplicate emission | Nhiều pod gửi cùng event | Dedup theo fingerprint/campaign |
| Exception thiếu hạn | Automation cũ luôn bị allowlist | Thêm owner, expiry và review |
| Detection bug | Metric đếm hai lần ở gateway và app | Sửa instrumentation/canonical source |

### 5.1. Ghi nguyên nhân bằng taxonomy ổn định

Dùng các reason code có tập giá trị quản lý được, ví dụ:

- `EXPECTED_BATCH_TRAFFIC`
- `STALE_CLIENT`
- `IDP_OR_KEY_ROTATION`
- `SHARED_NAT`
- `POLICY_REGRESSION`
- `DUPLICATE_EVENT`
- `THRESHOLD_TOO_LOW`
- `ROUTE_CLASSIFICATION_ERROR`
- `AUTHORIZED_AUTOMATION`
- `UNKNOWN_NEEDS_REVIEW`

Không cho phép người triage chỉ ghi “noise” mà không có chi tiết. Nếu chưa rõ, dùng `UNKNOWN_NEEDS_REVIEW` và tạo follow-up để tìm nguyên nhân.

### 5.2. Phân biệt expected với acceptable

Một automation đã đăng ký có thể tạo traffic lặp, nhưng không có nghĩa mọi hành vi của nó đều an toàn. Một service account hợp lệ vẫn có thể bị compromise hoặc cấu hình sai.

Không biến “known client” thành miễn trừ toàn diện. Exception nên giới hạn đúng route, action, principal và behavior đã xác minh.

## 6. Thu feedback từ quá trình triage

Triage là nguồn dữ liệu quan trọng để cải thiện detection. Mỗi alert được xử lý nên tạo feedback có cấu trúc.

Các trường nên ghi:

- Alert/rule ID và version.
- Thời gian, service, route template và environment.
- Severity lúc phát.
- Outcome: confirmed, false positive, duplicate, expected, inconclusive.
- Reason code.
- Principal/client/tenant reference đã pseudonymize.
- Evidence đã xem.
- Hành động thực hiện.
- Thời gian điều tra.
- Có cần sửa rule hoặc runbook không.
- Người review và thời điểm.

### 6.1. Không ép mọi alert thành true hoặc false

Có các trường hợp:

- Chưa đủ evidence.
- Alert phát hiện behavior lạ nhưng không chứng minh malicious.
- Hành vi hợp lệ nhưng vẫn có rủi ro cấu hình.
- Nhiều alert thuộc một incident.
- Alert đúng về service health nhưng không phải security incident.

Dùng trạng thái `inconclusive` hoặc `needs_follow_up`. Ép phân loại sai làm dữ liệu huấn luyện/tuning kém chất lượng.

### 6.2. Giữ nguyên evidence khi điều chỉnh

Trước khi sửa rule, lưu lại query, event sample, threshold hiện tại và khoảng thời gian bị ảnh hưởng. Điều này cho phép replay để biết thay đổi có giảm noise mà không làm mất detection thật hay không.

Không chỉ dựa vào trí nhớ người trực hoặc ghi chú trong chat. Lưu feedback vào hệ thống ticket/case hoặc detection repository theo quy trình của đội.

## 7. Đo lường chất lượng alert

Một dashboard chất lượng nên kết hợp metric thống kê và metric vận hành.

| Metric | Cách tính/góc nhìn | Ý nghĩa |
|---|---|---|
| Precision | TP / (TP + FP) | Tỷ lệ alert xác nhận đúng |
| Recall | TP / (TP + FN) | Mức bao phủ hành vi mục tiêu |
| False discovery rate | FP / tổng alert đã phân loại | Phần alert không xác nhận |
| Actionable alert ratio | Alert có action/evidence/owner / tổng alert | Alert có thể xử lý |
| Duplicate ratio | Alert duplicate / tổng alert | Mức lặp thông báo |
| Alert volume | Alert theo rule/service/severity/time | Tải cho on-call |
| Acknowledge time | Từ phát alert tới acknowledge | Khả năng tiếp nhận |
| Triage duration | Từ mở tới phân loại | Chi phí điều tra |
| Escalation rate | Alert cần chuyển cấp / tổng alert | Độ phù hợp severity |
| Reopen rate | Case đã đóng phải mở lại | Chất lượng triage/resolve |
| Suppression rate | Event bị suppress / event đủ điều kiện | Mức lọc và nguy cơ che mất tín hiệu |
| Missed detection | Incident/test không có alert tương ứng | Khoảng trống detection |

### 7.1. Phân tích theo rule, không chỉ tổng hệ thống

Precision toàn hệ thống có thể che giấu một rule rất noisy. Đo theo rule ID/version, severity, service và use case. Với sample nhỏ, hiển thị số lượng mẫu cùng khoảng tin cậy thay vì chỉ đưa phần trăm.

### 7.2. Cẩn thận với số liệu “false positive”

Một alert bị đóng do không tìm thấy bằng chứng không nhất thiết là false positive. Có thể log thiếu, retention ngắn hoặc detection context không đủ. Tách `false_positive_confirmed` khỏi `inconclusive`.

### 7.3. Đo thời gian theo mức độ nghiêm trọng

Không nên giảm acknowledge time bằng cách khuyến khích acknowledge mọi alert ngay. Theo dõi time-to-triage và time-to-action theo severity; kiểm tra alert có được điều tra đúng hay chỉ được acknowledge để dọn queue.

## 8. Tuning threshold bằng nhiều tín hiệu

Threshold quá thấp tạo noise; threshold quá cao làm tăng false negative. Thường cần kết hợp:

- Absolute count.
- Request rate.
- Error ratio.
- Distinct principal/account/object count.
- Thay đổi so với baseline.
- Thời gian kéo dài.
- Route/action sensitivity.
- Correlation với các event khác.

Ví dụ, thay vì page khi có bất kỳ 401 nào, một rule credential abuse có thể yêu cầu đồng thời:

1. Số lần authentication failure vượt mức tối thiểu.
2. Nhiều account distinct bị thử.
3. Rate tăng so với baseline của login endpoint.
4. Pattern xảy ra trong một cửa sổ thời gian ngắn.
5. Không trùng với IdP outage hoặc rollout đã biết.

Các ngưỡng cụ thể phải dựa trên traffic thật và threat model. Không sao chép một con số chung sang mọi service.

### 8.1. Absolute threshold và relative threshold

Absolute threshold giúp phát hiện volume đủ lớn ngay cả khi baseline thấp. Relative threshold phát hiện mức tăng so với hành vi bình thường.

Dùng cả hai khi phù hợp. Ví dụ một route ít traffic có thể tăng từ 1 lên 10 request, tương đương 10 lần nhưng chưa chắc cần page; một route lớn có thể tăng 20% và tạo hàng nghìn deny, rất đáng chú ý.

### 8.2. Minimum sample size

Tỷ lệ 403 là 100% khi có một request và một request bị deny. Không nên page chỉ từ tỷ lệ này.

Yêu cầu minimum request volume hoặc minimum event count trước khi áp dụng ratio threshold. Với endpoint cực kỳ nhạy cảm, một event có thể vẫn tạo high-priority signal, nhưng cần rule riêng dựa trên hành động/identity cụ thể thay vì ratio tổng quát.

### 8.3. Time window và persistence

Cửa sổ quá ngắn dễ phản ứng với burst hợp lệ; cửa sổ quá dài làm detection chậm và gộp nhiều behavior không liên quan.

Có thể dùng:

- Short window để phát hiện burst.
- Longer window để phát hiện low-and-slow behavior.
- `for` duration để yêu cầu condition tồn tại.
- Cooldown để tránh page lặp sau khi đã mở incident.

Không dùng `for` dài để che một spike có tác động tức thời. Chọn window theo tốc độ tấn công và thời gian phản ứng cần thiết.

### 8.4. Threshold theo route và principal type

Một endpoint login, export, admin và search có baseline khác nhau. Human user, service account, API key và anonymous traffic cũng khác nhau.

Tạo cohort đủ cụ thể để so sánh có ý nghĩa nhưng tránh chia quá nhỏ khiến sample không đủ. Khi traffic ít, fallback sang baseline của nhóm route/service tương đồng.

## 9. Baseline động và anomaly detection

Baseline động giúp phát hiện traffic thay đổi theo giờ/ngày, nhưng có thể tự thích nghi với hành vi xấu.

Các kỹ thuật thường dùng:

- Rolling mean/median.
- Percentile theo time bucket.
- Exponentially weighted moving average (EWMA).
- Seasonal baseline theo giờ và ngày.
- Median absolute deviation (MAD).
- Anomaly score từ model đã được kiểm định.

### 9.1. Không để attack poison baseline

Nếu model liên tục học từ traffic hiện tại, một cuộc tấn công kéo dài có thể dần được xem là bình thường. Cần:

- Dùng dữ liệu baseline được review.
- Giới hạn tốc độ update.
- Loại trừ hoặc gắn nhãn incident window.
- Có ngưỡng tuyệt đối cho hành vi nghiêm trọng.
- Review drift và baseline version.
- Có rollback khi model thay đổi bất thường.

### 9.2. Kết hợp anomaly score với rule rõ ràng

Anomaly score nên là một tín hiệu hỗ trợ. Với quyết định page hoặc auto-containment, cần feature có thể giải thích, ngưỡng đã kiểm định và bằng chứng cụ thể.

Một alert “anomaly score 0.97” không đủ cho người trực nếu không biết route, principal cohort, baseline, volume và điều gì đã thay đổi.

### 9.3. Không dùng model như allow/deny policy

Detection anomaly không thay authorization. Không tự động mở quyền hoặc bỏ qua rate limit vì model đánh giá traffic “bình thường”. Enforcement vẫn phải dựa trên policy rõ ràng.

## 10. Correlation để giảm noise mà không bỏ sót

Một số alert riêng lẻ có thể được gộp thành một incident khi chúng cùng phản ánh một campaign hoặc một nguyên nhân.

Ví dụ:

- Nhiều 401 từ cùng client, sau đó một login success.
- Nhiều 403/404 trên cùng object route từ một principal.
- Nhiều 429 từ cùng API key do retry loop.
- Nhiều service cùng báo 401 sau một JWKS rotation.
- Nhiều 404 route cũ sau một frontend deployment.

Correlation key có thể gồm:

- Rule/use case.
- Service và route template.
- Principal/client reference.
- Tenant cohort.
- Source network/ASN ở mức phù hợp.
- Policy/release version.
- Time window.

Không correlation chỉ theo IP. Một IP NAT có thể đại diện cho hàng nghìn người dùng; một attacker có thể thay đổi IP liên tục.

### 10.1. Correlation theo cause và campaign

Phân biệt một nguyên nhân chung (IdP outage, config deploy) với một campaign (credential stuffing, enumeration). Cùng một status spike có thể cần hai loại incident khác nhau: reliability incident cho diện rộng và security investigation cho các principal có pattern đáng ngờ.

### 10.2. Không gộp mất phạm vi ảnh hưởng

Nếu một alert liên quan nhiều tenant hoặc service, giữ danh sách affected scope trong case metadata. Grouping giúp giảm thông báo nhưng không được làm mất evidence cần containment riêng.

## 11. Deduplication và grouping

Deduplication loại bỏ thông báo lặp của cùng một alert instance. Grouping gom nhiều alert có liên quan thành một notification hoặc incident.

Ví dụ Alertmanager:

```yaml
route:
  receiver: default
  group_by:
    - alertname
    - service
    - route
  group_wait: 30s
  group_interval: 5m
  repeat_interval: 4h

receivers:
  - name: default
    # Configure the actual notification integration here.
```

Cấu hình chỉ minh họa grouping. Cần thiết kế label ổn định và tránh đưa raw user ID, token, object ID vào group key.

### 11.1. Chọn group key phù hợp

- Group theo service/route cho spike cùng endpoint.
- Group theo principal reference khi điều tra một identity.
- Group theo client/policy khi một integration gây retry storm.
- Group theo incident/campaign nếu nhiều rule cùng phát hiện một chuỗi.

Nếu group quá rộng, một alert critical có thể bị chôn trong nhóm lớn. Nếu group quá hẹp, một incident tạo hàng nghìn notification.

### 11.2. Dedup fingerprint

Fingerprint nên dựa trên các thuộc tính ổn định của alert, không dùng timestamp hoặc request ID mới cho mỗi event. Nếu fingerprint thay đổi ở mọi request, deduplication sẽ không hoạt động.

Giữ event count, first seen, last seen và representative sample để người điều tra thấy quy mô mà không nhận từng notification.

### 11.3. Repeat notification

Repeat interval quá ngắn gây fatigue; quá dài có thể khiến alert chưa xử lý bị quên. Điều chỉnh theo severity và escalation policy. Incident đang mở có thể cập nhật count/context thay vì gửi lại cùng một page.

## 12. Suppression, inhibition và maintenance window

Các cơ chế này có mục đích khác nhau:

- **Suppression:** tạm không phát notification cho một điều kiện đã xác định.
- **Inhibition:** không gửi alert cấp thấp khi alert cấp cao hơn cùng nguyên nhân đang active.
- **Maintenance silence:** tạm ngừng notification trong một khoảng thời gian đã lên lịch.
- **Deduplication:** loại thông báo lặp của cùng alert instance.

### 12.1. Inhibition theo nguyên nhân

Ví dụ nếu `IdentityProviderDown` đang active, có thể inhibit các alert 401 downstream có cùng issuer/region để tránh hàng trăm page. Tuy nhiên vẫn giữ metric/event và một alert tổng hợp cho impact.

Không inhibit mọi alert 401 toàn hệ thống chỉ vì một IdP incident nếu có route dùng issuer khác hoặc dấu hiệu credential abuse độc lập.

### 12.2. Maintenance window

Maintenance silence cần có:

- Owner.
- Service/route/environment scope.
- Lý do và change/ticket reference.
- Start/end time.
- Alert được silence.
- Người review.
- Hành vi khi maintenance kéo dài quá hạn.

Không silence security detection toàn hệ thống cho một deploy nhỏ. Ưu tiên silence đúng rule/service và giữ detection signal trong dashboard hoặc event store.

### 12.3. Suppression không được xóa evidence

Suppress notification không có nghĩa bỏ event. Giữ metric/log để có thể điều tra lại, đánh giá false negative và biết suppression có che một incident thật hay không.

## 13. Allowlist và exception có kiểm soát

Allowlist thường được dùng cho batch job, scanner nội bộ hoặc integration đã biết. Đây là một trong những nguồn tạo blind spot lớn nếu scope quá rộng hoặc không hết hạn.

Một exception cần có:

- Owner chịu trách nhiệm.
- Principal/client identity đã xác minh.
- Route/method/action cụ thể.
- Behavior được miễn trừ rõ ràng.
- Environment và tenant scope.
- Lý do nghiệp vụ.
- Ngày bắt đầu và expiry.
- Người phê duyệt.
- Cách review và thu hồi.

### 13.1. Tránh allowlist chỉ theo IP

IP có thể dùng chung, thay đổi hoặc được tái sử dụng. Nếu có thể, ưu tiên workload identity, client ID, certificate identity hoặc principal đã xác minh; dùng IP như một thuộc tính bổ sung.

### 13.2. Không miễn trừ toàn bộ status

Một batch client được miễn alert cho 404 trên một route cụ thể không nên tự động được miễn 401, 403 hoặc 429 trên toàn service. Scope exception phải khớp behavior đã xác minh.

### 13.3. Expiry và periodic review

Exception không có expiry sẽ trở thành policy vĩnh viễn. Tự động cảnh báo trước ngày hết hạn; khi hết hạn, rule trở lại behavior mặc định. Gia hạn cần review evidence và owner mới xác nhận.

### 13.4. Known automation vẫn cần phát hiện compromise

Một service account được allowlist có thể bị lộ secret hoặc bị dùng sai. Giữ detection cho hành vi vượt baseline, gọi route nhạy cảm mới, thay đổi source network bất thường hoặc sử dụng credential sau revoke.

## 14. Severity và alert routing

Severity phải phản ánh impact, confidence và urgency, không chỉ status code hoặc số event.

| Mức | Tiêu chí gợi ý | Kênh xử lý |
|---|---|---|
| Critical | Có bằng chứng compromise, access trái phép hoặc credential revoked vẫn tạo side effect | Page incident response ngay |
| High | Pattern probing/abuse rõ, có thể ảnh hưởng dữ liệu hoặc service | On-call security/service khẩn |
| Medium | Anomaly đáng điều tra nhưng chưa có bằng chứng compromise | Ticket hoặc on-call theo SLA |
| Low/Info | Expected behavior, client stale hoặc drift nhỏ đã có owner | Dashboard/report định kỳ |

Một alert 401 đơn lẻ không mặc định Critical. Một request thành công truy cập object ngoài tenant có thể cần Critical dù chỉ xảy ra một lần.

### 14.1. Severity theo confidence và impact

Có thể dùng ma trận:

- Impact cao + confidence cao: Critical.
- Impact cao + confidence thấp: High hoặc investigation nhanh để xác minh.
- Impact thấp + confidence cao: Medium/Low tùy khả năng lặp.
- Impact thấp + confidence thấp: dashboard hoặc ticket.

Không hạ severity chỉ vì alert thường xuyên xảy ra. Nếu event lặp thường xuyên nhưng có impact thật, cần xử lý nguyên nhân gốc.

### 14.2. Routing theo owner

Route alert tới team sở hữu service hoặc control đang phát hiện. Security team có thể nhận campaign-level alert; service team nhận regression/availability; platform team nhận gateway/IdP/limiter issue.

Một alert cần một owner chịu trách nhiệm chính và escalation path rõ ràng.

## 15. Thiết kế alert actionable

Một alert tốt cần trả lời:

- Điều gì đã xảy ra?
- Bắt đầu khi nào và kéo dài bao lâu?
- Service/route/method nào bị ảnh hưởng?
- Principal/client/tenant cohort nào liên quan?
- Baseline và threshold là bao nhiêu?
- Count/rate/ratio hiện tại là bao nhiêu?
- Reason code hoặc decision stage nào tăng?
- Có deploy/IdP/policy change liên quan không?
- Có request success hoặc side effect sau failure không?
- Người trực cần làm gì đầu tiên?

Ví dụ nội dung alert:

```text
Title: API object-scope deny spike
Severity: High
Service: orders-api
Route: GET /v1/orders/{orderId}
Window: 10 minutes
Observed: 186 authorization denies
Baseline: 4-12 denies per 10 minutes
Context: 1 verified principal reference, 73 distinct object references,
multiple tenant-scope mismatches
Related signals: no deployment in the window; no IdP incident
First action: inspect the principal's request sequence and confirm
whether any request produced a successful read or business side effect.
Runbook: security/api-object-probing
Owner: orders-api on-call + security response
```

Ví dụ trên dùng số liệu giả định để minh họa format. Alert production cần link tới dashboard/case có access control; không đính kèm token, raw payload hoặc object data nhạy cảm.

### 15.1. Đưa evidence vào alert

Alert có thể chứa vài sample event đã redact, query link và trace ID. Không nhồi toàn bộ log vào notification. Người trực cần xem được bằng một lần mở dashboard với quyền phù hợp.

### 15.2. Có resolve condition

Nêu điều kiện alert tự resolve hoặc cần manual close. Ví dụ rate trở lại baseline trong 15 phút và không có event mới. Với incident security, metric hết spike không đồng nghĩa investigation đã hoàn tất.

## 16. Backtest và historical replay

Trước khi thay threshold hoặc correlation, chạy rule mới trên dữ liệu lịch sử.

Quy trình:

1. Chọn khoảng thời gian có cả traffic bình thường và incident/test đã xác nhận.
2. Chuẩn hóa schema và route labels như production.
3. Chạy rule hiện tại để tạo baseline kết quả.
4. Chạy rule candidate trên cùng dữ liệu.
5. So sánh alert count, confirmed detections, false positives và missed cases.
6. Kiểm tra theo service, route, principal type và tenant cohort.
7. Review những incident candidate không phát hiện.
8. Ghi lại rule version, query, dataset và kết quả.

### 16.1. Dữ liệu lịch sử có giới hạn

Log có thể bị sampling, thiếu principal reference hoặc retention không đủ. Một khoảng thời gian không có incident được xác nhận không phải ground truth âm tính hoàn hảo.

Gắn confidence cho kết quả backtest và ghi rõ phần data coverage. Không báo recall 100% nếu không có nguồn độc lập để xác định false negative.

### 16.2. Replay không tái hiện đầy đủ runtime

Historical replay có thể không mô phỏng đúng alert routing, dedup state, preflight cache, delayed event hoặc clock skew. Dùng replay để kiểm tra detection logic, sau đó test riêng notification pipeline và stateful behavior.

## 17. Shadow mode và rollout có kiểm soát

Khi thay đổi detection lớn, chạy candidate rule ở shadow mode trước khi cho phép page.

Các bước:

- Giữ rule hiện tại làm control.
- Candidate rule phát event/metric nhưng không gửi page.
- So sánh output theo cùng traffic.
- Thu feedback từ analyst.
- Đánh giá FP, FN có bằng chứng, volume và severity.
- Điều chỉnh query và context.
- Chuyển candidate thành active theo từng service/route.
- Theo dõi rollback criteria.

### 17.1. Canary theo phạm vi

Có thể bật rule mới trước cho một service hoặc một nhóm route có telemetry tốt. Không triển khai cùng lúc cho toàn bộ module nếu chưa hiểu tác động.

### 17.2. Giữ rollback đơn giản

Version detection rule trong repository/config, ghi change owner và ngày rollout. Nếu noise tăng đột biến hoặc missed detection được phát hiện, có thể quay về version trước mà không sửa trực tiếp nhiều nơi.

## 18. Kiểm thử detection bằng tình huống có nhãn

Detection cần test positive, negative và edge cases.

| Scenario | Kết quả mong đợi |
|---|---|
| Một user nhập sai password một lần | Không page security |
| Nhiều account bị thử theo pattern credential stuffing | Alert theo threshold/correlation |
| Service account batch tạo 404 đã đăng ký | Không page; vẫn giữ telemetry |
| Một principal thử nhiều object ngoài tenant | Alert BOLA/IDOR probing |
| Frontend gọi route cũ sau deploy | Signal stale client, không mặc định scanner |
| Một client retry ngay sau 429 | Alert retry storm hoặc client behavior |
| IdP outage làm nhiều route 401 | Alert service/identity health, không khóa toàn bộ user |
| Gateway và app cùng ghi một response | Dedup hoặc phân biệt layer |
| Known automation bị dùng từ context mới bất thường | Không được miễn trừ toàn bộ detection |
| Một request đơn lẻ tới endpoint rất nhạy cảm | Rule riêng có thể phát signal theo impact |

### 18.1. Positive test và negative test

Positive test chứng minh hành vi mục tiêu được phát hiện. Negative test chứng minh traffic hợp lệ không tạo page ngoài ý muốn. Cần có cả hai cho mỗi rule.

Không chỉ assert query trả về một số. Test cả severity, routing, grouping, notification content và suppression behavior.

### 18.2. Test regression sau mỗi thay đổi

Khi đổi threshold, label hoặc allowlist, chạy lại bộ test detection. Một thay đổi nhỏ trong route normalization có thể khiến rule không còn match hoặc cardinality tăng mạnh.

## 19. Quản lý alert lifecycle

Alert có vòng đời từ tạo rule tới retirement:

1. Proposed: mục tiêu và owner được xác định.
2. Testing: chạy trên fixture/replay.
3. Shadow: nhận event nhưng chưa page.
4. Active: route tới người trực.
5. Tuning: điều chỉnh theo feedback có version.
6. Deprecated: thay bằng detection mới.
7. Retired: tắt sau khi có bằng chứng và owner sign-off.

Mỗi rule nên có metadata:

- Rule ID và version.
- Use case/threat.
- Data source và required fields.
- Owner và severity.
- Query/threshold.
- Test cases.
- Runbook.
- Exception/suppression policy.
- Last reviewed và next review date.
- Change history.
- Retirement evidence nếu đã tắt.

Không xóa rule noisy ngay khi chưa biết nó có đang bắt một threat hiếm. Chạy candidate replacement hoặc shadow analysis trước khi retire.

## 20. Quy trình xử lý một alert noisy

Ví dụ alert 401 login failure tăng cao mỗi sáng:

1. Xác định spike theo route, time window và client.
2. Kiểm tra 401 có tập trung vào một IdP/client version hay nhiều account.
3. Correlate với token expiry, SSO rollout, deployment và secret rotation.
4. Kiểm tra success sau failure và account/client distinct count.
5. Xem alert có bị đếm trùng ở gateway và application không.
6. Phân loại nguyên nhân: expected rollout, client bug, IdP issue hay credential abuse.
7. Nếu là expected rollout, thêm context hoặc điều chỉnh threshold theo cohort; không allowlist toàn bộ IP.
8. Backtest rule candidate trên cùng thời gian và incident history.
9. Chạy shadow mode để quan sát false positive/false negative.
10. Rollout version mới và theo dõi actionable ratio, alert volume cùng missed test cases.

Kết quả mong đợi là giảm page không cần thiết mà vẫn giữ được detection cho credential abuse và login success đáng ngờ.

## 21. Continuous improvement và review cadence

Alert quality không phải cấu hình một lần. Traffic, client, endpoint, auth provider và threat behavior đều thay đổi.

Một lịch review tham khảo:

| Chu kỳ | Hoạt động |
|---|---|
| Hàng ngày | Review Critical/High, unresolved và alert storm |
| Hàng tuần | Top noisy rules, duplicate ratio, false-positive reason |
| Hàng tháng | Precision, actionability, threshold và exception expiry |
| Sau incident | Kiểm tra detection gap, missed signal và runbook |
| Sau deploy lớn | Kiểm tra baseline drift, route/client changes |
| Theo quý | Review owner, threat coverage, rule retirement và test suite |

### 21.1. Đừng chỉ đặt KPI giảm số alert

Nếu đặt mục tiêu giảm 50% alert mà không đo recall, đội có thể đạt KPI bằng cách tắt detection. KPI nên cân bằng:

- Alert volume và page burden.
- Precision/actionability.
- Recall theo incident/test đã biết.
- Detection coverage theo threat.
- Time-to-triage/action.
- Exception/suppression scope.
- Detection test pass rate.

### 21.2. Tổ chức review không đổ lỗi

False positive là feedback cho chất lượng detection và context. Người triage cần được khuyến khích phân loại trung thực; không phạt vì một alert candidate bị false positive. Tập trung sửa data, rule, runbook và ownership.

## 22. Những lỗi thiết kế thường gặp

1. **Chỉ giảm threshold để hết noise.** Có thể tạo false negative nghiêm trọng.
2. **Chỉ tối ưu precision.** Detection có thể bỏ lỡ threat hiếm.
3. **Gọi mọi alert không xác minh được là false positive.** Thiếu evidence không đồng nghĩa benign.
4. **Không có taxonomy feedback.** Không tìm được nguyên nhân gốc.
5. **Allowlist toàn bộ IP hoặc service account.** Tạo blind spot lớn.
6. **Exception không có expiry.** Miễn trừ tồn tại vô thời hạn.
7. **Dùng một threshold cho mọi route.** Không xét traffic profile.
8. **Dùng ratio với sample nhỏ.** Một request có thể tạo tỷ lệ 100%.
9. **Không deduplicate.** Một incident tạo hàng nghìn page.
10. **Group quá rộng.** Alert quan trọng bị chìm trong nhóm lớn.
11. **Silence toàn bộ security rules trong maintenance.** Có thể bỏ qua incident độc lập.
12. **Suppress và xóa event.** Mất evidence để điều tra và đo FN.
13. **Không backtest.** Không biết thay đổi ảnh hưởng detection cũ thế nào.
14. **Không dùng shadow mode.** Candidate rule lập tức gây noise production.
15. **Anomaly model tự học attack traffic.** Baseline bị poison.
16. **Alert không có owner/runbook.** Người trực không biết làm gì.
17. **Auto-containment chỉ từ một anomaly score.** Có thể khóa user hợp lệ hoặc gây outage.
18. **Đo precision từ alert đã phát nhưng tuyên bố recall cao.** Không có ground truth độc lập.
19. **Chỉ đo tổng alert toàn hệ thống.** Rule noisy bị che khuất.
20. **Tắt rule noisy mà không có replacement.** Threat coverage bị mất.

## 23. Checklist đánh giá false positive và alert fatigue

Trước khi đưa rule vào production hoặc thay đổi rule đang chạy, hãy xác nhận:

- [ ] Mục tiêu phát hiện và hành động mong đợi được mô tả rõ.
- [ ] Có phân biệt TP, FP, FN, duplicate và inconclusive.
- [ ] Có định nghĩa rõ FPR, FDR, precision và recall.
- [ ] Có nguồn evidence độc lập để đánh giá missed detection.
- [ ] Có taxonomy nguyên nhân false positive.
- [ ] Triage feedback có rule version, reason, evidence và owner.
- [ ] Threshold kết hợp count, rate/ratio và minimum sample size.
- [ ] Baseline phù hợp với route, principal type, tenant và thời gian.
- [ ] Có kiểm tra attack poisoning đối với baseline động.
- [ ] Correlation key không chỉ dựa vào IP.
- [ ] Dedup fingerprint ổn định và group key không quá rộng.
- [ ] Suppression/inhibition không xóa security event.
- [ ] Maintenance silence có owner, scope và expiry.
- [ ] Allowlist gắn principal/client đã xác minh, route/action và expiry.
- [ ] Known automation vẫn có detection cho credential compromise và behavior drift.
- [ ] Severity dựa trên impact, confidence và urgency.
- [ ] Alert có evidence, owner, runbook và resolve condition.
- [ ] Candidate rule được backtest trên dữ liệu lịch sử có coverage rõ.
- [ ] Rule thay đổi lớn được chạy shadow mode hoặc canary.
- [ ] Positive, negative và edge-case tests đều pass.
- [ ] Có rollback path và version history.
- [ ] Review cadence theo dõi alert volume, precision, actionability và recall evidence.
- [ ] Không dùng KPI giảm alert volume để biện minh cho việc tắt detection.

## 24. Kết luận

False positive và alert fatigue làm suy giảm hiệu quả bảo mật dù hệ thống có nhiều metric và rule. Cần phân biệt alert sai với alert trùng, alert không actionable và trường hợp chưa đủ evidence. Đánh giá chất lượng phải xem cả precision lẫn recall, đồng thời ghi rõ nguồn ground truth và giới hạn dữ liệu.

Cải thiện detection bắt đầu từ feedback có cấu trúc: phân loại nguyên nhân, giữ evidence, xác định route/principal/client context và sửa đúng phần gây noise. Threshold cần kết hợp count, rate, ratio, minimum sample và baseline; grouping, dedup, suppression, maintenance silence và allowlist phải có scope, owner và expiry.

Mọi thay đổi lớn nên được backtest, chạy shadow hoặc canary, kiểm thử positive/negative và có rollback. Mục tiêu là giảm page không cần thiết trong khi giữ được khả năng phát hiện credential abuse, authorization probing, route scanning và rate-limit abuse. Một alert tốt phải giúp đúng người hiểu điều gì xảy ra, tại sao đáng quan tâm và cần làm gì tiếp theo.

