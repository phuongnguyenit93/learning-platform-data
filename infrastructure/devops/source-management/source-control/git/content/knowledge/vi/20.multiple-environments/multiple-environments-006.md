# Liên kết tượng trưng và khác biệt hỗ trợ giữa các hệ điều hành

Liên kết tượng trưng (symbolic link, thường gọi là **symlink**) là một mục trong hệ thống tệp trỏ tới một đường dẫn khác. Symlink giúp nhiều vị trí cùng tham chiếu tới một file hoặc thư mục mà không cần sao chép dữ liệu. Trong dự án Git, symlink thường được dùng để chia sẻ cấu hình, tài nguyên hoặc thư mục dùng chung.

Git có thể lưu symlink trong repository, nhưng cách symlink xuất hiện trong working tree phụ thuộc vào hệ điều hành, hệ thống tệp và quyền của người dùng. Linux và macOS thường hỗ trợ symlink trực tiếp; Windows cũng hỗ trợ nhưng có thể cần Developer Mode hoặc quyền tạo symbolic link. Nếu môi trường không tạo được symlink, Git có thể checkout nó thành một file văn bản chứa đường dẫn đích.

Hiểu cách Git lưu symlink và các khác biệt này giúp tránh tình trạng một thành viên thấy liên kết hoạt động, còn thành viên khác chỉ thấy một file văn bản hoặc gặp lỗi khi checkout.

## 1. Symlink là gì?

Symlink là một mục của hệ thống tệp chứa đường dẫn tới một mục khác. Khi chương trình truy cập symlink, hệ điều hành thường phân giải đường dẫn và chuyển thao tác tới đích của liên kết.

Ví dụ, dự án có cấu trúc:

~~~text
project/
├── config/
│   └── app.yml
└── deploy/
    └── app.yml -> ../config/app.yml
~~~

File deploy/app.yml là symlink trỏ tới config/app.yml. Khi ứng dụng đọc deploy/app.yml, hệ điều hành chuyển việc đọc tới file đích.

Symlink có thể trỏ tới:

- Một file.
- Một thư mục.
- Một đường dẫn tương đối hoặc tuyệt đối.
- Một đích chưa tồn tại (dangling symlink).

Symlink có thể hợp lệ về mặt cấu trúc dù đích chưa tồn tại, nhưng ứng dụng truy cập liên kết sẽ không đọc được nội dung đích cho tới khi đường dẫn đó xuất hiện.

### Phân biệt symlink, hard link và shortcut

| Loại liên kết | Cách hoạt động | Đặc điểm |
|---|---|---|
| Symbolic link | Lưu đường dẫn tới một đích | Có thể trỏ tới file hoặc thư mục, kể cả đích chưa tồn tại; có thể trỏ qua filesystem khác |
| Hard link | Tạo thêm một tên cho cùng file object/inode | Thường không dùng cho thư mục; bị giới hạn bởi filesystem và volume |
| Windows shortcut (.lnk) | Là một file shortcut do Windows Shell xử lý | Không phải symlink mà Git lưu dưới mode symlink |

Một file .lnk thường được Git xem như file thông thường. Ứng dụng đọc đường dẫn trực tiếp có thể không hiểu shortcut đó. Nếu dự án cần liên kết mà công cụ dòng lệnh và Git nhận diện nhất quán, hãy dùng symlink thực sự.

## 2. Git lưu symlink như thế nào?

Git không sao chép nội dung file đích vào repository khi thêm một symlink. Git lưu:

1. Một blob chứa chính chuỗi đường dẫn đích của symlink.
2. Một file mode đặc biệt trong tree/index để đánh dấu mục đó là symlink.

Mode của symlink là **120000**. Khi Git checkout trong môi trường hỗ trợ, Git dùng thông tin này để tạo symlink trong working tree.

Ví dụ:

~~~text
Index / Git tree
100644  blob   -> file thường
100755  blob   -> file có executable bit
120000  blob   -> symbolic link
~~~

Với symlink deploy/app.yml trỏ tới ../config/app.yml, blob của symlink chứa chuỗi:

~~~text
../config/app.yml
~~~

