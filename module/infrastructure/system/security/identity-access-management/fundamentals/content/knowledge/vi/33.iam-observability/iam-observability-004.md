# Account lockout rate — Tỷ lệ khóa tài khoản

## 1. Chỉ số này giúp quan sát điều gì?

Account lockout là việc hệ thống tạm thời hoặc có điều kiện ngăn một tài khoản tiếp tục xác thực, thường sau khi số lần xác thực thất bại chạm ngưỡng của chính sách. Trong IAM observability, **account lockout rate** giúp trả lời: trong nhóm tài khoản có hoạt động xác thực, bao nhiêu tài khoản vừa bị khóa trong khoảng thời gian đang xét?

Chỉ số này nằm ở giao điểm giữa an toàn và khả năng truy cập. Một đợt khóa tăng có thể cho thấy cơ chế chống đoán mật khẩu đang hoạt động, nhưng cũng có thể phản ánh người dùng hợp lệ bị cản trở bởi thông tin đăng nhập cũ, ứng dụng lỗi hoặc chính sách quá nhạy. Vì vậy, không thể kết luận hệ thống an toàn hơn chỉ vì số lần khóa tăng, hoặc trải nghiệm tốt hơn chỉ vì tỷ lệ khóa giảm.

Ví dụ, sau một đợt đổi mật khẩu, ứng dụng thư điện tử trên điện thoại vẫn gửi mật khẩu cũ. Tài khoản bị khóa liên tục dù chủ tài khoản nhập đúng mật khẩu trên trình duyệt. Nếu chỉ nhìn số lần đăng nhập thất bại, đội vận hành có thể nhầm đây là tấn công; nếu liên kết được thời điểm đổi mật khẩu, ứng dụng nguồn và các lần khóa, nguyên nhân trở nên rõ hơn.

Trong bài này, các tên sự kiện, công thức và ngưỡng cảnh báo là một thiết kế minh họa. Khi áp dụng vào IdP hoặc directory thực tế, cần ánh xạ sang ngữ nghĩa của sản phẩm đang sử dụng.

## 2. Xác định đúng sự kiện khóa

### 2.1. Phân biệt chuyển trạng thái với yêu cầu bị từ chối

Một tài khoản đang được phép xác thực chuyển sang trạng thái bị khóa là **một lần bắt đầu khóa**. Các yêu cầu tiếp theo bị từ chối do tài khoản vẫn đang khóa không tạo thêm lần bắt đầu khóa.

```text
09:00:00  Xác thực thất bại, chưa chạm ngưỡng
09:00:05  Xác thực thất bại, chạm ngưỡng → bắt đầu khóa L1
09:00:10  Yêu cầu bị từ chối vì đang khóa L1
09:00:20  Yêu cầu bị từ chối vì đang khóa L1
09:15:05  Khóa L1 hết hiệu lực
09:30:00  Một chuỗi thất bại mới chạm ngưỡng → bắt đầu khóa L2
```

Chuỗi trên có hai đợt khóa, một tài khoản bị ảnh hưởng và hai yêu cầu bị từ chối vì khóa đang có hiệu lực. Ba đại lượng đó phục vụ ba câu hỏi khác nhau.

Trong hệ thống nhiều node, nơi thay đổi trạng thái tài khoản nên phát sự kiện bắt đầu khóa sau khi cập nhật trạng thái thành công. Nếu mỗi node tự suy ra sự kiện từ mã lỗi đăng nhập, cùng một đợt khóa có thể bị đếm nhiều lần. Log được chuyển tiếp qua nhiều hệ thống cũng cần được khử trùng theo `event_id`; có thể dùng thêm `lockout_episode_id` để đối chiếu các sự kiện thuộc cùng đợt khóa.

### 2.2. Không gom mọi hình thức chặn truy cập vào lockout

| Hiện tượng | Cách xử lý khi thiết kế chỉ số |
|---|---|
| Tài khoản bị khóa vì chạm ngưỡng xác thực thất bại | Tính vào chỉ số khóa do thất bại xác thực |
| Một phương tiện xác thực bị vô hiệu hóa nhưng tài khoản còn cách đăng nhập khác | Ghi nhận riêng theo phạm vi authenticator; không mặc định là khóa toàn tài khoản |
| IP hoặc thiết bị bị giới hạn tốc độ | Theo dõi throttling riêng; chưa đủ để kết luận tài khoản bị khóa |
| Nhân viên nghỉ việc và tài khoản bị disable | Theo dõi sự kiện vòng đời danh tính riêng |
| Quản trị viên khóa tài khoản khi xử lý sự cố | Phân loại khóa hành chính hoặc khóa do ứng phó sự cố |
| Đăng nhập thất bại vì mật khẩu sai, tài khoản vẫn được thử tiếp | Tính vào thất bại xác thực, chưa tính là lockout |
| Ứng dụng trả lỗi nhưng không biết trạng thái tại IdP | Đánh dấu nguyên nhân chưa xác định; không tự suy thành lockout |

