# Kiểm tra phần còn sót và xác nhận hành vi sau khi xử lý xung đột

## Vì sao phải kiểm tra sau khi giải quyết xung đột?

Khi Git phát hiện hai nhánh cùng thay đổi một vùng nội dung theo cách không thể tự động kết hợp, Git yêu cầu người phát triển giải quyết xung đột (conflict). Việc chỉnh sửa tệp để chọn, kết hợp hoặc viết lại nội dung chỉ là một phần của công việc. Sau khi chỉnh sửa, cần xác nhận rằng:

- Tất cả đường dẫn bị xung đột đã được xử lý.
- Không còn dấu phân cách xung đột vô tình nằm trong mã nguồn hoặc cấu hình.
- Kết quả cuối cùng giữ đúng ý định của các thay đổi liên quan.
- Tệp đã được đưa vào staging area đúng cách.
- Ứng dụng vẫn biên dịch, kiểm thử và hoạt động đúng sau khi kết hợp thay đổi.
- Thao tác merge, rebase hoặc cherry-pick đã được hoàn tất theo đúng quy trình.

Một lần merge có thể không còn báo conflict nhưng vẫn tạo ra lỗi logic. Chẳng hạn, một nhánh bổ sung bước kiểm tra quyền truy cập, nhánh còn lại thêm chức năng xuất dữ liệu. Nếu khi xử lý xung đột chỉ giữ phần xuất dữ liệu và bỏ qua kiểm tra quyền, mã nguồn có thể biên dịch thành công nhưng làm lộ dữ liệu. Vì vậy, xác nhận sau conflict cần xem cả trạng thái Git lẫn hành vi của sản phẩm.

## Xác định trạng thái hiện tại của Git

Bắt đầu bằng cách xem trạng thái kho:

~~~bash
git status
git status --short
~~~

Lệnh git status cho biết Git đang ở giữa thao tác merge, rebase hay cherry-pick, những tệp nào còn xung đột, những tệp nào đã được giải quyết và thay đổi nào đang chờ commit.

Để chỉ liệt kê đường dẫn còn ở trạng thái unmerged:

~~~bash
git diff --name-only --diff-filter=U
~~~

Nếu lệnh không in ra đường dẫn nào, Git không còn ghi nhận tệp chưa được giải quyết ở index. Có thể kiểm tra thêm các entry chưa hợp nhất:

~~~bash
git ls-files -u
~~~

Khi còn xung đột, git ls-files -u có thể hiển thị nhiều entry cho cùng một đường dẫn. Với xung đột nội dung thông thường, các stage có ý nghĩa như sau:

| Stage | Nội dung |
|---|---|
| 1 | Phiên bản cơ sở chung (merge base), nếu có |
| 2 | Phiên bản phía hiện tại (ours) |
| 3 | Phiên bản phía được hợp nhất vào (theirs) |

Sau khi đã giải quyết và stage tệp, các entry unmerged tương ứng sẽ biến mất. Hai lệnh kiểm tra trên giúp xác nhận trạng thái của Git, nhưng chưa chứng minh nội dung đã đúng về nghiệp vụ.

### Hiểu đúng ours và theirs

Trong một lần merge thông thường, ours là nhánh hiện tại và theirs là nhánh đang được merge vào. Trong rebase, cách hiểu này thường đảo chiều so với trực giác: ours thường là nhánh nền mà commit đang được phát lại lên trên, còn theirs là thay đổi của commit đang được áp dụng. Đây là lý do các lựa chọn ours/theirs trong rebase dễ gây nhầm lẫn. Không chọn nội dung chỉ dựa trên tên hai phía. Hãy xem thông báo thao tác hiện tại, lịch sử commit và mục tiêu của thay đổi để hiểu phần nào cần được giữ.

Có thể xem các phiên bản đang được lưu trong index khi tệp còn unmerged:

~~~bash
git show :1:path/to/file
git show :2:path/to/file
git show :3:path/to/file
~~~

Một số loại xung đột như add/add, modify/delete hoặc xung đột rename có thể không có đủ cả ba stage. Nếu một lệnh git show không tìm thấy stage tương ứng, đó có thể là đặc điểm của loại xung đột hiện tại chứ không nhất thiết là kho bị hỏng.

## Kiểm tra dấu phân cách xung đột còn sót

### Nhận diện các marker

Khi Git chèn xung đột vào tệp văn bản, nội dung thường có dạng:

~~~text
<<<<<<< HEAD
Nội dung ở phía hiện tại
=======
Nội dung ở phía được hợp nhất vào
>>>>>>> feature/new-report
~~~

