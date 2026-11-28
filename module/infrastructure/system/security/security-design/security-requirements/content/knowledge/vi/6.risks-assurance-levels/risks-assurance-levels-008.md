# Chọn mức kiểm soát theo rủi ro

## 1. Mục tiêu của việc chọn kiểm soát theo rủi ro

**Chọn mức kiểm soát theo rủi ro** là xác định cơ chế bảo vệ, phạm vi áp dụng, độ nghiêm của điều kiện thực thi và mức bằng chứng cần có để đưa rủi ro về vùng được chấp nhận. Quyết định phải xuất phát từ tài sản, hành động, đe dọa và tác động cụ thể.

Một trang danh mục hàng hóa dành cho công chúng cần cho phép đọc thuận tiện, nhưng vẫn phải chống sửa nội dung trái phép và lạm dụng tài nguyên. Một chức năng xuất toàn bộ đơn hàng cần kiểm soát ai được xuất, dữ liệu thuộc khách thuê nào, khối lượng phơi nhiễm và cách tải kết quả. Một chức năng cấp quyền quản trị cần bảo vệ cả việc xác minh người thao tác lẫn phạm vi quyền được cấp.

Không thể dùng cùng một tập điều kiện cho mọi hành động rồi mặc định đã cân bằng được rủi ro. Cũng không nên chỉ đếm số công cụ bảo mật: ba kiểm soát không tác động tới đường tấn công có thể kém hiệu quả hơn một kiểm soát được thực thi đúng vị trí.

Trong bài học này, đầu ra cần đạt là một quyết định có thể triển khai và kiểm chứng:

> Với tài sản và kịch bản rủi ro đã xác định, hệ thống phải thực hiện kiểm soát nào, tại đâu, trong điều kiện nào, khi lỗi phải xử lý ra sao và cần bằng chứng gì để chấp nhận rủi ro còn lại?

Đây là bước nối mô hình đe dọa với đặc tả xác thực, phân quyền, dữ liệu, logging và phục hồi trong vòng đời phát triển.

## 2. Những khái niệm cần phân biệt

| Khái niệm | Ý nghĩa trong quyết định chọn kiểm soát |
|---|---|
| Tài sản và mục tiêu bảo vệ | Dữ liệu, chức năng, quyền hoặc bằng chứng cần giữ bí mật, toàn vẹn hay sẵn sàng |
| Đe dọa | Tác nhân hoặc sự kiện có thể gây hành vi không mong muốn trên tài sản |
| Điểm yếu | Điều kiện giúp đe dọa thành hiện thực, chẳng hạn thiếu kiểm tra quyền ở đường tải trực tiếp |
| Rủi ro | Sự kết hợp giữa khả năng xảy ra và hậu quả đối với mục tiêu, kèm bất định của đánh giá |
| Kiểm soát | Cơ chế kỹ thuật hoặc tổ chức làm thay đổi khả năng, tác động hoặc năng lực xử lý sự kiện |
| Rủi ro còn lại | Rủi ro sau khi xét các kiểm soát thực sự có hiệu lực |
| Mức đảm bảo | Mức tin cậy có căn cứ rằng yêu cầu và kiểm soát hoạt động trong phạm vi đã đánh giá |

**Mức kiểm soát** và **mức đảm bảo** liên quan nhưng không đồng nhất. Mức kiểm soát trả lời hệ thống bắt buộc làm gì; mức đảm bảo trả lời có cơ sở nào để tin hệ thống thực sự làm được điều đó.

Ví dụ, yêu cầu kiểm tra quyền khách thuê tại mọi đường tải là yêu cầu kiểm soát. Kiểm kê đường truy cập, kiểm thử chéo khách thuê, rà soát thiết kế và xác minh cấu hình triển khai là hoạt động tạo bằng chứng về hiệu lực kiểm soát đó.

Một cơ chế được ghi trong tài liệu nhưng chưa triển khai chỉ làm thay đổi rủi ro mục tiêu. Không được dùng nó để hạ đánh giá rủi ro còn lại hiện tại.

## 3. Chuẩn bị đầu vào trước khi chọn mức

### 3.1. Xác định tài sản, hành động và ranh giới

Nên đánh giá theo tổ hợp **tài sản – hành động – chủ thể – ngữ cảnh**, thay vì chỉ gắn nhãn “ứng dụng rủi ro cao”. Cùng một hệ thống có thể chứa nhiều hành động với yêu cầu khác nhau.

| Đầu vào | Câu hỏi cần trả lời |
|---|---|
| Tài sản và phân loại dữ liệu | Nội dung nào nhạy cảm, quyền nào có tác động lớn, bằng chứng nào phải giữ? |
| Chủ thể và danh tính | Người dùng, quản trị viên, dịch vụ hay đối tác thực hiện hành động? |
| Hành động | Đọc một đối tượng, sửa, phê duyệt, xuất hàng loạt, cấp quyền hay phục hồi? |
| Phạm vi và quy mô | Một bản ghi, một khách thuê hay nhiều khách thuê có thể bị ảnh hưởng? |
| Ranh giới tin cậy | Dữ liệu đi qua trình duyệt, API, tác vụ nền, kho tệp và bên nhận nào? |
| Phơi nhiễm | Ai có thể tiếp cận đường xử lý và cần điều kiện gì để khai thác? |
| Kiểm soát hiện tại | Cơ chế nào đã có, ở vị trí nào, có bằng chứng hiệu lực chưa? |
| Giới hạn và nghĩa vụ | Điều kiện bắt buộc, khẩu vị rủi ro, dung sai và thẩm quyền quyết định là gì? |