Đặc biệt trong SSO, ứng dụng phụ thuộc có thể chỉ nhận lỗi chung. Nguồn quan sát trạng thái khóa thường phải đến từ IdP hoặc directory có thẩm quyền, thay vì suy đoán từ HTTP 401 ở ứng dụng.

## 3. Chọn công thức và mẫu số

### 3.1. Tỷ lệ tài khoản bị khóa mới

Với cửa sổ thời gian `W`, xác định:

- `A(W)`: tập tài khoản đã xác định được danh tính, thuộc phạm vi chính sách đang đo và có ít nhất một lần thử xác thực trong `W`.
- `L(W)`: tập tài khoản thuộc `A(W)` có ít nhất một sự kiện bắt đầu khóa đúng loại cần đo trong `W`.

```text
Tỷ lệ tài khoản bị khóa mới (%) = |L(W)| / |A(W)| × 100
```

Mỗi tài khoản chỉ được tính một lần trong mỗi tập, bất kể có bao nhiêu lần đăng nhập hay đợt khóa. Nếu tài khoản chỉ bị khóa từ trước cửa sổ và không phát sinh đợt khóa mới, nó không thuộc `L(W)`. Nếu tài khoản đó có thử xác thực trong cửa sổ thì vẫn có thể thuộc `A(W)`, theo định nghĩa trên.

Phạm vi cần thống nhất giữa tử số và mẫu số: cùng tenant, môi trường, nhóm tài khoản, phương thức xác thực và loại chính sách. Chẳng hạn, khi đo khóa do thử mật khẩu của người dùng, không đưa các lượt làm mới token của workload vào mẫu số.

Tên người dùng không tồn tại không phải một tài khoản đã xác định. Cần theo dõi các lần thử đó bằng chỉ số riêng về danh tính không xác định hoặc dò tìm tài khoản. Đưa hàng triệu username giả vào mẫu số sẽ làm tỷ lệ khóa trông thấp hơn mà không phản ánh khả năng truy cập của người dùng thật.

Nếu `|A(W)| = 0`, tỷ lệ là không xác định và nên hiển thị `N/A`. Không biến trường hợp không có hoạt động hoặc mất dữ liệu thành một kết quả 0% có vẻ bình thường.

### 3.2. Các chỉ số bổ trợ

| Chỉ số | Công thức hoặc ý nghĩa | Câu hỏi trả lời |
|---|---|---|
| Tỷ lệ tài khoản bị khóa mới | Tài khoản bị khóa mới duy nhất / tài khoản có thử xác thực duy nhất | Phạm vi người dùng bị ảnh hưởng lớn đến đâu? |
| Số đợt khóa trên 1.000 lần thử xác thực | Số sự kiện bắt đầu khóa / số lần thử xác thực × 1.000 | Khóa xuất hiện dày đến đâu so với lưu lượng? |
| Tỷ lệ yêu cầu bị từ chối do đang khóa | Số lần thử bị từ chối vì khóa có hiệu lực / tổng số lần thử xác thực × 100 | Khóa đang cản trở bao nhiêu lưu lượng? |
| Số tài khoản đang khóa | Số tài khoản ở trạng thái khóa tại thời điểm quan sát | Hiện còn bao nhiêu tài khoản chịu ảnh hưởng? |
| Tỷ lệ tài khoản bị khóa lặp lại | Tài khoản có từ hai đợt khóa / tài khoản có ít nhất một đợt khóa trong cửa sổ | Có nhóm tài khoản chưa được xử lý nguyên nhân gốc không? |
| Thời gian bị khóa | Khoảng từ lúc khóa bắt đầu đến khi khóa được gỡ hoặc hết hạn | Người dùng bị cản trở trong bao lâu? |

Đối với thời gian bị khóa, các đợt chưa kết thúc phải được thể hiện riêng bằng số lượng và tuổi khóa hiện tại. Nếu chỉ tính trung vị hoặc percentile của các đợt đã mở khóa, dashboard có thể bỏ qua những tài khoản đang mắc kẹt lâu nhất.

### 3.3. Ví dụ tính toán

