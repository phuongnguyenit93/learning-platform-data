# Các mức bảo đảm khi xác minh tăng cường (Step up assurance levels)

## 1. Bài toán: đủ bằng chứng để làm việc gì?

Trong chương **Step Up Verification** của module khôi phục tài khoản, step-up là việc yêu cầu thêm bằng chứng khi bằng chứng hiện tại chưa đáp ứng điều kiện của một thao tác. Mục tiêu không phải tăng số màn hình xác minh, mà là ngăn người đang nắm một phần quyền truy cập biến quyền đó thành quyền kiểm soát toàn bộ tài khoản.

Ví dụ, Lan mất điện thoại chứa ứng dụng TOTP nhưng vẫn nhớ mật khẩu. Người nhập đúng mật khẩu có thể là Lan, cũng có thể là người đã lấy được mật khẩu qua phishing. Nếu hệ thống cho tắt MFA ngay sau khi nhập mật khẩu, cơ chế recovery đã mở đường bỏ qua yếu tố bị mất. Nếu hệ thống luôn yêu cầu mã TOTP trên điện thoại đã mất, người dùng hợp lệ lại không thể hoàn tất luồng.

Thiết kế cần trả lời đồng thời ba câu hỏi:

1. Bằng chứng hiện có xác nhận điều gì và có thể bị chiếm đoạt bằng cách nào?
2. Thao tác sắp thực hiện cần mức bảo đảm nào?
3. Nếu không thể cung cấp bằng chứng thông thường, nhánh khôi phục nào vẫn đáp ứng chính sách?

Sau bài này, người học có thể phân biệt mức bảo đảm xác thực với mức cho phép khôi phục, lập điều kiện step-up theo thao tác, và thiết kế việc chuyển từ phiên recovery sang phiên sử dụng bình thường.

## 2. Tách bốn khái niệm thường bị gộp chung

| Khái niệm | Câu hỏi cần trả lời | Ví dụ trong recovery |
| --- | --- | --- |
| Authentication assurance — bảo đảm xác thực | Lần xác thực này chứng minh khả năng kiểm soát authenticator đến đâu? | Một passkey đã liên kết được dùng để ký challenge và xác minh người dùng |
| Identity proofing — kiểm chứng danh tính | Danh tính được khai báo đã được đối chiếu theo quy trình nào? | Đối chiếu lại hồ sơ đã kiểm chứng từ khi mở tài khoản |
| Risk — rủi ro của yêu cầu | Có dấu hiệu giả mạo, gian lận hoặc chiếm đoạt không? | Đổi số điện thoại rồi lập tức yêu cầu thay MFA từ thiết bị mới |
| Authorization — quyền thực hiện thao tác | Chủ thể này có được làm thao tác cụ thể trong trạng thái hiện tại không? | Được thêm yếu tố thay thế nhưng chưa được xuất dữ liệu hay chuyển tiền |

Các cột có thể hỗ trợ nhau nhưng không thay thế nhau. Một phiên có xác thực mạnh vẫn có thể bị giới hạn vì tài khoản đang điều tra chiếm đoạt. Một hồ sơ đã kiểm chứng danh tính cũng không chứng minh người đang cầm cookie là chủ tài khoản.

**Tín hiệu ngữ cảnh không phải yếu tố xác thực.** IP quen thuộc, cookie nhận diện thiết bị và lịch sử truy cập có thể ảnh hưởng lựa chọn nhánh xử lý; chúng không tự chứng minh người gửi yêu cầu đang kiểm soát một authenticator.

Một cách biểu diễn quyết định của ứng dụng là:

~~~text
CHO_PHÉP(thao_tác) =
    đúng_tài_khoản_và_phạm_vi
    AND bằng_chứng_được_chấp_nhận
    AND bằng_chứng_còn_mới
    AND nguồn_gốc_liên_kết_đủ_tin_cậy
    AND trạng_thái_recovery_cho_phép
    AND ràng_buộc_rủi_ro_được_đáp_ứng
~~~

Đây là mô hình thiết kế của bài học, không phải công thức chấm điểm hay định nghĩa AAL của một tiêu chuẩn.

## 3. Đọc đúng AAL1, AAL2 và AAL3

NIST SP 800-63B-4 phân biệt các mức AAL như sau:

| Mức | Ý nghĩa rút gọn |
| --- | --- |
| AAL1 | Bảo đảm cơ bản về quyền kiểm soát authenticator; có thể dùng một yếu tố |
| AAL2 | Hai loại yếu tố khác nhau, bằng giao thức đáp ứng yêu cầu của mức này |
| AAL3 | Xác thực mật mã chống phishing, khóa riêng không xuất được, kết hợp yếu tố kích hoạt hoặc mật khẩu |

