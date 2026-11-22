# Tạo bí danh (alias) cho các thao tác thường dùng

Khi làm việc với Git hằng ngày, bạn thường lặp lại các lệnh như git status, git log, git switch, git diff hoặc git restore. Git alias cho phép đặt tên ngắn cho những lệnh này để giảm thao tác gõ, giúp quy trình quen thuộc dễ nhớ và nhất quán hơn.

Ví dụ, thay vì gõ git status --short --branch, bạn có thể tạo alias st rồi dùng git st. Alias có thể là một lệnh Git đơn giản, một chuỗi lệnh Git có tham số cố định hoặc một shell command khi cần xử lý phức tạp hơn.

Alias chỉ là cách gọi tắt. Người dùng vẫn cần hiểu lệnh thật phía sau, đặc biệt với các alias có thể thay đổi lịch sử hoặc xóa dữ liệu.

## 1. Git alias hoạt động như thế nào?

Git đọc các mục trong section alias của file cấu hình để mở rộng lệnh viết tắt. Ví dụ:

~~~sh
git config --global alias.st "status --short --branch"
~~~

Sau khi tạo, có thể chạy:

~~~sh
git st
~~~

Git hiểu lệnh này tương đương:

~~~sh
git status --short --branch
~~~

Tên alias xuất hiện sau từ git. Vì vậy, git st là một lệnh Git alias; nó khác với alias của shell như gs, vốn được shell mở rộng trước khi gọi Git.

Alias thường được dùng để:

- Rút ngắn lệnh dài được dùng thường xuyên.
- Chuẩn hóa cách xem trạng thái và lịch sử.
- Đặt tên dễ nhớ cho các tổ hợp tùy chọn.
- Tạo lệnh trợ giúp cho quy trình riêng của nhóm.
- Gói một shell command nhỏ khi một lệnh Git đơn lẻ không đủ.

Git alias không làm thay đổi cách Git lưu commit, branch hoặc remote. Nó chỉ giúp gọi lệnh thuận tiện hơn.

## 2. Tạo alias ở các phạm vi cấu hình

Git hỗ trợ nhiều phạm vi cấu hình. Chọn phạm vi phù hợp để alias xuất hiện ở đúng nơi cần dùng.

### 2.1. Alias toàn cục cho người dùng

--global lưu cấu hình ở cấp người dùng. Alias thường có hiệu lực trong các repository mà người dùng đó làm việc:

~~~sh
git config --global alias.st "status --short --branch"
~~~

File cấu hình toàn cục thường là ~/.gitconfig hoặc file được chỉ định qua biến môi trường và cấu hình XDG. Không cần tự sửa file bằng tay; git config --global giúp Git ghi đúng định dạng.

### 2.2. Alias riêng cho một repository

--local lưu alias trong cấu hình của repository hiện tại, thường là .git/config:

~~~sh
git config --local alias.st "status --short --branch"
~~~

Alias local chỉ áp dụng cho repository đó trên máy hiện tại. File .git/config không được commit và không tự chia sẻ cho đồng đội khi clone.

### 2.3. Alias chỉ dùng một lần

Nếu chỉ cần thử một alias cho một lệnh, dùng -c:

~~~sh
git -c alias.st="status --short --branch" st
~~~

Cấu hình này chỉ tồn tại trong lần gọi Git đó. Nó hữu ích khi thử alias trước khi quyết định lưu ở cấp global hoặc local.

### 2.4. Chọn phạm vi nào?

| Phạm vi | Cách khai báo | Khi nên dùng |
|---|---|---|
| System | git config --system ... | Quản trị viên cấu hình chung cho máy |
| Global | git config --global ... | Alias cá nhân dùng trong nhiều repository |
| Local | git config --local ... | Alias chỉ phục vụ một repository trên máy hiện tại |
| Worktree | git config --worktree ... | Cấu hình riêng cho một worktree khi repository bật hỗ trợ worktree config |
| Command | git -c alias.name=... name | Thử nghiệm hoặc dùng một lần |

