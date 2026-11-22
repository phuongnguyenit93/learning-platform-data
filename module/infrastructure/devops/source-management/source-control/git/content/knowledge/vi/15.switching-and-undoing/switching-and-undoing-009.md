# Chuyển nhiều commit, giữ tham chiếu nguồn với -x và xử lý xung đột

`git cherry-pick` cho phép lấy thay đổi từ một hoặc nhiều commit đã tồn tại rồi áp dụng chúng lên nhánh hiện tại. Đây là cách phổ biến để chuyển một bản sửa lỗi từ nhánh phát triển sang nhánh release, hoặc chọn một số thay đổi cần thiết mà không hợp nhất toàn bộ nhánh nguồn.

Khi chuyển nhiều commit, thứ tự áp dụng có thể ảnh hưởng đến kết quả vì commit sau thường phụ thuộc vào commit trước. Tùy chọn `-x` giúp ghi mã commit nguồn vào commit message để người đọc truy vết được nguồn gốc thay đổi. Nếu một commit gây conflict, Git tạm dừng chuỗi cherry-pick để bạn giải quyết và tiếp tục.

## 1. Cherry-pick tạo ra điều gì?

Giả sử nhánh `feature` có một bản sửa lỗi đã được commit, còn nhánh `release` cần nhận riêng bản sửa lỗi đó:

```bash
git switch release
git cherry-pick abc123
```

Git áp dụng thay đổi do commit `abc123` giới thiệu lên trạng thái hiện tại của `release`, sau đó tạo một commit mới nếu áp dụng thành công.

Sơ đồ đơn giản:

```text
A---B---C             (feature)
     \
      D---E           (release)
```

Nếu cherry-pick commit `C` lên `release`, Git tạo một commit mới `C'` trên đầu `E`:

```text
A---B---C             (feature)
     \
      D---E---C'      (release)
```

`C'` có nội dung thay đổi tương ứng với `C`, nhưng là một commit khác vì nó có parent mới và có thể có timestamp/committer khác. Do đó, mã commit của `C'` khác mã commit của `C`. Nhánh nguồn `feature` không bị di chuyển; thao tác chỉ thêm commit vào nhánh hiện tại.

Cherry-pick chuyển thay đổi của commit, không chuyển nguyên nhánh hoặc toàn bộ lịch sử phát triển của nhánh nguồn. Nếu commit phụ thuộc vào thay đổi ở một commit trước đó, bạn cần chuyển cả commit phụ thuộc hoặc giải quyết các khác biệt phát sinh.

## 2. Chuyển nhiều commit theo thứ tự chỉ định

Có thể truyền nhiều mã commit trong cùng một lệnh:

```bash
git switch release
git cherry-pick abc123 def456 789abc
```

Git lần lượt áp dụng các commit theo thứ tự bạn liệt kê: `abc123`, sau đó `def456`, rồi `789abc`. Cách này phù hợp khi bạn đã biết chính xác các commit cần chuyển và thứ tự phụ thuộc giữa chúng.

Nếu mỗi commit được áp dụng thành công, Git tạo một commit mới tương ứng cho từng commit nguồn. Nếu một commit gây conflict hoặc không thể áp dụng, Git dừng tại commit đó. Các commit còn lại trong chuỗi chưa được xử lý và được giữ trong trạng thái sequencer để bạn tiếp tục sau khi giải quyết.

Trước khi chuyển nhiều commit, nên xem lịch sử nhánh nguồn:

```bash
git log --oneline --decorate feature
git log --oneline --graph --decorate --all
```

Dùng mã commit đầy đủ hoặc một phần đủ duy nhất để tránh nhầm commit có nội dung tương tự. Nếu không chắc thứ tự, hãy xem quan hệ cha-con và nội dung từng commit:

```bash
git show --stat abc123
git show --stat def456
git show --stat 789abc
```

Không nên chọn commit chỉ dựa trên thứ tự thời gian hoặc thông điệp. Một commit sửa cách gọi API có thể phụ thuộc vào commit đã thêm API đó; chuyển ngược thứ tự có thể làm phát sinh conflict hoặc tạo trạng thái không chạy được.

## 3. Chuyển một dải commit

Cú pháp revision range thường dùng là:

```bash
git cherry-pick BASE..TIP
```

Biểu thức `BASE..TIP` chọn các commit có thể đi tới từ `TIP` nhưng không thể đi tới từ `BASE`. Vì vậy, commit `BASE` bị loại khỏi dải; commit `TIP` được bao gồm nếu nó nằm trong tập commit được chọn.

