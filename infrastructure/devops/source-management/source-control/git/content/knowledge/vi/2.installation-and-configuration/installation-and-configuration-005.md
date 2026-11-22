# Thiết lập tên, email và phân biệt tác giả với người tạo commit

Mỗi commit Git đều ghi lại thông tin người được ghi nhận là tác giả và người tạo commit. Hai vai trò này thường thuộc cùng một người khi bạn chạy `git commit` thông thường, nhưng có thể khác nhau khi một người nhận commit từ người khác, cherry-pick, rebase hoặc tạo lại lịch sử. Để lịch sử dự án chính xác, bạn cần cấu hình tên và email Git phù hợp, đồng thời hiểu rõ trường **Author** và **Committer** trong một commit.

Git dùng `user.name` và `user.email` làm identity mặc định khi tạo commit. Đây là metadata được ghi vào đối tượng commit; chúng không phải tên đăng nhập, mật khẩu hay cơ chế xác thực với máy chủ Git. Việc push thành công còn phụ thuộc thông tin xác thực và quyền truy cập remote.

## 1. Cấu hình tên và email cho Git

Thiết lập tên và email toàn cục cho người dùng hiện tại:

```bash
git config --global user.name "Nguyen Van An"
git config --global user.email "an@example.com"
```

Các giá trị này được dùng làm mặc định cho những repository của người dùng nếu không có cấu hình ở scope ưu tiên cao hơn.

Nếu một repository cần identity riêng, chuyển vào repository đó và cấu hình local:

```bash
git config --local user.name "An Nguyen - Company"
git config --local user.email "an.nguyen@company.example"
```

Cấu hình local được lưu trong `.git/config` của repository và chỉ áp dụng cho repository đó. Đây là lựa chọn phù hợp khi bạn dùng cùng một máy cho công việc công ty và dự án cá nhân.

Có thể mở file cấu hình để chỉnh sửa nhiều giá trị:

```bash
git config --global --edit
git config --local --edit
```

Ví dụ nội dung trong file cấu hình:

```ini
[user]
    name = Nguyen Van An
    email = an@example.com
```

Tên và email là chuỗi metadata. Bạn có thể dùng tên có dấu hoặc tên hiển thị theo quy ước nhóm; điều quan trọng là email nên là địa chỉ mà bạn muốn gắn với lịch sử commit. Nếu dùng GitHub hoặc nền tảng tương tự và muốn ẩn email cá nhân, có thể dùng địa chỉ noreply do dịch vụ cung cấp trong phần cài đặt tài khoản.

## 2. Phạm vi cấu hình và thứ tự ưu tiên

Git đọc cấu hình từ nhiều scope. Với cùng một khóa, giá trị ở scope ưu tiên cao hơn sẽ được dùng:

| Scope | Lệnh thiết lập | Phạm vi |
|---|---|---|
| System | `git config --system ...` | Toàn bộ người dùng trên máy; thường cần quyền quản trị |
| Global | `git config --global ...` | Người dùng hiện tại, áp dụng cho nhiều repository |
| Local | `git config --local ...` | Repository hiện tại |
| Worktree | `git config --worktree ...` | Worktree hiện tại khi repository bật extension `worktreeConfig` |
| Command | `git -c user.name="..." ...` | Chỉ lệnh Git được gọi với tùy chọn đó |

Trong các scope thông thường, thứ tự ưu tiên tăng dần là system, global, local, worktree và command. Các biến môi trường dùng để cung cấp author/committer identity có thể ghi đè identity được lấy từ cấu hình khi tạo commit.

Ví dụ, nếu global đặt email cá nhân nhưng repository công ty đặt email công ty ở local, commit trong repository công ty dùng email local:

```bash
# Giá trị mặc định của người dùng
git config --global user.email "an@example.com"

# Giá trị riêng của repository hiện tại
git config --local user.email "an.nguyen@company.example"

# Giá trị hiệu lực trong repository hiện tại
git config --get user.email
```

