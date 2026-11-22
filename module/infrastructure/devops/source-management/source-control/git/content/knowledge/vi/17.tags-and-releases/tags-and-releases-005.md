# Làm việc với tag trong trạng thái detached HEAD

Trong Git, tag là một tên tham chiếu tới một mốc cụ thể trong lịch sử, thường dùng để đánh dấu phiên bản phát hành như `v1.4.0`. Khi checkout hoặc switch trực tiếp tới một tag, Git đưa working tree về đúng commit mà tag trỏ tới. Lúc này `HEAD` không còn gắn với một branch mà trỏ thẳng tới commit, tạo thành trạng thái **detached HEAD**.

Detached HEAD rất phù hợp để kiểm tra mã nguồn tại một phiên bản, chạy thử, tìm lỗi hoặc tạo một bản vá thử nghiệm. Tuy nhiên, nếu bạn tạo commit mới trong trạng thái này, không có branch nào tự động tiến lên để giữ commit đó. Cần hiểu cách tag và HEAD liên hệ với nhau để không làm mất dấu công việc sau khi chuyển sang branch khác.

## 1. HEAD, branch và tag liên hệ thế nào?

Trong trạng thái bình thường, `HEAD` thường trỏ tới một branch hiện tại. Branch lại trỏ tới commit mới nhất của nó:

```text
HEAD -> main -> C
```

Khi tạo commit mới trên `main`, Git cập nhật ref `main` để trỏ tới commit mới; `HEAD` vẫn gắn với branch đó.

Tag cũng là một ref, nhưng được dùng để đặt tên cho một mốc lịch sử. Ví dụ:

```text
HEAD -> main -> C
                 ^
                 |
              v1.2.0
```

Khi chuyển trực tiếp tới tag:

```bash
git switch --detach v1.2.0
```

Git đặt `HEAD` trực tiếp lên commit được tag chỉ tới:

```text
HEAD ------> C
             ^
             |
          v1.2.0

main ------> D
```

Trong ví dụ này, `main` vẫn ở commit `D`, còn `HEAD` đang xem commit `C`. Không có branch nào được checkout. Đây là detached HEAD.

Có thể kiểm tra trạng thái bằng:

```bash
git status
git branch --show-current
git rev-parse --short HEAD
git tag --points-at HEAD
```

Khi đang detached, `git status` hiển thị thông báo tương ứng; `git branch --show-current` thường không in tên branch; `git rev-parse --short HEAD` cho biết commit hiện tại; `git tag --points-at HEAD` liệt kê các tag trỏ đúng commit đó.

Detached HEAD không có nghĩa là repository chỉ đọc. Bạn vẫn có thể sửa file, stage thay đổi và tạo commit. Khác biệt là commit mới không làm di chuyển một branch ref.

## 2. Chuyển tới tag để kiểm tra phiên bản

Trước khi chuyển, kiểm tra working tree để biết có thay đổi chưa commit hay không:

```bash
git status
```

Liệt kê tag:

```bash
git tag --list
git tag --list 'v1.*'
git tag --sort=-version:refname
```

Lệnh cuối sắp xếp tên tag theo thứ tự phiên bản nếu tên tag tuân theo quy ước version mà Git nhận diện được.

Xem tag trỏ tới đâu và nội dung commit:

```bash
git show v1.2.0
git rev-parse v1.2.0
```

Chuyển tới tag trong detached HEAD:

```bash
git switch --detach v1.2.0
```

Lệnh tương đương kiểu cũ là:

```bash
git checkout --detach v1.2.0
```

Dùng `git switch --detach` thể hiện rõ ý định chuyển tới commit mà không checkout branch. Sau khi chuyển, working tree phản ánh nội dung tại tag `v1.2.0`; bạn có thể đọc mã nguồn, chạy test hoặc kiểm tra hành vi của phiên bản đó.

Một số trường hợp dùng detached HEAD:

- Tái hiện lỗi chỉ xuất hiện ở một phiên bản đã phát hành.
- So sánh hành vi giữa hai tag.
- Chạy test trên commit đã được gắn tag.
- Kiểm tra nội dung phát hành mà không làm thay đổi branch phát triển.
- Tạo một branch sửa lỗi bắt đầu từ phiên bản cũ.

Ví dụ so sánh hai mốc:

```bash
git diff v1.1.0..v1.2.0
git log --oneline v1.1.0..v1.2.0
```

Hai lệnh trên không yêu cầu checkout tag; chúng giúp xem phần thay đổi giữa các mốc.

## 3. Tạo tag khi đang ở detached HEAD

Khi đã chuyển tới đúng commit cần đánh dấu, bạn có thể tạo tag ngay tại `HEAD`. Git hỗ trợ hai dạng tag thường dùng.

**Lightweight tag** là một ref đơn giản trỏ trực tiếp tới object được chỉ định, thường là commit:

```bash
git tag v1.2.1
```

Vì không ghi thêm metadata như người tạo tag, thời gian và thông điệp, lightweight tag phù hợp với mốc nội bộ hoặc nhãn tạm thời.

