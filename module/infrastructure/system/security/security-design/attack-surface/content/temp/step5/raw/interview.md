Anh/chị xác định bề mặt tấn công của một hệ thống gồm những thành phần và tương tác nào?
Làm thế nào xây dựng inventory tài sản đủ bao quát ứng dụng, API, hạ tầng, dữ liệu, danh tính và dịch vụ bên thứ ba?
Anh/chị xác định owner, mục đích nghiệp vụ, mức độ quan trọng và môi trường triển khai cho từng tài sản như thế nào?
Những nguồn dữ liệu nào giúp phát hiện tài sản chưa được đăng ký hoặc không còn người chịu trách nhiệm?
Anh/chị phân biệt tài sản đang hoạt động, tài sản dự phòng, tài sản ngừng sử dụng và tài sản bị bỏ quên ra sao?
Trong môi trường nhiều cloud account và subscription, anh/chị hợp nhất inventory mà vẫn giữ được ranh giới quản trị như thế nào?
Làm thế nào phát hiện domain, subdomain, IP, certificate và endpoint công khai mới xuất hiện ngoài quy trình thay đổi chính thức?
Anh/chị đánh giá mức độ phơi lộ của một tài sản dựa trên khả năng truy cập, dữ liệu xử lý và quyền mà nó nắm giữ như thế nào?
Những tiêu chí nào giúp phân biệt một điểm vào được dự kiến với một điểm vào không cần thiết hoặc không được quản lý?
Anh/chị kiểm kê các điểm vào từ web, mobile, API, webhook, remote access, admin console và giao thức quản trị ra sao?
Làm thế nào xác định endpoint cũ, API version không còn dùng hoặc giao diện quản trị vẫn mở trên Internet?
Anh/chị phát hiện các cổng mạng, dịch vụ và giao thức đang lắng nghe khác với cấu hình thiết kế bằng cách nào?
Khi một load balancer, reverse proxy hoặc API gateway định tuyến tới nhiều backend, anh/chị xác định đầy đủ điểm vào thực tế như thế nào?
Anh/chị đánh giá rủi ro từ endpoint chỉ dành cho nội bộ nhưng có thể truy cập qua VPN, peering hoặc mạng đối tác ra sao?
Những nguy cơ nào xuất hiện khi hệ thống có nhiều đường truy cập thay thế để phục vụ quản trị, hỗ trợ và khôi phục?
Anh/chị lập bản đồ luồng dữ liệu để xác định dữ liệu nhạy cảm đi qua những thành phần và vùng tin cậy nào như thế nào?
Làm thế nào nhận diện nơi dữ liệu được tạo, xử lý, lưu trữ, sao chép, xuất ra và xóa trong toàn bộ vòng đời?
Anh/chị xác định các trust boundary giữa trình duyệt, ứng dụng, API gateway, dịch vụ nội bộ, database và nhà cung cấp ra sao?
Những dấu hiệu nào cho thấy một trust boundary chỉ tồn tại trên sơ đồ nhưng không được thực thi bằng kiểm soát kỹ thuật?
Anh/chị đánh giá dữ liệu đi qua message broker, queue, event stream và batch file có thể mở thêm đường tấn công nào?
Làm thế nào theo dõi luồng dữ liệu khi một giao dịch đi qua nhiều microservice và nhiều vùng mạng khác nhau?
Anh/chị xác định nơi dữ liệu hoặc credential có thể vượt qua ranh giới tenant và môi trường như thế nào?
Khi một dịch vụ nhận dữ liệu từ nhiều nguồn có mức tin cậy khác nhau, anh/chị đánh giá các điểm chuyển đổi trust ra sao?
Anh/chị xây dựng attack graph từ tài sản, điểm vào, lỗ hổng, danh tính và quyền truy cập như thế nào?
Làm thế nào xác định một chuỗi tấn công có thể đi từ tài sản Internet-facing tới dữ liệu hoặc hệ thống quan trọng?
Những yếu tố nào giúp phân biệt một lỗ hổng riêng lẻ với một đường tấn công có thể dẫn tới tác động lớn?
Anh/chị đánh giá rủi ro kết hợp giữa misconfiguration, credential exposure và quyền quá rộng trong một attack path ra sao?
Khi có nhiều đường tấn công dẫn tới cùng tài sản quan trọng, anh/chị ưu tiên xử lý theo tiêu chí nào?
Anh/chị xác định blast radius nếu một tài khoản quản trị, workload identity hoặc dịch vụ trung gian bị chiếm quyền như thế nào?
Làm thế nào phát hiện một tài sản ít quan trọng trở thành bước đệm tới hệ thống có mức độ nhạy cảm cao?
Anh/chị đánh giá bề mặt tấn công của API dựa trên authentication, authorization, input, versioning và chức năng quản trị như thế nào?
Những cách nào giúp phát hiện API ẩn, endpoint không có tài liệu hoặc chức năng debug bị triển khai nhầm ra môi trường thật?
Anh/chị kiểm tra liệu schema, GraphQL introspection, API documentation hoặc error response có làm lộ thêm thông tin về hệ thống ra sao?
Khi API được gọi trực tiếp mà bỏ qua gateway, anh/chị xác định những kiểm soát nào có thể bị vượt qua như thế nào?
Anh/chị đánh giá bề mặt tấn công từ ứng dụng mobile, deep link, callback URL và các kênh giao tiếp với backend ra sao?
Những thành phần nào của cloud control plane, data plane, metadata service và public storage cần được đưa vào attack surface inventory?
Anh/chị phát hiện storage bucket, database, snapshot hoặc dashboard bị cấu hình công khai ngoài chủ đích như thế nào?
Làm thế nào đánh giá rủi ro từ container image, registry, orchestration API, Kubernetes dashboard và control plane endpoint?
Anh/chị xác định các đường truy cập tới workload thông qua service account, managed identity, metadata endpoint và secret store ra sao?
Khi một workload có thể truy cập nhiều subnet hoặc dịch vụ cloud, anh/chị đánh giá quyền di chuyển ngang như thế nào?
Anh/chị xem xét DNS, certificate, domain ownership và quy trình gia hạn để tìm các điểm yếu trong bề mặt Internet-facing ra sao?
Những rủi ro nào phát sinh từ subdomain takeover, DNS record cũ hoặc endpoint trỏ tới dịch vụ đã ngừng hoạt động?
Anh/chị đánh giá bề mặt tấn công của VPN, bastion, remote administration và kết nối giữa mạng đối tác như thế nào?
Làm thế nào xác định firewall rule, security group, network route và peering đang mở rộng phạm vi truy cập vượt nhu cầu?
Anh/chị phân tích tác động của một hệ thống flat network hoặc thiếu segmentation tới các đường tấn công như thế nào?
Những điểm vào nào có thể xuất hiện qua email, file upload, webhook, CI runner và công cụ hỗ trợ vận hành?
Anh/chị đưa nhà cung cấp SaaS, đối tác tích hợp và managed service vào sơ đồ trust boundary như thế nào?
Làm thế nào đánh giá rủi ro từ thư viện, package registry, build system, artifact repository và quy trình cập nhật dependency?
Anh/chị xác định một pipeline build hoặc deployment có thể trở thành đường truy cập vào production thông qua quyền và secret nào?
Khi một nhà cung cấp thay đổi endpoint, quyền tích hợp hoặc vùng xử lý dữ liệu, anh/chị cập nhật đánh giá attack surface ra sao?
Anh/chị phát hiện shadow IT, tài khoản cloud thử nghiệm và dịch vụ SaaS được triển khai ngoài quy trình phê duyệt bằng cách nào?
Những nguồn telemetry nào có thể hỗ trợ phát hiện tài sản mới, cổng mở, DNS thay đổi và cấu hình phơi lộ theo thời gian?
Làm thế nào phân biệt một thay đổi bề mặt tấn công hợp lệ với một thay đổi bất thường cần điều tra?
Anh/chị thiết lập baseline để theo dõi drift về endpoint, quyền truy cập, network exposure và cấu hình cloud như thế nào?
Những thay đổi nào cần kích hoạt đánh giá lại attack surface trước khi triển khai hoặc đưa tính năng mới vào sử dụng?
Anh/chị xác định phạm vi kiểm thử bề mặt tấn công để bao phủ đúng tài sản mà vẫn tránh ảnh hưởng dịch vụ như thế nào?
Làm thế nào phối hợp asset discovery, vulnerability scanning, penetration testing và threat modeling mà không xem chúng là các hoạt động thay thế nhau?
Anh/chị kiểm soát phạm vi và quyền cho phép khi kiểm thử tài sản do nhà cung cấp hoặc đối tác sở hữu như thế nào?
Khi scanner không thể xác minh một tài sản hoặc endpoint, anh/chị ghi nhận giới hạn coverage và xử lý khoảng trống đó ra sao?
Anh/chị đánh giá mức độ ưu tiên xử lý dựa trên khả năng bị khai thác, mức phơi lộ, giá trị tài sản và đường tấn công như thế nào?
Làm thế nào cân bằng việc giảm số lượng điểm vào với yêu cầu khả dụng, tích hợp đối tác và vận hành khẩn cấp?
Anh/chị quyết định khi nào nên đóng endpoint, khi nào cần giới hạn truy cập và khi nào phải bổ sung lớp kiểm soát như thế nào?
Những bằng chứng nào chứng minh một điểm vào đã được loại bỏ hoặc một đường tấn công đã bị ngắt thực sự?
Anh/chị kiểm tra các đường truy cập dự phòng và cơ chế rollback để bảo đảm chúng không vô tình mở lại bề mặt đã được thu hẹp ra sao?
Làm thế nào duy trì trách nhiệm owner và thời hạn xử lý cho các tài sản không rõ nguồn gốc hoặc không còn được sử dụng?
Anh/chị đo lường hiệu quả chương trình attack surface management bằng những chỉ số nào ngoài số lượng tài sản đã phát hiện?
Những thông tin nào cần được báo cáo cho lãnh đạo để thể hiện thay đổi về exposure, attack paths và rủi ro còn lại?
Anh/chị đưa bài học từ incident, threat intelligence và hoạt động red team vào quy trình cập nhật attack surface như thế nào?
