Câu 1. Trong lập trình khai báo, mô tả chương trình chủ yếu tập trung vào điều gì?
A. Thứ tự từng lệnh và cách cập nhật mọi biến trung gian
B. Cách lặp và phân nhánh cụ thể trên từng phần tử dữ liệu
C. Kết quả hoặc ràng buộc cần đạt, không ấn định các bước
D. Lịch chạy chi tiết cho mọi tác vụ đồng thời của hệ thống
Đáp án đúng: C

Câu 2. Lập trình khai báo có loại bỏ nhu cầu về thuật toán thực thi không?
A. Không; lập trình viên vẫn phải viết từng bước lặp
B. Không; engine vẫn phải chọn cách hiện thực mô tả
C. Có; đặc tả tự tạo ra kết quả mà không cần engine
D. Có; toàn bộ truy vấn chỉ được xử lý khi biên dịch
Đáp án đúng: B

Câu 3. Một truy vấn SQL `SELECT ... WHERE ...` thường thể hiện điều gì?
A. Số luồng xử lý cùng thứ tự truy cập từng trang dữ liệu
B. Thuật toán sắp xếp vật lý mà máy chủ phải chạy
C. Tập kết quả và điều kiện lọc, không cố định cách quét
D. Chỉ số cần sử dụng và thứ tự từng thao tác đọc
Đáp án đúng: C

Câu 4. Nếu truy vấn SQL không có `ORDER BY`, điều gì đúng về thứ tự các hàng?
A. Các hàng luôn được sắp theo khóa chính tăng dần
B. Các hàng luôn theo vị trí lưu trữ trên đĩa
C. Các hàng luôn theo thứ tự chúng được chèn vào
D. Không có thứ tự hàng kết quả được bảo đảm
Đáp án đúng: D

Câu 5. Trong truy vấn có `GROUP BY`, chức năng đúng của `HAVING` là gì?
A. Lọc từng hàng trước bước gom nhóm dữ liệu
B. Lọc nhóm theo điều kiện sau bước gom nhóm
C. Thay thế khóa gom nhóm bằng một biểu thức khác
D. Sắp xếp nhóm trước khi thực hiện phép tổng hợp
Đáp án đúng: B

Câu 6. Trong SQL, cách kiểm tra cột `city` mang giá trị `NULL` đúng là gì?
A. Dùng biểu thức `city LIKE NULL` trong điều kiện
B. Dùng biểu thức `city = NULL` trong điều kiện
C. Dùng biểu thức `city == NULL` trong điều kiện
D. Dùng biểu thức `city IS NULL` trong điều kiện
Đáp án đúng: D

Câu 7. Với cột `score` có giá trị `NULL`, `COUNT(score)` khác `COUNT(*)` thế nào?
A. `COUNT(*)` chỉ đếm số giá trị `score` duy nhất
B. `COUNT(score)` đếm mọi hàng kể cả giá trị `NULL`
C. Bỏ qua hàng có `score` là `NULL` khi đếm cột
D. `COUNT(*)` chỉ đếm hàng có mọi cột không `NULL`
Đáp án đúng: C

Câu 8. Với hai phép `INNER JOIN` độc lập về tác dụng phụ, optimizer có thể làm gì?
A. Tự động đổi kết nối trong thành kết nối ngoài
B. Đổi thứ tự kết nối mà vẫn giữ kết quả logic
C. Bỏ mọi điều kiện kết nối để giảm chi phí thực thi
D. Bắt buộc kết nối đúng thứ tự bảng viết trong SQL
Đáp án đúng: B

Câu 9. `EXPLAIN` cho truy vấn SQL thường được dùng để xem điều gì?
A. Kế hoạch truy cập và các toán tử thực thi dự kiến
B. Giá trị đầu ra của mọi bản ghi đang bị khóa
C. Đường dẫn tệp nguồn chứa mã SQL đã thực thi
D. Các quyền truy cập của toàn bộ người dùng database
Đáp án đúng: A

Câu 10. Vì sao cùng một truy vấn SQL có thể dùng kế hoạch khác sau khi dữ liệu thay đổi?
A. SQL bắt buộc cố định một kế hoạch khi tạo bảng
B. Thống kê và chi phí ước lượng có thể đổi
C. Trình tối ưu hóa chỉ chọn kế hoạch theo tên cột
D. Engine luôn quét toàn bộ bảng bất kể kích thước
Đáp án đúng: B

