# Password spraying: nhận diện và phòng vệ trước tấn công mật khẩu trên nhiều tài khoản

Trong hệ thống quản lý danh tính và truy cập (**Identity and Access Management – IAM**), mỗi tài khoản đăng nhập là một điểm mà tổ chức cần bảo vệ. Một kiểu tấn công phổ biến là **password spraying**: kẻ tấn công thử một số ít mật khẩu có khả năng được nhiều người sử dụng trên nhiều tài khoản khác nhau, thay vì tập trung thử rất nhiều mật khẩu với một tài khoản. Cách phân tán này có thể khiến những cơ chế chỉ theo dõi số lần thất bại của từng tài khoản không phát hiện được toàn bộ chiến dịch.

Bài học thuộc chương **Mật khẩu** của mô-đun **SECURITY_IDENTITY_ACCESS_MANAGEMENT_IDENTITY_LIFECYCLE**. Mô-đun tập trung quản lý vòng đời danh tính theo **Joiner–Mover–Leaver (JML)**, từ xác minh người dùng, tạo tài khoản và cấp quyền đến rà soát và thu hồi khi thay đổi vai trò. Vì vậy, bên cạnh nhận diện password spraying, nội dung sẽ kết nối **IdP, SSO, SCIM, RBAC/ABAC, tài khoản dịch vụ, kiểm toán** và việc giảm những tài khoản/quyền truy cập tồn dư.

Mục tiêu của bài học là hiểu **cơ chế rủi ro và biện pháp phòng vệ**, không thực hành đoán mật khẩu hoặc thử đăng nhập trên tài khoản không được phép.

Sau bài học, người học có thể:

- Giải thích password spraying và phân biệt với brute-force password guessing, credential stuffing và một lần đăng nhập sai thông thường.
- Đọc nhật ký xác thực của IdP/SSO và phát hiện tín hiệu **nhiều danh tính bị nhắm tới**, kể cả khi nguồn yêu cầu thay đổi.
- Thiết kế bảo vệ nhiều lớp bằng MFA chống phishing, passwordless, chính sách mật khẩu, điều tiết yêu cầu, quản lý rủi ro và kiểm soát tài khoản cũ.
- Xây dựng luồng cảnh báo, phân loại mức độ, điều tra, xử lý phiên/token và phục hồi tài khoản an toàn.
- Đánh giá tác động của password spraying tới Joiner, Mover, Leaver, tài khoản đặc quyền và tài khoản dịch vụ.

## 1. Password spraying là gì?

**Password spraying** là một hình thức thử xác thực trái phép: đối tượng tấn công sử dụng **một hoặc một vài mật khẩu dự đoán** đối với **nhiều tên tài khoản** để tìm tài khoản có mật khẩu yếu hoặc được dùng chung. Đặc trưng nhận diện là **mô hình thất bại trải rộng trên nhiều danh tính**, không chỉ số lần thất bại lớn của một tài khoản.

Ví dụ mang tính phân tích: hệ thống IAM quan sát được các sự kiện nhập sai mật khẩu ở nhiều tài khoản nhân viên trong một khoảng thời gian; sau đó một tài khoản có đăng nhập thành công bất thường và bị yêu cầu xác thực yếu tố bổ sung. Dấu hiệu này **có thể** liên quan password spraying, nhưng cũng có thể do ứng dụng dùng cấu hình sai, nguồn NAT chung hoặc thay đổi mật khẩu đồng loạt. Cần điều tra thay vì suy kết luận chỉ từ một thống kê.

### 1.1. So sánh các dạng tấn công và sự cố

| Hiện tượng | Cách thất bại thường xuất hiện | Điểm khác biệt khi phòng vệ |
| --- | --- | --- |
| **Password spraying** | Nhiều tài khoản xuất hiện lỗi mật khẩu, mỗi tài khoản có thể chỉ có ít lần thử. | Phát hiện theo **chiều rộng danh tính**, chiến dịch và nguồn/ứng dụng liên quan. |
| **Brute-force password guessing** | Một hoặc một số tài khoản nhận nhiều lần thử liên tiếp. | Điều tiết theo tài khoản, phiên và nguồn; theo dõi số lần thử và hành vi tự động. |
| **Credential stuffing** | Các cặp tên đăng nhập/mật khẩu bị lộ được thử lại trên dịch vụ khác. | Ngăn tái sử dụng mật khẩu, phát hiện thông tin lộ và yêu cầu MFA. |
| **Đăng nhập thất bại hợp lệ** | Người dùng gõ sai, đổi mật khẩu hoặc ứng dụng giữ thông tin cũ. | Phân biệt bằng ngữ cảnh thiết bị, nguồn, số danh tính, lịch thay đổi và ứng dụng. |
| **Lỗi tích hợp** | Nhiều tài khoản lỗi từ cùng một ứng dụng hoặc connector bị cấu hình sai. | Đối chiếu sự kiện triển khai, tài khoản dịch vụ và trạng thái IdP. |

Các nhóm không hoàn toàn loại trừ nhau. Một sự cố có thể bắt đầu bằng việc thử mật khẩu trên nhiều tài khoản, sau đó chuyển thành truy cập trái phép vào một tài khoản cụ thể. Phân loại dùng để chọn kiểm soát và cách điều tra, không phải để gán nhãn cứng cho mọi log.

### 1.2. Vì sao cách tấn công này đáng chú ý?

Một chính sách chỉ khóa tài khoản sau nhiều lần nhập sai có thể không phát hiện được **rất nhiều tài khoản mỗi tài khoản chỉ lỗi một vài lần**. Hơn nữa, đăng nhập có thể trải qua IdP, VPN, ứng dụng cũ, cổng email và các giao thức khác. Nếu mỗi nơi tự quan sát riêng mà không hợp nhất tín hiệu, bức tranh rủi ro của cả tổ chức bị chia nhỏ.

Password spraying cũng có thể gây hậu quả ngoài việc chiếm tài khoản: khóa hàng loạt người dùng do chính sách lockout cứng, tăng tải helpdesk, tạo cảnh báo giả và cản trở công việc. Vì vậy, phản ứng cần cân bằng **an ninh** và **khả năng sẵn sàng của dịch vụ**.

## 2. Từ định danh tới quyền truy cập: tấn công chạm vào lớp nào?

Để hiểu tác động, cần phân biệt:

1. **Identity/Subject:** người hoặc workload mà IAM quản lý, thường có mã chủ thể ổn định.
2. **Account:** đối tượng đăng nhập tại IdP hoặc ứng dụng.
3. **Credential:** bằng chứng dùng cho xác thực như mật khẩu, passkey, certificate hoặc API key.
4. **Authentication:** quá trình chứng minh quyền kiểm soát danh tính.
5. **Session/Token:** trạng thái hoặc vật mang quyền được phát hành sau một luồng xác thực/cấp phép.
6. **Authorization:** quyết định người dùng được làm gì theo **RBAC**, **ABAC**, nhóm hoặc quyền trực tiếp.

Password spraying nhắm vào **khâu kiểm tra credential mật khẩu**. Nếu một mật khẩu phù hợp và không có bảo vệ khác, đối tượng có thể vượt qua bước xác thực. Tuy nhiên, tác động cuối cùng còn phụ thuộc trạng thái tài khoản, MFA, điều kiện truy cập, token đã phát hành và các quyền ứng dụng.

**Một lần xác thực mật khẩu thành công chưa chắc là đăng nhập hoàn tất:** IdP có thể tiếp tục yêu cầu MFA hoặc từ chối do chính sách thiết bị/rủi ro. Ngược lại, nếu một ứng dụng cũ cho phép chỉ dùng mật khẩu mà không áp dụng MFA của IdP, bảo vệ ở SSO hiện đại có thể không bao phủ đường đó.

### 2.1. Đường đăng nhập cần kiểm kê

| Đường truy cập | Nguồn nhật ký/kiểm soát | Rủi ro đặc trưng |
| --- | --- | --- |
| **Ứng dụng qua IdP/SSO** | Sign-in logs, MFA và Conditional Access tại IdP; log ứng dụng. | Thiết bị, phiên và chính sách có thể ảnh hưởng kết quả cuối. |
| **VPN / remote access** | Cổng VPN/RADIUS, IdP nếu được tích hợp. | Đường xác thực khác với ứng dụng web; phải kiểm tra MFA riêng. |
| **Ứng dụng có local password** | Log của chính ứng dụng, API quản trị tài khoản. | Có thể không chịu chính sách MFA hay lockout trung tâm. |
| **Directory/on-premises** | Nhật ký xác thực directory, federation, gateway. | Giao thức cũ hoặc hệ thống liên kết thiếu khả năng quan sát tập trung. |
| **Email và dịch vụ đồng bộ cũ** | Log giao thức và ứng dụng liên quan. | Một số đường truy cập có cơ chế xác thực khác luồng đăng nhập tương tác. |
| **API dùng mật khẩu hoặc basic authentication** | API gateway, resource server. | Cần đánh giá thay bằng cơ chế xác thực ứng dụng phù hợp. |

Không nên khẳng định tất cả password spraying đều đi qua IdP. Một số hệ thống đích vẫn có tài khoản riêng, và việc **chặn tại SSO** không tự chứng minh đã loại bỏ mọi đường thử mật khẩu.

## 3. Dấu hiệu nhận diện trong nhật ký xác thực

Password spraying không có một bản ghi log duy nhất mang tên “attack”. Nó thường được phát hiện từ **tổ hợp sự kiện, quan hệ giữa các tài khoản và bối cảnh vận hành**.

### 3.1. Những trường dữ liệu nên thu thập

| Trường log | Cách sử dụng phòng thủ |
| --- | --- |
| **eventId**, **correlationId**, **requestId** | Truy vết một phiên xác thực hoặc kết nối tới log ứng dụng. |
| **occurredAt**, **ingestedAt** | Biết lúc xác thực xảy ra và lúc SIEM nhận sự kiện; phát hiện log đến trễ. |
| **subjectId/accountId** | Đếm đúng số tài khoản bị nhắm tới; tránh phụ thuộc vào email có thể đổi. |
| **result / reasonCode** | Phân biệt sai mật khẩu, không tồn tại tài khoản, MFA thất bại, bị khóa hoặc chính sách từ chối. |
| **authenticationProtocol / applicationId** | Xem đường xác thực và ứng dụng nào nhận nhiều yêu cầu. |
| **sourceIp**, thông tin mạng/ASN khi được phép | Tìm tương quan theo nguồn nhưng lưu ý NAT, proxy và VPN. |
| **deviceId / clientApp / userAgent** | Bổ sung bối cảnh thiết bị, ứng dụng và dấu hiệu tự động hóa; không coi user agent là bằng chứng chắc chắn. |
| **MFA / conditional access outcome** | Biết mật khẩu đã đạt bước nào, có bảo vệ bổ sung hay không. |
| **sessionId / token issuance metadata** | Truy tiếp các phiên được tạo và hành động sau xác thực nếu có. |
| **accountLifecycleState** | Phân biệt Employee đang hoạt động, tài khoản chờ kích hoạt, Leaver hoặc tài khoản mồ côi. |

**Không ghi mật khẩu được thử**, giá trị token, cookie hoặc mã MFA vào log. Phòng vệ không cần thu thập raw credential; chỉ cần kết quả và metadata đủ để đối chiếu.

### 3.2. Các tín hiệu nổi bật

- **Nhiều tài khoản có lỗi sai mật khẩu** trong cùng một giai đoạn, có quan hệ về nguồn, giao thức, client hoặc các đặc điểm chiến dịch.
- **Một nguồn tương tác với nhiều danh tính**, khác với mẫu sử dụng bình thường của một thiết bị/người dùng.
- **Tài khoản không tồn tại hoặc đã nghỉ việc** cũng bị thử xác thực, gợi ý danh sách danh tính cũ hoặc bị thu thập từ nguồn bên ngoài.
- **Đăng nhập thành công hoặc hoàn tất MFA sau chuỗi lỗi trên nhiều tài khoản**, cần ưu tiên xác minh người dùng và phiên.
- **Cùng chiến dịch xuất hiện ở nhiều ứng dụng** hoặc giao thức, nhất là đường không áp dụng chính sách xác thực hiện đại.
- **Mẫu xảy ra ngoài thông lệ** của tổ chức, không khớp hoạt động onboarding, đồng bộ hay bảo trì.

Một tín hiệu riêng lẻ là **dấu hiệu nghi vấn**, không phải kết luận đã có chiếm đoạt. Để xác định, cần kết hợp thêm trạng thái thiết bị, sự kiện MFA, lịch sử IP, tài khoản sử dụng thực tế và thay đổi cấu hình gần đó.

