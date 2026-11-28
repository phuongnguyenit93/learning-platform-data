# Entitlement theo resource trong PAM

## Mục tiêu bài học

Trong Privileged Access Management (PAM), một vai trò như “vận hành” hoặc “quản trị viên” chưa mô tả đủ quyền truy cập. Cần biết vai trò đó cho phép hành động gì, trên tài sản nào, trong môi trường nào và với những điều kiện nào.

**Entitlement theo resource** là quyền hoặc điều kiện được hưởng quyền gắn với một tài nguyên xác định hay một phạm vi tài nguyên được quản trị. Thiết kế này giúp tránh tình trạng một người cần bảo trì một dịch vụ nhưng được tiếp cận mọi máy chủ, credential hoặc dữ liệu trong cùng hệ thống PAM.

Sau bài học, bạn có thể:

- Mô hình hóa quyền bằng chủ thể, resource, hành động, phạm vi và điều kiện.
- Phân biệt eligibility, entitlement, grant đang hoạt động và quyền thực tế tại đích.
- Thiết kế định danh resource, quan hệ kế thừa và nhóm tài nguyên.
- Tách quyền xem, mở phiên, tiết lộ credential, luân chuyển và quản lý chính sách.
- Kiểm soát quyền hợp thành, thay đổi nhãn, cấp quyền JIT và thu hồi.
- Kiểm chứng quyền tại API, vault, session broker và hệ thống đích.

Tên tài sản, hành động, profile và mô hình dữ liệu trong bài là minh họa. Cần ánh xạ chúng sang cơ chế thực thi của hệ thống cụ thể trước khi triển khai.

## 1. Từ “ai có vai trò gì” đến “ai được làm gì trên đâu”

Giả sử Huy thuộc đội vận hành ứng dụng thanh toán. Huy cần đọc log và khởi động lại một dịch vụ trên máy `payments-app-02`.

Một quyền quá rộng có thể là:

> Thành viên đội vận hành được sử dụng mọi tài khoản quản trị sản xuất trong vault.

Một entitlement theo resource có thể mô tả:

> Huy đủ điều kiện yêu cầu profile bảo trì dịch vụ thanh toán trên tài sản có mã `asset-2041`. Mỗi lần sử dụng cần phê duyệt và grant có thời hạn. Profile chỉ cho đọc log liên quan và khởi động lại đúng dịch vụ.

Hai mô tả có thể cùng phục vụ nhu cầu ban đầu nhưng phạm vi ảnh hưởng rất khác nhau.

Một mô hình khái niệm:

```text
Chủ thể
  + hành động
  + resource/phạm vi resource
  + điều kiện
  + nguồn thẩm quyền và vòng đời
  = một quan hệ quyền cần được quản trị
```

Resource có thể là máy chủ, cơ sở dữ liệu, dịch vụ, tài khoản đặc quyền, secret trong vault, thiết bị mạng hoặc một đối tượng quản trị của chính PAM.

Cần xác định resource ở mức đủ chi tiết cho công việc. Quyền trên một máy chủ không nên vô tình bao gồm mọi dịch vụ chạy trên đó nếu chính sách muốn tách chúng.

## 2. Thuật ngữ và vòng đời quyền

Cách dùng từ entitlement khác nhau giữa các sản phẩm. Trong bài này, cần phân biệt rõ các trạng thái sau:

| Khái niệm | Ý nghĩa trong thiết kế |
|---|---|
| Eligibility | Chủ thể đủ điều kiện yêu cầu hoặc kích hoạt một loại quyền |
| Entitlement được khai báo | Quan hệ quyền được chính sách hoặc cấu hình ghi nhận cho chủ thể và resource |
| Grant đang hoạt động | Lần cấp quyền cụ thể đang có hiệu lực trong thời gian và phạm vi xác định |
| Quyền thực tế | Khả năng thực hiện thao tác tại các điểm thực thi và hệ thống đích |
| Quyền tồn dư | Khả năng vẫn còn sau khi lẽ ra quyền phải kết thúc |

Eligibility không đồng nghĩa được truy cập ngay. Một thành viên đội vận hành có thể được yêu cầu bảo trì nhưng vẫn phải chờ phê duyệt và đáp ứng điều kiện xác thực.

Ngược lại, một người có thể không còn eligibility trong PAM nhưng vẫn giữ quyền trực tiếp tại hệ thống đích do một thay đổi thủ công chưa được gỡ. Vì vậy, cấu hình PAM và quyền thực tế phải được đối soát.

### Ví dụ

