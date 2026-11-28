# Timeout — Đặc tả giới hạn thời gian để bảo vệ tính sẵn sàng

## 1. Timeout là một yêu cầu bảo mật như thế nào?

**Timeout** là giới hạn thời gian chờ hoặc thực hiện một hoạt động trước khi hệ thống chuyển sang hành vi đã được xác định. Hoạt động đó có thể là nhận dữ liệu, lấy kết nối từ pool, gọi dịch vụ định danh, thực hiện truy vấn hoặc chờ hoàn thành một giao dịch.

Trong thiết kế yêu cầu bảo mật, timeout giúp giới hạn khoảng thời gian một yêu cầu chiếm giữ tài nguyên. Nếu không có giới hạn phù hợp, một phụ thuộc bị treo hoặc một nhóm yêu cầu chậm có thể giữ hết luồng xử lý, kết nối, bộ nhớ và chỗ trong hàng đợi. Người dùng hợp lệ sau đó không còn sử dụng được dịch vụ.

Timeout không tự bảo đảm hoạt động từ xa đã dừng, giao dịch đã rollback hay hệ thống sẽ chống được mọi kiểu từ chối dịch vụ. Một yêu cầu đầy đủ phải mô tả cả giới hạn thời gian, phạm vi áp dụng, hành vi khi hết hạn, việc xử lý tài nguyên và kết quả nghiệp vụ.

Trong module chuyển mục tiêu an toàn thông tin thành yêu cầu kiểm chứng được, câu hỏi chính là:

> Đối với hoạt động nào, hệ thống được chờ tối đa bao lâu, tính từ đâu, sau đó phải làm gì, giữ những kiểm soát bảo mật nào và cung cấp bằng chứng gì?

Sau bài học, người đọc có thể:

- Phân biệt timeout của từng giai đoạn với deadline của cả hành trình.
- Phân bổ ngân sách thời gian qua nhiều phụ thuộc mà không kéo dài chờ ngoài dự kiến.
- Đặc tả xử lý timeout cho xác thực, phân quyền, dữ liệu và logging.
- Viết tiêu chí kiểm thử cho tác vụ bị treo, hủy không thành công và giao dịch có kết quả chưa rõ.

Các giá trị số trong bài là ví dụ cho một hệ thống giả định. Chúng cần được điều chỉnh theo tác động nghiệp vụ, độ trễ thực tế, khả năng xử lý và điều kiện sử dụng của người dùng.

## 2. Phân biệt timeout, deadline và cancellation

| Khái niệm | Ý nghĩa | Điều không được suy ra |
|---|---|---|
| Timeout tương đối | Được chờ tối đa một khoảng thời gian kể từ mốc bắt đầu của một thao tác. | Mỗi tầng đặt cùng một timeout không làm tổng thời gian của cả hành trình bằng timeout đó. |
| Deadline | Mốc thời gian mà sau đó kết quả không còn đáp ứng giới hạn đã đặt cho một hành trình. | Truyền một con số thời gian giữa hai máy không tự giải quyết sai lệch đồng hồ. |
| Idle timeout | Giới hạn khoảng thời gian không có tiến triển hoặc không nhận thêm dữ liệu, theo định nghĩa của thành phần. | Gửi từng byte nhỏ trước khi hết hạn có thể khiến tổng thời gian kéo dài nếu thiếu giới hạn tổng. |
| Cancellation | Yêu cầu dừng một hoạt động không còn cần thiết hoặc đã hết thời gian. | Bên nhận có thể chưa xử lý việc hủy; tác vụ từ xa vẫn có thể tiếp tục. |
| Budget — ngân sách thời gian | Phần thời gian còn được phép sử dụng cho một giai đoạn hoặc hành trình. | Không thể phân bổ lại toàn bộ ngân sách ban đầu cho mỗi lần retry. |

Ví dụ, dịch vụ A có deadline một giây. Sau khi A xử lý hết 400 ms, lời gọi tới B chỉ còn dưới 600 ms, vì A vẫn cần thời gian chuẩn bị và gửi phản hồi. Nếu A cấp cho B một timeout mới một giây, giới hạn của hành trình có thể bị vượt.

Cần phân biệt ba sự kiện:

1. Bên gọi ngừng chờ.
2. Tác vụ được yêu cầu hủy.
3. Tác vụ thực sự dừng và tài nguyên được thu hồi hoặc đưa về trạng thái an toàn.

Chúng có thể xảy ra ở các thời điểm khác nhau. Yêu cầu chỉ ràng buộc sự kiện thứ nhất vẫn có thể để lại rất nhiều công việc chạy ngầm, làm sự cố tiếp tục lan rộng.

## 3. Từ mối đe dọa tới yêu cầu timeout

