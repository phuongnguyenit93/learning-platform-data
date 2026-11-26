1. Ứng dụng tăng số request nhưng CPU máy DB vẫn thấp; kết nối gần chạm giới hạn. Bước đầu hợp lý nhất?
A. Kiểm tra pool, hàng đợi và mức kết nối mỗi instance.
B. Tăng giới hạn kết nối theo số request cao điểm dự kiến.
C. Tăng cache dữ liệu để giảm số phiên đang chờ kết nối.
D. Tăng timeout truy vấn để phiên không bị ngắt giữa chừng.
Đáp án đúng: A

2. Nhiều phiên đồng thời thực hiện sort lớn; tăng bộ nhớ sort mỗi phiên có rủi ro gì?
A. RAM chỉ tăng theo kích thước cache trang đã được chia sẻ.
B. Nhiều sort cùng cấp phát khiến tổng RAM tăng mạnh.
C. RAM chỉ tăng khi thao tác checkpoint ghi trang xuống đĩa.
D. RAM chỉ tăng nếu số bảng có chỉ mục B-tree thay đổi.
Đáp án đúng: B

3. Một tham số cấu hình DB chỉ có hiệu lực sau restart. Triển khai thay đổi đó nên làm gì?
A. Reload cấu hình nhiều lần rồi coi như tham số đã có hiệu lực.
B. Khởi động lại mỗi ứng dụng mà giữ nguyên tiến trình DB.
C. Chỉnh tham số trên một phiên rồi suy ra cấu hình toàn hệ.
D. Kiểm tra phạm vi restart, lịch bảo trì và hậu kiểm ứng dụng.
Đáp án đúng: D

4. Sau khi chỉnh cache, p95 truy vấn tăng trong giờ cao điểm. Cách đối chiếu nào đáng tin hơn?
A. So sánh thời gian trung bình ở hai khung giờ khác tải.
B. So p95 với cùng tải và query mix ở hai phiên bản.
C. So sánh cache hit ratio mà bỏ qua p95 từng truy vấn.
D. So sánh số connection mà bỏ qua tải từng câu SQL.
Đáp án đúng: B

5. Nhiều kết nối ứng dụng ở trạng thái idle khiến DB gần đầy slot. Hướng xử lý nào phù hợp?
A. Tăng thời gian giữ kết nối idle của mọi instance.
B. Giảm giới hạn connection ở DB nhưng giữ nguyên pool.
C. Tăng thời hạn transaction để các kết nối chờ lâu hơn.
D. Giới hạn kích thước pool và đặt timeout cho phiên idle.
Đáp án đúng: D

6. Các truy vấn sắp xếp lớn đang ghi nhiều tệp tạm. Nên kiểm tra điều gì trước khi tăng RAM?
A. Đo tỷ lệ hit cache và số trang bộ nhớ đang sử dụng.
B. Đo thời gian chờ lock trên bảng của câu truy vấn đó.
C. Đo lượng spill ra đĩa và số lượt sort chạy đồng thời.
D. Đo độ trễ replication và lưu lượng WAL ở primary.
Đáp án đúng: C

7. Nhật ký truy cập liên tục tăng chiếm dung lượng ổ. Chính sách vận hành phù hợp là gì?
A. Xóa toàn bộ log cũ mỗi ngày mà không xét thời hạn pháp lý.
B. Thiết lập retention, lưu trữ log và yêu cầu kiểm toán.
C. Chỉ ghi log khi DB dừng để giảm lượng dữ liệu phải lưu.
D. Dồn log truy cập vào bảng giao dịch mà không đặt retention.
Đáp án đúng: B

8. Các job backup ở nhiều múi giờ cần đối chiếu thời điểm sự cố. Cách ghi thời gian nào ít nhầm lẫn?
A. Lưu UTC và ghi rõ múi giờ khi hiển thị bản ghi.
B. Ghi giờ địa phương nhưng bỏ thông tin độ lệch múi giờ.
C. Ghi giờ mặc định của máy chủ mà không ghi tên vùng giờ.
D. Ghi ngày trong tên máy và suy ra giờ khi khôi phục.
Đáp án đúng: A

