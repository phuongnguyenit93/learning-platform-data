# Xác định phạm vi kiểm tra bảo mật từ tài sản và mối đe dọa

Trong chiến lược kiểm thử xác thực (**VALIDATION_TESTING_STRATEGY**), phạm vi kiểm tra bảo mật cần bắt đầu từ những gì hệ thống phải bảo vệ và những cách mà tài sản đó có thể bị xâm phạm. Nếu chỉ lập danh sách công cụ hoặc chạy một bộ kiểm tra bảo mật chung cho toàn bộ ứng dụng, nhóm có thể bỏ sót tài sản quan trọng, kiểm tra sai ranh giới hoặc dành nhiều công sức cho vấn đề ít ảnh hưởng.

Cách tiếp cận dựa trên tài sản và mối đe dọa giúp nhóm trả lời ba câu hỏi: **điều gì cần được bảo vệ, ai hoặc điều gì có thể gây hại, và bằng chứng nào cho thấy các biện pháp bảo vệ hoạt động?** Từ đó, nhóm xác định thành phần, luồng dữ liệu, giao diện, cấu hình và kịch bản cần kiểm tra; đồng thời ghi rõ phần chưa nằm trong phạm vi và rủi ro còn lại.

## 1. Bắt đầu từ tài sản cần bảo vệ

### 1.1. Tài sản là gì?

Tài sản (*asset*) là dữ liệu, năng lực, thành phần hoặc nguồn lực có giá trị đối với tổ chức, người dùng hay hoạt động của hệ thống. Tài sản không chỉ là thông tin bí mật. Một chức năng hoặc dịch vụ có thể là tài sản vì tính toàn vẹn và khả năng sẵn sàng của nó rất quan trọng.

Các nhóm tài sản thường gặp:

| Nhóm tài sản | Ví dụ | Thuộc tính bảo mật cần quan tâm |
|---|---|---|
| Dữ liệu cá nhân | Tên, địa chỉ, số điện thoại, hồ sơ người dùng. | Tính bí mật, quyền truy cập phù hợp, lưu giữ và xóa đúng quy định. |
| Dữ liệu tài chính | Đơn hàng, giao dịch, số dư, hóa đơn, thông tin thanh toán được phép lưu. | Tính bí mật và toàn vẹn; khả năng truy vết thay đổi. |
| Thông tin xác thực | Mật khẩu đã băm, token, khóa API, chứng thư, khóa mã hóa. | Bí mật, vòng đời, khả năng thu hồi và chống sử dụng trái phép. |
| Dữ liệu nghiệp vụ | Giá, tồn kho, quyền sở hữu, trạng thái đơn hàng, cấu hình sản phẩm. | Toàn vẹn, tính nhất quán và khả năng truy cập đúng vai trò. |
| Danh tính và quyền | Tài khoản, vai trò, nhóm, chính sách truy cập, phiên đăng nhập. | Xác thực, phân quyền, kiểm soát phiên và khả năng kiểm toán. |
| Dịch vụ và quy trình | Đăng nhập, thanh toán, tìm kiếm, xử lý đơn, gửi thông báo. | Tính toàn vẹn, sẵn sàng, chống lạm dụng và khả năng phục hồi. |
| Hạ tầng và cấu hình | Cơ sở dữ liệu, bucket, mạng, pipeline, container image, cấu hình cloud. | Kiểm soát truy cập, cấu hình an toàn, tính toàn vẹn và khả năng quan sát. |
| Tài sản vận hành | Log, trace, bản sao lưu, khóa khôi phục, công cụ quản trị. | Bí mật, toàn vẹn, thời hạn lưu giữ và quyền truy cập. |

Một tài sản có thể nằm ở nhiều nơi. Dữ liệu thanh toán có thể xuất hiện trong request, hàng đợi, log, cơ sở dữ liệu và bản sao lưu. Khi lập phạm vi, cần lần theo vòng đời dữ liệu thay vì chỉ ghi tên bảng hoặc màn hình.

### 1.2. Đánh giá giá trị và mức độ nhạy cảm

Không phải tài sản nào cũng cần cùng mức bảo vệ. Hãy đánh giá:

- **Bí mật:** hậu quả nếu người không có quyền xem được tài sản.
- **Toàn vẹn:** hậu quả nếu tài sản bị sửa, xóa, giả mạo hoặc xử lý sai.
- **Sẵn sàng:** hậu quả nếu tài sản hoặc dịch vụ không thể sử dụng.
- **Truy xuất và trách nhiệm:** khả năng xác định ai đã thực hiện hành động và khi nào.
- **Nghĩa vụ pháp lý và hợp đồng:** yêu cầu về quyền riêng tư, lưu giữ, vị trí dữ liệu hoặc tiêu chuẩn ngành.
- **Phạm vi ảnh hưởng:** số lượng người dùng, giao dịch, hệ thống hoặc đơn vị bị tác động.

Có thể dùng phân loại như công khai, nội bộ, nhạy cảm và hạn chế. Tổ chức cần thống nhất ý nghĩa từng mức và cách xử lý tương ứng. Không nên tự đưa dữ liệu bí mật hoặc thông tin cá nhân thật vào tài liệu phạm vi; chỉ cần ghi loại tài sản, chủ sở hữu và nơi lưu trữ.

### 1.3. Xác định chủ sở hữu và nơi lưu trữ

Mỗi tài sản quan trọng nên có người hoặc vai trò chịu trách nhiệm. Chủ sở hữu tài sản giúp xác nhận giá trị, mức nhạy cảm, quyền truy cập hợp lệ và hậu quả nếu tài sản bị xâm phạm.

