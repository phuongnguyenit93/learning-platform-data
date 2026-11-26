Câu 1. Trong quy trình contract-first SOAP, thành phần nào nên được thống nhất trước khi lập trình endpoint?
A. Hợp đồng XSD/WSDL mô tả message và operation
B. Các controller trả JSON tự sinh từ domain entity
C. Các Java DTO do service tự phát hiện lúc runtime
D. Các bảng JPA tạo theo tên thuộc tính DTO
Đáp án đúng: A

Câu 2. XSD đóng vai trò chính nào trong một dịch vụ Spring Web Services?
A. Định tuyến HTTP path tới từng SOAP endpoint bean
B. Cấu hình xác thực username/password WS-Security
C. Khai báo transport binding của SOAP 1.1 trong WSDL
D. Mô tả cấu trúc, kiểu dữ liệu và ràng buộc XML
Đáp án đúng: D

Câu 3. Trong WSDL 1.1, phần binding mô tả nội dung nào?
A. Các cấu trúc complexType và elementFormDefault của XSD
B. Danh sách private key dùng ký SOAP Header tại client
C. Các Java method được Spring MVC ánh xạ bằng URL
D. Cách ánh xạ operation vào protocol và format message
Đáp án đúng: D

Câu 4. Khai targetNamespace trong XSD chủ yếu giúp điều gì?
A. Xác định địa chỉ HTTP thực tế của SOAP service đã deploy
B. Chỉ định mã HTTP trả về khi SOAP Fault được phát sinh
C. Phân biệt các tên XML toàn cục theo namespace của schema
D. Cấu hình nơi client tìm JWK Set để kiểm tra chữ ký
Đáp án đúng: C

Câu 5. Khi một XML element khai minOccurs="0" trong XSD, điều gì được phép?
A. Element phải có giá trị số nguyên bằng 0 khi gửi đi
B. Element có thể không xuất hiện ở vị trí đó trong XML
C. Element phải xuất hiện đúng một lần ở vị trí đã khai
D. Element không được chứa chữ cái Unicode trong nội dung
Đáp án đúng: B

Câu 6. Nếu một XML element có maxOccurs="unbounded", điều gì đúng?
A. Element bắt buộc chỉ xuất hiện đúng một lần trong Body
B. Element chỉ được mang dữ liệu trong SOAP Header
C. Element có thể lặp nhiều lần theo cấu trúc schema
D. Element phải có text rỗng nếu là một complexType
Đáp án đúng: C

Câu 7. xs:sequence trong XML Schema dùng để diễn đạt ràng buộc nào?
A. Thứ tự EndpointInterceptor được đăng ký vào context
B. Thứ tự các Java method được thực thi trong @Endpoint
C. Thứ tự các SOAP Action được trình bày trong WSDL
D. Thứ tự xuất hiện của các phần tử con trong tài liệu XML
Đáp án đúng: D

Câu 8. Khi Spring-WS xét QName của phần tử gốc payload, QName bao gồm những phần nào?
A. Địa chỉ HTTP host và path của SOAP endpoint
B. Tên Java package và class JAXB đã được sinh
C. SOAPAction và mã HTTP status của SOAP response
D. Namespace URI và local name của phần tử XML
Đáp án đúng: D

Câu 9. JAXB marshalling trong SOAP service chủ yếu thực hiện thao tác nào?
A. Biến XML payload thành Java object sau khi nhận
B. Biến Java object thành XML theo mapping JAXB
C. Biến SOAP Fault thành RuntimeException phía client
D. Biến XSD thành WSDL operation trước khi deploy
Đáp án đúng: B

Câu 10. JAXB unmarshalling xử lý theo hướng nào với SOAP payload?
A. Biến Java DTO thành XML response trước khi gửi đi
B. Đọc XML payload thành đối tượng Java có binding phù hợp
C. Biến WSDL operation thành Servlet URL mapping
D. Biến SOAP Header thành TLS certificate của client
Đáp án đúng: B