### 3.3. Đầu ra mong muốn của cảnh báo

Thay vì chỉ hiển thị “20 lần đăng nhập lỗi”, một cảnh báo hữu ích nên nói:

> Trong một cửa sổ quan sát, nhiều tài khoản thuộc cùng phạm vi IdP có lỗi sai mật khẩu có liên hệ về nguồn hoặc dấu hiệu client. Cần kiểm tra các phiên thành công theo sau, đường xác thực không có MFA và những tài khoản đã rời tổ chức.

Thông tin nên kèm danh sách account ID, thời điểm, kết quả, nguồn và mức độ tin cậy, với quyền truy cập phù hợp. Nêu rõ **vì sao mô hình này khác baseline**, không chỉ một con số độc lập.

## 4. Phát hiện theo chiều rộng thay vì chỉ theo số lần nhập sai

### 4.1. Một ví dụ nhật ký tổng hợp

Bảng dưới đây mô tả **dữ liệu đã được lược giản để huấn luyện phòng thủ**:

| Thời điểm | Account ID | Nguồn | Kết quả | Ghi chú |
| --- | --- | --- | --- | --- |
| 08:10 | user-A | source-X | Sai mật khẩu | Luồng xác thực của ứng dụng chung. |
| 08:11 | user-B | source-X | Sai mật khẩu | Tài khoản khác, cùng ngữ cảnh nguồn. |
| 08:12 | user-C | source-X | Sai mật khẩu | Chưa đủ kết luận độc lập. |
| 08:15 | user-D | source-X | Sai mật khẩu | Nhiều danh tính bị ảnh hưởng. |
| 08:17 | user-E | source-X | Sai mật khẩu | Cần đối chiếu sự kiện hệ thống. |
| 08:20 | user-C | source-X | Yêu cầu MFA | Cần xác minh kết quả xác thực cuối cùng. |

Mục đích của ví dụ không phải cung cấp nhịp độ thử mật khẩu; các mốc và tài khoản là giả định để minh họa **cách đọc log theo nhiều chủ thể**. Điều tra viên phải kiểm tra liệu source-X có phải mạng NAT của văn phòng hoặc ứng dụng được cấp phép hay không.

### 4.2. Mẫu truy vấn phân tích phòng thủ

Một phép phân tích thường nhóm sự kiện **sai mật khẩu** theo nguồn và cửa sổ thời gian rồi đếm **số danh tính duy nhất**. Giả mã SQL sau không phụ thuộc một sản phẩm SIEM cụ thể:

~~~sql
-- Minh họa truy vấn phòng thủ trên dữ liệu xác thực đã chuẩn hóa.
-- window_start và window_end do pipeline phát hiện cung cấp.
SELECT
    source_group,
    application_id,
    COUNT(*) AS wrong_password_events,
    COUNT(DISTINCT subject_id) AS distinct_subjects,
    MIN(event_time) AS first_seen,
    MAX(event_time) AS last_seen
FROM normalized_authentication_events
WHERE event_time >= window_start
  AND event_time < window_end
  AND result_code = 'INVALID_PASSWORD'
GROUP BY source_group, application_id
HAVING COUNT(DISTINCT subject_id) >= configured_unique_subject_threshold;
~~~

Đây là **logic phân tích phòng thủ**, không phải truy vấn chạy ngay trên mọi SIEM. Trên thực tế:

- **source_group** phải được định nghĩa cẩn thận: IP đơn có thể đại diện cho cả văn phòng qua NAT; nhiều IP cũng có thể thuộc một chiến dịch.
- **configured_unique_subject_threshold** cần được điều chỉnh theo baseline, quy mô tenant, mạng và mức độ nhạy cảm; không có ngưỡng chung cho mọi hệ thống.
- Phải bảo đảm **result_code** thực sự biểu thị mật khẩu sai. Nhiều IdP dùng mã riêng, và “authentication failed” có thể là lỗi MFA, policy hoặc mạng.
- Cần ghép log theo **subject ID ổn định**, phiên bản ánh xạ tài khoản và khoảng thời gian có ngữ nghĩa chính xác.
- Quy trình phải tiếp tục truy tìm **thành công bất thường và phiên đã phát hành**, không dừng ở thống kê thất bại.

### 4.3. Giới hạn của việc nhóm theo một IP

IP không phải danh tính con người. Một IP có thể đại diện cho:

- Nhiều nhân viên đi qua NAT hoặc VPN doanh nghiệp.
- Proxy/gateway hợp lệ của một ứng dụng tập trung.
- Một nguồn truy cập Internet thay đổi địa chỉ theo thời gian.

Vì vậy, **số tài khoản lỗi theo một IP cao** chưa chắc là tấn công. Ngược lại, chỉ theo dõi một IP có thể bỏ sót sự kiện liên quan nhưng phân tán trên nhiều nguồn. Cần kết hợp **thời gian, tenant, ứng dụng, giao thức, thiết bị, độ nhất quán hành vi và lịch sử truy cập**.

### 4.4. Hoạt động phân tán và kéo dài

Một phần hoạt động nghi vấn có thể trải rộng trên nhiều nguồn hoặc xuất hiện thưa trong thời gian dài. Các bộ phát hiện nên có **nhiều cửa sổ quan sát**, duy trì tương quan chiến dịch, so sánh baseline của tổ chức và đặt trọng số cao hơn cho dấu hiệu thành công sau bất thường.

Tránh dựa vào một ngưỡng cứng hoặc mô tả duy nhất về nhịp độ tấn công. Việc liên kết sự kiện cần được kiểm chứng để không gộp nhầm nhiều người dùng hợp lệ thành một cảnh báo hoặc làm lộ thông tin cá nhân quá mức.

## 5. Những nguồn gây cảnh báo giả thường gặp

