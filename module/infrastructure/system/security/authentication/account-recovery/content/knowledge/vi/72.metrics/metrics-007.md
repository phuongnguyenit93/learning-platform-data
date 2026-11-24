# Recovery time measurement — Đo thời gian khôi phục tài khoản

## 1. Đang đo thời gian nào?

Một endpoint khôi phục trả lời trong 150 ms không có nghĩa người dùng đã lấy lại được tài khoản sau 150 ms. Họ có thể còn chờ email, nhập mã, cung cấp chứng cứ, chờ đánh giá hoặc đăng ký lại phương tiện xác thực. Nếu dashboard chỉ hiển thị latency HTTP, một hệ thống rất nhanh về kỹ thuật vẫn có thể khiến người dùng chờ nhiều giờ.

Trong `SECURITY_AUTHENTICATION_ACCOUNT_RECOVERY`, **recovery time** là thời gian giữa hai mốc nghiệp vụ được định nghĩa rõ của một quá trình khôi phục tài khoản. Nó liên quan tới việc mất mật khẩu, MFA, passkey hoặc thiết bị xác thực, không phải mặc nhiên là Recovery Time Objective của khôi phục hạ tầng sau thảm họa. Hai loại thời gian có thể liên quan trong một sự cố nhưng cần tên và định nghĩa riêng.

Mục tiêu đo là tìm nút thắt, đánh giá trải nghiệm và kiểm tra hệ thống có thực hiện đúng policy. Không tối ưu tốc độ bằng cách bỏ xác minh danh tính, kéo dài token tùy ý hoặc giữ session nguy hiểm hoạt động.