Giả sử cổng đặt hàng có đường xử lý: cổng vào → dịch vụ đơn hàng → kiểm tra quyền → cơ sở dữ liệu. Dịch vụ cũng nhận kết quả từ một số phụ thuộc bên ngoài.

| Rủi ro hoặc tình huống lỗi | Tác động cần hạn chế | Yêu cầu cần hình thành |
|---|---|---|
| Client gửi header hoặc body rất chậm | Giữ kết nối và trạng thái trước khi ứng dụng xử lý được yêu cầu. | Giới hạn nhận dữ liệu, kích thước, mức đồng thời và cách kết thúc kết nối. |
| Dịch vụ định danh không phản hồi | Luồng xử lý chờ mãi hoặc hệ thống bỏ kiểm tra quyền để phục vụ tiếp. | Giới hạn chờ và quy định từ chối an toàn khi không xác minh được điều kiện bắt buộc. |
| Pool kết nối cơ sở dữ liệu đã đầy | Yêu cầu mới xếp hàng kéo dài và chiếm thêm bộ nhớ. | Giới hạn thời gian chờ pool, độ dài hàng đợi và hành vi từ chối. |
| Truy vấn bị khóa hoặc rất tốn tài nguyên | Hết thời gian ở phía ứng dụng nhưng truy vấn vẫn chạy. | Phối hợp timeout truy vấn, giới hạn giao dịch và xử lý hủy không hoàn tất. |
| Nhiều tầng cùng retry | Lưu lượng tăng mạnh đúng khi phụ thuộc đang chậm. | Giới hạn số lần thử, tổng thời gian và điều kiện được phép retry. |
| Ghi dữ liệu thành công nhưng phản hồi bị mất | Client gửi lại, có thể phát sinh giao dịch trùng. | Đặc tả trạng thái chưa rõ, idempotency và cách tra cứu kết quả. |
| Hệ thống ghi log bị treo | Một phụ thuộc quan sát làm dừng toàn bộ nghiệp vụ. | Giới hạn chờ và chính sách riêng cho audit bắt buộc với log chẩn đoán. |

Chuỗi truy vết cho một yêu cầu có thể viết như sau:

> Tài sản: khả năng tạo đơn → rủi ro: cạn pool do phụ thuộc chậm → yêu cầu: chờ pool hữu hạn và giữ deadline chung → thiết kế: hàng đợi hữu hạn, timeout và cancellation → kiểm thử: làm đầy pool, đo thời gian chờ và tài nguyên còn bị giữ.

Đặt timeout là một phần của kiểm soát tài nguyên. Cần kết hợp với giới hạn đồng thời, kích thước yêu cầu, hạn mức theo chủ thể và khả năng từ chối tải. Timeout rất dài vẫn cho phép một lượng lớn tác vụ chiếm chỗ; timeout rất ngắn có thể loại nhiều người dùng hợp lệ.

## 4. Liệt kê đúng các đồng hồ cần kiểm soát

Một cấu hình mang tên “request timeout” không đủ chứng minh toàn bộ hành trình đã có giới hạn. Phải xác định thành phần nào đo thời gian và giới hạn đó bao gồm những giai đoạn nào.

| Giai đoạn | Điều cần đặc tả |
|---|---|
| Nhận header | Mốc bắt đầu, thời gian tổng để nhận đủ header, giới hạn kích thước và hành vi khi không hoàn tất. |
| Nhận body | Thời gian tổng, khoảng bất hoạt nếu có, kích thước tối đa và xử lý client gửi rất chậm. |
| Chờ hàng đợi xử lý | Thời gian được xếp hàng, độ dài hàng đợi và cách tính vào deadline. |
| Chờ pool kết nối | Thời gian chờ kết nối rảnh; không nhầm với thời gian mở kết nối mới. |
| Phân giải tên, kết nối, bắt tay bảo mật | Những bước nào nằm trong cùng một giới hạn; hành vi của thư viện và môi trường phải được kiểm chứng. |
| Gửi yêu cầu tới phụ thuộc | Giới hạn gửi khi bên nhận đọc chậm hoặc không đọc. |
| Chờ phản hồi | Giới hạn đến dữ liệu đầu tiên, khoảng chờ giữa các lần nhận và thời gian tổng nếu cần. |
| Truy vấn và giao dịch dữ liệu | Thời gian thực thi, chờ khóa, thời gian sống giao dịch và cơ chế hủy. |
| Xử lý toàn hành trình | Deadline chung bao trùm các giai đoạn đã công bố, kể cả lần thử lại. |
| Thu hồi sau timeout | Thời gian yêu cầu hủy, dọn trạng thái và phát hiện công việc vẫn còn chạy. |

