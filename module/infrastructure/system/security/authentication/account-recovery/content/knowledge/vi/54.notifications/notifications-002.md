# Recovery completion notification

## 1. Thông báo hoàn tất có vai trò gì?

Thông báo hoàn tất khôi phục tài khoản cho chủ tài khoản biết một thay đổi nhạy cảm đã xảy ra. Người thực hiện hợp lệ có thể xác nhận kết quả; người không thực hiện có cơ hội nhận ra dấu hiệu chiếm đoạt và yêu cầu hỗ trợ.

Trong một hệ thống hỗ trợ khôi phục mật khẩu, MFA, passkey hoặc thiết bị xác thực, thông báo phải nói rõ điều gì đã được khôi phục. “Đã đặt lại mật khẩu” khác với “đã thay thiết bị MFA”, và cả hai đều không mặc nhiên có nghĩa mọi phiên truy cập cũ đã bị thu hồi.

Cần phân biệt ba thông điệp:

| Thông điệp | Sự kiện được xác nhận |
| --- | --- |
| Đã nhận yêu cầu khôi phục | Hệ thống tiếp nhận một yêu cầu, chưa khẳng định người gửi là chủ tài khoản |
| Đang chờ xác minh hoặc chờ hết thời gian trì hoãn | Quy trình còn điều kiện phải hoàn thành |
| Khôi phục đã hoàn tất | Những thay đổi bắt buộc của chính thao tác đó đã được ghi nhận có hiệu lực theo hợp đồng nghiệp vụ |

Một liên kết khôi phục được gửi thành công chưa phải bằng chứng quá trình khôi phục đã hoàn tất. Người dùng mở email, nhập đúng một OTP hoặc vượt qua một bước xác minh cũng chưa đủ nếu vẫn còn bước bắt buộc.

