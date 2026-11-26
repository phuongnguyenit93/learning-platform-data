Shell đảm nhiệm vai trò nào giữa người dùng và hệ điều hành?
A. Lập lịch CPU và phân chia thời gian cho tiến trình.
B. Quản lý page table và cấp phát frame bộ nhớ.
C. Phân tích cú pháp và khởi chạy lệnh.
D. Điều khiển trực tiếp thiết bị mà không qua kernel.
Đáp án đúng: C

Vì sao cd thường là lệnh tích hợp của shell?
A. Nó thay đổi biến PATH cho mọi tiến trình hệ thống.
B. Nó phải đổi thư mục làm việc của chính shell.
C. Nó yêu cầu kernel khởi động lại terminal hiện tại.
D. Nó cần chạy trong tiến trình riêng để đổi thư mục.
Đáp án đúng: B

Đường dẫn tương đối được diễn giải dựa trên vị trí nào?
A. Thư mục gốc của hệ thống tệp đang gắn.
B. Thư mục home của tài khoản đang đăng nhập.
C. Thư mục chứa tệp thực thi của shell.
D. Thư mục làm việc hiện tại của tiến trình.
Đáp án đúng: D

Khi truyền đường dẫn có dấu cách làm một đối số, cách nào phù hợp?
A. Đặt toàn bộ đường dẫn trong một cặp dấu nháy.
B. Tách đường dẫn thành nhiều đối số theo từng từ.
C. Thay mọi dấu cách bằng ký tự wildcard của shell.
D. Thêm dấu phân cách thư mục vào cuối mỗi thành phần.
Đáp án đúng: A

Trong Bash, ký tự * không được đặt trong dấu nháy thường có ý nghĩa gì?
A. Đại diện cho một đối số vị trí của script.
B. Thực hiện phép nhân số học trên giá trị kế tiếp.
C. Khớp với mọi ký tự trong một biểu thức chính quy.
D. Khớp với chuỗi tên tệp theo mẫu glob.
Đáp án đúng: D

Điểm khác biệt cơ bản giữa glob và regular expression là gì?
A. Glob chọn tên đường dẫn; regex mô tả mẫu văn bản.
B. Hai cú pháp tương đương và dùng thay thế trực tiếp.
C. Glob chỉ tìm nội dung file; regex chỉ tìm tên thư mục.
D. Glob luôn hỗ trợ nhóm bắt; regex không hỗ trợ nhóm.
Đáp án đúng: A

Trong Bash, single quote và double quote khác nhau thế nào?
A. Cả hai đều mở rộng biến và command substitution như nhau.
B. Single quote literal; double quote mở rộng biến.
C. Single quote mở rộng biến; double quote giữ nguyên mọi ký tự.
D. Double quote tách từ; single quote chỉ ngăn wildcard.
Đáp án đúng: B

Điều gì có thể xảy ra khi mở rộng biến không được quote trong Bash?
A. Giá trị có thể bị tách từ và mở rộng pathname.
B. Shell tự động mã hóa giá trị trước khi truyền đi.
C. Biến bị xóa sau khi lệnh bên ngoài kết thúc.
D. Giá trị luôn được giữ thành một đối số duy nhất.
Đáp án đúng: A

Trong Bash, cách nào truyền từng đối số vị trí mà vẫn giữ nguyên ranh giới của chúng?
A. Dùng $# để shell khôi phục nội dung từng đối số.
B. Dùng "$@" trong ngữ cảnh tạo danh sách đối số.
C. Dùng "$*" để luôn tạo một đối số cho mỗi phần tử.
D. Dùng $@ không quote để shell tự bảo toàn ranh giới.
Đáp án đúng: B

Command substitution trong Bash thường được dùng để làm gì?
A. Lấy exit code của lệnh con làm nội dung văn bản.
B. Chuyển stderr của shell thành biến môi trường.
C. Chạy lệnh trong tiến trình cha mà không tạo subshell.
D. Lấy stdout của lệnh con làm một phần giá trị.
Đáp án đúng: D

Trong Bash, export VAR=value có tác dụng nào?
A. Truyền biến vào môi trường tiến trình con.
B. Chỉ đặt biến cục bộ trong hàm hiện tại.
C. Đưa biến vào PATH để shell tìm lệnh theo tên.
D. Lưu biến vào profile để mọi lần đăng nhập đều dùng.
Đáp án đúng: A

Trong PowerShell, cú pháp nào truy cập biến môi trường của tiến trình hiện tại?
A. Dùng $global:NAME để truy cập trực tiếp environment.
B. Dùng $NAME vì mọi biến PowerShell đều là environment.
C. Dùng $env:NAME để đọc hoặc gán biến môi trường.
D. Dùng %NAME% trong mọi biểu thức PowerShell.
Đáp án đúng: C

Khi tiến trình con thay đổi biến môi trường của nó, điều gì xảy ra với tiến trình cha?
A. Thay đổi đó không tự truyền ngược về tiến trình cha.
B. Tiến trình cha nhận thay đổi ngay khi tiến trình con thoát.
C. Hệ điều hành đồng bộ biến môi trường giữa mọi tiến trình.
D. Chỉ biến PATH được truyền ngược về tiến trình cha.
Đáp án đúng: A

