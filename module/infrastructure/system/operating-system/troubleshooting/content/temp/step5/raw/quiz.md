Câu 1. Khi tiếp nhận sự cố hệ điều hành, bước đầu tiên nào giúp tránh chẩn đoán theo phỏng đoán?
A. Khoanh vùng triệu chứng, ảnh hưởng và mốc thời gian.
B. Khởi động lại máy ngay để xem lỗi có tự biến mất.
C. Cập nhật toàn bộ package và driver trước khi thu thập log.
D. Tắt các dịch vụ không quen thuộc để giảm tải hệ thống.
Đáp án đúng: A

Câu 2. Vì sao nên ghi lại baseline trước khi thay đổi cấu hình?
A. Để bảo đảm mọi chỉ số sau đó luôn thấp hơn baseline.
B. Để tránh phải thu thập log khi sự cố tái diễn.
C. Tạo mốc đối chiếu trước và sau thay đổi.
D. Để chứng minh nguyên nhân gốc trước khi kiểm tra giả thuyết.
Đáp án đúng: C

Câu 3. Lệnh Linux `ps -eo pid,ppid,stat,%cpu,%mem,comm` giúp xem gì?
A. Socket đang lắng nghe, địa chỉ IP và route của từng process.
B. Lịch sử khởi động, lỗi kernel và service đã restart.
C. Liệt kê process cùng trạng thái và tài nguyên.
D. Dung lượng filesystem, inode và các thư mục chiếm chỗ.
Đáp án đúng: C

Câu 4. Khi muốn quan sát CPU và process đang thay đổi theo thời gian trên Linux, công cụ nào phù hợp?
A. `df -h` để theo dõi CPU và mức sử dụng process.
B. `ip route` để theo dõi CPU theo từng network interface.
C. `journalctl -u` để đo phần trăm CPU của từng thread.
D. `top` hoặc `htop` để theo dõi process và mức sử dụng tài nguyên.
Đáp án đúng: D

Câu 5. Load average trên Linux biểu thị điều gì?
A. Trung bình tác vụ runnable và uninterruptible.
B. Phần trăm CPU đã sử dụng trong các khoảng thời gian tương ứng.
C. Tỷ lệ RAM còn trống sau khi trừ page cache và buffer.
D. Số process đã kết thúc nhưng chưa được parent thu hồi.
Đáp án đúng: A

Câu 6. Khi CPU cao theo từng đợt ngắn, cách đo nào giúp xác định process gây tải?
A. Chỉ xem một ảnh chụp `ps` sau khi đợt tải đã kết thúc.
B. Chạy `df -i` để tìm process chiếm CPU theo inode.
C. Xem tổng load average rồi kết luận process đứng đầu.
D. Lấy mẫu process theo chu kỳ và đối chiếu lúc tải.
Đáp án đúng: D

Câu 7. Process Linux ở trạng thái `D` kéo dài thường gợi ý điều gì?
A. Process đã kết thúc nhưng parent chưa thu hồi mã thoát.
B. Process đang chờ người dùng nhập dữ liệu từ terminal.
C. Process bị scheduler tạm dừng vì không còn CPU được cấp.
D. Đang chờ I/O không ngắt được; xem storage và kernel log.
Đáp án đúng: D

Câu 8. Zombie process thường có đặc điểm nào?
A. Process vẫn chạy và liên tục chiếm CPU trong nền.
B. Đã kết thúc nhưng parent chưa thu hồi trạng thái.
C. Process bị kẹt trong I/O và không thể nhận tín hiệu.
D. Process đang ngủ và giữ toàn bộ RAM vật lý của máy.
Đáp án đúng: B

Câu 9. Trên Windows, công cụ nào phù hợp để xem process, CPU, memory và chi tiết tài nguyên theo process?
A. Task Manager hoặc Resource Monitor.
B. Disk Management hoặc Device Manager.
C. Event Viewer hoặc Registry Editor.
D. Windows Update hoặc Services console.
Đáp án đúng: A

Câu 10. Trên macOS, công cụ đồ họa nào giúp kiểm tra process và áp lực tài nguyên?
A. Disk Utility với các tab CPU, Memory và Network.
B. Activity Monitor xem CPU, Memory, Disk và Energy.
C. Console với các tab Process, Route và Filesystem.
D. Keychain Access với danh sách process và thread.
Đáp án đúng: B