```text
Thuộc nhóm vận hành thanh toán
    -> Đủ điều kiện yêu cầu bảo trì payments-app-02
    -> Có yêu cầu đúng phạm vi được duyệt
    -> Kích hoạt grant 30 phút
    -> Mở phiên với profile hạn chế
    -> Hết hạn hoặc hoàn tất
    -> Gỡ quyền tạm và xác minh
```

Nếu chỉ cấu hình bước đầu rồi cấp sẵn tài khoản quản trị không hết hạn, đó không phải cùng mức kiểm soát với chuỗi trên.

## 3. Mô hình hóa resource và định danh

### 3.1. Định danh ổn định và đủ miền

Tên hiển thị như `db-01` có thể xuất hiện ở nhiều môi trường hoặc được tái sử dụng. Một địa chỉ IP cũng có thể đổi hoặc được gán cho tài sản khác.

Một resource nên có định danh ổn định trong miền quản trị, cùng các thuộc tính phục vụ quyết định:

- Tổ chức hoặc tenant.
- Loại tài sản.
- Môi trường như sản xuất hoặc thử nghiệm.
- Dịch vụ, đơn vị và chủ sở hữu.
- Vùng hoặc phạm vi hạ tầng cần phân biệt.
- Mức độ nhạy cảm và trạng thái vòng đời.
- Đích thực thi tương ứng, với ánh xạ được quản lý.

Ví dụ:

```yaml
resource:
  id: asset-2041
  tenant_id: organization-01
  type: application_host
  display_name: payments-app-02
  environment: production
  service_id: service-payments
  owner_group_id: group-payments-owners
  lifecycle_status: active
  target_binding_reference: target-binding-773
```

Định danh chỉ là căn cứ tham chiếu. Hệ thống vẫn phải xác minh resource thuộc đúng tenant và người dùng có quyền trên resource đó.

Nếu một máy bị hủy rồi máy mới được tạo lại với cùng tên, cần có quy tắc rõ về định danh và việc tái áp dụng entitlement. Không tự chuyển quyền sang tài sản mới chỉ vì chuỗi tên giống nhau.

### 3.2. Tài sản đích, tài khoản và secret là những đối tượng khác nhau

Một máy chủ có thể liên quan đến nhiều tài khoản; một tài khoản có thể được dùng trên nhiều máy; một secret có thể cho phép truy cập nhiều dịch vụ.

```text
Máy chủ A ---- tài khoản quản trị A ---- secret A
Máy chủ B ---- tài khoản quản trị B ---- secret B

Hoặc một thiết kế có rủi ro rộng hơn:

Máy chủ A ---+
            +---- tài khoản dùng chung ---- một secret
Máy chủ B ---+
```

Nếu người dùng được phép xem secret dùng chung, họ có thể có khả năng truy cập cả A và B, dù giao diện PAM chỉ hiển thị A.

Do đó, entitlement trên secret phải được đánh giá theo phạm vi hiệu lực thực sự của credential. Cần tách tài khoản hoặc hạn chế đường sử dụng khi mục tiêu là giới hạn từng resource.

Giữ bí mật trong vault và thiết lập phiên thay vì tiết lộ có thể giảm rủi ro sao chép credential, nhưng vẫn cần kiểm tra quyền của tài khoản đích và các đường truy cập khác.

## 4. Tách hành động thay vì cấp một quyền “access” chung

Một resource có thể có nhiều hành động với tác động khác nhau.

| Hành động minh họa | Khả năng được cấp |
|---|---|
| `view_metadata` | Xem thông tin tài sản được phép |
| `request_access` | Gửi yêu cầu sử dụng một profile |
| `open_session` | Mở phiên qua cơ chế được kiểm soát |
| `reveal_secret` | Hiển thị hoặc nhận giá trị credential |
| `rotate_secret` | Yêu cầu đổi credential |
| `restart_service` | Thực hiện thao tác hạn chế trên dịch vụ |
| `edit_access_policy` | Sửa quy tắc quyền trên resource |
| `grant_access` | Cấp hoặc thay đổi quyền cho người khác |
| `view_session_evidence` | Xem log hoặc bản ghi phiên liên quan |

Không suy luận rằng người được mở phiên cũng được xem mật khẩu, hoặc người dùng được dùng secret cũng được luân chuyển nó.

Luân chuyển credential có thể ảnh hưởng ứng dụng phụ thuộc. Đó là một quyền vận hành có tác động, cần phạm vi và quy trình phù hợp.

