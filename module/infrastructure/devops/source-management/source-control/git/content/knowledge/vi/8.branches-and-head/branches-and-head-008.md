# Phân biệt nhánh cục bộ, nhánh từ xa và upstream

Khi làm việc với remote, Git có nhiều tên trông giống branch nhưng đại diện cho các đối tượng khác nhau. Ví dụ, `main` là một local branch, `origin/main` thường là remote-tracking branch được lưu trong repository local, còn “upstream của main” là nhánh mà local branch `main` được cấu hình để theo dõi. Ba khái niệm này liên quan với nhau nhưng không đồng nghĩa.

Hiểu đúng mối quan hệ giúp bạn biết lệnh `fetch` cập nhật gì, `pull` lấy dữ liệu từ đâu, `push` gửi branch nào và vì sao thông tin ahead/behind đôi khi chưa phản ánh trạng thái mới nhất trên server.

Bài học thuộc chương **Nhánh và HEAD** của module `SOURCE_CONTROL_GIT`. Module hướng dẫn working tree, staging area, commit, lịch sử, branch, merge, rebase, remote và tag; quản lý đúng local branch, remote-tracking branch và upstream là nền tảng để cộng tác an toàn qua nhiều remote.

## 1. Ba khái niệm cần phân biệt

| Khái niệm | Ví dụ | Nằm ở đâu? | Vai trò |
| --- | --- | --- | --- |
| Local branch | `main`, `feature/payment` | Repository local, ref `refs/heads/...` | Nhánh bạn trực tiếp checkout và tạo commit |
| Remote-tracking branch | `origin/main`, `upstream/develop` | Repository local, ref `refs/remotes/...` | Ghi nhớ trạng thái branch trên remote tại lần fetch gần nhất |
| Upstream branch | Upstream của local `main` có thể là `origin/main` | Được cấu hình cho từng local branch | Đích mặc định để so sánh ahead/behind và dùng trong pull/push theo cấu hình |

Một remote có tên `origin` không phải là một branch. `origin` chỉ là nickname của một remote repository. `origin/main` là remote-tracking branch tương ứng với branch `main` trên remote có tên `origin`.

Tương tự, từ “upstream” có hai cách dùng thường gặp:

- **Upstream branch**: branch mà một local branch được cấu hình để theo dõi.
- **Remote tên upstream**: nickname thường đặt cho repository gốc trong quy trình fork.

Đây là hai khái niệm độc lập. Upstream branch của local `feature/payment` có thể là `origin/feature/payment` dù không hề có remote tên `upstream`.

## 2. Local branch là gì?

Local branch là một ref trong repository local, thường nằm dưới `refs/heads/`. Nó trỏ đến commit hiện tại của nhánh. Khi bạn tạo commit trên branch đang checkout, ref branch sẽ di chuyển đến commit mới.

Liệt kê local branches:

~~~bash
git branch
~~~

Xem tên branch hiện tại:

~~~bash
git branch --show-current
~~~

Xem commit mà branch hiện tại trỏ tới:

~~~bash
git rev-parse HEAD
~~~

Tạo local branch mới:

~~~bash
git branch feature/payment
~~~

Lệnh trên tạo branch nhưng không chuyển sang branch mới. Để tạo và chuyển ngay:

~~~bash
git switch -c feature/payment
~~~

Local branch là nơi bạn thường tạo commit, merge hoặc rebase. Bạn có thể đổi tên branch, xóa branch đã merge hoặc giữ branch làm mốc công việc theo quy ước của nhóm.

## 3. Remote và remote-tracking branch

Remote là cấu hình chỉ đến một repository khác. Khi clone, Git thường tạo remote có tên `origin`:

~~~bash
git remote -v
~~~

Ví dụ:

~~~text
origin  https://example.com/team/app.git (fetch)
origin  https://example.com/team/app.git (push)
~~~

