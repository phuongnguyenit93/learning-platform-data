# Chuẩn bị môi trường Linux cho bài thực hành

Các bài thực hành CRaC cần một môi trường Linux có thể checkpoint và restore tiến trình Java. Ngoài JDK có hỗ trợ CRaC, máy cần có kernel phù hợp, công cụ CRIU và quyền hệ thống cần thiết để lưu rồi khôi phục trạng thái tiến trình.

Phần chuẩn bị nên được thực hiện trên một máy Linux riêng hoặc máy ảo dùng cho học tập. Máy ảo giúp kiểm soát phiên bản hệ điều hành, kernel, JDK và quyền truy cập; đồng thời có thể tạo lại môi trường khi cấu hình thử nghiệm bị sai.

## 1. Hiểu các thành phần của môi trường

Một môi trường CRaC trên Linux có các thành phần chính:

| Thành phần | Vai trò |
|---|---|
| Linux kernel | Cung cấp các cơ chế cấp thấp để đóng băng, ghi nhận và khôi phục trạng thái tiến trình |
| CRIU | Công cụ checkpoint/restore tiến trình ở user space; CRaC runtime sử dụng nó để làm việc với trạng thái hệ điều hành |
| CRaC-enabled JDK | JVM có tích hợp CRaC, cung cấp tùy chọn và API để ứng dụng tham gia vòng đời checkpoint/restore |
| Ứng dụng Java | Chuẩn bị tài nguyên trước checkpoint và phục hồi tài nguyên sau restore khi cần |
| Thư mục checkpoint | Lưu các image và metadata được tạo trong quá trình checkpoint |

CRaC và CRIU có trách nhiệm khác nhau. CRaC cung cấp tích hợp ở mức JVM và API cho ứng dụng; CRIU thực hiện phần lớn công việc checkpoint/restore tiến trình trên Linux. Chỉ cài CRIU không làm cho một JDK thông thường tự có khả năng CRaC. Ngược lại, có JDK hỗ trợ CRaC nhưng thiếu CRIU hoặc thiếu quyền kernel cần thiết thì thao tác checkpoint vẫn có thể thất bại.

## 2. Chọn máy Linux phù hợp

### Môi trường khuyến nghị

Để bắt đầu, hãy sử dụng một bản phân phối Linux phổ biến có gói CRIU và có thể cài JDK CRaC tương ứng. Ubuntu LTS 64-bit là lựa chọn thuận tiện cho bài thực hành vì có trình quản lý gói APT và tài liệu cộng đồng phong phú.

Có thể dùng máy vật lý hoặc máy ảo. Với máy ảo, cần bảo đảm kernel bên trong máy ảo cung cấp các tính năng mà CRIU yêu cầu; cấu hình của hệ điều hành host không thay thế cho kernel guest đang chạy JVM.

Các môi trường khác cần được đánh giá riêng:

- Debian và Fedora có thể dùng nếu phiên bản hệ điều hành, kernel, CRIU và JDK nằm trong tổ hợp được hỗ trợ.
- Rocky Linux, AlmaLinux và các bản phân phối tương thích RHEL phụ thuộc vào phiên bản repository và gói CRIU sẵn có.
- WSL1 không cung cấp một Linux kernel độc lập nên không phù hợp cho bài thực hành CRIU. WSL2 có kernel Linux nhưng khả năng sử dụng còn phụ thuộc kernel, quyền và các tính năng CRIU; phải kiểm tra trực tiếp bằng lệnh criu check.
- Container dùng chung kernel với host và có thể bị giới hạn bởi capability, namespace, seccomp hoặc chính sách bảo mật. Nên hoàn thành bài thực hành trên Linux host hoặc VM trước khi chuyển sang container.

Không chọn hệ điều hành chỉ dựa vào tên bản phân phối. Hãy kiểm tra cả kiến trúc CPU, kernel đang chạy và ma trận hỗ trợ của nhà cung cấp JDK CRaC. Một số bản JDK chỉ cung cấp build CRaC cho một số kiến trúc nhất định; không mặc định mọi build x86-64 đều có bản tương đương cho ARM64.

### Thu thập thông tin hệ thống

Mở terminal trên máy Linux và chạy:

~~~bash
cat /etc/os-release
uname -r
uname -m
id
~~~

Các lệnh cho biết:

- /etc/os-release: tên và phiên bản bản phân phối.
- uname -r: phiên bản kernel đang chạy, không phải phiên bản kernel được cài nhưng chưa khởi động.
- uname -m: kiến trúc máy, thường gặp x86_64 hoặc aarch64.
- id: user và các group hiện tại.

Ghi lại các thông tin này để đối chiếu khi cài JDK và xử lý lỗi. Nếu vừa nâng cấp kernel, hãy khởi động lại máy trước khi kiểm tra để chắc chắn JVM chạy trên kernel mới.

## 3. Cài và kiểm tra CRIU

CRIU (Checkpoint/Restore In Userspace) là thành phần thực hiện việc ghi và phục hồi trạng thái tiến trình. CRaC runtime thường cần gọi CRIU trong quá trình checkpoint/restore.

### Cài trên Ubuntu hoặc Debian

Trên hệ thống dùng APT, cập nhật package index rồi cài CRIU:

~~~bash
sudo apt update
sudo apt install -y criu
~~~

Kiểm tra binary và phiên bản:

~~~bash
command -v criu
criu --version
~~~

Nếu command -v criu không trả về đường dẫn, shell chưa tìm thấy CRIU. Kiểm tra kết quả cài package, tên gói của bản phân phối và biến PATH.

### Cài trên Fedora

Trên Fedora, có thể cài bằng DNF:

~~~bash
sudo dnf install -y criu
~~~

Sau khi cài, kiểm tra bằng command -v criu và criu --version như trên. Với các bản phân phối thuộc họ RHEL, hãy dùng repository được quản trị viên hoặc nhà cung cấp hệ điều hành hỗ trợ; vị trí và phiên bản package có thể khác nhau.

### Kiểm tra khả năng của kernel

Chạy kiểm tra CRIU:

~~~bash
sudo criu check
sudo criu check --all
~~~

criu check kiểm tra những điều kiện cơ bản để CRIU hoạt động. criu check --all kiểm tra thêm các tính năng tùy chọn mà CRIU có thể sử dụng. Đọc toàn bộ kết quả thay vì chỉ nhìn mã thoát của lệnh.

Nếu kiểm tra thất bại, nguyên nhân có thể thuộc một trong các nhóm sau:

- Kernel thiếu tính năng cần thiết hoặc đang chạy kernel không phù hợp.
- CRIU quá cũ so với kernel hoặc thiếu hỗ trợ cho một tính năng.
- User hiện tại không có quyền cần thiết.
- Container, namespace hoặc chính sách bảo mật đang giới hạn thao tác.
- Một tính năng tùy chọn không được hỗ trợ dù chức năng checkpoint cơ bản vẫn có thể dùng được.

Không phải mọi cảnh báo từ criu check --all đều có nghĩa mọi bài thực hành đều không thể chạy. Cần phân biệt tính năng bắt buộc với tính năng tùy chọn, rồi đối chiếu yêu cầu của JDK và nội dung bài thực hành.

## 4. Kiểm tra quyền checkpoint/restore

Checkpoint và restore cần quyền thao tác trên tiến trình cùng một số tài nguyên kernel. Quyền cụ thể phụ thuộc phiên bản kernel, CRIU, cách chạy JVM và cấu hình bảo mật.

Trong một máy ảo dùng riêng cho bài thực hành, cách đơn giản nhất là bắt đầu với cấu hình quyền theo tài liệu của bản CRaC JDK và CRIU đang sử dụng. Một số thiết lập cần quyền quản trị; một số môi trường mới hơn có thể cấu hình capability phù hợp để chạy với user thường.

Lưu ý các điểm sau:

- Chạy sudo criu check chỉ xác nhận CRIU có thể thực hiện kiểm tra trong ngữ cảnh quyền của lệnh đó. Nó không tự chứng minh JVM chạy bằng user thường cũng có đủ quyền.
- Tiến trình Java và lệnh jcmd điều khiển tiến trình thường cần chạy dưới cùng một user. Tránh khởi chạy ứng dụng bằng một user rồi điều khiển bằng user khác.
- Nếu dùng user thường, hãy làm theo hướng dẫn least-privilege của CRIU, kernel và nhà cung cấp JDK. Capability như CAP_CHECKPOINT_RESTORE có thể liên quan trên kernel hỗ trợ nó; các kernel cũ hoặc thao tác khác có thể cần quyền bổ sung.
- Trong container, quyền của container bị giới hạn độc lập với quyền root bên trong container. Có UID 0 trong container không đồng nghĩa có đầy đủ quyền trên host.
- Không tùy tiện đặt setuid hoặc cấp toàn bộ capability cho binary CRIU. Những thay đổi đó làm tăng quyền của một chương trình hệ thống và cần được hiểu rõ trước khi áp dụng.

