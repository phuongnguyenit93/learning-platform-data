# Traceability từ rủi ro đến kiểm thử

## 1. Traceability giúp trả lời điều gì?

Trong một dự án, nhóm bảo mật có thể lập danh sách rủi ro, nhóm phân tích viết yêu cầu, nhóm phát triển chọn cơ chế bảo vệ và nhóm kiểm thử chạy nhiều ca kiểm thử. Dù từng phần đều tồn tại, vẫn có thể không ai trả lời được:

- Rủi ro này đang được giảm bằng yêu cầu nào?
- Cơ chế đã triển khai có thực sự phục vụ yêu cầu đó không?
- Ca kiểm thử nào chứng minh hành vi bảo vệ cần có?
- Kết quả kiểm thử thuộc phiên bản, cấu hình và môi trường nào?
- Khi một yêu cầu thay đổi, cần sửa thiết kế và chạy lại những kiểm thử nào?

**Traceability**, hay **khả năng truy vết**, là khả năng theo dõi các mối liên hệ có ý nghĩa giữa những đối tượng này trong suốt vòng đời phát triển. Với yêu cầu bảo mật, một chuỗi thường dùng là:

**Tài sản và ngữ cảnh → rủi ro → yêu cầu bảo mật → thiết kế và biện pháp kiểm soát → ca kiểm thử → lần chạy → bằng chứng → quyết định về rủi ro còn lại.**

Truy vết có hai chiều:

| Chiều truy vết | Câu hỏi chính | Giá trị sử dụng |
| --- | --- | --- |
| Từ rủi ro đi tới kiểm thử | Mỗi rủi ro đã có yêu cầu, thiết kế và bằng chứng phù hợp chưa? | Phát hiện phần bị bỏ sót |
| Từ kiểm thử quay về rủi ro | Vì sao kiểm thử này tồn tại, và nó bảo vệ điều gì? | Phát hiện kiểm thử không rõ mục đích hoặc bị hiểu quá mức |
| Theo thay đổi | Những đối tượng nào bị ảnh hưởng khi một mắt xích thay đổi? | Lập phạm vi sửa đổi và kiểm thử lại |
| Theo phiên bản | Bằng chứng nào còn áp dụng cho bản phát hành đang xét? | Tránh dùng kết quả cũ cho một hệ thống đã thay đổi |

Một đường liên kết tồn tại không đồng nghĩa yêu cầu đã được đáp ứng. Ca kiểm thử có thể chưa chạy, đã thất bại, chỉ bao phủ một nhánh hoặc dựa vào dữ liệu không phù hợp. Truy vết phải giữ cả **ý nghĩa liên kết**, **trạng thái thực hiện** và **phạm vi bằng chứng**.

Sau bài này, người học cần có thể tạo một chuỗi truy vết cho rủi ro cụ thể, viết tiêu chí chấp nhận có thể kiểm chứng, đọc ma trận truy vết và phân tích tác động khi thiết kế thay đổi.

## 2. Bối cảnh: dịch vụ quản lý đơn hàng nhiều tenant

Giả sử một dịch vụ phục vụ nhiều doanh nghiệp. Mỗi doanh nghiệp là một **tenant**, có dữ liệu, người dùng và phạm vi quyền riêng.

Dịch vụ cho phép:

- Đăng nhập và quản lý phiên.
- Xem, xuất dữ liệu đơn hàng.
- Phê duyệt đơn hàng theo vai trò.
- Cấp và thu hồi quyền trong từng tenant.
- Ghi nhận sự kiện kiểm toán.
- Sao lưu và phục hồi dữ liệu khi xảy ra sự cố.

Tài sản cần bảo vệ gồm nội dung đơn hàng, dữ liệu khách hàng trong đơn, quyền phê duyệt, thông tin xác thực và lịch sử thao tác.

Một mô hình đe dọa tối thiểu cần nêu tác nhân, điểm vào, tài sản, ranh giới tin cậy và các giả định. Trong ví dụ này:

- Người dùng đã đăng nhập vẫn có thể gửi yêu cầu trái phép.
- Mã đơn hàng và mã tenant trong yêu cầu là dữ liệu đầu vào cần kiểm tra.
- API có thể được gọi trực tiếp, không qua giao diện.
- Dịch vụ phụ thuộc và công việc chạy nền có thể gặp lỗi.
- Phiên và cache quyền có thể giữ trạng thái cũ.
- Sao lưu có thể chứa trạng thái dữ liệu và quyền trước thời điểm sự cố.

### 2.1. Danh sách rủi ro minh họa

| Mã | Tình huống có thể xảy ra | Tài sản và hậu quả |
| --- | --- | --- |
| RISK-01 | Thành viên tenant A thay mã đơn hàng hoặc mã công việc xuất dữ liệu để truy cập đối tượng của tenant B | Lộ dữ liệu đơn hàng và khách hàng giữa các tenant |
| RISK-02 | Kẻ tấn công có mật khẩu của tài khoản phê duyệt và dùng nó để đăng nhập | Phê duyệt trái phép dưới danh tính hợp lệ |
| RISK-03 | Thành viên bị thu hồi quyền tiếp tục sử dụng phiên hoặc bản quyền trong cache | Thực hiện thao tác sau khi không còn được phép |
| RISK-04 | Thay đổi quyền hoặc phê duyệt không để lại dấu vết cần thiết | Không đủ dữ liệu để truy tìm chủ thể và diễn biến sự cố |
| RISK-05 | Token hoặc nội dung đơn hàng bị ghi vào hệ thống log | Người có quyền đọc log tiếp cận dữ liệu ngoài phạm vi cần thiết |
| RISK-06 | Phục hồi chậm, mất dữ liệu vượt mức chấp nhận hoặc khôi phục lại quyền đã thu hồi | Gián đoạn nghiệp vụ, mất tính toàn vẹn hoặc mở lại quyền không hợp lệ |

Bảng này chỉ tạo bối cảnh học tập. Trong dự án, mỗi rủi ro còn cần chủ sở hữu, cách đánh giá khả năng xảy ra và tác động, mức ưu tiên, giả định cùng quyết định xử lý.

