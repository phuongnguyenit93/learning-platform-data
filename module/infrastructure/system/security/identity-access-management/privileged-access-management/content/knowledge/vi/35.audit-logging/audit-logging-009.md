# Log admin của PAM

## 1. Vì sao phải ghi lại hoạt động quản trị chính hệ thống PAM?

Privileged Access Management (PAM) kiểm soát các quyền nhạy cảm: ai được lấy credential, mở phiên quản trị, thực hiện tác vụ với quyền cao và sử dụng quyền đó trong bao lâu. Nhưng bản thân PAM cũng có tài khoản quản trị, policy, cấu hình vault, connector, cơ chế phê duyệt và cấu hình lưu bằng chứng. Người thay đổi những thành phần này có thể tác động đến rất nhiều hệ thống đích cùng lúc.

Vì vậy, ngoài việc biết một kỹ sư đã làm gì trên máy chủ, tổ chức cần trả lời được câu hỏi: **ai đã thay đổi cách PAM cho phép, giới hạn và ghi lại hoạt động đó?**

Ví dụ, một phiên SSH có thể hoàn toàn phù hợp với policy tại thời điểm truy cập. Tuy nhiên, năm phút trước phiên đó, một quản trị viên đã bỏ yêu cầu phê duyệt và tắt ghi phiên cho nhóm máy chủ production. Nếu chỉ xem log phiên, người điều tra sẽ bỏ qua thay đổi tạo điều kiện cho truy cập.

Log admin của PAM là dấu vết về hoạt động trên **mặt phẳng quản trị của PAM**. Trong bài này, “admin” bao gồm quản trị viên con người, tài khoản dịch vụ, pipeline và API client có khả năng thay đổi cấu hình hay quyền của nền tảng, không chỉ người đăng nhập vào giao diện quản trị.

Mục tiêu học tập:

- Phân biệt log admin PAM với log truy cập credential, log phiên và log vận hành.
- Xác định những thao tác quản trị cần có bằng chứng.
- Thiết kế sự kiện cho biết chủ thể, thay đổi, kết quả và chuỗi phê duyệt.
- Bảo vệ log trước sửa, xóa, ngừng thu thập và lạm dụng quyền đọc.
- Dùng log admin để phát hiện thay đổi nguy hiểm và dựng lại một tình huống điều tra.

## 2. Ranh giới của log admin

Một nền tảng PAM thường phát ra nhiều nhóm sự kiện. Chúng bổ sung cho nhau nhưng không thay thế nhau.

| Nhóm log | Câu hỏi chính | Ví dụ |
|---|---|---|
| Admin audit | Ai thay đổi cơ chế quản trị PAM? | Sửa policy JIT, gán vai trò quản trị vault |
| Credential access | Ai yêu cầu hoặc sử dụng bí mật? | Checkout credential, yêu cầu cấp credential động |
| Session audit | Ai mở phiên và hoạt động trong phiên ra sao? | Mở phiên RDP qua broker, gắn bản ghi phiên |
| Authentication | Chủ thể được xác thực như thế nào? | Đăng nhập, bước xác thực bổ sung thất bại |
| Operational log | Nền tảng đang vận hành thế nào? | Collector không kết nối được đích lưu log |
| Log của hệ thống đích | Tài nguyên đích thực sự nhận và thực thi gì? | Hệ điều hành ghi nhận thay đổi nhóm quản trị |

Một sự kiện có thể liên quan nhiều nhóm. Đăng nhập vào console admin là sự kiện xác thực, đồng thời là ngữ cảnh quan trọng cho các thao tác admin sau đó. Đọc một credential khôi phục phục vụ bảo trì PAM có thể đồng thời là truy cập bí mật và một hoạt động nhạy cảm của quản trị nền tảng.

Không nên gom tất cả vào một loại “admin activity” quá chung chung. Cần phân loại đủ rõ để người điều tra biết đó là **đăng nhập**, **yêu cầu thay đổi**, **thay đổi đã được áp dụng**, hay chỉ là **thử thực hiện nhưng bị từ chối**.

### 2.1. Tên tài khoản không quyết định loại sự kiện

Tài khoản có tên `pam-admin` mở phiên vào máy chủ ứng dụng không làm cho toàn bộ phiên đó trở thành log cấu hình PAM. Ngược lại, một service account mang tên `automation-reader` nhưng đang được cấp quyền sửa policy vẫn tạo ra hoạt động admin khi gọi API cập nhật policy.

Phân loại theo **hành động và đối tượng chịu tác động**, kết hợp quyền thực tế tại thời điểm hành động. Không suy luận chỉ từ username hay nhãn vai trò hiện tại.

### 2.2. PAM không tự nhìn thấy mọi thay đổi ngoài nó

Nếu quản trị viên máy chủ sửa trực tiếp file cấu hình hoặc cơ sở dữ liệu mà không đi qua API của PAM, ứng dụng có thể không phát ra cùng loại sự kiện như khi thay đổi qua console.

Do đó, phạm vi bằng chứng cần bao gồm các đường quản trị thực sự tồn tại:

- Giao diện web và API quản trị.
- CLI, công cụ bảo trì và automation.
- Hệ điều hành, cơ sở dữ liệu và nền tảng chạy PAM.
- Hạ tầng lưu bản ghi phiên, audit store và bản sao lưu.
- Nhà cung cấp định danh hoặc hệ thống quản lý nhóm nếu chúng quyết định quyền admin PAM.

Log admin ở lớp ứng dụng là một phần của chuỗi bằng chứng. Nó không tự chứng minh rằng không có thay đổi ở lớp thấp hơn.

## 3. Những hoạt động quản trị cần có dấu vết

Không chỉ ghi các thay đổi thành công. Một yêu cầu bị từ chối, một lần xuất dữ liệu audit hay một thao tác thay đổi chính cấu hình logging đều có thể quan trọng.

### 3.1. Danh tính và quyền quản trị

Các sự kiện cần xem xét gồm:

