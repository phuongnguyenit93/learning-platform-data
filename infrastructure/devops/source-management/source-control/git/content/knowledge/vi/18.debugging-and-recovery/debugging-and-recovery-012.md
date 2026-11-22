# Xác minh nội dung, lịch sử và kết quả kiểm thử sau khi phục hồi

## Vì sao phải xác minh sau khi phục hồi?

Phục hồi trong Git là đưa mã nguồn hoặc lịch sử về một trạng thái mong muốn sau khi có thao tác sai, mất commit, ghi đè tệp, merge lỗi hoặc áp dụng nhầm thay đổi. Các thao tác như restore, reset, revert, cherry-pick, stash apply, merge --abort và rebase --abort có cách tác động khác nhau lên working tree, staging area, commit và tham chiếu nhánh.

Một lệnh kết thúc với mã thoát 0 chỉ cho biết Git đã thực hiện thao tác theo yêu cầu. Điều đó chưa chứng minh:

- Đã phục hồi đúng tệp và đúng phiên bản cần lấy lại.
- Không làm mất thay đổi hợp lệ được tạo sau mốc phục hồi.
- Nhánh hiện tại trỏ tới commit mong muốn.
- Lịch sử commit còn giữ đúng quan hệ cha-con và các mốc cần thiết.
- Không còn thao tác merge, rebase, cherry-pick hoặc revert dang dở.
- Ứng dụng vẫn biên dịch, kiểm thử và đáp ứng đúng hành vi nghiệp vụ.

Ví dụ, git reset --hard có thể đưa working tree về đúng commit được chỉ định và làm git status báo sạch. Tuy nhiên, nếu chọn nhầm commit cũ, kho vẫn sạch nhưng nhánh đã bị đưa về sai trạng thái. Tương tự, git revert có thể tạo commit hoàn tác thành công nhưng phần logic còn lại vẫn có thể phụ thuộc vào chức năng vừa bị loại bỏ.

Vì vậy, xác minh sau phục hồi cần kiểm tra ba lớp:

1. **Nội dung:** tệp, staging area và working tree đang chứa gì?
2. **Lịch sử:** HEAD, nhánh và commit mới có đúng như mục tiêu không?
3. **Hành vi:** build, test và các luồng sử dụng liên quan có hoạt động đúng không?

## Bắt đầu bằng cách ghi nhận trạng thái kho

Trước khi thực hiện thêm thao tác, xem trạng thái hiện tại:

~~~bash
git status
git status --short
git branch --show-current
git rev-parse --show-toplevel
git rev-parse HEAD
~~~

Các lệnh này cho biết:

- Bạn đang ở repository nào.
- Nhánh hiện tại là nhánh nào.
- HEAD đang trỏ tới commit nào.
- Working tree và staging area có thay đổi hay không.
- Git có đang ở giữa một thao tác nhiều bước hay không.

Nếu cần ghi lại commit hiện tại để đối chiếu, lưu mã commit từ git rev-parse HEAD vào ghi chú công việc hoặc terminal session. Không ghi đè file trong repository chỉ để lưu thông tin kiểm tra.

### Đọc đúng git status --short

Kết quả dạng rút gọn sử dụng hai ký tự để mô tả trạng thái:

~~~text
 M src/ReportService.java
M  src/ReportRepository.java
MM src/ReportController.java
A  src/ReportFilter.java
D  src/LegacyReport.java
?? notes/recovery-check.txt
~~~

Ký tự thứ nhất mô tả trạng thái trong staging area; ký tự thứ hai mô tả thay đổi trong working tree so với index.

| Ký hiệu | Ý nghĩa thường gặp |
|---|---|
| ␠M | Tệp đã theo dõi có thay đổi chưa stage |
| M␠ | Tệp đã stage thay đổi |
| MM | Tệp có thay đổi đã stage và còn thay đổi mới chưa stage |
| A␠ | Tệp mới đã được stage |
| D␠ | Tệp đã được stage để xóa |
| ?? | Tệp chưa được Git theo dõi |