Trong một giờ, hệ thống ghi nhận các số liệu giả định sau, cùng thuộc nhóm tài khoản người dùng xác thực bằng mật khẩu:

| Đại lượng | Giá trị |
|---|---:|
| Tổng lần thử xác thực | 6.000 |
| Tài khoản có thử xác thực duy nhất | 1.000 |
| Sự kiện bắt đầu khóa đã khử trùng | 18 |
| Tài khoản bị khóa mới duy nhất | 12 |
| Lần thử bị từ chối vì tài khoản đang khóa | 240 |

Kết quả:

```text
Tỷ lệ tài khoản bị khóa mới = 12 / 1.000 × 100 = 1,2%
Số đợt khóa trên 1.000 lần thử = 18 / 6.000 × 1.000 = 3
Tỷ lệ yêu cầu bị từ chối do khóa = 240 / 6.000 × 100 = 4%
```

Không thể dùng 18 đợt khóa để kết luận 18 người dùng bị ảnh hưởng. Cũng không thể từ 240 lượt từ chối suy ra 240 tài khoản bị khóa. Sự khác biệt giữa số sự kiện, số yêu cầu và số tài khoản là phần cốt lõi của việc đọc chỉ số này.

Khi tổng hợp từ giờ lên ngày, phải tính lại tập tài khoản duy nhất cho cả ngày. Một tài khoản xuất hiện ở nhiều giờ vẫn chỉ là một tài khoản trong thống kê ngày. Không cộng số unique của các giờ hoặc lấy trung bình các phần trăm theo giờ để thay thế kết quả đó.

## 4. Thu thập dữ liệu đủ để giải thích biến động

### 4.1. Sự kiện minh họa

```json
{
  "event_id": "evt-demo-1842",
  "event_type": "account_lockout_started",
  "occurred_at": "2026-10-12T02:15:00Z",
  "tenant_id": "tenant-demo",
  "subject_key": "subject-pseudo-81",
  "account_type": "human",
  "auth_method": "password",
  "lock_scope": "account",
  "lockout_episode_id": "lock-demo-67",
  "reason": "failed_attempt_threshold",
  "policy_version": "password-policy-v7",
  "source_system": "primary-idp",
  "client_class": "legacy-mail-client",
  "environment": "production"
}
```

Đây là schema ví dụ, không phải tên field bắt buộc của một sản phẩm IAM. `subject_key` cần ổn định trong phạm vi cần đối chiếu nhưng không nhất thiết là email hay username có thể đọc trực tiếp. Khóa định danh nên được xét cùng `tenant_id` để tránh trộn hai tài khoản thuộc hai tenant.

Không ghi mật khẩu, OTP, access token, refresh token hoặc cookie phiên vào sự kiện. Các thông tin có thể nhận diện người dùng, IP và thiết bị cần được giới hạn truy cập, thời gian lưu và mục đích sử dụng. Định danh giả vẫn có thể liên kết hành vi, vì vậy không được xem là dữ liệu vô danh tuyệt đối.

### 4.2. Luồng tính toán

```text
Sự kiện từ IdP / directory và sự kiện thử xác thực
    → chuẩn hóa thời gian, loại sự kiện và phạm vi khóa
    → khử trùng các bản sao sự kiện
    → xác định tập tài khoản đủ điều kiện trong cửa sổ
    → đếm tài khoản duy nhất và số đợt khóa
    → xuất dashboard tổng hợp, giữ log chi tiết để điều tra
```

Cần dùng thời điểm sự kiện xảy ra để phân cửa sổ, đồng thời theo dõi độ trễ đến hệ thống thu thập. Một lô log cũ đến cùng lúc có thể tạo đỉnh giả nếu toàn bộ được gom theo thời điểm tiếp nhận. Dashboard nên thể hiện khi số liệu còn tạm tính do dữ liệu đến muộn.

Nếu có sự kiện khóa mà không tìm thấy tài khoản tương ứng trong tập thử xác thực của cùng cửa sổ, cần kiểm tra khác biệt nguồn log, ranh giới thời gian hoặc phạm vi định nghĩa. Không âm thầm bỏ qua chúng để tỷ lệ trông hợp lệ. Có thể báo riêng số sự kiện khóa ngoài cohort để phát hiện vấn đề chất lượng dữ liệu.

Các metric tổng hợp nên dùng chiều phân loại có số lượng giá trị được kiểm soát, như môi trường, phương thức xác thực, loại client hoặc phiên bản chính sách. Không đặt `subject_key`, email, IP hay `event_id` thành label cho từng time series. Việc đếm tài khoản duy nhất nên thực hiện ở tầng xử lý sự kiện hoặc kho phân tích, rồi xuất kết quả tổng hợp.