Quyền sửa policy hoặc cấp quyền cho người khác có thể mạnh hơn quyền sử dụng tài sản, vì nó cho phép thay đổi ai được truy cập và trong điều kiện nào. Cần bảo vệ những quyền quản trị này riêng.

### 4.1. Profile kỹ thuật phải khớp hành động

Một profile tên `service-restart-limited` chỉ có giá trị nếu cơ chế thực thi thực sự hạn chế đúng dịch vụ.

Nếu PAM mở một shell quản trị toàn máy rồi giao diện chỉ ghi “khởi động lại dịch vụ”, phạm vi thực tế vẫn quá rộng.

Một số công cụ hoặc lệnh được cho phép có thể mở chương trình khác, thay tệp thực thi hoặc tạo đường nâng quyền. Cần kiểm chứng hành động có thể thực hiện, không chỉ tên vai trò.

### 4.2. Không cấp quyền xem bằng chứng một cách mặc định

Bản ghi phiên có thể chứa bí mật hoặc dữ liệu nhạy cảm. Người được quản trị máy chủ không mặc nhiên cần quyền xem bản ghi của mọi người trên máy đó.

Tách quyền sử dụng tài sản, giám sát và quản trị bằng chứng theo trách nhiệm của tổ chức.

## 5. Chọn phạm vi resource: trực tiếp, nhóm hay kế thừa

### 5.1. Cấp trực tiếp cho từng resource

Cách này dễ giải thích: principal hoặc nhóm được gắn với một tài sản cụ thể.

Ưu điểm là phạm vi rõ. Hạn chế là số lượng cấu hình có thể lớn nếu hạ tầng thay đổi thường xuyên.

Cần có quy trình cho tài sản mới, chuyển chủ sở hữu và ngừng hoạt động. Nếu không, quyền trực tiếp có thể tích lũy thành các ngoại lệ khó quản lý.

### 5.2. Nhóm tài nguyên

Có thể gom tài sản theo dịch vụ hoặc một tiêu chí được quản trị. Ví dụ nhóm máy ứng dụng của dịch vụ thanh toán.

Cần phân biệt hai mô hình:

- **Tập tĩnh:** entitlement áp dụng cho danh sách resource xác định.
- **Tập động:** entitlement áp dụng cho những resource thỏa điều kiện tại thời điểm đánh giá.

Với tập động, việc thêm tài sản hoặc đổi nhãn có thể cấp thêm quyền mà không sửa entitlement. Vì vậy, ai có thể chỉnh thành viên hoặc nhãn cũng đang kiểm soát một phần phạm vi quyền.

Không để chủ thể tự gắn nhãn “thuộc đội tôi” lên một tài sản rồi nhận đặc quyền trên tài sản đó.

### 5.3. Kế thừa theo cây tài nguyên

Ví dụ:

```text
Tổ chức
└── Sản xuất
    ├── Dịch vụ thanh toán
    │   ├── payments-app-01
    │   └── payments-app-02
    └── Dịch vụ báo cáo
        └── reports-app-01
```

Một entitlement tại nút “Sản xuất” có thể tác động rộng hơn nhiều so với nút “Dịch vụ thanh toán”, nếu mô hình có kế thừa.

Phải nói rõ:

- Những hành động nào được kế thừa.
- Resource con nào nằm trong phạm vi.
- Quyền trực tiếp và quyền kế thừa được kết hợp thế nào.
- Quy tắc từ chối hoặc ngoại lệ có hiệu lực ra sao.
- Thêm resource mới vào cây có tự mang quyền xuống không.

Không phải sản phẩm nào cũng có cùng quy tắc ưu tiên. Cần kiểm tra hành vi thực tế, không giả định một lệnh “deny” luôn thắng mọi nguồn quyền.

### 5.4. Phê duyệt tập tĩnh hay cho phép phạm vi động?

Một chủ sở hữu có thể duyệt đúng ba máy cho một lần bảo trì. Nếu đến lúc kích hoạt, nhóm động đã tăng thành năm máy, không nên mặc định hai máy mới thuộc quyết định cũ.

Có thể chọn một trong những thiết kế phù hợp với mục tiêu:

- Chụp danh sách tài sản ở thời điểm phê duyệt cho công việc cụ thể.
- Cho phép phạm vi động được định nghĩa rõ, với quy trình kiểm soát thay đổi thành viên.
- Yêu cầu đánh giá hoặc phê duyệt bổ sung khi phạm vi thay đổi.

Điều quan trọng là người phê duyệt và cơ chế thực thi hiểu cùng một phạm vi.

