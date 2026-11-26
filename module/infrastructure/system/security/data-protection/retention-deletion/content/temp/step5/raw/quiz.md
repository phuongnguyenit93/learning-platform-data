1. Một hồ sơ hợp đồng phải được giữ bảy năm sau khi kết thúc hiệu lực. Mốc tính hạn nào nên dùng?
A. Ngày tạo bản ghi đầu tiên trong hệ thống quản lý hợp đồng.
B. Ngày file được sao chép vào kho lưu trữ dài hạn.
C. Ngày nhân viên gần nhất mở hồ sơ trên giao diện.
D. Ngày kết thúc hợp đồng là mốc retention đã phê duyệt.
Đáp án đúng: D

2. Một hồ sơ phục vụ giao dịch và marketing có hai thời hạn khác nhau. Thiết kế nào phù hợp?
A. Giữ toàn bộ hồ sơ theo thời hạn dài nhất của mọi mục đích.
B. Xóa toàn bộ hồ sơ theo thời hạn ngắn nhất để đơn giản vận hành.
C. Tách mục đích hoặc trường dữ liệu để áp dụng lịch xóa riêng.
D. Giữ hồ sơ đến khi cả hai nhóm xác nhận không còn nhu cầu.
Đáp án đúng: C

3. Luật tại hai khu vực quy định thời hạn lưu giữ khác nhau cho cùng loại hồ sơ. Cách xử lý nào phù hợp?
A. Chọn thời hạn dài nhất cho mọi khu vực để tránh xóa quá sớm.
B. Xác định nghĩa vụ áp dụng theo phạm vi và ghi nhận quyết định.
C. Chọn thời hạn ngắn nhất toàn cầu để giảm chi phí lưu trữ.
D. Dùng thời hạn mặc định của nhà cung cấp cloud đang lưu dữ liệu.
Đáp án đúng: B

4. Một legal hold chỉ áp dụng cho hồ sơ của một khách hàng trong một khoảng thời gian. Phạm vi đóng băng nên là gì?
A. Chỉ giữ dữ liệu khớp chủ thể, loại hồ sơ và khoảng thời gian hold.
B. Đóng băng toàn bộ tenant để tránh bỏ sót tài liệu liên quan.
C. Tạm dừng mọi job retention trong hệ thống cho đến khi hold kết thúc.
D. Chỉ giữ bản ghi trong database chính và để bản sao tự hết hạn.
Đáp án đúng: A

5. Một tài liệu thuộc hai legal hold có ngày kết thúc khác nhau. Khi hold đầu tiên được giải phóng, điều gì đúng?
A. Xóa tài liệu theo ngày kết thúc của hold đầu tiên đã được giải phóng.
B. Chuyển tài liệu sang archive mới và bắt đầu lịch retention khác.
C. Giữ tài liệu thêm một chu kỳ cố định sau mỗi lần giải phóng hold.
D. Tiếp tục giữ hồ sơ đến khi mọi hold liên quan được giải phóng hết.
Đáp án đúng: D

6. Legal hold được giải phóng sau thời gian dài. Retention schedule nên tiếp tục thế nào?
A. Đặt lại ngày bắt đầu retention bằng thời điểm giải phóng hold.
B. Xóa ngay toàn bộ dữ liệu vì ngoại lệ lưu giữ đã kết thúc.
C. Tính lại hạn từ trigger gốc theo policy retention hiện hành.
D. Giữ dữ liệu vô thời hạn để tránh phát sinh một hold mới.
Đáp án đúng: C

7. Người dùng yêu cầu xóa nhưng hệ thống có nhiều định danh lịch sử. Bước nào giúp tìm đủ hồ sơ?
A. Chỉ tìm theo email hiện tại để tránh khớp nhầm người khác.
B. Liên kết các định danh đã xác minh qua subject identity map.
C. Tìm mọi bản ghi có cùng họ tên rồi xóa tất cả kết quả.
D. Dùng địa chỉ IP gần nhất làm khóa tra cứu chính của yêu cầu.
Đáp án đúng: B

8. Một phần hồ sơ phải giữ theo nghĩa vụ pháp lý sau yêu cầu xóa. Cách xử lý nào phù hợp?
A. Từ chối toàn bộ yêu cầu xóa và tiếp tục dùng hồ sơ như trước.
B. Giữ phần bắt buộc, khóa mục đích khác và ghi nhận căn cứ ngoại lệ.
C. Giữ toàn bộ tài khoản vì một trường dữ liệu còn nghĩa vụ lưu trữ.
D. Ẩn hồ sơ khỏi giao diện nhưng vẫn cho mọi dịch vụ nội bộ truy cập.
Đáp án đúng: B

