# Refspec và ánh xạ `refs/heads` với `refs/remotes`

Khi làm việc với remote, Git cần biết **lấy ref nào từ repository từ xa và lưu ref đó ở đâu trong repository local**. Khi push, Git cần biết **lấy ref nào ở local và cập nhật ref nào trên remote**. Quy tắc mô tả hai đầu ánh xạ này được gọi là *refspec*.

Refspec là nền tảng để hiểu vì sao sau `git fetch origin`, ta thường thấy `origin/main`; vì sao `main` và `origin/main` có thể trỏ tới hai commit khác nhau; và vì sao một remote có thể chỉ tải một số nhánh hoặc lưu nhánh từ xa vào một namespace tùy chỉnh. Chủ đề này thuộc phần kết nối remote của Git: nó kết nối branch, remote, fetch, push, upstream và lịch sử mà ta dùng khi cộng tác, giải quyết xung đột hoặc truy tìm thay đổi.

## 1. Ref là gì?

Trong Git, **ref (reference)** là một tên có thể phân giải tới một đối tượng Git, thường là commit. Thay vì phải nhớ mã hash dài của commit, ta dùng tên như `main`, `feature/login`, `v1.2.0` hoặc `origin/main`.

Git lưu ref trong các namespace. Một số namespace thường gặp:

| Namespace | Ý nghĩa | Ví dụ |
|---|---|---|
| `refs/heads/` | Các branch local trong repository hiện tại; trên repository remote, đây cũng là namespace chứa branch của remote đó. | `refs/heads/main` |
| `refs/remotes/` | Các remote-tracking ref được lưu trong repository local để ghi nhận trạng thái nhánh lấy từ remote. | `refs/remotes/origin/main` |
| `refs/tags/` | Các tag. | `refs/tags/v1.2.0` |
| `refs/notes/` | Các Git notes gắn thông tin bổ sung vào đối tượng Git. | `refs/notes/commits` |

Hai namespace quan trọng nhất trong bài này là `refs/heads/` và `refs/remotes/`.

### 1.1. `refs/heads/` biểu diễn branch

Branch local `main` thường được lưu dưới tên đầy đủ:

```text
refs/heads/main
```

Branch `feature/login` tương ứng với:

```text
refs/heads/feature/login
```

Khi ta commit trên branch đang checkout, Git cập nhật ref branch đó để trỏ tới commit mới. Vì vậy, branch là một tên di chuyển theo lịch sử commit; nó không phải bản sao của toàn bộ nội dung dự án.

Mỗi repository có namespace `refs/heads/` của riêng nó. `refs/heads/main` trên máy lập trình viên và `refs/heads/main` trên máy chủ là hai ref nằm ở hai repository khác nhau. Chúng có thể trỏ tới cùng commit, nhưng không tự động đồng bộ với nhau.

### 1.2. `refs/remotes/` biểu diễn remote-tracking ref

Khi fetch nhánh `main` từ remote tên `origin`, cấu hình mặc định thường lưu trạng thái vừa lấy được ở:

```text
refs/remotes/origin/main
```

Tên viết gọn thường dùng là `origin/main`. Đây là **remote-tracking branch/ref**: một ref local ghi nhận trạng thái nhánh `main` mà repository local đã lấy từ remote `origin` ở lần fetch gần nhất.

`origin/main` không phải branch đang nằm trực tiếp trên máy chủ. Branch trên máy chủ thường là `refs/heads/main`; `origin/main` là bản ghi trạng thái của branch đó trong repository local. Nó chỉ thay đổi khi một thao tác như fetch cập nhật nó, hoặc khi ta chủ động thay đổi ref tương ứng.

Ví dụ, sau khi fetch:

```text
Repository trên máy chủ origin       Repository local
refs/heads/main          ----------> refs/remotes/origin/main
                                              |
                                              +-- tên viết gọn: origin/main

refs/heads/main (local branch) ---------------+
        tên viết gọn: main
```

