# Peer review security

## 1. Peer review bảo mật cần chứng minh điều gì?

**Peer review security** là việc một người có năng lực phù hợp kiểm tra thay đổi của người khác để xác định liệu thay đổi đó có giữ các yêu cầu và bất biến bảo mật hay không. Đối tượng review có thể là mã ứng dụng, cấu hình, hạ tầng dưới dạng mã, schema, pipeline, migration hoặc chính sách quyền, miễn là nằm trong phạm vi thay đổi cần kiểm soát.

Mục tiêu không phải thu thập một nút “Approve”. Review cần làm rõ ai kiểm tra điều gì, dựa trên rủi ro nào, thấy bằng chứng gì, phát hiện nào còn mở và kết luận áp dụng cho phiên bản nào. Một thay đổi nhỏ về số dòng vẫn có thể mở quyền cho mọi tenant hoặc đưa secret vào log.

Trong chương **Secure development** của module yêu cầu bảo mật, peer review là một điểm kiểm chứng trong vòng đời phát triển. Nó liên kết mục tiêu an toàn và mô hình đe dọa với mã, kiến trúc, kiểm thử và quyết định phát hành. Review không thay thế threat modeling, test, phân tích tự động hoặc giám sát; các hoạt động đó cung cấp những loại bằng chứng khác nhau.

Ví dụ: endpoint tải báo cáo đã có middleware xác thực. Một PR thêm chức năng tạo URL tải tệp nhưng chỉ kiểm tra report tồn tại, không kiểm tra người gọi có quyền đọc nó. Reviewer chỉ nhìn thấy `authenticated=true` có thể bỏ sót việc dùng danh tính đúng để đọc đối tượng sai.

### Mục tiêu học tập

Sau bài này, người học có thể:

1. Xác định thay đổi nào ảnh hưởng đến ranh giới tin cậy và yêu cầu bảo mật nào cần kiểm tra.
2. Tổ chức review có người chịu trách nhiệm, năng lực và mức độc lập phù hợp.
3. Viết phát hiện với điều kiện kích hoạt, tác động, yêu cầu bị vi phạm và cách xác minh sửa lỗi.
4. Ràng buộc approval với đúng revision và ngăn đường merge/deploy bỏ qua policy.
5. Thiết kế acceptance criteria cho cả thay đổi ứng dụng và cơ chế review.

## 2. Mô hình đe dọa của một thay đổi phần mềm

### 2.1. Những nguồn lỗi cần xem xét

Một tác giả có thể hiểu sai yêu cầu, bỏ sót nhánh lỗi, sao chép mẫu không phù hợp hoặc đánh giá thiếu tác động của cấu hình. Mã sinh tự động hoặc được công cụ hỗ trợ vẫn có thể chứa các lỗi đó. Việc tác giả tự kiểm tra có ích nhưng không tạo ra một đánh giá độc lập.

Mô hình cũng cần xét hành vi cố ý: giấu thay đổi quyền trong PR lớn, sửa policy review ngay trong PR để tự bỏ gate, đưa code khác sau approval hoặc dùng một đường deploy ngoài quy trình. Peer review chỉ có hiệu lực khi nơi merge/phát hành thực sự cưỡng chế điều kiện.

Danh tính reviewer phải đến từ hệ thống quản lý quyền có thẩm quyền. Tên tác giả ghi trong commit, một dòng “reviewed-by” tự nhập hoặc tài khoản bot không tự chứng minh đã có người phù hợp kiểm tra thay đổi.

### 2.2. Các rủi ro và mục tiêu kiểm soát

| Mã rủi ro | Kịch bản | Mục tiêu kiểm soát |
|---|---|---|
| R1 | Review chỉ xét style hoặc đoạn diff, bỏ yêu cầu và luồng có tác động bảo mật | Review theo ranh giới, hành vi đầu cuối và yêu cầu cụ thể |
| R2 | Tự approve, reviewer thiếu quyền/năng lực hoặc bot thay đánh giá độc lập | Danh tính, vai trò, mức độc lập và routing rõ ràng |
| R3 | Code/config đổi sau approve hoặc merge/deploy dùng revision khác | Ràng buộc revision, candidate và bằng chứng hiện hành |
| R4 | Cảnh báo nghiêm trọng bị đóng bằng lời hứa hoặc test không kiểm tra đúng kiểm soát | Phát hiện có bằng chứng, sửa được xác minh và gate cưỡng chế |
| R5 | Checklist/scanner sạch bị coi là chứng minh không có lỗi logic | Kết hợp review thủ công với kiểm thử ngữ cảnh và công cụ |
| R6 | Ngoại lệ hoặc xử lý khẩn cấp làm mất kiểm soát lâu dài | Phạm vi, thời hạn, thẩm quyền và hoạt động bù rõ ràng |
| R7 | PR, log hoặc bằng chứng chứa secret/dữ liệu nhạy cảm, thiếu audit | Bảo vệ dữ liệu review và truy vết quyết định |

### 2.3. Bất biến của quy trình

> Thay đổi chỉ được merge và phát hành khi yêu cầu review áp dụng đã được thỏa mãn cho đúng nội dung, các phát hiện chặn còn hiệu lực đã được xử lý và bằng chứng bắt buộc tương ứng vẫn hợp lệ.

Approval là kết luận trong một phạm vi, không phải sự miễn trừ cho các commit tiếp theo. Test xanh không tự đáp ứng số reviewer; đủ reviewer cũng không thay thế một bài test bảo mật đang thất bại.

## 3. Đặc tả hợp đồng review

### 3.1. Phạm vi áp dụng

