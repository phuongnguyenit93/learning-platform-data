Câu 1. Khi mã khách hàng có khoảng trắng thừa và khác biệt chữ hoa, bước nào giúp gom nhóm nhất quán?
A. Chuẩn hóa trim và kiểu chữ theo quy tắc
B. Chuyển mọi mã khách hàng thành số nguyên
C. Chỉ sắp xếp các mã theo thứ tự nhập liệu
D. Xóa tất cả mã xuất hiện nhiều hơn một lần
Đáp án đúng: A

Câu 2. Trong pipeline tính doanh thu từ các giao dịch hợp lệ, filter nên thực hiện nhiệm vụ nào?
A. Biến tất cả giá trị doanh thu thành một hằng số
B. Giữ bản ghi thỏa điều kiện hợp lệ đã nêu
C. Tạo kết quả gộp cho toàn bộ trường doanh thu
D. Sắp xếp kết quả cuối mà không loại bản ghi
Đáp án đúng: B

Câu 3. Với Stream<List<Item>>, muốn tạo Stream<Item> gồm các phần tử bên trong, chọn phép nào?
A. map(List::size) để lấy từng độ dài danh sách
B. filter(List::isEmpty) để bỏ danh sách không rỗng
C. distinct() để loại toàn bộ danh sách trùng nhau
D. flatMap(List::stream) để trải các phần tử
Đáp án đúng: D

Câu 4. Trong Java Stream API, điều gì xảy ra khi chạy hai terminal operation trên cùng một stream?
A. Stream đã tiêu thụ không thể chạy lần nữa
B. Stream tự tính lại nguồn dữ liệu ở lần thứ hai
C. Hai terminal operation luôn tự chạy song song
D. Stream được sao chép sâu cho thao tác lần sau
Đáp án đúng: A

Câu 5. Muốn đếm số đơn hàng theo trạng thái bằng Java Stream, collector nào phù hợp?
A. mapping() để đổi mỗi trạng thái thành đối tượng
B. joining() để nối mọi trạng thái thành một chuỗi
C. groupingBy(status, counting()) để nhóm và đếm
D. averagingInt() để lấy trung bình mã trạng thái
Đáp án đúng: C

Câu 6. Dùng Collectors.toMap(keyFn, valueFn) khi hai phần tử có cùng khóa, điều gì cần lưu ý?
A. Java luôn giữ giá trị đến sau mà không báo lỗi
B. Mặc định có thể lỗi, cần xác định hàm gộp
C. Java luôn tự tạo một danh sách cho mỗi khóa
D. Hai phần tử tự động được loại khi trùng khóa
Đáp án đúng: B

Câu 7. Với phép inner join giữa bảng A và B theo mã, bản ghi nào xuất hiện trong kết quả?
A. Mọi bản ghi A, kể cả mã không có trong B
B. Mọi bản ghi B, kể cả mã không có trong A
C. Chỉ các cặp bản ghi khớp điều kiện join
D. Mỗi bản ghi có mã null ở một trong hai bảng
Đáp án đúng: C

Câu 8. Với left join từ bảng A sang B, chuyện gì xảy ra khi một mã của A không có ở B?
A. Bản ghi A bị loại khỏi kết quả giống inner join
B. Bản ghi B được tạo từ mã gần giống nhất trong A
C. Cả hai bảng bị loại phần tử có mã không khớp
D. Bản ghi A vẫn có, phần thông tin B bị thiếu
Đáp án đúng: D

Câu 9. Khi join dữ liệu hai nguồn, vấn đề nào có thể làm số bản ghi kết quả tăng ngoài dự kiến?
A. Thực hiện phép lọc trước khi join dữ liệu
B. Khóa join không duy nhất ở cả hai nguồn
C. Chuẩn hóa khoảng trắng của khóa theo quy tắc
D. Đánh dấu rõ kiểu dữ liệu của từng cột đầu vào
Đáp án đúng: B

Câu 10. Với reduce() trong parallel stream, tính chất nào của hàm kết hợp là quan trọng nhất?
A. Phép gộp cần có tính kết hợp (associative)
B. Hàm kết hợp phải thay đổi phần tử đầu vào
C. Hàm kết hợp phải dùng một biến đếm global
D. Hàm kết hợp chỉ được gọi đúng một lần duy nhất
Đáp án đúng: A

Câu 11. Trong Java Stream, cặp thao tác nào có thể cần ghi nhớ trạng thái của nhiều phần tử?
A. map() và filter() trên từng phần tử nguồn
B. peek() và map() trên từng phần tử nguồn
C. filter() và map() với hàm biến đổi thuần
D. sorted() và distinct() có lưu trạng thái
Đáp án đúng: D

Câu 12. Với pipeline stream chỉ gồm map() và filter(), khi nào các phép này thường được thực thi?
A. Khi terminal operation tiêu thụ luồng
B. Ngay khi gọi map() dù không có terminal operation
C. Chỉ khi toàn bộ collection nguồn được sửa đổi
D. Khi tạo đối tượng stream nhưng chưa gọi terminal
Đáp án đúng: A

