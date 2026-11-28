# Log break-glass

## 1. Mục tiêu và phạm vi

Trong quản lý truy cập đặc quyền (PAM), **break-glass** là cơ chế truy cập khẩn cấp khi đường quản trị thông thường không dùng được hoặc không đáp ứng được tình huống khôi phục. Ví dụ: IdP gián đoạn, cấu hình xác thực làm quản trị viên mất quyền đăng nhập, hoặc nền tảng cấp quyền tạm thời gặp sự cố. Tùy hệ thống, đường khẩn cấp có thể dùng tài khoản dự phòng, tài khoản cục bộ, credential được giữ riêng hoặc một quy trình cấp quyền ngoại lệ đã thiết kế trước.

Bài này tập trung vào **log của quá trình sử dụng break-glass**, từ chuẩn bị, lấy phương tiện truy cập, đăng nhập, thực hiện thao tác đến đóng phiên và rà soát. Mục tiêu là khôi phục được chuỗi bằng chứng:

> Người nào sử dụng danh tính đặc quyền nào, vì sự cố gì, vào tài nguyên nào, làm gì, kết quả ra sao, và ai đã xác minh việc kết thúc truy cập?

Sau bài học, người học có thể:

- Xác định sự kiện phải thu ở các lớp danh tính, custody, PAM và hệ thống đích.
- Thiết kế bản ghi có định danh ổn định, thời gian rõ nghĩa và khả năng liên kết nhiều nguồn.
- Phát hiện việc sử dụng khẩn cấp và các khoảng trống quan sát mà không nhầm thiếu log với không có hành vi.
- Bảo vệ log, thiết kế đường ghi dự phòng và tổ chức hậu kiểm có bằng chứng.
- Thực hành dựng lại một phiên break-glass trong môi trường giả lập.

Các tên sự kiện, trường dữ liệu, ngưỡng cảnh báo và thời gian trong ví dụ là **thiết kế minh họa**, không phải schema bắt buộc của một sản phẩm hay yêu cầu áp dụng cho mọi tổ chức.

## 2. Vì sao break-glass cần một chuỗi log riêng?

### 2.1. Đường ngoại lệ có thể đi vòng qua điểm quan sát thông thường

Trong luồng quản trị bình thường, PAM có thể xác minh người dùng, cấp credential, áp giới hạn quyền và ghi phiên. Khi break-glass đi trực tiếp vào hệ thống đích, một phần chuỗi này có thể không còn hiện diện. Vì vậy, kết luận “không thấy session trong PAM nên không có truy cập đặc quyền” là sai nếu vẫn tồn tại đường khẩn cấp ngoài PAM.

Break-glass không mặc nhiên đồng nghĩa với bỏ xác thực, bỏ mọi chính sách hay dùng mật khẩu chia sẻ. Thiết kế cụ thể tùy nền tảng. Điều phải biết rõ là **kiểm soát nào vẫn có hiệu lực, kiểm soát nào được thay thế và nguồn nào còn quan sát được**.

| Đặc điểm của đường khẩn cấp | Rủi ro đối với bằng chứng | Yêu cầu ghi nhận |
|---|---|---|
| Không đi qua gateway PAM | Không có recording của PAM | Thu log xác thực và thao tác trực tiếp tại đích; đánh dấu recording không khả dụng |
| Dùng danh tính được nhiều người có thể tiếp cận | Tài khoản không tự chỉ ra con người | Lưu chuỗi bàn giao, người nhận và bằng chứng liên kết với phiên |
| IdP hoặc mạng quản trị bị gián đoạn | Không truy vấn được nguồn danh tính quen thuộc | Chuẩn bị định danh và phương án xác minh dự phòng từ trước |
| Ticket hoặc workflow phê duyệt bị lỗi | Thiếu mã sự cố, thiếu quyết định trong hệ thống chính | Ghi mã khẩn cấp tạm và quyết định qua kênh dự phòng, đối soát sau |
| Thu log trung tâm bị gián đoạn | Sự kiện đến trễ hoặc mất | Lưu bền vững tại nguồn hoặc collector dự phòng; công bố khoảng thiếu |
| Quyền rất rộng | Một phiên có thể tạo thêm đường truy cập | Thu thay đổi role, tài khoản, credential và cấu hình audit |

### 2.2. Ba loại bằng chứng phải được phân biệt

**Bằng chứng về ý định:** yêu cầu khẩn cấp, phạm vi được phép, người quyết định và lý do. Đây là bằng chứng về việc được yêu cầu làm gì.

**Bằng chứng về truy cập:** xác thực thành công hoặc thất bại, danh tính đã dùng, nguồn kết nối và phiên. Đây là bằng chứng về việc hệ thống quan sát được ai hoặc danh tính nào truy cập.

**Bằng chứng về hành động và kết quả:** API đã gọi, tài nguyên đã đổi, quyền đã cấp, trạng thái trước/sau và kết quả thực thi. Đây là bằng chứng về việc thực sự xảy ra tại đích.

Một ticket được duyệt không chứng minh thao tác tuân thủ phạm vi. Một lần đăng nhập thành công cũng không chứng minh đã sửa cấu hình nào. Ngược lại, một yêu cầu bị từ chối vẫn cần lưu vì nó có thể cho thấy nỗ lực lạm dụng đường khẩn cấp.

## 3. Vòng đời sự kiện cần thu

Không nên chỉ bắt đầu ghi khi tài khoản khẩn cấp đăng nhập. Sự thay đổi trước đó đối với tài khoản, credential, danh sách người giữ hoặc cấu hình giám sát có thể quyết định nguyên nhân của sự cố.

