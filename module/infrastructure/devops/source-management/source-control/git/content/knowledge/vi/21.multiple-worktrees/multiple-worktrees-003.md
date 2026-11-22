# Những dữ liệu được chia sẻ và dữ liệu riêng của mỗi worktree

Git worktree cho phép một repository có nhiều thư mục làm việc cùng lúc. Bạn có thể mở một worktree cho tính năng đang phát triển, một worktree khác cho nhánh sửa lỗi và một worktree nữa để review commit. Các worktree này dùng chung kho đối tượng và phần lớn tham chiếu Git, nhưng mỗi thư mục có working tree, index và `HEAD` riêng. Hiểu ranh giới đó giúp bạn biết thay đổi nào nhìn thấy ở mọi worktree, thay đổi nào chỉ tồn tại trong một thư mục và vì sao Git không cho checkout cùng một branch ở nhiều worktree thông thường.

## 1. Một repository có thể có nhiều worktree

Khi clone repository theo cách thông thường, bạn có một thư mục làm việc và thư mục quản trị `.git`. Với linked worktree, Git tạo thêm một thư mục làm việc nhưng vẫn dùng chung kho Git của repository ban đầu.

Ví dụ:

```text
workspace/
  project/                 worktree chính
    .git/                  thư mục quản trị chung
    src/
  project-hotfix/          linked worktree
    .git                    file trỏ tới metadata riêng của worktree
  project-review/           linked worktree
    .git                    file trỏ tới metadata riêng của worktree
```

Trong linked worktree, `.git` thường là một file văn bản chứa đường dẫn tới thư mục quản trị của worktree đó, thay vì một thư mục `.git` độc lập. Các metadata riêng được lưu dưới thư mục quản trị chung, thường ở `.git/worktrees/<id>/`. Cấu trúc thực tế có thể khác nếu repository dùng gitdir tùy chỉnh hoặc được tạo bởi công cụ quản lý khác; hãy dùng lệnh Git để truy vấn thay vì tự ghép đường dẫn.

Tạo worktree mới từ một branch có sẵn:

```bash
git worktree add ../project-hotfix hotfix/urgent-fix
```

Tạo branch mới đồng thời tạo worktree:

```bash
git worktree add -b feature/report ../project-report main
```

Tạo worktree ở trạng thái detached HEAD để review một commit cụ thể:

```bash
git worktree add --detach ../project-review <commit>
```

Các lệnh trên được chạy từ một worktree thuộc repository. Đường dẫn đích phải là vị trí phù hợp để Git tạo thư mục làm việc mới.

## 2. Dữ liệu nào được chia sẻ?

Các worktree thuộc cùng repository dùng chung phần dữ liệu cốt lõi sau:

| Dữ liệu chia sẻ | Ý nghĩa |
|---|---|
| Object database | Commit, tree, blob và tag object; nội dung đã lưu trong Git có thể được truy cập từ các worktree |
| Branch refs | Các nhánh local như `main`, `feature/report` là ref chung của repository |
| Tag refs | Các tag local như `v1.2.0` được chia sẻ |
| Remote-tracking refs | Các ref như `origin/main` được cập nhật khi fetch từ bất kỳ worktree nào |
| Cấu hình repository thông thường | Phần lớn cấu hình local trong common config được dùng chung |
| Stash stack | Các stash entry thuộc repository và có thể được xem từ worktree khác |
| Hooks và thông tin remote | Thường dùng cấu hình chung của repository, trừ khi được tùy chỉnh theo cơ chế phù hợp |

Ví dụ, khi chạy `git fetch origin` trong một worktree, Git cập nhật remote-tracking refs dùng chung. Một worktree khác có thể nhìn thấy `origin/main` mới ngay sau đó mà không cần fetch lần nữa.

Tương tự, commit được tạo trong một worktree trở thành đối tượng trong kho chung. Nếu commit được gắn vào một branch ref chung, worktree khác có thể nhìn thấy commit qua branch đó. Việc một commit tồn tại trong object database không đồng nghĩa mọi worktree tự chuyển sang commit đó; mỗi `HEAD` vẫn có trạng thái riêng.

Kiểm tra branch và tag từ các worktree:

```bash
git branch --all
git tag --list
git stash list
```

Danh sách branch, tag và stash phản ánh dữ liệu repository được chia sẻ, không phải bản sao riêng cho từng thư mục làm việc.

## 3. Dữ liệu nào thuộc riêng từng worktree?

Mỗi worktree có những trạng thái độc lập:

| Dữ liệu riêng | Ý nghĩa |
|---|---|
| Working tree | Các file và thư mục trên ổ đĩa trong worktree đó |
| Index | Vùng staging riêng; `git add` ở worktree này không stage file ở worktree khác |
| `HEAD` | Commit hoặc branch mà worktree hiện tại đang checkout |
| Trạng thái thao tác đang diễn ra | Trạng thái merge, rebase, cherry-pick hoặc revert đang tạm dừng |
| Một số pseudo-ref và ref quản lý worktree | Ví dụ trạng thái bisect hoặc rebase được lưu riêng theo worktree |
| Reflog của `HEAD` | Ghi lại chuyển động `HEAD` của worktree tương ứng |

Ví dụ, bạn sửa `src/App.java` trong `project-hotfix/` nhưng không đụng tới `project/`. Hai working tree có thể chứa hai phiên bản khác nhau của cùng một đường dẫn. Khi stage file trong `project-hotfix/`, index của `project/` vẫn không thay đổi.

Điều này cho phép bạn giữ công việc đang dang dở ở một worktree trong khi mở worktree khác để xử lý yêu cầu khẩn cấp. Bạn không cần stash hoặc commit chỉ để chuyển sang thư mục làm việc khác.

## 4. Vì sao một branch thường chỉ được checkout ở một worktree?

Branch refs được chia sẻ, trong khi mỗi worktree có index và working tree riêng. Nếu hai worktree cùng checkout một branch, mỗi nơi có thể tạo commit hoặc di chuyển branch tip theo trạng thái khác nhau. Điều đó dễ gây nhầm lẫn và làm mất tính nhất quán giữa branch với `HEAD` đang sử dụng.

Vì vậy, Git thông thường ngăn bạn checkout cùng một branch ở hai worktree cùng lúc. Ví dụ nếu `main` đang được checkout ở worktree chính, lệnh sau có thể bị từ chối:

```bash
git worktree add ../project-main-copy main
```

Git sẽ thông báo branch đã được checkout ở worktree khác. Hãy tạo worktree từ một branch khác hoặc dùng detached HEAD nếu mục đích chỉ là đọc/review một commit:

```bash
git worktree add --detach ../project-main-review main
```

Detached HEAD không tạo một branch mới. Nếu bạn tạo commit trong trạng thái này, hãy tạo branch để giữ commit trước khi xóa worktree hoặc chuyển sang trạng thái khác:

```bash
git switch -c review/experiment
```

Không nên tìm cách ép hai worktree cùng sử dụng một branch chỉ để tránh tạo branch riêng. Nếu cần chia sẻ tiến độ, hãy commit trên branch của worktree hiện tại và chuyển sang branch đó ở worktree phù hợp theo quy tắc Git.

## 5. Kiểm tra thư mục Git riêng và thư mục Git chung

Các lệnh sau giúp xác định worktree hiện tại đang dùng những thư mục quản trị nào:

```bash
git rev-parse --show-toplevel
git rev-parse --git-dir
git rev-parse --git-common-dir
```

- `--show-toplevel` trả về thư mục gốc của working tree hiện tại.
- `--git-dir` trả về thư mục Git dành cho worktree hiện tại.
- `--git-common-dir` trả về thư mục quản trị chung của repository, nơi lưu các dữ liệu được chia sẻ.

Trong worktree chính, `--git-dir` và `--git-common-dir` thường trỏ tới cùng thư mục `.git`. Trong linked worktree, `--git-dir` thường trỏ tới thư mục metadata riêng như `.git/worktrees/<id>`, còn `--git-common-dir` trỏ tới `.git` chung của repository.

Liệt kê các worktree đã đăng ký:

```bash
git worktree list
git worktree list --porcelain
```

Kết quả thường hiển thị đường dẫn, commit hiện tại và branch được checkout; định dạng porcelain phù hợp cho script vì có cấu trúc dễ phân tích hơn.

## 6. Cấu hình repository được chia sẻ theo mặc định

Thông thường, cấu hình local nằm trong common config và được dùng chung bởi mọi worktree. Ví dụ:

```bash
git config --local user.name
git config --local user.email
git config --local remote.origin.url
```

Khi cấu hình `remote.origin.url` hoặc thông tin user trong một worktree bằng `--local`, bạn đang thay đổi cấu hình chung của repository. Worktree khác cũng thấy giá trị mới.

Nếu cần một số cấu hình riêng cho từng worktree, Git hỗ trợ extension `worktreeConfig`. Khi extension này được bật, bạn có thể dùng `git config --worktree` để ghi vào file cấu hình riêng của worktree:

```bash
git config extensions.worktreeConfig true
git config --worktree user.name "Reviewer"
git config --worktree user.email "reviewer@example.com"
```