Nếu dùng kiểu hiển thị diff3 hoặc zdiff3, Git còn hiển thị phiên bản cơ sở với marker bắt đầu bằng |||||||:

~~~text
<<<<<<< HEAD
Nội dung ở phía hiện tại
||||||| 1a2b3c4
Nội dung tại merge base
=======
Nội dung ở phía được hợp nhất vào
>>>>>>> feature/new-report
~~~

Sau khi giải quyết, các marker <<<<<<<, =======, >>>>>>> và ||||||| của vùng xung đột phải được loại bỏ khỏi nội dung cuối cùng. Cần kiểm tra cả tệp mã nguồn, cấu hình, tài liệu và những tệp được tạo hoặc sửa trong quá trình giải quyết. Không phải mọi loại conflict đều chèn marker vào tệp: xung đột nhị phân, add/delete hoặc rename thường cần được nhận diện qua trạng thái Git và quyết định rõ phiên bản hay đường dẫn cuối cùng.

### Tìm marker trong các tệp vừa thay đổi

Nếu đã biết các tệp từng xung đột, tìm marker theo từng đường dẫn:

~~~bash
rg -n '^(<<<<<<<|=======|>>>>>>>|\|\|\|\|\|\|\|)' -- src/service.java config/application.yml
~~~

rg (ripgrep) in số dòng và nội dung khớp. Nếu không có kết quả và mã thoát là 1, không tìm thấy dòng nào khớp. Mã thoát lớn hơn 1 thường biểu thị lỗi khi chạy lệnh, chẳng hạn đường dẫn không tồn tại hoặc không thể đọc tệp; không nên coi lỗi đó là xác nhận sạch marker.

Có thể tìm trong toàn bộ mã nguồn được ripgrep quét:

~~~bash
rg -n '^(<<<<<<<|=======|>>>>>>>|\|\|\|\|\|\|\|)' .
~~~

Tuy nhiên, tìm toàn kho có thể phát hiện ví dụ minh họa, fixture kiểm thử hoặc tài liệu cố ý chứa chuỗi marker. Hãy tập trung vào các tệp bị xung đột và xem từng kết quả trước khi kết luận. Một dòng ======= trong tài liệu hoặc dữ liệu kiểm thử không tự động chứng minh conflict chưa được giải quyết.

Nếu dự án không cài ripgrep, có thể dùng tìm kiếm của IDE hoặc công cụ dòng lệnh tương đương. Điều quan trọng là tìm trong đúng các tệp đã xử lý, bao gồm cả tệp cấu hình và tệp không phải mã nguồn.

## Đọc lại diff cuối cùng

Sau khi sửa xong một tệp, hãy đọc lại toàn bộ phần thay đổi trong ngữ cảnh. Hai lệnh sau cho biết nội dung khác nhau giữa working tree, staging area và commit hiện tại:

~~~bash
# Thay đổi chưa stage
git diff

# Thay đổi đã stage
git diff --cached
~~~

Có thể giới hạn phạm vi vào một tệp:

~~~bash
git diff -- src/service.java
git diff --cached -- src/service.java
~~~

Khi một tệp đã được stage, nội dung được chuẩn bị cho commit nằm trong git diff --cached. Nếu tiếp tục sửa tệp sau khi stage, phần sửa mới xuất hiện trong git diff. Vì vậy, chỉ xem một trong hai diff có thể bỏ sót phần thay đổi còn lại.

Để xem thống kê và danh sách đường dẫn:

~~~bash
git diff --stat
git diff --cached --stat
git diff --name-status
git diff --cached --name-status
~~~

Khi xem diff, hãy tự hỏi:

- Có giữ đủ hành vi từ cả hai nhánh không?
- Có vô tình xóa điều kiện, kiểm tra quyền, xử lý lỗi hoặc log quan trọng không?
- Có giữ đúng chữ ký hàm, kiểu dữ liệu, tên trường, API và cấu trúc dữ liệu mà nơi gọi đang sử dụng không?
- Có thay đổi cấu hình môi trường, dependency, schema hoặc migration mà chưa cập nhật phần liên quan không?
- Các thay đổi không liên quan có bị đưa vào cùng phần giải quyết không?
- Có tệp bị xóa hoặc đổi tên ngoài dự kiến không?

Đừng chỉ nhìn những dòng được đánh dấu conflict. Git có thể tự động kết hợp các vùng khác nhau, nhưng một kết quả tự động vẫn có thể sai về mặt logic khi hai thay đổi phụ thuộc lẫn nhau.

