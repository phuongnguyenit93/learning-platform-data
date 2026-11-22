# Observability Telemetry Governance Sanitization Filtering

Filtering là bước quyết định dữ liệu quan sát nào được giữ hay loại bỏ trong luồng telemetry. Đối với logs, metrics và traces, lọc đúng giúp hạn chế chuyển tiếp dữ liệu nhạy cảm hoặc không cần thiết, giảm nhiễu và kiểm soát chi phí. Khác với masking hay redaction, filtering có thể loại bỏ toàn bộ log record, span hoặc điểm dữ liệu đáp ứng điều kiện.

Module này hướng dẫn từ phạm vi dữ liệu, chính sách giữ/bỏ và biểu thức OTTL đến vị trí filter trong pipeline OpenTelemetry Collector. Bạn sẽ học cách cấu hình, kiểm thử các trường hợp dữ liệu cần giữ hoặc chặn, đồng thời kiểm tra tác động của việc lọc tới khả năng điều tra lỗi và mối liên kết trace.

Nội dung phù hợp với người đã biết cơ bản về logs, metrics, traces và muốn quản trị luồng observability an toàn hơn. Kết thúc module, bạn có thể giải thích được quyết định lọc, đọc cấu hình filter processor, kiểm chứng kết quả và theo dõi thay đổi để tránh mất tín hiệu vận hành quan trọng.