Câu 11. Với giá trị do người dùng nhập vào `WHERE id = ?`, lựa chọn nào an toàn hơn?
A. Ghép input vào truy vấn rồi bỏ các câu lệnh `WHERE`
B. Bind tham số qua prepared statement, không nối chuỗi
C. Ghép trực tiếp input đã thêm dấu cách vào SQL
D. Chèn input vào câu SQL sau khi đổi thành chữ hoa
Đáp án đúng: B

Câu 12. Trong SQL, điều kiện `EXISTS (subquery)` kiểm tra chủ yếu điều gì?
A. Có ít nhất một hàng thỏa truy vấn con hay không
B. Có tối thiểu hai hàng thỏa truy vấn con hay không
C. Có hàng nào chứa toàn bộ giá trị khác `NULL`
D. Có đúng một hàng thỏa truy vấn con hay không
Đáp án đúng: A

Câu 13. Khi dùng `WITH cte AS (...)`, phát biểu nào đúng giữa các database?
A. CTE không buộc được lưu thành bảng tạm vật lý
B. CTE mặc nhiên chỉ chạy một lần trong mọi hệ quản trị
C. CTE mặc nhiên được lưu vĩnh viễn sau lệnh truy vấn
D. CTE mặc nhiên luôn tạo bảng tạm vật lý trên đĩa
Đáp án đúng: A

Câu 14. Ràng buộc `CHECK (price >= 0)` thể hiện ý tưởng khai báo nào?
A. Nêu vòng lặp duyệt từng dòng bằng mã ứng dụng
B. Nêu thứ tự khóa các bảng trước mỗi lần cập nhật
C. Nêu thuật toán tính giá trị `price` trong bộ nhớ
D. Khai báo điều kiện hợp lệ để DB kiểm tra
Đáp án đúng: D

Câu 15. Khi phân trang SQL, tại sao thường dùng `ORDER BY` có tiêu chí phá hòa?
A. Để có thứ tự xác định khi nhiều hàng trùng khóa sắp
B. Để database buộc dùng index cho mọi trang kết quả
C. Để bỏ kiểm tra điều kiện lọc khi dùng `OFFSET`
D. Để mọi truy vấn phân trang tự động chạy tuần tự
Đáp án đúng: A

Câu 16. Khi tối ưu biểu thức khai báo có gọi hàm gây side effect, rủi ro nào cần xét?
A. Engine tự loại bỏ side effect trước lúc thực thi
B. Engine luôn gọi hàm đúng một lần theo thứ tự viết
C. Engine có thể đổi thứ tự hoặc số lần đánh giá
D. Engine bảo đảm không gọi hàm khi biểu thức có `WHERE`
Đáp án đúng: C

Câu 17. Trong Java Stream, `filter(predicate)` mô tả thao tác nào?
A. Ghép nhiều luồng nguồn thành một luồng kết quả
B. Giữ các phần tử thỏa predicate được khai báo
C. Gom mọi phần tử vào một collection ngay lập tức
D. Chuyển mỗi phần tử thành đối tượng giá trị mới
Đáp án đúng: B

Câu 18. Trong Java Stream, `map(function)` thường dùng để làm gì?
A. Biến đổi từng phần tử bằng hàm ánh xạ được cung cấp
B. Giữ các phần tử được predicate chấp nhận trong luồng
C. Gộp tất cả phần tử thành một kết quả duy nhất
D. Sắp xếp các phần tử bằng comparator được cung cấp
Đáp án đúng: A

Câu 19. Vì sao `flatMap` khác `map` trong Java Stream?
A. Chỉ áp dụng predicate để bỏ phần tử không hợp lệ
B. Chỉ sắp xếp các phần tử theo thứ tự giảm dần
C. Có thể duyệt lại stream sau khi terminal đã chạy
D. Dùng stream con rồi trải phẳng phần tử
Đáp án đúng: D

