1. Nhóm sản phẩm yêu cầu mỗi khách có thể có nhiều địa chỉ nhưng tối đa một địa chỉ mặc định. Mô hình cần thể hiện gì?
A. Đặt cờ mặc định trên khách và không lưu cờ trên địa chỉ.
B. Quan hệ một-nhiều với tối đa một địa chỉ mặc định mỗi khách.
C. Chỉ cho mỗi khách một địa chỉ qua khóa ngoại duy nhất.
D. Dùng quan hệ nhiều-nhiều và chọn địa chỉ mặc định khi đọc.
Đáp án đúng: B

2. Lớp học và học viên có quan hệ nhiều-nhiều; mỗi lượt đăng ký có ngày và trạng thái. Thiết kế logic nào phù hợp?
A. Tạo bảng DangKy có khóa hai phía, ngày và trạng thái.
B. Bảng Lop lưu danh sách học viên kèm ngày và trạng thái.
C. Bảng HocVien chỉ lưu mã lớp cuối kèm ngày đăng ký.
D. Hai bảng nối bằng tên học viên và ngày đăng ký.
Đáp án đúng: A

3. Mỗi đơn hàng phải thuộc đúng một khách; một khách có thể chưa có đơn. Cách thể hiện quan hệ nào đúng?
A. Mỗi khách đúng một đơn và khóa khách hàng có thể NULL.
B. Mỗi đơn nhiều khách và khóa khách chứa nhiều giá trị.
C. FK khách tại đơn NOT NULL; khách có thể có 0-n đơn.
D. Mỗi khách phải có đơn và khóa khách ở đơn phải UNIQUE.
Đáp án đúng: C

4. Số dòng hàng được đánh 1, 2, 3 lại từ đầu trong mỗi hóa đơn. Khóa tự nhiên của dòng là gì?
A. Chỉ dùng số dòng vì số này tăng trong từng hóa đơn.
B. Kết hợp mã sản phẩm với số dòng của mỗi hóa đơn.
C. PK (ma_hoa_don, so_dong) cho mỗi dòng hóa đơn.
D. Chỉ dùng mã sản phẩm vì mã này đại diện mỗi dòng.
Đáp án đúng: C

5. Khách hàng có thể có nhiều số điện thoại, cần tìm theo từng số và không giới hạn số lượng. Nên thiết kế thế nào?
A. Bảng SoDienThoai gồm khóa khách và mỗi số một dòng.
B. Tạo phone1, phone2, phone3 trong mỗi bản ghi khách hàng.
C. Gộp tất cả số vào một chuỗi phân cách bằng dấu phẩy.
D. Dùng nhiều cột JSON để chia số theo từng nhóm thứ tự.
Đáp án đúng: A

6. Mã sản phẩm có thể thay đổi khi hợp nhất danh mục, nhưng quan hệ đơn hàng phải ổn định. Nên chọn khóa nào?
A. Dùng tên sản phẩm làm khóa và cập nhật theo tên mới.
B. Khóa chính ID nội bộ, mã sản phẩm có UNIQUE.
C. Dùng mã đang hiển thị làm khóa và bỏ ràng buộc UNIQUE.
D. Dùng ngày tạo làm khóa và chuyển mã sang bảng khác.
Đáp án đúng: B

7. Trong hệ thống đa tenant, project_id chỉ duy nhất bên trong mỗi tenant. Task cần tham chiếu Project ra sao?
A. FK ghép (tenant_id, project_id) từ Task tới Project.
B. Chỉ lưu project_id và khóa ngoại theo riêng mã dự án.
C. Chỉ lưu tenant_id rồi suy ra dự án từ tên công việc.
D. Lưu tên tenant và tên dự án, sau đó nối bằng chuỗi.
Đáp án đúng: A

8. Email tài khoản bắt buộc và không được trùng dù có khác biệt chữ hoa, chữ thường. Cách ràng buộc phù hợp?
A. Đặt UNIQUE trên email nguyên bản và cho phép email NULL.
B. Đặt NOT NULL trên email gốc nhưng không cần UNIQUE.
C. NOT NULL và UNIQUE trên email đã chuẩn hóa.
D. Chỉ kiểm tra ký tự @ và tạo INDEX không duy nhất cho email.
Đáp án đúng: C