Ghi lại:

- Tên tài sản và mô tả.
- Chủ sở hữu nghiệp vụ hoặc kỹ thuật.
- Nguồn tạo và nơi lưu trữ.
- Các thành phần đọc, ghi, truyền hoặc xử lý tài sản.
- Nhóm người dùng và dịch vụ được phép truy cập.
- Thời hạn lưu giữ và cách xóa hoặc thu hồi.
- Môi trường và bản sao có chứa tài sản.

Danh mục tài sản có thể được xây dựng cùng sơ đồ kiến trúc và luồng dữ liệu. Nếu chưa biết dữ liệu đi qua đâu, phạm vi kiểm tra bảo mật sẽ dễ bỏ sót log, cache, bản sao lưu hoặc dịch vụ tích hợp.

## 2. Xác định mối đe dọa và tác nhân

### 2.1. Mối đe dọa là gì?

Mối đe dọa (*threat*) là một tình huống hoặc hành động có khả năng gây hại cho tài sản. Mối đe dọa có thể đến từ người bên ngoài, người dùng hợp lệ lạm dụng quyền, nhân viên nội bộ, dịch vụ bị xâm nhập hoặc lỗi vận hành.

Ví dụ:

- Người dùng truy cập hồ sơ của tài khoản khác.
- Kẻ tấn công đánh cắp token và sử dụng phiên đăng nhập.
- Người dùng sửa giá hoặc số lượng trong request để tạo đơn sai.
- Một service nhận thông điệp giả mạo từ nguồn không được xác thực.
- Bí mật bị ghi vào log hoặc đưa vào artifact build.
- Dịch vụ bị làm quá tải bởi yêu cầu tự động hoặc thao tác tốn tài nguyên.
- Quyền của tài khoản dịch vụ quá rộng khiến một sự cố lan sang hệ thống khác.

Cần phân biệt các khái niệm:

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| Tài sản | Điều cần bảo vệ. | Hồ sơ và địa chỉ của khách hàng. |
| Tác nhân đe dọa | Người hoặc hệ thống có khả năng gây ra sự kiện. | Người dùng khác, tài khoản bị chiếm, service bên ngoài. |
| Mối đe dọa | Hành động hoặc tình huống gây hại có thể xảy ra. | Đọc hồ sơ không thuộc quyền sở hữu. |
| Điểm yếu (vulnerability) | Lỗ hổng hoặc thiếu sót có thể bị khai thác. | API chỉ kiểm tra người dùng đã đăng nhập mà không kiểm tra quyền sở hữu hồ sơ. |
| Rủi ro | Khả năng và hậu quả khi mối đe dọa khai thác điểm yếu trong bối cảnh cụ thể. | Dữ liệu cá nhân có thể bị lộ cho người dùng khác. |
| Kiểm soát bảo mật | Biện pháp giảm khả năng hoặc tác động. | Kiểm tra quyền ở server, log truy cập và cảnh báo bất thường. |

Một mối đe dọa có thể tồn tại ngay cả khi chưa biết điểm yếu cụ thể. Việc kiểm tra bảo mật nhằm tìm điểm yếu, đánh giá hiệu quả kiểm soát và thu thập bằng chứng về mức rủi ro còn lại.

### 2.2. Xác định tác nhân và khả năng của họ

Không nên giả định mọi tác nhân đều có cùng quyền và kỹ năng. Hãy mô tả bối cảnh:

- Người chưa xác thực có thể truy cập những điểm nào?
- Người dùng đã đăng nhập có thể sửa định danh hoặc tham số để truy cập dữ liệu khác không?
- Người dùng có vai trò thấp có thể gọi trực tiếp chức năng quản trị không?
- Nhân viên hỗ trợ có quyền xem dữ liệu nào và có cần lý do truy cập không?
- Tài khoản dịch vụ có thể gọi những API hoặc truy cập tài nguyên nào?
- Dịch vụ bên ngoài có thể gửi dữ liệu không đáng tin cậy vào hệ thống không?
- Nếu một token, máy trạm hoặc service bị chiếm, phạm vi ảnh hưởng có thể lan đến đâu?

Khả năng của tác nhân có thể được phân loại đơn giản: không có tài khoản, tài khoản thường, tài khoản có vai trò đặc biệt, quyền nội bộ hoặc quyền của một dịch vụ. Việc phân loại giúp tạo test case phù hợp với từng ranh giới tin cậy.

### 2.3. Viết kịch bản đe dọa cụ thể

Một kịch bản đe dọa nên nêu:

**Tác nhân + tài sản mục tiêu + điểm vào hoặc điều kiện + hành động + hậu quả.**

Ví dụ:

“Người dùng đã đăng nhập thay đổi orderId trong request truy vấn đơn hàng; nếu API chỉ xác thực phiên mà không kiểm tra quyền sở hữu, người dùng có thể đọc thông tin đơn của tài khoản khác.”

Mô tả này gợi ra các kiểm tra cụ thể: xác thực, quyền sở hữu đối tượng, phản hồi khi bị từ chối, không rò rỉ dữ liệu và ghi nhận sự kiện truy cập phù hợp.

Tránh ghi rủi ro chung chung như “có thể bị hack” hoặc “bảo mật chưa tốt”. Mô tả càng cụ thể, nhóm càng dễ xác định điểm vào, điều kiện kiểm tra và bằng chứng cần thu thập.

## 3. Lập bản đồ tài sản, luồng dữ liệu và ranh giới tin cậy

### 3.1. Theo dấu dữ liệu từ đầu đến cuối

