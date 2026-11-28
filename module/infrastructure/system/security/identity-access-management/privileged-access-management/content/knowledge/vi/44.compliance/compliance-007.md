# Bằng chứng cho ngoại lệ chính sách trong PAM

## 1. Ngoại lệ chính sách cần chứng minh điều gì?

Một hệ thống Privileged Access Management (PAM) có thể đặt ra các chính sách như: tài khoản quản trị phải được kiểm kê, người dùng phải đăng nhập bằng danh tính cá nhân, quyền đặc biệt chỉ được cấp trong thời gian cần thiết, credential phải được quản lý và luân chuyển, phiên truy cập phải được giám sát, bằng chứng phải được lưu để truy vết.

Trong thực tế, một hệ thống cũ, một thiết bị chưa được hỗ trợ hoặc một quy trình khôi phục đặc biệt có thể chưa đáp ứng được một phần chính sách. **Ngoại lệ chính sách** là quyết định cho phép một sai lệch đã xác định, trong phạm vi và thời hạn cụ thể, với trách nhiệm và điều kiện đi kèm.

Bằng chứng cho ngoại lệ chính sách, hay *policy exception evidence*, là tập hợp thông tin giúp một người độc lập kiểm tra được:

- Yêu cầu nào chưa được đáp ứng, trên những đối tượng nào.
- Vì sao cần ngoại lệ và những phương án nào đã được xem xét.
- Rủi ro phát sinh là gì và ai có thẩm quyền chấp nhận rủi ro đó.
- Kiểm soát bù nào thực sự hoạt động trong thời gian ngoại lệ.
- Có hoạt động truy cập nào xảy ra và hoạt động đó có nằm trong phạm vi được duyệt hay không.
- Ngoại lệ đã hết hạn, được gia hạn hợp lệ hay đã được khắc phục như thế nào.

Một email viết “đồng ý cho tiếp tục” thường không đủ để trả lời các câu hỏi trên. Ngược lại, một hồ sơ rất dài nhưng không liên kết được với tài sản, quyết định phê duyệt và bằng chứng vận hành cũng khó kiểm chứng.

Trong bài này, mọi mã tài sản, thời gian, ngưỡng và mẫu hồ sơ đều là ví dụ thiết kế nội bộ. Chúng không đại diện cho yêu cầu bắt buộc của một tiêu chuẩn hoặc văn bản pháp luật cụ thể.

## 2. Phân biệt ngoại lệ với những tình huống gần giống

### 2.1. Ngoại lệ không làm thay đổi chính sách gốc

Giả sử chính sách yêu cầu mọi credential quản trị phải được luân chuyển sau mỗi lần sử dụng. Một thiết bị cũ chưa hỗ trợ cơ chế này được duyệt dùng quy trình thay đổi mật khẩu thủ công trong ba mươi ngày.

Chính sách gốc vẫn có hiệu lực. Quyết định ngoại lệ chỉ áp dụng cho thiết bị, tài khoản, thời gian và điều kiện được ghi trong hồ sơ. Các thiết bị cùng loại khác không tự động được hưởng ngoại lệ.

Khi một ngoại lệ phải gia hạn liên tục hoặc áp dụng cho phần lớn tài sản, tổ chức cần đánh giá lại thiết kế kiểm soát, năng lực triển khai hoặc chính sách. Việc đánh giá đó là một quyết định riêng, không được ngầm thực hiện bằng cách mở rộng hồ sơ ngoại lệ.

### 2.2. Ngoại lệ, chấp nhận rủi ro và kiểm soát bù

| Khái niệm | Câu hỏi chính | Bằng chứng điển hình |
| --- | --- | --- |
| Ngoại lệ chính sách | Được phép sai lệch yêu cầu nào, ở đâu và đến bao giờ? | Phạm vi, điều kiện, phê duyệt, thời hạn |
| Chấp nhận rủi ro | Ai chịu trách nhiệm đối với phần rủi ro còn lại? | Quyết định của người có thẩm quyền và căn cứ đánh giá |
| Kiểm soát bù | Biện pháp nào hạn chế rủi ro khi chưa đáp ứng kiểm soát gốc? | Cấu hình, thử nghiệm, log vận hành, kết quả rà soát |
| Kế hoạch khắc phục | Làm thế nào đưa đối tượng về trạng thái phù hợp? | Mốc công việc, người thực hiện, tiêu chí nghiệm thu |
| Bằng chứng tuân thủ | Căn cứ nào cho phép kiểm tra việc áp dụng các yêu cầu và quyết định? | Hồ sơ có nguồn gốc, dấu thời gian, liên kết và khả năng truy xuất |

Phê duyệt ngoại lệ không chứng minh rằng kiểm soát bù đã hoạt động. Một kế hoạch cài đặt giám sát cũng không chứng minh rằng giám sát đã được triển khai. Mỗi loại khẳng định cần bằng chứng phù hợp.

### 2.3. Break-glass không mặc nhiên là ngoại lệ

