# Data export

## 1. Audit cho export cần trả lời được dữ liệu đã đi tới bước nào

Data export là quá trình tạo hoặc truyền một biểu diễn dữ liệu ra khỏi ranh giới xử lý hiện tại: tải CSV, sinh báo cáo, xuất PDF, gửi tệp cho đối tác hoặc cung cấp luồng dữ liệu cho một hệ thống khác.

Trong chương Logging và audit, mục tiêu là xác định bằng chứng nào giúp giải thích ai đã yêu cầu, phạm vi được phép, dữ liệu thực tế được tạo, ai được cấp khả năng truy cập và kết quả phân phối được quan sát.

Một access log ghi HTTP 200 cho API tạo job chưa chứng minh tệp đã được sinh. Một object tồn tại chưa chứng minh đã có người tải. Một request tải được ghi thành công ở máy chủ cũng chưa chứng minh người nhận đã đọc nội dung.

OWASP đưa hoạt động nhập và xuất dữ liệu, bao gồm báo cáo trên màn hình, vào nhóm chức năng có rủi ro cần xem xét ghi nhận. Xem [OWASP Logging Cheat Sheet — Which events to log](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html#which-events-to-log).

Trong module yêu cầu bảo mật, đặc tả cần nối được:

> Rủi ro export → mốc cần chứng minh → dữ liệu audit tối thiểu → nguồn đáng tin → cơ chế ghi bền và đối soát → giới hạn kết luận.

Audit hỗ trợ giải trình và phát hiện; authorization, giới hạn dữ liệu và kiểm soát phân phối vẫn phải được thực thi tại các ranh giới tương ứng.

## 2. Kiểm kê các luồng export và câu hỏi điều tra

### 2.1. Không chỉ có nút tải CSV

| Luồng minh họa | Đặc điểm bằng chứng cần xem xét |
|---|---|
| Export đồng bộ | Quyết định quyền, phạm vi và truyền nội dung có thể xảy ra trong một request |
| Job export nền | Cần nối người yêu cầu với worker, từng lần chạy, artifact và các lượt tải |
| Báo cáo định kỳ | Người cấu hình, chủ thể ủy quyền hiện hành, lịch chạy và người nhận có thể khác nhau |
| Gửi dữ liệu tới đối tác | Cần phân biệt đã gửi, bên nhận đã tiếp nhận và xử lý đã được xác nhận |
| Xuất PDF hoặc in | Có artifact hoặc kênh phân phối riêng, không chỉ response HTML |
| Truy vấn và báo cáo trên màn hình | Có thể cung cấp lượng lớn dữ liệu dù không có tệp export |
| Công cụ quản trị hoặc hỗ trợ | Có đường đọc trực tiếp và quyền khác với người dùng thông thường |
| Export qua object storage | Ứng dụng, gateway và kho object có thể quan sát các mốc khác nhau |

Phạm vi phải chỉ rõ những đường thuộc trách nhiệm của dự án. Nếu chỉ instrument controller của chức năng CSV, không được kết luận mọi đường dữ liệu đi ra đã được quan sát.

### 2.2. Các câu hỏi cần có bằng chứng

Với một vụ việc cụ thể, hệ thống nên giúp xác định:

- Ai khởi tạo yêu cầu, ai thực thi, ai phê duyệt nếu có và ai được phép nhận?
- Yêu cầu thuộc tenant nào và đã được đánh giá theo policy nào?
- Phạm vi yêu cầu khác gì phạm vi được cho phép và phạm vi thực tế?
- Artifact nào thuộc lần chạy nào, được tạo từ snapshot hoặc cách đọc nguồn nào?
- Bao nhiêu dòng hoặc byte được tạo theo định nghĩa đếm đã chọn?
- Khả năng truy cập được cấp qua kênh nào, trong khoảng thời gian nào?
- Có lượt truy cập hoặc truyền dữ liệu nào được quan sát, với mức tin cậy nào?
- Có phần thất bại, bị hủy, hết hạn hoặc thiếu bằng chứng nào không?

Không phải mọi câu hỏi đều cần dữ liệu nội dung. Reference và metadata được kiểm soát có thể đủ cho mục đích điều tra nếu chúng được thiết kế từ đầu.

## 3. Mô hình đe dọa cho bằng chứng export

| Rủi ro | Tình huống | Mục tiêu yêu cầu |
|---|---|---|
| R1: thiếu chuỗi bằng chứng | Chỉ có event tạo job, không nối được artifact và tải | Có mốc, ID liên kết và nguồn chịu trách nhiệm rõ |
| R2: ghi sai phạm vi | Log ghi filter client gửi nhưng worker xuất rộng hơn | Tách phạm vi yêu cầu, được phép và thực tế |
| R3: gán sai chủ thể | Chỉ thấy service account của worker hoặc khóa ký link | Phân biệt người khởi tạo, workload và danh tính được quan sát |
| R4: báo thành công sai | Tệp một phần hoặc kết nối đứt vẫn ghi “đã nhận dữ liệu” | Định nghĩa chính xác trạng thái và điểm quan sát |
| R5: audit làm lộ dữ liệu | Log có CSV, raw SQL, filter nhạy cảm hoặc URL mang token | Tối thiểu hóa và bảo vệ trước khi phân phối event |
| R6: mất hoặc đếm trùng | Retry, event đến trễ hoặc log nhà cung cấp không đầy đủ | Ghi bền, nhận diện trùng, đối soát và thể hiện khoảng thiếu |
| R7: đọc hoặc sửa audit ngoài quyền | Người hỗ trợ đọc export của tenant khác hoặc sửa dấu vết | Phân quyền, bảo vệ toàn vẹn và audit việc truy cập audit |
| R8: bằng chứng hoặc bản sao giữ quá lâu | Export, log, mapping và backup có vòng đời không rõ | Retention và trách nhiệm cho từng lớp dữ liệu |

Cần nêu bên tấn công có thể kiểm soát client, tài khoản người dùng, worker, kho artifact hoặc tài khoản vận hành. Cùng một cơ chế logging không tự cung cấp mọi mức bảo đảm trước các khả năng đó.

Một người được phép export cũng có thể lạm dụng quyền về khối lượng hoặc mục đích. Ngược lại, khối lượng tăng chưa đủ để kết luận có hành vi xấu nếu chưa xét lịch chạy và nghiệp vụ.

## 4. Danh mục sự kiện theo vòng đời

### 4.1. Mỗi mốc phải có ý nghĩa cụ thể

| Mốc | Event minh họa | Điều event có thể chứng minh |
|---|---|---|
| Nhận yêu cầu | `EXPORT_REQUEST_RECEIVED` | Nguồn đã nhận một yêu cầu, chưa khẳng định được phép |
| Đánh giá quyền | `EXPORT_DECISION_RECORDED` | Có quyết định và phạm vi được policy đánh giá |
| Phê duyệt nếu áp dụng | `EXPORT_APPROVAL_RECORDED` | Chủ thể có thẩm quyền đã quyết định theo quy trình |
| Bắt đầu chạy | `EXPORT_GENERATION_STARTED` | Một worker và attempt bắt đầu xử lý |
| Tạo xong artifact | `EXPORT_ARTIFACT_GENERATED` | Artifact và metadata thực tế đã được ghi nhận tại mốc đã định |
| Cho phép phân phối | `EXPORT_ARTIFACT_PUBLISHED` | Artifact được chuyển sang trạng thái có thể truy cập theo contract |
| Cấp khả năng truy cập | `EXPORT_ACCESS_GRANTED` | Đã cấp một quyền hoặc phương tiện truy cập có phạm vi |
| Bắt đầu truyền | `EXPORT_DELIVERY_STARTED` | Một đường phân phối bắt đầu phục vụ theo điểm quan sát |
| Kết thúc quan sát truyền | `EXPORT_DELIVERY_OBSERVED` | Máy chủ hoặc kênh đã quan sát kết quả cụ thể của lần truyền |
| Thất bại hoặc hủy | `EXPORT_ATTEMPT_FAILED`, `EXPORT_CANCELLED` | Một attempt hoặc yêu cầu bị kết thúc theo nguyên nhân đã ghi |
| Chấm dứt truy cập | `EXPORT_ACCESS_EXPIRED`, `EXPORT_ACCESS_REVOKED` | Khả năng truy cập được xử lý ở ranh giới đã định |
| Dọn artifact | `EXPORT_ARTIFACT_DISPOSAL_RECORDED` | Có kết quả xử lý vòng đời trong phạm vi được xác minh |

Tên event là thiết kế minh họa, không phải tiêu chuẩn bắt buộc. Một dự án có thể dùng ít loại hơn với trường phase và outcome rõ ràng.

### 4.2. Quyết định, thực thi và xác minh không được gộp

`ALLOWED` là kết quả quyết định. `GENERATED` nói về artifact. `DELIVERY_STARTED` nói về một lần truyền. Chúng không thay thế nhau bằng một trạng thái `SUCCESS` chung.

Một phản hồi “đã nhận job” chưa chứng minh worker đã chạy. Một receipt từ đối tác có thể chỉ xác nhận nhận tác vụ, không chứng minh đã nhập hoặc đọc dữ liệu.

Nếu kết quả chưa xác định, event cần biểu diễn điều đó. Không điền “thất bại” hoặc “thành công” chỉ vì một code path không có đủ nhánh cho trạng thái chưa biết.

### 4.3. Ghi cả các quyết định từ chối có ý nghĩa

Request vượt quyền, yêu cầu cột ngoài policy, tải artifact tenant khác hoặc dùng link hết hạn có thể là tín hiệu điều tra quan trọng.

Metadata của sự kiện từ chối cũng phải giới hạn. Không ghi toàn bộ dữ liệu của tài nguyên mà người gọi không được phép biết chỉ để giải thích tại sao bị từ chối.

## 5. Schema liên kết chủ thể, phạm vi và artifact

### 5.1. Các nhóm trường cần lựa chọn

| Nhóm | Trường minh họa | Điều cần đặc tả |
|---|---|---|
| Event | eventId, eventType, schemaVersion | Một quan sát cụ thể và cách diễn giải |
| Thời gian và nguồn | occurredAt, observedAt, producerId, release | Nguồn nào biết điều gì, khi nào |
| Luồng xử lý | requestId, jobId, generationAttemptId | Yêu cầu, job và từng lần thực thi |
| Chủ thể | initiatorRef, executorRef, approverRef | Người khởi tạo khác với worker hoặc người phê duyệt |
| Phạm vi tổ chức | tenantRef hoặc scopeRef tương ứng | Giá trị từ ngữ cảnh được xác minh |
| Chính sách | decision, reasonCode, policyVersion | Quyết định tại mốc nào và căn cứ có thể tra cứu |
| Dữ liệu | datasetRef, requestedScopeRef, effectiveScopeRef, schemaRef | Phạm vi yêu cầu, được phép và dạng đầu ra |
| Nguồn dữ liệu | snapshotRef hoặc consistencyMode | Cách xác định tập dữ liệu tại lúc chạy |
| Artifact | artifactId, artifactVersion, contentDigest nếu phù hợp | Liên kết tới đúng bản tạo ra |
| Khối lượng | rowsWritten, artifactBytes, countDefinition | Đếm dòng, header, định dạng và byte theo quy tắc nào |
| Phân phối | accessGrantId, deliveryAttemptId, recipientRef | Cấp truy cập khác với từng lần sử dụng |
| Kết quả | phase, outcome, evidenceRef | Trạng thái quan sát và bằng chứng bổ sung |

Không bắt buộc mọi event chứa mọi trường. Một event từ chối trước tạo job có thể không có job ID hoặc artifact. Một luồng stream có thể không tạo tệp bền vững và cần reference cho phiên truyền.

### 5.2. Actor và tenant phải đến từ nguồn phù hợp

Người dùng có thể gửi tenant ID, mục đích hoặc địa chỉ người nhận trong request. Audit cần phân biệt dữ liệu được yêu cầu với thông tin đã được xác minh và chấp nhận.

Worker thường dùng workload identity để đọc dữ liệu. Nếu audit chỉ ghi service account đó, sẽ khó truy lại người hoặc lịch chạy đã ủy quyền. Cần quan hệ giữa initiator, decision và execution.

Với export định kỳ, hãy giữ thông tin cấu hình hoặc lịch được phê duyệt và chủ thể chịu trách nhiệm. Không mặc định coi người tạo lịch từ lâu là danh tính hiện đang thực hiện mọi lần tải.

### 5.3. Phạm vi thực tế cần bằng chứng riêng

Raw filter từ client chưa chứng minh worker thực thi đúng filter. Cần kết quả phạm vi được cho phép và cách worker ràng buộc truy vấn vào phạm vi đó.

Nếu dữ liệu thay đổi trong lúc export, snapshot hoặc consistency mode giúp giải thích tập dữ liệu. Không ghi một số lượng ước lượng ban đầu thành số dòng thực tế được ghi ra tệp.

Schema đầu ra cần có reference hoặc phiên bản rõ. Số dòng đúng vẫn có thể đi cùng cột nhạy cảm ngoài quyền; audit không được chỉ lưu mỗi row count rồi kết luận phạm vi phù hợp.

## 6. Ví dụ sự kiện và chuỗi đối soát

### 6.1. Sự kiện tạo artifact

Giả sử một job tạo CSV khách hàng theo profile cột đã được phê duyệt:

```json
{
  "schemaVersion": 1,
  "eventId": "event-example-111",
  "eventType": "EXPORT_ARTIFACT_GENERATED",
  "occurredAt": "2026-11-27T08:00:00Z",
  "producerId": "customer-export-worker",
  "tenantRef": "tenant-example-a",
  "initiatorRef": "user-example-7",
  "executorRef": "workload-example-export",
  "requestId": "request-example-83",
  "jobId": "job-example-17",
  "generationAttemptId": "generation-example-2",
  "datasetRef": "dataset-example-customer",
  "effectiveScopeRef": "scope-example-31",
  "schemaRef": "customer-contact-export-example-4",
  "snapshotRef": "snapshot-example-9",
  "policyVersion": "export-policy-example-4",
  "artifactId": "artifact-example-17",
  "artifactVersion": "version-example-2",
  "rowsWritten": 2500,
  "artifactBytes": 153600,
  "countDefinition": "DATA_ROWS_EXCLUDING_HEADER",
  "outcome": "GENERATED"
}
```

Các giá trị đều giả lập và schema thuộc ứng dụng minh họa. Event không nói rằng tệp đã được tải, người nhận đã đọc hoặc mọi dữ liệu đều được phép chỉ từ số lượng.

Nếu job chạy lại, cần generationAttemptId mới và cách xác định artifact nào được công bố. Không dùng cùng một ID bất biến cho các nội dung khác nhau mà không có version hoặc quan hệ rõ.

### 6.2. Chuỗi cần nối được

```text
request-example-83
    → quyết định quyền và phạm vi
    → job-example-17
    → generation-example-2
    → artifact-example-17 / version-example-2
    → quyết định công bố
    → access grant hoặc phiên tải
    → từng delivery attempt và kết quả quan sát
```

Một điều tra cần xem các quan hệ này và phần nào còn thiếu. Không ghép chỉ bằng tên tệp hoặc một timestamp gần nhau nếu có nhiều export tương tự.

### 6.3. Reference và digest có vai trò giới hạn

Scope reference phải trỏ tới metadata được bảo vệ, có ý nghĩa ổn định đủ để giải thích quyết định trong thời hạn cần thiết. Không để một scope bị sửa tại chỗ làm thay đổi cách diễn giải lịch sử.

Digest của artifact có thể hỗ trợ đối chiếu đúng nội dung khi có bằng chứng thích hợp. Nó không tự chứng minh authorization hoặc tính đầy đủ của dữ liệu, và cũng có thể tiết lộ quan hệ bằng nhau giữa các tệp.

Không lưu hash từng email hoặc số điện thoại rồi mặc định coi đó là dữ liệu ẩn danh. Cần đánh giá thông tin liên kết và mục đích giữ của các reference hoặc digest.

## 7. Ghi bền tại các ranh giới có ý nghĩa

### 7.1. Tạo job và event cần được phối hợp

Nếu job được commit nhưng event quyết định bị mất, điều tra có thể thiếu căn cứ. Nếu ghi “job đã tạo” trước rồi transaction rollback, log lại mô tả một việc chưa xảy ra.

Khi có cùng ranh giới giao dịch, có thể ghi trạng thái job và outbox event trong cùng transaction. Publisher chuyển tiếp với retry và nhận diện trùng theo contract.

Cần nêu rõ mốc nào được coi là ghi bền, khả năng chịu lỗi và cách đối soát. Việc một thư viện nhận lệnh ghi không đồng bộ chưa chứng minh event đã tồn tại bền vững ở đích.

### 7.2. Artifact ngoài database cần workflow riêng

Ghi object và cập nhật job thường không nằm trong cùng một giao dịch nguyên tử. Luồng minh họa:

```text
Tạo artifact trong vùng chưa được phân phối
    → xác minh kết quả ghi, version, schema và metadata thực tế
    → gắn artifact với job và attempt
    → ghi quyết định công bố cùng bằng chứng audit cần thiết
    → mở khả năng truy cập qua đường được kiểm soát
```

Nếu worker dừng sau khi tạo object nhưng trước khi ghi trạng thái, có thể còn artifact mồ côi. Cần đối soát, cách ly hoặc dọn theo policy; không tự coi object đó là một bản xuất đã được phê duyệt.

Nếu dùng trạng thái ready và outbox trong database, đường phân phối phải thật sự kiểm tra trạng thái và điều kiện cần thiết. Một object đã public hoặc một đường đọc khác bỏ qua kiểm tra sẽ phá vỡ ranh giới này.

### 7.3. Ghi đúng mốc trước khi dữ liệu rời hệ thống

Với export nhạy cảm, dự án có thể yêu cầu quyết định cấp truy cập được ghi bền trước khi cấp link hoặc bắt đầu phục vụ nội dung.

Sự kiện trước khi gửi byte nên mô tả đúng là đã cho phép hoặc chuẩn bị phân phối. Không gọi nó là “đã truyền hoàn tất”. Khi máy chủ quan sát bắt đầu và kết thúc truyền, cần event hoặc kết quả bổ sung tương ứng.

Không có một transaction đơn giản bao trùm database audit và mọi byte tới thiết bị người nhận. Crash giữa các mốc có thể để lại kết quả chưa xác định. Contract và báo cáo phải biểu diễn được giới hạn đó.

### 7.4. Audit lỗi không được đổi quyết định cấp quyền

Nếu điều kiện ghi bền bắt buộc không đạt, luồng phải giữ chờ hoặc từ chối theo policy đã chọn. Không để logger ném exception rồi đi vào nhánh công bố artifact mặc định.

Nếu collector tạm lỗi nhưng outbox bền vững còn đáp ứng contract, hệ thống có thể tiếp tục theo chính sách được phê duyệt. Cần giới hạn backlog, dung lượng và điều kiện ngừng cấp thêm truy cập.

Phải phân biệt mất khả năng tra cứu tức thời với mất bằng chứng bắt buộc. Không áp cùng một phản ứng cho mọi loại lỗi logging mà không xét thiết kế.

## 8. Đường tải, link ký và log nhà cung cấp

### 8.1. Tải qua ứng dụng có xác thực

Khi nội dung đi qua một dịch vụ tải có xác thực, dịch vụ có thể ghi người gọi đã xác minh, quyết định quyền hiện hành, artifact version và deliveryAttemptId.

Cần bao phủ tải mới, tải tiếp, request một phần nếu hỗ trợ, redirect, CDN và các đường khác có thể phục vụ artifact. Một request chỉ lấy metadata hoặc HEAD không nên được đếm như đã tải toàn bộ dữ liệu.

Nếu kết nối kết thúc bất thường, event cần nêu điều máy chủ đã quan sát và lượng byte theo định nghĩa của nguồn. Không tự kết luận người nhận chắc chắn không có dữ liệu nào.

### 8.2. Presigned URL là một khả năng truy cập

Một link ký có thể được chuyển cho người khác. Danh tính trong log kho lưu trữ không nhất thiết là người dùng ứng dụng đang sử dụng link.

Tài liệu Amazon S3 nêu presigned URL là bearer token, log nhận diện bên ký thay vì khẳng định ai dùng link sau đó; việc phát hành cần được ghi nhận ở ứng dụng để đối soát. Xem [Amazon S3 — Auditing presigned URLs](https://docs.aws.amazon.com/AmazonS3/latest/userguide/using-presigned-url.html#auditing-presigned-urls).

Vì vậy, event “đã cấp link cho U” không tự chứng minh “U đã tải”. Cần giữ các thuộc tính riêng: người được cấp, bên ký, request được kho quan sát và mức tin cậy về người sử dụng.

Nếu nghiệp vụ yêu cầu nhận diện người tải theo phiên ứng dụng, phải chọn đường phân phối có cơ chế đáp ứng yêu cầu đó. Không suy ra khả năng này chỉ từ việc URL có chữ ký.

### 8.3. Kiểm tra cấu hình quan sát ở tầng dữ liệu

Log quản trị bucket và log đọc object có phạm vi khác nhau. Trong ví dụ S3, CloudTrail data events không được ghi mặc định và không nằm trong Event history; cần cấu hình theo tài nguyên và loại sự kiện phù hợp. Xem [Amazon S3 CloudTrail events](https://docs.aws.amazon.com/AmazonS3/latest/userguide/cloudtrail-logging-s3-info.html).

Đây là ví dụ cụ thể về việc kiểm tra contract của nhà cung cấp. Một tùy chọn tên “audit enabled” ở nơi nào đó chưa chứng minh tất cả đường tải dữ liệu đã được bao phủ.

Cần thử bằng một thao tác đọc được phép trong môi trường kiểm tra, xác nhận nguồn, operation, resource version hoặc reference và độ trễ đúng theo contract. Không chỉ kiểm tra file cấu hình.

### 8.4. Log đến trễ hoặc thiếu phải được diễn giải đúng

Amazon S3 server access logging được mô tả là best effort, không bảo đảm đầy đủ hoặc kịp thời và có thể có bản ghi trùng. Xem [Amazon S3 — Best-effort server log delivery](https://docs.aws.amazon.com/AmazonS3/latest/userguide/ServerLogs.html#LogDeliveryBestEffort).

Một suy luận từ giới hạn đó là không thể dùng việc chưa thấy bản ghi như bằng chứng chắc chắn không có request. Khi nguồn không đủ bảo đảm cho mục tiêu audit, cần nguồn bổ sung hoặc thay đổi đường phân phối.

Mục tiêu tra cứu 60 giây của event nội bộ, nếu có, không tự áp dụng cho log của nhà cung cấp có thời gian giao khác. Dashboard cần tách nguồn và trạng thái độ trễ.

### 8.5. Không ghi nguyên link để tiện đối soát

Ứng dụng nên giữ accessGrantId hoặc reference của lần phát hành, artifact, thời hạn và chủ thể được phép theo schema. Không ghi toàn bộ presigned URL hoặc credential vào log.

Một số log ở tầng hạ tầng có thể chứa URI hoặc query nhạy cảm. Cần kiểm soát quyền ở đích gốc và quá trình làm sạch trước khi đưa tiếp sang hệ thống khác; không chỉ sửa event ứng dụng rồi bỏ qua nguồn này.

## 9. Đếm khối lượng và phát hiện hành vi có ngữ cảnh

### 9.1. Các đại lượng không thay thế nhau

| Đại lượng | Câu hỏi trả lời | Giới hạn |
|---|---|---|
| Số yêu cầu | Có bao nhiêu ý định export được nhận | Có thể có retry hoặc bị từ chối |
| Số job | Bao nhiêu đơn vị xử lý được tạo | Một job có nhiều attempt |
| Số artifact | Bao nhiêu bản nội dung được tạo hoặc công bố | Một artifact có thể không được tải |
| Số access grant | Bao nhiêu khả năng truy cập được cấp | Một grant có thể dùng nhiều lần tùy thiết kế |
| Số delivery attempt | Có bao nhiêu request hoặc phiên truyền | Có tải tiếp, request một phần và lần thất bại |
| Rows written | Bao nhiêu dòng dữ liệu được ghi ra artifact | Không tự là số cá nhân hoặc số dòng người nhận đã đọc |
| Bytes observed | Lượng byte nguồn phân phối quan sát theo định nghĩa | Có nén, overhead, retry và phần chồng lấn |

Ví dụ, một artifact 2.500 dòng được tải lại hai lần không có nghĩa là có 5.000 cá nhân khác nhau. Hai lần ghi log cùng một request cũng không tạo hai lượt tải thực.

### 9.2. Byte và dòng cần định nghĩa đếm

Cần nói rõ artifactBytes là kích thước object, nội dung chưa nén hay dạng đã mã hóa. Với đường truyền, nguồn có thể đo byte ứng dụng ghi ra chứ không phải byte chắc chắn được lưu trên thiết bị người dùng.

Các range request có thể chồng lấn. Tổng byte của chúng có thể lớn hơn kích thước artifact; không dùng tổng đó để suy ra số dòng duy nhất đã nhận.

Rows written cần quy định có tính header, dòng tổng, sheet phụ hoặc bản ghi lỗi không. Dữ liệu một dòng có thể biểu diễn nhiều chủ thể, nên không đổi trực tiếp row count thành số người.

### 9.3. Phát hiện cần xét cả tích lũy và bối cảnh

Có thể theo dõi khối lượng theo người khởi tạo, workload, tenant, tập dữ liệu và cửa sổ thời gian. Một người chia export thành nhiều tệp nhỏ có thể không vượt ngưỡng mỗi tệp nhưng vẫn tăng đáng kể tổng lượng dữ liệu.

Cần đối chiếu lịch chạy định kỳ, thay đổi vai trò, loại dữ liệu, người nhận mới và chuỗi yêu cầu bị từ chối. Một đợt export hợp lệ cho đối soát có thể khác với hành vi thử liên tục nhiều schema nhạy cảm.

Metric label nên dùng danh mục hữu hạn như loại dữ liệu và operation. Request ID, link, email hoặc object key tùy ý không nên trở thành label không giới hạn.

Một cảnh báo biểu diễn dấu hiệu và bằng chứng cần kiểm tra, không tự tuyên bố đã có rò rỉ trái phép chỉ vì số lượng tăng.

## 10. Tối thiểu hóa, quyền và vòng đời bằng chứng

### 10.1. Không tạo bản export thứ hai trong log

Audit thường không cần giữ nội dung CSV, bản ghi mẫu, SQL đầy đủ hoặc mọi giá trị filter. Những dữ liệu đó có thể làm kho audit nhạy cảm như chính nguồn được xuất.

Có thể dùng datasetRef, schemaRef, scopeRef và các thuộc tính tổng hợp được phê duyệt. Reference phải đủ để giải thích trong thời hạn cần thiết, có quyền truy cập và cách xử lý khi hết retention.

Một scope có điều kiện nhạy cảm cũng cần bảo vệ. Hash filter hoặc định danh không tự loại bỏ khả năng dò hoặc liên kết.

Đầu vào như tên tệp, lý do tự do và tên người nhận cần được kiểm tra, giới hạn và encode. Không để chúng chèn event giả hoặc markup vào công cụ xem.

### 10.2. Bảo vệ nguồn và tính toàn vẹn

Workload phát event chỉ cần quyền theo loại và phạm vi. Người điều tra cần quyền đọc đúng vụ việc; quyền sửa, xóa hoặc thay retention cần tách và có audit.

Có thể dùng cơ chế lưu bất biến, manifest hoặc kiểm tra toàn vẹn phù hợp với mô hình đe dọa. Cần xác định điểm tin cậy và khả năng phát hiện mất đoạn, không chỉ checksum của một tệp log.

Một cơ chế toàn vẹn không tự chứng minh event chưa bị gán sai phạm vi tại nguồn. Cần kết hợp kiểm tra ở worker và đối soát với inventory, trạng thái job hoặc nguồn khác.

### 10.3. Audit việc xem và xuất audit

Công cụ tra cứu phải kiểm tra tenant, vụ việc, vai trò và trường được phép. Người biết job ID hoặc artifact ID không tự được đọc audit tương ứng.

Export kết quả audit tạo thêm một artifact cần quản lý người nhận, schema, khả năng tải và vòng đời. Không bỏ qua nó chỉ vì nó phục vụ điều tra nội bộ.

### 10.4. Tách vòng đời artifact với vòng đời audit

Một artifact có thể hết thời hạn tải sau 15 phút, được dọn trong 24 giờ tiếp theo, trong khi metadata audit được giữ lâu hơn theo policy. Đây là những mục tiêu khác nhau.

Hết hạn truy cập chưa chứng minh object đã bị xóa. Xóa object ở kho chính chưa chứng minh các version hoặc backup đã hết vòng đời. Event xử lý cần nói rõ phạm vi và mức xác minh.

Audit có thể giữ reference và bằng chứng tối thiểu theo mục đích, nhưng không được giữ nguyên dữ liệu export mặc định chỉ vì thời hạn audit dài hơn.

## 11. Ví dụ yêu cầu đo được và ma trận nghiệm thu

### 11.1. Giả định của cổng quản trị

Dự án minh họa sử dụng job nền, kho artifact riêng tư và dịch vụ tải có xác thực. Nhóm chọn:

- Các quyết định export, tạo artifact, công bố, cấp truy cập, từ chối tải và kết quả phân phối thuộc danh mục event bắt buộc.
- Mỗi event có ID, nguồn và reference đủ nối request, job, attempt, artifact hoặc grant theo mốc tương ứng.
- Không sampling các event bắt buộc của luồng đã cam kết.
- Quyết định công bố hoặc cấp khả năng truy cập phải có bằng chứng ghi bền tại ranh giới được phê duyệt trước khi mở truy cập.
- Event nội bộ có thể tra cứu trong 60 giây từ lúc ghi bền ở nguồn khi pipeline hoạt động bình thường.
- Chênh lệch đối soát hoặc backlog quá 5 phút phải tạo tín hiệu vận hành.
- Event JSON không quá 8 KiB UTF-8, không chứa payload hoặc URL mang bí mật truy cập.
- Metadata audit ở kho chính giữ 90 ngày theo mốc tin cậy đã chọn; các bản sao và mapping có policy riêng được đưa vào giới hạn lưu giữ tổng.

**Các con số là giả định minh họa, không phải yêu cầu mặc định từ OWASP hoặc AWS.** Bảo đảm của nguồn nội bộ và của nhà cung cấp phải được mô tả riêng.

Nếu pipeline không đáp ứng điều kiện ghi bền bắt buộc, luồng có thể giữ chờ hoặc từ chối theo policy. Tải tăng không được là lý do tự tắt audit rồi tiếp tục phân phối như bình thường.

### 11.2. Ma trận rủi ro, yêu cầu và bằng chứng

| Mã | Rủi ro | Yêu cầu cụ thể | Bằng chứng nghiệm thu |
|---|---|---|---|
| EXA-01 | R1 | Danh mục bao phủ API, job, lịch chạy và đường phân phối thuộc phạm vi | Thực hiện từng luồng giả lập; xác định được nguồn chịu trách nhiệm và mốc thiếu nếu có |
| EXA-02 | R1, R4 | Ghi riêng quyết định, tạo artifact, công bố và phân phối; bao phủ từ chối | Request bị từ chối không có event tạo artifact thành công; API nhận job chưa bị báo thành đã tải |
| EXA-03 | R3 | Giữ quan hệ người khởi tạo, workload, người duyệt và người được cấp truy cập nếu áp dụng | Job nền và lịch chạy không chỉ có service account; actor hoặc tenant tự khai không được coi là đã xác minh |
| EXA-04 | R2 | Phạm vi yêu cầu, hiệu lực và thực tế có reference và schema đúng phiên bản | Dữ liệu thử có cột hoặc dòng ngoài quyền không xuất hiện trong artifact; metadata khớp kết quả thực tế |
| EXA-05 | R2, R4 | Artifact gắn đúng attempt, version và metadata đo sau khi ghi hoàn tất | Worker retry hoặc tạo object một phần không công bố nhầm; digest nếu dùng khớp bản đã được kiểm tra |
| EXA-06 | R6 | Có ghi bền trước ranh giới công bố hoặc cấp truy cập theo policy | Làm lỗi nơi ghi bền bắt buộc: object vẫn riêng tư và không cấp link; outbox đủ điều kiện được xử lý đúng contract |
| EXA-07 | R3, R4 | Mỗi lượt phân phối có mức nhận diện và kết quả quan sát rõ | Link chuyển cho chủ thể khác không bị quy chắc cho người được cấp; kết nối đứt không thành “người dùng đã đọc” |
| EXA-08 | R6 | Nhận diện event trùng và phân biệt job, artifact, grant, delivery attempt | Retry event không tăng số job; tải lại hoặc range có số liệu đúng định nghĩa, không tự suy ra số người |
| EXA-09 | R5 | Schema tối thiểu, xử lý dữ liệu trước phân phối và chống log injection | Token, URL ký, filter nhạy cảm và payload thử không xuất hiện ở các đích không được phép; không tạo event giả |
| EXA-10 | R7 | Quyền đọc, xuất và thay cấu hình audit theo tenant và vai trò | Đổi job ID, tenant hoặc endpoint không đọc được audit ngoài quyền; thay policy có dấu vết riêng |
| EXA-11 | R6 | Đối soát nguồn, cảnh báo backlog và thể hiện chất lượng bằng chứng | Tắt nguồn log hoặc gây mất event có kiểm soát; báo cáo hiển thị khoảng thiếu, không kết luận không có export |
| EXA-12 | R8 | Retention và xử lý artifact, audit, mapping, version và backup có phạm vi rõ | Kiểm tra hết hạn tải, dọn artifact và vòng đời audit; báo cáo không gộp hết hạn thành đã xóa mọi bản sao |

Các phép kiểm tra phải quan sát cả event lẫn trạng thái và dữ liệu thực tế. Một log tự khai “scope hợp lệ” không đủ để nghiệm thu phạm vi export.

### 11.3. Tiêu chí chấp nhận cho ghi bền trước phân phối

```gherkin
Given artifact A da duoc tao trong vung rieng tu
And policy yeu cau bang chung ghi ben truoc khi cong bo
When noi ghi ben bat buoc khong the chap nhan su kien
Then A chua duoc mo truy cap theo duong phan phoi
And khong cap link hoac quyen tai cho nguoi nhan
And trang thai cho hoac tu choi duoc the hien theo policy
And khong ghi payload hoac URL mang token vao fallback
```

### 11.4. Tiêu chí chấp nhận cho truyền bị gián đoạn

```gherkin
Given mot luot tai da duoc xac thuc va cho phep
When may chu quan sat ket noi bi ngat sau khi da gui mot phan
Then delivery attempt ghi ket qua quan sat gian doan
And luong byte neu co dung dinh nghia cua nguon do
And bao cao khong khang dinh nguoi nhan chua co du lieu
And cung khong khang dinh nguoi nhan da nhan hoac doc toan bo artifact
```

### 11.5. Tiêu chí chấp nhận cho thiếu log từ kho lưu trữ

```gherkin
Given nguon access log co bao dam best effort theo contract
When chua tim thay ban ghi cho mot khoang thoi gian
Then bao cao neu ro nguon va do tre hoac gioi han bao phu
And khong ket luan chac chan rang khong co request
And thuc hien doi soat voi nguon khac neu muc tieu yeu cau
```

Đây là tiêu chí để xây dựng kiểm thử dự án, không phải thông báo rằng một hệ thống thực tế đã vượt qua các kiểm tra.

## 12. Điều tra, vận hành và quản lý thay đổi

### 12.1. Kiểm tra cả lỗi và đường đi vòng

Dữ liệu thử cần bao phủ yêu cầu hợp lệ, vượt quyền, đổi tenant, worker crash, artifact một phần, retry, nhiều lần tải, tải tiếp và link bị chuyển.

Cần thử đường đọc object trực tiếp hoặc công cụ quản trị nếu chúng thuộc phạm vi. Một luồng ứng dụng được instrument đầy đủ không bù được đường dữ liệu khác hoàn toàn không được kiểm soát hoặc quan sát.

Kiểm tra các kênh tự động như báo cáo định kỳ, email và đối tác. Người khởi tạo lịch, workload thực thi và người nhận cần được diễn giải đúng trong chuỗi bằng chứng.

### 12.2. Báo cáo cần giữ giới hạn kết luận

Một báo cáo có thể nói artifact đã được tạo, link đã được cấp và có request đọc được quan sát theo nguồn xác định. Chỉ nên kết luận về người nhận hoặc nội dung đã đọc khi có bằng chứng phù hợp.

Nếu có khoảng mất dữ liệu, log đến trễ hoặc thay đổi cấu hình thu thập, phải ghi rõ ảnh hưởng tới khả năng đối soát. Không backfill một event giả như thể nó đã được quan sát ở thời điểm trước.

Bằng chứng không đủ cho một kết luận cũng là một kết quả cần quản lý. Nó giúp xác định nơi phải cải thiện kiến trúc hoặc policy ghi nhận.

### 12.3. Thay đổi kiến trúc phải cập nhật audit

Chuyển từ tải qua ứng dụng sang link ký có thể làm thay đổi khả năng nhận diện người sử dụng. Bật CDN, cho phép range, đổi định dạng nén hoặc tách worker cũng thay đổi cách đếm và nguồn quan sát.

Khi thay schema, policy hoặc transaction boundary, cần cập nhật event catalog, mapping, runbook và kiểm thử. Một trường vẫn cùng tên nhưng đổi ý nghĩa sẽ làm sai báo cáo lịch sử.

### 12.4. Những câu đặc tả cần viết rõ hơn

| Câu còn mơ hồ | Điều cần bổ sung |
|---|---|
| “Log mỗi lần export” | Mốc nhận yêu cầu, tạo tệp, cấp truy cập hay truyền dữ liệu |
| “Ghi ai đã tải” | Danh tính được xác thực, bên ký link, người được cấp hay nguồn mạng quan sát |
| “Ghi filter và số dòng” | Phạm vi được phép, snapshot, schema, số thực tế và cách đếm |
| “HTTP 200 nghĩa là thành công” | Thành công của bước nào và dữ liệu nào đã được quan sát |
| “Có log storage là đủ” | Loại sự kiện, cấu hình nguồn, độ đầy đủ, độ trễ và ID liên kết |
| “Log không có dữ liệu nhạy cảm” | Payload, token, URL, raw query, reference và khả năng liên kết |
| “Giữ audit 90 ngày” | Mốc tính, index, mapping, export bằng chứng, backup và ngoại lệ |
| “Không thấy tải thì chưa có rò rỉ” | Chất lượng nguồn, đường truy cập khác và giới hạn khả năng kết luận |

Một đặc tả audit cho data export cần nối được **yêu cầu → quyết định quyền và phạm vi → lần thực thi → artifact → cấp khả năng truy cập → kết quả phân phối được quan sát → vòng đời và đối soát**. Chuỗi này giúp tổ chức giải thích việc dữ liệu đi ra khỏi hệ thống bằng bằng chứng đúng phạm vi, đồng thời tránh tạo thêm rò rỉ trong chính hệ thống audit.
