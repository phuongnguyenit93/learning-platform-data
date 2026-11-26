Câu 01. Vai trò cốt lõi của hệ quản trị cơ sở dữ liệu (DBMS) là gì?
A. Quản lý lưu trữ, truy vấn và kiểm soát truy cập dữ liệu.
B. Chỉ biên dịch mã nguồn ứng dụng thành chương trình chạy.
C. Chỉ vận chuyển gói tin giữa các máy trong cùng mạng.
D. Quản lý giao diện người dùng và bố cục các biểu mẫu.
Đáp án đúng: A

Câu 02. Phân biệt schema và trạng thái dữ liệu tại một thời điểm như thế nào?
A. Schema là truy vấn; trạng thái là quyền truy cập của tài khoản.
B. Schema chứa bản ghi; trạng thái chỉ mô tả tên trường dữ liệu.
C. Schema là bản sao lưu; trạng thái là kiểu cột của từng bảng.
D. Schema mô tả cấu trúc; trạng thái biểu thị dữ liệu hiện có.
Đáp án đúng: D

Câu 03. Trong mô hình quan hệ, một hàng của bảng thường đại diện cho gì?
A. Một ràng buộc kiểm tra áp dụng cho toàn bộ cơ sở dữ liệu.
B. Một bộ giá trị thuộc các cột của quan hệ tương ứng.
C. Một chỉ mục chứa danh sách các bảng trong cùng schema.
D. Một kiểu dữ liệu duy nhất dùng chung cho tất cả cột.
Đáp án đúng: B

Câu 04. Ý nghĩa chính của PRIMARY KEY trong bảng quan hệ là gì?
A. Cho phép trùng khóa khi hai hàng có thời điểm tạo khác nhau.
B. Cho phép giá trị NULL nếu đã có một cột UNIQUE khác.
C. Định danh duy nhất từng hàng và không chấp nhận giá trị NULL.
D. Xác định thứ tự lưu vật lý của mọi hàng trong bảng dữ liệu.
Đáp án đúng: C

Câu 05. Ràng buộc FOREIGN KEY hỗ trợ tính toàn vẹn nào?
A. Tự chèn hàng bên bảng cha khi khóa ngoại chưa tồn tại ở đó.
B. Kiểm tra giá trị tham chiếu tới khóa hợp lệ ở bảng liên quan.
C. Bảo đảm trường được tham chiếu luôn tăng theo thời gian nhập.
D. Bảo đảm mọi giá trị khóa ngoại phải khác nhau trong cùng bảng.
Đáp án đúng: B

Câu 06. Khóa ghép (composite key) có đặc điểm nào?
A. Được xác định bởi tổ hợp giá trị của nhiều cột cùng nhau.
B. Chỉ dùng cho những bảng hoàn toàn không có khóa ngoại.
C. Được tự tạo khi hai bảng có cùng tên cột trong schema.
D. Chỉ được tạo từ một cột duy nhất có kiểu số nguyên.
Đáp án đúng: A

Câu 07. Một candidate key trong quan hệ được hiểu như thế nào?
A. Tập mọi thuộc tính chưa tham gia bất kỳ phép JOIN nào.
B. Tập thuộc tính bắt buộc phải chứa một số nguyên tự tăng.
C. Tập thuộc tính tối thiểu có thể định danh duy nhất mỗi hàng.
D. Tập thuộc tính chỉ được dùng trong điều kiện ORDER BY.
Đáp án đúng: C

Câu 08. Ràng buộc NOT NULL đối với một cột có tác dụng gì?
A. Ngăn truy vấn đọc cột khi chưa có giao dịch nào commit.
B. Ngăn lưu hai giá trị giống nhau trong cột của bảng.
C. Ngăn thay đổi giá trị cột sau lần ghi dữ liệu đầu tiên.
D. Ngăn lưu giá trị NULL vào cột được khai báo ràng buộc.
Đáp án đúng: D