Tên `origin` chỉ là tên quy ước. Bạn có thể thêm remote khác:

~~~bash
git remote add upstream https://example.com/platform/app.git
git remote -v
~~~

Git lưu các remote-tracking refs ở local. Ví dụ branch `main` trên remote `origin` thường được biểu diễn bằng:

~~~text
refs/remotes/origin/main
~~~

Khi hiển thị ngắn, Git dùng tên `origin/main`.

Liệt kê remote-tracking branches:

~~~bash
git branch --remotes
~~~

Liệt kê cả local branch và remote-tracking branch:

~~~bash
git branch --all
~~~

### Remote-tracking branch không phải branch đang chạy trên server

`origin/main` là bản ghi local về trạng thái branch `main` trên remote tại lần fetch gần nhất. Nó không tự cập nhật theo thời gian thực khi ai đó push lên server.

Ví dụ:

1. Lần fetch gần nhất, `origin/main` trỏ đến commit A.
2. Một đồng đội push commit B lên branch `main` trên server.
3. Máy bạn vẫn hiển thị `origin/main` trỏ đến A cho đến khi fetch.
4. Sau `git fetch origin`, Git cập nhật remote-tracking ref thành B.

Vì vậy, khi muốn biết trạng thái mới nhất mà server công bố, hãy fetch trước khi kết luận branch local đang ahead hoặc behind.

Để hỏi trực tiếp các branch mà remote đang công bố mà không dựa vào cache remote-tracking local:

~~~bash
git ls-remote --heads origin
~~~

Lệnh này liệt kê refs branch từ remote. Nó không tự cập nhật các remote-tracking refs trong repository local.

## 4. Upstream branch là gì?

Upstream branch là branch được cấu hình làm nhánh theo dõi cho một local branch. Trong quy trình phổ biến, upstream của local `main` là `origin/main`.

Cấu hình upstream giúp Git biết:

- Branch nào dùng để tính trạng thái ahead/behind.
- Branch nào được `git pull` dùng khi bạn không chỉ định nguồn.
- Branch đích mặc định cho một số cách dùng `git push`, tùy cấu hình push.

Upstream không phải bản sao thứ hai của local branch. Nó là quan hệ cấu hình giữa local branch và một nhánh khác.

### Xem upstream của branch

Dùng:

~~~bash
git branch -vv
~~~

Ví dụ:

~~~text
* main             a1b2c3d [origin/main: ahead 2] Update invoice flow
  feature/payment  e4f5a6b [origin/feature/payment: behind 1] Add payment form
~~~

Trong ví dụ:

- Local `main` có upstream là `origin/main` và đang ahead 2 commit theo thông tin local hiện có.
- Local `feature/payment` có upstream là `origin/feature/payment` và đang behind 1 commit.

Các con số này được tính từ những refs local hiện có. Nếu chưa fetch gần đây, chúng có thể đã cũ.

Xem upstream của branch hiện tại bằng:

~~~bash
git rev-parse --abbrev-ref --symbolic-full-name '@{upstream}'
~~~

Nếu branch hiện tại chưa cấu hình upstream, lệnh này báo lỗi vì không thể phân giải `@{upstream}`.

### Xem cấu hình upstream chi tiết

Git lưu quan hệ theo các khóa cấu hình như:

- `branch.main.remote`: remote mà branch `main` theo dõi, ví dụ `origin`.
- `branch.main.merge`: ref branch ở remote, ví dụ `refs/heads/main`.

Kiểm tra:

~~~bash
git config --get branch.main.remote
git config --get branch.main.merge
~~~

Xem các branch đã có cấu hình remote/merge:

~~~bash
git config --get-regexp '^branch\..*\.(remote|merge)$'
~~~

Cấu hình này giúp Git phân giải upstream. Nếu remote hoặc branch đích bị đổi tên/xóa, quan hệ tracking có thể không còn hợp lệ.

## 5. Tạo local branch có upstream ngay từ đầu

