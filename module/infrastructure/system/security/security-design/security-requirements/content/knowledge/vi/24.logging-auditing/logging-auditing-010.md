# Administrative action

## 1. Thao tác quản trị cần được giải trình đến kết quả

Administrative action là hoạt động dùng khả năng quản trị để tác động đến tài khoản, quyền, chính sách, cấu hình, dữ liệu, khóa hoặc khả năng vận hành của hệ thống.

Trong logging và audit, mục tiêu không chỉ là ghi “admin đã làm gì”. Hệ thống phải giải thích được:

- Ai khởi tạo và danh tính nào thực sự thực hiện?
- Quyền quản trị nào được dùng, trong phạm vi tenant hoặc tài nguyên nào?
- Yêu cầu có được xác thực, cấp quyền hoặc phê duyệt theo chính sách không?
- Hệ thống định thay đổi gì và thực tế đã thay đổi gì?
- Kết quả là đã tiếp nhận, đã commit, có hiệu lực, thất bại hay chưa biết?
- Bằng chứng có còn đáng tin nếu một tài khoản quản trị bị chiếm không?

Ví dụ, API thu hồi quyền trả thành công sau khi cập nhật kho nguồn. Một số điểm thực thi vẫn giữ quyền cũ trong cache. Audit đúng cần phân biệt “đã ghi thu hồi tại nguồn” với “mọi nơi trong phạm vi đã ngừng chấp nhận quyền”.

