# Privacy control evidence — Bằng chứng cho kiểm soát quyền riêng tư

## 1. Mục tiêu và phạm vi

Một hệ thống có thể công bố rằng dữ liệu khách hàng chỉ được dùng đúng mục đích, chỉ người có quyền mới được xuất dữ liệu và yêu cầu xóa sẽ được xử lý. Để đánh giá những khẳng định đó, cần bằng chứng cho thấy kiểm soát đã được thiết kế, triển khai và vận hành trong phạm vi cụ thể.

**Privacy control evidence** là bằng chứng có thể kiểm tra về cách hệ thống giới hạn việc thu thập, truy cập, sử dụng, chia sẻ, lưu giữ và xử lý dữ liệu cá nhân theo chính sách áp dụng. Bằng chứng phải nối được một yêu cầu bảo vệ với quyết định và hiệu lực thực tế; việc có tài liệu chính sách hoặc nút “xóa” trên giao diện chưa đủ.

Bài học thuộc chương Compliance của module SECURITY_APPLICATION_SECURITY_BUSINESS_LOGIC_SECURITY. Trọng tâm là quyền riêng tư trong logic nghiệp vụ: quyền theo đối tượng và trường dữ liệu, mục đích sử dụng, state machine, transaction, idempotency và các đường xử lý có thể bị lạm dụng như export, replay, sửa tham chiếu hoặc bỏ qua phê duyệt.

Bài học sử dụng chính sách nội bộ giả định để minh họa cách tạo bằng chứng kỹ thuật. Yêu cầu áp dụng cho từng tổ chức phải được xác định riêng; một kết quả test hoặc bộ bằng chứng kỹ thuật không tự xác nhận mọi nghĩa vụ tuân thủ.

Sau bài học, bạn có thể:

- Chuyển yêu cầu quyền riêng tư thành bất biến và tuyên bố có thể kiểm chứng.
- Phân biệt bằng chứng thiết kế, cấu hình triển khai, thực thi và đánh giá hiệu quả.
- Thu thập bằng chứng cho luồng đồng bộ và bất đồng bộ mà không tạo thêm rò rỉ.
- Kiểm thử export, thay đổi quyền, yêu cầu lặp và vòng đời dữ liệu.
- Đóng gói kết quả có nguồn gốc, phạm vi, thời gian và giới hạn kết luận rõ ràng.

## 2. Từ yêu cầu quyền riêng tư đến bất biến nghiệp vụ

“Dữ liệu được bảo vệ” quá rộng để làm một kết luận kiểm tra. Cần phân rã thành các điều kiện xác định theo chủ thể, hành động, tài nguyên, trường dữ liệu, mục đích và thời điểm.

| Mã ví dụ | Bất biến | Dấu hiệu cần bằng chứng |
| --- | --- | --- |
| PRIV-01 | Chỉ chủ thể có quyền mới tác động tới đúng đối tượng và phạm vi tổ chức | Quyết định quyền khớp tài nguyên thực sự được đọc, sửa hoặc xuất |
| PRIV-02 | Tập trường được trả về nằm trong phạm vi được phép cho thao tác và mục đích | Artifact và response thực tế không chứa trường ngoài chính sách |
| PRIV-03 | Job và đường tải dữ liệu tuân thủ chính sách quyền ở các thời điểm được quy định | Thay đổi quyền, ticket hoặc phạm vi không bị đường nền bỏ qua |
| PRIV-04 | Thay đổi lựa chọn sử dụng dữ liệu được cấp quyền và áp dụng đúng trạng thái | Không giả mạo chủ thể, đảo trạng thái bằng replay hoặc bỏ qua bước xác nhận |
| PRIV-05 | Dữ liệu hết hạn hoặc thuộc yêu cầu xử lý được đi qua đúng vòng đời | Không coi xóa ở bảng chính là hoàn tất mọi bản sao và mọi đích |
| PRIV-06 | Bằng chứng đủ truy nguyên nhưng không chứa dữ liệu vượt nhu cầu điều tra | Có quyết định, hiệu lực và tham chiếu cần thiết mà không ghi bí mật hoặc payload đầy đủ |

Các mã chỉ là quy ước trong bài. Không áp chúng như yêu cầu pháp lý phổ quát.

Một số thuộc tính cần phân biệt:

- **Mục đích được khai báo:** chuỗi do người gọi gửi, chẳng hạn “hỗ trợ khách hàng”.
- **Căn cứ được hệ thống chấp nhận:** ticket, quan hệ với đối tượng, quyền được cấp hoặc phê duyệt theo chính sách.
- **Quyền thực sự được thực thi:** dữ liệu mà truy vấn, worker và đường tải đã cho phép sử dụng.
- **Hiệu lực quan sát được:** trường và đối tượng thực sự có trong kết quả hoặc đã bị thay đổi.

Nếu client chỉ cần tự gán purpose là “support” để đọc dữ liệu rộng hơn, hệ thống chưa chứng minh được ràng buộc mục đích. Tương tự, mã hóa đường truyền không chứng minh người nhận có quyền nhận dữ liệu đó.

## 3. Phân biệt các lớp bằng chứng

Một kiểm soát thường cần nhiều lớp bằng chứng bổ trợ nhau:

| Lớp | Ví dụ | Điều có thể kết luận | Giới hạn |
| --- | --- | --- | --- |
| Thiết kế | Quy tắc export, mô hình quyền và sơ đồ luồng dữ liệu | Kiểm soát được dự định hoạt động thế nào | Chưa chứng minh code hoặc cấu hình thực tế làm đúng |
| Triển khai | Revision code, cấu hình quyền, bộ trường được phép | Một phiên bản có cơ chế liên quan | Chưa chứng minh phiên bản đó đang chạy ở đích cần đánh giá |
| Triển khai vào môi trường | Build, cấu hình hiệu lực, thời điểm rollout | Kiểm soát nào được đưa vào môi trường nào | Chưa chứng minh mọi thao tác đều đi qua kiểm soát |
| Vận hành | Quyết định quyền, trạng thái job, dấu vết tải và xử lý dữ liệu | Một hoạt động được ghi nhận trong thời gian cụ thể | Chưa bảo đảm log đầy đủ hoặc phản ánh đúng hiệu lực |
| Hiệu quả | Test đối kháng, kiểm tra artifact, đối soát và rà soát mẫu | Kiểm soát giữ được điều kiện trong kịch bản đã đánh giá | Không tự mở rộng sang mọi kênh, mọi thời điểm |