Một timeout đọc có thể chỉ giới hạn thời gian không nhận được dữ liệu giữa hai lần đọc. Nó không nhất thiết giới hạn tổng thời gian nhận một phản hồi. Ngữ nghĩa cụ thể phụ thuộc thành phần triển khai, vì vậy yêu cầu nên mô tả hành vi cần đạt; thiết kế và kiểm thử phải chứng minh cấu hình được chọn thực sự đáp ứng hành vi ấy.

Với luồng dài như tải tệp hoặc stream, một deadline ngắn cho toàn bộ nội dung có thể không phù hợp. Cần đặc tả theo loại hoạt động: thời gian thiết lập, khoảng bất hoạt tối đa, giới hạn tài nguyên và cơ chế kết thúc. Không áp một giá trị chung cho cả giao dịch ngắn lẫn luồng dài mà thiếu phân tích.

## 5. Phân bổ deadline cho một hành trình

### 5.1. Xác định ranh giới trước khi cộng các con số

Trong ví dụ, deadline xử lý tạo đơn là 1.500 ms, bắt đầu khi cổng vào đã nhận đủ yêu cầu trong giới hạn kích thước và kết thúc khi cổng vào phát xong phản hồi. Thời gian nhận header, body trước đó có giới hạn riêng.

Ranh giới này chưa bao gồm toàn bộ đường truyền tới thiết bị người dùng. Nếu mục tiêu là thời gian người dùng quan sát được, cần phép đo đầu cuối tương ứng, đồng thời tính cả thời gian gửi yêu cầu qua mạng.

Một phân bổ minh họa cho các bước xử lý tuần tự:

| Phần việc | Ngân sách tối đa minh họa |
|---|---:|
| Tiếp nhận vào xử lý và kiểm tra đầu vào | 100 ms |
| Kiểm tra quyền qua phụ thuộc | 200 ms |
| Chờ pool cơ sở dữ liệu | 100 ms |
| Thực hiện thao tác dữ liệu | 750 ms |
| Chuẩn bị và tuần tự hóa phản hồi | 100 ms |
| Phát phản hồi tại cổng vào | 100 ms |
| Dự phòng điều phối và chi phí chưa phân bổ | 150 ms |
| **Tổng** | **1.500 ms** |

Đây là ngân sách thiết kế, không phải kết quả benchmark. Mức phân bổ phải được kiểm chứng dưới tải và khi có lỗi. Với các nhánh chạy song song, tổng thời gian phụ thuộc đường xử lý quyết định thời điểm hoàn thành, không đơn giản là cộng thời gian mọi nhánh.

### 5.2. Giới hạn mỗi bước bằng thời gian còn lại

Trước khi bắt đầu một thao tác, cần tính phần thời gian còn lại sau khi chừa phần cần thiết để kết thúc hành trình.

~~~text
thời_gian_còn_lại = deadline_cục_bộ - thời_điểm_hiện_tại

ngân_sách_thao_tác
  = min(giới_hạn_của_thao_tác,
        thời_gian_còn_lại - phần_dành_cho_kết_thúc)

nếu ngân_sách_thao_tác không đủ để bắt đầu hữu ích:
  không khởi chạy thêm công việc
  kết thúc theo hợp đồng lỗi
~~~

Không cấp giá trị âm hoặc giá trị bằng không vào cấu hình mà chưa biết ngữ nghĩa. Một thành phần có thể hiểu số không là “không chờ”, trong khi thành phần khác hiểu là “không giới hạn”. Việc chuyển đổi và làm tròn đơn vị cũng phải được xác định, nhất là khi phần thời gian còn lại rất nhỏ.

Trong một tiến trình, phép đo khoảng thời gian nên dùng đồng hồ đơn điệu để tránh ảnh hưởng của việc chỉnh đồng hồ lịch. Khi truyền qua mạng, cần có quy ước về thời gian còn lại hoặc deadline, cách xử lý thời gian truyền và sai lệch đồng hồ. Bên nhận phải áp giới hạn cục bộ và không cho giá trị do client gửi kéo dài vượt chính sách của dịch vụ.

### 5.3. Retry phải dùng chung ngân sách

Một lần retry tiêu tốn cả thời gian chờ trước khi thử lại, thời gian lấy tài nguyên và thời gian thực thi. Chỉ thử lại khi còn đủ ngân sách và loại thao tác cho phép.

Ví dụ, sau lần gọi đầu và khoảng chờ đã dùng 600 ms của ngân sách 800 ms dành cho một nhánh, lần thử tiếp theo không được nhận lại 800 ms. Nếu 200 ms còn lại không đủ cho một lần thử hữu ích và việc kết thúc an toàn, phải dừng retry.

Tác vụ ghi có kết quả chưa rõ không được retry tùy tiện. Cần xem xét tính idempotent và cơ chế xác định kết quả, được trình bày ở mục 8.

