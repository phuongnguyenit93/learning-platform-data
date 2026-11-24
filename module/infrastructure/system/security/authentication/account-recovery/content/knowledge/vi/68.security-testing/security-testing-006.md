# Privilege escalation test — Kiểm thử leo thang đặc quyền qua luồng khôi phục tài khoản

## 1. Mục tiêu và phạm vi

Một người vừa chứng minh quyền truy cập email có thể được phép đặt mật khẩu mới, nhưng chưa chắc được phép tháo MFA. Một phiên recovery có thể được phép đăng ký passkey thay thế cho đúng tài khoản, nhưng không được phép đọc dữ liệu nghiệp vụ hoặc gọi API quản trị. Một hỗ trợ viên có thể xem hồ sơ xác minh nhưng chưa có quyền phê duyệt hồ sơ đó.

Privilege escalation test kiểm tra xem hệ thống có cho một chủ thể thực hiện hành động vượt quá quyền được cấp hay không. Trong module SECURITY_AUTHENTICATION_ACCOUNT_RECOVERY, trọng tâm là những quyền tạm thời xuất hiện khi người dùng mất mật khẩu, MFA, passkey hoặc thiết bị xác thực. Bài học không chỉ xem người dùng có trở thành quản trị viên hay không; việc biến một bằng chứng khôi phục yếu thành quyền kiểm soát tài khoản cũng là một kết quả nguy hiểm cần kiểm tra.

Các endpoint, role, trạng thái và tên trường trong bài thuộc hệ thống minh họa. Khi áp dụng, phải lấy chính sách thực tế của sản phẩm làm kết quả mong đợi. Không tự mặc định rằng quản trị viên luôn được reset mọi tài khoản hoặc rằng mọi recovery đều dẫn thẳng tới một phiên đăng nhập đầy đủ.

Sau bài học, người học cần:

- Xác định các ranh giới quyền trong luồng recovery.
- Phân biệt truy cập tài khoản khác, vượt role và vượt yêu cầu xác thực.
- Xây dựng ma trận actor–action–resource–context để làm oracle cho test.
- Kiểm tra việc sửa account, tenant, purpose, trạng thái và trường đặc quyền trong request.
- Quan sát dữ liệu, credential và quyền truy cập thực tế sau mỗi lần thử.
- Thiết kế test cho replay, session cũ, xử lý đồng thời và thao tác hỗ trợ.

Các ví dụ được tổ chức cho ứng dụng thử nghiệm với tài khoản và dữ liệu do nhóm kiểm thử tạo. Mục tiêu là tái hiện và ngăn lỗi trong hệ thống được giao kiểm tra, không cần quét hay tương tác với dịch vụ bên ngoài.

## 2. Leo thang quyền trong recovery có những dạng nào?