Ảnh chụp màn hình có thể hỗ trợ nhận diện cấu hình nhưng không thay bằng chứng từ API, worker, storage hoặc artifact thực tế. Một test bị mock toàn bộ tầng phân quyền cũng không chứng minh cấu hình production đang thực thi đúng.

Kết luận nên có dạng: “Build B, cấu hình C, trong môi trường E và khoảng thời gian T, các kịch bản S cho thấy tập trường và phạm vi export tuân thủ policy P.” Tránh nâng kết luận thành “toàn hệ thống luôn bảo vệ quyền riêng tư” khi phạm vi quan sát không đủ.

## 4. Lập bản đồ dữ liệu và các đường tạo hiệu lực

Muốn chứng minh một kiểm soát có hiệu lực, trước hết cần biết các đường có thể đọc, sao chép hoặc thay đổi cùng loại dữ liệu.

Với dữ liệu khách hàng, phạm vi có thể gồm:

- API chi tiết và danh sách, tìm kiếm, lọc và báo cáo.
- Worker export, file tạm, object storage và đường download.
- Cache, chỉ mục tìm kiếm, hệ thống phân tích và bản sao phục vụ đọc.
- Message broker, retry queue, dead-letter queue và công cụ phát lại.
- Log ứng dụng, trace, cảnh báo, công cụ hỗ trợ và bản sao điều tra.
- Công cụ quản trị, tài khoản dịch vụ, tích hợp nhận dữ liệu.
- Snapshot, backup và đường phục hồi dữ liệu.

Không phải mọi đích có cùng vai trò hoặc cùng thời hạn xử lý. Bản đồ cần nói rõ dữ liệu nào tới đâu, ai có quyền, vì mục đích gì và kiểm soát nào chịu trách nhiệm ở từng ranh giới.

Một ma trận kiểm soát tối thiểu:

| Luồng | Đối tượng và trường | Điểm quyết định | Hiệu lực cần kiểm tra | Nguồn bằng chứng |
| --- | --- | --- | --- | --- |
| Xem hồ sơ | Hồ sơ trong phạm vi được cấp | Quyền theo đối tượng và trường | Response thực tế | Quyết định quyền và bộ kiểm thử response |
| Export | Tập hồ sơ và các cột được phép | Request, worker, publish và download theo policy | Nội dung file và người tải | Trạng thái job, artifact và log truy cập đã giảm dữ liệu |
| Thay lựa chọn sử dụng | Lựa chọn của đúng chủ thể | Xác thực, đại diện hợp lệ và state machine | Phiên bản lựa chọn đã commit | Lịch sử thay đổi và xác nhận downstream |
| Xử lý dữ liệu theo vòng đời | Các bản sao thuộc phạm vi đã xác định | Lịch lưu giữ và trạng thái yêu cầu | Hoàn tất hoặc còn tồn đọng ở từng đích | Kết quả tác vụ và đối soát |

Nếu chỉ kiểm tra endpoint chính nhưng worker dùng truy vấn rộng hơn, bằng chứng chưa bao phủ luồng nghiệp vụ. Việc thống kê đầy đủ các đường liên quan là một phần của kết luận về độ bao phủ.

## 5. Chất lượng của bằng chứng

### 5.1. Nguồn gốc và tính toàn vẹn

Mỗi bằng chứng cần truy được hệ thống tạo, môi trường, phiên bản, thời điểm thu thập và thao tác liên quan. Người thu thập cũng cần có quyền phù hợp; không thu thêm dữ liệu chỉ vì công cụ có thể đọc được.

Có thể dùng digest, chữ ký, lịch sử thay đổi hoặc kho có giới hạn quyền sửa để hỗ trợ phát hiện thay đổi. Digest khớp chỉ cho thấy nội dung khớp với digest đang tin cậy; nó không chứng minh dữ liệu ban đầu đúng, bộ thu thập đầy đủ hay kiểm soát nghiệp vụ có hiệu quả.

Một chuỗi hash cũng không tự chứng minh không thiếu phần đầu, phần cuối hoặc cả một kênh dữ liệu. Cần điểm neo, phạm vi dự kiến và kiểm tra tính đầy đủ phù hợp thiết kế.

### 5.2. Thời gian, phiên bản và tính nhất quán

Bằng chứng phải nói nó đại diện cho thời điểm nào. Quyền hiện tại không đủ để đánh giá thao tác cũ; ngược lại, quyền tại lúc tạo export chưa chắc đủ cho phép tải file sau khi bị thu hồi.

Khi đọc nhiều bảng, cần cách quan sát nhất quán theo câu hỏi. Ghép quyền ở T1 với trạng thái job ở T2 có thể tạo tổ hợp chưa từng tồn tại. Với nhiều hệ thống không có transaction chung, ghi mốc chốt, độ trễ và phần trạng thái chưa rõ thay vì gọi mọi lần đọc là snapshot nhất quán.

### 5.3. Đầy đủ trong phạm vi đã tuyên bố

Một log không ghi nhận truy cập bị từ chối không thể dùng để đếm toàn bộ nỗ lực vượt quyền. Một test không chạm đường download không chứng minh file không bị tải trái phép.

Bộ bằng chứng cần nêu rõ:

