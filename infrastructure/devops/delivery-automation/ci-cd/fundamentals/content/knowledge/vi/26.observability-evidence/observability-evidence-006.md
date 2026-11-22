# Đặt thời gian lưu bằng chứng theo nhu cầu điều tra

## 1. Vì sao cần chính sách lưu bằng chứng?

CI/CD tạo ra nhiều dấu vết trong suốt vòng đời phát hành: commit, pipeline run, kết quả kiểm thử, log build, artifact, SBOM, chữ ký, phê duyệt, lần triển khai, cấu hình môi trường và tín hiệu sau triển khai. Khi một sự cố xảy ra, nhóm cần ghép những dấu vết này để trả lời các câu hỏi:

- Thay đổi nào đã được đưa vào hệ thống?
- Ai hoặc pipeline nào đã khởi chạy và phê duyệt?
- Artifact nào thực sự được triển khai?
- Công cụ và policy nào đã kiểm tra artifact?
- Môi trường đã thay đổi ra sao trước và sau phát hành?
- Sự cố bắt đầu khi nào, ảnh hưởng đến phiên bản hoặc nhóm người dùng nào?
- Thao tác khôi phục đã diễn ra theo trình tự nào?

Nếu bằng chứng đã hết hạn hoặc không thể truy xuất, nhóm có thể không xác định được nguyên nhân, phạm vi ảnh hưởng và trách nhiệm xử lý. Ngược lại, lưu mọi log, trace và payload mãi mãi làm tăng chi phí, rủi ro lộ dữ liệu và độ phức tạp quản trị.

Vì vậy, thời gian lưu cần dựa trên **nhu cầu điều tra, thời gian phát hiện sự cố, mức độ quan trọng của dịch vụ, yêu cầu kiểm toán và độ nhạy của dữ liệu**. Không có một con số TTL phù hợp cho mọi loại bằng chứng.

Trong phạm vi **DEVOPS_CI_CD_FUNDAMENTALS**, bằng chứng phải hỗ trợ truy vết từ sự kiện Git, pipeline dưới dạng mã, build và kiểm thử đến artifact, môi trường, cổng chất lượng, xác minh sau triển khai và rollback. Chính sách retention giúp những bằng chứng này còn tồn tại đủ lâu để nhóm có thể điều tra một release sau khi nó đã kết thúc.

## 2. Phân biệt telemetry vận hành và bằng chứng phát hành

Telemetry và evidence có liên quan nhưng phục vụ các câu hỏi khác nhau.

- **Telemetry vận hành** giúp quan sát tình trạng dịch vụ theo thời gian: metric, log, trace, event và alert.
- **Bằng chứng phát hành** ghi nhận điều gì đã được kiểm tra, phê duyệt, tạo ra và triển khai: commit SHA, pipeline run, kết quả gate, artifact digest, SBOM, provenance, chữ ký và deployment record.
- **Bằng chứng sự cố** ghi lại diễn biến và quyết định xử lý: timeline, log liên quan, snapshot cấu hình, thao tác của người trực, kết quả khôi phục và biên bản điều tra.

Một metric time series có thể chỉ được giữ trong thời gian ngắn để phục vụ dashboard, trong khi release record và artifact digest cần tồn tại lâu hơn để trả lời câu hỏi về một phiên bản cũ. Ngược lại, log debug chi tiết có thể chứa dữ liệu nhạy cảm và không cần lưu lâu sau khi mục đích điều tra đã hết.

Không nên dùng thời gian lưu của hệ thống log làm mặc định cho mọi loại evidence. Cần phân loại dữ liệu trước khi đặt TTL.

## 3. Phân loại bằng chứng trong CI/CD

Một danh mục cơ bản có thể gồm:

| Loại bằng chứng | Ví dụ | Nhu cầu điều tra |
|---|---|---|
| Source/change identity | Repository, commit SHA, branch, tag, PR ID | Xác định thay đổi nguồn |
| Pipeline execution | Run ID, job status, runner image, workflow version | Tái dựng luồng build/release |
| Build/test output | Test report, coverage, compiler output | Điều tra lỗi build hoặc hồi quy |
| Security/quality results | SAST, SCA, secret scan, license, policy decision | Giải thích quyết định gate |
| Artifact identity | Package version, image digest, checksum | Xác định đúng binary đã phát hành |
| Supply-chain evidence | SBOM, provenance, signature, attestation | Xác minh nguồn gốc và tính toàn vẹn |
| Approval/audit | Người phê duyệt, thời điểm, change request | Kiểm tra quyền và quy trình |
| Deployment record | Environment, revision, rollout step, result | Tái dựng thay đổi môi trường |
| Configuration snapshot | Phiên bản cấu hình, feature flag, manifest | So sánh trạng thái trước/sau |
| Runtime telemetry | Log, metric, trace, alert | Điều tra tác động sau triển khai |
| Recovery evidence | Rollback operation, artifact cũ, smoke test | Xác minh khôi phục |