Sau khi không khớp alias, function hoặc builtin, shell tìm executable bên ngoài theo cách nào?
A. Tìm trong mọi thư mục gắn trên hệ thống tệp.
B. Duyệt các thư mục trong PATH theo thứ tự.
C. Tra cơ sở dữ liệu tiến trình đang chạy theo tên.
D. Tìm trong thư mục hiện tại trước rồi mới tra PATH.
Đáp án đúng: B

Sau khi dùng setx trên Windows, vì sao giá trị mới có thể chưa xuất hiện trong PowerShell hiện tại?
A. setx chỉ cập nhật biến trong Command Prompt hiện tại.
B. setx chỉ thay đổi PATH khi PowerShell được chạy với quyền admin.
C. setx ghi giá trị cho tiến trình mới, không sửa shell hiện tại.
D. setx ghi biến vào profile shell nhưng chỉ áp dụng sau reboot.
Đáp án đúng: C

Ba file descriptor chuẩn của một tiến trình Unix thường là gì?
A. 1 cho stdin, 2 cho stdout và 3 cho stderr.
B. 0 cho stdout, 1 cho stderr và 2 cho stdin.
C. 0 cho stdin, 2 cho stdout và 1 cho stderr.
D. stdin là 0, stdout là 1 và stderr là 2.
Đáp án đúng: D

Trong Bash, khác biệt giữa > và >> khi chuyển hướng stdout là gì?
A. Một lệnh tạo tệp tạm; lệnh kia xóa tệp cũ.
B. Một lệnh ghi vào pipe; lệnh kia ghi vào terminal.
C. Một lệnh ghi đè; lệnh kia nối thêm vào tệp.
D. Một lệnh chuyển stderr; lệnh kia chuyển stdin.
Đáp án đúng: C

Trong Bash, `command >out 2>&1` có tác dụng nào?
A. Chuyển stdout vào stderr rồi bỏ toàn bộ output.
B. Ghi stdout vào out; stderr dùng cùng đích.
C. Ghi stderr vào out và giữ stdout trên terminal.
D. Ghi stdout và stderr vào hai tệp riêng biệt.
Đáp án đúng: B

Một pipeline Unix thông thường truyền dữ liệu nào từ lệnh trước sang lệnh sau?
A. stdout của lệnh trước trở thành stdin của lệnh sau.
B. stderr của lệnh trước trở thành stdin của lệnh sau.
C. Cả stdout và stderr luôn được gộp tự động vào stdin.
D. Exit code của lệnh trước trở thành đối số lệnh sau.
Đáp án đúng: A

Trong Bash, set -o pipefail thay đổi cách xác định exit status của pipeline ra sao?
A. Pipeline bỏ qua lỗi và luôn trả về mã thành công.
B. Pipeline dừng mọi lệnh ngay khi có lệnh trả mã khác 0.
C. Trả status của lệnh lỗi bên phải nhất, nếu có.
D. Pipeline luôn trả về exit status của lệnh đầu tiên.
Đáp án đúng: C

Quy ước exit status 0 của một lệnh thường biểu thị điều gì?
A. Lệnh đã khởi chạy tiến trình nền thành công.
B. Lệnh hoàn tất thành công theo quy ước của nó.
C. Lệnh đã chạy với quyền root hoặc administrator.
D. Lệnh không tạo bất kỳ output nào trên stdout.
Đáp án đúng: B

Trong Bash, biểu thức `A && B` thực thi B khi nào?
A. Khi A trả về exit status bằng 0.
B. Khi A trả về exit status khác 0.
C. Bất kể A thành công hay thất bại.
D. Chỉ khi A và B cùng là shell builtin.
Đáp án đúng: A

Here-document với delimiter được quote trong Bash có đặc điểm nào?
A. Nội dung được diễn giải như một biểu thức regular expression.
B. Nội dung không thực hiện parameter hoặc command expansion.
C. Nội dung tự động được ghi vào một tệp tạm trên đĩa.
D. Nội dung được mở rộng biến trước khi truyền cho lệnh.
Đáp án đúng: B

Trong PowerShell, single-quoted string và double-quoted string khác nhau thế nào?
A. Double quote chạy lệnh; single quote chỉ chứa đường dẫn.
B. Cả hai đều mở rộng biến và subexpression giống nhau.
C. Single quote literal; double quote mở rộng biến.
D. Single quote mở rộng biến; double quote giữ nguyên nội dung.
Đáp án đúng: C

Pipeline của PowerShell khác pipeline Bash ở đặc điểm nào?
A. PowerShell truyền object; Bash chủ yếu truyền luồng byte.
B. PowerShell chỉ truyền byte; Bash truyền object có kiểu.
C. Cả hai đều truyền chuỗi văn bản và không giữ kiểu dữ liệu.
D. Bash truyền object; PowerShell chỉ truyền exit status.
Đáp án đúng: A

