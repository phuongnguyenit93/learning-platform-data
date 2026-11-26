Bạn giải thích Spring Web Services hỗ trợ xây dựng dịch vụ SOAP theo cách tiếp cận contract-first như thế nào?
Bạn phân biệt contract-first SOAP với cách sinh hợp đồng từ Java implementation theo khả năng quản trị thay đổi như thế nào?
Bạn sẽ xác định khi nào SOAP phù hợp hơn REST cho một hệ thống tích hợp doanh nghiệp theo yêu cầu hợp đồng nào?
Bạn mô tả vai trò của SOAP Envelope, Header và Body trong một thông điệp SOAP như thế nào?
Bạn phân biệt XML message payload với SOAP Envelope chứa các metadata ở header như thế nào?
Bạn sẽ quyết định ranh giới giữa application service và SOAP endpoint để không gắn logic nghiệp vụ vào tầng vận chuyển ra sao?
Bạn mô tả XML namespace giúp phân biệt các phần tử trùng tên giữa nhiều hệ thống như thế nào?
Bạn phân biệt targetNamespace trong XSD với namespace của SOAP Envelope theo mục đích nào?
Bạn sẽ thiết kế một XSD schema diễn tả request và response của nghiệp vụ tạo đơn hàng như thế nào?
Bạn phân biệt xsd:element với xsd:complexType khi xây dựng contract dùng cho SOAP body ra sao?
Bạn sẽ chọn xsd:sequence hoặc xsd:choice để biểu diễn thứ tự và lựa chọn fields theo quy tắc nào?
Bạn phân tích ảnh hưởng của minOccurs, maxOccurs và nillable tới client JAXB bindings như thế nào?
Bạn sẽ phân biệt trường bị bỏ qua hoàn toàn với trường hiện diện nhưng nil trong XML message ra sao?
Bạn sẽ xác định khi nào nên dùng xsd:enumeration và khi nào cần mở rộng giá trị qua versioning như thế nào?
Bạn phân tích rủi ro đổi một xsd:string sang xsd:int đối với các client đang dùng hợp đồng cũ ra sao?
Bạn sẽ quản lý các XML types dùng chung qua xsd:import và xsd:include theo phạm vi namespace như thế nào?
Bạn phân biệt xsd:import với xsd:include theo ảnh hưởng của targetNamespace như thế nào?
Bạn sẽ quyết định ranh giới một XSD file chứa đầy đủ types hay nhiều schema files theo bounded contexts ra sao?
Bạn phân tích vì sao XML schema validation không thể thay thế kiểm tra business invariants ở application service như thế nào?
Bạn sẽ xác định các constraints như pattern, length và fractionDigits phù hợp ở XSD thay vì để toàn bộ ở Java ra sao?
Bạn mô tả thành phần types, message, portType, binding và service trong WSDL 1.1 ra sao?
Bạn phân biệt WSDL portType mô tả operations với SOAP binding khai báo thông tin truyền tải như thế nào?
Bạn sẽ thiết kế một WSDL document/literal endpoint theo contract-first style ra sao?
Bạn phân biệt document/literal wrapped và document/literal bare theo quy ước message payload và compatibility như thế nào?
Bạn sẽ xác định SOAPAction cần khai báo như thế nào để client SOAP 1.1 sử dụng đúng operation ra sao?
Bạn phân biệt SOAP 1.1 và SOAP 1.2 theo namespace Envelope và Content-Type như thế nào?
Bạn sẽ chọn một SOAP version dựa vào hệ thống đối tác và các chính sách bảo mật nào?
Bạn phân tích vì sao WSDL truy cập qua URL có địa chỉ nội bộ phía sau proxy gây khó khăn cho bên tích hợp như thế nào?
Bạn sẽ quản lý thay đổi contract WSDL/XSD như một artifact có version thay vì chỉ dựa vào Java code như thế nào?
Bạn đánh giá khi nào cần tạo namespace phiên bản mới để tránh làm hỏng clients hiện tại như thế nào?
Bạn sẽ kiểm tra contract có thể được tạo code client bởi các SOAP toolkits khác nhau ra sao?
Bạn giải thích @EnableWs kích hoạt hạ tầng xử lý Spring Web Services trong ứng dụng Spring như thế nào?
Bạn mô tả MessageDispatcherServlet nhận SOAP request và chuyển vào các thành phần Spring-WS như thế nào?
Bạn sẽ cấu hình servlet mapping cho /ws/* mà không xung đột với Spring MVC DispatcherServlet ra sao?
Bạn phân biệt MessageDispatcherServlet với DispatcherServlet của Spring MVC về hợp đồng endpoint như thế nào?
Bạn sẽ dùng @Endpoint để khai báo lớp xử lý SOAP requests theo từng business operation ra sao?
Bạn phân biệt @Endpoint với @RestController theo cách định tuyến và kiểu dữ liệu request như thế nào?
Bạn mô tả @PayloadRoot dùng namespace và localPart để ánh xạ SOAP body tới endpoint method như thế nào?
Bạn sẽ xác định vì sao một @PayloadRoot không khớp dù phần tử XML có cùng tên nhưng khác namespace ra sao?
Bạn phân biệt PayloadRootAnnotationMethodEndpointMapping với SoapActionAnnotationMethodEndpointMapping theo tiêu chí định tuyến nào?
Bạn sẽ dùng @SoapAction khi đối tác yêu cầu routing theo SOAPAction theo điều kiện nào?
Bạn phân tích rủi ro dựa vào SOAPAction khi các SOAP clients gửi header không thống nhất như thế nào?
Bạn sẽ chọn namespace và localPart ổn định để tránh mapping collision giữa các endpoint methods ra sao?
Bạn mô tả vai trò của @RequestPayload và @ResponsePayload khi endpoint nhận và trả XML payload ra sao?
Bạn sẽ thiết kế endpoint method dùng JAXB-generated request class rồi trả response class như thế nào?
Bạn phân biệt EndpointAdapter với EndpointMapping trong quy trình dispatch SOAP request như thế nào?
Bạn sẽ xác định vì sao một endpoint method không được adapter hỗ trợ dù đã được mapping ra sao?
Bạn phân tích rủi ro dùng trực tiếp transport-specific HttpServletRequest trong SOAP business logic như thế nào?
Bạn sẽ đọc SOAP headers khi nghiệp vụ cần correlation identifier hoặc tenant metadata theo cách nào?
Bạn phân biệt header business metadata với WS-Security header trong xử lý endpoint như thế nào?
Bạn sẽ sử dụng MessageContext khi cần truy cập SOAP request và response mà không lạm dụng nó trong domain service ra sao?
Bạn mô tả @SoapHeader giúp endpoint nhận một phần SOAP header theo API Spring-WS như thế nào?
Bạn sẽ kiểm tra trường hợp SOAP header có mustUnderstand mà endpoint không nhận biết theo semantics nào?
Bạn phân tích nguy cơ bỏ qua header mustUnderstand dẫn tới yêu cầu chưa được xử lý đúng chính sách ra sao?
Bạn sẽ tổ chức một endpoint trả về payload và phản hồi SOAP Fault khi application service phát hiện lỗi nghiệp vụ như thế nào?
Bạn sẽ xác định khi nào không nên trả null response cho operation được mô tả có response bắt buộc trong WSDL ra sao?
Bạn phân biệt one-way SOAP operation với request-response operation về xử lý lỗi và hành vi client ra sao?
Bạn sẽ tách validation, authentication và business execution thành các lớp khác nhau trong SOAP processing pipeline như thế nào?
Bạn mô tả DefaultWsdl11Definition có thể dùng XSD để sinh WSDL 1.1 theo những cấu hình nào?
Bạn sẽ khai báo SimpleXsdSchema làm nguồn XSD cho định nghĩa WSDL trong Spring Boot như thế nào?
Bạn phân biệt WSDL tự sinh tại runtime với WSDL tĩnh được kiểm soát chặt trong quá trình release ra sao?
Bạn sẽ điều chỉnh service location URI do WSDL công bố khi triển khai phía sau reverse proxy như thế nào?
Bạn phân tích rủi ro tự động sinh WSDL dựa trên naming convention khiến operations khác dự kiến như thế nào?
Bạn sẽ xác định khi nào cần WSDL tĩnh vì hợp đồng bao gồm WS-Policy hoặc binding phức tạp như thế nào?
Bạn sẽ quản lý @Endpoint beans và servlet mapping trong một ứng dụng chứa nhiều SOAP services ra sao?
Bạn giải thích JAXB hỗ trợ ánh xạ XML Schema types sang Java objects trong Spring Web Services như thế nào?
Bạn phân biệt marshalling với unmarshalling khi endpoint nhận request và trả response như thế nào?
Bạn sẽ dùng Jaxb2Marshaller để xử lý request/response JAXB trong endpoint hoặc SOAP client ra sao?
Bạn mô tả cách tạo JAXB-generated classes từ XSD bằng công cụ XJC phù hợp với phiên bản Jakarta JAXB như thế nào?
Bạn phân biệt jakarta.xml.bind và javax.xml.bind khi nâng từ Spring Boot cũ sang Spring Boot mới theo mức độ tương thích nào?
Bạn sẽ xác định packagesToScan hoặc contextPaths khi cấu hình Jaxb2Marshaller cho nhiều schemas ra sao?
Bạn phân tích rủi ro hai schemas có generated classes cùng tên nhưng khác namespace khi đặt chung package ra sao?
Bạn mô tả @XmlRootElement giúp JAXB biết phần tử XML root khi marshal một Java object như thế nào?
Bạn phân biệt @XmlType, @XmlElement và @XmlAttribute trong ánh xạ schema với Java types ra sao?
Bạn sẽ xử lý một JAXB class được dùng qua JAXBElement khi schema không tạo @XmlRootElement phù hợp như thế nào?
Bạn phân tích vì sao không nên sửa tay JAXB-generated classes nếu XSD mới sẽ sinh lại các file này như thế nào?
Bạn sẽ thiết kế lớp adapter chuyển từ generated DTO sang domain model để không làm domain phụ thuộc schema như thế nào?
Bạn phân biệt XML element absent với xsi:nil khi ánh xạ sang Java null và optional wrappers như thế nào?
Bạn sẽ bảo đảm định dạng date/time có timezone rõ ràng khi XML Schema dùng xsd:dateTime ra sao?
Bạn phân tích vì sao BigDecimal phù hợp hơn double khi schema biểu diễn monetary decimal có scale quan trọng như thế nào?
Bạn sẽ xử lý unknown XML elements hoặc namespace mismatch theo chính sách validation như thế nào?
Bạn phân biệt schema validation ở tầng payload với validation sâu hơn về quy tắc nghiệp vụ như thế nào?
Bạn sẽ cấu hình marshaller bảo vệ khỏi XML External Entity (XXE) thông qua parser và XML processing settings như thế nào?
Bạn phân tích khả năng entity expansion hoặc XML bomb làm tiêu tốn CPU/RAM khi unmarshalling như thế nào?
Bạn sẽ giới hạn kích thước XML payload và nesting depth để giảm nguy cơ denial-of-service ra sao?
Bạn mô tả cách namespace prefixes có thể khác nhau nhưng expanded element names vẫn tương đương như thế nào?
Bạn sẽ tránh so sánh nguyên chuỗi XML trong test khi thứ tự attributes hoặc prefix không ảnh hưởng ngữ nghĩa như thế nào?
Bạn phân biệt schemaLocation hint do XML input cung cấp với schema được ứng dụng tin cậy và đóng gói sẵn như thế nào?
Bạn sẽ xác định nguy cơ tải external XSD từ URL do client điều khiển khi xử lý XML như thế nào?
Bạn sẽ test JAXB round-trip để phát hiện mất giá trị optional hoặc đa phần tử như thế nào?
Bạn phân tích rủi ro schema thay minOccurs từ 0 sang 1 làm request từ client cũ thất bại ra sao?
Bạn sẽ quyết định khi nào nên bổ sung một field optional thay vì tạo contract version mới như thế nào?
Bạn mô tả cách map XML enumeration values vào Java enum và xử lý unknown values như thế nào?
Bạn sẽ kiểm tra WSDL/XSD và generated JAXB classes không trôi lệch khi build hoặc upgrade dependencies ra sao?
Bạn đánh giá khi nào cần giữ một bước kiểm tra XSD compatibility tự động trong CI ra sao?
Bạn giải thích WebServiceTemplate thực hiện các bước gửi SOAP request, nhận response và chuyển đổi payload như thế nào?
Bạn phân biệt WebServiceTemplate với RestTemplate hoặc WebClient theo giao thức và kiểu hợp đồng ra sao?
Bạn sẽ cấu hình defaultUri và messageSender cho WebServiceTemplate theo endpoint đích như thế nào?
Bạn mô tả cách marshalSendAndReceive gửi object JAXB và nhận object phản hồi qua WebServiceTemplate ra sao?
Bạn sẽ sử dụng WebServiceMessageCallback để bổ sung SOAPAction hoặc header cho outgoing request như thế nào?
Bạn phân biệt SoapActionCallback với thao tác trực tiếp thêm SOAPAction header tùy loại SOAP message ra sao?
Bạn sẽ thiết kế SOAP client wrapper chỉ expose domain methods thay vì trả về JAXB transport objects ra sao?
Bạn mô tả vai trò của WebServiceMessageSender khi Spring-WS client gửi request qua HTTP transport như thế nào?
Bạn sẽ chọn HTTP client transport hỗ trợ connection pooling, connect timeout và read timeout theo phiên bản nào?
Bạn phân tích rủi ro WebServiceTemplate không có timeout hợp lý khiến server request threads bị giữ quá lâu như thế nào?
Bạn sẽ cấu hình HTTPS truststore và client certificate khi đối tác yêu cầu mutual TLS như thế nào?
Bạn phân biệt TLS client authentication bằng X.509 certificate với SOAP Message-level Signature trong WS-Security ra sao?
Bạn sẽ quản lý client key material và trust certificates mà không commit keystore password vào source ra sao?
Bạn mô tả SaajSoapMessageFactory tạo SOAP messages theo SAAJ và cấu hình SOAP version như thế nào?
Bạn sẽ phân biệt SAAJ SOAP message handling với cách streaming khi xử lý payload lớn theo điều kiện thư viện hỗ trợ ra sao?
Bạn sẽ xác định khi nào cần MTOM attachments thay vì encode binary thành base64 inline trong SOAP Body ra sao?
Bạn phân tích khả năng SOAP attachments gây tăng memory pressure hoặc cần streaming khi file quá lớn như thế nào?
Bạn sẽ thiết kế request/response headers để thêm correlation ID giữa SOAP client và server ra sao?
Bạn phân biệt business correlation header với HTTP trace headers khi truy vết giao dịch qua nhiều hệ thống như thế nào?
Bạn sẽ quyết định khi nào cần cấu hình HTTP proxy và proxy authentication cho SOAP client trong doanh nghiệp ra sao?
Bạn mô tả cách WebServiceTemplate dùng marshaller và unmarshaller tương ứng cho payloads gửi và nhận ra sao?
Bạn sẽ xử lý đối tác trả SOAP Fault trong một response có HTTP status không như dự kiến theo chính sách nào?
Bạn phân tích vì sao không nên coi mọi HTTP 500 của SOAP endpoint là transport failure có thể retry ngay như thế nào?
Bạn sẽ phân biệt connection timeout với read timeout và SOAP Fault khi tổ chức retry policy ra sao?
Bạn sẽ thiết kế retry có backoff cho SOAP request idempotent thay vì retry mù quáng operation tạo dữ liệu như thế nào?
Bạn phân tích rủi ro timeout sau khi đối tác đã xử lý request khiến client gửi lại và tạo giao dịch trùng ra sao?
Bạn sẽ dùng business idempotency key hoặc request identifier để an toàn khi gọi lại SOAP operation có side effects ra sao?
Bạn sẽ đánh giá khả năng áp dụng WS-Addressing MessageID hoặc business key theo hợp đồng đối tác như thế nào?
Bạn mô tả cách client interceptor có thể thêm SOAP headers hoặc ghi thời gian gọi đối tác ra sao?
Bạn sẽ đặt ClientInterceptor theo thứ tự logging, security và metrics phù hợp với nội dung message như thế nào?
Bạn phân tích rủi ro interceptor log toàn bộ SOAP Body có chứa thông tin cá nhân hoặc mật khẩu ra sao?
Bạn sẽ xử lý nhiều SOAP endpoints có timeout, chứng chỉ và XSD khác nhau mà vẫn tái sử dụng cấu trúc client phù hợp ra sao?
Bạn sẽ kiểm tra WSDL endpoint location khác với URL gọi thực tế trong staging và production như thế nào?
Bạn phân biệt lỗi DNS, TLS handshake, HTTP transport, SOAP Fault và XML unmarshalling trong giám sát SOAP client ra sao?
Bạn sẽ giới hạn concurrency của SOAP calls tới đối tác có rate limit để tránh làm quá tải hệ thống như thế nào?
Bạn giải thích SOAP Fault cung cấp cơ chế báo lỗi được chuẩn hóa ở tầng SOAP như thế nào?
Bạn phân biệt SOAP Fault Code, Reason hoặc Fault String và Detail theo SOAP 1.1/1.2 như thế nào?
Bạn sẽ xác định khi nào dùng Client/Sender fault so với Server/Receiver fault theo ngữ nghĩa lỗi nào?
Bạn mô tả SOAP 1.1 faultcode, faultstring, faultactor và detail khác các trường tương ứng SOAP 1.2 ra sao?
Bạn sẽ thiết kế business error detail theo XSD để client có thể đọc lỗi theo hợp đồng như thế nào?
Bạn phân tích nguy cơ đưa internal exception class names hoặc SQL errors vào SOAP Fault Detail ra sao?
Bạn sẽ dùng SoapFaultMappingExceptionResolver để ánh xạ exception từ endpoint thành SOAP Fault như thế nào?
Bạn phân biệt SoapFaultMappingExceptionResolver với SoapFaultAnnotationExceptionResolver khi muốn kiểm soát lỗi theo class/annotation ra sao?
Bạn sẽ dùng @SoapFault theo phiên bản Spring-WS hỗ trợ để mô tả loại Fault cho exception như thế nào?
Bạn sẽ xác định cách tạo fault detail cho lỗi validation có nhiều fields không hợp lệ theo hợp đồng nào?
Bạn phân tích vì sao một lỗi nghiệp vụ có thể cần fault detail ổn định hơn việc chỉ trả SOAP faultstring ra sao?
Bạn sẽ quyết định khi nào SOAP Fault nên thể hiện lỗi hợp đồng và khi nào trả business rejection response hợp lệ theo WSDL ra sao?
Bạn phân biệt HTTP status code với SOAP Fault Code vì sao không được suy luận chỉ từ status như thế nào?
Bạn sẽ xử lý SOAP Fault phía client bằng SoapFaultClientException và trích xuất thông tin an toàn ra sao?
Bạn mô tả khi nào WebServiceTemplate phát sinh exception cho fault thay vì trả unmarshalled response object như thế nào?
Bạn sẽ phân loại lỗi client-side invalid request với server-side transient fault để quyết định retry như thế nào?
Bạn phân tích vì sao retry một validation fault vĩnh viễn chỉ làm tăng tải mà không giải quyết lỗi ra sao?
Bạn sẽ lưu correlation ID trong SOAP Fault Detail mà không đưa secrets hoặc token vào response ra sao?
Bạn sẽ chuẩn hóa SOAP Fault messages giữa các operations để phía client không phải parse natural-language text ra sao?
Bạn phân biệt unhandled exception trên endpoint với exception đã được mapping thành fault theo khả năng quan sát ra sao?
Bạn sẽ cấu hình logging của SoapFaultMappingExceptionResolver để vận hành thấy nguyên nhân mà client chỉ thấy message an toàn như thế nào?
Bạn sẽ kiểm thử lỗi namespace của payload được chuyển thành fault hay bị từ chối ở bước endpoint mapping ra sao?
Bạn đánh giá khi nào XML validation error xảy ra trước endpoint invocation và được phản hồi bởi interceptor như thế nào?
Bạn phân tích nguy cơ trả HTTP 200 chứa business failure nhưng client coi operation đã thành công do chỉ kiểm HTTP status ra sao?
Bạn sẽ lập bảng fault codes và fault details để công bố trong tài liệu tích hợp với đối tác như thế nào?
Bạn giải thích EndpointInterceptor được gọi ở giai đoạn nào của quá trình xử lý SOAP endpoint trong Spring Web Services?
Bạn phân biệt EndpointInterceptor phía server với ClientInterceptor phía WebServiceTemplate theo vị trí thực thi như thế nào?
Bạn sẽ sử dụng handleRequest, handleResponse và handleFault của EndpointInterceptor cho mục tiêu nào?
Bạn mô tả afterCompletion của interceptor giúp cleanup hay chẩn đoán sau khi xử lý như thế nào?
Bạn sẽ xác định thứ tự các interceptors khi cần vừa schema validation vừa message security như thế nào?
Bạn phân tích rủi ro logging interceptor đọc SOAP Body trước security verification khiến nội dung chưa tin cậy bị ghi lại ra sao?
Bạn sẽ dùng PayloadValidatingInterceptor để kiểm tra request và response dựa trên XSD được tin cậy như thế nào?
Bạn phân biệt kiểm tra XML schema ở interceptor với business validation trong endpoint method ra sao?
Bạn sẽ quyết định khi nào bật validateRequest và validateResponse theo môi trường và chi phí thực thi nào?
Bạn đánh giá ảnh hưởng của việc validate response trên mỗi request tới latency và hiệu năng của SOAP service ra sao?
Bạn sẽ tạo interceptor bổ sung correlation ID vào logs nhưng không sửa nội dung đã được ký số theo WS-Security như thế nào?
Bạn phân tích vì sao sửa SOAP Body sau khi ký XML làm signature validation phía nhận thất bại ra sao?
Bạn sẽ triển khai metrics interceptor đo SOAP operation latency và fault rate theo những dimensions nào?
Bạn sẽ tránh dùng user ID, SOAP message ID hoặc payload content làm metric tags có cardinality cao ra sao?
Bạn phân biệt các sự kiện transport, marshalling và endpoint execution khi xác định latency breakdown ra sao?
Bạn sẽ tổ chức một interceptor chỉ áp dụng cho nhóm endpoints cụ thể theo mapping hoặc cấu hình phù hợp như thế nào?
Bạn đánh giá khi nào nên dùng Spring-WS interception thay vì Servlet filter cho SOAP-aware processing ra sao?
Bạn sẽ xác định dữ liệu SOAP Header nào có thể dùng cho routing sau khi qua authentication và integrity checks như thế nào?
Bạn phân tích vì sao không được tin giá trị username ở SOAP Header nếu WS-Security chưa được xác minh ra sao?
Bạn sẽ dùng interceptor để kiểm soát kích thước XML và yêu cầu an toàn trước khi JAXB unmarshalling theo giới hạn nào?
Bạn sẽ test thứ tự invoke interceptor và xử lý exception để không vô tình bỏ qua bước signature verification ra sao?
Bạn giải thích WS-Security mở rộng SOAP với những cơ chế bảo mật message-level nào khác TLS?
Bạn phân biệt transport-level HTTPS với WS-Security XML Signature và XML Encryption theo threat model như thế nào?
Bạn sẽ sử dụng Wss4jSecurityInterceptor để xử lý các chính sách WS-Security theo phiên bản Spring-WS tương thích như thế nào?
Bạn mô tả UsernameToken, Timestamp và BinarySecurityToken có những vai trò khác nhau ra sao?
Bạn sẽ xác định khi nào UsernameToken dùng PasswordDigest phù hợp và cần các điều kiện chống replay nào?
Bạn phân tích rủi ro dùng UsernameToken PasswordText trên kết nối không mã hóa TLS ra sao?
Bạn sẽ xác minh nonce và created timestamp của UsernameToken để giảm nguy cơ phát lại request như thế nào?
Bạn sẽ thiết kế anti-replay cache có thời hạn và chia sẻ giữa nhiều replicas theo yêu cầu nào?
Bạn phân biệt authentication bằng UsernameToken với mutual TLS client certificate về ranh giới xác minh như thế nào?
Bạn sẽ dùng X.509 certificate để xác minh XML Signature của SOAP request theo quy trình nào?
Bạn mô tả key store và trust store khác nhau theo trách nhiệm giữ private key và xác minh chứng chỉ như thế nào?
Bạn sẽ xác định chính sách certificate chain validation, expiry và key usage khi kiểm chữ ký như thế nào?
Bạn phân tích rủi ro tắt certificate trust validation chỉ để một SOAP client kết nối được trong test ra sao?
Bạn sẽ tổ chức rotation signing certificates mà cả client và server vẫn có thể xác minh message trong giai đoạn chuyển tiếp như thế nào?
Bạn sẽ thiết kế XML Encryption bảo vệ phần tử có dữ liệu nhạy cảm theo yêu cầu WS-Security ra sao?
Bạn phân biệt ký rồi mã hóa với mã hóa rồi ký theo chính sách tương thích và bảo mật của đối tác như thế nào?
Bạn phân tích rủi ro XML Signature Wrapping làm ứng dụng đọc một node khác với node đã được chữ ký bảo vệ ra sao?
Bạn sẽ xác định các XML elements bắt buộc phải được ký theo WS-Policy hoặc hợp đồng bảo mật nào?
Bạn sẽ kiểm tra Timestamp nằm trong phạm vi chữ ký để tránh bị chỉnh thời hạn hợp lệ như thế nào?
Bạn phân tích nguy cơ bỏ qua các SOAP headers đã được ký nhưng application xử lý các headers không được ký ra sao?
Bạn sẽ lựa chọn KeyStoreCallbackHandler hoặc callback mechanism phù hợp để cung cấp bí mật ký/mã hóa mà không hardcode password như thế nào?
Bạn sẽ phân biệt certificate dùng cho HTTPS với certificate dùng ký message-level SOAP theo vòng đời nào?
Bạn sẽ thiết kế fail-closed khi signature hoặc trust chain không hợp lệ nhưng endpoint mapping vẫn tìm được method ra sao?
Bạn phân tích vì sao WS-Security không tự bảo vệ khỏi XML External Entity hoặc XML bomb nếu parser chưa được harden ra sao?
Bạn sẽ kiểm tra cấu hình XML parser để từ chối external entity resolution và DTD không cần thiết như thế nào?
Bạn sẽ xác định cơ chế bảo vệ chống Billion Laughs và payload XML quá sâu trước xử lý WS-Security như thế nào?
Bạn phân tích rủi ro một bên ký SOAP Body nhưng thay đổi SOAPAction không được bảo vệ gây điều hướng sai operation ra sao?
Bạn sẽ đồng bộ security policies giữa WSDL/WS-Policy, server interceptor và client configuration ra sao?
Bạn sẽ kiểm tra thông điệp với UsernameToken sai, chữ ký sai và timestamp hết hạn được phản hồi lỗi nhất quán như thế nào?
Bạn sẽ ghi log các lỗi WS-Security mà không ghi dữ liệu bí mật, private key hoặc toàn bộ SOAP message như thế nào?
Bạn phân biệt WS-Security authentication với authorization theo role và business ownership sau khi danh tính được xác minh ra sao?
Bạn sẽ đưa danh tính được WS-Security xác thực vào SecurityContext phù hợp thay vì tin SOAP header thủ công như thế nào?
Bạn sẽ đánh giá khi nào cần kết hợp mTLS, XML Signature và UsernameToken thay vì triển khai tất cả mặc định ra sao?
Bạn giải thích sự khác nhau giữa SOAP 1.1 và SOAP 1.2 có thể ảnh hưởng khả năng tương thích của client như thế nào?
Bạn sẽ xác định binding document/literal có phù hợp với SOAP client toolkits của đối tác như thế nào?
Bạn phân tích rủi ro đổi namespace hoặc element local name khiến @PayloadRoot không tìm được endpoint dù payload khác rất ít ra sao?
Bạn sẽ thiết kế thêm một optional field trong XSD mà client cũ vẫn gửi request hợp lệ như thế nào?
Bạn phân biệt backward-compatible schema evolution với thay đổi phá vỡ contract như đổi required field hoặc type ra sao?
Bạn sẽ quản lý multiple WSDL contract versions trong cùng ứng dụng mà không làm lẫn endpoint mappings như thế nào?
Bạn sẽ xác định khi nào nên giữ SOAP endpoint phiên bản cũ và công bố endpoint mới thay vì sửa tại chỗ ra sao?
Bạn phân tích rủi ro lỗi tiền tố XML namespace làm test text comparison thất bại dù message hợp lệ như thế nào?
Bạn sẽ xử lý JAXB-generated code của client cũ khi server thêm một XML element chưa được schema cũ biết như thế nào?
Bạn sẽ kiểm tra compatibility giữa JAXB Jakarta và đối tác dùng toolchain Javax cũ theo giới hạn nào?
Bạn mô tả SoapAction khác nhau giữa SOAP 1.1 và SOAP 1.2 có thể ảnh hưởng routing qua gateway ra sao?
Bạn sẽ xác định khi nào Content-Type, charset và SOAPAction không khớp làm proxy hoặc server từ chối request như thế nào?
Bạn sẽ thiết kế conformance tests dựa trên WSDL và XSD để xác nhận request/response chuẩn qua mỗi release ra sao?
Bạn phân tích vì sao WSDL tự sinh từ XSD vẫn cần contract test với khách hàng sử dụng công cụ SOAP khác nhau ra sao?
Bạn sẽ quyết định cách xử lý unknown optional elements của client theo khả năng validation và JAXB binding như thế nào?
Bạn phân biệt testing compatibility theo XML schema với testing semantic behavior của SOAP operation như thế nào?
Bạn sẽ lập kế hoạch deprecation một SOAP operation trong WSDL mà vẫn bảo vệ clients cũ theo thời hạn nào?
Bạn phân tích nguy cơ thay đổi Fault Detail schema nhưng giữ faultcode cũ khiến client parse lỗi ra sao?
Bạn sẽ kiểm tra SOAP service URL trong WSDL khi backend chạy sau ingress, load balancer hoặc proxy TLS termination như thế nào?
Bạn sẽ xác minh endpoint không tự rò nội bộ server hostnames trong WSDL service location ra sao?
Bạn mô tả cách tạo contract compatibility report từ hai phiên bản XSD/WSDL theo những thay đổi nào?
Bạn sẽ thiết kế consumer-driven compatibility test khi có nhiều đối tác dùng tập con operations khác nhau ra sao?
Bạn phân tích rủi ro bỏ một giá trị enum XSD cũ nhưng client vẫn gửi dữ liệu lịch sử có giá trị đó ra sao?
Bạn sẽ chọn policy thay đổi optionality và occurrence constraints theo khả năng tương thích với client code generators như thế nào?
Bạn đánh giá khi nào một thay đổi SOAP security policy là breaking change dù XSD payload không đổi ra sao?
Bạn phân biệt unit test JAXB mapper, endpoint method và integration test của toàn bộ SOAP dispatch pipeline như thế nào?
Bạn sẽ dùng MockWebServiceClient để gửi một SOAP request tới endpoint trong Spring TestContext như thế nào?
Bạn mô tả các request creators và response matchers trong spring-ws-test hỗ trợ assert kết quả theo XML như thế nào?
Bạn sẽ sử dụng MockWebServiceServer để mô phỏng external SOAP server khi kiểm thử WebServiceTemplate client ra sao?
Bạn phân biệt MockWebServiceClient và MockWebServiceServer theo việc bên nào là hệ thống được kiểm thử như thế nào?
Bạn sẽ cấu hình @SpringBootTest khi cần nạp @Endpoint, marshaller và interceptors đầy đủ theo cách nào?
Bạn sẽ kiểm tra @PayloadRoot mapping được chọn đúng cho request có namespace hợp lệ bằng test nào?
Bạn sẽ xây dựng negative test cho payload root namespace sai mà không nhầm với lỗi business validation như thế nào?
Bạn sẽ kiểm thử JAXB unmarshalling với optional fields, xsi:nil, repeated elements và XML namespace prefixes ra sao?
Bạn phân tích vì sao mock endpoint method trực tiếp không kiểm chứng hoạt động của MessageDispatcherServlet như thế nào?
Bạn sẽ xác minh SOAP Fault mapping cho invalid request, business error và unexpected exception bằng cách nào?
Bạn sẽ kiểm tra Fault Detail có mã lỗi ổn định nhưng không chứa stack trace hoặc secrets ra sao?
Bạn sẽ kiểm thử PayloadValidatingInterceptor từ chối XML không hợp lệ dù endpoint method chưa được gọi như thế nào?
Bạn sẽ dùng XSD fixture và WSDL snapshots để phát hiện contract drift giữa các phiên bản ra sao?
Bạn sẽ kiểm tra SOAP 1.1 và SOAP 1.2 Content-Type hoặc Envelope đều được xử lý đúng theo policy như thế nào?
Bạn sẽ tạo test SOAPAction mismatch nhằm xác minh endpoint không chạy nhầm operation như thế nào?
Bạn sẽ kiểm thử ClientInterceptor thêm SOAP header mà không làm đổi payload đã được ký như thế nào?
Bạn sẽ dùng MockWebServiceServer để xác minh SoapActionCallback và outbound XML payload chính xác ra sao?
Bạn sẽ kiểm thử SOAP client xử lý timeout, HTTP failure và SoapFaultClientException theo từng nhánh ra sao?
Bạn phân tích vì sao integration test với SOAP service thực của đối tác không nên phụ thuộc dữ liệu production ra sao?
Bạn sẽ xây dựng stub SOAP server từ contract để test backward compatibility khi đối tác chưa có môi trường test như thế nào?
Bạn sẽ kiểm thử mTLS handshake với test certificates mà không nhúng private key production vào source ra sao?
Bạn sẽ thiết kế test UsernameToken có nonce lặp lại, timestamp hết hạn và signature invalid để xác nhận fail-closed như thế nào?
Bạn sẽ kiểm thử XML Signature Wrapping defense với payload có nhiều phần tử cùng tên theo chiến lược nào?
Bạn sẽ tạo test XXE và XML bomb trong môi trường giới hạn tài nguyên để xác nhận parser từ chối như thế nào?
Bạn sẽ kiểm thử certificate rotation khi truststore có khóa cũ và khóa mới theo chính sách nào?
Bạn sẽ dùng Testcontainers hoặc mock HTTP service khi cần kiểm thử hạ tầng SOAP và dependency thật theo tiêu chí nào?
Bạn sẽ đánh giá khi nào test thông điệp có MTOM attachment cần xác minh memory footprint và streaming như thế nào?
Bạn sẽ thiết kế performance test đo unmarshalling CPU, endpoint latency, SOAP payload size và connection pool ra sao?
Bạn sẽ xây dựng contract CI gate kiểm tra XSD, WSDL, JAXB code generation và security regression tests như thế nào?
Bạn giải thích những metrics nào cần theo dõi để vận hành SOAP endpoint an toàn với lưu lượng lớn?
Bạn sẽ dùng Micrometer ghi SOAP operation latency, fault count và validation failures mà không gắn PII vào tags như thế nào?
Bạn sẽ phân biệt HTTP 500 do SOAP Fault với HTTP 500 do reverse proxy hoặc network gateway qua dấu hiệu nào?
Bạn phân tích tác động của SOAP payload lớn đến heap, garbage collection và request threads như thế nào?
Bạn sẽ xác định khi nào cần giới hạn request body size ở servlet container hoặc API gateway trước khi xử lý JAXB ra sao?
Bạn sẽ tổ chức connection pooling và timeout cho WebServiceTemplate clients gọi nhiều SOAP providers ra sao?
Bạn sẽ kiểm tra trường hợp server trả SOAP Fault sau khi response bị delayed để tránh retry side effects ngoài dự kiến như thế nào?
Bạn phân tích rủi ro logging raw XML request chứa thông tin thẻ, nhân sự hoặc tài khoản như thế nào?
Bạn sẽ triển khai redaction các trường nhạy cảm trong SOAP payload logging theo schema thay vì regex tùy ý ra sao?
Bạn sẽ dùng correlation ID thống nhất giữa SOAP Header, HTTP request và distributed tracing như thế nào?
Bạn sẽ phân biệt lỗi XML parsing, WSDL mismatch, SOAP Fault và WS-Security signature failure trong dashboard như thế nào?
Bạn sẽ thiết kế readiness check không cần gửi giao dịch SOAP thật có side effects tới đối tác theo điều kiện nào?
Bạn phân tích khi nào health check chỉ kiểm tra port mở không chứng minh SOAP operation có thể xử lý chính xác ra sao?
Bạn sẽ tổ chức circuit breaker và bulkhead cho SOAP client khi đối tác bị quá tải theo tiêu chí nào?
Bạn sẽ xác định cách giới hạn retries tránh làm đối tác nhận cùng một payment request nhiều lần ra sao?
Bạn sẽ kiểm tra keystore/truststore certificate expiry sớm và lập lịch rotation an toàn như thế nào?
Bạn sẽ xây dựng runbook chẩn đoán lỗi SOAP namespace, XSD validation, SSL handshake và WS-Security timestamp như thế nào?
Bạn phân tích rủi ro batch import qua SOAP làm các request threads hết tài nguyên vì unmarshalling payload quá lớn ra sao?
Bạn sẽ đánh giá khi nào cần đưa long-running business operation vào asynchronous job thay vì giữ SOAP request mở như thế nào?
Bạn sẽ thiết kế throttling và request size quotas theo đối tác để tránh một client làm cạn tài nguyên toàn hệ thống ra sao?
Bạn phân tích tác động của SOAP Fault quá chi tiết đối với bảo mật thông tin nội bộ khi client không đáng tin cậy như thế nào?
Bạn sẽ xác định chính sách giữ và xóa request logs chứa dữ liệu cá nhân theo yêu cầu kiểm toán nào?
Bạn sẽ tổ chức nâng cấp Spring WS, Jakarta XML libraries và WSS4J mà không phá tương thích hợp đồng SOAP ra sao?
Bạn sẽ phân biệt nguy cơ thay đổi TLS trust policy với thay đổi WS-Security key material khi deploy phiên bản mới như thế nào?
Bạn sẽ xây dựng checklist go-live cho SOAP service gồm WSDL, XSD, Fault, security, certificates, compatibility tests và observability như thế nào?
Nếu một SOAP request có payload đúng localPart nhưng sai namespace và endpoint không được gọi, bạn sẽ chẩn đoán @PayloadRoot như thế nào?
Nếu client cũ không deserialize được response sau khi thêm một XSD field bắt buộc, bạn sẽ thiết kế tương thích contract ra sao?
Nếu WSDL công bố địa chỉ http nội bộ sau khi triển khai HTTPS reverse proxy, bạn sẽ cấu hình lại service location như thế nào?
Nếu SOAP 1.2 client gửi request tới endpoint chỉ nhận SOAP 1.1, bạn sẽ kiểm tra Envelope namespace và Content-Type ra sao?
Nếu SOAPAction của client không khớp routing nhưng payload namespace đúng, bạn sẽ xác định chiến lược endpoint mapping như thế nào?
Nếu JAXB unmarshalling lỗi trên một schema enum value mới, bạn sẽ thiết kế xử lý compatibility và migration ra sao?
Nếu một SOAP client báo SoapFaultClientException nhưng HTTP log chỉ có 500, bạn sẽ phân biệt Fault Detail với lỗi transport như thế nào?
Nếu request business sai nhưng server trả raw stack trace trong Fault, bạn sẽ cải thiện SoapFaultMappingExceptionResolver như thế nào?
Nếu PayloadValidatingInterceptor nhận XSD không tương thích với WSDL công bố, bạn sẽ kiểm tra source-of-truth của contract ra sao?
Nếu một outbound SOAP request timeout sau khi đối tác đã xử lý đơn hàng, bạn sẽ thiết kế idempotency trước khi retry như thế nào?
Nếu ClientInterceptor log SOAP Body đã ký rồi vô tình chỉnh namespace prefix khiến signature sai, bạn sẽ thay đổi interceptor ra sao?
Nếu WS-Security UsernameToken có timestamp cũ nhưng nonce mới, bạn sẽ áp dụng kiểm tra freshness và replay cache như thế nào?
Nếu một XML Signature hợp lệ nhưng endpoint lại đọc một Body node khác được chèn vào, bạn sẽ chống signature wrapping như thế nào?
Nếu TLS handshake thất bại sau certificate rotation, bạn sẽ kiểm tra truststore, chain và client certificate như thế nào?
Nếu một SOAP service bị quá tải bởi XML bomb, bạn sẽ giới hạn parser và request size ngay từ những tầng nào?
Nếu MockWebServiceClient test PASS nhưng SOAP client của đối tác không gọi được vì WSDL binding khác, bạn sẽ bổ sung kiểm thử tương thích giữa hai hệ thống như thế nào?
Nếu một SOAP message chứa MTOM attachment lớn làm heap tăng mạnh, bạn sẽ kiểm tra streaming và kích thước giới hạn như thế nào?
Nếu SOAP Fault rate tăng nhưng HTTP status dashboard không thay đổi như kỳ vọng, bạn sẽ điều chỉnh metrics theo SOAP operation và fault code ra sao?
Nếu cùng một SOAP service phải duy trì hai contract versions và hai bộ security requirements, bạn sẽ thiết kế định tuyến và kiểm thử như thế nào?
Nếu cần triển khai Spring Web Services SOAP tích hợp hệ thống doanh nghiệp, bạn sẽ thiết kế contract-first XSD/WSDL, JAXB, endpoint, WebServiceTemplate, Fault, interceptors, WS-Security và kiểm thử như thế nào?