Câu 11. Để kiểm tra một service systemd trên Linux, cặp lệnh nào hữu ích?
A. `df -h` và `du -sh` cho service đó.
B. `systemctl status` cùng `journalctl -u`.
C. `ip addr` và `ip route` cho service đó.
D. `lsmod` và `modinfo` cho service đó.
Đáp án đúng: B

Câu 12. Trên Windows, `Get-Service` chủ yếu cung cấp thông tin gì?
A. Tên, trạng thái và thông tin quản lý service.
B. Danh sách process cùng mức dùng CPU theo từng thread.
C. Các sự kiện lỗi và cảnh báo trong Event Log.
D. Các port TCP đang lắng nghe cùng PID sở hữu.
Đáp án đúng: A

Câu 13. Để kiểm tra trạng thái một LaunchDaemon trên macOS, công cụ nào phù hợp?
A. `systemctl status <label>` với label của daemon.
B. Tra trạng thái daemon bằng launchctl.
C. `Get-Service <label>` trong PowerShell.
D. `diskutil info <label>` với tên daemon.
Đáp án đúng: B

Câu 14. Khi service Linux vừa thất bại sau lần reboot gần nhất, cách xem log nào có ích?
A. `journalctl --disk-usage` để xem stack trace của service.
B. `dmesg -C` để đọc toàn bộ log ứng dụng theo service.
C. `journalctl -b -u <service>` để giới hạn theo boot và service.
D. `systemctl list-dependencies` để xem nội dung log của service.
Đáp án đúng: C

Câu 15. Windows service dừng bất ngờ; nguồn nào nên kiểm tra đầu tiên để tìm dấu vết?
A. Danh sách file trong Recycle Bin và lịch sử trình duyệt.
B. Danh sách driver trong Device Manager không kèm timestamp.
C. System và Application logs trong Event Viewer quanh thời điểm lỗi.
D. Windows Update history mà không đối chiếu thời điểm sự cố.
Đáp án đúng: C

Câu 16. Trên macOS, lệnh `log show` với predicate theo process hữu ích để làm gì?
A. Đọc trực tiếp nội dung file log của mọi ứng dụng bất kể nguồn.
B. Liệt kê các process đang chiếm CPU trong thời gian thực.
C. Xóa log cũ theo process để giải phóng dung lượng.
D. Lọc unified log theo process và khoảng thời gian cần điều tra.
Đáp án đúng: D

Câu 17. Khi Linux báo OOM kill, bằng chứng nào nên được kiểm tra?
A. Chỉ xem dung lượng filesystem vì OOM luôn do disk đầy.
B. Chỉ xem DNS cache vì OOM thường do truy vấn mạng.
C. Chỉ xem danh sách package cài đặt trước lần reboot.
D. Đọc kernel log và journal quanh thời điểm OOM.
Đáp án đúng: D

Câu 18. Trong `free -h` trên Linux, trường `available` hữu ích vì sao?
A. Ước lượng RAM còn có thể cấp cho ứng dụng mà không swap quá mức.
B. Cho biết tổng dung lượng swap đã được cấu hình trên máy.
C. Đếm tổng số byte đang nằm trong file log trên filesystem.
D. Cho biết RAM vật lý đã hỏng và không thể được kernel dùng.
Đáp án đúng: A

Câu 19. Trên Windows, chỉ số Committed trong Task Manager liên quan điều gì?
A. Dung lượng RAM vật lý còn trống trên từng DIMM.
B. Bộ nhớ committed so với giới hạn commit.
C. Dung lượng đĩa còn trống trên volume hệ thống.
D. Bộ nhớ cache của từng process chưa được ghi xuống đĩa.
Đáp án đúng: B

Câu 20. Trên macOS, Memory Pressure giúp đánh giá điều gì?
A. Áp lực bộ nhớ và khả năng đáp ứng nhu cầu RAM.
B. Phần trăm dung lượng filesystem còn trống trên ổ khởi động.
C. Số lượng process đang chờ DNS resolver trả lời.
D. Tốc độ đọc ghi mạng của các ứng dụng đang mở.
Đáp án đúng: A

Câu 21. Trên Linux, `df -h` và `df -i` được dùng để phân biệt vấn đề nào?
A. Dung lượng RAM còn trống và số process đang chạy.
B. Tốc độ đọc đĩa và số lỗi TCP retransmission.
C. Dung lượng block còn trống và số inode còn khả dụng.
D. Dung lượng swap còn trống và số file descriptor.
Đáp án đúng: C

