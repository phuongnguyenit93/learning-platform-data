Câu 01. BSON khác JSON thông thường ở đặc điểm nào?
A. Hỗ trợ kiểu dữ liệu riêng như ObjectId, Date và Decimal128.
B. Chỉ nhận chuỗi và số nguyên dưới dạng văn bản UTF-8.
C. Chỉ lưu giá trị number, string, boolean và null thuần túy.
D. Luôn chuyển mọi giá trị nhị phân thành chuỗi Base64.
Đáp án đúng: A

Câu 02. Trong collection chưa sharding, thuộc tính nào của trường _id là chính xác?
A. Giá trị _id được phép trùng nếu thuộc hai nhóm shard khác nhau.
B. Giá trị _id duy nhất trong collection và được lập chỉ mục.
C. Giá trị _id duy nhất cho mọi collection cùng một database.
D. Giá trị _id bắt buộc là số nguyên tăng liên tiếp từng bản ghi.
Đáp án đúng: B

Câu 03. Khi insertOne() không truyền trường _id, hành vi thường gặp là gì?
A. MongoDB lấy giá trị của trường đầu tiên làm _id mặc định.
B. Driver hoặc máy chủ bổ sung một giá trị _id cho tài liệu.
C. Driver chỉ thêm _id khi bật tuỳ chọn upsert cho thao tác.
D. MongoDB từ chối thao tác vì mỗi client phải cấp sẵn _id.
Đáp án đúng: B

Câu 04. Khi nào nên nhúng dữ liệu con vào một document MongoDB?
A. Khi dữ liệu con tăng vô hạn nhưng luôn muốn ghi vào một mảng.
B. Khi dữ liệu con được nhiều chủ thể độc lập chỉnh sửa đồng thời.
C. Khi dữ liệu con hữu hạn và thường được đọc cùng tài liệu cha.
D. Khi dữ liệu con cần được tìm riêng trên nhiều collection khác.
Đáp án đúng: C

Câu 05. Với danh sách hoạt động của người dùng tăng không giới hạn, thiết kế nào bền vững hơn?
A. Tăng giới hạn dung lượng document để chứa mọi hoạt động.
B. Dồn hoạt động vào một mảng trên document người dùng mãi.
C. Chuyển toàn bộ hoạt động thành một trường chuỗi JSON lớn.
D. Tách hoạt động thành collection riêng và liên kết qua khóa.
Đáp án đúng: D

Câu 06. Giới hạn kích thước 16 MiB trong MongoDB áp dụng trực tiếp cho gì?
A. Dung lượng của toàn bộ dữ liệu trên một phân vùng shard.
B. Kích thước của mọi kết quả trả về từ một truy vấn find().
C. Dung lượng tổng của một collection sau khi tạo các chỉ mục.
D. Kích thước của một document BSON được lưu vào collection.
Đáp án đúng: D

Câu 07. Cách nào lọc document theo trường city bên trong object profile?
A. Dùng khóa điều kiện "profile->city" trong truy vấn find().
B. Dùng khóa điều kiện "profile.city" trong truy vấn find().
C. Dùng khóa điều kiện "profile:city" trong truy vấn find().
D. Dùng khóa điều kiện "profile/city" trong truy vấn find().
Đáp án đúng: B

Câu 08. Muốn nhiều điều kiện khớp trên cùng một phần tử của mảng object, nên dùng gì?
A. Đặt các điều kiện riêng lẻ với dot notation trên mảng.
B. Đặt từng điều kiện với $in trên các trường con của mảng.
C. Đặt các điều kiện trong toán tử $elemMatch của trường mảng.
D. Đặt mỗi điều kiện vào một phép $or trên các trường của mảng.
Đáp án đúng: C

Câu 09. Trong projection chỉ bao gồm các trường muốn lấy, _id được xử lý như thế nào?
A. Trường _id được chuyển thành chuỗi nếu projection có field.
B. Trường _id vẫn được trả về trừ khi loại trừ tường minh.
C. Trường _id chỉ xuất hiện nếu truy vấn sử dụng chỉ mục _id.
D. Trường _id bị ẩn khi có bất kỳ field nào được chọn để trả.
Đáp án đúng: B

Câu 10. Với insertMany() và ordered=true, nếu một thao tác chèn bị lỗi thì sao?
A. Mọi thao tác chèn còn lại vẫn tiếp tục theo thứ tự bất kỳ.
B. Các thao tác chèn thành công trước đó tự rollback toàn bộ.
C. MongoDB tự bỏ tài liệu lỗi và ghi tiếp trong cùng transaction.
D. Các thao tác chèn sau lỗi sẽ không tiếp tục được thực hiện.
Đáp án đúng: D

