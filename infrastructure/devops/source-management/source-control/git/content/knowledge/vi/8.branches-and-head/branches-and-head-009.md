# Xem quan hệ ahead/behind bằng git branch -vv và git status

Khi làm việc với branch có upstream, Git có thể cho biết nhánh local đang có bao nhiêu commit chưa được đẩy lên upstream và còn thiếu bao nhiêu commit từ upstream. Hai trạng thái này thường được gọi là **ahead** và **behind**.

Bạn có thể xem nhanh bằng `git branch -vv` và `git status`. Các thông tin này giúp quyết định khi nào cần push, pull, merge hoặc rebase. Tuy nhiên, chúng được tính dựa trên remote-tracking ref hiện có trong máy local. Nếu chưa fetch, số liệu có thể đã cũ so với remote thật.

Bài này giải thích upstream/tracking branch, cách đọc ahead/behind, cách kiểm tra chính xác các commit khác nhau và cách xử lý từng trạng thái mà không vô tình làm mất công việc.

## 1. Branch local và upstream là gì?

Branch local là một ref trong repository hiện tại, ví dụ `feature/payment`. Upstream là branch mà Git dùng làm mốc so sánh và đồng bộ cho branch local đó.

Trong workflow phổ biến, upstream là một remote-tracking branch như `origin/main`, `origin/feature/payment` hoặc `upstream/develop`.

Remote-tracking branch là ref local phản ánh trạng thái branch trên remote ở lần fetch gần nhất. Ví dụ `origin/main` nằm trong namespace `refs/remotes/origin/`, không phải một kết nối trực tiếp tới server mỗi khi bạn chạy `git status`.

Có thể hình dung:

~~~text
Remote server                 Máy local
origin/main  ------------->   refs/remotes/origin/main
                                  |
                                  | upstream của
                                  v
                             refs/heads/main
                             branch local
~~~

Khi chạy `git fetch origin`, Git cập nhật các remote-tracking refs theo dữ liệu mới nhận được. `git status` và `git branch -vv` sau đó so sánh branch local với các ref này.

Một branch có thể không có upstream. Git vẫn cho phép commit và quản lý branch đó, nhưng không có mốc mặc định để hiển thị ahead/behind hoặc thực hiện một số thao tác push/pull không chỉ rõ đích.

## 2. Ahead và behind có nghĩa gì?

Giả sử local branch và upstream cùng bắt đầu từ commit A:

~~~text
        B---C  local feature/payment
       /
A-----+
       \
        D      origin/feature/payment
~~~

Trong ví dụ này:

- Local có B và C mà upstream chưa có: local **ahead 2**.
- Upstream có D mà local chưa có: local **behind 1**.
- Hai nhánh đã phân kỳ (diverged), vì mỗi bên có commit riêng.

| Trạng thái | Ý nghĩa |
|---|---|
| Ahead N | Local có N commit không reachable từ upstream |
| Behind N | Upstream có N commit không reachable từ local |
| Ahead 0, behind 0 | Hai branch có cùng tip và cùng tập lịch sử reachable |
| Ahead N, behind M với cả hai lớn hơn 0 | Hai branch đã phân kỳ |
| Không có số liệu | Branch chưa có upstream hoặc upstream không còn tồn tại |

Ahead/behind đếm commit trong đồ thị lịch sử. Chúng không đếm số file thay đổi, số dòng code hay số lần push. Một commit merge có thể ảnh hưởng số lượng vì Git xét quan hệ reachable trong DAG, không chỉ đếm commit trên một đường thẳng.

## 3. Cách đọc git branch -vv

Lệnh:

~~~bash
git branch -vv
~~~

Liệt kê các branch local cùng commit gần nhất và thông tin upstream nếu branch đã được cấu hình tracking.

Ví dụ:

~~~text
  main             8ac12f0 [origin/main] Merge pull request #42
* feature/payment  b91d2a4 [origin/feature/payment: ahead 2, behind 1] Add payment validation
  feature/search   2c41e9b [origin/feature/search: gone] Add search endpoint
~~~

Cách đọc:

- Dấu `*` đánh dấu branch hiện tại.
- Tên trong ngoặc vuông là upstream.
- `ahead 2` nghĩa local có hai commit chưa có ở upstream.
- `behind 1` nghĩa upstream có một commit chưa có ở local.
- `gone` nghĩa upstream ref được cấu hình không còn tồn tại trong các refs local hiện tại.