Policy cần bao phủ những thay đổi có thể ảnh hưởng các yêu cầu bảo mật của sản phẩm, gồm cả cấu hình feature, quyền workload, template triển khai, test bảo mật, dependency, schema và đường phát hành. Không loại một thay đổi khỏi review chỉ vì nằm trong folder cấu hình hoặc được bot tạo.

Với thao tác ngoài repository như đổi policy hoặc feature flag ở hệ thống quản trị, cần một record thay đổi và điểm cưỡng chế tương đương theo phạm vi sản phẩm. Một branch rule không kiểm soát được mọi thay đổi trực tiếp ở production nếu quyền quản trị vẫn cho phép đi vòng.

### 3.2. Vai trò và mức độc lập

Hồ sơ tham chiếu trong bài sử dụng các điều kiện minh họa sau:

| Loại thay đổi | Điều kiện review |
|---|---|
| Thay đổi thuộc phạm vi bảo mật thông thường | Ít nhất 1 reviewer phù hợp, khác người chịu trách nhiệm tạo thay đổi |
| Thay đổi nhạy cảm | Ít nhất 2 reviewer khác nhau và độc lập với tác giả: có vai trò owner ứng dụng và reviewer lĩnh vực liên quan |
| Kết quả scan/test tự động | Bằng chứng hỗ trợ; không được tính là một reviewer độc lập |
| Thay đổi policy review/gate | Review theo policy có thẩm quyền ở nhánh đích hoặc nguồn quản lý tin cậy, không theo policy tự nới trong PR |

Thay đổi nhạy cảm trong ví dụ gồm xác thực, phân quyền, isolation tenant, crypto/key/secret, dữ liệu nhạy cảm, thực thi mã, quyền hạ tầng và cơ chế release. Định nghĩa cần được điều chỉnh cho sản phẩm và không chỉ dựa vào tên file; một helper được gọi từ nhiều endpoint cũng có thể thay đổi quyền.

Một người có cả hai vai trò vẫn chỉ là một reviewer, không đủ điều kiện hai người của hồ sơ nhạy cảm. Người đã trực tiếp tạo phần thay đổi không được dùng một tài khoản khác để tự kiểm tra. Hệ thống cần dựa vào danh tính được quản lý và record trách nhiệm, không chỉ so chuỗi tên trong Git.

Năng lực phù hợp là khả năng hiểu luồng và bằng chứng liên quan: reviewer phân quyền cần hiểu chủ thể, tài nguyên, hành động, tenant và nơi cưỡng chế; reviewer crypto cần hiểu hợp đồng khóa và cách sử dụng. Không bắt buộc mọi PR đều do một nhóm bảo mật trung tâm thực hiện, nhưng phải có đường hỗ trợ khi nhóm chưa đủ năng lực.

### 3.3. Thông tin bắt buộc để có thể review

Một đề nghị thay đổi nên cung cấp:

- Hành vi trước/sau và lý do thay đổi.
- Tài sản, ranh giới tin cậy, entry point và luồng dữ liệu chịu ảnh hưởng.
- ID yêu cầu/bất biến liên quan và các giả định cần được xác nhận.
- Quyền, dữ liệu, cấu hình hoặc dependency mới; thay đổi trong đường lỗi và tác vụ nền.
- Test đã chạy trên revision nào, test âm/biên cần có và phần chưa được kiểm chứng.
- Kế hoạch triển khai, quan sát và phục hồi khi thay đổi có tác động vận hành.

Thiếu ngữ cảnh cần thiết là điều kiện yêu cầu bổ sung bằng chứng, không phải lý do approve theo cảm giác. PR quá lớn có thể cần chia theo thay đổi hành vi để người review vẫn quan sát được đầy đủ đường thực thi.

## 4. Phân loại theo rủi ro và liên kết yêu cầu

### 4.1. Xác định thay đổi ranh giới trước khi đọc từng dòng

| Tín hiệu thay đổi | Câu hỏi review trọng tâm | Bằng chứng mong đợi |
|---|---|---|
| Endpoint/hành động mới | Ai được thực hiện trên đối tượng nào, ở tenant nào? | Quy tắc quyền, nơi cưỡng chế và test dùng chủ thể sai quyền |
| Nhận URL/path/query hoặc nội dung bên ngoài | Đầu vào có thể điều khiển đích, câu lệnh hoặc nơi lưu không? | Hợp đồng đầu vào, parser/sink và test âm |
| Job/queue/cache | Quyền có đổi giữa lúc nhận và thực thi không; cache có trộn chủ thể không? | Vòng đời job, thời điểm đánh giá quyền và khóa cache |
| Log/export/diagnostic | Secret hoặc dữ liệu nhạy cảm có đi ra kênh mới không? | Schema dữ liệu ra, che dữ liệu và quyền truy cập |
| Dependency/runtime/pipeline | Có mã mới chạy với quyền nào hoặc artifact nào được phát hành? | Nguồn, cấu hình, scope quyền và liên kết digest/revision |
| Migration/permission/config | Dữ liệu hoặc quyền đã tồn tại có bị mở rộng không? | Quyền trước/sau, kiểm thử migration và kế hoạch phục hồi |

Độ dài diff không phải thước đo mức rủi ro. Một dòng bỏ điều kiện tenant có thể quan trọng hơn nhiều dòng đổi cấu trúc không làm đổi hành vi. Nhãn “refactor” do tác giả đặt cũng không chứng minh bất biến được giữ.

### 4.2. Mẫu truy vết

