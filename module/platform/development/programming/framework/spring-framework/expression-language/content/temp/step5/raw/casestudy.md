Một API đặt hàng dùng SpEL truy cập customer.address.city; dữ liệu nhập từ nguồn cũ không có address khiến tính phí giao hàng lỗi với một nhóm khách.
Nhóm quản lý hồ sơ đổi tên thuộc tính profile.level thành membershipTier; biểu thức SpEL lưu trong cấu hình vẫn đọc đường dẫn cũ và bỏ sót quyền lợi.
Ứng dụng bán vé đánh giá SpEL trên object record Java thay vì JavaBean; một biểu thức dựa vào quy ước getter cũ không đọc được thông tin ghế.
Đội phát triển dùng SpEL để đọc thuộc tính từ entity có quan hệ lazy; khi đánh giá ngoài transaction, truy vấn lấy trạng thái đơn phát sinh lỗi truy cập.
Một dịch vụ tính thưởng gọi method của bean thông qua SpEL; method thực hiện truy vấn database nên mỗi lượt đánh giá gây thêm các lần truy cập không dự kiến.
Nhóm kế toán dùng SpEL đọc trường amount nullable từ giao dịch; phép cộng trên những bản ghi chưa có giá trị gây lỗi tính tổng cuối tháng.
Ứng dụng đặt phòng lấy phần tử đầu tiên của danh sách phòng bằng SpEL; các đặt chỗ không gắn phòng làm thao tác truy cập collection gặp lỗi chỉ mục.
Đội quản lý sản phẩm dùng SpEL lấy giá theo key trong Map; key có dấu gạch ngang được xử lý như cú pháp khác và một vùng nhận giá mặc định.
Nhóm xây báo cáo truy cập thuộc tính nested của địa chỉ khách; một thuộc tính trùng tên với method làm kết quả khác sau khi nâng thư viện domain.
Ứng dụng cho phép SpEL lấy timestamp từ object đơn hàng; dữ liệu giữa hai region lưu LocalDateTime với timezone khác khiến quyết định hết hạn không nhất quán.
Đội thiết kế logic giảm giá kết hợp AND và OR trong biểu thức; một tổ hợp quyền thành viên với chiến dịch đặc biệt được xét khác bảng quy tắc đã duyệt.
Nhóm quản lý tồn kho so sánh trạng thái enum với String trong SpEL; một trạng thái mới không được chuyển kiểu như dự kiến và đơn hợp lệ bị chặn.
Ứng dụng xác định ngày đáo hạn bằng phép so sánh Date trong SpEL; một nguồn sử dụng String không đúng định dạng nên lỗi chỉ xuất hiện ở production.
Đội phát triển dùng phép chia trong expression tính tỷ lệ hoàn tiền; giao dịch có tổng tiền bằng không khiến expression thất bại và API trả lỗi chung.
Nhóm dùng toán tử Elvis chọn tên người nhận mặc định; một hồ sơ có chuỗi rỗng làm email hiện tên khác kỳ vọng của bộ phận chăm sóc khách hàng.
Ứng dụng dùng safe navigation truy cập manager của nhân viên; phần còn lại của biểu thức vẫn truy cập thuộc tính trên null khiến cấu hình phân quyền lỗi.
Đội định nghĩa biểu thức điều kiện ba ngôi để chọn plan; hai nhánh trả kiểu dữ liệu khác nhau và chỉ một nhóm khách phát sinh lỗi conversion.
Nhóm dùng SpEL so sánh giá với ngưỡng decimal; tiền tệ được convert từ Double làm số tiền sát ranh giới bị xếp sai nhóm.
Ứng dụng tạo mã đối soát bằng phép nối chuỗi SpEL; một field tùy chọn có giá trị null khiến ID gửi đối tác chứa nội dung không hợp lệ.
Đội dùng T(...) để tham chiếu hằng số static trong rule; lớp Java đã đổi package làm biểu thức không được đánh giá khi khởi động production.
Nhóm sử dụng SpEL gọi static method tính thuế; sau khi method đổi tham số, expression lưu ở database không còn gọi được dù dự án biên dịch thành công.
Ứng dụng tạo object trong expression bằng toán tử new; rule đến từ bảng cấu hình có quyền chỉnh sửa rộng nên thao tác vượt ngoài mục tiêu chỉ lọc dữ liệu.
Đội lọc tên khách bằng toán tử matches của SpEL; một regex phức tạp với chuỗi đầu vào dài gây CPU spike và nghẽn luồng HTTP.
Nhóm dùng between để xét đơn thuộc dải giá; giá từ file CSV là chuỗi làm một số biên dưới hoặc trên bị so sánh sai kiểu.
Ứng dụng dùng selection của SpEL để lọc các item đã giao; phần tử null trong danh sách hàng làm rule ném lỗi với một đơn lịch sử.
Đội phát triển dùng collection projection để lấy SKU từ nhiều LineItem; một item thiếu SKU tạo kết quả không đạt hợp đồng gửi kho.
Nhóm dùng selection lấy phần tử đầu tiên thỏa điều kiện; khi không có item phù hợp, code phía sau vẫn giả định trả về object và gây lỗi.
Ứng dụng áp selection trên Map cấu hình chi nhánh; value được lưu dạng String và expression so sánh với Number khiến cùng rule có kết quả khác.
Đội chạy SpEL selection trên hàng nghìn giao dịch cho từng dòng báo cáo; việc quét collection lặp lại làm CPU tăng khi chốt sổ cuối tháng.
Nhóm dùng inline list chứa các trạng thái cho phép; enum Java đã thêm trạng thái mới nhưng rule không cập nhật nên hàng trăm đơn bị từ chối.
Ứng dụng dùng inline map để chọn handler theo vùng; một key viết hoa khác dữ liệu nguồn khiến sự kiện được chuyển nhầm handler mặc định.
Đội tính danh sách email bằng projection trên collection khách; một phần tử có địa chỉ rỗng làm lệnh gửi email thất bại nhưng parser vẫn thành công.
Nhóm dùng SpEL truy cập collection bằng chỉ mục do client gửi; chỉ mục ngoài giới hạn khiến request trả HTTP 500 thay vì lỗi validation.
Ứng dụng đánh giá selection trên ORM lazy collection; việc lọc yêu cầu tải hàng nghìn phần tử và gây N+1 mà dashboard service không thấy.
Đội dùng SpEL để gom dữ liệu từ list và map lồng nhau; một item chứa kiểu BSON khác dữ liệu Java thường khiến rule lỗi tại runtime.
Nhóm xây expression trả String từ một List; kết quả được chuyển thành chuỗi mô tả object Java và hiển thị nội dung khó hiểu trên email.
Ứng dụng dùng SpEL đọc list mutable đang được scheduler thay đổi; một request đôi khi nhận kết quả thiếu item dù dữ liệu ban đầu đầy đủ.
Đội quản trị dùng rule selection rồi projection để tìm item giá cao; những item trùng giá được sắp xếp khác khiến quyết định lấy item đầu không ổn định.
Nhóm dùng @Value với biểu thức SpEL tham chiếu bean quản lý giá; bean đó phụ thuộc ngược bean đang tạo gây lỗi vòng dependency.
Ứng dụng đổi tên bean ở một module Spring; SpEL tham chiếu tên bean cũ khiến môi trường production không thể hoàn tất startup.
Đội triển khai hai bean giá theo vùng trong cùng ApplicationContext; biểu thức tham chiếu nhầm bean và áp bảng giá châu Âu cho khách châu Á.
Nhóm cấu hình @Value kết hợp property placeholder và SpEL; một default value được xử lý như literal thay vì expression gây lỗi kiểu dữ liệu.
Ứng dụng đọc cổng kết nối từ Environment qua SpEL; giá trị String không thể chuyển sang Integer khi biến môi trường chứa ký tự phụ.
Đội triển khai bean chỉ tồn tại ở profile staging; SpEL cấu hình production vẫn tham chiếu bean đó và ứng dụng dừng khi khởi tạo context.
Nhóm dùng SpEL trong @Value để lấy danh sách region; một region chứa dấu phẩy làm cách tách dữ liệu không phù hợp danh sách thực tế.
Ứng dụng tham chiếu bean cấu hình prototype từ expression nhiều lần; mỗi lần đánh giá có thể tạo instance khác khiến giá trị cấu hình không nhất quán.
Đội tạo URL callback bằng SpEL gọi method bean chưa sẵn sàng; lỗi xuất hiện trong lúc khởi tạo và làm toàn bộ service không thể phục vụ.
Nhóm triển khai bean resolver tùy biến cho plugin; trùng alias giữa hai plugin khiến expression chọn handler không đúng module nghiệp vụ.
Ứng dụng dùng SpEL trong @EventListener(condition) để lọc event đã thanh toán; schema event mới đổi tên trường và listener không chạy dù publisher thành công.
Đội sử dụng SpEL trong @Cacheable key dựa trên mã đơn; thiếu tenantId khiến hai khách trùng mã đọc nhầm cache của nhau.
Nhóm dùng @CacheEvict với expression key khác rule @Cacheable; sau khi cập nhật giá, cache vẫn chứa kết quả cũ và khách nhìn giá không mới.
Ứng dụng dùng @Cacheable unless xét result.price; một endpoint trả null khiến biểu thức lỗi sau khi nghiệp vụ đã xử lý thành công.
Đội quản lý quyền dùng @PreAuthorize với SpEL kiểm vùng truy cập; operator OR đặt sai dẫn tới vai trò thường vượt qua ràng buộc tenant.
Nhóm refactor tên tham số method được dùng trong SpEL security; rule vẫn tham chiếu tên cũ và một số request hợp lệ bị từ chối.
Ứng dụng phân loại event bằng SpEL dựa trên header; một producer không gửi header và thông điệp đi sang nhánh xử lý lỗi.
Đội dùng SpEL để quyết định cron của scheduled task từ bean; đội vận hành đổi biến cấu hình nhưng lịch đã đăng ký không tự cập nhật.
Nhóm lưu điều kiện giá trong database dưới dạng SpEL; một rule mới tương thích payload hiện tại nhưng làm lỗi hàng nghìn giao dịch lịch sử.
Ứng dụng dùng SpelExpressionParser cho rule nhân viên nhập; một lỗi dấu ngoặc chỉ phát hiện khi khách đầu tiên thực thi rule thay vì lúc lưu.
Đội parse mỗi expression giống nhau cho mọi request; số lần parse lớn gây CPU cao dù nội dung rule không đổi.
Nhóm cache Expression theo tên rule nhưng không gắn version; sau khi quản trị sửa điều kiện, ứng dụng vẫn đánh giá bản cũ trong nhiều giờ.
Ứng dụng tạo hàng triệu key cache từ expression do người dùng nhập; bộ nhớ tăng không giới hạn và gây áp lực garbage collector.
Đội dùng ExpressionParser.parseExpression trong template không đúng ParserContext; chuỗi đáng lẽ được render lại được coi như literal và email thiếu dữ liệu.
Nhóm chạy parser trên nhiều phiên bản Spring Framework; một cú pháp được bổ sung ở phiên bản mới khiến quá trình rollback không đánh giá được rule.
Ứng dụng chỉ kiểm parse thành công trước khi lưu rule; thuộc tính không tồn tại trong root object nên lỗi chỉ xuất hiện ở lần getValue đầu.
Đội sử dụng cùng một Expression trên nhiều loại DTO; một rule có property chung nhưng type cụ thể khác làm đánh giá trên DTO thứ hai thất bại.
Nhóm tạo StandardEvaluationContext với root Customer; khi một API khác dùng root Order, expression dựa trên cùng tên field nhưng semantics dữ liệu đã khác.
Ứng dụng tái sử dụng StandardEvaluationContext singleton và gọi setRootObject cho từng request; hai người dùng đồng thời có lúc đánh giá nhầm object của nhau.
Đội lưu variable tenantId vào EvaluationContext chung; giá trị của request mới ghi đè giá trị request cũ và tạo nguy cơ truy cập chéo tenant.
Nhóm setVariable limit cho một biểu thức tính phí; một nhánh không đặt limit khiến rule trả null và bỏ qua điều kiện giới hạn.
Ứng dụng dùng tên biến trùng tên root property trong SpEL; sau lần refactor, rule đọc dữ liệu từ scope khác và áp sai hạng khách.
Đội cấu hình StandardEvaluationContext với BeanResolver cho rule nội bộ; cùng context được dùng cho request khách hàng nên khách có thể tham chiếu bean không được phép.
Nhóm cho phép rule gọi method thông qua MethodResolver; method đó thay đổi số dư mặc dù biểu thức được trình bày như điều kiện chỉ đọc.
Ứng dụng dùng PropertyAccessor tùy biến đọc field từ payload động; khi field và getter cùng tên xuất hiện, giá trị trả về thay đổi sau nâng cấp.
Đội chuyển từ StandardEvaluationContext sang SimpleEvaluationContext; những rule dùng static type reference không còn được hỗ trợ và bị lỗi trong production.
Nhóm tạo SimpleEvaluationContext ở chế độ read-only; một rule nội bộ cố setValue lên property nên chức năng cập nhật cấu hình thất bại.
Ứng dụng chọn DataBindingPropertyAccessor để hạn chế truy cập object; một expression cũ vốn dùng reflection đến trường không công khai không còn hoạt động.
Đội phát triển bổ sung custom MethodResolver cho các phép tính; việc thêm overload mới khiến tham số null được ánh xạ sang method không dự kiến.
Nhóm dùng TypeLocator tùy biến cho class helper; sau khi di chuyển package, rule tồn tại trong database không tìm thấy type.
Ứng dụng đăng ký Converter từ String sang Money; một quy tắc không xét đơn vị tiền tệ khiến phép so sánh số tiền giữa hai currency bị sai.
Đội chuyển kiểu enum bằng ConversionService; giá trị từ đối tác khác chữ hoa và một số giao dịch không được phân loại.
Nhóm đánh giá rule với LocalDate và Instant; TypeConverter dùng timezone của node khiến một giao dịch nằm trong hai kỳ báo cáo ở hai vùng.
Ứng dụng dùng TypeConverter cho chuỗi tỷ lệ từ CSV; giá trị mang dấu phẩy thập phân không được parse như trên màn hình nhập liệu.
Đội dùng SpEL setValue lên amount bằng String từ form; chuyển đổi sang Number làm tròn phần lẻ và báo cáo doanh thu lệch.
Nhóm cấu hình autoGrowNullReferences trong SpelParserConfiguration; expression gán property tự tạo object lồng nhau mà workflow chưa thực sự duyệt.
Ứng dụng bật autoGrowCollections để ghi phần tử theo index; một chỉ mục cực lớn từ request khiến list mở rộng và tiêu tốn heap.
Đội nâng phiên bản parser với giới hạn độ dài expression; rule cũ rất dài không còn parse được trong môi trường production.
Nhóm dùng SpEL gán giá trị cho bean singleton mutable; cùng request đánh giá rule có thể thay đổi cấu hình cho mọi khách.
Ứng dụng đánh giá một expression trên record bất biến rồi thử setValue; runtime không cho ghi property như một JavaBean có setter.
Đội thêm PropertyAccessor ưu tiên cao cho Map; một tên thuộc tính lồng nhau được resolve theo cách khác và rule cũ trả sai.
Nhóm dùng EvaluationContext với ConversionService thay đổi runtime; hai worker cập nhật converter làm cùng expression trả giá trị không ổn định.
Ứng dụng chạy phương thức getValue với kiểu đích Long; biểu thức trả Decimal quá lớn và kết quả không thể chuyển đổi an toàn.
Đội xử lý expression có getter phát sinh lỗi I/O; RuntimeException được đóng gói trong lỗi đánh giá và hệ thống không phân biệt lỗi dữ liệu với lỗi hạ tầng.
Nhóm dùng expression gọi method async trả Future; phần đánh giá mong một kết quả trực tiếp nên so sánh với trạng thái nghiệp vụ bị sai.
Ứng dụng dùng SpEL để quyết định mức chiết khấu nhưng một method helper có side effect; retry đánh giá rule làm cùng tác động xảy ra nhiều lần.
Đội dùng TemplateParserContext để render nội dung email; một chuỗi người dùng chứa delimiter biểu thức bị đánh giá ngoài mong muốn.
Nhóm thay delimiter template SpEL để hợp tác với CMS; một bản template thiếu dấu kết thúc khiến email không được tạo sau khi đơn đã thanh toán.
Ứng dụng render mẫu thông báo có dấu tiếng Việt và ký tự escape; phần parser coi một đoạn văn bản là biểu thức làm nội dung gửi tới khách bị hỏng.
Đội lưu template hóa đơn theo ngôn ngữ; template tiếng Nhật tham chiếu field chỉ tồn tại ở event loại khác nên render thất bại cho một nhóm hóa đơn.
Nhóm tạo subject email từ một expression trả List; nội dung cuối là biểu diễn object thay vì tên người nhận dễ hiểu.
Ứng dụng ghép URL callback bằng SpEL template; thông số chứa dấu hỏi hoặc dấu & làm đường dẫn được dựng không phù hợp.
Đội sử dụng template lấy dữ liệu từ bean runtime; việc bean gọi API ngoài khi render mỗi email làm thời gian gửi tăng mạnh.
Nhóm cho phép biên tập viên sửa mẫu có SpEL; một template gọi method có side effect thay vì chỉ hiển thị trường dữ liệu.
Ứng dụng render cùng template hàng nghìn lần nhưng parse lại từng lượt; chi phí CPU tăng rõ rệt vào giờ gửi email hàng loạt.
Đội cache Expression của template nhưng không xóa cache khi xuất bản mẫu mới; người dùng vẫn nhận nội dung đã bị thu hồi.
Nhóm dùng SpEL thay engine template HTML chuyên dụng; nội dung có dấu ngoặc hoặc escape không còn được diễn giải theo semantics cũ.
Ứng dụng tạo audit log bằng template SpEL; trường actor null làm dòng lịch sử thiếu người thực hiện mà không có cảnh báo.
Đội lấy template từ hệ thống quản trị không tin cậy; một tài khoản biên tập nhập biểu thức tham chiếu bean quản lý dữ liệu nội bộ.
Nhóm dùng biểu thức compiled để xử lý hàng triệu đơn; phần benchmark chỉ đo getValue với DTO nhỏ và bỏ qua conversion ở production.
Ứng dụng bật SpelCompilerMode.IMMEDIATE cho rule giá; một expression dùng feature chưa được compiler hỗ trợ gây lỗi ở giai đoạn biên dịch.
Đội chọn SpelCompilerMode.MIXED cho rule dùng nhiều kiểu DTO; khi runtime type thay đổi, fallback về interpreted làm độ trễ biến động.
Nhóm dùng expression compiled với class cụ thể; một API truyền proxy object không tương thích và việc truy cập property thất bại.
Ứng dụng có method với side effect trong compiled expression; khi rule bị đánh giá lại do lỗi kiểu runtime, tác động nghiệp vụ có thể xảy ra lặp.
Đội dùng compiled expressions trong plugin classloader; một plugin bị unload nhưng tham chiếu tới class cũ vẫn còn làm memory footprint tăng.
Nhóm cho phép mỗi tenant định nghĩa rule compiled riêng; số lượng generated class tăng theo số tenant và gây áp lực bộ nhớ.
Ứng dụng dùng collection selection phức tạp; nhóm vận hành kỳ vọng SpEL compiler tăng tốc toàn bộ nhưng phần này vẫn có thể phải chạy interpreted.
Đội áp SpEL compiled cho dynamic expression thay đổi liên tục; chi phí làm nóng, compile và bỏ cache lớn hơn phần thời gian được tiết kiệm.
Nhóm sử dụng custom PropertyAccessor trong rule có compiler; expression chạy được ở interpreted mode nhưng đường compiled không hỗ trợ cùng khả năng.
Ứng dụng chạy native image với expression tham chiếu helper Java; một type hoặc method cần metadata phản chiếu mà bản native chưa khai báo.
Đội triển khai rule đã compiled trên các node dùng classloader khác nhau; cùng expression chạy thành công ở một node nhưng lỗi hoặc fallback ở node còn lại.
Nhóm cần quan sát lỗi compile và evaluate riêng; metrics hiện gộp mọi exception nên khó biết vấn đề từ parser, compiler hay dữ liệu.
Ứng dụng cho phép khách hàng nhập trực tiếp SpEL qua HTTP để lọc giao dịch; StandardEvaluationContext cho phép method access rộng hơn mục đích truy vấn.
Đội nhận expression từ bên thứ ba và dùng TypeLocator mặc định; rule có khả năng tham chiếu type ngoài tập đối tượng nghiệp vụ cho phép.
Nhóm dùng BeanResolver trên expression của khách hàng; một rule được nhập có thể tham chiếu bean nhạy cảm và vượt quyền dự kiến.
Ứng dụng đánh giá rule người dùng trên entity có method cập nhật số dư; một biểu thức chỉ được phép kiểm tra nhưng lại làm thay đổi trạng thái lưu trữ.
Đội giới hạn chiều dài expression nhưng không hạn chế độ phức tạp; một rule selection lồng sâu chạy lâu và làm cạn CPU của server.
Nhóm cho phép regex matches từ payload đối tác; một pattern có backtracking tệ làm thread HTTP bị giữ lâu bởi đầu vào dài.
Ứng dụng giới hạn chuỗi rule nhưng không giới hạn collection; expression selection trên hàng triệu item vẫn gây quá tải heap và CPU.
Đội đưa cả object SecurityContext vào root cho rule người dùng; một biểu thức có thể đọc token hoặc thuộc tính không nên công khai.
Nhóm tách DTO công khai để đánh giá SpEL an toàn hơn; sau refactor thêm field bí mật vào DTO, phạm vi dữ liệu mà rule đọc được bị mở rộng.
Ứng dụng có hai endpoint đánh giá rule dùng hai loại EvaluationContext; một endpoint hạn chế method access còn endpoint khác vẫn dùng cấu hình rộng.
Đội whitelist method có thể gọi trong SpEL; khi method overload mới xuất hiện, một kiểu tham số đầu vào bất thường chọn nhầm operation.
Nhóm dùng expression từ đối tác trong controller; method helper không có timeout nên một đánh giá làm giữ worker khi nhà cung cấp ngoài gặp lỗi.
Ứng dụng trả chi tiết EvaluationException nguyên bản cho khách; thông báo chứa tên class, field và cấu trúc domain nội bộ.
Đội ghi toàn expression vào log khi lỗi; literal trong rule có mã định danh và dữ liệu khách nên thông tin nhạy cảm đi vào hệ thống quan sát.
Nhóm normalize rule bằng cách xóa khoảng trắng; các chuỗi literal trong SpEL bị thay đổi nên expression cũ cho kết quả khác.
Ứng dụng lưu rule chưa kiểm tra với root type tương ứng; một bản sửa cú pháp khiến toàn bộ người dùng chung tính năng bị lỗi ở runtime.
Đội cache expression theo tên rule nhưng không theo tenant; tenant khác có rule trùng tên sử dụng nhầm biểu thức và áp sai chính sách.
Nhóm triển khai đồng thời hai bản rule ở hai region; cùng đơn hàng nhận kết quả xét duyệt khác nhau tùy replica xử lý.
Ứng dụng chuyển context từ read-write sang read-only tại production; rule cũ được phép setValue không còn chạy và chỉ một luồng cấu hình gặp lỗi.
Đội thiết kế fallback khi SpEL lỗi phân quyền nhưng coi lỗi là true; người dùng không đủ quyền vẫn đi qua bước kiểm tra trong một tình huống dữ liệu thiếu.
Nhóm dùng SpEL để gọi helper kiểm tra hạn mức; helper bị timeout nhưng cách catch lỗi biến kết quả thành cho phép thay vì trạng thái chưa xác định.
Ứng dụng áp expression phân loại khách dựa trên object chưa validate; giá trị âm từ form được convert và vượt qua điều kiện nghiệp vụ theo cách không mong muốn.
Đội chuyển các quy tắc Java cũ sang SpEL; cách so sánh null, decimal và String thay đổi khiến các giao dịch ở ranh giới bị tính phí sai.
Nhóm chạy cùng SpEL expression với dữ liệu từ hai kho; một kho lưu ID dạng Long còn kho kia dùng String và rule cho kết quả không đồng nhất.
Ứng dụng cache kết quả tính giá bằng SpEL nhưng không kèm version profile; sau khi khách đổi hạng thành viên, giá cũ tiếp tục được trả.
Đội dùng StandardEvaluationContext dùng chung với variables; worker của tenant A thay variable khiến request tenant B có thể nhận kết quả sai.
Nhóm viết unit test chỉ kiểm parseExpression thành công; các trường hợp property không có, null và nested collection không được đánh giá thực tế.
Ứng dụng test SpEL với context có TypeLocator và BeanResolver khác production; rule hợp lệ trong test nhưng bị từ chối khi chạy trên server.
Đội kiểm tra template SpEL với dữ liệu ASCII đơn giản; tên khách tiếng Việt, emoji và ký tự escape làm mẫu render bị sai.
Nhóm benchmark SpEL compiled trên object nhỏ; trường hợp production dùng lazy database proxy và conversion phức tạp khiến lợi ích không xuất hiện.
Ứng dụng chạy test với một thread riêng; production dùng EvaluationContext mutable cùng nhiều thread và xuất hiện lỗi lẫn biến tenant.
Đội dùng mock bean cho expression trong unit test; method thực tế gọi API ngoài và có side effect nên lỗi thời gian chờ không được phát hiện.
Nhóm đo thời gian parse mà không đo thời gian evaluate; việc gọi method của bean phía sau mới là nguyên nhân khiến p95 latency cao.
Ứng dụng không log rule version khi đánh giá SpEL tính giá; trong đợt đối soát không xác định được biểu thức nào đã áp lên giao dịch.
Đội cho phép thay rule runtime giữa nhiều replica; một số replica còn expression cached cũ nên quyết định phân quyền khác nhau trên cùng dữ liệu.
Nhóm tạo API xem trước rule dùng payload mock; expression thật được chạy trên entity và EvaluationContext khác nên kết quả xem trước không giống production.
Ứng dụng dùng SpEL làm điều kiện @EventListener; trường event vừa đổi tên khiến listener ngừng chạy im lặng và báo cáo thiếu sự kiện.
Đội phát hiện một rule gây CPU cao nhưng chỉ có metric theo endpoint; không xác định được root type, version expression và thời gian đánh giá từng rule.
Nhóm chạy lại rule khi client timeout nhưng không giữ idempotency; một method bị gọi nhiều lần và làm thay đổi dữ liệu nghiệp vụ.
Ứng dụng dùng SpEL trong điều kiện cache kết quả; một kiểu dữ liệu mới khiến conversion thất bại và API nhận exception sau khi service đã hoàn tất.
Đội triển khai bản Spring Framework mới rồi rollback; bản cũ không hiểu cú pháp expression vừa được lưu vào database và tính năng không khởi động.
Nhóm chạy đánh giá biểu thức từ request không tin cậy mà chưa kiểm giới hạn property, method và bean; trong lần rà soát an ninh không thể chứng minh phạm vi thực thi được hạn chế.
