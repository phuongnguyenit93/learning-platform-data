# Authentication context trong PAM

## Mục tiêu bài học

Trong Privileged Access Management (PAM), biết một người “đã đăng nhập” chưa đủ để quyết định họ có thể thực hiện một hành động đặc quyền hay không. Hệ thống còn cần hiểu danh tính nào đã được xác thực, bởi ai, bằng phương thức gì, khi nào và kết quả đó gắn với phiên nào.

**Authentication context**, hay ngữ cảnh xác thực, là tập thông tin giúp diễn giải và đánh giá một sự kiện xác thực. Khi được thu thập từ nguồn tin cậy và sử dụng đúng ngữ nghĩa, nó cho phép PAM phân biệt một phiên SSO cũ với một lần xác thực mới đáp ứng yêu cầu của thao tác nhạy cảm.

Sau bài học, bạn có thể:

- Phân biệt ngữ cảnh xác thực với quyền, phê duyệt và ngữ cảnh rủi ro.
- Xác định thuộc tính cần thiết, nguồn gốc và giới hạn của bằng chứng.
- Diễn giải thông tin phương thức, mức bảo đảm và thời điểm xác thực.
- Chuẩn hóa ngữ cảnh từ nhiều IdP mà không nâng mức tin cậy ngoài ý định.
- Ràng buộc ngữ cảnh với đúng người, phiên, bên nhận và hành động.
- Lưu bằng chứng để giải thích một quyết định truy cập đặc quyền.

Các mô hình dữ liệu, tên profile và thời hạn trong bài là minh họa. Chúng không phải cấu hình sản phẩm hoặc hệ thống phân hạng bắt buộc áp dụng chung.

## 1. Một kết quả đăng nhập cần được giải thích

An và Bình cùng mở cổng PAM lúc 10:00. Cả hai đều có phiên hợp lệ.

- An vừa xác thực bằng một phương thức đáp ứng yêu cầu của tổ chức.
- Bình nhận token mới từ phiên SSO đã được xác thực từ 07:00.
- Thiết bị của An đáp ứng điều kiện quản trị hiện tại.
- Thiết bị của Bình chưa có dữ liệu trạng thái đủ mới.

Nếu PAM chỉ có cờ `logged_in=true`, các trường hợp này trông giống nhau. Nếu PAM hiểu ngữ cảnh, hệ thống có thể yêu cầu Bình cung cấp bằng chứng xác thực mới hoặc xử lý điều kiện thiết bị trước một thao tác đặc quyền.

Điều đó không có nghĩa An tự động được quản trị mọi tài sản. Ngữ cảnh tốt giúp đánh giá độ tin cậy của xác thực; quyền vẫn cần được kiểm tra riêng.

## 2. Phân biệt bốn nhóm thông tin

| Nhóm | Câu hỏi chính | Ví dụ |
|---|---|---|
| Danh tính | Chủ thể nào đang được nói đến? | Principal PAM ánh xạ từ issuer và subject |
| Ngữ cảnh xác thực | Chủ thể được xác thực như thế nào và khi nào? | Phương thức, bên xác thực, thời điểm, phiên liên quan |
| Ngữ cảnh truy cập và rủi ro | Điều kiện hiện tại của yêu cầu là gì? | Thiết bị, nguồn kết nối, tín hiệu xâm nhập, tài sản và hành động |
| Cấp phép và phê duyệt | Chủ thể được phép làm gì? | Vai trò, grant JIT, ticket và quyết định chủ sở hữu |

Trong một kiến trúc, các nhóm này có thể cùng được đưa vào một đối tượng đánh giá. Tuy nhiên, chúng có nguồn, thời gian hiệu lực và ý nghĩa khác nhau.

Ví dụ, “được quản lý phê duyệt” không phải phương thức xác thực. “Đến từ mạng nội bộ” cũng không chứng minh đã dùng MFA. Một lần MFA thành công không chứng minh ticket còn hiệu lực.

Trong các giao thức liên kết, thuật ngữ ngữ cảnh xác thực có thể chỉ những trường cụ thể về lần xác thực hoặc lớp bảo đảm. Trong chính sách PAM, tổ chức có thể sử dụng thêm dữ liệu thiết bị và rủi ro. Cần ghi rõ ranh giới này để không biến một claim xác thực thành kết luận về toàn bộ môi trường.

## 3. Những thành phần quan trọng của authentication context

### 3.1. Chủ thể và miền tin cậy

Cần xác định danh tính trong đúng miền phát hành. Một subject giống nhau từ hai IdP không nhất thiết là cùng người.

Thông tin hữu ích có thể gồm:

