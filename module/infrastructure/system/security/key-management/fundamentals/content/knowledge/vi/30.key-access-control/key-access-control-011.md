# Break-glass key access

Trong chương **Access control cho key** của module SECURITY_KEY_MANAGEMENT_FUNDAMENTALS, bài học này giải thích cơ chế truy cập khóa khẩn cấp (break-glass key access). Cơ chế này cho phép một số người được ủy quyền thực hiện thao tác cần thiết trên key khi quy trình truy cập thông thường không khả dụng hoặc không thể đáp ứng thời gian xử lý sự cố. Vì quyền khẩn cấp có thể mở rộng khả năng giải mã, ký, khôi phục hoặc thay đổi policy, nó phải có phạm vi hẹp, thời hạn ngắn, phê duyệt phù hợp, giám sát tức thời và hậu kiểm bắt buộc.

## 1. Break-glass key access là gì?

**Break-glass key access** là quy trình cấp quyền truy cập đặc biệt, có kiểm soát và thường chỉ có hiệu lực trong thời gian ngắn để xử lý tình huống khẩn cấp liên quan tới cryptographic key. Tên gọi gợi ý một cơ chế dự phòng chỉ được sử dụng khi các lối vận hành thông thường không đáp ứng được nhu cầu khôi phục hoặc bảo vệ hệ thống.

Các tình huống có thể cần quyền khẩn cấp:

- Hệ thống quản lý danh tính hoặc quy trình cấp credential thông thường gặp sự cố, khiến operator hợp lệ không thể truy cập KMS.
- Một workload production bị lỗi và cần thao tác key để khôi phục dữ liệu hoặc dịch vụ.
- Key policy bị cấu hình sai khiến operation thiết yếu bị từ chối.
- Cần cô lập, disable hoặc thay thế key khi phát hiện compromise.
- Cần restore key backup hoặc phục hồi HSM security domain theo kế hoạch disaster recovery.
- Dịch vụ mã hóa quan trọng phải phục hồi trong khi một thành phần quản trị thông thường không khả dụng.

Break-glass không phải tài khoản superuser dùng hàng ngày, không phải cách bỏ qua mọi policy và cũng không phải quyền truy cập không giới hạn vào tất cả private key. Đây là một đường vận hành khẩn cấp đã được thiết kế, kiểm thử và giới hạn từ trước.

## 2. Vì sao cần cơ chế truy cập khẩn cấp?

Quy trình truy cập thông thường có thể phụ thuộc vào nhiều thành phần: identity provider, MFA, mạng quản trị, ticketing, approval workflow, KMS control plane, HSM operator console hoặc hệ thống cấp credential. Nếu một thành phần thiết yếu gặp sự cố, người có trách nhiệm có thể không thực hiện được thao tác phục hồi.

Không có đường khẩn cấp được chuẩn bị trước có thể dẫn tới:

- Dịch vụ mã hóa hoặc giải mã ngừng hoạt động kéo dài.
- Dữ liệu backup không thể phục hồi đúng thời hạn.
- Key bị compromise nhưng không thể disable hoặc rotate kịp thời.
- Hệ thống bị khóa ngoài ý muốn do policy sai hoặc mất quyền quản trị.
- Operator phải tìm cách không được phê duyệt để truy cập key trong lúc áp lực sự cố cao.

Một cơ chế break-glass được thiết kế tốt giúp duy trì khả năng xử lý sự cố mà vẫn giữ được trách nhiệm, dấu vết kiểm toán và giới hạn quyền.

## 3. Phân biệt break-glass identity, emergency approval và key access

Ba khái niệm có liên quan nhưng không giống nhau:

| Thành phần | Vai trò | Ví dụ |
|---|---|---|
| Break-glass identity | Danh tính dự phòng có thể xác thực khi luồng identity thông thường gặp sự cố | Emergency administrator hoặc recovery operator |
| Emergency approval | Bằng chứng người có thẩm quyền cho phép một hành động khẩn cấp | Incident commander và key owner phê duyệt |
| Break-glass key access | Quyền cụ thể được cấp để thực hiện operation trên key | Unwrap một DEK backup hoặc disable key bị compromise |

Có break-glass account không đồng nghĩa account đó tự động được quyền dùng mọi key. Sau authentication vẫn cần authorization theo key, action, purpose, incident và thời hạn. Ngược lại, có approval cũng không đủ nếu principal không được xác thực hoặc KMS/HSM không có cơ chế cấp quyền tương ứng.

