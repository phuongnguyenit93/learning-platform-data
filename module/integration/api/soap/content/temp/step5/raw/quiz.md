Câu 1. Trong một thông điệp SOAP, phần tử XML nào đóng vai trò bao ngoài cùng?
A. Header bao bọc phần Body và nội dung trả về
B. Body bao bọc Envelope và phần Header
C. Envelope bao bọc các thành phần SOAP
D. Fault bao bọc toàn bộ XML của thông điệp
Đáp án đúng: C

Câu 2. Trong SOAP Envelope, phần tử nào là bắt buộc để chứa nội dung xử lý chính?
A. Header chứa toàn bộ payload và tham số nghiệp vụ
B. Fault chứa mọi yêu cầu gửi đến dịch vụ SOAP
C. Body mang payload nghiệp vụ hoặc SOAP Fault
D. Detail chứa cả thông điệp gửi và nhận qua SOAP
Đáp án đúng: C

Câu 3. SOAP Header thường được dùng nhằm mục đích nào?
A. Quy định schema XSD cho dữ liệu trong SOAP Body
B. Mang metadata cho xác thực và định tuyến
C. Thay thế toàn bộ phần payload trong SOAP Body
D. Chứa địa chỉ vật lý của endpoint trong WSDL
Đáp án đúng: B

Câu 4. Giữa SOAP 1.1 và SOAP 1.2, nhận định nào đúng về namespace của Envelope?
A. Mỗi phiên bản định nghĩa một namespace Envelope riêng
B. Cả hai phiên bản chia sẻ một namespace Envelope duy nhất
C. Chỉ phần Header có namespace riêng theo mỗi phiên bản
D. Namespace Envelope được lấy từ tên service trong WSDL
Đáp án đúng: A

Câu 5. Trong XML có namespace, hai phần tử được nhận diện theo yếu tố nào?
A. Cặp tiền tố namespace và local name của phần tử
B. Cặp namespace URI và local name của phần tử
C. Cặp namespace URI và tiền tố được dùng trong XML
D. Cặp local name và đường dẫn xuất hiện trong XML
Đáp án đúng: B

Câu 6. Khi dịch vụ SOAP trả về lỗi theo chuẩn giao thức, SOAP Fault được đặt ở đâu?
A. Trong phần Header của thông điệp SOAP phản hồi
B. Trong phần types của hợp đồng WSDL dịch vụ
C. Trong phần binding của hợp đồng WSDL dịch vụ
D. Trong phần Body của thông điệp SOAP phản hồi
Đáp án đúng: D

Câu 7. Với SOAP 1.1, cặp trường Fault nào mô tả mã lỗi và lý do lỗi?
A. faultcode và faultstring trong SOAP Fault
B. Code cùng Reason trong phần tử Fault
C. MessageID cùng Action trong phần tử Fault
D. status cùng description trong phần tử Fault
Đáp án đúng: A

Câu 8. Với SOAP 1.2, cặp thành phần nào thể hiện mã lỗi và lý do lỗi?
A. faultcode và faultstring thuộc SOAP Fault
B. Action và ReplyTo thuộc nội dung SOAP Fault
C. Code và Reason trong phần tử SOAP Fault
D. status và description thuộc SOAP Fault
Đáp án đúng: C

Câu 9. Trong SOAP 1.2, Fault Code mang giá trị Sender thường báo hiệu điều gì?
A. Bên nhận tạm thời không thể xử lý yêu cầu hợp lệ
B. Thông điệp gửi đến có vấn đề cần phía gửi xử lý
C. Đường truyền đã mã hóa sai chứng chỉ của máy chủ
D. Endpoint đã nhận phản hồi sau khi hết thời gian chờ
Đáp án đúng: B

Câu 10. Khi gửi SOAP 1.2 qua HTTP, Content-Type thường dùng là gì?
A. text/xml cho thông điệp SOAP 1.2
B. application/json cho thông điệp SOAP 1.2
C. application/soap+xml cho thông điệp SOAP 1.2
D. application/wsdl+xml cho thông điệp SOAP 1.2
Đáp án đúng: C

