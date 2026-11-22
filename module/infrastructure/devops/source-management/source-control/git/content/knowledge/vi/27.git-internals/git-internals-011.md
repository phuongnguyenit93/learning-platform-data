# Cập nhật tham chiếu bằng git update-ref và bảo vệ tính nhất quán

Git lưu commit và các object khác trong object database, còn branch, tag và nhiều tên tham chiếu khác được quản lý thông qua **ref**. Một ref trỏ tới object cụ thể; khi branch tiến lên, Git cập nhật ref để nó trỏ tới commit mới. Việc cập nhật này cần được thực hiện an toàn để tránh ghi đè thay đổi của tiến trình khác, tạo trạng thái tham chiếu không nhất quán hoặc làm lệch HEAD với index và working tree.

Lệnh **git update-ref** là công cụ plumbing cấp thấp để tạo, cập nhật, xác minh và xóa ref. Nó được dùng trong script quản trị repository, công cụ Git và các quy trình cần cập nhật nhiều ref có kiểm soát. Đây không phải lệnh thay thế thông thường cho commit, switch, merge hoặc reset. Khi dùng trực tiếp, người vận hành phải tự chịu trách nhiệm kiểm tra object đích, giá trị cũ, trạng thái worktree và phạm vi ảnh hưởng.

## 1. Ref là gì và Git dùng ref để làm gì?

Ref (reference) là một tên có thể phân giải thành object trong repository. Các ref phổ biến nằm trong namespace:

| Namespace | Ý nghĩa | Ví dụ |
|---|---|---|
| refs/heads/ | Branch local | refs/heads/main |
| refs/tags/ | Tag | refs/tags/v2.0.0 |
| refs/remotes/ | Remote-tracking branch | refs/remotes/origin/main |
| refs/notes/ | Git notes | refs/notes/commits |
| refs/stash | Ref đặc biệt cho stash | refs/stash |

Một branch như main không phải bản sao của toàn bộ lịch sử. Nó là một ref thường trỏ tới commit tip của dòng phát triển. Khi tạo commit mới trên branch, Git cập nhật ref đó để trỏ tới commit vừa tạo. Remote-tracking ref như refs/remotes/origin/main thường do thao tác fetch quản lý; không nên tự di chuyển chúng nếu không có mục đích quản trị rõ ràng.

Tag cũng là ref, nhưng thường được dùng để đánh dấu một mốc. Lightweight tag thường trỏ trực tiếp tới commit; annotated tag trỏ tới tag object, rồi tag object mới trỏ tới commit hoặc object được gắn nhãn.

### 1.1. HEAD là một symbolic ref

Trong repository thông thường, HEAD thường là symbolic ref trỏ tới branch hiện tại:

~~~text
HEAD -> refs/heads/main -> <commit-id>
~~~

Kiểm tra:

~~~sh
git symbolic-ref HEAD
git rev-parse HEAD
~~~

Lệnh đầu hiển thị ref mà HEAD đang trỏ tới, ví dụ refs/heads/main. Lệnh thứ hai phân giải HEAD thành mã object của commit hiện tại.

Khi checkout một commit trực tiếp thay vì branch, HEAD trở thành detached HEAD và trỏ trực tiếp tới commit. Đây là trạng thái khác với HEAD trỏ tới branch.

### 1.2. Ref có thể được lưu theo nhiều cách

Trong backend truyền thống, ref có thể tồn tại dưới dạng file riêng trong thư mục refs hoặc được gom vào file packed-refs. Git cũng có thể dùng backend lưu ref khác, chẳng hạn reftable trong những môi trường hỗ trợ.

Vì cách lưu có thể thay đổi, không nên sửa trực tiếp file bên trong .git/refs hoặc packed-refs. Hãy dùng lệnh Git như update-ref, branch, tag và symbolic-ref để Git tự quản lý định dạng, khóa và tính nhất quán.

## 2. git update-ref làm gì?

git update-ref thay đổi ref để nó trỏ tới object ID được chỉ định. Lệnh có thể:

- Tạo ref mới.
- Cập nhật ref đang tồn tại.
- Kiểm tra ref vẫn có giá trị mong đợi.
- Xóa ref.
- Thực hiện một nhóm cập nhật trong transaction.
- Ghi lý do cập nhật vào reflog.

Lệnh chỉ thay đổi mối liên hệ giữa tên ref và object. Nó không sửa nội dung commit, tree hoặc blob, và không tự checkout mã nguồn mới.

Lệnh cơ bản:

~~~sh
git update-ref <ref> <new-oid> [<old-oid>]
~~~

Trong đó:

- ref là tên tham chiếu cần cập nhật, thường dùng tên đầy đủ như refs/heads/feature/search.
- new-oid là mã object mới mà ref sẽ trỏ tới.
- old-oid là mã object hiện tại được kỳ vọng; nếu truyền vào, Git chỉ cập nhật khi giá trị hiện tại khớp.

Nếu old-oid không khớp giá trị đang có, Git từ chối cập nhật. Đây là cơ chế quan trọng để tránh ghi đè một thay đổi mới mà script chưa biết tới. Nếu bỏ old-oid, lệnh không có điều kiện so sánh với giá trị đã đọc trước đó; chỉ bỏ nó khi chủ đích cập nhật không điều kiện đã được xác định rõ.

### 2.1. Kiểm tra ref trước khi cập nhật

Xem danh sách ref:

~~~sh
git show-ref
~~~

Xem một branch cụ thể:

~~~sh
git show-ref --verify refs/heads/main
~~~

Liệt kê ref với object và tên:

~~~sh
git for-each-ref --format="%(objectname) %(refname)" refs/heads/
~~~

Lấy object ID của branch:

~~~sh
git rev-parse refs/heads/main
~~~

Nên dùng ref đầy đủ trong script. Tên ngắn như main có thể được phân giải theo quy tắc DWIM của Git; tên đầy đủ giúp tránh nhầm giữa branch, tag hoặc ref khác cùng tên.

### 2.2. Kiểm tra tên ref hợp lệ

Trước khi tạo ref do người dùng hoặc script sinh ra, kiểm tra tên:

~~~sh
git check-ref-format refs/heads/feature/search
~~~

Lệnh trả mã thành công nếu tên ref hợp lệ. Không nối trực tiếp dữ liệu không tin cậy vào tên ref rồi gọi shell; hãy kiểm tra đầu vào và dùng đúng namespace mà ứng dụng cho phép.

## 3. Cập nhật ref với giá trị cũ mong đợi

Một cập nhật đơn giản:

~~~sh
git update-ref refs/heads/release <new-oid>
~~~

Lệnh này yêu cầu ref trỏ tới object mới. Tuy nhiên, nếu script đã đọc giá trị cũ rồi một tiến trình khác cập nhật ref trước khi script chạy lệnh, script có thể vô tình ghi đè thay đổi mới đó.

Để bảo vệ tính nhất quán, hãy truyền cả giá trị cũ mong đợi:

~~~sh
git update-ref refs/heads/release <new-oid> <expected-old-oid>
~~~

Đây là cơ chế compare-and-swap (CAS): chỉ cập nhật nếu ref hiện tại vẫn bằng expected-old-oid. Nếu ref đã thay đổi, lệnh thất bại thay vì âm thầm ghi đè.

### 3.1. Ví dụ cập nhật branch có kiểm tra giá trị cũ

Giả sử branch release đang trỏ tới commit hiện tại và muốn chuyển tới commit candidate-release:

~~~sh
old_oid=$(git rev-parse refs/heads/release)
new_oid=$(git rev-parse 'candidate-release^{commit}')

git cat-file -e "$new_oid^{commit}"
git update-ref -m "promote release candidate" refs/heads/release "$new_oid" "$old_oid"
~~~

Giải thích:

1. Đọc object ID hiện tại của branch release.
2. Phân giải candidate-release thành commit, kể cả khi tên đó là tag.
3. Xác nhận object đích là commit tồn tại.
4. Chỉ cập nhật branch nếu giá trị hiện tại vẫn khớp old_oid.

Tùy chọn -m ghi lý do cập nhật vào reflog khi reflog được ghi cho ref đó. Để yêu cầu tạo reflog nếu chưa có, có thể thêm --create-reflog.

~~~sh
git update-ref --create-reflog -m "promote release candidate" refs/heads/release "$new_oid" "$old_oid"
~~~

### 3.2. Vì sao old-oid quan trọng?

Giả sử script đọc release đang trỏ tới A. Trong lúc script chuẩn bị, một người khác đã đẩy branch tới B. Nếu script cập nhật ref tới C mà không kiểm tra giá trị cũ, thay đổi B có thể bị mất khỏi branch.

Với điều kiện old-oid=A, Git phát hiện branch hiện không còn trỏ tới A và từ chối thao tác. Script có thể đọc lại trạng thái mới, đánh giá lại và thử lại nếu phù hợp.

Không nên tự động retry vô hạn. Nếu ref thay đổi liên tục, hãy dừng và yêu cầu quy trình điều phối hoặc người vận hành giải quyết.

## 4. Tạo, xác minh và xóa ref

git update-ref hỗ trợ các thao tác khác nhau qua chế độ --stdin. Đây là cách rõ ràng để yêu cầu tạo ref chỉ khi ref chưa tồn tại, hoặc xóa ref chỉ khi giá trị còn đúng như dự kiến.

### 4.1. Tạo ref mới

Để tạo một ref và bảo đảm tên đó chưa tồn tại, dùng lệnh create trong giao thức stdin:

~~~sh
new_oid=$(git rev-parse HEAD)

git update-ref --stdin <<EOF
create refs/heads/rescue/before-maintenance $new_oid
EOF
~~~

Nếu ref đã tồn tại, thao tác create thất bại. Điều này tránh việc script vô tình di chuyển một branch cứu hộ đã có.

Với thao tác tạo branch thông thường, git branch thường dễ hiểu và phù hợp hơn. update-ref hữu ích khi cần điều khiển chính xác ref trong script hoặc trong một transaction nhiều ref.

### 4.2. Xác minh ref

Lệnh verify kiểm tra ref có tồn tại và có object ID đúng như mong đợi:

~~~sh
expected_oid=$(git rev-parse refs/heads/release)

git update-ref --stdin <<EOF
verify refs/heads/release $expected_oid
EOF
~~~

Nếu ref đã thay đổi, thao tác xác minh thất bại. Verify không di chuyển ref.

### 4.3. Xóa ref có kiểm tra

Có thể xóa ref bằng:

~~~sh
git update-ref -d refs/heads/rescue/before-maintenance <expected-old-oid>
~~~

Nếu cung cấp expected-old-oid, Git chỉ xóa khi ref vẫn trỏ tới object được mong đợi. Cách này hữu ích cho script dọn dẹp vì tránh xóa nhầm ref vừa được một tiến trình khác cập nhật.

Đối với tag hoặc branch thông thường, lệnh cấp cao như git tag -d hoặc git branch -d thường dễ hiểu hơn. Chỉ dùng update-ref khi cần điều kiện kiểm tra hoặc transaction cụ thể.

## 5. Cập nhật nhiều ref trong một transaction

Một số quy trình cần cập nhật nhiều ref như một đơn vị logic. Ví dụ, khi hoàn tất một lần phát hành, hệ thống có thể cần cập nhật hai branch bảo trì hoặc di chuyển một nhóm ref liên quan.

Nếu cập nhật từng ref bằng các lệnh riêng, tiến trình khác có thể quan sát trạng thái ở giữa: ref thứ nhất đã đổi nhưng ref thứ hai chưa đổi. Nếu lệnh thứ hai thất bại, repository có thể ở trạng thái một phần mà quy trình cấp cao không mong muốn.