Câu 11. Jaxb2Marshaller thường được gắn vào SOAP client để phục vụ việc gì?
A. Cung cấp marshaller/unmarshaller cho các JAXB type
B. Sinh WSDL 1.1 trực tiếp từ Java class trong lúc gọi
C. Ánh xạ SOAPAction thành handler method của endpoint
D. Xác minh certificate chain của SOAP request theo X.509
Đáp án đúng: A

Câu 12. Khi JAXB sinh JAXBElement cho một global element, bước nào phù hợp khi marshal?
A. Dùng JAXBElement bao bọc giá trị với QName root tương ứng
B. Loại namespace của global element khỏi JAXB metadata
C. Đổi JAXBElement thành Servlet response header trước gửi
D. Chỉ marshal object bên trong mà bỏ thông tin root element
Đáp án đúng: A

Câu 13. Annotation @Endpoint trong Spring-WS có vai trò gì?
A. Chỉ định SOAP client sẽ gọi URL từ defaultUri
B. Sinh XSD schema từ tất cả Java model đang có
C. Định nghĩa root WSDL binding của mỗi endpoint
D. Đánh dấu bean chứa các handler cho SOAP messages
Đáp án đúng: D

Câu 14. @PayloadRoot(namespace="urn:shop", localPart="GetOrderRequest") ánh xạ dựa vào gì?
A. HTTP URL và method của request tới Spring MVC
B. QName của phần tử payload gốc trong SOAP Body
C. SOAPAction header, không phụ thuộc SOAP payload
D. Tên Java DTO mà JAXB trả về sau unmarshalling
Đáp án đúng: B

Câu 15. @RequestPayload trên tham số endpoint giúp làm gì?
A. Đính kèm SOAPAction header cho outgoing client
B. Khai báo HTTP endpoint URL cho Servlet mapping
C. Chuyển phần payload request vào tham số handler
D. Thiết lập mã SOAP Fault cho một custom exception
Đáp án đúng: C

Câu 16. @ResponsePayload trên method endpoint giúp điều gì?
A. Đưa dữ liệu request vào tham số JAXB method
B. Đưa giá trị trả về vào SOAP response payload
C. Đăng ký schema để validate request trước handler
D. Đặt HTTP response status cho tất cả SOAP Fault
Đáp án đúng: B

Câu 17. Trong cấu hình Spring-WS, @EnableWs thường được dùng để làm gì?
A. Thêm Spring MVC JSON converters cho mọi SOAP request
B. Sinh JAXB DTO từ XSD mỗi lần Spring context start
C. Tự tạo private key X.509 để ký mọi SOAP response
D. Kích hoạt hạ tầng hỗ trợ xử lý Spring Web Services
Đáp án đúng: D

Câu 18. MessageDispatcherServlet thường chịu trách nhiệm nào?
A. Gửi SOAP request đến đối tác từ backend SOAP client
B. Tự sinh WSDL 1.1 từ Java method không qua schema
C. Nhận SOAP HTTP request và giao cho dispatcher xử lý
D. Giải mã XML Signature bằng JPA entity manager
Đáp án đúng: C

Câu 19. Khi dùng @PayloadRoot, hai request cùng localPart nhưng namespace khác nhau được phân biệt thế nào?
A. Chỉ QName khớp cả namespace và localPart mới phù hợp mapping
B. Chỉ localPart được kiểm tra, namespace bị bỏ qua mặc định
C. Chỉ SOAPAction được so sánh, QName không có tác dụng
D. Chỉ HTTP path quyết định method handler của SOAP body
Đáp án đúng: A

Câu 20. DefaultWsdl11Definition thường dùng để làm gì với XSD trong Spring-WS?
A. Xuất OpenAPI 3 JSON từ các DTO của SOAP handler
B. Tạo WSDL 1.1 từ schema theo các quy ước cấu hình
C. Tạo các Java JAXB class từ schema mỗi khi gọi GET
D. Cấp quyền WS-Security cho các WSDL operation mới
Đáp án đúng: B

