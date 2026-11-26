Một ứng dụng Spring MVC nhận biểu mẫu cập nhật hồ sơ khách hàng qua DataBinder, nhưng trường role vô tình được bind từ request khiến người dùng có thể tự thay đổi quyền quản trị.
Nhóm phát triển dùng @ModelAttribute trực tiếp trên entity Customer và cho phép gửi tham số isApproved, khiến trạng thái duyệt được sửa mà không đi qua quy trình nghiệp vụ.
Một dịch vụ cho phép cập nhật địa chỉ giao hàng nhưng WebDataBinder chưa giới hạn allowedFields, khiến request chứa trường accountBalance có thể tác động dữ liệu nhạy cảm.
Đội khai báo disallowedFields cho một thuộc tính quyền nhưng sau khi đổi tên thuộc tính Java, trường mới lại được bind từ request mà không bị chính sách cũ chặn.
Ứng dụng đặt allowedFields cho trang tạo sản phẩm nhưng dùng cùng binder ở trang sửa, khiến thuộc tính được phép tạo mới lại không được cập nhật ở màn hình chỉnh sửa.
Nhóm bật ignoreUnknownFields cho DataBinder trong API nhận JSON form, khiến một lỗi đánh máy trong tên field không được phản ánh và dữ liệu khách tưởng đã lưu bị mất.
Một service tắt ignoreUnknownFields để phát hiện lỗi client nhưng ứng dụng mobile cũ gửi thêm thuộc tính đã ngừng sử dụng, khiến đợt nâng cấp làm nhiều request hợp lệ trước đây thất bại.
Đội dùng @InitBinder để cấu hình WebDataBinder nhưng method chỉ áp dụng cho một controller, khiến endpoint cập nhật khác tiếp tục chấp nhận các field không mong muốn.
Một ứng dụng chia sẻ @ControllerAdvice chứa @InitBinder cho nhiều endpoint nhưng cấu hình chỉ phù hợp với OrderForm, khiến biểu mẫu UserForm cũng bị chặn các thuộc tính hợp lệ.
Nhóm xây một helper gọi DataBinder bên ngoài Spring MVC nhưng không đăng ký Validator và ConversionService của ứng dụng, khiến cùng dữ liệu đầu vào cho kết quả khác controller HTTP.
Một service dùng DataBinder để cập nhật object có thuộc tính nested address.city, nhưng object address chưa được khởi tạo nên binding không tạo kết quả như frontend mong đợi.
Đội bật autoGrowNestedPaths để bind địa chỉ sâu trong cây object, nhưng một khách gửi property path có độ sâu lớn làm quá trình khởi tạo đối tượng phình to.
Ứng dụng bind danh sách orderLines từ form với chỉ số phần tử rất lớn, khiến cơ chế autoGrowCollectionLimit trở thành giới hạn bị vượt trong request nhập hàng.
Nhóm cho phép tạo các phần tử giỏ hàng qua index trong tham số form, nhưng client gửi các index cách xa nhau khiến danh sách có nhiều phần tử rỗng không hợp lệ.
Một service nhận form dữ liệu nhân sự với department.manager.email nhưng đường nested binding vô tình tạo object manager mới thay vì liên kết người quản lý đã tồn tại.
Đội xây form chỉ cho phép sửa địa chỉ nhưng binder đặt allowedFields quá rộng, khiến các giá trị từ query string không liên quan cũng được đưa vào object domain.
Ứng dụng dùng field marker từ checkbox trong MVC form nhưng một proxy loại tham số marker, khiến người dùng bỏ chọn một quyền mà trạng thái cũ vẫn được giữ.
Nhóm có trường boolean subscribeToNewsletter mặc định true nhưng gửi biểu mẫu không có checkbox, khiến cách binder xử lý giá trị không hiện diện khác kỳ vọng người dùng.
Một service dùng field default prefix để điền giá trị thiếu nhưng cùng trường có thể nhận giá trị rỗng hợp lệ, khiến binder phân biệt sai không gửi với cố ý xóa.
Đội nhận multipart form gồm metadata và file nhưng binder cố gắng gán dữ liệu upload vào thuộc tính String, khiến một số request thất bại chuyển kiểu.
Ứng dụng công bố object có getter tính toán read-only nhưng form client cố bind trường đó, khiến BindingResult chứa lỗi bất ngờ trong bước cập nhật.
Nhóm dùng DataBinder với object không có setter cho một thuộc tính, nhưng frontend vẫn gửi field này và coi response thành công nghĩa là thuộc tính đã đổi.
Một service chuyển form JavaBean có setter sang immutable record, khiến chiến lược constructor binding được áp dụng khác cách data binding cũ hoạt động.
Đội xây DTO chứa constructor có tham số bắt buộc nhưng một request thiếu tên tham số, khiến ứng dụng không tạo được đối tượng đầu vào như khi bind vào bean có no-args constructor.
Ứng dụng dùng constructor binding cho đối tượng tạo khoản vay nhưng tham số định danh người duyệt cũng được lấy từ request, khiến dữ liệu do client cung cấp vượt phạm vi tin cậy.
Nhóm trộn constructor binding với property binding trên cùng DTO có trạng thái mutable, khiến một phần thuộc tính được xác lập theo hai cơ chế khác nhau.
Một hệ thống dùng custom PropertyEditor ở @InitBinder cho trường customerCode nhưng editor giữ state trong singleton, khiến hai request đồng thời có nguy cơ ảnh hưởng kết quả chuyển đổi.
Đội cấu hình một PropertyEditor đọc ngày theo định dạng cố định nhưng ứng dụng có khách ở nhiều locale, khiến dữ liệu ngày hợp lệ tại một quốc gia bị báo sai.
Một service sử dụng StringTrimmerEditor để chuyển chuỗi rỗng thành null, khiến trường biệt danh được phép rỗng lại bị @NotNull từ chối sau binding.
Nhóm bind giá tiền từ biểu mẫu bằng cách dùng dấu phẩy làm dấu thập phân nhưng converter đang áp dụng định dạng US, khiến đơn đặt hàng nhập sai giá trị.
Ứng dụng nhận số lượng sản phẩm từ query parameter và lỗi typeMismatch xảy ra với giá trị âm dạng text có dấu cách, khiến frontend không hiển thị lỗi ngay tại field.
Đội sử dụng DataBinder cho đối tượng chứa Set quyền, nhưng client gửi phần tử trùng và business dự kiến báo lỗi trùng thay vì chỉ nhận tập đã loại trùng.
Một service bind Map từ tham số tùy ý và sử dụng khóa làm nhãn nghiệp vụ, khiến tên khóa không được kiểm soát có thể tạo cấu trúc dữ liệu ngoài schema.
Nhóm cho phép bind cả nested field từ JSON và form-url-encoded trên hai endpoint, nhưng dữ liệu giống nhau cho kết quả khác khi chuyển array/list.
Ứng dụng nhận giá trị null trong JSON để xóa số điện thoại nhưng form HTML không phân biệt được null với chuỗi rỗng, khiến chính sách update không nhất quán giữa hai client.
Đội chuyển từ DataBinder bean property access sang direct field access để hỗ trợ DTO legacy, khiến setter đang chứa business validation không được gọi theo đường binding mới.
Một service dùng BeanWrapper để gán thuộc tính lồng nhau nhưng tên field được lấy từ dữ liệu người dùng mà không có whitelist, khiến những thuộc tính ngoài phạm vi cấu hình cũng được chỉnh.
Nhóm gọi BeanWrapperImpl để sửa object đã được dùng chung bởi nhiều thread, khiến cập nhật cấu hình runtime từ hai yêu cầu quản trị bị ghi đè.
Ứng dụng dùng BeanWrapper để đọc giá trị từ object proxy Hibernate nhưng thuộc tính lazy chưa được tải, khiến một màn hình kiểm tra dữ liệu vô tình tạo nhiều SQL queries.
Đội dùng PropertyAccessorFactory trên object immutable nhưng công cụ import mong có thể sửa mọi property, khiến một nhóm bản ghi không được cập nhật và khó chẩn đoán.
Một service cho phép thay tên thuộc tính Java trong form cấu hình nhưng BeanWrapper vẫn tham chiếu tên property cũ, khiến lúc deploy bản mới dữ liệu migration không được điền.
Nhóm dùng BeanWrapper.getPropertyType để sinh schema form tự động, nhưng thuộc tính generic collection bị suy ra không đủ kiểu phần tử, khiến UI tạo input không phù hợp.
Ứng dụng có đối tượng chứa property nested kiểu Optional nhưng một form gửi chuỗi đơn giản, khiến quá trình binding không thể áp dụng như quy tắc chuyển đổi đang dùng.
Đội xây chức năng sửa cấu hình động bằng BeanWrapper nhưng không phân biệt property readable và writable, khiến người quản trị được hiển thị ô chỉnh cho field chỉ đọc.
Một service dùng BeanWrapper để truy cập các getter có side effect, khiến quá trình lấy dữ liệu để render form vô tình kích hoạt tác vụ nghiệp vụ.
Nhóm nhận yêu cầu thay đổi trường billingAddress.zipCode nhưng object có nhiều getter lồng nhau, khiến lỗi thuộc tính không tồn tại bị báo dưới mã không quen thuộc với frontend.
Ứng dụng cập nhật một nested path dùng BeanWrapper và auto-grow nhưng dữ liệu hiện có là một object subtype khác, khiến đường gán field tạo object kiểu không phù hợp.
Đội muốn ánh xạ DTO từ Map<String,Object> bằng BeanWrapper nhưng một giá trị trong Map đã có kiểu số khác kiểu Java đích, khiến một phần hồ sơ lỗi conversion.
Một service cấu hình DataBinder theo phương thức field access để bỏ qua setter không an toàn nhưng một thay đổi trong class chuyển field từ mutable sang final, khiến form không được điền.
Nhóm dùng BeanWrapper với tên property do file CSV cung cấp, khiến một cột lạ trùng tên thuộc tính nhạy cảm và được gán mà không qua hợp đồng nhập liệu.
Ứng dụng dùng ConversionService chuyển productId từ String sang UUID nhưng chuỗi từ đối tác không hợp lệ, khiến controller trả lỗi chung thay vì mã lỗi field cụ thể.
Đội đăng ký Converter<String,Status> cho trạng thái đơn nhưng quy tắc viết hoa/chữ thường khác giữa các quốc gia, khiến những trạng thái hợp lệ bị từ chối trong API.
Một service dùng ConverterFactory để chuyển nhiều enum loại tài sản nhưng enum mới có alias cũ, khiến client gửi mã legacy không được công nhận sau nâng cấp.
Nhóm cấu hình GenericConversionService ở một module khác với MVC ConversionService, khiến cùng kiểu tiền tệ được chuyển đổi đúng ở service nhưng lỗi tại binding HTTP.
Ứng dụng có hai Converter từ String sang cùng loại Money trong ApplicationContext, khiến cấu hình nhận converter của hai module theo thứ tự khác và kết quả biến động giữa môi trường.
Đội dùng GenericConverter cho dữ liệu có type annotation nhưng không xem xét field annotation của đối tượng đích, khiến hai trường cùng kiểu Java cần định dạng khác nhau bị xử lý giống nhau.
Một service chuyển chuỗi tỷ lệ phần trăm sang BigDecimal nhưng Converter hiểu 15% thành 15 thay vì giá trị tỷ lệ dùng trong tính toán, khiến kết quả chiết khấu sai.
Nhóm dùng ConversionService cho enum OrderState nhưng DTO có giá trị null hợp lệ, khiến một bộ chuyển đổi tùy biến ném lỗi khi nhận trường vắng mặt.
Ứng dụng bind mảng UUID từ query parameter nhưng request chứa một phần tử rỗng, khiến cả danh sách mã sản phẩm bị từ chối dù các mã còn lại hợp lệ.
Đội xử lý chuỗi ngày ISO-8601 trong Converter nhưng dữ liệu có timezone offset, khiến thời điểm giao dịch bị đổi khác giữa server tại hai khu vực.
Một service chuyển chuỗi sang boolean nhưng các client gửi yes/no và true/false theo thói quen khác nhau, khiến một loại người dùng không thể hoàn tất form.
Nhóm import dữ liệu có mã quốc gia viết thường nhưng converter được dùng chung với Validator yêu cầu mã chuẩn hóa, khiến giá trị được coi hợp lệ phụ thuộc bước nào chạy trước.
Ứng dụng nâng phiên bản Spring và thay custom ConversionService bằng cấu hình mặc định, khiến một kiểu định danh nội bộ đang được hỗ trợ trong form đột nhiên không convert được.
Đội đăng ký Converter để map String sang một entity trong database, khiến mỗi lần nhập mã khách trong form lại gọi database và làm tăng latency dưới tải cao.
Một service dùng Converter từ số tiền sang đơn vị tiền tệ mặc định nhưng dữ liệu đối tác có currency khác, khiến giá trị được bind đúng kiểu Java nhưng sai ý nghĩa nghiệp vụ.
Nhóm chuyển một JSON property dạng number sang Java String rồi vào enum qua nhiều converter, khiến request dữ liệu cũ được chấp nhận dù hợp đồng mới chỉ cho phép mã chữ.
Ứng dụng truyền LocalDate từ HTTP vào DTO nhưng formatter dùng múi giờ hệ thống để diễn giải ngày, khiến một số request ở cuối ngày bị gán sang ngày trước.
Đội thêm AnnotationFormatterFactory theo custom annotation cho field số điện thoại nhưng một DTO khác dùng annotation đó với quy tắc vùng khác, khiến validation không thống nhất.
Một service cấu hình FormattingConversionService cho MVC nhưng bài kiểm thử gọi Converter trực tiếp, khiến lỗi định dạng phần thập phân theo locale chưa được phát hiện.
Nhóm dùng @DateTimeFormat cho ngày bắt đầu hợp đồng nhưng trình duyệt gửi định dạng tháng/ngày, khiến người dùng tại Việt Nam nhập đúng theo giao diện vẫn nhận lỗi.
Ứng dụng dùng @NumberFormat cho tổng tiền nhưng khi locale tiếng Đức áp dấu chấm phân tách hàng nghìn, một số số tiền nhập thành giá trị khác dự kiến.
Đội muốn hiển thị số lượng theo locale nhưng một Formatter có parse và print không đối xứng, khiến người dùng mở rồi lưu lại form không sửa gì cũng làm đổi dữ liệu.
Một service dùng Formatter<LocalTime> trong một lịch hẹn nhưng khách nhập thời gian 12 giờ có AM/PM, khiến dữ liệu từ thiết bị di động không được parse.
Nhóm cấu hình LocaleResolver trên MVC nhưng màn hình đặt hàng có cookie locale cũ, khiến error messages và field formatting không theo ngôn ngữ vừa được khách chọn.
Ứng dụng có một custom Formatter đọc số tiền với dấu phẩy nhưng không xử lý dấu khoảng trắng không ngắt dòng, khiến dữ liệu copy từ bảng tính bị báo lỗi trên vài trình duyệt.
Đội dùng conversion cho chuỗi thời gian làm việc theo timezone UTC nhưng người dùng chỉ nhập local date và hour, khiến thời điểm hẹn bị dịch sai ở thị trường khác.
Một service cần parse mã quốc gia theo chuẩn ISO nhưng có các mã cũ trong database, khiến converter dùng lúc binding và converter dùng khi đọc hồ sơ chấp nhận các tập mã khác nhau.
Nhóm xây dynamic form có field kiểu List<LocalDate> nhưng FormattingConversionService chỉ được test cho một giá trị ngày, khiến lỗi ở phần tử thứ ba không có vị trí field rõ ràng.
Ứng dụng dùng ConversionService trong batch ngoài web và thiếu LocaleContext, khiến số liệu nhập từ file đa quốc gia luôn được parse theo locale mặc định JVM.
Đội có Converter<String,Instant> đòi timezone offset nhưng frontend chỉ gửi ngày giờ địa phương, khiến biểu mẫu đặt lịch không thể nhập dù trình duyệt cung cấp giá trị hợp lệ cho widget.
Một service cho phép sửa số tiền qua form nhưng formatter round khi print tới hai chữ số, khiến khi người dùng lưu lại một giá trị có precision cao thì dữ liệu thay đổi.
Nhóm thay DecimalFormatSymbols trong một Formatter singleton theo request, khiến nhiều request locale khác nhau có thể bị trộn định dạng số.
Ứng dụng gặp lỗi khi parse ngày không tồn tại như 31/02 nhưng response chỉ nói conversion failed, khiến khách không biết trường nào cần sửa.
Đội dùng @DateTimeFormat cho tham số @RequestParam nhưng endpoint nhận @PathVariable ngày theo mẫu khác, khiến cùng loại dữ liệu có hai hợp đồng parse không nhất quán.
Một service cấu hình MessageSource lỗi validation bằng locale tiếng Việt nhưng Formatter vẫn dùng locale tiếng Anh, khiến thông báo hướng dẫn nhập ngày không khớp cú pháp hệ thống chấp nhận.
Nhóm dùng Converter chuyển String sang đối tượng nghiệp vụ có logic phức tạp và ném RuntimeException không rõ mã, khiến BindingResult không cung cấp thông tin field có ích cho giao diện.
Ứng dụng muốn chấp nhận ngày có dấu gạch chéo lẫn gạch ngang nhưng formatter phân giải hai format theo thứ tự khác nhau, khiến một vài giá trị ngày mơ hồ bị hiểu không nhất quán.
Đội định chuyển mã bưu chính thành số nguyên để dễ validate, khiến các mã bắt đầu bằng số 0 bị mất ký tự khi DataBinder chuyển kiểu.
Một service truyền số tài khoản dưới dạng numeric JSON nhưng độ dài vượt giới hạn JavaScript number ở frontend, khiến server nhận giá trị đã bị làm tròn trước khi validation chạy.
Nhóm parse thời gian giao hàng từ chuỗi tự do nhưng không xét thay đổi giờ mùa hè tại một thị trường, khiến appointment được tạo tại thời điểm không tồn tại.
Ứng dụng hỗ trợ danh sách số lượng trong form và dùng Converter<String, Integer>, nhưng một giá trị quá lớn gây overflow và cả giỏ hàng không được lưu.
Đội dùng @Valid để kiểm tra CustomerForm nhưng chưa thêm ràng buộc trên trường email, khiến form chỉ kiểm tra object tồn tại và chấp nhận địa chỉ email không đúng định dạng.
Một service khai báo @NotNull trên tên hiển thị String và nghĩ chuỗi chỉ gồm khoảng trắng bị chặn, khiến nhiều hồ sơ có tên vô nghĩa vẫn được tạo.
Nhóm áp @NotBlank cho một field ID tùy chọn trong bước tạo nháp, khiến khách không thể lưu bản nháp trước khi nhập đủ thông tin.
Ứng dụng dùng @Size cho giá trị tiếng Việt có emoji nhưng bộ đếm độ dài nghiệp vụ dựa trên số ký tự hiển thị, khiến người dùng thấy thông báo tối đa không khớp input thực.
Đội khai báo @Pattern cho mã bưu chính chỉ cho phép chữ số, khiến mã hợp lệ ở những quốc gia có chữ cái không được chấp nhận.
Một service dùng @Email để kiểm tra địa chỉ liên hệ nhưng nghiệp vụ yêu cầu địa chỉ thuộc domain công ty, khiến một email đúng cú pháp vẫn không đáp ứng quy tắc đăng ký.
Nhóm dùng @Min trên số tiền BigDecimal cần đơn vị nhỏ hơn 1, khiến giá trị 0,5 được xử lý khác yêu cầu nghiệp vụ vì chọn constraint không phù hợp.
Ứng dụng gắn @DecimalMin lên giá bán nhưng trường được convert từ String sai dấu thập phân trước validation, khiến mức giá bị kiểm tra trên một số khác giá người dùng nhập.
Đội dùng @Positive cho số lượng hàng nhưng trường hợp hoàn trả cho phép giá trị âm, khiến cùng DTO không phù hợp hai workflow nghiệp vụ.
Một service dùng @Past cho ngày sinh nhưng chính sách có giới hạn tuổi tối thiểu và không đảm bảo điều kiện đó, khiến một số tài khoản dưới tuổi vẫn được đăng ký.
Nhóm áp @FutureOrPresent cho ngày hẹn nhưng so sánh bằng clock của máy chủ khác múi giờ người dùng, khiến lịch hẹn trong ngày bị từ chối bất ngờ.
Ứng dụng dùng @NotEmpty cho danh sách sản phẩm và nghĩ mọi phần tử đều hợp lệ, khiến giỏ có một sản phẩm với số lượng âm vẫn qua được kiểm tra danh sách.
Đội khai báo @Valid trên OrderForm nhưng quên cascade validation xuống orderLines, khiến các ràng buộc trên từng dòng đơn không được chạy trong request tạo đơn.
Một service dùng nested DTO cho địa chỉ có @NotBlank nhưng quên kiểm tra phần tử trong danh sách địa chỉ phụ, khiến một nhánh collection cho phép dữ liệu không hợp lệ.
Nhóm đưa @NotNull vào phần tử collection nhưng dữ liệu nhận được có một phần tử null do binding list index, khiến lỗi trên phần tử đó không được phản ánh như frontend dự kiến.
Ứng dụng định cấm mã khuyến mãi rỗng trong Map<String, CouponDto> nhưng constraint chỉ gắn lên property Map, khiến một value bên trong vi phạm quy tắc mà không được phát hiện.
Đội dùng @Valid cho request chứa Optional<Address> nhưng đường validation khi không có địa chỉ và khi Optional chứa object cần được phân biệt theo yêu cầu tạo đơn.
Một service có custom @Constraint kiểm tra mã định danh theo hệ thống ngoài nhưng validator gọi HTTP đồng bộ cho mỗi phần tử, khiến việc tạo lô người dùng chậm bất thường.
Nhóm triển khai ConstraintValidator giữ giá trị tenant hiện tại trong field mutable, khiến hai request khác tenant chạy đồng thời có thể kiểm tra theo sai quy tắc.
Ứng dụng tạo constraint liên trường xác minh endDate sau startDate nhưng lỗi được gắn lên object, khiến frontend chỉ biết form sai mà không xác định trường nào cần sửa.
Đội xây kiểm tra mật khẩu xác nhận khớp với mật khẩu gốc nhưng không phân biệt request tạo mới và đổi mật khẩu, khiến form chỉnh hồ sơ bị bắt nhập lại mật khẩu.
Một service dùng annotation validation cho chuỗi code nhưng một mã hợp lệ ở sản phẩm mới chưa có trong whitelist đang chạy, khiến rollout dữ liệu và ứng dụng mất đồng bộ.
Nhóm cần kiểm tra cặp currency và amount nhưng khai báo constraint riêng trên mỗi field, khiến từng field đều hợp lệ còn tổ hợp giá trị vi phạm chính sách.
Ứng dụng có quy tắc một trong hai số điện thoại hoặc email phải được nhập, nhưng @NotBlank trên cả hai field khiến người dùng không thể hoàn tất dù đã cung cấp một cách liên lạc.
Đội sử dụng constraint cho mã đơn duy nhất bằng cách truy vấn database, nhưng hai POST đồng thời cùng thấy chưa tồn tại nên tạo mã trùng khi không có ràng buộc ở nguồn.
Một service custom Validator kiểm tra danh sách orderItems nhưng giả định thứ tự phần tử cố định, khiến khi người dùng sắp xếp dòng trên UI thông báo lỗi trỏ sai mặt hàng.
Nhóm viết org.springframework.validation.Validator dùng supports cho class cha, nhưng một subclass mới không được công nhận nên quy tắc bắt buộc không được áp dụng.
Ứng dụng đăng ký Spring Validator chỉ ở controller tạo mới nhưng endpoint PATCH tương ứng không sử dụng Validator đó, khiến hai đường cập nhật áp quy tắc khác nhau.
Đội gọi SmartValidator với validation hints nhưng custom validator bỏ qua hints, khiến một số rule dành riêng cho nhóm duyệt được chạy ngay ở bước tạo nháp.
Một service kết hợp Spring Validator và Jakarta Bean Validation cho cùng DTO nhưng cả hai báo một lỗi giống nhau, khiến frontend hiển thị hai thông báo trùng trên một field.
Nhóm đổi validator provider trong môi trường production nhưng vẫn giả định mọi custom ConstraintValidator được tạo bằng Spring và có dependency injection, khiến một rule lỗi khởi tạo.
Ứng dụng sử dụng Validation.buildDefaultValidatorFactory bên ngoài Spring context, khiến ConstraintValidator cần service bean không được cung cấp như khi validate qua Spring MVC.
Đội dùng LocalValidatorFactoryBean cho Bean Validation nhưng không truyền MessageSource theo cấu hình đa ngôn ngữ, khiến thông báo annotation xuất hiện bằng tiếng Anh trong form Việt.
Một service khai báo nhiều constraint trên một field nhưng thứ tự báo lỗi trên UI được giả định cố định, khiến các lần chạy Java provider khác nhau cho trải nghiệm không nhất quán.
Nhóm dùng group sequence để chạy ràng buộc cơ bản trước kiểm tra tốn tài nguyên nhưng cấu hình các nhóm không như dự kiến, khiến query database vẫn được gọi với input sai cú pháp.
Ứng dụng có validation groups Create và Update nhưng controller PATCH sử dụng nhóm Create, khiến mã định danh không gửi trong request sửa bị báo thiếu.
Đội tạo @Validated(Update.class) cho phương thức sửa nhưng một endpoint dùng @Valid mặc định, khiến hai API áp những quy tắc khác nhau trên cùng model.
Một service có group sequence theo trạng thái tài khoản nhưng một rule trong nhóm cuối cần dữ liệu chỉ có sau chuyển đổi, khiến lỗi runtime xuất hiện với input hợp lệ về cú pháp.
Nhóm kiểm tra @NotBlank trên query object trong API tìm kiếm nhưng người dùng có thể bỏ bộ lọc, khiến trang kết quả mặc định bị từ chối.
Ứng dụng xây rule @AssertTrue để bảo đảm chấp thuận điều khoản nhưng DTO deserialized thiếu trường và getter tính trạng thái mặc định, khiến kiểm tra không phản ánh việc khách đã chọn hay chưa.
Đội dùng @Digits cho mã số thuế được lưu dạng String nhưng số 0 ở đầu là một phần định danh, khiến một đường nhập dựa trên numeric conversion làm mất mã gốc.
Một service yêu cầu file đính kèm có dung lượng tối đa và loại MIME hợp lệ nhưng chỉ kiểm tra filename extension, khiến request chứa payload khác loại vẫn vượt qua vòng validation.
Nhóm định dùng @Valid trên Mono<CreateOrderRequest> trong WebFlux nhưng kiểm thử chỉ gửi object trực tiếp, khiến hành vi binding/validation khi Publisher phát error chưa được quan sát.
Ứng dụng có rule cross-field đòi startAt trước endAt nhưng input thiếu một trong hai field, khiến ConstraintValidator ném exception thay vì trả lỗi hợp lệ cho người dùng.
Đội thêm một trường mới bắt buộc trong DTO production nhưng khách mobile cũ không gửi field, khiến mọi lệnh tạo hồ sơ bị từ chối sau deploy.
Một service validate số tài khoản theo quốc gia nhưng dùng một regex chung, khiến các định dạng hợp lệ của chi nhánh nước ngoài bị chặn khi mở rộng thị trường.
Nhóm áp kiểm tra tương tác đồng thời với database bên trong ConstraintValidator không có timeout, khiến chuỗi xử lý HTTP bị kẹt khi database chậm.
Ứng dụng sử dụng @NotNull cho giá trị Boolean cần người dùng xác nhận, nhưng giá trị false vẫn hợp lệ theo constraint trong khi chính sách yêu cầu lựa chọn true.
Đội muốn phân biệt thanh toán trước với thanh toán sau trong validation groups nhưng class-level validator chỉ nhận một DTO chung, khiến một nhóm quy tắc bị bỏ qua.
Một service kiểm tra tên trường trong một Map linh hoạt nhưng payload gửi key chưa từng có, khiến Validator bỏ qua key mà hợp đồng API không công nhận.
Nhóm chuyển model form sang Java record với các ràng buộc trên component nhưng bộ test chỉ kiểm tra getter của JavaBean cũ, khiến đường validate record chưa được chứng minh.
Ứng dụng nhận dữ liệu bản nháp mà người dùng có thể điền dần nhưng Validator chỉ có chế độ full validation, khiến API không lưu được tiến độ chưa hoàn chỉnh.
Đội định validate object lồng trong Optional nhưng tùy nhánh deserialization mà object không được tạo, khiến một request bị coi như không có địa chỉ thay vì địa chỉ sai.
Một service dùng method validation @Validated trên service công khai nhưng một lời gọi nội bộ cùng bean không đi qua proxy, khiến tham số sai không bị kiểm tra ở đường batch.
Nhóm khai báo constraint trên method return value để bảo đảm không trả danh sách rỗng, nhưng một nhánh service dùng dữ liệu cache cũ và vi phạm mà tầng HTTP không có xử lý lỗi phù hợp.
Ứng dụng dùng method validation cho tham số PageSize nhưng client gửi giá trị vượt giới hạn, khiến exception được ném khác đường Bean Validation của request body.
Đội thêm method validation vào service có nhiều interface nhưng metadata constraint giữa interface và implementation không nhất quán, khiến khởi động hoặc invocation gặp lỗi validation.
Một service bật method validation để kiểm tra số tiền trong luồng @Async, nhưng exception xảy ra sau khi controller đã trả thành công nên khách không nhận thông báo lỗi.
Nhóm dùng @Validated trên interface repository service rồi gọi một implementation thông qua object tự tạo, khiến quy tắc method parameter validation không được thực thi.
Ứng dụng cần validate response DTO trước khi gửi đối tác nhưng chỉ validate request vào, khiến một số giá trị null từ database làm payload trả về vi phạm hợp đồng ngoài.
Đội áp @Valid cho danh sách tham số method nhưng không rõ phần tử bên trong được cascade, khiến một object lỗi chỉ bị phát hiện khi lưu xuống database.
Một service có constraint trên method result chứa dữ liệu y tế nhưng exception handler ghi toàn bộ invalid value, khiến thông tin nhạy cảm có mặt trong logs.
Nhóm dùng Bean Validation message template với tham số tính toán nhưng không escape hợp lý nội dung nguồn, khiến thông báo được tạo có chuỗi khó hiểu cho khách.
Ứng dụng lưu tên trường với ký tự Unicode vào constraint message nhưng khách tiếng Anh nhận nội dung tiếng Việt vì message bundle thiếu bản dịch.
Đội dùng ValidationMessages.properties riêng nhưng ứng dụng có ResourceBundleMessageSource khác, khiến lỗi annotation và lỗi business rule xuất hiện với ngôn ngữ khác nhau.
Một service đăng ký MessageSource basename mới sau khi tách module nhưng file ngôn ngữ cho lỗi validation chưa được đóng gói vào artifact, khiến UI hiển thị mã lỗi thô.
Nhóm dùng FieldError message code theo tên object đầy đủ trong Spring MVC nhưng file messages chỉ chứa code tổng quát, khiến cùng lỗi có message đúng ở một form và thiếu ở form khác.
Ứng dụng xây ErrorResponse chỉ từ defaultMessage mà không lưu mã lỗi máy đọc được, khiến frontend không thể định vị field theo hợp đồng khi đổi ngôn ngữ.
Đội dùng BindingResult.getAllErrors rồi chỉ trả lỗi đầu tiên, khiến một biểu mẫu có nhiều field sai buộc người dùng gửi đi nhiều lần mới thấy đủ vấn đề.
Một service trả lỗi validation theo thứ tự của HashMap chứ không theo vị trí field, khiến màn hình form mỗi lần submit lại sắp xếp cảnh báo theo thứ tự khác.
Nhóm dùng Errors.reject cho lỗi của object nhưng frontend chỉ hiển thị FieldError, khiến lỗi tương quan startDate/endDate hoàn toàn không xuất hiện trước mắt khách.
Ứng dụng dùng rejectValue với nested path không khớp DTO mà frontend gửi, khiến lỗi được báo ở địa chỉ field không tồn tại và màn hình không tô đỏ đúng ô.
Đội có nhiều item trong danh sách đơn hàng nhưng BindingResult không mang index của phần tử bị lỗi vào response, khiến khách không biết mặt hàng nào cần sửa.
Một service dùng DefaultMessageCodesResolver nhưng bộ dịch chỉ định nghĩa thông báo typeMismatch cho một field cụ thể, khiến các trường khác cùng lỗi nhận mã chưa dịch.
Nhóm thay objectName trong @ModelAttribute từ orderForm sang checkoutForm nhưng messages bundle chứa mã cũ, khiến bản phát hành mới hiển thị thông báo fallback.
Ứng dụng nhận lỗi typeMismatch trên LocalDate và chỉ hiển thị thông báo chung, khiến khách không biết cần nhập ngày theo định dạng nào của locale đang chọn.
Đội trả BindingResult trong HTTP response gồm cả rejectedValue, khiến giá trị mật khẩu vừa nhập được gửi lại cho frontend và có thể xuất hiện trong browser logs.
Một service đưa toàn bộ Errors.toString vào log khi validate thất bại, khiến thông tin nhận dạng cá nhân và access token bị ghi ra môi trường quan sát.
Nhóm đặt tên resource bundle với dấu gạch dưới locale khác convention cần thiết, khiến một số thông báo tiếng Việt không được chọn dù file bản dịch đã tồn tại.
Ứng dụng dùng Accept-Language để chọn bản dịch lỗi nhưng client mobile gửi ngôn ngữ không có trong hệ thống, khiến thông báo fallback không rõ hoặc xuất hiện mã technical.
Đội triển khai cơ chế đổi ngôn ngữ trong MVC bằng locale cookie nhưng phần trả lỗi từ một @ControllerAdvice sử dụng default Locale, khiến cùng request có hai ngôn ngữ.
Một service dùng LocaleContext của WebFlux để sinh message lỗi nhưng helper async lấy Locale từ ThreadLocal cũ, khiến response lỗi không theo ngôn ngữ request.
Nhóm định ghép tên field vào thông báo bằng MessageSource arguments nhưng template và tham số không cùng số lượng, khiến người dùng thấy placeholder chưa được thay.
Ứng dụng có thông báo ràng buộc số lượng tối đa nhưng error message cố định ghi giới hạn cũ, khiến UI hướng dẫn sai sau khi business đổi limit.
Đội lưu code của lỗi field trong JSON nhưng không phân biệt validation và conversion error, khiến frontend hiển thị gợi ý nhập sai cho trường chưa thể parse.
Một service dựng ProblemDetail từ MethodArgumentNotValidException nhưng bỏ path chi tiết của nested errors, khiến client chỉ nhận 400 mà không có địa chỉ input sai.
Nhóm có handler exception MVC chỉ bắt MethodArgumentNotValidException nhưng một lỗi binding form phát sinh BindException, khiến API trả cấu trúc lỗi khác.
Ứng dụng bắt mọi ValidationException thành HTTP 500 mặc dù nhiều lỗi là request không hợp lệ, khiến client retry vô ích và dashboard báo nhầm lỗi hạ tầng.
Đội dùng HandlerMethodValidationException trên controller parameter của phiên bản Spring mới nhưng error mapper cũ chỉ nhận một loại exception validation, khiến client nhận schema lỗi không nhất quán.
Một service WebFlux dùng WebExchangeBindException khi ràng buộc request model nhưng handler chung với MVC giả định BindingResult luôn có cùng cách khôi phục, khiến lỗi field bị thiếu trong response.
Nhóm sử dụng @ExceptionHandler cho lỗi validation nhưng một phản hồi HTTP streaming đã bắt đầu gửi body, khiến không thể đổi status sang 400 khi validation phát sinh muộn.
Ứng dụng đưa exception message do Converter ném thẳng ra JSON public, khiến tên package Java và cấu trúc field nội bộ bị lộ cho client.
Đội muốn hỗ trợ accessibility cho thông báo lỗi field nhưng mã trả về chỉ chứa text đã dịch, khiến screen reader không biết lỗi thuộc input nào.
Một service định dùng MessageSource chung cho email xác nhận và validation HTTP nhưng cache locale cũ giữ message sau khi triển khai bản dịch mới, khiến người dùng vẫn thấy hướng dẫn lỗi cũ.
Nhóm chỉnh sửa resource bundle cho ràng buộc số tiền nhưng một service khác có file cùng basename và key, khiến nội dung bản dịch được chọn khác theo thứ tự cấu hình.
Ứng dụng phân biệt trường bắt buộc với trường sai định dạng nhưng frontend gom tất cả dưới thông báo dữ liệu không hợp lệ, khiến người dùng sửa dữ liệu khó hơn sau chuyển API.
Đội lưu localized defaultMessage trong audit thay vì error code trung lập, khiến phân tích số lỗi theo loại bị chia nhỏ theo ngôn ngữ của người dùng.
Một service tạo field error object có message tiếng Anh vì không lấy locale request từ ngữ cảnh WebFlux, khiến người dùng chọn tiếng Việt vẫn nhận lỗi bằng tiếng Anh.
Nhóm gửi danh sách lỗi validation cho ứng dụng di động nhưng thay tên JSON property fieldPath trong một bản cập nhật, khiến client cũ không tô sáng ô sai.
Ứng dụng dùng Jakarta Validation trên @RequestBody nhưng một request JSON sai cú pháp bị parser từ chối trước bước validation, khiến frontend nhận lỗi khác với quy tắc field.
Đội xây endpoint MVC nhận @ModelAttribute qua query parameters và form body nhưng chưa phân biệt nguồn dữ liệu tin cậy, khiến giá trị query có thể ghi đè giá trị người dùng nhập.
Một service có @RequestParam số lượng kiểu int và kỳ vọng @NotNull bắt lỗi khi thiếu trường, nhưng binding thất bại từ trước nên lỗi được trả không giống thông báo yêu cầu.
Nhóm dùng @RequestBody DTO với một field enum nhưng client gửi giá trị không thuộc tập mã cho phép, khiến JSON conversion error xảy ra trước khi custom Validator được gọi.
Ứng dụng đặt BindingResult trước parameter @Valid thay vì ngay sau argument được validate, khiến framework không cung cấp lỗi cho controller như cách xử lý cũ mong đợi.
Đội có MVC form với BindingResult nhưng một nhánh controller vẫn gọi service lưu dữ liệu khi có field errors, khiến database nhận bản ghi không hợp lệ.
Một service dùng @InitBinder với target name chỉ phù hợp cho customerForm nhưng endpoint mới đổi tên @ModelAttribute, khiến cấu hình giới hạn field không còn áp dụng.
Nhóm nhận @RequestPart metadata JSON và multipart file trong cùng request, nhưng validation metadata không chạy giống đường @RequestBody đã được kiểm thử.
Ứng dụng có controller dùng @RequestBody cho dữ liệu nhập nhưng DTO có field chỉ dành cho server như createdBy, khiến JSON client có thể thử tự điền actor.
Đội gửi JSON null cho trường không được phép xóa nhưng DTO mặc định chứa null và validation groups của PATCH không phản ánh khác biệt giữa không gửi và gửi null.
Một service nhận HTTP PATCH từng phần nhưng validation full object đòi cả các trường không cập nhật, khiến khách không thể sửa duy nhất số điện thoại.
Nhóm dùng request body có danh sách items rất lớn và Bean Validation kiểm tra từng phần tử, khiến thời gian validate và memory tăng mạnh khi khách gửi payload vượt ngân sách.
Ứng dụng tạo form HTML có các checkbox liên quan nhưng Java DTO giữ boolean primitive, khiến không phân biệt được khách cố chọn false và trình duyệt bỏ gửi field.
Đội hỗ trợ nested form cho lịch trình nhiều điểm dừng nhưng một input path có index vượt auto-grow limit, khiến request bị từ chối mà client không nhận được lý do rõ.
Một service dùng @SessionAttributes lưu model form giữa hai bước nhưng DataBinder lần sau tái sử dụng dữ liệu cũ, khiến trường ở bước đầu không phản ánh chỉnh sửa mới từ khách.
Nhóm bind object ở MVC controller từ query parameter rồi validate ownership bằng accountId từ DTO, khiến khách thử sửa accountId để cập nhật hồ sơ không thuộc mình.
Ứng dụng dùng một DTO vừa làm JSON input vừa làm response, khiến những field chỉ có ở response như internalStatus cũng được đưa vào bề mặt bind của request.
Đội muốn giữ input gốc để hiện lại form sau typeMismatch nhưng converter đã thay đổi một phần object, khiến giá trị người dùng nhập bị mất khi trang được render lại.
Một service xử lý file CSV thành từng DTO bằng DataBinder nhưng một dòng lỗi không được lưu kèm số dòng nguồn, khiến người dùng không sửa được bản ghi trong file import.
Nhóm có upload ảnh với thuộc tính mô tả nhưng kiểm tra MIME type chỉ dựa vào Content-Type do client gửi, khiến tệp sai định dạng vẫn vượt qua rule đầu vào.
Ứng dụng có MVC handler thêm dữ liệu form vào model khi validation lỗi nhưng vô tình đưa cả hash mật khẩu của entity vào template, khiến trường nhạy cảm có nguy cơ hiển thị.
Đội áp dụng Validator tại controller nhưng các lệnh cập nhật từ Kafka consumer bỏ qua vòng kiểm tra tương ứng, khiến bản ghi nhập ngoài HTTP không đạt quy tắc dữ liệu.
Một service chuyển từ MVC sang WebFlux nhưng vẫn đăng ký một custom Formatter trong cấu hình MVC cũ, khiến endpoint reactive không hiểu mã định danh theo format mới.
Nhóm dùng WebFlux functional handler đọc JSON vào DTO nhưng bỏ qua thao tác validate sau deserialize, khiến cùng model được kiểm tra ở annotation controller nhưng không ở route chức năng.
Ứng dụng chạy WebFlux với Validator cần truy cập JDBC đồng bộ để kiểm tra mã khách, khiến Netty event loop bị giữ lâu khi nhiều request hợp lệ đến đồng thời.
Đội có WebFlux handler trả Mono<ServerResponse> nhưng dữ liệu được kiểm tra trong callback ngoài chuỗi reactive, khiến response được gửi trước khi quyết định validation hoàn tất.
Một service dùng Reactive WebFilter để lấy locale và security context nhưng một helper xác thực yêu cầu lại dựa vào ThreadLocal, khiến thông tin validate giữa các nhánh không nhất quán.
Nhóm gọi block trong reactive validation để hỏi database, khiến API WebFlux tăng latency đột ngột khi datasource chậm dù handler vẫn trả Mono.
Ứng dụng xử lý hàng nghìn item bằng Flux rồi dùng Validator cho từng phần tử, nhưng lỗi của một item kết thúc cả subscription mà client cần bản báo lỗi theo từng dòng.
Đội gửi request WebFlux chứa danh sách field nested lớn hơn giới hạn codec, khiến lỗi nhận body xuất hiện trước Bean Validation và hệ thống trả thông báo không đúng trường hợp.
Một service xử lý WebFlux @RequestBody theo Publisher nhưng Validator được gọi trước khi body thực tế được decode, khiến kiểm tra dựa trên object chưa có dữ liệu.
Nhóm xây API WebFlux trả lỗi validation đa ngôn ngữ qua WebExchangeBindException nhưng message lookup chưa dùng LocaleContext, khiến language header bị bỏ qua.
Ứng dụng có cả MVC và WebFlux modules với hai cấu hình ConversionService khác nhau, khiến cùng ngày sinh được chấp nhận ở API cũ nhưng từ chối ở API mới.
Đội chuyển một endpoint MVC sang WebFlux nhưng áp dụng validator có trạng thái mutable vốn chỉ chạy tuần tự trong test, khiến kết quả sai khi request reactive đồng thời.
Một service nhận thông báo validate của WebFlux qua Mono nhưng client hủy request giữa chừng, khiến job kiểm tra dữ liệu bên ngoài tiếp tục chạy mà không có người sử dụng kết quả.
Nhóm dùng Reactive Streams cho request body và tích lũy toàn bộ field errors trong List chung, khiến những subscription đồng thời ghi đè trạng thái lỗi của nhau.
Ứng dụng xử lý lỗi typeMismatch trong WebFlux nhưng chỉ kiểm tra status 400 ở integration test, khiến schema fieldErrors không phù hợp hợp đồng mobile.
Đội có WebFlux endpoint xử lý PUT với JSON body hợp lệ nhưng security validation dùng một service bất đồng bộ được subscribe tách rời, khiến client nhận kết quả trước khi bị phát hiện thiếu quyền.
Một service cần chặn field lạ từ input JSON trong WebFlux nhưng chỉ cài ignoreUnknownFields trên WebDataBinder cho form, khiến cấu hình không tác động như kỳ vọng với JSON deserialization.
Nhóm dùng Bean Validation trong WebFlux cho email nhưng một custom Validator đồng bộ đọc file cấu hình lớn trên event loop, khiến request đăng ký trì hoãn khi đĩa chậm.
Ứng dụng có một request ID trong Reactor Context nhưng error mapper dùng thread-local MDC để log validation failure, khiến các lỗi input khó nối với HTTP request gốc.
Đội chuyển từ @ModelAttribute form sang @RequestBody JSON nhưng vẫn trông đợi field marker cho checkbox, khiến người dùng bỏ chọn tùy chọn không được xử lý như trước.
Một service xử lý đồng thời request ở các locale khác nhau bằng Formatter singleton có state thay đổi theo request, khiến một khách nhận định dạng số của khách khác.
Nhóm kiểm thử @Valid trên controller WebFlux chỉ với Mono.just DTO hợp lệ nhưng không gửi HTTP JSON sai kiểu, khiến lỗi conversion chưa được kiểm chứng.
Ứng dụng thiết lập quy tắc cần quyền admin mới sửa hạn mức nhưng validation chỉ kiểm tra khoảng số, khiến mass assignment vẫn có thể thay giá trị đúng cú pháp nhưng không được phép.
Đội để field ownerId trong DTO nhập từ khách rồi dùng nó quyết định tenant lưu bản ghi, khiến một user có thể thay ownerId để tạo tài liệu cho tổ chức khác.
Một service cập nhật tài khoản bằng DTO có trường passwordHash và nghĩ @JsonIgnore của đường xuất JSON đủ để chặn binding mọi loại request, khiến nguy cơ sửa field từ đầu vào chưa được kiểm chứng.
Nhóm giới hạn allowedFields theo pattern rộng như account.* cho một biểu mẫu, khiến property mới account.permissions sau refactor cũng trở thành trường có thể gán.
Ứng dụng nhận dữ liệu nested profile.securityQuestions từ khách nhưng không dùng DTO chuyên biệt, khiến những câu trả lời bảo mật có thể bị ghi từ một form chỉ sửa địa chỉ.
Đội nhập dữ liệu từ CSV bằng BeanWrapper và bỏ kiểm tra tên cột, khiến file của đối tác có header lạ có thể ghi vào thuộc tính internalRiskScore.
Một service khai báo nhóm validation chỉ kiểm tra giá trị của role hợp lệ, nhưng chưa kiểm tra người gửi có được sửa role hay không, khiến input đúng kiểu vẫn gây leo thang quyền.
Nhóm dùng DataBinder.setAllowedFields cho hai nhóm user nhưng một bean binder được tái sử dụng không đúng vòng đời, khiến whitelist của request quản trị ảnh hưởng request khách thường.
Ứng dụng kiểm tra số tiền trên client rồi chuyển thẳng vào domain entity server, khiến request sửa thủ công bỏ qua giao diện có thể gửi số âm không hợp lệ.
Đội có constraint kiểm tra userId thuộc tập định danh hợp lệ nhưng không xác nhận userId thuộc tenant của caller, khiến cross-tenant access không bị chặn bởi validation cú pháp.
Một service nhận danh sách địa chỉ của người dùng nhưng mỗi phần tử có field verifiedBy do hệ thống đặt, khiến client có thể tự xác nhận địa chỉ nếu object được bind nguyên trạng.
Nhóm ghi rejectedValue của tất cả FieldError ra audit để điều tra hành vi xấu, khiến mật khẩu, số tài khoản và token do người dùng nhập được lưu ở kho phân tích.
Ứng dụng trả defaultMessage chứa chuỗi nhập sai nguyên văn trong lỗi validation, khiến nội dung do người dùng kiểm soát được đưa trở lại giao diện không escape phù hợp.
Đội có API cho phép tùy chỉnh tên file import nhưng message error ghép trực tiếp tên file vào HTML email, khiến chuỗi từ bên ngoài được hiển thị ngoài quy tắc an toàn.
Một service chấp nhận object graph sâu từ biểu mẫu nhưng không giới hạn số thuộc tính được bind, khiến request được tạo có thể tiêu tốn quá nhiều CPU và bộ nhớ.
Nhóm dùng custom Converter thực hiện truy vấn database theo mỗi mã sản phẩm trong danh sách dài, khiến một request hợp lệ tạo hàng nghìn SQL calls khi nhập đơn lớn.
Ứng dụng cho phép client gửi danh sách 100 nghìn phần tử và Validator lưu một FieldError cho mỗi phần tử, khiến response lỗi phình to và gateway từ chối payload.
Đội hỗ trợ upload hồ sơ chứa hàng trăm trường tùy chỉnh nhưng cấu hình binder mặc định cho phép key không giới hạn, khiến người dùng tạo request lớn làm chậm server.
Một service áp regex validation có lượng backtracking lớn cho chuỗi người dùng tự nhập, khiến request bất thường giữ thread lâu dù không truy vấn database.
Nhóm dùng custom ConstraintValidator gọi dịch vụ chống gian lận bên ngoài không có timeout, khiến một loạt request đăng ký làm cạn thread pool khi bên thứ ba gián đoạn.
Ứng dụng chuẩn hóa số điện thoại sau validation thay vì trước, khiến số hợp lệ có dấu cách bị từ chối trong khi dữ liệu lưu cuối cùng vốn có thể chuẩn hóa.
Đội xử lý làm sạch HTML trong Converter nhưng một đường nhập batch sử dụng object đã được xây mà không qua Converter, khiến hai nguồn dữ liệu có chính sách sanitization khác nhau.
Một service bind dữ liệu từ HTTP vào DTO rồi ghi logs toàn bộ object, khiến thông tin cá nhân lộ dù response đã được che các field nhạy cảm.
Nhóm cho phép thời gian hẹn bất kỳ do client nhập nhưng constraint @Future chỉ kiểm tra tương lai, khiến lịch hẹn vượt xa phạm vi kinh doanh vẫn được nhận.
Ứng dụng dùng cùng DTO cho API public và công cụ admin, khiến bộ rule @Validated không phân biệt được quyền sở hữu và loại request ở đường public.
Đội chuyển timezone của vùng triển khai nhưng bài validation so sánh ngày theo LocalDate.now mặc định, khiến cùng đầu vào hôm nay được chấp nhận ở pod này và từ chối ở pod khác.
Một service xác thực mã giảm giá còn hiệu lực bằng đồng hồ server nhưng test chỉ dùng ngày tĩnh, khiến ngày hết hạn trong vài giây quanh ranh giới giờ bị xử lý khác.
Nhóm kiểm tra giá trị @Pattern với regex cố định nhưng mã khách có Unicode tương đương nhiều dạng chuẩn hóa, khiến hai chuỗi nhìn giống nhau cho kết quả validate khác.
Ứng dụng normalize tên người dùng ở Converter nhưng constraint uniqueness kiểm tra chuỗi trước normalization trong một nhánh, khiến nhiều biến thể cùng tên được tạo.
Đội muốn cảnh báo input có field không được phép nhưng DataBinder ghi suppressedFields mà controller bỏ qua, khiến nỗ lực mass assignment không được phát hiện trong audit.
Một service trả HTTP 400 khi input có trường bị chặn nhưng không giới hạn response error fields, khiến attacker có thể kiểm tra tồn tại của các thuộc tính nội bộ qua phản hồi.
Nhóm bật rejectUnknownFields trên biểu mẫu nhưng error mapper trích property path trực tiếp từ request và log, khiến dữ liệu không tin cậy xuất hiện trong hệ thống quan sát.
Ứng dụng dùng mật khẩu làm validation input và một ConstraintValidator đưa invalidValue vào exception message, khiến raw password xuất hiện trong monitoring khi có lỗi.
Đội bảo vệ email cá nhân ở response nhưng một message template có tham số rejectedValue khi validation thất bại, khiến email vẫn có thể hiển thị trong lỗi công khai.
Một service cần kiểm tra một form theo thị trường nhưng tenant locale và quốc gia pháp lý được lấy từ hai nguồn khác nhau, khiến quy tắc định dạng hợp lệ sai theo khu vực.
Nhóm dùng @Size cho chuỗi mã truy cập có độ dài tính theo byte UTF-8, khiến các ký tự Unicode chiếm nhiều byte hơn được chấp nhận dù vượt giới hạn hệ thống downstream.
Ứng dụng kiểm tra nội dung địa chỉ trước khi lưu nhưng không chuẩn hóa Unicode NFC, khiến tìm kiếm và so sánh địa chỉ trùng hoạt động không nhất quán sau nhập.
Đội áp validation cho bản ghi đồng ý điều khoản nhưng không lưu phiên bản điều khoản khi người dùng chọn, khiến việc audit sau này không xác định được khách đã đồng ý với bản nào.
Một service truyền danh sách quyền từ client và validate rằng các giá trị đều thuộc enum, nhưng không kiểm tra nguồn cấp quyền nên việc gửi role ADMIN vẫn là input hợp lệ về kiểu.
Nhóm xây kiểm tra độ dài mật khẩu nhưng Validator trả chi tiết từng policy vào log khi người dùng thất bại, khiến dữ liệu thử đăng nhập xuất hiện trong công cụ support.
Ứng dụng có validator đọc thông tin cá nhân của người dùng khác để kiểm tra quan hệ gia đình nhưng request chỉ được phân quyền ở controller, khiến bước validation có thể thực hiện truy vấn vượt phạm vi.
Đội cập nhật schema JSON client để chấp nhận field mới nhưng Java DTO chưa có property tương ứng, khiến dữ liệu bị bỏ qua và hợp đồng API khác với những gì đối tác được thông báo.
Một service chỉ thử converter với input hợp lệ trong unit test nhưng không gửi chuỗi rỗng, null, tràn số hoặc sai locale, khiến lỗi typeMismatch chưa được phát hiện.
Nhóm kiểm thử allowedFields của DataBinder chỉ với các field được phép mà không thử role, status và internalId, khiến đường mass assignment không được kiểm chứng.
Ứng dụng unit test BeanWrapper với một property phẳng nhưng production nhận nested paths và list indices, khiến giới hạn auto-grow chưa được đánh giá trước deploy.
Đội gọi validator trực tiếp trong test nhưng không tạo WebDataBinder như HTTP thật, khiến lỗi binding xảy ra trước validation không nằm trong phạm vi suite.
Một service dùng MockMvc kiểm tra kết quả controller khi input hợp lệ nhưng không assert BindingResult.fieldErrors, khiến frontend nhận sai field code mà CI vẫn PASS.
Nhóm triển khai @WebMvcTest cho controller nhưng custom ConversionService/Formatter không được import, khiến test chấp nhận một kiểu ngày khác môi trường production.
Ứng dụng chạy integration test với locale mặc định tiếng Anh nhưng khách sử dụng tiếng Việt, khiến ResourceBundleMessageSource thiếu key bản dịch mà test không phát hiện.
Đội chỉ kiểm thử @NotNull cho string null mà không thử chuỗi trống hoặc khoảng trắng, khiến yêu cầu tên bắt buộc bị vượt qua bằng giá trị vô nghĩa.
Một service test validation groups Create nhưng không có testcase Update/PATCH, khiến trường bắt buộc ở create tiếp tục bị đòi trong update một phần.
Nhóm chạy test Jakarta Validator bằng một factory tự dựng nhưng production dùng LocalValidatorFactoryBean, khiến custom ConstraintValidator phụ thuộc bean Spring bị lỗi sau deploy.
Ứng dụng kiểm thử object-level validation bằng dữ liệu không hợp lệ ở hai field nhưng không assert object error, khiến lỗi cross-field không xuất hiện trong response mà bài test vẫn xanh.
Đội kiểm tra @Valid trên OrderForm với danh sách chỉ có một dòng, khiến lỗi index và container element constraint ở phần tử thứ ba chưa được bao phủ.
Một service kiểm thử trùng email bằng hai request tuần tự nhưng không chạy đồng thời, khiến custom uniqueness validator không chứng minh được tính đúng đắn khi race.
Nhóm tạo test method validation bằng gọi trực tiếp object được new thay vì proxy Spring, khiến annotation @Validated không thực thi mà suite chỉ assert output thành công.
Ứng dụng dùng MockMvc để test lỗi @RequestBody nhưng test chỉ gửi JSON đúng kiểu, khiến trường enum không thể parse trả lỗi schema khác chưa được phát hiện.
Đội thử @ModelAttribute binding với form text nhưng không kiểm tra checkbox bị bỏ chọn hoặc field marker, khiến một số preference không thể tắt từ giao diện.
Một service dùng WebTestClient cho WebFlux controller nhưng chỉ kiểm tra status 400, khiến nội dung lỗi WebExchangeBindException thiếu locale hoặc fieldPath mà test vẫn PASS.
Nhóm kiểm thử reactive handler với Mono.just DTO đã được tạo sẵn, khiến lỗi Jackson decode, missing property và type conversion trong HTTP body không được mô phỏng.
Ứng dụng test lỗi đa ngôn ngữ bằng cách đổi Locale mặc định toàn JVM, khiến chạy suite song song làm kết quả các testcase ảnh hưởng lẫn nhau.
Đội kiểm tra formatter parse với ngày tháng hợp lệ nhưng không thử 31/02, leap day hoặc thời điểm đổi giờ, khiến trường hợp lịch hẹn hiếm bị xử lý sai.
Một service dùng property-based tests cho mã định danh nhưng không sinh ký tự Unicode kết hợp, khiến dữ liệu trông giống nhau mà khác normalization chưa được phát hiện.
Nhóm chạy API test với DTO đơn giản nhưng production gửi danh sách 20 nghìn item, khiến hiệu năng của cascaded validation và response errors chưa được kiểm tra.
Ứng dụng test validator chỉ với user admin nhưng không có user thường và tenant khác, khiến ranh giới quyền sửa field nhạy cảm chưa được đánh giá.
Đội thử @InitBinder ở một controller nhưng không kiểm thử controller còn lại dùng DTO chung, khiến whitelist được khai báo cục bộ không bảo vệ toàn bộ bề mặt API.
Một service mock MessageSource trả thông báo đã dịch cho mọi key, khiến bộ test không phát hiện lỗi thiếu resource bundle tiếng Nhật sau khi mở thị trường.
Nhóm có contract test chỉ kiểm tra HTTP status cho form lỗi mà không assert mã lỗi ổn định, khiến khi đổi tên objectName frontend cũ không định vị được input cần sửa.
Ứng dụng đặt error handling chung cho MVC và WebFlux ở hai module khác nhau nhưng chỉ chạy integration tests cho MVC, khiến API WebFlux xuất format lỗi không tương thích.
Đội kiểm thử sai kiểu số ở controller nhưng không kiểm tra rejectedValue có được che khi ghi log, khiến một mật khẩu sai format có thể xuất hiện trong hệ thống giám sát.
Một service dùng Testcontainers database để test uniqueness constraint nhưng không chạy thử tình huống constraint lỗi sau khi controller validation đã PASS, khiến error mapping không thống nhất.
Nhóm thử upload multipart bằng file nhỏ hợp lệ nhưng không có testcase filename độc hại, MIME giả và kích thước lớn, khiến chính sách input validation chưa được xác nhận đầy đủ.
Ứng dụng chạy integration tests với một locale và một timezone nhưng production có các pod ở nhiều vùng, khiến @FutureOrPresent và formatter thời gian khác nhau sau deploy.
Đội muốn chứng minh mọi field nhạy cảm bị chặn trước khi cập nhật entity, nhưng test chỉ xác nhận response 400 mà không kiểm tra trạng thái dữ liệu sau request.
Một service quan sát tỷ lệ lỗi validation chỉ theo HTTP status nhưng không gắn mã lỗi field đã ẩn danh, khiến một thay đổi formatter làm hàng nghìn khách nhập sai mà dashboard không nhận biết nguyên nhân.
Nhóm gắn toàn bộ rejectedValue vào metric labels để gỡ lỗi typeMismatch, khiến số time series tăng đột biến và dữ liệu cá nhân đi vào hệ thống quan sát.
Ứng dụng đổi ValidationMessages bundle trong phiên bản mới nhưng một số pod giữ message cache cũ, khiến khách nhận lỗi khác nhau theo load balancer dù cùng request.
Đội dùng API Gateway để kiểm soát kích thước JSON request nhưng một endpoint import CSV qua multipart không có giới hạn tương đương, khiến validator phải xử lý tệp rất lớn.
Một service tiếp nhận dữ liệu tài chính từ đối tác và cần chứng minh cùng input luôn được chuyển đổi, validate và lưu nhất quán, nhưng các đường HTTP, batch và WebFlux hiện dùng những cấu hình khác nhau.
