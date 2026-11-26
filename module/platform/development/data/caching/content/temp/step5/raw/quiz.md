1. Trong cache-aside, ứng dụng nên xử lý một cache miss thế nào?
A. Yêu cầu cache tự tải dữ liệu nguồn khi thiếu entry
B. Đọc nguồn, lưu kết quả vào cache rồi trả dữ liệu
C. Chờ tác vụ ghi định kỳ đồng bộ lại toàn bộ cache
D. Chỉ xóa khóa cũ và trả về kết quả chưa tìm thấy
Đáp án đúng: B

2. Trong chiến lược write-through, luồng ghi dữ liệu diễn ra thế nào?
A. Ghi cache trước và đẩy xuống nguồn bằng tác vụ nền
B. Chỉ ghi nguồn chính và không đi qua cache lúc ghi
C. Ghi cả cache và nguồn chính trong đường xử lý ghi
D. Ghi nguồn chính rồi vô hiệu hóa mọi cache của ứng dụng
Đáp án đúng: C

3. Rủi ro đặc trưng của write-behind khi cache bị mất đột ngột là gì?
A. Dữ liệu nguồn được cập nhật trước khi cache đổi
B. Mọi lần đọc cache đều thành truy vấn nguồn trực tiếp
C. Các khóa có TTL ngắn bị kéo dài vô thời hạn
D. Mất cập nhật chưa được đẩy xuống nguồn dữ liệu
Đáp án đúng: D

4. Với expire-after-access, sự kiện nào thường làm tính lại thời hạn entry?
A. Một lần ghi mới vào bất kỳ khóa nào của cùng cache
B. Một đợt quét toàn bộ cache để loại khóa ít dùng
C. Một lần thay đổi cấu hình ở nguồn dữ liệu chính
D. Một lần truy cập hợp lệ tới entry đang được lưu
Đáp án đúng: D

5. Đối với cache đa tenant, thiết kế key nào hạn chế trả nhầm dữ liệu?
A. Chỉ dùng ID đối tượng vì mỗi tenant đã có tên riêng
B. Chỉ dùng tên bảng và bỏ mọi định danh của dữ liệu
C. Ghép tenant ID và định danh đối tượng vào key
D. Dùng chung key rồi phân quyền sau khi lấy giá trị
Đáp án đúng: C

6. Khi cache kết quả tìm kiếm có phân trang, yếu tố nào cần nằm trong key?
A. Chỉ thời điểm request đầu tiên được đưa vào cache
B. Chỉ tên endpoint mà không kèm tham số truy vấn
C. Bộ lọc, thứ tự sắp xếp và thông tin phân trang
D. Chỉ phiên bản JVM chạy dịch vụ ở thời điểm đọc
Đáp án đúng: C

7. Vì sao chỉ dùng TTL vẫn có thể trả dữ liệu cũ?
A. Cache luôn bỏ qua cập nhật mới trước khi có miss
B. Nguồn thay đổi khi entry cache vẫn còn hiệu lực
C. TTL chỉ có tác dụng sau khi ứng dụng khởi động lại
D. Đọc cache bắt buộc phải cập nhật lại nguồn dữ liệu
Đáp án đúng: B

8. Khi nhiều node giữ cache riêng, cách nào hỗ trợ invalidation đúng lúc?
A. Phát sự kiện thay đổi để các node xóa key liên quan
B. Chỉ xóa khóa ở node nhận yêu cầu cập nhật dữ liệu
C. Đặt TTL vô hạn để mỗi node tự giữ trạng thái ổn định
D. Tăng dung lượng cache của node ghi để giảm eviction
Đáp án đúng: A

9. Eviction theo LRU ưu tiên loại bỏ entry nào khi cần chỗ?
A. Entry có tần suất truy cập thấp nhất từ lúc tạo
B. Entry được chèn đầu tiên bất kể lịch sử truy cập
C. Entry có thời điểm hết TTL gần nhất trong tương lai
D. Entry có lần truy cập gần nhất cách đây lâu nhất
Đáp án đúng: D

10. Trong Caffeine, `maximumSize` nhằm kiểm soát điều gì?
A. Số lượng entry tối đa ước lượng được cache giữ lại
B. Tổng số byte tối đa của mọi đối tượng đang được lưu
C. Số luồng tối đa có thể nạp một key trong cache
D. Số giây tối đa trước khi mọi entry cần được tải lại
Đáp án đúng: A

11. Với Caffeine `expireAfterWrite`, mốc hết hạn tính từ đâu?
A. Lần đọc thành công entry gần nhất từ ứng dụng
B. Lần ghi hoặc cập nhật entry gần nhất vào cache
C. Lần cache gửi yêu cầu refresh bất đồng bộ gần nhất
D. Lần cuối JVM chạy dọn dẹp các entry không dùng
Đáp án đúng: B

12. Caffeine `refreshAfterWrite` trong loading cache có ý nghĩa gì?
A. Entry luôn bị xóa ngay khi đạt tuổi ghi quy định
B. Entry đủ điều kiện làm mới khi được đọc sau ngưỡng
C. Mọi entry đều tự được nạp lại dù không ai truy cập
D. Toàn bộ cache tự reset mỗi khi một key được cập nhật
Đáp án đúng: B

