Một hệ thống chuyển module tính phí từ khởi tạo object thủ công sang Spring IoC, nhưng controller vẫn giữ tham chiếu đến service cũ nên cấu hình dependency mới không có tác dụng.
Một ứng dụng xử lý đơn hàng tạo BeanFactory tối giản để chạy job, nhưng nhóm vận hành kỳ vọng các tiện ích tự động đăng ký với ApplicationContext cũng hoạt động giống bản web.
Một dịch vụ dùng BeanFactory để lấy bean theo tên trong thư viện tích hợp, nhưng tại startup một bean không tồn tại và lỗi chỉ xuất hiện khi request đầu tiên cần đến nó.
Một nhóm chuyển từ BeanFactory thuần sang ApplicationContext để có thêm dịch vụ container, nhưng quy trình khởi tạo singleton khiến lỗi dependency bộc lộ sớm hơn dự kiến.
Một ứng dụng CLI khởi nhiều ApplicationContext độc lập cho từng file đầu vào, khiến mỗi context tạo một tập singleton và số connection tới hệ thống ngoài tăng theo số file.
Một nền tảng đa tenant có context cha chứa bean dùng chung và context con chứa bean từng tenant, nhưng một bean ở context cha cần inject service chỉ tồn tại trong context con.
Một hệ thống cho phép context con đăng ký bean cùng tên với bean trong context cha, khiến module đọc cấu hình nhận implementation khác tùy nơi thực hiện lookup.
Một dịch vụ khởi một AnnotationConfigApplicationContext tạm để chạy migration, nhưng không đóng context nên các resource và callback dọn dẹp của bean không được giải phóng.
Một ứng dụng chỉ gọi getBean với kiểu interface chung từ ApplicationContext, nhưng có nhiều bean cùng triển khai interface nên container không xác định được ứng viên duy nhất.
Một nhóm gọi getBean theo tên để tránh trùng kiểu, nhưng tên bean thay đổi sau refactor cấu hình khiến job nền lỗi dù ứng dụng web vẫn inject bình thường.
Một hệ thống quản lý báo cáo lấy bean qua ApplicationContext ở mỗi request, khiến dependency động và phạm vi tồn tại của object trở nên khó kiểm soát khi lưu cache.
Một dịch vụ tích hợp plugin đăng ký bean sau khi context đã hoàn tất refresh, nhưng nhóm phát triển kỳ vọng các singleton hiện tại tự nhận dependency mới.
Một ứng dụng dùng GenericApplicationContext để đăng ký BeanDefinition theo dữ liệu startup, nhưng một bean cần được tạo trước khi toàn bộ định nghĩa đã được đăng ký.
Một nhóm tạo hai ApplicationContext cho cùng một module trong test, khiến bean singleton trong mỗi context có trạng thái riêng và kết quả không trùng production.
Một hệ thống chạy command-line workload không có HTTP request nhưng một bean phụ thuộc request scope được tạo từ đường thực thi nền, khiến việc lấy instance thất bại khi xử lý.
Một dịch vụ muốn đọc trạng thái các bean trong ApplicationContext để debug, nhưng công cụ chỉ liệt kê bean definitions và bỏ qua những singleton được đăng ký bằng cách khác.
Một ứng dụng tạo service bằng new trong một lambda do Spring quản lý, khiến dependency của service đó không được inject dù các lớp xung quanh đều là Spring beans.
Một nhóm lưu ApplicationContext vào biến static dùng chung nhiều test, khiến lần test sau vô tình truy cập bean đã bị đóng khi context cũ được giải phóng.
Một hệ thống có context cha giữ bean Client và context con tùy biến cấu hình Client, nhưng lookup bằng tên từ context cha vẫn trả instance chia sẻ thay vì phiên bản tenant.
Một dịch vụ chuyển startup logic sang ApplicationRunner nhưng một dependency singleton đã được khởi tạo trước lúc runner cài đặt cấu hình mà nhóm vận hành kỳ vọng.
Một ứng dụng dùng @Component cho service thanh toán nhưng class nằm ngoài base package của component scan, khiến constructor của controller không tìm thấy bean cần inject.
Một nhóm thêm @Service cho implementation mới nhưng cấu hình @ComponentScan loại toàn bộ package billing, khiến bean không xuất hiện dù annotation vẫn còn trên class.
Một hệ thống quét cả package thử nghiệm ở production, khiến một @Repository giả được đăng ký cùng bean thật và dependency injection trở nên mơ hồ.
Một ứng dụng định nghĩa @Component và @Bean cho cùng một implementation xử lý đơn hàng, khiến container tạo hai instance và listener nghiệp vụ có thể bị kích hoạt hai lần.
Một dịch vụ đặt tên @Component tường minh khác với tên mặc định, nhưng một module dùng @Qualifier theo tên trước đó khiến startup thất bại sau thay đổi.
Một nhóm dùng @ComponentScan với exclude filter quá rộng, khiến các class có custom stereotype annotation cũng bị loại dù cần tham gia xử lý.
Một hệ thống thiết kế @Service chuyên dụng với meta-annotation @Component, nhưng class được đặt ở thư viện ngoài phạm vi scan nên chỉ một ứng dụng không tạo bean.
Một ứng dụng quét module plugins bằng include filter cho annotation đặc biệt, nhưng annotation chưa được giữ ở runtime nên một số implementation không được nhận diện.
Một nhóm có hai component cùng simple class name ở hai package, khiến Spring sinh tên bean mặc định trùng nhau và context gặp lỗi hoặc đăng ký không như dự kiến.
Một hệ thống bật hai cấu hình component scan chồng lấp qua nhiều import, khiến nhóm phát triển không biết một class có được đăng ký hai lần hay không khi đổi phạm vi quét.
Một dịch vụ đánh dấu đối tượng DTO bằng @Component để tiện dùng lại, khiến DTO trở thành singleton chứa trạng thái request và làm lộ thông tin giữa các phiên xử lý.
Một ứng dụng có class cấu hình chứa @Bean trong package được scan, nhưng một profile chuyển cấu hình ra ngoài vùng scan khiến bean chỉ thiếu ở production.
Một nhóm dùng @Configuration để import nhiều module hạ tầng, nhưng một import nhầm gói test tạo thêm implementation lưu dữ liệu không được phép dùng ở production.
Một hệ thống gọi @ComponentScan từ module gốc mới khi tái cấu trúc source tree, khiến những bean trong package cũ không được tìm thấy sau deployment.
Một ứng dụng quản lý notification khai báo custom stereotype nhưng thiếu @Component trong meta-annotation, khiến class được nhìn nhận là logic hợp lệ mà Spring không tạo bean.
Một nhóm đặt interface mapper bên cạnh component implementation, nhưng cấu hình scan chỉ dựa trên tên package mà bỏ sót implementation trong module phụ thuộc.
Một dịch vụ đăng ký bean qua @Import nhưng một cấu hình import có điều kiện môi trường không được kích hoạt, khiến component scan riêng không tìm thấy bean dự phòng.
Một hệ thống chạy nhiều loại worker qua cùng module Spring, nhưng @ComponentScan quá rộng làm những worker không liên quan cũng được khởi tạo và chiếm tài nguyên.
Một ứng dụng dùng @Repository cho adapter kết nối database rồi chuyển nó thành class tiện ích không có annotation, khiến service inject adapter thất bại sau refactor.
Một nhóm muốn chỉ đăng ký một adapter giả lập trong CI, nhưng điều kiện profile của bean giả và bean thật cùng thỏa nên container có hai ứng viên.
Một hệ thống có plugin do bên thứ ba cung cấp được đánh dấu @Component, nhưng ứng dụng chủ không quét package plugin khiến code thư viện được tải mà bean không xuất hiện.
Một ứng dụng tách configuration vào nhiều jar nhưng class @Configuration của jar mới không được import, khiến những @Bean method trong jar đó không được thực thi.
Một dịch vụ thay một bean bằng implementation mới nhưng chưa cập nhật include filter, khiến Spring tiếp tục tạo bản cũ dù bean mới có đủ annotation.
Một nhóm sử dụng @ComponentScan theo pattern tên class, nhưng convention tên thay đổi sau khi đổi nhóm phát triển khiến một tập bean bị bỏ qua khi khởi động.
Một hệ thống muốn đăng ký tất cả MessageHandler bằng stereotype tùy biến, nhưng vài handler không được quét nên danh sách inject dạng collection thiếu chức năng xử lý.
Một ứng dụng dùng constructor injection cho ShippingService, nhưng thiếu bean ShippingClient trong context khiến toàn bộ chuỗi tạo bean từ controller tới service bị lỗi.
Một nhóm chuyển từ field injection sang constructor injection nhưng để lại hai constructor chưa được phân giải, khiến cách Spring chọn constructor không còn rõ ở các môi trường.
Một hệ thống có constructor yêu cầu hai dependency cùng kiểu PricingPolicy, khiến Spring không thể chọn ứng viên đúng khi cả chính sách trong nước và quốc tế đều được đăng ký.
Một dịch vụ có constructor tham số thứ ba chỉ phục vụ môi trường staging, nhưng dependency tùy chọn không tồn tại ở production và làm cả service không khởi tạo được.
Một ứng dụng dùng setter injection cho endpoint URL và không cung cấp cấu hình ở một môi trường, khiến bean đã được tạo nhưng chỉ lỗi khi gọi API đối tác.
Một nhóm dùng field injection với @Autowired nhưng unit test tự khởi tạo class, khiến dependency vẫn null dù test service không khởi động Spring context.
Một hệ thống dùng constructor injection trong hai bean cùng cần nhau, khiến ApplicationContext không giải quyết được vòng phụ thuộc khi tạo singleton.
Một dịch vụ đặt vòng phụ thuộc qua setter giữa InvoiceService và AuditService, khiến bean khởi tạo nhưng hai component khó xác định rõ ranh giới trách nhiệm.
Một ứng dụng dùng @Lazy trên dependency để trì hoãn khởi tạo, nhưng lỗi credential của dependency chỉ được phát hiện khi request đầu tiên đi qua bean đó.
Một nhóm inject ObjectProvider vào factory để chọn processor tại runtime, nhưng code mong đợi luôn có đúng một processor trong khi Spring đăng ký nhiều bean hợp lệ.
Một hệ thống dùng Optional cho dependency không bắt buộc, nhưng một module thiếu bean cung cấp và chức năng liên quan âm thầm không hoạt động dù service đã startup.
Một dịch vụ inject collection các RuleHandler để xử lý quy tắc, nhưng một handler mới không được đăng ký khiến tập chính sách thiếu phần kiểm tra sau release.
Một nhóm inject Map tên bean đến implementation để chọn handler, nhưng tên một bean thay đổi khi refactor khiến lookup theo mã nghiệp vụ không còn trùng key.
Một hệ thống dùng Stream từ ObjectProvider để duyệt nhiều bean, nhưng xử lý gây tác dụng phụ trong lúc duyệt khiến thứ tự khởi tạo và sử dụng handler khó dự đoán.
Một ứng dụng inject một Factory tạo đối tượng nghiệp vụ nhưng implementation lại giữ trạng thái người dùng trong singleton, khiến hai yêu cầu đồng thời dùng chung dữ liệu.
Một nhóm có nhiều bean implements CurrencyConverter, nhưng mong Spring tự chọn converter theo mã tiền của request dù lựa chọn injection diễn ra lúc wiring.
Một hệ thống dùng tham số tên trong constructor để phân biệt bean cùng kiểu, nhưng khi build không giữ metadata tên tham số thì cách phân giải dependency đổi khác.
Một dịch vụ đưa @Autowired lên constructor chứa cả network client và heavy model, khiến một tính năng nhỏ không thể startup khi model tùy chọn gặp lỗi tải.
Một ứng dụng có bean cần một List<Validator>, nhưng thư viện mới đưa thêm validator vào context khiến cùng yêu cầu bị từ chối theo chính sách chưa được đánh giá.
Một nhóm thử thay mock dependency trong test nhưng service được tạo trước khi mock được đăng ký, khiến constructor vẫn giữ dependency thật suốt bài kiểm tra.
Một hệ thống chuyển constructor của ProductService thành kiểu tham số interface, nhưng bean hiện tại chỉ đăng ký qua kiểu class không tương thích và container không tìm được ứng viên.
Một ứng dụng inject generic Repository<Order> và Repository<Customer>, nhưng hai bean đăng ký qua factory xóa metadata generic khiến việc phân biệt theo kiểu không còn đáng tin.
Một nhóm tạo bean theo method generic dùng chung, nhưng return type khai báo quá rộng khiến Spring không cung cấp đủ type metadata cho dependency nơi tiêu thụ.
Một dịch vụ dùng @Autowired(required=false) trên setter, nhưng logic nghiệp vụ vẫn gọi dependency như bắt buộc và lỗi xuất hiện muộn khi người dùng thực hiện chức năng.
Một ứng dụng inject Supplier<ReportService> tự viết, nhưng supplier tạo object thủ công ngoài container khiến các dependency và callback lifecycle của service không được áp dụng.
Một nhóm inject bean có kiểu Collection để cấu hình bộ xử lý nhưng Spring hiểu đây là collection dependency, khiến nhiều implementation được tập hợp khác kỳ vọng người thiết kế.
Một hệ thống dùng constructor injection trên record làm holder cấu hình, nhưng đưa object đó vào bean scope sai khiến dữ liệu cấu hình tenant bị chia sẻ ngoài ý muốn.
Một dịch vụ áp dụng @Qualifier("domestic") cho chính sách thuế, nhưng bean đã được đổi qualifier sau tách module nên context lỗi dù vẫn có TaxPolicy bean.
Một nhóm đặt @Primary cho hai implementation PaymentGateway, khiến Spring không có lựa chọn ưu tiên duy nhất khi inject vào OrderService.
Một ứng dụng có @Primary trên processor mặc định nhưng một chỗ injection dùng @Qualifier khác, khiến implementation được chọn không giống điều mà nhóm phát triển suy từ @Primary.
Một hệ thống dùng bean name như qualifier trong module A và custom @Qualifier ở module B, khiến khi hợp nhất context một số injection points không phân giải được.
Một dịch vụ dùng @Fallback để đánh dấu implementation dự phòng, nhưng khi plugin thêm một bean không fallback nữa cách Spring chọn dependency thay đổi giữa các triển khai.
Một nhóm có qualifier trên constructor parameter nhưng đặt lại annotation trên bean definition theo quy ước khác, khiến Spring không tìm thấy đúng converter cho tenant.
Một ứng dụng cần tất cả implementations của FraudRule bằng list nhưng @Order được thêm không nhất quán, khiến chuỗi đánh giá chính sách khác dự kiến.
Một dịch vụ inject Map<String, PaymentHandler> nhưng sử dụng key là mã cổng thanh toán thay vì bean name, khiến lookup thất bại với handler mới được đăng ký.
Một hệ thống dùng @Primary cho bean singleton chung, nhưng request scope bean cùng kiểu cũng tồn tại và việc inject qua provider không chọn bean mà nhóm mong đợi.
Một ứng dụng có hai DataExporter với qualifier khác nhau, nhưng khi test thay bean bằng stub không giữ qualifier khiến BeanCreationException chỉ xuất hiện ở CI.
Một nhóm tách interface sang package khác, nhưng bean @Bean method vẫn trả interface cũ khiến autowiring theo kiểu mới không nhận implementation.
Một dịch vụ có custom qualifier annotation cho RegionAwareClient nhưng thiếu runtime retention, khiến cấu hình Java trông hợp lệ còn container không dùng được qualifier.
Một hệ thống đăng ký nhiều object từ cùng factory method có tên bean động, khiến một qualifier tĩnh trong service không chọn được bean đã đổi tên theo môi trường.
Một nhóm đặt alias cho bean để tương thích API cũ, nhưng một alias trùng tên bean khác làm wiring của module legacy không còn ổn định.
Một ứng dụng có bean @Primary của module ứng dụng và bean @Primary của thư viện chung, khiến sau khi import thư viện các injection point từng chạy ổn gặp lỗi mơ hồ.
Một dịch vụ dùng annotation tùy biến gắn qualifier trên class nhưng đăng ký bean bằng @Bean trả interface, khiến nhóm phát triển cần xác minh metadata qualifier tại bean definition.
Một hệ thống chọn handler theo @Order trong List nhưng code tự sort theo tên bean, khiến thứ tự Spring đã thiết lập không được duy trì khi chạy chính sách.
Một ứng dụng inject bean theo @Qualifier tên cũ trong constructor, nhưng tên @Bean method đã đổi cùng bản release và không còn match sau khi cấu hình được làm sạch.
Một nhóm muốn dùng implementation dự phòng khi không có bean phù hợp, nhưng class dự phòng được scan cùng primary implementation và gây lựa chọn ngoài ý muốn.
Một hệ thống có plugin được cấp custom @Qualifier nhưng hai bean dùng cùng annotation và thuộc tính giống nhau, khiến injection điểm duy nhất vẫn có nhiều ứng viên.
Một ứng dụng đánh dấu plugin handler bằng @Order nhưng kỳ vọng Spring chỉ khởi tạo handler đầu tiên, khiến các bean còn lại cũng được tạo với dependency nặng.
Một nhóm dùng @Resource theo tên ở một module và @Autowired theo kiểu ở module khác, khiến refactor bean name chỉ làm hỏng một số đường injection.
Một dịch vụ áp dụng @Value cho thuộc tính timeout mà không có giá trị trong Environment, khiến singleton phụ thuộc cấu hình không thể được tạo khi khởi động.
Một ứng dụng dùng @PropertySource cho cấu hình nội bộ nhưng file bị loại khỏi artifact production, khiến nhiều @Value injection không được giải quyết dù file tồn tại ở IDE.
Một hệ thống dùng placeholder với giá trị mặc định cho endpoint tích hợp, nhưng production thiếu biến môi trường và kết nối vô tình chuyển tới endpoint staging.
Một nhóm đặt cùng một key cấu hình trong nhiều PropertySource có thứ tự ưu tiên khác nhau, khiến bean được tạo với giá trị không trùng file mà người vận hành vừa sửa.
Một ứng dụng dùng @Value truyền chuỗi vào tham số kiểu Duration, nhưng dữ liệu cấu hình có đơn vị không đúng nên quá trình chuyển đổi kiểu xảy ra lỗi.
Một dịch vụ đọc giá trị cấu hình bằng Environment ở constructor, nhưng property được bổ sung sau giai đoạn tạo bean nên object giữ giá trị không đầy đủ trong suốt vòng đời.
Một nhóm đưa SpEL vào @Value để gọi bean khác lúc khởi tạo, khiến thứ tự tạo dependency thay đổi và một lỗi vòng tham chiếu xuất hiện khi startup.
Một hệ thống muốn dùng cùng configuration class cho test và production, nhưng property được override trong test context làm bean giả lập nhận đường dẫn dữ liệu thật.
Một dịch vụ khai báo bean cấu hình từ Environment nhưng quên truyền hai property bắt buộc trong @Bean factory method, khiến service nhận object với giá trị mặc định sai môi trường.
Một ứng dụng thay đổi property sau khi ApplicationContext đã refresh, nhưng singleton lấy giá trị qua constructor vẫn dùng cấu hình cũ dù Environment đọc được giá trị mới.
Một nhóm dùng @Bean method tạo StorageClient từ URL cấu hình, nhưng không xác minh URL ngay lúc tạo nên lỗi mạng chỉ bộc lộ khi người dùng tải file.
Một hệ thống tạo hai bean cùng tên qua @Bean methods trong các module config khác nhau, khiến behavior phụ thuộc chính sách ghi đè BeanDefinition của context.
Một ứng dụng viết @Configuration class với @Bean method gọi một @Bean method khác, nhưng nhóm đổi sang chế độ lite configuration khiến object được tạo lại ngoài singleton mong đợi.
Một dịch vụ đặt proxyBeanMethods=false để giảm overhead cấu hình, nhưng code vẫn gọi trực tiếp một @Bean method khác thay vì nhận bean từ container nên có hai instance.
Một nhóm chuyển @Bean methods từ class @Configuration sang @Component, khiến việc gọi trực tiếp method trong class không được container intercept như ở full configuration.
Một hệ thống dùng @Bean cho SDK client đóng tài nguyên, nhưng method trả interface không khai báo cách đóng rõ khiến team không biết callback destroy nào thực thi khi context ngừng.
Một ứng dụng dùng @Import để tổ hợp nhiều cấu hình hạ tầng, nhưng một cấu hình tạo bean với tên trùng khiến context lỗi chỉ ở môi trường đã bật cả hai tính năng.
Một nhóm dùng @Conditional dựa vào classpath bên ngoài để bật một bean, nhưng test và production có dependency khác nhau nên lựa chọn implementation không thống nhất.
Một dịch vụ muốn đăng ký bean theo điều kiện property nhưng điều kiện đặt ở method @Bean khác vị trí mong đợi, khiến module import vẫn tạo bean phụ thuộc không cần thiết.
Một hệ thống có nhiều @Configuration classes dùng @Profile khác nhau, nhưng một profile mới được bật đồng thời khiến hai phiên bản của cùng DataSource được đăng ký.
Một ứng dụng tạo bean bằng factory method có ngoại lệ kiểm tra cấu hình, nhưng exception bị bắt và trả một object chưa hợp lệ khiến lỗi thật xuất hiện khi bean được sử dụng.
Một nhóm cần bean được khởi tạo theo cấu hình có tham số runtime, nhưng @Bean singleton giữ giá trị của lần tạo đầu nên những request sau không nhận được cấu hình riêng.
Một dịch vụ tạo ShoppingCart như singleton Spring bean, khiến người dùng khác nhau vô tình dùng chung danh sách sản phẩm và dữ liệu giỏ hàng bị trộn.
Một ứng dụng có singleton OrderProcessor chứa trường mutable currentOrder, khiến hai HTTP request đồng thời ghi đè trạng thái trong bean khi xử lý đơn.
Một nhóm đổi bean ReportBuilder sang prototype nhưng inject trực tiếp vào singleton ReportService, khiến mọi lần tạo báo cáo vẫn sử dụng cùng một instance đã được resolve lúc khởi tạo.
Một hệ thống dùng ObjectProvider cho prototype bean trong job nền, nhưng code chỉ lấy instance một lần rồi cache lại khiến phạm vi thực tế không còn như nhóm mong đợi.
Một dịch vụ triển khai SessionPreferences với session scope nhưng được gọi từ CLI task không có HTTP session, khiến bean không thể được resolve khi công việc bắt đầu.
Một ứng dụng inject request-scoped ShoppingContext vào singleton BillingService mà không có cơ chế tham chiếu phù hợp, khiến context không thể tạo dependency khi chưa có request.
Một nhóm sử dụng scoped proxy cho bean chứa thông tin request, nhưng debug so sánh identity của proxy với target khiến họ hiểu nhầm mọi request dùng cùng object trạng thái.
Một hệ thống có request scope bean được tạo trong servlet thread, nhưng công việc được chuyển sang worker thread không có request context nên truy cập bean thất bại.
Một ứng dụng gắn prototype scope cho file parser nhưng không đóng stream trong parser, khiến Spring không tự thực hiện đầy đủ vòng đời hủy của những instance đã được cấp.
Một nhóm ghi số lượng instance prototype bằng singleton counter không thread-safe, khiến số liệu đo mức tạo bean sai khi nhiều request cùng tạo parser.
Một dịch vụ dùng thread scope tự đăng ký cho một tác vụ, nhưng thread pool tái sử dụng worker khiến dữ liệu của lượt xử lý trước còn gắn với scope trong lượt sau.
Một hệ thống chuyển UserSession từ session scope sang singleton để cải thiện hiệu năng, khiến trạng thái đăng nhập được chia sẻ giữa nhiều khách hàng không liên quan.
Một ứng dụng dùng application scope bean trong web context, nhưng module kiểm thử chạy ApplicationContext không web và không có scope được yêu cầu.
Một nhóm đặt @Scope trên class nhưng lại đăng ký instance bằng @Bean có phạm vi khác, khiến team hiểu sai scope thực tế của bean được inject.
Một dịch vụ tạo request-scoped PricingContext cho nhiều method, nhưng một singleton giữ tham chiếu target thay vì scoped proxy làm dữ liệu theo request không được tách như mong muốn.
Một hệ thống muốn mỗi lần gọi một factory nhận bean độc lập, nhưng singleton scope của sản phẩm khiến các lần getBean trả cùng instance và thay đổi trạng thái ảnh hưởng nhau.
Một ứng dụng có prototype Processor gắn @PreDestroy để dọn tài nguyên, nhưng team kỳ vọng Spring sẽ tự hủy mọi instance prototype khi ApplicationContext đóng.
Một nhóm đánh dấu @Lazy trên singleton service nhưng một bean eager khác phụ thuộc vào nó, khiến service vẫn được tạo sớm và startup không giảm tài nguyên như dự kiến.
Một dịch vụ dùng @DependsOn cho bean khởi tạo cache, nhưng một thành phần khác tạo cache qua đường thủ công nên thứ tự startup của hai hệ thống không thống nhất.
Một ứng dụng cần tạo singleton sau khi dữ liệu tham chiếu sẵn sàng, nhưng ApplicationContext khởi tạo bean eager trong lúc refresh trước khi tác vụ import hoàn tất.
Một nhóm thiết kế custom Scope lưu bean trong Map toàn cục, nhưng không gắn cleanup callback nên các resource của bean còn tồn tại sau khi scope bị đóng.
Một hệ thống có nhiều custom scopes trong một context, nhưng hai scope đăng ký cùng tên khiến một module dùng vòng đời object khác với bản thiết kế.
Một dịch vụ yêu cầu bean có trạng thái mới cho từng tenant, nhưng chọn request scope khiến hai request liên tiếp của cùng tenant không chia sẻ dữ liệu cần thiết.
Một ứng dụng dùng scoped proxy cho BeanFactory lookup và serialize proxy vào kết quả API, khiến JSON response chứa kiểu runtime không phù hợp với dữ liệu nghiệp vụ.
Một nhóm giữ tham chiếu đến request scope bean trong async callback sau khi HTTP request kết thúc, khiến callback không còn truy cập được trạng thái đã gắn với scope.
Một hệ thống tạo prototype TaskHandler chứa trạng thái file đang xử lý, nhưng các handler cùng tham chiếu một dependency singleton mutable và kết quả các file ảnh hưởng nhau.
Một ứng dụng có factory method tạo nhiều instance của một object nặng, nhưng bean scope được đặt prototype khiến mỗi lần resolve lại tạo connection mới và cạn tài nguyên.
Một nhóm dùng @Lookup method để nhận prototype từ singleton, nhưng class/method bị giới hạn override nên cơ chế lookup injection không hoạt động như dự kiến.
Một dịch vụ muốn singleton dùng một bean mới sau mỗi lần xử lý, nhưng dependency được tiêm vào constructor chỉ được resolve một lần và các lần sau giữ trạng thái cũ.
Một ứng dụng cấu hình custom Scope theo thời gian sống, nhưng phần quản lý session hủy scope trước khi các component hoàn tất xử lý, khiến bean biến mất giữa request.
Một hệ thống dùng singleton chứa cache tùy biến không giới hạn, khiến memory tăng qua nhiều ngày và việc thay scope không giải quyết được vấn đề vòng đời dữ liệu.
Một nhóm tạo ApplicationContext mới cho mỗi tenant để có singleton riêng, nhưng không đóng context khi tenant rời hệ thống khiến connection pools tồn tại lâu hơn cần thiết.
Một dịch vụ có bean đăng ký callback trong @PostConstruct để nghe message, nhưng dependency của nó chưa được cấu hình xong khi callback bắt đầu nhận dữ liệu.
Một ứng dụng dùng @PostConstruct trên service có bước gọi mạng dài, khiến quá trình tạo ApplicationContext bị chậm hoặc lỗi khi service đối tác không khả dụng.
Một nhóm đặt @PreDestroy trên worker đang xử lý, nhưng tác vụ được hệ điều phối dừng cưỡng bức trước khi callback hoàn thành khiến trạng thái chưa được ghi lại.
Một dịch vụ khai báo initMethod và @PostConstruct cho cùng bean, nhưng cả hai đều tạo resource mới và kết quả là hai connection không mong muốn.
Một hệ thống cấu hình destroyMethod cho bean quản lý file, nhưng một @Bean khác mượn cùng stream và vẫn cố ghi khi context đóng khiến dữ liệu bị mất.
Một ứng dụng dùng DisposableBean và @PreDestroy trên cùng object để dọn tài nguyên, nhưng mỗi callback cùng đóng một resource khiến log shutdown có lỗi phụ.
Một nhóm triển khai InitializingBean.afterPropertiesSet để validate secret, nhưng secret chỉ có sau khi bên ngoài tải config khiến startup thất bại ở một vùng.
Một dịch vụ tạo bean kế thừa lớp cha có callback khởi tạo, nhưng một subclass còn gắn @PostConstruct và team không biết thứ tự chuẩn bị dữ liệu đang diễn ra.
Một hệ thống dùng @DependsOn để ép thứ tự khởi tạo DataSource và CacheWarmer, nhưng nghĩ rằng annotation này cũng bảo đảm mọi cache warmup async hoàn tất trước các request.
Một ứng dụng gọi method nghiệp vụ ở constructor trước khi setter injection hoàn tất, khiến dependency chỉ được gán sau constructor và lần gọi đầu gặp giá trị null.
Một nhóm truy cập BeanFactory từ callback BeanPostProcessor nhưng tạo thêm dependency quá sớm, khiến một bean chưa được xử lý hoàn chỉnh bởi các post-processors khác.
Một hệ thống có init callback đăng ký listener vào broker và destroy callback gỡ listener, nhưng bean được khởi tạo ngoài container khiến hai callback không bao giờ chạy.
Một dịch vụ chuyển đổi một resource manager từ singleton sang prototype, nhưng không quản lý việc đóng từng instance khiến số file descriptor tăng sau nhiều lượt xử lý.
Một ứng dụng đăng ký ApplicationListener trong một bean và cũng thêm listener bằng cấu hình trực tiếp, khiến một sự kiện context bị nhận hai lần.
Một nhóm phát event nghiệp vụ trong @PostConstruct, nhưng một listener bean khác chưa được đăng ký theo lifecycle mong đợi khiến sự kiện đầu bị bỏ qua.
Một hệ thống dùng ContextRefreshedEvent để bắt đầu job nền, nhưng khi context được refresh lần nữa job được chạy lặp và nhập cùng file hai lần.
Một ứng dụng dùng ApplicationReadyEvent của Spring Boot để gọi service, nhưng một module core-only chỉ có ApplicationContext thông thường nên listener đó không bao giờ được kích hoạt.
Một nhóm nghe ContextClosedEvent để giải phóng connection, nhưng shutdown được thực hiện sau khi một dependency đã ngừng phục vụ và cleanup không hoàn tất.
Một dịch vụ có SmartLifecycle bean điều khiển consumer, nhưng phase không phù hợp khiến consumer nhận message trước khi dependency xử lý của nó sẵn sàng.
Một ứng dụng khai báo autoStartup=false cho SmartLifecycle worker, nhưng bộ điều phối lại giả định mọi consumer được khởi cùng lúc ApplicationContext refresh.
Một nhóm dùng lifecycle phase để sắp thứ tự dừng hai consumers, nhưng một component không implements SmartLifecycle nên thứ tự dừng không tuân theo suy luận ban đầu.
Một hệ thống cần xác định lúc mọi singleton đã được tạo, nhưng một bean dùng SmartInitializingSingleton thực thi tác vụ nặng và kéo dài toàn bộ startup.
Một dịch vụ bật lazy initialization cho nhiều singleton nhưng vẫn chạy thống kê ở giai đoạn pre-instantiation, khiến thời điểm lỗi dependency không như thiết kế kiểm tra.
Một ứng dụng có bean callback @PreDestroy gọi endpoint ngoài, nhưng khi endpoint chậm quá timeout của orchestrator tiến trình bị kill và trạng thái cleanup khó xác định.
Một nhóm gọi context.close trong khi một request vẫn sử dụng bean singleton, khiến callback hủy resource chạy song song với thao tác nghiệp vụ đang xử lý.
Một hệ thống chạy nhiều context cùng event listener type, nhưng event từ context con có thể được publish lên context cha khiến listener dùng chung nhận sự kiện nhiều lần.
Một dịch vụ dùng FactoryBean để tạo HTTP client tùy biến, nhưng component khác gọi getBean theo tên và nhầm đối tượng client được tạo với chính factory.
Một nhóm cần inspect FactoryBean đã đăng ký, nhưng lookup bean theo tên thông thường trả sản phẩm thay vì đối tượng factory nên công cụ cấu hình không đọc được metadata.
Một hệ thống tạo nhiều serializer từ FactoryBean có trạng thái nội bộ, nhưng factory không khai báo rõ sản phẩm singleton hay không khiến việc tái sử dụng khác dự kiến.
Một ứng dụng tạo FactoryBean để khởi một client nặng, nhưng getObject ném lỗi cấu hình ở lần lookup đầu và startup chỉ thất bại khi feature được sử dụng.
Một nhóm dùng FactoryBean.getObjectType để giúp Spring autowiring theo kiểu, nhưng return type báo không chính xác khiến dependency không được tìm thấy trong context.
Một dịch vụ tích hợp SDK có FactoryBean sản xuất ProxyClient, nhưng getObjectType trả null ở giai đoạn kiểm tra và lựa chọn bean theo kiểu trở nên khó chẩn đoán.
Một hệ thống đăng ký một FactoryBean dưới tên pluginA, nhưng @Qualifier cho product bean không khớp với cách bean name và factory name được sử dụng.
Một ứng dụng đổi implementation của FactoryBean nhưng vẫn dùng cache ngoài của sản phẩm cũ, khiến một số consumer giữ client đã được tạo theo cấu hình trước.
Một nhóm dùng FactoryBean để cấp đối tượng có session riêng, nhưng chính factory giữ shared mutable state và các lần tạo session ảnh hưởng nhau dưới tải.
Một hệ thống gọi trực tiếp factory.getObject trong code thay vì lấy sản phẩm từ container, khiến hành vi scope và quản lý singleton sản phẩm khác cách bean được resolve.
Một ứng dụng có FactoryBean nắm resource cần đóng nhưng chỉ cấu hình destroy của sản phẩm được tạo, khiến resource bên trong factory chưa được xử lý ở shutdown.
Một nhóm tạo BeanFactoryPostProcessor để sửa giá trị BeanDefinition, nhưng lại đọc một singleton service ngay trong callback khiến nó bị khởi tạo trước khi các definitions được xử lý hết.
Một hệ thống dùng BeanDefinitionRegistryPostProcessor để thêm hàng trăm bean động, nhưng tên bean trùng với định nghĩa hiện tại nên đăng ký bị từ chối hoặc thay thế ngoài dự kiến.
Một ứng dụng có hai BeanFactoryPostProcessor cùng sửa property của một definition, nhưng thứ tự thực thi chưa được kiểm chứng khiến giá trị cuối khác staging.
Một nhóm gắn @Bean method không static để khai báo một BeanFactoryPostProcessor trong @Configuration, khiến config class được khởi tạo sớm và việc inject dependency có hành vi bất thường.
Một hệ thống viết BeanPostProcessor để gắn metadata cho service, nhưng vô tình tạo một target object mới thay vì trả đúng bean đang được khởi tạo khiến các dependency mất trạng thái.
Một dịch vụ có BeanPostProcessor bọc thêm client thành proxy, nhưng logic advice chung của framework được áp dụng sau đó khiến chuỗi proxy và kiểu cuối khó kiểm tra.
Một ứng dụng dùng BeanPostProcessor để validate bean sau init, nhưng chỉ test constructor và không kích hoạt quá trình post-processing nên lỗi metadata không xuất hiện ở CI.
Một nhóm muốn áp BeanPostProcessor trên bean được tạo bằng new trong logic nghiệp vụ, khiến các object ngoài container không nhận callback như những bean Spring quản lý.
Một hệ thống có BeanFactoryPostProcessor thuộc module tùy chọn, nhưng module không được import nên nhiều BeanDefinitions giữ placeholder chưa được điều chỉnh.
Một ứng dụng viết BeanDefinitionRegistryPostProcessor đăng ký bean theo danh sách đối tác, nhưng danh sách tải sau refresh khiến các bean cần thiết không được tạo trong đợt startup.
Một nhóm dùng PropertySourcesPlaceholderConfigurer để phân giải placeholder, nhưng biến môi trường thiếu khiến quá trình tạo bean định nghĩa bằng giá trị động thất bại.
Một hệ thống có BeanPostProcessor đặt trạng thái audit lên mọi bean, nhưng một bean infrastructure được tạo sớm không trải qua đầy đủ các post-processors và làm đội vận hành hiểu nhầm.
Một dịch vụ dùng BeanNameAware để lấy tên bean cho log, nhưng cùng class được đăng ký dưới nhiều tên nên kết quả giám sát khác giữa các module.
Một ứng dụng dùng ApplicationContextAware trong một service để lấy tùy ý các bean, khiến dependency ẩn tăng nhiều và unit test phải dựng context lớn thay vì một tập dependency rõ ràng.
Một nhóm sử dụng EnvironmentAware để đọc cấu hình tại khởi tạo, nhưng property thay đổi sau đó không làm biến nội bộ của singleton tự cập nhật.
Một hệ thống có ResourceLoaderAware bean nạp file cấu hình, nhưng đường resource tồn tại trong IDE mà không nằm trong jar được phát hành khiến startup thất bại.
Một dịch vụ đọc dữ liệu từ classpath Resource bằng File path tuyệt đối, nhưng sau khi đóng executable jar URL của resource không còn tương ứng file thực trên đĩa.
Một ứng dụng có bean trong context cha cần tìm định nghĩa ở context con, nhưng BeanFactoryAware cung cấp factory sở hữu bean nên lookup không thấy các bean chỉ có ở context con.
Một nhóm làm ApplicationEventPublisherAware để gửi thông báo khi dữ liệu thay đổi, nhưng listener ném exception đồng bộ và làm luồng lưu nghiệp vụ bị ảnh hưởng.
Một hệ thống có nhiều PropertyEditors và Converter được đăng ký qua ConversionService, nhưng một bean dùng kiểu thời gian đặc biệt không chuyển được từ cấu hình như nhóm mong đợi.
Một dịch vụ khai báo FormattingConversionService cho UI nhưng container đang dùng ConversionService khác, khiến injection property sang DTO và bean configuration có kết quả khác nhau.
Một ứng dụng định nghĩa custom TypeConverter cho giá tiền, nhưng một @Value vẫn được chuyển bằng quy tắc khác nên giá trị đơn vị bị diễn giải không đồng nhất.
Một nhóm dùng message source để hiển thị thông báo lỗi từ ApplicationContext, nhưng bundle ngôn ngữ thiếu resource của region mới khiến fallback message không phù hợp.
Một hệ thống xử lý events qua ApplicationEventMulticaster đồng bộ, nhưng listener làm HTTP call chậm khiến publisher bị giữ lâu trong method đang lưu đơn.
Một ứng dụng cấu hình async event multicaster nhưng listener của hai sự kiện liên tiếp chạy khác thứ tự, khiến mã nghiệp vụ giả định event được xử lý tuần tự bị sai.
Một nhóm phát cùng event từ hai ApplicationContext có quan hệ cha con, khiến listener ở parent nhận cả event của child ngoài số liệu thống kê cần thiết.
Một dịch vụ inject một List<Object> kỳ vọng chỉ plugin beans, nhưng context trả quá nhiều bean khác kiểu vì generic type không đủ ràng buộc chức năng.
Một ứng dụng đăng ký dependency dưới interface của thư viện ngoài, nhưng class loader của plugin tạo kiểu cùng tên từ loader khác khiến Spring không coi chúng tương thích.
Một nhóm dùng bean alias để duy trì API config cũ, nhưng dependency injection ở module mới dựa trên tên chính và team không nhận ra hai tên trỏ một singleton.
Một hệ thống muốn khởi tạo bean có điều kiện dữ liệu từ server ngoài, nhưng điều kiện được đánh giá khi đọc definitions và kết quả API ngoài có thể thay đổi sau lúc context refresh.
Một dịch vụ ghi đè BeanDefinition trong module test nhưng chính sách context không cho override, khiến bài kiểm thử thay thế bean bị từ chối dù cấu hình override có vẻ hợp lý.
Một ứng dụng dùng @ImportResource cho XML bean definitions trong thư viện cũ, nhưng đường XML không có trong artifact mới nên service không tìm thấy bean legacy.
Một nhóm định nghĩa cùng một DataSource trong XML và Java @Configuration, khiến bean theo type và bean theo tên được resolve khác kỳ vọng khi hợp nhất module.
Một hệ thống có tùy chọn tạo bean qua FactoryBean hoặc @Bean cho cùng loại client, nhưng import cả hai cấu hình khiến dependency cần một client có nhiều lựa chọn.
Một ứng dụng lưu reference đến bean trong static holder khi context đầu tiên khởi tạo, khiến hot-reload test tạo context mới vẫn truy cập bean cũ đã bị destroy.
Một nhóm chạy @SpringJUnitConfig với cấu hình tối thiểu nhưng thiếu BeanPostProcessor nghiệp vụ, khiến test tạo bean thành công mà callback quan trọng của production không chạy.
Một hệ thống chỉnh trạng thái singleton trong integration test nhưng không đánh dấu context đã thay đổi, khiến các lớp test khác tái dùng ApplicationContext cache và nhận dữ liệu cũ.
Một ứng dụng thay bean thật bằng mock trong test nhưng mock được đăng ký khác qualifier, khiến constructor vẫn nhận bean thật hoặc gặp lỗi nhiều ứng viên.
Một nhóm chỉ test service bằng constructor thủ công, khiến lỗi component scanning và missing bean definitions của configuration thật không được phát hiện trước release.
Một hệ thống có context tests tạo bean nhờ profile dev nhưng deployment chạy profile prod, khiến sự khác biệt implementation không được xác minh trong integration test.
Một ứng dụng kiểm tra custom FactoryBean bằng gọi getObject thủ công, nhưng không thử lookup qua ApplicationContext nên lỗi product type và bean name không được phát hiện.
Một nhóm muốn xác nhận prototype scope nhưng bài test chỉ lấy bean một lần, khiến thực tế bean được tiêm vào singleton như một dependency cố định không được kiểm tra.
Một dịch vụ có bean @Lazy chứa lỗi startup, nhưng suite chỉ gọi context.refresh mà không truy cập bean nên bài kiểm thử không chứng minh chức năng có thể chạy.
Một hệ thống có vòng phụ thuộc giữa ba singleton, nhưng test mock một dependency làm cấu trúc vòng biến mất và production mới lỗi khi khởi tạo.
Một ứng dụng dùng condition theo Environment để chọn bean, nhưng test đặt property nguồn ưu tiên khác production nên hai cấu hình thực thi không đồng nhất.
Một nhóm đo thời gian startup bằng context nhỏ trong test, nhưng production scan rất nhiều components và các init callbacks gọi mạng nên thời gian khởi tạo tăng ngoài dự kiến.
Một hệ thống có BeanPostProcessor dựa trên annotation riêng nhưng test chỉ đăng ký bean bằng plain factory, khiến annotation metadata không được phản ánh như ở context đầy đủ.
Một ứng dụng kiểm thử đóng ApplicationContext nhưng không xác minh resource manager destroy callback, khiến connection leak chỉ xuất hiện sau nhiều lần restart production.
Một nhóm chạy stress test chỉ với một thread trên singleton service, khiến lỗi chia sẻ mutable field giữa nhiều request không lộ trước khi vận hành.
Một dịch vụ triển khai nhiều replica và mong singleton chứa registry được chia sẻ toàn cluster, khiến cấu hình mới được ghi trên replica A không xuất hiện ở replica B.
Một hệ thống muốn đổi bean implementation không cần restart, nhưng lựa chọn DI đã cố định trong ApplicationContext đang chạy nên request mới vẫn dùng dependency cũ.
Một ứng dụng cần cô lập cấu hình tenant nhưng mọi tenant dùng cùng singleton chứa mutable Configuration, khiến thay đổi tenant này gây ảnh hưởng tenant khác.
Một nhóm đưa thông tin người dùng vào @Bean singleton factory method, khiến thông tin của request đầu vô tình được dùng cho tất cả yêu cầu sau.
Một dịch vụ có custom BeanPostProcessor ghi log tên mọi bean, nhưng log startup chứa secret được đưa vào bean configuration nên thông tin nhạy cảm lộ trên hệ thống vận hành.
Một hệ thống có nhiều bean eager tải mô hình lớn khi startup, khiến JVM vượt memory limit trước khi bất kỳ endpoint nào được khai báo sẵn sàng.
Một ứng dụng dùng lazy-init cho network client để rút ngắn startup, nhưng lần gọi nghiệp vụ đầu tiên gặp lỗi kết nối thay vì thất bại ở bước khởi tạo.
Một nhóm chuyển bean từ class sang factory method trong @Configuration, nhưng metadata scope và destroy callback không còn tương đương nên có resource không được đóng.
Một hệ thống nâng phiên bản Spring Framework và thay đổi cơ chế giải quyết một dependency tùy chọn, khiến tập bean được inject qua constructor cần kiểm tra lại trước phát hành.
Một ứng dụng khởi nhiều context để thử tính năng mới nhưng không tách tài nguyên dùng chung, khiến hai context cùng đóng một connection khi vòng đời kết thúc.
Một dịch vụ dùng ApplicationContext để tổ chức dependency graph lớn, nhưng một nhóm vô tình inject lớp domain entity như singleton khiến state của request bị giữ trong container lâu dài.