OWASP đưa hoạt động quản lý người dùng, thay quyền, sử dụng đặc quyền quản trị và tài khoản khẩn cấp vào các nhóm sự kiện cần được xem xét ghi nhận. Một tài khoản được tin cậy không phải lý do loại hoạt động của nó khỏi audit. [OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html#which-events-to-log).

Bài học tập trung chuyển nhu cầu truy vết này thành yêu cầu bảo mật cụ thể, có phạm vi, mốc đo và tiêu chí kiểm chứng.

## 2. Xác định administrative action theo tác động thực tế

### 2.1. Không chỉ là nút trong trang quản trị

Một thao tác có thể được gọi từ giao diện, CLI, API, worker, công cụ vận hành, pipeline triển khai hoặc trực tiếp ở control plane của nền tảng.

Tên role hoặc URL không đủ để phân loại. Một endpoint không có chữ admin vẫn có thể cấp quyền, export diện rộng hoặc tắt một kiểm soát bảo mật.

Ngược lại, không phải mọi hành động thường ngày của một người có role admin đều tạo cùng mức tác động. Cần phân loại theo hành động và ngữ cảnh quyền thực sự sử dụng.

### 2.2. Lập danh mục theo nhóm tác động

| Nhóm | Ví dụ | Điều cần quan sát |
| --- | --- | --- |
| Danh tính và tài khoản | Tạo, khóa, mở khóa, đổi chủ sở hữu | Actor, đối tượng và trạng thái thực tế |
| Phân quyền | Cấp, thu hồi, đổi role hoặc phạm vi | Chủ thể nhận quyền, quyền trước/sau và hiệu lực |
| Chính sách bảo mật | Đổi quy tắc truy cập, MFA hoặc phiên | Phiên bản, phạm vi và quyết định có thẩm quyền |
| Credential và khóa | Tạo, xoay, ngừng hoặc hủy | Mã tham chiếu, trạng thái và phạm vi ảnh hưởng |
| Dữ liệu | Export, xóa hàng loạt, restore | Tập dữ liệu, tiến độ và tác động không thể hoàn tác |
| Vận hành | Đổi cấu hình, triển khai, chuyển vùng | Phiên bản, môi trường và nguồn khởi tạo |
| Logging và audit | Đổi collector, retention, mức ghi | Thay đổi khả năng quan sát và bằng chứng độc lập |
| Truy cập khẩn cấp | Kích hoạt hoặc dùng break-glass | Danh tính, phạm vi, thời hạn và kết quả sử dụng |

NIST SP 800-53 Rev. 5, kiểm soát AC-6(9), nêu việc ghi nhận sử dụng chức năng đặc quyền. Đây là một nguồn tham khảo để xác định mục tiêu quan sát; phạm vi áp dụng và các tham số vẫn cần được lựa chọn cho hệ thống cụ thể. [NIST SP 800-53 Rev. 5](https://nvlpubs.nist.gov/nistpubs/SpecialPublications/NIST.SP.800-53r5.pdf).

### 2.3. Bốn lớp không được đánh đồng

| Lớp | Câu hỏi |
| --- | --- |
| Authentication | Danh tính hoặc credential nào đã được xác minh? |
| Authorization | Actor có quyền thực hiện hành động này ở phạm vi này không? |
| Approval | Có cần và đã có quyết định phê duyệt phù hợp không? |
| Audit | Có bằng chứng về các bước, việc thực thi và kết quả không? |

Có ticket không tự tạo quyền. Có quyền không chứng minh đã có phê duyệt nếu chính sách yêu cầu. Có audit không làm một thao tác trái quyền trở nên hợp lệ.

Không phải mọi thay đổi đều cần phê duyệt thủ công. Nếu một nhóm thao tác được tự động hóa theo chính sách, audit cần ghi căn cứ tự động tương ứng.

## 3. Từ mô hình đe dọa đến yêu cầu audit

| Đe dọa hoặc sai sót | Tác động | Kết quả cần đặc tả |
| --- | --- | --- |
| Credential quản trị bị chiếm | Thay quyền hoặc lấy dữ liệu dưới danh tính hợp lệ | Ghi việc dùng đặc quyền và ngữ cảnh đủ để điều tra |
| Tài khoản dùng chung | Không xác định được người khởi tạo | Liên kết danh tính cá nhân với phiên hoặc công cụ quản trị |
| Service account che mất người yêu cầu | Chỉ thấy bot thay đổi hệ thống | Giữ chuỗi người khởi tạo, workload và principal hiệu lực |
| Caller tự khai approved=true | Vượt quy trình | Xác minh phê duyệt từ nguồn có thẩm quyền |
| Request đổi sau khi được duyệt | Thực hiện thay đổi khác ý định đã duyệt | Ràng buộc phê duyệt với nội dung, phạm vi và phiên bản |
| Ghi thành công trước commit | Audit mô tả việc chưa xảy ra | Trạng thái theo mốc thực tế và dữ liệu đã xác minh |
| Crash giữa thay đổi và ghi log | Mất dấu tác động đã xảy ra | Cơ chế bền vững và đối soát khoảng trống |
| Timeout thao tác từ xa rồi retry | Thực hiện lặp hoặc báo sai thất bại | Idempotency, mã liên kết và trạng thái chưa biết |
| Quản trị viên tắt log rồi thao tác | Che dấu chuỗi hành động | Bảo vệ cấu hình audit và quan sát từ miền tin cậy khác |
| Ghi nguyên secret hoặc hồ sơ trước/sau | Log thành kho dữ liệu nhạy cảm | Thay đổi có chọn lọc, mã tham chiếu và quyền đọc |
| Trực tiếp sửa kho hoặc control plane | Bỏ qua audit ở API ứng dụng | Inventory mọi đường quản trị và nguồn bằng chứng |
| Rollback xóa lịch sử thao tác | Mất khả năng giải trình | Bản ghi bù hoặc đảo có liên kết, không viết lại quá khứ |

Yêu cầu tốt cần biết sự kiện nào phát sinh, ai chịu trách nhiệm, bằng chứng nào có thể quan sát và phần nào còn nằm ngoài phạm vi bảo đảm.

Không dùng một dòng “mọi thao tác admin đều có log” nếu chỉ kiểm kê giao diện quản trị.

## 4. Inventory và ranh giới tin cậy

### 4.1. Danh mục hành động phải có owner

Mỗi hành động cần mô tả:

- Tên nghiệp vụ và mức tác động.
- Nguồn gọi: giao diện, API, CLI, job, pipeline hoặc đường khác.
- Loại actor và quyền được dùng.
- Tenant, tài nguyên hoặc môi trường chịu tác động.
- Điều kiện xác thực, phân quyền và phê duyệt nếu áp dụng.
- Các bước và trạng thái kết quả cần audit.
- Nguồn xác nhận thay đổi và hiệu lực.
- Owner của hành động, audit và quy trình đối soát.

Cần cập nhật inventory khi thêm endpoint, công cụ hoặc phương án vận hành. Đường khẩn cấp cũng phải nằm trong danh mục.

### 4.2. Phân biệt các nguồn bằng chứng

Log của ứng dụng có thể chứng minh nó đã phát lệnh. Log của hệ thống đích có thể xác nhận lệnh đã được áp dụng. Hai nguồn cần quan hệ liên kết, không tự thay thế nhau.

Một thao tác ở cơ sở dữ liệu hoặc cloud console có thể cần audit của nền tảng, cổng truy cập đặc quyền hoặc cơ chế khác phù hợp. Không giả rằng audit ứng dụng sẽ nhìn thấy mọi thay đổi bên dưới nó.

Quyền root trên máy phát log có thể ảnh hưởng độ tin cậy của log cục bộ. Nếu cần bảo đảm cao hơn, phải xác định nguồn nhận, cách bảo vệ và giới hạn tin cậy tương ứng.

### 4.3. “Ai thực hiện” có thể là một chuỗi

Trong pipeline, người sửa mã, người khởi chạy, người duyệt, workload triển khai và principal có quyền tại đích có thể khác nhau.

Không lấy tên tác giả commit làm bằng chứng duy nhất rằng người đó đã thực hiện thao tác production. Cần metadata được hệ thống thực thi xác minh và quan hệ với lệnh, phiên bản hoặc artifact thực tế.

Chuỗi danh tính nên đủ giải trình nhưng không thu thập mọi dữ liệu cá nhân. Các tham chiếu vẫn cần phân quyền và retention phù hợp.

## 5. Vòng đời sự kiện phải khớp vòng đời thao tác

### 5.1. Định nghĩa các mốc theo loại hành động

| Mốc hoặc kết quả | Ý nghĩa cần chứng minh |
| --- | --- |
| REQUESTED | Hệ thống đã nhận yêu cầu theo phạm vi định nghĩa |
| AUTHORIZED | Có quyết định quyền phù hợp tại điểm kiểm tra |
| APPROVED | Có phê duyệt hợp lệ nếu chính sách yêu cầu |
| STARTED | Đã bắt đầu bước có thể tạo tác động |
| COMMITTED_AT_SOURCE | Nguồn có thẩm quyền đã ghi bền thay đổi |
| EFFECTIVE_IN_SCOPE | Hiệu lực đã được xác nhận tại phạm vi được công bố |
| REJECTED | Không được thực hiện vì điều kiện không đạt |
| FAILED_NO_EFFECT | Có đủ căn cứ xác nhận không có tác động |
| OUTCOME_UNKNOWN | Chưa thể xác định có hay chưa có tác động |
| PARTIAL | Một phần đối tượng hoặc bước đã được thực hiện |
| COMPENSATED | Có hành động bù hoặc đảo theo một quyết định riêng |

Không phải mọi thao tác đều có tất cả các mốc. Export dữ liệu có thể cần mốc tạo file và phát dữ liệu; nó không giống một cập nhật cấu hình có transaction.

Cần chọn mốc cho từng nhóm thay vì ép mọi hành động vào một cờ success.

### 5.2. Ví dụ đổi quyền

~~~mermaid
flowchart LR
    A["Nhận yêu cầu"] --> B["Xác minh quyền và phê duyệt cần thiết"]
    B --> C["Ghi thay đổi tại nguồn"]
    C --> D["Phân phối tới điểm thực thi"]
    D --> E["Xác nhận hiệu lực trong phạm vi"]
    B --> F["Từ chối có lý do"]
    C --> G["Lỗi hoặc kết quả chưa biết"]
    D --> H["Đang chờ hoặc hiệu lực một phần"]
~~~

Nếu chỉ hoàn tất bước C, event có thể ghi COMMITTED_AT_SOURCE. Không được gắn EFFECTIVE_IN_SCOPE nếu chưa có bằng chứng cho bước E.

Trường hợp thu hồi quyền đặc biệt cần kiểm tra những điểm còn cache hoặc phiên có quyền cũ.

### 5.3. Timeout không chứng minh thất bại không tác động

Lệnh từ xa có thể đã thực hiện nhưng phản hồi bị mất. HTTP timeout hoặc mất kết nối không đủ để ghi FAILED_NO_EFFECT.

Cần mã liên kết, cơ chế truy vấn trạng thái hoặc đối soát. Trong lúc chưa biết, event phải giữ OUTCOME_UNKNOWN và có owner xử lý.

Retry mù có thể tạo thêm tác động. Không thực hiện lại một thao tác không idempotent chỉ vì chưa thấy log success ở hệ thống gọi.

### 5.4. Trạng thái tổng hợp không thay thế lịch sử

Có thể có một bảng trạng thái operation hiện tại để phục vụ hỗ trợ. Nhưng thay đổi bảng đó không nên xóa các event đã xảy ra.

Rollback nghiệp vụ cũng là một thao tác mới, có actor, căn cứ và liên kết với thao tác gốc. Không sửa event thành công trước đây thành thất bại để làm lịch sử trông đơn giản hơn.

Với bulk action, cần số đối tượng yêu cầu, thành công, thất bại và chưa rõ theo ngữ nghĩa đã chọn. Một event tổng không nên chứa danh sách không giới hạn; có thể tham chiếu manifest được bảo vệ.

## 6. Danh tính, căn cứ quyền và phê duyệt

### 6.1. Phân biệt người khởi tạo và bên thực thi

Các trường hữu ích có thể gồm:

- Initiator: người hoặc hệ thống khởi tạo.
- Executor: workload hoặc công cụ thực hiện.
- Effective principal: danh tính có quyền tại điểm tác động.
- Delegation hoặc elevation reference: căn cứ ủy quyền hay nâng quyền.
- Target subject: người hoặc tài khoản bị tác động.

Không ghi người nhận quyền thành actor chỉ vì hai trường cùng là user ID.

Nếu dùng danh tính thay mặt, audit phải lấy quan hệ từ cơ chế được xác minh. Header tự khai của caller không tạo bằng chứng ủy quyền.

### 6.2. Ghi việc sử dụng quyền, không ghi secret

Có thể lưu mã tham chiếu phiên quản trị hoặc grant tạm thời, phạm vi và thời hạn đã được xác minh.

Không ghi session token, mã MFA, password khẩn cấp, private key hoặc API key nguyên giá trị.

Một bản ghi về việc xác thực mạnh có thể tham chiếu ngữ cảnh xác thực; không cần lưu lại vật liệu xác thực.

### 6.3. Approval phải gắn đúng yêu cầu

Nếu chính sách yêu cầu phê duyệt, cần xác định:

- Ai có quyền duyệt loại hành động đó.
- Người duyệt có được độc lập với người yêu cầu theo chính sách không.
- Phê duyệt bao phủ tenant, tài nguyên, trường và giá trị nào.
- Phiên bản yêu cầu nào được duyệt.
- Khi nào hết hiệu lực hoặc phải duyệt lại.
- Thay đổi nào làm phê duyệt không còn áp dụng.

Một chuỗi ticket_id hoặc trường approved=true không chứng minh những điều kiện này.

Ví dụ, phê duyệt cấp quyền đọc cho 10 đối tượng không tự cho phép cấp quyền quản trị cho 100 đối tượng. Dùng cùng mã ticket không làm hai yêu cầu trở nên tương đương.

### 6.4. Truy cập khẩn cấp vẫn cần dấu vết

Break-glass có thể dùng quy trình khác luồng thường, nhưng phải có phạm vi, quyền, thời hạn và cách xem xét đã định.

Cần ghi việc kích hoạt lẫn việc sử dụng quyền sau đó. Một lần ghi “đã mở phiên khẩn cấp” không mô tả mọi thay đổi trong phiên.

Nếu cho phép bỏ bước phê duyệt trước theo chính sách khẩn cấp, phải ghi loại ngoại lệ và căn cứ. Không đánh dấu là đã có phê duyệt bình thường khi thực tế chỉ có kiểm tra sau.

## 7. Schema sự kiện quản trị

### 7.1. Những nhóm thông tin cần có

| Nhóm | Nội dung |
| --- | --- |
| Định danh | Event ID, operation ID, attempt ID và phiên bản schema |
| Thời gian | Mốc sự kiện, ghi nhận và tiếp nhận theo nguồn |
| Nguồn | Dịch vụ, instance, kênh và môi trường |
| Actor | Initiator, executor và principal hiệu lực khi có |
| Phạm vi | Tenant, môi trường, tài nguyên và chủ thể bị tác động |
| Hành động | Tên nghiệp vụ chuẩn hóa và loại tác động |
| Quyền | Quyết định, chính sách và ngữ cảnh đặc quyền |
| Phê duyệt | Yêu cầu có cần duyệt, tham chiếu và phiên bản đã duyệt |
| Thay đổi | Tóm tắt trường và giá trị được phép ghi, hoặc tham chiếu |
| Kết quả | Mốc thực tế, outcome, reason và trạng thái tác động |
| Liên kết | Ticket, workflow, deployment hoặc operation liên quan |
| Bằng chứng | Nguồn xác nhận và phạm vi đã kiểm chứng |

Trường không có giá trị cần trạng thái rõ. Không điền một approver giả để mọi event trông giống nhau.

Tên action phải mô tả công việc như iam.role_binding.update hoặc audit.retention.update, không chỉ POST /admin.

### 7.2. Ví dụ cập nhật một role binding

Ví dụ dưới đây dùng dữ liệu tổng hợp. Nó mô tả commit tại nguồn; hiệu lực downstream vẫn đang chờ kiểm chứng.

~~~json
{
  "schema_version": "1",
  "event_type": "admin.action.committed",
  "event_id": "event-demo-01",
  "operation_id": "operation-demo-07",
  "attempt_id": "attempt-demo-02",
  "occurred_at": "2026-11-27T03:00:00.100Z",
  "producer": {
    "service": "iam-admin-service-demo",
    "channel": "ADMIN_API",
    "environment": "TEST"
  },
  "actor": {
    "initiator_ref": "operator-demo-01",
    "executor_ref": "admin-worker-demo-01",
    "effective_principal_ref": "service-principal-demo-03"
  },
  "scope": {
    "tenant_ref": "tenant-demo-a",
    "resource_type": "role_binding",
    "resource_ref": "binding-demo-07",
    "target_subject_ref": "user-demo-24"
  },
  "action": "iam.role_binding.update",
  "authorization": {
    "decision_ref": "decision-demo-09",
    "policy_version": "admin-policy-demo-v5"
  },
  "approval": {
    "required": true,
    "approval_ref": "approval-demo-01",
    "approved_request_version": 4
  },
  "change_summary": {
    "fields": ["role_ref"],
    "before": {"role_ref": "SUPPORT_READER"},
    "after": {"role_ref": "SUPPORT_MANAGER"}
  },
  "result": {
    "phase": "COMMITTED_AT_SOURCE",
    "source_version_before": 12,
    "source_version_after": 13,
    "downstream_effect": "PENDING_VERIFICATION"
  }
}
~~~

Những ID minh họa không quy định thuật toán production. Schema thực tế cần kiểu, giới hạn, nguồn tin cậy và quy tắc duy nhất.

Mốc thời gian phải theo hợp đồng của nguồn. Gọi now trước transaction rồi ghi vào object không tự chứng minh thời điểm commit thực tế.

## 8. Ghi thay đổi đủ dùng mà không lộ dữ liệu

### 8.1. Tách giá trị yêu cầu và giá trị thực tế

Caller có thể yêu cầu một giá trị, nhưng hệ thống từ chối, chuẩn hóa hoặc áp dụng một phần.

Nếu cần ghi request summary, phải phân biệt nó với observed change. Không dùng payload của caller làm bằng chứng trạng thái sau.

Giá trị trước cần gắn với phiên bản mà transaction thực sự cập nhật. Nếu request dựa trên phiên bản cũ bị từ chối, không ghi một diff như thể nó đã được commit.

### 8.2. Before/after không phải ảnh chụp mọi dữ liệu

Đối với role hoặc cấu hình không chứa secret, có thể cần giá trị trước/sau trong audit có quyền.

Đối với password, credential hoặc dữ liệu cá nhân nhạy cảm, thường cần tên trường, mã tham chiếu, phiên bản và loại thao tác thay vì nguyên giá trị.

Ví dụ, event xoay khóa có thể ghi key reference và version, không ghi vật liệu khóa. Event đổi password không cần bản password hoặc bản hash mới trong log phổ thông.

Mã hóa log không phải lý do để sao chép mọi secret vào đó.

### 8.3. Nội dung tự do và công cụ quản trị

Lý do, tên tài nguyên, ticket text, tham số CLI hoặc output terminal có thể chứa dữ liệu không đáng tin và secret.

Cần allowlist, giới hạn, serialize an toàn và hiển thị như dữ liệu. Một chuỗi chứa xuống dòng không được tạo event quản trị giả.

Nếu dùng session recording, phải xét dữ liệu có thể bị ghi hình hoặc ghi output, quyền xem và retention. Recording bổ sung ngữ cảnh, không thay các event nghiệp vụ có kết quả rõ.

## 9. Nhất quán giữa thay đổi và bằng chứng

### 9.1. Hai cách ghi dễ sai

**Ghi success trước rồi mới thay đổi:** nếu transaction thất bại, audit khẳng định một việc chưa xảy ra.

**Thay đổi trước rồi gọi logger riêng:** nếu tiến trình dừng ở giữa, thay đổi có thể tồn tại mà không có event tương ứng.

Yêu cầu cần xác định điểm commit, mô hình sự cố và cơ chế bảo đảm. “Hàm được gọi liền nhau” không chứng minh tính nguyên tử.

### 9.2. Trường hợp thay đổi cục bộ có transaction

Với cập nhật role binding trong một kho có khả năng giao dịch phù hợp, có thể ghi thay đổi và một bản ghi công việc audit trong cùng transaction.

~~~text
Kiểm tra quyền, phê duyệt và phiên bản áp dụng

Trong cùng transaction phù hợp:
    cập nhật role binding
    ghi thông tin audit được phép và công việc chuyển tiếp

Commit:
    cả thay đổi và bản ghi audit cùng bền vững theo mô hình đã chọn

Sau commit:
    chuyển tiếp event đến kho audit
    đối soát bằng ID ổn định
~~~

Đây là một mẫu kiến trúc, không phải yêu cầu mọi hệ thống phải dùng một công nghệ cụ thể.

Một outbox chỉ bảo đảm những gì được ghi trong cùng phạm vi giao dịch. Nó không tự bảo đảm audit thất bại hoặc từ chối, vì bản ghi trong transaction bị rollback cũng có thể mất theo.

Những mốc REQUESTED, REJECTED hoặc lỗi trước commit cần đường ghi và quy tắc độ bền riêng phù hợp.

### 9.3. Trường hợp tác động ở hệ thống từ xa

Không nên giả có một transaction nguyên tử giữa cơ sở dữ liệu ứng dụng, API bên ngoài và kho audit.

Có thể cần:

1. Ghi bền ý định đã được xác minh cùng mã operation.
2. Gửi lệnh có cơ chế idempotency hoặc liên kết được đích hỗ trợ.
3. Nhận và ghi kết quả từ nguồn có thẩm quyền.
4. Khi mất phản hồi, giữ OUTCOME_UNKNOWN.
5. Truy vấn hoặc đối soát theo mã operation và bằng chứng tại đích.
6. Bổ sung kết quả xác minh mà không xóa lịch sử chưa biết trước đó.

Thấy trạng thái hiện tại đúng giá trị mong muốn chưa đủ chứng minh chính operation này đã tạo thay đổi. Có thể có thao tác khác xen vào. Nếu cần chứng minh quan hệ, phải có ID, phiên bản hoặc lịch sử phù hợp tại đích.

### 9.4. Retry và idempotency

Operation ID biểu diễn một công việc logic. Attempt ID phân biệt những lần thực hiện theo hợp đồng. Event ID phân biệt sự kiện; bản sao vận chuyển của cùng event giữ định danh tương ứng.

Caller không được tái sử dụng idempotency key để nhận kết quả tenant khác hoặc gắn một nội dung mới vào phê duyệt cũ.

Retry tác động chưa thực hiện phải đáp ứng điều kiện quyền, thời hạn và phê duyệt còn áp dụng tại điểm thực thi. Một lệnh nằm trong queue từ lâu không tự giữ quyền mãi.

Truy vấn kết quả một operation đã hoàn tất cũng cần quyền đọc thích hợp. Không trả nguyên kết quả nhạy cảm cho bất kỳ người nào biết mã operation.

### 9.5. Nhiều bước và hiệu lực phân tán

Một thay đổi có thể commit ở kho nguồn nhưng chưa áp dụng ở mọi consumer. Một bulk operation có thể thành công ở một số đối tượng rồi dừng.

Cần kết quả theo từng phần hoặc manifest được kiểm chứng, không dùng một cờ success cho toàn bộ.

Nếu có bù trừ, cần action mới và quan hệ với phần đã tác động. Không giả mọi tác động như export hoặc hủy khóa đều có thể đảo.

Đối với thu hồi quyền, điểm kết thúc cần dựa vào hành vi ở nơi chấp nhận quyền, không chỉ một trường revoked trong database.

## 10. Pipeline, độ bền và lỗi audit

### 10.1. Xác định mốc thành công của logging

Các mức khác nhau gồm:

- Event đã được tạo trong bộ nhớ.
- Đã ghi bền tại nguồn theo mô hình được chọn.
- Đã được collector tiếp nhận.
- Đã ghi vào kho audit.
- Đã truy vấn được.
- Đã được detector hoặc người giám sát xử lý.

Lệnh gửi thành công không luôn chứng minh mức sau đã đạt. Cần hợp đồng, timeout, retry và bằng chứng từng mốc.

Độ trễ phải đo từ mốc đúng. Event đến muộn có thể gây cảnh báo muộn dù detector chạy rất nhanh.

### 10.2. Hành động có rủi ro cao cần chính sách khi thiếu bằng chứng

Trong tình huống minh họa của bài, thay quyền bảo mật không được commit nếu không thể ghi bền bằng chứng bắt buộc tại nguồn.

Kho audit trung tâm gián đoạn không nhất thiết chặn mọi thay đổi nếu nguồn vẫn có journal hoặc outbox đủ bền và đủ dung lượng theo cam kết.

Ngược lại, nếu cả nguồn ghi bằng chứng bắt buộc cũng không sẵn sàng, không được tự tiếp tục rồi hy vọng tái tạo audit sau.

Luồng khẩn cấp, nếu có quy tắc khác, phải có thiết kế và căn cứ riêng. Không dùng nhãn break-glass như cờ vô hiệu hóa mọi quan sát.

### 10.3. Không hứa độ bền ngoài mô hình

Bản ghi cùng database có thể chịu restart ứng dụng nhưng không tự chịu được mất toàn bộ dữ liệu của database.

Outbox cũng không tự bảo vệ khỏi actor có quyền sửa cả dữ liệu và outbox. Chuyển sang miền tin cậy khác có thể giảm rủi ro, nhưng tồn tại cửa sổ và giả định cần công bố.

Cần chọn mô hình sự cố, tải, thời gian gián đoạn và mức phục hồi. Bộ đệm hữu hạn không bảo đảm hấp thụ vô hạn.

Khi vượt giới hạn, phải chặn hoặc kiểm soát công việc theo chính sách và báo đúng phần thiếu. Không giảm audit bắt buộc bằng sampling âm thầm.

### 10.4. Bỏ trùng, đối soát và thời gian

Một event gửi lại không phải một thao tác quản trị mới. Một operation có nhiều event vòng đời cũng không được tính thành nhiều lần đổi quyền nếu báo cáo đang đo thay đổi logic.

Cần timestamp có nguồn rõ, phiên bản và quan hệ nhân quả phù hợp. Chỉ sắp xếp theo thời gian nhận không đủ dựng thứ tự giữa cấp quyền, dùng quyền và thu hồi quyền.

Đối soát nên tìm operation thiếu mốc tiếp theo, event có kết quả không khớp nguồn và khoảng trống collector. Một trạng thái chưa biết phải có owner, không bị bỏ quên vì dashboard không hiển thị lỗi đỏ.

## 11. Bảo vệ audit khỏi chính quyền quản trị và sử dụng để giám sát

### 11.1. Tách quyền theo miền và nhiệm vụ

Quyền quản trị ứng dụng không tự bao gồm quyền xóa lịch sử audit.

Writer có thể cần append nhưng không cần sửa event cũ. Người điều tra có thể cần đọc nhưng không cần thay retention hoặc collector. Quyền vận hành kho log cũng cần kiểm soát và audit riêng.

Tách vai trò phải tương ứng với khả năng thực tế ở hạ tầng. Nếu một tài khoản gốc vẫn điều khiển mọi miền, cần ghi rõ giới hạn thay vì tuyên bố tuyệt đối rằng admin không thể sửa log.

### 11.2. Thay logging là một hành động quản trị nhạy cảm

Đổi collector, retention, mức ghi, quyền đọc hoặc tuyến gửi có thể làm mất khả năng phát hiện các thao tác sau.

Cần ghi việc thay cấu hình và có cách quan sát không chỉ phụ thuộc vào đúng đường vừa bị tắt. Có thể cần nguồn control plane, xác nhận nhận ở miền khác hoặc giám sát thiếu heartbeat.

Không để quyền “giảm log debug” tự cho phép tắt các event audit bắt buộc.

Nếu ghi audit việc đọc hoặc sửa audit, cần tránh vòng lặp vô hạn. Thiết kế phải phân định rõ nhóm sự kiện và đường quản trị được theo dõi.

### 11.3. Toàn vẹn, danh tính và sự thật là các mục tiêu khác nhau

Cơ chế hạn chế sửa, chữ ký hoặc chuỗi kiểm chứng có thể giúp phát hiện một số thay đổi và xác minh nguồn.

Chúng không tự chứng minh mọi event đã được tạo, cũng không chứng minh người thật đứng sau credential không bị chiếm.

Audit có thể xác nhận một thao tác dưới một danh tính được hệ thống công nhận. Muốn kết luận về người thực sự có mặt hoặc ý định của họ cần thêm bằng chứng phù hợp.

Không coi checksum thường là chống actor có quyền sửa cả nội dung và checksum.

### 11.4. Mẫu giám sát có ích

Các mẫu cần xem xét theo rủi ro có thể gồm:

- Tạo hoặc cấp thêm quyền quản trị.
- Actor thay quyền của chính mình hoặc mở rộng phạm vi ngoài dự kiến.
- Kích hoạt và sử dụng quyền khẩn cấp.
- Thay logging rồi thực hiện thao tác đặc quyền.
- Export lớn sau khi mới được cấp quyền.
- Nhiều thao tác ở tenant khác với nhiệm vụ thường lệ.
- Operation còn UNKNOWN hoặc PARTIAL quá thời hạn của loại công việc.
- Kết quả thực tế lệch nội dung đã được phê duyệt.

Không phải mọi mẫu đều là bằng chứng tấn công. Pipeline tự động hoặc một đợt vận hành hợp lệ có thể tạo nhiều thay đổi.

Quy tắc cần dữ liệu đầu vào, ngưỡng, phạm vi, owner và cách xử lý nhầm. Cảnh báo không tự cấp quyền đảo mọi thay đổi hoặc khóa cả hệ thống.

### 11.5. Quyền riêng tư và retention

Mã operator, lịch sử công việc, địa chỉ nguồn và tham chiếu dữ liệu có thể nhạy cảm. Cần mục đích, quyền đọc và hạn lưu.

Tệp export audit, bộ đệm, backup và bằng chứng điều tra cũng là bản sao phải quản lý.

Lịch sử cần giữ theo chính sách, nhưng không có nghĩa giữ mọi payload hoặc secret mãi. Thao tác sửa hoặc hủy cuối vòng đời audit phải có điều kiện riêng, không được ngụy trang thành một thao tác dọn log không có thẩm quyền.

## 12. Bộ yêu cầu đo được cho tình huống minh họa

### 12.1. Phạm vi và giả định

Giả sử nền tảng nhiều tenant có ba nhóm hành động: cập nhật role binding, khóa tài khoản và thay cấu hình audit được phép. Các đường đã kiểm kê gồm API, CLI gọi dịch vụ quản trị và worker thực thi.

Với cập nhật cục bộ, thay đổi và bằng chứng commit cần bền vững trong phạm vi giao dịch phù hợp. Với tác động từ xa, cần ý định bền vững, mã operation và quy trình đối soát.

Ví dụ chọn:

- Không commit thay đổi bảo mật khi không thể ghi bền bằng chứng bắt buộc theo mô hình đã chọn.
- Khi pipeline khỏe, event truy vấn được tại kho audit trong tối đa 30 giây từ mốc sự kiện được định nghĩa.
- Phạm vi producer chịu tải tối đa 100 event mỗi giây trong 15 phút gián đoạn kho trung tâm, với event tối đa 4 KiB.
- Operation ngắn trong ví dụ ở trạng thái UNKNOWN hoặc thiếu mốc tiếp theo quá 120 giây phải được phát hiện và cảnh báo trong tối đa 60 giây sau khi đủ điều kiện tại bộ giám sát.
- Kích hoạt break-glass và thay tuyến collector thuộc nhóm cần cảnh báo theo chính sách mẫu.

Các ngưỡng chỉ là giả định học tập, không phải thời hạn chung. Dung lượng phải tính phân bổ thực tế, metadata, journal, retry và loại sự cố cần chịu.

Không áp dụng thời hạn 120 giây cho mọi loại công việc như restore lớn nếu chưa có đặc tả riêng.

### 12.2. Ma trận yêu cầu và tiêu chí chấp nhận

| ID | Yêu cầu | Tiêu chí chấp nhận |
| --- | --- | --- |
| AA-01 | Mỗi hành động quản trị trong inventory có đường phát audit và owner | API, CLI, worker và đường khẩn cấp thuộc phạm vi đều có ca kiểm chứng; không chỉ ghi click giao diện |
| AA-02 | Audit liên kết đúng initiator, executor, principal hiệu lực và chủ thể bị tác động | Workload không che mất người khởi tạo đã biết; caller không giả actor hoặc tenant bằng payload |
| AA-03 | Quyền và phê duyệt cần thiết được xác minh, gắn với đúng nội dung và phiên bản | Request bị đổi sau duyệt hoặc dùng approval sai phạm vi bị từ chối, có event đúng nguyên nhân |
| AA-04 | Kết quả phản ánh mốc thực tế, phân biệt commit, hiệu lực, một phần và chưa biết | HTTP tiếp nhận không tạo event hiệu lực; timeout từ xa không tự thành FAILED_NO_EFFECT |
| AA-05 | Thay đổi bảo mật không được commit nếu không ghi bền được bằng chứng bắt buộc | Lỗi ghi outbox hoặc journal trong mô hình thử không để lại thay đổi trái yêu cầu; không báo success trước commit |
| AA-06 | Retry và vận chuyển lặp không nhân đôi tác động hoặc số thao tác logic | Cùng event được bỏ trùng đúng hợp đồng; operation, attempt và phase khác nhau không bị gộp sai |
| AA-07 | Thay đổi được ghi từ trạng thái thực tế và có giới hạn dữ liệu | Before/after gắn phiên bản đúng; secret, nguyên credential và nội dung nhạy cảm không vào log phổ thông |
| AA-08 | Khi pipeline khỏe, event truy vấn được trong tối đa 30 giây | Đo từ mốc nguồn hợp lệ tới truy vấn kho, có xét giới hạn thời gian; không chỉ dùng ACK của collector |
| AA-09 | Trong tải và gián đoạn đã định, bằng chứng bắt buộc được giữ và chuyển tiếp sau phục hồi | Restart thuộc mô hình không mất event; backlog, bản sao và kết quả được đối soát |
| AA-10 | Actor quản trị ứng dụng không tự xóa audit hoặc vô hiệu hóa audit bắt buộc bằng cấu hình thông thường | Thử quyền sửa lịch sử, thay retention và tắt event; hành động nhạy cảm có dấu vết theo miền phù hợp |
| AA-11 | Operation UNKNOWN hoặc PARTIAL có owner, điều kiện đối soát và cảnh báo theo loại hành động | Ca mất phản hồi giữ đúng trạng thái; quá ngưỡng mẫu được báo và không tự retry tác động không idempotent |
| AA-12 | Dữ liệu audit, bản sao và đường truy cập có quyền, mục đích và retention | Phân quyền đọc/export theo phạm vi; vòng đời và bảo toàn được kiểm tra, không tạo kho payload vô hạn |

AA-05 không có nghĩa mọi API đều phải đợi kho audit trung tâm. Nó yêu cầu bằng chứng đủ bền theo kiến trúc đã chọn trước hoặc cùng thời điểm tạo tác động cần bảo vệ.

AA-09 không được báo đạt ngoài phạm vi sự cố đã thử. Nếu mất cả nguồn dữ liệu và bằng chứng cùng miền, phải báo đúng giới hạn thay vì suy từ kết quả chịu restart ứng dụng.

## 13. Ví dụ đặc tả có truy vết và cách đo độ đầy đủ

### 13.1. Đặc tả AA-05

~~~yaml
requirement_id: AA-05
risk_id: TH-ADMIN-AUDIT-04
risk: Thay đổi quyền đã xảy ra nhưng không còn bằng chứng quản trị cần thiết
scope:
  - Cập nhật role binding tại nguồn có thẩm quyền
  - Các đường API, CLI và worker thuộc inventory
required_behavior:
  - Xác minh actor, tenant, quyền và phê duyệt đang áp dụng
  - Ghi thay đổi và bằng chứng commit theo cơ chế nhất quán đã chọn
  - Không báo COMMITTED trước khi có căn cứ về commit
  - Giữ quan hệ operation, attempt và event
local_transaction_case:
  - Thay đổi và công việc audit cùng bền trong transaction phù hợp
  - Rollback không để lại thay đổi được báo thành công
remote_case:
  - Ghi bền ý định trước tác động
  - Dùng mã liên kết hoặc idempotency theo khả năng đích
  - Mất phản hồi dẫn tới OUTCOME_UNKNOWN và đối soát
failure_behavior:
  - Không tiếp tục thay đổi qua đường không có bằng chứng bắt buộc
  - Không nâng trạng thái chưa biết thành thành công hoặc không tác động
verification:
  - Dừng tiến trình tại các điểm trước và sau commit
  - Gây lỗi ghi bằng chứng bắt buộc
  - Mất phản hồi từ đích sau khi đích đã thực hiện
  - Retry và đối soát không tạo tác động lặp ngoài chính sách
evidence:
  - Trạng thái nguồn và phiên bản
  - Event vòng đời cùng mã liên kết
  - Kết quả đối soát và giới hạn mô hình sự cố
owner: Nhóm IAM, nhóm ứng dụng quản trị và nhóm nền tảng audit
~~~

Đây là nội dung yêu cầu minh họa, không phải cấu hình triển khai. Cần gắn mỗi đường với thành phần, mô hình độ bền và nguồn bằng chứng cụ thể.

### 13.2. Độ đầy đủ theo các mốc cần có

Trong bộ thử, có thể định nghĩa tập E gồm các cặp operation và loại mốc phải xuất hiện theo kịch bản.

~~~text
E = các cặp (operation_id, required_phase) phải có
V = những cặp trong E đã có event hợp lệ, đúng ngữ cảnh

coverage = |V| / |E|
~~~

Không phải mọi operation đều cần EFFECTIVE_IN_SCOPE. Một operation bị từ chối cần event từ chối; một operation đã commit cần mốc tương ứng và những mốc tiếp theo theo hợp đồng.

Một nghìn bản sao của event REQUESTED không bù được event commit bị thiếu. Cũng không nên đòi FAILED_NO_EFFECT khi bằng chứng đúng phải là OUTCOME_UNKNOWN.

Event hợp lệ cần khớp actor, target, phiên bản, approval và trạng thái thực tế. Số lượng đủ nhưng nội dung sai vẫn không đạt yêu cầu giải trình.

### 13.3. Tách độ đầy đủ và sự thật nghiệp vụ

Có đủ event không chứng minh thao tác đúng quyền hoặc đúng kết quả. Cần đối chiếu quyết định, nguồn dữ liệu và các điểm hiệu lực.

Ngược lại, trạng thái cuối đúng không chứng minh audit đầy đủ. Một thay đổi có thể đã được hoàn tác nhưng vẫn cần lịch sử của cả lần thay đổi và lần hoàn tác.

Trong production, counter và sequence giúp đối soát nhưng có giới hạn tin cậy. Không công bố 100% chỉ vì hai số đếm từ cùng tiến trình bị chiếm vẫn khớp nhau.

## 14. Thiết kế kiểm chứng theo rủi ro

### 14.1. Danh tính và ràng buộc phê duyệt

Dùng operator, workload, tenant và tài nguyên tổng hợp trong phạm vi kiểm chứng.

Thử:

- Actor có quyền, actor thiếu quyền và actor sai tenant.
- Người khởi tạo khác người thực thi.
- Caller giả actor, approver hoặc approval_ref.
- Phê duyệt đúng yêu cầu và phê duyệt đã hết hạn.
- Đổi target, loại quyền hoặc số đối tượng sau khi duyệt.
- Job chờ lâu làm điều kiện quyền hoặc phê duyệt thay đổi.
- Luồng tự động hợp lệ không cần người duyệt theo chính sách.

Đối chiếu cả enforcement và audit. Có event từ chối không đủ nếu thay đổi vẫn được thực hiện.

Nếu cần độc lập theo người, hai account ID khác nhau chưa đủ chứng minh hai người khác nhau. Quy tắc nhận diện và kiểm chứng phải phù hợp chính sách đã chọn.

### 14.2. Kết quả, commit và hiệu lực

Kiểm tra trước commit, rollback, commit thành công và lỗi phản hồi sau commit.

Một ca source đã đổi nhưng consumer chưa cập nhật phải thể hiện trạng thái đang chờ, không tự báo hiệu lực toàn phạm vi.

Với thu hồi quyền, dùng credential hoặc phiên thử nghiệm còn hợp lệ ở các điều kiện khác để kiểm tra điểm thực thi. Từ chối vì credential đã tự hết hạn không chứng minh thu hồi đã lan truyền.

Với thao tác từ xa, mô phỏng đích đã thực hiện rồi mất phản hồi. Hệ thống phải giữ trạng thái chưa biết đến khi có bằng chứng phù hợp, không tự gửi lệnh lặp không kiểm soát.

### 14.3. Crash, retry và bulk action

Dừng hoặc gây lỗi tại các điểm thiết kế đã xác định: trước tác động, sau ghi dữ liệu, trước phát event, sau nhận event và trước xác nhận.

Đối soát event, dữ liệu nguồn và kết quả thực tế sau phục hồi. Kiểm tra đúng giới hạn của cơ chế giao dịch hoặc journal.

Gửi lại cùng event để thử bỏ trùng, nhưng cũng tạo attempt hoặc phase mới hợp lệ để chứng minh không gộp nhầm.

Với bulk action, tạo ca một phần thành công, một phần thất bại và một phần chưa rõ. Manifest, số lượng và trạng thái tổng phải khớp; không có một cờ success che toàn bộ khác biệt.

### 14.4. Dữ liệu nhạy cảm và log injection

Đưa secret tổng hợp vào những trường có nguy cơ bị ghi như tham số, lý do, query hoặc kết quả công cụ.

Kiểm tra log ứng dụng, outbox, collector, vùng cách ly event lỗi và export. Lọc ở kho cuối không bảo vệ bản sao đã lộ ở bước trước.

Thử xuống dòng, dấu phân cách và chuỗi giống JSON hoặc HTML. Không được tạo event giả hoặc thực thi nội dung khi xem.

Không dùng credential hay dữ liệu cá nhân thật để làm mẫu kiểm thử.

### 14.5. Quyền sửa audit và đường bypass

Dùng danh tính quản trị ứng dụng thử sửa event cũ, xóa lịch sử, đổi retention hoặc tắt event bắt buộc.

Kiểm tra các đường CLI, worker, thao tác nền tảng và công cụ trực tiếp theo inventory. Nếu một đường không được quan sát, phải ghi giới hạn và xử lý, không coi việc không có event là không có hành động.

Với thay collector hoặc cấu hình audit, xác minh có bằng chứng và tín hiệu phát hiện thích hợp khi chính pipeline đó không còn gửi.

Hoạt động kiểm chứng phải trong phạm vi được phép, không tác động hệ thống production hoặc tenant khác để chứng minh bypass.

### 14.6. Cảnh báo và xử lý chưa biết

Tạo event tổng hợp cho kích hoạt khẩn cấp, thay cấu hình logging và operation còn UNKNOWN quá ngưỡng của loại công việc.

Đo cả thời gian event tới kho và thời gian detector phát cảnh báo. Không trộn mốc nhận cảnh báo với mốc thao tác xảy ra.

Thử bản sao và event đến muộn để tránh cảnh báo trùng. Thêm quy trình hợp lệ để đánh giá mức nhiễu và cách xem xét.

Một cảnh báo cần mã operation, phạm vi và tham chiếu bằng chứng, không cần toàn bộ secret hoặc payload.

## 15. Vận hành và những cách đặc tả cần sửa

### 15.1. Những số liệu nên theo dõi

Nên quan sát:

- Mức phủ hành động, kênh quản trị và môi trường.
- Operation thiếu mốc, kết quả UNKNOWN/PARTIAL và tuổi lớn nhất.
- Độ trễ từ nguồn tới kho audit.
- Backlog, lỗi ghi bền, event lỗi schema và khoảng trống.
- Sự khác biệt giữa thay đổi tại nguồn và hiệu lực downstream.
- Quyền khẩn cấp, thay logging và cấu hình ngoài phạm vi được duyệt.
- Tình trạng quyền đọc/export và vòng đời các bản sao audit.

Nếu cam kết là giới hạn tối đa, trung bình hoặc p95 không đủ chứng minh mọi trường hợp đáp ứng.

Không dùng số HTTP 200, số dòng log hoặc số message đã gửi làm đại diện duy nhất cho số thao tác có bằng chứng đầy đủ.

Một thay đổi có vẻ hợp lệ vẫn cần được điều tra khi bối cảnh bất thường. Một event mức cao cũng không tự chứng minh operator cố ý vi phạm.

### 15.2. Những câu yêu cầu dễ gây hiểu nhầm

| Cách viết chưa đủ | Vấn đề | Cách làm rõ |
| --- | --- | --- |
| Mọi thao tác admin đều có log | Không biết hành động và đường nào | Inventory theo tác động, kênh và owner |
| Admin đã đăng nhập nên không cần ghi nữa | Bỏ mất việc sử dụng quyền | Event theo hành động và kết quả |
| Có ticket là được thực hiện | Ticket không tự chứng minh quyền hoặc approval | Xác minh căn cứ và ràng buộc nội dung |
| Caller gửi approved=true là đủ | Có thể giả hoặc tái dùng | Nguồn phê duyệt có thẩm quyền và phiên bản |
| API success là thay đổi đã có hiệu lực | Có thể mới nhận lệnh hoặc commit nguồn | Phân biệt tiếp nhận, commit và hiệu lực |
| Timeout nghĩa là không có tác động | Lệnh có thể đã chạy ở đích | UNKNOWN, mã liên kết và đối soát |
| Ghi trước/sau toàn bộ để dễ điều tra | Lộ dữ liệu và secret | Diff có chọn lọc và tham chiếu phù hợp |
| Gọi logger sau update là đủ | Có khoảng trống khi crash | Cơ chế nhất quán và mô hình sự cố |
| Event ID bằng operation ID | Mất nhiều phase hoặc attempt | Phân biệt các loại định danh |
| Rollback thì xóa log cũ | Viết lại lịch sử | Event bù/đảo có liên kết |
| Admin ứng dụng cũng quản lý mọi audit | Có thể che dấu thao tác | Tách quyền và miền tin cậy phù hợp |
| Có chữ ký là chứng minh người thật đã làm | Credential hoặc producer có thể bị chiếm | Nêu rõ nguồn, tính toàn vẹn và giới hạn quy trách nhiệm |

Một đặc tả audit cho administrative action cần nối được chuỗi danh tính, căn cứ thực hiện, thay đổi thực tế và mức hiệu lực đã xác nhận. Khi các mốc và bằng chứng được định nghĩa rõ, tổ chức mới có thể giải trình thao tác quản trị thay vì chỉ lưu một lịch sử thông báo thành công.
