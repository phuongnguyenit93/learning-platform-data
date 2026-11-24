# Nhà cung cấp kiểm chứng danh tính (Identity proofing provider)

## 1. Provider giúp xác minh điều gì trong luồng khôi phục?

Trong chương **Identity Proofing** của module khôi phục tài khoản, identity proofing provider là đơn vị hoặc dịch vụ thực hiện một phần hay toàn bộ quy trình kiểm chứng danh tính. Hệ thống có thể dùng dịch vụ này khi người dùng mất mật khẩu, MFA, passkey hoặc thiết bị xác thực và cần một nhánh recovery dựa trên danh tính đã thiết lập trước đó.

Một provider có thể kiểm tra giấy tờ, đối chiếu thuộc tính với nguồn dữ liệu, so sánh khuôn mặt hoặc hỗ trợ nhân viên xét duyệt. Tuy nhiên, việc provider trả về “đã xác minh” chưa tự trả lời câu hỏi quan trọng nhất:

> Người vừa được xác minh có phải là chủ của tài khoản đang yêu cầu khôi phục hay không?

Ví dụ, Lan từng mở một tài khoản có hồ sơ danh tính đã được kiểm chứng. Khi Lan mất tất cả thiết bị, một lần kiểm chứng lại có thể cung cấp bằng chứng để đối chiếu với hồ sơ cũ. Ngược lại, nếu tài khoản chỉ được tạo bằng biệt danh và chưa có liên kết đáng tin với danh tính ngoài đời, việc một người xuất trình giấy tờ thật của chính họ chưa chứng minh họ sở hữu tài khoản đó.

Mục tiêu của tích hợp là tạo ra **bằng chứng có nguồn gốc, phạm vi và điều kiện sử dụng rõ ràng**, để policy recovery của ứng dụng quyết định quyền tiếp theo. Provider không nên trở thành một nút mở khóa mọi tài khoản.

Sau bài này, người học có thể xác định phạm vi provider, lập tiêu chí lựa chọn, thiết kế tích hợp bất đồng bộ, bảo vệ dữ liệu nhạy cảm và sử dụng kết quả kiểm chứng để cấp quyền recovery có giới hạn.

## 2. Hiểu đúng phạm vi của một dịch vụ kiểm chứng

