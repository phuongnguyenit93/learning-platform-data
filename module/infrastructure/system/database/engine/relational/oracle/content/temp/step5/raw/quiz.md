Câu 01. Trong kiến trúc Oracle, một database instance gồm những thành phần chính nào?
A. Các datafile cùng control file và các online redo log trên đĩa.
B. Các tablespace cùng mọi schema và đối tượng thuộc người dùng.
C. Những PDB và các file sao lưu độc lập của từng ứng dụng.
D. Vùng nhớ SGA cùng các tiến trình nền để vận hành database.
Đáp án đúng: D

Câu 02. Phân biệt Oracle instance và Oracle database nào là đúng?
A. Instance là bộ nhớ và tiến trình; database gồm các tệp lưu trữ.
B. Instance là một PDB; database chỉ là danh mục tablespace của PDB.
C. Instance là tập datafile; database chỉ là bộ nhớ cache của SQL.
D. Instance là các bảng ứng dụng; database là những tài khoản đăng nhập.
Đáp án đúng: A

Câu 03. Shared Pool của Oracle chủ yếu hỗ trợ loại dữ liệu nào?
A. Các bản ghi redo đã commit nhưng chưa kịp ghi ra redo log.
B. Các cấu trúc SQL đã phân tích và thông tin từ data dictionary.
C. Các phiên bản row cũ đang được lưu tạm để hỗ trợ rollback.
D. Các block dữ liệu bảng đã đọc vào RAM và đang chờ ghi xuống đĩa.
Đáp án đúng: B

Câu 04. Database Buffer Cache trong SGA được dùng chủ yếu để làm gì?
A. Lưu bản sao mọi archive log để phục hồi từng thời điểm quá khứ.
B. Ghi toàn bộ câu SQL của session thành nhật ký cho bộ tối ưu.
C. Giữ bản sao block dữ liệu được đọc hoặc chỉnh sửa trong bộ nhớ.
D. Lưu vĩnh viễn các block dữ liệu khi chưa có datafile trên đĩa.
Đáp án đúng: C

Câu 05. Tiến trình LGWR trong Oracle chịu trách nhiệm chính cho việc gì?
A. Sao chép control file thành các bản backup định kỳ trên đĩa.
B. Ghi các block dữ liệu bẩn từ cache xuống các datafile.
C. Ghi redo từ redo log buffer xuống các online redo log.
D. Thu hồi phân đoạn undo đã hết hạn trong các tablespace.
Đáp án đúng: C

Câu 06. Undo data trong Oracle phục vụ mục đích nào của giao dịch?
A. Tự tạo chỉ mục bổ sung khi câu SQL lọc nhiều dòng dữ liệu.
B. Ghi lại toàn bộ kết quả truy vấn để đọc lại mà không chạy SQL.
C. Giữ bản sao online redo log để phục hồi sau sự cố mất điện.
D. Hỗ trợ rollback và cung cấp phiên bản cũ cho đọc nhất quán.
Đáp án đúng: D

Câu 07. Trong mô hình multitenant, mối quan hệ CDB và PDB nào là đúng?
A. Một PDB chứa nhiều CDB và chia sẻ các datafile của mọi CDB.
B. Mỗi schema là một CDB và chỉ được gắn với một bảng dữ liệu.
C. Một CDB chứa các PDB, mỗi PDB có không gian schema riêng.
D. Mỗi CDB chỉ có một schema và không hỗ trợ nhiều PDB.
Đáp án đúng: C

Câu 08. Local user trong một Oracle PDB thường có phạm vi nào?
A. Tài khoản được tạo và quản lý trong PDB tương ứng.
B. Tài khoản bắt buộc tồn tại đồng thời ở mọi PDB của CDB.
C. Tài khoản mặc định có quyền quản trị toàn bộ các PDB.
D. Tài khoản chỉ có thể được tạo từ root của mọi CDB.
Đáp án đúng: A

Câu 09. Tablespace trong Oracle được hiểu như thế nào?
A. Vùng bộ nhớ lưu tất cả con trỏ đang mở của một session.
B. Tập hợp các quyền truy cập được gán cho một database role.
C. Tiến trình nền chịu trách nhiệm ghi mọi redo log sau commit.
D. Đơn vị lưu trữ logic được ánh xạ xuống một hoặc nhiều datafile.
Đáp án đúng: D

Câu 10. Trong Oracle, schema thuộc về đối tượng nào?
A. Tài khoản người dùng sở hữu các bảng, view và đối tượng khác.
B. Mỗi datafile có một schema riêng độc lập với tài khoản tạo.
C. Một instance luôn sở hữu đúng một schema cho mọi ứng dụng.
D. Mỗi tablespace mặc định là một schema cùng tên trên database.
Đáp án đúng: A

