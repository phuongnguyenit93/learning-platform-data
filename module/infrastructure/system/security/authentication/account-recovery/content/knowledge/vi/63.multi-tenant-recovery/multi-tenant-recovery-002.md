# Tenant isolation — Cô lập tenant trong khôi phục tài khoản

## 1. Vì sao luồng khôi phục dễ làm thủng ranh giới tenant?

Trong hệ thống nhiều tenant, mỗi tổ chức hoặc không gian sử dụng có ranh giới dữ liệu, quản trị và chính sách riêng. Luồng đăng nhập thông thường thường có sẵn phiên người dùng để xác định ngữ cảnh, nhưng khôi phục tài khoản lại diễn ra khi người dùng chưa đăng nhập hoặc đã mất phương thức xác thực. Vì vậy, nếu thiết kế chỉ dựa vào một trường `tenantId` do trình duyệt gửi, hệ thống có thể xử lý sai tổ chức ngay từ bước đầu.

**Tenant isolation** trong khôi phục tài khoản là việc bảo đảm một yêu cầu chỉ đọc dữ liệu, đánh giá chính sách, cấp quyền và thay đổi trạng thái trong phạm vi tenant đã được xác định và cho phép. Ranh giới này phải được giữ ở mọi thành phần, không chỉ tại giao diện hoặc endpoint đầu tiên.

Đối với `SECURITY_AUTHENTICATION_ACCOUNT_RECOVERY`, việc cô lập cần bao phủ khôi phục mật khẩu, MFA, passkey và thiết bị xác thực; đồng thời bảo vệ bằng chứng danh tính, quyết định quản trị, token dùng một lần, phiên và các tác vụ chống lạm dụng.

### Ví dụ mở đầu

Hai tenant `tenant-red` và `tenant-blue` cùng có một hồ sơ sử dụng địa chỉ `user@example.test`. Người dùng bắt đầu khôi phục trong cổng của `tenant-red`, nhưng một truy vấn chỉ tìm theo email và lấy kết quả đầu tiên. Nếu kết quả thuộc `tenant-blue`, liên kết khôi phục có thể tác động đến tài khoản sai tổ chức.

Ngay cả khi bước tìm tài khoản đúng, lỗi vẫn có thể xuất hiện ở bước sau: token không gắn tenant, worker mất ngữ cảnh, cache dùng khóa chỉ gồm email hoặc người duyệt có quyền ở red nhưng lại phê duyệt yêu cầu thuộc blue.

## 2. Xác định mô hình danh tính trước khi đặt ranh giới

Không phải hệ thống nhiều tenant nào cũng lưu tài khoản giống nhau. Cần phân biệt các đối tượng sau:

| Đối tượng | Ý nghĩa | Câu hỏi cần làm rõ |
|---|---|---|
| Danh tính toàn cục | Một chủ thể dùng chung trên nền tảng | Mật khẩu hoặc yếu tố xác thực có tác động đến mọi tenant không? |
| Tài khoản thuộc tenant | Một tài khoản được sở hữu trong một tenant cụ thể | Credential có độc lập với tenant khác không? |
| Quan hệ thành viên | Liên kết chủ thể với tenant và quyền trong tenant | Khôi phục truy cập có làm thay đổi membership không? |
| Yêu cầu khôi phục | Một quy trình có mục đích, căn cứ và thời hạn | Nó được phép thay đổi đối tượng nào? |

### Mô hình tài khoản độc lập theo tenant

Trong mô hình này, tài khoản red và blue có thể dùng cùng email nhưng có credential, chính sách và vòng đời riêng. Một thao tác khôi phục cho red không được đổi MFA hoặc mật khẩu của blue.

### Mô hình danh tính toàn cục, nhiều membership

Trong mô hình này, đổi mật khẩu của một danh tính toàn cục có thể ảnh hưởng khả năng đăng nhập vào nhiều tenant. Không thể biến một thao tác toàn cục thành thao tác cục bộ chỉ bằng cách thêm `tenantId` vào URL.

