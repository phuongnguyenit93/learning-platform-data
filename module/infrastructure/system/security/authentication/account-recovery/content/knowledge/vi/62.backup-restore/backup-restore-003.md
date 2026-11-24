# Backup access control — Kiểm soát truy cập bản sao lưu

## 1. Vì sao backup là một đường truy cập cần được bảo vệ riêng?

Một dịch vụ khôi phục tài khoản có thể lưu mật khẩu đã băm, metadata MFA, credential passkey phía máy chủ, bằng chứng xác minh danh tính, yêu cầu hỗ trợ và lịch sử quyết định. Nếu các dữ liệu đó xuất hiện trong backup, người có quyền đọc hoặc phục hồi backup có thể tiếp cận nhiều thông tin hơn một nhân viên hỗ trợ thông thường.

**Backup access control** là hệ thống phân quyền và kiểm soát các hành động đối với bản sao lưu: tạo, liệt kê, đọc, sao chép, giải mã, xuất dữ liệu, phục hồi và quản lý vòng đời. Nó phải bảo vệ cả nơi lưu backup lẫn đường đưa dữ liệu từ backup trở lại một môi trường có thể sử dụng.

Trong `SECURITY_AUTHENTICATION_ACCOUNT_RECOVERY`, kiểm soát này có hai mục tiêu gắn liền:

1. Backup không trở thành đường vòng để đọc dữ liệu hoặc tiếp quản tài khoản ngoài quy trình xác minh.
2. Việc phục hồi không làm sống lại phiên, token, yếu tố xác thực hoặc quyền đã mất hiệu lực sau thời điểm tạo backup.

Quyền “được hỗ trợ người dùng khôi phục tài khoản” không tự bao gồm quyền tải một bản sao toàn bộ cơ sở dữ liệu. Quyền quản lý hạ tầng lưu trữ cũng không nên mặc nhiên đồng nghĩa quyền đọc dữ liệu đã giải mã.

### Ví dụ mở đầu

Một người dùng mất điện thoại MFA. Nhân viên hỗ trợ đề nghị tải backup gần nhất để lấy thông tin tài khoản rồi phục hồi các hàng liên quan. Nếu hệ thống chỉ kiểm tra nhân viên có vai trò hỗ trợ, quy trình này có thể cho phép họ đọc dữ liệu của các tài khoản khác, khôi phục mã dự phòng đã dùng hoặc đưa một cấu hình MFA cũ trở lại hoạt động.

Luồng đúng cần xác định hành động cụ thể, phạm vi dữ liệu, môi trường đích, thẩm quyền và các điều kiện an toàn. Sự tồn tại của một bản sao không phải bằng chứng rằng người gọi được phép sử dụng nó.

## 2. Phân biệt khôi phục tài khoản với phục hồi backup

Khôi phục tài khoản là quy trình xác lập lại quyền truy cập của một chủ thể sau khi mất phương thức xác thực. Phục hồi backup là thao tác đưa dữ liệu từ một bản sao vào môi trường đích. Hai quy trình có thể liên quan nhưng không thay thế nhau.

| Tình huống | Căn cứ cần kiểm tra | Điều không được suy ra |
|---|---|---|
| Người dùng quên mật khẩu | Các điều kiện của luồng đặt lại mật khẩu | Người dùng được phép đọc backup |
| Người dùng mất MFA hoặc passkey | Xác minh danh tính và quyền khôi phục phù hợp | Được phục hồi mọi credential cũ |
| Dữ liệu bị xóa nhầm | Thẩm quyền yêu cầu, phạm vi dữ liệu và kế hoạch phục hồi | Người yêu cầu sở hữu mọi dữ liệu trong bản sao |
| Hệ thống bị sự cố | Thẩm quyền vận hành, nguồn backup và môi trường đích | Có thể mở lại toàn bộ quyền từ thời điểm backup |
| Điều tra chiếm đoạt tài khoản | Quyền điều tra và phạm vi truy xuất được duyệt | Người điều tra cần toàn quyền quản trị kho backup |

Một token đặt lại mật khẩu không phải thông tin xác thực quản trị backup. Ngược lại, một quyền phục hồi backup không chứng minh chủ thể đang yêu cầu đăng nhập là chủ tài khoản hợp pháp.

