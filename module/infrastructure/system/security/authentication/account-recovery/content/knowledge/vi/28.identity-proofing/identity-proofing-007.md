# Identity proofing retention — Quản lý thời hạn lưu dữ liệu xác minh danh tính

## 1. Mục tiêu và phạm vi

Trong chương **Identity Proofing** của module **SECURITY_AUTHENTICATION_ACCOUNT_RECOVERY**, retention là chính sách và cơ chế quyết định dữ liệu xác minh danh tính được giữ ở đâu, để làm gì, trong bao lâu và kết thúc vòng đời bằng cách nào.

Khi người dùng mất mật khẩu, MFA, passkey hoặc thiết bị xác thực, recovery có thể phát sinh ảnh giấy tờ, dữ liệu trích xuất, selfie, video, kết quả đối sánh, quyết định xét duyệt và audit. Những dữ liệu này giúp giải quyết một yêu cầu nhạy cảm, đồng thời tạo thêm rủi ro nếu bị thu thập quá mức hoặc giữ lại không có điểm kết thúc.

Bài học tập trung vào thiết kế retention có thể thực thi: phân loại dữ liệu, xác định mốc thời gian, kiểm soát ngoại lệ, xóa trên nhiều hệ thống và kiểm chứng trạng thái hoàn tất. Các mô hình và mã giả là ví dụ thiết kế, không phải lịch lưu bắt buộc cho mọi tổ chức.

Nguyên tắc trung tâm là: **giữ đúng dữ liệu cần cho mục đích được chấp nhận, bảo vệ nó trong suốt thời gian lưu, rồi xử lý hết hạn trên mọi nơi thuộc phạm vi trách nhiệm.**

## 2. Retention khác với hiệu lực bằng chứng và quyền truy cập

### 2.1. Các loại thời hạn cần tách biệt

| Khái niệm | Câu hỏi được trả lời | Ví dụ |
| --- | --- | --- |
| Retention của dữ liệu | Dữ liệu được phép hoặc cần giữ đến khi nào? | Ảnh giấy tờ thuộc lịch lưu của loại hồ sơ |
| Hiệu lực của proof hoặc challenge | Output còn được chấp nhận cho bước xác minh không? | Mã gửi cho một attempt đã hết hạn |
| Độ mới của kết quả xác minh | Kết quả cũ có đủ cho quyết định hiện tại không? | Hồ sơ đã proofing từ trước cần đánh giá lại |
| Thời hạn của recovery grant | Quyền khôi phục còn được sử dụng không? | Grant chỉ cho đăng ký lại MFA |
| Hiệu lực của session | Session còn được phép truy cập không? | Phiên bị thu hồi sau recovery |
| Thời hạn của URL tải bằng chứng | Link còn mở được đối tượng không? | URL ký tạm thời hết hạn |

Ảnh còn nằm trong storage không có nghĩa proof từ ảnh đó còn đủ để cấp quyền hôm nay. URL hết hạn không có nghĩa object đã bị xóa. Grant đã dùng không có nghĩa mọi dữ liệu của case phải lập tức biến mất.

Một thiết kế dùng chung trường `expires_at` cho tất cả các ý nghĩa trên dễ dẫn đến giữ dữ liệu quá lâu hoặc cấp quyền sai.

### 2.2. Mã hóa và giới hạn truy cập không thay thế lịch xóa

Mã hóa giúp bảo vệ nội dung. Phân quyền giới hạn người được đọc. Retention quyết định lý do và thời gian tiếp tục giữ nội dung.

“Đã mã hóa” không tự tạo căn cứ giữ ảnh giấy tờ vô thời hạn. “Chỉ nhân viên an ninh đọc được” cũng chưa mô tả khi nào dữ liệu hết mục đích.

Ngược lại, đặt lịch xóa không thay thế kiểm soát truy cập trong thời gian chờ. Một ảnh dự kiến xóa ngày mai vẫn cần được bảo vệ ngay hôm nay.

## 3. Căn cứ xây dựng chính sách

### 3.1. Không có một số ngày chung cho mọi dữ liệu proofing

Thời hạn phải được xác định theo mục đích, loại dữ liệu, profile proofing, yêu cầu áp dụng và mô hình dịch vụ. Bài không đưa một mốc 30, 90 hay 365 ngày như quy tắc phổ quát.