## 4. Phân biệt truy cập quản trị và sử dụng key

Khẩn cấp có thể liên quan tới control plane hoặc data plane:

- **Control-plane emergency:** sửa policy, thu hồi grant, disable key, tạo key version mới hoặc điều chỉnh cấu hình KMS/HSM.
- **Data-plane emergency:** decrypt, unwrap, sign hoặc thực hiện operation mật mã cần thiết để phục hồi.

Hai nhóm quyền có tác động khác nhau. Một operator có thể cần disable key bị compromise nhưng không cần decrypt dữ liệu nghiệp vụ. Một recovery service có thể cần unwrap DEK để restore backup nhưng không cần quyền update key policy hoặc tạo grant cho principal khác.

| Mục tiêu khẩn cấp | Quyền tối thiểu có thể cần | Quyền không nên tự động đi kèm |
|---|---|---|
| Cô lập key bị lộ | Disable hoặc thu hồi operation liên quan | Decrypt toàn bộ dữ liệu |
| Khôi phục dữ liệu backup | Unwrap/decrypt trên key và backup được chỉ định | Export KEK hoặc thay đổi mọi key policy |
| Sửa policy gây lockout | Update policy cho đúng key sau phê duyệt | Wildcard admin trên toàn bộ KMS |
| Rotate signing key | Tạo/cấu hình key mới và chuyển đổi consumer | Export private key cũ |
| Phục hồi HSM | Recovery operation theo ceremony và quorum | Truy cập tùy ý mọi key object |

Thiết kế quyền theo mục tiêu sự cố giúp tránh cấp một emergency role quá rộng chỉ vì dễ cấu hình.

## 5. Những điều kiện kích hoạt break-glass

Break-glass chỉ nên được kích hoạt khi có một điều kiện được xác định trước và đường vận hành bình thường không thể đáp ứng nhu cầu xử lý.

Ví dụ điều kiện:

- Incident được phân loại ở mức nghiêm trọng theo quy trình tổ chức.
- Identity provider hoặc hệ thống approval thông thường không khả dụng và gây ảnh hưởng tới recovery.
- Key bị compromise hoặc có dấu hiệu sử dụng trái phép cần cô lập ngay.
- RTO/RPO của dịch vụ có nguy cơ bị vi phạm nếu không có thao tác khẩn cấp.
- Người chịu trách nhiệm đã xác định key, operation, dữ liệu hoặc dịch vụ bị ảnh hưởng.

Không kích hoạt break-glass chỉ vì thao tác thông thường mất thêm vài phút, người dùng quên mật khẩu cá nhân hoặc operator muốn tránh quy trình change management. Lý do, phạm vi và thời hạn phải được ghi nhận.

## 6. Thiết kế danh tính khẩn cấp độc lập

Break-glass identity cần được chuẩn bị trước và có khả năng hoạt động trong failure mode mà nó được thiết kế để xử lý. Nếu emergency identity phụ thuộc hoàn toàn vào cùng một identity provider, cùng một mạng quản trị hoặc cùng một secret store đang gặp sự cố, đường dự phòng có thể cũng không dùng được.

Các nguyên tắc:

- Dùng danh tính riêng cho mục đích khẩn cấp, không dùng chung với tài khoản cá nhân hàng ngày.
- Giới hạn số lượng emergency identity và người được giữ quyền kích hoạt.
- Xác thực mạnh; dùng MFA hoặc cơ chế phần cứng khi khả thi.
- Credential dự phòng được lưu trong vault hoặc quy trình custody được phê duyệt.
- Tách đường quản trị khỏi môi trường ứng dụng thông thường.
- Kiểm tra khả năng truy cập khi identity provider hoặc một thành phần mạng chính gặp sự cố.
- Không để credential khẩn cấp xuất hiện trong source code, image, script hoặc tài liệu vận hành thông thường.

Nếu phải lưu credential offline, cần kiểm soát vật lý, niêm phong, người giữ, quy trình mở niêm phong, kiểm kê và thay mới sau khi sử dụng. Bản ghi custody không được chứa secret ở dạng có thể đọc bởi người không được phép.

## 7. Least privilege trong quyền khẩn cấp

Break-glass thường được xem là quyền mạnh, nhưng vẫn cần giới hạn:

- Chỉ áp dụng cho key hoặc nhóm key đã xác định.
- Chỉ cho phép action cần để xử lý incident.
- Ràng buộc theo incident ID, purpose và environment.
- Có thời hạn tự hết hiệu lực.
- Hạn chế export key material; ưu tiên thao tác qua key handle.
- Không cho phép principal tự mở rộng quyền của chính mình nếu không có approval độc lập.
- Giới hạn số lần gọi, loại dữ liệu hoặc phạm vi backup khi phù hợp.

Nếu cần quyền rộng hơn do chưa thể xác định phạm vi, quyền đó phải có lý do cụ thể, thời hạn ngắn hơn, giám sát cao hơn và hậu kiểm độc lập. Mọi quyền rộng được cấp trong tình huống khẩn cấp cần được thu hẹp ngay sau khi sự cố ổn định.

## 8. Dual control và separation of duties

Với key có tác động lớn như KEK production, CA key, master key hoặc backup recovery key, nên yêu cầu ít nhất hai cá nhân độc lập tham gia. Một người khởi tạo yêu cầu, người khác xác nhận phạm vi và phê duyệt.

Các hình thức kiểm soát:

- Người yêu cầu và người phê duyệt là hai danh tính khác nhau.
- M-of-N custodians tham gia thao tác HSM theo quy trình của thiết bị.
- Hai người cùng xác nhận key ID, action, environment và incident ID trước khi chạy operation.
- Approval có thời hạn, chỉ dùng một lần hoặc giới hạn số operation nếu nền tảng hỗ trợ.
- Người thực hiện không được tự phê duyệt quyền của chính mình.

Dual control không nhất thiết áp dụng cho mọi thao tác khẩn cấp. Ví dụ disable một key đang bị compromise có thể cần thực hiện rất nhanh theo runbook đã phê duyệt trước. Tổ chức có thể cho phép một operator kích hoạt thao tác cô lập và yêu cầu review độc lập ngay sau đó. Các thao tác export, restore, thay đổi quorum hoặc hủy key thường cần kiểm soát nhiều người chặt hơn.

## 9. Quy trình kích hoạt break-glass

Một quy trình tổng quát có thể gồm các bước sau:

1. **Declare incident:** ghi nhận incident ID, mức độ nghiêm trọng, dịch vụ và tác động.
2. **Identify asset:** xác định key ID/version, owner, purpose và dữ liệu phụ thuộc.
3. **Define operation:** mô tả chính xác action cần thực hiện và kết quả mong muốn.
4. **Check normal path:** xác nhận vì sao quyền truy cập thông thường không khả dụng hoặc không đủ nhanh.
5. **Approve:** lấy phê duyệt theo mức rủi ro; dùng dual control khi cần.
6. **Authenticate:** dùng emergency identity và cơ chế xác thực đã chuẩn bị.
7. **Grant just-in-time access:** cấp quyền tối thiểu, có expiry và scope cụ thể.
8. **Execute:** thực hiện thao tác theo runbook đã kiểm thử, ghi nhận kết quả.
9. **Revoke:** thu hồi grant, credential tạm hoặc quyền nâng cao ngay khi hoàn tất.
10. **Review:** kiểm tra audit, dữ liệu, key state và các phụ thuộc bị ảnh hưởng.

~~~mermaid
flowchart TD
    A[Phát hiện incident] --> B[Xác định key và operation]
    B --> C{Đường truy cập thường còn khả dụng?}
    C -->|Có| D[Dùng quy trình chuẩn]
    C -->|Không hoặc quá chậm| E[Declare break-glass]
    E --> F[Approval và dual control theo mức rủi ro]
    F --> G[Authenticate emergency identity]
    G --> H[Grant quyền JIT có scope và expiry]
    H --> I[Thực hiện operation và ghi audit]
    I --> J[Thu hồi quyền khẩn cấp]
    J --> K[Hậu kiểm và cập nhật runbook]
~~~

Nếu incident yêu cầu hành động cô lập ngay, runbook có thể định nghĩa trước một số thao tác containment được phép kích hoạt nhanh. Quyền khẩn cấp vẫn phải được ghi nhận và review sau đó.

## 10. Just-in-time access và thời hạn hiệu lực