Git lưu đường dẫn đích, không lưu nội dung của config/app.yml trong blob symlink. File đích được theo dõi riêng nếu nó cũng nằm trong repository.

Có thể hình dung:

~~~text
Git tree
  deploy/app.yml
    mode: 120000
    blob: "../config/app.yml"

Working tree trên hệ điều hành hỗ trợ
  deploy/app.yml  --symlink-->  config/app.yml

Working tree khi core.symlinks=false
  deploy/app.yml  --regular file chứa text-->  "../config/app.yml"
~~~

Điểm quan trọng: loại mục được ghi trong Git index/tree vẫn là symlink. Cách checkout thành symlink thực hoặc file văn bản phụ thuộc cấu hình và khả năng của môi trường.

## 3. Tạo symlink trên Linux và macOS

Trên Linux và macOS, lệnh phổ biến để tạo symlink là **ln -s**.

Tạo symlink tới file:

~~~bash
ln -s ../config/app.yml deploy/app.yml
~~~

Tạo symlink tới thư mục:

~~~bash
ln -s ../shared-assets deploy/assets
~~~

Đường dẫn đích tương đối được tính từ thư mục chứa symlink. Trong ví dụ đầu, deploy/app.yml trỏ tới ../config/app.yml, nghĩa là đi lên một cấp từ deploy rồi vào config.

Kiểm tra liên kết:

~~~bash
ls -l deploy
readlink deploy/app.yml
~~~

Lệnh ls -l thường hiển thị mũi tên và đích liên kết. Lệnh readlink in ra chuỗi đường dẫn được lưu trong symlink.

Nếu đích là thư mục, liên kết vẫn được tạo bằng ln -s. Không cần một tùy chọn riêng cho thư mục trên Linux/macOS.

## 4. Tạo symlink trên Windows

Windows hỗ trợ symbolic link, nhưng việc tạo symlink có thể phụ thuộc phiên bản Windows, Developer Mode, quyền của tài khoản và chính sách máy.

Có ba cách thường gặp.

### Dùng PowerShell

Tạo symlink tới file:

~~~powershell
New-Item -ItemType SymbolicLink -Path .\deploy\app.yml -Target ..\config\app.yml
~~~

Tạo symlink tới thư mục:

~~~powershell
New-Item -ItemType SymbolicLink -Path .\deploy\assets -Target ..\shared-assets
~~~

### Dùng Command Prompt

Trong Command Prompt (cmd.exe), dùng mklink:

~~~cmd
mklink deploy\app.yml ..\config\app.yml
mklink /D deploy\assets ..\shared-assets
~~~

Tùy chọn /D tạo directory symbolic link. Lệnh mklink là lệnh của cmd.exe; nếu đang ở PowerShell, có thể gọi cmd /c mklink hoặc dùng New-Item.

### Dùng Git Bash

Git Bash cung cấp lệnh ln:

~~~bash
ln -s ../config/app.yml deploy/app.yml
~~~

Cách này thuận tiện khi nhóm dùng cùng lệnh trong tài liệu cho Linux, macOS và Git Bash. Tuy nhiên, Git Bash vẫn cần Windows cho phép tạo symbolic link thực. Nếu thiếu quyền hoặc khả năng hệ thống, thao tác có thể thất bại hoặc Git có thể đang được cấu hình để checkout symlink thành file thường.

### Quyền tạo symlink trên Windows

Trên Windows, việc tạo symbolic link có thể cần quyền Create symbolic links hoặc Developer Mode được bật. Trong một số môi trường doanh nghiệp, chính sách máy có thể hạn chế tính năng này.

Nếu lệnh báo lỗi như privilege not held hoặc access denied:

1. Xác nhận bạn đang tạo đúng loại symbolic link.
2. Kiểm tra Developer Mode hoặc quyền của tài khoản.
3. Kiểm tra chính sách máy và filesystem.
4. Kiểm tra cấu hình Git core.symlinks.
5. Chỉ thay đổi cấu hình sau khi xác nhận môi trường có thể tạo symlink thật.

