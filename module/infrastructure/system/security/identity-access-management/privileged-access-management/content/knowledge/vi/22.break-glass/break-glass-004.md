# Credential lưu trữ thứ cấp cho break-glass

## Mục tiêu bài học

Trong Privileged Access Management (PAM), credential thường được quản lý qua vault và quy trình cấp quyền thông thường. Khi vault, IdP hoặc một thành phần phụ thuộc không sẵn sàng, tổ chức vẫn có thể cần một đường truy cập khẩn cấp để khôi phục hệ thống.

**Credential lưu trữ thứ cấp** là credential hoặc vật liệu khôi phục được giữ bằng một cơ chế bổ sung, có mục đích break-glass và vòng đời riêng. Nó phải vừa đủ sẵn sàng khi cần, vừa được bảo vệ để không trở thành đường truy cập thường trực ngoài kiểm soát.

Sau bài học, bạn có thể:

- Phân biệt bản sao vault, bản sao credential và credential khẩn cấp độc lập.
- Phân tích phụ thuộc của nơi lưu, khóa giải mã, danh tính và đường truy cập.
- Thiết kế quyền giữ, quyền lấy và kiểm soát hai người khi phù hợp.
- Quản lý phiên bản và cập nhật sau luân chuyển credential.
- Thực hiện quy trình sử dụng, thu hồi và khôi phục trạng thái sẵn sàng.
- Kiểm chứng khả năng dùng được mà không ghi bí mật vào hồ sơ.

Tên tài khoản, trạng thái, thời hạn và mô hình dữ liệu trong bài là minh họa. Chúng không phải cấu hình của một sản phẩm hoặc yêu cầu áp dụng chung cho mọi tổ chức.

## 1. “Có bản sao” khác “có thể khôi phục”

Giả sử mật khẩu quản trị khẩn cấp được mã hóa và lưu ngoài vault chính. Khi vault gặp sự cố, đội vận hành cần mở bản sao đó.

Tuy nhiên:

- Khóa giải mã chỉ lấy được qua chính vault đang hỏng.
- Đăng nhập nơi lưu bản sao cần IdP đang mất kết nối.
- Mật khẩu trong bản sao đã cũ sau lần luân chuyển gần nhất.
- Tài khoản đích đã bị vô hiệu hóa và cách kích hoạt lại cũng phụ thuộc hệ thống đang lỗi.
- Người giữ vật liệu khôi phục không thể được liên hệ.

Bản sao tồn tại nhưng đường khôi phục không hoạt động.

Một thiết kế tốt phải kiểm tra toàn đường:

```text
Người có trách nhiệm
    -> Xác minh và cho phép kích hoạt break-glass
    -> Tiếp cận nơi lưu thứ cấp
    -> Có vật liệu/khóa cần thiết
    -> Lấy đúng credential còn hiệu lực
    -> Có nguồn và đường truy cập tới tài sản
    -> Xác thực và khôi phục trong phạm vi
    -> Thu hồi, luân chuyển và tái lập sẵn sàng
```

Nếu một bước bắt buộc phụ thuộc vào thành phần đang cần khôi phục, có thể xuất hiện vòng phụ thuộc.

## 2. Phân biệt ba mô hình thường gặp

| Mô hình | Điều được lưu hoặc chuẩn bị | Ưu điểm | Giới hạn cần đánh giá |
|---|---|---|---|
| Sao lưu hoặc bản sao hệ thống vault | Dữ liệu và cấu hình cần để phục hồi vault | Hỗ trợ phục hồi nền tảng | Có thể cần hạ tầng, khóa và thời gian khôi phục trước khi lấy được bí mật |
| Bản sao thứ cấp của cùng credential | Một credential được giữ ở thêm nơi khác | Có thể truy cập bí mật khi đường chính lỗi | Phải luôn biết phiên bản nào còn hợp lệ tại đích |
| Credential khẩn cấp riêng | Tài khoản, khóa hoặc phương thức được chuẩn bị riêng cho break-glass | Có thể giảm phụ thuộc vào luồng chính | Tạo thêm danh tính/quyền phải bảo vệ và rà soát |

Các mô hình có thể được kết hợp, nhưng không nên gọi tất cả là cùng một giải pháp.

Một replica ở khu vực khác vẫn có thể dùng chung IAM, khóa, tài khoản quản trị hoặc control plane. Địa điểm khác không tự chứng minh độc lập trước mọi loại sự cố.