Không cần đặt `--global` cho mọi trường hợp. Hãy chọn scope nhỏ nhất phù hợp với ý định để tránh một identity công ty bị dùng nhầm cho repository cá nhân hoặc ngược lại.

## 3. Kiểm tra identity Git đang sử dụng

Xem riêng tên và email hiệu lực:

```bash
git config --get user.name
git config --get user.email
```

Để biết giá trị đến từ file cấu hình nào và scope nào, dùng:

```bash
git config --show-origin --show-scope --get-regexp '^user\.(name|email)$'
```

Lệnh này hữu ích khi có nhiều file cấu hình hoặc khi bạn không nhớ đã đặt identity ở global hay local. `--show-origin` cho biết nguồn file; `--show-scope` cho biết scope.

Để xem identity Git sẽ dùng làm author và committer trong môi trường lệnh hiện tại:

```bash
git var GIT_AUTHOR_IDENT
git var GIT_COMMITTER_IDENT
```

Hai lệnh này giúp phát hiện trường hợp cấu hình có vẻ đúng nhưng biến môi trường đang ghi đè identity. Chúng hiển thị identity cùng timestamp mà Git tính cho vai trò tương ứng.

Nếu muốn yêu cầu Git không tự suy đoán identity từ tên người dùng hoặc hostname của máy khi chưa cấu hình rõ, có thể bật:

```bash
git config --global user.useConfigOnly true
```

Khi đó, Git yêu cầu identity phải được cung cấp rõ ràng qua cấu hình hoặc nguồn phù hợp; lệnh tạo commit sẽ báo lỗi nếu không có identity hợp lệ. Thiết lập này hữu ích trên máy dùng cho nhiều dự án hoặc trong môi trường tự động hóa.

## 4. Author và Committer khác nhau như thế nào?

Một đối tượng commit chứa hai nhóm thông tin danh tính:

- **Author:** người được ghi nhận là người tạo ra nội dung thay đổi.
- **Committer:** người hoặc tiến trình tạo đối tượng commit hiện tại và ghi nó vào lịch sử.

Khi bạn tự sửa mã nguồn và chạy `git commit`, Author và Committer thường giống nhau. Khi bạn nhận một commit do người khác viết rồi tạo lại commit đó trong repository của mình, hai vai trò có thể khác nhau.

Ví dụ, Linh viết một thay đổi và gửi patch cho An. An áp dụng patch rồi tạo commit trong repository:

```text
commit 8a31...
Author:    Linh Tran <linh@example.com>
Committer: Nguyen Van An <an@example.com>

    Add input validation
```

Linh là Author vì Linh tạo ra thay đổi. An là Committer vì An tạo commit object trong repository. Cách ghi này giữ thông tin đóng góp ban đầu và vẫn cho biết ai đã đưa thay đổi vào lịch sử hiện tại.

Author và Committer là metadata của commit. Chúng không chứng minh danh tính pháp lý hoặc quyền truy cập của một tài khoản. Bất kỳ ai có thể tạo commit đều có thể cung cấp chuỗi tên/email trong cấu hình hoặc biến môi trường; chữ ký commit là một cơ chế xác minh riêng.

## 5. Git lấy Author và Committer từ đâu?

Thông thường, Git lấy cả hai identity từ `user.name` và `user.email`. Khi tạo commit, Git có thể dùng các biến môi trường riêng cho từng vai trò:

| Vai trò | Biến môi trường ghi đè |
|---|---|
| Author | `GIT_AUTHOR_NAME`, `GIT_AUTHOR_EMAIL`, `GIT_AUTHOR_DATE` |
| Committer | `GIT_COMMITTER_NAME`, `GIT_COMMITTER_EMAIL`, `GIT_COMMITTER_DATE` |