| Hiện tượng hợp lệ | Dấu hiệu giống password spraying | Cách phân biệt |
| --- | --- | --- |
| **Thay đổi mật khẩu hàng loạt** | Nhiều người dùng nhập mật khẩu cũ. | Đối chiếu đợt thay đổi đã thông báo, thiết bị và các lần đăng nhập thành công. |
| **Ứng dụng lưu credential cũ** | Nhiều tài khoản bị thử lại từ một connector hoặc ứng dụng. | Kiểm tra owner, danh sách tài khoản phục vụ tích hợp, lịch triển khai và log connector. |
| **Văn phòng dùng NAT/VPN** | Một IP phát sinh lỗi từ nhiều người. | So sánh hành vi thiết bị/người dùng, mạng nội bộ, hoạt động làm việc bình thường. |
| **Sự cố IdP hoặc chính sách MFA** | Lỗi xác thực tăng đột ngột trên diện rộng. | Phân loại đúng error code và kiểm tra tình trạng dịch vụ. |
| **Đồng bộ directory bị trễ** | Người dùng mới hoặc đã đổi tên không đăng nhập được. | Đối chiếu Joiner/Mover và trạng thái tài khoản tại IdP, SCIM. |
| **Bài kiểm tra bảo mật được phép** | Nhiều tài khoản có sự kiện xác thực khác thường. | Xác nhận phạm vi/đơn vị được ủy quyền; không tự bỏ qua nếu có dấu hiệu lạm dụng. |

Điều tra cần sử dụng **bằng chứng xác minh** thay vì tự động loại bỏ mọi sự kiện xuất phát từ IP nội bộ hoặc mọi giao thức mang tên ứng dụng quen thuộc. Tài khoản hợp lệ vẫn có thể bị chiếm và được sử dụng từ môi trường tin cậy.

## 6. Phòng vệ lớp thứ nhất: giảm giá trị của mật khẩu dễ đoán

### 6.1. Chính sách mật khẩu an toàn, khả dụng

Chính sách nên hướng tới **mật khẩu đủ dài, khó đoán và không bị lộ**, thay vì chỉ áp đặt thay đổi hình thức như bắt buộc xen kẽ một chữ hoa, một ký hiệu hoặc đổi định kỳ bất kể rủi ro.

Các biện pháp phòng vệ thường có giá trị:

1. Khuyến khích **mật khẩu dài và duy nhất cho từng dịch vụ**, hỗ trợ password manager để tránh dùng lại.
2. Kiểm tra mật khẩu mới với danh sách **phổ biến, dễ đoán hoặc đã bị lộ** bằng phương pháp được phép và bảo vệ dữ liệu.
3. Không dùng **mật khẩu mặc định chung** cho hàng loạt tài khoản Joiner.
4. Không để trợ giúp người dùng qua helpdesk tiết lộ mật khẩu gốc hoặc dùng câu hỏi bảo mật dễ suy đoán.
5. Bảo vệ password verifier bằng thuật toán băm mật khẩu có salt và thông số chi phí phù hợp, ví dụ Argon2id nếu kiến trúc hỗ trợ.
6. Có cơ chế đổi/đặt lại mật khẩu khi có dấu hiệu bị lộ hoặc bị chiếm, cùng quy trình xác minh an toàn.

**Băm mật khẩu đúng cách bảo vệ cơ sở dữ liệu xác thực**, nhưng không trực tiếp ngăn password spraying qua màn hình đăng nhập. Đó là hai lớp kiểm soát khác nhau: một lớp giảm hậu quả khi database bị lộ, lớp kia giới hạn khả năng đoán mật khẩu qua dịch vụ trực tuyến.

### 6.2. Chặn mật khẩu đã biết yếu trong quá trình đặt và reset

Password spraying tận dụng khả năng nhiều người dùng chọn cùng những mật khẩu dễ đoán. Bước đặt/khôi phục mật khẩu nên từ chối các lựa chọn nằm trong tập mật khẩu phổ biến hoặc đã được ghi nhận lộ, theo chính sách và giải pháp kiểm tra an toàn.

Không ghi mật khẩu bị từ chối vào log để “phân tích xu hướng” vì có thể tạo thêm kho bí mật dễ bị lộ. Có thể lưu **mã lý do từ chối** và thống kê tổng hợp mà không giữ giá trị mật khẩu.

## 7. Phòng vệ lớp thứ hai: MFA, passkey và xác thực chống phishing

**MFA** có thể ngăn người đã đoán đúng mật khẩu sử dụng tài khoản nếu họ không chứng minh được yếu tố còn lại. Tuy nhiên, mức bảo vệ khác nhau theo phương thức:

| Phương thức | Tác dụng trước password spraying | Điểm cần lưu ý |
| --- | --- | --- |
| **Mật khẩu đơn yếu tố** | Phụ thuộc hoàn toàn vào độ mạnh và bảo vệ xác thực mật khẩu. | Rủi ro cao khi có mật khẩu đoán được. |
| **Mật khẩu + SMS/TOTP OTP** | Bổ sung yếu tố nếu mật khẩu bị đoán. | Mã có thể bị phishing theo thời gian thực; bảo vệ recovery và kênh OTP. |
| **Mật khẩu + push** | Có thể chặn bước hoàn tất nếu người dùng không chấp thuận. | Nguy cơ MFA fatigue; cần ngữ cảnh, number matching hoặc biện pháp phù hợp. |
| **Passkey/WebAuthn** | Xác thực bằng khóa công khai được ràng buộc với relying party/origin; không dựa vào đoán mật khẩu. | Kiểm soát đăng ký, khôi phục, thiết bị, chính sách user verification. |
| **Security key phần cứng** | Có thể cung cấp xác thực chống phishing mạnh cho trường hợp nhạy cảm. | Cần quản lý khóa dự phòng, mất thiết bị và thủ tục recovery. |

**Passwordless**, nhất là phương thức chống phishing được triển khai đúng, giảm đáng kể bề mặt password spraying đối với những đường không còn chấp nhận mật khẩu. Tuy vậy, cần bảo đảm **đường đăng nhập cũ, giao thức legacy và quy trình recovery** không vô tình cho phép quay về mật khẩu yếu.

### Step-up authentication cho tác vụ rủi ro cao

Khi người dùng đăng nhập từ môi trường rủi ro hoặc yêu cầu thao tác đặc quyền, ứng dụng có thể yêu cầu **xác thực tăng cường** bằng phương thức phù hợp. Chính sách cần xét tín hiệu thiết bị, mức rủi ro, vai trò, quyền và nguồn truy cập. Đây là biện pháp bổ sung, không thay thế việc sửa lỗ hổng ở một đường xác thực chỉ dùng mật khẩu.

## 8. Phòng vệ lớp thứ ba: giới hạn yêu cầu và phản ứng thích ứng

