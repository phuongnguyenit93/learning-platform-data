# Tích hợp trình so sánh và xử lý xung đột bên ngoài

Khi review thay đổi hoặc giải quyết merge conflict, việc chỉ xem diff dạng văn bản trong terminal đôi khi không đủ trực quan. Trình so sánh bên ngoài (diff tool) có thể hiển thị hai phiên bản cạnh nhau, tô màu dòng thay đổi và hỗ trợ so sánh thư mục. Trình xử lý xung đột bên ngoài (merge tool) có thể hiển thị phiên bản gốc, hai phía thay đổi và kết quả hợp nhất trong giao diện ba hoặc bốn vùng.

Git hỗ trợ tích hợp các công cụ này qua `git difftool` và `git mergetool`. Git chịu trách nhiệm xác định phiên bản cần so sánh, tạo các file tạm cần thiết và cập nhật index sau khi người dùng giải quyết conflict. Công cụ bên ngoài tập trung vào hiển thị và chỉnh sửa nội dung. Hiểu rõ vai trò của từng phần giúp ta cấu hình công cụ phù hợp, tránh ghi đè nhầm thay đổi và hoàn tất đúng quy trình merge hoặc rebase.

Trong dịch vụ quản lý mã nguồn Git, trình diff và merge tool giúp review chính xác hơn, giảm lỗi khi hòa giải thay đổi từ nhiều nhánh và hỗ trợ cộng tác trong nhóm. Công cụ cần được cấu hình nhất quán, có thể khởi chạy từ Git và trả kết quả theo cách Git hiểu được.

## 1. Diff tool và merge tool khác nhau thế nào?

| Công cụ | Mục tiêu | Đầu vào thường gặp | Có sửa file kết quả không? |
| --- | --- | --- | --- |
| Diff tool | So sánh hai phiên bản để review khác biệt | Bản local và bản remote/phiên bản khác | Thông thường không; chủ yếu để xem |
| Merge tool | Hòa giải các phiên bản đang xung đột | Base, local, remote và file kết quả | Có; người dùng chỉnh sửa file kết quả |

Diff tool trả lời câu hỏi “hai phiên bản khác nhau ở đâu?”. Merge tool giúp trả lời “nên kết hợp các thay đổi này thành nội dung cuối cùng như thế nào?”.

Git có hai lệnh tương ứng:

```bash
git difftool
git mergetool
```

`git difftool` là giao diện gọi một chương trình so sánh cho các cặp file do Git xác định. `git mergetool` gọi chương trình xử lý các file đang có conflict. Cả hai lệnh không tự quyết định thay đổi nào đúng; người review hoặc người giải quyết conflict vẫn phải hiểu ngữ cảnh và chọn kết quả phù hợp.

## 2. Các công cụ phổ biến

Một số công cụ đồ họa thường được dùng với Git:

| Công cụ | Nền tảng thường hỗ trợ | Điểm mạnh |
| --- | --- | --- |
| Visual Studio Code | Windows, macOS, Linux | Diff hai file, editor tích hợp và Merge Editor trong giao diện Source Control |
| Meld | Linux, Windows, macOS tùy gói cài | So sánh file/thư mục và hợp nhất ba chiều |
| KDiff3 | Windows, Linux, macOS tùy gói cài | Hiển thị ba phiên bản và kết quả hợp nhất |
| Beyond Compare | Windows, macOS, Linux | So sánh file/thư mục, nhiều định dạng và giao diện hợp nhất |
| P4Merge | Windows, macOS, Linux tùy phiên bản | So sánh và hợp nhất trực quan |
| Vimdiff | Nơi có Vim | So sánh ngay trong terminal, chia cửa sổ và chỉnh sửa nhanh |

Git cũng có thể dùng các công cụ dòng lệnh như `vimdiff`. Không bắt buộc phải chọn cùng một ứng dụng cho diff và merge; một nhóm có thể dùng VS Code để xem diff nhưng dùng KDiff3 hoặc Meld để giải quyết xung đột.