Tên tệp có thể được hiển thị kèm thông tin rename hoặc copy tùy cấu hình và dạng diff. Khi cần xác định đầy đủ, dùng git status thay vì chỉ dựa vào một ký hiệu.

Một working tree sạch thường không có dòng nào trong git status --short. Tuy nhiên, sạch không đồng nghĩa đúng: vẫn cần xác nhận HEAD đang ở commit mong muốn và nội dung của commit đó phù hợp với mục tiêu phục hồi.

## Xác minh nội dung trong working tree và staging area

Git có ba khu vực cần phân biệt khi kiểm tra nội dung:

- **HEAD:** snapshot của commit hiện tại.
- **Staging area (index):** nội dung sẽ được ghi vào commit tiếp theo.
- **Working tree:** các tệp đang có trên đĩa sau những chỉnh sửa cục bộ.

Các lệnh diff giúp kiểm tra sự khác nhau giữa những khu vực này.

~~~bash
# Thay đổi trong working tree chưa stage
git diff

# Thay đổi đã stage so với HEAD
git diff --cached

# Tổng thay đổi của các tệp được theo dõi so với HEAD
git diff HEAD
~~~

Nếu một tệp vừa được stage vừa tiếp tục chỉnh sửa, cả git diff và git diff --cached đều có thể có nội dung. Chỉ xem một lệnh sẽ không đủ để hiểu toàn bộ trạng thái.

### Kiểm tra danh sách tệp thay đổi

~~~bash
git diff --name-status
git diff --cached --name-status
git diff HEAD --name-status
~~~

Các lệnh này giúp xác định tệp nào được sửa, thêm, xóa hoặc đổi tên trong từng phạm vi so sánh.

Nếu muốn xem thống kê:

~~~bash
git diff --stat
git diff --cached --stat
git diff HEAD --stat
~~~

Đối chiếu danh sách với phạm vi phục hồi dự kiến. Nếu chỉ muốn khôi phục một tệp nhưng thấy nhiều tệp không liên quan thay đổi, hãy tìm nguyên nhân trước khi tiếp tục.

### So sánh một tệp với phiên bản mong muốn

Giả sử cần xác nhận tệp ReportService.java đã được phục hồi đúng phiên bản từ commit 4a5b6c7.

Xem nội dung tệp trong commit:

~~~bash
git show 4a5b6c7:src/ReportService.java
~~~

So sánh working tree hiện tại với phiên bản trong commit đó:

~~~bash
git diff 4a5b6c7 -- src/ReportService.java
~~~

Nếu lệnh không hiển thị khác biệt, nội dung được Git theo dõi của tệp trong working tree trùng với snapshot của commit đã chỉ định. Nếu có khác biệt, đọc diff để xác định đó là thay đổi dự kiến hay dấu hiệu phục hồi chưa đúng.

Lưu ý: git show <commit>:<path> đọc nội dung được lưu trong commit. Nó không chứng minh tệp hiện tại đã được ghi đúng nếu bạn chưa so sánh với working tree.

Với tệp đã stage, có thể kiểm tra phiên bản index:

~~~bash
git show :src/ReportService.java
~~~

Cú pháp stage không có số sau dấu hai chấm đọc phiên bản trong index. Nếu tệp đang unmerged, cần xem stage 1, 2 và 3 thay vì dùng cú pháp này.

### Kiểm tra tệp chưa được theo dõi và tệp bị ignore

git diff thông thường không hiển thị nội dung của tệp chưa được theo dõi. Vì vậy, nếu thao tác phục hồi liên quan tới tệp mới, hãy kiểm tra riêng:

~~~bash
git status --short
git ls-files --others --exclude-standard
~~~

Lệnh thứ hai liệt kê các tệp chưa được theo dõi và không bị ignore.

