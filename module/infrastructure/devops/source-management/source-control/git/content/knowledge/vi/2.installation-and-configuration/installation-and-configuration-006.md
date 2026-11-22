# Chọn trình soạn thảo, công cụ so sánh và công cụ xử lý xung đột

Git thường cần mở một trình soạn thảo để bạn viết thông điệp commit, sửa todo list khi interactive rebase hoặc nhập nội dung tag. Khi xem khác biệt giữa hai phiên bản, bạn có thể muốn dùng công cụ diff có giao diện trực quan. Khi merge hoặc rebase phát sinh xung đột, công cụ merge ba phía giúp so sánh thay đổi từ hai nhánh với phiên bản nền và tạo ra kết quả cuối cùng.

Git cho phép cấu hình riêng từng loại công cụ. Bạn có thể dùng VS Code làm editor, một công cụ diff chuyên dụng để review thay đổi và một merge tool để giải quyết conflict. Bài này hướng dẫn cách chọn, cấu hình, kiểm tra và sử dụng các công cụ đó trên repository cá nhân hoặc trong nhóm.

Bài học thuộc chương **Cài đặt và cấu hình** của module **SOURCE_CONTROL_GIT**. Module hướng dẫn Git từ working tree, staging area, commit và lịch sử đến branch, merge, rebase, remote và tag; đồng thời rèn cách cộng tác qua nhánh, giải quyết xung đột, truy tìm thay đổi và khôi phục thao tác sai mà vẫn bảo toàn lịch sử quan trọng. Cấu hình công cụ phù hợp giúp thao tác với thông điệp commit, review diff và xử lý xung đột nhất quán hơn.

## 1. Ba loại công cụ và vai trò của chúng

Git có thể gọi các chương trình bên ngoài để thực hiện những công việc khác nhau:

| Công cụ | Mục đích | Ví dụ thao tác Git |
|---|---|---|
| Editor | Soạn văn bản do Git yêu cầu | <code>git commit</code>, <code>git tag -a</code>, <code>git rebase -i</code> |
| Diff tool | Hiển thị khác biệt giữa hai phiên bản | <code>git difftool</code> |
| Merge tool | Kết hợp thay đổi từ các phía khi có xung đột | <code>git mergetool</code> |

Ba công cụ có thể là ba ứng dụng khác nhau hoặc cùng một ứng dụng. Chẳng hạn, VS Code có thể làm editor, hiển thị diff và hỗ trợ giải quyết conflict. Vim cũng có thể dùng để soạn thảo, xem diff và xử lý xung đột với chế độ vimdiff.

Không nên nhầm lẫn:

- Editor sửa nội dung văn bản mà Git yêu cầu bạn nhập.
- Diff tool giúp xem hai phiên bản khác nhau ở đâu; nó không tự quyết định phiên bản đúng.
- Merge tool giúp tạo kết quả kết hợp từ các phiên bản; người dùng vẫn phải kiểm tra và xác nhận nội dung cuối cùng.

## 2. Git chọn editor theo cấu hình nào?

Khi Git cần mở editor, nó tìm lệnh theo thứ tự ưu tiên phổ biến sau:

1. Biến môi trường <code>GIT_EDITOR</code>.
2. Cấu hình Git <code>core.editor</code>.
3. Biến môi trường <code>VISUAL</code>.
4. Biến môi trường <code>EDITOR</code>.
5. Editor mặc định của môi trường Git nếu các nguồn trên chưa được đặt.

Vì vậy, nếu bạn đã cấu hình <code>core.editor</code> nhưng Git vẫn mở chương trình khác, hãy kiểm tra xem <code>GIT_EDITOR</code> có đang ghi đè hay không.

Interactive rebase có thêm cấu hình riêng là <code>sequence.editor</code>. Cấu hình này quyết định editor dùng để sửa todo list của rebase. Nếu không đặt, Git dùng editor thông thường theo cấu hình hiện có.

## 3. Chọn editor cho commit và thông điệp Git

### Dùng VS Code

Nếu đã cài VS Code và lệnh <code>code</code> có trong PATH, cấu hình:

~~~bash
git config --global core.editor "code --wait"
~~~

Tùy chọn <code>--wait</code> yêu cầu lệnh CLI chờ đến khi cửa sổ/tài liệu được mở đóng lại. Nếu không có tùy chọn này, Git có thể tiếp tục quá trình commit khi bạn vẫn chưa hoàn tất thông điệp.