`main` và `origin/main` là hai ref riêng. Nếu người khác push commit mới lên `origin/main`, branch local `main` không tự di chuyển theo. Sau fetch, `origin/main` có thể đi trước `main`; ta cần xem xét rồi merge hoặc rebase để tích hợp thay đổi.

### 1.3. Ref đầy đủ và tên viết gọn

Trong hầu hết lệnh hằng ngày, Git cho phép dùng tên viết gọn:

| Tên viết gọn | Ref đầy đủ thường tương ứng |
|---|---|
| `main` | `refs/heads/main` |
| `feature/login` | `refs/heads/feature/login` |
| `origin/main` | `refs/remotes/origin/main` |
| `origin/feature/login` | `refs/remotes/origin/feature/login` |
| `v1.2.0` | `refs/tags/v1.2.0` |

Khi tên viết gọn có thể gây nhầm lẫn, dùng ref đầy đủ giúp chỉ rõ đối tượng mà lệnh đang tham chiếu. Các lệnh sau hữu ích để quan sát ref:

```bash
# Liệt kê branch local
git branch

# Liệt kê remote-tracking branch
git branch -r

# Liệt kê cả branch local và remote-tracking branch
git branch -a

# Liệt kê ref cùng object ID mà chúng trỏ tới
git show-ref
```

## 2. Refspec là gì?

**Refspec (reference specification)** là biểu thức chỉ định ref nguồn và ref đích trong một thao tác trao đổi dữ liệu. Cấu trúc cơ bản:

```text
[+]<src>:<dst>
```

Trong đó:

- `<src>` là ref nguồn mà Git đọc.
- `<dst>` là ref đích mà Git cập nhật.
- Dấu `+` ở đầu cho phép cập nhật đích ngay cả khi thay đổi không phải fast-forward, trong những ngữ cảnh hỗ trợ force update.
- Dấu `:` phân cách nguồn và đích. Tùy thao tác, một phía có thể được bỏ trống hoặc phần đích có thể được lược bỏ.

Điểm cần nhớ là **cùng cú pháp `<src>:<dst>` nhưng chiều nhìn nguồn và đích phụ thuộc thao tác**:

| Thao tác | `<src>` nằm ở đâu? | `<dst>` nằm ở đâu? |
|---|---|---|
| Fetch | Repository remote | Repository local |
| Push | Repository local | Repository remote |

Ví dụ:

```text
Fetch: +refs/heads/*:refs/remotes/origin/*
       remote source       local destination

Push:  refs/heads/feature/login:refs/heads/feature/login
       local source                         remote destination
```

Vì vậy, đừng đọc refspec một cách tách rời khỏi lệnh đang sử dụng. Với fetch, nguồn thường là branch trên máy chủ và đích là remote-tracking ref local. Với push, nguồn thường là branch local và đích là branch trên máy chủ.

## 3. Fetch refspec: ánh xạ `refs/heads/*` sang `refs/remotes/*`

Khi clone một repository từ xa, Git thường thiết lập cấu hình fetch cho remote `origin` tương tự:

```ini
[remote "origin"]
    url = https://example.com/team/project.git
    fetch = +refs/heads/*:refs/remotes/origin/*
```

Phần `fetch` là refspec mặc định thường gặp. Có thể đọc nó thành:

1. Lấy các ref khớp với `refs/heads/*` từ remote `origin`.
2. Với mỗi ref được lấy, thay phần `*` bằng tên tương ứng ở đích `refs/remotes/origin/*` trong repository local.
3. Cho phép cập nhật remote-tracking ref kể cả khi lịch sử remote đã bị viết lại, nhờ dấu `+`.

Ví dụ ánh xạ:

| Ref branch trên remote | Ref local sau fetch |
|---|---|
| `refs/heads/main` | `refs/remotes/origin/main` |
| `refs/heads/develop` | `refs/remotes/origin/develop` |
| `refs/heads/feature/login` | `refs/remotes/origin/feature/login` |
| `refs/heads/release/2.x` | `refs/remotes/origin/release/2.x` |