Câu 13. Dùng parallelStream().forEach() để ghi kết quả vào danh sách, nguy cơ nào cần tính đến?
A. forEach tự bảo đảm thứ tự như nguồn đầu vào
B. forEach mặc định biến danh sách thành immutable
C. Thứ tự không đảm bảo và đích ghi phải an toàn
D. Mỗi phần tử luôn được xử lý trong một thread riêng
Đáp án đúng: C

Câu 14. Trường hợp nào khiến chuyển stream sang parallel có thể chậm hơn sequential?
A. Tác vụ tính nặng và dữ liệu có đủ nhiều phần tử
B. Dữ liệu quá ít so với chi phí chia và gộp
C. Hàm xử lý thuần và chia đều giữa các worker
D. Tổng hợp dữ liệu dùng phép gộp có tính kết hợp
Đáp án đúng: B

Câu 15. Điểm khác biệt đặc trưng giữa batch processing và streaming là gì?
A. Batch không thể biến đổi dữ liệu sau khi đã lọc
B. Streaming chỉ xử lý dữ liệu sau khi kết thúc ngày
C. Batch xử lý tập hữu hạn, streaming nhận dòng liên tục
D. Streaming không cần cơ chế phục hồi khi xử lý lỗi
Đáp án đúng: C

Câu 16. Event time khác processing time ở điểm nào trong pipeline sự kiện?
A. Event time luôn là lúc máy xử lý nhận bản ghi
B. Event time chỉ tồn tại ở luồng xử lý không phân tán
C. Processing time luôn chính xác như thời điểm phát sinh
D. Event time là thời điểm sự kiện tại nguồn
Đáp án đúng: D

Câu 17. Trong xử lý cửa sổ theo event time, watermark biểu thị điều gì?
A. Mọi sự kiện sau watermark sẽ không bao giờ bị trễ
B. Tất cả bản ghi trước watermark chắc chắn được lưu
C. Mức sử dụng bộ nhớ tối đa của mỗi cửa sổ trạng thái
D. Ngưỡng event time hệ thống ước lượng đã qua
Đáp án đúng: D

Câu 18. Cửa sổ tumbling dài 5 phút có đặc trưng nào?
A. Mỗi sự kiện luôn nằm đồng thời ở hai cửa sổ
B. Các cửa sổ chạy theo từng phiên người dùng
C. Cửa sổ cố định liên tiếp và không chồng lấp
D. Mỗi cửa sổ chỉ kết thúc khi có sự kiện kết phiên
Đáp án đúng: C

Câu 19. Với sliding window dài 10 phút, bước trượt 2 phút, nhận định nào đúng?
A. Các cửa sổ không thể chứa chung một sự kiện
B. Một sự kiện có thể nằm trong nhiều cửa sổ
C. Mỗi cửa sổ chỉ chứa các sự kiện đúng 2 phút
D. Mỗi sự kiện được tự động gộp thành một bản ghi
Đáp án đúng: B

Câu 20. Một event đến sau khi cửa sổ đã đóng theo watermark; pipeline cần quyết định gì?
A. Coi event là hợp lệ và luôn thay lại mọi kết quả
B. Bỏ kiểm tra thời gian và chuyển sang batch mode
C. Chọn chính sách xử lý dữ liệu đến trễ
D. Đổi event time thành thời điểm ghi file đầu tiên
Đáp án đúng: C

Câu 21. Trong streaming, backpressure được dùng để xử lý tình trạng nào?
A. Phía tiêu thụ chậm hơn tốc độ phía phát dữ liệu
B. Khóa join bị trùng giữa hai nguồn dữ liệu nhỏ
C. Cửa sổ event time có số phút là số nguyên lẻ
D. Phép reduce có hàm kết hợp không mang tính thuần
Đáp án đúng: A

Câu 22. Pipeline có cơ chế at-least-once, khi ghi sang hệ thống ngoài cần chú ý gì?
A. Mỗi event chắc chắn chỉ được ghi đúng một lần
B. Mọi sink đều tự xử lý trùng lặp dù không cấu hình
C. Retry luôn bảo đảm không tạo tác dụng phụ mới
D. Dùng khóa idempotency để hạn chế ghi lặp
Đáp án đúng: D

Câu 23. Để khôi phục aggregate state sau worker bị lỗi, cơ chế nào hữu ích?
A. Chỉ lưu kết quả trong biến local của thread
B. Checkpoint state và tiến độ nguồn nhất quán
C. Tắt mọi retry và bỏ các event chưa được xử lý
D. Xóa khóa partition trước khi khởi động lại job
Đáp án đúng: B

Câu 24. Sau khi chuyển pipeline từ batch sang streaming, cách kiểm chứng kết quả nào phù hợp?
A. Đối chiếu tổng hợp trên cùng bộ dữ liệu kiểm thử
B. Chỉ đếm số dòng code của pipeline mới và cũ
C. Bỏ qua bản ghi đến trễ để mọi thống kê dễ tính
D. Chỉ so độ trễ một event thay cho toàn bộ kết quả
Đáp án đúng: A
