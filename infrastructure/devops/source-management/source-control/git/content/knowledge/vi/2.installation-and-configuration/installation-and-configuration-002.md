# Kiểm tra phiên bản, trợ giúp và khả năng tương thích lệnh

Git phát triển qua nhiều phiên bản. Một máy có thể cài Git từ bộ cài riêng, trình quản lý gói, Git for Windows hoặc đi kèm IDE. Vì vậy, hai terminal trên cùng máy đôi khi gọi hai bản Git khác nhau. Một lệnh chạy được trên máy của bạn cũng có thể không tồn tại hoặc không hỗ trợ cùng tùy chọn trên máy đồng đội hay môi trường CI.

Trước khi sử dụng một lệnh mới, viết script tự động hoặc hướng dẫn nhóm, hãy xác định đúng phiên bản Git đang được gọi, xem tài liệu trợ giúp của chính lệnh đó và kiểm tra các tùy chọn có sẵn trong môi trường thực tế. Bài học này hướng dẫn cách kiểm tra phiên bản, tra cứu trợ giúp và đánh giá khả năng tương thích để sử dụng Git nhất quán.

## 1. Kiểm tra phiên bản Git đang chạy

### 1.1. Dùng git --version

Lệnh cơ bản nhất:

~~~bash
git --version
~~~

Ví dụ kết quả:

~~~text
git version 2.43.0.windows.1
~~~

Kết quả cho biết phiên bản của chương trình Git được shell tìm thấy khi chạy lệnh. Phần hậu tố có thể cho biết bản đóng gói hoặc nền tảng, chẳng hạn bản dành cho Windows. Không nên xóa hoặc bỏ qua hậu tố khi cần điều tra khác biệt giữa các bản phân phối.

Phiên bản Git thường có dạng:

`major.minor.patch`

- **major:** phiên bản chính.
- **minor:** phiên bản phụ, thường bổ sung tính năng và cải tiến.
- **patch:** bản sửa lỗi trong dòng phiên bản.

Một số nhà phân phối thêm hậu tố hoặc thông tin build. Vì vậy, không nên so sánh chuỗi phiên bản bằng cách nhìn ký tự đơn giản; hãy dùng quy tắc phiên bản phù hợp hoặc kiểm tra trực tiếp khả năng của lệnh.

### 1.2. Kiểm tra đúng bản Git mà terminal đang gọi

Máy có thể cài nhiều bản Git. Ví dụ, Git for Windows có thể nằm trong `C:\Program Files\Git`, còn một IDE có thể dùng bản Git đi kèm hoặc một đường dẫn được cấu hình riêng.

Trên Windows PowerShell:

~~~powershell
Get-Command git -All | Format-Table CommandType, Source, Definition -AutoSize
~~~

Trong Command Prompt:

~~~bat
where.exe git
~~~

Trong Bash hoặc shell tương tự trên Linux/macOS:

~~~bash
type -a git
~~~

Các lệnh này cho biết shell có thể tìm thấy những chương trình hoặc alias nào mang tên `git`. Nếu có nhiều kết quả, vị trí đứng đầu trong thứ tự phân giải thường là lệnh được gọi khi bạn gõ `git`.

Sau đó chạy:

~~~bash
git --version
~~~

để xác nhận phiên bản của chương trình đang được chọn.

Nếu IDE có cấu hình đường dẫn Git riêng, hãy kiểm tra trong phần cài đặt của IDE và chạy kiểm tra phiên bản từ terminal tích hợp của IDE. Kết quả ở terminal hệ thống không bảo đảm IDE đang sử dụng cùng executable.

### 1.3. Vì sao phiên bản hiển thị có thể khác?

Một số nguyên nhân thường gặp:

- PATH chứa nhiều thư mục cài Git và thứ tự tìm kiếm khác nhau.
- IDE hoặc công cụ GUI sử dụng Git đi kèm.
- Terminal được mở trước khi PATH thay đổi nên vẫn giữ môi trường cũ.
- Máy dùng Git từ trình quản lý gói, trong khi terminal khác gọi Git for Windows hoặc bản cài độc lập.
- CI dùng image hoặc runner có phiên bản Git khác máy phát triển.

