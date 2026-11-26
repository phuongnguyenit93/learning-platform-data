Một ứng dụng thương mại điện tử có web, mobile và đối tác cùng gọi nhiều microservice; mỗi client đang giữ riêng danh sách địa chỉ backend, nên sau khi dịch vụ đơn hàng đổi địa chỉ thì chỉ một số client gửi request thành công.
Gateway định tuyến tiền tố /api/orders sang dịch vụ đơn hàng và /api/orders/history sang dịch vụ lịch sử; sau khi thêm route mới, request lịch sử đôi lúc đi vào dịch vụ đơn hàng vì thứ tự và độ ưu tiên quy tắc khớp đường dẫn.
API phiên bản cũ dùng /v1/customers còn phiên bản mới dùng /v2/customers; khi công bố bản mới qua gateway, một số request vẫn đi về backend cũ dù URL có tiền tố phiên bản mới.
Hệ thống cho phép GET và POST trên cùng đường dẫn /orders nhưng chuyển hai phương thức đến backend khác nhau; request tạo đơn bị chuyển nhầm tới dịch vụ chỉ hỗ trợ đọc sau một lần thay đổi chính sách route.
Nền tảng dùng cùng địa chỉ gateway cho nhiều tenant dựa vào tên miền; request của khách hàng doanh nghiệp A đôi lúc bị định tuyến sang môi trường của doanh nghiệp B khi cấu hình host matching được cập nhật.
Một endpoint nhận cả đường dẫn thường và đường dẫn có dấu gạch chéo cuối; khi chuyển qua gateway mới, một số client nhận 404 chỉ vì cách chuẩn hóa đường dẫn khác với backend.
Gateway loại bỏ tiền tố /public trước khi chuyển tiếp request, nhưng backend lại mong nhận đầy đủ /public; sau phát hành, nhiều endpoint tạo và tra cứu trả 404 dù kiểm thử gọi thẳng backend vẫn đạt.
Một đối tác gửi đường dẫn chứa ký tự được mã hóa phần trăm; gateway và backend giải mã hoặc chuẩn hóa URL theo cách khác nhau, dẫn đến kết quả định tuyến không nhất quán với kiểm tra quyền truy cập.
Gateway thêm tham số ngôn ngữ mặc định vào request tìm kiếm, nhưng khi client đã có tham số ngôn ngữ, backend nhận hai giá trị và trả kết quả khác giữa ứng dụng web và mobile.
Nhóm chuyển đổi tên header phiên bản API ở gateway; một phần request bị mất giá trị định tuyến khi header gốc có cách viết chữ hoa khác nhau.
Dịch vụ báo cáo cần IP gốc của client để kiểm toán, nhưng sau khi đi qua cân bằng tải và gateway, log backend chỉ hiển thị IP của proxy và việc đọc X-Forwarded-For chưa có quy tắc nguồn tin cậy.
Gateway nhận request từ nhiều lớp proxy; một client tự gửi header X-Forwarded-For giả làm IP nội bộ và chính sách giới hạn truy cập theo dải IP cho kết quả sai.
Ứng dụng web gọi API từ miền khác; các request GET hoạt động nhưng request có Authorization header bị trình duyệt chặn từ bước preflight OPTIONS sau khi gateway đổi cấu hình CORS.
Gateway trả Access-Control-Allow-Origin dạng wildcard cho endpoint sử dụng cookie phiên đăng nhập; trình duyệt không cho ứng dụng đọc response dù backend đã xác thực request thành công.
Ứng dụng chat dùng WebSocket qua gateway; phiên kết nối được mở thành công trong môi trường thử nghiệm nhưng production thường bị ngắt khi thời gian không có tin nhắn vượt ngưỡng của proxy.
Dịch vụ nội bộ dùng gRPC streaming qua cùng gateway HTTP; các request ngắn chạy được nhưng luồng truyền dữ liệu kéo dài thường kết thúc sớm do chính sách timeout chưa phù hợp.
Người dùng tải tệp video dung lượng lớn qua gateway; một số request bị trả 413 dù backend hỗ trợ kích thước tệp đó và nhóm vận hành chưa xác định giới hạn nằm ở lớp nào.
Hệ thống tải tệp theo luồng nhưng gateway đệm toàn bộ body trước khi chuyển tiếp; khi nhiều người dùng tải lên cùng lúc, bộ nhớ gateway tăng mạnh và thời gian backend nhận byte đầu bị kéo dài.
Gateway chuẩn hóa response lỗi của các dịch vụ thành cùng một cấu trúc JSON; trong đợt sự cố, mã lỗi nghiệp vụ do backend trả về bị thay thế làm client không phân biệt được lỗi nhập liệu và lỗi hạ tầng.
Ứng dụng trả thông tin sản phẩm qua gateway có bước biến đổi response; khi thêm nhiều trường lớn vào payload, CPU gateway tăng và p95 tăng dù thời gian truy vấn ở backend không đổi.
Client mang JWT hợp lệ nhưng vừa hết hạn ở thời điểm gateway kiểm tra; nhiều request nhận 401 vào thời điểm chuyển ngày vì đồng hồ giữa thiết bị, gateway và nhà phát hành token lệch nhau.
Nhà cung cấp danh tính xoay khóa ký JWT; một phần instance gateway tiếp tục giữ bộ khóa công khai cũ và từ chối token mới trong khi các instance khác vẫn xác thực thành công.
Gateway kiểm tra chữ ký token và cho phép mọi người dùng đã đăng nhập gọi API xóa đơn hàng; backend yêu cầu vai trò quản trị nhưng nhóm phát triển tưởng xác thực tại gateway đã đủ để bảo vệ thao tác.
Một endpoint đăng nhập cần được truy cập công khai nhưng chính sách xác thực mặc định mới áp dụng cho toàn bộ nhóm route; người dùng chưa có token không thể lấy token lần đầu.
Dịch vụ nội bộ từng chỉ nhận request qua gateway, nhưng sau thay đổi mạng một endpoint backend có thể được gọi trực tiếp và bỏ qua giới hạn lưu lượng cũng như kiểm tra token ở gateway.
Gateway chấp nhận API key dành cho đối tác và gắn user-id mặc định vào request; backend phân quyền theo người dùng cuối và bắt đầu ghi nhận thao tác không đúng danh tính thực tế.
Hệ thống B2B sử dụng mTLS từ client tới gateway; sau đợt xoay chứng chỉ của đối tác, một số request bị ngắt ở bước bắt tay TLS trong khi backend không ghi nhận request nào.
Gateway xác thực JWT rồi chuyển tiếp các header định danh sang backend; một tuyến cấu hình thiếu bước loại bỏ header do client tự cung cấp, khiến backend có nguy cơ tin dữ liệu định danh chưa được gateway xác minh.
Nền tảng nhiều tenant gắn tenant-id bằng header của client; gateway chỉ kiểm tra người dùng đã đăng nhập mà không kiểm tra quan hệ giữa tenant-id với token, làm xuất hiện request truy cập sai phạm vi dữ liệu.
Gateway giới hạn 100 request mỗi phút theo IP; hàng nghìn nhân viên ở một văn phòng cùng dùng địa chỉ NAT nên nhiều người bình thường nhận 429 dù mỗi người gửi rất ít request.
Chính sách rate limiting theo user-id áp dụng cho API tìm kiếm; khi client chưa đăng nhập, hàng loạt request bị gom vào cùng một khóa rỗng và người dùng mới bị chặn lẫn nhau.
Một ứng dụng cho phép burst 20 request trong vài giây nhưng cần giới hạn mức trung bình theo phút; hệ thống hiện trả 429 ngay khi người dùng mở màn hình gọi nhiều API đồng thời.
Gateway chạy trên 12 replica nhưng bộ đếm rate limit được giữ riêng trong bộ nhớ từng replica; cùng một API key có thể gửi tổng lưu lượng vượt xa hạn mức công bố khi request được phân phối đều.
Kho lưu bộ đếm rate limit dùng chung không sẵn sàng trong vài phút; các replica gateway xử lý request khác nhau và nhóm vận hành chưa có hành vi thống nhất cho trường hợp không kiểm tra được hạn mức.
Nền tảng có gói miễn phí và trả phí với quota khác nhau; sau khi khách nâng gói, gateway vẫn dùng cấu hình hạn mức cũ và tiếp tục trả 429 cho các thao tác hợp lệ.
Một đối tác gửi số lượng request hợp lệ rất cao qua route tạo báo cáo; dù chính sách rate limit tổng còn dư, backend báo cáo bị bão hòa và ảnh hưởng các endpoint giao dịch cùng dùng tài nguyên.
Gateway trả 429 cho client tự động gửi lại ngay lập tức; trong giờ cao điểm, số request lặp tăng mạnh vì response không truyền đủ thông tin giúp client biết khi nào có thể thử lại.
Gateway phân phối request đều cho bốn backend nhưng một instance đã báo không sẵn sàng; người dùng thỉnh thoảng nhận 502 vì instance đó vẫn nằm trong danh sách đích.
Đội vận hành dùng weighted routing để chuyển 10% lưu lượng sang phiên bản backend mới; do một số phiên người dùng thực hiện nhiều request hơn hẳn, kết quả theo số người dùng và theo số request chênh lệch đáng kể.
Một chiến dịch tạo đơn hàng yêu cầu các bước liên tiếp đọc cùng trạng thái phiên lưu trong bộ nhớ của một backend cũ; khi gateway phân phối từng request sang backend khác, giỏ hàng của khách hiển thị không nhất quán.
Gateway lấy danh sách backend từ service discovery; một instance mới vừa khởi động đã được định tuyến vào dù chưa sẵn sàng kết nối cơ sở dữ liệu, dẫn tới lỗi ngắt quãng sau mỗi lần autoscale.
Một vùng hạ tầng mất kết nối đến dịch vụ thanh toán nhưng health check của gateway vẫn nhận 200 từ endpoint chỉ kiểm tra tiến trình; request thanh toán tiếp tục được gửi tới vùng lỗi.
Gateway giữ quá nhiều kết nối nhàn rỗi tới upstream trong khi backend có giới hạn socket thấp; vào giờ cao điểm, kết nối mới bị từ chối dù CPU backend còn thấp.
Gateway đặt thời gian chờ upstream là 3 giây còn API xuất báo cáo thường mất 20 giây; client liên tục nhận 504 dù backend cuối cùng vẫn hoàn tất xử lý.
Client chỉ cho phép tổng thời gian 5 giây nhưng gateway có nhiều lần thử lại, mỗi lần chờ upstream tới 4 giây; request thường kết thúc sau khi client đã hủy và gateway vẫn giữ tài nguyên.
Gateway tự động retry POST tạo giao dịch khi kết nối đứt trước khi nhận response; một khách hàng bị ghi nhận hai giao dịch vì lần gửi đầu đã thành công ở backend.
Trong đợt sự cố, backend trả 503 và gateway thử lại cùng request nhiều lần trên các instance khác; tổng số request đi vào cụm backend tăng đúng lúc hệ thống đang quá tải.
Gateway ngắt request và trả 504 sau khi chờ thao tác ghi quá lâu; vài giây sau backend vẫn commit thành công, khiến người dùng thử lại và nhìn thấy hai bản ghi.
Một dịch vụ trả 502 ngắt quãng khi một upstream reset kết nối, trong khi một dịch vụ khác chủ động trả 500 khi xử lý lỗi; dashboard hiện gộp tất cả vào cùng một chỉ số lỗi 5xx.
Trong giờ cao điểm, circuit breaker ở gateway mở do tỷ lệ lỗi upstream tăng; một phần tuyến dự phòng cũng trở nên quá tải vì lưu lượng được chuyển dồn mà không có giới hạn bổ sung.
Một API quản lý kho có thời gian phản hồi ngắn nhưng đôi lúc trả 409 do xung đột nghiệp vụ; cấu hình gateway tính mọi response không phải 2xx là lỗi hạ tầng và liên tục ngắt route này.
Gateway có chính sách cache response GET danh mục sản phẩm; khi thay giá ở backend, một số khách hàng vẫn nhìn thấy giá cũ trên nhiều thiết bị vì thời hạn cache chưa phù hợp.
Gateway cache kết quả GET thông tin tài khoản theo đường dẫn nhưng thiếu thành phần danh tính trong cache key; hai người dùng truy cập cùng URL nhận dữ liệu cá nhân không thuộc tài khoản của mình.
Gateway thêm route canary cho phiên bản backend mới; cùng một URL trả hai cấu trúc response khác nhau nên ứng dụng mobile phiên bản cũ có lỗi phân tích dữ liệu với nhóm request được chuyển sang canary.
Đội triển khai thay đổi hàng loạt chính sách route, xác thực và timeout cùng lúc; sau phát hành xuất hiện lỗi 401 và 504 xen kẽ nhưng không có cách đối chiếu phiên bản cấu hình gây thay đổi hành vi.
Hệ thống có gateway ở hai vùng nhưng tập quy tắc CORS và rate limit khác nhau; người dùng chuyển vùng sau failover thấy cùng request lúc thành công lúc nhận 403 hoặc 429.
Gateway trở thành điểm vào duy nhất của nhiều dịch vụ nhưng chỉ chạy ở một vùng khả dụng; khi hạ tầng vùng đó lỗi, toàn bộ ứng dụng không thể gọi API dù các backend ở vùng khác vẫn hoạt động.
Gateway ghi log request và response body để hỗ trợ debug; sau khi bật theo dõi lỗi đăng nhập, log chứa token và dữ liệu cá nhân mà nhóm vận hành khác cũng có quyền đọc.
Nhóm gắn nguyên đường dẫn chứa mã đơn hàng vào nhãn metric của gateway; số lượng chuỗi thời gian tăng mạnh và dashboard giám sát tiêu thụ nhiều tài nguyên khi lưu lượng lớn.
Dashboard cho thấy p99 qua gateway tăng lên 2 giây nhưng p99 tại backend chỉ khoảng 200 ms; hiện chưa có metric tách thời gian nhận request, xử lý chính sách, chờ kết nối và chờ upstream.
Một request đi qua gateway rồi tới dịch vụ đơn hàng và thanh toán; khi thanh toán chậm, trace bị đứt ở ranh giới gateway vì correlation-id không được chuyển tiếp nhất quán.
Gateway ghi nhận nhiều request 499 khi ứng dụng mobile mất mạng, còn backend tiếp tục xử lý các tác vụ tốn tài nguyên; nhóm chưa biết tại thời điểm client hủy thì tiến trình downstream đang ở trạng thái nào.
Một đội muốn chuyển toàn bộ kiểm tra tồn kho và tính chiết khấu vào gateway để giảm một lần gọi backend; logic thay đổi thường xuyên và phụ thuộc dữ liệu giao dịch của nhiều dịch vụ.
Dịch vụ đơn hàng trả 422 cho trường nhập không hợp lệ nhưng gateway đổi mọi 4xx thành 400; ứng dụng web không còn phân biệt tình huống nhập sai dữ liệu với không có quyền truy cập.
Một khách hàng doanh nghiệp gửi lượng truy cập tăng gấp mười trong giờ khuyến mãi; chính sách giới hạn chung ở gateway chặn cả API thanh toán quan trọng lẫn endpoint tra cứu ít ưu tiên.