Câu 20. Khi nào pipeline có `filter` và `map` thường bắt đầu duyệt nguồn?
A. Chỉ khi gọi `close()` trên nguồn của pipeline
B. Ngay khi gọi `filter` đầu tiên trong pipeline
C. Ngay khi khai báo hàm lambda trong biểu thức
D. Khi terminal operation yêu cầu xử lý dữ liệu
Đáp án đúng: D

Câu 21. Sau khi một Stream đã chạy terminal operation, hành động nào phù hợp?
A. Gọi `reset()` để quay stream về trạng thái ban đầu
B. Cần tạo Stream mới cho lần duyệt tiếp theo
C. Gọi `iterator()` để khôi phục stream đã tiêu thụ
D. Dùng lại stream đó để tiếp tục một terminal khác
Đáp án đúng: B

Câu 22. `Collectors.groupingBy(User::role)` chủ yếu tạo ra cấu trúc nào?
A. Map gom người dùng theo khóa role được tính
B. Set có thứ tự cố định của toàn bộ người dùng
C. Stream dùng chung một iterator cho từng role
D. List duy nhất chỉ chứa một role của mỗi người dùng
Đáp án đúng: A

Câu 23. Khi dùng `reduce` trong Stream song song, yêu cầu quan trọng của accumulator là gì?
A. Tuân thủ tính kết hợp phù hợp với cách phân mảnh
B. Phải thay đổi một biến global sau mỗi lần kết hợp
C. Phải dựa vào thứ tự thread chạy để giữ đúng kết quả
D. Phải ghi log mỗi phần tử trước khi kết hợp kết quả
Đáp án đúng: A

Câu 24. Vì sao cập nhật chung một `ArrayList` từ `parallelStream().forEach` có rủi ro?
A. `forEach` luôn duy trì thứ tự nguồn khi song song
B. Nhiều luồng sửa trạng thái chung không đồng bộ
C. Luồng song song luôn xử lý dữ liệu thành một thread
D. `ArrayList` tự khóa tất cả thao tác ghi trong JVM
Đáp án đúng: B

Câu 25. `peek(action)` trong Stream nên được dùng thận trọng vì lý do nào?
A. `peek` luôn biến đổi kiểu phần tử của pipeline
B. Mọi lời gọi `peek` sẽ tự đóng collection đầu vào
C. `peek` tự loại bỏ phần tử không thỏa predicate
D. Action phụ có thể bị bỏ qua do cách tối ưu pipeline
Đáp án đúng: D

Câu 26. Với stream có thứ tự, `findFirst()` khác `findAny()` ở đảm bảo nào?
A. `findFirst` bắt buộc chọn phần tử có giá trị lớn nhất
B. `findAny` luôn trả phần tử cuối của collection
C. Giữ phần tử đầu theo encounter order của nguồn
D. `findAny` buộc trả phần tử đầu theo encounter order
Đáp án đúng: C

Câu 27. Khi một Stream đang duyệt `ArrayList`, thay đổi cấu trúc nguồn từ ngoài có thể gây gì?
A. Can thiệp nguồn có thể làm kết quả sai hoặc ném lỗi
B. Mọi thay đổi nguồn sẽ được phản ánh nguyên tử tự động
C. Stream tự sao chép tất cả phần tử trước mọi terminal
D. Trình biên dịch luôn cấm các lệnh sửa list nguồn
Đáp án đúng: A

Câu 28. Tính thuần khiết của một hàm trong biểu thức khai báo hỗ trợ lợi ích nào?
A. Dễ thay thế biểu thức và kiểm thử ổn định
B. Tự động làm mọi phép tính nhanh hơn một bậc độ phức tạp
C. Tự động tạo thread riêng để chạy mọi lời gọi hàm
D. Buộc các kết quả được lưu bền vững trong database
Đáp án đúng: A

Câu 29. Trong lập trình logic, quy tắc `eligible(X) :- paid(X).` mô tả điều gì?
A. Thao tác gán giá trị mới vào biến X trên heap
B. Trình tự bắt buộc gọi hàm `eligible` trước `paid`
C. Vòng lặp duyệt biến X cho đến khi gặp exception
D. Quan hệ suy ra `eligible` khi mệnh đề `paid` đúng
Đáp án đúng: D