- Bên phát hành hoặc nguồn xác thực.
- Định danh chủ thể tại nguồn đó.
- Principal nội bộ đã được ánh xạ có kiểm soát.
- Định danh sự kiện xác thực hoặc mã tương quan.
- Phiên PAM mà kết quả được dùng để thiết lập hoặc tăng cường.

Không dùng riêng tên hiển thị hoặc email để chứng minh ngữ cảnh thuộc về đúng tài khoản đặc quyền. Những thuộc tính đó có thể thay đổi, trùng hoặc được tái sử dụng.

### 3.2. Phương thức xác thực

Ngữ cảnh có thể mô tả việc sử dụng mật khẩu, mã dùng một lần, thiết bị xác thực hoặc những phương thức khác.

Một danh sách phương thức không tự trả lời đầy đủ:

- Các phương thức có được IdP thực sự xác minh không?
- Chúng có thuộc cùng lần xác thực liên quan không?
- Chúng đáp ứng yêu cầu chống phishing hoặc yêu cầu khác không?
- Người dùng có vừa thực hiện phương thức cần thiết hay chỉ tái sử dụng một phiên cũ?
- Cách khôi phục hoặc thay thế phương thức có làm thay đổi mức tin cậy không?

Không đếm số chuỗi trong một mảng rồi kết luận có từng đó yếu tố độc lập. Tương tự, nhãn “MFA” cần có ý nghĩa được thống nhất với nguồn phát hành.

### 3.3. Mức bảo đảm hoặc profile

Một profile xác thực có thể biểu diễn một tập yêu cầu về phương thức và quy trình. PAM cần biết profile đó có ý nghĩa gì trong quan hệ tin cậy cụ thể.

Không giả định profile có tên `level-3` từ IdP A tương đương profile cùng tên từ IdP B. Không so sánh các giá trị bằng thứ tự chữ hoặc con số nếu chưa có quy tắc ngữ nghĩa.

Một profile nội bộ minh họa như `privileged-human-strong` có thể ánh xạ từ những giá trị đã được đánh giá của từng nguồn. Bảng ánh xạ đó là cấu hình bảo mật cần phiên bản và kiểm soát thay đổi.

### 3.4. Thời điểm xác thực

Cần phân biệt:

| Mốc | Ý nghĩa |
|---|---|
| Thời điểm xác thực | Khi sự kiện xác thực liên quan xảy ra theo nguồn có thẩm quyền |
| Thời điểm phát hành bằng chứng | Khi assertion hoặc token được tạo |
| Thời điểm PAM nhận bằng chứng | Khi ứng dụng thu nhận kết quả |
| Thời điểm đánh giá | Khi PAM ra quyết định cho hành động |
| Thời điểm hết hạn bằng chứng | Giới hạn sử dụng theo giao thức hoặc chính sách |

Token vừa được phát hành không nhất thiết dựa trên một lần xác thực mới. Việc tải lại trang hoặc làm mới cookie cũng không làm tuổi xác thực trở về không.

Nếu một chính sách yêu cầu MFA mới thực hiện, thông tin thời gian phải đủ để chứng minh điều đó theo hợp đồng với IdP. Một thời điểm chung không tự cho biết mỗi yếu tố được thực hiện lúc nào.

### 3.5. Bên nhận và ràng buộc phiên

Bằng chứng xác thực cần đúng bên nhận và giao dịch. Một ID token dành cho ứng dụng khác hoặc ngữ cảnh của một người khác không được dùng cho phiên PAM hiện tại.

Khi chuyển ngữ cảnh giữa thành phần, cần biết nó được bảo vệ thế nào, dành cho dịch vụ nào và có thể được dùng trong khoảng thời gian nào.

Một HTTP header có tên `X-MFA-Verified` do client tự gửi không phải bằng chứng. Nếu kiến trúc dùng gateway để truyền ngữ cảnh, chỉ thành phần được tin cậy mới được đặt dữ liệu đó và dịch vụ nhận phải có cơ chế kiểm chứng, chống giả mạo và ràng buộc phù hợp.

Kết nối mã hóa bảo vệ đường truyền nhưng không tự làm mọi trường dữ liệu trên đường truyền trở thành đúng về mặt danh tính người dùng.

## 4. Ngữ nghĩa trong OIDC và SAML

PAM nên dùng thư viện và cơ chế tích hợp được duy trì để kiểm tra bằng chứng. Những trường dưới đây chỉ giúp hiểu ngữ nghĩa, không thay thế toàn bộ quy trình xác minh giao thức.

### 4.1. Ví dụ với OpenID Connect

Một số claim thường liên quan đến ngữ cảnh:

| Claim | Cách hiểu ở mức khái niệm |
|---|---|
| `iss` và `sub` | Bên phát hành và chủ thể trong miền đó |
| `auth_time` | Thời điểm xác thực của người dùng mà IdP khẳng định theo ngữ nghĩa giao thức |
| `amr` | Các phương thức xác thực được biểu diễn bởi nguồn phát hành |
| `acr` | Lớp hoặc tham chiếu ngữ cảnh xác thực |
| `aud` | Bên nhận mà bằng chứng hướng tới |
| `iat`, `exp` | Thời điểm phát hành và hết hạn của token |

Không phải mọi phản hồi đều có đủ các claim trên. PAM phải xác định thông tin bắt buộc cho từng luồng và cách yêu cầu hoặc xử lý khi thiếu.

`iat` không thay cho `auth_time`. `amr` không tự cung cấp thời điểm riêng của từng phương thức. `acr` không có một thứ tự “cao hơn” chung cho mọi IdP.

Trước khi sử dụng nội dung claim, cần kiểm tra bằng chứng đúng giao thức, issuer, bên nhận, thời hạn và các ràng buộc giao dịch. Việc giải mã được nội dung token không chứng minh token đáng tin.

### 4.2. Ví dụ với SAML

Trong SAML, thông tin ngữ cảnh có thể xuất hiện trong statement xác thực, chẳng hạn thời điểm xác thực và tham chiếu lớp ngữ cảnh.

Cần biết IdP phát giá trị nào, SP yêu cầu hoặc chấp nhận giá trị nào và chúng được ánh xạ sang chính sách PAM ra sao.

Một assertion có chữ ký hợp lệ nhưng không đáp ứng mức ngữ cảnh yêu cầu vẫn có thể chưa đủ để thực hiện hành động đặc quyền. Ngược lại, việc có tên profile mong muốn trong một phần dữ liệu chưa được xác minh không tạo ra bằng chứng hợp lệ.

### 4.3. Chuẩn hóa không được làm mất nguồn gốc

Khi quy đổi dữ liệu từ nhiều giao thức, nên giữ:

- Giá trị nguồn có liên quan, ở mức không tiết lộ bí mật.
- Nguồn phát hành và cấu hình tin cậy được dùng.
- Giá trị chuẩn hóa.
- Phiên bản quy tắc ánh xạ.
- Thời gian và kết quả kiểm tra.

Không quy mọi giá trị lạ thành “MFA đạt”. Một giá trị không biết hoặc không được hỗ trợ cần được biểu diễn là chưa xác định hoặc chưa đáp ứng theo chính sách.

## 5. Thiết kế mô hình ngữ cảnh có thể kiểm chứng

Một thiết kế hữu ích tách **sự kiện xác thực đã xảy ra** khỏi **đánh giá hiện tại cho một hành động**.

Sự kiện gốc giúp giải thích lịch sử. Đánh giá hiện tại kết hợp sự kiện đó với quyền và tín hiệu mới. Không sửa thời điểm xác thực cũ để làm nó trông mới hơn khi phiên được gia hạn.

### 5.1. Sự kiện xác thực đã xác minh

```yaml
authentication_event:
  event_id: PAM-AUTHN-401
  source:
    trust_configuration: corp-idp-trust-01
    issuer_reference: corp-idp
    provider_event_reference: IDP-EVT-882
  subject:
    external_subject: subject-7258
    pam_principal: person-041
  authentication:
    occurred_at: "2026-12-05T10:00:00+07:00"
    source_context_class: provider-profile-A
    source_methods:
      - provider-method-reference
    normalized_profile: privileged-human-strong
    mapping_version: authn-map-v4
  binding:
    relying_party: pam-console
    pam_session_reference: PAM-SESSION-903
  verification:
    verifier: federation-component
    verified_at: "2026-12-05T10:00:03+07:00"
    result: accepted
  evidence_reference: protected-authn-evidence-401
```

Đây là cấu trúc minh họa, không phải các claim gốc của một giao thức. Những giá trị như `accepted` phải là kết quả do thành phần xác minh tin cậy tạo ra, không phải trường được nhận nguyên trạng từ trình duyệt.

`evidence_reference` là tham chiếu được bảo vệ; không nên biến nó thành nơi lưu token nguyên vẹn trong log thông thường.

### 5.2. Đánh giá cho một hành động