- Tạo, vô hiệu hóa, khôi phục hoặc xóa tài khoản quản trị.
- Gán hoặc thu hồi vai trò admin, thay đổi phạm vi tenant, vault hay nhóm tài nguyên.
- Thay đổi nhóm được ánh xạ từ hệ thống định danh.
- Tạo API client, thay đổi quyền hoặc chủ sở hữu của automation identity.
- Thay đổi yêu cầu MFA, cơ chế federation hoặc đường đăng nhập dự phòng.
- Kích hoạt và kết thúc quyền quản trị JIT.
- Sử dụng tài khoản hoặc quy trình break-glass.

Khi ghi việc gán vai trò, cần lưu vai trò và phạm vi tại thời điểm đó. Một bản ghi chỉ nói “user updated” không cho biết người đó vừa được quyền đọc báo cáo hay toàn quyền quản trị vault.

### 3.2. Policy cấp quyền và kiểm soát phiên

Những thay đổi có ảnh hưởng trực tiếp đến least privilege và JIT/JEA cần quan sát được:

- Thời hạn cấp quyền, giới hạn phiên đồng thời, tập lệnh hoặc tác vụ được phép.
- Yêu cầu phê duyệt, người phê duyệt và số cấp phê duyệt.
- Điều kiện thiết bị, mạng nguồn hoặc mức độ xác thực.
- Cơ chế che credential, giới hạn truyền file, clipboard hoặc chuyển tiếp kết nối.
- Yêu cầu ghi phiên và cách xử lý khi dịch vụ ghi phiên không hoạt động.
- Ngoại lệ cho tài khoản, nhóm người dùng hoặc nhóm tài nguyên.
- Quy tắc tự động hết hạn và thu hồi.

Cần phân biệt sửa một bản nháp policy với kích hoạt policy cho production. Hai sự kiện này có mức tác động khác nhau.

### 3.3. Vault, credential và connector

Ví dụ về hoạt động admin cần ghi:

- Tạo, đổi chủ sở hữu hoặc thay phạm vi vault.
- Onboard, chuyển nhóm hoặc loại bỏ tài khoản đặc quyền.
- Đổi lịch rotation, cơ chế reconcile hoặc cấu hình xác minh credential.
- Tạo, sửa, vô hiệu hóa connector và thay đổi phạm vi hệ thống đích.
- Thay đổi cách ứng dụng được nhận bí mật.
- Cập nhật tham chiếu khóa, certificate hoặc cấu hình bảo vệ dữ liệu.

**Ghi hoạt động thay đổi bí mật không đồng nghĩa ghi giá trị bí mật.** Log có thể cho biết credential nào đã được thay, phiên bản nào được kích hoạt, kết quả thế nào và ai thực hiện; không chứa mật khẩu, private key hay token mới.

### 3.4. Chính sách audit, dữ liệu và phục hồi

Đây là nhóm đặc biệt nhạy cảm vì có thể ảnh hưởng khả năng chứng minh các hoạt động khác:

- Bật, tắt hoặc đổi phạm vi ghi audit.
- Thay đổi nơi gửi log, cấu hình xác thực kênh gửi hoặc bộ lọc sự kiện.
- Sửa thời hạn lưu giữ, quyền xóa, cơ chế khóa lưu trữ hoặc legal hold nếu có.
- Xóa, xuất, tải xuống hoặc thay đổi quyền đọc log và bản ghi phiên.
- Thực hiện backup, restore và khôi phục cấu hình.
- Nâng cấp, rollback phiên bản hoặc thay đổi cấu hình cụm PAM.
- Thay đổi cấu hình thời gian, chứng thư hoặc khóa bảo vệ bằng chứng.

Hoạt động đọc và xuất dữ liệu audit cũng cần kiểm soát: log có thể tiết lộ cấu trúc hạ tầng, danh tính quản trị viên và thông tin sự cố. Không nên mặc định người đọc được báo cáo cũng được tải toàn bộ bản ghi thô.

## 4. Một sự kiện admin cần nói được điều gì?

Có thể dùng sáu câu hỏi để đánh giá một bản ghi:

1. **Ai** thực hiện, và nếu là automation thì đại diện cho ai?
2. **Làm gì** qua console, API, CLI hay đường bảo trì?
3. **Tác động vào đâu**, với phạm vi và phiên bản đối tượng nào?
4. **Điều gì thay đổi**, ở mức đủ phục vụ điều tra nhưng không lộ bí mật?
5. **Kết quả thực tế là gì**, đã được áp dụng hay mới tiếp nhận?
6. **Dựa trên quyền và phê duyệt nào**, tại thời điểm thực hiện?

### 4.1. Các trường cốt lõi

| Nhóm | Trường minh họa | Ý nghĩa |
|---|---|---|
| Định danh sự kiện | `event_id`, `event_type`, `schema_version` | Nhận diện, phân loại và đọc đúng cấu trúc |
| Nguồn phát | `source.instance_id`, `source.epoch`, `source.sequence` | Phân biệt node và theo dõi khoảng trống khi nguồn hỗ trợ sequence |
| Thời gian | `occurred_at`, `received_at` | Tách lúc xảy ra và lúc collector nhận |
| Chủ thể | `actor.subject_id`, `actor.type`, `actor.session_id` | Danh tính ổn định và phiên thực hiện |
| Đại diện | `initiated_by`, `delegated_by` | Truy nguồn yêu cầu khi có cơ chế ủy quyền |
| Ngữ cảnh truy cập | `channel`, `client_id`, `source_address`, `auth_context` | Đường thực hiện và trạng thái xác thực liên quan |
| Đối tượng | `resource.type`, `resource.id`, `resource.scope` | Đối tượng và phạm vi chịu tác động |
| Thao tác | `action`, `changed_fields` | Hành động có nghĩa rõ ràng |
| Kết quả | `outcome`, `reason_code`, `effective_revision` | Trạng thái xử lý và lý do |
| Liên kết | `request_id`, `change_id`, `approval_id`, `job_id` | Nối yêu cầu, phê duyệt và thực thi |
| Kiểm chứng | `integrity`, `export_batch_id` nếu có | Tham chiếu cơ chế kiểm chứng hoặc gói bằng chứng |

