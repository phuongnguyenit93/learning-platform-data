# Git reset --mixed tác động đến HEAD và chỉ mục

Trong Git, một thay đổi có thể nằm ở ba nơi khác nhau: commit được HEAD tham chiếu, staging area (index) và working tree. Khi muốn bỏ một commit gần nhất nhưng vẫn giữ nội dung các tệp để chỉnh sửa hoặc tạo commit mới, `git reset --mixed` là một lựa chọn thường dùng. Lệnh này di chuyển HEAD đến commit đích và đưa index về trạng thái của commit đó, trong khi giữ nguyên nội dung working tree.

Hiểu chính xác ba khu vực này giúp bạn dự đoán kết quả trước khi chạy lệnh. `--mixed` không xóa nội dung đang có trong working tree, nhưng nó thay thế trạng thái staging hiện tại bằng snapshot của commit đích. Vì vậy, những thay đổi từng được stage sẽ trở thành thay đổi chưa stage.

## 1. Ba thành phần cần hiểu trước khi dùng reset

### HEAD và branch hiện tại

`HEAD` cho biết vị trí hiện tại của repository. Trong cách làm việc thông thường, HEAD là symbolic reference trỏ đến branch đang checkout, ví dụ `refs/heads/main`. Khi bạn tạo commit mới, branch đó tiến đến commit mới và HEAD đi theo branch. Nếu đang checkout trực tiếp một commit (*detached HEAD*), HEAD trỏ thẳng đến commit đó.

Với dạng `git reset <commit>`, Git di chuyển branch hiện tại đến commit đích (hoặc di chuyển HEAD nếu đang detached). Do đó, reset ở cấp commit làm thay đổi vị trí của nhánh hiện tại trong lịch sử.

### Index (staging area)

Index là vùng Git lưu nội dung và trạng thái đã chọn để đưa vào commit tiếp theo. Khi chạy `git add`, nội dung của tệp tại thời điểm đó được đưa vào index. Một tệp có thể tiếp tục thay đổi trong working tree sau khi đã stage; khi ấy index và working tree chứa hai phiên bản khác nhau.

### Working tree

Working tree là các tệp và thư mục bạn trực tiếp xem, tạo, sửa hoặc xóa trong thư mục dự án. Đây là nơi chứa nội dung đang làm việc, bao gồm cả những thay đổi đã stage và chưa stage.

Có thể hình dung luồng trạng thái như sau:

```mermaid
flowchart LR
    H[HEAD / commit hiện tại] -->|snapshot của commit| I[Index / staging area]
    I -->|nội dung được checkout| W[Working tree]
    W -->|git add| I
    I -->|git commit| H
```

Sơ đồ mô tả quan hệ khái niệm giữa các khu vực trong công việc thường ngày. `git reset --mixed <commit>` đặt HEAD và index theo commit đích, nhưng không checkout lại nội dung vào working tree.

## 2. Cú pháp và ý nghĩa của --mixed

Cú pháp dạng reset theo commit:

```bash
git reset [--mixed] [<commit>]
```

Nếu không chỉ định mode, `git reset` mặc định dùng `--mixed`. Nếu không chỉ định commit, commit đích mặc định là HEAD hiện tại.

Ví dụ:

```bash
# Đưa index về snapshot của HEAD hiện tại, giữ nguyên working tree.
git reset --mixed HEAD

# Đưa branch hiện tại và index về commit cha của HEAD.
git reset --mixed HEAD~1
```

Với `git reset --mixed <commit>`, Git thực hiện hai việc chính:

1. Di chuyển branch hiện tại (hoặc HEAD trong trạng thái detached) đến `<commit>`.
2. Đặt index về snapshot của `<commit>`.

Working tree được giữ nguyên. Các tệp đang có nội dung khác index mới sẽ xuất hiện dưới dạng thay đổi chưa stage. Tệp không được Git theo dõi cũng được giữ nguyên; reset không phải lệnh dọn dẹp tệp untracked.

## 3. Quan sát tác động lên HEAD, index và working tree