Quản trị viên của red không nên tự có quyền đặt lại credential toàn cục cho người dùng rồi gián tiếp tác động đến blue. Hệ thống cần một luồng khôi phục toàn cục với thẩm quyền và chính sách tương ứng, hoặc một hành động cục bộ thực sự chỉ giới hạn ở membership của red.

Phạm vi quyết định phải phản ánh tác động thực tế. Nếu credential là toàn cục, việc khôi phục không được mô tả như thể chỉ thay đổi một tenant. Đồng thời, quy trình toàn cục cũng không được tự cấp lại membership hoặc vai trò đã bị thu hồi trong các tenant.

## 3. Các bất biến cần giữ xuyên suốt

Với mô hình tài khoản thuộc tenant, một tập bất biến minh họa là:

```text
request.tenantId == account.tenantId
challenge.tenantId == request.tenantId
grant.tenantId == request.tenantId
approval.tenantId == request.tenantId
evidence.tenantId == request.tenantId
operation.tenantId == request.tenantId
```

Các so sánh phải đi cùng định danh yêu cầu, tài khoản và mục đích. Cùng tenant không có nghĩa mọi yêu cầu hoặc mọi tài khoản trong tenant đều dùng chung quyền khôi phục.

Những bất biến khác gồm:

- Một quản trị viên chỉ tác động đến tenant và hành động mà họ có thẩm quyền.
- Token của tenant này không đổi được thành quyền trên tenant khác.
- Chính sách, template và đích thông báo được lấy từ cấu hình có thẩm quyền của phạm vi đang xử lý.
- Thiếu tenant hoặc ngữ cảnh mâu thuẫn không được chuyển thành truy vấn toàn hệ thống.
- Một tác vụ nền không được kế thừa ngữ cảnh tenant từ tác vụ trước.
- Các đầu ra như log, bằng chứng, thông báo và tệp xuất không làm lộ dữ liệu tenant khác.

Nếu có luồng toàn cục hoặc quy trình qua nhiều tenant được phép, cần mô hình hóa phạm vi đó rõ ràng. Không dùng tenant mặc định hay quyền bỏ qua kiểm tra như một ngoại lệ ngầm cho các thao tác khó phân loại.

## 4. Xác định tenant không đồng nghĩa xác thực người yêu cầu

Một yêu cầu công khai có thể xác định tenant qua tên miền đã đăng ký, đường dẫn cổng tổ chức hoặc mã tổ chức. Đây là bước định tuyến tới đúng ngữ cảnh, chưa chứng minh người gửi là thành viên hoặc chủ tài khoản.

Hệ thống nên chuyển các thông tin bên ngoài thành một định danh tenant chuẩn qua cấu hình được kiểm soát. Không tin trực tiếp một header, tên miền hay giá trị query chỉ vì nó có định dạng hợp lệ.

Ví dụ:

```text
Thông tin định tuyến do client gửi
    → đối chiếu với cấu hình tenant được chấp nhận
    → tạo ngữ cảnh tenant chuẩn
    → tìm tài khoản và áp dụng chính sách trong phạm vi đó
    → thực hiện xác minh danh tính theo luồng khôi phục
```

Với endpoint đã xác thực, tenant được chọn còn phải phù hợp với quyền của người gọi hoặc với một quyền thao tác đã cấp. Người có membership ở nhiều tenant không được tự động dùng quyền của tenant này cho tenant khác.

Với endpoint bắt đầu khôi phục chưa xác thực, hệ thống có thể cho phép gửi yêu cầu trong tenant được xác định theo chính sách công khai. Điều đó không cấp quyền đọc hồ sơ, nhận biết membership ở tenant khác hoặc thay đổi yếu tố xác thực trước khi hoàn tất các điều kiện cần thiết.

Nếu nguồn tenant từ URL, phiên và token mâu thuẫn, không âm thầm ưu tiên một nguồn tùy từng endpoint. Cần một contract rõ ràng về nguồn có thẩm quyền và cách từ chối khi phạm vi không khớp.

