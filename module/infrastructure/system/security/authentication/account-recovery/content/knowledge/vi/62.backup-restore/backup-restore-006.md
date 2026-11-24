# Recovery disaster procedure — Quy trình phục hồi sau thảm họa

## 1. Phạm vi của quy trình

Trong hệ thống khôi phục tài khoản, thảm họa có thể là mất cơ sở dữ liệu, hỏng vùng triển khai, mã độc tống tiền, hỏng dữ liệu diện rộng hoặc mất khả năng sử dụng hạ tầng quản lý khóa. Sự cố có thể đồng thời ảnh hưởng tới thông tin xác thực, trạng thái thu hồi, hồ sơ khôi phục và các kênh thông báo.

**Recovery disaster procedure** là trình tự đưa dịch vụ trở lại hoạt động từ nguồn dữ liệu đáng tin cậy, đồng thời giữ các bất biến bảo mật. Mục tiêu không chỉ là ứng dụng khởi động được hoặc người dùng đăng nhập được.

Trong module `SECURITY_AUTHENTICATION_ACCOUNT_RECOVERY`, quy trình cần bảo vệ cả việc khôi phục khi mất mật khẩu, MFA, passkey hoặc thiết bị xác thực. Sau thảm họa, hệ thống không được vô tình chấp nhận lại token đã dùng, phiên đã thu hồi, yếu tố xác thực bị báo mất hoặc kênh khôi phục không còn đáng tin cậy.

Cần phân biệt hai bài toán:

- **Khôi phục tài khoản cá nhân:** xác minh người yêu cầu rồi tái lập khả năng truy cập cho tài khoản cụ thể.
- **Phục hồi dịch vụ sau thảm họa:** khôi phục hạ tầng và dữ liệu cho nhiều tài khoản, có thể từ một mốc cũ.

Không phục hồi cả cơ sở dữ liệu chỉ để giải quyết một lượt quên mật khẩu. Ngược lại, không coi toàn bộ tài khoản đã được chứng minh sở hữu chỉ vì đội vận hành vừa đưa một bản backup trở lại hệ thống.

Một nguyên tắc xuyên suốt là:

```text
Khôi phục dữ liệu cũ
    không được tự động khôi phục
hiệu lực của mọi quyền truy cập từng tồn tại trong dữ liệu đó
```

## 2. Mối nguy đặc thù của việc quay về trạng thái cũ

Giả sử backup được tạo lúc 08:00. Sau đó xảy ra các sự kiện:

```text
08:00  Tạo backup B0.
08:20  Người dùng thu hồi một passkey bị mất.
08:30  Token khôi phục R1 được tiêu thụ.
08:40  Toàn bộ phiên của một tài khoản bị chiếm được vô hiệu hóa.
09:00  Cơ sở dữ liệu chính gặp thảm họa.
09:30  Đội vận hành phục hồi B0.
```

Nếu chỉ đưa B0 vào phục vụ, passkey có thể trông như còn hợp lệ, token R1 có thể trở lại trạng thái chưa dùng và các phiên cũ có thể được chấp nhận. Dữ liệu phục hồi đúng với thời điểm 08:00 nhưng trạng thái bảo mật lại sai với các quyết định đã có hiệu lực sau đó.

Tương tự, mật khẩu đã đổi hoặc địa chỉ khôi phục đã bị loại bỏ sau mốc backup có thể xuất hiện lại. Chỉ thu hồi phiên không đủ để xử lý một password verifier cũ vẫn cho phép đăng nhập mới.

Nguy cơ khác là phục hồi dữ liệu đã xóa hợp lệ, liên kết nhầm tenant, phát lại email chứa quyền khôi phục, hoặc thực hiện lại một tác vụ đã có tác dụng ở nhà cung cấp bên ngoài.

Quy trình vì vậy cần khôi phục **dữ liệu nền** và **các quyết định bảo mật còn hiệu lực**, rồi kiểm tra điều kiện mở dịch vụ. Nếu thiếu nguồn đủ tin cậy để tái lập trạng thái, cần giới hạn hoặc vô hiệu hóa phần bị ảnh hưởng thay vì suy đoán rằng trạng thái cũ là an toàn.

