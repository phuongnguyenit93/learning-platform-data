# Phân biệt git fetch, git pull và git push

Khi làm việc với repository từ xa, ba lệnh `git fetch`, `git pull` và `git push` thường xuất hiện trong cùng một quy trình. Chúng đều trao đổi dữ liệu giữa repository local và remote, nhưng mỗi lệnh có mục đích và ảnh hưởng khác nhau:

- `git fetch` lấy commit, object và thông tin tham chiếu mới từ remote về local để bạn kiểm tra.
- `git pull` lấy thay đổi từ remote rồi tích hợp chúng vào branch hiện tại theo chính sách merge hoặc rebase đã chọn.
- `git push` gửi commit local lên remote và yêu cầu cập nhật branch hoặc tag ở đó.

Hiểu rõ sự khác nhau này giúp bạn biết khi nào lịch sử local thay đổi, khi nào working tree có thể bị tác động và cần làm gì khi hai phía đã phát triển theo những hướng khác nhau.

## 1. Mô hình local và remote

Khi clone một repository, máy của bạn có một repository local với working tree, staging area, commit và các branch local. Repository trên máy chủ như GitHub, GitLab hoặc máy chủ Git nội bộ là remote. Remote thường được đặt tên là `origin`, nhưng tên này chỉ là quy ước; một dự án có thể có nhiều remote.

Ví dụ, sau khi clone:

~~~
git clone https://example.com/team/shop.git
cd shop
git remote -v
~~~

Kết quả `git remote -v` có thể hiển thị:

~~~
origin  https://example.com/team/shop.git (fetch)
origin  https://example.com/team/shop.git (push)
~~~

Tên `origin` là tên remote được lưu trong cấu hình local. Nó không phải một branch và cũng không phải bản sao trực tiếp luôn cập nhật của máy chủ.

Git thường dùng ba loại tham chiếu quan trọng khi đồng bộ:

| Tham chiếu | Ý nghĩa |
|---|---|
| `main` | Branch local mà bạn có thể checkout và tạo commit |
| `origin/main` | Remote-tracking branch, ghi nhận mốc `main` gần nhất mà local đã biết từ remote `origin` |
| `HEAD` | Cho biết vị trí hiện tại của repository, thường gắn với branch đang checkout |

`origin/main` không tự thay đổi ngay khi đồng nghiệp push lên máy chủ. Nó chỉ được cập nhật khi bạn thực hiện một thao tác lấy thông tin, chẳng hạn `git fetch origin` hoặc `git pull`. Remote-tracking branch là mốc tham chiếu local giúp bạn so sánh lịch sử; bạn thường không checkout và commit trực tiếp trên đó.

## 2. `git fetch`: tải thông tin mới về để kiểm tra

`git fetch` liên hệ với remote, tải các object còn thiếu và cập nhật những remote-tracking branch theo cấu hình fetch. Lệnh này không tự merge hoặc rebase thay đổi vào branch local hiện tại, không di chuyển branch local hiện tại và không ghi đè các tệp đang làm việc.

Lệnh cơ bản:

~~~
git fetch origin
~~~

Sau khi fetch, bạn có thể thấy `origin/main` đã tiến lên trong khi `main` local vẫn đứng ở commit cũ. Đây là chủ ý: Git đã tải dữ liệu về và cho bạn cơ hội xem xét trước khi tích hợp.

### Kiểm tra thay đổi sau fetch

Giả sử bạn đang ở branch `main`. Có thể xem các commit có trên remote-tracking branch nhưng chưa có trong local:

~~~
git log --oneline main..origin/main
~~~

Chiều ngược lại cho biết commit local chưa có trong mốc remote-tracking:

~~~
git log --oneline origin/main..main
~~~

Để quan sát quan hệ giữa các branch:

~~~
git log --oneline --graph --decorate --all
git status -sb
~~~

Bạn cũng có thể xem nội dung khác nhau giữa hai mốc:

~~~
git diff main..origin/main
~~~

