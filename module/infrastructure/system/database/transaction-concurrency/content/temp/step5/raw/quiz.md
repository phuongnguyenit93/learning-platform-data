1. Chuyển tiền trừ tài khoản A thành công nhưng cộng tài khoản B thất bại. Thuộc tính ACID nào đòi hủy cả hai thao tác?
A. Consistency: các ràng buộc dữ liệu luôn được kiểm tra.
B. Isolation: các phiên không thấy ghi chưa được commit.
C. Atomicity: các thao tác cùng commit hoặc cùng rollback.
D. Durability: dữ liệu đã commit vẫn bền qua sự cố.
Đáp án đúng: C

2. Tồn kho không được âm sau COMMIT. Thiết kế nào trực tiếp bảo vệ tính nhất quán của giao dịch?
A. Tăng buffer cache để mọi lệnh cập nhật chạy nhanh hơn.
B. Đọc từ replica để phát hiện những thay đổi chưa commit.
C. Ràng buộc CHECK cùng logic nghiệp vụ giữ tồn kho hợp lệ.
D. Thêm chỉ mục thường trên tồn kho mà bỏ kiểm tra miền giá trị.
Đáp án đúng: C

3. Phiên T1 đang cập nhật nhưng chưa COMMIT; phiên T2 không được đọc thay đổi này. Thuộc tính ACID liên quan nhất là gì?
A. Isolation: ngăn phiên khác quan sát ghi chưa commit.
B. Atomicity: hoàn tất mọi câu lệnh như một đơn vị.
C. Consistency: ràng buộc giá trị hợp lệ sau giao dịch.
D. Durability: ghi kết quả commit bền vững qua crash.
Đáp án đúng: A

4. DB đã xác nhận COMMIT rồi máy chủ gặp crash. Thuộc tính ACID nào yêu cầu thay đổi đã xác nhận vẫn được bảo toàn?
A. Atomicity: hủy nhóm thao tác nếu một bước thất bại.
B. Isolation: các phiên nhìn dữ liệu theo mức cô lập.
C. Durability: giữ kết quả commit sau khi khởi động lại.
D. Consistency: mỗi trạng thái hoàn tất tuân quy tắc.
Đáp án đúng: C

5. Khi ghi hóa đơn và các dòng hóa đơn, ứng dụng muốn tránh hóa đơn thiếu dòng nếu lỗi giữa chừng. Cần làm gì?
A. Ghi hóa đơn trước rồi đợi job hằng ngày bù các dòng bị thiếu.
B. Cho từng INSERT tự COMMIT rồi dựa trên chỉ mục để nối dữ liệu.
C. Tăng transaction timeout để mọi lệnh chắc chắn chạy thành công.
D. Đặt các ghi liên quan vào cùng transaction, rollback khi lỗi.
Đáp án đúng: D

6. Trong giao dịch nhập hàng, bước cuối bị lỗi nhưng hai bước đầu cần được giữ để tiếp tục. Nên dùng cơ chế nào?
A. COMMIT toàn bộ trước bước cuối rồi bỏ trạng thái transaction.
B. Đổi mức cô lập để tự hủy riêng lệnh cuối mà giữ kết quả.
C. Khởi động một phiên DB khác để undo từng câu lệnh đã chạy.
D. Tạo SAVEPOINT trước bước cuối rồi ROLLBACK TO SAVEPOINT.
Đáp án đúng: D

7. Một transaction chuyển tiền đã COMMIT nhưng tổng số dư bị sai vì code tính phí lỗi. Nhận xét nào đúng về ACID?
A. Cần mã hóa invariant nghiệp vụ; ACID không sửa logic sai.
B. Atomicity tự động kiểm tra tổng số dư của mọi tài khoản.
C. Durability tự động đối chiếu số dư sau mỗi lần commit.
D. Isolation tự động tính lại mọi công thức nghiệp vụ đã ghi.
Đáp án đúng: A