Nếu criu check báo lỗi liên quan đến ptrace hoặc Yama, kiểm tra chính sách hiện tại:

~~~bash
sysctl kernel.yama.ptrace_scope
~~~

Chỉ điều chỉnh chính sách khi thông báo lỗi và tài liệu môi trường chỉ ra đó là nguyên nhân. Không tắt cơ chế bảo vệ ptrace trên máy dùng chung chỉ để làm cho bài thực hành chạy được. Nếu cần thay đổi, ưu tiên cấu hình tạm thời trong VM dùng riêng và khôi phục lại sau bài thực hành.

SELinux và AppArmor cũng có thể giới hạn truy cập. Khi gặp lỗi permission, hãy kiểm tra log audit hoặc log kernel để xác định đúng hành động bị chặn. Không tắt toàn bộ cơ chế bảo vệ như một bước khắc phục mặc định.

## 5. Cài CRaC-enabled JDK

Không phải mọi bản phân phối OpenJDK đều có CRaC. Cần tải một bản JDK được nhà cung cấp công bố có hỗ trợ CRaC, đúng với:

- Phiên bản Java mà module và bài thực hành yêu cầu.
- Bản phân phối Linux đang dùng.
- Kiến trúc CPU của máy.
- Phiên bản CRaC và CRIU được nhà cung cấp hỗ trợ.

Làm theo hướng dẫn cài đặt của nhà cung cấp JDK. Có thể cài từ package repository hoặc giải nén archive vào một thư mục riêng. Không ghi đè JDK hệ thống nếu máy còn phục vụ ứng dụng khác.

Sau khi cài, thiết lập JAVA_HOME trỏ đến thư mục JDK CRaC. Ví dụ, nếu JDK được giải nén vào /opt/jdks/crac-jdk:

~~~bash
export JAVA_HOME=/opt/jdks/crac-jdk
export PATH="$JAVA_HOME/bin:$PATH"
~~~

Đây là ví dụ đường dẫn; thay bằng thư mục thực tế trên máy. Có thể thêm hai dòng vào file cấu hình shell của user để giữ thiết lập sau khi mở terminal mới.

Kiểm tra JDK đang được sử dụng:

~~~bash
echo "$JAVA_HOME"
command -v java
java -version
command -v jcmd
~~~

Đảm bảo java và jcmd đến từ cùng JDK. Nếu java -version hiển thị một JDK khác, kiểm tra thứ tự PATH, file cấu hình shell và liên kết symbolic link của Java.

### Kiểm tra tùy chọn CRaC của JVM

Một cách kiểm tra nhanh là yêu cầu JVM nhận diện tùy chọn checkpoint:

~~~bash
java -XX:CRaCCheckpointTo=/tmp/crac-option-check -version
~~~

Lệnh này chỉ kiểm tra JVM có nhận tùy chọn CRaCCheckpointTo hay không; vì chương trình chỉ in phiên bản rồi kết thúc nên nó **không thực hiện checkpoint thật**. Nếu JVM báo Unrecognized VM option, nhiều khả năng bạn đang dùng JDK không có CRaC hoặc đã chọn nhầm Java trên PATH.

Không nên suy ra khả năng restore chỉ từ việc JVM chấp nhận một tùy chọn. Cần thực hiện một bài smoke test checkpoint/restore hoàn chỉnh bằng JDK, CRIU và quyền thực tế của môi trường.

## 6. Chuẩn bị thư mục checkpoint

Checkpoint có thể tạo ra nhiều image và file metadata. Hãy chọn một thư mục local mà user chạy JVM có quyền đọc, ghi và tạo file. Ví dụ:

~~~bash
mkdir -p "$HOME/crac/checkpoints"
chmod 700 "$HOME/crac/checkpoints"
df -h "$HOME"
~~~

Thư mục nằm trong home giúp giới hạn quyền truy cập cho user hiện tại. Kiểm tra dung lượng trống trước khi chạy bài thực hành; kích thước checkpoint phụ thuộc vào heap, trạng thái tiến trình và tài nguyên được lưu.

Khi chọn vị trí lưu checkpoint, lưu ý:

- Ưu tiên filesystem local trên VM hoặc máy Linux.
- Không dùng thư mục tạm có thể bị tự động dọn khi reboot nếu muốn giữ checkpoint qua lần khởi động lại.
- Tránh network filesystem hoặc thư mục đồng bộ đám mây trong lần thực hành đầu tiên; chỉ dùng khi đã xác minh tương thích.
- Bảo đảm user restore có quyền đọc checkpoint và các file cần thiết.
- Giữ đường dẫn mount và cấu trúc thư mục phù hợp giữa lúc checkpoint và restore.
- Không chỉnh sửa hoặc xóa thủ công các file bên trong checkpoint.

Checkpoint có thể chứa dữ liệu nhạy cảm trong bộ nhớ của ứng dụng, chẳng hạn token, thông tin người dùng hoặc dữ liệu nghiệp vụ. Hãy bảo vệ thư mục checkpoint như dữ liệu nhạy cảm: giới hạn quyền truy cập, không đưa vào Git và không chia sẻ lên nơi công khai.

## 7. Kiểm tra các giới hạn của môi trường

Trước khi chạy ứng dụng, kiểm tra tài nguyên và môi trường shell:

~~~bash
free -h
df -h
ulimit -n
id
~~~

Những lệnh này giúp phát hiện sớm các vấn đề thường gặp:

- RAM quá ít so với heap và dữ liệu mà ứng dụng cần giữ.
- Dung lượng filesystem không đủ cho checkpoint.
- Giới hạn số file descriptor thấp hơn nhu cầu của ứng dụng.
- User đang chạy không phải user dự kiến hoặc thiếu group/quyền cần thiết.

Nếu dùng VM, nên cấp RAM và disk đủ cho ứng dụng mẫu cùng checkpoint. Không cần cấp tài nguyên quá lớn cho bài đầu tiên; hãy bắt đầu với ứng dụng nhỏ rồi tăng dần khi cần.

Kiểm tra kết nối mạng nếu bài thực hành sử dụng database, HTTP service hoặc message broker. Tên host, DNS, route và firewall cần cho phép ứng dụng kết nối lại sau restore. Một kết nối TCP đã mở trước checkpoint có thể không còn hợp lệ sau restore; môi trường phải cho phép ứng dụng tạo kết nối mới.

## 8. Lưu ý khi chạy trong container

Container không có kernel riêng. CRIU chạy dựa trên kernel của host, còn container chỉ nhìn thấy một phần tài nguyên và quyền mà host cấp.

Một container có thể cài criu và chạy với user root nhưng vẫn không checkpoint được do:

- Thiếu capability được yêu cầu.
- Seccomp chặn syscall cần thiết.
- Namespace không cho phép thao tác trên tiến trình hoặc tài nguyên liên quan.
- Mount /proc hoặc các filesystem cần thiết không phù hợp.
- SELinux/AppArmor hoặc chính sách runtime container giới hạn quyền.

Vì vậy, không nên sao chép nguyên lệnh cài đặt CRIU trên VM rồi kỳ vọng container hoạt động giống hệt. Nếu bài học được chạy trong container, cần có hướng dẫn riêng cho image, runtime, host kernel, capability và chính sách bảo mật. Hãy dùng cấu hình tối thiểu theo tài liệu chính thức của môi trường; không bật privileged hoặc vô hiệu hóa seccomp một cách tùy tiện.

## 9. Smoke test trước khi bắt đầu bài thực hành

Sau khi hoàn thành các bước trên, chạy lại nhóm lệnh kiểm tra:

~~~bash
cat /etc/os-release
uname -r
uname -m
criu --version
sudo criu check
java -version
command -v java
command -v jcmd
echo "$JAVA_HOME"
~~~

Đối chiếu kết quả với yêu cầu của JDK CRaC đã chọn. Nếu các kiểm tra cơ bản thành công, bước tiếp theo là chạy một ứng dụng Java nhỏ bằng JDK này, tạo checkpoint và restore trong cùng môi trường.

Với ứng dụng mẫu, quy trình tổng quát có dạng:

1. Khởi chạy ứng dụng bằng CRaC-enabled JDK và chỉ định thư mục checkpoint qua tùy chọn -XX:CRaCCheckpointTo.
2. Đợi ứng dụng khởi tạo xong và sẵn sàng checkpoint.
3. Dùng jcmd từ cùng JDK và cùng user để yêu cầu JVM checkpoint, theo lệnh được JDK CRaC cung cấp.
4. Xác nhận checkpoint đã được tạo và tiến trình đã đi vào trạng thái mà runtime mong đợi.
5. Khởi chạy lại JVM bằng tùy chọn restore -XX:CRaCRestoreFrom trỏ tới checkpoint, theo tài liệu của bản JDK đang dùng.
6. Xác nhận ứng dụng tiếp tục hoạt động và các tài nguyên bên ngoài được tạo lại hoặc kiểm tra hợp lệ.