9. Số lượng của một dòng đơn phải là số nguyên dương khi ghi vào cơ sở dữ liệu. Ràng buộc nào đủ?
A. INTEGER NOT NULL và CHECK(quantity > 0) trên dòng hàng.
B. Dùng DEFAULT 1 để tự sửa mọi giá trị không hợp lệ.
C. Dùng UNIQUE(quantity) để chặn giá trị âm và bằng không.
D. Dùng INDEX(quantity) để từ chối giá trị số không hợp lệ.
Đáp án đúng: A

10. Trong PostgreSQL, người dùng có thể có nhiều giỏ đã khóa nhưng chỉ một giỏ active. Nên cưỡng chế bằng gì?
A. UNIQUE INDEX trên user_id với WHERE status = 'active'.
B. UNIQUE(user_id) áp dụng cho tất cả giỏ hàng của người dùng.
C. INDEX(user_id,status) thường và không cần ràng buộc khác.
D. CHECK(status='active') áp dụng riêng trên từng bản ghi giỏ.
Đáp án đúng: A

11. Ứng dụng cần tính tuổi tại ngày xuất báo cáo, kể cả báo cáo cho những năm trước. Nên lưu dữ liệu nào?
A. Lưu tuổi hiện tại và tăng tuổi sau mỗi lần đăng nhập.
B. Lưu ngày sinh, tính tuổi dựa vào ngày tham chiếu báo cáo.
C. Lưu năm sinh và lấy năm xem báo cáo trừ năm sinh.
D. Lưu tuổi gần nhất và cập nhật khi chạy mỗi báo cáo.
Đáp án đúng: B

12. ChiTietDon có khóa ghép (don_id,san_pham_id), trong đó ten_san_pham chỉ phụ thuộc san_pham_id. Cách loại phụ thuộc bộ phận?
A. Thêm chỉ mục trên tên sản phẩm trong bảng ChiTietDon.
B. Tách tên khỏi ChiTietDon sang SanPham theo san_pham_id.
C. Thay khóa ghép bằng mã dòng nhưng giữ tên sản phẩm.
D. Lưu thêm tên sản phẩm tại bảng Don để giảm phép nối.
Đáp án đúng: B

13. Trong NhanVien, ma_nv xác định ma_phong và ma_phong xác định ten_phong. Cách loại phụ thuộc bắc cầu?
A. Thêm chỉ mục ma_phong và giữ ten_phong trong NhanVien.
B. Ghép ma_nv với ten_phong làm khóa chính của NhanVien.
C. Chép ten_phong sang bảng dự phòng rồi đồng bộ bằng lịch.
D. Tạo bảng Phong(ma_phong,ten_phong), nhân viên tham chiếu.
Đáp án đúng: D

14. Một quan hệ có phụ thuộc hàm X → Y nhưng X không là siêu khóa. Khi chuẩn hóa đến BCNF, cần làm gì?
A. Thêm chỉ mục trên X để tăng tốc kiểm tra phụ thuộc hàm.
B. Phân rã để mọi vế xác định của phụ thuộc là siêu khóa.
C. Thêm ID thay thế để X không còn xác định được giá trị Y.
D. Đặt NOT NULL cho Y trước khi khai báo một khóa thay thế.
Đáp án đúng: B

15. Mỗi đơn hàng có thể dùng nhiều khuyến mại, một khuyến mại áp dụng cho nhiều đơn; mức giảm lưu theo lượt áp dụng. Mô hình nào?
A. Lưu danh sách mã và mức giảm trong một cột của DonHang.
B. Chỉ lưu một ma_khuyen_mai và mức giảm tại DonHang.
C. Bảng Don_KhuyenMai ghi cặp khóa và mức giảm.
D. Lưu danh sách mã đơn và mức giảm ngay trong KhuyenMai.
Đáp án đúng: C

16. JOIN DonHang với ChiTietDon làm một đơn xuất hiện nhiều lần. Muốn đếm số đơn theo khách, nên dùng gì?
A. COUNT(DISTINCT don_id) theo từng khách sau khi JOIN.
B. COUNT(*) theo từng khách vì mỗi dòng là một đơn hàng.
C. SUM(so_luong) theo từng khách vì mỗi món là một đơn.
D. COUNT(customer_id) sau JOIN vì mã khách chỉ xuất hiện một lần.
Đáp án đúng: A

