Trong kiến trúc microservice, Kong Gateway giải quyết những nhu cầu nào về định tuyến, bảo mật và quản trị lưu lượng API?
Bạn phân biệt vai trò của Kong Gateway với reverse proxy và service mesh dựa trên những yêu cầu triển khai nào?
Một HTTP request đi qua Kong Gateway từ client đến upstream và quay về theo các bước chính nào?
Bạn giải thích mối quan hệ giữa Service, Route, Upstream, Target, Consumer và Plugin trong mô hình cấu hình của Kong như thế nào?
Bạn phân biệt cổng proxy phục vụ client với Admin API của Kong về mục đích sử dụng và cách giới hạn truy cập như thế nào?
Bạn lựa chọn cách triển khai Kong có database, DB-less hoặc hybrid dựa trên yêu cầu vận hành nào?
Trong chế độ hybrid, bạn mô tả vai trò của control plane và data plane đối với cấu hình và xử lý request như thế nào?
Bạn đánh giá ảnh hưởng của việc data plane tạm mất kết nối với control plane đến việc phục vụ lưu lượng ra sao?
Bạn chuẩn bị những cấu hình tối thiểu nào để đưa một API nội bộ ra ngoài qua Kong?
Bạn xác định Kong Service đại diện cho hệ thống backend như thế nào và chọn địa chỉ upstream dựa trên tiêu chí gì?
Bạn tạo một Route khớp theo host, path và phương thức HTTP cho từng nhóm API như thế nào?
Bạn phân biệt các trường hợp cần route theo header, host, path hoặc method để tránh nhập nhằng định tuyến ra sao?
Bạn chẩn đoán thế nào khi một request không khớp Route nào và Kong trả phản hồi không mong đợi?
Khi nhiều Route có điều kiện trùng hoặc chồng lấn, bạn kiểm tra cơ chế ưu tiên và quyết định Route khớp như thế nào?
Bạn đánh giá các ảnh hưởng của strip_path và path_handling đối với URI mà backend nhận được ra sao?
Bạn xử lý tình huống upstream cần đường dẫn khác với đường dẫn public API bằng cách cấu hình Kong như thế nào?
Bạn lựa chọn giữ hoặc thay đổi Host header khi proxy tới backend dựa trên yêu cầu nào?
Bạn xác định lúc nào cần chuyển tiếp thông tin client qua các header và làm thế nào để tránh tin dữ liệu do client giả mạo?
Bạn cấu hình và kiểm tra proxy request HTTP, HTTPS hoặc WebSocket trong những điều kiện nào?
Bạn tổ chức Route cho nhiều phiên bản API để dịch chuyển client sang phiên bản mới mà không gây gián đoạn như thế nào?
Bạn chọn mô hình dùng nhiều Service hay nhiều Route khi một backend phục vụ nhiều giao diện API ra sao?
Bạn thiết kế tên và quy ước gắn tag cho Service, Route và Plugin để dễ kiểm toán cấu hình như thế nào?
Bạn điều tra thế nào khi Kong định tuyến thành công nhưng phản hồi của backend có mã trạng thái không như mong đợi?
Bạn phân biệt lỗi phát sinh tại gateway với lỗi do upstream trả về bằng log, header và thời gian xử lý như thế nào?
Upstream và Target trong Kong giúp tách cấu hình Route khỏi danh sách backend thực tế như thế nào?
Bạn lựa chọn chính sách cân bằng tải cho các Target dựa trên mức tải và đặc tính phiên làm việc như thế nào?
Bạn phân bố trọng số Target để triển khai canary hoặc chuyển dần lưu lượng sang backend mới ra sao?
Bạn sử dụng health check chủ động và thụ động cho Upstream trong các trường hợp nào?
Bạn chọn ngưỡng thành công, thất bại và khoảng thời gian kiểm tra sức khỏe backend như thế nào?
Khi Kong đánh dấu một Target không khỏe, bạn điều tra nguyên nhân từ gateway, mạng và ứng dụng backend ra sao?
Bạn nhận diện sự khác biệt giữa backend phản hồi chậm, backend từ chối kết nối và backend không thể phân giải DNS như thế nào?
Bạn đánh giá tác động của DNS cache và việc thay đổi địa chỉ backend đến quá trình định tuyến ra sao?
Bạn cấu hình connect timeout, read timeout và write timeout theo SLA của API như thế nào?
Bạn lựa chọn retry cho request thất bại dựa trên phương thức HTTP và khả năng xử lý lặp lại an toàn của backend ra sao?
Bạn kiểm tra nguy cơ retry làm tăng tải lên upstream khi hệ thống đang quá tải như thế nào?
Bạn giải quyết tình huống backend cần sticky session nhưng hạ tầng phía sau gateway thay đổi liên tục ra sao?
Bạn lập thử nghiệm nào để xác nhận cân bằng tải và chuyển hướng khi một Target bị loại khỏi Upstream?
Bạn thiết kế cấu hình TLS giữa client và Kong để bảo vệ API công khai như thế nào?
Bạn quyết định khi nào cần xác minh chứng chỉ TLS hoặc dùng mTLS giữa Kong và upstream dựa trên mô hình tin cậy nào?
Bạn quản lý vòng đời chứng chỉ, khóa và thay đổi endpoint HTTPS để tránh gián đoạn lưu lượng ra sao?
Consumer trong Kong thể hiện danh tính của đối tượng sử dụng API như thế nào và khác với người dùng ứng dụng ra sao?
Bạn lựa chọn cơ chế key authentication, basic authentication, JWT hoặc OIDC dựa trên yêu cầu bảo mật nào?
Bạn thiết kế quy trình cấp phát, luân chuyển và thu hồi API key cho Consumer như thế nào?
Bạn kiểm soát việc truyền và lưu trữ thông tin xác thực để không xuất hiện bí mật trong log hoặc repository ra sao?
Bạn phân biệt xác thực danh tính với phân quyền truy cập từng API trong cấu hình Kong như thế nào?
Bạn xây dựng quy tắc phân quyền theo Consumer hoặc nhóm Consumer bằng plugin thích hợp ra sao?
Bạn giải thích luồng kiểm tra JWT và xử lý token hết hạn hoặc chữ ký không hợp lệ trong gateway như thế nào?
Bạn cân nhắc xác thực tại Kong và xác thực tiếp tại backend để đáp ứng những ranh giới bảo mật nào?
Bạn phân tích rủi ro khi gateway truyền thông tin người dùng đã xác thực cho backend bằng header như thế nào?
Bạn cấu hình bảo vệ một Route riêng mà vẫn cho phép một số Route công khai như thế nào?
Bạn thiết kế cách kiểm thử trường hợp thiếu credential, credential sai và Consumer không có quyền như thế nào?
Plugin của Kong có thể được gắn ở những phạm vi nào và thứ tự áp dụng ảnh hưởng đến request ra sao?
Bạn quyết định gắn plugin ở phạm vi global, Service, Route hoặc Consumer theo chính sách nào?
Khi nhiều cấu hình plugin có cùng tên được áp dụng ở các phạm vi khác nhau, bạn xác định cấu hình có hiệu lực như thế nào?
Bạn lựa chọn plugin rate limiting để bảo vệ upstream theo IP, Consumer hoặc credential dựa trên mục tiêu nào?
Bạn thiết kế ngưỡng giới hạn theo giây, phút hoặc khoảng thời gian dài để cân bằng công bằng và trải nghiệm client như thế nào?
Bạn phân biệt rate limiting với kiểm soát số kết nối đồng thời hoặc giới hạn tài nguyên backend ra sao?
Bạn đánh giá độ chính xác của giới hạn lưu lượng khi có nhiều Kong instance hoặc nhiều vùng triển khai như thế nào?
Bạn kiểm thử phản hồi khi vượt giới hạn lưu lượng và hướng dẫn client retry một cách phù hợp như thế nào?
Bạn nhận diện và xử lý trường hợp nhiều client dùng chung IP khiến chính sách rate limit theo IP thiếu công bằng ra sao?
Bạn lựa chọn plugin CORS cho từng loại API và kiểm tra những origin, method, header được cho phép như thế nào?
Bạn sử dụng plugin biến đổi request hoặc response trong trường hợp nào và phòng tránh làm sai hợp đồng API ra sao?
Bạn chọn phương án kiểm soát kích thước request và nội dung gửi lên để giảm rủi ro quá tải backend như thế nào?
Bạn thiết kế cơ chế correlation ID để theo dõi cùng một request qua gateway và các service phía sau ra sao?
Bạn lựa chọn plugin ghi log và metric dựa trên yêu cầu truy vết, hiệu năng và bảo vệ dữ liệu nhạy cảm như thế nào?
Bạn đánh giá rủi ro và quy trình kiểm thử khi cài plugin tùy biến hoặc plugin bên thứ ba vào Kong ra sao?
Bạn kiểm tra cách thực thi plugin theo các phase xử lý request và response khi nhiều plugin cùng hoạt động như thế nào?
Bạn phân biệt cách cấu hình Kong qua Admin API, file khai báo và công cụ decK về khả năng kiểm soát thay đổi như thế nào?
Bạn tổ chức cấu trúc file cấu hình decK để quản lý Service, Route, Consumer và Plugin dễ review như thế nào?
Bạn sử dụng các thao tác diff, validate và sync của decK theo trình tự nào trước khi cập nhật môi trường dùng chung?
Bạn phân tích những thay đổi dự kiến bị tạo, cập nhật hoặc xóa từ kết quả diff trước khi chạy sync như thế nào?
Bạn đánh giá rủi ro khi đồng bộ một cấu hình decK thiếu tài nguyên đang tồn tại trên gateway ra sao?
Bạn sử dụng tag hoặc cơ chế phân phạm vi của decK để các nhóm quản lý những phần cấu hình độc lập như thế nào?
Bạn thiết kế quy trình GitOps cho cấu hình Kong với pull request, kiểm tra tự động và lịch sử triển khai ra sao?
Bạn quản lý giá trị phụ thuộc môi trường và thông tin bí mật trong cấu hình decK để tránh đưa credential lên Git như thế nào?
Bạn xác định và xử lý config drift khi cấu hình thực tế bị thay đổi thủ công ngoài pipeline decK như thế nào?
Bạn tổ chức phát hành và rollback cấu hình Kong để có thể khôi phục Route hoặc Plugin khi bản mới gây lỗi ra sao?
Bạn kiểm soát việc chạy đồng thời nhiều pipeline decK trên cùng gateway để tránh ghi đè cấu hình như thế nào?
Bạn cân nhắc sự tương thích giữa phiên bản Kong, plugin và decK trước khi nâng cấp môi trường như thế nào?
Bạn mô tả cách Kong Ingress Controller chuyển tài nguyên Kubernetes thành cấu hình gateway như thế nào?
Bạn phân biệt Ingress Controller với Kong Gateway data plane trong kiến trúc Kubernetes ra sao?
Bạn lựa chọn Kubernetes Ingress hay Gateway API để mô tả định tuyến theo yêu cầu ứng dụng như thế nào?
Bạn cấu hình Service Kubernetes và luật định tuyến để đưa API đang chạy trong cluster ra ngoài qua Kong như thế nào?
Bạn quản lý plugin trong Kubernetes bằng những tài nguyên cấu hình thích hợp và kiểm tra phạm vi áp dụng ra sao?
Bạn thiết kế cách ánh xạ chính sách xác thực của Kong vào các API được khai báo qua Kubernetes như thế nào?
Bạn xác định xung đột ownership khi vừa dùng decK vừa dùng Ingress Controller quản lý cùng tài nguyên Kong như thế nào?
Bạn đánh giá những vấn đề có thể phát sinh khi Kubernetes pod thay đổi địa chỉ, restart hoặc scale nhanh đối với việc định tuyến ra sao?
Bạn cấu hình readiness, liveness và tài nguyên cho các thành phần Kong trong cluster theo tải dự kiến như thế nào?
Bạn lựa chọn số replica, chiến lược rolling update và phân bố Kong Gateway theo zone để nâng độ sẵn sàng ra sao?
Bạn xác định cách bảo vệ Admin API và mặt phẳng quản trị Kong khi chạy trong Kubernetes như thế nào?
Bạn xây dựng bộ metric cho lưu lượng, tỷ lệ lỗi, độ trễ gateway và độ trễ upstream để theo dõi chất lượng API ra sao?
Bạn sử dụng metric, access log và distributed tracing để truy tìm nguyên nhân một API tăng p99 latency như thế nào?
Bạn phân biệt thời gian chờ ở Kong với thời gian xử lý tại upstream để xác định nút thắt như thế nào?
Bạn thiết kế dashboard theo Service, Route, Consumer và mã trạng thái để tìm API bị lỗi hoặc bị giới hạn lưu lượng ra sao?
Bạn xây dựng cảnh báo cho upstream không khỏe, lỗi xác thực, rate limit và tăng bất thường 5xx như thế nào?
Khi Kong trả 502, 503 hoặc 504, bạn thu thập những dấu hiệu nào để phân biệt lỗi kết nối, thiếu upstream và timeout?
Bạn kiểm tra tác động của plugin, TLS và logging đến CPU, bộ nhớ và thông lượng gateway dưới tải như thế nào?
Bạn thiết kế load test để đánh giá khả năng mở rộng số replica Kong khi số kết nối và request đồng thời tăng ra sao?
Bạn kiểm chứng một thay đổi Route, policy bảo mật hoặc upstream bằng canary và phương án rollback như thế nào?
Bạn lập quy trình xử lý sự cố khi một bản cấu hình mới làm nhiều API không định tuyến hoặc xác thực được như thế nào?
