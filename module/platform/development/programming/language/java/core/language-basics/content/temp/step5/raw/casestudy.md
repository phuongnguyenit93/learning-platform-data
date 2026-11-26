Một sinh viên biên dịch chương trình Java thành công trên máy có JDK mới nhưng không chạy được trên máy thực hành dùng runtime cũ; hãy xây dựng tình huống kiểm tra sự tương thích giữa công cụ biên dịch và JVM.
Một nhóm nộp bài tập Java có lớp khởi động nhưng lệnh chạy không tìm thấy phương thức main hợp lệ, dù chương trình không có lỗi cú pháp; hãy đặt tình huống xác minh điểm vào ứng dụng.
Một dự án nhỏ khai báo lớp public với tên khác tên file nguồn, khiến bước biên dịch bị từ chối trên máy của giảng viên; hãy xây dựng tình huống kiểm tra quy tắc tổ chức mã nguồn.
Một ứng dụng console chạy được trong IDE nhưng thất bại khi dùng terminal vì lớp khởi động thuộc package và người dùng gọi sai tên đầy đủ; hãy đặt tình huống xác định cách định danh lớp.
Một nhóm sao chép file class sang thư mục triển khai mà không giữ cấu trúc package, khiến JVM không thể tìm lớp dù file vẫn tồn tại; hãy xây dựng tình huống đối chiếu thư mục và tên lớp.
Một bài tập dùng thư viện ngoài để đọc dữ liệu nhưng lệnh javac chạy thành công còn lệnh java không tìm được lớp thư viện khi thực thi; hãy đặt tình huống phân biệt classpath biên dịch và runtime.
Một chương trình nhận tên file và chế độ chạy qua command-line arguments, nhưng người dùng không truyền đủ tham số khiến ứng dụng truy cập phần tử không tồn tại; hãy đặt tình huống kiểm tra đầu vào khởi động.
Một ứng dụng console đọc tiếng Việt từ mã nguồn nhưng sau khi biên dịch trên máy có encoding khác thì thông báo xuất ra bị lỗi dấu; hãy xây dựng tình huống đánh giá mã hóa ký tự trong chuỗi công cụ.
Một đội phát triển đóng gói bài tập vào JAR nhưng người sử dụng không thể khởi chạy bằng lệnh dành cho executable JAR vì thiếu thông tin lớp bắt đầu; hãy đặt tình huống kiểm tra cấu hình đóng gói.
Một chương trình Java được chạy từ một thư mục làm việc khác thư mục dự án, khiến đường dẫn file dữ liệu tương đối không còn đúng; hãy xây dựng tình huống phân biệt working directory và vị trí class.
Một hệ thống có hai lớp cùng tên trong các package khác nhau nhưng chương trình nhập sai lớp qua import, khiến xử lý dữ liệu dùng implementation không mong muốn; hãy đặt tình huống xác minh khai báo import.
Một dự án sử dụng nhiều file Java nhưng người học chỉ biên dịch file khởi động và gặp lỗi phụ thuộc chưa được tạo, trong khi IDE tự quản lý toàn bộ nguồn; hãy đặt tình huống kiểm tra quy trình build cơ bản.
Một người học thử khai báo hai lớp public cấp cao nhất trong cùng một file Java và gặp lỗi khi chuyển từ ví dụ nhỏ sang dự án nhiều lớp; hãy xây dựng tình huống xác định quy tắc file nguồn.
Một ứng dụng cần hiển thị thông báo lỗi cấu hình lên terminal nhưng mọi lỗi đều được in chung với kết quả chuẩn, khiến script gọi không phân biệt được dữ liệu và lỗi; hãy đặt tình huống thiết kế đầu ra console.
Một dự án chuyển mã nguồn từ Windows sang Linux và lệnh chạy không tìm đúng tên file có chữ hoa chữ thường khác nhau, khiến bài kiểm thử triển khai thất bại; hãy xây dựng tình huống kiểm tra tính di động.
Một bài tập yêu cầu chạy chương trình từ terminal không dùng IDE, nhưng người học chỉ cài môi trường thực thi và không tìm thấy công cụ javac; hãy đặt tình huống phân biệt công cụ JDK với JVM.
Một ứng dụng lưu tên người dùng trong biến cục bộ rồi sử dụng trước khi mọi nhánh xử lý đều gán giá trị, khiến compiler báo biến có thể chưa được khởi tạo; hãy đặt tình huống kiểm tra luồng gán biến.
Một lớp quản lý hồ sơ có trường số nguyên chưa được gán trong constructor nhưng chương trình vẫn đọc được giá trị mặc định, khiến người học tưởng biến cục bộ cũng hoạt động tương tự; hãy xây dựng tình huống phân biệt.
Một chương trình tính số lượng mặt hàng dùng byte để tiết kiệm bộ nhớ, nhưng kết quả vượt phạm vi biểu diễn khi cửa hàng có nhiều sản phẩm; hãy đặt tình huống đánh giá lựa chọn kiểu số nguyên.
Một hệ thống ghi số lượt truy cập tích lũy bằng int và sau nhiều tháng thống kê xuất hiện giá trị âm dù dữ liệu đầu vào luôn dương; hãy xây dựng tình huống xác minh tràn số nguyên.
Một ứng dụng lưu tổng doanh thu theo đơn vị đồng bằng int, nhưng chỉ một giao dịch lớn đã vượt giới hạn và báo cáo cho kết quả sai; hãy đặt tình huống đánh giá kiểu lưu giá trị.
Một hệ thống nhận mã bưu chính bắt đầu bằng số không nhưng người học lưu trong kiểu số nguyên, khiến số không đầu bị mất khi in địa chỉ; hãy xây dựng tình huống phân biệt dữ liệu định danh và số học.
Một chương trình tính tiền thanh toán bằng double và thấy kết quả có sai số thập phân nhỏ sau khi cộng nhiều dòng hóa đơn, khiến bộ phận kế toán không chấp nhận; hãy đặt tình huống xác định yêu cầu độ chính xác.
Một công cụ chấm điểm lưu điểm trung bình bằng int và dùng phép chia hai số nguyên, khiến kết quả mất phần thập phân mặc dù biến nhận thuộc kiểu thực; hãy xây dựng tình huống kiểm tra thứ tự tính toán.
Một ứng dụng tính tổng chi phí bằng phép nhân hai số int rồi gán vào long, nhưng giá trị đã bị tràn trước khi chuyển sang biến nhận; hãy đặt tình huống phân tích phép toán trung gian.
Một bộ xử lý dữ liệu nhận số nguyên lớn dưới dạng chuỗi nhưng gọi thao tác chuyển đổi sang int cho tất cả dữ liệu, khiến một số mã giao dịch không thể parse; hãy đặt tình huống kiểm tra phạm vi.
Một chương trình tính tỉ lệ giảm giá với phép chia nguyên nên mọi mức giảm nhỏ hơn một trăm phần trăm đều cho ra giá trị không; hãy đặt tình huống phân tích kiểu toán hạng.
Một ứng dụng kiểm tra hai kết quả tính toán kiểu double bằng phép so sánh bằng tuyệt đối và thỉnh thoảng từ chối dữ liệu tương đương về mặt nghiệp vụ; hãy xây dựng tình huống đánh giá sai số.
Một hệ thống lưu thời lượng sự kiện bằng số milliseconds trong int, khiến các phiên hoạt động kéo dài bị vượt phạm vi và hiển thị thời lượng sai; hãy đặt tình huống lựa chọn kiểu số.
Một chương trình dùng char để lưu ký tự biểu tượng emoji của người dùng, nhưng dữ liệu ký tự thực tế có thể cần nhiều hơn một đơn vị UTF-16; hãy xây dựng tình huống kiểm chứng giới hạn kiểu char.
Một ứng dụng đọc cờ bật tính năng từ file cấu hình dưới dạng chuỗi rồi sử dụng như boolean, khiến giá trị có chữ hoa hoặc khoảng trắng bị hiểu sai; hãy đặt tình huống xác định quy tắc chuyển đổi.
Một đội sử dụng biến final để giữ tham chiếu tới một mảng cấu hình nhưng sau đó thay phần tử của mảng và tưởng từ khóa final đã ngăn mọi thay đổi; hãy xây dựng tình huống phân biệt.
Một lớp quản lý tài khoản có biến thành viên cùng tên với tham số constructor, khiến phép gán không cập nhật trạng thái object như người học kỳ vọng; hãy đặt tình huống kiểm tra che khuất biến.
Một chương trình có biến đếm được khai báo trong khối điều kiện nhưng cố sử dụng ngoài phạm vi khối đó, khiến bước biên dịch bị lỗi; hãy xây dựng tình huống xác định scope.
Một người học dùng suy luận kiểu cục bộ cho biến có giá trị ban đầu là chuỗi, rồi gán số nguyên vào cùng biến ở bước tiếp theo và gặp lỗi; hãy đặt tình huống phân biệt suy luận với kiểu động.
Một ứng dụng lưu trạng thái chưa có dữ liệu bằng null trong một biến kiểu nguyên thủy, khiến chương trình không thể biểu diễn trạng thái đó theo cách đã thiết kế; hãy đặt tình huống kiểm tra biểu diễn dữ liệu.
Một bộ xử lý đơn hàng dùng kiểu wrapper Integer có thể nhận null nhưng tự chuyển sang int trước khi kiểm tra, khiến một request thiếu số lượng ném ngoại lệ; hãy xây dựng tình huống phân tích unboxing.
Một chương trình so sánh hai đối tượng Integer tạo từ dữ liệu nhập bằng toán tử so sánh tham chiếu và cho kết quả khác nhau tùy giá trị, khiến kiểm thử khó hiểu; hãy đặt tình huống kiểm tra equality.
Một ứng dụng lưu chuỗi trạng thái đơn hàng nhưng so sánh bằng toán tử dành cho tham chiếu object, khiến một số request hợp lệ không đi vào nhánh tương ứng; hãy đặt tình huống phân biệt so sánh giá trị.
Một chương trình có biểu thức chứa cộng, nhân và điều kiện nhưng kết quả tính chiết khấu sai vì người viết suy đoán thứ tự ưu tiên toán tử; hãy đặt tình huống kiểm tra precedence.
Một hệ thống xác thực kiểm tra tài khoản không null và thuộc tính kích hoạt, nhưng đảo vị trí hai điều kiện khiến chương trình truy cập thành viên của giá trị null; hãy xây dựng tình huống đánh giá short-circuit.
Một ứng dụng dùng phép AND bitwise thay cho phép AND điều kiện trong kiểm tra đầu vào, khiến thao tác ở vế phải vẫn chạy và gây ngoại lệ; hãy đặt tình huống phân biệt hai nhóm toán tử.
Một công cụ phân loại mã hàng dựa trên phần dư của phép chia nhưng với mã âm kết quả phân nhóm khác quy tắc toán học mà người thiết kế giả định; hãy đặt tình huống kiểm chứng toán tử modulo.
Một chương trình dùng phép tăng biến ngay trong biểu thức in kết quả, khiến số được hiển thị khác số lưu lại sau phép tính; hãy xây dựng tình huống phân tích tác dụng phụ và thứ tự đánh giá.
Một ứng dụng cập nhật điểm thưởng bằng phép gán kết hợp cho biến kiểu nhỏ, nhưng người học không hiểu vì sao phép gán thường tương đương lại bị compiler từ chối; hãy đặt tình huống kiểm tra chuyển kiểu.
Một API nhận giá trị số lớn dạng long nhưng gán sang short để truyền cho thư viện cũ, khiến thông tin bị mất mà chương trình vẫn tiếp tục; hãy xây dựng tình huống đánh giá ép kiểu thu hẹp.
Một báo cáo doanh thu sử dụng phép làm tròn sau khi chuyển số thực sang int, khiến phần thập phân bị cắt trước khi thuật toán làm tròn được áp dụng; hãy đặt tình huống xác định trình tự chuyển đổi.
Một chương trình cộng một số byte và một số short rồi muốn lưu trực tiếp vào short, nhưng kết quả biểu thức được nâng kiểu rộng hơn; hãy đặt tình huống kiểm chứng numeric promotion.
Một hệ thống phân quyền biểu diễn nhiều trạng thái bằng các cờ bit nhưng điều kiện kiểm tra được viết như phép so sánh thông thường, khiến một vai trò có nhiều quyền bị đánh giá sai; hãy xây dựng tình huống phân tích toán tử.
Một cửa hàng có chương trình giảm giá nếu khách hàng là thành viên hoặc đơn hàng vượt ngưỡng, nhưng nhóm lập trình dùng điều kiện AND và bỏ sót người đủ một tiêu chí; hãy đặt tình huống kiểm chứng biểu thức logic.
Một ứng dụng có yêu cầu điểm từ 0 đến 10 nhưng logic kiểm tra dùng hai phép so sánh rời rạc kết hợp sai, khiến mọi điểm đều được chấp nhận; hãy xây dựng tình huống phân tích ràng buộc khoảng.
Một bài tập phân loại kết quả học tập theo mức điểm có các ngưỡng giao nhau, khiến điểm đúng tại ranh giới được xếp vào hai nhóm tùy thứ tự if; hãy đặt tình huống kiểm chứng ranh giới điều kiện.
Một hệ thống tính phí giao hàng dựa trên khu vực và trọng lượng, nhưng nhánh điều kiện cho trường hợp trọng lượng lớn luôn bị nhánh tổng quát phía trước che khuất; hãy xây dựng tình huống phân tích cấu trúc if-else.
Một ứng dụng kiểm tra người dùng trưởng thành bằng tuổi nhập trực tiếp nhưng bỏ qua giá trị âm và tuổi bất thường, khiến dữ liệu không hợp lệ vẫn vào bước xử lý; hãy đặt tình huống thiết kế validation.
Một ứng dụng điều hướng menu bằng switch truyền thống nhưng thiếu điểm dừng ở một trường hợp, khiến sau khi chọn mục xem báo cáo lại thực hiện thêm mục xóa; hãy xây dựng tình huống kiểm tra fall-through.
Một chương trình xử lý mã hành động từ người dùng nhưng switch không có nhánh mặc định, khiến mã không nhận dạng được không tạo ra thông báo nào; hãy đặt tình huống đánh giá xử lý đầu vào lạ.
Một hệ thống nhận trạng thái đơn hàng dạng chuỗi có thể null nhưng đưa trực tiếp vào switch, khiến request thiếu trạng thái bị lỗi trước khi validation; hãy đặt tình huống kiểm tra dữ liệu đầu vào.
Một công cụ console yêu cầu nhập lại mật khẩu cho đến khi hợp lệ, nhưng vòng while chỉ kiểm tra giá trị cũ và bỏ qua lần nhập mới nhất; hãy xây dựng tình huống xác minh điều kiện lặp.
Một ứng dụng hiển thị menu ít nhất một lần rồi nhận lựa chọn, nhưng dùng vòng while với điều kiện ban đầu sai khiến người dùng không thấy menu; hãy đặt tình huống đánh giá do-while.
Một chương trình in số thứ tự từ 1 đến N nhưng dùng điều kiện nhỏ hơn N, khiến phần tử cuối không xuất hiện trong báo cáo; hãy xây dựng tình huống kiểm tra biên vòng for.
Một hệ thống duyệt mảng sản phẩm dùng điều kiện chỉ số nhỏ hơn hoặc bằng số phần tử, khiến truy cập vượt biên ở lần lặp cuối; hãy đặt tình huống kiểm chứng ranh giới mảng.
Một ứng dụng nhận dữ liệu liên tục từ bàn phím nhưng không có điều kiện dừng phù hợp khi người dùng gửi tín hiệu kết thúc đầu vào, khiến vòng lặp không thoát; hãy xây dựng tình huống xử lý EOF.
Một chương trình tìm sản phẩm đầu tiên thỏa điều kiện nhưng đặt break trong vòng lặp bên trong, khiến vòng ngoài tiếp tục và ghi đè kết quả; hãy đặt tình huống phân tích vòng lặp lồng nhau.
Một bộ lọc danh sách bỏ qua bản ghi không hợp lệ bằng continue nhưng đặt thao tác cập nhật chỉ số ở phía sau, khiến cùng một bản ghi được xét liên tục; hãy xây dựng tình huống kiểm tra tiến triển vòng lặp.
Một chương trình xử lý bảng điểm có vòng lặp lồng để duyệt lớp và học sinh, nhưng số lần thực hiện tăng quá nhanh khi dữ liệu lớn; hãy đặt tình huống đánh giá độ phức tạp cơ bản.
Một công cụ tính tổng các số từ 1 đến N dùng int cho bộ cộng, khiến kết quả sai khi N tăng dù từng số hạng vẫn nằm trong phạm vi int; hãy xây dựng tình huống kiểm tra tràn tổng.
Một chương trình cho phép nhập điểm đến khi nhập mã dừng, nhưng mã dừng có thể được nhập tại nơi đang đòi một số và gây NumberFormatException; hãy đặt tình huống xác định luồng nhập.
Một ứng dụng đánh giá điều kiện cho vay bằng nhiều if độc lập, khiến cùng một hồ sơ có thể được ghi vào cả danh sách duyệt và danh sách từ chối; hãy đặt tình huống phân tích tính loại trừ nhánh.
Một bộ lọc log duyệt hàng nghìn dòng và dùng lệnh dừng ngay khi gặp dòng trống, khiến mọi dữ liệu sau dòng trống bị bỏ sót; hãy đặt tình huống phân biệt dòng rỗng với kết thúc file.
Một hệ thống nhập số lượng sản phẩm có thể bằng không nhưng vòng lặp giả định phải thực hiện ít nhất một lần, khiến chương trình vẫn yêu cầu nhập dữ liệu; hãy xây dựng tình huống kiểm tra case rỗng.
Một ứng dụng tính số nguyên tố bằng vòng lặp nhưng bỏ qua các giá trị 0, 1 và số âm, khiến kết quả phân loại sai cho đầu vào biên; hãy đặt tình huống thiết kế tập kiểm thử.
Một chương trình tạo bảng cửu chương bằng hai vòng lặp nhưng dùng nhầm biến đếm của vòng ngoài ở điều kiện vòng trong, khiến ứng dụng không kết thúc; hãy xây dựng tình huống tìm lỗi điều khiển.
Một service nhập danh sách từ bàn phím đến khi đủ N phần tử, nhưng nếu N âm thì vòng lặp và thông báo kết quả không phản ánh đầu vào không hợp lệ; hãy đặt tình huống đánh giá quy tắc tiền điều kiện.
Một chương trình chọn phần tử lớn nhất của mảng số nguyên nhưng dùng giá trị khởi tạo bằng không, khiến kết quả sai khi mọi số đều âm; hãy xây dựng tình huống xác minh khởi tạo biến tổng hợp.
Một API nhỏ nhận mảng rỗng để tính trung bình và thực hiện phép chia cho độ dài mảng bằng không, khiến kết quả không phù hợp hợp đồng; hãy đặt tình huống xác định hành vi với dữ liệu rỗng.
Một ứng dụng đọc phần tử đầu tiên của mảng mà chưa xác minh mảng có dữ liệu, khiến request không có sản phẩm gây ArrayIndexOutOfBoundsException; hãy xây dựng tình huống kiểm tra chỉ số.
Một bài tập tạo mảng với số phần tử lấy từ bàn phím nhưng người dùng nhập kích thước âm, khiến chương trình ném ngoại lệ trước khi đưa ra thông báo; hãy đặt tình huống validation kích thước.
Một hệ thống dùng mảng int để lưu số lượng tồn kho và chưa khởi tạo từng phần tử, khiến giá trị không được nhập bị hiểu nhầm là đã xác nhận tồn kho bằng không; hãy xây dựng tình huống đánh giá giá trị mặc định.
Một công cụ quản lý danh sách học sinh có mảng đối tượng được tạo đúng kích thước nhưng từng phần tử chưa khởi tạo, khiến truy cập tên học sinh gây NullPointerException; hãy đặt tình huống phân biệt mảng và đối tượng.
Một chương trình xử lý bảng điểm hai chiều giả định mọi hàng có cùng số cột, nhưng nguồn dữ liệu tạo mảng hai chiều có các hàng dài ngắn khác nhau; hãy đặt tình huống kiểm tra mảng không đều.
Một ứng dụng đọc cột điểm thứ ba của mọi hàng trong mảng hai chiều nhưng có một hàng chỉ chứa hai điểm, khiến lỗi xảy ra giữa quá trình tổng hợp; hãy xây dựng tình huống kiểm chứng từng hàng.
Một bộ phận bán hàng sao chép mảng đối tượng đơn hàng rồi sửa thuộc tính của phần tử trong bản sao, khiến dữ liệu mảng gốc cũng thay đổi; hãy đặt tình huống phân biệt sao chép tham chiếu.
Một ứng dụng dùng phép so sánh bằng giữa hai mảng có phần tử giống nhau và kết luận chúng khác nhau vì tham chiếu được tạo riêng; hãy xây dựng tình huống đánh giá so sánh nội dung.
Một chương trình hiển thị mảng bằng cách in trực tiếp biến mảng ra console, khiến đầu ra không thể hiện danh sách phần tử như người dùng mong muốn; hãy đặt tình huống kiểm tra cách biểu diễn.
Một công cụ tìm kiếm dùng binary search trên mảng mã sản phẩm chưa được sắp xếp, khiến một số mã có tồn tại nhưng bị báo không tìm thấy; hãy xây dựng tình huống xác định tiền điều kiện thuật toán.
Một bộ xử lý xếp hạng sắp xếp trực tiếp mảng đầu vào để tạo báo cáo, khiến màn hình khác đang dùng mảng đó mất thứ tự nhập ban đầu; hãy đặt tình huống đánh giá tác dụng phụ.
Một ứng dụng duy trì danh sách sản phẩm bằng mảng cố định nhưng khi đủ chỗ vẫn cố thêm phần tử tiếp theo, khiến logic cập nhật không còn hoạt động; hãy xây dựng tình huống kiểm tra giới hạn sức chứa.
Một hệ thống lọc các số dương từ mảng lớn nhưng mảng kết quả được khởi tạo bằng chiều dài đầu vào, khiến phần tử mặc định bị hiểu là kết quả hợp lệ; hãy đặt tình huống xác định số phần tử thực.
Một chương trình đếm số lần xuất hiện của một giá trị trong mảng nhưng dừng ở lần tìm thấy đầu tiên, khiến báo cáo tần suất không chính xác; hãy xây dựng tình huống phân biệt tìm kiếm và đếm.
Một ứng dụng nhập điểm các học sinh vào mảng và tính trung bình nhưng dùng nhầm số học sinh dự kiến thay vì số điểm thực tế đã nhập; hãy đặt tình huống xác định lượng dữ liệu hợp lệ.
Một bộ xử lý văn bản chuyển chuỗi thành mảng ký tự để kiểm tra độ dài tên, nhưng dữ liệu chứa emoji làm số đơn vị ký tự khác số ký tự người dùng nhìn thấy; hãy xây dựng tình huống đánh giá giới hạn.
Một hệ thống xuất danh sách mã hàng từ mảng đã sắp xếp nhưng phép duyệt bắt đầu ở chỉ số một, khiến mã đầu tiên bị bỏ khỏi file kết quả; hãy đặt tình huống kiểm tra vị trí bắt đầu.
Một ứng dụng nạp dữ liệu từ mảng vào cấu trúc khác nhưng sửa trực tiếp phần tử khi chuẩn hóa, khiến bản ghi gốc bị thay đổi trước bước đối soát; hãy xây dựng tình huống kiểm tra trách nhiệm biến đổi.
Một lớp xử lý báo cáo có nhiều đoạn mã tính thuế giống nhau ở từng màn hình, nhưng mỗi lần thay công thức nhóm phải sửa thủ công nhiều nơi; hãy đặt tình huống xác định phương thức dùng lại.
Một ứng dụng tính tổng tiền bằng phương thức nhận hai tham số nhưng khi gọi nhầm thứ tự giá và số lượng, khiến kết quả không phản ánh đơn hàng thực tế; hãy xây dựng tình huống đánh giá hợp đồng tham số.
Một chương trình có phương thức tính điểm không trả kết quả mà chỉ in ra console, khiến module tổng hợp không thể sử dụng giá trị để phân loại học viên; hãy đặt tình huống phân biệt return và output.
Một ứng dụng khai báo phương thức trả về số nguyên nhưng một nhánh điều kiện không trả giá trị, khiến compiler từ chối trước khi chạy; hãy xây dựng tình huống kiểm chứng đủ nhánh trả về.
Một thư viện nhỏ có hai phương thức cùng tên khác danh sách tham số để tính diện tích hình học, nhưng một lời gọi dùng số nguyên dẫn đến chọn overload ngoài dự đoán; hãy đặt tình huống đánh giá overload.
Một chương trình có hai overload nhận các kiểu tham chiếu khác nhau nhưng lời gọi truyền null gây mơ hồ khi biên dịch, khiến đội phát triển không xác định được phương thức; hãy xây dựng tình huống kiểm tra độ rõ ràng API.
Một lớp tiện ích khai báo phương thức instance nhưng gọi trực tiếp từ main trong ngữ cảnh static, khiến chương trình không biên dịch; hãy đặt tình huống phân biệt thành viên class và object.
Một hệ thống truyền số lượng vào phương thức điều chỉnh rồi tưởng biến nguyên thủy của caller sẽ thay đổi trực tiếp, khiến bản ghi cuối không phản ánh tính toán; hãy xây dựng tình huống kiểm tra cách truyền tham số.
Một chương trình truyền đối tượng giỏ hàng vào phương thức cập nhật và nhận thấy thuộc tính giỏ hàng bị thay đổi sau lời gọi, khiến người học hiểu nhầm Java truyền tham chiếu bằng tham chiếu; hãy đặt tình huống phân tích.
Một phương thức nhận mảng sản phẩm và sắp xếp tại chỗ, khiến danh sách gốc của caller cũng thay đổi dù tên phương thức gợi ý chỉ tạo báo cáo; hãy xây dựng tình huống đánh giá side effect.
Một ứng dụng tính giai thừa bằng đệ quy nhưng không định nghĩa rõ trường hợp dừng đối với đầu vào âm, khiến ngăn xếp lời gọi tăng cho đến khi lỗi; hãy đặt tình huống xác định điều kiện cơ sở.
Một chương trình duyệt cấu trúc thư mục bằng đệ quy nhưng gặp liên kết vòng và tiếp tục gọi chính nó không giới hạn, khiến ứng dụng mất khả năng phản hồi; hãy xây dựng tình huống đánh giá tiến triển đệ quy.
Một ứng dụng muốn tính số Fibonacci cho N lớn bằng đệ quy trực tiếp và thời gian xử lý tăng đột biến dù kết quả đúng với N nhỏ; hãy đặt tình huống đánh giá chi phí lời gọi.
Một phương thức xử lý danh sách số dùng varargs nhưng caller truyền một mảng có phần tử null, khiến phép tính không phản ánh dữ liệu đầu vào; hãy đặt tình huống kiểm tra hợp đồng phần tử.
Một tiện ích console có nhiều phương thức tự đọc System.in trong khi caller cũng đang đọc đầu vào, khiến một số dòng bị tiêu thụ ngoài dự kiến; hãy xây dựng tình huống phân chia trách nhiệm.
Một chương trình xác thực tuổi gọi phương thức kiểm tra ở hai thời điểm với dữ liệu có thể thay đổi, khiến kết quả từ hai bước không nhất quán; hãy đặt tình huống đánh giá trạng thái và tác dụng phụ.
Một lớp toán học có phương thức dùng biến static để giữ kết quả trung gian, khiến hai lời gọi liên tiếp cho đầu vào giống nhau nhưng trả giá trị khác; hãy xây dựng tình huống kiểm tra tính độc lập.
Một nhóm chuyển đoạn xử lý phí vận chuyển sang phương thức riêng nhưng đặt tham số và kiểu trả về không biểu đạt trường hợp địa chỉ giao hàng thiếu dữ liệu; hãy đặt tình huống xác định hợp đồng lỗi.
Một ứng dụng phân tích chuỗi cần tách bước chuẩn hóa, kiểm tra và lưu dữ liệu nhưng mọi thao tác đang nằm trong main dài hàng trăm dòng; hãy đặt tình huống thiết kế trách nhiệm phương thức.
Một chương trình dùng tên phương thức giống nhau cho cả tính toán và ghi file, khiến caller không biết lời gọi có làm thay đổi trạng thái bên ngoài; hãy đặt tình huống đánh giá khả năng hiểu và kiểm thử.
Một API nội bộ truyền nhiều tham số cùng kiểu String vào phương thức tạo đơn và một lời gọi đảo vị trí số điện thoại với mã bưu chính mà compiler không phát hiện; hãy xây dựng tình huống kiểm tra hợp đồng.
Một chương trình so sánh tên hai khách hàng bằng toán tử tham chiếu và chỉ sai khi chuỗi được đọc từ bàn phím thay vì literal trong mã nguồn; hãy đặt tình huống kiểm chứng so sánh String.
Một ứng dụng nối thêm dòng CSV bằng toán tử cộng chuỗi trong vòng lặp hàng triệu lần, khiến thời gian chạy và lượng object tạm tăng mạnh; hãy xây dựng tình huống đánh giá xử lý chuỗi.
Một hệ thống xử lý số lượng và giá tiền từ text nhưng nối hai chuỗi trước khi chuyển thành số, khiến tổng hóa đơn mang ý nghĩa ghép ký tự thay vì cộng; hãy đặt tình huống phân biệt kiểu.
Một công cụ kiểm tra tên người dùng từ form nhưng chỉ so sánh với chuỗi rỗng và bỏ qua trường hợp chuỗi toàn dấu cách; hãy đặt tình huống xác định tiêu chí dữ liệu trống.
Một ứng dụng đọc tên khách hàng nhưng không kiểm tra null trước khi gọi phương thức chuỗi, khiến trường hợp không cung cấp họ tên làm chương trình dừng; hãy xây dựng tình huống validation.
Một hệ thống chuẩn hóa tên hiển thị bằng một phương thức trên String nhưng không gán lại kết quả, khiến giá trị gốc vẫn được lưu vào cơ sở dữ liệu; hãy đặt tình huống đánh giá tính bất biến.
Một chương trình tách tên tệp ở dấu chấm bằng thao tác split dùng biểu thức chính quy, khiến kết quả không giống mong đợi vì dấu chấm có ý nghĩa đặc biệt; hãy đặt tình huống kiểm tra quy tắc tách.
Một ứng dụng nhập danh sách sản phẩm từ CSV nhưng phương thức split bỏ một số cột rỗng ở cuối dòng, khiến số cột không khớp header; hãy xây dựng tình huống kiểm chứng dữ liệu thiếu.
Một dịch vụ tìm ký tự phân cách trong một chuỗi rồi dùng kết quả indexOf làm vị trí bắt đầu cắt chuỗi, nhưng ký tự không tồn tại và phép cắt gây lỗi; hãy đặt tình huống xử lý không tìm thấy.
Một công cụ rút gọn tiêu đề bằng substring với chiều dài cố định, khiến tiêu đề quá ngắn dẫn đến StringIndexOutOfBoundsException; hãy đặt tình huống kiểm tra ranh giới.
Một ứng dụng tìm từ khóa trong nội dung văn bản nhưng phân biệt chữ hoa chữ thường ngoài ý muốn, khiến nhiều kết quả hợp lệ không được nhận diện; hãy đặt tình huống xác định quy tắc so khớp.
Một hệ thống chuẩn hóa mã sản phẩm bằng toUpperCase nhưng kết quả khác khi môi trường máy chủ dùng Locale có quy tắc chữ hoa đặc biệt; hãy xây dựng tình huống kiểm tra phụ thuộc Locale.
Một chương trình đếm độ dài mật khẩu bằng String.length nhưng yêu cầu của sản phẩm dựa trên số ký tự hiển thị, khiến dữ liệu Unicode bổ sung bị đếm khác; hãy đặt tình huống phân biệt đơn vị ký tự.
Một bộ xử lý nhập tên tiếng Việt từ hai nguồn có cách mã hóa dấu tổ hợp khác nhau, khiến chuỗi trông giống hệt nhưng không so sánh bằng nhau; hãy xây dựng tình huống đánh giá chuẩn hóa Unicode.
Một ứng dụng đọc câu văn có dấu cách ở đầu và cuối nhưng dùng trim rồi so sánh mà không xem xét một số ký tự khoảng trắng Unicode; hãy đặt tình huống xác định quy tắc làm sạch.
Một chương trình phân tích nhật ký ghép đường dẫn tệp bằng chuỗi nhưng vô tình tạo dấu phân cách không phù hợp với hệ điều hành triển khai; hãy xây dựng tình huống đánh giá xử lý đường dẫn.
Một ứng dụng ghi thông báo có dấu phần trăm bằng cơ chế định dạng chuỗi nhưng chuỗi đầu vào được dùng như mẫu định dạng, khiến quá trình hiển thị bị lỗi; hãy đặt tình huống kiểm tra format string.
Một bộ lọc dữ liệu người dùng dùng replace trên String để loại bỏ ký tự không hợp lệ nhưng vẫn gửi chuỗi ban đầu sang bước lưu, khiến bản ghi không được chuẩn hóa; hãy đặt tình huống xác minh giá trị trả về.
Một chương trình dùng chuỗi số có dấu phẩy thập phân từ người dùng để chuyển trực tiếp sang double, khiến việc parse thất bại dù định dạng hợp lệ theo ngôn ngữ của họ; hãy đặt tình huống kiểm chứng đầu vào.
Một ứng dụng xuất các trường người dùng thành một dòng CSV bằng phép nối dấu phẩy đơn giản, nhưng trường địa chỉ có dấu phẩy làm dữ liệu đọc lại bị lệch cột; hãy đặt tình huống đánh giá định dạng văn bản.
Một hệ thống log toàn bộ chuỗi nhập từ người dùng trước khi kiểm tra, khiến mật khẩu và dữ liệu nhạy cảm xuất hiện trong file log dùng để học và kiểm thử; hãy xây dựng tình huống đánh giá giới hạn thông tin.
Một chương trình nhận câu chứa ký tự xuống dòng nhưng coi mỗi lần gọi đọc một dòng là một câu hoàn chỉnh, khiến nội dung bị chia thành nhiều bản ghi; hãy đặt tình huống xác định hợp đồng nhập liệu.
Một ứng dụng xây dựng URL từ tham số tìm kiếm bằng cách nối String, khiến dữ liệu có dấu cách và ký tự đặc biệt tạo ra đường dẫn không hợp lệ; hãy đặt tình huống kiểm tra xử lý ký tự.
Một hệ thống chuẩn hóa số điện thoại bằng cách loại bỏ dấu gạch nhưng lại chuyển toàn bộ dữ liệu sang kiểu số, khiến ký hiệu cộng đầu mã quốc gia bị mất; hãy xây dựng tình huống đánh giá biểu diễn.
Một chương trình hiển thị tên lớp và mã sản phẩm qua phương thức toString mặc định, khiến log không cung cấp giá trị nghiệp vụ mà chỉ là biểu diễn object; hãy đặt tình huống thiết kế đầu ra.
Một lớp quản lý tài khoản cho phép code bên ngoài sửa trực tiếp trường số dư public, khiến các quy tắc kiểm tra giao dịch bị bỏ qua; hãy xây dựng tình huống xác định mức đóng gói.
Một ứng dụng khởi tạo đối tượng SinhVien nhưng constructor không kiểm tra mã học sinh và ngày sinh, khiến nhiều instance không có trạng thái hợp lệ; hãy đặt tình huống đánh giá trách nhiệm khởi tạo.
Một lớp HoaDon có constructor nhận nhiều tham số cùng kiểu và người gọi truyền nhầm địa chỉ với mã thuế, khiến dữ liệu lưu sai mà không có lỗi biên dịch; hãy đặt tình huống kiểm chứng hợp đồng constructor.
Một hệ thống quản lý sản phẩm dùng nhiều constructor nhưng một overload không khởi tạo giá trị mặc định cần thiết, khiến đối tượng hoạt động khác tùy cách tạo; hãy xây dựng tình huống kiểm tra nhất quán.
Một ứng dụng có danh sách người dùng trong trường static và mọi instance dịch vụ đều chia sẻ cùng dữ liệu, khiến thông tin từ các phiên kiểm thử bị lẫn nhau; hãy đặt tình huống phân biệt static và instance.
Một chương trình tạo hai object tài khoản rồi gán một biến tham chiếu sang object còn lại, khiến việc sửa một tài khoản ảnh hưởng kết quả quan sát qua biến kia; hãy đặt tình huống phân tích aliasing.
Một lớp quản lý điểm cung cấp getter trả trực tiếp mảng điểm nội bộ, khiến code gọi có thể thay đổi điểm mà không qua phương thức cập nhật; hãy đặt tình huống đánh giá bảo vệ trạng thái.
Một hệ thống khởi tạo đối tượng địa chỉ bằng constructor mặc định nhưng bỏ trống mã quốc gia, trong khi mọi thao tác vận chuyển đều giả định mã này tồn tại; hãy xây dựng tình huống kiểm tra bất biến.
Một ứng dụng chứa nhiều trường của khách hàng trong một lớp nhưng những phương thức quản lý thanh toán cũng sửa trực tiếp thông tin địa chỉ, khiến khó phân định trách nhiệm; hãy đặt tình huống thiết kế lớp cơ bản.
Một chương trình định nghĩa hai lớp User ở hai package khác nhau nhưng dùng wildcard import của cả hai, khiến compiler không xác định được User đang được tham chiếu; hãy đặt tình huống kiểm chứng import.
Một dự án chuyển một lớp sang package mới nhưng các file nguồn khác vẫn import đường dẫn cũ, khiến biên dịch đa module thất bại; hãy đặt tình huống kiểm tra cập nhật cấu trúc package.
Một lớp tiện ích có thành viên package-private được gọi từ package khác, khiến code không biên dịch dù cả hai cùng thuộc một dự án; hãy xây dựng tình huống phân biệt giới hạn truy cập.
Một nhóm đặt tất cả các lớp vào default package để làm bài thực hành, nhưng khi kết nối với dự án có named package việc tham chiếu lớp trở nên khó khăn; hãy đặt tình huống đánh giá tổ chức.
Một ứng dụng dùng package đặt tên trùng với một package của thư viện tiêu chuẩn và import thiếu rõ ràng, khiến người học chọn sai kiểu dữ liệu; hãy xây dựng tình huống xác minh định danh đầy đủ.
Một chương trình tạo một lớp cha và một lớp con để chia sẻ hành vi, nhưng lớp con viết phương thức gần giống chữ ký của lớp cha và không thực sự override; hãy đặt tình huống kiểm tra tính đa hình.
Một hệ thống lưu các object của nhiều lớp con trong mảng kiểu lớp cha nhưng logic gọi lại truy cập trực tiếp trường riêng của từng lớp con, khiến code không biên dịch; hãy đặt tình huống phân biệt kiểu tham chiếu.
Một lớp định nghĩa phương thức static để tính số lượng đối tượng nhưng code ở nơi gọi nghĩ đây là trạng thái của từng instance và cho kết quả không mong muốn; hãy xây dựng tình huống xác định phạm vi.
Một ứng dụng dùng phương thức equals mặc định để so hai object hồ sơ có cùng thông tin, khiến chúng được xem là khác nhau vì được tạo riêng; hãy đặt tình huống đánh giá quy tắc bằng nhau.
Một lớp lưu thông tin thanh toán định nghĩa toString hiển thị toàn bộ số thẻ, khiến log phục vụ kiểm thử chứa dữ liệu nhạy cảm; hãy xây dựng tình huống kiểm tra thiết kế biểu diễn object.
Một ứng dụng có lớp Order giữ trạng thái đã thanh toán nhưng setter công khai vẫn cho phép đổi tổng tiền sau khi thanh toán, khiến dữ liệu không còn nhất quán; hãy đặt tình huống đánh giá đóng gói.
Một module tạo object cấu hình ở nhiều nơi bằng các giá trị khác nhau thay vì dùng một nơi quản lý, khiến hoạt động giữa các màn hình không giống nhau; hãy xây dựng tình huống kiểm tra cách khởi tạo.
Một chương trình dùng vòng lặp tạo hàng nghìn đối tượng nhưng giữ toàn bộ vào trường static dù chỉ dùng từng đối tượng một lần, khiến bộ nhớ tăng không cần thiết; hãy đặt tình huống đánh giá vòng đời.
Một ứng dụng gọi phương thức trên một biến tham chiếu chưa trỏ tới object nào sau khi bỏ qua bước tạo instance, khiến lỗi chỉ xuất hiện với một nhánh menu; hãy đặt tình huống kiểm tra null.
Một hệ thống tạo đối tượng tệp đính kèm trong constructor nhưng thao tác đọc file có thể thất bại, khiến trạng thái object khởi tạo dở dang chưa có quy tắc xử lý; hãy xây dựng tình huống thiết kế.
Một công cụ nhập thông tin khách hàng đọc tuổi từ bàn phím và người dùng gõ chữ thay vì số, khiến quá trình chuyển kiểu ném NumberFormatException; hãy đặt tình huống xác định cách phản hồi đầu vào sai.
Một chương trình xử lý danh sách sinh viên bắt ArrayIndexOutOfBoundsException bằng cách trả kết quả rỗng, khiến lỗi tính chỉ số bị che và báo cáo sai mà không có cảnh báo; hãy đặt tình huống đánh giá xử lý lỗi.
Một dịch vụ console bắt mọi Exception rồi in duy nhất thông báo không thành công, khiến người bảo trì không xác định được lỗi file, lỗi parse hay lỗi lập trình; hãy đặt tình huống thiết kế thông tin chẩn đoán.
Một ứng dụng đọc file dữ liệu có thể không tồn tại nhưng chương trình chưa phân biệt lỗi thiếu file với lỗi sai nội dung, khiến người dùng không biết cách khắc phục; hãy xây dựng tình huống phân loại ngoại lệ.
Một chương trình có nhiều khối catch nhưng đặt loại ngoại lệ rộng ở trước loại cụ thể, khiến code sau đó không thể biên dịch; hãy đặt tình huống kiểm tra thứ tự nhánh xử lý.
Một ứng dụng dùng finally để đóng file nhưng đóng tài nguyên lại ném lỗi, khiến ngoại lệ gốc khi đọc dữ liệu không còn dễ nhận biết; hãy xây dựng tình huống đánh giá quá trình dọn dẹp.
Một ứng dụng đọc nhiều file trong một lần xử lý nhưng chỉ đóng tài nguyên ở nhánh thành công, khiến số file descriptor tăng khi gặp dữ liệu không hợp lệ; hãy đặt tình huống kiểm tra vòng đời tài nguyên.
Một chương trình mở file rồi chuyển dữ liệu thành số, nhưng một dòng sai định dạng gây ngoại lệ và file reader không được đóng; hãy đặt tình huống đánh giá quản lý tài nguyên khi thất bại.
Một công cụ nhập điểm bằng Scanner nhận số nguyên rồi đọc tên học sinh bằng phương thức đọc dòng, nhưng lời gọi sau nhận chuỗi rỗng vì dấu xuống dòng còn lại; hãy đặt tình huống phân tích bộ đệm nhập.
Một chương trình nhận dữ liệu từ System.in nhưng một phương thức phụ đóng Scanner sau khi dùng, khiến chức năng menu tiếp theo không thể đọc thêm từ bàn phím; hãy xây dựng tình huống kiểm tra sở hữu nguồn nhập.
Một ứng dụng đọc file văn bản bằng encoding mặc định của hệ điều hành, khiến tên tiếng Việt hiển thị đúng trên máy lập trình nhưng lỗi ký tự khi triển khai; hãy đặt tình huống đánh giá charset.
Một chương trình ghi thông báo ra file bằng writer nhưng không đóng hoặc flush trước khi thoát bất thường, khiến một phần dữ liệu chưa xuất hiện trên đĩa; hãy xây dựng tình huống kiểm tra tính đầy đủ.
Một hệ thống ghi file báo cáo mỗi ngày nhưng luôn mở ở chế độ ghi đè, khiến dữ liệu của các lần chạy trước bị mất thay vì được nối tiếp; hãy đặt tình huống xác định yêu cầu lưu trữ.
Một công cụ đọc danh sách từ file bằng vòng lặp nhưng không xử lý kết thúc file đúng cách, khiến dòng cuối bị bỏ qua hoặc dòng trước được xử lý hai lần; hãy xây dựng tình huống kiểm chứng EOF.
Một ứng dụng nhập CSV với dòng trống xen giữa các bản ghi, nhưng vòng đọc coi dòng trống là dấu kết thúc file và bỏ sót các bản ghi còn lại; hãy đặt tình huống phân biệt dữ liệu với EOF.
Một chương trình giả định file luôn có dòng header, khiến file rỗng gây lỗi truy cập khi lấy tên cột; hãy đặt tình huống xác định hành vi với đầu vào không có dữ liệu.
Một service nhỏ tạo đường dẫn file đầu ra từ tên người dùng nhập nhưng không kiểm tra các thành phần đường dẫn, khiến dữ liệu có thể được ghi ngoài thư mục dự định; hãy đặt tình huống đánh giá giới hạn.
Một ứng dụng chạy trên môi trường chỉ cho phép đọc thư mục triển khai nhưng cố ghi kết quả vào đó, khiến thao tác file thất bại dù đường dẫn tồn tại; hãy đặt tình huống kiểm tra quyền ghi.
Một chương trình xử lý file log lớn bằng cách đọc toàn bộ nội dung thành một String, khiến bộ nhớ tăng vượt giới hạn khi log kéo dài; hãy đặt tình huống đánh giá cách nhập dữ liệu.
Một ứng dụng chỉ kiểm tra rằng đường dẫn tồn tại trước khi đọc file, nhưng đường dẫn thực tế là thư mục, khiến thao tác đọc không thành công; hãy đặt tình huống xác định điều kiện mở file.
Một công cụ ghi bảng điểm ra file bằng dấu xuống dòng chỉ phù hợp một hệ điều hành, khiến đối tác dùng nền tảng khác đọc sai các dòng; hãy xây dựng tình huống kiểm tra tính di động.
Một ứng dụng xuất số tiền và ngày vào file văn bản bằng cấu hình locale mặc định của máy, khiến công cụ xử lý file trên server khác không parse đúng; hãy đặt tình huống đánh giá định dạng dữ liệu.
Một chương trình ghi file cấu hình rồi đọc lại ngay nhưng hệ thống có một nhánh lỗi chưa đóng writer, khiến dữ liệu đọc lại chưa phản ánh nội dung mới; hãy đặt tình huống kiểm tra đồng bộ I/O.
Một công cụ nhỏ cần phân biệt lỗi do đầu vào không hợp lệ và lỗi do hệ thống không thể ghi file, nhưng mọi nhánh đều trả cùng một mã kết thúc; hãy đặt tình huống đánh giá hợp đồng CLI.
Một ứng dụng nhập mã số học sinh từ console và chuyển nó sang số nguyên, khiến các mã có số không ở đầu bị biến đổi sau khi xuất ra file; hãy đặt tình huống kiểm tra bảo toàn định dạng.
Một chương trình tính điểm trung bình từ file dữ liệu nhưng một dòng thiếu cột làm phép truy cập mảng thất bại và toàn bộ quá trình xử lý bị hủy; hãy xây dựng tình huống xác định cách xử lý bản ghi lỗi.
Một ứng dụng cung cấp menu thêm, sửa và xem sản phẩm nhưng chưa tách xử lý input, tính toán và in kết quả, khiến một thay đổi hiển thị làm lỗi phép tính; hãy đặt tình huống thiết kế trách nhiệm cơ bản.
Một nhóm kiểm thử chương trình tính tiền chỉ dùng đơn hàng có số lượng dương, khiến lỗi với số không, số âm và giá trị cực lớn chỉ được phát hiện sau khi bàn giao; hãy xây dựng tình huống lập bộ test biên.
Một chương trình đọc điểm từ file và tự động xếp loại nhưng chưa kiểm tra các trường hợp điểm đúng ở ngưỡng chuyển hạng, khiến học sinh nhận kết quả không nhất quán; hãy đặt tình huống kiểm thử điều kiện.
Một ứng dụng console tính cước điện theo bậc giá nhưng dùng số thực cho mọi phép tính và không xác định quy tắc làm tròn, khiến số tiền khác trên các máy; hãy xây dựng tình huống nghiệm thu kết quả.
Một hệ thống quản lý thư viện nhỏ dùng mảng sách, phương thức tìm kiếm và nhập liệu console nhưng khi xóa sách giữa mảng các phần tử phía sau vẫn giữ vị trí cũ; hãy đặt tình huống kiểm tra cập nhật danh sách.
Một chương trình đặt lịch hẹn nhận ngày và giờ dưới dạng String rồi kiểm tra bằng cách so sánh chữ cái, khiến thời gian không theo cùng định dạng được xếp sai; hãy xây dựng tình huống đánh giá dữ liệu nhập.
Một ứng dụng tính hóa đơn từ nhiều dòng sản phẩm có thể thiếu giá hoặc số lượng, nhưng chương trình vẫn chạy phép toán trên giá trị mặc định bằng không; hãy đặt tình huống xác định quy tắc xác nhận.
Một công cụ chấm công nhận dữ liệu từ nhiều file và xuất báo cáo chung, nhưng file đầu tiên hợp lệ còn file thứ hai lỗi encoding khiến kết quả xuất dở dang; hãy đặt tình huống thiết kế kiểm tra luồng xử lý.
Một nhóm phát hành ứng dụng Java console cho người không dùng IDE nhưng thiếu hướng dẫn JDK/runtime, tham số khởi động và vị trí file đầu vào, khiến lỗi vận hành bị hiểu nhầm là lỗi thuật toán; hãy đặt tình huống xác định tiêu chí bàn giao.
Một khóa học yêu cầu người học tự viết ứng dụng quản lý đơn hàng bằng lớp, mảng, phương thức, điều kiện, ngoại lệ và đọc ghi file, nhưng bản hiện tại chưa có kiểm thử cho đầu vào thiếu, sai kiểu và ranh giới số; hãy xây dựng tình huống nghiệm thu tổng thể.