```yaml
access_evaluation:
  evaluation_id: EVAL-614
  evaluated_at: "2026-12-05T10:07:00+07:00"
  subject: person-041
  session_reference: PAM-SESSION-903
  authentication_event_reference: PAM-AUTHN-401
  action:
    type: reveal_credential
    asset_reference: database-prod-02
    secret_reference: secret-ref-182
  current_conditions:
    identity_status: active
    approval_reference: APPROVAL-912
    jit_grant_reference: GRANT-522
    device_assessment_reference: DEVICE-ASSESS-740
    risk_assessment_reference: RISK-ASSESS-311
  policy:
    version: pam-action-policy-v6
    required_profile: privileged-human-strong
    maximum_authentication_age_seconds: 120
  result:
    decision: reauthenticate
    reason: authentication_too_old
```

Lần xác thực lúc 10:00 đã bảy phút tuổi tại thời điểm 10:07, nên không đáp ứng ngưỡng hai phút của ví dụ. Một token phát lúc 10:06 không thay đổi điều đó nếu nó vẫn dựa trên lần xác thực 10:00.

Các mã phê duyệt và grant chỉ là tham chiếu. Thành phần quyết định phải xác minh trạng thái thực tế, không coi việc có một chuỗi mã là đã đủ quyền.

### 5.3. Dữ liệu chưa biết khác dữ liệu không đạt

Nên phân biệt các trạng thái như:

- Đã xác minh và đáp ứng.
- Đã xác minh nhưng không đáp ứng.
- Thiếu dữ liệu.
- Dữ liệu quá cũ.
- Nguồn không tin cậy.
- Xung đột hoặc không thể diễn giải.

Nếu thiếu `auth_time`, không thể tự kết luận lần xác thực vừa xảy ra. Nếu nguồn phương thức chưa được ánh xạ, không thể tự nâng thành profile yêu cầu.

Việc xử lý trạng thái chưa biết phụ thuộc chính sách của hành động. Với điều kiện bắt buộc, thường cần thêm bằng chứng hoặc từ chối hành động; không tự biến thiếu thông tin thành kết quả thuận lợi.

## 6. Kiểm tra chất lượng ngữ cảnh trước khi dùng

### 6.1. Nguồn gốc

Dữ liệu đến từ IdP đã được cấu hình, thành phần xác minh hay một trường do client tự khai? Nếu lấy từ API bổ sung, API đó có đúng bên cung cấp và đúng chủ thể không?

Tên trường nghe có vẻ đáng tin không làm dữ liệu trở nên đáng tin. Cần xác định đường tin cậy từ nguồn đến nơi ra quyết định.

### 6.2. Tính toàn vẹn

Ngữ cảnh có bị sửa khi đi qua proxy, hàng đợi hoặc dịch vụ trung gian không? Thành phần nào có thể tạo hoặc thay đổi dữ liệu đã chuẩn hóa?

Nếu dùng chữ ký hoặc cơ chế bảo vệ thông điệp, cần quản lý khóa, bên nhận, thời hạn và ràng buộc liên quan. Một chữ ký đúng không thay thế kiểm tra xem người phát hành có được phép khẳng định thuộc tính đó hay không.

### 6.3. Độ mới

Mỗi loại dữ liệu có thể có thời hạn khác nhau:

| Dữ liệu | Điều cần kiểm tra |
|---|---|
| Sự kiện xác thực | Tuổi của bằng chứng đáp ứng phương thức yêu cầu |
| Trạng thái tài khoản | Có cập nhật khóa hoặc nghỉ việc mới không? |
| Điều kiện thiết bị | Đánh giá được thực hiện khi nào, còn giá trị không? |
| Tín hiệu rủi ro | Có tín hiệu mới hoặc khoảng trễ thu thập không? |
| Phê duyệt và grant | Còn hiệu lực tại lúc thực hiện hành động không? |

Không dùng thời hạn còn lại của token làm thời hạn chung của mọi dữ liệu.

Cần đồng bộ thời gian và quy định sai lệch cho phép. Một mốc xác thực ở tương lai bất hợp lý không nên được dùng để tạo tuổi âm rồi coi bằng chứng luôn mới.

### 6.4. Tính ràng buộc

Kiểm tra ngữ cảnh thuộc đúng người, phiên, ứng dụng và hành động mà chính sách đang xét. Khi người dùng đổi tài sản, tăng quyền hoặc mở phiên mới, phải xác định có được tái sử dụng bằng chứng hay không.

Một lần xác thực có thể phục vụ nhiều quyết định nếu chính sách cho phép, nhưng mỗi quyết định vẫn cần kiểm tra quyền và điều kiện hiện tại. Ngữ cảnh không nên trở thành vé toàn quyền.

### 6.5. Khả năng giải thích

Một quyết định nên chỉ ra được dữ liệu và quy tắc có liên quan:

> Từ chối checkout vì nguồn xác thực không có profile được chấp nhận cho hành động này.

