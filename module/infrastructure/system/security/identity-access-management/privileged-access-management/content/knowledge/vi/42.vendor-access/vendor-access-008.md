# Vendor offboarding: thu hồi quyền nhà cung cấp trong hệ thống PAM

## 1. Offboarding phải chấm dứt được khả năng truy cập

Vendor offboarding là quá trình kết thúc quyền truy cập của nhà cung cấp và những danh tính kỹ thuật họ sử dụng, đồng thời bàn giao trách nhiệm vận hành, xử lý credential còn tồn tại và giữ lại bằng chứng cần thiết. Trong quản lý truy cập đặc quyền (PAM), kết quả cần đạt không chỉ là tài khoản đã bị vô hiệu hóa, mà là nhà cung cấp không còn thực hiện được hành động đặc quyền ngoài phạm vi còn được phê duyệt.

Một hợp đồng kết thúc không tự làm hết hiệu lực mọi quyền liên quan. Nhà cung cấp có thể đã có phiên SSH đang mở, token truy cập đám mây, khóa SSH trong tài khoản dùng chung, API key của công cụ hỗ trợ hoặc bản sao mật khẩu được checkout từ vault. Nếu chỉ xóa tài khoản đăng nhập cổng PAM, một số đường truy cập đó có thể vẫn hoạt động.

Có thể hình dung kết quả offboarding bằng bốn câu hỏi:

1. Danh tính nào và đường truy cập nào phải kết thúc?
2. Phiên, token và credential nào còn khả năng sử dụng?
3. Tác vụ vận hành nào phải bàn giao để không làm gián đoạn dịch vụ?
4. Bằng chứng nào chứng minh quyền đã bị thu hồi, thay vì chỉ ghi nhận rằng một yêu cầu đã được gửi?

Ví dụ, công ty thuê Vendor Atlas bảo trì cụm cơ sở dữ liệu. Hai kỹ sư đăng nhập qua liên kết danh tính, yêu cầu quyền JIT rồi mở phiên thông qua PAM. Họ còn dùng một tài khoản dịch vụ để đẩy báo cáo kiểm tra hằng đêm. Khi hợp đồng kết thúc, việc khóa hai danh tính con người chưa giải quyết được phiên đang chạy, credential của job báo cáo và quyền quản trị tại cơ sở dữ liệu.

Mục tiêu của bài học là xây dựng một quy trình có thể thực thi và kiểm chứng cho tình huống đó, từ xác định phạm vi đến đóng hồ sơ.

## 2. Phân biệt kết thúc hợp đồng, thay người và xử lý sự cố

Không phải mọi lần offboarding đều có cùng phạm vi hoặc cùng trình tự.

| Tình huống | Phạm vi cần xử lý | Điểm cần chú ý |
|---|---|---|
| Một kỹ sư rời đội hỗ trợ | Danh tính, phiên và quyền của cá nhân đó; credential dùng chung mà họ biết | Các kỹ sư khác có thể vẫn được phép làm việc |
| Nhà cung cấp kết thúc hợp đồng | Toàn bộ quan hệ truy cập theo hợp đồng, gồm người, tài khoản kỹ thuật và kênh hỗ trợ | Bàn giao chủ sở hữu và phụ thuộc vận hành trước mốc kết thúc |
| Đổi đối tác hỗ trợ | Thu hồi phía cũ, cấp phạm vi riêng cho phía mới | Không chuyển nguyên tài khoản hoặc mật khẩu giữa hai nhà cung cấp |
| Tạm đình chỉ vì rủi ro | Chặn quyền ngay trong phạm vi được quyết định | Có thể chưa xóa danh tính để phục vụ điều tra và khôi phục có kiểm soát |
| Nghi ngờ credential bị lộ | Khoanh vùng danh tính, credential, hệ thống đích và khả năng truy cập còn lại | Xử lý theo quy trình ứng phó sự cố; không chờ lịch kết thúc hợp đồng |

Với offboarding có kế hoạch, tổ chức thường có thời gian chuyển job, kiểm tra phụ thuộc và chọn cửa sổ thay đổi. Với nghi ngờ xâm nhập, yêu cầu ngăn chặn có thể phải thực hiện trước công việc bàn giao thông thường. Người chỉ huy sự cố hoặc vai trò được ủy quyền quyết định thứ tự dựa trên rủi ro, đồng thời ghi nhận ảnh hưởng và ngoại lệ.

Không dùng một thứ tự máy móc như “luôn đổi mật khẩu trước khi khóa tài khoản”. Đổi một credential sớm có thể làm dừng job quan trọng, còn trì hoãn thu hồi để hoàn tất bàn giao có thể để lại đường truy cập cho đối tượng đang bị nghi ngờ.

## 3. Lập bản đồ quyền theo quan hệ nhà cung cấp

### 3.1. Khóa định danh của một đợt offboarding

Một đợt offboarding nên gắn với mã nhà cung cấp, mã hợp đồng hoặc phạm vi hỗ trợ xác định. Tên miền email đơn thuần không đủ để xác định toàn bộ đối tượng: nhà thầu phụ có thể dùng miền khác, tài khoản dịch vụ không có email và một đối tác có thể đang thực hiện nhiều hợp đồng.

