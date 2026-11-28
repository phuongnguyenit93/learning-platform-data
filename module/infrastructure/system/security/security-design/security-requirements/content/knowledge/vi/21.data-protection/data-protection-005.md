# Data tokenization

## 1. Token hóa dữ liệu giải quyết yêu cầu bảo mật nào?

Data tokenization là việc thay một giá trị dữ liệu cần bảo vệ bằng một giá trị đại diện, gọi là token, để các thành phần được phép vẫn thực hiện công việc mà không cần thường xuyên tiếp xúc với dữ liệu gốc.

Ví dụ, hệ thống quản lý đơn hàng có thể lưu một mã đại diện cho số điện thoại. Hệ thống báo cáo chỉ cần mã đó để đếm số khách hàng quay lại. Dịch vụ giao hàng mới cần lấy lại số điện thoại, trong một nghiệp vụ đã được cấp quyền.

Mục tiêu bảo mật không phải chỉ là “dữ liệu trông khác đi”. Mục tiêu là giảm số nơi nhìn thấy dữ liệu gốc, giới hạn khả năng khôi phục hoặc suy ra dữ liệu, và kiểm soát những cách token được sử dụng.

Trong phạm vi thiết kế yêu cầu bảo mật, cần trả lời được:

- Trường dữ liệu nào cần được thay thế, ở những đường vào và đầu ra nào?
- Thành phần nào được nhìn thấy dữ liệu gốc, thành phần nào chỉ được giữ token?
- Token có cho phép nối các bản ghi của cùng một người không? Trong phạm vi nào?
- Ai được chuyển token trở lại dữ liệu gốc, cho mục đích gì?
- Nếu mất kho ánh xạ hoặc khóa, hệ thống chấp nhận mất khả năng nào?
- Kiểm thử và bằng chứng nào chứng minh dữ liệu gốc không đi vào nơi bị cấm?