9. Dịch vụ báo cáo chỉ cần SELECT trên hai bảng. Nên cấp quyền bằng cách nào?
A. Cấp SELECT trên hai bảng qua role báo cáo riêng biệt.
B. Role chung có quyền ghi trên toàn bộ schema của ứng dụng.
C. Role sở hữu database để thuận tiện cho dịch vụ báo cáo.
D. Role quản trị chỉ giới hạn bằng kiểm tra phía ứng dụng.
Đáp án đúng: A

10. Kỹ sư cần điều tra dữ liệu production trong thời gian ngắn. Cách cấp quyền phù hợp?
A. Cấp quyền chủ sở hữu với tài khoản chia sẻ trong nhóm.
B. Cấp quyền ghi lâu dài để tiện sửa khi phát hiện bất thường.
C. Cấp quyền đọc cho toàn công ty và kiểm soát qua VPN.
D. Cấp quyền đọc có thời hạn, định danh riêng và ghi audit.
Đáp án đúng: D

11. Một password kết nối DB đã xuất hiện trong commit công khai. Việc xử lý trực tiếp nhất?
A. Xóa dòng chứa password khỏi nhánh chính rồi giữ khóa cũ.
B. Đổi tên database rồi tiếp tục dùng bí mật đã bị công khai.
C. Thêm tệp vào .gitignore nhưng giữ nguyên thông tin truy cập.
D. Thu hồi hoặc xoay bí mật và chuyển lưu vào secret manager.
Đáp án đúng: D

12. Dịch vụ không được downtime khi xoay credential của DB. Thứ tự nào an toàn?
A. Thu hồi credential hiện tại rồi cấp khóa mới cho client.
B. Cập nhật client sang khóa mới trước khi DB chấp nhận khóa ấy.
C. Tạo credential mới, cập nhật client dần rồi thu hồi khóa cũ.
D. Cấp quyền cao hơn cho credential cũ rồi trì hoãn xoay khóa.
Đáp án đúng: C

13. Kết nối từ ứng dụng tới DB đi qua mạng không tin cậy. Chính sách TLS nào đúng?
A. Bật TLS, xác minh certificate và tên máy chủ DB.
B. Bật TLS nhưng vô hiệu hóa kiểm tra certificate máy chủ.
C. Mã hóa ở ứng dụng nhưng không xác thực kênh tới DB.
D. Dựa vào firewall thay cho xác thực đầu máy chủ DB.
Đáp án đúng: A

14. Muốn biết ai đã thay đổi quyền truy cập production lúc 14 giờ. Tín hiệu nào hữu ích nhất?
A. Đối chiếu log đăng nhập để đoán tài khoản có thể đổi quyền.
B. Tra audit GRANT/REVOKE kèm tài khoản và thời điểm.
C. So danh sách quyền trước/sau nhưng không giữ thông tin actor.
D. Dựa vào lịch triển khai để suy ra tài khoản đã cấp quyền.
Đáp án đúng: B

15. Nhân viên đã nghỉ vẫn còn phiên DB mở bằng tài khoản cũ. Cách thu hồi quyền đầy đủ hơn?
A. Đổi tên tài khoản nhưng giữ nguyên các phiên đã xác thực.
B. Xóa log đăng nhập và chỉ theo dõi những phiên tạo mới.
C. Thu hồi truy cập, xử lý phiên và xoay bí mật chung.
D. Thay hostname của dịch vụ, giữ nguyên quyền tài khoản cũ.
Đáp án đúng: C

16. Sao lưu đã mã hóa nhưng mất khóa giải mã thì hệ quả vận hành là gì?
A. Bản sao vẫn dùng được nếu chỉ nhớ mật khẩu user DB.
B. Bản sao có thể đọc được bằng việc tăng mức nén dữ liệu.
C. Mất khóa khiến backup không giải mã được để khôi phục.
D. Bản sao tự có thể giải mã từ checksum của từng trang.
Đáp án đúng: C