Kiểm tra:

~~~bash
git config --global --get core.editor
~~~

Thử tạo commit không kèm tùy chọn <code>-m</code>:

~~~bash
git commit
~~~

Git sẽ mở VS Code để bạn nhập thông điệp. Lưu và đóng tài liệu theo cách mà VS Code CLI nhận biết; Git tiếp tục khi editor kết thúc.

### Dùng Vim

~~~bash
git config --global core.editor "vim"
~~~

Trong Vim:

- Nhấn <code>i</code> để vào chế độ nhập.
- Viết thông điệp commit.
- Nhấn <code>Esc</code> để về chế độ lệnh.
- Gõ <code>:wq</code> rồi Enter để lưu và thoát.
- Gõ <code>:q!</code> nếu muốn thoát mà không lưu; Git sẽ không nhận được nội dung đã sửa.

### Dùng Nano

~~~bash
git config --global core.editor "nano"
~~~

Trong Nano, nhập thông điệp, nhấn <code>Ctrl+O</code> để lưu, Enter xác nhận tên file rồi <code>Ctrl+X</code> để thoát.

### Dùng Notepad trên Windows

Có thể dùng Notepad nếu Git nhận được lệnh:

~~~bash
git config --global core.editor "notepad"
~~~

Notepad phù hợp với nhu cầu soạn thông điệp đơn giản. Nếu editor mở bất đồng bộ hoặc Git không chờ đúng thời điểm, hãy dùng một lệnh khởi chạy có cơ chế chờ hoặc chọn VS Code với <code>--wait</code>.

### Dùng Notepad++

Nếu Notepad++ đã được cài và đường dẫn thực thi có trong PATH:

~~~bash
git config --global core.editor "notepad++ -multiInst -notabbar -nosession -noPlugin"
~~~

Tùy chọn khởi chạy phụ thuộc cách cài đặt và phiên bản Notepad++. Hãy kiểm tra Git có chờ editor đóng hay không trước khi dùng cấu hình này cho commit hoặc rebase. Có thể cần thêm tùy chọn chờ theo phiên bản ứng dụng.

## 4. Đặt editor chỉ cho một repository

Không phải dự án nào cũng cần cùng một editor. Bạn có thể đặt cấu hình local trong repository hiện tại:

~~~bash
git config --local core.editor "code --wait"
~~~

Lệnh này ghi vào cấu hình local của repository và có ưu tiên cao hơn cấu hình global khi không có biến môi trường ghi đè.

So sánh:

| Phạm vi | Lệnh | Tác động |
|---|---|---|
| System | <code>git config --system</code> | Áp dụng cho người dùng trên máy theo cấu hình hệ thống; thường cần quyền quản trị |
| Global | <code>git config --global</code> | Áp dụng cho các repository của người dùng hiện tại |
| Local | <code>git config --local</code> | Chỉ áp dụng cho repository hiện tại |
| Worktree | <code>git config --worktree</code> | Áp dụng cho worktree hiện tại khi repository bật cấu hình extension cần thiết |

Khi cần đặt cấu hình riêng cho một worktree, kiểm tra trước repository có bật <code>extensions.worktreeConfig</code> hay chưa. Không giả định mọi thiết lập local đều tự động được tách theo worktree.

## 5. Cấu hình editor riêng cho interactive rebase

Khi chạy:

~~~bash
git rebase -i HEAD~3
~~~

Git mở một todo list để bạn đổi <code>pick</code>, <code>reword</code>, <code>squash</code> hoặc các hành động khác. Bạn có thể chọn editor riêng cho danh sách này:

~~~bash
git config --global sequence.editor "code --wait"
~~~

Hoặc dùng Vim:

~~~bash
git config --global sequence.editor "vim"
~~~

Kiểm tra:

~~~bash
git config --show-origin --get sequence.editor
~~~

Để tạm thời dùng editor khác cho một lần chạy, có thể đặt biến môi trường <code>GIT_SEQUENCE_EDITOR</code> trong phiên shell hiện tại. Biến này dành riêng cho editor của chuỗi lệnh rebase; nó không thay đổi editor commit mặc định.

## 6. Dùng biến môi trường để thay editor tạm thời

