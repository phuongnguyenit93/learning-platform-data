# Refs, symbolic refs, packed-refs và reflog

Git dùng **ref** (reference) để đặt tên dễ nhớ cho các đối tượng trong repository. Thay vì phải ghi nhớ một object ID dài, bạn có thể dùng tên như `main`, `feature/login`, `v2.1.0` hoặc `HEAD`. Một ref thường trỏ đến commit, nhưng tag ref có thể trỏ đến đối tượng tag hoặc một loại object khác. Git dùng các ref để xác định nhánh hiện tại, phiên bản phát hành, trạng thái remote đã fetch và nhiều mốc lịch sử khác.

Ref có thể được lưu dưới dạng một file riêng (loose ref) hoặc được gom vào file `packed-refs`. Một số ref như `HEAD` là **symbolic ref**: thay vì chứa trực tiếp object ID, nó chỉ đến một ref khác. Bên cạnh ref hiện tại, Git còn có **reflog** để ghi lại những lần một ref di chuyển. Reflog thường giúp tìm lại commit sau reset, amend, rebase hoặc xóa nhánh nhầm, miễn là đối tượng chưa bị dọn khỏi object database.

## 1. Ref là gì và Git dùng ref để làm gì?

Một ref là tên có thể phân giải thành một object ID. Với nhánh local, ref thường trỏ đến commit mới nhất của nhánh. Khi bạn tạo commit trên nhánh đó, Git cập nhật ref để nó trỏ đến commit mới.

Các namespace ref thường gặp:

| Namespace / tên | Ví dụ | Công dụng |
|---|---|---|
| `refs/heads/` | `refs/heads/main` | Nhánh local |
| `refs/remotes/` | `refs/remotes/origin/main` | Remote-tracking branch, ghi nhận trạng thái nhánh remote tại lần fetch gần nhất |
| `refs/tags/` | `refs/tags/v2.1.0` | Tag đánh dấu phiên bản hoặc mốc lịch sử |
| `refs/stash` | `refs/stash` | Ref quản lý stash mới nhất và reflog của stash stack |
| `refs/notes/` | `refs/notes/review` | Git notes gắn metadata bổ sung vào object |
| `refs/replace/` | `refs/replace/<oid>` | Cơ chế thay thế object khi đọc lịch sử |

Tên nhánh ngắn `main` thường được Git phân giải thành `refs/heads/main`. Tên `origin/main` thường được phân giải thành `refs/remotes/origin/main`. Tên đầy đủ giúp tránh nhầm lẫn khi nhiều namespace có tên gần giống nhau.

Một ref không chứa toàn bộ commit. Nó chỉ giữ tên và object ID; object database mới lưu nội dung commit, tree và blob. Nhờ vậy, việc di chuyển ref có thể làm thay đổi nhánh đang trỏ đến commit nào mà không cần sao chép toàn bộ lịch sử.

## 2. Ref trực tiếp và symbolic ref

### Ref trực tiếp

Ref trực tiếp (direct ref) chứa object ID của object mà nó trỏ đến. Ví dụ, ref nhánh `refs/heads/main` có thể chứa một OID commit. Khi nhánh tiến lên, Git thay OID trong ref bằng OID commit mới.

Các lệnh sau giúp xem ref và giá trị của nó:

```bash
# Liệt kê các ref cùng object ID
git show-ref

# Xem riêng ref nhánh main
git show-ref --verify refs/heads/main

# Phân giải tên nhánh thành object ID
git rev-parse refs/heads/main
```

`git show-ref` đọc ref theo giao diện Git, không yêu cầu bạn biết ref đang nằm trong file riêng hay `packed-refs`.

### Symbolic ref

Symbolic ref (symref) chứa tên của một ref khác thay vì object ID. `HEAD` là ví dụ quan trọng nhất. Khi đang ở nhánh `main`, nội dung logic của `HEAD` tương đương:

```text
ref: refs/heads/main
```

Điều đó có nghĩa `HEAD` trỏ đến nhánh `main`; nhánh `main` mới là ref trực tiếp trỏ đến commit. Khi bạn chuyển sang `feature/login`, Git đổi đích symbolic của `HEAD` thành `refs/heads/feature/login`.