Khẩu vị rủi ro là định hướng về loại và mức rủi ro tổ chức sẵn sàng duy trì để theo đuổi mục tiêu. Dung sai và giới hạn cụ thể giúp xác định khi nào phải xử lý hoặc chuyển cấp. Các điều kiện bắt buộc cần được giữ riêng; nhóm không thể tự bỏ chúng chỉ vì một điểm rủi ro thấp.

### 3.2. Viết kịch bản thay vì chỉ liệt kê lỗ hổng

Một kịch bản có thể viết theo cấu trúc:

> Do điểm yếu X, chủ thể Y có thể thực hiện hành động Z trên tài sản A, dẫn đến hậu quả B trong phạm vi C.

Ví dụ:

> Do tác vụ xuất lấy khách thuê từ trường do bên gọi tự truyền, nhân viên của khách thuê A có thể tạo tệp chứa đơn hàng của B, gây tiết lộ dữ liệu hàng loạt qua đường tải kết quả.

Kịch bản này cho thấy kiểm soát không chỉ nằm ở API tiếp nhận. Cần xem cả nơi tạo tác vụ, danh tính của worker, truy vấn dữ liệu, kho kết quả và đường tải.

### 3.3. Đánh giá tác động, khả năng và độ bất định

Đối với tác động, cần xét mất bí mật, sửa trái phép, gián đoạn và mất khả năng điều tra. Với khả năng xảy ra, cần xem mức tiếp cận, điều kiện khai thác, quyền ban đầu và hiệu lực kiểm soát hiện có.

Không nên dùng một điểm lỗ hổng kỹ thuật như toàn bộ đánh giá rủi ro nghiệp vụ. Một lỗi cần quyền thấp nhưng cho phép xuất dữ liệu toàn khách thuê có thể cần ưu tiên khác với lỗi tương tự chỉ ảnh hưởng dữ liệu tổng hợp đã công khai.

Nếu sử dụng ma trận thấp–trung bình–cao, phải thống nhất định nghĩa và khoảng thời gian. Điểm thứ bậc là công cụ hỗ trợ quyết định; nó không tự là xác suất hay số tiền tổn thất. Cần giữ lại kịch bản và lập luận thay vì chỉ lưu điểm cuối.

Độ bất định cũng là đầu vào. Chưa kiểm kê đủ đường tải hoặc chưa xác minh quyền của worker không đồng nghĩa các đường đó an toàn. Có thể cần bổ sung bằng chứng hoặc thu hẹp phạm vi trước khi quyết định mức kiểm soát phù hợp.

## 4. Chọn kiểm soát theo tác dụng lên kịch bản

### 4.1. Bốn nhóm tác dụng bổ sung cho nhau

| Nhóm | Tác dụng chính | Ví dụ | Giới hạn cần nhớ |
|---|---|---|---|
| Phòng ngừa | Ngăn hành động không được phép hoặc giảm khả năng xảy ra | Phân quyền theo đối tượng, xác thực phù hợp, ràng buộc trạng thái và đầu vào | Có thể thiếu đường thực thi hoặc bị sai cấu hình |
| Phát hiện | Nhận biết hành vi, sai lệch hoặc mất hiệu lực kiểm soát | Sự kiện kiểm toán, cảnh báo truy cập bất thường, đối soát cấu hình | Phát hiện không tự ngăn nội dung đã bị tiết lộ |
| Ứng phó và khoanh vùng | Giảm phạm vi và thời gian tác động sau khi phát hiện | Thu hồi phiên, dừng tác vụ, vô hiệu hóa quyền, cô lập đường xử lý | Cần người hoặc tự động hóa có quyền và quy trình đã kiểm chứng |
| Phục hồi | Đưa chức năng và dữ liệu về trạng thái đúng sau sự cố | Khôi phục dữ liệu, quyền, khóa và cấu hình từ nguồn tin cậy | Bản sao có thể lỗi hoặc khôi phục cả trạng thái quyền đã bị thu hồi |

Chọn nhiều nhóm giúp xử lý các giai đoạn khác nhau của cùng kịch bản. Tuy nhiên, không nên mô tả một nhóm như thay thế hoàn toàn nhóm khác khi chưa phân tích tác động.

Ví dụ, thêm cảnh báo tải nhiều tệp không sửa được lỗi cho phép đọc một tệp của khách thuê khác. Mã hóa kho lưu trữ cũng không ngăn ứng dụng giải mã rồi trả dữ liệu sai quyền. Với kịch bản này, kiểm tra quyền đúng ranh giới vẫn là điều kiện trọng yếu.

### 4.2. Vị trí thực thi quan trọng hơn tên cơ chế

Một yêu cầu “có phân quyền” chưa cho biết quyền được kiểm tra ở đâu. Nếu giao diện ẩn nút nhưng API vẫn chấp nhận yêu cầu trực tiếp, kiểm soát chưa bao phủ đường tấn công.

Đối với tác vụ nền, việc API đã kiểm tra quyền lúc tạo tác vụ chưa đủ để mặc định mọi hoạt động sau đó còn được phép. Cần xác định hiệu lực quyền khi chạy, khi tạo kết quả và khi tải. Nếu quyền thay đổi trong thời gian chờ, thiết kế phải nêu rõ hành vi theo chính sách.

Đối với một hành động thay đổi trạng thái, phải xem cả điều kiện trước hành động và trạng thái lúc ghi kết quả. Hai yêu cầu đồng thời có thể vượt qua một kiểm tra chỉ thực hiện riêng lẻ. Kiểm soát cần gắn với ranh giới giao dịch hoặc cơ chế nhất quán tương ứng.

