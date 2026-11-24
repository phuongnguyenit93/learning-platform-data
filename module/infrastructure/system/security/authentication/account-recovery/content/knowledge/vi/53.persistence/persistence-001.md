# Transactional recovery writes

## 1. Vì sao các thao tác ghi khôi phục cần transaction?

Một thao tác khôi phục tài khoản thường thay đổi nhiều bản ghi: tiêu thụ token, lưu mật khẩu mới, thu hồi phương thức cũ, cập nhật request và ghi sự kiện bảo mật. Nếu mỗi bước được commit riêng, lỗi giữa chừng có thể để lại trạng thái nguy hiểm.

Ví dụ, hệ thống đã lưu mật khẩu mới nhưng chưa đánh dấu token đã dùng. Một yêu cầu khác vẫn có thể sử dụng token đó để thay đổi tài khoản lần nữa. Theo chiều ngược lại, token đã bị tiêu thụ nhưng mật khẩu chưa được cập nhật khiến người dùng mất khả năng hoàn tất bằng chính liên kết vừa dùng.

[Tài liệu PostgreSQL về transaction](https://www.postgresql.org/docs/current/tutorial-transactions.html) mô tả việc gom nhiều thao tác thành một đơn vị nguyên tử: các thay đổi được commit cùng nhau hoặc bị rollback. Trong luồng khôi phục, cần chọn đúng tập thay đổi phải có tính chất này.

Transaction bảo vệ tính nhất quán trong phạm vi dữ liệu mà nó quản lý. Nó không tự xác minh danh tính, không tự tạo chính sách khôi phục và không làm một lời gọi email bên ngoài trở thành thao tác có thể rollback.

## 2. Xác định đơn vị nghiệp vụ trước khi chọn lệnh ghi

Không phải toàn bộ hành trình kéo dài nhiều phút đều nằm trong một transaction. Mỗi bước chuyển trạng thái có thể là một đơn vị ghi riêng, với điều kiện và kết quả rõ ràng.

| Đơn vị nghiệp vụ | Các thay đổi có thể cần ghi cùng nhau |
| --- | --- |
| Tạo challenge | Request hoặc bước liên quan, verifier của challenge, hạn dùng và ý định gửi thông báo |
| Chấp nhận mã dự phòng | Trạng thái dùng một lần của mã nguồn, evidence đã xác minh và sự kiện tương ứng |
| Đặt lại mật khẩu | Token dành cho thao tác, mật khẩu mới, trạng thái request và dữ liệu vô hiệu hóa truy cập theo chính sách |
| Thay phương thức MFA hoặc passkey | Liên kết phương thức mới, xử lý phương thức bị mất, trạng thái bước và sự kiện |
| Hoàn tất khôi phục | Những điều kiện bắt buộc đã đạt, trạng thái cuối và các tác động bảo mật thuộc cùng phạm vi lưu trữ |

Danh sách cụ thể phụ thuộc mô hình sản phẩm. Điều quan trọng là viết rõ bất biến, chẳng hạn:

> Khi thao tác đặt lại mật khẩu được ghi nhận hoàn tất, mật khẩu mới đã được lưu và token cho thao tác đó không còn dùng được để thực hiện một thay đổi mới.

Đừng trộn token hoàn tất thao tác với mã dự phòng đã được tiêu thụ ở một bước xác minh trước đó. Chúng có thể có ranh giới dùng một lần khác nhau và phải được mô tả riêng.

## 3. Chuẩn bị ngoài transaction, quyết định trong transaction

Một thiết kế thực tế thường chia công việc thành ba phần:

1. Chuẩn bị dữ liệu và những phép tính không cần giữ khóa.
2. Trong transaction ngắn, đọc lại trạng thái có thẩm quyền, kiểm tra điều kiện và áp dụng thay đổi.
3. Sau commit, trả kết quả và xử lý các tác dụng phụ qua cơ chế đáng tin cậy.

Có thể kiểm tra định dạng và tính hash mật khẩu mới trước khi giữ khóa cơ sở dữ liệu. Tuy nhiên, kết quả đọc token, tài khoản hoặc chính sách trước đó không được coi là vẫn đúng tại lúc ghi.

Trong transaction, cần kiểm tra lại những điều kiện có thể thay đổi:

- Request còn hoạt động và thuộc đúng tài khoản, tenant, mục đích.
- Token hoặc evidence còn hiệu lực, chưa bị tiêu thụ hoặc thu hồi ngoài phạm vi được phép.
- Phiên khôi phục còn quyền thực hiện đúng hành động.
- Phiên bản bảo mật của tài khoản và điều kiện chính sách vẫn phù hợp.
- Những điều kiện bổ sung bắt buộc đã được đáp ứng.

Thời gian dùng để quyết định hạn dùng phải đến từ nguồn có thẩm quyền. Nếu đã phải chờ khóa, không dùng một thời điểm client gửi lên hoặc một giá trị cũ được lấy từ trước khi chờ. Cần định nghĩa rõ hạn dùng được xét tại lúc chấp nhận thao tác và giữ bước ghi đủ ngắn.

Không mở transaction rồi chờ người dùng nhập OTP, phê duyệt thủ công hoặc chờ nhà cung cấp xác minh từ xa. Các công việc đó cần được ràng buộc với request qua dữ liệu và bước chuyển trạng thái phù hợp.

## 4. Ví dụ transaction đặt lại mật khẩu

Giả sử request R đang ở bước được phép đặt lại mật khẩu, token T được cấp riêng cho mục đích này và dữ liệu liên quan nằm trong cùng cơ sở dữ liệu.

Trình tự sau là mã giả nghiệp vụ, không phải một hàm triển khai hoàn chỉnh:

```text
passwordHash = chuẩn_bị_hash_mật_khẩu_mới()

BEGIN
  Khóa tài khoản, request và token theo thứ tự thống nhất
  Đọc lại trạng thái hiện tại của các bản ghi
  Kiểm tra tài khoản, tenant, mục đích và quyền của phiên khôi phục
  Kiểm tra token, hạn dùng và phiên bản bảo mật dự kiến
  Kiểm tra các điều kiện chính sách còn lại

  Tiêu thụ token bằng thao tác có điều kiện
  Yêu cầu đúng một token được chuyển trạng thái

  Lưu passwordHash theo điều kiện cập nhật phù hợp
  Áp dụng thay đổi vô hiệu hóa truy cập theo chính sách
  Chuyển request sang trạng thái hoàn tất tương ứng
  Ghi sự kiện bảo mật và bản ghi outbox cần thiết
COMMIT

Trả kết quả đã được xác nhận
```

[OWASP Forgot Password Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html) nêu yêu cầu token khôi phục được lưu an toàn, có hạn dùng và bị vô hiệu hóa sau sử dụng. Ranh giới transaction cần bảo đảm những thuộc tính đó vẫn đúng khi có nhiều request hoặc lỗi giữa chừng.

Một thao tác tiêu thụ token minh họa theo PostgreSQL:

```sql
UPDATE recovery_token
SET consumed_at = :decision_time
WHERE id = :token_id
  AND recovery_request_id = :request_id
  AND account_id = :account_id
  AND purpose = 'PASSWORD_RESET'
  AND consumed_at IS NULL
  AND revoked_at IS NULL
  AND expires_at > :decision_time
RETURNING id;
```

Các tên bắt đầu bằng dấu hai chấm là tham số bind của lớp truy cập dữ liệu. `decision_time` được lấy từ nguồn thời gian máy chủ phù hợp sau bước khóa; các định danh đích được xác định và đối chiếu theo ngữ cảnh có thẩm quyền.

Câu SQL này chỉ minh họa một phần transaction. Máy chủ vẫn phải kiểm tra giá trị token qua verifier được bảo vệ, quyền thao tác, phạm vi tenant nếu có và các điều kiện nghiệp vụ khác.

Nếu không có hàng trả về, không được tiếp tục lưu mật khẩu rồi commit như bình thường. Một câu UPDATE tác động không hàng có thể không tạo lỗi SQL; ứng dụng phải xử lý rõ kết quả đó. Với các bản ghi nghiệp vụ khác cũng vậy: số hàng thay đổi ngoài dự kiến phải dẫn đến hành vi đã được định nghĩa, thường là rollback toàn đơn vị ghi.

## 5. Transaction không thay thế kiểm soát cạnh tranh

Hai transaction đều có thể đọc trạng thái token chưa dùng trước khi một bên ghi. Chỉ thêm `BEGIN` và `COMMIT` quanh chuỗi đọc rồi ghi chưa đủ để loại bỏ mọi race condition.

[Tài liệu PostgreSQL về isolation](https://www.postgresql.org/docs/current/transaction-iso.html) giải thích rằng Read Committed cho mỗi câu lệnh một snapshot phù hợp với thời điểm bắt đầu câu lệnh; các lần đọc liên tiếp trong một transaction vẫn có thể thấy dữ liệu khác nhau. Cách chọn isolation và cơ chế ghi cần khớp với bất biến đang bảo vệ.

Một số cơ chế có thể dùng:

| Cơ chế | Vai trò | Điều cần chú ý |
| --- | --- | --- |
| Cập nhật có điều kiện | Chỉ chuyển trạng thái nếu điều kiện còn đúng | Phải kiểm tra kết quả ghi |
| Khóa hàng | Tuần tự hóa những writer cùng tác động dữ liệu | Mọi đường ghi liên quan cần tuân thủ giao thức |
| Optimistic locking | Phát hiện bản ghi đã đổi qua version | Phải có điều kiện version và xử lý xung đột |
| Unique constraint | Ngăn một số dạng trùng lặp được mô hình hóa | Không thay thế việc xác minh hoặc kiểm tra hạn |
| Serializable | Phát hiện những thực thi không phù hợp với tuần tự hóa | Có thể cần retry toàn transaction khi bị từ chối |

Nếu hai request khác nhau dùng cùng mã nguồn, khóa riêng hai hàng request không ngăn được dùng lại mã. Cần bảo vệ trạng thái dùng một lần ở nguồn chung.

Nếu hai token khác nhau đều có quyền thay đổi cùng tài khoản, chính sách cũng cần xác định điều gì xảy ra sau lần thay đổi đầu tiên. Có thể dùng phiên bản bảo mật của tài khoản hoặc vô hiệu hóa phạm vi request/token liên quan để ngăn một luồng cũ ghi đè thay đổi mới.

Thứ tự khóa nên nhất quán giữa các đường xử lý. Không giữ transaction dài chỉ để “chắc chắn hơn”, vì thời gian giữ khóa dài có thể làm tăng chờ đợi và deadlock.

## 6. Rollback đúng, kể cả đối với kết quả từ chối

Khi lưu mật khẩu mới thất bại, việc tiêu thụ token trong cùng đơn vị ghi cần được rollback theo thiết kế. Khi cập nhật request thất bại, không nên để credential đã đổi nhưng request vẫn biểu diễn chưa hoàn thành.

Tuy nhiên, một kết quả xác minh bị từ chối là tình huống nghiệp vụ cần xử lý riêng với lỗi hạ tầng. Ví dụ, mã sai có thể cần làm tăng bộ đếm thử và ghi sự kiện thất bại.

Nếu ứng dụng tăng bộ đếm rồi ném lỗi khiến toàn transaction rollback, dấu vết lần thử có thể biến mất. Từ đó người gửi có thể thử nhiều lần mà bộ đếm không phản ánh đúng.

Một thiết kế có thể:

- Trong nhánh từ chối xác minh, ghi bộ đếm và sự kiện cần thiết rồi commit kết quả từ chối, không thay đổi credential.
- Trong nhánh thành công, thực hiện trọn đơn vị ghi nhạy cảm.
- Khi có lỗi hạ tầng, rollback đơn vị đang xử lý và trả kết quả phù hợp với điều đã biết.
- Quản lý ngân sách yêu cầu hoặc kiểm soát chống lạm dụng ở phạm vi phù hợp, thay vì dựa hoàn toàn vào một transaction thành công.

Cần xác định rõ bộ đếm nào đo yêu cầu gửi đến, bộ đếm nào đo lần xác minh thực sự và tác động của rollback đến chúng. Không giải quyết bằng cách commit riêng trạng thái cấp quyền trước rồi hy vọng những bước sau sẽ thành công.

Tương tự, sự kiện “khôi phục thành công” phải gắn với thay đổi đã commit. Dữ liệu vận hành về lỗi transaction có thể được ghi theo cơ chế khác, nhưng không được tạo một lịch sử thành công khi thay đổi chính đã rollback.

## 7. Email, SMS và event qua transactional outbox

Một transaction SQL cục bộ không thể tự rollback email đã gửi. Nếu gửi email trước commit, người dùng có thể nhận thông báo thành công dù cơ sở dữ liệu sau đó rollback. Nếu commit rồi mới gọi gửi một cách trực tiếp, ứng dụng có thể dừng giữa hai bước và làm mất ý định thông báo.

[Tài liệu AWS về transactional outbox](https://docs.aws.amazon.com/prescriptive-guidance/latest/cloud-design-patterns/transactional-outbox.html) mô tả cách ghi thay đổi nghiệp vụ và ý định phát sự kiện trong cùng transaction, sau đó xử lý việc chuyển sự kiện bằng thành phần riêng.

Áp dụng cho khôi phục:

```text
Trong cùng transaction:
  thay đổi xác thực
  trạng thái request
  sự kiện bảo mật
  outbox(event_id, event_type, aggregate_id, payload_tối_thiểu)

Sau commit:
  thành phần chuyển sự kiện đọc outbox đã commit
  gửi đến hệ thống thông báo hoặc dịch vụ liên quan
  ghi nhận tiến độ và thử lại theo hợp đồng
```

Outbox bảo vệ việc không bỏ sót ý định đã ghi. Nó không tự bảo đảm người dùng nhận email đúng một lần. Nếu tiến trình dừng sau khi gửi nhưng trước khi ghi nhận kết quả, cùng sự kiện có thể được gửi lại.

Cần dùng định danh sự kiện ổn định và cơ chế xử lý trùng phù hợp ở các thành phần nhận. Với sự kiện cùng tài khoản, cũng cần xác định thứ tự hoặc phiên bản để một thông báo cũ không làm sai trạng thái mới.

Payload không nên chứa mật khẩu, OTP hoặc token chỉ để dễ gửi lại. Các nội dung thực sự cần bí mật phải có cơ chế bảo vệ và vòng đời riêng, không được coi một bảng outbox thông thường là kho lưu bí mật an toàn.

## 8. Session và những hệ thống ngoài phạm vi transaction

Một thao tác khôi phục có thể tác động đến cơ sở dữ liệu credential, kho session, cache hoặc dịch vụ định danh khác. Không nên gọi tất cả chúng là “đã nguyên tử” nếu chỉ một phần dùng cùng transaction.

Ví dụ, tăng `security_version` trong tài khoản có thể là một phần chiến lược vô hiệu hóa phiên. Tuy nhiên, nó chỉ có hiệu lực theo cơ chế thực tế mà các điểm chấp nhận session dùng để kiểm tra phiên bản. Một cache chưa cập nhật có thể vẫn chấp nhận dữ liệu cũ nếu thiết kế không xử lý độ trễ đó.

Cần phân biệt:

- Thay đổi đã được commit trong cơ sở dữ liệu nguồn.
- Ý định thu hồi đã được ghi để xử lý.
- Việc thu hồi tại từng điểm sử dụng đã có hiệu lực.
- Điều kiện nào phải đạt trước khi request được coi là hoàn tất.

Nếu chính sách yêu cầu thu hồi xong mới cấp quyền tiếp tục, trạng thái request phải phản ánh điều kiện đó. Không đặt `COMPLETED` rồi để giao diện nói mọi phiên đã kết thúc trong khi hệ thống liên quan vẫn đang chờ.

Với nhiều kho dữ liệu, cần một quy trình phối hợp có trạng thái, retry và đối chiếu rõ ràng. Không mặc định dùng bù trừ bằng cách khôi phục credential bị nghi ngờ hoặc làm token đã dùng trở lại hợp lệ; những thao tác đó có thể tạo đường chiếm đoạt.

## 9. Retry sau xung đột hoặc mất phản hồi commit

Có hai trường hợp khác nhau:

| Trường hợp | Điều đã biết | Cách xử lý |
| --- | --- | --- |
| Cơ sở dữ liệu xác nhận transaction bị rollback do xung đột | Đơn vị ghi chưa được commit | Có thể thử lại toàn đơn vị theo chính sách |
| Mất kết nối trong lúc xác nhận commit | Kết quả có thể chưa rõ với client | Đối chiếu cùng thao tác trước khi tạo thay đổi mới |

Khi retry do deadlock hoặc serialization failure, cần đọc lại điều kiện và thực hiện lại cả transaction cần thiết. Không chỉ phát lại câu lệnh cuối với dữ liệu đã đọc trước đó.

Khi kết quả commit chưa rõ, một định danh thao tác có phạm vi quyền phù hợp có thể hỗ trợ trả lại kết quả của cùng ý định. Định danh chống lặp không thay thế token xác minh và không cho phép truy cập kết quả của người khác.

Thời gian lưu kết quả chống lặp phải phù hợp với hợp đồng retry. Không lưu mật khẩu thô, toàn bộ request nhạy cảm hoặc bí mật cấp quyền chỉ để nhận diện thao tác trùng.

Retry cũng cần có giới hạn. Nếu trạng thái đã thay đổi, token đã bị thu hồi hoặc request không còn quyền, lần thử mới phải tôn trọng trạng thái đó thay vì cố “hoàn tất bằng mọi giá”.

## 10. Tình huống minh họa

An nhận token T cho thao tác đặt lại mật khẩu trong request R. Hai lần gửi gần nhau đến hai instance ứng dụng.

Instance thứ nhất giành được quyền cập nhật dữ liệu liên quan, kiểm tra lại điều kiện, tiêu thụ T, lưu mật khẩu mới, cập nhật request và ghi outbox trong cùng transaction. Khi commit thành công, đơn vị thay đổi đó trở thành kết quả có thẩm quyền.

Instance thứ hai không thể coi bản đọc token chưa dùng trước đó là còn đúng. Khi đọc hoặc cập nhật lại theo cơ chế kiểm soát cạnh tranh, nó phải xử lý trạng thái hiện tại. Nếu đây là gửi lại cùng ý định có hợp đồng chống lặp, hệ thống có thể trả kết quả đã ghi trong phạm vi quyền phù hợp; nó không dùng T để đặt thêm một mật khẩu khác.

Nếu instance thứ nhất lỗi trước commit, toàn đơn vị ghi cục bộ được rollback và không có sự kiện outbox thành công để chuyển đi. Nếu lỗi sau commit nhưng trước khi trả phản hồi, kết quả vẫn có thể được đối chiếu theo cùng thao tác. Thông báo và việc thu hồi ở hệ thống ngoài được theo dõi theo trạng thái thực tế.

Transactional recovery writes giúp việc khôi phục giữ được những bất biến khi có lỗi và cạnh tranh. Đơn vị ghi rõ ràng, kiểm tra trạng thái tại lúc quyết định và ranh giới chính xác giữa cơ sở dữ liệu với hệ thống ngoài là nền tảng của thiết kế này.