## 5. Thiết kế dashboard và cảnh báo

### 5.1. Các góc nhìn cần đặt cạnh nhau

Một dashboard hữu ích nên thể hiện tỷ lệ khóa mới cùng số tài khoản bị khóa, mẫu số, số đợt khóa và số tài khoản còn đang khóa. Bên cạnh đó, đặt tỷ lệ xác thực thất bại, xác thực thành công, yêu cầu bị từ chối vì khóa và mức độ đầy đủ của log.

Nên có khả năng phân tách theo IdP, môi trường, loại tài khoản, nhóm client, phương thức xác thực và phiên bản chính sách. Nếu hệ thống có nhiều tenant, việc hiển thị dữ liệu theo tenant phải theo đúng quyền của người xem; dashboard tổng không được trở thành kênh lộ hoạt động của tenant khác.

Không nên gộp người dùng, tài khoản quản trị và danh tính workload vào một đường duy nhất. Khóa một tài khoản quản trị khẩn cấp có ý nghĩa vận hành khác với một người dùng nhập sai mật khẩu; khóa một tài khoản dịch vụ dùng chung có thể làm gián đoạn nhiều tác vụ dù chỉ tăng số tài khoản bị ảnh hưởng thêm một đơn vị.

### 5.2. Kết hợp tỷ lệ với số lượng và thời gian

Không có một ngưỡng tỷ lệ đúng cho mọi hệ thống. Cần xây baseline theo lưu lượng, thời điểm trong ngày, nhóm người dùng và chính sách thực tế. Ví dụ dưới đây chỉ minh họa cấu trúc một điều kiện cảnh báo:

```text
Cửa sổ trượt: 15 phút
Điều kiện tỷ lệ: tài khoản bị khóa mới / tài khoản có thử xác thực > 2%
Điều kiện số lượng: có ít nhất 20 tài khoản bị khóa mới
Điều kiện duy trì: điều kiện trên tồn tại liên tục 10 phút
Điều kiện dữ liệu: nguồn sự kiện và mẫu số được xác nhận còn hoạt động
```

Ngưỡng số lượng hạn chế cảnh báo do một nhóm rất nhỏ: một tài khoản bị khóa trong hai tài khoản hoạt động tạo tỷ lệ 50%, nhưng mức độ ảnh hưởng khác với 500 tài khoản bị khóa trong 10.000 tài khoản. Đối với danh tính đặc quyền hoặc tài khoản quan trọng, cần có cảnh báo riêng phù hợp với tác động, không bắt buộc chờ ngưỡng 20 tài khoản của ví dụ.

Mất log là một tình trạng cần cảnh báo độc lập. Không nên để điều kiện chất lượng dữ liệu làm một dashboard im lặng hoặc hiển thị 0% khi thực tế không còn quan sát được hệ thống.

## 6. Đọc tín hiệu và xử lý nguyên nhân

| Mẫu quan sát | Giả thuyết cần kiểm tra | Bằng chứng tiếp theo |
|---|---|---|
| Nhiều tài khoản bị khóa gần nhau, nhiều thất bại liên tiếp | Đoán mật khẩu, credential stuffing hoặc lỗi client diện rộng | Phân bố nguồn, loại client, danh tính mục tiêu, mẫu thất bại và log chính sách |
| Một vài tài khoản có rất nhiều đợt khóa lặp lại | Credential cũ trong ứng dụng hoặc tác vụ định kỳ | Chu kỳ lỗi, thời điểm đổi mật khẩu, cấu hình ứng dụng và chủ sở hữu tài khoản |
| Khóa tăng ngay sau triển khai chính sách | Ngưỡng mới hoặc lỗi cấu hình làm tăng khóa | Phiên bản chính sách, thời điểm triển khai, nhóm bị ảnh hưởng |
| Tỷ lệ tăng nhưng số tài khoản bị khóa gần như không đổi | Mẫu số giảm, lưu lượng thay đổi hoặc thiếu log | Số tài khoản hoạt động tuyệt đối, độ đầy đủ của nguồn sự kiện |
| Tỷ lệ giảm nhưng thất bại xác thực vẫn cao | Chính sách thay đổi, log khóa bị thiếu hoặc tấn công tránh ngưỡng | Cấu hình khóa, pipeline log và phân bố thất bại theo tài khoản |

Các hàng trên là giả thuyết điều tra, không phải quy tắc kết luận tấn công. Một địa chỉ IP có thể đại diện nhiều người dùng qua NAT; một tác nhân tấn công cũng có thể dùng nhiều IP. Thông tin nguồn chỉ là một phần của bằng chứng.