`git branch -vv` hiển thị tất cả branch local. Nó không tự fetch để hỏi server, vì vậy số liệu phản ánh remote-tracking refs đã fetch trước đó.

Nếu muốn xem cả remote-tracking branches:

~~~bash
git branch -avv
~~~

Nếu chỉ muốn xem remote-tracking branches:

~~~bash
git branch -r
~~~

`git branch -r` chỉ liệt kê refs remote-tracking đã có trong local repository, không phải danh sách live được truy vấn trực tiếp từ server.

## 4. Cách đọc git status

Lệnh:

~~~bash
git status
~~~

Ngoài trạng thái working tree và staging area, Git còn cho biết branch hiện tại có ahead hoặc behind upstream hay không.

Ví dụ branch đang ahead:

~~~text
On branch feature/payment
Your branch is ahead of 'origin/feature/payment' by 2 commits.
  (use "git push" to publish your local commits)

nothing to commit, working tree clean
~~~

Ví dụ branch đang behind:

~~~text
On branch feature/payment
Your branch is behind 'origin/feature/payment' by 3 commits, and can be fast-forwarded.
  (use "git pull" to update your local branch)
~~~

Ví dụ branch đã phân kỳ:

~~~text
On branch feature/payment
Your branch and 'origin/feature/payment' have diverged,
and have 2 and 1 different commits each, respectively.
  (use "git pull" to integrate the remote branch with yours)
~~~

Thông báo này chỉ mô tả quan hệ commit với upstream. Phần working tree clean hoặc danh sách file modified/staged là một trạng thái khác. Bạn có thể vừa ahead 2 vừa có file chưa commit.

## 5. Dùng git status -sb để xem nhanh

Tùy chọn `-s` hiển thị trạng thái ngắn, `-b` thêm thông tin branch:

~~~bash
git status -sb
~~~

Ví dụ:

~~~text
## feature/payment...origin/feature/payment [ahead 2, behind 1]
 M src/payment/service.ts
M  src/payment/controller.ts
?? notes/test-cases.txt
~~~

Dòng đầu cho biết branch và quan hệ với upstream. Các dòng tiếp theo thể hiện thay đổi trong working tree và index:

- ` M`: file đã sửa trong working tree, chưa stage.
- `M `: file đã stage.
- `??`: file chưa được Git theo dõi.

Đừng đọc `ahead` là số file đã sửa hoặc cho rằng branch ahead thì working tree sạch. Hãy đọc cả phần branch và phần file status.

Có thể dùng `git status --branch` hoặc `git status --short --branch` để yêu cầu hiển thị thông tin branch.

## 6. Vì sao phải fetch trước khi tin vào ahead/behind?

`git status` không gọi mạng để hỏi remote. Nó so sánh branch local với remote-tracking ref được lưu trên máy.

Ví dụ:

~~~text
Remote thật:
A---B---C---D  origin/main

Máy local chưa fetch:
A---B---C      origin/main
         \
          L    main
~~~

Nếu remote vừa nhận commit D nhưng local chưa fetch, máy có thể báo `main` ahead 1 và behind 0. Sau khi fetch, Git cập nhật `origin/main` và kết quả có thể thành ahead 1, behind 1.

Làm mới dữ liệu:

~~~bash
git fetch origin
git status -sb
git branch -vv
~~~

`git fetch` tải commit và cập nhật remote-tracking refs. Nó không tự merge/rebase vào branch hiện tại và không ghi đè working tree.

Nếu muốn loại bỏ remote-tracking refs của branch đã bị xóa trên remote:

~~~bash
git fetch --prune origin
~~~

Sau khi prune, branch local có upstream đã bị xóa có thể hiển thị `[origin/branch: gone]`. Nếu không fetch được do mạng, quyền truy cập hoặc remote lỗi, các con số hiện có vẫn chỉ là số liệu từ lần fetch trước.

## 7. Remote-tracking branch không phải branch trên server

Tên `origin/main` thường được hiểu nhầm là branch đang tồn tại trực tiếp trên server. Thực tế, đây là ref local do Git cập nhật khi fetch.

| Tên | Loại | Vị trí |
|---|---|---|
| `main` | Branch local | Repository local |
| `origin/main` | Remote-tracking branch | Repository local, phản ánh lần fetch gần nhất |
| Branch `main` trên origin | Branch remote thật | Repository trên server |

