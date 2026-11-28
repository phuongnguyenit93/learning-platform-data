# Service-to-service authentication — Đặc tả xác thực giữa các dịch vụ

## 1. Mục tiêu bảo mật và phạm vi

**Service-to-service authentication** là việc một dịch vụ kiểm chứng danh tính của dịch vụ hoặc workload đang giao tiếp với mình, dựa trên bằng chứng được một miền tin cậy chấp nhận.

Một địa chỉ nội bộ, tên DNS hoặc header mang tên dịch vụ không tự chứng minh chủ thể gọi. Nếu chỉ tin rằng mọi kết nối trong mạng nội bộ đều hợp lệ, một workload bị chiếm quyền hoặc một đường truy cập ngoài dự kiến có thể mạo danh dịch vụ khác.

Trong module chuyển mục tiêu an toàn thông tin và mô hình đe dọa thành yêu cầu bảo mật, cần trả lời:

> Workload nào được cấp danh tính, bên nhận kiểm chứng bằng chứng nào, tin cậy tổ chức cấp nào, xác thực có hiệu lực trong bao lâu và phải xử lý thế nào khi bằng chứng sai hoặc không còn hiệu lực?

Sau bài học, người đọc có thể:

- Phân biệt danh tính dịch vụ, danh tính instance và danh tính người dùng.
- Đặc tả kiểm chứng danh tính qua kênh và qua thông tin xác thực ở tầng ứng dụng.
- Xác định ranh giới tin cậy khi có gateway, proxy hoặc hệ thống nhắn tin.
- Viết yêu cầu cấp, xoay vòng, thu hồi và quan sát thông tin xác thực.
- Liên kết yêu cầu với quyền nghiệp vụ và ca kiểm thử có bằng chứng.

Các ngưỡng thời gian trong bài thuộc một hệ thống giả định. Chúng minh họa cách viết yêu cầu đo được, không phải giá trị mặc định cho mọi sản phẩm.

## 2. Danh tính, xác thực và phân quyền là các quyết định khác nhau

| Khái niệm | Câu hỏi | Ví dụ |
|---|---|---|
| Service identity | Dịch vụ logic nào đang gọi? | orders-service trong môi trường production. |
| Workload hoặc instance identity | Bản triển khai hoặc thực thể đang chạy nào có bằng chứng được cấp? | Một instance được nền tảng cho phép chạy dưới danh tính orders-service. |
| Authentication — xác thực | Bên gọi có chứng minh được danh tính đó theo chính sách không? | Chứng minh quyền giữ khóa và có chứng thư hợp lệ hoặc có token được chấp nhận. |
| Authorization — phân quyền | Danh tính đã xác thực được làm gì trên tài nguyên nào? | orders-service được tạo hóa đơn nhưng không được điều chỉnh số dư. |
| User delegation — ủy quyền người dùng | Dịch vụ đang hành động thay ai và với giới hạn nào? | Tạo hóa đơn cho tenant mà người dùng có quyền thao tác. |

Một dịch vụ được xác thực không mặc nhiên được gọi mọi endpoint. Tương tự, dịch vụ có quyền gọi một thao tác không có nghĩa nó được tự chọn tenant hoặc người dùng bất kỳ.

Cần giữ riêng ít nhất hai lớp chủ thể:

- **Chủ thể kỹ thuật gọi:** workload nào chịu trách nhiệm tạo yêu cầu.
- **Chủ thể nghiệp vụ được đại diện:** người dùng, tenant hoặc tác vụ hệ thống nào là căn cứ quyền nghiệp vụ.

Gộp hai lớp thành một trường “caller” dễ dẫn tới việc dùng quyền mạnh của dịch vụ để thực hiện yêu cầu mà người dùng không được phép.

## 3. Từ mô hình đe dọa tới yêu cầu

Giả sử orders-service gọi billing-service để tạo hóa đơn, còn notification-service chỉ cần nhận kết quả để gửi thông báo.

| Kịch bản rủi ro | Tác động | Hướng chuyển thành yêu cầu |
|---|---|---|
| Workload tự khai tên orders-service | Mạo danh dịch vụ có quyền cao hơn. | Danh tính phải được suy ra từ bằng chứng đã xác minh, không từ header tùy ý. |
| Token cấp cho dịch vụ khác được dùng tại billing-service | Dùng bằng chứng ngoài phạm vi dự kiến. | Kiểm tra bên phát hành, đối tượng nhận và mục đích token. |
| Workload ở môi trường thử gọi production | Vượt ranh giới môi trường. | Phân biệt miền tin cậy, danh tính và chính sách chấp nhận. |
| Lộ thông tin xác thực | Chủ thể khác có thể gọi như dịch vụ hợp lệ. | Giới hạn phạm vi, vòng đời, quyền lưu giữ và thời gian thu hồi. |
| Tắt kiểm tra máy chủ để xử lý lỗi kết nối | Client có thể gửi dữ liệu cho bên giả mạo. | Xác thực đích và từ chối khi không kiểm chứng được. |
| Proxy làm mất danh tính gốc | Ứng dụng chỉ thấy proxy nhưng tin một header do client cung cấp. | Hợp đồng truyền danh tính qua proxy và chặn đường bỏ qua. |
| Dịch vụ chuyển tiếp quyền của mình cho yêu cầu người dùng trái phép | Confused deputy, dùng quyền mạnh thay cho quyền người dùng. | Kiểm tra đồng thời danh tính dịch vụ và ngữ cảnh ủy quyền. |
| Credential bị thu hồi nhưng kết nối cũ vẫn được dùng | Tiếp tục chấp nhận chủ thể không còn được phép. | Ràng buộc hiệu lực trên từng quyết định, kể cả kết nối tái sử dụng. |

