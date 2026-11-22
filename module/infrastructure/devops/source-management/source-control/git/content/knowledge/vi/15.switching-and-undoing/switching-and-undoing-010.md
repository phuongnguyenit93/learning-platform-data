# Áp dụng thay đổi không tạo commit bằng cherry-pick --no-commit

Trong một dự án, đôi khi bạn cần lấy một thay đổi từ nhánh khác nhưng muốn tự quyết định nội dung và thời điểm tạo commit. Ví dụ, một commit sửa lỗi đã có trên nhánh phát triển cần được đưa sang nhánh bảo trì; hoặc nhiều commit nhỏ cần được kết hợp thành một commit duy nhất trên nhánh đích. Git hỗ trợ cách làm này bằng <code>git cherry-pick --no-commit</code> (viết tắt là <code>git cherry-pick -n</code>).

Tùy chọn <code>--no-commit</code> yêu cầu Git áp dụng thay đổi của commit được chọn vào **working tree và index**, nhưng không tự tạo commit. Bạn có thể kiểm tra diff, chỉnh sửa nội dung, chọn một phần thay đổi hoặc kết hợp nhiều commit rồi mới commit theo mục đích của nhánh đích.

Bài này thuộc chương **Chuyển và hoàn tác** của module **SOURCE_CONTROL_GIT**. Module hướng dẫn Git từ working tree, staging area, commit và lịch sử đến branch, merge, rebase, remote và tag; đồng thời rèn cách cộng tác qua nhánh, giải quyết xung đột, truy tìm thay đổi và khôi phục thao tác sai mà vẫn bảo toàn lịch sử quan trọng. Hiểu rõ index, working tree và HEAD khi cherry-pick không tạo commit giúp bạn chuyển thay đổi có kiểm soát giữa các nhánh.

## 1. Cherry-pick thông thường và cherry-pick --no-commit

<code>git cherry-pick</code> lấy thay đổi được giới thiệu bởi một hoặc nhiều commit nguồn rồi áp dụng lên nhánh hiện tại. Git không chuyển nhánh hiện tại sang commit nguồn; nó tạo một commit mới trên nhánh đích với thay đổi tương ứng.

Với cherry-pick thông thường:

~~~bash
git switch release/2.x
git cherry-pick a1b2c3d
~~~

Nếu áp dụng thành công, Git tự tạo một commit mới trên <code>release/2.x</code>. Commit mới có nội dung thay đổi tương ứng với commit nguồn, nhưng thường có hash khác vì commit cha và metadata của nó khác.

Với <code>--no-commit</code>:

~~~bash
git switch release/2.x
git cherry-pick --no-commit a1b2c3d
~~~

Git áp dụng thay đổi vào working tree và index, nhưng dừng trước bước tạo commit. HEAD và nhánh hiện tại vẫn trỏ đến commit cũ cho đến khi bạn chủ động chạy <code>git commit</code> hoặc thực hiện thao tác khác làm di chuyển nhánh.

| Cách chạy | Working tree | Index | HEAD / nhánh hiện tại |
|---|---|---|---|
| <code>git cherry-pick &lt;commit&gt;</code> thành công | Chứa snapshot sau khi áp dụng | Được cập nhật | Di chuyển đến commit mới |
| <code>git cherry-pick --no-commit &lt;commit&gt;</code> thành công | Chứa nội dung đã áp dụng | Chứa thay đổi đã staging | Giữ nguyên vị trí |

Với trạng thái làm việc sạch trước khi bắt đầu, thay đổi được áp dụng thường xuất hiện ở phần staged. Vì vậy, <code>git diff --staged</code> là lệnh quan trọng để xem nội dung sẽ đi vào commit tiếp theo.

## 2. Khi nào nên dùng --no-commit?

Một số tình huống phù hợp:

- **Gom nhiều commit thành một:** lấy các commit nhỏ từ nhánh tính năng, kiểm tra kết quả rồi tạo một commit tổng hợp trên nhánh đích.
- **Chuyển một phần thay đổi:** áp dụng commit nguồn, sau đó chọn các tệp hoặc hunk cần đưa vào commit.
- **Điều chỉnh trước khi commit:** áp dụng một bản sửa lỗi từ nhánh khác rồi sửa lại tên, cấu hình hoặc chi tiết phù hợp với nhánh hiện tại.
- **Chuẩn bị thay đổi cho nhánh bảo trì:** lấy phần sửa cần thiết từ nhánh phát triển mà không phải giữ nguyên cấu trúc commit của nhánh nguồn.
- **Kiểm tra trước khi quyết định:** đưa patch vào index để review và chạy test trước khi tạo commit.