Đây là một mô hình thiết kế minh họa, không phải schema bắt buộc của sản phẩm cụ thể.

Không phải hệ thống nào cũng có đủ mọi trường. Trường không được hỗ trợ phải được thể hiện rõ là thiếu hoặc không áp dụng; không tự điền “MFA=true”, địa chỉ máy người dùng hay danh tính người khởi tạo khi không có bằng chứng.

### 4.2. Danh tính phải đủ bền để điều tra về sau

Display name và email có thể đổi; tài khoản có thể bị xóa. Vì vậy, nên giữ định danh chủ thể ổn định cùng một snapshot thích hợp của tên hiển thị tại thời điểm sự kiện.

Trong môi trường nhiều tenant hoặc nhiều miền định danh, `subject_id=1042` chưa chắc duy nhất. Cần kèm issuer hoặc namespace của danh tính và tenant liên quan.

Với automation, phân biệt:

- API client thực sự gọi PAM.
- Pipeline hoặc job tạo yêu cầu.
- Người khởi chạy hoặc phê duyệt nếu được hệ thống nguồn ghi nhận đáng tin cậy.
- Danh tính hiệu lực mà PAM dùng để ra quyết định.

Không chấp nhận một HTTP header do client tự gửi như bằng chứng chắc chắn về “người đứng sau”. Danh tính đại diện cần được ràng buộc bằng cơ chế xác thực và ủy quyền phù hợp.

### 4.3. Thành công ở tầng HTTP chưa chắc là thay đổi đã có hiệu lực

Một API có thể tiếp nhận yêu cầu rồi đưa vào hàng đợi. Việc trả kết quả “accepted” không chứng minh policy đã được áp dụng.

Có thể tách chuỗi trạng thái như sau:

~~~text
Yêu cầu được tiếp nhận
        |
        v
Kiểm tra quyền và điều kiện
        |
        +---- bị từ chối ----> DENIED
        |
        v
Chờ phê duyệt / chờ thực thi
        |
        +---- lỗi -----------> FAILED
        |
        v
Thay đổi được commit -------> APPLIED
        |
        v
Phân phối tới các node -----> DEPLOYMENT_COMPLETED / PARTIAL / FAILED
~~~

Tên trạng thái tùy thiết kế. Điều cốt lõi là không gộp “yêu cầu hợp lệ”, “đã commit” và “mọi node đã sử dụng cấu hình mới” thành một kết quả duy nhất khi chúng thực sự là các bước khác nhau.

Nếu một lần cập nhật hàng loạt chỉ thành công cho một phần đối tượng, log cần phản ánh kết quả từng phần hoặc tham chiếu một báo cáo chi tiết được bảo vệ tương ứng.

## 5. Ví dụ sự kiện thay đổi policy

Giả sử policy `policy-prod-ssh` được sửa để giảm thời hạn quyền JIT từ 60 phút xuống 30 phút. Giá trị thời hạn không phải bí mật nên có thể ghi chênh lệch trực tiếp.

~~~json
{
  "schema_version": "1",
  "event_id": "evt-7c1b9f23",
  "event_type": "pam.admin.policy.change.applied",
  "occurred_at": "2026-11-20T03:15:08.210Z",
  "source": {
    "instance_id": "pam-control-02",
    "epoch": "boot-31",
    "sequence": 48291
  },
  "actor": {
    "type": "human",
    "issuer": "identity-example",
    "subject_id": "user-184",
    "display_name": "quantri.a",
    "session_id": "admin-session-8f2",
    "effective_role": "policy-editor"
  },
  "channel": "admin-api",
  "auth_context": {
    "assurance": "step-up-verified",
    "authentication_event_id": "auth-64e"
  },
  "resource": {
    "type": "access-policy",
    "id": "policy-prod-ssh",
    "scope": "production/linux"
  },
  "action": "update",
  "change": {
    "previous_revision": 17,
    "effective_revision": 18,
    "changed_fields": [
      "jit.maximum_duration_minutes"
    ],
    "safe_diff": {
      "jit.maximum_duration_minutes": {
        "before": 60,
        "after": 30
      }
    }
  },
  "outcome": "APPLIED",
  "request_id": "req-3e1",
  "change_id": "change-826",
  "approval_id": "approval-551"
}
~~~

Địa chỉ nguồn, thời điểm collector nhận và nhãn tuyến thu thập có thể được bổ sung trong envelope tại nơi tiếp nhận. Cần phân biệt trường do ứng dụng gốc phát với trường do collector bổ sung.

Bản ghi trên hữu ích vì có thể nối với:

- Sự kiện xác thực `auth-64e`.
- Yêu cầu thay đổi `change-826`.
- Quyết định phê duyệt `approval-551`.
- Policy revision 17 và 18.
- Sự kiện phân phối revision 18 đến các node.
- Phiên quản trị phát sinh sau khi revision mới có hiệu lực.

Một `approval_id` tồn tại trong JSON chưa đủ chứng minh thay đổi đã được phê duyệt đúng. Cần kiểm tra bản phê duyệt đó gắn với đúng nội dung, phạm vi và phiên bản thay đổi; không phải một ticket bất kỳ được nhập vào ô lý do.

### 5.1. Khi thay đổi liên quan bí mật

Ví dụ đổi credential của một connector chỉ nên chứa metadata an toàn:

~~~json
{
  "event_type": "pam.admin.connector.credential.changed",
  "resource": {
    "type": "connector",
    "id": "connector-inventory-03"
  },
  "change": {
    "changed_fields": [
      "authentication.credential_reference"
    ],
    "secret_material_logged": false,
    "credential_version_after": "credential-version-12"
  },
  "outcome": "APPLIED"
}
~~~

Đây là phần nội dung minh họa đã lược các trường envelope, không phải một sự kiện hoàn chỉnh thay thế schema ở trên.

Không ghi password cũ/mới, bearer token, cookie phiên, private key, mã phục hồi hoặc payload yêu cầu thô. Cũng không mặc định băm mật khẩu rồi ghi vào log là an toàn: dữ liệu dẫn xuất vẫn có thể gây rủi ro và thường không cần thiết cho mục tiêu audit.