1. Những kênh và loại thao tác đã kiểm tra.
2. Khoảng thời gian và môi trường đại diện.
3. Phần dữ liệu toàn bộ hay mẫu được chọn.
4. Các nguồn bị thiếu hoặc thu thập lỗi.
5. Ngoại lệ được phê duyệt và công việc còn tồn đọng.

Không tìm thấy bản ghi có thể là không có thao tác, cũng có thể là lỗi thu thập. Kết luận phải phân biệt được hai khả năng này.

## 6. Bằng chứng cho quyết định quyền và mục đích

Một quyết định quyền có ích cần ràng buộc tối thiểu chủ thể đã xác thực, hành động, tài nguyên, phạm vi trường, ngữ cảnh và phiên bản chính sách. Nếu hành động được đại diện hoặc ủy quyền, cần tham chiếu căn cứ tương ứng.

Các trường như tenantId, role, ownerId hoặc purpose trong request không tự có thẩm quyền. Bằng chứng cần chỉ ra hệ thống đã xác minh chúng bằng nguồn nào.

Không chỉ kiểm tra “đã gọi authorization service”. Cần xác nhận:

- Object ID đã kiểm tra là object ID thực sự bị truy cập.
- Phạm vi tenant tới truy vấn và worker không bị thay bằng tham số do người gọi sửa.
- Trường bị hạn chế không quay lại qua serializer, báo cáo hoặc cột phụ.
- Quyết định không được tái sử dụng quá thời hạn hoặc ngoài ngữ cảnh được cấp.
- Cùng quy tắc được áp dụng trên đường API, nền, quản trị và download liên quan.
- Thông báo từ chối không làm lộ nội dung ngoài quyền.

Decision ID giúp nối bằng chứng, nhưng không phải bằng chứng độc lập rằng quyết định cho phép là đúng. Cần đối chiếu với policy, dữ liệu cấp quyền và hiệu lực thực tế.

Quyền riêng tư cũng không chỉ là từ chối người ngoài. Một người có quyền xem một hồ sơ vì xử lý ticket chưa mặc nhiên có quyền xuất toàn bộ hồ sơ của tổ chức hoặc sao chép chúng sang một mục đích khác.

## 7. Ví dụ xuyên suốt: export dữ liệu hỗ trợ khách hàng

### 7.1. Chính sách của ví dụ

Giả sử một ứng dụng nhiều tenant cho phép nhân viên hỗ trợ xuất bản tóm tắt hồ sơ theo ticket. Chính sách P3 của ví dụ quy định:

- Người tạo phải có quyền export trong tenant của ticket đang hoạt động.
- Chỉ hai trường customer_ref và status được xuất; yêu cầu thêm email bị từ chối trước khi tạo job.
- Worker xác minh lại phạm vi và điều kiện ticket trước khi đọc, đồng thời kiểm tra điều kiện được phép trước khi công bố artifact.
- Người tải phải còn quyền tương ứng và ticket vẫn hoạt động tại lúc tải.
- Artifact có thời hạn lưu và không được công khai qua đường storage khác.
- Replay cùng thao tác không tạo thêm artifact hoặc quyền tải ngoài hợp đồng.

Đây là chính sách giả định để có đáp án kiểm thử cụ thể. Hệ thống khác có thể dùng quyền đã cấp cho một khoảng thời gian xác định; khi đó bằng chứng phải phản ánh đúng hợp đồng đó thay vì áp chính sách P3 ngầm.

### 7.2. Bằng chứng tại từng ranh giới

| Ranh giới | Điều cần chứng minh | Bằng chứng có ích |
| --- | --- | --- |
| Nhận yêu cầu | Chủ thể, ticket, tenant và tập trường hợp lệ | Quyết định quyền và trạng thái yêu cầu đã commit |
| Xếp lịch | Job gắn với đúng nội dung đã được cấp quyền | Operation ID, revision yêu cầu, phạm vi và dấu vân tay nội dung |
| Thực thi | Worker không mở rộng phạm vi hoặc bỏ qua thay đổi quyền theo P3 | Quyết định tại lúc chạy, phạm vi truy vấn và trạng thái ticket |
| Công bố file | Artifact tương ứng đúng job và điều kiện công bố | Manifest, tập cột, phạm vi hàng, thời hạn và tham chiếu policy |
| Tải file | Người nhận được phép ở thời điểm tải | Quyết định download, artifact ID, kết quả giao file |
| Hết hạn | File và quyền sử dụng không tồn tại quá hợp đồng | Trạng thái thu hồi, kết quả dọn dữ liệu và đối soát |

Log “job thành công” không chứng minh file chỉ chứa dữ liệu đúng tenant. Cần kiểm tra kết quả thực tế và quan hệ giữa artifact với yêu cầu được cho phép.

Nếu hệ thống dùng URL ký sẵn có tính chất bearer và người giữ URL có thể tải trực tiếp, việc kiểm tra quyền khi cấp URL không tự chứng minh quyền được kiểm tra lại ở mỗi lần tải. Muốn khẳng định thu hồi có hiệu lực tức thời phải có cơ chế thực sự đáp ứng điều đó, chẳng hạn đường tải được kiểm soát hoặc thu hồi khả năng truy cập tương ứng. Nếu chỉ bảo đảm hết hiệu lực sau TTL, bằng chứng và kết luận phải nói rõ cửa sổ đó.

### 7.3. Những đường lạm dụng cần bao phủ

- Thay tenant hoặc ticket ID giữa lúc tạo yêu cầu và lúc worker nhận job.
- Thêm trường không được phép, kể cả qua cấu hình cột phụ hoặc định dạng export khác.
- Tạo job khi có quyền rồi tải sau khi quyền đã bị thu hồi.
- Đọc artifact của người khác bằng cách sửa job ID hoặc artifact ID.
- Gửi lại idempotency key với nội dung hoặc tenant khác.
- Tải qua đường storage trực tiếp để né kiểm soát trên API.
- Phát lại job cũ sau khi ticket đã đóng hoặc artifact đã hết hạn.