Để xem tệp bị ignore:

~~~bash
git status --short --ignored
~~~

Đừng nhầm tệp ignored với tệp đã bị xóa hoặc chưa được phục hồi. Nếu tệp quan trọng bị ignore, hãy xác nhận quy tắc ignore và đường dẫn của nó.

### Kiểm tra đường dẫn còn unmerged

Nếu thao tác phục hồi phát sinh conflict, trước tiên xác định các tệp chưa được giải quyết:

~~~bash
git diff --name-only --diff-filter=U
git ls-files -u
~~~

Khi còn entry unmerged, chưa thể coi thao tác phục hồi đã hoàn tất. Cần chỉnh sửa từng tệp, stage kết quả, đọc lại diff và tiếp tục hoặc hủy đúng thao tác đang diễn ra.

## Xác minh lịch sử và tham chiếu nhánh

Nội dung tệp đúng chưa đủ nếu nhánh đang trỏ tới sai commit hoặc lịch sử bị thay đổi ngoài dự kiến.

Xem commit hiện tại:

~~~bash
git log -1 --oneline --decorate
git show --no-patch --pretty=fuller HEAD
git rev-parse HEAD
~~~

Xem đồ thị lịch sử gần đây:

~~~bash
git log --oneline --graph --decorate -n 20
~~~

Nếu cần xem cả nhánh cục bộ và remote-tracking branch:

~~~bash
git branch -avv
~~~

Hãy xác nhận:

- Tên nhánh hiện tại đúng với công việc cần phục hồi.
- HEAD trỏ tới commit mong muốn.
- Các commit cần giữ vẫn có thể truy cập.
- Commit mới (nếu có) có nội dung và parent phù hợp.
- Nhánh không bị di chuyển ngoài ý định.
- Remote-tracking branch không bị hiểu nhầm là trạng thái đã cập nhật mới nhất nếu chưa fetch.

Để xem danh sách parent của một commit:

~~~bash
git rev-list --parents -n 1 HEAD
~~~

Một commit thường có một parent; merge commit có từ hai parent trở lên. Khi phục hồi lịch sử liên quan đến merge, cần kiểm tra đúng số lượng và thứ tự parent.

### So sánh trước và sau phục hồi

Nếu biết commit trước thao tác và commit sau thao tác, có thể so sánh snapshot:

~~~bash
git diff <before-commit> <after-commit>
git diff --stat <before-commit> <after-commit>
~~~

Lệnh này so sánh nội dung hai snapshot. Nó không tự mô tả toàn bộ chuỗi commit giữa chúng.

Để xem những commit có trong nhánh sau nhưng không có trong nhánh trước:

~~~bash
git log --oneline <before-commit>..<after-commit>
~~~

Để xem các commit chỉ có ở phía trước:

~~~bash
git log --oneline <after-commit>..<before-commit>
~~~

Hai dấu chấm ở đây xác định tập commit có thể truy cập từ đầu bên trái nhưng không có trong đầu bên phải. Không nhầm kết quả này với git diff A..B, vốn là cách viết so sánh hai cây nội dung.

### Xác nhận một commit còn nằm trong lịch sử nhánh

Nếu cần kiểm tra commit C có phải tổ tiên của HEAD hay không:

~~~bash
git merge-base --is-ancestor C HEAD
~~~

Mã thoát 0 nghĩa là C là tổ tiên của HEAD; mã thoát 1 nghĩa là không phải. Mã thoát khác có thể cho biết lỗi tham số hoặc repository, nên cần đọc thông báo lỗi.

Có thể xem những nhánh chứa commit:

~~~bash
git branch --contains C
git branch -r --contains C
~~~

Các lệnh này hữu ích khi khôi phục commit bị mất hoặc kiểm tra commit đã được tích hợp vào nhánh nào.

## Dùng reflog để xác minh và truy tìm trạng thái trước đó