Chuỗi truy vết nên giữ dạng:

> Rủi ro → yêu cầu xác thực hoặc quyền → điểm kiểm chứng → ca kiểm thử → bằng chứng.

“Đã bật mã hóa” chưa trả lời bên nào đang kết nối. “Đã bật mTLS” cũng chưa trả lời danh tính được ánh xạ thành chủ thể nào và chủ thể đó được phép làm gì.

## 4. Thiết kế không gian danh tính và quan hệ tin cậy

### 4.1. Danh tính ổn định theo chính sách

Danh tính nên biểu diễn được các ranh giới có ý nghĩa như môi trường, miền vận hành và dịch vụ. Ví dụ:

~~~text
workload:prod:orders-service
workload:prod:billing-service
workload:prod:notification-service
workload:test:orders-service
~~~

Đây là quy ước minh họa, không phải định dạng bắt buộc. Tên cần được so sánh theo quy tắc rõ ràng, không dùng kiểm tra chuỗi chứa một từ gần giống để cấp quyền.

IP, địa chỉ instance hoặc tên hiển thị có thể đổi khi triển khai. Chúng là dữ liệu mạng hoặc vận hành, không tự thay cho danh tính bảo mật ổn định.

Nếu nhiều instance dùng chung một service identity, cần ghi thêm định danh instance thích hợp để điều tra. Không suy ra rằng mọi yêu cầu mang cùng service identity đều đến từ cùng một tiến trình.

### 4.2. Ai được cấp danh tính?

Dịch vụ cấp danh tính phải xác minh workload có quyền nhận đúng danh tính, dựa trên bằng chứng từ nền tảng hoặc quy trình đăng ký tin cậy.

Không cho workload tự chọn tên đặc quyền rồi nhận credential tương ứng chỉ vì nó gọi được endpoint cấp phát. Các giá trị môi trường, nhãn triển khai hoặc tham số tự khai chỉ có giá trị khi đã được đối chiếu với nguồn có thẩm quyền.

Đặc tả bootstrap cần làm rõ:

- Nguồn bằng chứng ban đầu và ai có quyền tạo nó.
- Cách ràng buộc bằng chứng với workload đang xin credential.
- Phạm vi và thời hạn sử dụng bằng chứng.
- Điều kiện ngăn workload của tenant hoặc môi trường khác nhận cùng danh tính.
- Quy trình cấp lại khi instance được thay thế.
- Audit cho đăng ký, cấp phát, từ chối và thay đổi ánh xạ.

### 4.3. Ma trận gọi được phép

| Bên gọi | Bên nhận | Năng lực được phép trong ví dụ |
|---|---|---|
| orders-service production | billing-service production | Tạo và tra cứu hóa đơn trong ngữ cảnh được phép. |
| notification-service production | billing-service production | Chỉ nhận hoặc đọc trạng thái phục vụ thông báo theo chính sách. |
| orders-service môi trường thử | billing-service production | Không được phép. |
| Danh tính chưa đăng ký | Mọi API production | Không được phép. |

Ma trận là đầu vào phân quyền, tách khỏi việc kiểm chứng chứng thư hoặc token. Một bằng chứng có chữ ký hợp lệ từ một tổ chức cấp không được chấp nhận cho mọi phạm vi chỉ vì chữ ký kiểm tra được.

## 5. Các cơ chế và điều kiện kiểm chứng

### 5.1. Xác thực kênh bằng mTLS

Với mutual TLS, các bên có thể kiểm chứng bằng chứng chứng thư và quyền giữ khóa theo cấu hình của kênh. Thiết kế phải xác định bên nào xác thực bên nào tại mỗi điểm kết thúc kênh.

Yêu cầu cần bao gồm:

- Chuỗi tin cậy và tổ chức cấp được phép cho đúng môi trường.
- Hiệu lực chứng thư và mục đích sử dụng phù hợp.
- Danh tính đích mà client mong đợi.
- Cách server ánh xạ chứng thư client thành workload identity.
- Chính sách với danh tính chưa đăng ký, chứng thư hết hạn hoặc không còn được phép.
- Vòng đời khóa và khả năng làm mới credential.

Không chỉ kiểm tra kết nối được mã hóa hoặc chứng thư “có thể đọc được”. Client phải từ chối đích không có danh tính mong đợi; server phải từ chối client không đủ bằng chứng theo chính sách.

