# Data protection obligations

## 1. Bảo vệ dữ liệu là một phần của account recovery

Trong module `SECURITY_AUTHENTICATION_ACCOUNT_RECOVERY`, hệ thống khôi phục tài khoản phải xử lý thông tin để biết ai đang yêu cầu lấy lại quyền truy cập khi mất mật khẩu, MFA, passkey hoặc thiết bị xác thực. Chính luồng này có thể tập trung email, số điện thoại, lịch sử thiết bị, bằng chứng xác minh, hồ sơ hỗ trợ và thông tin về sự cố tài khoản.

Nếu thiết kế chỉ chú ý token một lần và chống brute force, dữ liệu có thể vẫn bị lộ qua ticket hỗ trợ, URL, log, bản sao ở nhà cung cấp hoặc file export. Một quy trình xác minh danh tính rất mạnh cũng có thể tạo rủi ro lớn nếu giữ ảnh giấy tờ vô thời hạn hoặc cho mọi nhân viên xem toàn bộ hồ sơ.

Data protection obligations là những nghĩa vụ cần xác định cho việc thu thập, sử dụng, lưu giữ, chia sẻ và xử lý sự cố dữ liệu. Công việc kỹ thuật là chuyển các nghĩa vụ áp dụng thành policy, quyền truy cập, vòng đời dữ liệu và bằng chứng có thể kiểm tra.

Bài học dùng các nguồn pháp lý chính thức để nêu ví dụ, rồi xây dựng mô hình kỹ thuật cho recovery. Các schema, interface và policy reference là minh họa; chúng không xác định thay tổ chức bộ luật, căn cứ xử lý hay thời hạn phải dùng cho một triển khai cụ thể.

## 2. Xác định nghĩa vụ áp dụng trước khi chọn biện pháp

Ngôn ngữ giao diện, quốc tịch của developer hoặc vị trí một database không tự quyết định toàn bộ phạm vi pháp luật. Cần xem tổ chức, nơi cung cấp dịch vụ, người có dữ liệu, hoạt động xử lý, ngành và luồng chuyển dữ liệu.