Đây chỉ là phần định hướng; đánh giá phù hợp cần đối chiếu đầy đủ yêu cầu đối với authenticator, verifier và phiên. AAL2 phải có lựa chọn chống phishing; không phải mọi cách xác thực AAL2 đều chống phishing. Tín hiệu gian lận không thay đổi AAL. Xem [NIST: Authentication Assurance Levels](https://pages.nist.gov/800-63-4/sp800-63b/aal/).

Không suy ra AAL từ tên giao diện. Nút “xác minh nâng cao”, ba lần nhập OTP hoặc nhãn “thiết bị an toàn” đều không đủ để kết luận một mức cụ thể. Nếu sản phẩm chưa đánh giá đầy đủ, nên ghi chính xác đặc tính đã kiểm chứng, chẳng hạn “passkey có user verification”, thay vì tự gắn nhãn AAL3.

Trong policy của bài này, khi dùng passkey làm bằng chứng MFA, backend phải kiểm tra user verification; thao tác chạm xác nhận hiện diện không tự bổ sung yếu tố thứ hai. Việc dùng PIN hoặc sinh trắc học tại authenticator không có nghĩa backend cần thu thập PIN hay mẫu sinh trắc học đó. Tham khảo [OWASP: Passkeys trong MFA](https://cheatsheetseries.owasp.org/cheatsheets/Multifactor_Authentication_Cheat_Sheet.html#passkeys).

## 4. Điều kiện recovery không phải AAL của lần đăng nhập

Có hai con đường cần phân biệt:

- **Còn authenticator đáp ứng yêu cầu:** thực hiện xác thực hoặc tái xác thực bằng phương tiện đó để cấp quyền cho thao tác.
- **Đã mất phương tiện cần thiết:** áp dụng chính sách recovery đã được thiết kế trước để quyết định có cho liên kết authenticator thay thế hay không.

Theo NIST, khôi phục tài khoản có khả năng xác thực tối đa AAL2 cần một trong ba phương án: hai recovery code thuộc hai phương thức khác nhau; một recovery code kết hợp một authenticator đơn yếu tố đã liên kết; hoặc kiểm chứng lại danh tính nếu tài khoản đã được kiểm chứng trước đó. Hai mã trong cùng một bộ mã lưu sẵn không phải hai phương thức khác nhau. Tài khoản chưa kiểm chứng danh tính không có nhánh kiểm chứng lại danh tính để thay thế. Xem [NIST: Account Recovery](https://pages.nist.gov/800-63-4/sp800-63b/events/#account-recovery).

Một ứng dụng có thể xây chính sách riêng sau phân tích rủi ro, nhưng phải mô tả chính sách đó đúng bản chất. Không gọi mọi bước gửi email là “đạt AAL2”, và không tuyên bố tuân thủ NIST chỉ vì có áp dụng một phần ví dụ trên.

Điểm quan trọng trong luồng triển khai:

~~~text
Bằng chứng recovery được chấp nhận
    → quyền giới hạn để liên kết yếu tố thay thế
    → xác thực bằng yếu tố đã liên kết theo yêu cầu
    → đánh giá các giới hạn còn hiệu lực
    → cấp phiên và quyền tương ứng
~~~

Liên kết thành công một khóa mới chỉ chứng minh người thực hiện đang kiểm soát khóa mới. Tính hợp lệ của việc gắn khóa đó vào tài khoản vẫn phụ thuộc vào quyết định recovery trước đó.

## 5. Xây hồ sơ yêu cầu theo từng thao tác

Các tên dưới đây là **hồ sơ policy nội bộ dùng để minh họa**, không phải các mức NIST mới và không ánh xạ một-một sang AAL1–AAL3.

| Hồ sơ | Khi nào dùng | Điều kiện chính | Quyền có thể cấp |
| --- | --- | --- | --- |
| RECOVERY_START | Tiếp nhận yêu cầu | Kiểm soát lưu lượng và phản hồi không lộ tài khoản | Khởi tạo giao dịch, xem hướng dẫn chung |
| RECOVERY_EVIDENCE | Tiếp nhận bằng chứng | Bằng chứng gắn đúng giao dịch, đúng tài khoản, còn hạn | Bổ sung bằng chứng hoặc xem tiến độ giới hạn |
| AUTHENTICATOR_REBIND | Thay yếu tố bị mất | Một tổ hợp recovery được policy chấp nhận hoặc tái xác thực bằng yếu tố còn dùng được | Liên kết đúng loại yếu tố được duyệt |
| RECOVERY_EXIT | Rời trạng thái khôi phục | Đã hoàn tất recovery, xác thực phù hợp, xử lý thu hồi và các điều kiện còn lại | Cấp phiên sử dụng với quyền được cho phép |
| SENSITIVE_ACTION | Thực hiện tác vụ nhạy cảm sau recovery | Bằng chứng mới đáp ứng yêu cầu riêng; không còn hạn chế liên quan | Thực hiện đúng tác vụ đã yêu cầu |

Không so sánh các tên này bằng phép lớn hơn hoặc nhỏ hơn. Một grant cho AUTHENTICATOR_REBIND không bao hàm quyền SENSITIVE_ACTION. Người được phép đăng ký lại MFA chưa đương nhiên được đổi email liên hệ, xuất dữ liệu hoặc tạo API key.

### 5.1. Ma trận thao tác minh họa

| Thao tác | Bằng chứng hoặc điều kiện cần xem xét | Điều hệ thống phải tránh |
| --- | --- | --- |
| Gửi yêu cầu quên mật khẩu | Chống gửi hàng loạt, phản hồi chung | Khóa tài khoản chỉ vì có người gửi yêu cầu |
| Đặt mật khẩu mới | Token reset hợp lệ, chính sách của tài khoản, MFA nếu còn áp dụng | Cho rằng đổi mật khẩu đồng thời cho phép bỏ MFA |
| Thay TOTP bị mất | Nhánh recovery đủ điều kiện hoặc authenticator dự phòng phù hợp | Dùng riêng mật khẩu làm quyền xóa TOTP |
| Thêm passkey thay thế | Quyền liên kết đã được cấp, xác minh đăng ký, phạm vi tài khoản | Dùng passkey vừa thêm để biện minh ngược cho chính lần recovery đó |
| Đổi email hoặc số recovery | Quyền riêng cho việc đổi kênh, xem lịch sử thay đổi và rủi ro | Cho thay kênh rồi lập tức dùng chính kênh đó để chứng minh quyền sở hữu cũ |
| Xuất dữ liệu hoặc đổi quyền quản trị | Step-up mới theo mức tác động và vai trò | Tái sử dụng grant thay MFA cho thao tác khác |

Đây là ma trận của ứng dụng giả định. Sản phẩm thực tế phải ghi rõ các tổ hợp được chấp nhận thay cho những cụm chung chung như “xác minh thêm”.

### 5.2. Phân biệt yêu cầu tối thiểu và xử lý rủi ro

Policy có thể yêu cầu một bằng chứng nền tảng cho thao tác và thêm điều kiện khi xuất hiện tín hiệu đáng ngờ. Ví dụ:

~~~text
Yêu cầu nền tảng: nhánh recovery đã được phê duyệt cho việc thay MFA.
Thiết bị mới: yêu cầu thêm bước kiểm tra hoặc chuyển xử lý có kiểm soát.
Kênh recovery vừa đổi: không dùng kênh đó làm bằng chứng lịch sử độc lập.
Không có dấu hiệu bất thường: vẫn phải đáp ứng yêu cầu nền tảng.
~~~

Không dùng điểm “rủi ro thấp” để bù cho bằng chứng bắt buộc còn thiếu. Ngược lại, tín hiệu rủi ro cao có thể dẫn đến rà soát thay vì tự động tăng số OTP, vì thêm OTP trên cùng kênh đang bị chiếm đoạt không giải quyết nguyên nhân.

## 6. Đánh giá chất lượng của bằng chứng

Một bộ kiểm tra không nên chỉ lưu số lần xác minh thành công. Mỗi bằng chứng cần có ý nghĩa cụ thể.

| Thuộc tính | Cần biết điều gì? | Ví dụ sai khi bỏ qua |
| --- | --- | --- |
| Loại bằng chứng | Mật khẩu, assertion của passkey, recovery code hay quyết định kiểm chứng danh tính? | Gọi mọi kết quả là “OTP thành công” |
| Nguồn gốc liên kết | Phương tiện đã được liên kết từ trước hay mới thêm trong recovery? | Kẻ tấn công tạo yếu tố mới rồi dùng làm bằng chứng cũ |
| Phạm vi | Thuộc tài khoản, tenant, giao dịch và thao tác nào? | Dùng bằng chứng của giao dịch A cho giao dịch B |
| Độ mới | Được xác minh lúc nào và còn phù hợp với yêu cầu hiện tại không? | Phiên còn sống nhưng lần xác thực mạnh đã quá cũ |
| Khả năng dùng lại | Một lần, nhiều lần hay chỉ hợp lệ cho một challenge? | Replay một mã để xin nhiều grant |
| Miền phụ thuộc | Các bằng chứng có cùng phụ thuộc vào một hộp thư, điện thoại hoặc kho đồng bộ không? | Hai kênh nhìn khác nhau nhưng cùng mất khi một tài khoản đám mây bị chiếm |
| Trạng thái thu hồi | Có bị báo mất, thay thế hoặc vô hiệu hóa sau khi xác minh không? | Dùng bằng chứng đã bị thu hồi trước lúc commit |

**Độc lập loại yếu tố** và **độc lập điểm bị chiếm đoạt** là hai phép kiểm tra khác nhau. Hai bước cùng dựa vào hộp thư không tạo ra hai loại yếu tố chỉ vì chúng có hai mã riêng. Ngược lại, ngay cả một tổ hợp có các loại yếu tố khác nhau vẫn cần phân tích khả năng chúng cùng bị mất hoặc cùng bị đánh cắp.

Ví dụ, mật khẩu vừa được đặt lại qua email và một mã khác gửi đến chính hộp thư ấy có chung nguồn cấp quyền trong giao dịch. Policy không được coi sự hiện diện của hai ô nhập là bằng chứng độc lập.

### 6.1. Không dùng chờ đợi để thay bằng chứng

Thời gian chờ có thể tạo cơ hội phát hiện và phản đối một thay đổi. Nó không chứng minh người chờ là chủ tài khoản. Trong mô hình này, một yêu cầu thiếu bằng chứng vẫn thiếu bằng chứng sau khi chờ đủ thời gian.

Khi áp dụng thời gian chờ, phải xác định rõ điều kiện bắt đầu, sự kiện hủy, quyền bị giới hạn, và cách xử lý khi người dùng báo không thực hiện yêu cầu. Một bộ đếm trên trình duyệt không đủ; trạng thái phải do backend quản lý.

## 7. Thiết kế giao dịch recovery và quyền step-up

Trong mô hình sau, backend quản lý ba đối tượng riêng:

- **Recovery transaction:** trạng thái của toàn bộ yêu cầu khôi phục.
- **Verified evidence:** kết quả kiểm chứng do verifier tin cậy ghi nhận.
- **Step-up grant:** quyền ngắn hạn để thực hiện một thao tác xác định.

Grant là đầu ra của quyết định policy, không phải bằng chứng đầu vào. Client không thể tự tạo grant bằng cách gửi số lượng yếu tố đã hoàn thành.

### 7.1. Bản ghi bằng chứng

Ví dụ dữ liệu dưới đây là kết quả do backend tạo sau khi verifier đã xác minh một assertion; các giá trị chỉ để minh họa:

~~~json
{
  "evidenceId": "ev-51",
  "tenantId": "tenant-a",
  "accountId": "account-42",
  "recoveryTransactionId": "rec-8",
  "kind": "EXISTING_PASSKEY_ASSERTION",
  "authenticatorId": "credential-7",
  "bindingOrigin": "PREEXISTING",
  "verifiedAt": "2026-11-23T02:00:00Z",
  "userVerification": true,
  "challengeId": "challenge-16",
  "verifier": "webauthn-service",
  "policyVersion": "recovery-v3"
}
~~~

Không cho trình duyệt tự khai báo các trường như userVerification, bindingOrigin hoặc verifiedAt rồi lưu chúng thành sự thật. Verifier phải xác minh kết quả giao thức và liên kết với challenge đã phát hành trước khi ghi nhận evidence.

Một authenticator được thêm ngay trước khi giao dịch bắt đầu cũng chưa chắc đủ tin cậy. Việc đánh giá nguồn gốc cần dùng lịch sử sự kiện, thời điểm nghi ngờ chiếm đoạt và chuỗi quyết định đã cho phép liên kết, thay vì chỉ kiểm tra “tạo trước giao dịch vài giây”.

### 7.2. Bản ghi grant

Grant cho phép thay một yếu tố có thể bao gồm:

~~~json
{
  "grantId": "grant-19",
  "tenantId": "tenant-a",
  "accountId": "account-42",
  "recoveryTransactionId": "rec-8",
  "recoverySessionBinding": "binding-12",
  "action": "BIND_REPLACEMENT_AUTHENTICATOR",
  "parametersDigest": "digest-of-immutable-prepared-operation",
  "evidenceIds": ["ev-51"],
  "policyVersion": "recovery-v3",
  "securityVersion": 17,
  "issuedAt": "2026-11-23T02:00:05Z",
  "expiresAt": "2026-11-23T02:03:05Z",
  "state": "ISSUED"
}
~~~

Bản ghi này được giữ ở backend. Trình duyệt chỉ nhận một mã tham chiếu ngẫu nhiên có đủ entropy, được bảo vệ như một bí mật nếu ai có mã cũng có thể gửi yêu cầu sử dụng. Khi lưu mã bí mật, có thể lưu giá trị băm phù hợp thay cho nguyên văn.

parametersDigest được backend tính trên biểu diễn chuẩn của thao tác đã chuẩn bị, chẳng hạn loại yếu tố, credential đã xác minh và yếu tố cũ cần thay. Không chấp nhận việc client gửi một digest tùy ý rồi coi đó là ràng buộc. Với dữ liệu có ít khả năng lựa chọn như số điện thoại, một digest cũng không tự tạo bảo mật về tính bí mật; không nên đưa dữ liệu đó vào token công khai.

Thời hạn ba phút trong ví dụ là lựa chọn giả định. Cần cấu hình riêng thời hạn token recovery, challenge, evidence, grant và phiên; mỗi loại có mục đích khác nhau.

### 7.3. Độ mới không được gia hạn bằng thao tác refresh

Giả sử policy giả định yêu cầu bằng chứng không quá năm phút để cấp quyền thay MFA:

- Người dùng xác thực lúc 09:00.
- Access token được refresh lúc 09:04.
- Đến 09:07, ứng dụng không được coi lần refresh là một lần xác thực mới lúc 09:04.

Cần giữ thời điểm xác thực thực tế và thời điểm cấp token riêng biệt. Khi policy yêu cầu nhiều bằng chứng, phải đánh giá độ mới của từng bằng chứng có liên quan; một bằng chứng mới không tự làm mới các bằng chứng khác.

Nếu grant vẫn chưa hết hạn nhưng yếu tố nguồn đã bị thu hồi hoặc tài khoản bị đánh dấu compromise, grant phải bị từ chối theo trạng thái mới.

## 8. Luồng chuyển trạng thái có kiểm soát

~~~mermaid
flowchart TD
    A["Khởi tạo recovery"] --> B["Phiên recovery giới hạn"]
    B --> C["Thu thập bằng chứng đã xác minh"]
    C --> D{"Đáp ứng policy cho thao tác?"}
    D -->|"Chưa đủ, còn phương án"| C
    D -->|"Không còn phương án tự phục vụ"| E["Xử lý có kiểm soát hoặc dừng"]
    E -->|"Có quyết định và bằng chứng phù hợp"| C
    D -->|"Đủ"| F["Cấp grant cho đúng thao tác"]
    F --> G{"Grant và trạng thái vẫn hợp lệ?"}
    G -->|"Không"| C
    G -->|"Có"| H["Tiêu thụ grant và commit thay đổi"]
    H --> I["Thu hồi yếu tố cũ và xử lý session"]
    I --> J["Xác thực bằng phương tiện đã liên kết"]
    J --> K{"Đủ điều kiện rời recovery?"}
    K -->|"Chưa"| L["Giữ các giới hạn còn hiệu lực"]
    K -->|"Đủ"| M["Cấp phiên theo quyền được duyệt"]
~~~

Ngoài các nhánh chính, giao dịch cần trạng thái hết hạn, hủy hoặc bị từ chối. Những trạng thái kết thúc đó không được tiếp tục nhận evidence hay sử dụng grant còn sót lại.

Nếu người dùng không còn phương án tự phục vụ, “xử lý có kiểm soát” phải là một quy trình có tiêu chí và thẩm quyền cụ thể. Nhân viên hỗ trợ không nên có nút bỏ qua mọi điều kiện chỉ vì người gọi kể đúng vài thông tin trong hồ sơ.

Nếu hệ thống chưa từng kiểm chứng danh tính pháp lý và tài khoản không có liên kết đáng tin với danh tính đó, một ảnh giấy tờ mới gửi chưa chứng minh giấy tờ thuộc về chủ tài khoản. Cần một phương án được thiết kế cho chính loại tài khoản này; có trường hợp không thể khôi phục an toàn với dữ liệu hiện có.

## 9. Cấp quyền và thực thi phải cùng bảo vệ thao tác

Một lỗi phổ biến là kiểm tra policy khi hiển thị form, nhưng endpoint commit chỉ kiểm tra người dùng đã đăng nhập. Mọi đường gọi đến thao tác nhạy cảm, bao gồm ứng dụng web, mobile, API cũ và công cụ hỗ trợ, cần có cùng điều kiện thực thi ở backend.

Mã giả theo phong cách Java dưới đây thể hiện ranh giới trách nhiệm. Các service, kiểu dữ liệu và hàm hash là hợp đồng minh họa, chưa phải ứng dụng hoàn chỉnh.

~~~java
public void bindReplacement(
        RecoveryPrincipal principal,
        BindReplacementCommand command) {

    transaction.required(() -> {
        // Khóa theo tenant/account để tuần tự hóa thay đổi bảo mật.
        var account = accounts.lock(
                principal.tenantId(), principal.accountId());

        var recovery = recoveries.lock(
                principal.recoveryTransactionId());

        // Mã grant là bí mật; repository tra bằng giá trị băm.
        var grant = grants.lockBySecretHash(
                hash(command.grantSecret()));

        var now = clock.instant();

        requireRecoveryPrincipalStillActive(principal);
        requireAccountAndTenantMatch(account, recovery, grant, principal);
        requireRecoveryOpen(recovery, now);
        requireGrantIssuedAndUnexpired(grant, now);
        requireSameRecoverySession(grant, principal);
        requireAction(grant, Action.BIND_REPLACEMENT_AUTHENTICATOR);
        requireSecurityVersion(grant, account.securityVersion());

        // Bản ghi đã xác minh, bất biến, chưa gắn vĩnh viễn vào tài khoản.
        var prepared = enrollments.lockPrepared(
                command.preparedEnrollmentId());

        requirePreparedEnrollmentOwnedBy(prepared, recovery);
        requirePreparedEnrollmentUnexpiredAndUnused(prepared, now);
        requireParametersMatch(grant, prepared.canonicalDigest());

        // Đọc evidence từ kho tin cậy, không lấy nhãn assurance từ request.
        var evidence = evidenceStore.lockBoundTo(
                grant.evidenceIds(), recovery.id(), account.id());

        var decision = policy.evaluateCurrent(
                account, recovery, prepared, evidence, risk.current(), now);

        requirePolicyCompatible(grant.policyVersion(), decision);
        requireAllowed(decision);

        evidenceStore.commitSingleUseEvidence(evidence, recovery.id(), now);
        grant.consume(now);
        authenticators.applyApprovedReplacement(account, prepared, decision);
        prepared.markUsed(now);
        account.incrementSecurityVersion();

        // Cùng transaction; các dịch vụ kiểm tra version khi nhận token.
        sessions.revokeAccordingTo(decision, account);
        recoveries.recordCommittedChange(recovery, grant, decision);
        outbox.appendSecurityNotification(account, recovery, decision);
    });
}
~~~

Các điểm cần giữ trong triển khai:

1. **Cùng một lần commit:** tiêu thụ grant, đánh dấu bản ghi đăng ký đã dùng và cập nhật authenticator phải cùng thành công hoặc cùng rollback.
2. **Chống sử dụng đồng thời:** khóa bản ghi hoặc cập nhật có điều kiện để hai request không cùng tiêu thụ grant. Các thao tác đổi bảo mật liên quan cần dùng quy tắc khóa nhất quán.
3. **Kiểm tra lại tại thời điểm thực thi:** thời hạn, thu hồi, securityVersion và policy có thể thay đổi từ lúc cấp grant đến lúc commit.
4. **Dữ liệu do backend quyết định:** accountId, tenantId, phạm vi quyền và đặc tính bằng chứng phải đến từ ngữ cảnh đã xác thực hoặc kho tin cậy.
5. **Thông báo qua outbox:** ghi sự kiện thông báo cùng transaction rồi gửi sau commit. Cần retry và theo dõi việc gửi, tránh vừa thay đổi tài khoản vừa mất dấu thông báo do lỗi mạng.

Trong ví dụ, commitSingleUseEvidence phải tiêu thụ đầu vào dùng một lần hoặc xác nhận reservation độc quyền đã được thiết lập cho đúng giao dịch; nó không được chấp nhận bằng chứng đã dùng ở giao dịch khác.

Chỉ đặt @Transactional không tự làm grant trở thành dùng một lần; cơ chế khóa hoặc điều kiện cập nhật vẫn cần được thiết kế. Nếu dữ liệu nằm ở nhiều dịch vụ, transaction trong ví dụ không tự bao phủ chúng; cần thiết kế riêng trạng thái trung gian, tính idempotent và cơ chế từ chối quyền cho đến khi các bước bắt buộc hoàn tất.

Một request thất bại trước commit không nên tiêu thụ mất grant nếu toàn bộ thay đổi đã rollback. Một request lặp lại sau commit không được thực hiện thay đổi lần thứ hai; có thể trả kết quả đã hoàn tất nếu việc trả kết quả vẫn được kiểm tra đúng chủ thể và phạm vi.

## 10. Session sau recovery: đã xác minh chưa có nghĩa có mọi quyền

Một cookie phiên đang hoạt động không tự chứng minh người gửi yêu cầu còn kiểm soát yếu tố gốc. OWASP khuyến nghị yêu cầu tái xác thực cho các thay đổi nhạy cảm và sau sự kiện rủi ro như khôi phục tài khoản. Xem [OWASP: Re-authentication After Risk Events](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html#re-authentication-after-risk-events).

Trong thiết kế minh họa này, phiên recovery chỉ có quyền truy cập các endpoint của giao dịch tương ứng. Khi người dùng chờ kiểm tra, phiên không được dùng để đọc dữ liệu cá nhân, tạo API key, cấp quyền cho ứng dụng khác hoặc xuất dữ liệu.

Sau khi một thay đổi bảo mật được chấp nhận:

- Vô hiệu hóa authenticator được xác định đã mất hoặc bị xâm phạm theo quyết định đã phê duyệt.
- Hủy các grant và challenge không còn phù hợp; đóng những giao dịch recovery cạnh tranh nếu policy yêu cầu.
- Xử lý session, refresh token và thiết bị ghi nhớ thuộc phạm vi phải thu hồi.
- Yêu cầu xác thực lại theo đường đăng nhập phù hợp trước khi cấp phiên sử dụng.
- Tiếp tục áp dụng các giới hạn còn hiệu lực đối với tác vụ nhạy cảm.

Khi chuyển sang trạng thái có quyền cao hơn, cần thay mã phiên và vô hiệu hóa mã cũ để giảm nguy cơ session fixation. Tham khảo [OWASP: Renew the Session ID After Any Privilege Level Change](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html#renew-the-session-id-after-any-privilege-level-change).

Với access token tự chứa, việc xóa cookie hoặc chỉ thu hồi refresh token không làm access token đã phát hành lập tức vô hiệu. Nếu thiết kế dùng securityVersion để chặn token cũ, mọi nơi chấp nhận token phải kiểm tra version và có chính sách cache đáp ứng thời gian thu hồi mong muốn. Nếu không có phép kiểm tra trạng thái đó, cần thừa nhận cửa sổ token cũ còn dùng được đến khi hết hạn.

Thời gian chờ và việc đăng nhập lại phục vụ các mục đích khác nhau. Kết thúc thời gian chờ không tự chứng minh danh tính; đăng nhập bằng yếu tố mới cũng không xóa lịch sử nguồn gốc của lần liên kết yếu tố đó.

## 11. Chọn nhánh khi mất từng loại phương tiện

### 11.1. Mất mật khẩu, còn passkey đã liên kết

Minh quên mật khẩu nhưng còn passkey hợp lệ. Policy có thể dùng xác thực bằng passkey đáp ứng yêu cầu để cấp quyền đặt mật khẩu mới.

Hệ thống vẫn kiểm tra passkey có thuộc đúng tài khoản, có bị thu hồi hay không, và kết quả xác minh có đúng đặc tính policy yêu cầu hay không. Quyền đặt mật khẩu mới không đồng thời cho phép đổi kênh recovery hoặc xóa mọi yếu tố còn lại.

### 11.2. Mất điện thoại TOTP, còn mật khẩu và mã recovery lưu trước

Lan cung cấp mật khẩu và một mã recovery đã phát hành trước đó. Nếu tổ hợp này đáp ứng policy đã chọn, hệ thống cấp grant để thay đúng TOTP bị mất.

Mã recovery được tiêu thụ an toàn, TOTP mới phải được xác minh trước khi hoàn tất liên kết, và TOTP cũ được xử lý theo quyết định thay thế. Một grant cho thay TOTP không được dùng để đổi email. Nếu phát hiện mật khẩu có thể đã bị lộ, phải xử lý dấu hiệu đó thay vì chỉ thêm yếu tố mới.

### 11.3. Mất mọi thiết bị, chỉ còn truy cập email

Một link email chứng minh quyền kiểm soát hộp thư theo cơ chế đã triển khai; nó chưa tự đáp ứng yêu cầu thay MFA của mọi tài khoản. Hệ thống cần tìm nhánh recovery đã được thiết kế cho tài khoản, chẳng hạn kết hợp bằng chứng khác đã đăng ký trước hoặc quy trình kiểm chứng lại phù hợp.

Nếu tổ hợp tối thiểu không thể hoàn thành, giao diện nên hướng dẫn phương án còn khả dụng và nêu rõ quyền đang bị giới hạn. Không tự hạ điều kiện chỉ vì người dùng không còn yếu tố mạnh.

### 11.4. Mất passkey nhưng còn bản đồng bộ trên thiết bị khác

Trước khi mở luồng thay toàn bộ yếu tố, có thể cho người dùng thử một passkey đã liên kết vẫn sử dụng được trên thiết bị khác. Backend phải kiểm chứng assertion bình thường, không coi câu trả lời “tôi đã đồng bộ” là bằng chứng.

Đồng thời, cần phân biệt mất thiết bị với nghi ngờ tài khoản đồng bộ bị chiếm. Trường hợp thứ hai đòi hỏi đánh giá các phương tiện cùng phụ thuộc vào tài khoản đồng bộ đó, thay vì mặc định chúng là các đường dự phòng độc lập.

### 11.5. Tài khoản đặc quyền

Trong một hệ thống quản trị giả định, thay authenticator của quản trị viên có thể cần một nhánh phê duyệt riêng và bằng chứng mạnh hơn so với tài khoản thông thường. Nếu áp dụng hai người phê duyệt, cần bảo đảm họ có tài khoản, phiên và vai trò độc lập theo policy.

Hai lần bấm của cùng một người hoặc hai nhân viên cùng dựa vào lời khai của người gọi không tạo ra hai nguồn bằng chứng độc lập. Hoàn tất phê duyệt cũng không được cấp quyền vượt quá vai trò của tài khoản.

## 12. Bảo vệ chính quá trình step-up

Một luồng có điều kiện xác minh tốt vẫn có thể bị lạm dụng ở bước gửi mã, thử mã hoặc hỗ trợ người dùng.

Đối với token recovery, cần dùng bộ sinh ngẫu nhiên an toàn, độ dài phù hợp, lưu an toàn, giới hạn thời gian và chỉ sử dụng một lần. Endpoint tiếp nhận yêu cầu cần tránh lộ tài khoản qua thông báo hoặc khác biệt thời gian dễ khai thác, đồng thời giới hạn gửi hàng loạt. Xem [OWASP: Forgot Password](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html).

Trong mô hình của bài, các kiểm soát được gắn vào từng đối tượng:

| Điểm kiểm soát | Cách áp dụng |
| --- | --- |
| Gửi challenge | Giới hạn theo tài khoản, kênh nhận, nguồn gửi và giao dịch; tránh làm phiền người dùng bằng mã liên tiếp |
| Thử bằng chứng | Giới hạn số lần thử và tổng ngân sách cho các lần resend, không cho reset bộ đếm bằng giao dịch mới |
| Dùng grant | Kiểm tra phiên recovery, thao tác, tài khoản, tham số và trạng thái dùng một lần |
| Chuyển sang hỗ trợ | Giữ tiêu chí bằng chứng và lịch sử quyết định khi đổi kênh xử lý |
| Chống yêu cầu ngoài ý muốn | Bảo vệ CSRF cho thao tác dùng cookie và xác nhận rõ thay đổi sắp commit |
| Ghi log | Ghi mã sự kiện, lý do quyết định và tham chiếu nội bộ; loại bỏ OTP, token bí mật, cookie và dữ liệu danh tính không cần thiết |

Cần cân bằng giới hạn thử với khả năng gây từ chối dịch vụ: không để người ngoài khóa vĩnh viễn tài khoản chỉ bằng cách gửi nhiều yêu cầu. Những quyết định hạn chế nên phân biệt chặn một giao dịch, một nguồn gửi và chặn toàn bộ tài khoản.

Khi thay yếu tố MFA, nên thông báo qua kênh đã thiết lập và coi đây là thay đổi rủi ro cao; không chỉ dựa vào phiên hiện tại để cho phép thay thế. Xem [OWASP: Changing MFA Factors](https://cheatsheetseries.owasp.org/cheatsheets/Multifactor_Authentication_Cheat_Sheet.html#changing-mfa-factors).

Thông báo cần có cách báo hoạt động không nhận ra qua một quy trình được bảo vệ. Nếu đưa vào email một link chỉ cần bấm là có thể thay hoặc khôi phục toàn bộ yếu tố, chính link phản hồi lại trở thành một đường cấp quyền mới cần được kiểm soát.

## 13. Các lỗi làm mức bảo đảm bị thổi phồng

| Sai lầm | Vì sao nguy hiểm | Thiết kế cần có |
| --- | --- | --- |
| assurance = số bước đã hoàn thành | Các bước có thể cùng một loại hoặc cùng một nguồn kiểm soát | Đánh giá loại, nguồn gốc và tổ hợp bằng chứng |
| Điểm rủi ro thấp thay cho MFA bắt buộc | Dữ liệu ngữ cảnh có thể bị bắt chước | Tách điều kiện bằng chứng khỏi điều kiện rủi ro |
| Passkey mới tự hợp thức hóa recovery cũ | Kẻ tấn công cũng có thể tạo một khóa mới của mình | Giữ nguồn gốc liên kết và quyết định recovery |
| Tự động coi mọi passkey là AAL3 | Nhãn sản phẩm không xác nhận toàn bộ đặc tính cần thiết | Đánh giá đúng giao thức, khóa, verifier và yêu cầu áp dụng |
| Grant không gắn thao tác hoặc tham số | Có thể đổi mục đích sau khi được duyệt | Ràng buộc nội dung đã chuẩn bị ở backend |
| Frontend giữ cờ stepUpComplete | Client có thể sửa hoặc gọi thẳng API | Quyết định và kiểm tra tại backend |
| Grant hết hạn chỉ ở phía trình duyệt | Client có thể gửi request trực tiếp | Backend kiểm tra thời gian tại commit |
| Refresh token cập nhật “lần xác thực mạnh” | Làm bằng chứng cũ trông như vừa được cung cấp | Lưu thời điểm xác minh thực tế riêng |
| Chờ đủ thời gian thì cấp toàn quyền | Người tấn công cũng chờ được | Duy trì điều kiện bằng chứng và ràng buộc quyền |
| Chỉ kiểm tra ở lúc phát grant | Không phát hiện thu hồi hoặc thay đổi policy sau đó | Đánh giá lại các trạng thái liên quan khi dùng grant |
| Chỉ xóa cookie sau recovery | Token đã bị đánh cắp có thể còn hiệu lực | Thu hồi ở phía chấp nhận session và token |

## 14. Ví dụ tổng hợp: thay MFA mà không mở rộng quyền

Giả sử một ứng dụng lưu tài liệu cho phép recovery bằng mật khẩu còn hợp lệ kết hợp mã recovery đã lưu từ trước. Đây là policy giả định để minh họa cách vận hành, không phải khẳng định ứng dụng đã đáp ứng đầy đủ một mức AAL.

Luồng xử lý cho người dùng mất điện thoại:

1. Người dùng khởi tạo recovery và nhận phiên giới hạn gắn với giao dịch.
2. Backend xác minh mật khẩu và mã recovery, lưu nguồn gốc, thời điểm và phạm vi của từng bằng chứng.
3. Policy xác định tổ hợp đủ điều kiện để chuẩn bị thay TOTP; giao dịch vẫn chưa có quyền commit thay đổi.
4. Người dùng thiết lập TOTP mới trong phạm vi phiên recovery. Backend xác minh mã từ secret mới và tạo bản ghi đăng ký đã chuẩn bị, chưa liên kết yếu tố mới vào tài khoản.
5. Backend cố định nội dung thay đổi và phát grant chỉ cho việc thay TOTP bằng bản ghi đã chuẩn bị đó.
6. Trong một lần commit, backend kiểm tra lại điều kiện, tiêu thụ grant và xử lý bằng chứng dùng một lần, liên kết TOTP mới, xử lý TOTP cũ và cập nhật trạng thái bảo mật.
7. Hệ thống xử lý các session thuộc phạm vi thu hồi, phát thông báo và yêu cầu đăng nhập theo phương tiện vừa được liên kết.
8. Nếu người dùng tiếp tục yêu cầu xuất toàn bộ tài liệu, endpoint xuất dữ liệu đánh giá policy riêng; grant thay TOTP không thể dùng thay cho quyền đó.

Secret TOTP trong bước chuẩn bị cần được bảo vệ khi lưu trữ, có thời hạn và chỉ truy cập được trong đúng giao dịch. Bản ghi chuẩn bị bị hủy hoặc hết hạn không được trở thành authenticator dùng để đăng nhập.

Mã recovery có thể được tiêu thụ khi backend chấp nhận nó thành evidence dùng một lần cho giao dịch, hoặc khi commit thay đổi, tùy thiết kế. Nếu tiêu thụ sớm, evidence phải được ràng buộc độc quyền vào giao dịch và không tạo nhiều grant cạnh tranh. Nếu tiêu thụ ở commit, việc đánh dấu đã dùng phải nằm trong cùng ranh giới nguyên tử với thay đổi. Không được chỉ đánh dấu trên giao diện hoặc giữ mã chưa bị khóa trong nhiều luồng song song.

Điểm quyết định là chuỗi cấp quyền có thể giải thích được: bằng chứng nào cho phép thay TOTP, grant nào duyệt thay đổi cụ thể, session nào bị thu hồi, và điều kiện nào cho phép cấp phiên sử dụng mới.

## 15. Nguyên tắc ghi nhớ

Mức bảo đảm phải gắn với bằng chứng đã kiểm chứng, thời điểm xác minh và thao tác cụ thể. Đừng biểu diễn nó bằng số màn hình người dùng đã đi qua.

Luồng recovery cần có một quyết định độc lập về quyền liên kết authenticator thay thế. Sau quyết định đó, xác thực bằng phương tiện mới và khôi phục quyền sử dụng vẫn là các bước cần điều kiện riêng.

Một thiết kế tốt cho phép trả lời rõ: **Ai đang được làm gì, nhờ bằng chứng nào, trong bao lâu, và điều gì sẽ khiến quyền đó hết hiệu lực?**
