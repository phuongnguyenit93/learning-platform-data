# NIST SP 800-63

Một cổng dịch vụ có thể xác thực rất mạnh nhưng vẫn gắn tài khoản với nhầm người. Một hệ thống khác có thể kiểm tra danh tính cẩn thận, rồi để kẻ tấn công chiếm tài khoản qua luồng đăng nhập hoặc khôi phục. Khi dùng SSO, còn có khả năng ứng dụng nhận sai thông tin từ bên cung cấp danh tính. Những lỗi này xảy ra ở các mắt xích khác nhau của IAM.

NIST SP 800-63, **Digital Identity Guidelines**, cung cấp cách mô tả và đánh giá các mắt xích đó. Bài này sử dụng **Revision 4**, bản chính thức công bố ngày 31/07/2025, thay thế Revision 3. Phạm vi chính là danh tính con người truy cập dịch vụ trực tuyến; không nên tự áp các mức trong tài liệu thành một hệ thống chứng nhận cho service account hoặc workload identity. Thông tin phiên bản được đối chiếu tại [trang công bố SP 800-63-4 của NIST](https://csrc.nist.gov/pubs/sp/800/63/4/final).

## 1. Đọc đúng phần của bộ tài liệu

Bộ hướng dẫn gồm tài liệu nền và ba phần chuyên biệt:

| Tài liệu | Trọng tâm khi thiết kế IAM |
|---|---|
| SP 800-63-4 | Mô hình danh tính và quản lý rủi ro để chọn mức bảo đảm |
| SP 800-63A-4 | Identity proofing và enrollment: thiết lập, kiểm chứng danh tính |
| SP 800-63B-4 | Authentication và quản lý authenticator: chứng minh quyền kiểm soát phương tiện xác thực |
| SP 800-63C-4 | Federation và assertion: truyền kết quả danh tính, xác thực giữa các bên |

Đây là cấu trúc của bộ [Digital Identity Guidelines do NIST công bố](https://csrc.nist.gov/pubs/sp/800/63/4/final). Trong thực hành, đội phụ trách đăng ký người dùng thường phải trao đổi với đội đăng nhập và đội tích hợp SSO, vì một thay đổi ở đầu vào có thể ảnh hưởng đến cách ứng dụng sử dụng danh tính về sau.

Ví dụ, trường `email` có thể xuất hiện trong cả ba đội, nhưng câu hỏi của mỗi đội khác nhau: địa chỉ này được thu thập và kiểm chứng thế nào, ai đang kiểm soát tài khoản chứa nó, và ứng dụng nào được tin thông tin ấy từ IdP? Không thể dùng một lần kiểm tra định dạng email để trả lời cả ba câu hỏi.

## 2. Ba chiều bảo đảm độc lập

Khi thảo luận thiết kế, có thể diễn đạt ba câu hỏi như sau:

| Chiều | Câu hỏi cần trả lời | Một lỗi minh họa |
|---|---|---|
| IAL — Identity Assurance Level | Tài khoản được gắn với danh tính ngoài đời đáng tin đến đâu? | Người đăng ký dùng danh tính bị đánh cắp |
| AAL — Authentication Assurance Level | Lần xác thực chứng minh quyền kiểm soát authenticator mạnh đến đâu? | Kẻ tấn công đăng nhập bằng bí mật bị lộ |
| FAL — Federation Assurance Level | Việc chuyển và tiếp nhận kết quả qua federation được bảo vệ đến đâu? | Assertion bị chèn vào sai giao dịch |

Tên và phạm vi của ba chiều được định nghĩa trong [SP 800-63-4](https://pages.nist.gov/800-63-4/sp800-63.html). Các tình huống trong bảng là ví dụ giải thích, không phải tiêu chí phân loại đầy đủ.

Hãy xét một tài khoản có tên hiển thị tự chọn nhưng dùng một khóa xác thực mạnh. Thiết kế ấy có thể bảo vệ tốt tính liên tục của tài khoản: người quay lại vẫn kiểm soát khóa đã đăng ký. Tuy nhiên, khóa không tự chứng minh tên hiển thị là tên thật. Ngược lại, một hồ sơ được đối chiếu kỹ vẫn có thể bị chiếm nếu mật khẩu bị lộ.

Trong hồ sơ thiết kế, nên ghi riêng từng chiều thay vì một nhãn mơ hồ như `identityLevel: high`. Không cộng ba con số thành điểm tổng và cũng không suy ra chiều còn lại chỉ từ một chiều đã biết. Đặc biệt, phân quyền RBAC/ABAC vẫn cần quyết định riêng: đăng nhập đáng tin chưa có nghĩa là được sửa mọi tài nguyên.

## 3. IAL: bảo đảm về danh tính ngoài đời

Revision 4 phân biệt rõ **không thực hiện identity proofing** với **IAL1**:

| Trường hợp | Ý nghĩa khái quát |
|---|---|
| Không identity proofing | Không yêu cầu liên kết tài khoản với một người cụ thể ngoài đời |
| IAL1 | Có kiểm chứng thuộc tính cốt lõi từ nguồn có thẩm quyền hoặc đáng tin và liên kết chúng với người đăng ký |
| IAL2 | Tăng yêu cầu bằng chứng, kiểm tra và xác minh người sở hữu bằng chứng |
| IAL3 | Bổ sung phiên kiểm chứng trực tiếp tại chỗ với nhân sự được đào tạo và thu thập đặc trưng sinh trắc học |

Vì vậy, mô tả “IAL1 chỉ là người dùng tự khai, không kiểm chứng danh tính” không phù hợp với Revision 4. Các mức và trường hợp không proofing được trình bày trong [SP 800-63A-4, phần Identity Assurance Levels](https://pages.nist.gov/800-63-4/sp800-63a.html).

Ví dụ, một diễn đàn kỹ thuật chỉ cần duy trì tài khoản để lưu bài viết có thể không cần biết tên pháp lý của thành viên. Nếu sau đó diễn đàn mở dịch vụ cấp chứng nhận đứng tên người học, nhóm sản phẩm phải đánh giá lại luồng cấp chứng nhận. Không nên âm thầm coi mọi tài khoản diễn đàn cũ là đã được kiểm chứng chỉ vì chúng tồn tại lâu năm.

Một hồ sơ enrollment dùng trong ví dụ này có thể tách các trạng thái:

```text
accountCreated          = true
emailOwnershipConfirmed = true
identityProofingDone    = false
certificateEligible     = false
```

Đây là mô hình minh họa của ứng dụng, không phải schema do NIST quy định. Việc tách trạng thái giúp đội vận hành nhìn thấy khoảng trống: xác nhận quyền kiểm soát hộp thư là một sự kiện có ích, nhưng không tự thay thế quy trình kiểm chứng danh tính cần cho dịch vụ mới.

## 4. AAL: bảo đảm của lần xác thực

Các mức AAL có thể khái quát như sau:

| Mức | Đặc điểm chính |
|---|---|
| AAL1 | Cho phép xác thực một yếu tố |
| AAL2 | Cần hai yếu tố khác nhau; ứng dụng phải cung cấp lựa chọn chống phishing |
| AAL3 | Hai yếu tố, giao thức mật mã khóa công khai, chống phishing và khóa xác thực không thể xuất |

Đạt một mức còn phụ thuộc các yêu cầu chi tiết và vòng đời authenticator, không chỉ số bước trên màn hình đăng nhập. Xem [SP 800-63B-4, phần Authentication Assurance Levels](https://pages.nist.gov/800-63-4/sp800-63b.html).

Một màn hình yêu cầu mật khẩu rồi PIN do máy chủ kiểm tra vẫn có thể chỉ hỏi hai bí mật cùng loại. Đếm hai ô nhập liệu không đủ để kết luận có hai yếu tố độc lập. Tương tự, nhãn “MFA enabled” trong trang quản trị chỉ là điểm bắt đầu để điều tra: phải biết chính lần đăng nhập đang xét đã đi qua phương thức nào và kết quả ấy còn phù hợp với thao tác sắp thực hiện hay không.

Ví dụ, cổng quản trị có thể cho phép đọc thông báo sau đăng nhập thông thường, nhưng yêu cầu một lần xác thực mới trước khi đổi cấu hình đăng nhập cho toàn tổ chức. Thiết kế cần làm rõ điều kiện kích hoạt, cách liên kết kết quả mới với phiên hiện tại và cách xử lý khi người dùng không hoàn thành. Không chỉ thêm hộp thoại xác nhận rồi ghi nhận rằng mức bảo đảm đã tăng.

### Mật khẩu và passkey cần được đặt đúng ngữ cảnh

Một số điểm đáng chú ý trong Revision 4 là mật khẩu dùng như yếu tố duy nhất phải dài ít nhất 15 ký tự, không áp quy tắc phối hợp bắt buộc các loại ký tự, không bắt đổi mật khẩu định kỳ theo lịch thông thường và phải cho phép password manager cùng autofill. Đây chỉ là một phần yêu cầu; xem [FAQ chính thức của NIST về Revision 4](https://pages.nist.gov/800-63-4-Implementation-Resources/faqs/).

Revision 4 cũng bổ sung hướng dẫn cho authenticator có khả năng đồng bộ, chẳng hạn synced passkey. NIST mô tả thay đổi này trong [bài công bố bộ hướng dẫn mới](https://www.nist.gov/blogs/cybersecurity-insights/lets-get-digital-updated-digital-identity-guidelines-are-here). Tên sản phẩm “passkey” vì thế chưa đủ để chọn mức bảo đảm cho một triển khai cụ thể: đội kỹ thuật phải đối chiếu đặc tính khóa, cách kích hoạt và quy trình quản lý với yêu cầu tương ứng.

Trong một bản đánh giá thiết kế, câu hỏi “người dùng có passkey chưa?” nên được cụ thể hóa thành “đường đăng nhập nào đã được sử dụng, khóa có thuộc loại được chính sách cho phép không, và có đường khôi phục nào làm thay đổi kết luận ấy không?”.

## 5. FAL: bảo đảm khi dùng federation

FAL đánh giá giao dịch federation giữa Identity Provider (**IdP**) và Relying Party (**RP**):

| Mức | Đặc điểm khái quát theo Revision 4 |
|---|---|
| FAL1 | Assertion được giới hạn bên nhận; RP kiểm tra bên nhận và chống phát lại |
| FAL2 | Bổ sung chống assertion injection, giao dịch do RP khởi tạo, một RP nhận và thỏa thuận tin cậy có trước |
| FAL3 | RP còn xác minh người dùng kiểm soát authenticator, qua holder-of-key hoặc bound authenticator |

Đây không phải toàn bộ điều kiện tuân thủ. Xem [SP 800-63C-4, phần Federation Assurance Levels](https://pages.nist.gov/800-63-4/sp800-63c.html). Không nên dùng mô tả rút gọn của phiên bản cũ để khẳng định rằng chỉ cần mã hóa assertion là đạt FAL2 của Revision 4.

Trong một tích hợp SSO giả định, IdP có thể xác thực người dùng rất mạnh nhưng RP lại xử lý sai callback. Khi đó, chất lượng xác thực tại IdP không sửa được lỗi gắn callback vào sai phiên ở RP. Câu hỏi thiết kế phải theo suốt đường đi của giao dịch, thay vì chỉ kiểm tra cấu hình đăng nhập của nhà cung cấp.

Với cùng lý do, bật OIDC hay SAML không tự xác định FAL. Đội tích hợp cần đưa ra bằng chứng từ cấu hình và hành vi thực tế. Một tài liệu chỉ ghi `protocol: OIDC` chưa giải thích RP tin issuer nào, kỳ vọng giao dịch nào hoặc xử lý callback lặp ra sao.

## 6. Chọn mức theo rủi ro của dịch vụ

SP 800-63-4 đưa ra quy trình quản lý rủi ro: xác định dịch vụ và nhóm người dùng, đánh giá tác động, chọn mức ban đầu, điều chỉnh có giải trình, sau đó liên tục đánh giá và cải thiện. Kết quả được ghi trong **Digital Identity Acceptance Statement — DIAS**, bao gồm mức được chọn và các kiểm soát liên quan. Nguồn: [SP 800-63-4, phần Digital Identity Risk Management](https://pages.nist.gov/800-63-4/sp800-63.html).

Có thể áp dụng cách nghĩ này cho một hệ thống quản lý chứng nhận nội bộ. Các mức bên dưới là **phương án giả định để thảo luận**, không phải kết luận phân loại do NIST đưa ra cho mọi hệ thống cùng tên.

| Chức năng giả định | Rủi ro cần xem xét | Hướng thiết kế để đánh giá |
|---|---|---|
| Đọc tài liệu công khai | Không có dữ liệu cá nhân hay thao tác thay đổi | Có thể không cần tài khoản |
| Lưu tiến độ học cá nhân | Mất lịch sử hoặc bị người khác sử dụng tài khoản | Đánh giá bảo vệ tài khoản; chưa mặc định cần proofing |
| Nhận chứng nhận gắn tên thật | Cấp chứng nhận cho nhầm người | Đánh giá nhu cầu proofing và bằng chứng phù hợp |
| Phê duyệt chứng nhận cho người khác | Lạm dụng quyền gây ảnh hưởng nhiều hồ sơ | Đánh giá riêng xác thực người phê duyệt và quyền theo phạm vi |
| Đăng nhập qua IdP đối tác | Tin sai người, sai tổ chức hoặc sai kết quả xác thực | Đánh giá thêm giao dịch federation và thỏa thuận với đối tác |

Nhóm thiết kế có thể thử phương án `IAL2/AAL2/FAL2` cho một chức năng đã xác định, rồi kiểm tra xem đánh giá tác động và cách triển khai có thực sự hỗ trợ phương án đó không. Viết bộ ba vào tài liệu chưa chứng minh hệ thống đáp ứng nó.

Ví dụ, nếu học viên đăng ký bằng bí danh nhưng người phê duyệt là nhân viên đã qua quy trình kiểm chứng riêng, hai nhóm không nhất thiết có cùng hồ sơ bảo đảm. Nếu dịch vụ không sử dụng federation, đội thiết kế cũng không cần dựng một IdP chỉ để điền đủ ba con số.

## 7. Từ quyết định thiết kế đến bằng chứng

Một bản ghi quyết định hữu ích phải cho phép người khác hiểu được phạm vi và kiểm tra lại. Mẫu dưới đây dành cho ví dụ cổng chứng nhận; đây là gợi ý tổ chức hồ sơ của đội dự án, không phải biểu mẫu chuẩn của NIST:

```yaml
service: internal-certificate-portal
userGroup: certificate-approvers
operation: approve-certificate
guidelineRevision: NIST-SP-800-63-4
proposedAssurance:
  ial: IAL2
  aal: AAL2
  fal: FAL2
decisionState: pending-evidence-review
evidenceNeeded:
  - staff-enrollment-process
  - permitted-authentication-paths
  - partner-federation-configuration
  - recovery-and-authenticator-change-process
authorizationPolicy: approval-scope-by-department
reviewOwner: identity-service-team
```

`proposedAssurance` có chủ ý biểu thị phương án cần kiểm tra. Không đưa bản ghi này vào token để ứng dụng tự tin rằng mọi đăng nhập đều đạt mức đề xuất. Trong hệ thống thật, kết luận về từng giao dịch phải đến từ thành phần tin cậy và chính sách đã được đánh giá.

Khi dùng nhà cung cấp bên ngoài, RP cần xem DIAS của CSP/IdP và đánh giá các điều chỉnh có phù hợp với dịch vụ của mình không. NIST cũng làm rõ rằng NIST không vận hành một chương trình chứng nhận cho bộ hướng dẫn này. Vì vậy, câu quảng cáo “NIST compliant” cần được làm rõ về phiên bản, phạm vi và bằng chứng. Xem [FAQ triển khai của NIST](https://pages.nist.gov/800-63-4-Implementation-Resources/faqs/).

Ví dụ, đội dự án có thể yêu cầu nhà cung cấp trình bày một luồng đăng nhập thành công, một luồng khôi phục sau mất thiết bị và một giao dịch federation bị từ chối. Cách hỏi này giúp biến lời tuyên bố chung thành hành vi có thể quan sát. Những yêu cầu kiểm tra cụ thể phải được lựa chọn theo phạm vi hợp đồng và thiết kế, không tự coi ba ví dụ ấy là một cuộc đánh giá tuân thủ đầy đủ.

## 8. Theo dõi toàn bộ vòng đời danh tính

Một cách áp dụng thực tế là theo dấu một tài khoản từ lúc tạo đến khi hết quyền sử dụng. Trong ví dụ cổng chứng nhận, đội IAM có thể lập bảng sau để giao trách nhiệm và thu thập bằng chứng:

| Sự kiện | Câu hỏi vận hành | Bằng chứng ứng dụng có thể lưu |
|---|---|---|
| Tiếp nhận nhân viên phê duyệt | Ai chấp thuận gắn tài khoản với hồ sơ nhân viên? | Mã hồ sơ quy trình và thời điểm hoàn thành |
| Đăng ký authenticator mới | Sự kiện có do đúng chủ tài khoản thực hiện không? | Loại thao tác, phương thức xác nhận và kết quả |
| Đổi thiết bị hoặc mất thiết bị | Ai quyết định tài khoản đủ điều kiện hoạt động lại? | Hồ sơ xử lý, người phụ trách và phương tiện bị thu hồi |
| Đăng nhập qua đối tác | Ứng dụng đã tin kết quả từ nguồn nào? | Định danh nguồn và kết quả kiểm tra giao dịch |
| Đổi phòng ban | Quyền phê duyệt cũ còn hợp lệ không? | Quyết định cấp/thu hồi quyền theo phạm vi |
| Nghỉ việc | Tài khoản, phiên và quyền liên quan đã được xử lý chưa? | Kết quả đóng tài khoản và các bước xử lý tiếp theo |

Đây là các câu hỏi triển khai cho tình huống minh họa. Bảng giúp nối thiết kế danh tính với phân quyền và kiểm toán mà không coi chúng là cùng một chức năng. Chẳng hạn, một nhân viên vẫn có thể đăng nhập đúng danh tính sau khi chuyển phòng, nhưng quyền phê duyệt của phòng cũ phải được xem xét lại.

Khi thiết kế log, chỉ lưu dữ liệu cần cho mục đích điều tra và vận hành. Một mã tham chiếu hồ sơ thường hữu ích hơn việc sao chép ảnh giấy tờ vào mọi sự kiện đăng nhập. Đội dự án phải xác định ai được đọc bằng chứng, thời gian lưu và cách xử lý khi có sai sót; thu thập nhiều dữ liệu hơn không tự tạo ra kết luận bảo đảm tốt hơn.

## 9. Những kết luận dễ nhầm trong dự án IAM

| Nhận định | Cách kiểm tra lại bằng tình huống cụ thể |
|---|---|
| “Có MFA nên hồ sơ người dùng chắc chắn đúng tên thật” | Xem tên thật đã được kiểm chứng ở luồng enrollment nào |
| “Người dùng đã được kiểm chứng nên mọi lần đăng nhập đều an toàn” | Xem phương thức và bối cảnh của chính lần truy cập đang xét |
| “Nhà cung cấp hỗ trợ mức cao nên mọi ứng dụng đều đạt mức đó” | Xem đường tích hợp, cấu hình và các ngoại lệ của ứng dụng |
| “SSO thành công thì được phê duyệt chứng nhận” | Kiểm tra tiếp quyền, phòng ban và phạm vi hồ sơ |
| “Luồng khôi phục ít dùng nên có thể xem sau” | Thử tình huống mất thiết bị trước khi chấp nhận thiết kế |
| “Một nhãn tuân thủ đủ cho mọi phiên bản” | Ghi rõ revision và phạm vi đánh giá trong quyết định |

Ví dụ, tài khoản của một trưởng bộ phận đã đăng nhập thành công và có hồ sơ danh tính đáng tin vẫn phải bị từ chối khi phê duyệt hồ sơ ngoài phạm vi được giao. Nếu ứng dụng cho phép thao tác đó, tăng yêu cầu xác thực có thể không sửa được nguyên nhân: chính sách phân quyền hoặc cách kiểm tra quyền đang sai.

## 10. Bài tập áp dụng

### Tình huống 1: đổi từ tài khoản diễn đàn sang cấp chứng nhận

Một hệ thống đã xác nhận email và bảo vệ đăng nhập bằng MFA. Nhóm sản phẩm muốn dùng tên tự khai từ hồ sơ cũ để in chứng nhận tên thật. Cần hỏi gì trước khi triển khai?

**Gợi ý:** Tách yêu cầu duy trì tài khoản khỏi yêu cầu biết danh tính ngoài đời. Xác định hậu quả của chứng nhận sai, nhóm người nhận, bằng chứng hiện có và quy trình cần bổ sung. Đừng lấy việc có MFA làm bằng chứng rằng tên đã được kiểm chứng.

### Tình huống 2: đối tác SSO tuyên bố “bảo mật mức cao”

Nhà cung cấp đưa một tài liệu giới thiệu nhưng không nêu revision, luồng khôi phục hoặc cấu hình federation dành cho ứng dụng. Đội tích hợp có thể chốt mức bảo đảm ngay không?

**Gợi ý:** Chưa có đủ căn cứ cho quyết định đó. Cần làm rõ tuyên bố áp dụng cho chức năng nào, lấy tài liệu và bằng chứng phù hợp, rồi đánh giá cách RP thực sự sử dụng dịch vụ. Khả năng của nền tảng và cấu hình đang triển khai là hai thông tin cần đối chiếu.

### Tình huống 3: đăng nhập đúng nhưng thao tác sai phạm vi

Người phê duyệt dùng phương thức xác thực được tổ chức chấp thuận, nhưng có thể sửa hồ sơ của phòng khác bằng cách đổi mã hồ sơ trong request. Nên bắt đầu điều tra ở đâu?

**Gợi ý:** Kiểm tra kiểm soát truy cập phía máy chủ và quan hệ giữa người phê duyệt với hồ sơ. Đây là ví dụ cho thấy bảo đảm danh tính hỗ trợ quyết định truy cập, còn quyền thực hiện thao tác vẫn phải được kiểm tra riêng.

Các bài tập trên giúp sử dụng NIST SP 800-63 như một công cụ đặt câu hỏi và tổ chức bằng chứng: xác định rõ đang bảo đảm điều gì, ở bước nào, cho nhóm người dùng nào và dựa trên cơ sở nào.