17. Kho dữ liệu phải biết phân khúc khách tại thời điểm bán dù phân khúc đã thay đổi. Phương án nào thích hợp?
A. Ghi đè phân khúc cũ bằng phân khúc mới trên dimension.
B. SCD Type 2 với khoảng ngày hiệu lực cho mỗi phân khúc.
C. Chỉ giữ phân khúc hiện tại ở bảng khách hàng của OLTP.
D. Tính lại phân khúc mới cho toàn bộ giao dịch lúc báo cáo.
Đáp án đúng: B

18. Dashboard thường tổng hợp doanh thu theo ngày, cửa hàng và sản phẩm trên lượng giao dịch rất lớn. Schema nào hợp lý?
A. Dồn mọi thuộc tính của giao dịch vào một bảng OLTP lớn.
B. Chuẩn hóa mọi dimension thành nhiều lớp bảng rất nhỏ.
C. Gom các giao dịch vào một tệp JSON riêng cho mỗi cửa hàng.
D. Fact giao dịch nối dimension ngày, cửa hàng, sản phẩm.
Đáp án đúng: D

19. Một đơn có nhiều dòng hàng; đội phân tích cần tổng hợp doanh thu không đếm trùng. Phải xác định điều gì trước?
A. Khóa thay thế của dimension khách phải đặt trước mọi việc.
B. Grain của fact là một bản ghi đại diện cho mỗi khách.
C. Grain của fact là một bản ghi duy nhất cho mỗi sản phẩm.
D. Grain của fact là một dòng hàng trong mỗi đơn hàng.
Đáp án đúng: D

20. Báo cáo có dữ liệu doanh thu theo giờ và theo ngày. Làm sao tránh đếm hai lần khi tổng hợp?
A. Chọn grain nhất quán, chỉ cộng các khoảng không chồng lặp.
B. Lưu tổng ngày và tổng tháng trong một fact rồi cộng tất cả.
C. JOIN fact giờ với fact ngày và SUM cả hai nguồn doanh thu.
D. Lưu số tích lũy theo ngày và cộng các dòng số tích lũy.
Đáp án đúng: A

21. Truy vấn thường lọc tenant_id bằng dấu bằng, lọc created_at theo khoảng và ORDER BY created_at. B-tree nào hợp lý?
A. Index (created_at, tenant_id) luôn tối ưu vì thời gian đứng đầu.
B. Index (status, created_at) dù câu truy vấn không dùng status.
C. Index (tenant_id,created_at) để lọc và sắp xếp thời gian.
D. Index (tenant_id, status) để tự sắp xếp theo created_at.
Đáp án đúng: C

22. Truy vấn đọc status bằng customer_id nhiều lần và cần giảm việc tìm lại bảng dữ liệu. Covering index giúp thế nào?
A. Chỉ đánh index trên status rồi đọc customer_id từ bảng.
B. Chỉ index customer_id và luôn truy cập bảng lấy status.
C. Sao chép toàn bộ bảng sang một bản phụ để thực hiện truy vấn.
D. Dùng customer_id làm key và mang theo status trong chỉ mục.
Đáp án đúng: D

23. Một bảng có hàng nghìn lượt ghi mỗi giây; nhóm định thêm nhiều chỉ mục để tăng tốc đọc. Đánh đổi chính là gì?
A. Tốn thêm chi phí ghi và dung lượng lưu chỉ mục.
B. INSERT nhanh hơn vì hệ quản trị không phải cập nhật index.
C. Tất cả truy vấn chắc chắn giảm CPU khi có thêm nhiều index.
D. Khóa ngoại có thể ngừng hoạt động nếu số index tăng cao.
Đáp án đúng: A

24. Bảng log xóa dữ liệu quá 12 tháng theo từng tháng và thường truy vấn theo created_at. Cách phân vùng nào phù hợp?
A. Range partition theo created_at để bỏ phân vùng hết hạn.
B. Hash partition theo user_id rồi xóa thủ công từng log cũ.
C. Giữ một bảng lớn, chỉ tạo B-tree index trên ngày tạo.
D. List partition theo trạng thái rồi xóa theo trạng thái log.
Đáp án đúng: A