NIST SP 800-63B-4 mô tả account recovery là quá trình có thể kém thuận tiện hơn xác thực thông thường và có thể cần thời gian chờ kéo dài. Đây là lý do cần đo cả các khoảng chờ có chủ đích, không coi mọi phút chờ là lỗi kỹ thuật. Xem [NIST — Authenticator Event Management, mục Account Recovery](https://pages.nist.gov/800-63-4/sp800-63b/events/).

Bài học dùng các tên sự kiện, metric và ngưỡng minh họa do bài học đặt. Chúng không phải tên bắt buộc của NIST, OpenTelemetry hay một thư viện Java, và không phải bằng chứng hệ thống đã được đo thực tế.

## 2. Viết hợp đồng đo trước khi tạo dashboard

Một metric thời gian cần trả lời ít nhất bảy câu hỏi:

1. Đơn vị quan sát là request HTTP, lần thử xác minh, transaction recovery hay hành trình người dùng?
2. Mốc bắt đầu nào được dùng, và hệ thống nào có thẩm quyền ghi nhận nó?
3. Mốc kết thúc có nghĩa chính xác là gì?
4. Đơn vị thời gian là giây, mili giây hay đơn vị khác?
5. Các trạng thái chưa hoàn tất, từ chối, hủy hoặc hết hạn được xử lý thế nào?
6. Báo cáo lấy mẫu theo thời điểm bắt đầu, kết thúc hay thời điểm sự kiện được tiếp nhận?
7. Thay đổi policy hoặc định nghĩa có làm kết quả trước và sau mất khả năng so sánh không?

Ví dụ hợp đồng đo nội bộ:

```text
Metric: recovery_access_ready_duration_seconds
Definition: access-ready-v1
Unit of observation: một logical recovery transaction
Start: transaction được tạo bền vững và sự kiện RECOVERY_STARTED được ghi
End: các điều kiện để dùng phương tiện mới đăng nhập đã hoàn tất theo policy
Observation: một duration cho mỗi transaction đạt ACCESS_READY lần đầu
Excluded from this histogram: transaction chưa đạt ACCESS_READY
Companion reporting: số bắt đầu, outcome, tuổi ca đang mở và cohort đủ theo dõi
Security boundary: grant reset password không tự cho quyền thay MFA/passkey
```

“Đủ điều kiện tạo transaction” không có nghĩa người yêu cầu đã được xác nhận là chủ tài khoản. Transaction có thể kết thúc bằng từ chối vì không đủ proof. Giữ các kết quả đó trong hệ thống đo theo định nghĩa đã chốt; không loại chúng sau khi thấy kết quả xấu chỉ để làm đẹp số liệu.

API public vẫn cần phản hồi phù hợp để tránh tiết lộ tài khoản. Sự tồn tại của một sự kiện backend cho account hợp lệ không phải lý do trả thông tin đó ra ngoài. Có thể đo riêng tổng request public, các request bị chặn và các logical transaction thực sự được tạo.

## 3. Đơn vị quan sát và các mốc nghiệp vụ

### 3.1. Request, attempt, transaction và journey

| Đơn vị | Ví dụ | Dùng để đo điều gì? |
| --- | --- | --- |
| Request | Một lời gọi kiểm tra mã | Latency backend, timeout, lỗi giao tiếp |
| Attempt | Một lần người dùng nhập proof | Thời gian xác minh, số lần thử và chống lạm dụng |
| Transaction | Một phiên recovery có ID, purpose và trạng thái | Thời gian hoàn thành một quá trình có ranh giới rõ |
| Journey | Người dùng thử nhiều transaction, đổi kênh hoặc nhờ helpdesk | Trải nghiệm tổng thể qua nhiều lần thử |

Một transaction có thể có nhiều request và attempt. Một journey có thể có nhiều transaction. Không cộng tất cả latency request rồi gọi đó là thời gian người dùng chờ; phần lớn khoảng chờ có thể nằm giữa các request.

Nếu cần đo journey, phải định nghĩa cách liên kết và quyền xử lý dữ liệu tương ứng. Không suy hai yêu cầu là cùng người chỉ vì chung IP, và không tự đưa email hoặc account ID vào label metric để liên kết cho tiện.

### 3.2. Chọn mốc kết thúc theo câu hỏi

| Mốc kết thúc | Ý nghĩa minh họa | Giới hạn |
| --- | --- | --- |
| `CREDENTIAL_CHANGED` | Mật khẩu hoặc phương tiện mới được ghi nhận bền vững | Có thể còn bước bắt buộc trước khi đăng nhập |
| `ACCESS_READY` | Những điều kiện để dùng phương tiện mới đăng nhập đã được đáp ứng | Người dùng có thể chưa thực sự đăng nhập |
| `FIRST_AUTHENTICATED` | Có lần xác thực thành công sau recovery theo tiêu chí đã chọn | Phụ thuộc thời điểm người dùng quay lại; không chỉ phản ánh tốc độ xử lý |
| `SECURITY_ACTIONS_EFFECTIVE` | Các hành động bảo vệ được theo dõi đã có hiệu lực trong phạm vi định nghĩa | Cần xác định session, token, service và độ trễ liên quan |
| `NOTIFICATION_ACCEPTED` | Provider chấp nhận yêu cầu gửi thông báo | Không chứng minh tin đã tới hoặc người dùng đã đọc |

Nếu policy yêu cầu thu hồi session nguy hiểm trước khi cho truy cập trở lại, điều kiện đó phải là một phần gate của `ACCESS_READY`. Nếu một hành động chỉ là công việc theo dõi bổ sung, ghi mốc riêng; không tuyên bố toàn bộ bảo vệ đã hiệu lực chỉ từ sự kiện thay mật khẩu.

Đối với mất MFA hoặc passkey, cần xác định kết thúc là bắt đầu đăng ký phương tiện mới hay đã hoàn tất việc đăng ký hợp lệ. Một trang “thành công” trên frontend không đủ làm nguồn chuẩn nếu backend chưa commit hành động.

## 4. Phân rã thời gian mà không cộng trùng khoảng chờ

Một timeline giả định dùng giờ UTC:

| Mốc | Thời điểm | Diễn giải |
| --- | --- | --- |
| Transaction được tạo | 09:00:00 | Bắt đầu thời gian nghiệp vụ |
| Provider chấp nhận gửi mã | 09:00:04 | Kết quả gửi, chưa phải bằng chứng nhận tin |
| Proof ban đầu được xác minh | 09:02:00 | Bắt đầu khoảng chờ policy trong ví dụ |
| Review thủ công bắt đầu | 09:03:00 | Có thể chạy trong khi policy vẫn đang chờ |
| Khoảng chờ policy kết thúc | 09:12:00 | Một điều kiện đã hoàn tất |
| Review thủ công kết thúc | 09:15:00 | Điều kiện khác đã hoàn tất |
| Credential mới được commit | 09:15:05 | Ghi nhận thay đổi bền vững |
| Hành động bảo vệ bắt buộc có hiệu lực | 09:15:08 | Theo phạm vi gate của ví dụ |
| Account đạt `ACCESS_READY` | 09:15:10 | Kết thúc metric đầu-cuối |
| Có lần xác thực thành công | 09:17:00 | Mốc trải nghiệm tiếp theo |

Với hợp đồng đo trên:

```text
T_access_ready = 09:15:10 - 09:00:00 = 910 giây
T_credential_changed = 09:15:05 - 09:00:00 = 905 giây
T_first_authenticated = 09:17:00 - 09:00:00 = 1.020 giây
```

Khoảng chờ policy dài 600 giây, review thủ công dài 720 giây. Chúng chồng nhau 540 giây, nên tổng 1.320 giây không phải thời gian người dùng chờ cho hai điều kiện này. Hợp của hai khoảng kéo từ 09:02:00 tới 09:15:00, tức 780 giây.

Phân rã theo phase hữu ích để tìm nguyên nhân, nhưng các phase chạy song song không thể cộng đơn giản thành elapsed time. Có thể chọn một trong hai cách:

- Giữ từng loại duration độc lập, ghi rõ có chồng lấn và dùng timeline để xem đường găng.
- Thiết kế trạng thái loại trừ nhau để phân bổ thời gian, đồng thời công bố quy tắc ưu tiên khi nhiều nguyên nhân cùng tồn tại.

Đừng phân loại toàn bộ thời gian sau gửi email là “người dùng chậm”. Không có telemetry chứng minh thời điểm nhận email thì chỉ có thể gọi đó là khoảng giữa hai mốc quan sát được.

## 5. Đồng hồ cho đo kỹ thuật và đồng hồ cho quy trình dài

### 5.1. Đo elapsed time trong cùng JVM

Java `System.nanoTime()` phục vụ đo khoảng thời gian trong cùng JVM; giá trị không phải wall-clock và không dùng để trừ với giá trị ở một JVM khác. Tài liệu cũng phân biệt độ chính xác biểu diễn với độ phân giải thực tế. Xem [Java SE 21 — System.nanoTime](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/System.html#nanoTime()).

Mẫu tích hợp minh họa cho một bước đồng bộ:

```java
long startedNanos = System.nanoTime();
try {
    verifyEvidence();
} finally {
    double durationSeconds =
            (System.nanoTime() - startedNanos) / 1_000_000_000.0;
    observeVerificationSeconds(durationSeconds);
}
```

`verifyEvidence()` và `observeVerificationSeconds()` là các hook do ứng dụng định nghĩa trong ví dụ. Hook ghi metric phải được thiết kế để không làm thay đổi kết quả xác minh hoặc che lỗi nghiệp vụ. Ghi trong `finally` giúp đo cả lần lỗi, nhưng vẫn phải ghi outcome riêng; không trộn mọi lần thử thành metric “xác minh thành công”.

Đây là thời gian tới lúc hàm đồng bộ kết thúc. Nếu hàm chỉ khởi tạo một tác vụ bất đồng bộ rồi trả về, cần gắn phép đo vào lúc tác vụ thực sự hoàn tất; không dùng latency khởi tạo làm latency hoàn tất.

### 5.2. Đo transaction kéo dài qua nhiều tiến trình

Một recovery có thể kéo dài qua restart, hàng đợi, nhiều service và nhiều ngày. Lưu các mốc nghiệp vụ bền vững bằng thời điểm tuyệt đối, có nguồn ghi nhận rõ; không lưu `nanoTime` rồi đem trừ sau khi restart.

Nếu hai mốc do hai máy ghi nhận, độ lệch đồng hồ có thể làm duration sai. Cần đồng bộ và giám sát thời gian, ghi nguồn timestamp, và chọn nơi có thẩm quyền cho các mốc quan trọng. Đối với yêu cầu độ chính xác cao, phải có cách đánh giá sai số phù hợp với kiến trúc.

Không âm thầm đổi duration âm thành 0. Hãy ghi nhận lỗi chất lượng dữ liệu, tách khỏi phân phối hợp lệ và điều tra nguyên nhân. Clamp về 0 có thể làm p50 đẹp hơn trong khi che lỗi đồng hồ hoặc sự kiện sai thứ tự.

## 6. Sự kiện nghiệp vụ và pipeline đo

Một mô hình sự kiện minh họa:

```json
{
  "eventId": "evt-example-0007",
  "transactionRef": "opaque-transaction-reference",
  "eventType": "RECOVERY_ACCESS_READY",
  "occurredAt": "2026-11-24T09:15:10Z",
  "observedAt": "2026-11-24T09:15:14Z",
  "sequence": 7,
  "flow": "mfa-loss",
  "routeClass": "assisted",
  "policyVersion": "recovery-policy-example-v3",
  "measurementDefinition": "access-ready-v1"
}
```

Các giá trị là dữ liệu giả. `transactionRef` phục vụ đối soát trong hệ thống được phân quyền, không phải label Prometheus. Không ghi OTP, token, recovery code, mật khẩu, ảnh tài liệu hoặc session cookie vào payload đo.

`occurredAt` là mốc nghiệp vụ theo hợp đồng sự kiện. `observedAt` cho biết pipeline nhận thấy sự kiện lúc nào. Chênh lệch trong ví dụ là 4 giây; không cộng 4 giây này vào thời gian recovery nếu metric đã định nghĩa theo event time.

Nếu pipeline chậm một giờ, báo cáo có thể thiếu các ca mới hoàn tất dù quy trình recovery đã xong. Vì vậy cần đo riêng độ trễ telemetry và thể hiện thời điểm dữ liệu được xem là đủ cập nhật.

### 6.1. Chống đếm lặp và mất quan sát

Đường xử lý lý tưởng là tạo thay đổi trạng thái và sự kiện nghiệp vụ theo một cơ chế đảm bảo nhất quán phù hợp, chẳng hạn transactional outbox trong phạm vi một database. Consumer dùng `eventId`, transaction và phiên bản trạng thái để chống xử lý lặp theo thiết kế.

Tuy nhiên, deduplicate sự kiện không tự khiến cập nhật histogram ở một hệ thống khác trở nên nguyên tử. Consumer có thể crash giữa ghi checkpoint và cập nhật metric. Cần công bố mức đảm bảo của pipeline; với báo cáo cohort cần độ chính xác cao, đối soát từ dữ liệu nghiệp vụ hoặc bản tổng hợp có khả năng replay và reconciliation.

Metrics vận hành gần thời gian thực và báo cáo phân tích đã đối soát có thể phục vụ hai mục đích khác nhau. Không giả định mọi counter giám sát đều là sổ cái chính xác tuyệt đối của recovery.

### 6.2. Sai thứ tự và sự kiện đến muộn

Sự kiện kết thúc có thể đến trước sự kiện bắt đầu ở consumer. Không lập tức tạo duration âm hoặc giả mốc bắt đầu bằng thời điểm nhận. Cần lưu chờ đối soát, lấy trạng thái canonical hoặc xử lý theo quy tắc late event đã định nghĩa.

Nếu có sửa mốc do dữ liệu ban đầu sai, lưu dấu thay đổi và cập nhật báo cáo phân tích có kiểm soát. Một histogram đã tăng không hỗ trợ tùy ý xóa riêng một quan sát sai; việc sửa số liệu có thể cần tái tính ở lớp phân tích thay vì phát ra một duration âm để bù.

## 7. Retry, đổi kênh và thời gian tạm chờ

### 7.1. Không đặt lại đồng hồ chỉ vì người dùng thử lại

Resend mã, nhập sai proof hoặc retry do mạng không nhất thiết là một recovery mới. Nếu vẫn thuộc cùng logical transaction, giữ nguyên mốc bắt đầu đầu-cuối. Đo thêm từng attempt nếu cần phân tích, nhưng không dùng thời điểm attempt cuối để thay mốc ban đầu.

Nếu policy thực sự yêu cầu tạo transaction mới, lưu quan hệ với transaction trước theo phạm vi dữ liệu được phép và nêu rõ báo cáo đang theo transaction hay journey. Cách tạo lại transaction liên tục có thể làm mỗi duration trông ngắn trong khi người dùng đã vật lộn rất lâu.

Khi đổi từ self-service sang helpdesk, có thể lưu cả route ban đầu và kết quả có escalation. Đừng chỉ gắn nhãn route cuối rồi so sánh self-service với assisted như hai nhóm được phân loại trước; nhóm assisted khi đó đã được chọn bởi sự khó khăn trong quá trình.

### 7.2. Chờ khách hàng và chờ policy vẫn là thời gian trải nghiệm

Có thể đo riêng tổng thời gian lịch, thời gian xử lý chủ động và thời gian nằm trong giờ phục vụ. Đây là ba đại lượng khác nhau. Một ca mở tối thứ sáu rồi được xử lý sáng thứ hai có thời gian theo giờ phục vụ thấp nhưng người dùng vẫn chờ qua cuối tuần.

Nếu có quy tắc dừng đồng hồ khi chờ người dùng bổ sung chứng cứ, công bố tiêu chí bắt đầu, kết thúc và nguồn sự kiện. Không thay `updatedAt` mỗi lần nhắc việc rồi dùng nó làm thời điểm bắt đầu mới.

Không tự gán mọi khoảng không có sự kiện thành “người dùng chờ”. Khi không biết nguyên nhân, giữ một nhóm chưa phân loại. Việc phân loại sai thời gian có thể chuyển trách nhiệm vận hành sang người dùng mà không có bằng chứng.

## 8. Các ca chưa hoàn tất và dữ liệu bị kiểm duyệt phải

Giả sử đến thời điểm chốt dữ liệu, một transaction đã chạy 3 giờ nhưng chưa đạt `ACCESS_READY`. Ta biết nó chưa hoàn tất trong 3 giờ đã quan sát; không biết thời gian hoàn tất cuối cùng. Trong ngôn ngữ thống kê time-to-event, đây có thể là một quan sát **right-censored** tại mốc chốt nếu trạng thái vẫn được theo dõi đáng tin cậy.

Không được gán duration hoàn tất bằng 0, bằng 3 giờ hoặc tự xóa quan sát đó khỏi mọi báo cáo. Histogram thời gian hoàn tất có thể chỉ chứa các ca đã hoàn tất, nhưng dashboard phải nói rõ điều kiện mẫu và có thông tin về các ca còn mở.

Khái niệm dữ liệu kiểm duyệt và nhu cầu xử lý chúng được trình bày trong [NIST/SEMATECH — Censoring](https://itl.nist.gov/div898/handbook/apr/section1/apr131.htm). Việc áp dụng vào recovery ở đây là cách mô hình hóa của bài học, không phải một yêu cầu thống kê do tiêu chuẩn danh tính đặt ra.

### 8.1. Phân biệt đang mở, kết thúc khác và thiếu dữ liệu

| Trạng thái quan sát | Có duration hoàn tất recovery chưa? | Cách thể hiện |
| --- | --- | --- |
| Đã đạt `ACCESS_READY` | Có | Duration thành công và thời điểm kết thúc |
| Đang mở tại cutoff, theo dõi còn tin cậy | Chưa | Tuổi hiện tại và thông tin bị chốt quan sát |
| Bị từ chối theo quyết định cuối | Không phải hoàn tất thành công | Outcome và thời gian tới từ chối |
| Hết hạn hoặc bị hủy | Không phải hoàn tất thành công | Outcome riêng, không thay bằng một ca thành công chậm |
| Mất sự kiện hoặc mất khả năng đối soát | Không biết chắc | Nhóm lỗi dữ liệu; không mặc định là người dùng bỏ cuộc |

Denied, expired hoặc cancelled là các kết quả nghiệp vụ khác trong mô hình này. Không tự coi tất cả là right-censoring có thể bỏ qua, rồi suy ra xác suất thành công như thể chúng chắc chắn còn cơ hội hoàn tất cùng transaction.

Nếu dùng phân tích sống sót hoặc mô hình time-to-event nâng cao, cần xác định outcome, giả định censoring và cách xử lý kết quả cạnh tranh phù hợp. Bài học không suy ra một đường xác suất hoàn tất từ histogram success-only.

### 8.2. Ví dụ cohort 100 transaction

Một cohort giả định có 100 transaction cùng định nghĩa và mỗi ca được theo dõi đủ 24 giờ từ lúc bắt đầu:

| Kết quả trong 24 giờ | Số ca |
| --- | ---: |
| `ACCESS_READY` trong 10 phút | 60 |
| `ACCESS_READY` sau 10 phút nhưng trong 24 giờ | 10 |
| Vẫn mở ở mốc 24 giờ | 20 |
| Bị từ chối | 5 |
| Hết hạn | 5 |
| Tổng | 100 |

Tỷ lệ hoàn tất trong 10 phút của cohort là `60 / 100 = 60%`. Tỷ lệ hoàn tất trong 24 giờ là `70 / 100 = 70%`. Trong riêng 70 ca hoàn tất trong 24 giờ, tỷ lệ mất không quá 10 phút là `60 / 70 ≈ 85,7%`.

Hai con số 60% và 85,7% trả lời hai câu hỏi khác nhau. Nếu dashboard chỉ hiển thị con số thứ hai với nhãn “tỷ lệ người dùng recovery trong 10 phút”, nó đã bỏ mất các ca chưa hoàn tất hoặc kết thúc khác.

20 ca vẫn mở chưa có duration hoàn tất tại cutoff. 10 ca từ chối hoặc hết hạn có outcome riêng. Không cộng các ca đó vào tử số thành công và không loại chúng khỏi mẫu số cohort đã chốt chỉ để tăng tỷ lệ.

## 9. Cửa sổ sự kiện khác với cohort theo thời điểm bắt đầu

### 9.1. Báo cáo theo sự kiện hoàn tất

Một histogram trong 6 giờ gần nhất thường phản ánh các quan sát được ghi trong 6 giờ đó. Nó có thể bao gồm transaction bắt đầu từ hôm trước. Nó cũng có thể chưa phản ánh một sự kiện đã xảy ra nhưng telemetry chưa tới.

Chỉ số này hữu ích cho vận hành: “Những ca vừa hoàn tất có duration như thế nào?”. Nó không tự trả lời: “Những ca bắt đầu trong 6 giờ này có bao nhiêu ca hoàn tất nhanh?”.

Ví dụ, 15 phút vừa qua có 100 ca cũ hoàn tất và 40 ca mới bắt đầu. `100 / 40 = 250%` không phải tỷ lệ thành công. Tử số và mẫu số thuộc các quần thể khác nhau.

### 9.2. Báo cáo cohort đủ thời gian theo dõi

Với horizon H, một chỉ số dễ diễn giải là:

```text
CompletionWithin(H, cohort) =
    số transaction của cohort đạt ACCESS_READY trong H từ lúc bắt đầu
    / tổng transaction thuộc cohort theo hợp đồng đo
```

Để báo cáo theo tỷ lệ quan sát trực tiếp mà không trộn ca chưa đủ tuổi, chọn cohort đã có đủ thời gian theo dõi H cho mọi thành viên. Nếu cohort là khoảng bắt đầu `[A, B)`, chốt sau `B + H` là một cách bảo thủ đảm bảo điều kiện tuổi, rồi còn phải kiểm tra độ trễ và độ đầy đủ dữ liệu.

Với cohort chưa trưởng thành, hiển thị “số liệu tạm thời” hoặc áp dụng phương pháp phân tích thích hợp với các giả định được công bố. Không mặc định các ca mới bắt đầu vài phút trước là đã thất bại một SLI có horizon 24 giờ.

### 9.3. Backlog có thể xấu đi khi duration đã hoàn tất đẹp hơn

Nếu hệ thống chỉ xử lý các ca dễ và để ca khó nằm chờ, p95 của những ca hoàn tất có thể giảm. Đồng thời, số ca đang mở và tuổi lớn nhất của backlog lại tăng. Vì thế phải xem ít nhất phân phối duration đã hoàn tất, tỷ lệ hoàn tất theo horizon và tuổi ca đang mở cạnh nhau.

Khi một đợt xử lý backlog lâu ngày diễn ra, p95 của các ca vừa hoàn tất có thể tăng mạnh dù vận hành đang khắc phục vấn đề. Đừng trừng phạt nhóm chỉ vì họ đã xử lý những ca lâu vốn trước đó không xuất hiện trong histogram thành công.

## 10. Trung bình, median, percentile và histogram

Một mẫu giả định gồm 10 duration thành công, tính bằng giây:

```text
60, 90, 120, 150, 180, 240, 300, 600, 1.800, 7.200
```

Tổng là 10.740 giây; trung bình là 1.074 giây. Median theo cách lấy trung bình hai giá trị giữa là 210 giây. Hai đại lượng cho thấy phần đuôi dài ảnh hưởng rõ lên trung bình.

Nếu chọn quy ước percentile nearest-rank, p95 của mẫu này lấy vị trí `ceil(0,95 × 10) = 10`, nên bằng 7.200 giây. Phương pháp percentile khác có thể cho giá trị khác ở mẫu nhỏ; phải công bố quy ước hoặc cách xấp xỉ đang dùng, cùng số quan sát.

Không gọi p95 là thời gian tối đa. Nó cũng không đại diện cho tất cả người bắt đầu recovery nếu mẫu chỉ chứa ca thành công.

### 10.1. Chọn bucket theo câu hỏi vận hành

Một dãy ranh giới giây minh họa cho classic histogram:

```text
1, 5, 15, 30, 60, 120, 300, 600, 1.800, 3.600,
14.400, 86.400, 172.800, 604.800, +Inf
```

Đây là ví dụ thiết kế, không phải ngưỡng chuẩn. Tập bucket cần bao phủ các luồng được đo và có đủ độ phân giải quanh các ngưỡng cần ra quyết định. Metric latency xác minh vài mili giây nên có cấu hình khác metric quy trình helpdesk nhiều giờ.

Không cấu hình toàn bucket ngắn rồi để mọi ca nhiều giờ rơi vào phần đuôi không phân biệt được. Nếu muốn kiểm tra một ngưỡng cụ thể bằng số đếm bucket, cần có ranh giới tương ứng và giữ tương thích khi tổng hợp giữa các instance.

Prometheus hỗ trợ tổng hợp histogram để ước lượng quantile; không được lấy trung bình các p95 đã tính riêng trên từng instance rồi gọi là p95 toàn dịch vụ. Xem [Prometheus — Histograms and summaries](https://prometheus.io/docs/practices/histograms/).

## 11. Từ điển metric vận hành minh họa

| Tên metric nội bộ | Loại | Nội dung quan sát |
| --- | --- | --- |
| `recovery_transaction_started_total` | Counter | Transaction được tạo theo định nghĩa bắt đầu |
| `recovery_transaction_terminal_total` | Counter | Outcome cuối theo mô hình, ví dụ ready, denied, expired, cancelled |
| `recovery_access_ready_duration_seconds` | Histogram | Một duration đầu-cuối cho ca đạt `ACCESS_READY` lần đầu |
| `recovery_phase_duration_seconds` | Histogram | Duration của một phase hoặc lần thực hiện phase, có outcome phù hợp |
| `recovery_open_transactions` | Gauge | Số transaction hiện đang mở theo snapshot có thẩm quyền |
| `recovery_oldest_open_age_seconds` | Gauge | Tuổi ca đang mở lâu nhất trong phạm vi snapshot |
| `recovery_telemetry_delay_seconds` | Histogram | Độ trễ từ mốc sự kiện tới mốc quan sát đã định nghĩa |
| `recovery_measurement_invalid_total` | Counter | Quan sát không hợp lệ theo nhóm lý do hữu hạn |

Các tên là đề xuất riêng của bài học. Cần có owner, đơn vị, definition version, điều kiện ghi, quy tắc chống lặp và phạm vi label cho từng metric.

Gauge backlog cần tránh đếm cùng transaction ở nhiều vùng xử lý. Một snapshot phân mảnh phải có quy tắc ownership hoặc tổng hợp không trùng. Gauge tuổi lớn nhất cũng không cộng giữa các shard; khi các shard không trùng và snapshot đủ cập nhật, lấy cực đại theo phạm vi phù hợp.

### 11.1. PromQL cho classic histogram

Các truy vấn sau giả định đã xuất classic histogram theo đúng các tên và label nội bộ trên. Chúng minh họa cú pháp truy vấn; không hàm ý metric đang tồn tại hoặc đã được chạy trên hệ thống.

Ước lượng p95 theo flow cho các quan sát được ghi trong cửa sổ 6 giờ:

```promql
histogram_quantile(
  0.95,
  sum by (le, flow) (
    rate(recovery_access_ready_duration_seconds_bucket{
      definition_version="access-ready-v1"
    }[6h])
  )
)
```

Trung bình có trọng số theo số quan sát, cùng cửa sổ và định nghĩa:

```promql
sum by (flow) (
  rate(recovery_access_ready_duration_seconds_sum{
    definition_version="access-ready-v1"
  }[6h])
)
/
sum by (flow) (
  rate(recovery_access_ready_duration_seconds_count{
    definition_version="access-ready-v1"
  }[6h])
)
```

Các truy vấn dùng `rate` trước khi tổng hợp; với classic histogram, giữ `le` khi tính quantile. Cách sử dụng được mô tả tại [Prometheus — Query functions](https://prometheus.io/docs/prometheus/latest/querying/functions/).

Nếu không có quan sát, mẫu số có thể bằng 0 và kết quả không xác định hoặc không có series. Dashboard phải phân biệt “không có dữ liệu” với “duration bằng 0”. Không thay mọi giá trị thiếu thành 0 rồi coi đó là hồi phục tức thời.

Kết quả histogram được ghi vào cửa sổ quan sát, không tự chuyển thành cohort theo mốc bắt đầu. Muốn báo cáo `CompletionWithin(24h)` của một cohort, cần nguồn dữ liệu hoặc bản tổng hợp lưu được quan hệ bắt đầu–kết thúc theo transaction.

### 11.2. Không nhầm timestamp metric với thời điểm bắt đầu recovery

OpenTelemetry Metrics có timestamp và các thuộc tính temporality để diễn tả quá trình tích lũy hoặc xuất điểm metric. `StartTimeUnixNano` của một chuỗi metric không phải mặc nhiên là `startedAt` của một recovery transaction. Xem [OpenTelemetry — Metrics Data Model](https://opentelemetry.io/docs/specs/otel/metrics/data-model/).

Một histogram trong một khoảng xuất có thể chứa nhiều transaction bắt đầu vào các ngày khác nhau. Timestamp của điểm metric không đủ để tái tạo timeline từng ca. Các mốc nghiệp vụ phải được ghi ở lớp dữ liệu phù hợp, không suy ngược từ thời điểm scrape.

## 12. Phân nhóm hữu ích và bảo vệ dữ liệu

Có thể phân nhóm theo các chiều hữu hạn phục vụ câu hỏi vận hành: loại mất phương tiện, route tự phục vụ hoặc có hỗ trợ, nhóm policy được quản lý, vùng xử lý hoặc outcome. Mỗi chiều cần có danh mục và owner; không tự phát sinh một label mới cho mọi thông tin có trong request.

| Chiều phân nhóm | Câu hỏi có thể trả lời | Điều cần lưu ý |
| --- | --- | --- |
| `flow` | Mất MFA chậm hơn quên mật khẩu ở đâu? | Định nghĩa các nhóm không chồng lấn ngoài ý định |
| `initial_route` | Nhóm bắt đầu bằng self-service có trải nghiệm ra sao? | Giữ nguyên phân nhóm ban đầu khi phân tích cohort |
| `escalated` | Bao nhiêu ca phải chuyển sang hỗ trợ? | Đây là kết quả của quá trình, không phải thuộc tính biết sẵn lúc bắt đầu |
| `policy_class` | Nhóm có bước chờ hoặc review có bị nghẽn không? | Không trộn policy có điều kiện khác nhau rồi suy tốc độ thay đổi |
| `outcome` | Ca hoàn tất, từ chối, hủy và hết hạn khác nhau thế nào? | Không đặt tất cả vào duration thành công |
| `processing_region` | Có nút thắt theo nơi xử lý không? | Không tự gọi đây là nơi cư trú hoặc phạm vi pháp lý của người dùng |
| `definition_version` | Các số liệu có cùng hợp đồng đo không? | Quản lý số phiên bản cùng tồn tại để không tạo series vô hạn |

Các chiều kết hợp có thể tạo số lượng series rất lớn. Ví dụ 4 flow × 3 route × 5 nhóm policy × 4 vùng × 3 phiên bản định nghĩa là tối đa 720 tổ hợp trước khi tính số bucket, instance hoặc outcome. Không phải mọi tổ hợp đều tồn tại, nhưng cần ước lượng và giới hạn trước khi triển khai.

Không dùng email, số điện thoại, account ID, token, transaction ID, tên ticket hoặc nội dung lỗi tùy ý làm label. Hash một ID vẫn có thể tạo số lượng giá trị rất lớn và vẫn cho phép liên kết; nó không tự giải quyết vấn đề metric cardinality hay quyền riêng tư.

Với tenant có rất nhiều giá trị, có thể dùng nhóm tenant ở metrics và giữ phân tích chi tiết trong nguồn dữ liệu có phân quyền. Quyết định cụ thể phụ thuộc nhu cầu và giới hạn hệ thống; đừng nhân mọi tenant với mọi bucket mà không đánh giá.

Đối soát từng transaction cần kho sự kiện hoặc công cụ điều tra có kiểm soát truy cập. Tách dữ liệu chi tiết khỏi dashboard phổ biến, giới hạn thời gian lưu và chỉ ghi các trường cần cho mục đích đo đã xác định.

## 13. Thiết kế SLI và mục tiêu mà không đánh đổi an toàn

Một bộ SLI có thể gồm ba câu hỏi độc lập:

1. Những ca đã hoàn tất có thời gian đầu-cuối như thế nào?
2. Trong một cohort bắt đầu đã được theo dõi đủ H, bao nhiêu ca hoàn tất trong H?
3. Hiện có bao nhiêu ca đang mở, và chúng đã chờ bao lâu?

Không có ngưỡng thời gian chung đúng cho mọi recovery. Một thao tác còn authenticator hợp lệ khác với mất toàn bộ phương tiện và cần review. Mọi con số mục tiêu phải gắn với định nghĩa, quần thể, policy và khả năng vận hành của sản phẩm.

Ví dụ một đặc tả mục tiêu minh họa có thể viết:

```text
SLI: tỷ lệ ACCESS_READY trong H của cohort bắt đầu đủ thời gian theo dõi
Population: transaction thuộc flow và policy class được chỉ rõ
Denominator: mọi transaction thuộc cohort theo hợp đồng đo
Numerator: thành viên đạt ACCESS_READY không muộn hơn startedAt + H
H: giá trị được tổ chức chọn sau phân tích rủi ro và dữ liệu
Data completeness: có kiểm tra late events và đối soát trạng thái
Companions: outcome, backlog age, data-quality signals và security guardrails
```

Những ca bị chặn trước khi tạo transaction không thuộc mẫu số này, nhưng vẫn cần metric request và kết quả chặn riêng. Nếu thay gate tạo transaction, mẫu số sẽ thay đổi và phải đánh giá khả năng so sánh. Không để việc chuyển lỗi ra ngoài mẫu số khiến SLI trông tốt mà người dùng khó recovery hơn.

### 13.1. Tốc độ cần đi cùng tín hiệu bảo vệ tài khoản

Một thay đổi có thể làm thời gian giảm bằng cách bỏ review, cho phép reset MFA dễ hơn hoặc không đợi hành động bảo vệ có hiệu lực. Đó không phải tối ưu được chấp nhận chỉ vì dashboard xanh.

Các guardrail cần lựa chọn theo threat model, chẳng hạn kết quả kiểm thử ranh giới quyền, tỷ lệ vi phạm policy được xác nhận, cảnh báo dùng lại grant, kết quả xử lý session và sự kiện người dùng phủ nhận recovery. Đây là các nhóm tín hiệu, không phải một phép đo duy nhất chứng minh đúng chủ tài khoản.

Nếu theo dõi chiếm đoạt hoặc khiếu nại sau recovery, ghi rõ cửa sổ quan sát và độ trễ phát hiện. “Chưa có khiếu nại” ngay sau triển khai không tương đương “đã xác nhận mọi recovery đều an toàn”.

### 13.2. Không loại nhóm chậm chỉ vì chúng làm SLI xấu

Có thể báo cáo riêng theo policy hoặc route, nhưng phải giữ báo cáo tổng thể với mẫu số có ý nghĩa. Nếu tổ chức công bố chỉ số cho self-service, nêu rõ những trường hợp được đưa sang helpdesk nằm ở đâu trong báo cáo trải nghiệm.

Nếu có loại trừ synthetic test hoặc dữ liệu kiểm thử nội bộ, định nghĩa trước và nhận diện bằng nguồn đáng tin cậy. Không cho client tự gửi `isTest=true` để né ghi nhận và không tự loại mọi account bị classifier nghi ngờ mà không giữ được khả năng đánh giá sai lệch.

## 14. Dashboard và cách đọc khi có sự cố

Một dashboard gọn có thể chia thành các vùng thông tin song song:

| Nhóm thông tin | Nội dung | Cách sử dụng |
| --- | --- | --- |
| Lưu lượng | Request, transaction bắt đầu, attempt và outcome | Kiểm tra thay đổi mẫu số và mức tải |
| Thời gian hoàn tất | Median/p95, số quan sát và định nghĩa | Xem các ca đã hoàn tất đang nhanh hay chậm |
| Cohort | CompletionWithin(H) của cohort đủ tuổi | Đánh giá xác suất quan sát được trong horizon đã chọn |
| Backlog | Số đang mở, tuổi lớn nhất, nhóm tuổi và phase | Phát hiện ca bị bỏ lại hoặc hàng đợi nghẽn |
| Phase | Chờ gửi tin, xác minh, review, policy và ghi credential | Tìm nút thắt theo mốc có thể đo |
| Chất lượng dữ liệu | Lag, sự kiện thiếu, trùng, duration không hợp lệ | Biết khi nào không nên tin đồ thị chính |
| Bảo vệ tài khoản | Những guardrail liên quan đã được định nghĩa | Kiểm tra tốc độ có đi cùng rủi ro mới không |

Dashboard phải hiển thị khoảng thời gian, đơn vị, số mẫu và cutoff dữ liệu. Một giá trị p95 của vài quan sát không có cùng ý nghĩa thực tiễn với p95 từ một mẫu lớn; không che số mẫu đi vì nó làm giao diện rối.

### 14.1. Phân biệt các nguyên nhân có cùng biểu hiện

| Quan sát | Những khả năng cần kiểm tra |
| --- | --- |
| p95 giảm, backlog tăng | Ca khó chưa hoàn tất nên chưa vào histogram; hoặc mix case thay đổi |
| p95 tăng, backlog giảm | Đang xử lý các ca cũ; hoặc các ca mới thật sự chậm hơn |
| Duration tốt, completion trong H giảm | Chỉ ca dễ hoàn tất; outcome khác tăng; hoặc telemetry thiếu |
| Không có quan sát mới | Lưu lượng bằng 0, pipeline lỗi, metric đổi tên hoặc không còn ca hoàn tất |
| Review nhanh hơn, denial tăng mạnh | Quy trình quyết định thay đổi; cần xem chất lượng và tác động người dùng |
| Gửi mã nhanh, proof tới chậm | Có thể là delivery, giao diện, người dùng hoặc dữ liệu mốc thiếu; chưa đủ để quy trách nhiệm |

Điều tra theo thứ tự có thể kiểm chứng: kiểm tra dữ liệu đủ cập nhật, kiểm tra lưu lượng và định nghĩa có đổi không, xem phân nhóm policy/flow, rồi đối chiếu timeline những ca mẫu trong phạm vi được phép.

### 14.2. Cảnh báo phải gắn với hành động

Một cảnh báo về backlog cần cho biết scope, phase, độ cũ và runbook xử lý. Một cảnh báo p95 ở lưu lượng rất thấp có thể không ổn định; cần định nghĩa điều kiện số mẫu và cửa sổ thích hợp thay vì áp dụng máy móc cùng một rule cho mọi flow.

Lỗi metric không được trở thành lý do bỏ xác minh để giảm thời gian. Khi cần giảm backlog, các hành động phù hợp có thể là sửa tuyến gửi, tăng năng lực review hoặc xử lý lỗi workflow đã xác nhận. Mọi thay đổi mục tiêu bảo vệ vẫn phải qua quy trình có thẩm quyền.

## 15. Ví dụ: trung bình đẹp hơn dù từng nhóm đều chậm hơn

Giả sử chỉ đang xét duration của các ca hoàn tất, với hai nhóm cố định theo định nghĩa phân tích:

| Nhóm | Trước: số ca | Trước: trung bình | Sau: số ca | Sau: trung bình |
| --- | ---: | ---: | ---: | ---: |
| Self-service | 100 | 120 giây | 200 | 130 giây |
| Assisted | 20 | 7.200 giây | 10 | 7.500 giây |

Trung bình tổng trước thay đổi:

```text
(100 × 120 + 20 × 7.200) / 120 = 1.300 giây
```

Trung bình tổng sau thay đổi:

```text
(200 × 130 + 10 × 7.500) / 210 ≈ 481 giây
```

Từng nhóm đều chậm hơn, nhưng trung bình tổng giảm vì tỷ trọng nhóm assisted thấp hơn. Không thể kết luận hệ thống xử lý nhanh hơn trong từng nhóm từ số tổng này.

Cũng chưa biết 10 ca assisted còn thiếu so với trước là do ít người cần hỗ trợ hay vì ca khó vẫn đang mở. Cần kiểm tra starts, escalation, outcome, backlog và cohort. Nếu các ca chậm chưa kết thúc, chỉ so sánh nhóm completion lại thêm một lớp sai lệch chọn mẫu.

Khi so sánh release, giữ điều kiện phân nhóm và định nghĩa nhất quán. Nếu cần so sánh điều chỉnh theo mix, công bố phương pháp và trọng số; không tự chọn trọng số sau khi thấy kết quả thuận lợi.

A/B test cũng cần unit phân bổ thích hợp để retry không tùy ý đổi nhánh. Đồng thời theo dõi completion theo horizon và guardrail an toàn, không chỉ duration của ca thành công. Một thay đổi có hiệu quả trải nghiệm phải được đánh giá với phạm vi và độ trễ quan sát phù hợp.

## 16. Kiểm tra chất lượng phép đo trước khi tin kết quả

Các ca thử sau là kế hoạch cho instrumentation và pipeline, không phải xác nhận chúng đã chạy trong module:

| Tình huống | Tính chất cần xác minh |
| --- | --- |
| Transaction hoàn tất qua các phase bình thường | Mốc đầu/cuối đúng; một quan sát duration đúng đơn vị |
| Nhập sai nhiều lần rồi thành công | Attempt tăng phù hợp; đồng hồ transaction không bị đặt lại |
| Resend hoặc đổi route | Không nhân bản transaction ngoài định nghĩa; giữ lịch sử cần thiết |
| Event được giao lặp | Báo cáo đã đối soát không tăng thêm ca hoặc duration |
| Consumer crash quanh bước cập nhật metric | Biết phạm vi có thể mất/trùng; reconciliation sửa được báo cáo canonical |
| Sự kiện đến sai thứ tự | Không tạo duration sai; có cơ chế đối soát |
| Mốc kết thúc đến muộn sau cutoff | Có quy tắc cập nhật lại báo cáo và trạng thái dữ liệu tạm thời |
| Đồng hồ lệch khiến duration âm | Quan sát bị đánh dấu lỗi; không đổi thành 0 để che vấn đề |
| JVM restart giữa quy trình | Mốc nghiệp vụ vẫn dùng được; không trừ `nanoTime` giữa tiến trình |
| Transaction bị từ chối, hủy hoặc hết hạn | Outcome riêng; không ghi vào histogram duration thành công |
| Không có lưu lượng | Phân biệt không dữ liệu với duration bằng 0 |
| Policy hoặc definition đổi | Có phiên bản; không âm thầm trộn các định nghĩa khác nhau |
| Hai vùng cùng báo backlog | Không đếm trùng; tuổi lớn nhất tổng hợp đúng ý nghĩa |
| Exception hoặc payload provider có bí mật | Telemetry không xuất token, OTP hoặc chứng cứ nhạy cảm |

Có thể dùng một timeline tổng hợp nhỏ với các mốc đã biết để kiểm tra phép trừ, đơn vị và quy tắc đếm. Với dữ liệu thật, lấy mẫu đối soát trong công cụ được phân quyền, không sao chép hồ sơ recovery ra nơi không được phép.

Một số bất biến hữu ích của lớp phân tích:

- `ACCESS_READY` được gán duration cần có mốc bắt đầu hợp lệ theo cùng định nghĩa.
- Mỗi logical transaction chỉ có một mốc đạt ready lần đầu cho metric tương ứng.
- Mốc kết thúc không trước bắt đầu trong dữ liệu hợp lệ theo hợp đồng thời gian.
- Phân nhóm outcome tại một cutoff dùng quy tắc rõ và không đếm trùng cùng một ca.
- Tổng các nhóm trạng thái được dùng để phân hoạch phải đối soát về cohort, kể cả nhóm thiếu dữ liệu.
- Mọi kết quả tỷ lệ phải truy được tử số và mẫu số về cùng quần thể được định nghĩa.

Không cần ép mọi dashboard vận hành trùng tức thời với warehouse đã chốt dữ liệu. Cần hiểu và công bố khác biệt về độ trễ, cập nhật muộn và mức đảm bảo để người dùng ra quyết định đúng.

## 17. Câu hỏi tự kiểm tra

**Câu 1:** Endpoint reset trả kết quả trong 100 ms, nhưng người dùng đợi review một giờ. Có thể nói recovery mất 100 ms không?

Không. Đó là latency của request được đo. Thời gian đầu-cuối phải tính giữa các mốc nghiệp vụ đã chốt, bao gồm khoảng chờ trong định nghĩa.

**Câu 2:** Trong 100 ca bắt đầu, 70 ca hoàn tất và 60 ca hoàn tất trong 10 phút. Có thể báo tỷ lệ recovery trong 10 phút là 85,7% không?

Chỉ nếu ghi rõ đây là tỷ lệ có điều kiện trong 70 ca hoàn tất thuộc phạm vi quan sát. Tỷ lệ trên toàn cohort 100 ca là 60%, khi mọi ca đã có đủ thời gian theo dõi ngưỡng đó và dữ liệu đã đầy đủ.

**Câu 3:** Vì sao không lấy trung bình p95 của các instance?

Vì quantile không cộng gộp theo cách đó. Cần tổng hợp phân phối phù hợp, chẳng hạn bucket histogram tương thích, rồi tính quantile trên phân phối tổng; đồng thời giữ đúng quần thể và định nghĩa.

**Câu 4:** Một ca đang mở 24 giờ có phải là ca hoàn tất mất 24 giờ không?

Không. Chỉ biết ca đó chưa hoàn tất trong khoảng được theo dõi. Ghi tuổi và trạng thái quan sát, không phát minh mốc hoàn tất.

**Câu 5:** Tại sao p95 có thể tăng sau khi đội vận hành xử lý backlog thành công?

Vì các ca cũ có duration dài vừa đi vào mẫu hoàn tất. Cần xem backlog và cohort cùng với histogram, thay vì kết luận từ một đường p95.

**Câu 6:** Khi metric collector ngừng hoạt động, có nên cho recovery bỏ qua bước xác minh để khỏi vi phạm SLO không?

Không. Hệ thống đo hỗ trợ quan sát, không cấp quyền thay đổi mục tiêu bảo vệ. Cần xử lý lỗi telemetry và giữ quy trình recovery theo policy.

## 18. Hồ sơ đo đủ để người khác hiểu và sử dụng

Một phép đo thời gian recovery có thể bàn giao khi người đọc biết đơn vị quan sát, mốc bắt đầu và kết thúc, policy/definition version, đơn vị thời gian, quy tắc retry, cách xử lý outcome và ca chưa hoàn tất, cùng nguồn dữ liệu để đối soát.

Báo cáo nên thể hiện cả tốc độ của ca đã hoàn tất, tỷ lệ hoàn tất theo horizon của cohort đủ tuổi và trạng thái các ca còn mở. Những thông tin về số mẫu, cutoff, độ trễ telemetry và lỗi đo giúp ngăn người đọc diễn giải quá mức một con số.

Thời gian khôi phục chỉ có giá trị khi gắn với việc lấy lại quyền truy cập theo đúng điều kiện bảo vệ tài khoản. Giảm thời gian chờ do lỗi hệ thống là một cải thiện; bỏ ranh giới xác minh để làm số liệu đẹp hơn là thay đổi rủi ro mà metric phải giúp phát hiện.