## 5. Tra cứu tài khoản và bảo vệ danh tính người dùng

Một truy vấn nguy hiểm trong mô hình tài khoản cục bộ là:

```sql
SELECT account_id
FROM account
WHERE normalized_email = :normalized_email;
```

Nếu email không duy nhất toàn hệ thống, truy vấn có thể trả nhiều tài khoản. Ngay cả khi email được đặt duy nhất toàn cục, việc tìm được tài khoản vẫn chưa chứng minh quyền thực hiện một hành động thuộc tenant.

Trong mô hình cục bộ, truy vấn cần phạm vi phù hợp:

```sql
SELECT account_id, tenant_id, status
FROM account
WHERE tenant_id = :trusted_tenant_id
  AND normalized_email = :normalized_email;
```

`:trusted_tenant_id` là tenant chuẩn đã được backend xác định cho thao tác. Nó không phải một tham số mà client được phép đổi để mở rộng truy vấn sau khi đã có quyền khôi phục cho tenant khác.

Chuẩn hóa email cần theo quy tắc định danh của hệ thống. Không tự suy ra hai tài khoản là một chỉ vì chuỗi email trông giống nhau hoặc dùng cùng tên hiển thị.

Phản hồi công khai nên tránh tiết lộ tài khoản tồn tại ở tenant nào, có membership ở tổ chức khác hay đang dùng loại MFA gì. Một thông báo chấp nhận xử lý phù hợp có thể được dùng cho cả trường hợp không tìm được tài khoản, nhưng các đường xử lý, giới hạn gửi và thông báo cũng cần được thiết kế để giảm khả năng suy đoán ngoài ý muốn.

Không gửi danh sách tenant mà một email tham gia cho người chưa được xác minh chỉ để họ chọn nơi khôi phục. Nếu cần hỗ trợ tìm cổng tổ chức, đó phải là một luồng được thiết kế với chính sách tiết lộ thông tin riêng.

## 6. Ràng buộc challenge, token và quyền khôi phục

Một bản ghi quyền khôi phục cục bộ có thể chứa:

```text
grantId
tenantId
accountId
recoveryRequestId
requestVersion
purpose
allowedAction
issuedAt
expiresAt
consumedAt
revokedAt
```

Token giao cho người dùng có thể là giá trị mờ tham chiếu bản ghi phía máy chủ hoặc mang dữ liệu đã được bảo vệ toàn vẹn theo thiết kế. Dù chọn cách nào, đường đổi token phải kiểm tra đúng tenant, tài khoản, yêu cầu, mục đích và trạng thái hiện tại.

Một token có chữ ký hợp lệ chưa đủ nếu handler cho phép sử dụng nó ở endpoint tenant khác. Tính toàn vẹn của token không thay thế kiểm tra phạm vi của hành động.

Ví dụ, liên kết bắt đầu trong red và được sửa đường dẫn sang blue phải bị từ chối nếu token vẫn đại diện cho quyền của red. Backend không được tìm token toàn cục rồi lấy tenant từ URL để thực hiện thay đổi ở một tài khoản khác có cùng email.

### Dùng một lần trong đúng phạm vi

Tại thao tác cuối, tiêu thụ quyền và thay đổi yếu tố xác thực cần được phối hợp bằng một cơ chế nhất quán phù hợp. Một cập nhật có điều kiện minh họa:

```sql
UPDATE recovery_grant
SET consumed_at = :decision_time,
    consumed_by_operation_id = :operation_id
WHERE grant_id = :grant_id
  AND tenant_id = :trusted_tenant_id
  AND account_id = :account_id
  AND recovery_request_id = :request_id
  AND purpose = :expected_purpose
  AND consumed_at IS NULL
  AND revoked_at IS NULL
  AND expires_at > :decision_time;
```

Các tham số cần được ràng buộc từ quyền và yêu cầu đã được xác minh, không lấy độc lập từ client. Đoạn SQL chỉ minh họa điều kiện trên grant; việc đổi mật khẩu hoặc MFA cũng phải tác động đúng tài khoản trong đúng tenant và được phối hợp nguyên tử hoặc qua giao thức phù hợp.