Câu 11. Ý nghĩa của $set trong updateOne() là gì?
A. Tăng các trường kiểu số thêm một đơn vị cho mỗi lần cập nhật.
B. Đặt giá trị cho trường chỉ định và giữ các trường còn lại.
C. Thay toàn bộ nội dung document bằng object truyền vào $set.
D. Chỉ cập nhật nếu trường được đặt chưa tồn tại trong tài liệu.
Đáp án đúng: B

Câu 12. Khi dùng $inc trên trường số trong updateOne(), tác dụng là gì?
A. Cộng thêm một lượng chỉ định vào giá trị số hiện tại.
B. Đổi kiểu trường số thành chuỗi trước khi ghi dữ liệu.
C. Tăng giá trị số lên một đơn vị dù tham số truyền là bao nhiêu.
D. Gán giá trị số bằng hằng số được truyền trong biểu thức.
Đáp án đúng: A

Câu 13. Khác biệt chính giữa replaceOne() và cập nhật bằng $set là gì?
A. replaceOne chỉ thay các trường có trong object và giữ mọi field.
B. replaceOne thay trường _id mới khi tài liệu cũ đã được tìm thấy.
C. replaceOne thêm một bản ghi khác khi bộ lọc đã khớp tài liệu.
D. replaceOne thay tài liệu khớp bằng document thay thế trừ _id.
Đáp án đúng: D

Câu 14. Tuỳ chọn upsert=true trong updateOne() có ý nghĩa nào?
A. Có thể bỏ qua lỗi unique index khi cập nhật trường trùng.
B. Có thể xóa mọi document cũ khi điều kiện tìm kiếm bị sai.
C. Có thể cập nhật đồng thời mọi document khớp cùng điều kiện.
D. Có thể thêm document mới khi không có document nào khớp.
Đáp án đúng: D

Câu 15. Khi thực thi deleteMany({}) trên collection, điều gì xảy ra?
A. Mọi document trong collection đều phù hợp để bị xoá.
B. Toàn bộ collection và chỉ mục kèm theo đều bị xóa.
C. MongoDB từ chối vì filter không chứa bất kỳ khóa nào.
D. Chỉ document đầu tiên tìm thấy phù hợp để bị xoá.
Đáp án đúng: A

Câu 16. Vì sao thường đưa $match lên sớm trong aggregation nếu kết quả vẫn tương đương?
A. Bắt mọi stage phía sau sử dụng duy nhất index trên trường _id.
B. Giảm số document đi qua những stage phía sau của pipeline.
C. Làm $group luôn chạy trên một luồng riêng và không giữ RAM.
D. Bắt MongoDB tự thay đổi shard key cho các document phù hợp.
Đáp án đúng: B

Câu 17. Trong aggregation, stage $group dùng để làm gì?
A. Gom document theo khóa và tính toán các giá trị tổng hợp.
B. Lựa chọn các field sẽ hiển thị theo từng document đầu vào.
C. Mở từng phần tử mảng thành một document của pipeline.
D. Kết hợp document với dữ liệu của collection nước ngoài.
Đáp án đúng: A

Câu 18. Trong aggregation, tác dụng chính của $unwind là gì?
A. Đặt lại cấu trúc trường đầu ra mà không thay số document.
B. Loại mọi giá trị trùng nhau khỏi mảng trước khi truy vấn.
C. Tách mỗi phần tử mảng thành một document ở pipeline.
D. Gộp nhiều document thành một bản ghi dựa trên khóa nhóm.
Đáp án đúng: C

Câu 19. Stage $lookup thường dùng cho thao tác nào trong aggregation?
A. Sao chép dữ liệu hiện tại sang toàn bộ shard khác trong cụm.
B. Nối dữ liệu với collection khác theo kiểu left outer join.
C. Chạy full-text search trên tất cả các trường của document.
D. Xây dựng index phụ theo trường chỉ định ngay trong pipeline.
Đáp án đúng: B

Câu 20. Stage $project trong aggregation thích hợp cho mục đích nào?
A. Đọc dữ liệu từ secondary mà không cần thiết lập read concern.
B. Nhóm tất cả document rồi đếm từng nhóm theo một khóa.
C. Chọn, loại bỏ hoặc tính toán trường trong kết quả đầu ra.
D. Di chuyển tài liệu giữa các shard theo giá trị khóa shard.
Đáp án đúng: C