8. Client gửi lệnh thanh toán, mất kết nối trước khi nhận phản hồi COMMIT. Cách retry giảm nguy cơ tính tiền hai lần là gì?
A. Gửi lại lệnh không định danh và tin rằng lần đầu đã rollback.
B. Đổi transaction isolation rồi phát lại lệnh theo session mới.
C. Dùng khóa idempotency để kiểm tra hoặc lặp lại an toàn.
D. Tăng connection pool để hệ thống tự hủy lệnh chưa được ACK.
Đáp án đúng: C

9. T1 cập nhật số dư nhưng chưa COMMIT; T2 đọc giá trị mới rồi T1 ROLLBACK. T2 đã gặp bất thường nào?
A. Dirty read: đọc thay đổi mà giao dịch ghi chưa commit.
B. Phantom read: tập dòng thỏa điều kiện có thêm bản ghi.
C. Lost update: hai phép ghi đè làm mất một thay đổi.
D. Write skew: hai ghi khác dòng vi phạm bất biến chung.
Đáp án đúng: A

10. Trong cùng transaction, T1 đọc giá sản phẩm hai lần; T2 COMMIT đổi giá giữa hai lần đọc. Hiện tượng nào xảy ra nếu T1 thấy hai giá khác nhau?
A. Dirty read: đọc giá chưa được phiên thay đổi commit.
B. Phantom read: số dòng thỏa điều kiện tăng lên.
C. Write skew: hai transaction sửa các dòng khác nhau.
D. Non-repeatable read: cùng dòng bị phiên khác sửa giữa hai lần.
Đáp án đúng: D

11. T1 hai lần đếm đơn có status='open'; giữa hai lần T2 INSERT đơn open và COMMIT. Nếu kết quả đếm khác, đó là gì?
A. Non-repeatable read: cùng một dòng bị đổi giá trị.
B. Dirty read: T1 thấy một lệnh ghi chưa được COMMIT.
C. Lost update: hai phiên ghi đè giá trị một dòng.
D. Phantom read: tập dòng thỏa predicate đã thay đổi.
Đáp án đúng: D

12. Hai phiên cùng đọc stock=10, mỗi phiên trừ 1 bằng cách ghi stock=9. Sau hai COMMIT stock vẫn 9. Đây là gì?
A. Dirty read: một phiên đã thấy giá trị chưa commit.
B. Phantom read: tập sản phẩm tăng thêm một phần tử.
C. Lost update: phép ghi sau xóa hiệu ứng của phép ghi trước.
D. Read skew: hai cột của cùng bảng được đọc khác lúc.
Đáp án đúng: C

13. Có hai bác sĩ A/B cùng trực; mỗi phiên thấy cả hai đang trực rồi tắt lịch trực của chính mình. Cuối cùng không ai trực. Đây là gì?
A. Lost update: hai phiên cùng ghi đè một dòng bác sĩ.
B. Dirty read: một phiên đọc ghi chưa commit của bên kia.
C. Non-repeatable read: cùng dòng được đọc thấy giá trị khác.
D. Write skew: cập nhật khác dòng phá vỡ bất biến chung.
Đáp án đúng: D

14. T1 đọc số dư A trước chuyển khoản, rồi số dư B sau khi T2 chuyển từ A sang B và COMMIT. Tổng sai tạm thời. Bất thường này là gì?
A. Lost update: hai transaction ghi đè cùng một số dư.
B. Dirty write: một transaction sửa dòng chưa commit.
C. Read skew: hai giá trị được đọc từ hai snapshot khác nhau.
D. Phantom read: tập dòng tài khoản có thêm bản ghi.
Đáp án đúng: C

15. Ở READ COMMITTED kiểu PostgreSQL, hai SELECT liên tiếp trong một transaction thường lấy dữ liệu thế nào?
A. Mỗi câu lệnh nhận snapshot mới tại lúc lệnh bắt đầu.
B. Hai SELECT dùng snapshot cố định từ khi transaction mở.
C. SELECT sau có thể đọc dữ liệu chưa commit của phiên khác.
D. Mọi SELECT khóa hàng đã đọc đến khi transaction kết thúc.
Đáp án đúng: A