| Giai đoạn | Sự kiện minh họa | Nội dung cần chứng minh |
|---|---|---|
| Chuẩn bị | EMERGENCY_IDENTITY_REGISTERED, CUSTODIAN_CHANGED | Danh tính nào thuộc diện khẩn cấp, ai quản lý, phiên bản cấu hình nào |
| Thay đổi cơ chế | CREDENTIAL_REPLACED, AUDIT_SETTING_CHANGED | Ai thay phương tiện xác thực hoặc khả năng quan sát |
| Khởi tạo sử dụng | EMERGENCY_REQUESTED, EMERGENCY_DECISION_RECORDED | Sự cố, nhu cầu, phạm vi, người quyết định và thời điểm |
| Bàn giao | CREDENTIAL_CHECKED_OUT, DEVICE_RELEASED | Ai nhận phương tiện, từ ai, theo quy trình nào |
| Truy cập | AUTHENTICATION_ATTEMPTED, SESSION_STARTED | Danh tính kỹ thuật, nguồn, kết quả và phiên quan sát được |
| Thao tác | PRIVILEGED_ACTION_COMPLETED, ROLE_ASSIGNED | Tài nguyên, loại hành động, kết quả và quyền được thay đổi |
| Theo dõi | ALERT_CREATED, ALERT_ACKNOWLEDGED | Cảnh báo có được sinh, chuyển đến và có người nhận xử lý không |
| Kết thúc | SESSION_ENDED, ACCESS_EXPIRY_VERIFIED | Phiên kết thúc và quyền tạm đã được xác minh hết hiệu lực |
| Phục hồi kiểm soát | CREDENTIAL_RESECURED, TEMPORARY_GRANT_REMOVED | Phương tiện đã được bảo quản lại, quyền phát sinh đã được xử lý |
| Hậu kiểm | EMERGENCY_REVIEW_COMPLETED | Bằng chứng đã được đối soát, khoảng trống và việc cần khắc phục |

Các tên trên chỉ là một taxonomy minh họa. Có hệ thống không phát sinh sự kiện checkout vì phương tiện nằm trong két ngoại tuyến; có hệ thống không phát sinh logout khi trình duyệt đóng đột ngột. Thiết kế phải nêu rõ nguồn thay thế và giới hạn quan sát, thay vì tạo bản ghi thành công giả để đủ bảng.

**Tách yêu cầu, kết quả và xác minh.** “Đã gửi yêu cầu thu hồi phiên” khác với “đã xác minh phiên không còn sử dụng được”. “Đã yêu cầu luân chuyển credential” khác với “credential mới hoạt động và credential cũ không còn hiệu lực theo cơ chế của nền tảng”.

Với quyền tạm theo JIT, cần ghi thời hạn đã cấp và kết quả xác minh hết hạn. Với tài khoản khẩn cấp có quyền thường trực theo thiết kế, không được tự suy diễn rằng kết thúc sự cố đồng nghĩa phải xóa tài khoản hay gỡ toàn bộ quyền của nó. Hậu kiểm phải đối chiếu đúng mô hình đã phê duyệt, đồng thời loại bỏ quyền ngoài mô hình đó.

## 4. Kiến trúc thu log khi chính hạ tầng quản trị đang hỏng

### 4.1. Dùng nhiều nguồn quan sát có vai trò khác nhau

Một kiến trúc tham khảo:

~~~mermaid
flowchart LR
    C[Custody và quyết định khẩn cấp] --> A[Kho bằng chứng kiểm toán]
    I[IdP hoặc xác thực tại đích] --> Q[Collector và hàng đợi bền vững]
    T[Audit thao tác tại hệ thống đích] --> Q
    P[PAM hoặc gateway nếu còn hoạt động] --> Q
    Q --> A
    Q --> D[Phát hiện và tương quan]
    D --> N[Kênh cảnh báo và ca trực]
    N --> R[Hồ sơ sự cố và hậu kiểm]
    A --> R
    H[Giám sát sức khỏe pipeline] --> N
~~~

Không phải mọi nguồn đều luôn sẵn sàng. Chẳng hạn, mất PAM nhưng audit của đích vẫn hoạt động là một trạng thái suy giảm khác với việc cả PAM lẫn audit tại đích đều mất.

Mỗi nguồn nên có một mô tả vận hành ngắn:

- Loại sự kiện cung cấp được và loại không cung cấp được.
- Danh tính collector, điểm lưu bền vững đầu tiên và cơ chế chuyển tiếp.
- Độ trễ dự kiến, dung lượng đệm và dấu hiệu gần đầy.
- Quyền cần có để sửa cấu hình nguồn hoặc xóa dữ liệu.
- Phương án khi nguồn không phát được log và người chịu trách nhiệm.

Một cảnh báo SIEM chỉ chứng minh cơ chế phát hiện nhìn thấy dữ liệu nào đó. Nó không thay thế bản ghi gốc tại nguồn. Ngược lại, có bản ghi nguồn nhưng chưa được gửi đến nơi phát hiện có nghĩa là khả năng điều tra có thể còn, còn khả năng phản ứng tức thời đã suy giảm.

### 4.2. Tránh cùng một điểm hỏng cho truy cập và cảnh báo

Nếu sự cố IdP khiến quản trị viên cần break-glass, nhưng hộp thư ca trực và công cụ xác nhận cảnh báo cũng chỉ đăng nhập qua đúng IdP đó, cảnh báo có thể tồn tại mà không ai đọc được.

Cần đánh giá phụ thuộc của cả đường truy cập lẫn đường thông báo: DNS, mạng, danh tính, nền tảng cộng tác, thiết bị xác thực và nguồn điện. Chọn kênh dự phòng phù hợp với mô hình sự cố của tổ chức; việc “có hai kênh” không đủ nếu cả hai cùng phụ thuộc một dịch vụ đang hỏng.