Mỗi loại có thể có thời hạn lưu khác nhau. Ví dụ, log verbose của một job có thể chỉ cần giữ trong thời gian ngắn; release manifest, digest và approval record có thể cần lưu trong toàn bộ thời gian artifact còn được triển khai hoặc được hỗ trợ.

## 4. Bắt đầu từ câu hỏi điều tra

Không nên chọn retention bằng cách hỏi "hệ thống đang cho phép lưu tối đa bao nhiêu ngày?". Hãy bắt đầu từ các tình huống cần điều tra.

Ví dụ:

- Một lỗi chỉ xuất hiện khi traffic tăng vào cuối tuần.
- Một CVE được công bố nhiều tháng sau khi artifact được phát hành.
- Một khách hàng báo sai dữ liệu từ một giao dịch đã xảy ra trước đó.
- Một release bị rollback và nhóm cần biết ai đã phê duyệt.
- Một pipeline bị nghi ngờ đã sử dụng dependency hoặc runner bị xâm nhập.
- Một audit yêu cầu chứng minh artifact được tạo từ commit và workflow đã phê duyệt.

Với mỗi tình huống, xác định:

1. Sự cố thường được phát hiện sau bao lâu?
2. Nhóm cần xem dữ liệu trong khoảng thời gian nào trước thời điểm phát hiện?
3. Bằng chứng nào cần có để tái dựng sự kiện?
4. Dữ liệu cần ở trạng thái searchable hay chỉ cần có thể khôi phục từ archive?
5. Ai được quyền truy cập?
6. Khi nào được phép xóa?

Thời gian lưu nên bao phủ cả độ trễ phát hiện và khoảng nhìn ngược cần cho điều tra. Nếu lỗi có thể chỉ lộ ra sau một chu kỳ nghiệp vụ dài, retention ngắn hơn chu kỳ đó sẽ khiến bằng chứng biến mất trước khi vấn đề được báo cáo.

## 5. Xác định retention theo rủi ro và thời gian phát hiện

Một mô hình thực tế đánh giá mỗi loại evidence theo nhiều yếu tố:

- **Impact:** tác động nếu không còn bằng chứng.
- **Detection delay:** thời gian có thể trôi qua trước khi phát hiện sự cố.
- **Investigation lookback:** khoảng thời gian cần xem lại trước khi sự cố được phát hiện.
- **Sensitivity:** mức độ nhạy cảm của nội dung.
- **Volume/cost:** dung lượng phát sinh và chi phí lưu trữ.
- **External obligation:** yêu cầu hợp đồng, kiểm toán, quy định hoặc chính sách nội bộ đã được xác nhận.
- **Reconstruction cost:** mức độ khó tái tạo lại bằng chứng.

Có thể dùng thang đánh giá nội bộ để xếp nhóm, nhưng không nên biến điểm số thành một công thức tự động áp dụng cho mọi hệ thống. Một release record nhỏ nhưng quan trọng có thể cần lưu lâu hơn nhiều log debug có dung lượng lớn.

### 5.1. Minh họa các nhóm retention

Các khoảng dưới đây chỉ là ví dụ để bắt đầu thảo luận, không phải tiêu chuẩn bắt buộc hay tư vấn pháp lý:

| Nhóm | Ví dụ | Khoảng lưu minh họa |
|---|---|---|
| Debug ngắn hạn | Log verbose của job, trace sampling phục vụ triage thường ngày | 7–14 ngày |
| Vận hành thường kỳ | Application log, metric chi tiết, deployment telemetry | 30–90 ngày |
| Điều tra release | Pipeline run, test report, security finding, deployment record | 90–180 ngày |
| Truy vết dài hạn | Artifact manifest, digest, SBOM, provenance, approval/audit record | 1 năm hoặc theo vòng đời sản phẩm |
| Sự cố đặc biệt | Evidence được bảo toàn cho incident hoặc investigation đang mở | Theo quyết định đóng vụ việc và policy liên quan |

Tổ chức cần điều chỉnh theo chu kỳ phát hiện lỗi, yêu cầu khách hàng, quy định áp dụng và khả năng lưu trữ. Không được coi các con số minh họa là thời hạn hợp pháp cho mọi loại dữ liệu.

## 6. Chọn mốc bắt đầu và kết thúc retention

TTL cần có điểm bắt đầu rõ ràng. Một số cách tính:

- Từ lúc log hoặc event được tạo.
- Từ lúc pipeline run kết thúc.
- Từ ngày artifact được publish.
- Từ lúc release được đưa vào production.
- Từ khi incident được đóng.
- Từ ngày hợp đồng hoặc giai đoạn hỗ trợ kết thúc.