16. Ở PostgreSQL REPEATABLE READ, phát biểu nào về snapshot và write skew là chính xác?
A. Mỗi lệnh lấy snapshot mới và luôn chặn mọi write skew.
B. Giữ snapshot ổn định nhưng vẫn có thể gặp write skew.
C. Các lệnh SELECT khóa toàn bộ dòng dữ liệu đã truy cập.
D. Mức cô lập này tương đương SERIALIZABLE cho mọi bất biến.
Đáp án đúng: B

17. Đâu là yêu cầu cốt lõi của mức cô lập SERIALIZABLE khi giao dịch chạy đồng thời?
A. Mọi SELECT nhìn được thay đổi đã COMMIT ngay lập tức.
B. Giao dịch được COMMIT theo đúng thứ tự chúng bắt đầu.
C. Kết quả tương đương một thứ tự thực thi tuần tự hợp lệ.
D. Từng câu lệnh chạy riêng lẻ và bỏ qua dữ liệu phiên khác.
Đáp án đúng: C

18. Hai giao dịch SERIALIZABLE xung đột, DB hủy một giao dịch với lỗi serialization. Ứng dụng nên làm gì?
A. Retry riêng câu lệnh cuối trong transaction đã bị hủy.
B. Ghi đè kết quả bằng UPDATE mới không cần kiểm tra nữa.
C. Retry toàn bộ transaction sau lỗi theo chính sách hữu hạn.
D. Đổi mọi transaction sang READ UNCOMMITTED để tránh lỗi.
Đáp án đúng: C

19. Hai phiên cùng thấy email chưa tồn tại rồi cùng INSERT. Kiểm tra nào phải cưỡng chế tại DB để tránh trùng?
A. UNIQUE constraint trên email và xử lý conflict khi INSERT.
B. SELECT kiểm tra email trước INSERT ở ứng dụng mỗi phiên.
C. INDEX thường trên email và chặn trùng bằng điều kiện WHERE.
D. Cache danh sách email đang có ở mỗi worker của hệ thống.
Đáp án đúng: A

20. Nhiều phiên tăng cùng một counter; thao tác nào giảm rủi ro lost update thay cho đọc rồi ghi giá trị mới?
A. SELECT value trước rồi UPDATE bằng value+1 tại client.
B. Gửi hai UPDATE value=giá_trị_cũ+1 theo thứ tự.
C. UPDATE counter SET value=value+1 trong một lệnh ghi.
D. Đọc counter từ replica rồi ghi lại kết quả lên primary.
Đáp án đúng: C

21. Ứng dụng dùng version để chỉnh hồ sơ theo optimistic locking. UPDATE nào phát hiện hồ sơ bị người khác đổi?
A. UPDATE ... WHERE id=? và bỏ điều kiện version ở câu ghi.
B. UPDATE ... WHERE version=? mà không lọc khóa hồ sơ.
C. UPDATE ... WHERE id=? và đặt version về giá trị ban đầu.
D. UPDATE ... WHERE id=? AND version=?, đồng thời tăng version.
Đáp án đúng: D

22. Khi UPDATE ... WHERE id=? AND version=? ảnh hưởng 0 dòng, cách diễn giải phù hợp nhất là gì?
A. Lệnh đã thành công vì update 0 dòng nghĩa là không đổi.
B. Dữ liệu có thể đã đổi; cần đọc lại và xử lý xung đột.
C. Mọi lỗi đều do deadlock nên cần restart toàn bộ DB.
D. Dòng chắc chắn bị xóa và không cần kiểm tra phiên bản.
Đáp án đúng: B

23. Hai phiên cần sửa cùng một tài khoản, phải đọc trạng thái hiện tại trước khi ghi. Biện pháp bi quan nào phù hợp?
A. SELECT ... FOR UPDATE để khóa dòng trong transaction.
B. SELECT ... FOR SHARE rồi cho cả hai phiên ghi đồng thời.
C. SELECT thường rồi đợi sau COMMIT mới sửa giá trị.
D. SELECT từ replica rồi khóa bảng báo cáo trước khi ghi.
Đáp án đúng: A