Giả sử lịch sử ban đầu có ba commit:

```text
A---B---C  (HEAD -> main)
```

Commit `C` vừa được tạo và chứa thay đổi ở `README.md` cùng `src/App.java`. Bạn quyết định bỏ commit `C` khỏi đầu branch để chỉnh sửa lại nội dung và tạo commit khác.

Trước khi reset, trạng thái đã commit có thể biểu diễn như sau:

| Thành phần | Trạng thái trước reset |
|---|---|
| HEAD / `main` | Commit `C` |
| Index | Snapshot của `C` nếu không có thay đổi stage thêm sau commit |
| Working tree | Nội dung của `C` nếu không có sửa đổi thêm sau commit |

Chạy:

```bash
git reset --mixed HEAD~1
```

Kết quả:

```text
A---B  (HEAD -> main)
     \
      C  (không còn là đầu branch main)
```

`main` hiện trỏ đến `B`; index được đặt theo snapshot của `B`; working tree vẫn chứa nội dung trước reset, tức nội dung đã có ở `C`. Vì working tree khác index, các thay đổi của `C` trở thành thay đổi chưa stage.

| Thành phần | Trạng thái sau reset |
|---|---|
| HEAD / `main` | Commit `B` (`HEAD~1` trước thao tác) |
| Index | Snapshot của `B` |
| Working tree | Vẫn giữ nội dung trước reset, bao gồm thay đổi từng nằm trong `C` |
| Kết quả trong `git status` | Các khác biệt giữa working tree và index được liệt kê là chưa stage |

Điểm cốt lõi: commit `C` không còn nằm ở đầu branch `main`, nhưng nội dung thay đổi của nó vẫn còn trong working tree để bạn xem, sửa, stage lại và commit theo cách khác.

## 4. Ví dụ thực tế: bỏ commit gần nhất nhưng giữ nội dung

Giả sử bạn đã tạo commit nhưng nhận ra commit đó gộp nhiều thay đổi không liên quan. Bạn muốn tách thành hai commit nhỏ hơn.

Trước hết, kiểm tra trạng thái và lịch sử:

```bash
git status
git log --oneline -5
```

Nếu working tree và index không có thay đổi khác cần bảo toàn riêng, có thể đưa branch về commit cha:

```bash
git reset --mixed HEAD~1
```

Kiểm tra lại:

```bash
git status
git diff
git diff --staged
```

Thông thường, `git status` sẽ liệt kê các tệp đã thay đổi trong phần *Changes not staged for commit*. `git diff` cho thấy nội dung chưa stage; `git diff --staged` không còn hiển thị thay đổi từ commit vừa được bỏ khỏi đầu branch vì index đã được đưa về `HEAD` mới.

Sau đó, chọn từng phần để tạo commit theo mục đích:

```bash
# Chọn từng phần thay đổi để stage tương tác.
git add -p

# Xem chính xác nội dung sẽ được commit.
git diff --staged

# Tạo commit thứ nhất.
git commit -m "feat: add application configuration"

# Stage phần còn lại và tạo commit tiếp theo.
git add src/App.java
git diff --staged
git commit -m "feat: wire application startup"
```

`git add -p` cho phép chọn từng hunk thay vì stage toàn bộ tệp. Nếu cần stage lại toàn bộ thay đổi, có thể dùng `git add <path>` hoặc `git add -A` tùy phạm vi mong muốn.

## 5. Unstage các thay đổi mà không di chuyển branch

Một cách dùng khác là chạy `git reset` mà không chỉ định commit:

```bash
git reset
```

Lệnh tương đương với `git reset --mixed HEAD`: HEAD vẫn ở commit hiện tại, index được đưa về snapshot của HEAD và working tree được giữ nguyên. Đây là cách phổ biến để bỏ staging cho tất cả thay đổi đã stage mà không xóa nội dung chỉnh sửa.

Ví dụ, sau khi stage hai tệp:

```bash
git add README.md src/App.java
git status
```

Bạn nhận ra chỉ muốn commit `README.md`. Chạy:

```bash
git reset
```

Sau đó cả hai tệp vẫn giữ nội dung đã sửa trong working tree, nhưng không còn được stage. Bạn có thể stage lại đúng tệp cần commit:

```bash
git add README.md
git diff --staged
```

Lưu ý: thao tác này bỏ trạng thái staging của mọi thay đổi được index quản lý, không chỉ một tệp. Nếu chỉ muốn unstage một số đường dẫn, dùng dạng pathspec được trình bày ở phần tiếp theo.

## 6. Phân biệt reset theo commit và reset theo pathspec

`git reset` có một dạng cú pháp dành cho đường dẫn:

```bash
git reset [<tree-ish>] -- <pathspec>...
```

Ví dụ:

```bash
git reset HEAD -- README.md
```

Dạng này cập nhật index của các đường dẫn được chỉ định theo nội dung từ `<tree-ish>` (mặc định thường là HEAD). Nó **không di chuyển HEAD hoặc branch hiện tại** và cũng không thay đổi working tree. Đây là cách unstage một tệp cụ thể.

So sánh hai trường hợp:

| Lệnh | HEAD / branch | Index | Working tree |
|---|---|---|---|
| `git reset --mixed HEAD~1` | Di chuyển về commit cha | Đặt theo `HEAD~1` | Giữ nguyên |
| `git reset` | Giữ nguyên HEAD hiện tại | Đặt theo HEAD | Giữ nguyên |
| `git reset HEAD -- README.md` | Giữ nguyên | Chỉ cập nhật index của `README.md` theo HEAD | Giữ nguyên |

Đừng nhầm `git reset HEAD -- <file>` với `git reset --mixed HEAD~1`. Cả hai có thể làm thay đổi trạng thái staging, nhưng chỉ dạng reset theo commit mới di chuyển vị trí branch.

## 7. So sánh --soft, --mixed và --hard

Ba mode reset khác nhau ở việc Git cập nhật những khu vực nào:

| Mode | HEAD / branch | Index | Working tree |
|---|---|---|---|
| `--soft` | Di chuyển đến commit đích | Giữ nguyên | Giữ nguyên |
| `--mixed` | Di chuyển đến commit đích | Đặt theo commit đích | Giữ nguyên |
| `--hard` | Di chuyển đến commit đích | Đặt theo commit đích | Cập nhật theo commit đích; có thể ghi đè thay đổi tracked |

Ví dụ cùng reset về `HEAD~1`:

```bash
git reset --soft HEAD~1
git reset --mixed HEAD~1
git reset --hard HEAD~1
```

Đây là ba lựa chọn thay thế nhau cho cùng một tình huống giả định; không chạy liên tiếp cả ba lệnh như một quy trình. `--soft` giữ thay đổi ở trạng thái staged sau khi bỏ commit; `--mixed` giữ nội dung nhưng chuyển khác biệt thành unstaged; `--hard` đưa cả working tree về commit đích và có thể làm mất thay đổi tracked chưa được commit. Hãy xác định trạng thái mong muốn trước khi chọn mode.

## 8. Kiểm tra trước và sau khi dùng --mixed

Trước khi reset, hãy xem branch, index và working tree:

```bash
git status --short --branch
git diff --staged
git diff
git log --oneline --decorate -5
```

Các lệnh giúp bạn biết:

- Branch hiện tại đang trỏ đến commit nào.
- Nội dung nào đã stage.
- Nội dung nào chỉ đang nằm trong working tree.
- Commit nào sẽ trở thành đích nếu dùng `HEAD~1`.

Sau reset, kiểm tra lại:

```bash
git status
git log --oneline --decorate -5
git diff
git diff --staged
```

Nếu mục tiêu là bỏ commit nhưng giữ nội dung, hãy xác nhận branch đã trỏ về commit mong muốn và các thay đổi cần giữ vẫn xuất hiện trong working tree. Đừng chỉ dựa vào thông báo lệnh; hãy đọc trạng thái thực tế.

## 9. Khôi phục khi reset nhầm