Bắt đầu từ cách tài sản được tạo, nhận, xử lý, lưu, chia sẻ, sao lưu và xóa. Với mỗi bước, ghi thành phần tham gia và quyền cần có.

Ví dụ, dữ liệu hồ sơ khách hàng có thể đi qua:

1. Trình duyệt gửi request đến API gateway.
2. Gateway xác thực token và chuyển request đến profile service.
3. Profile service kiểm tra quyền sở hữu.
4. Service đọc cơ sở dữ liệu và cache.
5. Kết quả được trả về trình duyệt.
6. Một số sự kiện truy cập được ghi vào hệ thống log.

Mỗi bước có thể tạo ra một loại rủi ro: request bị giả mạo, gateway cấu hình sai, kiểm tra quyền bị thiếu, cache trả dữ liệu sai người dùng, response chứa trường nhạy cảm hoặc log lưu thông tin không cần thiết.

### 3.2. Xác định ranh giới tin cậy

Ranh giới tin cậy (*trust boundary*) là nơi dữ liệu, danh tính hoặc quyền đi từ vùng có mức tin cậy này sang vùng khác. Những ranh giới thường gặp:

- Trình duyệt hoặc ứng dụng di động đến backend.
- Internet đến mạng nội bộ hoặc cloud network.
- API gateway đến service nội bộ.
- Service đến cơ sở dữ liệu, cache hoặc message broker.
- Hệ thống nội bộ đến nhà cung cấp bên ngoài.
- Pipeline build đến registry và môi trường triển khai.
- Tài khoản người dùng đến chức năng quản trị.
- Dữ liệu nhập từ file, webhook hoặc message bên ngoài vào hệ thống.

Tại mỗi ranh giới, cần hỏi dữ liệu có được xác thực, kiểm tra, chuẩn hóa, phân quyền và ghi nhận phù hợp không. Không nên mặc định một service nội bộ luôn đáng tin chỉ vì nó nằm trong mạng riêng.

### 3.3. Xác định bề mặt tấn công

Bề mặt tấn công (*attack surface*) là tập hợp các điểm mà tác nhân có thể tương tác hoặc ảnh hưởng đến hệ thống. Có thể bao gồm:

- Endpoint HTTP, RPC, GraphQL hoặc giao diện quản trị.
- Form, query parameter, header, cookie và file upload.
- Webhook, queue, event consumer và scheduler.
- Chức năng đăng nhập, khôi phục mật khẩu, cấp token và đổi quyền.
- Kho dữ liệu, bucket, cache, backup và công cụ quản trị.
- Cấu hình mạng, cổng dịch vụ, DNS, TLS và chứng thư.
- Pipeline CI/CD, dependency, package registry và container image.
- Log, dashboard, tracing và hệ thống cảnh báo.

Bề mặt tấn công thay đổi theo phiên bản và cấu hình. Một endpoint bị tắt trong môi trường này có thể vẫn mở trong môi trường khác; một feature flag có thể bật thêm đường xử lý mới. Hãy định danh phiên bản, môi trường và trạng thái cấu hình đang được đánh giá.

## 4. Dùng mô hình đe dọa để tìm kịch bản kiểm tra

Mô hình đe dọa (*threat modeling*) là hoạt động phân tích có cấu trúc để xác định tài sản, tác nhân, điểm vào, ranh giới tin cậy, mối đe dọa và kiểm soát cần có. Nó giúp nhóm lựa chọn phạm vi kiểm tra dựa trên cách hệ thống có thể bị lạm dụng.

### 4.1. Dùng STRIDE làm khung gợi ý

STRIDE là một cách phân loại mối đe dọa thường dùng. Có thể áp dụng để rà soát từng thành phần hoặc luồng dữ liệu:

| Nhóm | Ý nghĩa | Ví dụ trong ứng dụng |
|---|---|---|
| Spoofing – Giả mạo | Giả danh người dùng, dịch vụ hoặc nguồn gửi. | Token hoặc webhook giả mạo được chấp nhận. |
| Tampering – Thay đổi trái phép | Sửa dữ liệu hoặc thông điệp không được phép. | Thay đổi giá đơn hàng hoặc payload sự kiện. |
| Repudiation – Chối bỏ hành động | Thiếu bằng chứng để xác định ai đã thực hiện hành động. | Không có audit log cho thay đổi quyền quản trị. |
| Information Disclosure – Tiết lộ thông tin | Dữ liệu được tiết lộ cho người không có quyền. | API trả thông tin hồ sơ của tài khoản khác. |
| Denial of Service – Từ chối dịch vụ | Làm dịch vụ không thể đáp ứng yêu cầu hợp lệ. | Endpoint tốn tài nguyên bị gọi liên tục. |
| Elevation of Privilege – Nâng quyền | Tác nhân có được quyền cao hơn quyền được cấp. | Người dùng thường gọi được API quản trị. |

STRIDE là danh sách gợi ý để đặt câu hỏi, không phải bộ kiểm thử bắt buộc hoặc bằng chứng rằng mọi mối đe dọa đã được bao phủ. Một luồng có thể có nhiều nhóm đe dọa và cần bổ sung kịch bản riêng theo nghiệp vụ.

### 4.2. Xây dựng misuse case và abuse case

Use case mô tả hành vi hợp lệ. Misuse case hoặc abuse case mô tả cách một tác nhân có thể sử dụng chức năng sai mục đích hoặc vượt khỏi quyền được cấp.

Ví dụ với chức năng đổi địa chỉ giao hàng:

- **Use case:** chủ đơn hàng thay đổi địa chỉ trước khi đơn được gửi.
- **Abuse case:** người dùng khác thay đổi orderId để sửa địa chỉ của đơn không thuộc quyền sở hữu.
- **Abuse case:** người dùng gửi yêu cầu lặp hoặc thay đổi trạng thái đơn sau khi đơn đã được giao.
- **Abuse case:** request chứa trường không được phép sửa nhưng server vẫn chấp nhận.

Mỗi abuse case cần được chuyển thành điều kiện kiểm tra có thể quan sát, chẳng hạn request bị từ chối, dữ liệu không thay đổi, không phát sinh tác dụng phụ và sự kiện bảo mật được ghi nhận khi phù hợp.

### 4.3. Dùng sơ đồ luồng dữ liệu

Một sơ đồ luồng dữ liệu (*data flow diagram*) đơn giản có thể thể hiện:

- Tác nhân bên ngoài.
- Tiến trình hoặc service xử lý.
- Kho dữ liệu.
- Luồng dữ liệu và giao thức.
- Ranh giới tin cậy.
- Tài sản nhạy cảm đi qua từng bước.

Sơ đồ không cần mô tả toàn bộ kiến trúc. Chỉ cần đủ để nhóm nhận ra dữ liệu nào đi qua ranh giới nào và nơi nào cần xác minh kiểm soát bảo mật.

## 5. Ưu tiên mối đe dọa và chọn phạm vi kiểm tra

### 5.1. Đánh giá khả năng và tác động

Có thể dùng thang định tính để ưu tiên:

| Mức | Khả năng xảy ra | Tác động |
|---|---|---|
| 1 – Thấp | Điều kiện khó xuất hiện, ít điểm vào hoặc có kiểm soát mạnh. | Ảnh hưởng giới hạn, dễ phát hiện và khôi phục. |
| 2 – Trung bình | Có điều kiện thực tế để xảy ra, nhưng cần một số bước hoặc quyền nhất định. | Một nhóm người dùng hoặc chức năng bị ảnh hưởng. |
| 3 – Cao | Điểm vào phổ biến hoặc có dấu hiệu yếu trong kiểm soát. | Có thể lộ dữ liệu nhạy cảm, sửa giao dịch hoặc làm gián đoạn chức năng quan trọng. |
| 4 – Rất cao | Điều kiện khai thác dễ xảy ra hoặc đã có dấu hiệu bị lạm dụng. | Có thể gây mất dữ liệu, chiếm quyền, thiệt hại tài chính hoặc gián đoạn diện rộng. |

Một mô hình đơn giản có thể dùng điểm khả năng nhân với tác động. Tuy nhiên, điểm số chỉ hỗ trợ thảo luận. Các rủi ro liên quan đến dữ liệu cá nhân, tiền, quyền quản trị hoặc tính toàn vẹn giao dịch có thể cần ưu tiên cao ngay cả khi khả năng xảy ra chưa rõ.

### 5.2. Cân nhắc khả năng phát hiện và phạm vi lan rộng

Ngoài khả năng và tác động, cần xem xét:

- Có phát hiện được hành vi bất thường qua log hoặc cảnh báo không?
- Một tài khoản bị xâm nhập có thể truy cập bao nhiêu tài sản?
- Một lỗi ở service dùng chung có thể ảnh hưởng bao nhiêu luồng?
- Có thể thu hồi token, khóa hoặc quyền nhanh chóng không?
- Có bản sao lưu và khả năng khôi phục đã được kiểm tra không?
- Sự cố có thể lan từ môi trường thử nghiệm sang môi trường khác không?

Một điểm yếu ở tài khoản dịch vụ có quyền rộng có thể có phạm vi ảnh hưởng lớn hơn một lỗi chỉ tác động đến một màn hình.

### 5.3. Chọn kiểm tra theo mối đe dọa

| Mối đe dọa | Kiểm tra có thể phù hợp |
|---|---|
| Truy cập trái phép tài nguyên | API authorization test, kiểm tra quyền theo vai trò và quyền sở hữu đối tượng. |
| Giả mạo danh tính hoặc token | Kiểm tra xác thực, chữ ký, hết hạn, thu hồi và cấu hình phiên. |
| Sửa dữ liệu hoặc giao dịch | Kiểm tra validation phía server, tính toàn vẹn, transaction và audit trail. |
| Tiết lộ thông tin | Kiểm tra response, log, cache, file export và phân quyền dữ liệu. |
| Injection hoặc xử lý đầu vào không an toàn | Code review, SAST, DAST và kiểm tra đầu vào ở các ranh giới. |
| Lạm dụng tài nguyên | Kiểm tra rate limit, quota, giới hạn kích thước, timeout và tải. |
| Lạm dụng upload hoặc file | Kiểm tra loại file, kích thước, nơi lưu, quyền truy cập và xử lý nội dung. |
| Bí mật bị lộ | Secret scanning, kiểm tra cấu hình, quyền truy cập và quy trình thu hồi khóa. |
| Rủi ro dependency hoặc build | Dependency scanning, kiểm tra provenance, chữ ký và quy trình build. |
| Thiếu khả năng truy vết | Kiểm tra audit log, trường bắt buộc, quyền xem log và khả năng tương quan sự kiện. |

Một mối đe dọa có thể cần nhiều lớp kiểm tra. Ví dụ, quyền truy cập trái phép nên được kiểm tra ở unit test của policy, API test tại ranh giới dịch vụ và kiểm tra cấu hình ở gateway nếu gateway tham gia thực thi quyền.

## 6. Xác định phạm vi bao gồm và loại trừ

### 6.1. Ghi rõ phạm vi bao gồm

