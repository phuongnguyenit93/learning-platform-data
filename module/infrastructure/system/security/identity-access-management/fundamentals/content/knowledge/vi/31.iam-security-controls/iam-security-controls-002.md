# Least privilege

## 1. Nguyên tắc ít quyền nhất là gì?

**Least privilege**, hay nguyên tắc ít quyền nhất, yêu cầu mỗi chủ thể chỉ được cấp những quyền cần thiết để thực hiện công việc đã được phép, trên đúng tài nguyên, trong điều kiện và khoảng thời gian phù hợp.

Chủ thể có thể là người dùng, quản trị viên, ứng dụng, service account, job nền hoặc pipeline triển khai. Quyền cần được xét theo hành động và tác động thực tế, không chỉ theo tên role.

Ví dụ, một job tạo báo cáo doanh thu cần đọc dữ liệu tổng hợp của tenant An và ghi tệp báo cáo vào khu vực lưu trữ đã xác định. Nó không vì thế cần quyền:

- Đọc toàn bộ hồ sơ nhân viên của mọi tenant.
- Sửa hoặc xóa hóa đơn.
- Cấp role cho người dùng.
- Tạo credential quản trị.
- Thay đổi chính sách truy cập của kho dữ liệu.

Quyền rộng hơn nhu cầu làm tăng tác động nếu credential bị lộ, code có lỗi hoặc một thao tác vận hành bị nhầm. Least privilege giảm phạm vi có thể bị ảnh hưởng, nhưng không thay thế xác thực, bảo vệ credential, kiểm tra đầu vào hoặc giám sát.

“Ít nhất” cần dựa trên công việc hợp lệ và khả năng vận hành đã được xác định. Cắt quyền tùy ý đến mức không thể hoàn thành nghiệp vụ không phải một thiết kế tốt; cấp quyền quản trị để tránh phân tích nhu cầu cũng không đáp ứng nguyên tắc này.

## 2. Phân tích quyền theo nhiều chiều

Một grant nên trả lời được các câu hỏi sau:

| Chiều | Câu hỏi | Ví dụ |
|---|---|---|
| Chủ thể | Ai hoặc workload nào nhận quyền? | `svc-report-generator` |
| Hành động | Được thực hiện thao tác nào? | Đọc dữ liệu tổng hợp |
| Tài nguyên | Trên đối tượng hoặc phạm vi nào? | Báo cáo của tenant An |
| Dữ liệu | Được xem trường hoặc mức chi tiết nào? | Tổng doanh thu, không có thông tin cá nhân |
| Điều kiện | Điều kiện gì phải còn đúng? | Tenant hoạt động, grant chưa bị thu hồi |
| Thời gian | Quyền có hiệu lực khi nào và đến bao giờ? | Trong thời gian thực hiện tác vụ đã duyệt |
| Ủy quyền | Có được cấp tiếp hoặc hành động thay người khác không? | Không được cấp role cho chủ thể khác |
| Môi trường | Áp dụng ở hệ thống nào? | Production của đúng ứng dụng |

Nếu chỉ ghi “quyền đọc”, vẫn chưa rõ được đọc dữ liệu nào, thuộc tenant nào hoặc có được xuất hàng loạt hay không. Quyền đọc toàn bộ dữ liệu nhạy cảm có thể gây tác động lớn dù không sửa được bản ghi.

Tương tự, quyền “vận hành ứng dụng” không tự bao gồm quyền sửa chính sách IAM, đọc secret hay thay đổi danh tính workload. Những khả năng này cần được đánh giá riêng.

## 3. Phân biệt least privilege với các kiểm soát liên quan

| Kiểm soát | Mục tiêu | Quan hệ với least privilege |
|---|---|---|
| Xác thực | Xác minh chủ thể | Biết ai đang dùng quyền, chưa xác định quyền có quá rộng không |
| MFA | Tăng độ bảo đảm của xác thực | Giảm một số rủi ro chiếm tài khoản, không thu hẹp quyền đã cấp |
| Default deny | Từ chối khi không có căn cứ cho phép phù hợp | Là nền tảng hữu ích, nhưng grant cho phép vẫn có thể quá rộng |
| Need-to-know | Giới hạn tiếp cận thông tin theo nhu cầu công việc | Bổ sung chiều phạm vi dữ liệu |
| Separation of duties | Tách các nhiệm vụ có xung đột | Ngăn một chủ thể tự hoàn thành toàn bộ chuỗi nhạy cảm |
| Just-in-time access | Chỉ kích hoạt quyền khi cần | Giảm thời gian tồn tại của đặc quyền |
| Audit | Ghi nhận hành động và thay đổi quyền | Cung cấp bằng chứng để đánh giá và điều tra |

