Câu 01. Redis String có đặc điểm nào khi lưu giá trị?
A. Lưu chuỗi byte và có thể dùng cho bộ đếm số nguyên.
B. Chỉ lưu văn bản UTF-8 và từ chối dữ liệu nhị phân.
C. Luôn giải mã giá trị thành JSON trước khi ghi key.
D. Tự lập chỉ mục nội dung string để tìm theo từ khóa.
Đáp án đúng: A

Câu 02. Khi gọi INCR trên một key chứa số nguyên hợp lệ, Redis làm gì?
A. Tự chuyển giá trị không phải số nguyên thành số hợp lệ.
B. Tăng giá trị số nguyên một cách nguyên tử theo từng lệnh.
C. Chỉ tăng giá trị khi key đã có một TTL đang còn hiệu lực.
D. Tăng đồng thời mọi key có chung một tiền tố trong tên.
Đáp án đúng: B

Câu 03. SET key value NX EX 60 có ý nghĩa nào?
A. Chỉ ghi key đã có TTL và trả lại giá trị vừa được ghi.
B. Chỉ tạo key mới nhưng bỏ qua thời hạn được chỉ định.
C. Chỉ tạo key nếu chưa tồn tại và đặt TTL là 60 giây.
D. Chỉ ghi key khi đã tồn tại và giữ nguyên TTL trước đó.
Đáp án đúng: C

Câu 04. Khi muốn lưu thuộc tính của đối tượng trong Redis Hash, dùng lệnh nào?
A. SADD để thêm một member vào set tại key tương ứng.
B. HSET để ghi một field cùng giá trị trong hash của key.
C. ZADD để thêm member và score vào sorted set tại key.
D. LPUSH để đẩy phần tử vào list tại key tương ứng.
Đáp án đúng: B

Câu 05. Vì sao cần cân nhắc khi gọi HGETALL trên hash rất lớn?
A. Lệnh tự giới hạn số field theo tham số COUNT mặc định.
B. Lệnh chỉ trả field mới chỉnh sửa trong một giao dịch.
C. Lệnh có độ phức tạp hằng số dù số field rất lớn.
D. Lệnh trả mọi cặp field-value nên phản hồi có thể lớn.
Đáp án đúng: D

Câu 06. Tính chất nào đúng với kiểu Set của Redis?
A. Các member luôn có thứ tự truy cập theo lúc thêm vào.
B. Member trùng nhau không được lưu thành nhiều phần tử.
C. Mỗi member bắt buộc có số thứ tự nguyên để tìm kiếm.
D. Member trùng nhau được lưu nếu có các score khác nhau.
Đáp án đúng: B

Câu 07. Điểm cần lưu ý khi dùng SMEMBERS với set lớn là gì?
A. Lệnh trả toàn bộ member nên có thể tạo phản hồi lớn.
B. Lệnh tự phân trang theo cursor được truyền từ client.
C. Lệnh chỉ lấy những member được thêm gần đây nhất.
D. Lệnh luôn giới hạn kết quả theo thông số COUNT chung.
Đáp án đúng: A

Câu 08. Trong Sorted Set, ZADD score member hỗ trợ gì?
A. Gán vị trí cố định cho member mà không dùng score.
B. Gán điểm cho member để truy vấn theo thứ tự score.
C. Gán thời gian sống cho member để lọc theo TTL riêng.
D. Đẩy member vào đầu list theo thứ tự ghi mới nhất.
Đáp án đúng: B

Câu 09. Muốn lấy các thành viên có score cao trước, có thể dùng cách nào?
A. Dùng SMEMBERS vì Set tự giữ member theo score giảm dần.
B. Dùng ZRANGE với tùy chọn REV để duyệt điểm giảm dần.
C. Dùng HGETALL vì Hash tự sắp xếp field theo score.
D. Dùng ZRANGE mặc định để duyệt score từ cao xuống thấp.
Đáp án đúng: B

Câu 10. Khi thêm một bản ghi vào Redis Stream, XADD hoạt động ra sao?
A. Thêm entry với một ID mới theo quy tắc thứ tự stream.
B. Sửa entry cũ nếu tên field trùng với entry trước đó.
C. Chỉ đọc entry mới chưa được consumer group xác nhận.
D. Tự xóa entry ngay sau khi một consumer đã đọc xong.
Đáp án đúng: A

