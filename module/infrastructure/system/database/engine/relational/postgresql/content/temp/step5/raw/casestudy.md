Một hệ thống thương mại điện tử lưu giá sản phẩm trên bảng danh mục rồi dùng giá đó để lập lại hóa đơn cũ; sau đợt thay đổi giá, tổng tiền của các đơn hàng đã thanh toán không còn khớp với chứng từ trước đây.
Nền tảng SaaS dùng chung bảng khách hàng cho nhiều doanh nghiệp; hai tenant có cùng mã khách hàng nội bộ, nhưng ràng buộc unique hiện tại chỉ cho phép một bản ghi tồn tại.
Ứng dụng đăng ký tài khoản cho phép tạo hai email chỉ khác chữ hoa và chữ thường; sau khi nhóm nghiệp vụ yêu cầu đăng nhập không phân biệt chữ hoa, việc áp dụng ràng buộc duy nhất mới gặp dữ liệu trùng.
Nhóm thay đổi schema bằng cách thêm cột bắt buộc cho bảng giao dịch chứa hàng trăm triệu dòng; trong giờ cao điểm, migration kéo dài và các thao tác ghi của ứng dụng xếp hàng chờ khóa.
Hai phiên bản ứng dụng cũ và mới cùng hoạt động trong lúc rolling deployment; phiên bản mới đổi tên cột địa chỉ giao hàng khiến các instance cũ bắt đầu lỗi khi ghi đơn hàng.
Dịch vụ thanh toán lưu số tiền dưới dạng số dấu phẩy động; sau nhiều phép tính chiết khấu và thuế, số dư đối soát lệch vài đơn vị nhỏ so với báo cáo kế toán.
Chuỗi cửa hàng lưu lịch hẹn của khách ở nhiều múi giờ; vào thời điểm đổi giờ mùa hè tại một số quốc gia, báo cáo theo ngày địa phương thiếu hoặc đếm lặp lịch hẹn.
Đội phát triển đưa cả trạng thái, người duyệt và thời gian phê duyệt vào cột JSONB; nhiều báo cáo chỉ lọc theo người duyệt và khoảng thời gian nên truy vấn trên bảng lớn chậm dần.
Một hệ thống nội dung lưu nhiều thẻ phân loại trong một mảng trên mỗi bài viết; yêu cầu mới cần theo dõi người gắn thẻ và thời điểm gắn cho từng thẻ, khiến mô hình dữ liệu hiện tại khó mở rộng.
Bảng sự kiện lưu vài tỷ bản ghi được phân vùng theo tháng; truy vấn chỉ yêu cầu một ngày nhưng kế hoạch thực thi vẫn truy cập nhiều partition và thời gian phản hồi tăng nhanh.
Một lô nhập đơn hàng từ hệ thống cũ bỏ qua kiểm tra quan hệ đến khách hàng; khi nhóm bật lại foreign key, một số bản ghi đơn hàng không có khách hàng tương ứng khiến việc triển khai thất bại.
Ứng dụng quản lý vận đơn bổ sung trạng thái mới bằng kiểu enum của PostgreSQL; bản phát hành đang chạy song song nhiều phiên bản ứng dụng và một số phiên bản chưa hiểu giá trị vừa thêm.
Báo cáo doanh thu nối đơn hàng với dòng sản phẩm và lần hoàn tiền; một đơn hàng có nhiều dòng và nhiều lần hoàn tiền làm tổng tiền hiển thị cao hơn dữ liệu kế toán.
Màn hình chăm sóc khách hàng cần hiển thị cả người chưa từng mua hàng; sau khi thêm điều kiện lọc trạng thái đơn vào phần WHERE của truy vấn có LEFT JOIN, những khách này biến mất.
API danh sách giao dịch phân trang bằng OFFSET lớn; khi người dùng chuyển đến trang hàng nghìn, thời gian truy vấn tăng mạnh và một số giao dịch bị lặp giữa hai trang nếu có bản ghi mới.
Một bảng xếp hạng sắp theo điểm với nhiều người cùng điểm; người dùng đổi trang và thấy thứ tự của các bản ghi bằng điểm thay đổi giữa các lần tải.
Phòng nhân sự truy xuất toàn bộ cấp dưới qua recursive CTE; dữ liệu lịch sử có một vòng quản lý khép kín, khiến truy vấn tiêu thụ tài nguyên tăng đột biến khi gặp chuỗi này.
Báo cáo số đơn theo ngày dùng ngày trên server để nhóm các timestamp; khách ở múi giờ khác phản ánh đơn đặt sát nửa đêm xuất hiện trong ngày không đúng tại nơi họ sinh sống.
Dashboard phân tích dùng materialized view làm mới theo lịch mỗi giờ; sau một giao dịch lớn, số liệu trên dashboard chậm hơn hệ thống giao dịch và các bộ phận nghi ngờ mất dữ liệu.
Hai worker đồng thời nhận sự kiện tạo cùng một hồ sơ khách hàng; thao tác kiểm tra tồn tại rồi INSERT gây lỗi khóa duy nhất ngắt quãng khi hàng đợi xử lý tăng.
Dịch vụ chuyển tiền ghi lệnh ghi nợ và ghi có bằng hai giao dịch riêng; khi kết nối bị gián đoạn giữa hai bước, hệ thống xuất hiện giao dịch chỉ hoàn thành một phía.
API cập nhật tồn kho đọc số lượng hiện tại, tính giá trị mới ở ứng dụng rồi ghi trở lại; khi hai đơn hàng cùng mua sản phẩm cuối cùng, lượng tồn kho lưu lại không phản ánh đủ cả hai đơn.
Một báo cáo chạy hai câu truy vấn liên tiếp trong giao dịch READ COMMITTED; tổng số đơn ở câu đầu khác tổng của các chi tiết ở câu sau khi worker nhập thêm đơn giữa hai lần đọc.
Một tác vụ cập nhật dữ liệu trong giao dịch REPEATABLE READ chạy lâu và gặp lỗi đồng thời khi một giao dịch khác đã thay đổi bản ghi mà nó định cập nhật.
Ứng dụng đặt vé chuyển sang mức cô lập SERIALIZABLE để bảo vệ điều kiện không vượt số ghế; khi mở bán, một phần giao dịch bị PostgreSQL từ chối do xung đột đồng thời và khách hàng nhận lỗi 500.
Một API mở transaction rồi chờ phản hồi HTTP của đối tác trước khi kết thúc; pg_stat_activity liên tục hiển thị nhiều phiên idle in transaction dù lượng SQL thực thi mỗi request không lớn.
Job xuất báo cáo giữ một snapshot MVCC trong nhiều giờ; số lần cập nhật dữ liệu vẫn bình thường nhưng dead tuples và kích thước các bảng tăng vì VACUUM không thu hồi được nhiều phiên bản cũ.
Hai nghiệp vụ cập nhật tài khoản và đơn hàng theo thứ tự khóa ngược nhau; trong giờ cao điểm, PostgreSQL phát hiện deadlock và hủy một số transaction vốn chạy ổn khi đứng riêng.
Hàng chục worker cùng tìm tác vụ chưa xử lý để nhận việc; khi xử lý đồng thời, cùng một job đôi lúc bị thực thi hai lần dù mỗi worker chỉ định nhận một bản ghi.
Nhóm vận hành tạo chỉ mục B-tree thông thường trên bảng đơn hàng lớn ngay giữa giờ giao dịch; các request ghi bắt đầu chờ và hàng đợi tích lũy trong suốt thời gian dựng chỉ mục.
Đợt xóa hàng triệu khách hàng không còn hoạt động dẫn đến nhiều thao tác trên bảng con có foreign key; các transaction liên quan bị chậm và xuất hiện hàng chờ khóa khó giải thích.
API tìm giao dịch thường lọc theo tenant, trạng thái và khoảng ngày; PostgreSQL có các chỉ mục đơn cột nhưng truy vấn vẫn đọc rất nhiều dòng rồi sort trước khi trả trang đầu.
Tính năng tìm sản phẩm theo chuỗi xuất hiện ở bất kỳ vị trí nào trong tên chạy nhanh trên vài nghìn dòng thử nghiệm, nhưng trên hàng chục triệu dòng PostgreSQL quét gần như toàn bộ bảng.
Màn hình duyệt đơn đã có partial index dành cho đơn đang chờ; một thay đổi nhỏ trong điều kiện truy vấn khiến planner không chọn chỉ mục này như nhóm phát triển kỳ vọng.
Truy vấn tra cứu từ bảng JSONB dùng cấu trúc điều kiện khác với truy vấn từng được benchmark; chỉ mục GIN hiện có không được sử dụng và lượng dữ liệu đọc tăng đột biến.
Báo cáo lấy vài cột đã nằm trong index nhưng EXPLAIN ANALYZE vẫn cho thấy nhiều heap fetch; bảng nhận cập nhật liên tục và việc đọc dữ liệu không đạt tốc độ dự kiến.
Cửa hàng có hầu hết đơn hàng ở trạng thái hoàn tất, chỉ một tỷ lệ rất nhỏ đang xử lý; sau thay đổi lớn về phân bố dữ liệu, planner chọn kế hoạch kém hiệu quả cho truy vấn theo trạng thái hiếm.
Truy vấn sắp xếp doanh số của nhiều triệu khách hàng chạy nhanh ở môi trường nhỏ; trên production, EXPLAIN ANALYZE cho thấy thao tác sort ghi tệp tạm xuống đĩa và độ trễ tăng mạnh.
Một truy vấn nối bảng sản phẩm, đơn hàng và dòng hàng có số hàng thực tế cao gấp nhiều lần ước lượng trong EXPLAIN ANALYZE; kế hoạch lặp truy cập index trở nên tốn kém khi dữ liệu tăng.
Ứng dụng sử dụng prepared statement cho truy vấn có tham số tenant; tenant lớn chậm hơn đáng kể so với tenant nhỏ dù dùng cùng câu SQL và cùng tập chỉ mục.
Bảng giao dịch có hàng chục index bổ sung dần qua nhiều phiên bản; truy vấn đọc vẫn đạt SLA nhưng tốc độ INSERT giảm và lượng WAL phát sinh tăng rõ rệt trong đợt nhập dữ liệu.
Một bảng nhật ký bị UPDATE và DELETE nhiều hơn dự kiến; dung lượng trên đĩa tăng liên tục, autovacuum thường hoạt động nhưng truy vấn vẫn phải đọc nhiều trang chứa phiên bản cũ.
PostgreSQL cảnh báo tuổi transaction ID tăng cao trên một cơ sở dữ liệu ít được bảo trì; đội trực ca phát hiện một số bảng lớn lâu ngày chưa VACUUM phù hợp.
Ổ đĩa lưu WAL gần đầy sau khi một subscriber ngừng hoạt động; primary vẫn nhận giao dịch mới nhưng các tệp WAL cũ tiếp tục được giữ lại bởi replication slot.
Ứng dụng nạp hàng trăm triệu sự kiện bằng các lô lớn; lưu lượng WAL và I/O tăng mạnh, replica chậm theo kịp và độ trễ của các giao dịch nhỏ cũng tăng.
Trong khoảng cao điểm, hệ thống có các đợt tăng độ trễ ghi ngắn và đều đặn, trùng với thời điểm checkpoint ghi nhiều dirty page xuống đĩa.
Job sao lưu PITR báo thành công đối với base backup, nhưng thao tác khôi phục đến một thời điểm cụ thể thất bại do thiếu một đoạn WAL archive trong khoảng cần khôi phục.
Một hệ thống dữ liệu vài terabyte chỉ dùng pg_dump mỗi đêm; kiểm thử khôi phục cho thấy thời gian nạp lại dài hơn nhiều so với mục tiêu phục hồi sau sự cố của doanh nghiệp.
Bản sao lưu khôi phục vào staging có số bảng và dòng dữ liệu hợp lý, nhưng ứng dụng không khởi động đầy đủ vì thiếu extension, role hoặc quyền truy cập từng tồn tại ở production.
API đọc từ standby ngay sau khi ghi thành công vào primary; một số người dùng không thấy bản ghi vừa tạo vì replica đang trễ vài giây trong giờ cao điểm.
Một truy vấn phân tích chạy lâu trên hot standby thỉnh thoảng bị hủy đúng lúc primary có nhiều UPDATE và VACUUM; dashboard báo lỗi truy vấn dù replica vẫn kết nối được.
Sau failover, một node standby được promote nhưng ứng dụng vẫn gửi một phần thao tác ghi đến endpoint đang ở chế độ chỉ đọc; số request lỗi tăng dù cụm đã có primary mới.
Hệ thống bật synchronous replication qua hai vùng mạng; mỗi lần đường truyền giữa các vùng tăng độ trễ, thời gian COMMIT của giao dịch tăng dù câu SQL trước đó không chậm.
Pipeline logical replication sao chép INSERT bình thường nhưng gặp lỗi khi cần phát UPDATE hoặc DELETE từ bảng không có primary key hay replica identity phù hợp.
Đội vận hành tăng số replica ứng dụng nhưng mỗi pod mở nhiều kết nối PostgreSQL; pg_stat_activity xuất hiện hàng trăm session phần lớn idle, trong khi CPU và bộ nhớ máy chủ tăng.
Một dashboard giám sát chỉ có CPU và số kết nối, không theo dõi câu SQL nặng; khi hệ thống chậm, nhóm không xác định được loại truy vấn nào tiêu tốn thời gian và I/O nhiều nhất.
Trong giờ cao điểm, CPU PostgreSQL thấp nhưng API cập nhật đơn hàng chậm; pg_stat_activity hiển thị hàng loạt phiên chờ khóa phía sau một giao dịch chưa kết thúc.
Sau một đợt tăng dữ liệu, dung lượng ổ đĩa tăng nhanh hơn số bản ghi mới; bảng, index và tệp tạm đóng góp tỷ lệ khác nhau nhưng cảnh báo hiện chỉ dựa trên dung lượng toàn ổ.
Ứng dụng PostgreSQL ngừng kết nối trên một số máy sau khi đội vận hành thay chứng chỉ TLS; các instance mới kết nối được nhưng một số instance cũ tiếp tục báo lỗi xác minh chứng chỉ máy chủ.