## 6. Mẫu entitlement và grant có thời hạn

### 6.1. Entitlement về điều kiện yêu cầu

```yaml
entitlement:
  id: ENT-304
  subject:
    type: governed_group
    id: group-payments-operators
  tenant_id: organization-01
  resource_scope:
    type: explicit_resources
    resource_ids:
      - asset-2041
  eligibility:
    actions:
      - request_access
    requested_profile: service-restart-limited
  activation_requirements:
    approval_policy: production-maintenance
    authentication_profile: privileged-human-strong
    managed_device_required: true
    maximum_duration_minutes: 30
  owner_reference: group-payments-owners
  status: active
```

Mẫu này không cấp ngay quyền khởi động lại. Nó mô tả ai được yêu cầu loại quyền đó và điều kiện để kích hoạt.

### 6.2. Grant cho một lần sử dụng

```yaml
grant:
  id: GRANT-615
  entitlement_reference: ENT-304
  beneficiary_id: person-041
  tenant_id: organization-01
  resource_id: asset-2041
  effective_profile: service-restart-limited
  approval_reference: APPROVAL-442
  request_reference: REQ-510
  request_version: 2
  starts_at: "2026-12-06T20:00:00+07:00"
  ends_at: "2026-12-06T20:30:00+07:00"
  access_path: controlled_session
  credential_disclosure: false
  status: active
```

Đây là dữ liệu minh họa, không phải schema sản phẩm. Thời lượng 30 phút là giả định của tình huống.

Grant cần được ràng buộc với chủ thể, resource, profile và lần yêu cầu. Khi đổi resource hoặc mở rộng quyền, phải đánh giá lại theo chính sách; không tái sử dụng một quyết định cũ ngoài phạm vi.

Cũng cần xử lý việc entitlement nguồn bị rút trong lúc grant đang hoạt động. Chính sách phải xác định hiệu lực với grant hiện hữu và cơ chế thu hồi tương ứng.

## 7. Tính quyền có hiệu lực từ nhiều nguồn

Một người có thể nhận quyền trực tiếp, qua nhóm, qua vai trò kế thừa, grant JIT và quyền có sẵn tại hệ thống đích.

Nếu chỉ nhìn một entitlement riêng lẻ, bạn có thể bỏ sót quyền hợp thành:

- Một nhóm cho phép đọc secret.
- Một nhóm khác cho phép mở đường kết nối trực tiếp.
- Kết hợp lại, người dùng có thể truy cập tài sản ngoài phiên được kiểm soát.

Cần xem tổng khả năng thực hiện, không chỉ từng dòng cấu hình.

Một mô hình quyết định minh họa cho luồng JIT:

```text
Cho phép hành động khi:
  danh tính và phiên hợp lệ
  VÀ chủ thể thuộc phạm vi eligibility được quản trị
  VÀ resource/hành động nằm trong entitlement phù hợp
  VÀ grant, phê duyệt và thời gian đáp ứng yêu cầu
  VÀ điều kiện xác thực, thiết bị và rủi ro đáp ứng
  VÀ không có điều kiện cấm theo chính sách
  VÀ điểm thực thi thực hiện được các giới hạn bắt buộc.
```

Đây là mô hình của bài, không phải thuật toán hợp nhất quyền chung cho mọi nền tảng. Cần biết sản phẩm thực tế xử lý cho phép, từ chối, kế thừa và lỗi đánh giá như thế nào.

### 7.1. Quyền tại đích có thể vượt profile PAM

Nếu tài khoản dùng để thực thi có quyền quản trị toàn máy, giới hạn trong giao diện PAM chưa chắc đủ. Người dùng có thể tạo tài khoản, token hoặc tác vụ tồn tại sau phiên nếu được phép thực hiện các thao tác đó.

Cần kết hợp giới hạn tại gateway với quyền thực thi tối thiểu tại đích khi nền tảng hỗ trợ. Nếu có giới hạn kỹ thuật, phải ghi rõ rủi ro và biện pháp bù có thể kiểm chứng.

### 7.2. Quyền tạo quyền

Một entitlement cho phép sửa policy, thêm thành viên nhóm, thay chủ sở hữu hoặc tạo credential có thể gián tiếp mở ra quyền khác.

Đánh giá quyền hiệu lực phải xem các hành động quản trị này, không chỉ quyền đăng nhập tài sản. Người có thể tự thay điều kiện để cấp quyền cho mình cần được kiểm soát bằng phân tách nhiệm vụ hoặc cơ chế phù hợp.