Câu 11. XREADGROUP phục vụ cơ chế nào khi xử lý Redis Stream?
A. Nhóm consumer chỉ xử lý các entry có cùng một field.
B. Mỗi consumer của nhóm nhận mọi entry như Pub/Sub.
C. Các consumer cùng nhóm phối hợp nhận entry để xử lý.
D. Các entry bị xóa ngay khi consumer đầu tiên đọc được.
Đáp án đúng: C

Câu 12. Trong Redis Streams, XACK có tác dụng chính nào?
A. Tự gán entry chưa xử lý cho một consumer khác trong nhóm.
B. Xác nhận entry đã xử lý trong consumer group tương ứng.
C. Phát lại entry đã đọc cho toàn bộ subscriber đang kết nối.
D. Xóa nội dung entry khỏi stream cho mọi consumer group.
Đáp án đúng: B

Câu 13. Khác biệt quan trọng giữa Redis Stream và Pub/Sub là gì?
A. Pub/Sub lưu message để client ngắt mạng vẫn đọc lại.
B. Stream lưu entry để có thể đọc lại theo ID phù hợp.
C. Stream chỉ gửi entry khi mọi consumer đang trực tuyến.
D. Pub/Sub tự lưu trạng thái đã đọc cho từng consumer group.
Đáp án đúng: B

Câu 14. Khi TTL key trả về -1, Redis đang báo điều gì?
A. Key đang được khóa nên không xem được thời gian hết hạn.
B. Key không còn tồn tại tại thời điểm kiểm tra TTL.
C. Key tồn tại nhưng hiện không được đặt thời gian hết hạn.
D. Key còn đúng một giây trước khi hết hạn trong Redis.
Đáp án đúng: C

Câu 15. Sau SET ghi đè một key đang có TTL, điều gì xảy ra theo mặc định?
A. TTL cũ được tăng theo thời gian kể từ lần SET trước.
B. TTL cũ được chuyển sang key được tạo tiếp theo trên Redis.
C. TTL cũ bị bỏ trừ khi lệnh yêu cầu giữ TTL hiện tại.
D. TTL cũ luôn được giữ nguyên qua mọi lần gọi lệnh SET.
Đáp án đúng: C

Câu 16. Lệnh EXPIRE session:42 60 dùng để làm gì?
A. Xóa mọi key có tiền tố session:42 sau đúng 60 giây.
B. Đặt thời gian hết hạn của key session:42 là 60 giây.
C. Đặt thời gian hết hạn của key session:42 là 60 phút.
D. Chỉ xóa key session:42 nếu key đã tồn tại 60 giây.
Đáp án đúng: B

Câu 17. Cách đặt tên key nào thuận tiện để tra cứu profile người dùng số 42?
A. Dùng user:42:profile để phân tách loại dữ liệu và ID.
B. Dùng user:*:profile làm một key chung cho mọi tài khoản.
C. Dùng profile để nhiều tài khoản cùng chia sẻ một key.
D. Dùng 42 vì ID đủ để phân biệt mọi kiểu dữ liệu.
Đáp án đúng: A

Câu 18. Khi cần duyệt nhiều key trong Redis đang phục vụ traffic, nên làm gì?
A. Dùng SCAN theo cursor để chia nhỏ công việc duyệt key.
B. Dùng GET với ký tự đại diện để lấy key theo tiền tố.
C. Dùng EXISTS với ký tự đại diện để trả danh sách key.
D. Dùng KEYS trong mọi request vì tự phân trang ổn định.
Đáp án đúng: A

Câu 19. Khi keyspace thay đổi trong lúc đang quét SCAN, điều gì có thể xảy ra?
A. Kết quả luôn là snapshot cố định từ đầu vòng quét.
B. Mỗi key được trả chính xác một lần trên mọi vòng quét.
C. Các key luôn được sắp xếp theo thứ tự chữ cái.
D. Một key có thể được trả nhiều lần trong vòng quét.
Đáp án đúng: D

Câu 20. Trong mô hình cache-aside, khi đọc Redis bị cache miss thì xử lý thế nào?
A. Tái sử dụng giá trị cũ dù lệnh GET đã trả cache miss.
B. Chỉ tăng TTL của key không tồn tại rồi gọi lại GET.
C. Đọc nguồn dữ liệu gốc rồi nạp kết quả vào cache.
D. Luôn trả giá trị mặc định mà không kiểm tra dữ liệu gốc.
Đáp án đúng: C