## 3. Tách các nhóm quyền thay vì dùng một vai trò toàn năng

Các hành động trên backup có rủi ro khác nhau. Có thể phân chia như sau:

| Nhóm quyền | Hành động điển hình | Rủi ro cần kiểm soát |
|---|---|---|
| Xem metadata | Xem thời điểm, trạng thái và phạm vi backup | Lộ cấu trúc hệ thống hoặc thông tin tenant |
| Tạo backup | Chạy tác vụ sao lưu từ nguồn đã xác định | Đọc nguồn quá rộng hoặc ghi bản sao ra nơi không được phép |
| Quản lý kho | Quản lý đối tượng và cấu hình lưu trữ | Sao chép, xóa hoặc thay đổi đường truy cập |
| Đọc nội dung mã hóa | Tải các đối tượng backup | Tạo bản sao ngoài kiểm soát; kết hợp với quyền khác để giải mã |
| Giải mã | Sử dụng khóa hoặc dịch vụ giải mã | Tiếp cận dữ liệu nhạy cảm dưới dạng rõ |
| Phục hồi vào vùng cách ly | Dựng dữ liệu để kiểm tra hoặc trích xuất có kiểm soát | Tạo thêm một môi trường chứa dữ liệu thật |
| Phục hồi vào môi trường hoạt động | Ghi dữ liệu vào hệ thống đang phục vụ | Thay đổi quyền, phiên, credential và dữ liệu người dùng |
| Quản lý vòng đời | Xóa, thay đổi hạn lưu hoặc cơ chế bảo vệ bản sao | Mất khả năng phục hồi hoặc giữ dữ liệu quá lâu |

Phân tách trên là mô hình thiết kế, không phải tên quyền của một sản phẩm cụ thể. Hệ thống triển khai cần ánh xạ sang các API và quyền thực tế.

Một dịch vụ tạo backup cần đọc dữ liệu nguồn trong phạm vi nhiệm vụ. Việc hạn chế nó không đọc hoặc giải mã các bản sao cũ chỉ giảm một đường truy cập, không làm mất rủi ro từ quyền đọc nguồn. Cần đánh giá cả hai phía.

Tương tự, tách quyền đọc backup và quyền giải mã chỉ hữu ích nếu một người không thể tự cấp cả hai, sửa chính sách khóa hoặc mạo danh dịch vụ có đủ quyền mà không bị kiểm soát.

## 4. Xác định tài nguyên và phạm vi của một quyền truy cập

Một quyền phục hồi nên được ràng buộc với những thuộc tính rõ ràng:

```text
operationId
requesterIdentity
approvedOperatorIdentity
backupId
backupObjectVersions
sourceEnvironment
sourceTenantScope
requestedDataset
destinationEnvironment
destinationTenantScope
allowedActions
approvedAt
expiresAt
approvalReferences
```

Ví dụ, phê duyệt “phục hồi dữ liệu hồ sơ của tài khoản A từ backup X vào vùng cách ly R” không được dùng để phục hồi toàn bộ tenant sang môi trường thử nghiệm T hoặc để tải backup X về máy cá nhân.

Môi trường đích là một phần của quyết định phân quyền. Một bản sao được bảo vệ tốt ở kho sản xuất vẫn có thể bị lộ nếu được phục hồi sang môi trường dùng tài khoản chung, ghi log quá nhiều hoặc cho phép truy cập Internet không phù hợp.

Định danh backup cần chỉ tới đúng phiên bản đối tượng hoặc tập đối tượng được phê duyệt. Nếu một alias như `latest` thay đổi sau khi duyệt, thao tác không nên âm thầm chuyển sang một bản sao khác có phạm vi hoặc thời điểm khác.

## 5. Nhận diện đường truy cập gián tiếp

Kiểm soát chỉ API tải tệp là chưa đủ. Dữ liệu có thể được tiếp cận qua nhiều đường khác:

- Tạo bản sao, bản xuất hoặc bản sao chéo vùng từ backup.
- Phục hồi một snapshot thành cơ sở dữ liệu mới rồi đọc từ cơ sở dữ liệu đó.
- Tạo liên kết tải xuống tạm thời hoặc chia sẻ backup cho một tài khoản khác.
- Gắn volume phục hồi vào máy do người gọi quản trị.
- Sử dụng tài khoản dịch vụ có quyền giải mã và quyền đọc kho.
- Thay đổi chính sách lưu trữ, chính sách khóa hoặc quyền mạo danh dịch vụ.
- Truy cập bản sao do một công cụ hỗ trợ hoặc tác vụ vận hành tạo ra.

Mỗi đường cần có kiểm soát theo cùng ranh giới dữ liệu. Không xem quyền `restore` là vô hại chỉ vì người đó không có quyền `download`; kết quả phục hồi có thể cho phép đọc cùng dữ liệu.

Ngay cả quyền liệt kê backup cũng cần xem xét. Tên đối tượng chứa email, số điện thoại hoặc định danh tenant có thể làm lộ thông tin dù nội dung đã mã hóa. Nên dùng định danh phù hợp và chỉ công bố metadata cần thiết.

## 6. Quyền tối thiểu và phân tách nhiệm vụ

Một thiết kế có thể tách các vai trò sau:

```text
Người yêu cầu phục hồi
    → nêu mục đích và phạm vi

Người phê duyệt
    → xác nhận thẩm quyền, dữ liệu và môi trường đích

Dịch vụ thực thi
    → nhận quyền tạm thời cho operation đã duyệt

Người kiểm tra kết quả
    → xác nhận phạm vi thực tế và điều kiện mở truy cập
```

Tùy mức rủi ro, một số vai trò có thể được kết hợp, nhưng xung đột quyền cần được xác định có chủ đích. Hành động phục hồi vào sản xuất hoặc xuất dữ liệu nhạy cảm có thể cần nhiều người phê duyệt độc lập.

Các tài khoản vận hành nên có danh tính riêng, không dùng một tài khoản chung khiến mọi thao tác đều mang tên “backup-admin”. Dịch vụ tự động cũng cần định danh riêng và quyền giới hạn theo nhiệm vụ.

Các thao tác nhạy cảm có thể yêu cầu xác thực tăng cường và quyền được cấp đúng lúc, tồn tại trong một khoảng thời gian ngắn. Thời hạn đó là giới hạn sử dụng quyền, không phải cam kết rằng công việc được phép tiếp tục vô thời hạn chỉ vì đã bắt đầu trước hạn.

Việc thu hồi quyền ở nguồn phải đi cùng cơ chế ngăn các lệnh tiếp theo hoặc truy cập đang tồn tại theo thiết kế hệ thống. Nếu đã tạo một URL hoặc môi trường phục hồi riêng, chúng cũng là đối tượng cần quản lý vòng đời.

## 7. Mã hóa và quản lý khóa trong mô hình phân quyền

Mã hóa khi lưu và khi truyền giúp bảo vệ backup trước các rủi ro tương ứng. Tuy nhiên, một người có thể gọi giải mã hoặc truy cập môi trường đã giải mã vẫn có thể đọc nội dung. Vì vậy, mã hóa không thay thế phân quyền.

Cần xem xét riêng:

1. Ai được đọc đối tượng backup?
2. Ai được dùng khóa để giải mã?
3. Ai được thay đổi chính sách khóa hoặc cấp quyền sử dụng khóa?
4. Dịch vụ giải mã có kiểm tra operation, phạm vi và môi trường đích không?
5. Dữ liệu rõ được ghi tạm ở đâu và ai có thể đọc nó?

Không đặt khóa giải mã cùng vị trí mà cùng một quyền đọc có thể lấy cả backup và khóa. Thông tin tham chiếu khóa có thể nằm trong manifest để phục hồi đúng cách, nhưng bí mật khóa phải được quản lý qua cơ chế phù hợp.

Khả năng phục hồi còn phụ thuộc vào khả năng sử dụng khóa hợp lệ trong tình huống sự cố. Quy trình cần bảo vệ khóa đồng thời bảo đảm người có thẩm quyền có thể thực hiện phục hồi theo kế hoạch. Không xử lý lỗi quyền bằng cách xuất khóa ra tệp hoặc vô hiệu hóa kiểm soát để tác vụ chạy nhanh hơn.