Câu 22. Khi cần tìm thư mục chiếm nhiều dung lượng trong `/var`, công cụ nào phù hợp?
A. Dùng `df` để liệt kê dung lượng từng file riêng lẻ.
B. Dùng `du` để tổng hợp dung lượng theo thư mục.
C. Dùng `ps` để sắp xếp thư mục theo kích thước.
D. Dùng `ss` để đo dung lượng thư mục theo socket.
Đáp án đúng: B

Câu 23. File đã bị xóa nhưng dung lượng đĩa chưa được giải phóng trên Linux; nguyên nhân thường gặp là gì?
A. Filesystem tự nhân đôi file đã xóa trong page cache.
B. Kernel giữ mọi file đã xóa cho tới lần nâng cấp kế tiếp.
C. Process vẫn giữ file descriptor mở tới inode đã unlink.
D. Process zombie giữ nguyên toàn bộ block của file đã xóa.
Đáp án đúng: C

Câu 24. Khi nghi ngờ filesystem có lỗi cấu trúc, nguyên tắc an toàn nào phù hợp?
A. Chạy fsck sửa chữa trên mọi filesystem đang mount để tránh downtime.
B. Xóa journal filesystem rồi reboot để tự tái tạo metadata.
C. Tiếp tục ghi dữ liệu lớn để kiểm tra filesystem có tự hồi phục.
D. Thu thập log và kiểm tra trạng thái mount trước repair.
Đáp án đúng: D

Câu 25. Trên Linux, `iostat -xz 1` có thể giúp xác định vấn đề nào?
A. Dung lượng inode và số file đã xóa trong mỗi thư mục.
B. Số kết nối TCP và thời gian phân giải DNS.
C. Đo latency và utilization của thiết bị lưu trữ.
D. Mức sử dụng CPU theo từng process và thread.
Đáp án đúng: C

Câu 26. Trên Linux, `ip addr` và `ip route` giúp xác minh điều gì?
A. Địa chỉ interface và bảng định tuyến hiện tại.
B. Bản ghi DNS cache và chứng chỉ TLS của host.
C. Các process mở port và trạng thái service systemd.
D. Dung lượng filesystem và trạng thái SMART của ổ đĩa.
Đáp án đúng: A

Câu 27. Để kiểm tra phân giải tên theo cơ chế NSS mà ứng dụng Linux thường sử dụng, lệnh nào hữu ích?
A. `getent hosts <hostname>` qua NSS của hệ thống.
B. `dig <hostname>` truy vấn trực tiếp các DNS record.
C. `nslookup <hostname>` gửi câu hỏi tới DNS resolver.
D. `host <hostname>` thực hiện một DNS lookup.
Đáp án đúng: A

Câu 28. Trên Linux, `ss -lntp` thường được dùng để kiểm tra gì?
A. Các kết nối UDP đã phân giải DNS và cache TTL.
B. Các route mặc định cùng gateway theo interface.
C. Các file log đang mở bởi process và dung lượng của chúng.
D. Socket TCP đang lắng nghe, port và process liên quan.
Đáp án đúng: D

Câu 29. Vì sao `ping` thất bại chưa đủ để kết luận dịch vụ ứng dụng không truy cập được?
A. ICMP có thể bị chặn trong khi TCP port và ứng dụng vẫn hoạt động.
B. Ping luôn dùng TCP nên lỗi ping chứng minh port ứng dụng đóng.
C. Ping chỉ hoạt động khi DNS có bản ghi PTR hợp lệ.
D. Ping kiểm tra HTTP status nên thất bại chứng minh server trả 5xx.
Đáp án đúng: A

Câu 30. Khi cần xem gói tin đi qua interface trong lúc tái hiện lỗi mạng, công cụ nào phù hợp?
A. Dùng tcpdump lọc host/port và capture có giới hạn.
B. `top` với PID của network interface và khoảng refresh một giây.
C. `df -h` với mount point chứa file cấu hình mạng.
D. `journalctl --vacuum-time` để lưu gói tin vào journal.
Đáp án đúng: A

Câu 31. Trên Windows, `Test-NetConnection -ComputerName host -Port 443` giúp kiểm tra điều gì?
A. Khả năng phân giải mọi loại DNS record của host.
B. Nội dung chứng chỉ TLS và chuỗi CA của endpoint.
C. Trạng thái service Windows đang sở hữu port 443.
D. Kiểm tra TCP handshake tới host và port.
Đáp án đúng: D