Break-glass là cơ chế truy cập khẩn cấp đã được thiết kế và phê duyệt trước, có điều kiện kích hoạt và hậu kiểm. Nếu cơ chế này được chính sách cho phép và được sử dụng đúng điều kiện, một lần sử dụng break-glass không nhất thiết là ngoại lệ chính sách.

Nếu nhóm vận hành bỏ qua điều kiện bắt buộc, chẳng hạn dùng tài khoản khẩn cấp cho công việc thường ngày hoặc không thực hiện hậu kiểm, đó có thể là vi phạm cần xử lý. Không được hợp thức hóa bằng cách đặt tên sự kiện thành “ngoại lệ”.

## 3. Bắt đầu hồ sơ từ yêu cầu và phạm vi sai lệch

Một hồ sơ ngoại lệ PAM nên bắt đầu bằng ba lớp định danh.

### 3.1. Định danh yêu cầu

Ghi mã chính sách, phiên bản và điều khoản cụ thể. Nếu chỉ ghi tên “PAM Policy”, người kiểm tra không biết nội dung nào có hiệu lực tại thời điểm phê duyệt.

Ví dụ:

> Chính sách PAM nội bộ, phiên bản 3.2, điều khoản ROT-04: credential quản trị được quản lý phải được luân chuyển tự động theo sự kiện checkout/check-in đã cấu hình.

Cần lưu hoặc tham chiếu được phiên bản chính sách đã dùng để ra quyết định. Nếu chính sách thay đổi trong khi ngoại lệ còn hiệu lực, người sở hữu hồ sơ cần đánh giá tác động; không âm thầm thay căn cứ ban đầu bằng phiên bản mới.

### 3.2. Định danh đối tượng

Phạm vi phải đủ cụ thể để có thể đối chiếu với kiểm kê và log:

- Mã tài sản, môi trường và chủ sở hữu.
- Mã tài khoản đặc quyền hoặc đối tượng credential trong vault.
- Nhóm người được phép sử dụng.
- Loại thao tác được phép.
- Đường truy cập hoặc điểm trung chuyển liên quan.
- Các đối tượng và hành vi bị loại trừ.

Với tài khoản dùng chung, hồ sơ cần giải thích cách gắn từng lần sử dụng với người thật. Việc chỉ biết tên tài khoản đích không đủ để xác định ai đã thao tác.

Một tài khoản dịch vụ có thể cần bằng chứng khác với tài khoản người dùng: workload nào sử dụng, deployment nào đang chạy, nơi cấp credential, quyền được cấp và cách thu hồi quyền. Không nên ép mọi ngoại lệ vào một mẫu chỉ dành cho phiên đăng nhập của con người.

### 3.3. Mô tả đúng khoảng trống

Mô tả “thiết bị không hỗ trợ PAM” quá rộng. Có thể thiết bị chỉ không hỗ trợ một cơ chế đổi mật khẩu, trong khi vẫn hỗ trợ truy cập qua bastion và gửi log.

Một mô tả có thể kiểm chứng là:

> Hai tài khoản quản trị trên ba thiết bị mạng thuộc danh sách đính kèm chưa thể luân chuyển tự động bằng connector hiện tại. Truy cập qua bastion, xác thực cá nhân tại bastion và thu thập log vẫn bắt buộc. Ngoại lệ không cho phép đăng nhập trực tiếp từ máy trạm.

Cách viết này giữ nguyên những yêu cầu vẫn phải đáp ứng và ngăn người đọc hiểu ngoại lệ thành quyền miễn trừ toàn bộ PAM.

## 4. Cấu trúc một bộ hồ sơ bằng chứng

Một bộ hồ sơ có thể được tổ chức thành các thành phần sau. Không bắt buộc tất cả nằm trong một hệ thống, nhưng phải có liên kết ổn định và quyền truy cập phù hợp.

| Thành phần | Nội dung tối thiểu cần kiểm tra | Sai sót thường gặp |
| --- | --- | --- |
| Hồ sơ chính | Mã ngoại lệ, yêu cầu, phạm vi, lý do, thời hạn, trạng thái | Không có tài sản hoặc tài khoản cụ thể |
| Đánh giá rủi ro | Kịch bản lạm dụng, ảnh hưởng, kiểm soát hiện có, rủi ro còn lại | Chỉ ghi nhãn “thấp” mà không có căn cứ |
| Quyết định | Người phê duyệt, vai trò, nội dung quyết định, thời điểm, điều kiện | Người yêu cầu tự duyệt |
| Kiểm soát bù | Cách triển khai, người vận hành, cách kiểm tra, phản ứng khi lỗi | Chỉ có kế hoạch hoặc ảnh chụp cấu hình |
| Bằng chứng sử dụng | Request, checkout, phiên, thay đổi, log đích, rà soát | Các bản ghi không có khóa liên kết |
| Kế hoạch khắc phục | Công việc, chủ sở hữu, mốc, phụ thuộc, tiêu chí đóng | “Sẽ nâng cấp khi có ngân sách” |
| Rà soát và kết thúc | Kết quả review, gia hạn hoặc đóng, xác minh thu hồi | Đổi trạng thái thành closed mà không kiểm tra |