Thuật ngữ tokenization có thể được dùng cho các cơ chế khác nhau. Chẳng hạn, một nền tảng bảo vệ dữ liệu có thể gọi cả phép biến đổi mật mã hai chiều và HMAC một chiều là cách tạo token. Vì vậy, yêu cầu phải ghi rõ khả năng khôi phục và liên kết, thay vì suy từ tên tính năng. [Tài liệu Pseudonymization của Google Cloud](https://docs.cloud.google.com/sensitive-data-protection/docs/pseudonymization).

**Token dữ liệu trong bài này không phải access token hay refresh token dùng để xác thực.** Dù vậy, nếu một API cho phép người giữ token thực hiện hành động mà không kiểm tra quyền bổ sung, token dữ liệu có thể trở thành một phương tiện cấp quyền trên thực tế. Thiết kế phải nhận diện trường hợp đó.

## 2. Phân biệt với những cách bảo vệ dữ liệu gần giống

| Cơ chế | Điều nó thực hiện | Giới hạn cần thể hiện trong yêu cầu |
| --- | --- | --- |
| Token hóa có kho ánh xạ | Thay dữ liệu bằng mã đại diện; kho lưu liên hệ để tra lại | Kho và đường tra lại trở thành tài sản đặc biệt nhạy cảm |
| Biến đổi mật mã có thể đảo | Tạo giá trị thay thế có thể khôi phục khi có khóa và ngữ cảnh thích hợp | Quyền giữ khóa và sử dụng dịch vụ khôi phục quyết định mức bảo vệ |
| Băm không khóa | Tạo giá trị băm từ đầu vào | Với miền đầu vào dễ đoán, có thể thử các ứng viên và so sánh |
| HMAC làm định danh thay thế | Dùng khóa bí mật để tạo giá trị đối chiếu theo thiết kế | Không có thao tác giải mã; khóa hoặc API tính token bị lạm dụng vẫn có thể hỗ trợ dò ứng viên |
| Masking khi hiển thị | Che một phần hoặc toàn bộ giá trị ở giao diện | Dữ liệu đầy đủ có thể vẫn có trong API, HTML, log hoặc cơ sở dữ liệu |
| Mã hóa khi lưu trữ | Bảo vệ nội dung lưu bằng khóa | Ứng dụng có quyền giải mã vẫn có thể đọc và phát tán dữ liệu gốc |
| Ẩn danh hóa | Hướng tới hạn chế khả năng nhận diện trong ngữ cảnh đánh giá cụ thể | Không được kết luận đã ẩn danh chỉ vì đã thay một trường bằng token |

Các cơ chế có thể kết hợp. Kho ánh xạ vẫn có thể cần mã hóa khi lưu trữ; giao diện nhận dữ liệu gốc hợp lệ vẫn có thể cần masking. Mỗi cơ chế phải gắn với một rủi ro và một điều kiện kiểm chứng riêng.

### Token hóa không tự xóa khả năng nhận diện

Một bảng chỉ giữ token khách hàng, thời điểm giao dịch, vị trí và các hành vi hiếm vẫn có thể cho phép liên kết với thông tin khác.

Nếu cùng một token xuất hiện ổn định ở nhiều hệ thống, người có các tập dữ liệu đó có thể nối bản ghi mà không biết tên thật. Đây có thể là tính năng cần thiết cho báo cáo, đồng thời là rủi ro cần giới hạn.

Yêu cầu nên chỉ ra dữ liệu phụ nào còn được giữ, ai có thể kết hợp chúng và mục tiêu giảm nhận diện nào cần đánh giá. Không dùng câu “đã token hóa nên có thể chia sẻ công khai” làm tiêu chí chấp nhận.

## 3. Bắt đầu từ luồng dữ liệu và mô hình đe dọa

Giả sử nền tảng có ba nhóm chức năng:

1. Dịch vụ hồ sơ tiếp nhận thông tin liên hệ của khách hàng.
2. Hệ thống đơn hàng lưu quan hệ giữa đơn hàng và khách hàng.
3. Dịch vụ thực hiện giao hàng cần dùng thông tin liên hệ tại thời điểm giao.

Bộ phận phân tích chỉ cần đếm khách quay lại, không cần số điện thoại. Nhân viên hỗ trợ chỉ được xem thông tin trong những yêu cầu hỗ trợ thuộc phạm vi được phân công.

### 3.1. Tài sản và ranh giới tin cậy

Cần lập danh sách ít nhất các tài sản sau:

- Dữ liệu gốc và mọi bản sao tạm thời.
- Token, namespace của token và siêu dữ liệu đi kèm.
- Kho ánh xạ, chỉ mục phục vụ tìm kiếm và bản sao lưu.
- Khóa mật mã nếu cơ chế sử dụng khóa.
- Danh tính dịch vụ, chính sách truy cập và quyền vận hành.
- Sự kiện, log, trace, hàng đợi lỗi, tệp xuất và dữ liệu khôi phục.

Một sơ đồ khái niệm cho mô hình có kho:

~~~mermaid
flowchart LR
    A["Nguồn dữ liệu được phép"] --> B["Điểm tiếp nhận và token hóa"]
    B --> C["Kho ánh xạ được bảo vệ"]
    B --> D["Dữ liệu nghiệp vụ chỉ chứa token"]
    D --> E["Báo cáo trong phạm vi được phép"]
    F["Dịch vụ nghiệp vụ cần dữ liệu gốc"] --> G["Kiểm tra danh tính, quyền và mục đích"]
    G --> C
    C --> F
~~~

Mũi tên thể hiện luồng được thiết kế, không tự chứng minh có kiểm soát bảo mật. Đường từ dịch vụ nghiệp vụ tới kho phải được bảo vệ và kiểm chứng như một API nhạy cảm.

### 3.2. Từ đe dọa đến kết quả cần đạt

| Đe dọa | Tác động | Kết quả yêu cầu cần hướng tới |
| --- | --- | --- |
| Bản sao cơ sở dữ liệu báo cáo bị lấy cắp | Lộ dữ liệu gốc hoặc liên kết hồ sơ ngoài dự kiến | Không chứa trường gốc bị cấm; phạm vi liên kết token được giới hạn |
| Dịch vụ đơn hàng bị chiếm | Kẻ tấn công gọi khôi phục dữ liệu hàng loạt | Danh tính này không có quyền detokenize; quyền đọc đơn không kéo theo quyền đọc dữ liệu gốc |
| Người dùng đổi tenant trong request | Tra token của tổ chức khác | Kiểm tra tenant từ ngữ cảnh đáng tin cậy tại phía phục vụ |
| Người có quyền gọi tokenize nhập nhiều ứng viên | Xây bảng đối chiếu số điện thoại với token | Giới hạn mục đích, phạm vi, tần suất và các đầu ra cho phép |
| Dữ liệu gốc nằm trong trace hoặc hàng đợi lỗi | Vượt qua ranh giới token hóa | Bảo vệ cả đường lỗi, retry và vận hành |
| Hai giá trị khác nhau nhận cùng mã đại diện | Gắn nhầm thông tin giữa chủ thể | Phát hiện va chạm và bảo toàn ánh xạ theo hợp đồng |
| Khôi phục bản sao lưu cũ | Token bị ngừng hoặc ánh xạ đã xóa hoạt động lại | Đối soát trạng thái vòng đời trước khi mở lại dịch vụ |
| Dịch vụ token hóa không sẵn sàng | Đường dự phòng lưu dữ liệu gốc vào bảng bị cấm | Từ chối hoặc đệm trong vùng đã được phê duyệt, không âm thầm hạ mức bảo vệ |

Đối với mỗi rủi ro, cần xác định điểm thực thi, owner và bằng chứng. Một yêu cầu chỉ ghi “dùng tokenization” chưa cho biết rủi ro nào thực sự được giảm.

## 4. Chọn đặc tính của token trước khi chọn sản phẩm

### 4.1. Khả năng khôi phục

**Token có thể khôi phục:** hệ thống có đường hợp lệ để lấy lại dữ liệu gốc, bằng kho ánh xạ hoặc cơ chế mật mã phù hợp. Yêu cầu phải bao phủ cả quyền gọi đường đó và quyền truy cập trực tiếp dữ liệu hoặc khóa phía sau.

**Token một chiều:** thiết kế không cung cấp thao tác đảo để trả dữ liệu gốc. Tuy nhiên, nếu vẫn giữ một bảng nguồn cùng token hoặc vẫn có thể dò đầu vào qua API, hệ thống có thể còn cách liên kết với danh tính. “Một chiều” của phép biến đổi không phải cam kết rằng toàn bộ hệ thống không thể nhận diện.

Trước khi yêu cầu không thể khôi phục, cần xác định nghiệp vụ có còn cần gửi thông báo, giao hàng, hỗ trợ hoặc sửa dữ liệu hay không. Không gọi một thiết kế là một chiều nếu nó vẫn duy trì một bảng đảo được sử dụng thường xuyên.

### 4.2. Tính ổn định và khả năng nối dữ liệu

Cùng một đầu vào có thể được thiết kế để:

- Có cùng token trong một tập dữ liệu và một mục đích.
- Có token khác nhau giữa các tenant hoặc các mục đích.
- Nhận token mới mỗi lần xuất hiện.

Không được suy rằng token ngẫu nhiên luôn không ổn định. Dịch vụ có thể sinh mã ngẫu nhiên lần đầu rồi tái sử dụng ánh xạ đó khi cùng giá trị xuất hiện lại.

Ngược lại, một phép biến đổi xác định có thể tạo mã khác nhau khi thay đổi ngữ cảnh hoặc khóa. Đặc tính “xác định” phải được mô tả cùng miền áp dụng.

Ví dụ hợp đồng cho báo cáo:

~~~text
Trong cùng tenant và cùng mục đích analytics_customer:
    cùng giá trị đã chuẩn hóa -> cùng token đang được sử dụng

Giữa hai mục đích analytics_customer và delivery_contact:
    không dùng chung ánh xạ token

Giữa hai tenant:
    không có API nối token hoặc tra ánh xạ xuyên tenant cho caller thông thường
~~~

Các điều kiện này cần được thực thi bằng cơ chế phù hợp. Thêm tên tenant vào một cột nhưng vẫn dùng cùng token toàn cục không tự ngăn người có hai tập dữ liệu nối chúng lại.

### 4.3. Định dạng và không gian token

Token phải phù hợp schema, độ dài và ký tự mà hệ thống xử lý. Nhưng giữ nguyên định dạng dữ liệu gốc có thể làm giảm không gian giá trị hoặc giữ lại đặc điểm dễ liên kết.

Yêu cầu cần phân biệt:

- Cần đúng độ dài để tương thích hệ thống cũ.
- Cần giữ tiền tố phục vụ định tuyến.
- Cần giữ một phần dữ liệu cho người vận hành nhận biết.
- Chỉ cần một mã đại diện không tiết lộ dữ liệu.

Mỗi phần được giữ lại là thông tin có thể lộ. Nếu giữ đuôi số điện thoại, phải ghi rõ bên nào được xem, lý do và rủi ro kết hợp với dữ liệu khác.

Một token có hình thức giống dữ liệu thật cũng có thể bị hệ thống phía sau hiểu nhầm. Cần quy tắc phân biệt loại dữ liệu và ngăn gửi token vào kênh liên lạc như thể đó là số điện thoại thật.

## 5. Hai mô hình kiến trúc và các nghĩa vụ đi kèm

### 5.1. Token ngẫu nhiên có kho ánh xạ

Một mô hình khái niệm:

~~~text
(namespace, token)
    -> dữ liệu gốc được bảo vệ
    -> tenant, mục đích, loại dữ liệu
    -> trạng thái và phiên bản
    -> thông tin vòng đời cần thiết
~~~

Dịch vụ sinh mã từ nguồn ngẫu nhiên phù hợp, kiểm tra ràng buộc duy nhất và lưu ánh xạ. Nếu chính sách cần token ổn định, dịch vụ còn phải nhận ra giá trị đã có trong đúng namespace mà không phơi bày thêm dữ liệu qua chỉ mục.

Các yêu cầu quan trọng:

- Không dùng số thứ tự dễ đoán nếu yêu cầu dựa vào độ khó đoán của token.
- Chọn không gian token theo số lượng phát hành, tuổi thọ và mức rủi ro va chạm.
- Có ràng buộc duy nhất và xử lý va chạm trước khi trả thành công.
- Chỉ trả token sau khi ánh xạ cần thiết đã được ghi bền.
- Không để lỗi ghi kho tạo token đã trả cho caller nhưng không thể giải nghĩa theo hợp đồng.
- Bảo vệ mọi chỉ mục có thể nối giá trị gốc với token.
- Giới hạn truy cập kho, bản sao và đường xuất dữ liệu.

Độ khó đoán không thay thế phân quyền. Một token ngẫu nhiên bị lộ từ tệp xuất vẫn có thể bị dùng để yêu cầu dữ liệu nếu API chỉ kiểm tra token tồn tại.

Với yêu cầu ổn định, hai request đồng thời cho cùng đầu vào cần có kết quả nhất quán trong phạm vi đã định. Với yêu cầu tạo token mới mỗi lần, hệ thống không được tự gom các request khác nhau chỉ vì giá trị gốc giống nhau. Chính sách retry phải phân biệt lỗi lặp của cùng thao tác với một thao tác nghiệp vụ mới.

### 5.2. Token được tạo bằng biến đổi mật mã

Thiết kế có thể tạo giá trị đại diện từ dữ liệu, khóa và ngữ cảnh, thay vì lưu một ánh xạ riêng cho từng giá trị.

Yêu cầu phải chỉ rõ:

- Phép biến đổi có thể đảo hay một chiều.
- Cách tách miền giữa tenant, trường dữ liệu và mục đích.
- Thành phần nào được dùng khóa; thành phần nào chỉ được gọi một thao tác được kiểm soát.
- Thông tin phiên bản và ngữ cảnh cần giữ để xử lý token về sau.
- Hành vi khi khóa mất, bị ngừng sử dụng, bị xâm phạm hoặc được thay thế.
- Hành vi với token bị sửa đổi, sai ngữ cảnh hoặc sai định dạng.

Việc không có bảng ánh xạ từng giá trị không có nghĩa hệ thống không giữ trạng thái hoặc không cần kiểm soát truy cập. Kho khóa, chính sách, dữ liệu nguồn và bản sao lưu vẫn có thể quyết định khả năng tái nhận diện.

Không tự ghép các phép biến đổi hoặc tự thiết kế thuật toán chỉ để khớp schema cũ. Khi ràng buộc định dạng xung đột với mục tiêu bảo vệ, yêu cầu cần làm rõ ưu tiên và phần rủi ro phải được đánh giá.

### 5.3. Đừng chọn cơ chế trước khi chốt tính chất cần đạt

| Nhu cầu nghiệp vụ | Tính chất phải đặc tả | Điểm phải xem xét |
| --- | --- | --- |
| Đếm khách hàng quay lại | Token ổn định trong miền báo cáo | Liên kết ngoài miền, thay đổi phiên bản và dữ liệu phụ |
| Giao hàng theo đơn | Khôi phục có kiểm soát | Quyền theo đơn, tenant, trạng thái nghiệp vụ và mục đích |
| Xuất dữ liệu cho bên nhận khác | Token theo phạm vi bên nhận | Bên nhận có nguồn nào để nối với danh tính hay không |
| Giữ schema cũ | Giới hạn định dạng cụ thể | Không gian token, phân biệt dữ liệu thật và token, tính toàn vẹn |
| Không cần biết lại dữ liệu gốc | Không cung cấp đường đảo trong thiết kế | Bản sao nguồn, bảng liên kết và khả năng dò ứng viên |
| Ngừng sử dụng từng token | Trạng thái và thời hạn có hiệu lực | Token có thể được giải mã offline hoặc còn trong cache không |

Nếu mọi consumer đều được giữ khóa để đảo token offline, một yêu cầu vô hiệu hóa riêng một token trong 60 giây cần thêm cơ chế và ranh giới thực thi. Chỉ thay trạng thái ở một API trung tâm không chứng minh các consumer đó đã dừng khôi phục.

## 6. Đặc tả miền dữ liệu và quy tắc chuẩn hóa

Token hóa chính xác phải bảo toàn đúng ý nghĩa của dữ liệu. Hai cách viết có thể cùng chỉ một thông tin, hoặc có thể là hai thông tin khác nhau.

Ví dụ, việc bỏ dấu phân cách trong một mã có thể hợp lệ với loại mã này nhưng sai với loại mã khác. Không được mặc định mọi chuỗi đều có thể đổi thành chữ thường, bỏ khoảng trắng hoặc bỏ số 0 đầu.

Yêu cầu chuẩn hóa cần ghi rõ:

1. Loại và encoding của đầu vào.
2. Dạng nào được chấp nhận, bị từ chối hoặc được chuyển đổi.
3. Quy tắc xác định hai giá trị tương đương.
4. Cách xử lý dữ liệu thiếu, null, chuỗi rỗng và giá trị không hợp lệ.
5. Phiên bản quy tắc và cách chuyển dữ liệu khi quy tắc thay đổi.

Chỉ thêm trường policy_version mà không cố định cách chọn và áp dụng quy tắc không đủ. Hai dịch vụ dùng hai phiên bản chuẩn hóa khác nhau có thể tạo các liên kết sai hoặc làm báo cáo mất tính nhất quán.

### Tính duy nhất không đồng nghĩa danh tính của một người

Cùng một số điện thoại có thể được nhiều người dùng chung hoặc được cấp lại theo thời gian. Token của giá trị đó không tự trở thành định danh vĩnh viễn của một con người.

Nếu nghiệp vụ muốn nối theo khách hàng, cần định nghĩa thực thể khách hàng và vòng đời quan hệ của thực thể với dữ liệu liên hệ. Không dùng token của một trường làm kết luận “hai hồ sơ là cùng một người” khi chưa có căn cứ nghiệp vụ.

### Chỉ mục tìm kiếm cũng là một phần của thiết kế

Nếu cần tìm theo dữ liệu gốc, hệ thống có thể có thêm chỉ mục hoặc dịch vụ đối chiếu. Đường này có thể làm lộ việc một giá trị tồn tại hoặc tạo mối nối tới token.

Không gọi chỉ mục đó là dữ liệu kỹ thuật để loại khỏi phạm vi bảo vệ. Cần áp dụng phân quyền, tách miền và giới hạn lạm dụng như với các đường có thể tái nhận diện khác.

## 7. Phân quyền tokenize, detokenize và sử dụng token

### 7.1. Tách quyền theo hành động

Quyền đọc bản ghi chứa token, quyền tạo token và quyền khôi phục dữ liệu gốc là ba quyền khác nhau.

| Actor | Quyền cần trong ví dụ | Quyền không được suy ra tự động |
| --- | --- | --- |
| Dịch vụ đơn hàng | Lưu token liên quan đến đơn | Đọc dữ liệu gốc của mọi khách hàng |
| Hệ thống báo cáo | Đọc token trong tập báo cáo được cấp | Gọi detokenize hoặc truy cập kho |
| Dịch vụ giao hàng | Khôi phục thông tin cho đơn đang được phép xử lý | Tra token tùy ý hoặc xuất cả kho |
| Nhân viên hỗ trợ | Xem thông tin theo hồ sơ được phân công | Khôi phục hàng loạt bằng tài khoản cá nhân |
| Nhân sự vận hành | Quản lý sức khỏe dịch vụ theo vai trò | Đọc toàn bộ dữ liệu gốc chỉ vì có quyền xem log |
| Tác vụ quản trị dữ liệu | Chuyển phiên bản hoặc xử lý vòng đời đã được duyệt | Dùng quyền quản trị như đường đọc dữ liệu thường xuyên |

Đối với hệ thống nhiều tenant, tenant dùng để quyết định quyền phải được xác lập từ danh tính và quan hệ được kiểm chứng. Trường tenant_id do caller gửi chỉ là dữ liệu yêu cầu, không phải bằng chứng quyền sở hữu.

### 7.2. Mục đích là một điều kiện phải được kiểm chứng

API có trường purpose không có nghĩa đã kiểm soát được mục đích sử dụng. Caller có thể tự khai một giá trị hợp lệ nhưng không có nghiệp vụ tương ứng.

Đối với yêu cầu khôi phục thông tin giao hàng, cần kiểm tra được:

- Danh tính gọi thuộc dịch vụ được phép.
- Đơn hàng nằm trong tenant và phạm vi mà dịch vụ được giao.
- Token đang được ràng buộc với đối tượng nghiệp vụ được phép.
- Trạng thái đơn hàng cho phép thao tác đó.
- Trường dữ liệu được trả về nằm trong tập tối thiểu cần dùng.

Việc gắn purpose vào token hoặc request chỉ có giá trị khi bên phục vụ áp dụng chính sách đáng tin cậy cho nó.

### 7.3. Token không thay thế kiểm tra quyền trên tài nguyên

Một request biết token của khách hàng vẫn phải được kiểm tra quyền đối với khách hàng, đơn hàng hoặc thao tác liên quan.

Cần kiểm thử cả trường hợp lấy token từ tài nguyên A rồi gắn sang tài nguyên B. Token có thể hoàn toàn hợp lệ về định dạng và tồn tại trong kho nhưng vẫn không được dùng trong ngữ cảnh B.

Đối với tác vụ khôi phục hàng loạt, cần có hợp đồng riêng về actor, phạm vi, đầu ra, thời hạn và audit. Không mở đường bulk chỉ bằng cách lặp API đơn lẻ với quyền không giới hạn.

## 8. Chống dò giá trị, liên kết và lạm dụng

### 8.1. Không dùng băm đơn giản như cam kết che giấu đầu vào dễ đoán

Một tập số điện thoại hoặc mã có cấu trúc có thể nhỏ hơn rất nhiều so với không gian của hàm băm. Người có giá trị băm có thể tạo các đầu vào ứng viên rồi đối chiếu.

Thêm một giá trị công khai cố định không tự ngăn được cách thử đó. Nếu dùng HMAC, việc giữ kín khóa và kiểm soát nơi được phép tính HMAC là một phần của mục tiêu bảo vệ.

Ngay cả khi khóa không bị lộ, một API cho phép gửi tùy ý ứng viên và nhận token ổn định vẫn có thể trở thành công cụ lập bảng đối chiếu. Yêu cầu không được chỉ dừng ở thuật toán.

### 8.2. Xác định rõ khả năng mà kẻ tấn công có

Cần phân biệt ít nhất các tình huống:

- Chỉ có tệp dữ liệu chứa token.
- Có nhiều tệp dùng cùng namespace.
- Có một phần ánh xạ đã biết.
- Có quyền gọi tokenize nhưng không có quyền detokenize.
- Có quyền gọi detokenize cho một phạm vi hạn chế.
- Có quyền đọc kho hoặc sử dụng khóa.

Một thiết kế chống việc suy ngược từ token bị lộ không tự bảo vệ được trường hợp kho đầy đủ đã bị lấy cắp.

### 8.3. Các biện pháp phải gắn với đường tấn công cụ thể

Yêu cầu có thể bao gồm giới hạn tốc độ theo danh tính và tenant, hạn mức khối lượng khôi phục, cảnh báo hành vi bất thường, và chặn các đường không có nhu cầu nghiệp vụ.

Không coi rate limit là bằng chứng dữ liệu không thể bị dò. Một actor có quyền dài hạn hoặc nhiều danh tính có thể tích lũy kết quả. Cần phối hợp giới hạn phạm vi, mục đích và đầu ra.

Thông báo lỗi cũng không nên trở thành công cụ phân biệt token của người khác với token không tồn tại. Hợp đồng lỗi công khai cần tránh tiết lộ ngoài quyền; audit được bảo vệ vẫn cần giữ lý do đủ cho điều tra.

### 8.4. Chống sửa đổi và nhầm ngữ cảnh

Bên nhận cần phát hiện hoặc từ chối token giả, token sai namespace, token đã ngừng và token được dùng sai loại dữ liệu.

Token đúng cú pháp không đủ để được chấp nhận. Với kho ánh xạ, phải kiểm tra bản ghi và ngữ cảnh. Với cơ chế mật mã, phải có cách đáp ứng yêu cầu toàn vẹn và ràng buộc ngữ cảnh; không mặc định mọi phép giữ định dạng đã cung cấp các tính chất đó.

## 9. Dữ liệu gốc được phép tồn tại ở đâu?

### 9.1. Token hóa tại ranh giới đã xác định

Nếu mục tiêu là dịch vụ đơn hàng không giữ dữ liệu liên hệ gốc, dữ liệu phải được biến đổi trước khi ghi vào kho hoặc sự kiện mà dịch vụ đó phát hành.

Phải kiểm tra cả các vị trí dễ bị bỏ qua:

- Access log chứa query string hoặc request body.
- Trace, công cụ theo dõi hiệu năng và thông báo lỗi.
- Hàng đợi retry, dead-letter queue và tệp import tạm.
- Cache, chỉ mục tìm kiếm và bản sao đọc.
- Export CSV, tệp debug, công cụ hỗ trợ và dữ liệu kiểm thử.
- Change-data-capture, sự kiện và bản sao lưu.

Tránh ghi yêu cầu “không có plaintext ở đâu cả” nếu hệ thống vẫn phải tiếp nhận và sử dụng dữ liệu gốc. Cần chỉ rõ vùng nào được phép xử lý, với thời gian lưu và quyền truy cập nào.

### 9.2. Đường lỗi không được âm thầm hạ mức bảo vệ

Khi dịch vụ token hóa không trả kết quả, không được tự chuyển sang lưu giá trị gốc vào trường vốn chỉ cho phép token.

Các lựa chọn có thể là từ chối thao tác, giữ tác vụ chờ, hoặc đệm dữ liệu trong vùng được phê duyệt riêng. Nếu dùng bộ đệm, phải đặc tả mã hóa, danh tính truy cập, thời hạn, xử lý tràn và dọn dữ liệu sau thành công.

Một hàng đợi mã hóa nhưng mọi dịch vụ nghiệp vụ đều có quyền giải mã không tự đáp ứng mục tiêu tách quyền.

### 9.3. Audit phải giúp điều tra mà không trở thành kho ánh xạ phụ

Một sự kiện audit có thể lưu:

- Mã request và mã tham chiếu nội bộ phục vụ điều tra.
- Actor, tenant và loại hành động.
- Phiên bản chính sách, kết quả và mã lý do.
- Mục đích nghiệp vụ đã được kiểm tra.
- Thời điểm, phạm vi dữ liệu và khối lượng.

Không ghi cặp dữ liệu gốc và token vào log thông thường. Token ổn định cũng có thể hỗ trợ nối dữ liệu, nên log chứa token vẫn cần chính sách truy cập và lưu giữ.

Nếu audit là điều kiện bắt buộc trước khi trả dữ liệu gốc, cần xác định hành vi khi không thể ghi nhận sự kiện bền vững. Không tiếp tục trả dữ liệu rồi mặc định sẽ bổ sung bằng chứng sau.

## 10. Vòng đời token, khóa và dữ liệu gốc

### 10.1. Tạo, sử dụng và ngừng sử dụng

Vòng đời khái niệm cho token có kho:

~~~text
Tạo ánh xạ bền vững
    -> cho phép sử dụng theo chính sách
    -> ngừng cho phép khôi phục hoặc sử dụng
    -> xử lý lưu giữ và xóa theo chính sách
~~~

“Ngừng sử dụng” có thể là một trạng thái truy cập, chưa phải xóa vật lý dữ liệu. Yêu cầu phải phân biệt:

- Ngừng khôi phục dữ liệu gốc.
- Ngừng cho token tham gia một nghiệp vụ.
- Xóa ánh xạ ở kho chính.
- Xử lý bản sao, hàng đợi, log và backup.
- Ngừng liên kết các bản ghi bằng token.

Một token bị chặn ở API detokenize vẫn có thể tiếp tục xuất hiện trong báo cáo hoặc giúp nối các tệp đã phát hành. Nếu mục tiêu là ngừng khả năng liên kết, phải thiết kế thêm phạm vi thay token hoặc xử lý tập dữ liệu đó.

Không gán lại một token cũ cho dữ liệu gốc khác khi vẫn có bản ghi hoặc consumer có thể sử dụng token cũ. Nếu làm vậy, một đơn hàng cũ có thể trỏ đến thông tin của người khác.

### 10.2. Thay dữ liệu gốc

Khi khách hàng đổi thông tin liên hệ, cần xác định token đại diện cho điều gì:

- Một giá trị cụ thể tại thời điểm tạo.
- Thuộc tính hiện tại của một hồ sơ.
- Một quan hệ nghiệp vụ có phiên bản.

Nếu token đại diện cho một giá trị bất biến, đổi số điện thoại thường cần một ánh xạ hoặc token phù hợp với giá trị mới. Nếu token đại diện cho thuộc tính hiện tại, việc cập nhật có thể làm token cũ trả về thông tin mới; hành vi đó phải phù hợp với nghiệp vụ và lịch sử.

Không cập nhật âm thầm một ánh xạ đang được coi là bất biến. Yêu cầu cần nói rõ đơn hàng cũ sử dụng thông tin tại thời điểm đặt hay thông tin mới nhất được phép dùng.

### 10.3. Thay khóa và chuyển phiên bản

Thay khóa mã hóa bao ngoài cho kho ánh xạ không nhất thiết làm token thay đổi. Thay khóa của phép biến đổi xác định có thể làm đầu ra thay đổi. Vì vậy, “đã rotation” chưa đủ để biết điều gì xảy ra với token cũ.

Kế hoạch chuyển phiên bản cần nêu:

- Token nào tiếp tục được chấp nhận.
- Dữ liệu nào cần được chuyển và bằng chứng hoàn tất.
- Có tồn tại giai đoạn đọc nhiều phiên bản hay không.
- Cách giữ hoặc thay quan hệ tham chiếu giữa các hệ thống.
- Khi nào có thể ngừng khóa cũ mà không phá nghiệp vụ được giữ lại.
- Đường rollback nào vẫn phải tuân thủ trạng thái ngừng và xóa.

Không suy rằng thay khóa tự làm dữ liệu từng bị lộ trở nên bí mật trở lại.

### 10.4. Xóa và khả năng khôi phục từ backup

Xóa ánh xạ khỏi kho đang chạy không tự xóa bản sao trong backup. Nếu chính sách cho phép bản sao lưu tồn tại thêm một thời gian, phải có quy tắc bảo vệ, hạn lưu và tái áp dụng yêu cầu xóa sau phục hồi.

Nếu dùng hủy khóa để làm dữ liệu không thể đọc, phải xác định mọi bản sao khóa, bản sao dữ liệu đã giải mã và phạm vi dữ liệu dùng chung khóa. Không hủy một khóa dùng chung rồi chỉ mô tả tác động đối với một hồ sơ.

Yêu cầu xóa cũng phải tính đến đường tái tạo token. Một ánh xạ đã xóa có thể được tạo lại từ nguồn chưa xử lý nếu luồng nhập dữ liệu vẫn chạy.

### 10.5. Xử lý lộ token hoặc xâm phạm kho

Mức xử lý phụ thuộc vào tài sản bị lộ:

| Sự cố | Câu hỏi cần trả lời | Hành động có thể phải đặc tả |
| --- | --- | --- |
| Lộ token đơn lẻ | Token chỉ là tham chiếu hay đang cấp quyền trên thực tế? | Ngừng token, kiểm tra truy cập và thay tham chiếu theo phạm vi |
| Lộ tập token ổn định | Có thể nối với những tập dữ liệu nào? | Hạn chế chia sẻ, đánh giá liên kết và thay miền token khi phù hợp |
| Lộ quyền gọi detokenize | Dữ liệu nào đã hoặc có thể được khôi phục? | Thu hồi quyền, chặn đường gọi, điều tra audit và xử lý credential |
| Lộ kho ánh xạ | Có cả dữ liệu gốc và liên hệ tới bản ghi nào? | Xử lý như sự cố dữ liệu trong phạm vi thực tế, không chỉ đổi token |
| Lộ khóa | Khóa cho phép tính hoặc đảo những token nào? | Ngừng sử dụng khóa theo kế hoạch, chuyển phiên bản và đánh giá dữ liệu bị ảnh hưởng |

Thay token có thể giảm khả năng sử dụng mã cũ trong tương lai. Nó không thu hồi được dữ liệu gốc mà một bên đã nhận hoặc sao chép trước đó.

## 11. Sẵn sàng, nhất quán và phục hồi

### 11.1. Cam kết thành công phải tương ứng với trạng thái bền vững

Với mô hình có kho, yêu cầu thành công cần làm rõ token đã được ghi bền ở mức nào và đã sẵn sàng cho những consumer nào.

Nếu API trả token nhưng consumer đọc một replica chưa có ánh xạ, cần có hành vi nhất quán đã định: đọc nguồn thích hợp, retry có giới hạn hoặc trả trạng thái chờ. Không xử lý lỗi bằng cách đoán dữ liệu gốc hoặc ghép một bản ghi gần giống.

Nếu một sự kiện chứa token chỉ được phép phát sau khi ánh xạ tồn tại, cần cơ chế bảo đảm quan hệ đó qua lỗi và retry. Một ví dụ kiến trúc là ghi nhận công việc phát sự kiện cùng giao dịch phù hợp; yêu cầu nên mô tả kết quả cần đạt, không chỉ tên kỹ thuật.

### 11.2. Cache là một bản sao dữ liệu hoặc quyết định

Cần phân biệt cache ánh xạ dữ liệu gốc và cache quyết định phân quyền. Hai loại này đều có thể làm trạng thái cũ tiếp tục có hiệu lực.

Yêu cầu phải xác định:

- Có được cache dữ liệu gốc không, ở thành phần nào?
- Thời hạn và cách phân tách tenant, mục đích.
- Cách xử lý khi quyền bị thu hồi hoặc token bị ngừng.
- Cache có được ghi ra đĩa, backup hoặc công cụ chẩn đoán không?
- Có cần kiểm tra quyền lại trước mỗi lần trả dữ liệu đã cache không?

Không chọn TTL dài hơn giới hạn ngừng sử dụng rồi vẫn cam kết API chặn trong giới hạn ngắn hơn khi không có biện pháp bổ sung.

### 11.3. Phục hồi không được làm sống lại quyền cũ

Backup cũ có thể chứa ánh xạ còn active, quyền đã bị thu hồi hoặc khóa đã bị ngừng.

Trước khi mở lại đường detokenize, cần đối soát trạng thái vòng đời với nguồn có thẩm quyền. Nếu không thể xác minh trạng thái bắt buộc, phải áp dụng chính sách lỗi đã định thay vì mặc định cho phép.

Mục tiêu thời gian phục hồi và mục tiêu mất dữ liệu cần áp dụng cả cho kho ánh xạ và dữ liệu nghiệp vụ chứa token. Phục hồi riêng một phía có thể tạo tham chiếu mất ánh xạ hoặc ánh xạ không còn phù hợp.

Một hệ thống khởi động thành công chưa chứng minh việc phục hồi đạt yêu cầu bảo mật.

## 12. Bộ yêu cầu và tiêu chí chấp nhận minh họa

Giả sử bài toán chọn mô hình token có kho cho thông tin liên hệ. Các ngưỡng dưới đây chỉ phục vụ ví dụ, không phải giá trị mặc định cho mọi hệ thống.

Phạm vi ví dụ gồm API tạo hồ sơ, import theo lô và retry của hai đường này; các đầu ra bị cấm chứa dữ liệu gốc là kho đơn hàng, sự kiện đơn hàng và kho báo cáo. Chỉ dịch vụ thực hiện giao hàng được yêu cầu khôi phục thông tin cho đơn đủ điều kiện.

| ID | Yêu cầu bảo mật | Tiêu chí chấp nhận |
| --- | --- | --- |
| DT-01 | Token hóa trường liên hệ trước khi ghi vào các đầu ra bị cấm trong mọi đường vào đã nêu | Dữ liệu thử nghiệm đi qua API, import, retry; không có giá trị gốc ở các đầu ra đó, kể cả ca lỗi |
| DT-02 | Tách namespace giữa tenant và giữa mục đích giao hàng với phân tích | Không dùng chung ánh xạ giữa các miền; caller không đọc, tra hoặc nối ánh xạ ngoài phạm vi được cấp |
| DT-03 | Dịch vụ báo cáo không có quyền detokenize hoặc đọc kho và khóa liên quan | Cả đường API lẫn đường truy cập trực tiếp đều từ chối với danh tính báo cáo |
| DT-04 | Mỗi lần detokenize phải kiểm tra actor, tenant, token, đơn hàng và trạng thái nghiệp vụ | Token hợp lệ nhưng sai đơn, sai tenant hoặc đơn không đủ điều kiện đều không trả dữ liệu gốc |
| DT-05 | Token của cùng giá trị đã chuẩn hóa ổn định trong cùng namespace theo chính sách của ví dụ | Request lặp và đồng thời không tạo các liên kết mâu thuẫn; giá trị khác nhau không bị ánh xạ nhầm |
| DT-06 | Chỉ trả thành công sau khi ánh xạ cần dùng được ghi bền; va chạm không ghi đè bản ghi khác | Lỗi ghi kho không trả token thành công; ca cưỡng bức va chạm không làm thay dữ liệu của token đã có |
| DT-07 | Ngừng trả dữ liệu gốc trong tối đa 60 giây kể từ khi lệnh ngừng token được ghi bền | Request được kiểm tra tại hoặc sau T0 + 60 giây bị từ chối trên mọi node và cache trong phạm vi |
| DT-08 | Khi không xác minh được điều kiện khôi phục bắt buộc, không trả dữ liệu gốc | Lỗi kho, chính sách hoặc trạng thái không dẫn tới bỏ qua kiểm tra hoặc fallback plaintext |
| DT-09 | Mỗi lần trả dữ liệu gốc phải có audit bền vững gắn với actor, phạm vi và quyết định; không chứa giá trị gốc | Đối chiếu được mọi lần trả thành công với audit; khi không ghi được audit bắt buộc, API không trả dữ liệu gốc |
| DT-10 | Phục hồi phải tái áp dụng trạng thái ngừng và xử lý xóa trước khi mở lại đường khôi phục | Khôi phục bản sao trước lệnh ngừng không làm token cũ được chấp nhận; dữ liệu vòng đời chưa xác minh bị chặn |
| DT-11 | Hợp đồng schema phân biệt được token với dữ liệu liên hệ gốc ở các consumer liên quan | Consumer không gửi token như số liên hệ thật và không nhận nhầm dữ liệu gốc vào trường chỉ cho phép token |
| DT-12 | Chuyển phiên bản token, chuẩn hóa hoặc khóa phải bảo toàn quan hệ nghiệp vụ đã xác định | Đơn hàng và báo cáo dùng đúng phiên bản; token ngừng không hoạt động lại trong cả chuyển đổi và rollback |

### 12.1. Làm rõ phép đo cho DT-07

Chọn các mốc:

~~~text
T0: lệnh ngừng token đã được nguồn quản trị có thẩm quyền ghi bền
Tdecision: thời điểm API quyết định có trả dữ liệu gốc hay không

Nếu Tdecision >= T0 + 60 giây:
    mọi node trong phạm vi phải từ chối khôi phục token đó
~~~

Yêu cầu này đo quyết định ở API, không chỉ thời điểm cập nhật một hàng trong kho.

Các request đang chạy, batch đã được cấp quyền trước đó và dữ liệu gốc đã trả ra cần điều kiện riêng. Trong ví dụ, một batch phải kiểm tra trạng thái đủ thường xuyên để mọi quyết định phát dữ liệu mới sau giới hạn vẫn tuân thủ DT-07. Không cho cả batch một ngoại lệ không giới hạn chỉ vì nó bắt đầu trước T0.

Nếu yêu cầu nghiệp vụ đòi hỏi chặn trước lúc gửi phản hồi thay vì tại thời điểm quyết định, phải đặc tả điểm kiểm tra đó và xử lý cuộc đua tương ứng.

### 12.2. Ví dụ đặc tả có truy vết

~~~yaml
requirement_id: DT-04
risk_id: TH-DATA-02
risk: Workload bị chiếm dùng token hợp lệ để đọc dữ liệu ngoài đơn được giao
asset: Thông tin liên hệ gốc
allowed_actor: Dịch vụ thực hiện giao hàng
scope:
  - API khôi phục thông tin liên hệ
  - Mọi node phục vụ và đường cache liên quan
conditions:
  - Danh tính dịch vụ được xác thực bằng cơ chế được phê duyệt
  - Tenant được xác lập từ ngữ cảnh có thẩm quyền
  - Token thuộc đúng namespace và đơn hàng được yêu cầu
  - Đơn hàng nằm trong phạm vi được phân công và đủ điều kiện xử lý
  - Chỉ trả trường dữ liệu cần cho hành động
required_behavior: Chỉ trả dữ liệu gốc khi tất cả điều kiện đạt
failure_behavior: Không trả dữ liệu gốc khi điều kiện thiếu hoặc không thể xác minh
verification:
  - Ca đúng phạm vi trả dữ liệu thử nghiệm dự kiến
  - Sai tenant hoặc sai đơn không trả dữ liệu gốc
  - Dịch vụ báo cáo bị từ chối
  - Cache nóng không làm bỏ qua kiểm tra bắt buộc
evidence:
  - Kết quả phản hồi đã lọc dữ liệu nhạy cảm
  - Audit của quyết định
  - Chính sách và danh tính triển khai tương ứng
owner: Nhóm hồ sơ, nhóm giao hàng và nhóm nền tảng bảo mật
~~~

Đây là nội dung đặc tả minh họa, không phải cấu hình của một sản phẩm. Trong hồ sơ yêu cầu thực tế cần bổ sung phiên bản, người chịu trách nhiệm phê duyệt và liên kết tới kiến trúc, kiểm thử tương ứng.

## 13. Thiết kế kiểm chứng theo từng rủi ro

### 13.1. Dữ liệu thử nghiệm và bằng chứng

Sử dụng dữ liệu tổng hợp có thể nhận biết, được bộ kiểm tra đầu vào chấp nhận và không lấy từ hồ sơ thật. Tập thử cần có giá trị lặp, giá trị khác nhau, dữ liệu biên và những cặp đầu vào liên quan đến quy tắc chuẩn hóa.

Không dùng ví dụ duy nhất để kết luận token không thể suy ra hoặc không bao giờ va chạm. Cần kết hợp kiểm tra hành vi với đánh giá cơ chế sinh, ràng buộc dữ liệu và cấu hình triển khai.

Bằng chứng kiểm thử cũng phải tránh trở thành bản sao dữ liệu nhạy cảm. Có thể dùng mã ca thử và chỉ báo đạt thay vì ghi toàn bộ dữ liệu gốc vào báo cáo.

### 13.2. Luồng hợp lệ và tách quyền

Một ca kiểm chứng nền:

1. Gửi dữ liệu tổng hợp qua đường tạo hồ sơ được phép.
2. Xác nhận đầu ra nghiệp vụ chứa token và quan hệ đúng.
3. Dùng danh tính báo cáo để đọc tập dữ liệu được cấp; không nhận dữ liệu gốc.
4. Thử detokenize bằng danh tính báo cáo; phải bị từ chối.
5. Dùng danh tính giao hàng với đơn đủ điều kiện; chỉ nhận trường cần thiết.
6. Đổi token, đơn hàng, tenant và trạng thái lần lượt; các tổ hợp sai không trả dữ liệu gốc.
7. Đối chiếu phản hồi với audit và chính sách thực thi.

Nếu chỉ kiểm thử danh tính quản trị có toàn quyền, không chứng minh được mục tiêu tách quyền của kiến trúc.

### 13.3. Luồng dữ liệu phụ và đường lỗi

Kiểm tra cả phản hồi lỗi, trace, log, hàng đợi và export trong phạm vi DT-01. Cần biết mỗi đường được quan sát bằng cách nào.

Tìm chuỗi dữ liệu tổng hợp có thể phát hiện rò rỉ đơn giản, nhưng không chứng minh mọi biến thể đã biến mất. Dữ liệu có thể đã được chuẩn hóa, chia nhỏ hoặc chuyển encoding. Vì vậy, cần kiểm tra schema và luồng xử lý bên cạnh việc tìm dấu hiệu.

Thử lỗi trước khi tạo token, sau khi ghi ánh xạ, trước khi phát sự kiện và trong lúc retry. Kết quả không được tạo đầu ra plaintext ngoài chính sách hoặc gắn nhầm token.

### 13.4. Đồng thời, va chạm và chuẩn hóa

Dùng các request đồng thời để kiểm tra hợp đồng ổn định, idempotency và tính duy nhất.

Không chờ ngẫu nhiên gặp va chạm trong kiểm thử thông thường. Có thể dùng cơ chế kiểm thử tách biệt để buộc bộ sinh trả mã đã tồn tại, rồi chứng minh hệ thống không ghi đè ánh xạ. Cơ chế cưỡng bức này không được trở thành cấu hình triển khai ngoài kiểm soát.

Kiểm thử cặp đầu vào chỉ khác ở đặc điểm được chuẩn hóa và cặp đầu vào không được coi tương đương. Cần phát hiện cả việc tách sai một giá trị thành nhiều token và việc gộp sai các giá trị khác nhau.

### 13.5. Trạng thái ngừng, cache và phục hồi

Làm nóng cache trước lệnh ngừng, tiếp tục yêu cầu trên từng điểm thực thi và đo theo DT-07. Bao gồm node mới, replica chậm và đường mất kết nối tới nguồn trạng thái.

Với phục hồi, dùng bản sao có trạng thái trước lệnh ngừng hoặc xóa. Xác nhận dịch vụ chỉ mở lại sau khi hoàn tất điều kiện đối soát; token cũ không hoạt động trở lại.

Cần kiểm thử cả rollback chuyển phiên bản. Một lần triển khai cũ chạy lại không được tự khôi phục chính sách cấp quyền đã bị thay đổi.

### 13.6. Lạm dụng API và liên kết ngoài dự kiến

Kiểm thử actor có quyền tokenize nhưng không được detokenize. Xem actor có thể dựng bảng đối chiếu ứng viên hoặc nhận biết dữ liệu của tenant khác qua phản hồi hay không.

Đối với xuất dữ liệu, dùng hai tập thuộc hai mục đích để đánh giá những phép nối mà thiết kế cho phép hoặc cần ngăn. Việc token khác nhau không tự chứng minh không thể nối bằng thời gian, địa điểm hoặc thuộc tính hiếm còn lại.

## 14. Những cách viết yêu cầu cần sửa

| Cách viết chưa đủ | Điều còn thiếu | Cách đặc tả tốt hơn |
| --- | --- | --- |
| Dữ liệu nhạy cảm phải được token hóa | Trường, ranh giới và ngoại lệ | Nêu trường nào bị cấm ở kho, sự kiện và đường lỗi nào |
| Có token thì không còn dữ liệu cá nhân | Khả năng khôi phục và liên kết | Đánh giá dữ liệu phụ, quyền truy cập và ngữ cảnh sử dụng |
| Băm số điện thoại để không ai biết số thật | Miền đầu vào dễ đoán và đường dò | Nêu mô hình tấn công, cơ chế và kiểm soát API tương ứng |
| Token ngẫu nhiên nên không cần kiểm tra quyền | Token có thể bị lộ hoặc thay giữa tài nguyên | Kiểm tra actor, tenant và đối tượng nghiệp vụ ở phía phục vụ |
| Caller gửi purpose là đủ | Mục đích do caller tự khai | Kiểm chứng quan hệ nghiệp vụ và quyền theo chính sách |
| Không có vault nên không cần bảo vệ gì thêm | Khóa, dữ liệu nguồn và khả năng tính token | Xác định mọi đường tái nhận diện và tài sản liên quan |
| Xóa mapping là xóa hết dữ liệu | Bản sao, backup, nguồn tái tạo | Đặc tả vòng đời từng bản sao và điều kiện sau phục hồi |
| Rotation khóa làm token cũ vô hiệu ngay | Cache, phiên bản và giải mã offline | Nêu điểm thực thi, thời hạn và bằng chứng ngừng sử dụng |
| Khi dịch vụ lỗi thì lưu tạm plaintext | Vùng lưu tạm có thể vi phạm mục tiêu | Chọn hành vi lỗi và vùng đệm được bảo vệ có hạn lưu cụ thể |
| API không trả dữ liệu gốc nên đã an toàn | Các đường truy cập trực tiếp có thể còn mở | Kiểm tra cả kho, bản sao, chỉ mục, khóa và quyền vận hành |

Một đặc tả token hóa dữ liệu có thể kiểm chứng phải nối được loại dữ liệu, rủi ro, phạm vi liên kết, quyền khôi phục, trạng thái vòng đời và bằng chứng thực thi. Chính mối nối đó quyết định hệ thống đã giảm mức phơi bày dữ liệu đến đâu và còn chấp nhận những rủi ro nào.