9. Một bản ghi dùng chung chứa thông tin của nhiều chủ thể. Một người yêu cầu xóa dữ liệu của họ. Nên làm gì?
A. Xóa toàn bộ bản ghi dùng chung để bảo đảm yêu cầu được đáp ứng.
B. Từ chối yêu cầu vì dữ liệu có tham chiếu tới chủ thể khác.
C. Giữ nguyên bản ghi và chỉ ẩn nó khỏi tài khoản người yêu cầu.
D. Tách phần dữ liệu riêng, bảo toàn phần dùng chung cần thiết.
Đáp án đúng: D

10. Backup bất biến vẫn chứa bản ghi đã xóa. Cách nào ngăn bản ghi quay lại sau restore?
A. Khôi phục backup rồi chờ job retention kế tiếp quét lại toàn bộ.
B. Replay deletion ledger hoặc tombstone sau khi khôi phục backup.
C. Đánh dấu backup đã mã hóa nên bản ghi không thể được truy cập.
D. Tạo backup mới trước restore để bản ghi cũ bị ghi đè tự động.
Đáp án đúng: B

11. Một backup phải giữ thêm 60 ngày trước khi hết hạn. Trong thời gian đó cần kiểm soát gì?
A. Cho phép restore vào production vì backup đã bất biến và được mã hóa.
B. Xóa metadata về yêu cầu xóa để backup không tạo trạng thái mâu thuẫn.
C. Cô lập backup, giới hạn quyền khôi phục và replay deletion ledger.
D. Gia hạn backup cho đến khi mọi bản ghi bên trong được xóa vật lý.
Đáp án đúng: C

12. Primary đã xóa bản ghi nhưng read replica còn lag và API vẫn đọc từ replica. Biện pháp nào phù hợp?
A. Kiểm tra trạng thái xóa trước khi phục vụ dữ liệu từ replica.
B. Tăng thời gian chờ của client để replica tự đồng bộ trước khi trả lời.
C. Chỉ xóa bản ghi trên replica khi lag đã giảm về mức bình thường.
D. Ẩn bản ghi ở giao diện nhưng vẫn trả dữ liệu qua API nội bộ.
Đáp án đúng: A

13. Cache phân tán còn giữ dữ liệu sau khi database xóa thành công. Cách nào giảm nguy cơ phục vụ dữ liệu cũ?
A. Chờ TTL cache hết hạn rồi mới đánh dấu yêu cầu xóa hoàn tất.
B. Phát invalidation và kiểm tra tombstone hoặc version khi đọc.
C. Xóa cache ở một node điều phối và giả định các node khác tự mất key.
D. Tăng TTL để giảm tải database trong thời gian xử lý deletion.
Đáp án đúng: B

14. CDC pipeline chỉ xử lý insert và update, không chuyển delete marker sang warehouse. Cần bổ sung gì?
A. Chạy full refresh warehouse mỗi quý để loại dữ liệu đã xóa.
B. Ẩn bản ghi trong báo cáo nhưng giữ nguyên dữ liệu trong warehouse.
C. Giảm thời gian lưu của bảng staging mà không đổi luồng CDC.
D. Phát và xử lý delete event hoặc tombstone xuyên suốt pipeline.
Đáp án đúng: D

15. Một deletion message có thể được giao nhiều lần. Consumer nên được thiết kế thế nào?
A. Từ chối mọi message lặp bằng cách so sánh timestamp nhận.
B. Tạo một bản ghi xóa mới cho mỗi lần nhận message từ broker.
C. Idempotent theo event ID và trạng thái xóa của đối tượng.
D. Đánh dấu message hoàn tất trước khi thực hiện thao tác xóa.
Đáp án đúng: C

16. Database đã đánh dấu xóa nhưng publish event có thể thất bại. Mẫu nào giúp tránh mất sự kiện?
A. Ghi deletion state và outbox event trong cùng transaction.
B. Publish event trước rồi mới xóa database khi broker xác nhận.
C. Dùng cron quét toàn bộ bảng để suy ra các event bị bỏ lỡ.
D. Gọi broker và database trong cùng request để coi như atomic.
Đáp án đúng: A

17. Search index nhận update cũ sau delete mới và làm tài liệu xuất hiện lại. Kiểm soát nào phù hợp?
A. Luôn áp dụng event đến sau cùng vì thứ tự nhận là thứ tự nghiệp vụ.
B. So sánh version và từ chối update cũ hơn tombstone đã ghi.
C. Tăng refresh interval để index có thời gian gom các event liên quan.
D. Xóa index rồi tạo lại từ bản snapshot gần nhất của database.
Đáp án đúng: B

18. Queue giữ payload cá nhân lâu hơn thời hạn nghiệp vụ. Thiết kế nào giảm rủi ro?
A. Giữ nguyên payload nhưng mã hóa broker bằng khóa dùng chung.
B. Giảm payload nhạy cảm và đặt giới hạn thời gian lưu message.
C. Tăng thời gian lưu queue để consumer có thể retry khi quá tải.
D. Chỉ xóa message sau khi mọi consumer đã tải payload về local.
Đáp án đúng: B