Hồ sơ tối thiểu cần biết:

- Mã nhà cung cấp, hợp đồng và lý do kết thúc hoặc thu hẹp truy cập.
- Danh sách cá nhân cùng định danh bất biến trong hệ thống danh tính.
- Sponsor nội bộ, chủ sở hữu dịch vụ và chủ sở hữu hệ thống đích.
- Mốc cắt quyền chính xác, múi giờ và khoảng thời gian bàn giao được duyệt.
- Môi trường, hệ thống, tài khoản đặc quyền và credential liên quan.
- Người thực thi, người kiểm chứng và người được phép chấp nhận ngoại lệ.

Mốc thời gian phải đủ rõ để vận hành. “Hết ngày thứ Sáu” không rõ bằng một dấu thời gian có độ lệch múi giờ. Nếu quyền hết lúc 18:00 giờ Việt Nam, lịch thay đổi, TTL của quyền tạm thời và bằng chứng kiểm tra phải được quy về cùng một mốc.

### 3.2. Theo dõi tất cả lớp truy cập

| Lớp | Đối tượng cần kiểm kê | Câu hỏi khi thu hồi |
|---|---|---|
| Danh tính | Tài khoản cá nhân, guest, tài khoản cục bộ, nhóm liên kết | Có danh tính phụ hoặc nhóm lồng nhau cấp lại quyền không? |
| Đường vào | VPN, ZTNA, bastion, cổng hỗ trợ, allowlist mạng | Nhà cung cấp còn đến được dịch vụ quản trị bằng đường nào? |
| PAM | Vai trò, safe/vault, quyền checkout, yêu cầu JIT, phạm vi JEA | Có thể yêu cầu quyền mới hoặc nhận lại secret không? |
| Phiên đang hoạt động | SSH, RDP, shell, console web, phiên proxy | Phiên nào cần kết thúc và ai xác nhận đã kết thúc? |
| Credential | Mật khẩu, khóa SSH, API key, certificate, token, recovery code | Có thể tiếp tục dùng credential đã lấy trước đó không? |
| Hệ thống đích | Nhóm quản trị, sudo, role cơ sở dữ liệu, IAM role, trust | Quyền có tồn tại độc lập với PAM không? |
| Tự động hóa | Service account, service principal, pipeline, agent, lịch chạy | Ai sở hữu, credential nằm ở đâu và thay đổi có làm hỏng job không? |
| Dữ liệu và kênh hỗ trợ | Kho chia sẻ, bản xuất log, cổng ticket, bản sao cấu hình | Ai xử lý bàn giao, hoàn trả hoặc xác nhận xóa theo thỏa thuận? |

Không suy luận rằng kiểm kê PAM đã bao phủ mọi hệ thống. Một tài khoản cục bộ được tạo trong lần hỗ trợ khẩn cấp có thể chưa được onboard vào vault. Một trust hoặc chính sách cấp role tại hệ thống đích có thể cho phép truy cập mà không cần mở cổng PAM.

### 3.3. Tài khoản cá nhân và credential dùng chung

Đối với tài khoản cá nhân, thu hồi đúng danh tính giúp duy trì khả năng truy vết. Đối với credential dùng chung mà một kỹ sư đã biết, vô hiệu hóa danh tính của kỹ sư đó không làm họ quên credential.

Cần xác định phạm vi tiếp xúc:

- Credential có từng được hiển thị hoặc tải xuống không?
- Phiên được broker có che credential hoàn toàn không, và kiểm soát đó có bằng chứng gì?
- Nhà cung cấp có quyền tạo credential mới hoặc thay đổi cơ chế xác thực không?
- Có quyền xem secret trong pipeline, file cấu hình hoặc công cụ triển khai không?
- Có người hoặc job hợp lệ khác đang dùng cùng credential không?

Khi có khả năng nhà cung cấp vẫn giữ credential còn hiệu lực, kế hoạch phải bao gồm thay thế hoặc vô hiệu hóa credential đó và cập nhật các consumer hợp lệ. Không mặc định luân chuyển mọi credential trong tổ chức; phạm vi phải dựa trên khả năng tiếp xúc, quyền tạo thêm credential và mức độ tin cậy của kết quả kiểm kê.

## 4. Quy định trách nhiệm và điều kiện đóng hồ sơ

Offboarding thường đi qua nhiều đội. Nếu mỗi đội chỉ xác nhận “đã làm phần mình” mà không có người tổng hợp, các đường truy cập còn lại dễ bị bỏ sót.