### 4.3. Tránh phụ thuộc chung làm mất nhiều lớp bảo vệ

Một hệ thống có nhiều bước kiểm tra nhưng tất cả cùng tin một trường khách thuê do bên gọi tự khai vẫn có thể hỏng theo cùng một cách. Tương tự, dùng chung một tài khoản toàn quyền cho ứng dụng, worker và sao lưu làm tăng phạm vi ảnh hưởng khi tài khoản đó bị chiếm quyền.

Khi cần tăng mức kiểm soát, nên xem xét việc tách danh tính, thu hẹp quyền, giới hạn dữ liệu và tạo các điểm kiểm tra có căn cứ độc lập. “Thêm một lớp” chỉ có ý nghĩa khi lớp đó xử lý được một sai hỏng hoặc đường tấn công chưa được lớp khác kiểm soát đầy đủ.

## 5. Dùng các mức nội bộ để tổ chức quyết định

Một dự án có thể đặt tên mức nội bộ để trao đổi nhất quán. Bảng sau chỉ là **mô hình minh họa của bài học**, không phải các cấp của một tiêu chuẩn hay chứng nhận.

| Chiều lựa chọn | M1 — nền tảng | M2 — tăng cường | M3 — nghiêm ngặt cho hành động trọng yếu |
|---|---|---|---|
| Điều kiện áp dụng | Các yêu cầu tối thiểu liên quan đều phải có, kể cả chức năng có rủi ro thấp | Tăng yêu cầu khi dữ liệu nhạy cảm, phơi nhiễm hoặc tác động tăng | Tập trung vào hành động có phạm vi lớn, quyền cao hoặc hậu quả khó phục hồi |
| Xác thực | Phù hợp với việc công khai hay yêu cầu nhận diện chủ thể | Tăng mức xác minh ở hành động hoặc ngữ cảnh cần thiết | Quy định rõ độ mới và mức xác minh, kiểm soát cả đường cấp lại thông tin xác thực |
| Phân quyền | Kiểm tra hành động và tài nguyên tại ranh giới tin cậy | Thêm ràng buộc khách thuê, mục đích, trạng thái và giới hạn phạm vi | Hạn chế đặc quyền, có thể cần phê duyệt độc lập và kiểm soát dùng một lần |
| Dữ liệu | Chỉ xử lý tập trường và phạm vi đã duyệt | Giảm dữ liệu xuất, tách kho hoặc tách quyền dùng khóa khi có căn cứ | Giới hạn mạnh phạm vi hàng loạt và các bản sao; kiểm soát chặt quyền xuất |
| Logging và ứng phó | Có sự kiện cần thiết, bảo vệ bí mật và điều tra được | Cảnh báo theo kịch bản, giới hạn thời gian phát hiện và thu hồi | Bảo đảm bằng chứng cho hành động trọng yếu, kiểm thử mất thu thập và khoanh vùng |
| Phục hồi | Phương án phù hợp chức năng và dữ liệu | Mục tiêu phục hồi đo được, kiểm thử các phụ thuộc chính | Diễn tập cả quyền, khóa, thu hồi và sai hỏng tác động rộng |
| Bằng chứng | Kiểm tra yêu cầu, cấu hình và các trường hợp cơ bản liên quan | Kiểm thử phủ định, nhiều ranh giới và lỗi phụ thuộc | Rà soát sâu, kiểm thử đối kháng và mức độc lập phù hợp với quyết định |

M2 và M3 bổ sung những yêu cầu liên quan trên nền điều kiện bắt buộc. Chúng không có nghĩa phải áp dụng mọi ô trong bảng cho mọi endpoint. Chức năng đọc công khai không tự cần đăng nhập tăng cường, nhưng đường sửa nội dung của chức năng đó có thể cần mức bảo vệ cao.

Nên chọn mức theo từng thuộc tính và hành động. Một trang trạng thái công khai có yêu cầu bí mật thấp nhưng toàn vẹn và sẵn sàng có thể cao. Nếu chỉ lấy mức trung bình của ba thuộc tính, nhóm có thể giảm nhầm kiểm soát cho một tác động trọng yếu.

Những biện pháp như phê duyệt hai người cũng cần căn cứ. Chúng có thể phù hợp với cấp quyền đặc biệt hoặc thay đổi có hậu quả lớn, nhưng không nên trở thành thao tác bắt buộc cho mọi hành động thường ngày nếu không giải quyết một rủi ro tương ứng.

## 6. Quy trình lựa chọn và điều chỉnh kiểm soát

### Bước 1: Giữ những điều kiện bắt buộc

Liệt kê yêu cầu nền tảng, nghĩa vụ áp dụng và ranh giới không cho phép ngoại lệ. Ví dụ, không cho phép người dùng của khách thuê A đọc đơn hàng của B. Một đánh giá có khả năng khai thác thấp không tự cho phép bỏ điều kiện này.

### Bước 2: Chọn những kịch bản cần xử lý

Xác định tài sản và hành động có tác động đáng kể, rồi mô tả đường tấn công hoặc sai hỏng. Ưu tiên theo tác động, khả năng và bất định, đồng thời xem phạm vi ảnh hưởng và phụ thuộc chung.

### Bước 3: Tạo các phương án có tác dụng rõ

Với mỗi kiểm soát đề xuất, ghi nó ngăn hoặc giảm phần nào của kịch bản. Nêu vị trí thực thi và những đường chưa được bao phủ.

Ví dụ với xuất dữ liệu chéo khách thuê:

| Phương án | Tác dụng thực tế | Nhận xét lựa chọn |
|---|---|---|
| Chỉ ẩn nút xuất với người không có quyền | Giảm thao tác nhầm qua giao diện | Không kiểm soát được gọi API trực tiếp |
| Mã hóa kho kết quả | Bảo vệ một số đường đọc ngoài ứng dụng theo thiết kế khóa | Không ngăn worker tạo tệp sai khách thuê hoặc ứng dụng trả tệp sai quyền |
| Kiểm tra quyền tại API và gắn khách thuê từ ngữ cảnh đã xác thực vào tác vụ | Giảm khả năng tạo tác vụ ngoài quyền | Còn cần kiểm tra nguồn dữ liệu và quyền của các bước sau |
| Giới hạn worker và truy vấn theo phạm vi được ủy quyền; kiểm tra tải kết quả | Bao phủ xử lý nền và đường phân phối | Phù hợp với kịch bản nếu quyền, trạng thái và ranh giới được kiểm chứng |
| Bổ sung nhật ký và cảnh báo bất thường | Hỗ trợ phát hiện và điều tra lạm dụng | Bổ sung cho kiểm soát quyền; không thay thế việc ngăn truy cập sai |

### Bước 4: So sánh hiệu quả và hệ quả phụ

Cần xem cả chi phí triển khai, độ trễ, tải vận hành, trải nghiệm và phụ thuộc mới. Một kiểm soát làm người vận hành thường xuyên tìm cách bỏ qua sẽ khó duy trì hiệu lực.

Tuy vậy, chi phí thấp không làm một phương án không đáp ứng điều kiện bắt buộc trở nên phù hợp. Nếu phương án đầy đủ chưa khả thi, có thể giảm quy mô xuất, giới hạn nhóm được mở tính năng, dùng dữ liệu ít nhạy cảm hơn hoặc chưa mở chức năng liên quan.

### Bước 5: Viết yêu cầu và tiêu chí chấp nhận

Chuyển phương án thành hành vi bắt buộc: ai, trên tài nguyên nào, với điều kiện gì, giới hạn nào, khi lỗi làm gì và kiểm chứng ra sao. Nêu rõ yêu cầu về bằng chứng, không chỉ yêu cầu về chức năng.

### Bước 6: Đánh giá rủi ro còn lại và quyết định

Sau khi có bằng chứng triển khai, đánh giá lại phần rủi ro còn lại. Nếu vượt giới hạn hoặc chưa đủ bằng chứng, tiếp tục giảm phạm vi, xử lý hay chuyển cấp theo thẩm quyền. Nếu được chấp nhận, ghi chủ sở hữu, giả định, điều kiện hiệu lực và tác nhân cần đánh giá lại.

## 7. Áp dụng cho một nền tảng quản lý đơn hàng

Giả sử hệ thống phục vụ nhiều khách thuê, gồm danh mục công khai, đơn hàng nội bộ, chức năng xuất dữ liệu và quản trị quyền. Bảng sau minh họa cách chọn theo hành động thay vì áp một mức duy nhất cho cả sản phẩm.

| Hành động | Tác động cần ưu tiên | Kiểm soát được chọn và lý do | Bằng chứng trọng tâm |
|---|---|---|---|
| Đọc danh mục đã công bố | Sửa sai nội dung và gây gián đoạn; bí mật của phần đã duyệt thấp | Tách đầu ra công khai khỏi trường nội bộ, bảo vệ đường ghi, giới hạn tài nguyên | Bản nháp và trường nội bộ không xuất hiện; người đọc không sửa được |
| Đọc một đơn hàng | Lộ thông tin khách hàng hoặc truy cập sai khách thuê | Xác thực, quyền theo đối tượng và khách thuê, bảo vệ đường tải đính kèm | Thử tráo chủ thể, đơn hàng, khách thuê và liên kết tệp |
| Xuất nhiều đơn hàng | Lộ dữ liệu với quy mô lớn qua nhiều giai đoạn | Quyền xuất riêng, giới hạn phạm vi, worker có quyền hẹp, kiểm soát tệp và bằng chứng xuất | Thử tạo–chạy–tải, thay quyền khi đang chờ, API cũ và kho kết quả |
| Cấp quyền quản trị | Mở rộng đặc quyền hoặc chiếm toàn khách thuê | Xác minh tăng cường, kiểm tra quyền cấp, giới hạn quyền được cấp và phê duyệt độc lập khi chính sách yêu cầu | Thử tự cấp, sửa nội dung sau duyệt, phát lại yêu cầu và đường khôi phục |
| Phục hồi hệ thống | Mất dữ liệu hoặc làm sống lại quyền đã thu hồi | Khôi phục dữ liệu cùng quyền và khóa; áp dụng lại quyết định thu hồi trước phục vụ | Diễn tập theo mốc dữ liệu, kiểm tra quyền và trạng thái sau phục hồi |

Mức rủi ro của chức năng xuất không chỉ bằng mức nhạy cảm của một bản ghi. Quy mô, khả năng sao chép và thời gian tồn tại của tệp làm tăng phạm vi ảnh hưởng. Đây là căn cứ để thêm giới hạn khối lượng, thời hạn kết quả và quyền tải lại.

Tương tự, khả năng cấp quyền có thể tạo tác động gián tiếp lớn hơn dữ liệu của chính màn hình quản trị. Cần đánh giá quyền mới cho phép làm gì và có thể mở rộng sang những tài sản nào.

## 8. Đặc tả yêu cầu cụ thể cho mức đã chọn

