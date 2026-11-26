Câu 1. Hệ thống chỉ lấy và ghi session theo session_id nên ưu tiên mô hình nào?
A. Kho khóa–giá trị với phép truy xuất theo khóa
B. Kho tài liệu với phép lọc theo nội dung JSON
C. Kho đồ thị với phép duyệt quan hệ nhiều bước
D. Kho cột rộng với phép quét theo khoảng cột
Đáp án đúng: A

Câu 2. Trong kho khóa–giá trị thuần không có chỉ mục phụ, thao tác nào thường tốn kém nhất?
A. Xóa một session theo khóa định danh
B. Tìm các session theo thuộc tính thiết bị
C. Đọc một session theo khóa định danh
D. Cập nhật một session theo khóa định danh
Đáp án đúng: B

Câu 3. Đặc điểm dữ liệu nào phù hợp với mô hình cơ sở dữ liệu tài liệu?
A. Document có các trường và object lồng nhau
B. Hàng được nhóm theo khóa phân vùng
C. Giá trị được truy xuất qua một khóa
D. Đỉnh và cạnh nối thành nhiều quan hệ
Đáp án đúng: A

Câu 4. Lợi ích thường gặp của schema linh hoạt trong kho document là gì?
A. Chấp nhận document có những trường tùy chọn
B. Bảo đảm mọi document cùng một cấu trúc
C. Bảo đảm mọi truy vấn đều không cần index
D. Thực thi join liên collection như SQL
Đáp án đúng: A

Câu 5. Trong mô hình cột rộng, partition key chủ yếu quyết định điều gì?
A. Những bản ghi nào dùng cùng khóa mã hóa
B. Những hàng nào được đặt cùng một phân vùng
C. Những thuộc tính nào tạo thành secondary index
D. Những phép tổng hợp nào được lưu sẵn
Đáp án đúng: B

Câu 6. Trong kho cột rộng kiểu Cassandra, clustering key thường làm gì?
A. Đánh chỉ mục toàn văn cho từng cột
B. Sắp xếp các partition giữa nhiều node
C. Sắp xếp các hàng bên trong một partition
D. Phân phối replica của toàn bộ cluster
Đáp án đúng: C

Câu 7. Bài toán nào phù hợp nổi bật với cơ sở dữ liệu đồ thị?
A. Đếm event theo một khoảng ngày đã chỉ định
B. Ghi log nối tiếp theo timestamp của sự kiện
C. Đọc một session từ khóa định danh đã biết
D. Tìm đường đi nhiều bước giữa các tài khoản
Đáp án đúng: D

Câu 8. Trong mô hình đồ thị, một cạnh thường biểu diễn điều gì?
A. Phân vùng logic của các hàng thuộc một bảng
B. Quan hệ có hướng hoặc không hướng giữa đỉnh
C. Phiên bản dữ liệu được sao chép sang replica
D. Giá trị khóa dùng để tra cứu một document
Đáp án đúng: B

Câu 9. Khi chỉ cần cache theo mã sản phẩm, lý do nào khiến kho đồ thị ít cần thiết?
A. Không thể lưu bất kỳ thuộc tính sản phẩm nào
B. Không phải duyệt quan hệ để trả về giá trị
C. Không hỗ trợ mở rộng thành nhiều node máy
D. Không thể truy xuất dữ liệu theo định danh
Đáp án đúng: B

Câu 10. Khi nào nên nhúng danh sách địa chỉ nhỏ vào document người dùng?
A. Khi địa chỉ yêu cầu phân vùng trên hàng triệu node
B. Khi địa chỉ rất lớn và cập nhật hoàn toàn độc lập
C. Khi địa chỉ phải truy vấn qua nhiều mức đồ thị
D. Khi địa chỉ ít và thường được đọc cùng người dùng
Đáp án đúng: D

Câu 11. Khi tập đơn hàng của khách tăng không giới hạn, thiết kế nào thường an toàn hơn?
A. Lưu đơn hàng riêng và tham chiếu khách hàng
B. Đặt toàn bộ đơn hàng trong một giá trị cache
C. Gộp mọi đơn hàng vào một phân vùng cố định
D. Nhúng mọi đơn hàng vào một document khách
Đáp án đúng: A