git update-ref --stdin hỗ trợ transaction với các bước start, prepare, commit và abort. Một transaction có thể gom nhiều cập nhật ref và áp dụng chúng cùng nhau.

### 5.1. Cú pháp transaction cơ bản

~~~text
start
update <ref> <new-oid> <old-oid>
update <ref> <new-oid> <old-oid>
prepare
commit
~~~

- start bắt đầu transaction.
- update thêm một yêu cầu cập nhật ref và kiểm tra giá trị cũ.
- prepare yêu cầu Git chuẩn bị transaction và giữ các khóa cần thiết.
- commit áp dụng toàn bộ thay đổi đã chuẩn bị.
- abort hủy transaction chưa commit.

Nếu không thể chuẩn bị một trong các cập nhật, transaction không được commit một phần. Script phải xử lý lỗi và không được giả định mọi ref đã thay đổi.

### 5.2. Ví dụ cập nhật hai branch cùng lúc

Giả sử hệ thống cần chuyển hai branch release và stable tới các commit đã được xác minh:

~~~sh
old_release=$(git rev-parse refs/heads/release)
old_stable=$(git rev-parse refs/heads/stable)
new_release=$(git rev-parse candidate-release^{commit})
new_stable=$(git rev-parse candidate-stable^{commit})

git cat-file -e "$new_release^{commit}"
git cat-file -e "$new_stable^{commit}"

git update-ref --stdin <<EOF
start
update refs/heads/release $new_release $old_release
update refs/heads/stable $new_stable $old_stable
prepare
commit
EOF
~~~

Hai cập nhật được thực hiện trong cùng transaction. Nếu một ref không còn ở giá trị cũ đã đọc, prepare sẽ thất bại và transaction không áp dụng một phần.

Các mã object trong ví dụ là placeholder được lấy từ repository thực tế. Trong script dùng cho production, cần xử lý mã thoát, log và trường hợp transaction thất bại một cách rõ ràng.

### 5.3. Khi transaction thất bại

Khi prepare hoặc commit thất bại:

1. Không tiếp tục giả định ref đã được cập nhật.
2. Đọc lại tất cả ref liên quan bằng show-ref hoặc rev-parse.
3. Xác định lỗi do giá trị cũ không khớp, tên ref không hợp lệ, object không tồn tại hay lỗi lưu trữ.
4. Chỉ chạy lại sau khi tính toán lại trạng thái mong đợi.
5. Ghi log transaction và lý do thất bại.

Không tự xóa file .lock để “sửa” transaction. Lock là một phần cơ chế bảo vệ ghi của Git; việc xóa khi tiến trình còn hoạt động có thể làm hỏng tính nhất quán.

## 6. Ref lock và tính nhất quán khi có nhiều tiến trình

Khi Git cập nhật ref, nó dùng cơ chế khóa để tránh hai tiến trình ghi đè nhau. Với backend files, Git thường tạo file khóa có hậu tố .lock, ghi giá trị mới rồi thay thế ref sau khi hoàn tất. Backend lưu ref khác có thể triển khai cơ chế tương ứng theo cách riêng.

Điều người dùng cần nhớ:

- Dùng lệnh Git để cập nhật ref, không tự sửa file nội bộ.
- Không xóa file lock khi chưa xác định tiến trình sở hữu nó.
- Dùng old-oid để phát hiện ref đã thay đổi kể từ lúc đọc.
- Dùng transaction khi nhiều ref phải đổi cùng nhau.
- Xử lý lỗi và đọc lại trạng thái sau mỗi lần cập nhật thất bại.

### 6.1. Không nhầm lock với kiểm soát nghiệp vụ

Ref lock ngăn các thao tác ghi xung đột ở mức lưu trữ. Nó không tự kiểm tra branch có được phép tiến tới commit đó hay không.

Ví dụ, update-ref có thể di chuyển branch từ A tới C dù C không phải hậu duệ của A, nếu điều kiện old-oid vẫn khớp. Nếu chính sách chỉ cho phép fast-forward, script phải kiểm tra quan hệ tổ tiên trước:

~~~sh
git merge-base --is-ancestor "$old_oid" "$new_oid"
~~~

Nếu lệnh trả mã khác 0, new_oid không phải hậu duệ của old_oid theo quan hệ commit đang xét. Khi đó, từ chối cập nhật nếu chính sách yêu cầu fast-forward.

### 6.2. Kiểm tra object đích trước khi di chuyển ref

Ref cần trỏ tới object tồn tại trong object database. Với branch, object đích thường phải là commit:

~~~sh
git cat-file -e "$new_oid^{commit}"
git cat-file -t "$new_oid"
~~~

Phép phân giải ^{commit} xác nhận object có thể được phân giải thành commit. Lệnh cat-file -t cho biết loại object được tham chiếu trực tiếp, chẳng hạn commit hoặc tag.

Đối với tag annotated, object trực tiếp mà tag ref trỏ tới có thể là tag object. Vì vậy, không áp dụng điều kiện “mọi ref phải trỏ trực tiếp tới commit” cho mọi namespace.

## 7. Bảo vệ HEAD, index và working tree

Đây là điểm dễ gây lỗi khi dùng update-ref: cập nhật ref không đồng nghĩa với checkout commit mới.

Giả sử bạn đang ở branch main:

~~~text
HEAD -> refs/heads/main -> A
index                 = tree(A)
working tree          = tree(A)
~~~

Nếu dùng update-ref để chuyển refs/heads/main từ A sang B, HEAD vẫn là symbolic ref trỏ tới main, nên HEAD giờ phân giải thành B. Nhưng Git không tự cập nhật index và working tree sang tree(B).

Kết quả có thể giống trạng thái working tree có nhiều thay đổi so với commit mới. Người dùng có thể nhầm các khác biệt này là file vừa sửa, trong khi nguyên nhân là ref đã được di chuyển mà chưa checkout.

### 7.1. Không dùng update-ref để di chuyển branch đang checkout

Nếu branch đang được checkout trong worktree hiện tại hoặc một linked worktree khác, không nên tự cập nhật ref đó bằng update-ref. Hãy dùng lệnh cấp cao để Git phối hợp HEAD, index và working tree:

~~~sh
git switch <branch>
git reset --hard <commit>
~~~

Lưu ý reset --hard có thể loại bỏ thay đổi chưa commit. Chỉ dùng sau khi đã kiểm tra và bảo toàn công việc cần giữ.

Nếu mục tiêu là chuyển sang branch khác, dùng git switch. Nếu mục tiêu là di chuyển branch tới commit và cập nhật worktree, chọn reset hoặc checkout theo ý định cụ thể.

### 7.2. HEAD là symbolic ref, không phải branch name đơn giản

Mặc định, update-ref phân giải symbolic ref trước khi cập nhật. Ví dụ, cập nhật HEAD có thể thực tế cập nhật branch mà HEAD trỏ tới; index và working tree vẫn không được checkout theo commit mới.

Tùy chọn --no-deref yêu cầu thao tác trên chính symbolic ref thay vì dereference nó. Đây là tùy chọn cấp thấp và có thể làm thay đổi cách HEAD được nối với branch. Không dùng nó để “sửa” HEAD nếu chưa hiểu trạng thái repository.

Kiểm tra HEAD:

~~~sh
git symbolic-ref -q HEAD
git rev-parse HEAD
git status -sb
~~~

Nếu HEAD detached, symbolic-ref có thể trả mã khác 0 vì HEAD không trỏ tới một branch.

### 7.3. Linked worktree dùng chung branch refs

Nhiều worktree có thể dùng chung object database và refs của cùng repository. Git thường ngăn cùng một branch được checkout trong nhiều worktree qua các lệnh cấp cao, nhưng update-ref là công cụ thấp hơn và không tự cập nhật working tree của các worktree liên quan.

Trước khi cập nhật branch bằng script, kiểm tra các worktree:

~~~sh
git worktree list --porcelain
~~~

