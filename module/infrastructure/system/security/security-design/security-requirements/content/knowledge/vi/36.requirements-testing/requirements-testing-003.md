# Negative security test: kiểm chứng hành vi bảo mật khi điều kiện không được phép

## 1. Negative security test là gì?

Negative security test là kiểm thử được thiết kế từ những điều kiện hoặc hành vi mà hệ thống không được cho phép, nhằm kiểm chứng rằng yêu cầu bảo mật vẫn được giữ.

Ví dụ, yêu cầu “chỉ người có quyền trên tài liệu mới được tải nội dung” cần ít nhất hai hướng kiểm chứng:

- Người có quyền tải được đúng tài liệu.
- Người không có quyền không nhận được nội dung, kể cả khi biết mã tài liệu và gọi API trực tiếp.

Hướng thứ hai là kiểm thử bảo mật theo trường hợp bị cấm. Nó có thể dùng một yêu cầu hoàn toàn đúng cú pháp và một tài khoản đăng nhập hợp lệ. Điều làm tình huống trở thành negative security test là việc hành động đó vi phạm điều kiện bảo mật, không nhất thiết là dữ liệu đầu vào sai định dạng.

Một phép thử có giá trị cần trả lời:

1. Điều kiện bảo mật nào đang bị vi phạm có chủ đích?
2. Hệ thống phải phản ứng thế nào theo yêu cầu?
3. Dữ liệu, quyền và tác dụng phụ nào không được xuất hiện?
4. Cách quan sát có đủ để phân biệt từ chối an toàn với một lỗi không liên quan không?

Negative security test giúp phát hiện khoảng trống trong triển khai và trong chính đặc tả. Nếu nhóm không thống nhất được kết quả mong đợi, cần làm rõ yêu cầu trước khi gọi test là đạt hay thất bại.

## 2. Không đồng nhất negative test với “gửi dữ liệu sai”

Các hoạt động sau có thể liên quan nhưng có mục đích khác nhau:

| Hoạt động | Ví dụ | Kết luận có thể hỗ trợ |
| --- | --- | --- |
| Positive test | Người được cấp quyền sửa tài liệu thực hiện sửa hợp lệ | Luồng được phép hoạt động trong điều kiện đã thử |
| Negative functional test | Gửi ngày không đúng định dạng | Kiểm tra quy tắc dữ liệu hoặc phản hồi lỗi chức năng |
| Negative security test | Người dùng tenant B yêu cầu tải tài liệu riêng của tenant A | Kiểm tra ranh giới truy cập và việc không làm lộ dữ liệu |
| Fault injection | Làm dịch vụ kiểm tra quyền không sẵn sàng trong môi trường thử | Quan sát hành vi khi phụ thuộc lỗi; cần yêu cầu bảo mật để đánh giá |
| Fuzzing | Sinh nhiều biến thể đầu vào ngoài các trường hợp đã viết tay | Tìm hành vi bất thường; từng phát hiện cần được phân tích và tái hiện |
| Kiểm thử dựa trên thuộc tính | Thay đổi danh tính và đối tượng nhưng giữ thuộc tính “không đọc chéo tenant” | Kiểm tra một điều kiện bảo vệ trên nhiều tổ hợp |

Một test dữ liệu sai có thể đồng thời là security test nếu nó kiểm chứng một yêu cầu bảo mật cụ thể, chẳng hạn ngăn dữ liệu điều khiển trái phép đi vào một nơi xử lý nhạy cảm.

Tuy nhiên, gửi một chuỗi bất thường và nhận lỗi không tự chứng minh hệ thống an toàn. Cần có yêu cầu nguồn, trạng thái mong đợi và cách quan sát đúng tác động.

## 3. Bắt đầu từ yêu cầu, rủi ro và điều kiện bảo vệ

### 3.1. Viết mệnh đề cần giữ

Một điều kiện bảo vệ có thể được diễn đạt như sau:

> Bất kể mã đối tượng do phía gọi cung cấp, người dùng không có quyền không được đọc hoặc sửa tài liệu ngoài phạm vi được cấp.

Từ điều kiện này, nhóm xác định những chiều có thể thay đổi:

- Danh tính: chưa đăng nhập, phiên hợp lệ, phiên hết hạn, phiên đã bị thu hồi.
- Vai trò: có quyền, thiếu quyền, quyền vừa bị thay đổi.
- Tenant và đối tượng: đúng phạm vi, khác tenant, đối tượng không tồn tại.
- Trạng thái dữ liệu: đang xử lý, đã hủy, đã hoàn tất hoặc không còn được phép truy cập.
- Đường truy cập: API chính, API hàng loạt, liên kết tải, công việc nền hoặc kênh khác nếu có.
- Thời điểm: trước thay đổi quyền, sau thay đổi quyền, cạnh tranh giữa các thao tác.
- Phụ thuộc: hoạt động bình thường, timeout, lỗi hoặc trả dữ liệu chưa đủ tin cậy.