Câu 30. Trong Prolog, unification chủ yếu giải quyết vấn đề nào?
A. Sắp xếp facts theo thời điểm được thêm vào nguồn
B. Tìm phép thế biến để hai hạng có thể khớp nhau
C. Khóa biến sau khi kết thúc toàn bộ chương trình
D. Gán biến mutable rồi cập nhật bằng toán tử cộng
Đáp án đúng: B

Câu 31. Với Datalog có quy tắc đệ quy hữu hạn thích hợp, engine thường tìm kết quả bằng gì?
A. Chỉ chạy một truy vấn SQL để cập nhật mọi biến
B. Bỏ qua quy tắc đệ quy vì không thể suy diễn
C. Lặp suy diễn tới điểm cố định không có fact mới
D. Duyệt AST một lần mà không sinh thêm bất kỳ fact
Đáp án đúng: C

Câu 32. Trong hệ rule dùng closed-world assumption, không chứng minh được fact thường được hiểu thế nào?
A. Fact được xem là đúng nếu chưa chứng minh là sai
B. Fact luôn gây ngoại lệ runtime rồi dừng engine
C. Thiếu chứng cứ được xem là sai theo closed-world
D. Fact tự động được thêm vào bộ tri thức ban đầu
Đáp án đúng: C

Câu 33. Một bộ giải CSP có biến và miền giá trị thường sử dụng constraint propagation để làm gì?
A. Thay toàn bộ ràng buộc bằng vòng lặp thủ công
B. Loại giá trị khỏi miền khi không thể thỏa constraint
C. Tăng miền của mọi biến để sinh thêm nghiệm mới
D. Cố định mọi biến vào giá trị đầu tiên ngay lập tức
Đáp án đúng: B

Câu 34. Khi giải một bài CSP bằng backtracking, thao tác cốt lõi là gì?
A. Chuyển mọi phép kiểm tra thành một lệnh SQL `JOIN`
B. Thử mọi hoán vị rồi chỉ giữ lần gán đầu tiên
C. Thử gán rồi quay lui khi gặp xung đột ràng buộc
D. Tắt các ràng buộc đã thất bại để tránh phải quay lui
Đáp án đúng: C

Câu 35. Nếu bộ ràng buộc là bất khả thỏa mãn, solver đúng cần phản hồi gì?
A. Báo không có nghiệm đáp ứng toàn bộ ràng buộc
B. Chọn tùy ý một nghiệm dù vi phạm điều kiện cứng
C. Bỏ những điều kiện xung đột để sinh nghiệm hợp lệ
D. Trả nghiệm vi phạm ít ràng buộc nhất mà không báo
Đáp án đúng: A

Câu 36. Nếu nhiều cấu hình thỏa cùng một đặc tả khai báo, engine được phép làm gì?
A. Luôn chọn nghiệm theo thứ tự tên biến trong mã nguồn
B. Tự động chuyển mọi nghiệm thành cùng một chuỗi byte
C. Chọn nghiệm thỏa quy tắc hoặc mục tiêu tối ưu
D. Bắt buộc tìm mọi nghiệm dù người gọi chỉ cần một
Đáp án đúng: C

Câu 37. Vì sao rule engine có side effect cần quản lý thứ tự kích hoạt rule?
A. Mọi quy tắc sẽ chạy đồng thời với cùng thứ tự cố định
B. Động cơ luật tự hoàn tác mọi side effect phát sinh
C. Thứ tự chạy luật có thể tác động trạng thái chung
D. Mọi luật chỉ mô tả dữ liệu, không thể gọi hành động
Đáp án đúng: C

Câu 38. Trong DSL, cách hiểu đúng về internal DSL là gì?
A. Không thể kiểm tra kiểu vì chỉ tồn tại dưới dạng text
B. Luôn cần lexer và parser của ngôn ngữ hoàn toàn mới
C. Luôn được biên dịch độc lập trước khi chạy ứng dụng
D. Tận dụng cú pháp và cơ chế của ngôn ngữ chủ
Đáp án đúng: D

Câu 39. External DSL khác internal DSL ở điểm nào thường gặp?
A. Không được dùng AST để phân tích hoặc chuyển đổi lệnh
B. Bắt buộc chạy trực tiếp trên CPU không qua interpreter
C. Phải biểu diễn hoàn toàn bằng method của ngôn ngữ chủ
D. Có cú pháp riêng, cần parser hoặc bước diễn giải riêng
Đáp án đúng: D