Có thể dùng một bản kê bằng chứng để ghi rõ mỗi tệp hoặc bản ghi hỗ trợ cho khẳng định nào. Nhờ đó, hồ sơ không biến thành một thư mục chứa nhiều tệp nhưng không rõ mục đích.

## 5. Xây dựng căn cứ rủi ro có thể kiểm tra

### 5.1. Dùng kịch bản cụ thể

Ví dụ với credential chưa luân chuyển tự động:

1. Một người đã từng sử dụng tài khoản có thể tiếp tục biết credential cũ.
2. Nếu có đường truy cập ngoài bastion, người đó có thể đăng nhập mà không đi qua quy trình cấp quyền.
3. Nếu log đích không đầy đủ, tổ chức khó gắn hành vi với một cá nhân.
4. Tài khoản có quyền rộng có thể làm thay đổi cấu hình hoặc gây gián đoạn dịch vụ.

Từ kịch bản này, kiểm soát bù có thể gồm giới hạn đường mạng, thay credential thủ công theo sự kiện, giới hạn người sử dụng, gắn người dùng với checkout và rà soát log. Mỗi biện pháp phải giải quyết một phần cụ thể của kịch bản.

### 5.2. Đừng nhầm phát hiện với ngăn chặn

Ghi hình phiên và cảnh báo hành vi có thể hỗ trợ phát hiện và điều tra. Chúng không tự ngăn người dùng biết mật khẩu tiếp tục dùng đường truy cập khác.

Tương tự, yêu cầu hai người phê duyệt không tự giảm quyền của tài khoản đích. Nếu rủi ro xuất phát từ quyền quá rộng, cần xem xét giới hạn lệnh, tách tài khoản, phân vùng hoặc biện pháp khác phù hợp với khả năng hệ thống.

Hồ sơ cần nêu phần rủi ro mà kiểm soát bù chưa xử lý. Người phê duyệt chấp nhận phần còn lại dựa trên thông tin đó, không dựa trên danh sách kiểm soát chỉ có tên.

### 5.3. Ghi cả phương án đã loại bỏ

Lý do kinh doanh nên giải thích vì sao không thể đáp ứng yêu cầu ngay, cùng các phương án đã cân nhắc:

- Tạm ngừng truy cập đặc quyền.
- Thay hệ thống hoặc nâng cấp firmware.
- Dùng tài khoản có quyền hẹp hơn.
- Chuyển thao tác sang một quy trình có kiểm soát khác.
- Thu hẹp phạm vi ngoại lệ.

Không cần biến hồ sơ thành tài liệu mua sắm. Mục đích là cho thấy quyết định không được đưa ra chỉ vì “làm như cũ thuận tiện hơn”.

## 6. Phê duyệt phải có thẩm quyền, điều kiện và thời gian

### 6.1. Tách các vai trò

Một mô hình nội bộ có thể phân công:

- **Người yêu cầu:** mô tả nhu cầu và cung cấp thông tin.
- **Chủ tài sản hoặc chủ dịch vụ:** xác nhận tác động và nhu cầu vận hành.
- **Nhóm an ninh hoặc kiểm soát:** đánh giá khoảng trống, kiểm soát bù và bằng chứng.
- **Người có thẩm quyền chấp nhận rủi ro:** quyết định có cho phép ngoại lệ hay không.
- **Người triển khai và người rà soát:** vận hành, kiểm tra điều kiện đã duyệt.

Một người có thể đảm nhiệm nhiều vai trò nếu cơ chế quản trị cho phép, nhưng cần nhận diện xung đột lợi ích. Người quản trị kỹ thuật không mặc nhiên có thẩm quyền chấp nhận rủi ro cho toàn bộ dịch vụ.

### 6.2. Quyết định phải gắn với nội dung đã duyệt

Bằng chứng quyết định nên thể hiện:

- Danh tính người quyết định và vai trò tại thời điểm duyệt.
- Phiên bản hoặc bản chụp hồ sơ được duyệt.
- Quyết định chấp thuận, từ chối hoặc yêu cầu bổ sung.
- Điều kiện có hiệu lực.
- Thời điểm bắt đầu và hết hạn, kèm múi giờ hoặc offset.
- Những thay đổi nào bắt buộc phải đánh giá lại.

Nếu phạm vi hồ sơ được sửa sau phê duyệt, bản phê duyệt cũ không tự áp dụng cho phạm vi mới. Cần lưu lịch sử và tạo quyết định bổ sung hoặc phiên bản mới theo quy trình.

### 6.3. Không phê duyệt lùi để che khoảng trống

Giả sử truy cập xảy ra lúc 08:00 nhưng ngoại lệ được phê duyệt lúc 10:00. Hồ sơ phải giữ đúng hai mốc này. Không chỉnh thời điểm phê duyệt về trước để làm cho truy cập trông hợp lệ.

Nếu đã có cơ chế khẩn cấp được phê duyệt từ trước, ghi nhận căn cứ kích hoạt cơ chế đó và thực hiện hậu kiểm. Nếu không có, cần ghi nhận sai lệch đã xảy ra và xử lý theo quy trình phù hợp. Ngoại lệ cho hoạt động tương lai không xóa lịch sử vi phạm.