Câu 11. Ràng buộc PRIMARY KEY có ý nghĩa nào cho một bảng Oracle?
A. Tự xác nhận khóa của từng dòng bằng một bảng tham chiếu.
B. Bảo đảm các giá trị khóa duy nhất và không được NULL.
C. Cho phép lặp khóa nhưng bắt buộc các giá trị không NULL.
D. Cho phép khóa NULL nhưng không cho phép hai giá trị trùng.
Đáp án đúng: B

Câu 12. Ràng buộc FOREIGN KEY trong Oracle thường kiểm soát điều gì?
A. Giá trị khóa bắt buộc duy nhất trong bảng chứa foreign key.
B. Giá trị khóa tham chiếu tới khóa hợp lệ ở bảng được tham chiếu.
C. Giá trị khóa được tự động tạo qua một sequence trên bảng.
D. Giá trị khóa luôn phải tăng dần sau mỗi câu lệnh INSERT.
Đáp án đúng: B

Câu 13. Khi dùng sequence.NEXTVAL để cấp ID, nhận định nào chính xác?
A. Giá trị sequence được hoàn trả lại khi transaction rollback.
B. Giá trị sequence luôn tăng đúng một đơn vị trên mọi phiên.
C. Giá trị sequence có thể bị nhảy số dù transaction rollback.
D. Giá trị sequence chỉ sinh được trong câu lệnh INSERT.
Đáp án đúng: C

Câu 14. Cột GENERATED AS IDENTITY trong Oracle thường giải quyết vấn đề nào?
A. Sinh giá trị nhận dạng cho cột theo quy tắc đã cấu hình.
B. Tự sao chép cột từ database khác vào mọi câu lệnh INSERT.
C. Tự tính khóa ngoại trỏ tới bản ghi mới nhất ở bảng khác.
D. Tự bảo đảm cột là khóa chính mà không cần định nghĩa constraint.
Đáp án đúng: A

Câu 15. Trong Oracle SQL, chuỗi rỗng '' được xử lý thế nào với VARCHAR2?
A. Chuỗi rỗng được tự chuyển thành một dấu cách trước khi so sánh.
B. Chuỗi có độ dài bằng không hiện được coi như giá trị NULL.
C. Chuỗi rỗng được chuyển thành chuỗi ký tự 'NULL' trong dữ liệu.
D. Chuỗi có độ dài bằng không luôn là một giá trị khác NULL.
Đáp án đúng: B

Câu 16. Sử dụng bind variable trong Oracle SQL mang lại lợi ích chính nào?
A. Bảo đảm mọi truy vấn đều chọn cùng execution plan tốt nhất.
B. Cho phép bỏ mọi kiểm tra quyền truy cập bảng trong database.
C. Giúp tái dùng SQL và tách giá trị tham số khỏi cú pháp lệnh.
D. Buộc database thực hiện full scan thay cho dùng chỉ mục có sẵn.
Đáp án đúng: C

Câu 17. Hàm phân tích ROW_NUMBER() OVER(PARTITION BY ... ORDER BY ...) làm gì?
A. Tạo các giá trị ID cố định được giữ sau mỗi lần đổi thứ tự.
B. Đánh số thứ tự dòng trong mỗi nhóm theo thứ tự được chỉ định.
C. Đếm tổng số dòng trong bảng rồi gán cùng kết quả cho mọi nhóm.
D. Loại các dòng trùng nhau trước khi áp dụng điều kiện lọc khác.
Đáp án đúng: B

Câu 18. Khi cần 10 bản ghi mới nhất, cách viết SQL nào có ý nghĩa phù hợp?
A. WHERE ROWNUM <= 10 ORDER BY created_at DESC trực tiếp.
B. ORDER BY created_at ASC FETCH FIRST 10 ROWS ONLY.
C. FETCH FIRST 10 ROWS ONLY ORDER BY created_at DESC.
D. ORDER BY created_at DESC FETCH FIRST 10 ROWS ONLY.
Đáp án đúng: D

Câu 19. Câu lệnh MERGE trong Oracle phù hợp với trường hợp nào?
A. Chỉ truy vấn dữ liệu từ bảng nguồn mà không thay đổi đích.
B. Cập nhật dòng đã khớp và chèn dòng mới khi chưa khớp.
C. Luôn xóa mọi dòng của bảng đích trước khi ghi dữ liệu mới.
D. Luôn chèn mọi dòng từ nguồn dù đã có dòng tương ứng ở đích.
Đáp án đúng: B

Câu 20. Một khối PL/SQL ẩn danh tối thiểu có thành phần nào bắt buộc?
A. Phần CREATE PROCEDURE để lưu khối thành đối tượng lâu dài.
B. Phần DECLARE bắt buộc khai báo ít nhất một biến đầu vào.
C. Phần EXCEPTION bắt buộc khai báo ít nhất một bộ xử lý lỗi.
D. Phần BEGIN ... END chứa các câu lệnh cần thực thi.
Đáp án đúng: D

