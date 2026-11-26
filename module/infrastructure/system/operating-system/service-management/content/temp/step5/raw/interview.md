Bạn sẽ phân biệt service nền, daemon, process và scheduled task trong hệ điều hành như thế nào?
Bạn sẽ xác định những thành phần nào cần có để một ứng dụng chạy ổn định như dịch vụ nền trên máy chủ?
Bạn sẽ mô tả vòng đời chung của một service từ cài đặt, cấu hình, khởi động đến dừng và gỡ bỏ như thế nào?
Bạn sẽ phân biệt trạng thái service đang chạy với trạng thái service đã được cấu hình tự khởi động ra sao?
Bạn sẽ xác định tiêu chí nào để lựa chọn chạy một tác vụ dưới dạng service thay vì cron job hoặc tác vụ thủ công?
Bạn sẽ thiết kế quy trình quản lý service nhất quán khi cùng ứng dụng cần chạy trên Linux, Windows và macOS như thế nào?
Bạn sẽ so sánh vai trò của systemd, Windows Service Control Manager và launchd trong quản lý dịch vụ nền ra sao?
Bạn sẽ phân biệt cấu hình khai báo trạng thái mong muốn với các thao tác start hoặc stop trực tiếp như thế nào?
Bạn sẽ xác định cách bảo đảm service tiếp tục hoạt động sau reboot nhưng không tự khởi động trong một số môi trường như thế nào?
Bạn sẽ đánh giá tác động của service startup đến thời gian khởi động máy và khả năng sẵn sàng của ứng dụng ra sao?
Bạn sẽ xây dựng danh mục service theo mức độ quan trọng, chủ sở hữu và phụ thuộc vận hành như thế nào?
Bạn sẽ xác định service nào cần giám sát liên tục và service nào chỉ cần chạy theo yêu cầu dựa trên tiêu chí nào?
Bạn sẽ thiết kế health check để phân biệt process còn sống với service thực sự xử lý được công việc như thế nào?
Bạn sẽ phân biệt trạng thái process running, service active, readiness và availability trong hệ thống như thế nào?
Bạn sẽ lựa chọn timeout khởi động và timeout dừng service dựa trên hành vi ứng dụng ra sao?
Bạn sẽ thiết kế shutdown graceful để service hoàn tất request đang xử lý trước khi thoát như thế nào?
Bạn sẽ lựa chọn KillMode, KillSignal và TimeoutStopSec để dừng process chính cùng các process con có kiểm soát như thế nào?
Bạn sẽ xác định cách xử lý khi service không phản hồi lệnh stop nhưng vẫn còn process hoạt động ra sao?
Bạn sẽ cân nhắc thứ tự dừng các service phụ thuộc nhau khi máy chủ tắt hoặc bảo trì như thế nào?
Bạn sẽ thiết kế quy trình triển khai phiên bản mới để tránh chạy đồng thời hai instance không tương thích như thế nào?
Bạn sẽ xác minh service sau reboot bằng kiểm tra trạng thái, log và một phép thử nghiệp vụ nào?
Bạn sẽ giải thích systemd quản lý unit và dependency thay vì chỉ khởi chạy process như thế nào?
Bạn sẽ phân biệt service unit, target, socket, timer, mount và path unit theo mục đích sử dụng ra sao?
Bạn sẽ mô tả cấu trúc một file systemd service unit với các section Unit, Service và Install như thế nào?
Bạn sẽ xác định vai trò của Description, Documentation, Wants, Requires và After trong section Unit ra sao?
Bạn sẽ phân biệt Wants và Requires khi một service phụ thuộc vào một service khác nhưng có mức độ bắt buộc khác nhau như thế nào?
Bạn sẽ giải thích After và Before quy định thứ tự khởi động chứ không tự kéo unit phụ thuộc vào như thế nào?
Bạn sẽ lựa chọn BindsTo, PartOf và Conflicts khi cần ràng buộc vòng đời giữa các unit ra sao?
Bạn sẽ thiết kế dependency graph cho ứng dụng cần network, filesystem và database trước khi khởi động như thế nào?
Bạn sẽ xác định vì sao một service có After=network.target vẫn chưa chắc có kết nối mạng sẵn sàng ra sao?
Bạn sẽ phân biệt network.target với network-online.target và xác định khi nào service cần chờ mạng thực sự sẵn sàng như thế nào?
Bạn sẽ lựa chọn target phù hợp để đưa một service vào quy trình boot của máy Linux ra sao?
Bạn sẽ giải thích WantedBy trong section Install ảnh hưởng đến systemctl enable như thế nào?
Bạn sẽ phân biệt systemctl enable, start, enable --now và preset theo trạng thái cấu hình và runtime ra sao?
Bạn sẽ phân biệt system-level unit với user-level unit được quản lý bằng systemctl --user như thế nào?
Bạn sẽ giải thích loginctl enable-linger ảnh hưởng đến việc user service chạy khi người dùng chưa đăng nhập ra sao?
Bạn sẽ mô tả quy trình daemon-reload sau khi thay đổi unit file và lý do cần thực hiện như thế nào?
Bạn sẽ phân biệt unit file gốc với drop-in override và cách systemd hợp nhất cấu hình ra sao?
Bạn sẽ sử dụng systemctl cat và systemctl show để kiểm tra cấu hình hiệu lực của một service như thế nào?
Bạn sẽ xác định unit file nào đang được systemd nạp khi có nhiều bản cùng tên trong các thư mục khác nhau ra sao?
Bạn sẽ thiết kế override để thay đổi một thuộc tính service mà không sao chép toàn bộ unit gốc như thế nào?
Bạn sẽ phân biệt Type=simple, exec, forking, oneshot và notify theo cách systemd xác định service đã khởi động ra sao?
Bạn sẽ lựa chọn Type=notify cho ứng dụng cần báo readiness sau khi hoàn tất khởi tạo như thế nào?
Bạn sẽ xác định khi nào Type=forking cần PIDFile và những rủi ro khi PID file không chính xác ra sao?
Bạn sẽ phân biệt RemainAfterExit với service có process chạy liên tục khi dùng Type=oneshot như thế nào?
Bạn sẽ tổ chức ExecStartPre, ExecStart, ExecStartPost và ExecStop để khởi tạo cũng như dọn dẹp service ra sao?
Bạn sẽ xác định hành vi khi một lệnh ExecStartPre thất bại và cách systemd phản ánh trạng thái unit như thế nào?
Bạn sẽ lựa chọn Restart=on-failure, always hoặc no theo loại service và đặc tính lỗi như thế nào?
Bạn sẽ kết hợp RestartSec, StartLimitIntervalSec và StartLimitBurst để tránh restart loop ra sao?
Bạn sẽ phân biệt restart do chính sách systemd với process tự daemonize hoặc tự tạo child process như thế nào?
Bạn sẽ cấu hình watchdog để phát hiện service không còn phản hồi dù process vẫn tồn tại như thế nào?
Bạn sẽ giải thích WatchdogSec và sd_notify giúp ứng dụng báo tình trạng hoạt động cho systemd ra sao?
Bạn sẽ thiết kế systemd timer thay cho cron khi cần quản lý lịch chạy và dependency với unit khác như thế nào?
Bạn sẽ phân biệt timer OnCalendar với OnBootSec và OnUnitActiveSec trong các lịch chạy khác nhau ra sao?
Bạn sẽ xác định Persistent=true ảnh hưởng đến timer đã bỏ lỡ lịch khi máy tắt như thế nào?
Bạn sẽ thiết kế socket activation để systemd chỉ khởi động service khi có kết nối đến như thế nào?
Bạn sẽ phân biệt service socket-activated với service luôn chạy nền về tài nguyên và độ trễ khởi động ra sao?
Bạn sẽ kiểm tra vì sao socket unit đang lắng nghe nhưng service nhận kết nối lại khởi động thất bại như thế nào?
Bạn sẽ lựa chọn template unit và instance name để chạy nhiều bản service cùng cấu hình chung ra sao?
Bạn sẽ quản lý biến môi trường trong unit bằng Environment và EnvironmentFile theo cách nào để giảm lộ bí mật?
Bạn sẽ xác định WorkingDirectory, RuntimeDirectory và StateDirectory phù hợp với vòng đời dữ liệu của service như thế nào?
Bạn sẽ lựa chọn User và Group để service chạy dưới tài khoản chuyên dụng thay vì root ra sao?
Bạn sẽ áp dụng DynamicUser khi service không cần tài khoản hệ điều hành cố định như thế nào?
Bạn sẽ giới hạn quyền của service bằng CapabilityBoundingSet, NoNewPrivileges và RestrictAddressFamilies ra sao?
Bạn sẽ giải thích ProtectSystem, ProtectHome, PrivateTmp và ReadWritePaths giúp cô lập filesystem như thế nào?
Bạn sẽ đánh giá tác động của MemoryMax, CPUQuota và TasksMax đến service khi chạy dưới cgroup ra sao?
Bạn sẽ xác định cách systemd quản lý process con và tài nguyên của service trong một cgroup như thế nào?
Bạn sẽ sử dụng systemctl status, list-dependencies và list-units để khoanh vùng service không khởi động ra sao?
Bạn sẽ đọc journalctl theo unit, boot ID và khoảng thời gian để tìm lỗi của service như thế nào?
Bạn sẽ phân biệt lỗi cấu hình unit, lỗi quyền truy cập, lỗi executable và lỗi dependency qua journal ra sao?
Bạn sẽ kiểm tra exit code và signal khiến service chuyển sang failed bằng những thông tin nào?
Bạn sẽ sử dụng systemd-analyze critical-chain để tìm service làm chậm quá trình boot như thế nào?
Bạn sẽ đánh giá tác động của service restart liên tục đến tài nguyên máy và các dịch vụ phụ thuộc ra sao?
Bạn sẽ xử lý trạng thái start-limit-hit sau nhiều lần khởi động thất bại theo trình tự nào?
Bạn sẽ xác định khi nào dùng systemctl reset-failed và bằng chứng nào cần giữ trước khi xóa trạng thái lỗi?
Bạn sẽ phân biệt journal volatile trong RAM với journal persistent trên đĩa và ảnh hưởng đến điều tra sau reboot như thế nào?
Bạn sẽ cấu hình giới hạn dung lượng và thời gian lưu journal để không làm đầy filesystem ra sao?
Bạn sẽ giải thích Windows Service Control Manager quản lý đăng ký, khởi động, dừng và trạng thái service như thế nào?
Bạn sẽ phân biệt Windows service với ứng dụng console chạy nền hoặc scheduled task ra sao?
Bạn sẽ mô tả các trạng thái SERVICE_STOPPED, START_PENDING, RUNNING, STOP_PENDING và PAUSED như thế nào?
Bạn sẽ giải thích startup type Automatic, Automatic Delayed Start, Manual và Disabled ảnh hưởng đến boot ra sao?
Bạn sẽ lựa chọn Automatic Delayed Start cho service không cần sẵn sàng ngay sau khi hệ thống khởi động như thế nào?
Bạn sẽ phân biệt cấu hình startup type với thao tác Start-Service hoặc Stop-Service về trạng thái runtime ra sao?
Bạn sẽ sử dụng Services.msc, Get-Service và sc.exe để kiểm tra cấu hình cùng trạng thái một service như thế nào?
Bạn sẽ dùng Get-CimInstance hoặc WMI để xác định executable path, process ID và tài khoản chạy service ra sao?
Bạn sẽ kiểm tra ImagePath có dấu cách hoặc tham số sai khiến Windows khởi chạy nhầm executable như thế nào?
Bạn sẽ xác định service phụ thuộc vào service hoặc driver nào bằng cấu hình SCM ra sao?
Bạn sẽ phân biệt service dependencies với load-order groups trong quá trình Windows khởi động như thế nào?
Bạn sẽ xác định cách Windows xử lý khi một service phụ thuộc chưa chạy hoặc khởi động thất bại ra sao?
Bạn sẽ giải thích service trigger start giúp khởi động service theo sự kiện thay vì luôn chạy như thế nào?
Bạn sẽ thiết kế cấu hình recovery action để service tự khởi động lại sau lần lỗi đầu, lần lỗi tiếp theo và lỗi kéo dài ra sao?
Bạn sẽ phân biệt First failure, Second failure và Subsequent failures trong tab Recovery của Windows service như thế nào?
Bạn sẽ xác định tác động của Reset fail count after đến việc áp dụng recovery action ra sao?
Bạn sẽ xử lý trường hợp service đã chạy lại nhưng lỗi gốc vẫn tồn tại khiến service tiếp tục crash như thế nào?
Bạn sẽ đọc Windows Event Viewer để tìm lỗi từ Service Control Manager và service application ra sao?
Bạn sẽ phân biệt event do SCM phát sinh với log riêng của ứng dụng chạy trong service như thế nào?
Bạn sẽ dùng Get-WinEvent để lọc sự kiện theo provider, event ID và khoảng thời gian ra sao?
Bạn sẽ xác định nguyên nhân Error 1068 khi dependency service không khởi động được như thế nào?
Bạn sẽ phân biệt lỗi service timeout với lỗi executable thoát ngay sau khi được khởi chạy ra sao?
Bạn sẽ giải thích service control handler báo START_PENDING, checkpoint và wait hint giúp SCM theo dõi khởi động kéo dài như thế nào?
Bạn sẽ kiểm tra service bị treo ở trạng thái START_PENDING hoặc STOP_PENDING bằng những dữ liệu nào?
Bạn sẽ xác định process ID của service và kiểm tra nhiều service cùng chia sẻ một process svchost như thế nào?
Bạn sẽ phân biệt service chạy trong process riêng với service dùng chung process host về phạm vi ảnh hưởng khi crash ra sao?
Bạn sẽ cấu hình service account LocalSystem, LocalService hoặc NetworkService theo quyền cần thiết như thế nào?
Bạn sẽ đánh giá rủi ro chạy service bằng LocalSystem khi ứng dụng chỉ cần quyền đọc một thư mục dữ liệu ra sao?
Bạn sẽ lựa chọn domain service account, group Managed Service Account hoặc virtual account cho service cần truy cập tài nguyên mạng như thế nào?
Bạn sẽ xác định quyền Log on as a service cần cấp cho tài khoản service trong chính sách Windows ra sao?
Bạn sẽ thiết kế ACL cho thư mục ứng dụng, log và dữ liệu để service account chỉ có quyền cần thiết như thế nào?
Bạn sẽ giải thích service SID giúp cấp quyền theo danh tính riêng của service thay vì cấp rộng cho tài khoản chạy chung ra sao?
Bạn sẽ bảo vệ mật khẩu service account và lên kế hoạch rotation mà không gây gián đoạn service như thế nào?
Bạn sẽ phân biệt quyền quản trị máy với quyền quản lý một service cụ thể khi phân quyền vận hành như thế nào?
Bạn sẽ kiểm tra vì sao service chạy được dưới tài khoản tương tác nhưng thất bại khi chạy dưới service account ra sao?
Bạn sẽ xác định ảnh hưởng của session isolation đến service không có giao diện người dùng trên Windows như thế nào?
Bạn sẽ xử lý service cần truy cập network share khi chạy dưới tài khoản LocalSystem hoặc LocalService ra sao?
Bạn sẽ mô tả launchd quản lý daemon và agent trên macOS theo domain và vòng đời như thế nào?
Bạn sẽ phân biệt LaunchDaemons với LaunchAgents về ngữ cảnh chạy, quyền và thời điểm khởi động ra sao?
Bạn sẽ xác định khi nào dùng LaunchDaemon ở cấp hệ thống và khi nào dùng LaunchAgent trong phiên người dùng như thế nào?
Bạn sẽ mô tả cấu trúc property list với Label, ProgramArguments và RunAtLoad trong cấu hình launchd ra sao?
Bạn sẽ phân biệt Program với ProgramArguments và kiểm tra lỗi đường dẫn executable trong plist như thế nào?
Bạn sẽ giải thích KeepAlive điều khiển việc launchd duy trì process theo những điều kiện nào?
Bạn sẽ lựa chọn RunAtLoad và StartInterval cho service cần chạy ngay khi nạp hoặc chạy định kỳ như thế nào?
Bạn sẽ xác định cách đặt UserName, GroupName và WorkingDirectory trong LaunchDaemon theo nguyên tắc quyền tối thiểu ra sao?
Bạn sẽ cấu hình StandardOutPath và StandardErrorPath để thu thập log cho service macOS như thế nào?
Bạn sẽ phân biệt launchctl bootstrap, bootout, kickstart và print trong quản lý service ra sao?
Bạn sẽ xác định domain system, gui và user khi kiểm tra một LaunchAgent hoặc LaunchDaemon như thế nào?
Bạn sẽ chẩn đoán vì sao một plist hợp lệ về cú pháp nhưng launchd không nạp service như thế nào?
Bạn sẽ sử dụng plutil để kiểm tra định dạng property list và launchctl để xác minh trạng thái service ra sao?
Bạn sẽ phân tích log từ unified logging khi service macOS khởi động rồi thoát ngay như thế nào?
Bạn sẽ xác định quyền file và thư mục cần có cho LaunchDaemon để tránh launchd từ chối nạp cấu hình ra sao?
Bạn sẽ xử lý trường hợp LaunchAgent chạy đúng trong phiên người dùng nhưng không hoạt động trước khi đăng nhập như thế nào?
Bạn sẽ thiết kế cơ chế restart có kiểm soát cho một daemon macOS khi process thoát bất thường ra sao?
Bạn sẽ xác định tác động của việc thay đổi plist trong lúc service đang chạy và quy trình nạp lại cấu hình như thế nào?
Bạn sẽ so sánh cơ chế dependency của launchd với systemd và Windows SCM về cách mô hình hóa thứ tự khởi động ra sao?
Bạn sẽ thiết kế cấu hình service đa nền tảng sao cho giữ cùng mục đích vận hành dù mỗi hệ điều hành có cơ chế khác nhau như thế nào?
Bạn sẽ phân biệt cấu hình service được quản lý bởi package installer với cấu hình được triển khai bằng công cụ quản lý cấu hình ra sao?
Bạn sẽ xây dựng quy trình cài đặt, nâng cấp và gỡ service có thể chạy lặp lại mà không tạo trạng thái thừa như thế nào?
Bạn sẽ xác định cách lưu cấu hình và dữ liệu runtime tách biệt với thư mục binary của service ra sao?
Bạn sẽ thiết kế quản lý secret cho service trên Linux, Windows và macOS mà không nhúng mật khẩu vào command line như thế nào?
Bạn sẽ lựa chọn tài khoản service riêng cho từng ứng dụng thay vì dùng chung một tài khoản dựa trên rủi ro nào?
Bạn sẽ áp dụng nguyên tắc least privilege cho quyền đọc file, ghi log, mở cổng mạng và truy cập tài nguyên như thế nào?
Bạn sẽ phân biệt quyền filesystem, quyền mạng và quyền IPC cần thiết của service trong quá trình hardening ra sao?
Bạn sẽ giới hạn service chỉ lắng nghe trên interface hoặc cổng cần thiết và xác minh điều đó như thế nào?
Bạn sẽ xác định rủi ro khi service chạy với quyền cao nhưng nạp plugin hoặc file cấu hình do người dùng khác ghi ra sao?
Bạn sẽ kiểm soát quyền sửa executable, unit file, plist hoặc registry entry của service như thế nào?
Bạn sẽ đánh giá tác động của việc bật auto-restart khi service gặp lỗi do cấu hình hoặc dữ liệu hỏng ra sao?
Bạn sẽ thiết kế backoff và giới hạn restart để tránh service crash loop làm quá tải máy chủ như thế nào?
Bạn sẽ phân biệt process supervisor với cơ chế retry ở tầng ứng dụng khi downstream không sẵn sàng ra sao?
Bạn sẽ xác định service nên chờ dependency, retry có giới hạn hay khởi động rồi degrade functionality theo tiêu chí nào?
Bạn sẽ thiết kế shutdown timeout để service có đủ thời gian flush dữ liệu nhưng không chặn máy tắt vô hạn ra sao?
Bạn sẽ xử lý signal hoặc control request dừng service khi ứng dụng có worker thread và queue đang hoạt động như thế nào?
Bạn sẽ xác định cách ngăn nhiều instance của cùng service chạy đồng thời khi ứng dụng chỉ hỗ trợ một instance như thế nào?
Bạn sẽ quản lý PID file hoặc lock file để tránh nhận nhầm process và xử lý file cũ sau crash ra sao?
Bạn sẽ phân biệt service process còn sống với cổng mạng đang lắng nghe nhưng không phản hồi request như thế nào?
Bạn sẽ kết hợp process health, endpoint health và kiểm tra nghiệp vụ để đánh giá service readiness ra sao?
Bạn sẽ thiết kế monitoring cho service bằng trạng thái, restart count, uptime, resource usage và tỷ lệ request lỗi như thế nào?
Bạn sẽ xác định metric nào giúp phát hiện service restart liên tục trước khi người dùng báo lỗi ra sao?
Bạn sẽ chuẩn hóa log service theo timestamp, severity, service identity và correlation ID như thế nào?
Bạn sẽ phân biệt stdout, stderr, journal, Windows Event Log và macOS unified logging trong chiến lược tập trung log ra sao?
Bạn sẽ xác định log nào cần giữ khi service khởi động thất bại trước khi logger của ứng dụng được khởi tạo như thế nào?
Bạn sẽ thiết kế retention và rotation cho service log để tránh đầy đĩa mà vẫn giữ đủ bằng chứng điều tra ra sao?
Bạn sẽ kiểm tra log bị mất khi service chạy dưới tài khoản không có quyền ghi thư mục log như thế nào?
Bạn sẽ bảo đảm log không chứa password, token hoặc dữ liệu người dùng nhạy cảm trong quá trình chẩn đoán ra sao?
Bạn sẽ phân biệt cảnh báo process down với cảnh báo service không hoàn thành công việc theo SLO như thế nào?
Bạn sẽ thiết kế cảnh báo khi service đang active nhưng dependency database hoặc queue không sẵn sàng ra sao?
Bạn sẽ đánh giá thời gian phát hiện và phục hồi sự cố service bằng những chỉ số vận hành nào?
Bạn sẽ xác định ngưỡng CPU, memory, handle hoặc file descriptor bất thường có thể làm service mất ổn định như thế nào?
Bạn sẽ điều tra service bị kill bởi OOM hoặc resource limit bằng log và metric hệ điều hành ra sao?
Bạn sẽ phân biệt lỗi do cạn tài nguyên của process với lỗi do giới hạn cgroup hoặc job object như thế nào?
Bạn sẽ kiểm tra port conflict khi service thất bại vì một process khác đã chiếm cổng cần thiết ra sao?
Bạn sẽ xác định nguyên nhân service không truy cập được file hoặc thư mục dù tài khoản quản trị có thể truy cập như thế nào?
Bạn sẽ chẩn đoán service phụ thuộc DNS hoặc network khi máy vừa boot nhưng dịch vụ chưa sẵn sàng ra sao?
Bạn sẽ kiểm tra service không khởi động sau reboot vì mount hoặc volume chưa được gắn như thế nào?
Bạn sẽ phân tích sự cố service chạy được thủ công nhưng thất bại khi khởi động tự động do environment khác nhau ra sao?
Bạn sẽ xác định biến môi trường, working directory và PATH khác nhau giữa interactive shell và service context như thế nào?
Bạn sẽ kiểm tra service bị lỗi sau khi certificate hết hạn hoặc credential rotation bằng log nào?
Bạn sẽ xây dựng runbook cho lỗi service start timeout gồm kiểm tra dependency, quyền, binary, port và log ra sao?
Bạn sẽ thiết kế quy trình rollback service version khi bản phát hành mới làm crash loop hoặc tăng lỗi như thế nào?
Bạn sẽ xác minh service đã phục hồi sau restart bằng kiểm tra health endpoint và hành vi nghiệp vụ ra sao?
Nếu systemd báo active nhưng API không phản hồi, bạn sẽ kiểm tra socket, process, dependency và endpoint health theo thứ tự nào?
Nếu một systemd service restart liên tục với exit code khác không, bạn sẽ kết hợp journalctl, systemctl show và giới hạn restart để tìm nguyên nhân như thế nào?
Nếu service Windows báo Error 1068, bạn sẽ lần theo dependency tree và Event Viewer để xác định service gốc bị lỗi ra sao?
Nếu Windows service chạy dưới LocalSystem nhưng không truy cập được network share, bạn sẽ kiểm tra identity và quyền mạng như thế nào?
Nếu một service bị treo ở STOP_PENDING, bạn sẽ xác định process, thread hoặc thao tác shutdown đang chờ bằng cách nào?
Nếu LaunchDaemon không chạy sau reboot nhưng chạy được bằng launchctl kickstart, bạn sẽ kiểm tra domain, plist và điều kiện bootstrap ra sao?
Nếu LaunchAgent chỉ hoạt động sau khi người dùng đăng nhập, bạn sẽ quyết định có cần chuyển thành LaunchDaemon hay không dựa trên yêu cầu nào?
Nếu service khởi động trước database và thoát ngay, bạn sẽ thiết kế lại dependency, retry và readiness để tránh lỗi lặp ra sao?
Nếu auto-restart khiến một service ghi dữ liệu lỗi lặp lại sau mỗi lần khởi động, bạn sẽ thiết kế giới hạn và cơ chế cách ly như thế nào?
Nếu bản cập nhật thay đổi tài khoản chạy service và khiến quyền thư mục không còn phù hợp, bạn sẽ khôi phục least privilege ra sao?
Nếu service chạy tốt trên terminal nhưng thất bại khi chạy dưới supervisor, bạn sẽ so sánh environment, working directory, permissions và session như thế nào?
Nếu service báo healthy nhưng người dùng vẫn gặp lỗi do downstream chậm, bạn sẽ mở rộng health check và monitoring ra sao?
Nếu máy chủ tắt đột ngột trong lúc service đang ghi dữ liệu, bạn sẽ xác minh tính nhất quán và quy trình khởi động lại như thế nào?
Bạn sẽ xây dựng quy trình vận hành service đa nền tảng từ cài đặt, tự khởi động, dependency, tài khoản tối thiểu đến giám sát và phục hồi như thế nào?