```text
Rủi ro: tenant A nhận được báo cáo của tenant B
    ↓
Yêu cầu: chỉ cấp quyền tải khi người gọi được phép đọc đúng report
    ↓
Kiến trúc: service cấp quyền trước khi gọi thành phần tạo link tải
    ↓
Thay đổi: endpoint, truy vấn report, bộ kiểm tra quyền và signer
    ↓
Bằng chứng: ca hợp lệ + ca chéo tenant/cùng tenant sai quyền
    ↓
Kết luận review cho revision cụ thể và các phát hiện còn mở
```

Nếu yêu cầu chưa rõ, reviewer cần làm rõ trước kết luận. Chẳng hạn, “link tải phải an toàn” chưa xác định ai được cấp, link có thể chia sẻ không, sống bao lâu và cần thu hồi tức thời hay chấp nhận cửa sổ hiệu lực.

## 5. Quy trình review theo hành vi đầu cuối

### 5.1. Chuẩn bị và chọn đúng phiên bản

Chốt base revision, head revision, phạm vi diff, cấu hình/feature liên quan và policy áp dụng. Xác định reviewer cần thiết theo tác động thực tế. Công cụ tự động có thể gợi ý vùng nhạy cảm nhưng không được là nguồn duy nhất để loại một thay đổi khỏi review.

Tác giả tự kiểm tra và cung cấp bằng chứng ban đầu; reviewer vẫn phải có điều kiện kiểm tra độc lập. Không coi việc tác giả chép một đoạn log “PASS” vào mô tả là đủ nếu không biết log đến từ candidate nào hoặc đã bỏ qua bước gì.

### 5.2. Theo dõi dữ liệu, quyền và tác động phụ

Bắt đầu ở entry point và lần theo xác thực, context tenant, truy vấn đối tượng, quyết định quyền, thay đổi trạng thái và các sink như database, mạng, filesystem, signer hoặc log. Xem cả caller/callee và hợp đồng được dùng, không chỉ các dòng có dấu cộng/trừ.

Với luồng async, xác định quyền nào được chốt khi nhận việc, quyền nào cần đánh giá lại khi chạy và cách xử lý thu hồi. Với cache, kiểm tra key và dữ liệu có ràng buộc đúng principal/tenant không. Với concurrency, xem quyết định quyền có thể bị vô hiệu trước tác động phụ hay cần snapshot/transaction/lease theo hợp đồng.

Các quyết định fail-open, default role, fallback credential và nhánh ngoại lệ thường không nằm trên đường thành công. Chúng cần test riêng; middleware tồn tại không chứng minh mọi job hoặc helper đều đi qua middleware đó.

### 5.3. Đọc test như bằng chứng của yêu cầu

Test cần chứng minh hành vi được phép vẫn hoạt động và hành vi ngoài quyền bị ngăn tại điểm thích hợp. Chỉ assert API trả lỗi chưa chắc chứng minh không có tác động phụ trước lỗi. Với chức năng tạo link, cần quan sát signer/storage; với giao dịch, cần quan sát dữ liệu và sự kiện đã phát.

Mock trả `authorized=true` cho mọi principal có thể làm test không kiểm tra được lỗi phân quyền. Một test lặp lại từng nhánh `if` cũng không tự chứng minh hợp đồng đầu cuối. Reviewer nên chọn ca khác chủ thể, tenant, đối tượng, thời điểm và trạng thái để thử bất biến.

### 5.4. Kết luận và theo dõi sửa

Ghi phát hiện có thể hành động, xác định phần chặn, người xử lý và bằng chứng cần bổ sung. Sau sửa, review nội dung mới và ảnh hưởng liên quan, không chỉ đọc lời phản hồi “đã fix”. Approval phải ghi đúng revision đã kiểm tra và các điều kiện còn áp dụng.

Review kết thúc ở một quyết định có thể truy vết. Tác giả đóng hội thoại hoặc công cụ hiện không còn comment chưa tự chứng minh yêu cầu đã đạt; gate cần kiểm tra trạng thái phát hiện, approval, test và ngoại lệ theo policy.

## 6. Bộ câu hỏi review và giới hạn của checklist

| Nhóm | Câu hỏi cần trả lời cho thay đổi | Ví dụ bằng chứng |
|---|---|---|
| Xác thực | Danh tính được xác minh ở đâu; có đường gọi bỏ qua không? | Luồng API/job và ca không có danh tính hợp lệ |
| Phân quyền | Chủ thể có quyền đúng hành động/đối tượng/tenant ở thời điểm nào? | Quy tắc quyền và ca chéo tenant, sai quyền, đối tượng bị thu hồi |
| Dữ liệu đầu vào/sink | Đầu vào được phân tích theo hợp đồng nào trước khi tới sink? | Truy vấn được ràng buộc, parser, encoding theo ngữ cảnh, ca biên |
| Secret và crypto | Vật liệu lấy từ đâu, phạm vi nào và có bị lộ khi lỗi không? | Binding, version policy, log/trace đã che, hành vi thu hồi |
| Kết nối ngoài | Đích, peer, redirect và credential có bị caller điều khiển không? | Transport/egress policy và fixture bị cấm không nhận request |
| Dữ liệu ra/cache | Response, export, link và cache có lộ hoặc trộn dữ liệu không? | Schema, cache key, quyền đọc và test hai chủ thể khác nhau |
| Tài nguyên và lỗi | Giới hạn, timeout, retry và cleanup có giữ bất biến không? | Test quá tải, timeout, dừng việc và đếm tác động phụ |
| Build/deploy | Thay đổi nào thực thi với quyền gì; evidence gắn artifact nào? | Policy pipeline, nguồn dependency và liên kết revision/digest |
| Logging/phục hồi | Có điều tra được mà không lộ secret; rollback có mở lại rủi ro không? | Audit schema, kế hoạch quan sát và artifact phục hồi hợp lệ |