Không nên chạy mọi terminal với quyền Administrator chỉ để né lỗi mà chưa hiểu chính sách máy. Hãy dùng cơ chế quyền được tổ chức cho phép.

## 5. Đưa symlink vào Git

Sau khi tạo symlink, thêm nó vào staging area như file thông thường:

~~~bash
git add deploy/app.yml
git status --short
git diff --cached --summary
~~~

Để xác nhận Git nhận diện đúng là symlink, xem mode trong index:

~~~bash
git ls-files --stage -- deploy/app.yml
~~~

Kết quả minh họa:

~~~text
120000 4b825dc642cb6eb9a060e54bf8d69288fbee4904 0 deploy/app.yml
~~~

Hash trong ví dụ chỉ để minh họa. Phần cần chú ý là mode 120000. Nếu Git hiển thị 100644, mục đang được stage như file thường chứ không phải symlink.

Xem chuỗi đích đang được lưu trong index:

~~~bash
git show :deploy/app.yml
~~~

Xem nội dung đã commit:

~~~bash
git show HEAD:deploy/app.yml
~~~

Hai lệnh này hiển thị blob chứa đường dẫn đích của symlink. Chúng không mở nội dung file đích như khi ứng dụng đi theo liên kết trong filesystem.

Sau khi kiểm tra:

~~~bash
git commit -m "Add shared app config symlink"
~~~

## 6. core.symlinks ảnh hưởng tới checkout ra sao?

Git có cấu hình **core.symlinks** để điều khiển cách xử lý symlink trong working tree.

Kiểm tra cấu hình:

~~~bash
git config --show-origin --get core.symlinks
~~~

Nếu lệnh không in kết quả, cấu hình có thể chưa được đặt tường minh. Git thường mặc định hỗ trợ symlink, nhưng khi clone trên môi trường không tạo được symlink, Git có thể đặt core.symlinks=false cho repository đó.

### core.symlinks=true

Khi bật, Git cố gắng checkout mục mode 120000 thành symlink thực trên filesystem.

~~~bash
git config --local core.symlinks true
~~~

Chỉ đặt true khi môi trường có thể tạo symlink. Nếu Windows chưa có quyền phù hợp hoặc filesystem không hỗ trợ, checkout có thể thất bại.

### core.symlinks=false

Khi tắt, Git checkout symlink thành file thường có nội dung là chuỗi đường dẫn đích:

~~~bash
git config --local core.symlinks false
~~~

Ví dụ, deploy/app.yml có thể trở thành file văn bản chỉ chứa:

~~~text
../config/app.yml
~~~

Trong repository, index vẫn ghi mode 120000. Đây là cơ chế tương thích để làm việc với repository có symlink trong môi trường không tạo được symlink thực. Nó không biến symlink trong lịch sử Git thành file thường.

Nếu bạn bật core.symlinks sau khi checkout, working tree hiện tại không nhất thiết tự chuyển đổi ngay. Hãy kiểm tra trước và checkout lại mục liên quan khi đã bảo toàn mọi chỉnh sửa:

~~~bash
git status
git config --local core.symlinks true
git restore --source=HEAD --worktree -- deploy/app.yml
~~~

Lệnh restore trên yêu cầu Git checkout lại mục từ HEAD. Chỉ dùng khi bạn không có chỉnh sửa local cần giữ ở đường dẫn đó. Sau đó xác minh bằng công cụ của hệ điều hành và git ls-files --stage.

Nếu clone mới, nên bảo đảm khả năng tạo symlink đã sẵn sàng trước khi clone để Git nhận diện đúng môi trường ngay từ đầu.

## 7. Khác biệt hỗ trợ symlink giữa các hệ điều hành

| Môi trường | Hỗ trợ thông thường | Điều cần chú ý |
|---|---|---|
| Linux | Hỗ trợ symlink ở cấp filesystem | Quyền truy cập đích, mount option và filesystem có thể ảnh hưởng |
| macOS | Hỗ trợ symlink ở cấp filesystem | APFS/HFS+ và quyền truy cập; volume có thể có thiết lập khác |
| Windows 10/11 | Hỗ trợ symlink | Có thể cần Developer Mode hoặc quyền tạo symbolic link; Git có thể dùng core.symlinks=false |
| WSL | Hỗ trợ symlink trong filesystem Linux | Khả năng tương tác phụ thuộc symlink nằm trong filesystem Linux hay Windows và cách mount |
| Network share, removable drive hoặc filesystem hạn chế | Tùy filesystem và chính sách | Có thể không tạo, theo dõi hoặc phân giải symlink giống filesystem cục bộ |