Câu 21. Nếu WSDL đã được quản lý như một file tĩnh, bean nào phù hợp để công bố?
A. DefaultWsdl11Definition tạo một XSD từ Java endpoint
B. Jaxb2Marshaller đọc file WSDL và sinh Servlet mapping
C. SimpleWsdl11Definition trỏ tới tài nguyên WSDL có sẵn
D. Wss4jSecurityInterceptor tự trả WSDL có sẵn cho client
Đáp án đúng: C

Câu 22. Trong DefaultWsdl11Definition, locationUri thường đi vào thông tin nào của WSDL?
A. Namespace JAXB dùng xác định các phần tử XML request
B. Tên file JKS lưu chứng chỉ của SOAP service nội bộ
C. Danh sách exception resolver được gắn trong application
D. Địa chỉ SOAP service được công bố để client gửi request
Đáp án đúng: D

Câu 23. Muốn validate XML payload theo XSD trước khi endpoint xử lý, interceptor nào phù hợp?
A. PayloadValidatingInterceptor được cấu hình schema và validateRequest
B. SoapActionCallback dùng làm server-side schema validator
C. SimpleWsdl11Definition dùng để validate request mỗi lần gửi
D. WebServiceTemplate tự áp XSD cho mọi inbound endpoint
Đáp án đúng: A

Câu 24. Trước khi phát hành phiên bản XSD/WSDL mới cho đối tác cũ, cần kiểm tra điều gì?
A. Chỉ tên Java class giữ nguyên trong source code backend
B. Chỉ method trả HTTP 200 khi không có SOAP envelope
C. Mọi global XML element đều đổi namespace để phân biệt
D. Hợp đồng request/response có tương thích với client cũ và mới
Đáp án đúng: D

Câu 25. SOAP Body trong Envelope thường chứa thành phần nào?
A. Các chứng chỉ TLS được browser xác minh qua HTTPS
B. Danh sách WSDL definitions dùng để tìm operation
C. Payload nghiệp vụ của request hoặc response SOAP
D. Các thiết lập keep-alive của HTTP connection
Đáp án đúng: C

Câu 26. SOAP Header thường chứa loại dữ liệu nào phù hợp?
A. Metadata như thông tin bảo mật hay định tuyến message
B. Payload nghiệp vụ thay cho nội dung chính trong Body
C. XSD complexType để định nghĩa kiểu của SOAP operation
D. HTTP status code dành cho mọi SOAP Fault xảy ra
Đáp án đúng: A

Câu 27. @SoapAction dùng để ánh xạ SOAP 1.1 request dựa vào thành phần nào?
A. HTTP method POST có hoặc không có query string
B. Giá trị SOAPAction của thông điệp gửi tới
C. Tên biến Java được gắn @RequestPayload trong method
D. Giá trị phần tử xsd:import trong WSDL schema
Đáp án đúng: B

Câu 28. Trong ứng dụng Spring-WS đóng vai SOAP client, lớp nào hỗ trợ gửi nhận message?
A. MessageDispatcherServlet tạo outgoing request từ client
B. WebServiceTemplate thực hiện trao đổi request/response SOAP
C. DefaultWsdl11Definition gửi SOAP envelope tới HTTP endpoint
D. PayloadValidatingInterceptor tự kết nối tới remote service
Đáp án đúng: B

Câu 29. Khi gọi marshalSendAndReceive trên WebServiceTemplate với Java object, cần gì?
A. Controller Spring MVC với @PostMapping trên cùng bean
B. EndpointMapping dựa trên SoapAction của server đối tác
C. Marshaller và unmarshaller phù hợp đã được cấu hình
D. SOAP Fault resolver luôn chuyển object thành DTO mới
Đáp án đúng: C

Câu 30. Muốn sửa SOAP header hoặc SOAPAction trước khi request được gửi, dùng gì?
A. MockWebServiceClient để thay đổi request thực tế lúc chạy
B. SoapFaultMappingExceptionResolver để viết SOAPAction
C. DefaultWsdl11Definition để gắn header cho từng request
D. WebServiceMessageCallback truy cập outgoing message
Đáp án đúng: D