Cùng một loại bằng chứng có thể cần mốc khác nhau. Ví dụ, thời gian lưu log của một job có thể tính từ lúc job kết thúc. Thời gian lưu evidence của incident có thể tính từ lúc incident đóng để bảo đảm nhóm có đủ thời gian hoàn tất điều tra và review.

Policy nên ghi rõ:

- **retention_start_event:** sự kiện bắt đầu tính hạn.
- **retention_duration:** thời gian giữ tối thiểu.
- **delete_after:** điều kiện đủ để xóa.
- **hold_override:** trường hợp phải giữ lâu hơn.
- **archive_transition:** thời điểm chuyển tầng lưu trữ.

Không nên chỉ ghi "giữ 90 ngày" mà không nói 90 ngày tính từ khi nào. Cũng cần xác định thời điểm xóa là tự động sau TTL hay chỉ được xóa sau khi qua bước kiểm tra legal hold và incident hold.

## 7. Lưu trữ theo tầng: hot, warm và cold

Không phải bằng chứng nào cũng cần được truy vấn với cùng tốc độ.

- **Hot storage:** dữ liệu mới, thường xuyên truy vấn; tối ưu cho tìm kiếm và dashboard.
- **Warm storage:** dữ liệu ít truy vấn hơn nhưng cần lấy lại tương đối nhanh.
- **Cold/archive storage:** dữ liệu hiếm khi truy cập, chi phí thấp hơn nhưng có thể mất nhiều thời gian hoặc cần thao tác restore.

Một lifecycle có thể chuyển log từ hot sang warm, rồi cold trước khi hết hạn. Tuy nhiên, việc chuyển tầng không được làm mất metadata, checksum hoặc liên kết giữa các bằng chứng.

### 7.1. Giữ metadata có thể tìm kiếm

Một cách giảm chi phí là giữ metadata nhỏ trong hệ thống tìm kiếm lâu hơn payload lớn. Ví dụ, giữ release ID, commit SHA, artifact digest, environment, thời điểm và URI archive ngay cả khi log verbose đã được chuyển sang cold storage.

Khi điều tra, nhóm tìm release bằng metadata trước rồi khôi phục đúng tập bằng chứng cần thiết. Cần bảo đảm metadata không tiết lộ thông tin nhạy cảm và URI archive vẫn hợp lệ trong suốt thời gian lưu.

## 8. Retention cho log, metric và trace

Ba loại telemetry có đặc điểm khác nhau.

### 8.1. Log

Log thường có dung lượng lớn và có thể chứa dữ liệu nhạy cảm. Nên phân biệt:

- Application log phục vụ vận hành.
- Audit log ghi thao tác có quyền.
- Pipeline/job log.
- Security log.
- Debug log hoặc log tạm.

Audit log và pipeline decision log thường cần chính sách riêng so với debug output. Không nên tăng retention cho toàn bộ log chỉ vì một số log cần giữ lâu.

### 8.2. Metric

Metric có thể được lưu lâu ở dạng aggregate hoặc downsample trong khi giữ dữ liệu chi tiết trong thời gian ngắn.

Ví dụ:
- Giữ metric độ phân giải cao cho điều tra gần thời điểm phát hành.
- Sau một khoảng thời gian, tổng hợp theo phút hoặc giờ.
- Giữ SLI/SLO và error budget trend lâu hơn metric raw có cardinality cao.

Downsampling phải bảo toàn ý nghĩa cần điều tra. Một percentile đã được tổng hợp đúng có thể hữu ích hơn trung bình đơn giản; không nên tính trung bình của các percentile đã tính riêng rồi coi đó là percentile toàn khoảng.

### 8.3. Trace

Trace thường được sampling để kiểm soát chi phí. Khi điều tra lỗi hiếm, sampling thông thường có thể bỏ sót trace quan trọng.

Có thể dùng:
- Tail-based sampling ưu tiên giữ trace có lỗi hoặc latency cao.
- Sampling tăng cường trong một khoảng phát hành.
- Giữ trace liên quan incident theo trace ID.
- Lưu aggregate về tỷ lệ lỗi và latency lâu hơn raw trace.

Cần lưu ý retention của trace và log phải tương thích với khoảng thời gian nhóm dự kiến ghép chúng bằng trace ID hoặc correlation ID.

## 9. Retention cho pipeline và build evidence

Pipeline evidence giúp tái dựng cách một artifact được tạo ra.

Các dữ liệu nên cân nhắc giữ:

- Repository, commit SHA, branch và tag.
- Workflow/pipeline definition version.
- Pipeline run ID và job ID.
- Runner image, toolchain và dependency lockfile.
- Build parameters không chứa secret.
- Test report và quality gate decision.
- Phiên bản scanner/ruleset và security findings.
- Artifact digest và nơi lưu artifact.
- Thời điểm, trạng thái và lý do retry/cancel.
- Người hoặc identity khởi chạy.