Ký tự `*` là wildcard: nó khớp một phần tên ref và phần khớp được dùng ở vị trí `*` trong đích. Một refspec wildcard ánh xạ một nhóm ref theo cùng quy tắc, thay vì phải viết từng branch riêng lẻ.

### 3.1. Vì sao đích là `refs/remotes/origin/*`?

Repository local có thể chứa branch do chính người dùng phát triển và branch-tracking phản ánh trạng thái của remote. Đặt remote-tracking ref dưới `refs/remotes/origin/` giúp Git phân biệt hai nhóm:

```text
refs/heads/
    main
    feature/login

refs/remotes/
    origin/
        main
        develop
        feature/payment
    upstream/
        main
        develop
```

Trong ví dụ trên:

- `refs/heads/main` là branch local `main`.
- `refs/remotes/origin/main` là trạng thái branch `main` đã fetch từ remote `origin`.
- `refs/remotes/upstream/main` là trạng thái branch `main` đã fetch từ remote `upstream`.

Hai remote có thể có branch trùng tên nhưng được lưu trong hai vùng riêng. Nhờ đó, ta có thể so sánh fork cá nhân với repository gốc mà không trộn lẫn remote-tracking ref của chúng.

### 3.2. Fetch không tự merge vào branch local

Giả sử trước khi fetch, `main` và `origin/main` cùng trỏ tới commit `A`. Một thành viên khác push thêm commit `B` lên remote. Sau lệnh:

```bash
git fetch origin
```

`origin/main` được cập nhật để trỏ tới `B`, còn `main` vẫn trỏ tới `A`:

```text
Trước fetch:

A  (main, origin/main)

Sau khi remote có commit B và ta fetch:

A  (main) ---- B  (origin/main)
```

Fetch chỉ tải đối tượng và cập nhật ref đích theo refspec. Nó không tự thay đổi branch đang checkout, working tree hoặc staging area để tích hợp commit mới. Sau khi xem trạng thái, ta có thể chủ động merge hoặc rebase:

```bash
git status -sb
git log --oneline --left-right main...origin/main

# Tích hợp bằng merge
git switch main
git merge origin/main

# Hoặc, nếu quy ước dự án yêu cầu lịch sử tuyến tính
# git rebase origin/main
```

Nếu hai nhánh có thay đổi xung đột, Git có thể yêu cầu giải quyết conflict trong quá trình merge hoặc rebase. Refspec chỉ quyết định ref được lấy và cập nhật; nó không quyết định cách tích hợp lịch sử vào branch local.

### 3.3. Kiểm tra cấu hình fetch refspec

Để xem URL và refspec đang dùng cho `origin`:

```bash
git remote -v
git config --get-all remote.origin.fetch
```

Lệnh thứ hai có thể in ra:

```text
+refs/heads/*:refs/remotes/origin/*
```

Dấu `+` hiển thị ở đầu là một phần của cấu hình refspec. Dùng `--get-all` vì một remote có thể có nhiều dòng `remote.<name>.fetch`, chẳng hạn nhiều ánh xạ dương và các mẫu loại trừ.

Để xem những branch mà máy chủ đang quảng bá:

```bash
git ls-remote --heads origin
```

Lệnh này truy vấn remote và hiển thị ref cùng object ID mà máy chủ cho phép kết nối nhìn thấy. Nó không đồng nghĩa với việc đã cập nhật các remote-tracking ref local; muốn cập nhật local, hãy fetch.

## 4. Đọc cú pháp refspec fetch chi tiết

### 4.1. Ánh xạ một branch cụ thể

Ta có thể fetch một branch và chỉ rõ nơi lưu nó:

```bash
git fetch origin refs/heads/release/2.x:refs/remotes/origin/release/2.x
```

Git lấy branch `release/2.x` trên remote và cập nhật remote-tracking ref tương ứng trong local.

Nếu phần đích bị bỏ trống:

```bash
git fetch origin refs/heads/release/2.x
```

Git lấy ref được chỉ định và ghi thông tin fetch vào `FETCH_HEAD`; lệnh này không chỉ định một remote-tracking ref đích trong refspec. `FETCH_HEAD` là thông tin phục vụ các thao tác tích hợp tiếp theo, không phải tên branch local lâu dài như `origin/release/2.x`.

### 4.2. Dấu `+` và cập nhật non-fast-forward

Thông thường, Git tránh cập nhật một số ref theo hướng non-fast-forward vì điều đó có thể làm mất dấu một phần lịch sử đang được tham chiếu. Với remote-tracking ref, remote có thể đã được force-push hoặc branch đã được viết lại có chủ đích. Dấu `+` cho phép fetch cập nhật ref đích trong tình huống đó:

```text
+refs/heads/*:refs/remotes/origin/*
^
Cho phép force-update ref đích khi cần
```

Đây là lý do refspec fetch mặc định thường có dấu `+`. Nó chỉ điều khiển việc cập nhật ref local trong quá trình fetch; nó **không** force-push thay đổi lên máy chủ và không tự viết lại branch local `main`.

Nếu remote branch đã bị viết lại, sau fetch hãy kiểm tra lịch sử và phối hợp với nhóm trước khi tích hợp. Đừng mặc định rằng commit cũ đã biến mất khỏi mọi nơi: nó có thể vẫn được giữ bởi branch khác, tag, reflog hoặc bản clone của thành viên khác.

### 4.3. Negative refspec để loại trừ ref

Fetch hỗ trợ negative refspec có dạng:

```text
^<src>
```

Negative refspec loại trừ các ref khớp mẫu khỏi tập ref được lấy bởi những refspec dương. Nó không có phần đích. Ví dụ cấu hình:

```ini
[remote "origin"]
    fetch = +refs/heads/*:refs/remotes/origin/*
    fetch = ^refs/heads/archive/*
```

Ý nghĩa:

- Dòng đầu cho phép lấy các branch dưới `refs/heads/` và ánh xạ chúng vào `refs/remotes/origin/`.
- Dòng thứ hai loại trừ các branch khớp `refs/heads/archive/*` khỏi tập đó.

Negative refspec cần đi cùng ít nhất một refspec dương để xác định tập ref ban đầu. Cú pháp loại trừ này dùng trong cấu hình fetch; không áp dụng nó như một cách viết refspec push thông thường.

### 4.4. Fetch vào namespace local tùy chỉnh

Ta không bắt buộc phải lưu mọi branch remote theo đúng tên mặc định. Ví dụ, muốn fetch các branch release vào namespace `refs/remotes/origin/releases/`, có thể chạy:

```bash
git fetch origin "+refs/heads/release/*:refs/remotes/origin/releases/*"
```

Khi đó:

| Remote source | Local destination |
|---|---|
| `refs/heads/release/2.x` | `refs/remotes/origin/releases/2.x` |
| `refs/heads/release/3.x` | `refs/remotes/origin/releases/3.x` |

Đây là ánh xạ bổ sung do lệnh fetch chỉ định. Nếu muốn dùng thường xuyên, có thể cấu hình thêm một dòng `remote.origin.fetch`; cần kiểm tra các dòng hiện có trước khi thay đổi vì cấu hình có thể chứa nhiều refspec. Khi thêm một dòng, các refspec dương hiện có vẫn tiếp tục có hiệu lực, nên cùng một remote branch có thể được lưu ở nhiều đích local.

Ví dụ thêm ánh xạ bổ sung:

```bash
git config --add remote.origin.fetch "+refs/heads/release/*:refs/remotes/origin/releases/*"
git config --get-all remote.origin.fetch
```

Sau đó `git fetch origin` sẽ áp dụng tất cả refspec fetch đang cấu hình cho remote đó. Việc đổi namespace local không đổi tên branch trên máy chủ.

## 5. Push refspec: ánh xạ branch local lên remote