Câu 12. Đánh đổi chính của denormalization để phục vụ nhiều dạng truy vấn là gì?
A. Đọc chậm hơn nhưng loại bỏ mọi bản sao dữ liệu
B. Ghi luôn có giao dịch mạnh trên mọi phân vùng
C. Ghi đơn giản hơn vì không còn dữ liệu trùng lặp
D. Đọc nhanh hơn nhưng phải đồng bộ nhiều bản sao
Đáp án đúng: D

Câu 13. Yếu tố nào quan trọng khi chọn partition key cho tải lớn?
A. Tăng số index phụ của mỗi bản ghi dữ liệu
B. Giữ mọi request của hệ thống trên một node
C. Phân bố đều dữ liệu và lưu lượng truy cập
D. Buộc mọi truy vấn dùng cùng một phép join
Đáp án đúng: C

Câu 14. Một partition nhận phần lớn request trong cluster được gọi là vấn đề gì?
A. Compaction giảm số tệp dữ liệu trên đĩa
B. Hot partition gây lệch tải giữa các node
C. Split brain làm mất quyền quản trị cluster
D. Read repair tạo bản ghi mới trên mọi replica
Đáp án đúng: B

Câu 15. Phân vùng bằng hash thường mang lợi ích nào so với phân vùng theo khoảng?
A. Bảo toàn thứ tự toàn cục của mọi khóa lưu trữ
B. Loại bỏ nhu cầu dùng secondary index cho lọc
C. Duyệt toàn bộ khoảng khóa theo thứ tự nhanh hơn
D. Phân phối khóa đều hơn khi khóa tăng dần
Đáp án đúng: D

Câu 16. Phân vùng theo range đặc biệt hữu ích với dạng truy vấn nào?
A. Quét các khóa liên tiếp trong một khoảng
B. Tra cứu ngẫu nhiên những khóa có hash giống nhau
C. Đọc mọi node trong một lần duyệt quan hệ đồ thị
D. Nhóm mọi document theo cùng độ dài của giá trị
Đáp án đúng: A

Câu 17. Consistent hashing thường được dùng khi thêm node để đạt mục tiêu nào?
A. Giảm số lần cần kiểm tra điều kiện truy vấn
B. Giảm số khóa cần chuyển khi đổi số node
C. Tăng độ chính xác của secondary index
D. Tăng số lần sao chép từng bản ghi đã ghi
Đáp án đúng: B

Câu 18. Replication khác sharding ở điểm chính nào?
A. Gộp các document khác nhau vào một document
B. Chia tập khóa thành các phần không chồng lấn
C. Tạo chỉ mục phụ cho điều kiện lọc không khóa
D. Tạo bản sao dữ liệu để tăng khả năng sẵn sàng
Đáp án đúng: D

Câu 19. Với replication bất đồng bộ, điều gì có thể xảy ra ngay sau khi primary ghi thành công?
A. Truy vấn trên primary buộc phải đọc dữ liệu cũ
B. Tất cả bản sao đồng thời đổi partition key
C. Mọi replica đã nhận bản ghi ngay lập tức
D. Replica chưa nhận bản ghi nên đọc có thể cũ
Đáp án đúng: D

Câu 20. Bảo đảm read-your-writes nghĩa là gì với một phiên người dùng?
A. Đọc sau khi ghi của phiên đó thấy thay đổi mới
B. Đọc bất kỳ replica nào đều thấy cùng timestamp
C. Ghi của mọi người dùng đều được thực hiện nối tiếp
D. Đọc giữa các phân vùng luôn tạo một snapshot
Đáp án đúng: A

Câu 21. Một lịch sử thao tác được gọi là linearizable khi nào?
A. Mọi thao tác đều được phát lại từ log trước khi trả kết quả
B. Các thao tác có điểm hiệu lực giữa lúc gọi và trả lời
C. Mỗi replica tự chọn trật tự ghi độc lập với các node khác
D. Các bản ghi được sắp xếp theo khóa chính trong bộ nhớ
Đáp án đúng: B

