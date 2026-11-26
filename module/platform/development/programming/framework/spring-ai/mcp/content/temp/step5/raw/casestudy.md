Một ứng dụng Spring Boot triển khai MCP Server cung cấp công cụ tra cứu đơn hàng, nhưng ChatClient không nhìn thấy công cụ dù endpoint của server vẫn phản hồi yêu cầu HTTP bình thường.
Đội phát triển đưa phương thức đặt lịch họp vào MCP Server, nhưng tên công cụ hiển thị cho client khác với tên mà mô hình đang được hướng dẫn sử dụng.
Một hệ thống logistics công bố công cụ tính phí vận chuyển với mô tả quá chung, khiến mô hình thường chọn nhầm công cụ tra cứu giá sản phẩm cho câu hỏi về cước giao hàng.
MCP Server cung cấp công cụ tìm khách hàng bằng email, nhưng schema đầu vào đánh dấu mã khách hàng là bắt buộc khiến những lời gọi hợp lệ bằng email bị từ chối.
Một nhóm tích hợp đổi kiểu tham số số lượng từ số nguyên sang chuỗi trong hợp đồng tool, khiến các MCP Client đang hoạt động gửi dữ liệu theo schema cũ và nhận lỗi xác thực.
Một công cụ tạo phiếu hỗ trợ nhận tham số mức ưu tiên không có giới hạn giá trị rõ ràng, khiến mô hình truyền nhãn không tồn tại trong quy trình chăm sóc khách hàng.
Đội sản phẩm bổ sung tham số tùy chọn vào công cụ tìm kiếm kho, nhưng ứng dụng cũ mặc định mọi tham số đều hiện diện nên lỗi phát sinh khi mô hình bỏ trống.
Một MCP Server khai báo hai công cụ có tên gần giống nhau để kiểm tra và xác nhận thanh toán, khiến mô hình chọn thao tác xác nhận khi khách chỉ hỏi trạng thái.
Một chatbot nội bộ tích hợp các công cụ đọc và sửa hồ sơ nhân viên, nhưng mô tả chức năng không phân biệt tác vụ chỉ đọc với tác vụ có tác dụng phụ.
Nền tảng quản lý tài sản công bố công cụ xóa tài liệu, nhưng người dùng chỉ cần tìm một tệp cũ và mô hình lại đề xuất gọi công cụ không thể hoàn tác.
Một dịch vụ nghiệp vụ trả kết quả công cụ dưới dạng văn bản tự do, nhưng ChatClient cần mã đơn và trạng thái có cấu trúc để tiếp tục xử lý quy trình.
MCP Server truyền danh sách nhiều nghìn sản phẩm trong một kết quả tool, khiến phần ngữ cảnh của cuộc hội thoại tăng đột biến và yêu cầu AI vượt giới hạn token.
Một hệ thống dự báo thời tiết trả đơn vị nhiệt độ khác với tài liệu mô tả của công cụ, khiến mô hình so sánh sai số đo giữa các thành phố.
Đội tích hợp thêm mô tả tiếng Anh cho tool vốn phục vụ khách Việt Nam, khiến mô hình chuyển cách giải thích kết quả sang thuật ngữ không phù hợp với giao diện.
Một MCP Server công bố công cụ truy vấn hóa đơn đã ngừng hỗ trợ từ lâu, nhưng client vẫn liệt kê và mô hình tiếp tục thử sử dụng mỗi khi khách hỏi dữ liệu cũ.
Ứng dụng trợ lý nhân sự cung cấp công cụ đọc bảng lương, nhưng tài khoản sử dụng ChatClient chỉ được phép xem thông tin hợp đồng và không được thấy dữ liệu thu nhập.
Một công cụ cập nhật hạn mức giao dịch được mô hình gọi hai lần sau khi mất phản hồi, khiến cùng một yêu cầu thay đổi hạn mức có nguy cơ được áp dụng lặp.
Hệ thống kho dùng MCP tool đặt giữ hàng trong một phiên hỏi đáp, nhưng người dùng đóng cuộc hội thoại trước khi hoàn tất và các vị trí hàng vẫn bị giữ.
Một công cụ gửi email đã trả kết quả thành công, nhưng kết nối MCP bị ngắt trước khi ChatClient nhận được phản hồi khiến ứng dụng không rõ có nên thực hiện lại.
Một nhóm triển khai công cụ tạo hợp đồng trên MCP Server và công cụ chỉ đọc thông tin hợp đồng trên server khác, nhưng mô hình lại gửi yêu cầu ghi vào endpoint chỉ phục vụ truy vấn.
Một MCP Client nhận kết quả tool gồm nhiều đoạn nội dung, nhưng bước tổng hợp chỉ sử dụng đoạn đầu nên câu trả lời bỏ sót cảnh báo về trạng thái đơn hàng.
Một công cụ phân loại tài liệu trả tín hiệu lỗi nghiệp vụ trong nội dung kết quả, nhưng ứng dụng coi đó là kết quả thành công và ghi nhãn sai vào cơ sở dữ liệu.
Dịch vụ tra cứu tồn kho trả một danh sách rỗng khi sản phẩm không tồn tại, nhưng chatbot giải thích thành lỗi kết nối vì không phân biệt kết quả rỗng với công cụ thất bại.
Một ứng dụng trợ lý bán hàng cho phép mô hình tự chọn số lần gọi tool, nhưng cùng câu hỏi đơn giản khiến nó lặp tra cứu giá nhiều lần và tăng độ trễ.
MCP Server hỗ trợ thao tác duyệt yêu cầu nghỉ phép, nhưng ChatClient không ghi nhận người đã phê duyệt và hồ sơ kiểm toán chỉ còn dấu vết gọi công cụ từ tài khoản kỹ thuật.
Một hệ thống tư vấn tài chính dùng kết quả tool tính lãi suất trong câu trả lời, nhưng thời điểm dữ liệu được cập nhật không được truyền rõ nên khách nhận con số đã hết hiệu lực.
Một công cụ đặt chỗ trả kết quả thành công trước khi giao dịch database hoàn tất, khiến mô hình xác nhận đã đặt chỗ dù tác vụ phía sau cuối cùng bị rollback.
Nhóm phát triển ghép nhiều công cụ tra cứu đơn, kiểm tra tồn và tạo vận đơn trong một hội thoại, nhưng bước cuối được gọi trước khi dữ liệu đơn ở bước đầu được xác thực.
Một ChatClient dùng tool để chuyển trạng thái đơn hàng, nhưng yêu cầu chứa mã đơn của khách khác và MCP Server chỉ kiểm tra token kết nối mà không kiểm tra quyền với bản ghi.
Ứng dụng tạo báo giá gọi tool tính chiết khấu, nhưng prompt từ người dùng chứa chỉ dẫn thay mức ưu đãi khiến mô hình truyền tham số trái chính sách doanh nghiệp.
MCP Client tích hợp cùng lúc hai server cung cấp công cụ tìm khách hàng trùng tên, khiến danh sách khả năng được gộp lại không đủ rõ để định tuyến đến server mong muốn.
Một server cung cấp phiên bản mới của công cụ tra cứu đơn, nhưng client vẫn giữ danh sách tool đã tải trước khi triển khai và không nhận ra schema vừa thay đổi.
Nền tảng trợ lý đặt lịch có hàng trăm tool từ nhiều MCP Server, nhưng mô hình được trình bày toàn bộ danh sách mỗi lượt hỏi khiến chi phí prompt tăng mạnh.
Ứng dụng dùng ChatClient cùng các tool cục bộ và tool từ MCP Client, nhưng một số tên bị trùng và đội phát triển khó xác định nguồn thực thi của lời gọi.
Một MCP Server thay tên tham số của tool mà không thay đổi hướng dẫn sử dụng, khiến mô hình tiếp tục sinh lời gọi chứa tên cũ và nhận lỗi kiểm tra đầu vào.
Một nhóm cho rằng việc tool có mặt trong danh sách là đủ để được gọi, nhưng ChatClient thực tế chưa được cấu hình sử dụng bộ công cụ MCP khi xử lý prompt.
MCP Server lưu công cụ chỉ có hiệu lực trong giờ làm việc, nhưng MCP Client tiếp tục hiển thị công cụ ngoài khung giờ và tạo nhiều lời gọi không còn được chấp nhận.
Một công cụ trích xuất thông tin hợp đồng được mô hình lựa chọn đúng, nhưng server yêu cầu tham số theo định dạng khác với schema công bố và thất bại với mọi lời gọi.
Ứng dụng gọi công cụ chỉnh sửa thông tin khách hàng từ nội dung cuộc trò chuyện, nhưng không có bước ghi lại giá trị trước và sau để kiểm tra các thay đổi gây tranh cãi.
Dịch vụ thanh toán dùng một công cụ chỉ mô phỏng phí nhưng kết quả tool không cho biết đây là dữ liệu thử nghiệm, khiến chatbot báo cho khách mức phí như đã được xác nhận.
Một MCP Server công bố resource chứa bảng quy định học phí, nhưng ChatClient được cấu hình chỉ sử dụng các tool và không có thành phần nào đọc tài nguyên theo URI.
Nền tảng học trực tuyến cung cấp resource theo URI của từng khóa học, nhưng client dùng sai định danh khóa học nên lấy nhầm đề cương của lớp khác.
Một ứng dụng trợ lý luật sư đọc resource văn bản hợp đồng, nhưng resource đã được cập nhật giữa hai lượt hỏi và câu trả lời mới không còn nhất quán với lượt trước.
MCP Server trả nội dung tài liệu bằng kiểu media không khớp thực tế, khiến phía nhận diễn giải một tệp nhị phân như văn bản và mất dữ liệu.
Một hệ thống quản lý kho công bố resource cho số lượng tồn, nhưng ứng dụng lưu cache mà không quan tâm đến phiên bản nên mô hình trả lời bằng mức tồn đã cũ.
Một dịch vụ nhân sự định nghĩa resource template nhận mã phòng ban, nhưng client không thay đúng biến trong URI khiến các lượt đọc tài nguyên đều thất bại.
Ứng dụng hỗ trợ kỹ thuật đọc nhiều resource nhật ký lỗi có kích thước lớn, nhưng đưa toàn bộ nội dung vào prompt làm vượt giới hạn ngữ cảnh của model.
Một MCP Server chỉ cho phép nhân viên phòng kế toán đọc resource báo cáo doanh thu, nhưng người dùng phòng khác đoán URI rồi yêu cầu client tải cùng tài liệu.
Một bảng hướng dẫn nội bộ được công bố dưới dạng MCP resource, nhưng nội dung có chỉ dẫn giả làm system prompt khiến mô hình bỏ qua mục tiêu hỏi đáp ban đầu.
MCP Client nhận resource đã thay đổi nhưng không có thông tin thời điểm hiệu lực, khiến câu trả lời về quy trình được trình bày như chính sách mới nhất dù tài liệu đã cũ.
Ứng dụng đọc resource theo URI do người dùng nhập trực tiếp, nhưng không kiểm tra phạm vi được phép nên có thể truy cập những tài nguyên nội bộ ngoài mục đích hỗ trợ.
Một server quản lý tài liệu có nhiều phiên bản resource cùng tên hiển thị, khiến nhân viên khó phân biệt bản dự thảo và bản đã được phê duyệt khi hỏi trợ lý.
Nền tảng chăm sóc khách hàng cung cấp resource hình ảnh minh họa sản phẩm, nhưng client chỉ xử lý dữ liệu văn bản nên mô hình không nhận được nội dung ảnh.
Một chatbot được yêu cầu giải thích bảng giá lưu trong resource, nhưng tệp trả về dùng mã ký tự không phù hợp và tên sản phẩm có dấu bị biến dạng.
Hệ thống vận hành phát cập nhật resource theo thời gian thực, nhưng một client sau khi mất mạng tiếp tục trả nội dung cũ mà không biết tài liệu đã thay đổi.
MCP Server có tài nguyên hướng dẫn xử lý sự cố nhưng liên kết đến tài liệu bên ngoài cần xác thực riêng, khiến một phần nội dung không thể được client truy cập.
Ứng dụng tuyển dụng công bố resource hồ sơ ứng viên để AI phân tích, nhưng dữ liệu chứa thông tin cá nhân nhiều hơn những gì mô hình cần cho tác vụ lọc hồ sơ.
Nhóm xây dựng MCP Server bổ sung resource mới mà không thông báo cập nhật danh mục, khiến client kết nối từ trước không đưa tài liệu mới vào kết quả khám phá.
Một chatbot nội bộ sử dụng prompt mẫu từ MCP Server để trả lời khiếu nại, nhưng các biến đầu vào của mẫu không khớp trường thông tin mà ứng dụng đang có.
MCP Server cung cấp prompt chuẩn cho tư vấn khách hàng, nhưng một bộ phận thay nội dung mẫu mà không quản lý phiên bản khiến cùng yêu cầu được xử lý bằng hai quy tắc khác nhau.
Một MCP Client tải prompt dùng để tóm tắt cuộc họp, nhưng ứng dụng bỏ qua phần ngữ cảnh vai trò message nên mô hình không làm đúng nhiệm vụ dự kiến.
Đội chăm sóc khách hàng công bố hai prompt cùng tên trên hai server khác nhau, khiến client chọn mẫu xử lý hoàn tiền khi đang cần mẫu trao đổi bảo hành.
Một mẫu prompt dùng biến mã ngôn ngữ, nhưng client truyền tên ngôn ngữ tự do khiến nội dung trả lời không thống nhất giữa các cuộc hội thoại.
Nền tảng giáo dục đưa các ví dụ hướng dẫn chấm bài vào prompt MCP, nhưng một đợt sửa mẫu làm trường tiêu chí bắt buộc bị bỏ khỏi phản hồi của mô hình.
Ứng dụng lấy prompt từ một server đối tác không đáng tin cậy, nhưng coi mọi chỉ dẫn trong mẫu là chính sách nội bộ và cho phép mô hình gọi tool có quyền nhạy cảm.
Dịch vụ tư vấn sản phẩm dùng prompt MCP chứa biến ngân sách, nhưng người dùng nhập chuỗi mang chỉ dẫn vượt phạm vi giá và mô hình không còn giữ tiêu chí chọn hàng.
MCP Client hiển thị danh sách prompt nhưng không tải được nội dung của một mẫu do thiếu đối số bắt buộc, khiến người dùng chỉ thấy lỗi chung khi bắt đầu hỏi đáp.
Một MCP Server thay đổi tên prompt mà không giữ khả năng tương thích với client đã triển khai, khiến trợ lý doanh nghiệp không tìm thấy mẫu làm việc đã cấu hình sẵn.
Ứng dụng khởi tạo phiên trợ lý bằng prompt mẫu, nhưng sau khi người dùng chọn ngôn ngữ khác client vẫn giữ bản prompt đã tải ở lượt trước.
Một server cung cấp prompt hướng dẫn vận hành máy móc, nhưng nội dung mẫu bao gồm ví dụ lỗi thời khiến câu trả lời không phù hợp với phiên bản thiết bị hiện hành.
Nền tảng hỗ trợ kỹ thuật muốn kiểm toán prompt MCP đã sử dụng, nhưng chỉ lưu câu trả lời cuối mà không lưu tên và phiên bản mẫu từ server.
Một ứng dụng dịch vụ công dùng prompt tạo từ dữ liệu cấu hình của nhiều chi nhánh, nhưng nhầm biến tên đơn vị khiến công văn xuất ra ghi sai cơ quan ban hành.
Một MCP Client kết nối qua stdio tới một tiến trình server cục bộ, nhưng đường dẫn chương trình trên máy triển khai không tồn tại khiến quá trình khởi tạo thất bại.
Ứng dụng Spring Boot chạy MCP Server qua stdio, nhưng thư viện ghi log ra standard output làm trộn thông báo vận hành vào luồng giao thức và client không đọc được phản hồi.
Một công cụ chạy dưới MCP Server dùng stdio cần thư mục làm việc tương đối để tìm cấu hình, nhưng môi trường chạy production khác máy phát triển khiến công cụ thiếu tệp cần thiết.
Nền tảng phân tích có MCP Server chạy cục bộ bằng stdio, nhưng nhiều phiên ứng dụng mở tiến trình độc lập và làm số kết nối database vượt giới hạn cho phép.
Một MCP Client kết nối tới server từ xa bằng HTTP, nhưng đội triển khai lại cấu hình tham số khởi chạy tiến trình stdio nên không thiết lập được phiên giao tiếp.
Nhóm chuyển MCP Server từ môi trường phát triển stdio sang Streamable HTTP, nhưng đường dẫn endpoint trên client vẫn trỏ tới địa chỉ cũ và không có phản hồi khởi tạo.
Một gateway HTTP tự đệm dữ liệu khi chuyển tiếp luồng MCP từ server, khiến các cập nhật tiến độ và thông báo phát theo thời gian thực đến client chậm.
Một tổ chức còn sử dụng MCP Server triển khai transport SSE kiểu cũ, nhưng client mới chỉ được cấu hình cho Streamable HTTP nên hai phía không thiết lập được giao tiếp.
Ứng dụng giao tiếp với MCP Server qua mạng di động, nhưng proxy đóng kết nối kéo dài giữa chừng và client coi yêu cầu tool còn thực thi là thất bại hoàn toàn.
Một hệ thống đặt MCP Server sau load balancer không duy trì thông tin phiên thống nhất, khiến yêu cầu tiếp theo đến node khác không tìm thấy trạng thái đã khởi tạo.
Nhà phát triển cấu hình Streamable HTTP trên đường dẫn công khai không có TLS, khiến tham số truy vấn và dữ liệu tool có thể bị quan sát trên đường truyền.
Một MCP Client sử dụng server tại mạng riêng, nhưng chính sách firewall chỉ cho phép kết nối outbound tới các host được duyệt nên quá trình khám phá không thể bắt đầu.
MCP Server được khởi động trong container không có quyền mở kết nối mạng ra ngoài, khiến các tool lấy dữ liệu từ nhà cung cấp bên thứ ba luôn thất bại dù protocol vẫn hoạt động.
Một ứng dụng chuyển server sang vùng hạ tầng khác, nhưng URL endpoint được lưu cố định trong cấu hình ChatClient khiến những lần triển khai mới vẫn gọi tới server cũ.
Một MCP Client chờ server phản hồi khởi tạo quá lâu mà không có giới hạn thời gian, khiến luồng tiếp nhận câu hỏi của người dùng bị treo khi server không sẵn sàng.
Hai thành phần MCP dùng các phiên bản protocol khác nhau, khiến quá trình thương lượng khả năng không tương thích và không thể thực hiện lời gọi tool sau kết nối.
Một MCP Server công bố hỗ trợ danh sách tool nhưng phía xử lý lại chưa triển khai thao tác liệt kê, khiến client báo lỗi ngay khi khám phá chức năng.
Ứng dụng tải danh sách tool từ MCP Server trước khi mô hình trả lời, nhưng server yêu cầu xác thực mới trong lần gọi tiếp theo khiến tool từng hiển thị trở nên không dùng được.
Một dịch vụ thay đổi tập công cụ theo quyền của người dùng, nhưng MCP Client dùng danh sách khả năng đã cache từ tài khoản có quyền cao hơn cho phiên tài khoản khác.
MCP Server gửi thông báo thay đổi danh mục resource, nhưng client không có thành phần xử lý thông báo nên câu hỏi tiếp theo vẫn dùng tài nguyên không còn tồn tại.
Một máy chủ công bố khả năng mà client không hỗ trợ, khiến hai nhóm triển khai hiểu nhầm rằng mọi loại prompt và resource đều được ứng dụng sử dụng tự động.
Một ứng dụng tạo nhiều phiên MCP Client cho các yêu cầu ngắn, nhưng không đóng các kết nối sau khi hoàn tất nên tài nguyên server tăng không ngừng.
Trong đợt nâng cấp cuốn chiếu, MCP Client đang gọi tool thì server khởi động lại và mất trạng thái phiên, khiến người dùng không biết lệnh tạo hồ sơ đã thực sự hoàn tất chưa.
Một ChatClient dùng chung MCP Client giữa nhiều request đồng thời, nhưng một thành phần lưu trạng thái người dùng ngoài phạm vi phiên khiến dữ liệu yêu cầu bị gắn nhầm.
MCP Server phát nhiều sự kiện tiến độ khi chạy tác vụ tạo báo cáo dài, nhưng giao diện người dùng chỉ nhận kết quả cuối và hiển thị như hệ thống không phản hồi.
Một công cụ truy vấn dữ liệu được client gọi với tham số hợp lệ, nhưng phiên MCP đã hết hiệu lực nên kết quả trả về là lỗi protocol thay vì lỗi nghiệp vụ.
Nhóm vận hành không đo thời gian khởi tạo phiên MCP, khiến đợt tăng độ trễ bắt nguồn từ kết nối lại bị quy nhầm cho thời gian suy luận của model.
Một ứng dụng có nhiều MCP Server cùng được khai báo trong cấu hình, nhưng một server không khởi động khiến toàn bộ quy trình kết nối tool của chatbot bị chậm.
Doanh nghiệp cho phép nhân viên chỉ xem dữ liệu khách hàng qua MCP, nhưng tool cập nhật vẫn xuất hiện và có thể được gọi bằng token chia sẻ của ứng dụng.
MCP Server xác thực tài khoản kỹ thuật chung của mọi người dùng, nhưng không nhận danh tính người đặt câu hỏi nên không thể phân quyền từng lần gọi công cụ.
Một người dùng có quyền xem đơn hàng của chi nhánh A nhưng thay mã chi nhánh trong tham số tool thành B và nhận được dữ liệu không thuộc phạm vi được phép.
Một công cụ tìm file cho phép truyền đường dẫn trực tiếp, nhưng người dùng nhập đường dẫn vượt thư mục tài liệu được duyệt và server vẫn đọc nội dung nhạy cảm.
Ứng dụng tiếp nhận resource URI từ phản hồi của mô hình, nhưng server không giới hạn nơi có thể truy cập khiến yêu cầu có thể hướng đến dịch vụ nội bộ không liên quan.
Một MCP Server cho phép gọi lệnh truy vấn dữ liệu bằng tham số tự do, nhưng không xác thực đầu vào khiến người dùng lợi dụng để đọc thêm bảng ngoài phạm vi yêu cầu.
Dịch vụ tài chính giao cho mô hình tool duyệt thanh toán, nhưng người dùng chỉ định số tiền lớn mà không có bước xác nhận từ người có thẩm quyền.
Một ứng dụng hỗ trợ nhân sự đưa access token vào đối số tool để tiện gọi API khác, khiến token có thể xuất hiện trong nội dung yêu cầu và bản ghi vận hành.
MCP Server chạy với quyền hệ điều hành quá cao để đọc tài liệu, khiến sự cố ở tool xử lý tệp có thể ảnh hưởng đến các thư mục ứng dụng không liên quan.
Một chatbot nhận kết quả tra cứu website qua tool rồi tin các chỉ dẫn chèn trong nội dung trang, khiến câu trả lời bị điều hướng sang yêu cầu tiết lộ dữ liệu mật.
MCP Server từ bên thứ ba khai báo tool tên giống công cụ nội bộ đã được tin cậy, khiến model chọn nhầm nguồn khi xử lý dữ liệu khách hàng nhạy cảm.
Một nhân viên đổi vai trò từ quản trị sang hỗ trợ nhưng phiên MCP vẫn dùng quyền trước đó, khiến những yêu cầu mới có thể truy cập chức năng không còn được cấp phép.
Một dịch vụ gọi tool gửi thông báo theo danh sách khách hàng, nhưng tham số do mô hình tự sinh chứa địa chỉ bên ngoài doanh nghiệp và server vẫn thực hiện gửi.
Ứng dụng đưa toàn bộ kết quả tool đọc hồ sơ nhân viên vào Prompt, nhưng mô hình chỉ cần tên bộ phận nên dữ liệu cá nhân không cần thiết bị chuyển đến provider AI.
Một MCP Server ghi log đầy đủ payload của mọi lời gọi, khiến mã bảo mật và thông tin hợp đồng nhạy cảm xuất hiện trong hệ thống quan sát dùng chung.
Doanh nghiệp triển khai MCP Server truy cập báo cáo kế toán nhưng không phân tách tenant, khiến khách hàng này có thể nhận kết quả tổng hợp của khách hàng khác.
Một công cụ sửa hồ sơ người dùng trả lỗi quyền truy cập chung chung, nhưng phía ChatClient diễn giải thành lỗi dữ liệu và tự thử lại cùng thao tác nhiều lần.
Một ứng dụng công khai danh mục tool cho mọi người đăng nhập, nhưng mô tả của một công cụ chứa tên hệ thống nội bộ và thông tin cấu hình không được phép tiết lộ.
MCP Client dùng một server không thuộc danh sách được phê duyệt trong môi trường thử nghiệm, nhưng sau deploy URL này vẫn còn trong cấu hình production và có quyền gọi tool.
Ứng dụng cho phép tool nội bộ truy cập URL do người dùng cung cấp, nhưng endpoint trỏ tới địa chỉ mạng riêng và server thực thi request ngoài mục đích nghiệp vụ.
Một hệ thống cấp quyền sử dụng công cụ theo tên tool, nhưng server vừa thay đổi ý nghĩa một công cụ mà không xét lại chính sách và người dùng nhận được quyền mạnh hơn trước.
Một MCP Server gửi phản hồi lỗi tool dưới dạng thông báo văn bản, nhưng ChatClient coi chuỗi này là dữ liệu thành công và tiếp tục thực hiện bước cập nhật kế tiếp.
Một công cụ kiểm tra tồn kho bị timeout trong lúc database đang khóa bản ghi, khiến phía mô hình đưa ra thông báo hết hàng dù thao tác chưa trả kết quả xác định.
MCP Client thực hiện retry toàn bộ lời gọi khi kết nối rớt, nhưng tool tạo phiếu giao hàng có thể đã ghi dữ liệu trước đó nên phát sinh bản ghi trùng.
Một công cụ nhận JSON tham số chứa mã khách hàng là số, nhưng mô hình gửi mã dưới dạng chuỗi có số 0 đầu và bước chuyển kiểu làm mất định danh gốc.
Nhóm tích hợp đổi quy tắc kiểm tra schema đầu vào của tool, khiến client cũ vẫn liệt kê được công cụ nhưng chỉ thất bại khi thực sự thực thi.
MCP Server đọc tài liệu lớn mất nhiều thời gian, nhưng ứng dụng chỉ có một timeout chung khiến các truy vấn đơn giản cũng phải chờ hết thời gian của tác vụ dài.
Một tool kiểm tra trạng thái hợp đồng trả thông báo lỗi kỹ thuật khi nhà cung cấp tạm ngừng, nhưng chatbot trình bày lỗi đó như bằng chứng hợp đồng của khách bị hủy.
Ứng dụng điều phối gọi nhiều tool liên tiếp rồi bị lỗi ở bước cuối, nhưng không lưu trạng thái các bước trước nên người dùng khó xác định thao tác nào cần kiểm tra lại.
MCP Server trả một kết quả resource sai MIME type, nhưng lớp xử lý phía client chỉ báo lỗi giải mã chung khiến đội vận hành không biết lỗi đến từ hợp đồng media.
Một tool phát sinh dữ liệu lớn khiến thời gian model đọc kết quả kéo dài, nhưng không có giới hạn kích thước đầu ra và chi phí token tăng ngoài dự toán.
Một MCP Server đặt giới hạn số lời gọi mỗi phút, nhưng nhiều chatbot cùng chia sẻ một client và dồn tải khiến các yêu cầu hợp lệ nhận lỗi rate limit.
Ứng dụng hỏi đáp bật retry khi server trả lỗi xác thực, khiến cùng thông tin đăng nhập hết hạn được gửi lặp lại mà không khôi phục khả năng truy cập.
Một công cụ cập nhật bảng giá bị ngắt kết nối trước khi phản hồi, khiến nhóm hỗ trợ không thể phân biệt thất bại do mạng với giao dịch database chưa hoàn thành.
MCP Client sử dụng tool từ server ngoài có độ trễ thất thường, khiến timeout ở phía ChatClient kết thúc hội thoại khi tool vẫn đang thực hiện công việc nền.
Một hệ thống ghi nhận thành công việc gọi tool dù kết quả chỉ là thông báo yêu cầu đang chờ duyệt, khiến giao diện thể hiện giao dịch đã hoàn tất.
Trong đợt chuyển transport MCP, một số client vẫn dùng đường kết nối cũ nên cùng tool đôi khi thành công đôi khi thất bại tùy phiên bản ứng dụng.
Ứng dụng chỉ kiểm thử gọi tool đơn giản với dữ liệu hợp lệ, nhưng ở production mô hình truyền object lồng nhau và trường còn thiếu làm bước kiểm tra schema thất bại.
Nhóm QA dùng mock MCP Server luôn trả kết quả ngay lập tức, khiến bài kiểm thử không phát hiện timeout và hủy request khi một tool chạy lâu.
Một bộ test tích hợp khởi chạy MCP Server stdio nhưng không quản lý vòng đời tiến trình, khiến sau nhiều lần chạy CI tồn tại các server cũ giữ kết nối và tài nguyên.
Ứng dụng kiểm thử MCP Client với danh sách tool cố định, nhưng không phát hiện trường hợp server thay đổi danh mục sau khi client đã khởi tạo.
Một bài test xác minh lời gọi tool hoàn tất nhưng không kiểm tra giá trị tham số thực tế, khiến mô hình dùng nhầm mã khách hàng vẫn được đánh giá thành công.
Đội phát triển kiểm thử một server chỉ có resource văn bản, nhưng bỏ sót resource ảnh và dữ liệu nhị phân nên client không xử lý được nội dung đa phương thức.
Một bộ test nhận kết quả công cụ dưới dạng một đoạn văn bản, nhưng môi trường thật trả nhiều phần content khiến một số trường bị bỏ qua khi tổng hợp.
Một bài kiểm thử tool tạo đơn hàng gọi lại cùng yêu cầu hai lần, nhưng không có bước đối chiếu số đơn được ghi nên lỗi lặp giao dịch không được phát hiện.
Nhóm QA kiểm thử quyền truy cập với tài khoản quản trị, nhưng không kiểm tra trường hợp người dùng thường đoán URI resource thuộc phòng ban khác.
MCP Server chạy ổn trong test stdio, nhưng khi chuyển sang HTTP có reverse proxy thực tế client gặp lỗi khởi tạo phiên không được bộ kiểm thử mô phỏng.
Đội vận hành chỉ giám sát tình trạng kết nối MCP mà không đo tỷ lệ lỗi tool, khiến chatbot được báo khỏe dù mọi lần gọi hệ thống đơn hàng đều thất bại.
Một ứng dụng ghi thời gian trả lời của ChatClient nhưng không tách thời gian mô hình suy luận với thời gian thực thi tool, khiến nhóm kỹ thuật không tìm được nguồn gây chậm.
Nền tảng có nhiều MCP Server nhưng log không ghi tên server và tool đã được chọn, khiến một lỗi cập nhật dữ liệu khó truy vết đến điểm thực thi.
Một dịch vụ kiểm toán lưu kết quả gọi công cụ mà không lưu mã tương quan từ request người dùng, khiến đội hỗ trợ không nối được thao tác AI với lịch sử giao dịch.
MCP Client gặp lỗi ngắt kết nối tạm thời nhưng dashboard chỉ đếm HTTP status của API chính, khiến lỗi bên trong chuỗi tool không xuất hiện trong báo cáo.
Ứng dụng đánh giá chất lượng chatbot bằng câu trả lời cuối, nhưng không kiểm tra các tool đã được gọi nên một câu trả lời đúng tình cờ che giấu thao tác sửa dữ liệu ngoài ý muốn.
Một dịch vụ kiểm thử quyền truy cập dùng cùng tài khoản kỹ thuật cho mọi người dùng giả lập, khiến lỗi rò rỉ dữ liệu giữa tenant không được phát hiện trong test.
Nền tảng trợ lý nội bộ thay đổi mô tả công cụ trên MCP Server nhưng không chạy bộ kiểm thử hành vi, khiến mô hình bắt đầu chọn công cụ khác cho cùng loại câu hỏi.
Một hệ thống báo cáo ghi số lượt gọi MCP tool nhưng không đo kích thước kết quả, khiến đợt tăng chi phí token do tài liệu lớn không được nhận diện.
Ứng dụng xử lý lỗi tool bằng một thông báo chung, nhưng không ghi loại lỗi protocol, lỗi quyền hay lỗi nghiệp vụ nên đội trực không biết lớp nào cần khắc phục.
Nhóm triển khai cập nhật MCP Server trong thời gian người dùng đang chat, nhưng không có bài kiểm thử với session đang mở nên lỗi tương thích chỉ xuất hiện sau phát hành.
Một hệ thống dùng ChatClient với nhiều MCP Server đồng thời, nhưng kiểm thử chỉ chạy riêng từng server nên không phát hiện trường hợp trùng tên tool làm chọn nhầm đích.
Ứng dụng đồng bộ dữ liệu qua MCP tool trong giờ cao điểm, nhưng chỉ có chỉ số request thành công mà không đo số thao tác bị retry và nguy cơ ghi trùng.
