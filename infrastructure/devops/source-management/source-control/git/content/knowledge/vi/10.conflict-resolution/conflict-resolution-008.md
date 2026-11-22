# Sử dụng git mergetool và đánh dấu tệp đã giải quyết

Khi Git gặp xung đột, bạn cần tạo ra nội dung cuối cùng cho từng tệp trước khi tiếp tục merge, rebase hoặc cherry-pick. Có thể sửa trực tiếp các conflict marker trong trình soạn thảo, nhưng với nhiều vùng thay đổi hoặc nhiều tệp, công cụ hợp nhất trực quan giúp so sánh các phiên bản và chọn từng phần dễ hơn. Git gọi quy trình này là **mergetool**.

Sau khi nội dung đã đúng, Git cần biết tệp đó được giải quyết. Việc này được ghi nhận trong index, thường thông qua `git mergetool` hoặc lệnh `git add`. Chỉ đóng cửa sổ công cụ hoặc xóa các dấu `<<<<<<<`, `=======`, `>>>>>>>` trong tệp chưa đủ để kết thúc một conflict.

## 1. Mergetool làm gì?

Một conflict ba phía thường có ba phiên bản đầu vào:

- **BASE**: phiên bản cơ sở chung trước khi hai phía thay đổi.
- **LOCAL**: phiên bản từ phía hiện tại của thao tác, thường tương ứng với stage 2 (ours).
- **REMOTE**: phiên bản từ phía được đưa vào, thường tương ứng với stage 3 (theirs).
- **MERGED**: tệp kết quả mà bạn chỉnh sửa để chứa nội dung hợp nhất.

BASE, LOCAL và REMOTE là các đầu vào để so sánh. MERGED là kết quả cuối cùng. Trong công cụ hai phía hoặc ba phía, cách bố trí giao diện có thể khác nhau; hãy xác định vùng kết quả và lưu kết quả đó trước khi đóng công cụ.

Cách hiểu LOCAL và REMOTE cũng phụ thuộc thao tác:

| Thao tác | LOCAL / phía hiện tại | REMOTE / phía được đưa vào |
|---|---|---|
| Merge | Nhánh đang checkout khi chạy merge | Nhánh được merge vào |
| Rebase | Nền mới tại HEAD, gồm upstream và các commit đã phát lại | Commit đang được rebase |
| Cherry-pick | Nhánh hiện tại nhận commit | Commit đang được cherry-pick |

Trong rebase, LOCAL thường là nền mới và REMOTE là commit đang được phát lại. Vì vậy, đừng chọn nội dung chỉ dựa vào chữ “local” hoặc “remote” trên giao diện. Nếu không chắc, kiểm tra stage của tệp bằng `git show :2:path/to/file` và `git show :3:path/to/file` trước khi quyết định.

Mergetool giúp bạn xem khác biệt, lấy một phần từ mỗi phía và biên tập kết quả. Công cụ không tự biết yêu cầu nghiệp vụ của chương trình; người giải quyết conflict vẫn phải hiểu thay đổi nào cần được giữ.

## 2. Chọn và cấu hình công cụ hợp nhất

Git hỗ trợ nhiều chương trình hợp nhất như Meld, KDiff3, Vimdiff, Neovim Diff, Beyond Compare hoặc các công cụ khác tùy hệ điều hành và cách cài đặt. Công cụ phải được cài trên máy và Git phải tìm thấy lệnh chạy của nó.

Liệt kê những công cụ Git nhận diện được:

```bash
git mergetool --tool-help
```

Bạn có thể chỉ định công cụ cho một lần chạy mà không thay đổi cấu hình:

```bash
git mergetool --tool=meld
```

Lệnh trên yêu cầu Git dùng Meld cho các tệp đang xung đột. Nếu chỉ muốn xử lý một tệp:

```bash
git mergetool --tool=meld -- src/config.yml
```

Thay `meld` bằng tên công cụ có trong danh sách trên máy của bạn. Nếu Git báo không tìm thấy công cụ, kiểm tra chương trình đã được cài đặt và đường dẫn thực thi có trong PATH chưa.