Câu 22. Theo CAP, khi xuất hiện network partition, hệ phân tán phải cân nhắc điều gì?
A. Dùng nén dữ liệu hay chuyển sang bộ nhớ trong cluster
B. Tối ưu chỉ mục phụ hay giảm dung lượng lưu trên đĩa
C. Chọn kiểu dữ liệu document hay kiểu dữ liệu cột rộng
D. Phản hồi yêu cầu hay duy trì nhất quán mạnh
Đáp án đúng: D

Câu 23. Tại sao cách nói 'NoSQL chỉ được chọn hai trong ba CAP' dễ gây hiểu nhầm?
A. Availability chỉ liên quan đến tốc độ tạo secondary index
B. Partition tolerance là một tính năng có thể bỏ qua hoàn toàn
C. Đánh đổi C và A rõ nhất khi mạng bị phân vùng
D. Consistency luôn bị loại bỏ ngay khi số replica tăng lên
Đáp án đúng: C

Câu 24. Khi dùng read quorum R và write quorum W với N replica, điều kiện R + W > N bảo đảm trực tiếp gì?
A. Tập replica đọc và ghi có ít nhất một nút chung
B. Từng replica đều nhận mọi bản ghi trước khi phản hồi
C. Toàn bộ các yêu cầu ghi được xử lý theo một thứ tự
D. Mọi phép đọc luôn tuyến tính hóa qua tất cả các node
Đáp án đúng: A

Câu 25. Trong hệ eventual consistency, điều nào được kỳ vọng khi ngừng ghi và mạng hoạt động?
A. Các replica cuối cùng hội tụ về cùng trạng thái
B. Mọi replica lập tức trả kết quả giống nhau
C. Mọi phép đọc đều có snapshot toàn cục
D. Các xung đột đồng thời không cần xử lý
Đáp án đúng: A

Câu 26. Rủi ro của cơ chế last-write-wins khi hai node ghi đồng thời là gì?
A. Mọi replica bắt buộc giữ cả hai bản cập nhật
B. Tất cả giá trị có thể bị hợp nhất tự động
C. Một thay đổi hợp lệ có thể bị ghi đè mất
D. Document được tự động chuyển sang phân vùng mới
Đáp án đúng: C

Câu 27. Vector clock được dùng trong một số hệ phân tán nhằm nhận biết điều gì?
A. Partition nào đang chiếm nhiều không gian đĩa
B. Chỉ mục nào cần được tối ưu hóa bằng compaction
C. Hai phiên bản là quan hệ nhân quả hay đồng thời
D. Khóa nào nên được đặt vào node có nhiều bộ nhớ
Đáp án đúng: C

Câu 28. Khi các replica tạo hai giá trị xung đột, chiến lược nào giữ được ý nghĩa nghiệp vụ?
A. Giải quyết xung đột bằng quy tắc của ứng dụng
B. Luôn chọn giá trị có kích thước chuỗi lớn nhất
C. Luôn gộp bytes của hai bản ghi thành một giá trị
D. Luôn xóa cả hai giá trị trước khi đọc lại dữ liệu
Đáp án đúng: A

Câu 29. TTL thường được áp dụng cho dữ liệu dạng nào trong NoSQL?
A. Khóa phân vùng phải tồn tại vĩnh viễn trên đĩa
B. Giao dịch cần khóa toàn bộ cluster trong nhiều giờ
C. Phiên hoặc cache cần tự hết hạn sau một thời gian
D. Index phụ cần ghi đè mọi document sau mỗi lần đọc
Đáp án đúng: C

Câu 30. Tombstone trong một số hệ NoSQL dựa trên LSM chủ yếu dùng để làm gì?
A. Đánh dấu partition vừa đạt ngưỡng giới hạn CPU
B. Đánh dấu xóa để hợp nhất và lan truyền trạng thái
C. Đánh dấu khóa duy nhất không được phép thay đổi
D. Đánh dấu document cần được tạo quan hệ đồ thị
Đáp án đúng: B