Ví dụ, lịch sử tuyến tính:

```text
A---B---C---D---E  (feature)
    ^
   BASE
```

Dải `B..E` bao gồm `C`, `D`, `E`; không bao gồm `B`. Nếu muốn bao gồm cả `B` trong lịch sử tuyến tính này, có thể dùng `A..E`.

Với dải commit, nên tạo danh sách theo thứ tự cha trước con một cách tường minh rồi đưa danh sách đó cho cherry-pick:

```bash
git rev-list --reverse --topo-order BASE..TIP | git cherry-pick -x --stdin
```

- `git rev-list BASE..TIP` xác định tập commit trong dải.
- `--reverse` đảo thứ tự duyệt để các commit cũ hơn được áp dụng trước.
- `--topo-order` ưu tiên thứ tự tô-pô, giúp commit cha được xử lý trước commit con trong lịch sử phân nhánh.
- `git cherry-pick --stdin` đọc danh sách mã commit từ đầu vào chuẩn.

Thay `BASE` và `TIP` bằng mã commit hoặc tên ref thực tế. Cách này hữu ích khi dải có nhiều commit và bạn muốn kiểm soát rõ thứ tự. Với một danh sách commit nhỏ, truyền trực tiếp từng mã commit theo thứ tự mong muốn thường dễ đọc hơn.

Lưu ý rằng một revision range trên lịch sử phân nhánh có thể chứa commit từ nhiều nhánh. Hãy xem danh sách trước khi áp dụng:

```bash
git rev-list --reverse --topo-order BASE..TIP
```

Nếu tập commit có merge commit, cherry-pick merge commit thường cần chỉ định mainline parent bằng `-m <parent-number>`. Việc chọn parent quyết định phần thay đổi nào của merge commit sẽ được áp dụng; không nên thêm `-m` một cách máy móc. Hãy xem `git show --no-patch --pretty=raw <merge-commit>` và xác định parent phù hợp trước. Nếu chỉ muốn chuyển các commit thường, có thể lọc merge commit khỏi danh sách, nhưng cần hiểu rằng thay đổi chỉ xuất hiện trong kết quả merge có thể không được chuyển theo cách đó.

## 4. Giữ tham chiếu commit nguồn với tùy chọn -x

Khi chuyển commit giữa các nhánh công khai hoặc các nhánh được nhiều nhóm cùng sử dụng, người đọc có thể cần biết commit mới được lấy từ đâu. Tùy chọn `-x` yêu cầu Git thêm một dòng tham chiếu vào commit message:

```bash
git cherry-pick -x abc123
```

Dòng được thêm có dạng:

```text
(cherry picked from commit abc123...)
```

Với một danh sách commit:

```bash
git cherry-pick -x abc123 def456 789abc
```

Git ghi tham chiếu nguồn vào message của các commit cherry-pick thành công mà không có conflict. Khi đọc lịch sử trên nhánh đích, người khác có thể tìm mã commit nguồn và đối chiếu thay đổi ban đầu.

Xem kết quả bằng:

```bash
git log --format=fuller -5
git show --format=fuller HEAD
```

`-x` chỉ thêm thông tin văn bản vào commit message. Nó không giữ nguyên mã commit nguồn, không tạo liên kết ref giữa hai commit, không giữ nhánh nguồn tồn tại và không ngăn commit nguồn bị xóa khỏi các ref khác. Commit mới vẫn có mã riêng.

Tùy chọn này đặc biệt hữu ích khi cherry-pick giữa các nhánh công khai vì nó giúp duy trì khả năng truy vết lịch sử. Với commit từ nhánh riêng hoặc nhánh nội bộ không có ý nghĩa đối với người nhận, tham chiếu đó thường không đem lại nhiều giá trị.

**Giới hạn quan trọng:** Git chỉ tự thêm dòng `(cherry picked from commit ...)` khi cherry-pick không có conflict. Nếu Git phải dừng để bạn giải quyết conflict, đừng giả định dòng `-x` đã được thêm. Nếu quy trình dự án yêu cầu giữ provenance, hãy bổ sung mã commit nguồn vào commit message sau khi giải quyết conflict. Với trường hợp cần kiểm soát message cho từng commit, xử lý từng commit một để có thể kiểm tra và chỉnh message trước khi chuyển commit kế tiếp.

## 5. Xem trước thay đổi trước khi cherry-pick

Trước khi chuyển commit, hãy xác nhận nhánh đích và working tree:

```bash
git status
git branch --show-current
```

Nếu working tree có thay đổi chưa commit, hãy quyết định cách bảo toàn chúng trước khi cherry-pick. Một working tree sạch giúp bạn phân biệt thay đổi do thao tác tích hợp tạo ra với thay đổi có sẵn.

Xem commit nguồn và các file bị tác động:

```bash
git show --stat --oneline abc123
git show --format=fuller --find-renames abc123
```

Với nhiều commit, kiểm tra danh sách trước khi thực hiện:

```bash
git rev-list --reverse --topo-order BASE..TIP
```

Nếu cần so sánh thay đổi của một commit với trạng thái nhánh đích, có thể xem diff của commit và ngữ cảnh file liên quan. Cherry-pick áp dụng patch của commit vào trạng thái hiện tại; nó không bảo đảm kết quả giống hệt source branch nếu hai nhánh đã phát triển khác nhau.

## 6. Xử lý conflict trong chuỗi cherry-pick

Khi một commit không thể áp dụng tự động, Git dừng chuỗi cherry-pick và để lại trạng thái conflict. Xác định commit đang được xử lý và các file bị xung đột:

```bash
git status
git diff --name-only --diff-filter=U
git show CHERRY_PICK_HEAD
```

`CHERRY_PICK_HEAD` trỏ tới commit đang được áp dụng. Với chuỗi nhiều commit, đây là commit hiện tại gây conflict; các commit tiếp theo vẫn đang chờ trong sequencer.

Mở các file conflict, hiểu thay đổi từ commit nguồn và nội dung đang có ở nhánh đích. Có thể xem diff tổng hợp:

```bash
git diff --cc -- path/to/file
```

Chỉnh sửa file thành nội dung cuối cùng, xóa các conflict marker nếu có, rồi đánh dấu từng file đã giải quyết:

```bash
git add -- path/to/file
```

Nếu quyết định xóa file, dùng:

```bash
git rm -- path/to/file
```

Kiểm tra trước khi tiếp tục:

```bash
git status
git diff --cached
git diff --cached --check
git diff --name-only --diff-filter=U
```

Khi mọi file đã được giải quyết, tiếp tục chuỗi:

```bash
git cherry-pick --continue
```

Git tạo commit cho thay đổi vừa giải quyết rồi tiếp tục xử lý các commit còn lại trong chuỗi. Nếu commit tiếp theo cũng conflict, lặp lại quy trình. Sau khi chuỗi hoàn tất, kiểm tra lại lịch sử và chạy test phù hợp.

Nếu bạn không muốn áp dụng commit hiện tại, có thể bỏ qua nó:

```bash
git cherry-pick --skip
```

Chỉ dùng `--skip` khi đã quyết định thay đổi của commit đó không cần có trong nhánh đích hoặc đã được đưa vào bằng cách khác. Bỏ qua một commit có thể khiến commit sau không còn áp dụng được hoặc làm thiếu một phần chức năng.

Nếu muốn hủy toàn bộ chuỗi cherry-pick đang dở và quay lại trạng thái trước khi chuỗi bắt đầu:

```bash
git cherry-pick --abort
```

`--abort` hủy thao tác cherry-pick đang diễn ra; nó không phải cách giải quyết conflict. Trước khi bắt đầu chuỗi, hãy bảo toàn các thay đổi chưa commit để tránh rủi ro mất công việc.

## 7. Bổ sung provenance khi commit có conflict

Vì `-x` không tự thêm dòng nguồn cho commit có conflict, hãy kiểm tra commit message sau khi giải quyết. Cách đơn giản là chuyển từng commit một nếu bạn biết có khả năng conflict:

```bash
git cherry-pick -x abc123
```

Nếu có conflict, giải quyết file rồi chạy:

```bash
git add -- path/to/file
git cherry-pick --continue
```

Sau khi commit được tạo, mở message để bổ sung tham chiếu nguồn nếu cần:

```bash
git commit --amend
```

Thêm dòng sau vào cuối commit message, thay bằng mã commit nguồn đầy đủ:

```text
(cherry picked from commit <source-commit-oid>)
```

Lưu và đóng editor. Sau đó kiểm tra:

```bash
git show --format=fuller --no-patch HEAD
```

Thao tác amend tạo lại commit đích với message đã chỉnh nên mã commit đích sẽ thay đổi. Nếu đã push commit này lên remote, việc amend có thể cần một lần push cập nhật lịch sử theo chính sách của nhóm.