Phạm vi cần nêu các tài sản, thành phần, giao diện và kịch bản sẽ được kiểm tra. Có thể ghi:

- Tài sản và mức nhạy cảm.
- Service, API, giao diện quản trị và luồng dữ liệu liên quan.
- Ranh giới tin cậy và bề mặt tấn công.
- Vai trò và loại tác nhân được mô phỏng.
- Mối đe dọa và abuse case ưu tiên.
- Kiểm soát bảo mật cần xác minh.
- Môi trường, phiên bản và cấu hình.
- Loại kiểm tra và bằng chứng cần thu thập.

Không nên chỉ ghi “kiểm tra bảo mật toàn hệ thống”. Câu này không xác định được tài sản nào, môi trường nào, vai trò nào hoặc tiêu chí nào.

### 6.2. Ghi rõ phần loại trừ và lý do

Một số phần có thể chưa được kiểm tra vì không có quyền, môi trường không phù hợp, phụ thuộc bên thứ ba hoặc giới hạn thời gian. Phần loại trừ phải đi kèm ảnh hưởng và kế hoạch xử lý.

Ví dụ:

| Phần loại trừ | Lý do | Rủi ro còn lại và hành động |
|---|---|---|
| Hệ thống thanh toán production | Không được thực hiện giao dịch thật trong hoạt động kiểm thử. | Dùng sandbox; ghi rõ chưa có bằng chứng trên production và xác minh qua quy trình triển khai có kiểm soát. |
| Hạ tầng của nhà cung cấp | Không thuộc quyền kiểm tra trực tiếp. | Rà soát tài liệu bảo mật, hợp đồng và bằng chứng độc lập; ghi phụ thuộc còn lại. |
| Kiểm thử tải gây gián đoạn | Môi trường dùng chung không cho phép tạo tải lớn. | Dùng môi trường chuyên biệt và phê duyệt phạm vi trước khi chạy. |
| Thành phần cũ đã ngừng hỗ trợ | Không nằm trong ma trận nền tảng hiện tại. | Ghi rõ đối tượng bị loại trừ và người dùng còn chịu ảnh hưởng nếu có. |

Không nên gọi một phần là “không có rủi ro” chỉ vì nó nằm ngoài phạm vi. Loại trừ là một giới hạn của bằng chứng và cần được người có thẩm quyền xem xét khi ảnh hưởng đáng kể.

### 6.3. Phân biệt phạm vi kiểm tra với phạm vi được phép

Phạm vi kỹ thuật mong muốn phải nằm trong phạm vi được phép thực hiện. Kiểm tra bảo mật có thể ảnh hưởng dữ liệu hoặc tính sẵn sàng, vì vậy cần xác định hệ thống, môi trường, thời gian, tài khoản và loại hoạt động được cho phép.

Đối với kiểm thử có khả năng gây tác động, cần thống nhất trước:

- Hệ thống và địa chỉ đích được phép kiểm tra.
- Môi trường và khoảng thời gian thực hiện.
- Tài khoản, vai trò và dữ liệu thử nghiệm.
- Loại kiểm tra được phép và giới hạn tải.
- Cách liên hệ khi phát hiện sự cố.
- Điều kiện dừng và khôi phục.

Không đưa hệ thống hoặc tài sản của bên thứ ba vào phạm vi chỉ vì chúng xuất hiện trong sơ đồ phụ thuộc. Cần có quyền và thỏa thuận phù hợp trước khi kiểm tra.

## 7. Ánh xạ tài sản và mối đe dọa thành kế hoạch kiểm thử

Một kế hoạch tốt nối được chuỗi:

**Tài sản → Mối đe dọa → Điểm yếu hoặc kiểm soát → Kịch bản kiểm tra → Bằng chứng → Rủi ro còn lại.**

Ví dụ:

| Tài sản | Mối đe dọa | Kiểm soát cần xác minh | Kịch bản kiểm tra | Bằng chứng |
|---|---|---|---|---|
| Hồ sơ khách hàng | Người dùng đọc hồ sơ người khác. | Kiểm tra quyền sở hữu ở server. | Gọi API bằng tài khoản A với định danh hồ sơ của B. | Request bị từ chối; không trả dữ liệu nhạy cảm; log phù hợp. |
| Đơn hàng | Người dùng sửa giá hoặc trạng thái trái phép. | Giá và trạng thái được quyết định phía server. | Gửi request có trường giá hoặc trạng thái không được phép sửa. | Giá trị không bị thay đổi; phản hồi và audit phù hợp. |
| Token truy cập | Token hết hạn hoặc bị thu hồi vẫn được chấp nhận. | Xác minh chữ ký, hạn dùng và trạng thái thu hồi. | Dùng token hết hạn hoặc đã thu hồi trong môi trường thử nghiệm. | Request bị từ chối theo hợp đồng; không có tác dụng phụ. |
| Bí mật dịch vụ | Khóa bị ghi vào log hoặc artifact. | Quản lý secret và lọc log. | Kiểm tra pipeline, cấu hình và log bằng dữ liệu thử nghiệm nhận diện được. | Không phát hiện secret trong artifact/log; quyền truy cập được giới hạn. |
| Dịch vụ thanh toán | Callback giả mạo hoặc gửi lặp. | Xác minh chữ ký, idempotency và trạng thái giao dịch. | Gửi callback thử nghiệm sai chữ ký và callback trùng. | Callback sai bị từ chối; callback hợp lệ không tạo xử lý trùng. |

Ma trận này giúp nhóm biết vì sao mỗi test tồn tại. Nếu một tài sản quan trọng không có mối đe dọa hoặc kiểm soát tương ứng, cần xem xét liệu phân tích có thiếu sót hay tài sản đó thực sự không nằm trong phạm vi.