Checklist là cách bảo đảm câu hỏi không bị quên, không phải bằng chứng tự động cho mọi hàng. Mục không áp dụng cần lý do theo phạm vi. Hàng còn thiếu dữ liệu cần ghi chưa xác định, không chọn “đạt” để hoàn tất biểu mẫu.

Các công cụ phân tích tĩnh, dependency scan, secret scan hoặc trợ lý viết mã có thể hỗ trợ tìm dấu hiệu và tổng hợp ngữ cảnh. Chúng không thay danh tính người chịu trách nhiệm kết luận. Mã hoặc dữ liệu dùng trong review chỉ được đưa vào công cụ/kênh đã được cấp quyền phù hợp, đặc biệt khi có secret hoặc thông tin nội bộ.

## 7. Ví dụ review: cấp link tải báo cáo

### 7.1. Chốt yêu cầu trước khi kết luận về code

Xét endpoint `GET /v1/reports/{report_id}/download` với các yêu cầu minh họa:

| ID | Yêu cầu |
|---|---|
| REP-DL-01 | Chỉ cấp link khi danh tính đã được xác thực có quyền đọc đúng report trong tenant được cấp. |
| REP-DL-02 | Report phải ở trạng thái cho phép tải; caller không được chọn object key, version hoặc credential của storage. |
| REP-DL-03 | Link gắn đúng object/version được cấp, có thời hạn tối đa 60 giây; response cấp link không được cache và URL không được ghi vào log/trace. |
| REP-DL-04 | Từ chối trước khi gọi signer hoặc tạo tác động phụ cấp quyền khi report không tồn tại hoặc caller không có quyền. |

Hồ sơ ví dụ chấp nhận quyền được kiểm tra khi cấp link và link có thể còn dùng được trong tối đa 60 giây. Đây là một quyết định sản phẩm phải được xác nhận. Nếu yêu cầu là thu hồi quyền tức thời cho mọi lần tải, signed URL chỉ kiểm tra tại lúc cấp không đủ; cần gateway kiểm tra lại hoặc cơ chế đầu cuối đáp ứng yêu cầu thu hồi.

### 7.2. Đoạn thay đổi có lỗi

```text
download_report(request):
    identity = authenticated_context(request)
    report = reports.find_by_id(request.report_id)
    require report exists
    link = signer.create_download_link(report.object_key)
    return link
```

`identity` đã tồn tại nhưng không tham gia quyết định quyền. Người dùng A có thể thử report ID ngoài phạm vi của mình. ID khó đoán hoặc kiểm tra đăng nhập không thay thế phân quyền đối tượng; một ID bị lộ qua luồng khác vẫn có thể bị dùng sai.

Reviewer cần chỉ rõ đường từ request tới signer và việc thiếu kiểm tra tenant/quyền/trạng thái. Chỉ yêu cầu “thêm validate đầu vào” không diễn đạt được lỗi và có thể dẫn tới một bản sửa chỉ kiểm tra hình dạng ID.

### 7.3. Hướng sửa theo hợp đồng

```text
download_report(request):
    context = authenticated_context(request)
    validate_report_identifier(request.report_id)

    grant = authorize_and_snapshot_report(
        principal=context.principal,
        tenant=context.authorized_tenant,
        report_id=request.report_id,
        action=REPORT_DOWNLOAD,
        required_state=READY
    )
    if grant is denied:
        audit_denial_without_sensitive_details()
        return consistent_not_found_response()

    link = signer.create_for_exact_object_version(
        grant.object_key, grant.storage_version, ttl_seconds=60
    )
    audit_grant_by_report_id_without_link_value(grant)
    return response_with_no_store_policy(link)
```

Các hàm mô tả trách nhiệm, không phải API đã tự có bảo đảm. `context.authorized_tenant` phải đến từ ngữ cảnh có thẩm quyền, không lấy trực tiếp một header tenant do caller khai. `authorize_and_snapshot_report` phải kiểm tra quyền thực sự và tạo binding tới đối tượng/version được phép; không chỉ so một nhãn tenant rồi cho mọi người trong tenant đọc tất cả report.

Snapshot, trạng thái report và object version cần có ngữ nghĩa phù hợp với storage và hợp đồng concurrency. Nếu storage không hỗ trợ cơ chế mà ví dụ giả định, cần thiết kế cách ràng buộc tương đương. Không để object key thay đổi sau kiểm tra thành dữ liệu khác khi signer sử dụng nó.

Trong ví dụ, phản hồi “không tìm thấy” được dùng nhất quán cho đối tượng không tồn tại hoặc ngoài quyền để hạn chế lộ sự tồn tại; lỗi chưa xác thực có hợp đồng riêng. Chính sách response và timing cần xem xét theo sản phẩm, không dùng che lỗi làm thay thế cho chặn signer.

### 7.4. Một phát hiện có thể hành động

```text
Finding: REV-F001
Revision: HEAD-C7
Requirement: REP-DL-01, REP-DL-04
Severity: HIGH theo mô hình rủi ro của ví dụ
Location: download_report, giữa find_by_id và signer
Trigger: principal tenant A yêu cầu ID report thuộc tenant B
Impact: được cấp khả năng tải dữ liệu ngoài quyền
Expected: phân quyền đúng report/tenant/trạng thái trước signer
Evidence: ca test chéo tenant; số lần gọi signer phải bằng 0
Owner: nhóm tính năng báo cáo
State: OPEN_BLOCKING
```