24. Trong PostgreSQL MVCC, T1 giữ row lock FOR UPDATE trên dòng X. Điều gì xảy ra với SELECT thường của T2?
A. SELECT thường phải chờ row lock của T1 được giải phóng.
B. SELECT thường bị chuyển thành SELECT FOR UPDATE tự động.
C. SELECT thường vẫn đọc phiên bản nhìn thấy theo snapshot.
D. SELECT thường bỏ qua toàn bộ dòng đang có row lock.
Đáp án đúng: C

25. Với khóa Shared (S) và Exclusive (X) thông dụng, cặp nào tương thích trên cùng tài nguyên?
A. Hai exclusive lock có thể cùng ghi một dòng dữ liệu.
B. Hai shared lock có thể cùng giữ khi chưa có exclusive lock.
C. Một shared và một exclusive cùng giữ trên một dòng.
D. Mọi exclusive lock tự chuyển thành shared khi có reader.
Đáp án đúng: B

26. Từ khóa toàn bảng sang khóa từng dòng thường có tác động nào khi workload ghi ở các dòng khác nhau?
A. Giữ nguyên phạm vi chặn nhưng giảm số lượng index phải dùng.
B. Ngăn toàn bộ deadlock vì mỗi phiên chỉ giữ khóa một dòng.
C. Giảm ghi chặn nhau trên các dòng khác nhau, tốn thêm khóa.
D. Tăng khóa bảng bắt buộc để tránh các phiên ghi song song.
Đáp án đúng: C

27. T1 giữ lock A rồi chờ B; T2 giữ lock B rồi chờ A. Đây là tình huống gì?
A. Lock timeout vì hai phiên đều vượt thời gian chờ cấu hình.
B. Lost update vì hai phiên cùng ghi một phiên bản dữ liệu.
C. Phantom read vì T2 thêm dòng mới trùng điều kiện lọc.
D. Deadlock vì tồn tại chu trình phụ thuộc chờ khóa.
Đáp án đúng: D

28. Hai giao dịch cần khóa dòng A và B. Cách giảm xác suất deadlock khi cùng xử lý hai dòng?
A. Một giao dịch khóa A rồi B, giao dịch kia khóa B rồi A.
B. Mỗi giao dịch lấy khóa bất kỳ theo kết quả truy vấn đầu.
C. Giao dịch khóa một dòng rồi ngủ ngẫu nhiên trước dòng sau.
D. Các giao dịch lấy khóa A rồi B theo cùng một thứ tự.
Đáp án đúng: D

29. DB phát hiện deadlock và chọn một transaction làm victim. Ứng dụng cần làm gì với giao dịch nạn nhân?
A. Rollback và retry toàn bộ transaction theo giới hạn đặt ra.
B. COMMIT phần ghi đã thực hiện trong transaction lỗi.
C. Retry riêng lệnh đang chờ khóa trên phiên đã thất bại.
D. Bỏ transaction và giữ các thay đổi trước khi bị khóa.
Đáp án đúng: A

30. Một transaction chờ khóa quá lâu và bị lock timeout, nhưng không có chu trình chờ. Nhận xét nào đúng?
A. Lock timeout chỉ xảy ra khi deadlock detector tìm thấy vòng.
B. Lock timeout đồng nghĩa mọi dữ liệu transaction bị mất bền.
C. Lock timeout chứng minh optimizer chọn sai chỉ mục.
D. Lock timeout có thể xảy ra ngay cả khi không có deadlock.
Đáp án đúng: D

31. Một giao dịch mở lâu khi đang gọi API ngoài, khiến nhiều phiên ghi chờ khóa. Hướng sửa hữu ích nhất?
A. Tăng timeout giữ lock để phiên chờ lâu mà không báo lỗi.
B. Đưa gọi mạng ra ngoài transaction để giảm thời gian giữ khóa.
C. Chuyển cả thao tác API thành câu lệnh SELECT bên trong DB.
D. Tăng số worker ghi đồng thời nhưng giữ nguyên transaction.
Đáp án đúng: B

32. Một counter chung bị hàng trăm worker UPDATE liên tục và trở thành hot row. Cách giảm tranh chấp là gì?
A. Phân tán counter qua nhiều shard rồi tổng hợp khi đọc.
B. Thêm nhiều index mới trên dòng counter đang bị tranh chấp.
C. Mọi worker đọc counter từ replica rồi ghi lên cùng dòng.
D. Giữ lock dòng counter lâu hơn để hạn chế số lần cập nhật.
Đáp án đúng: A