Các lệnh so sánh này hữu ích trước khi quyết định merge hoặc rebase. Hãy nhớ rằng `origin/main` phản ánh lần fetch gần nhất; nếu cần dữ liệu mới nhất từ máy chủ, hãy fetch trước khi kết luận.

### Fetch một branch và dọn tham chiếu cũ

Thông thường `git fetch origin` lấy các tham chiếu theo cấu hình của remote. Bạn cũng có thể yêu cầu fetch một branch cụ thể:

~~~
git fetch origin main
~~~

Nếu một branch remote đã bị xóa, remote-tracking branch tương ứng có thể vẫn còn trong local cho đến khi được dọn. Dùng `--prune` để xóa những remote-tracking ref không còn được remote quảng bá:

~~~
git fetch --prune origin
~~~

Lệnh này chỉ dọn tham chiếu theo dõi ở local. Nó không xóa branch trên máy chủ. Nếu có nhiều remote:

~~~
git fetch --all --prune
~~~

`--all` yêu cầu fetch từ các remote đã cấu hình; `--prune` áp dụng việc dọn tham chiếu cũ cho các lần fetch đó.

### Khi nào nên dùng fetch?

Dùng fetch khi bạn muốn cập nhật thông tin trước khi tích hợp, chẳng hạn:

- Trước khi bắt đầu làm việc để biết đồng đội đã push gì.
- Trước khi merge hoặc rebase một branch.
- Khi cần xem diff, commit hoặc kiểm tra thay đổi từ remote.
- Khi muốn cập nhật nhiều remote-tracking branch mà chưa muốn thay đổi branch hiện tại.

Fetch là bước kiểm tra có kiểm soát: dữ liệu mới đã có trong repository local, còn quyết định tích hợp vẫn thuộc về bạn.

## 3. `git pull`: lấy thay đổi và tích hợp vào branch hiện tại

`git pull` là thao tác kết hợp: trước hết fetch dữ liệu từ remote, sau đó tích hợp branch upstream vào branch local hiện tại. Cách tích hợp phụ thuộc vào tùy chọn bạn truyền vào và cấu hình Git.

~~~
git pull
~~~

Lệnh không có tham số thường dùng remote và branch upstream đã cấu hình cho branch hiện tại. Ví dụ, nếu `main` theo dõi `origin/main`, Git sẽ fetch từ `origin` rồi tích hợp `origin/main` vào `main` local.

### Pull bằng merge

Với chiến lược merge, Git đưa lịch sử của upstream vào branch hiện tại. Nếu local chỉ đang chậm hơn remote và không có commit riêng cần kết hợp, Git có thể fast-forward: di chuyển branch local tới commit mới hơn mà không tạo merge commit.

Nếu local và remote đều có commit riêng, hai lịch sử đã phân nhánh. Merge sẽ kết hợp chúng và có thể tạo merge commit:

~~~
git pull --no-rebase
~~~

Có thể hình dung tình huống phân nhánh như sau:

~~~text
          L1---L2  main (local)
         /
A---B---C
         \
          R1---R2  origin/main
~~~

Sau khi merge, lịch sử có một commit kết hợp hai nhánh:

~~~text
          L1---L2
         /       \
A---B---C---------M  main
         \       /
          R1---R2
~~~

Merge giữ lại quan hệ phân nhánh ban đầu. Điều này hữu ích khi muốn thể hiện rõ các nhánh công việc đã được kết hợp.

### Pull bằng rebase

Với rebase, Git lấy các commit local chưa có trên upstream, đặt branch local tại commit upstream mới nhất rồi phát lại các commit local phía trên:

~~~
git pull --rebase
~~~

Kết quả thường có lịch sử tuyến tính hơn. Tuy nhiên, rebase tạo commit mới cho các thay đổi được phát lại, vì vậy mã định danh commit có thể thay đổi. Chỉ nên rebase những commit local chưa được chia sẻ hoặc khi nhóm đã thống nhất quy tắc làm việc. Không tự ý rebase branch công khai mà nhiều người đang dựa vào.