Câu 21. Khai báo biến v_code employees.code%TYPE trong PL/SQL có ý nghĩa gì?
A. Biến lấy tên bảng làm schema mặc định của session hiện tại.
B. Biến tự đồng bộ dữ liệu khi employees.code được cập nhật.
C. Biến lấy kiểu dữ liệu theo kiểu của cột employees.code.
D. Biến có giá trị đầu bằng dữ liệu của employees.code đầu tiên.
Đáp án đúng: C

Câu 22. Trong PL/SQL, nhánh WHEN OTHERS trong phần EXCEPTION dùng để làm gì?
A. Xác nhận giao dịch khi mọi câu lệnh PL/SQL chạy thành công.
B. Thực hiện mọi truy vấn trước khi phần BEGIN được chạy.
C. Chỉ xử lý ngoại lệ NO_DATA_FOUND trong câu SELECT INTO.
D. Xử lý các ngoại lệ chưa được các nhánh trước bắt cụ thể.
Đáp án đúng: D

Câu 23. Với cursor FOR loop trong PL/SQL, Oracle tự thực hiện thao tác nào?
A. Chạy lại truy vấn từ đầu sau mỗi lần chuyển sang dòng kế.
B. Mở, fetch và đóng cursor theo vòng lặp đã khai báo.
C. Commit các thay đổi sau mỗi dòng mà vòng lặp đã duyệt.
D. Khóa tất cả dòng kết quả cho tới khi toàn bộ vòng lặp kết thúc.
Đáp án đúng: B

Câu 24. Vai trò của package specification trong PL/SQL là gì?
A. Tự động cấp quyền EXECUTE cho mọi schema cùng một database.
B. Chỉ lưu cấu hình của session và không chứa khai báo PL/SQL.
C. Chứa toàn bộ mã cài đặt bắt buộc của mọi thủ tục riêng tư.
D. Khai báo giao diện công khai mà package cung cấp cho bên gọi.
Đáp án đúng: D

Câu 25. Lệnh DDL thông thường trong Oracle ảnh hưởng gì tới transaction đang mở?
A. Được gộp với DML trước đó để ROLLBACK cả phần thay đổi schema.
B. Chỉ commit khi ứng dụng gọi COMMIT sau khi DDL thành công.
C. Tự rollback mọi DML trước đó nếu DDL thay đổi cấu trúc bảng.
D. Có implicit commit trước lúc Oracle thực thi lệnh DDL.
Đáp án đúng: D

Câu 26. ROLLBACK TO savepoint_name có tác dụng nào trong Oracle?
A. Phục hồi dữ liệu về snapshot của một lần backup trước đó.
B. Hoàn tác phần thay đổi sau savepoint trong transaction hiện tại.
C. Hoàn tác cả transaction và giải phóng mọi savepoint đã tạo.
D. Xác nhận các thay đổi trước savepoint và kết thúc giao dịch.
Đáp án đúng: B

Câu 27. Ở mức READ COMMITTED mặc định, Oracle bảo đảm điều nào?
A. Các giao dịch chỉ được chạy khi giao dịch trước đã commit.
B. Các truy vấn đọc luôn khóa hàng cho tới cuối giao dịch.
C. Mọi câu SQL cùng giao dịch luôn thấy một snapshot cố định.
D. Mỗi câu SQL đọc ảnh nhất quán của dữ liệu đã commit.
Đáp án đúng: D

Câu 28. Trong Oracle, SELECT ... FOR UPDATE thường dùng để làm gì?
A. Khóa các dòng được chọn cho tới khi giao dịch kết thúc.
B. Khóa toàn bộ schema để mọi giao dịch khác không thể đọc.
C. Chuyển truy vấn SELECT thành một lệnh INSERT mới vào bảng.
D. Ép bộ tối ưu chỉ sử dụng unique index trên điều kiện lọc.
Đáp án đúng: A

Câu 29. Khi Oracle phát hiện deadlock, kết quả điển hình là gì?
A. Tự xóa các hàng đang tranh chấp trước khi tiếp tục truy vấn.
B. Đưa lỗi ORA-00060 cho một câu lệnh tham gia vòng chờ khóa.
C. Tự commit mọi giao dịch tham gia vòng chờ khóa hiện tại.
D. Tự dừng toàn bộ instance để giải phóng tất cả khóa đang giữ.
Đáp án đúng: B

Câu 30. Trường hợp nào thường phù hợp với B-tree index trong Oracle?
A. Thay toàn bộ ràng buộc foreign key khi phát sinh thao tác ghi.
B. Tăng tốc mọi truy vấn không phụ thuộc điều kiện và lượng dữ liệu.
C. Lọc theo giá trị chọn lọc hoặc truy cập theo khoảng giá trị.
D. Lọc cột có rất ít giá trị trong bảng chỉ phục vụ phân tích.
Đáp án đúng: C

