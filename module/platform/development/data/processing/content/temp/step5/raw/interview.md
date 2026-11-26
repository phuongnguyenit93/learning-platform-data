Bạn sẽ xác định đầu vào, đầu ra và các bất biến cần giữ khi thiết kế một pipeline xử lý dữ liệu như thế nào?
Bạn sẽ đánh giá chất lượng nguồn dữ liệu trước khi quyết định các bước chuẩn hóa và biến đổi ra sao?
Bạn sẽ lựa chọn cách xử lý giá trị thiếu, rỗng và không hợp lệ mà không làm mất ý nghĩa nghiệp vụ như thế nào?
Khi hai nguồn dùng đơn vị đo hoặc múi giờ khác nhau, bạn sẽ chuẩn hóa dữ liệu theo quy tắc nào?
Bạn sẽ phân biệt thao tác lọc, ánh xạ, làm phẳng và loại trùng trong một luồng xử lý dữ liệu ra sao?
Bạn sẽ chọn khóa dùng để loại bỏ bản ghi trùng lặp và xử lý trường hợp các bản ghi có nội dung xung đột như thế nào?
Khi dữ liệu chứa nhiều phiên bản của cùng một thực thể, bạn sẽ xác định bản ghi có hiệu lực dựa trên bằng chứng nào?
Bạn sẽ xây dựng một phép join giữa hai tập dữ liệu và phân tích sự khác nhau giữa inner, left và full join ra sao?
Bạn sẽ xử lý sự thay đổi về số lượng bản ghi do quan hệ một-nhiều khi join như thế nào?
Bạn sẽ xác định khóa gom nhóm và phép tổng hợp để bảo đảm kết quả phản ánh đúng nghiệp vụ ra sao?
Bạn sẽ phân biệt count bản ghi, count giá trị không null và count distinct khi tính chỉ số như thế nào?
Bạn sẽ xử lý sai số khi cộng dồn dữ liệu tài chính hoặc dữ liệu số thực với quy mô lớn ra sao?
Khi một pipeline gồm nhiều phép biến đổi, bạn sẽ xác định phép nào có thể đổi thứ tự mà không thay đổi kết quả như thế nào?
Bạn sẽ áp dụng Java Collections khi xử lý dữ liệu cần truy cập ngẫu nhiên, tra cứu và giữ thứ tự theo tiêu chí nào?
Bạn sẽ giải thích sự khác nhau giữa Collection và Stream trong Java về lưu trữ và xử lý dữ liệu như thế nào?
Bạn sẽ sử dụng map, filter và flatMap trong Stream API để biến đổi dữ liệu lồng nhau ra sao?
Bạn sẽ chọn Collector phù hợp để tạo map theo khóa và xử lý trường hợp khóa trùng như thế nào?
Bạn sẽ xây dựng kết quả groupBy và tổng hợp nhiều chỉ số trên một tập dữ liệu bằng Java Stream như thế nào?
Bạn sẽ phân biệt hoạt động trung gian và hoạt động kết thúc trong Java Stream, kể cả tính đánh giá lười, ra sao?
Khi một lambda trong stream sửa trạng thái bên ngoài, bạn sẽ giải thích rủi ro đối với tính đúng và khả năng chạy song song như thế nào?
Bạn sẽ đánh giá việc dùng parallel stream theo kích thước dữ liệu, chi phí tính toán và khả năng chia nhỏ công việc ra sao?
Bạn sẽ phân biệt reduce với collect khi xây dựng phép tổng hợp có thể thực hiện song song như thế nào?
Bạn sẽ xác định tính kết hợp, phần tử đơn vị và khả năng gộp kết quả cần có của một phép reduce ra sao?
Bạn sẽ kiểm tra thứ tự xuất hiện của bản ghi có thực sự được bảo đảm sau các thao tác stream như thế nào?
Bạn sẽ phân biệt xử lý batch với xử lý streaming theo độ trễ, thông lượng và khả năng xem lại dữ liệu ra sao?
Bạn sẽ chọn kích thước lô xử lý dựa trên chi phí I/O, sử dụng bộ nhớ và nhu cầu khôi phục như thế nào?
Khi dữ liệu đầu vào quá lớn để chứa trong RAM, bạn sẽ thay đổi thuật toán và cách đọc ghi ra sao?
Bạn sẽ mô tả vai trò của bộ đệm và backpressure khi tốc độ nguồn vượt quá khả năng xử lý như thế nào?
Bạn sẽ lựa chọn chiến lược giới hạn tốc độ, xếp hàng hoặc giảm tải để tránh pipeline bị quá tải ra sao?
Bạn sẽ phân biệt thời gian sự kiện với thời gian xử lý khi dữ liệu đến không đúng thứ tự như thế nào?
Bạn sẽ lựa chọn cửa sổ tumbling, sliding hoặc session để tính chỉ số theo thời gian dựa trên đặc điểm nào?
Bạn sẽ thiết kế cách xử lý sự kiện đến muộn và cập nhật kết quả cửa sổ sau khi đã công bố như thế nào?
Bạn sẽ giải thích vai trò của watermark trong việc xác định mức tiến triển của thời gian sự kiện ra sao?
Khi phải duy trì trạng thái tổng hợp giữa nhiều sự kiện, bạn sẽ xác định cách lưu, giới hạn và làm sạch trạng thái như thế nào?
Bạn sẽ phân biệt phép biến đổi không trạng thái với phép biến đổi có trạng thái qua một bài toán phát hiện hành vi bất thường ra sao?
Bạn sẽ so sánh các bảo đảm xử lý at-most-once, at-least-once và exactly-once trong bối cảnh dữ liệu đầu ra như thế nào?
Khi pipeline thử lại một sự kiện sau lỗi, bạn sẽ thiết kế phép ghi idempotent để tránh cộng trùng số liệu ra sao?
Bạn sẽ xác định nội dung checkpoint cần lưu và điều kiện có thể khôi phục pipeline từ checkpoint như thế nào?
Khi một bản ghi gây lỗi phân tích cú pháp, bạn sẽ chọn dừng pipeline, bỏ qua hay chuyển sang kênh lỗi dựa trên tiêu chí gì?
Bạn sẽ thiết kế quy trình tái xử lý dữ liệu lỗi sau khi sửa quy tắc chuyển đổi mà vẫn kiểm soát trùng lặp ra sao?
Bạn sẽ giải thích vì sao phân vùng dữ liệu theo khóa ảnh hưởng đến tính đúng của phép gom nhóm phân tán như thế nào?
Khi một khóa xuất hiện quá nhiều so với các khóa khác, bạn sẽ xác định dữ liệu lệch phân bố và cách giảm nghẽn ra sao?
Bạn sẽ đánh giá chi phí truyền dữ liệu giữa các nút khi thực hiện join hoặc groupBy phân tán như thế nào?
Bạn sẽ xác định trường hợp nào có thể dùng xử lý cục bộ trước khi trộn dữ liệu để giảm lượng truyền tải ra sao?
Bạn sẽ bảo đảm tính xác định của kết quả khi các bản ghi được xử lý theo thứ tự khác nhau như thế nào?
Bạn sẽ xây dựng bộ dữ liệu kiểm thử bao phủ giá trị null, bản ghi trùng, trường hợp biên và thứ tự sự kiện như thế nào?
Bạn sẽ đối chiếu kết quả tổng hợp với dữ liệu nguồn bằng các phép kiểm tra bảo toàn và đối soát nào?
Bạn sẽ tổ chức quan sát pipeline qua số bản ghi vào ra, tỷ lệ lỗi, độ trễ và lượng dữ liệu tồn đọng ra sao?
Khi chỉ số tổng hợp giảm bất thường sau một bản phát hành, bạn sẽ lần ngược từng bước pipeline để tìm nguyên nhân như thế nào?
Bạn sẽ thiết kế khả năng mở rộng schema đầu vào mà không làm hỏng các phép biến đổi và kết quả hiện có ra sao?