Khi clone repository, Git thường thiết lập local branch mặc định theo dõi remote-tracking branch tương ứng. Với branch mới, bạn có thể tạo quan hệ tracking ngay khi tạo branch.

### Tạo branch từ remote-tracking branch và chuyển sang

~~~bash
git switch --track origin/feature/payment
~~~

Git tạo local branch `feature/payment` từ `origin/feature/payment` và cấu hình upstream tương ứng nếu tên branch có thể được suy ra duy nhất.

Nếu muốn chỉ định rõ tên local branch:

~~~bash
git switch --create feature/payment --track origin/feature/payment
~~~

### Tạo branch nhưng chưa chuyển sang

~~~bash
git branch --track feature/payment origin/feature/payment
~~~

Lệnh này tạo local branch và đặt upstream nhưng giữ nguyên branch đang checkout.

### Tạo branch mới từ branch hiện tại

~~~bash
git switch -c feature/payment
~~~

Lệnh này tạo local branch mới từ commit hiện tại. Upstream chưa được cấu hình tự động trong mọi trường hợp. Sau khi push lần đầu, bạn có thể thiết lập upstream bằng:

~~~bash
git push --set-upstream origin feature/payment
~~~

Viết tắt:

~~~bash
git push -u origin feature/payment
~~~

Tùy chọn `-u` lưu quan hệ tracking cho local branch, thường là `branch.feature/payment.remote=origin` và `branch.feature/payment.merge=refs/heads/feature/payment`.

## 6. Gắn hoặc thay đổi upstream cho branch đã có

Nếu local branch đã tồn tại nhưng chưa có upstream, hoặc bạn muốn đổi upstream sang branch khác, dùng:

~~~bash
git branch --set-upstream-to=origin/main main
~~~

Lệnh trên đặt `origin/main` làm upstream cho local branch `main`. Nếu bỏ tên local branch cuối cùng, Git dùng branch hiện tại:

~~~bash
git branch --set-upstream-to=origin/main
~~~

Kiểm tra kết quả:

~~~bash
git branch -vv
git rev-parse --abbrev-ref --symbolic-full-name '@{upstream}'
~~~

Thay upstream chỉ thay đổi cấu hình tracking. Nó không tự fetch, merge, rebase, reset hay push commit. Nếu branch đích chưa được fetch về local, trước tiên cập nhật remote-tracking refs:

~~~bash
git fetch origin
git branch --set-upstream-to=origin/main main
~~~

### Bỏ upstream

Nếu không muốn local branch theo dõi branch nào nữa:

~~~bash
git branch --unset-upstream main
~~~

Hoặc áp dụng cho branch hiện tại:

~~~bash
git branch --unset-upstream
~~~

Local branch vẫn tồn tại và không mất commit. Git chỉ xóa quan hệ tracking.

## 7. Fetch cập nhật remote-tracking branch như thế nào?

Lệnh:

~~~bash
git fetch origin
~~~

lấy object và refs từ remote `origin`, rồi cập nhật các remote-tracking refs theo fetch refspec đã cấu hình. Nó không tự merge các commit mới vào local branch đang checkout.

Ví dụ trước fetch:

~~~text
main        -> A
origin/main -> A
~~~

Sau khi đồng đội push B lên server, fetch sẽ làm local thành:

~~~text
main        -> A
origin/main -> B
~~~

Local `main` vẫn trỏ đến A. Remote-tracking branch `origin/main` đã cập nhật đến B.

Để cập nhật refs từ mọi remote:

~~~bash
git fetch --all
~~~

Nếu muốn dọn remote-tracking refs không còn branch tương ứng ở remote:

~~~bash
git fetch --prune origin
~~~

Hoặc xem trước các refs stale có thể bị dọn:

~~~bash
git remote prune --dry-run origin
~~~