Không nên suy luận chỉ từ tên hệ điều hành rằng mọi ổ đĩa đều hỗ trợ giống nhau. Ví dụ, một máy Linux có thể truy cập filesystem hoặc mount được cấu hình hạn chế; một máy Windows có thể hỗ trợ symlink ở ổ NTFS nhưng không ở một volume khác.

Khi nhóm làm việc đa hệ điều hành, hãy kiểm tra khả năng thật của filesystem và cấu hình Git trên từng môi trường.

## 8. Đường dẫn tương đối và tuyệt đối

Symlink có thể lưu đường dẫn tương đối hoặc tuyệt đối.

Ví dụ đường dẫn tương đối:

~~~bash
ln -s ../config/app.yml deploy/app.yml
~~~

Ví dụ đường dẫn tuyệt đối:

~~~bash
ln -s /home/alex/project/config/app.yml deploy/app.yml
~~~

Đường dẫn tuyệt đối thường phụ thuộc máy cụ thể. Trên máy khác, username, ổ đĩa hoặc vị trí checkout có thể khác nên liên kết bị hỏng.

Đối với repository được chia sẻ, nên ưu tiên đường dẫn tương đối nằm trong cấu trúc dự án:

- Không gắn symlink vào thư mục home của một cá nhân.
- Không dùng đường dẫn ổ đĩa riêng như D:/workspace/... nếu repository dành cho nhiều người.
- Kiểm tra đường dẫn tương đối từ vị trí symlink, không phải từ thư mục gốc repository.
- Nếu target nằm ngoài repository, ghi rõ yêu cầu môi trường và cách thiết lập.

Symlink tương đối thường dễ di chuyển cùng repository hơn. Tuy vậy, nếu cấu trúc thư mục thay đổi, đường dẫn đích cũng cần được cập nhật.

## 9. Dấu phân cách đường dẫn và tính di động

Git lưu tên đường dẫn trong tree bằng dấu gạch chéo xuôi (/). Đường dẫn trong symlink là nội dung blob, vì vậy chuỗi đích được lưu đúng như đã tạo.

Trên Linux và macOS, dấu gạch chéo ngược thường không được hiểu là dấu phân cách thư mục trong đường dẫn Unix. Trên Windows, cả dấu / và \ thường được chấp nhận trong nhiều ngữ cảnh đường dẫn, nhưng cách các công cụ xử lý có thể khác.

Để tăng khả năng di động:

- Ưu tiên symlink tương đối.
- Dùng dấu / trong target khi tạo symlink bằng Git Bash hoặc công cụ hỗ trợ cú pháp này.
- Tránh ghi đường dẫn Windows tuyệt đối vào repository đa nền tảng.
- Kiểm tra target sau khi clone trên từng hệ điều hành được hỗ trợ.
- Không giả định mọi công cụ build sẽ tự phân giải symlink theo cùng cách.

Một symlink có target dùng dấu gạch chéo ngược có thể hoạt động trên Windows nhưng bị hiểu thành tên chứa ký tự backslash trên Unix. Vì vậy, cách viết target có tính di động rất quan trọng.

## 10. Khác biệt về phân biệt chữ hoa/chữ thường

Git lưu tên file theo đúng chữ hoa/chữ thường, nhưng filesystem có thể xử lý khác nhau.

- Linux thường phân biệt App.yml và app.yml là hai tên khác nhau.
- Windows thường không phân biệt hoa/thường trong tên file.
- macOS thường dùng filesystem không phân biệt hoa/thường theo mặc định, dù có thể tạo volume phân biệt hoa/thường.