Không được đồng nhất ba khái niệm:

- **Đe dọa:** tác nhân hoặc tình huống có khả năng gây hại.
- **Điểm yếu:** điều kiện khiến hành vi gây hại có thể thành công, chẳng hạn thiếu kiểm tra quyền tại API tải tệp xuất.
- **Rủi ro:** khả năng xảy ra hậu quả và mức tác động trong ngữ cảnh cụ thể.

Một rủi ro có thể xuất hiện trước khi đã chứng minh có điểm yếu trong mã nguồn. Ngược lại, một lỗi đã xác nhận có thể làm thay đổi đánh giá rủi ro và ưu tiên khắc phục.

### 2.2. Từ rủi ro đến quyết định xử lý

Không phải rủi ro nào cũng chuyển thẳng thành một chức năng mới. Có thể chọn:

- **Giảm rủi ro:** bổ sung hoặc cải thiện biện pháp bảo vệ.
- **Tránh rủi ro:** loại bỏ chức năng hoặc luồng nghiệp vụ tạo ra rủi ro.
- **Chia sẻ hoặc chuyển một phần trách nhiệm:** sử dụng nhà cung cấp hay thỏa thuận phù hợp; vẫn phải làm rõ nghĩa vụ còn lại.
- **Chấp nhận rủi ro:** chủ sở hữu có thẩm quyền chấp nhận trong phạm vi và thời hạn xác định.

Ví dụ, tạm loại bỏ chức năng xuất dữ liệu có thể loại bỏ một đường khai thác của RISK-01, nhưng chưa giải quyết đường đọc chi tiết đơn hàng. Thuê nhà cung cấp danh tính cũng không tự giải quyết quyền truy cập đơn hàng.

Vì vậy, hồ sơ truy vết phải liên kết tới **quyết định xử lý** trước khi kết luận một rủi ro đã được xử lý. Rủi ro được chấp nhận không được ghi thành yêu cầu đã triển khai hoặc kiểm thử đã đạt.

## 3. Những mắt xích cần định danh

Có thể dùng mã ổn định để nhận diện các đối tượng:

| Đối tượng | Mã ví dụ | Nội dung phải giữ được |
| --- | --- | --- |
| Tài sản | ASSET-ORDER | Dữ liệu nào, ai sở hữu, giá trị cần bảo vệ |
| Kịch bản đe dọa | THREAT-01 | Ai làm gì qua điểm vào nào, vượt ranh giới nào |
| Rủi ro | RISK-01 | Hậu quả, đánh giá, chủ sở hữu và cách xử lý |
| Yêu cầu | SEC-REQ-01 | Nghĩa vụ có phạm vi, điều kiện và tiêu chí chấp nhận |
| Quyết định thiết kế | ARCH-DEC-01 | Cơ chế được chọn, lý do và giới hạn |
| Thành phần kiểm soát | CTRL-AUTHZ | Nơi thực thi biện pháp bảo vệ |
| Ca kiểm thử | TEST-01 | Tiền điều kiện, dữ liệu, thao tác và kết quả mong đợi |
| Lần chạy | RUN-01 | Phiên bản, môi trường, thời điểm và kết quả thực tế |
| Bằng chứng | EVID-01 | Tệp hoặc bản ghi chứng minh điều đã quan sát |
| Quyết định rủi ro còn lại | RISK-DEC-01 | Phần còn lại, căn cứ và người chấp nhận |

Mã giúp liên kết bền vững khi tên hoặc mô tả thay đổi. Không cần nhét mọi thông tin vào tên mã; nội dung và phiên bản mới là nơi diễn giải đầy đủ.

### 3.1. Ghi rõ ý nghĩa của quan hệ

Một danh sách “có liên quan” thường quá mơ hồ. Nên ghi rõ quan hệ:

| Quan hệ | Ý nghĩa |
| --- | --- |
| Rủi ro **được giảm bởi** yêu cầu | Yêu cầu đóng góp vào việc giảm khả năng xảy ra hoặc tác động |
| Yêu cầu **được hiện thực bởi** thiết kế và kiểm soát | Cơ chế được giao trách nhiệm thực hiện nghĩa vụ |
| Yêu cầu **được kiểm chứng bởi** ca kiểm thử hoặc phương pháp khác | Phương pháp thu thập bằng chứng cho một hoặc nhiều tiêu chí |
| Lần chạy **thực thi** ca kiểm thử | Tách định nghĩa phép thử khỏi kết quả ở một thời điểm |
| Bằng chứng **hỗ trợ** kết luận của lần chạy | Giữ được dữ liệu để xem lại kết quả |
| Quyết định **chấp nhận** rủi ro còn lại | Ghi nhận quyết định quản lý, không thay thế kết quả kiểm thử |

Một yêu cầu có thể giảm nhiều rủi ro. Một rủi ro có thể cần nhiều yêu cầu. Một ca kiểm thử có thể kiểm chứng nhiều tiêu chí nếu kết quả cho từng tiêu chí vẫn phân biệt được. Đây là mạng quan hệ nhiều–nhiều, không phải một danh sách ghép một rủi ro với một bài kiểm thử duy nhất.

## 4. Chuyển một rủi ro thành yêu cầu có thể kiểm chứng

Xét RISK-01: thành viên tenant A đọc hoặc xuất được dữ liệu đơn hàng của tenant B.

Phát biểu “hệ thống phải bảo đảm cách ly tenant” diễn đạt mục tiêu nhưng chưa đủ để thiết kế và nghiệm thu. Cần tách thành các nghĩa vụ có ranh giới rõ ràng.

### 4.1. Yêu cầu cho thao tác đọc đơn hàng

**SEC-REQ-01 — Kiểm tra quyền đọc trên tài nguyên đích**