[OWASP Forgot Password Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html#user-resets-password) khuyến nghị gửi email sau khi mật khẩu được đặt lại và không gửi mật khẩu trong email. Bài này mở rộng thiết kế thông báo cho các dạng khôi phục khác trong cùng module; các mô hình trạng thái và ví dụ bên dưới là đề xuất thiết kế, không phải schema bắt buộc của OWASP hay NIST.

## 2. Chọn đúng thời điểm phát sự kiện hoàn tất

Bất biến cần bảo vệ là:

> Thông báo hoàn tất phải dựa trên kết quả nghiệp vụ đã được ghi nhận, không dựa trên dự định thực hiện hoặc một phản hồi tạm thời.

Ví dụ, một thao tác thay MFA sau khi mất điện thoại có thể yêu cầu: xác minh đủ bằng chứng, ràng buộc phương thức mới, vô hiệu hóa phương thức bị mất, tiêu thụ quyền khôi phục dùng một lần và áp dụng chính sách session. Chỉ phát sự kiện hoàn tất khi các điều kiện được định nghĩa cho thao tác đó đã đạt.

Không bắt buộc mọi sản phẩm có cùng danh sách điều kiện. Điều bắt buộc về mặt thiết kế là trạng thái cuối, thông báo và hành vi thực tế phải thống nhất.

Nếu credential và session nằm ở hai hệ thống khác nhau, cần xác định ranh giới rõ ràng:

- Nếu thu hồi session là điều kiện hoàn tất, quy trình còn chờ khi hệ thống session chưa xác nhận điều kiện đó.
- Nếu sản phẩm cho phép hoàn tất thay credential trước và theo dõi thu hồi riêng, thông báo phải mô tả chính xác phần đã xong và phần đang xử lý.
- Không viết “mọi thiết bị đã đăng xuất” chỉ vì một lệnh thu hồi đã được đưa vào hàng đợi.
- Không gọi MFA hoặc passkey “đã được khôi phục” nếu mới hoàn tất xác minh danh tính mà chưa ràng buộc phương thức sử dụng được.

Một thao tác bị rollback không được để lại thông báo hoàn tất. Một thao tác đã commit nhưng client mất kết nối vẫn có thể đã hoàn tất; việc gửi lại request cần đối chiếu kết quả đã lưu thay vì tạo thêm một sự kiện thành công cho cùng lần thay đổi.

## 3. Gửi đến kênh nào để chủ tài khoản có thể nhận biết?

Nếu kẻ tấn công thay email rồi hệ thống chỉ báo cho email vừa thay, thông báo có thể chỉ đến tay kẻ tấn công. Việc chọn người nhận vì thế là một quyết định bảo mật.

Kênh thông báo nên được lấy từ dữ liệu tài khoản có thẩm quyền theo chính sách đã xác định. Không lấy địa chỉ nhận trực tiếp từ tham số của request hoàn tất.

Một chính sách có thể xem xét:

| Kênh hoặc địa chỉ | Điều cần quyết định |
| --- | --- |
| Email thông báo đã được xác nhận trước sự kiện | Có còn phù hợp để gửi cảnh báo và có bị đánh dấu mất quyền kiểm soát không? |
| Kênh phụ độc lập đã đăng ký | Có thể tăng khả năng chủ tài khoản nhận ra sự kiện khi kênh chính bị mất không? |
| Email hoặc số điện thoại mới trong quy trình | Đã được xác minh, được phép nhận loại thông báo nào và có cần cảnh báo riêng cho thay đổi liên hệ không? |
| Push đến thiết bị từng được tin cậy | Thiết bị có thể chính là thiết bị bị mất; nội dung nào được phép hiện trên màn hình khóa? |
| Thông báo trong ứng dụng | Có ích sau khi đăng nhập nhưng không đủ để tiếp cận người đang mất toàn bộ khả năng đăng nhập |

Không tự động khôi phục một địa chỉ cũ hoặc tái cấp quyền cho phương thức cũ chỉ để gửi cảnh báo. Một địa chỉ lịch sử có thể đã bị bỏ vì mất quyền kiểm soát; lịch sử tồn tại không đồng nghĩa hiện tại còn an toàn.

[NIST SP 800-63B-4, mục 4.6](https://pages.nist.gov/800-63-4/sp800-63b/events/#notification) mô tả việc thông báo độc lập cho các sự kiện như khôi phục tài khoản. Trong phạm vi tiêu chuẩn này, hệ thống phải hỗ trợ ít nhất hai địa chỉ thông báo và gửi tới các địa chỉ đã lưu, với quy định riêng cho địa chỉ bưu chính. Thông báo phải hướng dẫn rõ cách liên hệ khi người nhận phủ nhận sự kiện. Sản phẩm áp dụng NIST cần đọc đầy đủ các điều kiện này; không thể suy ra đáp ứng tiêu chuẩn chỉ từ việc gửi một email.

Đối với thiết kế minh họa trong bài, danh sách người nhận được quyết định cùng sự kiện hoàn tất và lưu dưới dạng tham chiếu có phiên bản, được bảo vệ. Nếu đến lúc gửi phát hiện kênh đã bị đánh dấu không an toàn, xử lý theo chính sách thay vì âm thầm đổi sang một địa chỉ vừa được bổ sung.

## 4. Nội dung đủ để nhận biết, ít dữ liệu nhạy cảm

Người nhận cần hiểu sự kiện và biết bước tiếp theo. Họ không cần nhận toàn bộ hồ sơ khôi phục.

Một thông báo thường cần các thông tin sau:

| Thành phần | Ví dụ và giới hạn |
| --- | --- |
| Tên dịch vụ | Giúp người nhận nhận diện tài khoản liên quan |
| Tài khoản được che bớt | Dùng biệt danh hoặc định danh che bớt; cân nhắc riêng tư trên từng kênh |
| Thay đổi đã hoàn tất | “Đã đặt lại mật khẩu” hoặc “Đã thay phương thức MFA” |
| Thời điểm sự kiện | Ghi ngày, giờ và múi giờ rõ ràng; phân biệt với thời điểm email đến |
| Tác động đến quyền truy cập | Chỉ nêu việc thu hồi hoặc hạn chế thực sự đã có hiệu lực |
| Hành động nếu không thực hiện | Chỉ dẫn truy cập ứng dụng hoặc kênh hỗ trợ chính thức |
| Mã tham chiếu hỗ trợ | Không mang quyền đăng nhập và không tự cấp quyền xem dữ liệu |

Không đưa vào thông báo hoàn tất:

- Mật khẩu mới, OTP, mã khôi phục dự phòng hoặc seed của ứng dụng MFA.
- Token đặt lại mật khẩu, token của phiên khôi phục hoặc liên kết đăng nhập tự động.
- Private key của passkey hoặc dữ liệu bí mật của thiết bị xác thực.
- Ảnh giấy tờ, câu trả lời xác minh hoặc mô tả chi tiết bằng chứng danh tính.
- Cookie, authorization header hoặc nội dung request dùng để khôi phục.

Vị trí gần đúng hoặc mô tả thiết bị chỉ nên xuất hiện khi có dữ liệu đủ tin cậy và có ích. IP không chứng minh ai đã thực hiện; định vị IP có thể sai vì VPN hoặc mạng di động. Không biến suy đoán vị trí thành một khẳng định chắc chắn.

SMS và push có không gian hạn chế và dễ hiện trên màn hình khóa. Có thể dùng thông điệp ngắn, hướng người nhận mở ứng dụng chính thức để xem chi tiết sau khi được xác thực phù hợp.

## 5. Mẫu thông báo hoàn tất

Ví dụ dưới đây dành cho thao tác đặt lại mật khẩu đã hoàn tất; thông tin thời gian và mã tham chiếu chỉ mang tính minh họa.

```text
Tiêu đề: Mật khẩu tài khoản của bạn đã được đặt lại

Mật khẩu của tài khoản có định danh p*** đã được đặt lại
lúc 14:20 ngày 24/11/2026, múi giờ UTC+07:00.

Nếu bạn thực hiện thao tác này:
Hãy đăng nhập qua ứng dụng hoặc trang web chính thức bằng mật khẩu mới.
Bạn có thể xem lại các phương thức xác thực trong mục Bảo mật.

Nếu bạn không thực hiện thao tác này:
Hãy mở ứng dụng hoặc tự truy cập trang web chính thức,
chọn Trợ giúp > Bảo mật tài khoản và báo cáo sự kiện.
Nếu không thể đăng nhập, sử dụng kênh hỗ trợ công khai
được công bố trên trang web chính thức.

Mã tham chiếu hỗ trợ: REC-EXAMPLE-2048

Chúng tôi không yêu cầu bạn trả lời thư bằng mật khẩu,
OTP hoặc mã khôi phục.
```

Mẫu không nói “bỏ qua nếu không phải bạn”. Người không thực hiện chính là người cần có chỉ dẫn ứng phó rõ nhất.

Với thay MFA hoặc passkey, thay mô tả sự kiện bằng đúng phương thức đã được thay đổi. Chỉ bổ sung câu “các phiên cũ đã bị thu hồi” nếu hệ thống có căn cứ xác nhận điều đó theo phạm vi đã nêu.

Thông báo không nên tự đăng nhập người nhận. OWASP cũng khuyến nghị người dùng đăng nhập qua cơ chế thông thường sau khi đặt lại mật khẩu, thay vì tự tạo phiên đăng nhập từ bước khôi phục. [OWASP Forgot Password Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html#user-resets-password)

## 6. Liên kết báo cáo không được trở thành đường khôi phục thứ hai

Một nút “Tôi không thực hiện” có thể giúp người dùng phản ứng nhanh, nhưng cần xác định nó được phép làm gì.

Nhận được thông báo không tự chứng minh người đọc là chủ tài khoản. Email có thể được chuyển tiếp, số điện thoại có thể thuộc người khác và phần mềm quét liên kết có thể truy cập URL trước người nhận.

Một thiết kế thận trọng có thể dùng liên kết chỉ mở trang hướng dẫn hoặc trang tiếp nhận báo cáo. Máy chủ vẫn phải kiểm tra quyền phù hợp trước các thao tác nhạy cảm.

Các giới hạn quan trọng:

1. Không dùng yêu cầu GET để trực tiếp đổi credential, khôi phục phương thức cũ hoặc vô hiệu hóa toàn tài khoản.
2. Không cho phép một mã tham chiếu công khai thay thế xác minh danh tính.
3. Không hoàn tác credential mới bằng cách khôi phục credential có thể đã bị lộ.
4. Không biến một liên kết thông báo có thể chuyển tiếp thành phiên có đầy đủ quyền.
5. Bảo vệ thao tác ghi khỏi CSRF, giới hạn lạm dụng và yêu cầu xác nhận phù hợp với mức tác động.

Có thể cần tiếp nhận báo cáo ngay cả khi chủ tài khoản không đăng nhập được. Luồng tiếp nhận đó chỉ ghi nhận nghi vấn và kích hoạt xử lý theo rủi ro; nó không tự cấp quyền kiểm soát tài khoản.

Nếu chính sách cho phép hạn chế tạm thời khi nhận báo cáo, phải đánh giá nguy cơ kẻ khác sử dụng chức năng này để gây từ chối dịch vụ. Mức hạn chế, điều kiện xác minh, thời hạn và cách hỗ trợ cần được xác định trước.

Đường dẫn trong thông báo phải được tạo từ cấu hình miền được tin cậy, không từ URL tùy ý do người gọi cung cấp. Không đặt bí mật trong tham số chỉ để liên kết “tiện lợi hơn”.

## 7. Gắn thông báo với kết quả bằng outbox

Không nên gửi email thành công trước khi transaction thay đổi tài khoản commit. Nếu transaction rollback, email đã gửi không thể được thu hồi như một bản ghi SQL.

Ngược lại, chỉ gọi dịch vụ email sau commit mà không lưu ý định gửi có thể làm mất thông báo nếu tiến trình dừng giữa hai bước.

[Transactional outbox của AWS](https://docs.aws.amazon.com/prescriptive-guidance/latest/cloud-design-patterns/transactional-outbox.html) giải quyết khoảng trống ghi dữ liệu và phát sự kiện bằng cách lưu sự kiện cùng transaction với thay đổi nghiệp vụ, rồi chuyển tiếp sau commit. Cơ chế chuyển tiếp có thể lặp, nên bên xử lý phải quản lý trùng lặp.

Áp dụng vào bài này:

```text
Trong đơn vị ghi hoàn tất:
  xác nhận điều kiện khôi phục đã đạt
  ghi các thay đổi bảo mật thuộc cùng phạm vi transaction
  chuyển request sang trạng thái cuối phù hợp
  ghi sự kiện RecoveryCompleted và ý định thông báo
COMMIT

Sau commit:
  bộ chuyển tiếp đọc sự kiện đã commit
  bộ gửi nhận danh sách đích theo chính sách
  tạo thông điệp tối thiểu và gửi
  theo dõi kết quả riêng cho từng đích và từng kênh
```

Sự kiện minh họa:

```yaml
eventId: evt_example_7d2
eventType: RecoveryCompleted
accountRef: acct_example_41
recoveryRequestRef: rr_example_89
completedAt: "2026-11-24T07:20:00Z"
changeKind: MFA_REPLACED
securityRevision: 12
recipientPlanRef: rp_example_22_v1
templateVersion: recovery-completed-vi-3
```

Các định danh chỉ là ví dụ. Payload không mang token, OTP, mật khẩu hoặc bằng chứng danh tính. Tham chiếu người nhận cần phân quyền truy cập; nếu lưu địa chỉ trực tiếp thì phải bảo vệ dữ liệu đó và có thời hạn lưu phù hợp.

Không có trường nào trong sự kiện tự chứng minh việc thu hồi session đã có hiệu lực ở hệ thống khác. Nếu thông báo cần nêu kết quả đó, phải lấy từ dữ liệu có thẩm quyền tương ứng.

## 8. Theo dõi gửi, retry và trùng lặp

Kết quả khôi phục và kết quả chuyển thông báo là hai chiều trạng thái khác nhau.

| Trạng thái thông báo minh họa | Ý nghĩa |
| --- | --- |
| PENDING | Ý định gửi đã được ghi nhưng chưa được xử lý |
| PROVIDER_ACCEPTED | Nhà cung cấp đã nhận yêu cầu, chưa chứng minh người dùng đã nhận |
| DELIVERED | Có tín hiệu chuyển phát theo định nghĩa của kênh |
| RETRY_SCHEDULED | Lỗi tạm thời đang được thử lại có giới hạn |
| FAILED_PERMANENT | Lỗi không thể tiếp tục xử lý tự động theo chính sách |
| UNKNOWN | Chưa xác định được kết quả lần gửi trước |

Ngay cả DELIVERED cũng không chứng minh chủ tài khoản đã đọc hoặc đồng ý. Tracking pixel, lượt mở thư và lượt truy cập liên kết đều không phải bằng chứng xác thực.

Khóa chống lặp có thể bao gồm `eventId + recipientRef + channel + templatePurpose`. Khóa chỉ theo tài khoản có thể vô tình nuốt mất thông báo của một sự kiện hoàn tất mới.

Nếu dịch vụ gửi đã nhận yêu cầu nhưng bộ gửi mất phản hồi, việc gửi lại có thể tạo bản sao. Dùng idempotency key của nhà cung cấp khi được hỗ trợ và quản lý trạng thái nội bộ; không mặc định tuyên bố email được gửi đúng một lần.

Retry cần phân biệt lỗi tạm thời, lỗi địa chỉ và lỗi chính sách. Áp dụng backoff có jitter, giới hạn thử lại và cảnh báo khi tồn đọng vượt ngân sách vận hành. Các ngưỡng là cấu hình của sản phẩm, không phải con số phổ quát.

Khi một đích thất bại, không đánh dấu cả nhóm là đã gửi. Có thể sử dụng kênh thay thế đã được phép hoặc chuyển xử lý vận hành; không gửi sang địa chỉ tùy ý do người gọi cung cấp để “cứu” thông báo.

Nếu thông báo đến muộn, vẫn giữ thời điểm sự kiện gốc và cho phép đối chiếu trạng thái mới nhất qua kênh chính thức. Đừng thay thời gian hoàn tất bằng thời gian retry hoặc ngụ ý trạng thái tài khoản hiện tại vẫn giống thời điểm sự kiện.

## 9. Chống lạm dụng và bảo vệ dấu vết vận hành

Một đối tượng có thể tạo nhiều yêu cầu khôi phục để gây mệt mỏi cảnh báo. Thông báo bắt đầu và thông báo hoàn tất nên có loại sự kiện và ngân sách xử lý riêng, để lưu lượng yêu cầu chưa xác minh không làm biến mất cảnh báo về thay đổi thực sự đã xảy ra.

Các biện pháp có thể phối hợp gồm:

- Chỉ sinh sự kiện hoàn tất từ chuyển trạng thái hợp lệ tại máy chủ.
- Chống xử lý lặp cùng sự kiện nhưng vẫn phân biệt những lần hoàn tất khác nhau.
- Giới hạn yêu cầu gửi lại từ giao diện; không cho một request tùy ý gửi thư tới nhiều người.
- Theo dõi độ trễ từ `completedAt` đến lần gửi đầu, tuổi sự kiện tồn đọng và tỷ lệ lỗi theo kênh.
- Cảnh báo nội bộ khi kênh thông báo bị lỗi kéo dài.
- Xác minh nguồn và tính toàn vẹn callback của nhà cung cấp, xử lý callback lặp và hạn chế quyền cập nhật.
- Giới hạn quyền đọc nội dung thông báo và dữ liệu liên hệ; không ghi bí mật khôi phục vào log.

Nếu dùng callback chuyển phát, cập nhật theo định nghĩa trạng thái của kênh và thứ tự sự kiện có thể kiểm chứng. Một callback cũ đến muộn không nên ghi đè tùy tiện kết quả mới hơn.

Lỗi gửi thông báo không phải lý do tự động làm token đã tiêu thụ hợp lệ trở lại hoặc khôi phục phương thức xác thực bị mất. Khôi phục nghiệp vụ đã commit cần được giữ nhất quán; vấn đề chuyển phát được retry, đối chiếu và xử lý theo chính sách.

## 10. Tình huống áp dụng

### Mất điện thoại, thay MFA thành công

Lan mất thiết bị MFA và hoàn tất quy trình xác minh theo chính sách. Hệ thống ràng buộc phương thức mới, xử lý phương thức bị mất, tiêu thụ quyền khôi phục và đạt các điều kiện hoàn tất.

Một sự kiện được ghi cùng kết quả. Thông báo được lập cho các kênh đã được phép theo chính sách của tài khoản. Nội dung nêu việc thay MFA, thời điểm thực hiện và đường liên hệ nếu Lan phủ nhận. Nó không chứa secret MFA hay mã dự phòng mới.

### Người thực hiện cũng thay email

Không mặc định gửi duy nhất đến email mới. Chính sách phải quyết định các đích cảnh báo độc lập, xét độ tin cậy và trạng thái của từng địa chỉ. Việc xác minh email mới và việc thông báo hoàn tất khôi phục là hai mục đích riêng.

### Nhà cung cấp email gặp sự cố

Kết quả khôi phục và ý định thông báo đã được lưu. Bộ gửi ghi nhận lỗi tạm thời, lên lịch retry và theo dõi kênh phụ nếu chính sách cho phép. Giao diện có thể xác nhận phần khôi phục đã hoàn tất mà không tuyên bố email đã tới người dùng.

### Người nhận phủ nhận sự kiện

Người nhận tự mở ứng dụng hoặc trang hỗ trợ chính thức và cung cấp mã tham chiếu. Hệ thống tiếp nhận báo cáo, áp dụng quy trình bảo vệ tài khoản theo rủi ro và yêu cầu bằng chứng phù hợp trước khi cấp lại quyền. Việc phủ nhận không tự động hoàn tác mọi thay đổi.

Một thông báo hoàn tất hữu ích nối kết ba việc: phản ánh đúng thay đổi đã xảy ra, tiếp cận chủ tài khoản qua kênh phù hợp và cung cấp cách ứng phó an toàn khi sự kiện không được họ thực hiện.