Việc xoay hoặc hủy khóa cũng phải xét các backup còn cần giữ. Không giả định rằng thay khóa đang dùng tự động giải quyết mọi bản sao cũ hoặc rằng xóa một khóa luôn tương đương xóa toàn bộ dữ liệu liên quan.

## 8. Quy trình cấp quyền phục hồi có kiểm soát

### Bước 1: Xác định yêu cầu nghiệp vụ

Ghi rõ lý do, tài khoản hoặc tenant bị ảnh hưởng, loại dữ liệu cần phục hồi và kết quả mong muốn. Phân biệt phục hồi dữ liệu người dùng với phục hồi toàn bộ dịch vụ.

Nếu yêu cầu xuất phát từ một người đang mất phương thức xác thực, phải hoàn tất các bước xác minh tương ứng trước khi cấp quyền tác động đến dữ liệu của họ. Không dùng chính tài khoản đang tranh chấp làm căn cứ duy nhất cho quyền quản trị backup.

### Bước 2: Lập kế hoạch từ metadata được phép đọc

Chọn backup, phiên bản, tập dữ liệu và môi trường đích. Xác định có thể phục hồi phạm vi hẹp hay phải dùng một môi trường cách ly chứa dữ liệu rộng hơn để trích xuất.

Một backup toàn cơ sở dữ liệu thường chứa nhiều tài khoản. Không thể biến nó thành bản sao chỉ thuộc một người dùng bằng cách gắn nhãn yêu cầu với người đó. Nếu cần đọc dữ liệu rộng hơn để trích xuất, môi trường và người thực thi phải có thẩm quyền tương ứng, còn đầu ra phải được giới hạn.

### Bước 3: Phê duyệt đúng kế hoạch

Người duyệt kiểm tra nguồn, phạm vi, môi trường đích, rủi ro và điều kiện hoàn tất. Quyết định gắn với phiên bản kế hoạch để không áp dụng cho một yêu cầu đã đổi sau khi duyệt.

### Bước 4: Cấp quyền tạm thời cho dịch vụ thực thi

Chỉ cấp các hành động cần thiết trên đúng tập backup và tài nguyên đích. Tránh đưa thông tin xác thực quản trị dài hạn vào ticket hỗ trợ, dòng lệnh ghi log hoặc nội dung job.

### Bước 5: Kiểm tra tại điểm thực thi

Backend xác minh quyền còn hiệu lực, kế hoạch chưa đổi, nguồn và đích khớp, operation còn được phép và không có điều kiện thu hồi. Kiểm tra ở giao diện phê duyệt không đủ vì job có thể chạy sau đó hoặc bị giao lại.

### Bước 6: Kiểm tra trạng thái sau phục hồi trước khi mở truy cập

Đối chiếu phạm vi dữ liệu thực tế, áp dụng các ràng buộc bảo mật hiện hành và xác nhận môi trường đích có kiểm soát phù hợp. Phục hồi xong về mặt lưu trữ không đồng nghĩa đã sẵn sàng phục vụ đăng nhập.

### Bước 7: Đóng operation và thu hồi tài nguyên tạm

Ghi kết quả, thu hồi quyền tạm thời và xử lý môi trường hoặc tệp trung gian theo chính sách. Không để một cơ sở dữ liệu phục hồi trở thành bản sao dữ liệu thật tồn tại ngoài danh mục quản lý.

## 9. Môi trường cách ly và dữ liệu rõ sau giải mã

Một môi trường phục hồi cách ly có thể giảm nguy cơ làm gián đoạn sản xuất và cho phép trích xuất có kiểm soát. Nhưng nó vẫn chứa dữ liệu nhạy cảm, nên phải được xem là một vùng dữ liệu cần bảo vệ.

Các kiểm soát cần được cân nhắc gồm:

- Danh tính người và dịch vụ được phép truy cập, cùng thời hạn truy cập.
- Giới hạn kết nối mạng và đường xuất dữ liệu theo mục đích operation.
- Tắt hoặc chặn các tác vụ có thể tự gửi email, webhook, thông báo hoặc thực thi job từ dữ liệu được phục hồi.
- Cấu hình ghi log không làm lộ dữ liệu xác thực hoặc tài liệu bằng chứng.
- Bảo vệ đĩa tạm, bộ nhớ đệm, tệp xuất và thông tin xác thực được tạo trong quá trình phục hồi.
- Theo dõi vòng đời của môi trường cho đến khi được xử lý theo kế hoạch.

Nếu sao chép một cơ sở dữ liệu cũ rồi chạy nguyên ứng dụng, các worker có thể tiếp tục xử lý những job đã từng hoàn tất ở sản xuất. Việc cách ly cần ngăn tác dụng phụ trước khi cho phép ứng dụng hoặc người dùng truy cập, không chỉ sau khi phát hiện thông báo bị gửi trùng.

Đầu ra của một thao tác trích xuất cũng cần phân quyền. Không nên bảo vệ backup rất chặt nhưng đưa tệp kết quả lên một liên kết công khai hoặc đính kèm vào ticket nhiều người có thể xem.

## 10. Không phục hồi quyền bảo mật cũ một cách máy móc

Giả sử backup được tạo lúc 01:00. Sau đó, một phiên bị thu hồi lúc 02:00 và một recovery code được dùng lúc 03:00. Phục hồi dữ liệu lúc 04:00 không được khiến phiên và recovery code đó hoạt động trở lại chỉ vì backup ghi chúng còn hợp lệ.

Những trạng thái cần xem xét gồm:

| Trạng thái trong backup | Rủi ro nếu dùng lại nguyên trạng |
|---|---|
| Phiên hoặc refresh token chưa thu hồi | Đường truy cập cũ có thể mở lại |
| Token khôi phục chưa dùng | Có thể cho phép replay một quyền đã được tiêu thụ |
| Recovery code chưa tiêu thụ | Có thể sử dụng lại mã đã mất tính dùng một lần |
| MFA hoặc passkey cũ chưa bị vô hiệu hóa | Yếu tố không còn được tin cậy có thể được chấp nhận |
| Vai trò quản trị tại thời điểm backup | Người đã mất quyền có thể được cấp lại đặc quyền |
| Phê duyệt khôi phục chưa hết hạn trong snapshot | Quyết định cũ có thể bị hiểu sai là còn hiệu lực |

Kế hoạch phục hồi cần đối chiếu với nguồn trạng thái bảo mật có thẩm quyền hiện hành hoặc áp dụng một quy trình vô hiệu hóa và tái xác minh phù hợp. Không lấy quyền quản trị trong backup làm căn cứ cho phép người gọi thực hiện chính thao tác phục hồi đó.

Nếu dùng security epoch để vô hiệu hóa phiên, không hạ phiên bản về giá trị cũ từ backup. Nếu không thể tái dựng các trạng thái thu hồi mới hơn, không được tự giả định mọi quyền trong snapshot đều an toàn; cần giữ giới hạn truy cập và có thể yêu cầu cấp lại phiên hoặc yếu tố qua luồng mới theo kế hoạch sự cố.

Backup chứa credential passkey phía máy chủ không đồng nghĩa hệ thống có thể phục hồi khóa riêng trên thiết bị người dùng. Việc thiếu thiết bị hoặc passkey vẫn cần được xử lý qua một luồng xác minh và đăng ký phù hợp.

## 11. Chống nhầm tenant, nguồn và môi trường đích

Một lỗi chọn nhầm backup hoặc môi trường đích có thể gây lộ dữ liệu dù người vận hành có quyền hợp lệ ở một phạm vi khác. Backend cần kiểm tra liên kết giữa yêu cầu, backup, tập dữ liệu và đích trước khi đọc hoặc ghi.

Một biểu thức chính sách minh họa:

```text
allowRestore(actor, operation, now) =
    actor is authenticated for the required assurance level
    AND actor may execute operation.allowedActions
    AND operation has the required independent approvals
    AND operation.planVersion matches the approved version
    AND operation.backupId identifies the approved source
    AND source scope is permitted for this operation
    AND destination scope and environment are approved
    AND operation is active and not revoked
    AND now < operation.expiresAt
```