> Với mọi yêu cầu đọc chi tiết đơn hàng qua API, dịch vụ phải xác định danh tính hợp lệ và kiểm tra quyền đọc của danh tính đó đối với đơn hàng đích trong tenant của đơn hàng. Nếu không có quyền hoặc không xác định được quyền, dịch vụ phải từ chối và không trả về nội dung đơn hàng.

Tiêu chí chấp nhận:

1. Người có quyền trong tenant của đơn hàng đọc được dữ liệu thuộc phạm vi được cấp.
2. Người dùng tenant A không đọc được đơn hàng tenant B, kể cả khi biết chính xác mã đơn hàng.
3. Sửa mã tenant trong đường dẫn, tham số hoặc nội dung yêu cầu không mở rộng được quyền.
4. Thiếu hoặc không có danh tính hợp lệ không dẫn đến trả dữ liệu.
5. Lỗi xác định quyền không tạo đường đi cho phép mặc định.
6. Phản hồi lỗi không chứa nội dung đơn hàng cần bảo vệ.

Hợp đồng API cần quy định cách phản hồi cho tài nguyên không tồn tại và tài nguyên không được phép truy cập. Nếu mục tiêu bao gồm việc che giấu sự tồn tại của tài nguyên, phải đặc tả và kiểm chứng riêng điều đó. Chỉ dùng cùng một mã lỗi chưa chứng minh đã loại bỏ mọi khác biệt có thể quan sát.

### 4.2. Yêu cầu cho xuất dữ liệu bất đồng bộ

**SEC-REQ-02 — Giới hạn phạm vi tạo và tải bản xuất**

> Dịch vụ chỉ được tạo bản xuất từ các đơn hàng mà người yêu cầu có quyền xuất trong tenant tương ứng. Tại thời điểm tải bản xuất, dịch vụ phải xác thực người tải và kiểm tra quyền truy cập bản xuất theo tenant, chủ thể được cấp và thời hạn đã quy định. Nếu không đạt điều kiện, không trả nội dung tệp.

Đối với ví dụ này, giả định người yêu cầu phải còn quyền xuất tại lúc bắt đầu tạo dữ liệu và lúc tải tệp. Nếu nghiệp vụ chọn chính sách khác, phải ghi rõ mốc hiệu lực thay vì để tác vụ nền tự quyết định.

Ca kiểm thử cần bao phủ cả:

- Thao tác tạo công việc xuất.
- Phạm vi dữ liệu mà tác vụ nền đọc.
- Truy vấn trạng thái công việc.
- Tải tệp bằng mã hoặc liên kết.
- Hành vi khi quyền bị thu hồi giữa các bước.

Ẩn nút xuất hoặc kiểm tra quyền ở bước tạo công việc chưa chứng minh được bước tải tệp an toàn. Mỗi đường truy cập có thể là một điểm thực thi kiểm soát khác nhau.

### 4.3. Yêu cầu về chất lượng không được làm yếu nghĩa vụ bảo vệ

**SEC-REQ-03 — Ngân sách thời gian đánh giá quyền**

> Trong môi trường kiểm thử đã xác định, với 200 yêu cầu đọc chi tiết đơn hàng mỗi giây trong 30 phút, độ trễ bước đánh giá quyền tại dịch vụ phải có p95 không quá 50 ms. Mọi trường hợp được kiểm chứng trong lượt thử phải giữ đúng quyết định cho phép hoặc từ chối theo bộ dữ liệu quyền.

Các số trên là **giả định minh họa**, không phải ngưỡng chung cho sản phẩm. Kế hoạch đo phải nêu tài nguyên triển khai, dữ liệu, tỷ lệ yêu cầu hợp lệ và bị từ chối, trạng thái cache, mốc bắt đầu/kết thúc, cách tính timeout và lỗi.

p95 là phân vị 95 của tập độ trễ. Nó không phải thời gian tối đa và không cho phép một tỷ lệ quyết định phân quyền bị sai. Độ trễ và tính đúng là hai nội dung phải quan sát riêng.

### 4.4. Giữ nghĩa vụ, giải pháp và bằng chứng ở đúng vai trò

| Lớp | Ví dụ | Điều chưa thể kết luận |
| --- | --- | --- |
| Yêu cầu | Người tenant A không được đọc đơn hàng B | Chưa nói cơ chế cụ thể sẽ thực hiện thế nào |
| Thiết kế | Kiểm tra quyền tại dịch vụ; giới hạn truy vấn bằng tenant của tài nguyên | Chưa chứng minh mọi đường đọc đều đi qua kiểm soát |
| Hiện thực | Bộ lọc yêu cầu, hàm kiểm tra quyền, truy vấn và kiểm tra lúc tải tệp | Chưa chứng minh hành vi đúng trong mọi trường hợp cần xét |
| Kiểm chứng | Kiểm thử API, kiểm tra đường dữ liệu, đo tải, gây lỗi có kiểm soát | Chỉ kết luận trong phạm vi và phiên bản đã thu thập bằng chứng |

Câu “dùng token” không thay thế SEC-REQ-01. Một token hợp lệ giúp xác định danh tính nhưng không tự cho biết danh tính đó được đọc mọi đơn hàng hay không.

## 5. Nối yêu cầu với kiến trúc và thành phần kiểm soát

Giả sử nhóm chọn các quyết định sau:

| Mã thiết kế | Nội dung | Yêu cầu được hỗ trợ |
| --- | --- | --- |
| ARCH-DEC-01 | Danh tính và phạm vi phiên được lấy từ ngữ cảnh xác thực đáng tin cậy; dữ liệu tenant do client gửi vẫn phải được đối chiếu | SEC-REQ-01, SEC-REQ-02 |
| ARCH-DEC-02 | Dịch vụ thực hiện kiểm tra quyền trên thao tác và tài nguyên; tầng truy vấn giới hạn dữ liệu theo tenant phù hợp | SEC-REQ-01 |
| ARCH-DEC-03 | Công việc xuất lưu ngữ cảnh cần thiết; worker xác định phạm vi dữ liệu và quyền theo chính sách; bước tải kiểm tra quyền độc lập | SEC-REQ-02 |
| ARCH-DEC-04 | Nếu bước quyết định quyền lỗi hoặc timeout, thao tác được bảo vệ bị từ chối theo hợp đồng | SEC-REQ-01, SEC-REQ-02 |
| ARCH-DEC-05 | Đo riêng độ trễ đánh giá quyền; tối ưu theo kết quả tải mà vẫn giữ đúng quyết định | SEC-REQ-03 |

