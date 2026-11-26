Thiết bị đo nhiệt độ gửi trường số nguyên có dấu 8 bit, nhưng phần mềm nhận coi byte là số không dấu; các giá trị nhiệt độ âm được hiển thị thành số dương rất lớn.
Trong bộ điều khiển nhúng, phép cộng hai số nguyên 8 bit có dấu vượt phạm vi biểu diễn; cảnh báo vượt ngưỡng không kích hoạt khi kết quả quay sang giá trị âm.
Một dịch vụ đọc dữ liệu cảm biến đa byte từ thiết bị mạng, nhưng nhà sản xuất và ứng dụng dùng thứ tự byte khác nhau; giá trị độ dài gói tin đôi khi trở nên phi lý.
Nhóm lưu dấu thời gian và số lượng bằng số thực nhị phân rồi cộng dồn trong thời gian dài; sai số nhỏ tích lũy khiến tổng trên dashboard không trùng với dữ liệu gốc.
Một chương trình cắt chuỗi UTF-8 bằng số byte cố định để gửi qua giao thức có giới hạn độ dài; tên người dùng có dấu bị hỏng dù số ký tự được đếm là hợp lệ.
Đội thiết kế mạch logic cho bộ khóa cửa kết hợp tín hiệu cảm biến và nút nhấn; tín hiệu ở hai cổng có độ trễ khác nhau khiến ngõ ra xuất hiện xung ngắn ngoài mong đợi.
Một hệ điều khiển sử dụng flip-flop lưu trạng thái nhưng quên xác định tín hiệu reset lúc khởi động; cùng firmware chạy khác nhau sau những lần cấp nguồn.
Nhóm mô phỏng CPU tự xây thêm lệnh số học mới vào tập lệnh mà chưa cập nhật đường dữ liệu và tín hiệu điều khiển; một số trường hợp dùng chung thanh ghi cho kết quả sai.
Trong ứng dụng phân tích log, CPU có nhiều nhân nhưng một nhánh rẽ khó dự đoán nằm trong vòng lặp nóng khiến throughput thấp hơn phiên bản có nhiều phép tính hơn.
Đội tăng tốc một bộ lọc dữ liệu bằng cách chia thành nhiều luồng cập nhật các bộ đếm nằm cạnh nhau trong bộ nhớ; hiệu năng giảm do các nhân phải liên tục đồng bộ dòng cache.
Một chương trình đọc mảng hai chiều theo cột trong khi dữ liệu được lưu liên tiếp theo hàng; thời gian xử lý tăng mạnh khi kích thước mảng vượt khả năng cache CPU.
Nhóm chuyển tác vụ từ máy tính cá nhân sang máy chủ NUMA; thread truy cập chủ yếu vùng nhớ trên node khác nên tốc độ thấp dù tổng RAM vẫn còn nhiều.
Ứng dụng phân tích ảnh cần giữ nhiều khối dữ liệu tạm; khi bộ nhớ vật lý gần đầy, hệ thống liên tục chuyển trang và hiệu năng sụt giảm trước khi báo thiếu RAM.
Một service khởi động nhiều tiến trình con cùng nạp thư viện lớn; dashboard cho thấy tổng bộ nhớ ảo rất cao và người vận hành nhầm đó với lượng RAM vật lý thực đang dùng.
Trong dịch vụ xử lý đệ quy một cây cực sâu, chương trình dừng vì tràn stack dù bộ nhớ heap vẫn còn; đội cần phân biệt hai vùng cấp phát và giới hạn của mỗi vùng.
Khi chạy workload truy cập ngẫu nhiên trên tập dữ liệu lớn, CPU sử dụng ít nhưng độ trễ truy cập bộ nhớ tăng; nhóm nghi ngờ chi phí bỏ lỡ TLB thay vì thời gian tính toán thuần.
Một chương trình C biên dịch thành công từng file đối tượng nhưng bước liên kết thất bại khi thiếu định nghĩa cho một hàm trong thư viện ngoài; đội nhầm lỗi linker thành lỗi cú pháp.
Ứng dụng được build với thư viện hệ thống phiên bản mới nhưng deploy trên máy cũ; binary nạp thất bại trước khi vào hàm main do không tìm thấy symbol tương thích.
Nhóm thay đổi cách sắp xếp trường trong một cấu trúc dùng để trao đổi dữ liệu giữa thư viện C và ứng dụng khác; hai thành phần cùng biên dịch nhưng đọc nhầm offset vì khác biệt ABI.
Một bản tối ưu của compiler thay đổi thời điểm đọc biến chia sẻ không có đồng bộ; code chạy ổn ở cấu hình debug nhưng xuất hiện lỗi khi bật tối ưu hóa.
Một server cần chạy tác vụ chuyển đổi video dài mà vẫn tiếp nhận nhiều kết nối; khi dùng một tiến trình với một luồng chặn toàn bộ vòng xử lý, độ trễ mọi request tăng đột biến.
Nhóm chạy nhiều thread cùng tăng bộ đếm giao dịch chung; báo cáo cuối ngày thấp hơn số sự kiện nhận được dù mỗi phép tăng trông có vẻ đơn giản.
Hai tác vụ chuyển tiền khóa tài khoản nguồn và đích theo thứ tự ngược nhau; trong tải cao, cả hai giữ một khóa rồi chờ khóa còn lại nên giao dịch không tiến triển.
Trong hệ thống làm việc theo lô, thread phát tín hiệu có dữ liệu mới trước khi thread nhận bắt đầu chờ điều kiện; đôi lúc thread nhận ngủ mãi dù hàng đợi đã có phần tử.
Một ứng dụng dùng biến cờ thường để dừng worker chạy trên lõi CPU khác; worker thỉnh thoảng không thấy thay đổi vì nhóm chưa làm rõ bảo đảm hiển thị giữa các luồng.
Trong hệ thống thời gian thực mềm, một tác vụ ưu tiên cao chờ khóa đang do tác vụ ưu tiên thấp giữ; nhiều tác vụ trung gian khiến yêu cầu khẩn cấp bị trì hoãn lâu.
Chương trình thực hiện thao tác đặc quyền với file hệ thống nhưng thất bại khi chạy dưới tài khoản không đủ quyền; người phát triển chưa phân biệt lời gọi hàm thư viện và system call do kernel kiểm soát.
Một dịch vụ ghi nhật ký giao dịch vào file rồi trả về thành công ngay sau lệnh ghi; khi máy mất điện, bản ghi cuối biến mất dù ứng dụng đã nhận kết quả ghi thành công.
Nhóm triển khai cập nhật cấu hình bằng cách ghi đè trực tiếp file đang dùng; nếu tiến trình bị dừng giữa chừng, cấu hình còn một phần và ứng dụng không thể khởi động lại.
Trung tâm dữ liệu có hai ổ SSD cấu hình RAID 1; khi khách hàng xóa nhầm dữ liệu quan trọng, nhóm nhận ra cơ chế nhân bản ổ đĩa không giải quyết được yêu cầu khôi phục lịch sử.
Ứng dụng phân tích hàng triệu file nhỏ trên SSD; số byte đọc không lớn nhưng thời gian xử lý cao vì metadata lookup và nhiều thao tác I/O ngẫu nhiên.
Một hệ thống truyền sự kiện qua TCP thấy hàm gửi hoàn tất nhưng phía nhận vẫn chưa xử lý thông điệp; đội phát triển đồng nhất xác nhận truyền byte với xác nhận nghiệp vụ.
Ứng dụng gọi dịch vụ qua mạng gửi dữ liệu UDP để giảm độ trễ, nhưng thiếu gói và trật thứ tự chỉ xuất hiện khi mạng nghẽn; thiết kế chưa xác định mức bảo đảm cần thiết.
Nhóm vận hành thấy một API luôn gọi sai địa chỉ sau khi đổi cấu hình DNS; ứng dụng và hệ thống có cache bản ghi với thời gian sống khác nhau.
Trong container Kubernetes, service bị khởi động lại vì vượt giới hạn bộ nhớ dù máy chủ còn RAM; nhóm vận hành chỉ nhìn tổng bộ nhớ host và bỏ qua giới hạn tài nguyên của container.
Đội đưa ứng dụng chạy trong container rồi giả định mỗi container có kernel riêng; một lỗi phụ thuộc phiên bản hệ điều hành chủ vẫn làm nhiều container trên cùng host bị ảnh hưởng.
Trong môi trường ảo hóa, nhiều máy ảo cùng dùng tài nguyên CPU vật lý; một ứng dụng có hai vCPU nhìn thấy mức sử dụng nội bộ thấp nhưng vẫn gặp độ trễ do thời gian chờ được hypervisor lên lịch.
Dịch vụ nhận sự kiện thanh toán từ hàng đợi ít nhất một lần; sau khi consumer xử lý xong nhưng mất kết nối trước khi xác nhận, cùng giao dịch được áp dụng thêm lần nữa.
Nhóm xây báo cáo từ nhiều service độc lập bằng đồng hồ của mỗi máy; thứ tự sự kiện bị đảo lộn vì sai lệch thời gian và độ trễ mạng, khiến hành trình giao dịch khó truy vết.
Một cụm lưu trữ phân tán cần tiếp tục phục vụ khi mất liên lạc giữa hai vùng; hai bên cùng nhận thao tác cập nhật một bản ghi và xuất hiện xung đột khi kết nối được khôi phục.