Các ngưỡng sau là **giá trị minh họa của một dự án giả định**, cần được quyết định theo tác động và năng lực vận hành. Chúng không phải giá trị mặc định cho mọi hệ thống.

| Mã | Yêu cầu | Tiêu chí chấp nhận |
|---|---|---|
| RC-01 | API danh mục công khai chỉ lấy bản đã duyệt và trả tập trường được cho phép; người đọc ẩn danh không có quyền ghi hoặc đổi trạng thái công bố. | Thử bản nháp, trường nội bộ mới, phương thức ghi và đường xuất; không có nội dung ngoài phạm vi hay thay đổi trái quyền. |
| RC-02 | Mọi lần đọc đơn hàng hoặc tải tệp phải kiểm tra danh tính, hành động, tài nguyên và khách thuê ở máy chủ; không tin riêng mã do bên gọi tự truyền. | Thử người dùng khác quyền, khác khách thuê và tham chiếu tệp bị tráo qua mọi đường truy cập đã kiểm kê. |
| RC-03 | Tác vụ xuất phải giữ phạm vi ủy quyền do máy chủ xác lập; worker chỉ được đọc và ghi tài sản cần cho phạm vi đó; không nhận phạm vi mở rộng trực tiếp từ đầu vào chưa kiểm chứng. | Sửa thông điệp tác vụ, tham số lọc và khách thuê; worker từ chối hoặc giới hạn đúng, không đưa dữ liệu ngoài phạm vi vào kết quả. |
| RC-04 | Nếu chính sách yêu cầu phê duyệt độc lập khi cấp quyền cao, phê duyệt phải gắn với người nhận, quyền, khách thuê và phiên bản nội dung; thay nội dung phải yêu cầu duyệt lại. | Thử tự duyệt khi bị cấm, đổi người nhận/quyền sau duyệt, dùng lại phê duyệt và gửi đồng thời; không cấp quyền ngoài nội dung đã được duyệt. |
| RC-05 | Trước hành động cấp quyền cao, phiên phải đạt mức xác minh tăng cường đã duyệt, với lần xác minh phù hợp gần nhất không quá 5 phút. | Phiên chưa đủ mức, quá hạn, bằng chứng của phiên khác và gọi trực tiếp API không được hoàn tất hành động. |
| RC-06 | Kết quả xuất chỉ được tải trong 10 phút từ lúc tạo và phải kiểm tra lại quyền hiện tại của người tải theo chính sách; biết định danh tệp không đủ để tải. | Thử hết hạn, khác tài khoản, khác khách thuê, quyền đã thu hồi và liên kết cũ; không trả nội dung ngoài quyền. |
| RC-07 | Trước khi bắt đầu trả nội dung xuất, hệ thống phải ghi bền vững sự kiện gồm chủ thể, phạm vi, kết quả nhận yêu cầu và mã tương quan; kết quả kết thúc phải được ghi hoặc đối soát. | Gây lỗi ghi sự kiện trước tải; nội dung chưa được trả. Với thao tác đã bắt đầu, xác định được kết quả hoặc phát hiện trường hợp cần đối soát. |
| RC-08 | Log, trace và thông báo lỗi không được chứa token, thông tin xác thực, vật liệu khóa hoặc bản rõ nội dung đơn hàng; các tham chiếu còn lại được bảo vệ theo mục đích điều tra. | Dùng dữ liệu thử có dấu nhận diện qua đường thành công và đường lỗi; kiểm tra đầu ra vận hành và quyền truy cập kho log. |
| RC-09 | Sau khi thu hồi quyền quản trị, các hành động dựa vào quyền đó phải ngừng được chấp nhận trong 60 giây tại các điểm thực thi và bộ nhớ đệm được quản lý. | Kiểm thử qua nhiều phiên, API, worker và bản sao dịch vụ; sau thời hạn không thực hiện được hành động dựa vào quyền đã thu hồi. |
| RC-10 | Trong kịch bản mất kho phục vụ đã duyệt, phải khôi phục chức năng cốt lõi trong 60 phút và đạt mốc dữ liệu mất tối đa 15 phút, bao gồm quyền, khóa và phụ thuộc cần dùng. | Diễn tập từ mốc sự cố đã định; kiểm tra dữ liệu phục hồi, quyền hiện hành và khả năng thực hiện chức năng. |
| RC-11 | Khi không xác định được quyền hoặc trạng thái phê duyệt, hành động tương ứng phải bị từ chối hoặc chờ theo hợp đồng lỗi; không dùng trạng thái mặc định cho phép. | Gây gián đoạn dịch vụ phụ thuộc, dữ liệu thiếu và lỗi hết hạn; không có quyền hoặc nội dung được cấp trái chính sách. |
| RC-12 | Ngoại lệ của tập kiểm soát phải có phạm vi, rủi ro còn lại, kiểm soát bù, người có thẩm quyền và ngày hết hạn; không tự mở rộng hoặc gia hạn. | Thử hồ sơ thiếu điều kiện, sai phạm vi và hết hạn; không được dùng như quyết định hợp lệ cho cổng phát hành hoặc vận hành. |

Mục tiêu 60 phút trong RC-10 là **RTO**, tức thời gian phục hồi chức năng theo kịch bản đã đặc tả. Mốc mất dữ liệu tối đa 15 phút là **RPO**, tức mục tiêu điểm phục hồi. Việc có lịch sao lưu không thay thế bằng chứng thực sự khôi phục được tới mốc này.

RC-05 không có nghĩa mọi hình thức xác minh bổ sung đều tương đương. Chính sách phải định nghĩa cơ chế được chấp nhận, mức chống các đe dọa liên quan, cách bảo vệ phiên và quy trình cấp lại thông tin xác thực. Hai lần nhập một loại bí mật không tự trở thành hai yếu tố độc lập.