NIST SP 800-63A-4 yêu cầu quy trình được tài liệu hóa về lưu giữ, bảo vệ và xóa dữ liệu cá nhân, nhạy cảm và sinh trắc học; nội dung này cũng cần xét khi dịch vụ ngừng hoặc chuyển giao hoạt động. [NIST SP 800-63A-4 — Identity Service Documentation and Records](https://pages.nist.gov/800-63-4/sp800-63a/ial-general/#identity-service-documentation-and-records)

Trong triển khai, đội sản phẩm, an ninh, vận hành và bộ phận phụ trách yêu cầu pháp lý hoặc hồ sơ cần thống nhất một lịch có chủ sở hữu. Không để developer tự chọn thời hạn chỉ vì bucket có sẵn cấu hình lifecycle.

### 3.2. Mục đích phải cụ thể và kiểm tra được

Một mục đích có thể là:

- Hoàn tất case recovery đang xử lý.
- Giải quyết một khoảng thời gian khiếu nại được chính sách xác định.
- Chứng minh căn cứ của quyết định proofing bằng record tối thiểu.
- Xử lý một cuộc điều tra có phạm vi và thẩm quyền.
- Duy trì dữ liệu bắt buộc của profile đang áp dụng.

“Có thể hữu ích sau này” chưa phải mô tả đủ cụ thể cho lịch lưu. Nếu muốn dùng dữ liệu cho mục đích khác như huấn luyện mô hình, đó là một quyết định xử lý riêng cần được đánh giá; không tự có quyền chỉ vì dữ liệu đã nằm trong hệ thống.

### 3.3. Xung đột yêu cầu phải được giải quyết rõ

Có thể tồn tại một yêu cầu giữ tối thiểu và một giới hạn thời gian lưu theo mục đích hoặc quy tắc khác. Nếu hai yêu cầu xung đột, hệ thống cần báo để chủ chính sách giải quyết.

Không luôn lấy thời hạn dài nhất cho mọi loại dữ liệu mà bỏ qua giới hạn tương ứng. Cũng không lấy thời hạn ngắn nhất rồi xóa cả hồ sơ phải được bảo toàn.

Kết quả phải trở thành một chính sách có phiên bản, phạm vi và lý do được phê duyệt, thay vì logic tùy ý trong một cron job.

## 4. Lập danh mục dữ liệu và các bản sao

### 4.1. Một case có nhiều nhóm dữ liệu

| Nhóm dữ liệu | Vai trò | Câu hỏi retention |
| --- | --- | --- |
| Ảnh hoặc bản quét giấy tờ gốc | Evidence đầu vào | Có cần giữ toàn bộ sau quyết định không? |
| Ảnh crop, thumbnail, bản tăng chất lượng | Dẫn xuất phục vụ xử lý | Có hết hạn cùng nguồn không? |
| OCR và thuộc tính trích xuất | Dữ liệu phục vụ validation | Trường nào cần tiếp tục giữ? |
| Selfie, video và mẫu sinh trắc học | Verification hoặc mục đích được chấp nhận | Loại mẫu nào được lưu theo profile? |
| Template hoặc embedding | Dữ liệu dẫn xuất có thể phục vụ đối sánh | Có còn khả năng liên kết hoặc nhận diện không? |
| Kết quả của provider | Căn cứ kỹ thuật và quyết định | Có chứa dữ liệu thô không cần thiết không? |
| Record quyết định proofing | Giải thích kết quả và profile | Có thể giữ record tối thiểu thay ảnh không? |
| Consent và phiên bản notice | Ghi nhận điều đã được thông báo hoặc chấp thuận | Cần giữ những trường nào? |
| Audit truy cập và thay đổi | Điều tra, phát hiện lạm dụng | Cần lịch lưu độc lập nào? |
| Upload chưa hoàn tất | Dữ liệu tạm | Ai dọn nếu không có case hoàn chỉnh? |

Không nên gắn một TTL chung vào case rồi cho rằng mọi thành phần có cùng nhu cầu. Ảnh gốc có thể hết mục đích trước record quyết định; mẫu sinh trắc học phục vụ một profile có thể có điều kiện khác.

### 4.2. Tìm dữ liệu ở ngoài database nghiệp vụ

Phạm vi cần kiểm kê có thể bao gồm:

~~~text
object storage và các object version
database, read replica và history table
cache, search index và vector store
temporary upload và nơi xử lý OCR
queue, retry payload và dead-letter queue
logs, traces, crash dump và APM
provider và các bên xử lý tiếp
ticket, bản xuất và công cụ hỗ trợ
backup, snapshot và bản restore thử nghiệm
~~~

Nếu dữ liệu nhạy cảm được đưa vào telemetry hoặc ticket, đó là một bản sao cần quản lý, không phải lý do để loại khỏi phạm vi retention.

Cách tốt hơn thường là không tạo bản sao không cần thiết ngay từ đầu: queue chỉ mang reference, log chỉ ghi mã sự kiện và nhân viên dùng viewer có quyền thay vì tải ảnh về máy.

### 4.3. Dữ liệu dẫn xuất không tự trở thành vô danh

Bỏ họ tên nhưng giữ mã hồ sơ có thể nối về tài khoản vẫn là dữ liệu có thể liên kết. Băm số giấy tờ cũng không tự làm dữ liệu vô danh, nhất là khi miền giá trị có thể bị dò hoặc còn bảng đối chiếu.

Template sinh trắc học, embedding và các tín hiệu chống gian lận cần được đánh giá theo khả năng sử dụng và liên kết thực tế. Không phân loại chúng là “chỉ dữ liệu kỹ thuật” để giữ mãi.

Dữ liệu thống kê chỉ nên được xem là đã vô danh sau khi có đánh giá phù hợp về khả năng tái nhận diện và các dữ liệu có thể kết hợp.

## 5. Tách evidence thô khỏi record quyết định

### 5.1. Không cần sao chép toàn bộ ảnh vào audit

Một record quyết định tối thiểu có thể chứa:

~~~text
assessment_reference
account_or_applicant_reference
case_reference
framework_and_revision
profile_reference
proofing_type
validation_and_verification_method_references
decision
decision_time
policy_version
authorized_decision_maker_reference
retention_policy_reference
~~~

Những trường nào thực sự cần phải do chính sách quy định. Mã tài khoản và reference vẫn cần phân quyền, lịch lưu và bảo vệ; tối thiểu không đồng nghĩa công khai.

NIST mô tả các thông tin cần duy trì trong subscriber account, gồm record bước proofing, mức đạt và consent liên quan; việc chấm dứt tài khoản phải đi cùng xử lý dữ liệu theo chính sách lưu và tiêu hủy đã tài liệu hóa. [NIST SP 800-63A-4 — Subscriber Accounts](https://pages.nist.gov/800-63-4/sp800-63a/accounts/)

### 5.2. Xóa ảnh không được sửa lịch sử quyết định

Nếu ảnh đã được xử lý hết vòng đời đúng chính sách, record có thể phản ánh:

~~~text
proofing_decision = PASSED_UNDER_PROFILE_P
raw_evidence_availability = PURGED_UNDER_POLICY_V
~~~

Không đổi kết quả lịch sử thành “chưa từng proofing” chỉ để giải thích ảnh không còn. Cũng không tuyên bố có thể thực hiện lại validation trên một file đã bị xóa.

Khi cần proofing mới, hệ thống yêu cầu thu thập lại qua context và quyền phù hợp. Kết quả cũ không tự trở thành một grant recovery mới.

### 5.3. Có profile cần giữ một loại dữ liệu cụ thể

Không thể đặt quy tắc “mọi sinh trắc học đều xóa ngay sau đối sánh” rồi vẫn tuyên bố đáp ứng mọi profile. SP 800-63A-4 có yêu cầu thu thập và lưu mẫu sinh trắc học tại IAL3 cho các mục đích được nêu trong tiêu chuẩn. [NIST SP 800-63A-4 — IAL3 Attribute Requirements](https://pages.nist.gov/800-63-4/sp800-63a/ial/#attribute-requirements)

Điều này không tạo quyền giữ tất cả ảnh, video và dẫn xuất vô thời hạn. Cần xác định chính xác dữ liệu, mục đích và lịch áp dụng.

## 6. Biểu diễn lịch lưu theo loại dữ liệu và sự kiện

### 6.1. Một quy tắc retention cần những thành phần nào?

~~~text
RetentionRule
    policy_id
    policy_version
    data_category
    processing_purpose
    applicable_profile_or_context
    retention_anchor_event
    approved_retention_duration_or_end_condition
    permitted_disposition
    hold_handling
    deletion_service_objective
    owner
~~~

Các giá trị có thể là khoảng thời gian hoặc điều kiện kết thúc được quy định rõ. Nếu dùng điều kiện như “đến khi chấm dứt quan hệ dịch vụ”, cần có sự kiện và cơ chế thực sự ghi nhận điều đó.

Không dùng giá trị null như một cách ngầm giữ vĩnh viễn. Nếu thiếu rule, cần chặn cấu hình hoặc tạo ngoại lệ có chủ sở hữu để xử lý.

### 6.2. Chọn anchor đúng nghĩa

Các anchor có thể là:

- Upload được tiếp nhận.
- Attempt bị bỏ dở hoặc hết hạn.
- Case được quyết định.
- Case được đóng sau xử lý khiếu nại.
- Tài khoản chấm dứt.
- Một hold được giải phóng.

Không tự reset thời hạn mỗi lần có người mở viewer, retry API hoặc chỉnh nhãn nội bộ. Nếu hoạt động đó không phải sự kiện được policy định nghĩa, nó không tạo mục đích lưu mới.

Case không bao giờ đóng cũng cần cơ chế xử lý: thời hạn case, review định kỳ và đường kết thúc cho hồ sơ bỏ dở. Nếu chỉ tính từ case_closed_at nhưng case luôn OPEN, dữ liệu có thể bị giữ vô hạn do lỗi nghiệp vụ.

### 6.3. Phân biệt đủ điều kiện xóa và đã xóa

Một record dữ liệu có thể lưu:

~~~text
retention_anchor_at
retention_policy_id
retention_policy_version
scheduled_disposition_at
disposition_state
disposition_started_at
active_storage_purged_at
provider_purge_state
backup_disposition_state
disposition_completed_at
~~~

Tên trường tùy sản phẩm. Chúng cần làm rõ thời điểm dự kiến, tiến độ xử lý và phạm vi đã hoàn tất.

Scheduler chạy mỗi đêm có thể tạo độ trễ sau thời điểm đến hạn. Độ trễ cần được xác định và đo; không nói “xóa đúng hạn” chỉ vì đã đưa item vào queue.

### 6.4. Ví dụ cấu hình khái niệm

~~~yaml
policy_id: proofing-recovery-evidence
policy_version: 4

rules:
  - category: TEMPORARY_UPLOAD
    anchor: UPLOAD_ACCEPTED
    duration: APPROVED_TEMP_UPLOAD_DURATION
    disposition: PURGE_ALL_TEMPORARY_COPIES

  - category: RAW_DOCUMENT_IMAGE
    anchor: CASE_DISPOSITION_FINALIZED
    duration: APPROVED_RAW_EVIDENCE_DURATION
    disposition: PURGE_RAW_AND_LINKED_DERIVATIVES

  - category: PROOFING_DECISION_RECORD
    anchor: RECORDS_POLICY_DEFINED_EVENT
    duration: APPROVED_DECISION_RECORD_DURATION
    disposition: DELETE_OR_MINIMIZE_AS_APPROVED

hold:
  authority_required: true
  scoped_to_relevant_assets: true
  periodic_review_required: true
~~~

Đây là mô hình học tập. Các duration là placeholder cho giá trị đã được phê duyệt, không phải tên cấu hình của một sản phẩm có sẵn.

Quy tắc cho ảnh gốc không được áp dụng máy móc lên dữ liệu thuộc một yêu cầu profile hoặc mục đích khác còn hiệu lực.

## 7. Hold và ngoại lệ lưu giữ

### 7.1. Hold phải có phạm vi và thẩm quyền

Một legal hold hoặc hold điều tra được áp dụng hợp lệ có thể tạm dừng xử lý một số dữ liệu. Record hold nên chỉ ra:

~~~text
hold_reference
authorized_issuer
reason_category
scope
effective_at
review_at
release_condition
released_at
~~~

Chi tiết nhạy cảm của cuộc điều tra có thể được giữ ở hệ thống có quyền hạn khác. Không đưa toàn bộ nội dung vào metadata mà mọi nhân viên hỗ trợ đều đọc được.

Không cho bất kỳ nhân viên nào nhập ghi chú “fraud” để giữ toàn bộ hồ sơ vô thời hạn.

### 7.2. Hold không mở rộng mọi quyền sử dụng

Dữ liệu đang được giữ cho một vụ việc không tự được dùng cho marketing, huấn luyện mô hình hoặc hỗ trợ không liên quan.

Hold cũng không có nghĩa mọi credential và session của tài khoản phải tiếp tục có hiệu lực. Quyết định lưu bằng chứng và quyết định thu hồi quyền truy cập là hai việc khác nhau.

### 7.3. Giải phóng hold phải quay lại lịch xử lý

Khi hold kết thúc, scheduler cần đánh giá lại dữ liệu đã quá hạn. Không mặc định bắt đầu lại toàn bộ retention từ ngày release nếu policy không quy định như vậy.

Nếu một phần dữ liệu có nhiều mục đích hợp lệ, hệ thống cần xác định phần nào còn cần giữ. Một hold cho một ảnh không tự kéo dài mọi bản xuất hoặc mọi hồ sơ của cùng người.

## 8. Bảo vệ dữ liệu trong thời gian còn lưu

### 8.1. Truy cập theo nhiệm vụ và trạng thái

Nhân viên hỗ trợ thường chỉ cần biết case đang chờ gì; họ không nhất thiết cần tải toàn bộ giấy tờ.

Viewer evidence có thể yêu cầu:

- Quyền phù hợp với tenant và loại case.
- Một nhiệm vụ đang được giao.
- Lý do truy cập nếu cần.
- Context xác thực đáp ứng chính sách.
- Ghi audit thao tác xem hoặc xuất.
- Giới hạn thời gian truy cập.

Link ký tạm thời cần phù hợp mục đích và có thời hạn. Tuy nhiên, một URL đã phát hành có thể có hành vi thu hồi phụ thuộc cơ chế storage; không giả định xóa quyền trong ứng dụng luôn làm URL cũ mất hiệu lực ngay.

### 8.2. Hạn chế bản sao do vận hành tạo ra

Tránh gửi ảnh giấy tờ vào chat nội bộ, email hỗ trợ hoặc công cụ theo dõi lỗi. Nếu quy trình cho phép xuất, cần biết bản xuất đi đâu, ai sở hữu và vòng đời ra sao.

Dữ liệu proofing không nên được dùng nguyên trạng trong môi trường phát triển hoặc demo. Một bản backup được restore để kiểm tra cũng cần chính sách truy cập và xử lý riêng.

Mã hóa và quản lý khóa phải đi cùng kiểm soát người được giải mã. Quyền đọc storage không nên mặc nhiên kéo theo quyền mở mọi evidence.

## 9. Pipeline xóa có thể kiểm chứng

### 9.1. Vòng đời minh họa của dữ liệu

~~~mermaid
stateDiagram-v2
    [*] --> RETAINED
    RETAINED --> ELIGIBLE_FOR_DISPOSITION: Đến hạn theo policy
    ELIGIBLE_FOR_DISPOSITION --> ON_HOLD: Có hold hợp lệ
    ON_HOLD --> ELIGIBLE_FOR_DISPOSITION: Giải phóng và đánh giá lại
    ELIGIBLE_FOR_DISPOSITION --> PURGE_PENDING: Tạo kế hoạch xử lý
    PURGE_PENDING --> PURGING: Kiểm tra lại điều kiện
    PURGING --> PARTIALLY_PURGED: Chưa xong mọi hệ thống
    PARTIALLY_PURGED --> PURGING: Retry có kiểm soát
    PURGING --> PURGED_WITHIN_DECLARED_SCOPE: Đủ xác nhận theo phạm vi
    PURGED_WITHIN_DECLARED_SCOPE --> [*]
~~~

Một trạng thái duy nhất `deleted = true` khó thể hiện trường hợp storage chính đã xóa nhưng provider vẫn đang xử lý.

Tên cuối dùng phạm vi được công bố vì không phải mọi hệ thống đều hỗ trợ xóa tức thì từng item trong backup. Phần còn lại phải có chính sách và trạng thái rõ, không bị giấu dưới chữ “đã xóa”.

### 9.2. Các bước thực hiện

1. Xác định asset đến hạn và rule có hiệu lực.
2. Nạp quyền sở hữu, liên kết dữ liệu và hold hiện tại.
3. Tạo kế hoạch xóa có định danh và phiên bản.
4. Ngăn hoặc điều phối các thao tác có thể tạo thêm bản sao trong phạm vi đang xóa.
5. Xử lý storage chính, dẫn xuất, cache, index và các nơi đã kiểm kê.
6. Yêu cầu bên xử lý thực hiện và thu nhận trạng thái phù hợp.
7. Theo dõi backup theo chính sách đã định.
8. Đối soát kết quả, ghi receipt tối thiểu và cảnh báo phần quá hạn.

Không coi một HTTP 202 từ provider là xác nhận mọi bản sao đã bị purge. Cần hiểu chính xác hợp đồng của API: đã tiếp nhận yêu cầu, đã lên lịch hay đã hoàn tất trong phạm vi nào.

### 9.3. Chống race với upload, review và hold mới

Một hold có thể được tạo sau khi scheduler chọn asset. Một worker OCR có thể tạo thumbnail sau khi ảnh gốc đã bị xóa.

Cần điều phối các điểm có tác dụng bằng version, trạng thái và cơ chế đồng thời phù hợp:

- Upload và callback phải kiểm tra case hoặc asset còn nhận dữ liệu không.
- Worker tạo dẫn xuất phải tôn trọng generation và trạng thái disposition.
- Worker xóa kiểm tra lại hold trước bước không thể đảo ngược.
- Tạo hold và tiến hành xóa cần có quy tắc tuyến tính hóa rõ trong hệ thống có thẩm quyền.
- Kết quả đến muộn không được làm dữ liệu đã purge sống lại.

Không thể bảo đảm toàn bộ dịch vụ ngoài cùng tham gia một database transaction. Cần xác định điểm chấp nhận, trạng thái trung gian và cách bù hoặc từ chối khi không còn đủ điều kiện.

### 9.4. Mã giả khái niệm

~~~text
disposeProofingAsset(assetReference, expectedGeneration):
    asset = loadAssetFromAuthoritativeRegistry(assetReference)
    requireCorrectTenantAndOwnership(asset)

    decision = evaluateCurrentRetentionAndHold(asset)
    if decision is not eligible:
        recordDeferredDispositionWithoutCopyingEvidence()
        return

    plan = claimDispositionPlanAtomically(
        asset, expectedGeneration, decision.policyVersion
    )

    coordinateNoNewCopiesAndRecheckHold(plan)

    for location in plan.requiredLocations:
        result = disposeUsingSupportedMechanism(location, plan)
        persistLocationResult(plan, location, result)

    if allDeclaredCompletionConditionsMet(plan):
        recordMinimalDispositionReceipt(plan)
        markCompletedForDeclaredScope(plan)
    else:
        keepPartialStateAndScheduleRetryOrEscalation(plan)
~~~

Mã giả mô tả trách nhiệm, không phải mã production đầy đủ. Một lỗi xóa không được làm hệ thống đánh dấu thành công rồi bỏ asset khỏi mọi lần quét tiếp theo.

### 9.5. Retry phải an toàn

Lệnh xóa cần idempotent hoặc có cơ chế nhận biết lần xử lý cũ. “Object không tồn tại” có thể là kết quả phù hợp nếu đúng object, đúng version và đúng phạm vi đã được xác định.

Không dùng một path do client gửi để worker xóa tùy ý. Registry server phải xác định tài nguyên được phép xử lý.

Nếu có deduplication hoặc object dùng chung, phải kiểm tra các liên kết còn hiệu lực trước khi xóa nội dung vật lý. Không để purge của một case làm mất bằng chứng đang cần cho case khác, hoặc dùng chung object giữa tenant mà không có ranh giới an toàn.

## 10. Soft delete, object version, backup và khóa mã hóa

### 10.1. Soft delete mới chỉ là thay đổi khả năng nhìn thấy

Ẩn một hàng khỏi truy vấn thông thường không xóa nội dung trong database, history table, replica hoặc backup.

Với object storage có versioning, thao tác xóa object hiện tại có thể vẫn để lại version cũ. Cần hiểu cơ chế storage được dùng và kiểm tra những version thuộc phạm vi xử lý.

Một lifecycle rule là một thành phần triển khai, không thay thế registry, hold và đối soát kết quả.

### 10.2. Backup cần một hợp đồng thực tế

Có hệ thống không xóa được từng bản ghi khỏi backup bất biến ngay lập tức. Chính sách phải mô tả:

- Backup được giữ trong bao lâu.
- Ai có quyền restore và vào môi trường nào.
- Dữ liệu đã hết mục đích được hạn chế sử dụng ra sao.
- Cách bảo đảm yêu cầu xóa được áp dụng lại sau restore.
- Khi nào bản backup hết vòng đời và được tiêu hủy.
- Phạm vi nào chưa thể được xác nhận là purge tức thời.

Không dùng câu “backup là ngoại lệ” để bỏ qua toàn bộ vòng đời. Cũng không hứa xóa mọi bản sao ngay khi kiến trúc không thể thực hiện.

### 10.3. Restore không được phục hồi quyền đọc dữ liệu đã xóa

Một bản snapshot cũ có thể chứa asset mà hệ thống đang chạy đã purge. Quy trình restore cần đối soát lịch sử disposition hoặc tombstone được bảo vệ trước khi mở dữ liệu cho luồng nghiệp vụ.

Tombstone chỉ cần thông tin tối thiểu để thực thi việc ngăn phục hồi, có quyền truy cập và vòng đời của riêng nó. Không sao chép toàn bộ ảnh hoặc số giấy tờ vào tombstone.

Nếu registry xóa cũng được restore về thời điểm cũ mà không có nguồn đối soát tin cậy, cơ chế chống phục hồi có thể bị vô hiệu.

### 10.4. Crypto-erasure cần điều kiện, không chỉ gọi xóa khóa

Phá hủy vật liệu khóa có thể là một phần của xử lý dữ liệu nếu thiết kế mã hóa, phạm vi khóa và mọi bản sao khóa đáp ứng mục tiêu đã xác định.

Cần xét:

- Khóa có được dùng chung với dữ liệu còn phải giữ không?
- Có bản sao khóa hoặc khả năng khôi phục khóa không?
- Có plaintext trong cache, export hoặc hệ thống khác không?
- Backup có giữ khóa hoặc bản dữ liệu giải mã được bằng khóa khác không?
- Bước xóa khóa đã hoàn tất theo cơ chế quản lý khóa hay mới được lên lịch?

Không kết luận dữ liệu đã không thể phục hồi chỉ vì một khóa có nhãn “disabled”. Vô hiệu tạm thời và tiêu hủy là hai trạng thái khác nhau.

## 11. Nhà cung cấp proofing và bên xử lý tiếp

### 11.1. Xóa ở ứng dụng chưa đủ

Provider có thể giữ dữ liệu thô, dẫn xuất, kết quả, log và dữ liệu ở các bên xử lý tiếp. Tích hợp cần biết những gì được gửi đi và nghĩa vụ xử lý của từng bên.

Các câu hỏi cần giải quyết trước khi đưa vào vận hành:

- Provider giữ từng loại dữ liệu cho mục đích nào?
- Có cấu hình retention theo tenant, profile hoặc case không?
- API xóa bao quát loại dữ liệu và bản sao nào?
- Những phần nào có lịch độc lập hoặc hạn chế xóa?
- Có được dùng cho mục đích bổ sung không?
- Kết quả xóa được xác nhận bằng trạng thái hoặc bằng chứng gì?
- Khi chấm dứt hợp đồng hoặc chuyển provider, dữ liệu được xử lý ra sao?

Những điểm này phải được phản ánh vào chính sách của sản phẩm. Không công bố thời hạn ngắn hơn thực tế chỉ vì database của ứng dụng đã xóa trước provider.

### 11.2. Lỗi provider là một trạng thái cần theo dõi

Nếu API xóa không khả dụng, hệ thống cần giữ kế hoạch ở trạng thái chưa hoàn tất, retry có giới hạn lưu lượng và escalations theo mục tiêu xử lý.

Receipt của ứng dụng nên phân biệt:

~~~text
application_active_storage = PURGED
provider_request = ACCEPTED
provider_completion = PENDING
backup_scope = SCHEDULED_UNDER_POLICY
~~~

Không cần đưa những chi tiết hạ tầng này vào mọi màn hình người dùng. Nhưng đội vận hành phải thấy đủ để không trả lời sai phạm vi đã xử lý.

## 12. Yêu cầu xóa, thông báo và sinh trắc học

### 12.1. Xác minh quyền yêu cầu nhưng tránh vòng lặp bất khả thi

Một người dùng đang recovery có thể không còn phương tiện xác thực thông thường. Không nên mặc định yêu cầu đúng phương tiện đã mất như con đường duy nhất để tiếp nhận yêu cầu về dữ liệu.

Cần có quy trình xác minh quyền phù hợp với rủi ro. Đồng thời, người ngoài không được chỉ biết email là xóa được bằng chứng của người khác hoặc phá hồ sơ điều tra.

Mức xác minh, ngoại lệ và những phần chưa thể xóa phải có căn cứ, thẩm quyền và thông báo phù hợp với yêu cầu áp dụng.

### 12.2. Phân biệt điều người dùng yêu cầu và phạm vi có thể thực hiện

Một yêu cầu có thể dẫn đến:

- Xóa dữ liệu đã hết mục đích.
- Giới hạn xử lý trong khi giải quyết yêu cầu.
- Giữ một số record tối thiểu theo căn cứ còn hiệu lực.
- Giải thích dữ liệu thuộc hold hoặc lịch khác.
- Thu thập lại bằng chứng nếu người dùng tiếp tục một quy trình cần dữ liệu đã xóa.

Không cam kết giữ nguyên mọi chức năng proofing sau khi loại bỏ dữ liệu mà một profile bắt buộc cần duy trì. Cũng không dùng điều đó để tự mở rộng phạm vi giữ sang mọi loại dữ liệu.

### 12.3. Đặc biệt rõ ràng với dữ liệu sinh trắc học

Trong SP 800-63A-4, CSP dùng sinh trắc học phải công khai thông tin sử dụng, có quy trình xóa và thời hạn lưu mặc định; việc xử lý yêu cầu xóa còn xét các giới hạn áp dụng. Các yêu cầu này cần được đọc cùng profile cụ thể. [NIST SP 800-63A-4 — Requirements for the Use of Biometrics](https://pages.nist.gov/800-63-4/sp800-63a/ial-general/#requirements-for-the-use-of-biometrics)

Thông báo không nên chỉ nói “lưu an toàn”. Người tham gia cần hiểu loại dữ liệu, mục đích, lịch hoặc điều kiện lưu, cách yêu cầu xử lý và những giới hạn liên quan.

Lưu một bản consent không tự cho phép dùng dữ liệu cho mọi mục đích tương lai.

## 13. Audit việc xóa và quan sát vận hành

### 13.1. Bằng chứng xóa không nên trở thành bản sao evidence

Một receipt tối thiểu có thể chứa:

~~~text
disposition_plan_reference
asset_reference_under_controlled_access
data_category
policy_id_and_version
approved_scope
location_result_references
started_at
completed_at_if_applicable
remaining_scope_and_reason
authorized_exception_reference_if_any
~~~

Không chèn nội dung OCR, ảnh hoặc token truy cập vào receipt chỉ để chứng minh đã xóa chúng.

Audit vẫn cần integrity, phân quyền và lịch lưu của chính nó. OWASP lưu ý việc xử lý log phải bao quát cả log tạm, bản sao, bản trích xuất và backup, cùng các yêu cầu retention tương ứng. [OWASP Logging Cheat Sheet — Disposal of Logs](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html#disposal-of-logs)

### 13.2. Đo những gì có thể làm lộ khoảng trống

Các chỉ số hữu ích:

- Số asset quá hạn nhưng chưa hoàn tất disposition.
- Thời gian từ đến hạn đến khi purge ở từng hệ thống.
- Số bản sao không có owner hoặc retention rule.
- Số kế hoạch đang partial và lý do.
- Số hold quá ngày review.
- Tỷ lệ yêu cầu provider chưa được xác nhận hoàn tất.
- Số lần phát hiện dữ liệu đã xóa xuất hiện sau restore.
- Số truy cập evidence sau khi case đóng hoặc quá hạn.

Không dùng riêng “số lệnh DELETE đã gửi” làm thước đo thành công. Một lệnh được gửi không chứng minh nội dung ở mọi phạm vi đã được xử lý.

### 13.3. Thay chính sách cần đánh giá ảnh hưởng

Khi rút ngắn retention, cần lập kế hoạch xử lý các asset tồn đọng. Khi kéo dài, cần căn cứ và quyền phù hợp, không chỉ đổi một tham số rồi giữ toàn bộ dữ liệu cũ.

Policy version giúp giải thích quyết định nhưng không có nghĩa chính sách cũ luôn tiếp tục áp dụng mãi. Cần định nghĩa rule chuyển tiếp và phạm vi đánh giá lại.

Đợt triển khai cần có đối soát và khả năng dừng lỗi, vì thao tác purge thực tế thường không thể đảo ngược bằng cách đổi cấu hình.

## 14. Ví dụ xuyên suốt

### 14.1. Hoàn tất recovery sau khi mất điện thoại

Minh gửi giấy tờ và selfie để phục vụ một case đăng ký lại MFA.

Khi case hoàn tất, hệ thống đánh giá từng nhóm dữ liệu theo lịch tương ứng. Ảnh gốc và crop có thể đến hạn trước record quyết định. Nếu provider vẫn đang giữ bản sao, trạng thái không được ghi là mọi phạm vi đã purge.

Việc giữ record quyết định tối thiểu không cho phép dùng lại grant enrollment đã tiêu thụ.

### 14.2. Case bị bỏ dở sau upload

Lan tải ảnh rồi không hoàn tất quy trình. Nếu lịch chỉ bắt đầu khi case đóng, dữ liệu có thể bị mắc kẹt.

Hệ thống cần có chính sách cho upload tạm và hồ sơ bỏ dở, rồi xử lý chúng ngay cả khi không có kết quả proofing. Không giữ ảnh chỉ vì chưa từng đạt trạng thái thành công.

### 14.3. Hold áp dụng cho một phần hồ sơ

Một vụ việc cần giữ một số asset của Hà để điều tra. Hold có phạm vi và người có thẩm quyền, được review theo lịch.

Các dữ liệu không thuộc phạm vi hold vẫn được đánh giá bình thường. Hết hold, hệ thống quay lại quyết định disposition theo rule áp dụng, không tự giữ thêm toàn bộ một chu kỳ mới.

### 14.4. Restore làm xuất hiện dữ liệu đã purge

Đội vận hành restore snapshot trước thời điểm xóa dữ liệu của Phúc.

Trước khi cho ứng dụng truy cập, quy trình đối soát với nguồn disposition tin cậy và áp dụng lại các hạn chế hoặc xóa cần thiết. Môi trường restore không trở thành đường đọc lại evidence đã hết vòng đời.

### 14.5. Provider đã nhận nhưng chưa hoàn tất yêu cầu xóa

Ứng dụng xóa object nội bộ và provider trả trạng thái đã tiếp nhận.

Kế hoạch giữ trạng thái partial, chờ kết quả đúng hợp đồng và cảnh báo nếu quá mục tiêu. Nhân viên không được diễn giải “accepted” thành “mọi dữ liệu đã bị xóa”.

## 15. Tình huống cần kiểm chứng khi triển khai

| Tình huống | Kết quả mong đợi |
| --- | --- |
| URL ký đã hết hạn nhưng object còn tồn tại | Không báo object đã purge |
| Grant recovery hết hạn | Không dùng nó để suy retention của evidence |
| Case không bao giờ đóng | Có cơ chế cho hồ sơ bỏ dở và dữ liệu tạm |
| Nhân viên mở viewer nhiều lần | Không tự kéo dài retention nếu không có rule |
| Xóa ảnh gốc nhưng còn thumbnail hoặc OCR | Chưa hoàn tất phạm vi đã định |
| Object storage có version cũ | Xử lý các version thuộc phạm vi |
| Xóa soft-delete ở database | Không tự coi nội dung vật lý đã hết |
| Hold xuất hiện trong lúc worker xử lý | Có điểm điều phối và kiểm tra trước bước không đảo ngược |
| Callback tạo dẫn xuất đến sau purge | Không làm dữ liệu sống lại |
| Provider chỉ trả accepted | Tiếp tục theo dõi kết quả hoàn tất |
| Provider lỗi hoặc một location thất bại | Giữ trạng thái partial và retry hoặc escalation |
| Retry cùng kế hoạch xóa | Không gây tác động ngoài đúng asset và scope |
| Object dùng chung còn liên kết hợp lệ | Không xóa nội dung đang cần cho scope khác |
| Backup bất biến còn dữ liệu | Theo chính sách riêng, không hứa purge tức thời |
| Restore từ snapshot cũ | Áp dụng disposition trước khi phục vụ dữ liệu |
| Khóa chỉ bị disable | Không suy thành crypto-erasure hoàn tất |
| Có plaintext hoặc bản sao khóa khác | Chưa chứng minh mọi bản dữ liệu không thể khôi phục |
| Hash hoặc embedding còn khả năng nối về người | Không tự phân loại vô danh |
| Profile cần giữ dữ liệu cụ thể | Không tự xóa rồi vẫn tuyên bố đáp ứng profile |
| Yêu cầu xóa từ người chưa được xác minh | Không cho phá hồ sơ người khác |
| Người dùng mất phương tiện xác thực | Có đường xử lý yêu cầu phù hợp, không chỉ một bước bất khả thi |
| Kiểm tra log, queue và ticket | Không có bản sao evidence ngoài kiểm kê |
| Audit việc xóa | Không chứa chính dữ liệu cần xóa |

Bảng là tiêu chí để đội triển khai kiểm chứng, không phải xác nhận một hệ thống cụ thể đã được kiểm thử.

## 16. Những điểm cần ghi nhớ

- Retention là vòng đời dữ liệu, khác với TTL của token, độ mới proofing và hiệu lực session.
- Lập lịch theo loại dữ liệu, mục đích và sự kiện; không chỉ theo một cột của case.
- Kiểm kê dữ liệu thô, dẫn xuất, provider, log, bản xuất và backup.
- Giữ record quyết định tối thiểu khi có căn cứ, không mặc định giữ toàn bộ evidence.
- Hold cần phạm vi, thẩm quyền và review; không tạo quyền sử dụng không liên quan.
- Một request xóa hoặc cờ soft-delete chưa chứng minh purge hoàn tất.
- Theo dõi trạng thái từng nơi, xử lý retry và ngăn dữ liệu sống lại sau callback hoặc restore.
- Chỉ công bố mức hoàn tất mà hệ thống có căn cứ xác nhận.