[OWASP WSTG — Testing for Privilege Escalation](https://github.com/OWASP/wstg/blob/master/document/4-Web_Application_Security_Testing/05-Authorization_Testing/03-Testing_for_Privilege_Escalation.md) phân biệt hai hướng thường gặp: truy cập tài nguyên của tài khoản ngang quyền và sử dụng chức năng dành cho tài khoản có quyền cao hơn. Với recovery, cần bổ sung góc nhìn về quyền theo giai đoạn và mức xác thực để nhận diện đầy đủ đường chiếm tài khoản.

| Dạng vượt quyền | Tình huống recovery minh họa | Ranh giới bị phá |
|---|---|---|
| Ngang tài khoản | Token của A đặt lại mật khẩu cho B | Quyền sở hữu tài nguyên |
| Xuyên tenant | Hồ sơ của tenant A thay factor cho tenant B | Phạm vi tổ chức |
| Dọc role | Người dùng thường phê duyệt recovery của người khác | Quyền chức năng |
| Vượt giai đoạn | Hồ sơ mới tạo đã được dùng để đăng ký passkey | Trạng thái nghiệp vụ |
| Vượt mục đích | Token reset password được dùng để xóa MFA | Purpose/capability |
| Vượt yêu cầu xác thực | Phiên chưa hoàn tất factor truy cập chức năng cần step-up | Điều kiện xác thực |
| Vượt thời hạn hoặc thu hồi | Grant đã hủy tiếp tục tạo credential mới | Vòng đời quyền |
| Lạm dụng quyền đại diện | Dịch vụ recovery dùng quyền nội bộ để thực hiện yêu cầu không được phép | Ủy quyền giữa dịch vụ |

Một tài khoản có role USER nhưng thay được credential của người khác đã vi phạm ranh giới quyền, dù chưa có role ADMIN. Tương tự, hệ thống có thể không thay role nào nhưng vẫn để phiên chỉ có bằng chứng email thực hiện thao tác vốn yêu cầu MFA.

Cũng cần phân biệt recovery hợp lệ với bypass. Một quy trình thay thế factor được phê duyệt có thể dùng bằng chứng khác với factor đã mất; đó là mục đích của recovery. Bypass xảy ra khi người gọi nhận quyền mà chưa thỏa quy trình hoặc mức bảo đảm đã được sản phẩm quy định.

## 3. Mô hình hóa quyền tạm thời và ranh giới tin cậy

### 3.1. Bằng chứng hợp lệ không đồng nghĩa toàn quyền

Một recovery grant có thể được mô tả bằng các thuộc tính:

~~~text
grantId
subjectAccountId
tenantId
recoveryTransactionId
purpose
allowedActions
expiresAt
state
evidenceVersion
policyVersion
~~~

Không phải mọi hệ thống đều dùng đúng cấu trúc này. Các thuộc tính có thể nằm trong bản ghi server, trong token có chữ ký hoặc được suy từ nhiều nguồn đáng tin cậy. Điều quan trọng là quyết định cuối phải ràng buộc đúng chủ thể, tài nguyên, hành động và bối cảnh.

Thông tin do client gửi như accountId, role hoặc mfaVerified không tự trở thành dữ kiện đáng tin cậy. Nó có thể là đầu vào để định vị yêu cầu, nhưng quyền xử lý phải được đối chiếu với bằng chứng và trạng thái do server xác minh.

### 3.2. Những ranh giới cần đi qua test

~~~mermaid
flowchart LR
    C[Client va du lieu request] --> V[Xac minh bang chung]
    V --> G[Grant gioi han]
    G --> P[Kiem tra quyen va trang thai]
    P --> R[Thay credential dung pham vi]
    R --> S[Dang nhap theo chinh sach]
    C --> H[Cong ho tro]
    H --> P
    P --> D[Dich vu credential]
~~~

Mỗi mũi tên là một nơi có thể xuất hiện lỗi:

- Client sửa subject nhưng verifier vẫn trả grant cho account cũ.
- Grant đúng nhưng policy chỉ kiểm tra “đã authenticated”.
- Policy kiểm tra đúng nhưng lời gọi tới dịch vụ credential dùng target khác.
- Cổng hỗ trợ xác thực nhân viên nhưng bỏ qua quyền phê duyệt.
- Recovery hoàn tất nhưng hệ thống cấp session với mức xác thực cao hơn bằng chứng thực có.

Đừng chỉ test controller nếu thực tế có gateway, worker, callback và dịch vụ credential riêng. Điểm thực hiện thay đổi cuối cùng phải nhận và kiểm tra đủ ngữ cảnh theo mô hình tin cậy của hệ thống.

### 3.3. Deny by default phải có bằng chứng

[OWASP Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html) khuyến nghị quyền tối thiểu, từ chối mặc định và kiểm tra quyền trên từng request. Trong recovery, một cách kiểm chứng cụ thể là thử dùng principal recovery với các hành động không nằm trong danh sách được cấp, đồng thời giữ test chứng minh hành động được phép vẫn hoạt động.

Ẩn nút “thay MFA” trên giao diện không đủ. Test cần gọi trực tiếp API đó với chính credential hoặc cookie của phiên recovery. CORS, tên URL khó đoán và UUID không thay thế việc kiểm tra quyền.

## 4. Xây dựng oracle bằng ma trận quyền

Trước khi sửa request, cần biết hành động nào thực sự được phép. Có thể mô tả mỗi quyết định bằng:

~~~text
Decision = Policy(actor, action, resource, context)

actor:
  danh tính, loại principal, quyền được cấp

resource:
  account, tenant, hồ sơ, factor, session

context:
  trạng thái recovery, bằng chứng, thời gian,
  phiên bản policy, điều kiện step-up
~~~

Ma trận dưới đây là một chính sách minh họa cho sản phẩm có tách luồng reset password và thay factor:

| Chủ thể hoặc trạng thái | Khởi tạo recovery | Reset password của chính mình | Đăng ký factor thay thế | Xem dữ liệu nghiệp vụ | Phê duyệt hồ sơ | Sửa role |
|---|---|---|---|---|---|---|
| Chưa có bằng chứng | Có, qua API công khai | Không | Không | Không | Không | Không |
| Grant PASSWORD_RESET hợp lệ | Theo API công khai | Có, đúng scope | Không | Không | Không | Không |
| Grant FACTOR_REBIND hợp lệ | Theo API công khai | Không qua grant này | Có, đúng scope | Không | Không | Không |
| Phiên đăng nhập thông thường | Theo chính sách | Qua luồng đổi password riêng | Cần điều kiện step-up hoặc recovery phù hợp | Theo quyền account | Không | Không |
| Hỗ trợ viên chỉ được đọc | Theo quy trình hỗ trợ | Không trực tiếp | Không trực tiếp | Không được suy từ quyền đọc hồ sơ | Không | Không |
| Người phê duyệt recovery | Theo quy trình hỗ trợ | Không tự suy ra | Chỉ mở bước được policy cho phép | Không được suy từ quyền phê duyệt | Có, đúng tenant và hồ sơ | Không |
| Quản trị role | Theo quyền riêng | Không tự suy ra | Không tự suy ra | Theo quyền riêng | Theo quyền riêng | Có nếu được cấp |

“Không tự suy ra” nghĩa là role đang xét không mặc nhiên cấp hành động đó. Một tổ chức có thể cho cùng nhân viên nhiều quyền, nhưng quyền cần được cấp và kiểm tra rõ ràng, không phát sinh từ nhãn ADMIN chung.

Ma trận cần có thêm chiều account và tenant. Ví dụ, grant PASSWORD_RESET của A chỉ được phép reset A trong tenant đã ràng buộc; không thể diễn giải ô “Có” thành được reset bất kỳ tài khoản nào.

Các quyết định chưa được mô tả phải được làm rõ trong thiết kế. Test không nên lấy hành vi hiện tại của endpoint làm chính sách rồi mặc định hành vi đó đúng.

## 5. Chuẩn bị môi trường và dữ liệu

### 5.1. Fixture tối thiểu

| Fixture | Mục đích |
|---|---|
| Account A, tenant T1, role USER | Chủ thể có bằng chứng hợp lệ |
| Account B, tenant T1, role USER | Phát hiện vượt ngang |
| Account C, tenant T2, role USER | Phát hiện vượt tenant |
| Account D, tenant T1, role quản trị | Kiểm tra recovery tài khoản đặc quyền |
| Nhân viên R, quyền đọc hồ sơ T1 | Kiểm tra vượt quyền hỗ trợ |
| Nhân viên P, quyền phê duyệt T1 | Positive control cho phê duyệt |
| Grant G1 cho A, purpose PASSWORD_RESET | Kiểm tra scope password |
| Grant G2 cho A, purpose FACTOR_REBIND | Positive control cho thay factor |
| Hồ sơ đã hủy hoặc đã hết hạn | Kiểm tra vòng đời quyền |

Nên có hai account thuộc hai tenant nhưng dùng cùng email hiển thị nếu mô hình sản phẩm cho phép. Fixture này giúp phát hiện việc tra cứu account chỉ theo email và bỏ qua tenant.

Đối với account MFA hoặc passkey, tạo credential test và các phiên trước recovery. Với tài khoản quản trị, ghi lại role ban đầu và yêu cầu xác thực để kiểm tra chúng sau recovery.

### 5.2. Baseline cần quan sát

Trước một case, chụp các thuộc tính có liên quan:

- Phiên bản credential hoặc dấu hiệu thay đổi password.
- Danh sách factor và trạng thái factor.
- Role, nhóm, quyền hoặc membership.
- Địa chỉ recovery và trạng thái xác minh.
- Recovery transaction, grant và phiên bản bằng chứng.
- Session hoặc refresh token đang có hiệu lực.
- Event nghiệp vụ đã commit.

Không đưa password, token thô hay seed TOTP vào snapshot báo cáo. Với password, kiểm tra qua verifier hoặc hành vi đăng nhập thay vì so sánh hash cố định.

Sau request bị từ chối, những thay đổi an ninh như audit hoặc tăng bộ đếm lạm dụng có thể hợp lệ. Assertion phải nói rõ dữ liệu nào không được thay đổi; không dùng một so sánh toàn bộ database rồi coi mọi thay đổi đều là lỗi.

### 5.3. Mỗi test có dữ liệu riêng

Một grant dùng một lần không nên được chia cho nhiều test chạy song song. Một test dùng hết grant có thể khiến test vượt quyền tiếp theo bị từ chối vì token đã dùng, che mất lỗi authorization thật.

Mỗi case cần grant riêng, account riêng hoặc fixture được khôi phục có kiểm soát. Khi cần kiểm tra replay, phải chủ động dùng lại cùng grant trong chính một case đó.

## 6. Danh mục kiểm thử ưu tiên

| ID | Phép thử | Bất biến cần giữ |
|---|---|---|
| PE-01 | Đổi account đích từ A sang B | Bằng chứng của A không thay credential của B |
| PE-02 | Đổi tenant T1 sang T2 | Không truy cập hoặc cập nhật xuyên tenant |
| PE-03 | Token password gọi endpoint thay MFA | Không sử dụng sai purpose |
| PE-04 | Token factor gọi API sửa role | Quyền recovery không bao gồm quản trị |
| PE-05 | Thêm role hoặc authorities vào body | Client không cấp đặc quyền cho chính mình |
| PE-06 | Thêm mfaVerified hoặc assurance vào body | Client không tự nâng mức xác thực |
| PE-07 | Principal recovery gọi tài nguyên nghiệp vụ | Phiên giới hạn giữ đúng phạm vi |
| PE-08 | Đổi trạng thái yêu cầu thành APPROVED | State server không bị trường client ghi đè |
| PE-09 | Nhân viên chỉ đọc gọi API phê duyệt | Quyền đọc không thành quyền quyết định |
| PE-10 | Người phê duyệt T1 xử lý hồ sơ T2 | Quyền hỗ trợ vẫn có tenant scope |
| PE-11 | Gọi thẳng bước cuối khi chưa đủ bằng chứng | Không bỏ qua bước nghiệp vụ bắt buộc |
| PE-12 | Dùng grant đã hủy, hết hạn hoặc đã dùng | Quyền kết thúc không có hiệu lực trở lại |
| PE-13 | Trộn cookie của B với grant của A | Không ghép sai danh tính và bằng chứng |
| PE-14 | Đổi email recovery rồi xác minh bằng email mới | Không tự tạo bằng chứng chiếm quyền ngoài policy |
| PE-15 | Callback cũ đến sau khi hủy hoặc đổi evidence | Không phục hồi quyền dựa trên dữ kiện cũ |
| PE-16 | Policy hoặc quyền hỗ trợ bị thu hồi giữa luồng | Thao tác cuối tuân thủ quy tắc hiệu lực đã công bố |
| PE-17 | Recovery tài khoản quản trị bằng nhánh người dùng thường | Áp dụng đúng yêu cầu cho account đặc quyền |
| PE-18 | Replay hoặc hai request thay factor đồng thời | Không dùng grant để tạo thêm credential ngoài phép |
| PE-19 | Session cũ refresh sau recovery | Không lấy lại quyền đã bị thu hồi |
| PE-20 | Endpoint thay thế, phiên bản cũ hoặc batch | Không tồn tại đường thiếu kiểm tra quyền |

Danh mục này là thiết kế kiểm thử cho ví dụ trong bài, không phải một checklist đủ cho mọi sản phẩm. Khi thêm endpoint, tenant policy hoặc loại factor mới, cần xem chúng tạo ranh giới quyền mới ở đâu.

## 7. Kiểm thử vượt ngang: account và tenant

### 7.1. Thay target trong một request hợp lệ

Bắt đầu từ request hợp lệ của A trong môi trường test. Cấp một grant mới cho A, sau đó chỉ đổi account đích thành B. Giữ các điều kiện còn lại hợp lệ để lỗi scope, nếu có, không bị che bởi token sai định dạng.

~~~http
POST /test-api/accounts/account-b/password-reset/complete HTTP/1.1
Host: recovery.example.test
Authorization: Bearer <valid-password-reset-grant-for-account-a>
Content-Type: application/json

{
  "recoveryTransactionId": "transaction-a",
  "newPassword": "<synthetic-password>"
}
~~~

Tên miền, endpoint và các giá trị trong request là ví dụ. Không cần sản phẩm có accountId trong URL mới kiểm tra được vượt ngang; target có thể nằm trong body, query, resource lồng nhau hoặc kết quả tra cứu phía server.

Expected cần gồm:

1. Hành động thay password cho B bị từ chối theo hợp đồng API.
2. Credential, factor, role và địa chỉ recovery của B không đổi.
3. Không cấp session cho B và không trả dữ liệu nhạy cảm của B.
4. Không có completion event hợp lệ cho B.
5. Positive control với một fixture mới cho A vẫn thành công.

Grant của A có bị thu hồi sau lần thử sai scope hay không phụ thuộc chính sách chống abuse. Không mặc định grant phải tiếp tục dùng được nếu sản phẩm quy định thu hồi khi phát hiện bất thường.

### 7.2. Kiểm tra mọi nguồn xác định tenant

Tenant có thể đến từ host, path, header được gateway xác minh, session hoặc membership. Tạo case xung đột giữa các nguồn mà sản phẩm thực sự sử dụng:

~~~text
Grant: tenant T1, account A
Path: tenant T2
Cookie đăng nhập: account C thuộc T2
Request body: account A
~~~

Expected là hệ thống xử lý xung đột theo hợp đồng tin cậy, không chọn tùy nguồn nào tạo điều kiện cho phép. Đặc biệt, header mà client tự đặt không được coi như header danh tính do proxy đáng tin cậy phát hành.

Nếu ID account là duy nhất toàn hệ thống, vẫn phải kiểm tra tenant theo mô hình phân quyền. ID duy nhất giúp định vị bản ghi; nó không chứng minh actor được phép thao tác bản ghi đó.

### 7.3. Hồ sơ và tài nguyên lồng nhau

Một endpoint như sau có hai đối tượng phải ràng buộc:

~~~text
/accounts/A/recovery-transactions/R/factors/F
~~~

Cần kiểm tra R có thuộc A và F có thuộc đúng account, tenant, giao dịch hay không. Việc đã kiểm tra A không tự bảo đảm R hoặc F đúng chủ sở hữu.

Đừng chỉ kiểm tra thao tác ghi. Quyền đọc hồ sơ xác minh, danh sách factor hay metadata thiết bị cũng có thể bị vượt ngang và hỗ trợ cho các bước chiếm tài khoản tiếp theo.

## 8. Kiểm thử vượt role và sửa trường đặc quyền

### 8.1. Gọi chức năng có quyền cao hơn

Lấy request hợp lệ từ một actor được phép trong fixture, rồi thay credential bằng actor quyền thấp hơn. Ví dụ, gọi API phê duyệt bằng phiên của hỗ trợ viên chỉ được đọc hoặc dùng grant recovery gọi API quản trị role.

Không giữ lại cookie quản trị trong HTTP client. Một lỗi thiết lập phổ biến là thay Authorization header nhưng client vẫn gửi cookie của người có quyền; test khi đó không kiểm tra actor mà người viết tưởng đang kiểm tra.

Một phép thử tốt có ba nhánh:

~~~text
Actor được cấp quyền + target đúng scope:
  Thành công theo chính sách.

Actor quyền thấp + cùng target:
  Bị từ chối, không có tác động được bảo vệ.

Actor được cấp quyền + target ngoài scope:
  Bị từ chối, không có tác động được bảo vệ.
~~~

Nhánh thứ ba phát hiện việc kiểm tra role đúng nhưng thiếu điều kiện resource hoặc tenant.

### 8.2. Mass assignment trong request recovery

Nếu controller bind toàn bộ request vào entity account, các trường không thuộc biểu mẫu recovery có thể bị ghi ngoài ý muốn. Tạo case với dữ liệu như sau trong môi trường test:

~~~json
{
  "newPassword": "<synthetic-password>",
  "role": "ADMIN",
  "authorities": ["ACCOUNT_ADMIN"],
  "mfaVerified": true,
  "recoveryApproved": true,
  "emailVerified": true,
  "assurance": "HIGH"
}
~~~

Các tên trường mang tính minh họa. Cần chọn trường mà mô hình dữ liệu hoặc DTO thực tế có thể tiếp nhận; gửi một trường không bao giờ được parser sử dụng không kiểm tra được đường ghi nguy hiểm.

Có hai hợp đồng có thể hợp lệ:

- API từ chối các trường ngoài schema và không thực hiện thay đổi.
- API bỏ qua trường ngoài schema, chỉ thực hiện tác vụ được cấp quyền.

Nếu sản phẩm chọn hợp đồng thứ hai, việc password của chính A được thay đúng grant không tự là lỗi. Assertion phải chứng minh role, quyền, trạng thái MFA, trạng thái xác minh và mức bảo đảm không bị những trường client điều khiển. Không áp một kỳ vọng “mọi dữ liệu đều không đổi” cho cả hai hợp đồng.

DTO hẹp giúp giảm bề mặt mass assignment, nhưng test vẫn cần đi qua mapper và persistence thật ở tầng tích hợp. Unit test chỉ kiểm tra annotation trên DTO chưa chứng minh entity không bị cập nhật qua một nhánh service khác.

### 8.3. Header và dữ liệu phía client không cấp quyền

Nếu ứng dụng có các trường hoặc header như role, userType, trustedDevice, supportMode hoặc tenantOverride, cần phân biệt chúng là dữ liệu hiển thị, đầu vào nghiệp vụ hay metadata được một thành phần tin cậy xác minh.

Case cần thử dữ liệu do client tự đặt đi qua đường truy cập công khai. Một request từ Internet không được có quyền nội bộ chỉ vì chứa header mà worker nội bộ cũng sử dụng.

Với proxy, test phải đi qua cấu hình proxy đại diện và xác nhận header danh tính do client gửi bị loại bỏ hoặc được xử lý theo thiết kế trước khi backend tin dùng. Chỉ test backend với header dựng sẵn có thể bỏ sót ranh giới này.

### 8.4. Token có chữ ký vẫn có thể sai ngữ cảnh

Nếu sản phẩm dùng JWT hoặc một định dạng token có chữ ký cho recovery, cần hai nhóm test riêng:

1. Token bị sửa nội dung mà không có chữ ký hợp lệ phải bị từ chối.
2. Token hợp lệ về mật mã nhưng được phát hành cho mục đích hoặc nơi nhận khác cũng không được dùng làm quyền recovery tương ứng.

Nhóm thứ hai quan trọng vì lỗi có thể nằm ở cách dùng token, không nằm ở khả năng giả mạo chữ ký. Ví dụ, một token PASSWORD_RESET hợp lệ không được coi là access token đầy đủ chỉ vì verifier trả về một subject.

Không cấp cho client quyền tự chọn issuer, audience hoặc loại principal được tin cậy. Test cần đi qua verifier thật tại tầng tích hợp; mock luôn trả principal hợp lệ chỉ kiểm tra được phần policy phía sau.

## 9. Kiểm thử vượt giai đoạn và nâng mức xác thực

### 9.1. Gọi thẳng bước cuối

Một luồng recovery có thể có các trạng thái:

~~~text
REQUESTED
  -> EVIDENCE_PENDING
  -> EVIDENCE_ACCEPTED
  -> DELAY_PENDING
  -> REBIND_ALLOWED
  -> COMPLETED
~~~

Không phải mọi sản phẩm đều có thời gian chờ. Khi có, sự kết thúc thời gian chờ phải được quyết định bằng trạng thái và thời gian đáng tin cậy phía server, không phải tham số như delayCompleted=true.

Tạo một hồ sơ ở từng trạng thái, rồi thử gọi thao tác chỉ được phép tại REBIND_ALLOWED. Kiểm tra cả API công khai, API hỗ trợ và callback có thể làm bước đó.

Một case đặc biệt hữu ích là sửa body:

~~~json
{
  "recoveryTransactionId": "transaction-a",
  "state": "REBIND_ALLOWED",
  "evidenceAccepted": true,
  "newFactor": "<synthetic-factor-registration>"
}
~~~

Expected là trường client không thay thế bằng chứng server. Nếu toàn bộ request bị từ chối, không có factor mới. Nếu trường ngoài schema bị bỏ qua, hành động vẫn phải bị từ chối khi trạng thái thật chưa cho phép.

### 9.2. Không biến reset password thành quyền tháo MFA

Đối với tài khoản bật MFA:

1. Khởi tạo và hoàn tất reset password bằng nhánh hợp lệ.
2. Thử đăng nhập bằng password mới nhưng chưa hoàn tất factor còn được yêu cầu.
3. Gọi tài nguyên có yêu cầu xác thực tương ứng.
4. Thử dùng cùng bằng chứng reset để thay hoặc xóa MFA.

Expected phụ thuộc policy: tài khoản vẫn phải thỏa yêu cầu MFA hoặc quy trình recovery thay thế đã được phê duyệt. Password mới không tự chứng minh quyền thay mọi factor.

[OWASP Multifactor Authentication Cheat Sheet — Resetting MFA](https://cheatsheetseries.owasp.org/cheatsheets/Multifactor_Authentication_Cheat_Sheet.html#resetting-mfa) lưu ý rằng cơ chế lấy lại quyền truy cập không được trở thành đường vượt MFA. Trong test, nguyên tắc này cần được biểu diễn bằng các hành động cụ thể bị chặn trước khi đủ bằng chứng thay factor.

### 9.3. Kiểm tra claim và hành vi thực

Ứng dụng có thể lưu thông tin như authentication methods, thời điểm xác thực hoặc mức bảo đảm trong session. Không chỉ đọc claim và kết luận test đạt.

Nếu một phiên chưa thỏa step-up gọi được thao tác nhạy cảm, đó là lỗi dù claim hiển thị đúng mức thấp. Ngược lại, claim bị đánh dấu mức cao sai có thể tạo lỗ hổng ở dịch vụ khác dù endpoint hiện tại vẫn chặn.

Do đó cần kiểm tra cả metadata do server phát hành và quyết định truy cập ở tài nguyên tiêu thụ metadata. Với hệ thống nhiều dịch vụ, chọn ít nhất một tài nguyên thực sự thực thi yêu cầu đó.

### 9.4. Passkey thay thế phải gắn với đúng quyền

Luồng khôi phục passkey thường kết thúc bằng việc đăng ký credential mới. Test cần xác nhận grant chỉ cho phép thao tác đó với account, tenant và transaction đã ràng buộc.

Đừng coi chuỗi “passkey” là đủ để cấp một mức xác thực cụ thể. Hệ thống cần xác minh kết quả giao thức và chính sách đăng ký; bộ kiểm thử phải dùng thành phần xác minh thật ở tầng phù hợp.

Ngoài case đăng ký hợp lệ, cần có case grant password reset gọi endpoint đăng ký passkey, grant của A đăng ký vào B, và grant đã tiêu thụ đăng ký thêm credential thứ hai. Nếu sản phẩm cố ý cho phép nhiều credential trong một phiên rebind, test số lượng và phạm vi theo hợp đồng đó thay vì mặc định chỉ một.

## 10. Trộn danh tính giữa cookie, bearer token và hồ sơ

Ứng dụng có thể đồng thời nhận cookie đăng nhập, bearer token recovery, accountId trong URL và transactionId trong body. Nếu các thành phần chọn danh tính từ những nguồn khác nhau, một request có thể được kiểm tra như A nhưng thực hiện tác động lên B.

| Cookie | Grant | Target | Điều cần xác định |
|---|---|---|---|
| Không có | A/T1 | A/T1 | Nhánh recovery được cấp quyền hoạt động |
| B/T1 | A/T1 | A/T1 | Xử lý xung đột theo hợp đồng, không ghép quyền |
| B/T1 | A/T1 | B/T1 | Grant của A không cấp quyền thay credential của B |
| Quản trị viên D | A/T1 | A/T1 | Không âm thầm đổi actor recovery thành D |
| C/T2 | A/T1 | A/T1 | Không suy tenant đích từ cookie khác scope |
| Session đã thu hồi | A/T1 | A/T1 | Không phục hồi quyền của session cũ |

Sản phẩm có thể từ chối request có hai credential khác ngữ cảnh, hoặc quy định rõ endpoint recovery chỉ dùng grant và không dùng session đăng nhập thông thường. Cả hai cần được thực thi nhất quán. Không để gateway dùng cookie cho authorization trong khi service dùng bearer subject để chọn account.

Khi test, dùng HTTP client hoặc browser context riêng cho từng actor. Ghi lại loại credential đã gửi bằng nhãn hoặc fingerprint an toàn, không ghi giá trị secret.

Cần lưu ý quyền vốn có của actor. Nếu dùng cookie quản trị viên đã được cấp quyền thay tài khoản đích, request thành công chưa chứng minh recovery grant gây leo thang. Phải tách test tác động của từng credential để tránh kết luận nhầm.

## 11. Ví dụ Java: mô hình policy cho recovery grant

Ví dụ dưới đây dùng Java 17 trở lên và JUnit Jupiter. Nó mô hình hóa một policy hẹp: grant chỉ cho phép reset password hoặc đăng ký factor đúng scope. Các API nghiệp vụ và quản trị đều bị từ chối trong policy recovery này.

Đây là mã minh họa tự chứa để giải thích điều kiện và assertion. Nó không thay thế verifier token, authorization của toàn ứng dụng, kiểm tra storage hoặc phép tiêu thụ grant nguyên tử.

~~~java
import org.junit.jupiter.api.Test;

import java.time.Instant;
import java.util.Objects;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class RecoveryPrivilegePolicyTest {

    enum Purpose {
        PASSWORD_RESET,
        FACTOR_REBIND
    }

    enum State {
        READY,
        CANCELLED,
        CONSUMED
    }

    enum Action {
        RESET_PASSWORD,
        REGISTER_FACTOR,
        READ_BUSINESS_DATA,
        CHANGE_ROLE
    }

    record Target(
            String accountId,
            String tenantId,
            String transactionId) {
    }

    record Grant(
            String accountId,
            String tenantId,
            String transactionId,
            Purpose purpose,
            State state,
            Instant expiresAt,
            long evidenceVersion) {
    }

    static boolean permits(
            Grant grant,
            Action action,
            Target target,
            Instant now,
            long currentEvidenceVersion) {

        if (grant == null || action == null
                || target == null || now == null) {
            return false;
        }

        if (grant.state() != State.READY
                || grant.expiresAt() == null
                || !now.isBefore(grant.expiresAt())
                || grant.evidenceVersion() != currentEvidenceVersion) {
            return false;
        }

        if (grant.accountId() == null
                || grant.tenantId() == null
                || grant.transactionId() == null
                || !Objects.equals(grant.accountId(), target.accountId())
                || !Objects.equals(grant.tenantId(), target.tenantId())
                || !Objects.equals(
                        grant.transactionId(), target.transactionId())) {
            return false;
        }

        return switch (action) {
            case RESET_PASSWORD ->
                    grant.purpose() == Purpose.PASSWORD_RESET;
            case REGISTER_FACTOR ->
                    grant.purpose() == Purpose.FACTOR_REBIND;
            case READ_BUSINESS_DATA, CHANGE_ROLE -> false;
        };
    }

    private static final Instant NOW =
            Instant.parse("2030-01-01T00:00:00Z");

    private static final Target OWN_TARGET =
            new Target("account-a", "tenant-1", "transaction-a");

    private static Grant grant(Purpose purpose, State state) {
        return new Grant(
                "account-a",
                "tenant-1",
                "transaction-a",
                purpose,
                state,
                NOW.plusSeconds(300),
                7L);
    }

    @Test
    void resetGrantAllowsOnlyItsOwnPasswordReset() {
        Grant reset = grant(Purpose.PASSWORD_RESET, State.READY);

        assertTrue(permits(
                reset, Action.RESET_PASSWORD, OWN_TARGET, NOW, 7L));

        assertFalse(permits(
                reset, Action.REGISTER_FACTOR, OWN_TARGET, NOW, 7L));

        assertFalse(permits(
                reset, Action.CHANGE_ROLE, OWN_TARGET, NOW, 7L));

        assertFalse(permits(
                reset, Action.READ_BUSINESS_DATA, OWN_TARGET, NOW, 7L));
    }

    @Test
    void factorGrantDoesNotInheritPasswordResetPermission() {
        Grant rebind = grant(Purpose.FACTOR_REBIND, State.READY);

        assertTrue(permits(
                rebind, Action.REGISTER_FACTOR, OWN_TARGET, NOW, 7L));

        assertFalse(permits(
                rebind, Action.RESET_PASSWORD, OWN_TARGET, NOW, 7L));
    }

    @Test
    void accountTenantAndTransactionMustAllMatch() {
        Grant reset = grant(Purpose.PASSWORD_RESET, State.READY);

        assertFalse(permits(
                reset, Action.RESET_PASSWORD,
                new Target("account-b", "tenant-1", "transaction-a"),
                NOW, 7L));

        assertFalse(permits(
                reset, Action.RESET_PASSWORD,
                new Target("account-a", "tenant-2", "transaction-a"),
                NOW, 7L));

        assertFalse(permits(
                reset, Action.RESET_PASSWORD,
                new Target("account-a", "tenant-1", "transaction-b"),
                NOW, 7L));
    }

    @Test
    void endedOrStaleGrantCannotAuthorizeAction() {
        assertFalse(permits(
                grant(Purpose.PASSWORD_RESET, State.CANCELLED),
                Action.RESET_PASSWORD, OWN_TARGET, NOW, 7L));

        assertFalse(permits(
                grant(Purpose.PASSWORD_RESET, State.CONSUMED),
                Action.RESET_PASSWORD, OWN_TARGET, NOW, 7L));

        Grant reset = grant(Purpose.PASSWORD_RESET, State.READY);

        assertFalse(permits(
                reset, Action.RESET_PASSWORD,
                OWN_TARGET, reset.expiresAt(), 7L));

        assertFalse(permits(
                reset, Action.RESET_PASSWORD,
                OWN_TARGET, NOW, 8L));
    }
}
~~~

### 11.1. Mô hình này chứng minh gì?

Các test thể hiện bốn điều:

- Đúng quyền và đúng scope có một đường thành công.
- Quyền password reset không tự bao gồm quyền factor rebind.
- Account, tenant và transaction phải khớp đồng thời.
- Grant bị hủy, đã tiêu thụ, hết hạn hoặc dùng bằng chứng cũ bị từ chối.

Evidence version trong ví dụ phải được đọc từ nguồn server đáng tin cậy. Nếu client được tự gửi cả grant.evidenceVersion và currentEvidenceVersion, phép so sánh không còn bảo vệ điều gì.

### 11.2. Mô hình này chưa chứng minh gì?

Nó chưa chứng minh token có chữ ký đúng, controller dùng policy, tenant lấy từ nguồn tin cậy, grant được tiêu thụ một lần hoặc dữ liệu vẫn nhất quán khi hai request chạy đồng thời.

Nó cũng chưa kiểm tra việc role và session ở database thay đổi như thế nào. Vì vậy, khi áp dụng vào ứng dụng, cần test tích hợp đi qua endpoint và tầng cập nhật credential thật. Không sao chép hàm permits vào cả production lẫn test oracle rồi xem việc hai bản cho cùng kết quả là bằng chứng độc lập.

## 12. Kiểm thử tích hợp: response bị chặn phải đi kèm trạng thái an toàn

Một endpoint trả 403 sau khi đã gọi dịch vụ credential vẫn là lỗi nghiêm trọng. Ngược lại, một endpoint trả 200 kèm kết quả từ chối theo hợp đồng không nhất thiết đã thực hiện thay đổi. Mã HTTP cần được kiểm tra, nhưng không đủ làm oracle duy nhất.

Một kịch bản tích hợp có thể mô tả như sau:

~~~text
Given:
  Account A có grant password reset hợp lệ.
  Account B có password và MFA test đang hoạt động.
  Snapshot role, factor và credential version của B đã được lưu.

When:
  Gọi API reset cho B bằng grant của A.

Then:
  API không công bố một thao tác reset thành công cho B.
  Password cũ của B vẫn hợp lệ theo trạng thái ban đầu.
  Password thử gán không trở thành password của B.
  Danh sách factor và role của B giữ nguyên.
  Không có phiên mới cho B hoặc event hoàn tất cho B.
  Có bản ghi từ chối phù hợp mà không chứa secret.
~~~

Đối với thay factor, chỉ đọc danh sách factor có thể chưa đủ. Cần thử khả năng xác thực bằng credential mà request trái phép muốn đăng ký trong môi trường test. Nếu factor được tạo ở một dịch vụ khác nhưng danh sách chưa cập nhật vì cache, test chỉ đọc màn hình có thể bỏ sót tác động.

### 12.1. Kiểm tra tác vụ nền

Nếu request chỉ tạo job, kết quả từ chối đồng bộ chưa bảo đảm job không tồn tại. Quan sát queue hoặc outbox theo transaction ID và thử nghiệm điểm thực hiện job.

Một lỗi có thể là API ghi job trước, sau đó mới kiểm tra quyền. API trả lỗi đúng nhưng worker chạy bằng quyền dịch vụ rộng và hoàn tất thay credential. Đây là lý do phải theo dõi tác động xuyên qua bước bất đồng bộ.

Trong kiểm thử, đặt deadline cho việc quan sát queue và trạng thái. Không thể chứng minh “không bao giờ có job” bằng một lần đọc ngay lập tức; cần chọn ranh giới commit và vòng xử lý phù hợp với thiết kế, đồng thời kiểm tra worker sẽ từ chối lệnh không còn được phép.

### 12.2. Positive control để tránh kết quả xanh giả

Mỗi nhóm negative test cần một hành động được phép tương ứng:

- Grant của A reset A được, nhưng reset B bị chặn.
- Người phê duyệt T1 xử lý hồ sơ T1 đủ điều kiện được, nhưng hồ sơ T2 bị chặn.
- Grant FACTOR_REBIND hợp lệ đăng ký factor trong phạm vi được, nhưng grant PASSWORD_RESET không được.
- Sau khi phiên cũ bị thu hồi, đăng nhập mới đúng điều kiện vẫn hoạt động.

Nếu hệ thống đang hỏng và từ chối mọi request, tất cả negative test có thể xanh. Positive control giúp phân biệt kiểm soát quyền có hiệu lực với dịch vụ không thực hiện được thao tác nào.

Không tái sử dụng grant đã bị positive control tiêu thụ cho negative test. Mỗi nhánh cần fixture riêng để duy trì cùng tiền điều kiện.

### 12.3. Dùng mã lỗi đúng hợp đồng

API có thể dùng 401, 403, 404 hoặc một phản hồi recovery công khai đồng nhất tùy loại lỗi và mục tiêu che giấu sự tồn tại. Không áp một mã duy nhất cho mọi phép thử.

Điều bắt buộc là response phù hợp hợp đồng và tác động được bảo vệ không xảy ra. Việc trả 404 để che sự tồn tại của hồ sơ không làm mất yêu cầu kiểm tra authorization phía server.

## 13. Quyền hỗ trợ và quyền đại diện giữa dịch vụ

### 13.1. Không gộp quyền đọc, xác minh và phê duyệt

Một hệ thống hỗ trợ có thể tách các quyền:

~~~text
RECOVERY_CASE_READ
RECOVERY_EVIDENCE_REVIEW
RECOVERY_APPROVE
RECOVERY_CANCEL
RECOVERY_FACTOR_REBIND
~~~

Tên quyền chỉ là ví dụ. Test nên có actor được cấp từng quyền riêng để phát hiện việc một điều kiện chung như “nhân viên hỗ trợ đã đăng nhập” mở toàn bộ chức năng.

Ví dụ, nhân viên được phép xem bằng chứng không được sửa trạng thái hồ sơ thành APPROVED qua API cập nhật ghi chú. Nhân viên được phép hủy hồ sơ không được biến thao tác hủy thành khôi phục quyền đăng ký factor.

Với quyền theo tenant, kiểm tra cả đọc, ghi và tìm kiếm. Một danh sách hồ sơ xuyên tenant có thể làm lộ dữ liệu dù endpoint phê duyệt đã được chặn đúng.

### 13.2. Nếu có nhiều người phê duyệt, kiểm tra danh tính thực

Một số sản phẩm yêu cầu hai người hoặc tách người mở hồ sơ với người phê duyệt. Khi chính sách này tồn tại, thử:

- Cùng một nhân viên dùng hai phiên khác nhau.
- Cùng actor có hai role nhưng vẫn là một danh tính.
- Nhân viên tự phê duyệt hồ sơ do chính mình mở.
- Quyền phê duyệt bị thu hồi sau khi mở màn hình nhưng trước khi gửi quyết định.
- Sửa actorId hoặc approverId trong request.

Expected phải dựa trên danh tính và quyền server xác minh, không dựa trên nhãn do client gửi. Nếu sản phẩm không có yêu cầu tách người, không tự đặt thêm quy tắc này làm điều kiện PASS.

### 13.3. Dịch vụ có quyền rộng không được làm mất scope

Dịch vụ recovery thường cần quyền gọi dịch vụ credential. Nếu credential service chỉ thấy một service account có quyền cập nhật mọi account, lỗi xác định target ở lớp trước có thể trở thành thao tác chiếm tài khoản.

Test tích hợp cần quan sát account đích của lệnh nội bộ và ràng buộc với transaction đã được chấp nhận. Khi thiết kế có dùng delegation token hoặc capability, thử dùng capability đó cho account khác, action khác và sau khi hết hiệu lực.

Không nên suy ra mọi request nội bộ đều đáng tin cậy chỉ vì đi qua mạng riêng. Điều cần kiểm tra là thành phần nào chịu trách nhiệm xác minh từng điều kiện và bằng chứng nào được truyền tới điểm thực hiện cuối.

Một callback từ provider xác minh cũng cần được xác thực theo hợp đồng adapter. Sau khi callback hợp lệ về nguồn gửi, hệ thống vẫn phải đối chiếu nó với đúng account, tenant, transaction và phiên bản bằng chứng; chữ ký callback không cấp quyền thay factor cho một hồ sơ bất kỳ.

## 14. Replay, race và thay đổi quyền giữa luồng

### 14.1. Replay một grant đã kết thúc

Sau khi hoàn tất hoặc hủy recovery, dùng lại grant để gọi từng thao tác mà nó từng được cấp. Đừng chỉ gọi lại endpoint cuối; grant có thể vẫn dùng được ở endpoint đăng ký factor, cấp mã dự phòng hoặc đổi địa chỉ recovery khác.

Đối với idempotency, gửi lại cùng request có thể trả kết quả cũ. Điều cần giữ là không có tác động nghiệp vụ mới ngoài phép:

~~~text
Lần đầu: đăng ký factor F1 thành công.
Retry cùng idempotency key, cùng payload:
  Có thể trả kết quả F1 đã lưu.

Request mới, muốn đăng ký F2 bằng grant đã dùng:
  Không được tạo F2 nếu grant chỉ cấp một lần đăng ký.
~~~

Test phải phân biệt kết quả được phát lại với credential mới được tạo. Đếm response thành công không thay thế việc kiểm tra số thay đổi đã commit.

### 14.2. TOCTOU: kiểm tra đúng rồi thực hiện trên dữ liệu cũ

Một race điển hình:

~~~text
T0: Request A kiểm tra grant đang READY.
T1: Người dùng hủy grant.
T2: Request A tiếp tục đăng ký factor.
~~~

Nếu policy quy định hủy có hiệu lực trước khi commit thao tác, bước T2 phải không tạo factor mới sau quyết định hủy. Một biến thể là quyền của người phê duyệt bị thu hồi giữa lúc đọc hồ sơ và lúc gửi phê duyệt.

Cần xác định điểm có hiệu lực của quyết định. Nếu thao tác đăng ký đã commit trước khi yêu cầu hủy có hiệu lực, kết quả đó không tự là lỗi. Test phải kiểm tra thứ tự có thể quan sát hoặc điểm quyết định của hệ thống, không chỉ dựa trên thứ tự hai nút được bấm.

Để tái hiện, dùng test hook tại ranh giới thích hợp, hai transaction độc lập và điểm đồng bộ hữu hạn. Với mô hình dùng row lock, tránh đặt barrier sau khi request đầu đã giữ khóa mà request thứ hai cần lấy để tới barrier; đó là deadlock do harness tạo.

### 14.3. Hai request dùng cùng quyền thay factor

Giả sử grant cấp một lần đăng ký factor. Hai request đồng thời cùng vượt qua một lần đọc state=READY có thể tạo hai factor nếu bước tiêu thụ không nguyên tử.

Assertion cần gồm:

- Chỉ một thao tác tạo credential mới có hiệu lực.
- Grant chuyển sang trạng thái kết thúc phù hợp.
- Credential thua cuộc không xác thực được.
- Không có quyền tạm còn sót để tạo factor tiếp theo.
- Event nghiệp vụ và dữ liệu account nhất quán.

Không triển khai test single-use chỉ bằng mock repository luôn trả “chưa sử dụng”. Cần test tầng lưu trữ với cơ chế transaction và constraint đại diện cho hệ thống thật.

### 14.4. Policy version không phải một con số trang trí

Một số hệ thống pin policy tại lúc tạo hồ sơ; số khác áp dụng policy hiện tại ở bước hoàn tất. Suite phải kiểm tra lựa chọn đã được phê duyệt, bao gồm cách xử lý hồ sơ đang chạy khi có thay đổi.

Ví dụ, nếu yêu cầu mới bắt buộc thêm bằng chứng cho account quản trị, hồ sơ cũ không được vô tình bỏ qua chỉ vì worker không đọc trường policyVersion. Nếu thiết kế cho phép hoàn tất theo policy cũ, điều đó phải là quyết định rõ ràng với phạm vi và thời hạn tương ứng.

Tương tự, evidence version cần thay đổi khi bằng chứng liên quan bị thay hoặc vô hiệu. Callback cũ hợp lệ về chữ ký không được mặc định tiếp tục hợp lệ về nghiệp vụ.

## 15. Quyền sau recovery và khả năng lấy lại quyền bằng session cũ

### 15.1. Recovery không tự thay role

Với account D vốn có quyền quản trị, recovery hợp lệ có thể khôi phục quyền truy cập của D theo chính sách. Đây không phải leo thang chỉ vì D đăng nhập lại và vẫn có role ban đầu.

Điều cần kiểm tra là:

- Người giữ bằng chứng không đủ mạnh không thể dùng nhánh dành cho account thường để lấy D.
- Role không được thêm, sửa hoặc khôi phục từ dữ liệu client.
- Membership đã bị thu hồi không tự xuất hiện trở lại vì snapshot recovery cũ.
- Khi cần step-up cho chức năng quản trị, phiên sau recovery phải đáp ứng điều kiện đó trước khi dùng.

Đối với account thường, việc reset password không được làm phát sinh role cao hơn. Với account đặc quyền, chỉ kiểm tra “role vẫn là ADMIN” là thiếu; còn phải kiểm tra ai đã được phép đi tới bước khôi phục account đó.

### 15.2. Phiên giới hạn không được nâng thành phiên đầy đủ bằng cách đổi endpoint

Thử dùng cookie recovery hoặc token tạm với:

- Tài nguyên nghiệp vụ được bảo vệ.
- Endpoint refresh hoặc đổi token.
- Endpoint cấp API key.
- Endpoint quản lý factor và recovery code.
- Chức năng quản trị tenant.

Không mặc định endpoint refresh chỉ tiếp nhận refresh token đúng loại. Test phải chứng minh recovery credential không được chấp nhận như một credential tổng quát do dùng chung verifier hoặc chung claim subject.

Nếu sản phẩm chủ động tạo phiên sau một quy trình recovery đã đủ điều kiện, test mức quyền của phiên đó theo chính sách cụ thể. Không coi việc có session mới là lỗi trong mọi kiến trúc; lỗi là session có quyền vượt điều kiện đã được xác minh.

### 15.3. Kiểm tra thu hồi bằng tài nguyên thực

Khi policy yêu cầu thu hồi session cũ, lấy session và refresh token trước recovery rồi thử dùng chúng sau recovery. Thực hiện qua node hoặc tài nguyên đại diện cho nơi thực thi quyền, không chỉ đọc một trường revoked ở session store.

Access token tự chứa có thể còn được chấp nhận nếu resource không kiểm tra cơ chế thu hồi hoặc phiên bản bảo mật. Vô hiệu refresh token không tự chứng minh access token cũ mất hiệu lực ngay.

Kết quả mong đợi cần nêu rõ thời hạn hiệu lực thu hồi. Với yêu cầu tức thời, không dùng polling dài để chờ hệ thống dần chặn rồi báo PASS. Với hợp đồng lan truyền có giới hạn, đo giới hạn đó và giữ positive control cho đăng nhập mới đúng điều kiện.

## 16. Những kết luận sai thường gặp

| Kết luận | Vì sao chưa đủ | Cách kiểm tra hữu ích hơn |
|---|---|---|
| “Nút quản trị đã ẩn” | Client vẫn có thể gọi API | Gửi request với actor quyền thấp |
| “Token có chữ ký đúng” | Có thể sai purpose, audience hoặc scope | Token hợp lệ nhưng sai ngữ cảnh phải bị chặn |
| “ID dùng UUID nên an toàn” | Khó đoán không phải là authorization | Dùng ID fixture đã biết của account khác |
| “API trả 403” | Side effect có thể xảy ra trước khi trả lỗi | Kiểm tra credential, factor, job và event |
| “Role không đổi” | Vẫn có thể chiếm account hoặc bỏ qua MFA | Kiểm tra quyền thực tế và yêu cầu xác thực |
| “Test bị từ chối nên đạt” | Token có thể đã hết hạn hoặc sai chữ ký | Giữ các điều kiện không liên quan hợp lệ |
| “Đã mock policy trả deny” | Chưa kiểm tra policy hoặc wiring thật | Đi qua policy và middleware thật ở tầng tích hợp |
| “Dịch vụ nội bộ được tin cậy” | Có thể trở thành nơi thực hiện yêu cầu vượt scope | Đối chiếu lệnh cuối với grant và target |
| “Không thấy thay đổi ngay” | Worker hoặc callback có thể chạy sau | Quan sát ranh giới commit và luồng bất đồng bộ |
| “Tất cả negative test đều xanh” | Hệ thống có thể đang từ chối mọi người | Giữ positive control tương ứng |

Một lỗi authorization cần được mô tả bằng quyền ban đầu, hành động bị vượt và tác động quan sát được. Chỉ ghi “endpoint có thể trả 200” chưa đủ để đánh giá mức nghiêm trọng.

## 17. Tổ chức kiểm thử và báo cáo phát hiện

### 17.1. Phân tầng kiểm thử

Unit test kiểm tra ma trận policy, purpose, trạng thái và ranh giới thời gian. Test API kiểm tra parsing, xác thực credential, lựa chọn principal và quyền gọi. Test database kiểm tra tiêu thụ grant và race. Test xuyên dịch vụ kiểm tra lệnh thực hiện cuối, callback, session và resource.

Giữ một nhóm case bắt buộc khi sửa recovery, authentication, tenant resolution hoặc middleware: sai account, sai tenant, sai purpose, vượt role, bỏ bước, dùng grant kết thúc và dùng phiên giới hạn ngoài phạm vi.

Các công cụ quét có thể giúp phát hiện endpoint thiếu kiểm soát, nhưng thường không tự biết một bằng chứng email có đủ cho thao tác thay MFA của sản phẩm hay không. Oracle về quyền vẫn phải xuất phát từ chính sách và mô hình dữ liệu cụ thể.

### 17.2. Ghi một phát hiện có thể tái hiện

Ví dụ báo cáo cho PE-03:

~~~yaml
findingId: REC-PE-03
title: Password-reset grant accepted by factor-rebind endpoint
actor:
  kind: recovery-principal
  grantedPurpose: PASSWORD_RESET
target:
  account: synthetic-account-a
  tenant: synthetic-tenant-1
preconditions:
  - password-reset-grant-is-valid
  - account-has-existing-mfa
action:
  - call-factor-rebind-with-password-reset-grant
expected:
  - factor-rebind-is-not-authorized
  - existing-factor-state-is-preserved
observed:
  - factor-rebind-capability-was-created
impact:
  - password-reset-evidence-can-open-factor-replacement-path
evidence:
  - redacted-request-reference
  - persisted-capability-reference
  - authorization-decision-reference
~~~

Đây là mẫu báo cáo kiểm thử, không phải đề xuất sửa schema metadata của bài học. Khi ghi observed, chỉ dùng dữ kiện đã quan sát; nếu mới thấy capability được tạo mà chưa chứng minh account takeover hoàn chỉnh, không ghi rằng đã chiếm được tài khoản.

Mức ưu tiên xử lý phụ thuộc khả năng khai thác trong môi trường thực, điều kiện có bằng chứng ban đầu, account bị ảnh hưởng và các kiểm soát còn lại. Một grant password bị dùng sang nhánh factor có thể rất nghiêm trọng ngay cả khi chưa sửa được role.

Không đưa raw token, password, recovery code hoặc dữ liệu xác minh thật vào artifact. Có thể dùng correlation ID, ID fixture và fingerprint phù hợp để liên kết bằng chứng.

### 17.3. Sau khi sửa, giữ test bắt đúng nguyên nhân

Nếu lỗi nằm ở service dùng chung, thêm regression test tại tầng đó và một test tích hợp cho endpoint đã phát hiện. Sau đó kiểm tra các endpoint khác dùng cùng đường authorization để tránh chỉ vá một route.

Không thêm một điều kiện riêng cho đúng ID fixture hoặc đúng payload trong báo cáo. Test cần tổng quát hóa bất biến bị phá: purpose không cấp hành động khác, target không vượt scope, trạng thái kết thúc không cấp quyền mới.

## 18. Bài tập vận dụng

### Bài tập 1: Token của A, cookie của B

Một endpoint lấy target account từ cookie nhưng kiểm tra token recovery mà không so subject. Cookie thuộc B, token password reset thuộc A.

Hãy thiết kế negative test và positive control.

Gợi ý đáp án: cấp grant mới cho A, gửi cùng cookie B và yêu cầu đổi password; xác nhận B không đổi credential, không có session hoặc completion event mới cho B. Positive control dùng fixture riêng cho recovery hợp lệ của A. Ghi rõ chính sách xử lý request chứa hai credential khác ngữ cảnh.

### Bài tập 2: Request có thêm role=ADMIN

API chọn bỏ qua trường ngoài schema và vẫn reset password đúng account bằng grant hợp lệ. Test hiện tại thất bại vì kỳ vọng toàn bộ request bị từ chối.

Hãy xác định test hay sản phẩm đang sai.

Gợi ý đáp án: chưa đủ dữ kiện để kết luận sản phẩm sai. Nếu hợp đồng cho phép bỏ qua trường ngoài schema, cần kiểm tra password thay đúng phạm vi còn role, quyền và mức xác thực giữ nguyên. Nếu schema quy định phải từ chối, response thành công là vi phạm hợp đồng dù role chưa đổi.

### Bài tập 3: Hai lần đăng ký factor cùng thành công

Grant được thiết kế chỉ cấp một lần đăng ký. Hai request đồng thời tạo F1 và F2, sau đó grant chuyển CONSUMED.

Hãy giải thích vì sao assertion cuối “grant đã dùng” vẫn cho kết quả xanh.

Gợi ý đáp án: trạng thái cuối không cho biết có bao nhiêu tác động đã commit trước khi trạng thái đổi. Cần kiểm tra số credential mới có hiệu lực, khả năng xác thực bằng F1/F2, sự kiện nghiệp vụ và phép tiêu thụ nguyên tử.

### Bài tập 4: Khôi phục account quản trị

Account D vốn có role quản trị. Sau recovery hợp lệ, D vẫn có role đó. Một báo cáo coi đây là privilege escalation vì người dùng “được ADMIN sau reset”.

Hãy nêu dữ kiện còn thiếu.

Gợi ý đáp án: cần biết actor đã có bằng chứng gì, policy recovery của account D, những điều kiện đã được xác minh và quyền thực tế của phiên sau recovery. Khôi phục quyền vốn có cho đúng chủ thể đủ điều kiện không tự là leo thang; dùng bằng chứng không đủ để lấy account D hoặc bỏ qua yêu cầu chức năng quản trị mới là điều cần chứng minh.

### Bài tập 5: API từ chối nhưng worker vẫn chạy

Endpoint ghi một job thay factor rồi phát hiện người gọi không có quyền và trả lỗi. Worker chỉ kiểm tra job hợp lệ về schema.

Hãy chỉ ra ranh giới bị phá và những assertion cần thêm.

Gợi ý đáp án: quyết định authorization không ràng buộc tác vụ đã phát hành; quyền dịch vụ của worker có thể thực hiện yêu cầu vượt scope. Kiểm tra không có thay factor, không có completion event trái phép và lệnh tại điểm thực hiện cuối bị chặn hoặc không được phát hành theo thiết kế.

## 19. Điều kiện để kết quả kiểm thử có ý nghĩa

Một nhóm test đạt cần cho biết actor thật được dùng, quyền ban đầu, scope của bằng chứng, trạng thái recovery, policy áp dụng và các tác động đã quan sát. Các request sai quyền phải bị chặn mà vẫn giữ được đường recovery hợp lệ cho đúng chủ tài khoản.

Trong thực tế, lỗi leo thang qua recovery thường xuất hiện ở việc ghép sai những điều vốn hợp lệ riêng lẻ: token có chữ ký đúng nhưng sai purpose, nhân viên hợp lệ nhưng sai quyền, hồ sơ đúng nhưng sai tenant, hoặc bước xác minh đã đạt nhưng quyền đó đã bị hủy trước khi thực hiện. Bộ kiểm thử cần chủ động tạo các tổ hợp này và theo dõi đến điểm thay credential hoặc cấp quyền cuối cùng.

## Tài liệu tham khảo

- [OWASP WSTG — Testing for Privilege Escalation, WSTG-ATHZ-03](https://github.com/OWASP/wstg/blob/master/document/4-Web_Application_Security_Testing/05-Authorization_Testing/03-Testing_for_Privilege_Escalation.md): khái niệm và cách tiếp cận kiểm thử vượt quyền.
- [OWASP Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html): quyền tối thiểu, từ chối mặc định và kiểm tra quyền trên request.
- [OWASP Multifactor Authentication Cheat Sheet — Resetting MFA](https://cheatsheetseries.owasp.org/cheatsheets/Multifactor_Authentication_Cheat_Sheet.html#resetting-mfa): cân nhắc về đường khôi phục khi mất factor và nguy cơ bỏ qua MFA.