Không nhất thiết giữ toàn bộ console log với cùng thời hạn. Có thể giữ test summary, decision record và metadata lâu hơn log debug. Nếu log build là bằng chứng duy nhất cho một bước quan trọng, cần lưu log đó hoặc tạo một attestation có chữ ký chứa kết quả và tham chiếu tới log gốc.

Artifact cần có retention riêng. Nếu artifact đã bị xóa nhưng release record vẫn còn, nhóm có thể biết điều gì đã triển khai nhưng không thể tái triển khai chính xác phiên bản đó. Cần xác định vòng đời artifact theo khả năng rollback, hỗ trợ phiên bản và chính sách phân phối.

## 10. Retention cho SBOM, provenance, chữ ký và attestation

Các bằng chứng chuỗi cung ứng phần mềm thường có dung lượng nhỏ hơn log nhưng giá trị điều tra cao.

- **SBOM:** danh sách thành phần và phiên bản trong artifact.
- **Provenance:** mô tả nguồn, builder và quy trình tạo artifact.
- **Signature:** chữ ký xác nhận danh tính hoặc nguồn phát hành.
- **Attestation:** tuyên bố có cấu trúc về một thuộc tính, ví dụ kết quả kiểm tra hoặc provenance.
- **Verification record:** kết quả xác minh chữ ký, issuer, policy và thời điểm.

Nên giữ các bằng chứng này ít nhất trong khoảng thời gian artifact có thể được triển khai, hỗ trợ, kiểm toán hoặc cần điều tra lỗ hổng. Nếu artifact vẫn chạy trong production sau một năm, xóa SBOM sau 30 ngày sẽ làm giảm khả năng xác định thành phần bị ảnh hưởng khi CVE mới xuất hiện.

Chữ ký hết hạn hoặc certificate bị thu hồi không có nghĩa record xác minh lịch sử nên bị xóa. Cần giữ thông tin cần thiết để giải thích chữ ký đã được kiểm tra trong bối cảnh nào, tại thời điểm nào và theo trust policy nào. Không lưu private key trong evidence package.

## 11. Retention cho deployment và cấu hình môi trường

Để điều tra một release, cần biết môi trường đã thay đổi thế nào.

Nên lưu:

- Release ID, commit SHA và artifact digest.
- Environment, cluster, region và namespace.
- Deployment revision và rollout strategy.
- Tỷ lệ traffic hoặc canary stage.
- Thời điểm bắt đầu, kết thúc và từng lần pause/resume.
- Desired configuration version.
- Feature flag state có liên quan.
- Approval và identity thực hiện.
- Health check, smoke test và rollout result.
- Rollback hoặc roll-forward operation.

Không nhất thiết lưu bản sao đầy đủ mọi secret hoặc toàn bộ runtime environment. Nên lưu version/reference của secret, tên cấu hình, digest của snapshot đã loại bỏ dữ liệu nhạy cảm hoặc metadata đủ để truy xuất từ hệ thống quản lý cấu hình có quyền kiểm soát.

Nếu cần snapshot để điều tra, hãy xác định rõ phần nào được lưu, cách redaction và ai có thể truy cập. Một file cấu hình có thể chứa token, connection string hoặc dữ liệu khách hàng.

## 12. Bằng chứng audit và approval

Audit evidence trả lời ai đã làm gì, khi nào và dựa trên quyền nào.

Ví dụ:

- Ai phê duyệt production deployment?
- Ai thay đổi quality gate?
- Ai tạo exception cho security finding?
- Ai chạy lại pipeline hoặc replay webhook?
- Ai thay đổi retention policy?
- Ai truy cập hoặc xuất evidence nhạy cảm?

Audit record cần có identity ổn định, action, resource, timestamp, kết quả và correlation ID. Tránh chỉ lưu display name vì tên hiển thị có thể đổi hoặc trùng nhau.

Các record về phê duyệt và thay đổi policy thường có giá trị lâu hơn log debug. Tuy nhiên, thời gian lưu phải căn cứ vào yêu cầu nội bộ, hợp đồng và quy định đã được tổ chức xác định. Không nên tự suy đoán một thời hạn pháp lý chung.

## 13. Giữ bằng chứng đủ để ghép thành một timeline

Một tập log còn tồn tại nhưng không thể liên kết với release thì giá trị điều tra rất thấp.

Nên dùng các định danh xuyên suốt:

- trace_id hoặc correlation_id cho một luồng xử lý.
- event_id cho sự kiện.
- pipeline_run_id và job_id.
- release_id hoặc deployment_id.
- commit_sha.
- artifact_digest.
- environment và deployment_revision.
- incident_id khi có sự cố.