Kiểm tra `HEAD` đang trỏ đến đâu:

```bash
# Hiển thị ref đích của HEAD nếu HEAD là symbolic ref
git symbolic-ref HEAD

# Hiển thị tên ngắn của nhánh hiện tại
git symbolic-ref --short HEAD

# Phân giải HEAD thành commit OID
git rev-parse HEAD
```

`git symbolic-ref` có thể thất bại khi `HEAD` không phải symbolic ref, ví dụ trong trạng thái detached HEAD. `git rev-parse HEAD` vẫn phân giải được commit mà HEAD đang trỏ đến.

### Detached HEAD

Khi checkout trực tiếp một commit hoặc tag thay vì một nhánh, `HEAD` có thể chứa trực tiếp OID commit. Trạng thái này được gọi là detached HEAD:

```bash
git switch --detach v2.1.0
git status
git rev-parse HEAD
git symbolic-ref -q HEAD
```

Trong trạng thái này, bạn không đứng trên một nhánh local. Nếu tạo commit mới, HEAD di chuyển đến commit mới nhưng không có nhánh tên rõ ràng nào tự động tiến theo. Hãy tạo nhánh nếu muốn giữ công việc:

```bash
git switch -c experiment/from-v2.1.0
```

## 3. HEAD, nhánh và remote-tracking refs liên hệ với nhau thế nào?

Khi đang làm việc trên `main`, mô hình thường là:

```text
HEAD
 |
 | symbolic ref
 v
refs/heads/main
 |
 | direct ref
 v
commit C3
```

Khi chạy `git commit`, Git tạo commit mới và cập nhật `refs/heads/main`; `HEAD` vẫn trỏ đến `refs/heads/main`. Vì vậy, nhánh tiến lên nhưng HEAD không cần đổi đích symbolic.

Remote-tracking branch như `origin/main` là ref local dưới `refs/remotes/origin/main`. Nó không phải ref đang nằm trên máy chủ và cũng không tự cập nhật tức thì khi đồng đội push. Lệnh fetch nhận thông tin từ remote rồi cập nhật remote-tracking ref:

```bash
git fetch origin
git show-ref refs/remotes/origin/main
git rev-parse origin/main
```

Khi push, Git yêu cầu remote cập nhật ref ở phía máy chủ. Việc push thành công không đồng nghĩa reflog local của bạn được gửi lên remote; reflog là dữ liệu lịch sử cục bộ của từng repository.

## 4. Loose refs: ref được lưu thành file riêng

Trong backend lưu ref dạng file truyền thống, ref chưa được đóng gói thường xuất hiện dưới thư mục `.git/refs/`. Ví dụ:

```text
.git/
├── HEAD
├── refs/
│   ├── heads/
│   │   ├── main
│   │   └── feature/
│   │       └── login
│   ├── remotes/
│   │   └── origin/
│   │       └── main
│   └── tags/
│       └── v2.1.0
└── packed-refs
```

Một loose ref trực tiếp thường chứa OID trên một dòng. Symbolic ref chứa dòng dạng `ref: <tên-ref>`. Tuy nhiên, không nên sửa trực tiếp các file ref để thay đổi nhánh hoặc tag. Thao tác thủ công có thể bỏ qua kiểm tra đồng thời, reflog hoặc các quy tắc định dạng mà Git đảm nhiệm.

Một số lệnh tạo hoặc di chuyển loose ref:

```bash
# Tạo nhánh local từ HEAD hiện tại
git branch feature/login

# Chuyển sang nhánh mới
git switch feature/login

# Xem tên ref đích của HEAD
git symbolic-ref --short HEAD
```

Các lệnh cấp cao này nên được ưu tiên vì chúng cập nhật ref và trạng thái làm việc theo quy trình Git hỗ trợ.

## 5. `packed-refs`: gom nhiều ref vào một file

Khi repository có nhiều ref, Git có thể đóng gói chúng vào file `packed-refs` thay vì giữ từng ref dưới `.git/refs/`. Thao tác này giúp giảm số lượng file ref riêng và có thể cải thiện hiệu quả đọc ref ở repository lớn.

