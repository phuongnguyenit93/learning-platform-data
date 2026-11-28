# Nhận diện việc sử dụng tài khoản bất thường (Atypical account usage)

## 1. Mục tiêu và phạm vi

Trong quản lý truy cập đặc quyền (Privileged Access Management — PAM), một lần đăng nhập thành công chỉ cho biết hệ thống đã chấp nhận bằng chứng xác thực. Nó chưa cho biết người thao tác có đúng là chủ thể được giao quyền, có thực hiện đúng công việc đã duyệt hay có sử dụng quyền vượt phạm vi hay không.

**Atypical account usage** là việc sử dụng tài khoản khác với hành vi được kỳ vọng trong một ngữ cảnh cụ thể. Ngữ cảnh bao gồm loại tài khoản, người hoặc workload sử dụng, tài sản đích, thời điểm, nguồn truy cập, phương thức truy cập, mức quyền và nhiệm vụ được phê duyệt.

Bài học này giúp bạn:

- Xác định “bình thường” cho tài khoản quản trị, tài khoản dịch vụ và tài khoản khẩn cấp.
- Chọn các dấu hiệu bất thường có ý nghĩa đối với PAM.
- Kết nối dữ liệu đăng nhập, vault, JIT/JEA, phiên quản trị và audit trên hệ thống đích.
- Phân biệt hành vi hiếm nhưng hợp lệ, vi phạm chính sách và dấu hiệu chiếm dụng tài khoản.
- Thiết kế cảnh báo có bằng chứng, phương án xác minh và hành động phù hợp với ảnh hưởng vận hành.

Các tên tài khoản, địa chỉ IP, mốc thời gian và ngưỡng trong ví dụ đều là dữ liệu giả lập. Các ngưỡng minh họa cần được hiệu chỉnh trên môi trường thực tế; chúng không phải ngưỡng mặc định của một sản phẩm PAM.

## 2. Hiểu đúng ý nghĩa của “bất thường”

### 2.1. Khác thói quen không đồng nghĩa với bị xâm nhập

Một quản trị viên cơ sở dữ liệu thường làm việc ban ngày nhưng đăng nhập lúc 02:00 để khôi phục dịch vụ có thể hoàn toàn hợp lệ. Ngược lại, việc xuất dữ liệu nhạy cảm vào đúng giờ làm việc, từ đúng máy quản trị, vẫn có thể là lạm dụng quyền.

Cần tách ba câu hỏi:

| Câu hỏi | Căn cứ chính | Ý nghĩa đối với xử lý |
|---|---|---|
| Hành vi có khác kỳ vọng không? | Baseline cá nhân, baseline workload, nhóm vai trò và ngữ cảnh | Tạo giả thuyết cần kiểm tra |
| Hành vi có được phép không? | Chính sách, grant, ticket, phạm vi tài sản và thời hạn | Xác định việc sử dụng quyền có hợp lệ |
| Có bằng chứng tài khoản bị chiếm dụng hoặc gây hại không? | Chuỗi sự kiện xác thực, thiết bị, thao tác đích và bằng chứng điều tra | Xác định mức độ nghiêm trọng và biện pháp ứng phó |

Ba câu trả lời có thể khác nhau. Một hành vi rất phổ biến vẫn có thể vi phạm chính sách; hành vi mới xuất hiện chưa đủ để kết luận là tấn công.

Ví dụ, tài khoản dịch vụ đăng nhập tương tác mỗi tuần không trở thành hợp lệ chỉ vì baseline ghi nhận nó là “thường xuyên”. Nếu chính sách cấm đăng nhập tương tác, quy tắc chính sách vẫn phải phát hiện. Baseline không được biến sai phạm lặp lại thành quyền được phép.

### 2.2. Tài khoản, danh tính và người thao tác là các thực thể khác nhau

Một người có thể có tài khoản thông thường, tài khoản quản trị riêng và vai trò cloud tạm thời. Một tài khoản quản trị dùng chung có thể được nhiều người checkout qua vault. Một workload có thể sử dụng nhiều credential trong quá trình rotation.

Do đó, câu hỏi “ai làm?” không thể chỉ trả lời bằng trường `username`.

Một chuỗi truy vết PAM có thể là:

```text
Danh tính cá nhân đã xác thực
  → yêu cầu và phê duyệt quyền
  → grant JIT hoặc checkout credential
  → phiên PAM
  → tài khoản/role hiệu lực trên tài sản đích
  → thao tác được audit tại đích
```

Mỗi mũi tên cần bằng chứng liên kết. Nếu chỉ biết tài khoản đích là `admin-db`, chưa thể quy trách nhiệm cho một cá nhân cụ thể. Nếu liên kết không chắc chắn, cảnh báo phải thể hiện mức độ chắc chắn thay vì tự điền tên người.

Đối với tài khoản dịch vụ, chuỗi tương đương là workload → môi trường chạy → credential/role → tài nguyên → hoạt động. “Chủ sở hữu tài khoản” là người chịu trách nhiệm quản lý, không mặc định là người trực tiếp thực hiện mọi sự kiện của workload.

### 2.3. So sánh đúng đơn vị

Các đơn vị quan sát thường dùng gồm:

- Một sự kiện, chẳng hạn đăng nhập hoặc đọc secret.
- Một phiên, chẳng hạn toàn bộ hoạt động quản trị sau khi được cấp quyền.
- Một cửa sổ thời gian theo tài khoản, chẳng hạn số tài sản đích khác nhau trong 15 phút.
- Một chuỗi danh tính, chẳng hạn cùng một người sử dụng nhiều role trên nhiều hệ thống.
- Một workload, chẳng hạn job sao lưu trên các replica đã được khai báo.

Nếu thống kê chỉ theo từng username, hoạt động trải qua nhiều role có thể bị chia nhỏ. Nếu gộp mọi tài khoản của một người, khác biệt giữa quyền thông thường và quyền đặc quyền có thể bị che khuất. Thiết kế phát hiện cần giữ cả định danh gốc và các liên kết đã được xác minh.