## 8. Chọn phương pháp kiểm tra bảo mật

Không có một công cụ nào bao phủ mọi mối đe dọa. Phương pháp nên được chọn theo loại tài sản, điểm vào, ranh giới và giai đoạn phát triển.

### 8.1. Kiểm tra mã nguồn và cấu hình

- **SAST:** phân tích mã nguồn hoặc bytecode để tìm mẫu lỗi bảo mật.
- **Secret scanning:** tìm khóa, token hoặc thông tin xác thực bị đưa vào mã và lịch sử repository.
- **Dependency scanning:** xác định thư viện có lỗ hổng đã biết hoặc phiên bản rủi ro.
- **IaC scanning:** rà soát cấu hình hạ tầng dưới dạng mã, quyền, mạng và tài nguyên.
- **Code review bảo mật:** xem xét xác thực, phân quyền, validation, xử lý lỗi và quản lý dữ liệu.

Các công cụ tự động có thể tạo cảnh báo sai hoặc bỏ sót lỗi logic. Kết quả cần được xác minh theo bối cảnh, phiên bản và khả năng khai thác thực tế.

### 8.2. Kiểm tra ứng dụng đang chạy

- **DAST:** kiểm tra ứng dụng đang chạy từ bên ngoài để tìm vấn đề ở các điểm vào có thể truy cập.
- **API security testing:** xác minh xác thực, phân quyền, validation, giới hạn và xử lý lỗi tại endpoint.
- **Kiểm tra cấu hình triển khai:** xác minh TLS, header, quyền service, network policy và cấu hình mặc định.
- **Kiểm tra session:** xác minh cookie, timeout, logout, thu hồi và vòng đời token.
- **Kiểm tra file và dữ liệu:** xác minh upload, download, export và quyền truy cập tài nguyên.

DAST không thay thế kiểm tra logic nghiệp vụ hoặc review mã nguồn. Nó chỉ quan sát hành vi có thể tiếp cận trong điều kiện và tài khoản được cung cấp.

### 8.3. Kiểm thử xâm nhập và đánh giá chuyên sâu

Kiểm thử xâm nhập (*penetration testing*) đánh giá khả năng khai thác các điểm yếu trong phạm vi và điều kiện được phê duyệt. Hoạt động này có thể hữu ích cho tài sản quan trọng, luồng phức tạp hoặc trước một mốc phát hành lớn.

Phạm vi cần nêu mục tiêu, môi trường, quyền, loại kiểm tra, giới hạn tác động, quy tắc dừng và cách báo cáo. Kiểm thử xâm nhập là một nguồn bằng chứng tại thời điểm đánh giá; nó không chứng minh hệ thống không còn điểm yếu và không thay thế kiểm tra liên tục trong vòng đời phát triển.

### 8.4. Kiểm tra vận hành và khả năng phát hiện

Bảo mật không chỉ là ngăn chặn. Nhóm cũng cần xác minh hệ thống phát hiện và phản ứng được với hành vi bất thường:

- Audit log ghi nhận hành động nhạy cảm.
- Cảnh báo được kích hoạt khi có dấu hiệu bất thường.
- Log không chứa dữ liệu bí mật không cần thiết.
- Sự kiện có thể liên kết qua trace hoặc định danh tương quan.
- Quy trình thu hồi token hoặc khóa có thể thực hiện.
- Backup và khôi phục được kiểm tra theo yêu cầu.
- Người phụ trách nhận được cảnh báo và biết cách phản ứng.

Một kiểm soát không có bằng chứng hoạt động hoặc không có người theo dõi có thể không tạo ra mức bảo vệ như dự kiến.

## 9. Ví dụ: xác định phạm vi bảo mật cho ứng dụng thương mại điện tử

Giả sử một ứng dụng có tài khoản khách hàng, danh mục sản phẩm, giỏ hàng, đơn hàng, thanh toán và trang quản trị. Nhóm cần xác định phạm vi kiểm tra cho một bản phát hành bổ sung luồng thanh toán mới.

### 9.1. Danh mục tài sản

| Tài sản | Chủ sở hữu | Mức nhạy cảm | Nơi xử lý |
|---|---|---|---|
| Hồ sơ và địa chỉ khách hàng | Product/data owner | Nhạy cảm | Profile service, database, cache |
| Đơn hàng và tổng tiền | Order service owner | Nội bộ/nhạy cảm | Checkout API, order database |
| Token và khóa tích hợp | Security/platform owner | Hạn chế | Secret store, runtime, CI/CD |
| Trạng thái giao dịch | Payment service owner | Nhạy cảm | Payment service, database, callback handler |
| Quyền quản trị | Application owner | Hạn chế | Identity provider, admin API |
| Log và audit event | Operations/security owner | Nội bộ, có thể chứa dữ liệu nhạy cảm | Logging platform, audit store |

### 9.2. Kịch bản đe dọa ưu tiên

- Người dùng sửa order ID để xem đơn của tài khoản khác.
- Người dùng gửi giá hoặc trạng thái đơn do client cung cấp để thay đổi kết quả thanh toán.
- Token bị lộ có thể được sử dụng sau khi người dùng đăng xuất.
- Callback giả mạo hoặc gửi lặp làm thay đổi trạng thái giao dịch.
- Tài khoản hỗ trợ có thể xem quá nhiều dữ liệu khách hàng.
- Khóa API bị đưa vào log hoặc artifact build.
- Endpoint tìm kiếm hoặc tính phí bị lạm dụng để tiêu thụ tài nguyên.