Khi gặp lỗi “command not found”, “unknown option” hoặc hành vi khác nhau, hãy kiểm tra executable và phiên bản trong chính môi trường phát sinh lỗi. Đừng vội kết luận repository bị hỏng.

## 2. Xem thông tin build và môi trường Git

Ngoài số phiên bản, Git có thể cung cấp thông tin build:

~~~bash
git version --build-options
~~~

Tùy bản phân phối, đầu ra có thể cho biết một số thông tin về môi trường biên dịch hoặc runtime. Đây là dữ liệu hỗ trợ chẩn đoán khi hai bản Git cùng số phiên bản nhưng được đóng gói khác nhau.

Có thể xem thư mục chứa các chương trình phụ trợ của Git:

~~~bash
git --exec-path
~~~

Lệnh này trả về đường dẫn Git dùng để tìm các chương trình thực thi nội bộ. Nó không phải lúc nào cũng là đường dẫn đầy đủ của file `git.exe` hoặc binary `git` mà shell đang gọi. Để xác định executable thực tế, dùng `Get-Command`, `where.exe` hoặc `type -a` như phần trước.

Xem thư mục Git metadata của repository hiện tại:

~~~bash
git rev-parse --git-dir
git rev-parse --show-toplevel
~~~

- `--git-dir` cho biết vị trí Git directory.
- `--show-toplevel` cho biết thư mục gốc của working tree.

Hai lệnh này giúp xác nhận bạn đang ở repository nào, đặc biệt khi terminal mở trong thư mục lồng nhau hoặc khi dùng linked worktree.

## 3. Sử dụng trợ giúp tổng quát của Git

### 3.1. git --help và git help

Để xem trợ giúp tổng quát:

~~~bash
git --help
~~~

Hoặc:

~~~bash
git help
~~~

Tài liệu tổng quát giới thiệu cú pháp, nhóm lệnh và cách truy cập các trang hướng dẫn. Hành vi hiển thị phụ thuộc hệ điều hành và cấu hình trình xem tài liệu: Git có thể mở man page, trình xem văn bản hoặc trang HTML.

Nếu chỉ cần xem danh sách lệnh trong terminal:

~~~bash
git -h
~~~

Đầu ra ngắn cho biết cú pháp chung và các nhóm lệnh chính.

### 3.2. Liệt kê lệnh có sẵn

Xem các lệnh Git:

~~~bash
git help -a
~~~

Xem các hướng dẫn tổng quan (guides):

~~~bash
git help -g
~~~

Các lệnh này hữu ích khi bạn biết mục tiêu nhưng chưa nhớ tên lệnh. Ví dụ, `git help -g` có thể dẫn đến các hướng dẫn về revisions, attributes, hooks hoặc workflows tùy phiên bản.

Không phải mọi lệnh trong danh sách đều là lệnh người dùng thường xuyên cần gọi. Một số lệnh phục vụ quản trị, nội bộ hoặc quy trình nâng cao. Hãy đọc trang trợ giúp tương ứng trước khi sử dụng.

### 3.3. Tìm tài liệu cấu hình

Để xem tài liệu về hệ thống cấu hình:

~~~bash
git help config
~~~

Để xem tài liệu về cú pháp biểu diễn commit và revision:

~~~bash
git help revisions
~~~

Các trang hướng dẫn này giải thích những khái niệm được nhiều lệnh sử dụng chung. Ví dụ, hiểu revision giúp đọc các biểu thức như `HEAD~1`, `main..feature` hoặc `tag^{commit}` chính xác hơn.

## 4. Xem trợ giúp của một lệnh cụ thể

### 4.1. Dùng -h để xem cú pháp ngắn

Khi cần kiểm tra cú pháp nhanh:

~~~bash
git commit -h
git switch -h
git stash push -h
~~~

Tùy chọn `-h` thường hiển thị phần usage và danh sách tùy chọn của lệnh. Đây là cách nhanh để kiểm tra một tùy chọn có được phiên bản Git hiện tại hỗ trợ hay không.

Ví dụ, trước khi dùng một tùy chọn mới của stash, xem:

~~~bash
git stash push -h
~~~

Nếu phần trợ giúp không liệt kê tùy chọn đó, phiên bản hiện tại có thể chưa hỗ trợ, hoặc cú pháp của lệnh khác với tài liệu bạn đang đọc.

### 4.2. Dùng git help để xem tài liệu đầy đủ

~~~bash
git help commit
git help switch
git help stash
~~~

Tài liệu đầy đủ thường giải thích:

- Cú pháp và ý nghĩa từng tùy chọn.
- Giá trị mặc định.
- Tương tác với cấu hình.
- Các tình huống đặc biệt.
- Ví dụ và ghi chú về hành vi.

Nếu `git help <command>` không mở được trang man, có thể hệ thống chưa cài trình xem tài liệu hoặc cấu hình viewer chưa phù hợp. Trên nhiều bản Git, có thể thử mở tài liệu HTML:

~~~bash
git help -w commit
~~~

Tùy cách đóng gói, tài liệu HTML có thể không được cài. Khi đó, dùng `git <command> -h` để xem cú pháp ngắn hoặc đọc tài liệu chính thức tương ứng với phiên bản đang dùng.

### 4.3. Đọc đúng phần liên quan

Trang trợ giúp dài không có nghĩa bạn phải đọc toàn bộ mỗi lần. Hãy tìm các phần:

- **NAME / SYNOPSIS:** tên và cú pháp lệnh.
- **DESCRIPTION:** lệnh làm gì.
- **OPTIONS:** các tùy chọn và tác động.
- **CONFIGURATION:** khóa cấu hình liên quan.
- **EXAMPLES:** tình huống sử dụng.
- **SEE ALSO:** lệnh hoặc khái niệm liên quan.

Đặc biệt, hãy kiểm tra cách lệnh tương tác với working tree, index và lịch sử trước khi dùng tùy chọn có khả năng ghi đè hoặc viết lại commit.

## 5. Xác định một lệnh có tương thích với phiên bản đang dùng hay không

### 5.1. Không phải lệnh nào cũng có ở mọi phiên bản

Git được bổ sung lệnh và tùy chọn theo thời gian. Một hướng dẫn có thể sử dụng cú pháp chỉ xuất hiện trong phiên bản mới hơn.

Ví dụ:

- `git switch` và `git restore` được giới thiệu trong Git 2.23. Chúng cung cấp giao diện chuyên biệt cho một số tác vụ trước đây thường thực hiện bằng `git checkout`.
- Tùy chọn `git stash push --staged` cần Git 2.35 trở lên.

Nếu máy dùng phiên bản cũ hơn, lệnh có thể báo không nhận diện subcommand hoặc tùy chọn. Điều đó không nhất thiết có nghĩa bạn nhập sai; hãy kiểm tra yêu cầu phiên bản của tính năng.

### 5.2. Kiểm tra bằng trợ giúp của chính lệnh

Ví dụ, muốn biết Git hiện tại hỗ trợ `switch` hay không:

~~~bash
git switch -h
~~~

Muốn biết `stash push` có tùy chọn `--staged` không:

~~~bash
git stash push -h
~~~

Đây là kiểm tra trực tiếp trên executable đang được gọi. Nó thường đáng tin cậy hơn việc chỉ đọc một hướng dẫn trên Internet không ghi rõ phiên bản.

Lưu ý: một số lệnh trả về mã thoát khác 0 khi chỉ in usage. Trong bước kiểm tra tương tác, hãy đọc đầu ra; không tự kết luận rằng lệnh không tồn tại chỉ dựa trên exit code.