Trước khi cấu hình, cài công cụ và xác nhận lệnh chạy được từ terminal. Một số ứng dụng có thể cần thêm thư mục cài đặt vào `PATH` hoặc chỉ định đường dẫn thực thi trong Git config.

## 3. Kiểm tra các công cụ Git nhận diện

Xem danh sách diff tool Git biết cách gọi:

```bash
git difftool --tool-help
```

Xem danh sách merge tool:

```bash
git mergetool --tool-help
```

Danh sách thay đổi theo phiên bản Git và nền tảng. Một công cụ có trong danh sách không có nghĩa ứng dụng đã được cài trên máy; Git có thể nhận diện tên tool nhưng không tìm thấy executable khi chạy.

Xem cấu hình hiện tại:

```bash
git config --show-origin --get diff.tool
git config --show-origin --get merge.tool
git config --show-origin --get-regexp '^difftool\.'
git config --show-origin --get-regexp '^mergetool\.'
```

Các lệnh `--show-origin` cho biết giá trị đến từ cấu hình system, global hay local. Điều này hữu ích khi công cụ được cấu hình ở nhiều cấp và kết quả thực tế khác với điều ta mong đợi.

## 4. Cấu hình diff tool mặc định

Git lưu tên diff tool mặc định trong `diff.tool`. Ví dụ dùng Meld:

```bash
git config --global diff.tool meld
```

Hoặc dùng Vimdiff:

```bash
git config --global diff.tool vimdiff
```

Thiết lập chỉ áp dụng cho tài khoản hiện tại. Nếu muốn chỉ áp dụng cho repository đang làm việc, thay `--global` bằng `--local`.

Chạy diff tool:

```bash
git difftool
```

Git sẽ so sánh working tree với index theo ngữ cảnh mặc định. Có thể chỉ định hai commit hoặc revision:

```bash
git difftool main feature/payment
```

Lệnh này mở công cụ cho các file khác nhau giữa hai nhánh. Có thể giới hạn một đường dẫn:

```bash
git difftool main feature/payment -- src/PaymentService.java
```

### So sánh staged và unstaged changes

```bash
# Thay đổi trong working tree so với index
git difftool

# Thay đổi đã stage so với HEAD
git difftool --cached

# So sánh hai commit
git difftool HEAD~1 HEAD
```

Các cặp phiên bản tương ứng với cách dùng `git diff`: mặc định xem unstaged changes; `--cached` hoặc `--staged` xem thay đổi đã stage; hai revision xem sự khác biệt giữa các snapshot.

## 5. Cấu hình merge tool mặc định

Git lưu merge tool mặc định trong `merge.tool`. Ví dụ dùng Meld:

```bash
git config --global merge.tool meld
```

Hoặc KDiff3:

```bash
git config --global merge.tool kdiff3
```

Sau khi cấu hình, khi có conflict, chạy:

```bash
git mergetool
```

Git mở công cụ cho từng file đang xung đột. Nếu muốn chọn tool khác cho một lần chạy:

```bash
git mergetool --tool=kdiff3
```

Tùy chọn `--tool` không nhất thiết thay đổi cấu hình mặc định. Muốn lưu mặc định, cập nhật `merge.tool` bằng `git config`.

Nếu Git không tự tìm được executable, kiểm tra `PATH` hoặc cấu hình đường dẫn cụ thể cho tool theo tên cấu hình `mergetool.<tool>.path`. Ví dụ, khi Git cần gọi executable nằm ngoài `PATH`, có thể đặt đường dẫn tuyệt đối:

```bash
git config --global mergetool.kdiff3.path "/path/to/kdiff3"
```

Thay đường dẫn minh họa bằng vị trí thực tế của ứng dụng trên máy. Cú pháp đường dẫn và tên executable có thể khác nhau giữa Windows, macOS và Linux.

## 6. Dùng VS Code để xem diff

VS Code có giao diện so sánh file tích hợp. Nếu lệnh `code` đã có trong `PATH`, có thể cấu hình một diff tool tùy chỉnh:

```bash
git config --global diff.tool vscode
git config --global difftool.vscode.cmd 'code --wait --diff "$LOCAL" "$REMOTE"'
```

Git cung cấp hai biến môi trường cho lệnh diff tùy chỉnh:

- `$LOCAL`: phiên bản file ở phía local của phép so sánh.
- `$REMOTE`: phiên bản file ở phía còn lại của phép so sánh.

`--diff` yêu cầu VS Code mở hai file trong chế độ so sánh; `--wait` yêu cầu tiến trình CLI đợi tới khi cửa sổ diff đóng để Git quản lý vòng đời lệnh đúng cách.

Thử:

```bash
git difftool --tool=vscode HEAD~1 HEAD
```

Nếu Git hỏi xác nhận mở từng file, có thể điều chỉnh prompt cho diff tool:

```bash
git config --global difftool.prompt false
```

Chỉ tắt prompt khi đã quen với việc Git tự mở tất cả file khác nhau. Với thay đổi lớn, giữ prompt có thể giúp kiểm tra từng file trước khi mở.

## 7. Dùng VS Code Merge Editor để giải quyết conflict

VS Code cung cấp Merge Editor trong giao diện Source Control. Khi một file có conflict, mở file đó từ danh sách Merge Changes hoặc chọn thao tác mở trong Merge Editor. Giao diện hiển thị các thay đổi từ hai phía và kết quả hợp nhất, giúp người dùng chọn hoặc chỉnh sửa từng vùng.

Quy trình cơ bản:

1. Thực hiện merge hoặc rebase để Git phát hiện conflict.
2. Mở repository trong VS Code.
3. Trong Source Control, chọn file thuộc nhóm Merge Changes.
4. Mở Merge Editor nếu VS Code nhận diện được conflict.
5. Xem nội dung từ hai phía, chấp nhận các thay đổi phù hợp hoặc sửa trực tiếp kết quả.
6. Lưu file kết quả.
7. Kiểm tra diff và chạy test liên quan.
8. Stage file đã giải quyết bằng Source Control hoặc `git add`.
9. Tiếp tục merge/rebase theo trạng thái Git.

VS Code có thể hiển thị nút như Accept Current, Accept Incoming hoặc Accept Both. Tên và vị trí nút có thể thay đổi theo phiên bản và loại conflict. Không chọn hàng loạt chỉ để làm biến mất dấu conflict; cần hiểu nội dung hai phía trước khi chấp nhận.

Merge Editor là giao diện chỉnh sửa kết quả. Việc lưu file chưa tự hoàn tất merge hoặc rebase; Git vẫn cần file được stage và lệnh tiếp tục tương ứng.

## 8. Hiểu các phiên bản BASE, LOCAL, REMOTE và MERGED

Khi gọi một custom merge tool, Git có thể cung cấp các biến môi trường:

| Biến | Ý nghĩa |
| --- | --- |
| `$BASE` | Phiên bản cơ sở chung trước khi hai phía thay đổi |
| `$LOCAL` | Phiên bản phía hiện tại mà Git xem là local trong thao tác merge |
| `$REMOTE` | Phiên bản từ phía được đưa vào merge |
| `$MERGED` | Đường dẫn file kết quả mà tool cần ghi nội dung hợp nhất |

Trong một merge thông thường, `LOCAL` thường tương ứng nhánh đang đứng (ours), còn `REMOTE` tương ứng nhánh được merge vào (theirs). Tuy nhiên, khi rebase hoặc một số thao tác khác, ý nghĩa “ours/theirs” có thể gây nhầm lẫn vì Git đang replay commit lên một base mới. Hãy dựa vào thông báo Git và nội dung từng phiên bản thay vì mặc định `ours` luôn là nhánh feature của mình.

Với xung đột nội dung ba chiều, Git thường có:

- Base: nội dung tại điểm chung trước khi hai phía chỉnh sửa.
- Local: nội dung từ phía hiện tại.
- Remote: nội dung từ phía được tích hợp.
- Merged: kết quả cuối do người dùng hoặc tool tạo ra.