Ví dụ timeline:

~~~text
09:00  Git event E-42 nhận commit C
09:01  Pipeline P-118 bắt đầu
09:07  Artifact digest D được publish
09:08  Security gate G-19 PASS
09:12  Release R-55 được phê duyệt
09:15  Deployment D-77 bắt đầu tại production
09:18  Canary nhận 5% traffic
09:24  Alert A-91 phát hiện error rate tăng
09:26  Rollback RB-12 bắt đầu
09:30  Smoke test xác nhận phiên bản trước hoạt động
~~~

Các timestamp cần có timezone hoặc được chuẩn hóa UTC. Đồng hồ giữa runner, cluster, database và hệ thống log cần được đồng bộ. Nếu đồng hồ lệch vài phút, timeline có thể sắp xếp sai thứ tự và gây nhầm lẫn khi điều tra.

## 14. Bảo đảm tính toàn vẹn và nguồn gốc bằng chứng

Retention chỉ bảo đảm dữ liệu còn tồn tại; nó không chứng minh dữ liệu chưa bị sửa.

Các biện pháp:

- Tạo checksum hoặc hash cho evidence package.
- Ký manifest bằng identity được kiểm soát.
- Dùng storage có versioning hoặc immutability khi phù hợp.
- Phân tách quyền ghi, đọc và xóa.
- Ghi audit cho mọi thao tác truy cập/xuất evidence.
- Giữ metadata về nguồn tạo và thời điểm thu thập.
- Xác minh checksum khi archive và khi restore.
- Bảo vệ signing key trong KMS/HSM hoặc dịch vụ quản lý khóa phù hợp.

Với bằng chứng cần bảo toàn cho điều tra, có thể dùng append-only hoặc WORM storage. Cần hiểu chế độ retention lock: cấu hình sai có thể khiến dữ liệu nhạy cảm không thể xóa đúng hạn, hoặc cho phép người có quyền cao xóa trước thời hạn.

Không nên coi hash đơn lẻ là bằng chứng về nguồn gốc. Hash giúp phát hiện thay đổi nếu giá trị tham chiếu được bảo vệ; chữ ký và audit trail bổ sung thông tin về identity và thời điểm.

## 15. Bảo vệ dữ liệu nhạy cảm trong evidence

Log và trace có thể vô tình chứa:

- Access token, password hoặc private key.
- Email, số điện thoại hoặc định danh người dùng.
- Request/response body có dữ liệu cá nhân.
- SQL query chứa giá trị nhạy cảm.
- URL có token trong query string.
- Header xác thực hoặc cookie.
- Thông tin hạ tầng nội bộ.

Trước khi lưu, nên áp dụng data minimization:

1. Không thu thập trường không cần cho điều tra.
2. Redact hoặc mask secret ở nguồn phát.
3. Dùng allowlist field cho log có cấu trúc.
4. Giới hạn kích thước payload và loại dữ liệu.
5. Tách dữ liệu nhạy cảm khỏi metadata tìm kiếm.
6. Mã hóa khi truyền và khi lưu.
7. Hạn chế quyền theo vai trò và mục đích.
8. Ghi audit khi truy cập dữ liệu nhạy cảm.

Không nên dựa hoàn toàn vào log masking của giao diện tìm kiếm. Nếu secret đã được ghi vào storage gốc, người có quyền truy cập thấp hơn có thể vẫn lấy được dữ liệu thô qua API hoặc export.

Retention càng dài thì hậu quả của việc lưu thừa dữ liệu càng lớn. Nếu không cần lưu raw payload trong một năm, hãy lưu kết quả đã chuẩn hóa và metadata cần thiết, còn payload thô có thời hạn ngắn hơn.

## 16. Phân quyền truy cập evidence

Không phải mọi thành viên đều cần đọc mọi bằng chứng.

Có thể phân quyền theo:

- Environment: dev, staging, production.
- Service hoặc repository.
- Loại evidence: build log, security finding, audit record, incident package.
- Mức nhạy cảm.
- Vai trò: developer, SRE, security, auditor, incident commander.
- Mục đích: vận hành, điều tra, kiểm toán hoặc hỗ trợ khách hàng.

Các nguyên tắc:

- Dùng least privilege.
- Tách quyền tìm kiếm metadata khỏi quyền tải raw payload.
- Cấp quyền tạm thời cho điều tra đặc biệt.
- Ghi lại ai đã truy cập hoặc xuất dữ liệu.
- Không chia sẻ link archive công khai.
- Xem xét định kỳ nhóm quyền và tài khoản dịch vụ.
- Bảo vệ khóa giải mã tách biệt với quyền đọc metadata.

