# Giải quyết xung đột khi áp dụng stash và tạo nhánh bằng stash branch

## Stash lưu những gì và khi nào có thể xảy ra xung đột?

Git stash giúp tạm cất các thay đổi chưa commit để bạn có thể chuyển sang công việc khác. Khi cần, bạn áp dụng lại nội dung đã cất vào working tree hiện tại. Stash thường lưu thay đổi trong các tệp đang được Git theo dõi; tùy chọn bổ sung có thể đưa cả tệp chưa được theo dõi hoặc tệp bị ignore vào stash.

Stash không phải commit thông thường trên nhánh hiện tại và cũng không phải bản sao lưu lâu dài. Các stash entry được lưu trong danh sách riêng, thường được tham chiếu bằng tên như stash@{0}, stash@{1}. Entry mới nhất thường có chỉ số 0.

Một stash có thể được áp dụng sạch khi nhánh hiện tại vẫn gần với trạng thái lúc stash được tạo. Xung đột có thể xuất hiện khi:

- Nhánh hiện tại đã sửa cùng vùng mã với thay đổi được cất.
- Một tệp đã bị đổi tên hoặc xóa sau khi tạo stash.
- Một nhánh khác tạo tệp cùng đường dẫn với tệp chưa được theo dõi trong stash.
- Cấu hình, dependency hoặc cấu trúc thư mục đã thay đổi.
- Các thay đổi được cất phụ thuộc vào một commit hoặc API không còn tồn tại trên nhánh hiện tại.

Khi Git không thể kết hợp tự động, thao tác apply hoặc pop dừng lại với các tệp ở trạng thái unmerged. Bạn cần giải quyết nội dung như khi xử lý conflict trong merge, sau đó kiểm tra và stage kết quả.

Hai điều cần nhớ ngay từ đầu:

- git stash apply áp dụng stash nhưng giữ entry trong danh sách để có thể dùng lại hoặc xóa sau.
- git stash pop vừa áp dụng vừa cố gắng xóa entry nếu áp dụng thành công. Nếu có conflict, Git không xóa entry đó.

## Kiểm tra stash trước khi áp dụng

Trước khi lấy thay đổi trở lại, xem danh sách stash:

~~~bash
git stash list
~~~

Ví dụ:

~~~text
stash@{0}: On feature/search: WIP add search filters
stash@{1}: On main: WIP update report layout
stash@{2}: On fix/login: WIP handle expired session
~~~

Mỗi entry có thể có thông điệp giúp nhận diện công việc. Nếu cần xem nội dung tóm tắt:

~~~bash
git stash show 'stash@{0}'
~~~

Xem patch đầy đủ của stash:

~~~bash
git stash show -p 'stash@{0}'
~~~

Có thể xem thêm tệp chưa được theo dõi đã được lưu trong stash bằng:

~~~bash
git stash show --include-untracked -p 'stash@{0}'
~~~

Nếu stash được tạo bằng tùy chọn bao gồm tệp ignored, hãy kiểm tra kỹ các tệp đó trước khi áp dụng. Tệp build, cache hoặc dữ liệu cục bộ có thể không nên đưa sang nhánh khác.

Trước khi apply hoặc pop, kiểm tra trạng thái working tree:

~~~bash
git status
git branch --show-current
~~~

Nếu working tree đã có thay đổi chưa commit, hãy hiểu rõ chúng thuộc công việc nào. Áp dụng stash lên một working tree đang chứa thay đổi khác có thể gây thêm conflict hoặc làm khó việc phân biệt nguồn gốc từng phần thay đổi.

### Chọn đúng stash entry

Không nên mặc định stash@{0} luôn là entry cần áp dụng. Nếu có nhiều stash, hãy đọc thông điệp và nội dung từng entry.

Có thể xem commit nền mà stash được tạo từ:

~~~bash
git log -1 --oneline 'stash@{0}^1'
~~~

Stash entry thường có cấu trúc commit riêng, trong đó parent đầu tiên đại diện cho commit HEAD tại thời điểm stash được tạo. Thông tin này hữu ích khi cần xác định nhánh hoặc trạng thái nền ban đầu.

Nếu muốn xem toàn bộ metadata của stash:

~~~bash
git show --no-patch --pretty=raw 'stash@{0}'
~~~

Lưu lại đúng entry trước khi thao tác. Chỉ số stash có thể thay đổi khi thêm hoặc xóa entry khác.

