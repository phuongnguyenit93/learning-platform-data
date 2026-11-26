Câu 1: Playbook có hosts: all, inventory chia nhóm web và db. Muốn chỉ chạy trên nhóm web mà không sửa playbook, nên dùng gì?
A. Dùng --tags web để chỉ chọn các máy web trong inventory.
B. Dùng --limit web để giới hạn tập máy đích của lượt chạy.
C. Dùng --skip-tags db để bỏ nhóm máy db khỏi tập đích.
D. Dùng --start-at-task web để bắt đầu với nhóm máy web.
Đáp án đúng: B

Câu 2: Nhóm quản trị máy Windows đã bật WinRM nhưng không cài OpenSSH. Biến kết nối nào cần đặt trong inventory?
A. Đặt ansible_connection: ssh để dùng SSH trên máy Windows.
B. Đặt ansible_connection: local để chạy từ control node.
C. Đặt ansible_connection: network_cli để điều khiển Windows.
D. Đặt ansible_connection: winrm để kết nối qua WinRM.
Đáp án đúng: D

Câu 3: Máy Linux yêu cầu SSH bằng user deploy và file khóa riêng tại control node. Hai biến inventory nào cần dùng?
A. Dùng ansible_become_user và ansible_become_password.
B. Dùng ansible_user và ansible_ssh_private_key_file.
C. Dùng ansible_connection và ansible_python_interpreter.
D. Dùng ansible_host và ansible_port để chỉ định thông tin.
Đáp án đúng: B

Câu 4: Chạy playbook lần hai trên Debian đã cài nginx phải giữ trạng thái unchanged nếu không có gì cần sửa. Task nào phù hợp?
A. Dùng ansible.builtin.apt với name=nginx và state=present.
B. Dùng ansible.builtin.command để gọi apt install nginx.
C. Dùng ansible.builtin.shell để gọi apt-get install nginx.
D. Dùng ansible.builtin.raw để gọi apt install nginx.
Đáp án đúng: A

Câu 5: File cấu hình Nginx cần thay listen_port theo host_vars từ một tệp .j2. Module Ansible nào phù hợp nhất?
A. Dùng ansible.builtin.copy để chuyển tệp cấu hình nguyên bản.
B. Dùng ansible.builtin.lineinfile để sửa một dòng bất kỳ.
C. Dùng ansible.builtin.template để render nội dung Jinja2.
D. Dùng ansible.builtin.fetch để lấy tệp cấu hình từ host.
Đáp án đúng: C

Câu 6: Thay đổi cấu hình ứng dụng xong, dịch vụ chỉ được restart nếu tệp thực sự đổi. Playbook nên tổ chức ra sao?
A. Task chỉnh tệp notify handler restart khi task báo changed.
B. Gọi restart cuối play bất kể nội dung tệp đã được thay đổi hay chưa.
C. Đặt restart trước task chỉnh tệp rồi chạy phần còn lại.
D. Đặt restart trong always để dịch vụ được khởi động lại.
Đáp án đúng: A

Câu 7: Biến app_port khai báo trong group_vars/web.yml và host_vars/web01.yml, không có nguồn ghi đè nào khác. web01 nhận giá trị từ đâu?
A. Từ group_vars/web.yml vì giá trị của nhóm luôn ưu tiên trên host.
B. Từ role defaults vì giá trị mặc định luôn thắng các biến.
C. Từ host_vars/web01.yml vì host vars ưu tiên hơn group vars.
D. Từ tên nhóm web vì biến app_port cùng tên sẽ bị bỏ qua.
Đáp án đúng: C

Câu 8: Task kiểm tra binary đã ghi kết quả vào register: check_result. Task sau chỉ chạy khi mã thoát bằng 0. Dùng gì?
A. Dùng changed_when: check_result.rc == 0 ở task sau.
B. Dùng failed_when: check_result.rc == 0 ở task sau.
C. Dùng notify: check_result.rc == 0 ở task sau.
D. Dùng when: check_result.rc == 0 ở task sau.
Đáp án đúng: D