Mỗi biến thể cần kết quả mong đợi và bằng chứng ở đúng ranh giới. Từ chối trên giao diện không chứng minh endpoint nền hoặc storage đã từ chối.

## 8. Mẫu bản ghi bằng chứng được giảm dữ liệu

Một bản ghi minh họa cho ca export hợp lệ với dữ liệu tổng hợp:

```json
{
  "evidenceId": "ev-export-test-041",
  "schemaVersion": 1,
  "controlId": "PRIV-EXPORT-SCOPE",
  "controlVersion": "P3",
  "environment": "controlled-integration",
  "deploymentRef": "build-example-27",
  "observedAt": "2026-01-15T09:00:00Z",
  "operationRef": "export-test-op-041",
  "subjectRef": "synthetic-actor-A",
  "resourceScopeRef": "synthetic-tenant-A",
  "purposeDecisionRef": "ticket-policy-decision-12",
  "authorizationDecisionRef": "authz-decision-73",
  "requestRevision": 1,
  "requestedFields": ["customer_ref", "status"],
  "allowedFields": ["customer_ref", "status"],
  "stage": "ARTIFACT_PUBLISHED",
  "outcome": "READY",
  "artifactRef": "synthetic-artifact-041",
  "evidenceRefs": [
    "request-commit-041",
    "worker-decision-041",
    "artifact-inspection-041"
  ]
}
```

Bản ghi chỉ chứa tham chiếu, không nhúng toàn bộ file hoặc dữ liệu khách hàng. Artifact inspection là một bằng chứng riêng có phạm vi và kết quả; việc đặt một chuỗi vào evidenceRefs chưa chứng minh lần kiểm tra đó đã xảy ra.

Các ID trong ví dụ là dữ liệu tổng hợp. Trong hệ thống thật, ID thay thế hoặc giá trị băm vẫn có thể liên kết tới một người qua nguồn khác. Không gọi chúng là dữ liệu vô danh chỉ vì không có tên hoặc email.

Nếu nhiều nguồn dùng chung định dạng bản ghi, danh tính nguồn phải được xác minh ngoài trường tự khai trong payload. Tên môi trường cũng cần gắn với nguồn triển khai đáng tin, tránh dùng kết quả test làm bằng chứng production do gắn nhãn sai.

Một bản ghi evidence cần có schema version và quy tắc diễn giải ổn định. Khi thay đổi ý nghĩa outcome hoặc tập trường, giữ khả năng đọc lại dữ liệu cũ thay vì diễn giải mọi phiên bản theo cấu trúc mới.

## 9. Kiểm thử và thu bằng chứng từ artifact thực tế

### 9.1. Fixture có thể kiểm chứng độc lập

Chuẩn bị hai tenant A và B trong môi trường được kiểm soát:

- A có hai hồ sơ tổng hợp A1, A2; B có B1.
- Mỗi hồ sơ có một giá trị email đánh dấu riêng để nhận ra rò rỉ trường.
- Người hỗ trợ U-A chỉ có quyền với ticket T-A của tenant A.
- Tập trường hợp lệ theo P3 là customer_ref và status.
- Có nguồn thời gian điều khiển được để kiểm tra hết hạn khi phù hợp thiết kế.

Kỳ vọng được xác định trực tiếp từ fixture, không lấy chính hàm lọc production làm đáp án. Nếu test gọi lại hàm đang sai để tính tập hàng mong đợi, cả code và test có thể cùng bỏ lọt dữ liệu.

### 9.2. Ca hợp lệ và ca bị từ chối

```text
fixture = commitSyntheticFixture(A1, A2, B1, U_A, T_A, policy = P3)

validJob = requestExportAs(
    U_A, ticket = T_A, fields = [customer_ref, status]
)
awaitWithDeadline(validJob.reachesTerminalState())
assert validJob.state == READY

artifact = downloadThroughAuthorizedPathAs(U_A, validJob.artifactRef)
parsed = parseActualArtifact(artifact)
assert parsed.columns == [customer_ref, status]
assert set(parsed.customer_ref) == {A1, A2}
assert parsed contains no B1 record
assert rawArtifact contains none of the synthetic email markers

denied = requestExportAs(
    U_A, ticket = T_A, fields = [customer_ref, status, email]
)
assert denied matches the documented rejection contract
assert no export job was accepted for denied.operationRef
```

Đây là giả mã, không phải API của một framework. Test phải đọc file thực tế theo định dạng export, không chỉ nhìn danh sách trường trong metadata. Kiểm tra marker giúp phát hiện nội dung bị chèn ngoài các cột dự kiến, nhưng không thay thế việc parse và so sánh cấu trúc.

Với ca bị từ chối, kiểm tra dấu vết chấp nhận job và artifact trong phạm vi operation của test. Chỉ một mã lỗi trả về không chứng minh worker chưa nhận công việc.

### 9.3. Thay đổi quyền giữa các bước

Theo P3, tạo job lúc U-A có quyền, giữ worker ở điểm điều khiển trước đọc dữ liệu, thu hồi quyền rồi cho worker tiếp tục. Kỳ vọng là không tạo artifact khả dụng trái chính sách; trạng thái cuối và lý do phải phản ánh việc điều kiện không còn hợp lệ.

Làm thêm ca đã có artifact nhưng quyền bị thu hồi trước khi tải. Kiểm tra đường download chính và mọi đường trực tiếp đã được phát hành trong phạm vi hỗ trợ. Không kết luận đã thu hồi chỉ vì nút tải biến mất.

Không có file được công bố chưa tự chứng minh worker chưa đọc dữ liệu ngoài quyền. Nếu cần kết luận về việc truy cập dữ liệu, thu thêm bằng chứng từ lớp truy cập hoặc nguồn kiểm toán phù hợp và xác nhận bộ thu thập đó hoạt động bằng ca đối chứng.

### 9.4. Ma trận kịch bản