## 6. Hành vi bắt buộc khi hết thời gian

Một yêu cầu timeout đầy đủ phải quy định các hành vi quan sát được:

1. **Ngừng chờ theo hợp đồng:** trả kết quả phù hợp hoặc kết thúc luồng đã thỏa thuận; không coi một phản hồi lỗi nhanh là giao dịch nghiệp vụ thành công.
2. **Không bắt đầu công việc mới đã hết ích lợi:** không lấy thêm kết nối hoặc khởi chạy thêm lần thử sau khi deadline của hành trình đã hết.
3. **Yêu cầu hủy tác vụ đang chạy:** truyền tín hiệu hủy tới những thành phần hỗ trợ và ghi nhận trạng thái thực tế.
4. **Xử lý tài nguyên an toàn:** dọn bộ đệm, hàng đợi và trạng thái cục bộ; không trả kết nối còn giao dịch không rõ về pool để tái sử dụng.
5. **Giữ các kiểm soát bảo mật:** không bỏ xác thực, cấp quyền mặc định hoặc dùng dữ liệu của tenant khác để phản hồi cho nhanh.
6. **Ghi nhận kết quả:** phân biệt bên gọi hết thời gian, đã yêu cầu hủy, đã xác nhận dừng và kết quả nghiệp vụ chưa rõ.
7. **Cho client cách xử lý tiếp:** chỉ rõ khi nào được thử lại, dùng định danh nào và tra cứu kết quả ở đâu nếu cần.

Việc client đóng kết nối cũng có thể là lý do ngừng công việc không còn cần thiết, nhưng không tự chứng minh tác vụ ghi đã rollback. Công việc đã được chấp nhận xử lý bất đồng bộ có thể có vòng đời riêng; cần một hợp đồng riêng về thời gian hoàn thành, quyền tra cứu và hủy.

Nếu phụ thuộc không hỗ trợ hủy đáng tin cậy, phải bù bằng giới hạn số công việc còn chạy, thời gian sống ở phía phụ thuộc nếu có, cô lập tài nguyên và khả năng phát hiện tác vụ mồ côi. Không được tuyên bố “đã hủy” chỉ vì luồng bên gọi không còn chờ.

## 7. Timeout không được làm yếu xác thực, phân quyền và audit

Khi một phụ thuộc bảo mật bị chậm, có thể xuất hiện đề xuất “cho qua tạm để giữ availability”. Hành vi đó chỉ được dùng nếu đã có chính sách nghiệp vụ và bảo mật cho đúng loại thao tác; một timeout không tự tạo ra ngoại lệ cấp quyền.

Cần đặc tả riêng:

| Phụ thuộc hoặc dữ liệu | Khi timeout cần quyết định gì? | Ràng buộc bảo mật |
|---|---|---|
| Xác thực đăng nhập mới | Trả lỗi tạm thời, có được retry không và trong bao lâu? | Không tạo phiên khi chưa có bằng chứng xác thực bắt buộc. |
| Kiểm tra quyền giao dịch | Có nguồn quyết định quyền hợp lệ khác được phép dùng không? | Không chuyển “không xác minh được” thành “được phép”. |
| Phiên hiện hữu | Có thể tiếp tục dùng bằng chứng đã xác minh trong phạm vi nào? | Giữ giới hạn hiệu lực, thu hồi quyền và yêu cầu của thao tác nhạy cảm. |
| Dữ liệu cache | Độ cũ tối đa và điều kiện quyền nào cho phép dùng? | Không lộ dữ liệu giữa tenant; không dùng cache để kéo dài quyền ngoài chính sách. |
| Audit bắt buộc | Có nguồn lưu bền vững dự phòng không; khi nào phải từ chối thao tác? | Không hoàn tất thao tác nếu chính sách yêu cầu bằng chứng audit mà chưa đáp ứng. |
| Log chẩn đoán | Có thể dùng bộ đệm hoặc bỏ bớt theo mức nào? | Giới hạn bộ đệm, cảnh báo mất log và không đưa bí mật vào log. |

Timeout của việc gửi audit không chứng minh audit đã được lưu, cũng không chứng minh nó chưa được lưu. Nếu có cơ chế gửi lại, cần định danh sự kiện và quy tắc xử lý bản trùng. Nếu thao tác nghiệp vụ và audit có quan hệ bắt buộc, phải thiết kế cơ chế bảo đảm mối quan hệ đó, thay vì chỉ tăng timeout.

Các phản hồi lỗi cần hữu ích cho client nhưng không lộ token, mật khẩu, câu truy vấn chứa dữ liệu nhạy cảm hoặc địa chỉ nội bộ. Thông tin chi tiết phục vụ điều tra nằm trong kênh quan sát có kiểm soát truy cập.