Câu 31. Nếu gọi WebServiceTemplate mà không truyền URI riêng, đích gửi lấy từ đâu?
A. targetNamespace của request JAXB được xem như HTTP URL
B. Tên @Endpoint bean của server mà client đã tải WSDL
C. defaultUri được cấu hình trong SOAP client template
D. Giá trị root element tự được gắn vào DNS hostname
Đáp án đúng: C

Câu 32. WebServiceGatewaySupport giúp thiết kế SOAP client thông qua điều gì?
A. Base class cung cấp WebServiceTemplate để client sử dụng
B. EndpointInterceptor tự khởi tạo HTTP server khi có request
C. SimpleWsdl11Definition tự tạo client stub từ WSDL
D. @PayloadRoot tự đóng vai WebServiceTemplate phía client
Đáp án đúng: A

Câu 33. SOAP Fault được dùng để biểu diễn thông tin nào trong một SOAP response?
A. HTTP redirect tới trang đăng nhập của SOAP client
B. Thông điệp thành công chứa toàn bộ JAXB result
C. Lỗi xử lý theo cấu trúc fault của giao thức SOAP
D. File XSD lỗi được nhúng thay thế SOAP Envelope
Đáp án đúng: C

Câu 34. Trong SOAP 1.1, mã Fault Client thường chỉ ra tình huống nào?
A. Lỗi nội bộ phía server khi xử lý request SOAP hợp lệ
B. Vấn đề phía request gửi đến khiến server không xử lý được
C. SOAP operation thành công nhưng cần chuyển sang HTTPS
D. Kết nối HTTP đang dùng đã được browser cache
Đáp án đúng: B

Câu 35. SoapFaultMappingExceptionResolver hỗ trợ việc gì trên SOAP server?
A. Ánh xạ SOAP Fault thành object Java phía SOAP client
B. Ánh xạ các exception Java thành SOAP Fault tương ứng
C. Ánh xạ XSD thành WSDL binding theo namespace URI
D. Ánh xạ SOAPAction thành method @PayloadRoot tương ứng
Đáp án đúng: B

Câu 36. EndpointInterceptor trong Spring-WS chủ yếu cho phép làm gì?
A. Can thiệp quanh việc xử lý request, response hoặc SOAP Fault
B. Tạo JAXB class từ XSD ngay trong SOAP request hiện tại
C. Thay SOAP Body bằng HTTP URL trước khi endpoint dispatch
D. Đặt số thread tối đa của Servlet container mỗi operation
Đáp án đúng: A

Câu 37. Với SOAP logging interceptor trong hệ thống có dữ liệu cá nhân, biện pháp nào hợp lý?
A. Ghi cả plaintext password token để phân tích signature nhanh
B. Đặt toàn bộ log SOAP vào endpoint public phục vụ đối tác
C. Tắt tất cả chính sách retention và mã hóa log mặc định
D. Che dữ liệu nhạy cảm và giới hạn truy cập các message log
Đáp án đúng: D

Câu 38. Wss4jSecurityInterceptor trong Spring Web Services được dùng cho mục tiêu nào?
A. Bảo vệ toàn bộ REST API với OAuth2 BearerToken filter
B. Sinh JDBC entity từ các UsernameToken claim của SOAP Header
C. Xác minh hoặc bổ sung bảo mật WS-Security ở mức SOAP message
D. Chuyển SOAP document sang JSON cho MVC controller
Đáp án đúng: C

Câu 39. Để xác minh chữ ký WS-Security ở server, cấu hình interceptor nào cần thiết?
A. validationActions có Signature cùng crypto xác minh chữ ký
B. securementActions có Signature nhưng không cần validation
C. validationActions chỉ có Timestamp thay vì Signature
D. PayloadValidatingInterceptor thay thế xác minh public key
Đáp án đúng: A