| Mã | Kịch bản | Kết quả cần chứng minh |
| --- | --- | --- |
| PE-01 | Export hợp lệ | Đúng tập hàng, cột, người nhận và thời hạn |
| PE-02 | Sửa tenant hoặc ticket | Không tác động hoặc đọc ngoài phạm vi được cấp |
| PE-03 | Thêm trường bị hạn chế | Từ chối theo P3 trước chấp nhận job |
| PE-04 | Thu hồi quyền trước khi worker chạy | Worker không tạo hiệu lực trái chính sách P3 |
| PE-05 | Thu hồi quyền sau tạo file, trước tải | Đường tải thực thi đúng hợp đồng thu hồi |
| PE-06 | Replay cùng operation và nội dung | Không tạo thêm artifact hoặc quyền ngoài hợp đồng |
| PE-07 | Cùng khóa nhưng khác nội dung hoặc phạm vi | Không trả kết quả cũ ngoài quyền, phát hiện xung đột |
| PE-08 | Sửa job ID hoặc artifact ID | Quyền theo đối tượng vẫn được kiểm tra |
| PE-09 | Artifact hết hạn | Không tiếp tục cấp hoặc dùng quyền tải trái hợp đồng |
| PE-10 | Retry sau lỗi hoặc restart | Phục hồi đúng phạm vi, không bỏ qua kiểm soát |
| PE-11 | Lỗi ghi evidence hoặc nguồn quyền | Có kết quả theo chính sách lỗi và dấu vết tồn đọng |
| PE-12 | Yêu cầu xử lý dữ liệu gặp bản sao hoặc backup | Bằng chứng chỉ rõ đích đã xử lý, giới hạn và công việc còn lại |

Các điểm chờ phải có thời hạn, đường giải phóng và cách cô lập công việc còn chạy. Hàng đợi trống chưa chứng minh job, download hoặc tác vụ dọn dữ liệu đã kết thúc.

## 10. Bằng chứng cho thay đổi lựa chọn và xử lý dữ liệu

### 10.1. Thay đổi lựa chọn sử dụng dữ liệu

Nếu hệ thống cho phép thay đổi lựa chọn nhận thông tin hoặc giới hạn sử dụng dữ liệu, cần biết ai được phép thay đổi cho chủ thể nào và hiệu lực bắt đầu khi nào.

Bằng chứng có thể gồm phiên bản trước và sau, chủ thể đã xác thực, căn cứ đại diện nếu có, nguồn thay đổi, thời điểm commit và trạng thái áp dụng ở các đích liên quan.

Không dùng một cờ chung để đại diện cho mọi mục đích nếu chính sách phân biệt chúng. Lựa chọn cho kênh A không mặc nhiên cho phép kênh B. Sự kiện cũ được phát lại cũng không được đảo lựa chọn mới nếu hợp đồng yêu cầu phiên bản mới hơn thắng.

Nếu downstream áp dụng bất đồng bộ, ghi rõ độ trễ được phép, xác nhận đã áp dụng và đường xử lý tồn đọng. Việc API trả thành công chỉ có thể chứng minh yêu cầu hoặc trạng thái nguồn đã được chấp nhận theo hợp đồng, chưa chứng minh mọi bên nhận đã cập nhật.

### 10.2. Yêu cầu xóa hoặc giới hạn dữ liệu

Một state machine minh họa:

```text
RECEIVED -> AUTHORITY_VERIFIED -> SCOPED -> PROCESSING
                                            -> COMPLETED_FOR_DEFINED_SCOPE
                                            -> PARTIALLY_COMPLETED
                                            -> NEEDS_REVIEW
```

Tên trạng thái không thay thế tiêu chí hoàn tất. Cần xác định phạm vi dữ liệu, các đích, yêu cầu giữ lại được phê duyệt, kết quả từng bước và những phần không thể xử lý ngay theo chính sách.

Soft delete, vô hiệu hóa tài khoản và xóa nội dung là các hiệu lực khác nhau. Nếu hệ thống chỉ ẩn bản ghi khỏi API, không ghi bằng chứng như thể mọi bản sao đã bị xóa.

Với cache, chỉ mục và dữ liệu phân tích, cần bằng chứng tác vụ đã áp dụng hoặc đã đối soát theo phạm vi. Với backup, mô tả chính sách vòng đời và đường phục hồi: dữ liệu nào còn ở bản sao, khi nào hết hạn, và cách ngăn dữ liệu bị xử lý trước đó quay lại phục vụ sau restore. Không tuyên bố xóa vật lý tức thời khỏi mọi backup nếu không có cơ chế và bằng chứng tương ứng.

Retry tác vụ xử lý dữ liệu cần idempotency, trạng thái bền vững và phạm vi không đổi ngoài quy trình được cấp quyền. Một bước thất bại không được bị che bằng trạng thái “hoàn tất” toàn bộ.

## 11. Bản thân bằng chứng cũng cần bảo vệ quyền riêng tư

Kho evidence có thể tập trung ID người dùng, lịch sử truy cập, quyết định quyền và tham chiếu dữ liệu nhạy cảm. Nếu thu thập quá mức, công cụ chứng minh kiểm soát có thể tạo một bản sao dữ liệu khó quản lý hơn hệ thống gốc.

Áp dụng các nguyên tắc:

- Thu đúng trường cần cho tuyên bố và bước xác minh.
- Dùng dữ liệu tổng hợp trong kiểm thử khi đáp ứng được mục tiêu.
- Phân tách kết quả tổng hợp khỏi bằng chứng chi tiết có hạn chế truy cập.
- Hạn chế quyền đọc, sửa, xuất và chia sẻ theo vai trò thực tế.
- Mã hóa và quản lý khóa theo kiến trúc, đồng thời kiểm tra đường truy cập dữ liệu sau giải mã.
- Có thời hạn lưu và tác vụ xử lý evidence phù hợp nhu cầu đã xác định.
- Ghi nhận việc truy cập hoặc xuất bộ bằng chứng khi cần truy nguyên.