Đây là mô tả khái niệm, không phải cú pháp của một công cụ IAM. Những giá trị như nguồn và đích phải được backend đối chiếu với metadata có thẩm quyền, không chỉ tin vào nhãn do client khai báo.

Nếu có một quy trình chuyển dữ liệu giữa các tenant được cho phép, đó phải là phạm vi được phê duyệt rõ ràng, không phải hệ quả của việc người vận hành có thể đọc cả hai tenant. Trong luồng khôi phục thông thường, không tự tạo ngoại lệ qua tenant chỉ để giải quyết nhanh một yêu cầu.

## 12. Quyền khẩn cấp vẫn cần ràng buộc

Trong sự cố lớn, hệ thống có thể cần một cơ chế truy cập khẩn cấp. Cơ chế này nên được chuẩn bị trước, có mục đích và phạm vi rõ, thay vì tạo một tài khoản quản trị dùng chung không được theo dõi.

Các thuộc tính cần xác định gồm người được sử dụng, phương thức xác thực độc lập phù hợp, điều kiện kích hoạt, tài nguyên được phép tác động, thời hạn và trách nhiệm xem xét sau thao tác.

Khôi phục dịch vụ không nên phụ thuộc hoàn toàn vào một tài khoản đang nằm trong chính hệ thống bị hỏng. Đồng thời, đường quản trị khẩn cấp không được trở thành cách bỏ qua xác minh tài khoản cho mọi ticket hỗ trợ.

Quyền khẩn cấp cần được ghi nhận theo từng người và từng operation. Nếu một số bước thông thường được thay bằng quy trình sự cố đã được phê duyệt, phải ghi rõ căn cứ đó; không xóa dấu vết để làm thao tác trông như một lần phục hồi bình thường.

Sau sự cố, thu hồi quyền tạm, rà soát tài nguyên đã tạo và xử lý thông tin xác thực theo quy trình áp dụng. Không để quyền khẩn cấp tiếp tục tồn tại vô thời hạn chỉ vì chưa có lỗi vận hành nào được báo cáo.

## 13. Kiểm toán hành động và phát hiện đường truy cập bất thường

Nhật ký cần liên kết được người yêu cầu, người duyệt, dịch vụ thực thi, backup, môi trường đích và operation. Tài khoản dịch vụ ghi dữ liệu không được che khuất người đã yêu cầu hoặc phê duyệt thao tác.

Các sự kiện minh họa:

```text
BACKUP_METADATA_ACCESSED
BACKUP_READ_AUTHORIZED
BACKUP_DECRYPT_REQUESTED
BACKUP_RESTORE_APPROVED
BACKUP_RESTORE_STARTED
BACKUP_RESTORE_COMPLETED
BACKUP_ACCESS_DENIED
BACKUP_TEMPORARY_ACCESS_REVOKED
BACKUP_RESTORE_ENVIRONMENT_CLOSED
```

Không cần ghi token truy cập, khóa giải mã hoặc nội dung backup vào sự kiện. Ghi định danh ổn định, phạm vi, kết quả và mã nguyên nhân đủ để giải thích.

Cần phân biệt quyết định cho phép với hành động đã hoàn tất. Một log `RESTORE_APPROVED` không chứng minh dữ liệu đã được phục hồi; một yêu cầu giải mã không chứng minh đã có đầu ra dữ liệu rõ được sử dụng.

Những tín hiệu cần chú ý có thể gồm tải nhiều backup, phục hồi sang đích khác thường, liên tục xin quyền giải mã, dùng quyền khẩn cấp ngoài bối cảnh sự cố hoặc môi trường tạm tồn tại quá thời hạn. Đây là tín hiệu cần xem xét theo ngữ cảnh, không phải kết luận tự động rằng người vận hành đã lạm dụng.

Nhật ký và cấu hình kiểm soát truy cập cũng cần được bảo vệ. Nếu một người có thể tự cấp quyền, đọc backup rồi xóa cả dấu vết, việc có nhiều dòng log bình thường không bảo đảm khả năng giải trình.

## 14. Vòng đời backup và thu hồi quyền