<code>--no-commit</code> đặc biệt hữu ích khi nội dung cần chuyển là đúng, nhưng bạn muốn commit cuối cùng phản ánh mục đích của nhánh đích. Ví dụ, nhánh nguồn có ba commit gồm sửa mã, thêm test và chỉnh tài liệu; nhánh release có thể cần một commit duy nhất đã được kiểm tra đầy đủ.

## 3. Chuẩn bị trước khi cherry-pick

Trước tiên, xác định nhánh hiện tại là nhánh đích và commit nguồn chứa đúng thay đổi cần lấy.

~~~bash
# Kiểm tra nhánh và trạng thái làm việc
git branch --show-current
git status

# Xem các nhánh và lịch sử gần đây
git branch -a
git log --oneline --graph --decorate -20

# Xem nội dung commit nguồn
git show --stat a1b2c3d
git show a1b2c3d
~~~

Nên bắt đầu với working tree sạch và index sạch để dễ phân biệt thay đổi do cherry-pick tạo ra. Nếu đã có thay đổi local cần giữ, hãy commit hoặc lưu chúng an toàn trước khi tiếp tục. <code>--no-commit</code> cho phép index hiện tại khác HEAD, nhưng khi index đã có thay đổi staged từ trước, commit tiếp theo có thể chứa cả những thay đổi đó lẫn patch vừa cherry-pick.

Một quy trình chuẩn bị đơn giản:

1. Xác nhận đúng repository và nhánh đích.
2. Fetch nếu commit nguồn nằm trên remote và chưa có trong local.
3. Xem commit nguồn bằng <code>git show</code>.
4. Xác nhận các thay đổi đó chưa có sẵn trên nhánh đích.
5. Kiểm tra working tree và index; lưu lại thay đổi local cần giữ.

Ví dụ:

~~~bash
git fetch origin
git switch release/2.x
git status
git show --stat a1b2c3d
~~~

Nếu commit nguồn chỉ tồn tại trên remote-tracking branch, bạn có thể dùng hash của commit hoặc tên tham chiếu như <code>origin/feature/payment-fix</code>.

## 4. Áp dụng một commit mà không tạo commit mới

Giả sử commit <code>a1b2c3d</code> chứa bản sửa lỗi kiểm tra số tiền và bạn muốn áp dụng nó vào nhánh <code>release/2.x</code>:

~~~bash
# Chuyển đến nhánh đích
git switch release/2.x

# Áp dụng thay đổi nhưng không tạo commit
git cherry-pick --no-commit a1b2c3d

# Kiểm tra trạng thái và nội dung đã staging
git status
git diff --staged
~~~

Sau lệnh cherry-pick, Git đã áp dụng patch vào index và working tree. HEAD vẫn ở commit trước đó. Nếu <code>git status</code> cho thấy các tệp đã staged, đây là trạng thái bình thường khi thao tác thành công và không có xung đột.

Bạn có thể xem thêm toàn bộ khác biệt so với commit hiện tại:

~~~bash
# Phần đã staging so với HEAD
git diff --staged

# Phần đã sửa thêm trong working tree nhưng chưa staging
git diff

# Tổng khác biệt của working tree so với HEAD
git diff HEAD

# Kiểm tra lỗi khoảng trắng
git diff --check
~~~

Nếu nội dung đúng và test đạt, tạo commit theo thông điệp phù hợp với nhánh đích:

~~~bash
git commit -m "fix: validate payment amount on release branch"
~~~

Commit này là commit mới do bạn tạo trên nhánh đích. Git không tự giữ nguyên thông điệp hoặc danh tính tác giả của commit nguồn theo cách cherry-pick thông thường thực hiện; bạn quyết định thông điệp và nội dung commit cuối cùng. Nếu cần truy vết nguồn, hãy ghi hash commit gốc hoặc tham chiếu ticket trong nội dung commit hoặc pull request.

## 5. Kết hợp nhiều commit thành một commit

Một lợi ích quan trọng của <code>--no-commit</code> là có thể áp dụng nhiều commit liên tiếp mà chưa tạo commit trung gian.