hoặc:

> Yêu cầu xác thực lại vì lần đáp ứng profile yêu cầu đã quá thời hạn.

Không cần đưa toàn bộ dữ liệu nhạy cảm ra giao diện. Log dành cho vận hành có thể chi tiết hơn nhưng vẫn phải được bảo vệ.

## 7. Từ ngữ cảnh đến quyết định trong PAM

Một luồng tham khảo:

```text
Yêu cầu hành động
       |
       v
Xác định chủ thể, phiên và phạm vi hành động
       |
       v
Lấy bằng chứng xác thực đã được xác minh
       |
       v
Kiểm tra nguồn, phương thức, profile, thời gian và ràng buộc
       |
       +--> Thiếu độ mới/profile --> Yêu cầu xác thực phù hợp
       |
       +--> Nguồn không hợp lệ --> Từ chối
       |
       v
Kiểm tra quyền, phê duyệt, JIT và điều kiện hiện tại
       |
       +--> Không đáp ứng --> Từ chối / xử lý theo chính sách
       |
       v
Thực thi đúng hành động và ghi bằng chứng
```

Thứ tự triển khai có thể khác, nhưng không nên tạo thử thách xác thực không cần thiết cho một hành động chắc chắn không được phép.

### 7.1. Đăng nhập cổng khác với tiết lộ bí mật

Một profile có thể đủ để tạo phiên cổng PAM nhưng chưa đủ để hiển thị credential quản trị. Hành động tiết lộ có thể cần bằng chứng mới hơn hoặc khác, cùng phê duyệt và giới hạn riêng.

Ngay cả khi đã có profile phù hợp, cần giới hạn đúng bí mật, tài sản và số lần sử dụng theo chính sách. Việc không hiển thị mật khẩu mà dùng cơ chế thiết lập phiên qua vault có thể giảm lộ bí mật, nhưng không loại bỏ nhu cầu kiểm soát quyền thực thi.

### 7.2. Xác thực lại tạo một sự kiện mới

Khi cần xác thực lại, giữ sự kiện cũ để giải thích lịch sử và liên kết một sự kiện mới vào lần đánh giá mới.

Sau khi người dùng hoàn tất, cần kiểm tra lại điều kiện có thể đã đổi trong lúc xác thực: danh tính bị khóa, ticket bị hủy, grant hết hạn hoặc thiết bị có cảnh báo.

Không lấy kết quả xác thực thành công làm lý do bỏ qua các điều kiện này.

### 7.3. Phương thức mạnh không chứng minh ý định mọi hành động

Một phương thức chống phishing có thể giảm nguy cơ bị sử dụng tại dịch vụ giả mạo. Nó không tự chứng minh người dùng đã xem và chấp thuận toàn bộ nội dung một thao tác phía sau.

Nếu yêu cầu xác nhận nội dung giao dịch, cần có cơ chế hiển thị và ràng buộc nội dung riêng. Không mặc định một lần chạm thiết bị xác thực là sự đồng ý cho mọi lệnh quản trị trong phiên.

### 7.4. Rủi ro thay đổi khi phiên đang chạy

Sự kiện xác thực cũ vẫn là một sự kiện đã xảy ra, nhưng có thể không còn đủ để cho phép tiếp tục. Nếu nhận tín hiệu phiên hoặc thiết bị bị xâm nhập, hệ thống cần đánh giá và thực thi chính sách hiện tại.

Tùy giao thức và kiến trúc, PAM có thể chặn thao tác tiếp theo, không cấp thêm quyền hoặc ngắt phiên. Không giả định mọi giao thức đều cho phép hỏi MFA trước từng lệnh.

Ngắt phiên cũng không tự dừng mọi tác vụ hoặc thu hồi mọi token trên máy đích. Cần cơ chế kiểm chứng và xử lý các trạng thái liên quan.

## 8. Tình huống thực hành: cùng token mới, quyết định khác nhau

### 8.1. Chính sách minh họa

Một hành động hiển thị credential sản xuất yêu cầu:

- Danh tính và phiên PAM hợp lệ.
- Profile xác thực nội bộ `privileged-human-strong`.
- Bằng chứng đáp ứng yêu cầu không quá hai phút.
- Thiết bị đáp ứng điều kiện hiện tại.
- Phê duyệt và grant JIT còn hiệu lực.
- Kết quả gắn đúng chủ thể, phiên, bí mật và hành động.

Không có điều kiện nào trong số này tự thay thế điều kiện khác.

### 8.2. Bốn trường hợp