Với push, chiều ánh xạ ngược lại: nguồn nằm ở local, đích nằm trên remote. Cấu trúc vẫn là:

```text
[+]<src>:<dst>
```

Ví dụ, để đẩy branch local `feature/login` lên branch cùng tên trên remote `origin`:

```bash
git push origin refs/heads/feature/login:refs/heads/feature/login
```

Có thể viết gọn hơn:

```bash
git push origin feature/login
```

Trong cách viết đầy đủ, nguồn là `refs/heads/feature/login` trên local và đích là `refs/heads/feature/login` trên remote. Push cập nhật branch trên máy chủ nếu quyền truy cập và quy tắc cập nhật của remote cho phép.

### 5.1. Đẩy branch local sang tên khác trên remote

Refspec cho phép tên nguồn và đích khác nhau:

```bash
git push origin refs/heads/feature/login:refs/heads/review/login
```

Kết quả là branch `feature/login` ở local được dùng để cập nhật branch `review/login` trên remote. Sau khi người khác fetch theo cấu hình mặc định, họ có thể thấy remote-tracking ref `origin/review/login`.

Điều này hữu ích khi nhóm muốn đặt tên branch trên máy chủ theo quy ước riêng, hoặc muốn đẩy một branch thử nghiệm lên một tên tạm thời để review. Nó không đổi tên branch local `feature/login`.

### 5.2. Dấu `+` trong push

Với push, dấu `+` cho phép cập nhật ref đích theo hướng non-fast-forward:

```bash
git push origin +refs/heads/feature/login:refs/heads/feature/login
```

Đây là thao tác có thể thay đổi lịch sử mà người khác đang dựa vào. Chỉ sử dụng khi hiểu rõ ảnh hưởng và phù hợp chính sách nhóm. Trong các tình huống cần force push, thường nên ưu tiên:

```bash
git push --force-with-lease origin feature/login
```

`--force-with-lease` kiểm tra ref remote vẫn ở trạng thái mà local kỳ vọng trước khi cho phép cập nhật cưỡng bức, giúp giảm nguy cơ ghi đè commit mới do người khác vừa push. Nó vẫn là thao tác viết lại lịch sử và cần phối hợp với nhóm.

Lưu ý phân biệt: dấu `+` trong fetch refspec cho phép cập nhật remote-tracking ref local khi remote viết lại branch; dấu `+` trong push refspec cho phép ghi đè ref trên remote. Cùng một ký hiệu nhưng tác động nằm ở hai repository khác nhau.

### 5.3. Xóa branch remote bằng refspec

Trong push refspec, nếu bỏ trống nguồn và giữ đích, Git hiểu đó là yêu cầu xóa ref đích:

```bash
git push origin :refs/heads/feature/old-login
```

Cách viết dễ đọc hơn:

```bash
git push origin --delete feature/old-login
```

Lệnh xóa branch trên remote. Remote-tracking ref tương ứng trong local có thể còn tồn tại cho đến khi fetch có prune hoặc thực hiện prune riêng:

```bash
git fetch --prune origin
```

Xóa branch remote không tự xóa branch local cùng tên. Trước khi xóa, cần chắc chắn branch không còn được dùng trong pull request, pipeline hoặc công việc đang thực hiện.

## 6. Remote-tracking ref, upstream và branch local

Ba khái niệm này thường xuất hiện cùng nhau nhưng có vai trò riêng:

- **Local branch:** branch trong `refs/heads/`, ví dụ `main`.
- **Remote-tracking ref:** ref trong `refs/remotes/`, ví dụ `origin/main`, ghi nhận trạng thái branch được fetch từ remote.
- **Upstream branch:** branch mà local branch được cấu hình để theo dõi. Cấu hình này giúp Git biết nơi fetch/pull và so sánh mặc định cho branch đó.

Ví dụ, branch local `main` theo dõi `origin/main`. Git lưu quan hệ upstream bằng các cấu hình tương tự:

```ini
[branch "main"]
    remote = origin
    merge = refs/heads/main
```

`branch.main.merge` chỉ tên branch ở phía remote; `remote.origin.fetch` ánh xạ branch đó thành remote-tracking ref local `refs/remotes/origin/main`. Hai cấu hình phối hợp để Git biết `main` theo dõi `origin/main`.

Có thể thiết lập upstream bằng:

```bash
git branch --set-upstream-to=origin/main main
```

Hoặc khi push branch mới lần đầu:

```bash
git push -u origin feature/login
```

Tùy chọn `-u` (hay `--set-upstream`) ghi cấu hình theo dõi cho branch hiện tại sau khi push thành công.

Kiểm tra quan hệ upstream:

```bash
git branch -vv
```

Lệnh này hiển thị branch local, commit hiện tại và thông tin upstream nếu đã cấu hình. Upstream không phải một bản sao commit khác; đó là quan hệ cấu hình giữa branch local và branch ở remote, thường được biểu diễn qua remote-tracking ref.

## 7. Các lệnh quan sát và chẩn đoán ánh xạ refs

Khi branch hoặc remote-tracking ref không xuất hiện như mong đợi, nên kiểm tra từ cấu hình đến dữ liệu thực tế.

### 7.1. Xem các remote và refspec

```bash
# Xem tên remote và URL fetch/push
git remote -v

# Xem mọi refspec fetch của origin
git config --get-all remote.origin.fetch

# Xem cấu hình branch hiện tại
git config --get-regexp '^branch\.'
```

Nếu `remote.origin.fetch` chỉ chứa một branch cụ thể, chẳng hạn:

```text
+refs/heads/main:refs/remotes/origin/main
```

thì `git fetch origin` chỉ cập nhật mapping đã cấu hình đó. Các branch khác trên máy chủ có thể không xuất hiện trong `git branch -r` vì chúng chưa được fetch theo refspec hiện tại.

### 7.2. Xem ref local và remote-tracking ref

```bash
# Chỉ branch local
git for-each-ref --format="%(refname) %(objectname:short)" refs/heads/

# Chỉ remote-tracking ref
git for-each-ref --format="%(refname) %(objectname:short)" refs/remotes/

# Xem object ID mà tên ref phân giải tới
git rev-parse refs/heads/main
git rev-parse refs/remotes/origin/main
```

Nếu hai lệnh `rev-parse` cuối trả về hai mã commit khác nhau thì hai ref đang trỏ tới hai commit khác nhau. Đây là trạng thái bình thường khi branch local chưa tích hợp thay đổi mới từ remote hoặc local có commit riêng.

### 7.3. So sánh branch local với remote-tracking ref

```bash
# Xem commit chỉ có ở một phía
git log --oneline --left-right main...origin/main

# Xem số commit ahead/behind qua upstream
git status -sb

# Xem branch local và upstream
git branch -vv
```

Trước khi so sánh, hãy fetch để cập nhật thông tin remote-tracking ref. Nếu không fetch, `origin/main` chỉ phản ánh lần fetch gần nhất và có thể đã cũ so với trạng thái máy chủ.

### 7.4. Kiểm tra branch máy chủ đang quảng bá

```bash
git ls-remote --heads origin
```

So sánh kết quả với `git branch -r` và refspec đã cấu hình:

- Nếu máy chủ có branch nhưng local không có remote-tracking ref, hãy kiểm tra refspec fetch có khớp branch đó không.
- Nếu refspec khớp nhưng vẫn chưa có ref local, chạy `git fetch origin` và đọc thông báo lỗi xác thực, quyền hoặc kết nối nếu có.
- Nếu remote branch đã bị xóa nhưng remote-tracking ref local còn, kiểm tra prune.

## 8. Prune và ref đã bị xóa trên remote

Khi một branch bị xóa trên remote, ref local `refs/remotes/origin/<branch>` có thể còn sót lại. Git không tự xóa mọi remote-tracking ref cũ trong mọi lần fetch mặc định. Dùng:

```bash
git fetch --prune origin
```

để xóa remote-tracking ref tương ứng với ref remote không còn tồn tại, trong phạm vi các mapping fetch có liên quan. Có thể cấu hình prune cho remote:

```bash
git config remote.origin.prune true
```

Hoặc cấu hình mặc định cho mọi remote:

```bash
git config fetch.prune true
```

Prune tác động tới remote-tracking ref local theo mapping; nó không xóa branch local trong `refs/heads/`. Nếu có nhiều refspec hoặc mapping tùy chỉnh, hãy xem kỹ cấu hình và phạm vi prune trước khi bật tự động.

Lệnh xem trước hữu ích:

```bash
git fetch --prune --dry-run origin
```

Đọc kết quả trước khi thực hiện prune thực tế nếu repository có cấu hình refspec phức tạp.

## 9. Tag và các namespace khác

Tag thường nằm trong namespace `refs/tags/`, tách biệt với branch `refs/heads/` và remote-tracking ref `refs/remotes/`. Cấu hình fetch branch mặc định:

```text
+refs/heads/*:refs/remotes/origin/*
```

không có nghĩa là ánh xạ toàn bộ tag sang `refs/remotes/origin/`. Git có cơ chế tự động lấy các tag trỏ tới đối tượng được tải về trong một số trường hợp; nếu muốn lấy tất cả tag từ remote, có thể dùng:

```bash
git fetch origin --tags
```

Hoặc chỉ rõ refspec tag:

```bash
git fetch origin "+refs/tags/*:refs/tags/*"
```

Khi push tag cụ thể:

```bash
git push origin refs/tags/v1.2.0:refs/tags/v1.2.0
```

Tag là một loại ref khác branch. Đừng dùng refspec branch `refs/heads/*` để suy luận rằng tag cũng được ánh xạ theo cùng quy tắc.

## 10. Các lỗi hiểu nhầm thường gặp

### 10.1. Nghĩ rằng `origin/main` là branch trên máy chủ

`origin/main` thường là ref local trong `refs/remotes/origin/main`. Branch trên remote có tên đầy đủ `refs/heads/main`. Fetch là thao tác cập nhật bản ghi local đó từ remote.

### 10.2. Nghĩ rằng fetch sẽ cập nhật branch local `main`

Fetch cập nhật đích theo fetch refspec, thường là `refs/remotes/origin/*`. Nó không tự cập nhật `refs/heads/main`. Muốn tích hợp, hãy merge hoặc rebase remote-tracking ref vào branch local.

### 10.3. Nghĩ rằng mọi branch trên remote đều xuất hiện sau fetch

`git fetch origin` áp dụng các refspec đã cấu hình cho `origin`. Nếu cấu hình chỉ lấy `main`, các branch khác có thể không được ánh xạ vào local. Kiểm tra bằng `git config --get-all remote.origin.fetch`.

### 10.4. Nhầm chiều nguồn và đích

Trong fetch, nguồn ở remote và đích ở local. Trong push, nguồn ở local và đích ở remote. Hãy ghi chú chiều dữ liệu trước khi tự viết refspec.

### 10.5. Nghĩ rằng dấu `+` luôn có cùng mức độ ảnh hưởng

Trong fetch, `+` cho phép cập nhật remote-tracking ref local theo hướng non-fast-forward. Trong push, `+` cho phép cập nhật cưỡng bức ref trên remote. Hãy xác định lệnh đang chạy và repository bị cập nhật trước khi dùng.

### 10.6. Xóa branch remote nhưng vẫn thấy `origin/branch`

Remote-tracking ref local có thể còn cũ sau khi branch remote bị xóa. Chạy `git fetch --prune origin` để dọn ref đã hết tương ứng. Branch local cùng tên vẫn tồn tại cho đến khi ta xóa riêng.

## 11. Quy trình thực hành: theo dõi branch từ remote