Phát hiện cần nêu điều kiện và tác động có căn cứ, không phóng đại rằng đã rò dữ liệu production nếu chỉ mới thấy đường code có thể vi phạm. Reviewer có thể đề nghị cách sửa nhưng phải giữ rõ bất biến cần đạt để tác giả chọn thiết kế phù hợp.

## 8. Approval, phát hiện và gate phải gắn đúng nội dung

### 8.1. Trạng thái phát hiện

Một mô hình đơn giản có thể dùng `OPEN`, `FIX_PROPOSED`, `VERIFIED_FIXED`, `ACCEPTED_EXCEPTION` và `NOT_APPLICABLE_WITH_EVIDENCE`. Việc chuyển trạng thái cần người có thẩm quyền và bằng chứng phù hợp; tác giả tự đánh dấu comment resolved không thay kiểm chứng sửa lỗi.

Hồ sơ ví dụ coi phát hiện high/critical còn áp dụng, test bắt buộc thất bại, thiếu phân quyền hoặc thiếu reviewer bắt buộc là điều kiện chặn. Phát hiện mức khác cần được phân loại theo policy; không mặc định “medium” luôn được phép bỏ qua, đặc biệt khi nó vi phạm yêu cầu bắt buộc của tính năng.

Khi bất đồng về điều kiện hoặc mức ảnh hưởng, ghi giả định, bằng chứng và bên quyết định thay vì đổi nhãn để tránh gate. Dấu hiệu đang bị khai thác hoặc rò secret cần kích hoạt xử lý sự cố liên quan, không chỉ chờ PR được merge.

### 8.2. Revision và merge candidate

Approval phải liên kết với head revision, base/context được kiểm tra, yêu cầu áp dụng và danh tính reviewer. Trong hồ sơ này, một commit mới trên nhánh thay đổi làm approval bảo mật cũ hết hiệu lực; cần review lại trước khi merge. Nếu base thay đổi làm ảnh hưởng ngữ cảnh hoặc merge candidate, phải đánh giá lại phần bị ảnh hưởng và chạy lại các kiểm tra cần thiết.

Không chỉ kiểm tra rằng đã từng có hai approval trong lịch sử PR. Các approval phải còn hiệu lực cho nội dung hiện tại; người rời vai trò hoặc không còn thẩm quyền cần được xử lý theo chính sách quyền tại thời điểm quyết định.

Merge queue, rebase, squash hoặc cherry-pick có thể tạo revision khác. Hệ thống cần chứng minh nội dung ứng viên và context vẫn thuộc phạm vi review, cùng CI bắt buộc trên đúng candidate; nếu không chứng minh được thì phải review/kiểm tra lại. Không suy tương đương chỉ vì thông điệp commit giống nhau.

### 8.3. Cưỡng chế tại nơi có thể đi vòng

```text
authorize_merge(change, candidate):
    policy = load_policy_from_trusted_target_context(change)
    require candidate matches current_change_and_required_context
    require risk_classification_is_current(change, candidate)
    require qualified_independent_approvals_satisfy(policy, candidate)
    require required_checks_pass_for(candidate)
    require no_applicable_blocking_finding(change, candidate)
    require exceptions_are_authorized_current_and_in_scope(candidate)
    record_decision_with_revision_and_evidence()
    permit_merge(candidate)
```

Các điều kiện là hợp đồng cần triển khai, không phải API có sẵn. Policy không được lấy từ nội dung PR tự sửa để giảm reviewer hoặc bỏ test. Thay đổi file owner, pipeline, rule merge hoặc cấu hình tương đương phải được xét như thay đổi nhạy cảm theo nguồn policy có thẩm quyền.

Phạm vi cưỡng chế cần bao gồm đường merge qua UI/API, bot, tài khoản có quyền cao và đường triển khai trực tiếp. Quyền khẩn cấp nếu tồn tại phải là cơ chế riêng có phạm vi và audit, không phải một checkbox bỏ qua âm thầm. Dùng một badge “review passed” ở giao diện không chứng minh deployment thực đã đi qua gate.

Artifact phát hành cần được liên kết với mã/cấu hình đã review qua bằng chứng build và digest. Review đúng code rồi triển khai artifact khác là một khoảng hở mà approval ở repository một mình không thể khắc phục.

## 9. Ngoại lệ, xử lý khẩn cấp và dữ liệu review

### 9.1. Ngoại lệ có thẩm quyền và có hạn

Một ngoại lệ cần ID yêu cầu/phát hiện, revision hoặc artifact, môi trường, lý do, tác động còn lại, biện pháp giảm thiểu, người sở hữu, người có thẩm quyền chấp nhận, hạn kết thúc và trigger đánh giá lại. Không dùng một ngoại lệ cho mọi PR tương lai có cùng tên tính năng.

Trong hồ sơ minh họa, ngoại lệ cho phát hiện được policy cho phép có hạn tối đa 7 ngày từ lúc cấp, không tự gia hạn. Ngoại lệ không được dùng để bỏ yêu cầu độc lập reviewer, che test phân quyền bắt buộc đang thất bại hoặc đưa một vi phạm hard gate vào trạng thái sạch. Nếu sản phẩm có quy tắc khác, cần đặc tả riêng quyền chấp nhận và giới hạn, không để reviewer tự suy ra.

Đổi code, context hoặc điều kiện làm giả định ngoại lệ không còn đúng phải buộc đánh giá lại. Hết hạn không chỉ đổi màu trong dashboard; gate không được dùng bản ghi đó để cho phép một quyết định mới. Với phần đã triển khai, cần có việc xử lý và người chịu trách nhiệm theo phạm vi ngoại lệ.