Câu 9: Repository Git chứa group_vars có mật khẩu CSDL. Muốn bảo vệ giá trị khi lưu trữ và giải mã lúc chạy, nên dùng gì?
A. Mã hóa group_vars bằng Ansible Vault, quản lý khóa giải mã riêng.
B. Để group_vars dạng rõ và dùng no_log ở tất cả task liên quan.
C. Đưa group_vars vào .gitignore dù secret đã commit lên Git.
D. Mã hóa kết nối SSH nhưng giữ mật khẩu dạng rõ trong Git.
Đáp án đúng: A

Câu 10: Task gửi secret tới API nội bộ; không muốn secret xuất hiện trong log CI từ tham số hoặc kết quả task. Thiết lập nào phù hợp?
A. Dùng diff: true để giới hạn giá trị nhạy cảm trong log.
B. Dùng verbosity: 0 để ẩn hoàn toàn secret trong output.
C. Dùng no_log: true trên task có dữ liệu nhạy cảm.
D. Dùng ignore_errors: true để che thông tin khi lỗi.
Đáp án đúng: C

Câu 11: Trước khi cập nhật template trên nhiều máy, cần dự đoán thay đổi và xem diff khi module hỗ trợ. Tổ hợp cờ nào phù hợp?
A. Dùng --list-hosts và --start-at-task để so sánh tệp.
B. Dùng --syntax-check và --list-tasks để so sánh nội dung.
C. Dùng --flush-cache và --verbose để chạy thử thay đổi.
D. Dùng --check và --diff để kiểm tra trước và xem khác biệt.
Đáp án đúng: D

Câu 12: Nhóm đưa cấu hình máy chủ web vào role tên webserver. Theo quy ước, Ansible tìm các task chính của role ở đâu?
A. roles/webserver/handlers/main.yml là tệp task chính.
B. roles/webserver/defaults/main.yml là tệp task chính.
C. roles/webserver/templates/main.yml là tệp task chính.
D. roles/webserver/tasks/main.yml là tệp task chính.
Đáp án đúng: D

Câu 13: Để tránh nhầm module trùng tên từ các collection, nhóm muốn gọi module apt bằng tên đầy đủ. Cú pháp nào đúng?
A. Dùng ansible.apt.builtin để gọi module quản lý apt trên Debian.
B. Dùng ansible.builtin.apt để gọi module quản lý apt.
C. Dùng builtin.ansible.apt để gọi module quản lý apt.
D. Dùng apt.ansible.builtin để gọi module quản lý apt.
Đáp án đúng: B

Câu 14: Playbook cập nhật 20 máy web nhưng mỗi đợt chỉ nên tác động tối đa hai máy để giảm rủi ro. Khai báo gì?
A. Đặt serial: 2 trong play để chạy theo từng lô hai host.
B. Đặt forks: 2 trong play để chia inventory thành các lô cập nhật.
C. Đặt throttle: 2 ở task để chia play thành từng lô host.
D. Đặt strategy: free để tất cả task chạy hai máy một đợt.
Đáp án đúng: A

Câu 15: Khi task nâng cấp package thất bại, cần thu thập log; dù thành công hay thất bại vẫn phải xóa file tạm. Dùng cấu trúc gì?
A. Dùng notify khi lỗi và changed_when để dọn file tạm.
B. Dùng ignore_errors cho mọi task rồi chạy lại toàn play.
C. Dùng block cho tác vụ chính, rescue khi lỗi và always dọn.
D. Dùng serial để chạy lần lượt, bỏ qua xử lý lỗi riêng.
Đáp án đúng: C

Câu 16: Muốn bảo đảm nginx được bật khi boot và đang chạy trên Linux dùng systemd. Trạng thái nào phù hợp?
A. Dùng systemd_service với enabled=false và state=started.
B. Dùng systemd_service với enabled=true và state=started.
C. Dùng systemd_service với enabled=true và state=stopped.
D. Dùng systemd_service với enabled=false và state=restarted.
Đáp án đúng: B
