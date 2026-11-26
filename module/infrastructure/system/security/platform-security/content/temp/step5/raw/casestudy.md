Một doanh nghiệp triển khai baseline hardening cho hàng nghìn máy Linux nhưng mỗi nhóm vận hành tự sửa cấu hình SSH, sudo và firewall theo nhu cầu riêng; sau vài tháng, cùng một vai trò máy chủ có nhiều trạng thái bảo mật khác nhau.
Một máy chủ Windows chạy dịch vụ nghiệp vụ vẫn bật SMBv1 và các giao thức cũ để tương thích với ứng dụng legacy; nhóm bảo mật chưa xác định được hệ thống phụ thuộc nào có thể nâng cấp hoặc cô lập.
Một image hệ điều hành mới được triển khai với nhiều package và service mặc định không cần thiết; đội vận hành lo ngại việc tắt chúng có thể làm hỏng agent giám sát và quy trình backup.
Một máy chủ Linux cho phép SSH đăng nhập trực tiếp bằng tài khoản root từ mạng nội bộ; nhóm quản trị cho rằng firewall đã giới hạn nguồn truy cập nên không cần thay đổi cấu hình xác thực.
Một số máy chủ dùng chung tài khoản quản trị local và cùng một mật khẩu được lưu trong tài liệu nội bộ; khi phát hiện đăng nhập bất thường, nhóm ứng cứu không thể xác định máy nào và cá nhân nào đã sử dụng credential.
Một dịch vụ trên máy chủ chạy với quyền root dù chỉ cần đọc một thư mục dữ liệu và mở một cổng mạng; khi tiến trình bị khai thác, attacker có thể thay đổi file hệ thống và cài persistence.
Một ứng dụng được triển khai bằng service account có quyền đăng nhập tương tác và quyền sudo toàn phần; nhóm nền tảng chưa tách quyền vận hành của tiến trình khỏi quyền của quản trị viên.
Một máy chủ Linux có nhiều binary đặt SUID/SGID từ các gói cũ; nhóm vận hành không có inventory để xác định file nào cần thiết và file nào có thể tạo đường leo thang đặc quyền.
Một hệ thống Windows có nhiều thành viên trong local Administrators do công cụ cài đặt tự động thêm nhóm hỗ trợ; quyền tồn tại lâu dài dù nhiệm vụ chỉ yêu cầu nâng quyền theo từng lần.
Một máy chủ production đã tắt SELinux hoặc AppArmor sau khi ứng dụng gặp lỗi quyền truy cập; profile không được điều chỉnh lại nên các tiến trình tiếp tục chạy thiếu lớp kiểm soát truy cập bắt buộc.
Một host Linux cho phép load các kernel module không cần thiết và đặt một số sysctl nhạy cảm ở mức lỏng; nhóm vận hành chưa có baseline để kiểm soát thay đổi và phát hiện cấu hình làm tăng bề mặt tấn công.
Một workload chạy trên máy ảo có Secure Boot tắt để hỗ trợ driver cũ; sau khi có cảnh báo bootkit, nhóm hạ tầng chưa có kế hoạch kiểm thử driver và bật lại chuỗi khởi động tin cậy.
Một fleet máy chủ chưa bật mã hóa ổ đĩa vì lo ngại hiệu năng; một máy bị thất lạc khi vận chuyển có thể chứa dữ liệu ứng dụng và file cấu hình nhạy cảm.
Một máy chủ đã bật disk encryption nhưng khóa mở volume được lưu cùng máy và tự động giải mã khi boot; nhóm bảo mật cần đánh giá khả năng bảo vệ khi attacker chiếm quyền hệ điều hành đang chạy.
Một hệ thống lưu backup, swap và crash dump trên volume riêng không mã hóa; dữ liệu nhạy cảm có thể xuất hiện ngoài vùng lưu trữ chính đã được bảo vệ.
Một máy chủ file chia sẻ cho nhiều phòng ban dùng quyền truy cập rộng để tránh lỗi permission; người dùng có thể đọc dữ liệu ngoài nhiệm vụ và một tài khoản bị chiếm có thể xóa nhiều thư mục.
Một nhóm vận hành dùng NFS để chia sẻ dữ liệu giữa các máy chủ; export hiện cho phép truy cập từ cả subnet người dùng và có tùy chọn ánh xạ root chưa được rà soát.
Một cụm máy chủ dùng chung network segment cho quản trị, database và ứng dụng; sự cố tại một máy web có thể tạo đường kết nối trực tiếp tới các dịch vụ quản trị nội bộ.
Một firewall có rule allow any được thêm tạm thời trong đợt xử lý sự cố nhưng không có ticket hết hạn; nhiều tháng sau rule vẫn mở cổng quản trị từ các mạng không cần thiết.
Một hệ thống cho phép quản trị từ xa qua RDP và SSH từ Internet với giới hạn IP tĩnh; nhóm bảo mật muốn chuyển sang bastion và xác thực mạnh nhưng cần duy trì hỗ trợ nhà cung cấp.
Một máy chủ có nhiều outbound connection tới Internet dù chức năng chỉ cần gọi vài API đối tác; chưa có egress policy và một tiến trình bị xâm nhập có thể truyền dữ liệu ra ngoài.
Một tổ chức triển khai DNS nội bộ và proxy tập trung nhưng một số workload vẫn dùng DNS công cộng và proxy tự cấu hình; chính sách lọc domain và ghi nhận truy cập bị bỏ qua.
Một endpoint quản trị chỉ giới hạn theo subnet nhưng không kiểm tra danh tính thiết bị; laptop cá nhân nhiễm mã độc kết nối VPN có thể tiếp cận mặt phẳng quản trị.
Một nhóm mạng bật port mirroring để điều tra sự cố nhưng không giới hạn quyền đọc packet capture; dữ liệu xác thực và thông tin khách hàng có thể bị thu thập ngoài mục đích.
Một máy chủ dùng TLS cũ và bộ cipher yếu để tương thích client đời cũ; đội vận hành cần xác định client nào còn phụ thuộc trước khi nâng chuẩn giao thức.
Một hệ thống nội bộ tin cậy mọi request từ mạng private và bỏ qua xác thực giữa các service; khi một workload bị chiếm quyền, attacker có thể gọi các API nội bộ bằng vị trí mạng.
Một tổ chức triển khai host firewall nhưng rule trên từng máy được quản lý thủ công; thay đổi cấu hình không được kiểm soát và có máy production mở cổng ngoài baseline.
Một image container được build từ base image cũ có nhiều package dễ tổn thương; pipeline chỉ quét mã nguồn nên các CVE trong operating system layer không được phát hiện.
Một container chạy bằng root và có quyền privileged để truy cập thiết bị host; ứng dụng chỉ cần ghi log nhưng container bị khai thác có thể tác động trực tiếp kernel.
Một container mount thư mục hệ thống host ở chế độ read-write để hỗ trợ công cụ vận hành; khi tiến trình trong container bị xâm nhập, file cấu hình host có thể bị sửa.
Một workload container chạy với Linux capabilities mặc định đầy đủ và seccomp unconfined dù chỉ cần mở socket, đọc file; nhóm nền tảng chưa xác định tập capability và system call tối thiểu.
Một Docker daemon cho phép truy cập API không xác thực từ mạng quản trị; người có thể gọi API này có khả năng tạo container với quyền truy cập host.
Một Kubernetes cluster chưa triển khai Pod Security Admission hoặc admission policy tương đương đồng nhất; một số namespace vẫn cho phép privileged pod và hostPath tùy ý.
Một pod có thể chạy với hostNetwork, hostPID và hostPath dù workload không cần các tính năng này; nhóm bảo mật muốn chuẩn hóa security context theo loại ứng dụng.
Một Kubernetes service account mặc định được mount vào mọi pod; các workload không cần gọi API vẫn nhận token và có thể dùng quyền của namespace khi bị khai thác.
Một cluster dùng NetworkPolicy nhưng namespace mới không có default-deny; pod mới có thể kết nối tới database và service quản trị trước khi policy riêng được áp dụng.
Một node Kubernetes có quyền cloud IAM rộng để tải image và ghi log; pod bị xâm nhập có thể lấy metadata credential hoặc tận dụng quyền của node nếu ranh giới chưa được bảo vệ.
Một registry nội bộ cho phép push image bằng tài khoản dùng chung; không có kiểm tra chữ ký hoặc provenance nên image không rõ nguồn gốc có thể được triển khai production.
Một pipeline CI/CD có quyền quản trị cluster để triển khai mọi ứng dụng; khi runner bị chiếm quyền, attacker có thể thay đổi workload, secret và chính sách bảo mật.
Một cloud account có nhiều security group với rule 0.0.0.0/0 cho cổng SSH và database do thử nghiệm tạm thời; cấu hình drift không được phát hiện sau khi môi trường chuyển production.
Một workload cloud dùng instance profile hoặc managed identity có quyền truy cập toàn bộ storage account; ứng dụng chỉ cần ghi vào một bucket nhưng credential có thể đọc dữ liệu khác.
Một tổ chức lưu access key cloud dài hạn trong file cấu hình trên nhiều máy ảo; chưa có inventory vị trí sử dụng và không thể thu hồi key mà không gây gián đoạn ngoài dự kiến.
Một cloud storage bucket chứa dữ liệu khách hàng bị cấu hình public read sau khi một template IaC thay đổi; cảnh báo posture chỉ chạy hằng tuần nên dữ liệu có thể đã lộ trong thời gian dài.
Một snapshot database được chia sẻ giữa các cloud account để phục vụ kiểm thử; dữ liệu production chưa được masking và quyền decrypt của snapshot rộng hơn dự kiến.
Một workload cloud có thể truy cập metadata service để lấy credential; SSRF trong ứng dụng tạo đường truy cập tới identity của máy ảo và các tài nguyên khác.
Một nền tảng multi-cloud dùng chính sách IAM khác nhau trên từng provider; nhóm bảo mật không có cách so sánh effective permission và phát hiện quyền quản trị tương đương giữa các môi trường.
Một tổ chức dùng Terraform để triển khai hạ tầng nhưng state file chứa secret và được lưu trong backend có quyền đọc rộng; người truy cập state có thể lấy credential production.
Một pipeline IaC phát hiện cấu hình sai sau khi đã triển khai; nhóm muốn thêm chính sách dưới dạng mã nhưng chưa xác định cách xử lý ngoại lệ và tài nguyên legacy.
Một bản vá bảo mật nghiêm trọng được phát hành cho kernel nhưng một số workload phụ thuộc driver và module bên thứ ba; đội vận hành phải cân bằng tốc độ vá với rủi ro downtime.
Một hệ thống quản lý bản vá chỉ theo dõi máy chủ đã đăng ký agent; các appliance, máy ảo tạm thời và node mới tạo không được đưa vào inventory lỗ hổng.
Một tổ chức có nhiều endpoint protection agent nhưng chính sách tamper protection không bật; người có quyền local admin hoặc malware có thể tắt agent trước khi thực hiện hành vi độc hại.
Một máy chủ production không có EDR vì lo ngại ảnh hưởng hiệu năng; nhóm bảo mật cần đánh giá telemetry tối thiểu và cách triển khai agent theo từng nhóm workload.
Một baseline cấu hình được áp dụng bằng script nhưng không có cơ chế phát hiện drift; quản trị viên có thể thay đổi audit policy, firewall và quyền file mà không bị cảnh báo.
Một hệ thống gửi log về SIEM nhưng log host không có đồng bộ thời gian và danh tính máy thống nhất; sự kiện đăng nhập, thay đổi quyền và kết nối mạng khó ghép thành chuỗi điều tra.
Một quản trị viên dùng công cụ remote management từ laptop cá nhân; phiên quản trị không được ghi nhận tập trung và thiết bị không có mã hóa ổ đĩa hoặc EDR.
Một tài khoản đặc quyền có quyền truy cập cả hypervisor, backup console và cloud control plane; khi credential bị lộ, attacker có thể phá hủy workload và bản sao lưu cùng lúc.
Một quy trình break-glass cho phép truy cập hạ tầng khi IdP ngừng hoạt động nhưng không có phê duyệt kép, cảnh báo tức thời hoặc hậu kiểm thao tác.
Một tổ chức chia subnet theo môi trường nhưng dùng chung tài khoản quản trị, secret và hệ thống logging giữa development và production; compromise ở môi trường thử nghiệm có thể lan sang production.
Một nhóm vận hành cần chuyển workload giữa hai cloud region; firewall, identity policy, encryption key và logging chưa được kiểm chứng tương đương ở vùng dự phòng.
Một kế hoạch khôi phục thảm họa chỉ kiểm tra khả năng boot máy ảo; chưa kiểm thử quyền truy cập, network segmentation, EDR, backup integrity và audit sau khi restore.
Một hệ thống quan trọng có backup bất biến nhưng tài khoản quản trị backup dùng chung với tài khoản domain admin; attacker chiếm domain có thể tìm cách thay đổi chính sách backup.
Một doanh nghiệp muốn chứng minh hiệu quả platform hardening nhưng chỉ đếm số máy đã cài agent; mức tuân thủ baseline, exposed services, quyền đặc biệt, lỗ hổng tồn đọng và config drift chưa được đo.
