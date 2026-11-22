# Nhánh, HEAD, remote và nhánh theo dõi từ xa

Khi làm việc với Git, ta thường tạo nhánh để phát triển tính năng, sửa lỗi hoặc thử nghiệm mà không làm gián đoạn nhánh chính. Khi nhiều người cùng làm việc, mỗi máy có thể có các nhánh cục bộ riêng, đồng thời trao đổi commit với một hoặc nhiều kho lưu trữ từ xa. Để phối hợp an toàn, cần hiểu nhánh đang trỏ tới commit nào, `HEAD` đang đại diện cho vị trí nào, remote lưu địa chỉ gì và nhánh theo dõi từ xa phản ánh trạng thái nào.

Trong học phần Git thuộc dịch vụ quản lý mã nguồn, các khái niệm này nối liền quá trình làm việc từ working tree, staging area và commit đến merge, rebase, remote và tag. Nắm vững chúng giúp ta cộng tác qua nhánh, nhận biết thay đổi từ đồng đội và giữ lịch sử dự án dễ truy vết.

## 1. Nhánh trong Git là gì?

Một nhánh (branch) là một tham chiếu có tên trỏ tới một commit. Ví dụ, nhánh `main` thường trỏ tới commit mới nhất của dòng phát triển chính; nhánh `feature/login` trỏ tới commit mới nhất của công việc xây dựng chức năng đăng nhập.

Nhánh trong Git rất nhẹ: tạo nhánh chủ yếu là tạo một tham chiếu mới tới commit hiện tại. Khi tạo commit mới trên nhánh đang đứng, Git di chuyển tham chiếu của nhánh đó tới commit mới. Các commit cũ vẫn được giữ nguyên và có thể được dùng chung giữa nhiều nhánh.

Hãy hình dung lịch sử có dạng sau:

```text
                 C3  main
                /
C0 --- C1 --- C2
                \
                 C4  feature/login
```

`main` và `feature/login` cùng bắt đầu từ `C2`, sau đó phát triển độc lập. Mỗi nhánh chỉ là một tên trỏ tới commit đầu nhánh; nhánh không phải bản sao đầy đủ của thư mục dự án. Working tree sẽ được Git cập nhật khi ta chuyển nhánh.

### Vì sao cần dùng nhánh?

- **Tách công việc:** một tính năng mới có thể được triển khai trong `feature/...` mà chưa ảnh hưởng đến `main`.
- **Làm song song:** nhiều người hoặc nhiều nhóm có thể phát triển các phần khác nhau rồi tích hợp sau.
- **Dễ thử nghiệm và sửa lỗi:** có thể tạo nhánh ngắn hạn để thử một hướng giải quyết, sau đó merge hoặc bỏ nhánh.
- **Dễ xem xét thay đổi:** pull request hoặc merge request thường so sánh một nhánh công việc với nhánh đích.
- **Giữ lịch sử có ý nghĩa:** tên nhánh mô tả mục đích của dòng công việc, giúp thành viên nhận biết phạm vi thay đổi.

Tên nhánh thường dùng chữ thường và dấu gạch nối hoặc dấu gạch chéo, chẳng hạn `feature/user-profile`, `bugfix/payment-timeout`, `hotfix/security-patch` và `release/2.4`. Nên tránh tên mơ hồ như `test`, `new` hoặc `fix` nếu chúng không giúp nhận diện mục đích.

## 2. Tạo, xem và chuyển nhánh cục bộ

Các lệnh dưới đây thao tác với nhánh trong repository hiện tại.

