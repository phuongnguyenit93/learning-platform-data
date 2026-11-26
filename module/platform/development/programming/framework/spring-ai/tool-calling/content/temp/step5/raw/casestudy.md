Một ứng dụng Spring Boot khai báo phương thức tra cứu đơn hàng bằng @Tool, nhưng ChatClient không nhận được công cụ vì thành phần cấu hình lời gọi chỉ đăng ký một tập công cụ khác.
Đội phát triển thêm @Tool vào phương thức tính phí giao hàng, nhưng mô hình vẫn trả lời bằng cách ước lượng do mô tả công cụ quá chung để phân biệt với phép tính thủ công.
Một trợ lý bảo hiểm công bố hai phương thức @Tool có tên và chức năng gần giống, khiến mô hình chọn công cụ hủy hợp đồng trong khi khách chỉ yêu cầu xem trạng thái.
Hệ thống kho sử dụng tên phương thức Java rất kỹ thuật làm tên công cụ hiển thị, khiến mô hình thường bỏ qua thao tác kiểm tra tồn cần thiết trước khi trả lời.
Một nhóm thay đổi tên công cụ @Tool sau khi chatbot đã triển khai, nhưng prompt nghiệp vụ vẫn nhắc tên cũ làm tỷ lệ gọi công cụ hợp lệ giảm rõ rệt.
Nền tảng học trực tuyến đưa phương thức kiểm tra tiến độ học tập vào danh sách tool, nhưng mô tả thiếu điều kiện sử dụng nên mô hình gọi cả khi học viên chỉ hỏi thông tin chung.
Dịch vụ kế toán khai báo @Tool cho thao tác tổng hợp hóa đơn, nhưng phương thức phụ thuộc vào trạng thái request trên ThreadLocal và không tìm thấy dữ liệu khi thực thi ở luồng khác.
Một nhóm công bố phương thức @Tool trả đối tượng có quan hệ tham chiếu vòng, khiến bước chuyển kết quả thực thi thành nội dung đưa lại cho mô hình gặp lỗi.
Ứng dụng chăm sóc khách hàng đưa một công cụ chỉ đọc và một công cụ ghi dữ liệu vào cùng tập tool, nhưng không thể phân biệt vì mô tả đều nói là cập nhật thông tin khách hàng.
Hệ thống hỗ trợ nhân viên đăng ký hàng chục @Tool từ các module nghiệp vụ, nhưng một phương thức debug nội bộ cũng vô tình được công bố cho mô hình.
Đội sản phẩm đổi mô tả công cụ tạo phiếu hỗ trợ để tăng tỷ lệ lựa chọn, nhưng mô hình bắt đầu gọi công cụ ngay cả với câu hỏi chưa đủ dữ liệu tạo phiếu.
Một ứng dụng dùng tên công cụ có ký tự không phù hợp với ràng buộc của provider, khiến việc gửi danh sách tool lên mô hình bị từ chối trước khi hội thoại bắt đầu.
Trợ lý tài chính hiển thị công cụ tính lãi suất với mô tả không nói rõ đơn vị phần trăm, khiến mô hình truyền tham số lãi suất theo hai cách diễn giải khác nhau.
Một phương thức @Tool dùng để kiểm tra số dư chỉ nhận mã tài khoản, nhưng ứng dụng lại nhúng toàn bộ thông tin đăng nhập vào phần mô tả công cụ cho mô hình.
Một doanh nghiệp chuyển các công cụ từ lớp dịch vụ sang lớp adapter, nhưng sau khi thay bean Spring một số lời gọi @Tool vẫn phụ thuộc vào bản triển khai cũ.
ChatClient được cấu hình công cụ tra cứu khách hàng mặc định, nhưng yêu cầu của bộ phận nhân sự cần tập công cụ hạn chế hơn mà vẫn nhìn thấy công cụ bán hàng.
Một chatbot nội bộ sử dụng danh sách tool cố định cho mọi nhóm người dùng, khiến ứng dụng hiển thị khả năng sửa dữ liệu cho tài khoản chỉ có quyền xem.
Nền tảng du lịch chỉ đăng ký công cụ tra cứu chuyến bay ở một nhánh ChatClient, khiến các yêu cầu từ giao diện khác luôn nhận câu trả lời không dựa trên dữ liệu thực.
Một dịch vụ dùng công cụ địa chỉ theo quốc gia, nhưng ChatClient đăng ký đồng thời các phiên bản dành cho nhiều thị trường khiến mô hình chọn sai bộ quy tắc địa phương.
Nhóm phát triển tạo tập ToolCallback động dựa vào gói dịch vụ khách mua, nhưng bộ nhớ đệm danh sách công cụ làm người dùng vừa hạ gói vẫn thấy chức năng cao cấp.
Một công cụ đặt lịch hẹn có tham số ngày bắt buộc trong schema đầu vào, nhưng mô hình gửi ngày theo cách diễn đạt tự nhiên nên bước chuyển kiểu thất bại.
Dịch vụ tìm sản phẩm đánh dấu bộ lọc màu sắc là bắt buộc dù người dùng chỉ muốn xem tất cả hàng còn bán, khiến nhiều lời gọi tool không vượt qua xác thực đầu vào.
Một hệ thống đăng ký công cụ lấy số lượng tồn bằng kiểu số nguyên, nhưng mô hình truyền chuỗi có đơn vị khiến phương thức không thể nhận tham số hợp lệ.
Ứng dụng quản lý kho dùng mã SKU có số 0 đầu, nhưng schema của tool khai báo kiểu số làm mã hàng mất định danh khi chuyển từ tham số mô hình.
Một công cụ đặt vé nhận thời gian khởi hành không kèm múi giờ, khiến lịch được ghi lệch khi ứng dụng phục vụ khách ở nhiều quốc gia.
Dịch vụ tính giá vận chuyển có tham số khối lượng, nhưng tài liệu tool không ghi đơn vị nên mô hình có lúc gửi gram thay cho kilogram.
Một công cụ tạo hóa đơn dùng kiểu số thực để nhận số tiền, khiến đối soát tiền tệ có sai lệch nhỏ sau nhiều thao tác làm tròn.
Hệ thống bảo hiểm yêu cầu trường loại hợp đồng nằm trong tập giá trị cố định, nhưng mô hình gửi nhãn mới không được khai báo trong enum nghiệp vụ.
Một công cụ cập nhật địa chỉ nhận đối tượng lồng nhau có trường quận bắt buộc, nhưng người dùng cung cấp địa chỉ ngoài Việt Nam nên schema từ chối yêu cầu.
Nhóm phát triển thêm trường tùy chọn vào Java record làm đối số công cụ, nhưng phiên bản cũ của bộ kiểm tra đầu vào vẫn yêu cầu trường này ở mọi lần gọi.
Một phương thức @Tool có danh sách sản phẩm trong tham số, nhưng mô hình trả một đối tượng đơn lẻ khi khách chỉ đặt một mặt hàng và việc ánh xạ bị lỗi.
Dịch vụ tìm kiếm nhân viên khai báo tham số tên với chú thích sơ sài, khiến mô hình dùng họ tên đầy đủ trong trường vốn chỉ dành cho mã nhân viên.
Ứng dụng dùng @ToolParam để mô tả tham số ngày giao hàng, nhưng mô tả và quy tắc xác thực phía server trái ngược nhau nên lời gọi do mô hình tạo thường không hợp lệ.
Một công cụ cần phân biệt trường không được cung cấp với giá trị rỗng, nhưng bộ chuyển tham số gom cả hai trường hợp khiến thao tác cập nhật có thể xóa nhầm dữ liệu.
Hệ thống cấp voucher dùng mã chiến dịch dạng chuỗi, nhưng một tầng ánh xạ tự loại khoảng trắng và đổi chữ hoa khiến mã khuyến mãi được kiểm tra không đúng.
Một công cụ tra cứu hợp đồng có đối số mã khách hàng và mã hợp đồng, nhưng mô hình đảo hai giá trị vì cả hai cùng là chuỗi mà schema thiếu mô tả phân biệt.
Nền tảng tuyển dụng gửi nhiều tiêu chí lọc vào tool tìm ứng viên, nhưng một trường kiểu danh sách bị nhận như chuỗi khiến kết quả tìm kiếm thiếu ứng viên phù hợp.
Ứng dụng phân loại phản ánh để mô hình sinh tham số mức nghiêm trọng, nhưng không kiểm tra miền giá trị nên tool nhận số nằm ngoài thang nghiệp vụ.
Một công cụ nhận dữ liệu phần trăm chiết khấu nhưng không nói rõ giới hạn tối đa, khiến mô hình truyền mức ưu đãi cao hơn chính sách mà dịch vụ đang áp dụng.
Đội triển khai đổi tên trường trong đối tượng tham số của ToolCallback, nhưng schema mô hình sử dụng còn tên cũ khiến lời gọi không ánh xạ được.
Một ứng dụng tạo ToolCallback cho tra cứu thời tiết theo thành phố, nhưng callback trả chuỗi lỗi như dữ liệu thời tiết bình thường khiến mô hình khẳng định thông tin không có thật.
Hệ thống tích hợp dịch vụ kho bằng ToolCallback, nhưng công cụ trả danh sách hàng quá lớn làm phần ngữ cảnh gửi lại mô hình vượt giới hạn token.
Một nhóm gói API của đối tác thành ToolCallback, nhưng lỗi HTTP từ API bị làm phẳng thành thông báo chung nên chatbot không phân biệt hết hạn token với không tìm thấy dữ liệu.
Ứng dụng cung cấp ToolCallback tùy biến dùng chung giữa nhiều request, nhưng callback giữ bộ đếm và thông tin khách hiện tại trong trạng thái mutable làm dữ liệu các phiên ảnh hưởng nhau.
Một công cụ tính phí vận chuyển được tạo bằng ToolCallback thay vì phương thức @Tool, nhưng quá trình đăng ký bỏ qua callback đó khi tạo ChatClient cho kênh di động.
Đội sản phẩm gắn cùng tên cho một ToolCallback động và một phương thức @Tool, khiến bước lựa chọn công cụ không xác định rõ phiên bản nào phải chạy.
Một callback truy vấn báo giá sử dụng dịch vụ đồng bộ chậm, nhưng ứng dụng chạy nhiều lượt gọi tool đồng thời trên ít luồng xử lý và gây nghẽn các request khác.
Một ToolCallback gọi API ngoài sử dụng thông tin xác thực lâu dài trong cấu hình, nhưng khi khóa bị thu hồi callback vẫn thử liên tục và làm tăng lỗi ở nhà cung cấp.
Nền tảng phân tích trả kết quả tool gồm nhiều cấp dữ liệu, nhưng mã chuyển nội dung gửi lại cho mô hình chỉ lấy cấp đầu và bỏ sót cảnh báo về dữ liệu thiếu.
Một callback tìm kiếm hồ sơ trả kết quả rỗng hợp lệ, nhưng tầng hội thoại diễn giải thành lỗi và tự tạo câu trả lời về một hồ sơ không tồn tại.
Một công cụ có nhiều kiểu phản hồi tùy trạng thái đơn, nhưng phía chuyển kết quả cho mô hình không phân biệt thành công một phần với hoàn tất toàn bộ quy trình.
ChatClient nhận yêu cầu gọi tool từ mô hình, nhưng nhóm phát triển hiểu nhầm yêu cầu đó là tác vụ đã được model thực thi và hiển thị trạng thái hoàn tất trước khi callback chạy.
Một ứng dụng cấu hình cho phép mô hình đề xuất công cụ nhưng xử lý thực thi ở tầng riêng, khiến luồng hội thoại không có câu trả lời cuối vì kết quả tool chưa được gửi lại mô hình.
Hệ thống nhận yêu cầu gọi công cụ tạo đơn từ mô hình, nhưng ứng dụng chỉ log tên tool rồi trả lời người dùng mà không thực hiện thao tác nghiệp vụ.
Một workflow kiểm tra tồn kho rồi đặt hàng mong hai lời gọi tool diễn ra nối tiếp, nhưng kết quả tồn kho chưa về đã có lệnh đặt hàng khiến số lượng không được đối chiếu.
Ứng dụng dùng kết quả công cụ tìm khách hàng làm đầu vào công cụ cập nhật đơn, nhưng mô hình chọn nhầm một trong nhiều khách có tên gần giống nhau.
Một trợ lý công việc nhận nhiều yêu cầu gọi tool trong một lượt phản hồi, nhưng bộ điều phối chỉ xử lý lời gọi đầu khiến các bước còn lại bị bỏ qua.
Nhóm triển khai thực hiện song song các tool mà mô hình đã yêu cầu, nhưng hai công cụ cùng cập nhật trạng thái đơn và ghi đè kết quả của nhau.
Một ứng dụng nhận kết quả từ nhiều tool theo thứ tự hoàn tất khác thứ tự yêu cầu, nhưng bộ ghép phản hồi dựa vào vị trí thay vì định danh lời gọi khiến mô hình nhận sai kết quả.
Hệ thống gửi phản hồi tool về mô hình nhưng thiếu thông tin tương quan với lời gọi gốc, khiến bước hội thoại tiếp theo không biết dữ liệu thuộc thao tác nào.
ChatClient được cấu hình tự điều phối chu trình tool, nhưng ứng dụng còn gọi thủ công cùng phương thức từ tầng controller khiến thao tác tạo phiếu được thực hiện hai lần.
Một trợ lý hoàn tiền được mô hình yêu cầu gọi công cụ nhiều lượt để kiểm tra hóa đơn và khách hàng, nhưng đội phát triển không giới hạn số lượt dẫn đến hội thoại lặp vô tận.
Một chatbot dùng công cụ đọc đơn rồi hỏi mô hình tạo phản hồi, nhưng mô hình lại yêu cầu công cụ đọc lại cùng đơn nhiều lần làm số request tới dịch vụ kho tăng bất thường.
Một ứng dụng tự quản lý việc thực thi tool muốn kiểm tra người dùng trước khi chạy callback, nhưng thông tin danh tính không được giữ qua lượt gọi mô hình tiếp theo.
Một dịch vụ phân loại yêu cầu không có nhu cầu truy cập dữ liệu ngoài, nhưng model vẫn đề xuất một tool không liên quan và bộ điều phối không ghi nhận lý do lựa chọn đó.
Một workflow yêu cầu xác nhận từ người dùng trước khi đặt hàng, nhưng mô hình phát lệnh gọi tool ngay khi nghe câu hỏi về giá và ứng dụng thực hiện không có bước phê duyệt.
Một hệ thống cho phép mô hình gọi công cụ gửi tin nhắn, nhưng người dùng hủy yêu cầu khi lời gọi đang chạy và tin nhắn vẫn được gửi sau khi giao diện đã đóng.
Dịch vụ điều phối công cụ ở nhiều bước lưu kết quả trung gian trong bộ nhớ phiên, nhưng tiến trình khởi động lại khiến không thể xác định thao tác nào đã hoàn tất.
Một ứng dụng phát hiện lỗi ở tool thứ ba của workflow, nhưng hai công cụ trước đã thay đổi dữ liệu và câu trả lời cuối chỉ nói chung rằng yêu cầu thất bại.
Trợ lý bán hàng đặt lại hạn mức gọi tool cho từng lượt suy luận, nhưng một chuỗi hội thoại dài vẫn có thể thực hiện số lượng lời gọi vượt ngân sách của người dùng.
Một provider trả nhiều phương án tool-call trong các lựa chọn sinh khác nhau, nhưng tầng thực thi không xác định phương án được chọn nên chạy cả lời gọi dự phòng ngoài ý muốn.
Ứng dụng gắn ToolContext chứa tenant ID cho mỗi yêu cầu, nhưng callback thực tế vẫn dùng tenant cố định trong cấu hình nên truy vấn sang dữ liệu của khách khác.
Một tool cần đọc thông tin phân quyền từ ToolContext, nhưng đường gọi qua adapter mới không chuyển tiếp ngữ cảnh nên callback không biết người dùng đang đăng nhập.
Nền tảng hỗ trợ nội bộ chuyển trace ID qua ToolContext cho các callback, nhưng một tầng dịch vụ tạo ngữ cảnh mới làm log công cụ mất liên kết với request ban đầu.
Một công cụ đọc hồ sơ lấy tenant ID từ tham số do mô hình sinh thay vì từ ToolContext đáng tin cậy, khiến người dùng có thể yêu cầu truy vấn hồ sơ của tenant khác.
Một ứng dụng đưa cả quyền truy cập và thông tin phiên vào ToolContext, nhưng mã ghi log toàn bộ đối tượng ngữ cảnh làm lộ dữ liệu bí mật cho nhóm vận hành.
Hệ thống cập nhật hạn mức tài khoản mong model tự điền user ID từ ToolContext, nhưng dữ liệu ngữ cảnh này không được khai báo như tham số mà mô hình có thể nhìn thấy.
Một ToolCallback dùng mã tương quan từ ToolContext để ghi nhật ký, nhưng truy cập ngữ cảnh ở callback bất đồng bộ ngoài vòng thực thi ban đầu cho ra giá trị rỗng.
Ứng dụng nhiều tenant tái sử dụng cùng một đối tượng ToolContext có trạng thái mutable giữa các lần gọi, khiến yêu cầu của người dùng sau kế thừa thông tin phiên trước.
Một công cụ báo cáo cần định dạng thời gian theo ngôn ngữ khách hàng lấy từ ToolContext, nhưng server đặt giá trị mặc định toàn cục làm các ngày tháng bị hiểu sai.
Một chatbot dùng ToolContext lưu vai trò người dùng và đồng thời cho mô hình sinh role dưới dạng tham số, khiến hai nguồn thông tin quyền không khớp khi thực thi.
Một hệ thống cho nhiều callback tham chiếu cùng một đối tượng bộ đếm mutable qua ToolContext, khiến các lượt gọi đồng thời ghi đè số bước đã xử lý và làm lệch số liệu giám sát.
Một hệ thống định nghĩa ToolContext riêng cho từng bước workflow, nhưng mã chuyển tiếp chỉ giữ thông tin bước hiện tại nên mất mã giao dịch ban đầu để kiểm toán.
Nền tảng chăm sóc sức khỏe gọi tool lấy dữ liệu bệnh nhân nhưng không xác thực mã hồ sơ trong phạm vi bác sĩ đang đăng nhập, khiến chatbot có thể trả thông tin của người khác.
Ứng dụng quản lý nhân sự cho phép tool sửa hợp đồng chỉ dựa vào lời yêu cầu của mô hình, dù người dùng chỉ có vai trò xem và không được phép thay đổi dữ liệu.
Một công cụ tìm kiếm tài liệu nhận đường dẫn từ mô hình, nhưng không giới hạn thư mục làm việc khiến yêu cầu có thể đọc file cấu hình chứa khóa bí mật.
Một ứng dụng chấp nhận tham số URL từ tool request để tải tài liệu, nhưng tên miền do người dùng nhập trỏ tới dịch vụ mạng nội bộ không thuộc phạm vi nghiệp vụ.
Trợ lý doanh nghiệp dùng nội dung email làm dữ liệu cho mô hình, nhưng email chứa chỉ dẫn giả làm quản trị viên yêu cầu gọi công cụ chuyển tiền.
Một chatbot dùng kết quả tra cứu website làm ngữ cảnh tiếp tục suy luận, nhưng trang bên ngoài có lời nhắc sử dụng công cụ gửi thông tin nội bộ tới một địa chỉ lạ.
Dịch vụ thanh toán công bố tool chuyển khoản với tham số tài khoản đích, nhưng không yêu cầu xác nhận bổ sung khi mô hình tự suy đoán người nhận từ cuộc trò chuyện.
Ứng dụng sử dụng khóa API chung cho mọi lời gọi tool, khiến nhật ký hệ thống ngoài không phân biệt được nhân viên nào tạo hoặc sửa hồ sơ.
Một hệ thống đặt giới hạn quyền ở giao diện ChatClient, nhưng cùng ToolCallback còn được gọi từ API khác không có bước kiểm tra quyền tương tự.
Một công cụ xuất dữ liệu khách hàng lọc theo phòng ban do mô hình gửi, nhưng server không đối chiếu với phạm vi phòng ban mà người dùng được phép xem.
Ứng dụng lưu toàn bộ đối số và kết quả gọi tool vào trace để debug, khiến số thẻ khách hàng và thông tin hợp đồng nhạy cảm xuất hiện trên dashboard chung.
Một tool tìm kiếm tài khoản trả nhiều trường nhạy cảm hơn cần thiết, khiến nội dung gửi lại cho model chứa thông tin mà câu hỏi ban đầu không yêu cầu.
Nền tảng hỗ trợ pháp lý cho phép tool sửa văn bản gốc theo đề xuất của model, nhưng không lưu lịch sử phiên bản nên không thể đối chiếu những thay đổi gây tranh cãi.
Một doanh nghiệp gắn tool xóa dữ liệu vào chatbot phục vụ người dùng cuối, nhưng cơ chế phân quyền hiện tại chỉ xác thực đăng nhập mà không kiểm tra quyền xóa.
Dịch vụ tạo voucher dùng tham số phần trăm giảm giá từ mô hình, nhưng không giới hạn mức tối đa nên khách có thể gây ra ưu đãi ngoài quy định.
Ứng dụng gọi tool truy vấn dữ liệu bằng điều kiện lọc tự do, nhưng adapter đưa điều kiện trực tiếp vào câu lệnh database khiến có nguy cơ truy cập ngoài bảng được cấp phép.
Một chatbot dành cho nhiều chi nhánh được cấp tài khoản chung để gọi công cụ kiểm tồn, nhưng tài khoản có thể xem toàn bộ kho nên lời gọi nhầm mã chi nhánh làm lộ dữ liệu.
Một công cụ cập nhật hồ sơ nhân viên trả thông báo từ chối quyền, nhưng tầng hội thoại chuyển thông báo này thành yêu cầu thử lại thay vì dừng thao tác nhạy cảm.
Ứng dụng cho mô hình chọn công cụ kết xuất dữ liệu, nhưng danh mục chứa cả công cụ xuất dữ liệu thật và công cụ thử nghiệm với chính sách bảo mật khác nhau.
Nền tảng đối soát đọc dữ liệu tài chính qua tool, nhưng một nhân viên cố nhập lệnh yêu cầu mô hình bỏ qua kiểm tra quyền và truy vấn toàn bộ tài khoản.
Một callback dùng token được truyền như tham số công khai trong schema để gọi hệ thống ngoài, khiến mô hình có thể đưa token đó vào phần nội dung trả lời.
Dịch vụ dùng ToolContext để mang thông tin phiên nhưng không ràng buộc nó với token được xác thực, khiến client giả mạo tenant có thể thao tác với dữ liệu khác.
Một người dùng yêu cầu chatbot tạo báo cáo từ dữ liệu nhạy cảm, nhưng mô hình còn gọi thêm công cụ gửi email và chuyển nội dung đến địa chỉ ngoài doanh nghiệp.
Một hệ thống cần lưu dấu vết việc phê duyệt trước khi gọi tool ghi dữ liệu, nhưng nhật ký chỉ chứa câu trả lời cuối cùng của chatbot nên không biết lúc nào công cụ thực sự chạy.
Một công cụ thanh toán chấp nhận cùng mã yêu cầu nhiều lần, khiến retry sau lỗi phản hồi có thể tạo thêm giao dịch thay vì trả kết quả của thao tác trước.
Một callback gọi nhà cung cấp vận chuyển bị timeout sau khi tạo vận đơn, khiến ứng dụng không thể khẳng định vận đơn chưa tồn tại khi đề xuất gọi lại.
Ứng dụng được mô hình yêu cầu gọi tool tra cứu khách hàng nhưng dịch vụ CRM trả lỗi 503, khiến chatbot diễn giải tình trạng kỹ thuật thành khách hàng không có hồ sơ.
Một công cụ đọc điểm thưởng trả danh sách rỗng hợp lệ, nhưng nhóm điều phối coi mọi kết quả rỗng là lỗi và yêu cầu mô hình gọi lại liên tục.
Hệ thống gọi tool gửi email gặp lỗi xác thực 401, nhưng chính sách retry đối xử như lỗi mạng tạm thời và tiếp tục gửi với khóa đã bị thu hồi.
Một ToolCallback được cấu hình thời hạn chờ ngắn hơn thời gian đáp ứng thực tế của đối tác, khiến yêu cầu truy vấn hợp lệ liên tục bị hủy trước khi nhận dữ liệu.
Ứng dụng ghi kết quả của tool vào bộ nhớ đệm nhưng không xét đến quyền của từng người dùng, khiến yêu cầu tra cứu cùng mã hồ sơ có thể trả dữ liệu của phiên trước.
Một công cụ chỉnh sửa đơn hàng trả thành công sau khi nhận việc vào queue, nhưng chatbot nói rằng đơn đã cập nhật hoàn toàn dù consumer chưa xử lý.
Nhóm vận hành cho tool gửi yêu cầu thanh toán có cơ chế retry khi mất kết nối, nhưng chưa có khả năng phân biệt yêu cầu được thực thi trước khi ngắt hay chưa.
Một callback tra cứu đơn trả lỗi dữ liệu do tham số không hợp lệ, nhưng ứng dụng tự chuyển thành thông báo thành công với mã đơn mặc định.
Dịch vụ phân loại hợp đồng gọi ba tool để đọc tài liệu rồi bị lỗi ở công cụ cuối, khiến bước trước đã ghi dữ liệu tạm nhưng không có cơ chế thu hồi.
Một tool gọi API đích phải đi qua proxy có giới hạn kết nối, nhưng nhiều request ChatClient cùng lúc làm pool hết kết nối và tăng độ trễ hội thoại.
Một hệ thống định nghĩa giới hạn số lần tool được gọi trong mỗi request, nhưng người dùng hỏi liên tiếp nhiều lượt vẫn gây tải vượt công suất của dịch vụ ngoài.
Nền tảng thương mại điện tử cho mô hình gọi đồng thời nhiều tool tìm sản phẩm, nhưng một API có giới hạn tần suất thấp khiến các lời gọi sau liên tục bị từ chối.
Một công cụ tạo báo cáo mất hai phút mới hoàn tất, nhưng timeout của ChatClient kết thúc trước và người dùng gửi lại yêu cầu khiến hai báo cáo được tạo song song.
Ứng dụng trả nội dung tool rất dài vào ngữ cảnh model, khiến chi phí token và thời gian suy luận tăng dù câu trả lời cuối chỉ cần một mã trạng thái.
Hệ thống dùng lời gọi tool lấy dữ liệu ở nhiều thời điểm, nhưng các bản ghi thay đổi giữa các lượt nên mô hình tạo báo cáo không nhất quán về thời gian.
Nền tảng thông báo để mô hình gọi công cụ gửi hàng loạt tin nhắn, nhưng kết quả chỉ trả tổng số đã nhận việc chứ không cho biết tin nào gửi thất bại.
Ứng dụng sử dụng tool lấy dữ liệu thời gian thực rồi cache kết quả phản hồi mô hình quá lâu, khiến chatbot trả số lượng tồn cũ ngay cả khi kho vừa thay đổi.
Một luồng xử lý công cụ bất đồng bộ bị người dùng hủy yêu cầu, nhưng thao tác ghi phía backend tiếp tục chạy và cập nhật dữ liệu sau khi hội thoại đã kết thúc.
Dịch vụ duy trì nhiều công cụ có tác dụng phụ trong cùng một chuỗi, nhưng một lỗi mạng giữa chừng làm ứng dụng không biết bước nào cần đối soát trước khi chạy lại.
Một công cụ ghi dữ liệu có cơ chế giới hạn theo tài khoản kỹ thuật, nhưng nhiều chatbot dùng chung tài khoản và khiến một nhóm người dùng chiếm hết hạn mức.
Nhóm triển khai bật logging chi tiết cho mọi callback trong production, nhưng dữ liệu trả về có kích thước lớn làm disk log tăng nhanh và ảnh hưởng hiệu năng.
Một tool gọi hệ thống tính phí trả kết quả theo loại tiền tệ, nhưng mô hình bỏ qua mã đơn vị và trả lời như thể mọi khoản tiền đều tính bằng đồng Việt Nam.
Ứng dụng giám sát chỉ đếm số ChatClient request thành công, nhưng không đo số lần tool thất bại rồi được mô hình che giấu bằng lời giải thích khác.
Một công cụ chạy thành công nhưng mô hình diễn đạt kết quả sai sau khi nhận phản hồi, khiến dashboard chỉ dựa vào trạng thái callback không phát hiện câu trả lời sai.
Một nhóm muốn xác minh tool chỉ được gọi với tham số hợp lệ, nhưng bài kiểm thử dùng mock luôn trả dữ liệu thành công bất kể mã khách hàng mô hình truyền vào.
Đội QA kiểm thử @Tool với phương thức Java trực tiếp, nhưng không chạy qua ChatClient nên không phát hiện công cụ bị thiếu trong danh sách đăng ký.
Một bộ test chỉ kiểm tra mô hình có yêu cầu gọi tool, nhưng không kiểm tra ứng dụng đã thực thi hay chuyển kết quả trở lại model nên lỗi điều phối lọt qua phát hành.
Ứng dụng kiểm thử schema bằng đầu vào hợp lệ, nhưng không bao gồm trường thiếu, giá trị null hay enum lạ làm những lỗi chuyển kiểu chỉ xuất hiện trong production.
Một bài test mô phỏng model chọn công cụ tra cứu, nhưng không kiểm tra tình huống model yêu cầu công cụ ghi và thao tác nhạy cảm được thực hiện ngoài ý muốn.
Hệ thống kiểm thử ToolContext bằng một tenant duy nhất, khiến lỗi tái sử dụng metadata giữa các phiên chỉ được phát hiện sau khi phục vụ nhiều khách hàng.
Một bộ kiểm thử dùng mô hình thật với câu hỏi cố định nhưng yêu cầu phải gọi đúng một tool mọi lần, khiến bài test thất bại không ổn định vì hành vi chọn công cụ có thể thay đổi.
Một nhóm dùng dữ liệu mock nhỏ cho kết quả tool, nhưng ở production dữ liệu lớn vượt giới hạn ngữ cảnh và chatbot không thể hoàn tất phản hồi.
Ứng dụng có kịch bản nhiều lượt gọi công cụ nối tiếp, nhưng bộ test chỉ kiểm tra một lượt nên không phát hiện kết quả tool trước bị ghép sai với yêu cầu sau.
Đội phát triển mô phỏng lỗi 500 từ backend trong bài kiểm thử, nhưng không kiểm tra việc tool có tác dụng phụ đã hoàn thành trước khi backend mất phản hồi.
Một bài test cho công cụ tạo đơn chỉ chạy lần đầu, khiến lỗi ghi trùng khi model yêu cầu công cụ lần thứ hai không có trong phạm vi kiểm thử.
Ứng dụng cho phép nhiều callback thực thi đồng thời, nhưng bộ kiểm thử tuần tự không phát hiện tranh chấp trên trạng thái mutable của một ToolCallback dùng chung.
Một nhóm cấu hình giới hạn tool-call cho ChatClient, nhưng bộ test không kiểm tra hội thoại lặp và tình huống provider trả nhiều lời gọi tool trong một phản hồi.
Nền tảng dùng kết quả callback để tạo báo cáo, nhưng bài kiểm thử chỉ xác nhận có văn bản đầu ra chứ không kiểm tra số tiền và thời điểm khớp dữ liệu nguồn.
Ứng dụng thử nghiệm quyền truy cập bằng tài khoản quản trị, nhưng chưa kiểm thử người dùng thường yêu cầu tool đọc hồ sơ thuộc phòng ban khác.
Một bài test mô phỏng người dùng chèn chỉ dẫn vào dữ liệu từ website, nhưng không quan sát các tool thực tế được gọi nên không biết model có thực hiện hành động ngoài yêu cầu.
Một hệ thống hồi quy so sánh văn bản câu trả lời đúng từng ký tự, khiến test thất bại khi model thay cách diễn đạt dù lời gọi tool và kết quả nghiệp vụ vẫn phù hợp.
Đội phát triển chỉ ghi trace của lần gọi mô hình mà không ghi từng tool request, khiến thời gian thực thi API ngoài bị quy nhầm thành thời gian suy luận của model.
Ứng dụng lưu lịch sử lời gọi công cụ nhưng không gắn trace ID và người khởi tạo, khiến sự cố sửa dữ liệu khó truy ngược tới hội thoại cụ thể.
Một dịch vụ đo số lần model yêu cầu tool nhưng không đo số lần callback được thực thi thành công, khiến biểu đồ hiển thị khối lượng nghiệp vụ cao hơn thực tế.
Nền tảng triển khai nhiều phiên bản mô tả @Tool, nhưng log không lưu phiên bản schema nên đội trực không tái hiện được các lỗi tham số sau cập nhật.
Một ứng dụng thay đổi cấu hình tool theo thời gian mà không có bài kiểm thử hồi quy hành vi chọn công cụ, khiến model bắt đầu ưu tiên tool đắt hơn cho câu hỏi thông thường.
Một hệ thống giám sát chỉ đo độ trễ trung bình của ChatClient, nhưng một số tool có p99 rất cao khiến khách hàng thỉnh thoảng chờ hàng phút không được cảnh báo.
Một chatbot dùng ToolCallback để gọi API ngân hàng, nhưng khi lỗi quyền truy cập tăng dashboard chỉ hiển thị lỗi trả lời AI chung và không xác định được nơi phát sinh.
Một ứng dụng quan sát số token dùng cho mỗi câu trả lời nhưng không gắn số lượt tool, khiến chi phí tăng do kết quả công cụ dài bị hiểu nhầm là do prompt người dùng.
Nền tảng đo tỷ lệ yêu cầu hoàn tất nhưng không thống kê số tác vụ đã thực hiện trước khi người dùng hủy, khiến dữ liệu nghiệp vụ phát sinh ngoài báo cáo.
Ứng dụng có kênh hỗ trợ tiếng Việt và tiếng Anh, nhưng mô tả tool chỉ được kiểm thử bằng tiếng Anh nên model thường không chọn đúng công cụ khi khách hỏi bằng tiếng Việt.
Một workflow dùng cùng ChatClient cho yêu cầu tư vấn và cập nhật thực tế, nhưng dashboard không phân biệt lượt gọi tool chỉ đọc với lượt gây thay đổi dữ liệu.
Đội vận hành cập nhật mô tả công cụ xóa hồ sơ nhưng không có bộ đánh giá an toàn theo tập hội thoại chuẩn, khiến khả năng chọn nhầm tool chỉ được phát hiện sau sự cố.