Khi reset theo commit, Git thường ghi lại các lần di chuyển của HEAD trong reflog. Nếu bạn chọn nhầm commit đích, có thể xem lịch sử di chuyển:

```bash
git reflog --date=local
```

Ví dụ:

```text
5d6e7f8 HEAD@{0}: reset: moving to HEAD~1
9a0b1c2 HEAD@{1}: commit: add login validation
```

Nếu `9a0b1c2` là commit trước khi reset và bạn muốn đưa branch trở lại commit đó trong khi vẫn giữ nội dung working tree hiện tại, có thể dùng:

```bash
git reset --mixed 9a0b1c2
```

Hãy thay mã minh họa bằng commit hash đã xác minh từ reflog. Nếu cần giữ một mốc tham chiếu trước khi tiếp tục xử lý, có thể tạo branch cứu hộ trỏ đến commit đó:

```bash
git branch rescue/before-reset 9a0b1c2
```

Reflog giúp tìm lại vị trí HEAD cũ trong thời gian các entry còn được lưu. Nó không lưu lại chính xác trạng thái staging của index trước lần reset; `git reset --mixed` đã thay index bằng snapshot của commit đích. Vì vậy, khôi phục branch pointer không nhất thiết khôi phục nguyên trạng những phần đã stage trước thao tác.

Nếu commit đã được push và người khác có thể đã dựa vào nó, việc reset rồi push viết lại lịch sử branch chung. Trong trường hợp cần hoàn tác một thay đổi đã chia sẻ, thường nên cân nhắc `git revert <commit>` để tạo commit mới đảo ngược thay đổi mà không di chuyển branch về lịch sử cũ. Hãy theo quy ước của nhóm trước khi thay đổi lịch sử remote.

## 10. Những hiểu nhầm thường gặp

| Hiểu nhầm | Cách hiểu đúng |
|---|---|
| `git reset --mixed` xóa nội dung thay đổi | Lệnh giữ nguyên working tree; nó di chuyển HEAD và cập nhật index |
| `--mixed` giữ nguyên staging | Index được đặt theo commit đích, nên thay đổi đã stage thường trở thành unstaged |
| `git reset` không có tham số sẽ xóa commit gần nhất | Không có commit đích thì mặc định reset về HEAD hiện tại; branch không di chuyển, index được đưa về HEAD |
| Mọi dạng `git reset` đều di chuyển HEAD | Dạng pathspec như `git reset HEAD -- file` chỉ cập nhật index cho đường dẫn đó |
| Reset commit đồng nghĩa commit object bị xóa ngay | Branch không còn trỏ đến commit đó; commit có thể còn được tìm thấy qua reflog trong thời gian entry được giữ |
| Có thể reset tùy ý branch đã push mà không ảnh hưởng ai | Việc cập nhật lịch sử đã chia sẻ có thể làm gián đoạn người khác; cần phối hợp hoặc dùng revert |

## 11. Ghi nhớ

Với dạng reset theo commit, `git reset --mixed <commit>` tác động đến hai khu vực: HEAD/branch được di chuyển đến commit đích và index được đưa về snapshot của commit đó. Working tree được giữ nguyên, vì vậy nội dung khác index sẽ trở thành thay đổi chưa stage.

Hãy nhớ ba trường hợp thường dùng:

- `git reset --mixed HEAD~1`: bỏ commit gần nhất khỏi đầu branch, giữ nội dung trong working tree ở trạng thái unstaged.
- `git reset` hoặc `git reset --mixed HEAD`: bỏ staging của các thay đổi được index quản lý, giữ nguyên branch và nội dung working tree.
- `git reset HEAD -- <file>`: bỏ staging cho đường dẫn cụ thể, không di chuyển HEAD.

Trước khi reset, kiểm tra `git status`, diff và lịch sử. Sau khi reset, đọc lại trạng thái để xác nhận đúng commit đích và nội dung cần giữ. Cách làm này giúp sử dụng `--mixed` có chủ đích khi cần sắp xếp lại commit hoặc điều chỉnh staging area.