## Áp dụng stash bằng git stash apply

Lệnh apply đưa nội dung của stash vào working tree hiện tại:

~~~bash
git stash apply 'stash@{0}'
~~~

Nếu không truyền entry, Git mặc định áp dụng stash mới nhất. Trong công việc nhóm hoặc khi có nhiều stash, nên chỉ rõ entry để tránh chọn nhầm.

Sau khi áp dụng, kiểm tra:

~~~bash
git status
git diff
git diff --cached
~~~

Thông thường, các thay đổi được áp dụng vào working tree. Nếu stash từng lưu cả nội dung staged, có thể dùng tùy chọn --index để yêu cầu Git khôi phục cả trạng thái staging:

~~~bash
git stash apply --index 'stash@{0}'
~~~

--index hữu ích khi bạn muốn giữ sự phân biệt giữa phần đã stage và chưa stage như thời điểm stash được tạo. Tuy nhiên, việc khôi phục index có thể thất bại nếu trạng thái hiện tại có conflict hoặc không thể tái lập đúng các entry cũ. Khi đó, hãy xem git status và quyết định staging lại thủ công sau khi giải quyết.

Khác với pop, apply không tự xóa stash entry sau khi áp dụng thành công. Bạn có thể kiểm tra, chạy test, commit hoặc áp dụng lại stash ở một thời điểm khác.

## Nhận biết xung đột sau khi apply hoặc pop

Giả sử bạn đã cất thay đổi của SearchService trên nhánh feature/search. Trong lúc đó, nhánh main thay đổi cùng phương thức. Khi chuyển sang main và áp dụng stash, Git không thể tự kết hợp hai phiên bản.

Bắt đầu bằng:

~~~bash
git status
~~~

Git sẽ liệt kê các đường dẫn đang ở trạng thái both modified, added by us, deleted by them hoặc trạng thái unmerged tương ứng.

Để liệt kê chính xác đường dẫn còn xung đột:

~~~bash
git diff --name-only --diff-filter=U
git ls-files -u
~~~

Với conflict nội dung thông thường, index có các stage:

| Stage | Ý nghĩa |
|---|---|
| 1 | Phiên bản cơ sở chung (merge base), nếu có |
| 2 | Phiên bản phía hiện tại (ours) |
| 3 | Phiên bản phía được áp dụng từ stash (theirs) |

Trong ngữ cảnh áp dụng stash, cách hiểu ours/theirs cần gắn với thao tác Git đang thực hiện. Ours thường là nội dung của nhánh và working tree hiện tại; theirs là nội dung được lấy từ stash. Không nên chọn toàn bộ một phía chỉ dựa trên tên, vì có thể làm mất thay đổi ở phía còn lại.

Xem các phiên bản đang nằm trong index:

~~~bash
git show :1:src/SearchService.java
git show :2:src/SearchService.java
git show :3:src/SearchService.java
~~~

Một số loại conflict như add/add, modify/delete hoặc rename không có đủ cả ba stage. Nếu một lệnh không tìm thấy stage tương ứng, hãy kiểm tra loại conflict và trạng thái tệp.

## Quy trình giải quyết conflict sau stash apply

### Bước 1: Xác định thay đổi được cất và thay đổi hiện tại

Trước khi sửa, xem stash patch:

~~~bash
git stash show -p 'stash@{0}'
~~~

Xem diff của working tree và trạng thái index:

~~~bash
git diff
git diff --cached
git status
~~~

Nếu cần, xem nội dung từng phía bằng git show :1:, :2: và :3: như phần trên.

Hãy xác định:

- Thay đổi nào đã có trên nhánh hiện tại?
- Stash muốn bổ sung hoặc sửa hành vi nào?
- Hai phần có thể kết hợp mà vẫn giữ đúng logic không?
- Có API, cấu hình, schema hoặc kiểm thử nào phụ thuộc vào thay đổi này không?
- Có tệp nào được thêm, xóa hoặc đổi tên cần quyết định rõ ràng không?

### Bước 2: Chỉnh sửa nội dung cuối cùng

Ví dụ nhánh hiện tại đã bổ sung kiểm tra quyền, còn stash chứa thay đổi thêm bộ lọc ngày cho báo cáo. Hai thay đổi cùng chạm vào phương thức:

~~~java
public Report exportReport(User user, ReportFilter filter) {
    // Phần kiểm tra quyền và bộ lọc ngày đang xung đột
}
~~~

Kết quả cuối cần bảo toàn cả hai hành vi:

~~~java
public Report exportReport(User user, ReportFilter filter) {
    permissionService.requireCanExport(user);

    return reportService.createReport(filter);
}
~~~

Đây là ví dụ minh họa. Với mã nguồn thực tế, hãy kiểm tra điều kiện phân quyền, cách xử lý bộ lọc rỗng, múi giờ và các trường hợp biên theo hợp đồng của ứng dụng.

Nếu conflict nằm trong tệp cấu hình, kiểm tra khóa, kiểu dữ liệu, giá trị mặc định và profile. Nếu nằm trong dependency manifest hoặc lockfile, xác nhận các phiên bản tương thích và sinh lại lockfile theo quy trình dự án. Với tệp bị xóa hoặc đổi tên, xác định rõ đường dẫn cuối cùng cần tồn tại.

### Bước 3: Tìm marker xung đột

Tệp văn bản có thể chứa các marker:

~~~text
<<<<<<< HEAD
Nội dung phía hiện tại
=======
Nội dung được lấy từ stash
>>>>>>> Stashed changes
~~~

Sau khi chỉnh sửa, tìm marker trong các tệp từng xung đột:

~~~bash
rg -n '^(<<<<<<<|=======|>>>>>>>|\|\|\|\|\|\|\|)' -- src/SearchService.java config/application.yml
~~~

Nếu không có kết quả và lệnh trả mã thoát 1, không tìm thấy dòng khớp. Nếu công cụ báo lỗi đọc tệp hoặc đường dẫn, cần xử lý lỗi đó trước khi kết luận. Chuỗi marker có thể xuất hiện hợp lệ trong tài liệu hoặc fixture kiểm thử, vì vậy hãy đánh giá theo ngữ cảnh.

### Bước 4: Đọc lại diff

~~~bash
git diff
git diff --check
~~~

Đảm bảo nội dung cuối cùng giữ đúng ý định của cả thay đổi hiện tại và stash. Không chỉ xóa marker để Git hết báo conflict; hãy kiểm tra logic, xử lý lỗi, điều kiện bảo mật và các trường hợp biên.

### Bước 5: Stage kết quả

Khi đã giải quyết xong, đưa từng tệp vào staging area:

~~~bash
git add -- src/SearchService.java config/application.yml
~~~

Nếu quyết định xóa một tệp:

~~~bash
git rm -- path/to/obsolete-file
~~~

Kiểm tra trạng thái và staged diff:

~~~bash
git status
git diff --name-only --diff-filter=U
git ls-files -u
git diff --cached
git diff --cached --check
~~~

Không còn đường dẫn unmerged là điều kiện cần để tiếp tục. Nếu muốn giữ lại một phần thay đổi trong trạng thái chưa stage, bạn có thể dùng git add -p để chọn từng phần; sau đó kiểm tra cả git diff và git diff --cached.

### Bước 6: Kiểm tra hành vi sau khi kết hợp

Chạy những kiểm tra gần với phần vừa sửa:

- Unit test cho lớp hoặc package liên quan.
- Kiểm tra cú pháp hoặc khả năng nạp cấu hình nếu tệp cấu hình bị xung đột.
- Build module bị ảnh hưởng.
- Test tích hợp nếu thay đổi liên quan đến API, cơ sở dữ liệu hoặc giao tiếp giữa các thành phần.

Nếu stash được tạo từ một nhánh khác, hãy xác nhận các thay đổi được áp dụng có còn tương thích với phiên bản code hiện tại hay không. Việc Git không còn conflict không đảm bảo chức năng hoạt động đúng.

## Điều gì xảy ra với stash sau khi apply hoặc pop?

Đây là khác biệt quan trọng khi xử lý conflict.

### Sau git stash apply

Apply không xóa stash entry, kể cả khi áp dụng thành công:

~~~bash
git stash apply 'stash@{0}'
git stash list
~~~

Nếu có conflict, stash vẫn được giữ. Sau khi giải quyết, stage, test và commit nếu cần, bạn có thể giữ entry để dự phòng hoặc xóa thủ công khi chắc chắn không còn cần dùng:

~~~bash
git stash drop 'stash@{0}'
~~~

