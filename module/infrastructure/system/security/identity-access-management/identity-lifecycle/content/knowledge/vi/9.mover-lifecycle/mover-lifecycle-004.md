# Thay đổi manager trong Mover lifecycle: cập nhật tuyến quản lý và kiểm soát truy cập IAM

Trong **Identity and Access Management (IAM)**, nhân viên có thể chuyển sang báo cáo cho một người quản lý khác mà vẫn giữ nguyên hợp đồng lao động, tài khoản đăng nhập và thậm chí chức danh. Dù vậy, trường **manager** (người quản lý trực tiếp) thường ảnh hưởng tới tuyến phê duyệt yêu cầu truy cập, trách nhiệm rà soát quyền, phạm vi dữ liệu nhân viên mà người quản lý được xem và các quy trình ủy quyền. Nếu IAM chỉ đổi tên manager trong hồ sơ mà không kiểm tra các tác động liên quan, người quản lý cũ có thể tiếp tục phê duyệt hoặc xem dữ liệu không còn thuộc trách nhiệm của họ.

Bài này thuộc chương **Mover lifecycle** của mô-đun **SECURITY_IDENTITY_ACCESS_MANAGEMENT_IDENTITY_LIFECYCLE**, học về vòng đời danh tính **Joiner–Mover–Leaver (JML)**: xác minh người dùng, tạo tài khoản, cấp quyền, cập nhật khi thay đổi vai trò và thu hồi truy cập. Chủ đề trực tiếp là **thay đổi manager** trong giai đoạn *Mover*; các thành phần liên quan gồm nguồn dữ liệu nhân sự (**HRIS**), **IdP**, **SSO**, **SCIM**, chính sách **RBAC/ABAC**, tài khoản dịch vụ, truy vết kiểm toán và kiểm soát quyền truy cập tồn dư.

Sau bài học, người học có thể:

- Giải thích thay đổi manager có ý nghĩa gì và phân biệt nó với chuyển phòng ban, đổi chức danh hay thay đổi vai trò cấp quyền.
- Mô hình hóa quan hệ **nhân viên → manager** bằng định danh ổn định, nguồn có thẩm quyền và thời điểm hiệu lực.
- Thiết kế luồng xử lý một sự kiện thay đổi manager từ HRIS qua IAM/IGA, IdP và các ứng dụng SCIM.
- Đánh giá tác động đến **phê duyệt**, **quyền xem dữ liệu cấp dưới**, **rà soát truy cập** và các ủy quyền tồn tại từ trước.
- Xử lý ngoại lệ như manager chưa có tài khoản, tạm quyền, nghỉ việc, thay đổi tương lai, dữ liệu đến sai thứ tự hoặc chu trình quản lý sai.
- Đặt các bước xác minh kết quả, kiểm toán và chỉ số để tránh quyền cũ còn hiệu lực ngoài ý muốn.

## 1. Thay đổi manager trong IAM là gì?

**Manager change** là sự kiện nguồn có thẩm quyền xác nhận một chủ thể (thường là Employee hoặc Contractor) bắt đầu được quản lý bởi một người hoặc vị trí quản lý khác theo thời điểm quy định. Ví dụ, nhân viên An trước đây báo cáo cho chị Mai, từ ngày 01/12 chuyển sang báo cáo cho anh Bình.

Đây là một dạng **Mover** vì quan hệ và thuộc tính của danh tính đang thay đổi. Tuy nhiên, thay manager **không mặc nhiên đồng nghĩa**:

- Nhân viên được chuyển phòng ban hoặc thay đổi chức danh.
- Nhân viên phải có tài khoản IdP mới.
- Người quản lý mới được tự động cấp mọi quyền đối với tài khoản và dữ liệu của cấp dưới.
- Các phê duyệt cũ phải được hủy hoặc chấp thuận lại trong mọi trường hợp.
- Người quản lý cũ bị thu hồi tất cả quyền của họ; thông thường chỉ cần thu hồi những quyền phát sinh từ **quan hệ quản lý đã kết thúc**, theo chính sách.