Điều này ảnh hưởng cả symlink lẫn file đích. Ví dụ, symlink trỏ tới Config/App.yml có thể hoạt động trên Windows hoặc macOS dùng filesystem không phân biệt hoa/thường, nhưng hỏng trên Linux nếu tên thật trong repository là config/app.yml. Sự khác biệt có thể chỉ lộ ra khi thành viên khác checkout trên filesystem phân biệt hoa/thường.

Git có cấu hình core.ignorecase để thích nghi với filesystem không phân biệt hoa/thường. Kiểm tra:

~~~bash
git config --show-origin --get core.ignorecase
~~~

Git thường tự dò và thiết lập giá trị phù hợp khi khởi tạo hoặc clone. Không nên thay đổi core.ignorecase chỉ để che lỗi khác biệt tên file.

Khi đổi tên chỉ khác chữ hoa/thường, có thể dùng tên trung gian:

~~~bash
git mv config.yml config.tmp
git mv config.tmp Config.yml
git status
~~~

Sau đó kiểm tra diff và commit. Cách này giúp Git nhận ra thao tác đổi tên trên filesystem vốn không hỗ trợ hai tên khác nhau chỉ bởi casing.

## 11. Khác biệt về executable bit và core.filemode

Ngoài symlink, Git còn theo dõi một số mode của file, trong đó có executable bit. Trên Linux và macOS, quyền thực thi thường được biểu diễn qua mode 100755; file thông thường thường là 100644.

Windows không sử dụng Unix executable bit theo cùng cách. Git for Windows thường cấu hình core.filemode=false khi filesystem không phản ánh quyền thực thi phù hợp.

Kiểm tra:

~~~bash
git config --show-origin --get core.filemode
git ls-files --stage -- scripts/deploy.sh
~~~

Các mode thường gặp:

| Mode | Ý nghĩa |
|---|---|
| 100644 | File thường, không có executable bit |
| 100755 | File thường có executable bit |
| 120000 | Symlink |

core.filemode điều khiển việc Git có xem thay đổi permission bit là thay đổi hay không. Nó không phải cấu hình symlink; core.symlinks mới là cấu hình liên quan tới checkout symlink.

Nếu script cần chạy trên Linux/macOS, hãy kiểm tra mode trong index thay vì chỉ nhìn thuộc tính file trên Windows. Có thể cập nhật executable bit trong Git bằng:

~~~bash
git update-index --chmod=+x scripts/deploy.sh
~~~

Lệnh thay đổi mode trong index. Sau đó kiểm tra bằng git ls-files --stage trước khi commit.

## 12. Thay đổi target của symlink

Để đổi target, tạo lại symlink với đường dẫn mới. Trên Linux/macOS hoặc Git Bash:

~~~bash
rm deploy/app.yml
ln -s ../config/app-v2.yml deploy/app.yml
~~~

Lệnh rm ở đây xóa chính symlink, không xóa file đích. Không dùng lệnh xóa đệ quy nếu chưa hiểu đường dẫn đang trỏ tới đâu.

Trong PowerShell, có thể xóa liên kết bằng:

~~~powershell
Remove-Item -LiteralPath .\deploy\app.yml
New-Item -ItemType SymbolicLink -Path .\deploy\app.yml -Target ..\config\app-v2.yml
~~~

Sau đó kiểm tra Git nhận ra thay đổi:

~~~bash
git status --short
git diff --summary
git diff
~~~

Vì target được lưu dưới dạng nội dung blob, thay đổi chuỗi target sẽ làm Git hiển thị thay đổi của symlink. Mode vẫn là 120000 nếu mục vẫn là symlink.

Nếu vô tình thay symlink bằng một file thường, mode có thể đổi từ 120000 sang 100644. Hãy xem staged mode bằng git ls-files --stage và sửa lại symlink trước khi commit.

## 13. Kiểm tra symlink trong working tree

Trên Linux/macOS/Git Bash:

~~~bash
ls -l deploy/app.yml
readlink deploy/app.yml
test -L deploy/app.yml && echo "is symlink"
~~~

Trên PowerShell hiện đại:

~~~powershell
$item = Get-Item -LiteralPath .\deploy\app.yml
$item | Format-List FullName,Attributes,LinkType,Target
~~~

Nếu Git đang checkout symlink dưới dạng file thường do core.symlinks=false, các lệnh kiểm tra filesystem sẽ nhận diện file thường. Nội dung file lúc đó thường là chuỗi target. Đừng chỉ mở file và thấy đường dẫn rồi kết luận Git đã lưu sai; hãy kiểm tra mode trong index.

Kiểm tra Git index:

~~~bash
git ls-files --stage -- deploy/app.yml
~~~

Kiểm tra blob target đang commit:

~~~bash
git show HEAD:deploy/app.yml
~~~

Đối chiếu cả ba góc nhìn: filesystem, index và commit. Chúng trả lời ba câu hỏi khác nhau: working tree hiện là gì, Git sắp commit loại mục nào, và lịch sử đang lưu target nào.

## 14. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra hoặc xử lý |
|---|---|---|
| Tạo symlink trên Windows báo Access denied | Thiếu quyền hoặc Developer Mode chưa bật | Kiểm tra chính sách và quyền tạo symbolic link |
| Clone xong symlink thành file văn bản | core.symlinks=false hoặc môi trường không tạo được symlink | Xem mode 120000 và cấu hình core.symlinks |
| Git báo symlink nhưng ứng dụng không đọc được | Target sai, target không tồn tại hoặc đường dẫn không tương thích | Dùng readlink/Get-Item và kiểm tra target từ vị trí symlink |
| Linux chạy được nhưng Windows lỗi | Windows thiếu quyền, đường dẫn khác hoặc filesystem không hỗ trợ | Kiểm tra quyền, filesystem, target và cấu hình Git |
| Windows chạy được nhưng Linux lỗi | Target chứa backslash hoặc phụ thuộc đường dẫn Windows | Dùng target tương đối với dấu / |
| Git thấy mode 100644 thay vì 120000 | Mục đang là file thường hoặc Windows shortcut .lnk, không phải symlink được stage | Kiểm tra loại mục trong filesystem và tạo symlink thật trước khi stage; file giả do core.symlinks=false vẫn giữ mode 120000 trong index |
| File đích bị sửa ngoài ý muốn | Công cụ đã đi theo symlink và ghi vào target | Xác định target và kiểm tra công cụ build/script |
| Đổi tên khác casing không được nhận | Filesystem không phân biệt hoa/thường | Dùng tên trung gian rồi kiểm tra git status |

Khi gặp lỗi, đừng vội xóa file hoặc thay đổi cấu hình toàn cục. Xác định Git đang lưu mode nào, working tree đang có loại mục nào và target thực tế là gì.

## 15. Symlink và an toàn khi làm việc với repository

Symlink có thể trỏ ra ngoài thư mục repository. Git lưu đường dẫn đích, nhưng không đảm bảo đích nằm trong repository hoặc tồn tại trên mọi máy.

Ví dụ, symlink có thể trỏ tới thư mục cha:

~~~bash
ln -s ../../private-config deploy/private
~~~

Khi một công cụ build, script hoặc editor mở deploy/private, nó có thể truy cập dữ liệu ngoài repository tùy quyền của người dùng.

Khi nhận repository từ nguồn chưa tin cậy:

- Kiểm tra symlink trong diff trước khi chạy script hoặc build.
- Xem target bằng readlink hoặc công cụ tương đương.
- Cẩn thận với symlink trỏ tới thư mục cấu hình, credential hoặc thư mục cá nhân.
- Không chạy script tự động nếu chưa hiểu nó đi theo các liên kết nào.
- Tránh đặt symlink trỏ ra ngoài repository nếu dự án không có lý do rõ ràng.

Symlink tự nó không cấp thêm quyền truy cập; chương trình đi theo liên kết vẫn chạy bằng quyền của người dùng hiện tại. Rủi ro nằm ở việc công cụ có thể đọc hoặc ghi một đường dẫn ngoài phạm vi mà người dùng tưởng đang thao tác.

## 16. Quy trình cộng tác đa hệ điều hành