Thiết kế phải chỉ ra **điểm thực thi**. Một sơ đồ chỉ vẽ hộp “authorization” chưa giải thích yêu cầu có đi qua hộp đó hay có đường đi khác.

Với đọc đơn hàng, cần biết:

- Ai xác định danh tính?
- Ai quyết định quyền cho tài nguyên đích?
- Ai giới hạn dữ liệu trả về?
- Endpoint nội bộ hoặc endpoint cũ có cùng nghĩa vụ không?
- Khi phụ thuộc lỗi, thành phần nào quyết định từ chối?

Với bản xuất, cần biết thêm dữ liệu được đọc bằng danh tính nào, phạm vi tenant có được truyền an toàn tới tác vụ nền không, và đường tải tệp có thể vượt qua dịch vụ hay không.

Nếu chọn liên kết tải trực tiếp từ kho lưu trữ, nhóm phải phân tích đặc tính quyền của liên kết đó. Một liên kết hoạt động như quyền truy cập theo người nắm giữ có thể không đáp ứng yêu cầu xác thực và kiểm tra quyền tại thời điểm tải. Khi đó cần thay đổi thiết kế hoặc sửa yêu cầu qua quyết định có thẩm quyền; không chỉ đổi tên cơ chế để coi như đã đạt.

## 6. Từ tiêu chí chấp nhận đến ca kiểm thử

Một ca kiểm thử có thể kiểm chứng yêu cầu cần mô tả đủ:

| Nội dung | Mục đích |
| --- | --- |
| Yêu cầu và tiêu chí liên quan | Nêu chính xác phần nghĩa vụ đang kiểm chứng |
| Tiền điều kiện | Thiết lập danh tính, quyền, tenant, tài nguyên và trạng thái phụ thuộc |
| Dữ liệu | Phân biệt rõ trường hợp hợp lệ với trường hợp bị cấm |
| Hành động | Gửi yêu cầu qua điểm vào nào, có sửa đầu vào gì |
| Kết quả mong đợi | Định nghĩa điều phải xảy ra và điều bị cấm |
| Quan sát | Thu thập dữ liệu ở đâu để đánh giá kết quả |
| Dọn dữ liệu | Tránh trạng thái lượt thử trước ảnh hưởng lượt thử sau |

### 6.1. Ca kiểm thử cụ thể cho truy cập khác tenant

~~~text
Mã: TEST-02
Yêu cầu: SEC-REQ-01, tiêu chí 2, 3 và 6

Tiền điều kiện:
- Tồn tại tenant A và tenant B.
- User A có phiên hợp lệ, chỉ có quyền đọc đơn hàng trong tenant A.
- Order A thuộc tenant A.
- Order B thuộc tenant B và có một giá trị dữ liệu giả dễ nhận diện.

Hành động:
1. Dùng phiên User A đọc Order A để kiểm tra dữ liệu nền và phiên hoạt động.
2. Dùng cùng phiên gọi trực tiếp API đọc Order B.
3. Thử sửa mã tenant ở các vị trí mà hợp đồng API hỗ trợ.
4. Kiểm tra phản hồi và các thông điệp lỗi liên quan.

Kết quả mong đợi:
- Bước đối chứng hợp lệ đọc được Order A.
- Các lần đọc Order B bị từ chối theo hợp đồng API.
- Không có nội dung hoặc giá trị nhận diện của Order B trong phản hồi.
- Thay mã tenant không làm mở rộng quyền.
~~~

Bước đối chứng hợp lệ rất quan trọng. Nếu mọi yêu cầu đều bị lỗi do dữ liệu sai hoặc môi trường hỏng, kết quả “không đọc được Order B” chưa chứng minh bộ kiểm soát tenant hoạt động.

Bộ dữ liệu mong đợi nên được xác định độc lập từ cấu hình kiểm thử đã biết. Nếu kiểm thử dùng lại đúng hàm phân quyền của ứng dụng để quyết định kết quả mong đợi, cùng một lỗi có thể xuất hiện ở cả hệ thống lẫn phép kiểm tra.

### 6.2. Bộ kiểm thử không chỉ có đường bị từ chối

| Mã | Tình huống | Điều cần quan sát |
| --- | --- | --- |
| TEST-01 | Người có quyền đọc đơn hàng đúng tenant | Trả đúng dữ liệu được phép |
| TEST-02 | Đổi mã đơn hàng hoặc mã tenant để đọc dữ liệu tenant khác | Từ chối, không trả dữ liệu ngoài quyền |
| TEST-03 | Thiếu hoặc có thông tin xác thực không hợp lệ | Không trả dữ liệu được bảo vệ |
| TEST-04 | Thành phần đánh giá quyền lỗi hoặc timeout | Từ chối đúng chính sách, không cho phép mặc định |
| TEST-05 | Tạo và tải bản xuất của chính mình | Bản xuất chỉ có dữ liệu trong phạm vi được cấp |
| TEST-06 | Dùng mã công việc hoặc liên kết xuất của tenant khác | Không lộ trạng thái nhạy cảm hoặc nội dung tệp theo hợp đồng |
| TEST-07 | Thu hồi quyền sau khi tạo công việc xuất | Worker và bước tải áp dụng đúng mốc kiểm tra đã đặc tả |
| TEST-08 | Tải 200 yêu cầu mỗi giây trong 30 phút | Độ trễ đạt ngưỡng minh họa và quyết định quyền vẫn đúng |

TEST-08 không thay thế TEST-02 hoặc TEST-04. Đạt hiệu năng không chứng minh cách ly tenant; vài trường hợp phân quyền đúng cũng không chứng minh đạt hiệu năng.

