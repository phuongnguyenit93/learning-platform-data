# Command audit trên Linux trong hệ thống PAM

Command audit là việc ghi nhận, liên kết và bảo vệ bằng chứng về các lệnh được thực thi trên Linux, đặc biệt trong những phiên sử dụng quyền quản trị. Mục tiêu là trả lời được: **ai khởi tạo hành động, đang dùng quyền của tài khoản nào, thực thi chương trình gì, trên máy nào, trong phiên nào và có bằng chứng nào về kết quả**.

Một dòng log “user đã đăng nhập” chưa trả lời được người đó làm gì sau khi nhận quyền. Ngược lại, một bản ghi “root chạy chương trình” cũng chưa đủ để quy trách nhiệm cho người đã mở phiên. Thiết kế command audit cần nối hai đầu này, rồi liên kết chúng với yêu cầu truy cập và phê duyệt của hệ thống quản lý truy cập đặc quyền.

Trong bài này, PAM của module là **Privileged Access Management**. Linux-PAM là bộ cơ chế xác thực, kiểm tra tài khoản và quản lý phiên của Linux. Hai khái niệm có liên quan nhưng không đồng nhất: module Linux-PAM có thể giúp giữ dấu danh tính phiên; nó không tự biến toàn bộ hoạt động của shell thành một nhật ký lệnh đầy đủ.

## 1. Kết quả cần đạt

Sau bài học, người học có thể:

- Phân biệt lịch sử shell, nhật ký quyết định của `sudo`, sự kiện Linux Audit và bản ghi đầu vào/đầu ra của phiên.
- Giải thích sự khác nhau giữa `auid`, `uid`, `euid` và danh tính người dùng ở hệ thống PAM.
- Thiết kế một phạm vi thu thập lệnh có chủ đích, thay vì cho rằng ghi mọi `execve` tương đương ghi mọi hành động.
- Thiết lập và kiểm tra rule audit minh họa trong máy lab.
- Ghép các record thành sự kiện, đối chiếu với phiên đặc quyền và nhận diện khoảng trống bằng chứng.
- Xây dựng tiêu chí vận hành cho chuyển log, bảo vệ bí mật và xử lý khi đường thu thập gặp lỗi.

Bài tập cấu hình dưới đây dành cho máy Linux lab đã được cho phép quản trị. Các ví dụ không phải cấu hình áp dụng nguyên xi cho mọi bản phân phối hay mọi máy production.

## 2. Tách ba câu hỏi: được phép làm gì, đã chạy gì, kết quả là gì?

Một yêu cầu hợp lệ có thể là: “Kỹ sư An được xem trạng thái dịch vụ thanh toán trong 15 phút, theo ticket CHG-2048”. Ba lớp bằng chứng cần được phân biệt:

| Câu hỏi | Nguồn bằng chứng phù hợp | Điều chưa thể suy ra chỉ từ nguồn đó |
| --- | --- | --- |
| An có được phép thao tác không? | Phê duyệt PAM, quyền JIT, chính sách `sudo` | Chưa chứng minh lệnh đã được chạy |
| Tiến trình đặc quyền đã khởi chạy chương trình nào? | Sự kiện thực thi từ Linux Audit, log lệnh của công cụ nâng quyền | Chưa chứng minh tác động nghiệp vụ đã hoàn tất |
| Lệnh có kết quả gì? | Mã kết thúc tiến trình, output, log dịch vụ, kiểm tra trạng thái sau thay đổi | Output có thể thiếu hoặc không phản ánh toàn bộ tác động |

Command audit chủ yếu làm rõ hành vi thực thi. Nó hỗ trợ điều tra, kiểm toán và phát hiện bất thường; bản thân việc ghi log không thay thế least privilege hoặc cơ chế chặn lệnh.

Ví dụ, việc ghi nhận một chương trình quản trị tài khoản được khởi chạy không tự chứng minh tài khoản mới đã được tạo thành công. Muốn xác nhận kết quả phải đối chiếu thêm mã kết thúc, dữ liệu tài khoản và log có liên quan.

Ngược lại, một lệnh bị `sudo` từ chối là bằng chứng quan trọng về một yêu cầu trái chính sách, dù không có tiến trình đích chạy với quyền root. Nếu chỉ thu lệnh đã thực thi ở `euid=0`, hệ thống sẽ bỏ qua phần quyết định từ chối này.

## 3. Kiến trúc bằng chứng theo nhiều lớp

Một thiết kế thực tế thường có chuỗi sau:

```text
Danh tính cá nhân + MFA
        |
Yêu cầu PAM / phê duyệt / quyền có thời hạn
        |
SSH hoặc cổng truy cập quản trị
        |
sudo / công cụ ủy quyền
        |
Tiến trình Linux và các sự kiện audit
        |
Bộ thu log ngoài máy đích + kho bằng chứng
```

Không có một khóa duy nhất luôn xuất hiện ở tất cả các lớp. PAM có thể có mã phiên riêng; Linux Audit có audit session ID; `sudo` có thể có mã I/O log. Vì vậy phải thiết kế ánh xạ giữa các nguồn, thay vì đặt cùng tên trường `session_id` rồi mặc định chúng trùng nhau.