Cảnh báo dự phòng chỉ nên chứa thông tin tối thiểu: mã cảnh báo, môi trường, danh tính kỹ thuật, thời gian và hướng dẫn liên hệ qua đường đã định. Không gửi credential, token hoặc đường dẫn chứa quyền truy cập trực tiếp vào bản ghi phiên.

### 4.3. Khi collector hoặc SIEM không dùng được

Một phương án cần được thiết kế trước, không ứng biến bằng việc tắt audit:

1. Tiếp tục ghi tại nguồn hoặc hàng đợi bền vững được bảo vệ.
2. Ghi trạng thái suy giảm, thời điểm phát hiện và nguồn bị ảnh hưởng.
3. Dùng kênh liên lạc dự phòng để báo việc sử dụng break-glass và tình trạng quan sát.
4. Theo dõi dung lượng đệm, lỗi ghi và thời gian chưa chuyển tiếp.
5. Khi đường thu phục hồi, gửi lại với định danh gốc và đối soát dữ liệu đã tiếp nhận.
6. Đưa khoảng trống, dữ liệu đến muộn và sự kiện không khôi phục được vào hồ sơ hậu kiểm.

Lưu đệm chỉ hữu ích khi dữ liệu thực sự được ghi bền vững. Một queue trong bộ nhớ không bảo đảm tồn tại sau khi tiến trình hoặc máy chủ dừng. Độ bền phải được kiểm tra theo cách triển khai và mô hình lỗi cụ thể.

Nếu bộ đệm đầy hoặc không thể ghi tại nguồn, phải có quyết định vận hành đã được tổ chức phê duyệt cho tình huống đó: mức độ khẩn cấp nào được tiếp tục, nguồn chứng kiến nào được dùng, ai nhận trách nhiệm và rủi ro nào cần ghi lại. Không có lựa chọn “luôn chặn” hoặc “luôn cho qua” phù hợp cho mọi hệ thống. Tuyệt đối không báo “audit đầy đủ” trong trạng thái này.

## 5. Gắn con người với danh tính khẩn cấp

### 5.1. Tách danh tính người thao tác và tài khoản dùng để truy cập

Giả sử tài khoản kỹ thuật là emergency-admin-02, còn người thao tác là nhân sự OPS-042. Bản ghi xác thực tại đích có thể chỉ chứa emergency-admin-02. Để liên kết với OPS-042, cần thêm bằng chứng từ quy trình bàn giao, máy trạm được dùng, hồ sơ ca trực hoặc kênh xác minh độc lập.

| Thành phần | Ý nghĩa |
|---|---|
| person_id | Định danh người thao tác theo nguồn quản lý con người |
| principal_id | Định danh ổn định của danh tính được hệ thống đích xác thực |
| principal_name | Tên hiển thị hoặc tên đăng nhập tại thời điểm sự kiện |
| custodian_id | Người giữ hoặc bàn giao phương tiện khẩn cấp |
| decision_maker_id | Người đưa ra quyết định theo quy trình khẩn cấp |
| attribution_basis | Nguồn dùng để gắn người với phiên |
| attribution_state | Trạng thái liên kết: đã đối soát, còn tạm thời hoặc chưa xác định |

Không được điền person_id bằng người đang trực chỉ vì “chắc là người đó”. Nếu chỉ có khai báo của người dùng, phải ghi đó là khai báo và chờ đối soát. Bằng chứng bàn giao một credential cho một người cũng không tự chứng minh mọi hành động của tài khoản sau đó đều do người ấy thực hiện.

Nên ưu tiên định danh ổn định và có phạm vi, ví dụ tenant_id kết hợp principal_id. Tên đăng nhập có thể đổi; cùng một chuỗi tên cũng có thể xuất hiện ở hai môi trường khác nhau.

### 5.2. Dùng một mã cho lần kích hoạt, không ép mọi nguồn cùng một correlation ID

Một lần sử dụng khẩn cấp có thể gồm nhiều đăng nhập, nhiều tài nguyên và nhiều session. Cần phân biệt:

- **emergency_use_id:** một lần kích hoạt quy trình khẩn cấp.
- **incident_id:** sự cố nghiệp vụ hoặc kỹ thuật liên quan.
- **source_event_id:** định danh sự kiện do từng nguồn phát.
- **session_id:** phiên tại một hệ thống cụ thể, có thể không tồn tại.
- **request_id hoặc correlation_id:** định danh yêu cầu do nguồn cung cấp.

Không phải nguồn nào cũng nhận emergency_use_id. Khi đó, tạo bản ghi liên kết riêng giữa các định danh, kèm nguồn bằng chứng và người xác minh. Không sửa bản ghi gốc để làm như nguồn đã phát một trường mà thực tế không có.

Tương quan bằng tài khoản, IP và thời gian chỉ là một giả thuyết liên kết. NAT, proxy, máy dùng chung hoặc đồng hồ lệch có thể làm nhiều hành động trông giống nhau. Nếu không có định danh phiên đáng tin cậy, cần thể hiện độ chắc chắn của liên kết thay vì tuyên bố đã quy trách nhiệm chính xác.

## 6. Schema sự kiện minh họa

Dưới đây là một sự kiện giả lập do bộ chuẩn hóa tạo ra. Mọi giá trị là dữ liệu minh họa, không chứa credential thật.

