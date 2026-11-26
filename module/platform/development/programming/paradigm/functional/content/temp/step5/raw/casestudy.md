Một hệ thống tính phí vận chuyển đang đọc trực tiếp bảng giá toàn cục khiến kết quả thay đổi giữa hai lần gọi với cùng đơn hàng; hãy thiết kế lại ranh giới dữ liệu và phép tính để kiểm tra được tính thuần của logic báo giá?
Một dịch vụ tính thuế đơn hàng gọi đồng hồ hệ thống để chọn biểu thuế đang hiệu lực, làm kết quả kiểm thử phụ thuộc thời điểm chạy; hãy xác định cách biểu diễn thời gian và đầu vào để tái hiện cùng kết quả?
Một chương trình phân bổ mã khuyến mãi sử dụng bộ sinh số ngẫu nhiên ẩn trong phép tính, khiến lỗi khó tái hiện; hãy thiết kế hợp đồng xử lý để kiểm soát sự ngẫu nhiên khi kiểm thử và chạy thực tế?
Một hệ thống thanh toán tính số dư dựa trên giao dịch nhưng đồng thời ghi lịch sử trong cùng phương thức, khiến việc chạy lại gây ghi trùng; hãy xác định ranh giới giữa biến đổi dữ liệu và tác dụng phụ?
Một bộ tính điểm tín dụng nhận hồ sơ khách hàng có nhiều trường có thể bị chỉnh sửa sau khi gửi yêu cầu; hãy đề xuất mô hình dữ liệu và quy trình xử lý tránh kết quả phụ thuộc thay đổi ngoài ý muốn?
Một nhóm phát triển chia sẻ một danh sách cấu hình có thể thay đổi giữa các bộ xử lý song song, dẫn đến lỗi không tái hiện ổn định; hãy lựa chọn cách biểu diễn trạng thái cho một lần xử lý nhất quán?
Một hệ thống giỏ hàng cần cập nhật số lượng một sản phẩm mà vẫn giữ được ảnh chụp giỏ hàng trước đó để hoàn tác; hãy thiết kế phép biến đổi bất biến và cân nhắc chi phí sao chép?
Một ứng dụng quản lý hồ sơ chứa cây địa chỉ và thông tin liên hệ lồng nhiều cấp, nhưng chỉnh sửa một trường đang sao chép toàn bộ cây; hãy phân tích khả năng chia sẻ cấu trúc và rủi ro về danh tính tham chiếu?
Một thư viện công khai cấu trúc bất biến ở lớp ngoài nhưng bên trong giữ một mảng có thể sửa qua getter, khiến dữ liệu thay đổi ngầm; hãy xác định cách kiểm tra và bảo vệ ranh giới bất biến?
Một đội phân tích dữ liệu đưa đối tượng có bộ nhớ đệm nội bộ vào phép so sánh giá trị, làm kết quả phụ thuộc lần truy cập trước; hãy phân biệt trạng thái quan sát được với chi tiết triển khai khi thiết kế mô hình?
Một chức năng cấp quyền lấy danh sách vai trò từ biến toàn cục có thể bị sửa giữa chừng, làm cùng yêu cầu có hai quyết định khác nhau; hãy thiết kế đầu vào tường minh cho phép đánh giá chính sách?
Một bảng điều khiển sử dụng hàm chuyển đổi dữ liệu nhưng hàm này âm thầm cập nhật biến đếm toàn cục, làm xử lý song song cho kết quả sai; hãy xác định tác dụng phụ và ranh giới có thể kiểm soát?
Một công cụ nhập dữ liệu chỉ được phép tạo bản ghi mới khi mọi phép kiểm tra đầu vào thành công, nhưng các bước kiểm tra hiện ghi dữ liệu dở dang; hãy thiết kế chuỗi kiểm tra với kết quả và tác dụng phụ được phân tách?
Một hệ thống đặt vé cần giữ phiên bản trước và sau mỗi thay đổi trạng thái để phục vụ audit và hoàn tác; hãy mô hình hóa các phép chuyển trạng thái như những phép biến đổi giá trị có thể kiểm chứng?
Một nền tảng thông báo dùng một closure bắt giữ biến trạng thái có thể đổi trong lúc hàng đợi đang xử lý, làm nội dung gửi không đúng kỳ vọng; hãy đánh giá cách chụp giá trị và kiểm soát phụ thuộc của closure?
Một hệ thống định giá có nhiều quy tắc giảm giá tùy khu vực và nhóm khách hàng, mỗi nơi lại viết vòng lặp lọc riêng; hãy xây dựng hướng tổ chức các hàm bậc cao cho các bước lọc và tính tổng?
Một ứng dụng thương mại điện tử có ba cách sắp xếp sản phẩm theo giá, mức độ phổ biến và thời gian tạo, nhưng mã sắp xếp lặp lại; hãy phân tích cách truyền hành vi so sánh như dữ liệu đầu vào?
Một bộ xử lý tài liệu cần chuẩn hóa văn bản, kiểm tra định dạng và chuyển sang cấu trúc nội bộ theo thứ tự, nhưng mỗi bước có kiểu đầu vào khác nhau; hãy thiết kế hợp đồng hợp thành giữa các phép biến đổi?
Một dịch vụ chống gian lận áp dụng một tập quy tắc có thể cấu hình mà không muốn chỉnh sửa hàm xử lý lõi mỗi khi thêm quy tắc; hãy thiết kế mô hình truyền các predicate và quy tắc hợp thành?
Một ứng dụng quản lý nhân sự có nhiều điều kiện chọn ứng viên, nhưng thứ tự áp dụng các điều kiện đang ảnh hưởng tới dữ liệu được ghi nhận; hãy phân tích điều kiện để hoán đổi hoặc hợp thành các phép lọc an toàn?
Một hệ thống tổng hợp chỉ số vận hành có các bước ánh xạ, lọc và gom nhóm giống nhau trên nhiều nguồn dữ liệu; hãy thiết kế khả năng tái sử dụng pipeline mà không làm mất ngữ nghĩa của từng nguồn?
Một dịch vụ xuất hóa đơn có một hàm chuyển số tiền sang chuỗi và một hàm thêm đơn vị tiền tệ, nhưng thành viên ghép hai hàm nhầm thứ tự; hãy làm rõ hợp đồng kiểu và thứ tự hợp thành cần kiểm thử?
Một nền tảng tìm kiếm thực hiện nhiều phép biến đổi tập kết quả liên tiếp rồi chạy lại toàn bộ cho mỗi loại báo cáo; hãy đánh giá khả năng trích xuất các hàm biến đổi có thể cấu hình và tái sử dụng?
Một hệ thống quản lý email sử dụng callback để phân loại thư, nhưng callback có thể ném lỗi hoặc ghi log trong quá trình lọc; hãy xác định ranh giới an toàn khi truyền hàm bậc cao vào pipeline?
Một engine giá động cho phép đối tác truyền quy tắc tính phí do họ viết, khiến cùng đơn hàng đôi khi trả kết quả khác nhau; hãy thiết kế hợp đồng kiểm soát độ thuần của hàm được truyền vào?
Một nhóm phát triển tạo nhiều hàm bao bọc để ghi log, đo thời gian và thử lại lời gọi API, nhưng thứ tự bao bọc làm thay đổi tác dụng quan sát được; hãy đánh giá thứ tự hợp thành và kiểm thử?
Một dịch vụ phân tích sự kiện cần chạy cùng một phép chuẩn hóa với tập dữ liệu nhỏ trong bộ nhớ và luồng dữ liệu lớn, nhưng logic đang gắn chặt với cấu trúc thu thập; hãy thiết kế trừu tượng hóa phù hợp cho phép biến đổi?
Một hệ thống tính thưởng theo thời gian cần tổng hợp kết quả qua nhiều quy tắc có thể bật tắt, nhưng cấu hình đang dùng các nhánh điều kiện lồng nhau; hãy tái tổ chức yêu cầu dưới dạng hợp thành các phép tính thuần?
Một dịch vụ lập lịch cần xác định các khung giờ trống từ danh sách khoảng thời gian đã đặt có thể giao nhau và không theo thứ tự; hãy thiết kế một phép fold có bất biến trạng thái tích lũy rõ ràng?
Một nền tảng phát hành điểm thưởng xử lý hàng nghìn sự kiện cộng trừ theo thứ tự, nhưng vòng lặp hiện cập nhật biến tổng dùng chung; hãy đánh giá phép reduce và điều kiện bảo toàn thứ tự?
Một ứng dụng phân tích cấu trúc tổ chức cần duyệt cây phòng ban sâu với nhiều nút và tạo thống kê theo cấp; hãy thiết kế phép đệ quy có trường hợp cơ sở và đánh giá nguy cơ tràn ngăn xếp?
Một bộ xử lý biểu thức số học đại diện đầu vào bằng cây với nhiều loại nút, đồng thời phải tính giá trị và dựng bản mô tả; hãy xác định cách tổ chức hai phép diễn giải mà vẫn giữ mô hình dữ liệu nhất quán?
Một chương trình phân tích nhật ký nhận danh sách lồng nhau nhiều cấp và phải làm phẳng trước khi tìm bất thường; hãy so sánh các cách đệ quy và fold theo độ sâu, bộ nhớ và tính dễ kiểm thử?
Một nhóm phát triển thay vòng lặp cộng dồn bằng reduce song song nhưng kết quả số thực khác nhau giữa các lần chạy; hãy phân tích điều kiện kết hợp của phép toán và yêu cầu tính xác định?
Một dịch vụ chuyển đổi đơn vị thực hiện nhiều phép làm tròn ở từng bước thay vì cuối pipeline, tạo sai khác khi đổi thứ tự hợp thành; hãy thiết kế kiểm thử cho sai số và tính chất đại số của các phép biến đổi?
Một nền tảng thương mại muốn gom các khoản giảm giá theo nhóm, nhưng phép tổng hợp hiện thay đổi hành vi khi chia dữ liệu thành các lô; hãy xác định phép gộp và phần tử trung hòa cần thỏa điều kiện nào?
Một hệ thống điều hướng tìm đường trên đồ thị có chu trình khiến hàm đệ quy gọi mãi không dừng; hãy thiết kế chiến lược theo dõi trạng thái đã duyệt và đánh giá giới hạn bộ nhớ?
Một ứng dụng danh bạ thực hiện đệ quy đuôi để lọc hàng triệu bản ghi nhưng chạy trên ngôn ngữ không bảo đảm tối ưu tail call; hãy đánh giá lựa chọn thay thế để tránh cạn stack?
Một công cụ nhập dữ liệu lớn tạo ra nhiều danh sách trung gian từ map và filter rồi vượt ngân sách bộ nhớ; hãy phân tích liệu có thể hợp nhất các bước biến đổi mà vẫn giữ ngữ nghĩa?
Một ứng dụng điều tra giao dịch dùng phép fold sinh bản ghi đối soát, nhưng lỗi ở bản ghi giữa chừng khiến khó tìm trạng thái trước lỗi; hãy thiết kế cấu trúc kết quả cho phép kiểm tra từng bước tích lũy?
Một dịch vụ tìm kiếm sản phẩm tải toàn bộ danh mục từ xa dù người dùng chỉ muốn 20 kết quả đầu; hãy đánh giá cách trì hoãn đánh giá và giới hạn số phần tử cần xử lý?
Một hệ thống đọc tệp lớn tạo chuỗi lazy từ các dòng, nhưng kết nối tệp bị đóng trước khi phần tử được sử dụng; hãy xác định ranh giới vòng đời tài nguyên và thời điểm đánh giá?
Một bảng điều khiển cập nhật từng giây dùng luồng giá trị lazy có nguồn dữ liệu liên tục, nhưng màn hình thỉnh thoảng giữ lại nhiều phần tử cũ; hãy phân tích cách tránh giữ tham chiếu không cần thiết?
Một nền tảng phân tích dữ liệu gọi map trên cấu trúc lazy rồi mong tác dụng ghi log xảy ra ngay, dẫn đến log xuất hiện muộn; hãy làm rõ hợp đồng thời điểm thực thi và cách bố trí tác dụng phụ?
Một dịch vụ lấy dữ liệu từ ba API tạo phép tính lazy nhưng yêu cầu chỉ gọi API thứ hai khi dữ liệu thứ nhất thiếu; hãy thiết kế thứ tự đánh giá để tránh lời gọi thừa?
Một ứng dụng tìm kiếm văn bản kết hợp nhiều predicate có chi phí rất khác nhau, khiến số lần đánh giá tăng mạnh khi bật lazy processing; hãy phân tích thứ tự lọc và tác động của short-circuit?
Một nền tảng gợi ý sử dụng generator vô hạn để tạo ứng viên nhưng chức năng gom tất cả phần tử không bao giờ hoàn thành; hãy xác định giới hạn tiêu thụ và tiêu chí kết thúc hợp lý?
Một hệ thống báo cáo áp dụng cache cho giá trị lazy được tính từ dữ liệu bên ngoài có thể thay đổi, khiến báo cáo hiển thị dữ liệu cũ; hãy phân tích chính sách làm mới và tính thuần của nguồn dữ liệu?
Một nhóm nghiên cứu tạo một luồng số Fibonacci lazy và chia sẻ cho nhiều consumer có tốc độ tiêu thụ khác nhau, dẫn đến chi phí tính toán và lưu trữ tăng; hãy đánh giá chiến lược chia sẻ kết quả?
Một dịch vụ kiểm tra điều kiện nghiệp vụ dùng phép AND với điều kiện thứ hai có thao tác mạng, nhưng lời gọi đôi khi không xảy ra; hãy phân tích short-circuit và yêu cầu tách tác dụng phụ?
Một pipeline đọc dữ liệu theo lô được viết lazy nhưng vẫn tiêu thụ RAM tăng tuyến tính do lưu mọi kết quả đã xử lý; hãy xác định cách quan sát và giới hạn dữ liệu được giữ sống?
Một chương trình phân tích telemetry kết hợp đánh giá lazy với xử lý song song, nhưng thứ tự xuất kết quả không ổn định; hãy xác định yêu cầu về thứ tự, độ trễ và sự nhất quán của pipeline?
Một API xử lý khách hàng trả về giá trị có thể thiếu và dùng null ở nhiều bước, gây lỗi chỉ xuất hiện sau khi triển khai; hãy thiết kế chuỗi xử lý dùng biểu diễn thiếu giá trị có kiểu rõ ràng?
Một dịch vụ đăng ký tài khoản có nhiều phép xác thực độc lập và cần hiển thị tất cả lỗi một lần, nhưng chuỗi xử lý hiện dừng ở lỗi đầu tiên; hãy chọn cơ chế hợp thành kiểm tra phù hợp với yêu cầu?
Một hệ thống đặt hàng cần chạy bước tính giá chỉ khi bước kiểm tra tồn kho thành công và giữ nguyên thông tin lỗi nếu thất bại; hãy mô hình hóa chuỗi xử lý dựa trên kết quả thành công hoặc thất bại?
Một dịch vụ chuyển tiền có ba bước phụ thuộc dữ liệu, mỗi bước có thể lỗi theo cách khác nhau; hãy thiết kế kiểu dữ liệu kết quả và phép nối các bước mà không làm mất ngữ cảnh lỗi?
Một ứng dụng xử lý hồ sơ sử dụng exception cho cả lỗi nhập liệu dự kiến và lỗi hạ tầng bất ngờ, làm các nhánh phục hồi khó phân biệt; hãy thiết kế ranh giới chuyển lỗi sang giá trị?
Một hệ thống đặt chỗ có nhiều biến thể trạng thái đơn hàng không hợp lệ xuất hiện do dùng cờ Boolean độc lập; hãy thiết kế mô hình trạng thái bằng các kiểu tổng và phép chuyển hợp lệ?
Một thư viện parse thời gian cần xử lý giá trị thiếu, sai cú pháp và không nằm trong khoảng cho phép, nhưng kiểu trả về hiện chỉ có null; hãy mô hình hóa trạng thái kết quả để caller phân biệt từng trường hợp?
Một hệ thống quản lý thiết bị sử dụng Result để biểu diễn lỗi, nhưng nội dung lỗi không có đủ thông tin vị trí và dữ liệu đầu vào; hãy xác định dữ liệu nên lưu trong nhánh lỗi và cách truyền qua pipeline?
Một bộ xử lý đơn hàng cần cộng dồn kết quả từ danh sách các phép tính có thể thất bại, nhưng đang bỏ qua các phần tử lỗi; hãy xác định chiến lược thu thập thành công và thất bại phù hợp hợp đồng nghiệp vụ?
Một dịch vụ cấp tín dụng muốn phân biệt lỗi có thể retry với lỗi vi phạm quy tắc, nhưng xử lý theo một kiểu lỗi chung; hãy thiết kế mô hình lỗi cho phép quyết định phục hồi mà không gắn logic vào thông báo văn bản?
Một nhóm phát triển hợp thành Future và Result nhưng có lúc nuốt mất ngoại lệ từ tác vụ bất đồng bộ, khiến quy trình báo thành công sai; hãy mô hình hóa các lớp hiệu ứng và quy tắc truyền thất bại?
Một ứng dụng đăng ký dịch vụ phải xác thực nhiều trường độc lập nhưng có bước gọi API chỉ chạy khi mọi kiểm tra hợp lệ; hãy xác định cách phối hợp kết quả kiểm tra và ranh giới I/O?
Một thư viện xử lý hộp dữ liệu có phép map nhưng làm biến đổi số phần tử hoặc thay đổi hình dạng cấu trúc sau khi ánh xạ; hãy thiết kế bài kiểm thử cho tính chất identity và composition của Functor?
Một cấu trúc dữ liệu tùy biến dùng để biểu diễn cây phân loại cần hỗ trợ áp dụng cùng một phép biến đổi cho mọi giá trị ở lá; hãy xác định hợp đồng map và cách giữ nguyên cấu trúc cây?
Một dịch vụ phân tích báo cáo muốn chuyển giá trị bên trong Option thành đơn vị mới mà vẫn giữ trạng thái không có dữ liệu; hãy phân biệt yêu cầu với việc tự lấy giá trị mặc định?
Một thư viện xử lý kết quả định nghĩa map cho nhánh thành công nhưng lại thay đổi nhánh lỗi khi hàm ánh xạ được gọi; hãy kiểm tra tính hợp lệ của phép ánh xạ theo luật Functor?
Một hệ thống xử lý hồ sơ gọi hàm trả về Option bên trong một Option khác khiến các nhánh điều khiển phức tạp; hãy lựa chọn cách hợp thành phép tính có ngữ cảnh mà không tích lũy nhiều lớp bao?
Một pipeline xác thực từng bước trả về Result và cần truyền lỗi đầu tiên xuống cuối chuỗi xử lý; hãy thiết kế phép flatMap và kiểm tra các luật cơ bản của Monad?
Một nhóm phát triển tạo kiểu hiệu ứng mới để mô tả tác vụ bất đồng bộ nhưng phép liên kết các bước phụ thuộc vào cách nhóm ngoặc, làm kết quả khác nhau; hãy xác định cách kiểm thử luật kết hợp của Monad?
Một thư viện xử lý dữ liệu định nghĩa phép pure/return cho một ngữ cảnh nhưng sau đó chạy thêm log và thay đổi trạng thái; hãy kiểm tra điều kiện để giữ luật đơn vị của Monad?
Một nền tảng tích hợp nhiều nguồn có các thao tác đọc cấu hình, ghi log và gọi mạng cùng bị trộn trong hàm nghiệp vụ; hãy thiết kế cách biểu diễn các hiệu ứng để kiểm thử phần logic độc lập?
Một hệ thống phân tích dùng danh sách các lựa chọn có thể thay thế, rồi kết hợp các bước sinh lựa chọn mới khiến số nghiệm tăng mạnh; hãy đánh giá ngữ nghĩa flatMap và giới hạn độ phức tạp?
Một dịch vụ xác thực cần kết hợp kết quả của các kiểm tra độc lập để thu thập lỗi, nhưng một lập trình viên dùng chuỗi monadic dừng sớm; hãy phân tích khác biệt ngữ nghĩa giữa kết hợp Applicative và Monad?
Một ứng dụng quản lý trạng thái bàn làm việc muốn mô tả nhiều phép cập nhật tuần tự mà vẫn có thể chạy lại từ trạng thái ban đầu; hãy mô hình hóa việc truyền trạng thái qua các phép biến đổi có kiểu rõ ràng?
Một đội kiểm thử cần giả lập truy cập cơ sở dữ liệu cho logic nghiệp vụ viết theo phong cách hàm, nhưng code hiện gọi trực tiếp thư viện lưu trữ; hãy thiết kế ranh giới phụ thuộc và phép diễn giải hiệu ứng?
Một dịch vụ tạo báo cáo phải duy trì log tính toán có thể tái hiện mà không thực sự ghi file trong từng bước; hãy đánh giá cách biểu diễn kết quả kèm nhật ký như dữ liệu và chi phí của nó?
Một pipeline tính chiết khấu cần tạo cấu hình chỉ đọc chung cho nhiều phép biến đổi, nhưng mỗi hàm đều nhận hàng chục tham số riêng; hãy đánh giá cách biểu diễn môi trường dùng chung mà vẫn giữ hàm thuần?
Một dịch vụ xử lý ảnh áp dụng chuỗi phép biến đổi thuần nhưng bản sao trung gian quá lớn khiến vượt bộ nhớ; hãy cân nhắc truyền dữ liệu bất biến với chiến lược tối ưu cấp phát và fusion?
Một ứng dụng xử lý triệu giao dịch dùng map rồi reduce song song nhưng phép gộp có thứ tự phụ thuộc vào dấu phẩy động, làm số liệu tổng lệch nhỏ; hãy xác định mức chấp nhận sai số và cách kiểm chứng?
Một hệ thống phân tán xử lý các lô sự kiện theo hàm thuần trên từng lô nhưng tái thực thi sau lỗi dẫn đến gửi thông báo trùng; hãy thiết kế ranh giới hiệu ứng và điều kiện idempotency?
Một ứng dụng giao dịch tài chính có các hàm thuần tính số dư nhưng nhiều luồng cùng cập nhật trạng thái tài khoản, gây mất bản cập nhật; hãy thiết kế phối hợp cập nhật trạng thái mà không mất tính nhất quán?
Một dịch vụ analytics sử dụng memoization cho phép tính báo cáo đắt đỏ nhưng khóa cache chứa cấu trúc mutable, khiến kết quả trả sai; hãy xác định điều kiện cache an toàn và chính sách vô hiệu?
Một chức năng tính cước viễn thông dùng đệ quy kết hợp memoization nhưng bảng memo tăng không giới hạn khi dữ liệu đầu vào thay đổi liên tục; hãy phân tích ngưỡng bộ nhớ và chiến lược quản lý vòng đời cache?
Một nền tảng thương mại dùng structural sharing cho trạng thái bất biến nhưng vô tình giữ chuỗi phiên bản lịch sử dài trong bộ nhớ; hãy kiểm tra retention và cân nhắc điểm cắt lịch sử?
Một nhóm thay lớp đối tượng mutable bằng cấu trúc giá trị bất biến trong luồng dữ liệu nóng, sau đó thời gian GC tăng mạnh; hãy thiết kế benchmark đo phân bổ, throughput và độ trễ trước khi quyết định giữ thay đổi?
Một ứng dụng theo dõi vận chuyển có nhiều cập nhật sự kiện chậm và không theo thứ tự, nhưng phép biến đổi trạng thái được chạy lại để phục hồi; hãy xác định các bất biến và điều kiện tái lập kết quả?
Một công cụ ETL sử dụng pipeline hàm trên tập dữ liệu lớn, nhưng mỗi bước tạo collection mới làm quá tải CPU và RAM; hãy so sánh fusion, lazy processing và truyền dữ liệu theo lô trong giới hạn yêu cầu?
Một hệ thống xếp lịch cần thực hiện tính toán song song trên các nhóm dữ liệu nhưng một số hàm nhận closure giữ kết nối không an toàn luồng; hãy xác định yếu tố ngăn thực thi song song an toàn?
Một hệ thống chọn sản phẩm dùng comparator dựa vào biến cấu hình mutable thay đổi giữa chừng, khiến kết quả sort không ổn định; hãy thiết kế đầu vào tường minh để bảo đảm phép so sánh có tính nhất quán?
Một ứng dụng kiểm kê có hàng trăm phép tính giá trị được cache nhưng quy tắc tính thay đổi theo phiên bản, làm kết quả cũ được dùng lại; hãy thiết kế khóa memoization và chiến lược xóa cache phù hợp?
Một nhóm phát triển chuyển bộ xử lý đơn hàng sang phong cách hàm nhưng phần lập trình mới có quá nhiều abstraction, khiến khó truy vết dữ liệu; hãy lựa chọn tiêu chí đánh đổi giữa độ rõ nghĩa và tính trừu tượng?
Một hệ thống thanh toán định kỳ đang dùng callback lồng nhau cùng biến trạng thái chia sẻ, khiến khó test lỗi ở bước cuối; hãy lên kế hoạch tách các phép biến đổi thuần khỏi orchestration và đánh giá thay đổi?
Một nền tảng tuyển dụng triển khai rule engine thuần để chấm điểm hồ sơ nhưng dữ liệu đến có thể thiếu trường, khiến nhiều bước thất bại không rõ nguyên nhân; hãy thiết kế kiểm thử property-based cho dữ liệu thiếu và bất biến?
Một dịch vụ đối soát ngân hàng có luật tổng tiền đầu ra phải bằng tổng tiền đầu vào sau phân loại, nhưng refactor fold làm mất vài giao dịch; hãy xây dựng bộ thuộc tính kiểm thử phát hiện dữ liệu bị mất hoặc tính hai lần?
Một công cụ chuyển đổi dữ liệu dùng hai hàm encode/decode mà kết quả không thể round-trip với ký tự Unicode và giá trị biên; hãy thiết kế các thuộc tính và dữ liệu kiểm thử cho hợp thành hai phép biến đổi?
Một hệ thống nhập hàng có phép chuẩn hóa địa chỉ cần idempotent nhưng áp dụng hai lần lại làm đổi nội dung, dẫn đến hash và cache sai; hãy xác định và kiểm thử tính chất cần có của phép chuẩn hóa?
Một ứng dụng quản lý đặt chỗ có chức năng hoàn tác, nhưng phép nghịch đảo chỉ hoạt động với một số trạng thái, khiến lịch sử không thể quay lại; hãy mô hình hóa giới hạn khả nghịch và cách xử lý trạng thái không có phép nghịch đảo?
Một dịch vụ xếp hạng nội dung áp dụng phép lọc và sắp xếp bằng các hàm thuần nhưng nhận dữ liệu không xác định thứ tự, làm kết quả khác nhau giữa môi trường; hãy xác định yêu cầu về thứ tự tổng và tính ổn định?
Một đội phát triển muốn đo độ tin cậy của việc thay loop truyền thống bằng map/filter/fold trong API có lưu lượng lớn; hãy thiết kế đánh giá gồm tính đúng, cấp phát bộ nhớ, độ trễ và khả năng bảo trì?
