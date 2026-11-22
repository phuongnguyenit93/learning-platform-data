# Liệt kê, di chuyển và khóa worktree

Git worktree cho phép một repository có nhiều thư mục làm việc cùng lúc. Mỗi worktree có working tree, index và `HEAD` riêng, trong khi chia sẻ object database và phần lớn metadata của repository. Nhờ đó, bạn có thể mở một nhánh hotfix ở thư mục riêng trong khi tiếp tục làm việc trên nhánh feature ở thư mục chính.

Khi số worktree tăng lên, cần biết cách liệt kê chúng, di chuyển một worktree sang vị trí mới và khóa worktree khi thư mục tạm thời không khả dụng. Các lệnh này giúp quản lý metadata của worktree chính xác, tránh để Git hiểu nhầm một worktree còn cần dùng là đã bị xóa.

## 1. Worktree và metadata được tổ chức thế nào?

Một repository có thể có worktree chính và nhiều linked worktree. Ví dụ:

```text
project/
├── .git/
└── src/

project-hotfix/
├── .git        (file trỏ tới metadata của linked worktree)
└── src/

project-release/
├── .git        (file trỏ tới metadata của linked worktree)
└── src/
```

Thư mục `.git` của linked worktree thường là một file trỏ tới vùng metadata riêng của worktree bên trong Git directory dùng chung. Nó không phải một repository độc lập có object database riêng.

Mỗi worktree có trạng thái checkout riêng. Một branch thường chỉ được checkout trong một worktree tại một thời điểm, nhằm tránh hai thư mục cùng cập nhật một branch ref và gây mất thay đổi của nhau. Các object và lịch sử commit vẫn được chia sẻ giữa những worktree thuộc cùng repository.

Ví dụ:

```text
project/           -> main
project-hotfix/    -> hotfix/login
project-release/   -> release/2.x
```

Khi một branch đã được checkout ở worktree khác, lệnh `git switch` trong worktree hiện tại thường từ chối checkout branch đó. Bạn có thể dùng `git worktree list` để xác định branch đang nằm ở thư mục nào.

## 2. Liệt kê các worktree

Lệnh cơ bản:

```bash
git worktree list
```

Ví dụ kết quả:

```text
/work/project              a1b2c3d [main]
/work/project-hotfix       e4f5a6b [hotfix/login]
/work/project-release      9a8b7c6 [release/2.x]
```

Mỗi dòng cho biết đường dẫn worktree, commit hiện tại và branch đang được checkout. Nếu worktree ở trạng thái detached HEAD, Git hiển thị trạng thái detached thay vì tên branch.

Lệnh này hữu ích khi bạn cần trả lời các câu hỏi:

- Có bao nhiêu worktree đang được đăng ký?
- Worktree nào đang checkout branch cần tìm?
- Một worktree đang ở commit nào?
- Đường dẫn nào đang được dùng trước khi di chuyển hoặc dọn dẹp?

Để có đầu ra dễ xử lý bằng script, dùng chế độ porcelain:

```bash
git worktree list --porcelain
```

Đầu ra porcelain tách thông tin thành các trường như `worktree`, `HEAD`, `branch`, `detached`, `locked` và `prunable` khi phù hợp. Đây là định dạng ổn định hơn cho công cụ tự động so với việc phân tích văn bản hiển thị thông thường.

Ví dụ:

```text
worktree /work/project
HEAD a1b2c3d...
branch refs/heads/main

worktree /work/project-hotfix
HEAD e4f5a6b...
branch refs/heads/hotfix/login
locked Keep for release validation
```

Trong ví dụ này, worktree hotfix đã được khóa với lý do `Keep for release validation`. Phần `locked` mô tả trạng thái quản lý worktree, không có nghĩa branch bị khóa quyền commit hay thư mục trở thành chỉ đọc.

Nếu muốn lấy thông tin của một worktree cụ thể, có thể dùng các lệnh Git trong chính thư mục đó:

```bash
git -C /work/project-hotfix status
git -C /work/project-hotfix branch --show-current
git -C /work/project-hotfix rev-parse --short HEAD
```

Tùy chọn `-C` yêu cầu Git chạy như thể lệnh được gọi từ đường dẫn được chỉ định. Điều này hữu ích khi bạn đang đứng ở một thư mục khác nhưng muốn kiểm tra worktree kia.