Tên tùy chọn và lệnh điều khiển cần khớp với bản phân phối JDK CRaC. Nếu bài thực hành cung cấp lệnh cụ thể, dùng đúng lệnh đó thay vì tự suy đoán từ một bản JDK khác.

Một smoke test thành công nên xác nhận được cả ba việc: JVM thực sự tạo checkpoint, JVM khôi phục được từ checkpoint đó, và ứng dụng tiếp tục xử lý sau restore. Chỉ thấy thư mục checkpoint xuất hiện hoặc chỉ thấy java -version chạy thành công chưa đủ để kết luận toàn bộ môi trường đã sẵn sàng.

## 10. Xử lý lỗi chuẩn bị thường gặp

| Triệu chứng | Hướng kiểm tra |
|---|---|
| criu: command not found | Kiểm tra package đã cài chưa và PATH có chứa thư mục binary không |
| criu check báo thiếu quyền | Chạy kiểm tra trong đúng user/capability context mà JVM sẽ dùng; xem hướng dẫn quyền của CRIU và JDK |
| CRIU báo kernel không hỗ trợ | Kiểm tra uname -r, kernel đang boot và các yêu cầu kernel của phiên bản CRIU |
| criu check --all báo một tính năng tùy chọn không có | Xác định tính năng đó có bắt buộc với bài thực hành hoặc loại tài nguyên đang checkpoint không |
| JVM báo Unrecognized VM option với CRaCCheckpointTo | Xác nhận JAVA_HOME, PATH và java -version; cài đúng JDK có CRaC |
| java và jcmd đến từ hai thư mục khác nhau | Đưa $JAVA_HOME/bin lên đầu PATH và mở lại terminal |
| Checkpoint lỗi Permission denied | Kiểm tra quyền user, thư mục checkpoint, capability, ptrace và chính sách SELinux/AppArmor |
| Restore không kết nối được database hoặc broker | Kiểm tra callback phục hồi tài nguyên, DNS, firewall, credential và trạng thái dịch vụ từ xa |
| Không đủ dung lượng | Kiểm tra df -h, dọn dữ liệu bài thực hành cũ theo đúng quy trình và chọn filesystem local đủ chỗ |

Khi gặp lỗi, hãy giữ lại toàn bộ thông báo từ JVM, CRIU và kernel. Một dòng Permission denied chưa đủ để xác định phải thay đổi quyền nào; cần biết tiến trình nào bị từ chối, trên file hoặc syscall nào và trong ngữ cảnh user/capability nào.

## 11. Checklist hoàn tất môi trường

Trước khi chuyển sang bài thực hành, xác nhận các mục sau:

- [ ] Đang chạy trên Linux kernel phù hợp; đã ghi nhận phiên bản hệ điều hành, kernel và kiến trúc CPU.
- [ ] CRIU đã cài và lệnh criu --version hoạt động.
- [ ] criu check đã chạy trong ngữ cảnh quyền phù hợp; các lỗi còn lại đã được hiểu rõ.
- [ ] Đã cài đúng CRaC-enabled JDK cho hệ điều hành và kiến trúc đang dùng.
- [ ] JAVA_HOME, java và jcmd cùng trỏ đến JDK dự kiến.
- [ ] JVM nhận diện tùy chọn CRaC của bản JDK.
- [ ] User chạy ứng dụng có quyền cần thiết đối với CRIU và thư mục checkpoint.
- [ ] Thư mục checkpoint nằm trên filesystem phù hợp, có đủ dung lượng và được bảo vệ quyền truy cập.
- [ ] Đã xác định giới hạn của VM, container hoặc chính sách bảo mật nếu có.
- [ ] Smoke test checkpoint/restore hoàn chỉnh đã thành công trước khi làm bài chính.

Khi các điều kiện trên được đáp ứng, môi trường Linux đã sẵn sàng để thực hành các bước checkpoint và restore. Trong quá trình học, hãy giữ ổn định JDK, kernel và cấu hình quyền để có thể phân biệt lỗi do ứng dụng với lỗi do môi trường.