Hệ thống nên giới hạn những lần thử mật khẩu không hợp lệ nhưng **không được chỉ nghĩ đến việc khóa cứng từng tài khoản**. Một đối tượng gây nhiều lần lỗi có thể khiến người dùng hợp lệ bị từ chối dịch vụ nếu cơ chế lockout quá nhạy.

Các kiểm soát kết hợp:

- **Rate limiting/throttling:** điều tiết có kiểm soát theo tài khoản, nguồn, phiên, ứng dụng và tín hiệu rủi ro khác.
- **Smart lockout/adaptive protection:** xem xét lịch sử và ngữ cảnh để giảm nguy cơ khóa nhầm người dùng hợp lệ; tùy khả năng IdP.
- **Risk-based access:** yêu cầu xác thực bổ sung hoặc hạn chế phiên khi có tín hiệu rủi ro được kiểm chứng.
- **Tập trung hóa chính sách:** ưu tiên đường đăng nhập qua IdP và MFA; ngừng các phương thức cũ không có bảo vệ tương xứng khi khả thi.
- **Giám sát theo chiến dịch:** phát hiện nhiều tài khoản bị nhắm tới, kể cả khi mỗi tài khoản có ít lỗi.
- **Bảo vệ tài khoản nhạy cảm:** admin, break-glass và dịch vụ có quyền cao cần kiểm soát đặc biệt, tránh phụ thuộc mật khẩu đơn yếu tố.

### Tránh biến chính sách khóa thành sự cố gián đoạn

Một chính sách khóa tự động mọi tài khoản xuất hiện trong cùng một cảnh báo có thể làm hàng loạt nhân viên mất khả năng làm việc. Cần:

1. Xác định mức tin cậy và hệ thống bị ảnh hưởng.
2. Ưu tiên **ngăn nguồn/hành vi đáng ngờ** hoặc tăng xác thực theo kiến trúc được phép trước khi khóa hàng loạt.
3. Chỉ khóa tài khoản khi có căn cứ và quy trình phù hợp, đặc biệt với tài khoản đặc quyền, điều hành và tài khoản dịch vụ.
4. Có luồng hỗ trợ khôi phục mà không hạ thấp tiêu chuẩn xác minh danh tính.
5. Theo dõi tác động vận hành và tình trạng false positive sau khi áp dụng kiểm soát.

Không có một ngưỡng lockout/rate limit dùng chung cho mọi tổ chức. Cấu hình cần thử nghiệm theo baseline, sản phẩm IdP, loại tài khoản và mục tiêu sẵn sàng của dịch vụ.

## 9. Phòng vệ lớp thứ tư: hợp nhất IdP, SSO và ứng dụng cũ

Một tổ chức có thể đã yêu cầu MFA tại SSO nhưng vẫn tồn tại ứng dụng cục bộ dùng mật khẩu hoặc một gateway với chính sách yếu hơn. Để giảm bề mặt password spraying cần:

1. **Kiểm kê tất cả đường xác thực**: IdP, VPN, email, ứng dụng nội bộ, SaaS, directory, API và giao thức cũ.
2. **Hợp nhất chính sách vào IdP khi phù hợp**, ưu tiên SSO và phương thức xác thực chống phishing.
3. **Tắt hoặc thay thế xác thực legacy** thiếu khả năng áp dụng MFA và kiểm soát rủi ro, theo kế hoạch bảo đảm ứng dụng còn vận hành.
4. **Thu thập log từ hệ thống không tích hợp SSO** và đưa vào cùng cơ chế phát hiện/correlation.
5. **Đối soát tài khoản và trạng thái từ SCIM/API**, không giả định vô hiệu hóa ở IdP đồng nghĩa mọi tài khoản cục bộ đều khóa.
6. **Kiểm tra chính sách tại resource server** để phiên/token cũ không còn quyền sau thay đổi tài khoản hoặc entitlement.

**SCIM** chủ yếu phục vụ quản lý User và Group giữa các hệ thống; nó **không tự mang lại MFA** và cũng không phải giải pháp phát hiện password spraying. SCIM có thể giúp hạn chế tài khoản mồ côi bằng cách truyền trạng thái vô hiệu hóa, nhưng việc xác thực và kiểm soát đăng nhập phải được đánh giá riêng.

## 10. Password spraying trong Joiner–Mover–Leaver

### 10.1. Joiner: tránh tài khoản mới trở thành mục tiêu dễ đoán

Tài khoản mới có thể được tạo trước ngày bắt đầu, và tên đăng nhập/email đôi khi đã có thể suy đoán từ quy tắc đặt tên. Nếu dùng mật khẩu tạm chung hoặc quy trình kích hoạt yếu, tài khoản có thể gặp rủi ro ngay trước khi nhân viên bắt đầu làm việc.

Luồng Joiner nên:

- Lấy danh tính từ HRIS hoặc nguồn có thẩm quyền, xác minh đúng người và ngày có hiệu lực.
- Tạo tài khoản ở trạng thái phù hợp; không bật quyền nghiệp vụ sớm chỉ vì tài khoản đã được pre-provision.
- Tránh mật khẩu mặc định dùng chung; cho phép người dùng đăng ký credential qua kênh được xác minh.
- Áp dụng MFA/phương thức chống phishing theo chính sách ngay từ lần kích hoạt hợp lệ.
- Giám sát đăng nhập bất thường vào tài khoản chưa tới ngày bắt đầu.
- Đối soát IdP và ứng dụng đích để phát hiện tài khoản đã hoạt động ngoài ý muốn.

### 10.2. Mover: thay đổi vai trò có thể đổi mức độ rủi ro

Khi nhân viên chuyển bộ phận, thay manager hoặc nhận nhiệm vụ đặc quyền, tài khoản cũ có thể tiếp tục dùng credential hợp lệ. Tuy nhiên, chính sách cần:

- Rà soát MFA hoặc step-up cho nhiệm vụ mới.
- Thu hồi entitlement không còn cần theo RBAC/ABAC, đặc biệt quyền admin và dữ liệu nhạy cảm.
- Kiểm tra tài khoản phụ, credential lưu trong công cụ tự động và ứng dụng có local password.
- Xem xét phiên/token đã được cấp mang quyền cũ; đừng chỉ thay nhóm trong directory rồi coi mọi quyền đã mất.
- Giám sát đăng nhập bất thường trong thời điểm chuyển vai trò, nhưng tránh mặc định mọi thay đổi manager đều phải reset password.

