Một tính năng nhập ảnh đại diện cho phép người dùng cung cấp URL; backend tải URL đó nhưng chỉ kiểm tra chuỗi bắt đầu bằng https, nên một địa chỉ nội bộ vẫn được chấp nhận sau khi parser chuẩn hóa URL.
Một webhook tester chặn URL có hostname localhost nhưng bỏ qua các biểu diễn IPv4 rút gọn và địa chỉ IPv6 loopback, khiến request vẫn tới dịch vụ trên chính máy chủ.
Một dịch vụ tạo preview website kiểm tra hostname bằng allowlist trước khi phân giải DNS; sau đó hostname được phân giải thành địa chỉ private do bản ghi DNS thay đổi giữa hai bước.
Một hệ thống chống SSRF kiểm tra DNS lần đầu nhưng HTTP client tự phân giải hostname lần nữa khi mở kết nối, cho phép câu trả lời DNS khác đưa request vào mạng nội bộ.
Một dịch vụ fetch URL chỉ kiểm tra địa chỉ A đầu tiên trong DNS response; hostname có thêm bản ghi AAAA hoặc địa chỉ thứ hai thuộc mạng private nhưng vẫn được HTTP client lựa chọn.
Một ứng dụng cho phép truy cập hostname công khai có CNAME trỏ qua nhiều lớp; một lớp trung gian bị thay đổi khiến đích cuối cùng phân giải vào dải địa chỉ nội bộ.
Một bộ lọc SSRF từ chối dải IPv4 private nhưng không xét IPv4-mapped IPv6, địa chỉ link-local và các dải đặc biệt không thể định tuyến công khai.
Một API import dữ liệu chặn IP private theo CIDR nhưng nhận địa chỉ IPv6 với dạng rút gọn hoặc zone identifier mà thư viện kiểm tra không chuẩn hóa đúng.
Một URL có userinfo và ký tự @ khiến validator tách hostname khác với HTTP client; allowlist xác nhận nhầm phần trước dấu @ là host đích.
Một bộ lọc URL kiểm tra chuỗi trước khi percent-decode; các ký tự mã hóa trong hostname hoặc path làm parser và validator hiểu khác nhau.
Một tính năng tải tài liệu chỉ cho phép cổng 443 nhưng URL được diễn giải qua dạng port mặc định hoặc dấu phân cách bất thường, khiến request tới cổng quản trị khác.
Một backend chấp nhận scheme https và http nhưng thư viện URL cũng hỗ trợ file hoặc giao thức khác; đầu vào được chuyển sang client tổng quát và truy cập tài nguyên ngoài dự kiến.
Một dịch vụ preview chặn hostname bằng regex nhưng không xử lý đúng dấu chấm cuối, chữ hoa, IDN và Punycode, tạo ra cách viết khác của cùng tên miền bị cấm.
Một hệ thống allowlist kiểm tra hậu tố domain bằng phép so sánh chuỗi đơn giản; hostname có thêm phần tên miền gây nhầm lẫn vẫn vượt qua điều kiện.
Một API tạo thumbnail theo URL cho phép redirect tự động; URL công khai chuyển hướng sang địa chỉ loopback và HTTP client tiếp tục request mà không kiểm tra lại đích.
Một dịch vụ tải file kiểm tra redirect đầu tiên nhưng không giới hạn số lần redirect; chuỗi chuyển hướng nhiều bước kết thúc ở một địa chỉ thuộc mạng quản trị.
Một HTTP client giữ nguyên Authorization header khi redirect sang origin khác, làm token của dịch vụ bị gửi tới máy chủ do người dùng kiểm soát.
Một webhook delivery service chuyển tiếp cookie và header tùy chỉnh qua redirect cross-origin, khiến credential nội bộ bị rò rỉ sang endpoint bên ngoài.
Một dịch vụ kiểm tra URL chỉ xác minh hostname ban đầu; redirect dùng scheme khác hoặc hạ từ HTTPS xuống HTTP khiến nội dung và thông tin xác thực không còn được bảo vệ như dự kiến.
Một tính năng tải ảnh cho phép redirect tới URL có userinfo hoặc hostname mới nhưng không áp dụng lại chính sách allowlist cho từng hop.
Một backend fetch URL dùng TLS nhưng tắt xác minh certificate để xử lý chứng chỉ tự ký của đối tác, khiến kết nối outbound có thể bị chặn giữa đường.
Một HTTP client chỉ kiểm tra certificate chain mà không xác minh hostname; chứng chỉ hợp lệ của một domain khác vẫn được chấp nhận cho đích nhạy cảm.
Một ứng dụng tích hợp API đối tác chấp nhận mọi certificate trong môi trường staging và cấu hình đó vô tình được đóng gói sang production.
Một dịch vụ gọi API nội bộ dùng mTLS nhưng chia sẻ cùng client certificate cho nhiều workload; khi một workload bị xâm nhập, danh tính chung không thể được thu hồi riêng.
Một hệ thống proxy outbound kết thúc TLS và ghi request body để debug; payload chứa access token và dữ liệu cá nhân được lưu trong log tập trung.
Một ứng dụng gọi API đối tác tự động gắn Authorization header mặc định cho mọi request; khi người dùng điều khiển URL, token dịch vụ được gửi tới host không tin cậy.
Một dịch vụ webhook cho phép người dùng cấu hình endpoint nhưng gửi kèm header nội bộ chứa tenant secret và định danh tài khoản trong mọi lần retry.
Một hệ thống tải tài liệu chuyển tiếp toàn bộ header từ request inbound sang URL do người dùng cung cấp, vô tình làm lộ cookie phiên và bearer token.
Một worker xử lý URL sử dụng proxy từ biến môi trường HTTP_PROXY; cấu hình môi trường bị thay đổi khiến toàn bộ request outbound đi qua proxy không được phê duyệt.
Một container có chính sách egress giới hạn subnet nhưng vẫn truy cập được metadata endpoint thông qua route đặc biệt của nền tảng cloud.
Một workload trong Kubernetes không có NetworkPolicy egress; lỗ hổng SSRF ở chức năng import ảnh cho phép truy cập Kubernetes API và các dịch vụ nội bộ.
Một API gateway áp dụng allowlist outbound nhưng backend có thể kết nối trực tiếp ra Internet qua interface khác, khiến chính sách gateway bị bỏ qua.
Một dịch vụ chỉ cho phép outbound đến domain đối tác nhưng firewall cho phép toàn bộ cổng và giao thức; máy chủ bị khai thác có thể dùng kênh khác để rò rỉ dữ liệu.
Một worker tải nội dung URL chạy cùng network namespace với database và control plane, nên một lỗi SSRF trong worker mở rộng thành khả năng dò quét toàn mạng nội bộ.
Một hệ thống webhook có thể gọi địa chỉ do tenant cấu hình nhưng không phân tách tenant network; một tenant dùng endpoint nội bộ để thăm dò dịch vụ của tenant khác.
Một tính năng callback cho phép URL đích thay đổi sau khi đã được phê duyệt; kẻ quản trị tenant sửa DNS hoặc cấu hình endpoint trước lúc tác vụ nền thực thi.
Một job scheduler lưu URL để xử lý sau vài giờ; hostname hợp lệ lúc tạo job nhưng DNS thay đổi trước thời điểm worker thực hiện request.
Một dịch vụ fetch URL giới hạn response body theo Content-Length; máy chủ đích không gửi Content-Length hoặc stream dữ liệu vô hạn khiến worker cạn bộ nhớ và kết nối.
Một API import đặt timeout cho kết nối ban đầu nhưng không giới hạn thời gian đọc body; máy chủ bên ngoài gửi từng byte rất chậm và giữ worker bận trong thời gian dài.
Một HTTP client tự động retry request POST sau timeout; endpoint đối tác đã xử lý lần đầu nhưng phản hồi bị mất, dẫn đến giao dịch hoặc hành động được thực hiện nhiều lần.
Một dịch vụ gọi API bên ngoài dùng connection pool lâu dài; DNS của đối tác đã thay đổi nhưng connection cũ tiếp tục được tái sử dụng và không còn đi qua tuyến mạng mong muốn.
Một hệ thống fetch nội dung theo URL tự động giải nén gzip mà không giới hạn kích thước sau giải nén, khiến response nhỏ tạo ra dữ liệu lớn và chiếm hết bộ nhớ.
Một ứng dụng đọc response JSON từ đối tác và parse toàn bộ vào RAM; đối tác hoặc endpoint bị chiếm quyền trả về cấu trúc lồng sâu và payload lớn gây CPU exhaustion.
Một dịch vụ tạo bản xem trước trang web giữ lại response không giới hạn và ghi toàn bộ nội dung vào object storage, làm phát sinh chi phí và lưu trữ dữ liệu nhạy cảm ngoài dự kiến.
Một nền tảng webhook không giới hạn số endpoint hoặc tần suất callback; tenant tạo hàng nghìn URL khiến worker outbound cạn connection pool và ảnh hưởng tích hợp hợp lệ.
Một dịch vụ gửi webhook không ký payload và không xác minh đích đến sau redirect; endpoint nhận có thể bị giả mạo hoặc nội dung callback bị chuyển tới hệ thống khác.
Một hệ thống gửi webhook ký request nhưng dùng timestamp quá rộng và không lưu nonce hoặc delivery ID, khiến request cũ có thể được phát lại để lặp hành động.
Một chức năng nhập feed RSS cho phép URL nguồn tùy ý; parser theo redirect và tải enclosure từ các host khác mà không kiểm tra lại chính sách đích đến.
Một dịch vụ chuyển đổi HTML sang PDF tải ảnh, font và stylesheet từ URL trong tài liệu; tài nguyên nhúng khiến renderer truy cập mạng nội bộ và metadata service.
Một hệ thống gửi email cho phép URL ảnh từ xa; dịch vụ render email tải tài nguyên trước khi gửi và vô tình tiết lộ địa chỉ IP, token hoặc trạng thái truy cập nội bộ.
Một ứng dụng tích hợp OAuth gọi token endpoint theo issuer URL do tenant cấu hình; issuer độc hại nhận client secret vì hệ thống không ràng buộc đích đến với danh sách nhà cung cấp đã đăng ký.
Một hệ thống đồng bộ cloud storage nhận endpoint S3-compatible tùy chỉnh nhưng không kiểm tra hostname, certificate và redirect, khiến credential lưu trữ bị gửi đến máy chủ giả mạo.
Một dịch vụ outbound ghi log URL đầy đủ; URL chứa signed query parameter và token truy cập bị sao chép vào log, tracing và hệ thống hỗ trợ.
Một hệ thống giám sát chỉ đếm request outbound thành công và thất bại mà không lưu hostname đã chuẩn hóa, IP đích, redirect chain và policy decision, khiến điều tra SSRF khó xác định phạm vi.
Một đội vận hành phát hiện worker gửi request bất thường tới nhiều IP private nhưng không có correlation ID giữa job, tenant, URL gốc và DNS resolution để truy nguyên nguồn phát sinh.