| Vai trò | Trách nhiệm điển hình | Bằng chứng bàn giao |
|---|---|---|
| Sponsor hoặc chủ hợp đồng | Xác nhận phạm vi và mốc kết thúc; chỉ định người tiếp nhận | Yêu cầu offboarding có phê duyệt |
| Chủ hệ thống hoặc dịch vụ | Xác định phụ thuộc, chấp nhận thay đổi và xác nhận vận hành | Danh sách hệ thống, consumer và kết quả kiểm tra dịch vụ |
| Đội IAM | Thu hồi danh tính, nhóm, liên kết và phiên thuộc phạm vi quản lý | Nhật ký thay đổi, kết quả đọc lại trạng thái |
| Đội PAM | Thu hồi entitlement, yêu cầu quyền, checkout và phiên qua PAM | Audit event, trạng thái phiên và tham chiếu sự kiện rotation |
| Đội quản trị hệ thống đích | Xử lý tài khoản, khóa, token và quyền ngoài PAM | Kết quả đọc lại cấu hình quyền, thử nghiệm từ chối |
| SOC hoặc đội an ninh | Theo dõi truy cập sau mốc cắt, xử lý dấu hiệu bất thường | Kết quả truy vấn, cảnh báo và hướng xử lý |
| Người kiểm chứng | Đối chiếu toàn bộ hồ sơ với tiêu chí hoàn thành | Biên bản xác minh, phần còn tồn tại và kết luận |

Đối với hệ thống nhạy cảm, người kiểm chứng nên khác người thực thi theo chính sách của tổ chức. Tổ chức nhỏ có thể sử dụng người rà soát được chỉ định hoặc đối chiếu tự động có lưu kết quả, nhưng vẫn cần làm rõ ai chịu trách nhiệm chấp nhận phần rủi ro còn lại.

Một thay đổi “đã gửi thành công” chưa phải bằng chứng rằng thay đổi có hiệu lực. Ví dụ, API có thể tiếp nhận yêu cầu vô hiệu hóa nhưng quá trình đồng bộ còn đang chạy. Vì vậy, hồ sơ cần phân biệt thao tác được yêu cầu, trạng thái đọc lại và hành vi truy cập được quan sát.

## 5. Quy trình offboarding có kế hoạch

### 5.1. Chuẩn bị trước mốc cắt quyền

Tạo hồ sơ và đối chiếu bản đồ quyền với danh sách do nhà cung cấp, sponsor, IAM, PAM và chủ hệ thống cung cấp. Nếu nguồn dữ liệu khác nhau, ghi rõ đối tượng chưa xác định thay vì loại bỏ vì “không thấy trong PAM”.

Bước chuẩn bị nên hoàn tất các việc sau:

1. Chỉ định chủ sở hữu nội bộ cho service account, lịch chạy, agent và công cụ do nhà cung cấp quản lý.
2. Bàn giao cấu hình vận hành, tài liệu khôi phục và thông tin phụ thuộc qua kênh được duyệt.
3. Xác định credential phải thay, consumer phải cập nhật và cách xác nhận cập nhật thành công.
4. Chuẩn bị tài khoản hoặc danh tính thay thế do tổ chức quản lý nếu dịch vụ vẫn cần chạy.
5. Kiểm tra năng lực truy cập của đội nội bộ, bao gồm đường khôi phục được kiểm soát.
6. Chốt cửa sổ thực thi, người trực xử lý lỗi và tiêu chí dừng hoặc chuyển sang phương án ứng cứu.
7. Chặn việc tạo mới quyền dài hạn ngoài kế hoạch; rà soát những yêu cầu đang chờ hoặc đã được phê duyệt cho tương lai.

Không yêu cầu nhà cung cấp gửi mật khẩu hiện tại qua email hoặc chèn secret vào ticket để “bàn giao”. Credential nên được quản lý qua vault và cơ chế cấp phát phù hợp. Tài liệu bàn giao tham chiếu đối tượng secret hoặc phiên bản, không chứa giá trị secret.

### 5.2. Kiểm soát giai đoạn chuyển tiếp

Nếu nhà cung cấp còn một nhiệm vụ bàn giao sau ngày kết thúc hỗ trợ thường lệ, cần định nghĩa một phạm vi tạm riêng: người nào, hệ thống nào, hành động nào, lý do và thời điểm tự hết hạn.

JIT và JEA có ích khi chuyển tiếp: quyền chỉ mở trong thời gian ngắn và chỉ cho phép thao tác cần thiết. Tuy nhiên, JIT không thay thế offboarding. Một danh tính vẫn đủ điều kiện yêu cầu quyền có thể được cấp lại sau khi grant hiện tại hết TTL.

Cần kiểm tra cả quyền đang được kích hoạt lẫn khả năng được kích hoạt trong tương lai, bao gồm lịch quyền, approval còn hiệu lực và membership làm điều kiện cấp quyền.

### 5.3. Thực thi tại mốc cắt

Một trình tự thường dùng cho đợt có kế hoạch là:

1. Chặn yêu cầu hoặc cấp mới quyền từ những danh tính thuộc phạm vi kết thúc.
2. Vô hiệu hóa hoặc đình chỉ danh tính, membership và đường vào theo kế hoạch.
3. Kết thúc phiên hiện hữu và xử lý session, token theo khả năng của từng hệ thống.
4. Thu hồi credential và quyền tại hệ thống đích; thay credential dùng chung đã bị tiếp xúc.
5. Cập nhật consumer hợp lệ và xác minh dịch vụ tiếp tục hoạt động.
6. Đọc lại trạng thái và thực hiện các kiểm tra từ chối được phê duyệt.
7. Theo dõi sau thay đổi, xử lý ngoại lệ rồi đóng hồ sơ khi đạt tiêu chí.