| Trường hợp | Dữ liệu quan sát | Quyết định phù hợp |
|---|---|---|
| A | Xác thực lúc 10:00 từ nguồn tin cậy, profile đạt; yêu cầu lúc 10:01; các điều kiện khác hợp lệ | Có thể cho phép đúng hành động sau kiểm tra cuối |
| B | Token phát lúc 10:01 nhưng xác thực thực sự lúc 08:00 | Chưa đáp ứng độ mới; yêu cầu xác thực lại |
| C | Có nhãn phương thức giống A nhưng issuer ngoài quan hệ tin cậy | Không chấp nhận nguồn làm bằng chứng cho hành động |
| D | Xác thực mới, profile đạt nhưng phê duyệt đã bị hủy | Từ chối hành động do không còn đủ quyền |

B và A có thể cùng sở hữu token mới. C và A có thể cùng hiển thị một nhãn “MFA”. D và A có thể cùng có bằng chứng xác thực mạnh. Ngữ cảnh cần được diễn giải cùng nguồn, thời gian và quyền hiện tại để tạo quyết định khác nhau.

### 8.3. Dòng sự kiện của trường hợp B

1. PAM nhận yêu cầu checkout và tìm sự kiện xác thực lúc 08:00.
2. Chính sách yêu cầu độ mới hai phút nên PAM tạo ngữ cảnh xác thực lại.
3. Ngữ cảnh gắn với người dùng, phiên, bí mật tham chiếu và hành động checkout.
4. IdP cung cấp kết quả mới đáp ứng hợp đồng tích hợp.
5. PAM xác minh kết quả và ghi sự kiện xác thực mới.
6. PAM kiểm tra lại grant, phê duyệt, thiết bị và phạm vi.
7. Nếu đủ điều kiện, PAM thực hiện đúng checkout và ghi kết quả.

Nếu ở bước 4 IdP chỉ trả lại bằng chứng dựa trên lần 08:00 mà không đáp ứng yêu cầu, luồng chưa thành công. Không cập nhật thời điểm xác thực thành giờ PAM nhận phản hồi.

### 8.4. Thay tài sản giữa luồng

Người dùng bắt đầu xác thực cho bí mật A nhưng gửi yêu cầu thực thi bí mật B.

PAM cần đối chiếu phạm vi đã ràng buộc. Kết quả của A không tự mở B. Có thể cần tạo một đánh giá hoặc ngữ cảnh mới theo chính sách.

Không đưa giá trị bí mật vào log hoặc thông báo để “ràng buộc cho chắc”. Dùng định danh tham chiếu được kiểm soát.

### 8.5. Ngữ cảnh còn mới nhưng thiết bị có vấn đề

Giả sử sự kiện xác thực mới một phút tuổi, nhưng nguồn bảo mật xác nhận thiết bị bị điều khiển trái phép.

Authentication context vẫn mô tả đúng sự kiện đã xảy ra. Tuy nhiên, bằng chứng đó không xóa điều kiện rủi ro hiện tại. Cần chặn hoặc xử lý theo chính sách, đánh giá phiên và grant liên quan.

## 9. Truyền và cache ngữ cảnh giữa các thành phần

Một hệ thống PAM có thể tách giao diện, dịch vụ chính sách, vault và session broker. Cần quyết định thành phần nào xác minh bằng chứng và thành phần nào được phép sử dụng kết quả.

### 9.1. Hợp đồng giữa bên phát và bên nhận

Hợp đồng cần xác định:

- Danh tính của thành phần phát.
- Ý nghĩa chính xác của từng trường.
- Bên nhận và mục đích sử dụng.
- Cách bảo vệ toàn vẹn, xác thực nguồn và thời hạn.
- Ràng buộc người dùng, phiên, yêu cầu hoặc hành động.
- Cách xử lý phản hồi trùng, dữ liệu thiếu và thay đổi chính sách.
- Cách thu hồi hoặc vô hiệu hóa đánh giá không còn được dùng.

Việc một dịch vụ nội bộ gọi qua kết nối được bảo vệ không cho phép dịch vụ đó tự khẳng định mọi thuộc tính người dùng. Nó chỉ nên phát những thông tin thuộc trách nhiệm và nguồn tin cậy được giao.

### 9.2. Cache bằng chứng và cache quyết định khác nhau

Có thể giữ sự kiện xác thực để dùng lại trong thời hạn cho phép. Nhưng một quyết định truy cập đã cache có thể chứa quyền, phê duyệt và tín hiệu rủi ro đã thay đổi.

Khóa cache quyết định cần bao phủ những chiều làm thay đổi kết quả, ví dụ chủ thể, phiên, tài sản, hành động, profile, phiên bản chính sách và trạng thái liên quan. Cần có thời hạn và cơ chế vô hiệu hóa phù hợp.