Giả sử nhánh <code>feature/export</code> có ba commit:

~~~text
a111111 feat: add export endpoint
b222222 test: cover export endpoint
c333333 docs: describe export endpoint
~~~

Bạn muốn đưa cả ba thay đổi sang <code>release/2.x</code> và tạo một commit duy nhất:

~~~bash
# Chuyển đến nhánh đích
git switch release/2.x

# Áp dụng lần lượt từ commit cũ đến commit mới
git cherry-pick --no-commit a111111 b222222 c333333

# Review tất cả thay đổi đã staging
git status
git diff --staged

# Chạy test và tạo một commit tổng hợp
git commit -m "feat: add export endpoint to release"
~~~

Hãy áp dụng theo thứ tự phụ thuộc của các commit, thường là từ commit cũ đến commit mới. Nếu commit kiểm thử phụ thuộc vào mã nguồn được thêm bởi commit trước, phải áp dụng commit mã nguồn trước để patch kiểm thử có nền tảng phù hợp.

Các commit nguồn vẫn tồn tại trong nhánh <code>feature/export</code>. Trên nhánh đích, một commit mới chứa tổng thay đổi đã áp dụng. Lịch sử nhánh đích không tự động nhận các commit nguồn làm tổ tiên, vì cherry-pick sao chép thay đổi chứ không hợp nhất quan hệ tổ tiên như merge.

Bạn có thể xem danh sách commit nguồn theo thứ tự cũ đến mới bằng:

~~~bash
git log --oneline --reverse release/2.x..feature/export
~~~

Chỉ dùng phạm vi trên khi <code>release/2.x</code> là nền phù hợp để so sánh với <code>feature/export</code>. Nếu hai nhánh đã có lịch sử khác nhau hoặc đã từng cherry-pick lẫn nhau, hãy đọc đồ thị commit và xác định chính xác các hash cần áp dụng.

## 6. Chọn một phần thay đổi trước khi commit

Sau khi cherry-pick không tạo commit, toàn bộ patch thường đã nằm trong index. Bạn có thể bỏ staging một tệp hoặc một phần thay đổi rồi quyết định nội dung commit cuối cùng.

### Bỏ staging toàn bộ một tệp nhưng giữ nội dung

~~~bash
git restore --staged -- src/ExportController.java
~~~

Lệnh này đưa nội dung staged của tệp về trạng thái trong HEAD ở index, nhưng giữ thay đổi trong working tree. Tệp sẽ chuyển từ staged sang modified chưa staging. Bạn có thể sửa thêm hoặc staging lại phần cần thiết.

### Bỏ staging theo từng hunk

~~~bash
git restore --staged -p -- src/ExportController.java
~~~

Git lần lượt hỏi bạn có muốn bỏ staging từng phần thay đổi hay không. Chọn hunk cần đưa ra khỏi index. Những phần bị bỏ staging vẫn còn trong working tree, vì vậy bạn có thể commit phần staged trước và xử lý phần còn lại sau.

Trên phiên bản Git cũ hơn hoặc theo thói quen sử dụng, có thể dùng:

~~~bash
git reset -p -- src/ExportController.java
~~~

Đây là cách cập nhật index theo từng hunk, không di chuyển HEAD khi dùng dạng pathspec này.

### Staging lại phần muốn commit

Sau khi chọn xong, kiểm tra cả hai vùng:

~~~bash
# Phần sẽ được commit
git diff --staged

# Phần còn lại trong working tree
git diff

# Trạng thái theo từng đường dẫn
git status --short
~~~

Nếu phần staged đã đúng, tạo commit:

~~~bash
git commit -m "fix: apply selected export validation changes"
~~~

Những phần chưa staging tiếp tục nằm trong working tree sau commit. Hãy xử lý chúng riêng, tránh vô tình đưa vào commit tiếp theo.

## 7. Chỉnh sửa nội dung sau khi cherry-pick

<code>--no-commit</code> cho phép sửa patch trước khi tạo commit. Ví dụ, commit nguồn dùng tên cấu hình phù hợp với môi trường phát triển nhưng nhánh release cần giá trị mặc định khác. Bạn có thể chỉnh tệp sau khi cherry-pick, sau đó kiểm tra lại:

~~~bash
# Sau khi sửa tệp
git status
git diff
git diff --staged

# Stage nội dung cuối cùng
git add config/application-release.yml