Credential riêng cũng không mặc định an toàn hơn. Nếu có quyền quá rộng, không giám sát và không ai kiểm tra, nó trở thành một điểm yếu bổ sung.

### 2.1. Sao lưu không thay kế hoạch truy cập tức thời

Một bản backup mã hóa có thể phù hợp mục tiêu phục hồi dữ liệu vault, nhưng chưa chắc đáp ứng thời gian lấy credential khẩn cấp.

Cần mô tả rõ cần phục hồi toàn hệ thống, đọc một hiện vật được chuẩn bị trước hay dùng một danh tính khác đã được chấp nhận ở đích.

### 2.2. Credential khẩn cấp phải được hệ thống đích chấp nhận

Một chuỗi bí mật được lưu cẩn thận không tạo ra quyền nếu tài khoản không tồn tại, khóa công khai không được đăng ký hoặc chính sách đích chặn phương thức đó.

Ngược lại, một tài khoản được vô hiệu hóa có thể không hữu ích nếu người duy nhất có quyền bật nó cần chính đường đăng nhập đã mất.

Cấu hình tài khoản và điều kiện kích hoạt cần được thử theo kịch bản sự cố, không chỉ trong trạng thái bình thường.

## 3. Phân tích phụ thuộc theo kịch bản sự cố

### 3.1. Các lớp cần xét

| Lớp | Câu hỏi |
|---|---|
| Danh tính | Ai được nhận credential, xác minh họ bằng cách nào khi IdP chính lỗi? |
| Nơi lưu | Có truy cập được nếu mạng, vùng hoặc tài khoản dịch vụ chính không sẵn sàng không? |
| Khóa giải mã | Nguồn khóa có độc lập đủ cho kịch bản đang xét không? |
| Thiết bị | Có nguồn quản trị phù hợp để mở hiện vật và thực hiện công việc không? |
| Mạng và console | Đường tới tài sản có phụ thuộc gateway đang lỗi không? |
| Đích | Tài khoản, chứng thư, khóa và chính sách xác thực còn chấp nhận không? |
| Con người | Người giữ và người phê duyệt có sẵn theo kế hoạch không? |
| Bằng chứng | Nếu log chính không sẵn sàng, ghi nhận và bảo toàn bằng cách nào? |

“Độc lập” phải gắn với một kịch bản. Kho thứ cấp có thể độc lập trước sự cố một vùng nhưng không độc lập trước việc quản trị viên IAM bị xâm nhập.

### 3.2. Sự cố khả dụng khác sự cố xâm nhập

Nếu mục tiêu là xử lý IdP mất kết nối, một đường xác thực riêng được chuẩn bị có thể hữu ích.

Nếu nghi IdP hoặc vault bị xâm nhập, cần đánh giá độ tin cậy của dữ liệu, khóa, tài khoản và bản sao liên quan. Không khôi phục hoặc dùng lại mọi thứ từ đường bị nghi ngờ mà mặc định nó còn sạch.

Kế hoạch nên phân biệt những kịch bản này, cùng thẩm quyền quyết định đường khôi phục nào được phép dùng.

### 3.3. Không tạo một đường mở mặc định

Break-glass không có nghĩa bất kỳ ai cũng được dùng mật khẩu dự phòng khi đăng nhập bình thường gặp lỗi.

Cần có điều kiện kích hoạt, tài sản, người chịu trách nhiệm, phạm vi, thời hạn và cách đóng quyền. Một lỗi kết nối đơn lẻ không tự cấp thêm thẩm quyền.

## 4. Chọn phạm vi credential cần lưu thứ cấp

Không nhất thiết sao chép mọi secret của tổ chức. Điều đó làm tăng bề mặt cần bảo vệ và khối lượng duy trì.

Nên bắt đầu từ các mục tiêu khôi phục cụ thể:

- Khôi phục một thành phần định danh.
- Truy cập nền tảng quản lý cần để sửa vault.
- Tiếp cận console hoặc thiết bị mạng trong kịch bản đã xác định.
- Mở đường tới một tập tài sản tối thiểu để phục hồi dịch vụ thiết yếu.

Mỗi mục nên có chủ sở hữu, lý do, phạm vi quyền và điều kiện sử dụng.

### 4.1. Credential khác nhau có cách sao lưu khác nhau