Với alias cá nhân, --global thường là lựa chọn thuận tiện. Nếu nhóm muốn mọi thành viên dùng chung một số lệnh, hãy ghi hướng dẫn hoặc cung cấp script cấu hình được review; không giả định alias local tự đi theo repository khi clone.

## 3. Tạo các alias cơ bản thường dùng

### 3.1. Xem trạng thái ngắn gọn

~~~sh
git config --global alias.st "status --short --branch"
~~~

Sử dụng:

~~~sh
git st
~~~

Lệnh này hiển thị trạng thái working tree theo dạng ngắn và branch hiện tại. Đây là alias hữu ích để kiểm tra nhanh trước khi commit, đổi branch hoặc đồng bộ.

### 3.2. Chuyển branch và tạo branch mới

~~~sh
git config --global alias.co switch
git config --global alias.cob "switch -c"
~~~

Sử dụng:

~~~sh
git co main
git cob feature/order-search
~~~

git co main tương đương git switch main; git cob feature/order-search tương đương git switch -c feature/order-search.

Nếu dự án còn phải hỗ trợ phiên bản Git cũ chưa có git switch, hãy cân nhắc alias dựa trên checkout hoặc thống nhất phiên bản Git tối thiểu cho nhóm.

### 3.3. Xem lịch sử dạng đồ thị

~~~sh
git config --global alias.lg "log --oneline --graph --decorate --all"
~~~

Sử dụng:

~~~sh
git lg
git lg --max-count=20
~~~

Alias này hiển thị commit trên các nhánh và tag với dạng đồ thị, giúp xem nhanh lịch sử phân nhánh và merge.

### 3.4. Xem commit gần nhất

~~~sh
git config --global alias.last "log -1 --stat"
~~~

Sử dụng:

~~~sh
git last
~~~

Kết quả cho biết commit mới nhất cùng thống kê file được thay đổi. Nếu cần xem đầy đủ nội dung commit, dùng git show.

### 3.5. Xem thay đổi đã stage

~~~sh
git config --global alias.dfs "diff --staged"
~~~

Sử dụng:

~~~sh
git dfs
~~~

Alias này tương đương git diff --cached, hiển thị phần thay đổi đã đưa vào staging area nhưng chưa commit.

### 3.6. Bỏ stage một file

~~~sh
git config --global alias.unstage "restore --staged --"
~~~

Sử dụng:

~~~sh
git unstage src/orders/order-service.ts
~~~

Lệnh này đưa nội dung của file trong index trở về trạng thái của commit hiện tại, đồng thời giữ nội dung đã sửa trong working tree. Nó giúp bỏ stage mà không xóa phần sửa chưa commit.

## 4. Bộ alias mẫu để bắt đầu

Có thể tạo một nhóm alias phổ biến bằng các lệnh:

~~~sh
git config --global alias.st "status --short --branch"
git config --global alias.co switch
git config --global alias.cob "switch -c"
git config --global alias.br "branch --sort=-committerdate"
git config --global alias.lg "log --oneline --graph --decorate --all"
git config --global alias.last "log -1 --stat"
git config --global alias.dfs "diff --staged"
git config --global alias.unstage "restore --staged --"
~~~

Sau đó có thể dùng:

~~~sh
git st
git co main
git cob feature/login
git br
git lg
git last
git dfs
git unstage README.md
~~~

Không cần tạo thật nhiều alias ngay từ đầu. Chọn một nhóm lệnh thường lặp lại, dùng thử trong vài ngày rồi điều chỉnh theo thói quen và quy ước dự án.

## 5. Alias có thể nhận tham số

Với alias gọi một lệnh Git thông thường, các tham số phía sau alias được chuyển tiếp cho lệnh đó.

Ví dụ:

~~~sh
git config --global alias.ls "log --oneline --decorate"
~~~

Gọi:

~~~sh
git ls -5
~~~

Git mở rộng thành lệnh log với tùy chọn giới hạn số commit. Tương tự, alias co có thể nhận tên branch hoặc commit:

~~~sh
git co release/2.x
~~~