mTLS xác thực đối tác tại điểm kết thúc TLS. Nếu kênh kết thúc ở proxy, ứng dụng phía sau không tự có bằng chứng rằng kết nối trực tiếp tới nó đến từ workload gốc.

### 5.2. Token truy cập của dịch vụ

Một dịch vụ có thể dùng token được cấp cho một đối tượng nhận và mục đích xác định. Token có thể được bên nhận kiểm tra cục bộ hoặc qua dịch vụ kiểm chứng, tùy thiết kế.

Nếu dùng token có chữ ký và các claim, cần xác minh:

| Điều kiện | Yêu cầu |
|---|---|
| Bên phát hành | Thuộc tập issuer được cấu hình cho môi trường và loại token. |
| Tính toàn vẹn | Chữ ký hoặc cơ chế xác thực token được kiểm tra bằng khóa tin cậy. |
| Loại và mục đích | Token được phép dùng cho truy cập dịch vụ, không nhầm với bằng chứng dùng cho mục đích khác. |
| Đối tượng nhận | Audience khớp billing-service theo quy tắc đã định nghĩa. |
| Chủ thể | Subject ánh xạ tới workload được chấp nhận. |
| Thời gian | Hiệu lực, thời điểm bắt đầu nếu có và thời hạn sống đáp ứng hồ sơ. |
| Phạm vi | Quyền hoặc scope được kiểm tra theo chính sách nghiệp vụ, không tự mở rộng từ đầu vào client. |
| Trạng thái thu hồi | Credential, khóa hoặc danh tính không nằm trong phạm vi bị thu hồi theo yêu cầu hiệu lực. |

Giải mã nội dung token không phải kiểm tra chữ ký. Một claim tự khai không có giá trị trước khi toàn bộ điều kiện xác thực cần thiết được đáp ứng.

Thuật toán và nguồn khóa phải bị giới hạn bởi chính sách máy chủ. Không để token tự chọn một địa chỉ tùy ý để máy chủ tải khóa, hoặc tự hạ mức kiểm chứng.

### 5.3. Token bearer và bằng chứng giữ khóa

Token bearer hợp lệ có thể được bên giữ token sử dụng trong phạm vi hiệu lực. Nó không tự chứng minh bên gửi đang giữ khóa riêng của một instance cụ thể.

Có thể đặt yêu cầu ràng buộc token với một khóa hoặc kênh bằng cơ chế được phê duyệt, nhưng bên nhận phải thực sự kiểm chứng ràng buộc đó. Chỉ đặt một bearer token lên một kết nối TLS không tự tạo ra cơ chế ràng buộc token.

Token truy cập cũng không mặc nhiên là token một lần. Nếu yêu cầu chống phát lại từng lệnh nghiệp vụ, cần định danh, thời hạn và trạng thái chống lặp riêng. Xác thực bên gọi không thay idempotency của thao tác.

### 5.4. Thông tin xác thực dùng chung

Khóa API hoặc bí mật dùng chung có thể là một cơ chế trong phạm vi đã chọn. Khi đó cần xác định danh tính gắn với bí mật, quyền, nơi lưu, phân phối, xoay vòng và khả năng thu hồi.

Một bí mật dùng chung cho nhiều dịch vụ làm giảm khả năng phân biệt chủ thể và tăng phạm vi ảnh hưởng khi lộ. Đặc tả phải phản ánh giới hạn đó, thay vì ghi nhận mọi yêu cầu là đã chứng minh một workload riêng biệt.

Không nhúng credential production vào mã nguồn, ảnh triển khai hoặc log. Việc lấy credential phải đi qua nguồn được kiểm soát và có quyền phù hợp.

## 6. Hồ sơ xác thực minh họa

Trong ví dụ production, orders-service gọi billing-service qua kênh mTLS và gửi token truy cập dịch vụ dành cho billing-service.

| Thuộc tính | Chính sách minh họa |
|---|---|
| Danh tính bên gọi | workload:prod:orders-service hoặc danh tính được ma trận cho phép. |
| Danh tính đích | workload:prod:billing-service theo cấu hình đích. |
| Bên cấp credential | Miền cấp danh tính production đã được phê duyệt. |
| Đối tượng nhận token | billing-service production, so khớp theo danh sách được cấu hình. |
| Thời hạn token | Tối đa năm phút kể từ lúc phát hành. |
| Sai lệch thời gian cho phép | Tối đa 30 giây theo quy tắc kiểm tra thời gian được xác định. |
| Quan hệ hai lớp danh tính | Chủ thể token phải khớp danh tính workload đã xác thực trên kênh hoặc ngữ cảnh proxy tin cậy. |
| Thu hồi danh tính | Ngừng chấp nhận yêu cầu mới trong tối đa hai phút từ lúc quyết định thu hồi có hiệu lực. |
| Độ cũ trạng thái thu hồi | Không quá 60 giây tại quyết định chấp nhận đối với thao tác được bảo vệ. |