**Annotated tag** tạo một tag object chứa tagger, ngày tạo, thông điệp và có thể có chữ ký:

```bash
git tag -a v1.2.1 -m "Release 1.2.1"
```

Annotated tag thường phù hợp với mốc phát hành vì nó lưu thông tin mô tả phiên bản. Có thể kiểm tra tag:

```bash
git show v1.2.1
git cat-file -t v1.2.1
git rev-parse "v1.2.1^{commit}"
```

Với annotated tag, `git cat-file -t v1.2.1` trả về `tag`; với lightweight tag trỏ trực tiếp tới commit, kết quả thường là `commit`. Cú pháp `^{commit}` yêu cầu Git phân giải tag về commit được tag chỉ tới.

Khi đang detached tại commit `C`, tạo tag sẽ đặt tên cho `C`:

```text
HEAD ------> C
             ^
             |
          v1.2.1
```

Tag không di chuyển branch `main`, không tạo commit mới và không tự chuyển HEAD về branch. Nó chỉ tạo thêm một tên tham chiếu tới mốc hiện tại.

Nếu tag đã tồn tại, Git mặc định từ chối tạo tag trùng tên. Hãy kiểm tra trước:

```bash
git tag --list v1.2.1
```

Không dùng `git tag -f` chỉ để vượt qua lỗi trùng tên. Force-update tag có thể làm thay đổi ý nghĩa của một phiên bản đã công bố và gây bất đồng giữa các bản clone. Với tag release đã chia sẻ, nên giữ tag bất biến; nếu cần phát hành sửa đổi, chọn số phiên bản mới theo quy ước của dự án.

## 4. Nếu tạo commit mới khi đang detached HEAD

Bạn có thể sửa file và tạo commit khi detached:

```bash
git switch --detach v1.2.0

# Chỉnh sửa file, sau đó:
git add -- src/fix.java
git commit -m "Try a fix on release 1.2.0"
```

Sau commit, `HEAD` trỏ tới commit mới, nhưng branch `main` hoặc branch khác vẫn ở vị trí cũ:

```text
A---B---C---D       (main)
         \
          E        (HEAD, detached)
```

Commit `E` đã được tạo và tồn tại trong object database. Tuy nhiên, chưa có branch nào giữ nó bằng một ref branch. Nếu chuyển đi mà không tạo ref giữ lại, commit có thể chỉ còn được tìm thấy qua reflog trong một khoảng thời gian; sau khi reflog hết hạn và garbage collection dọn object không còn reachable, việc khôi phục sẽ khó hơn.

Nếu muốn giữ công việc, tạo branch ngay tại commit hiện tại:

```bash
git switch -c fix/release-1.2.0
```

Lệnh này tạo branch mới trỏ tới commit hiện tại và chuyển HEAD sang branch đó:

```text
A---B---C---D       (main)
         \
          E        (fix/release-1.2.0, HEAD)
```

Từ đây, các commit tiếp theo sẽ làm di chuyển branch `fix/release-1.2.0` như bình thường.

Nếu chỉ muốn đặt một mốc cứu hộ mà chưa cần làm việc tiếp trên branch, có thể tạo tag:

```bash
git tag rescue/release-1.2.0
```

Tag giữ lại commit hiện tại, nhưng branch thường thuận tiện hơn khi bạn dự định phát triển nhiều commit tiếp theo.

## 5. Quay lại branch sau khi kiểm tra tag

Nếu bạn chỉ đọc mã nguồn hoặc chạy test và không tạo commit, có thể quay lại branch:

```bash
git switch main
```

Nếu đã tạo commit khi detached và muốn tiếp tục phát triển nó, tạo branch trước khi chuyển đi:

```bash
git switch -c fix/from-v1.2.0
```

Nếu commit detached đã được tạo nhưng bạn đã chuyển sang branch khác, vẫn có thể tìm commit qua reflog và tạo branch trỏ tới nó:

```bash
git reflog
git switch -c rescue/detached-work <commit-id>
```

Thay `<commit-id>` bằng mã commit tìm được trong reflog. Lệnh tạo branch mới tại commit đó; sau đó bạn có thể xem lại nội dung và tiếp tục công việc.

Nếu bạn muốn đưa một commit đã tạo ở detached HEAD vào một branch đã tồn tại, hãy giữ mã commit rồi cherry-pick:

```bash
git switch main
git cherry-pick <commit-id>
```

Cherry-pick tạo một commit mới trên `main` với thay đổi tương ứng. Commit ban đầu ở detached HEAD vẫn có thể được giữ bởi branch hoặc tag cứu hộ nếu bạn đã tạo ref cho nó.

Đừng dùng `git reset --hard` như cách thông thường để thoát detached HEAD. Lệnh đó có thể làm mất thay đổi chưa commit trong working tree và index.

## 6. Phát hành tag từ detached HEAD và đẩy lên remote

Một quy trình phổ biến là kiểm tra chính xác commit, tạo annotated tag, rồi push tag lên remote:

```bash
# Lấy tag mới từ remote trước khi chọn phiên bản
git fetch origin --tags

# Chuyển tới commit đã được chọn làm nội dung phát hành
git switch --detach <release-commit>

# Xác nhận commit và chạy kiểm thử
git show --no-patch --format=fuller HEAD
git status

# Tạo tag phát hành mới trên commit hiện tại
git tag -a v1.2.1 -m "Release 1.2.1"

# Kiểm tra tag vừa tạo
git show v1.2.1

# Đẩy riêng tag lên remote
git push origin v1.2.1
```

Thay `<release-commit>` bằng mã commit đã được kiểm tra và chọn làm nội dung cho phiên bản `v1.2.1`. Không mặc định tag mới phải trỏ tới commit của tag phiên bản trước.

Push tag riêng bằng `git push origin v1.2.1` làm remote nhận tag đó. Lệnh không di chuyển branch remote như `main`. Để đẩy mọi tag local chưa có trên remote, Git có lệnh:

```bash
git push origin --tags
```

Chỉ dùng `--tags` khi bạn thực sự muốn đẩy tất cả tag local đủ điều kiện; repository có thể chứa tag thử nghiệm hoặc tag nội bộ không nên công bố. Với một release cụ thể, push tên tag tường minh thường dễ kiểm soát hơn.

Có thể xem tag đã có trên remote bằng:

```bash
git ls-remote --tags origin
```

Nếu người khác cần lấy tag mới, họ có thể chạy:

```bash
git fetch origin --tags
```

## 7. Sửa hoặc xóa tag

Tag thường được xem là mốc bất biến sau khi đã công bố. Nếu tag local được tạo nhầm và chưa chia sẻ, có thể xóa rồi tạo lại sau khi kiểm tra:

```bash
git tag -d v1.2.1
git tag -a v1.2.1 -m "Release 1.2.1" <correct-commit>
```

Thay `<correct-commit>` bằng mã commit đúng. Việc xóa tag local không xóa tag trên remote.

Nếu tag đã được push, xóa tag remote là một thao tác riêng:

```bash
git push origin --delete refs/tags/v1.2.1
```

Không xóa hoặc di chuyển tag release đã công bố nếu chưa phối hợp với người dùng tag đó. Các clone khác có thể vẫn giữ tag cũ, khiến cùng một tên tag trỏ tới các commit khác nhau giữa các máy. Nếu phát hành có lỗi, thông thường nên tạo tag phiên bản mới thay vì tái sử dụng tên cũ.

## 8. Các trạng thái thường gặp và cách xử lý

| Tình huống | Điều đang xảy ra | Cách xử lý |
|---|---|---|
| `git status` báo detached HEAD | HEAD đang trỏ trực tiếp tới commit | Bình thường khi kiểm tra tag; tạo branch nếu cần phát triển |
| `git branch --show-current` không in tên | Không có branch hiện tại được checkout | Dùng `git status` và `git rev-parse HEAD` để xác nhận |
| Tạo commit rồi chuyển branch | Commit detached chưa được branch giữ | Tạo branch hoặc tag cứu hộ trước khi chuyển đi |
| `git tag` báo tag đã tồn tại | Tên tag đã được dùng | Kiểm tra `git show <tag>`; chọn tên mới hoặc xử lý theo chính sách |
| Tag local có nhưng remote không có | Tag chưa được push | Dùng `git push origin <tag>` |
| Tag remote khác tag local | Hai phía đang có giá trị tag khác nhau | Dừng thao tác ghi đè, xác minh nguồn và phối hợp trước khi sửa |
| Muốn sửa mã tại tag release | Tag chỉ là mốc tham chiếu | Tạo branch từ tag bằng `git switch -c <branch> <tag>` |

## 9. Checklist trước khi rời detached HEAD

Trước khi chuyển sang branch khác, hãy tự kiểm tra:

1. Tôi đang ở commit nào? Dùng `git rev-parse --short HEAD`.
2. HEAD đang detached hay gắn với branch? Dùng `git status`.
3. Có thay đổi chưa commit không? Dùng `git status --short`.
4. Tôi có tạo commit mới khi detached không? Kiểm tra `git log --oneline --decorate -5`.
5. Nếu có commit mới, nó đã được giữ bằng branch hoặc tag chưa?
6. Tag tôi tạo là đúng loại, đúng tên và đúng commit chưa?
7. Nếu cần chia sẻ tag, tôi đã push đúng tag lên đúng remote chưa?

Checklist này giúp bạn phân biệt ba việc khác nhau: xem một commit, tạo commit mới và đặt tên cho một mốc. Chúng có thể diễn ra cùng lúc nhưng không tự thay thế cho nhau.

## Kết luận

Khi dùng `git switch --detach <tag>`, Git đưa HEAD trực tiếp tới commit được tag chỉ tới và không checkout branch. Bạn có thể kiểm tra phiên bản hoặc tạo commit thử nghiệm trong trạng thái này. Nếu commit mới cần được giữ lâu dài, hãy tạo branch bằng `git switch -c <branch>` hoặc tag cứu hộ trước khi rời đi. Khi tạo tag phát hành, xác minh commit, ưu tiên annotated tag, push tag tường minh và xem tag đã công bố là mốc cần được giữ ổn định.