### Pull chỉ khi có thể fast-forward

Nếu muốn cập nhật local mà không tạo merge commit và không viết lại commit local, có thể yêu cầu:

~~~
git pull --ff-only
~~~

Lệnh thành công khi branch hiện tại có thể tiến thẳng tới upstream. Nếu hai phía đã có commit riêng, Git dừng lại và yêu cầu bạn giải quyết tình trạng phân kỳ. Đây là lựa chọn hữu ích khi nhóm muốn lịch sử branch chính chỉ tiến theo fast-forward.

### Vì sao `git pull` đôi khi cho kết quả khác nhau?

Git có thể được cấu hình cách xử lý khi branch local và upstream phân kỳ. Một số cấu hình phổ biến:

~~~
git config pull.rebase false
git config pull.rebase true
git config pull.ff only
~~~

Các lệnh trên lần lượt chọn merge, rebase hoặc chỉ cho phép fast-forward cho repository hiện tại. Có thể dùng `--global` thay vì cấu hình theo repository nếu muốn áp dụng cho các repository của người dùng. Tùy chọn trên dòng lệnh như `--rebase`, `--no-rebase` hoặc `--ff-only` giúp thể hiện rõ ý định của lần pull cụ thể.

Nếu Git báo cần chỉ định cách reconcile divergent branches, hãy chọn chính sách phù hợp với quy ước của dự án. Đừng chọn ngẫu nhiên chỉ để lệnh chạy qua; merge và rebase tạo ra lịch sử khác nhau.

### Pull có thể gây xung đột

Nếu thay đổi từ remote và local sửa cùng một vùng nội dung theo cách không thể tự kết hợp, merge hoặc rebase có thể dừng với conflict. Khi đó:

1. Dùng `git status` để xác định các tệp đang xung đột.
2. Mở từng tệp, xem các vùng đánh dấu conflict và chỉnh thành nội dung mong muốn.
3. Dùng `git add <file>` để đánh dấu tệp đã giải quyết.
4. Nếu đang merge, hoàn tất bằng `git commit` khi Git yêu cầu. Nếu đang rebase, tiếp tục bằng `git rebase --continue`.
5. Nếu cần hủy quy trình đang thực hiện, dùng `git merge --abort` hoặc `git rebase --abort` tương ứng.

Không xóa dấu conflict một cách máy móc. Hãy hiểu cả hai thay đổi và xác nhận kết quả vẫn đúng về chức năng. Khi có thay đổi chưa commit trong working tree, nên commit hoặc stash phù hợp trước khi pull để tránh làm gián đoạn công việc.

## 4. `git push`: gửi commit local lên remote

`git push` gửi các object cần thiết và yêu cầu remote cập nhật branch hoặc tag. Ví dụ:

~~~
git push origin main
~~~

Lệnh này yêu cầu cập nhật branch `main` trên remote `origin` bằng lịch sử local tương ứng. Push không tự lấy commit mới từ remote về và cũng không tự tích hợp thay đổi của đồng nghiệp vào branch local.

### Push branch lần đầu và thiết lập upstream

Khi tạo branch local mới, remote có thể chưa có branch tương ứng. Lần push đầu tiên thường dùng `-u` hoặc `--set-upstream`:

~~~
git switch -c feature/payment
git push -u origin feature/payment
~~~

Lệnh này đẩy branch lên `origin` và thiết lập quan hệ upstream cho branch local. Những lần sau, khi đang ở branch đó, bạn thường chỉ cần:

~~~
git push
~~~

Upstream là branch remote mà branch local dùng làm mốc theo dõi. Có thể xem quan hệ này bằng:

~~~
git branch -vv
~~~

Nếu branch đã tồn tại nhưng chưa có upstream, có thể thiết lập rõ ràng:

~~~
git branch --set-upstream-to=origin/feature/payment feature/payment
~~~