Biến môi trường hữu ích khi bạn muốn thử một editor mà không ghi cấu hình lâu dài.

Ví dụ trong Bash:

~~~bash
GIT_EDITOR="vim" git commit
~~~

Trong PowerShell:

~~~powershell
$env:GIT_EDITOR = "code --wait"
git commit
Remove-Item Env:GIT_EDITOR
~~~

Để thay editor cho todo list của interactive rebase:

~~~powershell
$env:GIT_SEQUENCE_EDITOR = "code --wait"
git rebase -i HEAD~3
Remove-Item Env:GIT_SEQUENCE_EDITOR
~~~

Biến môi trường trong PowerShell tồn tại trong phiên hiện tại cho đến khi bị xóa hoặc phiên kết thúc. Hãy xóa sau khi thử nếu không muốn nó tiếp tục ghi đè cấu hình.

## 7. Kiểm tra và gỡ cấu hình editor

Một số lệnh chẩn đoán:

~~~bash
# Xem giá trị và nguồn cấu hình
git config --show-origin --get core.editor
git config --show-origin --get sequence.editor

# Liệt kê các cấu hình editor liên quan
git config --show-origin --get-regexp '^(core|sequence)\.editor$'

# Xem biến môi trường trong Bash
env | grep -E '^(GIT_EDITOR|GIT_SEQUENCE_EDITOR|VISUAL|EDITOR)='
~~~

Trong PowerShell:

~~~powershell
Get-ChildItem Env:GIT_EDITOR, Env:GIT_SEQUENCE_EDITOR, Env:VISUAL, Env:EDITOR
~~~

Nếu muốn bỏ cấu hình local hoặc global để Git quay lại nguồn ưu tiên thấp hơn:

~~~bash
git config --local --unset core.editor
git config --global --unset core.editor
~~~

Chỉ chạy lệnh ở phạm vi bạn muốn thay đổi. Xóa cấu hình local không xóa cấu hình global; xóa global cũng không xóa biến môi trường đang ghi đè.

## 8. Diff tool dùng để làm gì?

Lệnh <code>git diff</code> hiển thị khác biệt dưới dạng văn bản ngay trong terminal. Đây là cách nhanh và phù hợp với hầu hết thay đổi mã nguồn:

~~~bash
# So sánh working tree với index
git diff

# So sánh index với commit hiện tại
git diff --staged

# So sánh hai commit
git diff main..feature/payment
~~~

Khi thay đổi lớn hoặc có nhiều tệp, một diff tool đồ họa có thể giúp đọc hai phía song song, điều hướng giữa các hunk và xem cấu trúc thư mục.

Git gọi công cụ diff bên ngoài bằng:

~~~bash
git difftool
~~~

Lệnh này hiển thị khác biệt theo công cụ đã cấu hình. Bạn có thể giới hạn phạm vi bằng pathspec hoặc chọn hai commit như khi dùng <code>git diff</code>.

## 9. Cấu hình diff tool

### Xem các công cụ được Git nhận diện

~~~bash
git difftool --tool-help
~~~

Danh sách phụ thuộc phiên bản Git và các ứng dụng được cài trên máy. Một số công cụ phổ biến là Vimdiff, Meld, KDiff3, Beyond Compare, Araxis và các trình so sánh khác.

### Dùng Vimdiff

~~~bash
git config --global diff.tool vimdiff
~~~

Sau đó:

~~~bash
git difftool
~~~

Vimdiff hiển thị hai phiên bản trong các cửa sổ chia đôi. Đây là lựa chọn phù hợp nếu bạn đã quen Vim và muốn làm việc ngay trong terminal.

### Dùng Meld

~~~bash
git config --global diff.tool meld
~~~

Git sẽ gọi Meld nếu ứng dụng đã được cài và có thể tìm thấy trong PATH. Tùy hệ điều hành và gói cài đặt, tên executable có thể khác; hãy xác nhận lệnh mở ứng dụng hoạt động từ terminal trước.

### Dùng VS Code làm diff tool

Bạn có thể khai báo một công cụ tùy chỉnh:

~~~bash
git config --global diff.tool vscode
git config --global difftool.vscode.cmd 'code --wait --diff "$LOCAL" "$REMOTE"'
~~~

Trong lệnh tùy chỉnh:

- <code>$LOCAL</code> là nội dung phía local mà Git đưa cho công cụ.
- <code>$REMOTE</code> là nội dung phía còn lại cần so sánh.
- <code>--diff</code> yêu cầu VS Code mở hai tệp ở chế độ so sánh.
- <code>--wait</code> giúp Git chờ công cụ kết thúc trước khi tiếp tục.

Các biến <code>$LOCAL</code> và <code>$REMOTE</code> là placeholder mà Git thay thế khi chạy difftool. Đừng tự đổi chúng thành đường dẫn cố định của máy bạn.

### Chạy diff tool một lần mà không đổi mặc định

~~~bash
git difftool --tool=vimdiff
git difftool --tool=meld
~~~

Nếu muốn gọi công cụ tùy chỉnh đã khai báo:

~~~bash
git difftool --tool=vscode
~~~

## 10. Các tùy chọn hữu ích của git difftool

| Tùy chọn | Tác dụng |
|---|---|
| <code>--tool=&lt;tool&gt;</code> | Chọn công cụ cho lần chạy hiện tại |
| <code>--tool-help</code> | Liệt kê các công cụ có thể dùng |
| <code>--no-prompt</code> | Không hỏi trước khi mở từng khác biệt |
| <code>--prompt</code> | Yêu cầu xác nhận trước mỗi lần mở công cụ |
| <code>--dir-diff</code> | So sánh theo thư mục thay vì mở từng cặp tệp |
| <code>--extcmd=&lt;command&gt;</code> | Chạy lệnh ngoài được chỉ định thay cho công cụ đã cấu hình |

Ví dụ:

~~~bash
# Mở diff tool mà không hỏi từng tệp
git difftool --no-prompt

# So sánh hai nhánh bằng công cụ đã cấu hình
git difftool main..feature/payment

# So sánh toàn bộ cây thư mục
git difftool --dir-diff main..feature/payment
~~~

Bạn có thể cấu hình để Git không hỏi mỗi lần:

~~~bash
git config --global difftool.prompt false
~~~

Nếu muốn hỏi lại, đặt thành <code>true</code> hoặc bỏ cấu hình để dùng mặc định.

## 11. Merge tool và xử lý xung đột

Merge tool hỗ trợ giải quyết conflict khi Git không thể tự kết hợp các thay đổi. Ví dụ, hai nhánh cùng sửa một vùng trong cùng một tệp:

~~~text
<<<<<<< HEAD
timeout = 30
=======
timeout = 60
>>>>>>> feature/performance
~~~

Đây là conflict marker trong working tree. Phần trên thường đại diện cho phía hiện tại (ours), phần dưới cho phía được tích hợp (theirs); dòng phân cách nằm giữa hai phía. Với rebase, ý nghĩa ours/theirs có thể gây nhầm vì nhánh đang được phát lại trên nền mới. Hãy đọc thông báo Git và xác định mục tiêu thay vì chỉ dựa vào tên.

Merge tool thường hiển thị ba phiên bản:

- **Base:** nội dung chung trước khi hai phía phân nhánh.
- **Local / ours:** nội dung của phía hiện tại trong thao tác merge.
- **Remote / theirs:** nội dung phía được tích hợp.

Ứng dụng sẽ giúp bạn xem các khác biệt và tạo tệp kết quả. Không phải công cụ nào cũng có cùng giao diện hoặc cách đặt tên ba phía.

## 12. Cấu hình merge tool

### Xem công cụ merge có sẵn

~~~bash
git mergetool --tool-help
~~~

Git có thể nhận diện các công cụ như Vimdiff, KDiff3, Meld, Beyond Compare, P4Merge, Araxis và một số ứng dụng khác tùy nền tảng.

### Dùng Vimdiff

~~~bash
git config --global merge.tool vimdiff
~~~

Khi xảy ra conflict:

~~~bash
git mergetool
~~~

Vimdiff mở các phiên bản để bạn so sánh và chỉnh sửa kết quả. Sau khi lưu và thoát, kiểm tra lại tệp trong working tree trước khi đánh dấu đã giải quyết.

### Dùng Meld

~~~bash
git config --global merge.tool meld
git mergetool
~~~

Meld thường cung cấp giao diện ba phía hoặc giao diện phù hợp với cấu hình được Git gọi. Hãy kiểm tra ứng dụng có sẵn trong PATH và xác nhận kết quả được ghi vào tệp mà Git yêu cầu.