Câu 31. Khi thêm secondary index, đánh đổi nào thường cần đánh giá?
A. Giảm dữ liệu trùng nhưng bắt buộc bỏ partition key
B. Giảm số replica đồng thời tăng nhất quán của cluster
C. Giảm chi phí lọc mà không ảnh hưởng thao tác ghi
D. Lọc nhanh hơn nhưng tốn dung lượng và chi phí ghi
Đáp án đúng: D

Câu 32. Trong kho dùng LSM-tree, compaction thường thực hiện công việc gì?
A. Chuyển mọi thao tác ghi thành giao dịch trên toàn cụm
B. Phân tích trường văn bản thành token để tìm kiếm
C. Hợp nhất các tệp đã sắp xếp và xử lý bản ghi cũ
D. Tự cấp phát node mới cho các shard có nhiều request
Đáp án đúng: C

Câu 33. Vì sao compaction có thể làm tăng latency trong giờ cao điểm?
A. Hoạt động hợp nhất tệp bắt buộc khóa toàn bộ mạng
B. Hoạt động hợp nhất tệp tự tạo thêm replica
C. Hợp nhất tệp tranh chấp I/O và CPU
D. Hoạt động hợp nhất tệp xóa mọi cache người dùng
Đáp án đúng: C

Câu 34. Thiết kế wide-column với một partition quá lớn dễ dẫn tới vấn đề nào?
A. Đọc và compaction chậm do dữ liệu tập trung
B. Partition key tự đổi sang một trường khác
C. Read quorum luôn lớn hơn write quorum
D. Tất cả truy vấn trở thành duyệt đồ thị
Đáp án đúng: A

Câu 35. Khi một document lớn bị cập nhật một trường nhỏ rất thường xuyên, cần cân nhắc gì?
A. Chi phí phân vùng băm mỗi khi thêm key mới
B. Chi phí cập nhật hoặc ghi lại document lớn
C. Chi phí duyệt mọi đỉnh trước khi đọc document
D. Chi phí tăng replica theo chiều sâu đồ thị
Đáp án đúng: B

Câu 36. Khi thêm field mới vào document mà vẫn hỗ trợ client cũ, cách nào hợp lý?
A. Bắt client cũ luôn gửi field mới trước khi nâng cấp
B. Tự động xóa tất cả document thiếu field mới
C. Coi field mới là tùy chọn và xử lý giá trị thiếu
D. Thay mọi truy vấn bằng phép join qua nhiều index
Đáp án đúng: C

Câu 37. Bài kiểm thử hiệu năng NoSQL cần mô phỏng điều gì để sát production?
A. Chỉ tỷ lệ đọc/ghi khi bỏ qua phân bố khóa
B. Tỷ lệ đọc/ghi, dung lượng và phân bố khóa nóng
C. Chỉ kích thước dữ liệu khi không có ghi mới
D. Chỉ truy vấn một khóa cố định với cache nóng
Đáp án đúng: B

Câu 38. Vì sao cần theo dõi độ trễ p99 ngoài thời gian đáp ứng trung bình?
A. Tính số request trên giây dựa vào một percentile
B. Ước lượng thời gian đáp ứng trung bình của node
C. Xác định mức tải ổn định từ một giá trị trung bình
D. Phát hiện request chậm ở phần đuôi phân bố
Đáp án đúng: D

Câu 39. Kiểm thử fault injection khi mất kết nối giữa các node giúp đánh giá điều gì?
A. Thời gian xử lý cache khi không xảy ra lỗi mạng
B. Chi phí ghi khi không có node nào bị cô lập
C. Hành vi đọc/ghi và phục hồi khi mạng phân vùng
D. Hiệu suất đọc khi toàn bộ replica còn hoạt động
Đáp án đúng: C

Câu 40. Để chọn hệ NoSQL cho một sản phẩm mới, căn cứ nào đáng tin cậy nhất?
A. So sánh benchmark của hãng trên dữ liệu mẫu của hãng
B. So sánh số node tối đa trong tài liệu kiến trúc hệ thống
C. So sánh chỉ tiêu throughput công bố khi tải lý tưởng
D. Kiểm thử truy vấn, tải và nhất quán theo nhu cầu
Đáp án đúng: D
