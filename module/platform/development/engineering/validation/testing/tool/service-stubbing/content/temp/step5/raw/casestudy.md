Một dịch vụ đặt hàng Java gọi API tính phí vận chuyển của đối tác theo mã bưu chính; môi trường thử nghiệm thường xuyên mất kết nối nên nhóm cần kiểm tra quy tắc tính tổng đơn mà không phụ thuộc endpoint thật.
Nhóm dùng WireMock giả lập API tra cứu khách hàng theo đường dẫn có customerId, nhưng stub khớp mọi đường dẫn cùng tiền tố nên request tới khách hàng khác vẫn nhận một hồ sơ cố định.
Ứng dụng tìm chuyến bay gửi tham số ngày đi và điểm đến qua query string; stub hiện chỉ kiểm tra path nên trả cùng kết quả khi người dùng đổi ngày hoặc thành phố.
Một endpoint bên ngoài yêu cầu header phiên bản và token xác thực; bộ kiểm thử dùng MockServer chỉ ghép phương thức và URL, khiến request thiếu header vẫn nhận phản hồi thành công.
Trong hệ thống thanh toán, cùng đường dẫn được gọi bằng GET để đọc trạng thái và POST để tạo giao dịch; hai expectation giả lập không phân biệt HTTP method nên kiểm thử bỏ sót request sai.
Dịch vụ khuyến mãi gửi JSON chứa mã sản phẩm và số lượng; nhóm cấu hình stub so sánh nguyên chuỗi body nên payload có cùng ý nghĩa nhưng thứ tự thuộc tính khác bị từ chối.
Một API đặt chỗ yêu cầu số lượng ghế từ một đến bốn; stub trả thành công cho mọi JSON chứa trường quantity nên không tái hiện được phản hồi từ chối với giá trị ngoài phạm vi.
Ứng dụng tích hợp dịch vụ trả về danh sách sản phẩm; nhóm muốn giả lập hai kết quả theo mã cửa hàng nhưng expectation tổng quát luôn được chọn trước expectation dành riêng cho một cửa hàng.
Một mô phỏng API phân trang trả cùng danh sách ở mọi trang; chức năng tổng hợp dữ liệu của client vượt qua kiểm thử dù bị lặp dữ liệu khi yêu cầu page tiếp theo.
Trong quy trình xác thực, request đầu nhận challenge và request sau phải gửi challengeId vừa phát hành; stub trả một chuỗi phản hồi tĩnh nên không phát hiện việc client sử dụng ID từ phiên trước.
Dịch vụ phát hành vé gọi tạo thanh toán rồi truy vấn trạng thái; trong thực tế trạng thái chuyển từ PENDING sang PAID, nhưng mock hiện trả PAID ngay lần đầu khiến luồng chờ chưa được kiểm thử.
Ứng dụng thương mại cần thử quy trình thanh toán thất bại sau khi đã tạo đơn; bộ giả lập chỉ có kịch bản luôn thành công nên không thể quan sát hành vi hủy đặt chỗ khi bước cuối lỗi.
Một nhóm dùng scenario state của WireMock cho quy trình đăng ký giao hàng; các ca test chạy nối tiếp mà không đặt lại trạng thái, dẫn đến ca sau nhận bước phản hồi của ca trước.
Trong kiểm thử đặt hàng song song, nhiều request cùng truy cập một stub có trạng thái dùng chung; các luồng thay đổi trạng thái theo thứ tự không dự đoán được và bài test lúc xanh lúc đỏ.
Dịch vụ thuế bên ngoài có thể trả HTTP 400 cho mã vùng không hỗ trợ; giả lập hiện trả HTTP 200 với trường error nên phía gọi không đi vào nhánh xử lý lỗi HTTP đã thiết kế.
Một API đối tác có thể phản hồi HTTP 429 kèm thời gian cần chờ; bộ test dùng stub chỉ trả lỗi 500 và không phân biệt logic điều tiết tải với logic retry lỗi máy chủ.
Ứng dụng ngân hàng gọi dịch vụ chống gian lận và phải dừng giao dịch khi nhận HTTP 503; nhóm đang dùng stub lỗi nhưng không mô phỏng được trường hợp mất kết nối trước khi có HTTP response.
Service tổng hợp giá gọi ba nhà cung cấp; một nhà cung cấp có độ trễ 8 giây trong khi hai nguồn khác nhanh, nhưng stub trả ngay khiến bài kiểm tra timeout và fallback chưa bao giờ thực hiện.
Trong hệ thống thông báo, API đối tác đôi khi đóng kết nối giữa chừng khi trả JSON; bộ kiểm thử chỉ giả lập status lỗi hoàn chỉnh nên không kiểm tra cách client xử lý response bị cắt.
Ứng dụng tải file báo cáo từ dịch vụ khác và đọc response theo luồng; stub trả nội dung nhỏ trong một lần, khiến lỗi ở nhánh nhận payload lớn hoặc chậm chưa được phát hiện.
Một REST client gửi cùng yêu cầu lần thứ hai sau timeout; mô phỏng đối tác luôn thành công ngay lần đầu nên tính đúng đắn của số lần retry và giới hạn retry chưa được quan sát.
Nhóm dùng MockServer để xác minh request tạo giao dịch được gửi đúng một lần; bài test vẫn PASS khi mã ứng dụng gửi thêm request âm thầm đến endpoint khác của cùng đối tác.
Trong luồng đăng ký bảo hiểm, ứng dụng phải gọi kiểm tra hồ sơ trước khi phát hành hợp đồng; bộ kiểm thử chỉ đếm mỗi request mà không xác minh thứ tự hai tương tác phụ thuộc.
Ứng dụng chuyển khoản gửi header Idempotency-Key mỗi lần thử lại; stub trả thành công cho mọi request và nhóm chưa kiểm tra khóa có được giữ nguyên qua các lần retry hay không.
Một client truyền số tiền bằng đơn vị nhỏ nhất của tiền tệ; expectation chỉ kiểm tra HTTP 200 mà không xác minh payload gửi đi nên lỗi nhân số tiền lên 100 lần không bị phát hiện.
Trong hệ thống đa tenant, token từ khách hàng A vô tình được dùng khi gọi dịch vụ của tenant B; stub không đối chiếu header tenantId với dữ liệu request nên bài tích hợp vẫn xanh.
Đội tích hợp một API tra cứu hàng tồn có schema mới; file stub giữ cấu trúc JSON của bản cũ và client PASS với mock nhưng lỗi deserialization khi thử với môi trường đối tác.
Một đối tác bổ sung giá trị enum chưa được công bố vào response; test với stub chỉ dùng hai trạng thái cũ nên ứng dụng Java không bộc lộ nhánh không nhận diện trạng thái.
Nhóm tạo fixture cho phản hồi chứa tên người dùng tiếng Việt, dấu nháy kép và ký tự xuống dòng; file JSON stub viết tay bị lỗi escaping và trả payload khác dữ liệu định kiểm thử.
Trong một hợp đồng API, trường địa chỉ có thể vắng mặt hoặc mang null; stub luôn gửi chuỗi rỗng nên không tái hiện được hai cách biểu diễn mà consumer xử lý khác nhau.
Ứng dụng có endpoint gọi thanh toán và sau đó nhận callback bất đồng bộ; mock HTTP trả PAID nhưng không có callback, khiến kịch bản trạng thái cuối khác với tích hợp thực.
Trong hệ thống chuyển phát, đối tác gửi webhook trùng sau khi chưa nhận xác nhận; nhóm dùng stubbing chỉ để trả response cho API gọi ra và chưa kiểm thử được sự kiện trả về từ phía ngoài.
Nhóm viết kiểm thử Java chạy với WireMock trên một cổng cố định; hai job CI chạy song song cùng máy và một job kết nối nhầm stub của job còn lại.
Một bộ test dùng MockServer và tái sử dụng cùng instance giữa nhiều lớp; expectation của lớp cũ vẫn còn khiến lớp sau nhận phản hồi không thuộc dữ liệu mình chuẩn bị.
Service chạy trong container gọi mock qua localhost theo cấu hình từ laptop; khi chuyển sang Docker Compose, địa chỉ đó trỏ vào chính container ứng dụng thay vì máy chứa stub.
Pipeline CI khởi động service Java trước khi WireMock sẵn sàng nhận request; một số bài tích hợp lỗi connection refused ngay đầu lượt chạy dù không có thay đổi logic.
Nhóm lưu phản hồi mẫu đã ghi lại từ đối tác trong repository; mẫu chứa email và số tài khoản thật nên dữ liệu kiểm thử có nguy cơ làm lộ thông tin khi chạy CI.
Ứng dụng dùng HTTPS để gọi dịch vụ đối tác nhưng môi trường giả lập chỉ phục vụ HTTP; việc tạm tắt xác minh chứng chỉ trong client test dẫn đến khác biệt lớn với cấu hình triển khai.
Đội phát triển dùng record-and-playback để có stub mới nhanh, nhưng phản hồi chứa mã giao dịch động và dấu thời gian từ một lần chạy cũ nên kiểm thử thất bại vào ngày khác.
Sau khi cập nhật client Java, mọi kiểm thử với WireMock vẫn PASS nhưng hợp đồng thực tế đã đổi; nhóm chưa phân biệt kiểm tra hành vi ứng dụng với xác minh độ chính xác của bộ giả lập so với provider.