Câu 11. Trong SOAP 1.1 trên HTTP, header SOAPAction chủ yếu cung cấp thông tin nào?
A. Ý định của lời gọi SOAP đối với bên nhận HTTP
B. Phiên bản của XSD dùng để kiểm tra payload XML
C. Địa chỉ schema dùng để giải mã SOAP Envelope
D. Tên chứng chỉ dùng để xác thực kết nối TLS
Đáp án đúng: A

Câu 12. Trong WSDL 1.1, thành phần types có vai trò nào?
A. Liệt kê địa chỉ endpoint đang triển khai dịch vụ
B. Gắn mỗi thao tác trừu tượng với một địa chỉ HTTP
C. Khai báo operation cùng các message vào và ra
D. Khai báo kiểu dữ liệu dùng trong các thông điệp
Đáp án đúng: D

Câu 13. Trong WSDL 1.1, thành phần message chủ yếu biểu diễn điều gì?
A. Nội dung dữ liệu trừu tượng trao đổi qua operation
B. Địa chỉ máy chủ thực tế phục vụ HTTP request
C. Danh sách phương thức Java được triển khai ở server
D. Chính sách ký số thông điệp theo WS-Security
Đáp án đúng: A

Câu 14. Trong WSDL 1.1, portType dùng để khai báo điều gì?
A. Các endpoint cụ thể và chứng chỉ TLS cần dùng
B. Các operation trừu tượng và thông điệp vào ra
C. Các lược đồ dữ liệu và ràng buộc XML Schema
D. Các thiết lập thời gian chờ khi kết nối mạng
Đáp án đúng: B

Câu 15. Trong WSDL 1.1, binding bổ sung thông tin nào cho portType?
A. Cách kết nối các kiểu XSD với kiểu dữ liệu Java
B. Cách kiểm tra các bước xác thực người sử dụng
C. Cách ánh xạ operation vào giao thức và định dạng
D. Cách định tuyến mỗi yêu cầu tới máy chủ dự phòng
Đáp án đúng: C

Câu 16. Trong WSDL 1.1, thành phần service mô tả điều gì?
A. Một tập hợp kiểu dữ liệu XML dùng trong request
B. Một tập hợp lớp Java để xử lý SOAP Envelope
C. Một tập hợp port cho các endpoint của dịch vụ
D. Một tập hợp tài khoản cần quyền truy cập endpoint
Đáp án đúng: C

Câu 17. Trong WSDL 1.1, port kết hợp những thông tin chính nào?
A. Một message trừu tượng và schema cho dữ liệu trả về
B. Một kiểu dữ liệu và chính sách bảo mật của dịch vụ
C. Một operation trừu tượng và mã lỗi phía server
D. Một binding cụ thể và địa chỉ endpoint của dịch vụ
Đáp án đúng: D

Câu 18. Trong XML Schema, xsd:sequence quy định điều gì?
A. Quyền có mặt của phần tử trong một thông điệp SOAP
B. Tên namespace mặc định cho mọi thuộc tính XML
C. Cách ánh xạ thuộc tính XML sang annotation của Java
D. Thứ tự xuất hiện của các phần tử con được khai báo
Đáp án đúng: D

Câu 19. Trong XSD, minOccurs="0" có ý nghĩa gì đối với một phần tử?
A. Cho phép phần tử vắng mặt trong cấu trúc hợp lệ
B. Bắt buộc phần tử xuất hiện ít nhất một lần
C. Cho phép phần tử nhận giá trị null qua xsi:nil
D. Bắt buộc phần tử xuất hiện đúng hai lần trong XML
Đáp án đúng: A

Câu 20. Trong XSD, maxOccurs="unbounded" tác động như thế nào?
A. Cho phép phần tử vắng mặt dù minOccurs bằng một
B. Cho phép phần tử chứa mọi kiểu dữ liệu bất kỳ
C. Cho phép phần tử lặp lại mà không đặt giới hạn trên
D. Cho phép phần tử bỏ qua mọi ràng buộc về namespace
Đáp án đúng: C