### 9.3. Phạm vi kiểm tra đề xuất

| Thành phần | Tài sản và mối đe dọa | Kiểm tra cần thực hiện |
|---|---|---|
| Identity và session | Token giả mạo, hết hạn hoặc không được thu hồi. | Kiểm tra chữ ký, hạn dùng, logout và thu hồi token. |
| Profile API | Đọc hoặc sửa hồ sơ người khác. | Kiểm tra quyền sở hữu với nhiều tài khoản và vai trò. |
| Checkout API | Sửa giá, số lượng hoặc trạng thái trái phép. | Kiểm tra validation phía server, quyền và tính toàn vẹn giao dịch. |
| Payment callback | Callback giả mạo hoặc trùng. | Kiểm tra xác minh chữ ký, idempotency và trạng thái cuối. |
| Admin API | Nâng quyền hoặc truy cập quá mức. | Kiểm tra vai trò, quyền theo chức năng và audit log. |
| CI/CD và secret store | Lộ khóa tích hợp. | Secret scanning, kiểm tra quyền và xác nhận không có secret trong artifact. |
| Logging platform | Lộ dữ liệu cá nhân hoặc token. | Kiểm tra masking, quyền xem log và trường dữ liệu được ghi. |

### 9.4. Ranh giới và loại trừ

Phạm vi có thể bao gồm các API và service của bản phát hành trên staging, sandbox thanh toán, tài khoản thử nghiệm với vai trò khách hàng và quản trị, cùng cấu hình triển khai tương ứng.

Có thể loại trừ hạ tầng nội bộ của nhà cung cấp thanh toán và giao dịch tiền thật trên production. Những phần này cần được ghi là giới hạn bằng chứng. Nhóm có thể rà soát tài liệu bảo mật của nhà cung cấp, xác minh tích hợp sandbox và đề xuất kiểm tra sau triển khai có kiểm soát theo quy trình phát hành.

### 9.5. Tiêu chí hoàn tất

- Các tài sản quan trọng có chủ sở hữu và mức nhạy cảm.
- Các luồng dữ liệu và ranh giới tin cậy liên quan được lập bản đồ.
- Mối đe dọa ưu tiên được chuyển thành kịch bản kiểm tra.
- Các kiểm soát xác thực, phân quyền, toàn vẹn, bí mật và audit được xác minh.
- Kết quả thất bại và phát hiện được phân loại, gắn với mức độ ảnh hưởng.
- Phần loại trừ và rủi ro còn lại được ghi nhận.
- Người có thẩm quyền xem xét các rủi ro chưa được xử lý trước quyết định phát hành.

## 10. Mẫu lập phạm vi kiểm tra bảo mật

Có thể sử dụng mẫu sau để lập kế hoạch và trao đổi với chủ sở hữu tài sản, phát triển, vận hành và bảo mật.

~~~text
Tên hệ thống / bản phát hành:
Phiên bản, môi trường và cấu hình:
Mục tiêu kiểm tra:

Tài sản cần bảo vệ:
- Tên và mô tả:
- Chủ sở hữu:
- Mức nhạy cảm / giá trị:
- Nơi lưu trữ và xử lý:
- Thuộc tính cần bảo vệ (bí mật / toàn vẹn / sẵn sàng):

Tác nhân và mối đe dọa:
- Tác nhân:
- Khả năng / quyền hiện có:
- Tài sản mục tiêu:
- Điểm vào và điều kiện:
- Hành động có thể xảy ra:
- Hậu quả:

Luồng dữ liệu và ranh giới tin cậy:
Bề mặt tấn công:
Kiểm soát bảo mật cần xác minh:

Kịch bản kiểm tra:
- Điều kiện ban đầu:
- Vai trò / tài khoản thử nghiệm:
- Hành động:
- Kết quả mong đợi:
- Bằng chứng cần lưu:

Phạm vi bao gồm:
Phạm vi loại trừ và lý do:
Giới hạn môi trường / phụ thuộc:
Quy tắc thực hiện và điều kiện dừng:

Mức ưu tiên và cơ sở đánh giá:
Người phụ trách:
Lỗi và phát hiện còn mở:
Rủi ro còn lại:
Quyết định / người chấp nhận (nếu có):
Ngày xem xét tiếp theo:
~~~

Với một thay đổi nhỏ, mẫu có thể rút gọn. Với hệ thống có nhiều tài sản và ranh giới, nên duy trì danh mục tài sản, sơ đồ luồng dữ liệu và danh mục kịch bản riêng, rồi liên kết chúng với kế hoạch kiểm thử.

## 11. Báo cáo phát hiện và quản lý rủi ro còn lại

Một phát hiện bảo mật cần đủ thông tin để người nhận hiểu tác động và tái xác minh. Báo cáo nên bao gồm:

- Tài sản và thành phần bị ảnh hưởng.
- Mối đe dọa hoặc kịch bản có thể xảy ra.
- Điều kiện và vai trò cần có để tái hiện.
- Bằng chứng đã thu thập trong môi trường được phép.
- Tác động đến bí mật, toàn vẹn, sẵn sàng hoặc nghĩa vụ liên quan.
- Mức độ ưu tiên và cơ sở đánh giá.
- Biện pháp khắc phục hoặc giảm thiểu.
- Người phụ trách và thời hạn.
- Kết quả kiểm tra lại sau khi sửa.

Không nên chỉ báo cáo tên công cụ và số lượng cảnh báo. Cần xác minh phát hiện trong bối cảnh hệ thống, loại bỏ cảnh báo sai có căn cứ và giữ lại các giới hạn chưa thể kiểm tra.

