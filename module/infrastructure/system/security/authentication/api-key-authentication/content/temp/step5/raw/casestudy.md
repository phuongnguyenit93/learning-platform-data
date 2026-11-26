Một API key được cấp cho ứng dụng đối tác nhưng nhóm dùng nó như bằng chứng người dùng cuối đã đăng nhập; đối tác có thể gọi API thay mặt nhiều người mà hệ thống không xác định được danh tính và quyền riêng của từng người.
Một mobile app nhúng API key dùng chung trong binary để gọi backend; người dùng có thể trích xuất khóa từ gói cài đặt và dùng lại ngoài ứng dụng, khiến khóa không còn là bí mật của server.
Frontend JavaScript gọi API bằng key đặt trong biến môi trường lúc build; giá trị được bundle vào file tĩnh tải xuống trình duyệt và bất kỳ người dùng nào cũng có thể xem.
Nhóm tạo API key bằng chuỗi ngắn hoặc tuần tự thay vì giá trị ngẫu nhiên mật mã đủ dài; kẻ tấn công có thể dò đoán khóa hợp lệ vì entropy không đủ cao.
Một dịch vụ tạo khóa bằng pseudo-random generator không phù hợp cho bí mật; khi seed có thể dự đoán, các khóa phát hành trong cùng khoảng thời gian có nguy cơ suy đoán được.
API key chỉ được hiển thị một lần lúc tạo nhưng backend lưu plaintext để có thể gửi lại khi người dùng quên; database dump vì thế chứa trực tiếp credential đang hoạt động.
Nhóm lưu API key có entropy thấp bằng hash nhanh không có secret; sau khi database bị lộ, attacker có thể thử dò offline các giá trị ứng viên với chi phí thấp.
API key có entropy cao được lưu bằng SHA-256 hoặc HMAC digest kèm key ID/prefix để tra cứu; nhóm cần bảo đảm quy trình xác minh so sánh an toàn và secret HMAC được quản lý riêng.
Một tổ chức dùng cùng API key cho staging và production để giảm công sức quản lý; khóa bị lộ trong môi trường thử nghiệm có thể truy cập dữ liệu production.
Khóa API của nhiều đối tác được dùng chung một credential; khi một đối tác rời hệ thống, nhóm không thể thu hồi riêng mà không làm gián đoạn các đối tác còn lại.
API key không có owner hoặc metadata về ứng dụng sử dụng; khi phát hiện khóa lạ, đội bảo mật không xác định được người chịu trách nhiệm và phạm vi ảnh hưởng.
Quy trình cấp phát API key không xác minh danh tính hoặc quyền của người yêu cầu; người dùng có quyền thấp có thể tự tạo key với phạm vi truy cập rộng.
API key được cấp với quyền mặc định admin để tránh lỗi thiếu quyền khi tích hợp; một credential dành cho đọc dữ liệu lại có thể thực hiện thao tác thay đổi hoặc xóa.
Gateway chỉ kiểm tra API key hợp lệ mà không ánh xạ key sang client principal và scope; mọi khách hàng hợp lệ đều có thể gọi cùng toàn bộ endpoint.
Ứng dụng kiểm tra scope ở controller nhưng quên kiểm tra trong một endpoint export dữ liệu; API key chỉ có quyền đọc thông thường vẫn tải được dữ liệu nhạy cảm.
API key được dùng để nhận diện ứng dụng nhưng backend suy ra user_id từ một header do client tự gửi; client có thể thay user ID và truy cập dữ liệu người khác nếu không có bước ủy quyền độc lập.
Một API key có scope read:orders được dùng ở endpoint quản trị chấp nhận mọi scope bắt đầu bằng chuỗi read; kiểm tra prefix làm quyền đọc thông thường bị hiểu nhầm thành quyền đọc quản trị.
Nhóm thay đổi tên scope nhưng gateway cache policy cũ; một số node tiếp tục chấp nhận quyền đã bị thu hẹp cho tới khi cache hết hạn.
API key chỉ được giới hạn theo quota tổng ngày; một client bị lộ khóa có thể gửi burst hàng nghìn request trong vài giây và làm cạn tài nguyên trước khi chạm quota ngày.
Rate limit áp dụng theo IP thay vì theo key; nhiều client hợp lệ dùng chung NAT bị giới hạn cùng nhau, trong khi attacker phân tán request qua nhiều IP để né hạn mức.
Quota được lưu trong memory của từng gateway replica; client phân phối request qua nhiều node và vượt quota toàn cục vì mỗi node đếm riêng.
API key có quota theo request count nhưng endpoint tạo báo cáo nặng và endpoint health nhẹ được tính như nhau; một client có thể tiêu tốn tài nguyên lớn trong quota nhỏ.
Gateway cache response chỉ theo URL mà không đưa client identity hoặc scope vào cache key; dữ liệu của một client có thể được trả cho client khác có API key hợp lệ nhưng quyền khác.
API key được truyền trong query string để dễ tích hợp với công cụ cũ; URL xuất hiện trong access log, browser history, proxy log và hệ thống analytics.
Client gửi API key trong header qua HTTP không mã hóa trong mạng nội bộ; người có khả năng quan sát traffic có thể lấy credential và phát lại request.
API key được đặt trong header Authorization nhưng reverse proxy ghi toàn bộ request headers vào access log; khóa bị lộ dù ứng dụng không log nó.
Một middleware che header X-API-Key trong application log nhưng gateway ghi lại header Authorization ở tầng trước; credential vẫn xuất hiện trong log tập trung.
Trang tài liệu API cho phép thử request và lưu key trong localStorage của trình duyệt dùng chung; script độc hại cùng origin hoặc người dùng sau có thể lấy lại khóa.
API key được lưu trong file cấu hình nằm trong repository; nhóm xóa key ở commit mới nhưng credential vẫn còn trong lịch sử Git và các fork.
Pipeline CI in toàn bộ environment khi job thất bại; biến API key xuất hiện trong log build và người có quyền đọc pipeline có thể sử dụng.
Secret scanning phát hiện API key trong pull request nhưng quy trình chỉ xóa dòng code; khóa cũ vẫn hoạt động và chưa được rotate hoặc revoke.
API key bị lộ nhưng đội chỉ xóa khỏi log và không vô hiệu hóa credential; attacker tiếp tục gọi API bằng khóa đã sao chép.
Quy trình xoay vòng chỉ tạo key mới rồi cập nhật một số service; các worker còn dùng key cũ bị lỗi khi key cũ bị thu hồi ngay lập tức.
Rotation cho phép key cũ và mới cùng hoạt động trong thời gian chuyển tiếp nhưng không đặt thời hạn kết thúc; khóa cũ bị lộ vẫn có thể được dùng vô thời hạn.
Ứng dụng hỗ trợ hai key active cùng lúc nhưng gateway chỉ cache trạng thái của key đầu tiên; sau rotation, một số replica chấp nhận key cũ và từ chối key mới.
API key hết hạn theo thời gian nhưng gateway kiểm tra expiry từ cache dài hơn thời gian hiệu lực; khóa hết hạn vẫn được chấp nhận trong cửa sổ cache.
Khóa bị revoke trong database nhưng trạng thái revoke không được truyền tới gateway replicas; request tiếp tục được chấp nhận ở node có cache cũ.
Emergency revoke vô hiệu hóa key nhưng không kết thúc các request đã xác thực và đang chạy; một tác vụ export dài vẫn tiếp tục trả dữ liệu sau thời điểm thu hồi.
API key được sao chép giữa nhiều service để giảm số lần cấp phát; khi cần thu hồi một service, không thể xác định nơi nào còn dùng credential đó.
Gateway có plugin API key trên route /v1 nhưng route /internal/export được cấu hình ở upstream riêng và bỏ qua plugin; endpoint nhạy cảm vẫn truy cập không cần key.
Một endpoint mới được thêm vào gateway nhưng quên gắn policy xác thực; các endpoint cũ được bảo vệ đúng còn route mới bị truy cập ẩn danh.
Ứng dụng xác minh API key ở gateway nhưng backend vẫn có thể truy cập trực tiếp từ mạng nội bộ; attacker bỏ qua gateway và gọi thẳng service không có middleware xác thực.
Gateway nhận API key trong header X-API-Key nhưng upstream app đọc Authorization; adapter giữa hai tầng không chuyển đổi header đúng và một số request bị xem là anonymous.
Reverse proxy chuẩn hóa hoặc xóa header trùng lặp khác nhau với application server; attacker gửi hai API key header và gateway với backend chọn giá trị khác nhau.
API key hợp lệ được kiểm tra trước khi đọc body nhưng authorization scope chỉ được kiểm tra sau khi backend đã bắt đầu stream dữ liệu; một số dữ liệu đã được xử lý trước khi từ chối.
Gateway chỉ kiểm tra key có tồn tại mà không kiểm tra trạng thái disabled, expiry hoặc scope; khóa đã thu hồi vẫn qua được bước xác thực cơ bản.
API key được dùng như cơ chế duy nhất để bảo vệ API có thao tác thay đổi tài khoản; khóa nhận diện client nhưng không chứng minh người dùng cụ thể đã đồng ý thao tác.
Một dịch vụ bên thứ ba yêu cầu API key nhưng nghiệp vụ cần quyền theo từng người dùng; hệ thống cần kết hợp client authentication với OAuth/OIDC user delegation thay vì gán quyền user cho key.
API key bị gửi trong request tới API qua TLS nhưng certificate validation bị tắt ở client; attacker trung gian có thể giả mạo server và thu thập khóa.
Client dùng API key lâu dài mà không có ràng buộc IP, mTLS hoặc chữ ký request; khi credential bị sao chép, attacker có thể dùng từ môi trường khác cho tới khi phát hiện.
API key được dùng để xác thực webhook callback nhưng không có timestamp hoặc nonce; một request hợp lệ bị ghi lại có thể được phát lại nhiều lần.
Hệ thống dùng API key để ký request bằng HMAC nhưng không ràng buộc method, path, body hash và timestamp; chữ ký hợp lệ có thể bị tái sử dụng cho request khác.
API key được gắn với IP allowlist nhưng client chạy sau NAT có IP thay đổi; nhóm mở rộng allowlist quá rộng để khắc phục lỗi và giảm hiệu quả kiểm soát.
API key có quyền truy cập nhiều API nhưng không có quota riêng cho từng scope; một chức năng tốn tài nguyên có thể chiếm toàn bộ hạn mức của client.
Dashboard chỉ đếm request thành công theo API key; không theo dõi invalid-key, revoked-key, scope-denied và quota-exceeded nên hành vi dò khóa khó bị phát hiện.
Audit log lưu key ID, owner, scope, thời điểm cấp phát, rotation và revoke nhưng vô tình ghi cả secret; đội điều tra có metadata cần thiết nhưng đồng thời tạo thêm nơi rò rỉ.
API key không có prefix nhận diện loại môi trường hoặc client; secret scanning và đội ứng cứu khó phân loại credential bị lộ để xác định nơi cần revoke.
Quy trình revoke không có danh sách dependency hoặc last-used timestamp; nhóm tắt key đang được một batch job cũ sử dụng và gây gián đoạn xử lý định kỳ.
Khóa API không được giới hạn theo endpoint hoặc resource; client chỉ cần một key hợp lệ là có thể liệt kê mọi tài nguyên thuộc tenant khác do backend thiếu tenant authorization.
Backend lấy tenant ID từ metadata gắn với key nhưng cache ánh xạ key-to-tenant bị stale sau khi chuyển quyền sở hữu; request mới được gắn tenant cũ và trả dữ liệu sai phạm vi.
API key được đặt trong URL của callback để đối tác dễ tích hợp; hệ thống referrer hoặc công cụ giám sát lưu URL đầy đủ và làm lộ khóa sang dịch vụ thứ ba.
Client library tự động retry khi nhận 401 bằng cách gửi lại cùng API key; sau khi key bị revoke, retry storm tạo thêm tải và che khuất lỗi cấu hình thực sự.
Key lookup trả lỗi khác nhau giữa unknown key, disabled key và sai scope; phản hồi giúp người ngoài dò danh sách key ID hoặc trạng thái credential.
API key được phát hành không giới hạn số lượng cho cùng một client; khi một tài khoản bị chiếm quyền, attacker tạo nhiều key và làm quy trình thu hồi từng khóa trở nên khó kiểm soát.
Request tạo API key bị timeout sau khi backend đã lưu credential nhưng client không nhận được secret; người dùng bấm tạo lại nhiều lần và sinh nhiều key active không được ghi nhận trong hệ thống quản lý phía client.