Không dùng cache `user_id -> trusted` cho mọi hành động. Cũng không lấy một đánh giá thiết bị cũ rồi gắn thời điểm hiện tại khi đọc cache.

Khi hệ thống phân tán có khoảng trễ, cần ghi rõ giới hạn thu hồi và điểm kiểm tra cuối tại nơi thực thi. Không tuyên bố thay đổi có hiệu lực tức thì nếu kiến trúc chưa bảo đảm điều đó.

### 9.3. Tác vụ bất đồng bộ

Nếu yêu cầu được đưa vào hàng đợi, tác vụ có thể chạy sau khi bằng chứng hết hạn hoặc quyền đã bị hủy. Phải quy định quyền thực thi của tác vụ, thời hạn và điều kiện cần kiểm tra lại.

Không chuyển một kết quả xác thực ngắn hạn thành khả năng chạy đặc quyền không giới hạn chỉ vì tác vụ đã được tạo.

Đối với workload tự động, cần một mô hình danh tính và xác thực riêng. Không giả lập ngữ cảnh MFA của con người bằng một cờ cố định hoặc giữ cookie của quản trị viên để dùng lâu dài.

## 10. Bằng chứng và bảo vệ thông tin

Một quyết định có thể được truy vết bằng chuỗi:

```text
Nguồn tin cậy + sự kiện xác thực
    -> Ánh xạ danh tính và profile
    -> Phiên PAM
    -> Yêu cầu tài sản/hành động
    -> Đánh giá quyền và rủi ro
    -> Quyết định
    -> Grant/phiên/thao tác thực tế
    -> Hết hạn hoặc thu hồi
```

Những dữ liệu nên cân nhắc lưu gồm:

- Mã sự kiện, nguồn, chủ thể và phiên liên quan.
- Thời điểm xác thực, kiểm tra, đánh giá và thực thi.
- Profile nguồn và profile chuẩn hóa cùng phiên bản ánh xạ.
- Chính sách, điều kiện quyết định và lý do.
- Tham chiếu phê duyệt, grant, tài sản và hành động.
- Trạng thái dữ liệu thiếu hoặc quá cũ khi có.
- Kết quả xác thực lại, từ chối, thu hồi và đối soát.

Không ghi token nguyên vẹn, cookie, OTP, mật khẩu, khóa riêng hoặc mã khôi phục vào log thông thường. Các thuộc tính thiết bị và hành vi cũng có thể nhạy cảm, cần thu thập theo mục đích và phân quyền.

Bằng chứng cần được bảo vệ khỏi sửa hoặc xóa trái phép. Khi sửa quy tắc ánh xạ, giữ được lịch sử để giải thích vì sao cùng một giá trị nguồn từng được diễn giải theo một profile khác.

Không sửa bản ghi cũ thành profile mới rồi dùng nó để chứng minh quyết định quá khứ. Nếu bổ sung chú thích hoặc kết quả điều tra, phải có dấu vết và liên kết tới dữ liệu gốc.

## 11. Kiểm chứng thiết kế

Thực hiện trong phạm vi và môi trường được phép.

| Phép thử | Kết quả mong đợi |
|---|---|
| Client tự gửi `mfa=true` hoặc thời gian xác thực mới | Không được dùng như bằng chứng tin cậy |
| Nội dung token giải mã được nhưng không hợp lệ | Không tạo ngữ cảnh đã xác minh |
| Token mới dựa trên xác thực cũ | Tuổi xác thực vẫn phản ánh sự kiện cũ |
| Thiếu thời điểm bắt buộc | Không tự thay bằng thời điểm nhận token |
| Profile nguồn chưa có ánh xạ | Không nâng thành profile đặc quyền mặc định |
| Cùng tên profile từ hai issuer khác nhau | Đánh giá theo từng quan hệ tin cậy |
| Ngữ cảnh của người A dùng cho phiên người B | Bị từ chối |
| Bằng chứng dành cho ứng dụng khác | Không được chấp nhận ngoài bên nhận |
| Thời điểm xác thực nằm bất hợp lý ở tương lai | Không tạo tuổi âm có lợi cho quyết định |
| Quyền hoặc phê duyệt đổi trong lúc xác thực lại | Kiểm tra cuối phản ánh trạng thái mới |
| Cache còn giữ quyết định sau khóa khẩn cấp | Cơ chế vô hiệu hóa hoặc kiểm tra lại hoạt động theo thiết kế |
| Một header nội bộ được gửi từ đường không tin cậy | Không thể giả mạo ngữ cảnh |
| Tác vụ hàng đợi chạy sau hạn cho phép | Không dùng ngữ cảnh cũ để cấp quyền trái chính sách |
| Xác thực mạnh nhưng thiết bị bị xác nhận xâm nhập | Điều kiện cấm hiện tại không bị bỏ qua |
| Thay phiên bản mapping | Có thể giải thích cả quyết định cũ và mới |
| Thành công ở lớp chính sách nhưng thất bại tại đích | Ghi đúng trạng thái thực thi, không coi quyền đã được dùng thành công |