Câu 21. Khi cập nhật database gốc, cách nào hạn chế cache bị lỗi thời?
A. Tăng TTL của cache để tránh ghi lại dữ liệu từ DB.
B. Chỉ cập nhật cache rồi để DB giữ nguyên dữ liệu cũ.
C. Giữ cache tới hết TTL để bảo đảm dữ liệu luôn mới nhất.
D. Xóa hoặc cập nhật entry cache liên quan sau khi ghi DB.
Đáp án đúng: D

Câu 22. Biện pháp nào giảm cache stampede khi nhiều request cùng miss một key?
A. Tạo một key ngẫu nhiên mới cho mỗi request bị miss.
B. Gộp lần tái nạp hoặc dùng khóa ngắn hạn cho key.
C. Tăng số truy vấn tới DB bằng cách chạy song song thêm.
D. Đặt TTL của mọi key bằng nhau để tái nạp đồng loạt.
Đáp án đúng: B

Câu 23. Tại sao nên thêm jitter khi thiết lập TTL cho nhiều cache entry?
A. Giúp phân tán thời điểm nhiều entry hết hạn đồng loạt.
B. Giúp tránh phải truy cập database ở mọi lần cache miss.
C. Giúp mọi entry hết hạn cùng lúc để làm nóng cache.
D. Giúp key không bị loại khỏi bộ nhớ khi Redis đầy.
Đáp án đúng: A

Câu 24. Khi Redis cấu hình allkeys-lru, nhóm key nào có thể bị loại?
A. Chỉ key không có TTL, ưu tiên key có score thấp nhất.
B. Chỉ key kiểu String, ưu tiên key có dung lượng nhỏ nhất.
C. Mọi key, ưu tiên gần đúng những key ít dùng gần đây.
D. Chỉ key có TTL, ưu tiên key có hạn hết trước nhất.
Đáp án đúng: C

Câu 25. Chính sách volatile-ttl áp dụng loại bỏ key theo tiêu chí nào?
A. Chỉ xét key không có TTL và ưu tiên key vừa tạo.
B. Xét mọi key và ưu tiên key ít được truy cập gần đây.
C. Xét mọi key và ưu tiên key có bộ nhớ sử dụng lớn nhất.
D. Chỉ xét key có TTL và ưu tiên key sớm hết hạn.
Đáp án đúng: D

Câu 26. RDB persistence trong Redis được hiểu đúng như thế nào?
A. Đẩy từng key hết hạn vào tệp lưu trữ riêng trên đĩa.
B. Ghi nối tiếp các lệnh thay đổi vào log để phát lại.
C. Chụp snapshot dữ liệu tại các thời điểm lưu nhất định.
D. Sao chép đồng bộ từng thao tác ghi tới tất cả replica.
Đáp án đúng: C

Câu 27. AOF persistence của Redis lưu thông tin theo cách nào?
A. Chỉ lưu thống kê lệnh đọc để phục hồi bộ đếm cache hit.
B. Chỉ lưu tệp cấu hình sau mỗi lần tài khoản đổi quyền.
C. Chụp snapshot tất cả key ở những mốc thời gian cố định.
D. Ghi nhật ký các thao tác thay đổi để phục hồi dữ liệu.
Đáp án đúng: D

Câu 28. Với appendfsync everysec, rủi ro nào cần tính đến?
A. Không thể mất bất kỳ lệnh ghi nào đã phản hồi thành công.
B. Mọi ghi đều chờ đồng bộ xuống đĩa trước khi trả kết quả.
C. Chỉ có thể phục hồi dữ liệu từ tệp RDB sau khi sự cố.
D. Có thể mất dữ liệu gần lần fsync cuối khi xảy ra sự cố.
Đáp án đúng: D

Câu 29. Đặc điểm nào đúng với replication Redis thông thường?
A. Replica có thể chậm hơn primary do đồng bộ bất đồng bộ.
B. Replica tự chia key theo hash slot để xử lý ghi phân tán.
C. Replica luôn xác nhận mỗi ghi trước phản hồi của primary.
D. Replica chỉ cập nhật khi Sentinel đã chọn primary mới.
Đáp án đúng: A

Câu 30. Redis Sentinel chủ yếu hỗ trợ khả năng nào?
A. Ghi snapshot dữ liệu thay cho mọi chính sách persistence.
B. Định tuyến từng truy vấn tới slot trong Redis Cluster.
C. Giám sát primary và điều phối failover khi cần thiết.
D. Chia các key thành hash slot để phân phối giữa shard.
Đáp án đúng: C