33. Các worker nhận tác vụ từ queue DB, muốn bỏ qua task đã bị worker khác khóa. Dùng gì?
A. SELECT ... FOR UPDATE NOWAIT để tự bỏ qua các task khóa.
B. SELECT ... FOR SHARE để tự nhận quyền cập nhật mọi task.
C. SELECT ... DISTINCT để loại trùng task đã bị khóa.
D. SELECT ... FOR UPDATE SKIP LOCKED để lấy task chưa khóa.
Đáp án đúng: D

34. Cần thử khóa một dòng ngay; nếu khóa đang bận thì trả lỗi tức thời để xử lý. Chọn gì?
A. SELECT ... FOR UPDATE SKIP LOCKED để báo lỗi khi khóa bận.
B. SELECT ... FOR UPDATE NOWAIT để báo lỗi khi khóa đang bận.
C. SELECT thường rồi tăng statement timeout để phát lỗi tức thì.
D. SELECT ... FOR SHARE để đợi ghi xong rồi mới đọc dữ liệu.
Đáp án đúng: B

35. Sử dụng SKIP LOCKED cho hàng đợi có thể gây nhược điểm nào nếu một task liên tục bị khóa?
A. Task luôn được lấy đầu tiên vì nó từng có row lock.
B. Task có thể bị bỏ qua lâu và khó bảo đảm xử lý công bằng.
C. Mọi worker sẽ chờ task bị khóa dù đã bật SKIP LOCKED.
D. Các task khác không thể COMMIT khi task đầu tiên bị khóa.
Đáp án đúng: B

36. Hai phiên cùng kiểm tra COUNT(*) WHERE status='active' rồi thêm người active khi còn dưới giới hạn. Để giữ giới hạn nghiêm, nên làm gì?
A. Dùng SERIALIZABLE kèm retry hoặc khóa bảo vệ bất biến.
B. Dùng READ COMMITTED và tin rằng COUNT khóa cả tập dòng.
C. Dùng READ UNCOMMITTED để thấy mọi lượt thêm tạm thời.
D. Dùng INDEX thường trên status và bỏ kiểm tra xung đột.
Đáp án đúng: A

37. Khi UPDATE trong DB dùng MVCC như PostgreSQL, tác động cơ bản lên dòng dữ liệu là gì?
A. Sửa trực tiếp mọi phiên bản cũ để mọi transaction thấy ngay.
B. Khóa toàn bảng và xóa phiên bản cũ trước khi commit.
C. Chỉ thay đổi bản sao trong cache cho tới khi hết lock.
D. Tạo row version mới, giữ bản cũ cho snapshot còn cần.
Đáp án đúng: D

38. T1 đang có snapshot cũ; T2 COMMIT một INSERT mới. SELECT trong T1 ở snapshot cũ thấy gì?
A. Thấy INSERT mới ngay vì T2 đã xác nhận COMMIT.
B. Không thấy INSERT mới nếu snapshot được giữ nguyên.
C. Thấy INSERT mới nếu T1 từng khóa một dòng bất kỳ.
D. Thấy INSERT mới nếu T1 chỉ chạy truy vấn SELECT.
Đáp án đúng: B

39. Một transaction đọc giữ snapshot nhiều giờ. Vì sao hệ MVCC có thể tích tụ dead tuple?
A. Checkpoint tạm dừng vì snapshot yêu cầu flush mọi trang.
B. Phiên bản cũ chưa được dọn vì snapshot còn có thể cần.
C. Các UPDATE không tạo phiên bản mới trong thời gian này.
D. Deadlock detector giữ lại tuple vì chưa tìm vòng chờ.
Đáp án đúng: B

40. Đội ngũ cần bảo vệ bất biến liên quan hai dòng, nhưng hai phiên có thể ghi hai dòng khác nhau. Lựa chọn nào mạnh nhất?
A. READ COMMITTED cùng index trên từng dòng được ghi.
B. READ UNCOMMITTED với timeout rất thấp cho các phiên.
C. Autocommit từng lệnh cập nhật ở mỗi dòng độc lập.
D. Dùng SERIALIZABLE và retry khi xung đột ràng buộc.
Đáp án đúng: D

