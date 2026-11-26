Một nền tảng bán lẻ chuyển API sản phẩm sang Spring HATEOAS với RepresentationModel; DTO cũ được trả trực tiếp ở một endpoint khiến client không tìm thấy liên kết self như ở các endpoint còn lại.
Nhóm quản lý đơn hàng dùng EntityModel<OrderDto> để trả chi tiết đơn; khi controller chuyển sang URL mới, liên kết self vẫn trỏ đường dẫn hard-code của phiên bản trước.
Ứng dụng CRM tạo RepresentationModel cho hồ sơ khách hàng; một số object có ID chưa được sinh khi assembler chạy nên liên kết self chứa giá trị null.
Đội phát triển gắn metadata nghiệp vụ và các Link vào cùng một DTO; tên thuộc tính của domain trùng cấu trúc hypermedia khiến JSON gửi ra khác hợp đồng đã công bố.
Một API thư viện dùng EntityModel để biểu diễn cuốn sách; quá trình serialization sau nâng thư viện làm client cũ không nhận diện được vị trí các liên kết.
Nhóm xuất danh sách tài khoản bằng CollectionModel; từng account không có liên kết riêng nên client không thể điều hướng từ tập hợp đến chi tiết tài khoản.
Ứng dụng quản lý kho trả CollectionModel với các item đúng; danh sách rỗng không có link collection self làm client không biết cách tải lại khi kho có hàng mới.
Đội dùng CollectionModel chứa DTO thông thường thay vì các representation con; khách cần mở từng sản phẩm nhưng không có đường dẫn điều hướng tương ứng.
Nhóm triển khai PagedModel cho danh sách hóa đơn; metadata page đã tồn tại nhưng link next được tạo ngay cả khi không còn trang kế tiếp.
Một hệ thống có 100.000 đơn hàng trả PagedModel; link last được tính trên tổng số từ query khác điều kiện lọc nên client đi tới trang không tồn tại.
Đội sử dụng PagedModel cho kết quả tìm kiếm; tham số sort bị bỏ khỏi link next khiến các trang tiếp theo đổi thứ tự và xuất hiện item trùng.
Ứng dụng tạo PagedModel từ Page đã lọc theo tenant; link first chứa thiếu tenant criteria và mở ra kết quả từ phạm vi dữ liệu khác.
Nhóm xử lý API phân trang theo page index bắt đầu từ 0; client của đối tác giả định trang bắt đầu từ 1 và link tiếp theo dẫn sai dữ liệu.
Một dịch vụ dùng cursor pagination nhưng trả metadata giống offset PagedModel; client tin rằng có thể truy cập trang cuối bằng số trang dù backend chỉ hỗ trợ cursor.
Đội thêm filter theo nhiều trạng thái vào endpoint tìm đơn; link prev do assembler dựng không giữ toàn bộ query parameters và kết quả chuyển trang bị lệch.
Ứng dụng gửi representation của một người dùng gồm nhiều danh sách con; link orders trỏ sai ID do assembler lấy mã hiện tại của một singleton thay vì ID của đối tượng.
Nhóm thiết kế response CustomerModel với thuộc tính address dạng object; một client tưởng mọi object nested đều là representation độc lập nhưng không có link chi tiết địa chỉ.
Đội tạo representation cho mỗi dòng hóa đơn bằng một entity con; người dùng bấm link item nhưng resource thực chỉ tồn tại trong ngữ cảnh hóa đơn cha.
Ứng dụng tổng hợp DashboardModel từ nhiều domain entity; self link mô tả trạng thái dashboard nhưng không có đường điều hướng về từng báo cáo thành phần.
Nhóm lưu các Link vào một RepresentationModel mutable dùng chung; request của tenant A vô tình nhìn thấy link được thêm ở lần xử lý tenant B.
Đội dùng RepresentationModelAssembler để chuyển Order thành OrderModel; một code path trả EntityModel tự tạo và thiếu các liên kết do assembler chuẩn phát hành.
Ứng dụng xây lớp assembler cho sản phẩm và dùng lại trong controller danh sách; assembler gọi service tìm quyền cho từng item khiến trang 100 sản phẩm tạo hàng trăm truy vấn.
Nhóm xây RepresentationModelAssemblerSupport cho nhiều subtype sản phẩm; một subtype mới không được ánh xạ đúng resource type và link hành động liên quan bị thiếu.
Đội phát triển đặt bean assembler ở module web phụ; test context thiếu bean nhưng production có nhiều bean cùng interface và controller inject nhầm assembler.
Ứng dụng dùng assembler gọi repository để lấy dữ liệu phụ cho mỗi item; khi tập kết quả lớn, quá trình tạo hypermedia trở thành phần tốn thời gian nhất của request.
Nhóm refactor tên class controller nhưng assembler xây link theo tên đường dẫn literal; unit test model đạt còn HTTP link thực tế dẫn tới 404.
Đội thêm API REST phiên bản mới cho cùng domain; assembler hiện gắn link tự tham chiếu tới phiên bản mới vào representation do controller phiên bản cũ trả về.
Ứng dụng sử dụng HATEOAS với ID có ký tự slash được mã hóa; link được dựng bằng cách nối chuỗi khiến router hiểu ID thành nhiều path segment.
Nhóm chuyển mã khách hàng từ Long sang UUID; link URI do assembler dựng từ kiểu cũ vẫn có định dạng số và client không tra được khách mới.
Đội dùng WebMvcLinkBuilder.linkTo với methodOn để xây link controller; method signature thay đổi tham số bắt buộc làm đường dẫn được tạo không mang thông tin query cần thiết.
Ứng dụng có nhiều route @GetMapping cùng tên phương thức theo consumes và produces; link builder chọn metadata không phù hợp và tạo link chỉ hoạt động với một media type.
Nhóm dùng WebMvcLinkBuilder dựa trên proxy controller; một method không thể được proxy theo cấu trúc class hiện tại khiến lỗi tạo link xuất hiện khi serialization.
Đội tạo link tới controller có path variable nested; builder thiếu biến của path cấp class nên URI trong response có template chưa được mở rộng.
Ứng dụng có @RequestMapping ở controller và @GetMapping ở method; một thay đổi prefix qua cấu hình làm link được tạo không khớp routing đang chạy sau gateway.
Nhóm muốn link self của OrderModel trỏ tới endpoint lấy đơn; assembler lại tham chiếu method trả danh sách và mọi item có cùng URL.
Đội dùng linkTo(methodOn(...)) cho thao tác xóa đơn; link trỏ tới đúng URI nhưng client lại gửi GET và nhận 405 do không biết phương thức HTTP khả dụng.
Ứng dụng có một controller @PathVariable với nhiều tham số; thứ tự truyền ID trong linkTo không đúng khiến link sản phẩm mở thông tin biến thể khác.
Nhóm triển khai một controller ở servlet context /api; WebMvcLinkBuilder tạo link với base path khác khi chạy sau load balancer và khách ngoài mạng nhận 404.
Đội khai báo ForwardedHeaderFilter sau reverse proxy; liên kết self được tạo bằng host nội bộ của pod thay vì domain công khai mà khách đang sử dụng.
Ứng dụng đi qua proxy HTTPS nhưng nhận header X-Forwarded-Proto sai; link tự sinh dùng HTTP và trình duyệt chặn request điều hướng từ trang HTTPS.
Nhóm cấu hình X-Forwarded-Host từ client không tin cậy; hypermedia self link chứa tên miền do client đưa vào và có nguy cơ chuyển hướng người dùng.
Đội dùng linkTo trên request MVC không có ngữ cảnh HTTP như scheduled job; URI gốc không được xác định theo domain cần có trong thông báo email.
Ứng dụng chạy ở hai region với domain khác nhau; cùng assembler xây absolute links theo từng host và cache chung phát nhầm domain của region khác.
Nhóm xử lý request từ API gateway có prefix /platform; URI của link collection thiếu prefix do proxy không truyền thông tin đường dẫn đầy đủ.
Đội tạo link relative để tránh host nội bộ; một client mobile ghép URL tương đối theo base không đúng và chuyển tới endpoint ngoài tài nguyên hiện tại.
Ứng dụng cần link đến tài nguyên ở dịch vụ khác; builder dựa vào controller nội bộ không có route tương ứng và phát hành đường dẫn 404.
Nhóm đặt trailing slash không nhất quán giữa controller và link builder; một số client đi qua proxy tự chuyển hướng và mất header xác thực.
Đội dùng HTTP URI template cho link tìm kiếm sản phẩm; tên biến query trong template khác @RequestParam thực tế nên client gửi request có filter không được nhận.
Ứng dụng tạo templated Link với tham số page và size; một client coi toàn URI có dấu ngoặc nhọn là đường dẫn literal và gửi request lỗi.
Nhóm mở rộng URI template cho danh sách category; các ký tự đặc biệt trong category không được encode đúng khiến kết quả tìm kiếm khác giá trị người dùng chọn.
Đội phát hành link search có tham số tùy chọn; một client luôn gửi chuỗi rỗng khiến backend áp filter thay vì bỏ qua điều kiện.
Ứng dụng thêm tham số locale vào link danh sách; những link đã cache thiếu locale nên người dùng chuyển trang và mất ngôn ngữ đã chọn.
Nhóm có link download kèm token thời hạn ngắn; representation được cache lâu hơn thời hạn token nên người dùng bấm link đã hết hạn.
Đội tạo link self của tài nguyên composite key; ID ghép bằng dấu hai chấm gây lỗi trong một client tự phân tách URI thành hai phần.
Ứng dụng sử dụng path traversal check trên router; một ID chứa dấu chấm và hai dấu chấm được encode khác nhau giữa link builder và gateway.
Nhóm muốn chuyển từ absolute links sang relative links trong cùng API; client cũ lưu absolute URI làm khóa cache và coi tài nguyên cũ là đối tượng khác.
Đội thêm tham số version vào URI template; các client chỉ biết mở link đã mở rộng cũ không đáp ứng được tham số mới bắt buộc.
Ứng dụng có link tự mô tả đến trạng thái workflow; endpoint trạng thái chuyển từ GET sang POST nhưng rel vẫn được phát hành như thao tác đọc.
Nhóm xây Link với rel self nhưng vô tình dùng tên rel là item; một client dùng _links.self.href để tải lại tài nguyên và không tìm thấy.
Đội tạo nhiều Link cùng rel related cho một Order; một client chỉ lấy một href đầu và bỏ sót các kiện hàng liên quan.
Ứng dụng sử dụng IANA link relations như self, next và prev; một custom client nhận diện quan hệ theo chữ hoa nên không điều hướng đúng.
Nhóm đặt custom rel approve không có namespace rõ; một API khác cũng dùng approve với ngữ nghĩa khác khiến client tích hợp hiểu nhầm hành động.
Đội dùng LinkRelation tùy biến cho invoice-download; sau khi đổi tên rel thành receipt, client cũ không còn tìm được PDF dù URL endpoint vẫn hoạt động.
Ứng dụng áp LinkRelationProvider để đặt tên collection relations; thay đổi quy tắc số nhiều làm _embedded.orders chuyển sang _embedded.orderItems trong cùng phiên bản API.
Nhóm tạo custom rel cho endpoint hủy đơn; liên kết được thêm cho cả đơn đã giao và giao diện cho người dùng thấy thao tác không còn hợp lệ.
Đội đặt rel alternate tới tài nguyên CSV; link không có type metadata và client dùng parser JSON cho response CSV, làm tải báo cáo thất bại.
Ứng dụng công bố rel describedby để chỉ tài liệu schema; URL tài liệu được chuyển sang host mới nhưng assembler vẫn trả domain cũ.
Nhóm thêm rel canonical cho tài nguyên có nhiều alias; một client dùng link self làm ID lâu dài và lưu hai bản cho cùng thực thể.
Đội dùng rel collection cho trang danh sách theo tổ chức; link về collection chung không gắn tenant và trả 403 khi người dùng điều hướng.
Ứng dụng phát hành link up từ một LineItem về Order; đối tác tích hợp đặt giả định mọi item có cùng một parent và lỗi khi sản phẩm chuyển đơn.
Nhóm muốn link next của bộ sưu tập có tiêu chuẩn ổn định; query sắp xếp theo updatedAt đổi liên tục và client đọc trùng item giữa các trang.
Đội mô hình hóa quy trình thanh toán qua các Link available actions; response đơn chưa thanh toán lại chứa rel refund và người dùng hiểu nhầm có thể hoàn tiền.
Ứng dụng quản lý hồ sơ hiển thị link edit cho chủ sở hữu; chính sách phân quyền thay đổi nhưng assembler vẫn thêm link dựa vào role cũ từ session.
Nhóm dùng security principal để quyết định link delete; một tác vụ nền không có principal nhưng vẫn sử dụng assembler và trả link không tương ứng quyền thật.
Đội kiểm trạng thái Order là PAID trước khi thêm rel cancel; trạng thái thay đổi đồng thời sau khi representation được tạo nên client gọi link nhận 409.
Ứng dụng chỉ phát link pay cho đơn PENDING; client được quyền truy cập đơn nhưng không đủ hạn mức tài khoản và link dẫn đến thao tác liên tục bị 403.
Nhóm xây affordance cho hành động approve đơn; link vẫn hiện cho một user bị tạm khóa vì logic hiển thị chỉ kiểm trạng thái đơn.
Đội thiết kế danh sách hành động dựa vào permission service; gọi permission service từng item trong trang lớn làm response HATEOAS chậm khi mạng gặp sự cố.
Ứng dụng thêm link admin vào representation theo role; representation được cache công khai và người dùng thường nhận response có link đặc quyền.
Nhóm coi việc ẩn link delete là đủ để bảo vệ endpoint; client tự gọi URL thao tác dù link bị ẩn và backend chưa kiểm quyền đầy đủ.
Đội trả rel edit dựa trên dữ liệu quyền tải lúc đầu request; role bị thu hồi trong khi user đang thao tác và client vẫn thấy hành động cũ.
Ứng dụng hiển thị link upload-document khi hồ sơ thiếu tệp; trạng thái hồ sơ đổi sang LOCKED nhưng link vẫn còn trên một response được cache.
Nhóm phát hành rel retry cho tác vụ thất bại; một tác vụ đã được worker khác khởi chạy lại nhưng client vẫn dùng link cũ và tạo công việc trùng.
Đội muốn client chỉ dựa vào rel để biết hành động được phép; các trường hợp nghiệp vụ trả 422 dù link đã được phát làm trải nghiệm không nhất quán.
Ứng dụng thiết kế workflow onboarding theo trạng thái tài nguyên; các bước nhảy trạng thái không có link chuyển tiếp khiến client phải hard-code endpoint mới.
Nhóm có nghiệp vụ duyệt hoàn tiền hai cấp; representation chỉ có rel approve chung nên client không phân biệt phê duyệt cấp một và cấp hai.
Đội thiết kế link reject dành cho người kiểm duyệt; một user vừa là người tạo vừa là người duyệt vẫn thấy link trái chính sách phân tách nhiệm vụ.
Ứng dụng trả link action dựa trên trạng thái lưu ở read replica; replica trễ so với primary và link thao tác được phát khi hành động đã hết hiệu lực.
Nhóm tạo Link với rel assign-driver cho phiếu giao hàng; xe đã được đặt bởi request khác và client nhấn link thì bị xung đột phiên bản.
Đội cần thể hiện các hành động không khả dụng trên giao diện; API chỉ phát link khả dụng khiến client không phân biệt không có quyền với hành động chưa đúng trạng thái.
Ứng dụng cấp quyền theo tenant và vùng địa lý cho tài nguyên; assembler chỉ nhìn tenantId nên một nhân viên thấy link từ vùng không thuộc quyền quản lý.
Nhóm tối ưu HATEOAS bằng cache link theo productId; quyền khác nhau theo user làm cache trả tập link thao tác của người khác.
Đội triển khai chính sách hủy đơn mới yêu cầu mã lý do; link cancel vẫn được phát nhưng không mô tả dữ liệu đầu vào khiến client cũ gửi request thiếu trường.
Ứng dụng dùng Spring HATEOAS affordances để mô tả hành động cập nhật; form hiển thị các trường nội bộ vì metadata đầu vào gắn trực tiếp với entity persistence.
Nhóm thêm affordance cho PUT cập nhật hồ sơ; DTO mới có trường bắt buộc nhưng mô tả mẫu hành động chưa cập nhật và client gửi payload không đủ.
Đội cung cấp affordance cho hành động approve bằng POST; một client coi link như GET nên gây lỗi phương thức HTTP khi người dùng bấm nút.
Ứng dụng khai báo nhiều affordances trên cùng một Link; client chỉ chọn affordance đầu và gửi DELETE thay cho PATCH trong một trạng thái đặc biệt.
Nhóm muốn biểu diễn input metadata trong HAL-FORMS; một thuộc tính enum dùng mã mới mà template client vẫn hiển thị các lựa chọn cũ.
Đội triển khai HAL-FORMS template cho tạo đơn; danh sách fields hiển thị id và createdAt vốn do server quản lý nên client có thể gửi giá trị không nên sửa.
Ứng dụng xuất affordance action từ controller method signature; một validation group chỉ dùng ở update không được thể hiện đúng trong metadata input.
Nhóm sử dụng action affordance với trường amount dạng BigDecimal; client dựa vào schema đơn giản và gửi String khác định dạng tiền tệ được chấp nhận.
Đội thêm affordance tạo tài nguyên mới vào collection; người dùng không có quyền tạo vẫn thấy template POST vì assembler không xét permission.
Ứng dụng mô tả action theo HTTP method; API xử lý PATCH theo merge semantics nhưng template không cho client biết ý nghĩa của null và field bị bỏ qua.
Nhóm khai báo affordance cho submit hồ sơ với media type JSON; client gửi form-url-encoded theo template cũ và nhận 415 từ backend.
Đội tạo link transition về trạng thái đã hoàn tất; một action không idempotent bị client gửi lại sau timeout và xử lý thanh toán hai lần.
Ứng dụng hỗ trợ affordance có input collection item; một client chỉ gửi phần tử đầu vì template chưa mô tả cardinality của danh sách.
Nhóm muốn mẫu action có liên kết tới các lựa chọn tỉnh thành; dữ liệu lựa chọn thay đổi theo quốc gia nhưng metadata template đang cố định.
Đội cấu hình affordance theo nhóm quyền quản trị; khi tạo representation ở tiến trình batch không có request context, input metadata lộ trường đặc quyền.
Ứng dụng sử dụng HAL-FORMS để mô tả tác vụ cancel; client dùng template cũ sau khi trạng thái thay đổi và action trả 409 dù trước đó rel còn tồn tại.
Nhóm phát hành affordance chứa trường lý do từ chối; một template có tham số không còn dùng nhưng client vẫn bắt người dùng nhập vì hợp đồng chưa được cập nhật.
Đội tạo interface client điều hướng theo action rel; khi affordance bị loại trong phiên bản mới, client không có hành vi dự phòng và giao dịch bị bỏ dở.
Ứng dụng biểu diễn báo cáo dạng HAL application/hal+json; một client gửi Accept application/json và nhận response khác media type đã xây dựng.
Nhóm chuyển controller từ JSON thuần sang HAL; dữ liệu domain chuyển sang các thuộc tính _links và _embedded làm parser cũ không đọc được danh sách item.
Đội trả HAL collection khi không có item; serializer vẫn phát _links nhưng bỏ _embedded, khiến client giả định luôn có mảng và phát lỗi.
Ứng dụng xuất HAL với _embedded.orders khi có kết quả; client trước đó lấy trực tiếp trường orders và hiển thị danh sách rỗng dù endpoint trả 200.
Nhóm định nghĩa rel tùy biến cho _embedded; naming strategy khác giữa hai assembler và cùng một loại tài nguyên xuất hiện dưới hai khóa khác nhau.
Đội dùng EntityModel với ID trong data và self link; một đoạn mapping đổi tên ID field nhưng client chỉ dựa vào self vẫn có thể điều hướng, còn client cũ lệ thuộc ID thì lỗi.
Ứng dụng có link tài nguyên quan hệ ở _links nhưng cũng nhúng đầy đủ object ở _embedded; client không biết trường nào là nguồn dữ liệu cập nhật mới nhất.
Nhóm nhúng Customer vào Order trong HAL để giảm round trips; một vòng tham chiếu Order-Customer làm biểu diễn tăng kích thước hoặc lặp vô hạn.
Đội chọn embedded summary cho Invoice thay vì chi tiết; client cũ giả định có đủ line items và tính tổng sai ở màn hình hóa đơn.
Ứng dụng muốn nhúng toàn bộ comments trong bài viết; các bài có hàng chục nghìn bình luận tạo response quá lớn và chậm qua mạng di động.
Nhóm dùng HAL relation links cho tài nguyên liên quan nhưng không nhúng; frontend hiện gọi thêm một request cho mỗi item và latency tăng theo danh sách.
Đội xây serializer HAL tùy biến để thêm metadata; một trường _links nghiệp vụ vô tình ghi đè trường điều hướng do Spring HATEOAS sinh.
Ứng dụng bật cơ chế HAL qua cấu hình media types; một test chỉ chấp nhận application/json nên không kiểm được response khi client yêu cầu application/hal+json.
Nhóm cập nhật Jackson ObjectMapper dùng chung cho API; converter không còn module hypermedia cần thiết nên Link bị serialize thành các thuộc tính Java thông thường.
Đội chuyển từ Jackson tùy biến sang cấu hình Spring HATEOAS; output của Optional field và null property khác trước làm client hợp đồng nghiêm ngặt lỗi.
Ứng dụng gửi HAL representation chứa nhiều rel giống nhau; client parser vốn chỉ hỗ trợ một object link không xử lý được khi rel có nhiều href.
Nhóm dùng HAL Link với property templated; serializer phát URL template nhưng một app mobile cũ không nhận diện thuộc tính templated và mở link nguyên văn.
Đội thiết kế CURIE để rút gọn rel tùy biến; một client không mở rộng được prefix nên không nhận diện quan hệ business được tài liệu hóa.
Ứng dụng đổi CURIE prefix của rel riêng từ acme sang shop; payload gọn hơn nhưng client đã hard-code prefix và không tìm thấy action link.
Nhóm dùng CURIE prefix trùng với một module khác trong HAL; client resolve rel sang tài liệu khác và chọn hành động không đúng ngữ nghĩa.
Đội công bố profile link cho representation; tài liệu profile không phản ánh field mới và client tạo form thiếu thông tin cần thiết.
Ứng dụng sử dụng HAL response cho các lỗi nghiệp vụ; client kỳ vọng ProblemDetail và không biết diễn giải cùng request giữa success và error.
Nhóm thiết kế HAL _links.next cho tìm kiếm; URI tiếp theo sử dụng query được encode hai lần nên client không lấy được trang mới.
Đội đặt link self trong mỗi embedded resource; một tài nguyên thuộc nhiều tập hợp nên cùng self xuất hiện khác host do assembler dùng request URL hiện tại.
Ứng dụng nhúng ảnh đại diện vào CustomerModel với URL riêng; một số client tưởng đó là HAL link để theo dõi và bỏ qua field ảnh nằm trong data.
Nhóm sử dụng HAL-FORMS cho thao tác đăng ký; Accept header của client vẫn là application/hal+json nên không nhận được metadata form như kỳ vọng.
Đội dùng HTTP content negotiation để chọn HAL và HAL-FORMS; hai loại representation có action metadata khác nhau làm client gửi cùng POST với payload không tương thích.
Ứng dụng trả Content-Type application/hal+json nhưng thực tế body đã được một filter đổi sang JSON thuần; trình phân tích HAL của client không tìm được _links.
Nhóm có error handler tạo JSON chuẩn nội bộ cho tất cả request; API HAL trả lỗi không kèm type và rel cần thiết khiến client khó xác định bước phục hồi.
Đội triển khai gzip cho HAL response lớn; client cache ETag từ bản không nén rồi so sánh trên bản có nén và hành vi revalidation bị sai.
Ứng dụng xác định LinkRelation theo bản địa hóa; khi user đổi ngôn ngữ, rel cũng đổi theo khiến client không nhận ra quan hệ ổn định.
Nhóm đặt title mô tả cho Link theo locale người dùng; title được cache chung làm người dùng tiếng Việt nhìn mô tả tiếng Anh dù rel và href vẫn đúng.
Đội tạo HATEOAS resource từ controller có @RequestMapping phiên bản; client dùng media-type versioning khác path version và link dẫn về phiên bản không mong muốn.
Ứng dụng tạo link từ assembler gọi controller method; mapping được điều chỉnh qua proxy rewrite và link chỉ đúng trong môi trường local không đi qua gateway.
Nhóm xây link về chính tài nguyên theo request Host; hệ thống có nhiều domain vanity và cache dùng chung khiến href của domain tenant này xuất hiện ở tenant khác.
Đội đặt canonical self link là absolute URI; khi đổi domain thương hiệu, ID tài nguyên đã lưu trong client không còn khớp với self mới.
Ứng dụng chuyển endpoint từ /customers/{id} sang /members/{id}; client đúng tinh thần hypermedia vẫn theo rel, còn client hard-code path bị lỗi khi điều hướng.
Nhóm thay rel update-profile bằng edit-profile; đường dẫn và HTTP method không đổi nhưng client tra rel cũ không còn tìm thấy thao tác.
Đội thêm rel verify-email ở bản mới nhưng không xóa rel cũ deprecated; một client chọn action cũ trước và gửi request đến endpoint sẽ bị gỡ bỏ.
Ứng dụng phát link deprecation tới tài liệu mới; URL tài liệu lỗi 404 khiến khách tích hợp không biết lịch thay đổi hợp đồng API.
Nhóm version resource representation theo media type; client dùng Accept application/hal+json chung và nhận field cũ trong khi đang chờ bản schema mới.
Đội thêm trường bắt buộc mới trong representation; client hypermedia chỉ đọc _links vẫn hoạt động, nhưng client dùng strict JSON schema từ bản cũ từ chối response.
Ứng dụng xóa một relation link ít dùng trong phiên bản mới; một hệ thống đối tác lấy rel đó làm bước bắt buộc và quy trình không còn tiếp tục được.
Nhóm đổi logic khi nào link cancel xuất hiện; client cũ có fallback hard-code endpoint và tiếp tục gửi hủy dù API không phát hành hành động này nữa.
Đội đưa hành động archive vào một rel mới; client đang hiển thị nút dựa vào danh sách rel cố định nên người dùng không thấy chức năng mới.
Ứng dụng cho phép resource chuyển trạng thái trong lúc client giữ representation cũ; link được phát hợp lệ trước đó nay trả 409 và client không biết cần refresh.
Nhóm sử dụng Last-Modified để cache OrderModel; action links thay đổi vì quyền user nhưng entity chưa đổi timestamp nên client tiếp tục thấy quyền cũ.
Đội tạo ETag chỉ từ dữ liệu Order; link edit tùy principal thay đổi nhưng response 304 giữ representation cũ chứa hành động không còn cho phép.
Ứng dụng đặt Cache-Control public cho HAL response theo trạng thái; response còn link nhạy cảm đến báo cáo riêng và bị cache trung gian phục vụ người khác.
Nhóm muốn giảm dữ liệu truyền nên bỏ _links khỏi các response cache hit; một client điều hướng từ bản cache không thể mở các tài nguyên liên quan.
Đội chuyển from eager embedding sang link-only để tiết kiệm băng thông; client cũ trông chờ object trong _embedded và tăng số request hoặc hiển thị thiếu dữ liệu.
Ứng dụng phân biệt resource identifier với URL; một client dùng self.href làm ID database và mất khả năng tìm object sau khi chuyển domain.
Nhóm có API tài nguyên tạm thời với link self hết hạn; client lưu URI trong bookmark và nhận 410 nhưng không có rel tìm tài nguyên thay thế.
Đội tạo alias rel canonical cho tài nguyên được sáp nhập; client vẫn theo self cũ và không cập nhật khi backend trả link canonical mới.
Ứng dụng cần mô tả trạng thái pagination đồng nhất giữa các phiên bản; một phiên bản dùng page count còn phiên bản khác dùng cursor và client không phân biệt semantics.
Nhóm sử dụng affordance để giới thiệu endpoint đổi trạng thái; sau khi đổi từ PUT sang PATCH, template client cũ gửi payload thay thế toàn bộ và làm mất field.
Đội xây trợ lý điều hướng theo _links của OrderModel; hệ thống trả link có URI templated nhưng trợ lý chưa có giá trị biến phù hợp và bị mắc ở bước tiếp theo.
Ứng dụng mobile lưu cache từng rel dưới dạng một đường dẫn tĩnh; khi backend phân vùng dữ liệu qua region, cached href dẫn tới node không còn quản lý tài nguyên.
Nhóm tạo relation mới để chỉ dòng lịch sử thanh toán; rel bị dùng đồng thời cho collection và một tài nguyên đơn khiến client không biết nên nhận list hay object.
Đội chuyển một action DELETE sang POST cancel để phù hợp audit; client vẫn lấy link rel delete cũ và nhận 405 khi gửi phương thức trước đây.
Ứng dụng có nhiều RepresentationModelAssembler khác nhau cho các vai trò; cùng entity trả các rel khác nhau và việc so sánh hợp đồng giữa admin và customer chưa được kiểm.
Nhóm chuyển từ monolith sang nhiều microservice nhưng giữ link tới controller cũ; API gateway chưa có route cho href mới nên client nhận 404 khi đi qua quy trình.
Đội dùng linkTo tạo href cho tài nguyên cross-service; domain của service đích khác gateway công khai làm client không gửi được credentials hợp lệ.
Ứng dụng phát link đến endpoint có yêu cầu OAuth scope riêng; client không có scope và điều hướng theo rel nhận 403 dù tài nguyên chính được phép xem.
Nhóm định nghĩa rel download cho hợp đồng có file nhạy cảm; link chứa token trong query và bị ghi vào log trình duyệt, proxy hoặc hệ thống analytics.
Đội xây action approve từ JWT scopes hiện tại; token hết hạn sau khi representation được tải và client nhấn link nhận 401 trong lúc workflow chưa được xử lý.
Ứng dụng tạo liên kết thao tác dựa trên role do frontend truyền; dữ liệu role không đáng tin khiến representation phát ra hành động đặc quyền ngoài phạm vi.
Nhóm dùng controller methodOn để tạo link của endpoint admin; một proxy security kiểm quyền đúng ở endpoint nhưng assembler lại công khai đường dẫn và ID nội bộ.
Đội dùng link collection filter theo nhóm sản phẩm; query parameter bị lấy từ request của user thay vì state resource khiến liên kết không thể chia sẻ ổn định.
Ứng dụng có rel payment-status tới một backend được triển khai riêng; downtime làm client theo link bị timeout nhưng representation gốc vẫn trả thành công.
Nhóm thiết kế link alternate tới tài nguyên PDF; một số khách cần JSON fallback nhưng link không có mô tả media type để lựa chọn thích hợp.
Đội xây HATEOAS representation chứa URI template cho lọc báo cáo; tham số ngày ở UTC nhưng client truyền ngày địa phương và nhận kết quả ngoài kỳ.
Ứng dụng giới hạn truy cập theo tổ chức; PagedModel self link được tạo từ path chung mà không giữ orgId và client đi tới bộ sưu tập không có quyền.
Nhóm dùng HAL links để hiển thị danh sách action trong UI; trang có hàng trăm item và phép đánh giá quyền từng link làm database quá tải.
Đội muốn thêm rel export khi số lượng item vượt ngưỡng; assembler dùng giá trị tổng trên cache cũ nên link xuất hiện hoặc biến mất không ổn định.
Ứng dụng tích hợp controller REST với Spring HATEOAS; một ResponseEntity trả status 204 lại mang RepresentationModel và client không nhận được các link như đội dự tính.
Nhóm tạo HTTP response 201 với EntityModel và Location; Location dùng URL khác self.href và client lưu hai định danh cho cùng tài nguyên mới.
Đội tạo redirect 301 từ URL cũ sang mới; một số client theo rel self cũ rồi cache redirect lâu, khiến thay đổi quyền truy cập không được áp như dự kiến.
Ứng dụng dùng controller GET trả HATEOAS resource cho mọi trạng thái; một trạng thái tài nguyên đã bị xóa mềm vẫn phát rel update và khách gặp 410 khi gọi.
Nhóm xử lý ProblemDetail khi hành động HATEOAS trả lỗi; client không tìm thấy link back để trở về bước trước và phải tự đoán endpoint.
Đội xây một endpoint actions cho tài nguyên; các affordance thay đổi theo feature flag nhưng client lưu representation cũ và nhấn action không còn được bật.
Ứng dụng có custom LinkRelationProvider tạo tên rel bằng tiếng Việt; một client quốc tế không hỗ trợ Unicode trong tên relation và bỏ qua các link.
Nhóm chuyển tên collection relation từ purchases sang orders; cùng entity data không đổi nhưng client mới và cũ phân tích _embedded theo hai tên khác nhau.
Đội phát triển dùng rel prev và next trên chuỗi phiên bản hợp đồng; client tưởng đó là phân trang danh sách và tải nhầm tài liệu.
Ứng dụng xây HATEOAS onboarding theo các bước xác thực; link chuyển tiếp ở bước thứ ba dẫn về phiên bản controller cũ và workflow bị lặp.
Nhóm nhận yêu cầu chỉ hiển thị các action được phép; một role có quyền xem link nhưng chưa được phép thực thi action và UI gây hiểu lầm.
Đội định nghĩa API báo cáo có link download trả file nén; client chỉ biết theo link rồi parse HAL nên không xử lý binary response.
Ứng dụng trả link search trong collection; client không hỗ trợ URI template expansion nên frontend vẫn hard-code đường dẫn tìm kiếm và mất khả năng tiến hóa API.
Nhóm dùng @SpringBootTest và MockMvc để kiểm JSON HAL; test chỉ assert status 200 và dữ liệu domain, không phát hiện _links.self.href sai prefix.
Đội kiểm EntityModel bằng unit test assembler; HTTP response thật đi qua forwarded headers làm host và scheme khác URL được assert trong unit test.
Ứng dụng kiểm PagedModel với đúng một trang; không kiểm first, prev, next, last nên link pagination bị lỗi khi production có nhiều trang.
Nhóm xây MockMvc test cho rel cancel; chỉ dùng Order PENDING nên không phát hiện link vẫn xuất hiện trên Order SHIPPED.
Đội dùng WebTestClient để kiểm JSON hypermedia; test bindToController không dùng đầy đủ codec và hypermedia configuration của production.
Ứng dụng dùng contract test để xác minh rel trên HAL; bộ stub chỉ chứa self và bỏ qua rel tạo hành động khiến bản client mới hoạt động khác môi trường tích hợp.
Nhóm kiểm endpoint yêu cầu Accept application/hal+json; test gửi Accept application/json và không xác minh cơ chế content negotiation của tài nguyên.
Đội phát triển test affordance với user admin; không có test user thường nên field nội bộ và link privileged bị lộ khi serialization cho khách.
Ứng dụng kiểm response HAL chứa _embedded cho collection có dữ liệu; trường hợp collection rỗng và thiếu _embedded khiến client phân tích lỗi mà test bỏ qua.
Nhóm tạo test cho URI template nhưng chỉ dùng giá trị ASCII; mã sản phẩm chứa dấu slash, khoảng trắng và tiếng Việt làm đường dẫn sau expansion không hợp lệ.
Đội dùng integration test qua localhost không có reverse proxy; linkTo tạo href đúng local nhưng sai host, scheme và path prefix khi deploy sau gateway.
Ứng dụng thêm rel canonical cho tài nguyên cũ; test chỉ kiểm self nên không phát hiện link canonical trỏ sang ID chưa được migration.
Nhóm kiểm quan hệ trong HAL với một link; trường hợp nhiều Link cùng rel được serialize thành array và client cũ không được kiểm khả năng đọc.
Đội áp API snapshot testing cho HAL; timestamp và absolute host trong href thay đổi mỗi môi trường khiến snapshot bị flaky dù relation semantics không đổi.
Ứng dụng đánh dấu link deprecated cho endpoint cũ; contract test hiện chỉ kiểm sự tồn tại rel và không phát hiện thiếu metadata deprecation.
Nhóm muốn kiểm tiến hóa API dựa vào rel; test client vẫn hard-code URL nên việc đổi path không được thử theo cách sử dụng hypermedia thực.
Đội sử dụng fake permission service trong test assembler; stub luôn cấp quyền và không kiểm link nào biến mất khi người dùng bị khóa.
Ứng dụng có controller phản hồi HAL tại các môi trường khác nhau; bộ test chỉ chạy với Jackson mặc định nên lỗi cấu hình HAL module production chưa được phát hiện.
Nhóm benchmark trả 100 sản phẩm qua EntityModel; production trả 10.000 sản phẩm và thời gian dựng linkTo cùng quyền truy cập tăng rõ rệt.
Đội đo latency controller mà không tính thời gian serialize HAL và build link; p95 bên ngoài gateway cao hơn metrics do service tự ghi.
Ứng dụng gắn trace vào controller nhưng assembler gọi nhiều repository; log SQL không có correlation ID khiến đội vận hành khó tìm nút thắt khi tạo link.
Nhóm chuyển thông tin link theo từng domain vanity; cache HTTP không phân biệt Host và trả absolute href của một khách hàng cho khách khác.
Đội cấu hình graceful shutdown cho API HATEOAS; request tải representation lớn bị cắt giữa chừng và client nhận JSON thiếu phần _embedded.
Ứng dụng thêm một media type hypermedia mới cạnh HAL; nhóm client gửi Accept wildcard nhận format khác trước và không thể parse các relation.
Nhóm triển khai API đa vùng sau load balancer; các href được tạo từ headers của một proxy chưa được tin cậy đúng cách và dẫn người dùng ra miền lạ.
Đội đưa logic quyền vào assembler và repository; khi quyền được thu hồi giữa hai bước, representation phát link edit đã lỗi thời và client nhận 403.
Ứng dụng cần kiểm link thay đổi theo trạng thái Order sau thanh toán; cache representation từ trước vẫn giữ pay link khiến khách gửi lại lệnh thanh toán.
Nhóm xuất bản tài liệu hợp đồng API gồm các rel có thể có; tài liệu không cập nhật khi endpoint mới thêm affordance nên phía client không khai thác được bước workflow mới.