**Mật khẩu hợp lệ không hợp thức hóa quyền cũ.** Sau Mover, người dùng có thể xác thực bình thường nhưng bị từ chối tài nguyên không còn thuộc phạm vi công việc.

### 10.3. Leaver: ngăn tài khoản cũ bị khai thác

Tài khoản của người đã nghỉ có thể vẫn xuất hiện trong danh sách đăng nhập tại ứng dụng cục bộ, nhóm quyền hoặc dịch vụ ít được quản lý. Những danh tính này dễ bị bỏ quên trong inventory, đặc biệt khi đồng bộ SCIM/API thất bại.

Leaver cần:

1. Nhận sự kiện kết thúc từ HRIS/hợp đồng kèm ID ổn định và thời điểm hiệu lực.
2. Khóa tài khoản IdP và các tài khoản ứng dụng theo chính sách.
3. Thu hồi/kiểm soát mật khẩu ứng dụng cục bộ, phiên, refresh token, API key, PAT và credential phù hợp.
4. Thu hồi nhóm, role, quyền trực tiếp, ủy quyền và quyền đặc quyền tồn dư.
5. Kiểm tra kết quả từng ứng dụng; ghi rõ lệnh đã gửi, phản hồi và trạng thái thực tế đã xác minh.
6. Theo dõi mọi nỗ lực đăng nhập vào tài khoản đã terminated như tín hiệu an ninh, nhưng không kết luận chỉ từ số lần lỗi.

**Vô hiệu hóa một danh tính cần được xác minh trên đường truy cập thực tế**, không chỉ ở trạng thái hồ sơ HRIS.

### 10.4. Rehire và chuyển loại quan hệ

Khi người lao động trở lại hoặc Contractor chuyển thành Employee, tổ chức có thể liên kết lịch sử với cùng Person sau khi xác minh. Tuy nhiên, **không tự khôi phục mật khẩu, credential, phiên hay quyền đã bị thu hồi** từ quan hệ cũ. Cần đánh giá lại nguồn, thời điểm hiệu lực, MFA, ứng dụng và quyền theo quan hệ hiện tại.

## 11. Tài khoản đặc quyền và tài khoản dịch vụ

### 11.1. Tài khoản quản trị

Một tài khoản quản trị bị chiếm có thể có tác động lớn hơn tài khoản thông thường. Nên:

- Sử dụng xác thực chống phishing, step-up hoặc kiểm soát PAM theo mức rủi ro.
- Tách tài khoản và phiên quản trị khỏi hoạt động thông thường khi chính sách yêu cầu.
- Giới hạn quyền, thời gian sử dụng và giám sát thao tác đặc quyền.
- Cảnh báo ưu tiên khi có nhiều đăng nhập lỗi hoặc bất thường nhắm tới danh tính có quyền cao.
- Bảo vệ quy trình khôi phục và tài khoản khẩn cấp bằng biện pháp được phê duyệt; không dùng cấu hình yếu hơn chỉ vì tài khoản hiếm khi đăng nhập.

### 11.2. Service account và workload identity

Tài khoản dịch vụ là **danh tính phi con người**, có thể tồn tại ngoài vòng đời Employee. Một số hệ thống cũ vẫn dùng mật khẩu dài hạn cho job hoặc tác vụ. Nếu dùng chung mật khẩu yếu hoặc không xoay bí mật khi owner rời tổ chức, tài khoản dịch vụ cũng có thể tạo bề mặt rủi ro.

Phương án tốt:

1. Gắn **principal ID**, **owner team**, **workload**, **environment** và mục đích sử dụng rõ ràng.
2. Ưu tiên workload identity, chứng chỉ hoặc credential ngắn hạn khi nền tảng hỗ trợ; tránh mật khẩu dùng chung dài hạn.
3. Lưu bí mật trong secrets manager; không đặt trong source code, log hoặc ticket.
4. Giới hạn ứng dụng, nguồn được phép, phạm vi quyền và các điều kiện xác thực.
5. Phát hiện xác thực bất thường so với hành vi job thông thường.
6. Khi owner rời tổ chức, chuyển ownership và rà soát secret/quyền; không vô hiệu hóa tùy tiện workload sản xuất còn hợp lệ.

**Không nên miễn trừ tài khoản dịch vụ khỏi giám sát chỉ vì chúng không phải con người.** Đồng thời, cách điều tiết và kiểm soát của workload phải được thiết kế riêng để tránh làm gián đoạn dịch vụ hợp lệ.

## 12. Điều tra và ứng phó khi nghi ngờ password spraying

Một quy trình ứng phó có thể chia thành sáu bước:

### Bước 1. Xác thực tín hiệu và xác định phạm vi

Nhận cảnh báo từ SIEM/IdP, kiểm tra loại thất bại, số tài khoản duy nhất, ứng dụng, cửa sổ quan sát và sự kiện vận hành gần đó. Xem log có đầy đủ không và liệu IP/nguồn có đại diện cho nhiều người dùng hợp lệ.

### Bước 2. Ưu tiên tài khoản có nguy cơ cao

Xác định danh tính đặc quyền, tài khoản chưa có MFA mạnh, ứng dụng legacy, người đang nghỉ việc hoặc tài khoản có dấu hiệu xác thực mật khẩu thành công. Kết hợp với mức nhạy cảm dữ liệu và quyền thực tế thay vì chỉ sắp xếp theo số lần thất bại.

### Bước 3. Xác định có truy cập trái phép thành công hay không

Kiểm tra **kết quả xác thực cuối**, MFA outcome, phiên được phát hành, thiết bị, ứng dụng đích và hành động sau đăng nhập. Một sự kiện “password accepted” chưa chắc là phiên hoàn tất; nhưng một phiên hợp lệ có hoạt động bất thường cần xử lý theo quy trình sự cố.

### Bước 4. Kiểm soát và cô lập rủi ro

Áp dụng chính sách rủi ro: điều tiết/chặn hành vi đáng ngờ, yêu cầu xác thực tăng cường, thu hồi phiên/token, reset credential khi có dấu hiệu bị lộ hoặc khóa tài khoản phù hợp mức độ. Không xóa log và không khóa hàng loạt vô điều kiện khi có nguy cơ gây gián đoạn.

### Bước 5. Khôi phục và loại bỏ nguyên nhân