Khi thiết kế alias, hãy chọn tên không gây nhầm lẫn với command có sẵn và kiểm tra cách Git chuyển tiếp tham số. Alias không cần tự phân tích tham số nếu lệnh Git phía sau đã hỗ trợ chúng.

## 6. Shell alias cho thao tác phức tạp hơn

Nếu giá trị alias bắt đầu bằng dấu chấm than, Git xem phần còn lại là shell command. Cách này cho phép chạy nhiều lệnh hoặc gọi một hàm shell.

### 6.1. Một shell alias chỉ đọc

Ví dụ tạo alias xem danh sách contributor:

~~~sh
git config --global alias.authors '!f() { git shortlog -sn --all "$@"; }; f'
~~~

Sử dụng:

~~~sh
git authors
git authors --since="2026-01-01"
~~~

Hàm f nhận tham số qua "$@" rồi chuyển tiếp cho git shortlog. Dùng dấu nháy kép quanh "$@" giúp giữ nguyên từng tham số, kể cả khi tham số có khoảng trắng.

Shell alias phù hợp khi cần:

- Kết hợp nhiều lệnh.
- Tính toán hoặc chuẩn hóa tham số.
- Gọi công cụ bên ngoài.
- Thực hiện thao tác có điều kiện.

Nếu một alias đơn giản chỉ gọi một lệnh Git, không cần thêm dấu chấm than.

### 6.2. Phân biệt Git alias và shell alias

| Tiêu chí | Git alias | Shell alias |
|---|---|---|
| Cách gọi | git st | gs |
| Nơi cấu hình | Git config | File cấu hình shell |
| Phạm vi | Theo system/global/local/worktree/command | Theo shell và môi trường người dùng |
| Chạy được từ script gọi Git? | Có, nếu Git config tương ứng có hiệu lực | Thường phụ thuộc shell đã nạp alias và chế độ tương tác |
| Có thể gọi lệnh Git? | Có | Có |

Ví dụ shell alias trong Bash:

~~~sh
alias gs='git status --short --branch'
~~~

Sau khi nạp cấu hình shell, có thể gõ gs. Trong khi đó, Git alias st được gọi bằng git st và được Git đọc từ cấu hình của nó.

Không nên nhầm hai cơ chế khi hướng dẫn đồng đội. Một người có Git alias global nhưng không có shell alias vẫn dùng được git st; ngược lại, shell alias gs không tự xuất hiện trong Git config.

## 7. Kiểm tra các alias đang có

Liệt kê các alias có hiệu lực:

~~~sh
git config --get-regexp "^alias\."
~~~

Xem alias cùng nguồn và phạm vi cấu hình:

~~~sh
git config --show-origin --show-scope --get-regexp "^alias\."
~~~

Kết quả giúp xác định alias đến từ file cấu hình nào và ở scope nào. Điều này hữu ích khi một alias được khai báo nhiều lần ở global và local.

Có thể xem một alias cụ thể:

~~~sh
git config --global --get alias.st
git config --local --get alias.st
~~~

Nếu lệnh trả về không có kết quả, alias có thể chưa được khai báo trong scope đó. Khi chẩn đoán, hãy kiểm tra các scope liên quan thay vì kết luận rằng alias không tồn tại ở mọi nơi.

## 8. Sửa và xóa alias

### 8.1. Sửa giá trị alias

Gọi lại git config với cùng key để cập nhật:

~~~sh
git config --global alias.st "status --branch"
~~~

Hoặc mở file cấu hình global:

~~~sh
git config --global --edit
~~~

Trong file cấu hình, alias thường nằm trong section:

~~~ini
[alias]
    st = status --short --branch
    lg = log --oneline --graph --decorate --all
~~~

Nên dùng git config khi có thể để Git xử lý escaping và định dạng. Nếu sửa trực tiếp, giữ đúng cấu trúc INI và tránh tạo nhiều giá trị trùng cho cùng alias ngoài ý muốn.

### 8.2. Xóa alias

Xóa alias ở global:

~~~sh
git config --global --unset alias.st
~~~

Xóa alias local của repository hiện tại:

~~~sh
git config --local --unset alias.st
~~~