Một trình tự xử lý thực tế:

1. Xác nhận chỉ số tăng thật: kiểm tra khử trùng, độ trễ log, mẫu số và thay đổi schema.
2. Xác định tác động: tài khoản mới bị khóa, tài khoản còn khóa, nhóm đặc quyền và dịch vụ phụ thuộc.
3. Đối chiếu các thay đổi gần nhất: chính sách khóa, password rotation, triển khai client hoặc thay đổi IdP.
4. Điều tra theo tài khoản và nguồn sự kiện trong công cụ có quyền truy cập phù hợp; liên hệ chủ sở hữu khi cần.
5. Áp dụng biện pháp theo nguyên nhân và quy trình đã phê duyệt: sửa credential cũ, xử lý client lỗi, hạn chế nguồn có bằng chứng lạm dụng hoặc khôi phục cấu hình sai.
6. Theo dõi sau xử lý: tỷ lệ khóa mới, số khóa lặp lại, thời gian khôi phục và khả năng đăng nhập của người dùng hợp lệ.

Không tự động mở khóa hàng loạt chỉ vì tỷ lệ vượt ngưỡng. Nếu nguyên nhân là tấn công còn diễn ra, thao tác đó có thể tạo lại cơ hội thử credential và làm tài khoản tiếp tục bị khóa. Ngược lại, hạ độ nhạy của chính sách chỉ để làm đẹp dashboard cũng không giải quyết nguyên nhân.

OWASP lưu ý cơ chế khóa có thể bị lợi dụng để gây từ chối dịch vụ cho người dùng và việc thiết kế cần cân bằng bảo vệ với khả năng sử dụng. Khi điều tra, cần xem cả tác động của chính cơ chế khóa, thay vì mặc định mọi đợt khóa đều là kết quả tốt. [OWASP Authentication Cheat Sheet — Account Lockout](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html#account-lockout).

Rate limiting và khóa toàn tài khoản cũng không phải cùng một cơ chế. Khi tham chiếu hướng dẫn xác thực, cần đọc đúng phạm vi: ví dụ NIST SP 800-63B-4 mô tả giới hạn các lần thử thất bại đối với một authenticator trên một tài khoản, không đưa ra công thức chung cho dashboard account lockout rate. Không suy một giới hạn thử xác thực thành ngưỡng phần trăm cảnh báo. [NIST SP 800-63B-4 — Rate Limiting](https://pages.nist.gov/800-63-4/sp800-63b.html#rate-limiting).

## 7. Tự kiểm tra cách hiểu

**Có 50 sự kiện khóa và 10.000 lần thử xác thực. Tỷ lệ người dùng bị khóa có phải 0,5% không?**

Chưa đủ dữ liệu. Phép chia đó so sánh số sự kiện với số lần thử, không phải số tài khoản duy nhất với số tài khoản hoạt động duy nhất. Muốn biết tỷ lệ tài khoản bị ảnh hưởng phải xác định hai tập tài khoản tương ứng.

**Một tài khoản bị khóa từ hôm qua, hôm nay gửi 100 yêu cầu và tất cả đều bị từ chối. Hôm nay có 100 đợt khóa mới không?**

Không. Đây là 100 lượt từ chối do khóa đang có hiệu lực. Nếu không có chuyển trạng thái sang khóa mới trong hôm nay, tài khoản không nằm trong tử số khóa mới của ngày hôm nay; nó vẫn xuất hiện trong thống kê tài khoản đang khóa và có thể trong mẫu số tài khoản có thử xác thực.

**Tỷ lệ khóa mới bằng 0% có chứng minh hệ thống không bị tấn công không?**

Không. Tác nhân có thể thử ít lần trên mỗi tài khoản, dùng credential đúng hoặc tấn công qua đường khác. Trước khi diễn giải 0%, cũng cần xác nhận mẫu số có hoạt động và nguồn log khóa đầy đủ.

**Điều gì khiến account lockout rate trở thành một chỉ số có thể hành động?**

Một định nghĩa nhất quán về phạm vi khóa, sự kiện bắt đầu khóa và mẫu số; dữ liệu được khử trùng; khả năng phân tách nhóm bị ảnh hưởng; cùng quy trình đối chiếu tấn công, lỗi ứng dụng và thay đổi chính sách. Khi các yếu tố đó rõ ràng, chỉ số giúp đội IAM bảo vệ tài khoản đồng thời khôi phục quyền truy cập hợp lệ có căn cứ.