## 3. Xây dựng kỳ vọng trước khi chấm điểm bất thường

### 3.1. Tách ràng buộc được phép và hành vi đã quan sát

Một hồ sơ giám sát nên có hai lớp:

1. **Ràng buộc được phép:** ai hoặc workload nào được dùng tài khoản, đích nào được truy cập, loại phiên nào hợp lệ, đường truy cập nào bắt buộc, quyền nào được cấp và trong bao lâu.
2. **Hành vi đã quan sát:** thời điểm thường sử dụng, tập tài sản thường truy cập, số lượng secret thường đọc, số phiên đồng thời và nhóm thao tác thường thực hiện.

Lớp thứ nhất đến từ chính sách và quy trình cấp quyền. Lớp thứ hai được xây từ dữ liệu đủ tin cậy. Không dùng hành vi quan sát để tự mở rộng ràng buộc được phép.

Việc xây baseline cho hành vi tài khoản và chú ý riêng tới tài khoản đặc quyền, tài sản quan trọng cũng được nhấn mạnh trong [hướng dẫn chung về event logging và threat detection của ASD’s ACSC cùng các cơ quan đối tác](https://www.cyber.gov.au/publication/best-practices-for-event-logging-and-threat-detection). Phần thiết kế và các ví dụ dưới đây là mô hình minh họa cho bài học PAM.

### 3.2. Lập hồ sơ theo loại tài khoản

| Loại tài khoản | Kỳ vọng cần mô tả | Dấu hiệu cần chú ý |
|---|---|---|
| Quản trị cá nhân | Người được giao, máy quản trị, ca trực, nhóm tài sản, phương thức PAM | Thiết bị mới cùng đích mới; quyền được dùng ngoài thời hạn |
| Quản trị dùng chung qua vault | Người checkout, khoảng thời gian cấp phát, phiên broker, tài khoản đích | Hoạt động đích không liên kết được với checkout hoặc phiên hợp lệ |
| Tài khoản dịch vụ | Workload, owner, node hoặc môi trường chạy, đích, giao thức, lịch job | Đăng nhập tương tác; dùng credential từ workload không được khai báo |
| Tài khoản automation/deployment | Pipeline, runner, môi trường, job và phạm vi deploy | Quyền production được dùng ngoài job được phê duyệt |
| Break-glass | Điều kiện kích hoạt, người được phép, tài sản, thông báo và hậu kiểm | Bất kỳ lần dùng nào cần kiểm tra; thiếu liên kết sự cố làm tăng ưu tiên |

Không áp baseline “giờ hành chính” của quản trị viên cho tài khoản backup chạy ban đêm. Không áp baseline “chỉ một máy nguồn” cho workload có autoscaling mà không xét định danh workload và cấu hình triển khai.

### 3.3. Chọn lịch sử và nhóm so sánh

Không có một độ dài lịch sử phù hợp cho mọi tài khoản. Cần xét chu kỳ hoạt động:

- Công việc hằng ngày cần dữ liệu đại diện cho ngày làm việc, cuối tuần và ca trực.
- Công việc cuối tháng cần được nhận diện theo lịch công việc, không coi các ngày còn lại là mẫu thay thế.
- Tài khoản mới hoặc tài khoản ít dùng có thể chưa có đủ lịch sử để tính độ hiếm đáng tin cậy.
- Sự kiện trong một giai đoạn đang điều tra không nên tự động được học thành hành vi bình thường.

Khi lịch sử cá nhân còn ít, có thể tham khảo nhóm cùng vai trò, cùng loại tài sản và cùng môi trường. Nhóm “mọi quản trị viên” thường quá rộng: quản trị ứng dụng không cần có mẫu truy cập giống quản trị hệ thống định danh.

Baseline cần lưu phiên bản, thời gian quan sát, số mẫu, các kỳ bảo trì được xử lý riêng và người duyệt thay đổi. Một nhãn “first seen” chỉ có nghĩa là chưa thấy trong tập dữ liệu đã quan sát, không chứng minh rằng trước đây chưa từng xảy ra.

### 3.4. Quản lý thay đổi hợp lệ

Một chuyển đổi hạ tầng có thể tạo hàng loạt nguồn truy cập và tài sản mới. Trước đợt thay đổi, đội vận hành có thể khai báo phạm vi dự kiến: workload nào chuyển, đích nào thay đổi, thời gian nào áp dụng và bằng chứng phê duyệt nào liên quan.

Ngoại lệ cần hẹp, có chủ sở hữu và có hạn dùng. Không tắt toàn bộ rule cho một tài khoản chỉ vì một lần bảo trì hợp lệ. Hành vi vượt tài sản, thời gian hoặc thao tác được duyệt vẫn cần được đánh giá.

Không tự động cập nhật baseline ngay sau một cảnh báo chưa được phân loại. Nếu có kẻ đang sử dụng tài khoản sai mục đích, việc học không kiểm soát có thể làm giảm độ nhạy phát hiện ở các lần tiếp theo.

## 4. Dữ liệu cần để nhận diện đúng ngữ cảnh PAM

### 4.1. Các nguồn có vai trò bổ sung cho nhau

| Nguồn dữ liệu | Câu hỏi hỗ trợ trả lời | Giới hạn cần ghi nhận |
|---|---|---|
| IdP/MFA | Danh tính nào xác thực, từ thiết bị nào, bằng phương thức nào? | MFA thành công không chứng minh mọi hành động sau đó là hợp lệ |
| Vault | Ai hoặc workload nào yêu cầu secret, khi nào, cho tài khoản nào? | Checkout không chứng minh credential đã được dùng ở đâu |
| JIT/JEA và hệ thống phê duyệt | Quyền, đích, lệnh hoặc nhiệm vụ nào được cấp? | Có grant chưa đủ; phải kiểm tra grant có bao phủ hành động thực tế |
| PAM session broker | Phiên nào kết nối tới đích, bắt đầu và kết thúc khi nào? | Một số đường truy cập ngoài broker có thể không xuất hiện |
| Audit hệ điều hành, DB hoặc cloud | Tài khoản/role hiệu lực thực hiện thao tác gì tại đích? | Mức chi tiết tùy cấu hình và khả năng của hệ thống |
| EDR, quản lý thiết bị, inventory | Máy nguồn có được quản lý, tài sản đích có quan trọng không? | Thông tin có thể cũ hoặc chưa bao phủ đầy đủ |
| Ticket, lịch trực, lịch automation | Hoạt động có phù hợp công việc đã duyệt không? | Ticket tồn tại nhưng sai đích hoặc hết hạn không phải bằng chứng cho phép |

Một phiên PAM có thể hợp lệ về đường truy cập nhưng hành động bên trong vẫn vượt nhiệm vụ. Ngược lại, không tìm thấy phiên PAM có thể do mất log, sai ánh xạ hoặc độ trễ ingest. Hai tình huống cần được phân biệt.

### 4.2. Chuẩn hóa một sự kiện để phục vụ tương quan

Ví dụ dưới đây là schema tự thiết kế phục vụ bài học, không phải định dạng bắt buộc của một sản phẩm:

```json
{
  "event_id": "evt-0073",
  "event_time": "2026-11-26T19:10:00Z",
  "ingest_time": "2026-11-26T19:10:04Z",
  "event_type": "privileged_action",
  "tenant_id": "org-lab",
  "source_system": "database-audit",
  "actor_identity_id": "person-042",
  "account_id": "db-admin-17",
  "account_type": "human_privileged",
  "source_asset_id": "admin-ws-09",
  "source_ip": "192.0.2.19",
  "target_asset_id": "prod-db-02",
  "target_criticality": "critical",
  "pam_session_id": "pam-s-091",
  "grant_id": "jit-g-231",
  "ticket_id": "CHG-218",
  "action_category": "database_export",
  "outcome": "success"
}
```

Trong ví dụ này, thời điểm sự kiện tương ứng 02:10 ngày 27/11 theo UTC+7. Lưu thời gian chuẩn có múi giờ giúp so sánh giữa nguồn; giao diện điều tra có thể hiển thị thêm giờ địa phương của ca trực.

Những điểm cần bảo toàn khi chuẩn hóa:

- Định danh tenant/domain và ID tài khoản ổn định để tránh gộp các username trùng tên.
- Thời gian phát sinh và thời gian nhận log để đánh giá sự kiện đến muộn.
- Tài khoản thực thi và danh tính gốc, nếu có bằng chứng liên kết.
- Grant, phiên và ticket dưới dạng định danh độc lập.
- Trạng thái chưa biết cho dữ liệu thiếu; không biến giá trị thiếu thành “được phép”.

Không ghi mật khẩu, nội dung secret, access token hoặc private key vào sự kiện phân tích. Nếu cần đối chiếu credential, dùng định danh hoặc phiên bản credential do hệ thống quản lý cung cấp.

### 4.3. Kiểm tra chất lượng dữ liệu trước khi kết luận

Giả sử audit tại đích có sự kiện lúc 02:10 nhưng log PAM của cùng phiên đến muộn ba phút. Rule tìm phiên ngay lúc audit vừa đến sẽ tạo ra kết luận sai nếu coi “chưa tìm thấy” là “không có”.

Cần biết trạng thái hoạt động của collector, độ trễ ingest, đồng bộ đồng hồ, tính đầy đủ của mapping và phạm vi coverage. Nếu chưa đủ dữ liệu, có thể phát cảnh báo sơ bộ rồi đánh giá lại khi log đến; đồng thời mở cảnh báo riêng về chất lượng thu thập.

Không trì hoãn mọi cảnh báo nghiêm trọng để chờ dữ liệu hoàn hảo. Một hành động phá hủy quan sát được trực tiếp cần được xử lý theo playbook tương ứng. Cách chờ và đánh giá lại dành cho kết luận phụ thuộc vào dữ liệu chưa đến, chẳng hạn sự vắng mặt của bản ghi phiên.

## 5. Những dạng sử dụng tài khoản bất thường cần theo dõi

### 5.1. Thời gian, tần suất và thời lượng

Các dấu hiệu có thể gồm truy cập ngoài ca trực, số lần checkout tăng mạnh, nhiều phiên đồng thời hơn dự kiến, thời lượng phiên kéo dài bất thường hoặc hoạt động sau khi grant hết hạn.

Cần đặt dấu hiệu trong bối cảnh:

- Truy cập ban đêm trong ca trực đã phân công có thể bình thường.
- Một job mới chạy lại sau sự cố có thể tăng số lần xác thực.
- Phiên còn mở không đồng nghĩa vẫn còn quyền hiệu lực; cần xem hoạt động tại đích và khả năng thu hồi thực tế.
- Hành động sau khi grant hết hạn là câu hỏi chính sách; không cần chờ nó trở nên hiếm trong baseline.

Với nhiều job tuần tự cùng dùng một tài khoản dịch vụ, số phiên đồng thời có thể tăng khi chuyển sang chạy song song. Cần xác minh thay đổi cấu hình thay vì bỏ qua cảnh báo theo lời giải thích chung “do automation”.

### 5.2. Nguồn truy cập và đường truy cập

Theo dõi máy nguồn mới, thiết bị không được quản lý, đường truy cập trực tiếp thay vì qua broker bắt buộc, hoặc việc sử dụng credential từ môi trường khác.

Địa chỉ IP không phải định danh người dùng hoặc workload. VPN, NAT, proxy, địa chỉ động và runner được tạo mới có thể làm IP thay đổi. Nếu dùng địa lý IP hoặc “impossible travel”, phải xét độ tin cậy của nguồn IP và khả năng lưu lượng đi qua hạ tầng trung gian.

Trong PAM, kết hợp “máy không được quản lý + truy cập trực tiếp tới đích nhạy cảm + thiếu grant bao phủ” thường có giá trị điều tra hơn chỉ “IP chưa từng thấy”.

### 5.3. Tài sản đích và phạm vi quyền

Một tài khoản vốn chỉ quản trị máy chủ ứng dụng nay truy cập hệ thống định danh hoặc kho secret có thể cần ưu tiên cao hơn việc truy cập thêm một máy cùng nhóm ứng dụng.

Theo dõi cả số lượng đích và loại đích. Với việc truy cập nhiều đích trong thời gian ngắn, nên đếm tài sản riêng biệt sau khi loại bỏ sự kiện trùng. Một công cụ quản lý cấu hình được duyệt có thể chạm nhiều máy; một tài khoản chỉ có nhiệm vụ xử lý một ticket trên một đích thì có kỳ vọng khác.

Các thay đổi quyền cần xem xét gồm nhận role đặc quyền chưa từng dùng, thêm thành viên nhóm quản trị, thay đổi chính sách truy cập hoặc sử dụng quyền ngoài tập được cấp. Quyền đã tồn tại trong hệ thống chưa chắc phù hợp với nhiệm vụ hiện tại.

### 5.4. Phương thức sử dụng và loại hoạt động

Một tài khoản dịch vụ dùng xác thực không tương tác nhưng xuất hiện phiên shell tương tác là dấu hiệu đáng kiểm tra, ngay cả khi thời gian và máy nguồn quen thuộc.

Những thay đổi đáng chú ý khác gồm:

- Tài khoản deploy dùng quyền để sửa chính sách định danh.
- Tài khoản backup thực hiện thao tác quản trị ngoài chức năng sao lưu.
- Tài khoản quản trị cơ sở dữ liệu xuất dữ liệu hàng loạt khác với nhiệm vụ đã duyệt.
- Một danh tính liên tiếp đọc nhiều secret không liên quan tới tập tài sản đang quản lý.
- Tài khoản khẩn cấp được dùng cho bảo trì thường lệ.

Không suy ra đăng nhập tương tác chỉ từ một trường thiếu hoặc tên tài khoản. Cần dữ liệu mô tả loại phiên, giao thức hoặc hoạt động đủ rõ; khi không có, ghi nhận giới hạn quan sát.

### 5.5. Chuỗi hành vi quan trọng hơn một dấu hiệu riêng lẻ

Ví dụ:

```text
Nguồn quản trị mới
  → checkout credential ngoài ca
  → truy cập đích production chưa từng được giao
  → thay đổi quyền
  → xuất dữ liệu
```

Từng sự kiện riêng có thể có lời giải thích hợp lệ. Khi chúng gắn với cùng chủ thể, cùng phiên và cùng khoảng thời gian, nhu cầu điều tra tăng lên.

Không cộng điểm nhiều lần cho các đặc trưng thực chất trùng nhau. “IP mới”, “ASN mới” và “quốc gia mới” có thể cùng xuất phát từ một thay đổi VPN; chúng không phải ba bằng chứng độc lập về chiếm dụng tài khoản.

## 6. Kết hợp chính sách, baseline và ngữ cảnh công việc

### 6.1. Ba tầng phát hiện bổ sung

**Tầng chính sách** tìm điều kiện không được phép: tài khoản dịch vụ đăng nhập tương tác, hoạt động vượt thời hạn, truy cập sai đích hoặc bỏ qua đường PAM bắt buộc.

**Tầng hành vi** tìm sự khác biệt đáng chú ý: đích mới, tần suất tăng, thời gian lạ hoặc loại thao tác hiếm so với hồ sơ phù hợp.

**Tầng tương quan** kết nối chúng với độ quan trọng tài sản, tình trạng thiết bị, bằng chứng xác thực, thay đổi quyền và công việc đã duyệt.

Không yêu cầu cả ba tầng cùng dương tính mới phát cảnh báo. Một vi phạm rõ ràng trên tài sản trọng yếu có thể đủ để mở điều tra. Ngược lại, nhiều dấu hiệu hiếm nhưng yếu không tự tạo thành kết luận tài khoản đã bị chiếm dụng.

### 6.2. Kiểm tra grant theo phạm vi thực tế

Một grant phù hợp cần được đối chiếu ít nhất với:

- Chủ thể hoặc workload được cấp.
- Tài khoản hay role hiệu lực được phép dùng.
- Tài sản đích hoặc tập tài sản cụ thể.
- Thao tác hoặc tập quyền được phép.
- Thời điểm hiệu lực, thời điểm hết hạn và trạng thái thu hồi.
- Liên kết phiên khi cơ chế PAM hỗ trợ.

Ví dụ, ticket cho phép kiểm tra tình trạng `prod-db-01` không bao phủ việc xuất dữ liệu từ `prod-db-02`. Chỉ kiểm tra `ticket_id != null` hoặc `grant_id != null` sẽ bỏ lọt trường hợp này.

JEA hạn chế các thao tác được cho phép ở mức nhiệm vụ, nhưng một phiên JEA vẫn cần audit để xác nhận nhiệm vụ thực tế. JIT giảm thời gian tồn tại quyền; nó không chứng minh mọi hoạt động trong cửa sổ cấp quyền đều đúng mục đích.

### 6.3. Điểm rủi ro là công cụ ưu tiên

Có thể dùng một công thức minh họa:

```text
priority_score =
    policy_evidence
  + behavioral_evidence
  + asset_impact
  + correlated_evidence
```

Mỗi thành phần cần có định nghĩa, giới hạn và lý do. Cảnh báo phải trả lời được điểm đến từ đâu. Không dùng một con số tổng để che mất sự khác biệt giữa “thiếu log để xác minh” và “audit chứng minh hành động vượt grant”.

Điểm ưu tiên không phải xác suất xâm nhập nếu chưa có mô hình xác suất được hiệu chuẩn. Một điểm 80 không có nghĩa tài khoản bị chiếm dụng với xác suất 80%.

Nên biểu diễn riêng:

- **Mức ảnh hưởng:** tài sản và thao tác có thể gây hậu quả gì.
- **Độ tin cậy bằng chứng:** dữ liệu có đủ, liên kết có chắc và sự kiện có được xác thực không.
- **Ưu tiên xử lý:** cần phản hồi nhanh đến mức nào theo playbook.

Thiếu dữ liệu có thể làm giảm độ tin cậy của kết luận nhưng vẫn đòi hỏi ưu tiên xử lý cao khi tài sản rất nhạy cảm.

## 7. Ví dụ thiết kế rule không phụ thuộc sản phẩm

### 7.1. Đặc tả trước khi viết truy vấn

Giả sử tổ chức muốn phát hiện tài khoản quản trị cá nhân sử dụng quyền trên đích mới ngoài ca trực, trong khi chưa xác minh được grant bao phủ.

Hợp đồng của rule cần nêu:

| Thành phần | Ví dụ minh họa |
|---|---|
| Đối tượng | Tài khoản được inventory phân loại là quản trị cá nhân |
| Đơn vị đánh giá | Sự kiện thao tác đặc quyền, gắn với phiên nếu có |
| Lịch sử | 28 ngày đủ dữ liệu, loại trừ các giai đoạn đang điều tra |
| Điều kiện hành vi | Đích chưa thấy trong lịch sử và ngoài ca được phân công |
| Điều kiện quyền | Không có grant bao phủ chủ thể, đích, thao tác, thời gian |
| Xử lý dữ liệu thiếu | Cảnh báo sơ bộ hoặc hàng đợi cần bổ sung, không kết luận “bypass” |
| Gom nhóm | Cùng tài khoản, đích, phiên và cửa sổ điều tra |
| Đầu ra | Lý do, chất lượng dữ liệu, sự kiện gốc và bước xác minh |

Khoảng lịch sử 28 ngày chỉ là lựa chọn cho ví dụ. Nếu tài khoản được dùng theo quý, cửa sổ này không đại diện cho hành vi của nó.

### 7.2. Giả mã tương quan

Đoạn sau mô tả logic, không phải code có thể chạy trực tiếp trong SIEM:

```text
ON privileged_action(event):
    IF event.account_type != "human_privileged":
        RETURN

    context = resolve_identity_asset_schedule_and_baseline(event)
    grant_result = find_grant_covering(
        actor=event.actor_identity_id,
        account=event.account_id,
        target=event.target_asset_id,
        action=event.action_category,
        time=event.event_time
    )

    IF grant_result == DENIED_BY_COMPLETE_RECORDS:
        emit_policy_alert(event, context, "activity_outside_grant")

    IF context.identity_link != VERIFIED:
        emit_correlation_gap(event, "actor_not_verified")
        RETURN

    IF context.baseline_state != READY:
        evaluate_cold_start_policy_rules(event, context)
        RETURN

    IF context.target_is_new AND context.outside_assigned_shift:
        IF grant_result == VALID:
            record_anomaly_with_approved_context(event, context)
        ELSE IF grant_result == UNKNOWN_DATA_GAP:
            emit_preliminary_alert(event, context, "grant_not_yet_verified")
        ELSE:
            emit_prioritized_alert(event, context, "new_target_outside_shift")
```

Ba trạng thái grant có ý nghĩa khác nhau:

- `VALID`: tìm được bản ghi đủ điều kiện bao phủ hành động.
- `DENIED_BY_COMPLETE_RECORDS`: dữ liệu được xác nhận đủ trong phạm vi kiểm tra và không có quyền phù hợp, hoặc có bằng chứng quyền đã hết hiệu lực.
- `UNKNOWN_DATA_GAP`: thiếu dữ liệu, nguồn lỗi hoặc liên kết chưa chắc nên chưa xác minh được.

Trong triển khai thực tế, “dữ liệu đầy đủ” cần tiêu chí cụ thể; nó không thể được suy ra chỉ từ việc một truy vấn trả về không có hàng. Việc ghi nhận anomaly có grant hợp lệ cũng không miễn trừ các rule khác, chẳng hạn hành động nguy hiểm hoặc thiết bị có dấu hiệu bị chiếm dụng.

### 7.3. Vận hành rule với dữ liệu đến muộn

Có thể giữ cảnh báo ở trạng thái sơ bộ trong một khoảng trễ dựa trên số liệu ingest của nguồn, sau đó đánh giá lại. Khi dữ liệu đến bổ sung, cập nhật cùng một cảnh báo và giữ lịch sử thay đổi thay vì tạo nhiều cảnh báo giống nhau.

Cần phân biệt:

- Thời gian sự kiện xảy ra.
- Thời gian hệ thống phát hiện.
- Thời gian bằng chứng bổ sung xuất hiện.
- Thời gian chuyên viên ra quyết định.

Dùng khóa sự kiện ổn định để loại bỏ bản ghi trùng. Khi gom nhiều sự kiện thành một cảnh báo, vẫn giữ danh sách sự kiện gốc để điều tra viên kiểm tra được thứ tự và phạm vi.

Nếu chấm baseline theo dòng sự kiện, phải kiểm soát thứ tự cập nhật: dữ liệu mới chưa được đánh giá không nên làm chính nó trở thành “đã quen thuộc”. Việc nạp sự kiện đến muộn cũng cần giữ đúng mốc tham chiếu của baseline.

## 8. Cảnh báo phải đủ thông tin để người trực hành động

Một cảnh báo chỉ ghi “abnormal login” thường đẩy toàn bộ công việc dựng ngữ cảnh cho người trực. Một cảnh báo PAM hữu ích nên có:

- Danh tính gốc, tài khoản hiệu lực, loại tài khoản và mức chắc chắn của mapping.
- Tài sản nguồn, tài sản đích, môi trường và độ quan trọng.
- Dòng thời gian theo cả event time và thời điểm tiếp nhận.
- Dấu hiệu cụ thể: mới so với baseline nào, vượt ngưỡng nào, vi phạm ràng buộc nào.
- Phiên, grant, ticket và kết quả kiểm tra phạm vi.
- Tình trạng log, độ trễ, những nguồn chưa có và các giả định.
- Bằng chứng gốc dưới dạng liên kết có kiểm soát truy cập.
- Chủ sở hữu tài khoản, đội vận hành liên quan và playbook xử lý.

Ví dụ nội dung cảnh báo giả lập:

```yaml
alert_id: PAM-ANOM-071
rule_id: human_privileged_new_target_outside_shift
rule_version: '1.2'
account_id: db-admin-17
actor_identity_id: person-042
identity_link: verified
target_asset_id: prod-db-02
event_time: '2026-11-26T19:10:00Z'
priority: high
compromise_status: unconfirmed
reasons:
  - target_not_seen_in_baseline
  - outside_assigned_shift
  - observed_action_not_covered_by_grant
evidence:
  event_ids: [evt-0073]
  pam_session_id: pam-s-091
  grant_id: jit-g-231
  ticket_id: CHG-218
  baseline_version: human-admin-2026-11-v3
data_quality:
  target_audit: healthy
  pam_events: healthy
  grant_records: complete_for_window
next_action: verify_change_scope_and_observed_database_action
```

Các field này là ví dụ thiết kế. Nhãn `high` nói về ưu tiên điều tra theo quy tắc của ví dụ, còn `unconfirmed` nhắc rằng chưa kết luận chiếm dụng tài khoản.

Bản ghi cảnh báo không nên chứa credential hoặc toàn bộ nội dung xuất dữ liệu. Điều tra viên được cấp quyền mới truy cập bằng chứng nhạy cảm tại nơi lưu trữ phù hợp.

## 9. Triage và ứng phó theo bằng chứng

### 9.1. Xác nhận sự kiện và đường truy vết

Trước tiên, kiểm tra sự kiện có đúng tenant, đúng tài khoản và đúng đích hay không; timestamp có lệch hay bị trùng không; parser có phân loại sai loại phiên không.

Tiếp theo, dựng chuỗi từ danh tính đến hoạt động đích. Một phiên trên broker và một sự kiện DB có tên tài khoản giống nhau chưa đủ để khẳng định cùng phiên nếu có nhiều người cùng sử dụng tài khoản. Cần session ID, connection metadata, khoảng thời gian và các liên kết đủ tin cậy.

Nếu kết quả chỉ là tương quan theo thời gian, ghi rõ mức độ không chắc chắn. Việc này đặc biệt quan trọng với tài khoản dùng chung.

### 9.2. Đối chiếu công việc đã phê duyệt

Đối chiếu ticket, ca trực, người được giao, đích, thao tác và thời hạn. Xác nhận với người phụ trách qua kênh đã được tổ chức tin cậy; không chỉ gửi câu hỏi vào chính phiên đang bị nghi ngờ.

Một người nói “đúng là tôi” hỗ trợ điều tra nhưng không thay bằng chứng về phạm vi được phép. Người dùng hợp lệ vẫn có thể thao tác sai, và thiết bị của họ vẫn có thể bị chiếm dụng.

Khi có bảo trì khẩn cấp, kiểm tra quy trình khẩn cấp đã được kích hoạt và ghi nhận ra sao. Không suy rằng mọi truy cập ngoài giờ đều hợp lệ chỉ vì có sự cố cùng ngày.

### 9.3. Chọn hành động theo mức ảnh hưởng và khả năng thực thi

| Tình huống | Hướng xử lý minh họa |
|---|---|
| Một dấu hiệu hiếm, có grant đúng phạm vi, thiết bị tin cậy | Ghi nhận, xác minh ngữ cảnh và theo dõi thêm |
| Chưa tìm được phiên do nguồn PAM đang trễ | Bổ sung dữ liệu, cập nhật cảnh báo sơ bộ và xử lý lỗi collector |
| Hành động vượt grant trên production | Liên hệ người trực, kiểm tra phiên và thực hiện playbook đã duyệt |
| Nhiều bằng chứng về chiếm dụng tài khoản | Thu hẹp quyền, chặn phiên hoặc cô lập nguồn theo thẩm quyền ứng phó |
| Tài khoản dịch vụ bị nghi lộ credential | Đánh giá phụ thuộc, chuyển credential an toàn và xác minh workload phục hồi |
| Break-glass được sử dụng | Thông báo ngay cho đầu mối được quy định, kiểm tra mục đích và hậu kiểm |

Việc chấm dứt phiên PAM không luôn bảo đảm mọi phiên đích, token hoặc kết nối đã được thiết lập đều hết hiệu lực. Tương tự, đổi mật khẩu không mặc định hủy mọi token đang hoạt động. Cần kiểm tra các cơ chế thu hồi cụ thể và đọc lại trạng thái trên hệ thống liên quan.

Với tài khoản dịch vụ quan trọng, khóa ngay có thể làm gián đoạn một chuỗi ứng dụng. Playbook cần cân bằng nguy cơ đang diễn ra với phụ thuộc vận hành, xác định người quyết định và đường khôi phục. Không tự động khóa hàng loạt chỉ dựa trên một đặc trưng như IP mới.

### 9.4. Bảo toàn bằng chứng và kết thúc điều tra

Giữ các event gốc, metadata phiên, grant, phiên bản rule, baseline và lịch sử quyết định. Ghi ai thực hiện hành động ứng phó, khi nào và kết quả kiểm tra sau hành động. Nếu rotation được thực hiện, lưu ID hoặc phiên bản credential thay vì giá trị bí mật.

Kết quả điều tra nên tách rõ:

- Hợp lệ nhưng mới: thay đổi đã được duyệt, cần điều chỉnh kỳ vọng.
- Cảnh báo sai do logic hoặc dữ liệu: parser, mapping, baseline hoặc ingest cần sửa.
- Vi phạm chính sách: cần khắc phục quy trình hay thu hẹp quyền, chưa nhất thiết có chiếm dụng.
- Sự cố được xác nhận: chuyển quy trình ứng phó và xác định phạm vi ảnh hưởng.
- Chưa đủ bằng chứng: lưu lý do, dữ liệu còn thiếu và người theo dõi.

Không đóng “benign” chỉ vì chưa tìm thấy bằng chứng bổ sung trong lúc nguồn log đang mất dữ liệu.

## 10. Tình huống xuyên suốt: quản trị DB ngoài ca

### 10.1. Kỳ vọng ban đầu

Trong mô hình giả lập, `person-042` dùng `db-admin-17` qua PAM từ máy quản trị được quản lý. Công việc thông thường là kiểm tra sức khỏe `prod-db-01`. Ca trực đã được khai báo trong hệ thống lịch trực.

Ticket `CHG-218` cấp quyền kiểm tra trạng thái trên `prod-db-01` từ 01:50 đến 02:20 giờ UTC+7. Grant không cấp quyền xuất dữ liệu từ `prod-db-02`.

### 10.2. Chuỗi sự kiện quan sát được

| Giờ UTC+7 | Sự kiện | Ý nghĩa cần kiểm tra |
|---|---|---|
| 02:05 | Xác thực từ máy quản trị đã biết | Nguồn quen thuộc làm giảm một giả thuyết, không xác nhận nhiệm vụ |
| 02:07 | Mở phiên PAM có liên kết với grant `jit-g-231` | Có bằng chứng đường truy cập qua PAM |
| 02:10 | Audit ghi nhận hoạt động xuất dữ liệu tại `prod-db-02` | Đích và hành động nằm ngoài phạm vi grant mô tả |
| 02:11 | Rule nối được danh tính, phiên, grant và audit đích | Cảnh báo có bằng chứng phạm vi, không chỉ bất thường về giờ |
| 02:14 | Đội trực xác nhận ticket không bao phủ hoạt động này | Cần xử lý vi phạm và tiếp tục xác minh nguồn gốc thao tác |

Giờ 02:10 không phải bằng chứng quyết định. Dấu hiệu quan trọng là hoạt động cụ thể trên đích không được grant bao phủ. Cũng không được bỏ qua chỉ vì phiên đi qua PAM và MFA đã thành công.

### 10.3. Hai hướng kết quả khác nhau

Nếu xác minh cho thấy quản trị viên chọn nhầm đích và không có dấu hiệu chiếm dụng, tổ chức vẫn cần xử lý hậu quả thao tác, kiểm tra quyền thực tế và cải thiện giới hạn JEA hoặc mapping đích.

Nếu xuất hiện thêm bằng chứng như thao tác không được người dùng nhận biết, thiết bị có dấu hiệu bị kiểm soát hoặc role bị sử dụng từ nguồn khác, phải điều tra theo hướng chiếm dụng và mở rộng phạm vi kiểm tra.

Hai kết quả có thể bắt đầu từ cùng một cảnh báo. Giá trị của giám sát là đưa ra bằng chứng và ưu tiên đúng, không phải gán trước nguyên nhân.

### 10.4. Nếu dữ liệu grant chưa đầy đủ

Giả sử collector quyền bị mất kết nối đúng cửa sổ trên. Audit vẫn chứng minh hoạt động xuất dữ liệu, nhưng kết luận “không có grant” chưa đủ cơ sở.

Cảnh báo nên thể hiện “chưa xác minh được phạm vi quyền”, kèm nguồn đang lỗi. Đội trực tiếp tục kiểm tra hành động trên tài sản trọng yếu và tra cứu bản ghi cấp quyền tại nguồn có thẩm quyền. Khi nguồn được khôi phục, đánh giá lại cảnh báo và giữ lịch sử kết luận.

## 11. Giảm nhiễu mà vẫn giữ khả năng phát hiện

Những nguyên nhân gây nhiễu thường gặp cần được xử lý cụ thể:

| Nguyên nhân | Cách điều chỉnh phù hợp |
|---|---|
| Luân phiên ca trực | Dùng lịch trực đã xác minh thay cho khung giờ cố định |
| Runner hoặc node autoscaling | Dùng định danh workload, môi trường và phạm vi triển khai |
| VPN/proxy thay đổi IP | Phân tích nguồn IP đúng lớp và bổ sung định danh thiết bị |
| Rotation credential | Liên kết phiên bản credential với cùng tài khoản hoặc workload |
| Di chuyển tài sản | Đối chiếu inventory, ticket và thời hạn thay đổi |
| Job retry hoặc chạy bù | Kiểm tra job ID, lịch dự kiến và mức tăng thực tế |
| Tài khoản mới, ít mẫu | Chuyển sang quy tắc chính sách và hồ sơ vai trò, đánh dấu cold start |
| Log đến trễ hoặc lặp | Đánh giá event time, trạng thái ingest, loại trùng và cập nhật cảnh báo |

Ngoại lệ nên có cấu trúc gồm chủ thể, đích, nhóm thao tác, thời gian hiệu lực, lý do, người phê duyệt và ngày rà soát. Đừng dùng ngoại lệ “mọi hoạt động của admin-db đều hợp lệ”.

Có thể gộp nhiều sự kiện cùng phiên thành một vụ việc để giảm số thông báo. Tuy nhiên, không gộp đến mức mất hành động nghiêm trọng hoặc các tài sản khác phạm vi. Một thao tác thay đổi quyền mới trong cùng phiên vẫn cần được bổ sung vào mức ưu tiên và bằng chứng.

Nhiễu được giảm nhờ ngữ cảnh tốt hơn. Việc tắt rule chỉ để số lượng cảnh báo thấp hơn không chứng minh khả năng giám sát tốt hơn.

## 12. Kiểm thử và đo hiệu quả vận hành

### 12.1. Bộ tình huống giả lập

Dùng log tổng hợp hoặc môi trường được phép để kiểm tra thiết kế, không cần tạo thao tác nguy hiểm trên production.

| Ca kiểm tra | Kết quả mong đợi |
|---|---|
| Quản trị viên vào đích mới trong ticket đúng phạm vi | Ghi nhận tính mới, gắn ngữ cảnh phê duyệt; không kết luận vi phạm |
| Cùng tài khoản vào đích ngoài grant | Tạo cảnh báo chính sách có bằng chứng đối chiếu |
| Tài khoản dịch vụ có sự kiện phiên tương tác được xác nhận | Kích hoạt rule dành cho loại tài khoản này |
| Workload hợp lệ chuyển sang node mới đã khai báo | Đánh giá theo định danh workload thay vì chỉ IP |
| Log PAM đến sau audit đích | Cảnh báo sơ bộ được cập nhật khi đủ dữ liệu, không sinh bản trùng |
| Tên tài khoản giống nhau ở hai tenant | Không gộp thành cùng một chủ thể |
| Tài khoản mới chưa có lịch sử | Áp dụng rule chính sách và đánh dấu thiếu baseline |
| Break-glass có ticket sự cố hợp lệ | Vẫn tạo thông báo sử dụng và yêu cầu hậu kiểm |
| Tài khoản vượt quyền theo mẫu đã lặp nhiều lần | Vẫn phát hiện theo chính sách dù baseline coi hành vi là phổ biến |

Kiểm tra cả phần giải thích: người trực có biết vì sao cảnh báo được tạo không, có mở được bằng chứng và có thấy dữ liệu đang thiếu không.

### 12.2. Chỉ số cần đọc cùng nhau

Các chỉ số có ích gồm độ bao phủ tài khoản đặc quyền, tỷ lệ sự kiện nối được với danh tính/phiên, độ trễ ingest, số cảnh báo theo loại tài khoản, thời gian triage và tỷ lệ kết quả được phân loại rõ.

Có thể tính precision trên tập cảnh báo đã được đánh giá theo nhãn thống nhất:

```text
precision =
  số cảnh báo được xác nhận thuộc mục tiêu phát hiện
  / tổng số cảnh báo đã được phân loại trong tập đánh giá
```

Phải định nghĩa “mục tiêu phát hiện” trước: vi phạm chính sách và chiếm dụng tài khoản là hai mục tiêu khác nhau. Không gộp mọi anomaly hợp lệ vào một nhãn rồi so sánh giữa các đội.

Không thể suy ra recall chỉ từ số cảnh báo đã phát. Cần tập sự kiện có nhãn, mô phỏng hoặc nguồn kiểm chứng độc lập để biết những trường hợp đáng lẽ phải bị phát hiện nhưng đã bị bỏ sót.

Số cảnh báo giảm trong khi collector mất dữ liệu là dấu hiệu đáng lo. Luôn xem chỉ số cảnh báo cùng độ bao phủ và sức khỏe pipeline.

## 13. Câu hỏi tự kiểm tra

1. Một quản trị viên đăng nhập ngoài giờ từ máy được quản lý, có MFA và ticket. Bạn cần kiểm tra thêm gì trước khi đóng cảnh báo?
2. Vì sao không nên coi IP mới là bằng chứng độc lập về một người hoặc workload mới?
3. Một tài khoản dịch vụ đăng nhập tương tác đã nhiều lần trong lịch sử. Baseline có làm hành vi này được phép không?
4. Truy vấn không tìm thấy bản ghi PAM có đủ chứng minh tài khoản bỏ qua PAM không?
5. Một grant còn thời hạn nhưng chỉ cho phép kiểm tra trạng thái máy A. Nó có bao phủ xuất dữ liệu từ máy B không?
6. Vì sao điểm ưu tiên cao không đồng nghĩa với xác suất xâm nhập cao theo cùng tỷ lệ phần trăm?
7. Khi nào nên học một thay đổi vào baseline và khi nào nên giữ nó ngoài tập học?
8. Sau khi đổi mật khẩu tài khoản nghi bị lộ, vì sao vẫn cần kiểm tra phiên và token đang hoạt động?

Gợi ý đối chiếu: hãy trả lời bằng chủ thể, phạm vi quyền, thời gian, hành động quan sát được và độ tin cậy dữ liệu. Một lời giải tốt nêu rõ điều đã biết, điều còn thiếu và bằng chứng cần để ra quyết định tiếp theo.

## 14. Những điểm cần ghi nhớ

Giám sát việc sử dụng tài khoản bất thường trong PAM cần kết hợp chính sách được phép, hành vi đã quan sát và bằng chứng tại tài sản đích. Baseline giúp thấy khác biệt nhưng không thay thế least privilege, phê duyệt quyền hay kiểm tra JIT/JEA.

Một cảnh báo có giá trị phải truy được từ danh tính hoặc workload tới tài khoản hiệu lực, phiên, grant và thao tác; đồng thời thể hiện phần liên kết chưa chắc chắn. Các hành động như khóa tài khoản, chấm dứt phiên hoặc rotation credential cần được chọn theo bằng chứng, mức ảnh hưởng và khả năng thu hồi thực tế.

Mục tiêu là giúp người trực phát hiện việc dùng quyền sai phạm vi, ưu tiên điều tra và lưu được bằng chứng có thể kiểm tra lại — kể cả khi hoạt động đi qua một đường truy cập PAM đã được xác thực thành công.