## 3. Chuẩn bị trước khi xảy ra sự cố

Quy trình không nên bắt đầu bằng việc đi tìm ai còn giữ mật khẩu của kho backup. Trước sự cố cần có danh mục phụ thuộc, phân vai và nguồn dữ liệu phục hồi rõ ràng.

| Thành phần | Cần biết trước | Rủi ro nếu thiếu |
| --- | --- | --- |
| Cơ sở dữ liệu tài khoản | Backup, nhật ký giao dịch, schema và mốc nhất quán | Khôi phục thiếu hoặc sai quan hệ |
| Trạng thái thu hồi và dùng một lần | Nguồn chuẩn, phạm vi và khả năng phát lại quyết định | Quyền đã mất hiệu lực được chấp nhận lại |
| Khóa và bí mật dịch vụ | Nguồn quản lý, quyền phục hồi, tình trạng bị nghi lộ | Không giải mã được hoặc dùng lại khóa không an toàn |
| Hồ sơ và kho đối tượng | Quan hệ giữa bản ghi và phiên bản đối tượng | Mất tệp, sai chủ sở hữu hoặc lộ dữ liệu |
| Queue và tác vụ nền | Tác vụ nào được tiếp tục, hủy hoặc đối soát | Phát lại tác dụng phụ |
| Nhà cung cấp xác minh, email, danh tính | Contract, đầu mối xử lý và cách kiểm tra trạng thái | Không biết tác vụ trước sự cố đã hoàn tất chưa |
| DNS, cân bằng tải, mạng và quan sát | Cách cô lập, chuyển vùng và ngăn writer cũ | Hai vùng cùng ghi hoặc lộ dịch vụ chưa sẵn sàng |

Backup cần có kiểm soát truy cập, mã hóa thích hợp, thông tin toàn vẹn và nguồn gốc có thể xác minh. Một checksum chỉ hữu ích nếu giá trị đối chiếu được bảo vệ và đến từ nguồn đáng tin cậy. Đặt backup và mọi chứng cứ kiểm tra trong cùng phạm vi bị xâm nhập có thể làm mất cơ sở tin cậy của cả hai.

Phân vai có thể gồm người chỉ huy sự cố, người phục hồi dữ liệu, người đánh giá an ninh và người cho phép mở lại dịch vụ. Các thao tác đặc quyền cần kiểm soát độc lập theo policy; không cho một người tự chọn backup, bỏ các cổng bảo mật rồi tự tuyên bố hoàn tất mà không có trách nhiệm kiểm chứng phù hợp.

### RTO và RPO phải đi cùng điều kiện bảo mật

RTO mô tả mục tiêu thời gian đưa dịch vụ trở lại; RPO mô tả mục tiêu về mức mất dữ liệu theo thời gian. Đây là mục tiêu thiết kế cần được kiểm chứng, không phải bảo đảm tự có khi sao lưu định kỳ.

Một RPO cho dữ liệu nghiệp vụ không tự cho phép chấp nhận lại yếu tố đã bị thu hồi trong khoảng mất dữ liệu. Nếu không phục hồi được các quyết định đó, phương án có thể là vô hiệu hóa phạm vi thông tin xác thực liên quan và yêu cầu quy trình tái xác minh thích hợp. Cần chuẩn bị năng lực hỗ trợ vì lựa chọn an toàn này có thể ảnh hưởng nhiều người dùng.

## 4. Giai đoạn 1 — Tuyên bố sự cố và cô lập nguồn không đáng tin cậy

Đội phụ trách xác định loại sự cố, phạm vi tài khoản hoặc tenant bị ảnh hưởng, mức tin cậy của hạ tầng và quyết định kích hoạt quy trình. Mất khả dụng thuần túy và nghi ngờ xâm nhập cần những điều kiện xử lý khác nhau.

Các hành động cô lập có thể gồm:

- Chặn ghi vào phạm vi dữ liệu bị ảnh hưởng.
- Ngăn vùng cũ tiếp tục xử lý yêu cầu sau khi có vùng thay thế.
- Dừng phát hành grant hoặc token khôi phục nếu không thể bảo đảm dùng một lần.
- Tạm dừng tác vụ nền có thể gửi bí mật hoặc thay đổi trạng thái.
- Giới hạn kết nối ra ngoài của môi trường phục hồi để tránh phát lại thông báo thật.
- Bảo vệ các bằng chứng sự cố theo quy trình được phép, tránh làm mất dữ liệu cần điều tra.

Không nên chỉ dừng một tiến trình ứng dụng rồi cho rằng không còn writer. Cron job, consumer, tích hợp quản trị hoặc vùng mạng bị phân tách vẫn có thể tiếp tục ghi.

Nếu nghi môi trường cũ bị xâm nhập, không sử dụng mặc nhiên các bí mật, công cụ và kết quả quan sát của nó làm nguồn tin cậy duy nhất. Môi trường phục hồi cần được xây từ nền tảng và quyền quản trị được chấp nhận theo kế hoạch ứng phó.

Việc duy trì truy cập khẩn cấp cho người vận hành phải có phạm vi, thời hạn và truy vết. Một tài khoản đặc quyền khẩn cấp không phải lý do để bỏ kiểm tra danh tính người dùng hoặc cấp quyền khôi phục hàng loạt.

## 5. Giai đoạn 2 — Chọn mốc phục hồi và tập dữ liệu nhất quán

Chọn nguồn phục hồi dựa trên tình trạng toàn vẹn và phạm vi sự cố. Backup mới nhất có thể đã chứa dữ liệu hỏng hoặc thay đổi do kẻ tấn công tạo ra. Backup cũ hơn có thể đáng tin cậy hơn nhưng tạo khoảng cách lớn hơn với trạng thái bảo mật hiện tại.

Manifest của lần phục hồi nên xác định:

```text
restore_run_id
incident_reference
backup_id và nguồn đã xác minh
backup_time hoặc checkpoint dữ liệu
schema_version
phạm vi account/tenant/dịch vụ
database_log_position nếu có
object_storage_manifest_reference
security_decision_watermark hoặc nguồn đối soát
người thực hiện và người kiểm tra theo policy
```

Không ghép tùy tiện bảng người dùng từ một ngày với bảng quyền, khóa mã hóa và kho đối tượng từ ngày khác. Cần hiểu mối quan hệ nhất quán mà hệ thống bảo đảm và cách đối soát phần chênh lệch.

Một timestamp chung không tự chứng minh mọi nơi đã cùng commit dữ liệu. Với hệ thống phân tán, mốc nhất quán có thể phải được mô tả bằng vị trí nhật ký hoặc checkpoint riêng cho từng thành phần, cùng các ràng buộc giữa chúng.

Nếu khôi phục một phần theo tenant, kiểm tra đầy đủ tham chiếu chéo và tài nguyên dùng chung. Không sao chép quyền hoặc hồ sơ của tenant khác chỉ vì chúng nằm trong cùng một file backup.

Chốt nguồn và phạm vi trước khi thao tác. Khi đổi backup giữa chừng, lập kế hoạch và ghi nhận lại những phần bị ảnh hưởng; không tiếp tục dùng kết quả kiểm tra của tập dữ liệu trước như thể chưa có thay đổi.

## 6. Giai đoạn 3 — Phục hồi trong môi trường chưa phục vụ người dùng

Phục hồi dữ liệu vào môi trường có kiểm soát, chưa nhận lưu lượng sản xuất thông thường và chưa tự động thực thi tác vụ cũ. Nạp schema, dữ liệu, phiên bản đối tượng và các phụ thuộc theo thứ tự đã được thiết kế.

Giữ account ID, tenant ID và quan hệ dữ liệu ổn định. Không tạo một người dùng mới cho mỗi hồ sơ rồi nối lại theo email. Cách đó có thể phá quyền sở hữu, quan hệ chia sẻ và chuỗi truy vết.

Những kiểm tra cấu trúc cần làm rõ gồm:

- Account, hồ sơ và thông tin xác thực có đúng phạm vi và quan hệ không.
- Các đối tượng được tham chiếu có đúng phiên bản và quyền truy cập không.
- Bản ghi đã xóa hoặc bị hạn chế có bị đưa trở lại sai cách không.
- Những trạng thái trung gian của khôi phục có được nhận diện để đối soát không.
- Dữ liệu mã hóa có thể được xử lý bằng khóa hợp lệ mà không hạ kiểm soát truy cập không.

Khôi phục thành công các hàng dữ liệu không chứng minh có khả năng giải mã. Ngược lại, giải mã được một tệp không chứng minh người dùng hiện tại có quyền xem tệp đó. Quyền truy cập và khả năng kỹ thuật phải được kiểm tra riêng.

Không đưa token, khóa hoặc tài liệu định danh thô vào log để minh họa rằng bản restore hoạt động. Dùng tham chiếu và kết quả tối thiểu trong hồ sơ vận hành.

## 7. Giai đoạn 4 — Tái lập trạng thái bảo mật hiện hành

Đây là cổng quan trọng trước khi cho đăng nhập hoặc phát hành quyền khôi phục mới. Cần xác định phần quyết định bảo mật bị lùi theo backup và nguồn nào có thể tái lập chúng.

### Đối soát các quyết định sau mốc backup

Tùy kiến trúc, nguồn đối soát có thể là nhật ký giao dịch, luồng sự kiện bảo mật, kho thu hồi độc lập hoặc một nguồn chuẩn bên ngoài còn đáng tin cậy. Nguồn đó phải đủ thông tin và có thứ tự hoặc quy tắc hợp nhất phù hợp; một log ứng dụng không đầy đủ không tự trở thành nhật ký phục hồi có thẩm quyền.

Các quyết định cần xem xét gồm:

- Mật khẩu đã thay hoặc đã được đánh dấu không còn đáng tin cậy.
- MFA, passkey và kênh khôi phục đã bị thu hồi hoặc thay đổi.
- Grant khôi phục đã dùng, bị hủy, hết hạn hoặc bị thu hồi.
- Phiên, refresh token và thông tin truy cập khác đã mất hiệu lực.
- Tài khoản bị khóa, bị hạn chế hoặc thay đổi quyền.
- Quyết định xóa dữ liệu cần được áp dụng lại trước khi phục vụ.

Phải bao phủ khoảng thời gian tới điểm chuyển quyền ghi đã được chốt, không chỉ tới thời điểm đội vận hành nhận ra sự cố. Nếu writer cũ vẫn hoạt động sau mốc đó, phạm vi chênh lệch tiếp tục thay đổi và cần được xử lý trước khi mở vùng mới.

Một số quyết định chỉ yêu cầu áp dụng lại trạng thái thu hồi; một số khác cần dữ liệu mới nhất. Nếu password verifier mới đã mất và không thể phục hồi đáng tin cậy, không thể tái tạo nó từ lịch sử “mật khẩu đã đổi”. Hệ thống có thể phải vô hiệu hóa verifier cũ và yêu cầu luồng khôi phục hợp lệ thay vì chấp nhận mật khẩu trước đó.

### Khi không thể chứng minh đầy đủ trạng thái

Không coi thiếu bản ghi là bằng chứng rằng quyền chưa từng bị thu hồi. Với phần trạng thái không thể đối soát, chọn phương án giới hạn theo policy, chẳng hạn vô hiệu hóa các grant cũ, yêu cầu xác thực lại hoặc chuyển tài khoản sang trạng thái cần tái lập thông tin xác thực.

Phạm vi phải được xác định rõ: thu hồi toàn bộ phiên không tự thu hồi mật khẩu hay passkey cũ; vô hiệu hóa token khôi phục không tự xử lý API key. Mỗi lớp thông tin xác thực cần có cơ chế hiệu lực riêng.

Nếu dùng một thế hệ bảo mật hoặc epoch toàn hệ thống, giá trị mới phải được tạo và kiểm tra từ nguồn đáng tin cậy không bị lùi cùng backup. Tăng `epoch` lên một đơn vị từ một số cũ trong snapshot có thể vẫn thấp hơn trạng thái đã tồn tại trước sự cố.