Câu 21. Khi bộ lọc trên field có độ chọn lọc tốt, index phù hợp giúp gì?
A. Giảm số document phải đọc để tìm các bản ghi thỏa điều kiện.
B. Giảm kích thước BSON của từng document được lưu trữ.
C. Bỏ qua việc kiểm tra điều kiện lọc sau khi đã chạy truy vấn.
D. Loại bỏ mọi thao tác đọc document khỏi bộ nhớ và ổ đĩa.
Đáp án đúng: A

Câu 22. Với compound index {a:1,b:1}, dạng lọc nào thường tận dụng được tiền tố chỉ mục?
A. Truy vấn chỉ lọc theo b và bỏ qua hoàn toàn trường a.
B. Truy vấn lọc theo c mà không xuất hiện trường a hoặc b.
C. Truy vấn chỉ lọc theo tên collection chứa document.
D. Truy vấn lọc theo a hoặc lọc theo cả a và b cùng lúc.
Đáp án đúng: D

Câu 23. Một index được tạo trên trường chứa mảng thường trở thành loại gì?
A. Geospatial index tự hiểu mọi phần tử mảng là tọa độ.
B. Hashed index chỉ lưu một mã băm cho toàn bộ mảng.
C. Text index tự phân tích từng từ trong các phần tử mảng.
D. Multikey index với các khóa chỉ mục cho phần tử mảng.
Đáp án đúng: D

Câu 24. Điều kiện cơ bản của covered query trong MongoDB là gì?
A. Index đáp ứng được điều kiện lọc và toàn bộ trường cần trả.
B. Mọi trường được truy vấn phải là kiểu dữ liệu số nguyên.
C. Chỉ cần có index _id ngay cả khi chiếu các trường ngoài index.
D. Truy vấn luôn lấy đủ document nhưng kết quả đã vào cache.
Đáp án đúng: A

Câu 25. Trong explain("executionStats"), totalDocsExamined biểu thị gì?
A. Tổng số document được kiểm tra trong quá trình thực thi.
B. Tổng số document hiện đang nằm trong collection được hỏi.
C. Tổng số index entry được sinh ra khi tạo collection mới.
D. Tổng số document đã trả cho client ở trang kết quả cuối.
Đáp án đúng: A

Câu 26. Một TTL index được dùng để xử lý document hết hạn như thế nào?
A. MongoDB tự chuyển document sang collection lưu trữ vĩnh viễn.
B. MongoDB luôn xoá đúng tại thời điểm hết hạn tới mili giây.
C. Tiến trình nền xoá các document đã hết hạn theo lịch kiểm tra.
D. MongoDB chỉ xoá document khi client thực thi truy vấn tìm.
Đáp án đúng: C

Câu 27. Partial index khác index thường ở điểm nào?
A. Chỉ áp dụng cho document nằm ở một shard được chỉ định sẵn.
B. Chỉ lập chỉ mục document khớp điều kiện partialFilterExpression.
C. Chỉ giữ index entry mới nhất khi nhiều document trùng field.
D. Chỉ lập chỉ mục một phần byte đầu tiên của từng field chuỗi.
Đáp án đúng: B

Câu 28. Khi tạo unique index trên một trường, mục tiêu chính là gì?
A. Bắt MongoDB lưu trường được đánh index thành kiểu ObjectId.
B. Ngăn các giá trị khoá chỉ mục trùng theo quy tắc unique.
C. Bảo đảm mọi truy vấn lọc theo field chạy nhanh hơn O(1).
D. Tự động thay document cũ khi chèn tài liệu có field trùng.
Đáp án đúng: B

Câu 29. Tại sao tạo quá nhiều index có thể làm thao tác ghi chậm?
A. Driver luôn phải duyệt mọi index trước khi gửi bản ghi lên DB.
B. Mọi index mới đều khiến server phải ghi thêm một bản sao DB.
C. Các index liên quan phải được cập nhật khi dữ liệu thay đổi.
D. Mọi câu lệnh ghi đều bị chuyển thành transaction nhiều shard.
Đáp án đúng: C

Câu 30. Trong replica set thông thường, node nào nhận các thao tác ghi mặc định?
A. Node arbiter được bầu để tiếp nhận mọi thao tác ghi.
B. Mọi node tự ghi độc lập và đồng bộ bằng cách chia shard.
C. Node secondary có mức độ trễ thấp nhất luôn phục vụ ghi.
D. Node primary hiện tại của replica set phục vụ ghi dữ liệu.
Đáp án đúng: D