Có thể xem URL remote:

~~~bash
git remote -v
~~~

Xem ref server đang quảng bá tại thời điểm truy vấn:

~~~bash
git ls-remote --heads origin
~~~

`git ls-remote` truy vấn refs trên remote nhưng không cập nhật remote-tracking refs local. Muốn cập nhật local tracking data, dùng `git fetch`.

## 8. Kiểm tra branch có upstream hay chưa

Xem thông tin branch:

~~~bash
git branch -vv
~~~

Xem upstream của branch hiện tại:

~~~bash
git rev-parse --abbrev-ref --symbolic-full-name '@{upstream}'
~~~

Nếu branch không có upstream, lệnh trên sẽ báo lỗi. Có thể kiểm tra cấu hình tracking bằng:

~~~bash
git config --get branch.feature/payment.remote
git config --get branch.feature/payment.merge
~~~

Hai cấu hình này lần lượt xác định remote và branch mà local branch theo dõi.

Nếu dòng đầu của `git status -sb` chỉ hiện `## feature/payment` mà không có `...origin/...`, có thể branch chưa được cấu hình upstream. Cũng cần kiểm tra xem upstream có bị xóa hoặc chưa fetch hay không.

## 9. Thiết lập, thay đổi hoặc bỏ upstream

Nếu branch remote đã được fetch và tồn tại dưới dạng `origin/feature/payment`, gắn upstream:

~~~bash
git branch --set-upstream-to=origin/feature/payment feature/payment
~~~

Nếu đang đứng trên branch cần cấu hình, có thể bỏ tên branch cuối:

~~~bash
git branch --set-upstream-to=origin/feature/payment
~~~

Nếu branch chưa tồn tại trên remote và bạn muốn push lần đầu đồng thời thiết lập upstream:

~~~bash
git push -u origin feature/payment
~~~

Nếu tạo local branch từ remote-tracking branch, có thể thiết lập tracking ngay:

~~~bash
git switch --track -c feature/payment origin/feature/payment
~~~

Đổi upstream sang branch khác:

~~~bash
git branch --set-upstream-to=origin/develop feature/payment
~~~

Bỏ upstream:

~~~bash
git branch --unset-upstream feature/payment
~~~

Bỏ upstream không xóa branch local, remote branch hay commit. Không gắn branch feature vào `origin/main` chỉ để làm cho thông báo ahead/behind biến mất; upstream cần phản ánh đúng branch mà nhóm dùng làm mốc.

## 10. Tính ahead/behind bằng git rev-list

Khi cần kiểm tra con số độc lập với cách trình bày của `git status`, dùng:

~~~bash
git rev-list --left-right --count HEAD...'@{upstream}'
~~~

Ví dụ output:

~~~text
2    1
~~~

Với thứ tự `HEAD...@{upstream}`:

- Số bên trái là commit reachable chỉ từ HEAD local: ahead.
- Số bên phải là commit reachable chỉ từ upstream: behind.

Có thể tính riêng:

~~~bash
git rev-list --count '@{upstream}'..HEAD
git rev-list --count HEAD..'@{upstream}'
~~~

Lệnh đầu đếm commit local chưa có ở upstream. Lệnh thứ hai đếm commit upstream chưa có ở local. Biểu thức `A..B` chọn commit reachable từ B nhưng không reachable từ A; `A...B` chọn symmetric difference của hai lịch sử.

Nếu dùng PowerShell, đặt revision có ký tự `@{}` trong dấu nháy đơn như các ví dụ trên để PowerShell không diễn giải nó thành cú pháp riêng.

## 11. Xem commit chỉ có ở local hoặc upstream

Để xem commit local có mà upstream chưa có:

~~~bash
git log --oneline '@{upstream}'..HEAD
~~~

Để xem commit upstream có mà local chưa có:

~~~bash
git log --oneline HEAD..'@{upstream}'
~~~

Để xem cả hai phía trên cùng một đồ thị:

~~~bash
git log --left-right --graph --oneline HEAD...'@{upstream}'
~~~

Git dùng dấu `<` và `>` để phân biệt phía trái và phía phải trong kết quả `--left-right`:

- `<` là commit chỉ reachable từ HEAD local.
- `>` là commit chỉ reachable từ upstream.