Mọi đường chấp nhận quyền liên quan phải kiểm tra thế hệ đó hoặc cơ chế thay thế tương ứng. Một token có chữ ký hợp lệ không tự mất hiệu lực vì một cột vừa được tăng ở cơ sở dữ liệu mà dịch vụ nhận token không đọc.

Không sửa thời gian hệ thống về quá khứ hoặc gia hạn token cũ để làm dữ liệu phục hồi “chạy được”. Dùng thời gian đáng tin cậy và đánh giá hết hạn theo hiện tại; các yêu cầu đã hết hạn không tự sống lại sau restore.

## 8. Giai đoạn 5 — Đối soát khóa, phiên và tác vụ dở dang

### Khóa và bí mật dịch vụ

Xác định riêng khóa mã hóa dữ liệu, khóa ký, bí mật tích hợp và thông tin xác thực quản trị. Chúng có vai trò và điều kiện phục hồi khác nhau. Không thay toàn bộ bằng một bí mật chung hoặc tắt mã hóa để vượt lỗi.

Nếu khóa ký bị nghi lộ hoặc trạng thái token cũ không thể được tin cậy, xử lý theo kế hoạch thu hồi và chuyển khóa. Phát hành bằng khóa mới trong khi mọi verifier vẫn chấp nhận khóa cũ chưa đủ để loại quyền cũ. Việc phân phối cấu hình, cache và các dịch vụ xác minh phải được tính đến.

Khóa giải mã cũ có thể cần để đọc dữ liệu còn hợp lệ, nhưng quyền dùng khóa phải được giới hạn theo mục đích. Không phục hồi một quyền giải mã đã bị thu hồi chỉ vì nó từng xuất hiện trong backup. Nếu khóa thực sự mất và không có cơ chế phục hồi hợp lệ, cần nêu đúng giới hạn dữ liệu có thể khôi phục.

### Phiên và thông tin truy cập

Lập danh sách lớp quyền cần kiểm soát: phiên web, refresh token, access token, phiên khôi phục hạn chế và những thông tin truy cập khác thuộc phạm vi dịch vụ. Áp dụng cơ chế thu hồi thực sự có hiệu lực ở từng nơi nhận.

Không nhập lại session cache từ backup rồi cho hoạt động ngay. Một bản cache cũ có thể chứa trạng thái cho phép đã hết hiệu lực. Nếu quyết định buộc đăng nhập lại, cần bảo đảm các đường nhận token và session cookie thực sự từ chối trạng thái cũ.

### Outbox, queue và tác dụng phụ bên ngoài

Một backup có thể chứa tác vụ gửi token đang chờ trong khi trước sự cố tác vụ đã được gửi và token đã dùng. Phát lại toàn bộ queue có thể gửi lại bí mật hoặc kích hoạt hành động không còn hợp lệ.

Phân loại tác vụ theo execution ID, request ID, phiên bản đề xuất và kết quả thực tế. Đối soát với hệ thống bên ngoài khi cần; nếu kết quả chưa rõ, ghi trạng thái chờ điều tra hoặc tiếp tục có kiểm soát, không tự tạo một lượt thực thi mới.

Chỉ cho chạy lại tác vụ còn hợp lệ theo trạng thái hiện tại. Tác vụ hết hạn, bị hủy hoặc thuộc phiên bản cũ cần bị loại khỏi luồng thực thi theo policy. Thông báo thông tin không mang bí mật cũng cần kiểm tra ngữ cảnh để tránh báo “đang chờ phê duyệt” cho hồ sơ đã đóng.

Outbox hỗ trợ giao bền vững nhưng không tự tạo thực thi đúng một lần xuyên nhiều hệ thống. Khóa chống trùng và kiểm tra trạng thái ở bên nhận vẫn cần thiết, nhất là khi bản ghi chống trùng cũng có thể đã bị lùi bởi backup.

## 9. Giai đoạn 6 — Chốt điều kiện mở lại dịch vụ