Câu 21. Trong XSD, nillable="true" cho phép XML biểu diễn điều gì?
A. Phần tử hiện diện với giá trị nil qua xsi:nil
B. Phần tử không xuất hiện mà không cần minOccurs
C. Phần tử được phép lặp không giới hạn trong XML
D. Phần tử được phép đổi namespace khi trao đổi
Đáp án đúng: A

Câu 22. Hai XML `<Order xmlns="urn:shop"/>` và `<s:Order xmlns:s="urn:shop"/>` có cùng tên phần tử vì sao?
A. Prefix rỗng được coi là local name của phần tử
B. Cùng namespace URI và local name của phần tử
C. Parser chỉ so local name nếu các prefix khác nhau
D. Default namespace không ảnh hưởng tới tên phần tử
Đáp án đúng: B

Câu 23. Trong XSD, khi tham chiếu định nghĩa từ một namespace khác, nên dùng khai báo nào?
A. xs:include để sử dụng schema của namespace khác
B. xs:import để sử dụng schema của namespace khác
C. xs:redefine để tạo namespace khác cho phần tử
D. xs:override để thay thế định nghĩa từ namespace khác
Đáp án đúng: B

Câu 24. Với kiểu SOAP document/literal, phần Body thường được xây dựng theo cách nào?
A. Mang danh sách đối số RPC theo SOAP encoding
B. Mang các chuỗi JSON theo cấu trúc schema XML
C. Mang dữ liệu nhị phân không qua cấu trúc XML
D. Mang các phần tử XML theo schema đã công bố
Đáp án đúng: D

Câu 25. Trong cách tiếp cận contract-first, bước nào nên được thực hiện đầu tiên?
A. Thiết kế WSDL/XSD trước khi triển khai Java
B. Sinh WSDL từ lớp Java sau khi đóng gói ứng dụng
C. Sinh XSD từ lớp JAXB trước rồi mới soạn WSDL
D. Tạo Java DTO trước rồi công bố WSDL từ runtime
Đáp án đúng: A

Câu 26. Với Apache CXF, công cụ wsdl2java thường phục vụ mục đích gì?
A. Sinh WSDL mới từ database đã triển khai
B. Sinh giao diện và kiểu Java dựa trên WSDL
C. Biên dịch XML Schema thành tệp JavaScript
D. Đóng gói trực tiếp yêu cầu SOAP thành HTTP
Đáp án đúng: B

Câu 27. Trong Spring Web Services, @PayloadRoot thường chọn handler bằng cách nào?
A. Ghép HTTP method và URI của endpoint SOAP
B. Ghép namespace và localPart của payload gốc
C. Ghép tên lớp JAXB và cổng mạng đang lắng nghe
D. Ghép SOAPAction và địa chỉ IP của người gọi
Đáp án đúng: B

Câu 28. Trong Spring-WS, @RequestPayload trên tham số endpoint có ý nghĩa gì?
A. Liên kết tham số với payload XML của request
B. Liên kết tham số với HTTP header Authorization
C. Liên kết tham số với địa chỉ endpoint trong WSDL
D. Liên kết tham số với mã trạng thái của SOAP Fault
Đáp án đúng: A

Câu 29. Trong Spring-WS, @ResponsePayload trên phương thức endpoint biểu thị điều gì?
A. Giá trị trả về chỉ dùng để ghi access log của server
B. Giá trị trả về được dùng làm payload của response
C. Giá trị trả về được ghi vào HTTP request header
D. Giá trị trả về chỉ dùng để xuất tài liệu WSDL
Đáp án đúng: B

Câu 30. Trong Spring-WS, WebServiceTemplate thường được dùng cho nhiệm vụ nào?
A. Đăng ký mọi endpoint SOAP vào servlet container
B. Gửi yêu cầu SOAP và nhận kết quả từ dịch vụ ngoài
C. Biên dịch Java thành XML Schema ở bước build
D. Kiểm tra tính hợp lệ của từng tập tin WSDL
Đáp án đúng: B