~~~json
{
  "schema_version": "1.0",
  "event_id": "norm-000184",
  "event_type": "AUTHENTICATION_ATTEMPTED",
  "occurred_at": "2026-08-18T02:03:12.431Z",
  "observed_at": "2026-08-18T02:03:15.082Z",
  "source": {
    "system": "identity-audit",
    "scope_id": "lab-tenant-a",
    "source_event_id": "src-auth-68192"
  },
  "emergency_use_id": "BG-LAB-027",
  "incident_id": "INC-LAB-104",
  "principal": {
    "id": "emergency-object-02",
    "name": "emergency-admin-02",
    "classification": "EMERGENCY_ACCESS",
    "registry_version": "registry-18"
  },
  "person_attribution": {
    "person_id": "OPS-042",
    "state": "PROVISIONAL",
    "basis": "custody-record-C-117"
  },
  "target": {
    "environment": "lab",
    "resource_id": "lab-tenant-a"
  },
  "connection": {
    "source_ip": "192.0.2.24",
    "workstation_id": "PAW-LAB-03"
  },
  "authentication": {
    "outcome": "SUCCESS",
    "method_category": "HARDWARE_BACKED"
  },
  "session_id": null,
  "correlation": {
    "source_correlation_id": "auth-req-094",
    "link_basis": "custody-plus-source-context"
  },
  "mode": "EMERGENCY",
  "evidence_ref": "evidence://lab/source-auth/src-auth-68192"
}
~~~

Các điểm cần giữ rõ:

- occurred_at là thời gian sự kiện theo nguồn; observed_at là thời gian hệ thống thu nhận thấy sự kiện. Cả hai dùng UTC trong ví dụ.
- SUCCESS nói về kết quả xác thực được quan sát, không có nghĩa lần sử dụng đã được phê duyệt hay toàn bộ thao tác đều thành công.
- person_attribution ở trạng thái PROVISIONAL cho thấy liên kết con người chưa được xác minh cuối cùng.
- session_id là null vì nguồn chưa cung cấp. Không tạo một session_id giả rồi dùng nó làm bằng chứng về phiên tại đích.
- principal.classification đến từ registry có phiên bản. Bộ chuẩn hóa phải lưu được cơ sở phân loại, thay vì tin nhãn do người truy cập tự gửi.
- evidence_ref là tham chiếu minh họa. Hệ thống thật phải kiểm soát quyền đọc và không biến nó thành URL công khai hoặc bearer token.
- event_id của tầng chuẩn hóa khác source_event_id. Khi gửi lại cùng sự kiện nguồn, hệ thống phải có cơ chế nhận diện trùng phù hợp với phạm vi của nguồn.

Đối với thao tác thay đổi quyền, bổ sung các trường như action, target_resource_id, requested_role, outcome, provider_error_code và tham chiếu cấu hình trước/sau đã lọc dữ liệu nhạy cảm. Không gom mọi chi tiết vào một chuỗi message khó truy vấn.

### 6.1. Không ghi bí mật vào audit log

Log cần chứng minh credential hoặc phương tiện nào được sử dụng, không cần chứa giá trị bí mật của nó.

Không ghi:

- Mật khẩu, mã khôi phục, OTP, private key hoặc nội dung secret.
- Access token, refresh token, session cookie và Authorization header.
- URL hoặc query string có credential.
- Toàn bộ lệnh hoặc request body khi chúng chứa bí mật.
- Bản chụp màn hình hoặc recording chưa được đánh giá rủi ro lộ dữ liệu.

Có thể ghi credential_reference, phiên bản secret, mã phương tiện xác thực hoặc mã giao nhận theo chính sách. Không băm mật khẩu để dùng làm “dấu vân tay kiểm toán”; bản băm đó vẫn có thể tạo rủi ro suy đoán bí mật.

Dữ liệu đầu vào phải được mã hóa theo cấu trúc và xử lý ký tự điều khiển khi hiển thị. Lý do khẩn cấp do người dùng nhập không được phép chèn dòng giả hoặc làm giao diện log hiểu nhầm thành một sự kiện khác.

## 7. Phát hiện và cảnh báo

### 7.1. Phát hiện mọi lần thử sử dụng rồi phân loại

Tài khoản khẩn cấp thường ít hoạt động, nên việc sử dụng là một tín hiệu cần được xem xét. Không chỉ theo dõi đăng nhập thành công. Nỗ lực thất bại, lấy phương tiện rồi không đăng nhập, hoặc thay đổi cấu hình giám sát cũng có thể đáng chú ý.

| Tín hiệu | Cách xử lý minh họa | Điều cần kiểm chứng |
|---|---|---|
| Bất kỳ lần thử xác thực bằng danh tính khẩn cấp | Sinh cảnh báo hoặc hồ sơ phát hiện theo mức ưu tiên đã định | Thành công/thất bại, nguồn, người thao tác, sự cố liên quan |
| Dùng tài khoản ngoài lần kích hoạt đã biết | Ưu tiên điều tra cao | Có quy trình dự phòng chưa được đồng bộ hay sử dụng không hợp lệ |
| Nhiều lần xác thực thất bại | Tương quan chuỗi thất bại và sự kiện tiếp theo | Sai phương tiện hợp lệ, tài khoản bị thử hoặc tấn công |
| Thêm danh tính, role hoặc credential mới | Gắn với phạm vi khôi phục và thời hạn | Có tạo quyền tồn tại sau sự cố không |
| Đổi audit, collector, retention hoặc rule cảnh báo | Thông báo cho nhóm giám sát phù hợp | Ai đổi, mục đích gì, còn nguồn quan sát độc lập không |
| Không có xác nhận kết thúc sau thời hạn | Yêu cầu kiểm tra phiên và quyền tại đích | Phiên còn hoạt động hay chỉ thiếu sự kiện kết thúc |
| Pipeline không khỏe trong lúc có sử dụng khẩn cấp | Cảnh báo suy giảm khả năng quan sát | Nguồn nào mất, mất từ khi nào, dữ liệu có đệm không |