Đây là bước nên làm trước khi merge, rebase hoặc push khi branch đã phân kỳ. Chỉ nhìn số lượng không cho biết nội dung thay đổi hoặc commit nào có thể gây xung đột.

## 12. Ahead-only: local có commit mới

Ví dụ:

~~~text
A---B---C---L1---L2  feature/payment
        ^
        origin/feature/payment
~~~

`git status -sb` có thể hiển thị:

~~~text
## feature/payment...origin/feature/payment [ahead 2]
~~~

Kiểm tra commit local:

~~~bash
git log --oneline '@{upstream}'..HEAD
~~~

Nếu các commit đã sẵn sàng chia sẻ và remote chưa có thay đổi mới, push:

~~~bash
git push
~~~

Nếu push bị từ chối vì remote đã tiến lên sau lần fetch gần nhất, fetch lại rồi xem quan hệ mới:

~~~bash
git fetch origin
git status -sb
git branch -vv
~~~

Không dùng force push chỉ để vượt qua lỗi non-fast-forward. Trước hết phải hiểu commit mới trên remote và tích hợp chúng theo workflow của nhóm.

## 13. Behind-only: upstream có commit mới

Ví dụ local không có commit riêng và upstream tiến lên:

~~~text
A---B---C  origin/feature/payment
    ^
    feature/payment (local đang ở B)
~~~

Xem các commit cần nhận:

~~~bash
git log --oneline HEAD..'@{upstream}'
~~~

Sau khi fetch và xác nhận không có thay đổi local cần bảo toàn, có thể cập nhật fast-forward:

~~~bash
git pull --ff-only
~~~

`--ff-only` yêu cầu Git chỉ cập nhật nếu có thể fast-forward. Nếu lịch sử đã phân kỳ, lệnh dừng thay vì tự tạo merge commit.

Có thể tách rõ hai bước:

~~~bash
git fetch origin
git merge --ff-only '@{upstream}'
~~~

Nếu working tree có thay đổi chưa commit, hãy commit hoặc stash trước khi tích hợp. Ahead/behind chỉ mô tả commit, không bảo đảm working tree đang sạch.

## 14. Diverged: cả local và upstream đều có commit riêng

Ví dụ:

~~~text
        L1---L2  feature/payment
       /
A---B---C
       \
        R1      origin/feature/payment
~~~

Status:

~~~text
## feature/payment...origin/feature/payment [ahead 2, behind 1]
~~~

Trước khi chọn cách tích hợp, xem cả hai phía:

~~~bash
git log --left-right --graph --oneline HEAD...'@{upstream}'
~~~

**Merge upstream vào local:**

~~~bash
git merge '@{upstream}'
~~~

Merge giữ nguyên các commit local và upstream, có thể tạo merge commit. Cách này phù hợp khi nhóm muốn giữ nguyên topology hoặc các commit local đã được chia sẻ.

**Rebase commit local lên upstream:**

~~~bash
git rebase '@{upstream}'
~~~

Rebase phát lại các commit local lên tip upstream, tạo OID mới cho các commit được viết lại. Cách này thường dùng cho branch feature riêng chưa chia sẻ rộng rãi.

Nếu tích hợp bằng pull, có thể chỉ rõ:

~~~bash
git pull --no-rebase
git pull --rebase
~~~

Hãy tuân theo chính sách của nhóm. Không rebase tùy tiện commit đã được người khác dựa vào, vì việc đổi OID sẽ làm lịch sử của họ phân kỳ.

## 15. Upstream đã gone hoặc branch chưa có upstream

`git branch -vv` có thể hiển thị:

~~~text
* feature/payment  b91d2a4 [origin/feature/payment: gone] Add payment validation
~~~

Điều này có nghĩa branch local đang cấu hình theo dõi `origin/feature/payment`, nhưng remote-tracking ref đó không tồn tại trong local hiện tại. Có thể branch đã bị xóa trên server và local đã prune, hoặc ref chưa được fetch.

Làm mới refs:

~~~bash
git fetch --prune origin
git branch -vv
~~~

Sau đó xác định ý định:

- Nếu branch remote bị xóa có chủ đích, giữ branch local và bỏ upstream hoặc gắn sang upstream khác.
- Nếu nhóm muốn khôi phục branch trên remote, kiểm tra commit local rồi push lại với `-u`.
- Nếu branch đã được thay thế bằng branch khác, xác nhận upstream mới trước khi đổi tracking.
- Nếu remote không truy cập được, chưa kết luận branch đã bị xóa; kiểm tra kết nối và quyền.