Quyền khẩn cấp nên được cấp ngay trước khi thực hiện và tự hết hạn sau khoảng thời gian cần thiết. Đây là mô hình **just-in-time (JIT) access**.

Một emergency grant nên có:

- Principal nhận quyền.
- Key ID và key version.
- Danh sách action được phép.
- Incident ID và lý do.
- Thời điểm bắt đầu, thời điểm hết hạn.
- Điều kiện context hoặc môi trường.
- Người phê duyệt và người thực hiện.
- Giới hạn số operation hoặc phạm vi dữ liệu nếu hỗ trợ.

Không cấp quyền vĩnh viễn rồi dựa vào operator tự nhớ thu hồi. Nếu nền tảng không hỗ trợ expiry tự động, cần có bước thu hồi thủ công bắt buộc, cảnh báo và người chịu trách nhiệm xác nhận.

## 11. Break-glass với KMS và HSM

KMS và HSM có thể cung cấp các cơ chế khác nhau cho quyền khẩn cấp. Một số dịch vụ hỗ trợ key policy, grant, role, key state và audit; HSM có thể hỗ trợ operator role, quorum hoặc M-of-N control. Không giả định tất cả sản phẩm có cùng cơ chế.

Một thiết kế có thể gồm:

- Emergency role được tạo trước và chỉ được bật qua approval.
- Quyền chỉ áp dụng với một key hoặc một key family.
- Key policy có deny mặc định cho export và policy modification.
- KMS operation được giới hạn theo encryption context hoặc request context.
- HSM administrative ceremony yêu cầu custodians theo ngưỡng đã định.
- Mọi thay đổi policy, grant và key state đều được ghi audit.

Với HSM, cần phân biệt quyền quản trị thiết bị, quyền quản trị partition/security domain và quyền sử dụng key object. Người có quyền quản trị thiết bị không nhất thiết phải có quyền ký hoặc giải mã bằng mọi key.

Nếu KMS/HSM control plane không khả dụng, break-glass identity không thể tự khôi phục dịch vụ từ một API đang ngừng hoạt động. Kế hoạch DR cần xét cả endpoint dự phòng, region/cluster thay thế, replica, backup và quy trình phục hồi phần cứng.

## 12. Emergency access cho các loại key

Mỗi loại key có rủi ro và yêu cầu khác nhau:

| Loại key | Mục đích khẩn cấp có thể có | Kiểm soát cần chú ý |
|---|---|---|
| DEK | Giải mã dữ liệu hoặc restore một tập backup xác định | Giới hạn record, tenant, backup và thời gian truy cập |
| KEK | Unwrap DEK hoặc phục hồi key hierarchy | Dual control, key policy, encryption context và audit |
| HMAC/signing key | Rotate hoặc xác minh message còn hiệu lực trong thời gian chuyển đổi | Tránh cấp quyền ký mới nếu chỉ cần verify; HMAC verify vẫn có thể tạo MAC |
| TLS private key | Khôi phục endpoint hoặc thay key bị compromise | Ưu tiên key mới; giới hạn quyền ký và export |
| CA private key | Khôi phục PKI hoặc thực hiện ceremony phát hành/thu hồi | Quy trình PKI riêng, quorum, HSM và phê duyệt nhiều bên |
| Backup/recovery key | Restore bản sao key hoặc security domain | Kiểm tra nguồn backup, integrity, custody và quyền restore |

Không dùng một emergency key chung cho mọi mục đích. Tách key theo purpose giúp giới hạn hậu quả và cho phép recovery mà không mở quyền không liên quan.

## 13. Trường hợp identity provider bị gián đoạn

Một lý do phổ biến để cần break-glass là identity provider hoặc hệ thống MFA thông thường không khả dụng. Đường dự phòng cần được thiết kế sao cho độc lập ở mức phù hợp nhưng vẫn có thể kiểm toán.

Các phương án có thể cân nhắc:

- Emergency identity được tạo trước trong control plane, có credential riêng và được bảo vệ trong vault.
- Hardware authenticator dự phòng được custody bởi các cá nhân được chỉ định.
- Kênh quản trị độc lập được giới hạn mạng và chỉ bật trong incident.
- Cơ chế phê duyệt thay thế đã được định nghĩa trước, có xác minh ngoài băng.

Không dùng tài khoản dùng chung không owner, mật khẩu viết trong runbook hoặc credential lưu cạnh hệ thống đang gặp sự cố. Nếu emergency identity không phụ thuộc IdP chính, cần có kiểm soát thay thế để tránh biến nó thành backdoor lâu dài.