# Kiểm tra snapshot sẽ commit
git diff --staged
~~~

Nếu tệp đã được staged từ lúc cherry-pick, sửa tiếp tệp sẽ tạo phần khác biệt chưa staging. Vì vậy, có thể cùng một tệp xuất hiện ở cả <code>git diff --staged</code> và <code>git diff</code>: phần thứ nhất là phiên bản đã áp dụng từ commit nguồn, phần thứ hai là phần bạn sửa thêm sau đó.

Đừng chỉ nhìn working tree rồi cho rằng toàn bộ nội dung đã nằm trong commit. <code>git commit</code> thông thường lấy snapshot từ index. Luôn xem <code>git diff --staged</code> trước khi commit.

## 8. Xử lý xung đột khi cherry-pick --no-commit

Nếu patch không áp dụng sạch lên nhánh đích, Git tạm dừng và báo các tệp xung đột. Một số tệp có thể đã được áp dụng thành công, trong khi các tệp khác ở trạng thái unmerged. Không được giả định toàn bộ thao tác đã thất bại hoặc toàn bộ thay đổi đã hoàn tất.

Quy trình xử lý:

~~~bash
# Xác định các tệp xung đột
git status

# Mở và chỉnh sửa các tệp có conflict markers
# Sau khi chọn nội dung cuối cùng:
git add src/ExportController.java

# Kiểm tra các thay đổi đã staging
git diff --staged
git status

# Tiếp tục tiến trình cherry-pick nếu Git đang giữ trạng thái sequencer
git cherry-pick --continue
~~~

Với một lần cherry-pick đơn lẻ, sau khi giải quyết xung đột, hãy làm theo trạng thái và hướng dẫn Git hiển thị. Với chuỗi nhiều commit, <code>--continue</code> cho phép tiếp tục xử lý các commit còn lại trong tiến trình đang dở. Do dùng <code>--no-commit</code>, mục tiêu cuối cùng vẫn là để thay đổi trong index và working tree mà không tạo commit tự động.

Nếu không muốn tiếp tục tiến trình đang dở:

~~~bash
git cherry-pick --abort
~~~

<code>--abort</code> hủy tiến trình cherry-pick đang được Git quản lý và khôi phục trạng thái trước khi tiến trình bắt đầu. Lệnh này phù hợp khi Git đang báo một cherry-pick chưa hoàn tất, chẳng hạn do conflict.

Nếu cherry-pick <code>--no-commit</code> đã áp dụng thành công và kết thúc bình thường, không còn tiến trình để abort. Khi đó, nếu muốn bỏ patch vừa áp dụng, hãy xác định chính xác các đường dẫn bị ảnh hưởng và đảm bảo chúng không có thay đổi local cần giữ trước khi khôi phục từ HEAD:

~~~bash
# Chỉ dùng với đường dẫn đã sạch trước khi cherry-pick
git restore --source=HEAD --staged --worktree -- src/ExportController.java
~~~

Lệnh restore trên thay cả index và working tree của đường dẫn được chỉ định bằng nội dung từ HEAD. Nó sẽ loại bỏ cả các chỉnh sửa khác trên cùng đường dẫn, vì vậy không dùng nếu bạn đã có thay đổi riêng cần giữ. Nếu không chắc, hãy sao lưu hoặc lưu lại thay đổi trước khi khôi phục.

## 9. Cherry-pick một merge commit

Một merge commit có nhiều hơn một parent. Khi cherry-pick merge commit, Git cần biết parent nào được xem là mainline để xác định thay đổi cần áp dụng. Nếu không chỉ định, Git thường báo lỗi yêu cầu chọn mainline.

Ví dụ:

~~~bash
git cherry-pick --no-commit -m 1 <merge-commit-hash>
~~~

<code>-m 1</code> yêu cầu Git xem parent thứ nhất là mainline và áp dụng khác biệt giữa merge commit với parent đó. Nếu chọn sai parent, nội dung được áp dụng có thể không phải phần thay đổi bạn mong muốn. Hãy kiểm tra merge commit trước:

~~~bash
git show --no-patch --pretty=raw <merge-commit-hash>
git diff <merge-commit-hash>^1 <merge-commit-hash>
git diff <merge-commit-hash>^2 <merge-commit-hash>
~~~