13. Biện pháp single-flight chống cache stampede hoạt động ra sao?
A. Tạo thêm lượt đọc nguồn song song khi key vừa hết TTL
B. Tăng số worker đọc nguồn cho mọi key đang được yêu cầu
C. Gộp các lượt nạp đồng thời của cùng key thành một
D. Bỏ toàn bộ TTL để cache không bao giờ phải nạp lại
Đáp án đúng: C

14. Vì sao thêm jitter vào TTL có thể giảm cache stampede?
A. Mỗi lần đọc tự động gia hạn TTL của tất cả các key
B. Các key hết hạn ở những thời điểm được phân tán hơn
C. Một key hết hạn sẽ khóa toàn bộ cache cho đến khi nạp
D. Mỗi cache miss được biến thành một thao tác ghi nền
Đáp án đúng: B

15. Negative caching thường phù hợp với tình huống nào?
A. Lưu vô hạn mọi lỗi timeout từ cơ sở dữ liệu nguồn
B. Chỉ lưu dữ liệu tồn tại, bỏ qua mọi request thất bại
C. Lưu ngắn kết quả không tìm thấy để bớt truy vấn lặp
D. Lưu nguyên lỗi xác thực của người dùng cho mọi tenant
Đáp án đúng: C

16. Với một hot key có lượng đọc rất lớn, cách xử lý nào hợp lý?
A. Phân tải lượt đọc qua bản sao và cache gần ứng dụng
B. Bỏ cache cho key để mọi request đọc trực tiếp nguồn
C. Tăng đồng thời số lần nạp cùng key từ nguồn dữ liệu
D. Vô hiệu hóa key ngay sau mọi lần cache trả về hit
Đáp án đúng: A

17. Trong lệnh Redis `SET`, tùy chọn `EX` hoặc `PX` có tác dụng gì?
A. Chỉ tạo key khi key đó chưa tồn tại trong Redis
B. Chỉ cập nhật giá trị nếu key đã tồn tại trong Redis
C. Gắn thời hạn hết hiệu lực cho key lúc thực hiện ghi
D. Yêu cầu trả về giá trị cũ của key khi ghi giá trị mới
Đáp án đúng: C

18. Cơ chế `maxmemory-policy` của Redis điều khiển việc gì?
A. Đặt TTL mặc định mới cho mọi key khi vừa ghi vào
B. Tạo một namespace riêng theo tenant ID của ứng dụng
C. Quy định số kết nối TCP tối đa được phép mở đến Redis
D. Chọn chiến lược loại khóa khi chạm giới hạn bộ nhớ
Đáp án đúng: D

19. Lệnh Redis `SET key value NX PX ...` có ý nghĩa gì?
A. Chỉ tạo key khi chưa có và kèm thời hạn tính bằng ms
B. Luôn ghi đè giá trị key và giữ nguyên mọi TTL đang có
C. Chỉ cập nhật key đã tồn tại và bỏ toàn bộ thời hạn cũ
D. Tăng giá trị số của key rồi tự thiết lập thời hạn mới
Đáp án đúng: A

20. Điểm khác nhau đáng chú ý giữa cache Redis và Caffeine local là gì?
A. Caffeine tự chia sẻ entry qua mạng giữa các JVM khác
B. Redis cho nhiều instance truy cập trạng thái cache chung
C. Redis chỉ lưu được đối tượng trên heap của một JVM
D. Caffeine đảm bảo các instance luôn thấy cùng một phiên bản
Đáp án đúng: B

21. Trong Spring Cache, `@Cacheable` thường làm gì khi có cache hit?
A. Trả kết quả cache mà không thực thi phần thân method
B. Luôn chạy method rồi chỉ ghi kết quả vào cache sau
C. Xóa toàn bộ cache trước mỗi lần gọi method được gắn
D. Chỉ sinh key cache mà không lưu bất kỳ kết quả nào
Đáp án đúng: A

22. Trong Spring Cache, `@CacheEvict` phù hợp với tác vụ nào?
A. Loại key liên quan sau khi dữ liệu nguồn được thay đổi
B. Ghi kết quả method vào cache ở mọi lần gọi thành công
C. Lấy kết quả cache để bỏ qua thực thi method hiện tại
D. Gia hạn tự động TTL cho toàn bộ key của một cache
Đáp án đúng: A

23. Vì sao lời gọi `this.cachedMethod()` có thể bỏ qua `@Cacheable`?
A. Annotation cache chỉ hoạt động khi method là `static`
B. Spring Cache luôn bỏ qua mọi method trả về đối tượng
C. Caffeine bắt buộc phải được khởi tạo qua Redis client
D. Self-invocation không đi qua proxy quản lý cache advice
Đáp án đúng: D

24. Khi đánh giá cache có thực sự hiệu quả, nên theo dõi nhóm chỉ số nào?
A. Chỉ hit ratio vì đó là mục tiêu duy nhất của mọi cache
B. Chỉ kích thước cache vì càng lớn thì càng chính xác
C. Chỉ số lượng key trong Redis mà bỏ qua tải nguồn
D. Hit ratio, p95 độ trễ và lưu lượng về nguồn dữ liệu
Đáp án đúng: D