19. Object storage bật versioning; thao tác delete chỉ tạo delete marker. Điều gì cần thêm để xóa theo policy?
A. Xử lý các version và replica theo lifecycle policy đã định.
B. Xóa delete marker để object cũ biến mất khỏi mọi version.
C. Đổi tên object rồi giữ nguyên version cũ trong bucket archive.
D. Tắt versioning sau khi delete marker được tạo thành công.
Đáp án đúng: A

20. Thiết bị offline nhiều tháng chưa nhận deletion request. Cách kiểm soát nào phù hợp?
A. Giữ dữ liệu offline vì server không thể liên lạc với thiết bị đang tắt.
B. Đồng bộ tombstone và chặn đọc dữ liệu cũ khi thiết bị kết nối lại.
C. Xóa toàn bộ dữ liệu ứng dụng mỗi khi thiết bị khởi động lại.
D. Đánh dấu request hoàn tất ngay khi server xóa bản sao trung tâm.
Đáp án đúng: B

21. Một bảng dùng chung được nhiều tenant tham chiếu. Yêu cầu xóa của một tenant cần xử lý ra sao?
A. Xóa quan hệ và phần riêng của tenant theo ownership và reference.
B. Xóa hàng dùng chung để bảo đảm tenant đó không còn tham chiếu.
C. Từ chối mọi thao tác vì bảng có dữ liệu của nhiều tenant khác.
D. Chỉ xóa cache theo tenant và giữ nguyên mọi quan hệ trong database.
Đáp án đúng: A

22. Tổ chức dùng cryptographic erasure nhưng DEK vẫn còn trong bản backup KMS. Kết luận nào đúng?
A. Việc xóa khóa chính đã đủ dù backup KMS vẫn giữ cùng DEK.
B. Backup khóa không ảnh hưởng vì ciphertext đã được chuyển sang archive.
C. Chỉ cần xóa metadata khóa trong ứng dụng mà không cần xử lý backup.
D. Dữ liệu vẫn có thể giải mã nếu còn bản sao khóa sử dụng được.
Đáp án đúng: D

23. Một khách hàng yêu cầu crypto-erasure độc lập với dữ liệu khách hàng khác. Kiến trúc khóa nào phù hợp?
A. Dùng một DEK chung và xóa khóa khi khách hàng đầu tiên yêu cầu.
B. Dùng một khóa toàn cục rồi phân biệt khách hàng bằng tên object.
C. Lưu một bản sao DEK trong từng record để việc khôi phục dễ hơn.
D. Tách DEK hoặc key-encryption key theo phạm vi khách hàng.
Đáp án đúng: D

24. Một SSD được thanh lý sau khi xóa file thông thường. Bằng chứng sanitization nào đáng tin cậy hơn?
A. Chạy lệnh delete file rồi kiểm tra thư mục không còn hiển thị.
B. Ghi đè một lần lên file logic và giả định mọi cell đã bị thay.
C. Dùng quy trình sanitize hoặc crypto erase được thiết bị hỗ trợ và xác nhận.
D. Định dạng nhanh phân vùng rồi lưu ảnh chụp màn hình kết quả.
Đáp án đúng: C

25. Hai worker retention cùng chọn một tập bản ghi hết hạn và ghi audit khác nhau. Cách nào phù hợp?
A. Cho phép cả hai worker chạy và hợp nhất audit log sau cùng.
B. Tăng số lần retry để worker hoàn thành nhanh hơn khi tranh chấp.
C. Chia danh sách theo thứ tự tên nhưng không lưu trạng thái claim.
D. Claim công việc nguyên tử bằng lease hoặc khóa theo partition.
Đáp án đúng: D

26. Deletion job timeout giữa các partition. Cơ chế nào giúp tiếp tục an toàn?
A. Lưu checkpoint và xử lý lặp idempotent theo partition.
B. Khởi chạy lại toàn bộ job từ đầu và bỏ qua kết quả lần trước.
C. Đánh dấu job hoàn tất nếu phần lớn partition đã phản hồi.
D. Tăng timeout toàn cục rồi chạy lại mà không lưu tiến độ.
Đáp án đúng: A

27. Một đợt xóa lớn gây lock kéo dài và ảnh hưởng giao dịch đang chạy. Cách giảm tác động nào phù hợp?
A. Xóa toàn bộ trong một transaction lớn để giảm số lần commit.
B. Tăng mức cô lập transaction để các thao tác xóa chạy nhanh hơn.
C. Chia batch, throttling và chọn cửa sổ tải thấp để thực thi.
D. Chạy nhiều worker đồng thời tối đa để rút ngắn thời gian xử lý.
Đáp án đúng: C

