# Recovery abandonment rate

## 1. Chỉ số này trả lời câu hỏi gì?

Trong module `SECURITY_AUTHENTICATION_ACCOUNT_RECOVERY`, recovery abandonment rate giúp phát hiện những hành trình lấy lại quyền truy cập mà người dùng không tiếp tục theo định nghĩa đo lường đã chọn. Hành trình có thể liên quan mất mật khẩu, MFA, passkey hoặc thiết bị xác thực; thời gian và yêu cầu proof của chúng không giống nhau.

Một tỷ lệ tăng có thể liên quan SMS chậm, màn hình khó hiểu, chuyển thiết bị không liền mạch, yêu cầu proof không phù hợp hoặc hàng đợi hỗ trợ quá dài. Nó cũng có thể tăng vì bot tạo nhiều request, instrumentation mất event hoặc cohort chưa có đủ thời gian hoàn tất.

Vì vậy không có một phép tính “100% trừ tỷ lệ thành công” luôn đồng nghĩa tỷ lệ người dùng tự bỏ cuộc. Cần xác định đơn vị đếm, mẫu số, khoảng thời gian, những trạng thái được phân biệt và mức chắc chắn của việc suy luận.

Bài học xây dựng một hợp đồng đo lường minh họa. Tên event, schema, query và tham số là ví dụ để áp dụng vào hệ thống cụ thể, không khẳng định dự án đang có sẵn những thành phần đó.

### 1.1. Bỏ dở là kết luận đo lường, không phải ý định đã biết

Khi không thấy hoạt động tiếp, ta chưa biết người dùng mất hứng, không nhận được mã, đã khôi phục bằng đường khác hay chuyển sang một thiết bị không được nối cùng hành trình.

Nên dùng tên như `inferred_abandoned` cho trường hợp được suy luận từ inactivity và cửa sổ quan sát. Chỉ một event chủ động cancel mới cho biết có một hành động hủy, nhưng ngay cả cancel cũng không tự giải thích động cơ.

Chỉ số này không nên tự điều khiển việc thu hồi token, khóa account hoặc xóa evidence. Vòng đời bảo mật phải theo policy riêng; phân loại analytics không phải một quyết định cấp hoặc tước quyền.

## 2. Chọn đơn vị: request, journey hay người dùng

| Đơn vị | Hữu ích khi nào? | Sai lệch dễ gặp |
| --- | --- | --- |
| HTTP request | Đo tải, lỗi API, chống lạm dụng | Retry và resend bị xem như nhiều người |
| Recovery request | Theo dõi một thực thể nghiệp vụ cụ thể | Một người có thể tạo lại nhiều request |
| Recovery journey | Theo dõi một quá trình theo quy tắc liên kết | Liên kết sai có thể gộp hoặc tách quá mức |
| Account hoặc người dùng | Đánh giá trải nghiệm ở mức subject | Khó định danh an toàn trước xác minh, nhiều mục đích khác nhau |
| Step attempt | Đo một lần nhập mã hoặc thao tác UI | Không thể trực tiếp dùng làm mẫu số hành trình |

Một journey có thể chứa nhiều resend và retry. Một request nghiệp vụ mới có thể thuộc cùng journey hoặc một journey mới, tùy contract. Phải ghi rõ quy tắc; không đổi quy tắc mỗi lần dashboard trông xấu.

### 2.1. Điểm bắt đầu phải là một sự kiện có nghĩa

“Trang forgot password được mở”, “caller gửi một định danh” và “server đã tạo recovery request đủ điều kiện” là ba mẫu số khác nhau.

Nếu lấy page view, có thể đếm người chỉ đọc hướng dẫn. Nếu chỉ lấy proof đã xác minh, sẽ bỏ qua mọi khó khăn trước proof và làm tỷ lệ đẹp hơn một cách có hệ thống.

Một lựa chọn minh họa là server ghi `journey_started` khi chấp nhận một thao tác khởi tạo theo contract, với một journey reference không mang quyền truy cập. Nếu public endpoint che sự tồn tại của account, pipeline nội bộ vẫn phải giữ ranh giới dữ liệu và quyền xem phù hợp.

Không tạo event chứa `account_exists=true` trong payload analytics công khai hoặc trả nó về browser để tiện phân đoạn.

### 2.2. Retry, resend và chuyển thiết bị

Retry kỹ thuật nên giữ operation/journey identity khi hợp đồng cho phép. Resend không tự tăng số journey. Quay lại bằng một token còn hợp lệ có thể tiếp tục journey cũ theo dữ liệu server.

Việc nối cross-device cần dùng một reference an toàn hoặc ngữ cảnh được server xác nhận, không dùng raw recovery token làm analytics ID. Link preview và email scanner có thể mở URL mà không phải người dùng thực sự tiếp tục.

Nếu không thể nối dữ liệu chắc chắn, ghi mức thiếu quan sát hoặc báo theo request-level. Không tự ghép chỉ vì cùng IP, cùng một địa chỉ email dạng hash hoặc một device fingerprint mơ hồ.

## 3. Viết hợp đồng chỉ số trước khi tính

Một metric contract cần trả lời được các câu hỏi sau.