Nếu thường xuyên dùng cùng một công cụ trong repository hiện tại, lưu cấu hình cục bộ:

```bash
git config --local merge.tool meld
git config --get merge.tool
```

Cấu hình `--local` chỉ áp dụng cho repository hiện tại. Dùng `git config --global merge.tool meld` nếu muốn đặt công cụ mặc định cho mọi repository của tài khoản người dùng. Bạn cũng có thể bỏ qua cấu hình mặc định bằng cách truyền `--tool=<ten-cong-cu>` khi gọi `git mergetool`.

Một số tùy chọn cấu hình hữu ích:

| Cấu hình | Tác dụng |
|---|---|
| `merge.tool` | Chọn công cụ hợp nhất mặc định |
| `mergetool.<tool>.trustExitCode` | Cho Git tin mã thoát của công cụ để xác định việc hợp nhất thành công |
| `mergetool.prompt` | Điều khiển lời nhắc trước mỗi lần mở công cụ |
| `mergetool.keepBackup` | Giữ hoặc xóa bản sao lưu `.orig` sau khi hợp nhất |

Ví dụ, nếu công cụ Meld trên máy trả mã thoát đáng tin cậy khi người dùng hoàn tất việc hợp nhất, có thể cấu hình:

```bash
git config --local mergetool.meld.trustExitCode true
```

Chỉ bật tùy chọn này khi bạn đã biết hành vi mã thoát của công cụ. Nếu không, giữ mặc định để Git hỏi bạn xác nhận kết quả sau khi công cụ đóng. Git thường giữ bản sao lưu có đuôi `.orig`; đây là bản dự phòng của tệp trước khi hợp nhất. Kiểm tra các tệp này trước khi xóa hoặc thay đổi cấu hình `mergetool.keepBackup`.

## 3. Quy trình dùng mergetool

Giả sử bạn đang ở nhánh `main` và muốn hợp nhất nhánh `feature`:

```bash
git switch main
git merge feature
```

Nếu Git báo conflict, bắt đầu bằng việc xem trạng thái và danh sách tệp chưa giải quyết:

```bash
git status
git diff --name-only --diff-filter=U
```

Lệnh thứ hai chỉ liệt kê các đường dẫn còn trạng thái unmerged. Sau đó mở công cụ:

```bash
git mergetool --tool=meld
```

Git lần lượt mở các tệp đang xung đột bằng công cụ đã chọn. Với từng tệp:

1. So sánh BASE, LOCAL và REMOTE để hiểu phần nào thay đổi ở mỗi phía.
2. Xem ngữ cảnh xung quanh vùng conflict, gồm tên hàm, cấu hình liên quan và các đoạn gọi tới nó.
3. Chọn một phía cho từng vùng khi phù hợp, hoặc kết hợp các thay đổi thành kết quả mới.
4. Kiểm tra vùng MERGED để chắc chắn nó thể hiện đúng kết quả mong muốn.
5. Lưu tệp kết quả trong công cụ rồi đóng cửa sổ theo cách công cụ yêu cầu.

Một số công cụ có nút chọn toàn bộ một phía hoặc chọn từng hunk. Các nút này chỉ giúp sao chép nội dung; chúng không thay thế bước đọc và kiểm tra kết quả. Nếu hai thay đổi cùng cần được giữ, hãy kết hợp chúng thay vì chọn toàn bộ một phía.

Sau khi đóng công cụ, Git có thể hỏi:

```text
Was the merge successful [y/n]?
```

Nếu bạn đã kiểm tra và kết quả đúng, trả lời `y`. Khi Git tin mã thoát của công cụ, bước xác nhận có thể được quyết định tự động. Nếu kết quả chưa đúng hoặc bạn chưa lưu tệp, không xác nhận thành công; mở lại và tiếp tục chỉnh sửa.

## 4. Đánh dấu tệp đã giải quyết

Trong index, một tệp conflict thường có các phiên bản stage 1, stage 2 và stage 3. Khi kết quả được chấp nhận, Git thay các stage chưa hợp nhất bằng stage 0 chứa nội dung cuối cùng. Đây là ý nghĩa của việc **đánh dấu tệp đã giải quyết**.