### 9.2. Review khẩn cấp vẫn có các điều kiện lõi

Có thể giảm độ trễ bằng PR nhỏ, xác định reviewer từ đầu, cung cấp ngay bằng chứng và tập trung vào đường rủi ro đang xử lý. Hồ sơ ví dụ vẫn giữ số người review độc lập theo mức nhạy cảm, hard gate và test bắt buộc; nhãn “hotfix” không tự làm các điều kiện đó mất hiệu lực.

Các tài liệu vận hành phụ trợ được policy cho phép bổ sung sau phải có owner và hạn rõ. Ví dụ, record giải thích vận hành của một thay đổi khẩn cấp cần hoàn thiện trong 24 giờ; điều đó không cho phép để trống yêu cầu, phạm vi diff hoặc kết quả kiểm thử cần cho quyết định merge trước đó.

Nếu không đáp ứng được điều kiện release, cần cơ chế xử lý sự cố hoặc giảm thiểu đã được tổ chức cấp quyền, chứ không tự coi không có reviewer là đã có approval. Quyết định vận hành khẩn cấp cần được phân biệt với kết luận peer review đạt.

### 9.3. Audit và bảo vệ thông tin

Record cần liên kết tác giả/người chịu trách nhiệm, reviewer/vai trò, base/head/candidate, phân loại rủi ro, yêu cầu, phát hiện, bằng chứng test, ngoại lệ và quyết định merge/release. Trong hồ sơ ví dụ, các record này được lưu 90 ngày với quyền đọc/sửa/xóa được quản lý; đây là tham số minh họa, không phải thời hạn pháp lý chung.

Không dán token, private key, connection string có password, URL tải có quyền hoặc dữ liệu khách hàng thật vào comment. Dùng fixture và mô tả đã che phù hợp. Nếu secret đã xuất hiện trong diff hoặc đầu ra review, cần xử lý theo quy trình sự cố và giới hạn lan truyền; chỉ xóa comment không tự thu hồi secret đã lộ.

Metric nên phản ánh phát hiện chặn còn mở, approval hết hiệu lực, đường bỏ gate, ngoại lệ quá hạn và lỗi lọt sau review. Tỷ lệ 100% PR có nút approve chưa chứng minh người review có ngữ cảnh hoặc phát hành đúng revision.

## 10. Ma trận yêu cầu review có thể kiểm chứng

Các yêu cầu dưới đây áp dụng cho hồ sơ tham chiếu. Nhóm ứng dụng sở hữu yêu cầu chức năng và test; owner lĩnh vực hỗ trợ đánh giá chuyên môn; nền tảng repository/build/deploy sở hữu các điểm cưỡng chế. Từng vai trò cần được gán cho chủ thể cụ thể khi triển khai.

| ID / rủi ro | Yêu cầu | Điểm cưỡng chế | Bằng chứng chấp nhận |
|---|---|---|---|
| PRV-01 / R1 | Mọi thay đổi trong phạm vi phải có phân loại rủi ro và liên kết yêu cầu theo hành vi, gồm code/config/pipeline và mã sinh tự động. | Record thay đổi và routing review | AC-01: thay một dòng quyền hoặc đổi cấu hình vẫn được phân loại đúng, không tự loại vì nhãn refactor/bot. |
| PRV-02 / R2 | Thay đổi thông thường cần 1 reviewer độc lập; nhạy cảm cần 2 người độc lập khác nhau, đủ vai trò owner và lĩnh vực theo hồ sơ. | Danh tính/vai trò và gate merge | AC-02: tự approve, một người có hai vai trò hoặc bot không đáp ứng điều kiện hai người. |
| PRV-03 / R1 | Review phải xác định entry point, ranh giới, nơi cưỡng chế, đường lỗi và giả định; thiếu bằng chứng bắt buộc không được approve đạt. | Hồ sơ review và người kết luận | AC-03: yêu cầu chưa rõ hoặc caller/callee chưa kiểm tra được giữ ở trạng thái cần bổ sung. |
| PRV-04 / R1, R4 | Thay đổi phải có test âm/biên đầu cuối cho bất biến liên quan, gồm quan sát tác động phụ khi cần. | CI và review test | AC-04: request ngoài quyền bị chặn trước signer; test chỉ assert response không được dùng thay toàn bộ bằng chứng. |
| PRV-05 / R4 | Phát hiện phải có điều kiện, tác động, yêu cầu, owner và trạng thái; phát hiện chặn chỉ được đóng khi sửa đã xác minh hoặc kết luận khác có bằng chứng theo policy. | Quản lý phát hiện và gate | AC-05: tác giả tự resolved hoặc hứa sửa sau không làm hard blocker biến mất. |
| PRV-06 / R3 | Approval và kiểm tra phải gắn revision/candidate/context; commit mới làm approval bảo mật cũ hết hiệu lực theo hồ sơ. | Repository, CI và merge queue | AC-06: push sau approve hoặc candidate khác buộc kiểm tra/review lại theo policy. |
| PRV-07 / R2, R3 | Gate phải dùng policy có thẩm quyền và bao phủ đường UI/API/bot/deploy; PR không được tự giảm policy áp dụng cho chính nó. | Quyền repository và release | AC-07: sửa policy trong PR hoặc đường đi vòng không tự tạo quyền merge/deploy. |
| PRV-08 / R5 | Công cụ tự động chỉ là bằng chứng hỗ trợ, không thay số reviewer hoặc kết luận ngữ cảnh; chưa xác định không được coi là sạch. | Gate và quy trình reviewer | AC-08: scanner xanh không đủ khi thiếu review độc lập hoặc còn lỗi logic chưa được xử lý. |
| PRV-09 / R7 | Comment, report và kênh review không được lan truyền secret/dữ liệu thật ngoài quyền; phát hiện lộ phải có đường xử lý. | Công cụ review, log và quyền truy cập | AC-09: marker fixture không bị khuếch tán qua báo cáo/comment tự động; record có xử lý sự cố phù hợp. |
| PRV-10 / R6 | Ngoại lệ tối đa 7 ngày, đúng phạm vi, không tự gia hạn; hotfix giữ điều kiện lõi, tài liệu phụ trợ được hoãn có hạn 24 giờ. | Gate, quản lý ngoại lệ và vận hành | AC-10: ngoại lệ hết hạn/sai revision hoặc nhãn hotfix không bỏ hard gate. |
| PRV-11 / R3, R7 | Quyết định phải audit được với identity, revision, yêu cầu, finding/test/exception; record giữ 90 ngày theo hồ sơ và có quyền sửa/xóa được quản lý. | Repository, CI và audit | AC-11: đối chiếu đầy đủ nguồn và phát hiện record thiếu hoặc bị sửa ngoài quyền. |
| PRV-12 / R3, R6 | Release phải liên kết artifact với nội dung đã review; cherry-pick/rollback/thay cấu hình phải được đánh giá theo policy hiện hành. | Build evidence và deploy gate | AC-12: artifact khác hoặc commit chuyển nhánh không tự kế thừa approval cũ. |