Nếu cập nhật không thành công, không tiếp tục thay đổi credential dựa trên kết quả kiểm tra cũ. Retry phải tra cứu operation theo phạm vi đã ràng buộc, không cấp thêm một quyền mới hoặc chuyển sang tenant khác.

## 7. Cô lập trong mô hình dữ liệu và kho lưu trữ

Mỗi tài nguyên có phạm vi tenant cần được mô hình hóa rõ: tài khoản, yêu cầu, bằng chứng, quyết định, challenge, grant, operation và nhật ký liên quan.

Với cơ sở dữ liệu dùng chung, một biện pháp có thể là dùng khóa hoặc ràng buộc quan hệ bao gồm tenant. Ví dụ, quan hệ từ yêu cầu tới tài khoản phải bảo đảm cặp `(tenant_id, account_id)` tham chiếu đúng tài khoản trong tenant đó, thay vì chỉ kiểm tra `account_id` ở một bảng khác.

Điều này hỗ trợ phát hiện lỗi gán chéo phạm vi, nhưng không thay thế kiểm tra thẩm quyền ở tầng ứng dụng. Một người có quyền đọc tất cả các hàng vẫn có thể truy vấn sai nếu đường gọi không bị giới hạn.

Các mô hình tách schema hoặc tách cơ sở dữ liệu tạo thêm ranh giới vận hành nhưng vẫn cần chọn đúng đích kết nối. Dùng riêng database cho mỗi tenant không giúp nếu bộ định tuyến chọn nhầm database hoặc một tài khoản dịch vụ được dùng tùy ý trên mọi database.

Nếu dùng chính sách lọc hàng hoặc ngữ cảnh kết nối để hỗ trợ cô lập, phải quản lý đúng vòng đời của ngữ cảnh đó. Kết nối tái sử dụng không được mang tenant của request trước sang request sau. Các đường đọc đặc biệt, job nền và công cụ quản trị cũng cần nằm trong thiết kế, không chỉ API thông thường.

Tệp bằng chứng và bản xuất phải được bảo vệ tương tự. Một tiền tố tên tệp chứa tenant chỉ là cách tổ chức; quyền đọc vẫn phải kiểm tra tenant và người gọi. URL tạm thời cần được cấp đúng phạm vi và không xuất hiện trong log hoặc thông báo của tenant khác.

## 8. API, repository và ngữ cảnh có kiểu rõ ràng

Các giao diện nội bộ có thể yêu cầu tenant như một phần bắt buộc của thao tác, thay vì cho phép tham số tùy chọn rồi dùng truy vấn toàn cục khi thiếu.

Minh họa bằng Java:

```java
record TenantId(String value) {
}

record RecoveryRequestId(String value) {
}

record ScopedRecoveryRequestId(
        TenantId tenantId,
        RecoveryRequestId requestId) {
}

interface RecoveryRequestRepository {
    RecoveryRequest load(ScopedRecoveryRequestId id);
}
```

`RecoveryRequest` trong ví dụ là kiểu miền do ứng dụng định nghĩa. Các kiểu bọc giúp biểu diễn phạm vi trong lời gọi, không tự xác thực chuỗi bên trong hoặc cấp quyền cho người gọi.

Tenant vẫn phải đến từ bước phân giải và kiểm tra phù hợp. Đóng một giá trị client gửi vào `TenantId` không làm nó trở thành ngữ cảnh đáng tin cậy.

Nên phân biệt rõ API cục bộ với API quản trị toàn cục. Một hàm toàn cục cần thẩm quyền đặc biệt không nên được dùng như phương án dự phòng khi truy vấn cục bộ không có kết quả.

## 9. Cache, giới hạn lạm dụng và trạng thái tạm