RC-06 kiểm soát tải kết quả; nó không tự xóa tệp khỏi mọi bản sao sau 10 phút. Thời hạn truy cập, thời hạn giữ tệp và thời hạn xóa bản sao cần được đặc tả riêng. Nếu cần giữ dữ liệu để điều tra, nơi giữ và quyền truy cập cũng phải được xác định.

RC-09 cần chỉ rõ cách hệ thống xử lý quyền đang dùng trong tác vụ dài. Một yêu cầu về thời gian thu hồi không có ý nghĩa nếu chỉ cập nhật màn hình quản trị mà worker vẫn tiếp tục sử dụng quyền cũ không giới hạn.

## 9. Lập hồ sơ quyết định để tránh chọn theo cảm tính

Một quyết định nên lưu được cả lý do chọn và phần còn lại chưa giải quyết. Nhờ đó, nhóm sau có thể biết vì sao một kiểm soát tồn tại và điều kiện nào khiến quyết định không còn phù hợp.

| Trường | Nội dung cần ghi |
|---|---|
| Mã tài sản và kịch bản | Tổ hợp tài sản, chủ thể, hành động, đường tấn công và tác động |
| Giới hạn quyết định | Điều kiện bắt buộc, khẩu vị liên quan và phạm vi ủy quyền |
| Phương án đã xét | Các biện pháp khả thi, tác dụng và lý do không chọn phương án chưa đủ |
| Tập kiểm soát được chọn | Vị trí thực thi, chính sách, giới hạn và hành vi khi lỗi |
| Yêu cầu về mức đảm bảo | Phạm vi kiểm tra, độ sâu, vai trò đánh giá và bằng chứng cần có |
| Hiện tại và mục tiêu | Kiểm soát đã có bằng chứng, kiểm soát còn kế hoạch và mức rủi ro tương ứng |
| Rủi ro còn lại | Đường tấn công hoặc sai hỏng còn tồn tại, giả định và độ bất định |
| Trách nhiệm và thời hạn | Chủ sở hữu rủi ro, chủ sở hữu kiểm soát, người quyết định và điều kiện rà soát |

Ví dụ sau là hồ sơ minh họa ở trạng thái đề xuất, không phải phê duyệt đang có hiệu lực:

```yaml
decision_id: CONTROL-SELECTION-ORDER-EXPORT
decision_status: proposed
asset: tenant_order_dataset
action: bulk_export
scenario: cross_tenant_disclosure_through_background_export
mandatory_boundary: no_cross_tenant_access
selected_requirements:
  - RC-02
  - RC-03
  - RC-06
  - RC-07
  - RC-08
enforcement_points:
  - export_request_api
  - job_authorization_and_worker
  - scoped_data_query
  - result_storage_and_download
required_evidence:
  - negative_authorization_tests_across_tenants
  - job_message_tampering_tests
  - permission_change_during_job_tests
  - audit_storage_failure_tests
  - deployed_service_permissions_review
residual_risk_review:
  includes_compromised_authorized_account: true
  includes_bulk_export_abuse: true
approval: required_before_production_activation
review_triggers:
  - new_export_channel
  - expanded_dataset
  - changed_worker_identity_or_permissions
```

Không nên hiểu việc có danh sách kiểm thử là đã có kết quả đạt. Hồ sơ cần chỉ ra bằng chứng thực tế trước khi chuyển từ đề xuất sang quyết định được xác nhận. Các tham chiếu và mã trong ví dụ chỉ phục vụ diễn giải, không yêu cầu tạo thêm tệp cấu hình.

## 10. Chọn độ sâu kiểm chứng tương ứng

### 10.1. Kiểm chứng hành vi và ranh giới

Với một kiểm soát, nên xem các nhóm trường hợp sau:

| Nhóm kiểm chứng | Mục đích | Ví dụ |
|---|---|---|
| Dương | Người đúng quyền vẫn hoàn thành chức năng đúng | Nhân viên được phép tải đơn hàng thuộc khách thuê của mình |
| Phủ định | Chủ thể thiếu điều kiện không thực hiện được | Cùng người dùng nhưng khác đơn hàng, khách thuê hoặc hành động |
| Ranh giới trạng thái | Kiểm soát giữ đúng khi thời hạn, quyền hoặc trạng thái thay đổi | Hết hạn xác minh, thu hồi quyền khi tác vụ đang chờ, sửa nội dung sau duyệt |
| Đường thay thế | Không có đường khác bỏ qua điều kiện | API cũ, URL tệp, tác vụ nền, trang hỗ trợ và công cụ quản trị |
| Lỗi phụ thuộc | Thất bại không làm hệ thống tự mở quyền | Dịch vụ quyền không trả lời, thiếu bằng chứng phê duyệt, không ghi được sự kiện |
| Đồng thời | Các yêu cầu đua nhau không phá giới hạn | Dùng lại cùng phê duyệt, cập nhật quyền trong lúc thực hiện, tải sau thu hồi |
| Vận hành và phục hồi | Cấu hình thật và trạng thái sau sự cố vẫn đáp ứng | Quyền của worker, bộ nhớ đệm, khôi phục quyền và khóa từ bản sao |

Với kịch bản có tác động lớn, kiểm chứng có thể cần người đánh giá độc lập với phần triển khai và các bài thử đối kháng theo mô hình đe dọa. Mức độc lập và phạm vi phải được chỉ rõ trong quyết định, thay vì chỉ ghi “đã được review”.