| Nhu cầu | Lệnh | Ý nghĩa |
| --- | --- | --- |
| Liệt kê nhánh cục bộ | `git branch` | Hiển thị các nhánh local; dấu `*` đánh dấu nhánh hiện tại |
| Xem tên nhánh hiện tại | `git branch --show-current` | Trả về tên nhánh nếu `HEAD` đang gắn với một nhánh |
| Tạo nhánh tại commit hiện tại | `git branch feature/login` | Tạo nhánh nhưng vẫn ở nhánh hiện tại |
| Tạo và chuyển sang nhánh mới | `git switch -c feature/login` | Tạo nhánh mới rồi chuyển working tree sang nhánh đó |
| Chuyển sang nhánh có sẵn | `git switch main` | Đưa `HEAD` về nhánh `main` và cập nhật working tree |
| Đổi tên nhánh hiện tại | `git branch -m feature/authentication` | Đổi tên nhánh đang đứng |
| Xóa nhánh đã được tích hợp | `git branch -d feature/login` | Xóa tham chiếu local khi Git xác nhận nhánh đã được merge an toàn |

Ví dụ tạo nhánh để làm chức năng đăng nhập:

```bash
git switch main
git switch -c feature/login
git branch --show-current
```

Lệnh đầu tiên đưa ta về `main`; lệnh thứ hai tạo `feature/login` từ commit hiện tại của `main` và chuyển sang nhánh đó. Các commit tiếp theo sẽ cập nhật đầu nhánh `feature/login`.

`git branch feature/login` chỉ tạo tên nhánh. Nếu muốn làm việc trên nhánh vừa tạo, cần chuyển sang nó bằng `git switch feature/login`. Cách viết cũ `git checkout -b feature/login` vẫn thường gặp; với Git hiện đại, `git switch` diễn đạt rõ mục đích chuyển nhánh hơn.

### Xóa nhánh và kiểm tra nhánh đã tích hợp

```bash
git branch --merged main
git branch --no-merged main
git branch -d feature/login
```

Hai lệnh đầu liệt kê các nhánh đã hoặc chưa được tích hợp vào `main`. `git branch -d` yêu cầu Git kiểm tra tính an toàn trước khi xóa. Lệnh `git branch -D feature/login` bỏ qua kiểm tra đó và xóa tham chiếu ngay cả khi nhánh chưa được merge; chỉ dùng khi đã xác nhận không cần các commit riêng của nhánh. Xóa nhánh không đồng nghĩa xóa ngay các đối tượng commit, nhưng nếu commit không còn được tham chiếu hoặc reachable từ nơi nào khác, Git có thể dọn chúng sau này.

## 3. HEAD đại diện cho vị trí hiện tại

`HEAD` là tham chiếu đặc biệt cho biết vị trí hiện tại mà repository đang làm việc. Trong trường hợp thông thường, `HEAD` trỏ gián tiếp tới nhánh hiện tại. Ví dụ, khi đang ở `main`, nội dung logic của `HEAD` là tham chiếu tới `refs/heads/main`; bản thân `refs/heads/main` lại trỏ tới commit đầu nhánh.

```text
HEAD -> refs/heads/main -> commit C3
```

Khi tạo commit mới trên `main`, Git cập nhật `refs/heads/main` sang commit mới. Vì `HEAD` trỏ tới tên nhánh, `HEAD` tự động đi theo commit mới mà không cần thay đổi thủ công.

Một số lệnh giúp kiểm tra vị trí hiện tại:

```bash
git status -sb
git branch --show-current
git rev-parse --short HEAD
git symbolic-ref --short HEAD
```

`git status -sb` hiển thị nhánh và trạng thái working tree ở dạng ngắn. `git rev-parse --short HEAD` cho biết mã rút gọn của commit hiện tại. `git symbolic-ref --short HEAD` cho biết tên tham chiếu mà `HEAD` đang trỏ tới; lệnh này không thành công khi đang ở detached HEAD.

### Detached HEAD là gì?

Detached HEAD (HEAD tách rời) xảy ra khi `HEAD` trỏ trực tiếp tới một commit thay vì trỏ tới tên nhánh. Điều này có thể xảy ra khi checkout một mã commit, tag hoặc một remote-tracking branch theo cách không tạo nhánh local.

```bash
git switch --detach <commit-id>
```