### Dùng VS Code làm merge tool

Có thể khai báo một công cụ tùy chỉnh mở tệp kết quả trong VS Code:

~~~bash
git config --global merge.tool vscode
git config --global mergetool.vscode.cmd 'code --wait "$MERGED"'
~~~

<code>$MERGED</code> là đường dẫn tệp kết quả mà Git muốn công cụ chỉnh sửa. VS Code sẽ mở tệp có conflict markers; bạn có thể dùng các nút Accept Current, Accept Incoming, Accept Both hoặc mở Merge Editor để giải quyết. Sau khi chọn và lưu kết quả, đóng cửa sổ để Git tiếp tục.

Đây là cách gọi editor trên tệp đã merge. Nếu muốn giao diện ba phía chuyên dụng của một công cụ khác, hãy cấu hình đúng lệnh của công cụ đó và truyền các biến <code>$BASE</code>, <code>$LOCAL</code>, <code>$REMOTE</code>, <code>$MERGED</code> theo tài liệu của nó.

### Chọn merge tool cho một lần chạy

~~~bash
git mergetool --tool=vimdiff
git mergetool --tool=meld
~~~

Không cần thay cấu hình mặc định nếu chỉ muốn thử một công cụ.

## 13. Các biến mà Git truyền cho công cụ merge

Khi cấu hình custom merge tool, Git cung cấp các biến quan trọng:

| Biến | Ý nghĩa |
|---|---|
| <code>$BASE</code> | Tệp chứa phiên bản nền chung |
| <code>$LOCAL</code> | Tệp từ phía local/ours trong thao tác hiện tại |
| <code>$REMOTE</code> | Tệp từ phía được tích hợp/theirs |
| <code>$MERGED</code> | Tệp kết quả mà công cụ cần tạo hoặc cập nhật |

Một cấu hình custom có thể dùng cả bốn biến:

~~~bash
git config --global merge.tool custom
git config --global mergetool.custom.cmd 'my-merge-app "$BASE" "$LOCAL" "$REMOTE" "$MERGED"'
~~~

Thay <code>my-merge-app</code> bằng lệnh thực tế của công cụ đã cài. Cú pháp tham số phụ thuộc ứng dụng; hãy đọc tài liệu của ứng dụng trước khi dùng. Đừng giả định mọi công cụ đều nhận bốn đường dẫn theo cùng thứ tự.

## 14. Quy trình xử lý conflict với mergetool

Giả sử bạn đang merge nhánh tính năng vào nhánh hiện tại:

~~~bash
git switch main
git merge feature/payment
~~~

Nếu Git báo conflict:

~~~bash
# Xem danh sách tệp đang xung đột
git status

# Mở công cụ xử lý conflict
git mergetool
~~~

Sau khi công cụ kết thúc, kiểm tra trạng thái:

~~~bash
git status
git diff
git diff --staged
git diff --check
~~~

Nếu kết quả đúng, đánh dấu từng tệp đã giải quyết bằng <code>git add</code>. Nếu một tệp cần bị xóa theo kết quả merge, dùng <code>git rm</code>:

~~~bash
git add src/PaymentService.java
git rm src/LegacyPaymentAdapter.java
~~~

Sau đó xác nhận không còn đường dẫn unmerged:

~~~bash
git status
git diff --staged
~~~

Kết thúc merge bằng:

~~~bash
git merge --continue
~~~

Trong quy trình merge thông thường, Git có thể yêu cầu tạo merge commit bằng editor. Nếu không có yêu cầu đặc biệt, <code>git commit</code> cũng có thể hoàn tất merge khi tất cả conflict đã được giải quyết.

## 15. Kết thúc đúng quy trình nếu conflict xảy ra trong rebase hoặc cherry-pick

Merge tool chỉ giúp chỉnh nội dung tệp. Nó không quyết định thao tác Git cấp cao nào cần tiếp tục.

| Thao tác đang dở | Sau khi giải quyết conflict và stage tệp |
|---|---|
| Merge | <code>git merge --continue</code> hoặc hoàn tất merge bằng commit |
| Rebase | <code>git rebase --continue</code> |
| Cherry-pick | <code>git cherry-pick --continue</code> |

Nếu muốn hủy:

~~~bash
git merge --abort
git rebase --abort
git cherry-pick --abort
~~~