Rủi ro còn lại cần được ghi rõ khi một mối đe dọa chưa thể loại bỏ hoặc một phần phạm vi bị loại trừ. Người có thẩm quyền phải hiểu tài sản nào bị ảnh hưởng, hậu quả có thể xảy ra, biện pháp giảm thiểu hiện có và điều kiện cần xem xét lại. Người thực hiện kiểm thử có thể đưa ra khuyến nghị nhưng không tự chấp nhận rủi ro vượt thẩm quyền.

## 12. Duy trì phạm vi bảo mật khi hệ thống thay đổi

Danh mục tài sản và mô hình đe dọa cần được cập nhật khi:

- Thêm API, webhook, worker hoặc giao diện quản trị.
- Thay đổi luồng dữ liệu, schema hoặc nơi lưu trữ.
- Thêm vai trò, quyền hoặc nhà cung cấp mới.
- Thay đổi xác thực, session, token hoặc cơ chế mã hóa.
- Thay đổi hạ tầng, mạng, cloud policy hoặc pipeline.
- Phát hiện lỗi bảo mật hoặc sự cố thực tế.
- Thay đổi phân loại dữ liệu hoặc nghĩa vụ tuân thủ.

Sau mỗi thay đổi, hãy xem xét tài sản mới, điểm vào mới, ranh giới mới và kịch bản đe dọa có thể phát sinh. Không cần làm lại toàn bộ mô hình nếu thay đổi nhỏ; hãy cập nhật phần bị ảnh hưởng và xác định bằng chứng cũ nào còn áp dụng.

Các lỗi bảo mật đã phát hiện nên được chuyển thành kiểm thử hồi quy phù hợp. Ví dụ, nếu từng có lỗi truy cập chéo tài khoản, cần duy trì test quyền sở hữu ở API và kiểm tra các luồng liên quan khi cấu trúc định danh hoặc phân quyền thay đổi.

## 13. Những sai lầm thường gặp

- **Bắt đầu từ công cụ:** chạy scanner trước khi biết tài sản và rủi ro có thể tạo nhiều cảnh báo nhưng bỏ sót luồng quan trọng.
- **Chỉ coi dữ liệu bí mật là tài sản:** trạng thái giao dịch, quyền quản trị và tính sẵn sàng cũng cần được bảo vệ.
- **Mô tả mối đe dọa quá chung:** “bị tấn công” không chỉ ra tác nhân, điểm vào hoặc hậu quả.
- **Bỏ qua ranh giới tin cậy:** service nội bộ, webhook, queue và pipeline cũng có thể là điểm vào.
- **Chỉ kiểm tra đăng nhập:** người dùng đã xác thực vẫn có thể truy cập tài nguyên hoặc chức năng ngoài quyền.
- **Chỉ kiểm tra trường hợp thành công:** cần kiểm tra cả hành vi từ chối và việc không tạo tác dụng phụ khi quyền hoặc dữ liệu không hợp lệ.
- **Đánh đồng cảnh báo scanner với lỗ hổng đã xác nhận:** phát hiện cần được kiểm chứng trong bối cảnh.
- **Bỏ qua log, backup và pipeline:** các nơi này có thể chứa dữ liệu hoặc quyền có giá trị cao.
- **Không ghi phần loại trừ:** người đọc có thể hiểu nhầm rằng toàn bộ hệ thống đã được đánh giá.
- **Không cập nhật sau thay đổi:** bề mặt tấn công có thể thay đổi dù tính năng chính không đổi.

## 14. Danh sách rà soát trước khi chốt phạm vi

- [ ] Tài sản quan trọng được liệt kê cùng chủ sở hữu và mức nhạy cảm.
- [ ] Vòng đời dữ liệu và nơi lưu trữ, xử lý, truyền tải được xác định.
- [ ] Tác nhân, quyền và khả năng của họ được mô tả.
- [ ] Mối đe dọa được viết thành kịch bản cụ thể với tài sản, điểm vào và hậu quả.
- [ ] Ranh giới tin cậy và bề mặt tấn công được lập bản đồ.
- [ ] Kiểm soát bảo mật được liên kết với kịch bản cần xác minh.
- [ ] Ưu tiên phản ánh khả năng, tác động và phạm vi lan rộng.
- [ ] Phương pháp kiểm tra phù hợp với loại tài sản và mối đe dọa.
- [ ] Phạm vi bao gồm, loại trừ và giới hạn môi trường được ghi rõ.
- [ ] Phạm vi kỹ thuật nằm trong phạm vi được phép thực hiện.
- [ ] Bằng chứng, phát hiện và lỗi còn mở có người phụ trách.
- [ ] Rủi ro còn lại được báo cáo và chấp nhận đúng thẩm quyền.
- [ ] Có kế hoạch cập nhật phạm vi khi kiến trúc, dữ liệu hoặc cấu hình thay đổi.

## Kết luận

Phạm vi kiểm tra bảo mật có cơ sở khi bắt đầu từ tài sản cần bảo vệ, lần theo luồng dữ liệu và ranh giới tin cậy, rồi xác định tác nhân cùng các kịch bản đe dọa có thể xảy ra. Nhóm cần ánh xạ từng kịch bản vào kiểm soát và bằng chứng phù hợp, ưu tiên theo hậu quả, ghi rõ phần bao gồm và loại trừ, đồng thời quản lý rủi ro còn lại. Cách làm này giúp hoạt động kiểm tra tập trung vào những gì có giá trị đối với hệ thống và tạo cơ sở rõ ràng cho quyết định phát hành.