Một tài khoản ADMIN được bảo vệ bằng MFA vẫn có quyền ADMIN. Nhật ký rất đầy đủ cũng không ngăn được một hành động quá quyền nếu chính sách vẫn cho phép.

Default deny cần được áp dụng cho đúng ranh giới hành động và tài nguyên. Một chính sách mặc định từ chối nhưng có một grant “mọi hành động trên mọi tài nguyên” cho toàn bộ nhóm nhân viên vẫn cấp quyền quá rộng.

## 4. Xác định nhu cầu trước khi tạo role

Có thể bắt đầu bằng việc mô tả công việc thay vì chọn sẵn một role có tên gần giống.

Ví dụ đối với nhân viên hỗ trợ:

```text
Công việc: kiểm tra trạng thái xử lý yêu cầu của khách hàng.
Cần: xem mã yêu cầu, trạng thái và lịch sử xử lý trong phạm vi được giao.
Không mặc nhiên cần: đọc secret, xuất mọi hồ sơ, thay đổi thanh toán,
                    cấp quyền hoặc truy cập mọi tenant.
```

Một quy trình xác định quyền:

1. Liệt kê các tác vụ hợp lệ của vị trí hoặc workload.
2. Ánh xạ mỗi tác vụ sang hành động nghiệp vụ cụ thể.
3. Xác định tập tài nguyên và dữ liệu cần thiết.
4. Xác định điều kiện và thời hạn.
5. Kiểm tra các khả năng cấp tiếp quyền hoặc truy cập gián tiếp.
6. Ghi lại chủ sở hữu quyền và lý do cấp.
7. Xác minh tác vụ hợp lệ hoạt động, còn các hành động ngoài phạm vi bị chặn.

Không nên sao chép toàn bộ quyền của một người đang làm cùng vị trí mà không đánh giá. Người đó có thể tích lũy nhiều quyền từ dự án cũ hoặc giữ một ngoại lệ đã hết mục đích.

Các quyền phục vụ vận hành ít gặp, như phục hồi sau sự cố hoặc xử lý công việc cuối kỳ, vẫn cần được đưa vào mô hình. Có thể tách chúng thành quyền tạm thời hoặc một quy trình đặc quyền có điều kiện, thay vì cấp thường trực cho mọi người.

## 5. Thiết kế role và policy đủ hẹp

### 5.1. Role mô tả trách nhiệm

Một role như `REPORT_VIEWER` có thể gom các quyền phục vụ việc xem báo cáo. Tên role chỉ là nhãn; cần kiểm tra các permission thực tế bên trong.

Ví dụ:

| Role minh họa | Quyền hợp lý theo mô hình đã chọn | Quyền cần tách riêng |
|---|---|---|
| REPORT_VIEWER | Xem báo cáo được phân công | Xóa dữ liệu nguồn |
| REPORT_OPERATOR | Tạo lại báo cáo trong phạm vi được phép | Cấp role quản trị |
| TENANT_MEMBER_MANAGER | Quản lý một số membership của tenant | Tự cấp quyền cao hơn phạm vi được ủy nhiệm |
| DEPLOY_OPERATOR | Triển khai bản phát hành đã được phê duyệt | Tự sửa toàn bộ chính sách danh tính nền tảng |

Không cần tạo một role riêng cho mọi tổ hợp tài nguyên nếu điều kiện có thể được biểu diễn rõ bằng policy. Ví dụ, role cho phép hành động đọc nhưng policy giới hạn tài nguyên theo tenant và nhóm dự án.

### 5.2. RBAC và ABAC có thể kết hợp

RBAC giúp gom quyền theo vai trò. ABAC bổ sung điều kiện dựa trên thuộc tính chủ thể, tài nguyên và ngữ cảnh.

Một quy tắc khái niệm:

```text
Cho phép document.read khi:
    subject có role hỗ trợ đọc tài liệu
    AND membership trong tenant mục tiêu còn ACTIVE
    AND document.tenant_id khớp tenant mục tiêu
    AND subject thuộc nhóm được đọc tài liệu
    AND các điều kiện bảo vệ khác của tài liệu đạt
```