Một lần diễn tập vẫn phải sinh sự kiện và kiểm tra đường cảnh báo. Có thể gắn exercise_id và hướng dẫn ca trực xử lý theo kế hoạch; không nên tắt thu log toàn cục để tránh tiếng ồn.

Đặc biệt, mode do người dùng tự khai báo là DRILL không đủ để làm cảnh báo biến mất. Việc xác nhận diễn tập phải đối chiếu kế hoạch đáng tin cậy, đúng thời gian, danh tính và phạm vi.

### 7.2. Ví dụ logic phát hiện trung lập với sản phẩm

Pseudocode sau giả định sự kiện đã được chuẩn hóa và registry lưu lịch sử phân loại danh tính:

~~~text
for each newly_observed_event:
    identity = find_identity_in_registry(
        scope_id = event.scope_id,
        principal_id = event.principal_id,
        at_time = event.occurred_at
    )

    if identity is classified as emergency
       and event is an authentication attempt:
        persist_detection(
            key = source_system + scope_id + source_event_id,
            outcome = event.authentication_outcome,
            source_reference = event.source_reference
        )
        enqueue_notification_for_reliable_delivery()

    if event changes emergency identity controls
       or changes the monitoring path:
        persist_control_change_detection()
        enqueue_notification_for_reliable_delivery()
~~~

Đây là logic minh họa, không phải API hoặc rule có thể dán trực tiếp vào SIEM. Registry cần được quản lý thay đổi và đồng bộ đủ nhanh. Một danh tính mới được tạo nhưng chưa vào registry có thể bị rule chuyên biệt bỏ sót, nên vẫn cần giám sát thay đổi tài khoản và quyền đặc quyền nói chung.

Khi đọc luồng có sự kiện đến muộn, nên dựa vào cơ chế tiếp nhận hoặc checkpoint của luồng để không bỏ qua dữ liệu chỉ vì occurred_at đã cũ. Với rule chạy theo cửa sổ thời gian, cần lookback phù hợp, phát hiện dữ liệu trễ và khử trùng ổn định. Một cửa sổ cố định ngắn không bảo đảm bao phủ được thời gian hệ thống thu log bị gián đoạn.

Không đánh dấu sự kiện đã xử lý trước khi kết quả phát hiện được lưu bền vững. Nếu lưu phát hiện thành công nhưng gửi thông báo thất bại, phải có retry hoặc hàng đợi thông báo độc lập; không yêu cầu nguồn phát lại log mới gửi được cảnh báo.

### 7.3. Phân biệt sinh cảnh báo, chuyển phát và có người tiếp nhận

Ba trạng thái khác nhau cần ghi:

1. Detection được tạo: rule đã nhìn thấy và nhận diện sự kiện.
2. Notification được chuyển phát hoặc được hệ thống nhận thông báo xác nhận.
3. Người trực xác nhận tiếp nhận và có hành động xử lý.

Một HTTP 200 từ dịch vụ gửi tin không chứng minh có người đọc. Thiết kế cần thời hạn xác nhận và đường escalation nếu chưa có người nhận trách nhiệm.

Thông báo nên gồm mã sự kiện, định danh tài khoản, môi trường, thời gian, kết quả, mã sự cố nếu đã xác minh và liên kết đến hồ sơ có kiểm soát truy cập. Chỉ đưa thông tin cá nhân và chi tiết hệ thống vào kênh có quyền phù hợp.

Không tự động vô hiệu hóa tài khoản khẩn cấp chỉ vì rule thấy một lần sử dụng. Hành động phản ứng phải cân nhắc việc đang khôi phục dịch vụ, mức độ xác minh lạm dụng và phương án truy cập còn lại. Các thao tác phản ứng tự động, nếu được triển khai, cũng phải có audit và kiểm thử riêng.

## 8. Chất lượng log: thời gian, sự kiện trùng và khoảng thiếu

### 8.1. Thời gian cần đủ để dựng lại diễn biến

Lưu thời gian theo định dạng có múi giờ rõ ràng; UTC thường thuận tiện cho tương quan. Nếu nguồn dùng múi giờ địa phương hoặc có độ chính xác thấp, giữ metadata này trong quá trình chuẩn hóa.

Đồng hồ lệch có thể khiến việc cấp quyền trông như xảy ra sau thao tác vốn cần quyền đó. Không sửa âm thầm thời gian nguồn để làm timeline “đẹp”. Có thể bổ sung thời gian hiệu chỉnh hoặc ghi chú phân tích, nhưng phải giữ giá trị gốc và cơ sở hiệu chỉnh.

Các chỉ số hữu ích gồm:

- Độ trễ thu nhận: observed_at trừ occurred_at, khi hai đồng hồ đủ tin cậy.
- Độ trễ phát hiện: detection_created_at trừ observed_at.
- Độ trễ người trực xác nhận: acknowledged_at trừ notification_sent_at.

Giá trị âm hoặc đột biến có thể do đồng hồ, ngữ nghĩa timestamp hoặc lỗi pipeline. Không loại chúng khỏi báo cáo mà không điều tra. Chỉ số trên dữ liệu đã đến cũng không đo được sự kiện bị mất hoàn toàn.

### 8.2. Khử trùng phải giữ được hành vi lặp thật

Một sự kiện có thể được gửi lại sau reconnect. Khóa khử trùng cần tính đến định danh nguồn và phạm vi của nó; không mặc định source_event_id là duy nhất trên toàn tổ chức.

Không khử trùng chỉ bằng “tài khoản + loại hành động + phút”. Hai lần đăng nhập thật trong cùng phút sẽ bị gộp mất. Nếu nguồn không có ID ổn định, cần chiến lược có đánh giá va chạm, đồng thời giữ bản ghi thô và đánh dấu mức chắc chắn.