Với đối tượng cấu hình chứa cả dữ liệu công khai lẫn bí mật, nên dùng danh sách trường được phép ghi. Việc che chuỗi có tên “password” đơn thuần có thể bỏ sót bí mật nằm trong URL, header hoặc trường có tên khác.

## 6. Ghi thay đổi đủ rõ mà không biến log thành kho dữ liệu nhạy cảm

### 6.1. Lưu chênh lệch có kiểm soát

“Updated configuration” thường quá ít thông tin. Lưu toàn bộ request body lại thường quá nhiều.

Một cách thiết kế thực dụng là:

1. Xác định loại đối tượng và các trường cấu hình được phép xuất hiện trong log.
2. Ghi tên trường thay đổi, revision trước/sau và chênh lệch an toàn.
3. Với trường bí mật, chỉ ghi việc đã thay đổi cùng tham chiếu phiên bản nếu phù hợp.
4. Nếu cần snapshot đầy đủ phục vụ phục hồi, lưu ở kho riêng được bảo vệ và chỉ tham chiếu trong log.

Phải bảo vệ cả giá trị trước và sau. Một credential đã bị thay vẫn có thể có giá trị ở nơi khác hoặc trong một khoảng thời gian chuyển tiếp.

### 6.2. Ràng buộc thay đổi với phê duyệt

Một chuỗi đáng tin cậy cần liên kết được:

~~~text
Nội dung thay đổi được đề nghị
            |
            v
Phiên bản / dấu vết nội dung được phê duyệt
            |
            v
Danh tính người phê duyệt và quyết định
            |
            v
Thao tác áp dụng đúng nội dung đó
            |
            v
Revision có hiệu lực và kết quả phân phối
~~~

Nếu người thực hiện sửa payload sau phê duyệt, hệ thống phải phát hiện sự khác biệt hoặc yêu cầu phê duyệt lại theo policy. Log cần giúp phân biệt “đã có ticket” với “đúng thay đổi này đã được duyệt”.

Với thay đổi khẩn cấp, bằng chứng có thể theo quy trình break-glass riêng: lý do, người kích hoạt, phạm vi, thời gian hết hạn và hậu kiểm. Không tạo bản ghi phê duyệt giả để làm cho quy trình khẩn cấp trông giống quy trình thông thường.

### 6.3. Bảo vệ định dạng log

Tên đối tượng, lý do thay đổi và thông điệp lỗi có thể chứa dữ liệu do người dùng cung cấp. Nếu đưa thẳng vào log dạng dòng, ký tự xuống dòng hoặc dấu phân cách có thể khiến một yêu cầu trông như nhiều sự kiện.

Dùng serializer có cấu trúc, escape dữ liệu đúng định dạng, giới hạn độ dài trường và đánh dấu rõ việc cắt bớt. Không cắt mất `event_id`, danh tính hay kết quả mà vẫn xem sự kiện là đầy đủ.

Thông báo lỗi cần đủ để điều tra nhưng không xuất stack trace, connection string hoặc credential vào luồng audit phổ biến một cách tùy tiện. Chi tiết chẩn đoán nếu cần có thể thuộc log vận hành với quyền truy cập khác.

## 7. Thu thập log theo hướng khó bị admin PAM tự che dấu

Một tuyến thu thập có thể được tổ chức như sau:

~~~mermaid
flowchart LR
    A[Console / API / automation] --> B[PAM control plane]
    B --> C[Audit event và hàng đợi bền vững]
    C --> D[Collector hoặc tuyến chuyển tiếp]
    D --> E[Kho audit tách quyền quản trị]
    E --> F[Chỉ mục tìm kiếm / SIEM]
    E --> G[Gói bằng chứng điều tra]
    B --> H[Giám sát sức khỏe audit]
    D --> H
    E --> H
    H --> I[Cảnh báo vận hành và an ninh]
~~~

Sơ đồ này mô tả mục tiêu kiến trúc, không mặc định mọi PAM đều triển khai theo cấu trúc đó.

### 7.1. Ghi nhận sự kiện gắn với thay đổi

Nếu ứng dụng sửa policy thành công rồi mới “cố gắng ghi log”, một lỗi tiến trình giữa hai bước có thể làm mất bằng chứng.

Tùy khả năng nền tảng, cần thiết kế để thay đổi và việc tạo dấu vết audit có ràng buộc đáng tin cậy, chẳng hạn lưu một audit record hoặc outbox bền vững cùng giao dịch của thay đổi, rồi chuyển tiếp độc lập. Với hệ phân tán, các bước ngoài cùng giao dịch vẫn cần trạng thái và cơ chế đối soát riêng.

Không mặc định cứ đặt log statement ngay sau câu lệnh cập nhật là đã bảo đảm audit.

### 7.2. Tách quyền quản trị nguồn phát và kho bằng chứng

Một mô hình phân quyền có thể gồm:

| Vai trò | Quyền phù hợp | Giới hạn cần xem xét |
|---|---|---|
| Admin vận hành PAM | Quản lý cấu hình PAM trong phạm vi được giao | Không tự xóa bằng chứng ở kho độc lập |
| Audit writer | Gửi sự kiện vào tuyến thu thập | Không sửa hoặc truy vấn tùy ý log đã lưu |
| Người vận hành logging | Quản lý collector và lưu trữ | Không tự cấp quyền truy cập production qua PAM |
| Auditor / điều tra viên | Đọc, tìm kiếm, xuất dữ liệu theo phạm vi | Không sửa policy hay nội dung log |
| Người phê duyệt thay đổi nhạy cảm | Phê duyệt theo phân công | Tránh tự duyệt thay đổi của chính mình khi policy yêu cầu tách nhiệm vụ |

Đây là mô hình mục tiêu. Quyền root, quyền quản trị cloud hoặc quyền với khóa mã hóa vẫn có thể ảnh hưởng bằng chứng. Phải đánh giá các đường quản trị thực tế, thay vì kết luận log an toàn chỉ vì giao diện PAM không có nút “delete”.