Đây là lựa chọn của hệ thống giả định, không phải yêu cầu mọi hệ thống phải dùng đồng thời hai cơ chế. Mỗi lớp có mục tiêu và điểm kiểm chứng riêng.

Thời hạn token năm phút không tự đáp ứng thu hồi trong hai phút. Thiết kế phải có cơ chế bổ sung đáp ứng giới hạn thu hồi, kể cả khi token chưa hết hạn hoặc kết nối đã được thiết lập.

Quy tắc sai lệch thời gian phải chỉ rõ cách tính tại các mốc hiệu lực. Nó không phải quyền cho client tự đặt thời hạn dài hơn hồ sơ hoặc bỏ kiểm tra thời gian khi đồng hồ có vấn đề.

## 7. Proxy, ủy quyền người dùng và thông điệp bất đồng bộ

### 7.1. Danh tính tại điểm kết thúc kênh

Xét đường đi:

~~~text
orders-service -> proxy phía orders -> proxy phía billing -> billing-service
~~~

Nếu proxy phía billing kết thúc mTLS, nó là nơi kiểm chứng danh tính đối tác trên kênh đó. billing-service cần một hợp đồng tin cậy để nhận ngữ cảnh đã kiểm chứng, thay vì tự tin mọi trường tên dịch vụ trên request.

Hợp đồng tối thiểu phải làm rõ:

- Proxy nào được phép xác lập ngữ cảnh danh tính.
- Ứng dụng xác thực proxy hoặc ràng buộc đường truyền từ proxy như thế nào.
- Những trường nào do proxy tạo và những trường đầu vào nào phải bị loại bỏ hoặc ghi đè.
- Ngữ cảnh áp dụng cho request, phiên hoặc khoảng thời gian nào.
- Cách ngăn truy cập trực tiếp tới ứng dụng để bỏ qua proxy.
- Cách xử lý khi thiếu, mâu thuẫn hoặc không xác minh được ngữ cảnh.

Một header chỉ trở thành đầu vào tin cậy khi đường cấp và truyền của nó được bảo vệ theo hợp đồng. Tên header tự nó không tạo ra mức tin cậy.

Nếu ứng dụng vẫn mở một cổng khác cho phép client tự đặt ngữ cảnh tương tự, kiến trúc chưa giữ được ranh giới đã đặc tả. Cần kiểm tra mọi đường vào, kể cả đường quản trị hoặc xử lý nội bộ có liên quan.

### 7.2. Gọi thay người dùng

Trong ví dụ, orders-service có quyền kỹ thuật gọi tạo hóa đơn. Tuy nhiên, một yêu cầu người dùng phải có căn cứ rằng người dùng hoặc tác vụ được phép tạo hóa đơn cho đúng tenant và đối tượng.

Cần định nghĩa nguồn ngữ cảnh người dùng, cách xác minh, phạm vi ủy quyền và đối tượng nhận. Không mặc định rằng một token dành cho orders-service được phép chuyển nguyên sang billing-service.

Có thể dùng cơ chế trao đổi hoặc cấp bằng chứng ủy quyền phù hợp. Dù chọn cách nào, bên nhận phải biết:

1. Dịch vụ nào thực sự gọi.
2. Người dùng hoặc tác vụ nào được đại diện, nếu có.
3. Phạm vi hành động được phép.
4. Tenant và tài nguyên nào thuộc phạm vi.
5. Hiệu lực của bằng chứng và chính sách thu hồi.

Một service token hợp lệ không làm mọi giá trị “user_id” hoặc “tenant_id” do bên gọi gửi trở thành đúng. Trách nhiệm kiểm tra quyền tại mỗi ranh giới phải được ghi rõ.

### 7.3. Queue và broker

Xác thực producer với broker và consumer với broker bảo vệ hai quan hệ riêng. Nó không tự chứng minh cho consumer rằng mọi trường trong payload phản ánh đúng producer gốc.

Nếu nghiệp vụ cần chứng minh nguồn phát một thông điệp, cần metadata do broker tin cậy xác lập hoặc bằng chứng tầng thông điệp theo hồ sơ đã phê duyệt. Phải xác định ai được đặt metadata đó và consumer kiểm chứng ra sao.

Kiểm tra nguồn thông điệp cũng không thay xử lý trùng, kiểm tra quyền nghiệp vụ hoặc đối soát. Một producer hợp lệ vẫn có thể gửi lại cùng lệnh.

## 8. Vòng đời credential và hành vi khi phụ thuộc lỗi

### 8.1. Cấp và làm mới

Credential phải được cấp đúng chủ thể, phạm vi và thời hạn. Instance mới không được nhận bí mật của dịch vụ khác qua một kho hoặc đường phân phối có quyền quá rộng.

Việc làm mới cần bắt đầu đủ sớm theo chính sách để tránh gián đoạn, nhưng credential cũ không được tự kéo dài ngoài hiệu lực. Khi không làm mới được, hệ thống phải thể hiện lỗi và giữ điều kiện xác thực, không chuyển sang một bí mật dự phòng không kiểm soát.