Câu 40. Khi bật Timestamp trong validationActions của Wss4jSecurityInterceptor, mục đích là gì?
A. Gắn SOAPAction vào outbound request của SOAP client
B. Thay thời gian timeout trong JDBC transaction manager
C. Tạo chứng chỉ X.509 mới mỗi khi nhận SOAP request
D. Kiểm tra thông tin thời gian của message nhận được
Đáp án đúng: D

Câu 41. Với XML Signature và XML Encryption trong WS-Security, phân biệt nào đúng?
A. Chữ ký chỉ mã hóa nội dung; mã hóa chỉ bảo vệ origin
B. Chữ ký áp dụng HTTP Header; mã hóa chỉ áp dụng URL
C. Chữ ký chỉ dùng client; mã hóa chỉ dùng server response
D. Chữ ký xác thực/toàn vẹn; mã hóa bảo vệ tính bí mật
Đáp án đúng: D

Câu 42. Khi xác thực chữ ký SOAP dùng X.509, phía nhận thường cần kiểm tra gì?
A. Public key/chứng chỉ người ký và chính sách tin cậy
B. Private key của bên gửi được trao trong SOAP Header
C. Mật khẩu của domain user đặt trong JAXB annotation
D. Khóa bí mật của HTTP cookie mà client đang giữ
Đáp án đúng: A

Câu 43. TLS và WS-Security XML Signature khác nhau chủ yếu về phạm vi nào?
A. TLS ký XML độc lập khỏi đường truyền; SOAP chỉ bảo vệ TCP
B. TLS bảo vệ kênh; chữ ký SOAP bảo vệ phần message đã ký
C. TLS bảo vệ SOAP sau khi lưu ở mọi queue trung gian
D. Chữ ký SOAP tự ngăn mọi SOAP Fault trong phiên TLS
Đáp án đúng: B

Câu 44. Để hạn chế replay của UsernameToken có nonce/timestamp, cơ chế nào phù hợp?
A. Chấp nhận nonce cũ nếu SOAP Header có cùng username
B. Bỏ kiểm tra timestamp để không phụ thuộc đồng hồ
C. Kiểm tra timestamp và theo dõi nonce đã sử dụng
D. Dùng JAXB marshaller để tự sinh mật khẩu mới mỗi lần
Đáp án đúng: C

Câu 45. Khi xử lý XML SOAP từ đối tác, cấu hình nào giảm nguy cơ XXE?
A. Giới hạn external entities và DTD trong XML parser
B. Cho phép tải external entities để tự tìm XSD chuẩn
C. Cho parser đọc local file vì SOAP đã dùng HTTPS
D. Bỏ xác thực XSD nhưng bật XML entity expansion
Đáp án đúng: A

Câu 46. Muốn kiểm thử SOAP endpoint không cần mở HTTP port thật, lớp nào phù hợp?
A. MockWebServiceServer giả lập server ngoài cho SOAP client
B. MockWebServiceClient gửi request giả và xác minh response
C. WebServiceTemplate kết nối đến SOAP service production
D. SoapFaultMappingExceptionResolver tự giả lập transport
Đáp án đúng: B

Câu 47. Muốn kiểm thử SOAP client dùng WebServiceTemplate mà không gọi đối tác, lớp nào phù hợp?
A. MockWebServiceClient thực hiện request HTTP tới đối tác thật
B. MessageDispatcherServlet đóng vai SOAP remote server trong unit test
C. MockWebServiceServer giả lập response và kiểm tra request client
D. DefaultWsdl11Definition tự giả lập SOAP Fault của client
Đáp án đúng: C

Câu 48. Trong SOAP 1.2, mã fault Sender được dùng cho loại lỗi nào?
A. Lỗi liên quan tới message do phía gửi cung cấp
B. Lỗi receiver nội bộ không thể xử lý message hợp lệ
C. Lỗi namespace Envelope do SOAP version không khớp
D. Lỗi bắt buộc xử lý SOAP Header nhưng chưa hiểu
Đáp án đúng: A