## Kiểm tra khoảng trắng và định dạng diff

Lệnh git diff --check phát hiện một số lỗi khoảng trắng trong phần thay đổi chưa stage, ví dụ khoảng trắng thừa ở cuối dòng hoặc lỗi whitespace theo quy tắc Git:

~~~bash
git diff --check
~~~

Để kiểm tra phần đã stage:

~~~bash
git diff --cached --check
~~~

Nếu muốn kiểm tra tổng thể phần khác biệt giữa HEAD và working tree, có thể dùng:

~~~bash
git diff HEAD --check
~~~

Các lệnh này giúp phát hiện lỗi định dạng, không kiểm tra cú pháp hay logic của chương trình. Một diff sạch không thay thế compiler, linter hoặc test.

## Xác nhận nội dung đã được stage

Sau khi đã đọc lại nội dung và chắc chắn kết quả đúng, đưa từng tệp đã giải quyết vào staging area:

~~~bash
git add -- src/service.java config/application.yml
~~~

Nếu quyết định cuối cùng là xóa một tệp, dùng:

~~~bash
git rm -- path/to/obsolete-file
~~~

Với thay đổi rename, add/delete hoặc nhiều tệp liên quan, xem kỹ git status và git diff --cached để xác nhận Git đang ghi nhận đúng thao tác. Không dùng git add . một cách máy móc nếu working tree còn những thay đổi độc lập chưa được phép đưa vào commit.

Kiểm tra lại:

~~~bash
git status
git diff --name-only --diff-filter=U
git ls-files -u
git diff --cached
~~~

Kết quả mong đợi là không còn đường dẫn unmerged, các tệp giải quyết đã được stage và diff staged phản ánh đúng nội dung dự định. Nếu sửa tiếp sau bước này, cần đọc lại diff và stage phần cập nhật mới.

## Xác nhận hành vi của ứng dụng

### Bắt đầu bằng kiểm tra có phạm vi nhỏ

Chạy những kiểm tra gần với khu vực vừa xử lý trước. Ví dụ:

- Biên dịch module có chứa lớp vừa sửa.
- Chạy unit test của lớp hoặc package bị ảnh hưởng.
- Chạy linter, formatter hoặc kiểm tra kiểu dữ liệu của các tệp đã sửa.
- Kiểm tra cú pháp và khả năng nạp cấu hình nếu conflict nằm trong YAML, JSON, TOML hoặc tệp cấu hình khác.
- Chạy test tích hợp nếu hai thay đổi liên quan tới giao tiếp giữa nhiều thành phần.

Sau khi kiểm tra hẹp thành công, chạy bộ test rộng hơn theo quy trình của dự án. Nếu thay đổi ảnh hưởng tới API, cơ sở dữ liệu, phân quyền hoặc luồng nghiệp vụ quan trọng, cần kiểm tra các trường hợp sử dụng liên quan thay vì chỉ dựa vào kết quả biên dịch.

Không có một lệnh test chung cho mọi dự án. Hãy dùng lệnh build và test được dự án quy định, đồng thời ghi nhận rõ kiểm tra nào đã chạy, kiểm tra nào chưa chạy và lý do.

### Kiểm tra các trường hợp hành vi từ cả hai nhánh

Giả sử nhánh feature/export thêm chức năng xuất báo cáo, còn nhánh security/permission-check bổ sung kiểm tra quyền truy cập. Hai nhánh cùng sửa phương thức:

~~~java
public Report exportReport(User user, ReportFilter filter) {
    // conflict giữa kiểm tra quyền và tạo báo cáo
}
~~~

Một kết quả giải quyết hợp lý phải bảo toàn cả hai yêu cầu: xác thực người dùng có quyền trước khi xuất, sau đó tạo báo cáo theo bộ lọc. Ví dụ minh họa:

~~~java
public Report exportReport(User user, ReportFilter filter) {
    permissionService.requireCanExport(user);

    return reportService.createReport(filter);
}
~~~

Sau khi giải quyết, không chỉ kiểm tra phương thức có biên dịch. Cần xác nhận ít nhất các trường hợp:

| Trường hợp | Hành vi cần xác nhận |
|---|---|
| Người dùng có quyền | Báo cáo được tạo theo bộ lọc yêu cầu |
| Người dùng không có quyền | Yêu cầu bị từ chối và không tạo hoặc trả dữ liệu báo cáo |
| Bộ lọc không hợp lệ | Trả lỗi xác thực phù hợp, không tạo báo cáo sai |
| Dữ liệu không tồn tại | Hành vi không có dữ liệu đúng với hợp đồng của chức năng |