## 7. Chứng minh kiểm soát bù thực sự hoạt động

Một cách hữu ích là tách ba lớp bằng chứng:

1. **Thiết kế:** mô tả kiểm soát dự kiến làm gì.
2. **Triển khai:** chứng minh kiểm soát đã được cấu hình cho đúng đối tượng.
3. **Vận hành:** chứng minh kiểm soát hoạt động trong khoảng thời gian ngoại lệ.

Ví dụ:

| Kiểm soát bù | Bằng chứng triển khai | Bằng chứng vận hành |
| --- | --- | --- |
| Chỉ truy cập từ bastion | Rule mạng và ánh xạ tài sản | Kết quả kiểm tra đường truy cập, log kết nối, rà soát rule |
| Checkout gắn với người thật | Cấu hình xác thực và workflow | Request ID, người checkout, thời điểm, session ID |
| Thay credential thủ công sau sử dụng | Runbook và phân công | Job hoặc ticket hoàn tất, xác minh dùng credential mới, không lưu giá trị bí mật |
| Rà soát phiên có rủi ro | Tiêu chí chọn phiên và người review | Danh sách phiên, kết luận, thời điểm, xử lý phát hiện |
| Cảnh báo truy cập ngoài cửa sổ | Rule cảnh báo và nguồn sự kiện | Kết quả thử cảnh báo, sự kiện thực tế, ticket xử lý |

Ảnh chụp cấu hình có thể hỗ trợ chứng minh triển khai tại một thời điểm. Nó thường không đủ để chứng minh kiểm soát hoạt động suốt một tháng. Bằng chứng vận hành cần bao phủ thời gian và phạm vi tương ứng với khẳng định.

Nếu một kiểm soát chưa có sự kiện thực tế, có thể dùng kiểm tra được phép để chứng minh một phần khả năng hoạt động. Phải ghi rõ đó là bằng chứng thử nghiệm, không trình bày thành hoạt động sản xuất đã xảy ra.

## 8. Liên kết bằng chứng từ quyết định đến từng lần truy cập

Một chuỗi liên kết có thể đi theo hướng:

```text
Mã ngoại lệ + phiên bản
    -> Request được duyệt trong phạm vi
    -> Danh tính cá nhân hoặc workload
    -> Checkout / quyền JIT / lần cấp credential
    -> Phiên truy cập hoặc hoạt động tại hệ thống đích
    -> Thay đổi thực hiện và kết quả rà soát
    -> Thu hồi quyền / thay credential / đóng request
```

### 8.1. Chọn khóa liên kết phù hợp

Nếu các hệ thống hỗ trợ, dùng các mã như:

- `exception_id` và `exception_version`.
- `access_request_id`.
- `asset_id`, `privileged_account_id`.
- `session_id` hoặc `credential_checkout_id`.
- `change_id`, `review_id`.

Không phải thiết bị nào cũng lưu được mã ngoại lệ trong log. Khi đó, cần có bảng ánh xạ đáng tin cậy giữa request, tài sản, danh tính, khoảng thời gian và session. Chỉ đối chiếu gần đúng theo giờ có thể không đủ nếu có nhiều người sử dụng đồng thời.

### 8.2. Chuẩn hóa ý nghĩa thời gian

Nên lưu timestamp có offset rõ ràng hoặc chuẩn hóa về UTC theo thiết kế của hệ thống. Khi hiển thị giờ địa phương, giữ khả năng quy đổi lại.

Đồng thời, phân biệt:

- Thời điểm sự kiện xảy ra.
- Thời điểm hệ thống thu thập nhận được sự kiện.
- Thời điểm người rà soát đưa ra kết luận.

Nếu nguồn bị lệch đồng hồ hoặc mất kết nối, ghi nhận sai lệch và giới hạn của phép đối chiếu. Không chỉnh sửa log gốc để làm cho chuỗi thời gian “đẹp” hơn.

### 8.3. Không coi sự thiếu log là bằng chứng không có truy cập

Một truy vấn không trả kết quả có thể do không có sự kiện, nhưng cũng có thể do sai bộ lọc, nguồn chưa gửi log, thời gian chưa đúng hoặc dữ liệu đã hết thời hạn lưu.

Khi báo “không phát hiện truy cập ngoài phạm vi”, nên nêu nguồn đã kiểm tra, khoảng thời gian, bộ lọc, tình trạng thu thập và giới hạn bao phủ. Khẳng định cần tương xứng với dữ liệu thực có.

## 9. Bảo vệ bằng chứng mà không phát tán secret

Hồ sơ ngoại lệ PAM có thể chứa thông tin nhạy cảm về tài sản, đường truy cập, quyền quản trị và sự kiện điều tra. Nó cần được quản lý quyền đọc và ghi riêng.

### 9.1. Không đưa credential vào bằng chứng

Không lưu mật khẩu, private key, access token hoặc recovery code trong ticket, ảnh chụp, tệp đính kèm hay ví dụ log.

Để chứng minh luân chuyển credential, thường có thể dùng:

- Mã đối tượng credential trong vault.
- Mã job luân chuyển và trạng thái.
- Thời điểm thực hiện.
- Danh tính thực hiện hoặc dịch vụ thực hiện.
- Kết quả kiểm tra theo quy trình.
- Liên kết với lần checkout và lần thu hồi liên quan.

Các thông tin này chứng minh quy trình mà không cần tiết lộ giá trị secret. Cần kiểm tra cả log lỗi và bản xuất cấu hình vì chúng có thể vô tình chứa dữ liệu bí mật.

### 9.2. Bản gốc, bản xuất và bản đã che dữ liệu

Nếu cần chia sẻ cho người kiểm tra, có thể tạo bản đã che dữ liệu theo quy trình. Bản này cần ghi rõ:

- Nguồn dữ liệu và người xuất.
- Thời điểm xuất.
- Những loại thông tin đã được che.
- Mã liên kết với bản gốc được bảo vệ.
- Cách người có thẩm quyền yêu cầu kiểm tra sâu hơn.

Không chỉnh sửa bản gốc để phục vụ việc chia sẻ. Một bản đã che quá nhiều đến mức mất mã tài sản, thời gian hoặc kết quả có thể không còn đủ sức hỗ trợ khẳng định cần kiểm tra.

### 9.3. Toàn vẹn và nguồn gốc

Có thể ghi checksum của tệp xuất vào bản kê để phát hiện thay đổi byte sau khi thu thập. Tuy nhiên, một checksum đặt cạnh tệp trong thư mục mà cùng một người có thể sửa cả hai không tự chứng minh ai đã tạo tệp, lúc nào, hay nội dung nguồn có chính xác hay không.

Cần kết hợp các yếu tố phù hợp với hệ thống: nhật ký xuất dữ liệu, kiểm soát truy cập, lịch sử thay đổi, kho lưu trữ có chính sách bảo vệ, dấu thời gian hoặc cơ chế ký nếu được triển khai. Chỉ ghi nhận các tính năng thực tế đang có.

### 9.4. Thời hạn lưu bằng chứng khác thời hạn ngoại lệ

Ngoại lệ hết hiệu lực không có nghĩa được xóa ngay toàn bộ hồ sơ. Thời hạn lưu cần được xác định theo chính sách dữ liệu, nhu cầu kiểm toán, điều tra và các yêu cầu áp dụng của tổ chức.

Nếu có yêu cầu bảo toàn phục vụ điều tra hoặc tranh chấp, xử lý theo cơ chế giữ dữ liệu có thẩm quyền. Không tự đặt một số năm lưu chung cho mọi nguồn log và mọi hồ sơ.

## 10. Ví dụ hồ sơ cho thiết bị chưa luân chuyển tự động

Giả sử một nhóm vận hành cần bảo trì ba thiết bị mạng. Connector hiện tại chưa đổi mật khẩu tự động ổn định. Nhóm đề nghị ngoại lệ có thời hạn trong khi hoàn tất nâng cấp.

Mẫu YAML dưới đây chỉ minh họa cấu trúc hồ sơ nghiệp vụ; nó không phải schema bắt buộc của nền tảng PAM hoặc file metadata bài học.

```yaml
exception:
  id: PAM-EX-2026-027
  version: 1
  title: Tam thoi luan chuyen thu cong credential thiet bi mang
  policy:
    id: PAM-POLICY
    version: "3.2"
    clause: ROT-04
  scope:
    environment: production
    asset_ids:
      - NET-EDGE-021
      - NET-EDGE-022
      - NET-EDGE-023
    privileged_account_ids:
      - VAULT-OBJ-621
      - VAULT-OBJ-622
    allowed_access_path: BASTION-NET-01
    allowed_activity: Bao tri theo change da duyet
    excluded_activity:
      - Dang nhap truc tiep tu may tram
      - Sao chep credential ra ngoai vault
  deviation:
    unmet_requirement: Luan chuyen credential tu dong theo su kien
    reason: Connector hien tai chua dap ung kiem thu voi firmware dang dung
  validity:
    starts_at: "2026-12-01T08:00:00+07:00"
    expires_at: "2026-12-31T18:00:00+07:00"
  compensating_controls:
    - id: CC-01
      description: Chi cho phep duong truy cap qua bastion
      owner_role: Network Operations
      evidence_refs:
        - EVD-101
        - EVD-102
    - id: CC-02
      description: Thay credential thu cong sau moi lan su dung
      owner_role: PAM Operations
      evidence_refs:
        - EVD-103
    - id: CC-03
      description: Ra soat cac phien thuoc ngoai le
      owner_role: Security Review
      evidence_refs:
        - EVD-104
  residual_risk:
    statement: Credential co the bi biet trong khoang truoc khi thay thu cong
    acceptance_decision_ref: DEC-2026-118
  remediation:
    owner_role: PAM Engineering
    work_item: CHG-2026-921
    target_date: "2026-12-28"
    acceptance_criteria:
      - Connector duoc kiem thu thanh cong tren pham vi duoc duyet
      - Credential duoc luan chuyen va xac minh theo quy trinh
      - Tai khoan va quyen tam thoi duoc thu hoi
  governance:
    record_status: APPROVED
    approval_ref: DEC-2026-118
    review_due_at: "2026-12-15T17:00:00+07:00"
    renewal_is_automatic: false
```