Có thể yêu cầu Git đóng gói ref:

```bash
git pack-refs --all
```

Trong backend file truyền thống, `packed-refs` có nội dung dạng văn bản, ví dụ:

```text
# pack-refs with: peeled fully-peeled sorted
<object-id-1> refs/heads/main
<object-id-2> refs/remotes/origin/main
<tag-object-id> refs/tags/v2.1.0
^<peeled-object-id>
```

Các dòng thông thường chứa OID và tên ref. Dòng bắt đầu bằng `^` có thể lưu OID đã peel của annotated tag, tức object mà tag object trỏ đến, thường là commit được gắn tag.

Loose ref có cùng tên sẽ được ưu tiên hơn bản ghi tương ứng trong `packed-refs`. Khi Git cập nhật một ref đã đóng gói, nó có thể tạo loose ref mới để ghi giá trị hiện tại; Git quản lý việc hợp nhất và dọn bản ghi cũ khi đóng gói lại.

Để kiểm tra ref, hãy dùng `git show-ref`, `git for-each-ref` hoặc `git rev-parse`. Không chỉnh sửa `packed-refs` bằng trình soạn thảo và không xóa file này thủ công. Ngoài backend file truyền thống, Git còn có thể dùng backend lưu ref khác; lệnh Git là giao diện ổn định để thao tác.

## 6. Duyệt và truy vấn refs

Một số lệnh hữu ích để khám phá ref:

```bash
# Hiển thị các ref mà Git biết
git show-ref

# Liệt kê branch local và remote-tracking branch
git branch -a

# Liệt kê tag
git tag --list

# Duyệt ref với tên và object ID
git for-each-ref --format='%(objectname) %(refname)' refs/heads refs/remotes refs/tags

# Kiểm tra ref cụ thể có tồn tại
git show-ref --verify refs/heads/main
```

`git for-each-ref` cho phép lọc theo namespace và định dạng các trường như `%(refname)`, `%(objectname)`, `%(upstream)` hoặc `%(subject)`. Đây là lựa chọn phù hợp cho script cần liệt kê ref mà không đọc trực tiếp cấu trúc lưu trữ nội bộ.

Để phân giải tên thành object ID:

```bash
git rev-parse HEAD
git rev-parse main
git rev-parse refs/remotes/origin/main
```

Khi script cần đảm bảo ref tồn tại và trỏ đến commit, dùng chế độ kiểm tra phù hợp, chẳng hạn:

```bash
git rev-parse --verify 'refs/heads/main^{commit}'
```

Hậu tố `^{commit}` yêu cầu Git phân giải đối tượng về commit. Điều này hữu ích với tag có thể trỏ đến tag object trước khi tới commit.

## 7. `git update-ref`: cập nhật ref có kiểm tra

`git update-ref` là lệnh cấp thấp để tạo, cập nhật hoặc xóa ref. Các lệnh cấp cao như `git branch`, `git tag`, `git reset` thường phù hợp hơn cho công việc hằng ngày. `update-ref` hữu ích trong script hoặc khi cần thao tác ref có điều kiện.

Tạo một ref mới trỏ đến commit đã biết:

```bash
git update-ref refs/heads/review/candidate <commit-oid>
```

Cập nhật ref chỉ khi giá trị hiện tại đúng bằng OID mong đợi:

```bash
git update-ref refs/heads/review/candidate <new-oid> <old-oid>
```

Tham số `<old-oid>` là điều kiện kiểm tra. Nếu ref hiện tại không còn trỏ đến OID đó, Git từ chối cập nhật. Cơ chế này giúp tránh ghi đè thay đổi của tiến trình khác khi ref đã di chuyển kể từ lúc bạn đọc.

Xóa ref với điều kiện giá trị hiện tại:

```bash
git update-ref -d refs/heads/review/candidate <old-oid>
```

Hãy dùng tên ref đầy đủ và OID mong đợi khi cần thao tác an toàn. Không dùng `update-ref` để chỉnh sửa ref tuỳ tiện nếu chưa hiểu nhánh hoặc tag nào đang phụ thuộc vào nó.