Xóa ở một scope chỉ ảnh hưởng đến scope đó. Nếu alias vẫn tồn tại ở global, system hoặc worktree, nó có thể tiếp tục được Git nhận diện. Hãy dùng lệnh --show-origin --show-scope để tìm đúng nguồn trước khi xóa.

### 8.3. Thử thay đổi trước khi lưu lâu dài

Có thể chạy alias tạm bằng -c:

~~~sh
git -c alias.st="status --short --branch" st
~~~

Khi kết quả phù hợp, mới lưu bằng --global hoặc --local. Cách này hữu ích khi đang thử một alias có nhiều tùy chọn hoặc cần kiểm tra trên một repository cụ thể.

## 9. Thứ tự ưu tiên cấu hình và xung đột alias

Một alias có thể được khai báo ở nhiều scope. Với cấu hình đơn trị, giá trị từ scope có ưu tiên cao hơn sẽ được dùng. Thứ tự tổng quát từ thấp lên cao là:

1. System.
2. Global.
3. Local.
4. Worktree, nếu repository bật cấu hình worktree.
5. Command line qua git -c.

Ví dụ, nếu global khai báo:

~~~sh
git config --global alias.st "status --short"
~~~

nhưng repository hiện tại khai báo:

~~~sh
git config --local alias.st "status --short --branch"
~~~

thì khi ở repository đó, alias local sẽ được ưu tiên. Ở repository khác, alias global vẫn có thể được dùng.

Ngoài ra, Git command có sẵn được ưu tiên hơn alias cùng tên. Không thể dùng alias để thay thế hoặc ghi đè một lệnh Git built-in như status, commit hoặc switch. Hãy chọn tên viết tắt riêng như st, ci, co hoặc lg.

## 10. Nguyên tắc đặt tên alias dễ nhớ

Một bộ alias tốt nên ngắn nhưng vẫn dễ đoán. Có thể áp dụng các nguyên tắc:

- Dùng tên ngắn cho lệnh rất thường dùng như st, co, lg.
- Dùng tên có nghĩa cho thao tác ít phổ biến như unstage, authors.
- Giữ quy ước nhất quán giữa các repository.
- Không dùng tên dễ nhầm với command Git có sẵn.
- Không tạo nhiều alias gần giống nhau nhưng khác hành vi mà không giải thích.
- Ưu tiên alias chỉ đọc trước khi tạo alias thay đổi dữ liệu.
- Ghi lại alias có tham số mặc định hoặc tác động đặc biệt.

Tên alias là tùy chọn cá nhân, nhưng nên tránh những chữ viết tắt quá khó hiểu nếu bạn định chia sẻ cách làm cho đồng đội.

## 11. Cẩn trọng với alias có tác động phá hủy

Alias có thể rút ngắn cả những lệnh nguy hiểm. Ví dụ:

~~~sh
git config --global alias.hardreset "reset --hard"
~~~

Khi đó, git hardreset <commit> có thể làm mất các thay đổi chưa commit trong working tree và index. Alias ngắn khiến thao tác nguy hiểm dễ bị chạy theo thói quen.

Không nên tạo alias phá hủy nếu không có lý do rõ ràng. Nếu cần, hãy đặt tên thể hiện hậu quả, kiểm tra trạng thái trước khi chạy và hiểu chính xác phạm vi tác động.

Một số lưu ý:

- reset --hard có thể loại bỏ thay đổi chưa commit.
- clean -fd có thể xóa file và thư mục chưa được theo dõi.
- push --force có thể ghi đè lịch sử remote mà người khác đang dựa vào.
- Shell alias có thể chạy bất kỳ lệnh nào mà tài khoản người dùng được phép thực hiện.

Đặc biệt, không sao chép một shell alias từ nguồn không tin cậy rồi chạy ngay. Hãy đọc toàn bộ giá trị alias, kể cả các đoạn dùng dấu chấm than, trước khi lưu vào cấu hình.

## 12. Chia sẻ alias trong nhóm

Git alias global thuộc cấu hình cá nhân, còn alias local nằm trong .git/config. Cả hai đều không tự được chia sẻ như commit trong repository.