Giả sử nhóm có remote `origin` với các branch `main`, `develop` và `feature/search`. Ta muốn kiểm tra mapping, cập nhật thông tin, tạo branch local theo dõi `develop` và đẩy branch tính năng lên máy chủ.

### Bước 1: Kiểm tra remote và fetch refspec

```bash
git remote -v
git config --get-all remote.origin.fetch
```

Xác nhận remote `origin` trỏ đúng repository và cấu hình fetch có ánh xạ branch cần theo dõi. Với cấu hình wildcard mặc định, các branch dưới `refs/heads/` sẽ được ánh xạ sang `refs/remotes/origin/`.

### Bước 2: Fetch và xem remote-tracking refs

```bash
git fetch --prune origin
git branch -r
```

Ta có thể thấy `origin/main`, `origin/develop` và `origin/feature/search` nếu các branch đó được remote quảng bá và khớp refspec.

### Bước 3: Tạo branch local theo dõi `origin/develop`

```bash
git switch --track -c develop origin/develop
```

Git tạo branch local `develop` trong `refs/heads/develop` và thiết lập upstream tới `origin/develop`. Hai ref vẫn độc lập, nhưng Git biết quan hệ theo dõi giữa chúng.

### Bước 4: Tạo branch tính năng và commit

```bash
git switch -c feature/search develop
# chỉnh sửa mã nguồn
git add src/
git commit -m "feat: add search feature"
```

Branch `feature/search` là branch local dưới `refs/heads/feature/search`.

### Bước 5: Push và thiết lập upstream

```bash
git push -u origin feature/search
```

Git dùng branch local làm nguồn và tạo/cập nhật branch `refs/heads/feature/search` trên remote. Sau khi push thành công, Git ghi quan hệ upstream cho branch local. Ở các lần làm việc sau, `git status -sb` và `git branch -vv` giúp kiểm tra quan hệ đó.

### Bước 6: Fetch thay đổi mới và tích hợp

Khi đồng đội cập nhật `develop`:

```bash
git fetch origin
git switch develop
git log --oneline --left-right develop...origin/develop
```

Sau khi xem các commit, chọn merge hoặc rebase theo quy ước nhóm:

```bash
git merge origin/develop
```

Nếu có conflict, giải quyết từng tệp, kiểm tra kết quả rồi hoàn tất merge. Việc fetch đã cập nhật remote-tracking ref; merge mới là bước tích hợp thay đổi vào branch local.

## 12. Ghi nhớ

- `refs/heads/` chứa branch trong repository đang xét. `refs/heads/main` trên local và `refs/heads/main` trên remote là hai ref ở hai repository khác nhau.
- `refs/remotes/<remote>/` chứa remote-tracking ref local, ví dụ `refs/remotes/origin/main`; tên viết gọn là `origin/main`.
- Refspec có dạng tổng quát `[+]<src>:<dst>`. Với fetch, nguồn ở remote và đích ở local; với push, nguồn ở local và đích ở remote.
- Fetch refspec mặc định thường gặp là `+refs/heads/*:refs/remotes/origin/*`, ánh xạ các branch remote thành remote-tracking ref local.
- Fetch cập nhật ref đích theo mapping; merge hoặc rebase mới tích hợp lịch sử vào branch local.
- Upstream là quan hệ cấu hình giữa branch local và branch remote được theo dõi; nó phối hợp với remote fetch refspec.
- `git config --get-all remote.origin.fetch`, `git branch -r`, `git branch -vv`, `git show-ref` và `git ls-remote --heads origin` giúp chẩn đoán mapping.
- `git fetch --prune origin` dọn remote-tracking ref đã bị xóa khỏi remote; nó không xóa branch local.

Khi cần tự viết hoặc sửa refspec, hãy xác định rõ ref nguồn, ref đích, repository chứa mỗi ref và chiều dữ liệu. Từ đó, việc đọc `origin/main`, kiểm soát branch được fetch, đẩy branch theo tên khác hoặc xử lý ref cũ sẽ trở nên dễ dự đoán hơn.