Role không phải đường tắt để bỏ qua tenant hoặc thuộc tính tài nguyên. Các thuộc tính cũng phải đến từ nguồn có thẩm quyền; không tin `department=Finance` hay `tenant_id` do client tự khai.

### 5.3. Hạn chế wildcard và quyền quá tổng quát

Các grant với “mọi tài nguyên”, “mọi hành động” hoặc role quản trị tổng quát cần được phân tích kỹ vì chúng có thể bao gồm những hành động mới được thêm vào hệ thống sau này.

Nếu một wildcard là cần thiết trong phạm vi xác định, cần hiểu phạm vi mở rộng thực tế, chủ thể được sử dụng và kiểm soát đi kèm. Không coi một tên prefix hoặc quy ước đặt tên là ranh giới bảo mật nếu nơi thực thi không kiểm tra nó.

Quyền được định nghĩa đủ cụ thể cũng giúp phê duyệt và audit có ý nghĩa hơn: “đọc báo cáo tổng hợp tenant An” dễ đánh giá hơn “quyền ứng dụng”.

## 6. Đánh giá quyền hiệu lực, không chỉ grant nhìn thấy

Một subject có thể nhận quyền qua nhiều đường:

- Gán trực tiếp.
- Role trong một tenant.
- Nhóm và nhóm lồng nhau.
- Role được kế thừa.
- Chính sách gắn với tài nguyên.
- Phiên hoặc grant tạm thời.
- Cơ chế hành động thay hoặc sử dụng danh tính khác.
- Quyền sửa code, cấu hình hoặc credential của một workload mạnh hơn.

Gỡ một role trực tiếp chưa chắc làm mất quyền nếu nhóm khác vẫn cấp quyền tương tự. Một role có tên “chỉ đọc” cũng chưa chắc ít quyền nếu nó cho đọc các secret có thể dùng để truy cập hệ thống khác.

Có thể dùng công thức khái niệm:

```text
quyền hiệu lực =
    kết quả kết hợp mọi nguồn cấp quyền
    với các giới hạn, điều kiện và quy tắc từ chối của hệ thống
```

Đây không phải một phép cộng hoặc một thứ tự ưu tiên chung cho mọi sản phẩm IAM. Cần hiểu chính xác cơ chế kết hợp policy của hệ thống đang dùng; không mặc định mọi loại DENY hoặc mọi loại giới hạn đều có cùng hiệu lực.

### 6.1. Quyền gián tiếp

Xét một chuỗi minh họa:

```text
Sửa cấu hình của job
        |
        v
Thay đổi hành vi job chạy bằng service account mạnh
        |
        v
Tác động tới tài nguyên ngoài nhu cầu của người sửa
```

Nếu chỉ nhìn permission sửa cấu hình, có thể đánh giá thấp đặc quyền thực tế. Cần kiểm tra quyền thay đổi môi trường thực thi, dùng danh tính workload, đọc credential, tạo token hoặc sửa chính sách.

Mục tiêu là xác định các đường dẫn đặc quyền có thể xảy ra trong kiến trúc, rồi giới hạn bằng quyền quản trị phù hợp, phê duyệt và cách ly. Không chỉ đếm số permission trong một role.

### 6.2. Phạm vi tenant và môi trường

Một người có thể là ADMIN trong tenant An và VIEWER trong tenant Bình. Quyền phải được gắn với từng quan hệ, không gom ADMIN thành thuộc tính toàn cục của user.

Development, staging và production cũng cần được xét như các phạm vi riêng. Credential phát triển không nên tự truy cập production chỉ vì dùng chung tên service hoặc cùng một hệ thống đăng nhập.

## 7. Least privilege cho workload

Workload thường chạy lặp lại và có khả năng xử lý nhiều dữ liệu, nên credential rộng có thể tạo tác động đáng kể ngay cả khi không có người đăng nhập.

Các nguyên tắc thiết kế:

**Danh tính riêng theo trách nhiệm.** Tách job đọc báo cáo khỏi thành phần quản trị membership hoặc migration dữ liệu khi nhu cầu và ranh giới cho phép.

**Grant theo tài nguyên cần dùng.** Một service tạo báo cáo không cần đọc toàn bộ kho secret hoặc mọi bucket.

**Tách quyền runtime và triển khai.** Tiến trình ứng dụng không mặc nhiên cần quyền thay schema, tạo user cơ sở dữ liệu hoặc sửa danh tính chính nó.