Quyền xóa backup hoặc thay đổi hạn lưu ảnh hưởng đến khả năng phục hồi và phạm vi dữ liệu được giữ. Nó cần được tách biệt và kiểm soát phù hợp, thay vì luôn đi kèm quyền đọc.

Một cơ chế bảo vệ backup khỏi chỉnh sửa hoặc xóa có thể hỗ trợ khả năng phục hồi, nhưng không tự ngăn người có quyền đọc tạo thêm bản sao. Ngược lại, hạn chế đọc không giải quyết được nguy cơ mất backup do cấu hình vòng đời hoặc quyền xóa quá rộng.

Khi nhân sự đổi vai trò, tác vụ kết thúc hoặc operation bị hủy, cần xem xét cả:

- Quyền trực tiếp trên kho lưu trữ và hệ thống quản lý khóa.
- Quyền mạo danh hoặc đảm nhận vai trò của dịch vụ thực thi.
- URL hoặc phiên quản trị còn hiệu lực.
- Môi trường phục hồi, volume, snapshot và tệp xuất đã tạo.
- Bản sao được chuyển sang các vị trí khác trong phạm vi quản lý.

Thu hồi quyền không làm biến mất một bản sao đã được tải ra ngoài. Vì vậy, kiểm soát xuất dữ liệu, danh mục tài nguyên và thời hạn xử lý tài nguyên tạm phải được thiết kế trước, không chỉ dựa vào việc gỡ vai trò sau cùng.

## 15. Các tình huống thiết kế cần được làm rõ

Những tình huống sau mô tả hành vi mong muốn, không phải báo cáo đã chạy kiểm thử hệ thống:

| Tình huống | Hành vi phù hợp |
|---|---|
| Nhân viên hỗ trợ có quyền xử lý ticket nhưng không có quyền backup | Không được đọc hoặc phục hồi backup chỉ từ vai trò hỗ trợ |
| Người vận hành đọc được đối tượng mã hóa nhưng chưa có quyền giải mã | Không được tự cấp quyền giải mã hoặc mạo danh dịch vụ để bỏ qua kiểm soát |
| Quyền phục hồi chỉ cho môi trường cách ly | Từ chối ghi vào sản xuất bằng cùng operation |
| Backup toàn cơ sở dữ liệu phục vụ yêu cầu một tài khoản | Xử lý trong phạm vi có thẩm quyền, chỉ xuất dữ liệu được phép |
| Alias backup thay đổi sau khi được duyệt | Không tự chuyển sang nguồn mới ngoài phiên bản kế hoạch |
| Job chờ đến sau hạn quyền tạm thời | Kiểm tra lại, không coi thời điểm tạo job là quyền thực thi |
| Phục hồi snapshot chứa phiên và token cũ | Áp dụng trạng thái bảo mật hiện hành trước khi mở truy cập |
| Môi trường phục hồi chứa job gửi email cũ | Ngăn tác dụng phụ trước khi chạy ứng dụng |
| Người vận hành bị thu hồi vai trò | Xử lý cả quyền gián tiếp, URL và tài nguyên đã tạo theo cơ chế hệ thống |
| Không xác định được nguồn hoặc tenant của backup | Không phục hồi theo phỏng đoán |
| Kho backup còn nguyên nhưng mất khả năng dùng khóa | Xử lý theo kế hoạch phục hồi khóa, không xuất hoặc chia sẻ bí mật tùy tiện |

Những lỗi phổ biến là dùng một vai trò quản trị toàn năng, cho rằng mã hóa đã giải quyết mọi quyền truy cập, chỉ bảo vệ tệp backup mà bỏ quên môi trường phục hồi và khôi phục nguyên trạng các quyền bảo mật đã cũ.

Kiểm soát truy cập backup phải theo suốt đường đi của dữ liệu: từ nguồn sao lưu, kho mã hóa, cơ chế giải mã đến đích phục hồi và các tệp trung gian. Một thao tác chỉ nên được cho phép khi đúng người, đúng phạm vi, đúng môi trường và còn hiệu lực; sau phục hồi, trạng thái xác thực và quyền truy cập vẫn phải được đánh giá theo các ràng buộc hiện hành.