Trong hệ thống thực, phải có ánh xạ rõ tài khoản nào tồn tại trên tài sản nào. Hai danh sách tài sản và tài khoản độc lập trong bản tóm tắt không được thay thế bản kiểm kê quan hệ chi tiết.

### 10.1. Bản kê bằng chứng đi kèm

| Mã | Khẳng định được hỗ trợ | Nguồn và nội dung cần giữ |
| --- | --- | --- |
| EVD-100 | Khoảng trống connector đã được xác nhận | Kết quả kiểm thử, phiên bản connector và firmware, tài sản thử |
| EVD-101 | Đường truy cập được giới hạn | Bản xuất rule mạng, phạm vi áp dụng, thời điểm và change ID |
| EVD-102 | Giới hạn mạng hoạt động | Kết quả kiểm tra được phép từ nguồn hợp lệ và nguồn bị chặn |
| EVD-103 | Credential được thay sau sử dụng | Request, checkout, job hoặc ticket thay credential, kết quả xác minh |
| EVD-104 | Phiên đã được rà soát | Session ID, người review, kết luận, phát hiện và ticket xử lý |
| EVD-105 | Quyết định được phê duyệt đúng phạm vi | Bản quyết định gắn với phiên bản 1 của hồ sơ |
| EVD-106 | Ngoại lệ đủ điều kiện đóng | Kết quả nghiệm thu nâng cấp, luân chuyển và thu hồi quyền tạm |

Đối với EVD-103 và EVD-104, thường sẽ có nhiều bản ghi phát sinh trong suốt thời gian ngoại lệ. Không nên dùng một bản ghi đầu tháng để đại diện cho mọi lần sử dụng cả tháng nếu chưa có cơ sở.

### 10.2. Một lần truy cập hợp lệ được chứng minh thế nào?

Giả sử request `AR-7621` được duyệt cho người vận hành bảo trì `NET-EDGE-021` theo change `CHG-2026-930`.

Bộ bằng chứng cần cho thấy:

1. Ngoại lệ đang hiệu lực và bao phủ đúng tài sản, tài khoản, hoạt động.
2. Request được duyệt theo điều kiện đã đặt ra.
3. Danh tính cá nhân được gắn với checkout `CO-4418` và session `SES-9912`.
4. Hoạt động đi qua đường truy cập cho phép.
5. Phiên và log đích được thu thập trong khả năng của hệ thống.
6. Credential được thay theo điều kiện ngoại lệ và có kết quả xác minh.
7. Rà soát phiên được hoàn tất, các phát hiện có kết luận hoặc đầu việc xử lý.

Nếu một trong những điểm trên không có bằng chứng, hồ sơ cần phản ánh khoảng trống đó. Không suy diễn từ việc ticket đã đóng rằng mọi điều kiện kỹ thuật đều đã đạt.

## 11. Rà soát định kỳ, hết hạn và gia hạn

### 11.1. Rà soát phải kiểm tra cả thay đổi trong thực tế

Trong thời gian ngoại lệ, người sở hữu cần xem xét:

- Tài sản và tài khoản có còn đúng phạm vi không.
- Người được phép truy cập có thay đổi không.
- Kiểm soát bù có bị tắt, lỗi hoặc mất nguồn dữ liệu không.
- Có sự kiện ngoài phạm vi hay phát hiện mới không.
- Kế hoạch khắc phục có tiến triển đúng mốc không.
- Rủi ro còn lại có thay đổi do môi trường, quyền hoặc mối đe dọa không.

Tần suất review nên dựa trên rủi ro và điều kiện phê duyệt. Không có một chu kỳ cố định phù hợp cho mọi ngoại lệ.

### 11.2. Trạng thái lưu trong ticket chưa chắc phản ánh hiệu lực

Một ticket vẫn có nhãn `APPROVED` sau thời điểm hết hạn không có nghĩa ngoại lệ còn hiệu lực.

Có thể mô hình hóa điều kiện hiệu lực:

```text
Ngoai le duoc phep su dung khi:
  co quyet dinh chap thuan hop le
  VA thoi diem hien tai nam trong khoang hieu luc
  VA doi tuong va hoat dong nam trong pham vi
  VA cac dieu kien bat buoc dang duoc dap ung
  VA quyet dinh chua bi thu hoi
```

Điều kiện này là logic kiểm soát cần được thực thi hoặc kiểm tra. Một trường trạng thái trong công cụ quản lý công việc chỉ là một phần dữ liệu.

Khi hết hạn, tổ chức cần thực hiện hành động đã định trước như chặn cấp request mới, thu hồi quyền tạm hoặc chuyển sang cơ chế xử lý được phê duyệt. Nếu nền tảng không tự động hóa được, phải có trách nhiệm vận hành và bằng chứng thực hiện thủ công.

### 11.3. Gia hạn là một quyết định mới

Gia hạn cần đánh giá lại lý do chưa khắc phục, phạm vi hiện tại, kết quả vận hành kiểm soát bù, sự kiện đã xảy ra và rủi ro còn lại.

