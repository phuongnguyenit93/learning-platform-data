# Database Engine Time Series InfluxDB

InfluxDB là cơ sở dữ liệu tối ưu cho dữ liệu chuỗi thời gian, nơi mỗi quan sát gắn với một mốc thời gian. Loại dữ liệu này xuất hiện trong hệ thống giám sát ứng dụng, thiết bị IoT, cảm biến và các phép đo thay đổi liên tục. Để khai thác tốt InfluxDB, cần hiểu cách lưu timestamp, phân biệt tags với fields và lựa chọn cấu trúc phục vụ truy vấn theo thời gian.

Module này phù hợp với người học backend, Data Engineering hoặc vận hành hệ thống muốn làm quen với InfluxDB. Lộ trình thực hành lấy InfluxDB 3 Core làm nền tảng: khởi tạo database, thiết kế schema, ghi dữ liệu bằng line protocol hoặc Telegraf, truy vấn bằng SQL/InfluxQL, tổng hợp và trực quan hóa kết quả. Cuối cùng, bạn sẽ tìm hiểu retention period và các thao tác vận hành cơ bản. Lưu ý Flux thuộc hệ sinh thái InfluxDB 2 và không được hỗ trợ trong InfluxDB 3 Core.

Hãy thử thu thập nhiệt độ cảm biến hoặc metrics ứng dụng theo từng phút, viết dữ liệu vào database rồi vẽ đồ thị biến động trong ngày. Sau module, bạn có thể mô hình hóa dữ liệu chuỗi thời gian, xây luồng nạp dữ liệu và kiểm tra truy vấn, đồng thời chọn chính sách lưu trữ phù hợp trước khi đưa vào sử dụng.