## 8. Timeout sau thao tác ghi: kết quả có thể chưa rõ

Xét chuỗi sự kiện:

~~~text
Client                 Dịch vụ                     Cơ sở dữ liệu
  | gửi tạo đơn            |                            |
  |----------------------->| ghi đơn                    |
  |                        |--------------------------->|
  |                        |           commit thành công|
  |                        |<---------------------------|
  |       phản hồi bị mất hoặc về quá muộn               |
  | hết thời gian chờ      |                            |
~~~

Client không nhận được xác nhận, nhưng đơn có thể đã tồn tại. Trong một tình huống khác, dịch vụ cũng có thể hết thời gian chờ cơ sở dữ liệu trước khi biết việc commit có thành công hay không.

Vì vậy, câu “nếu timeout thì giao dịch thất bại và có thể gửi lại” là thiếu an toàn. Đặc tả cần phân biệt:

- **Đã xác nhận thành công:** có bằng chứng nghiệp vụ đạt điều kiện thành công.
- **Đã xác nhận không thực hiện:** có bằng chứng tác vụ không được thực hiện hoặc đã được hoàn tác theo hợp đồng.
- **Chưa rõ kết quả:** chưa đủ bằng chứng để kết luận một trong hai trạng thái trên.

Trạng thái chưa rõ phải có cách giải quyết, chẳng hạn tra cứu theo định danh giao dịch, đối soát hoặc tiếp tục cùng một yêu cầu có khóa idempotency hợp lệ.

Một yêu cầu idempotency đi kèm timeout cần làm rõ:

1. Khóa thuộc phạm vi tenant và loại thao tác nào; ai được quyền dùng và tra cứu.
2. Cùng khóa, cùng nội dung được xử lý như thế nào khi lần đầu còn đang chạy.
3. Cùng khóa nhưng nội dung khác phải bị từ chối theo hợp đồng, không được âm thầm coi là cùng giao dịch.
4. Thời gian giữ bản ghi chống lặp và hành vi sau khi thời gian đó hết.
5. Cách gắn bản ghi chống lặp với kết quả ghi dữ liệu để tránh khoảng hở tạo trùng.
6. Cách xử lý lỗi hoặc timeout ngay khi lưu bản ghi chống lặp.
7. Quy trình giải quyết các giao dịch chưa rõ còn tồn tại quá giới hạn theo dõi.

Ví dụ, hệ thống giả định giữ kết quả chống lặp trong 24 giờ. Client gửi lại cùng khóa và cùng nội dung trong khoảng đó phải nhận trạng thái tương ứng với một giao dịch nghiệp vụ, không tạo thêm một đơn mới. Đây là yêu cầu về hiệu ứng nghiệp vụ trong phạm vi xác định; không nên mô tả nó như một bảo đảm rằng mạng chỉ truyền mỗi thông điệp đúng một lần.

Việc đóng kết nối cơ sở dữ liệu hoặc yêu cầu hủy có thể giúp dừng công việc nhưng không thay thế việc xác định kết quả commit. Thông báo cho người dùng phải phản ánh điều hệ thống thực sự biết.

## 9. Bộ yêu cầu timeout mẫu

Bộ yêu cầu sau dùng cho cổng đặt hàng giả định. Tải nghiệm thu là 200 yêu cầu tạo đơn hợp lệ mỗi giây trong mười phút, với dữ liệu và cấu hình được cố định trong hồ sơ thử. Các lần chèn lỗi phải được nêu riêng; thành công nghiệp vụ và kết thúc chờ đúng hạn được đo bằng hai chỉ số khác nhau.

### SR-TO-001 — Deadline xử lý chung

Mỗi yêu cầu tạo đơn được nhận đủ tại cổng vào phải chịu deadline xử lý 1.500 ms theo ranh giới ở mục 5. Thời gian xếp hàng, lấy kết nối, gọi phụ thuộc, retry và tạo phản hồi đều nằm trong giới hạn này.

Trước mỗi thao tác phụ thuộc, ngân sách phải được giới hạn bởi phần thời gian còn lại và phần dành cho kết thúc. Khi hết ngân sách, hệ thống không khởi chạy thêm thao tác hoặc lần thử lại của cùng yêu cầu.

Bằng chứng phải có thời điểm bắt đầu, deadline, thời điểm bắt đầu và kết thúc từng giai đoạn. Những phản hồi sau deadline được báo cáo là vi phạm, kể cả khi chúng trả lỗi timeout. Phép đo cần có độ phân giải và sai số được công bố, phù hợp với ngưỡng cần kiểm chứng.

### SR-TO-002 — Chờ pool và xử lý tài nguyên còn hoạt động

