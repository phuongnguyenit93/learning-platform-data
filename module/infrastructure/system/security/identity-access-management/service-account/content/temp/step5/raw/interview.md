Bạn phân biệt service account với tài khoản người dùng tương tác về mục đích, vòng đời và cách xác thực như thế nào?
Bạn phân biệt danh tính phi con người, principal và credential trong một giao dịch service-to-service ra sao?
Bạn xác định khi nào một ứng dụng, tác vụ định kỳ, agent tự động hoặc tích hợp bên ngoài cần một service identity riêng như thế nào?
Bạn xây dựng quy ước đặt tên service account để thể hiện owner, workload, môi trường và mục đích mà không làm lộ thông tin nhạy cảm ra sao?
Bạn lập inventory service account trên nhiều nền tảng, cloud account, máy chủ, container và SaaS như thế nào?
Bạn xác định owner chịu trách nhiệm nghiệp vụ và kỹ thuật cho từng service account ra sao khi workload được nhiều nhóm cùng vận hành?
Bạn ghi nhận mục đích, phạm vi, dependency và hệ thống được phép truy cập của một service identity như thế nào?
Bạn thiết kế service account riêng cho development, staging và production để tránh credential hoặc quyền truy cập bị dùng chéo ra sao?
Bạn quyết định khi nào mỗi workload cần identity riêng và khi nào có thể dùng chung một identity theo ranh giới tin cậy nào?
Bạn ngăn service account dùng chung giữa nhiều ứng dụng khiến audit không thể quy trách nhiệm cho workload cụ thể như thế nào?
Bạn quản lý service identity cho workload ngắn hạn hoặc tự động tạo theo từng lần chạy mà không để lại tài khoản mồ côi ra sao?
Bạn thiết kế vòng đời service account từ yêu cầu, phê duyệt, cấp phát, kích hoạt, rà soát đến thu hồi như thế nào?
Bạn tự động hóa provisioning service account để bảo đảm cấu hình nhất quán và có thể kiểm toán trên nhiều môi trường ra sao?
Bạn xác định thông tin và phê duyệt tối thiểu cần có trước khi cấp một danh tính máy mới như thế nào?
Bạn đặt thời hạn cho service account hoặc credential ra sao để các danh tính tạm thời không tồn tại vô thời hạn?
Bạn xác định sự kiện nào phải kích hoạt thu hồi service account khi ứng dụng ngừng hoạt động, owner rời nhóm hoặc hợp đồng kết thúc như thế nào?
Bạn phát hiện và xử lý service account không còn owner, không còn workload hoặc không có hoạt động trong thời gian dài ra sao?
Bạn phân biệt tài khoản đã ngừng sử dụng với tài khoản chỉ hoạt động theo lịch hiếm để tránh thu hồi nhầm như thế nào?
Bạn thiết kế quy trình decommission để thu hồi quyền, credential, token và các quan hệ tin cậy khi một workload bị loại bỏ ra sao?
Bạn xác định dependency của service account trước khi thay đổi hoặc thu hồi để tránh làm gián đoạn các dịch vụ phụ thuộc như thế nào?
Bạn áp dụng least privilege cho service account bằng cách xác định resource, action và phạm vi truy cập cần thiết ra sao?
Bạn thiết kế permission riêng cho từng workload thay vì cấp quyền quản trị rộng chỉ để đơn giản hóa triển khai như thế nào?
Bạn phân biệt quyền đọc, ghi, xóa, quản trị và thực thi đối với từng tài nguyên mà service account truy cập ra sao?
Bạn kết hợp role và điều kiện theo thuộc tính hoặc ngữ cảnh để giới hạn quyền service account theo môi trường, tenant và workload như thế nào?
Bạn giới hạn quyền của service account theo namespace, project, subscription hoặc account boundary ra sao?
Bạn kiểm soát quyền truy cập dữ liệu production từ pipeline CI/CD và môi trường kiểm thử như thế nào?
Bạn thiết kế quyền cho service account cần thực hiện tác vụ quản trị đặc quyền mà vẫn giảm thiểu thời gian và phạm vi sử dụng ra sao?
Bạn tách quyền triển khai workload khỏi quyền đọc dữ liệu nghiệp vụ để một credential bị lộ không thể thực hiện cả hai nhóm hành động như thế nào?
Bạn bảo đảm service account chỉ được gọi đúng dịch vụ đích và đúng loại hành động thông qua audience, scope hoặc resource restriction ra sao?
Bạn thiết kế xác thực và phân quyền riêng biệt cho giao tiếp giữa hai workload như thế nào?
Bạn sử dụng OAuth 2.0 Client Credentials Grant trong trường hợp nào và quản lý client identity, scope cùng token lifetime ra sao?
Bạn phân biệt client secret, private key JWT và mutual TLS khi xác thực ứng dụng với authorization server như thế nào?
Bạn thiết kế token exchange hoặc delegation để một workload gọi dịch vụ tiếp theo theo đúng danh tính và quyền được ủy quyền ra sao?
Bạn lựa chọn token ngắn hạn hay credential dài hạn dựa trên khả năng cấp mới, rủi ro lộ lọt và yêu cầu sẵn sàng như thế nào?
Bạn giới hạn audience và scope của access token để token dành cho một API không thể bị dùng tại API khác ra sao?
Bạn xác minh chữ ký, issuer, audience, thời hạn và trạng thái token của service identity như thế nào?
Bạn thiết kế mutual TLS để xác thực danh tính workload ở hai đầu kết nối và ánh xạ certificate sang quyền truy cập ra sao?
Bạn lựa chọn subject hoặc SAN trong certificate để định danh workload ổn định qua các lần triển khai như thế nào?
Bạn quản lý vòng đời certificate máy gồm cấp phát, gia hạn, rotation, thu hồi và phân phối trust bundle ra sao?
Bạn sử dụng workload identity federation để cấp quyền cho workload dựa trên danh tính từ môi trường thực thi mà không lưu secret dài hạn như thế nào?
Bạn xác minh issuer, subject, audience và điều kiện trust khi liên kết danh tính từ CI/CD hoặc cloud workload với tài nguyên đích ra sao?
Bạn ngăn workload giả mạo danh tính của một pipeline hoặc môi trường khác trong quy trình federation như thế nào?
Bạn quản lý token do nền tảng điều phối container cấp để giới hạn audience, thời hạn và quyền truy cập của từng workload ra sao?
Bạn thiết kế cơ chế bootstrap danh tính ban đầu cho máy hoặc workload mới mà không cần nhúng credential gốc vào image như thế nào?
Bạn lựa chọn giữa API key, client secret, certificate và token ngắn hạn cho từng kiểu tích hợp như thế nào?
Bạn lưu trữ secret của service account trong secret manager hoặc vault với quyền truy cập và audit phù hợp ra sao?
Bạn ngăn credential bị hard-code trong source code, file cấu hình, container image hoặc repository lịch sử như thế nào?
Bạn phân phối secret tới workload khi khởi động và giới hạn khả năng đọc secret của tiến trình hoặc người vận hành ra sao?
Bạn đánh giá rủi ro khi truyền secret qua biến môi trường, command-line argument hoặc file tạm trong các môi trường thực thi khác nhau như thế nào?
Bạn bảo vệ private key và client secret khi lưu trữ, backup và khôi phục bằng KMS, HSM hoặc cơ chế quản lý khóa phù hợp ra sao?
Bạn tách quyền quản trị secret khỏi quyền sử dụng secret để người vận hành không thể tùy ý đọc credential của mọi workload như thế nào?
Bạn thiết kế rotation cho API key hoặc client secret mà không làm gián đoạn workload đang chạy ra sao?
Bạn triển khai giai đoạn overlap giữa credential cũ và mới, xác minh consumer đã chuyển đổi rồi thu hồi credential cũ như thế nào?
Bạn xoay vòng certificate hoặc key pair khi nhiều instance và vùng triển khai có lịch cập nhật khác nhau như thế nào?
Bạn xác định tần suất rotation dựa trên thời hạn credential, mức độ nhạy cảm, khả năng phát hiện xâm phạm và chi phí vận hành ra sao?
Bạn xử lý trường hợp credential bị lộ trong repository hoặc log bằng cách thu hồi, thay thế và xác định phạm vi ảnh hưởng như thế nào?
Bạn ngăn secret xuất hiện trong application log, audit event, trace, crash dump và thông báo lỗi như thế nào?
Bạn phân biệt rotation định kỳ với rotation khẩn cấp sau sự cố và xác định bằng chứng cần thu thập trước khi thu hồi ra sao?
Bạn thiết kế cơ chế thu hồi tức thời khi service account bị xâm phạm trong khi token hoặc session đã được phát hành vẫn còn hiệu lực như thế nào?
Bạn xác định cách vô hiệu hóa đồng thời identity, credential, certificate, token và trust relationship khi xảy ra sự cố như thế nào?
Bạn giám sát việc sử dụng service account bằng các thuộc tính actor, workload, resource, action, source và kết quả ra sao?
Bạn xây dựng baseline hành vi để phát hiện service account truy cập tài nguyên mới, tăng đột biến hoặc hoạt động ngoài lịch dự kiến như thế nào?
Bạn phát hiện credential của một workload bị sử dụng từ vị trí, mạng hoặc môi trường thực thi bất thường ra sao?
Bạn thiết kế cảnh báo cho service account có quyền rộng, credential sắp hết hạn, key cũ còn hoạt động hoặc owner không xác định như thế nào?
Bạn phân biệt lỗi xác thực bình thường với dấu hiệu dò credential, token replay hoặc lạm dụng danh tính máy như thế nào?
Bạn bảo đảm audit log phân biệt được service account với người dùng đã khởi tạo tác vụ và workload thực sự thực hiện hành động ra sao?
Bạn thiết kế access review định kỳ cho service account khi chủ sở hữu ứng dụng, dependency và quyền truy cập thường xuyên thay đổi như thế nào?
Bạn xác định quyền nào không còn được sử dụng và loại bỏ permission dư thừa mà không làm gián đoạn workload hợp lệ ra sao?
Bạn áp dụng separation of duties giữa người yêu cầu, người phê duyệt, người cấp quyền và người vận hành service identity như thế nào?
Bạn thiết kế break-glass access cho tác vụ tự động khẩn cấp và bảo đảm credential đặc quyền được giám sát, giới hạn thời gian ra sao?
Bạn kiểm soát việc con người mạo danh hoặc sử dụng trực tiếp service account để tránh né quy trình xác thực cá nhân như thế nào?
Bạn quản lý ủy quyền khi một workload gọi dịch vụ khác thay mặt người dùng mà vẫn giữ được danh tính người khởi tạo và phạm vi quyền như thế nào?
Bạn xử lý ranh giới tin cậy khi service account truy cập tài nguyên ở một tổ chức, cloud account hoặc tenant khác như thế nào?
Bạn kiểm soát service identity của nhà cung cấp và đối tác bên ngoài để credential không tồn tại sau khi tích hợp hoặc hợp đồng kết thúc ra sao?
Bạn thiết kế quota, rate limit và giới hạn tài nguyên cho service account để credential bị lạm dụng không gây ảnh hưởng diện rộng như thế nào?
Bạn kiểm thử authorization của service account bằng các trường hợp truy cập được phép, bị từ chối và vượt ranh giới môi trường ra sao?
Bạn kiểm tra cấu hình policy-as-code để phát hiện service account có wildcard permission, quyền quản trị hoặc trust condition quá rộng như thế nào?
Bạn đánh giá rủi ro khi service account credential được đóng gói trong image hoặc artifact có thể bị sao chép sang môi trường không tin cậy ra sao?
Bạn bảo vệ danh tính máy trong pipeline build và deploy để một job bị xâm phạm không thể lấy credential của các job khác như thế nào?
Bạn xây dựng quy trình ứng phó khi phát hiện một service account bị dùng trái phép để khoanh vùng workload, thu hồi quyền và bảo toàn bằng chứng ra sao?
Bạn xác định các chỉ số để đo chất lượng quản trị service account như tỷ lệ có owner, credential quá hạn, quyền dư thừa và thời gian thu hồi như thế nào?