Câu 31. Bitmap index thường được cân nhắc cho môi trường nào?
A. Hệ thống OLTP cập nhật cùng lúc rất nhiều dòng nhỏ liên tục.
B. Kho phân tích ít ghi đồng thời với cột có ít giá trị phân biệt.
C. Bảng log ghi liên tục và nhiều transaction thay cùng một khóa.
D. Bảng thay đổi liên tục với cột có giá trị gần như duy nhất.
Đáp án đúng: B

Câu 32. Với index ghép (customer_id, created_at), trường hợp nào có lợi thế rõ ràng?
A. Chỉ sắp xếp theo amount mà không lọc customer_id.
B. Chỉ lọc theo created_at và bỏ qua điều kiện customer_id.
C. Lọc customer_id rồi giới hạn theo khoảng created_at.
D. Chỉ lọc theo product_id mà không dùng hai cột của index.
Đáp án đúng: C

Câu 33. Function-based index trên UPPER(email) có thể hỗ trợ truy vấn nào?
A. Điều kiện WHERE UPPER(email) = :email_normalized.
B. Điều kiện WHERE salary > :minimum_salary.
C. Điều kiện WHERE created_at >= :start_date.
D. Điều kiện WHERE LENGTH(phone) = :phone_length.
Đáp án đúng: A

Câu 34. Trong Oracle, thống kê của bảng và index hỗ trợ optimizer ở việc gì?
A. Ước lượng số dòng và chi phí để lựa chọn execution plan.
B. Thay thế dữ liệu thực bằng thống kê trong mọi câu SELECT.
C. Tự động tạo index cho toàn bộ điều kiện trong ứng dụng.
D. Bỏ mọi ràng buộc khóa ngoại để đơn giản hóa thực thi.
Đáp án đúng: A

Câu 35. Để xem execution plan của SQL cursor đang được lưu, nên dùng công cụ nào?
A. DBMS_OUTPUT.PUT_LINE với câu SQL đang chạy.
B. DBMS_METADATA.GET_DDL với tên bảng phù hợp.
C. DBMS_XPLAN.DISPLAY_CURSOR với SQL_ID phù hợp.
D. DBMS_STATS.GATHER_TABLE_STATS với tên bảng.
Đáp án đúng: C

Câu 36. Nguyên tắc phân quyền truy cập bảng Oracle nào an toàn hơn?
A. Chỉ GRANT các quyền đối tượng mà tài khoản thật sự cần.
B. Cấp SELECT ANY TABLE cho mọi tài khoản chỉ có nhu cầu đọc.
C. Cho mọi ứng dụng dùng chung schema quản trị của database.
D. Cấp DBA cho mọi tài khoản ứng dụng để không gặp lỗi quyền.
Đáp án đúng: A

Câu 37. Vì sao archived redo log quan trọng trong nhiều phương án phục hồi?
A. Tự chứa bản sao đầy đủ mọi datafile ở từng thời điểm riêng.
B. Loại bỏ hoàn toàn nhu cầu tạo backup định kỳ của datafile.
C. Chỉ lưu lệnh SELECT để dựng lại kết quả truy vấn cũ.
D. Cho phép áp dụng thay đổi sau backup khi khôi phục database.
Đáp án đúng: D

Câu 38. Phân biệt RESTORE và RECOVER trong Oracle RMAN nào là đúng?
A. RESTORE lấy dữ liệu từ backup; RECOVER áp dụng redo cần thiết.
B. RESTORE tạo index mới; RECOVER xóa dữ liệu đã hết thời hạn.
C. RESTORE chỉ áp dụng redo; RECOVER chỉ sao chép file từ backup.
D. RESTORE thực hiện COMMIT; RECOVER xác nhận các quyền database.
Đáp án đúng: A

Câu 39. Với JDBC giao dịch thủ công trên Oracle, khi một bước ghi thất bại nên làm gì?
A. Gọi rollback trên connection trước khi kết thúc xử lý lỗi.
B. Chỉ đóng ResultSet để Oracle tự hoàn tác toàn bộ câu DML.
C. Tạo Statement khác rồi tiếp tục mà không kiểm tra transaction.
D. Gọi commit dù đã có lỗi để đóng giao dịch và giữ thay đổi.
Đáp án đúng: A

Câu 40. Khi dùng connection pool với Oracle JDBC, gọi close() trên handle thường làm gì?
A. Luôn đóng socket vật lý ngay cả khi pool đang còn hoạt động.
B. Xóa mọi session khác đang kết nối cùng database instance.
C. Trả handle về pool để có thể cấp lại ở lần mượn tiếp theo.
D. Tự commit mọi giao dịch còn mở trên các connection cùng pool.
Đáp án đúng: C