Nếu biến môi trường của một trường được đặt, Git dùng giá trị đó cho trường tương ứng thay vì giá trị cấu hình thông thường. Vì vậy, một script CI có thể tạo commit với committer là bot trong khi giữ author của người đóng góp.

Ví dụ trong môi trường POSIX, có thể đặt identity riêng cho một lệnh:

```bash
GIT_AUTHOR_NAME="Linh Tran" \
GIT_AUTHOR_EMAIL="linh@example.com" \
GIT_COMMITTER_NAME="Release Bot" \
GIT_COMMITTER_EMAIL="release-bot@example.com" \
git commit -m "Apply reviewed patch"
```

Trong PowerShell, cách đặt biến môi trường tạm thời cho phiên hiện tại có cú pháp khác:

```powershell
$env:GIT_AUTHOR_NAME = "Linh Tran"
$env:GIT_AUTHOR_EMAIL = "linh@example.com"
$env:GIT_COMMITTER_NAME = "Release Bot"
$env:GIT_COMMITTER_EMAIL = "release-bot@example.com"
git commit -m "Apply reviewed patch"

# Xóa các biến sau khi dùng để tránh ảnh hưởng lệnh tiếp theo
Remove-Item Env:GIT_AUTHOR_NAME
Remove-Item Env:GIT_AUTHOR_EMAIL
Remove-Item Env:GIT_COMMITTER_NAME
Remove-Item Env:GIT_COMMITTER_EMAIL
```

Chỉ nên dùng override môi trường khi có lý do rõ ràng, chẳng hạn automation hoặc quy trình nhận patch. Nếu để các biến tồn tại trong terminal lâu hơn dự kiến, những commit sau có thể tiếp tục ghi identity ngoài ý muốn.

## 6. Tình huống Author và Committer thay đổi qua các thao tác

| Thao tác | Author thường được ghi | Committer thường được ghi |
|---|---|---|
| `git commit` thông thường | Identity hiện tại | Identity hiện tại |
| `git commit --author="..."` | Người được chỉ định qua `--author` | Identity hiện tại |
| `git cherry-pick <commit>` | Author của commit nguồn được giữ | Người thực hiện cherry-pick |
| `git rebase` phát lại commit | Author của commit gốc thường được giữ | Người thực hiện rebase |
| Tạo merge commit | Người tạo merge commit | Người tạo merge commit |
| `git commit --amend` | Thường giữ Author của commit cũ | Người tạo commit mới |

Các từ “thường” trong bảng nhấn mạnh rằng tùy chọn và biến môi trường có thể thay đổi kết quả. Ví dụ `--author`, `--reset-author`, `GIT_AUTHOR_*` hoặc `GIT_COMMITTER_*` có thể ghi đè hành vi mặc định.

### Cherry-pick

Khi cherry-pick commit của Linh vào nhánh do An quản lý, Git tạo commit mới trên nhánh hiện tại. Author thường vẫn là Linh; Committer là An. Điều này phản ánh việc Linh viết thay đổi còn An áp dụng commit vào dòng lịch sử mới.

```bash
git cherry-pick 8a31...
git show --format=fuller --no-patch HEAD
```

### Rebase

Khi rebase, Git phát lại các commit trên nền mới. Commit được tạo lại có OID mới; Author thường được giữ từ commit gốc, còn Committer được cập nhật theo người thực hiện rebase. Vì vậy, rebase có thể làm CommitDate thay đổi dù AuthorDate vẫn giữ nguyên.

### Amend

`git commit --amend` thay thế commit tip bằng một commit mới. Theo mặc định, Git giữ thông tin Author của commit cũ và cập nhật thông tin Committer. Nếu bạn muốn nhận mình là Author của commit mới, dùng `--reset-author`:

```bash
git commit --amend --reset-author --no-edit
```

Tùy chọn này đặt Author theo identity hiện tại và làm mới thời điểm author. Vì amend tạo commit mới, OID của commit thay đổi.

## 7. Chỉ định Author cho một commit

