Một nền tảng Cloud Foundry đăng ký service broker viết bằng Spring Cloud; yêu cầu đọc catalog thành công ở môi trường thử nghiệm nhưng production từ chối vì broker không xử lý đúng header phiên bản Open Service Broker API.
Nhóm cung cấp cơ sở dữ liệu dịch vụ công bố catalog chứa hai service plan; sau khi cập nhật bản phát hành, plan ID bị thay đổi dù tên plan giữ nguyên và các service instance đã cấp trước đó không còn đối chiếu được.
Một broker cung cấp cả dịch vụ Redis và PostgreSQL trong cùng catalog; sau khi thêm sản phẩm thứ ba, hai service vô tình dùng trùng service ID khiến nền tảng không thể đăng ký catalog.
Đội phát triển dùng mô tả service plan làm khóa nghiệp vụ trong hệ thống billing; khi phòng sản phẩm đổi tên plan hiển thị, nhiều instance bị gán sang gói giá khác.
Một broker công bố plan giá thấp là miễn phí ở metadata, nhưng backend lại tính phí theo dung lượng thực tế khiến thông tin người dùng thấy trên marketplace không khớp hóa đơn.
Ứng dụng cung cấp dịch vụ lưu trữ xuất catalog với cờ cho phép binding; khi tạo binding, broker thực tế chưa hỗ trợ cấp credential nên thao tác liên tục thất bại sau khi provision thành công.
Nhóm quản trị công bố service plan yêu cầu tham số vùng triển khai; trong schema của catalog trường region không được đánh dấu bắt buộc khiến platform gửi request thiếu dữ liệu vẫn vượt bước kiểm tra.
Một broker cung cấp tham số provisioning dưới dạng JSON Schema; sau khi thêm giá trị enum mới cho cỡ máy, giao diện marketplace chỉ cho phép lựa chọn cũ dù backend đã hỗ trợ.
Đội tích hợp thêm giá trị mặc định vào parameter schema của service plan; platform và broker diễn giải mặc định khác nhau làm hai tài nguyên cùng plan có cấu hình khác nhau.
Một nhà cung cấp muốn ẩn service plan thử nghiệm khỏi người dùng thông thường; catalog vẫn hiển thị plan đó trên nền tảng khách hàng vì điều kiện hiển thị chưa được phân biệt rõ.
Nhóm dùng một catalog cho nhiều vùng địa lý; plan có mặt tại vùng châu Á nhưng backend vùng châu Âu chưa hỗ trợ, khiến khách đăng ký thành công rồi thất bại khi provisioning.
Broker cập nhật metadata hiển thị logo và tài liệu hỗ trợ; URL trỏ tới miền nội bộ không truy cập được từ Cloud Foundry nên marketplace bị thiếu thông tin dịch vụ.
Một sản phẩm được khai báo có hỗ trợ cập nhật service plan; khi người dùng nâng cấp, backend từ chối thay đổi dù catalog vẫn quảng bá khả năng cập nhật.
Nhóm phát hành catalog mới bằng một bản deploy độc lập với broker; trong thời gian rolling update, các replica trả về danh sách service plan không giống nhau cho cùng yêu cầu.
Đội kiểm thử chỉ xác minh catalog là JSON hợp lệ; một service plan bị thiếu trường định danh ổn định khiến platform báo lỗi khi đăng ký dù endpoint trả HTTP 200.
Một tổ chức cần thu hồi plan cũ khỏi danh sách bán mới nhưng vẫn quản lý instance đã cấp phát; việc xóa plan khỏi catalog khiến nhiều tác vụ lifecycle của instance đang chạy gặp trở ngại.
Nhóm cung cấp service broker xây endpoint catalog với thông tin dựa trên database; khi database cấu hình chậm, yêu cầu đọc catalog của platform bị timeout và toàn bộ dịch vụ bị đánh dấu không khả dụng.
Một marketplace đa ngôn ngữ hiển thị mô tả dịch vụ bằng tiếng Việt; catalog trả nội dung với encoding không nhất quán khiến tên gói có dấu bị hiển thị sai.
Dịch vụ cấp phát PostgreSQL nhận PUT cho một service instance mới; broker ghi nhận metadata instance nhưng tác vụ tạo database không bắt đầu, trong khi platform đã nhận phản hồi thành công.
Nhóm triển khai sử dụng service instance ID do Cloud Foundry gửi để liên kết tài nguyên; sau một lần tái cấu trúc, backend tự sinh ID khác khiến thao tác xóa theo ID platform không tìm thấy database.
Một broker nhận request provision chứa service_id và plan_id hợp lệ nhưng thiếu organization_guid; hệ thống vẫn cấp tài nguyên và không biết phải quy chiếu quota cho tổ chức nào.
Ứng dụng cấp bucket lưu trữ nhận tham số tên bucket người dùng chọn; hai service instance khác nhau yêu cầu cùng tên và một request vô tình sử dụng bucket của khách khác.
Một nhà cung cấp Redis áp giới hạn tổng dung lượng theo tổ chức; hai yêu cầu provisioning đồng thời đều vượt qua kiểm tra quota ban đầu và cùng tạo tài nguyên vượt mức cho phép.
Broker cấp database trong vùng được chọn qua tham số region; khi một vùng tạm hết công suất, phản hồi của broker không thể hiện rõ liệu tài nguyên đã được tạo ở vùng dự phòng hay chưa.
Một nền tảng gửi lại PUT provision sau timeout mạng; request đầu tiên đã tạo database, nhưng lượt thứ hai bắt đầu một tác vụ tạo mới khác và gây cấp phát trùng.
Đội phát triển thay đổi cách chuẩn hóa provisioning parameters; hai request có cùng instance ID nhưng bộ tham số khác nhau bị broker coi là giống hệt và trả thành công với cấu hình không đúng.
Một service broker nhận cùng PUT provision từ hai replica platform gần như đồng thời; không có kiểm soát cạnh tranh nên hai backend worker cùng tạo tài nguyên cho một instance ID.
Nhà cung cấp cơ sở dữ liệu cho phép tạo instance với dung lượng lưu trữ nhỏ; giá trị trong request vượt giới hạn plan nhưng API trả thành công rồi backend dừng ở bước cấp phát ổ đĩa.
Một request provisioning chứa thông tin network CIDR dưới dạng chuỗi; backend chỉ gặp lỗi khi tạo VPC vì giá trị vượt vùng mạng cho phép dù hợp đồng plan chưa phát hiện.
Nhóm cấp phát cluster theo một bộ tham số JSON có trường lồng nhau; sau khi nâng thư viện binding, danh sách node bị đọc thành rỗng và instance được tạo với topology khác yêu cầu.
Một broker triển khai cho nhiều tenant sử dụng context từ platform; một request được xử lý bằng context còn lưu trong thread của tenant trước làm resource bị gắn nhầm chủ sở hữu.
Dịch vụ broker trả mã lỗi chung khi người dùng hết quota; giao diện platform không thể phân biệt lỗi cấu hình đầu vào và lỗi giới hạn tài nguyên để hiển thị thông điệp phù hợp.
Một tổ chức yêu cầu môi trường production không cấp phát dịch vụ thử nghiệm; broker chỉ kiểm tên plan mà không đối chiếu không gian triển khai nên resource không phù hợp vẫn được tạo.
Nhóm triển khai provisioning qua API của nhà cung cấp cloud; API trả timeout sau khi thực hiện thành công và broker đánh dấu request thất bại dù tài nguyên thực đã tồn tại.
Một ứng dụng broker khởi động tác vụ tạo database mất mười lăm phút; platform chỉ cho phép chờ phản hồi HTTP trong thời gian ngắn nên request đồng bộ thường bị đóng kết nối.
Đội phát triển hỗ trợ provisioning bất đồng bộ nhưng vẫn trả phản hồi cho biết hoàn tất ngay khi tác vụ mới được đưa vào queue; người dùng bind vào instance chưa sẵn sàng và nhận lỗi.
Một service plan cần nhiều bước thiết lập mạng và database; sau khi bước mạng hoàn thành nhưng bước database thất bại, trạng thái tài nguyên trung gian không rõ có cần được coi là đã provision.
Broker cấp phát một cluster lớn cần thao tác bất đồng bộ; request platform không thể hiện chấp nhận incomplete nhưng backend vẫn bắt đầu tác vụ dài rồi trả phản hồi trái với kỳ vọng phía gọi.
Một request provision bất đồng bộ nhận được token operation; khi platform dùng token này để gọi last_operation, broker không tìm thấy trạng thái vì task đã chuyển sang hệ thống queue khác.
Nhóm phát triển tạo operation token từ ID worker tạm thời; sau khi worker restart, platform tiếp tục polling last_operation nhưng token không còn ánh xạ tới tác vụ cũ.
Một backend đang tạo database nhưng last_operation luôn trả trạng thái in progress; tài nguyên thực đã hoạt động từ lâu và người dùng không thể bind vì platform chưa nhận được tín hiệu hoàn tất.
Dịch vụ provisioning thất bại do vượt quota giữa chừng; last_operation báo succeeded từ một bước phụ nên platform coi instance khả dụng dù database chưa tồn tại.
Broker trả last_operation với trạng thái failed nhưng thiếu mô tả có ích; đội vận hành phải tra nhiều hệ thống để xác định vì sao tác vụ cấp phát đã dừng.
Một platform polling last_operation với tần suất cao trên hàng nghìn instance; broker mỗi lần lại truy vấn trực tiếp API cloud làm hệ thống giám sát và giới hạn request của nhà cung cấp bị quá tải.
Nhóm điều phối tác vụ provisioning trên queue có cơ chế at-least-once; sau khi worker bị khởi động lại, cùng message được giao lại và hai nhánh cùng thay đổi trạng thái một instance.
Một tác vụ tạo cluster chạy quá thời gian giữ task record trong database; last_operation báo không tồn tại mặc dù resource bên cloud đang tiếp tục được tạo.
Đội vận hành triển khai bản broker mới trong lúc hàng trăm thao tác bất đồng bộ đang chạy; version mới không đọc được dữ liệu trạng thái của version cũ nên polling đồng loạt thất bại.
Một service instance được ghi là succeeded ngay trước khi cấu hình firewall hoàn tất; các ứng dụng sử dụng dịch vụ liên tục gặp connection refused trong vài phút đầu.
Nhóm thiết kế tác vụ provisioning có bước cần được phê duyệt thủ công; platform tiếp tục polling mà không biết yêu cầu đã chờ xác nhận nhiều ngày.
Một broker cung cấp endpoint đọc thông tin service instance để hỗ trợ truy vấn; tài nguyên bị sửa trực tiếp trong cloud console làm dữ liệu trả về khác với thông tin đã lưu lúc cấp phát.
Dịch vụ cho phép đổi service plan từ basic sang premium; request update được nhận nhưng dung lượng database tăng còn số lượng replica vẫn giữ theo plan cũ.
Một khách hàng yêu cầu giảm dung lượng lưu trữ trong PATCH update; broker bắt đầu thay đổi dù backend không hỗ trợ thu nhỏ volume và tác vụ kết thúc thất bại sau thời gian dài.
Nhóm cung cấp Redis đổi cấu hình maxmemory thông qua parameters update; broker chỉ lưu JSON mới mà chưa đồng bộ giá trị tới cluster đang chạy.
Một bản cập nhật service instance thay đổi region của tài nguyên; backend tạo cluster mới ở vùng khác nhưng ứng dụng đang binding vẫn giữ endpoint cũ và bị ngắt kết nối.
Broker cho phép nâng plan mà không ngừng dịch vụ; sau khi triển khai, thao tác update một instance đang có nhiều binding làm credential của các ứng dụng mất hiệu lực.
Một service plan đánh dấu có hỗ trợ update nhưng broker chỉ kiểm plan_id và bỏ qua parameters thay đổi; platform báo thành công dù yêu cầu sửa backup policy không có tác dụng.
Nhóm nhận hai PATCH update liên tiếp cho cùng instance; tác vụ nâng cấp còn chạy thì tác vụ hạ cấp bắt đầu và trạng thái cuối cùng không tương ứng yêu cầu mới nhất.
Đội vận hành dùng service broker để thay đổi số node cluster; khi một worker bị lỗi giữa update, platform chỉ thấy trạng thái in progress mà không biết còn bao nhiêu node đang chạy.
Một broker kiểm tra plan mới theo tên hiển thị thay vì ID; khi nhiều plan có tên tương tự, yêu cầu nâng cấp bị áp cấu hình nhầm gói.
Ứng dụng đã provision với thông số mã hóa bắt buộc; PATCH update nhận parameters mới không kèm trường cũ và broker vô tình vô hiệu hóa chính sách bảo vệ dữ liệu.
Nhóm mở rộng hỗ trợ update ở một số service plan nhất định; platform gửi PATCH tới plan không cho phép và nhận response không giải thích được giới hạn thay đổi.
Dịch vụ update configuration thành công trên backend nhưng phản hồi HTTP về platform mất do sự cố mạng; platform gửi lại request và broker chạy lại thao tác có thể gây downtime.
Một thao tác update bất đồng bộ sử dụng last_operation giống provisioning; broker không phân biệt các lần update nối tiếp nên platform đọc kết quả của thao tác trước.
Nhóm dịch vụ muốn khôi phục cấu hình sau update thất bại; broker chỉ còn thông số mong muốn mới trong database và không lưu được phiên bản cấu hình đang hoạt động.
Một platform gửi request deprovision cho instance đã bị xóa thủ công từ cloud console; broker báo lỗi chung và nền tảng không thể dọn mục dịch vụ khỏi không gian làm việc.
Đội phát triển triển khai DELETE service instance chỉ xóa record trong database broker; tài nguyên cloud và phí lưu trữ vẫn phát sinh sau khi user xóa dịch vụ.
Một broker bắt đầu xóa database trước khi kiểm tra các binding đang tồn tại; ứng dụng đang sử dụng mất kết nối mà không có giai đoạn gỡ binding phù hợp.
Dịch vụ lưu trữ thực hiện deprovision bằng tác vụ mất nhiều giờ; phản hồi ban đầu báo hoàn tất dù bucket vẫn còn dữ liệu, khiến bộ phận tài chính dừng tính phí quá sớm.
Nhóm triển khai xóa cluster Kubernetes do broker cấp; một finalizer bị treo làm tài nguyên còn trạng thái terminating nhiều ngày trong khi last_operation không cập nhật được.
Một request DELETE đến hai lần sau retry của platform; lượt thứ hai trả lỗi không rõ ý nghĩa dù lượt đầu đã hoàn tất xóa tài nguyên.
Nhóm cấp phát cơ sở dữ liệu có backup theo ngày; khi deprovision, backend xóa database nhưng các snapshot còn tồn tại và vi phạm chính sách xóa dữ liệu khách hàng.
Một service instance có nhiều resource phụ như VPC, volume và DNS; bước xóa VPC bị chặn bởi network interface còn tồn tại khiến toàn bộ deprovision dở dang.
Đội vận hành mất kết nối tới nhà cung cấp cloud giữa lúc deprovision; broker không biết cluster đã bị xóa hay chưa và một tác vụ xóa lại có thể tác động nhầm resource khác.
Broker nhận DELETE với service_id hoặc plan_id không trùng dữ liệu đang lưu; code xử lý dựa vào tham số của platform và định xóa tài nguyên không thuộc instance mục tiêu.
Nhóm vận hành đang nâng cấp plan cho một instance thì người dùng yêu cầu deprovision; hai luồng cập nhật và xóa chạy đồng thời làm phát sinh resource mồ côi.
Một service broker đóng quyền truy cập tài nguyên ngay khi nhận DELETE; tác vụ sao lưu dữ liệu trước xóa vẫn đang chạy và không thể đọc database để hoàn thành.
Đội phát triển chỉ thử deprovision của instance đã tạo thành công; một instance provision thất bại nửa chừng không thể được dọn vì trạng thái nội bộ không cho phép xóa.
Một service plan có tùy chọn giữ dữ liệu khi xóa; broker áp chính sách giữ dữ liệu không đồng đều giữa các vùng và nền tảng không biết dữ liệu nào còn tồn tại.
Nhóm viết cleanup job định kỳ cho resource thất bại; tác vụ dọn rác xóa nhầm instance vừa được provision lại do ID tài nguyên được tái sử dụng.
Một ứng dụng Cloud Foundry muốn bind service instance PostgreSQL vào app; broker trả credentials nhưng username không tồn tại trong database do bước tạo user chưa hoàn tất.
Nhóm cung cấp service plan khai báo có hỗ trợ binding; request PUT binding nhận thành công nhưng broker không lưu binding ID nên thao tác unbind sau đó không thể thu hồi quyền.
Một platform gửi lại PUT binding sau timeout; broker tạo thêm một user database mỗi lần và không nhận biết đó là cùng binding ID.
Dịch vụ cấp binding theo scope chỉ đọc; broker trả credentials của tài khoản có quyền ghi làm ứng dụng tiêu thụ sở hữu đặc quyền vượt yêu cầu.
Một service instance có năm ứng dụng cùng bind; broker dùng chung một tài khoản database nên không thể thu hồi riêng quyền của một ứng dụng khi nó ngừng sử dụng.
Nhóm cấp phát API token khi binding; token được đặt trực tiếp trong log request/response của broker và xuất hiện trong hệ thống quan sát có nhiều người truy cập.
Một ứng dụng Spring Cloud yêu cầu binding có tham số tên schema riêng; broker bỏ qua parameters của binding và cấp credentials truy cập schema mặc định.
Đội phát triển sửa cấu trúc credential trả về từ binding; ứng dụng đã triển khai vẫn tìm trường uri cũ và không thể tạo kết nối dù thông tin username, password mới hợp lệ.
Một dịch vụ trả credentials chứa dấu đặc biệt trong password và URL; khi ứng dụng nhận binding data, connection string không được diễn giải nhất quán giữa các runtime.
Nhóm cung cấp message broker cho app trên Cloud Foundry; binding chỉ chứa endpoint nội bộ của region đang cấp phát và ứng dụng chuyển region không thể kết nối.
Broker cấp binding với quyền giới hạn theo tenant; một lỗi ở bước mapping context khiến ứng dụng tenant A nhận credential đọc tài nguyên tenant B.
Một platform gửi app_guid trong request binding; broker dùng app_guid làm resource ID duy nhất và không hỗ trợ cùng app tạo hai binding độc lập với cùng instance.
Nhóm tích hợp hỗ trợ service key không gắn trực tiếp với app; broker chỉ xử lý binding có app_guid nên yêu cầu tạo khóa truy cập độc lập bị từ chối.
Một binding được tạo thành công nhưng response bị mất; khi platform retry, broker trả credentials khác cho cùng binding ID và ứng dụng vẫn giữ token cũ.
Đội vận hành xoay vòng mật khẩu database; binding cũ trong platform vẫn hiển thị credential đã bị thu hồi trong khi app chưa được cập nhật secret mới.
Một broker thực hiện unbind rồi lập tức xóa user database; ứng dụng đang có connection pool vẫn tiếp tục gửi giao dịch và nhận lỗi xác thực đột ngột.
Nhóm triển khai DELETE binding chỉ xóa thông tin nội bộ; quyền IAM đã cấp cho app vẫn tồn tại trong cloud và có thể bị lạm dụng sau khi unbind.
Một platform gửi unbind hai lần cho cùng binding ID do retry; broker coi yêu cầu thứ hai là lỗi chưa xử lý khiến quy trình thu hồi service instance bị treo.
Đội kỹ thuật nâng cấp binding từ credentials dạng username/password sang token ngắn hạn; consumer vẫn dùng cách đọc dữ liệu cũ nên không kết nối được sau deploy.
Một service broker hỗ trợ binding bất đồng bộ đối với tài nguyên phức tạp; platform dùng cách gọi đồng bộ cũ khiến trạng thái ứng dụng và quyền IAM không được theo dõi nhất quán.
Nhóm hỗ trợ muốn đọc thông tin binding đã tạo để kiểm tra lỗi; broker không có đường truy vấn phù hợp và platform không thể đối chiếu ID, credentials và quyền thực tế.
Một service instance được deprovision trong lúc binding vẫn đang cấp quyền; worker binding hoàn tất muộn và tạo credential trỏ tới tài nguyên đã bị xóa.
Đội phát triển trả endpoint private network trong binding; ứng dụng ở space khác không có định tuyến mạng đến endpoint và thất bại dù binding được đánh dấu thành công.
Một ứng dụng sử dụng volume service qua broker; binding nhận thông tin mount nhưng đường dẫn volume được tái sử dụng giữa hai app và dẫn tới ghi đè dữ liệu.
Broker trả binding response có dữ liệu credential nhạy cảm khi lỗi xảy ra; reverse proxy ghi nguyên body của HTTP response vào access log để chẩn đoán.
Đội cung cấp dịch vụ yêu cầu Basic Authentication cho Open Service Broker API; sau khi xoay mật khẩu broker ở Cloud Foundry, một phần replica vẫn dùng credential cũ và bị từ chối.
Một service broker chạy sau API Gateway và nhận thêm header X-Forwarded-User; một endpoint vô tình tin header do client tự gửi thay vì danh tính đã xác thực của platform.
Nhóm bảo mật cấu hình endpoint catalog dùng auth nhưng các endpoint provisioning lại thiếu kiểm tra quyền; người ngoài có thể gửi lệnh cấp tài nguyên nếu biết URL.
Một broker công khai qua TLS nhưng dùng chứng chỉ hết hạn ở môi trường production; Cloud Foundry từ chối các yêu cầu lifecycle dù dashboard ứng dụng vẫn báo tiến trình khỏe.
Đội triển khai yêu cầu mutual TLS giữa platform và broker; khi thay chứng chỉ client ở cluster, broker chỉ chấp nhận các node dùng CA cũ và request bị lỗi ngẫu nhiên.
Nhóm lưu secret truy cập cloud provider trong application.yml đóng gói chung JAR; nhà phát triển không có quyền vận hành production vẫn xem được khóa cấp phát resource.
Một broker đọc access token từ Kubernetes Secret lúc khởi động; secret được rotate trên cluster nhưng service vẫn dùng token cũ để gọi cloud API và lỗi cấp phát.
Đội vận hành bật HTTP request logging để điều tra lỗi provision; body request chứa thông số hệ thống riêng tư của khách hàng được đẩy vào nền tảng log dùng chung.
Một service broker đa tenant xác định quyền dựa trên organization_guid trong body; client có thể giả mạo trường này nếu không có ràng buộc với danh tính nền tảng gọi API.
Nhóm cấp service binding cho ứng dụng chưa được xác thực rõ ràng; credentials được trả cho request có binding ID hợp lệ nhưng không thuộc tổ chức đã tạo instance.
Broker đặt hạn mức request toàn cục cho API; trong đợt deploy nhiều ứng dụng, platform polling bất đồng bộ làm hết quota và những request deprovision cần thiết không được xử lý.
Một broker triển khai trên Kubernetes phải nhận PUT provision từ hệ thống quản lý catalog; sau khi đổi cấu hình ingress, request được chuyển đến route không giữ nguyên service instance ID.
Nhóm tích hợp Open Service Broker API với nền tảng Kubernetes theo cơ chế service catalog; resource được yêu cầu trong namespace này nhưng credential xuất hiện ở namespace khác.
Một môi trường Kubernetes sử dụng service plan được công bố từ broker; RBAC của người dùng cho phép tạo service instance nhưng không cho đọc Secret binding để ứng dụng truy cập.
Đội triển khai broker ở nhiều cụm Kubernetes; cùng một instance ID được gửi từ hai cụm nhưng broker chỉ có namespace khóa định danh chung và cập nhật nhầm tài nguyên.
Một service broker tạo database ngoài cụm cho ứng dụng Kubernetes; namespace bị xóa nhưng thao tác cleanup chưa gửi tới broker và database tiếp tục phát sinh phí.
Nhóm Cloud Foundry chuyển ứng dụng qua space khác; service instance đã tồn tại nhưng quyền gắn vào app mới và các metadata space trong broker chưa được đồng bộ.
Một doanh nghiệp đăng ký cùng broker ở hai nền tảng Cloud Foundry khác nhau; request cùng service ID và instance ID hiếm gặp làm dữ liệu lifecycle của hai nền tảng bị trộn.
Đội vận hành đổi URL broker đã đăng ký trong marketplace; các thao tác catalog chạy qua URL mới nhưng một số pipeline nền tảng còn gọi endpoint cũ để deprovision.
Nhóm triển khai Blue-Green cho service broker; task trạng thái bất đồng bộ lưu trong bộ nhớ cục bộ khiến poll qua replica mới trả không tìm thấy operation.
Một broker mất kết nối JobRepository lưu trạng thái provisioning trong vài phút; worker vẫn tạo tài nguyên ngoài cloud nhưng platform không nhận được kết quả trong lần polling kế tiếp.
Đội phát triển dùng cache cho catalog với TTL dài; sau khi ngừng bán một plan rủi ro, platform tiếp tục cho phép yêu cầu instance mới dựa trên catalog cũ.
Một backend resource API trả lỗi 429 khi số lượt provisioning tăng; broker liên tục retry không có giới hạn và kéo dài trạng thái in progress trên hàng trăm instance.
Nhóm vận hành đo latency trung bình của endpoint broker; request provisioning trả nhanh 202 nhưng thời gian tạo cluster phía sau mất hàng giờ nên dashboard vẫn báo hiệu năng tốt.
Đội kiểm toán cần biết ai đã tạo, cập nhật và xóa mỗi service instance; log broker chỉ ghi instance ID mà không lưu correlation ID và ngữ cảnh request từ platform.
Một broker phân tán trace giữa API ingress, hàng đợi tác vụ và cloud provider; correlation ID bị mất sau khi task được enqueue khiến sự cố tạo tài nguyên không thể lần theo toàn bộ chuỗi.
Nhóm metrics gắn instance ID vào tất cả nhãn Prometheus; sau khi số lượng instance tăng lớn, số time series và chi phí lưu trữ metrics vượt dự toán.
Ứng dụng cấp tài nguyên chạy trong container có readiness probe chỉ kiểm HTTP; broker báo sẵn sàng dù queue worker và database lưu operation đang mất kết nối.
Một broker có liveness probe phụ thuộc trực tiếp cloud provider; sự cố mạng ngắn khiến Kubernetes restart broker liên tục trong khi trạng thái task cần được bảo toàn.
Đội triển khai tăng số replica broker để chịu tải; hai replica cùng nhận xử lý một operation chưa có lock và cùng thao tác lên resource cloud.
Nhóm kiểm thử chỉ xác minh request provision thành công; khi Cloud Foundry retry PUT cùng ID do timeout, hệ thống tạo hai database nhưng bộ test không phát hiện.
Một bộ integration test dùng stub cloud API luôn trả thành công; các tình huống provider đã tạo tài nguyên nhưng trả timeout không được kiểm thử và hệ thống sinh resource mồ côi.
Đội QA kiểm thử catalog và plan theo dữ liệu mẫu tĩnh; khi plan bị rút khỏi marketplace, bộ test không phát hiện instance cũ vẫn cần hỗ trợ update và deprovision.
Nhóm chạy contract test cho endpoint binding nhưng chỉ kiểm status code; credential trả về thiếu trường mà ứng dụng Cloud Foundry cần nên integration test app thất bại.
Một service broker được kiểm thử trong môi trường không có nhiều người dùng; trên production hai request PATCH và DELETE đến đồng thời gây race condition không xuất hiện trong CI.
Đội kỹ thuật kiểm thử last_operation bằng một tác vụ hoàn thành ngay; khi tác vụ thật kéo dài nhiều phút, token operation hết hạn và platform không thể xác định kết quả.
Một bộ test giả lập platform luôn gửi accepts_incomplete; khi khách dùng bản platform khác không gửi cờ này, broker vẫn bắt đầu thao tác lâu và trả phản hồi không tương thích.
Nhóm phát triển nâng phiên bản Spring Cloud Open Service Broker; một sự thay đổi mapping request ở nhánh update khiến parameters có cấu trúc nested bị bỏ sót dù test thông thường đạt.
Đội QA chạy test unbind sau khi provision hoàn tất nhưng không thử binding bị lỗi nửa chừng; credential đã được tạo vẫn có thể dùng dù platform coi binding thất bại.
Một broker hỗ trợ nhiều service plan khác nhau ở các vùng; bộ kiểm thử chỉ dùng vùng mặc định nên không phát hiện plan được công bố nhưng không cấp được ở một vùng sản xuất.
Nhóm vận hành rollback broker sau khi phát hiện lỗi cấp phát; phiên bản cũ không hiểu schema trạng thái operation do bản mới ghi nên các tác vụ đang chạy không thể tiếp tục.
Đội tài chính đối soát hàng tháng giữa database broker và cloud provider; nhiều tài nguyên hiện tồn tại nhưng không có service instance tương ứng, tạo chi phí không được phân bổ.
Một service instance bị xóa khỏi platform sau thao tác deprovision; cloud API chậm cập nhật trạng thái khiến công cụ kiểm toán nhầm tài nguyên đang xóa với tài nguyên mồ côi.
Nhóm quản lý tenant thu hồi quyền sử dụng plan premium; các binding cũ vẫn truy cập tài nguyên và broker chưa thể hiện rõ quyền nào đang tồn tại sau khi quyền thuê bao thay đổi.
Một doanh nghiệp cần chuyển tài nguyên đã provision từ vùng chính sang vùng dự phòng; platform gửi update theo plan hiện có nhưng backend cần nhiều bước và không phản ánh trạng thái từng giai đoạn.
Trong lần nâng cấp Cloud Foundry, platform thay phiên bản OSB API mà broker hỗ trợ; catalog vẫn trả được nhưng một yêu cầu lifecycle có trường mới không được ánh xạ và không thể cấp phát tài nguyên.
Đội vận hành khôi phục database lưu trạng thái broker từ snapshot cũ; task worker và resource cloud đã tiến xa hơn checkpoint nên cùng instance có ba trạng thái khác nhau cần được đối chiếu.