Các lệnh diff giúp hiểu kết quả merge khác gì so với từng parent. Chỉ chọn <code>-m</code> sau khi xác định đúng nhánh nền cần giữ. Với thay đổi phức tạp, có thể an toàn hơn nếu chọn các commit cụ thể thay vì cherry-pick cả merge commit.

## 10. Phân biệt cherry-pick --no-commit với các cách áp dụng patch khác

| Cách làm | Nguồn đầu vào | Kết quả chính |
|---|---|---|
| <code>git cherry-pick &lt;commit&gt;</code> | Một commit Git | Áp dụng thay đổi và tự tạo commit mới |
| <code>git cherry-pick -n &lt;commit&gt;</code> | Một hoặc nhiều commit Git | Áp dụng thay đổi vào index/working tree, không tự tạo commit |
| <code>git merge &lt;branch&gt;</code> | Lịch sử của một nhánh | Tích hợp lịch sử và có thể tạo merge commit hoặc fast-forward |
| <code>git apply &lt;patch&gt;</code> | Tệp patch/diff | Áp dụng patch; không dựa vào commit hash hay quan hệ cha-con của commit |
| <code>git revert &lt;commit&gt;</code> | Một commit đã có | Tạo thay đổi đảo ngược commit đó; với <code>-n</code>, không tự tạo commit |

<code>git cherry-pick -n</code> phù hợp khi nguồn thay đổi là commit trong repository và bạn muốn tận dụng khả năng xác định patch, áp dụng và xử lý xung đột của Git. Nếu bạn chỉ có một file patch độc lập, <code>git apply</code> có thể phù hợp hơn. Nếu muốn tích hợp toàn bộ lịch sử của nhánh, hãy cân nhắc merge.

### So sánh với git revert --no-commit

Hai lệnh có ý nghĩa ngược nhau:

- <code>git cherry-pick --no-commit &lt;commit&gt;</code> áp dụng thay đổi được giới thiệu bởi commit nguồn.
- <code>git revert --no-commit &lt;commit&gt;</code> áp dụng thay đổi đảo ngược commit được chọn.

Cả hai đều có thể để kết quả trong index và working tree mà chưa tạo commit. Hãy xác định mục tiêu là lấy một thay đổi hay hoàn tác một thay đổi trước khi chọn lệnh.

## 11. Những điều cần lưu ý khi commit kết quả

Khi đã áp dụng một hoặc nhiều commit bằng <code>--no-commit</code>, commit cuối cùng do bạn tạo có thể khác với commit nguồn:

- Thông điệp commit do bạn viết, nên mô tả kết quả trên nhánh đích.
- Nội dung có thể đã được chỉnh sửa, chọn lọc hoặc kết hợp.
- Tác giả/committer của commit mới phụ thuộc vào cấu hình và thông tin bạn dùng khi tạo commit.
- Các commit nguồn vẫn tồn tại trong nhánh gốc; cherry-pick không xóa chúng.
- Lịch sử nhánh đích chỉ có commit mới nếu bạn tự tạo commit.

Nếu cần giữ dấu vết nguồn, hãy ghi hash commit gốc, ticket hoặc pull request trong thông điệp commit. Với quy trình yêu cầu attribution, tuân theo quy ước ghi <code>Co-authored-by</code> hoặc ghi chú nguồn của nhóm.

Sau khi commit, xác nhận nhánh và lịch sử:

~~~bash
git status
git log --oneline --graph --decorate -10
git show --stat HEAD
~~~

Nếu commit trên nhánh đích cần được chia sẻ:

~~~bash
git push origin release/2.x
~~~

Hãy bảo đảm bạn đang push đúng nhánh và có quyền cập nhật. Nếu remote đã tiến lên, fetch và tích hợp theo quy trình của nhóm thay vì force push chỉ để thay thế lịch sử.