Câu 40. Trong pipeline xử lý DSL, AST có ích cho công đoạn nào?
A. Biểu diễn cấu trúc để phân tích, kiểm tra và biến đổi
B. Thay thế mọi kiểm tra cú pháp bằng kiểm tra database
C. Làm cho mọi chương trình DSL tự động không có lỗi
D. Lưu sẵn mọi kết quả runtime để bỏ qua việc thực thi
Đáp án đúng: A

Câu 41. Với DSL có kiểu dữ liệu, kiểm tra kiểu trước khi thực thi giúp gì?
A. Tự động xác định một nghiệm duy nhất cho mọi đầu vào
B. Đảm bảo chương trình luôn có hiệu năng tối ưu tuyệt đối
C. Tự động xóa toàn bộ ràng buộc không thỏa ở runtime
D. Bắt được tổ hợp kiểu không hợp lệ trước khi chạy
Đáp án đúng: D

Câu 42. Khi DSL cho phép biểu thức do người dùng nhập, biện pháp bảo vệ phù hợp là gì?
A. Trộn biểu thức vào shell command rồi bỏ qua escaping
B. Cho biểu thức gọi toàn bộ method qua Reflection không giới hạn
C. Tắt kiểm tra kiểu và chạy trực tiếp mã người dùng
D. Giới hạn cú pháp và quyền thực thi theo whitelist rõ ràng
Đáp án đúng: D

Câu 43. Trong cấu hình desired state, khai báo `replicas: 3` chủ yếu là gì?
A. Bảo đảm có đúng ba process ngay lúc lưu tệp
B. Mục tiêu số bản sao mà controller cần duy trì
C. Lệnh chỉ được chạy một lần để tạo ba process
D. Thứ tự ba câu lệnh shell để khởi chạy container
Đáp án đúng: B

Câu 44. Trong mô hình reconciliation, controller thường so sánh hai thứ gì?
A. Thứ tự lệnh đã chạy và thời gian biên dịch mã nguồn
B. So sánh trạng thái mong muốn với quan sát thực tế
C. Định dạng JSON với YAML mà không xét tài nguyên
D. Cú pháp của hai ngôn ngữ khai báo không liên quan
Đáp án đúng: B

Câu 45. Khi áp dụng lại cùng desired state mà thực tế đã đúng, tính idempotent có nghĩa gì?
A. Lần áp dụng sau phải tạo lại toàn bộ tài nguyên
B. Lần áp dụng sau tăng số bản sao thêm một đơn vị
C. Lần áp dụng sau không tạo thêm thay đổi cần thiết
D. Lần áp dụng sau phải đổi ID của mọi đối tượng
Đáp án đúng: C

Câu 46. Khi trạng thái thực tế bị drift khỏi đặc tả, hệ thống khai báo nên làm gì?
A. Phát hiện lệch và cố gắng hội tụ lại mục tiêu
B. Bỏ qua drift vì đặc tả đã được lưu từ trước
C. Ghi đè đặc tả theo mọi thay đổi ngoài ý muốn
D. Chạy lại ngẫu nhiên một số bước bootstrap
Đáp án đúng: A

Câu 47. Vì sao một hệ desired-state thường bảo đảm eventual convergence hơn là kết quả tức thì?
A. Engine chỉ được thực thi đúng một lần sau lúc deploy
B. Cú pháp khai báo không cho phép xử lý bất đồng bộ
C. Vòng reconcile và tác động bên ngoài cần thời gian
D. Mọi thay đổi phải đợi lập trình viên biên dịch lại
Đáp án đúng: C

Câu 48. Kiểm thử hệ khai báo có bước thực thi gây side effect nên ưu tiên điều gì?
A. Chỉ kiểm tra cấu hình có đủ số dòng được yêu cầu
B. Bỏ kiểm tra kết quả vì engine đã chọn execution plan
C. Chỉ so khớp nguyên văn thứ tự lệnh từ engine
D. Kiểm tra invariant, kết quả và side effect quan sát được
Đáp án đúng: D