Chỉ chạy lệnh abort tương ứng với tiến trình đang thực hiện. Hãy xem <code>git status</code> để xác định Git đang ở trạng thái nào.

## 16. Các tùy chọn mergetool thường dùng

| Cấu hình / tùy chọn | Ý nghĩa |
|---|---|
| <code>merge.tool</code> | Công cụ merge mặc định |
| <code>mergetool.&lt;tool&gt;.cmd</code> | Lệnh tùy chỉnh để gọi công cụ |
| <code>mergetool.prompt</code> | Có hỏi trước khi mở công cụ hay không |
| <code>mergetool.keepBackup</code> | Có giữ file backup dạng <code>.orig</code> sau khi xử lý hay không |
| <code>mergetool.trustExitCode</code> | Có tin exit code của công cụ để xác định kết quả merge hay không |

Ví dụ không giữ file backup .orig sau khi xử lý:

~~~bash
git config --global mergetool.keepBackup false
~~~

Chỉ thay đổi thiết lập này nếu bạn đã có quy trình lưu và kiểm tra kết quả phù hợp. Trong giai đoạn học hoặc khi xử lý conflict phức tạp, giữ backup có thể hữu ích để đối chiếu.

Bạn có thể xem các cấu hình hiện tại và nguồn của chúng:

~~~bash
git config --show-origin --get merge.tool
git config --show-origin --get mergetool.keepBackup
git config --show-origin --get mergetool.prompt
git config --show-origin --get difftool.prompt
~~~

## 17. So sánh công cụ diff và merge

| Nhu cầu | Lệnh nên dùng | Kết quả |
|---|---|---|
| Xem thay đổi chưa stage | <code>git diff</code> | Diff dạng văn bản |
| Xem thay đổi đã stage | <code>git diff --staged</code> | Diff giữa index và HEAD |
| Mở ứng dụng so sánh hai phiên bản | <code>git difftool</code> | Mở diff tool |
| Xử lý tệp đang conflict | <code>git mergetool</code> | Mở merge tool |
| Xác nhận nội dung sẽ commit | <code>git diff --staged</code> | Kiểm tra snapshot trong index |
| Xác nhận conflict đã hết | <code>git status</code> | Kiểm tra trạng thái unmerged |

Diff tool không thay thế merge tool. Khi review một thay đổi bình thường, bạn cần so sánh hai phiên bản. Khi Git đang giữ trạng thái conflict, bạn cần tạo một nội dung kết quả hợp lệ rồi stage nó.

## 18. Cấu hình theo nhóm và repository

Một số dự án thống nhất editor, diff tool hoặc merge tool để mọi người có trải nghiệm tương tự. Tuy nhiên, cấu hình global thường phụ thuộc máy cá nhân và không nên giả định mọi thành viên đều cài cùng một ứng dụng.

Các cách phối hợp:

- Tài liệu hóa công cụ được nhóm khuyến nghị và cách cài đặt.
- Dùng tên công cụ phổ biến hoặc cấu hình custom có hướng dẫn rõ ràng.
- Chỉ lưu cấu hình repository khi nó không chứa đường dẫn tuyệt đối riêng của một máy.
- Đặt cấu hình global cho ứng dụng cá nhân và giữ cấu hình local cho những yêu cầu đặc thù của dự án.
- Kiểm tra các lệnh custom trên hệ điều hành mà nhóm hỗ trợ.

Không commit đường dẫn executable cá nhân như <code>C:/Users/.../App.exe</code> vào cấu hình dùng chung nếu các máy khác không có cùng cấu trúc. Với công cụ không có sẵn trên tất cả hệ điều hành, hãy cung cấp hướng dẫn thay thế.