## 8. Thực thi ở đâu để không bị bỏ qua?

Một mô hình chức năng có thể gồm:

- **Điểm quyết định chính sách:** đánh giá chủ thể, resource, hành động và điều kiện.
- **Nguồn thuộc tính:** cung cấp thông tin tài sản, nhóm, thiết bị, phê duyệt và trạng thái quyền.
- **Điểm thực thi:** API, vault, session broker, agent hoặc hệ thống đích thực sự cho phép hay chặn thao tác.

Một quyết định cho phép có thể kèm điều kiện như ghi phiên, dùng tài khoản hạn chế hoặc không tiết lộ credential. Nếu điểm thực thi không đáp ứng được điều kiện bắt buộc, không nên thực hiện như một lần truy cập tuân thủ đầy đủ.

### 8.1. Kiểm tra từng đối tượng tại API

Không tin resource ID từ trình duyệt chỉ vì nó xuất hiện trong danh sách được hiển thị trước đó.

Mỗi yêu cầu cần xác định chủ thể và kiểm tra đúng resource, tenant, hành động và điều kiện. Người dùng không được đổi một ID trong URL hoặc request body để chạm vào tài sản khác.

Đường dẫn, tham số và nội dung yêu cầu cần được chuẩn hóa về cùng đối tượng. Nếu các nguồn chỉ đến các resource khác nhau, không để phần kiểm tra dùng A nhưng phần thực thi lại dùng B.

Chỉ ẩn nút trên giao diện không tạo thành kiểm soát cấp quyền tại máy chủ.

### 8.2. Danh sách, tìm kiếm và thao tác hàng loạt

Danh sách tài sản, kết quả tìm kiếm và dữ liệu xuất cần được lọc theo quyền phù hợp. Số lượng tổng hoặc chi tiết lỗi cũng có thể tiết lộ tài sản ngoài phạm vi, nên cần thiết kế phản hồi.

Với thao tác hàng loạt, phải kiểm tra từng resource và định nghĩa cách xử lý khi một phần không được phép: từ chối toàn bộ hoặc chỉ thực hiện tập hợp hợp lệ được mô tả rõ.

Không kiểm tra quyền trên một resource rồi áp dụng cho toàn bộ danh sách gửi kèm.

### 8.3. Đường truy cập ngoài PAM

Nếu người dùng có thể lấy cùng credential rồi đăng nhập trực tiếp, entitlement trong PAM không kiểm soát được toàn bộ đường đi.

Cần kiểm tra phân đoạn mạng, tài khoản trực tiếp, công cụ hỗ trợ khác và quyền tại đích. Một ngoại lệ khẩn cấp có thể tồn tại theo thiết kế, nhưng phải có phạm vi và trách nhiệm riêng.

## 9. Vòng đời entitlement và thu hồi

### 9.1. Tạo và thay đổi

Entitlement cần có chủ sở hữu, mục đích, phạm vi, nguồn thẩm quyền và điều kiện rà soát. Quyền sản xuất nhạy cảm nên được xử lý theo mức rủi ro và chính sách của tổ chức.

Những thay đổi ảnh hưởng phạm vi gồm:

- Thêm chủ thể hoặc nhóm được hưởng quyền.
- Thêm hành động hoặc đổi profile.
- Mở rộng resource trực tiếp, cây kế thừa hoặc điều kiện chọn động.
- Đổi môi trường hoặc mức nhạy cảm của tài sản.
- Nới lỏng điều kiện xác thực, phê duyệt hoặc thời hạn.
- Thay ánh xạ từ resource logic sang tài khoản hay đích thực thi.

Cần kiểm tra thay đổi ở cả entitlement và các dữ liệu gián tiếp quyết định phạm vi. Một nhãn tài sản có thể là dữ liệu nghiệp vụ nhưng đồng thời là đầu vào cấp quyền.

### 9.2. Rà soát quyền hiệu lực

Chủ sở hữu cần đánh giá người nào còn cần quyền và quyền nào thực tế đang tồn tại.

Không chỉ gửi một danh sách tên vai trò để bấm xác nhận. Hồ sơ rà soát nên chỉ ra resource, hành động, nguồn quyền, trạng thái grant, quyền kế thừa và những ngoại lệ cần chú ý.

Có thể ưu tiên các trường hợp quyền rộng, không sử dụng, không có chủ sở hữu, đổi nhóm nhân sự hoặc khác biệt giữa PAM và đích. Quyền không dùng không tự chứng minh cần xóa ngay, nhưng cần xác minh lý do tồn tại.