Che dữ liệu trên dashboard không đủ nếu log gốc, trace, file tải hoặc message lỗi vẫn chứa bản rõ. Kiểm thử cả exception, retry, dead-letter queue và thông báo cảnh báo vì đây là nơi payload thường bị sao chép ngoài đường chính.

Không đưa URL tải có quyền truy cập trực tiếp, token hoặc khóa ký vào bộ evidence chia sẻ rộng. Dùng tham chiếu tới kho được kiểm soát; quyền mở bằng chứng phải được kiểm tra riêng.

Băm email hoặc số điện thoại không tự biến chúng thành dữ liệu vô danh, đặc biệt khi không gian giá trị có thể đoán được hoặc còn bảng liên kết. Chỉ dùng kỹ thuật thay thế định danh với mục tiêu và mô hình đe dọa rõ ràng.

## 12. Transaction, idempotency và tính đầy đủ khi thu thập

### 12.1. Nối quyết định với hiệu lực đã commit

Không ghi “đã xóa”, “đã tải” hoặc “đã công bố file” chỉ vì thao tác bắt đầu. Sự kiện trước commit và kết quả sau commit cần phân biệt rõ.

Khi cùng database, có thể ghi thay đổi nghiệp vụ và sự kiện outbox trong một transaction. Sau đó, bộ thu thập phát hành và lưu bằng chứng theo thiết kế chịu được retry. Ràng buộc này giúp tránh sự kiện báo thành công cho thay đổi đã rollback, nhưng không tự bao phủ storage, dịch vụ ngoài hay toàn bộ pipeline kiểm toán.

Với artifact ở object storage, cần state machine thể hiện các bước tạo, xác minh, công bố và dọn khi thất bại. Transaction database không tự hoàn tác file đã tạo bên ngoài.

### 12.2. Không nhầm lần giao với hiệu lực

Event ID nhận diện sự kiện trong nguồn đã xác thực; operation ID nhận diện thao tác nghiệp vụ; artifact ID nhận diện kết quả cụ thể. Ba giá trị không thay thế nhau.

Bộ thu thập phải chịu được cùng sự kiện tới nhiều lần mà không đếm thành nhiều export hoặc nhiều yêu cầu xử lý dữ liệu. Ngược lại, hai artifact thực sự khác nhau không được bị gộp mất chỉ vì cùng một request ID do người gọi tự khai.

Idempotency key cần có phạm vi phù hợp và ràng buộc nội dung. Đường trả kết quả cũ vẫn phải thực thi quyền theo chính sách hiện hành của luồng; không trả artifact ngoài quyền chỉ vì đã tìm thấy khóa.

### 12.3. Phân biệt quyết định, giao dữ liệu và người đã đọc

Dấu vết cho phép download không chứng minh dữ liệu đã được giao hết. Lượt phản hồi hoàn tất ở server cũng không chắc chứng minh người nhận đã mở và đọc nội dung. Dùng tên sự kiện phản ánh đúng quan sát, tránh ghi “người dùng đã đọc” khi hệ thống chỉ biết đã cấp URL.

Tương tự, xác nhận đã gửi lệnh xóa tới downstream không chứng minh downstream đã xử lý. Cần trạng thái và bằng chứng ở ranh giới có thẩm quyền tương ứng.

## 13. Thu thập liên tục và phát hiện lệch cấu hình

Bằng chứng tại một thời điểm có thể hết tính đại diện khi code, policy, quyền storage hoặc đường tích hợp thay đổi. Cần xác định sự kiện nào khiến kết quả cũ phải được đánh giá lại.

Ví dụ:

- Thêm trường vào serializer hoặc mẫu export.
- Thêm tenant, loại tài khoản hoặc quan hệ ủy quyền.
- Đổi cách cấp URL tải hoặc thời hạn artifact.
- Thay worker, hàng đợi retry hoặc đường quản trị.
- Đổi lịch lưu giữ, phạm vi xóa hoặc quy trình restore.
- Thay cấu hình kho evidence và quyền mở bằng chứng.

Có thể kết hợp kiểm tra cấu hình, test tích hợp, đối soát trạng thái và rà soát mẫu hoạt động. Mỗi phương pháp có giới hạn: cấu hình đúng chưa chứng minh mọi đường dùng nó, còn một mẫu hoạt động không đại diện tự động cho toàn bộ kỳ đánh giá.

Nếu lấy mẫu, cần ghi tổng thể dự kiến, cách chọn, khoảng thời gian và các nhóm được bao phủ. Chỉ chọn các job thành công sẽ bỏ qua lỗi và tác vụ treo. Các luồng rủi ro cao hoặc ngoại lệ cần cách kiểm tra phù hợp thay vì chỉ dựa vào mẫu thuận tiện.

Một chỉ số độ bao phủ có thể là số tổ hợp kiểm soát, luồng và môi trường đã có bằng chứng hợp lệ so với tổng tổ hợp bắt buộc trong phạm vi đã thống nhất. Mẫu số phải được quản lý; không tự tăng độ bao phủ bằng cách bỏ luồng chưa kiểm tra khỏi danh sách.

Theo dõi độ trễ thu thập, checkpoint, lỗi schema, khoảng thiếu dữ liệu và tuổi bằng chứng. Sau sự cố pipeline, khôi phục hoặc đối soát khoảng thiếu rồi mới tuyên bố đã có bằng chứng cho cả khoảng thời gian.

Khi dùng tín hiệu thử có kiểm soát trong môi trường vận hành, phải có phạm vi và quyền phù hợp, dữ liệu thích hợp và cách tránh tạo nghĩa vụ thật ngoài dự kiến. Kết quả từ môi trường tổng hợp cần được phân biệt với quan sát hành vi thực tế.

## 14. Xử lý thiếu bằng chứng và lỗi thu thập

Bộ đánh giá nên phân biệt tối thiểu:

| Kết quả | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| Đạt trong phạm vi đánh giá | Có bằng chứng phù hợp cho điều kiện và kịch bản đã nêu | Artifact tổng hợp đúng hàng, cột và quyền tải theo P3 |
| Không đạt | Có bằng chứng kiểm soát bị phá | File chứa marker email bị cấm hoặc dữ liệu của tenant khác |
| Chưa kết luận | Thiếu bằng chứng hoặc điều kiện quan sát chưa hoàn tất | Không đọc được artifact, job còn chạy hoặc nguồn quyền bị thiếu |
| Ngoại lệ được chấp nhận có phạm vi | Có quyết định ngoại lệ theo quy trình | Giữ dữ liệu nhất định trong thời hạn đã phê duyệt, có kiểm soát bù trừ |

Ngoại lệ không có nghĩa kiểm soát gốc đã đạt. Cần ghi người chấp nhận, lý do, phạm vi, thời hạn và cách theo dõi phần rủi ro còn lại.

Nếu evidence pipeline lỗi, không mặc định mọi thao tác đều đạt hoặc đều vi phạm quyền riêng tư. Ghi nhận mất khả năng quan sát và xác định hoạt động nào có thể bị ảnh hưởng.

Hành vi của luồng nghiệp vụ khi không lưu được bằng chứng phải do chính sách quy định. Chẳng hạn, nếu P3 yêu cầu lưu quyết định bền vững trước khi công bố export, bước công bố phải bị giữ lại khi điều kiện này chưa đáp ứng. Một đường fallback âm thầm bỏ qua yêu cầu đó làm bộ bằng chứng mất giá trị.

Không dùng log payload đầy đủ như phương án dự phòng cho kho evidence hỏng. Nếu có bộ đệm bền vững, nó cũng cần giảm dữ liệu, quyền truy cập, giới hạn dung lượng, thời hạn và cơ chế xử lý lại.

Khi tìm thấy rò rỉ trong bộ bằng chứng hoặc artifact, bảo vệ phạm vi truy cập, giữ dấu vết cần thiết và chuyển sang quy trình ứng phó được cấp quyền. Không phát tán file bị lỗi sang nhiều kênh chỉ để chứng minh rằng file đã lộ dữ liệu.

## 15. Đóng gói bộ bằng chứng có thể đánh giá lại

Một gói bằng chứng nên giúp người đánh giá hiểu tuyên bố, nguồn và giới hạn mà không phải tự suy đoán từ các file rời rạc.

Ví dụ cấu trúc logic, không phải yêu cầu tạo thư mục hay định dạng cố định:

| Thành phần | Nội dung |
| --- | --- |
| Tuyên bố kiểm soát | PRIV-01 đến PRIV-03 trên luồng export hỗ trợ theo P3 |
| Phạm vi | Môi trường, build, cấu hình, tenant tổng hợp và mốc thời gian |
| Mô hình luồng | Request, worker, publish, storage, download và cleanup |
| Danh mục bằng chứng | Evidence ID, loại, nguồn, thời điểm, revision và digest nếu dùng |
| Kịch bản | Tiền điều kiện, lịch thực thi, đầu vào và kết quả kỳ vọng |
| Kết quả quan sát | Trạng thái đã commit, artifact inspection và quyết định quyền liên quan |
| Khoảng trống | Kênh chưa kiểm tra, dữ liệu thiếu, tác vụ còn chạy hoặc kết quả chưa rõ |
| Ngoại lệ | Quyết định được phê duyệt, phạm vi, thời hạn và kiểm soát đi kèm |
| Kết luận | Đạt, không đạt hoặc chưa kết luận cho từng tuyên bố cụ thể |
| Trách nhiệm | Người tạo, người rà soát, thời hạn lưu và quyền truy cập |

Các tham chiếu phải mở được bởi đúng người đánh giá và trỏ tới phiên bản phù hợp. Link tới bản cấu hình “mới nhất” có thể không đại diện cho cấu hình đã dùng trong lần kiểm tra.

Nếu xuất gói ra ngoài hệ thống evidence, kiểm tra lại tập dữ liệu, quyền người nhận, thời hạn và cơ chế thu hồi theo hợp đồng chia sẻ. Việc nguồn gốc có quyền chặt không bảo đảm bản sao được gửi đi cũng có quyền tương đương.

Một kết luận minh họa:

> Trong môi trường kiểm thử tích hợp, build B27 và policy P3, các ca PE-01 đến PE-10 đã hoàn tất theo fixture tổng hợp. Kiểm tra artifact xác nhận chỉ có A1, A2 và hai trường được phép. Đường tải được kiểm tra sau thu hồi quyền theo P3. Kết quả chưa đánh giá cấu hình production hoặc việc xử lý backup.

Đây là ví dụ cách diễn đạt kết luận có giới hạn, không phải báo cáo rằng các ca đó đã được chạy trong bài học. Bộ bằng chứng thật phải chứa kết quả thực thi, thời điểm và nguồn tương ứng.

Không thay khoảng trống bằng câu chung “đã kiểm tra bảo mật”. Nếu một ca chưa chạy, một nguồn không sẵn sàng hoặc một đích chưa đối soát, ghi rõ điều đó.

## 16. Trách nhiệm, lưu giữ và đánh giá lại

Các vai trò cần được phân định theo mô hình tổ chức:

- Chủ sở hữu nghiệp vụ xác định mục đích, đối tượng, trường và vòng đời được phép.
- Nhóm phát triển triển khai kiểm soát, tạo khả năng quan sát và duy trì ca hồi quy.
- Nhóm vận hành xác nhận môi trường, cấu hình và trạng thái pipeline.
- Người rà soát kiểm tra tính phù hợp, độ đầy đủ và giới hạn của bằng chứng.
- Chủ sở hữu dữ liệu hoặc chức năng liên quan phê duyệt ngoại lệ và yêu cầu giữ lại theo quy trình.

