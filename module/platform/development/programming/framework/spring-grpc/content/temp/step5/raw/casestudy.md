Một hệ thống đặt hàng có hai ứng dụng Spring gRPC dùng chung hợp đồng .proto, nhưng server đổi số field của orderId khi nâng phiên bản khiến client cũ diễn giải dữ liệu không đúng.
Nhóm thêm trường bắt buộc về nghiệp vụ vào request Protobuf nhưng khách hàng đang chạy ứng dụng cũ không gửi field mới, khiến server nhận giá trị mặc định không thể phân biệt với đầu vào hợp lệ.
Ứng dụng đổi kiểu của một field Protobuf từ int32 sang string mà vẫn giữ field number, khiến các message lưu trong hàng đợi từ phiên bản trước không còn tương thích khi đọc.
Đội xóa một field đã ngừng sử dụng khỏi .proto rồi tái sử dụng cùng field number cho dữ liệu khác, khiến bản client cũ và mới hiểu nội dung khác nhau trong rolling deployment.
Một service đổi tên package của định nghĩa Protobuf để sắp xếp repository, khiến tên service gRPC đầy đủ mà hệ thống định tuyến đang sử dụng thay đổi ngoài dự tính.
Nhóm chuyển java_package trong .proto nhưng không cập nhật module Java tiêu thụ mã được sinh, khiến một nhánh ứng dụng còn tham chiếu tới các class của package trước.
Ứng dụng cấu hình java_multiple_files khác giữa hai bản hợp đồng, khiến code Java cũ mong class lồng không còn khớp với kết quả protobuf code generation.
Đội phát hành hợp đồng .proto có import file dùng chung nhưng pipeline build của một đối tác không có đường dẫn import tương ứng, khiến bước sinh mã Java thất bại.
Một service sử dụng hai phiên bản khác nhau của protoc và protobuf runtime giữa server và client, khiến lỗi build chỉ xuất hiện ở nhánh tích hợp cuối cùng.
Nhóm cập nhật plugin sinh Java gRPC stub nhưng vẫn giữ dependency runtime gRPC phiên bản cũ, khiến ứng dụng biên dịch được ở một module và thất bại ở module còn lại.
Ứng dụng quản lý file .proto trong nhiều repository độc lập, khiến cùng một message được sinh mã với các field number khác nhau dù tên Java giống hệt.
Đội gộp hai service Protobuf vào một file rồi đổi tên RPC, khiến client đã triển khai tiếp tục gọi tên method cũ và nhận trạng thái không tìm thấy phương thức.
Một hệ thống dùng enum trạng thái vận chuyển nhưng không có giá trị UNKNOWN ở số 0, khiến field không được client cũ gửi bị hiểu thành trạng thái nghiệp vụ cụ thể.
Nhóm bổ sung enum value mới cho loại thanh toán, khiến client cũ nhận giá trị chưa biết và logic hiển thị mặc định không đáp ứng yêu cầu tài chính.
Ứng dụng đổi một field thông thường thành oneof trong message yêu cầu, khiến client gửi đồng thời hai lựa chọn từ SDK cũ và server chỉ nhìn thấy một giá trị.
Đội dùng oneof để biểu diễn tài khoản cá nhân hoặc doanh nghiệp nhưng một request không chọn nhánh nào vẫn được xử lý, khiến quy trình tạo hợp đồng thiếu thông tin định danh.
Một service dựa vào giá trị int32 bằng 0 để xác định người dùng có gửi số lượng hay không, khiến request đặt đúng 0 sản phẩm và request thiếu field không được phân biệt.
Nhóm thêm proto3 optional cho một field giá chiết khấu nhưng các phiên bản mã sinh cũ xử lý sự hiện diện của field khác nhau, khiến validation không thống nhất.
Ứng dụng nhận Timestamp Protobuf từ các múi giờ khác nhau nhưng một DTO Java tự chuyển sang giờ local, khiến cùng một giao dịch được hiển thị vào hai ngày khác nhau.
Đội chuyển LocalDate nghiệp vụ thành Timestamp tại đầu ngày UTC, khiến ngày sinh hoặc ngày giao hàng không có timezone bị dịch khi client ở vùng khác.
Một service dùng google.protobuf.Duration cho timeout nghiệp vụ nhưng client cũ gửi thời lượng theo milliseconds trong field số nguyên, khiến giá trị mới bị diễn giải sai đơn vị.
Nhóm dùng google.protobuf.Any để chứa sự kiện nhiều loại nhưng client Java không có message type mới trong dependency, khiến dữ liệu nhận được không thể unpack.
Ứng dụng biểu diễn tiền tệ bằng double trong message Protobuf, khiến phép làm tròn không nhất quán giữa các service khi tính tổng hóa đơn giá trị lớn.
Đội thêm FieldMask cho RPC cập nhật hồ sơ nhưng client gửi một mask không khớp các field có trong payload, khiến tài nguyên được sửa khác những gì UI hiển thị.
Một service dùng map<string,string> cho metadata nghiệp vụ nhưng một khách gửi key khác cách viết hoa, khiến quy tắc đọc Map ở hai ngôn ngữ client cho kết quả khác.
Nhóm đổi repeated field thành một message wrapper nhưng vẫn giữ field number, khiến dữ liệu cũ không được decode thành danh sách đơn hàng như trước.
Ứng dụng cần phản ánh dữ liệu không biết từ client mới nhưng một gateway deserialize rồi serialize qua DTO trung gian, khiến unknown fields của Protobuf bị mất.
Đội thêm chuỗi mô tả dài vào message trả về nhưng giới hạn kích thước response của một client gRPC không thay đổi, khiến lỗi chỉ xuất hiện với sản phẩm có nhiều thuộc tính.
Một service hỗ trợ nhiều quốc gia gửi tên Unicode qua Protobuf string nhưng tầng chuyển đổi Java cũ dùng sai normalization, khiến đối soát tên khách không ổn định.
Nhóm muốn dùng reserved field numbers cho các trường đã loại bỏ nhưng một bản .proto mới vô tình khai báo lại tên cũ, khiến schema compatibility check của pipeline thất bại.
Ứng dụng dùng proto service name để phân quyền từ gateway nhưng đổi package hợp đồng mà không điều chỉnh policy, khiến một nhóm RPC mới bị từ chối sau rollout.
Đội gắn tài liệu hợp đồng riêng với .proto nhưng không cập nhật semantic version khi đổi hành vi default, khiến đối tác không dự đoán được tác động dù wire format vẫn đọc được.
Một service dùng message Protobuf cho báo cáo có nhiều bản ghi lồng nhau, nhưng response vượt giới hạn memory parser của client khi khách yêu cầu toàn bộ dữ liệu lịch sử.
Nhóm sinh mã Java từ .proto trong cả Maven và Gradle ở hai module nhưng cấu hình plugin khác nhau, khiến các lớp stub có API khác nhau khi được ghép vào một ứng dụng.
Ứng dụng cập nhật protobuf schema trên server trước khi thư viện Java client được phát hành, khiến một RPC mới chạy được trong môi trường nội bộ nhưng client đối tác chưa thể gọi.
Đội duy trì hợp đồng gRPC cho Java và Go nhưng thêm một field có tên trùng từ khóa ở client khác, khiến mã sinh của một nền tảng không có API như tài liệu Java đang mô tả.
Một dịch vụ Spring đăng ký implementation gRPC trong ApplicationContext nhưng server chưa nhận bean service đó, khiến các RPC khác hoạt động mà method mới trả UNIMPLEMENTED.
Nhóm dùng hai bean gRPC server triển khai cùng service name để thử nghiệm A/B, khiến registry dịch vụ tại startup không thể xác định phương thức nào được công bố.
Ứng dụng có gRPC service implementation phụ thuộc bean khởi tạo trong profile thử nghiệm, khiến server startup production không có đủ dependency để đăng ký RPC.
Đội di chuyển gRPC implementation sang một package mới ngoài component scan, khiến server vẫn mở cổng nhưng RPC nghiệp vụ không được tìm thấy.
Một service dùng Spring gRPC server cùng ứng dụng HTTP và đổi cấu hình port, khiến load balancer chuyển traffic gRPC sang cổng REST không hỗ trợ HTTP/2.
Nhóm chạy nhiều server gRPC trong cùng JVM với địa chỉ bind giống nhau, khiến bản thứ hai thất bại khi mở port dù tất cả Spring beans tạo thành công.
Ứng dụng mở gRPC server trước khi dữ liệu tham chiếu được nạp, khiến health báo phục vụ còn RPC tra cứu trả NOT_FOUND cho các bản ghi sẽ có sau vài giây.
Đội tách service implementation thành hai module Spring nhưng sử dụng cấu hình khởi tạo khác nhau, khiến một bean chỉ có mặt ở staging còn production thiếu toàn bộ RPC của module đó.
Một service đặt gRPC client stub trong bean singleton nhưng khởi tạo ManagedChannel mới cho mỗi request, khiến số kết nối TCP và thread tăng theo traffic.
Nhóm tái sử dụng một ManagedChannel nhưng không quản lý shutdown khi context đóng, khiến integration tests và các lần hot reload còn giữ tài nguyên nền.
Ứng dụng chọn blocking stub để gọi service chậm ngay trên thread xử lý HTTP Netty, khiến một request gRPC làm nghẽn các endpoint WebFlux không liên quan.
Đội dùng asynchronous stub rồi coi invocation trả về là kết quả RPC đã thành công, khiến API xác nhận đơn trước khi callback server trả trạng thái cuối.
Một service sử dụng future stub để kết hợp nhiều RPC nhưng không xử lý exceptional completion, khiến một lỗi UNAVAILABLE bị chuyển thành response treo tại gateway.
Nhóm tạo stub cho một khách theo tenant rồi lưu chung trong cache mà quên metadata xác thực khác nhau, khiến yêu cầu tiếp theo có nguy cơ mang credential của khách trước.
Ứng dụng đưa endpoint gRPC của staging vào cấu hình client production, khiến dữ liệu thử được truy vấn từ hệ thống thật và kết quả báo cáo khó đối soát.
Đội dùng tên DNS của service trong cấu hình Spring nhưng cluster chỉ có endpoint HTTP gateway, khiến client gRPC nhận phản hồi không hợp lệ ở bước handshake.
Một service cập nhật địa chỉ server gRPC qua config runtime nhưng ManagedChannel cũ không được thay đổi tương ứng, khiến một số pod tiếp tục kết nối instance đã rút khỏi cluster.
Nhóm dùng client stub tạo từ một channel rồi shutdown channel sau một RPC, khiến lần gọi tiếp theo bằng cùng stub bị từ chối dù bean vẫn được giữ trong Spring context.
Ứng dụng bật gRPC reflection ở local để khám phá dịch vụ nhưng môi trường production chưa có quyền truy cập reflection, khiến tool vận hành hiểu nhầm server không công bố RPC.
Đội sử dụng gRPC health check để sẵn sàng nhận traffic nhưng service chỉ trả trạng thái toàn server, khiến một RPC phụ thuộc hệ thống ngoài đang hỏng vẫn được điều hướng tới.
Một service tạo bean interceptors trong Spring nhưng thứ tự áp dụng giữa log và authentication khác kỳ vọng, khiến một số request nhạy cảm được log trước khi metadata được che.
Nhóm cấu hình một client interceptor kiểm tra quota nhưng chỉ gắn vào một loại stub, khiến các request qua future stub không được theo dõi như đường blocking.
Ứng dụng dùng Spring lifecycle để dừng server gRPC nhưng chưa cho streaming RPC hoàn tất, khiến khi pod được thay thế những client đang tải báo cáo bị cắt giữa chừng.
Đội cấu hình server gRPC chỉ nghe loopback trong container, khiến pod health nội bộ thành công nhưng Service Kubernetes không thể truy cập cổng từ pod khác.
Một service muốn đưa RPC mới vào ứng dụng Spring nhưng bean implementation đăng ký đúng còn Protobuf descriptor trên client vẫn là phiên bản cũ, khiến kiểm thử kết nối không phát hiện hợp đồng thay đổi.
Nhóm triển khai unary RPC tra cứu khách hàng nhưng xử lý kết quả qua database trong blocking call lâu, khiến nhiều request đồng thời chiếm hết thread pool server.
Ứng dụng tạo đơn qua unary RPC và client gửi lại yêu cầu sau khi mất kết nối, khiến hệ thống tạo hai đơn vì RPC đầu đã hoàn tất tại server nhưng response không tới client.
Đội nhận unary request có danh sách sản phẩm rỗng và vẫn trả OK, khiến downstream coi đơn không có hàng là giao dịch thành công.
Một service trả response unary từ dữ liệu cache nhưng bản ghi vừa được cập nhật ở database, khiến khách nhận trạng thái cũ ngay sau khi lưu.
Nhóm dùng unary RPC cập nhật user profile nhưng server không đối chiếu tenant trong metadata với userId trong message, khiến yêu cầu có thể sửa hồ sơ ngoài tổ chức.
Ứng dụng dùng unary RPC thanh toán nhưng server thực hiện xác minh với hai hệ thống ngoài, khiến deadline mặc định của khách kết thúc trước bước thứ hai.
Đội trả nhiều lỗi nghiệp vụ qua response có field success=false nhưng vẫn dùng gRPC status OK, khiến client metrics và retry policy không nhận ra giao dịch thất bại.
Một service gọi gRPC unary vào database replica và hứa read-after-write consistency, khiến request ngay sau lệnh cập nhật vẫn nhận bản ghi cũ do replication lag.
Nhóm xây RPC tìm kiếm trả danh sách kết quả trong một message unary, khiến payload quá lớn khi khách chọn phạm vi toàn bộ dữ liệu.
Ứng dụng có unary RPC chấp nhận mã voucher nhưng hai request đồng thời kiểm tra số lượt còn lại trước khi ghi, khiến nhiều khách dùng một mã quá số lần cho phép.
Đội chạy server-streaming RPC xuất lịch sử giao dịch nhưng implementation tạo toàn bộ danh sách trước khi gửi, khiến JVM tăng heap khi khách yêu cầu nhiều năm dữ liệu.
Một service phát từng message qua server-streaming RPC nhưng một client đọc chậm và server bỏ qua trạng thái ready, khiến số buffer pending tăng trong giờ cao điểm.
Nhóm dùng onNext liên tục trong vòng lặp lớn trên server mà không xét flow control, khiến một lần tải báo cáo chiếm nhiều tài nguyên cho một kết nối chậm.
Ứng dụng hoàn thành server-streaming bằng onCompleted ngay sau khi phát phần tử đầu, khiến những dữ liệu được chuẩn bị trong tác vụ async phía sau không bao giờ được chuyển.
Đội chuyển một server-streaming RPC từ báo giá tức thời sang cập nhật liên tục mà không xác định điểm kết thúc, khiến client cũ chờ onCompleted để xử lý kết quả.
Một service chạy luồng server-streaming từ database nhưng khi client hủy subscription, tác vụ truy vấn nền vẫn đọc tiếp và giữ connection tới database.
Nhóm dùng server-streaming để gửi thông báo hệ thống nhưng một load balancer có idle timeout ngắn, khiến stream bị cắt dù server không phát dữ liệu trong vài phút.
Ứng dụng phát cập nhật tồn kho qua server stream nhưng không mang sequence number, khiến khách reconnect không phát hiện những sự kiện bị bỏ lỡ.
Đội gửi cảnh báo qua server-streaming RPC khi có lỗi và duy trì các stream dài hạn, nhưng rolling deployment đóng kết nối khiến dashboard bỏ qua trạng thái vừa phát.
Một service dùng streaming gRPC thay vì pagination để truyền toàn bộ danh mục nhưng client mobile mất mạng giữa chừng, khiến API không biết cần tiếp tục từ offset nào.
Nhóm triển khai client-streaming RPC nhập bản ghi nhưng consumer xử lý dữ liệu theo thứ tự onNext mà một worker async hoàn tất lộn thứ tự, khiến tổng số lượng sai.
Ứng dụng nhận client-streaming upload file nhưng lưu từng chunk ngay xuống storage trước khi xác minh checksum cuối, khiến file lỗi vẫn xuất hiện như đã hoàn tất.
Đội để client gọi onCompleted trước khi mọi chunk được gửi từ thread phụ, khiến server tính checksum trên tệp chưa đủ dữ liệu.
Một service có client-streaming RPC gom danh sách đơn trước khi trả response, nhưng không giới hạn số phần tử nên một client gửi hàng triệu message làm hết heap.
Nhóm cho phép client gửi onNext đồng thời từ nhiều threads vào một request observer chưa được serialize đúng, khiến payload nhập lô bị lỗi theo thời điểm tải cao.
Ứng dụng gửi toàn bộ dữ liệu bằng client-streaming RPC nhưng người dùng đóng app khi mới gửi một nửa, khiến server còn bản nhập dở mà không có trạng thái hủy rõ ràng.
Đội dùng client-streaming để tải hàng triệu hồ sơ nhưng chỉ trả một response tổng, khiến một item lỗi giữa chừng không thể được đối chiếu với vị trí dữ liệu nguồn.
Một service trả response cho client-streaming sau khi tính toán xong nhưng server không gọi onCompleted trên response observer, khiến client treo tới deadline.
Nhóm triển khai client-streaming nhập kho và retry cả stream khi kết nối mất, khiến các chunk đã được ghi từ lần đầu có nguy cơ được ghi lại.
Ứng dụng có client-streaming RPC xử lý mỗi record theo transaction riêng nhưng phía gọi kỳ vọng cả luồng nhập thành công hoặc rollback toàn bộ, khiến dữ liệu chỉ được lưu một phần sau lỗi.
Đội nhận stream ảnh nhiều chunk và validate từng kích thước riêng nhưng không giới hạn tổng byte, khiến client có thể vượt quota bằng cách chia upload rất nhỏ.
Một service sử dụng bidirectional streaming để đồng bộ giá sản phẩm nhưng client gửi yêu cầu liên tục và server trả phản hồi theo thứ tự hoàn tất khác thứ tự gửi, khiến UI gắn giá sai sản phẩm.
Nhóm thiết kế bidirectional stream cho giao dịch chat nhưng server không ràng buộc roomId ở từng message với metadata phiên, khiến người dùng có thể gửi vào phòng không thuộc mình.
Ứng dụng dùng bidi streaming trao đổi lệnh điều khiển và phản hồi nhưng client chỉ chờ server kết thúc để hiển thị, khiến phản hồi từng lệnh không được xử lý theo thời gian thực.
Đội để hai luồng cùng gọi onNext lên response observer của một bidi RPC, khiến các message phản hồi có thể bị phát không an toàn khi concurrency tăng.
Một service phát trạng thái qua bidi streaming nhưng server không xử lý client half-close, khiến một phía đã gửi xong mà phía kia vẫn chờ dữ liệu vô hạn.
Nhóm dùng bidi stream để cập nhật vị trí tài xế nhưng không kiểm soát tốc độ gửi, khiến client có mạng tốt áp đảo consumer ghi dữ liệu phía server.
Ứng dụng triển khai bidi RPC cho thiết bị IoT nhưng một thiết bị kết nối chậm làm queue cho chính phiên đó tăng liên tục, khiến memory service tăng theo số thiết bị.
Đội gửi command qua bidi stream và mong mỗi command có đúng một acknowledgement, nhưng protocol message không có correlation ID nên client gán phản hồi sai sau khi xử lý song song.
Một service sử dụng một bidi stream cho nhiều tenant mà không tách định danh người gọi, khiến notification của tenant khác có thể đi qua cùng session.
Nhóm đặt deadline ngắn cho một bidi stream dự kiến mở hàng giờ, khiến kết nối tự hết hạn giữa ca làm việc dù không có lỗi nghiệp vụ.
Ứng dụng dự kiến retry bidirectional stream khi bị UNAVAILABLE nhưng không lưu trạng thái đã ACK, khiến thiết bị thực thi lại những lệnh trước khi kết nối mất.
Đội dùng bidirectional stream để phát kết quả tìm kiếm theo từng ký tự, nhưng client không gửi tín hiệu hủy tác vụ cũ khi query mới tới, khiến server tính toán kết quả không còn cần.
Một service stream dữ liệu sang dashboard nhưng một interceptor dùng bộ đếm message để giới hạn lưu lượng cho mọi stream chung, khiến một dashboard nhiều người xem làm các phiên khác bị từ chối.
Nhóm muốn cấp ưu tiên cho command khẩn qua bidi stream nhưng hàng đợi hiện dùng chung FIFO với hàng nghìn event thường, khiến lệnh khẩn không tới thiết bị kịp thời.
Ứng dụng nhận onError từ upstream stream rồi tiếp tục cố gửi onNext cho cùng RPC, khiến một số callback lỗi thêm thay vì dừng theo vòng đời terminal signal.
Đội phát gRPC message từ callback sau khi client đã cancel server stream, khiến tác vụ vẫn giữ dữ liệu ở bộ nhớ và ghi log lỗi observer liên tục.
Một service chấp nhận streaming message có kích thước nhỏ nhưng lượng metadata per-message lớn do custom envelope, khiến băng thông và CPU cao hơn giả định.
Nhóm dùng server-streaming qua HTTP/2 nhưng một proxy chuyển request sang HTTP/1.1, khiến các message không được gửi đúng framing và client báo protocol error.
Ứng dụng muốn hỗ trợ trình duyệt gọi trực tiếp bidi streaming gRPC chuẩn nhưng browser chỉ có gRPC-Web transport trong hệ thống hiện tại, khiến kịch bản client frontend không hoạt động như SDK Java.
Đội triển khai gRPC-Web qua proxy cho một server-streaming RPC nhưng cấu hình gateway buffer response, khiến giao diện không nhận message ngay khi server phát.
Một service dùng gRPC status CANCELLED khi khách ngắt tải file, nhưng dashboard coi đó là lỗi server nghiêm trọng và cảnh báo sai trong giờ cao điểm.
Nhóm đặt deadline cho RPC theo mặc định toàn client nhưng một loại tác vụ export dài cần thời gian khác, khiến export bị DEADLINE_EXCEEDED dù server vẫn xử lý đúng.
Ứng dụng không đặt deadline cho cuộc gọi sang đối tác đang không phản hồi, khiến thread và connection client tiếp tục chờ đến khi container hết tài nguyên.
Đội chuyển một deadline còn lại qua nhiều service nối tiếp nhưng một bước backend tự tạo deadline dài hơn request gốc, khiến công việc tiếp tục sau khi caller đã bỏ cuộc.
Một service nhận Context cancellation từ RPC nhưng phương thức xử lý vẫn gửi email qua tác vụ nền, khiến khách đã hủy thao tác vẫn nhận thông báo giao dịch.
Nhóm dùng deadline theo thời gian tuyệt đối do đồng hồ client tự đặt sai, khiến server thấy request đã hết hạn ngay khi vừa nhận.
Ứng dụng gọi RPC phụ sau một bước database chậm mà không xét thời gian còn lại, khiến gần như mọi request của luồng đó bị DEADLINE_EXCEEDED ở bước cuối.
Đội tự retry một RPC khi nhận DEADLINE_EXCEEDED nhưng thao tác server đã commit dữ liệu, khiến hai lần chạy tác vụ ghi có side effect trùng.
Một service trả INVALID_ARGUMENT cho mọi lỗi, kể cả database không kết nối được, khiến client không phân biệt dữ liệu đầu vào sai với lỗi tạm thời để retry.
Nhóm dùng NOT_FOUND cho trường hợp khách không có quyền xem hồ sơ nhưng một endpoint khác trả PERMISSION_DENIED, khiến client có thể suy ra sự tồn tại của dữ liệu nhạy cảm.
Ứng dụng gửi UNAUTHENTICATED khi token đã hết hạn nhưng client không có quy trình làm mới token, khiến mọi request sau đó bị thất bại tới khi khởi động lại app.
Đội trả PERMISSION_DENIED cho lỗi token thiếu chữ ký hợp lệ, khiến hệ thống xác thực của bên tích hợp không biết phải sửa credential hay xin thêm quyền.
Một service dùng ALREADY_EXISTS để báo trùng orderId nhưng phía gọi coi lỗi như sự cố hạ tầng, khiến client retry lặp lại cùng yêu cầu trong nhiều phút.
Nhóm cần bảo vệ optimistic locking cho hồ sơ nhưng trả ABORTED mà không giải thích phiên bản xung đột, khiến frontend không biết khi nào lấy bản mới để sửa lại.
Ứng dụng gặp RESOURCE_EXHAUSTED khi pool gRPC server quá tải nhưng client coi đây là lỗi nghiệp vụ vĩnh viễn, khiến các job nhập liệu bị bỏ mà không được lên lịch tiếp.
Đội dùng UNAVAILABLE khi kết nối tới service ngoài bị mất nhưng policy retry tất cả các RPC gồm thanh toán, khiến một số side effects đã chạy trước khi lỗi mạng được thực hiện lại.
Một service trả INTERNAL kèm nguyên stack trace database trong status description, khiến tên bảng và dữ liệu cấu hình nội bộ bị lộ cho đối tác.
Nhóm trả UNKNOWN cho mọi exception chưa phân loại, khiến hệ thống giám sát không biết lỗi bắt nguồn từ validation, downstream timeout hay bug Java.
Ứng dụng muốn trả nhiều FieldViolation trong response lỗi gRPC nhưng client chỉ đọc status code, khiến người dùng chỉ thấy INVALID_ARGUMENT mà không biết trường nào sai.
Đội bổ sung structured error details qua google.rpc.Status nhưng client cũ không có thư viện đọc chi tiết, khiến kênh hỗ trợ khách không nhận được mã lỗi nghiệp vụ.
Một service dùng StatusRuntimeException để trả lỗi sau khi đã gửi vài message trên server stream, khiến client đã ghi phần dữ liệu nhận trước mà không đánh dấu kết quả chưa hoàn tất.
Nhóm mapping exception business thành status trong interceptor nhưng một loại exception được throw từ callback async không đi qua bộ chuyển đổi dự kiến, khiến client nhận UNKNOWN.
Ứng dụng trả OK khi không có dữ liệu trong unary RPC nhưng một client dự kiến NOT_FOUND, khiến hai ứng dụng tích hợp hiển thị trạng thái không thống nhất.
Đội đặt retry policy cho status UNAVAILABLE nhưng gRPC service phía sau phát trạng thái đó cả khi request không hợp lệ, khiến client tăng lưu lượng vô ích vào endpoint đã quá tải.
Một service cần phân biệt CANCELLED do người dùng ngắt và DEADLINE_EXCEEDED do server xử lý chậm, nhưng logs chỉ ghi một nhóm timeout chung khiến phân tích SLA sai.
Nhóm gọi một gRPC service có nhiều downstream phụ thuộc, nhưng khi một downstream trả UNAVAILABLE server trả chung INTERNAL, khiến client không biết lỗi nào còn có thể phục hồi.
Ứng dụng dùng trailers chứa mã đối soát giao dịch khi trả lỗi nhưng proxy trung gian không chuyển đầy đủ trailers, khiến client thiếu thông tin tra cứu khi hỗ trợ khách.
Đội truyền bearer token qua Metadata ở client interceptor nhưng một lời gọi được tạo bằng stub không gắn interceptor đó, khiến một RPC hoạt động local và bị UNAUTHENTICATED ở production.
Một service cần đọc tenantId từ request Metadata nhưng một client gửi key viết hoa không phù hợp quy tắc header gRPC, khiến xác định tenant thất bại ở môi trường đối tác.
Nhóm lấy userId từ metadata do client tự cung cấp mà không xác minh chữ ký token, khiến một khách có thể giả mạo danh tính để truy cập dữ liệu người khác.
Ứng dụng ghi đầy đủ Metadata trong server interceptor để debug nhưng token xác thực xuất hiện trong log tập trung của production.
Đội dùng một Context key cho correlation ID nhưng interceptor đặt giá trị sau khi handler đã bắt đầu, khiến logs trong phần đầu xử lý không có trace ID.
Một service truyền requestId từ gRPC Metadata vào MDC ThreadLocal nhưng processing chuyển thread, khiến log từ callback dùng requestId của yêu cầu khác.
Nhóm gửi tracing baggage qua metadata và đặt thông tin khách hàng ở mỗi RPC hop, khiến dữ liệu nhạy cảm được chuyển tiếp tới những service không cần biết.
Ứng dụng dùng client interceptor thêm header region nhưng khi request đi qua service trung gian, Context propagation không chuyển region sang stub outbound khiến dữ liệu bị truy vấn sai vùng.
Đội gắn deadline propagation vào client interceptor tùy biến nhưng interceptor tạo Deadline mới mỗi hop, khiến tổng thời gian xử lý vượt SLA caller đã đặt.
Một service có server interceptor kiểm tra quota theo từng request nhưng với streaming RPC một phiên gửi hàng triệu message, khiến giới hạn tải không phản ánh lượng dữ liệu thực.
Nhóm dùng authentication interceptor kiểm tra token tại lúc mở bidi stream nhưng quyền của người dùng bị thu hồi giữa phiên, khiến stream tiếp tục hoạt động lâu hơn chính sách.
Ứng dụng thêm interceptor audit bên trong handler chỉ cho unary method, khiến các lệnh cập nhật qua client-streaming không có thông tin người thực hiện.
Đội sắp xếp thứ tự interceptor log trước interceptor làm sạch dữ liệu, khiến các metadata có token được ghi ra log trước khi bị che.
Một service phát gRPC error từ interceptor trước khi gọi business handler nhưng không đóng server call đúng vòng đời, khiến client chờ tới deadline trong một số request.
Nhóm sử dụng Metadata ASCII marshaller để truyền payload nhị phân tùy biến, khiến một số byte không thể biểu diễn đúng và server không giải mã được.
Ứng dụng gửi cấu hình byte array trong metadata key không có suffix nhị phân phù hợp, khiến client Java và Go truyền thông tin khác nhau.
Đội đưa JWT quá lớn vào Metadata vì chứa nhiều roles, khiến HTTP/2 proxy từ chối request do vượt giới hạn tổng kích thước headers.
Một service tạo traceId mới cho mọi retry RPC thay vì giữ correlation với yêu cầu gốc, khiến khó nhận diện các lần thử cùng một đơn hàng.
Nhóm dùng server interceptor để thêm response metadata về quota nhưng gọi phần ghi headers sau khi response headers đã được gửi, khiến client không nhận thông tin đó.
Ứng dụng cần đọc trailers khi RPC thất bại để biết mã hỗ trợ, nhưng callback của client chỉ ghi exception message và bỏ qua Metadata đi kèm.
Đội dùng mTLS để xác thực client service identity nhưng code vẫn tin tenantId do request metadata tự khai báo, khiến xác thực đường truyền không bảo vệ phạm vi dữ liệu.
Một service phân quyền theo tên RPC đầy đủ nhưng khi đổi package .proto, interceptor không cập nhật policy khiến các method mới lọt qua cấu hình không mong đợi.
Nhóm thiết kế interceptor ghi độ trễ nhưng gọi thời gian bắt đầu tại lúc tạo stub thay vì lúc RPC thực sự khởi chạy, khiến latency histogram cao sai.
Ứng dụng có nhiều client interceptor cùng bổ sung cùng một header tên authorization, khiến server nhận metadata trùng và logic chọn token không nhất quán.
Đội tạo correlation ID trong Reactor Context của ứng dụng WebFlux nhưng client gRPC callback dùng executor khác, khiến metadata outbound không chứa ID để liên kết trace.
Một service dùng server interceptor kiểm tra địa chỉ IP của client nhưng request qua Envoy khiến địa chỉ nhìn thấy là proxy, khiến whitelist chặn nhầm toàn bộ đối tác.
Nhóm dùng request metadata để chọn locale lỗi nhưng không giới hạn giá trị locale, khiến response message được chọn ngoài tập ngôn ngữ nghiệp vụ cho phép.
Ứng dụng bật TLS trên gRPC server nhưng Java client vẫn cấu hình plaintext, khiến kênh không thiết lập được HTTP/2 handshake khi chuyển sang production.
Đội xoay chứng chỉ TLS của server nhưng một nhóm client giữ truststore CA cũ, khiến các kết nối mới thất bại trong khi channel đang mở vẫn tạm hoạt động.
Một service triển khai mutual TLS nhưng chỉ cấu hình client certificate tại một pod, khiến lỗi UNAVAILABLE chỉ xuất hiện khi load balancer chọn pod chưa có chứng chỉ.
Nhóm cấu hình TLS certificate cho tên miền public nhưng client gọi bằng tên DNS nội bộ, khiến xác minh hostname thất bại dù địa chỉ và port đúng.
Ứng dụng dùng certificate chain thiếu intermediate CA, khiến một số Java runtime thiết lập kết nối thành công còn máy đối tác báo handshake failure.
Đội cấu hình gRPC qua ingress HTTP/2 nhưng proxy downgrade giao thức ở chặng backend, khiến unary RPC lỗi protocol và streaming RPC không hoạt động.
Một service chạy gRPC plaintext h2c ở mạng thử nghiệm nhưng ingress production yêu cầu TLS phía backend, khiến channel chưa từng chuyển trạng thái READY.
Nhóm triển khai service mesh sidecar với mTLS nhưng ứng dụng tiếp tục bật TLS theo giả định cũ, khiến hai lớp mã hóa không được ghép đúng cách và kênh bị lỗi.
Ứng dụng đặt TLS key/cert rotation vào secret volume nhưng server chỉ nạp lúc startup, khiến chứng chỉ cũ hết hạn dù file trên volume đã được cập nhật.
Đội tạo endpoint gRPC sau load balancer chỉ hỗ trợ round-robin theo connection, khiến một số HTTP/2 connection sống lâu đẩy hầu hết request vào một pod.
Một service dùng client-side load balancing với danh sách IP tĩnh, khiến các pod mới sau autoscaling không được nhận traffic và pod cũ tiếp tục quá tải.
Nhóm dùng service discovery để tìm gRPC endpoints nhưng resolver trả tên HTTP API gateway, khiến stub kết nối được TCP mà không thực hiện được gRPC method.
Ứng dụng đặt DNS TTL rất dài cho channel resolution, khiến khi cluster thay instance gRPC các client còn gọi địa chỉ cũ trong thời gian dài.
Đội đổi địa chỉ backend trong rolling deployment nhưng gRPC channel vẫn dùng kết nối HTTP/2 cũ, khiến traffic tiếp tục vào pod chuẩn bị tắt.
Một service bật keepalive ping tần suất quá cao, khiến proxy phía trước đóng connection theo chính sách phòng tránh ping abuse.
Nhóm không bật cơ chế phát hiện connection không còn hoạt động phù hợp cho long-lived stream, khiến client giữ kênh tưởng còn sống dù đường mạng đã bị cắt.
Ứng dụng cấu hình HTTP/2 max concurrent streams thấp ở ingress nhưng client dồn hàng nghìn RPC qua một channel, khiến pending call tăng và latency đỉnh cao.
Đội tăng số ManagedChannel trên mỗi pod để giảm hàng chờ nhưng không xét socket và thread overhead, khiến tài nguyên JVM và proxy tăng vượt dự toán.
Một service gửi response protobuf lớn mà không cấu hình giới hạn inbound message size trên client, khiến báo cáo của khách lớn bị RESOURCE_EXHAUSTED trước khi parser chạy.
Nhóm bật gzip cho tất cả gRPC messages gồm payload vốn đã nén, khiến CPU tăng trong giờ cao điểm mà băng thông gần như không giảm.
Ứng dụng gửi dữ liệu không thể nén với compression bắt buộc nhưng một client cũ không hỗ trợ thuật toán cấu hình, khiến tích hợp giữa hai nhóm thất bại.
Đội cấu hình gRPC server reflection trong production để hỗ trợ grpcurl nhưng mở cùng quyền truy cập với Internet, khiến danh sách service/method nội bộ có thể bị khám phá.
Một service triển khai health checking nhưng endpoint chỉ xác nhận tiến trình JVM đang chạy, khiến traffic được chuyển vào node đã mất kết nối database.
Nhóm chuyển trạng thái health sang NOT_SERVING khi nhận SIGTERM nhưng grace period của Kubernetes quá ngắn, khiến stream đang hoạt động bị đóng trước khi hoàn tất.
Ứng dụng chạy gRPC server và REST server trên cùng pod nhưng readiness probe chỉ kiểm tra REST, khiến gRPC port lỗi bind mà rollout vẫn được đánh dấu sẵn sàng.
Đội triển khai nhiều gRPC services trên một server và health check báo toàn bộ SERVING, khiến một service phụ thuộc broker bị hỏng vẫn tiếp tục nhận request.
Một service đăng ký service name theo contract package trong gRPC health checks nhưng load balancer truy vấn tên khác, khiến node khỏe bị xem là không sẵn sàng.
Nhóm bật proxy protocol trên load balancer mà gRPC server không hiểu định dạng đầu kết nối, khiến một phần request thất bại ngay lúc thiết lập HTTP/2.
Ứng dụng triển khai gRPC bên sau API gateway yêu cầu gRPC-Web nhưng Java client dùng native gRPC, khiến cùng hostname không thể phục vụ hai loại client theo cấu hình hiện tại.
Đội dùng một DNS endpoint cho cả public và private gRPC nhưng TLS và authorization khác nhau theo vùng, khiến một số client nội bộ bị định tuyến ra cổng public ngoài dự kiến.
Một service có RPC đặt hàng cần idempotency nhưng client retry sau khi gặp UNAVAILABLE, khiến database có nhiều bản ghi do server đã xử lý trước lúc connection rớt.
Nhóm bật retry policy trên client cho RESOURCE_EXHAUSTED nhưng server đã quá tải, khiến tổng lượng RPC tăng và recovery kéo dài sau đợt traffic lớn.
Ứng dụng sử dụng hedging cho unary RPC đọc báo cáo nhưng mỗi bản sao yêu cầu đều thực hiện một phép tính tốn nhiều CPU, khiến tải backend tăng trong giờ cao điểm.
Đội dùng retryBackoff chung cho mọi gRPC method, khiến lời gọi lấy cấu hình và lời gọi ghi thanh toán có cùng hành vi retry dù rủi ro side effect khác nhau.
Một service cần giảm lỗi do backend failover nhưng client không thiết lập deadline, khiến RPC xếp hàng quá lâu trong lúc resolver cập nhật địa chỉ mới.
Nhóm đặt thời gian retry tối đa dài hơn deadline caller, khiến log ghi nhiều vòng retry dù request đã hết hạn và khách nhận lỗi.
Ứng dụng mở circuit breaker dựa trên số StatusRuntimeException nhưng không phân biệt INVALID_ARGUMENT với UNAVAILABLE, khiến input sai của client làm ngắt dịch vụ cho khách khác.
Đội thực hiện fallback sang data cache khi RPC trả DEADLINE_EXCEEDED nhưng không ghi tuổi cache, khiến nghiệp vụ tài chính sử dụng giá đã quá hạn.
Một service phát event để đồng bộ kho sau khi gRPC server nhận request nhưng mất network trước khi trả ACK, khiến client gửi lại lệnh và event được phát trùng.
Nhóm triển khai phân quyền ở gateway và giả định mọi gRPC request đi qua gateway, khiến client nội bộ gọi trực tiếp service có thể bỏ qua kiểm tra như đường public.
Ứng dụng có rate limit theo số unary RPC nhưng một client chuyển cùng dữ liệu qua một client-streaming RPC dài, khiến mức tải thực không bị giới hạn như kỳ vọng.
Đội dùng connection pool client chung giữa các tenant nhưng quota ứng dụng được đếm theo channel thay vì identity, khiến một tenant chiếm phần lớn khả năng phục vụ.
Một service kiểm tra JWT ở mỗi unary RPC nhưng bidi stream dài không đánh giá lại quyền, khiến một tài khoản đã bị vô hiệu hóa vẫn gửi command.
Nhóm gửi client certificate qua service mesh nhưng Spring gRPC server chỉ đọc token metadata, khiến các yêu cầu từ máy dịch vụ chưa có token bị từ chối dù đã xác thực mTLS.
Ứng dụng để một gRPC method quản trị xóa cache cùng port với RPC public và cùng quyền gọi, khiến tài khoản khách có thể vô tình kích hoạt thao tác vận hành.
Đội cấu hình audit chỉ ở Spring MVC interceptor nhưng gRPC service implementation không đi qua MVC, khiến các lệnh chỉnh sửa qua RPC không có thông tin người thực hiện.
Một service gửi thông tin cá nhân qua protobuf request nhưng log interceptor serialize toàn bộ message, khiến dữ liệu định danh bị đưa vào hệ thống theo dõi ngoài chính sách.
Nhóm dùng Metadata để truyền một token dịch vụ dùng chung cho các lệnh khác tenant, khiến sau khi token bị lộ không thể thu hẹp phạm vi thiệt hại theo từng khách.
Ứng dụng đổi certificate của một partner nhưng policy mTLS chỉ khớp subject DN quá rộng, khiến certificate khác cùng tổ chức có thể gọi RPC nhạy cảm.
Đội yêu cầu mã hóa dữ liệu nội bộ nhưng một backend gRPC đang dùng plaintext vì nằm sau sidecar, khiến đường truyền giữa app container và sidecar chưa được đánh giá trong mô hình đe dọa.
Một service nhận file upload streaming và ghi chunk trước khi xác thực checksum, khiến người dùng có quyền thấp có thể tiêu tốn storage bằng các request không hoàn chỉnh.
Nhóm cho phép request metadata mang tên tổ chức để phục vụ billing nhưng không xác nhận với JWT claim, khiến hóa đơn sử dụng gRPC có thể bị ghi cho tenant khác.
Ứng dụng muốn quản lý quyền theo từng phương thức Protobuf nhưng một RPC mới không được bổ sung vào bảng policy, khiến quyền mặc định không phù hợp độ nhạy của thao tác.
Đội ghi correlation ID vào trailers của mọi RPC nhưng client bị lỗi kết nối trước khi nhận trailers, khiến audit cần dựa vào log server mà thiếu liên kết với yêu cầu client.
Một service phát response lỗi chứa exception details nhạy cảm qua protobuf Any, khiến đối tác có thể thấy cấu trúc hệ thống nội bộ dù status gRPC là INTERNAL.
Nhóm muốn log payload request gRPC khi xử lý sự cố nhưng không có cơ chế masking field số tài khoản, khiến việc bật debug có nguy cơ vi phạm chính sách dữ liệu.
Ứng dụng theo dõi số kết nối TLS thành công nhưng không phân loại lỗi authentication và authorization, khiến đội trực nhầm lỗi chứng chỉ với lỗi thiếu role.
Đội viết unit test cho gRPC implementation bằng cách gọi trực tiếp method Java, khiến lỗi interceptor metadata và mapping status chưa được phát hiện trước khi chạy server thật.
Một service dùng in-process gRPC server/channel cho integration test nhưng production chạy qua TLS và ingress, khiến bài test không phát hiện sự cố HTTP/2 handshake.
Nhóm xây test unary RPC chỉ với request thành công và response đúng dữ liệu, khiến các trường hợp INVALID_ARGUMENT, NOT_FOUND và DEADLINE_EXCEEDED chưa được kiểm chứng.
Ứng dụng thử tạo đơn bằng gRPC một lần nhưng không mô phỏng response bị mất rồi client retry, khiến nguy cơ ghi trùng không được phát hiện ở CI.
Đội kiểm thử server-streaming bằng cách đọc hết một stream nhỏ nhưng không hủy giữa chừng, khiến nguồn database tiếp tục chạy sau client cancel chưa được thử nghiệm.
Một service thử client-streaming với hai chunk hợp lệ nhưng không gửi onError hoặc half-close bất thường, khiến bản ghi tạm chưa được dọn khi upload thất bại.
Nhóm test bidi streaming bằng cách gửi một command rồi đợi một response tuần tự, khiến vấn đề response đến lệch thứ tự khi nhiều command concurrent chưa được phát hiện.
Ứng dụng dùng in-process transport để test stream lớn nhưng không giới hạn memory tương tự production, khiến lỗi RESOURCE_EXHAUSTED khi chạy qua network chưa được mô phỏng.
Đội viết integration test xác thực token với metadata đúng nhưng không thử token hết hạn hoặc tenantId giả, khiến interceptor bảo mật chưa được kiểm chứng toàn diện.
Một service dùng mock StreamObserver nhưng không kiểm tra onNext sau onCompleted, khiến vi phạm vòng đời observer không làm suite test thất bại.
Nhóm mô phỏng flow control bằng client đọc nhanh, khiến trường hợp server gửi dữ liệu vượt demand khi client chậm chưa được đánh giá.
Ứng dụng chạy test gRPC qua localhost chỉ một process nhưng production có nhiều pod và load balancer, khiến stream bị cắt ở rolling deployment chưa được mô phỏng.
Đội chỉ kiểm tra health endpoint của gRPC server mà không thử service-specific health, khiến một RPC phụ thuộc database chết nhưng smoke test vẫn PASS.
Một service nâng phiên bản Protobuf schema và test chỉ với client mới, khiến bản client cũ đang hoạt động không đọc được response mới dù server test xanh.
Nhóm muốn kiểm chứng backward compatibility nhưng pipeline không đọc message serialized từ phiên bản trước, khiến thay đổi field number không được phát hiện trước publish.
Ứng dụng chạy integration test với stub blocking nhưng production có async stub xử lý callback lỗi, khiến exceptional completion bị bỏ sót ở bộ kiểm thử.
Đội thử deadline lớn hơn thời gian xử lý bình thường nhưng không thử deadline cực ngắn, khiến những tác vụ server vẫn chạy sau cancellation chưa được phát hiện.
Một service kiểm thử retry UNAVAILABLE với một mock luôn trả lỗi trước khi thực thi, khiến trường hợp server đã commit nhưng response bị mất không được xem xét.
Nhóm chạy performance test chỉ với unary RPC và message nhỏ, khiến memory và latency của server-streaming payload lớn chưa được đo.
Ứng dụng đo throughput gRPC bằng một client trên mạng nội bộ nhưng production dùng TLS qua nhiều proxy, khiến kết quả benchmark không dự đoán được latency ở đối tác.
Đội dùng grpcurl để kiểm thử RPC qua server reflection nhưng production tắt reflection, khiến runbook kiểm tra sự cố không hoạt động tại môi trường cần nhất.
Một service chạy test authentication interceptor bằng token thật của môi trường dev và ghi debug request, khiến credential thử nghiệm có nguy cơ bị lưu lại trong artifacts CI.
Nhóm thử mTLS với một certificate còn hạn nhưng không mô phỏng CA rotation và certificate hết hạn, khiến ngày gia hạn production gặp lỗi hàng loạt.
Ứng dụng có test xác minh gRPC method trả OK nhưng không kiểm tra response trailers chứa mã audit, khiến đối tác thiếu thông tin đối soát dù RPC hoàn tất.
Đội kiểm thử TLS ở cấp ManagedChannel nhưng không mô phỏng proxy đổi hostname, khiến xác minh certificate chỉ thất bại khi service được gọi qua DNS thật.
Một service có server-streaming RPC dùng coroutine/callback async nhưng test kết thúc khi observer nhận phần tử đầu, khiến lỗi cuối stream không được báo trong kết quả CI.
Nhóm chạy test nhiều context Spring gRPC dùng chung port cố định, khiến các suite song song tranh cổng và kết quả CI thay đổi theo thứ tự chạy.
Ứng dụng dùng test client với metadata locale mặc định tiếng Anh nhưng khách hàng gửi nhiều locale, khiến lỗi validation qua gRPC luôn có ngôn ngữ sai mà test chưa biết.
Đội kiểm thử graceful shutdown với unary RPC ngắn nhưng không mở long-lived bidi streams, khiến quá trình drain thực tế làm mất sự kiện của thiết bị.
Một service test request message với enum hợp lệ nhưng không thử giá trị enum chưa biết từ client mới, khiến code chuyển đổi của bản cũ ném exception khi triển khai song song.
Nhóm có contract test so sánh tên field Java thay vì số field trong Protobuf, khiến thay đổi không tương thích ở wire format không được cảnh báo trước merge.
Ứng dụng muốn kiểm tra message size limit nhưng test chỉ gửi dữ liệu nhỏ, khiến upload nhiều MB bị từ chối ngay tại client trong production.
Đội thử response StatusRuntimeException bằng cách đọc code mà không kiểm tra trailers và structured details, khiến một lỗi quyền được hiển thị như lỗi chung trên mobile.
Một service đo latency chỉ từ lúc implementation handler bắt đầu đến lúc trả giá trị, khiến thời gian xếp hàng trong HTTP/2 và interceptor không xuất hiện trên dashboard.
Nhóm gắn metrics theo từng requestId vào nhãn gRPC method, khiến số lượng time series tăng nhanh và hệ thống quan sát bị quá tải.
Ứng dụng ghi status code tổng hợp cho tất cả RPC nhưng không phân biệt unary và streaming, khiến một stream dài bị hủy làm tỷ lệ lỗi so sánh giữa các method không chính xác.
Đội theo dõi số lần DEADLINE_EXCEEDED ở client mà không có trace phía server, khiến không xác định được thời gian mất tại network, queue hay database.
Một service gắn OpenTelemetry trace vào HTTP ingress nhưng gRPC client outbound không truyền context metadata, khiến một giao dịch bị chia thành nhiều trace rời rạc.
Nhóm đo payload bytes của unary RPC nhưng không tính lượng message trong client-streaming, khiến chi phí băng thông của một tenant lớn bị đánh giá thấp.
Ứng dụng phát logging interceptor cho mỗi message stream nhưng người dùng có thể gửi hàng nghìn message một giây, khiến logging chiếm CPU và tạo nhiều dữ liệu nhạy cảm.
Đội dùng histogram latency cho gRPC method nhưng không ghi method name đầy đủ sau khi đổi package Protobuf, khiến dashboard cũ trống dữ liệu dù traffic vẫn có.
Một service có nhiều ManagedChannels nhưng không theo dõi trạng thái CONNECTING, TRANSIENT_FAILURE và READY, khiến sự cố DNS chỉ được phát hiện qua tăng timeout.
Nhóm bật channelz để điều tra socket nhưng công cụ vận hành không có phân quyền phù hợp, khiến thông tin connection nội bộ bị xem bởi tài khoản không cần biết.
Ứng dụng theo dõi số kết nối gRPC active nhưng không theo dõi active streams, khiến một số ít kết nối HTTP/2 vẫn mang hàng nghìn luồng quá tải.
Đội thêm tracing interceptor trên server nhưng không gắn event cho onCancel, khiến những stream bị khách đóng sớm bị ghi như kết thúc bình thường.
Một service tính error rate từ response trailers nhưng gateway đôi lúc cắt kết nối trước trailers, khiến một phần thất bại bị đếm thành thiếu dữ liệu.
Nhóm báo availability bằng health SERVING nhưng client gọi method mới nhận UNIMPLEMENTED sau deploy, khiến chỉ số health không phản ánh hợp đồng RPC đang phục vụ.
Ứng dụng dùng cùng metric label cho tất cả các mã StatusRuntimeException, khiến cảnh báo không phân biệt quá tải RESOURCE_EXHAUSTED với lỗi phân quyền PERMISSION_DENIED.
Đội triển khai canary gRPC service nhưng chỉ đo request count chung, khiến tỷ lệ lỗi cao của một RPC hiếm bị che bởi các unary RPC phổ biến.
Một service deploy bản Protobuf mới đồng thời với nhiều client nhưng chưa có dashboard thống kê tỷ lệ UNIMPLEMENTED theo version, khiến lỗi tương thích chỉ được phát hiện qua hỗ trợ khách.
Nhóm có streaming RPC chạy qua đợt rollout và đo throughput bình quân, nhưng không theo dõi số phần tử đã ACK hoặc bị replay khiến nguy cơ trùng dữ liệu bị che khuất.
Ứng dụng cần đối soát từng lệnh quản trị từ gRPC với người gọi và trạng thái database, nhưng audit chỉ lưu timestamp của RPC mà không có correlation ID và kết quả cuối.
Đội muốn chứng minh gRPC API cho giao dịch tài chính có deadline, retry và error status nhất quán theo hợp đồng, nhưng nhiều service sử dụng interceptor và client policy khác nhau mà chưa có kiểm thử chung.