### 9.3. Thu hồi nhiều lớp

| Lớp | Điều cần xử lý |
|---|---|
| Eligibility và entitlement nguồn | Chặn yêu cầu hoặc kích hoạt mới ngoài phạm vi |
| Grant đang có | Hủy hoặc để kết thúc theo chính sách đã xác định |
| Phiên PAM | Chặn mở mới, kết nối lại hoặc ngắt phiên khi cần |
| Quyền tại đích | Gỡ nhóm, vai trò hoặc tài khoản tạm do lần cấp tạo ra |
| Credential | Vô hiệu hóa hoặc luân chuyển theo loại bí mật và phụ thuộc |
| Trạng thái còn tồn tại | Kiểm tra token, phiên đích, tác vụ và cơ chế truy cập mới |

Đổi mật khẩu không bảo đảm chấm dứt phiên đã xác thực. Ngắt broker cũng không tự hoàn tác thay đổi hoặc dừng mọi tiến trình tại đích.

Không xóa mọi quyền của một tài khoản chỉ vì một grant hết hạn. Phải biết phần quyền nào do grant đó tạo ra và phần nào đã tồn tại hợp lệ từ nguồn khác.

Khi nhiều grant cùng sử dụng một quan hệ nhóm hoặc vai trò, cần cách quản lý quyền sở hữu và thời gian để thu hồi một grant không phá grant còn hiệu lực. Một tác vụ thu hồi đến muộn cũng không được vô tình xóa quyền của lần cấp mới.

### 9.4. Đối soát thay đổi thủ công và quyền tồn dư

PAM có thể ghi nhận grant đã hết hạn trong khi hệ thống đích vẫn giữ vai trò. Cần cơ chế đọc trạng thái hoặc bằng chứng thực thi để phát hiện.

Các trường hợp cần phân loại:

- Quyền đúng và còn hiệu lực.
- Quyền được kỳ vọng nhưng chưa cấp thành công.
- Quyền đã hết hạn nhưng còn tại đích.
- Quyền cấp trực tiếp không có hồ sơ tương ứng.
- Quyền tại đích rộng hơn ánh xạ đã duyệt.

Không coi trạng thái “revoked” trong workflow là bằng chứng duy nhất rằng thu hồi đã hoàn tất.

## 10. Tình huống thực hành: bảo trì dịch vụ thanh toán

### 10.1. Bối cảnh

Huy thuộc `group-payments-operators`. Công việc là đọc log và khởi động lại dịch vụ trên `asset-2041`, môi trường sản xuất.

Tài sản `asset-3082` của dịch vụ báo cáo nằm ngoài phạm vi. Máy thử nghiệm có cùng tên hiển thị với một máy sản xuất cũng không được coi là cùng resource.

Thiết kế mong muốn:

- Huy được yêu cầu profile bảo trì cho `asset-2041`.
- Cần phê duyệt theo chính sách sản xuất.
- Grant kéo dài tối đa 30 phút trong cửa sổ công việc.
- Phiên dùng tài khoản hạn chế và không tiết lộ credential.
- Không cho truy cập dịch vụ khác hoặc sửa chính sách PAM.
- Kết thúc phải kiểm tra quyền tạm và phiên liên quan.

### 10.2. Quyết định theo từng yêu cầu

| Yêu cầu | Kết quả mong đợi |
|---|---|
| Xem metadata được phép của asset-2041 | Theo quyền hiển thị đã cấp |
| Gửi yêu cầu profile bảo trì asset-2041 | Cho phép yêu cầu nếu eligibility hợp lệ |
| Mở phiên trước khi được duyệt | Chưa cho phép |
| Mở phiên đúng grant, đúng thời gian | Cho phép với giới hạn bắt buộc |
| Hiển thị mật khẩu tài khoản đích | Từ chối vì không có entitlement tiết lộ |
| Đổi ID sang asset-3082 trong API | Từ chối theo resource và hành động |
| Sửa policy để tự thêm quyền | Từ chối vì đây là quyền quản trị riêng |
| Tiếp tục hoặc mở lại sau khi grant hết hạn | Xử lý theo chính sách thu hồi, không tự kéo dài |

### 10.3. Biến thể: thêm máy vào nhóm động

Chủ sở hữu thêm `asset-2042` vào nhóm tài sản dịch vụ thanh toán.

Nếu eligibility được thiết kế theo nhóm động, Huy có thể đủ điều kiện yêu cầu trên tài sản mới. Tuy nhiên, grant hiện tại cho riêng `asset-2041` không tự mở sang `asset-2042`.