Một incident commander có thể cần quyền truy xuất evidence trong một khoảng thời gian ngắn. Quyền này nên được cấp có thời hạn và tự động thu hồi sau khi vụ việc kết thúc.

## 17. Legal hold và incident hold

TTL thông thường không nên xóa dữ liệu đang được bảo toàn cho một cuộc điều tra hoặc yêu cầu giữ dữ liệu đã được tổ chức xác nhận.

- **Incident hold:** giữ bằng chứng liên quan đến incident đang mở hoặc cần review sau sự cố.
- **Legal hold:** tạm dừng xóa dữ liệu theo yêu cầu chính thức của bộ phận pháp chế hoặc người có thẩm quyền.

Khi áp dụng hold, cần ghi:

- Hold ID và phạm vi.
- Người yêu cầu/phê duyệt.
- Lý do và thời điểm bắt đầu.
- Evidence set hoặc resource bị giữ.
- Người chịu trách nhiệm review.
- Điều kiện kết thúc hold.
- Thời điểm giải phóng và tiếp tục lifecycle.

Không nên tự suy đoán khi nào legal hold được áp dụng hoặc gỡ bỏ. Việc đó cần theo quy trình của tổ chức và người có thẩm quyền.

Khi hold kết thúc, dữ liệu không nhất thiết phải giữ mãi. Hãy đánh giá lại retention policy ban đầu và tiếp tục lifecycle nếu không còn lý do hợp lệ để bảo toàn.

## 18. Xóa dữ liệu an toàn và có thể kiểm chứng

Hết TTL không có nghĩa dữ liệu lập tức biến mất khỏi mọi bản sao. Evidence có thể còn trong:

- Replica.
- Backup.
- Snapshot.
- Cache.
- Search index.
- Export đã tải.
- Archive copy.
- Object version cũ.

Chính sách xóa cần xác định phạm vi và độ trễ xóa ở từng hệ thống. Một số backup có thể hết hạn theo chu kỳ riêng; cần ghi rõ thời gian tối đa để dữ liệu rời khỏi bản sao lưu.

Nên lưu deletion record tối thiểu gồm loại dữ liệu, phạm vi, thời điểm, policy version và kết quả. Không ghi lại payload đã xóa vào audit log chỉ để chứng minh việc xóa.

Với dữ liệu cần xóa theo yêu cầu riêng, phải xem xét các bản sao, chỉ mục và bản export theo quy trình đã được phê duyệt. Nếu dùng encryption key để cryptographic erase, cần xác minh tất cả bản sao của dữ liệu đều phụ thuộc vào khóa đó và không còn bản rõ ở nơi khác.

## 19. Xây dựng retention policy theo loại evidence

Một policy nên có ít nhất các thuộc tính:

| Thuộc tính | Ý nghĩa |
|---|---|
| Evidence type | Loại dữ liệu |
| Owner | Nhóm chịu trách nhiệm |
| Purpose | Mục đích thu thập và lưu |
| Classification | Mức nhạy cảm |
| Retention start | Mốc bắt đầu tính hạn |
| Duration | Thời gian giữ |
| Storage tier | Hot, warm hoặc cold |
| Access policy | Ai được truy cập |
| Integrity control | Hash, signature, immutability |
| Hold behavior | Xử lý khi có incident/legal hold |
| Deletion method | Cách xóa và thời gian hoàn tất |
| Restore target | Thời gian có thể khôi phục khi cần |

Policy nên được version hóa và review khi có thay đổi về hệ thống, rủi ro, quy định hoặc chu kỳ phát hành.

### 19.1. Ví dụ retention matrix

Bảng dưới đây là ví dụ khởi đầu; nhóm cần thay đổi thời hạn theo điều tra, vòng đời artifact và yêu cầu đã được xác nhận.

| Evidence | Retention start | Ví dụ thời hạn | Tầng sau khi hết hot |
|---|---|---:|---|
| Debug job log | Job completed | 14 ngày | Xóa |
| Application log chi tiết | Event timestamp | 30 ngày | Warm aggregate thêm 60 ngày |
| Trace raw | Trace timestamp | 14 ngày | Giữ metric aggregate |
| Pipeline decision/test summary | Pipeline completed | 180 ngày | Cold archive nếu cần |
| Security scan report | Scan completed | 1 năm | Cold archive |
| Release manifest và artifact digest | Release created | Theo vòng đời artifact và hỗ trợ | Cold archive |
| SBOM/provenance/signature record | Artifact published | Theo vòng đời artifact và hỗ trợ | Cold archive |
| Production approval/audit event | Approval timestamp | Theo policy audit được xác nhận | Immutable archive nếu yêu cầu |
| Incident evidence | Incident closed hoặc hold release | Theo quyết định incident/policy | Cold archive |