Nếu ref định cập nhật đang được checkout ở bất kỳ worktree nào, hãy dùng quy trình phù hợp để cập nhật worktree đó hoặc chọn một ref khác. Không để branch ref và trạng thái làm việc của worktree lệch nhau.

## 8. Reflog giúp truy vết thay đổi ref

Reflog ghi lại những lần ref hoặc HEAD thay đổi trong repository local. Nó có thể giúp tìm lại vị trí trước đó sau một thao tác cập nhật nhầm.

Xem reflog của branch:

~~~sh
git reflog show refs/heads/release
~~~

Ghi lý do khi cập nhật:

~~~sh
git update-ref --create-reflog -m "restore approved release pointer" refs/heads/release "$new_oid" "$old_oid"
~~~

Lý do được ghi vào reflog giúp người vận hành hiểu tại sao ref đã di chuyển. Reflog không phải bản ghi audit tập trung và thường chỉ có trong repository local; nó không tự được push lên remote.

### 8.1. Khôi phục ref từ reflog

Nếu branch bị di chuyển nhầm, tìm object ID trước thao tác:

~~~sh
git reflog show refs/heads/release
~~~

Sau khi xác định commit cũ và kiểm tra nội dung, có thể tạo branch cứu hộ:

~~~sh
git branch rescue/release-before-update <old-commit>
~~~

Nếu cần khôi phục branch gốc, trước tiên đọc giá trị hiện tại, xác minh branch không được checkout ở worktree nào và phối hợp với người dùng liên quan. Sau đó có thể cập nhật ref với điều kiện old-oid:

~~~sh
current_oid=$(git rev-parse refs/heads/release)
git update-ref -m "restore release ref" refs/heads/release <old-commit> "$current_oid"
~~~

Ví dụ trên chỉ phù hợp khi đã kiểm tra các điều kiện về worktree và chính sách. Nếu branch đang được sử dụng, ưu tiên lệnh cấp cao và quy trình đồng bộ tương ứng.

### 8.2. Reflog có giới hạn

Reflog có thể hết hạn hoặc bị xóa. Nó không thay thế backup, remote hoặc audit log. Một object không còn được ref hay reflog giữ có thể bị garbage collection thu hồi sau này.

Khi cần điều tra sâu, có thể tìm object chưa được tham chiếu:

~~~sh
git fsck --full --no-reflogs --unreachable
~~~

Lệnh có thể tốn thời gian trên repository lớn. Chỉ dùng khi cần điều tra object bị mất ref và lưu lại các object cần thiết trước khi cleanup.

## 9. Cập nhật ref có an toàn về mặt nghiệp vụ không?

update-ref bảo vệ thao tác ghi ref, nhưng không tự đảm bảo quy tắc của dự án. Script cần kiểm tra các điều kiện bổ sung.

| Điều kiện | Cách kiểm tra hoặc bảo vệ |
|---|---|
| Tên ref hợp lệ | git check-ref-format |
| Ref đang ở giá trị dự kiến | old-oid hoặc verify |
| Object đích tồn tại | git cat-file -e |
| Branch chỉ tiến fast-forward | git merge-base --is-ancestor |
| Không di chuyển branch đang checkout | git worktree list --porcelain |
| Nhiều ref phải cùng cập nhật | git update-ref --stdin transaction |
| Có thể truy vết thay đổi | -m và --create-reflog |
| Ref không bị xóa nhầm | delete với expected old-oid |

Ví dụ, một công cụ phát hành có thể yêu cầu:

1. Tag phát hành đã được xác minh.
2. Commit đích là commit hợp lệ.
3. Branch hiện tại vẫn ở SHA đã đọc ban đầu.
4. Branch không được checkout trong worktree đang hoạt động.
5. Cập nhật ref được ghi lý do vào reflog.
6. Kết quả được xác minh lại sau khi transaction hoàn tất.

Không nên chỉ dựa vào việc update-ref trả mã 0 để kết luận toàn bộ quy trình phát hành đã đúng. Lệnh chỉ xác nhận thao tác ref được chấp nhận.