Các sự kiện cấp, đổi ánh xạ danh tính, làm mới và từ chối cần có audit. Khóa riêng hoặc token đầy đủ không được đưa vào bằng chứng vận hành thông thường.

### 8.2. Xoay vòng bình thường và thu hồi do sự cố

Xoay vòng có kế hoạch có thể cần khoảng chồng lấn để các bằng chứng còn hợp lệ được kiểm chứng trong cửa sổ đã đặt. Thiết kế phải xác định khóa nào dùng để phát hành và khóa nào chỉ còn dùng để kiểm tra.

Nếu credential hoặc khóa bị xâm phạm, chính sách thu hồi có thể yêu cầu chấm dứt tin cậy trước khi hết hạn tự nhiên. Không để quy tắc chồng lấn của xoay vòng bình thường vô tình cho phép tiếp tục sử dụng credential đã bị thu hồi.

Thu hồi có thể theo nhiều phạm vi:

| Phạm vi | Ví dụ mục tiêu |
|---|---|
| Một credential | Loại bỏ một chứng thư hoặc token bị lộ theo khả năng hệ thống. |
| Một instance | Ngừng chấp nhận thực thể triển khai cụ thể. |
| Một service identity | Chặn mọi instance mang danh tính dịch vụ đó. |
| Một khóa phát hành hoặc miền tin cậy | Ngừng tin các bằng chứng thuộc phạm vi bị ảnh hưởng. |

Phải chỉ rõ hệ thống hỗ trợ phạm vi nào và thời gian hiệu lực. Một nút giao diện “revoke” không chứng minh mọi verifier đã ngừng chấp nhận.

### 8.3. Kết nối lâu sống và cache

Thông tin xác thực thường được kiểm tra tại thời điểm thiết lập kênh hoặc khi nhận token. Nếu kết nối được tái sử dụng lâu, cần có cách duy trì giới hạn hiệu lực cho các yêu cầu tiếp theo.

Trong hồ sơ ví dụ, yêu cầu mới phải bị chặn trong tối đa hai phút sau thu hồi service identity, kể cả trên kết nối mở trước đó. Thiết kế có thể tái đánh giá ngữ cảnh, cập nhật chính sách tại proxy hoặc dùng giới hạn phiên phù hợp; bằng chứng phải đo kết quả tại nơi chấp nhận request.

Không tự kéo dài hiệu lực danh tính vì kết nối vẫn hoạt động. Các phiên được nối lại cũng phải chịu cùng chính sách, không trở thành đường bỏ qua thu hồi.

Cache khóa đã được xác minh có thể hỗ trợ kiểm tra token trong phạm vi cho phép. Tuy nhiên, “còn khóa để kiểm tra chữ ký” khác với “danh tính vẫn được phép”. Các trạng thái khóa, credential và danh tính phải được áp dụng đúng vai trò.

### 8.4. Không khả dụng của dịch vụ danh tính

| Tình huống | Hành vi cần đặc tả |
|---|---|
| Không cấp được token mới | Không tạo token thay thế bằng dữ liệu tự khai; báo lỗi phù hợp. |
| Token còn hiệu lực và đủ bằng chứng cục bộ | Có thể tiếp tục trong phạm vi chính sách, nếu trạng thái thu hồi và các điều kiện khác vẫn đáp ứng. |
| Không nhận diện được khóa của token | Chỉ tra cứu nguồn cấu hình tin cậy theo giới hạn; chưa xác minh thì không chấp nhận. |
| Trạng thái thu hồi quá cũ | Không chấp nhận thao tác được bảo vệ bằng một kết luận không còn đủ độ mới. |
| Đồng hồ không đủ tin cậy để xác minh hiệu lực | Không tắt kiểm tra thời gian để cho qua. |
| Proxy không cung cấp được ngữ cảnh đã kiểm chứng | Không lấy một header từ client để thay thế. |

Trong ví dụ, dữ liệu thu hồi dùng cho quyết định chấp nhận không được cũ quá 60 giây. Nếu không duy trì được điều kiện đó, thao tác được bảo vệ phải bị từ chối tạm thời.

Quy tắc này có thể làm giảm availability khi phụ thuộc quản lý danh tính lỗi. Cần đưa tác động đó vào yêu cầu dịch vụ, năng lực dự phòng và phép thử; không âm thầm thay đổi mục tiêu xác thực để che gián đoạn.

## 9. Bộ yêu cầu service-to-service authentication mẫu

### SR-STA-001 — Cấp và ánh xạ danh tính có thẩm quyền

Mỗi workload production phải được cấp credential cho danh tính đã đăng ký sau khi nguồn cấp xác minh bằng chứng bootstrap được phép.

Danh tính phải phân biệt môi trường và phạm vi triển khai theo chính sách. Workload không được chọn một service identity khác bằng trường tự khai. Bên nhận chỉ ánh xạ chủ thể từ bằng chứng đã kiểm chứng hoặc ngữ cảnh proxy được bảo vệ.