Đây là ví dụ về cách suy nghĩ khi kiểm tra: xác định yêu cầu do từng nhánh đưa vào, tìm những điểm phụ thuộc giữa chúng, rồi kiểm thử các trường hợp có thể bị ảnh hưởng bởi việc kết hợp. Không sao chép nguyên ví dụ vào sản phẩm nếu tên lớp hoặc nghiệp vụ thực tế khác.

### Kiểm tra cấu hình, dependency và dữ liệu

Conflict không chỉ xảy ra trong mã nguồn. Khi giải quyết các tệp sau, cần kiểm tra nội dung tương ứng:

- **Tệp cấu hình:** xác nhận khóa, kiểu dữ liệu, giá trị mặc định, profile và biến môi trường. Chú ý trường hợp một nhánh thêm khóa mới còn nhánh kia đổi tên hoặc xóa khóa cũ.
- **Dependency manifest và lockfile:** xác nhận phiên bản thư viện, ràng buộc tương thích và nội dung lockfile được sinh nhất quán với manifest.
- **Database migration:** kiểm tra thứ tự migration, tên đối tượng, khả năng chạy trên trạng thái dữ liệu hiện tại và việc hai nhánh có tạo thay đổi trùng nhau hay không.
- **API và schema:** kiểm tra request/response, tên trường, kiểu dữ liệu, mã lỗi và các nơi gọi.
- **Tài liệu và ví dụ:** cập nhật mô tả, cấu hình mẫu và hướng dẫn nếu hành vi thực tế đã thay đổi.

Với dữ liệu nhạy cảm, không đưa giá trị bí mật thật vào ví dụ kiểm thử hoặc log. Hãy dùng dữ liệu giả và cơ chế cấu hình an toàn của dự án.

## Hoàn tất đúng thao tác đang diễn ra

Sau khi mọi conflict đã được giải quyết, stage đúng các tệp, diff đã được đọc lại và các kiểm tra phù hợp đã đạt, hãy hoàn tất thao tác Git đang chờ.

### Nếu đang merge

Kiểm tra trạng thái:

~~~bash
git status
~~~

Nếu Git xác nhận mọi conflict đã được giải quyết và các thay đổi cần thiết đã stage, tiếp tục merge:

~~~bash
git merge --continue
~~~

Git có thể mở trình soạn thảo để xác nhận thông điệp merge. Sau khi hoàn tất, kiểm tra:

~~~bash
git status
git log -1 --oneline
~~~

Một số merge có thể được fast-forward và không tạo merge commit. Hãy dựa vào trạng thái và kết quả thực tế của thao tác thay vì mặc định rằng luôn phải có một merge commit.

### Nếu đang rebase

Sau khi giải quyết và stage các tệp của commit hiện tại:

~~~bash
git rebase --continue
~~~

Rebase có thể dừng lại ở commit kế tiếp nếu commit đó cũng xung đột. Lặp lại quy trình kiểm tra, giải quyết, stage và tiếp tục cho tới khi rebase hoàn tất. Sau đó kiểm tra lịch sử và trạng thái:

~~~bash
git status
git log --oneline --decorate -n 8
~~~

### Nếu đang cherry-pick

Sau khi giải quyết và stage các tệp:

~~~bash
git cherry-pick --continue
~~~

Nếu cherry-pick nhiều commit, Git có thể tiếp tục xử lý các commit còn lại. Kiểm tra git status để xác nhận thao tác đã kết thúc.

Không dùng lẫn các lệnh --continue. Hãy dùng lệnh tương ứng với thao tác mà git status cho biết đang diễn ra. Nếu chủ động muốn hủy thao tác, cần hiểu tác động của git merge --abort, git rebase --abort hoặc git cherry-pick --abort đối với các thay đổi hiện tại trước khi chạy.

## Quy trình mẫu từ lúc giải quyết tới lúc xác nhận

Ví dụ đang merge nhánh feature/report vào main:

~~~bash
# Xác định trạng thái và các tệp còn xung đột
git status
git diff --name-only --diff-filter=U

# Sau khi chỉnh sửa các tệp conflict, tìm marker còn sót
rg -n '^(<<<<<<<|=======|>>>>>>>|\|\|\|\|\|\|\|)' -- src/report.java config/application.yml

# Đọc lại cả phần chưa stage và phần đã stage
git diff
git diff --cached

# Kiểm tra whitespace
git diff --check
git diff --cached --check

# Stage các tệp đã giải quyết
git add -- src/report.java config/application.yml