Không phải mọi tổ hợp đều có cùng giá trị. Chọn tổ hợp dựa trên rủi ro, kiến trúc và những đường có thể tạo tác động.

### 3.2. Mỗi test phải có một cơ sở kết luận

Test oracle là cơ sở để quyết định kết quả thực tế đúng hay sai. Trong bài học này, oracle gồm:

- Kết quả phản hồi hoặc trạng thái xử lý được yêu cầu.
- Điều được phép thay đổi.
- Điều không được thay đổi hoặc tiết lộ.
- Các sự kiện phải được ghi nhận.
- Thời hạn và phạm vi quan sát khi có xử lý bất đồng bộ.

Ví dụ, test “người không có quyền xuất tài liệu” có thể yêu cầu đồng thời:

1. API từ chối theo hợp đồng đã chốt.
2. Không có nội dung tài liệu trong phản hồi.
3. Không có công việc xuất được tạo cho lần gọi đó.
4. Không có tệp xuất hoặc lệnh gửi ra hệ thống ngoài từ lần gọi bị từ chối.
5. Có sự kiện audit phù hợp nhưng không chứa token hoặc nội dung tài liệu.

Nếu API trả lỗi nhưng vẫn tạo công việc nền, test phải không đạt.

### 3.3. Không tự đặt chính sách trong test

Mã HTTP, cách che giấu sự tồn tại của đối tượng, ngưỡng thu hồi quyền và hành vi khi dịch vụ phụ thuộc lỗi phải xuất phát từ yêu cầu đã được xác nhận.

Một hệ thống có thể dùng cùng phản hồi không tìm thấy cho đối tượng không tồn tại và đối tượng không được phép biết. Hệ thống khác có thể có hợp đồng khác. Không dùng một mã HTTP như quy tắc bắt buộc cho mọi sản phẩm.

Tương tự, không mặc định mọi lỗi phụ thuộc đều phải dẫn đến cùng một hành vi. Cần xác định thao tác nào phải bị từ chối, thao tác nào được dùng dữ liệu dự phòng và trong giới hạn nào.

## 4. Ví dụ xuyên suốt: dịch vụ tài liệu nhiều tenant

### 4.1. Kiến trúc và dữ liệu thử

Một dịch vụ cho phép đọc, sửa và xuất tài liệu:

1. API xác thực người dùng.
2. Dịch vụ quyền kiểm tra tenant, quyền trên tài liệu và hành động.
3. Yêu cầu xuất hợp lệ tạo công việc trong hàng đợi.
4. Worker xử lý và lưu tệp xuất.
5. API tải tệp kiểm tra quyền trước khi trả nội dung.

Bộ dữ liệu tổng hợp được tạo riêng cho mỗi lần chạy:

| Danh tính hoặc đối tượng | Phạm vi và quyền |
| --- | --- |
| A-EDITOR | Thuộc tenant A, được đọc, sửa và xuất tài liệu DOC-A |
| A-READER | Thuộc tenant A, được đọc DOC-A nhưng không được sửa hoặc xuất |
| A-NO-GRANT | Thuộc tenant A, không được truy cập DOC-A |
| B-EDITOR | Thuộc tenant B, được thao tác DOC-B và không có quyền trên DOC-A |
| DOC-A | Tài liệu tenant A, chứa marker tổng hợp riêng của lần chạy |
| DOC-B | Tài liệu tenant B, chứa marker khác |
| DOC-MISSING | Mã đã xác nhận không tồn tại trong phạm vi bộ thử |

Marker là dấu nhận diện dữ liệu thử, chẳng hạn `SYNTHETIC-A-<run-id>`. Không dùng dữ liệu khách hàng thật hoặc bí mật đang có hiệu lực để thử khả năng rò rỉ.

Cần biết A-EDITOR thực sự thao tác được DOC-A và B-EDITOR thực sự thao tác được DOC-B. Nếu cả hai tài khoản đều không hoạt động, việc từ chối truy cập chéo tenant chưa chứng minh kiểm soát tenant đúng.

### 4.2. Các yêu cầu nguồn minh họa

Các hợp đồng và giá trị sau chỉ áp dụng cho ví dụ:

| ID yêu cầu | Hành vi bắt buộc |
| --- | --- |
| SEC-AUTH-01 | Các API tài liệu riêng chỉ xử lý nghiệp vụ sau khi xác thực phiên hợp lệ; phiên thiếu hoặc không hợp lệ bị từ chối |
| SEC-AUTHZ-01 | Mỗi thao tác kiểm tra tenant, tài liệu và quyền hành động ở phía máy chủ |
| SEC-EXPORT-01 | Người không có quyền xuất không được tạo công việc xuất hoặc tệp xuất |
| SEC-JOB-01 | Worker phải kiểm tra lại quyền xuất hiện hành của người khởi tạo trước khi tạo nội dung xuất |
| SEC-DATA-01 | Phản hồi và nguồn log trong phạm vi không làm lộ nội dung tài liệu hoặc bí mật bị cấm cho tình huống bị từ chối |
| SEC-AUD-01 | Các lần từ chối có sự kiện audit liên kết được với lần gọi và không ghi token hoặc nội dung tài liệu |
| SEC-FAIL-01 | Nếu không xác định được quyền do dịch vụ quyền lỗi, yêu cầu xuất mới bị từ chối và không tạo công việc |