Nếu một lần phê duyệt cho phép cả nhóm động, phải xác định rõ điều kiện đó và cách kiểm soát thay đổi thành viên. Không tự suy ra từ việc hai máy có cùng nhãn.

### 10.4. Biến thể: credential dùng được trên tài sản ngoài phạm vi

Kiểm tra phát hiện tài khoản đích trên `asset-2041` dùng cùng credential với một máy khác. Nếu Huy nhận được credential đó hoặc có thể mở kết nối từ máy được duyệt sang máy khác, phạm vi thực tế có thể vượt thiết kế.

Cần đánh giá khả năng sử dụng thực tế, tách credential hoặc tài khoản khi phù hợp, hạn chế đường đi và kiểm tra lại cơ chế phiên. Việc giao diện chỉ hiển thị một tài sản không giải quyết được quan hệ credential phía sau.

### 10.5. Biến thể: thu hồi thất bại

Grant hết hạn lúc 20:30, broker đã ngắt nhưng tác vụ gỡ vai trò tạm tại máy đích thất bại.

Trạng thái phải phản ánh còn phần thu hồi chưa hoàn tất. Cần cảnh báo, người xử lý và cách kiểm chứng sau đó. Không chỉ đánh dấu “đã đóng” vì cửa sổ thời gian kết thúc.

Nếu có tác vụ chạy nền, cần đánh giá tác động riêng. Thu hồi quyền đăng nhập không tự dừng tác vụ đã được tạo.

## 11. Bằng chứng cần lưu

Một chuỗi có thể đối chiếu:

```text
Danh tính và nhóm tại thời điểm liên quan
    -> Entitlement và phiên bản phạm vi
    -> Yêu cầu + phê duyệt
    -> Grant cho người/resource/profile cụ thể
    -> Quyết định tại điểm thực thi
    -> Quyền hoặc phiên thực tế tại đích
    -> Thu hồi và kết quả xác minh
```

Các dữ liệu hữu ích gồm:

- Định danh chủ thể, tenant, resource và hành động.
- Nguồn quyền trực tiếp, nhóm hoặc kế thừa.
- Phiên bản policy, profile và ánh xạ tài khoản đích.
- Danh sách resource đã được duyệt hoặc điều kiện tập động áp dụng.
- Mốc thời gian, phê duyệt và trạng thái grant.
- Mã phiên, tài khoản thực thi và sự kiện đích liên quan.
- Thay đổi nhóm, nhãn, chủ sở hữu hoặc cấu hình phạm vi.
- Kết quả thu hồi, lỗi và việc xử lý tiếp.

Không lưu giá trị credential vào hồ sơ quyền. Bằng chứng có thể chứa thông tin hạ tầng hoặc dữ liệu nhạy cảm, nên cần phân quyền và thời hạn lưu phù hợp.

Khi audit quá khứ, không dùng cây tài nguyên hoặc membership hiện tại để mặc định phạm vi của một grant cũ. Cần dữ liệu lịch sử đủ để giải thích phạm vi tại thời điểm quyết định và sử dụng.

## 12. Kiểm chứng entitlement theo resource

Thực hiện trong môi trường và phạm vi được phép.

| Phép thử | Kết quả mong đợi |
|---|---|
| Cùng tên tài sản ở hai môi trường | Quyết định dựa đúng định danh và miền resource |
| Đổi resource ID trong URL hoặc body | Không truy cập được đối tượng ngoài phạm vi |
| Gửi ID thuộc tenant khác | Bị từ chối theo kiểm tra phía máy chủ |
| Đường dẫn và body chỉ hai tài sản khác nhau | Không kiểm tra A rồi thực thi B |
| Có eligibility nhưng chưa có grant bắt buộc | Chưa sử dụng được quyền đặc biệt |
| Được mở phiên nhưng không có quyền reveal | Không nhận được credential |
| Profile hạn chế thử thao tác rộng hơn | Bị hạn chế bởi cơ chế thực thi thực tế |
| Thêm resource vào nhóm động | Hiệu lực theo thiết kế, không mở rộng grant tĩnh |
| Đổi nhãn để đưa tài sản vào phạm vi | Thay đổi được kiểm soát và có bằng chứng |
| Quyền rộng đến từ một nhóm khác | Được phát hiện trong đánh giá quyền hợp thành |
| Thao tác hàng loạt có một resource ngoài phạm vi | Xử lý đúng quy tắc toàn bộ hoặc từng phần |
| API gọi trực tiếp bỏ giao diện | Vẫn kiểm tra entitlement và điều kiện |
| Grant hết hạn khi phiên đang mở | Thực thi chính sách kết thúc đã xác định |
| Hai grant chồng thời gian cùng dùng một vai trò đích | Thu hồi một grant không phá quyền hợp lệ của grant khác |
| Tác vụ cấp hoặc thu hồi đến muộn | Không tạo quyền cũ hoặc xóa nhầm quyền mới |
| PAM báo đã thu hồi nhưng đích còn vai trò | Phát hiện chênh lệch và có xử lý |
| Tài sản được tạo lại với tên cũ | Không tự thừa hưởng quyền ngoài quy tắc vòng đời |

