# Tạo thư mục làm việc bổ sung bằng git worktree add

Khi đang phát triển một tính năng nhưng cần chuyển sang sửa lỗi khẩn cấp, bạn có thể tạo thêm một thư mục làm việc từ cùng repository bằng **Git worktree**. Mỗi worktree có working tree và index riêng, vì vậy bạn có thể mở hai nhánh trong hai thư mục khác nhau cùng lúc mà không phải stash hoặc clone repository thêm lần nữa.

Lệnh tạo worktree là `git worktree add`. Bạn có thể dùng nó để mở một branch đã tồn tại, tạo branch mới từ một mốc cụ thể hoặc checkout một commit ở trạng thái detached `HEAD` để review. Các worktree liên kết cùng một repository nên dùng chung object database và các tham chiếu branch/tag.

## 1. Worktree bổ sung hoạt động như thế nào?

Một repository có thể có một worktree chính và nhiều linked worktree. Mỗi thư mục làm việc có:

- Working tree riêng: các file bạn mở và chỉnh sửa nằm trong thư mục đó.
- Index riêng: vùng staging của mỗi worktree độc lập.
- `HEAD` riêng: mỗi worktree có thể checkout một branch khác nhau hoặc ở trạng thái detached.
- Dữ liệu repository dùng chung: object database, branch, tag và phần lớn cấu hình được chia sẻ.

Ví dụ, bạn có thể có cấu trúc:

```text
workspace/
|-- payment-service/       # worktree chính, đang ở main
|-- wt-payment/            # worktree bổ sung, ở feature/payment
`-- wt-hotfix/              # worktree bổ sung, ở hotfix/login
```

Các thư mục trên không phải những bản clone độc lập. Commit được tạo trong một worktree sẽ được nhìn thấy từ các worktree khác vì chúng cùng dùng object database. Tuy nhiên, thay đổi chưa commit ở working tree và index của worktree này không tự xuất hiện ở worktree khác.

Trong linked worktree, file `.git` ở thư mục làm việc thường là một file trỏ đến metadata riêng của worktree bên trong repository chính. Không tự xóa hoặc di chuyển file metadata đó bằng thao tác hệ thống tệp; hãy quản lý vòng đời worktree bằng các lệnh Git.

## 2. Cú pháp cơ bản của git worktree add

Cú pháp tổng quát:

```bash
git worktree add <path> [<commit-ish>]
```

- `<path>` là thư mục làm việc mới. Có thể dùng đường dẫn tương đối hoặc tuyệt đối.
- `<commit-ish>` là branch, tag hoặc commit mà worktree sẽ checkout.
- Nếu `<commit-ish>` là branch đã tồn tại và branch chưa được checkout ở worktree khác, Git sẽ dùng branch đó.

Ví dụ tạo worktree từ branch đã có:

```bash
git worktree add ../wt-payment feature/payment
```

Lệnh tạo thư mục `../wt-payment` và checkout branch `feature/payment` trong thư mục đó. Worktree hiện tại vẫn giữ nguyên branch và trạng thái của nó.

Nếu muốn xem nhanh branch đang được checkout trong worktree hiện tại:

```bash
git branch --show-current
```

Sau khi thêm worktree, có thể kiểm tra branch tại thư mục mới bằng:

```bash
git -C ../wt-payment branch --show-current
git -C ../wt-payment status
```

Tùy chọn `-C` yêu cầu Git chạy lệnh như thể thư mục làm việc hiện tại là đường dẫn được chỉ định.

## 3. Tạo worktree và branch mới bằng -b

Nếu branch tính năng chưa tồn tại, dùng `-b` để tạo branch mới đồng thời tạo worktree:

```bash
git worktree add -b feature/refactor ../wt-refactor main
```

Ý nghĩa các thành phần:

- `-b feature/refactor`: tạo branch mới tên `feature/refactor`.
- `../wt-refactor`: tạo thư mục làm việc mới tại đường dẫn đó.
- `main`: dùng commit đầu nhánh `main` làm điểm bắt đầu cho branch mới.

Sau lệnh, worktree mới checkout branch `feature/refactor`; branch `main` ở worktree ban đầu không bị di chuyển.

Nếu muốn branch mới bắt đầu từ commit hiện tại của repository, bạn có thể bỏ `<commit-ish>`:

```bash
git worktree add -b feature/docs ../wt-docs
```

Khi không chỉ định branch hoặc commit-ish, Git cũng có tiện ích tạo branch mới dựa trên `HEAD`, với tên branch được suy ra từ thành phần cuối của đường dẫn worktree. Ví dụ:

```bash
git worktree add ../experiment
```

Git tạo branch mới tên `experiment` từ `HEAD` hiện tại (nếu tên đó chưa tồn tại). Trong quy trình nhóm, nên dùng `-b` tường minh để người đọc lệnh biết branch nào sẽ được tạo.

### Tạo worktree từ remote-tracking branch

Nếu muốn bắt đầu tính năng từ `origin/main`, trước hết cập nhật thông tin remote:

```bash
git fetch origin
git worktree add -b feature/api ../wt-api origin/main
```

Lệnh tạo branch local `feature/api` tại commit mà `origin/main` đang trỏ đến và checkout branch đó trong `../wt-api`. Tùy cấu hình `branch.autoSetupMerge`, Git có thể tự thiết lập upstream khi branch mới bắt đầu từ remote-tracking branch. Kiểm tra bằng:

```bash
git -C ../wt-api branch -vv
```

Nếu upstream chưa được thiết lập, có thể cấu hình sau:

```bash
git -C ../wt-api branch --set-upstream-to=origin/main feature/api
```

`git fetch` cập nhật remote-tracking branch; nó không tự thay đổi branch local đang làm việc.

## 4. Mở branch đã tồn tại trong worktree mới

Nếu branch đã được tạo trước đó và chưa checkout ở worktree nào khác, truyền tên branch làm `<commit-ish>`:

```bash
git worktree add ../wt-release release/2.4
```

Git checkout branch `release/2.4` trong worktree mới. Các commit được tạo trong worktree này sẽ cập nhật branch `release/2.4` dùng chung; khi chuyển sang worktree khác, bạn sẽ thấy branch đã tiến lên.

Nếu tên branch không tồn tại, Git có thể tự đoán một remote-tracking branch cùng tên trong trường hợp chỉ có một remote phù hợp. Để tránh tạo nhầm branch từ nguồn không mong muốn, hãy chỉ rõ điểm bắt đầu và dùng `-b` khi mục tiêu là tạo branch local mới:

```bash
git fetch origin
git worktree add -b feature/search ../wt-search origin/feature/search
```

Lệnh trên tạo branch local `feature/search` từ remote-tracking branch cùng tên. Nếu branch local đó đã tồn tại, không dùng `-b`; hãy kiểm tra trạng thái và mở branch hiện có theo cách phù hợp.

## 5. Tạo worktree ở detached HEAD

Đôi khi bạn chỉ muốn kiểm tra một commit hoặc tag mà không cần tạo branch. Dùng `--detach`:

```bash
git worktree add --detach ../wt-review v2.4.0
```

Worktree mới checkout nội dung mà tag `v2.4.0` trỏ tới nhưng `HEAD` không gắn với branch local. Cách này hữu ích để review bản phát hành, chạy kiểm thử hồi quy hoặc so sánh hành vi giữa hai commit.

Bạn có thể dùng mã commit thay cho tag:

```bash
git worktree add --detach ../wt-old-build a1b2c3d
```

Kiểm tra trạng thái detached:

```bash
git -C ../wt-review status
git -C ../wt-review branch --show-current
git -C ../wt-review rev-parse HEAD
```

Trong trạng thái detached, `git branch --show-current` không in tên branch. Nếu bạn tạo commit tại worktree này, commit vẫn được lưu trong object database nhưng không tự cập nhật một branch có tên. Hãy tạo branch nếu muốn tiếp tục phát triển từ commit đó:

```bash
git -C ../wt-review switch -c review/fix
```

Lệnh trên tạo branch `review/fix` từ commit hiện tại của worktree review.

## 6. Các tùy chọn tạo worktree thường gặp

| Tùy chọn | Tác dụng | Khi dùng |
|---|---|---|
| `-b <branch>` | Tạo branch mới từ điểm bắt đầu | Mở một nhánh tính năng mới trong thư mục riêng |
| `-B <branch>` | Tạo hoặc đặt lại branch về điểm bắt đầu được chỉ định | Chỉ dùng khi chủ đích di chuyển/reset branch đã tồn tại |
| `--detach` | Checkout commit mà không gắn `HEAD` với branch | Review commit hoặc tag độc lập |
| `--lock` | Khóa worktree ngay sau khi tạo | Worktree nằm trên ổ đĩa tháo rời hoặc vị trí có thể tạm thời không truy cập |
| `--no-checkout` | Tạo worktree mà không checkout nội dung | Quy trình đặc biệt cần tự xử lý bước checkout sau đó |

Ví dụ khóa worktree ngay khi tạo:

```bash
git worktree add --lock -b release/test ../external/release-test main
```

Worktree bị khóa sẽ được bảo vệ khỏi một số thao tác prune tự động. Khi cần mở khóa:

```bash
git worktree unlock ../external/release-test
```

`-B` có thể đặt lại một branch đang tồn tại về commit chỉ định. Đây là thao tác ảnh hưởng lịch sử branch, vì vậy hãy xác nhận branch không được đồng đội sử dụng và không có commit cần giữ trước khi dùng.

## 7. Giới hạn: một branch không thể checkout ở nhiều worktree

Theo mặc định, Git ngăn cùng một branch được checkout đồng thời trong nhiều worktree. Ví dụ nếu worktree chính đang ở `main`, lệnh sau sẽ bị từ chối:

```bash
git worktree add ../wt-main main
```

Git bảo vệ quy tắc này để tránh hai working tree cùng cập nhật một branch và gây nhầm lẫn về trạng thái `HEAD`/index. Hãy tạo branch mới nếu cần một vùng làm việc độc lập:

```bash
git worktree add -b experiment/main-copy ../wt-main-copy main
```

Hoặc tạo worktree detached từ commit hiện tại nếu chỉ cần đọc/kiểm tra:

```bash
git worktree add --detach ../wt-main-review main
```

Không nên dùng `--force` chỉ để bỏ qua cảnh báo branch đã được checkout ở nơi khác. Tùy chọn force có thể cho phép tình huống nhiều worktree dùng cùng branch, nhưng làm mất bảo vệ mà Git cung cấp và dễ dẫn đến thao tác ghi đè hoặc cập nhật branch khó kiểm soát.

## 8. Xác minh worktree sau khi tạo

Sau khi tạo một hoặc nhiều worktree, xem danh sách:

```bash
git worktree list
```

Ví dụ kết quả:

```text
/workspace/payment-service       5ab12cd [main]
/workspace/wt-payment            7cd34ef [feature/payment]
/workspace/wt-hotfix              8ef56ab [hotfix/login]
/workspace/wt-review              5ab12cd (detached HEAD)
```

Để xem thông tin máy có thể phân tích dễ hơn:

```bash
git worktree list --porcelain
```

Kiểm tra riêng trạng thái của worktree mới:

```bash
git -C ../wt-payment status
git -C ../wt-payment log -1 --oneline --decorate
git -C ../wt-payment branch --show-current
```

Nếu lệnh `git worktree add` báo lỗi, hãy kiểm tra đường dẫn đã tồn tại hay chưa, branch có đang checkout ở worktree khác không, commit đích có hợp lệ không và quyền ghi thư mục có đủ không.

## 9. Quy trình làm việc song song với worktree

Giả sử bạn đang làm tính năng thanh toán trên `main` và cần xử lý lỗi đăng nhập ngay. Bạn có thể tạo worktree cho nhánh hotfix:

```bash
git fetch origin
git worktree add -b hotfix/login ../wt-login origin/main
```

Mở `../wt-login` trong IDE hoặc terminal khác, sửa lỗi và tạo commit:

```bash
git -C ../wt-login status
git -C ../wt-login add src/auth/LoginService.java
git -C ../wt-login commit -m "Fix login validation"
```

Trong khi đó, worktree ban đầu vẫn giữ nguyên thay đổi đang làm trên nhánh tính năng. Sau khi hoàn thành hotfix, push branch theo quy trình nhóm:

```bash
git -C ../wt-login push -u origin hotfix/login
```

Bạn có thể tiếp tục làm ở worktree chính hoặc mở worktree khác cho nhánh release. Các commit được chia sẻ trong cùng repository; thay đổi chưa commit của mỗi worktree vẫn tách biệt.

## 10. Lưu ý về đường dẫn và môi trường

- Đường dẫn worktree phải chỉ đến thư mục có thể được tạo hoặc thư mục rỗng; tránh chọn nhầm thư mục đang chứa dữ liệu.
- Nên đặt worktree cạnh thư mục chính, chẳng hạn `../wt-payment`, để dễ phân biệt và dọn dẹp.
- Trên Windows, có thể dùng đường dẫn như `..\wt-payment`; trong Git Bash, đường dẫn dạng `/c/work/wt-payment` cũng có thể sử dụng tùy môi trường.
- Không copy nguyên thư mục `.git` hoặc tự di chuyển thư mục linked worktree bằng Explorer/File Manager. Nếu cần đổi vị trí, dùng các lệnh worktree phù hợp.
- Nếu worktree nằm trên ổ đĩa tháo rời, hãy khóa nó trước khi ngắt kết nối để Git không cố dọn một worktree tạm thời không truy cập được.
- Worktree chia sẻ branch và object database, nên xóa một worktree không xóa branch hoặc commit đã tạo. Tuy nhiên, thay đổi chưa commit trong thư mục đó có thể mất nếu bạn xóa thư mục.

## 11. Bài tập thực hành

Trong một repository thử nghiệm có branch `main`, tạo ba worktree theo các cách khác nhau:

1. Dùng `git worktree add -b feature/demo ../wt-demo main` để tạo branch mới và worktree.
2. Tạo một commit trong `../wt-demo`, sau đó quay lại worktree chính và xác nhận commit mới xuất hiện trong `git log --all`.
3. Dùng `git worktree add --detach ../wt-review HEAD~1` để tạo worktree detached tại commit cha.
4. Thử mở lại branch `main` trong worktree khác và quan sát Git bảo vệ branch đang được checkout.
5. Chạy `git worktree list --porcelain` để xem đường dẫn, HEAD và branch của từng worktree.
6. Giải thích sự khác nhau giữa working tree/index riêng và object database/branch dùng chung.

Bạn hoàn thành bài tập khi có thể tạo worktree từ branch hiện có, tạo branch mới bằng `-b`, checkout commit bằng `--detach` và xác minh được mỗi thư mục đang làm việc trên trạng thái nào.
