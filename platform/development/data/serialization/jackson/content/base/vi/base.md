# Data Serialization Jackson

Jackson là thư viện xử lý dữ liệu trong Java, hỗ trợ chuyển đổi qua lại giữa đối tượng Java và JSON. Module này giúp bạn hiểu cách serialize/deserialize, kiểm soát cấu trúc dữ liệu và hạn chế lỗi ánh xạ khi làm việc với API hoặc tệp JSON.

Bạn nên có kiến thức Java cơ bản, POJO và cú pháp JSON. Lộ trình bắt đầu từ các thành phần Jackson, `ObjectMapper` và ánh xạ POJO/collection; tiếp theo là annotation, cây `JsonNode`, cấu hình và module, bộ chuyển đổi tùy chỉnh; cuối cùng là streaming và xử lý lỗi.

Hoàn thành module, bạn có thể đọc/ghi JSON bằng Jackson, tùy chỉnh dữ liệu đầu vào và đầu ra, lựa chọn cách xử lý JSON có cấu trúc hoặc linh hoạt, đồng thời nhận biết những lỗi chuyển đổi thường gặp. Lưu ý: `JavaTimeModule` là lựa chọn phổ biến cho kiểu ngày giờ ở Jackson 2.x; Jackson 3.x đã tích hợp hỗ trợ tương ứng.