Một số công cụ hiển thị bốn vùng để người dùng xem cả ba đầu vào và kết quả. Công cụ hai chiều vẫn có thể dùng được, nhưng người giải quyết conflict phải tự đối chiếu base và hai phía để hiểu thay đổi.

## 9. Các stage của file đang conflict trong Git index

Khi một file có conflict, Git có thể lưu nhiều phiên bản trong index thay vì một entry stage bình thường. Ba stage quan trọng:

| Stage | Nội dung |
| --- | --- |
| `:1:path` | Base, phiên bản chung trước khi phân nhánh |
| `:2:path` | Ours, phía local/current trong thao tác hiện tại |
| `:3:path` | Theirs, phía incoming |

Xem các entry chưa hòa giải:

```bash
git ls-files -u
```

Xem từng phiên bản:

```bash
git show :1:src/PaymentService.java
git show :2:src/PaymentService.java
git show :3:src/PaymentService.java
```

Các lệnh này giúp kiểm tra dữ liệu đầu vào trước khi mở merge tool. Nếu conflict là add/add hoặc modify/delete, một số stage có thể không tồn tại; không phải file nào cũng có đủ cả stage 1, 2 và 3.

Khi chạy qua `git mergetool`, Git thường đánh dấu file đã giải quyết (stage) sau khi nhận diện tool hoàn tất thành công. Với custom tool, việc này phụ thuộc vào mã thoát, thay đổi của file kết quả và cấu hình `mergetool.<tool>.trustExitCode`. Nếu bạn mở Merge Editor trực tiếp từ IDE thay vì chạy `git mergetool`, hãy stage file sau khi kiểm tra kết quả:

```bash
git add src/PaymentService.java
```

`git add` thay các entry unmerged bằng một entry bình thường trong index. Kiểm tra:

```bash
git status --short
git ls-files -u
```

Nếu `git ls-files -u` không còn liệt kê file đã xử lý, các entry conflict của file đó đã được loại khỏi index. Vẫn cần review nội dung trước khi tiếp tục.

## 10. Cấu hình merge tool tùy chỉnh

Git cho phép định nghĩa command riêng khi tool chưa được tích hợp sẵn. Ví dụ cấu hình khái quát:

```bash
git config --global merge.tool mymerge
git config --global mergetool.mymerge.cmd 'my-merge-app "$LOCAL" "$BASE" "$REMOTE" --output "$MERGED"'
```

Đây là mẫu minh họa, không phải tên executable có sẵn. Cần thay `my-merge-app` bằng ứng dụng thật và điều chỉnh thứ tự tham số theo tài liệu của ứng dụng. Tool phải ghi kết quả cuối vào đường dẫn `$MERGED` và trả mã thoát phù hợp.

Một số thiết lập hữu ích:

```bash
git config --global mergetool.prompt true
git config --global mergetool.keepBackup true
git config --global mergetool.keepTemporaries false
```

- `mergetool.prompt`: hỏi trước khi mở từng file conflict.
- `mergetool.keepBackup`: giữ file backup `.orig` sau khi merge tool chạy thành công; mặc định thường là `true`.
- `mergetool.keepTemporaries`: giữ các file tạm mà Git tạo cho merge tool; mặc định thường là `false`.

Không nên tắt backup trước khi đã hiểu quy trình và có cách khôi phục khác. File `.orig` có thể hữu ích khi cần so sánh kết quả với nội dung trước khi chạy tool. Sau khi xác minh kết quả, có thể xóa backup theo chính sách workspace.

## 11. Kiểm soát cách Git tin kết quả merge tool

Git cần biết tool đã giải quyết conflict thành công hay chưa. Cấu hình `mergetool.<tool>.trustExitCode` điều khiển việc Git có tin mã thoát của tool hay không.

Ví dụ:

```bash
git config --global mergetool.meld.trustExitCode true
```