| Loại vật liệu | Điều cần hiểu |
|---|---|
| Mật khẩu | Có thể thay đổi tại đích, cần cập nhật bản thứ cấp |
| Khóa riêng | Cần bảo vệ vật liệu bí mật và biết tài sản nào chấp nhận nó |
| Chứng thư | Cần xét cả khóa riêng, hạn chứng thư và trạng thái tin cậy |
| Recovery code | Có thể dùng một lần hoặc bị vô hiệu hóa sau khi tạo bộ mới |
| Thiết bị xác thực vật lý | Có thể cần phương thức dự phòng được đăng ký riêng |
| Khóa giải mã hoặc vật liệu khôi phục | Giúp truy cập dữ liệu, chưa chắc là credential đăng nhập tài sản |

Bản sao chứng thư công khai không thay cho khóa riêng. Một khóa không xuất được khỏi phần cứng không thể được “backup” bằng cách lưu thêm phần công khai; cần phương án dự phòng mà nền tảng hỗ trợ.

Không áp dụng cùng một cách xuất và lưu cho mọi loại credential.

### 4.2. Giảm phạm vi ảnh hưởng

Nếu có thể, tách credential theo tài sản hoặc phạm vi khôi phục. Một secret mở được toàn bộ hạ tầng có hậu quả lớn khi bị lộ.

Tài khoản khẩn cấp cần đủ khả năng cho mục tiêu đã xác định, nhưng không nên có quyền ngoài mục tiêu chỉ để thuận tiện. Những trường hợp bắt buộc quyền rất cao phải được nhận diện và bảo vệ tương xứng.

## 5. Nơi lưu, mã hóa và người giữ

### 5.1. Kho điện tử thứ cấp

Một kho điện tử cần được đánh giá về quyền truy cập, mã hóa, quản lý khóa, giám sát và khả năng dùng khi thành phần chính gặp sự cố.

Không mặc định “đã mã hóa” là đủ. Cần trả lời:

- Ai có thể lấy bản mã?
- Ai có thể dùng khóa giải mã?
- Hai quyền đó có bị gộp vào cùng một danh tính dễ bị chiếm không?
- Khóa có cần chính IdP, vault hoặc vùng đang lỗi không?
- Có cách kiểm chứng nguồn gốc và phiên bản của hiện vật không?
- Ai có thể sửa, xóa hoặc thay bằng một bản khác?

Nên dùng cơ chế mật mã và công cụ được quản trị phù hợp, không tự tạo thuật toán mã hóa hoặc quy tắc chia mật khẩu bằng tay.

Mã băm giúp đối chiếu dữ liệu với một mốc đáng tin. Nó không tự bảo mật giá trị secret hoặc chứng minh nguồn gốc nếu chính mốc đó cũng bị thay.

### 5.2. Vật liệu offline hoặc vật lý

Một số kế hoạch có thể sử dụng hiện vật mã hóa trên phương tiện được quản lý hoặc vật liệu được niêm phong tại địa điểm phù hợp.

Cần kiểm soát:

- Người được giữ và người được lấy.
- Địa điểm, điều kiện tiếp cận và phương án khi một địa điểm không sẵn sàng.
- Niêm phong, định danh gói và lịch sử bàn giao.
- Phiên bản, ngày cập nhật và trạng thái sẵn sàng.
- Cách mở bằng thiết bị tin cậy.
- Cách thay thế hoặc xử lý sau sử dụng.

Dấu niêm phong hỗ trợ phát hiện một số thay đổi vật lý; không bảo đảm bí mật chưa từng bị sao chép. Một USB hoặc tệp mã hóa cũng không tự an toàn nếu được mở trên máy bị xâm nhập.

Không gửi ảnh gói bí mật, mã khôi phục hoặc khóa giải mã qua kênh trao đổi thông thường để “làm bản dự phòng”.

### 5.3. Kiểm soát hai người và chia vật liệu mật mã

Có hai ý tưởng khác nhau:

- Hai người phải tham gia quyết định hoặc thao tác lấy credential.
- Vật liệu được chia theo một cơ chế mật mã có ngưỡng, cần đủ phần mới khôi phục được.

Quy trình hai người không tự biến thành cơ chế chia bí mật. Ngược lại, có đủ phần mật mã không tự chứng minh người lấy đã được phép sử dụng.

Nếu dùng cơ chế ngưỡng, cần giải pháp được đánh giá, quản lý người giữ, thay phần và diễn tập. Không chia chuỗi mật khẩu thành vài đoạn rồi mặc định đã đạt mức bảo vệ tương đương.

Cũng cần xét khả dụng: nếu chỉ một nhóm rất nhỏ giữ vật liệu và cùng vắng mặt, đường khẩn cấp có thể không dùng được. Phương án dự phòng phải được thiết kế mà vẫn giữ trách nhiệm và giới hạn.