Các bước có thể cần chạy phối hợp hoặc thay đổi thứ tự để đáp ứng yêu cầu ngăn chặn và tính sẵn sàng. Không để việc thực thi tuần tự tạo một khoảng hở không được quản lý, ví dụ tắt VPN nhưng để API công khai với token cũ hoạt động thêm nhiều giờ.

## 6. Thu hồi theo vòng đời phiên và credential

### 6.1. Thu hồi quyền trong PAM

Kiểm tra và thu hồi:

- Vai trò quản trị hoặc vận hành PAM được cấp cho nhà cung cấp.
- Quyền xem, checkout, thay đổi hoặc phê duyệt truy cập vào safe/vault.
- Quyền khởi tạo phiên tới tài khoản và hệ thống đích.
- Khả năng yêu cầu JIT, eligibility, lịch grant và các yêu cầu còn chờ.
- Mapping nhóm liên kết hoặc cơ chế provisioning có thể cấp lại quyền.
- Tài khoản tích hợp và API credential dùng để tự động gọi PAM.

Nếu chỉ xóa grant hiện tại nhưng giữ nhóm nguồn, lần đồng bộ tiếp theo có thể cấp lại entitlement. Vì vậy cần xử lý nguồn cấp quyền và xác minh qua ít nhất một chu kỳ đồng bộ có liên quan, hoặc dùng kết quả kiểm tra tương đương phù hợp với hệ thống.

Không xóa lịch sử truy cập, approval và recording cùng lúc với danh tính chỉ để “dọn sạch”. Việc giữ dữ liệu phải theo chính sách lưu trữ, quyền truy cập bằng chứng và yêu cầu bảo toàn phục vụ điều tra nếu có.

### 6.2. Kết thúc phiên đang mở

Vô hiệu hóa đăng nhập mới không đồng nghĩa với kết thúc phiên cũ. Một phiên SSH hoặc tiến trình được khởi tạo trước mốc cắt có thể cần xử lý riêng tại bastion, proxy hoặc máy đích.

Đối với mỗi loại phiên, cần biết:

- Phiên do PAM broker hay kết nối trực tiếp?
- Điểm nào có quyền kết thúc và có nhìn thấy đầy đủ phiên?
- Đóng kết nối có đồng thời dừng tác vụ chạy nền hay không?
- Có kênh truyền file hoặc phiên quản trị thứ hai nằm ngoài danh sách không?
- Bằng chứng nào xác nhận phiên đã kết thúc ở phía đích?

Không mặc định đóng cửa sổ giao diện là đã thu hồi phiên. Khi cần dừng tiến trình, chủ dịch vụ phải phân biệt tiến trình hỗ trợ cần chấm dứt với tác vụ vận hành hợp lệ đã được bàn giao. Mọi quyết định để một tác vụ tiếp tục cần có người nhận trách nhiệm và quyền điều khiển nội bộ.

### 6.3. Mật khẩu, khóa SSH và certificate

Đối với mật khẩu từng được checkout, việc xóa quyền truy cập vault chỉ ngăn lấy mật khẩu về sau. Nếu mật khẩu tại đích chưa thay, bản sao cũ có thể vẫn dùng được.

Một vòng thay credential đầy đủ cần xác nhận:

1. Credential mới được thiết lập tại hệ thống đích.
2. Vault lưu đúng phiên bản hiện hành và việc đồng bộ không lỗi.
3. Consumer hợp lệ nhận được phiên bản mới theo cơ chế được thiết kế.
4. Phiên bản cũ bị từ chối theo phạm vi kiểm tra đã duyệt.
5. Dịch vụ và job liên quan hoạt động bình thường.

Đối với SSH, kiểm kê khóa trong tài khoản đích, nguồn cấu hình quản lý khóa và khả năng cấp certificate. Xóa một khóa khỏi một máy không đủ nếu công cụ quản lý cấu hình sẽ thêm lại khóa đó. Nếu dùng certificate ngắn hạn, cần xử lý khả năng cấp mới, phạm vi trust, principal và cách thu hồi có sẵn; thời hạn ngắn vẫn để lại khoảng hiệu lực cần được đánh giá.

Không sao chép private key của nhà cung cấp cho đội mới. Tạo danh tính và credential mới để duy trì trách nhiệm riêng cho từng bên.

### 6.4. API key và token

API key dài hạn cần bị vô hiệu hóa hoặc thay thế tại nơi xác thực thực sự. Xóa key khỏi file cấu hình hoặc vault không tự làm key cũ mất hiệu lực tại dịch vụ phát hành.

Đối với token, cần phân biệt access token, refresh token, phiên đăng nhập và quyền phát hành token mới. Cơ chế thu hồi phụ thuộc từng nền tảng: một số token có thể còn được chấp nhận đến hết hạn hoặc đến khi hệ thống đích nhận được thay đổi chính sách.