Reflog ghi lại những lần các tham chiếu cục bộ được cập nhật, ví dụ HEAD chuyển nhánh, commit, reset hoặc rebase. Khi phục hồi sau thao tác nhầm, reflog thường giúp tìm commit mà nhánh từng trỏ tới.

Xem reflog của HEAD:

~~~bash
git reflog --date=iso
~~~

Giới hạn số dòng gần đây:

~~~bash
git reflog -n 20 --date=iso
~~~

Ví dụ:

~~~text
a1b2c3d HEAD@{0}: reset: moving to HEAD~2
d4e5f6a HEAD@{1}: commit: Add report validation
1122334 HEAD@{2}: checkout: moving from feature/report to main
~~~

Trong ví dụ, HEAD@{1} là trạng thái trước lần reset được ghi ở HEAD@{0}. Có thể xem commit đó:

~~~bash
git show --stat --oneline HEAD@{1}
~~~

Reflog là nhật ký cục bộ, không được push lên remote như commit. Các entry có thể hết hạn theo cấu hình và thời gian; thao tác garbage collection có thể làm object không còn được giữ lại. Vì vậy, khi tìm thấy commit cần giữ, hãy tạo một nhánh hoặc tag phục hồi phù hợp sau khi xác nhận.

Ví dụ tạo nhánh tham chiếu tới commit cần phục hồi:

~~~bash
git branch recovery/report-before-reset d4e5f6a
~~~

Lệnh trên tạo một nhánh mới trỏ tới commit, không di chuyển nhánh hiện tại. Sau đó có thể kiểm tra nhánh phục hồi và so sánh nội dung trước khi quyết định merge, cherry-pick hoặc chuyển nhánh.

Không coi HEAD@{1} luôn là commit đúng. Reflog thay đổi theo từng thao tác mới; hãy đọc thông điệp, thời gian và nội dung commit trước khi sử dụng.

## Xác minh theo từng loại thao tác phục hồi

Mỗi lệnh phục hồi có tác động khác nhau. Cần chọn phép kiểm tra phù hợp với thao tác đã dùng.

### Sau git restore

git restore có thể phục hồi nội dung tệp trong working tree hoặc staging area tùy tùy chọn. Ví dụ:

~~~bash
git restore --source=HEAD --worktree -- src/ReportService.java
~~~

Lệnh trên chỉ khôi phục working tree; nếu index đang có thay đổi đã stage, chúng vẫn được giữ. Nếu mục tiêu là khôi phục cả index lẫn working tree về HEAD, dùng:

~~~bash
git restore --source=HEAD --staged --worktree -- src/ReportService.java
~~~

Kiểm tra lại:

~~~bash
git status --short
git diff HEAD -- src/ReportService.java
git diff --cached -- src/ReportService.java
git show HEAD:src/ReportService.java
~~~

Lệnh git diff HEAD so sánh tổng nội dung tracked trong working tree với snapshot của HEAD; git diff --cached cho biết riêng phần khác biệt đã stage. Nếu mục tiêu là đưa cả index và working tree của tệp về đúng snapshot HEAD, hai diff tương ứng sẽ không còn khác biệt.

Không chỉ dựa vào trạng thái sạch toàn kho nếu lệnh chỉ tác động một đường dẫn. Hãy kiểm tra đúng đường dẫn được giao.

### Sau git reset

reset di chuyển HEAD và có thể thay đổi index hoặc working tree tùy tùy chọn --soft, --mixed hoặc --hard.

Sau reset, kiểm tra:

~~~bash
git rev-parse HEAD
git status
git log --oneline --decorate -n 12
git reflog -n 12
~~~

Đối chiếu HEAD với commit đích. Nếu dùng --soft, các thay đổi của commit bị lùi có thể còn trong staging area. Nếu dùng --mixed, thay đổi thường nằm trong working tree chưa stage. Nếu dùng --hard, index và tracked working tree được đưa về commit đích, nên các thay đổi tracked cục bộ có thể đã bị loại bỏ.

