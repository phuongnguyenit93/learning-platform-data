Một máy chủ Linux khởi động lại sau bảo trì nhưng ứng dụng API không tự chạy dù unit đã được tạo; nhóm vận hành cần phân biệt trạng thái enable với start trong systemd.
Một unit khai báo After=database.service nhưng ứng dụng vẫn khởi động trước khi database sẵn sàng nhận truy vấn; nhóm SRE cần phân biệt thứ tự khởi động với quan hệ kéo theo và readiness.
Dịch vụ xử lý đơn hàng cần database bắt buộc, nhưng unit chỉ dùng Wants nên vẫn khởi động khi database thất bại; nhóm vận hành cần đánh giá Requires và điều kiện phụ thuộc.
Một ứng dụng cần dừng khi mount dữ liệu bị tháo, nhưng unit chỉ khai báo After mount và vẫn tiếp tục chạy sau khi mount biến mất; đội Linux cần đánh giá BindsTo và vòng đời phụ thuộc.
Một unit thay đổi file cấu hình nhưng systemd vẫn dùng định nghĩa cũ sau khi restart; nhóm vận hành cần xác định khi nào cần daemon-reload và khi nào chỉ cần restart service.
Một dịch vụ chạy Type=simple nhưng ứng dụng fork tiến trình nền rồi thoát tiến trình cha, systemd đánh dấu service stopped và khởi động lại liên tục; nhóm phát triển cần chọn Type phù hợp.
Một ứng dụng hỗ trợ systemd notification nhưng unit dùng Type=simple, hệ thống báo service started trước khi ứng dụng hoàn tất khởi tạo; đội vận hành cần đánh giá Type=notify và readiness.
Một service bị crash liên tục và Restart=always tạo vòng lặp khởi động làm log tăng nhanh; đội vận hành cần đánh giá Restart policy, RestartSec và giới hạn start rate.
Một service cần network nhưng unit chỉ khai báo After=network.target, ứng dụng khởi động khi địa chỉ IP chưa được cấu hình; đội hạ tầng cần đánh giá network-online.target và readiness của network manager.
Một dịch vụ được kích hoạt bằng socket systemd nhưng socket unit không được enable, request đầu tiên sau reboot bị từ chối; nhóm vận hành cần xác định vòng đời socket và service activation.
Một unit sử dụng User=app nhưng thư mục log và dữ liệu thuộc sở hữu root, tiến trình khởi động được rồi thoát khi ghi file; nhóm bảo mật cần kiểm tra quyền thư mục và nguyên tắc least privilege.
Một daemon cần bind cổng thấp nhưng được chạy bằng root để đơn giản hóa, đội bảo mật muốn bỏ quyền root mà vẫn giữ khả năng lắng nghe; nhóm Linux cần đánh giá capability phù hợp và quyền thực thi.
Một service có thể ghi vào mọi thư mục hệ thống dù chỉ cần đọc cấu hình và ghi dữ liệu riêng; nhóm nền tảng cần đánh giá systemd sandboxing như ProtectSystem, ReadWritePaths và PrivateTmp.
Một dịch vụ Java cần secret lúc khởi động, nhóm triển khai đặt mật khẩu trực tiếp trong Environment của unit và người có quyền đọc cấu hình có thể xem; nhóm bảo mật cần đánh giá cơ chế systemd credentials và quản lý secret.
Một ứng dụng ghi log vào file riêng và journal đồng thời, logrotate xóa file đang mở khiến tiến trình tiếp tục ghi vào inode không còn đường dẫn; nhóm SRE cần xác định cơ chế rotation và reopen log.
Một service systemd thất bại sau deploy nhưng nhóm trực chỉ xem application log, không xem journal có thông tin lỗi sandbox và exit status; đội vận hành cần xác định nguồn log và metadata cần đối chiếu.
Một service bị OOMKilled trong cgroup nhưng dashboard chỉ theo dõi CPU của host, không thấy giới hạn memory riêng của unit; nhóm SRE cần theo dõi resource control theo service.
Một dịch vụ nền chiếm CPU và ảnh hưởng workload quan trọng, nhóm vận hành muốn giới hạn tài nguyên mà không thay đổi code; đội Linux cần đánh giá CPUQuota, MemoryMax và IOWeight.
Một unit cho phép người dùng không đặc quyền gọi systemctl restart thông qua sudoers với wildcard quá rộng, họ có thể sửa tham số hoặc chạy lệnh ngoài dự kiến; nhóm an ninh cần đánh giá quyền điều khiển service.
Một service cần giới hạn thứ tự dừng để hoàn tất giao dịch, nhưng unit không có TimeoutStopSec và KillSignal phù hợp nên systemd buộc kill tiến trình; đội SRE cần đánh giá graceful shutdown.
Một ứng dụng phụ thuộc vào mount mạng, khi mạng mất service tiếp tục chạy và ghi dữ liệu vào thư mục mount rỗng trên filesystem gốc; nhóm Linux cần đánh giá mount dependency và bảo vệ đường dẫn.
Một máy chủ Windows khởi động nhưng dịch vụ ứng dụng ở trạng thái Stopped do startup type đặt Manual; nhóm vận hành cần phân biệt Automatic, Manual và Disabled trong Service Control Manager.
Một Windows Service được đặt Automatic nhưng ứng dụng cần database khởi động trước, SCM báo dependency failure khi boot; đội hạ tầng cần kiểm tra service dependencies và delayed automatic start.
Một service Windows không khởi động sau khi mật khẩu tài khoản chạy dịch vụ thay đổi, SCM báo logon failure; nhóm quản trị cần xác định quy trình cập nhật credential và kiểm tra quyền Log on as a service.
Một tổ chức dùng Group Managed Service Account cho Windows Service, sau thay đổi domain policy dịch vụ không đăng nhập được; nhóm hạ tầng cần kiểm tra quyền máy tính, SPN và khả năng lấy mật khẩu do domain quản lý.
Một Windows Service chạy bằng LocalSystem có quyền quá rộng, ứng dụng chỉ cần truy cập một thư mục và một dịch vụ mạng; nhóm bảo mật cần đánh giá virtual service account hoặc tài khoản riêng với quyền tối thiểu.
Một dịch vụ Windows được cấu hình Recovery restart service ngay cả khi lỗi do file cấu hình sai, hệ thống lặp khởi động và ghi event log liên tục; nhóm vận hành cần đánh giá failure actions và reset failure count.
Một Windows Service khởi động thất bại nhưng nhóm hỗ trợ chỉ xem application log, không kiểm tra System event log và Service Control Manager events; đội SRE cần đối chiếu mã lỗi và thời điểm.
Một Windows Service chạy được khi khởi động thủ công từ console nhưng thất bại khi SCM start vì working directory và PATH khác; nhóm phát triển cần kiểm tra môi trường và đường dẫn của service process.
Một service Windows dùng executable path có khoảng trắng nhưng ImagePath thiếu dấu ngoặc kép, hệ thống có thể phân giải nhầm chương trình khi khởi động; nhóm bảo mật cần đánh giá quoting và quyền ghi thư mục.
Một dịch vụ Windows được cài bằng tài khoản quản trị nhưng ACL của binary cho phép Users sửa file, người dùng thường có thể thay chương trình sẽ chạy với quyền service; đội an ninh cần rà soát quyền trên executable và thư mục cha.
Một nhóm hỗ trợ cấp quyền Start/Stop cho service nhưng đồng thời cấp quyền sửa cấu hình service và binary, tạo khả năng leo thang đặc quyền; nhóm bảo mật cần phân biệt quyền điều khiển với quyền thay đổi nội dung.
Một Windows Service bị treo nhưng trạng thái SCM vẫn Running vì tiến trình không phản hồi lệnh điều khiển; nhóm vận hành cần đánh giá service control handler, health check và timeout.
Một máy Windows được vá và reboot, service khởi động chậm hơn timeout SCM nên bị đánh dấu failed dù cuối cùng tiến trình có thể phục vụ; nhóm nền tảng cần đánh giá startup timeout và readiness.
Một máy macOS chạy tác vụ nền cần hoạt động ngay cả khi chưa có người dùng đăng nhập, nhưng nhóm triển khai tạo LaunchAgent trong thư mục người dùng; đội vận hành cần phân biệt LaunchAgent và LaunchDaemon.
Một LaunchDaemon được đặt trong thư mục sai hoặc plist không có quyền sở hữu và permission theo yêu cầu, launchd từ chối nạp job; nhóm macOS cần kiểm tra vị trí, owner và mode của plist.
Một LaunchAgent được cài cho người dùng nhưng nhóm vận hành dùng sai launchctl domain, job không xuất hiện trong phiên GUI đang đăng nhập; đội hỗ trợ cần xác định bootstrap domain phù hợp.
Một job launchd có RunAtLoad nhưng không có KeepAlive, tiến trình kết thúc sau khi chạy một lần và không được khởi động lại; nhóm phát triển cần xác định semantics của các khóa lifecycle.
Một daemon macOS có KeepAlive bật vô điều kiện, ứng dụng lỗi cấu hình thoát ngay và launchd khởi động lặp liên tục; nhóm SRE cần đánh giá điều kiện KeepAlive và giới hạn retry.
Một LaunchAgent cần truy cập giao diện người dùng nhưng được cài thành LaunchDaemon ở system domain, job chạy ngoài phiên GUI và không thể mở cửa sổ; nhóm phát triển cần xác định phạm vi phiên người dùng.
Một ứng dụng macOS phụ thuộc biến môi trường có trong Terminal nhưng launchd không kế thừa shell profile, job thất bại khi khởi động tự động; đội vận hành cần khai báo môi trường rõ ràng trong plist.
Một job launchd ghi StandardOutPath và StandardErrorPath vào thư mục chưa tồn tại, tiến trình không khởi chạy như mong đợi; nhóm hỗ trợ cần kiểm tra đường dẫn log và quyền ghi.
Một daemon macOS được nạp bằng launchctl bootstrap nhưng nhóm quản trị sửa plist và chỉ gọi kickstart, cấu hình mới chưa được nạp lại; đội nền tảng cần phân biệt reload, bootout và bootstrap.
Một job launchd cần giữ tiến trình khi người dùng logout, nhưng được cấu hình trong user GUI domain nên bị dừng theo phiên; nhóm phát triển cần đánh giá vòng đời job và loại domain.
Một nhóm dùng launchctl list để kiểm tra job, thấy mã exit khác không nhưng vẫn kết luận daemon hoạt động vì label còn trong danh sách; nhóm SRE cần phân biệt job được đăng ký với tiến trình đang phục vụ.
Một service trên Linux, Windows và macOS đều được báo Running nhưng endpoint ứng dụng không phản hồi sau khi dependency database lỗi; nhóm vận hành cần xác định khác biệt giữa trạng thái process và sức khỏe dịch vụ.
Một ứng dụng có cấu hình tự khởi động trên cả ba hệ điều hành, sau nâng cấp hệ thống service được tạo trùng ở hai cơ chế khiến tiến trình chạy hai bản; đội nền tảng cần kiểm kê mọi cơ chế autostart.
Một nhóm triển khai cùng service account name trên Linux, Windows và macOS nhưng quyền mặc định khác nhau, ứng dụng hoạt động ở một nền tảng và thất bại ở nền tảng khác; nhóm bảo mật cần lập ma trận quyền theo hệ điều hành.
Một ứng dụng được nâng cấp nhưng service definition vẫn trỏ binary phiên bản cũ, dashboard chỉ theo dõi service name nên không phát hiện phiên bản đang chạy; nhóm SRE cần theo dõi executable path và version.
Một nhóm thay đổi service account để giảm quyền, nhưng quên cập nhật ACL của thư mục log và socket, dịch vụ khởi động thất bại trên một số máy; đội triển khai cần kiểm tra quyền sau migration identity.
Một dịch vụ nền tự khởi động sau reboot nhưng không có health check chủ động, lỗi kết nối dependency chỉ xuất hiện khi người dùng gửi request; nhóm SRE cần thiết kế kiểm tra readiness và dependency.
Một service có restart policy tự động nhưng lỗi do schema database không tương thích, khởi động lại không giải quyết được nguyên nhân và gây bão log; nhóm vận hành cần xác định ngưỡng dừng và escalation.
Một nhóm hỗ trợ restart service để xử lý sự cố nhưng không kiểm tra request đang xử lý, giao dịch bị gián đoạn và dữ liệu chưa flush; đội phát triển cần xác định graceful shutdown và tiêu chí an toàn.
Một máy chủ có nhiều dịch vụ phụ thuộc nhau, lịch patch yêu cầu reboot nhưng chưa xác định thứ tự dừng và khởi động lại; nhóm hạ tầng cần xây dựng dependency-aware maintenance plan.
Một doanh nghiệp muốn phát hiện service bị disable ngoài kế hoạch, hệ thống monitoring chỉ cảnh báo khi process down nên không phát hiện cấu hình autostart bị thay đổi; nhóm SRE cần giám sát desired state và runtime state.
Một đội vận hành thay đổi startup type hoặc enablement của service qua công cụ quản trị, nhưng không lưu người thực hiện và lý do; nhóm kiểm toán cần xác định audit trail cho thay đổi vòng đời dịch vụ.
Một dịch vụ quan trọng có nhiều bản sao trên các máy chủ, rollout cấu hình đồng thời làm tất cả instance restart cùng lúc; nhóm SRE cần đánh giá rolling restart, availability và giới hạn gián đoạn.
Một service được khôi phục tự động sau lỗi nhưng không có cảnh báo số lần restart, sự cố chập chờn kéo dài nhiều ngày mà không được phát hiện; nhóm vận hành cần theo dõi restart rate và thời gian uptime.
Một máy chủ Windows hoặc Linux hết dung lượng log, dịch vụ không thể ghi trạng thái và tự thoát; đội hạ tầng cần xác định cảnh báo dung lượng, log rotation và hành vi khi filesystem đầy.
Một daemon Linux bị OOM killer chấm dứt nhưng systemd tự khởi động lại, người trực chỉ thấy uptime ngắn và không tìm được nguyên nhân; nhóm SRE cần đối chiếu journal, kernel log và cgroup events.
Một service Windows chạy ổn định nhiều tháng nhưng bị dừng sau khi tài khoản dịch vụ hết hạn hoặc quyền đăng nhập bị thu hồi; nhóm quản trị cần theo dõi tình trạng credential và lịch rà soát quyền.
Một ứng dụng cần đảm bảo dịch vụ nền hoạt động sau khi cập nhật hệ điều hành, nhưng nhóm triển khai chỉ kiểm tra cài đặt binary mà không kiểm thử start, stop, restart và recovery; đội QA cần xây dựng kiểm thử vòng đời end-to-end.