### 5.3. Dùng lệnh tương thích trên phiên bản cũ

Nếu môi trường chưa hỗ trợ `git switch`, có thể dùng `git checkout` cho tác vụ chuyển nhánh:

~~~bash
git switch main
~~~

Tương đương trong phiên bản cũ:

~~~bash
git checkout main
~~~

Tạo nhánh và chuyển sang nhánh mới:

~~~bash
git switch -c feature/login
~~~

Cách cũ:

~~~bash
git checkout -b feature/login
~~~

Nếu chưa có `git restore --staged`, có thể bỏ staging một tệp bằng:

~~~bash
git reset HEAD -- path/to/file
~~~

Trên phiên bản mới:

~~~bash
git restore --staged path/to/file
~~~

Nếu chưa có `git restore` để khôi phục nội dung working tree từ index, cách cũ thường dùng:

~~~bash
git checkout -- path/to/file
~~~

Các lệnh cũ có nhiều chế độ hoạt động hơn và cú pháp dễ gây nhầm lẫn. Hãy đọc trợ giúp trước khi dùng, nhất là với `checkout`, vì lệnh này vừa có thể chuyển nhánh vừa có thể cập nhật đường dẫn.

Không thay thế lệnh một cách máy móc nếu tác vụ khác nhau. Hãy xác định bạn muốn chuyển nhánh, bỏ staging hay khôi phục nội dung tệp.

## 6. Phân biệt lỗi phiên bản với lỗi cú pháp và môi trường

Khi một lệnh không chạy, cần phân loại nguyên nhân.

| Dấu hiệu | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| `git: command not found` hoặc không nhận diện lệnh | Git chưa cài hoặc PATH không có executable | `Get-Command git -All`, `where.exe git`, `type -a git` |
| `unknown option` | Phiên bản không hỗ trợ tùy chọn hoặc viết sai cú pháp | `git --version`, `git command -h` |
| `not a git repository` | Terminal đang ở ngoài working tree hoặc Git directory | `pwd`, `git rev-parse --show-toplevel` |
| `pathspec did not match` | Tên đường dẫn hoặc nhánh không đúng trong ngữ cảnh hiện tại | `git status`, `git branch --all`, `git ls-files` |
| Help không mở được | Thiếu man viewer, HTML docs hoặc cấu hình viewer | Dùng `git command -h`, thử `git help -w command` |
| IDE chạy khác terminal | IDE dùng executable Git riêng | Kiểm tra đường dẫn Git trong cài đặt IDE và terminal tích hợp |

Không nên cập nhật Git ngay khi gặp lỗi. Trước tiên hãy kiểm tra executable, cú pháp, thư mục làm việc và trạng thái repository. Việc phân loại đúng giúp tránh thay đổi môi trường khi nguyên nhân thực sự chỉ là nhập sai đường dẫn hoặc đang đứng sai repository.

## 7. Kiểm tra cấu hình ảnh hưởng đến hành vi lệnh

Cùng một lệnh Git có thể cho kết quả khác nhau do cấu hình. Ví dụ, hành vi pull có thể phụ thuộc `pull.rebase`, cách push mặc định phụ thuộc `push.default`, và hiển thị diff có thể phụ thuộc `diff.external` hoặc pager.

Xem cấu hình cùng nguồn xuất xứ:

~~~bash
git config --show-origin --list
~~~

Xem một khóa cụ thể:

~~~bash
git config --show-origin --get pull.rebase
git config --show-origin --get push.default
~~~

Cấu hình có thể đến từ nhiều cấp:

- System: áp dụng cho toàn máy.
- Global: áp dụng cho người dùng hiện tại.
- Local: áp dụng riêng repository.
- Worktree: áp dụng riêng worktree khi được hỗ trợ.

Cấu hình ở cấp cụ thể hơn có thể ghi đè giá trị ở cấp rộng hơn. Khi hành vi lệnh khác mong đợi, hãy kiểm tra cả giá trị lẫn nơi nó được đặt.