`--worktree` chỉ ghi vào file cấu hình riêng khi extension đã được bật; nếu chưa bật, nó có hành vi tương đương `--local` và tiếp tục ghi vào cấu hình chung. Việc bật extension làm thay đổi cách Git đọc cấu hình và có một số thiết lập cần được đặt đúng vị trí. Hãy đọc tài liệu Git về `extensions.worktreeConfig` trước khi bật trong repository đang dùng chung.

Không nên dùng cấu hình per-worktree để che giấu các thiết lập quan trọng cần thống nhất cho nhóm. Hãy dùng cấu hình chung cho remote, chính sách dự án và các thiết lập dùng chung; chỉ tách riêng khi có nhu cầu cụ thể như danh tính commit khác nhau giữa worktree review và worktree phát triển.

## 7. Trạng thái merge, rebase và cherry-pick được tách riêng

Một worktree có thể đang dừng ở giữa thao tác merge do conflict, trong khi worktree khác vẫn có thể dùng để đọc code hoặc làm việc trên branch khác. Trạng thái tạm dừng của thao tác được lưu riêng theo worktree, nên `git status` trong worktree đang conflict sẽ hiển thị thao tác đó; worktree khác không tự nhận trạng thái merge hoặc rebase này.

Ví dụ:

```text
project/          main, trạng thái sạch
project-hotfix/   hotfix/urgent-fix, merge đang dừng do conflict
project-review/   detached HEAD tại một commit, chỉ dùng để đọc
```

Trong tình huống này, hãy xử lý conflict trong `project-hotfix/` bằng các lệnh phù hợp như `git status`, sửa file, `git add` và `git merge --continue`. Không chạy `git merge --continue` từ worktree `project/`, vì worktree đó không có trạng thái merge đang dừng.

Các lệnh tiếp tục hoặc hủy thao tác phải chạy trong đúng worktree đã bắt đầu thao tác đó:

```bash
git rebase --continue
git rebase --abort
git cherry-pick --continue
git cherry-pick --abort
```

Trước khi thực hiện, dùng `git status` để xác nhận loại thao tác đang diễn ra và thư mục làm việc hiện tại.

## 8. Thay đổi ở một worktree có thể ảnh hưởng worktree khác như thế nào?

| Thao tác trong worktree A | Worktree B nhìn thấy gì? |
|---|---|
| Sửa một file chưa stage | Không thấy nội dung sửa trong working tree của B |
| Chạy `git add` | Index của B không đổi |
| Tạo commit trên branch đang checkout | Commit object được lưu trong kho chung; branch ref chung di chuyển |
| Fetch remote | Remote-tracking refs và object mới được chia sẻ |
| Tạo hoặc xóa tag local | Tag ref chung thay đổi, B nhìn thấy tên tag và đích mới/cũ |
| Tạo stash | Stash entry nằm trong repository chung và có thể liệt kê từ B |
| Đang merge/rebase conflict | Trạng thái thao tác riêng ở A; B không tự chuyển sang trạng thái đó |

Có một số tình huống cần chú ý. Nếu branch `feature/report` đang checkout ở worktree A, Git sẽ chặn việc checkout branch đó ở B theo cách thông thường. Tuy nhiên, các branch khác và tag vẫn được chia sẻ. Một thao tác fetch ở B có thể cập nhật `origin/main`, nên khi quay lại A, bạn thấy remote-tracking ref mới hơn dù chưa chạy fetch tại A.

## 9. Quản lý vòng đời worktree

Xem tất cả worktree:

```bash
git worktree list
```

Thêm worktree cho branch có sẵn:

```bash
git worktree add ../project-docs docs/update-guide
```

Tạo branch mới và worktree:

```bash
git worktree add -b feature/audit ../project-audit main
```

Gỡ một linked worktree khi không còn cần:

```bash
git worktree remove ../project-docs
```

Lệnh remove yêu cầu worktree sạch theo mặc định. Nếu còn thay đổi chưa commit, Git sẽ từ chối để tránh làm mất công việc. Hãy commit, stash hoặc sao lưu trước khi gỡ. Tùy chọn `--force` có thể bỏ qua một số bảo vệ; chỉ dùng khi đã kiểm tra rõ nội dung sẽ bị loại bỏ.

Nếu thư mục worktree đã bị xóa thủ công bên ngoài Git, metadata đăng ký có thể còn sót. Dọn các đăng ký không còn hợp lệ bằng:

```bash
git worktree prune --dry-run
git worktree prune
```

`--dry-run` liệt kê những metadata Git dự định prune mà chưa xóa. Chỉ chạy lệnh prune thật sau khi xác nhận đường dẫn không còn là worktree cần giữ. Nếu worktree nằm trên ổ đĩa ngoài hoặc thiết bị tạm thời và đang offline, có thể lock nó để tránh prune nhầm:

```bash
git worktree lock --reason "External review workspace" ../project-review
```

Mở khóa khi worktree sẵn sàng được quản lý lại:

```bash
git worktree unlock ../project-review
```

## 10. Ví dụ thực tế: phát triển tính năng và sửa lỗi song song

Bạn đang phát triển tính năng báo cáo trên branch `feature/report`. Đột nhiên nhóm yêu cầu sửa lỗi khẩn cấp ở `main`. Nếu chỉ có một working tree, bạn có thể phải commit tạm hoặc stash công việc đang làm. Với worktree, tạo một thư mục riêng cho hotfix:

```bash
git worktree add -b hotfix/report-crash ../project-hotfix main
```

Giờ bạn có hai thư mục:

```text
project/          feature/report
project-hotfix/   hotfix/report-crash
```

Trong `project-hotfix/`, sửa lỗi, chạy test và commit:

```bash
git status
git add src/main/ReportService.java
git commit -m "Fix report crash on empty input"
```

Branch `hotfix/report-crash` và commit mới là dữ liệu chung của repository. Trong `project/`, bạn vẫn thấy branch đó khi chạy `git branch --list`, nhưng working tree và index của `feature/report` vẫn giữ công việc đang làm.

Sau khi hotfix được tích hợp vào `main`, quay lại worktree tính năng và cập nhật nền theo quy trình nhóm, ví dụ fetch rồi merge hoặc rebase. Không cần chuyển đổi qua lại branch trong cùng một thư mục làm việc chỉ để xử lý hai luồng công việc.

## 11. Các nhầm lẫn thường gặp

- **Cho rằng mỗi worktree là một bản clone độc lập.** Chúng chia sẻ object database, refs và phần lớn cấu hình repository.
- **Cho rằng stage ở một worktree sẽ stage ở tất cả.** Mỗi worktree có index riêng.
- **Cho rằng file sửa trong working tree này tự xuất hiện trong working tree khác.** Nội dung chưa được commit vẫn nằm trong thư mục riêng.
- **Cho rằng branch local thuộc riêng một worktree.** Branch refs là dữ liệu chung; chỉ `HEAD` cho biết worktree hiện tại đang checkout branch nào.
- **Checkout cùng branch ở hai worktree.** Git thường ngăn việc này để tránh hai `HEAD` cùng điều khiển một branch ref.
- **Chạy lệnh tiếp tục merge/rebase ở sai thư mục.** Trạng thái thao tác thuộc worktree đã bắt đầu nó.
- **Xóa thư mục linked worktree bằng công cụ hệ điều hành rồi quên metadata.** Dùng `git worktree remove` hoặc kiểm tra trước khi `git worktree prune`.
- **Nghĩ cấu hình `--local` là riêng cho worktree.** Theo mặc định nó ghi vào common config; cần bật `extensions.worktreeConfig` mới có cấu hình riêng qua `--worktree`.

## 12. Quy trình xác định dữ liệu chia sẻ và dữ liệu riêng

Khi không chắc một trạng thái có ảnh hưởng đến worktree khác hay không, hãy kiểm tra:

1. Chạy `git rev-parse --show-toplevel` để xác định thư mục hiện tại.
2. Chạy `git rev-parse --git-dir` và `git rev-parse --git-common-dir` để phân biệt metadata riêng và chung.
3. Chạy `git worktree list --porcelain` để xem branch và commit của từng worktree.
4. Chạy `git status --short` trong từng worktree để kiểm tra working tree và index riêng.
5. Kiểm tra `git branch`, `git tag`, `git remote -v` và `git stash list` để xem refs/configuration dùng chung.
6. Nếu cần cấu hình riêng, xác nhận `extensions.worktreeConfig` trước khi dùng `git config --worktree`.
7. Trước khi remove hoặc prune, xác nhận worktree không còn thay đổi cần giữ và không phải thư mục đang tạm thời offline.

## 13. Ghi nhớ

Các worktree trong cùng repository chia sẻ object database, branch/tag refs, remote-tracking refs, stash và phần lớn cấu hình. Mỗi worktree có working tree, index, `HEAD` và trạng thái thao tác riêng. Git dùng quy tắc một branch chỉ được checkout ở một worktree thông thường để tránh nhiều nơi cùng điều khiển một branch ref. Dùng `git rev-parse` và `git worktree list` để xác định cấu trúc thực tế, rồi chọn đúng worktree khi stage, giải quyết conflict, tiếp tục thao tác hoặc dọn thư mục làm việc.
