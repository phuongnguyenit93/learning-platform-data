Một script Bash chạy trong thư mục dự án có khoảng trắng ở tên nhưng biến PROJECT_DIR không được quote khi truyền cho cd; shell tách đường dẫn thành nhiều đối số và script chuyển nhầm thư mục hoặc dừng giữa chừng.
Một lệnh PowerShell dùng đường dẫn chứa dấu ngoặc vuông trong tham số -Path; wildcard expansion coi phần tên thư mục là pattern và thao tác nhắm tới nhiều mục hơn dự kiến.
Script Bash dùng dấu nháy đơn quanh biến HOME nên chuyển nguyên văn chuỗi $HOME thay vì thư mục người dùng; file đầu ra được tạo sai vị trí mà không báo lỗi.
Script PowerShell dùng dấu nháy đơn cho chuỗi cần nội suy $env:TEMP; chương trình nhận literal '$env:TEMP' và không tìm thấy thư mục tạm.
Một lệnh Bash chứa dấu nháy kép nhưng tên file có ký tự $ và backtick; shell nội suy command substitution ngoài ý muốn và lệnh xử lý nhầm tên file.
Script PowerShell cần truyền ký tự backtick cho chương trình native nhưng backtick bị PowerShell dùng làm escape; đối số tới executable khác với chuỗi người viết dự định.
Một script Bash nhận danh sách file qua biến rồi dùng for f in $FILES; tên file có dấu cách hoặc newline bị tách thành nhiều phần do word splitting và glob expansion.
Script PowerShell dùng chuỗi đường dẫn có dấu nháy kép lồng nhau để gọi executable native; cách ghép chuỗi làm đối số bị tách sai và tên file chứa dấu cách không còn nguyên vẹn.
Script PowerShell xây lệnh dưới dạng chuỗi rồi gọi Invoke-Expression; tên file do người dùng nhập chứa dấu chấm phẩy và thực thi thêm biểu thức ngoài ý muốn.
Một script dùng relative path và được chạy từ thư mục Downloads thay vì thư mục script; các file cấu hình được tìm tương đối theo current working directory nên script không tìm thấy tài nguyên.
Một lệnh Bash chạy trong thư mục có hàng nghìn file và glob *.log không khớp file nào; tùy cấu hình shell, pattern được truyền nguyên văn cho chương trình và tạo lỗi khó hiểu.
Script PowerShell dùng Get-ChildItem -Path *.log trong khi tên file có dấu ngoặc vuông; wildcard path coi tên file là pattern, còn -LiteralPath mới biểu diễn đúng tên thực.
Script PowerShell chạy trên Windows thành công nhưng khi chuyển sang PowerShell trên Linux, đường dẫn và tên biến môi trường có phân biệt hoa thường; cấu hình tham chiếu PATH thay vì Path không được phân giải như kỳ vọng.
Ứng dụng chạy trên Linux không tìm thấy biến API_KEY dù file cấu hình đã export api_key; tên biến môi trường phân biệt hoa thường trên Unix và hai tên không tương đương.
Script Bash gán biến bằng VAR = value có khoảng trắng quanh dấu bằng; shell diễn giải VAR thành command và value thành đối số thay vì gán biến.
Một script PowerShell gán biến $env:MODE trong process hiện tại rồi khởi chạy một shell độc lập; biến chỉ tồn tại ở process cha và tiến trình con không nhận được cấu hình như mong muốn.
Nhóm thêm thư mục công cụ vào PATH trong file .bashrc nhưng tác vụ cron chạy non-interactive shell không đọc file này; lệnh có sẵn trong terminal nhưng không tìm thấy khi chạy lịch.
Script Windows thêm thư mục mới vào PATH nhưng ghi đè toàn bộ PATH hiện tại; các lệnh hệ thống và công cụ build khác đột nhiên không được tìm thấy.
Thư mục hiện tại chứa executable tên curl và nằm trước thư mục hệ thống trong PATH; script gọi curl không có đường dẫn đầy đủ nên chạy nhầm chương trình không đáng tin cậy.
PowerShell tìm thấy alias ls trỏ tới Get-ChildItem, nhưng script cần gọi executable ls native; alias resolution khiến tham số Unix được hiểu theo cú pháp PowerShell và lệnh thất bại.
Một script Bash gọi python nhưng máy có cả python2 và python3; PATH ưu tiên môi trường cũ nên script dùng cú pháp hoặc thư viện không tương thích.
Một pipeline Bash dùng command1 | command2; command1 thất bại nhưng command2 trả exit code 0, khiến script coi cả pipeline thành công nếu không bật pipefail hoặc kiểm tra PIPESTATUS.
Script Bash bật set -e và mong mọi lỗi command substitution làm script dừng; một số ngữ cảnh như điều kiện if, danh sách &&/|| hoặc pipeline làm hành vi errexit khác kỳ vọng.
PowerShell chạy nhiều lệnh trong pipeline và kiểm tra $? sau một lệnh ghi log; giá trị phản ánh trạng thái của lệnh gần nhất, không còn phản ánh lệnh native trước đó.
Script PowerShell gọi chương trình native trả exit code 7 nhưng chỉ kiểm tra $?; cần đọc $LASTEXITCODE để phân biệt tiến trình native thất bại với lỗi PowerShell.
Một script Bash gọi nhiều lệnh rồi cuối cùng chạy echo 'done'; exit code cuối cùng bằng 0 che mất lỗi ở lệnh build trước đó vì script không kiểm tra trạng thái từng bước.
PowerShell dùng pipeline object để lọc process theo thuộc tính Id, còn script Bash chuyển output ps thành chuỗi rồi grep; khi locale hoặc định dạng ps thay đổi, phép lọc theo cột bị sai.
Một nhóm nối output của lệnh native vào cmdlet PowerShell và giả định dữ liệu vẫn là object có thuộc tính; PowerShell chuyển output native thành text nên Where-Object không tìm được trường dự kiến.
Script Bash dùng 2>&1 > build.log nhưng người viết mong stdout và stderr cùng vào file; thứ tự redirect khiến stderr vẫn đi tới nơi stdout ban đầu trỏ tới.
Script dùng > output.log 2>&1 để gom stdout và stderr, nhưng trong PowerShell 5.1 redirect stream khác với Bash và một số native output được xử lý khác; log thu được không đúng định dạng mong đợi.
Một pipeline Bash dùng tee để lưu log và chuyển tiếp dữ liệu; nếu không kiểm tra trạng thái pipeline, lỗi của lệnh đầu có thể bị che bởi tee thành công.
Script PowerShell ghi thông báo ra Write-Host và mong pipeline phía sau nhận được; Write-Host phục vụ hiển thị còn dữ liệu cần chuyển qua pipeline phải được emit bằng output object.
Script PowerShell đọc file UTF-8 có BOM rồi ghi lại bằng encoding mặc định của Windows PowerShell 5.1; file đầu ra có thể thành UTF-16LE và chương trình Linux downstream không đọc như mong đợi.
Một file script Bash được lưu CRLF trên Windows và chạy trong Linux; ký tự carriage return ở cuối dòng shebang khiến hệ thống không tìm thấy interpreter dù đường dẫn /bin/bash tồn tại.
Script PowerShell gọi native executable và truyền một mảng đối số; cách serialize đối số thay đổi theo phiên bản PowerShell, làm chuỗi có dấu cách hoặc dấu nháy bị tách khác nhau trên PowerShell 5.1 và 7.
Một Bash script xử lý file bằng vòng while read chạy ở phía sau pipeline; vòng lặp chạy trong subshell nên biến đếm thay đổi bên trong không tồn tại ở shell cha sau khi kết thúc.
Một script Bash nhận input có dấu gạch ngang đầu tên file; chương trình downstream hiểu tên đó là option vì không dùng -- để kết thúc danh sách option.
Script Bash dùng read để đọc dòng cuối file không có newline; vòng lặp chỉ kiểm tra read exit status nên bỏ mất dòng cuối dù dữ liệu vẫn có.
Một script PowerShell đọc CSV bằng Get-Content rồi split dấu phẩy thủ công; trường có dấu phẩy được quote hợp lệ bị tách sai thay vì dùng Import-Csv.
Script Bash khởi chạy tiến trình nền bằng & rồi thoát ngay; tiến trình con bị đóng stdin hoặc nhận SIGHUP tùy môi trường, nên job dài không tiếp tục như người viết mong đợi.
Một script PowerShell dùng Start-Process -PassThru nhưng không chờ WaitForExit trước khi đọc ExitCode; thuộc tính chưa có giá trị cuối cùng và bước kiểm tra kết quả chạy quá sớm.
Nhóm dừng tiến trình bằng kill PID đã lưu từ nhiều giờ trước; PID đã được hệ điều hành tái sử dụng cho process khác và script kết thúc nhầm ứng dụng không liên quan.
Script Bash dùng trap để cleanup file tạm khi nhận SIGINT nhưng không xử lý EXIT; khi một lệnh lỗi khiến shell thoát bình thường, file tạm và lock file vẫn còn.
PowerShell script chạy trong CI bị Ctrl+C nhưng không có finally block hoặc trap phù hợp; file tạm và process con còn tồn tại sau khi job bị hủy.
Một script xóa file theo pattern do người dùng nhập; biến rỗng hoặc sai thư mục khiến lệnh rm -rf nhắm vào đường dẫn rộng hơn dự định vì không kiểm tra giá trị và thư mục gốc.
PowerShell script dùng Remove-Item -Recurse trên đường dẫn được ghép từ biến chưa kiểm tra; biến rỗng khiến thao tác nhắm tới nội dung thư mục hiện tại thay vì thư mục build dự kiến.
Script Bash chạy lệnh có input từ người dùng bằng eval; chuỗi chứa shell metacharacters được diễn giải thành cú pháp shell và thực thi lệnh ngoài ý định.
Một script PowerShell dùng Invoke-Expression với tham số lấy từ file cấu hình; ký tự pipe và dấu chấm phẩy trong giá trị bị thực thi như cú pháp PowerShell thay vì dữ liệu.
Script Bash ghi secret vào command-line argument của tiến trình con; người dùng khác có quyền xem process list có thể đọc credential trong danh sách đối số.
PowerShell script đặt API token trực tiếp trong file .ps1 được commit vào Git; xóa dòng secret ở commit mới không loại bỏ credential khỏi lịch sử repository.
Một script dùng set -x để debug trong CI; shell in lệnh đã mở rộng biến và vô tình ghi token hoặc mật khẩu ra log build.
PowerShell transcript được bật để chẩn đoán script và ghi cả giá trị biến bí mật ra file; file transcript có ACL rộng hơn kho secret ban đầu.
Script Bash dùng sudo cho toàn bộ pipeline dù chỉ một lệnh cần quyền cao; các lệnh xử lý dữ liệu khác cũng chạy với quyền root và có phạm vi ảnh hưởng lớn hơn dự định.
Một script PowerShell cần ghi vào thư mục hệ thống nhưng chạy không elevated; lệnh thất bại do access denied và script tiếp tục vì không bật xử lý lỗi thích hợp.
Nhóm chạy script bằng tài khoản dịch vụ không có home directory hợp lệ; công cụ tìm config theo $HOME hoặc $env:USERPROFILE và dùng cấu hình mặc định ngoài dự kiến.
Một script dựa vào locale để parse ngày tháng nhưng máy CI dùng en-US còn máy người dùng dùng vi-VN; cùng chuỗi ngày được hiểu thành hai ngày khác nhau.
PowerShell script dùng Sort-Object trên chuỗi số '2', '10' và kỳ vọng thứ tự số; so sánh chuỗi đặt '10' trước '2' và chọn sai phiên bản mới nhất.
Một script dùng đường dẫn chứa ký tự Unicode trên Windows rồi chuyển file sang Linux; một công cụ normalize tên file khác dạng NFC/NFD nên lệnh tìm kiếm chính xác không thấy file.
Script Bash được chạy qua sh thay vì bash; cú pháp array và [[ ... ]] không được POSIX sh hỗ trợ nên script lỗi dù chạy trực tiếp bằng Bash thành công.
PowerShell script sử dụng cú pháp mới của PowerShell 7 nhưng được gọi bởi Windows PowerShell 5.1 từ Task Scheduler; parser dừng trước khi script bắt đầu xử lý.
Một nhóm dùng biến môi trường để cấu hình proxy nhưng chỉ đặt HTTP_PROXY; một công cụ chỉ đọc http_proxy chữ thường hoặc HTTPS_PROXY nên các request đi theo đường mạng khác nhau giữa môi trường.
Script Bash thay đổi PATH trong subshell để chạy một công cụ cục bộ; lệnh sau pipeline ở shell cha không thấy PATH mới và không tìm được executable.
PowerShell dùng Set-Location trong script dot-sourced; current directory của session tương tác thay đổi ngoài ý muốn sau khi script hoàn tất.
Một script Bash được source thay vì execute; lệnh exit trong file kết thúc luôn shell tương tác của người dùng thay vì chỉ dừng script con.
Script PowerShell được dot-source để dùng function nhưng cũng thay đổi global preference variables và location; các thay đổi rò ra session gọi script và ảnh hưởng lệnh tiếp theo.