| Lớp thu thập | Giá trị chính | Giới hạn cần nhớ |
| --- | --- | --- |
| Lịch sử shell | Hỗ trợ người vận hành xem lại lệnh đã nhập | Có thể bị sửa, thiếu phiên hoặc chưa ghi xuống đĩa |
| Event log của `sudo` | Người yêu cầu, tài khoản đích, lệnh được phép hoặc bị từ chối | Lệnh con của một root shell cần cơ chế bổ sung |
| Linux Audit | Góc nhìn ở lớp kernel về syscall và thông tin tiến trình | Không ghi mọi thao tác bên trong một tiến trình |
| I/O recording | Ngữ cảnh hiển thị và luồng dữ liệu của phiên được ghi | Không đồng nghĩa với nhật ký chương trình đã thực thi |
| Log ứng dụng, dịch vụ | Tác động ở hệ thống đích và nghiệp vụ | Cần ánh xạ người thao tác hoặc yêu cầu gốc |
| Kho log độc lập | Lưu giữ, truy vấn và hạn chế khả năng sửa bằng chứng | Cần theo dõi tính đầy đủ của luồng gửi nhận |

Lịch sử shell vẫn hữu ích khi hỗ trợ vận hành, nhưng không nên là bằng chứng duy nhất của một phiên đặc quyền. Một chính sách chỉ bật `HISTTIMEFORMAT` hoặc lưu `.bash_history` chưa tạo ra command audit đáng tin cậy.

## 4. Giữ được danh tính gốc khi chuyển sang root

### 4.1. Các trường định danh

Giả sử An đăng nhập bằng tài khoản cá nhân UID 1001, sau đó chạy một lệnh qua `sudo` với tài khoản đích root.

| Trường | Ý nghĩa khi đọc bằng chứng |
| --- | --- |
| `auid` hoặc login UID | Danh tính đăng nhập gốc được gắn vào chuỗi tiến trình audit |
| `uid` | Real UID của tiến trình tại thời điểm sự kiện |
| `euid` | Effective UID đang dùng để kiểm tra nhiều quyền truy cập |
| `ses` | Mã phiên của Linux Audit, nếu được thiết lập |
| `pid`, `ppid` | Tiến trình và tiến trình cha trên máy đích |
| Tài khoản đích trong log `sudo` | Tài khoản mà người dùng yêu cầu chuyển quyền sang |
| Actor ID của PAM | Định danh ở hệ thống quản lý truy cập, cần ánh xạ sang tài khoản Linux |

Trong phiên được cấu hình đúng, lệnh chạy bằng root có thể có `auid=1001` và `euid=0`. Đây là thông tin có giá trị: tài khoản đang có quyền là root, còn nguồn gốc đăng nhập vẫn là UID 1001.

Tuy nhiên, không thể chỉ nhìn số 1001 rồi kết luận đó luôn là An. UID có thể được tái sử dụng sau khi xóa tài khoản; tài khoản cục bộ cùng tên cũng có thể khác nhau giữa các host. Cần lưu host identity và ánh xạ danh tính theo thời điểm xảy ra sự kiện.

### 4.2. Vai trò của pam_loginuid