Câu 31. Trong ứng dụng Java dùng JAX-WS với Apache CXF, annotation nào thường khai báo lớp endpoint?
A. @WebService đánh dấu lớp triển khai dịch vụ SOAP
B. @PayloadRoot đánh dấu lớp triển khai JAX-WS
C. @XmlRootElement đánh dấu lớp endpoint JAX-WS
D. @Controller đánh dấu interface của JAX-WS
Đáp án đúng: A

Câu 32. Với JAXB, quá trình unmarshalling chủ yếu thực hiện thao tác gì?
A. Chuyển đối tượng Java thành chuỗi XML tương ứng
B. Tạo SOAP Fault từ cấu hình timeout của client
C. Chuyển XML Schema thành chính sách WS-Security
D. Chuyển nội dung XML thành đối tượng Java tương ứng
Đáp án đúng: D

Câu 33. Khi bổ sung dữ liệu vào request XSD, thay đổi nào thường không làm hỏng request cũ?
A. Thêm phần tử bắt buộc với minOccurs bằng một
B. Đổi namespace URI của phần tử gốc request
C. Thêm phần tử tùy chọn với minOccurs bằng không
D. Đổi kiểu phần tử từ xsd:string sang xsd:date
Đáp án đúng: C

Câu 34. Trong contract SOAP, tại sao thay namespace URI của phần tử request gốc dễ gây lỗi?
A. Tên đầy đủ của phần tử thay đổi theo namespace
B. Tiền tố XML đổi sẽ làm client không parse được
C. schemaLocation đổi khiến local name tự thay đổi
D. Hợp đồng chỉ so local name, bỏ qua namespace mới
Đáp án đúng: A

Câu 35. Khi server bắt buộc validate theo XSD mới, thay đổi nào dễ khiến XML client cũ không hợp lệ?
A. Thêm phần tử tùy chọn vào kiểu dữ liệu của response
B. Thêm một operation riêng không được client cũ gọi
C. Thêm phần tử bắt buộc vào phần request đang dùng
D. Bổ sung mô tả tài liệu vào tệp schema hiện hữu
Đáp án đúng: C

Câu 36. Trong WS-Security, UsernameToken chủ yếu mang thông tin gì?
A. Địa chỉ các endpoint dự phòng để gọi khi có lỗi
B. Chữ ký số cho mọi byte trong toàn bộ kết nối HTTP
C. Định dạng nén cho các tài liệu XML đính kèm
D. Thông tin danh tính để xác thực người gửi thông điệp
Đáp án đúng: D

Câu 37. Trong WS-Security, XML Signature bảo vệ thuộc tính nào của phần XML được ký?
A. Tính bí mật của phần XML được mã hóa bằng khóa
B. Tính xác thực của phiên TLS tới endpoint nhận
C. Bảo đảm chuyển phát SOAP thông qua sequence ACK
D. Tính toàn vẹn và khả năng xác minh bên ký
Đáp án đúng: D

Câu 38. Trong WS-Security, XML Encryption được dùng chủ yếu để làm gì?
A. Ký xác nhận các phần XML mà server đã xử lý
B. Đồng bộ hóa thứ tự thực hiện operation SOAP
C. Mã hóa các phần XML cần giữ bí mật trong thông điệp
D. Nén văn bản XML trước khi gửi qua giao thức HTTP
Đáp án đúng: C

Câu 39. Để giảm nguy cơ phát lại thông điệp SOAP đã ký, cơ chế nào phù hợp?
A. Kiểm tra Timestamp và lưu dấu định danh đã dùng
B. Chỉ kiểm tra XML có đóng đủ thẻ mở và thẻ đóng
C. Chỉ kiểm tra chứng chỉ TLS chưa hết hạn sử dụng
D. Đổi tên các phần tử XML qua từng lần gửi request
Đáp án đúng: A

