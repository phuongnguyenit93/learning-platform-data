Một ứng dụng Spring Boot vừa tích hợp springdoc-openapi nhưng endpoint xuất đặc tả trả 404 sau khi triển khai, dù các REST controller vẫn hoạt động; hãy xây dựng tình huống kiểm tra điều kiện sinh tài liệu.
Một hệ thống có hàng chục controller trong nhiều package nhưng tài liệu OpenAPI chỉ hiển thị nhóm API quản trị; hãy đặt bài toán xác minh phạm vi quét và các endpoint bị bỏ sót.
Một dự án nâng cấp Spring Boot và springdoc-openapi, sau đó ứng dụng khởi động được nhưng quá trình tạo đặc tả gặp lỗi liên quan đến thư viện; hãy xây dựng tình huống đánh giá tương thích phiên bản.
Một ứng dụng có các controller Spring MVC chạy sau reverse proxy, khiến server URL trong OpenAPI trỏ tới host nội bộ; hãy đặt tình huống kiểm chứng địa chỉ công khai mà client nhận được.
Một hệ thống triển khai cùng REST API ở staging và production, nhưng trường servers trong đặc tả vẫn chứa URL của môi trường phát triển; hãy xây dựng ca kiểm tra thông tin môi trường trước phát hành.
Một ứng dụng có context path tùy biến và gateway thêm tiền tố đường dẫn, khiến Swagger UI gọi nhầm endpoint khi người dùng thử request; hãy đặt bài toán chẩn đoán đường dẫn được công bố.
Một microservice chuyển sang sử dụng endpoint quản lý riêng cho observability, nhưng endpoint OpenAPI vô tình nằm trên cổng không được phép truy cập từ nội bộ; hãy xây dựng tình huống kiểm chứng phạm vi phơi bày tài liệu.
Một nhóm tạo tài liệu từ controller ở module mới nhưng các API chỉ xuất hiện khi bật một Spring profile nhất định; hãy đặt tình huống đánh giá tác động của cấu hình và bean có điều kiện.
Một dự án di trú các endpoint từ Spring MVC sang WebFlux, nhưng tài liệu sinh ra ở môi trường thử nghiệm khác với hành vi của các route Reactive; hãy xây dựng tình huống kiểm tra đường phát sinh hợp đồng.
Một ứng dụng có router function khai báo REST endpoint ngoài controller truyền thống, khiến nhóm phát triển không tìm thấy chúng trong tài liệu; hãy xây dựng tình huống xác minh độ bao phủ của đặc tả.
Một REST controller kế thừa phương thức từ lớp cơ sở dùng chung, nhưng OpenAPI hiển thị thao tác trùng lặp sau khi đội phát triển thêm controller con; hãy đặt bài toán phân tích nguồn mô tả operation.
Một dự án có API được công bố công khai và endpoint dùng nội bộ trong cùng controller, khiến tài liệu dành cho đối tác vô tình liệt kê endpoint quản trị; hãy xây dựng tình huống đánh giá phạm vi xuất bản.
Một hệ thống nhiều ứng dụng dùng chung một bản mô tả OpenAPI, nhưng mỗi ứng dụng chạy các path khác nhau và một số thao tác không tồn tại trong môi trường đích; hãy đặt bài toán kiểm chứng nguồn hợp đồng.
Một bản phát hành thêm endpoint mới nhưng file OpenAPI xuất ra không thay đổi do pipeline vẫn dùng artifact của phiên bản trước; hãy xây dựng tình huống phát hiện tài liệu lỗi thời.
Một ứng dụng Spring Boot có nhiều cấu hình springdoc khác nhau giữa local và CI, khiến endpoint tải đặc tả xuất hiện ở một môi trường nhưng bị vô hiệu hóa ở môi trường khác; hãy đặt tình huống so sánh.
Một nhóm phát triển tùy biến tiêu đề, phiên bản và mô tả API, nhưng thông tin OpenAPI hiện vẫn ghi tên sản phẩm cũ sau đổi thương hiệu; hãy xây dựng tình huống kiểm chứng metadata của đặc tả.
Một API nhận thông tin khách hàng qua POST nhưng schema request trong Swagger UI thiếu trường địa chỉ bắt buộc, khiến đối tác gửi dữ liệu không hợp lệ; hãy xây dựng tình huống kiểm chứng hợp đồng đầu vào.
Một endpoint cập nhật hồ sơ nhận trường ngày sinh tùy chọn, nhưng đặc tả đánh dấu trường này là required và công cụ sinh client từ chối request hợp lệ; hãy đặt bài toán đánh giá tính bắt buộc của thuộc tính.
Một controller nhận danh sách mã sản phẩm, nhưng tài liệu mô tả request body như một object đơn nên client generator tạo sai kiểu tham số; hãy xây dựng tình huống kiểm chứng dạng dữ liệu của collection.
Một ứng dụng nhận enum trạng thái đơn hàng, nhưng giá trị mới được thêm vào Java mà không xuất hiện trong schema OpenAPI; hãy đặt tình huống phát hiện sai lệch giữa enum thực tế và tài liệu.
Một trường số tiền dùng BigDecimal với ràng buộc phần thập phân, nhưng OpenAPI mô tả như số nguyên và đối tác làm tròn giá trị trước khi gửi; hãy xây dựng tình huống kiểm tra độ chính xác dữ liệu.
Một model nhận mã quốc gia có độ dài cố định, nhưng tài liệu chỉ ghi kiểu string mà không thể hiện ràng buộc validation hiện có; hãy đặt tình huống đánh giá tính đầy đủ của schema.
Một service quản lý người dùng thêm Bean Validation cho email, nhưng schema xuất ra không phản ánh quy tắc hợp lệ mà frontend dựa vào; hãy xây dựng tình huống kiểm chứng annotation và tài liệu.
Một DTO có thuộc tính chỉ được đọc từ response, nhưng OpenAPI hiển thị thuộc tính đó trong request tạo mới và đối tác bắt đầu gửi giá trị không được chấp nhận; hãy đặt bài toán xác minh read-only field.
Một hệ thống cho phép cập nhật tên hiển thị nhưng không cho khách thay đổi định danh do server tạo, trong khi cùng một DTO dùng cho tạo và đọc; hãy xây dựng tình huống kiểm tra vai trò của trường dữ liệu theo thao tác.
Một API bán hàng nhận địa chỉ giao hàng dạng object lồng nhiều cấp, nhưng Swagger UI chỉ mô tả phần tử cha mà thiếu các ràng buộc ở phần tử con; hãy đặt tình huống đánh giá nested schema.
Một model Java sử dụng kiểu thời gian có múi giờ, nhưng tài liệu đưa ra ví dụ không có offset làm khách hàng hiểu sai thời điểm giao dịch; hãy xây dựng tình huống xác minh định dạng thời gian.
Một API nhận timestamp theo chuẩn ISO-8601 nhưng một endpoint khác dùng epoch milliseconds, trong khi cả hai được mô tả giống nhau trong đặc tả; hãy xây dựng tình huống đánh giá tính nhất quán.
Một hệ thống trả UUID cho mọi ID giao dịch, nhưng một schema công bố ID là số nguyên và client sinh ra thất bại khi parse response; hãy xây dựng tình huống kiểm tra kiểu định danh.
Một DTO có map với khóa động và giá trị là object, nhưng tài liệu được sinh thành object rỗng khiến phía đối tác không biết cấu trúc dữ liệu; hãy đặt tình huống đánh giá schema cho map.
Một REST API trả về một trong hai kiểu kết quả thanh toán tùy phương thức giao dịch, nhưng schema chỉ mô tả kiểu cơ sở và bỏ qua thuộc tính riêng; hãy xây dựng tình huống kiểm chứng mô hình đa hình.
Một hệ thống sử dụng sealed hierarchy cho các loại sự kiện, nhưng OpenAPI thể hiện mỗi loại như một schema rời không có thông tin phân biệt; hãy đặt bài toán đánh giá hợp đồng cho discriminator.
Một DTO tự tham chiếu dùng để mô tả cây danh mục, nhưng công cụ xuất schema gặp lỗi hoặc tạo định nghĩa lặp vô hạn; hãy xây dựng tình huống kiểm chứng dữ liệu đệ quy.
Một model nghiệp vụ sử dụng generic wrapper cho kết quả phân trang, nhưng schema trong tài liệu chỉ hiển thị phần metadata và làm mất kiểu của danh sách phần tử; hãy đặt tình huống kiểm tra kiểu generic.
Một API trả về danh sách rỗng trong trường hợp không có dữ liệu, nhưng schema lại công bố trường danh sách có thể là null; hãy đặt bài toán xác minh ngữ nghĩa nullable và giá trị rỗng.
Một service dùng Optional cho thuộc tính không bắt buộc nhưng schema OpenAPI vẫn đánh dấu trường là required, khiến client sinh code yêu cầu truyền trường đó; hãy xây dựng tình huống đánh giá.
Một ứng dụng bổ sung thuộc tính nhạy cảm vào entity JPA và vô tình trả trực tiếp entity ở controller, khiến OpenAPI công bố cả thông tin nội bộ; hãy xây dựng tình huống kiểm tra giới hạn schema response.
Một API trả về password hash trong model nội bộ nhưng chỉ muốn công bố tên người dùng và trạng thái tài khoản, trong khi tài liệu hiện mô tả toàn bộ model; hãy đặt bài toán phát hiện rò rỉ trường.
Một response dùng trường số điện thoại được che một phần tùy quyền của người đọc, nhưng OpenAPI chỉ công bố một định dạng cố định; hãy xây dựng tình huống đánh giá mô tả biến thể dữ liệu.
Một ứng dụng dùng các DTO có tên lớp trùng nhau ở hai package khác nhau, khiến phần components của OpenAPI có schema bị ghi đè hoặc đặt tên khó phân biệt; hãy đặt tình huống kiểm tra định danh schema.
Một hệ thống chuyển tên trường từ snake_case sang camelCase trong JSON, nhưng OpenAPI vẫn dùng cách đặt tên trước khi đổi cấu hình serialization; hãy xây dựng tình huống kiểm chứng sự đồng bộ.
Một DTO có thuộc tính bỏ qua khi serialize bằng Jackson, nhưng tài liệu lại hiển thị thuộc tính này trong response khiến bên tích hợp chờ dữ liệu không tồn tại; hãy đặt bài toán đối chiếu serializer và schema.
Một API trả dữ liệu theo JsonView tùy endpoint, nhưng hai endpoint cùng dùng một lớp Java và tài liệu hiển thị tập thuộc tính giống hệt nhau; hãy xây dựng tình huống kiểm chứng schema theo view.
Một ứng dụng dùng custom serializer cho mã đơn hàng, khiến JSON thực tế là chuỗi có tiền tố nhưng schema lại ghi số nguyên; hãy đặt tình huống kiểm tra hợp đồng sau tùy biến Jackson.
Một nhóm thêm ví dụ JSON để giúp đối tác tích hợp, nhưng ví dụ chứa các trường khác tên với schema và một giá trị enum không còn hợp lệ; hãy xây dựng tình huống đánh giá độ tin cậy của example.
Một hệ thống công bố giá trị mặc định của trường pagination trong OpenAPI, nhưng hành vi controller vừa đổi giới hạn mặc định khiến trang đầu trả dữ liệu khác dự kiến; hãy đặt bài toán kiểm chứng default.
Một endpoint hỗ trợ tải danh sách sản phẩm theo query page và size, nhưng Swagger UI biểu diễn size là tham số bắt buộc dù controller có giá trị mặc định; hãy xây dựng tình huống kiểm tra request parameter.
Một API tìm kiếm hỗ trợ nhiều tag trong một tham số query, nhưng tài liệu không mô tả cách tuần tự hóa danh sách và các client tạo URL khác nhau; hãy đặt tình huống đánh giá cách biểu diễn array.
Một controller lấy mã cửa hàng từ path variable, nhưng tài liệu lại mô tả mã cửa hàng trong query khiến đối tác gọi sai đường dẫn; hãy xây dựng tình huống đối chiếu nguồn tham số.
Một dịch vụ chấp nhận filter lồng nhau trong query object, nhưng trang Swagger UI tạo các tham số rời không phản ánh cách controller nhận dữ liệu; hãy đặt bài toán xác minh tham số phức hợp.
Một endpoint hỗ trợ sắp xếp theo nhiều trường bằng một tham số lặp lại, nhưng file OpenAPI chỉ cho một chuỗi đơn; hãy xây dựng tình huống kiểm tra hợp đồng cho request có tham số lặp.
Một API bắt buộc header X-Tenant-Id để xác định tổ chức, nhưng đặc tả chỉ mô tả request body và không nhắc đến header; hãy đặt tình huống kiểm chứng điều kiện đầu vào.
Một endpoint dựa trên cookie ngôn ngữ để chọn nội dung trả về, nhưng tài liệu không mô tả cookie và client thử nghiệm cho kết quả khác sản phẩm thật; hãy xây dựng tình huống kiểm tra tham số cookie.
Một service xuất báo cáo dùng tham số ngày bắt đầu và kết thúc trong query, nhưng schema không thể hiện định dạng date nên frontend gửi timestamp; hãy đặt tình huống kiểm chứng hợp đồng thời gian.
Một API quản lý file yêu cầu multipart/form-data gồm file và mã hồ sơ, nhưng Swagger UI dựng request JSON khiến upload thất bại; hãy xây dựng tình huống kiểm chứng định dạng request body.
Một endpoint cho phép upload nhiều ảnh trong cùng request, nhưng đặc tả chỉ mô tả một file làm ứng dụng đối tác không thể gửi album; hãy đặt bài toán xác minh schema multipart.
Một API cho phép tải file dạng binary, nhưng tài liệu mô tả response là JSON object và client generator cố parse dữ liệu nhị phân; hãy xây dựng tình huống kiểm tra media type.
Một controller hỗ trợ cả JSON và XML cho cùng endpoint, nhưng OpenAPI chỉ liệt kê application/json khiến người dùng tích hợp không biết định dạng còn lại; hãy xây dựng tình huống kiểm chứng content negotiation.
Một endpoint nhận application/merge-patch+json để cập nhật một phần tài nguyên, nhưng Swagger UI gửi application/json thông thường dẫn đến phản hồi 415; hãy đặt tình huống phân tích media type.
Một ứng dụng trả lỗi khi thiếu header Accept nhưng file OpenAPI lại công bố mọi kiểu response mà không phân biệt; hãy xây dựng tình huống đánh giá hành vi content negotiation.
Một service chấp nhận mã đơn có dấu gạch chéo được mã hóa trong path, nhưng tài liệu cung cấp ví dụ URL không phù hợp với cách routing thực tế; hãy đặt tình huống kiểm tra đường dẫn.
Một REST API sử dụng regex ràng buộc biến đường dẫn để giới hạn loại mã, nhưng tài liệu công bố path parameter không có giới hạn và bên tích hợp gửi giá trị sai; hãy xây dựng tình huống xác minh ràng buộc.
Một endpoint dùng API version trong header thay vì đường dẫn, nhưng hai phiên bản đang được mô tả thành một operation duy nhất và gây nhầm schema; hãy đặt bài toán quản lý biến thể hợp đồng.
Một controller có hai phương thức cùng path nhưng khác điều kiện consumes, khiến đặc tả chỉ giữ một operation và bỏ sót nhánh còn lại; hãy xây dựng tình huống kiểm chứng hành vi đa định dạng.
Một hệ thống có endpoint PATCH mà controller chỉ cập nhật một số trường, nhưng tài liệu lại dùng cùng schema với PUT và yêu cầu cả những trường không thay đổi; hãy đặt tình huống kiểm tra ngữ nghĩa cập nhật.
Một API tạo đơn hàng trả 201 kèm Location header nhưng tài liệu chỉ ghi 200 và không mô tả vị trí tài nguyên mới; hãy xây dựng tình huống đối chiếu hợp đồng thành công.
Một endpoint xóa tài nguyên trả 204 không có body, nhưng schema vẫn yêu cầu client đọc một object kết quả; hãy đặt tình huống xác minh mã trạng thái và nội dung response.
Một dịch vụ đăng ký tài khoản có thể trả 202 khi xử lý bất đồng bộ, nhưng OpenAPI chỉ công bố 201 làm đối tác hiểu rằng tài khoản đã sẵn sàng; hãy đặt bài toán kiểm chứng trạng thái nghiệp vụ.
Một API tra cứu hóa đơn trả 404 khi không có dữ liệu, nhưng tài liệu chỉ liệt kê 200 nên SDK sinh ra không xử lý trường hợp không tìm thấy; hãy xây dựng tình huống kiểm tra nhánh lỗi.
Một endpoint tạo phiếu yêu cầu có thể trả 409 khi trùng mã, nhưng đặc tả hiện chỉ ghi lỗi validation 400; hãy đặt tình huống kiểm chứng bộ mã lỗi nghiệp vụ.
Một bộ xử lý lỗi tập trung trả problem details theo một cấu trúc nhất quán, nhưng OpenAPI của từng controller vẫn mô tả lỗi dưới dạng chuỗi đơn giản; hãy xây dựng tình huống đối chiếu response lỗi.
Một ứng dụng chỉ hiển thị mã lỗi nội bộ trong response ở môi trường phát triển, nhưng tài liệu sinh trên máy lập trình đưa mã lỗi đó vào mô tả công khai; hãy đặt tình huống đánh giá rò rỉ chi tiết.
Một endpoint trả 429 khi bị giới hạn tốc độ nhưng tài liệu không công bố Retry-After header làm ứng dụng khách liên tục thử lại; hãy xây dựng tình huống kiểm tra hợp đồng lỗi hạn mức.
Một API yêu cầu If-Match để cập nhật bản ghi và có thể trả 412 khi phiên bản đã cũ, nhưng tài liệu không mô tả optimistic concurrency; hãy đặt bài toán kiểm chứng header và phản hồi.
Một controller sử dụng ResponseEntity với body khác nhau tùy nhánh lỗi, nhưng schema OpenAPI chỉ suy luận từ kiểu thành công và bỏ sót dữ liệu cảnh báo; hãy xây dựng tình huống kiểm tra.
Một endpoint được bảo vệ bởi quyền quản trị có thể trả 401 hoặc 403, nhưng OpenAPI chỉ mô tả 200 khiến đội kiểm thử bỏ qua trường hợp phân quyền; hãy đặt tình huống xác minh thông tin lỗi bảo mật.
Một dịch vụ trả lỗi 503 kèm mã theo dõi khi hệ thống phụ trợ không sẵn sàng, nhưng đặc tả không mô tả nhánh này khiến đối tác hiểu nhầm là lỗi không xác định; hãy xây dựng tình huống kiểm chứng.
Một API trả dữ liệu phân trang với Link header và thông tin tổng số bản ghi, nhưng OpenAPI chỉ mô tả mảng dữ liệu mà không có metadata điều hướng; hãy đặt tình huống đánh giá hợp đồng paging.
Một endpoint phục vụ stream sự kiện qua text/event-stream, nhưng đặc tả chỉ công bố response JSON thông thường và công cụ thử API giữ kết nối sai; hãy đặt tình huống kiểm tra dạng truyền dữ liệu.
Một ứng dụng có response 200 chứa body khi tìm thấy và response 304 không body khi cache còn hiệu lực, nhưng tài liệu không đề cập ETag; hãy xây dựng tình huống xác minh hành vi HTTP caching.
Một API tạo chứng từ trả file PDF nhưng mô tả content type là application/octet-stream cho mọi tải xuống, khiến client khó đặt tên và xử lý file; hãy đặt bài toán kiểm chứng response metadata.
Một controller khai báo hai mã lỗi nghiệp vụ cùng status 422 nhưng payload có trường khác nhau, trong khi OpenAPI chỉ nêu một ví dụ; hãy xây dựng tình huống đánh giá tính đầy đủ của ví dụ lỗi.
Một dịch vụ công bố mô hình lỗi chung trong components, nhưng sau refactor hai controller trả các trường lỗi khác nhau dù cùng tham chiếu một schema; hãy đặt tình huống kiểm tra độ nhất quán.
Một endpoint API dành cho khách vãng lai cho phép GET nhưng POST yêu cầu Bearer token, trong khi OpenAPI gắn yêu cầu bảo mật chung lên mọi operation; hãy xây dựng tình huống xác minh chính sách theo thao tác.
Một ứng dụng sử dụng HTTP Bearer JWT nhưng đặc tả mô tả apiKey trong header, khiến Swagger UI gửi token sai định dạng; hãy đặt tình huống kiểm tra định nghĩa security scheme.
Một API quản trị yêu cầu OAuth2 scope report.write nhưng tài liệu chỉ ghi có Bearer token nên người tích hợp không biết phạm vi quyền cần cấp; hãy xây dựng tình huống kiểm chứng yêu cầu scope.
Một hệ thống dùng OAuth2 Authorization Code để đăng nhập trên Swagger UI nhưng callback của giao diện thử API không được đăng ký ở authorization server; hãy đặt tình huống chẩn đoán luồng xác thực.
Một client Swagger UI sử dụng OAuth2 nhưng cấu hình authorization URL vẫn trỏ tới tenant thử nghiệm, khiến người dùng production nhận token từ sai nhà cung cấp; hãy xây dựng tình huống kiểm tra đường xác thực.
Một API vừa hỗ trợ OAuth2 vừa hỗ trợ API key cho các đối tác khác nhau, nhưng tài liệu thể hiện hai cơ chế thành yêu cầu đồng thời thay vì lựa chọn; hãy đặt tình huống đánh giá biểu thức security requirement.
Một endpoint nhận access token qua cookie trình duyệt, nhưng sơ đồ bảo mật trong OpenAPI mô tả token như query parameter khiến đối tác triển khai sai; hãy xây dựng tình huống kiểm chứng vị trí credential.
Một hệ thống có endpoint công khai để nhận webhook nhưng tài liệu gắn yêu cầu OAuth2 chung làm đối tác cho rằng phải gửi token người dùng; hãy đặt bài toán mô tả ngoại lệ bảo mật.
Một API đòi chứng chỉ mTLS ở gateway, nhưng đặc tả chỉ mô tả Bearer token nên đối tác có token hợp lệ vẫn không kết nối được; hãy xây dựng tình huống đánh giá hợp đồng bảo mật ngoài ứng dụng.
Một hệ thống phân quyền theo tenant lấy tenant ID từ header và JWT, nhưng OpenAPI chỉ công bố header mà không nhắc quan hệ với danh tính; hãy đặt tình huống kiểm tra thông tin yêu cầu truy cập.
Một nhóm công bố các scope OAuth2 quá rộng trong tài liệu API dù mọi endpoint chỉ cần phạm vi hẹp, khiến ứng dụng đối tác yêu cầu thừa quyền; hãy xây dựng tình huống đánh giá độ chính xác của scope.
Một ứng dụng dùng OpenID Connect discovery cho xác thực, nhưng OpenAPI mô tả thủ công các endpoint OAuth2 lỗi thời làm công cụ tích hợp đăng nhập thất bại; hãy đặt tình huống kiểm tra metadata bảo mật.
Một trang Swagger UI lưu token thử nghiệm để tái sử dụng qua reload trình duyệt, nhưng máy tính dùng chung khiến người tiếp theo có thể thử API bằng danh tính trước; hãy xây dựng tình huống đánh giá hành vi giao diện.
Một API cho phép tài khoản có vai trò nhân viên đọc dữ liệu nhưng chỉ quản trị viên được sửa, trong khi tài liệu mô tả cùng một scope ở cả hai operation; hãy đặt tình huống đối chiếu phân quyền thực thi.
Một đội dự án thêm endpoint nhạy cảm và chỉ che nó khỏi Swagger UI, nhưng endpoint thực tế vẫn có thể gọi bằng HTTP; hãy đặt tình huống đánh giá khác biệt giữa xuất bản tài liệu và bảo vệ API.
Một cổng tài liệu API công khai hiển thị ví dụ Authorization header chứa token còn hiệu lực từ môi trường thử nghiệm, khiến bất kỳ người xem nào cũng đọc được; hãy xây dựng tình huống kiểm tra dữ liệu ví dụ.
Một doanh nghiệp yêu cầu loại bỏ API nội bộ khỏi đặc tả phát cho đối tác, nhưng nhóm mới chỉ ẩn tab Swagger UI và file JSON vẫn chứa operation bí mật; hãy đặt tình huống xác minh bề mặt xuất bản.
Một hệ thống có nhóm OpenAPI cho API công khai, quản trị và đối tác, nhưng một controller có đường dẫn /internal bị đưa vào nhóm công khai qua quy tắc chọn package; hãy xây dựng tình huống phát hiện sai phạm vi.
Một ứng dụng có nhiều nhóm tài liệu với cùng một endpoint, nhưng schema request trong hai nhóm bị tùy biến khác nhau dẫn đến hai hợp đồng mâu thuẫn; hãy đặt tình huống kiểm chứng.
Một dịch vụ thay đổi tiền tố URL của API đối tác nhưng cấu hình GroupedOpenApi vẫn dùng path cũ, khiến đặc tả nhóm đối tác trở nên rỗng; hãy xây dựng tình huống điều tra quy tắc phân nhóm.
Một module được chuyển sang package mới sau refactor, khiến các operation của module biến mất khỏi nhóm OpenAPI dù controller vẫn xử lý bình thường; hãy đặt bài toán kiểm tra phụ thuộc theo package.
Một nhóm tạo tài liệu riêng cho phiên bản v1 và v2, nhưng endpoint đã ngừng hỗ trợ ở v1 vẫn xuất hiện trong bản đặc tả mới; hãy đặt tình huống xác minh phân tách vòng đời API.
Một API v2 dùng cùng đường dẫn nghiệp vụ nhưng thêm field bắt buộc, trong khi nhóm tài liệu v1 và v2 tham chiếu nhầm cùng một schema; hãy xây dựng tình huống đánh giá tương thích hợp đồng.
Một dịch vụ thêm endpoint beta chỉ dành cho khách hàng thử nghiệm, nhưng bản đặc tả công khai đã liệt kê trước khi tính năng được bật; hãy đặt tình huống kiểm tra trạng thái xuất bản.
Một ứng dụng có các nhóm API theo bộ phận, nhưng Swagger UI không tải được danh sách nhóm sau khi thay đổi đường dẫn cấu hình; hãy xây dựng tình huống chẩn đoán cơ chế chọn tài liệu.
Một gateway tập hợp tài liệu từ nhiều microservice, nhưng các operation có cùng operationId gây xung đột khi sinh một client SDK duy nhất; hãy đặt bài toán kiểm chứng định danh thao tác.
Một hệ thống có nhiều API trùng tên phương thức controller và sau refactor operationId thay đổi dù URL không đổi, khiến SDK đối tác phát sinh API client khác trước; hãy xây dựng tình huống đánh giá tính ổn định.
Một dịch vụ tạo nhóm API theo đường dẫn và annotation, nhưng route mới thuộc cả hai tiêu chí nên xuất hiện ở nhiều nhóm ngoài ý muốn; hãy đặt tình huống kiểm tra quy tắc lựa chọn.
Một ứng dụng sử dụng customizer để thêm header theo dõi vào mọi operation, nhưng endpoint public callback không chấp nhận header bắt buộc này; hãy xây dựng tình huống đánh giá phạm vi tùy biến.
Một nhóm thêm global response cho 500 vào OpenAPI, nhưng các operation vốn có nhiều loại content type bị ghi đè mô tả response; hãy đặt tình huống kiểm chứng thay đổi quy tắc dùng chung.
Một hệ thống muốn thống nhất tên và mô tả tag theo nghiệp vụ, nhưng controller từ module mới xuất hiện dưới tag mặc định gây khó tra cứu trong Swagger UI; hãy đặt tình huống đánh giá tổ chức tài liệu.
Một nhóm thay đổi thứ tự hiển thị các operation trên Swagger UI nhưng những endpoint nguy hiểm bị đặt lẫn với endpoint đọc dữ liệu công khai, khiến thao tác thử nhầm dễ xảy ra; hãy xây dựng tình huống kiểm tra trải nghiệm.
Một ứng dụng chạy sau proxy và Swagger UI mở được HTML nhưng không tải được cấu hình hoặc đặc tả JSON do đường dẫn tài nguyên không khớp; hãy đặt tình huống kiểm tra toàn bộ hành trình giao diện.
Một trang Swagger UI nội bộ cho phép Try it out trên API ghi dữ liệu production, nhưng quyền truy cập giao diện rộng hơn chính sách vận hành; hãy xây dựng tình huống đánh giá thao tác thử API.
Một cổng tài liệu mở trên domain riêng nhưng trình duyệt báo lỗi CORS khi Swagger UI gọi thử API ở domain dịch vụ, dù thao tác qua curl vẫn thành công; hãy đặt tình huống kiểm chứng môi trường trình duyệt.
Một ứng dụng cấu hình CSP nghiêm ngặt chặn các script cần thiết cho Swagger UI, khiến giao diện trắng dù endpoint OpenAPI JSON vẫn hoạt động; hãy xây dựng tình huống kiểm tra lớp bảo vệ HTTP.
Một trang Swagger UI hiển thị sai ký tự tiếng Việt trong mô tả API sau khi đặc tả đi qua CDN, nhưng JSON trực tiếp tại ứng dụng vẫn đúng; hãy đặt tình huống xác minh encoding và phân phối.
Một bộ phận bảo mật muốn dùng Swagger UI trong mạng nội bộ, nhưng đường dẫn UI bị public ingress phơi bày trên Internet sau thay đổi routing; hãy đặt bài toán kiểm tra quyền truy cập giao diện.
Một ứng dụng cho phép mở Swagger UI sau xác thực SSO, nhưng request tải đặc tả JSON bị 401 nên giao diện không liệt kê operation; hãy xây dựng tình huống kiểm chứng chuỗi request bảo mật.
Một nhóm tắt giao diện Swagger UI ở production nhưng endpoint xuất OpenAPI JSON vẫn công khai và chứa đường dẫn nội bộ; hãy đặt tình huống đánh giá chính sách công bố dữ liệu tài liệu.
Một đội vận hành cần xuất OpenAPI dưới dạng YAML cho cổng đối tác, nhưng dữ liệu YAML được xuất khác JSON về danh sách schema sau bước chuyển đổi; hãy đặt tình huống kiểm tra tính tương đương.
Một pipeline xuất đặc tả OpenAPI từ ứng dụng khởi chạy với profile test, khiến nhiều operation có điều kiện không xuất hiện trong bản tài liệu phát hành; hãy xây dựng tình huống đánh giá môi trường xuất.
Một nhóm đưa đặc tả OpenAPI vào repository để kiểm soát thay đổi, nhưng file xuất có thứ tự phần tử biến động khiến mỗi lần build tạo diff lớn dù API không đổi; hãy đặt tình huống kiểm chứng tính ổn định.
Một đối tác cần tải hợp đồng API từ đường dẫn tĩnh trên CDN, nhưng CDN còn giữ bản JSON của tháng trước sau khi backend cập nhật; hãy xây dựng tình huống đánh giá vòng đời cache.
Một dịch vụ công bố phiên bản API trong thông tin OpenAPI nhưng quên tăng version sau thay đổi response không tương thích, khiến đối tác tiếp tục dùng SDK cũ; hãy đặt tình huống phát hiện drift.
Một nhóm đặt mô tả deprecated cho endpoint cũ trong code nhưng bản đặc tả vẫn trình bày như operation đang được khuyến nghị; hãy xây dựng tình huống kiểm chứng vòng đời API.
Một client được sinh từ OpenAPI gặp lỗi compile sau khi server đổi tên thuộc tính enum, dù controller test thành công; hãy đặt tình huống kiểm tra tính tương thích client.
Một pipeline kiểm tra sự thay đổi OpenAPI giữa nhánh phát triển và bản phát hành gần nhất, nhưng chỉ so sánh số lượng endpoint và bỏ qua thay đổi required field; hãy xây dựng tình huống đánh giá độ sâu kiểm chứng.
Một bản phát hành đổi mã phản hồi từ 200 sang 204 nhưng vẫn có những client cũ kỳ vọng body JSON; hãy đặt tình huống xác minh breaking change dựa trên hợp đồng.
Một endpoint đổi tên path parameter từ orderId sang id nhưng giữ nguyên đường dẫn, khiến công cụ sinh SDK thay đổi chữ ký hàm; hãy xây dựng tình huống đánh giá tác động lên client.
Một ứng dụng thêm trường mới vào response được đánh dấu required, nhưng dữ liệu cũ trong database khiến một số response thiếu trường và vi phạm hợp đồng; hãy đặt tình huống kiểm thử dữ liệu thực.
Một contract test dùng OpenAPI để xác minh response 200 nhưng bỏ qua response lỗi 400 và 422, khiến backend thay đổi cấu trúc lỗi mà không bị phát hiện; hãy đặt bài toán đánh giá độ bao phủ.
Một service dùng JSON Schema trong OpenAPI để kiểm chứng payload nhưng dữ liệu trả về chứa trường không được mô tả, gây bất đồng về chính sách chấp nhận trường mở rộng; hãy xây dựng tình huống kiểm tra.
Một nhóm tạo stub server từ OpenAPI để frontend phát triển sớm, nhưng stub chấp nhận request không có header xác thực trong khi backend production từ chối; hãy đặt tình huống đánh giá giới hạn mock.
Một ứng dụng ký hợp đồng với đối tác dựa trên OpenAPI, nhưng bản tài liệu chứa mô tả response thành công khác với request/response được ghi nhận từ hệ thống; hãy đặt tình huống kiểm chứng hợp đồng thực thi.
Một API dùng file OpenAPI để sinh bộ kiểm thử nhưng các ví dụ mẫu toàn dữ liệu hợp lệ, khiến không có ca kiểm tra field thiếu và giá trị ngoài giới hạn; hãy đặt tình huống bổ sung kiểm thử âm tính.
Một thay đổi ở Bean Validation làm một trường từ tùy chọn thành bắt buộc, nhưng hệ thống chỉ chạy unit test cho service và bỏ qua diff OpenAPI; hãy xây dựng tình huống bảo vệ tương thích hợp đồng.
Một nhóm phát triển muốn xóa operation không còn người dùng nhưng chưa biết SDK của đối tác có đang sử dụng nó hay không; hãy đặt tình huống đánh giá điều kiện ngừng hỗ trợ API.
Một công cụ quản lý API yêu cầu gắn thông tin license và contact vào OpenAPI, nhưng artifact xuất thiếu metadata pháp lý sau khi thay đổi cấu hình; hãy xây dựng tình huống kiểm chứng trước phân phối.
Một đội triển khai công bố đặc tả bản v2 lên kho tài liệu, nhưng đường dẫn stable/latest vẫn trỏ tới v1 do quy trình phát hành thiếu bước cập nhật; hãy đặt tình huống kiểm thử phân phối.
Một nhóm tích hợp sử dụng OpenAPI YAML trong code generator phiên bản cũ, nhưng tài liệu được xuất với đặc tính schema mà generator đó không hỗ trợ; hãy đặt tình huống đánh giá mức tương thích công cụ.
Một dịch vụ thay đổi response schema cho endpoint tìm kiếm, khiến client TypeScript sinh từ OpenAPI có kiểu không phù hợp, nhưng các test REST chỉ xác minh HTTP 200; hãy xây dựng tình huống kiểm chứng xuyên chuỗi.
Một hệ thống phân phối tài liệu cho đối tác có hợp đồng khác nhau, nhưng kho artifact cho phép tài khoản của đối tác A tải đặc tả API riêng của đối tác B; hãy đặt bài toán kiểm chứng quyền truy cập.
Một báo cáo CI chỉ thể hiện rằng bước xuất OpenAPI thành công nhưng file thực tế chứa schema rỗng do các controller không được khởi tạo; hãy xây dựng tình huống kiểm tra chất lượng artifact.
Một ứng dụng có tính năng cung cấp OpenAPI JSON và YAML nhưng hai định dạng không được kiểm tra trên cùng profile, dẫn đến khác biệt về endpoint bị ẩn; hãy đặt tình huống đánh giá độ tương đương đầu ra.
Một nhóm thêm mô tả hợp đồng phản hồi cho endpoint streaming, nhưng công cụ thử API trong Swagger UI không quan sát được toàn bộ sự kiện và test chỉ kiểm tra kết nối thành công; hãy đặt tình huống xác định phạm vi kiểm chứng.
Một doanh nghiệp muốn tự động chặn merge khi API mới không mô tả quyền truy cập hoặc response lỗi, nhưng quy trình chỉ kiểm tra file JSON parse được; hãy xây dựng tình huống xác định quality gate.
Một sản phẩm có ba phiên bản API còn hỗ trợ và nhiều nhóm OpenAPI, nhưng tài liệu bản cũ bị ghi đè bởi artifact của bản mới trong quá trình deploy; hãy xây dựng tình huống kiểm tra tính bất biến phiên bản.
Một hệ thống dùng springdoc-openapi để mô tả REST API nhưng có endpoint thử nghiệm được sinh tự động từ actuator ở một profile, khiến tài liệu công khai khác giữa các môi trường; hãy đặt tình huống rà soát phạm vi xuất bản.
Một nhóm thay đổi tên trường và mô tả schema trực tiếp qua OpenAPI customizer nhưng quên đồng bộ DTO Java, khiến hợp đồng tuy hợp lệ về cú pháp nhưng response thực tế khác; hãy xây dựng tình huống kiểm chứng tính đúng ngữ nghĩa.
Một đội phát triển xây dựng trang tài liệu riêng dựa trên file OpenAPI, nhưng khi thêm nhóm mới đường dẫn tài liệu không được công bố khiến khách hàng không tìm thấy API; hãy đặt tình huống kiểm tra khả năng khám phá.
Một ngân hàng chuẩn bị công bố API cho đối tác và cần xác minh URL, scope OAuth2, mô hình lỗi và mẫu dữ liệu trên staging trước ngày phát hành; hãy xây dựng tình huống lập tiêu chí nghiệm thu hợp đồng.
Một tổ chức nâng cấp Spring Boot, springdoc-openapi và bộ sinh SDK trong cùng đợt phát hành, nhưng chưa có bằng chứng rằng đặc tả, Swagger UI và client đều tương thích; hãy đặt tình huống thiết kế kiểm thử hồi quy.
Một nền tảng muốn kiểm toán mọi thay đổi OpenAPI theo từng bản phát hành và liên kết chúng với endpoint thực tế, nhưng chỉ lưu bản YAML cuối cùng trong thư mục triển khai; hãy xây dựng tình huống kiểm tra khả năng truy vết.