**Giới hạn vòng đời credential.** Ưu tiên cơ chế có thể quản lý thời hạn, thu hồi và xoay phù hợp. Credential ngắn hạn nhưng mang quyền rất rộng vẫn là credential quá quyền.

**Kiểm soát việc sử dụng danh tính khác.** Quyền gắn một service account mạnh vào job hoặc tạo credential của nó phải được đánh giá như một khả năng đặc quyền.

### Ví dụ: workload tạo báo cáo

Giả sử `svc-report-generator` chỉ cần tổng hợp doanh thu đã được hệ thống chuẩn bị cho tenant An.

| Nhu cầu | Grant phù hợp trong ví dụ | Quyền không cần |
|---|---|---|
| Lấy số liệu | Đọc tập dữ liệu tổng hợp được cấp cho tenant An | Đọc mọi bảng nghiệp vụ |
| Tạo báo cáo | Ghi object dưới vùng báo cáo của tenant An | Xóa mọi object trong kho |
| Đọc cấu hình cần thiết | Đọc đúng cấu hình hoặc secret được chỉ định | Liệt kê và đọc toàn bộ secret |
| Gửi kết quả | Gọi endpoint gửi báo cáo với phạm vi cần thiết | Cấp role hoặc tạo tài khoản |
| Vận hành | Ghi log có kiểm soát và metric cần thiết | Sửa policy IAM của nền tảng |

Nếu workload phục vụ nhiều tenant, kiến trúc cần có cơ chế kiểm tra tenant và grant ở mỗi tác vụ hoặc cơ chế cách ly tương ứng. Không lấy tenant ID trong payload làm bằng chứng quyền chỉ vì message đến từ queue nội bộ.

Một service có danh tính hợp lệ vẫn phải bị giới hạn theo hành động và tài nguyên. Xác thực workload không đồng nghĩa service có quyền toàn nền tảng.

## 8. Giảm thời gian tồn tại của đặc quyền

Một quyền nhạy cảm thường trực tồn tại cả khi chủ thể không sử dụng nó. Có thể tách:

- Đủ điều kiện xin kích hoạt quyền.
- Đã được phê duyệt cho một nhiệm vụ.
- Quyền đang ACTIVE trong một thời gian cụ thể.
- Quyền đã hết hạn hoặc bị thu hồi.

Ví dụ, kỹ sư vận hành bình thường dùng tài khoản không có đặc quyền quản trị. Khi cần xử lý sự cố, họ yêu cầu một quyền cụ thể với mã công việc, phạm vi tài nguyên, thời hạn và cơ chế xác nhận phù hợp.

Một hồ sơ cấp quyền tạm thời có thể gồm:

```json
{
  "subject_id": "u-174",
  "tenant_id": "tenant-an",
  "permission": "report.retry",
  "resource_scope": "report-job-508",
  "reason_reference": "operation-728",
  "approved_by": "u-009",
  "expires_at": "2026-06-12T10:30:00Z"
}
```

Đây là cấu trúc minh họa, không phải một policy có thể đem áp dụng nguyên trạng. Máy chủ phải xác minh người phê duyệt có quyền cấp permission đó và người yêu cầu không thể sửa phạm vi hoặc hạn hết hiệu lực sau khi được duyệt.

Thời điểm hết hạn phải được nơi thực thi kiểm tra hoặc được hiện thực bằng cơ chế thu hồi có hiệu lực. Chỉ có một cột `expires_at` trong cơ sở dữ liệu nhưng API bỏ qua cột đó thì quyền chưa thực sự có thời hạn.

Tương tự, một scheduler thu hồi có thể lỗi hoặc chạy trễ. Thiết kế cần xác định rõ hành vi khi hết hạn, độ trễ chấp nhận được và cách xử lý phiên hoặc token đã phát hành.

Tài khoản khẩn cấp phục vụ phục hồi cũng cần phạm vi, bảo vệ credential, giám sát và quy trình đánh giá sau sử dụng. Nó không nên trở thành tài khoản dùng thường ngày vì tiện lợi.

## 9. Quản lý toàn bộ vòng đời quyền

### 9.1. Cấp quyền

Yêu cầu cấp quyền cần có mục đích, phạm vi, thời hạn và người chịu trách nhiệm. Người phê duyệt phải có thẩm quyền đối với quyền được cấp, không chỉ có khả năng bấm nút trên một màn hình quản trị.