Do đó, không đặt tiêu chí “revoke token thành công” chỉ dựa vào phản hồi của một API. Cần xác minh hành vi tại resource, hoặc ghi rõ giới hạn thu hồi, thời điểm hết hiệu lực dự kiến và kiểm soát bù đã được chấp thuận. Kiểm soát bù có thể là chặn danh tính ở phía resource, giới hạn đường mạng hoặc áp dụng cơ chế từ chối phiên phù hợp với nền tảng.

Nếu không thể chứng minh hết khả năng truy cập trong khoảng thời gian yêu cầu, đó là ngoại lệ hoặc sự cố cần xử lý, không phải một mục được đánh dấu hoàn tất.

## 7. Bàn giao tài khoản dịch vụ và tự động hóa

Một service account không rời công ty theo cách con người rời công ty. Nếu tài khoản đó tiếp tục tồn tại nhưng không có chủ sở hữu nội bộ, tổ chức đã giữ lại một phần quyền nhà cung cấp mà không quản lý rõ ràng.

Với mỗi danh tính kỹ thuật, cần quyết định một trong ba hướng:

- **Ngừng sử dụng:** dừng lịch chạy hoặc agent, thu hồi credential và quyền, xác minh không còn consumer cần thiết.
- **Chuyển quyền quản lý nội bộ:** gán owner, rà soát least privilege, thay credential từng bị nhà cung cấp biết và đưa vào chu kỳ quản trị.
- **Thay bằng danh tính mới:** chuyển consumer sang danh tính do tổ chức kiểm soát, kiểm tra vận hành rồi thu hồi danh tính cũ.

Quyết định nên dựa vào trách nhiệm, phạm vi quyền và khả năng truy vết. Nếu tài khoản cũ được nhiều bên dùng chung hoặc có lịch sử quyền khó kiểm kê, tạo danh tính mới có thể giúp làm rõ phạm vi; vẫn phải kiểm tra các phụ thuộc trước khi kết thúc tài khoản cũ.

### Ví dụ: job báo cáo do nhà cung cấp vận hành

Job báo cáo hằng đêm dùng tài khoản đọc dữ liệu nhưng đang có thêm quyền cấu hình không cần thiết. Credential nằm trong vault và một file cấu hình cũ trên máy agent.

Kế hoạch bàn giao gồm:

1. Chủ dịch vụ nội bộ tiếp nhận job và danh sách dữ liệu đầu ra.
2. Tạo hoặc điều chỉnh danh tính phù hợp với quyền đọc thực sự cần thiết.
3. Cập nhật agent sang cơ chế lấy credential được quản lý.
4. Kiểm tra một lần chạy đại diện và xử lý lỗi truy cập nếu có.
5. Thu hồi credential cũ, xử lý file cấu hình theo chính sách và xác minh job không còn phụ thuộc vào nó.
6. Kiểm tra hoạt động sau mốc cắt, đặc biệt các lịch chạy ít thường xuyên như cuối tuần hoặc cuối tháng.

Một lần chạy thử thành công chưa chứng minh mọi consumer đã chuyển. Cần đối chiếu inventory, cấu hình và lịch chạy để xác định khoảng theo dõi thích hợp. Nếu chưa thể quan sát một job cuối tháng, hồ sơ phải thể hiện trách nhiệm theo dõi hoặc bằng chứng kiểm tra thay thế, thay vì bỏ qua phụ thuộc đó.

## 8. Xác minh bằng trạng thái và hành vi

### 8.1. Ma trận kiểm tra sau thu hồi

| Hạng mục | Kiểm tra trạng thái | Kiểm tra hành vi trong phạm vi được duyệt | Kết quả mong đợi |
|---|---|---|---|
| Danh tính cá nhân | Tài khoản bị đình chỉ hoặc vô hiệu hóa; nhóm bị gỡ | Kiểm tra đăng nhập bằng danh tính thử nghiệm phù hợp hoặc xác nhận từ cơ chế kiểm tra được duyệt | Không tạo được phiên mới |
| JIT/JEA và PAM | Eligibility, mapping và entitlement đã thu hồi | Kiểm tra không thể yêu cầu, phê duyệt hoặc khởi tạo quyền mới | Yêu cầu bị từ chối |
| Phiên hiện hữu | Không còn phiên thuộc phạm vi cần chấm dứt | Đối chiếu phía proxy và hệ thống đích | Không còn kênh điều khiển đặc quyền |
| Credential cũ | Credential bị vô hiệu hóa, thay thế hoặc hết hiệu lực được xác minh | Thử có kiểm soát qua cơ chế kiểm tra credential | Credential cũ bị từ chối |
| Quyền ngoài PAM | Nhóm, role, khóa và trust tại đích đã xử lý | Kiểm tra đường truy cập đại diện | Không còn đường truy cập ngoài phạm vi |
| Consumer nội bộ | Cấu hình và owner đã cập nhật | Kiểm tra chức năng và job quan trọng | Dịch vụ hoạt động với danh tính hợp lệ |
| Tự cấp lại quyền | Nguồn provisioning và chính sách đã cập nhật | Kiểm tra sau đồng bộ hoặc đánh giá quy tắc tương đương | Quyền không tái xuất hiện |