Câu 31. Redis Cluster sử dụng bao nhiêu hash slot để phân phối key?
A. Không gian key được chia thành 16.384 hash slot.
B. Không gian key được chia theo số CPU trên từng node.
C. Mỗi primary giữ toàn bộ key của tất cả slot trên cụm.
D. Mỗi kiểu dữ liệu được dành riêng một tập hash slot.
Đáp án đúng: A

Câu 32. Trong Redis Cluster, hai key dùng cùng hash tag {user42} sẽ có tính chất gì?
A. Phần trong ngoặc nhọn được hash nên key cùng slot.
B. Các key cùng kiểu String luôn ở chung một node.
C. Các key chung tiền tố luôn cùng slot dù tag khác.
D. Các key có cùng TTL tự được ánh xạ vào một slot.
Đáp án đúng: A

Câu 33. Lỗi CROSSSLOT thường xuất hiện với lệnh nhiều key khi nào?
A. Một trong các key có TTL thấp hơn một giây trên Redis.
B. Các key được yêu cầu không nằm cùng một hash slot.
C. Một key chưa được khai báo trước khi thực thi lệnh GET.
D. Các key được yêu cầu trùng một hash slot trên cluster.
Đáp án đúng: B

Câu 34. Pipelining trong Redis giúp giảm chi phí nào của nhiều lệnh?
A. Tự rollback toàn bộ các lệnh nếu một lệnh gặp lỗi.
B. Chạy tất cả các lệnh song song trên nhiều lõi của Redis.
C. Khóa toàn bộ key trong pipeline tới khi nhận phản hồi.
D. Giảm số lượt trao đổi mạng bằng cách gửi gộp các lệnh.
Đáp án đúng: D

Câu 35. Khi thực hiện MULTI rồi EXEC, Redis xử lý các lệnh xếp hàng ra sao?
A. Các lệnh được tự phát lại sau khi Redis khởi động lại.
B. Mỗi lệnh được thực thi ngay lúc client đang gọi MULTI.
C. Nếu một lệnh lỗi runtime thì mọi lệnh trước đều rollback.
D. Các lệnh được thực thi liên tiếp khi client gọi EXEC.
Đáp án đúng: D

Câu 36. Cơ chế WATCH trong Redis transaction nhằm mục đích gì?
A. Tự tạo snapshot key để rollback nếu một lệnh gặp lỗi.
B. Buộc các thao tác GET trả kết quả từ secondary Redis.
C. Huỷ EXEC nếu key đang theo dõi đã thay đổi trước đó.
D. Khóa độc quyền các key cho đến khi giao dịch gọi EXEC.
Đáp án đúng: C

Câu 37. Khi Lua script thực thi tại Redis, điều nào đúng?
A. Script tự hoàn tác các thao tác ghi nếu một bước lỗi.
B. Script thực thi từng dòng đồng thời trên nhiều worker.
C. Script được tự chuyển qua node khác khi hết bộ nhớ.
D. Script chạy nguyên tử so với các lệnh Redis khác.
Đáp án đúng: D

Câu 38. Khi cấp ACL cho một ứng dụng Redis, nguyên tắc nào phù hợp?
A. Chỉ giới hạn cổng kết nối mà không cấu hình xác thực.
B. Cấp toàn bộ quyền lệnh để tránh lỗi ứng dụng khi chạy.
C. Giới hạn lệnh và mẫu key theo nhu cầu truy cập thực.
D. Dùng chung user quản trị cho mọi dịch vụ trong hệ thống.
Đáp án đúng: C

Câu 39. SLOWLOG của Redis ghi lại loại thông tin nào?
A. Mọi lệnh trả về dữ liệu lớn hơn ngưỡng maxmemory.
B. Các lần client reconnect mà không thực thi lệnh Redis.
C. Toàn bộ thời gian truyền dữ liệu từ Redis tới client.
D. Các lệnh có thời gian thực thi vượt ngưỡng được đặt.
Đáp án đúng: D

Câu 40. Trong ứng dụng Java, cách quản lý Redis client nào phù hợp?
A. Tái sử dụng client và cấu hình timeout theo tải thực tế.
B. Tạo client mới cho từng GET để tránh cache kết nối cũ.
C. Dùng một kết nối blocking chung cho tất cả tác vụ nền.
D. Để timeout vô hạn khi Redis không phản hồi qua mạng.
Đáp án đúng: A
