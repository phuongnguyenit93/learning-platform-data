# Data Mapping Object Mapping

Object Mapping là quá trình chuyển dữ liệu giữa các kiểu đối tượng Java, chẳng hạn domain model, Entity và DTO. Kỹ năng này giúp các tầng ứng dụng trao đổi dữ liệu qua hợp đồng rõ ràng, kiểm soát trường được công khai và giảm sự phụ thuộc trực tiếp vào cấu trúc lưu trữ hoặc API.

Module phù hợp với người đã biết Java hướng đối tượng, collection, getter/setter và kiểu dữ liệu phổ biến. Lộ trình bắt đầu từ mục đích dùng DTO và quy tắc ánh xạ, tiếp tục với mapping thủ công, đối tượng lồng nhau, tập hợp, giá trị null và cập nhật. Sau đó bạn thực hành MapStruct để sinh mã tại thời điểm biên dịch và ModelMapper để hiểu cách ánh xạ động.

Sau khi hoàn thành, bạn có thể chọn kỹ thuật mapping thích hợp, kiểm soát dữ liệu được chuyển đổi và viết kiểm thử cho các trường hợp như đổi tên trường, chuyển kiểu, danh sách, null và chuyển đổi hai chiều.