Nếu nhóm muốn chuẩn hóa một số alias:

1. Chọn một bộ alias nhỏ có ích cho nhiều thành viên.
2. Giải thích lệnh Git thật phía sau mỗi alias.
3. Đưa các lệnh thiết lập vào tài liệu onboarding hoặc script cấu hình được review.
4. Nêu rõ phiên bản Git tối thiểu nếu alias dùng lệnh hoặc tùy chọn mới.
5. Đảm bảo mọi người vẫn biết cách chạy lệnh Git gốc khi alias chưa được thiết lập.

Ví dụ phần hướng dẫn onboarding:

~~~sh
git config --global alias.st "status --short --branch"
git config --global alias.lg "log --oneline --graph --decorate --all"
git config --global alias.unstage "restore --staged --"
~~~

Không nên yêu cầu thành viên dùng một alias bí mật chỉ được cấu hình trên máy của người viết tài liệu. Tài liệu và quy trình CI nên dùng lệnh Git chuẩn hoặc hướng dẫn thiết lập alias rõ ràng.

## 13. Ví dụ sử dụng trong một phiên làm việc

Giả sử bạn thường xuyên kiểm tra branch, tạo branch tính năng, xem lịch sử và bỏ stage một file.

**Bước 1 — Tạo alias**

~~~sh
git config --global alias.st "status --short --branch"
git config --global alias.cob "switch -c"
git config --global alias.lg "log --oneline --graph --decorate --all"
git config --global alias.unstage "restore --staged --"
~~~

**Bước 2 — Kiểm tra repository**

~~~sh
git st
~~~

**Bước 3 — Tạo branch**

~~~sh
git cob feature/search
~~~

**Bước 4 — Xem lịch sử**

~~~sh
git lg --max-count=15
~~~

**Bước 5 — Bỏ stage một file nhưng giữ nội dung sửa**

~~~sh
git unstage src/search/search-service.ts
git st
~~~

Những alias này rút ngắn các lệnh lặp lại mà vẫn giữ nguyên hành vi của Git. Khi cần hiểu chính xác điều gì xảy ra, bạn có thể mở cấu hình hoặc chạy lệnh gốc tương ứng.

## 14. Checklist quản lý alias

**Khi tạo alias**

- [ ] Đã chọn đúng scope global, local hoặc command.
- [ ] Tên alias dễ nhớ và không trùng lệnh Git built-in.
- [ ] Đã hiểu lệnh Git thực tế phía sau.
- [ ] Đã thử alias trên repository phù hợp.
- [ ] Đã xem kỹ shell alias bắt đầu bằng dấu chấm than.

**Khi quản lý alias**

- [ ] Có thể liệt kê alias bằng git config --get-regexp "^alias\.".
- [ ] Biết nguồn cấu hình khi có alias trùng tên.
- [ ] Xóa đúng scope khi không còn cần alias.
- [ ] Không để alias phá hủy dữ liệu chạy theo thói quen.

**Khi chia sẻ với nhóm**

- [ ] Có tài liệu giải thích lệnh gốc.
- [ ] Có hướng dẫn thiết lập rõ ràng.
- [ ] Không giả định alias local/global tự đi theo repository.
- [ ] Không yêu cầu alias thay thế hiểu biết về Git command.

## 15. Kết luận

Git alias giúp rút ngắn các thao tác thường dùng và tạo cách làm nhất quán hơn. Bạn có thể lưu alias ở cấp global để dùng trong nhiều repository, local cho một repository hoặc command line để thử một lần. Alias đơn giản thường gọi trực tiếp một lệnh Git; alias bắt đầu bằng dấu chấm than có thể chạy shell command và cần được kiểm tra kỹ.

Hãy bắt đầu với các alias chỉ đọc như status, log và diff, sau đó thêm alias cho thao tác thường dùng như switch hoặc unstage. Luôn kiểm tra nguồn cấu hình, hiểu tác động của lệnh thật và ghi lại alias khi chia sẻ với nhóm. Alias tốt giúp thao tác nhanh hơn mà không làm người dùng quên điều Git thực sự đang thực hiện.