Đối với cảnh báo, có thể gom nhiều sự kiện thành một hồ sơ điều tra để ca trực xử lý thuận tiện. Việc gom cảnh báo không được làm mất những sự kiện cấu thành hồ sơ.

### 8.3. Thiếu log cần được coi là một phát hiện

Không thấy sự kiện logout không chứng minh phiên còn mở, nhưng cũng không đủ để khẳng định phiên đã đóng. Có thể cần kiểm tra phiên, token hoặc kết nối đang tồn tại theo cơ chế của nền tảng.

Tương tự, một collector phát heartbeat không chứng minh mọi nguồn đều gửi đủ loại sự kiện. Cần quan sát cả trạng thái nguồn, độ trễ, lỗi chuyển tiếp, checkpoint và số lượng bản ghi theo các phép đối soát mà nguồn hỗ trợ.

Nếu nguồn cung cấp sequence liên tục theo phạm vi xác định, có thể phát hiện lỗ hổng sequence. Không áp dụng phép kiểm này cho một trường số bất kỳ chưa được nhà cung cấp xác nhận có tính liên tục.

Một gap record nên ghi nguồn bị ảnh hưởng, khoảng thời gian ước lượng, loại sự kiện thiếu, nguyên nhân đã biết, dữ liệu có thể khôi phục và người phụ trách. Kết luận điều tra phải giữ giới hạn do khoảng thiếu tạo ra.

## 9. Bảo vệ bằng chứng và quyền truy cập log

Người có quyền rất rộng trên hệ thống đích có thể đồng thời có khả năng sửa audit hoặc xóa dữ liệu tại chỗ. Vì thế, bản sao log nên được chuyển sang một miền quản trị có kiểm soát phù hợp, và quyền sửa rule, retention hoặc kho bằng chứng phải được theo dõi riêng.

Các biện pháp có thể kết hợp:

- Mã hóa khi truyền và khi lưu, quản lý khóa theo ranh giới tin cậy đã thiết kế.
- Phân tách quyền phát log, đọc log, quản lý retention và xóa dữ liệu.
- Cấu hình lưu bất biến hoặc khóa retention khi nền tảng hỗ trợ và tổ chức đã đánh giá cách vận hành.
- Theo dõi thay đổi cấu hình audit, collector, quyền đọc và thao tác export.
- Giữ bản gốc cùng dữ liệu chuẩn hóa, phiên bản parser và tham chiếu để kiểm tra ngược.
- Đối soát theo đợt dữ liệu đã phát và đã tiếp nhận, ghi nhận lỗi thay vì bỏ qua.

Một checksum giúp so sánh nội dung với giá trị kỳ vọng đáng tin cậy. Nó không tự chứng minh nguồn phát, thời điểm phát hoặc việc không có sự kiện bị xóa trước khi tạo checksum. Nếu kẻ sửa file cũng sửa được manifest checksum, khả năng phát hiện thay đổi giảm đáng kể.

Chữ ký số hoặc kho bất biến cũng cần được hiểu đúng theo ranh giới bảo vệ: ai giữ khóa, ai đổi chính sách, dữ liệu được bảo vệ từ thời điểm nào và ai có quyền ngoại lệ. Không nên gọi log là “không thể chối bỏ” chỉ vì đã thêm một trường hash.

### 9.1. Gói bằng chứng cho một lần sử dụng

Gói bằng chứng có thể gồm:

| Thành phần | Nội dung |
|---|---|
| Manifest | emergency_use_id, danh sách artifact, nguồn, thời gian thu, checksum và người đóng gói |
| Quyết định | Sự cố, phạm vi, người quyết định, ngoại lệ đã dùng và lý do |
| Custody | Biên bản nhận/trả phương tiện, người liên quan, định danh bản ghi |
| Truy cập và thao tác | Log gốc, log chuẩn hóa, tham chiếu phiên hoặc recording nếu có |
| Cảnh báo | Thời điểm phát hiện, gửi, retry, xác nhận và escalation |
| Phục hồi | Xác minh kết thúc truy cập, xử lý quyền phát sinh, bảo quản lại phương tiện |
| Khoảng thiếu | Nguồn thiếu, thời gian, ảnh hưởng đến kết luận và việc cần khắc phục |
| Hậu kiểm | Kết luận, người rà soát, hành động tiếp theo và thời hạn |

Việc export cũng phải được ghi audit. Nếu cần che dữ liệu cho người đọc có quyền thấp hơn, tạo bản đã che có tham chiếu nguồn; giữ bản gốc được bảo vệ. Không sửa bản gốc để làm mất phần nhạy cảm rồi tuyên bố đó vẫn là bằng chứng nguyên vẹn.

Thời hạn lưu cần được tổ chức xác định theo nhu cầu điều tra, chính sách và yêu cầu áp dụng. Không có một số ngày cố định có thể suy ra chỉ từ khái niệm break-glass. Khi có yêu cầu bảo toàn bằng chứng cho sự cố, phải xử lý quan hệ giữa retention thông thường và quyết định bảo toàn theo quy trình của tổ chức.

## 10. Tình huống xuyên suốt: khôi phục quyền quản trị khi IdP gián đoạn

Một môi trường lab mất đường đăng nhập quản trị thông thường. Đội vận hành dùng tài khoản khẩn cấp để khôi phục cấu hình kết nối danh tính.