### 7.3. Tính toàn vẹn không đồng nghĩa tính đầy đủ

Append-only, khóa lưu trữ, chữ ký hay chuỗi băm có thể hỗ trợ phát hiện hoặc hạn chế thay đổi sau khi ghi, tùy cách triển khai. Nhưng một chuỗi log còn nguyên vẹn không chứng minh rằng mọi sự kiện đáng lẽ phải phát ra đều đã được tạo.

Cần phân biệt bốn thuộc tính:

- **Đầy đủ:** hoạt động thuộc phạm vi audit có được tạo sự kiện và chuyển tới đích hay không.
- **Toàn vẹn:** dữ liệu đã lưu có bị sửa hoặc xóa ngoài quy trình hay không.
- **Nguồn gốc:** có căn cứ xác định sự kiện đến từ thành phần nào.
- **Khả dụng:** khi điều tra có tìm, đọc và xuất được bằng chứng hay không.

Một file hash lưu ngay cạnh file log mà cùng một admin có thể thay cả hai chỉ cung cấp bảo vệ hạn chế. Nếu dùng chữ ký hoặc dấu kiểm chứng, việc giữ khóa, lưu checkpoint và phân tách quyền xác minh đều thuộc thiết kế.

Ngay cả cơ chế kiểm chứng tốt cũng không bảo đảm nội dung nguồn phát là đúng khi chính nguồn phát đã bị chiếm quyền. Vì vậy cần đối chiếu với log định danh, log hạ tầng và hệ thống đích.

### 7.4. Chống mất log và quản lý bản sao

Tuyến chuyển tiếp có thể retry và gửi lại cùng sự kiện. Giữ `event_id` ổn định qua các lần gửi giúp bên nhận nhận diện bản sao. Không tạo một sự kiện nghiệp vụ mới cho mỗi lần retry rồi đếm nhầm thành nhiều lần thay đổi policy.

Nếu dùng sequence, cần hiểu phạm vi của nó: theo node, stream, partition hay epoch khởi động. Không so sánh hai sequence của hai nguồn độc lập rồi kết luận mất log.

Một khoảng trống sequence là tín hiệu cần đối soát, không phải tự động chứng minh có kẻ xóa log. Nguyên nhân còn có thể là tuyến lọc, nguồn khởi động lại hoặc cách cấp sequence của nền tảng.

## 8. Khi logging lỗi, PAM phải làm gì?

Không có một đáp án chung “luôn dừng tất cả” hoặc “luôn tiếp tục”. Quyết định phải gắn với mức rủi ro của thao tác và tính sẵn sàng cần bảo vệ.

Phân biệt ít nhất hai tình huống:

1. Không gửi được ngay tới SIEM nhưng PAM vẫn ghi bền vững và hàng đợi còn dung lượng.
2. Không thể tạo hoặc lưu bền vững audit record tại nguồn.

Hai tình huống này có mức mất bằng chứng khác nhau.

Một policy minh họa:

| Tình trạng | Hướng xử lý minh họa |
|---|---|
| Đích SIEM chậm, hàng đợi bền vững bình thường | Tiếp tục theo policy, cảnh báo độ trễ, retry có kiểm soát |
| Hàng đợi gần đầy | Cảnh báo sớm, ưu tiên khôi phục tuyến, hạn chế thao tác admin theo ngưỡng đã quy định |
| Không lưu được audit của thay đổi có rủi ro cao | Chặn thay đổi theo policy hoặc dùng quy trình khẩn cấp được định nghĩa trước |
| Tuyến audit bị tắt trái phép | Cảnh báo qua kênh độc lập và điều tra |
| Cần phục hồi logging trong sự cố | Dùng runbook khôi phục và ghi bằng chứng độc lập để tránh vòng phụ thuộc |

Policy chỉ hữu ích nếu người vận hành biết nó trước sự cố và đã thử nghiệm trong môi trường phù hợp.

Một thay đổi làm tắt audit không nên chỉ được ghi vào chính tuyến audit vừa bị tắt. Cần có bằng chứng và tín hiệu độc lập: giám sát cấu hình từ bên ngoài, trạng thái tuyến chuyển tiếp hoặc sự kiện trên hạ tầng liên quan.

Các chỉ số nên theo dõi gồm độ trễ chuyển tiếp, tuổi sự kiện chưa gửi lâu nhất, dung lượng hàng đợi, số lần lỗi, sự kiện bị loại và tình trạng xác minh toàn vẹn. Heartbeat đơn thuần chỉ chứng minh một thành phần còn gửi heartbeat; nó không chứng minh đường audit nghiệp vụ đang đầy đủ.

## 9. Thời gian, phiên bản và điều tra chuỗi hành động

### 9.1. Giữ cả thời gian nguồn và thời gian nhận

`occurred_at` và `received_at` phục vụ hai mục đích khác nhau:

- Thời gian nguồn mô tả thời điểm sự kiện được nguồn ghi nhận.
- Thời gian nhận cho biết khi nào bằng chứng tới một điểm thu thập.

Nên dùng định dạng có múi giờ rõ ràng, thường chuẩn hóa UTC khi lưu, rồi hiển thị theo nhu cầu người dùng. Khi có sai lệch đồng hồ hoặc collector nhận muộn, cần giữ thông tin đó thay vì lặng lẽ sửa dấu thời gian gốc.

Chỉ sắp xếp theo timestamp có thể dẫn đến kết luận sai về thứ tự, đặc biệt trong cụm nhiều node. Kết hợp `request_id`, revision, sequence có phạm vi rõ ràng và mối liên hệ giữa các sự kiện.

### 9.2. Giữ phiên bản policy có hiệu lực

Khi điều tra một phiên truy cập hôm qua, policy hiện tại không nhất thiết giống policy lúc phiên bắt đầu.

Cần nối được phiên hoặc quyết định cấp quyền với revision có hiệu lực khi ra quyết định. Nếu có thay đổi giữa phiên, xác định policy sản phẩm áp dụng cho phiên đang chạy theo cơ chế nào và kiểm tra sự kiện thu hồi hay cập nhật tương ứng.