### 6.3. Khi phản hồi không đủ làm bằng chứng

Với yêu cầu có tác động nghiệp vụ, cần quan sát cả tác động sau phản hồi.

Ví dụ, API phê duyệt trả lỗi nhưng đã ghi thay đổi trạng thái hoặc đã đẩy một thông điệp thanh toán vào hàng đợi. Nếu yêu cầu chỉ được kiểm tra bằng mã HTTP, ca kiểm thử có thể báo đạt trong khi nghĩa vụ “không thực hiện thao tác” đã bị vi phạm.

Tương tự, một tác vụ xuất bị từ chối ở bước tải vẫn có thể đã tạo một tệp chứa dữ liệu ngoài quyền trong kho. Kiểm chứng SEC-REQ-02 phải xét cả phạm vi dữ liệu mà worker tạo ra và điều kiện tải tệp.

## 7. Mở rộng truy vết sang xác thực, logging và phục hồi

Một mạng truy vết chỉ tập trung vào API chính có thể bỏ sót đường khôi phục tài khoản, hệ thống log hoặc quá trình phục hồi. Các rủi ro trong ví dụ cần thêm những yêu cầu sau.

### 7.1. Xác thực tài khoản phê duyệt

**SEC-REQ-04 — Hoàn tất xác thực bổ sung trước khi cấp phiên nghiệp vụ**

> Tài khoản có quyền phê duyệt phải hoàn tất bước xác thực bổ sung đã đăng ký khi bắt đầu phiên mới. Trạng thái đang chờ bước bổ sung không được dùng để phê duyệt đơn hàng.

Liên kết tới RISK-02 vì yêu cầu làm giảm khả năng chỉ có mật khẩu đã đủ để thực hiện nghiệp vụ nhạy cảm. Nó không loại bỏ mọi hình thức chiếm tài khoản hoặc đánh cắp phiên.

**TEST-09** cần thử luồng hoàn tất đúng, thiếu bước bổ sung, bằng chứng sai, bằng chứng hết hạn và lỗi thành phần xác thực. Cần kiểm tra việc gọi trực tiếp API bằng trạng thái chưa hoàn tất. Đường khôi phục tài khoản phải có yêu cầu và bằng chứng tương ứng nếu nằm trong phạm vi.

### 7.2. Thu hồi quyền và trạng thái cũ

**SEC-REQ-05 — Thu hồi quyền có hiệu lực trong thời hạn**

> Thay đổi thu hồi quyền phê duyệt phải có hiệu lực tại mọi điểm quyết định quyền trong tối đa 60 giây từ khi thao tác thu hồi được ghi nhận thành công. Yêu cầu phê duyệt bắt đầu sau mốc đó phải bị từ chối nếu quyền chưa được cấp lại, kể cả khi dùng phiên cũ.

Trong ví dụ này, khi không xác định được quyền do mất kết nối, thao tác nhạy cảm phải bị từ chối. Chính sách cho yêu cầu đã bắt đầu trước khi thu hồi cần được đặc tả riêng nếu phải hủy tác động đang chạy.

**TEST-10** liên kết tới RISK-03. Phép thử giữ phiên cũ, thu hồi quyền rồi gửi yêu cầu tới nhiều instance và các đường quyết định quyền liên quan. Bằng chứng cần có thời điểm thu hồi, thời điểm gửi, kết quả và cách kiểm soát sai lệch đồng hồ. Kiểm tra một instance không đủ đại diện cho mọi cache.

### 7.3. Dấu vết kiểm toán

**SEC-REQ-06 — Ghi dấu vết bền vững cho thao tác quan trọng**

> Thay đổi quyền và kết quả phê duyệt phải tạo sự kiện kiểm toán có thời điểm, chủ thể, tenant, thao tác, tài nguyên, kết quả, mã lý do và mã tương quan. Với thao tác thay đổi quyền hoặc phê duyệt thành công, hệ thống chỉ xác nhận thành công khi dấu vết tương ứng đã được lưu bền vững theo thiết kế nhất quán đã chọn.

Yêu cầu này phục vụ RISK-04. Thiết kế phải làm rõ mối liên hệ giữa thay đổi nghiệp vụ và dấu vết: không để nghiệp vụ thành công nhưng mất sự kiện khi tiến trình dừng.

**TEST-11** cần bao phủ thao tác thành công, bị từ chối, lỗi nơi nhận sự kiện, dừng tiến trình ở điểm nhạy cảm và gửi lại sự kiện. Nếu chấp nhận sự kiện trùng, phải có quy tắc nhận diện trùng. Bằng chứng không chỉ là ảnh màn hình có một dòng log.

### 7.4. Dữ liệu bị cấm trong log

**SEC-REQ-07 — Không đưa bí mật và nội dung đơn hàng vào log**

> Log và sự kiện của luồng đăng nhập, quản lý quyền và xử lý đơn hàng không được chứa mật khẩu, mã xác thực dùng một lần, token truy cập, token làm mới hoặc toàn bộ nội dung đơn hàng. Quy tắc áp dụng cho đường thành công, bị từ chối, xử lý ngoại lệ và thử lại.

Liên kết tới RISK-05. Cần định nghĩa riêng những trường nghiệp vụ tối thiểu được phép ghi; “không ghi toàn bộ” không có nghĩa mọi trường đơn lẻ đều được phép.

**TEST-12** dùng dữ liệu giả có dấu nhận diện, đi qua các nhánh liên quan rồi kiểm tra log ứng dụng, middleware, proxy và hệ thống thu lỗi thuộc phạm vi. Không dùng bí mật thật để tạo bằng chứng. Nếu một kho log chưa được kiểm tra, báo cáo phải giữ rõ khoảng trống đó.

### 7.5. Phục hồi và điều kiện mở lại nghiệp vụ

**SEC-REQ-08 — Phục hồi được dữ liệu và cấu hình cần thiết**

> Quy trình phục hồi phải khôi phục đơn hàng, thành viên, chính sách quyền và các cấu hình cần thiết từ nguồn sao lưu được chọn; xác minh tính nhất quán và khả năng truy cập các khóa cần dùng trước khi mở lại nghiệp vụ.