41. DB trả lỗi serialization_failure khi COMMIT. Quy tắc retry nào phù hợp để đảm bảo quyết định nghiệp vụ đúng?
A. Chạy lại toàn transaction gồm bước đọc quyết định và ghi.
B. Chạy lại mỗi COMMIT với cùng snapshot đã bị từ chối.
C. Chỉ chạy lại lệnh INSERT cuối mà bỏ qua logic kiểm tra.
D. Giữ cache đọc cũ rồi cập nhật thêm một lần lên DB.
Đáp án đúng: A

42. Nhiều client gặp conflict cùng lúc rồi retry tức thì, khiến tắc nghẽn kéo dài. Chiến lược nào tốt hơn?
A. Retry ngay vô hạn với cùng khoảng thời gian giữa các phiên.
B. Exponential backoff với jitter và số lần thử tối đa.
C. Tăng thread retry cho tới khi tất cả transaction thành công.
D. Bật timeout bằng 0 để các retry không bao giờ phải chờ.
Đáp án đúng: B

43. Một request tạo thanh toán bị gửi lại sau timeout. Cơ chế nào chặn tạo hai giao dịch nghiệp vụ?
A. Random delay trước INSERT nhưng không lưu ID của request.
B. Idempotency key duy nhất được kiểm tra và lưu tại DB.
C. Mỗi retry sinh ID mới và coi là một lần mua riêng biệt.
D. Chuyển mức isolation thấp hơn để lệnh tạo chạy nhanh.
Đáp án đúng: B

44. Transaction ghi đơn hàng đồng thời gọi dịch vụ email; nếu retry transaction, email có thể gửi trùng. Thiết kế nào an toàn hơn?
A. Gọi email trước khi INSERT để chắc chắn thư được gửi đi.
B. Gửi email trong transaction rồi rollback cả email khi DB lỗi.
C. Ghi outbox trong transaction rồi gửi sau commit có dedupe.
D. Tăng timeout email để tránh phải retry transaction ghi đơn.
Đáp án đúng: C

45. Hai dịch vụ có database riêng và cần hoàn tác nghiệp vụ khi bước hai thất bại. Mẫu xử lý nào phù hợp?
A. Một local transaction duy nhất tự rollback cả hai database.
B. Saga có bước bù trừ và theo dõi trạng thái mỗi dịch vụ.
C. Một row lock trong DB thứ nhất sẽ khóa luôn DB thứ hai.
D. Đổi tất cả transaction thành read-only để không cần bù trừ.
Đáp án đúng: B

46. Ứng dụng làm việc nặng qua mạng trong transaction đang giữ row lock. Thay đổi nào nên ưu tiên?
A. Giữ row lock rồi gọi API nhiều lần để tránh retry.
B. Tính toán và gọi mạng trước khi vào vùng khóa ngắn.
C. Tăng số lock đồng thời mà không đổi phạm vi transaction.
D. Dùng transaction dài hơn để các phiên khỏi tranh chấp.
Đáp án đúng: B

47. Muốn tái hiện lost update trong kiểm thử, bộ bước nào đủ mạnh?
A. Cho hai phiên cùng đọc giá trị cũ rồi cập nhật xen kẽ.
B. Chạy từng giao dịch nối tiếp sau khi phiên trước COMMIT.
C. Chạy một phiên đọc SELECT nhiều lần mà không có ghi.
D. Đo throughput lúc chỉ có một transaction truy cập bảng.
Đáp án đúng: A

48. Dashboard cho thấy p95 tăng dù CPU thấp, nhiều phiên chờ khóa. Chỉ số nào giúp tìm nguyên nhân?
A. Đo lock wait, phiên chặn và tuổi transaction giữ khóa.
B. Cache hit và tổng số bảng không kèm trạng thái chờ.
C. Kích thước dữ liệu sao lưu và số file snapshot gần nhất.
D. Số kết nối TCP mà không xem truy vấn đang bị chặn.
Đáp án đúng: A