Câu 40. Nhận định nào đúng khi so sánh TLS với WS-Security ở mức thông điệp?
A. TLS bảo vệ payload qua nhiều hop; WS-Security bảo vệ một kết nối
B. TLS ký SOAP Body; WS-Security xác thực chứng chỉ phiên TLS
C. TLS bảo vệ chặng truyền; WS-Security bảo vệ nội dung
D. TLS bảo vệ payload khi lưu; WS-Security mã hóa kết nối HTTP
Đáp án đúng: C

Câu 41. Trong WS-Addressing, MessageID và ReplyTo giúp giải quyết nhu cầu nào?
A. Mã hóa XML và xác minh chứng chỉ của người gửi
B. Nhận diện thông điệp và chỉ định nơi nhận phản hồi
C. Ánh xạ schema XSD sang các lớp Java ở client
D. Giới hạn kích thước XML của từng thông điệp
Đáp án đúng: B

Câu 42. WS-Policy thường biểu diễn thông tin nào gắn với dịch vụ SOAP?
A. Địa chỉ máy chủ và địa chỉ IP dự phòng đang hoạt động
B. Yêu cầu và khả năng như cơ chế bảo mật cần hỗ trợ
C. Nội dung nghiệp vụ của các bản ghi dữ liệu gửi lên
D. Lịch sử những lần lỗi khi gửi thông điệp trên mạng
Đáp án đúng: B

Câu 43. Trong WS-ReliableMessaging, chức năng trọng tâm là gì?
A. Gắn MessageID và ReplyTo để định tuyến phản hồi
B. Công bố yêu cầu bảo mật và tính năng cần hỗ trợ
C. Ký SOAP Body để xác minh tính toàn vẹn thông điệp
D. Cung cấp cơ chế đảm bảo chuyển phát thông điệp
Đáp án đúng: D

Câu 44. Khi SOAP cần gửi dữ liệu nhị phân lớn, MTOM thường giúp gì?
A. Mã hóa blob base64 rồi nhúng trực tiếp trong XML
B. Nén toàn bộ SOAP Envelope trước khi gửi HTTP
C. Thay SOAP Body bằng MIME part không còn XML
D. Tối ưu truyền dữ liệu nhị phân gắn với nội dung XML
Đáp án đúng: D

Câu 45. Khi xác minh SOAP response tuân thủ hợp đồng, bước kiểm thử nào hữu ích?
A. Chỉ kiểm tra mã HTTP mà bỏ qua nội dung XML
B. Chỉ kiểm tra tốc độ response của load balancer
C. Validate XML phản hồi bằng XSD của hợp đồng
D. Chỉ kiểm tra file Java được biên dịch thành công
Đáp án đúng: C

Câu 46. Trong kiểm thử tích hợp Java client và SOAP server, cách nào phản ánh giao tiếp thực tế?
A. Chỉ khởi tạo object JAXB mà không gửi SOAP request
B. Chỉ đọc file WSDL và kiểm tra có tên operation
C. Chỉ kiểm tra dữ liệu mock do chính test tự cung cấp
D. Gọi endpoint bằng client sinh từ WSDL và so nội dung
Đáp án đúng: D

Câu 47. Để tìm một lỗi SOAP xuyên qua nhiều dịch vụ, phương án vận hành nào hữu ích?
A. Ghi SOAPAction mỗi hop nhưng bỏ dấu vết request
B. Gắn ID khác nhau mỗi hop mà không truyền ID gốc
C. Dùng correlation ID theo tên service thay vì request
D. Gắn correlation ID vào SOAP Header và log cùng ID
Đáp án đúng: D

Câu 48. Nếu client retry một SOAP operation tạo giao dịch, biện pháp nào giúp tránh thực hiện trùng?
A. Dùng mã yêu cầu duy nhất và kiểm tra trùng phía server
B. Đổi SOAPAction qua mỗi lần gửi lại cùng một request
C. Tạo thêm một WSDL mới sau mỗi lần request bị lỗi
D. Tắt xử lý SOAP Fault trước khi gửi lại giao dịch
Đáp án đúng: A