Không chia sẻ toàn bộ đầu ra cấu hình công khai nếu trong đó có URL repository nội bộ, tên người dùng hoặc thông tin môi trường nhạy cảm. Chỉ trích phần liên quan sau khi đã kiểm tra nội dung.

## 8. Kiểm tra tương thích trong nhóm và CI

### 8.1. Thống nhất phiên bản tối thiểu

Nếu dự án sử dụng lệnh hoặc tùy chọn mới, hãy thống nhất phiên bản Git tối thiểu cho:

- Máy phát triển của thành viên.
- IDE hoặc GUI mà nhóm hỗ trợ.
- Máy build và CI.
- Container hoặc image triển khai có chạy Git.

Có thể ghi yêu cầu trong tài liệu onboarding, ví dụ:

~~~text
Git 2.35 trở lên
~~~

Đây chỉ là ví dụ. Hãy chọn phiên bản tối thiểu theo các tính năng thực tế dự án sử dụng, không sao chép con số này nếu repository không cần tính năng tương ứng.

### 8.2. Kiểm tra phiên bản trong CI

Trong job CI, có thể in phiên bản Git ngay đầu log:

~~~bash
git --version
~~~

Nếu script phụ thuộc một tùy chọn cụ thể, hãy xác định rõ phiên bản tối thiểu hoặc kiểm tra khả năng lệnh trước khi chạy. Điều này giúp log CI cho biết môi trường thực tế thay vì chỉ báo một lệnh thất bại ở cuối pipeline.

### 8.3. Không chỉ dựa vào chuỗi phiên bản

Một số bản phân phối có thể backport bản sửa lỗi hoặc tính năng mà không thay đổi số phiên bản theo cách bạn kỳ vọng. Ngược lại, chuỗi phiên bản có hậu tố của nhà cung cấp có thể làm việc so sánh chuỗi trở nên sai.

Với script tự động:

- Nếu tính năng có phiên bản tối thiểu chính thức, khai báo và kiểm tra điều kiện đó.
- Nếu có thể, kiểm tra khả năng cụ thể bằng trợ giúp hoặc một phép thử an toàn.
- Không chạy thử lệnh có tác động phá hủy chỉ để xem nó có tồn tại hay không.
- Nếu không đáp ứng điều kiện, dừng với thông báo rõ ràng thay vì tiếp tục bằng một hành vi khác chưa được kiểm chứng.

Đối với các hệ thống hỗ trợ nhiều phiên bản Git, hãy chạy kiểm thử trên phiên bản tối thiểu và phiên bản mới nhất mà dự án công bố hỗ trợ.

## 9. Một quy trình tra cứu trước khi sử dụng lệnh mới

Khi đọc một hướng dẫn Git hoặc nhận lệnh từ đồng đội, có thể làm theo trình tự:

**Bước 1 — Xác định môi trường**

~~~bash
git --version
git rev-parse --show-toplevel
~~~

Xác nhận phiên bản và repository hiện tại.

**Bước 2 — Xem cú pháp lệnh**

~~~bash
git <command> -h
~~~

Thay `<command>` bằng tên lệnh thực tế, ví dụ `switch`, `restore` hoặc `stash`. Dấu ngoặc nhọn trong tài liệu chỉ là chỗ giữ chỗ, không gõ nguyên văn vào terminal.

**Bước 3 — Đọc tài liệu đầy đủ khi cần**

~~~bash
git help <command>
~~~

Tập trung vào tùy chọn, giá trị mặc định và tác động đến repository.

**Bước 4 — Kiểm tra cấu hình liên quan**

~~~bash
git config --show-origin --list
~~~

Chỉ xem các khóa cần thiết và lưu ý giá trị có thể được đặt ở nhiều cấp.

**Bước 5 — Thử trên repository hoặc nhánh an toàn**