Module `pam_loginuid` thiết lập thuộc tính login UID ở ứng dụng đầu vào của phiên. Tài liệu Linux-PAM chỉ ra rằng module này phù hợp với điểm vào như `sshd` hoặc `login`; đặt nó ở `sudo` hoặc `su` có thể làm mất ý nghĩa danh tính gốc do ghi lại tài khoản vừa chuyển sang. Tham khảo [tài liệu pam_loginuid của Linux-PAM](https://github.com/linux-pam/linux-pam/blob/master/modules/pam_loginuid/pam_loginuid.8.xml).

Có thể quan sát phiên hiện tại bằng:

```bash
id
cat /proc/self/loginuid
cat /proc/self/sessionid
```

Đây là thao tác đọc. Nó không cấu hình PAM stack và không chứng minh tất cả đường đăng nhập khác đã đúng.

Nếu login UID là `4294967295`, một số công cụ hiển thị là `unset` hoặc `-1`, phiên chưa có login UID hợp lệ. Không được tùy tiện gán trường này về một người để làm đẹp báo cáo. Cần xác định đường tạo phiên và sửa cấu hình ở đúng điểm vào.

Một tài khoản được nhiều người dùng chung vẫn không tạo được quy trách nhiệm cá nhân chỉ nhờ có `auid`. Nếu cổng PAM ánh xạ nhiều người sang cùng tài khoản đích, kho bằng chứng phải giữ ánh xạ actor–phiên–host ở phía cổng và bảo vệ nó tương xứng.

## 5. Chọn phạm vi trước khi viết rule

Cụm từ “audit lệnh đặc quyền” có thể chỉ nhiều phạm vi khác nhau:

1. Các lần người dùng yêu cầu chạy lệnh qua `sudo`, bao gồm yêu cầu bị từ chối.
2. Các chương trình được thực thi với effective UID root trong phiên của người dùng.
3. Mọi chương trình được thực thi trong một phiên đăng nhập, kể cả trước hoặc sau khi đổi quyền.
4. Chương trình chạy dưới tài khoản ứng dụng, có Linux capabilities hoặc trong container.
5. Thao tác ở dịch vụ từ xa do một lệnh trên máy Linux khởi tạo.

Không nên dùng một rule duy nhất rồi tuyên bố đã bao phủ cả năm phạm vi.

Ví dụ rule lọc `euid=0` phù hợp với một phần hoạt động root. Nó không bao phủ đầy đủ lệnh dưới tài khoản `postgres`, tài khoản ứng dụng không phải root hoặc tiến trình có capability nhạy cảm với `euid` khác 0.

Tương tự, điều kiện `auid>=1000` là giả định về dải tài khoản người dùng ở máy lab. Một doanh nghiệp dùng danh tính tập trung có thể có dải UID khác. Một tài khoản hệ thống cũng có thể nằm trong dải UID cao nếu chính sách cấp phát không nhất quán.

Phạm vi thu thập cần được ghi thành một quyết định rõ ràng, chẳng hạn:

> Thu các lần thực thi chương trình với euid root phát sinh từ phiên đăng nhập có auid thuộc dải người dùng đã xác minh; bổ sung log sudo cho quyết định cho phép/từ chối và một thiết kế riêng cho workload tự động.

Quyết định này giúp người đọc đánh giá khoảng trống mà không phải đoán từ câu “đã bật audit”.

## 6. Chuẩn bị máy lab

Ví dụ tiếp theo giả định:

- Máy lab 64-bit dùng Linux Audit và có các tiện ích `auditctl`, `ausearch`, `augenrules`.
- Người học dùng tài khoản cá nhân với UID từ 1000 trở lên.
- Có quyền quản trị phù hợp để xem và cấu hình audit trên máy lab.
- Rule hiện hành chưa bị khóa immutable, hoặc có quy trình thay đổi và reboot được chuẩn bị.
- Đường dẫn chương trình trong ví dụ đã được đối chiếu với máy lab.

Thu thập thông tin đầu vào:

```bash
uname -m
id
sudo -V
command -v auditctl
command -v ausearch
command -v augenrules
sudo auditctl -s
sudo auditctl -l
```

Có thể xem gợi ý dải tài khoản cục bộ trong `/etc/login.defs`, nhưng không dùng riêng `UID_MIN` làm bằng chứng cho toàn bộ chính sách danh tính tập trung.

Kết quả `auditctl -s` và `auditctl -l` cần được lưu vào hồ sơ lab trước khi thay đổi. Đặc biệt kiểm tra trạng thái enabled, daemon PID, mức mất record và các rule loại trừ. Trạng thái có rule trong file trên đĩa không chứng minh rule đã hoạt động trong kernel.

Nếu có cấu hình khóa `-e 2`, không cố tắt hoặc bỏ qua để nạp thử. Bài lab phải đi qua quy trình bảo trì phù hợp; thay đổi file trên đĩa chưa đồng nghĩa thay đổi có hiệu lực ngay.

## 7. Rule minh họa cho các chương trình root của phiên người dùng

### 7.1. Cấu hình hẹp có chủ đích

Trong môi trường dùng `augenrules`, tạo hoặc chỉnh file lab được quản lý riêng, ví dụ `/etc/audit/rules.d/50-pam-command.rules`, với dòng sau:

```text
-a always,exit -F arch=b64 -S execve,execveat -F auid>=1000 -F auid!=unset -F euid=0 -k pam_root_exec
```

Đây là nội dung file rule, không phải một dòng lệnh shell. Không thêm `sudo` hoặc tiền tố `auditctl` vào file.

Các thành phần có ý nghĩa:

| Thành phần | Vai trò |
| --- | --- |
| `always,exit` | Đánh giá việc tạo record ở bộ lọc syscall exit |
| `arch=b64` | Chọn bảng syscall cho ABI 64-bit trước khi phân giải tên syscall |
| `execve,execveat` | Nhắm vào các đường thực thi chương trình được nêu |
| `auid>=1000` | Giới hạn theo dải login UID giả định của lab |
| `auid!=unset` | Loại giá trị chưa thiết lập khỏi phép so sánh số |
| `euid=0` | Chọn sự kiện thỏa điều kiện effective UID root |
| `-k pam_root_exec` | Gắn nhãn để truy vấn và vận hành |

Không có `success=1` trong ví dụ, nên rule không chủ động loại sự kiện syscall thất bại nếu các điều kiện khác vẫn khớp. Đừng mặc định một lần thực thi thất bại có đủ các record đối số giống lần thành công; phải kiểm tra dữ liệu thực nhận.

Tài liệu [audit.rules của Linux Audit](https://github.com/linux-audit/audit-userspace/blob/master/docs/audit.rules.7) mô tả cú pháp rule, việc tách ABI và ý nghĩa của login UID chưa thiết lập. Cú pháp và syscall phải được kiểm tra với phiên bản đang cài.

Nếu kernel hoặc audit userspace không nhận `execveat`, thao tác nạp có thể báo lỗi. Ghi nhận khoảng trống đó, xác định phiên bản được hỗ trợ và triển khai thay đổi tương ứng; không giữ một dòng lỗi rồi đánh dấu phạm vi đã hoàn tất.

### 7.2. ABI 32-bit trên máy hỗ trợ bi-arch

Nếu host cho phép thực thi chương trình 32-bit và đó là phạm vi cần thu, bổ sung rule tương ứng sau khi kiểm tra khả năng hỗ trợ:

```text
-a always,exit -F arch=b32 -S execve,execveat -F auid>=1000 -F auid!=unset -F euid=0 -k pam_root_exec
```

Không tự động thêm `b32` cho mọi kiến trúc. Một máy không hỗ trợ ABI này có thể không nạp được rule hoặc không có trường hợp kiểm thử tương ứng.

### 7.3. Phương án thu rộng hơn cho phiên người dùng

Nếu yêu cầu là theo dõi chương trình trong toàn bộ phiên người dùng, có thể chọn phương án không lọc `euid=0`:

```text
-a always,exit -F arch=b64 -S execve,execveat -F auid>=1000 -F auid!=unset -k pam_login_exec
```

Đây là **phương án phạm vi khác**, không phải dòng phải thêm mặc định bên cạnh phương án hẹp. Những rule chồng lấn có thể làm việc giải thích key và đánh giá hiệu lực khó hơn; cần thiết kế thứ tự và thử nghiệm dữ liệu thực.

Phương án rộng thu được nhiều ngữ cảnh hơn nhưng làm tăng khối lượng dữ liệu và khả năng thu đối số chứa thông tin nhạy cảm. Nó vẫn không ghi được mọi thao tác bên trong một tiến trình đã tồn tại.

## 8. Nạp và xác minh cấu hình

Với máy lab đã xác nhận dùng `augenrules`:

```bash
sudo augenrules --check
sudo augenrules --load
sudo auditctl -l
sudo auditctl -s
```

`augenrules` tổng hợp các file `.rules` trong thư mục rule và có tùy chọn nạp vào kernel. `--check` kiểm tra nhu cầu cập nhật file tổng hợp, không phải một trình chứng minh toàn bộ cú pháp, coverage hay hiệu lực runtime. Chi tiết tại [tài liệu augenrules](https://github.com/linux-audit/audit-userspace/blob/master/docs/augenrules.8).

Khi nghiệm thu thay đổi, cần phân biệt:

- File nguồn có đúng nội dung không?
- Quá trình nạp có báo lỗi không?
- Rule mong muốn có xuất hiện trong danh sách runtime không?
- Một sự kiện thử mới có thực sự đi tới kho bằng chứng không?

Nếu một rule bị từ chối trong khi rule khác đã được nạp, không báo cả đợt là thành công. Ghi rõ phần đã áp dụng và phần chưa áp dụng trước khi khắc phục.

Không dùng `auditctl -D` như bước chuẩn bị thông thường vì nó có thể xóa các rule audit khác. Không vô hiệu audit để làm cho lab “chạy được”. Việc khóa immutable cũng cần là một thay đổi có kế hoạch sau khi cấu hình đã được kiểm tra, không nên ghép vào bài thử đầu tiên.

Rollback của lab là gỡ đúng phần cấu hình do bài lab thêm rồi nạp lại theo cơ chế của host. Nếu runtime đã khóa, việc khôi phục cần lịch reboot phù hợp. Không thay toàn bộ bộ rule bằng một bản mẫu ngắn.

## 9. Bổ sung log sudo và I/O recording

Linux Audit cho biết điều gì xảy ra ở tiến trình; log `sudo` bổ sung ý định yêu cầu nâng quyền và quyết định chính sách.

Một ví dụ thiết lập ghi output cho nhóm lab đã tồn tại là:

```sudoers
Defaults:%pamops use_pty
Defaults:%pamops log_output
```

Những dòng này không cấp quyền chạy lệnh cho nhóm. Quyền chạy phải được định nghĩa riêng theo least privilege. Chỉ thêm cấu hình bằng công cụ và quy trình quản lý `sudoers` của host; dùng `visudo` kiểm tra trước khi nghiệm thu.

Không bật `log_input` một cách mặc định chỉ để tăng lượng dữ liệu. Luồng đầu vào có thể chứa mật khẩu, khóa, nội dung tệp hoặc dữ liệu khách hàng. Output cũng có thể chứa bí mật, nên việc chỉ ghi output không loại bỏ yêu cầu phân quyền và bảo vệ bản ghi.

Một số phiên bản `sudo` hỗ trợ `log_subcmds` để ghi thêm chương trình con thông qua cơ chế intercept. Tính năng này có điều kiện tương thích và không bảo đảm ghi shell builtin. Cần thử đúng phiên bản và ứng dụng, không bật chỉ vì tên tùy chọn có vẻ phù hợp.

Tài liệu [sudoers của dự án sudo](https://github.com/sudo-project/sudo/blob/main/docs/sudoers.man.in) phân biệt event logging, I/O logging và ghi lệnh con. Người vận hành phải đối chiếu manual của phiên bản đã cài.

Hai câu hỏi phải được kiểm thử riêng:

1. Có event cho yêu cầu `sudo` ban đầu không?
2. Nếu lệnh mở shell hoặc chương trình tương tác, hoạt động bên trong được quan sát bằng nguồn nào?

Việc đã có bản ghi khởi chạy `sudo -i` không có nghĩa tất cả lệnh bên trong đã xuất hiện trong event log của `sudo`. Linux Audit và I/O recording có thể bổ sung nhau nhưng không thay thế hoàn toàn nhau.

## 10. Bài thử thực thi và cách diễn giải kết quả

### 10.1. Tạo một sự kiện dễ nhận diện

Đăng nhập mới bằng tài khoản cá nhân, kiểm tra login UID và ghi lại thời điểm bắt đầu lab:

```bash
date -u
id
cat /proc/self/loginuid
cat /proc/self/sessionid
```

Sau đó dùng một lệnh đọc thông tin đã được chính sách lab cho phép:

```bash
sudo /usr/bin/id
```

Điều kiện kỳ vọng với phương án `pam_root_exec`:

- Yêu cầu `sudo` được ghi với tài khoản khởi tạo và tài khoản đích.
- Có sự kiện thực thi chương trình `id` thỏa rule.
- Login UID của sự kiện khớp phiên cá nhân; effective UID của chương trình đích là root.
- Có thể tìm được sự kiện từ phía bộ thu log ngoài host sau thời gian gửi dự kiến.

Đường dẫn `/usr/bin/id` phải đúng trên host. Không mở rộng quyền `sudo` chỉ để ép một câu lệnh mẫu chạy thành công.

### 10.2. Tách khởi chạy thành công khỏi kết thúc thành công

Nếu lab đã cho phép, chạy:

```bash
sudo /usr/bin/false
```

Chương trình này có thể được khởi chạy thành công nhưng kết thúc với mã khác 0. Vì vậy `success=yes` của sự kiện syscall thực thi không được dịch thành “lệnh đã hoàn thành thành công”.

Để biết kết thúc của lệnh cần nguồn riêng, chẳng hạn exit status do công cụ quản lý phiên ghi nhận hoặc log kết quả tác vụ. Không dùng trường `exit` trong record syscall thực thi như mã kết thúc cuối cùng của toàn bộ chương trình.

### 10.3. Kiểm tra shell builtin

Trong một shell lab đang có quyền phù hợp theo chính sách hiện hành:

```bash
type cd
type printf
cd /
printf '%s' 'PAM-LAB-BUILTIN'
/usr/bin/printf '%s' 'PAM-LAB-EXTERNAL'
```

`cd` và `printf` có thể do shell xử lý trực tiếp; cần xem kết quả `type` để biết trường hợp thực tế. Bản external `/usr/bin/printf` là ví dụ để so sánh với chương trình được thực thi riêng.

Không kỳ vọng một record `execve` cho mỗi builtin. I/O recording có thể bổ sung ngữ cảnh phiên, nhưng việc nhìn thấy chuỗi ký tự cũng chưa chứng minh shell đã thực hiện thành công hành động đó.

### 10.4. Kiểm tra yêu cầu bị từ chối

Dùng một trường hợp kiểm thử đã định trước trong lab để xác nhận chính sách từ chối đúng. Bằng chứng kỳ vọng nằm ở quyết định của `sudo` hoặc hệ thống PAM.

Nếu chương trình đích không được chạy, không yêu cầu rule audit chương trình root phải tạo record như khi lệnh được cho phép. Đây là hai loại sự kiện khác nhau và phải có tiêu chí nghiệm thu riêng.

## 11. Đọc một sự kiện nhiều record

Ví dụ dưới đây là dữ liệu giả lập rút gọn để giải thích trường, không phải log thu từ máy đang chạy và không phải mẫu đầy đủ để nhập vào parser:

```text
type=SYSCALL msg=audit(1795741200.250:4201): arch=c000003e syscall=59 success=yes exit=0 ppid=2210 pid=2211 auid=1001 uid=0 euid=0 tty=pts0 ses=42 comm="id" exe="/usr/bin/id" key="pam_root_exec"
type=EXECVE msg=audit(1795741200.250:4201): argc=1 a0="/usr/bin/id"
type=CWD msg=audit(1795741200.250:4201): cwd="/home/an"
```

Các record cùng `msg=audit(...:4201)` thuộc một sự kiện trên host này. `ausearch` có khả năng trình bày các record của một sự kiện cùng nhau; không nên chỉ lấy từng dòng khớp tên chương trình rồi bỏ phần còn lại. Xem [tài liệu ausearch](https://github.com/linux-audit/audit-userspace/blob/master/docs/ausearch.8).

Diễn giải ví dụ:

- `auid=1001` là login UID để đối chiếu danh tính gốc.
- `euid=0` cho biết effective UID trong sự kiện là root.
- `exe` cho biết đường dẫn chương trình được ghi nhận; `a0` là đối số do bên gọi cung cấp, không phải định danh đáng tin tuyệt đối của executable.
- `cwd` bổ sung thư mục làm việc, hữu ích khi đối số dùng đường dẫn tương đối.
- `pid`, `ppid` hỗ trợ dựng quan hệ tiến trình trong khoảng thời gian tương ứng.
- `key` giúp tìm nhóm rule, không phải kết luận về mức độ độc hại.
- `success=yes` ở đây nói về syscall được audit, không chứng minh nghiệp vụ hoàn tất.

Sự kiện thực tế có thể có thêm `PATH`, `PROCTITLE` hoặc các record khác. Không buộc mọi syscall thực thi phải có đúng bộ record minh họa này.

Argument có thể được mã hóa hoặc chia thành nhiều phần. Chuỗi lệnh dài, khoảng trắng, dấu nháy và ký tự đặc biệt là các trường hợp phải kiểm thử parser. Không tách toàn bộ record theo dấu cách rồi giả định mỗi token là một field hoàn chỉnh.

Đối với kho đa host, chỉ số serial 4201 không phải định danh toàn cục. Cần gắn host identity, ngữ cảnh lần khởi động khi có và thời điểm sự kiện. PID và audit session ID cũng không nên được coi là duy nhất vĩnh viễn.

## 12. Truy vấn phục vụ xác minh và điều tra

Các lệnh sau chỉ đọc dữ liệu audit trong phạm vi tài khoản được cấp quyền:

```bash
sudo ausearch -k pam_root_exec -ts recent -i
sudo ausearch -k pam_root_exec -ul 1001 -ts today -i
sudo ausearch -m EXECVE -ts recent -i
sudo ausearch -a 4201 -ts today -i
```

`-ul` lọc theo login UID; không nhầm với một bộ lọc chỉ theo UID hiện tại. Khi xác minh actor, ưu tiên UID số và ánh xạ danh tính đúng thời điểm; tên được diễn giải trên máy phân tích có thể không phản ánh nguyên vẹn directory tại thời điểm sự kiện.

Một số lưu ý khi dùng kết quả:

- Cửa sổ `recent` hoặc `today` tiện cho lab, nhưng điều tra cần cửa sổ thời gian rõ ràng cùng múi giờ.
- Tìm theo `EXECVE` là cách kiểm tra record thực thi; không thay thế truy vấn log quyết định từ chối của `sudo`.
- Tìm theo serial phải gắn đúng host và khoảng thời gian, tránh gom các sự kiện trùng số ở phạm vi khác.
- Dữ liệu đã xoay vòng, lưu trữ hoặc chuyển về hệ thống trung tâm có thể không còn trong phạm vi truy vấn cục bộ mặc định.
- Không có kết quả chỉ chứng minh truy vấn hiện tại không trả về dữ liệu; chưa chứng minh không có hoạt động.

Ở kho tập trung, một truy vấn điều tra nên thể hiện rõ bộ điều kiện:

```text
host_id = máy đích đã xác minh
event_time = khoảng thời gian sự cố
login_uid = UID gốc của phiên cần điều tra
event_kind = thực thi chương trình hoặc quyết định sudo
pam_session_id = qua bảng liên kết phiên, nếu có
```

Đây là mô tả logic truy vấn, không phải cú pháp của một sản phẩm SIEM cụ thể.

## 13. Liên kết với ticket và phiên PAM

Một bản ghi thực thi thường không tự mang theo ticket phê duyệt. Không nên yêu cầu người vận hành nhập ticket vào một biến môi trường rồi coi đó là bằng chứng tin cậy duy nhất; người có quyền điều khiển phiên có thể sửa dữ liệu tự khai.

Thiết kế ánh xạ có thể gồm:

| Nhóm dữ liệu | Ví dụ trường cần lưu |
| --- | --- |
| Phê duyệt | Request ID, ticket, người phê duyệt, phạm vi, thời hạn |
| Danh tính | Actor ID ổn định, tài khoản đăng nhập đích, UID theo thời điểm |
| Phiên | Mã phiên PAM, audit `ses`, nguồn kết nối, thời điểm mở/đóng |
| Máy | Host ID, tên máy tại thời điểm sự kiện, ngữ cảnh boot khi có |
| Thực thi | Event ID, PID/PPID, executable, đối số, UID/EUID, key |
| Tiếp nhận | Thời điểm collector nhận, nguồn gửi, trạng thái xử lý |
| Bằng chứng bổ sung | Mã I/O recording, kết quả lệnh, log dịch vụ |

Ví dụ quá trình đối chiếu một lệnh ngoài phạm vi phê duyệt:

1. Lấy event thực thi trên host và xác định login UID, phiên và thời điểm.
2. Tìm phiên đăng nhập tương ứng từ SSH hoặc hệ thống quản lý phiên.
3. Ánh xạ phiên đích sang actor ở cổng PAM.
4. Tìm request còn hiệu lực, tài khoản và tài nguyên được phê duyệt.
5. Đối chiếu quyền được cấp với hành động thực tế và log kết quả.
6. Đánh dấu mức độ chắc chắn của kết luận và các nguồn đang thiếu.

Nếu có hai phiên đồng thời dùng cùng tài khoản đích và thiếu định danh phiên đủ mạnh, phải ghi nhận sự mơ hồ. Đừng chọn người gần thời điểm nhất rồi trình bày như một liên kết đã được chứng minh.

JIT hết hạn cũng chưa bảo đảm một tiến trình hoặc credential đã được cấp trước đó tự biến mất. Audit cần quan sát những phiên và hành động còn tiếp diễn sau khi cửa sổ quyền đóng, đồng thời cơ chế thu hồi quyền phải được kiểm tra riêng.

## 14. Những vùng mù quan trọng

### Shell, script và tiến trình tồn tại lâu

Một interpreter có thể xử lý nhiều hành động trong cùng tiến trình. Audit việc khởi chạy `bash` hoặc `python` không đồng nghĩa ghi được từng câu lệnh bên trong script.

Pipeline có thể khởi tạo nhiều chương trình; redirection thường do shell thực hiện. Một chuỗi người dùng nhập không nhất thiết tương ứng một record thực thi, và một record thực thi cũng không nhất thiết chứa nguyên văn chuỗi đã gõ.

Đường dẫn script hoặc đối số chưa chứng minh chính xác nội dung script ở thời điểm chạy. Với tác vụ nhạy cảm cần thêm provenance của phiên bản triển khai hoặc bằng chứng file được quản lý.

### Tác vụ từ xa

Một CLI quản trị cơ sở dữ liệu có thể thực hiện nhiều thao tác SQL sau khi đã khởi chạy. Lệnh gọi API cũng có thể gây thay đổi ở hệ thống khác.

Host audit cho thấy chương trình phía client, nhưng kết luận về thay đổi phía server cần log ứng dụng, audit cơ sở dữ liệu hoặc nhật ký API tương ứng.

### Tài khoản dịch vụ và tự động hóa

Cron, systemd hoặc công cụ triển khai có thể tạo tiến trình với login UID không thuộc dải người dùng, hoặc chưa thiết lập. Rule loại `auid=unset` cố ý không bao phủ toàn bộ nhóm này.

Một workload được người dùng khởi động thông qua service manager cũng có thể không giữ nguyên chuỗi tiến trình và login UID của phiên tương tác. Cần đối chiếu job ID, deployment ID, tài khoản workload và log điều khiển dịch vụ.

Đừng giả một service account thành người dùng cá nhân để thỏa điều kiện rule. Hãy định nghĩa identity và coverage riêng cho workload.

### Container và quyền ngoài UID root

Container dùng kernel của host và có thể có ánh xạ UID qua namespace. Một UID nhìn thấy trong container không phải lúc nào cũng tương đương UID ở host.

Việc cài `auditd` trong container không tự tạo miền audit kernel độc lập như một máy ảo. Cần thiết kế thu ở host và liên kết metadata container, pod hoặc workload theo thời điểm.

Linux capabilities và tài khoản ứng dụng đặc quyền cũng cần đánh giá riêng. Bộ lọc root là một lát cắt, không phải định nghĩa đầy đủ của mọi quyền nhạy cảm.

## 15. Bảo vệ log và dữ liệu nhạy cảm

Command audit dễ thu phải bí mật khi chương trình nhận credential trực tiếp qua đối số. Những dữ liệu đó có thể đi vào `EXECVE`, log của công cụ nâng quyền và bản ghi phiên.

Một thiết kế tốt giảm nguồn rò rỉ trước khi thêm bộ lọc:

- Dùng cơ chế nhận bí mật phù hợp của ứng dụng và vault, thay vì đặt token hoặc mật khẩu trực tiếp trên command line.
- Dùng credential ngắn hạn và giới hạn quyền để giảm hậu quả nếu dữ liệu bị lộ.
- Xem cả output, stdin, environment và file tạm trong đánh giá luồng bí mật; chuyển khỏi argv không có nghĩa tự động an toàn ở mọi nơi.
- Phân quyền riêng cho người đọc bằng chứng, người vận hành hệ thống PAM và người quản trị máy đích.
- Ghi lại việc tìm kiếm, mở, xuất hoặc xóa bằng chứng ở hệ thống lưu giữ.

Che dữ liệu ở giao diện không xóa bản gốc trong kho lưu trữ. Nếu giữ raw evidence và bản hiển thị đã che, cần quy định rõ ai được truy cập mỗi loại.

Khi xuất bằng chứng cho điều tra, có thể lưu bản raw được kiểm soát, metadata nguồn, thời gian lấy và hash của gói xuất. Hash giúp phát hiện thay đổi sau khi lấy mẫu; nó không tự chứng minh log ban đầu đầy đủ hoặc chưa bị sửa trước khi xuất.

Lưu giữ nên dựa trên nhu cầu điều tra, nghĩa vụ áp dụng và loại dữ liệu thực thu. Không chọn một số ngày chung rồi coi đó là đủ cho mọi hệ thống.

## 16. Vận hành khi log tăng mạnh hoặc đường gửi lỗi

Một thiết kế chỉ kiểm tra “dịch vụ audit đang chạy” có thể bỏ sót mất dữ liệu trên đường gửi. Cần quan sát ít nhất ba vị trí:

1. Kernel có tạo và chuyển được record cho userspace không?
2. Host có ghi và chuyển tiếp được không?
3. Collector có tiếp nhận, ghép sự kiện và lưu truy vấn được không?

Theo [tài liệu auditctl](https://github.com/linux-audit/audit-userspace/blob/master/docs/auditctl.8), đầu ra trạng thái có thông tin backlog và lost; chế độ khóa `-e 2` cũng có tác động đến khả năng thay đổi cấu hình. Các chỉ số phải được theo dõi theo thời gian, thay vì chụp một lần rồi coi là bảo đảm lâu dài.

Ở host, kiểm tra dung lượng, độ trễ ghi, xoay vòng và cấu hình phản ứng khi thiếu đĩa. Các tùy chọn thuộc `auditd.conf` cần được chọn theo mức chịu lỗi của dịch vụ; tham khảo [tài liệu auditd.conf](https://github.com/linux-audit/audit-userspace/blob/master/docs/auditd.conf.5).

Ở đường gửi, cần có:

- Kết nối được xác thực và mã hóa theo cơ chế của bộ chuyển tiếp.
- Bộ đệm đủ cho khoảng gián đoạn dự kiến và cảnh báo khi sắp đầy.
- Xác nhận tiếp nhận phù hợp, cơ chế gửi lại và xử lý trùng.
- Giám sát độ trễ từ event time đến ingest time.
- Một sự kiện thử định kỳ để xác nhận khả năng tìm kiếm đầu cuối.

Không đặt chính sách “mất log thì dừng mọi thứ” hoặc “cứ tiếp tục dù mất bao lâu” mà chưa đánh giá tác động. Với từng cấp tài nguyên, cần quyết định có cho mở phiên mới, tiếp tục phiên cũ hay kích hoạt đường khẩn cấp khi bằng chứng không còn được thu đầy đủ.

Đối với break-glass, vẫn phải ghi nhận người dùng, lý do, thời điểm, phạm vi và phần bằng chứng bị thiếu; sau đó đối soát và thu hồi hoặc luân chuyển credential theo quy trình. Tính khẩn cấp không làm khoảng trống audit trở thành không đáng quan tâm.

## 17. Ma trận nghiệm thu và xử lý lỗi

### 17.1. Các tình huống nên có trong lab

| Tình huống | Bằng chứng kỳ vọng | Sai lầm cần phát hiện |
| --- | --- | --- |
| Người dùng chạy lệnh root được phép | Event sudo và event thực thi liên kết được với actor | Chỉ nhìn thấy root, mất danh tính gốc |
| Yêu cầu sudo bị từ chối | Log quyết định từ chối | Đòi có event chương trình root dù không chạy |
| Chương trình khởi chạy rồi trả mã lỗi | Có bằng chứng thực thi, kết quả được phân biệt | Đổi `success=yes` thành thành công nghiệp vụ |
| Shell builtin | Coverage được mô tả đúng, có nguồn bổ sung nếu cần | Kỳ vọng một exec event cho mọi câu lệnh |
| Chạy bằng tài khoản ứng dụng không root | Được thu bởi phạm vi đã thiết kế hoặc ghi rõ ngoài phạm vi | Tuyên bố rule root bao phủ tất cả |
| Workload có auid unset | Có thiết kế workload riêng hoặc ngoại lệ có chủ sở hữu | Loại khỏi rule rồi quên hoàn toàn |
| Mất kết nối collector | Có cảnh báo, buffer và chính sách phiên xác định | Local có log nên cho rằng kho trung tâm đầy đủ |
| Argument dài hoặc có ký tự đặc biệt | Parser giữ đúng dữ liệu và ghép đủ record | Cắt chuỗi, tách field sai, mất đối số |
| Hai host có cùng serial hoặc UID | Không gộp nhầm actor hay sự kiện | Dùng serial hoặc UID làm khóa toàn cục |

Không cần thử bằng hành vi phá hoại. Các tình huống bị từ chối, mất collector hoặc thiếu đĩa nên được mô phỏng có kiểm soát trên lab theo kế hoạch khôi phục.

### 17.2. Không tìm thấy sự kiện thực thi

Kiểm tra lần lượt:

1. Thời gian truy vấn, múi giờ và nguồn dữ liệu có đúng không?
2. Lệnh thử có thực thi chương trình ngoài hay là builtin?
3. Lệnh có đi qua đường nâng quyền và đạt điều kiện `euid` của rule không?
4. Login UID có đúng dải và đã được thiết lập không?
5. ABI và syscall thực tế có được bao phủ không?
6. Rule runtime có tồn tại; có rule loại trừ hoặc thiết lập ngăn thu trước đó không?
7. Kernel, audit daemon, bộ chuyển tiếp và collector có báo mất record không?

Không giải quyết bằng cách nới toàn bộ điều kiện hoặc xóa các rule khác trước khi biết nguyên nhân.

### 17.3. Có event nhưng không quy được về người

Đối chiếu tài khoản dùng chung, PAM stack ở điểm vào, metadata của cổng truy cập, login UID và sự đồng bộ thời gian.

Nếu log lịch sử không đủ, kết quả điều tra phải ghi nhận mức độ không chắc chắn. Sửa cấu hình hiện tại không phục hồi được một ánh xạ danh tính đã mất trong quá khứ.

### 17.4. Dữ liệu quá nhiều

Đo nguồn sinh nhiều sự kiện trước khi thay đổi phạm vi. Có thể cần tách tương tác người dùng và workload, điều chỉnh rule chồng lấn hoặc xử lý truy vấn hiệu quả hơn.

Không bỏ một nhóm sự kiện chỉ vì nó có khối lượng lớn nếu đó chính là phần rủi ro đã cam kết thu. Mọi thu hẹp coverage cần ghi rõ tác động và người chịu trách nhiệm.

## 18. Tình huống thực hành tổng hợp

Đội vận hành cấp cho An quyền JIT vào `app-linux-01` để kiểm tra dịch vụ trong khoảng bảo trì. SOC phát hiện một chương trình ngoài danh sách tác vụ dự kiến được chạy với quyền root.

Bằng chứng hiện có gồm:

- Request PAM ghi actor của An, host, ticket và cửa sổ quyền.
- Log phiên có thời điểm mở kết nối và mã phiên riêng.
- Linux Audit ghi executable, login UID 1001, effective UID root và audit session ID.
- Log sudo ghi tài khoản yêu cầu và tài khoản đích.
- Collector nhận được raw event cùng các record bổ sung.
- Log dịch vụ ghi một thay đổi trạng thái sau đó.

Cách phân tích phù hợp là xác minh từng liên kết, đối chiếu lệnh với phạm vi phê duyệt, rồi kiểm tra tác động thực tế. Việc lệnh chạy trong cửa sổ JIT không tự làm nó hợp lệ; JIT giới hạn thời gian quyền, còn phạm vi công việc vẫn phải được kiểm soát.

Nếu một record cho thấy chương trình đã khởi chạy nhưng chưa có nguồn xác nhận kết quả, báo cáo nên nói “đã ghi nhận thực thi chương trình với quyền root”. Chỉ kết luận “đã thay đổi cấu hình thành công” khi có bằng chứng hỗ trợ cho thay đổi đó.

Một hồ sơ bàn giao lab đạt yêu cầu nên có phạm vi đã chọn, cấu hình nguồn, rule runtime, sự kiện thử raw, bản diễn giải, ánh xạ actor và phiên, kết quả tại collector, cùng những giới hạn còn lại. Hồ sơ này cho phép người khác tái kiểm tra bằng chứng thay vì chỉ tin vào ảnh chụp “audit enabled”.

## 19. Câu hỏi tự kiểm tra

1. Vì sao `auid=1001` và `euid=0` có giá trị hơn một dòng chỉ ghi “root chạy lệnh”?
2. Vì sao đặt `pam_loginuid` ở sai điểm chuyển quyền có thể làm hỏng truy vết?
3. Điều gì nằm ngoài phạm vi của rule có `euid=0` và `auid>=1000`?
4. Một chương trình trả mã 1 có thể vẫn có sự kiện thực thi `success=yes` không?
5. Vì sao một root shell không làm xuất hiện `execve` cho mọi builtin bên trong?
6. Phải bổ sung dữ liệu nào để liên kết event Linux với ticket PAM đáng tin cậy?
7. Nếu host vẫn có audit log nhưng collector không nhận trong 20 phút, bằng chứng nào đang thiếu?
8. Vì sao hash của gói log xuất ra không chứng minh toàn bộ lịch sử trên host là đầy đủ?

Khi trả lời, cần chỉ ra nguồn bằng chứng và giới hạn của từng kết luận. Năng lực quan trọng của command audit là biết chính xác điều gì đã được quan sát, điều gì mới chỉ được suy ra và điều gì vẫn chưa có dữ liệu để xác nhận.