| Thành phần | Ví dụ nội dung phải xác định |
| --- | --- |
| Unit | Một recovery journey theo phiên bản quy tắc liên kết |
| Cohort entry | Journey bắt đầu trong khoảng `[t0, t1)` |
| Population | Những journey được nhận vào đo, loại trừ theo quy tắc nào |
| Completion | Điều kiện nghiệp vụ đã commit nào được coi là khôi phục xong |
| Observation horizon H | Khoảng theo dõi cố định theo loại luồng/policy |
| Inactivity rule W | Khoảng không có tiến triển có nghĩa theo định nghĩa |
| Data cutoff T | Mốc dữ liệu được dùng để phát hành snapshot |
| Late-event allowance L | Khoảng chờ dữ liệu tới muộn trước khi phát hành ổn định |
| Outcome taxonomy | Completed, inferred abandoned, denied, failed, cancelled, waiting, unknown |
| Version | Phiên bản measurement, policy và event schema |
| Restatement | Cách cập nhật số liệu khi dữ liệu muộn hoặc sửa lỗi |
| Privacy | Field cho phép, scope người đọc và vòng đời dữ liệu |

Không có một H hoặc W phổ quát cho mọi recovery. Luồng mật khẩu tự phục vụ và luồng chờ đánh giá thủ công có thời gian hợp lý khác nhau.

Một thay đổi định nghĩa H, W, điểm bắt đầu hoặc completion là thay đổi metric. Cần version và đánh dấu trên báo cáo, không để nó xuất hiện như một cải thiện sản phẩm.

### 3.1. Completion phải gắn với quyền thực sự được khôi phục

HTTP 200 khi gửi mã không phải completion. Provider báo delivered cũng chưa phải completion. Event frontend “success page viewed” có thể thiếu hoặc được mở lại nhiều lần.

Một contract có thể định nghĩa hoàn tất khi thay đổi credential cần thiết đã commit, proof/grant được tiêu thụ đúng và những điều kiện session bắt buộc đã được đáp ứng. Contract khác có thể đo riêng “credential reset completed” và “access restored”.

Không gộp hai milestone đó mà không nêu rõ. Người đổi mật khẩu thành công nhưng bị mắc ở bước đăng ký MFA có thể hoàn tất một bước, vẫn chưa đạt mục tiêu truy cập của journey.

## 4. Phân loại outcome để tránh đổ mọi lỗi cho người dùng

Tại horizon của một journey đã đủ điều kiện đo, dùng một bộ outcome loại trừ nhau theo contract.

| Outcome minh họa | Ý nghĩa |
| --- | --- |
| COMPLETED | Điều kiện hoàn tất đã xảy ra trong horizon |
| INFERRED_ABANDONED | Không hoàn tất, không có outcome riêng khác, đủ điều kiện inactivity và dữ liệu quan sát đáng tin |
| POLICY_DENIED | Journey kết thúc bằng quyết định policy được ghi nhận |
| TERMINAL_FAILED | Journey kết thúc vì lỗi kỹ thuật/nghiệp vụ cuối theo contract |
| EXPLICIT_CANCELLED | Có hành động hủy rõ, được ghi nhận theo đúng vòng đời |
| WAITING_OR_ACTIVE | Có chờ hợp lệ hoặc tiến triển còn gần horizon, chưa đủ điều kiện suy luận bỏ dở |
| UNKNOWN | Thiếu dữ liệu, mâu thuẫn hoặc không đủ căn cứ phân loại |

Đây là taxonomy minh họa. Một hệ thống có thể tách thêm outcome, nhưng cần giữ khả năng đối chiếu tổng và tránh đếm một journey vào nhiều nhóm cùng lúc.

### 4.1. Quy tắc suy luận abandonment

Trong ví dụ này, tại thời điểm `deadline = started_at + H`, một journey chỉ thuộc INFERRED_ABANDONED khi:

1. Không có completion hợp lệ trong horizon.
2. Không có denied, terminal failure hay explicit cancel đã xác định.
3. Không có trạng thái chờ bắt buộc hoặc tác vụ hệ thống đang chờ được contract nhận diện.
4. Đã không có tiến triển có nghĩa trong ít nhất W trước deadline.
5. Dữ liệu đủ để đưa ra suy luận theo điều kiện chất lượng đã công bố.

“Tiến triển có nghĩa” phải được xác định. Một page heartbeat, resend tự động hoặc retry của worker không nên mặc định làm mới hoạt động của người dùng.

Nếu không nhận được SMS vì provider lỗi và trạng thái chờ đó được biết, hãy giữ reason tương ứng. Nếu lỗi không được quan sát, một số ca có thể bị suy luận nhầm là bỏ dở; cần công bố giới hạn thay vì gọi đây là ý định thật của người dùng.

### 4.2. Outcome kết thúc và sự kiện mâu thuẫn

Nếu cùng journey có cả completed và cancelled với thứ tự không phù hợp, đừng chọn event đến warehouse cuối cùng một cách mù quáng. Dùng state/version nguồn chuẩn và quy tắc vòng đời.

Một transition bị từ chối một lần không phải POLICY_DENIED cuối cùng nếu user sau đó hoàn tất hợp lệ trong horizon. Một lần nhập OTP sai cũng không phải TERMINAL_FAILED nếu còn quyền thử.

Trường hợp không giải được mâu thuẫn nên vào UNKNOWN và được điều tra. Không đưa nó vào outcome nào giúp tỷ lệ trông tốt hơn.

## 5. Cohort trưởng thành, right censoring và thời gian chờ

Một journey vừa bắt đầu có thể chưa có thời gian hoàn tất. Nếu đếm nó là bỏ dở ngay khi chạy báo cáo, cohort mới sẽ trông tệ hơn cohort cũ.