Thời gian chờ pool cơ sở dữ liệu không vượt 100 ms và luôn chịu deadline chung. Trong cấu hình thử minh họa, pool có tối đa 20 kết nối, hàng đợi chờ có tối đa 100 mục. Yêu cầu vượt giới hạn chờ hoặc giới hạn hàng đợi phải kết thúc theo hợp đồng lỗi; không tạo hàng đợi khác không có giới hạn để chờ tiếp.

Nếu thao tác dữ liệu bị timeout, hệ thống phải gửi yêu cầu hủy khi có hỗ trợ và xác định tình trạng giao dịch trước khi tái sử dụng kết nối. Trong 250 ms sau khi xác định timeout, kết nối phải được xác nhận đủ điều kiện tái sử dụng hoặc bị loại khỏi khả năng tái sử dụng và được theo dõi để xử lý tiếp.

Việc loại khỏi khả năng tái sử dụng không được làm biến mất tài nguyên còn đang mở khỏi phép đếm giới hạn. Cần quan sát riêng kết nối hoặc tác vụ đang chờ kết thúc, đồng thời bảo đảm chúng không tăng vô hạn qua các lần timeout lặp lại.

### SR-TO-003 — Nhận dữ liệu hữu hạn trước xử lý

Với endpoint tạo đơn có body tối đa 16 KiB, cổng vào phải hoàn tất nhận header trong hai giây kể từ byte đầu tiên của request và hoàn tất nhận body trong bốn giây kể từ khi nhận đủ header. Khi vượt giới hạn thời gian hoặc kích thước, cổng vào phải kết thúc nhận theo hợp đồng giao tiếp.

Khoảng chờ kết nối chưa gửi byte đầu tiên, thời gian giữ kết nối nhàn rỗi và tổng số kết nối đồng thời phải có giới hạn riêng trong thiết kế. Các giới hạn đó không được coi là đã được bao phủ bởi đồng hồ bắt đầu từ byte đầu tiên.

Phải kiểm thử trường hợp client đều đặn gửi một ít dữ liệu trước khi hết idle timeout: tổng thời gian nhận body vẫn phải bị giới hạn. Nếu triển khai trên giao thức hỗ trợ nhiều luồng trong một kết nối, cần xác định rõ giới hạn và hành vi kết thúc áp dụng cho luồng hay kết nối.

### SR-TO-004 — Không cấp quyền khi kiểm tra quyền hết thời gian

Lời gọi kiểm tra quyền tạo đơn phải có giới hạn 200 ms và chịu ngân sách còn lại của SR-TO-001. Nếu không thể nhận quyết định quyền hợp lệ và không có nguồn thay thế được chính sách cho phép, hệ thống phải từ chối giao dịch bằng lỗi tạm thời đã đặc tả.

Không được tạo đơn, phát sinh tác vụ ghi thay mặt người dùng hoặc trả dữ liệu riêng khi chưa đáp ứng kiểm soát quyền bắt buộc. Phản hồi nhanh trong tình huống này được ghi nhận là kết thúc chờ đúng hạn, nhưng không phải thành công nghiệp vụ.

Bằng chứng phải bao gồm trường hợp người dùng có quyền, không có quyền và đã bị thu hồi quyền; kiểm tra cả khi phụ thuộc timeout và khi phản hồi muộn quay trở lại.

### SR-TO-005 — Không tạo đơn trùng sau kết quả chưa rõ

Trong thời gian hỗ trợ idempotency 24 giờ của ví dụ, các lần gửi lại hợp lệ với cùng tenant, khóa và nội dung phải quy về cùng một giao dịch tạo đơn. Khi kết quả chưa rõ, phản hồi phải chỉ dẫn cách tra cứu hoặc gửi lại theo hợp đồng; không được khẳng định chưa tạo đơn khi chưa có bằng chứng.

Ca nghiệm thu phải làm mất hoặc trì hoãn phản hồi sau khi dữ liệu đã commit, sau đó gửi lại cùng khóa. Kết quả đối soát phải chứng minh chỉ có một đơn nghiệp vụ và việc tra cứu không cho phép tenant khác đọc kết quả.

### SR-TO-006 — Quan sát và truy vết timeout

Mỗi lần timeout phải có sự kiện quan sát phân biệt được giai đoạn, nguyên nhân quan sát được, thời điểm hết hạn, trạng thái hủy và trạng thái nghiệp vụ. Sự kiện không chứa bí mật xác thực hoặc toàn bộ nội dung yêu cầu nhạy cảm.

Bộ đếm timeout, tỷ lệ thành công nghiệp vụ và số tác vụ còn chạy sau deadline phải được theo dõi riêng. Mất dữ liệu quan sát phải được thể hiện rõ; không tự coi khoảng thiếu dữ liệu là không có timeout.

