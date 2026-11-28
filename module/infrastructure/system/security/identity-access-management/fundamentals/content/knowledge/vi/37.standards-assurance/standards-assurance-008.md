# ASVS authentication — Kiểm chứng an toàn xác thực với OWASP ASVS

## 1. Từ chức năng đăng nhập đến yêu cầu có thể kiểm chứng

**OWASP Application Security Verification Standard (ASVS)** cung cấp các yêu cầu an toàn để thiết kế và kiểm chứng ứng dụng web, dịch vụ web. Với authentication, câu hỏi không chỉ là “đăng nhập đúng mật khẩu có thành công không?”, mà còn là “hệ thống ngăn đăng nhập trái phép và bảo vệ các đường thay đổi credential như thế nào?”. [OWASP ASVS — Overview](https://asvs.owasp.org/).

Bài này lấy **ASVS 5.0.0** làm mốc. Trong phiên bản này, chương **V6 — Authentication** là đầu mối cho các yêu cầu xác thực. Đây là bài hướng dẫn cách đọc và áp dụng một phần tiêu chuẩn, không phải bản chép đầy đủ hay kết luận một ứng dụng đã đáp ứng ASVS.

Ví dụ, ứng dụng quản lý hồ sơ có thể đăng nhập bằng mật khẩu, SSO và mã recovery. Nếu màn hình chính yêu cầu MFA nhưng một API cũ chỉ cần mật khẩu, việc kiểm tra màn hình chính sẽ bỏ sót đường truy cập yếu hơn. ASVS giúp biến những kỳ vọng như “mọi đường đăng nhập phải được kiểm soát” thành phạm vi, yêu cầu và bằng chứng cụ thể.

## 2. Ghi rõ phiên bản và hiểu mức L1–L3

Mã yêu cầu có thể thay đổi giữa các phiên bản. OWASP khuyến khích tham chiếu dạng có phiên bản, chẳng hạn `v5.0.0-6.3.1`, để người đọc biết chính xác yêu cầu được sử dụng. Không nối tùy ý ID của một bản cũ với nội dung bản mới. [OWASP ASVS — How To Reference Requirements](https://asvs.owasp.org/#how-to-reference-asvs-requirements).

ASVS dùng ba mức kiểm chứng tăng dần. Khi đánh giá L2, phải xét các yêu cầu L1 và L2 áp dụng; L3 tiếp tục bao gồm các mức dưới, với những điều kiện nghiêm ngặt hơn nếu yêu cầu nêu rõ. L1 không mặc định chỉ cần kiểm thử hộp đen: một số yêu cầu vẫn cần tài liệu hoặc khả năng xem xét bên trong. [ASVS 5.0.0 — Application Security Verification Levels](https://github.com/OWASP/ASVS/blob/v5.0.0/5.0/en/0x03-What-is-the-ASVS.md#application-security-verification-levels).

| Khái niệm | Điều cần phân biệt |
|---|---|
| ASVS L1, L2, L3 | Phạm vi yêu cầu an toàn ứng dụng cần kiểm chứng theo mức |
| NIST IAL | Bảo đảm về quá trình chứng minh danh tính |
| NIST AAL | Bảo đảm về quá trình xác thực |
| NIST FAL | Bảo đảm về federation |

Các hệ thống đánh giá này không có phép đổi một-một chỉ vì cùng dùng số 1, 2, 3. Không kết luận “đạt ASVS L2 nghĩa là mọi phiên đều đạt AAL2”. Cần xem tiêu chuẩn, phiên bản, phạm vi và bằng chứng của từng kết luận.

Trong hồ sơ dự án, nên tách mức mục tiêu khỏi kết quả thực tế. `targetLevel: L2` là mục tiêu; nó không chứng minh các yêu cầu đã pass. Nếu chỉ kiểm chứng chương authentication, báo cáo phải nêu đúng phạm vi đó thay vì công bố toàn ứng dụng đạt L2.

## 3. Kiểm kê toàn bộ đường xác thực

Trước khi tạo ca kiểm thử, lập bản đồ các cách người dùng có thể có hoặc lấy lại khả năng truy cập. Bảng sau là ví dụ kiểm kê của một ứng dụng giả định:

| Đường đi | Điểm vào cần xác định | Câu hỏi cần giải quyết |
|---|---|---|
| Đăng nhập mật khẩu | Web, mobile, API cùng chức năng | Có cùng policy và trạng thái MFA không? |
| SSO qua IdP | Điểm bắt đầu, callback, ánh xạ tài khoản | Subject nào được tạo phiên cục bộ? |
| Đăng ký và kích hoạt | Form tạo tài khoản, liên kết kích hoạt | Trạng thái chưa hoàn tất được phép làm gì? |
| Quên mật khẩu | Request reset và hoàn tất reset | Bằng chứng được gắn với ai, được dùng bao lâu? |
| Mất hoặc thay yếu tố MFA | Trang self-service, helpdesk | Ai được phép gắn yếu tố mới? |
| Ghi nhớ thiết bị | Cookie hoặc trạng thái phía máy chủ | Điều kiện nào cho phép giảm bước xác thực? |
| Đăng nhập dự phòng | API cũ, tài khoản local sau SSO | Có tạo đường vòng quanh kiểm soát chính không? |

Không chỉ tìm URL có chữ `login`. Một endpoint “kích hoạt tài khoản”, “xác nhận hỗ trợ” hoặc “liên kết tài khoản” cũng có thể tạo ra trạng thái đủ mạnh để truy cập chức năng.

Kết quả kiểm kê cần chỉ rõ chủ sở hữu kiểm soát. Nếu IdP thực hiện một phần, nhóm ứng dụng vẫn cần biết ứng dụng kiểm tra kết quả ra sao và làm gì khi thông tin cần thiết không có. Việc thuê dịch vụ xác thực không tự tạo bằng chứng cho cấu hình tích hợp của mình.

## 4. Đọc yêu cầu cùng level và điều kiện áp dụng

Một số điểm neo để bắt đầu đọc V6 trong **đúng bản 5.0.0**:

| ID | Mức bắt đầu | Trọng tâm tóm lược |
|---|---|---|
| `v5.0.0-6.1.1` | L1 | Tài liệu hóa phòng chống đoán mật khẩu và credential stuffing |
| `v5.0.0-6.3.3` | L2 | MFA; có điều kiện nghiêm ngặt hơn ở L3 |
| `v5.0.0-6.4.3` | L2 | Reset mật khẩu không vượt MFA đang bật |
| `v5.0.0-6.5.1` | L2 | Mã hoặc yêu cầu dùng một lần không được dùng thành công lại |
| `v5.0.0-6.8.1` | L2 | Không mạo danh qua IdP khác có cùng user identifier |

Yêu cầu `6.3.3` có nội dung riêng cho L3 và điều kiện khi nới lỏng. Không được chỉ đọc cột level rồi bỏ các mệnh đề ấy. Bảng là chỉ dẫn đọc chọn lọc, không phải toàn bộ checklist. [ASVS 5.0.0 — V6 Authentication](https://github.com/OWASP/ASVS/blob/v5.0.0/5.0/en/0x15-V6-Authentication.md).

Với mỗi yêu cầu, hãy ghi câu trả lời cho ba việc: có áp dụng không, kiểm soát nằm ở đâu và bằng chứng nào đủ để đánh giá. Một yêu cầu chưa được kiểm tra phải là “chưa kiểm tra”, không phải pass. Trạng thái không áp dụng cần có lý do phù hợp kiến trúc, không dùng để che phần chưa triển khai.

Ví dụ, ứng dụng chỉ dùng SSO có thể không tự quản lý mật khẩu người dùng cuối. Tuy nhiên, nếu vẫn có tài khoản local dự phòng, không thể loại toàn bộ đường mật khẩu khỏi phạm vi chỉ vì giao diện mặc định chuyển sang IdP.

## 5. Mật khẩu: kiểm tra cả trải nghiệm và xử lý phía máy chủ

Trong ASVS 5.0.0, `6.2.1` đặt mức tối thiểu 8 ký tự và khuyến nghị mạnh tối thiểu 15; `6.2.9` ở L2 yêu cầu cho phép mật khẩu dài ít nhất 64 ký tự. Phải phân biệt số tối thiểu bắt buộc, khuyến nghị và khả năng tiếp nhận mật khẩu dài. [ASVS 5.0.0 — V6.2 Password Security](https://github.com/OWASP/ASVS/blob/v5.0.0/5.0/en/0x15-V6-Authentication.md#v62-password-security).

Hướng dẫn Authentication của OWASP nhấn mạnh độ dài, việc chặn mật khẩu phổ biến hoặc đã lộ, hỗ trợ password manager, không cắt ngầm mật khẩu và tránh quy tắc thành phần ký tự áp đặt. Hướng dẫn triển khai này bổ trợ cho việc đọc tiêu chuẩn, không tự thay đổi bản ASVS đã chọn. [OWASP Authentication Cheat Sheet — Password Strength Controls](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html#implement-proper-password-strength-controls).

Trong một bộ test minh họa, có thể tạo các cặp đầu vào giống nhau ở phần đầu nhưng khác phần cuối. Nếu cả hai đều đăng nhập được vào cùng tài khoản sau khi chỉ một giá trị được đặt làm mật khẩu, cần điều tra việc cắt chuỗi hoặc biến đổi dữ liệu. Không ghi các giá trị mật khẩu thật vào báo cáo để chứng minh kết quả.

Cũng cần so sánh đăng ký, đổi mật khẩu và reset. Nếu cùng một mật khẩu bị từ chối lúc đăng ký nhưng lại được chấp nhận qua reset, có thể ứng dụng đang dùng nhiều validator không đồng nhất. Quy tắc chỉ tồn tại trong JavaScript của một form cũng không kiểm soát được request trực tiếp.

Việc lưu trữ cần được xem xét riêng. OWASP hướng dẫn dùng thuật toán được thiết kế cho password hashing và cấu hình chi phí phù hợp; một phép băm nhanh đơn lẻ không cung cấp cùng khả năng chống đoán ngoại tuyến. [OWASP Password Storage Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html).

Ví dụ, một ca UI pass không thể chứng minh database không lưu plaintext. Cần bằng chứng phù hợp như cấu hình encoder, đường ghi credential và dạng bản ghi thử nghiệm đã loại bỏ bí mật. Không yêu cầu người kiểm chứng thu thập mật khẩu của người dùng thật.

## 6. Chống tự động hóa phải có hành vi được xác định

Credential stuffing dùng cặp credential đã bị lộ; password spraying thử một số mật khẩu trên nhiều tài khoản. Các đợt tấn công phân tán có thể làm giới hạn chỉ theo IP kém hiệu quả. OWASP khuyến nghị phối hợp nhiều tín hiệu và biện pháp phù hợp bối cảnh. [OWASP Credential Stuffing Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Credential_Stuffing_Prevention_Cheat_Sheet.html).

Một policy minh họa cần giải thích cách đếm lỗi, phạm vi bộ đếm, hành vi khi vượt ngưỡng, điều kiện phục hồi và ảnh hưởng đối với người dùng hợp lệ. Không có một con số retry trong ví dụ nào tự trở thành ngưỡng bắt buộc cho mọi ứng dụng.

Bộ test có thể kiểm tra các tình huống sau bằng tài khoản và dữ liệu thử nghiệm:

| Tình huống | Điều cần quan sát |
|---|---|
| Nhiều lần sai trên một tài khoản | Kiểm soát hoạt động theo policy đã công bố |
| Nhiều tài khoản từ một nguồn | Không chỉ bảo vệ một user đơn lẻ |
| Một tài khoản được thử qua nhiều nguồn | Bộ đếm và phản ứng không bị vượt dễ dàng |
| Chuyển từ web sang API khác | Không khởi động lại toàn bộ kiểm soát ngoài thiết kế |
| Kẻ khác cố làm tài khoản bị khóa | Không tạo cơ chế từ chối dịch vụ tùy tiện |
| Người dùng hợp lệ quay lại | Có đường phục hồi rõ ràng và được kiểm soát |

Thông báo chung cũng cần được kiểm tra cùng status code và thời gian phản hồi; chỉ đổi chữ trên giao diện chưa giải quyết mọi khả năng dò tài khoản. Khi đo thời gian, cần nhiều mẫu trong điều kiện kiểm soát, không kết luận từ một request chậm hơn tình cờ.

## 7. MFA là trạng thái bảo mật, không chỉ là một màn hình OTP

MFA cần các loại yếu tố khác nhau; mật khẩu cộng PIN vẫn thuộc cùng nhóm “điều người dùng biết”. OWASP cũng lưu ý vòng đời yếu tố, thay thế yếu tố và recovery có thể trở thành đường vòng. [OWASP Multifactor Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Multifactor_Authentication_Cheat_Sheet.html).

Với một ứng dụng yêu cầu mật khẩu và TOTP, có thể mô hình hóa trạng thái minh họa như sau:

```text
Chưa xác thực
  → Mật khẩu hợp lệ
  → Giao dịch chờ hoàn tất MFA, có quyền giới hạn
  → MFA hợp lệ và giao dịch còn hiệu lực
  → Phiên đã hoàn tất yêu cầu xác thực
```

Mô hình này không phải schema của ASVS. Nó giúp làm rõ tại sao “đã qua mật khẩu” không được coi là đủ quyền dùng các API yêu cầu toàn bộ MFA.

Test cần thử gọi chức năng được bảo vệ ngay sau bước mật khẩu, dùng giao dịch MFA của tài khoản khác và gửi lại một mã đã được sử dụng thành công. Với xử lý đồng thời, phải quan sát kết quả commit hoặc trạng thái phía máy chủ; chạy hai request tuần tự chưa kiểm tra được mọi tranh chấp.

TOTP có seed dài hạn để tính mã; không nên nhầm seed với mã dùng một lần rồi áp dụng cơ chế lưu trữ giống hệt. Trong triển khai, việc bảo vệ seed và chống dùng lại kết quả xác thực là những vấn đề khác nhau. [OWASP MFA Cheat Sheet — TOTP Seeds and Validation Window](https://cheatsheetseries.owasp.org/cheatsheets/Multifactor_Authentication_Cheat_Sheet.html#totp-seeds-and-validation-window).

## 8. Reset mật khẩu và recovery phải giữ đúng phạm vi

OWASP hướng dẫn token reset được sinh an toàn, gắn với người dùng, có thời hạn, được bảo vệ khi lưu và bị vô hiệu sau sử dụng. Quy trình request cũng cần hạn chế dò tài khoản và lạm dụng gửi thông báo. [OWASP Forgot Password Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html).

Trong ứng dụng giả định, một token cho phép An đặt mật khẩu mới không được dùng để đổi tài khoản đích thành Bình. Nó cũng không nên tự cho phép thay email, gắn authenticator mới hoặc xóa yêu cầu MFA nếu những việc đó nằm ngoài quy trình đã thiết kế.

Ba ca kiểm thử nên được tách rõ:

1. **Đổi mật khẩu khi còn truy cập:** xác minh điều kiện trước khi thay credential.
2. **Quên mật khẩu:** xác minh proof cho đúng mục đích và đúng tài khoản.
3. **Mất yếu tố MFA:** xác minh quy trình recovery và việc gắn lại yếu tố.

Việc ba ca đều có nút “Tiếp tục” không có nghĩa chúng được phép dùng chung một bằng chứng cho mọi hành động. Helpdesk cũng cần phạm vi quyền và audit; quyền khởi tạo hỗ trợ không tự là quyền chọn credential thay cho người dùng.

## 9. IdP, phiên và authorization là các ranh giới tiếp theo

Một ví dụ nhiều IdP có thể gồm `IdP-A/sub-42` và `IdP-B/sub-42`. Đây không tự là cùng một người. Ứng dụng cần phân biệt namespace nguồn khi ánh xạ tài khoản; nếu có liên kết chủ động, phải có quy trình chứng minh quyền liên kết, không chỉ so sánh một chuỗi ID giống nhau.

Khi một chức năng cần phương thức xác thực hoặc thời điểm xác thực cụ thể, phải có cơ sở từ thông tin tin cậy để đánh giá. Không diễn giải việc “đã redirect qua SSO” thành mọi mức xác thực mong muốn. Các thông tin như `acr`, `amr` hoặc `auth_time` cần được hiểu theo hợp đồng tích hợp; thiếu thông tin không phải bằng chứng đã đạt yêu cầu.

Session management có chương V7 riêng. Ví dụ, `v5.0.0-7.2.4` liên quan đến đổi session token sau xác thực, còn `v5.0.0-7.5.1` liên quan đến tái xác thực trước thay đổi thuộc tính nhạy cảm ảnh hưởng xác thực. Kiểm tra V6 không tự bao phủ đầy đủ session. [ASVS 5.0.0 — V7 Session Management](https://github.com/OWASP/ASVS/blob/v5.0.0/5.0/en/0x16-V7-Session-Management.md).

Trong một hệ thống dùng token tự chứa, xóa cookie trên trình duyệt không tự chứng minh backend đã từ chối token cũ. Tương tự, logout ở một ứng dụng không tự cho biết phiên IdP và các ứng dụng khác đã kết thúc. Bộ test cần nêu đúng artifact và thành phần được quan sát.

Cuối cùng, xác thực thành công vẫn không cho phép đọc tài nguyên tùy ý. Sau khi xác định subject, backend còn phải kiểm tra tenant, role và quyền trên hành động cụ thể. Không dùng kết quả kiểm chứng authentication làm kết luận thay cho authorization.

## 10. Biến yêu cầu thành hồ sơ kiểm chứng

Một hồ sơ nên nối được **yêu cầu → điểm kiểm soát → cách kiểm tra → bằng chứng → kết luận**. Ví dụ sau là định dạng tự thiết kế để minh họa, không phải schema chính thức của ASVS:

```yaml
standard: OWASP-ASVS
version: 5.0.0
targetLevel: L2
requirement: v5.0.0-6.4.3
scope:
  - local-password-reset
  - customer-accounts-with-totp
testCase: RESET-DOES-NOT-BYPASS-MFA-01
preconditions:
  account: synthetic-customer-a
  mfaState: ENABLED
procedure:
  - Reset mật khẩu bằng proof hợp lệ của tài khoản thử
  - Bắt đầu đăng nhập với mật khẩu mới
  - Thử truy cập chức năng yêu cầu hoàn tất MFA
expected:
  fullAccessBeforeMfa: false
  existingMfaRequirementPreserved: true
evidence:
  - sanitized-request-response
  - server-side-authentication-state
result: NOT_RUN
```

`NOT_RUN` được dùng vì đây là đặc tả, chưa phải kết quả chạy. Chỉ đổi sang pass khi quan sát thực tế phù hợp. Một ảnh chụp trang OTP không đủ: cần biết API được bảo vệ có thật sự từ chối trạng thái chưa hoàn tất hay không.

Khi báo cáo fail, mô tả trigger cụ thể, hành vi quan sát, tác động và yêu cầu liên quan. Chẳng hạn: “Sau reset, request tới API hồ sơ thành công bằng phiên chưa hoàn tất TOTP” dễ tái hiện và sửa hơn “MFA chưa an toàn”.

Bằng chứng cần loại mật khẩu, seed, mã recovery, session token và thông tin cá nhân không cần thiết. Nếu không đủ quyền xem cấu hình hoặc đường xử lý để kết luận, hãy ghi giới hạn kiểm chứng thay vì suy diễn pass.

## 11. Tự kiểm tra cách hiểu

**Ứng dụng có trang login và MFA thì đã đáp ứng chương authentication chưa?**

Chưa thể kết luận. Cần kiểm tra các đường đi, vòng đời credential và từng yêu cầu áp dụng.

**Đạt một số yêu cầu V6 ở L2 có nghĩa toàn ứng dụng đạt ASVS L2 không?**

Không. Báo cáo phải nêu đúng phạm vi và tình trạng các yêu cầu còn lại.

**Không có mật khẩu local thì bỏ mọi kiểm tra xác thực được không?**

Không. Cần kiểm tra IdP, ánh xạ subject, kết quả xác thực và các đường dự phòng thực tế.

**Một test mock luôn trả kết quả MFA thành công chứng minh được điều gì?**

Nó có thể kiểm tra logic sau một kết quả đã cho; không chứng minh validator, yếu tố xác thực hoặc toàn bộ luồng MFA hoạt động an toàn.

**Khi nâng phiên bản ASVS nên làm gì trước?**

Cố định bản mới, đối chiếu thay đổi và cập nhật mapping, ca kiểm thử cùng bằng chứng. Không chỉ thay chuỗi phiên bản trong báo cáo cũ.