## 8. Reflog là gì?

Reflog (reference log) ghi lại những lần giá trị của một ref thay đổi trong repository local. Ví dụ, khi `HEAD` chuyển từ nhánh `main` sang `feature/login`, hoặc khi nhánh di chuyển do commit, reset, amend hay rebase, Git có thể ghi một mục reflog tương ứng.

Reflog khác với commit history:

| Commit history (`git log`) | Reflog (`git reflog`) |
|---|---|
| Đi theo quan hệ parent của commit | Ghi lại các lần ref di chuyển |
| Phản ánh lịch sử commit có thể truy cập từ ref được chọn | Phản ánh lịch sử cục bộ của một ref trong một khoảng thời gian |
| Có thể chia sẻ qua fetch/push dưới dạng commit và ref | Không được push hoặc clone như lịch sử chung |
| Không nhất thiết cho biết một nhánh từng trỏ đến commit nào trước reset | Có thể cho biết HEAD hoặc nhánh từng trỏ đến commit cũ |

Reflog thường lưu OID cũ, OID mới, identity của người cập nhật, thời gian và thông điệp mô tả thao tác. Nó là công cụ phục hồi hữu ích nhưng không phải bản sao lưu vĩnh viễn.

## 9. Xem reflog của HEAD và branch

Xem reflog của HEAD:

```bash
git reflog
git reflog show HEAD
git reflog show --date=iso HEAD
```

Xem reflog của một nhánh:

```bash
git reflog show main
git reflog show feature/login
```

Có thể dùng `git log -g` để duyệt reflog với định dạng log:

```bash
git log -g --oneline HEAD
```

Một kết quả minh họa:

```text
9ac31d2 HEAD@{0}: commit: Add login validation
6b2e811 HEAD@{1}: reset: moving to HEAD~1
9ac31d2 HEAD@{2}: commit: Add login validation
```

Mỗi mục biểu diễn một trạng thái ref trong quá khứ. Cú pháp `HEAD@{1}` có nghĩa là giá trị HEAD ở một mục reflog trước đó, không phải commit cha thứ nhất của commit hiện tại. Chỉ số thay đổi khi có thao tác mới, vì vậy hãy đọc kết quả ngay trước khi dùng.

Bạn cũng có thể tham chiếu theo thời gian, ví dụ `main@{yesterday}` hoặc `HEAD@{2.hours.ago}`. Cách diễn giải phụ thuộc cú pháp revision của Git và dữ liệu reflog còn tồn tại.

## 10. Phục hồi commit sau reset, amend hoặc rebase

Giả sử bạn vô tình reset nhánh về commit cũ:

```bash
git reset --hard HEAD~2
```

Nếu commit mới hơn chưa bị dọn, reflog có thể giúp tìm lại OID mà HEAD từng trỏ đến:

```bash
git reflog --date=local
```

Sau khi xác định đúng commit, hãy tạo nhánh cứu hộ để giữ commit trước khi thực hiện thao tác khác:

```bash
git branch rescue/before-reset <recovered-commit-oid>
```

Kiểm tra nội dung:

```bash
git log --oneline --decorate rescue/before-reset -10
git show --stat rescue/before-reset
```

Tạo nhánh cứu hộ giúp commit tiếp tục được tham chiếu, tránh phụ thuộc vào việc mục reflog có còn hay không. Sau khi kiểm tra, bạn có thể chọn cách merge, cherry-pick hoặc reset nhánh làm việc theo kế hoạch. Không vội chạy `reset --hard` lần nữa khi chưa bảo vệ các commit cần giữ.

### Sau amend hoặc rebase

`git commit --amend` và `git rebase` tạo commit mới với OID mới. Commit cũ có thể không còn được nhánh hiện tại tham chiếu, nhưng reflog của HEAD hoặc nhánh có thể còn ghi lại vị trí trước đó:

```bash
git reflog show --date=local HEAD
```

Tìm mục trước thao tác amend/rebase, xác minh commit bằng `git show`, rồi tạo nhánh cứu hộ trỏ đến OID đó. Điều này giúp xem lại nội dung cũ hoặc khôi phục các commit bị bỏ sót.