### 5.4. Tách quyền quản trị nơi lưu và quyền sử dụng

Người vận hành hệ thống lưu không nhất thiết cần xem mọi giá trị bí mật. Người phê duyệt break-glass cũng không nhất thiết cần giữ credential thường trực.

Cần đánh giá những quyền gián tiếp như cấp lại vai trò, thay chính sách khóa hoặc đọc snapshot. Tách trên giao diện không đủ nếu một người vẫn có toàn quyền ở lớp bên dưới.

## 6. Phiên bản và đồng bộ sau luân chuyển

Đây là điểm dễ làm một phương án dự phòng mất hiệu lực.

### 6.1. Bản sao đúng lúc tạo có thể sai lúc dùng

Giả sử mật khẩu được đổi từ phiên bản 17 sang 18 tại đích. Vault chính đã cập nhật, nhưng bản thứ cấp còn phiên bản 17.

Nếu đích không còn chấp nhận phiên bản 17, bản thứ cấp không đáp ứng khả năng khôi phục dù tệp vẫn mở được.

Tần suất backup hay một mục tiêu mất dữ liệu chung không đủ để chứng minh credential hợp lệ. Cần biết trạng thái thực tế của từng mục và cách credential đó thay đổi.

### 6.2. Metadata không chứa giá trị secret

```yaml
secondary_credential_record:
  record_id: BG-REC-142
  target_reference: recovery-target-07
  account_reference: emergency-account-02
  credential_type: password
  credential_version: 18
  storage_package_reference: sealed-package-309
  key_custody_reference: custody-plan-12
  owner_reference: identity-recovery-team
  authorized_use: restore_identity_service
  updated_at: "2026-12-08T16:30:00+07:00"
  validation:
    checked_version: 18
    checked_at: "2026-12-08T16:45:00+07:00"
    evidence_reference: validation-evidence-901
  readiness_status: validated
```

Mẫu này chỉ mô tả hồ sơ. Không đưa mật khẩu vào phần metadata hoặc bằng chứng kiểm tra.

Trạng thái `validated` cần có căn cứ. Việc khớp số phiên bản trong hai hồ sơ chưa chứng minh đích chấp nhận credential; cần phương pháp xác minh phù hợp với loại credential và nền tảng.

Kết quả xác minh tại một thời điểm cũng không bảo đảm credential sẽ còn hiệu lực mãi sau đó.

### 6.3. Luân chuyển là một chuỗi có thể lỗi từng phần

Nhiều môi trường không có giao dịch nguyên tử bao trùm đích, vault chính và kho thứ cấp.

Cần xác định trạng thái như:

| Trạng thái quan sát | Ý nghĩa |
|---|---|
| Đích và các nơi giữ dự kiến cùng phiên bản đã xác minh | Có bằng chứng sẵn sàng theo phạm vi kiểm tra |
| Đích đã đổi, kho thứ cấp chưa cập nhật | Bản thứ cấp có thể không dùng được |
| Hiện vật đã cập nhật nhưng chưa xác minh | Chưa đủ bằng chứng để đánh dấu sẵn sàng |
| Không biết đích đã đổi thành công chưa | Cần đối soát trước khi thử lại hoặc tiếp tục |
| Tác vụ cập nhật cũ đến sau phiên bản mới | Có nguy cơ ghi đè bằng dữ liệu lỗi thời |

Quy trình cần bảo vệ vật liệu ứng viên, ghi trạng thái bền vững phù hợp, kiểm tra phiên bản và có cách xử lý thất bại. Không để một tác vụ thử lại tự ghi đè bản mới bằng bản cũ.

Nếu nền tảng hỗ trợ hai khóa hoặc hai phương thức có thể cùng có hiệu lực trong giai đoạn chuyển tiếp, có thể thiết kế khoảng chuyển tiếp được giới hạn. Không giả định mọi tài khoản hỗ trợ hai mật khẩu đồng thời.

Nếu cập nhật thứ cấp thất bại sau khi đích đã đổi, phải phản ánh trạng thái giảm sẵn sàng, giao người xử lý và áp dụng phương án khôi phục đã thiết kế. Không đánh dấu “rotation completed” như thể mọi bản sao đều dùng được.

### 6.4. Credential riêng có vòng đời riêng

Một tài khoản khẩn cấp riêng có thể không thay bí mật cùng nhịp với tài khoản dùng hằng ngày. Điều đó không có nghĩa không cần luân chuyển hoặc kiểm tra.

