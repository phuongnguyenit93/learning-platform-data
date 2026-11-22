# Data Caching

Data Caching là kỹ thuật lưu tạm bản sao của dữ liệu được truy cập thường xuyên để giảm độ trễ và hạn chế tải lên nguồn dữ liệu. Cache giúp tăng tốc ứng dụng nhưng đồng thời đặt ra bài toán về độ mới, dung lượng bộ nhớ và tính đúng của thông tin trả về.

Module dành cho người đã biết Java cơ bản và cách ứng dụng đọc, ghi dữ liệu. Bạn sẽ học cách chọn vị trí cache và cache key, hiểu các chiến lược đọc/ghi như cache-aside, quản lý TTL và eviction, đồng bộ dữ liệu khi nguồn thay đổi và xử lý tình huống nhiều yêu cầu cùng truy cập hoặc cache gặp lỗi. Phần thực hành giới thiệu Caffeine, Spring Cache và Redis theo từng nhu cầu sử dụng.

Sau khi hoàn thành tám mốc, bạn có thể thiết kế một luồng truy cập dữ liệu có cache, viết kiểm thử cho expiration và invalidation, đo hit rate cùng độ trễ và đánh giá liệu cache thực sự cải thiện hiệu năng mà vẫn giữ dữ liệu đúng yêu cầu.