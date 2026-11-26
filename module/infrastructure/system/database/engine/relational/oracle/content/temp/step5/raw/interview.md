Bạn sẽ giải thích sự khác biệt giữa Oracle Database instance và database khi mô tả một hệ thống đang chạy như thế nào?
Những thành phần bộ nhớ trong SGA và PGA phục vụ các loại công việc nào, và bạn sẽ quan sát chúng khi có vấn đề hiệu năng ra sao?
Bạn sẽ mô tả vai trò của các tiến trình nền DBWn, LGWR, CKPT, SMON và PMON trong vận hành Oracle như thế nào?
Điều gì diễn ra từ lúc ứng dụng gửi lệnh SQL cho đến khi Oracle trả về dữ liệu, xét theo session, process và bộ nhớ?
Bạn sẽ phân biệt datafile, control file, online redo log và archived redo log về mục đích và vòng đời như thế nào?
Checkpoint có vai trò gì đối với việc ghi dữ liệu xuống đĩa và khôi phục sau sự cố?
Bạn sẽ mô tả mối quan hệ giữa tablespace, datafile, segment, extent và block khi quản lý lưu trữ Oracle như thế nào?
Bạn sẽ đánh giá việc tăng kích thước bảng và index ảnh hưởng đến dung lượng tablespace và khả năng vận hành ra sao?
Trong kiến trúc multitenant, bạn sẽ giải thích trách nhiệm của CDB root, PDB và PDB$SEED như thế nào?
Bạn sẽ thiết kế việc tách dữ liệu và quyền quản trị giữa các PDB theo yêu cầu của nhiều ứng dụng ra sao?
Bạn sẽ phân biệt common user và local user trong kiến trúc CDB/PDB, và quyết định sử dụng từng loại khi nào?
Bạn sẽ quản lý service name và đường kết nối đến đúng PDB để tránh thao tác nhầm môi trường như thế nào?
Khi cần di chuyển hoặc nhân bản một PDB, bạn sẽ xem xét những phụ thuộc và bước xác minh nào?
Bạn sẽ lựa chọn tổ chức schema, bảng và đối tượng cơ sở dữ liệu cho hệ thống bán hàng dựa trên yêu cầu nghiệp vụ như thế nào?
Bạn sẽ thiết kế khóa chính, khóa ngoại, ràng buộc duy nhất và kiểm tra dữ liệu để bảo vệ tính toàn vẹn ra sao?
Bạn sẽ cân nhắc chuẩn hóa và phi chuẩn hóa bảng khi khối lượng đọc lớn nhưng dữ liệu được cập nhật thường xuyên như thế nào?
Bạn sẽ chọn giữa NUMBER, BINARY_FLOAT, BINARY_DOUBLE và các kiểu dữ liệu khác cho các phép tính cần độ chính xác ra sao?
Bạn sẽ lựa chọn DATE, TIMESTAMP và các kiểu TIMESTAMP có thông tin múi giờ cho dữ liệu sự kiện như thế nào?
Bạn sẽ xử lý việc Oracle coi chuỗi ký tự rỗng là NULL trong thiết kế bảng và kiểm thử ứng dụng ra sao?
Bạn sẽ phân biệt VARCHAR2, CHAR, CLOB và các kiểu chuỗi liên quan để tránh lỗi độ dài và lưu trữ như thế nào?
Bạn sẽ sử dụng sequence hoặc cột identity để sinh khóa và xử lý các khoảng trống trong dãy giá trị ra sao?
Bạn sẽ chọn default, generated column và các ràng buộc schema khi cần bảo đảm dữ liệu đồng nhất từ nhiều ứng dụng như thế nào?
Bạn sẽ áp dụng các kiểu quan hệ một-một, một-nhiều và nhiều-nhiều cho một schema Oracle theo những tiêu chí nào?
Bạn sẽ lập kế hoạch thay đổi cấu trúc bảng đang có nhiều dữ liệu mà vẫn duy trì khả năng tương thích cho ứng dụng như thế nào?
Bạn sẽ lựa chọn thiết kế partition cho một bảng giao dịch lớn dựa trên thời gian và mẫu truy vấn như thế nào?
Bạn sẽ giải thích tác động của thao tác DDL đến transaction đang mở và việc triển khai migration như thế nào?
Bạn sẽ xây dựng một truy vấn SQL có JOIN nhiều bảng mà vẫn trả đúng số dòng khi dữ liệu có quan hệ một-nhiều như thế nào?
Bạn sẽ phân biệt INNER JOIN, LEFT JOIN và các trường hợp dùng EXISTS để biểu diễn điều kiện nghiệp vụ ra sao?
Bạn sẽ xử lý NULL trong điều kiện WHERE, phép so sánh và hàm tổng hợp để tránh sai lệch kết quả như thế nào?
Bạn sẽ sử dụng GROUP BY, HAVING và các hàm tổng hợp để tạo báo cáo doanh thu theo thời gian ra sao?
Bạn sẽ áp dụng các hàm phân tích như ROW_NUMBER, RANK và SUM OVER cho bài toán xếp hạng hoặc tổng lũy kế như thế nào?
Bạn sẽ chọn cách viết truy vấn phân cấp bằng CONNECT BY hay truy vấn đệ quy khi biểu diễn cây tổ chức ra sao?
Bạn sẽ sử dụng common table expression để làm rõ một truy vấn có nhiều bước biến đổi dữ liệu như thế nào?
Bạn sẽ thiết kế truy vấn phân trang ổn định bằng ORDER BY và cú pháp giới hạn dòng của Oracle ra sao?
Bạn sẽ sử dụng MERGE trong trường hợp đồng bộ dữ liệu, và kiểm soát lỗi trùng nguồn hoặc cập nhật nhầm như thế nào?
Bạn sẽ quyết định dùng view hay materialized view cho một báo cáo có chi phí tổng hợp lớn như thế nào?
Bạn sẽ đánh giá chính sách refresh của materialized view theo độ mới dữ liệu và chi phí cập nhật ra sao?
Bạn sẽ truy vấn dữ liệu JSON lưu trong Oracle bằng SQL ra sao, và khi nào bạn sẽ ưu tiên mô hình quan hệ?
Bạn sẽ xác định ranh giới xử lý ở tầng SQL hay ở tầng ứng dụng cho một nghiệp vụ có nhiều phép biến đổi dữ liệu ra sao?
Bạn sẽ mô tả cấu trúc một PL/SQL block với phần khai báo, xử lý và bắt ngoại lệ như thế nào?
Bạn sẽ lựa chọn procedure, function và package để đóng gói logic nghiệp vụ trong Oracle dựa trên những tiêu chí nào?
Bạn sẽ phân biệt package specification và package body trong việc thiết kế giao diện và triển khai mã PL/SQL ra sao?
Bạn sẽ xây dựng quy tắc xử lý exception để giữ thông tin lỗi hữu ích và bảo đảm transaction được xử lý đúng như thế nào?
Bạn sẽ phân tích rủi ro của việc nuốt lỗi trong PL/SQL hoặc tự commit ở thủ tục con như thế nào?
Bạn sẽ lựa chọn cursor tường minh hoặc thao tác SQL tập hợp khi xử lý nhiều dòng dữ liệu như thế nào?
Bạn sẽ dùng BULK COLLECT và FORALL khi nào để giảm chi phí chuyển đổi giữa PL/SQL và SQL, và kiểm soát bộ nhớ ra sao?
Bạn sẽ quyết định dùng trigger hay thực hiện kiểm tra tại tầng ứng dụng khi có thay đổi dữ liệu như thế nào?
Bạn sẽ thiết kế dynamic SQL an toàn với bind variable để tránh chèn SQL và tận dụng khả năng tái sử dụng câu lệnh ra sao?
Bạn sẽ kiểm thử procedure hoặc package PL/SQL có phụ thuộc dữ liệu, quyền truy cập và ngoại lệ như thế nào?
Bạn sẽ mô tả vòng đời transaction từ DML đầu tiên đến COMMIT hoặc ROLLBACK trong Oracle ra sao?
Cơ chế read consistency dựa trên undo giúp các câu SELECT nhìn thấy dữ liệu như thế nào khi có giao dịch đồng thời?
Bạn sẽ phân biệt mức cô lập READ COMMITTED và SERIALIZABLE của Oracle trong một tình huống cập nhật cạnh tranh như thế nào?
Bạn sẽ dùng SAVEPOINT khi nào và làm rõ phạm vi của ROLLBACK TO SAVEPOINT trong một giao dịch ra sao?
Bạn sẽ thiết kế transaction chuyển tiền giữa hai tài khoản để bảo đảm bất biến số dư như thế nào?
Bạn sẽ sử dụng SELECT FOR UPDATE để bảo vệ một thao tác đọc rồi ghi, và dự đoán tác động đến tranh chấp khóa ra sao?
Bạn sẽ phân biệt khóa ở mức dòng với các cơ chế khóa khác của Oracle khi ứng dụng nhiều người dùng thao tác đồng thời như thế nào?
Khi hai transaction tạo thành deadlock, bạn sẽ thu thập bằng chứng và thay đổi thứ tự cập nhật để khắc phục như thế nào?
Bạn sẽ tìm nguyên nhân session chờ khóa lâu bằng những thông tin nào về session, wait event và transaction?
Bạn sẽ đánh giá rủi ro của transaction kéo dài đối với undo, khả năng đồng thời và việc giải phóng connection ra sao?
Khi gặp lỗi snapshot too old, bạn sẽ khảo sát truy vấn, khối lượng cập nhật và chính sách undo retention như thế nào?
Bạn sẽ thiết kế thử lại một transaction lỗi tạm thời mà không vô tình thực thi nghiệp vụ hai lần như thế nào?
Bạn sẽ phân biệt hiện tượng lock contention, thiếu tài nguyên CPU và truy vấn không có index qua những tín hiệu nào?
Bạn sẽ giải thích vai trò của cost-based optimizer trong việc lựa chọn kế hoạch thực thi Oracle như thế nào?
Bạn sẽ thu thập và đánh giá thống kê bảng, cột và index để hỗ trợ optimizer chọn execution plan như thế nào?
Bạn sẽ dùng EXPLAIN PLAN và dữ liệu từ câu lệnh đã thực thi để phân biệt kế hoạch dự kiến với hành vi thực tế như thế nào?
Bạn sẽ đọc một execution plan có full table scan, index range scan và nested loops để đánh giá điểm tốn chi phí như thế nào?
Bạn sẽ phân biệt nested loops, hash join và sort merge join trong lựa chọn thuật toán kết hợp dữ liệu ra sao?
Bạn sẽ so sánh số dòng ước lượng với số dòng thực tế để phát hiện sai lệch cardinality như thế nào?
Bạn sẽ đánh giá ảnh hưởng của histogram và phân bố giá trị không đều đến lựa chọn kế hoạch truy vấn như thế nào?
Bạn sẽ phân tích tác động của bind variable và giá trị đầu vào đến độ ổn định của execution plan ra sao?
Bạn sẽ quyết định tạo B-tree index, bitmap index hoặc function-based index theo loại dữ liệu và mô hình cập nhật như thế nào?
Thứ tự các cột trong composite index ảnh hưởng thế nào đến bộ lọc, sắp xếp và khả năng tái sử dụng index?
Vì sao optimizer có thể chọn full table scan dù truy vấn đã có index, và bạn sẽ kiểm chứng lựa chọn đó ra sao?
Bạn sẽ sử dụng partition pruning để giảm dữ liệu cần quét trong bảng partition lớn như thế nào?
Bạn sẽ đánh giá tác động của việc thêm quá nhiều index đến ghi dữ liệu, không gian lưu trữ và thời gian bảo trì ra sao?
Bạn sẽ xác minh rằng một lần thay đổi index hoặc thống kê cải thiện truy vấn mà không làm xấu những truy vấn khác như thế nào?
Bạn sẽ dùng SQL trace, wait events và số liệu thời gian để tách nút nghẽn CPU, I/O và khóa như thế nào?
Bạn sẽ phân tích một truy vấn chạy nhanh ở môi trường kiểm thử nhưng chậm trên sản xuất dựa trên những khác biệt nào?
Bạn sẽ xác định nguyên nhân kế hoạch truy vấn thay đổi sau khi dữ liệu tăng mạnh hoặc thống kê được làm mới ra sao?
Bạn sẽ thiết kế bộ chỉ số theo dõi query latency, throughput, session và các loại wait event cho một ứng dụng Oracle như thế nào?
Bạn sẽ cấp quyền cho tài khoản ứng dụng theo nguyên tắc tối thiểu quyền bằng user, role và grant như thế nào?
Bạn sẽ phân biệt quyền hệ thống với quyền trên đối tượng khi cấp quyền truy cập vào bảng hoặc procedure ra sao?
Bạn sẽ quản lý quyền giữa các schema để ứng dụng chỉ truy cập được dữ liệu và API cần thiết như thế nào?
Bạn sẽ cân nhắc ảnh hưởng của definer rights và invoker rights khi chạy chương trình PL/SQL có quyền khác nhau ra sao?
Bạn sẽ thiết lập auditing để xác định người thực hiện thay đổi nhạy cảm mà không ghi thừa dữ liệu bí mật như thế nào?
Bạn sẽ tổ chức quản lý mật khẩu, credential và secret cho ứng dụng Oracle trong nhiều môi trường triển khai như thế nào?
Bạn sẽ đánh giá nhu cầu mã hóa kết nối, mã hóa dữ liệu lưu trữ và quản lý khóa của Oracle như thế nào?
Bạn sẽ xây dựng quy trình sao lưu bằng RMAN dựa trên yêu cầu mất dữ liệu tối đa và thời gian phục hồi như thế nào?
Bạn sẽ phân biệt full backup, incremental backup và archived redo log trong các kịch bản phục hồi ra sao?
Bạn sẽ mô tả vai trò của chế độ ARCHIVELOG đối với khả năng sao lưu và phục hồi khi cơ sở dữ liệu đang hoạt động như thế nào?
Bạn sẽ xử lý tình huống hỏng datafile hoặc mất control file bằng quy trình restore và recover có kiểm chứng như thế nào?
Bạn sẽ quyết định thực hiện point-in-time recovery khi ứng dụng xóa nhầm dữ liệu trên diện rộng như thế nào?
Bạn sẽ tổ chức diễn tập phục hồi để kiểm chứng bản sao lưu có thể sử dụng được và đáp ứng RTO/RPO ra sao?
Bạn sẽ phân biệt cơ chế backup/restore với các phương án dự phòng và chuyển đổi vai trò như Data Guard như thế nào?
Bạn sẽ đánh giá tác động của không gian lưu trữ archived redo log đầy đối với khả năng ghi và phục hồi như thế nào?
Bạn sẽ kết nối một ứng dụng Java với Oracle bằng JDBC Thin driver và xác định đúng service name như thế nào?
Bạn sẽ chọn DataSource và connection pool cho ứng dụng Java có nhiều truy vấn đồng thời dựa trên những tiêu chí nào?
Bạn sẽ quản lý thời gian chờ thiết lập kết nối, thời gian chờ lấy connection từ pool và giới hạn truy vấn trong ứng dụng ra sao?
Bạn sẽ dùng PreparedStatement và bind parameter để bảo đảm an toàn SQL cũng như hiệu quả xử lý câu lệnh như thế nào?
Bạn sẽ ánh xạ kiểu Oracle NUMBER, DATE, TIMESTAMP và CLOB sang kiểu Java mà không mất độ chính xác hoặc dữ liệu ra sao?
Bạn sẽ triển khai batch DML từ Java và quyết định kích thước batch theo giới hạn bộ nhớ, mạng và transaction như thế nào?
Bạn sẽ quản lý auto-commit, rollback và phạm vi transaction khi nhiều tầng service Java cùng thao tác Oracle như thế nào?
Bạn sẽ gọi stored procedure và xử lý tham số vào/ra từ Java thông qua JDBC như thế nào?
Bạn sẽ tối ưu fetch size và vòng đời ResultSet khi đọc tập dữ liệu lớn từ Oracle vào ứng dụng Java ra sao?
Bạn sẽ nhận diện connection leak, giao dịch giữ khóa quá lâu và session không được trả về pool qua log và chỉ số nào?
Bạn sẽ thiết kế khả năng phục hồi của ứng dụng Java khi Oracle restart hoặc dịch vụ database chuyển nút như thế nào?
Bạn sẽ phân tích mã lỗi Oracle, nguyên nhân gốc và ngữ cảnh JDBC để đưa ra retry hoặc xử lý lỗi thích hợp ra sao?
Bạn sẽ tổ chức kiểm thử tích hợp Java-Oracle để xác minh transaction, constraint, phân quyền và hiệu năng của truy vấn như thế nào?
Khi người dùng báo hệ thống chậm vào giờ cao điểm, bạn sẽ điều tra từ API, pool kết nối, session chờ đến execution plan theo trình tự nào?
Bạn sẽ đặt những tiêu chí nghiệm thu nào cho thiết kế schema, truy vấn, bảo mật và kế hoạch khôi phục trước khi triển khai Oracle vào sản xuất?