Nếu bạn đang áp dụng thay đổi do một người khác viết, có thể ghi nhận Author bằng `--author`:

```bash
git add src/validator
git commit --author="Linh Tran <linh@example.com>" -m "Add input validation"
```

Trong trường hợp này, Author là Linh; Committer vẫn lấy từ identity hiện tại của bạn hoặc nguồn ghi đè committer tương ứng.

Nếu muốn tạo commit mới và dùng identity hiện tại làm Author, kể cả khi đang amend hoặc dùng lại thông tin commit khác, có thể dùng `--reset-author` trong các ngữ cảnh Git hỗ trợ:

```bash
git commit --amend --reset-author --no-edit
```

Không tự ý đổi Author của người khác chỉ để làm lịch sử trông đồng nhất. Hãy giữ thông tin đóng góp đúng thực tế và tuân theo quy ước ghi nhận tác giả của dự án.

## 8. Đọc Author và Committer trong lịch sử

Để xem đầy đủ danh tính và ngày của commit hiện tại:

```bash
git show --format=fuller --no-patch HEAD
```

Kết quả có các trường Author, AuthorDate, Commit, CommitDate và thông điệp commit. `git log --pretty=fuller` cho phép xem thông tin tương tự trên nhiều commit:

```bash
git log --pretty=fuller -5
```

Nếu cần xem trực tiếp nội dung đối tượng commit:

```bash
git cat-file -p HEAD
```

Bạn sẽ thấy các dòng `author` và `committer` cùng timestamp và timezone. Đây là dữ liệu nằm trong commit object; Git không tra cứu lại cấu hình hiện tại để hiển thị lịch sử cũ.

Để chỉ in tên/email và ngày theo định dạng riêng:

```bash
git log -5 --format="%h | author=%an <%ae> | committer=%cn <%ce>"
git log -5 --format="%h | author-date=%aI | commit-date=%cI"
```

Các placeholder thường dùng:

| Placeholder | Nội dung |
|---|---|
| `%an`, `%ae` | Tên và email Author |
| `%cn`, `%ce` | Tên và email Committer |
| `%aI` | Author date theo định dạng ISO 8601 nghiêm ngặt |
| `%cI` | Committer date theo định dạng ISO 8601 nghiêm ngặt |
| `%h`, `%H` | OID rút gọn và đầy đủ của commit |

## 9. Sửa identity cấu hình sai

Nếu commit mới đang dùng sai tên hoặc email, hãy kiểm tra scope trước:

```bash
git config --show-origin --show-scope --get-regexp '^user\.(name|email)$'
git var GIT_AUTHOR_IDENT
git var GIT_COMMITTER_IDENT
```

Sau đó sửa đúng scope:

```bash
# Sửa mặc định cho người dùng
git config --global user.name "Nguyen Van An"
git config --global user.email "an@example.com"

# Hoặc chỉ sửa repository hiện tại
git config --local user.name "An Nguyen - Company"
git config --local user.email "an.nguyen@company.example"
```

Thay đổi cấu hình chỉ ảnh hưởng các commit tạo sau đó. Nó không tự sửa Author hoặc Committer trong những commit đã tồn tại.

Nếu commit sai identity chưa được chia sẻ, bạn có thể tạo lại commit bằng amend:

```bash
git config --local user.name "Nguyen Van An"
git config --local user.email "an@example.com"
git commit --amend --reset-author --no-edit
```

Lệnh này thay commit tip bằng commit mới và đặt Author theo identity hiện tại. Nếu chỉ cần thay Committer hoặc cần giữ Author gốc, không dùng `--reset-author`; hãy cân nhắc amend với cấu hình đúng và kiểm tra kết quả bằng `git show --format=fuller HEAD`.

Nếu commit đã push hoặc người khác đã dựa trên nó, việc sửa identity sẽ viết lại lịch sử. Hãy phối hợp với nhóm trước khi amend/rebase và cập nhật remote; không force-push một nhánh dùng chung chỉ để sửa metadata mà chưa thống nhất.

