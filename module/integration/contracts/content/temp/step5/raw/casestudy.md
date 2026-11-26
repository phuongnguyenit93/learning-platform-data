Một ứng dụng đặt vé bổ sung tham số truy vấn bắt buộc vào API tìm chuyến bay đã công bố bằng OpenAPI; các phiên bản mobile cũ không gửi tham số này và đồng loạt nhận lỗi sau khi backend được triển khai.
Dịch vụ khách hàng đổi thuộc tính fullName thành displayName trong response HTTP, trong khi ứng dụng CRM của đối tác vẫn tạo đối tượng dựa trên tên trường cũ và hiển thị tên khách hàng trống.
Nhóm thanh toán chuyển trường amount từ số nguyên biểu diễn đơn vị nhỏ nhất sang số thập phân biểu diễn tiền tệ, nhưng tài liệu hợp đồng API chưa nêu lại đơn vị và hệ thống đối soát tính lệch số tiền.
Đội kho đổi kiểu dữ liệu productId từ chuỗi sang số trong OpenAPI; một số mã sản phẩm có số 0 ở đầu bị mất thông tin khi client được tạo lại từ schema.
Schema response đơn hàng tuyên bố địa chỉ giao hàng luôn có giá trị, nhưng người mua chọn nhận tại cửa hàng khiến trường này trả null và client sinh từ OpenAPI từ chối dữ liệu.
API quản lý vé thêm giá trị CHECKED_IN vào enum trạng thái; bản ứng dụng iOS chưa cập nhật không nhận diện giá trị mới và bỏ qua các vé đã được xác nhận tại cổng.
Một API báo giá có trường discountPercent tùy chọn nhưng backend bắt đầu luôn trả giá trị 0 khi khách không có mã giảm; hai hệ thống tiêu thụ hiểu khác nhau giữa không áp dụng khuyến mãi và mức giảm 0%.
Dịch vụ hồ sơ thay đổi quy ước ngày sinh từ ngày lịch không có múi giờ sang timestamp UTC; ứng dụng đối tác hiển thị lệch ngày sinh với khách ở một số múi giờ.
Một endpoint giao hàng trước đây trả HTTP 201 kèm mã vận đơn, nay trả HTTP 202 vì chuyển sang xử lý bất đồng bộ; client đối tác vẫn coi việc nhận 202 là lỗi tạo đơn.
API danh sách giao dịch dùng HTTP 200 với mảng trống cho tài khoản không tồn tại, trong khi hợp đồng OpenAPI và client khác kỳ vọng HTTP 404; bộ phận chăm sóc khách hàng đưa ra kết luận sai về lịch sử giao dịch.
Hệ thống đối soát đổi cấu trúc body của HTTP 409 từ mã lỗi nghiệp vụ thành thông báo văn bản; ứng dụng đối tác không còn phân biệt được giao dịch trùng với xung đột trạng thái.
Nhà cung cấp vận chuyển trả lỗi xác thực HTTP 401 ở một môi trường và HTTP 403 ở môi trường khác cho cùng tình huống thiếu quyền; các ứng dụng tích hợp xử lý đăng nhập lại không nhất quán.
API cập nhật hồ sơ bằng PATCH nhận trường phoneNumber không xuất hiện khác với trường mang null; một client đã gộp hai trường hợp này và vô tình xóa số điện thoại của khách.
OpenAPI của dịch vụ đơn hàng đánh dấu address là required ở request tạo mới nhưng ví dụ chính thức lại bỏ trường này; các nhóm tích hợp xây client dựa trên hai nguồn và gặp lỗi khác nhau.
Một nhóm phát hành OpenAPI mới với đường dẫn /v2/orders nhưng gateway vẫn chỉ chuyển tiếp /v1/orders; SDK sinh tự động từ bản hợp đồng mới không gọi được dịch vụ production.
API nhập hàng có response mô tả bằng oneOf cho hai loại chứng từ nhưng không có trường nhận diện rõ ràng; client tự sinh chọn nhầm kiểu khi hai biến thể có nhiều thuộc tính giống nhau.
Dịch vụ catalog cho phép sắp xếp sản phẩm theo giá nhưng tài liệu OpenAPI không quy định cách phân biệt các mặt hàng có giá bằng nhau; client lật trang liên tục thấy sản phẩm trùng và bị bỏ sót.
API tra cứu hóa đơn chuyển từ phân trang offset sang cursor nhưng giữ nguyên tên tham số page; SDK của khách hàng cũ vẫn gửi số trang và không thể tải phần dữ liệu tiếp theo.
Ứng dụng y tế gửi tệp PDF qua multipart/form-data nhưng hợp đồng OpenAPI mô tả body là application/json; công cụ sinh client gửi nhầm content type và hệ thống lưu trữ không nhận tệp.
Đội phát triển bổ sung cơ chế xác thực theo scope vào OpenAPI nhưng endpoint báo cáo vẫn được công bố như API chỉ cần đăng nhập; đối tác nhận lỗi thiếu quyền dù token hợp lệ.
Nhà cung cấp đổi endpoint lấy danh sách từ GET sang POST để nhận bộ lọc lớn; ứng dụng tích hợp cũ, proxy cache và tài liệu HTTP được sử dụng tại các chi nhánh chưa thống nhất cách gọi.
API dành cho đối tác mở rộng trường mã bưu chính từ chuỗi tối đa 6 ký tự lên 12 ký tự; một chương trình nhập liệu vẫn kiểm tra theo hợp đồng cũ và từ chối địa chỉ quốc tế.
Nhóm xuất bản OpenAPI với định nghĩa tham số query tùy chọn nhưng lớp validation thực tế bắt buộc có tham số này; kiểm thử tự động từ hợp đồng báo pass trong khi request thật liên tục nhận HTTP 400.
Đội phát hành SDK Java từ OpenAPI và phát hiện hai schema có cùng tên lớp sau khi chuẩn hóa; khách hàng dùng bản SDK mới không thể biên dịch ứng dụng dù tài liệu API vẫn hợp lệ.
Người dùng tích hợp dịch vụ bảo hiểm thông qua webhook hoàn tất bồi thường; bản phát hành mới thay đổi trường eventType trong payload nhưng tài liệu callback OpenAPI vẫn mô tả tên sự kiện cũ.
Hệ thống ngân hàng gửi webhook thanh toán có header chữ ký thay đổi định dạng sau lần xoay khóa; dịch vụ nhận dựa theo hợp đồng cũ từ chối các callback hợp lệ và đơn hàng bị treo.
Đội tích hợp đưa ví dụ trạng thái tài khoản trong OpenAPI về dữ liệu mới nhưng không cập nhật mô tả ý nghĩa trường isActive; hệ thống đối tác hiểu trạng thái tạm khóa như tài khoản đã bị đóng.
Nền tảng bán lẻ phát sự kiện OrderCreated vào topic order.created nhưng AsyncAPI được phát hành ghi channel orders.created; consumer do đối tác triển khai đăng ký sai địa chỉ và không nhận thông điệp.
Hệ thống vận chuyển đổi routing key của thông báo giao hàng từ shipment.updated sang shipment.status.changed nhưng metadata binding trong AsyncAPI chưa đổi; các hệ thống kho ngừng cập nhật tiến độ.
Thông điệp tạo đơn công bố qua AsyncAPI yêu cầu orderId và createdAt, nhưng publisher mới phát hành đôi khi bỏ createdAt khi đơn được nhập thủ công; consumer từ chối các thông điệp này.
Ứng dụng phát sự kiện PaymentCaptured nhưng thay payload từ cấu trúc giao dịch sang một phần thông tin đơn hàng mà không đổi tên sự kiện; hệ thống kế toán ghi thiếu dữ liệu đối soát.
Hệ thống CRM đổi trường customerEmail thành contactEmail trong sự kiện CustomerUpdated; một consumer tiếp thị cũ vẫn đọc tên cũ và ngừng gửi email xác nhận.
Đội nghiệp vụ mở rộng enum trạng thái giao hàng trong event từ DELIVERED và IN_TRANSIT thêm RETURNED; một consumer báo cáo cũ bỏ qua các event có trạng thái lạ và thống kê thất lạc hàng.
Sự kiện InventoryAdjusted chỉ mang số lượng thay đổi, nhưng một consumer mới hiểu nhầm trường quantity là lượng tồn cuối cùng; tồn kho giữa kho và website sai lệch theo từng lần điều chỉnh.
Nhà cung cấp phát OrderStatusChanged trong một channel dùng chung cho nhiều tenant nhưng hợp đồng message không mô tả khóa phân vùng tenant; ứng dụng đối tác áp dụng cập nhật vào sai tài khoản.
Đội vận hành phát lại các thông điệp cũ từ dead-letter queue sau sự cố; payload có phiên bản schema trước hai lần phát hành và consumer hiện tại không còn xử lý được một số trường.
Một event cập nhật hợp đồng bảo hiểm có timestamp theo giờ địa phương nhưng AsyncAPI ghi format date-time mà không quy định múi giờ; các đối tác tính thời điểm hiệu lực khác nhau.
Sự kiện PaymentSettled được gửi ít nhất một lần khi broker kết nối lại, nhưng hợp đồng sự kiện không mô tả mã định danh ổn định của message; hệ thống nhận đôi lúc ghi nhận hai khoản thu.
Workflow tạo đơn qua HTTP rồi phát sự kiện OrderAccepted có hai mã định danh khác nhau; các nhóm phân tích không ghép được phản hồi API với event đến sau trong lúc điều tra một giao dịch lỗi.
Ứng dụng nhận cả sự kiện OrderCreated và OrderCancelled trên các channel khác nhau; trạng thái hủy đôi lúc được xử lý trước trạng thái tạo và hợp đồng không nêu rõ yêu cầu thứ tự giữa các thông điệp.
Một hệ thống phân phối sử dụng sự kiện ProductUpdated lúc chứa toàn bộ dữ liệu sản phẩm, lúc chỉ chứa trường đã thay đổi; consumer không biết nên ghi đè hay hợp nhất bản ghi hiện có.
Đội tích hợp dùng cùng một eventType cho sự kiện một giao dịch đã hoàn tất và thông điệp yêu cầu thực hiện giao dịch; các consumer khác nhau có hành vi nghiệp vụ trái ngược khi nhận thông điệp.
AsyncAPI mô tả message phản hồi kết quả xét duyệt vào một channel duy nhất, nhưng thực tế broker dùng queue phản hồi động theo correlationId; ứng dụng đối tác không tìm được kết quả yêu cầu.
Dịch vụ xử lý hồ sơ thỉnh thoảng từ chối thông điệp đầu vào và phát thông báo lỗi riêng; hợp đồng message chưa mô tả trường nào giúp đối tác liên hệ lỗi với hồ sơ gốc.
Đội thay đổi quy tắc thời hạn xử lý yêu cầu thanh toán trong broker; một consumer vẫn giả định thông điệp luôn còn hiệu lực và hoàn tất giao dịch đã hết hạn.
Nền tảng IoT phát dữ liệu cảm biến qua message broker nhưng tài liệu AsyncAPI thiếu đơn vị nhiệt độ và độ chính xác; hai hệ thống giám sát diễn giải cùng trường temperature theo thang đo khác nhau.
Một hệ thống dùng header contentType để phân biệt JSON và Avro nhưng publisher mới không gửi header trên một số message; consumer giải mã sai nội dung dù channel và schema không đổi.
Nhóm sở hữu sự kiện OrderPlaced thay đổi schema ở một repository, trong khi bản AsyncAPI phát hành cho đối tác vẫn trỏ đến phiên bản cũ; kiểm thử trên staging thành công nhưng production nhận dữ liệu không như tài liệu.
Đội dữ liệu thêm trường loyaltyTier mới vào Avro schema của CustomerEvent nhưng không khai báo default; consumer mới đọc lại bản ghi do publisher cũ lưu từ tháng trước và gặp lỗi giải mã.
Nhà cung cấp sử dụng Avro đổi tên trường branchCode thành locationCode; những chương trình đọc bản ghi cũ không nhận ra giá trị tương ứng dù ý nghĩa nghiệp vụ của trường không đổi.
Một nhóm sửa kiểu trường amount trong Avro từ long sang string để lưu số có dấu phân cách; dữ liệu mới được ghi thành công nhưng consumer cũ không thể giải mã các giao dịch này.
Avro schema của một sự kiện ngân hàng bổ sung giá trị FROZEN vào enum AccountStatus; một ứng dụng cũ nhận bản ghi chứa giá trị này và không xác định được trạng thái tài khoản.
Đội nâng độ chính xác và scale của trường decimal lưu lãi suất trong Avro; hai hệ thống được triển khai lệch phiên bản bắt đầu đọc cùng bản ghi thành các giá trị lãi khác nhau.
Một trường tùy chọn trong Avro dùng union của null và string; nhóm sửa vị trí kiểu trong union nhưng giữ default theo định dạng trước đó, khiến bước kiểm tra schema ở pipeline bị lỗi.
Schema Registry đặt chế độ kiểm tra BACKWARD cho sự kiện thanh toán; một consumer cũ vẫn đang chạy và bị lỗi khi đọc thông điệp do writer mới phát hành, mặc dù phiên bản schema được registry chấp nhận.
Đội công bố schema Avro mới với tên subject khác do đổi quy tắc đặt tên; bản ghi trong cùng topic tham chiếu nhiều subject và consumer không tìm được định nghĩa dữ liệu cần đọc.
Trong một topic Kafka lưu lịch sử đơn hàng nhiều năm, consumer mới được cập nhật schema chỉ qua các bản ghi mới; khi phải đọc lại toàn bộ topic để tái lập báo cáo, lỗi tương thích chỉ xuất hiện ở dữ liệu đời đầu.
Dịch vụ gRPC dùng Protobuf tái sử dụng số field tag từng dành cho customerId để lưu accountId; một ứng dụng cũ vẫn đang chạy đọc giá trị mới vào thuộc tính cũ và liên kết nhầm tài khoản.
Một nhóm chuyển type của field Protobuf từ string sang số nguyên nhưng giữ nguyên tag; thông điệp cũ và mới được trao đổi cùng thời điểm và hai phía gặp lỗi giải mã không nhất quán.
Protobuf message của dịch vụ kho dùng số lượng bằng 0 để chỉ hàng hết; sau khi mở rộng quy trình đặt trước, backend cần phân biệt field không được gửi với field được gửi giá trị 0 nhưng client cũ không thể hiện được khác biệt.
Đội bỏ trường mã giảm giá cũ khỏi Protobuf schema, sau đó tái sử dụng cùng tag cho ý nghĩa khác; các bản ghi lưu trữ trước đó được đọc lại thành dữ liệu chiết khấu không chính xác.
Một message Protobuf bổ sung biến thể mới vào oneof PaymentSource; các ứng dụng đối tác dùng bản generated client cũ không biết cách xử lý trường hợp thanh toán mới khi nhận phản hồi.
Nhóm đổi package của Protobuf service từ billing.v1 sang finance.v1 và sinh lại client; các ứng dụng gRPC cũ tiếp tục gọi tên service trước khi thay đổi và bị trả về lỗi không tìm thấy phương thức.
Một số service cùng định nghĩa Protobuf message Customer với tên trường giống nhau nhưng ý nghĩa mã nhận dạng khác nhau; bộ chuyển đổi giữa hai service gán sai khách hàng dù dữ liệu đều giải mã hợp lệ.
Nhóm chuyển payload của một topic từ JSON sang Avro nhưng không phân tách phiên bản hoặc cung cấp dấu hiệu encoding nhất quán; trong giai đoạn triển khai luân phiên, các consumer không thể dự đoán định dạng message.
Ứng dụng giao vận dùng gRPC thay đổi phương thức GetShipment từ một phản hồi đơn thành luồng nhiều phản hồi; client Java cũ không tương thích với hợp đồng RPC được phát hành mới.
Hệ thống phát sinh nhiều hóa đơn dùng gRPC streaming nhưng tài liệu hợp đồng chỉ nêu từng item, không quy định ý nghĩa khi stream kết thúc sớm; các client báo hoàn tất dù chưa nhận đủ hóa đơn.
Dịch vụ tìm kiếm gRPC được nâng cấp và đổi tên phương thức ListProducts; SDK đã triển khai ở các cửa hàng vẫn gửi yêu cầu đến đường dẫn phương thức cũ và nhận UNIMPLEMENTED.
API gRPC kiểm tra quyền truy cập bằng metadata mới nhưng các client tích hợp chỉ cập nhật Protobuf message mà không cập nhật yêu cầu metadata; các cuộc gọi vẫn có payload đúng nhưng bị từ chối.
Nhóm xây gateway chuyển HTTP JSON sang gRPC; Protobuf khai báo trường quantity là số nguyên có giá trị mặc định 0, còn hợp đồng REST cho phép bỏ trường để dùng số lượng mặc định khác và gây sai đơn.
Đội RPC thay đổi deadline yêu cầu xét duyệt xuống mức thấp hơn thời gian xử lý bình thường; client tự sinh từ schema không biết quy tắc timeout mới và coi nhiều giao dịch đang xử lý là thất bại.
Nhà cung cấp trả lỗi gRPC FAILED_PRECONDITION cho một trạng thái nghiệp vụ mà trước đây trả INVALID_ARGUMENT; các ứng dụng đối tác thực hiện retry khác nhau cho cùng một giao dịch.
Một dịch vụ gRPC phát hành Protobuf mới nhưng quên cập nhật thư viện client dùng chung trong một nhóm microservice; khi triển khai hai phiên bản song song, các bên gọi nhau với hợp đồng khác nhau.
Đội kiến trúc muốn ngừng phiên bản v1 của API đối tác nhưng chưa biết còn ứng dụng nào dùng các endpoint này; nhật ký gateway và danh mục hợp đồng không có thông tin phiên bản ở cấp consumer.
Hai nhóm phát triển cùng sửa OpenAPI của dịch vụ đơn hàng: một nhóm đổi kiểu response, nhóm kia thêm trường optional; khi hợp nhất, schema phát hành không phản ánh chính xác bất kỳ triển khai nào.
Một dịch vụ cung cấp song song HTTP API và sự kiện OrderChanged cho cùng khái niệm trạng thái đơn; hai hợp đồng dùng tập enum khác nhau và báo cáo tổng hợp gặp giá trị không thể đối chiếu.
Doanh nghiệp phát hành hợp đồng mới theo semantic versioning và tăng minor version sau khi bỏ một trường response bắt buộc; client đối tác tự động nâng cấp và dừng xử lý dữ liệu.
Nhóm bảo hiểm công bố chính sách hỗ trợ ba phiên bản schema sự kiện, nhưng nhà sản xuất triển khai phiên bản thứ tư trong khi một consumer vùng xa chưa chuyển đổi và ngừng xử lý hồ sơ.
Khách hàng tích hợp nhận thông báo ngừng hỗ trợ endpoint cũ quá sát ngày tắt; chương trình chạy định kỳ hàng tháng chưa kịp cập nhật và không lấy được dữ liệu báo cáo cuối kỳ.
Một nhóm triển khai consumer-driven contract test cho API tạo đơn, nhưng chỉ có hợp đồng của ứng dụng web; một đối tác vận chuyển bên ngoài dùng response field khác không được đại diện trong bộ kiểm thử.
Bộ contract test do consumer công bố khẳng định trường status của Order luôn có bốn giá trị; provider thêm trạng thái mới hợp lệ theo nghiệp vụ và pipeline hợp đồng báo không tương thích với consumer này.
Nhà cung cấp vượt qua các contract test trên mock server nhưng phản hồi từ hệ thống production thêm wrapper data ngoài cấu trúc hợp đồng; client được sinh tự động lỗi ngay sau triển khai.
Consumer test ghi lại response JSON với các trường có dữ liệu mẫu cố định; khi provider thay đổi nội dung động như orderId và thời gian tạo, kiểm thử hợp đồng thất bại dù cấu trúc vẫn phù hợp.
Nhóm đối tác chỉ kiểm thử contract theo status 200 của API tra cứu; bản phát hành mới đổi cấu trúc response lỗi 400, khiến hệ thống giám sát người dùng không thể phân loại lỗi đầu vào.
Pipeline CI kiểm thử OpenAPI trên từng pull request nhưng không so sánh với hợp đồng của phiên bản đang chạy; khi hai nhánh được phát hành gần nhau, thay đổi không tương thích vẫn đi vào production.
Provider chạy thành công contract test với consumer phiên bản mới nhất, nhưng nhiều thiết bị POS vẫn hoạt động trên phiên bản client cũ và nhận dữ liệu không đọc được sau cập nhật.
Hai service dùng chung một schema Protobuf trong monorepo nhưng phát hành theo lịch độc lập; bên phát hành trước sử dụng field mới mà bản triển khai cũ của bên kia chưa xử lý được.
Dịch vụ thanh toán có contract test dùng môi trường thử nghiệm với mã lỗi giả lập; hệ thống production của ngân hàng trả thêm một mã lỗi nghiệp vụ chưa xuất hiện trong hợp đồng và luồng hoàn tiền bị treo.
Đội tích hợp tạo stub HTTP từ OpenAPI phục vụ kiểm thử ứng dụng mobile; stub luôn trả dữ liệu đúng hợp đồng nhưng backend thật có trường hợp trả HTTP 204 kèm body không hợp lệ.
Nhóm quản trị hợp đồng đặt owner ở cấp repository nhưng không xác định được ai chịu trách nhiệm phê duyệt thay đổi schema thuộc kênh sự kiện dùng chung; hai đội phát hành các bản mô tả trái nhau.
Trong đợt kiểm toán, nhóm vận hành phát hiện OpenAPI, AsyncAPI và Protobuf đã được cập nhật nhưng không có hồ sơ thể hiện consumer nào đã kiểm thử từng phiên bản trước khi sản xuất.
Một hệ thống xử lý đơn cần đồng bộ cả HTTP API tạo đơn và event OrderConfirmed; event mới được triển khai trước khi contract HTTP có trường liên quan, khiến đối tác không thể truy ra nguyên nhân trạng thái đơn thay đổi.
Gateway quản lý API công bố hợp đồng OpenAPI mới với giới hạn rate limit khác, nhưng header phản hồi production vẫn dùng quy ước cũ; SDK đối tác tính sai thời điểm nên gửi lại yêu cầu.
