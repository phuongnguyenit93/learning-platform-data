Một hệ thống thương mại điện tử dùng ApplicationEventPublisher phát OrderPlaced từ module Đơn hàng, nhưng module Thanh toán vẫn gọi trực tiếp repository nội bộ của Đơn hàng để lấy dữ liệu, khiến ranh giới module chưa thực sự được tách.
Nhóm bán hàng phát sự kiện CustomerRegistered chứa toàn bộ entity Customer của JPA, khiến listener ở module Marketing truy cập lazy association sau khi transaction tạo khách đã kết thúc.
Ứng dụng phát ProductPriceChanged chỉ mang mã sản phẩm mà module Báo cáo cần cả giá cũ và giá mới, khiến listener phải truy vấn lại dữ liệu và có thể đọc phiên bản giá khác lúc event xảy ra.
Đội triển khai sự kiện LoanApproved bằng một object mutable rồi sửa trạng thái object trước khi commit, khiến listener đồng bộ đọc dữ liệu khác với snapshot nghiệp vụ dự định công bố.
Một service tạo application event từ controller trước khi kiểm tra quyền cập nhật đơn, khiến module Thông báo phản ứng với yêu cầu chưa được xác thực thành công.
Nhóm quản lý kho publish StockReserved mỗi khi bắt đầu xử lý, nhưng transaction trừ tồn cuối cùng rollback, khiến module Vận chuyển nhận tín hiệu giữ hàng không tồn tại.
Ứng dụng sử dụng tên event ShipmentStatusChanged cho cả lệnh yêu cầu giao hàng và sự kiện giao hàng đã hoàn thành, khiến các module downstream hiểu khác nhau về thời điểm nghiệp vụ.
Đội thay một lời gọi service trực tiếp bằng application event nhưng module Đặt hàng vẫn kỳ vọng có kết quả trả về tức thì để quyết định HTTP response, khiến hợp đồng xử lý không còn phù hợp.
Một service phát CustomerDeleted nhưng payload chỉ có email, khiến module Quản lý dữ liệu không xác định được tenant sở hữu khi hai khách thuộc hai tổ chức có email trùng.
Nhóm dùng ApplicationEventPublisher cho thông tin thanh toán nhạy cảm nhưng listener ghi log cả event, khiến số tài khoản xuất hiện trong nhật ký của module không cần truy cập.
Ứng dụng tạo event với ID đơn hàng sinh từ database trước lúc entity được flush, khiến listener nhận ID chưa có bản ghi tương ứng khi chạy ngoài transaction.
Đội phát một event cho mỗi thay đổi field của hồ sơ khách trong cùng request, khiến module Audit nhận hàng chục sự kiện rời mà không phân biệt chúng thuộc một thao tác sửa.
Một service dùng generic Map làm payload application event để linh hoạt mở rộng, khiến các module consumer không có hợp đồng kiểu rõ ràng và lỗi key chỉ xuất hiện tại runtime.
Nhóm đổi tên một class event được dùng giữa các module trong cùng application nhưng module listener chưa cập nhật kiểu tham số, khiến sự kiện mới không được xử lý sau deploy.
Ứng dụng phát event chứa enum trạng thái có giá trị mới nhưng một listener chỉ xử lý các giá trị đã biết, khiến nhánh báo cáo bỏ qua trạng thái giao hàng mới.
Đội dùng ZonedDateTime từ server hiện tại trong event thay vì thời điểm nghiệp vụ của đơn hàng, khiến báo cáo theo ngày giao dịch đổi khác khi process chuyển vùng giờ.
Một service phát sự kiện PaymentCaptured với giá tiền kiểu double, khiến module Đối soát nhận các sai khác làm tròn nhỏ khi cộng hàng nghìn giao dịch.
Nhóm dùng cùng correlationId cho nhiều đơn được xử lý trong một batch nhưng thiếu eventId riêng, khiến module Audit không phân biệt hai lần phát sự kiện trong cùng yêu cầu.
Ứng dụng cho phép hai module tự phát cùng loại CustomerUpdated event với ý nghĩa khác nhau, khiến listener không biết sự kiện đã được kiểm tra các quy tắc nghiệp vụ nào.
Đội đặt object chứa thông tin credential vào metadata event để một listener gửi email, khiến mọi listener khác cùng kiểu event có thể truy cập thông tin bí mật không cần thiết.
Một service phát AddressValidated sau khi gọi API địa chỉ bên ngoài nhưng callback có thể được gọi nhiều lần, khiến module Thanh toán nhận nhiều sự kiện cùng ý nghĩa cho một lần xác nhận.
Nhóm chuyển sự kiện nghiệp vụ qua ApplicationEventPublisher nhưng vẫn truyền object nội bộ có phương thức thao tác repository, khiến module nhận event có thể vượt ranh giới thay vì chỉ đọc dữ liệu.
Ứng dụng phát một event có tên InvoiceCreated ngay khi bắt đầu tạo file PDF, khiến module Thông báo gửi đường dẫn hóa đơn trước khi file được lưu thành công.
Đội dùng event OrderCanceled để hủy các tác vụ theo dõi nhưng message chỉ chứa trạng thái hiện tại mà không có phiên bản, khiến module Kho không nhận ra lệnh hủy cũ tới muộn.
Một service đăng nhiều listener cho cùng event loại CustomerActivated nhưng không có hợp đồng trách nhiệm rõ, khiến cùng người dùng nhận hai email kích hoạt từ hai module.
Nhóm áp @EventListener đồng bộ để xử lý LoyaltyPointsEarned, nhưng listener gọi mạng bên ngoài chậm khiến transaction thanh toán bị giữ lâu hơn SLA.
Ứng dụng sử dụng @EventListener ở module Audit và ném RuntimeException khi audit storage lỗi, khiến transaction nghiệp vụ gốc rollback dù thay đổi cần được lưu độc lập.
Đội giả định mọi listener @EventListener chạy trên thread khác publisher, khiến quá trình gửi notification chặn request tạo đơn khi số lượng khách tăng.
Một service thêm @Async cho @EventListener xử lý tạo hóa đơn nhưng executor thiếu cấu hình giới hạn, khiến đợt khuyến mãi làm queue tác vụ tăng đến lúc cạn bộ nhớ.
Nhóm triển khai hai @EventListener xử lý cùng event nhưng một listener sửa entity còn listener kia đọc nó, khiến kết quả phụ thuộc thứ tự gọi listener không được cam kết trong hợp đồng.
Ứng dụng dùng @Order để sắp xếp listener đồng bộ nhưng chuyển một listener sang bất đồng bộ, khiến đội phát triển vẫn kỳ vọng xử lý hoàn tất tuần tự như trước.
Đội publish sự kiện trong một vòng lặp nhập hàng bằng ApplicationEventPublisher nhưng một listener đồng bộ ném lỗi ở phần tử giữa, khiến những đơn đã phát trước đó và đơn còn lại có trạng thái khác nhau.
Một service xử lý event bằng @EventListener và cập nhật database nhưng method này được gọi từ một giao dịch ngoài, khiến trách nhiệm rollback của publisher và listener bị ghép chặt.
Nhóm dùng ApplicationEventPublisher phát OrderSubmitted từ một batch không có transaction nhưng một listener @TransactionalEventListener mặc định không chạy, khiến module Báo cáo thiếu số đơn batch.
Ứng dụng chuyển endpoint MVC sang scheduler tạo cùng loại event nhưng không có transaction active, khiến behavior của listener sau commit khác với đường gọi HTTP được kiểm thử.
Đội cấu hình @TransactionalEventListener với fallbackExecution cho một luồng không có transaction, khiến sự kiện ở nguồn batch được xử lý ngay còn nguồn HTTP phải đợi commit.
Một service sử dụng @TransactionalEventListener(phase = AFTER_COMMIT) để gửi hóa đơn nhưng publisher phát event trước khi transaction mở, khiến listener không có giao dịch để gắn vào.
Nhóm đặt transaction propagation REQUIRES_NEW cho một bước tạo đơn phụ và publish event trong đó, khiến listener thấy commit của bước phụ dù transaction nghiệp vụ cha về sau thất bại.
Ứng dụng publish CustomerVerified trong một transaction bị đánh dấu rollback-only, khiến đội hỗ trợ kỳ vọng listener chạy nhưng publication không đạt pha AFTER_COMMIT.
Đội chọn phase BEFORE_COMMIT cho một listener kiểm tra hạn mức nhưng listener cần truy cập API ngoài, khiến transaction giữ tài nguyên trong suốt thời gian chờ đối tác.
Một service đặt listener gửi SMS ở phase AFTER_ROLLBACK để báo giao dịch không thành công, nhưng event chỉ được phát trên một số nhánh thất bại, khiến khách nhận thông báo không nhất quán.
Nhóm sử dụng AFTER_COMPLETION cho audit trạng thái cuối nhưng không có dấu hiệu transaction đã commit hay rollback trong event, khiến bản ghi audit khó phân loại.
Ứng dụng có listener AFTER_COMMIT gọi repository để sửa trạng thái đã gửi email nhưng không tạo ranh giới transaction mới phù hợp, khiến thay đổi không được lưu như đội vận hành kỳ vọng.
Đội chuyển một @EventListener sang @TransactionalEventListener nhưng test chỉ publish event ngoài transaction, khiến bài test không còn kích hoạt listener theo cùng thời điểm trước.
Một service tạo @ApplicationModuleListener cho module Khuyến mãi, nhưng một test giả định nó cập nhật điểm thưởng trước khi publisher trả về, khiến kết quả unit test phụ thuộc việc executor đã xử lý kịp hay chưa.
Nhóm dùng @ApplicationModuleListener gửi event tới module Hóa đơn, nhưng bước tạo PDF ném exception sau commit và người dùng vẫn nhận kết quả tạo đơn thành công dù hóa đơn chưa sẵn sàng.
Ứng dụng đặt hai @ApplicationModuleListener cùng xử lý event rồi cùng cập nhật một cột trạng thái, khiến thứ tự hoàn tất bất đồng bộ làm trạng thái cuối không ổn định.
Đội cấu hình thread pool xử lý @ApplicationModuleListener quá nhỏ cho lượng event mỗi phút, khiến thời gian xử lý notification tăng mạnh mặc dù API vẫn trả lời nhanh.
Một service dùng @ApplicationModuleListener với thao tác blocking truy cập HTTP nhưng khi kết nối đối tác treo, các publication khác bị dồn vào hàng chờ executor.
Nhóm chuyển listener sang @ApplicationModuleListener để cách ly transaction nhưng method đọc các thuộc tính lazy của entity truyền trong event, khiến thao tác chỉ lỗi sau khi transaction publisher đóng.
Ứng dụng gắn @ApplicationModuleListener lên method ở bean không được Spring quản lý trong một công cụ import, khiến sự kiện từ luồng đó không có listener active.
Đội có listener @ApplicationModuleListener được đóng gói trong một module profile riêng, khiến profile production không tạo bean và event không được giao cho tính năng mới.
Một service tạo listener có @TransactionalEventListener cùng @Async tùy biến nhưng không có cơ chế hoàn tất phù hợp, khiến trạng thái publication trong registry không phản ánh lần xử lý thực tế.
Nhóm dùng @ApplicationModuleListener thực thi gọi thanh toán bên ngoài rồi cập nhật DB, khiến side effect tại đối tác vẫn xảy ra khi transaction cập nhật DB của listener rollback.
Ứng dụng phát PaymentReviewed trong phương thức @Transactional(readOnly=true) nhưng Event Publication Registry vẫn cần ghi nhận publication, khiến database production cưỡng chế quyền chỉ đọc từ chối thao tác mà bộ test trước đó chấp nhận.
Đội tạo listener chạy sau commit nhưng dùng thông tin bảo mật lấy từ ThreadLocal của request gốc, khiến xử lý trên thread async thiếu danh tính caller.
Một service chuyển tenantId qua ThreadLocal trong publisher nhưng không mang tenant vào event, khiến @ApplicationModuleListener chạy ở executor khác và chọn sai datasource.
Nhóm lưu traceId trong MDC khi publish sự kiện nhưng listener bất đồng bộ không kế thừa MDC, khiến logs về cùng OrderPlaced bị chia thành nhiều trace rời.
Ứng dụng dùng RequestContextHolder trong listener chạy sau commit để lấy locale khách, khiến email được gửi bằng ngôn ngữ mặc định khi không còn HTTP request context.
Đội nhận một lỗi phát sinh trong @ApplicationModuleListener và kỳ vọng exception quay lại controller, khiến API báo thành công còn module downstream cần xử lý sự cố độc lập.
Một service tự gọi method listener từ nội bộ bean thay vì đợi event, khiến đường gọi này bỏ qua một số hành vi proxy/transaction mà flow sự kiện thông thường có.
Nhóm đăng ký ApplicationEventMulticaster với executor riêng và gắn thêm @Async ở listener, khiến số lần chuyển luồng và cách quan sát lỗi khác giả định của đội vận hành.
Ứng dụng chuyển từ synchronous event multicast sang async cho toàn hệ thống, khiến các listener kiểm tra dữ liệu vốn phải hoàn tất trước response hoạt động muộn hơn thiết kế.
Đội bật async cho mọi listener nhưng một listener cần chạy trước commit để bảo vệ invariant tồn kho, khiến kiểm tra bắt buộc bị tách khỏi transaction gốc.
Một service phát EventA từ trong @ApplicationModuleListener của EventB, khiến các module downstream khó theo dõi chuỗi nghiệp vụ khi retry EventB sinh EventA lần nữa.
Nhóm publish event liên tiếp Created và Confirmed trong cùng transaction nhưng hai listener async xử lý khác tốc độ, khiến mô hình báo cáo quan sát Confirmed trước Created.
Ứng dụng cập nhật điểm thưởng bằng listener sau commit, nhưng khách đọc điểm ngay sau HTTP 200 và không thấy phần thưởng mới, khiến hợp đồng eventual consistency chưa được truyền đạt.
Đội dùng event sau commit để gửi email cho khách nhưng hệ thống thông báo bắt buộc gửi trong vòng hai giây, khiến executor backlog làm vi phạm SLA dù transaction hoàn tất.
Một service sử dụng Event Publication Registry để ghi nhận việc giao OrderPlaced tới các listener, nhưng bảng publication chưa có đúng schema ở production khiến bản ghi nghiệp vụ được lưu mà lịch sử giao sự kiện không đầy đủ.
Nhóm bật event publication persistence cho Spring Modulith nhưng datasource của module không có quyền INSERT vào bảng registry, khiến ghi publication thất bại trong đường tạo đơn.
Ứng dụng di chuyển database và dùng Event Publication Registry nhưng chỉ migrate bảng nghiệp vụ, khiến các publication chưa hoàn tất ở database cũ không xuất hiện sau cutover.
Đội phát OrderPlaced tới ba transactional listeners nhưng bảng registry chỉ được kiểm thử với một listener, khiến trường hợp một listener thành công và hai listener thất bại không được giám sát.
Một service có nhiều event loại PaymentAuthorized và registry lưu publication theo từng listener, nhưng dashboard chỉ đếm số event gốc, khiến đội trực không nhận ra còn một listener đang chờ.
Nhóm dùng EventPublicationRegistry để theo dõi các publication incomplete nhưng không phân biệt lỗi serialization và lỗi listener, khiến runbook retry không phù hợp loại sự cố.
Ứng dụng triển khai listener mới cho một sự kiện đã có từ trước nhưng đội vận hành kỳ vọng registry sẽ tự retroactively tạo publication cho tất cả event lịch sử, khiến dữ liệu báo cáo thiếu.
Đội thay tên class của event dùng trong publication lưu bền khi nâng phiên bản, khiến các bản ghi còn chưa hoàn tất từ bản cũ không được deserialize đúng để phát lại.
Một service lưu event payload trong registry dưới dạng có cấu trúc phức tạp, nhưng object chứa kiểu Java từ thư viện sắp gỡ bỏ, khiến replay sau nâng version gặp lỗi type mapping.
Nhóm chuyển từ cơ chế serialization mặc định sang custom serializer trong registry mà không migrate dữ liệu đã lưu, khiến publication cũ còn tồn không đọc được ở bản mới.
Ứng dụng giữ event chứa nhiều dữ liệu nhạy cảm trong bảng publication, khiến retention của registry không đáp ứng thời hạn lưu dữ liệu cá nhân sau khi khách yêu cầu xóa.
Đội sử dụng cùng database cho bảng nghiệp vụ và registry nhưng transaction manager của publisher không bao phủ cả hai, khiến commit dữ liệu và ghi publication có thể lệch nhau.
Một service kích hoạt registry cho luồng import batch không mở transaction, khiến một số event không được ghi lại theo cách giống luồng HTTP có transaction.
Nhóm lưu event publication theo một transaction tạo đơn đã commit nhưng listener bắt exception rồi im lặng trả về, khiến registry đánh dấu hoàn tất dù tác vụ gửi hóa đơn thất bại.
Ứng dụng triển khai @ApplicationModuleListener gửi email rồi mất kết nối database trước khi registry ghi nhận completion, khiến thư được gửi nhưng publication còn ở trạng thái chưa hoàn tất.
Đội dùng listener gọi API thanh toán và nhận timeout sau khi đối tác đã thực hiện lệnh, khiến publication incomplete có nguy cơ phát lại thao tác ghi tiền lần nữa.
Một service hoàn tất publication ở registry nhưng thao tác lưu bản ghi phụ chỉ được enqueue trong memory, khiến pod restart làm mất công việc dù registry coi listener đã xử lý xong.
Nhóm đặt cấu hình timeout cho một listener nhưng publication vẫn incomplete sau nhiều giờ và dashboard chỉ hiển thị số đã hoàn tất, khiến thông báo lỗi không được phát hiện.
Ứng dụng lưu publication theo event ID không ổn định giữa các lần gửi, khiến một event nghiệp vụ bị phát nhiều lần nhưng công cụ điều tra không đối chiếu được các bản liên quan.
Đội có registry với hàng triệu bản publication đã hoàn tất và bảng tăng nhanh, khiến truy vấn incomplete bị chậm rõ rệt trong giờ cao điểm.
Một service lập lịch xóa lịch sử publication quá sớm, khiến kiểm toán không còn bằng chứng đã giao sự kiện đến các module nhận vào thời điểm cần đối soát.
Nhóm dùng registry với bộ nhớ đệm SQL chưa được đánh chỉ mục phù hợp, khiến khi backlog tăng việc lấy các publication incomplete làm database bị quá tải.
Ứng dụng triển khai registry trong môi trường multi-tenant nhưng bảng publication không có thông tin tenant cần thiết cho việc phân quyền truy vấn, khiến dashboard hỗ trợ có thể xem metadata của khách khác.
Đội đặt registry cùng database có replication lag rồi đọc incomplete từ read replica, khiến việc xác định publication nào đang chờ khác với trạng thái mới commit tại primary.
Một service cần hoàn tất hai listeners độc lập nhưng một listener bị xóa khỏi module sau deploy, khiến publication đã lưu cho listener cũ còn incomplete không có handler tương ứng.
Nhóm đổi tên bean listener trong bản nâng cấp nhưng publication incomplete lưu định danh listener trước đó, khiến việc khôi phục không tìm được target như kỳ vọng.
Ứng dụng chạy hai versions cùng kết nối bảng registry trong rolling deployment, khiến phiên bản cũ và mới hiểu event payload khác nhau khi phát lại cùng một publication.
Đội cấu hình event publication persistence cho database H2 trong test nhưng production dùng PostgreSQL với transaction isolation khác, khiến hành vi khi listener failover chưa được đánh giá.
Một service dùng JDBC event publication repository nhưng database production thỉnh thoảng bị deadlock lúc ghi trạng thái hoàn tất, khiến nhiều publication vẫn incomplete dù side effect xong.
Nhóm đổi từ JDBC sang JPA event publication persistence nhưng chưa chuyển bảng và mapping tương ứng, khiến các publication đang chờ không theo được sang backend mới.
Ứng dụng muốn bật Event Publication Registry chỉ cho một số module nhưng đồng thời có listeners không transactional, khiến nhóm khó xác định những sự kiện nào thực sự có dấu vết giao bền.
Đội vận hành nhận thấy bảng incomplete vẫn chứa các event đã được listener xử lý, nhưng logging không có eventId và publication target để phân biệt completion update lỗi với retry thật.
Một service nạp lại unfinished publications sau restart nhưng một event có class version cũ bị parse lỗi, khiến quá trình khôi phục của các event khác cần được đánh giá khi gặp poison publication.
Nhóm thiết kế rollback deployment nhưng bản trước không hiểu payload event mới lưu trong registry, khiến các publication chờ trở thành rủi ro khi khôi phục ứng dụng.
Ứng dụng ghi cùng event business vào nhiều registry entries cho các listeners khác nhau, khiến việc xóa một record theo event ID vô tình bỏ cả trạng thái target khác chưa hoàn tất.
Đội cần tuân thủ quy định xóa dữ liệu sau 30 ngày nhưng publication registry lưu object gốc chứa tên và địa chỉ, khiến backup giữ dữ liệu lâu hơn retention của hệ thống chính.
Một service dùng CustomEventSerializer cho publication nhưng không version hóa định dạng payload, khiến một thay đổi tên field phá khả năng phục hồi sau rollback.
Nhóm sử dụng EventPublicationRegistry để kiểm tra trạng thái giao event nhưng hỗ trợ chỉ xem được bảng thô, khiến khó xác định từng publication đã được xử lý bởi module nào.
Ứng dụng cần tái phát publication incomplete cho listener gửi hóa đơn nhưng hai pod cùng chạy recovery, khiến cùng email có thể được gửi từ hai instance nếu xử lý trùng không được kiểm soát.
Đội xây công cụ re-submit các publication chưa hoàn tất nhưng operator chạy lệnh hai lần khi giao diện không trả kết quả, khiến một loạt events được xử lý lặp.
Một service gọi quy trình resubmit trong lúc publisher đang tiếp tục ghi publication mới, khiến dashboard thấy số incomplete tăng dù tiến độ phục hồi thực tế vẫn tốt.
Nhóm dự kiến tự động retry mọi publication incomplete nhưng một event có dữ liệu thiếu vĩnh viễn, khiến nó lặp lại nhiều lần mà không tạo tiến triển.
Ứng dụng dùng retry cho listener sau commit khi API đối tác trả HTTP 429, khiến hàng nghìn publication được gửi lại cùng lúc và đối tác tiếp tục hạn chế lưu lượng.
Đội cấu hình retry không có giới hạn theo thời gian cho module Thông báo, khiến một event tạo email đã quá hạn kinh doanh vẫn được gửi sau nhiều ngày.
Một service phát lại OrderShipped sau sự cố nhưng trạng thái đơn hiện tại đã Delivered, khiến listener dùng event cũ có thể ghi lùi trạng thái shipment.
Nhóm retry publication cho một quy trình gửi SMS khi không có idempotency key ở nhà cung cấp, khiến khách nhận nhiều tin nhắn khi lần đầu đã gửi nhưng completion update lỗi.
Ứng dụng retry event cập nhật điểm thưởng bằng cách cộng điểm vào tổng hiện tại, khiến một publication được giao hai lần làm khách được cộng điểm gấp đôi.
Đội publish InvoiceIssued vào module Ledger và thực hiện insert với eventId làm khóa duy nhất, nhưng module gửi thông báo lại chỉ dựa vào invoiceId không đủ phân biệt các lần phát hành lại.
Một service tự động re-submit incomplete publications mỗi phút nhưng thời gian xử lý một job dài hơn chu kỳ, khiến cùng bản ghi có thể được hai lượt phục hồi xử lý đồng thời.
Nhóm gọi recovery trên mỗi instance lúc startup nhưng không có thống kê instance nào đã nhận publication, khiến log cho thấy hai lần thực thi mà không xác định nguồn.
Ứng dụng yêu cầu phát lại chỉ với events sau ngày bắt đầu sự cố nhưng giao diện hỗ trợ lọc theo thời điểm tạo event thay vì thời điểm publication thất bại, khiến phạm vi retry khác mong muốn.
Đội vận hành phát lại toàn bộ sự kiện khi database phục hồi nhưng hệ thống ngoài áp hạn mức 100 requests/phút, khiến tốc độ recovery làm hệ thống đối tác quá tải.
Một service dùng backoff retry tăng dần nhưng trong lúc chờ người dùng hủy đơn, khiến publication cũ được phát lại và tạo phiếu giao hàng cho đơn đã hủy.
Nhóm muốn bỏ qua publication không còn liên quan nhưng không ghi lý do hoặc quyết định vận hành, khiến audit sau sự cố không thể phân biệt bỏ có chủ ý với mất dữ liệu.
Ứng dụng gặp lỗi deserialize publication cũ rồi tự động đánh dấu hoàn tất để dọn backlog, khiến dữ liệu cần giao bị coi là đã xử lý mà listener chưa từng chạy.
Đội dùng dead-letter workflow cho publication không thể phục hồi nhưng không lưu original event type và error history, khiến nhóm hỗ trợ không có đủ bối cảnh để điều tra.
Một service đã xử lý event thành công nhưng registry vẫn incomplete do lỗi commit completion, khiến lệnh retry phục hồi cần đối mặt tình huống side effect đã xảy ra trước.
Nhóm gửi publication theo thứ tự tạo ở registry nhưng một event có thời gian xử lý dài, khiến một sự kiện nghiệp vụ mới bị chặn khi cố phục hồi toàn bộ theo hàng chờ tuần tự.
Ứng dụng dùng retry ở hai cấp gồm listener và công cụ replay vận hành, khiến tổng số lần gọi dịch vụ ngoài vượt chính sách kiểm soát khi cùng một sự cố xảy ra.
Đội xây listener tính doanh thu từ OrderPaid nhưng khi replay các event lịch sử, tỷ giá hiện tại được dùng để tính lại số tiền, khiến báo cáo sau phục hồi lệch khỏi sổ lúc giao dịch.
Một service retry sau lỗi kết nối email nhưng template email đã thay đổi theo phiên bản mới, khiến khách nhận nội dung không khớp thời điểm OrderCreated ban đầu.
Nhóm có listener ghi nhận tất toán khoản vay nhưng event bị lặp trong lúc failover, khiến module Ledger tạo nhiều bút toán nếu không phân biệt event đã được áp dụng.
Ứng dụng sử dụng idempotency key theo requestId HTTP nhưng một đơn được xử lý từ batch không có requestId, khiến quá trình replay có thể tạo nhiều bản ghi trùng.
Đội dùng event publication registry cho những lệnh có ảnh hưởng tiền nhưng hợp đồng event thiếu định danh giao dịch bất biến, khiến không thể chứng minh hai lần delivery là một giao dịch.
Một service cần phân loại retryable và non-retryable exceptions nhưng listener ném RuntimeException chung cho mọi lỗi, khiến recovery lặp với event có quy tắc nghiệp vụ sai.
Nhóm cấu hình retry khi publication đã hoàn tất một phần ở ba listeners, nhưng thao tác quản trị phát lại event gốc cho tất cả listeners, khiến những listener đã thành công có nguy cơ thực hiện side effect thêm lần.
Ứng dụng nhận payment event từ module Đặt hàng rồi chuyển tiếp sang external broker, nhưng external broker đã lưu message trước khi completion registry thất bại, khiến retry có thể publish hai bản cùng event.
Đội đồng bộ CustomerChanged sang hệ thống CRM nhưng CRM có cập nhật mới hơn, khiến việc phát lại event cũ sau downtime ghi đè thông tin mới.
Một service có publication incomplete từ module Vận chuyển nhưng chính sách retention xóa event object khỏi database trước khi retry, khiến listener mất dữ liệu bổ sung cần cho side effect.
Nhóm muốn gửi báo cáo sau commit nhưng thời gian replay nhiều ngày khiến báo cáo được tính theo cấu hình sản phẩm mới, không khớp ý nghĩa của event đã phát khi giao dịch xảy ra.
Ứng dụng mở rộng Spring Modulith thành ba pods cùng chạy listener sau commit, khiến nhóm vận hành cần đánh giá những publication được khôi phục khi một pod chết giữa xử lý.
Đội gán publisher và listener vào hai module có chung entity repository nhưng dùng application events chỉ làm lớp chuyển tiếp, khiến module nhận vẫn phụ thuộc bảng nội bộ của module phát.
Một service đưa interface nội bộ của module Hóa đơn vào payload OrderCompleted, khiến thay đổi nội bộ module Hóa đơn kéo theo rebuild nhiều listener không liên quan.
Nhóm giữ event contract trong package implementation không được expose của module Nghiệp vụ, khiến việc module khác subscribe phá quy tắc dependency khi chạy verify architecture.
Ứng dụng dùng application event để giảm phụ thuộc nhưng một listener gọi ngược public API publisher ngay khi nhận event, khiến hai module tạo vòng phụ thuộc vận hành khi hệ thống tăng tải.
Đội phát CustomerUpdated với toàn bộ profile và cho mọi module nhận, khiến một thay đổi field nhỏ tạo hợp đồng rộng và tăng số module cần chỉnh khi version dữ liệu thay đổi.
Một service phát domain event sau khi entity thay đổi nhưng tên event chỉ phản ánh công nghệ lưu trữ thay vì kết quả nghiệp vụ, khiến module khác khó xác định có nên phản ứng.
Nhóm dùng event ProcessStarted cho cả luồng nhập kho và xuất kho mà không có business intent trong payload, khiến listener phải suy luận loại nghiệp vụ từ các field tùy chọn.
Ứng dụng thêm một module FraudDetection nghe OrderPlaced nhưng nó cần quyền truy cập sang bảng nội bộ Payment, khiến ranh giới module không được bảo vệ chỉ bằng cơ chế event.
Đội mong listeners sử dụng public event types nhưng một class event được khai báo package-private, khiến module bên ngoài không thể tham chiếu hợp đồng theo cách thiết kế.
Một service chuyển logic cập nhật loyalty points sang listener event nhưng dùng một singleton cache mutable do hai module cùng ghi, khiến module vẫn bị ghép chặt qua shared state.
Nhóm mở thêm module Analytics và subscribe cùng event CustomerDeleted, nhưng listener Analytics không có thông tin phân vùng tenant, khiến dữ liệu cũ của khách vẫn tồn tại trong hệ thống báo cáo.
Ứng dụng muốn thay thế một module bằng dịch vụ ngoài sau này nhưng event payload chứa class Java-specific và object graph JPA, khiến hợp đồng khó chuyển sang broker giữa tiến trình.
Đội dùng application events trong cùng JVM và kỳ vọng các service chạy ở pod khác tự nhận được, khiến module Báo cáo thuộc một ứng dụng triển khai riêng không thấy event.
Một service tách module Email thành process khác nhưng vẫn dựa vào ApplicationEventPublisher nội bộ, khiến yêu cầu gửi thông báo không thể vượt ranh giới JVM.
Nhóm tích hợp external event publishing để gửi dữ liệu sang Kafka nhưng một listener nội bộ cũng ghi cùng bảng của downstream, khiến cùng event bị áp dụng theo hai đường khác nhau.
Ứng dụng đánh dấu event để externalize nhưng thông tin nhận diện schema và subject trên broker không thống nhất với consumer hiện tại, khiến luồng ra ngoài lỗi dù listeners trong JVM chạy tốt.
Đội phát sự kiện PaymentSettled với chi tiết nội bộ không cần cho đối tác, khiến khi externalize qua AMQP một phần thông tin nhạy cảm bị gửi vượt ranh giới hệ thống.
Một service dùng event nội bộ và event external cùng tên nhưng thời điểm công bố khác nhau, khiến báo cáo từ broker cho rằng đơn đã hoàn tất trong khi module trong JVM vẫn đang xử lý.
Nhóm triển khai outbox nội bộ qua event publication rồi nghĩ external broker đảm bảo exactly-once, khiến khi lỗi network broker có thể nhận message trùng và consumer chưa có cơ chế idempotent.
Ứng dụng chuyển từ sự kiện theo entity sang immutable business event record, nhưng một module cũ vẫn cần trường không còn được công bố, khiến luồng chuyển đổi tạo dependency ngược.
Đội dùng event version để tránh phá vỡ listeners nhưng một lần rollback ứng dụng còn publication chứa version mới, khiến listener từ bản cũ không hiểu event.
Một service có hai event versions ProductCreated và ProductCreatedV2 cùng được publish trong giai đoạn chuyển tiếp, khiến module Analytics nhận cả hai và đếm trùng sản phẩm.
Nhóm quản lý hợp đồng event giữa module bằng một thư viện dùng chung nhưng mọi thay đổi nhỏ buộc deploy đồng loạt các module trong cùng ứng dụng, khiến mục tiêu độc lập bị hạn chế.
Ứng dụng tạo sự kiện cross-module ngay trong domain entity bằng tham chiếu tới ApplicationEventPublisher, khiến unit tests của domain logic cần khởi tạo thêm Spring context.
Đội thiết kế mọi phản hồi nghiệp vụ đều qua event mà không phân biệt command/query, khiến module Giao hàng không biết khi nào có thể xác nhận tác vụ bắt buộc đã hoàn tất.
Một service gọi nhiều listener độc lập cho cùng event và giả định chúng dùng một database transaction chung, khiến khi một listener lỗi các module có trạng thái cập nhật từng phần.
Nhóm publish OrderPaid rồi có listener tạo shipment và listener ghi audit chạy song song, khiến shipment sẵn sàng trong khi audit publication còn incomplete mà dashboard chỉ hiện một trạng thái chung.
Ứng dụng ghi tổng tồn kho vào module Báo cáo sau commit nhưng listener nhận event cũ sau event mới, khiến bảng tổng hợp hiển thị số lượng lùi về quá khứ.
Đội publish CustomerMerged từ hai transaction liên tiếp trên cùng khách, nhưng async listener xử lý lần thứ hai trước lần đầu, khiến module CRM giữ quan hệ khách không đúng phiên bản.
Một service thực thi listener sau commit bằng transaction mới nhưng đồng thời nhận hai event cập nhật cùng tài khoản, khiến optimistic locking conflict và một publication bị treo chưa hoàn tất.
Nhóm dùng một executor cho @ApplicationModuleListener của Email và FraudDetection, khiến email chậm làm trễ quyết định cảnh báo gian lận quan trọng.
Ứng dụng chia sẻ một event listener singleton giữ biến đếm tiến độ của khách hiện tại, khiến nhiều event chạy đồng thời làm kết quả của tenant A ảnh hưởng tenant B.
Đội gọi dịch vụ ngoài từ listener sau commit rồi trả exception nếu request timeout, khiến event publication incomplete nhưng không rõ đối tác đã thực hiện side effect hay chưa.
Một service phát cùng một event twice trong một transaction do hai handler đều gọi publisher, khiến registry có thể ghi hai publications cho cùng kết quả nghiệp vụ và listener chạy hai lần.
Nhóm cần thứ tự A rồi B giữa hai loại sự kiện cùng aggregate nhưng publish sau commit ở hai transaction khác nhau, khiến tốc độ scheduler quyết định thứ tự giao thực tế.
Ứng dụng mở thêm parallelism cho listeners để tăng throughput nhưng một event cập nhật bảng tổng hợp mang dữ liệu tính toán từ state cũ, khiến batch kết quả ghi đè lẫn nhau.
Đội có một listener sau commit cần đọc bản ghi vừa cập nhật nhưng truy vấn chạy trên read replica còn lag, khiến listener báo NOT_FOUND dù transaction publisher đã commit.
Một service dùng optimistic version trên aggregate nhưng event không mang version, khiến listener không xác định được event nào mới hơn khi replay sau gián đoạn.
Nhóm xử lý sự kiện OrderCanceled rồi OrderShipped trên hai luồng async nhưng module Vận chuyển không có quy tắc nhận dạng trạng thái hợp lệ, khiến yêu cầu hủy có thể bị ghi đè.
Ứng dụng có listener hoàn tất một phần công việc rồi ném lỗi, khiến khi registry phát lại cùng event những bước đã thực hiện trước đó cũng chạy lại.
Đội dùng một sự kiện PaymentRefunded để đồng bộ nhiều aggregate nhưng listener chỉ lock một aggregate, khiến retry đồng thời tạo các bản ghi phụ không nhất quán.
Một service tính điểm loyalty trong listener sau commit dựa vào cấu hình khuyến mãi hiện thời, khiến event cũ được replay sau chương trình kết thúc tạo số điểm sai.
Nhóm thử giữ event delivery order bằng cách dùng executor một thread nhưng một listener xử lý lâu khiến các publication quan trọng khác xếp hàng và trễ SLA.
Ứng dụng có một transaction listener tạo event mới và ghi dữ liệu trong REQUIRES_NEW, khiến event thứ hai có thể đến consumer trước event từ transaction cha được ghi nhận đầy đủ.
Đội coi async event listener là hàng đợi bền và xóa toàn bộ trạng thái chuyển tiếp khỏi database, khiến trong sự cố đột ngột yêu cầu không thể tự suy ra trạng thái chưa hoàn thành.
Một service đưa logic kiểm tra quyền vào listener chạy sau commit, khiến thao tác nghiệp vụ đã lưu thành công trước khi listener phát hiện người gọi không có quyền.
Nhóm publish sự kiện OrderPlaced trong transaction nhưng một listener @EventListener đồng bộ gửi email trước commit và một listener sau commit xử lý báo cáo, khiến email có thể tới dù transaction rollback.
Ứng dụng dùng @TransactionalEventListener(AFTER_ROLLBACK) để gửi cảnh báo khi nhập hàng thất bại, nhưng listener phụ thuộc dữ liệu đã bị rollback và không còn đọc được.
Đội chạy startup job publish event để dựng cache nhưng listener @TransactionalEventListener không có transaction ở startup, khiến cache chưa sẵn sàng mà health vẫn báo SERVING.
Một service đăng listener mới cho BillingCycleClosed nhưng module billing đã publish event trước khi ApplicationContext hoàn tất đăng ký handler, khiến các event startup bị bỏ lỡ.
Nhóm đổi transaction manager cho module Đơn hàng sang một datasource mới nhưng registry event publication vẫn sử dụng datasource cũ, khiến transaction gốc và publication không còn atomic theo giả định.
Ứng dụng kiểm tra listener bằng cách gọi trực tiếp method Java thay vì publish event qua Spring, khiến test bỏ qua pha AFTER_COMMIT và registry completion.
Đội viết unit test ApplicationEventPublisher chỉ xác minh publishEvent đã được gọi, khiến các listener module nhận không được chạy và sự cố thiếu bean không bị phát hiện.
Một service dùng @ApplicationModuleTest cho module Đơn hàng nhưng không bật các module lắng nghe bên ngoài, khiến bài test không chứng minh được side effect của giao tiếp qua event.
Nhóm bật @ApplicationModuleTest với mock event publisher nhưng mong đo các publication incomplete trong registry, khiến bộ test không ghi nhận vòng đời event thực.
Ứng dụng kiểm thử event sau commit mà không mở transaction, khiến listener @TransactionalEventListener không được kích hoạt và test cho kết quả sai về luồng production.
Đội dùng @Transactional trên phương thức test rồi không commit, khiến listener AFTER_COMMIT không chạy trong suite dù đường HTTP production commit và xử lý bình thường.
Một service thử @ApplicationModuleListener bằng cách assert database ngay sau publishEvent, khiến test lúc đậu lúc rớt theo tốc độ executor xử lý bất đồng bộ.
Nhóm kiểm thử event bus trong cùng thread nhưng production dùng @Async, khiến lỗi mất TenantContext và MDC ở listener chỉ xuất hiện sau deploy.
Ứng dụng dùng Testcontainers PostgreSQL cho Event Publication Registry nhưng không mô phỏng registry schema migration với dữ liệu incomplete từ phiên bản trước.
Đội chạy integration test với H2 rồi kết luận Event Publication Registry an toàn khi failover, khiến vấn đề isolation và transaction khác PostgreSQL chưa được kiểm chứng.
Một service test listener gửi email bằng mock luôn trả thành công, khiến tình huống email đã gửi nhưng registry completion update thất bại không được mô phỏng.
Nhóm kiểm tra retry bằng exception phát ra trước mọi side effect, khiến tình huống timeout sau khi đối tác đã xử lý và nguy cơ gửi trùng chưa được chứng minh.
Ứng dụng test registry chỉ với một publication incomplete nhưng production có hàng triệu entries, khiến truy vấn recovery và cleanup chậm bất thường chưa được đánh giá.
Đội thử re-submit một event bằng một instance duy nhất nhưng production có nhiều pods cùng nhận lệnh phục hồi, khiến xử lý publication trùng chưa xuất hiện trong suite.
Một service kiểm thử sự kiện hợp lệ mới nhất nhưng không deserialize event từ bản release cũ đã lưu trong registry, khiến rollback gặp lỗi phục hồi.
Nhóm viết contract test cho event DTO nhưng chỉ kiểm tra Java field names mà không xét dữ liệu có thể thiếu hoặc chứa enum mới, khiến một module consumer cũ bị lỗi khi nâng version.
Ứng dụng chạy test OrderPlaced với một listener duy nhất nhưng production có listener Email, Analytics và Loyalty, khiến trường hợp chỉ một listener thất bại không được quan sát.
Đội test @TransactionalEventListener bằng event phát trong transaction thành công nhưng không có testcase rollback, khiến một listener chạy sai pha không bị phát hiện.
Một service thử listener AFTER_ROLLBACK với exception nhưng không kiểm tra dữ liệu giao dịch bị xóa, khiến test cho phép listener dựa vào một bản ghi không tồn tại.
Nhóm đưa eventId ngẫu nhiên vào mọi testcase nhưng không thử publish cùng ID hai lần, khiến tính idempotent của listener chưa được xác minh trong CI.
Ứng dụng test sự kiện có version tăng tuần tự nhưng không cố tình đảo thứ tự delivery, khiến bảng báo cáo có thể bị ghi lùi khi recovery thực tế.
Đội kiểm thử sự kiện PaymentCaptured bằng mock entity có đủ lazy associations, khiến listener ngoài transaction production gặp lỗi truy cập JPA association không được mô phỏng.
Một service kiểm tra trace logging trong HTTP request mà không gọi listener async, khiến correlationId biến mất qua @ApplicationModuleListener chưa được phát hiện.
Nhóm chạy module tests với một tenant duy nhất nhưng production chia sẻ registry cho nhiều tenant, khiến nguy cơ dùng nhầm tenant context khi retry chưa được kiểm chứng.
Ứng dụng test khôi phục publication bằng việc gọi lại listener trực tiếp, khiến trạng thái registry incomplete/completed thực tế không được chuyển như công cụ vận hành kỳ vọng.
Đội kiểm tra thông báo email khi event xử lý thành công nhưng không assert publication completed trong registry, khiến lỗi commit completion đi vào production mà test vẫn xanh.
Một service tạo testcase dữ liệu bị lỗi serialization ở thời điểm lưu event nhưng không thử lỗi deserialize khi đọc lại sau deploy, khiến poison publication tồn lâu không được phát hiện.
Nhóm chạy unit tests ở trạng thái database sạch nhưng không kiểm tra migration từ một bảng registry có dữ liệu chưa hoàn tất, khiến lần nâng cấp production bị lỗi schema.
Ứng dụng chỉ đo số event nhận từ ApplicationEventPublisher nhưng không đo số listeners hoàn tất, khiến dashboard báo mọi đơn đã đồng bộ dù còn publication incomplete.
Đội hiển thị tổng số publication incomplete trên một dashboard nhưng không tách theo listener target, khiến sự cố của module Hóa đơn bị che trong tổng backlog nhiều module.
Một service theo dõi thời gian thực thi listener nhưng không ghi thời gian từ commit transaction đến khi bắt đầu xử lý, khiến SLA giao sự kiện bị đánh giá thấp.
Nhóm chỉ cảnh báo listener exception trong log mà không theo dõi tuổi của publication incomplete, khiến một publication mắc kẹt lâu không gây cảnh báo.
Ứng dụng ghi error class của failed publication nhưng không có correlationId nghiệp vụ, khiến kỹ sư không thể đối chiếu publication đang chờ với đơn hàng gốc.
Đội dùng traceId của HTTP request khi publish nhưng không đưa trace context vào event, khiến execution của listener async và retry bị tách khỏi trace người dùng.
Một service gắn eventId làm metric tag cho mọi publication, khiến số series metrics tăng cực nhanh khi hàng triệu đơn hàng được xử lý.
Nhóm đo tỷ lệ thành công theo số API HTTP 200 nhưng không giám sát listener publication completion, khiến các sự cố gửi email sau commit không xuất hiện trong KPI.
Ứng dụng cần báo số publication retry mỗi giờ nhưng không phân biệt recovery thủ công và tự động, khiến đánh giá ổn định của hệ thống bị sai sau đợt xử lý sự cố.
Đội có Event Publication Registry ở database nhưng bảng lớn chưa có chỉ mục phù hợp, khiến dashboard truy vấn incomplete và gây áp lực lên transaction tạo đơn.
Một service mở logging nội dung event để điều tra retry nhưng event chứa địa chỉ khách, khiến dữ liệu cá nhân xuất hiện trong logs của đội trực không có quyền.
Nhóm ghi timestamp publication bằng đồng hồ pod và thời gian completion bằng database clock, khiến một số latency được đo âm khi clock lệch.
Ứng dụng gửi email cảnh báo cho mọi publication incomplete khi đối tác dừng một giờ, khiến hàng trăm nghìn alert được phát thay vì một sự cố có thể điều tra.
Đội báo event registry còn incomplete nhưng không gắn mức ưu tiên theo domain event, khiến sự kiện mất điểm thưởng được xử lý trước sự kiện tất toán tài chính.
Một service lưu publication completion của nhiều tenants trong cùng bảng nhưng báo cáo hỗ trợ không lọc tenant, khiến một nhân viên xem được thông tin sự kiện của tổ chức khác.
Nhóm cần kiểm toán thao tác re-submit từ trang quản trị nhưng công cụ chỉ ghi số lượng publication phát lại, khiến không biết operator nào đã kích hoạt xử lý.
Ứng dụng có dashboard chỉ tính event publish count tại publisher, khiến khi một listener thiếu bean sau deploy số event công bố vẫn đẹp dù chức năng mới không nhận.
Đội theo dõi executor active threads nhưng không theo dõi queue depth, khiến tình trạng backlog @ApplicationModuleListener bị phát hiện muộn sau khi khách báo thiếu email.
Một service ghi nhận retry attempts ở listener nhưng không lưu outcome của side effect tại đối tác, khiến một publication incomplete không thể phân loại đã xử lý hay chưa.
Nhóm xây cảnh báo khi publication tồn đọng quá 15 phút nhưng không tính thời gian bảo trì được lên lịch, khiến dashboard báo sự cố ngay trong đợt dừng dịch vụ có kế hoạch.
Ứng dụng cần tạo báo cáo nhất quán giữa module Đơn hàng và module Loyalty nhưng hợp đồng hiện chỉ nói event sẽ được phát mà không định nghĩa cách xác minh kết quả sau commit.
Đội muốn chứng minh mọi OrderPaid đều được module Hóa đơn xử lý ít nhất một lần kể cả khi pod restart, nhưng bộ test hiện chỉ kiểm tra ApplicationEventPublisher được gọi mà không có kịch bản registry recovery.