Không nên áp dụng một thời hạn cứng cho tất cả repository hoặc môi trường. Một dịch vụ xử lý dữ liệu quan trọng có thể cần khoảng nhìn ngược dài hơn một job thử nghiệm trong dev.

## 20. Ví dụ cấu hình retention dạng mã giả

Ví dụ sau mô tả policy ở mức khái niệm, không phải schema của một nền tảng lưu trữ cụ thể:

~~~yaml
evidence_retention:
  policy_version: "2026-01"

  classes:
    pipeline_debug_log:
      owner: platform
      classification: internal
      start_event: pipeline_completed
      hot_days: 7
      archive_days: 7
      delete_after_days: 14
      redact_secrets: true

    pipeline_decision:
      owner: platform
      classification: internal
      start_event: pipeline_completed
      hot_days: 30
      archive_days: 150
      delete_after_days: 180
      integrity:
        checksum: true
        signed_manifest: true

    security_report:
      owner: security
      classification: confidential
      start_event: scan_completed
      hot_days: 30
      archive_days: 335
      delete_after_days: 365
      access:
        roles: [security, incident_commander]

    release_manifest:
      owner: release
      classification: internal
      start_event: artifact_published
      retention: artifact_support_lifecycle
      integrity:
        checksum: true
        signature_reference: true

  holds:
    incident_hold: suspend_deletion
    legal_hold: require_authorized_release

  deletion:
    audit_record: true
    verify_replicas_and_indexes: true
~~~

Các trường hot_days, archive_days và delete_after_days chỉ minh họa cách diễn đạt policy. Hệ thống thật cần xác định cách tính tổng thời hạn, mốc bắt đầu, cách xử lý backup, legal hold và hành vi khi policy được thay đổi.

Đặc biệt, retention theo artifact_support_lifecycle là một điều kiện theo vòng đời, không phải một số ngày cố định. Cần định nghĩa ai xác nhận artifact đã hết thời gian hỗ trợ hoặc không còn được triển khai trước khi xóa evidence liên quan.

## 21. Kiểm thử khả năng truy xuất bằng chứng

Một policy chỉ có giá trị khi nhóm có thể tìm và khôi phục evidence trong thời gian cần thiết.

Nên diễn tập các tình huống:

- Tìm toàn bộ evidence từ một commit SHA.
- Tìm artifact digest đang chạy ở production.
- Khôi phục pipeline log từ cold archive.
- Xác minh chữ ký và checksum của evidence package.
- Tái dựng timeline từ webhook đến rollback.
- Truy xuất kết quả security scan của artifact cũ.
- Xác định ai đã phê duyệt một release.
- Áp dụng incident hold rồi xác nhận lifecycle không xóa dữ liệu.
- Kết thúc hold và xác minh xóa tiếp tục theo policy.
- Xác minh người không có quyền không thể tải raw evidence.

Đo thời gian tìm kiếm và khôi phục. Nếu nhóm cần 12 giờ để restore archive nhưng quy trình incident yêu cầu quyết định trong 30 phút, cần điều chỉnh tầng lưu trữ hoặc chuẩn bị index/metadata phù hợp.

### 21.1. Kiểm tra restore định kỳ

Định kỳ chọn một tập evidence cũ và thực hiện restore trong môi trường kiểm thử:

1. Xác định release ID và archive location.
2. Tải dữ liệu bằng identity có quyền tối thiểu.
3. Kiểm tra checksum hoặc signature.
4. Ghép với release manifest và pipeline record.
5. Xác nhận file có thể đọc bằng công cụ hiện tại.
6. Ghi thời gian restore và kết quả.

Đừng chỉ kiểm tra rằng object tồn tại. Định dạng có thể đã thay đổi, khóa mã hóa có thể không còn khả dụng hoặc index có thể đã hết hạn.

## 22. Quản lý thay đổi retention policy

Retention policy cũng là một cấu hình quan trọng cần kiểm soát.

Khi thay đổi thời hạn:

- Ghi policy version và người phê duyệt.
- Đánh giá dữ liệu hiện có sẽ bị xóa sớm hơn hay được giữ lâu hơn.
- Xác định ảnh hưởng tới chi phí và truy vấn.
- Kiểm tra legal/incident hold đang mở.
- Thử policy trên một nhóm nhỏ.
- Ghi audit cho lần áp dụng.
- Có cách khôi phục cấu hình nếu lifecycle bị đặt sai.

Giảm retention từ 180 xuống 30 ngày có thể khiến dữ liệu cũ đủ điều kiện xóa ngay khi policy mới áp dụng, tùy engine. Tăng retention cũng có thể tạo chi phí lớn nếu áp dụng cho dữ liệu raw có volume cao. Cần mô phỏng ảnh hưởng trước khi thay đổi.