| Thời điểm UTC | Diễn biến | Bằng chứng cần giữ |
|---|---|---|
| 02:00 | Xác nhận mất đường quản trị thông thường | Mã sự cố, kiểm tra lỗi và người ghi nhận |
| 02:01 | Ghi quyết định dùng break-glass theo quy trình | BG-LAB-027, phạm vi khôi phục, người thao tác và người quyết định |
| 02:02 | Bàn giao phương tiện khẩn cấp | Custody record, người giao/nhận, định danh phương tiện |
| 02:03 | Đăng nhập thành công tại đích | Log xác thực gốc, principal_id, nguồn kết nối |
| 02:03 | Phát hiện được sinh, kênh chính lỗi | Detection ID, lỗi gửi, retry và thông báo qua kênh dự phòng |
| 02:04 | Ca trực xác nhận tiếp nhận | Người nhận, thời gian và hành động đầu tiên |
| 02:05 | Thay đổi cấu hình để khôi phục đường thường | Audit thao tác, tài nguyên, kết quả và trạng thái cấu hình |
| 02:07 | Đường quản trị thông thường hoạt động lại | Kết quả kiểm tra và log xác thực tương ứng |
| 02:08 | Kết thúc sử dụng khẩn cấp | Kết quả kiểm tra phiên/quyền, trạng thái phương tiện |
| 02:12 | Collector đồng bộ hết phần dữ liệu đệm | Checkpoint, bản ghi nhận lại, kết quả khử trùng và khoảng thiếu nếu có |
| 03:00 | Rà soát độc lập | Timeline, đối soát phạm vi, đánh giá thiếu sót và việc cần sửa |

Trong tình huống này, một số log thao tác tới trung tâm sau thời điểm kết thúc phiên. Khi dựng timeline, cần phân biệt **thời điểm hành động** và **thời điểm thu nhận**. Không kết luận rằng ca trực chỉ được báo sau 02:12 nếu cảnh báo xác thực đã đến qua một đường khác lúc 02:03.

Nếu chỉ có log “đã gọi API cập nhật cấu hình”, còn kết quả chưa rõ, hồ sơ phải giữ trạng thái chưa xác minh. Cần audit kết quả tại đích hoặc một phép đọc lại cấu hình có quyền phù hợp để kết luận thay đổi đã có hiệu lực.

Nếu trong phiên xuất hiện việc tạo thêm tài khoản quản trị không nằm trong phạm vi khôi phục, hậu kiểm phải làm rõ nhu cầu, quyết định, thời hạn và việc xử lý quyền đó. Không coi mọi hành động trong một phiên có ticket hợp lệ là mặc nhiên hợp lệ.

## 11. Quy trình vận hành và hậu kiểm

### Trước khi cần dùng

Đăng ký danh tính khẩn cấp bằng định danh ổn định; ghi rõ người quản lý và đường truy cập. Kiểm tra nguồn log, rule phát hiện, kênh nhận cảnh báo và quyền truy cập kho bằng chứng. Chuẩn bị cách ghi nhận quyết định, custody và mã sự cố khi công cụ chính không hoạt động.

Diễn tập phải kiểm tra khả năng quan sát cùng với khả năng đăng nhập. Một tài khoản có thể đăng nhập được nhưng không sinh cảnh báo do registry hoặc rule đã sai; đó vẫn là một kết quả cần khắc phục.

### Trong khi sử dụng

Ghi mã lần kích hoạt và sự cố sớm nhất có thể theo quy trình. Dùng danh tính và môi trường thao tác đã định, giữ phạm vi công việc rõ ràng. Nếu thiếu phê duyệt hoặc công cụ ghi nhận chính bị lỗi, phải mô tả đúng ngoại lệ và quyết định dự phòng; không tạo một phê duyệt lùi thời gian để làm hồ sơ có vẻ đầy đủ.

Ca trực theo dõi cảnh báo và tình trạng thu log. Nếu recording không có vì đường đi không qua gateway, ghi rõ điều đó và thu bằng chứng từ nguồn khác. Ghi chú của người thao tác hỗ trợ điều tra nhưng không được trình bày như log hệ thống độc lập.

### Sau khi khôi phục

Xác minh trạng thái phiên và quyền tại đích theo khả năng nền tảng. Xử lý credential, thiết bị và quyền tạm theo loại phương tiện cùng quy trình đã thiết kế. Với phương tiện không phải secret có thể luân chuyển theo cách thông thường, cần biện pháp bảo quản, kiểm kê hoặc thay thế phù hợp; không dùng một lệnh “rotate tất cả” cho mọi trường hợp.

Đối soát danh sách thay đổi thực tế với phạm vi đã quyết định, kiểm tra quyền mới và cấu hình audit. Bảo toàn dữ liệu trước khi chúng hết retention. Người rà soát nên đủ độc lập với người thao tác để phát hiện thiếu sót thay vì chỉ xác nhận báo cáo tự viết.

Kết luận hậu kiểm nên tách ba câu hỏi:

1. Việc dùng break-glass có phù hợp với tình huống và quy trình không?
2. Các hành động có phù hợp phạm vi khôi phục và đã xử lý quyền phát sinh chưa?
3. Bằng chứng đủ đến mức nào, còn điều gì không thể kết luận?

Đóng sự cố kỹ thuật không tự động đồng nghĩa hoàn thành ba nội dung trên. Có thể khôi phục dịch vụ xong nhưng vẫn còn việc đối soát log hoặc xử lý một khoảng thiếu quan sát.

## 12. Bài thực hành trong môi trường giả lập

### 12.1. Thiết lập bài tập

Tạo bộ dữ liệu giả cho một lần sử dụng BG-LAB-027, gồm yêu cầu khẩn cấp, custody record, hai lần xác thực, một thao tác thay đổi cấu hình, một lần cấp quyền tạm và bằng chứng kết thúc. Chỉ dùng tài khoản lab và dữ liệu tự tạo; không đưa credential thật vào bộ dữ liệu.