Một kho sạch sau reset --hard không chứng minh đã chọn đúng commit. Luôn xác minh hash, nhánh và nội dung.

### Sau git revert

revert tạo commit mới đảo ngược một commit cũ. Kiểm tra commit mới và nội dung đảo ngược:

~~~bash
git log -1 --oneline
git show --stat --oneline HEAD
git diff HEAD^ HEAD
~~~

Nếu revert một merge commit, commit revert mới vẫn thường là commit một parent. Merge gốc vẫn nằm trong lịch sử; xác minh cả quan hệ tổ tiên và hệ quả đối với lần merge sau.

Chạy test cho cả hành vi được loại bỏ và những hành vi phụ thuộc vào nó. Một patch đảo ngược đúng về mặt văn bản vẫn có thể làm hỏng luồng nghiệp vụ.

### Sau git cherry-pick

cherry-pick tạo commit mới trên nhánh hiện tại với thay đổi lấy từ commit được chọn. Kiểm tra:

~~~bash
git log -1 --oneline --decorate
git show --stat --oneline HEAD
git diff HEAD^ HEAD
~~~

So sánh commit mới với commit nguồn:

~~~bash
git show --stat <source-commit>
git show --stat HEAD
~~~

Hash của commit mới thường khác commit nguồn vì parent, thời gian và metadata khác. Đừng yêu cầu hai hash phải giống nhau; hãy xác minh nội dung và thông điệp thay đổi.

Nếu cherry-pick nhiều commit hoặc gặp conflict, kiểm tra thứ tự commit và trạng thái sau từng lần --continue.

### Sau git stash apply hoặc pop

Kiểm tra thay đổi được phục hồi:

~~~bash
git status
git diff
git diff --cached
git stash list
~~~

apply giữ stash entry. pop chỉ xóa entry khi áp dụng thành công; nếu conflict, entry vẫn còn. Đừng drop stash trước khi đã xác nhận đầy đủ nội dung, kiểm thử và tạo commit hoặc một hình thức lưu trữ an toàn khác.

### Sau git merge --abort hoặc git rebase --abort

Hai lệnh abort hủy thao tác đang dang dở và cố gắng đưa kho về trạng thái trước khi bắt đầu thao tác tương ứng.

Kiểm tra:

~~~bash
git status
git branch --show-current
git rev-parse HEAD
git log --oneline --graph --decorate -n 15
~~~

Nếu có thay đổi trước khi bắt đầu merge hoặc rebase, xác nhận chúng còn được giữ theo trạng thái ban đầu. Nếu đã sử dụng autostash, kiểm tra stash list và các thay đổi được áp dụng lại.

Đừng giả định abort đã khôi phục mọi tệp theo đúng mong đợi nếu working tree ban đầu đã chứa thay đổi cục bộ phức tạp. Đọc diff và so sánh với mốc trước thao tác nếu đã ghi nhận.

## Kiểm tra kết quả kiểm thử sau phục hồi

Git xác minh trạng thái nội dung và lịch sử. Compiler, linter và test xác minh những phần khác của hệ thống. Cần chọn kiểm tra theo rủi ro của thay đổi được phục hồi.

### Bắt đầu bằng kiểm tra gần với phần thay đổi

Ví dụ:

- Chạy unit test cho lớp hoặc package vừa được phục hồi.
- Biên dịch module có chứa các tệp bị ảnh hưởng.
- Chạy linter hoặc kiểm tra kiểu dữ liệu.
- Kiểm tra cú pháp và khả năng nạp cấu hình nếu đã phục hồi YAML, JSON, TOML hoặc file cấu hình khác.
- Chạy test tích hợp nếu thay đổi ảnh hưởng tới API, database, message queue hoặc giao tiếp giữa dịch vụ.

Dùng đúng lệnh build/test do dự án quy định. Không giả định một lệnh Gradle, Maven, npm hay công cụ khác áp dụng cho mọi repository.