# Xác nhận index không còn unmerged và xem diff chuẩn bị commit
git status
git ls-files -u
git diff --cached

# Chạy các kiểm tra phù hợp với dự án
# Ví dụ: chạy unit test hoặc build theo hướng dẫn của dự án

# Tiếp tục merge khi mọi kiểm tra cần thiết đã đạt
git merge --continue

# Xác nhận trạng thái sau merge
git status
git log -1 --oneline
~~~

Các lệnh tìm marker và kiểm tra diff là ví dụ cần điều chỉnh theo đường dẫn thực tế. Nếu lệnh tìm marker không có kết quả, hãy kiểm tra mã thoát và xác nhận công cụ đã đọc được các tệp. Nếu test thất bại, đọc thông báo lỗi và xác định lỗi có liên quan tới thay đổi vừa kết hợp hay môi trường kiểm thử.

## Đọc kết quả cuối cùng và lưu bằng chứng

Sau khi thao tác merge, rebase hoặc cherry-pick đã kết thúc, thực hiện kiểm tra cuối:

~~~bash
git status --short
git status
git log --oneline --decorate -n 8
~~~

Cần xác nhận:

1. Không còn trạng thái merge/rebase/cherry-pick đang diễn ra ngoài dự kiến.
2. Không còn đường dẫn unmerged.
3. Các tệp đã giải quyết có nội dung cuối cùng đúng và được ghi nhận trong commit dự kiến.
4. Các kiểm tra đã chọn đều có kết quả rõ ràng.
5. Không có thay đổi ngoài phạm vi bị đưa nhầm vào commit.

Nếu dự án yêu cầu review trước khi push, hãy xem lại commit và tạo pull request hoặc merge request theo quy trình của nhóm. Sau khi push, kiểm tra kết quả CI và phản hồi review nếu có. Một lần test thành công ở máy cá nhân không đảm bảo mọi môi trường CI hoặc production đều giống nhau.

Có thể ghi lại bằng chứng kiểm tra trong mô tả pull request hoặc báo cáo công việc: loại conflict, tệp đã xử lý, các hành vi được kiểm tra, lệnh test đã chạy và kết quả. Không cần ghi lại token, thông tin xác thực hay dữ liệu khách hàng trong báo cáo.

## Những lỗi thường gặp khi xác nhận sau conflict

| Sai sót | Hệ quả | Cách xử lý |
|---|---|---|
| Chỉ xóa marker rồi kết luận đã xong | Có thể bỏ mất một phần logic của nhánh | Đọc lại toàn bộ hàm hoặc cấu hình và đối chiếu yêu cầu của hai phía |
| Chỉ xem git diff | Bỏ sót nội dung đã stage | Xem cả git diff và git diff --cached |
| Thấy không còn marker nhưng chưa kiểm tra unmerged path | Có thể còn tệp chưa được xử lý hoặc xử lý sai loại conflict | Dùng git diff --name-only --diff-filter=U và git ls-files -u |
| Stage tất cả bằng git add . | Đưa nhầm thay đổi độc lập vào commit | Stage theo đường dẫn và kiểm tra lại staged diff |
| Chỉ chạy build | Lỗi nghiệp vụ có thể không được phát hiện | Chạy test cho các hành vi và trường hợp biên bị ảnh hưởng |
| Chạy git commit khi đang rebase | Làm sai luồng thao tác hoặc gây nhầm lẫn | Dùng git rebase --continue khi rebase đang chờ |
| Bỏ qua tệp cấu hình hoặc lockfile | Ứng dụng có thể chạy sai ở môi trường khác | Kiểm tra dependency, profile, schema và migration liên quan |
| Không kiểm tra trạng thái sau khi continue | Có thể rebase/cherry-pick còn commit tiếp theo cần xử lý | Chạy git status sau mỗi lần tiếp tục |

## Ghi nhớ

Giải quyết conflict chỉ hoàn tất khi Git không còn ghi nhận đường dẫn unmerged, nội dung cuối đã được đọc lại, thay đổi được stage đúng và hành vi liên quan đã được xác nhận. Dùng git status, git diff --name-only --diff-filter=U và git ls-files -u để kiểm tra trạng thái; tìm marker trong các tệp đã sửa; xem cả diff staged lẫn unstaged; chạy kiểm tra phù hợp; cuối cùng tiếp tục đúng thao tác merge, rebase hoặc cherry-pick. Mục tiêu là bảo toàn ý định của các thay đổi được kết hợp và giữ cho ứng dụng hoạt động đúng sau khi lịch sử được cập nhật.