Bổ sung các tình huống sau:

| Tình huống đưa vào dữ liệu | Kết quả cần quan sát |
|---|---|
| Một lần xác thực thất bại trước lần thành công | Cả hai được giữ, hồ sơ phát hiện có đủ kết quả |
| Một sự kiện nguồn được gửi lại hai lần | Không nhân đôi cùng một hành vi, vẫn truy được bằng chứng nguồn |
| Hai lần xác thực thật trong cùng một phút | Không bị gộp mất vì khóa khử trùng quá rộng |
| Log thao tác đến muộn sau khi collector phục hồi | Timeline dùng đúng thời gian nguồn, phát hiện không bỏ dữ liệu trễ |
| Không có session_id tại nguồn | Hệ thống giữ null và mô tả cơ sở liên kết thay thế |
| Không có recording của gateway | Hồ sơ công khai khoảng quan sát này, không báo đã ghi hình |
| Kênh cảnh báo chính không gửi được | Có retry, đường dự phòng và bằng chứng người trực tiếp nhận |
| Quyền tạm chưa có xác minh hết hạn | Hồ sơ còn việc phải xử lý, không đóng hoàn tất theo thời gian dự kiến |

### 12.2. Sản phẩm cần tạo

Người học lập một timeline với hai cột thời gian nguồn và thu nhận; bảng liên kết person_id, principal_id, emergency_use_id cùng source_event_id; hồ sơ cảnh báo có trạng thái chuyển phát và xác nhận; cuối cùng là manifest bằng chứng và bản mô tả khoảng thiếu.

Với mỗi kết luận trong báo cáo, chỉ rõ nó dựa vào artifact nào. Ví dụ, kết luận “OPS-042 đã nhận phương tiện” dựa vào custody record; kết luận “tài khoản emergency-admin-02 đã đăng nhập” dựa vào audit xác thực. Việc liên kết hai kết luận cần thêm cơ sở và có thể vẫn chỉ ở trạng thái tạm thời.

### 12.3. Tiêu chí hoàn thành bài tập

Bài tập đạt yêu cầu khi không bỏ mất sự kiện lặp thật, xử lý được gửi lại và đến muộn, không ghi bí mật, không tự tạo dữ liệu nguồn còn thiếu, và không đóng hồ sơ khi quyền tạm chưa được xác minh.

Báo cáo phải phân biệt rõ sự kiện quan sát được, khai báo của con người và suy luận của người điều tra. Một kết quả ghi rõ “chưa xác định do thiếu log đích từ 02:05 đến 02:06” có giá trị hơn một khẳng định chắc chắn không có bằng chứng.

## 13. Các lỗi thường gặp và cách sửa thiết kế

| Lỗi | Hệ quả | Cách sửa |
|---|---|---|
| Chỉ tìm tên tài khoản chứa breakglass | Bỏ sót danh tính đổi tên hoặc đặt tên khác | Dùng registry với định danh ổn định, phạm vi và lịch sử thay đổi |
| Chỉ ghi đăng nhập thành công | Mất dấu nỗ lực truy cập và bối cảnh thất bại | Thu cả kết quả thất bại, từ chối và thay đổi cơ chế |
| Chỉ giữ audit của PAM | Không thấy đường truy cập trực tiếp | Bổ sung audit danh tính và hệ thống đích |
| Tin incident_id do người dùng nhập | Có thể gắn một mã hợp lệ cho hành vi ngoài phạm vi | Giữ nguồn khai báo và đối soát với hồ sơ quyết định |
| Tắt rule trong thời gian diễn tập | Không kiểm chứng được đường phát hiện | Giữ phát hiện, gắn kế hoạch diễn tập đã xác minh |
| Có email gửi đi là coi đã xử lý | Không ai nhận trách nhiệm khi kênh hoặc ca trực lỗi | Theo dõi xác nhận và escalation |
| Xóa trùng theo tài khoản và phút | Làm mất nhiều hành vi thật gần nhau | Dùng định danh sự kiện có phạm vi và giữ bản thô |
| Hết thời hạn là coi đã thu hồi | Token, session hoặc quyền khác có thể còn | Xác minh theo cơ chế cụ thể và ghi kết quả |
| Điền phần thiếu để hồ sơ đủ trường | Biến suy luận thành bằng chứng giả | Giữ null, trạng thái chưa xác minh và gap record |
| Chỉ thêm hash rồi gọi log bất biến | Không bảo vệ được nguồn hoặc manifest bị sửa | Thiết kế ranh giới tin cậy, quyền quản trị và cách kiểm chứng |
| Hoàn tất sự cố là xóa dữ liệu tạm ngay | Mất bằng chứng cần cho hậu kiểm | Phân loại artifact, bảo toàn theo quy trình và kiểm soát quyền xóa |

## 14. Tài liệu tham khảo và điểm áp dụng

Microsoft khuyến nghị theo dõi hoạt động đăng nhập và audit của tài khoản khẩn cấp, tạo thông báo khi chúng được sử dụng, đồng thời bảo toàn log và rà soát sau lần sử dụng. Đây là một ví dụ triển khai cụ thể cho nguyên tắc quan sát và hậu kiểm được bàn trong bài. Tham khảo [Manage emergency access accounts in Microsoft Entra ID](https://learn.microsoft.com/en-us/entra/identity/role-based-access-control/security-emergency-access).

Schema chuẩn hóa, tên sự kiện, kiến trúc dự phòng, logic phát hiện và bài tập ở trên là các đề xuất minh họa của bài học. Khi áp dụng vào một nền tảng, cần ánh xạ sang nguồn log thực tế, quyền đọc, cơ chế phiên và khả năng bảo toàn mà nền tảng đó cung cấp.