25. Trong PostgreSQL, chỉ 3% ticket có status open và truy vấn chủ yếu tìm ticket open theo assignee_id. Index nào gọn?
A. Index toàn bảng trên assignee_id cho tất cả trạng thái.
B. Index toàn bảng trên created_at dù không lọc theo ngày.
C. Index toàn bảng trên status dù vẫn phải lọc assignee_id.
D. Partial index trên assignee_id với WHERE status = 'open'.
Đáp án đúng: D

26. Đã thêm chỉ mục nhưng truy vấn vẫn chậm. Cần loại bằng chứng nào để biết chỉ mục được sử dụng và tốn thời gian ở đâu?
A. Đếm toàn bộ cột đang có chỉ mục trong cấu trúc bảng.
B. Kiểm tra migration đã chứa lệnh CREATE INDEX hay chưa.
C. Đo tốc độ đọc đĩa chung mà không chạy câu truy vấn.
D. EXPLAIN ANALYZE cho biết scan, thời gian và số hàng thực.
Đáp án đúng: D

27. Đơn hàng tham chiếu customer_id không có trong bảng KhachHang. DB nên chặn trạng thái này bằng gì?
A. INDEX(customer_id) trên đơn mà không khai báo tham chiếu.
B. UNIQUE(customer_id) trên đơn để ngăn mã khách không tồn tại.
C. FOREIGN KEY(customer_id) tham chiếu khách hàng tồn tại.
D. CHECK(customer_id > 0) để ngăn mã khách không tồn tại.
Đáp án đúng: C

28. Chứng từ hóa đơn phải được giữ khi tài khoản khách ngừng hoạt động. Xóa hồ sơ khách đang được tham chiếu nên xử lý thế nào?
A. RESTRICT xóa khách còn hóa đơn; giữ trạng thái ngừng dùng.
B. CASCADE xóa toàn bộ hóa đơn khi xóa hồ sơ khách hàng.
C. SET NULL mọi mã khách trên hóa đơn khi đóng tài khoản.
D. Tắt FOREIGN KEY để xóa khách mà không xử lý hóa đơn.
Đáp án đúng: A

29. Giá tiền phải cộng chính xác với hai chữ số sau dấu thập phân. Kiểu dữ liệu SQL nào phù hợp?
A. FLOAT vì mọi phép cộng đều chính xác đến từng đồng.
B. DOUBLE vì kiểu số thực không tạo ra lỗi làm tròn.
C. VARCHAR vì phép cộng chuỗi có thể thực hiện ở ứng dụng.
D. Dùng DECIMAL(p,2) với độ chính xác đủ cho tiền.
Đáp án đúng: D

30. Ứng dụng nhiều quốc gia cần so sánh thời điểm giao dịch qua các múi giờ. Cách lưu nào phù hợp?
A. Chỉ lưu giờ địa phương dạng chuỗi mà không có offset.
B. Chỉ lưu ngày và giờ theo múi giờ mặc định của máy chủ.
C. Lưu thời điểm chuẩn hóa UTC rồi đổi múi giờ khi hiển thị.
D. Lưu tên thành phố thay cho thời điểm thực hiện giao dịch.
Đáp án đúng: C

31. Trong document DB, Order có ít line item và chúng luôn được đọc, cập nhật cùng Order. Cách tổ chức nào hợp lý?
A. Tách từng line item thành collection chỉ để truy xuất riêng.
B. Nhúng các line item vào document Order theo cùng aggregate.
C. Gộp toàn bộ order của ngày vào chung một document lớn.
D. Sao chép line item vào document Customer thay cho Order.
Đáp án đúng: B

32. Tên sản phẩm được sao chép vào nhiều document đặt hàng để hiển thị nhanh và phải cập nhật khi đổi tên. Đánh đổi của denormalization là gì?
A. Mọi bản sao tự nhất quán mà không cần bước đồng bộ.
B. Thao tác ghi luôn ít tốn tài nguyên hơn thiết kế tham chiếu.
C. Đọc thuận tiện hơn nhưng cần quy trình cập nhật các bản sao.
D. Kiểm tra nhất quán giữa các document hoàn toàn không cần thiết.
Đáp án đúng: C