Trước khi drop, kiểm tra lại danh sách vì chỉ số stash có thể thay đổi nếu trong lúc làm việc có stash mới được tạo hoặc entry khác bị xóa. Không drop entry chỉ vì apply đã chạy xong; hãy xác nhận nội dung đã được phục hồi đầy đủ.

### Sau git stash pop

Pop áp dụng stash rồi cố gắng xóa entry nếu quá trình áp dụng thành công:

~~~bash
git stash pop 'stash@{0}'
~~~

Nếu pop gặp conflict, Git không xóa stash entry. Bạn giải quyết tệp và tiếp tục làm việc như thay đổi bình thường trong working tree. Không có lệnh git stash --continue cho thao tác này.

Sau khi xử lý xong conflict, kiểm tra:

~~~bash
git status
git stash list
~~~

Nếu stash vẫn còn và bạn đã xác nhận nội dung được áp dụng đầy đủ, có thể xóa entry bằng:

~~~bash
git stash drop 'stash@{0}'
~~~

Nếu chưa chắc chắn, hãy giữ stash lại. Bạn có thể xem lại patch, chạy test hoặc tạo một commit an toàn trước khi quyết định drop.

### Không áp dụng lại stash chỉ vì còn conflict

Khi apply hoặc pop đã dừng vì conflict, các thay đổi đã được đưa một phần vào working tree và index. Không chạy lại cùng lệnh apply/pop ngay lập tức, vì điều đó có thể làm trạng thái khó hiểu hơn hoặc tạo thêm xung đột.

Hãy giải quyết trạng thái hiện tại trước. Stash entry còn nguyên để bạn có thể đối chiếu hoặc thử lại trên một nhánh khác nếu cần.

## Tạo nhánh từ stash bằng git stash branch

Đôi khi stash được tạo trên một nhánh có nền code cũ. Sau đó, bạn chuyển sang một nhánh đã thay đổi nhiều và apply gặp conflict. Nếu thay đổi được cất vốn thuộc về nền cũ, cách phù hợp có thể là tạo một nhánh mới ngay từ commit nền ban đầu của stash.

Cú pháp:

~~~bash
git stash branch <branch-name> [<stash>]
~~~

Ví dụ:

~~~bash
git stash branch feature/resume-search 'stash@{0}'
~~~

Git sẽ:

1. Tạo và chuyển sang nhánh feature/resume-search.
2. Đặt nhánh mới tại commit mà stash được tạo ra.
3. Áp dụng thay đổi đã lưu trong stash vào working tree và index của nhánh mới.
4. Nếu áp dụng thành công, xóa stash entry được chỉ định.

Cách này hữu ích khi nhánh hiện tại đã tiến xa so với nền ban đầu và stash không thể áp dụng sạch. Bắt đầu từ commit gốc thường giúp Git tìm được ngữ cảnh gần với lúc thay đổi được tạo.

Lệnh không tự tạo commit cho nội dung được phục hồi. Sau khi tạo nhánh, bạn vẫn cần kiểm tra trạng thái, đọc diff, chạy test và commit theo quy trình.

### Vì sao stash branch có thể giảm conflict?

Giả sử bạn tạo stash trên feature/search tại commit A. Sau đó main phát triển tới commit D và bạn chuyển sang main. Nếu áp dụng stash trực tiếp trên D, các tệp có thể đã thay đổi đáng kể.

~~~text
A---B---C---D  main
^
feature/search ở A khi stash được tạo
~~~

Stash entry lưu thay đổi dựa trên commit A; nó được lưu riêng và không phải một nhánh Git. Nếu áp dụng stash lên D, Git phải kết hợp thay đổi được tạo trên nền A với code hiện tại ở D. Nếu hai bên sửa cùng khu vực, conflict có thể xuất hiện.

Dùng stash branch:

~~~bash
git stash branch feature/resume-search 'stash@{0}'
~~~

Git tạo nhánh từ A rồi áp dụng stash tại nền ban đầu. Sau đó bạn có thể kiểm tra, commit công việc và cập nhật nhánh theo quy trình merge hoặc rebase của nhóm.

Đây là cách đưa công việc trở lại đúng ngữ cảnh ban đầu. Nó không đảm bảo luôn hết conflict: nếu stash tự nó có thay đổi không tương thích với commit nền hoặc chứa xung đột về tệp, bạn vẫn cần xử lý.