Bỏ upstream nếu không còn cần tracking:

~~~bash
git branch --unset-upstream feature/payment
~~~

Nếu muốn tạo lại remote branch từ local:

~~~bash
git push -u origin feature/payment
~~~

Nếu branch mới tạo chưa có upstream, `git status -sb` thường chỉ hiện tên branch. Thiết lập bằng `git push -u origin feature/payment` hoặc `git branch --set-upstream-to=origin/feature/payment feature/payment` nếu remote-tracking branch đã tồn tại.

## 16. Ahead/behind không thay thế git diff

Ahead/behind cho biết commit khác nhau trong lịch sử, còn `git diff` so sánh nội dung tree hoặc file.

Một số lệnh bổ trợ:

~~~bash
git diff
git diff --cached
git diff '@{upstream}'...HEAD
git diff HEAD '@{upstream}'
~~~

- `git diff`: thay đổi chưa stage trong working tree.
- `git diff --cached`: thay đổi đã stage so với HEAD.
- `git diff '@{upstream}'...HEAD`: thay đổi của phía HEAD kể từ merge base với upstream.
- `git diff HEAD '@{upstream}'`: so sánh tree tại hai tip.

Diff ba chấm và hai chấm trả lời câu hỏi khác nhau. Trước khi tích hợp branch, kết hợp `git log --left-right` và `git diff` để xem cả commit lẫn nội dung thay đổi.

## 17. Ahead/behind trong script và khi liệt kê nhiều branch

Không nên parse chuỗi output thân thiện với người dùng của `git status` nếu script cần định dạng ổn định. Git có porcelain v2:

~~~bash
git status --porcelain=v2 --branch
~~~

Ví dụ:

~~~text
# branch.oid b91d2a4...
# branch.head feature/payment
# branch.upstream origin/feature/payment
# branch.ab +2 -1
~~~

`# branch.ab +2 -1` biểu thị local ahead 2 và behind 1 so với upstream. Nếu không có upstream, các dòng `branch.upstream` và `branch.ab` có thể không xuất hiện; script phải xử lý trường hợp thiếu trường thay vì mặc định 0/0.

Để rà soát branch local và sắp xếp theo thời gian commit gần nhất:

~~~bash
git branch -vv --sort=-committerdate
~~~

Có thể dùng `git for-each-ref` để tạo báo cáo:

~~~bash
git for-each-ref --format="%(refname:short) %(upstream:short) %(upstream:track)" refs/heads/
~~~

- `%(refname:short)`: tên branch local.
- `%(upstream:short)`: tên upstream nếu có.
- `%(upstream:track)`: trạng thái ahead/behind hoặc thông tin upstream gone nếu có.

Các báo cáo này vẫn dựa trên refs local. Fetch trước nếu muốn số liệu phản ánh trạng thái remote gần nhất.

## 18. Các lỗi và hiểu nhầm thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra/xử lý |
|---|---|---|
| Branch báo up to date nhưng đồng đội vừa push | Chưa fetch nên remote-tracking ref cũ | Chạy `git fetch`, rồi xem lại status |
| `git branch -vv` không có phần upstream | Branch chưa được cấu hình tracking | Dùng `git push -u` hoặc `git branch --set-upstream-to` |
| Status báo ahead và behind cùng lúc | Hai phía đã có commit riêng | Xem `git log --left-right`, chọn merge hoặc rebase |
| Hiện `[origin/foo: gone]` | Upstream ref không còn trong local refs | Fetch/prune, xác minh remote và chọn upstream mới hoặc push lại |
| Push bị từ chối dù status chỉ ahead | Remote có thể đã tiến lên sau lần fetch | Fetch lại, xem commit mới và tích hợp |
| `git pull` tạo merge commit ngoài dự kiến | Cấu hình pull dùng merge và branch đã phân kỳ | Kiểm tra `pull.rebase`, dùng tùy chọn rõ ràng theo chính sách |
| `git pull --ff-only` dừng | Lịch sử không thể fast-forward | Xem commit hai phía rồi chọn merge/rebase |
| `git status` có file modified dù branch up to date | Working tree dirty độc lập với quan hệ commit | Xem `git status --short`, `git diff` và staging |
| `git branch -r` vẫn thấy branch đã xóa | Remote-tracking ref local chưa được prune | Chạy `git fetch --prune origin` |
| Số ahead/behind khác nhau giữa hai máy | Hai máy fetch ở thời điểm khác nhau hoặc upstream khác nhau | So sánh `git remote -v`, upstream và fetch mới |