Sửa mật khẩu yếu hoặc tái sử dụng, chuyển sang MFA/phương thức chống phishing, đóng đường xác thực legacy, xử lý tài khoản mồ côi, rà soát role/entitlement và credential ngoài IdP. Với tài khoản đã bị chiếm, xem xét thay đổi liên quan như thiết bị MFA mới, phương thức recovery, OAuth grants hoặc quy tắc chuyển tiếp email bất thường nếu hệ thống tương ứng có chức năng đó.

### Bước 6. Kiểm chứng, lưu bằng chứng và cải thiện phát hiện

Đối chiếu IdP/SSO, ứng dụng và API đích, xác nhận phiên trái phép đã bị chặn trong phạm vi kỹ thuật. Lưu chuỗi thời gian, các quyết định và giới hạn quan sát; cập nhật bài học rút ra, tuning rule và kiểm soát tạo tài khoản.

### Luồng xử lý minh họa

~~~mermaid
flowchart TD
    A["SIEM / IdP phát hiện đăng nhập lỗi<br/>trên nhiều danh tính"] --> B["Kiểm tra chất lượng log và baseline"]
    B --> C{"Có bằng chứng<br/>bất thường đáng tin?"}
    C -->|Chưa| D["Theo dõi / điều chỉnh rule<br/>đối chiếu sự kiện vận hành"]
    C -->|Có| E["Xác định phạm vi tài khoản,<br/>ứng dụng, MFA, quyền đặc quyền"]
    E --> F{"Có phiên thành công<br/>hoặc dấu hiệu chiếm tài khoản?"}
    F -->|Có| G["Ứng phó sự cố<br/>thu hồi phiên/token, xác minh và khôi phục"]
    F -->|Chưa rõ| H["Giảm thiểu phù hợp<br/>điều tiết, MFA, giám sát"]
    G --> I["Đối soát trạng thái đích<br/>và lưu bằng chứng"]
    H --> I
    D --> I
    I --> J["Tối ưu phát hiện và vòng đời IAM"]
~~~

## 13. Một tình huống phòng thủ tổng hợp

**Bối cảnh:** tổ chức có SSO qua IdP cho phần lớn ứng dụng nhưng vẫn giữ một ứng dụng nội bộ dùng mật khẩu cục bộ. Trong cùng một ngày, SIEM ghi nhận nhiều lỗi sai mật khẩu trên các tài khoản ở ứng dụng nội bộ; một vài danh tính bị lỗi tại IdP, và một tài khoản của nhân viên đã nghỉ vẫn xuất hiện trong log ứng dụng.

| Phát hiện | Diễn giải cần kiểm chứng | Hành động phòng vệ |
| --- | --- | --- |
| Nhiều tài khoản có lỗi tại ứng dụng nội bộ. | Có thể là password spraying hoặc lỗi cấu hình tập trung. | Kiểm tra số danh tính, nguồn/client, lịch triển khai và kết quả đăng nhập. |
| Một tài khoản có sự kiện mật khẩu đúng nhưng MFA bị từ chối ở IdP. | Mật khẩu có thể đã bị lộ hoặc đoán đúng, nhưng chưa chắc có phiên hợp lệ. | Xác minh người dùng, đánh giá thiết bị, đổi credential và xử lý MFA theo chính sách. |
| Một tài khoản đã terminated vẫn có lỗi ở ứng dụng nội bộ. | Có thể là tài khoản cục bộ chưa deprovision hoặc chỉ còn bản ghi lịch sử. | Kiểm tra trạng thái thật tại ứng dụng; disable và thu hồi quyền nếu còn hoạt động. |
| Một nhóm người dùng cùng IP nội bộ xuất hiện lỗi. | Có thể do NAT, VPN hoặc một ứng dụng quản lý mật khẩu cấu hình sai. | Không kết luận từ IP duy nhất; đối chiếu thiết bị, ứng dụng và sự kiện vận hành. |
| Một phiên sau đăng nhập có hoạt động khác thường tại dữ liệu nhạy cảm. | Có nguy cơ chiếm tài khoản và khai thác entitlement. | Kích hoạt ứng phó sự cố, đối soát quyền, phiên và hành động nghiệp vụ. |

**Kết quả mong muốn:** đội IAM và SOC không chỉ dừng chiến dịch thử mật khẩu mà còn tìm ra **đường xác thực chưa được kiểm soát**, tài khoản Leaver chưa bị khóa và quyền/phiên còn tồn dư. Việc phát hiện thành công phải đi kèm kiểm chứng ở cả IdP và ứng dụng cục bộ.

## 14. Kiểm toán và bảo vệ dữ liệu xác thực

### 14.1. Chuỗi bằng chứng nên có

Một sự kiện an ninh cần có khả năng truy vết:

| Bằng chứng | Ý nghĩa |
| --- | --- |
| **Nguồn sự kiện** | IdP, ứng dụng, directory hoặc API gateway nào tạo log. |
| **Danh tính** | Subject/account ID, trạng thái JML, độ nhạy của tài khoản. |
| **Thời gian** | Thời điểm xảy ra, thời điểm SIEM nhận và thời điểm phản ứng. |
| **Kết quả xác thực** | Mật khẩu sai/đúng, MFA được yêu cầu/thành công/thất bại, policy từ chối. |
| **Ngữ cảnh** | Ứng dụng, giao thức, IP/thiết bị theo chính sách thu thập. |
| **Phân tích** | Rule/baseline, lý do alert, false-positive assessment. |
| **Quyết định và thực thi** | Ai phê duyệt, biện pháp điều tiết/khóa/reset, trạng thái phiên và token. |
| **Kết quả tại đích** | Tài khoản/quyền bị hạn chế hay thu hồi thực tế, ứng dụng nào còn lỗi. |
| **Ngoại lệ** | Hệ thống không có log, quyền chưa xác minh, owner và hạn xử lý. |

### 14.2. Giữ log mà không tạo kho bí mật

Nhật ký phục vụ phòng vệ có thể chứa thông tin nhạy cảm về tài khoản, IP, vị trí và hành vi sử dụng dịch vụ. Cần áp dụng **phân quyền đọc**, thời hạn lưu theo căn cứ, mã hóa, ghi vết truy xuất và tối thiểu hóa trường dữ liệu.