### Nếu stash branch gặp conflict

Nếu lệnh tạo nhánh thành công nhưng áp dụng stash dừng vì conflict:

~~~bash
git status
git diff --name-only --diff-filter=U
git ls-files -u
~~~

Bạn đang ở nhánh mới được tạo từ base của stash. Giải quyết conflict như quy trình apply thông thường: chỉnh sửa, kiểm tra marker, stage tệp và chạy test.

Không có lệnh git stash branch --continue. Sau khi giải quyết, hãy tiếp tục công việc trên nhánh mới và kiểm tra stash list. Git chỉ tự drop stash khi bước áp dụng của stash branch thành công; nếu có lỗi, không giả định entry đã bị xóa.

Nếu stash vẫn còn, chỉ drop sau khi xác nhận thay đổi đã được phục hồi đầy đủ:

~~~bash
git stash list
git stash drop 'stash@{0}'
~~~

Hãy chắc chắn stash@{0} vẫn là entry đúng trước khi drop; chỉ số có thể thay đổi theo danh sách hiện tại.

Trước khi gọi git stash branch, hãy đảm bảo working tree và index cho phép chuyển sang commit nền của stash. Nếu một lần git stash apply trước đó đã để lại conflict, không chạy stash branch ngay trên trạng thái unmerged đó. Hãy hoàn tất việc giải quyết hiện tại hoặc đưa kho về trạng thái trước lần apply một cách có chủ đích, đồng thời bảo toàn mọi thay đổi có trước; sau đó mới tạo nhánh từ stash.

## So sánh apply, pop và branch

| Lệnh | Nơi áp dụng | Stash entry sau khi thành công | Khi conflict |
|---|---|---|---|
| git stash apply | Working tree hiện tại | Được giữ lại | Giải quyết như thay đổi bình thường; stash vẫn còn |
| git stash pop | Working tree hiện tại | Được xóa nếu áp dụng thành công | Không xóa entry khi có conflict |
| git stash branch | Nhánh mới từ commit nền gốc của stash | Được xóa nếu áp dụng thành công | Giải quyết trên nhánh mới; kiểm tra lại entry trước khi drop |

Chọn lệnh theo mục tiêu:

- Dùng apply khi muốn giữ stash để kiểm tra hoặc có thể áp dụng lại.
- Dùng pop khi muốn phục hồi công việc và xóa stash nếu thành công.
- Dùng branch khi muốn phục hồi công việc trên nền ban đầu vì nhánh hiện tại đã thay đổi nhiều.

## Xử lý tệp chưa được theo dõi và tệp ignored

Mặc định, git stash push không bao gồm tệp chưa được theo dõi (untracked) và tệp bị ignore.

Nếu muốn lưu cả untracked:

~~~bash
git stash push -u -m "WIP include untracked files"
~~~

Nếu muốn lưu cả ignored:

~~~bash
git stash push -a -m "WIP include ignored files"
~~~

Khi apply hoặc pop, Git có thể không phục hồi được một tệp nếu working tree hiện tại đã có tệp cùng đường dẫn. Đây có thể là lỗi khôi phục untracked file, không nhất thiết là conflict nội dung thông thường có marker.

Kiểm tra tệp và trạng thái trước khi xử lý:

~~~bash
git status --short
git stash show --include-untracked -p 'stash@{0}'
~~~

Nếu có tệp cùng tên, xác định nội dung nào cần giữ và di chuyển hoặc đổi tên tệp hiện tại một cách có chủ đích trước khi thử khôi phục. Không ghi đè tệp chỉ để lệnh stash chạy thành công.

Với tệp ignored, đặc biệt là file cấu hình máy cá nhân, dữ liệu build hoặc secret, hãy xác nhận chúng thực sự cần được chuyển sang nhánh mới trước khi áp dụng.

## Ví dụ thực tế: phục hồi công việc đang dở

Giả sử bạn đang làm tính năng tìm kiếm, có thay đổi trong SearchService và một tệp kiểm thử mới. Cần chuyển sang main để xử lý lỗi khẩn cấp.

~~~bash
# Cất thay đổi đang làm, gồm cả tệp chưa được theo dõi
git stash push -u -m "WIP search filter"

# Chuyển sang nhánh khác và xử lý công việc khẩn cấp
git switch main

# Sau khi hoàn tất, quay lại nhánh tính năng
git switch feature/search