### Sau khi xóa nhánh

Nếu nhánh local bị xóa nhầm, Git thường xóa cả reflog riêng của nhánh đó. Reflog HEAD có thể vẫn giữ dấu vết nếu bạn từng checkout hoặc tạo commit khi đang ở nhánh này. Hãy xem các reflog còn tồn tại:

```bash
git reflog --all --date=local
```

`git reflog --all` chỉ liệt kê reflog còn tồn tại; nó không khôi phục reflog đã bị xóa cùng nhánh. Nếu không tìm thấy commit tip ở đây, hãy thử tìm object unreachable bằng `git fsck` khi object chưa bị prune. Khi tìm thấy OID, tạo lại nhánh:

```bash
git branch rescue/restored-feature <recovered-commit-oid>
```

## 11. Reflog có giới hạn thời gian và phạm vi

Reflog được lưu cục bộ. Khi clone repository, bạn không nhận được reflog của máy người khác; khi push, bạn cũng không gửi reflog của mình lên máy chủ. Nếu cần giữ một commit lâu dài hoặc chia sẻ với nhóm, hãy tạo branch hoặc tag phù hợp và push ref đó.

Git có các cấu hình điều khiển thời gian hết hạn reflog, gồm:

| Cấu hình | Ý nghĩa |
|---|---|
| `gc.reflogExpire` | Thời gian hết hạn mặc định cho reflog entry, thường là 90 ngày |
| `gc.reflogExpireUnreachable` | Thời gian hết hạn ngắn hơn cho entry không còn reachable từ tip hiện tại, mặc định thường là 30 ngày |
| `core.logAllRefUpdates` | Điều khiển việc Git ghi reflog cho các ref theo phạm vi cấu hình |

Giá trị mặc định có thể thay đổi theo loại repository, phiên bản và cấu hình cụ thể. Kiểm tra cấu hình hiện tại:

```bash
git config --show-origin --get gc.reflogExpire
git config --show-origin --get gc.reflogExpireUnreachable
git config --show-origin --get core.logAllRefUpdates
```

Reflog entry hết hạn không nhất thiết có nghĩa object bị xóa ngay tại thời điểm đó. Garbage collection và prune có thể dọn object unreachable sau khi các điều kiện hết hạn được đáp ứng. Tuy nhiên, đừng dựa vào reflog như nơi lưu trữ lâu dài.

Các lệnh như `git reflog expire`, `git gc` và `git prune` có thể làm giảm hoặc loại bỏ cơ hội phục hồi. Trước khi dọn dẹp repository, hãy xác nhận không còn commit cần giữ chỉ được tìm thấy qua reflog.

## 12. Các lệnh reflog và bảo trì

Những lệnh sau hữu ích khi kiểm tra và quản lý reflog:

```bash
# Xem reflog HEAD
git reflog show HEAD

# Xem reflog của tất cả ref có reflog
git reflog show --all

# Xem các mục mới nhất với thời gian
git reflog --date=local -20

# Xóa reflog của một ref cụ thể (thao tác phá hủy dữ liệu phục hồi)
git reflog delete 'refs/heads/old-feature@{2}'
```

`git reflog delete` và `git reflog expire` là lệnh bảo trì có thể loại bỏ dấu vết cần thiết để phục hồi. Chỉ dùng khi hiểu rõ mục tiêu và chính sách lưu trữ. Không xóa reflog để xử lý một nhánh lỗi nếu chưa kiểm tra commit và tạo ref cứu hộ.

## 13. Quy trình kiểm tra và phục hồi an toàn

Khi nghi ngờ một commit bị mất do reset, amend, rebase hoặc xóa nhánh:

1. Dừng các thao tác dọn dẹp như `git gc --prune=now`, `git prune` hoặc expire reflog.
2. Chạy `git status` để xác định thay đổi working tree và index hiện tại.
3. Xem `git reflog --all --date=local` để tìm thời điểm ref di chuyển.
4. Dùng `git show <oid>` hoặc `git log <oid>` để xác minh commit cần giữ.
5. Tạo branch cứu hộ bằng `git branch rescue/<name> <oid>`.
6. Sau khi commit được giữ bằng ref, mới chọn merge, cherry-pick hoặc cách khôi phục phù hợp.
7. Nếu không tìm thấy qua reflog, xem xét `git fsck --full --no-reflogs --unreachable` để tìm object còn sót.

Ví dụ:

```bash
git status
git reflog --all --date=local
git show <recovered-commit-oid>
git branch rescue/lost-work <recovered-commit-oid>
git log --oneline --decorate rescue/lost-work -10
```

Đừng checkout hoặc reset về OID vừa tìm thấy trước khi tạo ref cứu hộ. Khi đã có nhánh cứu hộ, commit sẽ tiếp tục reachable và dễ kiểm tra hơn.

## 14. Những nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu chính xác |
|---|---|
| `HEAD` luôn chứa trực tiếp commit OID | Khi ở trên branch, HEAD thường là symbolic ref trỏ đến `refs/heads/...`; detached HEAD mới thường chứa OID trực tiếp. |
| `origin/main` là ref trên máy chủ | Đây là remote-tracking ref local, được cập nhật khi fetch. |
| `packed-refs` là nơi lưu commit object | Nó lưu mapping giữa tên ref và OID; object thực tế nằm trong object database. |
| Mọi ref luôn là một file dưới `.git/refs` | Ref có thể được đóng gói trong `packed-refs` hoặc dùng backend lưu trữ khác. |
| Reflog là lịch sử commit giống `git log` | Reflog ghi các lần ref di chuyển; git log đi theo quan hệ parent của commit. |
| Reflog được chia sẻ khi push | Reflog là dữ liệu local và không được push như branch hoặc tag. |
| Reflog giữ commit mãi mãi | Entry có thể hết hạn và object unreachable có thể bị prune. |
| `HEAD@{1}` là parent của commit hiện tại | Đây là giá trị HEAD ở một mục reflog trước đó; parent commit được truy cập bằng `HEAD^` hoặc `HEAD~1`. |
| Có thể sửa `packed-refs` bằng tay an toàn | Nên dùng lệnh Git như `show-ref`, `update-ref`, `pack-refs` để tránh làm hỏng ref hoặc bỏ qua kiểm tra. |

## 15. Tự kiểm tra

1. **Ref là gì?**
   - Là tên có thể phân giải thành object ID, thường dùng để tham chiếu commit hoặc object trong repository.
2. **Khác biệt giữa direct ref và symbolic ref là gì?**
   - Direct ref chứa OID; symbolic ref chứa tên của một ref khác.
3. **Khi đang ở nhánh `main`, HEAD thường trỏ đến đâu?**
   - `refs/heads/main`.
4. **`packed-refs` lưu nội dung commit hay tên ref cùng OID?**
   - Lưu mapping tên ref và OID; nội dung object nằm trong object database.
5. **Reflog khác `git log` như thế nào?**
   - Reflog ghi lại các lần ref di chuyển; git log hiển thị commit theo quan hệ parent.
6. **Sau khi reset nhầm, bước đầu tiên để bảo vệ commit tìm được trong reflog là gì?**
   - Tạo một branch cứu hộ trỏ đến OID commit đó trước khi thực hiện thao tác khôi phục khác.
7. **Reflog có được gửi lên remote không?**
   - Không. Reflog là dữ liệu cục bộ của repository.

## Kết luận

Refs cung cấp tên dễ nhớ cho object; symbolic ref như `HEAD` trỏ đến ref khác, còn direct ref chứa OID. Trong backend file truyền thống, ref có thể tồn tại dưới dạng loose file hoặc được gom vào `packed-refs`; hãy dùng lệnh Git để truy vấn và cập nhật thay vì sửa file nội bộ. Reflog ghi lại các lần ref di chuyển và thường giúp phục hồi commit sau reset, amend, rebase hoặc xóa nhánh. Vì reflog có thể hết hạn và object unreachable có thể bị prune, hãy tạo branch hoặc tag cứu hộ ngay khi xác định được commit cần giữ.