Trong ví dụ này, hợp đồng API chọn:

- `401` cho trường hợp thiếu hoặc không có phiên hợp lệ.
- `403` cho người được biết tài liệu nhưng không có quyền thực hiện hành động.
- `404` cho tài liệu không tồn tại hoặc người gọi không được biết tài liệu đó tồn tại.
- `503` khi yêu cầu xuất không thể kiểm tra quyền do phụ thuộc lỗi.

Các mã này là một phần hợp đồng minh họa. Chỉ kiểm tra mã mà bỏ qua nội dung, trạng thái và tác dụng phụ vẫn không đủ.

### 4.3. Ma trận negative test

| ID test | Điều kiện bị vi phạm | Thao tác | Kết quả chính | Kiểm tra bổ sung |
| --- | --- | --- | --- | --- |
| NEG-AUTH-01 | Không có phiên | Đọc DOC-A | 401 theo hợp đồng | Không có nội dung; không tiếp tục xử lý dữ liệu được bảo vệ |
| NEG-AUTH-02 | Phiên hết hạn | Tạo bản xuất DOC-A | 401 | Không tạo công việc hoặc tệp |
| NEG-AZ-01 | Sai tenant | B-EDITOR đọc DOC-A | 404 | Không có marker DOC-A hoặc metadata bị cấm |
| NEG-AZ-02 | Đúng tenant nhưng không được cấp quyền | A-NO-GRANT đọc DOC-A | 404 | Không suy ra quyền chỉ từ tenant |
| NEG-AZ-03 | Có quyền đọc nhưng thiếu quyền sửa | A-READER sửa DOC-A | 403 | Phiên bản và nội dung không thay đổi |
| NEG-EXP-01 | Có quyền đọc nhưng thiếu quyền xuất | A-READER tạo bản xuất DOC-A | 403 | Không tạo job, tệp hoặc lời gọi xuất bên ngoài |
| NEG-JOB-01 | Quyền bị thu hồi trước khi worker thực thi | Xử lý job đã được nhận hợp lệ | Job kết thúc ở trạng thái hủy do quyền theo hợp đồng | Không tạo nội dung xuất |
| NEG-FAIL-01 | Không thể xác định quyền | A-EDITOR tạo bản xuất khi dịch vụ quyền lỗi | 503 | Không tự cho phép, không tạo job |
| NEG-DATA-01 | Yêu cầu bị từ chối có dữ liệu thử nhạy cảm | Thực hiện các tình huống liên quan | Phản hồi đúng hợp đồng | Không có marker bị cấm trong nguồn phản hồi hoặc log đã xác định |

Ma trận là bản đồ phạm vi, không phải bằng chứng các test đã chạy. Mỗi dòng còn cần dữ liệu, thao tác thực thi, assertion và kết quả của một lần chạy cụ thể.

## 5. Xây dựng một negative test có thể tin cậy

### Bước 1: Cố định điều kiện hợp lệ còn lại

Với test sai tenant, dùng phiên hợp lệ, request đúng lược đồ, endpoint tồn tại và đối tượng đã được tạo thành công. Chỉ thay đổi quan hệ quyền cần kiểm tra.

Nếu request vừa sai quyền vừa sai định dạng, API có thể dừng ở bước kiểm tra dữ liệu. Kết quả đó không chứng minh điểm kiểm tra quyền đã được thực thi.

Sau các test cô lập, có thể bổ sung test nhiều điều kiện kết hợp để đánh giá thứ tự xử lý và khả năng rò rỉ. Cần ghi rõ mục tiêu của từng loại.

### Bước 2: Chạy positive control phù hợp

Positive control là trường hợp được phép dùng để xác nhận rằng bối cảnh thử hoạt động đúng.

Ví dụ:

- A-EDITOR đọc được DOC-A.
- B-EDITOR đọc được DOC-B.
- A-READER đọc được DOC-A nhưng không được xuất.
- Hệ thống quan sát có thể nhận một sự kiện hoặc job thử đã biết.

Không nhất thiết lặp lại mọi positive control trước từng test nếu fixture đã được xác nhận trong cùng phạm vi. Tuy nhiên, test không được phụ thuộc vào giả định chưa kiểm tra rằng tài khoản, dữ liệu và đường gọi đang hoạt động.

### Bước 3: Chụp trạng thái liên quan trước thao tác

Chỉ lấy các trạng thái cần đối chiếu:

- Phiên bản và nội dung của tài liệu đích.
- Bản ghi job gắn với run ID hoặc correlation ID.
- Tệp xuất và lời gọi tới phụ thuộc mô phỏng.
- Các dữ liệu nghiệp vụ mà thao tác không được phép thay đổi.

Không so sánh toàn bộ cơ sở dữ liệu nếu nó có hoạt động hợp lệ khác. Counter giới hạn tần suất, sự kiện audit hoặc telemetry có thể được phép thay đổi khi một yêu cầu bị từ chối.

Cần phân biệt tác dụng phụ nghiệp vụ bị cấm với dấu vết bảo vệ được yêu cầu.

### Bước 4: Gửi yêu cầu và kiểm tra phản hồi

Kiểm tra kết quả theo hợp đồng, cấu trúc phản hồi và trường dữ liệu. Tránh assertion chỉ dựa trên một từ như “error” trong body.

Nếu yêu cầu trả về HTML đăng nhập do một proxy chuyển hướng, trong khi test định kiểm tra API phân quyền, phải xác định đó có thực sự là đường xử lý cần thử không.

### Bước 5: Kiểm tra trạng thái và tác dụng phụ

Đối chiếu dữ liệu sau thao tác với trạng thái trước đó, theo đúng phạm vi:

- Nội dung hoặc quyền có bị thay đổi không?
- Job có bị tạo dù phản hồi là lỗi không?
- Worker có nhận công việc không được phép không?
- Có tệp hoặc lời gọi ra ngoài không?
- Có đường tải khác làm lộ dữ liệu sau đó không?

Sử dụng định danh của lần thử để tách kết quả khỏi các hoạt động khác. Không đếm tổng job trong một hệ thống đang chạy rồi suy ra một request cụ thể không tạo job.

### Bước 6: Kiểm tra audit và dữ liệu bị cấm

Đối chiếu actor đã được xác thực hoặc trạng thái chưa xác thực, hành động, đối tượng theo chính sách, kết quả và correlation ID.

Không coi danh tính tự khai trong request là người dùng đã được xác thực. Với request không có phiên hợp lệ, audit cần phản ánh đúng mức tin cậy của thông tin thu được.

Kiểm tra marker tổng hợp trong các nguồn cần quan sát. Không tìm thấy marker chỉ hỗ trợ kết luận trong phạm vi nguồn, thời gian và quy tắc tìm kiếm đã dùng; không tự chứng minh mọi vị trí có thể chứa dữ liệu đều sạch.

### Bước 7: Kết luận theo chất lượng quan sát

Một request bị từ chối vì bộ cân bằng tải lỗi không phải bằng chứng cho phân quyền trên tài liệu. Nếu không quan sát được job hoặc trạng thái dữ liệu cần thiết, phải ghi rằng phép thử chưa đủ cơ sở.

Kết quả nên phân biệt hành vi vi phạm yêu cầu, lỗi bộ thử và thiếu quan sát để việc khắc phục đi đúng nơi.

## 6. Mẫu đặc tả test và mã giả

### 6.1. Mẫu test case có truy vết

```yaml
testId: NEG-EXP-01
requirementIds:
  - SEC-AUTHZ-01
  - SEC-EXPORT-01
  - SEC-DATA-01
  - SEC-AUD-01
risk: "Người chỉ có quyền đọc tạo được bản xuất ngoài quyền được cấp"
preconditions:
  - "A-READER có phiên hợp lệ và đọc được DOC-A"
  - "A-READER không có quyền xuất DOC-A"
  - "Các nguồn dữ liệu và quan sát của lần chạy đã sẵn sàng"
action: "A-READER yêu cầu tạo bản xuất DOC-A"
expectedResponse:
  status: 403
  bodyContract: "Lỗi quyền theo hợp đồng, không có nội dung tài liệu"
forbiddenBusinessEffects:
  - "Tạo công việc xuất cho lần gọi bị từ chối"
  - "Tạo tệp xuất"
  - "Gọi phụ thuộc xuất dữ liệu"
expectedSecurityEffects:
  - "Audit từ chối liên kết với lần gọi"
observationScope:
  - "Phản hồi API"
  - "Kho trạng thái job và bộ chạy nền được kiểm soát"
  - "Kho tệp và phụ thuộc mô phỏng"
  - "Nguồn audit và log được liệt kê"
```

Đặc tả trên chưa phải báo cáo kết quả. Khi thực thi, cần bổ sung phiên bản, môi trường, định danh lần chạy, kết quả từng assertion và các bằng chứng liên quan.

### 6.2. Mã giả kiểm tra cả phản hồi lẫn tác dụng phụ

Đoạn sau mô tả logic bộ thử, không phụ thuộc một thư viện cụ thể:

```text
fixture = createIsolatedFixture(runId)
assert fixture.readerCanReadDocument()
assert fixture.readerCannotExportByDefinedPolicy()
assert observability.isReadyFor(runId)

before = snapshotBusinessState(fixture.document)
invocation = requestExport(
    session = fixture.readerSession,
    document = fixture.document
)

assert invocation.response.status == 403
assert matchesDeniedResponseContract(invocation.response)
assert containsNoProtectedDocumentData(invocation.response)

barrier = waitForObservationBoundary(invocation.traceId)
if not barrier.reached:
    recordInconclusive("Không đủ quan sát về xử lý liên quan")
    stopTest()

after = snapshotBusinessState(fixture.document)
assert after == before
assert noExportJobFor(invocation.traceId)
assert noExportArtifactFor(invocation.traceId)
assert noExternalExportCallFor(invocation.traceId)

audit = findAuditFor(invocation.traceId)
assert audit.action == "EXPORT_DOCUMENT"
assert audit.outcome == "DENIED"
assert audit.actor == fixture.readerIdentity
assert audit.document == fixture.document.id

assert noForbiddenMarkerInScopedLogs(invocation.traceId)
recordResultAndEvidence()
```

Các thao tác `assert` phải làm test không đạt khi điều kiện không đúng. Không dùng cơ chế assertion có thể bị tắt trong cấu hình chạy thực tế của bộ thử mà không có kiểm soát.

Mốc quan sát `waitForObservationBoundary` phải được thiết kế theo hệ thống. Ví dụ, bộ thử có thể điều khiển worker và theo dõi các công việc liên quan đến trace cho đến khi hoàn tất. Việc thấy hàng đợi trống ở một thời điểm chưa đủ nếu tác vụ tạo message vẫn đang chạy ở nơi khác.

Nếu chưa có cách xác định mốc quan sát tin cậy, cần bổ sung công cụ quan sát hoặc giới hạn rõ kết luận. Không thay vấn đề đó bằng một khoảng sleep tùy ý rồi khẳng định “không có tác dụng phụ”.

## 7. Kiểm thử khi quyền thay đổi trong xử lý bất đồng bộ

### 7.1. Vì sao chỉ thử API đầu vào chưa đủ?

Một yêu cầu có thể hợp lệ lúc được nhận nhưng không còn hợp lệ lúc worker sử dụng dữ liệu. SEC-JOB-01 trong ví dụ yêu cầu kiểm tra lại quyền trước khi tạo nội dung xuất.

Kịch bản:

1. A-EDITOR yêu cầu xuất DOC-A và API chấp nhận.
2. Job chưa đến điểm kiểm tra quyền của worker.
3. Quyền xuất của A-EDITOR bị thu hồi.
4. Worker tiếp tục thực thi.
5. Worker phải hủy job theo hợp đồng, không tạo nội dung xuất.

Phản hồi chấp nhận ở bước 1 không phải lỗi: khi đó người dùng vẫn có quyền. Kết quả negative test cần đánh giá hành vi tại bước 4 và 5.

### 7.2. Điều khiển thứ tự bằng điểm đồng bộ

Để kiểm thử ổn định:

- Tạo fixture và xác nhận quyền xuất ban đầu.
- Dùng cơ chế của bộ thử để giữ worker trước điểm kiểm tra quyền.
- Gửi yêu cầu và lưu job ID.
- Thu hồi quyền ở nguồn có thẩm quyền, xác nhận thay đổi đã có hiệu lực theo yêu cầu.
- Cho worker chạy tiếp.
- Chờ trạng thái cuối của đúng job.
- Kiểm tra không có nội dung xuất hoặc lời gọi tạo bản xuất bên ngoài.
- Đối chiếu sự kiện hủy với người khởi tạo và tài liệu.

Một trạng thái cuối minh họa là `CANCELLED_AUTHORIZATION`. Tên và ý nghĩa chính thức phải nằm trong hợp đồng job của hệ thống.

Không điều khiển thứ tự chỉ bằng “đợi một chút rồi thu hồi quyền”. Cách đó có thể để worker xử lý xong trước khi quyền đổi, khiến test không thử đúng tình huống.

Nếu thời hạn chờ của bộ thử kết thúc mà job chưa có trạng thái cuối, không được kết luận không tạo tệp là đạt. Có thể job chỉ chưa chạy. Cần phân biệt timeout kỹ thuật của bộ thử với vi phạm một ngưỡng thời gian xử lý đã được yêu cầu rõ ràng.

### 7.3. Ranh giới của kết luận

Test trên không chứng minh việc hủy một luồng tải đã bắt đầu hoặc xóa được bản sao người dùng đã tải hợp lệ trước đó.

Nếu sản phẩm có liên kết tải được cấp trước, worker khác hoặc đường truy cập trực tiếp vào kho tệp, cần yêu cầu và test riêng cho các đường đó. Phạm vi phải đi theo kiến trúc thực tế.

Nếu yêu cầu thu hồi cho phép một khoảng trễ, cần chốt mốc bắt đầu, thao tác thuộc phạm vi và thời hạn. Kết quả sát ngưỡng phải được đánh giá cùng sai số phép đo.