## 3. Di chuyển linked worktree bằng git worktree move

Khi cần đổi vị trí thư mục, hãy dùng lệnh chuyên dụng:

```bash
git worktree move <worktree> <new-path>
```

Ví dụ, chuyển worktree hotfix sang thư mục lưu trữ worktree:

```bash
git worktree move ../project-hotfix ../worktrees/project-hotfix
```

Sau khi di chuyển thành công:

- Git chuyển thư mục linked worktree tới đường dẫn mới.
- Metadata liên kết được cập nhật để Git nhận diện vị trí mới.
- Branch và commit đang checkout vẫn được giữ nguyên.
- Các thay đổi trong working tree và index được giữ theo thư mục được di chuyển.

Kiểm tra lại danh sách:

```bash
git worktree list
git -C ../worktrees/project-hotfix status
```

Hãy bảo đảm thư mục đích chưa tồn tại và thư mục cha đã sẵn sàng. Dùng đường dẫn chính xác lấy từ `git worktree list` để tránh di chuyển nhầm worktree. Nếu đường dẫn có khoảng trắng, đặt đường dẫn trong dấu nháy phù hợp với shell.

Lệnh `git worktree move` chỉ dùng để di chuyển linked worktree. Không thể di chuyển worktree chính bằng lệnh này. Git cũng không hỗ trợ di chuyển linked worktree đang chứa submodule theo cách này; trong trường hợp đó, cần xử lý theo quy trình riêng của repository và submodule thay vì cố ép lệnh move.

Không dùng thao tác di chuyển thư mục bằng File Explorer hoặc lệnh hệ điều hành như cách mặc định. Nếu tự di chuyển bên ngoài Git, metadata có thể vẫn ghi đường dẫn cũ và worktree có thể bị xem là không còn khả dụng. Phần tiếp theo mô tả cách sửa liên kết trong tình huống đó.

## 4. Nếu đã di chuyển thư mục thủ công

Nếu thư mục worktree đã được di chuyển bằng công cụ hệ điều hành, Git có thể chưa biết đường dẫn mới. Khi đó, dùng:

```bash
git worktree repair <new-path>
```

Ví dụ, sau khi tự chuyển thư mục từ `../project-hotfix` sang `../worktrees/project-hotfix`, chạy lệnh repair từ repository chính:

```bash
git worktree repair ../worktrees/project-hotfix
```

Lệnh này cập nhật các liên kết metadata để Git nhận diện worktree tại vị trí mới. Nếu cấu trúc repository chính hoặc Git directory dùng chung cũng được di chuyển, `git worktree repair` có thể được chạy trong worktree chính để cập nhật metadata cho các linked worktree liên quan.

Sau khi repair, kiểm tra:

```bash
git worktree list
git -C ../worktrees/project-hotfix status
```

Nếu worktree vẫn không được nhận diện, kiểm tra file `.git` bên trong linked worktree có còn trỏ tới Git directory hợp lệ không và đường dẫn mới có đúng không. Không xóa metadata thủ công chỉ vì lệnh list đang hiển thị đường dẫn cũ; hãy xác định chính xác tình trạng liên kết trước.

Ưu tiên `git worktree move` khi bắt đầu di chuyển. `git worktree repair` là công cụ khôi phục liên kết sau khi có thay đổi đường dẫn bên ngoài Git hoặc khi metadata bị lệch.

## 5. Khóa worktree bằng git worktree lock

Một worktree có thể nằm trên ổ đĩa tháo rời, ổ mạng hoặc vị trí đôi khi không được kết nối. Khi đường dẫn đó tạm thời không truy cập được, Git có thể xem metadata worktree là stale và đưa nó vào danh sách có thể prune sau thời hạn cấu hình.

Để giữ metadata của worktree trong trường hợp này, dùng lệnh lock:

```bash
git worktree lock <worktree>
```

Bạn có thể ghi lý do khóa để người khác hiểu tại sao worktree cần được giữ lại:

```bash
git worktree lock --reason "Keep for release validation" ../worktrees/project-release
```

Lý do khóa được hiển thị trong đầu ra của `git worktree list` hoặc chế độ porcelain. Điều này hữu ích khi nhiều người cùng quản lý một repository có worktree trên các ổ đĩa hoặc môi trường khác nhau.

