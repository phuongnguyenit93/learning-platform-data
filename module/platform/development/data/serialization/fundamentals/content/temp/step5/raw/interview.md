Bạn sẽ giải thích vai trò của serialization và deserialization khi trao đổi dữ liệu giữa các tiến trình hoặc lưu trữ lâu dài như thế nào?
Bạn sẽ phân biệt biểu diễn dữ liệu trong bộ nhớ với biểu diễn dữ liệu trên đường truyền bằng những ví dụ nào?
Khi thiết kế định dạng trao đổi dữ liệu, bạn sẽ xác định những yêu cầu nào về tính đúng, tính di động và hiệu năng?
Bạn sẽ giải thích mối liên hệ giữa bit, byte, ký tự Unicode và encoding trong việc ghi một chuỗi ra tệp như thế nào?
Bạn sẽ kiểm tra việc hai hệ thống sử dụng thứ tự byte khác nhau có làm sai giá trị số nhị phân ra sao?
Bạn sẽ xác định cách biểu diễn số nguyên có dấu và số thực để dữ liệu được đọc lại nhất quán như thế nào?
Khi một giá trị số vượt quá phạm vi kiểu đích, bạn sẽ lựa chọn chính sách chuyển đổi và báo lỗi ra sao?
Bạn sẽ phân biệt giá trị null, trường không tồn tại và chuỗi rỗng trong một tài liệu dữ liệu như thế nào?
Bạn sẽ quyết định một thuộc tính nên bắt buộc hay tùy chọn trong schema theo nguyên tắc nào?
Bạn sẽ lựa chọn JSON, XML, CSV, YAML hoặc định dạng nhị phân dựa trên mục đích sử dụng và đánh đổi nào?
Bạn sẽ phân tích sự khác nhau giữa cấu trúc đối tượng, mảng và kiểu dữ liệu nguyên thủy trong JSON như thế nào?
Bạn sẽ xử lý trường hợp một văn bản JSON có tên thuộc tính trùng lặp để tránh kết quả đọc khác nhau giữa thư viện ra sao?
Bạn sẽ thiết kế quy tắc biểu diễn ngày giờ và múi giờ để các hệ thống không hiểu sai cùng một thời điểm như thế nào?
Bạn sẽ kiểm soát tính chính xác của số thập phân khi một hệ thống sinh JSON và hệ khác đọc vào như thế nào?
Khi ánh xạ object có nhiều tham chiếu chung hoặc tham chiếu vòng, bạn sẽ quyết định cách biểu diễn dữ liệu ra sao?
Bạn sẽ giải thích ưu điểm của việc tách schema trao đổi khỏi mô hình đối tượng nội bộ như thế nào?
Bạn sẽ xác định cách đặt tên trường dữ liệu để cân bằng tính rõ nghĩa và khả năng tương thích lâu dài ra sao?
Bạn sẽ đánh giá rủi ro khi thêm một trường mới vào schema mà người đọc cũ không biết xử lý như thế nào?
Bạn sẽ lựa chọn chính sách xử lý trường không nhận diện được khi deserialization dựa trên mức độ nghiêm ngặt của hợp đồng nào?
Bạn sẽ mô tả một chiến lược phát triển schema để ứng dụng cũ và mới cùng trao đổi dữ liệu như thế nào?
Bạn sẽ giải thích sự khác nhau giữa tương thích ngược và tương thích xuôi qua một lần thay đổi cấu trúc thông điệp ra sao?
Khi cần đổi tên hoặc bỏ một trường cũ, bạn sẽ lập kế hoạch chuyển đổi qua nhiều phiên bản như thế nào?
Bạn sẽ quyết định sử dụng schema tường minh hay suy ra schema từ dữ liệu trong từng tình huống ra sao?
Bạn sẽ mô tả vai trò của namespace, attribute và element khi ánh xạ mô hình dữ liệu sang XML như thế nào?
Bạn sẽ kiểm tra rủi ro thực thể ngoài trong XML và cách giới hạn khả năng truy cập tài nguyên của parser ra sao?
Bạn sẽ thiết kế cách đọc CSV chứa dấu phân tách trong chuỗi, dấu ngoặc kép và ký tự xuống dòng như thế nào?
Bạn sẽ phân biệt trường hợp CSV có header, thiếu cột hoặc thay đổi thứ tự cột khi đọc dữ liệu như thế nào?
Bạn sẽ phòng ngừa nguy cơ công thức được thực thi ngoài ý muốn khi xuất CSV để mở bằng phần mềm bảng tính ra sao?
Bạn sẽ đánh giá ưu điểm và rủi ro của YAML khi dùng cho cấu hình, nhất là alias và kiểu dữ liệu suy diễn, như thế nào?
Bạn sẽ so sánh kích thước, khả năng tự mô tả và chi phí giải mã giữa định dạng văn bản và định dạng nhị phân ra sao?
Khi dữ liệu phải truyền qua mạng với băng thông hạn chế, bạn sẽ cân nhắc nén và chi phí CPU theo tiêu chí nào?
Bạn sẽ giải thích tại sao mã hóa bảo mật, nén và serialization là các bước có trách nhiệm khác nhau như thế nào?
Bạn sẽ thiết kế cơ chế kiểm tra tính toàn vẹn của thông điệp khi lưu hoặc truyền dữ liệu qua môi trường không tin cậy ra sao?
Khi dữ liệu có kích thước lớn, bạn sẽ lựa chọn deserialization toàn bộ hay đọc luồng từng phần dựa trên yếu tố nào?
Bạn sẽ xác định giới hạn về kích thước tài liệu, độ sâu lồng nhau và số lượng phần tử để ngăn cạn kiệt tài nguyên như thế nào?
Bạn sẽ phân biệt lỗi cú pháp dữ liệu với lỗi kiểm tra hợp lệ nghiệp vụ sau deserialization bằng cách nào?
Khi đầu vào chứa kiểu dữ liệu không đúng với schema, bạn sẽ thiết kế báo lỗi cung cấp đủ vị trí và ngữ cảnh ra sao?
Bạn sẽ xác định dữ liệu nào cần loại bỏ hoặc che giấu trước khi serialization để tránh rò rỉ thông tin nhạy cảm như thế nào?
Bạn sẽ giải thích cơ chế Java Serialization lưu đồ thị đối tượng và xử lý tham chiếu chia sẻ ra sao?
Bạn sẽ phân biệt vai trò của Serializable, transient và serialVersionUID trong vòng đời dữ liệu Java như thế nào?
Khi thay đổi cấu trúc một lớp Serializable, bạn sẽ đánh giá khả năng đọc dữ liệu cũ dựa trên những điều kiện nào?
Bạn sẽ giải thích vì sao deserialize dữ liệu Java không đáng tin cậy có thể gây nguy cơ bảo mật nghiêm trọng như thế nào?
Bạn sẽ quyết định khi nào không nên sử dụng Java native Serialization cho dữ liệu qua biên tin cậy ra sao?
Bạn sẽ sử dụng các hook tùy biến của Java Serialization trong phạm vi nào và kiểm soát bất biến đối tượng như thế nào?
Bạn sẽ thiết kế kiểm thử round-trip để phát hiện giá trị nào bị mất hoặc biến đổi không mong muốn sau hai chiều chuyển đổi ra sao?
Bạn sẽ kiểm tra các trường hợp biên gồm ký tự đặc biệt, số lớn, null và collection rỗng khi thử nghiệm bộ serializer như thế nào?
Bạn sẽ phân biệt việc hai dữ liệu có cùng ý nghĩa với việc chúng có cùng thứ tự byte được serialized ra sao?
Bạn sẽ triển khai kiểm thử tương thích giữa phiên bản bộ đọc cũ và bộ ghi mới theo ma trận nào?
Khi một hệ thống nhận thông điệp lỗi định dạng trong môi trường sản xuất, bạn sẽ cách ly, ghi nhận và xử lý thông điệp đó ra sao?
Bạn sẽ lập kế hoạch thay đổi định dạng dữ liệu của một API đang được nhiều đối tác sử dụng để giảm rủi ro gián đoạn như thế nào?