### Mở rộng kiểm thử theo mức độ ảnh hưởng

Sau khi kiểm tra hẹp đạt, mở rộng theo phạm vi:

| Mức kiểm tra | Mục tiêu |
|---|---|
| Unit test | Xác nhận logic của lớp hoặc hàm bị ảnh hưởng |
| Integration test | Xác nhận tương tác giữa các thành phần |
| Contract/API test | Xác nhận request, response, schema và mã lỗi |
| Build toàn module | Phát hiện lỗi biên dịch và dependency |
| End-to-end hoặc acceptance test | Xác nhận luồng sử dụng thực tế |
| CI | Kiểm tra trong môi trường và cấu hình mà nhóm sử dụng |

Không cần chạy toàn bộ suite nhiều lần nếu đã có kết quả phù hợp và không có thay đổi mới. Nhưng nếu việc phục hồi làm thay đổi dependency, cấu hình, schema hoặc nhiều module, hãy mở rộng phạm vi kiểm tra tương ứng.

### Kiểm tra cả hành vi được phục hồi và hành vi không được phép bị ảnh hưởng

Ví dụ, sau khi phục hồi một commit sửa quyền truy cập báo cáo, cần kiểm tra:

| Trường hợp | Kết quả mong đợi |
|---|---|
| Người dùng có quyền | Truy cập hoặc xuất báo cáo thành công |
| Người dùng không có quyền | Bị từ chối và không nhận dữ liệu |
| Token hết hạn | Trả lỗi xác thực theo hợp đồng |
| Bộ lọc không hợp lệ | Trả lỗi xác thực phù hợp |
| Báo cáo không có dữ liệu | Trả kết quả rỗng theo quy định |

Nếu phục hồi một phiên bản cũ của cấu hình hoặc schema, hãy kiểm tra khả năng tương thích với dữ liệu và dịch vụ đang chạy. Việc build thành công không đảm bảo migration có thể chạy an toàn hoặc dữ liệu hiện có được đọc đúng.

### Đọc kết quả test một cách trung thực

Khi ghi nhận kết quả, phân biệt rõ:

- Test đã chạy và PASS.
- Test đã chạy nhưng FAIL.
- Test bị bỏ qua hoặc không thể chạy do môi trường.
- Test chưa chạy.

Nếu test thất bại, đọc log để xác định nguyên nhân. Không đánh dấu PASS chỉ vì lệnh build thành công nếu bộ test nghiệp vụ chưa chạy.

Nếu có thể, so sánh với kết quả trên commit nền hoặc một môi trường chuẩn để xác định lỗi có phải do thay đổi phục hồi hay là lỗi đã tồn tại. Ghi lại lệnh thực tế, mã thoát và phần test bị ảnh hưởng.

## Kiểm tra secret, dữ liệu và cấu hình sau phục hồi

Một thao tác phục hồi có thể đưa nội dung cũ trở lại, bao gồm cả cấu hình lỗi thời hoặc thông tin nhạy cảm từng bị xóa.

Sau khi phục hồi, kiểm tra:

- Token, mật khẩu, private key hoặc credential có xuất hiện trong tệp được khôi phục không.
- File cấu hình có trỏ tới endpoint, database hoặc môi trường đúng không.
- Giá trị mặc định có làm thay đổi hành vi bảo mật không.
- Dependency và lockfile có tương thích với manifest không.
- Migration hoặc schema có phù hợp với dữ liệu hiện tại không.
- File generated, cache và file cục bộ có bị đưa vào commit ngoài ý muốn không.

Không đưa bí mật thật vào log kiểm thử, ảnh chụp màn hình hoặc báo cáo. Nếu phát hiện secret đã được commit hoặc chia sẻ, xử lý theo quy trình ứng phó lộ thông tin của tổ chức; xóa file ở commit mới không làm secret trong lịch sử cũ biến mất.

