Một nền tảng bán lẻ dùng Spring Modulith để mô tả các module Order, Inventory và Payment; sau khi đổi package của Payment, sơ đồ module sinh tự động không còn hiển thị ranh giới mà đội kiến trúc mong đợi.
Nhóm phát triển gọi ApplicationModules để khám phá cấu trúc ứng dụng; một thư viện đặt các package nghiệp vụ ngoài root package khiến module quan trọng không xuất hiện trong graph.
Ứng dụng dùng package theo tầng controller, service và repository; việc nhận diện application module dựa trên cấu trúc package làm sơ đồ không phản ánh đúng các miền nghiệp vụ.
Đội chia module Fulfillment thành nhiều package ngang hàng; tài liệu sinh ra nhiều module nhỏ không tương ứng với một đơn vị triển khai trách nhiệm mà nhóm vận hành đang quản lý.
Nhóm thiết lập application module theo cấu trúc package nghiệp vụ; một class được di chuyển tới package gốc và vô tình trở thành API công khai cho module khác.
Ứng dụng có module Shipping phụ thuộc trực tiếp một class nội bộ của Billing; sơ đồ dependency được sinh cho thấy một liên kết trái với quy ước ranh giới đã phê duyệt.
Đội đổi kiểu trả về của một service được module khác gọi; tài liệu module canvas vẫn hiển thị sự phụ thuộc nhưng không thể hiện ngay thay đổi hợp đồng dữ liệu gây lỗi.
Nhóm thiết kế mô-đun Customer và Loyalty với dependency vòng; kết quả kiểm tra kiến trúc không phù hợp sơ đồ trình bày trước đó đã được gửi cho stakeholders.
Ứng dụng sử dụng @ApplicationModule để khai báo tên hiển thị cho module; tên được đổi theo tái cấu trúc tổ chức làm người đọc báo cáo nhầm hai module với một miền nghiệp vụ.
Đội dùng allowedDependencies để hạn chế phụ thuộc giữa các application module; một feature mới thêm tham chiếu tới module ngoài danh sách và bản vẽ phát sinh liên kết không được duyệt.
Nhóm chỉ cho phép truy cập API qua @NamedInterface; một class mới không thuộc giao diện công khai nhưng vẫn được module khác import và được ghi nhận trong đồ thị tương tác.
Ứng dụng có hai named interfaces phục vụ đối tác nội bộ và backoffice; tài liệu graph gộp cả hai nên người đọc không biết một module nên dùng interface nào.
Đội thêm module Reporting chuyên đọc dữ liệu tổng hợp; graph phát sinh phụ thuộc Reporting tới gần mọi module và khiến việc xác định ranh giới quản lý dữ liệu trở nên khó khăn.
Nhóm theo dõi sự phụ thuộc ngược giữa các module sau khi thêm hệ thống audit; một bean chung được mọi module tham chiếu tạo nút trung tâm rất lớn trên sơ đồ.
Ứng dụng chuyển một phần xử lý từ lời gọi trực tiếp sang application event; module graph vẫn có phụ thuộc kiểu dữ liệu event và nhóm nghĩ hai module đã hoàn toàn tách rời.
Đội tạo một module Common chứa DTO và utility; gần như mọi module phụ thuộc vào đó làm sơ đồ rất dày và che khuất các ranh giới nghiệp vụ thật.
Nhóm dùng Java package-private cho implementation của module; module graph vẫn hiển thị phụ thuộc qua shared type đặt sai package và các reviewer bỏ sót vi phạm.
Ứng dụng sử dụng reflection để gọi một component nội bộ từ module khác; sơ đồ dependency tĩnh không thể hiện được tương tác thực tế khiến kiểm toán kiến trúc bỏ lỡ một điểm nối.
Đội gắn handler Spring event theo tên bean thay vì type công khai; module graph cho thấy ít dependency hơn thực tế khi luồng runtime gửi sự kiện qua nhiều module.
Nhóm đổi tên module theo ngôn ngữ nghiệp vụ nhưng classpath vẫn chứa package legacy; tài liệu tự sinh và sơ đồ nhóm xây thủ công sử dụng hai hệ thống tên khác nhau.
Ứng dụng có module cấu hình dùng @Import kéo bean từ module khác; graph dependency hiển thị các kết nối kỹ thuật gây nhầm lẫn với dependency nghiệp vụ mà nhóm cần theo dõi.
Đội muốn phân biệt dependency bắt buộc và dependency chỉ dùng trong test; sơ đồ kiến trúc đang được tạo từ một cấu hình có nhiều bean thử nghiệm nên thể hiện kết nối không tồn tại ở production.
Nhóm tổ chức package theo bounded context cho ứng dụng quản lý bảo hiểm; một module có quá nhiều public type và canvas không nói rõ điểm vào nào là hợp đồng ổn định.
Ứng dụng phục vụ nhiều thị trường với các bean theo @Profile; tài liệu module graph được sinh từ cấu trúc mã nhưng nhóm vận hành tưởng mọi bean đều chạy trong profile production.
Đội phát triển dựa vào application module graph để đánh giá mức độ tách biệt; dependency động qua HTTP client tới dịch vụ ngoài không hiện ở graph và nhóm hiểu sai phạm vi tương tác.
Nhóm kiểm tra phụ thuộc khi xóa một tính năng cũ; sơ đồ vẫn cho thấy liên kết tới module đã ngừng sử dụng vì tham chiếu type còn sót trong mã nguồn.
Ứng dụng chuyển các giao diện công khai sang một package named interface mới; client trong module khác vẫn import package cũ và việc thay đổi gây lỗi ở một số luồng ít được kiểm thử.
Đội muốn đo độ lớn application module bằng số package và bean; một module có ít class nhưng các giao dịch nghiệp vụ bên trong phức tạp làm đánh giá dựa trên graph thiếu chiều sâu.
Nhóm tái sử dụng chung event class giữa Order và Shipping; tài liệu ghi nhận sự liên hệ nhưng không nêu rõ ai sở hữu version schema của sự kiện đó.
Ứng dụng được tách từ monolith cũ thành các application module; cùng một entity được sử dụng trong ba module khiến sơ đồ không xác định rõ module sở hữu dữ liệu.
Đội sinh sơ đồ kiến trúc bằng Spring Modulith Documenter trong build; một thay đổi package được merge nhưng không tạo lại tài liệu nên trang wiki vẫn trình bày ranh giới cũ.
Nhóm xuất module graph thành sơ đồ PlantUML để review; hệ thống render trên CI thiếu công cụ phù hợp làm artifact tài liệu của bản phát hành không được tạo.
Ứng dụng đặt hình tài liệu module trong thư mục do pipeline lưu; lần chạy trên môi trường Windows tạo đường dẫn khác runner Linux nên liên kết từ README bị hỏng.
Đội thiết kế tài liệu C4 cho application modules; nội dung tự động lấy từ code chỉ có quan hệ phụ thuộc và không mô tả các hệ thống bên ngoài mà kiến trúc sư muốn thể hiện.
Nhóm dùng Documenter tạo tài liệu riêng cho module Billing; một helper kỹ thuật bị nhầm là API công khai làm module canvas liệt kê nhiều điểm vào không dành cho khách tích hợp.
Ứng dụng sinh module canvas mô tả beans và events của từng module; một event mới được tạo qua reflection không xuất hiện như cách đội tích hợp mong đợi.
Đội công bố tài liệu boundary trong pull request; diagram thay đổi quá nhiều vị trí nút do tự động sắp xếp khiến reviewer khó phát hiện một dependency mới đáng ngại.
Nhóm cần so sánh module graph giữa hai bản phát hành; tên module đổi làm hệ thống diff coi module cũ bị xóa và module mới được tạo dù miền nghiệp vụ không đổi.
Ứng dụng có tài liệu PlantUML generated từ snapshot mã nguồn; build artifact được cache theo nhánh và bản production vô tình mang sơ đồ của commit trước.
Đội tạo module canvas có các named interfaces; người xem không phân biệt API được cho phép và class chỉ hỗ trợ nội bộ vì format tài liệu không nhất quán giữa module.
Nhóm sử dụng tên sự kiện để mô tả tương tác trong module documentation; hai sự kiện khác package nhưng cùng tên đơn giản khiến tài liệu hiển thị nhầm nguồn phát.
Ứng dụng ghi mô tả nghiệp vụ vào tài liệu bổ sung thủ công; lần tạo lại Documenter làm mất các ghi chú cần thiết để hiểu quy tắc sử dụng API module.
Đội triển khai tài liệu module trên cổng developer nội bộ; file graph được tạo nhưng đường dẫn tương đối tới hình ảnh không được đóng gói và người đọc chỉ thấy liên kết lỗi.
Nhóm muốn nhóm sơ đồ theo subsystem để giảm độ phức tạp; một module shared xuất hiện ở nhiều nhóm và việc xem graph từng nhóm gây hiểu nhầm module đã được tách độc lập.
Ứng dụng phát hành sơ đồ architecture cho đơn vị kiểm toán; sơ đồ tự sinh thiếu version ứng dụng nên không thể chứng minh ranh giới đó tương ứng bản production nào.
Đội dùng Documentation build để giới thiệu các module cho nhân viên mới; module canvas chứa tên class thuần kỹ thuật mà không giải thích luồng nghiệp vụ khiến việc onboarding khó khăn.
Nhóm thay đổi package của module Returns khi tái cấu trúc; bookmark trỏ tới trang tài liệu module cũ bị hỏng dù mã nguồn mới vẫn hoạt động.
Ứng dụng muốn sinh tài liệu chỉ cho modules được phép công khai; tài liệu chung chứa cả module Security và nội bộ vận hành khiến phạm vi truy cập thông tin không phù hợp.
Đội có tài liệu module chứa các liên kết HTTP callback mẫu; khi một endpoint chuyển domain, sơ đồ dependency vẫn đúng nhưng liên kết hướng dẫn tích hợp không còn hoạt động.
Nhóm đặt module documentation dưới công cụ preview PR; các nhánh có tên ký tự đặc biệt tạo artifact path không hợp lệ và reviewer không thấy sự thay đổi ranh giới.
Ứng dụng tự động xuất graph vào artifact của CI; một thay đổi Gradle build bỏ qua bước documentation nhưng pipeline vẫn xanh và phát hành tài liệu cũ.
Đội quản lý dependency bằng rule trong tài liệu kiến trúc; kiểm tra tự động và graph sinh ra có cùng module khác tên nên báo cáo vi phạm khó ghép với tài liệu.
Nhóm muốn người duyệt xem module graph ngay trong diff; hình render chỉ là file binary và không cho thấy rõ nguyên nhân của cạnh dependency mới.
Ứng dụng dùng module canvas để thống kê các listener được phép; một class listener mới đặt sai package làm documentation liệt kê ở module khác và team gán nhầm owner sự cố.
Đội phát hành cùng lúc API module và sự kiện tích hợp; tài liệu được sinh từ class hiện có nhưng không chỉ ra giai đoạn deprecation của event version cũ.
Nhóm xây tài liệu tương tác giữa Inventory và Order; đồ thị chỉ thể hiện phụ thuộc static nên không minh họa được trình tự event khi có retry và xử lý lỗi.
Ứng dụng chuyển một endpoint giao tiếp trực tiếp thành published event; bản sơ đồ mới không cho người đọc biết tính bất đồng bộ thay đổi thời điểm dữ liệu sẵn sàng.
Đội tạo module graph từ ứng dụng có hơn 100 modules; kết quả quá dày để đưa vào tài liệu vận hành và người trực sự cố khó tìm lân cận một module cụ thể.
Nhóm sinh một trang cho mỗi module từ Documenter; tên file của hai module trùng nhau khi rút gọn và một tài liệu ghi đè tài liệu còn lại trên artifact server.
Ứng dụng có profile chỉ bật module Warehouse ở một quốc gia; documentation từ toàn codebase lại được đọc như sơ đồ runtime cho mọi quốc gia.
Đội dùng tài liệu module như chuẩn review kiến trúc; một lần sửa code khẩn không cập nhật artifact khiến báo cáo kiểm toán và trạng thái source khác nhau.
Nhóm cần nhận biết event dependency khác type dependency; cùng một màu đường nối trong module graph làm reviewer đánh giá sai mức độ coupling giữa các phần.
Ứng dụng sinh sơ đồ cho ứng dụng đa tenant; tài liệu không thể hiện cấu hình ranh giới dữ liệu theo tenant dù application module graph nhìn hợp lệ.
Đội tái cấu trúc module thành hai named interfaces; documentation vẫn trình bày một API chung nên module tiêu thụ không biết điểm vào nào được khuyến nghị.
Nhóm muốn phát hành snapshot module graph theo từng release; việc sinh tài liệu từ branch hiện tại làm link tài liệu lịch sử thay đổi theo bản commit mới.
Ứng dụng có phần documentation do bên thứ ba truy cập; tên package nội bộ, bean và event được xuất đầy đủ mà không có bước duyệt thông tin nhạy cảm.
Đội triển khai module documentation lên portal có CDN cache; một bản release xóa module cũ nhưng cache vẫn phục vụ sơ đồ với đường dependency đã bị loại.
Nhóm sử dụng tài liệu ứng dụng để đối soát kiến trúc; người xem nhầm mọi liên kết trên graph là call runtime và dự báo sai chi phí kết nối giữa các module.
Ứng dụng bật Spring Modulith Actuator để xem cấu trúc module; endpoint không được expose trên môi trường production dù dashboard vận hành đang gọi URL đó.
Đội cấu hình management.endpoints.web.exposure.include quá rộng; thông tin tên module và cấu trúc package nội bộ có thể bị truy cập từ mạng không tin cậy.
Nhóm đặt Actuator ở management port riêng; gateway chỉ chuyển tiếp cổng ứng dụng nên đội hỗ trợ nhận 404 khi kiểm dữ liệu module từ hệ thống giám sát.
Ứng dụng chuyển endpoint Actuator sang base path tùy chỉnh; script kiểm tra sơ đồ ứng dụng vẫn gọi đường dẫn mặc định và báo cấu trúc module không tồn tại.
Đội bật cơ chế xác thực cho management endpoints; tài khoản monitoring chỉ có quyền xem health nhưng không được phép đọc thông tin module phục vụ phân tích kiến trúc.
Nhóm cấu hình Actuator ở staging với đầy đủ tính năng; production thiếu dependency cần thiết nên endpoint mô-đun không có dù service khởi động thành công.
Ứng dụng có nhiều phiên bản triển khai cạnh nhau; dashboard truy vấn ngẫu nhiên một pod và hiển thị module graph khác với bản canary đang được kiểm thử.
Đội dùng dữ liệu cấu trúc module từ Actuator để tạo catalog; response đổi sau nâng Spring Modulith và parser dashboard không nhận các thuộc tính như trước.
Nhóm cấu hình lộ endpoint quản trị chỉ trong mạng nội bộ; một thay đổi ingress chuyển tiếp sai rule và làm lộ thông tin quan hệ module cho người ngoài.
Ứng dụng dùng dữ liệu module Actuator để gán owner sự cố; danh sách module thực tế không được gắn với đội sở hữu trong catalog nên alert không biết chuyển tới ai.
Đội muốn kiểm các modules thực sự có trên JVM đang chạy; endpoint cung cấp cấu trúc application modules nhưng người vận hành nhầm đó là bằng chứng từng module đã nhận traffic.
Nhóm nâng phiên bản Spring Boot và Spring Modulith; một endpoint quản trị không còn cùng điều kiện auto-configuration như môi trường test và dashboard bị mất số liệu.
Ứng dụng deploy nhiều instance với profile khác nhau; kết quả quản trị về module không tương ứng thứ tự khởi tạo bean mà đội vận hành đang quan sát trong log.
Đội gắn metadata module vào hệ thống asset inventory; một lần rename package làm cùng module bị coi là một tài sản mới và mất lịch sử sự cố cũ.
Nhóm đặt cache cho dữ liệu Actuator module structure; sau rollout phiên bản mới, cache giữ snapshot của bản cũ và cảnh báo kiến trúc phát sinh sai.
Ứng dụng có management endpoint yêu cầu TLS client certificate; công cụ giám sát không gửi đúng chứng chỉ và liên tục nhận 401 hoặc lỗi bắt tay.
Đội muốn truy cập endpoint qua service mesh; chính sách mạng chỉ cho /actuator/health nên truy vấn cấu trúc module bị chặn trong lúc health vẫn xanh.
Nhóm tăng tần suất lấy cấu trúc module từ Actuator lên mỗi giây; lượng request quản trị tăng không cần thiết và log bị ngập khi dashboard mở trên nhiều màn hình.
Ứng dụng có nhiều module với class name nhạy cảm về cơ chế chống gian lận; dữ liệu Actuator bị xuất công khai và tạo nguy cơ tiết lộ thiết kế nội bộ.
Đội xây readiness check bằng cách phụ thuộc thông tin module Actuator; endpoint module tạm không được nạp làm pod bị loại khỏi load balancer dù HTTP chính vẫn sẵn sàng.
Nhóm dùng một reverse proxy chung cho Actuator và API công khai; cấu hình cache ngoài ý muốn lưu phản hồi endpoint quản trị và người dùng khác có thể truy xuất.
Ứng dụng phát hành bản canary chỉ thay dependency graph; health vẫn báo UP và đội vận hành cần nhận biết bản đang chạy có ranh giới không khớp thiết kế đã duyệt.
Đội so sánh dữ liệu module từ Actuator với tài liệu Documenter cùng release; hai nguồn được lấy từ hai commit khác nhau và kết quả audit không nhất quán.
Nhóm muốn dùng Actuator để theo dõi thời gian thực từng module; endpoint cấu trúc không tự thể hiện latency nên dashboard không có chỉ số vận hành mà team kỳ vọng.
Ứng dụng có module Fraud độc lập về package; Actuator vẫn báo module tồn tại nhưng một bean bị tắt theo feature flag khiến xử lý fraud không thực hiện.
Đội giới hạn truy cập endpoint quản trị bằng role; một token service của đối tác được cấu hình quyền rộng hơn mức cần thiết và xem được toàn bộ application graph.
Nhóm đưa Actuator response vào ticket lỗi; payload chứa tên lớp và package nội bộ bị gửi sang hệ thống ticket bên ngoài không có cùng mức bảo vệ.
Ứng dụng tạo documentation ở build time rồi dùng Actuator runtime để so đối chiếu; thời gian deploy giữa hai môi trường gây cảnh báo sai khi một bản cũ còn phục vụ.
Đội thêm Spring Modulith observability để ghi dấu tương tác giữa application modules; hệ thống tracing chưa được cấu hình exporter nên trace tạo trong ứng dụng không xuất hiện ở backend.
Nhóm chuyển một luồng xử lý đơn từ gọi trực tiếp sang event nội bộ; trace của request gốc không nối với span xử lý sự kiện và điều tra lỗi phải tìm hai chuỗi riêng.
Ứng dụng có module Checkout gọi service Payment qua API công khai; công cụ trace không gắn tên application module cho entry point khiến dashboard chỉ thấy tên method kỹ thuật.
Đội quan sát span ở ranh giới module bằng Micrometer Observation; trong một release mới, các span bị đặt tên khác và dashboard không còn ghép được chuỗi latency lịch sử.
Nhóm bật tracing với sampling thấp trong production; một giao dịch hiếm gây lỗi ở module Billing không được lấy mẫu nên đội điều tra không thấy trace tương ứng.
Ứng dụng dùng một sampler chỉ giữ các request nhanh; những trace timeout dài nhất bị loại và dữ liệu quan sát khiến đội vận hành hiểu sai phân phối độ trễ.
Đội muốn nhận biết các lời gọi chéo module có latency cao; span của method xuất hiện nhưng khoảng thời gian chờ thread pool không được tính vào cùng đoạn xử lý.
Nhóm cấu hình histogram latency cho mỗi module; các module ít traffic có mẫu quá thưa và biểu đồ p99 dao động không phản ánh đúng hành vi điển hình.
Ứng dụng ghi số lượt gọi module A sang B bằng metric; nhãn chứa ID đơn hàng làm cardinality tăng theo giao dịch và chi phí giám sát vượt dự toán.
Đội gắn span attribute theo tên module và tên tenant; tenantId có hàng trăm nghìn giá trị làm việc truy vấn và lưu trace ngày càng tốn tài nguyên.
Nhóm đổi tên module trong code nhưng không đổi tên bảng dashboard; metric với nhãn module mới xuất hiện như một chuỗi dữ liệu khác và cảnh báo cũ mất hiệu lực.
Ứng dụng chỉ có metric HTTP endpoint toàn hệ thống; khi latency tăng ở module Inventory, đội không phân biệt được lỗi nằm trong validation hay truy vấn kho.
Đội tích hợp Micrometer Tracing để truyền trace sang PostgreSQL và WebClient; một client tự tạo ngoài Spring context không ghi span và lời gọi ngoại vi bị thiếu trong trace.
Nhóm thiết lập OTLP exporter cho môi trường cloud; endpoint collector sai cổng nên service vẫn xử lý đơn nhưng không có dữ liệu trace gửi về.
Ứng dụng gặp gián đoạn collector tracing; exporter queue đầy làm tăng bộ nhớ trong lúc nghiệp vụ đang chịu tải lớn.
Đội bật trace cho mọi lời gọi nội bộ giữa các module; một request tạo hàng nghìn span và backend observability giới hạn số span được lưu cho mỗi trace.
Nhóm dùng trace ID để điều tra sự cố ứng dụng; log không có traceId do MDC chưa được nối với hệ thống tracing và việc tìm một giao dịch vẫn phải dò thủ công.
Ứng dụng ghi metric cho event listener theo status; một exception bị handler bắt và nuốt khiến metric báo completed trong khi database chưa ghi kết quả.
Đội xây dashboard số sự kiện nội bộ được publish; lượt publish thành công được hiểu là mọi listener đã xử lý xong dù có listener async còn đang chờ.
Nhóm có hai application modules cùng lắng nghe OrderCompletedEvent; metric chỉ đếm số event đầu vào nên không biết listener nào đã lỗi và listener nào hoàn tất.
Ứng dụng ghi thời gian xử lý event theo tên event class; nhiều module phát class cùng tên đơn giản khiến biểu đồ trộn những luồng nghiệp vụ khác nhau.
Đội đo số sự kiện đã hoàn tất ở module Shipping; event listener xử lý ngoại lệ bằng retry nền nên số liệu completed không cho biết side effect cuối đã thành công hay chưa.
Nhóm quan sát workflow từ module Order sang Payment; một giao dịch được retry tạo nhiều lượt event handler và số span lớn hơn số đơn thực tế.
Ứng dụng có @ApplicationModuleListener xử lý sự kiện sau transaction; tracing chỉ ghi thời điểm listener bắt đầu mà thiếu thời gian chờ publication nên SLA tổng bị đánh giá thấp.
Đội dùng @TransactionalEventListener ở module Audit; transaction gốc rollback và listener không được gọi, nhưng biểu đồ publish dựa trên lệnh gọi publisher vẫn tăng.
Nhóm muốn đo thời gian từ event publication đến completion; dashboard chỉ có thời gian thực thi listener mà không ghi độ trễ trong queue của executor.
Ứng dụng dùng event publication registry để theo dõi xử lý sự kiện; một publication hoàn tất nhưng bị crash trước khi marker được cập nhật khiến số outstanding vẫn tăng.
Đội cấu hình kho event publication bền vững; một đợt lỗi database làm registry không ghi nhận trạng thái đầy đủ và dashboard báo sai số event còn tồn.
Nhóm chạy retry các event publications chưa hoàn tất sau restart; metric xử lý thành công tăng hai lần cho cùng một event khiến tỷ lệ hoàn tất cao bất thường.
Ứng dụng có listener xử lý mail và listener ghi audit cùng một domain event; một listener thất bại nhưng dashboard chỉ xem event-level counter và đánh dấu cả quy trình thành công.
Đội thêm sự kiện OrderCancelled vào module Orders; documentation hiển thị event mới nhưng metric listener không có dữ liệu do flow chỉ bật ở profile khác.
Nhóm chuyển phát event từ trong transaction sang sau commit; thời điểm span và event metrics thay đổi làm dashboard thời gian xử lý trước/sau release không còn so sánh trực tiếp.
Ứng dụng dùng sự kiện nội bộ cho phần lập báo cáo; một listener chỉ chạy vào ban đêm và alert phát hiện không có traffic đánh dấu module lỗi vào ban ngày.
Đội đo tỷ lệ lỗi cho event listener; một listener nhận event không hợp lệ và từ chối nghiệp vụ nhưng metrics ghi cùng nhóm với lỗi hạ tầng, tạo cảnh báo giả.
Nhóm sử dụng retry có backoff cho listener; dashboard chỉ ghi lỗi cuối nên số lần thử lại và thời gian chờ bị ẩn sau kết quả thành công.
Ứng dụng xuất metric số publication pending; lượng pending tăng do worker pause có chủ đích nhưng đội vận hành không biết khác biệt với lỗi ngừng tiêu thụ.
Đội phân loại metric event theo customerId để điều tra; số lượng label values tăng theo mỗi event và collector bị giới hạn tài nguyên.
Nhóm muốn so sánh số event publish và số listener complete; một event có ba listener làm hai bộ đếm không cùng đơn vị, báo cáo tỷ lệ thành công bị sai.
Ứng dụng phát sự kiện sau commit để cập nhật search index; tracing của request ban đầu kết thúc trước listener nên đội hỗ trợ hiểu rằng cập nhật tìm kiếm đã đồng bộ.
Đội mở metric cho transaction event publication; thao tác ghi marker lỗi riêng không làm nghiệp vụ chính thất bại và hệ thống có khoảng trống quan sát trạng thái thực.
Nhóm cần kiểm tra event listener nào phát sinh lỗi ở production; tên listener không được gắn trong metric và mọi lỗi bị quy về module sở hữu event.
Ứng dụng gửi domain event chứa dữ liệu riêng tư; observability log nguyên payload để debug làm thông tin khách xuất hiện trong hệ thống giám sát truy cập rộng.
Đội dùng trace sampling theo endpoint HTTP; các sự kiện được tạo từ scheduler không có HTTP root span và không được lấy mẫu theo chính sách tương ứng.
Nhóm muốn gắn event ID vào trace; publisher và listener sinh ID khác nhau khi retry làm đội vận hành không đối chiếu được tất cả lần xử lý cùng một sự kiện.
Ứng dụng có event handler update trạng thái đơn nhiều lần; metric chỉ ghi số lần xử lý mà không phân biệt update hợp lệ với duplicate do retry.
Đội xây cảnh báo khi sự kiện pending quá lâu; sự kiện của workflow tháng có thời hạn xử lý khác sự kiện OTP nhưng đều dùng cùng một ngưỡng chung.
Nhóm dùng event metrics làm chỉ số đúng dữ liệu; publication completed chỉ cho biết callback đã hoàn thành chứ không chứng minh hệ thống bên ngoài đã giao thông báo thành công.
Ứng dụng có event từ module Customer truyền sang Billing; một phần event được lọc theo tenant nhưng số liệu publish không chia nhánh nên team nghĩ Billing nhận toàn bộ.
Đội muốn theo dõi luồng giao dịch từ REST đến event listener qua executor; trace context chỉ tồn tại trong request thread và biến mất khi listener bắt đầu trên worker.
Nhóm dùng ThreadLocal lưu traceId của khách; listener được thực thi trên thread khác nên log PaymentEvent không còn mã tương quan với thao tác tạo đơn.
Ứng dụng bật @Async trên application event listener; SecurityContextHolder không được truyền sang worker và module Audit ghi người thực hiện là anonymous.
Đội đặt tenantId trong MDC của HTTP filter; khi thread pool tái sử dụng worker mà MDC không được dọn, event của khách mới có thể bị log dưới tenant cũ.
Nhóm cấu hình TaskDecorator cho một ThreadPoolTaskExecutor; module Reporting dùng executor khác không có decorator nên trace vẫn đứt tại một nhánh sự kiện.
Ứng dụng dùng CompletableFuture để xử lý event listener; các callback chạy ở ForkJoinPool.commonPool không giữ context truyền từ Spring-managed executor.
Đội chuyển từ platform threads sang virtual threads trong Spring Boot; hệ thống observability dựa vào thread name không còn nhận diện luồng giao dịch như dashboard cũ.
Nhóm áp virtual threads cho event handlers; một thiết lập ThreadLocal giữ object người dùng lớn trên mỗi task làm bộ nhớ tăng theo số event đang chạy.
Ứng dụng dùng Reactor Mono để gọi kho dữ liệu từ listener; MDC được đọc trực tiếp thay vì Reactor Context khiến trace và tenantId biến mất sau chuyển scheduler.
Đội truyền traceparent vào HTTP outbound trong một module; module khác dùng client mới không có interceptor nên phân tách trace tại ranh giới gọi đối tác.
Nhóm nhận Kafka message rồi publish application event; headers Kafka có traceparent nhưng code dựng event không nối ngữ cảnh làm trace consumer và listener không liên hệ.
Ứng dụng gửi một domain event qua nhiều module với nhiều async branches; mỗi nhánh tạo trace root riêng và dashboard không thể dựng toàn bộ nhánh workflow từ một giao dịch.
Đội chuyển xử lý sang scheduled retry job; event được phát lại sau nhiều giờ và trace của request ban đầu không còn tồn tại trong ngữ cảnh chạy job.
Nhóm muốn giữ correlation ID riêng cho nghiệp vụ dù trace sampling tắt; code chỉ dựa vào traceId tự động và không tìm được bản ghi khi không có trace được tạo.
Ứng dụng thiết kế event mang customerId nhưng không mang business correlation ID; handler phía sau không biết sự kiện thuộc yêu cầu đồng bộ nào trong một đợt backfill.
Đội dùng Micrometer Context Propagation với nhiều context accessors; một accessor tùy chỉnh copy dữ liệu tenant không đúng khiến worker ghi log sang namespace khác.
Nhóm thay tên baggage field trong cấu hình tracing; phần xuất hiện trên downstream dùng tên cũ nên correlation giữa hai module không còn khớp.
Ứng dụng dựa vào ThreadLocal để giữ LocaleContext của request; email async từ một event listener dùng locale mặc định và người nhận thấy nội dung sai ngôn ngữ.
Đội dùng @Async ở module Billing sau khi publish event từ @Transactional service; listener không kế thừa transaction của request nhưng log trace khiến nhóm tưởng cả workflow nằm trong một transaction.
Nhóm nhận callback từ hệ thống thứ ba và publish event ở thread do thư viện quản lý; Spring observation scope không tự được áp vào thread và span bắt đầu không có parent.
Ứng dụng tạo event từ batch scheduler không có người dùng đăng nhập; interceptor context propagation giả định luôn có SecurityContext và ném lỗi ở job cuối ngày.
Đội cấu hình propagation cho Reactor Context nhưng module khác sử dụng Java ExecutorService tự tạo; một số bước có trace còn những bước khác bị mất dấu.
Nhóm muốn quan sát listener sau khi WebFlux request bị cancel; business event vẫn chạy nhưng trace của request đã kết thúc và callback không có trạng thái hủy tương ứng.
Ứng dụng copy MDC sang worker nhưng không xóa dữ liệu sau completion; task tiếp theo cùng worker hiển thị traceId cũ và dẫn điều tra sự cố sang khách khác.
Đội chuyển sự kiện nội bộ thành message Kafka; trace propagation chỉ từng hoạt động trong JVM và không có traceparent trên broker headers nên chuỗi phân tán bị đứt.
Nhóm sử dụng virtual-thread-per-task executor cho nhiều listeners; các metric dựa vào số active platform threads báo tải thấp dù hàng nghìn tác vụ đang chờ database.
Ứng dụng kết hợp async listener và transaction event; tracing của sự kiện bắt đầu trước commit nhưng callback thực hiện sau commit khiến thời gian xử lý hiển thị không rõ ranh giới.
Đội có nhiều tenant với cùng module event flow; nhãn trace chứa email người dùng thay vì một business ID an toàn làm dữ liệu cá nhân được chuyển sang collector ngoài.
Nhóm tạo span theo một module method được gọi lặp nhiều lần; cách đặt tên span chứa UUID của mỗi object khiến truy vấn hiệu năng theo module không còn hiệu quả.
Ứng dụng dùng sampling chỉ theo root HTTP request; lỗi nghiêm trọng phát sinh tại event listener vài giờ sau không được ưu tiên giữ trace cho việc điều tra.
Đội phát hiện lỗi logger không có traceId trong một callback reactive; metric event vẫn tăng đều làm nhóm vận hành tưởng tracing đã bao phủ toàn luồng.
Nhóm thêm module-specific logging để xác định owner; một event chuyển qua module Fraud nhưng tên logger chỉ có class kỹ thuật nên alert route tới sai nhóm.
Ứng dụng xuất span của module Payment bằng tên đã đổi package; backend observability đang dùng filter theo tên cũ và biểu đồ giao dịch hiển thị bằng không sau deploy.
Đội đặt cảnh báo theo exception count ở module Shipping; khi lỗi được xử lý bằng fallback, exception bị ẩn và chỉ số lỗi giảm dù chất lượng dữ liệu thấp hơn.
Nhóm cần quan sát việc cập nhật mô-đun trên canary; metrics cùng module name từ bản ổn định và bản canary bị gộp khiến ảnh hưởng release mới bị che.
Ứng dụng tính p95 cho từng application module; một module xử lý nền nhiều giờ được thống kê chung với lời gọi HTTP ngắn khiến percentile khó diễn giải.
Đội tăng số module nhỏ và đặt metric riêng mỗi public method; cardinality tăng mạnh, gây tốn chi phí và khó tạo dashboard cấp miền nghiệp vụ.
Nhóm muốn liên hệ số event failures với lượng request của một module; các request tạo nhiều events làm tỷ lệ tính trực tiếp giữa hai metric không còn ý nghĩa.
Ứng dụng có job dọn outstanding publications lúc nửa đêm; metric completion tăng đột biến nhưng người xem tưởng module được phục hồi khỏi outage đúng thời điểm đó.
Đội xây SLO dựa trên số event listener completed; event bị xử lý trùng do retry được đếm nhiều lần và chỉ số hoàn tất cao hơn số giao dịch thật.
Nhóm đo latency cho từng module boundary; phần đợi hàng đợi executor giữa hai module không nằm trong span nào và tổng latency thực bị thiếu.
Ứng dụng xuất metric từ cả Micrometer Observation và một interceptor tự viết; cùng lượt gọi module được đếm hai lần sau khi bật observability tự động.
Đội cấu hình tags cho các module với tên có dấu gạch chéo; backend metrics chuẩn hóa khác nhau nên một module bị tách thành hai chuỗi thời gian.
Nhóm muốn tìm dependency gây lỗi gián tiếp từ graph; cấu trúc module không chỉ ra được service call bên ngoài bị timeout mà chỉ trace runtime mới cho thấy thời gian chờ.
Ứng dụng ghi event spans nhưng không ghi trạng thái result; toàn bộ event listener nhìn như đã hoàn tất trong tracing dù có nhánh trả exception bị xử lý ngầm.
Đội muốn cảnh báo khi module vốn thường xuyên phát event ngừng gửi; một đợt bảo trì có chủ đích khiến zero-traffic alert liên tục gây báo động giả.
Nhóm xây dashboard top module latency; các event listener async được tính vào module phát thay vì module tiêu thụ và đội sở hữu nhận sai cảnh báo.
Ứng dụng áp quota metrics per pod; một pod có nhiều custom tags bị collector cắt dữ liệu và bảng tỷ lệ lỗi theo application module bị thiếu.
Đội xuất OpenTelemetry spans từ Spring Modulith cùng spans HTTP; tên service giống nhau giữa staging và production làm dữ liệu hai môi trường bị trộn trong cùng biểu đồ.
Nhóm đổi exporter endpoint giữa release nhưng collector mới chưa được phép truy cập; API vẫn thành công và sự cố thiếu trace chỉ được nhận ra khi xảy ra lỗi nghiệp vụ.
Ứng dụng dùng biểu đồ module interaction để đánh giá phụ thuộc runtime; sampling thấp làm một interaction hiếm không xuất hiện và team kết luận sai rằng hai module không tương tác.
Đội muốn phát hiện ranh giới module bị xuyên thủng sau refactor; đồ thị static đúng nhưng trace có lời gọi qua adapter động không được phân loại theo module owner.
Nhóm lưu chi tiết trace trong 7 ngày; một lỗi đối soát cuối tháng không còn trace gốc và chỉ còn metrics tổng hợp không đủ chứng minh bước thất bại.
Ứng dụng có policy xóa dữ liệu người dùng theo yêu cầu; một số span attributes lưu business identifiers lâu hơn chính sách retention của dữ liệu gốc.
Đội tăng tần suất phát sự kiện để thử throughput; exporter tracing tạo áp lực CPU và network khiến phép đo hiệu năng ứng dụng bị sai lệch.
Nhóm nhận sự kiện từ cùng HTTP request trên hai async listeners; trace context copy khác nhau làm một listener liên quan parent cũ còn listener khác thành trace mới.
Ứng dụng dùng spans để định nghĩa giao dịch đã thành công; span của publisher kết thúc khi gửi event chứ không thể chứng minh side effect trong listener hoàn tất.
Đội dùng một module đóng vai trò facade gọi nhiều module con; dashboard chỉ hiển thị facade span mà không có phân tách thời gian từng dependency và khó định vị bottleneck.
Nhóm thêm observation convention riêng cho từng module; một module dùng tag action còn module khác dùng operation khiến truy vấn tổng hợp không phản ánh cùng ngữ nghĩa.
Ứng dụng chia một module lớn thành hai module nhỏ; số spans và metrics thay đổi nhiều dù lưu lượng không đổi và alert dựa trên baseline cũ kích hoạt sai.
Đội cần phân biệt tương tác trực tiếp với event-driven giữa các module; telemetry hiện ghi cùng một operation name và không mô tả thời điểm chuyển ngữ cảnh.
Nhóm muốn gắn architecture rule với số liệu vận hành; một phụ thuộc bị cấm trong module graph vẫn chạy thành công và chỉ được phát hiện sau khi kiểm thử kiến trúc.
Ứng dụng thêm ApplicationModules.verify vào kiểm thử kiến trúc; một dependency mới bị cấm xuất hiện nhưng job sinh documentation vẫn chạy và xuất bản sơ đồ vi phạm.
Đội tạo kiến trúc test chỉ cho module Shipping; các package khác không được kiểm và một vòng dependency xuyên ba module tồn tại trong bản release.
Nhóm viết @ApplicationModuleTest để kiểm module Billing riêng; module test dùng dependency giả và không phản ánh một sự kiện thực đi qua ranh giới hai module.
Ứng dụng tạo test module với bootstrap mode giới hạn; một bean nhập từ module khác không được nạp khiến test lỗi dù ứng dụng production có đủ bean.
Đội kiểm module event listener bằng published events từ bộ test; chỉ xác minh event được phát mà không xác minh trạng thái listener khi transaction commit.
Nhóm dùng PublishedEvents để xác nhận một service phát DomainEvent; testcase mặc định rollback nên không quan sát được callback AFTER_COMMIT đang chạy trong production.
Ứng dụng kiểm ranh giới module qua diagram snapshot; hình thay đổi do layout engine dù dependency không đổi và pipeline báo lỗi giả khi so binary artifact.
Đội chỉ kiểm tài liệu module có được tạo thành công; một module mới bị đặt sai package nhưng không có assertion nào nhận ra module đó bị mất khỏi graph.
Nhóm viết test xác minh named interfaces; một interface bị đổi package khiến module đối tác vẫn import class nội bộ và test hiện chưa kiểm đường dependency này.
Ứng dụng kiểm Actuator endpoint trong môi trường staging; production cấu hình management port và security khác, khiến dashboard vận hành không truy cập được module data.
Đội test tracing trong @ApplicationModuleTest bằng một thread đồng bộ; listener production dùng TaskExecutor nên lỗi mất traceId khi async không được phát hiện.
Nhóm dùng mock ObservationRegistry ở integration test; mock luôn ghi nhận span nhưng exporter và propagation thật trên production chưa được kiểm.
Ứng dụng chạy test event metrics bằng một sự kiện hợp lệ; lỗi deserialization, rollback và event retry không được đưa vào tình huống nên dashboard thiếu trạng thái lỗi.
Đội sử dụng Testcontainers cho database lưu event publications; bài test chỉ khởi động rồi tắt bình thường và không kiểm crash giữa xử lý và cập nhật trạng thái.
Nhóm kiểm idempotency của module listener bằng một event đơn; production replay cùng event từ event registry sau restart và tạo side effect lặp chưa được phát hiện.
Ứng dụng có test dùng Clock cố định để đo publication duration; production dùng thời gian tường giữa nhiều node và metric duration biến động khi đồng hồ lệch.
Đội thực thi integration tests với profile không bật observability; bộ test pass dù bản release không có trace module nào được gửi đi.
Nhóm kiểm việc gắn correlation ID vào ApplicationEvent tại HTTP request; scheduler và Kafka consumer cũng phát sự kiện nhưng không mang cùng context trong test.
Ứng dụng nâng Spring Modulith cùng Micrometer; tên span và attribute thay đổi làm dashboard cũ không còn truy xuất đúng, còn test hiện chỉ xác minh không có exception.
Đội thêm Module Documentation vào pipeline Maven; runner CI không có khả năng render diagram và job bỏ qua bước mà không báo lỗi phát hành.
Nhóm muốn kiểm module graph không có cycle qua ApplicationModules; một module legacy nằm ngoài package scan nên vòng phụ thuộc quan trọng bị bỏ khỏi kết quả.
Ứng dụng có test đối chiếu graph giữa branch và main; một refactor hợp lệ đổi tên module làm test fail mặc dù các dependency thực vẫn tương đương.
Đội tạo test verifying public named interfaces; một loại event nằm ngoài interface công khai mà module tiêu thụ vẫn dùng trực tiếp trong runtime và không bị test phát hiện.
Nhóm dùng MockMvc để kích hoạt event rồi kiểm metrics; request hoàn thành trước async listener nên assertion đôi khi thấy count cũ và testcase flaky trên CI.
Ứng dụng kiểm trace context qua nhiều module bằng một fake executor đồng bộ; production có virtual threads và Reactor scheduling làm đường propagation khác hẳn môi trường test.
Đội triển khai tracing để chẩn đoán lỗi hiếm; test sampling bật 100% trong khi production sampling thấp và một incident không giữ được trace cần thiết.
Nhóm xây cảnh báo pending event publications; không mô phỏng retry sau crash trong test nên metric pending và completed chỉ được kiểm ở trạng thái bình thường.
Ứng dụng chuyển một controller sang WebFlux còn module khác dùng MVC; một chuỗi event xuyên cả hai stack làm SecurityContext và MDC không cùng cơ chế truyền.
Đội cần hiển thị một ứng dụng modulith theo các module đã đổi owner; graph vẫn liệt kê module cũ nhưng mapping owner ở dashboard không được cập nhật theo tổ chức mới.
Nhóm triển khai rolling update cùng lúc thay tên event và module; publication còn chờ của bản cũ không được listener mới nhận diện và metric pending tăng bất thường.
Ứng dụng có multi-tenant event workflow; một listener bị retry trên tenant context mặc định và trace biểu thị thành công dù dữ liệu được ghi sang tenant sai.
Đội phát hành documentation tự động và theo dõi metrics vận hành; đồ thị tĩnh cho thấy kết nối không đổi nhưng runtime sau deploy chuyển sang event handler mới có latency cao hơn.
Nhóm dùng C4 diagram để thảo luận tách ứng dụng thành microservices; dữ liệu module documentation không thể hiện dependency dữ liệu dùng chung và lãnh đạo hiểu sai chi phí chia tách.
Ứng dụng hiện triển khai như monolith có application modules rõ ràng; đội vận hành nhầm modules với các service riêng và kỳ vọng actuator/health isolation mà JVM hiện tại không cung cấp.
Đội yêu cầu điều tra vì sao Payment module chậm; biểu đồ chỉ có HTTP request latency còn module observations cho thấy một listener gây trì hoãn dù không có request mới.
Nhóm quyết định tách module Notification theo số span cao; số span lớn chủ yếu do retry chứ không phải lượng công việc mới và việc đánh giá capacity bị sai.
Ứng dụng giữ docs module graph và dashboard trace trên hai môi trường; tài liệu mô tả package hiện tại còn dashboard đang dùng nhãn module tên cũ khiến việc đối chiếu release thất bại.
Đội muốn báo cáo tỷ lệ dependency vi phạm qua từng sprint; schema của tài liệu generated đổi theo phiên bản thư viện và công cụ trích xuất graph không còn đọc được.
Nhóm cần xây SLO theo hành trình Order đến Invoice; luồng phát event bất đồng bộ làm root trace HTTP kết thúc sớm và SLO nhìn theo request không bao gồm thời gian xuất hóa đơn.
Ứng dụng có module Inventory gọi Payment qua facade không công khai; graph test báo lỗi phụ thuộc trong khi runtime spans cho thấy đường gọi đang phục vụ nhiều khách quan trọng.
Đội muốn chứng minh mọi thông điệp event đã được xử lý; trace retention ngắn, registry chỉ giữ trạng thái cuối và không đủ bằng chứng lịch sử đối soát dài hạn.
Nhóm giám sát một bản canary với module graph mới; metrics cùng tên module bị trộn giữa canary và stable khiến không thể đánh giá tác động của thay đổi ranh giới.
Ứng dụng có một listener lỗi do dữ liệu cũ trong quá trình migration; pending events tăng nhưng log trace không còn business correlation ID và không xác định được khách bị ảnh hưởng.
Đội công bố kết quả kiểm tra application module cho đối tác; sơ đồ chứa phụ thuộc nội bộ và các thông số hạ tầng chỉ dành cho nhân viên khiến việc chia sẻ tài liệu cần được xem xét.
Nhóm cần theo dõi tính nhất quán từ module graph tới runtime traces; một tương tác được thực hiện qua reflection không hiện trên sơ đồ nhưng gây chậm đáng kể khi giao dịch tăng.
Ứng dụng bật Actuator và observability sau một release; dashboard chỉ có dữ liệu từ các pod mới nên thông tin về lỗi xảy ra trước thời điểm bật telemetry vẫn chưa có.
Đội xây playbook khôi phục event publication bị lỗi; các nhánh async có transaction và context khác nhau làm một lần replay không tái hiện đúng dấu vết quan sát ban đầu.
Nhóm tổng kết sự cố cross-module cuối tháng bằng diagram, metrics và traces; ba nguồn dùng mã release, tên module và cửa sổ thời gian khác nhau nên không thể xác lập đầy đủ chuỗi nguyên nhân.