Không nên để mỗi team tự đặt TTL khác nhau mà không có owner hoặc quy trình review. Có thể cho phép ngoại lệ theo dịch vụ, nhưng phải có lý do, thời hạn và người chịu trách nhiệm.

## 23. Các anti-pattern thường gặp

| Anti-pattern | Hệ quả | Cách cải thiện |
|---|---|---|
| Một TTL cho mọi loại dữ liệu | Log quan trọng mất sớm hoặc debug log giữ quá lâu | Phân loại theo mục đích và rủi ro |
| Tính hạn từ thời điểm không rõ | Không biết khi nào dữ liệu đủ điều kiện xóa | Định nghĩa retention start event |
| Giữ raw log lâu để thay cho audit record | Chi phí và rủi ro dữ liệu nhạy cảm tăng | Tạo decision/audit evidence có cấu trúc |
| Xóa SBOM khi artifact còn chạy | Khó điều tra CVE mới | Giữ SBOM theo vòng đời artifact |
| Chỉ giữ metadata mà không có archive payload cần thiết | Không thể tái dựng chi tiết sự cố | Xác định evidence package theo use case |
| Lưu trace nhưng thiếu correlation ID | Không ghép được timeline | Chuẩn hóa ID và timestamp |
| Dựa vào hash không được bảo vệ | Kẻ có quyền sửa cả dữ liệu và hash | Ký manifest và tách quyền |
| WORM không có quy trình hold/release | Có thể giữ dữ liệu nhạy cảm quá hạn | Quản lý immutability và legal hold rõ ràng |
| Chỉ kiểm tra object tồn tại | Restore có thể thất bại | Diễn tập restore và xác minh integrity |
| Xóa primary nhưng quên replica/index/export | Dữ liệu vẫn tồn tại ngoài policy | Lifecycle bao phủ mọi bản sao |
| Không audit việc truy cập evidence | Không biết ai đã xem hoặc xuất dữ liệu | Access logging và least privilege |
| Thay đổi TTL không đánh giá dữ liệu cũ | Xóa hàng loạt ngoài dự kiến | Mô phỏng và review trước khi áp dụng |

## 24. Checklist đặt thời gian lưu bằng chứng

**Mục đích và phạm vi**

- [ ] Đã liệt kê các tình huống điều tra cần hỗ trợ.
- [ ] Đã phân biệt telemetry, release evidence và incident evidence.
- [ ] Có owner cho từng loại bằng chứng.
- [ ] Có classification và mục đích thu thập.
- [ ] Đã xác định detection delay và investigation lookback.

**Retention và storage**

- [ ] Có retention start event và duration rõ ràng.
- [ ] Thời hạn phù hợp với vòng đời artifact và chu kỳ nghiệp vụ.
- [ ] Có hot/warm/cold tier khi phù hợp.
- [ ] Metadata đủ để tìm lại archive.
- [ ] SBOM, provenance, signature và release record được giữ đủ lâu.
- [ ] Backup, replica, index và export nằm trong lifecycle.

**Toàn vẹn và bảo mật**

- [ ] Có checksum/signature cho evidence quan trọng.
- [ ] Quyền truy cập theo least privilege.
- [ ] Secret và dữ liệu cá nhân được redact hoặc loại bỏ.
- [ ] Dữ liệu được mã hóa khi truyền và lưu.
- [ ] Có access audit và deletion audit.
- [ ] Có quy trình incident hold và legal hold.

**Khả năng điều tra và xóa**

- [ ] Timestamp và correlation ID có thể ghép timeline.
- [ ] Có diễn tập tìm kiếm và restore archive.
- [ ] Có kiểm tra checksum sau restore.
- [ ] Thời gian khôi phục đáp ứng nhu cầu incident.
- [ ] Có deletion policy cho mọi bản sao.
- [ ] Thay đổi retention policy được review và version hóa.

## 25. Kết luận

Thời gian lưu bằng chứng cần được thiết kế từ câu hỏi điều tra, độ trễ phát hiện sự cố, vòng đời artifact và mức độ nhạy cảm của dữ liệu. Log, metric, trace, pipeline report, security finding, SBOM, provenance, approval và deployment record có giá trị và chi phí khác nhau; vì vậy chúng cần chính sách riêng.

Một lifecycle tốt xác định mốc bắt đầu, thời hạn, tầng lưu trữ, quyền truy cập, tính toàn vẹn, hold và cách xóa. Metadata và correlation ID giúp ghép timeline; checksum, chữ ký và audit trail giúp bảo vệ nguồn gốc; diễn tập restore chứng minh bằng chứng thực sự có thể sử dụng. Khi retention được kiểm soát theo rủi ro và mục đích, nhóm có đủ dữ liệu để điều tra release và sự cố mà không phải giữ vô hạn mọi dữ liệu phát sinh từ pipeline.