Prune xóa remote-tracking refs local đã biến mất ở remote; nó không xóa local branches như `main` hoặc `feature/payment`. Tuy nhiên, trước khi prune, hãy chắc chắn bạn không cần giữ ref stale làm mốc tham khảo.

## 8. Pull sử dụng upstream như thế nào?

`git pull` kết hợp fetch với bước tích hợp lịch sử vào branch hiện tại. Khi không chỉ định remote và branch, Git thường dùng upstream đã cấu hình cho branch hiện tại.

Ví dụ, nếu local `main` theo dõi `origin/main`:

~~~bash
git switch main
git pull
~~~

Git fetch từ remote tương ứng rồi tích hợp thay đổi từ upstream vào `main`. Cách tích hợp phụ thuộc tùy chọn và cấu hình, phổ biến là merge hoặc rebase.

Chọn rõ cách tích hợp khi cần:

~~~bash
git pull --rebase
~~~

Hoặc yêu cầu fast-forward only:

~~~bash
git pull --ff-only
~~~

`--rebase` phát lại commit local trên lịch sử mới được fetch; `--ff-only` chỉ cập nhật khi có thể fast-forward, nếu không thì dừng để bạn xử lý. Hãy hiểu chính sách của nhóm trước khi chọn cấu hình mặc định.

Nếu branch chưa có upstream, `git pull` không có đủ thông tin mặc định để biết nên fetch từ đâu và tích hợp branch nào. Hãy thiết lập tracking hoặc chỉ rõ remote và branch trong lệnh.

## 9. Push và upstream

Upstream cũng có thể giúp Git xác định nơi push. Tuy nhiên, quy tắc push mặc định được điều khiển bởi `push.default` và các cấu hình liên quan.

Xem cấu hình:

~~~bash
git config --get push.default
~~~

Nếu không được cấu hình, Git hiện đại thường dùng chế độ `simple`. Trong trường hợp phổ biến, chế độ này yêu cầu branch local và upstream có cùng tên trước khi push.

Push branch hiện tại và đặt upstream lần đầu:

~~~bash
git push -u origin HEAD
~~~

`HEAD` ở vị trí source chỉ branch/commit hiện tại; lệnh này hữu ích khi muốn tạo branch tương ứng trên remote và thiết lập tracking.

Sau khi upstream đã được thiết lập, lệnh:

~~~bash
git push
~~~

có thể dùng quan hệ tracking cùng chính sách `push.default` để xác định nơi gửi. Khi làm việc với nhiều remote hoặc branch đặc biệt, chỉ định rõ remote và branch giúp giảm nhầm lẫn:

~~~bash
git push origin feature/payment
~~~

Đừng giả định upstream luôn là nơi push trong mọi cấu hình. Upstream chủ yếu là quan hệ tracking; hành vi push còn chịu ảnh hưởng của `push.default`, refspec và các tùy chọn push.

## 10. Làm việc với nhiều remote: origin và upstream

Trong quy trình fork phổ biến:

- `origin` thường trỏ đến fork của bạn, nơi bạn có quyền push.
- `upstream` thường trỏ đến repository gốc của dự án, nơi bạn fetch thay đổi mới.

Thêm remote gốc:

~~~bash
git remote add upstream https://example.com/original/app.git
git remote -v
~~~

Cập nhật branch từ dự án gốc:

~~~bash
git fetch upstream
~~~

Giờ bạn có thể thấy remote-tracking branch như `upstream/main`. Đây là ref local phản ánh branch main của remote có nickname `upstream` sau lần fetch gần nhất.

Một cách tổ chức thường gặp:

| Local branch | Upstream branch | Mục đích |
| --- | --- | --- |
| `main` | `upstream/main` | Theo dõi lịch sử chính thức của dự án gốc |
| `feature/payment` | `origin/feature/payment` | Theo dõi branch làm việc trên fork cá nhân |