Ranh giới tenant dễ bị mất trong những thành phần không phải cơ sở dữ liệu chính. Các khóa như `recovery:user@example.test` hoặc `request:123` có thể trộn dữ liệu nếu định danh chỉ duy nhất trong từng tenant.

Khóa cache minh họa cần mang phạm vi phù hợp:

```text
recovery-request:{tenantId}:{requestId}:{requestVersion}
recovery-policy:{tenantId}:{policyVersion}
recovery-challenge:{tenantId}:{challengeId}
```

Không đưa token thô vào khóa có thể bị ghi log hoặc quan sát ngoài phạm vi. Quy ước đặt khóa cũng không thay thế kiểm soát quyền truy cập kho cache.

Giới hạn chống lạm dụng cần xem xét nhiều chiều: tenant, tài khoản trong tenant, nguồn gửi, loại hành động và mức toàn nền tảng. Chỉ giới hạn theo tenant có thể cho phép hành vi phân tán qua nhiều tenant; chỉ giới hạn theo email toàn cục có thể khiến một tenant làm gián đoạn khôi phục của tenant khác.

Các giới hạn dùng chung cần được thiết kế có chủ đích cho mục tiêu chống lạm dụng, không vô tình trộn hồ sơ hoặc làm lộ membership. Một yêu cầu xấu ở blue không nên tự động khóa đăng nhập của tài khoản red chỉ vì chúng dùng cùng chuỗi email, trừ khi có một chính sách bảo vệ danh tính toàn cục thực sự phù hợp với mô hình hệ thống.

## 10. Hàng đợi, worker và callback

Tác vụ nền không có phiên trình duyệt để suy ra tenant. Job cần tham chiếu phạm vi rõ ràng và được tạo bởi một nguồn có thẩm quyền.

Một payload minh họa:

```text
jobId
operationId
tenantId
recoveryRequestId
requestVersion
expectedAction
```

Worker kiểm tra tính hợp lệ của nguồn job, đọc yêu cầu trong đúng tenant và đối chiếu các thuộc tính trước khi thực hiện. Sự hiện diện của `tenantId` trong JSON không phải bằng chứng payload đáng tin cậy.

Nếu request đã bị hủy, đổi phiên bản hoặc tenant không còn cho phép thao tác đó, job cũ không được tiếp tục dựa trên ảnh chụp trạng thái đã lưu từ trước. Retry phải giữ nguyên phạm vi operation đã được cấp, không tự tìm một tài khoản tương tự ở tenant khác khi tài nguyên không còn tồn tại.

Worker xử lý nhiều tenant phải khởi tạo và dọn ngữ cảnh theo từng job. Không dựa vào một biến toàn cục hoặc ngữ cảnh luồng còn sót lại. Nếu framework có cơ chế truyền ngữ cảnh, vẫn cần bảo đảm nó đi qua đúng ranh giới bất đồng bộ và được xóa khi hoàn tất.

Callback từ nhà cung cấp xác minh phải được ràng buộc với phiên xác minh và yêu cầu đã tạo từ trước. Không chấp nhận một kết quả chỉ vì nó có email và tenant trùng với dữ liệu do callback tự khai báo. Nguồn callback, tính toàn vẹn và khả năng giao lại đều cần được xử lý theo contract của tích hợp.

## 11. Chính sách tenant, thông báo và liên kết khôi phục

Mỗi tenant có thể có quy tắc về loại yếu tố dự phòng, thời hạn, số người duyệt hoặc kênh thông báo. Cấu hình cần được tra cứu bằng tenant chuẩn và phiên bản chính sách phù hợp.

Không lấy chính sách mặc định của tenant khác khi thiếu cấu hình rồi tiếp tục cấp quyền. Một cơ chế mặc định toàn nền tảng nếu có phải được định nghĩa rõ và không làm suy yếu điều kiện bắt buộc của tenant.

Đối với email hoặc thông báo khôi phục:

- Nội dung phải tham chiếu đúng tổ chức và yêu cầu, không lộ thông tin của tenant khác.
- Địa chỉ nhận phải xuất phát từ dữ liệu hoặc luồng thay đổi kênh đã được xác minh theo chính sách.
- Tên miền liên kết và đích chuyển hướng phải lấy từ cấu hình đã được kiểm soát.
- Không xây dựng liên kết bảo mật từ một header host hoặc URL đích tùy ý mà người gửi có thể thao túng.
- Token trong liên kết vẫn cần được kiểm tra phạm vi tại backend, dù giao diện có đúng logo tenant.

Branding giúp người dùng nhận biết ngữ cảnh, nhưng không phải ranh giới bảo mật. Một trang mang logo red vẫn có thể gọi nhầm API blue nếu backend không ràng buộc phạm vi.

## 12. Quản trị viên, bộ phận hỗ trợ và quyền toàn nền tảng

Quyền quản trị cần nêu rõ tenant và loại hành động. Một người có thể quản trị red và chỉ là thành viên thông thường ở blue; hệ thống không được gộp các vai trò đó thành quyền quản trị chung.

Tại thời điểm duyệt hoặc thực thi, kiểm tra:

```text
actor has the required role in the target scope
AND actor may perform the requested recovery action
AND approval references the same request and version
AND separation-of-duty conditions are satisfied
AND current account and risk state permit the action
```

Quyền hỗ trợ toàn nền tảng nếu cần phải là một loại thẩm quyền riêng, có phạm vi, mục đích, thời hạn và nhật ký phù hợp. Không cấp đường bỏ qua tenant chỉ vì một API nội bộ có tên “support”.

Các thao tác toàn cục đối với danh tính dùng chung cần được phân biệt với quyền quản trị tenant. Chẳng hạn, quản trị viên red có thể vô hiệu hóa membership của người dùng trong red theo thẩm quyền, nhưng không vì thế được thay passkey toàn cục hoặc khôi phục quyền trong blue.

Sau khôi phục, không tự cấp lại vai trò đã mất trong tenant chỉ vì backup hoặc hồ sơ trước đây từng ghi người dùng có vai trò đó. Đăng nhập thành công và được cấp quyền truy cập tài nguyên là hai quyết định khác nhau.

## 13. Bằng chứng, nhật ký và quan sát theo tenant

Bằng chứng xác minh cần liên kết với đúng tenant, yêu cầu và phiên bản. Nếu một nhà cung cấp xác minh được dùng chung, kết quả trả về vẫn cần được gắn vào phiên xác minh đã tạo cho phạm vi đó, không tìm hồ sơ toàn cục bằng email rồi cập nhật tất cả yêu cầu trùng email.

Nhật ký nên ghi rõ tenant chịu tác động, chủ thể tài khoản, người thực hiện, operation và loại hành động. Tài khoản dịch vụ dùng chung không được làm mất thông tin về phạm vi gốc hoặc người đã duyệt.

Quyền đọc log và dashboard cũng phải được cô lập. Quản trị viên red có thể cần xem tiến độ khôi phục trong red, nhưng không vì dùng chung công cụ quan sát mà thấy email, bằng chứng hoặc quyết định của blue.

Không ghi OTP, token thô, recovery code hoặc bí mật phiên vào log để hỗ trợ truy vết. Dùng định danh ổn định và mã kết quả phù hợp. Những lần từ chối do phạm vi không khớp có thể là tín hiệu cần theo dõi, nhưng không nên trả chi tiết tài nguyên tenant khác cho người gọi.

Một công việc phân tích toàn nền tảng có thể có thẩm quyền riêng để tổng hợp dữ liệu. Đầu ra của nó vẫn phải phù hợp với đối tượng được nhận; không đưa dữ liệu nhận diện của tenant khác vào báo cáo cục bộ chỉ vì quá trình phân tích có quyền đọc rộng.

## 14. Ví dụ đi hết một luồng khôi phục MFA

Giả sử red và blue có tài khoản độc lập, cùng dùng một email liên hệ. Người dùng muốn đăng ký lại MFA của red:

1. Cổng red được phân giải thành `tenant-red` từ cấu hình được kiểm soát.
2. Backend tìm tài khoản theo tenant và định danh trong mô hình cục bộ.
3. Yêu cầu, challenge và kết quả xác minh đều liên kết với tài khoản red.
4. Người duyệt có thẩm quyền trong red xem đúng bộ bằng chứng và phiên bản yêu cầu.
5. Một grant chỉ cho phép đăng ký lại MFA của tài khoản red được cấp với thời hạn phù hợp.
6. Job thông báo mang tham chiếu yêu cầu red và worker đối chiếu lại trạng thái nguồn.
7. Khi đổi token, backend kiểm tra tenant, tài khoản, mục đích, thời hạn và tính dùng một lần.
8. Thao tác cuối thay đổi đúng MFA của red, áp dụng chính sách phiên tương ứng và ghi kết quả.

Nếu đường dẫn bị đổi sang blue ở bước 7, thao tác phải bị từ chối vì phạm vi không khớp. Không tìm tài khoản blue có cùng email để “hỗ trợ tiếp tục”.

Nếu người dùng cũng cần khôi phục blue, đó là yêu cầu khác với căn cứ và chính sách của blue. Trong mô hình danh tính toàn cục, luồng phải được thiết kế lại theo phạm vi toàn cục ngay từ đầu, thay vì lấy ví dụ cục bộ trên rồi bỏ qua những tác động tới các tenant khác.

## 15. Các tình huống thiết kế cần được làm rõ

Những tình huống sau mô tả hành vi mong muốn, không phải báo cáo đã chạy kiểm thử hệ thống:

| Tình huống | Hành vi phù hợp |
|---|---|
| Cùng email xuất hiện ở hai tài khoản tenant độc lập | Tra cứu và xử lý theo đúng tenant, không chọn kết quả đầu tiên toàn cục |
| Token red được gửi tới endpoint blue | Từ chối do phạm vi không khớp |
| Người duyệt chỉ có quyền ở red | Không được duyệt yêu cầu blue hoặc thao tác credential toàn cục ngoài thẩm quyền |
| Worker xử lý red rồi nhận job blue | Khởi tạo ngữ cảnh mới, không dùng dữ liệu hoặc kết nối mang phạm vi cũ |
| Thiếu tenant trong job hoặc truy vấn cục bộ | Không chuyển sang thao tác không giới hạn tenant |
| Cache có hai request ID giống nhau ở hai tenant | Khóa và đối tượng cache giữ phạm vi, không trả chéo dữ liệu |
| Callback khai đúng email nhưng sai phiên xác minh | Không gắn kết quả vào yêu cầu khác |
| Người dùng đổi host hoặc redirect trong request | Không tạo liên kết khôi phục tới đích tùy ý |
| Một tenant bị lạm dụng kênh khôi phục | Áp dụng giới hạn phù hợp mà không vô tình trộn danh tính hoặc quyền của tenant khác |
| Credential dùng chung toàn nền tảng | Thể hiện đúng tác động và dùng luồng toàn cục có thẩm quyền tương ứng |
| Người dùng khôi phục đăng nhập sau khi membership bị thu hồi | Không tự cấp lại quyền tenant đã mất |

Các lỗi cốt lõi thường bắt đầu từ việc coi `tenantId` là nhãn giao diện, xem email như khóa danh tính toàn cục trong mọi mô hình hoặc chỉ kiểm tra tenant ở endpoint đầu tiên. Ranh giới cần được mang theo và xác minh lại tại nơi đọc dữ liệu, cấp quyền và thực hiện thay đổi.

Cô lập tenant hiệu quả đòi hỏi mô hình danh tính rõ ràng, phạm vi bắt buộc trong tài nguyên và kiểm tra nhất quán xuyên các thành phần. Khi khôi phục mật khẩu, MFA hoặc passkey, hệ thống phải biết chính xác quyền nào đang được cấp, tài khoản nào chịu tác động và tác động đó là cục bộ hay toàn cục trước khi cho phép thực thi.