Không thu thập mật khẩu cá nhân của kỹ sư nhà cung cấp để thực hiện kiểm tra. Thử nghiệm phải dùng cơ chế được tổ chức phê duyệt, không tạo một tài khoản tạm có quyền rộng chỉ để kiểm tra offboarding.

Kiểm tra credential cũ cũng không phải yêu cầu lưu credential trong ticket. Có thể dùng chức năng kiểm tra của vault, môi trường thử nghiệm phù hợp hoặc một bước xác minh được thiết kế với giá trị secret không bị ghi log. Nếu thử nghiệm có nguy cơ khóa tài khoản hay gây gián đoạn, cần lựa chọn cách xác minh thay thế và ghi rõ giới hạn.

### 8.2. Giới hạn của kết quả kiểm tra âm tính

Một lần truy cập thất bại chỉ chứng minh đường truy cập, danh tính và thời điểm đã kiểm tra. Nó không tự chứng minh mọi quyền đã biến mất.

Ví dụ, VPN từ chối kết nối chưa chứng minh API key trên một endpoint công khai đã bị thu hồi. SSH bằng tài khoản cá nhân bị từ chối chưa chứng minh khóa của tài khoản dùng chung đã bị gỡ.

Vì vậy cần kết hợp bản đồ quyền, đọc lại cấu hình, kết quả kiểm tra và quan sát log. Nếu inventory không đầy đủ, kết luận phải thể hiện phần chưa xác định và chủ thể xử lý.

## 9. Bằng chứng, dữ liệu bàn giao và quyền riêng tư

Hồ sơ offboarding nên cho phép người khác trả lời được “ai thu hồi cái gì, khi nào, bằng cách nào và dựa vào đâu để kết luận”.

Một bộ bằng chứng có thể gồm:

- Yêu cầu được phê duyệt cùng phạm vi và mốc cắt.
- Inventory danh tính, entitlement, credential và consumer tại thời điểm thực thi.
- Tham chiếu audit event của IAM, PAM và hệ thống đích.
- Kết quả kết thúc phiên và trạng thái xử lý recording.
- Tham chiếu sự kiện thay hoặc vô hiệu hóa credential, không chứa giá trị secret.
- Kết quả đọc lại và kiểm tra từ chối, kèm thời gian và hệ thống được kiểm tra.
- Kết quả kiểm tra vận hành sau bàn giao.
- Ngoại lệ, kiểm soát bù, người chấp nhận và thời điểm hết hạn.
- Kết luận kiểm chứng và người phê duyệt đóng hồ sơ.

Dữ liệu nhà cung cấp đã nhận cần được xử lý theo hợp đồng và chính sách áp dụng: hoàn trả, chuyển giao hoặc xác nhận xóa qua quy trình có thẩm quyền. Xóa quyền trên kho chia sẻ không tự chứng minh bản tải xuống hoặc bản sao lưu bên ngoài đã bị xóa.

Không ghi nhận một chứng nhận xóa dữ liệu như bằng chứng kỹ thuật rằng mọi bản sao không còn tồn tại. Hồ sơ cần mô tả đúng bằng chứng đang có và giới hạn xác minh. Nếu có yêu cầu bảo toàn bằng chứng, phối hợp với bộ phận phụ trách trước khi xóa dữ liệu thuộc phạm vi đó.

Recording, log và thông tin cá nhân trong hồ sơ cũng cần được giới hạn quyền đọc và lưu trữ theo chính sách. Chỉ thu thập phần cần thiết; tránh đưa toàn bộ nội dung phiên hoặc dữ liệu nhạy cảm vào một ticket mà quá nhiều người xem được.

## 10. Ngoại lệ phải có giới hạn và người chịu trách nhiệm

Ví dụ, một công cụ cũ chưa thể thay credential mà không dừng dịch vụ. Đó là một rủi ro cần quản lý, không phải lý do để để nguyên quyền nhà cung cấp vô thời hạn.

Ngoại lệ cần ghi rõ:

- Đối tượng quyền hoặc credential chưa thu hồi được.
- Lý do và tác động nếu xử lý ngay.
- Chủ sở hữu nội bộ và người có thẩm quyền chấp nhận rủi ro.
- Kiểm soát bù cụ thể, cách kiểm tra hiệu lực và người theo dõi.
- Hạn xử lý, điều kiện phải chuyển sang ứng phó sự cố và lịch kiểm tra lại.
- Kế hoạch kết thúc ngoại lệ.

Nếu cần truy cập lại để sửa lỗi sau offboarding, cấp một grant mới theo quy trình hiện hành, có phê duyệt, phạm vi tối thiểu và TTL. Không coi việc hoàn tác offboarding bằng cách khôi phục toàn bộ quyền cũ là phương án khôi phục mặc định.

Credential đã thay không nên được đưa trở lại chỉ để tiện xử lý. Phương án vận hành cần ưu tiên danh tính nội bộ, credential mới hoặc đường truy cập khẩn cấp được kiểm soát. Mọi tái cấp quyền cho nhà cung cấp phải truy vết được như một quyết định mới.