NIST SP 800-63A-4 mô tả ba bước: resolution để phân giải danh tính trong tập đối tượng liên quan; validation để kiểm tra tính xác thực, chính xác và còn hiệu lực của bằng chứng; verification để xác nhận người trình bằng chứng là người gắn với bằng chứng đó. Xem [NIST: Identity Proofing Overview](https://pages.nist.gov/800-63-4/sp800-63a/proofing/).

Một dịch vụ chỉ thực hiện một bước chưa chắc là một quy trình proofing đầy đủ.

| Năng lực | Có thể cung cấp điều gì? | Chưa tự chứng minh điều gì? |
| --- | --- | --- |
| OCR giấy tờ | Trích xuất chữ, ngày tháng, số nhận dạng | Giấy tờ thật hoặc người trình là chủ giấy tờ |
| Kiểm tra tài liệu | Tín hiệu về mẫu giấy tờ, đặc điểm bảo vệ hoặc nguồn phát hành | Quyền sở hữu tài khoản ứng dụng |
| Đối chiếu thuộc tính | Mức phù hợp của thông tin với nguồn đối chiếu | Người gửi request đang kiểm soát authenticator cũ |
| So khớp khuôn mặt | Mức tương đồng giữa ảnh và ảnh tham chiếu | Danh tính đã liên kết với đúng tài khoản cần phục hồi |
| Kiểm tra hiện diện hoặc chống giả mạo | Tín hiệu chống một số cách trình ảnh, video hay đầu vào giả | Miễn nhiễm với mọi deepfake, injection hoặc cưỡng ép |
| Nhân viên xét duyệt | Quyết định theo hồ sơ và quy trình được giao | Quyền bỏ qua policy recovery của ứng dụng |
| Quy trình proofing được đánh giá | Kết quả của tổ hợp kiểm tra trong cấu hình cụ thể | Tự động đạt mọi yêu cầu xác thực, session và cấp quyền |

Khi đánh giá provider, cần biết chính xác các bước được thực hiện, bằng chứng nào được chấp nhận, nguồn đối chiếu nào được dùng và trường hợp nào bị chuyển xét duyệt. Một nhãn “AI verification” hoặc một điểm số chung không mô tả đủ những điều đó.

### 2.1. Provider kiểm chứng danh tính khác IdP đăng nhập

Một identity provider dùng cho SSO thường phát hành thông tin xác thực về người dùng theo giao thức liên kết danh tính. Một identity proofing provider kiểm tra danh tính theo quy trình đã thỏa thuận. Một nhà cung cấp có thể cung cấp cả hai chức năng, nhưng hai vai trò không tự đồng nhất.

Tương tự, IAL mô tả mức bảo đảm của kiểm chứng danh tính, còn AAL thuộc bảo đảm xác thực. Không gắn AAL2 hoặc AAL3 cho session chỉ vì người dùng vừa hoàn tất một lần chụp giấy tờ.

Nếu muốn tuyên bố một mức bảo đảm cụ thể, phải xem xét toàn bộ quy trình, cấu hình và phạm vi đánh giá liên quan. Không suy mức bảo đảm từ tên gói sản phẩm.

## 3. Điều kiện tiên quyết: liên kết với danh tính lịch sử

Trong recovery dựa trên kiểm chứng lại, cần có một mốc đáng tin đã được thiết lập từ trước:

~~~text
Tài khoản ứng dụng
    → hồ sơ danh tính đã được thiết lập
    → nguồn gốc và phương pháp kiểm chứng ban đầu
    → kết quả kiểm chứng lại
    → quyết định phù hợp giữa danh tính hiện tại và hồ sơ cũ
~~~

Theo NIST SP 800-63B-4, kiểm chứng lại phục vụ recovery cần xác nhận danh tính phù hợp với tài khoản đã thiết lập. Với tài khoản chưa từng được kiểm chứng danh tính, nhánh reproofing không có sẵn để dùng làm phương án recovery. Xem [NIST: Repeated Identity Proofing](https://pages.nist.gov/800-63-4/sp800-63b/events/#repeated-identity-proofing).

Ứng dụng có thể xây phương án riêng theo phân tích rủi ro, nhưng không được coi một giấy tờ mới là bằng chứng sở hữu tài khoản chỉ vì tên trên giấy tờ giống tên hiển thị.

### 3.1. Những liên kết yếu thường bị nhầm là đủ

| Cách đối chiếu | Rủi ro |
| --- | --- |
| Trùng tên hiển thị | Tên có thể phổ biến, tự khai hoặc đã bị sửa |
| Trùng email vừa nhập trong recovery | Kênh mới có thể do người tấn công kiểm soát |
| Provider nhận accountId từ client | Có thể gắn kết quả của một người vào tài khoản khác |
| Trùng một số giấy tờ do người gọi đọc ra | Biết thuộc tính không đồng nghĩa sở hữu danh tính hoặc tài khoản |
| Ảnh selfie giống avatar | Avatar có thể công khai, cũ hoặc không phải ảnh chủ tài khoản |
| Trùng dữ liệu hồ sơ vừa được đổi | Thay đổi do kẻ chiếm phiên có thể làm sai mốc đối chiếu |

Mốc lịch sử cần có nguồn gốc và khả năng truy vết. Hệ thống nên ghi nhận phiên bản hồ sơ, thời điểm thiết lập, phương pháp đã dùng và các thay đổi liên quan.

Giấy tờ đổi số hoặc tên thay đổi không đồng nghĩa người dùng đã trở thành người khác. Quy trình đối chiếu cần có cách xử lý các thay đổi hợp lệ bằng bằng chứng thích hợp. Không nên vừa dùng so tên gần đúng để tự cấp quyền, vừa từ chối tuyệt đối mọi thay đổi giấy tờ.

### 3.2. Kết quả đối chiếu cần có trạng thái riêng

Trong mô hình của bài, tách hai kết quả:

- **Proofing outcome:** provider đã kiểm chứng điều gì về người đang thực hiện?
- **Historical identity match:** kết quả đó có phù hợp với hồ sơ danh tính đáng tin của tài khoản cần recovery không?

Historical identity match có thể là MATCH, MISMATCH hoặc INCONCLUSIVE. Thiếu dữ liệu không được tự chuyển thành MATCH. Một tên và ngày sinh trùng nhau cũng không nên tự trở thành một phép nối tài khoản duy nhất.

Nếu phải dùng thuộc tính nhạy cảm để đối chiếu, thực hiện trong một dịch vụ được giới hạn truy cập. Có thể lưu tham chiếu hồ sơ hoặc giá trị đối chiếu được bảo vệ phù hợp thay cho việc sao chép dữ liệu giấy tờ sang mọi dịch vụ. Không coi hash của số giấy tờ có không gian đoán nhỏ là dữ liệu đã được ẩn danh.

## 4. Chọn provider bằng yêu cầu kiểm chứng có thể kiểm tra

Không bắt đầu bằng câu hỏi “provider nào có điểm chính xác cao nhất”. Trước hết, xác định đối tượng người dùng, bằng chứng cần thu thập và quyết định recovery mà hệ thống muốn hỗ trợ.

| Nhóm tiêu chí | Câu hỏi cần làm rõ |
| --- | --- |
| Phạm vi giấy tờ và địa lý | Hỗ trợ loại giấy tờ, ngôn ngữ và nguồn phát hành nào? Có giới hạn phiên bản hoặc chất lượng ảnh không? |
| Phương pháp kiểm chứng | Chỉ OCR, kiểm tra ảnh tài liệu, đọc chip, đối chiếu nguồn hay tổ hợp nào? |
| Chống gian lận | Có bằng chứng đánh giá đối với giấy tờ giả, replay, video giả và đầu vào bị chèn không? |
| Bảo đảm của quy trình | Quy trình và cấu hình nào được đánh giá, theo phiên bản nào, trong phạm vi nào? |
| Khả năng giải thích | Có kết quả theo từng phép kiểm tra, mã lý do và phiên bản cấu hình không? |
| Xét duyệt | Khi nào cần người duyệt, ai được xem dữ liệu và thời gian xử lý dự kiến là gì? |
| Trải nghiệm | Người dùng có thể hoàn tất trên thiết bị phổ biến, mạng yếu hoặc với nhu cầu tiếp cận khác nhau không? |
| Tích hợp | Có API server, webhook được xác thực, cơ chế truy vấn trạng thái và hỗ trợ idempotency không? |
| Dữ liệu | Thu thập những gì, xử lý ở đâu, lưu trong bao lâu, chia sẻ cho bên nào và xóa theo cách nào? |
| Vận hành | Có giới hạn lưu lượng, thông báo sự cố, thay đổi API và quy trình hỗ trợ phù hợp không? |
| Chi phí | Tính phí theo phiên, lần thử, kết quả hay xét duyệt? Retry do lỗi kỹ thuật được tính thế nào? |
| Khả năng rời nhà cung cấp | Có giữ đủ provenance để chuyển dịch vụ mà không phá liên kết danh tính lịch sử không? |

Đây là khung đánh giá của ứng dụng, không phải danh sách chứng nhận. Một chứng nhận bảo mật của tổ chức không tự chứng minh cấu hình proofing đang dùng đáp ứng yêu cầu recovery của sản phẩm.

NIST yêu cầu tài liệu vận hành mô tả quy trình, loại bằng chứng, công nghệ, xử lý ngoại lệ, thay đổi dịch vụ và quản lý dữ liệu. Những nội dung này là căn cứ hữu ích để yêu cầu provider giải trình. Xem [NIST: Identity Service Documentation and Records](https://pages.nist.gov/800-63-4/sp800-63a/ial-general/#identity-service-documentation-and-records).

### 4.1. Đọc số liệu hiệu quả đúng ngữ cảnh

Tỷ lệ một phép so khuôn mặt nhận nhầm người khác khác với tỷ lệ toàn bộ quy trình chấp nhận một hồ sơ gian lận. Tỷ lệ từ chối nhầm cũng khác với tỷ lệ người dùng bỏ dở do camera, giấy tờ không hỗ trợ hoặc mạng lỗi.

Khi so sánh số liệu, cần biết tập đánh giá, ngưỡng quyết định, loại thiết bị, phương pháp tấn công, thời điểm và phạm vi kiểm tra. Không so hai con số phần trăm mà bỏ qua các điều kiện đó.

Trong vận hành, nên quan sát cả việc chấp nhận sai, từ chối nhầm, tỷ lệ hoàn tất và kết quả xét lại theo những nhóm người dùng có liên quan. Việc thu thập dữ liệu để đánh giá cũng cần có mục đích, phạm vi và quyền truy cập được kiểm soát.

Ngưỡng provider chọn để tối ưu chuyển đổi chưa chắc phù hợp với recovery cho tài khoản đặc quyền. Ngược lại, thắt ngưỡng mà không có đường xử lý ngoại lệ có thể làm người dùng hợp lệ mất quyền truy cập lâu dài.

## 5. Phân chia trách nhiệm trước khi viết API

Thuê ngoài proofing không chuyển toàn bộ trách nhiệm khôi phục tài khoản sang provider.

| Thành phần | Trách nhiệm trong mô hình minh họa |
| --- | --- |
| Recovery service | Xác định giao dịch, phương án recovery, quyền giới hạn và hạn mức |
| Provider adapter | Gọi đúng API, xác thực webhook, chuẩn hóa kết quả theo hợp đồng |
| Identity matching service | Đối chiếu với hồ sơ danh tính lịch sử đã được bảo vệ |
| Recovery policy | Đánh giá kết quả, tổ hợp bằng chứng, rủi ro và quyền được cấp |
| Authenticator service | Liên kết yếu tố mới khi có quyền hợp lệ |
| Session service | Thu hồi và cấp phiên theo quyết định bảo mật |
| Nhóm hỗ trợ và xét duyệt | Xử lý ngoại lệ theo thẩm quyền và lưu căn cứ quyết định |

Provider không được tự gửi lệnh “tắt MFA” vào authenticator service. Kết quả của provider đi qua adapter và policy của ứng dụng.

~~~mermaid
flowchart TD
    U["Người dùng trong phiên recovery giới hạn"] --> R["Recovery service"]
    R --> E{"Có phương án proofing phù hợp?"}
    E -->|"Không"| O["Phương án recovery khác hoặc xử lý ngoại lệ"]
    E -->|"Có"| A["Tạo attempt và chọn cấu hình ở backend"]
    A --> P["Provider thu thập và kiểm chứng"]
    P --> W["Webhook đã xác thực hoặc truy vấn trạng thái"]
    W --> N["Chuẩn hóa kết quả và kiểm tra phạm vi"]
    N --> M["Đối chiếu danh tính lịch sử"]
    M --> D["Recovery policy"]
    D -->|"Chưa đủ"| X["Bổ sung, xét duyệt hoặc từ chối"]
    D -->|"Đủ"| G["Quyền giới hạn cho thao tác đã duyệt"]
    G --> B["Liên kết authenticator thay thế"]
    B --> S["Xử lý session và yêu cầu xác thực phù hợp"]
~~~

Đường quay lại từ trình duyệt của provider chỉ giúp người dùng trở về ứng dụng. Quyết định bảo mật dựa trên dữ liệu server đã kiểm chứng, không dựa vào tham số success=true trên URL.

## 6. Mô hình dữ liệu: lưu kết quả và nguồn gốc riêng

Trong bài này, một **proofing attempt** là một lần thực hiện proofing thuộc một giao dịch recovery. Nó khác với một lần chụp lại ảnh và khác với phiên recovery trong trình duyệt.

Ví dụ bản ghi attempt ở backend:

~~~json
{
  "attemptId": "proof-72",
  "tenantId": "tenant-a",
  "accountId": "account-42",
  "recoveryCaseId": "rec-18",
  "generation": 1,
  "purpose": "ACCOUNT_RECOVERY_REPROOFING",
  "providerId": "provider-a",
  "providerAccountScope": "project-prod-1",
  "environment": "PRODUCTION",
  "providerSessionId": "external-session-91",
  "expectedIdentityRecordRef": "identity-record-12",
  "expectedIdentityRecordVersion": 3,
  "requiredProfile": "recovery-document-check-v2",
  "configurationFingerprint": "config-ref-204",
  "accountSecurityVersion": 17,
  "state": "AWAITING_RESULT",
  "createdAt": "2026-11-23T02:00:00Z",
  "expiresAt": "2026-11-23T02:30:00Z"
}
~~~

Tên trường và giá trị là mô hình giả định, không phải API của một provider cụ thể. Nếu giấy tờ đã được nhà cung cấp thu thập trực tiếp, attempt không cần chứa ảnh giấy tờ hoặc video.

providerSessionId không đủ để xác định phạm vi tin cậy. Cần biết provider, tài khoản hoặc project phía provider và môi trường test hay production. Một ID có thể không có tính duy nhất trên mọi hệ thống bên ngoài.

requiredProfile mô tả các kiểm tra mà ứng dụng yêu cầu. configurationFingerprint tham chiếu cấu hình thực tế đã dùng. Cấu hình phải do backend chọn; client không được tắt kiểm tra cần thiết rồi vẫn xin quyền recovery.

### 6.1. Kết quả chuẩn hóa không được làm mất thông tin quan trọng

~~~json
{
  "attemptId": "proof-72",
  "providerSessionId": "external-session-91",
  "providerReportId": "report-305",
  "providerStatus": "provider-specific-completed",
  "normalizedOutcome": "PASSED",
  "checks": {
    "documentValidation": "PASSED",
    "holderVerification": "PASSED",
    "requiredFraudControls": "PASSED"
  },
  "observedAt": "2026-11-23T02:08:00Z",
  "providerCompletedAt": "2026-11-23T02:07:45Z",
  "historicalIdentityMatch": "NOT_EVALUATED",
  "recoveryDecision": "NOT_EVALUATED"
}
~~~

Đây là ví dụ theo profile đã chọn; các nhánh proofing khác có thể yêu cầu tổ hợp kiểm tra khác. Không mặc định mọi người dùng đều phải dùng cùng kiểu giấy tờ hay sinh trắc học.

Mỗi phép kiểm tra nên phân biệt PASSED, FAILED, NOT_RUN và INCONCLUSIVE khi provider có thể cung cấp dữ liệu đó. Thiếu kết quả của một phép kiểm tra bắt buộc không được tự chuyển thành PASSED.

Các trạng thái sau không nên gộp vào một boolean verified:

- Đang xử lý.
- Cần người dùng cung cấp lại đầu vào.
- Cần xét duyệt.
- Không đạt theo phép kiểm tra.
- Lỗi kỹ thuật.
- Đã hủy hoặc hết hạn.
- Đã hoàn tất các kiểm tra theo cấu hình.

Ví dụ thực tế về sự khác nhau giữa session và report có trong [Stripe: Verification Sessions API](https://docs.stripe.com/identity/verification-sessions). Tài liệu mô tả trạng thái verified khi các kiểm tra đã hoàn tất thành công và requires_input khi cần xử lý đầu vào sau kiểm tra không đạt. Các trạng thái này vẫn cần được adapter diễn giải theo cấu hình của ứng dụng.

Không dùng điểm số 0,9 của provider A như tương đương điểm 0,9 của provider B. Adapter phải giữ ý nghĩa của kết quả, phiên bản API và phiên bản mapping đang dùng.

## 7. Tạo phiên provider an toàn và có thể khôi phục khi lỗi

Một luồng tạo phiên phù hợp có thể diễn ra như sau:

1. Recovery service xác minh quyền truy cập giao dịch giới hạn, kiểm tra phương án proofing được phép và hạn mức phát hành.
2. Backend chọn provider, môi trường, profile và hồ sơ danh tính tham chiếu.
3. Backend lưu attempt ở trạng thái CREATING với một khóa idempotency ổn định cho lần tạo này.
4. Dispatcher gọi API provider ngoài transaction đang giữ khóa dữ liệu.
5. Khi nhận kết quả, backend lưu providerSessionId và các tham chiếu cần thiết vào đúng attempt.
6. Chỉ người đang được phép truy cập attempt mới nhận URL hoặc client token ngắn hạn để bắt đầu thu thập.
7. Khi quay lại ứng dụng, client truy vấn trạng thái từ backend.

Khóa idempotency nên gắn với attempt hoặc giao dịch và generation, tránh chứa số giấy tờ hay dữ liệu cá nhân. Retry sau lỗi mạng dùng lại khóa của cùng thao tác tạo. Nếu cần tạo attempt mới theo policy, đó là một quyết định riêng với generation mới.

### 7.1. Provider đã tạo phiên nhưng ứng dụng bị timeout

Một timeout HTTP không chứng minh provider chưa tạo đối tượng. Nếu lập tức tạo lại bằng khóa mới, hệ thống có thể phát sinh nhiều phiên, mất lịch sử thử và tăng chi phí.

Cần dùng cơ chế idempotency hoặc tra cứu được provider hỗ trợ để đối soát. Attempt chưa biết kết quả tạo nên có trạng thái thể hiện sự chưa chắc chắn, thay vì bị ghi thành “không đạt danh tính”.

Nếu webhook đến trước khi mapping providerSessionId được lưu xong, nhận nó vào inbox đã xác thực và thực hiện đối soát có giới hạn. Không bỏ qua vĩnh viễn chỉ vì chưa tìm thấy mapping ở thời điểm đầu tiên; cũng không dùng metadata do client cung cấp để tự gắn vào một tài khoản bất kỳ.

### 7.2. URL và client token là dữ liệu nhạy cảm

URL bắt đầu proofing hoặc client token có thể cấp khả năng truy cập một phiên chứa dữ liệu cá nhân. Chỉ chuyển chúng đến đúng phiên recovery, qua kênh bảo vệ và trong phạm vi cần thiết.

Không đặt API secret của provider trong frontend. Không đưa client token vào log, công cụ phân tích hành vi hoặc thông báo hỗ trợ. Trang xử lý nên tránh thành phần bên thứ ba không cần thiết có thể thu thập URL hay nội dung nhạy cảm.

Return URL cần được cấu hình hoặc kiểm tra theo danh sách được phép. Nó không được trở thành open redirect hoặc một nơi lộ token khi đưa người dùng quay lại ứng dụng.

## 8. Webhook cần xác thực, chống lặp và đối soát trạng thái

Webhook là dữ liệu đầu vào từ một hệ thống ngoài. Cần xác minh cả **nguồn gửi** lẫn **ý nghĩa và phạm vi của kết quả**.

### 8.1. Xác thực thông điệp

Các bước cụ thể phụ thuộc giao thức provider:

1. Giới hạn kích thước request và chọn cấu hình endpoint đã biết.
2. Xác thực chữ ký hoặc cơ chế xác thực theo SDK, tài liệu và khóa đúng môi trường.
3. Nếu giao thức ký raw body, xác thực trên đúng byte nhận được trước khi framework thay đổi cách biểu diễn.
4. Kiểm tra timestamp hoặc chống replay theo cơ chế được giao thức hỗ trợ.
5. Chỉ sau khi xác thực mới tin eventId, provider object reference và các trường nghiệp vụ.
6. Lưu bền vững vào inbox với khóa chống trùng rồi mới xác nhận đã nhận thành công.

Chữ ký hợp lệ không ngăn cùng một sự kiện bị xử lý nhiều lần. OWASP phân biệt xác thực nguồn với chống replay và xử lý idempotent. Xem [OWASP: Webhook Security](https://cheatsheetseries.owasp.org/cheatsheets/Webhook_Security_Cheat_Sheet.html).

Nếu inbox không lưu được, không trả thông báo đã nhận thành công rồi bỏ mất sự kiện. Cách báo lỗi và retry cần phù hợp hợp đồng của provider.

### 8.2. Dedupe theo đúng phạm vi

Khóa chống lặp có thể gồm:

~~~text
(providerId, providerAccountScope, environment, eventId)
~~~

Ngoài chống trùng event, việc ghi evidence cần có tính idempotent theo attempt và report hoặc kết quả liên quan. Hai eventId khác nhau cùng phản ánh một report không được tạo hai quyền độc lập.

Lưu bản ghi “đã xử lý” phải gắn với việc cập nhật trạng thái nội bộ trong cùng transaction hoặc một thiết kế inbox có thể retry an toàn. Đánh dấu đã xử lý trước rồi lỗi ở bước ghi evidence có thể làm mất kết quả.

### 8.3. Không suy trạng thái hiện tại từ thứ tự nhận

Sự kiện PROCESSING có thể đến sau sự kiện hoàn tất. Một retry của report cũ có thể đến sau attempt mới. Không cập nhật theo quy tắc “event đến sau cùng luôn thắng”.

Tùy khả năng provider, adapter có thể dùng phiên bản đối tượng, phiên bản report hoặc truy vấn lại đối tượng chuẩn qua API đã cấu hình. Nếu không có version đáng tin, cần tuần tự hóa đối soát cho cùng attempt để tránh hai lần fetch hoàn tất trái thứ tự ghi đè nhau.

Tài liệu [Stripe: Webhooks](https://docs.stripe.com/webhooks) nêu yêu cầu dùng raw body khi kiểm tra chữ ký, khả năng nhận sự kiện không theo thứ tự và cách xử lý sự kiện lặp. Đây là ví dụ cho một giao thức cụ thể; provider khác có thể có cơ chế và cam kết khác.

Khi truy vấn lại, dùng provider reference đã lưu trong mapping của backend. Không gọi URL bất kỳ nằm trong webhook hoặc request của client. Endpoint, project và credential phải đến từ cấu hình được kiểm soát.

### 8.4. Kết quả đến sau khi giao dịch đã đóng

Provider có thể hoàn tất sau khi người dùng hủy recovery, giao dịch hết hạn hoặc một attempt mới đã thay thế attempt cũ. Có thể lưu kết quả để đối soát và quản lý dữ liệu, nhưng không tự tạo quyền recovery từ kết quả đó.

Tương tự, webhook test có chữ ký hợp lệ của môi trường test không được ảnh hưởng tài khoản production. Tính hợp lệ về nguồn không xóa các ràng buộc môi trường, project và tài khoản.

## 9. Chuyển kết quả proofing thành điều kiện recovery

Bài này dùng mô hình quyết định sau:

~~~text
Đủ điều kiện dùng kết quả proofing =
    nguồn và môi trường được chấp nhận
    AND đúng attempt, tài khoản, tenant và giao dịch
    AND đúng profile và các kiểm tra bắt buộc
    AND kết quả còn được phép sử dụng
    AND danh tính phù hợp với hồ sơ lịch sử đáng tin
    AND policy và trạng thái rủi ro cho phép
~~~

Việc provider xác minh thành công chỉ là một thành phần. Nếu profile yêu cầu xác minh người giữ giấy tờ nhưng kết quả chỉ có OCR thành công, điều kiện vẫn chưa đạt.

Mã giả Java dưới đây minh họa cách giữ các điều kiện riêng biệt. Các kiểu dữ liệu và phương thức là hợp đồng của ứng dụng giả định, chưa phải một bộ tích hợp hoàn chỉnh.

~~~java
public RecoveryEvaluation evaluate(
        RecoveryCase recovery,
        ProofingAttempt attempt,
        TrustedProviderObservation observation,
        HistoricalIdentityMatch identityMatch,
        Instant now) {

    if (!attempt.belongsTo(recovery)
            || !attempt.matchesProviderScope(observation)
            || !attempt.isCurrentFor(recovery)) {
        return RecoveryEvaluation.rejectResult("INVALID_BINDING");
    }

    if (!recovery.isOpenAt(now)
            || !attempt.acceptsResultAt(now)) {
        return RecoveryEvaluation.rejectResult("CLOSED_OR_EXPIRED");
    }

    if (!providerPolicy.accepts(
            attempt.providerId(),
            attempt.requiredProfile(),
            observation.configuration())) {
        return RecoveryEvaluation.review("PROFILE_NOT_ACCEPTED");
    }

    if (observation.outcome() == ProofingOutcome.PROCESSING) {
        return RecoveryEvaluation.pending();
    }

    if (observation.outcome() == ProofingOutcome.TECHNICAL_ERROR) {
        return RecoveryEvaluation.retryAccordingToPolicy();
    }

    if (observation.outcome() != ProofingOutcome.PASSED
            || !requiredChecks.allPassed(attempt, observation)) {
        return RecoveryEvaluation.review("PROOFING_NOT_SUFFICIENT");
    }

    if (!identityMatch.isMatchFor(
            attempt.id(),
            attempt.expectedIdentityRecordRef(),
            attempt.expectedIdentityRecordVersion())) {
        return RecoveryEvaluation.review("HISTORICAL_MATCH_NOT_ESTABLISHED");
    }

    if (!securityState.compatibleWith(recovery, attempt)
            || riskPolicy.requiresReview(recovery, observation)) {
        return RecoveryEvaluation.review("SECURITY_REVIEW_REQUIRED");
    }

    return RecoveryEvaluation.eligibleFor(
            Action.BIND_REPLACEMENT_AUTHENTICATOR,
            observation.evidenceReference());
}
~~~

TrustedProviderObservation chỉ được tạo sau khi adapter đã xác thực nguồn và kiểm tra dữ liệu theo hợp đồng. HistoricalIdentityMatch cũng phải là kết quả của dịch vụ tin cậy, gắn với cùng attempt và cùng phiên bản hồ sơ; không nhận một trường match=true từ client.

rejectResult là từ chối sử dụng kết quả đó, không đồng nghĩa khóa tài khoản hoặc kết luận người dùng gian lận. REVIEW cũng chưa phải phê duyệt. Nó yêu cầu quy trình có căn cứ và thẩm quyền trước khi có quyền mới.

### 9.1. ELIGIBLE chưa phải grant có thể sử dụng

Đầu ra của hàm chỉ ghi nhận đủ điều kiện theo dữ liệu đã đánh giá. Khi người dùng tiếp tục, backend còn phải xác minh quyền truy cập phiên recovery và kiểm tra trạng thái mới trước khi cấp grant.

Quyết định cấp grant cần được ghi trong ranh giới nhất quán với giao dịch, evidence và trạng thái bảo mật. Không chỉ chạy hàm trên một snapshot cũ rồi cấp token bất chấp tài khoản vừa bị báo chiếm đoạt.

Grant phải gắn với tài khoản, giao dịch, phiên recovery, thao tác và nội dung thay đổi được duyệt; có thời hạn và dùng một lần. Một kết quả proofing không được dùng để xin nhiều grant trái với policy của cùng lần recovery.

### 9.2. Sau khi liên kết yếu tố thay thế

Khi thay MFA hoặc passkey, hệ thống cần xử lý authenticator cũ, các phiên và token trong phạm vi thu hồi, đồng thời thông báo qua kênh đã thiết lập.

Người dùng nên xác thực theo phương tiện đã liên kết trước khi có phiên sử dụng phù hợp. Các tác vụ nhạy cảm như đổi email recovery, tạo API key hoặc xuất dữ liệu có thể tiếp tục cần điều kiện riêng.

Một passkey mới có chữ ký hợp lệ không hợp thức hóa ngược một lần recovery đã gắn sai danh tính. Chuỗi nguồn gốc từ proofing, historical match đến quyền liên kết phải được giữ lại.

## 10. Quyền riêng tư là một phần của kiến trúc tích hợp

Ảnh giấy tờ, video và dữ liệu sinh trắc học làm tăng hậu quả nếu bị lộ. Cần quyết định dữ liệu nào thật sự cần cho recovery và thành phần nào được xử lý dữ liệu đó.

NIST yêu cầu đánh giá rủi ro quyền riêng tư đối với quy trình proofing, bao gồm dữ liệu do bên thứ ba xử lý và lịch lưu giữ. Xem [NIST: General Privacy Requirements](https://pages.nist.gov/800-63-4/sp800-63a/ial-general/#general-privacy-requirements).

Trong thiết kế minh họa:

| Dữ liệu | Cách giới hạn phù hợp |
| --- | --- |
| Ảnh giấy tờ, video | Ưu tiên không đi qua backend ứng dụng nếu kiến trúc thu thập trực tiếp đáp ứng yêu cầu |
| Client token và URL phiên | Chỉ cấp cho đúng phiên recovery, tránh log và công cụ analytics |
| Thuộc tính đã kiểm chứng | Chỉ lấy trường cần cho đối chiếu và quyết định |
| Kết quả phép kiểm tra | Lưu trạng thái, nguồn gốc và lý do cần thiết thay cho toàn bộ hồ sơ thô |
| Tham chiếu provider | Giới hạn quyền truy vấn dữ liệu nhạy cảm thông qua tham chiếu |
| Hồ sơ xét duyệt | Phân quyền theo nhiệm vụ, ghi nhận truy cập và hạn chế xuất dữ liệu |
| Log vận hành | Dùng mã tham chiếu nội bộ; lọc token, giấy tờ và payload nhạy cảm |
| Bản sao lưu | Có kế hoạch hết hạn và xử lý dữ liệu tương ứng, không chỉ xóa hàng trong bảng chính |

Thu thập trực tiếp tại provider giảm dữ liệu đi qua ứng dụng, nhưng provider vẫn đang xử lý dữ liệu cho luồng của sản phẩm. Cần nắm rõ mục đích sử dụng, bên xử lý phụ, phạm vi truy cập của nhân viên và các điều kiện chia sẻ dữ liệu.

Người dùng cần được biết lý do thu thập, đơn vị xử lý, dữ liệu cần cung cấp và phương án khi không thể hoàn tất. Không mặc định chấp nhận điều khoản của sản phẩm là đồng ý với mọi mục đích sử dụng dữ liệu sinh trắc học.

### 10.1. Lưu giữ và xóa phải có cơ chế kiểm chứng

Đặt thời hạn theo loại dữ liệu và mục đích, thay vì lưu mọi thứ vô thời hạn “để phòng tranh chấp”. Quyết định xóa cần bao phủ dữ liệu ở provider, bản sao nội bộ, file tải xuống và các hệ thống phụ trong phạm vi kiểm soát.

Một request xóa được API tiếp nhận chưa chắc có nghĩa toàn bộ dữ liệu đã được xóa ngay. Theo dõi trạng thái hoàn tất theo hợp đồng, cách xử lý lỗi và các dữ liệu còn phải giữ theo chính sách đã xác định.

Có thể cần lưu dấu vết quyết định tối thiểu sau khi dữ liệu thô đã được xóa, chẳng hạn thời điểm, provider, profile, tham chiếu report và quyền đã cấp. Bản ghi đó vẫn có thể liên quan đến một cá nhân nên vẫn cần bảo vệ và thời hạn phù hợp.

Không lưu ảnh giấy tờ lâu dài chỉ để tạo một phương án recovery trong tương lai nếu không có phân tích nhu cầu và rủi ro tương ứng.

## 11. Xét duyệt thủ công và hỗ trợ người dùng

Một luồng proofing không đạt có thể do ảnh mờ, giấy tờ không hỗ trợ, thay đổi tên, thiết bị không phù hợp hoặc một tín hiệu gian lận. Không gộp mọi trường hợp thành “người dùng giả mạo”.

Quy trình ngoại lệ cần nêu rõ:

- Ai được xem hồ sơ và loại dữ liệu nào.
- Căn cứ nào cho phép yêu cầu bổ sung.
- Kết quả nào cần người có thẩm quyền khác xem xét.
- Cách xử lý mâu thuẫn với hồ sơ lịch sử.
- Thời hạn xử lý và cách người dùng theo dõi.
- Điều kiện từ chối, khiếu nại hoặc bắt đầu phương án khác.

Nhân viên hỗ trợ không nên nhận ảnh giấy tờ qua hộp thư cá nhân rồi tự bấm “bỏ MFA”. Công cụ hỗ trợ cần đưa hồ sơ qua cùng hệ thống evidence, policy và kiểm toán.

Nếu áp dụng hai người phê duyệt cho tài khoản có tác động cao, cần độc lập về tài khoản, vai trò và quyết định theo policy. Hai lần bấm xác nhận không tự tạo thêm bằng chứng nếu cả hai chỉ lặp lại một kết luận chưa được kiểm chứng.

Nếu tài khoản chưa có liên kết danh tính lịch sử, chuyển sang người duyệt không tự giải quyết khoảng trống đó. Cần một phương án recovery khác có căn cứ; có trường hợp dữ liệu hiện có không cho phép khôi phục an toàn.

## 12. Provider lỗi, chậm hoặc bị nghi ngờ xâm phạm

Một dịch vụ ngoài sẽ có lúc timeout, trả lỗi hoặc cần xét duyệt lâu hơn dự kiến. Các trạng thái kỹ thuật phải được tách khỏi kết quả kiểm chứng danh tính.

| Sự cố | Cách xử lý phù hợp |
| --- | --- |
| Timeout khi tạo phiên | Đối soát bằng idempotency hoặc tham chiếu đã biết trước khi tạo lại |
| Webhook bị mất | Truy vấn lại các attempt đang chờ theo hạn mức và thời hạn |
| API trả trường chưa biết | Không coi trường thiếu là thành công; dùng mapping có phiên bản và cảnh báo |
| Provider gián đoạn | Giữ phiên recovery giới hạn, hướng dẫn chờ hoặc phương án đủ điều kiện khác |
| Kết quả đến sau hủy | Ghi nhận để đối soát và quản lý dữ liệu; không cấp quyền |
| Provider thay cấu hình kiểm tra | Đánh giá profile mới trước khi dùng cho quyết định mới |
| Rò rỉ khóa API hoặc webhook | Thu hồi, thay khóa và đánh giá các kết quả bị ảnh hưởng |
| Nghi ngờ kết quả bị làm giả từ provider | Dừng sử dụng nguồn ảnh hưởng để cấp quyền mới và rà soát các quyết định liên quan |

Circuit breaker và retry có backoff có thể bảo vệ hệ thống khỏi lỗi dây chuyền. Chúng không được đổi một trạng thái chưa có kết quả thành PASSED.

Nếu provider không hỗ trợ hủy khi đang xử lý, ứng dụng vẫn có thể đóng attempt tại phía mình và chặn sử dụng kết quả về sau. Việc dữ liệu tiếp tục được xử lý hoặc lưu ở provider cần theo dõi riêng theo hợp đồng.

### 12.1. Nhiều provider không tự tạo thêm độ tin cậy

Chuyển từ provider A sang B có thể giúp khả năng phục vụ, nhưng phải bảo đảm profile B đáp ứng yêu cầu tương đương đã được đánh giá. Không dùng một phương án kiểm tra yếu hơn chỉ vì dịch vụ chính đang lỗi.

Nếu người dùng được thử không giới hạn qua nhiều provider cho đến khi có một nơi chấp nhận, nguy cơ chấp nhận sai tích lũy có thể tăng. Hạn mức cần nhìn theo tài khoản, giao dịch và lịch sử thử, không chỉ theo từng nhà cung cấp.

Hai provider cùng dùng một nguồn đối chiếu hoặc cùng công nghệ lõi cũng không tự trở thành hai nguồn bằng chứng độc lập. Quy tắc “hai trong ba provider đồng ý thì khôi phục” không thay thế phân tích phương pháp và điểm phụ thuộc.

## 13. Ví dụ tổng hợp: phục hồi tài khoản đã có hồ sơ danh tính

Giả sử một ứng dụng lưu trữ tài liệu đã kiểm chứng danh tính của Lan khi mở tài khoản và lưu được tham chiếu hồ sơ cùng nguồn gốc kiểm chứng. Lan mất điện thoại và không còn passkey dự phòng.

Luồng minh họa:

1. Lan bắt đầu giao dịch recovery và có phiên giới hạn, chưa được xem tài liệu.
2. Policy xác định tài khoản có phương án kiểm chứng lại phù hợp; backend chọn profile đã được phê duyệt.
3. Backend tạo attempt, liên kết với tài khoản, hồ sơ danh tính lịch sử và project production của provider.
4. Lan cung cấp bằng chứng qua phiên provider được cấp cho attempt đó.
5. Backend nhận sự kiện đã xác thực, chống trùng và truy vấn report theo mapping đã lưu nếu cần.
6. Adapter kiểm tra các phép kiểm tra bắt buộc; dịch vụ đối chiếu xác nhận danh tính phù hợp với hồ sơ lịch sử.
7. Policy đánh giá rủi ro và các điều kiện còn lại. Nếu cần xét duyệt, Lan tiếp tục chờ trong phạm vi giới hạn.
8. Khi đủ điều kiện, một request hợp lệ trong phiên recovery nhận quyền dùng một lần để liên kết authenticator thay thế cụ thể.
9. Backend thực thi thay đổi nguyên tử theo grant, xử lý yếu tố cũ, các session liên quan và thông báo.
10. Lan xác thực bằng phương tiện đã liên kết để nhận phiên sử dụng phù hợp.

Nếu ở bước 4, một người khác xuất trình giấy tờ thật của chính họ và provider xác minh thành công, bước 6 vẫn không cho phép nối danh tính đó vào tài khoản Lan.

Nếu webhook của bước 5 bị gửi lại, hệ thống chỉ đọc hoặc cập nhật cùng kết quả đã biết, không phát thêm quyền. Nếu giao dịch bị hủy trước bước 8, kết quả provider không được tự mở lại giao dịch.

Ví dụ này không giả định việc chụp giấy tờ luôn là phương án tốt nhất. Nếu Lan còn authenticator phù hợp hoặc có một tổ hợp recovery đã đăng ký đáp ứng policy, có thể dùng nhánh đó thay cho việc thu thập thêm dữ liệu danh tính.

## 14. Những sai lầm cần tránh

| Sai lầm | Hậu quả | Cách thiết kế |
| --- | --- | --- |
| Browser redirect thành công thì bỏ MFA | Client có thể sửa hoặc phát lại URL | Dùng kết quả server đã kiểm chứng và policy recovery |
| Provider PASSED thì tài khoản thuộc người gửi | Nối danh tính thật vào sai tài khoản | Đối chiếu với danh tính lịch sử đáng tin |
| Một boolean verified cho mọi cấu hình | Kiểm tra bị bỏ qua vẫn trông như đầy đủ | Giữ profile, cấu hình và kết quả từng phép kiểm tra |
| Chỉ biết providerSessionId | Dùng nhầm môi trường hoặc project | Ràng buộc đầy đủ provider scope |
| Tin metadata do client khai | Chuyển kết quả sang tài khoản nạn nhân | Mapping do backend tạo và kiểm soát |
| Có chữ ký webhook là đủ | Replay có thể tạo nhiều lần cấp quyền | Chống trùng event và idempotency ở evidence, grant |
| Event đến sau luôn là trạng thái mới | Ghi đè sai do thứ tự giao hàng | Dùng version hoặc cơ chế đối soát phù hợp |
| Timeout kỹ thuật là không đạt danh tính | Gây khóa và yêu cầu thử lại không cần thiết | Tách lỗi kỹ thuật với kết quả kiểm chứng |
| Provider lỗi thì bỏ qua kiểm tra | Tạo đường recovery yếu trong lúc sự cố | Chờ hoặc dùng phương án tương đương đã duyệt |
| Support có nút mở khóa không lưu căn cứ | Social engineering vượt qua toàn bộ luồng | Xét duyệt qua evidence, policy và thẩm quyền |
| Lưu mọi ảnh, video trong log | Mở rộng phạm vi lộ dữ liệu | Tối thiểu hóa, phân quyền, lưu giữ và xóa có kiểm soát |
| Tạo passkey mới là kết thúc mọi hạn chế | Người chiếm recovery nhận toàn quyền | Giữ chuỗi cấp quyền và xử lý session sau recovery |

Giá trị của một identity proofing provider nằm ở bằng chứng mà quy trình của họ tạo ra và khả năng ứng dụng kiểm tra, ràng buộc, sử dụng bằng chứng đó đúng mục đích. Để giảm chiếm đoạt tài khoản, hệ thống phải giữ quyền quyết định recovery ở policy của mình, với liên kết danh tính lịch sử và phạm vi cấp quyền có thể giải thích được.