Cần theo dõi hạn chứng thư, phương thức xác thực, trạng thái tài khoản, thay đổi chính sách, người giữ và việc lộ vật liệu. Khi dùng hoặc nghi lộ, xử lý theo loại credential và khả năng thu hồi của nền tảng.

Không giữ mật khẩu cũ còn dùng được vô thời hạn để tránh phải cập nhật hiện vật.

## 7. Quy trình lấy và sử dụng khi break-glass

### 7.1. Xác nhận tình huống

Ghi nhận thành phần lỗi, mục tiêu cần khôi phục, phạm vi và người có thẩm quyền kích hoạt. Xác minh người thực hiện qua kênh được chuẩn bị, kể cả khi công cụ liên lạc thông thường không hoạt động.

Một người tự nhận là quản trị viên qua điện thoại không đủ để được nhận credential.

### 7.2. Lấy đúng hiện vật

Đối chiếu target, tài khoản, phiên bản và trạng thái. Người giữ ghi nhận ai lấy, lý do, thời điểm và mã sự cố theo quy trình.

Nếu hiện vật có dấu bất thường hoặc không xác định được nguồn, cần xử lý theo kế hoạch thay vì mặc định tin cậy vì đang khẩn cấp.

### 7.3. Mở từ nguồn phù hợp

Dùng thiết bị và công cụ được phép. Không giải mã trên một máy hằng ngày đang bị nghi xâm nhập, không đưa secret vào công cụ chat và không ghi vào command history hoặc ticket.

Credential chỉ nên được tiếp cận bởi người cần sử dụng. Nếu có phương thức thiết lập phiên mà không tiết lộ bí mật và vẫn dùng được trong kịch bản sự cố, cần đánh giá khả năng đó.

### 7.4. Thực hiện trong phạm vi

Ưu tiên thao tác khôi phục tối thiểu cần thiết. Không dùng lần break-glass để làm thêm công việc không liên quan.

Nếu PAM hoặc ghi phiên chính không hoạt động, áp dụng cách ghi nhận thay thế đã được cho phép và bảo vệ dữ liệu. Không mô tả phiên như đã được ghi đầy đủ nếu bằng chứng đó không tồn tại.

### 7.5. Kiểm tra và kết thúc

Xác nhận hệ thống đã phục hồi theo tiêu chí, chấm dứt phiên và xử lý quyền tạm. Ghi những thay đổi thực tế, tác vụ còn chạy và phần chưa hoàn tất.

Một ticket đóng không tự thu hồi credential hoặc kết thúc các phiên đã được tạo.

## 8. Sau sử dụng: đóng quyền và tái lập sẵn sàng

Một lần break-glass chưa hoàn tất chỉ vì dịch vụ đã hoạt động lại. Credential đã được tiếp cận hoặc sử dụng cần được xử lý theo chính sách.

### 8.1. Những việc cần xem xét

- Kết thúc phiên, token hoặc grant đã tạo.
- Luân chuyển mật khẩu hoặc thu hồi vật liệu đã dùng khi phù hợp.
- Thay recovery code đã tiêu thụ và kiểm tra bộ mới.
- Cập nhật hiện vật thứ cấp theo phiên bản đang có hiệu lực.
- Kiểm tra tài khoản, khóa hoặc tác vụ mới tạo trong lúc khôi phục.
- Xác nhận nơi lưu, khóa và người giữ đã trở lại trạng thái được yêu cầu.
- Rà soát bằng chứng và các ngoại lệ.

Loại credential quyết định hành động cụ thể. Một thiết bị xác thực vật lý không có cùng quy trình thay thế với mật khẩu; một khóa đã lộ có thể cần thay và thu hồi ở những nơi chấp nhận nó.

Luân chuyển cũng cần xét phụ thuộc. Không đổi một credential dùng chung cho dịch vụ mà không biết cách cập nhật và kiểm chứng những bên sử dụng.

### 8.2. Không đồng nhất đổi bí mật với kết thúc phiên

Một phiên đã xác thực có thể còn hiệu lực sau khi đổi mật khẩu, tùy nền tảng và cơ chế. Token, khóa phiên hoặc tiến trình tại đích có thể cần xử lý riêng.

Cần bằng chứng thực thi, không chỉ lời xác nhận rằng “mật khẩu đã đổi”.

### 8.3. Trạng thái sẵn sàng sau sự cố

Có thể biểu diễn vòng đời như sau:

```text
Đã chuẩn bị và xác minh
        |
        v
Được phát hành cho tình huống khẩn cấp
        |
        v
Đang sử dụng / đã tiếp cận
        |
        v
Thu hồi và xử lý sau sử dụng
        |
        v
Cập nhật hiện vật + xác minh lại
        |
        v
Trở lại trạng thái sẵn sàng
```

Nếu hiện vật mới chưa được xác minh hoặc credential chưa xử lý xong, trạng thái cần phản ánh điều đó. Không tự đưa về “ready” chỉ vì hồ sơ sự cố đã đóng.

## 9. Tình huống thực hành: vault không truy cập được

### 9.1. Bối cảnh

Một thành phần định danh gặp sự cố và vault chính không thể truy cập theo luồng thông thường. Đội khôi phục cần vào console của một nền tảng được xác định trong kế hoạch.

Tổ chức đã chuẩn bị một tài khoản khẩn cấp riêng cho mục tiêu này. Vật liệu liên quan được lưu thứ cấp bằng phương án đã kiểm thử, với người giữ và đường xác minh không phụ thuộc hoàn toàn vào IdP đang lỗi.

Đây là mô tả tình huống, không phải khuyến nghị tạo tài khoản chung có quyền toàn hệ thống.

### 9.2. Diễn biến

| Mốc | Sự kiện | Hành động cần có |
|---|---|---|
| Phát hiện | Không truy cập được vault qua luồng chuẩn | Xác định tình huống và mục tiêu khôi phục |
| Kích hoạt | Người có thẩm quyền xác nhận break-glass | Ghi phạm vi, người thực hiện và điều kiện |
| Lấy vật liệu | Người giữ bàn giao hiện vật theo quy trình | Xác minh người nhận, mã gói và phiên bản |
| Trước đăng nhập | Kiểm tra nguồn quản trị và đường console | Không mở bí mật trên endpoint không phù hợp |
| Khôi phục | Thực hiện thao tác tối thiểu trong phạm vi | Ghi bằng chứng và thay đổi thực tế |
| Sau phục hồi | Luồng thông thường hoạt động lại | Kết thúc quyền khẩn cấp và đối soát |
| Tái lập | Credential và hiện vật được xử lý | Xác minh và trả về trạng thái sẵn sàng |

### 9.3. Biến thể: bản thứ cấp cũ

Đội khôi phục thấy metadata ghi phiên bản 17, trong khi hồ sơ cập nhật cho thấy đích đã chuyển sang 18.

Không nên thử hàng loạt mật khẩu cũ đến khi một cái hoạt động. Việc đó có thể gây khóa tài khoản và không giải quyết được tính tin cậy của hồ sơ.

Cần dùng phương án được thiết kế cho trường hợp credential lỗi thời, xác định trạng thái đích và liên hệ vai trò có trách nhiệm. Sau sự cố, phải sửa cơ chế cập nhật để không lặp lại khoảng trống này.

### 9.4. Biến thể: khóa giải mã mắc vòng phụ thuộc

Gói được mã hóa nhưng người giữ chỉ có thể lấy khóa thông qua vault chính.

Đây là lỗi thiết kế khả dụng theo kịch bản đang xét. Không khắc phục bằng cách bỏ mã hóa hoặc gửi khóa công khai qua chat. Cần một kế hoạch quản lý vật liệu khôi phục phù hợp và được kiểm thử trước.

Nếu chưa có đường đó trong thời điểm sự cố, hồ sơ phải ghi đúng giới hạn thay vì tuyên bố đã có dự phòng hoạt động.

### 9.5. Biến thể: tài khoản đích bị chặn bởi điều kiện không còn đáp ứng

Credential đúng nhưng chính sách xác thực hoặc đường mạng không cho phép đăng nhập khi một thành phần phụ thuộc lỗi.

Cần kiểm tra toàn luồng chứ không chỉ giá trị secret. Không tự loại bỏ mọi điều kiện bảo vệ của tài khoản khẩn cấp. Điều kiện và đường thay thế phải được thiết kế theo rủi ro, bảo vệ phù hợp và xác minh bằng diễn tập.

### 9.6. Biến thể: nghi vault bị xâm nhập

Nếu sự cố là dấu hiệu xâm nhập, không nên mặc định bản sao từ vault cũng đáng tin hoặc credential đó chưa bị biết.

Cần đánh giá nguồn gốc, thời điểm, khả năng lộ bí mật và hệ thống đích. Có thể cần một đường khôi phục khác hoặc thay credential theo quy trình đã chuẩn bị.