Câu 31. Replica set sao chép thay đổi từ primary sang secondary theo cách nào?
A. Secondary áp dụng thay đổi bất đồng bộ nên có thể trễ hơn.
B. Secondary luôn nhận commit đồng bộ trước mọi phản hồi client.
C. Secondary chỉ đồng bộ sau khi primary mất kết nối hoàn toàn.
D. Secondary chuyển từng truy vấn đọc thành thao tác ghi mới.
Đáp án đúng: A

Câu 32. Khi cấu hình readPreference=secondary, cần lưu ý rủi ro nào?
A. Bất kỳ document nào ở secondary đều không có trường _id.
B. Mọi yêu cầu đọc phải đi qua primary trước khi tới secondary.
C. Dữ liệu đọc có thể lạc hậu do replication lag ở secondary.
D. Mọi truy vấn đọc tự trở thành ghi có thể lặp lại khi lỗi mạng.
Đáp án đúng: C

Câu 33. Với writeConcern w:"majority", xác nhận ghi yêu cầu điều gì?
A. Mỗi secondary phải áp dụng dữ liệu trước khi primary ghi.
B. Client phải tự mở transaction riêng cho mọi thao tác insert.
C. Đủ số thành viên có dữ liệu của replica set xác nhận ghi.
D. Tất cả node cùng cụm sharding phải xác nhận dữ liệu đã ghi.
Đáp án đúng: C

Câu 34. Khi chọn shard key, đặc điểm nào giúp giảm nguy cơ hotspot?
A. Khóa tăng tuần tự ở mọi lần insert để mọi ghi tới một shard.
B. Khóa có ít giá trị phân biệt để mỗi nhóm dữ liệu thật lớn.
C. Khóa chỉ được sử dụng khi truy vấn toàn collection không lọc.
D. Khóa phân bố thao tác ghi hợp lý giữa nhiều phân vùng shard.
Đáp án đúng: D

Câu 35. Trong cụm sharded MongoDB, mongos có vai trò chính nào?
A. Tự thay giá trị shard key trên mọi document trước mỗi truy vấn.
B. Lưu một bản sao đầy đủ của toàn bộ document thuộc mọi shard.
C. Định tuyến truy vấn tới shard phù hợp theo thông tin định tuyến.
D. Thực hiện election để chọn primary mới cho mọi replica set.
Đáp án đúng: C

Câu 36. Balancer trong sharded cluster hỗ trợ mục tiêu nào?
A. Dồn mọi ghi mới về primary của một replica set duy nhất.
B. Loại bỏ mọi index phụ để tăng tốc thao tác chia shard.
C. Sao chép liên tục tất cả collection lên mọi máy mongos.
D. Phân phối các range dữ liệu giữa các shard bằng di chuyển.
Đáp án đúng: D

Câu 37. Khi cần cập nhật atomically nhiều document cùng giao dịch, MongoDB hỗ trợ gì?
A. Dùng multi-document transaction trong phiên hỗ trợ giao dịch.
B. Dùng insertMany() mặc định để tất cả insert đều atomic chung.
C. Dùng một câu updateMany() để các document cùng commit nguyên tử.
D. Dùng writeConcern=majority để nhiều thao tác tự thành giao dịch.
Đáp án đúng: A

Câu 38. Cách phân quyền tài khoản ứng dụng MongoDB nào phù hợp nhất?
A. Dùng chung role quản trị cụm cho các ứng dụng không liên quan.
B. Gán role chỉ có những quyền cần cho công việc của ứng dụng.
C. Gán role root cho mọi tài khoản để tránh lỗi cấp quyền.
D. Tắt authentication trên cụm nội bộ để bỏ qua quá trình xác thực.
Đáp án đúng: B

Câu 39. Để bảo vệ dữ liệu trên đường truyền giữa ứng dụng và MongoDB, nên làm gì?
A. Chỉ xác nhận địa chỉ IP máy chủ rồi tắt mọi kiểm tra chứng chỉ.
B. Bật cơ chế nén BSON và xem kết nối đã được mã hóa đường truyền.
C. Bật TLS và kiểm tra danh tính máy chủ qua chứng chỉ hợp lệ.
D. Chỉ mã hóa thông tin kết nối trong file cấu hình ứng dụng.
Đáp án đúng: C

Câu 40. Khi tích hợp Java MongoDB driver, nên quản lý MongoClient như thế nào?
A. Tái sử dụng MongoClient an toàn đa luồng cho vòng đời ứng dụng.
B. Khởi tạo MongoClient mới trong mỗi lần truy vấn để tránh cache.
C. Chia một ClientSession dùng chung cho toàn bộ luồng xử lý.
D. Đóng MongoClient sau từng thao tác insert hoặc find trong service.
Đáp án đúng: A