## 10. So sánh update-ref với các lệnh cấp cao

| Lệnh | Mục đích chính | Có phối hợp working tree/index? |
|---|---|---|
| git branch | Tạo, liệt kê, xóa branch | Không checkout nếu chỉ tạo branch |
| git switch | Chuyển branch hoặc commit | Có |
| git reset | Di chuyển HEAD/branch và tùy mode cập nhật index, working tree | Có, tùy tùy chọn |
| git tag | Tạo, liệt kê, xóa tag | Không |
| git symbolic-ref | Đọc hoặc cập nhật symbolic ref | Không |
| git update-ref | Tạo, cập nhật, xác minh, xóa ref ở mức plumbing | Không tự checkout hoặc cập nhật index |

Dùng lệnh cấp cao khi thao tác là một hành động làm việc thông thường của người dùng. Dùng update-ref khi viết công cụ, quản trị ref hoặc cần transaction và điều kiện old-value rõ ràng.

## 11. Không sửa trực tiếp file refs và packed-refs

Trong backend files, có thể thấy các đường dẫn như:

~~~text
.git/refs/heads/main
.git/refs/tags/v2.0.0
.git/packed-refs
~~~

Không nên dùng editor, echo hoặc script tùy ý để sửa các file này. Cách làm đó có thể:

- Bỏ qua cơ chế lock của Git.
- Ghi đè cập nhật của tiến trình khác.
- Tạo giá trị object ID sai định dạng hoặc trỏ tới object không tồn tại.
- Làm reflog không được cập nhật.
- Không tương thích với backend lưu ref khác.
- Tạo trạng thái không thể giải thích khi repository đang có thao tác đồng thời.

Hãy dùng update-ref hoặc lệnh cấp cao. Nếu nghi ngờ ref bị hỏng, dùng show-ref, fsck và các lệnh kiểm tra thay vì tự sửa cấu trúc nội bộ.

## 12. Ví dụ thực hành: công cụ promote release an toàn

Giả sử một script cần di chuyển branch release từ commit cũ sang commit đã được kiểm thử. Script phải từ chối nếu branch thay đổi trong lúc chuẩn bị, commit đích không tồn tại hoặc cập nhật không phải fast-forward.

~~~sh
#!/bin/sh
set -eu

ref=refs/heads/release
candidate=candidate-release

git check-ref-format "$ref"

old_oid=$(git rev-parse "$ref")
new_oid=$(git rev-parse "$candidate^{commit}")

git cat-file -e "$new_oid^{commit}"

if ! git merge-base --is-ancestor "$old_oid" "$new_oid"; then
    echo "Từ chối: candidate không phải fast-forward của release." >&2
    exit 1
fi

if git worktree list --porcelain | grep -Fqx "branch $ref"; then
    echo "Từ chối: release đang được checkout trong một worktree." >&2
    exit 1
fi

git update-ref --create-reflog -m "promote candidate-release" "$ref" "$new_oid" "$old_oid"

actual_oid=$(git rev-parse "$ref")
if [ "$actual_oid" != "$new_oid" ]; then
    echo "Lỗi: ref sau cập nhật không khớp candidate." >&2
    exit 1
fi

echo "Đã cập nhật release tới $actual_oid"
~~~

Script là ví dụ minh họa cho các bước kiểm tra, không phải bộ công cụ phát hành hoàn chỉnh. Trong production, cần xem xét tên branch và worktree có thể thay đổi đồng thời, cách phân tích output porcelain, quyền chạy, log, xử lý lỗi và chính sách rollback. Việc kiểm tra worktree rồi mới gọi update-ref không phải một transaction chung với thao tác checkout; cần điều phối để không có tiến trình khác thay đổi worktree trong khoảng giữa hai bước. Cơ chế old_oid của update-ref vẫn là lớp bảo vệ cuối cùng chống cập nhật dựa trên giá trị ref đã lỗi thời.