## 10. Identity Git không phải thông tin xác thực

`user.name` và `user.email` chỉ xác định thông tin được ghi trong commit. Chúng không cấp quyền đọc hoặc ghi repository. Việc xác thực với remote thường dùng credential manager, token, SSH key hoặc cơ chế của nền tảng lưu trữ.

Ví dụ, bạn có thể đặt `user.email` thành email công ty nhưng vẫn không push được nếu tài khoản chưa được cấp quyền. Ngược lại, bạn có thể có quyền push nhưng commit vẫn ghi email cá nhân nếu cấu hình Git đang dùng email đó.

Nếu nền tảng lưu trữ dùng email để liên kết commit với hồ sơ người dùng, hãy bảo đảm email trong commit là địa chỉ đã xác minh hoặc địa chỉ noreply hợp lệ của tài khoản. Điều đó giúp hiển thị đóng góp đúng hồ sơ, nhưng vẫn là cơ chế liên kết metadata, không thay thế xác thực.

## 11. Những nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu chính xác |
|---|---|
| Author và Committer luôn là cùng một người | Chúng thường giống nhau trong commit thông thường nhưng có thể khác khi cherry-pick, rebase, amend hoặc áp dụng patch. |
| `user.name` là username đăng nhập GitHub/GitLab | Đây là tên metadata trong commit, không phải tài khoản xác thực. |
| Đổi `git config user.email` sẽ sửa commit cũ | Không. Cấu hình chỉ ảnh hưởng commit tạo sau đó; commit cũ phải được tạo lại nếu cần sửa. |
| Cherry-pick luôn đổi Author thành người chạy lệnh | Thông thường cherry-pick giữ Author của commit nguồn và ghi người thực hiện là Committer. |
| Rebase chỉ đổi vị trí commit | Rebase tạo lại commit; OID và thông tin Committer thường thay đổi. |
| `--author` thay cả Author lẫn Committer | Nó chỉ chỉ định Author; Committer vẫn lấy từ identity hiện tại hoặc override riêng. |
| Email trong commit chứng minh người đó đã xác thực với remote | Không. Đây là metadata do người tạo commit cung cấp; quyền remote được kiểm tra bằng cơ chế xác thực riêng. |

## 12. Tự kiểm tra

1. **Lệnh nào đặt tên và email mặc định cho người dùng hiện tại?**
   - `git config --global user.name "..."` và `git config --global user.email "..."`.
2. **Muốn đặt identity riêng cho một repository, dùng scope nào?**
   - `--local`.
3. **Author và Committer khác nhau ở điểm nào?**
   - Author là người được ghi nhận tạo ra thay đổi; Committer là người hoặc tiến trình tạo commit object hiện tại.
4. **Khi cherry-pick commit của người khác, Author thường là ai?**
   - Author của commit nguồn; người chạy cherry-pick thường trở thành Committer.
5. **Lệnh nào xem Author và Committer của commit hiện tại?**
   - `git show --format=fuller --no-patch HEAD`.
6. **Đổi `user.email` có cập nhật email trong commit đã tạo không?**
   - Không. Cần tạo lại commit nếu muốn thay metadata của commit cũ.

## Kết luận

Thiết lập `user.name` và `user.email` đúng scope để commit mới mang identity phù hợp với repository. Dùng `git config --show-origin --show-scope`, `git var GIT_AUTHOR_IDENT` và `git var GIT_COMMITTER_IDENT` để kiểm tra giá trị hiệu lực. Author ghi nhận người tạo ra thay đổi; Committer ghi nhận người hoặc tiến trình tạo commit hiện tại. Hai vai trò có thể khác nhau khi cherry-pick, rebase hoặc amend. Identity này là metadata lịch sử, tách biệt với thông tin xác thực và quyền truy cập remote.