Câu 09. Ràng buộc CHECK trong bảng quan hệ chủ yếu dùng để làm gì?
A. Giới hạn giá trị hợp lệ theo biểu thức điều kiện đã khai báo.
B. Chuyển các giá trị sai điều kiện thành giá trị hợp lệ gần nhất.
C. Đảm bảo giá trị cột chỉ thay đổi khi có khóa ngoại phù hợp.
D. Tự tạo chỉ mục mới cho mọi cột xuất hiện trong biểu thức.
Đáp án đúng: A

Câu 10. Trong quan hệ một-nhiều giữa phòng ban và nhân viên, khóa ngoại thường đặt ở đâu?
A. Trong bảng phòng ban để tham chiếu từng nhân viên riêng lẻ.
B. Trong bảng nhân viên để tham chiếu đến khóa của phòng ban.
C. Trong bảng phòng ban làm khóa chính thay cho mã phòng ban.
D. Trong cả hai bảng với hai khóa ngoại vòng tròn bắt buộc.
Đáp án đúng: B

Câu 11. Mối quan hệ nhiều-nhiều giữa sinh viên và môn học thường được biểu diễn thế nào?
A. Tạo một khóa ngoại duy nhất ở bảng sinh viên là đủ.
B. Đặt toàn bộ danh sách môn học trong một cột kiểu số.
C. Đưa bản sao mọi sinh viên vào từng hàng của bảng môn học.
D. Dùng bảng liên kết chứa khóa tham chiếu tới hai bảng.
Đáp án đúng: D

Câu 12. Dấu hiệu nào thể hiện bất thường cập nhật do dữ liệu lặp?
A. Đổi một thông tin phải sửa nhiều hàng để giữ nhất quán.
B. Một bảng có khóa chính và nhiều ràng buộc khóa ngoại.
C. Một truy vấn JOIN ghép các hàng theo điều kiện bằng nhau.
D. Một truy vấn SELECT có thể lọc dữ liệu theo nhiều cột.
Đáp án đúng: A

Câu 13. Chuẩn 1NF trong mô hình quan hệ yêu cầu điều gì?
A. Mọi bảng phải có ít nhất hai cột tham gia khóa chính.
B. Mọi phụ thuộc hàm đều phải có vế trái là siêu khóa.
C. Mỗi ô lưu một giá trị đơn trong miền giá trị phù hợp.
D. Mỗi bảng bắt buộc có một chỉ mục trên tất cả các cột.
Đáp án đúng: C

Câu 14. Với bảng đã ở 1NF, yêu cầu chính của chuẩn 2NF là gì?
A. Mọi quan hệ phải tách thành hai bảng để giảm số hàng lưu.
B. Mọi cột không khóa phải có khóa ngoại tới một bảng riêng.
C. Thuộc tính không khóa không phụ thuộc vào một phần khóa ứng viên.
D. Mỗi bảng phải có đúng một candidate key kiểu số nguyên.
Đáp án đúng: C

Câu 15. Điều kiện cốt lõi của chuẩn 3NF liên quan đến phụ thuộc hàm là gì?
A. Chỉ cho phép một khóa ngoại xuất hiện trong mỗi quan hệ.
B. Loại tất cả giá trị NULL khỏi mọi bảng trước khi lưu.
C. Bắt buộc mọi cột mang dữ liệu đều có thuộc tính UNIQUE.
D. Tránh phụ thuộc bắc cầu gây dư thừa giữa thuộc tính không khóa.
Đáp án đúng: D

Câu 16. Khi phi chuẩn hóa có chủ đích, đánh đổi nào thường xuất hiện?
A. Loại bỏ mọi nhu cầu cập nhật dữ liệu đã lưu vào hệ thống.
B. Giảm chi phí đọc ghép bảng nhưng tăng trùng lặp và đồng bộ.
C. Đảm bảo dữ liệu luôn nhất quán mà không cần ràng buộc.
D. Giảm mọi chi phí lưu trữ dù số cột lặp tăng lên.
Đáp án đúng: B