## Khi Git báo thành công nhưng kết quả vẫn sai

Có một số nguyên nhân phổ biến:

| Hiện tượng | Nguyên nhân có thể | Cách xác minh |
|---|---|---|
| Working tree sạch nhưng ứng dụng sai phiên bản | HEAD trỏ tới commit không mong muốn | Xem git rev-parse HEAD và git log |
| Tệp đã phục hồi nhưng vẫn khác phiên bản mục tiêu | Chọn sai source commit hoặc path | So sánh git diff <expected> -- <path> |
| Commit cũ không xuất hiện trong nhánh | Chỉ phục hồi nội dung, chưa tạo ref hoặc commit cần thiết | Kiểm tra reflog và git branch --contains |
| Revert thành công nhưng tính năng phụ thuộc bị lỗi | Các commit sau dựa vào nội dung đã bị đảo ngược | Xem lịch sử và chạy test tích hợp |
| Test cục bộ đạt nhưng CI thất bại | Khác môi trường, biến cấu hình hoặc dependency cache | Đọc log CI và so sánh cấu hình |
| Stash vẫn còn sau pop | Pop đã gặp conflict | Kiểm tra git stash list và nội dung phục hồi |
| Tệp untracked không xuất hiện trong diff | git diff không hiển thị tệp chưa được theo dõi | Kiểm tra git status --short và git ls-files |
| Không tìm thấy commit trong log | Commit không còn reachable từ nhánh hiện tại | Kiểm tra reflog và các ref khác |

Không vội chạy thêm reset, clean hoặc force push khi chưa hiểu trạng thái. Các thao tác đó có thể làm giảm khả năng phục hồi thêm.

## Xử lý khi không tìm thấy commit cần phục hồi

Nếu commit không xuất hiện trong git log của nhánh hiện tại, hãy kiểm tra reflog trước:

~~~bash
git reflog --all --date=iso
~~~

Nếu tìm được mã commit, xác minh object còn tồn tại:

~~~bash
git cat-file -e 'd4e5f6a^{commit}'
git show --stat --oneline d4e5f6a
~~~

Nếu xác nhận đúng commit, tạo một nhánh phục hồi để giữ tham chiếu:

~~~bash
git branch recovery/restore-lost-work d4e5f6a
~~~

Sau đó kiểm tra nội dung, lịch sử và test trên nhánh phục hồi trước khi tích hợp.

Nếu reflog không còn entry phù hợp nhưng nghi commit object vẫn tồn tại, có thể kiểm tra object không còn reachable bằng:

~~~bash
git fsck --full --no-reflogs --unreachable
~~~

Lệnh này có thể in nhiều object không còn được tham chiếu. Cần xem từng object và dùng git show hoặc git cat-file để xác định loại, nội dung và quan hệ của chúng. Không tự động đưa mọi object tìm thấy vào nhánh.

Việc tìm thấy object không đảm bảo có thể khôi phục toàn bộ working tree chưa commit. Những thay đổi chưa từng được commit hoặc lưu trong stash có thể không có object phù hợp để phục hồi. Hãy phân biệt mất commit với mất nội dung chưa commit.

## Ghi nhận bằng chứng phục hồi

Sau khi nội dung, lịch sử và test đã được xác nhận, lưu lại thông tin đủ để người khác có thể đánh giá kết quả.

Một báo cáo phục hồi có thể gồm:

| Thông tin | Nội dung cần ghi |
|---|---|
| Sự cố | Thao tác sai hoặc thay đổi cần phục hồi |
| Phương pháp | restore, reset, revert, cherry-pick, stash hoặc reflog |
| Mốc nguồn | Commit hoặc stash đã dùng làm nguồn |
| Trạng thái sau phục hồi | Nhánh, HEAD và trạng thái working tree |
| Tệp ảnh hưởng | Danh sách tệp được phục hồi hoặc thay đổi |
| Lịch sử | Commit mới, parent và ref liên quan |
| Kiểm thử | Lệnh đã chạy và PASS/FAIL/BLOCKED |
| Việc còn lại | Kiểm tra chưa chạy hoặc phụ thuộc cần theo dõi |