Câu 32. Trên macOS, `scutil --dns` hữu ích khi cần kiểm tra điều gì?
A. Các process đang giữ file đã xóa trên filesystem.
B. Cấu hình resolver DNS mà hệ thống đang sử dụng.
C. Trạng thái service được quản lý bởi launchd.
D. Bảng route IPv4 và IPv6 của mọi interface.
Đáp án đúng: B

Câu 33. Khi TLS handshake thất bại, bước kiểm tra nào giúp phân biệt lỗi chứng chỉ và kết nối?
A. Dùng `ping` để xác định certificate hết hạn hay chưa.
B. Dùng openssl kiểm tra handshake, SNI và certificate.
C. Dùng `df -h` để kiểm tra chain CA đã được mount.
D. Dùng `ps` để suy ra cipher suite của server.
Đáp án đúng: B

Câu 34. Một service chạy thủ công được nhưng thất bại khi chạy dưới service manager; nên kiểm tra gì?
A. Đổi kernel ngay vì service manager luôn dùng kernel khác.
B. Tăng CPU priority cho mọi process trong máy.
C. Xóa cache DNS vì service manager không kế thừa DNS resolver.
D. So sánh môi trường chạy tay với service account.
Đáp án đúng: D

Câu 35. Khi process chạm giới hạn file descriptor trên Linux, bằng chứng nào hữu ích?
A. Kiểm tra `df -i` rồi kết luận giới hạn FD bằng số inode.
B. Kiểm tra `free -h` để đọc giới hạn FD trong swap.
C. Kiểm tra `ulimit -n`, `/proc/<pid>/limits` và số FD đang mở.
D. Kiểm tra `ip route` để đếm số file descriptor đang mở.
Đáp án đúng: C

Câu 36. Vì sao cần đồng bộ thời gian và kiểm tra timezone khi ghép log nhiều máy?
A. Timezone quyết định PID được cấp cho process trên từng host.
B. Đồng hồ sai khiến filesystem tự đổi owner của file log.
C. NTP chỉ ảnh hưởng dashboard, không ảnh hưởng điều tra nguyên nhân.
D. Timestamp lệch làm sai thứ tự sự kiện và tương quan giữa các log.
Đáp án đúng: D

Câu 37. Event Windows Kernel-Power 41 thường chứng minh điều gì?
A. Nguồn điện chắc chắn là nguyên nhân duy nhất của lần reboot.
B. Driver GPU luôn là nguyên nhân khi event 41 xuất hiện.
C. Event 41 chỉ ghi nhận shutdown bất thường; cần thêm bằng chứng.
D. Ổ đĩa hệ thống chắc chắn có bad sector gây reboot.
Đáp án đúng: C

Câu 38. Khi áp dụng biện pháp khắc phục trên máy đang gặp sự cố, cách nào giúp giảm rủi ro?
A. Thay nhiều cấu hình cùng lúc để giảm số lần kiểm tra.
B. Thay từng yếu tố, có thể rollback và ghi lại.
C. Xóa log và cache trước để tránh dữ liệu cũ gây nhiễu.
D. Tắt monitoring để thao tác sửa chữa không bị cảnh báo.
Đáp án đúng: B

Câu 39. Sau khi sửa lỗi, bằng chứng nào cho thấy nguyên nhân gốc đã được xử lý?
A. Chỉ xác nhận process đã restart và trạng thái service là running.
B. Theo dõi tái hiện, chỉ số hồi phục và tái phát.
C. Chỉ xác nhận người dùng không gửi thêm ticket trong vài phút.
D. Xóa cảnh báo cũ rồi xem dashboard không còn màu đỏ.
Đáp án đúng: B

Câu 40. Khi Linux chậm và cần quan sát run queue, swap activity và I/O wait theo chu kỳ, công cụ nào phù hợp?
A. `iostat -xz 1` chỉ tổng hợp độ trễ và mức bận của từng thiết bị block.
B. `free -h` chụp nhanh tổng RAM, cache và swap đang dùng trên máy.
C. `vmstat 1` hiển thị run queue, blocked tasks, swap và CPU wait theo chu kỳ.
D. `sar -n DEV 1` thống kê lưu lượng nhận gửi của từng network interface.
Đáp án đúng: C