Trong PowerShell, `$?` và `$LASTEXITCODE` thường biểu thị điều gì?
A. $? giữ mã native process; LASTEXITCODE báo mọi lỗi cmdlet.
B. $? là mã của pipeline; LASTEXITCODE là mã của shell cha.
C. $? báo thành công; LASTEXITCODE giữ mã native.
D. Cả hai đều giữ nguyên exit code của tiến trình native gần nhất.
Đáp án đúng: C

Trong PowerShell, call operator & thường được dùng khi nào?
A. Chuyển một chuỗi thành biến môi trường của tiến trình.
B. Nối hai pipeline thành một luồng object duy nhất.
C. Chạy lệnh trong một tiến trình nền không chờ kết quả.
D. Gọi lệnh hoặc script từ đường dẫn đã cho.
Đáp án đúng: D

Shebang ở đầu script trên Unix thường dùng để làm gì?
A. Khai báo thư mục làm việc hiện tại của script.
B. Chỉ định interpreter dùng để thực thi script.
C. Đặt biến môi trường PATH cho tiến trình cha.
D. Bật quyền thực thi cho tệp script trên filesystem.
Đáp án đúng: B

Vì sao script Unix có thể chạy bằng `bash script.sh` dù chưa có execute bit?
A. Kernel bỏ qua mọi quyền filesystem khi gặp đuôi .sh.
B. Lệnh bash luôn chạy script bằng quyền root.
C. Bash tự động cấp execute bit trước khi đọc tệp.
D. Shell đọc và diễn giải tệp script được chỉ định.
Đáp án đúng: D

PowerShell execution policy nên được hiểu như thế nào?
A. Cơ chế phân quyền filesystem cho từng câu lệnh.
B. Cơ chế sandbox cô lập script khỏi hệ thống tệp và mạng.
C. Chính sách kiểm soát việc nạp script, không phải sandbox.
D. Cơ chế mã hóa nội dung script trước khi chạy.
Đáp án đúng: C

Vì sao PATH có thể khác giữa shell đăng nhập và shell không đăng nhập?
A. Mỗi shell tự tạo một PATH ngẫu nhiên khi khởi động.
B. PATH chỉ được kế thừa từ tiến trình kernel.
C. Shell không đăng nhập luôn xóa mọi thư mục PATH.
D. Chúng có thể nạp các tệp khởi động khác nhau.
Đáp án đúng: D

Trong Bash, cách chạy lệnh ở nền và xem các job của shell là gì?
A. Dùng nohup để khởi chạy và dùng fg để liệt kê mọi job.
B. Dùng disown để khởi chạy và dùng wait để xem job.
C. Thêm & khi khởi chạy và dùng jobs để liệt kê job.
D. Dùng ; khi khởi chạy và dùng ps để liệt kê job shell.
Đáp án đúng: C

SIGTERM và SIGKILL khác nhau chủ yếu ở điểm nào?
A. SIGTERM dừng máy; SIGKILL chỉ dừng terminal hiện tại.
B. SIGTERM luôn kết thúc tức thì; SIGKILL cho phép cleanup.
C. SIGTERM chỉ gửi cho thread; SIGKILL chỉ gửi cho process.
D. SIGTERM có thể xử lý; SIGKILL thì không thể bắt.
Đáp án đúng: D

Trong Bash, thay đổi thư mục bên trong `( ... )` thường có ảnh hưởng nào?
A. Subshell đổi thư mục riêng, không đổi shell cha.
B. Thư mục làm việc của shell cha cũng đổi theo.
C. Thư mục chỉ đổi với các lệnh external tiếp theo.
D. Thư mục được ghi vào PATH và tồn tại sau khi thoát.
Đáp án đúng: A

trap trong shell script thường được dùng để làm gì?
A. Chuyển hướng stdout và stderr của toàn hệ thống.
B. Đặt giới hạn CPU và RAM cho mọi tiến trình con.
C. Định nghĩa alias tồn tại trong mọi shell đăng nhập.
D. trap đăng ký xử lý signal hoặc sự kiện thoát.
Đáp án đúng: D

Trong Bash, vì sao vòng lặp đọc từng dòng thường dùng `IFS= read -r`?
A. Bỏ qua dòng trống và dừng khi gặp ký tự backslash.
B. Giữ khoảng trắng và coi backslash là ký tự thường.
C. Tự động tách mỗi dòng thành các trường theo dấu phẩy.
D. Mở rộng biến trong dòng trước khi gán vào biến đích.
Đáp án đúng: B

Khi truyền tên tệp có thể bắt đầu bằng dấu gạch ngang cho tiện ích hỗ trợ `--`, cách nào an toàn hơn?
A. Bỏ quote để shell tự phân biệt tên tệp với option.
B. Thêm dấu gạch chéo vào đầu mọi tên tệp tương đối.
C. Chuyển tên tệp thành biến môi trường trước khi gọi lệnh.
D. Quote tên tệp và dùng -- để kết thúc phần tùy chọn.
Đáp án đúng: D