Nếu xử lý một chuỗi nhiều commit và muốn bổ sung provenance cho commit conflict, cân nhắc cherry-pick từng commit riêng. Như vậy bạn có thể hoàn tất, kiểm tra message và amend commit hiện tại trước khi bắt đầu commit kế tiếp.

## 8. Commit đã được áp dụng hoặc trở thành rỗng

Một commit nguồn có thể đã được áp dụng trước đó bằng cách khác, hoặc phần thay đổi của nó đã tồn tại trên nhánh đích. Khi đó cherry-pick có thể báo commit trở thành empty sau khi áp dụng.

Đừng tạo commit rỗng chỉ để làm cho chuỗi chạy tiếp nếu không có lý do lịch sử rõ ràng. Kiểm tra diff, xác nhận thay đổi đã có trong nhánh đích hay chưa, rồi chọn cách xử lý:

- Dùng `git cherry-pick --skip` nếu thay đổi không cần áp dụng thêm.
- Giữ commit rỗng chỉ khi dự án có chủ đích lưu dấu một sự kiện hoặc mốc lịch sử như vậy.
- Nếu thay đổi chỉ được áp dụng một phần, chỉnh sửa kết quả cho đúng rồi stage và tiếp tục.

Không nên bỏ qua một commit chỉ vì Git báo empty mà chưa kiểm tra nội dung và lý do commit đó có trong chuỗi.

## 9. Ví dụ quy trình chuyển một nhóm commit sang release

Giả sử nhánh `feature/payment-fix` có ba commit đã được kiểm tra và cần chuyển sang `release/2.x`. Bạn đã xác định thứ tự phụ thuộc và muốn giữ tham chiếu nguồn:

```bash
# Kiểm tra trạng thái hiện tại
git status

# Chuyển sang nhánh nhận thay đổi
git switch release/2.x

# Xem commit nguồn trước khi áp dụng
git show --stat 12ab345
git show --stat 34bc567
git show --stat 56cd789

# Chuyển theo đúng thứ tự, đồng thời ghi nguồn vào commit message
git cherry-pick -x 12ab345 34bc567 56cd789

# Nếu có conflict:
# 1. Sửa file
# 2. Stage file đã giải quyết
git add -- path/to/file

# 3. Tiếp tục chuỗi
git cherry-pick --continue

# Kiểm tra các commit mới và message
git log --oneline --decorate -5
git show --format=fuller --no-patch HEAD

# Chạy test phù hợp với phần thay đổi
```

Trong thực tế, nếu chuỗi dừng ở một commit có conflict và bạn cần tự thêm provenance, xử lý từng commit một rồi amend message như phần 7 trước khi chuyển commit tiếp theo.

## 10. Những nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu đúng |
|---|---|
| Cherry-pick giữ nguyên mã commit nguồn | Git tạo commit mới trên nhánh đích; mã commit thường khác |
| `-x` giữ nhánh nguồn tồn tại | `-x` chỉ thêm mã commit nguồn vào commit message |
| `-x` luôn thêm dòng provenance | Git chỉ tự thêm dòng này cho cherry-pick không có conflict |
| `BASE..TIP` bao gồm BASE | Range loại BASE và các commit reachable từ BASE; TIP được bao gồm nếu nằm trong tập được chọn |
| Có thể áp dụng commit theo bất kỳ thứ tự nào | Commit sau có thể phụ thuộc commit trước; hãy chỉ định thứ tự cha trước con |
| Đóng conflict marker là xong | Cần stage file đã giải quyết rồi chạy `git cherry-pick --continue` |
| `--skip` và `--abort` giống nhau | `--skip` bỏ commit hiện tại; `--abort` hủy toàn bộ thao tác đang dở |
| Cherry-pick một merge commit giống commit thường | Merge commit cần chọn mainline parent bằng `-m` và hiểu rõ diff sẽ được áp dụng |

## Kết luận

Dùng `git cherry-pick <commit>...` khi đã biết rõ danh sách và thứ tự commit cần chuyển. Với một dải commit, tạo danh sách bằng `git rev-list --reverse --topo-order` để kiểm soát thứ tự cha trước con. Thêm `-x` khi cần lưu mã commit nguồn trong message của các cherry-pick không conflict; nếu có conflict, kiểm tra và bổ sung provenance thủ công khi chính sách dự án yêu cầu. Khi Git dừng, giải quyết file, stage kết quả rồi dùng `git cherry-pick --continue`; chỉ skip hoặc abort sau khi đã hiểu tác động của quyết định đó.