17. CPU DB cao đột biến cùng lúc nhiều yêu cầu chậm. Nên thu thập gì trước khi tăng máy?
A. Dựa trên tổng CPU máy chủ mà bỏ qua phân rã theo truy vấn.
B. Dựa trên tổng I/O ổ đĩa mà không nối với SQL cụ thể.
C. Dựa trên số kết nối active và giả sử mọi SQL như nhau.
D. Đối chiếu SQL theo CPU, tần suất và kế hoạch chạy.
Đáp án đúng: D

18. Thời gian chờ I/O tăng nhưng CPU DB không cao. Nguồn bằng chứng nào giúp khoanh vùng?
A. Latency đọc ghi, hàng đợi đĩa và truy vấn có nhiều I/O.
B. Tổng CPU theo giờ và số phiên đang chạy câu truy vấn.
C. Số checkpoint cùng tỷ lệ cache hit khi truy vấn chậm.
D. Mức lock wait và thời gian transaction giữ kết nối.
Đáp án đúng: A

19. Ứng dụng timeout, trong DB nhiều phiên wait trên lock nhưng CPU thấp. Hành động đầu tiên?
A. Tăng CPU ngay vì tất cả wait lock đều do thiếu bộ xử lý.
B. Xóa toàn bộ index để giảm số khóa đang sử dụng trong bảng.
C. Restart DB ngay trước khi xem phiên nào đang giữ khóa.
D. Kiểm tra phiên giữ lock, thời gian chờ và ảnh hưởng.
Đáp án đúng: D

20. DB cảnh báo cạn kết nối sau khi tăng số instance ứng dụng. Cần xem cặp chỉ số nào?
A. Tăng max_connections mà không đo phiên idle của pool.
B. Đếm request HTTP nhưng không đo pool wait tại ứng dụng.
C. So sánh CPU và đĩa mà không theo dõi số phiên DB.
D. Số phiên active/idle và pool wait theo mỗi instance.
Đáp án đúng: D

21. Replica không báo lỗi nhưng dữ liệu người dùng thấy chậm cập nhật. Cần đo điều gì?
A. Số transaction primary và dung lượng file log lưu trữ.
B. Theo dõi độ trễ gửi, nhận và apply log trên replica.
C. Cache hit của replica và thời gian đọc dữ liệu từng bảng.
D. Số phiên đọc replica và tần suất checkpoint ở primary.
Đáp án đúng: B

22. Sau đợt nhập dữ liệu, planner chọn kế hoạch sai vì ước lượng số dòng lệch lớn. Nên làm gì?
A. Tăng work_mem rồi bỏ qua thống kê số dòng hiện tại.
B. Tăng cache DB và không xem sai lệch estimated/actual rows.
C. Cập nhật thống kê và so số dòng ước lượng/thực tế.
D. Rebuild index mà không đối chiếu phân bố dữ liệu mới.
Đáp án đúng: C

23. Metric monitoring có nhãn request_id khác nhau ở mỗi request. Vấn đề nào dễ xảy ra?
A. Số series giảm do mỗi request dùng nhãn định danh riêng.
B. Số series giữ nguyên nhưng độ phân giải sample tăng.
C. Tăng số series metric, gây áp lực lưu trữ và truy vấn.
D. Số sample tăng trong khi series không đổi theo request_id.
Đáp án đúng: C

24. Health check chỉ trả OK khi mở được TCP port, nhưng giao dịch ghi đang thất bại. Nên cải tiến gì?
A. Thêm readiness kiểm tra khả năng phục vụ nghiệp vụ.
B. Tăng timeout TCP để giảm cảnh báo khi hệ thống quá tải.
C. Đổi cổng probe nhưng vẫn kiểm tra mở kết nối TCP.
D. Dùng trạng thái tiến trình thay cho thử nghiệp vụ ghi.
Đáp án đúng: A