Nếu branch release đang được checkout, script dừng lại thay vì di chuyển ref và để working tree/index ở commit cũ. Người vận hành có thể chuyển sang quy trình cập nhật branch bằng lệnh cấp cao hoặc thực hiện promotion trong một môi trường bare được quản lý riêng.

## 13. Lỗi thường gặp khi dùng update-ref

**Ref không tồn tại.** Kiểm tra tên đầy đủ và namespace bằng show-ref hoặc for-each-ref. Nếu mục tiêu là tạo ref mới, dùng create trong chế độ --stdin.

**Giá trị cũ không khớp.** Một tiến trình khác có thể đã cập nhật ref. Đọc lại trạng thái và tính toán lại quyết định; không bỏ old-oid chỉ để lệnh chạy qua.

**Object đích không tồn tại hoặc sai loại.** Kiểm tra bằng rev-parse và cat-file. Branch nên phân giải thành commit; tag có thể trỏ tới tag object.

**Tên ref không hợp lệ.** Kiểm tra bằng check-ref-format và từ chối đầu vào không hợp lệ.

**Di chuyển branch đang checkout.** update-ref không cập nhật working tree/index. Dùng switch/reset theo mục đích hoặc dừng thao tác.

**Transaction chỉ cập nhật được một phần?** Với transaction stdin được chuẩn bị và commit đúng cách, Git áp dụng nhóm cập nhật như một đơn vị. Nếu lỗi, đọc lại toàn bộ ref và không suy đoán trạng thái.

**Không tìm thấy reflog.** Một số ref chưa có reflog hoặc reflog đã hết hạn. Có thể dùng --create-reflog khi cập nhật và duy trì backup phù hợp.

**File .lock còn tồn tại.** Kiểm tra tiến trình Git còn chạy hay không. Không xóa lock thủ công khi chưa xác định nguyên nhân và quyền sở hữu.

## 14. Checklist bảo vệ tính nhất quán của ref

**Trước cập nhật**

- [ ] Dùng tên ref đầy đủ và đã kiểm tra định dạng.
- [ ] Đọc lại object ID hiện tại.
- [ ] Xác nhận object đích tồn tại và đúng loại.
- [ ] Kiểm tra điều kiện fast-forward hoặc chính sách dự án.
- [ ] Xác nhận branch không được checkout trong worktree liên quan.
- [ ] Xác định có cần cập nhật nhiều ref trong một transaction hay không.

**Trong khi cập nhật**

- [ ] Truyền expected old-oid để tránh ghi đè thay đổi đồng thời.
- [ ] Dùng transaction cho nhóm ref cần tính nguyên tử.
- [ ] Ghi lý do vào reflog khi phù hợp.
- [ ] Không sửa trực tiếp file trong .git/refs hoặc packed-refs.
- [ ] Không xóa lock khi chưa xác định tiến trình đang dùng.

**Sau cập nhật**

- [ ] Xác minh ref trỏ tới object mong đợi.
- [ ] Kiểm tra reflog nếu cần truy vết.
- [ ] Kiểm tra HEAD, index và working tree.
- [ ] Ghi log kết quả và xử lý lỗi rõ ràng.
- [ ] Bảo đảm quy trình cấp cao hoặc worktree liên quan vẫn nhất quán.

## 15. Kết luận

git update-ref là công cụ plumbing để thay đổi ref có kiểm soát. Điều kiện old-oid giúp phát hiện cập nhật đồng thời, các lệnh stdin như create, verify, delete và transaction cho phép quản lý ref chính xác hơn, còn reflog hỗ trợ truy vết những lần di chuyển.

Tính nguyên tử của ref không tự đồng nghĩa với tính nhất quán của toàn bộ working tree. update-ref không checkout commit mới và không đồng bộ index; vì vậy cần tránh di chuyển branch đang được checkout. Hãy dùng lệnh cấp cao cho thao tác làm việc thông thường, dùng update-ref cho công cụ quản trị có kiểm tra rõ ràng, và luôn xác minh ref, object, worktree cùng trạng thái sau cập nhật.