## 11. Tình huống xuyên suốt: kết thúc quyền của Vendor Atlas

### 11.1. Đầu vào

Vendor Atlas hỗ trợ hai máy chủ ứng dụng và một cơ sở dữ liệu. Mốc cắt quyền được duyệt là 18:00 với múi giờ ghi rõ trong hồ sơ. Inventory ban đầu có:

- Hai danh tính cá nhân qua IdP và VPN.
- Một nhóm cấp eligibility JIT trong PAM.
- Hai phiên SSH qua bastion.
- Một khóa SSH trên tài khoản quản trị cục bộ được thêm trong lần hỗ trợ trước.
- Một API key của công cụ thu thập chẩn đoán.
- Một service account chạy job báo cáo hằng đêm.
- Một kho chia sẻ dùng để trao đổi log.

Chủ dịch vụ xác nhận job báo cáo phải tiếp tục chạy; công cụ thu thập chẩn đoán của nhà cung cấp không còn cần thiết.

### 11.2. Thực hiện

Trước mốc cắt, đội nội bộ tiếp nhận job, kiểm tra quyền cần thiết và chuyển sang credential do tổ chức quản lý. Đội vận hành kiểm tra một lần chạy đại diện và đối chiếu các consumer liên quan.

Tại mốc cắt, nhóm nguồn cấp eligibility được xử lý, các grant và yêu cầu tương lai bị thu hồi, danh tính cùng đường VPN bị đình chỉ theo kế hoạch. Hai phiên SSH được kết thúc và xác minh ở phía đích.

Đội quản trị gỡ khóa SSH khỏi nguồn cấu hình và máy đích, vô hiệu hóa API key tại nơi phát hành, dừng agent chẩn đoán theo kế hoạch thay đổi và thu hồi quyền của nó. Credential mà nhà cung cấp từng được phép biết được thay theo phạm vi tiếp xúc đã xác định.

Quyền kho chia sẻ được thu hồi. Sponsor xử lý bàn giao dữ liệu và xác nhận nghĩa vụ hoàn trả hoặc xóa qua quy trình hợp đồng; đội kỹ thuật không tự tuyên bố đã xóa được mọi bản sao ngoài tổ chức.

### 11.3. Phát hiện khoảng hở

Kiểm tra sau thay đổi cho thấy nhóm JIT đã bị gỡ, nhưng một quy tắc provisioning cũ sẽ thêm lại membership vào đêm hôm đó. Nếu đóng hồ sơ ngay, quyền có thể xuất hiện trở lại.

Đội IAM sửa nguồn cấp quyền theo yêu cầu được duyệt và xác minh sau đồng bộ. Đồng thời, SOC thấy một lần dùng API key cũ bị từ chối từ địa chỉ đã biết. Sự kiện được đối chiếu với agent cũ và xử lý theo quy trình, không mặc định coi mọi truy cập bị từ chối là bằng chứng tấn công.

Hồ sơ chỉ được đóng sau khi xác nhận không còn quyền ngoài phạm vi, credential cũ bị từ chối trong kiểm tra phù hợp, job nội bộ hoạt động và các hạng mục bàn giao dữ liệu đã có kết luận hoặc ngoại lệ được quản lý.

## 12. Mẫu kế hoạch thực thi không chứa secret

Mẫu YAML dưới đây minh họa cấu trúc hồ sơ. Đây không phải cấu hình có thể nhập trực tiếp vào sản phẩm PAM; trường và trạng thái phải được ánh xạ sang quy trình thực tế của tổ chức.

```yaml
offboarding:
  id: OFFBOARD-VENDOR-ATLAS-01
  vendorId: VENDOR-ATLAS
  contractRef: CONTRACT-SUPPORT-01
  reason: planned_contract_end
  cutoffAt: "2026-12-01T18:00:00+07:00"
  accountableOwner: internal-service-owner
  verifier: security-reviewer

  identities:
    - identityRef: vendor-engineer-01
      requiredActions:
        - disable_new_authentication
        - remove_future_privilege_eligibility
        - terminate_existing_sessions
    - identityRef: vendor-engineer-02
      requiredActions:
        - disable_new_authentication
        - remove_future_privilege_eligibility
        - terminate_existing_sessions

  credentials:
    - credentialRef: vault/support/admin-local
      exposure: potentially_known_to_vendor
      requiredAction: rotate_and_verify_consumers
    - credentialRef: issuer/diagnostics/api-key
      requiredAction: revoke_at_issuer

  automation:
    - identityRef: service/reporting
      decision: transfer_to_internal_owner
      owner: reporting-service-owner
      verification:
        - representative_job_passed
        - consumer_inventory_reconciled
        - old_credential_rejected

  closureRequirements:
    - identity_and_resource_state_readback
    - no_unapproved_active_privileged_sessions
    - no_future_privilege_regrant
    - old_credentials_no_longer_accepted_or_exception_approved
    - internal_service_health_confirmed
    - evidence_references_recorded
    - independent_verification_recorded

  exceptions: []
```