Việc đặt upstream giúp `git status`, `git pull` và các lệnh push không tham số biết branch remote liên quan. Nếu một branch theo dõi sai remote hoặc sai branch, hãy kiểm tra bằng `git branch -vv` và sửa cấu hình trước khi đồng bộ.

### Vì sao push bị từ chối?

Remote thường từ chối push kiểu fast-forward nếu branch trên máy chủ đã tiến lên bằng commit mà local chưa có. Ví dụ, một đồng nghiệp đã push commit `R1` lên `origin/main` trong khi local của bạn vẫn dựa trên commit cũ và tạo `L1`:

~~~text
A---B---R1  origin/main
     \
      L1   main (local)
~~~

Nếu push `L1` ngay, việc cập nhật remote sẽ bỏ qua `R1`, nên Git từ chối với thông báo non-fast-forward. Đây là cơ chế bảo vệ lịch sử khỏi bị ghi đè ngoài ý muốn.

Quy trình xử lý thường là fetch, xem lịch sử rồi tích hợp thay đổi remote:

~~~
git fetch origin
git log --oneline --graph --decorate --all
git pull --rebase
~~~

Hoặc dùng merge theo chính sách của nhóm:

~~~
git pull --no-rebase
~~~

Sau khi giải quyết conflict (nếu có), kiểm tra lại trạng thái và push:

~~~
git status
git push
~~~

Nếu branch đang được bảo vệ hoặc tài khoản không có quyền ghi, push cũng có thể bị từ chối dù lịch sử local đã cập nhật. Khi đó cần tuân theo quy trình pull request hoặc yêu cầu quyền phù hợp; không tìm cách vượt qua chính sách bảo vệ branch.

### Cẩn trọng với force push

`git push --force` có thể di chuyển tham chiếu remote theo lịch sử local và làm mất các commit mà người khác đã push. Không dùng lệnh này để xử lý lỗi non-fast-forward thông thường.

Trong trường hợp nhóm chủ động viết lại lịch sử của một branch riêng, `--force-with-lease` có thêm bước kiểm tra rằng remote vẫn ở mốc mà local dự kiến:

~~~
git push --force-with-lease origin feature/payment
~~~

Tùy chọn này giảm nguy cơ ghi đè commit mới mà bạn chưa biết, nhưng vẫn là thao tác viết lại lịch sử remote. Chỉ dùng khi hiểu rõ tác động, đã phối hợp với người cùng làm branch và có lý do cụ thể. Nó không thay thế việc fetch, review và thống nhất với nhóm.

## 5. So sánh nhanh ba lệnh

| Tiêu chí | `git fetch` | `git pull` | `git push` |
|---|---|---|---|
| Hướng trao đổi chính | Remote về local | Remote về local, sau đó tích hợp | Local lên remote |
| Cập nhật object trong repository local | Có | Có, thông qua fetch | Không phải mục đích |
| Cập nhật remote-tracking branch | Có | Có, thông qua fetch | Không |
| Di chuyển branch local hiện tại | Không | Có thể, tùy merge/rebase/fast-forward | Không |
| Có thể thay đổi working tree | Không tự tích hợp vào working tree | Có | Không |
| Có thể tạo conflict | Không trong bước fetch | Có, khi tích hợp | Thường bị từ chối nếu không fast-forward; không tự giải quyết conflict |
| Mục đích điển hình | Cập nhật thông tin để xem xét | Đồng bộ và tích hợp upstream | Chia sẻ commit với người khác |

Một cách nhớ ngắn gọn:

- **Fetch:** cập nhật những gì local biết về remote.
- **Pull:** lấy thay đổi và đưa chúng vào branch hiện tại.
- **Push:** gửi thay đổi local lên remote.

## 6. Quy trình đồng bộ thường dùng

### Cập nhật branch main trước khi làm việc

Nếu local `main` theo dõi `origin/main` và nhóm dùng fast-forward-only:

~~~
git switch main
git fetch origin
git status -sb
git log --oneline main..origin/main
git pull --ff-only
~~~

Nếu nhóm dùng rebase cho branch local, có thể thay bước cuối bằng `git pull --rebase`. Nếu nhóm dùng merge, dùng `git pull --no-rebase`. Điều quan trọng là áp dụng nhất quán chính sách của repository.

### Làm việc trên feature branch

~~~
git switch -c feature/payment
# chỉnh sửa tệp
git add .
git commit -m "Add payment flow"
git push -u origin feature/payment
~~~

Trong lúc làm việc, nếu đồng nghiệp cập nhật branch upstream:

~~~
git fetch origin
git log --oneline --graph --decorate --all
git pull --rebase
git push
~~~

Ví dụ này giả định feature branch có upstream và nhóm cho phép rebase các commit riêng của branch. Nếu branch đang được nhiều người cùng sử dụng, cần phối hợp trước khi rebase hoặc chọn merge.

### Kiểm tra trước khi push

Trước khi chia sẻ commit, nên xem branch hiện tại, trạng thái working tree và quan hệ với upstream:

~~~
git status -sb
git branch -vv
git log --oneline --decorate -5
git diff
git diff --cached
~~~

`git diff` cho biết thay đổi chưa stage; `git diff --cached` cho biết thay đổi đã stage. Sau khi xác nhận commit đúng và branch đang dựa trên lịch sử phù hợp, thực hiện push.

## 7. Các lỗi hiểu nhầm thường gặp

**Nghĩ rằng fetch đã cập nhật branch local.** Fetch cập nhật object và remote-tracking ref. Branch local chỉ thay đổi khi bạn thực hiện bước tích hợp như merge, rebase hoặc fast-forward.

**Nghĩ rằng pull luôn chỉ là fetch rồi merge.** Pull luôn fetch trước, nhưng bước tích hợp có thể là merge, rebase hoặc chỉ cho phép fast-forward tùy tùy chọn và cấu hình.

**Nghĩ rằng push sẽ tự tải thay đổi mới nhất về.** Push gửi dữ liệu local lên remote. Nếu remote có commit mới mà local chưa tích hợp, push có thể bị từ chối.

**Nhầm `origin/main` với `main`.** `main` thường là branch local; `origin/main` là remote-tracking branch ghi nhận lần đồng bộ gần nhất với remote. Hai tham chiếu có thể trỏ tới hai commit khác nhau.

**Dùng force push để vượt qua mọi lỗi push.** Non-fast-forward thường cho biết local chưa tích hợp lịch sử mới từ remote. Hãy fetch và xem xét lịch sử trước; force push có thể làm mất commit của người khác.

**Cho rằng push thành công nghĩa là thay đổi đã được phát hành.** Push chỉ cập nhật repository remote. Việc build, kiểm thử, review và triển khai phụ thuộc vào quy trình của dự án.

## 8. Checklist chọn lệnh

- [ ] Muốn xem remote có thay đổi gì mà chưa động vào branch hiện tại: dùng `git fetch`.
- [ ] Đã xem thay đổi và muốn tích hợp upstream vào branch hiện tại: dùng `git pull` với chiến lược đã thống nhất.
- [ ] Muốn chia sẻ commit local lên máy chủ: dùng `git push`.
- [ ] Push bị từ chối non-fast-forward: fetch, xem lịch sử, tích hợp commit remote rồi push lại.
- [ ] Branch mới chưa có trên remote: push lần đầu với `git push -u origin <branch>`.
- [ ] Không chắc branch đang theo dõi remote nào: kiểm tra `git remote -v` và `git branch -vv`.

Khi cộng tác, hãy coi fetch là bước cập nhật thông tin, pull là bước tích hợp và push là bước chia sẻ lịch sử. Chọn đúng thao tác và hiểu branch nào sẽ di chuyển giúp bạn đồng bộ repository có chủ đích, giảm xung đột và tránh ghi đè công việc của người khác.