Giữ thời hạn cũ và quyết định cũ trong lịch sử. Không thay ngày hết hạn rồi để người xem hiểu rằng thời hạn dài hơn đã được duyệt từ đầu.

Một lần gia hạn có thể gắn với phiên bản mới hoặc quyết định bổ sung. Dù dùng cách nào, phải truy được ngoại lệ đã hợp lệ trong những khoảng nào và theo những điều kiện nào.

## 12. Khi kiểm soát bù thất bại

Giả sử hệ thống ghi phiên dừng hoạt động, trong khi ghi phiên là điều kiện bắt buộc để sử dụng ngoại lệ.

Người vận hành cần:

1. Ghi nhận thời điểm phát hiện, phạm vi ảnh hưởng và nguồn dữ liệu bị thiếu.
2. Thực hiện hành động theo điều kiện đã duyệt, chẳng hạn tạm ngừng cấp phiên mới hoặc kích hoạt phương án thay thế đã được phê duyệt.
3. Xác định các hoạt động diễn ra trong khoảng thiếu bằng chứng.
4. Bảo toàn nguồn thay thế nếu có, như log bastion, log đích, request và change record.
5. Thông báo đúng vai trò có trách nhiệm, đánh giá rủi ro và xử lý sự cố nếu cần.
6. Xác minh khôi phục và ghi rõ giới hạn của dữ liệu còn thiếu.

Không được tự đặt một biện pháp thay thế sau sự kiện rồi coi nó như điều kiện đã được duyệt từ đầu. Nguồn log thay thế có thể hỗ trợ điều tra nhưng không tự biến khoảng mất ghi phiên thành trạng thái tuân thủ đầy đủ.

Hồ sơ tốt cho phép người kiểm tra thấy cả sự thất bại và cách tổ chức phản ứng. Việc che khoảng trống làm suy yếu khả năng đánh giá thực tế.

## 13. Đóng ngoại lệ bằng kết quả khắc phục

Trước khi đóng, cần đối chiếu với tiêu chí nghiệm thu ban đầu hoặc tiêu chí thay đổi đã được duyệt.

Với ví dụ connector, bộ bằng chứng đóng có thể gồm:

- Phiên bản và cấu hình đã triển khai theo change.
- Kết quả kiểm thử connector trên đúng phạm vi.
- Kết quả luân chuyển và xác minh credential.
- Kiểm tra các đường truy cập không được phép.
- Bằng chứng thu hồi quyền và tài khoản tạm.
- Đánh giá những điều kiện nào vẫn cần duy trì.
- Người xác nhận, thời điểm và liên kết với hồ sơ ngoại lệ.

Không xóa kiểm soát bù ngay sau khi một lần thử thành công nếu chưa xác định điều kiện chuyển đổi an toàn. Một số biện pháp như giới hạn mạng hoặc rà soát quyền có thể tiếp tục là kiểm soát thông thường sau khi ngoại lệ kết thúc.

Nếu chỉ một phần tài sản được khắc phục, ghi nhận phần đã hoàn thành và giữ rõ phạm vi còn mở. Không đóng toàn bộ hồ sơ rồi để các tài sản còn lại tiếp tục sai lệch mà không có quyết định hợp lệ.

## 14. Chuẩn bị bộ bằng chứng cho người kiểm tra

Một bộ hồ sơ dễ sử dụng cần cho phép người đọc đi từ quyết định đến sự kiện và quay ngược lại.

Có thể chuẩn bị:

1. Bản tóm tắt phạm vi, yêu cầu, khoảng thời gian và kết quả cuối cùng.
2. Hồ sơ ngoại lệ cùng lịch sử phiên bản.
3. Quyết định phê duyệt và căn cứ thẩm quyền.
4. Đánh giá rủi ro và kiểm soát bù.
5. Bản kê bằng chứng có liên kết tới nguồn được bảo vệ.
6. Tập các lần truy cập được lựa chọn theo phương pháp có giải thích.
7. Bằng chứng review, gia hạn hoặc đóng.
8. Những khoảng dữ liệu thiếu và cách xử lý.

Nếu dùng lấy mẫu, cần ghi tiêu chí chọn mẫu và giới hạn của kết luận. Một số phiên được chọn không tự chứng minh mọi phiên trong tổng thể đều đáp ứng yêu cầu.

Bộ hồ sơ cũng cần có thể truy xuất bằng quyền của người kiểm tra được cấp. Một danh sách liên kết mà tất cả đều lỗi, hết hạn hoặc chỉ người lập hồ sơ đọc được sẽ gây gián đoạn việc xác minh.

## 15. Các lỗi thường gặp và cách sửa

### Chỉ có phê duyệt, không có bằng chứng vận hành

**Vấn đề:** Hồ sơ cho thấy người có thẩm quyền đồng ý nhưng không cho thấy điều kiện đi kèm được thực hiện.

**Cách sửa:** Liên kết kiểm soát bù với cấu hình, lần kiểm tra, hoạt động sử dụng và kết quả review theo đúng thời gian ngoại lệ.