Một phép thử không đạt cần dẫn đến sửa cấu hình, cơ chế thực thi hoặc giới hạn phạm vi có thể kiểm chứng. Không chỉ sửa tên profile để tạo cảm giác quyền đã hẹp hơn.

## 13. Những sai lầm thường gặp

**Gắn quyền vào tên hiển thị.** Tên có thể trùng hoặc tái sử dụng; cần định danh ổn định và đúng miền.

**Dùng một quyền “access” cho mọi hành động.** Mở phiên, tiết lộ secret, luân chuyển và sửa policy có tác động khác nhau.

**Coi thành viên nhóm là grant đang có hiệu lực.** Đủ điều kiện yêu cầu không đồng nghĩa được sử dụng ngay.

**Quên quyền kế thừa hoặc nhóm chồng lấn.** Quyền thực tế có thể rộng hơn từng entitlement riêng lẻ.

**Coi nhãn tài sản là dữ liệu không liên quan bảo mật.** Nếu nhãn chọn phạm vi quyền, thay nhãn có thể cấp quyền.

**Hạn chế trên UI nhưng không kiểm tra API.** Resource cần được kiểm tra ở điểm thực thi.

**Giới hạn resource trong PAM nhưng tiết lộ credential dùng chung.** Khả năng truy cập của bí mật có thể vượt phạm vi hiển thị.

**Chỉ thu hồi bản ghi grant.** Cần đối soát quyền, phiên và trạng thái đích liên quan.

## 14. Tự kiểm tra

1. Vì sao vai trò “vận hành” chưa đủ để mô tả entitlement?
2. Eligibility khác grant đang hoạt động như thế nào?
3. Người được mở phiên có tự được xem mật khẩu không?
4. Vì sao thay nhãn hoặc thành viên nhóm tài nguyên có thể là thay đổi bảo mật?
5. Grant cho tài sản A có tự áp dụng cho tài sản B mới thêm vào nhóm không?
6. Cần kiểm tra gì khi một secret dùng được trên nhiều máy?
7. Vì sao phải đánh giá quyền hợp thành từ nhiều nhóm và nguồn?
8. PAM báo thu hồi thành công có đủ chứng minh máy đích không còn quyền không?

### Gợi ý trả lời

1. Cần thêm resource, hành động, phạm vi và điều kiện sử dụng.
2. Eligibility cho phép yêu cầu hoặc kích hoạt theo điều kiện; grant là lần cấp cụ thể đang có hiệu lực.
3. Không. Đó là hai hành động cần quyền riêng.
4. Vì chúng có thể quyết định tài sản nào nằm trong phạm vi được hưởng quyền.
5. Không tự động. Phụ thuộc phạm vi grant và mô hình phê duyệt đã thiết kế.
6. Phạm vi xác thực thực tế, khả năng sao chép, đường truy cập và quyền tài khoản liên quan.
7. Các quyền riêng lẻ có thể kết hợp thành khả năng rộng hơn hoặc tạo đường vượt kiểm soát.
8. Chưa đủ. Cần bằng chứng thực thi và kiểm tra quyền, phiên hoặc trạng thái còn tồn tại tại đích.

## Kết luận

Entitlement theo resource làm rõ một chủ thể được yêu cầu hoặc thực hiện hành động nào trên tài sản nào, trong điều kiện và thời hạn nào. Giá trị của mô hình nằm ở định danh đúng resource, giới hạn hành động và kiểm soát các nguồn quyền hợp thành.

Trong PAM, mô hình đó phải nối với phê duyệt, JIT/JEA, vault, phiên và quyền thực tế tại đích. Khi cả cấp quyền lẫn thu hồi đều có bằng chứng đối chiếu, phạm vi quyền được mô tả có thể khớp với khả năng thực hiện trong hệ thống.