Một bản restore mở được không đồng nghĩa dịch vụ đủ điều kiện nhận mọi lưu lượng. Cần chốt các cổng phù hợp với từng khả năng sẽ được mở.

| Cổng | Điều cần chứng minh | Khi chưa đạt |
| --- | --- | --- |
| Cô lập writer cũ | Không có hai vùng cạnh tranh ghi ngoài kế hoạch | Chưa cho vùng mới nhận ghi |
| Toàn vẹn dữ liệu | Nguồn, schema và quan hệ phục hồi đúng phạm vi | Tiếp tục cô lập và xử lý sai lệch |
| Trạng thái xác thực | Quyền cũ bị thu hồi hoặc được đối soát đúng | Giới hạn đăng nhập theo phạm vi ảnh hưởng |
| Quyền khôi phục | Không chấp nhận lại grant đã dùng hoặc không còn đáng tin | Chưa mở đường thực thi khôi phục liên quan |
| Khóa và bí mật | Nguồn hợp lệ, quyền và chính sách chấp nhận đúng | Chưa phát hành hoặc giải mã ngoài phạm vi được xác lập |
| Dữ liệu đã xóa | Không phục vụ lại dữ liệu phải tiếp tục bị xóa hoặc hạn chế | Giữ phần dữ liệu đó ngoài phục vụ |
| Tác vụ nền | Không phát lại hành động cũ ngoài quyền hiện tại | Giữ queue hoặc consumer tương ứng ở trạng thái dừng |
| Quan sát và phản ứng | Có khả năng phát hiện lỗi, truy vết và cô lập lại | Chưa mở rộng phạm vi lưu lượng |

Có thể mở theo giai đoạn nếu kiến trúc và policy hỗ trợ, chẳng hạn một phạm vi tenant đã đối soát hoặc một chức năng chỉ đọc đã xác lập quyền. Chế độ chỉ đọc không tự an toàn nếu vẫn trả dữ liệu cho phiên cũ hoặc đưa dữ liệu đã xóa trở lại.

Không bật endpoint đặt lại mật khẩu chỉ vì email đã gửi được. Đường đó còn cần đúng tài khoản đích, xác minh danh tính, đánh giá rủi ro, token dùng một lần và kiểm soát phiên có hiệu lực.

Sau khi mở, theo dõi dấu hiệu bất thường như tăng lỗi xác thực, token cũ được gửi lại, tài khoản có phương thức xác thực không mong đợi, tác vụ lặp và hồ sơ sai tenant. Có tiêu chí ngừng mở rộng hoặc cô lập phần bị ảnh hưởng, không chỉ một kế hoạch quay lại backup cũ hơn.

### Ví dụ Java: một cổng không chấp nhận kết quả chưa kiểm tra

Đoạn mã minh họa cách yêu cầu các báo cáo đều thuộc đúng restore run và có kết quả đạt. Nó không tự tạo bằng chứng và không phải toàn bộ hệ thống cấp quyền mở dịch vụ.

```java
import java.util.EnumSet;
import java.util.Map;
import java.util.UUID;

enum RestoreGate {
    OLD_WRITERS_FENCED,
    DATA_INTEGRITY,
    AUTHORIZATION_STATE,
    KEY_STATUS,
    DELETION_STATE,
    BACKGROUND_TASKS,
    OBSERVABILITY
}

enum GateResult {
    NOT_CHECKED, PASSED, FAILED
}

record GateEvidence(UUID restoreRunId, GateResult result) {
}

final class RestoreReadiness {
    static boolean allRequiredGatesPassed(
            UUID currentRunId,
            Map<RestoreGate, GateEvidence> evidence) {

        if (currentRunId == null || evidence == null) {
            return false;
        }

        for (RestoreGate gate : EnumSet.allOf(RestoreGate.class)) {
            GateEvidence report = evidence.get(gate);
            if (report == null
                    || !currentRunId.equals(report.restoreRunId())
                    || report.result() != GateResult.PASSED) {
                return false;
            }
        }
        return true;
    }
}
```