Không kết luận truy cập “đúng policy” chỉ vì đem phiên cũ so với cấu hình đang thấy hôm nay.

### 9.3. Restore cũng có thể làm thay đổi cách đọc bằng chứng

Khôi phục PAM từ backup có thể đưa cấu hình về revision cũ hoặc thay đổi chuỗi định danh cục bộ. Cần sự kiện restore, nguồn backup, phạm vi khôi phục và định danh epoch thích hợp.

Log đã chuyển tới kho độc lập cần được bảo toàn khi khôi phục PAM. Không dùng việc rollback cấu hình làm lý do xóa dấu vết các thay đổi đã xảy ra sau bản backup.

## 10. Phát hiện từ log admin

Không nên chỉ cảnh báo mọi thao tác admin. Cần nhận diện những hành động hoặc tổ hợp hành động có ý nghĩa đối với cơ chế kiểm soát PAM.

### 10.1. Thay đổi làm suy yếu kiểm soát

Những ví dụ cần đánh giá theo ngữ cảnh:

- Tắt ghi phiên cho một nhóm tài nguyên nhạy cảm.
- Bỏ yêu cầu phê duyệt hoặc giảm mức xác thực cho quyền cao.
- Mở rộng phạm vi JEA hoặc tăng đáng kể thời hạn JIT.
- Cấp vai trò quản trị toàn cục cho tài khoản mới.
- Đổi đích gửi audit, giảm retention hoặc thay quyền xóa log.
- Tạo API client có quyền rộng và sử dụng ngay sau đó.

Một quy tắc minh họa bằng giả mã:

~~~text
KHI nhận sự kiện policy.change.applied:
    đọc chênh lệch an toàn và phạm vi tác động

    NẾU changed_fields chứa session.recording.required
       VÀ giá trị trước = true
       VÀ giá trị sau = false
       VÀ scope thuộc nhóm tài nguyên nhạy cảm:
        tạo tín hiệu điều tra
        đính kèm actor, change_id, approval_id,
                 previous_revision, effective_revision
~~~

Đây là logic minh họa, không phải cú pháp của một SIEM cụ thể. Cần xử lý trường thiếu: không có `safe_diff` không thể được coi là bằng chứng rằng giá trị không thay đổi.

### 10.2. Chuỗi thay đổi rồi truy cập

Một hành động riêng lẻ có thể hợp lệ nhưng chuỗi hành động tạo ra rủi ro cao:

~~~text
Cấp quyền sửa policy
    -> tắt yêu cầu phê duyệt cho nhóm production
    -> cấp quyền JIT
    -> mở phiên đặc quyền
    -> khôi phục policy ban đầu
~~~

Việc khôi phục policy không xóa tác động của khoảng thời gian ngoại lệ. Cảnh báo nên gắn actor, đối tượng, phạm vi và quan hệ ủy quyền; không chỉ so trùng username.

Ví dụ, người sửa policy là một pipeline nhưng người khởi chạy pipeline lại là người mở phiên. Chỉ so sánh `actor.subject_id` của hai sự kiện có thể bỏ sót quan hệ đó. Nếu hệ thống không có bằng chứng về người khởi chạy, phải thể hiện giới hạn này thay vì suy đoán.

### 10.3. Hoạt động thất bại cũng có giá trị

Nhiều yêu cầu gán vai trò quản trị bị từ chối có thể cho thấy tài khoản hiểu sai quyền, automation lỗi hoặc hành vi dò quyền.

Có thể tổng hợp theo chủ thể, loại thao tác và phạm vi trong một cửa sổ thời gian. Tuy nhiên, giới hạn hoặc tổng hợp sự kiện để tránh quá tải phải được thiết kế cẩn thận: giữ được số lượng, khoảng thời gian, tiêu chí gộp và dữ liệu cần điều tra; không âm thầm loại bỏ toàn bộ lần từ chối.

### 10.4. Ngoại lệ hợp lệ không nên thành điểm mù

Một thay đổi có ticket và nằm trong maintenance window có thể làm giảm mức ưu tiên, nhưng không tự động trở thành vô hại. Cần kiểm tra đúng phạm vi, người thực hiện, nội dung và thời hạn đã được duyệt.

Ngoại lệ nên có chủ sở hữu và thời gian hết hạn. Không bỏ cảnh báo vô thời hạn cho toàn bộ hoạt động của tài khoản admin chỉ vì tài khoản đó thường xuyên thực hiện thay đổi.

## 11. Tình huống thực tế: phiên hợp lệ sau một thay đổi nguy hiểm

Một công ty dùng PAM để cấp quyền SSH tạm thời vào máy chủ production. Policy ban đầu yêu cầu người quản lý phê duyệt và ghi phiên.

Ngày minh họa, các sự kiện thu được như sau:

| Thời điểm UTC | Sự kiện | Điều cần kiểm chứng |
|---|---|---|
| 09:00 | `user-184` kích hoạt quyền policy editor | Ai duyệt, phạm vi và thời hạn quyền này? |
| 09:03 | Policy revision 42 bỏ yêu cầu phê duyệt | Có được duyệt đúng nội dung hay không? |
| 09:04 | Revision 42 được áp dụng tới broker liên quan | Node nào đã có hiệu lực? |
| 09:06 | `user-184` nhận quyền JIT cho nhóm production | Quyết định dùng revision nào? |
| 09:07 | Phiên SSH mở qua PAM | Phiên nối tới tài khoản và máy chủ nào? |
| 09:12 | Policy được đổi về yêu cầu phê duyệt | Chỉ thay cấu hình hay cũng thu hồi quyền đã cấp? |

Một cách điều tra:

1. Bảo toàn bản ghi admin, xác thực, cấp quyền và phiên trong khoảng thời gian liên quan.
2. Kiểm tra nguồn gốc, độ trễ và dấu hiệu thiếu sự kiện của từng tuyến.
3. Xác định quyền policy editor đến từ gán trực tiếp, nhóm định danh hay JIT.
4. Đối chiếu revision 41, 42 và revision khôi phục, tập trung vào chênh lệch có tác động.
5. Đối chiếu phê duyệt với đúng payload của revision 42.
6. Nối quyết định cấp quyền và phiên SSH với policy thực sự được sử dụng.
7. Kiểm tra credential, entitlement hoặc phiên còn tồn tại sau khi policy được khôi phục.
8. Đối chiếu log hệ thống đích để xác định hoạt động đã thực thi và tác động thực tế.