Khi `trustExitCode` là `true`, Git dựa vào mã thoát của chương trình để xác định kết quả. Nếu không bật tùy chọn này, Git kiểm tra thời gian sửa đổi của file kết quả; nếu file không được cập nhật, Git sẽ hỏi người dùng xác nhận việc merge có thành công hay không. Chỉ đặt `true` nếu ứng dụng trả mã thoát đáng tin cậy và chỉ trả thành công khi đã ghi kết quả hợp lệ.

Nếu tool đóng mà không ghi file kết quả, hoặc trả mã thoát thành công dù người dùng chưa giải quyết conflict, Git có thể cần kiểm tra thêm. Luôn xem nội dung `$MERGED`, `git status` và các entry unmerged trước khi tiếp tục.

## 12. Chạy difftool và mergetool với từng lựa chọn

Một số lệnh hữu ích:

```bash
# Chạy diff với tool mặc định
git difftool

# Chọn tool cụ thể cho lần chạy
git difftool --tool=meld HEAD~1 HEAD

# So sánh file đã stage
git difftool --cached

# Chạy merge tool với tool mặc định
git mergetool

# Chọn merge tool cụ thể
git mergetool --tool=kdiff3

# Mở từng file conflict theo prompt mặc định
git mergetool
```

`git difftool` có các tùy chọn tương tự `git diff` cho revision và pathspec. `git mergetool` chỉ xử lý file đang được Git ghi nhận là unmerged; nếu chưa có conflict, lệnh có thể không mở công cụ nào.

Muốn xem chi tiết cách gọi của phiên bản đang cài:

```bash
git help difftool
git help mergetool
```

## 13. Quy trình xử lý conflict bằng merge tool

Giả sử đang merge nhánh `feature/payment` vào `main`:

```bash
git switch main
git merge feature/payment
```

Nếu Git báo conflict, kiểm tra trạng thái:

```bash
git status
git diff --name-only --diff-filter=U
```

Mở merge tool:

```bash
git mergetool
```

Với mỗi file:

1. Đọc base để hiểu nội dung trước khi hai nhánh thay đổi.
2. So sánh local và remote, xác định mục tiêu của mỗi thay đổi.
3. Kết hợp nội dung hợp lệ vào vùng kết quả.
4. Kiểm tra import, cú pháp, điều kiện và các thay đổi liên quan.
5. Lưu file kết quả và đóng tool.

Sau khi xử lý:

```bash
git status --short
git diff
git diff --cached
git ls-files -u
```

Khi `git mergetool` nhận diện thao tác giải quyết thành công, Git thường đã stage file. Nếu mở Merge Editor trực tiếp trong IDE hoặc file vẫn còn unmerged, kiểm tra kết quả rồi stage thủ công:

```bash
git add src/PaymentService.java
```

Khi tất cả file đã được giải quyết và stage, kiểm tra lại rồi hoàn tất merge:

```bash
git status
git diff --check
git commit
```

Nếu Git đang ở trạng thái merge và đã chuẩn bị message, có thể dùng `git merge --continue` để hoàn tất theo quy trình hiện tại. `git commit` cũng có thể hoàn tất merge khi mọi conflict đã được giải quyết và stage. Không dùng `git commit` để bỏ qua kiểm tra test hoặc review.

## 14. Quy trình xử lý conflict trong rebase

Khi rebase, Git lần lượt áp dụng lại các commit của nhánh hiện tại lên base mới. Nếu có conflict:

```bash
git status
git mergetool
```

Giải quyết file, xác nhận trạng thái index rồi tiếp tục:

```bash
git status --short
git ls-files -u
git rebase --continue
```

Nếu bạn mở tool từ IDE thay vì gọi `git mergetool`, stage file đã giải quyết bằng `git add src/PaymentService.java`. Khi dùng `git mergetool`, Git thường stage file sau khi xác nhận tool hoàn tất thành công.

Nếu cần bỏ commit đang được replay:

```bash
git rebase --skip
```

Nếu muốn hủy toàn bộ phiên rebase và quay lại trạng thái trước khi bắt đầu:

```bash
git rebase --abort
```