**SEC-REQ-09 — Mục tiêu thời gian và điểm dữ liệu phục hồi**

> Trong kịch bản mất kho dữ liệu chính và với quy mô đã mô tả trong kế hoạch diễn tập, dịch vụ phải phục hồi mức phục vụ đã xác định trong tối đa 60 phút từ lúc gián đoạn. Khoảng cách thời gian từ điểm dữ liệu phục hồi được tới thời điểm gián đoạn không được vượt quá 15 phút.

Ở đây, **RTO** là mục tiêu thời gian phục hồi; **RPO** là mục tiêu mức mất dữ liệu được diễn đạt theo thời gian. Hai giá trị là giả định minh họa và phải được chọn theo nghiệp vụ.

**SEC-REQ-10 — Không mở lại quyền đã bị thu hồi**

> Trước khi mở chức năng nhạy cảm sau phục hồi, hệ thống phải đối soát và áp dụng các thay đổi thu hồi quyền sau điểm sao lưu từ nguồn thay đổi quyền đáng tin cậy đã được thiết kế. Khi chưa có trạng thái quyền đáng tin cậy, chức năng nhạy cảm phải tiếp tục bị chặn.

SEC-REQ-10 làm lộ một phụ thuộc quan trọng: phải có nguồn thay đổi quyền phù hợp với kịch bản sự cố, hoặc một phương án xác lập lại quyền. Nếu thiết kế không cung cấp nguồn đó, yêu cầu chưa khả thi; không được coi bước đối soát là đã tồn tại chỉ vì tài liệu có nhắc tới.

**TEST-13** phục hồi thực tế, đối chiếu dữ liệu và đo mốc thời gian cho SEC-REQ-08/09. **TEST-14** tạo thay đổi thu hồi quyền sau điểm sao lưu rồi kiểm tra quyền sau phục hồi cho SEC-REQ-10. Các kiểm thử này hỗ trợ RISK-06; TEST-14 còn liên quan tới RISK-03 trong bối cảnh phục hồi.

## 8. Tạo ma trận truy vết có ích

**Ma trận truy vết yêu cầu** là một cách trình bày mạng quan hệ dưới dạng bảng. Không bắt buộc dùng một công cụ cụ thể. Có thể quản lý bằng hệ thống công việc, kho tài liệu hoặc dữ liệu có cấu trúc, miễn là mã và liên kết được duy trì nhất quán.

### 8.1. Ma trận kế hoạch kiểm chứng

| Rủi ro | Yêu cầu | Điểm thực thi hoặc thiết kế | Kiểm chứng dự kiến |
| --- | --- | --- | --- |
| RISK-01 | SEC-REQ-01 | Dịch vụ đơn hàng, truy vấn giới hạn tenant, xử lý lỗi quyền | TEST-01, TEST-02, TEST-03, TEST-04 |
| RISK-01 | SEC-REQ-02 | API xuất, worker, nơi lưu tệp, điểm tải | TEST-05, TEST-06, TEST-07 |
| Chất lượng đi kèm kiểm soát RISK-01 | SEC-REQ-03 | Bước đánh giá quyền và phép đo độ trễ | TEST-08 |
| RISK-02 | SEC-REQ-04 | Dịch vụ danh tính và cổng vào nghiệp vụ | TEST-09 |
| RISK-03 | SEC-REQ-05 | Nơi lưu quyền, phiên, cache, mọi điểm quyết định quyền | TEST-10 |
| RISK-04 | SEC-REQ-06 | Ghi nhận nghiệp vụ, lưu sự kiện, gửi và thu gom | TEST-11 |
| RISK-05 | SEC-REQ-07 | Ứng dụng và các thành phần tạo log liên quan | TEST-12 |
| RISK-06 | SEC-REQ-08, SEC-REQ-09 | Sao lưu, phục hồi, xác minh dữ liệu và cấu hình | TEST-13 |
| RISK-06, RISK-03 | SEC-REQ-10 | Đối soát thay đổi quyền và điều kiện mở lại nghiệp vụ | TEST-14 |

Đây là **kế hoạch**, chưa phải kết quả kiểm chứng. SEC-REQ-03 đặt chất lượng cho kiểm soát; đạt độ trễ không tự giảm được rủi ro đọc dữ liệu khác tenant nếu quyết định quyền vẫn sai.

### 8.2. Tách kết quả chạy khỏi định nghĩa kiểm thử

Giả sử có một hồ sơ minh họa:

| Ca kiểm thử | Lần chạy | Kết quả | Bằng chứng | Hệ quả |
| --- | --- | --- | --- | --- |
| TEST-02 | RUN-101 | PASS trong phạm vi đã thử | EVID-101: yêu cầu và phản hồi đã lọc bí mật | Có bằng chứng cho các tiêu chí chéo tenant của SEC-REQ-01 |
| TEST-06 | RUN-102 | FAIL | EVID-102: tài khoản A tải được bản xuất B | SEC-REQ-02 chưa đáp ứng; RISK-01 còn đường khai thác đã xác nhận |
| TEST-13 | Chưa chạy | NOT_RUN | Chưa có | Chưa đủ bằng chứng cho khả năng phục hồi và mục tiêu thời gian |

Các mã, kết quả và bằng chứng trong bảng là **hồ sơ giả định để học cách đọc ma trận**, không phải kết quả kiểm thử của một sản phẩm đang chạy.

Một lần chạy tối thiểu nên giữ:

~~~text
Lần chạy: RUN-101
Ca kiểm thử và phiên bản: TEST-02, revision 3
Yêu cầu và phiên bản: SEC-REQ-01, revision 2
Bản dựng được kiểm thử: một định danh bản dựng xác định được
Môi trường: cấu hình dịch vụ, phụ thuộc, cờ tính năng và dữ liệu nền
Thời điểm: bắt đầu, kết thúc và múi giờ
Kết quả: PASS / FAIL / BLOCKED / NOT_RUN theo quy ước
Quan sát thực tế: những kết quả đã thu được
Bằng chứng: vị trí lưu, quyền truy cập và thời hạn lưu phù hợp
Vấn đề liên quan: mã lỗi hoặc hành động cần xử lý, nếu có
~~~

