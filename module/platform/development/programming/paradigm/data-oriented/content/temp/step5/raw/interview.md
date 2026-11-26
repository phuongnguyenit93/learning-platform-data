Bạn giải thích Data-Oriented Programming là gì và các tiêu chí nào cho thấy một thiết kế thực sự lấy dữ liệu làm trung tâm?
Bạn phân biệt Data-Oriented Programming trong mô hình hóa phần mềm với Data-Oriented Design tập trung vào cách truy cập bộ nhớ như thế nào?
Bạn đánh giá những lợi ích và giới hạn của việc tách cấu trúc dữ liệu khỏi các hàm xử lý so với cách gắn hành vi trực tiếp vào đối tượng ra sao?
Bạn xác định ranh giới giữa dữ liệu nghiệp vụ, quy tắc biến đổi và tác vụ có tác dụng phụ trong một hệ thống như thế nào?
Bạn thiết kế một hợp đồng dữ liệu tường minh để các thành phần độc lập có thể hiểu và kiểm tra cùng một bản ghi ra sao?
Bạn chọn record, struct, tuple hay cấu trúc tương đương dựa trên những yêu cầu nào về tính rõ nghĩa, khả năng mở rộng và hiệu năng?
Bạn sử dụng kiểu tổng và kiểu tích để biểu diễn các trạng thái nghiệp vụ hữu hạn và loại trừ trạng thái không hợp lệ như thế nào?
Bạn kiểm soát các bất biến liên quan đến nhiều trường dữ liệu khi mô hình chủ yếu gồm những giá trị đơn giản ra sao?
Bạn mô tả và kiểm tra chuyển trạng thái từ dữ liệu đầu vào sang dữ liệu đầu ra như thế nào khi quy trình có nhiều bước?
Bạn quyết định khi nào một dữ liệu nên được biểu diễn lồng nhau và khi nào nên tách thành các bảng hoặc tập bản ghi có khóa liên kết ra sao?
Bạn xử lý danh tính, vòng đời và quan hệ giữa các thực thể khi cấu trúc dữ liệu không mang trực tiếp các phương thức nghiệp vụ như thế nào?
Bạn cân nhắc việc lưu dữ liệu dư thừa để đọc nhanh với việc chuẩn hóa nhằm giảm sai lệch thông tin ra sao?
Bạn xác định dữ liệu nào cần bất biến và dữ liệu nào được phép thay đổi tại chỗ trong một pipeline xử lý như thế nào?
Bạn cập nhật một nhánh nhỏ trong cấu trúc dữ liệu lồng nhau bất biến mà vẫn kiểm soát chi phí sao chép như thế nào?
Bạn lựa chọn giữa structural sharing, copy-on-write và tạo bản sao toàn phần dựa trên đặc điểm truy cập nào?
Bạn đặt ranh giới đột biến cục bộ ở đâu để vừa giữ giao diện xử lý dễ suy luận vừa tránh phân bổ bộ nhớ không cần thiết?
Bạn nhận biết một hàm biến đổi dữ liệu thuần và phân tách các phụ thuộc thời gian, ngẫu nhiên hoặc I/O để kiểm thử ra sao?
Bạn thiết kế chuỗi phép biến đổi sao cho mỗi bước có đầu vào, đầu ra và điều kiện hợp lệ quan sát được như thế nào?
Bạn đưa những kiểm tra nào vào bước tiếp nhận dữ liệu không đáng tin cậy trước khi chuyển thành mô hình nội bộ?
Bạn phân biệt trường không tồn tại, giá trị null, giá trị mặc định và giá trị không hợp lệ trong hợp đồng dữ liệu như thế nào?
Bạn thiết kế thông tin lỗi xác thực để chỉ rõ phần dữ liệu sai mà không làm lộ thông tin nhạy cảm ra sao?
Bạn xây dựng chiến lược tiến hóa schema khi bên phát và bên nhận dữ liệu được triển khai ở các thời điểm khác nhau như thế nào?
Bạn đánh giá tương thích ngược và tương thích xuôi khi thêm, bỏ hoặc đổi ý nghĩa một trường dữ liệu ra sao?
Bạn cân nhắc mô hình dữ liệu có kiểu tĩnh so với map hoặc document linh hoạt trong một hệ thống có yêu cầu thay đổi schema liên tục như thế nào?
Bạn phân tách dữ liệu truyền qua API, dữ liệu lưu trữ và dữ liệu phục vụ tính toán nội bộ theo những tiêu chí nào?
Bạn thiết kế quá trình tuần tự hóa và giải tuần tự hóa sao cho không làm mất ý nghĩa của kiểu dữ liệu, thứ tự hay độ chính xác như thế nào?
Bạn xử lý các bản ghi đến sai thứ tự hoặc trùng lặp trong một luồng cập nhật trạng thái dựa trên dữ liệu ra sao?
Bạn biểu diễn thay đổi dữ liệu dưới dạng sự kiện so với bản chụp trạng thái và lựa chọn giữa chúng theo yêu cầu nào?
Bạn sử dụng kiểm thử dựa trên thuộc tính để xác minh các bất biến của những phép chuyển đổi dữ liệu như thế nào?
Bạn kiểm thử các trường hợp thiếu dữ liệu, dữ liệu cực lớn, dữ liệu sai định dạng và ranh giới số học trong pipeline như thế nào?
Bạn giải thích tại sao cách bố trí dữ liệu trong bộ nhớ có thể ảnh hưởng tới hiệu năng dù số phép toán không thay đổi?
Bạn phân biệt spatial locality và temporal locality, đồng thời xác định chúng từ một mẫu truy cập cụ thể như thế nào?
Bạn so sánh Array of Structures (AoS) và Structure of Arrays (SoA) khi thuật toán chỉ cần đọc một vài thuộc tính của hàng triệu phần tử ra sao?
Bạn chọn bố trí theo hàng hoặc theo cột cho các truy vấn cập nhật, quét và tổng hợp dữ liệu khác nhau như thế nào?
Bạn tách dữ liệu được truy cập thường xuyên khỏi dữ liệu ít dùng để cải thiện tỷ lệ trúng cache như thế nào?
Bạn giải thích cache line, kích thước phần tử và padding ảnh hưởng tới mật độ dữ liệu hữu ích trong cache ra sao?
Bạn đánh giá tác động của alignment và stride đến việc tải dữ liệu tuần tự từ bộ nhớ như thế nào?
Bạn xác định điểm nghẽn do pointer chasing trong một cấu trúc liên kết nhiều cấp bằng cách nào?
Bạn thay thế tham chiếu phân tán bằng chỉ số vào mảng trong những trường hợp nào và quản lý tính hợp lệ của chỉ số ra sao?
Bạn phân biệt một tác vụ bị giới hạn bởi băng thông bộ nhớ với một tác vụ bị giới hạn bởi năng lực tính toán như thế nào?
Bạn dùng các chỉ số cache miss, số byte đọc ghi và số phép toán để giải thích kết quả đo hiệu năng ra sao?
Bạn giải thích vai trò của TLB và kích thước trang bộ nhớ khi quét một tập dữ liệu lớn có truy cập rải rác như thế nào?
Bạn nhận diện chi phí cấp phát đối tượng, thu gom rác và phân mảnh bộ nhớ trong một chương trình xử lý khối lượng lớn ra sao?
Bạn cân nhắc bộ nhớ do runtime quản lý và vùng nhớ ngoài heap hoặc bộ nhớ native theo những rủi ro vòng đời và lợi ích nào?
Bạn thiết kế mảng hoặc buffer có dung lượng tăng dần để hạn chế cấp phát lại mà không sử dụng bộ nhớ quá mức như thế nào?
Bạn quyết định khi nào nén dữ liệu, mã hóa bit hoặc dùng kiểu số hẹp giúp tăng thông lượng dù phải thêm chi phí giải mã ra sao?
Bạn sử dụng bitmap hoặc bitset để biểu diễn tập cờ và hỗ trợ thao tác trên nhiều phần tử như thế nào?
Bạn lựa chọn cấu trúc dữ liệu dựa trên chuỗi truy cập thực tế thay vì chỉ dựa vào độ phức tạp tiệm cận như thế nào?
Bạn đo trade-off giữa tăng locality và chi phí chuyển đổi dữ liệu khi một hệ thống phải phục vụ nhiều kiểu truy vấn ra sao?
Bạn giải thích các vai trò riêng của Entity, Component và System trong kiến trúc Entity Component System (ECS) như thế nào?
Bạn thiết kế các component dữ liệu sao cho các system có thể dùng lại mà vẫn tránh liên kết ngầm giữa chúng ra sao?
Bạn chọn mức độ chi tiết của component dựa trên sự đồng xuất hiện và tần suất truy cập các trường như thế nào?
Bạn biểu diễn và quản lý vòng đời entity như thế nào khi cần tạo mới, hủy và tái sử dụng định danh?
Bạn xử lý nguy cơ tham chiếu tới entity đã bị xóa khi dùng chỉ số tái sử dụng trong kho lưu trữ ECS ra sao?
Bạn so sánh lưu trữ ECS kiểu archetype và sparse set theo mẫu thêm bớt component và truy vấn ra sao?
Bạn triển khai truy vấn các entity có một tập component bắt buộc nhưng không có một component khác như thế nào?
Bạn kiểm soát chi phí dịch chuyển dữ liệu khi entity thường xuyên được thêm hoặc gỡ component trong ECS ra sao?
Bạn thiết lập thứ tự thực thi và khai báo phụ thuộc đọc ghi giữa các system để bảo đảm kết quả đúng như thế nào?
Bạn lựa chọn cơ chế truyền sự kiện giữa các system so với để system đọc trực tiếp dữ liệu chung dựa trên tiêu chí nào?
Bạn chia các system độc lập thành công việc song song mà vẫn kiểm soát tranh chấp khi truy cập component ra sao?
Bạn xây dựng snapshot và cơ chế tái phát để tái hiện chính xác một trạng thái mô phỏng ECS như thế nào?
Bạn đánh giá khi nào ECS mang lại lợi ích và khi nào mô hình đối tượng truyền thống dễ vận hành hơn ra sao?
Bạn áp dụng cách tổ chức dữ liệu theo ECS cho một miền ngoài trò chơi, chẳng hạn xử lý thiết bị hoặc mô phỏng sản xuất, như thế nào?
Bạn tổ chức một tác vụ xử lý hàng triệu bản ghi thành các lô để giảm overhead điều phối và tăng locality như thế nào?
Bạn chọn kích thước batch dựa trên giới hạn bộ nhớ, chi phí khởi tạo, thông lượng và độ trễ cuối cùng ra sao?
Bạn giải thích SIMD xử lý nhiều phần tử đồng dạng cùng lúc như thế nào và cách tổ chức vòng lặp ảnh hưởng đến khả năng vector hóa ra sao?
Bạn nhận diện các phép toán nào trong pipeline phù hợp để vector hóa và các phép toán nào thường cản trở vector hóa ra sao?
Bạn phân tích ảnh hưởng của rẽ nhánh phụ thuộc dữ liệu, aliasing và truy cập không liên tục tới khả năng tự vector hóa như thế nào?
Bạn xử lý phần tử dư ở cuối vector, mặt nạ điều kiện và dữ liệu không thẳng hàng trong một thuật toán SIMD ra sao?
Bạn kiểm soát sai khác số học dấu phẩy động, thứ tự cộng dồn và tràn số khi chuyển từ tính toán vô hướng sang SIMD như thế nào?
Bạn cân nhắc chi phí đóng gói hoặc chuyển đổi dữ liệu trước khi thực hiện một phép tính vector hóa ra sao?
Bạn thiết kế phương án fallback khi kiến trúc CPU hoặc runtime không hỗ trợ tập lệnh vector mong muốn như thế nào?
Bạn kiểm chứng rằng tối ưu SIMD cải thiện hiệu năng toàn pipeline chứ không chỉ một vòng lặp nhỏ như thế nào?
Bạn phân chia tập dữ liệu thành các đoạn xử lý song song để cân bằng tải và giảm tranh chấp bộ nhớ ra sao?
Bạn tránh data race khi nhiều worker cùng cập nhật những vùng dữ liệu có thể chồng lấn như thế nào?
Bạn giữ kết quả tổng hợp có tính xác định khi thay đổi thứ tự xử lý song song hoặc dùng phép reduction như thế nào?
Bạn giải thích false sharing giữa các luồng và cách nhận biết nó bằng số liệu đo đạc ra sao?
Bạn tổ chức buffer đầu vào, đầu ra và cơ chế chuyển quyền sở hữu để giảm sao chép giữa các giai đoạn đồng thời như thế nào?
Bạn áp dụng backpressure khi tốc độ tạo batch vượt khả năng tiêu thụ mà vẫn giữ giới hạn sử dụng bộ nhớ ra sao?
Bạn thiết kế phép đo benchmark để tránh sai lệch do JIT, warm-up, dead-code elimination, GC hoặc kích thước dữ liệu quá nhỏ như thế nào?
Bạn kết hợp CPU profiler, allocation profiler và bộ đếm phần cứng để xác định nút thắt của thuật toán xử lý dữ liệu ra sao?
Bạn chọn các chỉ số thông lượng, độ trễ phân vị, bộ nhớ đỉnh và mức tiêu thụ CPU để đánh giá một thay đổi bố trí dữ liệu như thế nào?
Bạn sử dụng định luật Amdahl để đánh giá giới hạn lợi ích khi tối ưu một bước xử lý chiếm tỷ lệ nhỏ trong pipeline ra sao?
Bạn thiết kế lại luồng xử lý telemetry có hàng triệu sự kiện mỗi phút nhằm giảm phân bổ và tăng hiệu quả quét dữ liệu ra sao?
Bạn lựa chọn cách biểu diễn và sắp xếp dữ liệu cho bài toán tính toán tọa độ hoặc chuyển động của hàng trăm nghìn phần tử như thế nào?
Bạn điều chỉnh thiết kế khi một API nghiệp vụ có lưu lượng thấp cần tính rõ ràng hơn tốc độ quét dữ liệu như thế nào?
Bạn lên kế hoạch di chuyển dần một bộ xử lý từ danh sách đối tượng sang mảng dữ liệu theo cột mà vẫn giữ hợp đồng đầu ra như thế nào?
Bạn xác định những ranh giới bảo mật và quyền truy cập nào phải được duy trì khi tách dữ liệu khỏi hành vi kiểm soát nó?
Bạn thiết kế tiêu chí quyết định giữ hay hoàn tác một tối ưu hướng dữ liệu sau khi so sánh số đo và chi phí bảo trì như thế nào?