Bạn có thể tích hợp thay đổi từ `upstream/main` vào local `main` rồi push kết quả lên `origin` theo quy trình đóng góp. Nhưng remote tên `upstream` không tự động trở thành upstream branch cho mọi local branch; mỗi branch có tracking configuration riêng.

## 11. Ahead, behind và diverged có nghĩa gì?

Khi một local branch có upstream, Git có thể so sánh hai đầu branch dựa trên common ancestor:

- **Ahead N:** local branch có N commit mà upstream chưa có.
- **Behind N:** upstream có N commit mà local branch chưa có.
- **Diverged:** cả hai phía đều có commit riêng kể từ common ancestor.

Xem trạng thái:

~~~bash
git status --short --branch
git branch -vv
~~~

Có thể đếm commit riêng mỗi phía bằng:

~~~bash
git rev-list --left-right --count '@{upstream}...HEAD'
~~~

Kết quả gồm hai số: số commit chỉ có ở upstream và số commit chỉ có ở HEAD. Vì thứ tự đối số là upstream trước, HEAD sau, hãy đọc đúng thứ tự khi diễn giải.

Thông tin ahead/behind dựa trên remote-tracking branch local. Nếu chưa fetch, nó không nhất thiết phản ánh branch hiện tại trên server. Cập nhật trước khi đánh giá:

~~~bash
git fetch
git status -sb
~~~

Không nên force-push chỉ vì thấy diverged. Trước hết xem graph và xác định commit của hai phía:

~~~bash
git log --oneline --graph --decorate --left-right 'HEAD...@{upstream}'
~~~

Trong một số shell, ký hiệu `@{upstream}` cần đặt trong dấu nháy để tránh shell diễn giải nó trước khi Git nhận lệnh.

## 12. Đổi tên hoặc xóa remote có ảnh hưởng gì?

Đổi tên remote:

~~~bash
git remote rename origin personal
~~~

Git đổi tên remote và các remote-tracking refs tương ứng. Các branch đang theo dõi remote đó cũng cần được kiểm tra lại cấu hình tracking; Git thường cập nhật một số cấu hình liên quan khi rename remote.

Xóa remote:

~~~bash
git remote remove old-origin
~~~

Thao tác này xóa cấu hình remote và các remote-tracking refs của remote đó. Local branches và commit local không tự bị xóa, nhưng upstream trỏ đến remote vừa xóa sẽ không còn phân giải được.

Sau khi đổi hoặc xóa remote, kiểm tra:

~~~bash
git remote -v
git branch -vv
git config --get-regexp '^branch\..*\.(remote|merge)$'
~~~

Nếu cần, đặt lại upstream cho branch:

~~~bash
git branch --set-upstream-to=personal/main main
~~~

## 13. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra hoặc xử lý |
| --- | --- | --- |
| `git pull` báo no tracking information | Local branch chưa có upstream | Fetch rồi dùng `git branch --set-upstream-to` hoặc chỉ định remote/branch |
| `git push` không biết push đi đâu | Chưa có upstream hoặc push policy không phù hợp | Dùng `git push -u origin HEAD` hoặc chỉ rõ remote và branch |
| `origin/main` không thấy commit mới | Chưa fetch hoặc fetch refspec không lấy branch đó | Chạy `git fetch origin` và kiểm tra `git remote show origin` |
| Branch báo ahead/behind không đúng kỳ vọng | Remote-tracking ref đã cũ | Fetch rồi xem lại `git status -sb` và `git branch -vv` |
| Upstream không còn tồn tại | Remote hoặc branch phía server đã đổi tên/xóa | Kiểm tra remote, fetch/prune và gắn upstream mới |
| Checkout `origin/main` tạo detached HEAD | Bạn checkout remote-tracking ref trực tiếp thay vì tạo local branch | Dùng `git switch --track origin/main` |
| Hai branch có cùng tên khiến nhầm nguồn | Local branch và remote-tracking branch có tên gần giống | Dùng tên đầy đủ và kiểm tra `git branch -vv` |
| Fork có commit mới nhưng local không thấy | Chưa fetch remote tương ứng hoặc upstream cấu hình nhầm | Kiểm tra `git remote -v`, fetch đúng remote và xem tracking |