## 8. Các nhóm negative security test cần cân nhắc

### 8.1. Xác thực và vòng đời phiên

Tùy thiết kế, có thể kiểm tra:

- Không có phiên hoặc thông tin xác thực không hợp lệ.
- Phiên hết hạn hoặc đã bị thu hồi.
- Thông tin xác thực bị thay đổi.
- Thông tin được cấp cho mục đích hoặc dịch vụ khác bị dùng sai phạm vi.
- Chưa hoàn thành bước xác thực bổ sung nhưng thực hiện hành động yêu cầu bước đó.

Nếu hệ thống dùng token có chữ ký, thử token bị sửa cần kiểm chứng việc không chấp nhận nội dung đó. Tuy nhiên, không giả định mọi hệ thống đều dùng cùng định dạng token hoặc cùng cơ chế thu hồi.

Bộ thử cần kiểm soát thời gian và nguồn tạo fixture phù hợp. Test dùng một token “sắp hết hạn” theo thời gian thực rất dễ thất thường và khó giải thích.

### 8.2. Phân quyền theo hành động và đối tượng

Các tổ hợp quan trọng thường gồm:

- Đúng tenant nhưng sai quyền hành động.
- Đúng vai trò nhưng không được cấp quyền trên tài liệu cụ thể.
- Sai tenant dù vai trò có cùng tên.
- Quyền trước đây hợp lệ nhưng hiện đã bị thu hồi.
- Cùng đối tượng được truy cập qua endpoint hoặc đường tải khác.
- Danh tính dịch vụ có phạm vi khác với người khởi tạo.

Chỉ kiểm tra nút bị ẩn trên giao diện không chứng minh API từ chối. Cũng không nên mặc định mọi người cùng tenant được xem mọi đối tượng nếu chính sách còn có quyền trên tài liệu.

### 8.3. Bảo vệ dữ liệu và phản hồi lỗi

Kiểm tra các nơi có thể chứa dữ liệu dù thao tác bị từ chối:

- Body, header và metadata của phản hồi.
- Thông báo lỗi hoặc chi tiết chẩn đoán được trả ra ngoài.
- Tệp tạm hoặc bản xuất sinh ra trước khi kiểm tra quyền.
- Log ứng dụng, log tích hợp và audit trong phạm vi.
- Phản hồi của đường truy cập thay thế.

Cần tách dữ liệu được phép xuất hiện trong audit hạn chế quyền với dữ liệu được phép trả cho người gọi. Một định danh đối tượng có thể cần cho điều tra nội bộ nhưng không được tiết lộ cho một người không có quyền biết nó tồn tại.

Với hợp đồng che giấu sự tồn tại, so sánh mã và cấu trúc phản hồi giữa đối tượng không tồn tại và đối tượng không được phép biết. Điều này chưa chứng minh không có rò rỉ qua thời gian, kích thước hoặc kênh khác; nếu các kênh đó nằm trong rủi ro cần xử lý, phải có kiểm chứng phù hợp riêng.

### 8.4. Logging và audit

Negative test cần kiểm chứng cả việc có dấu vết cần thiết lẫn việc không ghi dữ liệu bị cấm.

Nếu không có sự kiện audit, có thể là:

- Ứng dụng chưa phát sự kiện.
- Đường chuyển tiếp lỗi.
- Truy vấn sai nguồn hoặc sai khoảng thời gian.
- Bộ thử chưa chờ đến mốc quan sát đúng.
- Correlation ID không được truyền đủ.

Cần phân tích nguyên nhân và ghi kết quả phù hợp. Không coi “không tìm thấy log” là bằng chứng không có hành vi.

### 8.5. Lỗi phụ thuộc và điều kiện suy giảm

Với một thao tác yêu cầu xác định quyền trước khi tạo job, thử các tình huống như timeout và lỗi dịch vụ quyền bằng phụ thuộc mô phỏng hoặc cơ chế điều khiển trong môi trường thử.

Oracle cần xác định:

- Có được dùng bản sao quyền không?
- Bản sao được coi là hợp lệ trong bao lâu?
- Khi nào thao tác phải bị từ chối?
- Có được tạo công việc chờ xác minh hay không?
- Người dùng và hệ thống audit nhận trạng thái nào?

Trong ví dụ SEC-FAIL-01, chính sách đã chọn là từ chối xuất mới và không tạo job. Test không được áp dụng kết luận đó một cách máy móc cho mọi chức năng khác của sản phẩm.

### 8.6. Phục hồi và trạng thái không còn đáng tin cậy

Nếu hệ thống có yêu cầu không khôi phục lại quyền đã thu hồi, một negative test có thể dùng dữ liệu phục hồi cũ và kiểm tra hệ thống không mở đường nhạy cảm trước khi đối soát quyền.

Điều kiện cần là đã xác định nguồn quyền có thẩm quyền sau phục hồi và quy trình đối soát. Nếu nguồn đó chưa rõ, vấn đề nằm ở đặc tả hoặc thiết kế; không tự đặt một kết quả mong đợi không có cơ sở.