Khôi phục khả dụng và khôi phục niềm tin là hai mục tiêu liên quan nhưng không giống nhau.

## 10. Diễn tập và kiểm chứng định kỳ

Diễn tập cần có phạm vi, người chịu trách nhiệm và cách kiểm soát tác động. Không tùy tiện tắt hạ tầng định danh sản xuất để thử.

Có thể kết hợp kiểm tra hồ sơ, diễn tập bàn giấy, kiểm thử môi trường phù hợp và bài thử có kiểm soát theo kế hoạch.

| Phép thử | Điều cần xác nhận |
|---|---|
| Luồng chính không khả dụng theo kịch bản | Có thể tiếp cận vật liệu mà không mắc vòng phụ thuộc |
| IdP chính không dùng được | Xác minh người nhận và truy cập nơi lưu theo kế hoạch |
| Một người giữ hoặc địa điểm không sẵn sàng | Phương án dự phòng con người và vật lý hoạt động |
| Hiện vật đúng nhưng khóa không lấy được | Phát hiện phụ thuộc và không đánh dấu sẵn sàng giả |
| Kiểm tra phiên bản sau rotation | Bản thứ cấp phù hợp trạng thái đích |
| Đích đổi thành công nhưng cập nhật thứ cấp lỗi | Có trạng thái giảm sẵn sàng và xử lý |
| Tác vụ cập nhật cũ chạy sau bản mới | Không ghi đè bằng credential lỗi thời |
| Chứng thư hoặc phương thức sắp hết hạn | Có phát hiện và kế hoạch thay trước khi không dùng được |
| Tài khoản bị khóa hoặc điều kiện đích thay đổi | Có thể phát hiện trước khi cần sử dụng thật |
| Mở hiện vật bằng nguồn quản trị phù hợp | Công cụ và quy trình dùng được mà không lộ secret vào log |
| Credential được lấy nhưng chưa dùng | Vẫn xử lý việc tiếp cận theo chính sách |
| Sau một lần dùng | Phiên/token và vật liệu liên quan được thu hồi hoặc thay đúng cách |
| Mất log chính | Bằng chứng thay thế có trách nhiệm và bảo vệ phù hợp |
| Hoàn tất kiểm tra | Hệ thống được đưa lại về trạng thái sẵn sàng đã xác minh |

Một bài thử đăng nhập thành công chỉ xác nhận một số điều kiện tại thời điểm đó. Cần biết thay đổi nào sau đó buộc kiểm tra lại: rotation, sửa policy, đổi người giữ, thay khóa, thay mạng hoặc thay phương thức xác thực.

Cũng cần bảo vệ việc kiểm thử để không tạo các bản sao secret ngoài kế hoạch. Không chụp ảnh hoặc dán giá trị bí mật vào báo cáo để chứng minh đã lấy được.

### Chỉ số hữu ích

Có thể theo dõi:

- Số mục chưa có chủ sở hữu.
- Số hiện vật quá hạn kiểm tra theo chính sách.
- Chênh lệch phiên bản và thời gian xử lý.
- Thời gian hoàn thành các bước trong diễn tập.
- Trường hợp không đạt vì người giữ hoặc phụ thuộc.
- Số lần dùng khẩn cấp và tình trạng xử lý sau sử dụng.

Các chỉ số cần gắn với phạm vi thực tế. “Có đủ tệp backup” không phải chỉ số đầy đủ về khả năng break-glass.

## 11. Hồ sơ và bằng chứng cần giữ

Một bộ hồ sơ có thể nối được:

```text
Mục tiêu khôi phục
    -> Tài sản và tài khoản/phương thức
    -> Phiên bản credential
    -> Hiện vật thứ cấp và cơ chế giữ khóa
    -> Người giữ và thẩm quyền phát hành
    -> Lần lấy/sử dụng
    -> Thay đổi và kết quả khôi phục
    -> Thu hồi + cập nhật + xác minh lại
```

Nội dung hữu ích gồm:

- Chủ sở hữu, phạm vi và kịch bản được hỗ trợ.
- Sơ đồ phụ thuộc và những điều kiện không được bao phủ.
- Tham chiếu hiện vật, khóa, người giữ và phiên bản.
- Kết quả kiểm tra cùng thời điểm.
- Người cho phép, người nhận và mã sự cố.
- Mốc sử dụng, đích, phiên và thao tác liên quan.
- Hành động sau sử dụng và kết quả thực thi.
- Khoảng trống bằng chứng, ngoại lệ và việc khắc phục.