### 10.2. Xác định điều kiện để bằng chứng còn hiệu lực

Kết quả kiểm thử cần gắn với phiên bản, cấu hình, môi trường và tập đường xử lý. Một lần kiểm tra thành công không tự bao phủ chức năng được thêm sau đó.

Cần phân biệt:

- Bằng chứng rằng chính sách được viết đúng.
- Bằng chứng rằng mã thực thi đúng chính sách.
- Bằng chứng rằng cấu hình và quyền trên môi trường phục vụ khớp với thiết kế.
- Bằng chứng rằng cơ chế vẫn hoạt động khi lỗi hoặc thay đổi trạng thái.

Mức đảm bảo phải phản ánh phạm vi thực sự đã xem xét. Nếu chưa kiểm tra đường xuất CSV hoặc tài khoản vận hành, không nên kết luận mọi đường dữ liệu đã được bảo vệ chỉ từ các bài thử API chính.

## 11. Xem xét chi phí và rủi ro mới do kiểm soát tạo ra

Kiểm soát cũng có phụ thuộc và khả năng thất bại. Lựa chọn theo rủi ro cần đánh giá chúng để không giảm một vấn đề rồi tạo ra một vấn đề lớn hơn ở nơi khác.

| Lựa chọn | Lợi ích dự kiến | Điều cần kiểm soát thêm |
|---|---|---|
| Xác minh tăng cường trước hành động nhạy cảm | Giảm một số đường lạm dụng phiên hoặc thông tin xác thực | Cấp lại thông tin xác thực, hỗ trợ người mất phương tiện và hành vi khi dịch vụ xác minh lỗi |
| Phê duyệt độc lập | Giảm quyền quyết định của một chủ thể trên hành động lớn | Tính độc lập thực tế, ràng buộc nội dung, phát lại và khả năng vận hành khi người duyệt vắng mặt |
| Giới hạn khối lượng xuất | Giảm phạm vi của một thao tác và chi phí tài nguyên | Nhiều yêu cầu nhỏ có thể vượt giới hạn tổng; cần xét cửa sổ và phạm vi cộng dồn phù hợp |
| Tách quyền dịch vụ và khóa | Thu hẹp phạm vi ảnh hưởng khi một danh tính bị chiếm quyền | Cấp phát, thu hồi, theo dõi phụ thuộc và phục hồi đúng các quyền cần thiết |
| Logging chặt chẽ | Tăng khả năng điều tra và phát hiện | Rò rỉ dữ liệu qua log, dung lượng, mất thu thập và quyền sửa bằng chứng |
| Phụ thuộc vào kiểm tra quyền tập trung | Chính sách nhất quán và dễ quản lý hơn | Độ trễ, sự sẵn sàng, tính cập nhật của bộ nhớ đệm và hành vi khi không có kết quả |

Ví dụ, nếu yêu cầu ghi bằng chứng trước khi xuất nhưng kho giám sát tập trung có thể gián đoạn, kiến trúc có thể cần nơi ghi bền vững được thiết kế để chuyển tiếp và đối soát. Cần quy định giới hạn dung lượng, độ trễ, quyền truy cập và điểm dừng khi không còn bảo đảm. Không được tự thay bằng ghi tạm không đáng tin rồi vẫn khẳng định đáp ứng yêu cầu.

Nếu chi phí của một phương án quá lớn, nên quay lại mục tiêu và phạm vi: xuất ít trường hơn, giảm nhóm được mở tính năng, rút ngắn thời gian giữ kết quả hoặc chưa hỗ trợ một hành động rủi ro cao. Việc điều chỉnh phải thay đổi phơi nhiễm thật, thay vì chỉ hạ nhãn rủi ro trên hồ sơ.

## 12. Ví dụ truy vết đầy đủ qua luồng xuất

Một người dùng có quyền xuất đơn hàng thuộc khách thuê A. Tác vụ chạy sau vài phút, tạo tệp trong kho và trả tham chiếu để tải.

1. **Ở yêu cầu tạo:** hệ thống xác thực người dùng, kiểm tra quyền xuất, xác lập khách thuê và tập dữ liệu từ ngữ cảnh đáng tin. Yêu cầu không được tự mở rộng sang khách thuê B.
2. **Ở thông điệp tác vụ:** phạm vi ủy quyền có nguồn gốc và tính toàn vẹn được bảo vệ. Không coi mọi trường trong hàng đợi là đáng tin chỉ vì đó là một hệ thống nội bộ.
3. **Ở worker:** danh tính dịch vụ chỉ có quyền cần thiết; nguồn dữ liệu và truy vấn giữ đúng phạm vi. Hệ thống xử lý thay đổi quyền theo chính sách đã đặc tả, thay vì mặc định quyền lúc tạo tồn tại mãi.
4. **Ở tệp kết quả:** tệp gắn với phạm vi và tác vụ, không chứa trường ngoài tập được duyệt. Truy cập trực tiếp kho không trở thành đường bỏ qua kiểm tra quyền.
5. **Ở tải kết quả:** kiểm tra chủ thể, quyền hiện tại, phạm vi và thời hạn. Tham chiếu khó đoán không thay cho các điều kiện này.
6. **Ở logging và ứng phó:** có sự kiện đủ nối các giai đoạn mà không ghi bản rõ. Khi có dấu hiệu lạm dụng, có thể dừng tác vụ, chặn tải hoặc thu hồi quyền theo thẩm quyền và thời hạn đã chọn.
7. **Ở lưu giữ và phục hồi:** kết quả hết thời hạn được xử lý theo chính sách; bản sao phục hồi không làm tệp hoặc quyền đã thu hồi trở lại đường phục vụ trái điều kiện.

