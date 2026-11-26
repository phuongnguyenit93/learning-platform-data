Bạn giải thích cache làm giảm độ trễ và tải lên nguồn dữ liệu như thế nào trong một ứng dụng Java?
Những đặc điểm nào của workload khiến việc thêm cache mang lại lợi ích hoặc gây hại?
Bạn phân biệt cache hit, cache miss, hit ratio và miss penalty trong đánh giá hiệu quả ra sao?
Bạn sẽ xác định dữ liệu nào cần cache dựa trên tần suất truy cập, chi phí tính toán và yêu cầu độ mới như thế nào?
Khi một giá trị trong cache cũ hơn dữ liệu gốc, bạn đánh giá mức sai lệch nào còn chấp nhận được?
Bạn so sánh chiến lược cache-aside, read-through và refresh-ahead theo luồng đọc dữ liệu như thế nào?
Bạn lựa chọn giữa write-through, write-behind và vô hiệu hóa cache sau khi ghi dựa trên rủi ro nào?
Khi thao tác ghi vào database thành công nhưng xóa cache thất bại, bạn sẽ bảo vệ tính đúng đắn ra sao?
Bạn sẽ thiết kế cache key cho dữ liệu phụ thuộc vào người dùng, ngôn ngữ và bộ lọc truy vấn như thế nào?
Bạn kiểm soát nguy cơ cache key collision hoặc vô tình chia sẻ dữ liệu giữa các tenant bằng cách nào?
Khi một API trả dữ liệu phân trang, bạn thiết kế cache key để phản ánh thứ tự sắp xếp và tham số phân trang ra sao?
Bạn sẽ xác định TTL phù hợp khi dữ liệu thay đổi theo chu kỳ và chi phí tái tạo cao như thế nào?
TTL cố định và TTL có độ lệch ngẫu nhiên ảnh hưởng thế nào đến hiện tượng nhiều khóa hết hạn đồng thời?
Bạn so sánh hết hạn theo thời gian ghi và hết hạn theo lần truy cập cuối trong các kịch bản nào?
Bạn dùng cơ chế versioned key hoặc namespace để tránh đọc dữ liệu cũ sau triển khai như thế nào?
Bạn lựa chọn eviction policy LRU, LFU hoặc dựa trên kích thước theo đặc trưng truy cập ra sao?
Một cache bị giới hạn dung lượng có thể tạo áp lực bộ nhớ và garbage collection trong JVM như thế nào?
Bạn sẽ xác định giới hạn số phần tử hoặc trọng số trong cache dựa trên dữ liệu thực tế bằng cách nào?
Khi tỷ lệ hit cao nhưng độ trễ API vẫn tăng, bạn sẽ điều tra những nguyên nhân nào?
Bạn phân biệt cache penetration, cache breakdown và cache stampede bằng các ví dụ truy cập như thế nào?
Bạn thiết kế single-flight hoặc khóa theo cache key để tránh nhiều request cùng tái tạo một giá trị ra sao?
Bạn đánh giá ưu nhược điểm của việc cache kết quả rỗng để giảm truy vấn với khóa không tồn tại như thế nào?
Bạn sử dụng TTL ngắn và bộ lọc yêu cầu đầu vào để chống truy vấn vào các khóa giả mạo ra sao?
Khi cache hết hạn trong lúc backend chậm, bạn áp dụng stale-while-revalidate theo giới hạn độ mới nào?
Bạn sẽ phối hợp timeout, circuit breaker và fallback khi cache phân tán không phản hồi như thế nào?
Bạn so sánh cache cục bộ trong JVM với cache phân tán về độ trễ, tính nhất quán và khả năng mở rộng ra sao?
Trong hệ thống có nhiều instance, bạn đồng bộ sự kiện invalidation giữa các cache cục bộ như thế nào?
Bạn thiết kế chiến lược caching hai tầng giữa Caffeine và Redis với thứ tự đọc ghi nào?
Khi cache L1 và L2 có TTL khác nhau, bạn phân tích nguy cơ dữ liệu cũ được tái đưa vào L1 ra sao?
Bạn cấu hình Caffeine với maximumSize, expireAfterWrite và thống kê cache theo nhu cầu nào?
Bạn sẽ sử dụng cơ chế tải dữ liệu của Caffeine để tránh tính toán lặp cho cùng một khóa như thế nào?
Khi cần nạp lại dữ liệu bất đồng bộ bằng Caffeine, bạn xử lý ngoại lệ và giá trị cũ ra sao?
Bạn chọn kiểu dữ liệu Redis String, Hash hoặc Sorted Set cho một trường hợp cache như thế nào?
Bạn sẽ đánh giá serialization, kích thước payload và tương thích schema khi lưu đối tượng Java vào Redis ra sao?
Bạn phân tích tác động của network round trip và Redis pipelining đối với các thao tác cache hàng loạt như thế nào?
Khi nhiều luồng cùng sửa một khóa Redis, bạn sẽ kiểm soát race condition và lost update ra sao?
Bạn sử dụng TTL và lệnh xóa khóa trong Redis thế nào để tránh các phiên bản dữ liệu tồn tại quá lâu?
Bạn xác định nhu cầu Redis replication hoặc clustering dựa trên độ sẵn sàng và phân phối tải như thế nào?
Trong Spring Cache, bạn sử dụng @Cacheable, @CachePut và @CacheEvict cho các luồng nghiệp vụ nào?
Khi phương thức có tham số phức tạp, bạn xây dựng key generator trong Spring Cache như thế nào?
Vì sao self-invocation có thể khiến annotation caching dựa trên proxy không có hiệu lực, và bạn sẽ khắc phục thế nào?
Khi một transaction rollback, bạn phối hợp thời điểm invalidation với commit để tránh cache chứa dữ liệu sai như thế nào?
Bạn thiết kế kiểm thử cho cache hit, miss, TTL và invalidation mà không phụ thuộc vào thời gian chờ thực như thế nào?
Bạn sẽ kiểm thử tải đồng thời để chứng minh cơ chế chống stampede hoạt động hiệu quả ra sao?
Bạn đo sự khác biệt p50, p95, p99 latency và tải database trước và sau khi bật cache như thế nào?
Những chỉ số cache eviction, memory usage, backend load và error rate nào bạn đưa vào dashboard vận hành?
Khi Redis bị sự cố hoàn toàn, bạn giới hạn lượng request đổ về database để tránh sự cố dây chuyền ra sao?
Bạn kiểm soát dữ liệu nhạy cảm trong cache qua quyền truy cập, mã hóa và chính sách thời gian lưu như thế nào?
Khi business yêu cầu cập nhật dữ liệu gần thời gian thực, bạn so sánh invalidation theo event với polling ra sao?
Bạn sẽ xây dựng kế hoạch triển khai thử, quan sát và rollback cho một thay đổi chiến lược cache như thế nào?