## 19. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Git không mở editor mong muốn | <code>GIT_EDITOR</code> hoặc cấu hình ở cấp khác đang ghi đè | Kiểm tra biến môi trường và <code>git config --show-origin</code> |
| Commit kết thúc trước khi nhập xong | Editor mở bất đồng bộ, thiếu tùy chọn chờ | Dùng cơ chế chờ như <code>code --wait</code> |
| Interactive rebase mở editor khác | <code>sequence.editor</code> hoặc <code>GIT_SEQUENCE_EDITOR</code> đang được đặt | Kiểm tra cấu hình riêng của sequence editor |
| <code>git difftool</code> báo không tìm thấy ứng dụng | Công cụ chưa cài hoặc executable không nằm trong PATH | Cài ứng dụng, kiểm tra lệnh khởi chạy rồi cấu hình lại |
| VS Code diff mở một cửa sổ nhưng không so sánh | Lệnh custom thiếu <code>--diff</code> hoặc biến đường dẫn không đúng | Kiểm tra <code>difftool.&lt;tool&gt;.cmd</code> và hai placeholder |
| <code>git mergetool</code> không mở giao diện ba phía | Công cụ chỉ mở tệp kết quả hoặc custom command chưa truyền các phía | Kiểm tra cấu hình và tài liệu tham số của ứng dụng |
| Conflict vẫn còn sau khi đóng merge tool | Nội dung chưa được lưu hoặc chưa stage | Lưu tệp, kiểm tra marker, chạy <code>git add</code> rồi xem <code>git status</code> |
| Git tạo file <code>.orig</code> | Cấu hình giữ backup đang bật | Kiểm tra file để đối chiếu; thay <code>mergetool.keepBackup</code> nếu quy trình cho phép |
| Merge không tiếp tục sau khi giải quyết | Chưa đánh dấu tất cả tệp đã giải quyết hoặc đang ở thao tác khác | Chạy <code>git status</code> và dùng đúng lệnh continue |

## 20. Quy trình thiết lập gợi ý

Một cấu hình cá nhân dùng VS Code cho editor, diff và xử lý conflict có thể bắt đầu như sau:

~~~bash
# Editor cho commit và các thông điệp Git
git config --global core.editor "code --wait"

# Editor cho todo list của interactive rebase
git config --global sequence.editor "code --wait"

# Diff tool VS Code
git config --global diff.tool vscode
git config --global difftool.vscode.cmd 'code --wait --diff "$LOCAL" "$REMOTE"'

# Merge tool VS Code, mở tệp kết quả để giải quyết conflict
git config --global merge.tool vscode
git config --global mergetool.vscode.cmd 'code --wait "$MERGED"'
~~~

Sau khi cấu hình, kiểm tra:

~~~bash
git config --show-origin --get core.editor
git config --show-origin --get sequence.editor
git config --show-origin --get diff.tool
git config --show-origin --get merge.tool
~~~

Thử từng chức năng riêng:

~~~bash
git commit
git rebase -i HEAD~2
git difftool
git mergetool
~~~

Hai lệnh cuối chỉ có nội dung để mở khi repository đang có khác biệt hoặc conflict phù hợp. Nếu chưa có, hãy tạo một repository thử nghiệm để kiểm tra, tránh tạo xung đột không cần thiết trên dự án đang làm.

## 21. Bài tập tự kiểm tra

Thực hành trong một repository thử nghiệm:

1. Đặt <code>core.editor</code> thành VS Code với <code>--wait</code>, sau đó tạo commit không dùng <code>-m</code>.
2. Đặt <code>sequence.editor</code> riêng và chạy <code>git rebase -i HEAD~2</code>. Xác nhận todo list mở đúng editor.
3. Đổi editor tạm thời bằng biến môi trường, sau đó xóa biến và kiểm tra cấu hình trở lại.
4. Cấu hình Vimdiff làm diff tool và so sánh hai commit.
5. Cấu hình VS Code custom diff tool bằng <code>$LOCAL</code> và <code>$REMOTE</code>.
6. Tạo conflict trong repository thử nghiệm, cấu hình merge tool và mở bằng <code>git mergetool</code>.
7. Sau khi xử lý conflict, dùng <code>git status</code> và <code>git diff --staged</code> để xác nhận nội dung trước khi continue.
8. Giải thích khác biệt giữa editor, diff tool và merge tool.
9. Dùng <code>git config --show-origin</code> để tìm nguồn của một cấu hình đang ghi đè thiết lập bạn mong muốn.

Khi biết cách chọn editor, diff tool và merge tool độc lập, bạn có thể cấu hình Git phù hợp với cách làm việc của mình mà vẫn kiểm soát được nguồn cấu hình và kết quả thao tác. Hãy thử công cụ trong repository mẫu, kiểm tra nội dung sau mỗi lần giải quyết conflict và chỉ tiếp tục merge hoặc rebase khi Git xác nhận các tệp đã được xử lý đầy đủ.