Sau tập kiểm soát này vẫn có thể còn rủi ro từ một tài khoản có quyền hợp lệ bị chiếm quyền hoặc người nội bộ lạm dụng quyền. Đánh giá còn lại cần xem quy mô xuất, giới hạn tổng, xác minh bổ sung nếu phù hợp, khả năng phát hiện và hành động khoanh vùng. Không nên kết luận “đã có phân quyền nên không còn rủi ro xuất dữ liệu”.

Điểm nối quan trọng là: mỗi kiểm soát được chọn có một đường gây thiệt hại cụ thể, một vị trí thực thi và bằng chứng tương ứng. Những phần chưa bao phủ được ghi thành rủi ro còn lại để xử lý hoặc quyết định đúng thẩm quyền.

## 13. Theo dõi hiệu lực và điều chỉnh mức

Quyết định ban đầu cần được xem lại khi thêm loại dữ liệu, mở API mới, thay danh tính worker, tăng khối lượng hoặc thay cách phân phối kết quả. Sự cố, kiểm thử thất bại và ngoại lệ kéo dài cũng là tác nhân đánh giá lại.

Các thước đo có thể hỗ trợ gồm đường truy cập chưa được kiểm kê, khoảng trống kiểm thử, độ trễ thu hồi, sự kiện thiếu, kết quả diễn tập phục hồi và số ngoại lệ quá hạn. Chúng cần được diễn giải cùng tác động và phạm vi, không cộng thành một “điểm an toàn” duy nhất rồi bỏ qua một điều kiện trọng yếu.

Không có sự cố được phát hiện không tự chứng minh kiểm soát hiệu quả. Có thể đường tấn công chưa bị sử dụng hoặc khả năng quan sát chưa đủ. Cần kết hợp số liệu vận hành với bằng chứng chủ động về cơ chế bảo vệ.

Khi tăng mức, hãy chỉ rõ rủi ro hoặc khoảng trống nào đòi hỏi tăng. Khi giảm mức, cần chứng minh thay đổi về phơi nhiễm, tác động hoặc bằng chứng đủ để quyết định đó còn nằm trong giới hạn. Những điều kiện bắt buộc vẫn phải được đáp ứng.

## 14. Sai lầm thường gặp

| Sai lầm | Vì sao chưa đủ | Cách làm rõ |
|---|---|---|
| Mọi chức năng dùng cùng một mức | Không xét hành động, quy mô và thuộc tính cần bảo vệ | Chọn theo tài sản, hành động, chủ thể và ngữ cảnh |
| Rủi ro cao thì thêm nhiều công cụ | Công cụ có thể không chặn đường gây thiệt hại | Gắn kiểm soát với tác dụng và vị trí thực thi cụ thể |
| Có mã hóa là đủ bảo vệ dữ liệu | Ứng dụng vẫn có thể trả bản rõ sai quyền | Kiểm tra danh tính, đối tượng, khách thuê và đường xuất |
| Có logging là có thể bỏ kiểm soát phòng ngừa | Bằng chứng không thu hồi được dữ liệu đã tiết lộ | Phân biệt ngăn chặn, phát hiện, khoanh vùng và phục hồi |
| Chỉ kiểm tra tại giao diện hoặc API đầu tiên | Worker, tệp trực tiếp và API cũ có thể bỏ qua | Kiểm kê và kiểm chứng toàn luồng liên quan |
| Kiểm soát trong kế hoạch được tính như đã có | Rủi ro hiện tại bị đánh giá thấp | Tách đã triển khai, đã có bằng chứng và trạng thái mục tiêu |
| Có bài kiểm thử là đủ mức đảm bảo | Có thể thiếu cấu hình thật, đường lỗi và trạng thái đồng thời | Gắn bằng chứng với phiên bản, môi trường và phạm vi |
| Giảm kiểm soát để đạt lịch phát hành | Phơi nhiễm không đổi nhưng giới hạn bị bỏ qua | Thu hẹp chức năng hoặc quyết định rủi ro đúng thẩm quyền |

## 15. Đầu ra cần có sau khi lựa chọn

Người xây dựng yêu cầu bảo mật cần bàn giao được:

1. **Kịch bản rủi ro:** tài sản, hành động, tác nhân, điểm yếu, tác động và phạm vi ảnh hưởng.
2. **Căn cứ lựa chọn:** điều kiện bắt buộc, khẩu vị, đánh giá khả năng, tác động và độ bất định.
3. **Tập kiểm soát:** tác dụng, vị trí, quyền, ngữ cảnh, giới hạn và hành vi khi lỗi.
4. **Yêu cầu có thể kiểm chứng:** cho xác thực, phân quyền, dữ liệu, logging, ứng phó và phục hồi khi liên quan.
5. **Kế hoạch bằng chứng:** trường hợp dương, phủ định, trạng thái, đường thay thế, lỗi phụ thuộc và mức độc lập cần thiết.
6. **Quyết định rủi ro còn lại:** phần chưa giải quyết, người chịu trách nhiệm, thẩm quyền, thời hạn và tác nhân rà soát lại.

Chọn mức kiểm soát theo rủi ro giúp tập trung nguồn lực vào những đường có thể gây thiệt hại thực tế và những điều kiện cần giữ vững. Khi mỗi lựa chọn được nối với yêu cầu, kiến trúc và bằng chứng, nhóm có thể giải thích vì sao mức bảo vệ đã chọn phù hợp và điều gì cần thay đổi khi rủi ro thay đổi.