Ở trạng thái này, ta vẫn có thể đọc mã nguồn, chạy thử và thậm chí tạo commit. Tuy nhiên, commit mới không tự động làm tiến nhánh local nào tiến lên, vì `HEAD` không gắn với một nhánh. Nếu chuyển sang vị trí khác mà không lưu lại tham chiếu, commit vừa tạo có thể khó tìm hơn dù thường vẫn còn trong reflog một thời gian.

Nếu muốn giữ công việc đang làm trong detached HEAD, hãy tạo nhánh tại vị trí hiện tại:

```bash
git switch -c rescue/keep-experiment
```

Lệnh này tạo `rescue/keep-experiment` trỏ tới commit hiện tại và chuyển `HEAD` sang nhánh mới. Ta có thể tiếp tục commit như bình thường.

## 4. Remote là gì?

Remote là tên cấu hình trong repository local đại diện cho một repository khác, thường nằm trên máy chủ Git hoặc dịch vụ lưu trữ mã nguồn. Remote cho Git biết địa chỉ cần dùng khi lấy hoặc gửi commit. Remote không phải một nhánh và cũng không phải bản sao tự đồng bộ liên tục.

Tên `origin` là quy ước phổ biến mà `git clone` tự tạo cho repository nguồn. Ta có thể đặt tên khác như `upstream`, `company` hoặc `mirror` khi dự án cần nhiều remote. Tên remote chỉ có ý nghĩa trong cấu hình của repository local.

### Xem và quản lý remote

```bash
git remote
git remote -v
git remote add origin https://example.com/team/project.git
git remote get-url origin
git remote set-url origin https://example.com/team/project-new.git
git remote rename origin upstream
git remote remove upstream
```

- `git remote` liệt kê tên remote đã cấu hình.
- `git remote -v` hiển thị URL dùng để fetch và push. Hai URL có thể giống hoặc khác nhau.
- `git remote add` đăng ký một remote mới với tên và URL.
- `git remote get-url` đọc URL đã cấu hình.
- `git remote set-url` thay URL cho remote hiện có.
- `git remote rename` đổi tên cấu hình remote.
- `git remote remove` xóa cấu hình remote và các remote-tracking ref tương ứng trong repository local; lệnh này không xóa repository trên máy chủ.

Ví dụ khi làm việc với repository được fork:

```bash
git remote -v
git remote add upstream https://example.com/original/project.git
git fetch upstream
```

Trong ví dụ, `origin` thường là repository fork của cá nhân hoặc nhóm, còn `upstream` là repository gốc. Ta fetch từ `upstream` để biết các thay đổi mới nhất của dự án gốc.

## 5. Nhánh từ xa và nhánh theo dõi từ xa

Trên máy chủ có các nhánh thật của repository, ví dụ `main` hoặc `feature/login`. Khi fetch, Git cập nhật các tham chiếu local phản ánh trạng thái gần nhất mà máy local đã biết của những nhánh đó. Các tham chiếu local này được gọi là **remote-tracking branch** (nhánh theo dõi từ xa).

Ví dụ `origin/main` là remote-tracking branch của nhánh `main` trên remote tên `origin`. Trong repository local, nó thường được lưu dưới dạng `refs/remotes/origin/main`.

Phân biệt ba đối tượng sau:

| Tên | Nằm ở đâu? | Vai trò |
| --- | --- | --- |
| `main` | Repository local | Nhánh local mà ta có thể commit trực tiếp khi đang đứng trên đó |
| `main` trên remote `origin` | Repository máy chủ | Nhánh thật được các thành viên chia sẻ trên remote |
| `origin/main` | Repository local | Remote-tracking ref ghi nhận trạng thái nhánh `main` của `origin` ở lần cập nhật gần nhất |

`origin/main` không phải là nhánh local để ta commit trực tiếp. Nó là mốc tham chiếu để so sánh hoặc tích hợp thay đổi từ remote. Ta có thể xem các nhánh đã biết bằng:

```bash
git branch -r
git branch -a
```

`git branch -r` liệt kê remote-tracking branches. `git branch -a` liệt kê cả nhánh local và remote-tracking branches. Danh sách này phản ánh những tham chiếu mà repository local đã biết; nếu remote có nhánh mới nhưng ta chưa fetch, nhánh đó có thể chưa xuất hiện.