Một quy trình thường dùng với ổ đĩa ngoài:

1. Khi worktree còn truy cập được, kiểm tra `git status` và hoàn tất hoặc bảo toàn công việc đang làm.
2. Khóa worktree bằng `git worktree lock --reason "..." <path>`.
3. Ngắt kết nối ổ đĩa hoặc tạm thời làm đường dẫn không khả dụng.
4. Khi kết nối lại, kiểm tra `git worktree list` và tiếp tục làm việc.
5. Khi không còn cần bảo vệ khỏi prune, mở khóa bằng `git worktree unlock`.

Lệnh lock không khóa branch khỏi việc commit và không làm thư mục thành read-only. Nó đánh dấu linked worktree cần được giữ lại khi đường dẫn không khả dụng để Git không tự prune metadata. Trạng thái locked cũng ngăn các thao tác quản lý worktree thông thường di chuyển hoặc xóa worktree đó; hãy unlock trước khi cần move hoặc remove.

## 6. Mở khóa worktree

Khi worktree đã có thể truy cập ổn định và không còn cần bảo vệ khỏi prune, dùng:

```bash
git worktree unlock <worktree>
```

Ví dụ:

```bash
git worktree unlock ../worktrees/project-release
git worktree list --porcelain
```

Sau khi mở khóa, trường `locked` không còn xuất hiện cho worktree đó. Nếu đường dẫn sau này không còn tồn tại, metadata có thể được xem là stale và đủ điều kiện để prune theo thời hạn cấu hình.

Không mở khóa một worktree chỉ vì bạn không thấy nó trong File Explorer hoặc vì nó đang offline. Trước tiên, xác nhận với người phụ trách rằng worktree không còn cần được giữ lại, nhất là khi nó nằm trên ổ đĩa ngoài hoặc ổ mạng.

## 7. Phân biệt lock, prune và remove

Ba thao tác này có mục tiêu khác nhau:

| Lệnh | Mục đích | Tác động |
|---|---|---|
| `git worktree lock` | Bảo vệ metadata của worktree khỏi tự động prune khi đường dẫn không khả dụng | Ghi trạng thái locked và lý do tùy chọn; ngăn move/remove thông thường cho tới khi unlock |
| `git worktree unlock` | Bỏ trạng thái bảo vệ | Cho phép Git xem xét prune nếu worktree trở thành stale |
| `git worktree prune` | Dọn metadata của các worktree đã không còn tồn tại hoặc stale đủ điều kiện | Xóa thông tin quản lý stale trong Git directory |
| `git worktree remove` | Chủ động xóa một linked worktree | Xóa thư mục worktree và metadata tương ứng nếu đủ điều kiện |

`prune` không phải lệnh xóa các worktree đang hoạt động. Nó dọn metadata của những worktree mà Git xác định không còn hiện diện và không được bảo vệ bởi lock. `remove` là thao tác chủ động loại bỏ một linked worktree, vì vậy cần kiểm tra trạng thái và thay đổi chưa commit trước khi dùng.

Trước khi prune, có thể xem trước các mục sẽ bị dọn:

```bash
git worktree prune --dry-run --verbose
```

Nếu kết quả cho thấy một worktree bạn vẫn cần, hãy kiểm tra đường dẫn và lock state trước khi chạy prune thật. Có thể thực hiện prune sau khi xác nhận:

```bash
git worktree prune --verbose
```

Git cũng cho phép điều chỉnh thời hạn stale bằng `--expire`, ví dụ:

```bash
git worktree prune --dry-run --verbose --expire now
```

`--expire now` yêu cầu xem xét ngay các metadata stale đủ điều kiện. Chỉ dùng thời hạn này sau khi đã kiểm tra kỹ, vì thao tác prune thật có thể xóa metadata cần thiết để Git nhận diện worktree cũ.

Nếu muốn xóa hẳn một linked worktree đang tồn tại, hãy dùng `git worktree remove <path>` sau khi kiểm tra nó không còn công việc cần giữ. Đừng dùng `prune` để thay thế cho remove đối với một worktree vẫn đang tồn tại.

## 8. Quy trình quản lý nhiều worktree

Giả sử repository có worktree chính ở `../project`, worktree hotfix ở `../project-hotfix` và một worktree release trên ổ đĩa ngoài.

Có thể quản lý theo quy trình:

**Bước 1: Liệt kê và xác định branch.**

```bash
git worktree list
git worktree list --porcelain
```

Kiểm tra branch và commit ở từng đường dẫn trước khi di chuyển hoặc khóa.

**Bước 2: Kiểm tra thay đổi của worktree cần di chuyển.**

```bash
git -C ../project-hotfix status
git -C ../project-hotfix log --oneline -5
```

Bảo đảm các thay đổi đang làm dở được giữ lại và xác định worktree đó đang dùng branch nào.

**Bước 3: Di chuyển bằng Git.**

```bash
git worktree move ../project-hotfix ../worktrees/project-hotfix
```

**Bước 4: Khóa worktree nằm trên ổ đĩa ngoài.**

```bash
git worktree lock --reason "Release worktree on removable drive" /mnt/releases/project-release
```

Thực hiện lock khi đường dẫn còn truy cập được, trước khi ngắt kết nối ổ đĩa.

**Bước 5: Xác minh trạng thái.**

```bash
git worktree list --porcelain
git -C ../worktrees/project-hotfix status
```

**Bước 6: Khi không còn cần giữ worktree release, mở khóa và dọn dẹp theo chủ đích.**

```bash
git worktree unlock /mnt/releases/project-release
git worktree list
```

Nếu muốn xóa worktree đang tồn tại, dùng `git worktree remove` sau khi kiểm tra thay đổi. Nếu thư mục đã bị xóa hoặc không còn tồn tại, xem trước stale metadata bằng `git worktree prune --dry-run --verbose` rồi mới quyết định prune.

## 9. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Không checkout được branch | Branch đang được checkout ở worktree khác | Chạy `git worktree list` để tìm worktree đang sử dụng branch |
| `git worktree move` thất bại | Đường dẫn đích đã tồn tại, đang chọn worktree chính hoặc worktree có submodule | Kiểm tra nguồn/đích; chỉ move linked worktree đủ điều kiện |
| Git hiển thị đường dẫn cũ sau khi tự di chuyển thư mục | Metadata chưa được cập nhật | Chạy `git worktree repair <new-path>` |
| Worktree trên ổ ngoài bị đánh dấu prunable | Đường dẫn tạm thời không khả dụng và chưa lock | Kết nối lại hoặc lock worktree trước khi ngắt kết nối lần sau |
| Không mở khóa được worktree | Chọn sai đường dẫn hoặc metadata worktree không còn tồn tại | Xem `git worktree list --porcelain` và dùng đúng path |
| Prune đề xuất xóa metadata worktree | Git xác định worktree đã stale theo thời hạn | Dùng `--dry-run --verbose`, xác minh và lock nếu cần giữ |
| Worktree bị mất thay đổi khi remove | Working tree có thay đổi chưa được bảo toàn hoặc thao tác force được dùng | Kiểm tra status, commit/stash/copy công việc trước khi remove |

## 10. Checklist trước khi move, lock hoặc prune

Trước khi quản lý một worktree, hãy kiểm tra:

1. Worktree cần thao tác có phải linked worktree hay là worktree chính?
2. Đường dẫn hiện tại lấy từ `git worktree list` có chính xác không?
3. Worktree đang checkout branch nào và ở commit nào?
4. Có thay đổi chưa commit hoặc file untracked cần bảo toàn không?
5. Nếu di chuyển, đường dẫn đích đã sẵn sàng và chưa tồn tại chưa?
6. Nếu đường dẫn sẽ tạm thời offline, đã lock worktree với lý do rõ ràng chưa?
7. Nếu prune, đã xem trước bằng `--dry-run --verbose` chưa?

Các bước này giúp tránh di chuyển nhầm thư mục, làm mất liên kết metadata hoặc dọn nhầm worktree vẫn còn được sử dụng.

## Kết luận

Dùng `git worktree list` để kiểm kê đường dẫn, commit và branch của các worktree; dùng `git worktree move` để di chuyển linked worktree và `git worktree repair` khi đã di chuyển thủ công khiến metadata lệch. Dùng `git worktree lock --reason` để giữ metadata của worktree tạm thời không khả dụng, rồi `unlock` khi không còn cần bảo vệ. Trước khi prune hoặc remove, hãy xác minh đường dẫn, trạng thái và mọi thay đổi cần giữ.