GDPR là một ví dụ có phạm vi tại Điều 3; không mặc định mọi dịch vụ viết bằng tiếng Việt đều thuộc hoặc đều nằm ngoài phạm vi đó. Việc xử lý thuộc GDPR cần một căn cứ phù hợp theo Điều 6 và tuân các nguyên tắc tại Điều 5. [GDPR — Articles 3, 5 và 6, EUR-Lex](https://eur-lex.europa.eu/eli/reg/2016/679/oj/eng).

Khi đánh giá triển khai tại Việt Nam, nguồn cần đối chiếu gồm Luật Bảo vệ dữ liệu cá nhân số 91/2025/QH15 và Nghị định 356/2025/NĐ-CP. Cổng Chính phủ ghi ngày có hiệu lực của cả hai là 01/01/2026. Mốc đối chiếu nguồn trong bài là 24/11/2026; triển khai cần kiểm tra nội dung, phạm vi, chuyển tiếp và văn bản liên quan tại thời điểm áp dụng. [Luật 91/2025/QH15](https://chinhphu.vn/?docid=214590&pageid=27160), [Nghị định 356/2025/NĐ-CP](https://chinhphu.vn/?docid=216387&pageid=27160).

Không lấy một quy tắc trong ví dụ GDPR rồi tự gán thành nghĩa vụ Việt Nam hoặc nghĩa vụ toàn cầu. Cũng không giữ nguyên một checklist pháp lý cũ mà không có người chịu trách nhiệm cập nhật.

### 2.1. Tạo hồ sơ nghĩa vụ theo phạm vi

Một hồ sơ thiết kế có thể gồm:

| Thành phần | Nội dung cần ghi |
| --- | --- |
| Processing scope | Luồng recovery, nhóm người dùng, tenant, môi trường |
| Applicable rules | Nguồn pháp lý, hợp đồng và policy áp dụng, phiên bản kiểm tra |
| Organisational role | Bên quyết định xử lý, bên xử lý theo chỉ dẫn và các bên liên quan |
| Purposes | Khôi phục quyền, chống lạm dụng, hỗ trợ, điều tra sự cố |
| Data categories | Dữ liệu liên hệ, proof, thiết bị, log, hồ sơ hỗ trợ |
| Conditions | Căn cứ xử lý, yêu cầu bổ sung, giới hạn hoặc ngoại lệ đã xác định |
| Lifecycle | Điều kiện thu thập, hết mục đích, lưu giữ, xóa và giới hạn sử dụng |
| Recipients | Provider, support team, đơn vị liên quan và luồng truy cập |
| Evidence | Quyết định, kiểm soát, test, log vận hành và hồ sơ phê duyệt |
| Owner and review | Người chịu trách nhiệm, ngày rà soát và trigger cập nhật |

Hồ sơ này là đầu vào để đội kỹ thuật thực thi. Nó không phải một file “đồng ý điều khoản” do người dùng tick để hợp thức hóa mọi xử lý.

### 2.2. Phân biệt luật, hợp đồng và biện pháp kỹ thuật

Một nghĩa vụ có thể yêu cầu mức bảo vệ phù hợp nhưng không chỉ định chính xác tên bảng, thuật toán queue hay TTL của ứng dụng. Đội kỹ thuật phải chọn biện pháp có thể chứng minh đáp ứng mục tiêu trong bối cảnh đó.

Ngược lại, việc dùng mã hóa, HMAC hoặc có một audit table không tự chứng minh căn cứ thu thập, thời hạn lưu giữ và quyền chia sẻ đã đúng.

Mỗi biện pháp nên liên kết tới mục tiêu, policy và bằng chứng. Tránh một bảng chỉ có cột “GDPR compliant = true” cho toàn bộ recovery service.

## 3. Lập bản đồ dữ liệu theo từng bước recovery

Trước khi bàn retention hoặc quyền truy cập, cần biết dữ liệu đi đâu. Không chỉ kiểm kê database chính.

```text
Caller
  -> Recovery API
  -> Account/challenge store
  -> Notification outbox -> Email/SMS provider
  -> Risk service
  -> Identity verification provider, nếu luồng sử dụng
  -> Support case/evidence store
  -> Audit, logs, traces, metrics
  -> Export, backup, archive và môi trường hỗ trợ
```

Một request có thể không dùng mọi đích. Sơ đồ giúp đặt câu hỏi về từng luồng thật, không phải yêu cầu bổ sung provider hoặc thu thập thêm bằng chứng.

| Giai đoạn | Dữ liệu có thể xuất hiện | Rủi ro cần xem |
| --- | --- | --- |
| Khởi tạo | Email/phone, tenant, request metadata | Enumeration, log định danh đầy đủ, spam |
| Tạo challenge | Token digest, purpose, expiry, generation | Lộ capability, sai binding, giữ quá lâu |
| Gửi thông báo | Recipient, template, nội dung, provider reference | Provider lưu payload, gửi nhầm recipient |
| Đánh giá rủi ro | IP, device signal, hành vi và quyết định | Thu thập quá mức, liên kết dữ liệu ngoài mục đích |
| Xác minh nâng cao | Reference bằng chứng, kết quả, tài liệu nếu cần | Bản sao giấy tờ, quyền truy cập, dữ liệu nhạy cảm |
| Hỗ trợ thủ công | Actor, ghi chú, attachment, approval | Dán secret vào ticket, xem chéo tenant |
| Hoàn tất | Credential/security version, session actions | Audit thiếu hoặc lộ token/session |
| Sau kết thúc | Outcome, hồ sơ dispute, backup | Giữ toàn bộ raw proof dù mục đích đã hết |

### 3.1. Định danh giả danh vẫn có thể liên kết

Account ID, device ID, token fingerprint hoặc một email được băm có thể vẫn gắn lại được với người dùng qua dữ liệu khác. Đừng coi mọi chuỗi không đọc được bằng mắt là đã ẩn danh.

Một hash không khóa của email phổ biến có thể bị đối chiếu bằng danh sách ứng viên. HMAC có thể giảm một số đường đoán khi quản lý khóa phù hợp, nhưng hệ thống nắm khóa và dữ liệu liên kết vẫn có khả năng nhận diện theo thiết kế.

Vì vậy classification, quyền truy cập và retention cần dựa trên khả năng liên kết và bối cảnh, không chỉ trên tên cột `anonymousId`.

### 3.2. Bí mật xác thực cần kiểm soát riêng

Token recovery, OTP, recovery code, TOTP seed, cookie và private key có thể trực tiếp cấp quyền hoặc hỗ trợ chiếm tài khoản. Chúng không nên được xử lý như thông tin liên hệ thông thường.

Chỉ lưu dạng cần thiết cho thiết kế xác minh. Ví dụ một high-entropy token có thể được đối chiếu bằng digest; OTP không gian nhỏ cần thêm kiểm soát chống đoán và bảo vệ dữ liệu thích hợp. Không suy rằng “đã băm” luôn đủ để bảo vệ mọi loại secret.

Raw secret có thể chỉ cần xuất hiện tại thời điểm tạo và chuyển tới đúng nơi dùng. Không sao chép nó vào log, event cho nhiều consumer, bản report hay ticket để thuận tiện debug.

## 4. Mục đích và căn cứ xử lý phải gắn với từng hoạt động

Khôi phục account, chống fraud, phân tích chất lượng và marketing là những mục đích khác nhau. Một tập dữ liệu được thu để xác minh recovery không mặc định được dùng để huấn luyện mô hình, quảng cáo hoặc đánh giá hành vi ngoài phạm vi đã xác định.

Trong ví dụ GDPR, consent là một trong những căn cứ tại Điều 6, không phải căn cứ duy nhất. Việc chọn căn cứ cần xét đúng hoạt động và điều kiện áp dụng; không tự gán mọi xử lý liên quan bảo mật là “legitimate interests” hoặc “necessary for contract”. [GDPR — Article 6](https://eur-lex.europa.eu/eli/reg/2016/679/oj/eng).

Một bảng thiết kế minh họa:

| Hoạt động | Mục đích cụ thể | Câu hỏi cần có quyết định |
| --- | --- | --- |
| Gửi link khôi phục | Chuyển quyền proof cho kênh phù hợp | Dữ liệu nào thực sự cần để gửi? |
| Giới hạn lạm dụng | Ngăn đoán mã/spam và bảo vệ tài khoản | Tín hiệu nào cần, lưu trong bao lâu? |
| Xem tài liệu xác minh | Đánh giá proof cho ca rủi ro cao | Có cần tài liệu thô, ai được xem? |
| Ghi audit đổi factor | Chứng minh ai làm gì và hỗ trợ điều tra | Những field nào đủ để tái dựng? |
| Phân tích sản phẩm | Đo tỷ lệ hoàn tất và lỗi luồng | Có thể dùng dữ liệu tổng hợp hoặc giảm liên kết không? |
| Dùng dữ liệu cho mục đích mới | Mục đích mới phải được xác định riêng | Có tương thích, cần thông báo/căn cứ bổ sung gì? |

Đừng viết một purpose chung “cải thiện dịch vụ” rồi gắn mọi bản sao dữ liệu vào đó. Đội triển khai cần đủ chi tiết để quyết định có cho một job, một provider hoặc một nhân viên truy cập hay không.

### 4.1. Dữ liệu xác minh có mức rủi ro cao

Nếu luồng dùng ảnh giấy tờ, selfie, kết quả đối chiếu khuôn mặt hoặc dữ liệu liên quan trẻ em, cần đánh giá phân loại và điều kiện áp dụng tương ứng. Không gộp “ảnh” và “biometric template” thành cùng một loại chỉ vì chúng nằm chung request.

Trong GDPR, dữ liệu sinh trắc học dùng để nhận diện duy nhất một người có điều kiện riêng tại Điều 9. Một checkbox consent chung không tự giải quyết mọi điều kiện đó. [GDPR — Article 9](https://eur-lex.europa.eu/eli/reg/2016/679/oj/eng).

Đây cũng là một trigger để xem có cần đánh giá tác động và sự tham gia của owner bảo vệ dữ liệu theo phạm vi áp dụng. Không tự kết luận mọi hệ thống recovery đều bắt buộc cùng một loại hồ sơ đánh giá, cũng không bỏ qua đánh giá chỉ vì đây là tính năng phụ.

## 5. Tối thiểu hóa dữ liệu và minh bạch trong giao diện

Thiết kế nên bắt đầu bằng câu hỏi “đủ để quyết định quyền gì?” thay vì “có thể thu thêm gì để yên tâm?”.

Một luồng người dùng còn passkey hợp lệ có thể không cần ảnh giấy tờ để thay mật khẩu. Một ca mất tất cả factor có thể cần proof khác, nhưng dữ liệu bổ sung nên được yêu cầu theo bước và mục đích rõ.

### 5.1. Thu theo tầng và chỉ giữ thứ cần

- Bắt đầu bằng định danh cần thiết cho đúng tenant/luồng.
- Dùng những proof đã đăng ký và còn đáng tin khi phù hợp.
- Chỉ mở bước xác minh bổ sung khi policy yêu cầu.
- Ưu tiên kết quả/reference từ provider nếu đáp ứng mục tiêu, thay vì luôn sao chép hồ sơ thô.
- Giới hạn attachment tự do và hướng dẫn người dùng không gửi password, OTP hay recovery code vào ticket.

Reference hoặc kết quả provider vẫn cần được bảo vệ; việc không giữ raw document không tự làm toàn bộ xử lý hết rủi ro.

Khi một field là bắt buộc, giao diện cần cho biết mục đích và tác động nếu không cung cấp, theo notice/policy đã xác định. Không tạo cảm giác người dùng phải chia sẻ thêm dữ liệu không cần cho recovery mới lấy lại được account.

### 5.2. Notice và anti-enumeration là hai lớp

Thông báo về xử lý dữ liệu cần rõ, dễ hiểu và tiếp cận được. Phản hồi công khai của endpoint vẫn phải tránh tiết lộ account tồn tại hoặc kênh bí mật trái thiết kế.

Có thể có một notice chung giải thích cách xử lý recovery mà không xác nhận ai đang có account. Khi người dùng đã vào một ngữ cảnh được xác thực phù hợp, có thể cung cấp thông tin chi tiết theo quyền.

Không trộn thông báo bảo mật với marketing. Cơ chế opt-out marketing cũng không nên vô tình làm mất mọi cảnh báo bảo vệ tài khoản cần gửi theo policy đã được xác định.

### 5.3. Tài liệu chính sách phải khớp hành vi thật

Nếu notice nói hồ sơ xác minh được xóa sau khi hết mục đích, nhưng provider giữ ảnh để sử dụng riêng hoặc support export vẫn còn bản sao, thiết kế đang có sự lệch cần xử lý.

Liên kết phiên bản notice/policy với thay đổi schema, provider và mục đích xử lý. Không chỉ cập nhật trang văn bản rồi để pipeline dữ liệu chạy theo quy tắc cũ.

## 6. Phân quyền, bảo mật và bằng chứng thực thi

EDPB giải thích rằng mức bảo vệ dữ liệu cần phù hợp với rủi ro và bối cảnh, bao gồm biện pháp kỹ thuật lẫn tổ chức. Bảo mật dữ liệu không chỉ là chống đọc trộm mà còn liên quan tính toàn vẹn và khả dụng. [EDPB — Secure personal data](https://www.edpb.europa.eu/sme/be-compliant/secure-personal-data_en).

Trong recovery, một thiết kế minh họa có thể tách các quyền:

| Vai trò hoặc thành phần | Dữ liệu/quyền cần thiết | Quyền không nên tự suy ra |
| --- | --- | --- |
| Notification worker | Recipient và payload được duyệt để gửi | Xem toàn bộ hồ sơ định danh |
| Risk service | Tín hiệu cần cho policy đánh giá | Dùng raw evidence cho mục đích khác |
| Support viewer | Metadata ca hỗ trợ đã che bớt | Tải ảnh giấy tờ hoặc reset factor |
| Evidence reviewer | Proof của ca được giao | Duyệt mọi tenant hoặc tự cấp quyền admin |
| Recovery executor | Outcome/authorization hợp lệ | Chấp nhận lời khai verified từ client |
| Audit reader | Event được phân loại theo quyền | Lấy raw token/session từ log |
| Privacy operations | Xử lý yêu cầu dữ liệu theo scope | Tự thay factor hoặc cấp session |

Scope cần bao gồm tenant, account/case, action và thời gian khi phù hợp. Role tên “support” chưa đủ để xác định mọi quyền.

### 6.1. Bảo vệ dữ liệu ở từng nơi xuất hiện

Sử dụng transport được bảo vệ, mã hóa lưu trữ và quản lý khóa phù hợp với threat model. Giới hạn truy cập ứng dụng vẫn cần thiết vì dữ liệu có thể bị lộ qua một tài khoản được quyền giải mã.

Thiết lập quyền upload/download, thời hạn access link, kiểm tra content và luồng quét file nếu có attachment. Một signed URL còn sống trong chat hỗ trợ có thể cho người ngoài đọc tài liệu dù database có kiểm soát rất tốt.

Không đặt recovery token hay ảnh giấy tờ vào URL được analytics, reverse proxy hoặc referrer thu thập ngoài ý muốn. Xem log ở gateway và provider chứ không chỉ controller.

### 6.2. Audit cần đủ nhưng không thành bản sao bí mật

Một audit event có thể chứa actor reference, subject reference, purpose, action, timestamp, outcome, policy version và operation reference. Cần quyết định field nào được phép và cách che bớt.

Không dump toàn bộ request body khi verify thất bại. Một error path hiếm vẫn có thể lộ OTP, token hoặc tài liệu vào hệ thống log có phạm vi người đọc rộng hơn evidence store.

Audit về việc đọc evidence cũng cần được quan sát. Người có quyền xem một tài liệu không đồng nghĩa được tải hàng loạt hồ sơ mà không có dấu vết.

## 7. Lưu giữ, xóa và các thời hạn không giống nhau

Ít nhất có ba vòng đời cần phân biệt:

```text
Hiệu lực của quyền:
  token/challenge còn được dùng để cấp quyền tới khi nào?

Thời gian cần dữ liệu cho mục đích:
  raw evidence hoặc recipient còn cần để xử lý ca recovery không?

Thời gian giữ bằng chứng:
  metadata tối thiểu nào cần cho audit, dispute hoặc nghĩa vụ đã xác định?
```

Token hết hạn không tự xóa mọi bản sao recipient và log. Xóa raw document không nhất thiết đòi xóa mọi dấu operation. Ngược lại, nhu cầu audit không tự cho phép giữ nguyên raw secret hoặc hồ sơ giấy tờ mãi mãi.

Không có một con số retention chung cho mọi recovery module. Cần một policy cho từng loại dữ liệu, sự kiện bắt đầu tính, mục đích, nguồn nghĩa vụ và các điều kiện giữ lại đã được xác định.

### 7.1. Bảng retention minh họa không ấn định số ngày

| Data class | Trigger đánh giá vòng đời | Hướng xử lý cần thiết kế |
| --- | --- | --- |
| Recovery capability/digest | Hết hạn, tiêu thụ, thu hồi | Chặn quyền ngay; dọn dữ liệu theo policy riêng |
| Challenge state | Ca đóng hoặc mất hiệu lực | Giữ tối thiểu cần cho vòng đời và chống replay |
| Raw verification document | Mục đích xử lý bằng chứng đã kết thúc | Xóa hoặc giữ có căn cứ cụ thể theo quyết định |
| Verification result/reference | Kết thúc recovery và thời gian theo policy | Giảm dữ liệu, giới hạn mục đích và truy cập |
| Notification payload | Submit/delivery đã kết thúc | Không giữ raw capability để phục vụ log |
| Security audit | Theo lịch lưu giữ đã phê duyệt | Bảo vệ toàn vẹn, giới hạn sử dụng và dọn đúng hạn |
| Support export | Hết mục đích của bản xuất | Thu hồi link và xóa bản sao theo phạm vi |
| Backup | Theo vòng đời backup và phương án restore | Không đưa dữ liệu đã xóa trở lại sử dụng trái policy |

Các trạng thái giữ phục vụ tranh chấp hoặc nghĩa vụ cần có thẩm quyền, scope và review. Một field `legalHold=true` do bất kỳ service nào đặt không tự tạo một căn cứ giữ dữ liệu hợp lệ.

### 7.2. Xóa phải theo toàn bộ bản sao

Đánh giá primary store, replica, search index, object storage, cache, log archive, dead-letter queue, support attachment, export và provider. Chỉ xóa một hàng database chính chưa phải bằng chứng dữ liệu đã được xử lý ở mọi đích.

Trong backup không hỗ trợ xóa ngay từng bản ghi, thiết kế cần giới hạn truy cập, vòng đời và quy trình restore phù hợp với nghĩa vụ đã xác định. Không hứa “đã xóa mọi bản sao” nếu còn bản phục hồi chưa được quản lý.

Một deletion ledger hoặc tombstone tối thiểu có thể giúp tránh tái nhập dữ liệu đã xóa khi restore. Chính ledger cũng cần được phân loại, giới hạn thông tin và có policy riêng.

### 7.3. Không đánh đồng vô hiệu hóa quyền với xóa dữ liệu

Nếu người dùng yêu cầu xóa dữ liệu, việc xóa bằng chứng xử lý không được làm token cũ trở lại sử dụng được do mất trạng thái revoked/consumed. Cần thiết kế validator và retention sao cho dọn dữ liệu không mở lại quyền.

Ví dụ khi không tìm thấy challenge record, không tự coi token có chữ ký hợp lệ là đủ để tiếp tục nếu hợp đồng cần trạng thái server. Những bản test xóa/restore phải kiểm tra cả tính riêng tư và bất biến cấp quyền.

## 8. Nhà cung cấp, vai trò xử lý và chuyển dữ liệu

Một provider email/SMS, xác minh danh tính hoặc hệ thống support có thể nhận dữ liệu recovery dù database ứng dụng nằm trong hạ tầng riêng.

Trong ví dụ GDPR, controller quyết định mục đích và phương tiện xử lý; processor xử lý thay mặt controller theo chỉ dẫn. Vai trò được xác định theo hoạt động thực tế, không chỉ tên sản phẩm hoặc nhãn trong hợp đồng. [EDPB — Data controller or data processor](https://www.edpb.europa.eu/sme/learn-the-basics/data-controller-or-data-processor_en).

Một nền tảng nhiều tenant cần xem vai trò trong từng hoạt động. Cùng một doanh nghiệp có thể xử lý theo chỉ dẫn cho dữ liệu khách hàng ở một luồng, nhưng tự quyết định một mục đích riêng ở luồng khác; cần đánh giá thay vì gán một nhãn cho mọi dữ liệu.

### 8.1. Hồ sơ provider cần trả lời được gì?

| Chủ đề | Câu hỏi thiết kế/vận hành |
| --- | --- |
| Payload | Provider nhận field nào, có raw secret/document không? |
| Purpose | Dùng để giao tin/xác minh hay có mục đích riêng khác? |
| Retention | Những bản nào được giữ, trigger và quy trình xóa là gì? |
| Access | Nhân sự, service và sub-provider nào có thể xem? |
| Locations | Nơi lưu, nơi xử lý và nơi có thể truy cập từ xa? |
| Incidents | Cách thông báo, dữ kiện cung cấp, đầu mối và hợp đồng? |
| Rights requests | Cách tìm, xuất, sửa hoặc xóa đúng subject? |
| End of service | Cách trả/xóa dữ liệu, xử lý backup và quyền còn tồn tại? |
| Evidence | Báo cáo, log và cách kiểm tra nghĩa vụ được thực thi? |

Trong quan hệ controller-processor thuộc GDPR, nội dung xử lý và trách nhiệm cần được ràng buộc bằng hợp đồng thích hợp; việc dùng sub-processor cũng có điều kiện riêng. [EDPB — Controller-processor responsibilities](https://www.edpb.europa.eu/sme/learn-the-basics/data-controller-or-data-processor_en).

Một chứng chỉ bảo mật của vendor là thông tin hữu ích nhưng không tự trả lời tất cả câu hỏi trên cho payload và cấu hình cụ thể đang dùng. Cần xem cả cài đặt lưu message body, attachment, debug và quyền support của tài khoản dịch vụ.

### 8.2. Dữ liệu ra ngoài khu vực áp dụng

Đối với xử lý thuộc GDPR, chuyển hoặc làm dữ liệu sẵn có cho một tổ chức khác ngoài EEA có thể thuộc quy tắc chuyển dữ liệu quốc tế khi đáp ứng các tiêu chí tương ứng. Cần đánh giá điều kiện Chương V; mã hóa không tự loại bỏ việc đánh giá transfer. [EDPB — International data transfers](https://www.edpb.europa.eu/sme/be-compliant/international-data-transfers_en).

Trong kiến trúc recovery, hãy kiểm kê cả backup, log platform, provider failover và việc một đội hỗ trợ ở nơi khác truy cập dữ liệu. Không kết luận chỉ từ region của database chính.

Các nghĩa vụ về chuyển dữ liệu ở phạm vi khác phải được đánh giá theo nguồn áp dụng của phạm vi đó. Không dùng một cơ chế hợp đồng EU như lời khẳng định tự động đáp ứng mọi yêu cầu tại Việt Nam hay quốc gia khác.

### 8.3. Failover cũng là thay đổi luồng dữ liệu

Nếu provider A lỗi rồi tự chuyển sang B, recipient, nội dung và evidence có thể đi tới một bên mới hoặc một nơi mới. Đây là thay đổi cần nằm trong thiết kế đã xét, không chỉ một lựa chọn resilience của SDK.

Policy và cấu hình nên xác định provider nào được phép cho data class/tenant nào. Một tuyến dự phòng không phù hợp không được tự mở chỉ vì hàng đợi đang dài.

## 9. Quyền của người có dữ liệu và recovery là hai quy trình

Yêu cầu lấy lại account và yêu cầu tiếp cận/xóa dữ liệu có thể đến từ cùng người, nhưng mục tiêu và quyền được cấp khác nhau. Hoàn tất một yêu cầu dữ liệu không được tự đổi password, reset MFA hoặc cấp session đăng nhập.

Trong ví dụ GDPR, các quyền có điều kiện và giới hạn riêng. EDPB hướng dẫn xử lý yêu cầu, bao gồm việc có thể yêu cầu thông tin bổ sung khi có nghi ngờ hợp lý về danh tính, và việc bảo vệ quyền của người khác khi cung cấp dữ liệu. [EDPB — Respect individuals’ rights](https://www.edpb.europa.eu/sme/be-compliant/respect-individuals-rights_en).

### 9.1. Xác minh người yêu cầu một cách tương xứng

Không gửi toàn bộ hồ sơ recovery tới một email mới chỉ vì caller nói mailbox cũ bị mất. Cũng không tạo vòng lặp yêu cầu người dùng phải đăng nhập bằng factor họ đã báo mất mới được gửi yêu cầu dữ liệu.

Thiết kế một đường xử lý thay thế phù hợp với rủi ro, dữ liệu sẽ cung cấp và policy áp dụng. Giữ bằng chứng về cách xác minh mà không thu thêm hồ sơ thô vượt nhu cầu.

Quyền xem ticket, quyền yêu cầu thay dữ liệu và quyền nhận một bản export không nên được suy ra chỉ từ một link hỗ trợ không có scope.

### 9.2. Nội dung trả lời và giới hạn sử dụng

Một package trả dữ liệu nên được chuẩn bị theo quyết định về phạm vi và các điều kiện áp dụng, không phải dump mọi bảng liên quan account. Xem xét dữ liệu của actor hỗ trợ, người khác, anti-abuse signal và những phần cần xử lý riêng.

Không tạo lại raw recovery token hoặc recovery code chỉ để đưa vào bản export. Nếu hệ thống không còn giữ raw secret, một API export không nên phát một capability mới dưới danh nghĩa “bản sao dữ liệu”.

Trường hợp cần cân nhắc giới hạn cung cấp thông tin phải được quyết định dựa trên quy định áp dụng và dữ kiện cụ thể. Không dùng một quy tắc blanket “dữ liệu bảo mật thì luôn loại khỏi mọi quyền tiếp cận”.

### 9.3. Sửa dữ liệu không đồng nghĩa chứng minh kênh mới

Nếu người dùng yêu cầu chỉnh một số điện thoại sai, luồng dữ liệu và luồng binding factor vẫn cần phối hợp đúng. Việc ghi nhận yêu cầu sửa chưa tự xác nhận người gọi sở hữu số mới.

Một thay đổi contact có thể tác động cả notification, recovery và MFA. Cần kiểm tra mục đích từng binding, hiệu lực proof và cách xử lý dữ liệu lịch sử; không cập nhật một field chung rồi vô tình chuyển mọi quyền tới kênh chưa xác minh.

### 9.4. Xóa dữ liệu và phần cần giữ lại

Theo ví dụ GDPR, quyền xóa không tuyệt đối; có các trường hợp và ngoại lệ cần đánh giá, chẳng hạn nghĩa vụ pháp lý hoặc yêu cầu pháp lý liên quan. [EDPB — Right to erasure](https://www.edpb.europa.eu/sme/be-compliant/respect-individuals-rights_en).

Nếu có phần tiếp tục giữ, ghi rõ phạm vi, mục đích, điều kiện và quyền truy cập. Không giữ toàn bộ hồ sơ chỉ vì một metadata field cần cho dispute. Cũng không xóa bừa dữ liệu cần để duy trì việc thu hồi token hoặc ngăn lạm dụng.

Thời hạn trả lời yêu cầu, cách thông báo và cơ chế khiếu nại cần nằm trong hồ sơ nghĩa vụ của phạm vi tương ứng. Đừng đưa một thời hạn mẫu của pháp luật khác thành hằng số cho mọi tenant.

## 10. Vi phạm dữ liệu và thông báo sự cố

Một sự cố recovery có thể làm lộ thông tin, làm dữ liệu bị thay sai hoặc khiến dữ liệu không còn truy cập được. Cần đánh giá tác động lên dữ liệu cá nhân, không chỉ hỏi có ai tải được file ra ngoài hay chưa.

Tách ít nhất ba loại quyết định:

| Loại quyết định | Mục đích | Đầu ra cần theo dõi |
| --- | --- | --- |
| Containment bảo mật | Chặn token, factor, session hoặc đường truy cập có rủi ro | Trạng thái thu hồi và bằng chứng enforcement |
| Thông báo vận hành cho người dùng | Giúp người bị ảnh hưởng hành động đúng | Phạm vi recipient, nội dung và delivery |
| Nghĩa vụ thông báo pháp lý | Đáp ứng quy định áp dụng theo điều kiện cụ thể | Đánh giá, chủ thể nhận, thời hạn và hồ sơ gửi |

Một email “chúng tôi đã reset MFA” không tự thay thế đánh giá và thông báo vi phạm dữ liệu. Ngược lại, việc gửi thông báo chính thức cũng không làm token bị lộ tự mất hiệu lực.

### 10.1. Ví dụ thời hạn trong GDPR

Nếu GDPR áp dụng, controller phải thông báo vi phạm cho cơ quan giám sát không chậm trễ không cần thiết và, khi khả thi, trong 72 giờ kể từ lúc biết, trừ trường hợp ít có khả năng gây rủi ro cho cá nhân. Khi có khả năng gây rủi ro cao, việc thông báo cho cá nhân có điều kiện riêng; processor thông báo cho controller không chậm trễ không cần thiết. [EDPB — Data breaches](https://www.edpb.europa.eu/sme/assess-the-risks/data-breaches_en).

Mốc này không có nghĩa mọi cảnh báo kỹ thuật đều phải email mọi người trong 72 giờ. Cũng không phải một SLA toàn cầu để gán vào mọi hệ thống. Phải ghi nguồn nghĩa vụ, trigger, mức đánh giá rủi ro, chủ thể chịu trách nhiệm và ngoại lệ cụ thể.

### 10.2. Thiết kế để phản ứng kịp thời

Incident record cần lưu các mốc phát hiện, escalation, đánh giá nhận biết vi phạm và cập nhật dữ kiện. Không ghi đè một timestamp duy nhất mỗi khi người phụ trách đổi nhãn ticket.

Hệ thống nên trích xuất được những nhóm dữ liệu bị ảnh hưởng, tenant/account reference, thời gian, recipients và biện pháp đã thực hiện. Không cần dump raw secret để chứng minh rằng secret có thể đã bị lộ.

Khi dữ kiện chưa đủ, giữ trạng thái chưa rõ và cập nhật theo quy trình. Không trì hoãn mọi trao đổi tới lúc có một báo cáo forensic hoàn hảo nếu nghĩa vụ áp dụng yêu cầu hành động sớm hơn.

Nội dung thông báo cần đúng mức chắc chắn, có hướng dẫn tin cậy và không mở thêm đường phishing. Không gửi token mới tới một kênh vừa bị attacker thay trong sự cố mà chưa xác minh.

## 11. Đánh giá tác động khi thay đổi luồng recovery

Thêm một nhà cung cấp, dùng đối chiếu khuôn mặt, kéo dài retention hoặc đưa risk signal vào mô hình mới đều có thể thay đổi rủi ro và nghĩa vụ cần đánh giá.

Một thay đổi nhỏ trong code có thể lớn trong dữ liệu. Ví dụ thêm trường `evidenceUrl` vào event chung có thể làm tài liệu xuất hiện ở nhiều consumer, log và dead-letter queue.

### 11.1. Trigger để rà soát

| Thay đổi | Những câu hỏi cần mở lại |
| --- | --- |
| Thêm proof hoặc raw document | Có cần dữ liệu đó, điều kiện xử lý, access và retention? |
| Thêm face matching | Dữ liệu và mục đích được phân loại thế nào, cần đánh giá gì? |
| Thêm provider/sub-provider | Vai trò, chỉ dẫn, vị trí, xóa và incident terms? |
| Thêm telemetry | Có định danh, secret hoặc khả năng liên kết mới không? |
| Dùng dữ liệu cho analytics/AI | Mục đích, căn cứ và notice đã bao phủ chưa? |
| Thêm automated denial | Có tác động tới quyền/lợi ích cần đánh giá hoặc cơ chế xem xét không? |
| Phục vụ nhóm người dùng mới | Có yêu cầu riêng theo tuổi, ngành hoặc phạm vi không? |
| Thay retention/backup | Lý do, bản sao hiện có, restore và phương án chuyển tiếp? |

Không mặc định mọi thay đổi đều cần cùng một biểu mẫu. Cần một quy trình phân loại để biết ai xem xét, khi nào cần đánh giá sâu hơn và bằng chứng nào đủ để triển khai.

### 11.2. Privacy trong môi trường phát triển

Dùng dữ liệu tổng hợp hoặc dữ liệu test được kiểm soát. Che email trong một bản dump chưa làm seed, session, IP, thiết bị và lịch sử hỗ trợ còn lại trở nên an toàn.

Một prompt gửi raw ticket tới một công cụ AI cũng là một luồng dữ liệu cần được đánh giá. Không cho rằng “chỉ dùng nội bộ để debug” tự loại bỏ vấn đề provider, mục đích hoặc quyền truy cập.

Bản chụp màn hình, video hỗ trợ và artifact CI có thể chứa dữ liệu tương tự log. Cấu hình retention và quyền cho chúng, không chỉ cho database ứng dụng.

## 12. Chuyển nghĩa vụ thành contract kỹ thuật

Có thể tổ chức một policy profile do các owner liên quan phê duyệt, rồi để service thực thi theo reference và version. Một mô hình minh họa:

```yaml
profileRef: recovery-data-policy-test-v1
processingScopeRef: scope-test-a
approvedPurposeRefs:
  - account-recovery
  - scoped-abuse-prevention
dataClasses:
  verification-document:
    ownerRef: evidence-policy-owner
    retentionRuleRef: approved-document-rule
    accessPolicyRef: assigned-reviewer-only
    disposalTargetsRef: approved-evidence-targets
  recovery-audit:
    ownerRef: security-audit-owner
    retentionRuleRef: approved-audit-rule
    accessPolicyRef: scoped-audit-reader
providerRoutesRef: approved-recovery-provider-routes
rightsWorkflowRef: approved-data-request-workflow
incidentWorkflowRef: approved-data-incident-workflow
```

Schema này không tự xác định luật áp dụng và không phải một policy production đề xuất. Reference chỉ có giá trị khi trỏ tới quyết định có nội dung, owner, phiên bản và scope rõ.

### 12.1. Trạng thái dọn dữ liệu cần phản ánh từng đích

Một disposal operation có thể theo dõi:

```text
PLANNED
  -> ELIGIBILITY_CHECKED
  -> LOCAL_DISPOSAL_APPLIED
  -> REMOTE_TARGETS_PENDING
  -> TARGET_RESULTS_VERIFIED
  -> COMPLETED hoặc REVIEW_REQUIRED
```

Kết quả `requested` ở provider không đồng nghĩa `verified`. Một API trả accepted có thể chỉ tạo job xóa. Outcome cần lưu đúng ý nghĩa và còn đường reconcile nếu response bị mất.

Điều kiện giữ lại phải được đánh giá trước khi xóa; điều kiện không rõ cần được chuyển xử lý đúng owner. Không biến một lỗi đọc policy thành “không có policy nên xóa” hoặc “giữ vĩnh viễn”.

### 12.2. Idempotency và version bảo vệ cả dữ liệu lẫn bằng chứng

Retry cùng disposal operation cần giữ scope đã duyệt. Cùng operation ID nhưng đổi target hoặc tenant là conflict cần kiểm tra.

Nếu tài liệu được thay thế bằng một version mới sau khi job cũ được tạo, job không được vô tình xóa version mới ngoài phạm vi. Dùng reference/version hoặc cơ chế tương đương mà storage hỗ trợ.

Receipt xóa nên chứa dữ liệu tối thiểu để chứng minh outcome, không sao chép chính tài liệu vừa xóa vào audit. Receipt và các reference còn liên kết được vẫn cần vòng đời và quyền truy cập riêng.

## 13. Mẫu hợp đồng kiểm thử Java

Đoạn dưới minh họa JUnit 5 cho disposal pipeline theo một policy fixture đã được phê duyệt. Đây là kiểm tra thực thi kỹ thuật của một trường hợp, không tự kết luận triển khai đã đáp ứng mọi nghĩa vụ pháp lý.

Các interface cần adapter tới hệ thống test; đoạn code chưa phải một test chạy độc lập.

```java
import java.time.Duration;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

abstract class RecoveryDataDisposalContract {
    record ArtifactRef(String tenant, String objectRef, long version) {}
    record DisposalRef(String value) {}

    interface Harness extends AutoCloseable {
        // Chỉ dùng dữ liệu tổng hợp trong namespace test.
        ArtifactRef eligibleDocumentUnderApprovedFixturePolicy();
        ArtifactRef unrelatedOtherTenantDocument();

        void makeProviderDeletionOutcomeUnknownOnce();
        DisposalRef beginDisposal(ArtifactRef artifact);
        void awaitLocalDisposal(DisposalRef operation, Duration deadline);

        boolean rawDocumentReadable(ArtifactRef artifact);
        boolean operationMarkedCompleted(DisposalRef operation);
        boolean minimalReceiptRecorded(DisposalRef operation);
        boolean receiptContainsRawDocument(DisposalRef operation);

        void reconcileProviderDeletion(DisposalRef operation);
        void awaitTargetVerification(DisposalRef operation, Duration deadline);

        @Override
        void close();
    }

    protected abstract Harness newHarness();

    @Test
    void unknownRemoteOutcomeIsNotReportedAsCompleteDisposal() {
        try (Harness h = newHarness()) {
            ArtifactRef target =
                    h.eligibleDocumentUnderApprovedFixturePolicy();
            ArtifactRef unrelated = h.unrelatedOtherTenantDocument();

            h.makeProviderDeletionOutcomeUnknownOnce();
            DisposalRef operation = h.beginDisposal(target);
            h.awaitLocalDisposal(operation, Duration.ofSeconds(5));

            assertFalse(h.rawDocumentReadable(target));
            assertTrue(h.rawDocumentReadable(unrelated));
            assertFalse(h.operationMarkedCompleted(operation));

            h.reconcileProviderDeletion(operation);
            h.awaitTargetVerification(operation, Duration.ofSeconds(10));

            assertTrue(h.operationMarkedCompleted(operation));
            assertTrue(h.minimalReceiptRecorded(operation));
            assertFalse(h.receiptContainsRawDocument(operation));
            assertTrue(h.rawDocumentReadable(unrelated));
        }
    }
}
```

Fixture cần tạo target thật sự đủ điều kiện xóa theo policy test, không dùng một API “bỏ qua mọi hold”. Probe provider phải dựa vào trạng thái được kiểm chứng theo hợp đồng, không tự ghi complete để assertion qua.

Một probe không đọc được tài liệu có thể do mất quyền hoặc outage thay vì dữ liệu đã được xóa. Harness cần phân biệt các kết quả đó và quan sát trực tiếp những storage target nằm trong phạm vi.

Test trên chưa bao phủ backup, restore, right-of-access package hay việc không còn capability cũ được sử dụng. Các mặt này cần ca riêng theo dữ liệu và kiến trúc thực tế.

## 14. Ma trận kiểm chứng cho recovery

| ID | Nội dung kiểm tra | Bằng chứng cần có |
| --- | --- | --- |
| DPO-01 | Processing scope và owner | Profile có phiên bản, nguồn và quyết định áp dụng |
| DPO-02 | Mỗi field gắn mục đích | Inventory nối field, purpose và luồng sử dụng |
| DPO-03 | Field không cần không bị thu | Test request/schema và dữ liệu lưu thực tế |
| DPO-04 | Raw secret không lọt vào log | Kiểm tra success, failure, proxy và tracing |
| DPO-05 | Support không có quyền quá rộng | Ca allow/deny theo action, case và tenant |
| DPO-06 | Signed URL/evidence download | Binding, expiry, quyền và audit đọc |
| DPO-07 | Retention chạy theo data class | Trigger, rule version và kết quả mỗi đích |
| DPO-08 | Giữ lại có scope và review | Quyết định có thẩm quyền, reason và giới hạn |
| DPO-09 | Xóa primary chưa đủ | Probe cache, index, attachment, export và provider |
| DPO-10 | Restore không hồi sinh dữ liệu/quyền sai | Diễn tập restore và đối chiếu disposition state |
| DPO-11 | Quyền dữ liệu không thành quyền login | Request/export không tạo grant hoặc session |
| DPO-12 | Người mất factor vẫn có đường yêu cầu dữ liệu | Workflow thay thế có xác minh tương xứng |
| DPO-13 | Thay contact không tự binding factor | Kiểm tra proof và purpose riêng |
| DPO-14 | Provider failover đúng route | Cấu hình theo data class/tenant và scope đã xét |
| DPO-15 | Provider/sub-provider được kiểm kê | Vai trò, hợp đồng, retention và incident workflow |
| DPO-16 | Vi phạm dữ liệu được đánh giá đúng scope | Timeline, rủi ro, quyết định thông báo và owner |
| DPO-17 | Đổi mục đích/provider/schema được rà soát | Hồ sơ change review và version policy |
| DPO-18 | CI/support/AI không có dữ liệu thật ngoài phạm vi | Dữ liệu test, quyền artifact và luồng tool |
| DPO-19 | Disposal retry không đổi scope | Operation key, target version và conflict handling |
| DPO-20 | Unknown outcome không bị báo complete | Journal, reconcile và kết quả verified |

Một control có tài liệu nhưng chưa được cấu hình hoặc kiểm thử không nên được ghi là đã vận hành. Một test thành công cũng chỉ chứng minh điều kiện của ca đó; cần liên kết bằng chứng với phạm vi chính xác.

Để tránh làm lộ dữ liệu trong chính quá trình đánh giá, dùng namespace tổng hợp, probe có quyền hạn chế và report không chứa raw secret hay tài liệu định danh thật.

## 15. Hồ sơ bàn giao và vận hành liên tục

Một bộ hồ sơ có ích nên giúp người tiếp theo trả lời được: dữ liệu nào đang xử lý, tại sao, ai quyết định, ai nhận, khi nào dọn và chứng cứ nằm ở đâu.

```text
PROCESSING_SCOPE: recovery flow and relevant tenants/groups
APPLICABLE_RULES: verified sources and review date
PURPOSE_AND_CONDITIONS: approved decision references
DATA_INVENTORY: sources, stores, copies and recipients
RETENTION_AND_DISPOSAL: per-class rules and target outcomes
ACCESS_CONTROL: roles, scopes, reviews and exceptions
VENDORS_AND_TRANSFERS: routes and approved arrangements
RIGHTS_WORKFLOW: verification, response and escalation path
INCIDENT_WORKFLOW: owner, timeline and notification decisions
EVIDENCE: actual configuration, tests and operational reports
OPEN_ITEMS: unknown, pending and review-required results
```

Không điền một nhãn compliant chung thay cho các trường chưa xác định. Nếu chưa đánh giá một provider hoặc chưa có bằng chứng cleanup backup, ghi đó là việc còn mở với owner và phạm vi tác động.

### 15.1. Cập nhật khi luật hoặc sản phẩm thay đổi

Nguồn pháp lý, hợp đồng provider và kiến trúc có thể thay đổi. Review nên được kích hoạt bởi thay đổi liên quan, không chỉ một lịch cố định.

Khi cập nhật policy, xét dữ liệu đã có: có cần dọn, hạn chế truy cập, sửa notice, thay tuyến provider hoặc đánh giá lại một mục đích cũ không? Đổi giá trị TTL cho bản ghi mới chưa chắc xử lý được backlog cũ.

Một rollout tốt có cách đối chiếu scope, chạy thử với dữ liệu tổng hợp, quan sát kết quả và xử lý ngoại lệ. Không xóa hàng loạt chỉ vì một policy parser lỗi hoặc một migration không đọc được rule cũ.

### 15.2. Những dấu hiệu cần xem lại thiết kế

Một số dấu hiệu thực tế gồm support liên tục xin thêm giấy tờ ngoài biểu mẫu, raw evidence được chuyển qua email cá nhân, cùng một secret xuất hiện ở nhiều log, disposal job luôn pending mà không owner hoặc người vận hành không biết provider đang lưu ở đâu.

Các dấu hiệu này nên mở một công việc xác định rõ nguyên nhân và phạm vi. Chỉ bổ sung một câu cảnh báo vào tài liệu mà không sửa luồng dữ liệu sẽ không giải quyết được hành vi đang tồn tại.

## 16. Tình huống và bài tập

**Tình huống A — Token hết hạn nhưng dữ liệu còn khắp nơi.** Recovery token đã hết hạn, nhưng email payload, recipient và request body còn ở queue lỗi, tracing và ticket hỗ trợ. Lập inventory, phân biệt điều kiện vô hiệu quyền với điều kiện xóa, rồi đề xuất probe cho từng bản sao.

**Tình huống B — Xác minh xong nhưng ảnh giấy tờ được giữ mãi.** Provider trả kết quả verified và ứng dụng vẫn tải mọi ảnh về support store. Xác định purpose, mức cần thiết, quyền truy cập, retention và các câu hỏi cần quyết định trước khi tiếp tục thiết kế.

**Tình huống C — Yêu cầu dữ liệu thành account takeover.** Caller nói mất email và yêu cầu export hồ sơ recovery tới một địa chỉ mới. Thiết kế cách xác minh tương xứng và scope trả dữ liệu, đồng thời chứng minh workflow không cấp quyền login hoặc chuyển factor.

**Tình huống D — Failover vượt tuyến dữ liệu đã xét.** SMS provider chính lỗi, SDK tự chuyển sang provider dự phòng chưa nằm trong profile của tenant. Xác định dữ liệu bị chuyển, các owner cần tham gia và điều kiện kỹ thuật để không tự mở tuyến ngoài phạm vi.

**Tình huống E — Nhầm thời hạn thông báo.** Đội vận hành gán hằng số 72 giờ cho mọi thông báo sự cố toàn cầu. Phân biệt cảnh báo tài khoản với nghĩa vụ thông báo pháp lý; lập bảng nguồn áp dụng, trigger, người nhận và decision owner cho từng scope.

**Tình huống F — Xóa làm mất trạng thái thu hồi.** Cleanup xóa challenge record, nhưng validator vẫn chấp nhận token có chữ ký còn hạn khi không thấy record. Mô tả vì sao điều kiện xóa dữ liệu và điều kiện cấp quyền phải được thiết kế cùng nhau, rồi viết một ca test tái hiện.

Một hệ thống recovery bảo vệ dữ liệu tốt cần nối được nghĩa vụ áp dụng với quyết định xử lý cụ thể, kiểm soát thật trong pipeline và bằng chứng vận hành. Việc thu ít hơn, giữ đúng vòng đời và chỉ cấp quyền theo proof hợp lệ phải được duy trì cả ở đường thành công, lỗi, retry và phục hồi sự cố.