### Cập nhật remote-tracking branches bằng fetch

```bash
git fetch origin
```

`git fetch origin` liên hệ với remote `origin`, tải về các đối tượng Git cần thiết và cập nhật remote-tracking refs theo cấu hình fetch. Lệnh này không tự merge hoặc rebase thay đổi vào nhánh local đang đứng, cũng không tự thay nội dung working tree. Vì vậy, fetch là bước an toàn để xem remote có gì mới trước khi quyết định tích hợp.

Để lấy thông tin từ tất cả remote và dọn các remote-tracking ref đã bị xóa trên máy chủ:

```bash
git fetch --all --prune
```

`--all` fetch từ tất cả remote đã cấu hình; `--prune` loại bỏ các remote-tracking ref không còn nhánh tương ứng trên remote theo refspec. Có thể dùng `git remote prune origin` để dọn riêng các tham chiếu cũ của một remote.

Nếu cần kiểm tra nhánh đang tồn tại trên máy chủ mà không dựa vào danh sách đã fetch trong local, có thể truy vấn:

```bash
git ls-remote --heads origin
```

Lệnh này liệt kê các nhánh trên remote `origin` tại thời điểm truy vấn. Kết quả truy vấn không tự cập nhật các remote-tracking refs trong repository local; dùng `git fetch` để cập nhật chúng.

## 6. Upstream và quan hệ tracking

Một nhánh local có thể được cấu hình để theo dõi một nhánh từ xa, thường gọi là upstream branch. Ví dụ, `main` local có thể theo dõi `origin/main`; `feature/login` local có thể theo dõi `origin/feature/login`.

Quan hệ upstream giúp Git biết nhánh nào cần so sánh khi hiển thị trạng thái ahead/behind, và biết nguồn mặc định cho các lệnh `git pull` hoặc đích mặc định cho một số cách gọi `git push`. Quan hệ này là cấu hình giữa nhánh local và remote-tracking branch; nó không làm hai nhánh tự đồng bộ.

### Thiết lập upstream khi push lần đầu

```bash
git switch -c feature/login
# chỉnh sửa, stage và commit các thay đổi
git add src/
git commit -m "Add login feature"
git push -u origin feature/login
```

`git push -u origin feature/login` gửi nhánh `feature/login` lên remote `origin` và thiết lập upstream cho nhánh local hiện tại. Tùy chọn `-u` là viết tắt của `--set-upstream`. Sau đó, khi đang ở `feature/login`, ta có thể dùng `git push` hoặc `git pull` mà không cần lặp lại tên remote và tên nhánh trong các trường hợp thông thường.

Nếu nhánh đã tồn tại và cần gắn upstream thủ công:

```bash
git branch --set-upstream-to=origin/feature/login feature/login
```

Kiểm tra các nhánh và upstream:

```bash
git branch -vv
```

Kết quả thường hiển thị commit đầu nhánh, tên upstream trong ngoặc vuông và thông tin ahead/behind nếu có. Thông tin ahead/behind dựa trên remote-tracking ref local hiện có; hãy fetch trước nếu cần so sánh với trạng thái mới nhất trên máy chủ.

Có thể bỏ quan hệ upstream của một nhánh bằng:

```bash
git branch --unset-upstream feature/login
```

Upstream không nhất thiết phải có cùng tên với nhánh local. Ví dụ, nhánh local `work` có thể theo dõi `origin/develop` nếu cấu hình như vậy.

## 7. Phân biệt fetch, pull và push

Ba thao tác này thường được dùng khi cộng tác, nhưng mục tiêu của chúng khác nhau.

| Lệnh | Hướng trao đổi chính | Tác động thường thấy trong local |
| --- | --- | --- |
| `git fetch origin` | Remote → local | Tải dữ liệu và cập nhật remote-tracking refs; không tích hợp vào nhánh hiện tại |
| `git pull` | Remote → local | Fetch rồi tích hợp vào nhánh hiện tại bằng merge hoặc rebase theo cấu hình/tùy chọn |
| `git push origin feature/login` | Local → remote | Gửi commit và cập nhật nhánh trên remote nếu việc cập nhật được chấp nhận |