Kết quả PASS của revision cũ không tự động áp dụng cho revision mới. Nếu thay đổi không ảnh hưởng đến phép kiểm chứng, phải có căn cứ đánh giá tác động để tái sử dụng bằng chứng.

### 8.3. Quản lý bằng chứng như dữ liệu cần bảo vệ

Bằng chứng có thể chứa token, dữ liệu khách hàng, thông tin tài khoản hoặc cấu hình nội bộ. Vì vậy cần:

- Dùng dữ liệu giả hoặc dữ liệu đã được xử lý phù hợp.
- Lọc bí mật trước khi chia sẻ báo cáo.
- Giới hạn quyền đọc và thời gian lưu.
- Giữ đủ thông tin để liên kết tới lần chạy, tránh tệp rời không biết xuất xứ.
- Bảo vệ tính toàn vẹn khi bằng chứng được dùng để ra quyết định.

Không nên sửa nội dung bằng chứng thất bại để biến kết quả thành đạt. Khi dữ liệu thu thập sai hoặc cần chạy lại, lưu lần chạy mới và giải thích quan hệ với lần trước.

## 9. Đánh giá độ bao phủ mà không hiểu sai số liệu

Truy vết giúp nhận diện khoảng trống, nhưng một tỷ lệ cao không tự chứng minh hệ thống an toàn.

### 9.1. Bao phủ về kế hoạch

Có thể tính:

~~~text
Tỷ lệ yêu cầu có kế hoạch kiểm chứng
= Số yêu cầu trong phạm vi có phương pháp kiểm chứng phù hợp
  / Tổng số yêu cầu đang có hiệu lực trong phạm vi
~~~

“Có phương pháp phù hợp” phải xét nội dung, không chỉ có một đường liên kết. Một kiểm thử đăng nhập thành công không đủ làm kế hoạch kiểm chứng cho yêu cầu thu hồi quyền trong 60 giây.

Chỉ số này trả lời “đã biết sẽ kiểm chứng thế nào chưa”, không trả lời “đã đáp ứng chưa”.

### 9.2. Bao phủ bằng bằng chứng đáp ứng

Một chỉ số khác:

~~~text
Tỷ lệ yêu cầu có bằng chứng đáp ứng
= Số yêu cầu có đầy đủ bằng chứng đạt cho các tiêu chí bắt buộc,
  phù hợp với phiên bản và cấu hình đang xét
  / Tổng số yêu cầu đang có hiệu lực trong phạm vi
~~~

Một yêu cầu cần ba phép kiểm chứng nhưng mới đạt hai chưa được tính là đã có đầy đủ bằng chứng. Các trạng thái chưa chạy, bị chặn, thất bại và bằng chứng không còn áp dụng phải được báo cáo rõ, không âm thầm bỏ khỏi mẫu số.

Ngoại lệ được chấp nhận cũng cần hiển thị riêng. Nó là quyết định về rủi ro, không phải bằng chứng yêu cầu đã đạt.

### 9.3. Bao phủ rủi ro và bao phủ đường đi

Với nhóm rủi ro đã chọn phương án giảm, có thể theo dõi tỷ lệ rủi ro có yêu cầu xử lý được giao trách nhiệm. Những rủi ro được tránh hoặc chấp nhận cần theo dõi theo quyết định tương ứng; không nên ép chúng vào cùng mẫu số rồi kết luận bị bỏ sót.

Tuy vậy, ngay cả khi mọi rủi ro đã có yêu cầu liên kết, vẫn phải hỏi:

- Danh sách rủi ro có bỏ sót tác nhân, tài sản hoặc đường truy cập không?
- Yêu cầu có thực sự giảm hậu quả đang xét không?
- Mọi điểm thực thi liên quan đã được đưa vào thiết kế chưa?
- Kiểm thử có bao phủ điều kiện lỗi, quyền cũ và đường đi bất đồng bộ không?
- Những giả định về phụ thuộc có còn đúng không?

Trong RISK-01, TEST-02 đạt ở API đọc chi tiết chưa đại diện cho API danh sách, tìm kiếm, bản xuất và đường tải trực tiếp. Cần thống kê các đường đọc trong phạm vi để đánh giá độ bao phủ, thay vì chỉ đếm số ca kiểm thử.

Không so sánh mức an toàn của hai hệ thống chỉ bằng số lượng kiểm thử. Một trăm kiểm thử lặp lại đường hợp lệ có thể bỏ sót một đường tải tệp không kiểm tra quyền.

## 10. Dùng truy vết để phân tích tác động thay đổi

Giả sử nhóm chuyển từ tải bản xuất qua dịch vụ sang tải bằng liên kết trực tiếp tại kho lưu trữ.

Đây có thể là thay đổi hiệu năng hoặc vận hành, nhưng nó tác động tới SEC-REQ-02: yêu cầu kiểm tra danh tính và quyền tại thời điểm tải.

### 10.1. Đi theo mạng liên kết

1. **Xác định thành phần đổi:** điểm tải bản xuất và cơ chế cấp liên kết.
2. **Tìm yêu cầu liên quan:** SEC-REQ-02 và các tiêu chí về quyền tại lúc tải, tenant, chủ thể được cấp, thời hạn.
3. **Quay về rủi ro:** RISK-01; xem thêm nguy cơ lộ liên kết qua log nếu có.
4. **Đánh giá thiết kế:** người nắm liên kết có tải được không; liên kết có gắn với chủ thể không; thu hồi quyền ảnh hưởng thế nào.
5. **Đánh giá kiểm thử:** TEST-05, TEST-06, TEST-07 phải còn đi qua đường tải thực tế.
6. **Đánh giá bằng chứng cũ:** kết quả của đường tải qua dịch vụ có thể không còn phù hợp.
7. **Chốt hành động:** sửa thiết kế, bổ sung yêu cầu hoặc xử lý ngoại lệ qua chủ sở hữu có thẩm quyền.
8. **Chạy lại và lưu bằng chứng:** kết quả mới phải gắn với bản dựng và cấu hình mới.