Báo cáo phải đến từ các kiểm tra và quyết định có thẩm quyền phía máy chủ, không từ các checkbox hoặc cờ do client tự khai. Hệ thống thực tế còn cần liên kết bằng chứng, phạm vi khả năng được mở, phiên bản cấu hình, độ mới và quyền ra quyết định.

Nếu đổi nguồn backup, cấu hình chấp nhận khóa hoặc phạm vi phục vụ sau khi kiểm tra, phải xem lại các cổng bị ảnh hưởng. Không tái sử dụng một bản `PASSED` của dữ liệu khác chỉ vì cùng một incident ID.

## 10. Truyền thông và hỗ trợ người dùng

Thông báo sự cố cần cho biết trạng thái dịch vụ và hành động người dùng cần thực hiện, không làm lộ danh sách tài khoản bị ảnh hưởng hoặc chi tiết có thể giúp lạm dụng đường khôi phục.

Nếu cần buộc xác thực lại hoặc thiết lập lại phương thức truy cập, hướng người dùng tới giao diện chính thức và giải thích phạm vi. Không gửi mật khẩu dùng chung, yêu cầu trả lời email bằng backup code hoặc nhờ nhân viên thu thập OTP qua chat.

Khi nhiều người cùng mất khả năng đăng nhập vì quyết định bảo vệ sau restore, luồng hỗ trợ có thể quá tải. Cần giữ nguyên yêu cầu xác minh và phân loại rủi ro, đồng thời điều phối năng lực xử lý. Không giảm kiểm soát xuống chỉ kiểm tra email hiển thị để rút ngắn hàng đợi.

Kênh thông báo cũng có thể nằm trong phạm vi sự cố. Nếu bí mật tích hợp hoặc mailbox bị nghi chiếm, dùng kênh dự phòng đã được xác lập trước theo policy; không chọn địa chỉ mới do người tự xưng là quản trị viên cung cấp tại chỗ.

Phân biệt rõ thông báo “dịch vụ đã hoạt động”, “tài khoản cần xác thực lại” và “dữ liệu của tài khoản đã được đối soát”. Không tuyên bố phục hồi toàn bộ nếu một số tenant hoặc loại dữ liệu vẫn đang bị giới hạn.

## 11. Phương án khi phục hồi không đạt

Không phải mọi lần phục hồi đều đủ điều kiện mở dịch vụ. Nguồn backup có thể bị hỏng, thiếu khóa, không đối soát được trạng thái thu hồi hoặc phát hiện dấu hiệu xâm nhập chưa được kiểm soát.

Trong các trường hợp đó, giữ môi trường không phục vụ phần chưa đủ điều kiện, bảo toàn trạng thái thực tế của lần phục hồi và chọn bước tiếp theo trong phạm vi ứng phó đã được cho phép. Có thể cần nguồn backup khác, phạm vi phục hồi nhỏ hơn hoặc quy trình tái lập quyền truy cập cho nhóm tài khoản cụ thể.

Nếu dịch vụ đã mở một phần rồi phải đóng lại, không đơn giản chuyển ngược DNS và xóa vùng mới. Vùng mới có thể đã có mật khẩu mới, quyết định thu hồi, giao dịch và yêu cầu xóa mới. Phải chốt writer, đối soát các thay đổi đã phát sinh và bảo vệ chúng trước khi chuyển tiếp.

Một rollback hạ tầng không nên hoàn tác quyết định bảo mật đã có hiệu lực. Cách ly hoặc thay thế hạ tầng cần giữ được ranh giới đó, kể cả khi phải duy trì hạn chế truy cập lâu hơn dự kiến.

Ghi rõ giới hạn không thể khắc phục ngay. Nếu một loại dữ liệu mã hóa mất khóa không thể phục hồi, không đánh dấu toàn bộ hệ thống thành công chỉ vì các trang không cần dữ liệu đó vẫn hoạt động.

## 12. Diễn tập và cải thiện quy trình

Khả năng phục hồi cần được diễn tập trong môi trường có kiểm soát, không chỉ kiểm tra rằng file backup tồn tại. Kịch bản nên bao gồm cả lỗi dữ liệu và lỗi trạng thái bảo mật.