28. Retention rule mới có thể chọn nhầm dữ liệu đang legal hold. Gate nào nên có trước khi chạy thật?
A. Chạy ngay trên production rồi phục hồi từ backup nếu có lỗi.
B. Dry-run, đối soát hold và phê duyệt phạm vi xóa.
C. Tắt legal hold trong lúc chạy để policy mới được áp dụng đồng nhất.
D. Chỉ kiểm tra số lượng bản ghi dự kiến mà không xem danh sách hold.
Đáp án đúng: B

29. Một deletion request đã xóa primary nhưng một số downstream chưa phản hồi. Trạng thái nào phản ánh đúng nhất?
A. Đánh dấu completed ngay khi primary xác nhận đã xóa thành công.
B. Đánh dấu failed toàn bộ dù một số hệ thống đã xóa xong.
C. Đóng request rồi để các hệ thống downstream tự đồng bộ khi rảnh.
D. Giữ trạng thái partial hoặc pending cho tới khi đủ xác nhận.
Đáp án đúng: D

30. Báo cáo chứng minh xóa có nguy cơ tạo thêm bản sao dữ liệu nhạy cảm. Nên lưu bằng chứng gì?
A. Lưu toàn bộ bản ghi trước khi xóa để kiểm toán có thể xem lại.
B. Lưu payload gốc trong audit log rồi giới hạn quyền truy cập log.
C. Ghi correlation ID, phạm vi xóa, thời điểm và kết quả đối soát.
D. Chụp ảnh dữ liệu trước và sau khi xóa để chứng minh thay đổi.
Đáp án đúng: C

31. Một nhà cung cấp kết thúc hợp đồng nhưng bản sao vẫn còn trong backup và tài khoản hỗ trợ. Cần yêu cầu bằng chứng nào?
A. Email chung xác nhận tenant chính đã bị xóa khỏi giao diện quản trị.
B. Ảnh chụp màn hình tài khoản không còn xuất hiện trong danh sách user.
C. Xác nhận theo từng kho, bản sao, subprocessor và thời hạn hết hạn.
D. Bản kê dung lượng hiện tại thấp hơn trước khi hợp đồng kết thúc.
Đáp án đúng: C

32. Retention policy thay đổi nhưng các job cũ và mới chạy đồng thời. Metadata nào cần quản lý?
A. Tên job và thời điểm deploy gần nhất trên từng máy chủ.
B. Ngày tạo dữ liệu gốc và dung lượng còn lại của mỗi partition.
C. Số lần retry và thời lượng trung bình của các lần chạy trước.
D. Lưu policy version, effective date và version theo batch.
Đáp án đúng: D

33. Một deletion request đến cùng lúc với cập nhật hồ sơ. Cách nào ngăn cập nhật muộn tạo lại dữ liệu?
A. Dùng tombstone/version và từ chối ghi cũ sau thời điểm xóa.
B. Cho phép update hoàn tất rồi chạy deletion job lại vào cuối ngày.
C. Ưu tiên update vì bản ghi mới hơn thời điểm nhận yêu cầu xóa.
D. Khóa giao diện chỉnh sửa nhưng không kiểm soát các writer nền.
Đáp án đúng: A

34. Import job chạy lại từ file cũ và tạo lại hồ sơ đã xóa. Kiểm soát nào phù hợp?
A. Tin file import vì dữ liệu đã được phê duyệt trước lần xóa.
B. Tạo record mới với ID khác để tránh xung đột khóa chính.
C. Chỉ kiểm tra ngày file import mà không đối chiếu trạng thái xóa.
D. Kiểm tra tombstone hoặc suppression registry trước khi tạo lại.
Đáp án đúng: A

35. Dashboard retention chỉ đếm request đã đóng. Bộ chỉ số nào giúp phát hiện suy giảm thực thi?
A. Tổng request tạo mới, số user đăng nhập và dung lượng ổ đĩa.
B. Số job đã khởi chạy, CPU trung bình và số dòng log phát sinh.
C. Theo dõi backlog age, quá hạn xóa, lỗi downstream và latency.
D. Tổng dữ liệu trong database, số replica và tốc độ ghi mỗi giây.
Đáp án đúng: C

36. Kiểm toán yêu cầu chứng minh xóa mọi bản sao nhưng inventory còn thiếu. Cách báo cáo nào trung thực?
A. Nêu phạm vi đã xác minh và các giới hạn do inventory còn thiếu.
B. Khẳng định xóa hoàn tất vì database chính không còn bản ghi.
C. Dùng kết quả từ một sample nhỏ để đại diện cho mọi kho dữ liệu.
D. Bỏ qua các hệ thống không có log và chỉ báo cáo phần đã kiểm tra.
Đáp án đúng: A