Câu 17. Trong thiết kế dữ liệu, thực thể và thuộc tính khác nhau như thế nào?
A. Thực thể là khóa ngoại; thuộc tính luôn là khóa chính.
B. Thực thể là đối tượng; thuộc tính mô tả đặc điểm của đối tượng.
C. Thực thể là kiểu cột; thuộc tính là cơ sở dữ liệu lưu cột.
D. Thực thể là phép JOIN; thuộc tính là điều kiện thực hiện JOIN.
Đáp án đúng: B

Câu 18. Trong SQL, mệnh đề WHERE của SELECT thực hiện nhiệm vụ gì?
A. Lọc các hàng thỏa điều kiện trước khi nhóm dữ liệu.
B. Đặt bí danh mới cho mọi bảng xuất hiện trong truy vấn.
C. Chỉ lọc các nhóm đã tạo bởi phép tổng hợp GROUP BY.
D. Sắp xếp các hàng đầu ra theo thứ tự tăng hoặc giảm.
Đáp án đúng: A

Câu 19. Mệnh đề ORDER BY trong SQL dùng chủ yếu để làm gì?
A. Xác định thứ tự các hàng của kết quả truy vấn.
B. Lọc bỏ các hàng không đáp ứng biểu thức điều kiện.
C. Tự nhóm các hàng có giá trị cột giống nhau.
D. Tự loại hàng trùng lặp ở mọi cột được chọn.
Đáp án đúng: A

Câu 20. INNER JOIN giữa hai bảng thường chỉ trả về những hàng nào?
A. Mọi tổ hợp hàng của hai bảng dù không có điều kiện.
B. Các cặp hàng thỏa điều kiện kết nối từ cả hai bảng.
C. Mọi hàng bảng trái dù không khớp với bảng bên phải.
D. Mọi hàng bảng phải dù không khớp với bảng bên trái.
Đáp án đúng: B

Câu 21. Với LEFT JOIN, các hàng ở bảng bên trái không có kết quả khớp được xử lý thế nào?
A. Được ghép với hàng đầu tiên của bảng phải bất kể điều kiện.
B. Được chuyển thành hàng mới trong bảng phải trước khi đọc.
C. Vẫn xuất hiện, với các cột phía phải nhận giá trị NULL.
D. Bị loại bỏ hoàn toàn như khi dùng kết nối INNER JOIN.
Đáp án đúng: C

Câu 22. Điểm khác nhau giữa COUNT(*) và COUNT(column) trong SQL là gì?
A. COUNT(*) chỉ đếm hàng có khóa chính khác giá trị NULL.
B. COUNT(column) luôn bao gồm cả hàng có giá trị NULL.
C. COUNT(column) bỏ các giá trị NULL; COUNT(*) đếm các hàng.
D. COUNT(*) luôn bỏ những hàng có cột khác mang giá trị NULL.
Đáp án đúng: C

Câu 23. Khi dùng GROUP BY department_id cùng COUNT(*), kết quả thể hiện gì?
A. Số phòng ban có cột department_id được đánh chỉ mục.
B. Danh sách mọi hàng đã được sắp theo thời điểm tạo.
C. Tổng số cột xuất hiện trong bảng của từng phòng ban.
D. Số hàng được đếm theo từng giá trị department_id.
Đáp án đúng: D

Câu 24. Trong truy vấn tổng hợp, HAVING thường được dùng để làm gì?
A. Chỉ định tên cột sẽ được dùng làm khóa chính của bảng.
B. Lọc các nhóm theo điều kiện trên kết quả tổng hợp.
C. Xác định thứ tự ghi các hàng vào vùng lưu trữ vật lý.
D. Lọc các hàng thô trước mọi phép tính tổng hợp nhóm.
Đáp án đúng: B