## 12. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra hoặc xử lý |
|---|---|---|
| Chạy <code>cherry-pick -n</code> nhưng không thấy commit mới | Đây là hành vi mong đợi; <code>-n</code> không tạo commit | Kiểm tra <code>git status</code> và <code>git diff --staged</code> |
| Commit tiếp theo chứa thay đổi không mong muốn | Index đã có thay đổi staged từ trước hoặc đã stage thêm tệp ngoài phạm vi | Xem <code>git diff --staged</code>, unstage phần không cần và kiểm tra lại |
| Một tệp có cả staged và unstaged changes | Bạn sửa tệp sau khi cherry-pick | Xem riêng <code>git diff --staged</code> và <code>git diff</code> |
| Cherry-pick báo conflict | Patch không áp dụng tự động lên trạng thái nhánh đích | Giải quyết tệp, <code>git add</code>, kiểm tra và continue |
| <code>--abort</code> không có tác dụng sau khi áp dụng thành công | Tiến trình cherry-pick đã kết thúc, không còn trạng thái để abort | Khôi phục đúng các đường dẫn từ HEAD nếu chúng sạch trước thao tác |
| Cherry-pick merge commit báo cần mainline | Merge commit có nhiều parent | Kiểm tra parent và dùng <code>-m</code> với parent phù hợp |
| Không thấy một số thay đổi trong commit nguồn | Commit sau phụ thuộc vào commit trước hoặc patch đã có trên nhánh đích | Kiểm tra lịch sử và áp dụng đúng thứ tự |
| Commit cuối cùng không giữ thông điệp nguồn | <code>--no-commit</code> không tự tạo commit metadata từ commit nguồn | Viết thông điệp mới và ghi nguồn nếu cần truy vết |

## 13. Quy trình thực hành an toàn

Quy trình dưới đây phù hợp khi cần lấy một thay đổi từ nhánh tính năng sang nhánh bảo trì:

~~~bash
# 1. Cập nhật thông tin remote
git fetch origin

# 2. Xem commit nguồn
git show --stat <source-commit>
git show <source-commit>

# 3. Chuyển sang nhánh đích và kiểm tra trạng thái
git switch release/2.x
git status

# 4. Áp dụng mà không tạo commit
git cherry-pick --no-commit <source-commit>

# 5. Kiểm tra các vùng thay đổi
git status
git diff --staged
git diff
git diff --check

# 6. Chạy test, chỉnh sửa và staging phần cuối cùng
# git add <path>

# 7. Tạo commit khi nội dung đã đúng
git commit -m "fix: describe the backported change"

# 8. Kiểm tra kết quả
git status
git show --stat HEAD
~~~

Với nhiều commit, thay bước 4 bằng danh sách hash theo thứ tự phụ thuộc:

~~~bash
git cherry-pick --no-commit <oldest-commit> <next-commit> <newest-commit>
~~~

Không chạy lệnh áp dụng nhiều commit một cách mù quáng. Hãy xác nhận từng commit thuộc cùng mục tiêu, xem các phụ thuộc và review toàn bộ diff sau khi áp dụng.

## 14. Bài tập tự kiểm tra

Thực hành trong repository thử nghiệm với hai nhánh:

1. Trên nhánh <code>feature/demo</code>, tạo một commit thêm một hàm nhỏ và push nhánh lên remote.
2. Chuyển sang nhánh <code>release/demo</code> và kiểm tra <code>git status</code>.
3. Chạy <code>git cherry-pick --no-commit &lt;commit-hash&gt;</code>. Quan sát HEAD có thay đổi không và các tệp xuất hiện ở trạng thái nào.
4. Chạy <code>git diff --staged</code> để xem patch được áp dụng.
5. Sửa một dòng trong tệp sau khi cherry-pick. So sánh <code>git diff --staged</code> với <code>git diff</code>.
6. Dùng <code>git restore --staged -p</code> để bỏ staging một hunk, rồi xem phần nào còn staged và phần nào còn trong working tree.
7. Commit phần đã chọn, sau đó kiểm tra thay đổi chưa staging vẫn còn hay không.
8. Tạo hai commit phụ thuộc nhau trên nhánh nguồn và áp dụng cả hai bằng một lệnh <code>cherry-pick --no-commit</code>; quan sát thứ tự áp dụng.
9. Tạo một tình huống xung đột trong repository thử nghiệm, giải quyết và tiếp tục; lặp lại để thử <code>git cherry-pick --abort</code>.
10. Giải thích sự khác nhau giữa <code>git cherry-pick --no-commit</code> và <code>git revert --no-commit</code>.

Khi hiểu rằng <code>cherry-pick --no-commit</code> đưa thay đổi vào index và working tree trong khi giữ nguyên HEAD, bạn có thể chọn lọc, chỉnh sửa và kết hợp patch trước khi tạo commit. Hãy luôn kiểm tra <code>git status</code> và <code>git diff --staged</code> để commit cuối cùng chỉ chứa những gì bạn chủ định đưa vào nhánh đích.