### Fetch trước, xem rồi mới tích hợp

Một quy trình dễ kiểm soát là:

```bash
git fetch origin
git log --oneline --graph --decorate --all -15
git status -sb
```

Sau fetch, có thể so sánh `main` local với `origin/main`, xem các commit mới và quyết định merge hoặc rebase. Ví dụ, nếu `main` local chỉ cần tiến nhanh tới `origin/main`:

```bash
git switch main
git merge --ff-only origin/main
```

`--ff-only` chỉ cho phép fast-forward. Nếu hai nhánh đã phân kỳ và cần tạo merge commit hoặc rebase, lệnh sẽ dừng thay vì tự chọn cách tích hợp.

### Pull tích hợp thay đổi như thế nào?

`git pull` về cơ bản thực hiện fetch rồi tích hợp nhánh upstream vào nhánh hiện tại. Cách tích hợp có thể là merge hoặc rebase tùy cấu hình và tùy chọn. Có thể chỉ rõ lựa chọn để lệnh dễ dự đoán hơn:

```bash
git pull --ff-only
git pull --rebase
```

`git pull --ff-only` chỉ cập nhật khi có thể fast-forward. `git pull --rebase` đặt các commit local chưa có trên upstream lên trên commit mới nhận được. Rebase làm thay đổi mã định danh commit được tạo lại; không nên tùy tiện rebase các commit đã chia sẻ và đang được người khác dựa vào.

### Push thay đổi lên remote

```bash
git push origin feature/login
```

Lệnh gửi commit mà nhánh local `feature/login` đang trỏ tới lên nhánh cùng tên trên `origin`. Nếu remote đã có commit mới khiến cập nhật không còn fast-forward, Git thường từ chối push để tránh ghi đè lịch sử. Khi đó, hãy fetch và tích hợp thay đổi cần thiết trước, rồi push lại.

## 8. Quy trình làm việc với nhánh trong nhóm

Một quy trình phổ biến khi phát triển tính năng có thể thực hiện như sau.

### Bước 1: Cập nhật nhánh nền

```bash
git fetch origin
git switch main
git merge --ff-only origin/main
```

Ta lấy trạng thái mới từ remote, chuyển về `main` local rồi fast-forward theo `origin/main`. Như vậy, nhánh tính năng mới sẽ bắt đầu từ nền cập nhật.

### Bước 2: Tạo nhánh công việc

```bash
git switch -c feature/user-profile
```

Tạo nhánh riêng cho tính năng hồ sơ người dùng. Tên nhánh thể hiện mục đích và giúp nhóm tìm kiếm công việc dễ hơn.

### Bước 3: Commit các thay đổi có ý nghĩa

```bash
git status
git add src/main/java/
git diff --cached
git commit -m "Add user profile page"
```

Trước khi commit, kiểm tra working tree và nội dung đã stage. Mỗi commit nên gom một thay đổi có mục đích rõ ràng để việc review, revert và truy vết dễ dàng.

### Bước 4: Đẩy nhánh lên remote và thiết lập upstream

```bash
git push -u origin feature/user-profile
```

Sau bước này, thành viên khác có thể fetch nhánh để review hoặc tiếp tục phối hợp. Ta có thể mở pull request/merge request từ `feature/user-profile` vào `main` theo quy trình của dự án.

### Bước 5: Cập nhật nhánh khi nhóm có commit mới

```bash
git fetch origin
git log --oneline --left-right main...origin/main
```

Nếu đang phát triển trên nhánh tính năng, có thể tích hợp `main` mới nhất vào nhánh đó bằng merge hoặc rebase:

```bash
git switch feature/user-profile
git merge origin/main
```

Hoặc, nếu nhóm thống nhất dùng rebase và các commit trên nhánh chưa được chia sẻ theo cách khiến việc viết lại lịch sử gây ảnh hưởng:

```bash
git switch feature/user-profile
git rebase origin/main
```

Merge giữ lại quan hệ phân nhánh và có thể tạo merge commit. Rebase phát lại các commit của nhánh hiện tại trên nền mới, tạo commit mới với mã định danh mới. Chọn cách nào cần nhất quán với quy ước cộng tác của nhóm.

### Bước 6: Dọn nhánh sau khi hoàn tất

Sau khi pull request/merge request đã được tích hợp, nhánh remote có thể được xóa theo chính sách của dự án. Nếu được phép xóa nhánh remote:

```bash
git push origin --delete feature/user-profile
git fetch --prune origin
```

Lệnh đầu xóa nhánh trên remote; lệnh sau dọn các remote-tracking refs đã cũ ở local. Nếu cần giữ bản local để tra cứu, chỉ xóa nhánh local sau khi đã xác nhận công việc được lưu và không còn cần tham chiếu đó:

```bash
git branch -d feature/user-profile
```

## 9. Sơ đồ quan hệ giữa HEAD, nhánh local và remote-tracking branch

Giả sử `main` local đang ở commit `C3`, nhánh tính năng đang ở `C4`, còn lần fetch gần nhất cho biết `origin/main` ở `C5`:

```text
                  C3 --- C4  feature/login
                 /
C0 --- C1 --- C2
                 \
                  C5  origin/main

HEAD -> refs/heads/feature/login -> C4
refs/heads/main -----------------> C3
refs/remotes/origin/main --------> C5
```

Trong sơ đồ, `HEAD` trỏ tới nhánh local `feature/login`; nhánh này trỏ tới `C4`. `main` local và `origin/main` là hai tham chiếu khác nhau, có thể trỏ tới hai commit khác nhau. Fetch có thể di chuyển `origin/main` khi remote có commit mới, nhưng không tự di chuyển `main` local hay thay đổi nhánh hiện tại.

Sau khi chạy `git switch main` và `git merge --ff-only origin/main` trong trường hợp có thể fast-forward, `main` local sẽ di chuyển tới `C5`. `feature/login` vẫn trỏ tới `C4` cho đến khi ta commit, merge hoặc rebase trên nhánh đó.

## 10. Một số nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu đúng |
| --- | --- |
| `origin` là tên bắt buộc của remote | `origin` chỉ là tên mặc định phổ biến; remote có thể mang tên khác |
| `origin/main` là nhánh trên máy chủ | Đây là remote-tracking ref nằm trong repository local, phản ánh trạng thái đã fetch gần nhất |
| `git fetch` đã cập nhật working tree | Fetch cập nhật dữ liệu và remote-tracking refs; muốn tích hợp vào nhánh local cần merge, rebase hoặc pull |
| `git branch -a` luôn hiển thị mọi nhánh trên máy chủ | Lệnh chỉ hiển thị các nhánh local và remote-tracking refs mà repository đã biết; cần fetch để cập nhật |
| `HEAD` luôn là tên nhánh hiện tại | Khi detached HEAD, `HEAD` trỏ trực tiếp tới commit |
| Xóa remote bằng `git remote remove` sẽ xóa repository trên máy chủ | Lệnh chỉ xóa cấu hình remote và tham chiếu theo dõi trong repository local |
| Tạo nhánh local đồng nghĩa nhánh đã được chia sẻ | Nhánh chỉ tồn tại trên local cho tới khi được push lên remote |

### Xử lý một số tình huống

**Không thấy nhánh của đồng đội:** fetch remote rồi kiểm tra lại danh sách remote-tracking branches.

```bash
git fetch origin
git branch -r
```

**Push bị từ chối vì non-fast-forward:** remote có lịch sử mà local chưa tích hợp. Fetch, kiểm tra khác biệt, merge hoặc rebase theo quy ước nhóm rồi push lại. Không dùng force push chỉ để làm biến mất thông báo lỗi.

```bash
git fetch origin
git log --oneline --graph --decorate --all -20
```

