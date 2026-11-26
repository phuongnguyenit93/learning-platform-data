Bạn mô tả quy trình chẩn đoán sự cố hệ điều hành dựa trên triệu chứng, giả thuyết và bằng chứng như thế nào?
Bạn phân biệt triệu chứng quan sát được với nguyên nhân gốc của một sự cố ra sao?
Bạn xác định phạm vi ảnh hưởng trước khi thực hiện thao tác khắc phục bằng cách nào?
Bạn lựa chọn thứ tự kiểm tra để nhanh chóng loại trừ các nguyên nhân có xác suất cao mà không làm mất bằng chứng ra sao?
Bạn xác định dữ liệu nền cần thu thập trước khi thay đổi cấu hình hoặc khởi động lại hệ thống như thế nào?
Bạn phân biệt sự cố đơn lẻ của một máy với sự cố diện rộng từ những dấu hiệu nào?
Bạn xây dựng timeline sự cố từ alert, log, thay đổi triển khai và hành động vận hành như thế nào?
Bạn đánh giá độ tin cậy của một giả thuyết bằng phép đo hoặc thử nghiệm có thể lặp lại ra sao?
Bạn phân biệt tương quan về thời gian với quan hệ nhân quả khi phân tích nhiều tín hiệu cùng thay đổi như thế nào?
Bạn lựa chọn thời điểm thu thập snapshot, log và trạng thái tiến trình để tránh bỏ lỡ hiện tượng ngắn hạn ra sao?
Bạn xác định khi nào cần ưu tiên khôi phục dịch vụ và khi nào cần giữ nguyên hiện trạng để thu thập bằng chứng như thế nào?
Bạn đánh giá rủi ro của việc chạy lệnh chẩn đoán có thể làm thay đổi trạng thái hệ thống ra sao?
Bạn phân biệt kiểm tra chỉ đọc với thao tác can thiệp có thể gây gián đoạn dịch vụ như thế nào?
Bạn ghi nhận giả thuyết, bằng chứng ủng hộ và bằng chứng bác bỏ theo cấu trúc nào?
Bạn xác định tiêu chí kết thúc điều tra khi đã tìm ra nguyên nhân và xác minh được biện pháp khắc phục như thế nào?
Bạn xây dựng runbook có thể áp dụng nhất quán cho sự cố lặp lại ra sao?
Bạn lựa chọn mức độ nghiêm trọng của incident dựa trên ảnh hưởng người dùng, dữ liệu và phạm vi hệ thống như thế nào?
Bạn phân biệt sự cố hiệu năng, sự cố khả dụng và sự cố toàn vẹn dữ liệu khi phân loại ban đầu ra sao?
Bạn xác định những câu hỏi cần đặt ra khi người dùng báo máy tính chậm nhưng không cung cấp thêm thông tin như thế nào?
Bạn xử lý một sự cố không tái hiện được bằng cách thu thập telemetry và bằng chứng tại thời điểm xảy ra ra sao?
Bạn xác định cách so sánh trạng thái máy lỗi với máy khỏe có cấu hình và tải tương tự như thế nào?
Bạn phân biệt thay đổi gần nhất với thay đổi thực sự gây ra sự cố bằng cách kiểm chứng giả thuyết ra sao?
Bạn tổ chức phối hợp giữa đội hệ điều hành, mạng, ứng dụng và lưu trữ khi sự cố nằm ở ranh giới nhiều lớp như thế nào?
Bạn xác định dữ liệu nào cần bảo toàn trước khi restart hoặc rebuild một máy đang lỗi ra sao?
Bạn đánh giá mức độ đầy đủ của bằng chứng trước khi kết luận nguyên nhân gốc như thế nào?
Bạn xác định cách truyền đạt kết quả điều tra để người tiếp nhận hiểu triệu chứng, tác động và nguyên nhân ra sao?
Bạn xây dựng quy trình hậu kiểm để bảo đảm lỗi không tái diễn sau khi khắc phục như thế nào?
Bạn phân biệt workaround giúp khôi phục tạm thời với corrective action xử lý nguyên nhân gốc ra sao?
Bạn xác định những chỉ số cần theo dõi sau khắc phục để phát hiện sự cố quay trở lại như thế nào?
Bạn đánh giá một sự cố đã thực sự được giải quyết hay chỉ tạm thời biến mất bằng những phép thử nào?
Bạn lựa chọn lệnh và công cụ Linux phù hợp khi bắt đầu điều tra một máy chủ không phản hồi như thế nào?
Bạn sử dụng uptime và load average để đánh giá tình trạng tải hệ thống ra sao?
Bạn phân biệt load average cao do CPU-bound với load cao do tiến trình chờ I/O như thế nào?
Bạn dùng top hoặc htop để tìm tiến trình tiêu thụ CPU và bộ nhớ bất thường ra sao?
Bạn sử dụng ps để kiểm tra trạng thái, thời gian chạy và quan hệ cha con của tiến trình như thế nào?
Bạn lựa chọn pidstat để phân tích CPU, memory và I/O theo từng tiến trình như thế nào?
Bạn dùng vmstat để xác định áp lực CPU, swap và I/O trong một khoảng thời gian ra sao?
Bạn kết hợp iostat và sar để đánh giá thiết bị lưu trữ và xu hướng tải theo thời gian như thế nào?
Bạn sử dụng free và /proc/meminfo để phân biệt bộ nhớ có thể thu hồi với bộ nhớ thực sự thiếu hụt ra sao?
Bạn kiểm tra tiến trình bị OOM killer kết thúc qua kernel log và exit status như thế nào?
Bạn dùng journalctl để lọc log theo boot, unit và khoảng thời gian sự cố ra sao?
Bạn lựa chọn dmesg để kiểm tra lỗi kernel, driver, thiết bị và filesystem trong tình huống nào?
Bạn phân biệt log của systemd service với log kernel khi truy tìm nguồn lỗi như thế nào?
Bạn sử dụng systemctl status và journalctl để điều tra một service Linux không khởi động ra sao?
Bạn xác định service thất bại do dependency, permission, cấu hình hay binary bằng những bước kiểm tra nào?
Bạn dùng ss hoặc công cụ tương đương để xác định tiến trình đang listen trên cổng cần thiết như thế nào?
Bạn kiểm tra kết nối tới một endpoint bằng curl, nc hoặc công cụ phù hợp để tách lỗi DNS, TCP và HTTP ra sao?
Bạn sử dụng ip, route và resolvectl để xác minh cấu hình mạng Linux như thế nào?
Bạn kiểm tra DNS resolution, search domain và cache khi hostname không phân giải đúng ra sao?
Bạn phân tích packet loss hoặc retransmission bằng ping, traceroute và tcpdump như thế nào?
Bạn xác định interface mạng nào bị lỗi hoặc bão hòa qua ip -s link và số liệu tương đương ra sao?
Bạn sử dụng lsof hoặc fuser để tìm tiến trình đang giữ file hoặc socket khiến thao tác bị chặn như thế nào?
Bạn điều tra tình trạng hết file descriptor bằng cách nào?
Bạn kiểm tra giới hạn ulimit và giới hạn cgroup khi tiến trình không mở thêm file hoặc socket được ra sao?
Bạn dùng strace để xác định system call bị lỗi, bị chặn hoặc trả về errno bất thường như thế nào?
Bạn lựa chọn perf hoặc eBPF khi cần tìm điểm nóng CPU hoặc latency kernel sâu hơn ra sao?
Bạn phân biệt tiến trình đang chạy, sleeping, uninterruptible sleep và zombie trong Linux như thế nào?
Bạn xác định nguyên nhân tiến trình ở trạng thái D kéo dài và các thiết bị I/O liên quan ra sao?
Bạn điều tra một tiến trình zombie không được thu hồi bằng cách xem quan hệ parent-child như thế nào?
Bạn kiểm tra memory mapping và RSS của tiến trình qua /proc/PID/smaps khi nghi ngờ memory leak ra sao?
Bạn xác định filesystem hoặc mount point nào đầy bằng df và du mà không nhầm file đã bị xóa nhưng còn mở ra sao?
Bạn sử dụng find hoặc công cụ tương đương để tìm file lớn mới phát sinh trong khoảng thời gian sự cố như thế nào?
Bạn kiểm tra inode exhaustion khi dung lượng đĩa vẫn còn nhưng ứng dụng không tạo được file ra sao?
Bạn xác định mount bị read-only hoặc filesystem chuyển sang chế độ bảo vệ sau lỗi I/O bằng cách nào?
Bạn kiểm tra lỗi filesystem và lựa chọn thời điểm chạy công cụ sửa chữa phù hợp ra sao?
Bạn phân biệt disk full, inode full, quota exceeded và permission denied qua thông báo lỗi như thế nào?
Bạn xác định một service bị chậm do DNS lookup, TCP connect hay xử lý ứng dụng bằng phép đo nào?
Bạn sử dụng tcpdump để xác nhận handshake, retransmission và reset trong một kết nối lỗi ra sao?
Bạn đánh giá tác động của firewall local hoặc SELinux/AppArmor tới khả năng mở cổng dịch vụ như thế nào?
Bạn xác định khi nào cần kiểm tra conntrack table hoặc giới hạn socket trong sự cố kết nối chập chờn ra sao?
Bạn điều tra máy Linux không thể boot bằng cách sử dụng rescue mode, boot log và initramfs như thế nào?
Bạn phân biệt lỗi kernel panic, lỗi bootloader và lỗi mount root filesystem qua bằng chứng nào?
Bạn kiểm tra cấu hình GRUB hoặc tham số kernel khi sự cố xuất hiện sau một lần nâng cấp như thế nào?
Bạn xác định module kernel hoặc driver vừa thay đổi có liên quan tới lỗi thiết bị bằng cách nào?
Bạn kiểm tra thời gian hệ thống, NTP và lệch đồng hồ khi log từ nhiều máy không khớp timeline ra sao?
Bạn dùng timedatectl hoặc công cụ tương đương để xác minh timezone và trạng thái đồng bộ thời gian như thế nào?
Bạn kiểm tra dung lượng journal và chính sách log rotation khi log chiếm hết filesystem ra sao?
Bạn phân biệt lỗi ứng dụng với lỗi kernel từ core dump, stack trace và kernel messages như thế nào?
Bạn lựa chọn cách thu thập core dump mà vẫn bảo vệ thông tin nhạy cảm trong bộ nhớ tiến trình ra sao?
Bạn kiểm tra một bản cập nhật package làm thay đổi dependency hoặc service behavior như thế nào?
Bạn xác định cấu hình nào đã thay đổi giữa lần chạy tốt và lần chạy lỗi bằng lịch sử package và configuration management ra sao?
Bạn dùng Windows Event Viewer để xác định thời điểm và nguồn phát sinh lỗi hệ thống như thế nào?
Bạn phân biệt Windows System log, Application log và Security log trong quá trình điều tra ra sao?
Bạn lọc event theo Event ID, provider và thời gian để tìm lỗi liên quan đến một dịch vụ như thế nào?
Bạn sử dụng Reliability Monitor để liên hệ crash ứng dụng với driver hoặc Windows update ra sao?
Bạn lựa chọn PowerShell Get-WinEvent để truy vấn log diện rộng và lưu bằng chứng như thế nào?
Bạn xác định một Windows service không khởi động do dependency hoặc tài khoản chạy dịch vụ bằng cách nào?
Bạn sử dụng Get-Service và sc query để kiểm tra trạng thái service như thế nào?
Bạn kiểm tra service startup type, recovery action và dependency khi service liên tục dừng ra sao?
Bạn sử dụng Task Manager hoặc Resource Monitor để xác định tiến trình gây CPU, memory hoặc disk usage cao như thế nào?
Bạn lựa chọn Process Explorer để kiểm tra handle, DLL và quan hệ tiến trình khi Task Manager chưa đủ thông tin ra sao?
Bạn dùng Performance Monitor để thu thập counter trong thời gian dài và xác định xu hướng bất thường như thế nào?
Bạn lựa chọn các counter Processor, Memory, PhysicalDisk và Network Interface để chẩn đoán nút thắt nào?
Bạn phân biệt Available MBytes, Committed Bytes và Working Set khi điều tra bộ nhớ Windows ra sao?
Bạn xác định tiến trình nào gây hard faults hoặc paging nhiều qua Resource Monitor và Performance Monitor như thế nào?
Bạn phân biệt hard fault với lỗi bộ nhớ phần cứng trong ngữ cảnh Windows như thế nào?
Bạn kiểm tra pagefile, commit limit và dấu hiệu hệ thống thiếu bộ nhớ như thế nào?
Bạn điều tra ứng dụng bị kết thúc do resource exhaustion hoặc access violation bằng event và dump ra sao?
Bạn sử dụng Windows Error Reporting hoặc crash dump để tìm module gây crash như thế nào?
Bạn xác định khi nào cần dùng ProcDump để thu dump theo điều kiện thay vì chụp thủ công ra sao?
Bạn kiểm tra file handle bị giữ khiến không thể xóa hoặc thay thế một file đang được sử dụng như thế nào?
Bạn sử dụng Handle hoặc Process Explorer để xác định tiến trình đang khóa file ra sao?
Bạn kiểm tra dung lượng volume, shadow copies và quota khi Windows báo hết dung lượng như thế nào?
Bạn dùng chkdsk hoặc công cụ kiểm tra filesystem phù hợp và đánh giá rủi ro trước khi sửa chữa ra sao?
Bạn phân biệt lỗi volume, lỗi storage driver và lỗi thiết bị vật lý qua Event Viewer và SMART data như thế nào?
Bạn sử dụng Get-Disk, Get-Volume và Get-PhysicalDisk để kiểm tra trạng thái lưu trữ như thế nào?
Bạn xác định một tiến trình gây disk queue cao bằng Resource Monitor hoặc Performance Monitor ra sao?
Bạn kiểm tra SMB share hoặc mapped drive chậm bằng cách tách DNS, network và server-side latency như thế nào?
Bạn sử dụng ipconfig, route print và Get-NetIPConfiguration để kiểm tra cấu hình mạng Windows ra sao?
Bạn xác định DNS cache hoặc DNS suffix khiến một hostname được phân giải sai bằng lệnh nào?
Bạn dùng Test-NetConnection để phân biệt lỗi DNS với lỗi TCP port reachability như thế nào?
Bạn kiểm tra firewall rule và Windows Filtering Platform khi kết nối bị chặn như thế nào?
Bạn sử dụng netstat hoặc Get-NetTCPConnection để xác định socket và trạng thái kết nối bất thường ra sao?
Bạn điều tra ephemeral port exhaustion và TIME_WAIT tăng cao trong Windows như thế nào?
Bạn xác định adapter hoặc driver mạng gây packet loss bằng Performance Monitor và event logs ra sao?
Bạn sử dụng pktmon, netsh trace hoặc công cụ tương đương để thu thập bằng chứng mạng như thế nào?
Bạn phân tích lỗi sau Windows update bằng cách so sánh build, driver và lịch sử cài đặt ra sao?
Bạn xác định khi nào cần dùng Safe Mode hoặc clean boot để cô lập xung đột phần mềm như thế nào?
Bạn sử dụng DISM và System File Checker để xác minh hoặc sửa lỗi thành phần hệ điều hành ra sao?
Bạn đánh giá rủi ro rollback driver hoặc update khi chưa xác định được nguyên nhân gốc như thế nào?
Bạn kiểm tra chính sách Group Policy hoặc quyền người dùng khi một thao tác quản trị thất bại ra sao?
Bạn phân biệt lỗi service account, quyền NTFS và quyền share trong sự cố truy cập tài nguyên mạng như thế nào?
Bạn lựa chọn dump loại minidump hay memory dump đầy đủ dựa trên mục tiêu phân tích crash ra sao?
Bạn bảo vệ dữ liệu nhạy cảm trong crash dump và event logs khi chuyển cho đội hỗ trợ như thế nào?
Bạn sử dụng Activity Monitor để xác định tiến trình gây CPU, memory, energy hoặc disk pressure trên macOS như thế nào?
Bạn phân biệt Memory Pressure với phần trăm RAM đang sử dụng trong Activity Monitor ra sao?
Bạn kiểm tra swap used, compressed memory và memory pressure khi máy Mac chạy chậm như thế nào?
Bạn sử dụng Console để lọc log theo process, subsystem và thời gian trong macOS ra sao?
Bạn lựa chọn log show để truy vấn unified logging theo predicate như thế nào?
Bạn phân biệt unified log với crash report khi điều tra ứng dụng macOS bị thoát đột ngột ra sao?
Bạn xác định vị trí và nội dung cần xem trong crash report để tìm thread hoặc binary gây lỗi như thế nào?
Bạn sử dụng spindump hoặc sample để thu thập dấu vết tiến trình bị treo hoặc chiếm CPU như thế nào?
Bạn xác định khi nào cần dùng sysdiagnose để thu thập gói bằng chứng hệ thống đầy đủ ra sao?
Bạn kiểm tra launchd service hoặc LaunchAgent không khởi động bằng launchctl và log như thế nào?
Bạn phân biệt LaunchDaemon với LaunchAgent trong việc xử lý dịch vụ hệ thống và phiên người dùng ra sao?
Bạn xác định quyền file, quarantine attribute hoặc Gatekeeper có ngăn ứng dụng khởi chạy như thế nào?
Bạn kiểm tra disk space, APFS volume và snapshot khi macOS báo dung lượng khả dụng bất thường ra sao?
Bạn sử dụng diskutil và tmutil để kiểm tra volume, snapshot và trạng thái backup như thế nào?
Bạn phân biệt dung lượng APFS container với dung lượng từng volume khi phân tích disk full ra sao?
Bạn xác định tiến trình đang giữ file hoặc mount point trên macOS bằng lsof như thế nào?
Bạn kiểm tra DNS, route và interface trên macOS bằng scutil, networksetup và netstat ra sao?
Bạn sử dụng route get hoặc traceroute để xác định đường đi của một kết nối mạng như thế nào?
Bạn kiểm tra packet capture bằng tcpdump khi ứng dụng macOS không kết nối được dịch vụ từ xa ra sao?
Bạn xác định tác động của VPN, proxy hoặc network extension tới luồng kết nối trên macOS như thế nào?
Bạn phân biệt lỗi do quyền privacy/TCC với lỗi quyền filesystem thông thường khi ứng dụng không truy cập được tài nguyên ra sao?
Bạn xác định khi nào cần kiểm tra FileVault, Secure Boot hoặc trạng thái bảo vệ hệ thống trong quá trình xử lý sự cố như thế nào?
Bạn đánh giá khác biệt trong cách thu thập bằng chứng giữa Linux, Windows và macOS để bảo đảm so sánh đúng ngữ cảnh ra sao?
Bạn phân biệt lỗi phần cứng, driver và hệ điều hành bằng phép thử chéo hoặc dữ liệu chẩn đoán nào?
Bạn xây dựng phương pháp tái hiện sự cố trên môi trường thử nghiệm mà không làm ảnh hưởng máy production như thế nào?
Bạn xác định khi nào nên khởi động lại máy và dữ liệu nào cần thu trước khi restart như thế nào?
Bạn kiểm tra tác động của reboot tới tiến trình, kết nối, file tạm và trạng thái chưa ghi bền như thế nào?
Bạn phân biệt restart service, restart tiến trình và reboot toàn hệ thống theo phạm vi ảnh hưởng ra sao?
Bạn lựa chọn biện pháp khôi phục an toàn khi máy không phản hồi nhưng vẫn cần giữ dữ liệu đang chạy như thế nào?
Bạn đánh giá một thao tác kill tiến trình có thể làm hỏng dữ liệu hoặc để lại trạng thái không nhất quán ra sao?
Bạn thiết kế quy trình thay đổi cấu hình có snapshot hoặc rollback trước khi can thiệp như thế nào?
Bạn xác định những bằng chứng cần thu trước khi xóa cache, dọn log hoặc giải phóng dung lượng ra sao?
Bạn xử lý sự cố disk full khẩn cấp mà vẫn bảo toàn log và dữ liệu cần cho điều tra như thế nào?
Bạn lựa chọn khi nào cần chuyển workload hoặc drain node trước khi bảo trì hệ điều hành ra sao?
Bạn đánh giá ảnh hưởng của cập nhật kernel hoặc driver đến khả năng tái hiện và điều tra sự cố như thế nào?
Bạn xác định cách so sánh cấu hình trước và sau thay đổi bằng configuration diff ra sao?
Bạn kiểm tra một bản sửa lỗi có làm thay đổi hành vi ngoài phạm vi dự kiến bằng những phép thử nào?
Bạn xây dựng checklist sau khắc phục để xác minh tiến trình, service, network và tài nguyên hoạt động ổn định như thế nào?
Bạn theo dõi các chỉ số nào trong khoảng thời gian sau khắc phục để phát hiện tái phát ra sao?
Bạn xác định khi nào cần mở rộng giám sát hoặc bổ sung alert sau một sự cố đã xử lý như thế nào?
Bạn tổ chức postmortem để chuyển bằng chứng điều tra thành hành động phòng ngừa có người phụ trách và thời hạn ra sao?
Bạn đánh giá chất lượng runbook qua khả năng giúp một người khác tái hiện và xác minh chẩn đoán như thế nào?
Bạn phân biệt root cause, contributing factor và trigger trong báo cáo sự cố ra sao?
Bạn xác định cách ghi nhận mức độ chắc chắn và những giới hạn còn lại của kết luận kỹ thuật như thế nào?
Bạn xây dựng báo cáo sự cố đa nền tảng có thể giúp đội khác hiểu rõ triệu chứng, tác động, nguyên nhân và xác minh khắc phục ra sao?
Bạn lựa chọn tiêu chí nghiệm thu một quy trình troubleshooting dựa trên độ chính xác, thời gian chẩn đoán và tỷ lệ tái phát như thế nào?