Không lưu giá trị secret, khóa giải mã, OTP, mã khôi phục hoặc token trong hồ sơ thông thường. Metadata cũng có thể nhạy cảm vì chỉ ra đường khẩn cấp, nên cần phân quyền và bảo vệ toàn vẹn.

Khi thay thế hoặc xử lý hiện vật cũ, phải theo vòng đời được xác định. Không để những bản đã nghỉ dùng nhưng còn credential hiệu lực tiếp tục nằm ở nhiều nơi không kiểm kê.

## 12. Những sai lầm thường gặp

**Đặt bản thứ cấp ở nơi cần chính vault để mở.** Cần phân tích toàn bộ phụ thuộc theo sự cố.

**Coi replica khác vùng là độc lập hoàn toàn.** Nó có thể vẫn dùng chung IAM, khóa hoặc control plane.

**Sao chép mọi secret mà không có mục tiêu.** Tăng bề mặt bảo vệ và nguy cơ lỗi thời.

**Không cập nhật sau rotation.** Bản sao còn đọc được nhưng không xác thực được tại đích.

**Coi có cùng số phiên bản là đã dùng được.** Cần phương pháp xác minh phù hợp trạng thái đích.

**Chia mật khẩu thủ công rồi gọi là cơ chế ngưỡng.** Cần phân biệt quy trình nhiều người với giải pháp mật mã.

**Lưu chứng thư công khai rồi cho rằng đã có khóa dự phòng.** Phần công khai không thay vật liệu bí mật hoặc phương thức dự phòng.

**Vô hiệu hóa tài khoản khẩn cấp nhưng không kiểm tra đường bật lại.** Có thể tự tạo vòng phụ thuộc.

**Đổi mật khẩu rồi bỏ qua phiên cũ.** Thu hồi cần xét token, kết nối và tác vụ.

**Đóng sự cố mà chưa tái lập hiện vật.** Đường khẩn cấp cho lần sau có thể không còn sẵn sàng.

## 13. Tự kiểm tra

1. Vì sao backup vault chưa chắc đáp ứng nhu cầu lấy credential tức thời?
2. Bản sao cùng credential khác tài khoản khẩn cấp riêng như thế nào?
3. Cần xét những phụ thuộc nào ngoài nơi giữ tệp?
4. Điều gì xảy ra khi đích đã đổi mật khẩu nhưng bản thứ cấp chưa cập nhật?
5. Kiểm soát hai người có tự là chia bí mật bằng mật mã không?
6. Có thể dùng bản sao chứng thư công khai thay cho khóa riêng không?
7. Sau khi dùng break-glass, vì sao cần xử lý cả phiên và hiện vật?
8. Khi nghi hệ thống chính bị xâm nhập, vì sao không chỉ khôi phục bản sao rồi tiếp tục?

### Gợi ý trả lời

1. Có thể phải phục hồi nền tảng, lấy khóa và đáp ứng các phụ thuộc trước khi đọc được bí mật.
2. Một mô hình phải đồng bộ cùng secret; mô hình kia có danh tính hoặc phương thức riêng nhưng thêm vòng đời cần quản trị.
3. Danh tính, khóa, người giữ, thiết bị, mạng/console, tài khoản đích và bằng chứng.
4. Đường dự phòng có thể không dùng được; phải ghi trạng thái giảm sẵn sàng và xử lý.
5. Không. Đó là hai cơ chế khác nhau và có thể bổ sung cho nhau.
6. Không. Cần vật liệu hoặc phương thức được nền tảng chấp nhận.
7. Secret có thể đã được biết, phiên có thể còn tồn tại và bản thứ cấp cần được cập nhật để dùng lần sau.
8. Dữ liệu, khóa hoặc credential có thể đã mất độ tin cậy; cần đánh giá khôi phục niềm tin cùng khả dụng.

## Kết luận

Credential lưu trữ thứ cấp chỉ có giá trị khi lấy được bằng một đường phù hợp với kịch bản sự cố và vẫn được hệ thống đích chấp nhận. Nơi lưu, khóa, danh tính, người giữ và đường truy cập cần được xem như một chuỗi khôi phục hoàn chỉnh.

Trong PAM, chuỗi đó phải có phạm vi tối thiểu, phiên bản được quản lý, quy trình phát hành có trách nhiệm và xử lý sau sử dụng. Diễn tập và bằng chứng xác minh giúp phân biệt một bản sao đang tồn tại với một khả năng break-glass thực sự sẵn sàng.