Cần thử cả trường hợp hợp lệ và các biên thời gian. Giới hạn thực tế của giao thức, sản phẩm hoặc nguồn tín hiệu phải được ghi rõ thay vì che bằng một nhãn “trusted”.

## 12. Những sai lầm thường gặp

**Biến authentication context thành một cờ duy nhất.** Một giá trị “đã xác thực” làm mất nguồn, phương thức, thời gian và ràng buộc.

**Dùng thời gian token để chứng minh MFA mới.** Thời điểm phát hành không nhất thiết là thời điểm thực hiện yếu tố cần thiết.

**So sánh profile bằng con số hoặc tên.** Chỉ có ý nghĩa nếu các lớp đã được định nghĩa và ánh xạ trong đúng miền tin cậy.

**Tin claim trước khi xác minh bằng chứng.** Nội dung đọc được chưa phải nội dung được tin cậy.

**Gộp thiếu dữ liệu với đạt điều kiện.** Cần biểu diễn trạng thái chưa biết và áp dụng chính sách tương ứng.

**Làm mới tuổi dữ liệu khi đọc cache.** Độ mới phụ thuộc thời điểm nguồn đánh giá hoặc xác thực, không phải lần cuối ứng dụng đọc bản ghi.

**Dùng ngữ cảnh tốt để bỏ qua quyền.** Danh tính đáng tin vẫn cần đúng tài sản, phê duyệt và grant.

**Đánh đồng xác thực với ý định giao dịch.** Cần cơ chế ràng buộc hành động riêng nếu muốn chứng minh người dùng chấp thuận nội dung cụ thể.

## 13. Tự kiểm tra

1. Authentication context trả lời những câu hỏi nào mà một cờ “đã đăng nhập” không trả lời được?
2. Vì sao token phát mới không chứng minh lần xác thực mới?
3. Hai IdP cùng phát một giá trị `acr` có chắc tương đương không?
4. Nếu claim phương thức bị thiếu, có nên gán profile đặc quyền mặc định không?
5. Vì sao phải giữ nguồn và phiên bản mapping khi chuẩn hóa?
6. Bằng chứng xác thực còn mới có vượt qua việc grant đã bị hủy không?
7. Sự kiện xác thực khác đánh giá truy cập hiện tại như thế nào?
8. Cần làm gì khi một ngữ cảnh hợp lệ bị dùng cho tài sản hoặc phiên khác?

### Gợi ý trả lời

1. Ai xác thực, nguồn nào xác minh, phương thức và profile gì, khi nào, cho bên nhận và phiên nào.
2. Token có thể được phát lại hoặc làm mới từ một phiên cũ.
3. Không. Cần hiểu ngữ nghĩa và quan hệ tin cậy của từng nguồn.
4. Không. Cần thêm bằng chứng hoặc xử lý trạng thái chưa đáp ứng theo chính sách.
5. Để tái dựng cách hệ thống diễn giải dữ liệu tại thời điểm quyết định và phát hiện thay đổi ngoài ý định.
6. Không. Xác thực không thay thế cấp phép và phê duyệt.
7. Sự kiện ghi nhận điều đã xảy ra; đánh giá kết hợp nó với hành động và điều kiện hiện tại.
8. Kiểm tra ràng buộc, từ chối việc sử dụng sai phạm vi và tạo đánh giá mới nếu phù hợp.

## Kết luận

Authentication context giúp PAM sử dụng bằng chứng xác thực với đúng ý nghĩa: đúng nguồn, đúng chủ thể, đúng phương thức, đúng thời gian và đúng phiên. Việc chuẩn hóa cần giữ nguồn gốc và tránh biến dữ liệu chưa biết thành mức tin cậy cao.

Khi ngữ cảnh được kết hợp với quyền tối thiểu, JIT/JEA, phê duyệt, vault và kiểm soát phiên, mỗi quyết định truy cập đặc quyền có thể được giải thích bằng dữ liệu cụ thể. Bằng chứng xác thực là một phần của quyết định đó, còn quyền và rủi ro hiện tại vẫn phải được kiểm tra tại nơi thực thi.