Tương tự, nếu yêu cầu chỉ cho phục hồi từ bản sao được kiểm tra tính toàn vẹn, dùng bản sao thử bị thay đổi để kiểm tra quy trình không âm thầm sử dụng nó. Chỉ thực hiện trên bản sao và môi trường dành cho kiểm thử.

## 9. Phân loại kết quả để tránh kết luận sai

Một bộ thử có thể dùng quy ước sau:

| Kết quả | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| PASS | Các assertion bắt buộc đã được quan sát và đạt | Request bị từ chối đúng, không có tác dụng phụ bị cấm và có audit |
| FAIL | Có quan sát cho thấy yêu cầu hoặc hợp đồng không được đáp ứng | Trả 403 nhưng vẫn tạo job xuất |
| ERROR | Bộ thử hoặc hạ tầng gặp lỗi khiến phép thử không thực hiện đúng | Không tạo được fixture hoặc phụ thuộc mô phỏng không khởi động |
| INCONCLUSIVE | Phép thử đã diễn ra nhưng thiếu cơ sở để kết luận | Không xác định được mốc quan sát trạng thái nền |
| SKIPPED | Test không được thực thi và có lý do được ghi nhận | Tính năng chưa nằm trong môi trường thử của lần chạy |

Đây là quy ước minh họa. Công cụ có thể dùng tên khác, nhưng cần giữ được sự khác biệt về ý nghĩa.

Một số trường hợp dễ nhầm:

| Quan sát | Cách đánh giá |
| --- | --- |
| Mong đợi 403 nhưng nhận 500 | Chưa đáp ứng hợp đồng; cần xác định lỗi sản phẩm hay lỗi môi trường, không tự coi là từ chối an toàn |
| Nhận 403 nhưng tài liệu đã đổi | FAIL vì trạng thái bị thay đổi trái phép |
| Nhận 401 do token fixture bị hết hạn, trong test định kiểm tra sai tenant | Test chưa kiểm chứng điều kiện sai tenant như dự định |
| Job vẫn đang chờ, chưa có tệp | Chưa chứng minh worker từ chối |
| Test bị bỏ qua nhưng pipeline vẫn xanh | Chưa có bằng chứng cho yêu cầu mà test đó bao phủ |
| Hai tài khoản đều không gọi được API vì endpoint sai | Chưa chứng minh kiểm soát quyền |
| Nhận đúng lỗi nhưng body chứa nội dung tài liệu | FAIL vì rò rỉ dữ liệu |

Không phải mọi FAIL đều là một lỗ hổng có thể khai thác. Ví dụ, mã lỗi không đúng hợp đồng có thể là lỗi tương thích. Cần phân tích tác động bảo mật, nhưng vẫn phải phản ánh chính xác kết quả kiểm chứng.

## 10. Bằng chứng và khả năng tái hiện

Mỗi kết quả nên gắn với:

- Requirement ID và test ID.
- Build hoặc phiên bản artifact thực sự được thử.
- Phiên bản cấu hình và bộ kiểm thử liên quan.
- Môi trường, nguồn quyền và trạng thái phụ thuộc.
- Run ID, fixture ID, correlation ID hoặc job ID cần thiết.
- Điều kiện ban đầu và thao tác đã thực hiện.
- Kết quả mong đợi, kết quả thực tế và từng assertion.
- Khoảng thời gian, nguồn quan sát và giới hạn.
- Phát hiện liên quan và kết quả thử lại sau khắc phục.

Chỉ lưu thông tin cần thiết, không lưu password hoặc token thật vào báo cáo để “dễ tái hiện”. Có thể lưu tham chiếu fixture và cách tạo lại phiên thử.

Khi sửa lỗi, giữ liên kết với lần thất bại và chạy lại các tình huống bị ảnh hưởng. Một lần chạy đạt mới không xóa lịch sử rằng phiên bản trước đã vi phạm yêu cầu.

Số lượng negative test hoặc tỷ lệ code coverage không tự cho biết đã bao phủ mọi ranh giới quyền. Cần kiểm tra ma trận danh tính, hành động, tài nguyên, trạng thái và đường truy cập theo rủi ro.

## 11. Tổ chức trong CI/CD

Có thể chia test theo lớp:

| Lớp | Nội dung phù hợp | Giới hạn |
| --- | --- | --- |
| Logic hoặc đơn vị | Quy tắc quyền, chuyển trạng thái, điều kiện phải giữ | Chưa chứng minh middleware, truy vấn dữ liệu và tích hợp đúng |
| Tích hợp | API với kho quyền, cơ sở dữ liệu, queue và phụ thuộc mô phỏng | Cần quản lý fixture, đồng bộ và trạng thái phụ thuộc |
| Toàn luồng có chọn lọc | Đường tạo, xử lý và tải bản xuất trên môi trường đại diện | Chi phí lớn hơn và phải giải thích khác biệt với môi trường đích |
| Diễn tập lỗi hoặc phục hồi | Thu hồi quyền khi phụ thuộc lỗi, phục hồi dữ liệu cũ | Cần môi trường và khả năng quan sát phù hợp |