25. Dung lượng đĩa DB tăng đều 10% mỗi tháng. Dự báo nâng dung lượng nên tính thêm gì?
A. Dự báo từ mức đầy hiện tại nhưng bỏ xu hướng tăng.
B. Dự báo theo số bảng mới và bỏ lưu lượng truy cập.
C. Dự báo theo log chậm nhưng bỏ dung lượng bảng/index.
D. Dự báo tăng trưởng, headroom và không gian bảo trì.
Đáp án đúng: D

26. Có một full backup chủ nhật và incremental mỗi ngày. Phục hồi tới thứ tư cần gì?
A. Khôi phục incremental thứ tư như một bản sao đầy đủ.
B. Khôi phục full chủ nhật và bỏ qua dữ liệu phát sinh.
C. Ghép full chủ nhật với incremental gần nhất bất kỳ.
D. Full chủ nhật và các incremental nối tiếp tới thứ tư.
Đáp án đúng: D

27. Sao chép thô file dữ liệu DB khi hệ thống vẫn ghi có thể làm backup lỗi vì sao?
A. Trang dữ liệu luôn tự khóa toàn hệ khi tiến trình copy mở file.
B. Trang và log có thể không cùng điểm nhất quán nếu thiếu cơ chế DB.
C. Hệ thống tự bảo đảm snapshot nhất quán ở mọi lệnh copy file.
D. Chỉ file chỉ mục thay đổi trong khi các file dữ liệu đứng yên.
Đáp án đúng: B

28. Có base backup và transaction log liên tục. Muốn phục hồi trước lệnh DELETE nhầm phải làm gì?
A. Dùng bản dump đã tạo sau DELETE rồi replay tới hiện tại.
B. Khôi phục base backup rồi replay log tới mốc trước DELETE.
C. Dùng một replica đã nhận DELETE rồi promote ngay lập tức.
D. Chạy rebuild index để khôi phục các dòng đã bị xóa.
Đáp án đúng: B

29. Chuỗi archive log bị thiếu một đoạn giữa hai mốc backup. Hậu quả với PITR là gì?
A. Vẫn replay được mọi mốc nếu bản backup full đủ lớn.
B. Phục hồi tới mốc mong muốn bằng snapshot dữ liệu cuối.
C. Phục hồi từ backup logic mà không cần chuỗi log.
D. Có thể không replay liên tục qua đoạn thiếu để đạt mốc mong muốn.
Đáp án đúng: D

30. Hệ thống đặt RPO là 15 phút. Điều kiện nghiệm thu nào diễn đạt chính xác?
A. Dữ liệu mất tối đa 15 phút tính từ thời điểm sự cố.
B. Dịch vụ phải mở lại tối đa 15 phút tính từ lúc phát hiện.
C. Bản backup phải chạy đúng mỗi 15 phút, không cần kiểm thử.
D. Replica phải cách primary tối đa 15 phút, kể cả khi đã mất log.
Đáp án đúng: A

31. Hệ thống cam kết RTO một giờ. Kiểm thử nên đo khoảng thời gian nào?
A. Từ backup gần nhất đến thời điểm transaction cuối được ghi.
B. Từ sự cố đến khi dịch vụ trở lại mức hoạt động chấp nhận được.
C. Từ lúc chạy query tới lúc query nhanh nhất được trả về.
D. Từ khi mở dashboard đến khi cảnh báo đầu tiên được phát.
Đáp án đúng: B

32. Cháy toàn bộ một vùng đặt máy chủ DB và bản backup cục bộ. Thiết kế nào giảm rủi ro?
A. Giữ nhiều bản sao cùng ổ đĩa để tăng số lượng bản backup.
B. Giữ backup trên primary rồi đặt lịch nén mỗi ngày.
C. Giữ bản snapshot cùng trung tâm và dùng chung tài khoản xóa.
D. Giữ bản sao ngoài vùng lỗi với quyền tách biệt và thử restore.
Đáp án đúng: D