### Phạm vi mô tả bằng tên nhóm quá rộng

**Vấn đề:** “Các máy chủ Linux” không cho phép xác định tài sản nào được duyệt và tài sản nào ngoài phạm vi.

**Cách sửa:** Dùng mã kiểm kê ổn định hoặc một tập phạm vi được định nghĩa, chốt phiên bản và lưu lịch sử thành viên. Việc thêm tài sản phải theo cơ chế đánh giá thay đổi được duyệt.

### Đưa secret vào ảnh hoặc tệp đính kèm

**Vấn đề:** Hồ sơ bằng chứng trở thành nơi phát tán credential.

**Cách sửa:** Dùng mã tham chiếu, trạng thái job và kết quả xác minh. Xử lý việc lộ secret theo quy trình thích hợp nếu đã xảy ra; chỉ che ảnh về sau không làm mất rủi ro đã phát sinh.

### Gia hạn bằng cách sửa ngày

**Vấn đề:** Mất dấu quyết định và không xác định được khoảng nào từng hết hiệu lực.

**Cách sửa:** Lưu phiên bản, quyết định mới, thời điểm và căn cứ đánh giá lại.

### Đồng nhất “không thấy sự kiện” với “không có sự kiện”

**Vấn đề:** Có thể bỏ qua lỗi thu thập, phạm vi truy vấn hoặc dữ liệu đã bị xóa theo chu kỳ.

**Cách sửa:** Ghi rõ độ bao phủ và tình trạng nguồn, kiểm tra phép truy vấn, mô tả giới hạn kết luận.

### Đóng ticket thay cho nghiệm thu

**Vấn đề:** Trạng thái công việc không chứng minh khoảng trống PAM đã được khắc phục.

**Cách sửa:** Đối chiếu từng tiêu chí đóng và lưu bằng chứng kỹ thuật cùng người xác nhận.

## 16. Bài tập thực hành

### Tình huống

Một nhóm hỗ trợ nhà cung cấp cần dùng tài khoản quản trị dùng chung trong hai tuần. Hệ thống đích chưa hỗ trợ danh tính cá nhân. Truy cập có thể đi qua bastion, nhưng đường quản trị trực tiếp vẫn đang mở trong mạng nội bộ. Nhóm đề nghị dùng ghi phiên làm kiểm soát bù duy nhất.

### Yêu cầu

1. Xác định điều khoản chính sách bị sai lệch và các yêu cầu vẫn phải giữ.
2. Lập phạm vi tài sản, tài khoản, người sử dụng và thao tác.
3. Nêu một kịch bản lạm dụng mà ghi phiên trên bastion chưa bao phủ.
4. Đề xuất kiểm soát bù và bằng chứng cho từng biện pháp.
5. Thiết kế khóa liên kết từ ngoại lệ đến request, người dùng và phiên.
6. Xác định điều kiện hiệu lực, điều kiện tạm ngừng và tiêu chí đóng.
7. Nêu cách chia sẻ bằng chứng mà không lộ credential.

### Gợi ý triển khai

Điểm cần nhận ra là người dùng có thể tránh bastion bằng đường quản trị trực tiếp. Vì vậy, chỉ ghi phiên tại bastion chưa đủ xử lý rủi ro bỏ qua điểm kiểm soát.

Một hồ sơ có căn cứ cần xem xét giới hạn đường truy cập, ánh xạ người thật với từng lần dùng tài khoản, giới hạn cửa sổ và hoạt động, thu hồi truy cập nhà cung cấp khi kết thúc, thay credential theo điều kiện đã duyệt và kiểm tra các hành động đó.

Nếu không thể triển khai biện pháp cần thiết, phải mô tả phần rủi ro còn lại để người có thẩm quyền quyết định. Không tự ghi kiểm soát “đã đáp ứng” chỉ vì có thể tạo một ticket hoặc một video.

## 17. Các câu hỏi tự kiểm tra

- Người độc lập có xác định được chính xác yêu cầu nào đang được ngoại lệ không?
- Có thể liệt kê tài sản, tài khoản và người sử dụng thuộc phạm vi tại một thời điểm quá khứ không?
- Quyết định phê duyệt gắn với phiên bản hồ sơ nào?
- Bằng chứng nào chứng minh từng kiểm soát bù đã hoạt động?
- Có thể nối một phiên truy cập cụ thể với ngoại lệ và request hợp lệ không?
- Ngoại lệ hết hạn thì hành động nào diễn ra, ai chịu trách nhiệm và kiểm tra ở đâu?
- Hồ sơ có chứa secret hoặc thông tin vượt nhu cầu của người nhận không?
- Bằng chứng đóng có chứng minh khoảng trống đã được khắc phục, hay chỉ chứng minh ticket đã đổi trạng thái?

Một bộ bằng chứng ngoại lệ PAM có giá trị khi nó hỗ trợ được các khẳng định cụ thể về quyết định, phạm vi, hoạt động và kết quả. Mục tiêu không phải tạo thêm giấy tờ mà là giữ được khả năng giải thích và kiểm chứng việc sử dụng quyền đặc biệt trong thời gian có sai lệch chính sách.