Không thu thập mật khẩu được nhập, mật khẩu “nghi ngờ đã thử”, mã OTP, passkey private key, access token, refresh token hoặc cookie phiên để điều tra password spraying. Thông tin **đăng nhập bị từ chối vì sai mật khẩu** là đủ để phát hiện lỗi; giá trị mật khẩu không nên xuất hiện trong SIEM.

Không thấy log **không chứng minh không có hoạt động** nếu connector đã ngừng gửi dữ liệu hoặc ứng dụng không ghi đủ sự kiện. Cần giám sát độ trễ thu thập, bao phủ nguồn log và tính đúng đắn của kết quả phân loại.

## 15. Chỉ số đo hiệu quả phòng vệ

| Chỉ số | Cách đo gợi ý | Câu hỏi quản trị |
| --- | --- | --- |
| **Bao phủ MFA chống phishing** | Tài khoản theo chính sách đã đăng ký và sử dụng phương thức phù hợp / tổng tài khoản thuộc phạm vi. | Đường truy cập nhạy cảm đã giảm phụ thuộc mật khẩu chưa? |
| **Bao phủ các đường xác thực** | Ứng dụng/gateway quan trọng có log xác thực và kiểm soát tương xứng / tổng đích phải quản lý. | Có đường local/legacy ngoài IdP không? |
| **Tỷ lệ sự kiện đăng nhập được phân loại chính xác** | Sự kiện có kết quả và error code chuẩn hóa / tổng sự kiện. | Rule có nhầm sai mật khẩu với lỗi MFA/policy không? |
| **Số tài khoản duy nhất chịu ảnh hưởng bởi chiến dịch xác thực nghi vấn** | Đếm distinct subject ID theo sự kiện đã tương quan. | Quy mô nguy cơ là bao nhiêu? |
| **Tỷ lệ cảnh báo được xác minh** | Alert được điều tra và phân loại / tổng alert theo phạm vi. | Chất lượng điều tra và false positive ra sao? |
| **Thời gian phát hiện và kiểm soát** | Từ sự kiện đầu tiên có thể xác định đến alert và hành động có hiệu lực. | Có kịp giảm rủi ro không? |
| **Đăng nhập hoàn tất bất thường sau chuỗi lỗi** | Số sự kiện xác thực thành công cần điều tra và kết quả xử lý. | Có dấu hiệu chiếm tài khoản không? |
| **Tài khoản Leaver còn đường xác thực hoạt động** | Account/app còn xác thực được sau thời điểm phải khóa, đã xác minh. | Quy trình deprovision có bỏ sót hệ thống không? |
| **Tỷ lệ tài khoản dùng mật khẩu yếu hoặc bị lộ** | Tài khoản bị xác định vi phạm chính sách đặt/đổi mật khẩu / tổng tài khoản được đánh giá. | Chính sách mật khẩu có hiệu quả không? |
| **Số trường hợp lockout gây gián đoạn hợp lệ** | Incident/ticket do khóa nhầm hoặc cơ chế tự động gây ra. | Kiểm soát có làm ảnh hưởng người dùng không? |
| **Bao phủ tài khoản dịch vụ** | Service account có owner, phương thức xác thực và chính sách hiện hành / tổng account kiểm kê. | Có tài khoản máy bị bỏ quên không? |

Không nên đặt một ngưỡng ngầm định như “số lần sai đủ ít nên an toàn”. Sự phù hợp phụ thuộc rủi ro, quy mô tenant, sản phẩm IdP, mẫu làm việc và mức độ đầy đủ của telemetry. Cần công bố phạm vi đo và các hệ thống chưa được bao phủ.

## 16. Checklist tự đánh giá

1. Đã phân biệt **password spraying**, brute-force, credential stuffing và lỗi cấu hình tích hợp chưa?
2. SIEM có đếm **số tài khoản duy nhất** trong một chiến dịch, không chỉ số lỗi của từng account không?
3. Đã chuẩn hóa error code để phân biệt **mật khẩu sai**, lỗi MFA, policy từ chối và tài khoản không tồn tại chưa?
4. Có quan sát các đường **IdP/SSO, VPN, ứng dụng cục bộ, directory và legacy authentication** không?
5. Có xử lý được dữ liệu từ NAT/VPN, proxy, nguồn phân tán và cửa sổ thời gian khác nhau để giảm cảnh báo sai không?
6. Có giám sát việc **mật khẩu được chấp nhận nhưng đăng nhập chưa hoàn tất MFA**, cùng phiên thật sự được phát hành không?
7. Chính sách mật khẩu có chặn các giá trị phổ biến/đã lộ, hỗ trợ mật khẩu duy nhất và password manager không?
8. Đường đăng nhập quan trọng có **MFA chống phishing/passkey** và không còn đường fallback yếu ngoài kiểm soát không?
9. Có rate limiting/risk-based controls mà không tự động khóa hàng loạt người dùng hợp lệ không?
10. **Joiner** có kích hoạt credential đúng người, đúng ngày; **Mover** có rà soát quyền/credential cũ; **Leaver** có khóa các tài khoản đích không?
11. Các tài khoản admin, break-glass và service account có biện pháp bảo vệ, owner và log riêng phù hợp rủi ro không?
12. Khi nghi chiếm tài khoản, có thu hồi phiên/token, kiểm tra MFA/recovery, quyền ứng dụng và kết quả thực tế tại đích không?
13. Nhật ký có đầy đủ chuỗi từ phát hiện đến kiểm chứng mà **không lưu raw password/token/OTP** không?
14. Có đo bao phủ, false positive, thời gian xử lý, tài khoản tồn dư và tác động lockout để cải thiện liên tục không?

**Ghi nhớ:** **Password spraying** nhắm vào **nhiều tài khoản với số lần thử mật khẩu ít trên từng tài khoản**, nên phòng vệ không thể chỉ dựa vào đếm lỗi và khóa một tài khoản đơn lẻ. Cần quan sát đa hệ thống, phát hiện theo **chiều rộng danh tính**, kiểm chứng tín hiệu thành công, áp dụng mật khẩu mạnh và duy nhất, **MFA chống phishing/passkey**, hạn chế đường xác thực cũ và xử lý sự cố có kiểm chứng. Gắn các biện pháp với **Joiner–Mover–Leaver** giúp tài khoản được tạo đúng, quyền thay đổi đúng và đường xác thực của người đã rời tổ chức được thu hồi, giảm rủi ro truy cập tồn dư.