Một hệ thống IAM tốt phải phân biệt **thông tin nhân sự** với **quyết định truy cập**: giá trị \`managerSubjectId\` chỉ thể hiện liên kết được xác minh; quyền và trách nhiệm được tính riêng từ chính sách đang có hiệu lực.

### Phân biệt những khái niệm gần nhau

| Khái niệm | Câu hỏi trả lời | Ví dụ |
| --- | --- | --- |
| **Direct manager / line manager** | Ai chịu trách nhiệm quản lý trực tiếp nhân viên theo nguồn nhân sự? | An → Bình. |
| **Functional/project manager** | Ai quản lý chuyên môn hoặc dự án cụ thể? | An vẫn làm dự án do Mai phụ trách. |
| **Approver** | Ai có thẩm quyền phê duyệt một loại yêu cầu cụ thể? | Người quản lý trực tiếp duyệt quyền cơ bản; chủ dữ liệu duyệt quyền nhạy cảm. |
| **Role owner / application owner** | Ai quản trị hoặc chịu trách nhiệm một role/ứng dụng? | Owner của ứng dụng kế toán. |
| **IAM role** | Tập quyền người dùng được cấp theo mô hình RBAC. | \`finance-reader\`. |
| **Access reviewer** | Ai có trách nhiệm xác nhận quyền còn cần thiết? | Bình rà soát quyền của An trong kỳ mới. |
| **Delegate** | Ai được ủy quyền hành động thay một người trong phạm vi và thời hạn xác định? | Một trưởng nhóm được Bình ủy quyền duyệt lúc Bình nghỉ phép. |

Các vai trò trên có thể do cùng một người đảm nhiệm nhưng **không được tự động coi là đồng nhất**. Chẳng hạn, HRIS đổi direct manager của An từ Mai sang Bình chưa chắc làm Bình trở thành owner của mọi hệ thống mà An sử dụng.

## 2. Tại sao một thay đổi manager phải được IAM xử lý?

Quan hệ manager thường tham gia nhiều quy trình:

| Hệ thống/nghiệp vụ | Tác động có thể có | Điểm kiểm soát |
| --- | --- | --- |
| **HRIS / sơ đồ tổ chức** | Cập nhật tuyến báo cáo và người chịu trách nhiệm. | Nguồn dữ liệu đúng, không có manager tự quản lý chính mình. |
| **IGA / yêu cầu truy cập** | Định tuyến phê duyệt yêu cầu mới hoặc chuyển giao các yêu cầu đang chờ. | Quy tắc ai được duyệt, thay đổi có hiệu lực lúc nào. |
| **Access recertification** | Người rà soát quyền của nhân viên được thay đổi. | Chuyển ownership đợt rà soát đúng quy trình, giữ lịch sử. |
| **IdP / Directory** | Cập nhật thuộc tính manager, tổ chức hoặc nhóm động có liên quan. | Không biến thuộc tính mới thành quyền quá mức. |
| **Ứng dụng SaaS qua SCIM** | Đồng bộ quan hệ manager cho ứng dụng hỗ trợ. | Ánh xạ đúng ID người quản lý tại đích; theo dõi lỗi và đọc lại. |
| **SSO / OIDC / SAML** | Ứng dụng có thể sử dụng claim manager hoặc dữ liệu tổ chức. | Chú ý token và phiên chứa giá trị cũ. |
| **RBAC / ABAC** | Quyền dựa trên cấp dưới, phạm vi phòng ban hoặc cấp quản lý có thể đổi. | Tính hiệu lực mới, loại bỏ quyền được suy ra từ quan hệ cũ. |
| **Tài khoản dịch vụ / owner** | Manager có thể tham gia tuyến phê duyệt thay owner hoặc xác nhận trách nhiệm. | Ownership dịch vụ là quan hệ riêng, cần quy tắc chuyển giao rõ ràng. |

**Ví dụ rủi ro:** một ứng dụng nhân sự cho phép manager xem hồ sơ của các direct report. Sau khi An chuyển sang Bình, ứng dụng vẫn giữ quan hệ cũ và Mai tiếp tục xem hồ sơ An. IdP có thể đã cập nhật manager đúng, nhưng **quyền tại ứng dụng đích chưa được điều chỉnh**; đây là quyền truy cập tồn dư cần phát hiện bằng đối soát.

## 3. Mô hình dữ liệu cho quan hệ manager

### 3.1. Định danh đúng người quản lý

Không nên lưu quan hệ manager bằng **họ tên**, **email** hoặc **tên đăng nhập** làm khóa chính, vì chúng có thể trùng, đổi tên hoặc được tái sử dụng. Thay vào đó, lưu tham chiếu ổn định tới danh tính manager, kết hợp ID nguồn đủ để kiểm chứng.

Một hồ sơ nội bộ minh họa:

~~~json
{
  "subjectId": "person-1420",
  "engagementId": "EMP-6104",
  "workerType": "EMPLOYEE",
  "departmentId": "OPERATIONS",
  "jobCode": "ANALYST",
  "managerSubjectId": "person-2088",
  "managerSourceRecordId": "HR-MGR-772",
  "managerRelationshipEffectiveAt": "2026-12-01T08:00:00+07:00",
  "managerRelationshipVersion": 16,
  "sourceSystem": "HRIS"
}
~~~

Trong mô hình này, \`subjectId\` chỉ danh tính An, \`managerSubjectId\` chỉ danh tính Bình, còn \`managerSourceRecordId\` giúp truy ngược quan hệ/ID manager do HRIS cung cấp. Các trường là **mô hình ví dụ**, không phải tên trường bắt buộc trong một chuẩn IAM.

**Một người có thể có nhiều quan hệ công việc** (Employee, Contractor, vị trí kiêm nhiệm). Cần xác định trường manager áp dụng cho **person** hay **engagement** nào; khi hai quan hệ đồng thời có manager khác nhau, mô hình một trường \`managerSubjectId\` duy nhất cho toàn bộ person có thể không đủ.

### 3.2. Những thành phần của quan hệ cần ghi nhận

| Thành phần | Tác dụng |
| --- | --- |
| **Subject ID** | Ai được đổi tuyến quản lý. |
| **Engagement / position ID** | Quan hệ lao động hoặc vị trí nào bị ảnh hưởng. |
| **Previous manager ID** | Căn cứ kiểm tra chuyển giao và thu hồi quyền cũ. |
| **New manager ID** | Người quản lý mới đã được xác minh. |
| **Effective at / effective date** | Thời điểm quan hệ mới có hiệu lực theo quy tắc nghiệp vụ. |
| **Source system, event ID, record version** | Kiểm soát sự kiện tin cậy, lặp hoặc đến sai thứ tự. |
| **Relationship type** | Phân biệt direct manager, project manager, temporary approver. |
| **Approval/exception reference** | Theo dõi trường hợp thay đổi nhạy cảm hoặc ngoài quy trình thông thường. |

Trong các hệ thống khác nhau, “manager” có thể biểu diễn **người** hoặc **vị trí quản lý**. Nếu HRIS quản lý theo position ID, IAM phải giải quyết vị trí đó tới đúng người đang đảm nhiệm tại thời điểm hiệu lực; không giả định vị trí luôn có một nhân sự cố định.

### 3.3. Ràng buộc dữ liệu và đồ thị tổ chức

Quan hệ quản lý có thể được mô hình hóa thành đồ thị có hướng:

~~~mermaid
flowchart TD
    CEO["Giám đốc: Lan"] --> M1["Manager: Mai"]
    CEO --> M2["Manager: Bình"]
    M1 -. "Trước 01/12" .-> E["Employee: An"]
    M2 == "Từ 01/12" ==> E
~~~

Nên kiểm tra tối thiểu:

1. **Manager tồn tại và được xác minh:** ID manager giải quyết được tới đúng chủ thể hoặc vị trí hợp lệ.
2. **Không tự quản lý:** \`subjectId != managerSubjectId\` trừ khi schema dành riêng cho tình huống khác có quy định rõ.
3. **Không tạo chu trình trái chính sách:** An → Bình → An là một chu trình quản lý trực tiếp không hợp lệ trong cấu trúc cấp bậc thông thường.
4. **Trạng thái quản lý phù hợp:** manager không phải người đã nghỉ hoặc mất thẩm quyền, trừ quan hệ tạm thời được chính sách cho phép.
5. **Phạm vi tổ chức hợp lệ:** nếu chính sách hạn chế quản lý chéo pháp nhân/đơn vị, phải có phê duyệt hoặc ngoại lệ.
6. **Đúng thời điểm:** dùng quan hệ có hiệu lực tại thời điểm ra quyết định, không luôn lấy phiên bản “mới nhất đã gửi”.

Với **quản lý ma trận** hoặc **đa tuyến**, phải có nhiều loại quan hệ rõ ràng, mỗi loại gắn với quy tắc phê duyệt/quyền riêng. Không ép một project manager thành direct manager chỉ vì ứng dụng đích chỉ hỗ trợ một trường \`manager\`.

## 4. Nguồn có thẩm quyền và chuỗi xử lý Mover

Đối với nhân viên, **HRIS thường là nguồn có thẩm quyền** cho direct manager. Đối với nhà thầu, nguồn có thể là hệ thống quản lý hợp đồng hoặc sponsor. Đối với ủy quyền phê duyệt, nguồn có thể là hệ thống workflow do bộ phận quản trị danh tính sở hữu. **Không đồng nhất quyền cập nhật tất cả loại quan hệ**.

~~~mermaid
flowchart LR
    HR["HRIS<br/>Thay đổi manager + hiệu lực"] -->|"Sự kiện có phiên bản"| IGA["IGA / Lifecycle workflow"]
    IGA -->|"Kiểm tra identity, quan hệ,<br/>policy và lịch hiệu lực"| DEC["Đánh giá tác động"]
    DEC -->|"Manager attribute"| IDP["IdP / Directory"]
    DEC -->|"SCIM / API"| APPS["Ứng dụng đích"]
    DEC -->|"Đổi tuyến phê duyệt"| FLOW["Workflow + recertification"]
    DEC -->|"Tính lại quyền"| PAM["RBAC / ABAC / PAM"]
    IDP --> AUD["Audit + reconciliation"]
    APPS --> AUD
    FLOW --> AUD
    PAM --> AUD
    AUD -->|"Lỗi/chênh lệch"| IGA
~~~

Quy trình đề xuất:

1. **Tiếp nhận:** xác thực nguồn sự kiện, mã hồ sơ, loại quan hệ, manager cũ/mới, ngày hiệu lực và phiên bản bản ghi.
2. **Giải quyết danh tính:** ánh xạ ID nhân viên và manager nguồn tới danh tính chuẩn; kiểm tra manager tồn tại, đúng người, hợp lệ theo thời điểm.
3. **Kiểm tra ràng buộc:** xác định có chu trình, tự quản lý, trùng liên kết, xung đột quan hệ hoặc thiếu dữ liệu không.
4. **Lên lịch hiệu lực:** nếu thay đổi có hiệu lực trong tương lai, ghi trạng thái chờ, chuẩn bị tác vụ nhưng chưa áp dụng quyền sớm.
5. **Đánh giá tác động:** xác định các workflow phê duyệt, quyền manager, scope dữ liệu, rà soát truy cập và nhóm/quyền liên quan.
6. **Áp dụng thay đổi có kiểm soát:** cập nhật IdP/directory, đồng bộ ứng dụng, chuyển các trách nhiệm cần thiết, cấp/thu hồi quyền theo chính sách.
7. **Xác minh:** đọc lại manager và entitlement tại hệ thống đích, rà soát yêu cầu phê duyệt đang chờ và quyền cũ có còn hiệu lực không.
8. **Lưu bằng chứng:** liên kết HRIS event → quyết định → lệnh → kết quả từng hệ thống; mở ngoại lệ có owner khi chưa hoàn tất.

**Đích đến của quy trình không chỉ là “trường manager đã đổi” mà là “mọi quyền và trách nhiệm phụ thuộc manager được xử lý nhất quán”.**

## 5. Quy tắc hiệu lực và cập nhật đúng thời điểm

### 5.1. Ngày nghiệp vụ khác timestamp kỹ thuật

HRIS có thể gửi \`effectiveDate=2026-12-01\`. Đây là một **ngày lịch**, cần quy tắc để xác định thời điểm áp dụng tại môi trường nhiều múi giờ. Ví dụ, nếu chính sách quy định áp dụng lúc **08:00 ngày 01/12 theo Asia/Ho_Chi_Minh**, thời điểm tương ứng là **2026-12-01T01:00:00Z**. Không được mặc định mọi ngày nghiệp vụ tương ứng 00:00 UTC.

Nên ghi nhận:

- Ngày quan hệ có hiệu lực do HRIS xác nhận.
- Múi giờ hoặc chính sách quy đổi ngày thành instant.
- Thời điểm nguồn phát sự kiện, IAM nhận sự kiện và bắt đầu xử lý.
- Thời điểm các hệ thống đích thực sự xác nhận cập nhật.

Với ứng dụng ra quyết định quyền theo dữ liệu tổ chức, phải xác định **cách xử lý giai đoạn chuyển tiếp** để tránh cấp quyền mới trước hạn và bỏ sót thu hồi quyền cũ.

### 5.2. Sự kiện đến sớm, muộn, trùng hoặc bị sửa

| Trường hợp | Hậu quả nếu xử lý đơn giản | Kiểm soát |
| --- | --- | --- |
| Manager đổi có hiệu lực tuần sau. | Người quản lý mới xem dữ liệu trước ngày được giao. | Lưu phiên bản chờ, áp dụng quyền theo thời điểm hiệu lực. |
| Ngày hiệu lực bị hoãn. | Lịch cũ cập nhật manager và quyền quá sớm. | Hủy/vô hiệu lịch cũ, kiểm tra lại phiên bản lúc chạy. |
| Sự kiện mới đến trước sự kiện cũ. | Bản ghi cũ ghi đè manager mới. | Dùng phiên bản/chuỗi hiệu lực, chống sự kiện stale. |
| Cùng sự kiện được gửi lặp. | Tạo tác vụ/phê duyệt trùng, cấp quyền nhiều lần. | Xử lý idempotent theo event ID và business key. |
| HRIS sửa thông tin quá khứ. | Truy vết phê duyệt trong khoảng cũ trở nên khó hiểu. | Giữ lịch sử trước/sau và đánh giá tác động ở hiện tại. |
| Thay đổi manager bị hủy sau khi áp dụng. | Quyền cũ/mới không còn nhất quán. | Tính lại từ nguồn có thẩm quyền; thu hồi các quyền phát sinh trái chính sách. |

Đối với **sự kiện quá khứ** đến muộn, ngoài việc cập nhật trạng thái hiện tại, có thể cần kiểm tra ai đã phê duyệt hoặc truy cập dữ liệu trong khoảng thời gian quan hệ mới lẽ ra đã có hiệu lực.

## 6. Đồng bộ thuộc tính manager qua IdP và SCIM

### 6.1. IdP / Directory

IdP có thể lưu \`managerId\`, người quản lý trong directory hoặc một thuộc tính tùy chỉnh. Khi thay đổi, cần cập nhật bằng **định danh ổn định**, phù hợp schema và quyền chỉnh sửa của hệ thống. Nếu nhóm hoặc quyền được tính động dựa trên manager, phải đánh giá lại chứ không chỉ thay chuỗi hiển thị.

Ứng dụng dùng SSO (OIDC/SAML) có thể nhận quan hệ quản lý qua claim, nhưng claim đã phát hành trước đó có thể tồn tại trong **phiên hoặc token còn thời hạn**. Việc sửa thuộc tính trong IdP không tự xóa giá trị cũ khỏi token đã cấp. Với quyết định truy cập nhạy cảm, cần biện pháp kiểm tra trạng thái hiện tại, điều chỉnh thời hạn token, tái xác thực hoặc làm mất hiệu lực phiên khi hệ thống hỗ trợ.

### 6.2. SCIM Enterprise User extension

SCIM chuẩn hóa quản lý người dùng/nhóm giữa hệ thống cung cấp danh tính và ứng dụng. Trong **Enterprise User extension** của SCIM 2.0, thuộc tính \`manager\` có thể có \`value\`, \`$ref\` và \`displayName\`.

Ví dụ **biểu diễn khái niệm** trong tài nguyên SCIM User:

~~~json
{
  "schemas": [
    "urn:ietf:params:scim:schemas:core:2.0:User",
    "urn:ietf:params:scim:schemas:extension:enterprise:2.0:User"
  ],
  "userName": "an@example.test",
  "active": true,
  "urn:ietf:params:scim:schemas:extension:enterprise:2.0:User": {
    "department": "OPERATIONS",
    "manager": {
      "value": "scim-manager-id-2088",
      "displayName": "Bình"
    }
  }
}
~~~

Ở đây, \`manager.value\` biểu diễn **ID tài nguyên manager tại chính SCIM service provider đích**, không tự động là mã HRIS hay \`subjectId\` nội bộ. \`displayName\` chỉ để hiển thị và có thể thay đổi; không nên dùng làm khóa liên kết. Khi dùng \`$ref\`, phải cung cấp tham chiếu hợp lệ tới tài nguyên manager mà provider hỗ trợ.

Tùy ứng dụng, trường manager có thể không được hỗ trợ, không có quyền ghi hoặc được quản lý theo cơ chế riêng. Cần kiểm tra schema/khả năng của provider và hợp đồng tích hợp; **SCIM không bảo đảm tất cả ứng dụng đều hỗ trợ mọi thuộc tính**.

### 6.3. Manager chưa có tài khoản tại ứng dụng đích

Nếu An có tài khoản ở hệ thống ERP nhưng Bình chưa có, không thể tùy tiện ghi \`manager.value\` bằng ID nội bộ rồi coi là hợp lệ.

Quy trình phù hợp:

1. Kiểm tra ERP có yêu cầu manager là một SCIM User đã tồn tại không.
2. Nếu có, đối chiếu hoặc cấp tài khoản manager theo chính sách quyền tối thiểu, tránh tạo tài khoản chỉ để nhận quyền không cần thiết.
3. Nếu provider hỗ trợ trạng thái manager tạm trống, ghi nhận hàng đợi phụ thuộc và xử lý khi đã có liên kết hợp lệ.
4. Nếu không thể hoàn thành, tạo ngoại lệ có người phụ trách; không gán manager sai hoặc im lặng bỏ qua.
5. Đọc lại thuộc tính tại ứng dụng đích và đánh giá các luồng phê duyệt bị ảnh hưởng.

### 6.4. Phân biệt manager của HRIS với manager tài khoản

Một ứng dụng có thể coi trường manager chỉ là thông tin nhân sự hiển thị, trong khi một ứng dụng khác dùng nó để cho phép xem dữ liệu nhân viên. Cần quản lý bản đồ **thuộc tính → hành vi → quyền tại ứng dụng**. Cập nhật trường dữ liệu không chứng minh đã cấp/thu hồi đúng quyền, và phản hồi HTTP thành công không chứng minh token hoặc phiên cũ đã mất hiệu lực.

## 7. Thay đổi tuyến phê duyệt và yêu cầu đang chờ

Đây thường là tác động khó nhất vì thay manager xảy ra trong khi các workflow đã bắt đầu.

### 7.1. Yêu cầu mới

Với những yêu cầu truy cập phát sinh **sau thời điểm hiệu lực**, workflow nên xác định approver theo quan hệ manager mới nhất **có hiệu lực** cùng chính sách phê duyệt. Nếu quyền nhạy cảm yêu cầu owner ứng dụng, an ninh hoặc phê duyệt hai cấp thì thay manager không được bỏ qua các bước đó.

### 7.2. Yêu cầu đang chờ

Giả sử An gửi yêu cầu vào ngày 28/11 để truy cập báo cáo nhạy cảm; yêu cầu đang chờ Mai phê duyệt. Ngày 01/12, An chuyển sang báo cáo cho Bình. Có một số chính sách hợp lý:

| Chiến lược | Áp dụng khi | Rủi ro và kiểm soát |
| --- | --- | --- |
| **Chuyển sang manager mới** | Chính sách yêu cầu approver hiện tại tại thời điểm quyết định. | Cập nhật người nhận, thông báo rõ và ngăn Mai duyệt sau khi mất thẩm quyền. |
| **Giữ manager đã được chỉ định** | Quy trình được thiết kế giữ người chịu trách nhiệm lúc phát sinh, có căn cứ quản trị rõ ràng. | Đảm bảo người cũ vẫn được phép duyệt loại yêu cầu này và có thời hạn hợp lệ. |
| **Hủy và yêu cầu gửi lại** | Bối cảnh vai trò, mức rủi ro hoặc đơn vị đã thay đổi đáng kể. | Giải thích nguyên nhân, bảo lưu lịch sử, tránh làm mất tính liên tục không cần thiết. |
| **Đưa về nhóm giải quyết ngoại lệ** | Quan hệ mâu thuẫn, manager mới không đủ điều kiện hoặc thiếu dữ liệu. | Có người chịu trách nhiệm và hạn xử lý, không tự duyệt. |

Không có một chiến lược chung cho mọi workflow. Điều quan trọng là **chính sách được xác định trước**, lưu lịch sử phân công/phê duyệt và xử lý nhất quán với mức rủi ro.

### 7.3. Chống phê duyệt bằng thông tin đã cũ

Một yêu cầu có thể đang mở trong giao diện của Mai trước khi manager đổi. Nếu Mai nhấn “Approve” sau khi đã mất thẩm quyền, hệ thống phải **kiểm tra lại quyền phê duyệt tại thời điểm thực thi**, không chỉ tin vào tên approver đã hiển thị trước đó. Dùng version của workflow, trạng thái yêu cầu và cơ chế cập nhật nguyên tử để tránh một yêu cầu được hai người duyệt đồng thời hoặc bị áp dụng hai lần.

Phê duyệt **đã hoàn tất hợp lệ trước thời điểm đổi manager** không tự trở thành vô hiệu. Tuy vậy, quyền được cấp từ phê duyệt đó vẫn phải được rà soát nếu công việc hoặc phạm vi trách nhiệm của An thay đổi.

### 7.4. Rà soát quyền định kỳ

Trong kỳ **access recertification**, người quản lý có thể được giao xác nhận quyền cấp dưới còn cần hay không. Khi manager thay đổi:

- Các đợt rà soát mới phải chọn người chịu trách nhiệm theo quan hệ có hiệu lực.
- Các mục đang chờ cần áp dụng quy tắc chuyển giao hoặc giữ nguyên được phê duyệt.
- Quyết định trước đó cần giữ lại người thực hiện, thời gian và trạng thái phê duyệt.
- Nếu có người thay thế hoặc ủy quyền, phải có hạn, phạm vi và bằng chứng tương ứng.

Không nên bỏ qua các mục rà soát đang chờ chỉ vì danh sách cấp dưới của người quản lý đã thay đổi.

## 8. Tác động đến quyền truy cập: RBAC, ABAC và phạm vi cấp dưới

### 8.1. Không cấp quyền chỉ vì thuộc tính manager đổi

Theo **RBAC**, quyền thường gắn với vai trò IAM. Việc An đổi manager nhưng giữ nguyên công việc có thể không thay đổi nhóm quyền của An. Tuy nhiên, một số ứng dụng trao cho manager vai trò **people-manager**, quyền xem báo cáo trực tiếp hoặc phê duyệt nội dung; khi đó quyền của **Mai và Bình** có thể cần thay đổi.

Theo **ABAC**, một quyết định có thể xét quan hệ giữa người yêu cầu và chủ dữ liệu:

~~~text
ALLOW view_direct_report_profile if
    subject.lifecycleState == "ACTIVE"
    AND subject.hasCapability("view_direct_report_profile")
    AND resource.employee.managerSubjectId == subject.subjectId
    AND resource.classification <= subject.approvedScope
~~~

Đây là **giả mã chính sách minh họa**. Không phải tất cả manager đều có quyền xem toàn bộ hồ sơ cấp dưới; quyền phụ thuộc phân loại dữ liệu, pháp luật, vai trò, mục đích và phê duyệt.

### 8.2. Tính chênh lệch quyền trước/sau

Khi An chuyển từ Mai sang Bình:

| Đối tượng | Có thể thay đổi | Kiểm tra sau cập nhật |
| --- | --- | --- |
| **An** | Người duyệt quyền, tuyến thông báo hoặc chính sách phụ thuộc manager; quyền công việc có thể giữ nguyên. | Không bị cấp quyền thừa do hiểu sai sự kiện. |
| **Mai** | Mất phạm vi quản lý An, quyền xem dữ liệu An nếu quyền chỉ phát sinh từ quan hệ đó. | Không còn xem được tài nguyên chỉ dành cho manager hiện tại của An. |
| **Bình** | Nhận trách nhiệm/khả năng xem dữ liệu An theo chính sách, nhận phê duyệt mới. | Chỉ có quyền nằm trong phạm vi được duyệt, không tự nhận quyền admin của An. |
| **Người ủy quyền/approver thay thế** | Các delegation liên quan có thể cần sửa/hủy/giữ theo quy tắc. | Không còn ủy quyền tồn dư không hợp lệ. |

Nếu quyền được cấp thông qua **nhóm tĩnh** (ví dụ nhóm \`direct-reports-of-Mai\`), phải cập nhật membership. Nếu quyền được quyết định **động** từ quan hệ manager trong policy engine, phải đảm bảo thuộc tính được cập nhật và cache/token không giữ quan hệ cũ quá thời hạn cho phép.

### 8.3. Phân tách nhiệm vụ và đặc quyền

Không nên cho manager tự phê duyệt quyền quản trị của chính mình hoặc các quyền có xung đột nhiệm vụ nếu chính sách SoD cấm. Nếu Bình mới trở thành approver cho An nhưng Bình đồng thời là người yêu cầu hoặc người hưởng lợi từ thay đổi, cần tuyến phê duyệt thay thế.

Với quyền **PAM**, tài khoản quản trị và đặc quyền tạm thời phải theo cơ chế được thiết kế riêng. Quan hệ direct manager không tự động cho phép mượn tài khoản đặc quyền của cấp dưới, xem bí mật hoặc vô hiệu hóa MFA của người khác.

## 9. Các ngoại lệ quan trọng

### 9.1. Manager nghỉ việc hoặc mất hiệu lực cùng ngày

Nếu manager mới sắp nghỉ việc hoặc đã bị khóa, IAM phải kiểm tra **trạng thái có hiệu lực tại thời điểm chuyển**. Có thể cần người quản lý tạm thời theo HRIS hoặc tuyến approver dự phòng có phê duyệt. Không dùng một manager đã terminated để tự động phê duyệt các quyền mới.

### 9.2. Manager tạm thời và quyền ủy quyền

Một trưởng nhóm được giao quản lý thay trong hai tuần có thể chỉ cần quyền phê duyệt theo phạm vi/thời gian, không nhất thiết phải ghi đè direct manager chính thức trong HRIS. Nên mô hình hóa riêng:

- **Direct manager:** quan hệ lâu dài hoặc chính thức do HRIS xác nhận.
- **Acting manager:** nhiệm vụ quản lý tạm thời với ngày bắt đầu/kết thúc.
- **Delegated approver:** quyền phê duyệt một số loại yêu cầu theo ủy quyền có hiệu lực.

Khi hết hạn, tự thu hồi delegation và xác minh quyền cũ đã ngừng; giữ lịch sử để giải trình những quyết định được thực hiện hợp lệ trong thời gian ủy quyền.

### 9.3. Manager chưa xác định hoặc dữ liệu bị lỗi

\`managerId=null\` có thể nghĩa là đang khuyết manager, quan hệ đã được xóa hoặc dữ liệu chưa có, tùy hợp đồng dữ liệu. Phải phân biệt **trường vắng mặt trong PATCH**, **giá trị null rõ ràng** và **giá trị mã không tồn tại**. Với quan hệ thiết yếu để xác định approver, nên đưa yêu cầu vào hàng đợi có người chịu trách nhiệm theo chính sách thay vì tự gán manager cũ hoặc phê duyệt tự động.

### 9.4. Chuyển pháp nhân hoặc quản lý chéo đơn vị

Khi nhân viên đổi manager sang người thuộc pháp nhân hoặc phòng ban khác, một số dữ liệu có thể bị giới hạn theo ranh giới pháp lý hoặc hợp đồng. Kiểm tra chính sách về phạm vi truy cập và thẩm quyền phê duyệt; không suy rằng manager mới đương nhiên có quyền xem toàn bộ dữ liệu nhân sự của đơn vị cũ.

### 9.5. Một người có nhiều manager

Ma trận quản lý có thể gồm direct manager, project manager, dotted-line manager. Tùy ứng dụng, chỉ một quan hệ có thể được đồng bộ qua trường SCIM manager; các quan hệ khác cần schema hoặc dịch vụ chuyên biệt. Cần quyết định **loại quan hệ nào dùng cho loại phê duyệt nào**, tránh nhân bản cùng một thuộc tính cho mọi mục đích.

### 9.6. Tài khoản dịch vụ có owner liên quan manager

Một Employee thay manager không tự động làm owner của các tài khoản dịch vụ thay đổi. Nếu quy trình vận hành yêu cầu manager phê duyệt quyền cho service account do Employee chịu trách nhiệm, cần cập nhật tuyến phê duyệt và rà soát quyền theo chính sách. Danh tính **workload** phải có owner ứng dụng/nhóm rõ ràng; không nhầm manager của người sở hữu với chủ thể kỹ thuật đã truy cập.

## 10. Ví dụ xử lý sự kiện manager change

Một thông điệp minh họa từ HRIS:

~~~json
{
  "eventId": "hr-manager-20261130-052",
  "eventType": "MANAGER_CHANGED",
  "sourceSystem": "HRIS",
  "recordVersion": 16,
  "subjectSourceId": "EMP-6104",
  "previousManagerSourceId": "EMP-4021",
  "newManagerSourceId": "EMP-7720",
  "relationshipType": "DIRECT_MANAGER",
  "effectiveAt": "2026-12-01T08:00:00+07:00",
  "occurredAt": "2026-11-30T03:12:00Z"
}
~~~

Một luồng xử lý khái niệm:

~~~text
onTrustedManagerChange(event):
    verifyTrustedSourceAndSchema(event)
    if alreadyProcessed(event.eventId): return

    employee = resolveEmployee(event.subjectSourceId)
    newManager = resolveEmployee(event.newManagerSourceId)
    if employee is ambiguous or newManager is ambiguous:
        raiseManualVerificationCase(event)
        return

    if isStale(event.recordVersion, employee.managerRelationVersion):
        recordIgnoredStaleEvent(event)
        return

    if selfOrCycleOrUnauthorizedRelation(employee, newManager, event):
        quarantineWithReason(event)
        return

    saveScheduledRelationVersion(event, employee, newManager)
    invalidateSupersededSchedules(employee, "DIRECT_MANAGER")
    scheduleEffectiveChange(event.effectiveAt, event.recordVersion)

onManagerChangeDue(subjectId, scheduledVersion):
    relation = reloadAuthoritativeEffectiveRelation(subjectId)
    if relation.version != scheduledVersion: return
    if not allRelationConditionsSatisfied(relation):
        openExceptionAndHoldDependentActions(relation)
        return

    before = captureRelevantApproversAndEntitlements(relation.subject)
    updateCanonicalManagerRelation(relation)
    synchronizeIdpAndSupportedTargetApps(relation)
    recalculateAffectedPermissionsAndApproverRoutes(relation, before)
    enforcePolicyApprovalsAndApplyChanges()
    verifyManagerAttributesApprovalRoutesAndAccess(relation)
    recordPerTargetOutcomesAndOpenFailures(relation)
~~~

Đây là giả mã để giải thích luồng, không phải mã hoàn chỉnh. Khi triển khai thực tế cần cơ chế chống xử lý lặp ở mỗi ứng dụng, quy tắc thứ tự sự kiện, xử lý lỗi từng phần, chính sách quyền và chuyển giao workflow, retry an toàn và kiểm soát tác vụ chậm. **Một bước cập nhật thành công không chứng minh tất cả bước phụ thuộc đã hoàn tất**.

### 10.1. Tính an toàn khi cập nhật nhiều hệ thống

HRIS, IGA, IdP và SaaS thường **không cùng một giao dịch nguyên tử**. Vì vậy, có thể xảy ra:

- IdP đã ghi manager mới nhưng SaaS chưa nhận được bản cập nhật SCIM.
- SaaS đã gắn Bình làm manager, nhưng mục phê duyệt đang chờ vẫn nằm ở Mai.
- Workflow đổi approver nhưng quyền xem dữ liệu của Mai còn hiệu lực.
- IAM đã gửi lệnh thu hồi, song token/phiên ứng dụng vẫn cho phép truy cập.

Cần theo dõi **trạng thái từng mục tiêu**, retry đúng nghĩa, kiểm tra kết quả thực tế và tạo ngoại lệ có owner/hạn xử lý. Với hệ thống nhạy cảm, khi xuất hiện trạng thái không nhất quán cần có chính sách hạn chế truy cập tạm thời hoặc đường xử lý thủ công an toàn.

## 11. Truy vết và kiểm toán thay đổi manager

Một hồ sơ kiểm toán phải trả lời được: **Ai quản lý An ở một thời điểm cụ thể? Ai có quyền duyệt yêu cầu của An? Vì sao Mai còn hoặc không còn xem được dữ liệu An? Những hệ thống nào đã xác minh chuyển sang Bình?**

### Những bằng chứng cần có

| Bằng chứng | Nội dung | Mục đích |
| --- | --- | --- |
| **Sự kiện nguồn** | ID sự kiện HRIS, subject/engagement, manager cũ/mới, ngày hiệu lực, record version. | Xác nhận căn cứ có thẩm quyền. |
| **Xác minh danh tính** | Ánh xạ ID nguồn sang subjectId của employee và manager; kết quả kiểm tra chu trình. | Tránh liên kết nhầm người. |
| **Quyết định chính sách** | Policy ID, version, quyền và workflow bị ảnh hưởng, ngoại lệ/phê duyệt. | Giải thích nguyên nhân thay đổi quyền/trách nhiệm. |
| **Thực thi** | Tài khoản đích, request ID, lệnh SCIM/API, nhóm/role, người/tiến trình thực hiện. | Xác định hệ thống đã nhận lệnh gì. |
| **Kết quả xác minh** | Manager đọc lại tại đích, quyền trước/sau, tuyến phê duyệt đang hoạt động. | Chứng minh các thay đổi có hiệu lực. |
| **Xử lý lỗi và ngoại lệ** | Lỗi, người chịu trách nhiệm, số lần thử lại, hạn xử lý và trạng thái cuối. | Phát hiện và khép kín truy cập tồn dư. |

Nên liên kết các bước bằng \`traceId\` hoặc ID tương quan; nếu một ứng dụng không hỗ trợ ID xuyên hệ thống, lưu bảng đối chiếu giữa ID yêu cầu, tài khoản đích, thời điểm và phản hồi. Ghi **thời điểm xảy ra, thời điểm có hiệu lực và thời điểm xác minh** riêng biệt để dựng lại lịch sử.

Không lưu mật khẩu, mã MFA, access token, refresh token hay giấy tờ nhân sự vào log vận hành. Nhật ký phải có kiểm soát truy cập, khả năng chống sửa/xóa trái phép và thời hạn lưu theo chính sách bảo vệ dữ liệu. Đặc biệt, việc ghi “đã cập nhật manager” trong IdP **không đủ** để khẳng định quyền của manager cũ đã bị thu hồi ở mọi ứng dụng.

## 12. Tình huống tổng hợp: đổi manager giữa kỳ phê duyệt

**Bối cảnh:** An là nhân viên phòng Vận hành, trước ngày 01/12 báo cáo cho Mai. Theo HRIS, từ **08:00 ngày 01/12** An báo cáo cho Bình. Ứng dụng quản lý nhân sự cho phép manager xem một phần dữ liệu direct report; công cụ IGA dùng manager để định tuyến phê duyệt.

| Thời điểm (giả định, giờ Việt Nam) | Sự kiện | Điều cần kiểm soát |
| --- | --- | --- |
| **28/11 10:00** | An gửi yêu cầu truy cập báo cáo, đang chờ Mai duyệt. | Ghi người được chỉ định và phiên bản workflow. |
| **30/11 16:00** | HRIS phát sự kiện manager mới là Bình, hiệu lực 01/12 08:00. | Lưu phiên bản chờ, chưa tự cấp quyền xem dữ liệu An cho Bình. |
| **01/12 08:00** | IAM kích hoạt quan hệ mới. | Đổi tuyến yêu cầu mới, xử lý yêu cầu đang chờ theo chính sách. |
| **01/12 08:02** | IdP cập nhật manager của An. | Chưa kết luận ứng dụng SaaS đã đồng bộ. |
| **01/12 08:04** | SCIM tới ứng dụng HR trả lỗi tạm thời. | Mở trạng thái chưa xác nhận, retry và theo dõi quyền Mai còn có. |
| **01/12 08:15** | Lần retry thành công; đối soát xác nhận Bình là manager và quyền dựa vào quan hệ cũ đã bị bỏ. | Đóng tác vụ sau khi kiểm tra trạng thái thực tế. |

**Phân tích:**

1. **Yêu cầu ngày 28/11:** có thể chuyển sang Bình, giữ Mai hoặc gửi duyệt lại tùy chính sách. Nếu chính sách yêu cầu manager hiện tại, phải kiểm tra lại thẩm quyền lúc nhấn Approve, ngay cả khi giao diện cũ vẫn hiển thị Mai.
2. **Quyền xem dữ liệu An:** nếu phát sinh hoàn toàn từ quan hệ direct report, sau chuyển đổi Mai không nên còn quyền đó; Bình chỉ được xem các trường được chính sách cho phép.
3. **Độ trễ SCIM:** trong khoảng 08:04–08:15, không được coi sự kiện đã hoàn tất trên mọi đích. Có thể cần giảm quyền tạm thời theo rủi ro.
4. **Kiểm toán:** phải có hồ sơ HRIS, thời điểm hiệu lực, trạng thái lệnh, kết quả đọc lại ở SaaS và quyết định xử lý yêu cầu đang chờ.

Nếu Mai vẫn xem được tài liệu của An vào ngày hôm sau, cần điều tra quyền cấp trực tiếp, nhóm cũ, ứng dụng cục bộ, ủy quyền chưa hết hạn hoặc phiên/token còn hiệu lực, không chỉ kiểm tra \`managerSubjectId\` trong IdP.

## 13. Chỉ số đánh giá quy trình thay đổi manager

| Chỉ số | Cách đo gợi ý | Ý nghĩa |
| --- | --- | --- |
| **Tỷ lệ thay đổi manager xử lý đầy đủ** | Số sự kiện có quan hệ, tuyến phê duyệt và quyền liên quan được xác minh ở các hệ thống thuộc phạm vi ÷ tổng sự kiện. | Độ bao phủ của luồng Mover. |
| **Độ trễ cập nhật manager** | Khoảng từ thời điểm có hiệu lực tại nguồn đến lúc xác minh giá trị tại từng đích; có thể theo P95/P99. | Nhận diện ứng dụng cập nhật chậm. |
| **Số quyền còn tồn dư của manager cũ** | Quyền dựa vào quan hệ đã hết hiệu lực mà vẫn được xác nhận hoạt động. | Kiểm soát rủi ro xem dữ liệu trái phạm vi. |
| **Tỷ lệ yêu cầu đang chờ được xử lý đúng chính sách** | Workflow có tuyến approver đúng, lưu dấu chuyển giao hoặc ngoại lệ ÷ tổng workflow bị ảnh hưởng. | Tránh phê duyệt bởi người đã mất thẩm quyền. |
| **Tỷ lệ lỗi/ngoại lệ đồng bộ manager** | Tác vụ SCIM/API/workflow quá hạn hoặc chưa xác nhận ÷ tổng tác vụ cần xử lý. | Phát hiện lỗi tích hợp. |
| **Số quan hệ không hợp lệ** | Manager không tồn tại, tự quản lý, chu trình hoặc manager đã hết hiệu lực. | Theo dõi chất lượng HRIS và mapping danh tính. |
| **Tỷ lệ sự kiện có đủ audit trail** | Sự kiện có nguồn → kiểm tra → quyết định → thực thi → xác minh ÷ tổng sự kiện cần kiểm toán. | Bảo đảm khả năng giải trình. |

Ngưỡng đánh giá cần được thiết lập theo mức nhạy cảm của ứng dụng, tốc độ thay đổi tổ chức và chính sách doanh nghiệp. Chỉ số “API thành công” không thể thay thế chỉ số **quyền thực tế và workflow đã đúng**.

## 14. Checklist thiết kế xử lý manager change

1. Đã xác định **loại manager** nào được HRIS quản lý và loại nào thuộc dự án/ủy quyền chưa?
2. Quan hệ manager có dùng **định danh ổn định**, gắn đúng Employee/engagement và lưu ngày hiệu lực không?
3. Có kiểm tra manager tồn tại, trạng thái hợp lệ, tự quản lý, chu trình và ranh giới pháp nhân không?
4. Sự kiện đến sớm/muộn/lặp hoặc đổi lại ngày hiệu lực có được xử lý bằng version và lịch kiểm tra lại không?
5. Có xác định rõ quyền, dữ liệu cấp dưới, nhóm động, delegation và workflow phê duyệt nào **phụ thuộc quan hệ manager** không?
6. Các yêu cầu phê duyệt/recertification đang chờ có quy tắc chuyển giao và kiểm tra lại thẩm quyền khi bấm Approve không?
7. Thuộc tính manager ở IdP và SCIM có được ánh xạ đúng ID **manager tại hệ thống đích**, không dựa vào email hoặc tên hiển thị không?
8. Có kiểm tra nhóm/quyền của manager cũ được thu hồi đúng phạm vi và manager mới không nhận quyền quá mức không?
9. Có xử lý ứng dụng không hỗ trợ SCIM, token/phiên cũ, tài khoản cục bộ và lỗi đồng bộ từng phần không?
10. Có phân biệt manager trực tiếp với owner của ứng dụng/tài khoản dịch vụ và người phê duyệt đặc quyền không?
11. Có truy vết đầy đủ từ sự kiện HRIS đến quyết định, từng lệnh, quyền/workflow sau thay đổi và ngoại lệ chưa xử lý không?

**Ghi nhớ:** Thay đổi manager trong **Mover lifecycle** là cập nhật một **quan hệ có hiệu lực theo thời gian** giữa danh tính nhân viên và người quản lý, từ đó có thể phát sinh thay đổi về tuyến phê duyệt, phạm vi dữ liệu và quyền. IAM phải xác minh đúng chủ thể, đồng bộ IdP/ứng dụng, kiểm tra RBAC/ABAC và workflow, rồi **đối soát quyền thực tế** để tránh manager cũ giữ truy cập tồn dư. Mọi thay đổi cần có nguồn gốc, thời điểm và bằng chứng kiểm toán rõ ràng.