Bằng chứng nghiệm thu gồm workload sai môi trường, workload không được đăng ký và thay đổi tên tự khai. Không trường hợp nào được nhận hoặc sử dụng quyền của orders-service production trái phép.

### SR-STA-002 — Kiểm chứng hai phía của kênh

Đường gọi production trong hồ sơ phải dùng kênh mTLS đáp ứng cấu hình bảo mật đã phê duyệt. Client phải xác minh danh tính đích; bên kết thúc kênh phải kiểm chứng credential client và ánh xạ đúng workload.

Không cho phép tắt kiểm tra chứng thư, chuyển sang đường không xác thực hoặc dùng đường truyền khác để hoàn thành cùng thao tác sau lỗi xác minh.

Bằng chứng phải gồm đích sai danh tính, client thiếu chứng thư, nguồn cấp ngoài tập tin cậy, credential chưa có hiệu lực hoặc hết hạn và đường truy cập thay thế. Không dữ liệu nghiệp vụ nhạy cảm nào được gửi cho đích chưa được xác minh theo chính sách.

### SR-STA-003 — Token đúng issuer, audience, chủ thể và hiệu lực

billing-service phải kiểm tra tính toàn vẹn, issuer, loại token, audience, chủ thể, thời gian và phạm vi theo hồ sơ.

Token chỉ sống tối đa năm phút từ phát hành; sai lệch thời gian tối đa 30 giây theo quy tắc đã xác định. Token dành cho dịch vụ hoặc môi trường khác không được chấp nhận. Trong ví dụ, chủ thể token phải khớp workload identity đã kiểm chứng trên kênh hoặc qua ngữ cảnh proxy tin cậy.

Khóa và thuật toán xác minh phải thuộc chính sách máy chủ. Nội dung token chưa xác minh không được dùng để cấp quyền hoặc chọn nguồn khóa tùy ý.

### SR-STA-004 — Ngữ cảnh proxy và quyền nghiệp vụ không bị giả mạo

Chỉ proxy đã được cấu hình và xác thực mới được cung cấp ngữ cảnh danh tính gốc. Đầu vào có cùng tên trường từ nguồn không tin cậy phải bị loại bỏ, ghi đè hoặc từ chối theo hợp đồng.

Mọi đường tới billing-service phải giữ điều kiện đó hoặc tự thực hiện xác thực tương đương. Chủ thể đã xác thực vẫn phải được kiểm tra quyền theo hành động, tenant và tài nguyên.

notification-service không được tạo hóa đơn chỉ vì có credential hợp lệ. Nếu hành động thay người dùng, ngữ cảnh ủy quyền phải được xác minh riêng, không lấy user_id hoặc tenant_id tự khai làm căn cứ duy nhất.

### SR-STA-005 — Xoay vòng và thu hồi đạt thời hạn

Hệ thống phải hỗ trợ làm mới credential và thay khóa theo quy trình có bằng chứng. Quy tắc chồng lấn bình thường không áp dụng để giữ tin cậy credential đã bị thu hồi do sự cố.

Sau khi quyết định thu hồi service identity có hiệu lực, mọi verifier trong phạm vi phải ngừng chấp nhận yêu cầu mới của danh tính đó trong tối đa hai phút. Phạm vi kiểm thử gồm token chưa hết hạn, kết nối đang mở, cache và mọi replica nhận request.

Trạng thái thu hồi tại quyết định chấp nhận không được cũ quá 60 giây. Hết thời hạn mà không có bằng chứng đủ mới thì từ chối thao tác được bảo vệ. Những hành động đã được chấp nhận trước đó không tự bị hoàn tác; cách xử lý công việc đang chạy cần chính sách riêng.

### SR-STA-006 — Lỗi kiểm chứng không trở thành danh tính hợp lệ

Nếu không thể kiểm chứng chữ ký, chuỗi tin cậy, hiệu lực, danh tính hoặc ngữ cảnh bắt buộc, hệ thống không được tiếp tục như đã xác thực.

Trong cấu hình minh họa, một lần tra cứu khóa hoặc trạng thái từ phụ thuộc có giới hạn chờ 500 ms và chịu deadline chung của request. Khi hết thời gian, không dùng credential mặc định hoặc bỏ kiểm tra.

Tra cứu khóa chỉ tới nguồn được cấu hình cho issuer tin cậy. Việc làm mới phải có giới hạn tài nguyên và phối hợp để đầu vào lạ không tạo số lượng tra cứu không giới hạn. Thông báo ra ngoài không chứa token, khóa hay chi tiết nội bộ nhạy cảm.

### SR-STA-007 — Audit và khả năng đối soát quyết định

Mỗi quyết định cần có định danh request, điểm kiểm chứng, phương thức, kết quả, lý do và danh tính đã xác minh nếu có. Các quyết định cấp, đổi ánh xạ, xoay vòng và thu hồi phải có mốc thời gian và chủ thể thực hiện.

Claim của request thất bại không được ghi thành danh tính đã xác thực. Log có thể lưu thông tin thử khai trong trường được phân biệt rõ là không tin cậy và được xử lý an toàn.