`git mergetool` thường đưa tệp vào index khi công cụ được xác nhận thành công hoặc mã thoát được cấu hình để báo thành công. Tuy vậy, hãy kiểm tra trạng thái thực tế, vì cấu hình và hành vi của từng công cụ có thể khác nhau:

```bash
git status
git diff --name-only --diff-filter=U
```

Nếu tệp vẫn còn unmerged, hoặc bạn giải quyết thủ công sau khi công cụ đóng, hãy lưu nội dung cuối cùng rồi thêm tệp vào index:

```bash
git add -- src/config.yml
```

Nếu quyết định cuối cùng là xóa tệp, ghi nhận việc xóa bằng:

```bash
git rm -- src/obsolete-config.yml
```

Không dùng `git add` để đánh dấu một tệp đã xóa nếu đường dẫn không còn tồn tại; `git rm` thể hiện rõ kết quả xóa và cập nhật index.

Kiểm tra những tệp còn xung đột và phần nội dung đã stage:

```bash
git diff --name-only --diff-filter=U
git diff --cached -- src/config.yml
git diff --cached --check
git status
```

Nếu lệnh đầu tiên không còn liệt kê tệp nào, Git không còn trạng thái unmerged cho các đường dẫn đó. `git diff --cached` cho bạn xem nội dung đã đưa vào index; hãy đọc kỹ để tránh bỏ sót thay đổi hoặc vô tình giữ nội dung sai. `git diff --cached --check` kiểm tra các lỗi whitespace phổ biến trong phần đã stage.

Có thể kiểm tra trực tiếp index của một tệp:

```bash
git ls-files -u -- src/config.yml
```

Nếu tệp đã được giải quyết, lệnh này không còn in các stage chưa hợp nhất cho tệp đó. Khi cần xem lại các phiên bản trước khi giải quyết, dùng:

```bash
git show :1:src/config.yml
git show :2:src/config.yml
git show :3:src/config.yml
```

Các stage này chỉ tồn tại khi Git còn lưu phiên bản unmerged tương ứng. Với conflict add/add, modify/delete hoặc các tình huống không có đủ ba phía, một stage có thể không tồn tại.

## 5. Khi mergetool không xử lý được conflict

Mergetool đặc biệt hữu ích với tệp văn bản có thể so sánh theo dòng. Một số tình huống cần quyết định thủ công:

- **Tệp nhị phân:** công cụ diff văn bản có thể không hiển thị nội dung có ý nghĩa. Dùng ứng dụng phù hợp với định dạng tệp, chọn phiên bản cần giữ hoặc tạo lại tệp rồi ghi nhận kết quả.
- **Một phía xóa, phía kia sửa:** quyết định giữ nội dung đã sửa hay chấp nhận xóa. Nếu giữ, bảo đảm tệp có mặt với nội dung đúng rồi chạy `git add`; nếu xóa, chạy `git rm`.
- **Đổi tên hoặc di chuyển tệp:** xem toàn bộ thông báo trong `git status`, xác định đường dẫn cuối cùng và bảo đảm các tệp cũ/mới được xử lý đúng.
- **Công cụ đóng nhưng kết quả chưa hoàn chỉnh:** mở lại tệp hoặc sửa bằng trình soạn thảo, sau đó stage thủ công. Đừng xác nhận thành công chỉ để bỏ qua lời nhắc.

Nếu muốn tự chỉnh sửa conflict marker, mở tệp và tạo ra nội dung cuối cùng, ví dụ:

```text
<<<<<<< HEAD
timeout = 30
=======
timeout = 60
>>>>>>> feature
```

Có thể kết quả đúng là giữ một giá trị, nhưng cũng có thể cần một giá trị thứ ba theo yêu cầu của ứng dụng. Sau khi biên tập, xóa tất cả marker còn sót lại, lưu tệp và chạy:

```bash
git add -- path/to/file
```

Mergetool là phương tiện hỗ trợ so sánh và chỉnh sửa; quyết định cuối cùng vẫn phải được xác minh bằng nội dung trong working tree và index.