Chạy sớm các test ổn định có giá trị cao, rồi bổ sung lớp kiểm chứng phản ánh các ranh giới quan trọng. Không dùng test logic riêng lẻ thay cho mọi kiểm tra tích hợp.

Để giữ bộ thử đáng tin cậy:

- Cô lập tenant, dữ liệu và danh tính thử theo lần chạy.
- Dùng thời gian hoặc điểm đồng bộ có thể kiểm soát khi cần.
- Không để test này phụ thuộc kết quả còn sót của test trước.
- Giữ thông tin đủ để phân biệt lỗi sản phẩm và lỗi bộ thử.
- Không tự động thử lại nhiều lần đến khi xanh rồi bỏ kết quả trước đó.
- Nếu tạm bỏ một test thất thường, ghi yêu cầu đang thiếu bằng chứng, người xử lý và điều kiện đưa test trở lại.

Test phải đi qua đúng lớp kiểm soát cần đánh giá. Một phản hồi từ chối ở cổng ngoài có thể chứng minh chính sách của cổng đó, nhưng chưa chắc kiểm chứng việc phân quyền đối tượng ở backend. Phạm vi và kỳ vọng phải được định nghĩa cho từng lớp.

## 12. Những sai lầm thường gặp

| Sai lầm | Hệ quả | Cách sửa |
| --- | --- | --- |
| Chỉ assert mã lỗi | Bỏ qua dữ liệu hoặc tác dụng phụ trái phép | Kiểm tra body, trạng thái, job, tệp và phụ thuộc liên quan |
| Dùng request không hợp lệ để thử phân quyền | Request bị chặn trước điểm cần thử | Giữ đúng lược đồ và thay điều kiện quyền có chủ đích |
| Không có positive control | Không biết fixture hoặc đường gọi có hoạt động không | Xác nhận trường hợp hợp lệ cùng phạm vi |
| Chỉ đổi vai trò, không đổi tenant hoặc đối tượng | Bỏ sót quyền trên tài nguyên | Lập ma trận theo nhiều chiều |
| Dùng sleep cố định cho worker | Test thất thường hoặc kết luận quá sớm | Dùng điểm đồng bộ và mốc quan sát đáng tin cậy |
| Coi không có tệp tức là worker đã từ chối | Có thể worker chưa chạy | Chờ và kiểm tra trạng thái cuối đúng job |
| Chỉ thử giao diện | Bỏ qua API trực tiếp hoặc đường tải khác | Đi theo các điểm vào thực tế của kiến trúc |
| Tìm marker trong một log rồi kết luận không rò rỉ | Kết luận vượt nguồn quan sát | Liệt kê nguồn và giữ giới hạn |
| Chạy lại đến khi xanh | Che điều kiện cạnh tranh hoặc mất quan sát | Giữ lịch sử và phân tích nguyên nhân |
| Coi test chưa chạy là đạt | Tạo cảm giác đã kiểm chứng | Tách SKIPPED, ERROR và thiếu bằng chứng khỏi PASS |
| Dùng dữ liệu hoặc bí mật thật trong fixture | Tăng rủi ro cho chính bộ thử | Dùng dữ liệu tổng hợp và tham chiếu an toàn |
| Có nhiều test nhưng không gắn yêu cầu | Không biết mục tiêu nào được bảo vệ | Truy vết từ yêu cầu và rủi ro đến assertion |

## 13. Checklist trước khi công nhận negative security test đạt

- [ ] Có yêu cầu nguồn và hành vi bị cấm được xác định rõ.
- [ ] Điều kiện hợp lệ còn lại và fixture đã được kiểm tra.
- [ ] Positive control xác nhận đường hợp lệ hoạt động.
- [ ] Dữ liệu thử tổng hợp và phạm vi cô lập phù hợp.
- [ ] Request thực sự đi tới lớp kiểm soát cần đánh giá.
- [ ] Kết quả mong đợi xuất phát từ hợp đồng đã chốt.
- [ ] Assertion bao gồm phản hồi và dữ liệu không được tiết lộ.
- [ ] Trạng thái nghiệp vụ và tác dụng phụ liên quan được đối chiếu.
- [ ] Xử lý nền có điểm đồng bộ và mốc quan sát đáng tin cậy.
- [ ] Audit cần thiết được kiểm tra cùng các trường dữ liệu bị cấm.
- [ ] Lỗi môi trường, thiếu quan sát và test bị bỏ qua không bị tính là PASS.
- [ ] Phiên bản, môi trường, định danh và giới hạn được lưu trong bằng chứng.
- [ ] Các đường chưa bao phủ được ghi nhận thay vì suy rộng kết luận.