# Xem stash và nội dung trước khi áp dụng
git stash list
git stash show -p 'stash@{0}'

# Thử phục hồi mà vẫn giữ stash
git stash apply 'stash@{0}'

# Nếu conflict, kiểm tra các tệp chưa được giải quyết
git status
git diff --name-only --diff-filter=U
git ls-files -u

# Chỉnh sửa tệp, sau đó stage và kiểm tra
git add -- src/SearchService.java src/test/java/SearchServiceTest.java
git diff --cached
git diff --cached --check

# Chạy test phù hợp, sau đó tạo commit nếu thay đổi đã hoàn chỉnh
git commit -m "Add search filter"

# Chỉ xóa stash sau khi xác nhận công việc đã được phục hồi đầy đủ
git stash list
git stash drop 'stash@{0}'
~~~

Nếu biết trước feature/search đã khác xa nền ban đầu, hãy dùng stash branch ngay từ đầu để tránh áp dụng stash lên nhánh có ngữ cảnh không phù hợp. Nếu đã chạy apply và gặp conflict, hãy giải quyết hoặc khôi phục trạng thái trước lần apply một cách an toàn trước; không chuyển nhánh khi index còn unmerged. Khi kho đã sẵn sàng, tạo nhánh từ commit gốc của stash:

~~~bash
git stash branch feature/resume-search 'stash@{0}'
~~~

Sau khi tạo nhánh, kiểm tra trạng thái, chạy test và tiếp tục công việc trên nhánh đó.

## Những lỗi thường gặp

| Tình huống | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Apply báo conflict | Nhánh hiện tại đã sửa cùng vùng với stash | Giải quyết từng tệp, stage và kiểm tra hành vi |
| Pop báo conflict | Stash không thể áp dụng sạch | Giải quyết conflict; stash entry vẫn còn |
| Không thấy tệp mới sau khi apply | Tệp chưa được theo dõi không được lưu vào stash ban đầu | Kiểm tra stash có được tạo bằng -u hoặc -a hay không |
| Apply --index không khôi phục đúng staging | Index hiện tại không thể nhận trạng thái cũ | Giải quyết conflict rồi stage lại thủ công |
| Stash branch không tạo được nhánh | Tên nhánh đã tồn tại hoặc ref stash không hợp lệ | Kiểm tra tên nhánh và git stash list |
| Stash vẫn còn sau pop | Pop gặp conflict nên không drop entry | Xác minh nội dung rồi mới drop thủ công |
| Mất thay đổi sau khi drop | Xóa nhầm stash hoặc chưa xác nhận phục hồi | Xem stash list và nội dung entry trước khi drop |
| Không thể khôi phục untracked file | Working tree đã có tệp cùng đường dẫn | Kiểm tra và xử lý xung đột đường dẫn trước khi phục hồi |

## Checklist trước khi kết thúc thao tác stash

- [ ] Đã xác định đúng stash entry và đọc thông điệp.
- [ ] Đã xem patch để biết chính xác nội dung được cất.
- [ ] Đã kiểm tra nhánh hiện tại và trạng thái working tree.
- [ ] Đã xác định các tệp unmerged nếu có conflict.
- [ ] Đã kết hợp đúng thay đổi từ nhánh hiện tại và stash.
- [ ] Đã tìm marker còn sót trong các tệp đã sửa.
- [ ] Đã stage đúng tệp và đọc staged diff.
- [ ] Đã chạy kiểm tra phù hợp với thay đổi.
- [ ] Đã xác nhận stash còn hay đã được xóa.
- [ ] Chỉ drop stash khi chắc chắn nội dung đã được phục hồi đầy đủ.

## Ghi nhớ

Khi apply hoặc pop stash gặp conflict, hãy xem git status, danh sách unmerged path và patch của stash để hiểu hai phía trước khi chỉnh sửa. Sau đó stage kết quả, kiểm tra diff và chạy test như với thay đổi thông thường. Apply luôn giữ stash; pop chỉ xóa stash khi áp dụng thành công, nên entry vẫn còn nếu conflict. Khi nhánh hiện tại đã khác xa nền ban đầu, git stash branch có thể tạo nhánh từ commit gốc của stash để phục hồi công việc trong ngữ cảnh phù hợp hơn. Luôn kiểm tra stash list và xác nhận nội dung đã được khôi phục trước khi drop entry.