Không nên kết luận chỉ từ log “session started successfully”. Kết quả đó cho biết cơ chế truy cập đã chấp nhận phiên, không chứng minh việc thay đổi cơ chế chấp nhận là hợp lệ.

Cũng không nên kết luận người dùng đã gây hại chỉ vì chuỗi sự kiện đáng ngờ. Log tạo căn cứ điều tra; kết luận cần dựa trên phê duyệt, bối cảnh khẩn cấp, hoạt động trong phiên và bằng chứng tại hệ thống đích.

## 12. Lưu giữ, truy cập và xuất bằng chứng

### 12.1. Chọn thời hạn dựa trên nhu cầu thực tế

Không áp dụng một con số retention tùy ý cho mọi loại log. Thời hạn cần đáp ứng nhu cầu điều tra, vòng đời thay đổi, khả năng phát hiện muộn, yêu cầu nội bộ và các nghĩa vụ áp dụng cho tổ chức.

Có thể phân tầng:

- Dữ liệu tra cứu nhanh phục vụ vận hành và cảnh báo.
- Bản lưu dài hạn để đối chiếu và điều tra.
- Gói bằng chứng được bảo toàn cho một vụ việc cụ thể.

Phải rõ dữ liệu nào là bản gốc, dữ liệu nào đã chuẩn hóa hoặc rút gọn. Một dashboard đếm số sự kiện không thay thế bản ghi chi tiết khi cần chứng minh ai đã thay đổi policy nào.

### 12.2. Quyền đọc audit cũng là quyền nhạy cảm

Kiểm soát theo vai trò và phạm vi: người phụ trách một tenant không mặc nhiên xem audit của tenant khác. Khi cần truy cập rộng để điều tra, có thể cấp tạm thời theo quy trình phù hợp và ghi lại việc sử dụng.

Những thao tác xuất hàng loạt, thay đổi quyền truy cập và xóa theo quy trình cần có dấu vết. Không để người quản trị ứng dụng tự xóa cả log về hành động xóa dữ liệu của chính họ.

### 12.3. Gói bằng chứng cần giữ ngữ cảnh

Một gói xuất phục vụ điều tra nên ghi nhận:

- Phạm vi nguồn và khoảng thời gian truy xuất, bao gồm múi giờ.
- Điều kiện tìm kiếm, bộ lọc và các giới hạn đã biết.
- Số lượng bản ghi, phiên bản schema và cách chuẩn hóa.
- Bản dữ liệu gốc hoặc tham chiếu đáng tin cậy tới dữ liệu gốc.
- Hash hoặc thông tin kiểm chứng của các file xuất.
- Người xuất, thời điểm xuất, mục đích và nơi lưu được kiểm soát.
- Các lần chuyển giao và xử lý tiếp theo của gói bằng chứng.

Hash giúp phát hiện thay đổi của một file so với giá trị đã ghi nhận. Nó không tự chứng minh rằng truy vấn xuất đã lấy đủ dữ liệu, rằng thời gian nguồn chính xác hay rằng nội dung ban đầu đúng sự thật.

Nếu phải che dữ liệu khi chia sẻ, giữ bản gốc được bảo vệ và ghi rõ bản chia sẻ đã biến đổi những gì. Không gọi bản đã cắt bớt trường là “nguyên bản”.

## 13. Bài thực hành với dữ liệu tổng hợp

Thực hành trên môi trường thử nghiệm hoặc bộ sự kiện giả lập; không tắt logging hay giảm kiểm soát production để tạo dữ liệu học tập.

### 13.1. Chuẩn bị tình huống

Giả sử có các đối tượng sau:

- Hai danh tính: `user-policy-01` và `user-approve-02`.
- Một automation identity: `svc-policy-deploy`.
- Policy `policy-lab-linux`, revision ban đầu là 10.
- Một tuyến thu thập có thông tin thời gian nguồn, thời gian nhận và định danh sự kiện.
- Một kho bằng chứng mà admin PAM không có quyền sửa dữ liệu đã nhận qua giao diện quản trị PAM.

Tạo chuỗi dữ liệu giả lập:

| STT | Sự kiện | Kết quả |
|---|---|---|
| 1 | Người dùng đề nghị giảm JIT từ 60 xuống 30 phút | Yêu cầu được tạo |
| 2 | Người khác phê duyệt đúng payload | Phê duyệt hợp lệ |
| 3 | Automation áp dụng revision 11 | APPLIED |
| 4 | Thử bỏ yêu cầu ghi phiên nhưng thiếu quyền | DENIED |
| 5 | Gửi lại sự kiện số 3 do collector retry | Cùng `event_id` |
| 6 | Đổi đích chuyển tiếp log theo yêu cầu thử nghiệm | Có dấu vết thay đổi cấu hình |
| 7 | Một sự kiện đến muộn do tuyến bị gián đoạn | `received_at` muộn hơn đáng kể |
| 8 | Cấp entitlement theo revision 11 | Tham chiếu đúng revision |

### 13.2. Nhiệm vụ

1. Tìm tất cả thay đổi admin đã áp dụng, tách khỏi yêu cầu đang chờ và yêu cầu bị từ chối.
2. Nối sự kiện áp dụng revision 11 với người đề nghị, người phê duyệt và automation thực thi.
3. Nhận diện bản sao của sự kiện số 3 mà vẫn giữ khả năng truy nguyên lần chuyển tiếp.
4. Phát hiện thao tác thử tắt ghi phiên dù nó không thành công.
5. Tính độ trễ của sự kiện đến muộn theo hai trường thời gian.
6. Xác định sự kiện nào tác động đến chính khả năng thu thập audit.
7. Kiểm tra dữ liệu không có password, token, cookie hoặc payload bí mật.
8. Xuất một gói bằng chứng nhỏ, ghi lại bộ lọc và giới hạn dữ liệu.

