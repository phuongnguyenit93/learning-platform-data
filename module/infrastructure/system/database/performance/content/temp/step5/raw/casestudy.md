Một API tra cứu đơn hàng tăng thời gian phản hồi p99 từ 180 ms lên 4 giây sau đợt phát hành, trong khi thời gian phản hồi trung bình chỉ tăng nhẹ; dashboard hiện chỉ theo dõi giá trị trung bình và CPU cơ sở dữ liệu.
Trong thử nghiệm tải với 10 nghìn bản ghi, truy vấn tìm khách hàng luôn dưới 10 ms; khi chạy trên production có 80 triệu bản ghi và nhiều giao dịch đồng thời, cùng truy vấn thường vượt một giây.
Nhóm vận hành tăng số request đồng thời từ 100 lên 500 khi kiểm thử; throughput gần như không tăng nhưng p95 tăng mạnh, số connection đang chờ cao và CPU cơ sở dữ liệu chạm ngưỡng.
Trước khi tối ưu, đội phát triển chỉ ghi nhận thời gian xử lý HTTP; một endpoint mất 2 giây nhưng các câu SQL cộng lại chỉ mất khoảng 80 ms, khiến nhóm chưa xác định được phần thời gian còn lại.
Hiệu năng báo cáo khác nhau giữa các lần thử trên cùng tập dữ liệu; lượt đầu truy vấn đọc nhiều trang từ đĩa, còn các lượt sau được phục vụ chủ yếu từ bộ nhớ đệm.
Một bài benchmark chạy liên tục sau khi thay đổi cấu hình nhưng khối lượng dữ liệu và tỷ lệ truy vấn đọc/ghi trong bài thử khác xa lưu lượng giờ cao điểm thực tế.
Đội kỹ thuật so sánh bản phát hành mới với bản cũ bằng hai mốc thời gian khác nhau; mốc mới có lượng đơn hàng và người dùng đồng thời cao hơn nhiều nên kết luận hồi quy hiệu năng chưa rõ ràng.
Ứng dụng gom các truy vấn của nhiều endpoint vào một chỉ số tổng; một truy vấn hiếm nhưng rất chậm bị che khuất bởi hàng triệu truy vấn tra cứu nhanh.
Màn hình danh sách sản phẩm hiển thị 50 bản ghi nhưng ORM lại thực hiện thêm một truy vấn lấy danh mục cho mỗi sản phẩm; số câu SQL trên mỗi request tăng theo kích thước trang.
API trả về 20 thuộc tính nhưng truy vấn chọn toàn bộ cột của bảng chứa nhiều trường văn bản lớn; băng thông giữa ứng dụng và cơ sở dữ liệu cùng thời gian đọc trang dữ liệu tăng.
Một truy vấn tìm đơn hàng theo mã đơn luôn duyệt toàn bộ bảng lớn dù điều kiện chỉ khớp một dòng; môi trường thử nghiệm chưa có index phù hợp với bộ lọc thường dùng.
Đội phát triển bổ sung index cho cột trạng thái chỉ có hai giá trị; truy vấn vẫn quét nhiều bản ghi vì phần lớn dữ liệu có cùng một trạng thái.
API thường lọc đơn hàng theo mã cửa hàng và khoảng ngày, sau đó sắp xếp thời điểm tạo; hệ thống có hai index đơn cột nhưng vẫn phải quét nhiều hàng và sắp xếp tập kết quả lớn.
Truy vấn lọc theo ngày nhưng biểu thức áp dụng hàm chuyển đổi lên từng giá trị timestamp; một index trên cột thời gian đã tồn tại nhưng kế hoạch thực thi không dùng như dự kiến.
Màn hình tìm kiếm khách hàng dùng điều kiện chứa chuỗi bất kỳ trong tên; khi bảng tăng đến hàng chục triệu dòng, lượng dữ liệu bị quét tăng liên tục dù chỉ trả vài kết quả.
Báo cáo truy vấn thuộc tính nằm sâu trong JSON; bảng đã có index thông thường trên một cột khác nhưng bộ lọc JSON vẫn khiến kế hoạch thực thi phải đọc phần lớn bản ghi.
Một partial index dành cho các đơn chưa xử lý giúp truy vấn nhanh ở môi trường thử nghiệm, nhưng sau khi đổi dạng điều kiện trạng thái trong SQL, optimizer không còn chọn index đó.
Truy vấn lấy vài cột đều có trong một covering index nhưng kế hoạch vẫn cần truy cập thêm dữ liệu gốc nhiều lần; bảng đang nhận cập nhật liên tục và tốc độ đọc chưa đạt kỳ vọng.
Màn hình sản phẩm phân trang bằng OFFSET lớn trên tập dữ liệu vài chục triệu dòng; trang đầu phản hồi nhanh còn các trang rất xa mất nhiều giây dù mỗi trang chỉ hiển thị 30 sản phẩm.
Danh sách xếp hạng sắp xếp theo điểm có nhiều giá trị trùng; khi người dùng chuyển trang trong lúc dữ liệu được cập nhật, các bản ghi xuất hiện lặp hoặc bị bỏ qua, làm khó việc đo hiệu năng phân trang.
Nhóm thêm nhiều index để tăng tốc báo cáo, nhưng sau đó thời gian INSERT một lô lớn tăng gấp đôi và dung lượng index lớn hơn đáng kể dù số truy vấn đọc không thay đổi.
Một bảng sự kiện được phân vùng theo tháng; báo cáo yêu cầu hai ngày nhưng execution plan vẫn truy cập nhiều phân vùng vì điều kiện lọc không phù hợp với khóa phân vùng.
Một bảng phân vùng theo tenant có một khách hàng chiếm 70% giao dịch; dù các phân vùng còn lại nhỏ, truy vấn và thao tác ghi của tenant lớn thường vượt SLA.
Truy vấn JOIN đơn hàng, dòng hàng và lịch sử thanh toán trả nhiều hàng hơn dự kiến; một đơn có nhiều dòng và nhiều lần thanh toán làm số bản ghi trung gian tăng theo phép nhân.
Nhóm tối ưu một câu SQL bằng cách thêm DISTINCT để bỏ kết quả trùng sau nhiều JOIN; lượng hàng trung gian vẫn rất lớn và bước khử trùng lặp tiêu thụ nhiều bộ nhớ.
Một báo cáo tính doanh thu nhóm theo khách hàng trên hàng chục triệu dòng; khi tải đồng thời tăng, thao tác GROUP BY và ORDER BY ghi nhiều tệp tạm ra đĩa.
Câu truy vấn có LIMIT 20 nhưng kế hoạch phải sắp xếp hàng triệu bản ghi trước khi chọn 20 dòng cuối; thời gian phản hồi tăng theo dữ liệu dù kết quả trả về ít.
Báo cáo dùng truy vấn lồng nhau tương quan với từng khách hàng; khi số khách tăng từ vài nghìn lên vài triệu, số lần đọc bảng giao dịch tăng mạnh.
Optimizer ước lượng một bộ lọc chỉ trả 200 dòng, nhưng EXPLAIN ANALYZE đo được hơn 200 nghìn dòng; JOIN phía sau dùng kế hoạch phù hợp với tập nhỏ nên rất chậm.
Hệ thống có phân bố dữ liệu thay đổi rõ sau chiến dịch giảm giá; thống kê bảng chưa được cập nhật kịp khiến truy vấn theo sản phẩm phổ biến chọn kế hoạch thiếu hiệu quả.
Ứng dụng dùng prepared statement chung cho nhiều tenant; truy vấn của tenant nhỏ rất nhanh nhưng tenant lớn có hàng triệu đơn hàng lại chậm đột biến dù cấu trúc SQL giống nhau.
Một truy vấn chạy nhanh với tham số lọc hiếm nhưng chậm với tham số rất phổ biến; đội phát triển chỉ đo một bộ tham số cố định khi kiểm tra kế hoạch thực thi.
Kế hoạch thực thi của báo cáo đổi từ tìm kiếm qua index sang quét bảng sau khi dữ liệu tăng; nhóm có bản ghi kết quả EXPLAIN cũ nhưng chưa lưu số hàng thực tế và thời gian từng bước.
Một câu SQL lọc danh sách mã sản phẩm dài từ vài phần tử đến hàng chục nghìn phần tử; ở tập đầu vào lớn, cách truy cập dữ liệu và thời gian thực thi thay đổi mạnh.
Nhân viên phân tích bật EXPLAIN ANALYZE cho truy vấn cập nhật dữ liệu trong môi trường vận hành mà chưa tính đến tác động của việc thực thi thật lên các giao dịch đang chạy.
Dashboard cho thấy CPU cơ sở dữ liệu thấp nhưng thời gian truy vấn tăng; các worker đang chờ thao tác đọc ngẫu nhiên trên đĩa và chỉ số I/O wait tăng cao.
Một truy vấn duyệt index rồi truy cập bản ghi gốc ở rất nhiều vị trí rời rạc; trên ổ đĩa có độ trễ cao, tổng số lần đọc ngẫu nhiên trở thành nút thắt dù số hàng trả về ít.
Tỷ lệ cache hit giảm sau khi thêm luồng phân tích quét bảng lớn mỗi giờ; các truy vấn giao dịch ngắn bắt đầu phải đọc dữ liệu từ đĩa nhiều hơn.
Đội vận hành tăng bộ nhớ dành cho sắp xếp mỗi truy vấn và thấy báo cáo riêng lẻ chạy nhanh hơn; khi 100 truy vấn phân tích đồng thời, tổng mức sử dụng bộ nhớ tăng mạnh và hệ thống bắt đầu swap.
Một truy vấn JOIN có bước hash lớn hơn bộ nhớ được cấp; execution plan cho thấy dữ liệu được chia nhiều batch và ghi tệp tạm, làm thời gian truy vấn tăng theo tải.
Sau khi tăng cache của cơ sở dữ liệu, máy chủ bắt đầu dùng swap và phản hồi chậm; bộ nhớ còn phải phục vụ tiến trình nền, hệ điều hành và nhiều kết nối đồng thời.
Truy vấn đọc của ứng dụng thường chỉ cần bản ghi gần đây nhưng báo cáo quét dữ liệu lịch sử nhiều năm; cache của máy chủ bị lấn bởi các trang ít được truy cập.
Hệ thống ghi dữ liệu theo lô lớn mỗi 15 phút; trong các đợt này, lượng log giao dịch và I/O ghi tăng mạnh, kéo theo độ trễ của các request nhỏ.
Một dịch vụ có các đợt tăng p99 đều đặn trùng với thời điểm checkpoint hoặc flush dữ liệu; CPU trung bình ổn định nhưng thời gian chờ ghi đĩa thay đổi rõ.
Sao lưu toàn bộ cơ sở dữ liệu được chạy giữa giờ cao điểm; dashboard đồng thời ghi nhận throughput đọc đĩa tăng và truy vấn nghiệp vụ phản hồi chậm hơn.
Ứng dụng tăng số pool connection khi chịu tải nhưng cơ sở dữ liệu chỉ có 8 lõi CPU; số kết nối hoạt động tăng gấp nhiều lần còn tổng throughput giao dịch hầu như không đổi.
Trong thời gian autoscale từ 4 lên 30 pod, mỗi pod mở pool 30 kết nối; máy chủ cơ sở dữ liệu đạt giới hạn session và phần lớn request chờ lấy kết nối.
Thời gian request API tăng sau khi một đối tác HTTP bên ngoài phản hồi chậm; transaction vẫn giữ connection cơ sở dữ liệu trong lúc chờ đối tác nên số connection đang dùng chạm giới hạn.
Một tác vụ xuất dữ liệu mở transaction để đọc theo luồng trong hơn một giờ; các bảng được cập nhật liên tục phát sinh nhiều phiên bản cũ và việc dọn dẹp dữ liệu bị trì hoãn.
Dashboard ghi nhận nhiều phiên idle in transaction, trong khi CPU thấp và hàng chờ cập nhật tăng; một phiên đã mở giao dịch rồi dừng chờ thao tác từ ứng dụng.
Hai worker cập nhật cùng bản ghi tổng tồn kho trong mỗi đơn hàng; khi số đơn tăng, lock wait chiếm phần lớn thời gian giao dịch dù mỗi câu UPDATE rất ngắn.
Phân tích thời gian phản hồi của một lô cập nhật cho thấy nhiều transaction chờ khóa phía sau một phiên chạy lâu; dashboard hiện chỉ hiển thị SQL đang chạy chứ chưa chỉ ra chuỗi phiên chặn nhau.
Hai tiến trình cập nhật nhiều bảng theo thứ tự khác nhau; khi chạy đồng thời, tỷ lệ deadlock và số lần thử lại tăng dù thời gian từng câu SQL đơn lẻ không thay đổi.
Ứng dụng đổi sang mức cô lập giao dịch cao hơn để tránh sai lệch dữ liệu; độ trễ tăng và một số giao dịch phải chạy lại do xung đột khi ghi dưới tải cao.
Một quy trình gộp 100 nghìn bản ghi vào một transaction duy nhất; thời gian giữ khóa và tài nguyên tăng khiến các thao tác nghiệp vụ nhỏ bị chậm khi job chạy.
Đội vận hành phát hiện các câu truy vấn có thời gian thực thi thấp nhưng request timeout trong lúc lấy connection; hệ thống chưa thu thập đồng thời active, idle và pending của pool.
Một ứng dụng chuyển phần đọc sang replica để giảm tải primary; báo cáo chạy nhanh hơn ở primary nhưng chậm tại replica vì năng lực phần cứng và độ trễ sao chép khác nhau.
Trên dữ liệu gần như không đổi, hai lần đo cùng một câu SQL cho kết quả trái ngược vì một lần có 1 worker và lần kia có 60 worker; nhóm cần quy định cách đo tải đồng thời.
Sau khi thay đổi index, truy vấn tìm kiếm giảm từ 600 ms xuống 40 ms nhưng lượng ghi mỗi giây giảm 25%; hệ thống phục vụ đồng thời luồng đọc và ghi nên tác động tổng thể chưa được đánh giá.
Nhóm cải tiến câu SQL trên môi trường staging rồi triển khai thẳng production; dữ liệu thật có phân bố tenant, kích thước bảng và tỷ lệ cache khác xa staging nên kết quả không được lặp lại.
Một đợt tối ưu bộ nhớ giúp p50 tốt hơn nhưng p99 xấu đi trong giờ cao điểm; phép đo trước và sau dùng khoảng thời gian khác nhau, chưa kiểm soát tải nền và truy vấn ngoại lai.
Đội phát triển thấy báo cáo chậm sau thay đổi cấu hình và muốn đảo ngược ngay, nhưng số liệu thiếu baseline về latency, throughput, CPU, I/O và lock wait trước thời điểm thay đổi.
Dashboard ứng dụng báo tăng timeout trong lúc máy chủ cơ sở dữ liệu phản hồi ổn định với truy vấn riêng lẻ; nhóm chưa phân tách thời gian chờ ở mạng, hàng đợi connection pool và thời gian thực thi SQL.