Các giá trị trong mẫu là giả lập. Danh sách hành động trong kế hoạch không phải bằng chứng chúng đã hoàn tất. Khi thực thi cần lưu kết quả, thời điểm, người thực hiện và tham chiếu audit riêng cho từng hạng mục.

## 13. Những lỗi thường làm offboarding thất bại

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Chỉ xóa tài khoản trong PAM | Quyền tại đích hoặc credential cũ còn dùng được | Đối chiếu toàn bộ đường truy cập và nơi xác thực |
| Chờ quyền JIT hết TTL | Danh tính vẫn có thể yêu cầu grant mới | Thu hồi eligibility, nguồn cấp và yêu cầu tương lai |
| Khóa IdP rồi kết luận đã chấm dứt phiên | Phiên hoặc token cũ có thể tiếp tục hoạt động | Kiểm tra khả năng thu hồi của từng loại phiên và resource |
| Đổi mật khẩu dùng chung trước khi biết consumer | Job nội bộ lỗi hoặc người vận hành quay lại mật khẩu cũ | Lập phụ thuộc, cập nhật consumer và xác minh hai phía |
| Xóa khóa trên máy nhưng bỏ qua cấu hình nguồn | Khóa được triển khai lại | Xử lý cả nguồn quản lý cấu hình và trạng thái tại đích |
| Xóa danh tính kèm toàn bộ audit ngay lập tức | Mất khả năng truy vết | Tách việc thu hồi quyền khỏi chính sách lưu bằng chứng |
| Giữ “tài khoản hỗ trợ dự phòng” không có hạn | Hình thành đường truy cập thường trực | Cấp lại có phê duyệt, giới hạn thời gian và phạm vi |
| Chuyển tài khoản cũ cho vendor mới | Không phân biệt được trách nhiệm | Cấp danh tính mới và offboard phía cũ |
| Đóng ticket khi có ngoại lệ chưa có owner | Rủi ro tồn tại không ai xử lý | Chỉ chấp nhận ngoại lệ có trách nhiệm và hạn rõ ràng |

## 14. Chỉ số theo dõi hiệu quả

Các chỉ số nên phản ánh kết quả thu hồi và chất lượng kiểm kê, thay vì chỉ đếm số ticket đã đóng:

- Thời gian từ mốc cắt được duyệt đến khi hoàn tất thu hồi từng lớp truy cập.
- Tỷ lệ đợt offboarding có đối chiếu inventory đầy đủ.
- Số phiên, credential hoặc quyền được phát hiện ngoài inventory ban đầu.
- Số lần quyền xuất hiện trở lại do đồng bộ hoặc provisioning.
- Tỷ lệ đợt có xác minh độc lập và bằng chứng đọc lại.
- Số ngoại lệ đang mở, quá hạn và thời gian tồn tại.
- Số lỗi dịch vụ do bàn giao credential hoặc consumer chưa đầy đủ.

Ví dụ, đo độ trễ thu hồi bằng thời điểm hoàn tất thu hồi trừ mốc cắt. Nếu truy cập bị thu hồi sớm hơn kế hoạch, ghi nhận riêng ảnh hưởng vận hành; không che tình huống đó bằng một số đo trung bình.

Không gộp mọi lớp thành “đã vô hiệu hóa tài khoản trong vài phút” nếu token hoặc credential tại đích còn hiệu lực lâu hơn. Báo cáo nên thể hiện thời điểm truy cập thực tế bị chấm dứt và phần chưa thể xác minh.

## 15. Bài tập tự thực hành

Một nhà cung cấp rời dự án. Tài khoản IdP đã bị khóa, nhưng còn một phiên RDP, một API token dài hạn và một service account đang chạy batch cuối tháng. Chủ dịch vụ đề nghị giữ nguyên mọi quyền thêm một tháng để tránh gián đoạn.

Hãy lập kế hoạch trả lời:

1. Đối tượng nào phải thu hồi ngay và đối tượng nào cần bàn giao có kiểm soát?
2. Làm thế nào để xác nhận phiên RDP đã kết thúc ở hệ thống đích?
3. Nơi nào phải vô hiệu hóa API token để bản sao cũ mất tác dụng?
4. Service account sẽ tiếp tục tồn tại dưới owner nào và credential nào?
5. Nếu chưa thể kiểm tra batch cuối tháng, cần bằng chứng thay thế hoặc ngoại lệ ra sao?
6. Những điều kiện nào phải đạt trước khi đóng hồ sơ?

Một hướng xử lý hợp lý là tách quyền con người khỏi phụ thuộc tự động hóa: kết thúc phiên và quyền cá nhân theo mốc đã duyệt, thu hồi token không còn cần thiết, chuyển batch sang owner nội bộ và credential được quản lý. Chỉ phần phụ thuộc thực sự chưa thể xử lý mới đi qua ngoại lệ có hạn, kiểm soát bù và người chịu trách nhiệm.

Offboarding hoàn tất khi khả năng truy cập của nhà cung cấp đã kết thúc trong phạm vi yêu cầu, tác vụ hợp lệ có người tiếp nhận và bằng chứng đủ để kiểm chứng kết luận đó.