### 13.3. Kết quả mong đợi

Người học phải phân biệt được:

- **Người đề nghị**, **người duyệt** và **chủ thể thực thi** là ba vai trò khác nhau.
- Một yêu cầu `DENIED` không làm thay đổi policy nhưng vẫn có ý nghĩa an ninh.
- Hai bản chuyển tiếp có cùng `event_id` không mặc nhiên là hai thay đổi nghiệp vụ.
- Đến muộn không đồng nghĩa xảy ra muộn.
- Một thay đổi tuyến gửi log phải được theo dõi ngay cả khi thay đổi đó có phê duyệt.
- Thiếu trường phê duyệt hay revision cần được ghi nhận là giới hạn bằng chứng; không tự điền giả.

Nếu thử nghiệm sự cố thu thập trong lab, cần quan sát hành vi thực tế của hàng đợi, cảnh báo và policy xử lý lỗi. Không đánh dấu “audit đầy đủ” chỉ vì sau sự cố vẫn nhìn thấy một vài bản ghi.

## 14. Những lỗi thiết kế thường gặp

| Lỗi | Hệ quả | Cách cải thiện |
|---|---|---|
| Chỉ ghi đăng nhập admin | Không biết admin thay đổi gì | Ghi hành động và đối tượng chịu tác động |
| Chỉ ghi “configuration updated” | Khó xác định tác động | Ghi changed fields, revision và diff an toàn |
| Lưu request body nguyên vẹn | Có thể lộ bí mật và dữ liệu nhạy cảm | Dùng schema audit với trường được phép ghi |
| Lấy tên hiển thị làm định danh duy nhất | Khó truy nguồn sau đổi tên hoặc xóa tài khoản | Giữ ID và namespace ổn định |
| Xem HTTP accepted là APPLIED | Kết luận sai về thay đổi thực tế | Ghi các trạng thái xử lý và kết quả cuối |
| Cùng một admin kiểm soát PAM và mọi bản log | Có khả năng che dấu dấu vết | Tách quyền và kho bằng chứng theo kiến trúc thực tế |
| Gửi log ra ngoài nhưng không giám sát hàng đợi | Mất log hoặc phát hiện rất muộn | Theo dõi độ trễ, dung lượng và lỗi chuyển tiếp |
| Chỉ dựa vào hash để khẳng định log đầy đủ | Bỏ sót sự kiện chưa từng được phát | Đối soát tuyến, nguồn và dữ liệu độc lập |
| Dùng policy hiện tại để xét phiên cũ | Đánh giá sai quyền tại thời điểm truy cập | Giữ revision có hiệu lực và liên kết quyết định |
| Bỏ cảnh báo cho mọi thay đổi có ticket | Ngoại lệ trở thành điểm mù | Xác minh đúng nội dung, phạm vi và thời hạn |
| Chỉ audit console, bỏ API và bảo trì | Có đường quản trị thiếu bằng chứng | Kiểm kê toàn bộ đường thay đổi được hỗ trợ |
| Tắt audit để sửa tuyến audit mà không có runbook | Mất bằng chứng trong lúc phục hồi | Chuẩn bị kênh ghi nhận độc lập và đối soát sau sự cố |

## 15. Câu hỏi tự kiểm tra

**1. Có log phiên SSH đầy đủ rồi thì cần log admin PAM nữa để làm gì?**

Log phiên cho biết hoạt động trong phiên. Log admin giải thích vì sao phiên được cho phép, ai đã thay đổi policy, quyền hay yêu cầu ghi nhận trước đó. Hai nhóm bằng chứng trả lời các câu hỏi khác nhau.

**2. Một thay đổi có `approval_id` có chắc đã được duyệt hợp lệ không?**

Không. Phải đối chiếu bản phê duyệt với đúng nội dung, phạm vi, người duyệt và thời điểm áp dụng. Một ID được nhập tự do không tự chứng minh quan hệ đó.

**3. Có nên ghi cả mật khẩu cũ và mới để chứng minh rotation thành công?**

Không. Ghi định danh credential, phiên bản, kết quả rotation và sự kiện xác minh liên quan theo khả năng nền tảng. Không đưa giá trị bí mật vào log.

**4. Kho log append-only có chứng minh không mất sự kiện không?**

Không. Nó liên quan đến cách bảo vệ dữ liệu sau khi ghi. Tính đầy đủ cần được đánh giá bằng phạm vi phát sự kiện, tuyến chuyển tiếp, đối soát và giám sát sức khỏe audit.

**5. SIEM mất kết nối có luôn buộc dừng mọi thay đổi admin không?**

Không có quy tắc chung cho mọi hệ thống. Cần biết nguồn còn ghi bền vững hay không, mức rủi ro của thay đổi, dung lượng hàng đợi và policy đã được phê duyệt. Mất điểm lưu audit tại nguồn nghiêm trọng hơn việc đích phân tích tạm thời chưa nhận dữ liệu.

**6. Policy được khôi phục về cấu hình ban đầu có chứng minh sự cố đã kết thúc không?**

Không. Quyền đã cấp, credential đã phát hoặc phiên đang chạy có thể cần xử lý riêng. Phải kiểm tra thu hồi và tác động còn lại theo cơ chế thực tế.

**7. Điều gì làm một log admin PAM thực sự hữu ích?**

Có thể nối được danh tính, quyền tại thời điểm hành động, nội dung thay đổi, phê duyệt, revision có hiệu lực và kết quả thực tế; đồng thời có căn cứ về nguồn gốc, tính toàn vẹn, tính đầy đủ và giới hạn của bằng chứng.

Log admin của PAM cần giúp người đọc dựng lại cách các cơ chế đặc quyền đã thay đổi. Khi nó được liên kết với log xác thực, cấp quyền, phiên và hệ thống đích, tổ chức mới có cơ sở đánh giá cả hoạt động sử dụng quyền lẫn người đã thay đổi luật sử dụng quyền đó.