Không cần áp cùng một mô hình tách vai trò cho mọi hệ thống, nhưng tránh để một người tự thay policy, tự sửa bằng chứng và tự xác nhận không có khoảng trống mà không có cơ chế kiểm tra phù hợp.

Bằng chứng cũng có vòng đời. Xác định thời hạn theo mục tiêu đánh giá, nhu cầu điều tra và yêu cầu áp dụng đã được tổ chức xác định. Không giữ vô hạn mọi payload chỉ vì có thể hữu ích sau này.

Khi đến hạn xử lý evidence, cần biết bản sao ở đâu, tham chiếu nào bị ảnh hưởng và thông tin tối thiểu nào còn cần cho truy nguyên. Một gói đã xuất hoặc một file đính kèm có thể tồn tại ngoài kho chính.

Các chỉ số hữu ích gồm tuổi bằng chứng so với lần thay đổi kiểm soát gần nhất, số luồng chưa có bằng chứng, số ngoại lệ quá hạn, khoảng thiếu dữ liệu, số phát hiện chưa xử lý và thời gian hoàn tất công việc đối soát.

Số file evidence hoặc dung lượng log không phải thước đo chất lượng. Một bộ ngắn, có phạm vi, có ca âm và ca dương, nối được đến hiệu lực thực tế thường hữu ích hơn nhiều bản sao payload không có ngữ cảnh.

## 17. Sai lầm thường gặp

| Sai lầm | Vì sao không đủ | Cách điều chỉnh |
| --- | --- | --- |
| Có tài liệu chính sách nên kết luận kiểm soát đang hiệu quả | Chưa nối đến phiên bản đang chạy và hiệu lực thực tế | Kết hợp thiết kế, triển khai, vận hành và kiểm tra kết quả |
| Chỉ chụp màn hình phân quyền | Không bao phủ API, worker hoặc storage | Kiểm tra đường tạo và giao dữ liệu thực tế |
| Coi dữ liệu đã mã hóa là được truy cập đúng quyền | Người có khả năng giải mã vẫn có thể đọc ngoài phạm vi | Kiểm tra quyền theo đối tượng, trường và mục đích |
| Chỉ tin metadata export | Metadata đúng nhưng file có thể chứa thêm dữ liệu | Parse artifact và so sánh với fixture độc lập |
| Kiểm tra quyền lúc tạo job rồi bỏ qua mọi bước sau | Thay đổi quyền hoặc trạng thái có thể không còn được áp dụng | Thực thi và chứng minh đúng hợp đồng ở từng ranh giới |
| Dùng cùng khóa replay để trả file mà không kiểm tra quyền | Kết quả cũ có thể lộ cho chủ thể hoặc phạm vi khác | Ràng buộc danh tính, nội dung và quyền truy xuất kết quả |
| Coi HTTP thành công là mọi đích đã xử lý xong | Công việc nền hoặc downstream có thể còn lỗi | Theo dõi trạng thái từng đích và tiêu chí hoàn tất |
| Gọi soft delete là xóa toàn bộ | Cache, file, phân tích và backup có thể còn dữ liệu | Nêu đúng hiệu lực và phạm vi từng bước |
| Băm định danh rồi gọi là vô danh | Có thể liên kết hoặc đoán lại từ nguồn khác | Đánh giá khả năng liên kết và bảo vệ dữ liệu thay thế |
| Dùng thiếu log để chứng minh không có truy cập | Bộ thu thập có thể mất dữ liệu | Kiểm tra độ bao phủ và phân loại chưa kết luận |
| Thêm payload thật vào báo cáo để tăng sức thuyết phục | Tạo bản sao dữ liệu nhạy cảm ngoài nhu cầu | Dùng tham chiếu, dữ liệu tổng hợp và giảm trường |
| Lấy test môi trường thử làm chứng nhận toàn production | Khác cấu hình, dữ liệu, đường tích hợp và thời gian | Giữ kết luận trong phạm vi bằng chứng thực có |

## 18. Danh sách kiểm tra cho privacy control evidence

- Mỗi tuyên bố gắn với một bất biến và chính sách có phiên bản.
- Phạm vi nêu rõ đối tượng, trường, mục đích, kênh, môi trường và thời gian.
- Có bản đồ các đường API, nền, download, quản trị và bản sao liên quan.
- Quyết định quyền gắn với chủ thể đã xác thực và tài nguyên thực bị tác động.
- Bằng chứng phân biệt yêu cầu, quyết định, commit và hiệu lực ở hệ thống ngoài.
- Đã kiểm tra artifact hoặc response thực tế thay vì chỉ kiểm tra metadata.
- Có ca hợp lệ, vượt phạm vi, trường bị cấm, thay đổi quyền, replay và hết hạn.
- Luồng bất đồng bộ thể hiện đúng chính sách ở lúc thực thi, công bố và tải.
- Việc xử lý dữ liệu nói rõ đích đã hoàn tất, phần tồn đọng và giới hạn backup.
- Bộ thu thập chịu được giao trùng, restart, thiếu dữ liệu và lỗi nguồn.
- Evidence được giảm dữ liệu, kiểm soát truy cập, lưu giữ và chia sẻ đúng phạm vi.
- Digest hoặc chữ ký được dùng đúng vai trò, không thay thế chứng minh tính đúng.
- Kết luận phân biệt đạt, không đạt, chưa kết luận và ngoại lệ có thời hạn.
- Có chủ sở hữu, lịch đánh giá lại và điều kiện làm bằng chứng cũ hết tính đại diện.

Bằng chứng quyền riêng tư có giá trị khi người khác có thể truy lại điều kiện được phép, hành động đã xảy ra và dữ liệu thực sự bị tác động. Nó cần đủ rõ để phát hiện kiểm soát bị bỏ qua, đồng thời đủ tiết chế để việc chứng minh không trở thành một nguồn sao chép dữ liệu ngoài nhu cầu.