## 14. Khôi phục khi KMS/HSM hoặc key policy gặp sự cố

Các failure mode khác nhau cần runbook khác nhau:

| Sự cố | Hướng xử lý khẩn cấp |
|---|---|
| Key policy cấu hình sai | Dùng emergency control-plane role để sửa đúng policy sau khi xác minh owner, key ID và change |
| Workload mất quyền decrypt | Kiểm tra identity, grant, context và key state; cấp lại quyền đúng scope |
| Key bị disable nhầm | Xác minh trạng thái, dependency và approval trước khi enable |
| Key bị compromise | Cô lập, disable/revoke, tạo key mới và đánh giá dữ liệu/chữ ký phụ thuộc |
| KMS region không khả dụng | Dùng kiến trúc DR/replica đã chuẩn bị; emergency identity không thay thế availability |
| HSM lỗi phần cứng | Thực hiện failover hoặc restore theo quy trình vendor và quorum custodians |
| Mất key backup hoặc wrapping key | Kích hoạt quy trình recovery đã diễn tập; không tự tạo key thay thế rồi giả định dữ liệu cũ giải mã được |

Đặc biệt, không enable lại key chỉ vì thao tác decrypt đang thất bại. Cần xác định key bị disable do nhầm cấu hình hay do incident compromise. Nếu key bị compromise, khôi phục availability bằng cách bật lại có thể tái mở cửa cho attacker.

## 15. Bảo vệ emergency credential và custody

Emergency credential là tài sản nhạy cảm. Cách lưu giữ phải phù hợp với mức rủi ro:

- Dùng vault hoặc kho custody có kiểm soát vật lý và audit.
- Nếu lưu bản offline, niêm phong chống can thiệp, ghi số seal và người giữ.
- Phân tách các phần bí mật theo quy trình split knowledge nếu cần.
- Dùng M-of-N để yêu cầu nhiều custodian cùng tham gia khôi phục.
- Không để cùng một người giữ credential, tự phê duyệt và thực hiện thao tác.
- Kiểm kê định kỳ, xác minh khả năng truy cập và thay credential sau khi sử dụng.
- Bảo vệ bản ghi quy trình để người không có quyền không thể suy ra credential.

Không chia nhỏ một secret bằng cách tự cắt chuỗi hoặc lưu từng phần theo cách không có bảo đảm mật mã. Nếu cần secret sharing, dùng cơ chế được thiết kế và triển khai phù hợp, có kiểm soát quorum và quy trình phục hồi được kiểm thử.

## 16. Audit và giám sát tức thời

Break-glass cần tạo audit trail rõ ràng hơn thao tác thông thường vì quyền và rủi ro đều cao hơn.

Các sự kiện cần ghi:

- Ai khai báo incident, ai yêu cầu và ai phê duyệt.
- Emergency identity/principal nào được sử dụng.
- Key ID, version, purpose và action.
- Thời điểm cấp quyền, expiry và thu hồi.
- Điều kiện/context được áp dụng.
- Operation thành công hay thất bại, request ID và mã lỗi.
- Thay đổi policy, grant, key state hoặc key version.
- Người xác nhận hoàn tất và hậu kiểm.

Không ghi secret, raw key material, password, token hoặc plaintext nhạy cảm vào log. Audit log cần được chuyển tới hệ thống tách biệt, chống sửa đổi và chỉ cho phép người có trách nhiệm đọc.

Khi break-glass được kích hoạt, phát cảnh báo tức thời tới nhóm security/incident response. Theo dõi operation bất thường trong thời gian quyền tồn tại; cảnh báo nếu quyền chưa bị thu hồi đúng hạn hoặc có action ngoài scope.

## 17. Thu hồi quyền và kết thúc phiên khẩn cấp

Kết thúc break-glass là một bước bắt buộc, không phải công việc tùy chọn sau khi sự cố đã hết.

Danh sách cần thực hiện:

1. Thu hồi emergency grant hoặc role tạm.
2. Hủy credential/session/token đã cấp nếu có thể.
3. Disable hoặc rotate credential khẩn cấp đã được sử dụng theo policy.
4. Kiểm tra không còn principal hoặc grant mới ngoài dự kiến.
5. Xác nhận key policy và key state đã trở về trạng thái mục tiêu.
6. Kiểm tra log và dữ liệu được truy cập trong thời gian khẩn cấp.
7. Đóng incident access window và lưu bằng chứng phê duyệt.
8. Nếu secret hoặc key material có thể bị lộ, thực hiện rotation/compromise response.

Với emergency identity lâu dài được giữ để dự phòng, cần thu hồi quyền tạm thời và reset hoặc thay credential sau mỗi lần sử dụng theo policy. Không xóa identity dự phòng nếu tổ chức vẫn cần nó cho khả năng phục hồi; phải khôi phục trạng thái an toàn và kiểm tra lại custody.

## 18. Hậu kiểm và cải tiến runbook

Sau khi sự cố kết thúc, thực hiện review độc lập:

- Break-glass có thực sự cần thiết không?
- Điều kiện kích hoạt và approval có đúng không?
- Quyền được cấp có vượt scope không?
- Có thao tác nào không có trong runbook không?
- Emergency credential có bị lộ hoặc sao chép không?
- Audit có đủ để dựng lại chuỗi hành động không?
- Quyền có được thu hồi đúng hạn không?
- Dữ liệu và key version nào bị ảnh hưởng?
- Có thể loại bỏ nguyên nhân khiến phải dùng break-glass không?
- Runbook, contact, credential custody và thời hạn cần cập nhật gì?

Hậu kiểm nên có người không trực tiếp thực hiện thao tác xem xét. Nếu phát hiện quyền bị lạm dụng, audit thiếu hoặc credential bị phơi nhiễm, mở incident bảo mật riêng và xử lý theo quy trình tương ứng.

## 19. Diễn tập break-glass

Một quy trình chưa từng được diễn tập có thể thất bại đúng lúc cần dùng. Cần kiểm tra định kỳ nhưng phải làm trong môi trường và phạm vi an toàn.

Nội dung diễn tập:

- Xác thực emergency identity khi IdP chính bị mô phỏng gián đoạn.
- Thực hiện approval và dual control.
- Cấp JIT grant đúng key/action và xác nhận expiry.
- Thực hiện thao tác thử nghiệm trên key test hoặc dữ liệu không production.
- Thu hồi quyền và kiểm tra session/grant đã hết hiệu lực.
- Xác nhận alert và audit được gửi tới đúng nhóm.
- Kiểm tra runbook, số điện thoại/on-call và custody.
- Đo thời gian phục hồi so với RTO/RPO.

Không thử thao tác destructive trên key production chỉ để chứng minh quy trình. Với HSM, dùng môi trường hoặc ceremony thử nghiệm được vendor và tổ chức cho phép; không reset security domain hay xóa key trong buổi diễn tập thông thường.

## 20. Ví dụ runbook: khôi phục quyền unwrap DEK cho backup

Giả sử backup service cần unwrap DEK để phục hồi dữ liệu, nhưng IAM policy bị thay đổi nhầm khiến workload không còn quyền gọi KMS. Quy trình minh họa:

1. Incident commander xác nhận sự cố ảnh hưởng tới backup recovery và tạo incident ID.
2. Key owner xác định KEK, key version, backup set, tenant và mục tiêu restore.
3. Operator xác minh key vẫn active và không có dấu hiệu compromise.
4. Người phê duyệt xác nhận cần emergency control-plane action để khôi phục grant hoặc policy.
5. Emergency identity xác thực qua kênh độc lập đã chuẩn bị.
6. Cấp quyền JIT chỉ cho key cụ thể và action cần thiết; không cấp export hoặc schedule deletion.
7. Kiểm tra encryption context của backup khớp tenant/purpose.
8. Thực hiện thử trên một bản backup kiểm thử hoặc một tập dữ liệu giới hạn.
9. Xác minh dữ liệu phục hồi, tính toàn vẹn và audit.
10. Thu hồi quyền tạm, khôi phục policy chuẩn và review change gây lockout.

Nếu nguyên nhân là key bị compromise thay vì policy sai, không thực hiện quy trình enable/grant như trên. Phải chuyển sang incident response: cô lập key, tạo key mới, đánh giá dữ liệu và thực hiện re-encryption/rewrap theo kế hoạch.

## 21. Mẫu policy logic cho break-glass

Ví dụ dưới đây minh họa các thuộc tính cần có, không phải cú pháp trực tiếp của một cloud KMS cụ thể:

~~~yaml
policy_name: emergency-backup-recovery
default_effect: deny
activation:
  incident_required: true
  approval_required: 2
  emergency_identity_required: true
  max_duration_minutes: 30
scope:
  resources:
    - key: backup-kek-prod
  actions:
    - unwrap
  conditions:
    environment: production
    purpose: approved-backup-restore
    incident_id: required
restrictions:
  - deny: export
  - deny: update_key_policy
  - deny: schedule_deletion
  - deny: create_grant
audit:
  immediate_alert: true
  immutable_record: true
  post_use_review_required: true
~~~

Mẫu này thể hiện default deny, approval, identity, thời hạn, resource/action scope, hạn chế và audit. Trong triển khai thực tế, phải ánh xạ các trường vào policy engine của nền tảng, kiểm tra semantics explicit deny và xác nhận emergency grant thật sự tự hết hạn.

## 22. Những sai lầm thường gặp

- **Dùng break-glass hằng ngày:** biến ngoại lệ thành đường truy cập chính và làm mất ý nghĩa kiểm soát.
- **Một tài khoản có toàn quyền trên mọi key:** blast radius quá lớn nếu credential bị lộ.
- **Emergency identity phụ thuộc hoàn toàn vào IdP đang gặp sự cố:** đường dự phòng không hoạt động khi cần.
- **Không có approval hoặc audit:** không xác định được ai đã cho phép và thực hiện thao tác.
- **Một người yêu cầu, phê duyệt và thực hiện:** không có separation of duties.
- **Cấp quyền vĩnh viễn:** quên thu hồi và tạo backdoor lâu dài.
- **Cho phép export mặc định:** tạo bản sao key material ngoài miền bảo vệ.
- **Bỏ qua key state:** bật lại key bị compromise để khôi phục dịch vụ.
- **Dùng emergency access để bỏ qua kiểm tra dữ liệu:** có thể giải mã sai tenant hoặc backup.
- **Không diễn tập:** credential hết hạn, contact sai hoặc runbook thiếu bước.
- **Không hậu kiểm:** bỏ sót quyền còn sót, credential bị lộ hoặc policy bị thay đổi.
- **Nhầm identity dự phòng với availability dự phòng:** tài khoản khẩn cấp không khắc phục được KMS/HSM outage hoặc mất key material.

## 23. Checklist thiết kế và vận hành break-glass

- [ ] Đã định nghĩa các tình huống đủ điều kiện kích hoạt.
- [ ] Emergency identity độc lập ở mức cần thiết với failure mode chính.
- [ ] Credential được bảo vệ bằng custody, MFA hoặc cơ chế phần cứng phù hợp.
- [ ] Principal, key, action, purpose và context được giới hạn rõ ràng.
- [ ] Có default deny và JIT grant với expiry.
- [ ] Có approval và dual control cho thao tác rủi ro cao.
- [ ] Tách quyền control plane khỏi data plane.
- [ ] Export, policy modification và deletion bị hạn chế riêng.
- [ ] Runbook phân biệt policy lockout, key compromise, KMS outage và HSM failure.
- [ ] KMS/HSM audit và cảnh báo được kích hoạt tức thời.
- [ ] Có bước thu hồi grant, session và credential sau khi sử dụng.
- [ ] Có hậu kiểm độc lập và xử lý ngoại lệ.
- [ ] Quy trình được diễn tập định kỳ trên key test hoặc dữ liệu an toàn.
- [ ] RTO/RPO, backup, replica và dependency được kiểm tra.
- [ ] Emergency identity và custody được kiểm kê, thay mới và review định kỳ.

Break-glass key access là cơ chế phục hồi có kiểm soát cho các tình huống mà quyền truy cập thông thường không thể đáp ứng. Cơ chế này chỉ an toàn khi identity dự phòng được chuẩn bị trước, quyền được cấp theo mục tiêu và thời hạn, thao tác nhạy cảm có phê duyệt phù hợp, mọi hoạt động được giám sát và quyền được thu hồi ngay sau khi hoàn tất. Khi kết hợp với runbook phân biệt rõ từng failure mode, diễn tập định kỳ và hậu kiểm độc lập, tổ chức có thể duy trì khả năng phục hồi mà không biến quyền khẩn cấp thành một backdoor thường trực.