## 14. Quy trình kiểm tra branch và upstream

Khi nhận một repository mới hoặc chuyển sang máy khác, có thể dùng trình tự sau:

~~~bash
# 1. Xem các remote
git remote -v

# 2. Cập nhật remote-tracking refs
git fetch --all --prune

# 3. Xem local và remote-tracking branches
git branch --all

# 4. Xem upstream và ahead/behind
git branch -vv

# 5. Xác định upstream của branch hiện tại
git rev-parse --abbrev-ref --symbolic-full-name '@{upstream}'

# 6. Xem cấu hình tracking nếu cần
git config --get-regexp '^branch\..*\.(remote|merge)$'
~~~

Nếu branch chưa có upstream, quyết định rõ branch nào cần theo dõi. Ví dụ:

~~~bash
git branch --set-upstream-to=origin/main main
~~~

Nếu branch mới chưa tồn tại trên remote, push lần đầu và thiết lập tracking:

~~~bash
git push -u origin HEAD
~~~

Sau đó kiểm tra lại:

~~~bash
git status -sb
git branch -vv
~~~

## 15. Sơ đồ mối quan hệ

~~~mermaid
flowchart TD
    A[Remote repository: origin] -->|git fetch| B[Remote-tracking ref: origin/main]
    B -->|được cấu hình làm upstream| C[Local branch: main]
    C -->|git commit| D[Commit mới trên local main]
    D -->|git push| A
    B -->|git pull: fetch rồi merge/rebase| C
~~~

Sơ đồ thể hiện các vai trò:

- Remote repository là nơi branch được lưu trên server.
- Remote-tracking branch là bản ghi local cập nhật qua fetch.
- Local branch là nhánh bạn trực tiếp làm việc.
- Upstream là quan hệ cấu hình giữa local branch và branch theo dõi.

Trước khi kết thúc, hãy tự xác nhận:

1. Tôi có phân biệt remote nickname với remote-tracking branch không?
2. Tôi có biết `origin/main` là ref local phản ánh lần fetch gần nhất không?
3. Local branch hiện tại có upstream chưa, và upstream chính xác là branch nào?
4. Tôi đã fetch trước khi dựa vào thông tin ahead/behind chưa?
5. Tôi hiểu pull tích hợp upstream còn push chịu ảnh hưởng của push policy chưa?
6. Khi làm việc với fork, tôi đã phân biệt remote tên upstream và khái niệm upstream branch chưa?

Local branch là nơi bạn phát triển và tạo commit; remote-tracking branch ghi nhớ trạng thái remote tại lần fetch gần nhất; upstream là quan hệ cấu hình giúp Git chọn nguồn theo dõi cho local branch. Khi phân biệt được ba lớp này, bạn có thể fetch, pull, push, đổi remote và xử lý ahead/behind mà không nhầm branch local với trạng thái trên server.

## Tài liệu tham khảo

- [Git documentation: git-branch](https://git-scm.com/docs/git-branch) — liệt kê branch, verbose output, tracking và set/unset upstream.
- [Git documentation: git-fetch](https://git-scm.com/docs/git-fetch) — cập nhật remote-tracking refs và prune.
- [Git documentation: git-pull](https://git-scm.com/docs/git-pull) — fetch và tích hợp upstream.
- [Git documentation: git-push](https://git-scm.com/docs/git-push) — push policy, upstream và thiết lập upstream.
- [Git documentation: git-remote](https://git-scm.com/docs/git-remote) — quản lý remote và remote-tracking branches.
- [Pro Git: Remote Branches](https://git-scm.com/book/en/v2/Git-Branching-Remote-Branches) — local branch, remote-tracking branch và tracking branch.