## 10. Ma trận kiểm thử và bằng chứng chấp nhận

| Kịch bản | Cách tạo điều kiện | Điều phải quan sát |
|---|---|---|
| Phụ thuộc không trả dữ liệu | Giữ lời gọi tới phụ thuộc ở trạng thái chờ. | Giới hạn giai đoạn và deadline chung được thực thi; tài nguyên còn hoạt động được theo dõi. |
| Phụ thuộc trả từng phần rất chậm | Trả một phần nhỏ trước mỗi lần hết idle timeout. | Giới hạn tổng vẫn có hiệu lực, không chỉ giới hạn khoảng bất hoạt. |
| Pool đã đầy | Giữ các kết nối trong cấu hình thử, tiếp tục gửi yêu cầu. | Chờ không vượt 100 ms, hàng đợi không vượt giới hạn, không có đường chờ vô hạn khác. |
| Hết deadline trước khi gọi tiếp | Làm các bước trước tiêu gần hết ngân sách. | Không bắt đầu công việc mới hoặc retry không còn đủ ngân sách. |
| Hủy không có tác dụng ngay | Phụ thuộc tiếp tục chạy sau tín hiệu hủy. | Phân biệt ngừng chờ với dừng thực thi; không tái dùng kết nối có trạng thái chưa rõ. |
| Client ngắt kết nối | Ngắt trước khi nhận phản hồi hoặc trong lúc ghi. | Xử lý tài nguyên và kết quả giao dịch theo hợp đồng; không suy diễn rollback. |
| Kiểm tra quyền timeout | Trì hoãn hoặc làm mất phản hồi quyết định quyền. | Không có giao dịch hoặc dữ liệu được cấp ngoài chính sách. |
| Commit xong nhưng phản hồi mất | Chèn mất phản hồi sau ghi dữ liệu. | Trạng thái chưa rõ được xử lý; gửi lại không tạo thêm đơn. |
| Timeout lặp lại trong thời gian dài | Duy trì lỗi và tải trong khoảng thử đã định. | Không tích lũy vô hạn tác vụ, timer, kết nối hoặc log đang chờ. |
| Deadline đầu vào bất thường | Gửi giá trị quá lớn, đã hết hoặc sai định dạng qua giao diện có hỗ trợ. | Giới hạn cục bộ vẫn được giữ; không vô hiệu hóa timeout bằng giá trị đầu vào. |

Ví dụ ca nghiệm thu kết quả chưa rõ:

~~~gherkin
Feature: Giữ đúng kết quả tạo đơn khi phản hồi bị mất

  Scenario: Gửi lại sau timeout không tạo đơn thứ hai
    Given tenant A có quyền tạo đơn và một khóa idempotency chưa dùng
    When yêu cầu đầu tiên đã commit nhưng phản hồi bị làm mất
    And client gửi lại cùng khóa và cùng nội dung trong thời hạn hỗ trợ
    Then chỉ tồn tại một đơn nghiệp vụ của yêu cầu đó
    And client nhận được kết quả hoặc cách tra cứu theo hợp đồng
    And tenant khác không thể tra cứu kết quả bằng cùng khóa
    And bằng chứng phân biệt được timeout với kết quả commit
~~~

Hồ sơ thử cần ghi phiên bản phần mềm, cấu hình timeout ở các tầng, điều kiện tải, dữ liệu, cách chèn lỗi, độ phân giải thời gian và số liệu đối soát. Khi đo thời gian, phải nêu rõ điểm đo; log ở hai máy có đồng hồ lệch không đủ để suy ra chính xác thời gian giữa hai sự kiện nếu thiếu cơ chế hiệu chỉnh phù hợp.

Bài thử kiểm tra kết thúc chờ đúng hạn không thay thế bài thử SLO thành công nghiệp vụ. Một hệ thống trả lỗi nhanh cho tất cả người dùng có thể đạt giới hạn thời gian chờ nhưng vẫn mất khả dụng về chức năng.

## 11. Logging và chỉ số vận hành

Nên giữ ít nhất ba góc nhìn:

- **Trải nghiệm người dùng:** tỷ lệ thao tác hợp lệ thành công, lỗi tạm thời, thời gian hoàn thành và số giao dịch chưa rõ.
- **Thực thi timeout:** số lần hết hạn theo giai đoạn, số lần bắt đầu công việc sau deadline, thời gian phản hồi sau khi hết hạn.
- **Sức khỏe tài nguyên:** số tác vụ còn chạy sau deadline, kết nối chờ dọn, độ dài hàng đợi và mức sử dụng bộ đệm.

Một sự kiện minh họa có thể có dạng:

~~~json
{
  "event": "operation_timeout",
  "operation": "create_order",
  "stage": "database_execute",
  "deadline_budget_ms": 1500,
  "stage_limit_ms": 750,
  "cancel_requested": true,
  "execution_stopped": false,
  "business_outcome": "unknown",
  "correlation_id": "example-correlation"
}
~~~

Đây là ví dụ dữ liệu quan sát, không phải giao diện của một thư viện cụ thể. Hệ thống phải định nghĩa ý nghĩa chính xác của từng trường. Trạng thái chưa rõ cần được cập nhật hoặc liên kết với sự kiện giải quyết sau đó, thay vì tồn tại vĩnh viễn mà không ai xử lý.

Không dùng định danh tùy ý có số lượng không giới hạn làm nhãn cho mọi metric. Có thể giữ mã tương quan trong log hoặc trace có kiểm soát và dùng tập nhãn hữu hạn cho bộ đếm. Chính sách lưu và truy cập phải bảo vệ dữ liệu người dùng.

Cảnh báo nên gắn với tác động: timeout tăng kéo theo thất bại nghiệp vụ, hoặc tác vụ còn chạy tăng dù phản hồi đã kết thúc. Chỉ tăng timeout theo cảnh báo có thể làm tài nguyên bị giữ lâu hơn; cần xác định nguyên nhân và đánh giá lại ngân sách.

## 12. Những cách viết yêu cầu cần tránh

| Cách viết chưa đủ | Vấn đề | Cách làm rõ |
|---|---|---|
| “Mọi API timeout sau ba giây.” | Chưa có ranh giới, loại hoạt động và hành vi sau timeout. | Đặc tả từng hành trình, giai đoạn, deadline và hợp đồng kết thúc. |
| “Có read timeout nên không thể giữ kết nối lâu.” | Timeout có thể chỉ đo khoảng bất hoạt. | Thêm giới hạn tổng và kiểm thử gửi dữ liệu nhỏ giọt. |
| “Mỗi tầng được chờ một giây.” | Tổng thời gian tuần tự và retry có thể vượt nhiều giây. | Truyền và giới hạn ngân sách còn lại theo deadline chung. |
| “Hết timeout thì tài nguyên tự giải phóng.” | Bên gọi ngừng chờ nhưng tác vụ có thể tiếp tục. | Đặc tả yêu cầu hủy, trạng thái dừng và khả năng tái sử dụng tài nguyên. |
| “Timeout khi tạo đơn nghĩa là chưa tạo đơn.” | Commit có thể đã hoàn tất. | Có trạng thái chưa rõ, định danh chống lặp và tra cứu kết quả. |
| “Xác thực chậm thì cho qua để giữ dịch vụ.” | Có thể cấp quyền trái phép. | Nêu chính sách cho từng thao tác và từ chối khi không thể xác minh điều kiện bắt buộc. |
| “Tăng timeout để hết lỗi.” | Có thể che phụ thuộc chậm và tăng cạn tài nguyên. | Đánh giá độ trễ, tải, giới hạn đồng thời và mục tiêu nghiệp vụ. |
| “Client gửi deadline nào thì server dùng deadline đó.” | Đầu vào có thể kéo dài giữ tài nguyên hoặc sai quy ước thời gian. | Kiểm tra, chuyển đổi và chặn bởi giới hạn cục bộ. |

## 13. Áp dụng trong vòng đời phát triển

Khi phân tích yêu cầu, xác định thời gian chờ mà người dùng chấp nhận và tác động của kết quả chưa rõ. Khi mô hình hóa đe dọa, bổ sung giữ kết nối chậm, cạn pool, retry khuếch đại và phụ thuộc bảo mật bị treo.

Khi thiết kế, gắn các mã SR-TO với điểm thực thi timeout, cơ chế hủy và nguồn bằng chứng. Nếu thay thư viện, proxy, cơ chế truy cập dữ liệu hoặc dịch vụ kiểm tra quyền, phải xác minh lại ngữ nghĩa timeout có liên quan; cùng tên cấu hình không bảo đảm cùng hành vi.

Khi nghiệm thu, kiểm tra cả giới hạn thời gian, tính đúng dữ liệu, quyền truy cập và tài nguyên còn hoạt động. Khi vận hành, dùng số liệu để đánh giá yêu cầu có còn phù hợp, đồng thời giữ lịch sử thay đổi ngưỡng và lý do chấp nhận rủi ro.

Bài tập áp dụng: với chức năng nộp bài thi trực tuyến, hãy xác định deadline xử lý, giới hạn lưu dữ liệu, hành vi khi xác thực bị chậm và cách trả lời người học khi hết thời gian chờ ngay sau khi bài đã được lưu. Viết một yêu cầu đo được cho từng phần, liên kết với rủi ro và nêu bằng chứng đủ để xác nhận rằng bài không bị mất hoặc nộp trùng.

