Một nhóm phát triển API đặt hàng dùng Spring REST Docs với MockMvc; sau khi đổi endpoint từ /orders sang /purchases, bài kiểm thử vẫn tạo snippet từ đường dẫn cũ và tài liệu xuất bản dẫn client tới URL không còn tồn tại.
Đội kiểm thử thiết lập MockMvcRestDocumentation trong một class tích hợp; controller khác được kiểm qua MockMvc chưa gắn cấu hình documentation nên request thành công nhưng không sinh snippet nào.
Ứng dụng quản lý khách hàng dùng MockMvcBuilders.standaloneSetup; test không nạp bộ converter và exception handler production nên snippet response khác với JSON mà client thực nhận.
Nhóm xây tài liệu bằng MockMvc đã gắn Spring Security filters; một bài test dùng user giả có đặc quyền và mô tả endpoint công khai dù request thực của khách nhận 403.
Đội dùng Spring REST Docs với @SpringBootTest và MockMvc; test context được tạo theo profile staging nhưng pipeline phát tài liệu như contract của profile production.
Ứng dụng chuyển từ servlet MVC sang WebFlux cho API thông báo; nhóm vẫn dùng cấu hình MockMvc cũ và không tài liệu hóa được đường reactive đã triển khai.
Đội tích hợp WebTestClientRestDocumentation vào WebTestClient; một test tạo client mới không cấu hình tài liệu nên các đoạn curl-request của endpoint báo cáo không xuất hiện.
Nhóm kiểm API WebFlux bằng WebTestClient.bindToController; những WebFilter triển khai thực tế không chạy nên tài liệu request headers thiếu trường bắt buộc để truy cập production.
Ứng dụng dùng WebTestClient.bindToServer với cổng ngẫu nhiên; snippet sinh absolute URL tới localhost và được sao chép nguyên vào tài liệu công bố cho đối tác.
Đội sử dụng REST Assured để kiểm API chạy trên cổng thật; RestAssuredRestDocumentation filter không được áp vào một nhóm request nên tài liệu phần xác thực được sinh thiếu.
Nhóm đổi thiết lập port và base URI của REST Assured giữa các test; snippet request của một endpoint mang port của server trước đó và người đọc không tái hiện được thao tác.
Ứng dụng có hai lớp test dùng MockMvc và REST Assured cùng document identifier; các test ghi snippet vào cùng thư mục và nội dung của lần chạy cuối ghi đè lần trước.
Đội tạo helper document chung cho tất cả request; helper sinh link và trường JSON mặc định nhưng một endpoint trả file nhị phân nên snippet không phản ánh response thực.
Nhóm thêm API POST thanh toán và chỉ kiểm HTTP 201; snippet được sinh từ response giả thiếu header Location trong khi contract đã hứa trả URI của giao dịch mới.
Ứng dụng đặt tên snippet theo tên method test có ký tự đặc biệt; đường dẫn output khác nhau giữa Windows và Linux khiến include trong Asciidoctor thất bại trên CI.
Đội chạy test có tên động theo tham số JUnit; identifier snippet của hai lần chạy trùng nhau và một ví dụ ngẫu nhiên được công bố thay cho tình huống đã chọn.
Nhóm sử dụng cùng operation identifier orders cho cả GET và POST; phần response-fields của hai thao tác ghi đè nhau khiến trang API mô tả nhầm cấu trúc trả về.
Ứng dụng cấu hình outputDir của Spring REST Docs tại build/generated-snippets; plugin Asciidoctor lại đọc target/generated-snippets nên build tài liệu thiếu các mảnh được tạo.
Đội tạo nhiều test diễn tả cùng endpoint bằng dữ liệu khác nhau; snippet trong tài liệu thay đổi theo test chạy cuối và giá trị ví dụ không ổn định.
Nhóm đưa việc sinh snippet vào phương thức @AfterEach của test; khi assertion thất bại trước đó, snippet không được tạo nhưng file cũ còn trong thư mục build.
Ứng dụng tạo test kiểm API với trạng thái 200 và 404; cùng identifier output được dùng cho hai trường hợp khiến tài liệu lỗi bị ghi lên ví dụ thành công.
Đội xây tài liệu cho endpoint sử dụng multipart; test chỉ gửi metadata JSON nên snippet không có Content-Type và các phần file bắt buộc.
Nhóm dùng MockMvc để tạo ví dụ header Authorization; token thật từ test environment được ghi nguyên vào snippet và xuất hiện trong tài liệu chia sẻ bên ngoài.
Ứng dụng có test POST nhận cookie session; snippet request chưa xóa giá trị cookie riêng của tài khoản test và CI xuất bản thông tin không phù hợp.
Đội áp dụng bộ tiền xử lý preprocessRequest với prettyPrint cho mọi payload; request chứa văn bản thuần và dữ liệu nhị phân không tương thích cách định dạng JSON nên test tài liệu thất bại.
Nhóm áp dụng preprocessResponse với prettyPrint vào API trả ảnh PNG; bộ tiền xử lý không hiểu nội dung nhị phân và tài liệu không sinh được ví dụ phản hồi.
Ứng dụng đặt base URI công khai trong cấu hình snippet; reverse proxy thực có tiền tố /platform mà ví dụ HTTP vẫn dùng đường dẫn root cũ.
Đội lọc header khỏi đoạn http-request để tránh tiết lộ token; một header X-Tenant-ID là bắt buộc cũng bị ẩn khiến khách sao chép lệnh rồi nhận lỗi.
Nhóm dựng tài liệu bằng bài test controller dùng bean mock; các biến thể lỗi của downstream không được mô phỏng nên trang chỉ chứa happy path.
Ứng dụng chuyển một endpoint từ JSON sang HAL; bài test vẫn dùng Accept application/json nên tài liệu không hiển thị các liên kết hypermedia mà client mới cần.
Đội tài liệu hóa tạo voucher bằng requestFields; DTO có trường code bắt buộc mới nhưng test vẫn dùng payload cũ và kiểm thử tài liệu thất bại khi schema thay đổi.
Nhóm mô tả requestFields cho hồ sơ khách hàng; trường address là object lồng nhau nhưng mô tả chỉ nói address dạng String và client gửi dữ liệu không phù hợp.
Ứng dụng nhận danh sách lineItems trong JSON; FieldDescriptor chỉ mô tả phần tử đầu qua chỉ số cố định nên ví dụ có nhiều dòng không được kiểm đúng cấu trúc.
Đội dùng fieldWithPath cho mảng products; một trường price mới được thêm vào mỗi item nhưng tài liệu vẫn thiếu đơn vị tiền tệ và làm đối tác tính tổng sai.
Nhóm thiết kế API PATCH cập nhật địa chỉ; descriptor đánh dấu mọi field là bắt buộc dù backend cho phép chỉ gửi một thuộc tính và client ép người dùng nhập thừa.
Ứng dụng có trường promoCode tùy chọn; tài liệu requestFields không đánh dấu optional nên công cụ đọc tài liệu hiểu rằng request thiếu code là không hợp lệ.
Đội đánh dấu trường accountId là ignored trong snippet; trường này thực tế là tham số quan trọng của request và tài liệu tạo ra không mô tả cách định danh tài khoản.
Nhóm dùng relaxedRequestFields để tránh test thất bại khi DTO thay đổi; một trường role nhạy cảm được thêm vào payload hợp lệ nhưng không được bất kỳ snippet nào nêu.
Ứng dụng dùng strict requestFields cho endpoint đã đóng băng contract; một header hoặc field metadata vô hại được thêm vào test fixture làm test tài liệu lỗi, kéo chậm phát hành.
Đội mô tả fieldWithPath cho thời điểm giao hàng dạng String; contract thực dùng ISO offset timestamp nhưng tài liệu chỉ đưa ví dụ local datetime không có múi giờ.
Nhóm có field tổng tiền BigDecimal; snippet JSON ví dụ được tạo bằng Double và mất độ chính xác khi đối tác lấy ví dụ làm đầu vào tích hợp.
Ứng dụng nhận enum fulfillmentStatus ở request; mô tả chỉ ghi String nhưng không nêu tập giá trị được chấp nhận nên client gửi tên hiển thị thay vì mã enum.
Đội tạo DTO chứa Map dynamic attributes; việc mô tả các khóa cố định trong requestFields khiến dữ liệu của tenant mới không khớp kiểm thử.
Nhóm chuyển field customerName từ bắt buộc thành tùy chọn; snippet vẫn được tạo từ fixture luôn có tên nên thay đổi ràng buộc không được thể hiện.
Ứng dụng dùng requestFields cho object payment; một field nested chỉ được phép khi method=card nhưng tài liệu đang mô tả như luôn có thể gửi cùng các phương thức.
Đội ghi tài liệu hóa password reset token trong request body; ví dụ được tạo với token thực còn hiệu lực và được đăng lên cổng tài liệu công khai.
Nhóm thiết lập requestFields mô tả số lượng item; dữ liệu test có quantity dương nhưng không kiểm giá trị âm nên hợp đồng validation chưa được phản ánh.
Ứng dụng có cùng tên field amount ở hai object nested; hai FieldDescriptor được định nghĩa sai đường dẫn và tài liệu hoán đổi ý nghĩa tiền gốc với tiền giảm.
Đội dùng subsectionWithPath để mô tả toàn bộ details object; trường nhạy cảm vừa được thêm vào details không làm test fail và bị công bố trong response ví dụ.
Nhóm tạo snippet với beneathPath để tài liệu hóa một phần collection; đường dẫn extractor chọn item đầu nhưng payload production không luôn có phần tử đầu.
Ứng dụng mô tả responseFields cho API danh sách khách; một thuộc tính email mới được đưa vào response ngoài chính sách truy cập nhưng test tài liệu dùng relaxedResponseFields nên không báo.
Đội kiểm responseFields nghiêm ngặt cho GET /orders; Jackson thêm một trường metadata vào response làm bài kiểm thử tài liệu fail dù API nghiệp vụ vẫn hoạt động.
Nhóm định nghĩa responseFields cho ProblemDetail; endpoint mới trả trường errors bổ sung trong validation nhưng phần mô tả lỗi chỉ còn title và detail.
Ứng dụng dùng responseFields cho endpoint trả Page<Order>; các thuộc tính pagination thay đổi theo phiên bản Spring Data làm test tài liệu thất bại ở profile mới.
Đội tạo ví dụ response với một record; trường list rỗng bị serializer bỏ khỏi JSON làm descriptor của list không được kiểm và tài liệu không nói cách xử lý rỗng.
Nhóm dùng relaxedResponseFields cho một endpoint xuất thông tin người dùng; trường internalNotes bất ngờ xuất hiện trong JSON mà test tài liệu không chặn thay đổi.
Ứng dụng trả HTTP 204 cho DELETE; nhóm cấu hình responseFields như một object bình thường và bài test không thể mô tả response body vốn không tồn tại.
Đội tạo response JSON với trường result có thể là null; FieldDescriptor mô tả luôn có object và client triển khai sai khi nghiệp vụ không tìm thấy bản ghi.
Nhóm trả hai kiểu response theo trạng thái đơn; bộ test chỉ tạo ví dụ PENDING và không ghi nhận các liên kết cùng field chỉ có khi trạng thái COMPLETED.
Ứng dụng trả JSON có dữ liệu polymorphic theo loại hàng; snippet chỉ mô tả biến thể vật lý và client không biết loại hàng dịch vụ được biểu diễn khác.
Đội dùng responseFields để mô tả nested array trong report; một kiểu dữ liệu BigDecimal bị serialize thành String ở môi trường production và không được tài liệu hóa.
Nhóm kiểm response từ WebTestClient với JSON có danh sách trống; phần descriptor cho các item không có giá trị đại diện và tài liệu thiếu cấu trúc phần tử.
Ứng dụng báo lỗi đối tác qua response chứa nested cause; test snippet không loại các field chứa chi tiết hạ tầng nên tài liệu công bố cấu trúc hệ thống nội bộ.
Đội mô tả các field thời gian trong response; ví dụ chạy ở môi trường máy CI dùng múi giờ khác và tài liệu thay đổi mỗi lần build.
Nhóm dùng responseFields mô tả link download; URL ví dụ mang hostname nội bộ của pod thay vì domain mà người dùng bên ngoài có thể truy cập.
Ứng dụng có response chứa tên cá nhân tiếng Việt; quá trình tạo tài liệu không giữ UTF-8 và snippet hiển thị ký tự lỗi trên portal.
Đội so sánh tài liệu response với JSON schema đã công bố; các tên property vẫn khớp nhưng tính optional và nullability khác nên client sinh từ schema chạy sai.
Nhóm muốn mô tả các response khi API rate limited; bộ test chỉ kiểm 200 nên snippet không có header Retry-After và dạng lỗi HTTP 429.
Ứng dụng trả 401 khi thiếu token và 403 khi thiếu quyền; tài liệu từ một test admin hợp lệ không giúp client phân biệt hai điều kiện lỗi.
Đội xây snippet pathParameters cho GET /users/{userId}; tài liệu ghi ID kiểu số nhưng controller mới nhận UUID khiến đối tác gửi định dạng không phù hợp.
Nhóm dùng pathParameters trong MockMvcRestDocumentation; một @PathVariable được đổi tên từ orderId sang id nhưng tài liệu và test vẫn dùng tên cũ.
Ứng dụng có route nested /stores/{storeId}/products/{productId}; snippet chỉ mô tả productId nên bên tích hợp không hiểu tham số storeId là bắt buộc.
Đội tạo test cho path segment có dấu gạch chéo mã hóa; URI ví dụ trong snippet được render khác cách proxy xử lý và client không tìm thấy tài nguyên.
Nhóm có API tìm kiếm với queryParameters cho page, size và sort; thêm tham số status nhưng chưa cập nhật descriptor nên bài test tài liệu báo thiếu trường được mô tả.
Ứng dụng cho phép lặp nhiều query parameter category; snippet mô tả category như một String đơn nên đối tác bỏ qua khả năng lọc theo nhiều loại.
Đội đổi tên tham số query từ sortBy thành sort; backend vẫn hỗ trợ alias cũ tạm thời nhưng tài liệu chỉ sinh ví dụ endpoint legacy.
Nhóm tạo snippet cho query parameter optional includeDetails; test luôn đặt true nên tài liệu không mô tả kết quả khi người gọi bỏ tham số.
Ứng dụng nhận filter ngày với giá trị UTC; queryParameters mô tả date mà không nêu timezone nên hai đối tác tích hợp ra kỳ báo cáo khác nhau.
Đội dùng formParameters để mô tả form đăng nhập; controller đã đổi sang application/json nhưng snippet vẫn được tạo từ giao diện form cũ.
Nhóm gửi một request kết hợp query parameter và form fields; tài liệu trộn cả hai thành cùng một bảng làm client gửi sai vị trí dữ liệu.
Ứng dụng có endpoint truyền marker phân trang qua query; ví dụ sử dụng cursor đã hết hạn trong lúc tài liệu được đọc và client nhận lỗi khi sao chép.
Đội tạo snippet requestParameters theo thói quen phiên bản cũ; sau khi nâng Spring REST Docs, quy ước mô tả query và form khác làm tài liệu không có nhóm tham số như mong đợi.
Nhóm bổ sung một path variable với mẫu regex; snippet không nêu giới hạn định dạng nên ví dụ của khách dùng ký tự không phù hợp và nhận 404.
Ứng dụng sử dụng queryParameters trên endpoint GET với filter tùy chọn; một request thiếu hoàn toàn filter cho response khác nhưng tài liệu chỉ chứa ví dụ có filter.
Đội dùng requestHeaders để mô tả Authorization và X-Correlation-ID; một endpoint mới yêu cầu X-Tenant-ID nhưng tài liệu không được cập nhật và khách nhận 400.
Nhóm thay cơ chế xác thực Bearer token; snippet requestHeaders vẫn mô tả Basic Authorization và code mẫu trên portal không thể gọi API.
Ứng dụng có header Idempotency-Key cho POST thanh toán; tài liệu chỉ mô tả body nên đối tác retry không có key và tạo giao dịch trùng.
Đội gắn header Accept-Language vào request; snippet không nêu trường này nên client nhận thông báo lỗi bằng ngôn ngữ không mong muốn.
Nhóm thiết kế responseHeaders ghi Location của tài nguyên mới; một lần refactor bỏ header nhưng test tài liệu vẫn xác minh chỉ status code và không phát hiện thay đổi.
Ứng dụng trả responseHeaders gồm ETag cho cập nhật có điều kiện; tài liệu không hướng dẫn If-Match ở lần ghi tiếp theo nên client dễ ghi đè thay đổi đồng thời.
Đội dùng responseHeaders để ghi Cache-Control; một cấu hình proxy mới đổi max-age nhưng tài liệu vẫn đưa ví dụ cũ và client cache quá lâu.
Nhóm có header RateLimit-Remaining trong response; test chỉ nhận một lần gọi nên giá trị ví dụ không phản ánh cách giới hạn được tính theo tenant.
Ứng dụng yêu cầu Content-Type application/vnd.company.v2+json; snippet request hiển thị application/json do test dùng converter mặc định và người đọc nhận 415 khi gửi.
Đội xử lý Accept application/hal+json cho tài nguyên HATEOAS; tài liệu responseFields mô tả domain data nhưng bỏ _links và _embedded cần thiết cho điều hướng.
Nhóm sử dụng links() trong Spring REST Docs để mô tả rel tự tham chiếu; endpoint trả rel next khi có phân trang nhưng test tài liệu chỉ dùng một trang.
Ứng dụng có link rel download chỉ xuất hiện với người đã thanh toán; test tài liệu dùng user admin và client thường hiểu nhầm liên kết này luôn khả dụng.
Đội bật snippet links cho response HAL; một custom rel mới được thêm mà không cập nhật mô tả và bài kiểm thử tài liệu báo thay đổi hợp đồng.
Nhóm dùng relaxedLinks để bỏ qua rel mới; một liên kết nhạy cảm trỏ tới endpoint quản trị được thêm ngoài ý muốn nhưng không bị test cảnh báo.
Ứng dụng đổi rel từ cancel thành refund theo trạng thái Order; một test chỉ xem JSON field trạng thái mà không kiểm link được phát cho client.
Đội kiểm Content-Disposition trong response tải báo cáo; filename có dấu tiếng Việt bị encode sai nhưng snippet headers chỉ chứa tên file ASCII.
Nhóm mô tả requestCookies cho phiên đăng nhập; một client dùng Bearer token không có cookie nhận response khác và tài liệu không phân biệt hai cơ chế truy cập.
Ứng dụng kiểm responseCookies cho refresh token; token HttpOnly bị thiết lập sai nhưng bài test chỉ assert status 200 và không mô tả các thuộc tính cookie.
Đội tạo test multipart requestParts cho upload ảnh; một phần metadata JSON có tên khác so với tài liệu khiến client gửi form đúng file nhưng thiếu metadata.
Nhóm dùng requestPartFields để mô tả JSON metadata đi kèm MultipartFile; trường checksum bị bổ sung nhưng snippet từ test cũ chưa nhắc tới tính toàn vẹn tệp.
Ứng dụng upload nhiều attachments trong cùng request; phần mô tả chỉ có một requestPart và client không biết cách gửi nhiều file cùng tên field.
Đội tài liệu hóa file upload với MIME type image/png; backend chấp nhận cả PDF và ảnh nhưng phần tài liệu không thể hiện quy tắc kích thước và loại tệp.
Nhóm dùng snippet mô tả body của download PDF; quá trình sinh raw response bytes vào tài liệu làm tập tài liệu tăng dung lượng và không có ví dụ dễ đọc.
Ứng dụng trả streaming file với Transfer-Encoding chunked; test controller trong MockMvc chỉ ghi một phần response và ví dụ tài liệu gây hiểu nhầm về kích thước kết quả.
Đội cần hướng dẫn multipart trong REST Assured; request mẫu chạy được trong test nhưng snippet command line thiếu đường dẫn file mà người đọc có thể tạo.
Nhóm muốn mô tả header chữ ký webhook; token ví dụ được tạo ngẫu nhiên mỗi lần test nên snapshot tài liệu thay đổi và không thể dùng lâu dài.
Ứng dụng dùng requestHeaders cho traceparent; ví dụ lưu một trace ID thật ở CI khiến nhóm hỗ trợ nhầm tưởng tài liệu đang mô tả giao dịch production.
Đội thêm response header cảnh báo deprecation; bài test không kiểm header nên tài liệu vẫn quảng bá endpoint như hợp đồng ổn định.
Nhóm đặt header Vary: Accept-Language cho response đa ngôn ngữ; snippet không mô tả cơ chế cache phân biệt và client thấy nội dung từ locale khác.
Ứng dụng cần tài liệu hóa thông số header X-Request-ID bắt buộc; bài test dùng filter tự sinh ID khi thiếu nên tài liệu không thể hiện yêu cầu với client thật.
Đội ghi responseCookies trong tài liệu logout; cookie xóa phiên không được đặt Max-Age đúng nhưng testcase không kiểm thuộc tính response để phát hiện.
Nhóm thiết kế API lỗi dùng ProblemDetail; tài liệu phần response-fields chưa mô tả traceId ở extension properties nên đội hỗ trợ không biết cách tra cứu sự cố.
Ứng dụng dùng @ControllerAdvice chuẩn hóa lỗi validation; test REST Docs chỉ kiểm một trường sai và không mô tả dạng danh sách errors khi nhiều trường vi phạm.
Đội trả lỗi 409 cho optimistic locking; tài liệu chỉ có ví dụ 400 và 500 nên client không biết có thể lấy lại version mới và thử cập nhật.
Nhóm mô tả endpoint POST tạo đơn; lỗi downstream 503 trả Retry-After nhưng snippet chưa được sinh từ trường hợp đối tác bảo trì.
Ứng dụng triển khai phân quyền theo tenant; test tài liệu dùng một tenant duy nhất nên ví dụ không nói rõ vì sao cùng ID có thể trả 404 hoặc 403.
Đội dùng relaxedResponseFields cho lỗi 500; một lỗi runtime trả stack trace trong body và phần tài liệu không phát hiện thông tin bị rò rỉ.
Nhóm tạo snippet error response bằng mock exception; exception thật khi gọi database có wrapper khác làm error code production khác mô tả.
Ứng dụng trả 422 cho nghiệp vụ hết hạn voucher; bộ tài liệu vẫn ghi 400 vì test chỉ tạo request vi phạm định dạng đầu vào.
Đội tạo bảng phản hồi HTTP status trong Asciidoctor bằng tay; khi controller đổi 409 sang 412, snippet kiểm thử không cập nhật bảng viết thủ công.
Nhóm dùng requestFields và responseFields cho endpoint trả PagedModel; các trường phân trang có cấu trúc khác giữa trang rỗng và có dữ liệu, nhưng test chỉ ghi một trường hợp.
Ứng dụng tài liệu hóa DELETE có status 204; một client xem ví dụ cũ 200 với body và lỗi parse khi môi trường mới không trả nội dung.
Đội có endpoint GET hỗ trợ If-None-Match; tài liệu từ một lần gọi 200 không đề cập phản hồi 304 mà client cache có thể nhận.
Nhóm muốn mô tả retry khi API trả 429; tài liệu được sinh từ test không thiết lập giới hạn truy cập thật nên không có ví dụ lỗi rate limit.
Ứng dụng trả lỗi auth trong Spring Security filter trước controller; cấu hình test standalone không chạy filter và tài liệu không sinh được phản hồi 401 thực.
Đội tích hợp OAuth2 vào API nội bộ; ví dụ request từ MockMvc dùng @WithMockUser nên không có Authorization header đúng cách gửi của client.
Nhóm bảo trì REST Docs trong dự án có nhiều API profiles; một endpoint chỉ bật trong production nhưng test profile cũng dựng đường dẫn giả nên tài liệu công khai API không tồn tại.
Ứng dụng có đường dẫn API bị gateway rewrite; snippet được sinh từ MockMvc trong app không có prefix nên tài liệu public URL bị thiếu đoạn /api/v2.
Đội dùng operationPreprocessors để thay host staging bằng public host; bộ tiền xử lý còn sót một trường Location chứa địa chỉ nội bộ và ví dụ không thống nhất.
Nhóm muốn loại thông tin nhạy cảm khỏi snippet bằng preprocessRequest; một trường số tài khoản nằm sâu trong JSON vẫn xuất hiện ở ví dụ đã xuất bản.
Ứng dụng tạo token JWT giả cho test tài liệu; công cụ xử lý snippet không che phần Bearer token nên người đọc nghĩ token mẫu còn có thể dùng để truy cập.
Đội xây tài liệu tương tác từ các snippet có email khách; dữ liệu fixture giống dữ liệu thật của một nhân viên và bị công bố lên portal ngoài tổ chức.
Nhóm dùng prettyPrint trên JSON có chuỗi chứa dấu xuống dòng; ví dụ do preprocessing thay đổi cách escaping làm đối tác hiểu nhầm payload hợp lệ.
Ứng dụng mô tả webhook nhận JSON với chữ ký raw body; tài liệu snippet dùng body đã prettyPrint nên người tích hợp ký lại chuỗi đẹp hóa và bị từ chối chữ ký.
Đội sử dụng preprocessResponse để bỏ các ID ngẫu nhiên; một giá trị business identifier cũng bị thay nên ví dụ phản hồi không còn phù hợp đường link self.
Nhóm muốn tài liệu ổn định trên mọi lần build; test tạo Instant.now và UUID mới nên cả snippets lẫn HTML thay đổi dù API không đổi.
Ứng dụng sinh ví dụ phân trang từ dữ liệu database dùng chung; thứ tự trả dữ liệu không ổn định và snippet đầu tiên đôi khi ghi một khách khác.
Đội dùng một tài khoản fixture trên nhiều test; trạng thái tài khoản thay đổi trong suite khiến response đã sinh khác nhau tùy thứ tự thực thi.
Nhóm chạy test REST Docs song song trong JUnit; nhiều testcase viết cùng identifier snippet và tạo file bị trộn nội dung hoặc bị ghi đè.
Ứng dụng xây tài liệu từ kết quả kiểm thử chạy trên CI nhiều JVM fork; từng fork ghi output vào một thư mục chung và artifact có snippet của bài test không liên quan.
Đội chạy Gradle test và asciidoctor song song không khai báo phụ thuộc task; Asciidoctor xử lý trước khi snippet được sinh xong nên tài liệu thiếu nhiều ví dụ.
Nhóm dùng Gradle outputDir được đặt trong build/generated-snippets; lần chạy clean xóa mọi snippet nhưng task asciidoctor được đánh dấu up-to-date và không tái tạo tài liệu.
Ứng dụng cấu hình Maven Surefire sinh snippets trong target/generated-snippets; plugin Asciidoctor chạy ở phase sớm hơn integration tests nên tài liệu không có snippet từ các endpoint thật.
Đội dùng Maven Failsafe cho bài test API; task tạo documentation chỉ phụ thuộc unit test và không chờ failsafe verify nên artifact xuất bản thiếu các hợp đồng tích hợp.
Nhóm dùng asciidoctorj để biên soạn từ AsciiDoc; môi trường build mới thiếu thuộc tính snippets khiến macro include không tìm được đoạn mô tả request/response.
Ứng dụng chia tài liệu thành nhiều file AsciiDoc include; một include trỏ sai case của identifier và trang đặt hàng hiển thị ví dụ của API trả hàng.
Đội tạo template Asciidoctor để chèn snippets; marker include nằm trong code block không phù hợp làm nội dung HTTP bị diễn giải thành định dạng khác.
Nhóm muốn phát tài liệu từ Markdown thay vì Asciidoctor; bộ template snippet đang sinh AsciiDoc và trang Markdown hiển thị nguyên ký hiệu bảng không đọc được.
Ứng dụng dùng REST Docs snippet templates tùy biến; một template response-fields đang bỏ cột mandatory nên bảng tài liệu không thể hiện sự khác biệt field tùy chọn.
Đội đổi bố cục bảng request parameters trong template tùy chỉnh; một số field có mô tả chứa dấu thẳng đứng làm Asciidoctor tách sai số cột.
Nhóm nhập mô tả FieldDescriptor bằng tiếng Việt; HTML sinh từ Asciidoctor không thiết lập encoding phù hợp và các dấu tiếng Việt trở thành ký tự lỗi.
Ứng dụng tạo tài liệu song ngữ từ cùng snippets; trường mô tả tiếng Anh được giữ trong bản tiếng Việt vì template tùy biến không có ngữ cảnh locale.
Đội tích hợp Asciidoctor PDF để tạo tài liệu gửi kiểm toán; hình và bảng snippet dài tràn lề trang khiến các trường quan trọng không thể đọc.
Nhóm sinh Markdown API reference từ response-fields snippets; đường dẫn asset relative không phù hợp cấu trúc portal nên các ví dụ bị mất khi chuyển thư mục.
Ứng dụng tạo tài liệu HTML qua Asciidoctor ở build pipeline; môi trường offline không tải được extension ngoài và job thất bại dù kiểm thử HTTP đã pass.
Đội phát tài liệu lên website sau khi test; bước upload lấy artifact HTML của build trước vì tên file trùng và bộ cache CDN chưa được làm mới.
Nhóm lưu snippets trong thư mục source control để tiện xem diff; các file tự sinh mới bị commit nhưng file cũ không được dọn khiến tài liệu có endpoint đã xóa.
Ứng dụng tổ chức snippet IDs theo tên controller; một lần refactor controller đổi tên tất cả đường include dù URL và hợp đồng HTTP không đổi.
Đội dùng cấu trúc snippet theo phiên bản API; một test v2 dùng identifier của v1 và tài liệu cũ bất ngờ hiển thị response mới.
Nhóm ghép một trang tổng hợp từ các request/response snippets; ví dụ request và response thuộc hai testcase khác nhau nên ID giao dịch không khớp.
Ứng dụng muốn versioning tài liệu theo Git tag; pipeline chạy trên branch main nhưng xuất bản vào thư mục phiên bản trước nên người dùng thấy hợp đồng bị thay đổi ngầm.
Đội chạy build trên Linux còn developer xem docs trên Windows; đường dẫn và separator output snippet khác nhau khiến include chỉ hoạt động trên một hệ điều hành.
Nhóm chuyển build từ Maven sang Gradle; location generated snippets thay đổi và pipeline release vẫn đóng gói tài liệu từ vị trí cũ.
Ứng dụng có module API độc lập trong multi-module Gradle; task docs chạy ở root nhưng snippets được sinh ở module con, dẫn tới website chứa trang trắng.
Đội sử dụng một task tổng hợp tài liệu từ nhiều microservices; hai service có cùng snippet ID /users-get và artifact của service thứ hai ghi đè service thứ nhất.
Nhóm phát hành tài liệu public với các snippet private admin; cấu hình chọn trang AsciiDoc chưa loại module nội bộ và làm lộ hợp đồng endpoint không được phép chia sẻ.
Ứng dụng xây tài liệu trong pipeline chỉ khi toàn bộ test pass; một test contract đang bị disabled nên snippet cũ vẫn được dùng và endpoint mới không có kiểm chứng.
Đội thêm endpoint mới nhưng quên tạo test REST Docs; tài liệu vẫn được build thành công vì không có kiểm tra độ bao phủ giữa controller mappings và các trang reference.
Nhóm cấu hình task tạo tài liệu bỏ qua test trong bản release gấp; artifact được sinh từ snippet đã tồn tại và không thể chứng minh khớp với binary vừa phát hành.
Ứng dụng chấp nhận thay đổi API breaking theo feature flag; bài test tài liệu luôn bật flag mới trong khi khách production còn dùng hợp đồng cũ.
Đội bật cache cho task documentation để tăng tốc CI; thay đổi response DTO chưa làm mất cache key và trang HTML vẫn mô tả schema của commit trước.
Nhóm tạo AsciiDoc thủ công cho endpoint đang dùng; một đoạn mô tả nghiệp vụ ngoài snippet không được kiểm thử và tiếp tục ghi trường đã bị loại.
Ứng dụng đính kèm bản HTML REST Docs vào release artifact; package chứa binary từ commit mới nhưng tài liệu từ commit cũ và đội tích hợp phát hiện sai sau deploy.
Đội dùng REST Docs để lập hợp đồng cho API không công khai; CI upload toàn bộ generated-snippets lên artifact server không có hạn chế truy cập.
Nhóm cần đối chiếu thay đổi tài liệu trong pull request; snapshot HTML đổi timestamp và ID ví dụ ngẫu nhiên khiến reviewer khó nhận ra một field bắt buộc mới.
Ứng dụng lưu snippets có thông tin token giả trong CI logs; cấu hình artifact retention quá lâu làm dữ liệu thử nghiệm và endpoint nội bộ vẫn được chia sẻ sau khi project kết thúc.
Đội có pipeline kiểm docs bằng Asciidoctor nhưng không kiểm link href; một URL reference tới schema bên ngoài bị xóa và trang vẫn được xuất bản không cảnh báo.
Nhóm nâng phiên bản Spring REST Docs cùng Spring Framework; một số API cấu hình preprocessor và snippets thay đổi khiến build lỗi chỉ ở runner release.
Ứng dụng kết hợp Spring REST Docs với OpenAPI generator từ snippet; một endpoint có mô tả thiếu ràng buộc validation nên schema xuất ra không phản ánh controller.
Đội muốn xuất tài liệu tương tác qua một extension bên ngoài; extension đọc response-fields nhưng không hiểu descriptor của array nested và sinh schema không chính xác.
Nhóm quản lý REST Docs trong cả MockMvc và WebTestClient tests; một endpoint migrated sang reactive trả media type khác nhưng hai bộ snippet vẫn được gộp một trang như cùng contract.
Ứng dụng dùng REST Assured test qua HTTPS nội bộ; cấu hình trust certificate chỉ có trong test khiến ví dụ curl công khai không giải thích yêu cầu mTLS đối với client.
Đội ghi mẫu HTTP request của endpoint upload file; lệnh sao chép từ tài liệu không có cách truyền metadata JSON part đúng Content-Type và đối tác nhận 415.
Nhóm muốn tài liệu hóa response streaming SSE; một test chờ response hoàn tất trong khi stream được thiết kế chạy lâu nên job sinh snippet bị timeout.
Ứng dụng dùng WebTestClient để lấy một số event đầu từ Flux; response snippet chỉ chứa một event và client tưởng kết nối sẽ đóng sau event đó.
Đội tạo tài liệu cho WebSocket handshake bằng kiểm thử HTTP; test chỉ mô tả 101 Switching Protocols và không có thông tin về message protocol phía sau.
Nhóm thử tài liệu REST API trả redirect 302; snippet chỉ giữ response ban đầu nhưng client REST Assured tự follow redirect và ghi lại nội dung endpoint đích.
Ứng dụng sử dụng OpenAPI làm nguồn tham khảo chính và REST Docs làm tài liệu kiểm chứng; hai nguồn khác trạng thái optional fields và không có kiểm tra đối chiếu lúc release.
Đội chuẩn hóa lỗi API theo RFC Problem Details; response-fields snippets trong một module vẫn mô tả lỗi tùy biến cũ khiến frontend phải xử lý hai cấu trúc.
Nhóm muốn chắc chắn tài liệu phản ánh chính xác HTTP status; các test REST Docs sinh snippet mà không assert status trước document nên ví dụ 500 có thể bị công bố như kết quả thành công.
Ứng dụng đổi quyền endpoint từ public sang chỉ admin; test REST Docs chạy với credential admin hợp lệ nên tài liệu không chỉ ra thay đổi yêu cầu xác thực.
Đội tạo snippet response từ object mock do test dựng sẵn; serialization ở production thêm field và custom header từ filter nên tài liệu không bao phủ hợp đồng HTTP thực.
Nhóm dùng relaxed descriptors để giữ CI xanh khi API phát triển nhanh; việc thiếu mô tả các trường mới làm người dùng tài liệu không thể nhận biết khả năng mới.
Ứng dụng sử dụng strict descriptors cho hệ thống thanh toán; một response chỉ có trường trong tình huống lỗi hiếm chưa được kiểm và việc phát hành API mới bị đánh giá thiếu.
Đội muốn đảm bảo test tài liệu độc lập theo môi trường; một snippet sinh absolute URL có hostname của runner cá nhân khiến release đổi nội dung dù source không thay.
Nhóm đổi quy ước ID của các tài nguyên từ số sang UUID; tài liệu từ fixture cũ vẫn gợi ý ID kiểu số và khách tích hợp nhận lỗi validation.
Ứng dụng đổi API list từ offset sang cursor pagination; bảng queryParameters vẫn mô tả page/size và client không biết cách theo cursor tiếp theo.
Đội chuyển một endpoint từ application/json sang multipart/form-data; trang tài liệu còn request-fields của JSON làm đối tác gửi payload sai dạng dù test khác đã chạy.
Nhóm mở rộng API chấp nhận đồng thời v1 và v2 trong giai đoạn chuyển đổi; một trang tài liệu ghép request v1 với response v2 và làm người đọc hiểu sai khả năng tương thích.
Ứng dụng đưa REST Docs vào CI để làm tài liệu sống; một bộ test stale luôn mock service trả payload cũ và pipeline vẫn xanh dù hợp đồng runtime đã thay đổi.
Đội muốn đánh giá mức tin cậy của tài liệu từ kiểm thử; số endpoint chỉ có happy-path snippets cao trong khi các tình huống lỗi mạng, auth và validation chưa được kiểm.
Nhóm xây tài liệu cho hàng trăm endpoint bằng snippets sinh tự động; một lỗi naming convention làm nhiều đoạn request và response của hai tài nguyên khác nhau bị đặt chung thư mục.
Ứng dụng dùng response-fields để mô tả dữ liệu cá nhân; sau thay đổi chính sách quyền truy cập, ví dụ response ở tài liệu không còn phản ánh dữ liệu mà user thường được xem.
Đội làm bộ tài liệu cho bản canary; endpoint đã đổi trong canary nhưng tài liệu vừa publish trỏ tới stable và khách không thể tái hiện response ví dụ.
Nhóm quản lý API gồm một số endpoint nội bộ chỉ mở theo feature flag; cấu hình test bật tất cả nên trang tài liệu công bố chức năng chưa được phép triển khai.
Ứng dụng cần đối soát tài liệu sinh từ HTTP tests với log production; cùng request khi gửi qua gateway nhận thêm header và URI prefix khác mà bài test không mô phỏng.
Đội phát hành website tài liệu từ Asciidoctor cùng JAR ứng dụng; một lỗi kiểm thử khiến task test bị skip nhưng task publish vẫn chạy và công bố hợp đồng chưa được xác nhận.
Nhóm trực sự cố cần tra cứu request mẫu trong REST Docs; phiên bản tài liệu không chứa commit SHA và không thể xác định ví dụ có đúng với bản service đang phục vụ hay không.