Với thao tác chỉ đọc như `git log`, `git status` hoặc `git diff`, có thể kiểm tra trực tiếp. Với thao tác thay đổi lịch sử hoặc ghi đè tệp, hãy thử trong repository kiểm thử hoặc bảo đảm đã có cách khôi phục.

**Bước 6 — Ghi rõ yêu cầu phiên bản nếu chia sẻ cho nhóm**

Nếu hướng dẫn yêu cầu tính năng mới, ghi phiên bản tối thiểu hoặc phương án tương thích đã được kiểm thử.

## 10. Ví dụ tổng hợp: hướng dẫn nhóm dùng git switch

Một thành viên viết tài liệu onboarding và đưa lệnh:

~~~bash
git switch -c feature/profile
~~~

Một đồng đội dùng Git cũ và nhận thông báo không nhận diện lệnh `switch`.

Cách điều tra:

1. Kiểm tra phiên bản trên máy phát sinh lỗi:

~~~bash
git --version
~~~

2. Xác định executable được gọi:

- PowerShell: `Get-Command git -All`.
- Command Prompt: `where.exe git`.
- Bash: `type -a git`.

3. Kiểm tra trợ giúp:

~~~bash
git switch -h
~~~

4. Nếu phiên bản cũ hơn Git 2.23, dùng cú pháp tương thích:

~~~bash
git checkout -b feature/profile
~~~

5. Cập nhật tài liệu onboarding để ghi rõ yêu cầu Git 2.23 trở lên nếu nhóm muốn dùng `switch`, hoặc cung cấp cú pháp cũ cho môi trường chưa nâng cấp.

6. Kiểm tra cùng lệnh trong terminal của IDE và CI để chắc chắn các môi trường được hỗ trợ dùng phiên bản phù hợp.

Ví dụ này cho thấy việc xác định đúng phiên bản và executable thường giải quyết được khác biệt mà không cần thay đổi repository.

## 11. Bảng tra cứu nhanh

| Nhu cầu | Lệnh |
| --- | --- |
| Xem phiên bản Git | `git --version` |
| Xem thông tin build | `git version --build-options` |
| Xem executable trên PowerShell | `Get-Command git -All` |
| Xem executable trên Command Prompt | `where.exe git` |
| Xem executable trên Bash | `type -a git` |
| Xem thư mục chương trình phụ trợ | `git --exec-path` |
| Xem Git directory | `git rev-parse --git-dir` |
| Xem gốc working tree | `git rev-parse --show-toplevel` |
| Trợ giúp tổng quát | `git --help` |
| Danh sách lệnh | `git help -a` |
| Danh sách hướng dẫn | `git help -g` |
| Trợ giúp ngắn của lệnh | `git <command> -h` |
| Tài liệu đầy đủ của lệnh | `git help <command>` |
| Tài liệu HTML nếu có | `git help -w <command>` |
| Xem cấu hình và nguồn | `git config --show-origin --list` |

## 12. Tổng kết

`git --version` cho biết phiên bản của executable mà shell đang gọi. Khi máy có nhiều bản Git, hãy kiểm tra đường dẫn bằng công cụ phù hợp với shell và kiểm tra riêng Git mà IDE hoặc CI sử dụng.

Trợ giúp tổng quát giúp khám phá lệnh; `git <command> -h` cung cấp cú pháp nhanh; `git help <command>` giải thích đầy đủ tùy chọn và hành vi. Trước khi dùng tính năng mới, hãy kiểm tra phiên bản và trợ giúp của chính môi trường thực tế.

Khả năng tương thích không chỉ phụ thuộc số phiên bản mà còn liên quan executable, hệ điều hành, shell, filesystem, cấu hình và môi trường CI. Khi viết hướng dẫn hoặc script cho nhóm, hãy công bố phiên bản tối thiểu cần thiết, kiểm tra tính năng có liên quan và cung cấp phương án thay thế đã được xác minh. Cách làm này giúp lệnh Git có thể lặp lại và nhất quán trên các môi trường phát triển khác nhau.