33. Bình luận của bài viết tăng không giới hạn nhưng mỗi lần mở chỉ lấy 20 bình luận mới nhất. Thiết kế document phù hợp?
A. Nhúng tất cả bình luận vào một document bài viết duy nhất.
B. Nhúng toàn bộ bình luận và luôn tải hết khi mở bài viết.
C. Tách collection Comment và truy vấn theo bài với phân trang.
D. Sao chép mọi bình luận vào từng document của người đọc.
Đáp án đúng: C

34. Sản phẩm thường cần tìm đường quan hệ ngắn nhất qua nhiều cấp giữa người dùng. Mô hình nào tự nhiên nhất?
A. Key-value chỉ lưu hồ sơ từng người dùng mà không có cạnh.
B. Document duy nhất chứa tất cả hồ sơ và mọi mối quan hệ.
C. Bảng tổng hợp số người dùng theo thành phố và độ tuổi.
D. Property graph với node người dùng và edge quan hệ.
Đáp án đúng: D

35. Truy vấn OLAP chỉ đọc vài cột rồi tổng hợp hàng trăm triệu bản ghi. Kiểu lưu trữ nào có lợi thế rõ?
A. Row storage luôn nhanh hơn vì đọc đủ toàn bộ bản ghi.
B. Columnar storage cho phép chỉ quét cột cần phân tích.
C. Key-value theo ID giúp SUM dữ liệu toàn bảng ít tốn I/O.
D. Graph adjacency tự tối ưu mọi phép tổng hợp doanh thu.
Đáp án đúng: B

36. Chọn mô hình SQL, document hoặc graph cho sản phẩm mới nên dựa chủ yếu vào yếu tố gì?
A. Loại cơ sở dữ liệu đã quen thuộc với nhiều người nhất.
B. Mẫu truy vấn, cách cập nhật, nhất quán và quy mô dữ liệu.
C. Mức độ dễ thêm trường mới trong ngày thử nghiệm đầu.
D. Số kiểu dữ liệu engine hỗ trợ dù không cần cho nghiệp vụ.
Đáp án đúng: B

37. Cần đổi tên cột được cả ứng dụng cũ và mới sử dụng, nhưng không thể ngừng phục vụ. Cách migrate nào an toàn?
A. Xóa cột cũ trước rồi triển khai lần lượt ứng dụng mới.
B. Đổi tên cột trực tiếp và để ứng dụng cũ tự xử lý lỗi.
C. Khóa mọi thao tác ghi cho đến khi tất cả client nâng cấp.
D. Thêm cột, backfill, đồng bộ, chuyển client rồi bỏ cột cũ.
Đáp án đúng: D

38. Cần backfill 50 triệu dòng mà không được khóa bảng lâu hoặc gây quá tải dịch vụ. Phương án nào hợp lý?
A. Chạy một UPDATE lớn quét cả bảng vào giờ cao điểm.
B. Chạy các batch nhỏ, checkpoint tiến độ và theo dõi tải.
C. Dừng toàn bộ truy vấn trước khi thực hiện một giao dịch lớn.
D. Xóa trước dữ liệu rồi nạp lại toàn bộ sau khi backfill.
Đáp án đúng: B

39. Trước khi triển khai, muốn kiểm chứng quy tắc mỗi khách tối đa một địa chỉ mặc định. Tình huống thử nào mạnh nhất?
A. Kiểm tra mọi tên bảng đều nhất quán với coding style.
B. Xem sơ đồ quan hệ có rõ ràng trên tài liệu thiết kế.
C. Thử thêm hai địa chỉ mặc định cho một khách và đòi lỗi.
D. Tạo hai khách có địa chỉ mặc định khác nhau rồi đọc lại.
Đáp án đúng: C

40. API đang được nhiều client cũ sử dụng, cần thêm trường mới cho schema dữ liệu trả về. Cách thay đổi nào hợp lý?
A. Đổi tên toàn bộ field cũ để các client nâng cấp ngay.
B. Bắt client cũ nhận schema mới trước khi triển khai phiên bản.
C. Xóa tài liệu schema vì client có thể tự suy đoán thay đổi.
D. Thêm field tùy chọn tương thích, giữ field cũ cho client.
Đáp án đúng: D