Không ghi token đầy đủ, khóa riêng hoặc bí mật bootstrap. Dữ liệu quan sát phải đủ để xác định request được chấp nhận bởi replica nào, theo chính sách nào và trước hay sau mốc thu hồi.

## 10. Ma trận kiểm thử và bằng chứng

| Kịch bản | Điều kiện thử | Kết quả phải chứng minh |
|---|---|---|
| Đường hợp lệ | orders-service production có đầy đủ bằng chứng và quyền. | Xác thực đúng chủ thể, thao tác hợp lệ được xử lý. |
| Sai đích | Client kết nối tới bên không có danh tính billing-service mong đợi. | Từ chối kênh; không gửi nội dung nghiệp vụ nhạy cảm. |
| Sai miền tin cậy | Credential của môi trường thử hoặc nguồn cấp ngoài phạm vi. | Không được ánh xạ thành chủ thể production. |
| Token sai đối tượng nhận | Token hợp lệ về chữ ký nhưng dành cho dịch vụ khác. | Từ chối tại billing-service. |
| Token bị sửa hoặc sai mục đích | Claim bị thay, token không đáp ứng loại được phép. | Không cấp danh tính hoặc quyền từ nội dung đó. |
| Thời gian tại biên | Token hết hạn, chưa hiệu lực hoặc vượt sai lệch cho phép. | Áp đúng hồ sơ, không bỏ kiểm tra để xử lý lỗi đồng hồ. |
| Hai lớp danh tính mâu thuẫn | Token khai orders-service nhưng kênh chứng minh danh tính khác. | Từ chối theo quy tắc khớp danh tính của ví dụ. |
| Giả ngữ cảnh proxy | Gửi header danh tính từ đường không tin cậy hoặc gọi thẳng app. | Không biến trường tự khai thành principal hợp lệ. |
| Thiếu quyền nghiệp vụ | notification-service gọi tạo hóa đơn. | Xác thực có thể đạt nhưng thao tác vẫn bị từ chối. |
| Giả ủy quyền người dùng | Dịch vụ gửi tenant hoặc người dùng ngoài phạm vi được phép. | Không dùng quyền dịch vụ để vượt quyền nghiệp vụ. |
| Thu hồi khi kết nối còn mở | Giữ kết nối và token còn hạn, thu hồi danh tính rồi gửi tiếp. | Mọi replica ngừng chấp nhận yêu cầu mới trong hai phút. |
| Phụ thuộc xác thực lỗi | Làm chậm cấp phát, tra cứu hoặc cập nhật trạng thái. | Hành vi đúng chính sách cache, độ mới và từ chối; không có đường bỏ qua. |
| Xoay vòng có kế hoạch | Thay credential và khóa trong cửa sổ đã phê duyệt. | Credential mới dùng được; credential cũ chỉ được chấp nhận đúng chính sách. |
| Sự kiện qua broker | Payload tự khai nguồn khác với bằng chứng tin cậy. | Không chấp nhận danh tính gốc chỉ theo nội dung payload. |

Ví dụ ca nghiệm thu thu hồi:

~~~gherkin
Feature: Thu hồi danh tính có hiệu lực cả trên kết nối tái sử dụng

  Scenario: Không tiếp tục nhận request bằng phiên đã xác thực trước đó
    Given orders-service đã thiết lập kết nối tới billing-service
    And token của orders-service vẫn chưa hết hạn
    When quyết định thu hồi danh tính có hiệu lực tại thời điểm T0
    And tiếp tục gửi request qua các kết nối cũ và các replica nhận
    Then không request mới nào của danh tính đó được chấp nhận sau T0 cộng hai phút
    And không có fallback bỏ kiểm tra hoặc dùng credential chung
    And audit đủ để xác định các quyết định trước và sau thời hạn
~~~

Phép thử phải đo tại điểm chấp nhận thực tế, không chỉ đo thời điểm API quản trị trả lời đã thu hồi. Cần bao phủ cache, proxy, kết nối cũ và replica ít nhận lưu lượng.

Với xoay vòng, cần kiểm tra cả tính liên tục của đường hợp lệ và khả năng từ chối ngoài cửa sổ. Chỉ chứng minh credential mới dùng được chưa chứng minh credential cũ đã ngừng được chấp nhận đúng hạn.

Hồ sơ thử nên lưu phiên bản chính sách, ánh xạ danh tính, điểm kết thúc kênh, nguồn cấp thử, cấu hình cache, mốc thời gian và kết quả từng đường gọi. Dùng credential của môi trường thử được kiểm soát; không đưa bí mật production vào tài liệu hoặc log nghiệm thu.

## 11. Logging và quan sát quyết định

Nên phân biệt lỗi xác thực, lỗi phân quyền và lỗi phụ thuộc. Nếu gộp tất cả thành “không được phép”, khó phát hiện dịch vụ cấp danh tính đang gián đoạn hoặc một cấu hình trust mới làm chặn toàn bộ caller.

Một sự kiện đã xác thực minh họa:

~~~json
{
  "event": "service_authentication",
  "request_id": "example-request",
  "verifier": "billing-ingress",
  "method": "mtls-and-service-token",
  "principal": "workload:prod:orders-service",
  "decision": "accepted",
  "policy_version": 7,
  "revocation_state_age_seconds": 12
}
~~~

Đây là cấu trúc minh họa, không phải giao diện của một sản phẩm. Việc được chấp nhận ở đây chỉ thể hiện quyết định xác thực; quyết định quyền nghiệp vụ cần sự kiện hoặc trường riêng.

Các chỉ số hữu ích gồm tỷ lệ lỗi theo nguyên nhân, lỗi làm mới credential, độ cũ dữ liệu thu hồi, lỗi đồng hồ và khác biệt giữa danh tính kênh với token. Không dùng định danh request hoặc credential có số lượng không giới hạn làm nhãn cho mọi metric.

Chi tiết phục vụ điều tra chỉ dành cho người có quyền. Phản hồi cho bên gọi nên đủ xử lý lỗi theo hợp đồng nhưng không lộ nội dung credential, cấu trúc khóa hoặc danh sách chủ thể nội bộ.

## 12. Những cách viết dễ gây hiểu sai

| Cách viết chưa đủ | Điểm thiếu | Cách làm rõ |
|---|---|---|
| “Dịch vụ trong mạng nội bộ được tin.” | Mạng không tự chứng minh danh tính và quyền. | Xác định nguồn cấp, bằng chứng và ma trận gọi. |
| “Có TLS là xác thực hai bên.” | Có thể chỉ kiểm chứng một phía hoặc tắt kiểm tra đích. | Nêu rõ mỗi bên kiểm chứng ai tại điểm kết thúc nào. |
| “Chứng thư hợp lệ thì được gọi mọi API.” | Xác thực không thay phân quyền. | Ánh xạ principal và kiểm tra quyền hành động, tenant, tài nguyên. |
| “Token giải mã được là hợp lệ.” | Chưa kiểm tra tính toàn vẹn và các điều kiện chấp nhận. | Kiểm tra issuer, khóa, mục đích, audience, thời gian và trạng thái. |
| “Có chữ ký đúng thì dùng ở đâu cũng được.” | Token có thể dành cho dịch vụ hoặc môi trường khác. | Ràng buộc đối tượng nhận và miền tin cậy. |
| “Proxy đã xác thực nên app tin mọi header.” | Header có thể từ client hoặc đường bỏ qua. | Có hợp đồng ngữ cảnh và bảo vệ mọi đường vào. |
| “Token ngắn hạn tự đáp ứng thu hồi ngay.” | Credential còn hạn hoặc phiên cũ vẫn có thể được dùng. | Đặt thời hạn thu hồi và cơ chế thực thi trên mọi verifier. |
| “Dịch vụ danh tính lỗi thì cho qua tạm.” | Biến thiếu bằng chứng thành chủ thể hợp lệ. | Đặc tả cache, độ mới và từ chối khi không đủ điều kiện. |
| “Dùng mTLS cùng bearer token thì token đã gắn với một khóa.” | Hai lớp có thể độc lập, chưa có kiểm chứng ràng buộc cụ thể. | Nếu cần ràng buộc, đặc tả cơ chế và phép thử riêng. |

## 13. Duy trì yêu cầu trong vòng đời phát triển

Khi phân tích nghiệp vụ, liệt kê các đường gọi, chủ thể kỹ thuật và trường hợp hành động thay người dùng. Khi mô hình hóa đe dọa, đưa vào mạo danh, lộ credential, sai audience, proxy không tin cậy và thu hồi không đồng đều.

Khi thiết kế, gắn mỗi yêu cầu SR-STA với nguồn cấp danh tính, điểm kết thúc kênh, verifier token, nơi phân quyền và đường cập nhật trạng thái. Không để một lớp tự giả định rằng lớp khác đã kiểm tra mà không có hợp đồng.

Khi phát triển và nghiệm thu, bao phủ đường hợp lệ, credential sai, chủ thể có danh tính nhưng thiếu quyền và lỗi phụ thuộc. Khi vận hành, theo dõi hiệu lực thu hồi và khả năng làm mới, không chỉ tỷ lệ kết nối thành công.

Thay gateway, thêm vùng triển khai, đổi issuer, mở endpoint mới hoặc thay cách ủy quyền đều có thể thay ranh giới tin cậy. Cần cập nhật ma trận, hồ sơ kiểm chứng và bằng chứng tương ứng.

Bài tập áp dụng: một dịch vụ đơn hàng gọi dịch vụ thanh toán, dịch vụ kho và broker gửi sự kiện. Hãy xác định danh tính tại từng ranh giới, bằng chứng được chấp nhận, audience, quyền theo tenant và cách truyền ngữ cảnh người dùng. Viết thêm yêu cầu thu hồi đo được và ca thử khi token chưa hết hạn, kết nối còn mở nhưng danh tính đã bị thu hồi.