Trong thống kê, right censoring mô tả tình huống việc theo dõi kết thúc trước khi biết thời điểm một sự kiện về sau. Bài này vận dụng ý tưởng đó để tránh xem “chưa quan sát đủ” là “không bao giờ hoàn tất”. [NIST/SEMATECH e-Handbook — Censoring](https://www.itl.nist.gov/div898/handbook/apr/section1/apr131.htm).

### 5.1. Một quy tắc maturity cố định

Với mỗi journey j:

```text
deadline(j) = started_at(j) + H(j)

mature_at(j) = deadline(j) + L(j)

Journey đủ trưởng thành để vào snapshot ổn định khi:
    mature_at(j) <= data_cutoff
```

H và L phải được chọn theo contract/version. Maturity chỉ nói đã đủ khoảng quan sát và chờ ingest dự kiến; nó không chứng minh pipeline không mất dữ liệu.

Đối với journey chưa mature, hiển thị là chưa đủ thời gian đo. Không trộn chúng vào mẫu số của tỷ lệ ổn định rồi gán phần thiếu completion thành abandonment.

### 5.2. Chờ bảo mật và hỗ trợ không giống inactivity

Một thời gian chờ chống gian lận hoặc review thủ công có thể dài hơn H của luồng tự phục vụ. Cần horizon phù hợp hoặc outcome chờ riêng và báo rõ.

Không xóa chờ bắt buộc khỏi telemetry để dashboard đẹp hơn. Cũng không tự ngừng đồng hồ mọi lúc hệ thống chờ nếu metric đang được định nghĩa theo thời gian thực người dùng trải qua.

Có thể đo riêng wall-clock time và thời gian có thể hành động. Nếu dùng đồng hồ thứ hai, nêu rõ trạng thái nào được trừ, nguồn trạng thái và cách chống việc hệ thống gán mọi lỗi thành “đang chờ”.

### 5.3. Đã bỏ dở suy luận rồi quay lại

Nếu user quay lại và hoàn tất trước deadline, outcome cuối của snapshot horizon cần phản ánh completion theo contract, không giữ nhãn inactivity tạm thời.

Nếu hoàn tất sau H, báo completion dài hạn hoặc horizon khác. Nó không thay đổi sự thật “chưa hoàn tất trong H”, nhưng cho thấy nhãn INFERRED_ABANDONED tại H không có nghĩa user bỏ cuộc vĩnh viễn.

Không tự khóa journey nghiệp vụ chỉ để bảo toàn nhãn analytics. Giữ vòng đời thật và các snapshot đo lường là hai lớp riêng.

### 5.4. Phân tích time-to-event nâng cao

Có thể dùng phương pháp time-to-event để phân tích khi thời gian quan sát không đồng đều, nhưng cần xác định event đích và giả định censoring phù hợp.

Nếu completion, policy denial và terminal failure là các outcome cạnh tranh, không mặc định coi mọi outcome còn lại là censoring độc lập rồi diễn giải `1 - survival` thành xác suất bỏ dở. Abandonment suy luận bằng inactivity còn có vấn đề xác định thời điểm sự kiện.

Phương pháp thống kê không sửa được một taxonomy mơ hồ hoặc thiếu dữ liệu có hệ thống. Bắt đầu bằng cohort ổn định, outcome rõ và chất lượng telemetry trước khi dùng mô hình phức tạp.

## 6. Công thức và ví dụ có thể kiểm tra

Gọi:

```text
D = số journey mature, nằm trong cohort và population đã công bố
A = số journey thuộc INFERRED_ABANDONED tại horizon

abandonment_rate = A / D, khi D > 0

Nếu D = 0:
    kết quả là không xác định / không có dữ liệu đủ điều kiện,
    không gán thành 0%.
```

Ví dụ một cohort minh họa có 1.000 journey mature:

| Outcome | Số journey |
| --- | ---: |
| COMPLETED | 620 |
| INFERRED_ABANDONED | 180 |
| POLICY_DENIED | 70 |
| TERMINAL_FAILED | 40 |
| EXPLICIT_CANCELLED | 30 |
| WAITING_OR_ACTIVE | 40 |
| UNKNOWN | 20 |
| Tổng | 1.000 |

Kết quả:

```text
Abandonment suy luận theo contract: 180 / 1000 = 18%
Chưa completed tại horizon:        380 / 1000 = 38%
Unknown:                           20 / 1000 = 2%
Waiting hoặc active:               40 / 1000 = 4%
```

38% không phải cùng một chỉ số với 18%. Nó gồm cả bị policy từ chối, lỗi cuối, hủy chủ động, đang chờ và unknown.

Nếu muốn tính “user exit” gồm cả explicit cancel, phải đặt tên và công thức riêng; trong ví dụ sẽ là `(180 + 30) / 1000 = 21%`. Không âm thầm đổi định nghĩa abandonment.

### 6.1. Không loại unknown mà không báo

Nếu tính trên phần có outcome đã biết, mẫu số là `1000 - 20 = 980`, cho `180 / 980 ≈ 18,37%`. Đây là một tỷ lệ khác, cần nêu rõ population và tỷ lệ bị loại.

Nếu chỉ 20 ca UNKNOWN có thể bị phân loại lại còn các outcome khác đã xác định đúng tại horizon, tỷ lệ A/D trong ví dụ nằm từ 18% tới 20% tùy kết quả 20 ca đó. Khoảng này là biên theo taxonomy giả định, không phải khoảng tin cậy thống kê.

Nếu telemetry còn mất journey bắt đầu hoặc completion ở ngoài tập UNKNOWN, biên đó không còn bảo đảm. Cần kiểm tra coverage thay vì dùng phép tính để che dữ liệu mất.

## 7. Funnel theo bước và abandonment toàn journey

Một funnel minh họa cho luồng mất mật khẩu:

```text
Journey started
  -> Challenge ready
  -> User reached proof step
  -> Proof verified
  -> Credential change committed
  -> Access restored theo contract
```

Luồng mất MFA/passkey có thể đi qua proof khác và enrollment mới. Không ép mọi đường vào một chuỗi bắt buộc như nhau rồi coi nhánh không dùng là rơi rụng.

Google Analytics phân biệt open funnel cho phép vào ở nhiều bước với closed funnel bắt đầu từ bước đầu. Sự khác biệt này minh họa vì sao điểm vào funnel phải được nêu rõ khi so sánh số liệu. [Google Analytics Help — Open and closed funnels](https://support.google.com/analytics/answer/13012015?hl=en).

### 7.1. Drop-off của một bước không tự là user abandonment

Tại một bước, số không sang bước kế tiếp có thể gồm user chọn nhánh khác, bị chặn, đang chờ hoặc hoàn tất qua đường hỗ trợ.

Một step drop-off rate cần mẫu số là các journey đủ điều kiện đã vào bước đó và quy tắc về bước tiếp theo hợp lệ. Nó không dùng cùng mẫu số với toàn journey.

Nếu funnel có nhánh, cộng số người ở mọi nhánh có thể đếm trùng journey. Dùng tập journey hoặc transition có danh tính rõ, không cộng các counter endpoint một cách trực tiếp.

### 7.2. Không lấy việc xem trang làm proof

Email scanner có thể mở link. Browser có thể báo page viewed nhưng request bị lỗi trước khi backend tạo challenge. Một màn hình success có thể được reload nhiều lần.

Những event đó hữu ích cho UX khi được hiểu đúng, nhưng completion và các milestone cấp quyền nên lấy từ dữ liệu server đã commit. Tránh phát một event marketing/analytics như nguồn chuẩn cho quyết định bảo mật.

## 8. Hợp đồng event để đo được đúng journey

Một envelope analytics nội bộ minh họa:

```json
{
  "eventId": "evt-test-001",
  "journeyRef": "journey-test-001",
  "eventType": "recovery_proof_verified",
  "occurredAt": "2026-11-24T00:00:00Z",
  "ingestedAt": "2026-11-24T00:00:02Z",
  "journeyType": "password_recovery",
  "measurementVersion": "abandonment-test-v1",
  "policyVersion": "recovery-policy-test-v1",
  "aggregateVersion": 4,
  "source": "recovery-service"
}
```

Đây là dữ liệu tổng hợp cho ví dụ. Không đưa email, số điện thoại, raw token, OTP, TOTP seed, session cookie hoặc ảnh định danh vào envelope để tính tỷ lệ.

`journeyRef` không được mang quyền sử dụng recovery. Dù là reference giả danh, nó vẫn có thể liên kết với người dùng trong hệ thống và cần scope truy cập, retention phù hợp.

### 8.1. Các event và nguồn có thẩm quyền

| Event minh họa | Nguồn cần xác nhận | Vai trò trong đo lường |
| --- | --- | --- |
| journey_started | Server chấp nhận điểm bắt đầu theo contract | Cohort và denominator |
| recovery_step_reached | UI/server tùy bước, ghi rõ nguồn | Chẩn đoán funnel |
| recovery_wait_entered/exited | State machine hoặc job đáng tin | Phân biệt chờ với inactivity |
| recovery_proof_rejected | Validator | Chẩn đoán thử sai, chưa mặc định terminal |
| recovery_proof_verified | Validator/transaction nguồn chuẩn | Milestone proof, chưa mặc định complete |
| recovery_completed | Nguồn commit tác động cần thiết | Completion theo contract |
| recovery_cancelled | Transition hợp lệ từ hành động hủy | Explicit cancel |
| recovery_terminal_failed | Nguồn trạng thái cuối | Technical/business failure riêng |
| recovery_policy_denied | Quyết định cuối theo policy | Tách denied khỏi abandonment |
| measurement_quality_flag | Pipeline đối chiếu dữ liệu | Unknown và giới hạn quan sát |

Không để client tự khai `recovery_completed` rồi dùng event đó làm nguồn duy nhất cho outcome. Một payload `verified=true` cũng không là bằng chứng xác minh thực tế.

### 8.2. Event time, ingest time và dữ liệu tới muộn

Cohort thường dựa trên thời điểm bắt đầu nghiệp vụ; outcome trong horizon dựa trên event time đáng tin. Ingest time cho biết dữ liệu được pipeline nhìn thấy lúc nào.

Nếu completion xảy ra trước deadline nhưng đến warehouse sau khi snapshot được phát hành, có thể cần restatement. Lưu phiên bản snapshot, cutoff và source revision để người đọc biết số liệu đã được sửa.

Nếu completion thực sự xảy ra sau deadline, đó là outcome ở horizon dài hơn, không phải late ingest của một completion trong horizon. Hai trường hợp này cần test riêng.

Không tin timestamp client vô điều kiện. Clock lệch, event offline và dữ liệu không hợp lệ cần quy tắc đối chiếu hoặc quality flag.

### 8.3. Duplicate và thứ tự event

Deduplicate event theo identity và scope được xác định. Cùng một completion được broker giao lại không được tăng numerator completion hoặc số journey.

Event tới không đúng thứ tự cần được dựng lại theo version/vòng đời đáng tin. Nếu chỉ sort theo thời gian warehouse nhận, một callback cũ có thể làm journey “lùi” trạng thái.

Cũng phải xử lý cùng event ID nhưng nội dung khác, nhiều event ID cho cùng transition và việc start bị phát lại. Không suy rằng unique event ID đã đủ để có đúng một bản ghi journey.

## 9. Tính theo cohort bằng snapshot đối chiếu được

Một cách tổ chức là tạo một hàng measurement cho mỗi journey trong mỗi snapshot, với uniqueness theo `(snapshot_id, journey_ref)`.

Các field minh họa:

```text
snapshot_id
journey_ref
journey_type
started_at
deadline_at
mature_at
measurement_version
policy_version
population_version
outcome
quality_reason
source_revision
```

Outcome đã được phân loại trước theo contract, không phải query cuối tự coi mọi hàng thiếu completed là abandonment.

### 9.1. Query tổng hợp minh họa

Ví dụ SQL dùng cú pháp tổng hợp PostgreSQL:

```sql
SELECT
    journey_type,
    measurement_version,
    policy_version,
    population_version,
    COUNT(*) AS mature_journeys,
    COUNT(*) FILTER (
        WHERE outcome = 'INFERRED_ABANDONED'
    ) AS inferred_abandoned,
    COUNT(*) FILTER (
        WHERE outcome = 'UNKNOWN'
    ) AS unknown_journeys,
    100.0 * COUNT(*) FILTER (
        WHERE outcome = 'INFERRED_ABANDONED'
    ) / NULLIF(COUNT(*), 0) AS inferred_abandonment_percent
FROM recovery_journey_measurements
WHERE snapshot_id = :snapshot_id
  AND started_at >= :cohort_start
  AND started_at < :cohort_end
  AND mature_at <= :data_cutoff
GROUP BY
    journey_type,
    measurement_version,
    policy_version,
    population_version;
```

Query giả định bảng đã giữ một outcome hợp lệ cho mỗi journey và snapshot. Nếu upstream join làm nhân đôi hàng, `COUNT(*)` sẽ sai; uniqueness và kiểm tra đối chiếu là điều kiện của contract.

Một group không có hàng sẽ không tự xuất hiện với 0%. Dashboard có thể bổ sung nhóm trống nhưng phải giữ trạng thái không đủ dữ liệu, không tự tạo một tỷ lệ thành công.

### 9.2. Vì sao chia counter cùng giờ dễ sai?

```text
completed ghi nhận trong giờ 10
--------------------------------
started ghi nhận trong giờ 10
```

Tử số có thể chứa journey bắt đầu từ giờ 8; mẫu số chứa journey sẽ hoàn tất sau giờ 10. Tỷ lệ có thể vượt 100% hoặc dao động mạnh dù hành vi của từng cohort không đổi.

Các counter đó hữu ích cho throughput hoặc vận hành, nhưng không phải một cohort conversion/abandonment rate. Cần nối outcome về cùng tập journey khởi đầu.

### 9.3. Snapshot và restatement

Khi sửa dữ liệu muộn, không cộng lại snapshot mới vào số liệu cũ. Mỗi snapshot cần được thay thế hoặc được chọn theo revision rõ ràng.

Không chỉ xuất counter “abandoned tăng một” nếu nhãn có thể bị rút lại trước khi snapshot ổn định. Counter không biểu diễn trực tiếp việc giảm số ca được phân loại sau restatement; cần một bảng/snapshot hoặc cơ chế đối chiếu phù hợp.

Một báo cáo lịch sử nên cho biết đang dùng revision nào. Nếu số của tuần trước thay đổi vì telemetry được khôi phục, ghi đó là sửa dữ liệu, không mô tả như một cải thiện mới của người dùng.

## 10. Ví dụ Java: tính tỷ lệ từ một partition hợp lệ

Đoạn sau minh họa Java 17+ cho bước tính cuối sau khi journey đã được phân loại. Nó không xác định H/W, không nối event và không suy luận động cơ người dùng.

```java
import java.util.Map;
import java.util.Objects;
import java.util.OptionalDouble;

public final class RecoveryAbandonmentMetric {
    public enum Outcome {
        COMPLETED,
        INFERRED_ABANDONED,
        POLICY_DENIED,
        TERMINAL_FAILED,
        EXPLICIT_CANCELLED,
        WAITING_OR_ACTIVE,
        UNKNOWN
    }

    private RecoveryAbandonmentMetric() {}

    public static OptionalDouble ratio(Map<Outcome, Long> counts) {
        Objects.requireNonNull(counts, "counts");
        long total = 0;

        for (Outcome outcome : Outcome.values()) {
            Long count = counts.get(outcome);
            if (count == null || count < 0) {
                throw new IllegalArgumentException(
                        "Every outcome must have a non-negative count");
            }
            total = Math.addExact(total, count);
        }

        if (total == 0) {
            return OptionalDouble.empty();
        }

        long abandoned = counts.get(Outcome.INFERRED_ABANDONED);
        return OptionalDouble.of(abandoned / (double) total);
    }
}
```

Một đầu vào ví dụ:

```java
Map<RecoveryAbandonmentMetric.Outcome, Long> counts = Map.of(
    RecoveryAbandonmentMetric.Outcome.COMPLETED, 620L,
    RecoveryAbandonmentMetric.Outcome.INFERRED_ABANDONED, 180L,
    RecoveryAbandonmentMetric.Outcome.POLICY_DENIED, 70L,
    RecoveryAbandonmentMetric.Outcome.TERMINAL_FAILED, 40L,
    RecoveryAbandonmentMetric.Outcome.EXPLICIT_CANCELLED, 30L,
    RecoveryAbandonmentMetric.Outcome.WAITING_OR_ACTIVE, 40L,
    RecoveryAbandonmentMetric.Outcome.UNKNOWN, 20L
);

double ratio = RecoveryAbandonmentMetric.ratio(counts).orElseThrow();
// ratio xấp xỉ 0.18; tầng hiển thị có thể đổi thành 18%.
```

Hàm yêu cầu đủ mọi outcome thay vì mặc định nhóm bị thiếu là 0. Điều này không chứng minh dữ liệu upstream đầy đủ, nhưng giúp không âm thầm bỏ một category khỏi mẫu số.

Các ca kiểm tra có ý nghĩa cho hàm gồm toàn bộ số 0 trả empty, số âm bị từ chối, thiếu outcome bị từ chối và ví dụ có đủ category trả tỷ lệ đúng. Các test pipeline riêng mới chứng minh mỗi journey được phân loại một lần và đúng cohort.

Nếu dùng dữ liệu đồng thời thay đổi, hãy truyền một snapshot bất biến hoặc bản sao ổn định. Đọc lần lượt các count đang được cập nhật không bảo đảm có một partition tại cùng thời điểm.

## 11. Phân đoạn để hiểu nguyên nhân thay vì chỉ nhìn tổng

Các chiều hữu ích có thể gồm loại recovery, phương thức proof, nhánh tự phục vụ/hỗ trợ, policy version, nhóm thiết bị, ngôn ngữ, provider route và nhóm accessibility có cách thu thập phù hợp.

Không đưa mọi chiều vào mọi biểu đồ. Mỗi phân đoạn cần đủ mẫu, cùng định nghĩa và cùng mức trưởng thành.

### 11.1. Tổng tăng dù từng nhóm cải thiện

Ví dụ hai phiên bản với cơ cấu journey khác nhau:

| Giai đoạn | Nhóm nhanh | Abandon nhóm nhanh | Nhóm chậm | Abandon nhóm chậm | Tổng |
| --- | ---: | ---: | ---: | ---: | ---: |
| Trước | 800 | 80 = 10% | 200 | 80 = 40% | 160/1000 = 16% |
| Sau | 200 | 16 = 8% | 800 | 280 = 35% | 296/1000 = 29,6% |

Từng nhóm giảm tỷ lệ, nhưng tổng tăng vì tỷ trọng nhóm chậm lớn hơn. Đây là ví dụ số học cho thấy mix thay đổi có thể làm kết luận tổng khác kết luận theo nhóm.

Nếu dùng trọng số cố định 80% nhóm nhanh và 20% nhóm chậm của giai đoạn trước:

```text
Tỷ lệ sau chuẩn hóa theo mix cũ
= 0,8 × 8% + 0,2 × 35%
= 13,4%
```

13,4% là một phép chuẩn hóa theo bộ trọng số công bố, không thay thế tỷ lệ thực 29,6% và không tự chứng minh nguyên nhân là thay đổi sản phẩm. Báo cả cơ cấu, số mẫu và cách chuẩn hóa khi dùng.

### 11.2. Population bot và người dùng chưa xác định

Một luồng phục hồi có thể nhận nhiều request tự động hoặc không liên quan một account thật. Không thể biết mọi journey là người dùng hợp lệ chỉ từ việc nó bắt đầu hay hoàn tất.

Có thể báo một view toàn traffic trong phạm vi và một view theo quy tắc lọc automation rõ, có version. Giữ số lượng bị loại và phần chưa xác định.

Không định nghĩa “legitimate user” là những journey hoàn tất rồi tính abandonment trên tập đó. Cũng không loại toàn bộ journey bị denied rồi tuyên bố trải nghiệm của người hợp lệ đã được đo đầy đủ; false positive có thể nằm chính trong nhóm bị loại.

### 11.3. Không so các policy khác nhau như cùng một bài toán

Luồng mất toàn bộ factor hoặc tài khoản đặc quyền có thể cần nhiều proof và thời gian hơn. Tỷ lệ bỏ dở cao hơn không tự chứng minh một nhóm làm UX kém.

Đối chiếu horizon, điểm bắt đầu, outcome và mức bảo đảm. Nếu không thể chuẩn hóa hợp lý, báo riêng và giải thích giới hạn thay vì xếp hạng bằng một số chung.

## 12. Dashboard và cảnh báo có thể hành động

Một dashboard tối thiểu nên thể hiện:

| Nhóm thông tin | Nội dung |
| --- | --- |
| Contract | Unit, cohort, H/W/L, population và measurement version |
| Kích thước | Số mature journey và số chưa mature |
| Outcome mix | Completed, abandonment suy luận và các outcome riêng |
| Chất lượng | Unknown, event lag, start/completion coverage |
| Funnel | Điểm rơi theo nhánh và thời gian tới milestone |
| Phân đoạn | Những nhóm ổn định có đủ dữ liệu |
| Vận hành | Provider latency, queue age, lỗi API, review backlog |
| Bảo mật | Policy denial, proof abuse và các guardrail phù hợp |
| Lịch sử | Incident, rollout, policy/measurement changes và restatement |

Hiển thị khoảng cohort cùng timezone. Nếu nhóm vận hành xem theo Asia/Saigon nhưng pipeline chốt ngày UTC, phải xác định khoảng start/end chính xác để không so hai ngày có tập journey khác nhau.

### 12.1. Cohort ổn định có độ trễ tự nhiên

Một tỷ lệ cần horizon đủ dài sẽ không phải chỉ số tức thời. Đừng làm nó “real time” bằng cách gán mọi journey mới chưa xong thành abandoned.

Để phát hiện sự cố nhanh, theo dõi leading signals như SMS/email submit latency, queue age, bước proof lỗi bất thường, frontend error và ingestion lag. Sau đó xác nhận tác động bằng cohort đã mature.

Không gọi một ước lượng sớm là số cuối mà không nêu mô hình, độ bất định và điều kiện dữ liệu.

### 12.2. Monitoring và kho phân tích có vai trò khác nhau

Prometheus khuyến cáo tránh label có cardinality cao như user ID hoặc email; mỗi tổ hợp label tạo thêm time series. [Prometheus — Metric and label naming](https://prometheus.io/docs/practices/naming/).

Không dùng journey ID, token fingerprint, recipient hay timestamp riêng từng cohort làm label không giới hạn. Dữ liệu chi tiết theo journey nên nằm trong hệ thống phân tích có quyền và vòng đời phù hợp.

Có thể xuất các aggregate/snapshot với số chiều được kiểm soát để monitoring, kèm thời điểm cutoff và trạng thái freshness. Một metric gauge của snapshot mới nhất cần được cập nhật đúng phiên bản, không cộng thêm như một batch event mới.

### 12.3. Ngưỡng cảnh báo và dữ liệu ít

Một thay đổi từ 0/2 sang 1/2 làm tỷ lệ lên 50%, nhưng chỉ có thêm một journey. Luôn hiển thị mẫu số và dùng quy tắc xử lý low volume.

Ngưỡng cần dựa trên baseline phù hợp, thời gian đủ quan sát và tác động của phân đoạn; không chọn một mức chung 5% hoặc 10% như chuẩn ngành.

Nếu muốn kết luận một thay đổi có ý nghĩa thống kê, cần phương pháp phù hợp với đơn vị randomization, sự phụ thuộc giữa các journey của cùng subject và việc xem nhiều phân đoạn. Tỷ lệ điểm đơn lẻ chưa đủ cho kết luận đó.

## 13. Giảm abandonment cùng với giữ điều kiện an toàn

Những cải thiện thường đáng đánh giá gồm hướng dẫn rõ hơn, giảm bước nhập không cần thiết, chuyển thiết bị đúng cách, thông báo thời gian chờ, hỗ trợ accessibility và sửa lỗi delivery.

OWASP khuyến nghị phản hồi quên mật khẩu nhất quán để giảm enumeration và bảo vệ trước yêu cầu tự động quá mức. Khi tối ưu funnel, các kiểm soát đó vẫn cần được duy trì. [OWASP Forgot Password Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html).

Không bỏ kiểm tra proof, cho token dùng nhiều lần hoặc cấp session đầy đủ sớm chỉ để làm completion tăng. Một journey của attacker hoàn tất cũng có thể làm một metric chuyển đổi trông đẹp hơn.

### 13.1. Cặp chỉ số và guardrail

| Mục tiêu trải nghiệm | Chỉ số cần xem cùng |
| --- | --- |
| Giảm chờ SMS/email | Delivery latency, duplicate send, chi phí và spam |
| Giảm khó khăn nhập mã | Proof failure, retry budget và rate-limit outcomes |
| Rút ngắn recovery MFA | False accept, unauthorized factor changes và mức bảo đảm |
| Giảm hồ sơ người dùng phải cung cấp | Proof sufficiency, dispute và khả năng hỗ trợ |
| Giảm review thủ công | False positive/negative và chất lượng quyết định |
| Tăng cross-device completion | Binding, replay, session handoff và privacy |
| Giảm abandonment của nhóm accessibility | Completion, lỗi tương tác và kiểm soát xác minh tương đương |

Một số nhãn fraud hoặc account takeover chỉ có sau điều tra và có thể chưa đầy đủ. Báo độ trễ, coverage và điều kiện xác nhận; không coi “chưa có báo cáo lừa đảo” là bằng chứng không có false accept.

### 13.2. Thử nghiệm phải giữ contract ổn định

Nếu thử hai giao diện, nên giữ định nghĩa start, completion, horizon và outcome để so sánh được. Ghi experiment assignment theo cách không chứa secret và không làm caller tự chọn policy yếu hơn.

Không phân nhóm bằng một kết quả chỉ xuất hiện sau can thiệp, ví dụ chỉ so những người đã vượt proof. Điều đó có thể loại chính những người bị giao diện mới làm khó trước proof.

Một cải thiện có thể làm abandonment giảm nhờ đường hỗ trợ hiệu quả hơn. Khi đó báo handoff và completion toàn journey, không giả định người rời self-service là thất bại nếu họ tiếp tục hợp lệ ở kênh khác.

## 14. Ma trận kiểm thử dữ liệu đo lường

| ID | Tình huống | Điều kiện đạt |
| --- | --- | --- |
| RAR-01 | Denominator không có journey | Trả no data/undefined, không báo 0% |
| RAR-02 | Cohort mới chưa hết H+L | Tách khỏi tỷ lệ ổn định |
| RAR-03 | Resend và retry cùng journey | Không tăng mẫu số ngoài contract |
| RAR-04 | Duplicate start/completion event | Một journey, một milestone logic |
| RAR-05 | Completion trong H nhưng ingest muộn | Restatement theo event time và revision |
| RAR-06 | Completion sau H | Không giả làm completion trong H; có view horizon dài |
| RAR-07 | Manual/security wait hợp lệ | Không tự suy luận thành abandonment |
| RAR-08 | Một lần nhập mã sai rồi thành công | Không gán terminal failure sai |
| RAR-09 | Policy denial cuối | Có outcome riêng, không gọi là user tự bỏ |
| RAR-10 | Telemetry không đủ hoặc mâu thuẫn | Unknown và quality reason rõ |
| RAR-11 | Chuyển thiết bị có liên kết an toàn | Tiếp tục đúng journey theo contract |
| RAR-12 | Link scanner mở email URL | Không tự coi là user proof/completion |
| RAR-13 | Completed và cancelled mâu thuẫn | Dùng state/version nguồn chuẩn hoặc báo unknown |
| RAR-14 | Snapshot mới thay số cũ | Không cộng trùng qua các revision |
| RAR-15 | Outcome partition | Tổng category bằng D, không journey đa nhóm |
| RAR-16 | Cơ cấu journey thay đổi | Báo mix và các tỷ lệ theo nhóm |
| RAR-17 | Filter automation đổi version | Phân biệt thay population với cải thiện hành vi |
| RAR-18 | Export monitoring | Không có label hoặc payload chứa secret/PII không cần |
| RAR-19 | Handoff sang hỗ trợ rồi hoàn tất | Tính theo milestone và quy tắc journey đã công bố |
| RAR-20 | Measurement code đổi H/W/completion | Version và chú thích comparability được cập nhật |

Các test nên dùng event fixture có cả `occurredAt` và `ingestedAt`, nhiều version và những timeline ở sát biên. So sánh trực tiếp với expected journey outcomes, không chỉ snapshot của một biểu đồ.

Không cần dữ liệu thật để kiểm tra logic cohort. Dùng dữ liệu tổng hợp và namespace riêng; việc kiểm thử không phải lý do sao chép token hoặc hồ sơ người dùng vào kho phát triển.

## 15. Diễn giải một báo cáo và quyết định bước tiếp

Một report minh họa có thể có cấu trúc:

```text
METRIC: inferred recovery abandonment at horizon
UNIT: journey
COHORT: [cohort_start, cohort_end), timezone explicitly stated
DATA_CUTOFF: fixed snapshot cutoff
CONTRACT: measurement/population/policy versions
HORIZON: per journey type, frozen by contract
MATURE_STARTS: D
INFERRED_ABANDONED: A
RATE: A / D if D > 0
OTHER_OUTCOMES: complete partition, including unknown and waiting
QUALITY: ingestion lag, coverage and restatement status
SEGMENTS: sample counts and consistent definitions
GUARDRAILS: security and reliability observations with limitations
NEXT_ACTION: hypothesis, owner and evidence needed
```

Không điền số PASS hoặc kết luận nguyên nhân khi mới có query. Một phát hiện nên nối được dấu hiệu với giả thuyết có thể kiểm tra.

Ví dụ: “Nhóm SMS route B tăng inactivity trước proof, cùng thời gian queue age tăng; chưa đủ dữ liệu để phân biệt lỗi provider với người dùng không nhìn thấy hướng dẫn.” Bước tiếp là đối chiếu delivery và UX của nhóm đó.

Một diễn giải quá mạnh sẽ là “người dùng không muốn xác minh MFA nên cần bỏ bước MFA”. Chỉ số quan sát không tự chứng minh động cơ hoặc cho phép hạ mức bảo đảm.

### 15.1. Ưu tiên hành động từ kết quả

Nếu UNKNOWN tăng, kiểm tra pipeline trước khi kết luận UX xấu đi. Nếu WAITING_OR_ACTIVE tăng cùng backlog review, xử lý khả năng vận hành và thông tin chờ. Nếu abandonment tăng ở một bước nhập nhưng delivery ổn định, xem hướng dẫn, lỗi tương tác và tính khả dụng của phương thức proof.

Khi POLICY_DENIED tăng, có thể đang chặn một chiến dịch lạm dụng hoặc tăng false positive; cần dữ kiện riêng để phân biệt. Không xem mọi denied là thành công bảo mật, cũng không xem mọi denied là lỗi sản phẩm.

Sau thay đổi, so cohort mature cùng contract và giữ các guardrail. Nếu phải đổi contract, công bố chuỗi đo mới và phạm vi so sánh được.

## 16. Bài tập tình huống

**Bài tập A — Công thức 1 trừ success.** Một cohort có 620 completed và 380 chưa completed, trong đó chỉ 180 đủ điều kiện inactivity. Lập bảng outcome còn lại và giải thích vì sao 38% không đồng nghĩa 18% abandonment suy luận.

**Bài tập B — Cohort chưa trưởng thành.** Luồng review thủ công cần một horizon dài hơn luồng password reset. Thiết kế maturity và dashboard để cohort mới không bị chấm bỏ dở sớm, nhưng thời gian chờ của người dùng vẫn được phản ánh.

**Bài tập C — Event tới muộn.** Completion xảy ra trước deadline nhưng được ingest sau cutoff; một completion khác thực sự xảy ra sau deadline. Xác định snapshot nào cần restatement và view horizon nào phản ánh từng trường hợp.

**Bài tập D — Retry làm mẫu số phình.** Một người resend ba lần và chuyển từ mobile sang desktop. Chốt unit và quy tắc liên kết, chỉ ra dữ liệu nào được phép dùng mà không đưa recovery token vào analytics.

**Bài tập E — Tổng xấu đi, từng nhóm tốt hơn.** Dùng bảng nhóm nhanh/chậm để tính tỷ lệ tổng và tỷ lệ chuẩn hóa theo trọng số cố định. Nêu giới hạn của việc quy nguyên nhân từ hai phép tính đó.

**Bài tập F — Tối ưu nhầm.** Một thay đổi tăng completion bằng cách cho phép phiên enrollment gọi API nhạy cảm trước khi proof hoàn tất. Đề xuất guardrail và bằng chứng để phát hiện việc chỉ số trải nghiệm được cải thiện bằng cách mở một đường cấp quyền sai.

Một recovery abandonment rate có giá trị khi gắn với một tập journey và khoảng quan sát xác định, tách được outcome hệ thống khỏi suy luận hành vi, và được dùng cùng dữ liệu chất lượng, khả dụng lẫn bảo mật.