33. Định kỳ diễn tập khôi phục từ backup, tiêu chí PASS mạnh nhất là gì?
A. Restore cô lập và kiểm tra dữ liệu, ứng dụng, RPO/RTO thực tế.
B. Job backup đã báo success và kích thước tệp khá lớn.
C. File backup mở được trong trình quản lý tệp trên server.
D. Số lượng file backup đúng kế hoạch dù chưa từng restore.
Đáp án đúng: A

34. Ransomware có quyền xóa backup trực tuyến. Biện pháp nào tăng khả năng phục hồi?
A. Dùng bản sao bất biến với quyền xóa tách biệt khỏi production.
B. Mã hóa backup nhưng giữ quyền xóa chung với production.
C. Tăng số backup nhưng lưu cùng nơi và cùng quyền xóa.
D. Nhân bản đồng bộ dữ liệu sang cùng vùng bị ảnh hưởng.
Đáp án đúng: A

35. Backup incremental nhiều ngày phụ thuộc nhau. Cách kiểm chứng chuỗi trước khi cần restore?
A. Kiểm tra kích thước file incremental cuối của chuỗi.
B. Kiểm tra đủ mắt xích và định kỳ restore thử toàn chuỗi.
C. Kiểm tra full đầu chuỗi rồi loại bỏ bản tăng dần đã cũ.
D. Đếm file theo lịch backup mà không restore đọc thử.
Đáp án đúng: B

36. Primary hỏng khi replica bất đồng bộ chưa nhận hết log. Rủi ro nào cần chấp nhận trong RPO?
A. Không mất bản ghi đã ACK vì replica luôn đồng bộ trước commit.
B. Mất phần cache ứng dụng nhưng toàn bộ commit vẫn đã có.
C. Có thể mất bản ghi đã ACK mà replica chưa nhận hoặc apply.
D. Mất giao dịch chưa COMMIT nhưng giữ mọi bản ghi đã ACK.
Đáp án đúng: C

37. Replication đồng bộ thường ảnh hưởng đến độ trễ giao dịch ghi theo cơ chế nào?
A. COMMIT có thể chờ replica xác nhận theo mức bền đã chọn.
B. COMMIT luôn hoàn tất trước khi replica nhận bất kỳ thay đổi nào.
C. COMMIT đợi backup full mới bắt đầu phản hồi cho ứng dụng.
D. COMMIT tự chuyển thành transaction chỉ đọc khi replica chậm.
Đáp án đúng: A

38. Ứng dụng yêu cầu đọc thấy bản ghi vừa ghi, nhưng đang đọc qua replica trễ. Cách xử lý phù hợp?
A. Tăng số replica rồi chọn ngẫu nhiên bất kể độ trễ log.
B. Đọc từ primary hoặc chờ replica tới vị trí log của lần ghi.
C. Chỉ thêm index ở replica và giữ chính sách đọc cũ.
D. Tắt mọi ghi trong hệ thống cho tới khi replica bắt kịp.
Đáp án đúng: B

39. Trong failover có nguy cơ primary cũ vẫn cho ghi trong khi node mới đã promote. Cần làm gì?
A. Cho cả hai node nhận ghi rồi hợp nhất dữ liệu sau sự cố.
B. Đổi DNS sang node mới dù node cũ vẫn nhận request ghi.
C. Cô lập primary cũ trước khi bật ghi trên primary mới.
D. Chỉ tăng tốc heartbeat mà không giới hạn quyền ghi node cũ.
Đáp án đúng: C

40. Sau khi promote standby thành primary, bước xác minh đầy đủ nào nên có?
A. Kiểm tra hostname mới đã ping được từ mọi ứng dụng.
B. Kiểm tra khả năng ghi, mất log và topology kết nối.
C. Xác nhận DB trên node mới đã lên và nhận kết nối TCP.
D. Tăng pool kết nối rồi kiểm tra một truy vấn đọc nhẹ.
Đáp án đúng: B

