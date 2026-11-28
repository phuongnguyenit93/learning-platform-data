# Identity Assurance Level

## 1. IAL trả lời câu hỏi nào?

Identity Assurance Level (IAL) là mức bảo đảm của quá trình kiểm chứng danh tính: tổ chức có cơ sở đến đâu để tin rằng người đăng ký thực sự là cá nhân mang danh tính được khai báo. Trong IAM, một tài khoản có thể có tên, email và số điện thoại nhưng các dữ liệu đó chưa tự chứng minh danh tính ngoài đời của người sử dụng.

Ví dụ, một người tạo tài khoản với tên “Nguyễn Minh An” rồi bật MFA. MFA giúp bảo vệ việc đăng nhập vào tài khoản đã tạo; nó không tự chứng minh rằng người đăng ký chính là Nguyễn Minh An. Nếu quy trình ban đầu gắn tài khoản với nhầm người, các lần đăng nhập sau có thể xác thực rất tốt chính người đang mạo danh.

IAL tập trung vào danh tính của con người. Khi quản lý service account hoặc workload identity, cần đánh giá nguồn cấp, chủ sở hữu và ràng buộc với workload; không gán mức IAL của con người trực tiếp cho một tiến trình chỉ vì tiến trình sử dụng chứng thư.

Bài học sử dụng bộ NIST SP 800-63 Revision 4 làm mốc. Các vai trò CSP, IdP và RP được phân biệt trong [mô hình danh tính số của NIST](https://pages.nist.gov/800-63-4/sp800-63/model/).

## 2. Phân biệt IAL, AAL, FAL và quyền truy cập

Ba chiều bảo đảm giải quyết những vấn đề khác nhau:

| Khái niệm | Điều cần có cơ sở tin cậy | Ví dụ câu hỏi khi thiết kế |
| --- | --- | --- |
| IAL — Identity Assurance Level | Danh tính được khai báo và mối liên hệ với người đăng ký | Tài khoản này đã được gắn với đúng cá nhân chưa? |
| AAL — Authentication Assurance Level | Việc kiểm soát authenticator gắn với tài khoản | Người đăng nhập đã chứng minh quyền kiểm soát phương tiện xác thực như thế nào? |
| FAL — Federation Assurance Level | Việc truyền thông tin xác thực và thuộc tính qua liên kết danh tính | Ứng dụng có nhận đúng assertion dành cho mình và đúng chủ thể không? |

Phân quyền còn trả lời câu hỏi khác: chủ thể có được thực hiện hành động trên tài nguyên cụ thể không? Một người đã được kiểm chứng danh tính vẫn phải đáp ứng RBAC, ABAC, tenant, phạm vi dữ liệu và các điều kiện phê duyệt.

Trong ví dụ cổng nhà thầu, tài khoản có hồ sơ proofing đạt yêu cầu nhưng hợp đồng đã hết hạn phải bị từ chối truy cập. Ngược lại, một phiên đăng nhập dùng MFA không đủ điều kiện thực hiện nghiệp vụ đòi hỏi danh tính đã được kiểm chứng nếu hồ sơ đó còn thiếu.

NIST cho phép lựa chọn các chiều bảo đảm theo nhu cầu dịch vụ; chúng không phải một con số chung phải bằng nhau. Việc lựa chọn dựa trên rủi ro của từng chức năng và nhóm người dùng được trình bày trong [Digital Identity Risk Management](https://pages.nist.gov/800-63-4/sp800-63/dirm/).

## 3. Chuỗi kiểm chứng: resolution, validation, verification

Một quy trình proofing cần phân biệt ba công việc:

1. **Identity resolution — phân giải danh tính:** thu thập đủ bằng chứng và thuộc tính để phân biệt cá nhân trong tập đối tượng mà dịch vụ phục vụ.
2. **Identity validation — kiểm tra tính hợp lệ:** kiểm tra bằng chứng có xác thực, chính xác, hợp lệ và thuộc tính có khớp nguồn có thẩm quyền hoặc đáng tin cậy hay không.
3. **Identity verification — kiểm chứng người xuất trình:** xác lập rằng người đang thực hiện quy trình là người gắn với bằng chứng đó.

Sau proofing thành công, enrollment thiết lập hồ sơ subscriber và gắn phương tiện xác thực với tài khoản. Quy trình này được mô tả trong [Identity Proofing Overview](https://pages.nist.gov/800-63-4/sp800-63a/proofing/).

Có thể hiểu qua một hồ sơ nhà thầu giả định:

- Hai người trùng họ tên cần được phân biệt bằng các thuộc tính phù hợp; tìm thấy một chuỗi tên giống nhau chưa đủ để chọn đúng hồ sơ.
- Một giấy tờ thật nhưng thuộc về người khác có thể vượt qua kiểm tra tính xác thực của giấy tờ. Bước liên kết người xuất trình với giấy tờ vẫn có thể thất bại.
- Một ảnh chụp đọc được thông tin chưa chứng minh rằng giấy tờ còn hợp lệ hoặc dữ liệu có thể kiểm tra với nguồn đáng tin.
- Nếu tài khoản được gắn với nhầm hồ sơ sau proofing, kết quả tốt ở bước trước cũng không cứu được việc cấp phát sai.

Vì vậy, khi xem thiết kế, cần hỏi cả “bằng chứng có đáng tin không?” và “bằng chứng này có thuộc về người đang đăng ký không?”. Hai câu hỏi không thể thay thế nhau.

## 4. Ba mức IAL trong Revision 4

| Mức | Đặc điểm khái quát |
| --- | --- |
| IAL1 | Có kiểm chứng danh tính, kiểm tra thuộc tính cốt lõi và liên kết người đăng ký với danh tính. |
| IAL2 | Tăng yêu cầu về bằng chứng, validation và verification; có thể triển khai từ xa hoặc tại chỗ, với các phương án có hoặc không dùng so khớp sinh trắc học tự động. |
| IAL3 | Thực hiện theo hình thức on-site attended, có proofing agent; bổ sung yêu cầu thu thập, lưu giữ và đối chiếu thông tin sinh trắc học. |

Bảng chỉ định hướng; triển khai phải đối chiếu toàn bộ yêu cầu của mức tương ứng. Tại IAL3, agent có thể tham gia qua kiosk hoặc thiết bị do CSP kiểm soát theo điều kiện quy định; một cuộc gọi video tùy ý không đủ. Xem [yêu cầu IAL của NIST SP 800-63A-4](https://pages.nist.gov/800-63-4/sp800-63a/ial/).

### Điểm dễ nhầm: IAL1 đã thay đổi giữa các phiên bản

Trong Revision 3, IAL1 cho phép sử dụng thuộc tính tự khai mà không validation hoặc verification. Quy định này được ghi tại [NIST SP 800-63A, mục 4.3](https://pages.nist.gov/800-63-3/sp800-63a.html#sec4).

Revision 4 đưa IAL1 vào phạm vi proofing có yêu cầu cụ thể. Do đó, khi đọc tài liệu cũ hoặc tích hợp một nhà cung cấp, cần hỏi rõ phiên bản chuẩn. Nhãn “IAL1” đứng một mình không đủ để diễn giải quy trình.

Một dịch vụ chỉ cần biệt danh và không cần biết danh tính ngoài đời có thể không cần identity proofing. Thiết kế nội bộ có thể biểu diễn là `NOT_PROOFED` hoặc `NOT_REQUIRED`, nhưng không tự coi những nhãn này là một mức IAL do NIST định nghĩa.

### Chất lượng bằng chứng không chỉ là số lượng

Một tập gồm nhiều ảnh chụp không được kiểm tra nguồn vẫn có thể kém tin cậy. Khi chọn phương án, cần đánh giá loại bằng chứng được chấp nhận, nguồn phát hành, phương pháp validation và cách liên kết người xuất trình.

Hệ quả thiết kế là không dùng quy tắc nội bộ như “có hai giấy tờ thì đạt IAL2”. Một workflow phải được đánh giá theo đầy đủ tập điều kiện áp dụng, thay vì suy ra mức bảo đảm từ số trường đã điền hoặc số tệp đã tải lên.

## 5. Chọn yêu cầu IAL từ nghiệp vụ

Trước hết cần xác định dịch vụ có thực sự cần danh tính ngoài đời hay không. Nếu có, hãy mô tả thiệt hại khi một người mạo danh đăng ký thành công. Phải xét cả người dùng, tổ chức và người bị ảnh hưởng dù không trực tiếp sử dụng dịch vụ.

Ví dụ thiết kế dưới đây là tình huống minh họa, không phải bảng cấp mức bắt buộc cho mọi hệ thống:

| Chức năng trong cổng nhà thầu | Rủi ro cần phân tích | Hướng thiết kế |
| --- | --- | --- |
| Xem tài liệu công khai | Ít phụ thuộc vào danh tính thật | Có thể không yêu cầu proofing nếu không có nhu cầu khác |
| Nộp hồ sơ xin cấp tài khoản | Nhận hồ sơ của người mạo danh | Chỉ coi đây là hồ sơ đang xét, chưa cấp quyền nhạy cảm |
| Xem hồ sơ hợp đồng riêng | Lộ thông tin cho người khác | Đặt yêu cầu proofing, xác thực và phân quyền riêng |
| Đề nghị thay đổi thông tin thanh toán | Gian lận và chuyển sai lợi ích | Kết hợp hồ sơ danh tính đủ tin cậy, xác thực phù hợp và phê duyệt nghiệp vụ |

Với cùng một ứng dụng, các nhóm người dùng có thể cần mức bảo đảm khác nhau. Việc chọn mức cao hơn cũng cần xét dữ liệu nhạy cảm phải thu thập, thời gian hoàn tất và khả năng người dùng hợp lệ bị loại nhầm. Đây là đánh đổi cần được ghi lại, không phải chỉ chọn mức lớn nhất rồi áp dụng đại trà.

## 6. Ví dụ gắn kết quả proofing với tài khoản IAM

Giả sử doanh nghiệp có chính sách yêu cầu hồ sơ proofing theo Revision 4 đạt tối thiểu IAL2 trước khi nhà thầu được xem hợp đồng. Quy trình minh họa:

1. Tạo hồ sơ đăng ký với định danh nội bộ ổn định; tài khoản mới chỉ có quyền hoàn tất đăng ký.
2. Dịch vụ proofing xử lý theo chính sách đã được đánh giá và trả kết quả qua kênh backend được xác thực.
3. Backend xác minh nguồn, đối chiếu mã giao dịch và ràng buộc kết quả với đúng tài khoản.
4. Ghi nhận kết quả proofing; không lấy giá trị `ial` từ form hoặc tham số do trình duyệt tự khai.
5. Một quy trình riêng kiểm tra hợp đồng, đơn vị bảo trợ và quyền tài nguyên.
6. Khi truy cập, ứng dụng xét đồng thời hồ sơ danh tính, chất lượng phiên xác thực và quyền hiện hành.

Hồ sơ dưới đây là schema nội bộ minh họa, không phải bộ claim chuẩn của OIDC hay một định dạng do NIST bắt buộc:

```json
{
  "subjectId": "contractor-7c92",
  "identityAssurance": {
    "framework": "NIST-SP-800-63-4",
    "ial": 2,
    "state": "VERIFIED",
    "providerId": "approved-csp-a",
    "policyId": "contractor-proofing-v3",
    "assessmentRef": "proofing-result-89ab",
    "proofedAt": "2026-11-20T08:15:00Z",
    "reviewAfter": "2027-11-20T08:15:00Z"
  }
}
```

Trong ví dụ này:

- `framework` xác định cách diễn giải mức; không so sánh mù quáng nhãn từ các phiên bản hoặc hệ chuẩn khác nhau.
- `providerId` và `assessmentRef` cho phép truy vết nguồn kết quả.
- `policyId` chỉ ra quy trình đã áp dụng, hữu ích khi nhà cung cấp thay đổi phương pháp.
- `state` là trạng thái nghiệp vụ của hồ sơ, độc lập với mức đã ghi nhận.
- `reviewAfter` là thời điểm rà soát theo chính sách doanh nghiệp trong ví dụ; không có nghĩa mọi IAL đều có thời hạn chuẩn một năm.

Không đưa ảnh giấy tờ, số định danh hoặc mẫu sinh trắc học vào access token chỉ để chứng minh rằng proofing đã xảy ra. Ứng dụng thường chỉ cần kết quả, nguồn tin cậy và tham chiếu có kiểm soát đến hồ sơ gốc.

## 7. Áp dụng trong quyết định truy cập

Có thể diễn đạt chính sách đọc hợp đồng bằng mã giả:

```text
evaluateContractRead(account, session, contract):
    if account.state != ACTIVE:
        return DENY_ACCOUNT_INACTIVE

    assurance = trustedAssuranceStore.lookup(account.subjectId)

    if assurance is missing:
        return REQUIRE_IDENTITY_PROOFING

    if assurance.framework != policy.acceptedFramework:
        return REQUIRE_ASSURANCE_REVIEW

    if assurance.providerId not in policy.approvedProviders:
        return DENY_UNTRUSTED_PROOFING_SOURCE

    if assurance.state != VERIFIED:
        return REQUIRE_ASSURANCE_REVIEW

    if assurance.ial < policy.minimumIal:
        return REQUIRE_HIGHER_IDENTITY_PROOFING

    if policy.requiresReview(assurance, account):
        return REQUIRE_ASSURANCE_REVIEW

    if not authenticationPolicy.accepts(session):
        return REQUIRE_STRONGER_AUTHENTICATION

    if not authorizationPolicy.canRead(account, contract):
        return DENY_INSUFFICIENT_PERMISSION

    return PERMIT
```

Kho kết quả trong ví dụ chỉ nhận dữ liệu sau khi đã kiểm tra nguồn và liên kết chủ thể. Mã giả bỏ qua chi tiết giao thức, lưu trữ và đồng thời; nó minh họa vị trí của IAL trong quyết định, không phải thư viện triển khai tiêu chuẩn.

Hai kết quả `REQUIRE_HIGHER_IDENTITY_PROOFING` và `REQUIRE_STRONGER_AUTHENTICATION` dẫn đến hai hành trình khác nhau. Người dùng thiếu proofing phải hoàn thành quy trình kiểm chứng danh tính phù hợp. Người dùng có hồ sơ đạt yêu cầu nhưng phiên xác thực chưa đủ mạnh cần hoàn tất xác thực bổ sung theo chính sách. Yêu cầu nhập thêm OTP không tự sửa được hồ sơ danh tính còn thiếu.

## 8. SSO và liên kết danh tính

Trong SSO, RP có thể tiếp nhận thông tin assurance từ một IdP hoặc dịch vụ liên quan. Quyết định tin cậy cần dựa trên thỏa thuận và ý nghĩa của dữ liệu được truyền, không chỉ dựa vào việc token có chữ ký hợp lệ.

Ví dụ, một IdP phát hành claim nội bộ `identity_verified=true`. RP vẫn cần biết “verified” là xác minh email, kiểm tra giấy tờ hay hoàn thành một quy trình proofing cụ thể. Nếu các bên chưa thống nhất cách diễn giải, RP không nên tự ánh xạ giá trị này thành IAL2.

Một thiết kế tích hợp nên xác định rõ:

- Bên nào thực hiện proofing và bên nào chịu trách nhiệm công bố kết quả.
- Chuẩn, phiên bản và chính sách dùng để đánh giá.
- Cách liên kết subject tại RP với hồ sơ đã proofing.
- Cách thông báo hồ sơ bị đình chỉ, thu hồi hoặc cần xem xét lại.
- Phạm vi thuộc tính mà RP thực sự cần sử dụng.

Cũng cần tránh gộp tài khoản chỉ vì có cùng tên hiển thị hoặc email không đủ tin cậy. Việc liên kết sai tài khoản có thể làm kết quả proofing của một người được sử dụng cho người khác.

## 9. Vòng đời hồ sơ và khả năng kiểm toán

Một kết quả proofing cần được quản lý trong suốt vòng đời tài khoản. CSP phải có tài liệu về quy trình, bằng chứng chấp nhận, nguồn validation, xử lý gian lận, ngoại lệ và những điều kiện cần kiểm chứng lại. Các yêu cầu này nằm trong [Identity Proofing Requirements](https://pages.nist.gov/800-63-4/sp800-63a/ial-general/).

Trong thiết kế minh họa, hồ sơ có thể chuyển qua các trạng thái:

```text
NOT_PROOFED -> IN_PROGRESS -> VERIFIED
                        `-> FAILED

VERIFIED -> REVIEW_REQUIRED
VERIFIED -> SUSPENDED
```

Đây là state machine nội bộ, không phải danh sách trạng thái chuẩn của NIST. Mức IAL đã đạt và trạng thái sử dụng kết quả là hai thuộc tính khác nhau: một hồ sơ từng hoàn thành IAL2 vẫn có thể bị đình chỉ khi phát hiện gian lận.

Các tình huống cần chính sách xử lý rõ gồm khôi phục tài khoản, thay đổi liên kết định danh, phát hiện bằng chứng bị sử dụng trái phép và thay đổi quy trình của nhà cung cấp. Không mặc định mọi sự kiện đều bắt buộc proofing lại; phải xét quy định áp dụng và mức độ ảnh hưởng đến cơ sở tin cậy.

Nhật ký nên giúp trả lời: ai hoặc hệ thống nào ghi nhận kết quả, cho subject nào, theo chính sách nào, khi nào và dựa trên tham chiếu nào. Việc thu hồi quyền sau khi nhà thầu rời tổ chức vẫn phải thực hiện, kể cả hồ sơ proofing trước đó còn nguyên.

## 10. Quyền riêng tư và trải nghiệm người dùng

Proofing có thể yêu cầu xử lý dữ liệu rất nhạy cảm. Một kiến trúc thực tế nên tách kho bằng chứng khỏi kho tài khoản thông thường, phân quyền người xem hồ sơ, bảo vệ dữ liệu khi truyền và lưu trữ, đồng thời quy định việc lưu giữ và xóa theo mục đích đã xác định.

Cần thiết kế hành trình cho người không có camera phù hợp, không có loại bằng chứng mặc định hoặc gặp lỗi đối chiếu. Kênh hỗ trợ phải có quy trình và thẩm quyền rõ ràng; không dùng việc “nhân viên hỗ trợ thấy hợp lý” để bỏ qua các điều kiện đạt mức đã công bố.

Theo dõi cả tỷ lệ gian lận, số người hợp lệ không hoàn tất được và thời gian xử lý giúp phát hiện vấn đề mà một tỷ lệ thành công tổng hợp có thể che giấu. Những chỉ số này cần được diễn giải theo nhóm người dùng và từng phương án proofing, tránh kết luận rằng nhiều bước hơn luôn có nghĩa là hiệu quả hơn.

## 11. Những nhầm lẫn cần tránh

| Nhầm lẫn | Cách hiểu đúng |
| --- | --- |
| Bật MFA làm tài khoản tăng IAL | MFA liên quan đến xác thực; proofing có quy trình và bằng chứng riêng |
| Email đã xác minh nghĩa là đã biết danh tính thật | Việc kiểm soát một hộp thư không tự xác lập danh tính ngoài đời |
| Nhãn IAL có nghĩa giống nhau ở mọi phiên bản | Phải xác định chuẩn và phiên bản, đặc biệt với IAL1 |
| Có ảnh giấy tờ là đã hoàn thành proofing | Cần xem cả validation, verification và việc gắn đúng tài khoản |
| IAL cao tự cấp quyền quản trị | Quyền phải được phê duyệt và áp dụng theo chính sách riêng |
| Kết quả proofing luôn dùng được mãi | Cần quản lý trạng thái, sự kiện ảnh hưởng và điều kiện rà soát |
| Dịch vụ lưu càng nhiều bằng chứng càng tốt | Dữ liệu phải phù hợp mục đích, phạm vi sử dụng và chính sách lưu giữ |

## 12. Tình huống tự kiểm tra

Một nhà thầu đăng nhập bằng MFA, có role `CONTRACT_READER`, nhưng hồ sơ chỉ ghi `emailVerified=true`. Ứng dụng yêu cầu proofing theo Revision 4 đạt tối thiểu IAL2 và hợp đồng của nhà thầu đang hoạt động.

Ứng dụng chưa đủ cơ sở cho phép truy cập. MFA đáp ứng một phần điều kiện xác thực; role đáp ứng một phần điều kiện phân quyền; xác minh email chưa chứng minh rằng quy trình proofing cần thiết đã hoàn tất. Hành động phù hợp là hướng người dùng đến quy trình kiểm chứng được chấp nhận, sau đó đánh giá lại toàn bộ điều kiện.

Nếu hồ sơ proofing đã đạt yêu cầu nhưng hợp đồng hết hạn, ứng dụng vẫn phải từ chối quyền đọc. IAL giúp biết tài khoản được gắn với ai; vòng đời quyền quyết định cá nhân đó còn được sử dụng tài nguyên hay không.