## 19. Quy trình kiểm tra trước khi push hoặc pull

Khi chuẩn bị đồng bộ branch, có thể dùng trình tự:

**Bước 1 — Xác định branch hiện tại**

~~~bash
git branch --show-current
git status -sb
~~~

**Bước 2 — Kiểm tra upstream**

~~~bash
git rev-parse --abbrev-ref --symbolic-full-name '@{upstream}'
git branch -vv
~~~

**Bước 3 — Fetch dữ liệu mới**

~~~bash
git fetch --prune origin
~~~

**Bước 4 — Xem lại quan hệ**

~~~bash
git status -sb
git branch -vv
git rev-list --left-right --count HEAD...'@{upstream}'
~~~

**Bước 5 — Xem commit và nội dung khác nhau**

~~~bash
git log --left-right --graph --oneline HEAD...'@{upstream}'
git diff '@{upstream}'...HEAD
~~~

**Bước 6 — Chọn hành động**

- Ahead-only: kiểm tra commit local rồi push.
- Behind-only: nếu fast-forward được, dùng `git pull --ff-only`.
- Diverged: chọn merge hoặc rebase theo quy ước nhóm.
- Gone: xác minh branch remote đã bị xóa hay đổi tên.
- No upstream: thiết lập tracking nếu cần đồng bộ.

**Bước 7 — Kiểm tra lại sau thao tác**

~~~bash
git status -sb
git branch -vv
~~~

## 20. Checklist đọc ahead/behind

- [ ] Đã xác định branch local hiện tại.
- [ ] Đã xác định upstream branch đang được theo dõi.
- [ ] Đã fetch remote gần nhất trước khi kết luận.
- [ ] Đã hiểu ahead là commit chỉ có ở local.
- [ ] Đã hiểu behind là commit chỉ có ở upstream.
- [ ] Đã phân biệt số commit với số file thay đổi.
- [ ] Đã kiểm tra working tree và staging area riêng.
- [ ] Đã xem commit local-only và upstream-only khi branch diverged.
- [ ] Đã kiểm tra upstream có bị gone hoặc chưa được cấu hình không.
- [ ] Đã chọn push, fast-forward, merge hoặc rebase theo chính sách nhóm.
- [ ] Đã xác minh status sau khi đồng bộ.

## 21. Những điểm cần ghi nhớ

- Upstream là branch mốc để local branch so sánh và đồng bộ; thường là remote-tracking branch như `origin/main`.
- `git branch -vv` hiển thị branch local, commit tip, upstream và ahead/behind.
- `git status` hoặc `git status -sb` cho biết trạng thái branch hiện tại và working tree.
- Ahead đếm commit chỉ có ở local; behind đếm commit chỉ có ở upstream.
- Ahead và behind đều lớn hơn 0 nghĩa là hai lịch sử đã phân kỳ.
- Các con số dựa trên remote-tracking refs local, vì vậy hãy `git fetch` trước khi tin vào chúng.
- `git fetch` cập nhật refs nhưng không tích hợp commit vào branch hiện tại.
- `git fetch --prune` loại remote-tracking refs của branch đã bị xóa khỏi remote theo refspec.
- `git push -u` tạo/cập nhật remote branch và thiết lập upstream cho những lần sau.
- Dùng `git rev-list --left-right --count` và `git log --left-right` để kiểm tra định lượng và nội dung hai phía.
- `git status --porcelain=v2 --branch` phù hợp cho script cần đọc trạng thái branch ổn định.
- Ahead/behind không thay thế việc kiểm tra diff, working tree và chính sách merge/rebase.

Khi đọc đúng quan hệ ahead/behind, bạn biết local đang có commit cần push, đang thiếu commit cần nhận hay đã phân kỳ với upstream. Hãy fetch trước, kiểm tra các commit ở cả hai phía rồi chọn cách đồng bộ phù hợp; điều đó giúp tránh push bị từ chối, merge ngoài ý muốn hoặc viết lại lịch sử mà đồng đội đang sử dụng.