Câu 25. Để thêm một hàng mới vào bảng SQL, nên dùng loại câu lệnh nào?
A. UPDATE với điều kiện chỉ chọn một hàng chưa có.
B. INSERT với các cột và giá trị cần ghi tương ứng.
C. SELECT với điều kiện lọc theo khóa hàng chưa có.
D. DELETE với tùy chọn tạo lại hàng trước khi xóa.
Đáp án đúng: B

Câu 26. Vì sao UPDATE không có WHERE cần được xem xét kỹ?
A. Luôn từ chối thực thi nếu bảng có khóa ngoại.
B. Luôn xóa toàn bộ bảng cùng các chỉ mục đã có.
C. Chỉ cập nhật hàng đầu tiên theo khóa chính mặc định.
D. Có thể thay đổi tất cả hàng của bảng khi chạy lệnh.
Đáp án đúng: D

Câu 27. Khác biệt cơ bản giữa DELETE và DROP TABLE là gì?
A. DELETE xóa hàng; DROP TABLE loại bỏ đối tượng bảng.
B. DELETE đổi tên bảng; DROP TABLE chỉ xóa chỉ mục phụ.
C. DELETE chỉ xóa index; DROP TABLE khôi phục các hàng.
D. DELETE xóa schema; DROP TABLE chỉ xóa một vài hàng.
Đáp án đúng: A

Câu 28. Trong ACID, tính nguyên tử (Atomicity) yêu cầu điều gì?
A. Giao dịch luôn cho kết quả nhanh hơn mọi truy vấn độc lập.
B. Các giao dịch chạy nối tiếp theo thứ tự người dùng gửi.
C. Các thay đổi trong giao dịch được áp dụng trọn vẹn hoặc hủy.
D. Giao dịch không cần ghi log vì bộ nhớ giữ kết quả.
Đáp án đúng: C

Câu 29. Trong ACID, tính bền vững (Durability) nói đến điều gì?
A. Mọi truy vấn đều chạy trên một bản sao dữ liệu tạm thời.
B. Mọi thao tác đọc phải nhìn thấy thay đổi chưa commit ngay.
C. Kết quả đã commit phải tồn tại qua các sự cố được bảo vệ.
D. Mọi transaction phải kết thúc trong một khoảng thời gian cố định.
Đáp án đúng: C

Câu 30. Khi cần hủy các thay đổi chưa commit trong một giao dịch, dùng gì?
A. ROLLBACK để hoàn tác các thay đổi chưa xác nhận.
B. GRANT để thay đổi quyền chạy của transaction hiện tại.
C. SELECT để tải lại dữ liệu và tự hủy các lệnh đã ghi.
D. COMMIT để ghi nhận các thay đổi đang chờ xác nhận.
Đáp án đúng: A

Câu 31. Hiện tượng dirty read xảy ra trong trường hợp nào?
A. Giao dịch đọc lại cùng hàng sau khi giao dịch khác commit.
B. Giao dịch đọc thay đổi của giao dịch khác chưa commit.
C. Giao dịch nhận thêm hàng mới thỏa điều kiện khi truy vấn lại.
D. Giao dịch đọc dữ liệu đã được commit trước khi bắt đầu.
Đáp án đúng: B

Câu 32. Non-repeatable read là hiện tượng nào khi cùng một giao dịch đọc lại dữ liệu?
A. Một giao dịch đọc được dữ liệu mới chưa commit từ phiên khác.
B. Một hàng chỉ được ghi lại trong chính giao dịch đang đọc.
C. Một câu truy vấn dùng chỉ mục mới nên đổi thời gian chạy.
D. Một hàng đã đọc có giá trị đổi do giao dịch khác commit.
Đáp án đúng: D