Có thể dùng các lệnh sau để thu thập thông tin:

~~~bash
git status --short
git branch --show-current
git rev-parse HEAD
git log -1 --oneline --decorate
git show --stat --oneline HEAD
git diff --check
git diff --cached --check
~~~

Nếu cần chia sẻ báo cáo, không đưa nội dung bí mật, token, thông tin xác thực hoặc dữ liệu cá nhân vào đó.

## Quy trình xác minh mẫu sau khi phục hồi

Giả sử bạn vừa khôi phục commit cần thiết sau một lần reset nhầm bằng cách tạo nhánh từ reflog. Có thể kiểm tra theo thứ tự:

~~~bash
# 1. Xác nhận repository, branch và HEAD
git status
git branch --show-current
git rev-parse HEAD

# 2. Xác nhận commit phục hồi và nội dung của nó
git show --stat --oneline HEAD
git show --format=fuller --no-patch HEAD

# 3. Xem đồ thị lịch sử và các tham chiếu liên quan
git log --oneline --graph --decorate -n 20
git branch -avv

# 4. Kiểm tra thay đổi trong index và working tree
git diff
git diff --cached
git status --short

# 5. Kiểm tra whitespace và đường dẫn unmerged
git diff --check
git diff --cached --check
git diff --name-only --diff-filter=U
git ls-files -u

# 6. Chạy unit test, build và các kiểm tra phù hợp với dự án
# Ghi lại lệnh thực tế và kết quả PASS/FAIL/BLOCKED

# 7. Kiểm tra trạng thái cuối
git status
git log -1 --oneline --decorate
~~~

Nếu thao tác phục hồi tạo commit mới, xác minh nội dung của commit mới so với parent. Nếu thao tác chỉ phục hồi working tree, xác minh các tệp với snapshot nguồn và quyết định có cần commit hay không theo quy trình của nhóm.

## Checklist hoàn tất phục hồi

- [ ] Đã xác định đúng repository, nhánh và commit đích.
- [ ] Đã kiểm tra working tree và staging area.
- [ ] Đã xác nhận nội dung từng tệp quan trọng so với phiên bản mong muốn.
- [ ] Đã kiểm tra untracked, ignored và tệp bị xóa nếu có liên quan.
- [ ] Không còn đường dẫn unmerged ngoài dự kiến.
- [ ] HEAD và lịch sử commit phản ánh đúng kết quả phục hồi.
- [ ] Các commit cần giữ vẫn có thể truy cập.
- [ ] Không đưa thay đổi ngoài phạm vi vào commit.
- [ ] Đã chạy test phù hợp và ghi nhận chính xác kết quả.
- [ ] Đã kiểm tra cấu hình, dependency, schema và secret liên quan.
- [ ] Đã xác nhận stash hoặc ref phục hồi còn được giữ nếu vẫn cần.
- [ ] Đã ghi lại bằng chứng và các việc còn lại.

## Ghi nhớ

Sau một thao tác phục hồi, hãy xác minh nội dung trong working tree và index, xác nhận HEAD cùng lịch sử nhánh, rồi chạy lại kiểm thử theo phạm vi bị ảnh hưởng. git status sạch chỉ phản ánh trạng thái tệp được Git theo dõi so với HEAD; nó không chứng minh commit đích đúng hoặc ứng dụng hoạt động đúng. Dùng diff để kiểm tra nội dung, log và reflog để kiểm tra lịch sử, test để xác nhận hành vi, và lưu lại bằng chứng trước khi chia sẻ kết quả. Mục tiêu là phục hồi đúng trạng thái mong muốn mà vẫn giữ được các thay đổi và mốc lịch sử cần thiết.