Chỉ chạy lại API tạo bản xuất sẽ bỏ sót chính điểm đã thay đổi.

### 10.2. Khi nào bằng chứng cần xem lại?

| Thay đổi | Chuỗi liên kết nên kiểm tra |
| --- | --- |
| Đổi nhà cung cấp danh tính hoặc luồng khôi phục tài khoản | RISK-02 → SEC-REQ-04 → TEST-09 |
| Thêm cache quyền hoặc đổi thời gian sống cache | RISK-03 → SEC-REQ-05 → TEST-10; xem cả SEC-REQ-01/02 |
| Thêm endpoint đọc dữ liệu hoặc tìm kiếm | RISK-01 → SEC-REQ-01 và phạm vi các đường đọc |
| Chuyển thư viện log hoặc thêm hệ thống thu lỗi | RISK-04/05 → SEC-REQ-06/07 → TEST-11/12 |
| Đổi cách sao lưu, khóa hoặc nơi phục hồi | RISK-06 → SEC-REQ-08/09/10 → TEST-13/14 |
| Chỉ đổi tên hiển thị không ảnh hưởng hành vi bảo vệ | Ghi căn cứ đánh giá tác động; có thể giữ bằng chứng còn phù hợp |

Không phải thay đổi nào cũng buộc chạy lại mọi kiểm thử bảo mật. Cần chọn theo tác động có căn cứ, đồng thời tránh tái sử dụng bằng chứng khi đường thực thi hoặc giả định đã đổi.

## 11. Những dấu hiệu chuỗi truy vết bị đứt

| Dấu hiệu | Điều cần xem xét |
| --- | --- |
| Rủi ro chọn phương án giảm nhưng không có yêu cầu | Chưa chuyển quyết định xử lý thành nghĩa vụ thực hiện |
| Yêu cầu không có nguồn gốc | Có thể thiếu liên kết tới rủi ro, nghĩa vụ tổ chức hoặc nhu cầu nghiệp vụ |
| Yêu cầu chỉ ghi tên công nghệ | Chưa có hành vi hoặc thuộc tính để nghiệm thu |
| Thiết kế không có điểm thực thi rõ ràng | Có thể tồn tại đường truy cập bỏ qua kiểm soát |
| Ca kiểm thử chỉ dẫn tới tiêu đề yêu cầu | Chưa rõ tiêu chí nào được kiểm chứng |
| Ca kiểm thử luôn từ chối mọi yêu cầu | Có thể môi trường hỏng; thiếu đường hợp lệ làm đối chứng |
| Ma trận có nhiều PASS nhưng không có bản dựng | Không biết bằng chứng áp dụng cho phiên bản nào |
| Lỗi đã sửa nhưng vẫn trỏ tới lần chạy thất bại | Cần bằng chứng kiểm thử lại và liên kết tới sửa đổi |
| Có ngoại lệ nhưng không có chủ sở hữu hoặc thời hạn | Quyết định rủi ro không đủ căn cứ để quản lý |
| Rủi ro được ghi “đã đóng” chỉ vì có một ca kiểm thử đạt | Đã bỏ qua phạm vi còn lại, giả định và rủi ro còn lại |

Yêu cầu không gắn với một rủi ro trong mô hình đe dọa không nhất thiết là thừa. Nó có thể xuất phát từ chính sách của tổ chức, hợp đồng hoặc nghĩa vụ khác. Khi đó cần ghi đúng nguồn và phạm vi, không bịa một rủi ro chỉ để làm đầy ma trận.

Tương tự, một kiểm thử kỹ thuật có thể hỗ trợ nhiều yêu cầu hoặc kiểm tra một giả định kiến trúc. Cần ghi rõ vai trò thay vì ép mọi kiểm thử vào một quan hệ giảm rủi ro trực tiếp.

## 12. Duy trì truy vết trong công việc hằng ngày

Một cách làm thực dụng là cập nhật liên kết tại nơi quyết định được tạo ra:

- **Khi phân tích rủi ro:** tạo mã, ghi tài sản, kịch bản, hậu quả, chủ sở hữu và quyết định xử lý.
- **Khi đặc tả:** viết yêu cầu có tiêu chí chấp nhận, gắn nguồn và rủi ro liên quan.
- **Khi thiết kế:** giao trách nhiệm cho thành phần, ghi giả định và điểm thực thi.
- **Khi triển khai:** liên kết hạng mục thay đổi với yêu cầu và quyết định thiết kế tương ứng.
- **Khi kiểm chứng:** giữ định nghĩa ca kiểm thử riêng với lần chạy và bằng chứng.
- **Khi sửa lỗi:** liên kết phát hiện, thay đổi khắc phục và kết quả chạy lại.
- **Khi chuẩn bị phát hành:** xem khoảng trống, kết quả thất bại, ngoại lệ và rủi ro còn lại.
- **Khi vận hành hoặc thay đổi:** cập nhật ngữ cảnh, hiệu lực bằng chứng và nhu cầu kiểm chứng lại.

Người phân tích hoặc chủ sở hữu yêu cầu làm rõ nghĩa vụ; người thiết kế và triển khai giải thích cơ chế; người kiểm chứng thu thập bằng chứng; chủ sở hữu rủi ro quyết định phần rủi ro còn lại theo thẩm quyền. Một người có thể kiêm nhiều vai trò, nhưng trách nhiệm không nên biến mất.

Trước một quyết định phát hành, mạng truy vết phải cho phép trả lời bằng thông tin cụ thể: rủi ro nào đang được xử lý, yêu cầu nào đã đáp ứng, bằng chứng nào còn áp dụng, khoảng trống nào còn tồn tại và ai chịu trách nhiệm về quyết định tiếp theo.