## 11. Test và acceptance criteria cho quy trình

### 11.1. Bộ fixture và cách kiểm chứng

Dùng repository/pipeline thử, tài khoản với vai trò được kiểm soát, ứng dụng báo cáo fixture và signer/storage giả lập có bộ đếm tác động. Không tạo PR chứa secret production hoặc thử quyền thật ngoài phạm vi chỉ để chứng minh gate.

Quan sát tại hệ thống quản lý quyền, record approval/finding, candidate chạy CI và điểm merge/deploy. Một trạng thái hiển thị trên UI không đủ nếu API hoặc bot vẫn cho đi vòng. Các ca sau là đặc tả nghiệm thu cần chạy, không phải tuyên bố một hệ thống đã được kiểm thử.

### 11.2. Các ca nghiệm thu

**AC-01 — Phân loại theo hành vi, truy vết PRV-01.**

Tạo các PR fixture: bỏ một điều kiện tenant, đổi role qua cấu hình, đổi pipeline phát hành và một diff do bot tạo. Gắn nhãn “refactor” hoặc “generated” không được tự miễn yêu cầu review. Một thay đổi thực không ảnh hưởng bảo mật phải có lý do phạm vi rõ, tránh giải pháp phân loại mọi PR thành high mà không có phân tích.

**AC-02 — Reviewer độc lập và đủ vai trò, truy vết PRV-02.**

Cho tác giả thử tự approve, một người có hai vai trò approve một lần, bot tạo trạng thái approve và reviewer không có vai trò cần thiết. Không trường hợp nào đủ điều kiện hai người của PR nhạy cảm. Đối chứng là hai reviewer đủ vai trò, độc lập với tác giả và còn thẩm quyền cho đúng candidate; thay đổi thông thường cũng được thử với một reviewer hợp lệ.

**AC-03 — Ngữ cảnh và yêu cầu chưa đầy đủ, truy vết PRV-03.**

Đưa PR cấp link nhưng chưa xác định quyền đọc report, thời hạn link hoặc điều kiện thu hồi. Review phải ghi cần làm rõ và không kết luận REP-DL-01–04 đã đạt. Bổ sung hợp đồng rồi kiểm tra caller/callee, signer và luồng lỗi; record phải thể hiện yêu cầu nào được xác minh bằng bằng chứng nào, thay vì chỉ đánh dấu checklist.

**AC-04 — Lỗi phân quyền và tác động phụ, truy vết PRV-04.**

Với ví dụ mục 7, chạy caller hợp lệ, caller chéo tenant, cùng tenant nhưng thiếu quyền report, report không READY và caller chưa xác thực. Chỉ ca đủ quyền/trạng thái được cấp đúng link có hạn không quá 60 giây; các ca bị từ chối không gọi signer. Thử header tenant giả và thay report/object reference ngoài hợp đồng; chúng không được mở quyền. Dùng bộ đếm signer và binding object/version làm bằng chứng, không chỉ mã response.

**AC-05 — Đóng phát hiện phải có bằng chứng, truy vết PRV-05.**

Tạo REV-F001 ở trạng thái chặn, cho tác giả đóng hội thoại hoặc thêm lời hứa sửa sau; gate vẫn từ chối nếu điều kiện vi phạm còn. Sau bản sửa, reviewer có thẩm quyền xác minh diff mới và ca AC-04 tương ứng; chỉ khi trạng thái hợp lệ và các điều kiện khác đạt mới được merge.

**AC-06 — Push sau approval và candidate thay đổi, truy vết PRV-06.**

Approve head H1 rồi push H2 thay luồng cấp quyền; approval bảo mật cũ phải hết hiệu lực và CI H1 không dùng thay cho H2. Thử thay base hoặc tạo merge candidate có khác biệt context liên quan; hệ thống phải yêu cầu kiểm tra lại phần bị ảnh hưởng. Sau re-review và CI đúng candidate, đường hợp lệ mới được đi tiếp.

**AC-07 — Policy và đường đi vòng, truy vết PRV-07.**