Câu 33. Phantom read là hiện tượng nào khi thực hiện lại truy vấn theo điều kiện?
A. Truy vấn thấy dữ liệu chưa commit được chèn bởi transaction khác.
B. Truy vấn đọc lại cùng hàng nhưng sắp xếp cột theo thứ tự khác.
C. Tập hàng thỏa điều kiện thay đổi do giao dịch khác commit.
D. Giá trị một hàng có sẵn bị thay nhưng không thêm hay bớt hàng.
Đáp án đúng: C

Câu 34. Trong hệ thống nhiều giao dịch đồng thời, khóa có vai trò chủ yếu nào?
A. Điều phối truy cập xung đột để bảo vệ tính nhất quán dữ liệu.
B. Thay mọi quy tắc kiểm tra kiểu dữ liệu của các cột.
C. Ngăn mọi phiên kết nối chạy truy vấn chỉ đọc với cơ sở dữ liệu.
D. Tự xóa các thay đổi bị lỗi từ mọi transaction đã commit.
Đáp án đúng: A

Câu 35. Khi hai giao dịch chờ tài nguyên do nhau giữ theo vòng, hiện tượng gì xảy ra?
A. Cache miss do dữ liệu chưa được nạp vào bộ nhớ truy vấn.
B. Deadlock do tồn tại vòng chờ giữa các giao dịch.
C. Dirty read do truy vấn đọc dữ liệu chưa được commit.
D. Phantom read do xuất hiện hàng mới trong một câu SELECT.
Đáp án đúng: B

Câu 36. Chỉ mục B-tree thường giúp cải thiện tình huống truy vấn nào?
A. Tăng tốc mọi câu INSERT mà không làm phát sinh chi phí.
B. Loại bỏ nhu cầu lưu bảng gốc khi cần truy vấn dữ liệu.
C. Lấy toàn bộ hàng của bảng nhỏ không có điều kiện lọc.
D. Lọc theo khóa chọn lọc hoặc điều kiện khoảng giá trị.
Đáp án đúng: D

Câu 37. Với chỉ mục ghép (customer_id, created_at), truy vấn nào thường có lợi thế?
A. Chỉ lọc created_at mà không có customer_id.
B. Chỉ lọc product_id không thuộc hai cột chỉ mục.
C. Chỉ lọc status không thuộc hai cột chỉ mục.
D. Lọc customer_id rồi giới hạn khoảng created_at.
Đáp án đúng: D

Câu 38. Khác biệt khái quát giữa cơ sở dữ liệu quan hệ và document là gì?
A. Quan hệ không tạo chỉ mục; document chỉ dùng chỉ mục khóa.
B. Quan hệ chỉ lưu chuỗi; document chỉ lưu dữ liệu số.
C. Quan hệ tổ chức bảng; document lưu các tài liệu có cấu trúc.
D. Quan hệ luôn không hỗ trợ giao dịch; document luôn hỗ trợ.
Đáp án đúng: C

Câu 39. Trong lựa chọn OLTP và kho dữ liệu phục vụ phân tích, nhận định nào phù hợp?
A. OLTP không cần chuẩn hóa; kho dữ liệu không dùng các phép tổng hợp.
B. OLTP chỉ lưu dữ liệu tạm; kho dữ liệu chỉ lưu dữ liệu mới nhất.
C. OLTP chủ yếu chạy báo cáo lịch sử; kho dữ liệu ưu tiên ghi từng đơn.
D. OLTP tối ưu giao dịch thường xuyên; kho dữ liệu thiên về phân tích.
Đáp án đúng: D

Câu 40. Nguyên tắc nào phù hợp khi kết nối và vận hành cơ sở dữ liệu cho ứng dụng?
A. Tái sử dụng kết nối, giới hạn quyền và kiểm tra khả năng phục hồi.
B. Tạo kết nối mới mỗi câu SQL và lưu mật khẩu trong nhật ký.
C. Cấp quyền quản trị cho mọi dịch vụ và chỉ dựa vào bộ nhớ cache.
D. Tắt mọi timeout và bỏ sao lưu vì dữ liệu đã được commit.
Đáp án đúng: A