**Nhánh báo upstream đã gone:** nhánh upstream có thể đã bị xóa trên remote hoặc thông tin local đã cũ. Fetch với prune, kiểm tra lại nhánh và quyết định gắn upstream mới hay bỏ cấu hình cũ.

```bash
git fetch --prune origin
git branch -vv
```

**Đang ở detached HEAD nhưng đã tạo commit cần giữ:** tạo nhánh ngay tại vị trí hiện tại để giữ một tham chiếu rõ ràng.

```bash
git switch -c rescue/save-detached-work
```

## 11. Bộ lệnh kiểm tra nhanh

Khi cần hiểu repository đang ở trạng thái nào, có thể chạy nhóm lệnh sau:

```bash
# Vị trí hiện tại và trạng thái working tree
git status -sb
git branch --show-current
git rev-parse --short HEAD

# Các nhánh local và remote-tracking
git branch -vv
git branch -a

# Remote và URL
git remote -v

# Cập nhật thông tin từ remote
git fetch --all --prune

# Xem lịch sử các nhánh cùng lúc
git log --oneline --graph --decorate --all -20
```

Các lệnh kiểm tra này giúp trả lời lần lượt: đang ở nhánh nào, `HEAD` trỏ tới commit nào, nhánh local theo dõi upstream nào, remote nào đã được cấu hình và lịch sử các nhánh đang phân kỳ ra sao.

## 12. Thực hành

Thực hiện trong một repository thử nghiệm để quan sát sự thay đổi của các tham chiếu:

1. Tạo repository mới hoặc dùng một repository thử nghiệm đã có commit.
2. Tạo nhánh `feature/notes` bằng `git switch -c feature/notes`.
3. Tạo một file, stage và commit thay đổi trên nhánh này.
4. Chạy `git status -sb`, `git branch -vv` và `git log --oneline --graph --decorate --all` để xác định `HEAD` và đầu nhánh.
5. Cấu hình một remote phù hợp với repository thử nghiệm, sau đó push nhánh với `git push -u <remote> feature/notes`.
6. Fetch lại remote và quan sát `git branch -r`, `git branch -a`.
7. Từ một clone khác hoặc nhờ một thành viên khác tạo và push commit mới lên nhánh nền trên remote; quay lại repository đang thực hành rồi fetch để xem remote-tracking branch thay đổi thế nào.
8. Thử `git merge --ff-only <remote>/<branch>` trong một tình huống fast-forward và quan sát nhánh local sau khi tích hợp.

Sau khi thực hành, hãy tự giải thích vì sao `feature/notes`, `<remote>/feature/notes` và `HEAD` có thể trỏ tới cùng một commit ở một thời điểm nhưng vẫn là các tham chiếu khác nhau.

## 13. Tự kiểm tra kiến thức

1. Nhánh trong Git trỏ tới đối tượng nào, và điều gì xảy ra với tham chiếu nhánh khi tạo commit mới?
2. `HEAD` khác gì với tên nhánh local? Trạng thái detached HEAD xuất hiện trong trường hợp nào?
3. `origin` và `origin/main` đại diện cho hai loại thông tin nào?
4. Vì sao `git fetch origin` có thể cập nhật `origin/main` mà không thay đổi working tree?
5. Upstream branch hỗ trợ những thao tác nào khi làm việc với nhánh local?
6. `git pull` khác `git fetch` ở bước tích hợp thay đổi như thế nào?
7. Khi push bị từ chối do non-fast-forward, cần kiểm tra và xử lý điều gì trước khi gửi lại?

## Kết luận

Nhánh là tham chiếu local có thể di chuyển theo commit; `HEAD` xác định vị trí hiện tại; remote lưu thông tin kết nối tới repository khác; remote-tracking branch ghi nhận trạng thái nhánh từ xa mà local đã biết; upstream xác định nhánh từ xa mà một nhánh local theo dõi. Khi phân biệt được các đối tượng này, ta có thể fetch để cập nhật thông tin, xem lịch sử trước khi tích hợp, push để chia sẻ công việc và quản lý vòng đời nhánh một cách có kiểm soát.
