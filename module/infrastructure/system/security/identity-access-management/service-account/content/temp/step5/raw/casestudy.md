Một doanh nghiệp có hàng trăm ứng dụng và tác vụ tự động nhưng không có danh mục service account tập trung; nhóm bảo mật không xác định được tài khoản nào còn hoạt động, chủ sở hữu là ai và quyền đang có ở hệ thống nào.
Một service account được tạo cho dự án thử nghiệm từ ba năm trước vẫn có quyền quản trị trên môi trường production; nhóm dự án đã giải thể và không còn người chịu trách nhiệm cho danh tính này.
Một tổ chức dùng cùng một tài khoản dịch vụ cho nhiều ứng dụng và nhiều môi trường để giảm công sức quản lý; khi credential bị lộ, không thể xác định phạm vi consumer bị ảnh hưởng.
Một tài khoản máy có tên mô tả chung như integration-user được nhiều nhóm sử dụng; audit log chỉ ghi danh tính này nên không thể quy hành động về workload hoặc chủ sở hữu cụ thể.
Một nhóm vận hành tạo service account bằng tài khoản cá nhân của quản trị viên rồi chuyển giao cho hệ thống tự động; khi nhân viên nghỉ việc, credential và quyền sở hữu của workload bị gián đoạn.
Một service account có quyền đọc và ghi trên toàn bộ bucket dữ liệu vì nhóm triển khai không phân biệt được các object prefix mà ứng dụng thực sự cần.
Một tác vụ backup chỉ cần đọc dữ liệu từ một database nhưng đang dùng credential có quyền tạo user, thay đổi schema và xóa database trên toàn cụm.
Một workload được cấp quyền cloud Administrator dài hạn để tránh lỗi permission khi triển khai; sau này workload chỉ cần ghi log nhưng quyền rộng vẫn chưa được thu hồi.
Một service account dùng chung giữa development, staging và production; một pipeline thử nghiệm bị xâm nhập có thể dùng cùng danh tính để truy cập dữ liệu production.
Một ứng dụng gọi nhiều API nội bộ bằng cùng một client credential; các dịch vụ đích không thể phân biệt mục đích hoặc giới hạn quyền theo từng workload.
Một hệ thống tích hợp đối tác dùng OAuth client credentials nhưng access token có scope quá rộng và audience không giới hạn vào API đích dự kiến.
Một client secret của ứng dụng được tạo với thời hạn không giới hạn và lưu trong file cấu hình trên máy chủ; không có inventory nơi secret được sao chép hoặc sử dụng.
Một nhóm phát triển đưa API key của tài khoản dịch vụ vào repository để pipeline dễ truy cập; key xuất hiện trong lịch sử commit và các fork bên ngoài.
Một pipeline CI/CD lưu cloud access key trong biến môi trường dùng chung cho mọi repository; contributor có quyền chạy job có thể làm lộ credential qua log hoặc tiến trình con.
Một build runner có quyền assume production role nhưng trust policy chỉ kiểm tra tên repository; workflow từ nhánh không tin cậy có thể chạy trong cùng repository và nhận quyền.
Một hệ thống dùng workload identity federation để bỏ key dài hạn nhưng điều kiện trust chỉ kiểm tra issuer, không ràng buộc repository, namespace, service account hoặc subject claim.
Một service account trên Kubernetes được mount vào mọi pod trong namespace; pod xử lý nội dung không tin cậy cũng nhận token có quyền đọc secret và tạo workload khác.
Một workload Kubernetes dùng service account token không giới hạn thời gian trong image; token vẫn có thể được sử dụng sau khi pod bị xóa hoặc chuyển sang node khác.
Một ứng dụng chạy trong Kubernetes không cần gọi Kubernetes API nhưng vẫn tự động nhận service account token; khi container bị khai thác, token tạo đường truy cập sang control plane.
Một cluster có nhiều namespace nhưng service account cùng tên được cấp quyền khác nhau; nhóm vận hành nhầm lẫn identity do không đưa namespace và cluster vào quy trình kiểm kê.
Một workload cloud trên máy ảo sử dụng access key tĩnh trong file cấu hình dù nền tảng đã hỗ trợ managed identity; key không được rotate và có quyền rộng hơn nhu cầu.
Một managed identity được gắn vào máy ảo chạy nhiều workload; mọi tiến trình trên máy đều có thể yêu cầu token của cùng danh tính và truy cập tài nguyên ngoài phạm vi.
Một workload chạy trên cloud container platform dùng node role chung thay vì workload identity riêng; một container bị xâm nhập có thể nhận quyền của các workload khác trên node.
Một hệ thống dùng service principal cho nhiều automation job; credential và quyền được quản lý tập trung nhưng không có cách thu hồi một job mà không làm gián đoạn các job còn lại.
Một tác vụ đồng bộ dữ liệu chạy bằng tài khoản dịch vụ có quyền đăng nhập tương tác; credential bị đánh cắp có thể được dùng để mở shell thay vì chỉ gọi API đồng bộ.
Một service account Linux chạy daemon có UID 0 vì cấu hình cũ; daemon chỉ cần đọc một thư mục nhưng khi bị khai thác có thể thay đổi toàn bộ hệ thống tệp.
Một Windows service chạy dưới tài khoản domain có quyền Domain Admin; ứng dụng chỉ cần truy cập một share nhưng compromise dịch vụ có thể ảnh hưởng toàn domain.
Một tài khoản dịch vụ database không có người dùng tương tác nhưng mật khẩu không hết hạn và được chia sẻ qua nhiều máy chủ; việc thu hồi sau sự cố rất khó xác định.
Một hệ thống dùng SSH private key cho automation; cùng một key được cài vào nhiều máy đích và không có mapping giữa key, service, môi trường và người chịu trách nhiệm.
Một certificate client dùng cho mTLS được cấp thời hạn hai năm và private key nằm trong filesystem của container; image bị sao chép khiến key xuất hiện ở nhiều môi trường.
Một CA cấp certificate cho service identity nhưng không kiểm tra subject hoặc SAN theo workload; một workload có thể xin certificate mang danh tính của service khác.
Một hệ thống tự động gia hạn certificate nhưng chỉ cập nhật file trên disk; tiến trình đang chạy vẫn giữ certificate cũ và kết nối mTLS bắt đầu thất bại khi certificate hết hạn.
Một quy trình rotate client secret tạo secret mới nhưng không có giai đoạn overlap và cập nhật consumer đồng bộ; nhiều tác vụ production ngừng xác thực trong lúc chuyển đổi.
Một nhóm vận hành rotate credential trong vault nhưng không biết các job batch chạy theo lịch tuần đang dùng secret cũ; job thất bại sau khi credential cũ bị thu hồi.
Một API key bị phát hiện trong log nhưng tổ chức không biết key được nhúng trong những image, file cấu hình, pipeline và hệ thống bên thứ ba nào.
Một service account bị nghi lộ private key; nhóm ứng cứu thu hồi key tại một hệ thống nhưng quên các bản sao public key, certificate và authorized key trên những máy đích khác.
Một workload dùng access token có thời hạn ngắn nhưng refresh credential tồn tại lâu dài trong persistent volume; token bị thu hồi nhưng workload vẫn có thể xin token mới.
Một hệ thống cấp token machine-to-machine không kiểm tra audience; token được phát hành cho một API lại được chấp nhận bởi dịch vụ nội bộ khác.
Một dịch vụ tin vào token client credentials chỉ dựa trên chữ ký và thời hạn; nó không kiểm tra issuer, subject, scope hoặc trạng thái danh tính của workload gọi đến.
Một API nhận request từ service account nhưng không xác minh workload identity ở từng request; gateway đã xác thực ban đầu rồi chuyển tiếp danh tính qua header có thể bị caller giả mạo.
Một tác vụ tự động gọi API đối tác từ nhiều môi trường nhưng dùng chung client ID và secret; đối tác không thể thu hồi riêng staging khi credential bị lộ ở production.
Một service account được cấp quyền theo nhóm động; khi workload chuyển sang namespace mới, membership cũ vẫn còn và quyền từ môi trường trước không được loại bỏ.
Một quy trình cấp service account tự động tạo identity và policy nhưng không có bước gắn owner, mục đích, thời hạn và hệ thống phụ thuộc; tài khoản không được rà soát sau triển khai.
Một ứng dụng tạo service account mới cho mỗi lần chạy batch nhưng không xóa identity sau khi job hoàn tất; số lượng danh tính và credential mồ côi tăng nhanh.
Một nhóm nền tảng xóa workload nhưng quên thu hồi service principal, API key và quyền trên storage; danh tính máy không còn workload sở hữu vẫn có thể truy cập tài nguyên.
Một hệ thống quản lý secret có audit log nhưng không ghi workload identity hoặc resource đích; khi phát hiện nhiều lần đọc secret bất thường, nhóm bảo mật không xác định được consumer.
Một service account truy cập secret manager bằng credential bootstrap tĩnh; credential này có quyền đọc các secret khác và không có cơ chế xác minh workload đang chạy trên hạ tầng hợp lệ.
Một nền tảng dùng secret store để cấp credential cho workload nhưng cho phép mọi service account trong namespace đọc mọi secret; ranh giới tenant và workload không được thực thi.
Một hệ thống tự động rotate credential có retry không giới hạn; khi API đích lỗi, nhiều job đồng thời liên tục yêu cầu rotate và làm quá tải secret manager.
Một service account có quyền xóa bản sao lưu để thực hiện cleanup; khi pipeline bị chiếm quyền, attacker có thể xóa cả dữ liệu chính lẫn bản sao phục hồi.
Một workload cần ghi dữ liệu vào object storage nhưng được cấp quyền list và đọc toàn bộ bucket; dữ liệu của tenant khác có thể bị truy cập qua cùng identity.
Một dịch vụ xử lý thông điệp dùng chung credential cho producer và consumer; thành phần chỉ cần publish vẫn có quyền đọc và xóa message của các queue khác.
Một tài khoản dịch vụ có quyền tạo user và cấp role trên hệ thống đích; ứng dụng bị xâm nhập có thể tạo identity mới để duy trì truy cập sau khi credential ban đầu bị thu hồi.
Một service account được dùng từ nhiều địa chỉ mạng và nhiều loại workload cùng lúc; hệ thống giám sát không có baseline để phân biệt hành vi bình thường với credential bị chia sẻ.
Một workload thường gọi API trong giờ làm việc nhưng đột ngột truy cập hàng nghìn object và nhiều region ngoài lịch; log không có correlation giữa identity, job và resource.
Một tổ chức muốn phát hiện service account không còn sử dụng nhưng chỉ dựa vào lần đăng nhập gần nhất; các tác vụ theo quý có thể bị thu hồi nhầm.
Một incident response team thu hồi service credential sau khi phát hiện xâm nhập nhưng không xác định được access token đã phát hành còn hiệu lực đến khi nào và có cần revoke session hay không.
Một tổ chức cần chứng minh mỗi non-human identity có owner, mục đích, scope, credential lifecycle và lịch rà soát; dữ liệu hiện phân tán giữa cloud console, CI/CD và hệ thống secret.
Một nền tảng đa cloud cần thống nhất quản lý service account trên AWS, Azure, Google Cloud, Kubernetes và hệ thống on-premises nhưng mỗi nơi dùng mô hình identity, federation và audit khác nhau.
Một doanh nghiệp chuyển từ credential dài hạn sang workload identity nhưng một số tác vụ chạy ngoài nền tảng được liên kết chưa có trust path; nhóm vận hành đề xuất giữ lại key chung cho mọi môi trường.
Một tổ chức đánh giá hiệu quả quản trị service account chỉ bằng số secret đã đưa vào vault; quyền dư thừa, identity không có owner, token sống lâu và credential chưa thu hồi chưa được đo lường.