41. Nâng major version hệ quản trị với downtime nhỏ, bước chuẩn bị nào quan trọng nhất?
A. Nâng trực tiếp production rồi kiểm tra tương thích sau.
B. Bỏ qua plugin và driver vì mọi major version giữ ABI.
C. Diễn tập trên bản sao và kiểm tra driver, extension, schema.
D. Tăng RAM node mới rồi chạy migration lúc cao điểm.
Đáp án đúng: C

42. Cần thêm cột NOT NULL vào bảng lớn đang phục vụ client cũ. Cách triển khai schema nào hợp lý?
A. Xóa cột cũ trước khi client nâng cấp để giảm dung lượng.
B. Thêm cột bắt buộc và cập nhật toàn bảng trong một khóa dài.
C. Thêm cột tương thích, backfill từng phần rồi siết ràng buộc.
D. Dừng mọi client cũ ngay khi bắt đầu tiến hành deploy schema.
Đáp án đúng: C

43. Tạo index cho bảng rất lớn trong giờ chạy, muốn giảm gián đoạn. Tiêu chí chọn cách tạo nào đúng?
A. Khóa toàn bảng đến khi xây xong dù truy vấn không dùng index.
B. Ưu tiên tạo online/concurrent nếu DB hỗ trợ, theo dõi tài nguyên.
C. Bỏ theo dõi log vì việc tạo index không gây ảnh hưởng I/O.
D. Restart máy ngay sau CREATE INDEX mà không kiểm tra trạng thái.
Đáp án đúng: B

44. Mỗi thay đổi cấu hình production cần có điều kiện rollback. Cách đặt điều kiện nào đo được?
A. Căn cứ cảm nhận người triển khai về sự ổn định.
B. Theo dõi số dòng cấu hình vừa đổi thay cho metric.
C. Đặt ngưỡng p95, lỗi, lock wait và thời hạn quan sát cụ thể.
D. Xem CPU trung bình rồi suy ra tỷ lệ lỗi và độ trễ.
Đáp án đúng: C

45. Sau release, lỗi deadlock tăng mạnh dù CPU DB vẫn thấp. Bước chẩn đoán và sửa nào có cơ sở?
A. Xem graph deadlock, thống nhất thứ tự khóa và retry.
B. Tăng lock timeout và giữ nguyên thứ tự cập nhật dữ liệu.
C. Tăng số connection để các giao dịch chờ khóa ngắn hơn.
D. Giảm log deadlock và tăng kích thước pool của ứng dụng.
Đáp án đúng: A

46. Ổ đĩa DB sắp đầy do transaction log chưa được dọn. Hành động an toàn trước tiên?
A. Xóa thủ công mọi log chưa archive để có ngay dung lượng.
B. Vô hiệu transaction log rồi tiếp tục nhận giao dịch ghi.
C. Đổi tên thư mục log rồi bỏ qua tác vụ replication đang chạy.
D. Xác định nguyên nhân giữ log, giải phóng an toàn và bảo vệ PITR.
Đáp án đúng: D

47. Sau khôi phục từ backup, ứng dụng trả HTTP 200. Cần kiểm tra thêm gì để công nhận phục hồi?
A. Kiểm tra dữ liệu phục hồi và mức mất ghi với RPO.
B. Đo số kết nối thành công và mã HTTP của ứng dụng.
C. Kiểm tra kết nối mạng tới host và khả năng ping.
D. Xác nhận service healthy mà chưa đối chiếu dữ liệu.
Đáp án đúng: A

48. Sau sự cố downtime kéo dài, đầu ra postmortem nào giúp giảm lặp lại tốt nhất?
A. Danh sách người trực ca cùng nhận xét không gắn số liệu.
B. Ảnh dashboard cuối sự cố mà không có trình tự thay đổi.
C. Dòng thời gian, ảnh hưởng, bằng chứng và hành động có owner.
D. Báo cáo backup tháng trước mà bỏ qua nguyên nhân sự cố.
Đáp án đúng: C