## 6. Tiếp tục thao tác sau khi đã giải quyết hết

Khi mọi tệp đã được xử lý, kiểm tra lại:

```bash
git status
git diff --name-only --diff-filter=U
git diff --cached
```

Đọc staged diff, chạy test hoặc build phù hợp với thay đổi, rồi tiếp tục đúng thao tác Git đang dừng:

```bash
# Nếu đang merge
git merge --continue

# Nếu đang rebase
git rebase --continue

# Nếu đang cherry-pick
git cherry-pick --continue
```

Rebase và cherry-pick có thể dừng ở một commit tiếp theo và phát sinh conflict mới. Khi đó, lặp lại quy trình kiểm tra, mở mergetool, lưu kết quả, stage tệp và tiếp tục.

Nếu cần hủy thao tác đang thực hiện, các lệnh tương ứng là:

```bash
git merge --abort
git rebase --abort
git cherry-pick --abort
```

Chỉ dùng lệnh abort khi bạn thực sự muốn hủy toàn bộ thao tác hiện tại. Nó không phải cách đánh dấu conflict đã giải quyết. Trước khi bắt đầu một thao tác tích hợp, hãy bảo toàn các thay đổi chưa commit để tránh làm mất công việc đang có.

## 7. Ví dụ đầy đủ

Quy trình dưới đây minh họa một lần merge dùng Meld. Giả sử Meld đã được cài đặt và Git nhận diện được công cụ này:

```bash
# Chuyển sang nhánh nhận thay đổi và bắt đầu merge
git switch main
git merge feature

# Xem các tệp đang xung đột
git status
git diff --name-only --diff-filter=U

# Mở công cụ hợp nhất cho các tệp conflict
git mergetool --tool=meld

# Kiểm tra trạng thái và phần nội dung đã stage
git status
git diff --name-only --diff-filter=U
git diff --cached

# Sau khi mọi conflict được giải quyết và đã kiểm tra
git merge --continue
```

Nếu một tệp chưa được stage sau khi đóng Meld, chỉnh sửa/lưu kết quả rồi dùng `git add -- path/to/file`. Nếu kết quả là xóa tệp, dùng `git rm -- path/to/file`. Chỉ chạy `git merge --continue` khi không còn đường dẫn unmerged và staged diff đã được xem lại.

## 8. Lỗi thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Git báo không tìm thấy mergetool | Công cụ chưa cài hoặc không có trong PATH | Cài công cụ, kiểm tra PATH và chạy lại `git mergetool --tool-help` |
| Đã đóng cửa sổ nhưng tệp vẫn conflict | Công cụ chưa lưu kết quả hoặc chưa được xác nhận thành công | Mở lại, lưu kết quả và kiểm tra `git status`; stage bằng `git add` nếu cần |
| Git hỏi kết quả hợp nhất có thành công không | Git không được cấu hình để tin mã thoát của công cụ | Chỉ trả lời có sau khi đã kiểm tra nội dung; chỉ cấu hình trustExitCode khi mã thoát đáng tin cậy |
| Tệp `.orig` xuất hiện | Git giữ bản sao lưu trước khi hợp nhất | Giữ lại trong lúc kiểm tra; xóa sau khi chắc chắn không cần khôi phục |
| Rebase chọn nhầm nội dung LOCAL/REMOTE | Nhầm phía của rebase với cách hiểu merge thông thường | Kiểm tra `git status`, stage 2/3 và commit đang được phát lại |
| `git merge --continue` vẫn báo conflict | Còn tệp unmerged hoặc một conflict mới chưa xử lý | Chạy `git diff --name-only --diff-filter=U` và xử lý các tệp còn lại |

## Kết luận

Dùng `git mergetool` để so sánh base và hai phía, tạo nội dung MERGED rồi lưu kết quả. Sau đó kiểm tra `git status` và staged diff để xác nhận Git đã ghi nhận tệp là resolved; nếu chưa, dùng `git add` hoặc `git rm` tùy kết quả cuối cùng. Khi tất cả conflict đã được xử lý, tiếp tục bằng lệnh tương ứng với merge, rebase hoặc cherry-pick.