Giả sử nhóm có thành viên dùng Linux, macOS và Windows. Repository dùng symlink deploy/app.yml trỏ tới config/app.yml.

Một quy trình nhất quán có thể gồm:

**Bước 1 — Thống nhất target tương đối**

~~~text
deploy/app.yml -> ../config/app.yml
~~~

Không dùng đường dẫn tuyệt đối gắn với một máy cụ thể.

**Bước 2 — Xác nhận môi trường**

Trên Windows, kiểm tra quyền tạo symlink và core.symlinks. Trên Linux/macOS, xác nhận filesystem và quyền truy cập đích.

**Bước 3 — Tạo symlink và stage**

~~~bash
ln -s ../config/app.yml deploy/app.yml
git add deploy/app.yml
~~~

Trên Windows, dùng Git Bash nếu có khả năng tạo symlink hoặc New-Item/mklink theo chính sách máy.

**Bước 4 — Kiểm tra mode và target**

~~~bash
git ls-files --stage -- deploy/app.yml
git show :deploy/app.yml
~~~

Kết quả mong đợi là mode 120000 và target tương đối đúng.

**Bước 5 — Commit và push**

~~~bash
git commit -m "Add portable config symlink"
git push
~~~

**Bước 6 — Kiểm tra sau clone trên hệ điều hành khác**

Mỗi thành viên xác minh Git index và working tree. Nếu Windows checkout thành file thường, kiểm tra core.symlinks và quyền tạo symbolic link trước khi kết luận repository bị lỗi.

Nhóm nên ghi yêu cầu môi trường vào tài liệu dự án, ví dụ cần bật Developer Mode trên Windows hoặc cần filesystem hỗ trợ symlink. Điều này giúp người mới biết vì sao cùng một repository có thể được checkout khác nhau.

## 17. Checklist trước khi commit symlink

- [ ] Target có đúng và tồn tại trong môi trường cần dùng không?
- [ ] Target có tương đối để tránh phụ thuộc máy cá nhân không?
- [ ] Đường dẫn có dùng dấu phân cách phù hợp cho các hệ điều hành mục tiêu không?
- [ ] Symlink có trỏ ra ngoài repository không?
- [ ] Git index hiển thị mode 120000 không?
- [ ] Blob trong index chứa đúng chuỗi target không?
- [ ] Thành viên Windows có quyền tạo symlink hoặc đã hiểu giới hạn core.symlinks chưa?
- [ ] Tên file có khác nhau chỉ bởi chữ hoa/thường không?
- [ ] Các script/build tool có xử lý symlink đúng và an toàn không?

## 18. Những điểm cần ghi nhớ

- Symlink là một mục hệ thống tệp trỏ tới đường dẫn khác; nó khác hard link và Windows shortcut.
- Git lưu symlink bằng mode 120000 và blob chứa chuỗi target.
- Linux và macOS thường hỗ trợ symlink trực tiếp; Windows hỗ trợ nhưng có thể cần Developer Mode hoặc quyền phù hợp.
- core.symlinks=true yêu cầu Git tạo symlink thật; core.symlinks=false checkout thành file thường chứa target.
- Git index vẫn có thể giữ mode 120000 ngay cả khi working tree hiển thị file văn bản do cấu hình tương thích.
- Ưu tiên target tương đối và tránh đường dẫn tuyệt đối gắn với máy cá nhân.
- Git lưu tên path phân biệt hoa/thường, nhưng filesystem Windows/macOS mặc định thường không phân biệt.
- core.filemode liên quan executable bit; core.symlinks liên quan symlink.
- Kiểm tra filesystem, index và commit riêng biệt khi chẩn đoán lỗi.
- Review symlink từ repository chưa tin cậy vì công cụ có thể đi theo liên kết tới dữ liệu ngoài repository.

Symlink giúp repository tham chiếu tài nguyên dùng chung mà không sao chép dữ liệu. Khi hiểu mode 120000, cấu hình core.symlinks và khả năng của từng hệ điều hành, nhóm có thể thiết kế liên kết dễ di chuyển, kiểm tra được và hoạt động ổn định hơn trong môi trường đa nền tảng.