Không nhầm `git mergetool` với lệnh tiếp tục rebase. Merge tool chỉ chỉnh sửa file và hỗ trợ loại bỏ trạng thái unmerged; `git rebase --continue` mới điều khiển tiến trình rebase.

Trong rebase, nhãn ours/theirs có thể ngược với trực giác của người mới: `ours` thường là base/upstream mà các commit đang được replay lên; `theirs` thường là commit feature đang được áp dụng. Hãy xem `git status`, `git show :2:path`, `git show :3:path` và thông báo rebase để xác định đúng phía.

## 15. Diff tool trong quy trình review code

Diff tool hữu ích trước khi commit, trước khi push và khi review pull request. Ví dụ:

```bash
# Xem thay đổi chưa stage
git difftool

# Xem thay đổi sẽ đi vào commit
git difftool --cached

# Xem thay đổi giữa branch hiện tại và main
git difftool origin/main...HEAD
```

Với `origin/main...HEAD`, Git so sánh từ merge base tới `HEAD`, thường hữu ích để xem thay đổi riêng của branch hiện tại so với nhánh nền. Kiểm tra đúng merge base nếu lịch sử có nhiều nhánh hoặc đã rebase.

Diff tool không thay thế kiểm tra test, lint, bảo mật hoặc review logic. Một diff có thể trông nhỏ nhưng thay đổi hành vi quan trọng; cần đọc ngữ cảnh gọi hàm, dữ liệu đầu vào và ảnh hưởng tới các module khác.

## 16. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể có | Cách xử lý |
| --- | --- | --- |
| Git báo không tìm thấy tool | Chưa cài ứng dụng hoặc executable không có trong `PATH` | Cài ứng dụng, kiểm tra lệnh chạy độc lập và cấu hình `*.path` nếu cần |
| `git difftool` chỉ mở editor thay vì chế độ diff | Command tùy chỉnh thiếu tùy chọn diff hoặc tham số file | Kiểm tra `difftool.<tool>.cmd` và cách truyền `$LOCAL`, `$REMOTE` |
| Git không đợi ứng dụng đóng | Command không dùng chế độ wait hoặc tiến trình cha kết thúc sớm | Dùng tùy chọn wait tương ứng của ứng dụng, ví dụ `--wait` của VS Code |
| `git mergetool` không mở file nào | Index không có entry unmerged | Kiểm tra `git status` và `git ls-files -u` |
| Merge tool mở sai phiên bản | Nhầm local/remote hoặc đang xử lý rebase | Kiểm tra base, stage 2/3 và thông báo Git trước khi chỉnh sửa |
| Đóng tool nhưng Git vẫn báo conflict | File kết quả chưa được stage hoặc tool chưa ghi `$MERGED` | Lưu kết quả, kiểm tra file và chạy `git add` |
| Git hỏi merge thành công dù tool báo thành công | `trustExitCode` chưa bật hoặc tool có mã thoát không rõ nghĩa | Xem cấu hình và xác nhận nội dung trước khi trả lời |
| File `.orig` còn lại | `mergetool.keepBackup` đang bật | Kiểm tra kết quả và xóa backup sau khi chắc chắn không cần |
| Merge kết thúc nhưng ứng dụng không chạy | Chọn nội dung hợp nhất sai hoặc thiếu thay đổi liên quan | Chạy test, xem diff và sửa kết quả trước khi hoàn tất |

## 17. Những nguyên tắc an toàn khi dùng công cụ bên ngoài

- Chỉ chạy tool đã cài từ nguồn tin cậy và được tổ chức cho phép.
- Kiểm tra đúng repository và đúng file trước khi xác nhận ghi kết quả.
- Giữ backup `.orig` hoặc bản sao khi chưa chắc kết quả hợp nhất.
- Không chấp nhận toàn bộ “ours”, “theirs” hoặc “both” nếu chưa hiểu ảnh hưởng.
- Không stage tất cả file bằng `git add .` khi còn file chưa được review.
- Sau khi merge, chạy test và `git diff --check` để phát hiện lỗi định dạng hoặc whitespace.
- Với file nhị phân, dùng công cụ có khả năng xem/merge định dạng đó; Git không thể tạo nội dung hợp nhất có ý nghĩa bằng merge text thông thường.
- Không mở file chứa secret trong công cụ có đồng bộ cloud hoặc plugin không được phê duyệt.