Trong PR nhạy cảm, thử sửa rule review/owner hoặc pipeline để chỉ cần tự approve. Gate phải dùng policy có thẩm quyền, không tự chấp nhận cấu hình hạ chuẩn trong PR. Lặp lại thao tác merge qua API/bot và deploy trực tiếp với principal thử không đủ quyền; không đường nào được cho phép ngoài hợp đồng. Nếu có quyền khẩn cấp riêng, kiểm tra phạm vi và audit của nó, không ghi nhầm là peer review bình thường đã đạt.

**AC-08 — Công cụ không thay reviewer, truy vết PRV-08.**

Cho scanner trả xanh đối với fixture có lỗi logic phân quyền và chưa có reviewer độc lập; gate không được cho merge chỉ từ scan. Một kết quả không xác định hoặc lỗi công cụ không được đổi thành sạch. Fixture có thể dùng để kiểm chứng quy trình yêu cầu phân tích ngữ cảnh và ghi nhận REV-F001; nó không chứng minh reviewer sẽ tìm được mọi lỗi trong mọi PR tương lai.

**AC-09 — Bảo vệ dữ liệu review, truy vết PRV-09.**

Dùng marker secret thử để mô phỏng đầu ra nhạy cảm. Comment/report/log tự động phải che hoặc giới hạn theo schema, không sao chép nguyên credential sang các kênh mới. Nếu fixture đặt marker vào diff gốc, quy trình phải phát hiện/giới hạn truy cập và xử lý theo policy, không tuyên bố chưa từng xuất hiện chỉ vì đã xóa một comment. Bằng chứng điều tra dùng định danh đã che và không chứa secret production.

**AC-10 — Ngoại lệ và hotfix, truy vết PRV-10.**

Cấp ngoại lệ thuộc loại được cho phép trong tối đa 7 ngày, rồi thử dùng cho revision/phạm vi khác hoặc sau hạn; gate phải từ chối hoặc buộc đánh giá lại theo policy. Đặt nhãn hotfix khi thiếu reviewer, còn hard blocker hoặc test phân quyền thất bại; các điều kiện lõi vẫn chặn. Với tài liệu phụ trợ được phép hoãn, đồng hồ kiểm soát phải cho thấy có owner và hoàn tất trong 24 giờ, không coi ticket tồn tại là đã hoàn tất.

**AC-11 — Audit và quyền đối với record, truy vết PRV-11.**

Đi qua tạo PR, phân loại, phát hiện, sửa, approval, CI, merge và release fixture. Đối chiếu identity/vai trò, base/head/candidate, yêu cầu, bằng chứng và quyết định. Thử chỉnh/xóa record bằng principal không có quyền; phải bị từ chối và có quan sát phù hợp. Kiểm tra policy lưu 90 ngày và quyền thay policy bằng cấu hình/thử nghiệm có kiểm soát, không cần chờ thật 90 ngày.

**AC-12 — Liên kết release và nội dung đã review, truy vết PRV-12.**

Review candidate A rồi thử triển khai artifact B có cùng tên/version nhưng khác nguồn hoặc digest; deploy gate phải phát hiện không khớp. Cherry-pick sang nhánh có context khác hoặc rollback tới thay đổi đang bị policy chặn không tự được kế thừa approval cũ. Đường hợp lệ giữ được bằng chứng build/deploy liên kết tới nội dung đã được kiểm tra và policy hiện hành.

### 11.3. Điều kiện chấp nhận của hồ sơ

PRV-01–PRV-12 phải có chủ sở hữu, cấu hình cưỡng chế và bằng chứng AC-01–AC-12 trên kiến trúc quản lý thay đổi thực. Phần thiếu dữ liệu, không áp dụng hoặc có ngoại lệ cần được ghi đúng trạng thái, không đổi thành đạt để đóng PR.

Khi đổi quyền repository, cơ chế bot, merge queue, CI, owner policy hoặc đường deploy, cần thực hiện lại các ca bị ảnh hưởng. Review đạt cho một revision chứng minh quyết định trong phạm vi và bằng chứng đã có; nó không chứng minh phần mềm hoàn toàn không còn lỗ hổng.

## 12. Ví dụ nối review với vòng đời phát hành

Với tính năng tải báo cáo, tác giả mô tả REP-DL-01–04 và đường API → service → signer. Vì thay đổi liên quan phân quyền và dữ liệu tenant, hồ sơ yêu cầu hai reviewer độc lập đúng vai trò. Reviewer phát hiện REV-F001, chỉ rõ ca chéo tenant và giữ gate chặn.

Tác giả sửa việc cấp quyền trước signer, bổ sung test hợp lệ/âm và ràng buộc đúng object/version. Head mới làm approval cũ hết hiệu lực; reviewer kiểm tra lại nội dung và bằng chứng, đồng thời xác nhận quyết định chấp nhận cửa sổ link 60 giây. Nếu yêu cầu thu hồi tức thời được bổ sung, thiết kế phải được xem lại thay vì tái dùng kết luận cũ.

Sau khi các điều kiện review và test đạt cho candidate hiện hành, build tạo artifact có nguồn và digest được liên kết với record. Deploy chỉ nhận artifact phù hợp, vận hành theo dõi lỗi quyền và tín hiệu rò dữ liệu mà không ghi URL tải vào log. Một lỗi lọt sau review quay lại thành yêu cầu/test hoặc cải tiến policy có chủ sở hữu.

Giá trị của peer review nằm ở việc nối được rủi ro, yêu cầu, đường thực thi, bằng chứng và quyết định cho đúng nội dung được phát hành. Số approval chỉ là một điều kiện trong chuỗi đó; tính độc lập, chất lượng phân tích và hiệu lực cưỡng chế mới giúp điều kiện ấy có ý nghĩa bảo mật.