Quyền quản lý thành viên nên có giới hạn cấp tiếp. Một người được mời thành viên không vì thế được cấp OWNER cho bất kỳ ai hoặc tự nâng role của chính mình.

### 9.2. Thay đổi công việc

Khi chuyển nhóm hoặc nhiệm vụ, chỉ thêm quyền mới sẽ dẫn tới privilege creep: quyền cũ tiếp tục tồn tại và tích lũy qua thời gian.

Cần đánh giá cả việc thêm quyền mới lẫn thu hồi quyền không còn mục đích. Không mặc định mọi quyền cũ đều được giữ để hỗ trợ bàn giao; nếu cần bàn giao, nên xác định thời hạn và phạm vi rõ ràng.

### 9.3. Rà soát

Rà soát cần xem quyền hiệu lực, đường cấp, lý do còn cần và chủ sở hữu nghiệp vụ. Dữ liệu sử dụng hỗ trợ đánh giá nhưng không phải bằng chứng duy nhất.

Một permission chưa được dùng gần đây có thể phục vụ sự cố hiếm hoặc tác vụ cuối kỳ. Ngược lại, một permission được dùng thường xuyên vẫn có thể không phù hợp với trách nhiệm được phép. Cần kết hợp dữ liệu quan sát với mô tả công việc và chính sách.

Tần suất rà soát nên dựa trên rủi ro và đặc điểm quyền, thay vì áp dụng một khoảng thời gian tùy ý cho mọi hệ thống.

### 9.4. Thu hồi

Thu hồi cần làm mất khả năng sử dụng quyền tại các điểm thực thi, bao gồm phiên, token, cache, credential và job có liên quan.

Gỡ role trong giao diện chưa chứng minh token mang snapshot quyền cũ đã mất hiệu lực. Hệ thống cần có cơ chế kiểm tra hiện trạng hoặc thời hạn và độ trễ thu hồi được xác định.

Khi một người rời tenant An, cần thu hồi các quyền thuộc tenant An mà vẫn bảo toàn quan hệ hợp lệ ở tenant Bình. Danh tính toàn cục và membership là hai vòng đời cần phân biệt.

## 10. Hiện thực nguyên tắc trong ứng dụng

Một ứng dụng có thể thực thi least privilege bằng cách kết hợp:

- Identity context đã được xác minh.
- Permission hoặc role có phạm vi.
- Thuộc tính tài nguyên từ nguồn có thẩm quyền.
- Kiểm tra quyền trước tác động.
- Truy vấn dữ liệu có tenant scope.
- Giới hạn trường và mức chi tiết được trả.
- Giới hạn credential ở tầng dữ liệu và dịch vụ phụ thuộc.

Pseudocode cho một hành động đọc báo cáo:

```text
readReport(request):
    identity = authenticate(request)
    tenant = resolveRequestedTenant(request)

    report = findReportWithinTenant(tenant.id, request.reportId)
    state = loadCurrentAuthorizationState(identity, tenant, report)

    decision = evaluate(
        subject = identity.subject,
        action = "report.read",
        resource = report,
        state = state
    )

    if decision is not ALLOW:
        reject()

    if cannotApplyRequiredRestrictions(decision):
        reject()

    return renderOnlyPermittedFields(report, decision)
```

Đây là pseudocode mô tả trách nhiệm. Nó không hàm ý request tự cung cấp một identity đáng tin cậy hoặc việc đọc báo cáo tự cho phép tải toàn bộ dữ liệu nguồn.

Các hành động quản trị cần kiểm tra riêng. Một endpoint chỉnh hồ sơ không được cho phép cập nhật mọi field của entity, trong đó có role hoặc tenant, chỉ vì người dùng có quyền chỉnh tên hiển thị. Cần xác định những trường được phép thay đổi và đánh giá hành động nhạy cảm theo đúng permission.

Ở tầng dữ liệu, credential runtime nên được giới hạn theo chức năng cần thiết. Nếu ứng dụng chỉ cần đọc một tập dữ liệu tổng hợp, cấp quyền quản trị cơ sở dữ liệu sẽ làm mất một lớp giới hạn quan trọng khi ứng dụng bị lỗi hoặc bị chiếm quyền.

## 11. Kiểm chứng bằng cả trường hợp được phép và bị từ chối

Một cấu hình chỉ được kiểm tra bằng việc “tác vụ chạy thành công” chưa chứng minh least privilege.

Với workload báo cáo tenant An, có thể xác định ma trận kỳ vọng:

| Tình huống | Kết quả mong đợi |
|---|---|
| Đọc dữ liệu tổng hợp tenant An được cấp | Cho phép |
| Đọc dữ liệu tenant Bình | Từ chối |
| Đọc bảng có thông tin ngoài phạm vi | Từ chối |
| Sửa dữ liệu nguồn | Từ chối |
| Ghi báo cáo vào vùng lưu đã cấp | Cho phép |
| Xóa vùng báo cáo ngoài grant | Từ chối |
| Đọc secret không được cấp | Từ chối |
| Tạo hoặc gán role quản trị | Từ chối |
| Chạy sau khi grant hết hạn | Từ chối theo cơ chế hiệu lực đã thiết kế |
| Gọi đường nội bộ thay cho endpoint ngoài | Vẫn cần quyền phù hợp |
| Dùng credential môi trường phát triển cho production | Từ chối khi không có grant tương ứng |

Đối với người dùng, cần kiểm tra quyền do nhóm, kế thừa, ủy quyền và chính sách tài nguyên. Sau khi thu hồi, cần xác minh các đường cấp khác không tiếp tục giữ lại khả năng tương tự.

Một rollout thu hẹp quyền có thể thực hiện theo phạm vi nhỏ, theo dõi tác vụ hợp lệ và có phương án phục hồi được phê duyệt. Phương án xử lý sự cố không nên là tự động gắn quyền quản trị toàn hệ thống mỗi khi xuất hiện lỗi thiếu quyền.

Khi một kiểm tra thất bại do hệ thống phân quyền không sẵn sàng, lỗi đó không tự tạo ra permission mới. Cách hoạt động suy giảm cần được định nghĩa trước, với giới hạn hiệu lực và phạm vi rõ ràng.

## 12. Quan sát và những hiểu lầm thường gặp

Có thể theo dõi những chỉ dấu như:

- Số grant đặc quyền thường trực và chủ sở hữu của chúng.
- Quyền có wildcard hoặc phạm vi tài nguyên rất rộng.
- Grant tạm thời còn tồn tại sau thời hạn.
- Credential không có chủ sở hữu hoặc quá lâu chưa được đánh giá.
- Người có quyền từ nhiều nhóm chồng lấn.
- Thời gian từ quyết định thu hồi đến khi quyền mất hiệu lực.
- Ngoại lệ chưa có ngày đánh giá lại.
- Lỗi nghiệp vụ phát sinh sau một lần thu hẹp quyền.

Các chỉ dấu phục vụ quyết định, không phải mục tiêu để tối ưu bằng cách bỏ qua nhu cầu thật. Một role ít permission nhưng có quyền cấp role quản trị vẫn có thể tạo đặc quyền rất lớn.

| Hiểu lầm | Điều cần hiểu đúng |
|---|---|
| Có MFA là đã ít quyền | MFA bảo vệ xác thực; phạm vi quyền vẫn cần thiết kế riêng |
| Read-only luôn an toàn | Quyền đọc có thể làm lộ dữ liệu nhạy cảm hoặc credential |
| Service nội bộ nên được tin toàn bộ | Workload cũng cần grant và giới hạn tài nguyên |
| Token ngắn hạn sửa được quyền quá rộng | Nó giảm thời gian tồn tại, không thu hẹp các hành động đang được cấp |
| Gỡ một role là hết quyền | Các nhóm, policy và đường ủy quyền khác có thể vẫn cấp quyền |
| Role có tên VIEWER thì chắc chỉ xem | Cần kiểm tra permission và tài nguyên thực tế |
| Không dùng gần đây thì tự động xóa | Cần xét tác vụ hiếm, trách nhiệm và bằng chứng nghiệp vụ |
| Cấp ADMIN tạm rồi quên thu hồi vẫn chấp nhận được | Quyền tạm cần cơ chế hết hiệu lực và kiểm chứng |
| Cắt mọi quyền là least privilege tốt nhất | Quyền cần đủ cho công việc đã được phép, có vận hành và phục hồi phù hợp |

Least privilege là một quá trình duy trì sự phù hợp giữa công việc và quyền hiệu lực. Thiết kế tốt làm rõ ai cần làm gì, trên dữ liệu nào, trong bao lâu; giới hạn cả quyền trực tiếp lẫn khả năng đặc quyền gián tiếp; và xác nhận quyền cũ thực sự mất hiệu lực khi nhu cầu kết thúc.