## 18. Checklist thiết lập cho nhóm

1. Chọn diff tool và merge tool được nhóm hỗ trợ.
2. Cài cùng phiên bản hoặc phiên bản tương thích trên máy thành viên.
3. Cấu hình `diff.tool` và `merge.tool` ở cấp phù hợp.
4. Nếu dùng custom command, kiểm tra đúng biến `$LOCAL`, `$REMOTE`, `$BASE`, `$MERGED`.
5. Bảo đảm tool chờ hoàn tất và trả mã thoát phù hợp.
6. Quy định có giữ file `.orig` hay không.
7. Hướng dẫn cách mở Merge Editor và stage file sau khi giải quyết.
8. Thống nhất rằng merge/rebase chỉ tiếp tục sau khi kiểm tra conflict và chạy test.

Không nhất thiết phải buộc mọi developer dùng cùng một GUI. Điều quan trọng là mọi người hiểu luồng Git, biết kiểm tra kết quả và không để tool tự động quyết định thay đổi về mặt nghiệp vụ.

## 19. Thực hành

Thực hiện trên repository thử nghiệm:

1. Cài một diff tool như VS Code, Meld hoặc KDiff3.
2. Cấu hình `diff.tool` và chạy `git difftool HEAD~1 HEAD`.
3. So sánh staged và unstaged changes bằng `git difftool --cached` và `git difftool`.
4. Tạo hai branch cùng sửa một vùng trong một file.
5. Merge hai branch để tạo conflict.
6. Chạy `git status` và `git ls-files -u` để xem trạng thái unmerged.
7. Mở conflict bằng `git mergetool` hoặc Merge Editor của VS Code.
8. Xem base, local, remote và kết quả; tự kết hợp nội dung.
9. Lưu file, stage bằng `git add` và xác nhận `git ls-files -u` không còn entry.
10. Chạy test rồi hoàn tất merge.
11. Lặp lại bài tập bằng rebase để nhận biết sự khác nhau giữa `git merge --continue` và `git rebase --continue`.

## 20. Tự kiểm tra kiến thức

1. `git difftool` và `git mergetool` phục vụ hai mục tiêu gì?
2. Cấu hình `diff.tool` và `merge.tool` khác nhau ra sao?
3. `$LOCAL`, `$REMOTE`, `$BASE` và `$MERGED` đại diện cho những file nào?
4. Vì sao cần tùy chọn `--wait` khi tích hợp một số editor?
5. Git index lưu các stage nào khi file đang conflict?
6. Vì sao lưu file trong Merge Editor chưa hoàn tất merge?
7. `mergetool.<tool>.trustExitCode` ảnh hưởng tới cách Git xác nhận kết quả như thế nào?
8. Vì sao cách hiểu ours/theirs cần cẩn thận khi rebase?
9. Khi nào nên giữ file `.orig`?
10. Sau khi giải quyết conflict, cần kiểm tra và chạy lệnh nào trước khi tiếp tục merge hoặc rebase?

## Kết luận

`git difftool` tích hợp Git với trình so sánh để review hai phiên bản; `git mergetool` chuyển các file đang conflict tới công cụ hòa giải nội dung. Cấu hình `diff.tool`, `merge.tool` và các thiết lập `difftool.*`/`mergetool.*` giúp Git gọi đúng ứng dụng. Khi giải quyết xung đột, hãy hiểu base, local, remote và file kết quả, lưu rồi stage nội dung đã xác minh, sau đó mới tiếp tục merge hoặc rebase. Công cụ giúp hiển thị và chỉnh sửa; quyết định nội dung đúng vẫn thuộc về người thực hiện và cần được kiểm tra bằng diff, test và review.
