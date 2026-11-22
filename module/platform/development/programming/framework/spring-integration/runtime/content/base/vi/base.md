# Spring Integration Runtime

**Spring Integration Runtime** tập trung vào cách một luồng tích hợp thực sự vận hành trong ứng dụng: các channel chuyển message, endpoint tiếp nhận và xử lý, poller kích hoạt công việc theo lịch, còn executor quyết định mức độ đồng thời. Hiểu những thành phần này giúp giải thích hành vi khi chạy, đặc biệt ở ranh giới giữa xử lý đồng bộ và bất đồng bộ.

Lộ trình gồm **8 mốc** đi từ khởi tạo IntegrationFlow, channels và threading, consumers và lifecycle, poller và scheduler đến điều khiển tải, xử lý lỗi, transaction và khả năng khôi phục, cuối cùng là quản trị cùng metrics. Mỗi mốc gắn kiến thức cấu hình với việc quan sát message, thread, lỗi và trạng thái endpoint khi ứng dụng chạy.

Học phần phù hợp với người đã biết Spring Boot và các khái niệm cơ bản của Spring Integration như message, channel và IntegrationFlow. Sau khi hoàn thành, bạn có thể giải thích đường đi của một message, chọn cấu hình poller/executor hợp lý, xác định nơi phát sinh lỗi hoặc mất ranh giới transaction, đồng thời theo dõi và kiểm thử hệ thống tích hợp khi vận hành.