| Kịch bản diễn tập | Điều cần quan sát |
| --- | --- |
| Token đã dùng sau mốc backup | Sau phục hồi không được thực thi lại bằng token đó |
| Passkey hoặc MFA đã thu hồi | Không chấp nhận lại yếu tố cũ |
| Mật khẩu đã đổi nhưng bản mới không còn trong backup | Không mặc nhiên cho đăng nhập bằng mật khẩu trước đó |
| Hai vùng bị chia cắt mạng | Writer cũ không tiếp tục ghi khi vùng mới được mở |
| Outbox chứa tác vụ đã thực thi | Không tạo lại tác dụng phụ ngoài kế hoạch |
| Hồ sơ hoặc tệp đã bị xóa | Không phục vụ lại từ snapshot cũ |
| Khóa bị nghi lộ hoặc không sẵn sàng | Không tắt kiểm soát để vượt cổng |
| Rollback sau khi đã nhận ghi mới | Không làm mất quyết định bảo mật mới |

Ưu tiên dữ liệu tổng hợp cho diễn tập. Nếu cần dữ liệu thật theo quyền đã xác lập, môi trường và đầu ra vẫn cần mức bảo vệ phù hợp; môi trường thử không tự làm giấy tờ hay bí mật bớt nhạy cảm.

Đo thời gian từng giai đoạn, phần dữ liệu mất, nguồn đối soát thiếu và các công việc phải làm thủ công. Kết quả diễn tập cần làm thay đổi runbook, kiến trúc backup hoặc nguồn trạng thái bảo mật khi phát hiện khoảng trống. Một báo cáo “restore thành công” không có tiêu chí về quyền cũ là chưa đủ cho dịch vụ khôi phục tài khoản.

## 13. Tình huống xuyên suốt

Một vùng cơ sở dữ liệu gặp sự cố nghiêm trọng lúc 09:00. Backup đáng tin cậy gần nhất có mốc 08:00. Trong khoảng đó, người dùng đã thu hồi một passkey, một token khôi phục đã được dùng và một nhóm phiên của tài khoản bị chiếm đã bị vô hiệu hóa.

Đội sự cố chặn writer cũ và dừng tác vụ có thể gửi hoặc sử dụng quyền khôi phục. Dữ liệu được phục hồi trong môi trường cô lập, dùng manifest xác định nguồn và phạm vi. Account ID cùng quan hệ hồ sơ được giữ nguyên.

Nguồn quyết định bảo mật đáng tin cậy cho phép áp dụng lại việc thu hồi passkey và trạng thái token đã dùng. Đối với một nhóm mật khẩu mới bị mất mà không thể tái lập verifier, hệ thống vô hiệu hóa khả năng đăng nhập bằng trạng thái cũ theo policy và yêu cầu quy trình tái lập phù hợp. Việc đó được xử lý riêng với hồ sơ người dùng, không tạo tài khoản mới.

Queue được đối soát để không gửi lại link khôi phục cũ. Cấu hình khóa và các đường chấp nhận phiên được kiểm tra để bảo đảm quyết định thu hồi có hiệu lực ở nơi nhận. Dữ liệu đã có quyết định xóa được xử lý trước khi phục vụ.

Chỉ các phạm vi đã đạt cổng mới được mở. Đội hỗ trợ hướng dẫn người bị ảnh hưởng qua kênh chính thức mà không yêu cầu họ gửi mật khẩu hoặc mã dự phòng cho nhân viên. Các giới hạn chưa giải quyết được tiếp tục được công bố đúng mức và theo dõi.

Quy trình phục hồi sau thảm họa chỉ đạt mục tiêu khi đưa dịch vụ trở lại mà vẫn giữ đúng ai được phép truy cập, quyền nào đã mất hiệu lực và dữ liệu nào được phép tồn tại. Backup cung cấp một điểm bắt đầu; các quyết định bảo mật, đối soát và kiểm soát mở dịch vụ quyết định điểm đó có thể được đưa vào sử dụng an toàn hay không.
