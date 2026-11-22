# Đánh giá kết quả hợp nhất bằng diff, log và kiểm thử

Một lệnh git merge chạy thành công chỉ cho biết Git đã cập nhật lịch sử hoặc working tree theo chiến lược hợp nhất được chọn. Nó chưa chứng minh kết quả cuối cùng đúng với yêu cầu. Merge không có conflict vẫn có thể bỏ sót hành vi cần thiết; merge có conflict có thể được giải quyết hết về mặt cú pháp nhưng chọn sai logic. Sau khi hợp nhất, bạn cần đọc đồ thị commit, so sánh snapshot kết quả với các nhánh đầu vào và chạy kiểm thử trên chính trạng thái đã hợp nhất.

Trong chương **Hợp nhất nhánh** của module **SOURCE_CONTROL_GIT**, bài học này hướng dẫn cách đánh giá merge bằng ba nguồn bằng chứng: diff cho biết nội dung thay đổi, log cho biết lịch sử nào đã được kết nối, và kiểm thử cho biết hành vi của kết quả. Bạn sẽ biết cách so sánh merge commit với từng parent, xem phần xử lý conflict, phân biệt merge commit với fast-forward hoặc squash merge và lập quy trình xác minh trước khi chia sẻ kết quả.

Sau bài học, bạn có thể:

- Ghi lại commit đầu và cuối của các nhánh trước khi merge.
- Đọc đồ thị lịch sử và xác định commit nào đã được tích hợp.
- Dùng git diff để so sánh kết quả với nhánh đích và nhánh nguồn.
- Đọc first parent, second parent và combined diff của merge commit.
- Kiểm tra phần thay đổi do giải quyết conflict.
- Phân biệt merge commit, fast-forward và squash merge khi đánh giá lịch sử.
- Kiểm tra index, working tree, whitespace và dấu conflict còn sót.
- Chọn kiểm thử phù hợp và xác minh trên đúng merge result.
- Lập báo cáo ngắn gọn về nội dung, lịch sử và kết quả kiểm thử.

## 1. Vì sao cần đánh giá sau merge?

Merge kết hợp lịch sử của các nhánh và tạo ra trạng thái code mới. Kết quả có thể khác với cả hai nhánh đầu vào vì hai nhánh thay đổi các phần độc lập, cùng sửa một vùng code, hoặc người giải quyết conflict chọn một phía, kết hợp hai phía hay viết lại logic. Merge strategy cũng có thể ảnh hưởng cách Git tạo kết quả.

Đánh giá sau merge cần trả lời ba câu hỏi:

1. **Nội dung:** Kết quả cuối cùng chứa thay đổi mong đợi và không mang theo thay đổi ngoài phạm vi hay không?
2. **Lịch sử:** Các commit dự kiến đã được tích hợp đúng và quan hệ parent có hợp lý hay không?
3. **Hành vi:** Build, test, lint và các kiểm tra liên quan có thành công trên kết quả đã hợp nhất hay không?

Không có một lệnh đơn lẻ trả lời đủ cả ba câu hỏi. Hãy kết hợp diff, log, status và test.

## 2. Ghi lại mốc trước khi merge

Muốn đánh giá kết quả, bạn cần biết trạng thái ban đầu của nhánh đích và nhánh nguồn. Nếu không ghi lại OID trước merge, branch có thể đã di chuyển và bạn sẽ khó phân biệt thay đổi nào thuộc về lần hợp nhất đang xem.

Giả sử bạn đang ở branch main và muốn merge origin/feature/payment.

### Bước 1: cập nhật thông tin remote

~~~bash
git fetch origin
git status -sb
git branch --show-current
git log -1 --oneline --decorate
~~~

fetch cập nhật remote-tracking refs mà không tự merge vào branch hiện tại. Không bắt đầu merge khi working tree hoặc index có thay đổi chưa được xử lý. Hãy commit, stash hoặc lưu chúng theo cách phù hợp.

### Bước 2: ghi lại OID của hai đầu vào

~~~bash
git rev-parse HEAD
git rev-parse origin/feature/payment
~~~

Gọi hai giá trị này là target-before (commit tip của branch đích trước merge) và source-before (commit tip của branch nguồn tại thời điểm merge). Lưu hai OID vào ghi chú review hoặc biến shell để dùng lại. Trong các ví dụ tiếp theo, thay placeholder target-before và source-before bằng OID thực tế đã ghi lại.

### Bước 3: xem lịch sử và phạm vi thay đổi trước merge

~~~bash
git log --graph --oneline --decorate --boundary main...origin/feature/payment
git diff --stat main...origin/feature/payment
git diff --check main...origin/feature/payment
git merge-base main origin/feature/payment
git log --oneline --decorate main..origin/feature/payment
~~~

Ba chấm có ý nghĩa khác nhau tùy lệnh:

- Với git log A...B, Git liệt kê symmetric difference: các commit chỉ reachable từ một phía.
- Với git diff A...B, Git so sánh merge base của A và B với B. Đây thường là cách review phần thay đổi của nhánh nguồn kể từ điểm chung.

Đừng đọc hai biểu thức này như cùng một phép tính. Lệnh git log main..origin/feature/payment liệt kê commit reachable từ branch nguồn nhưng không reachable từ branch đích tại thời điểm chạy.

## 3. Xác định loại kết quả merge

Sau merge, trước tiên xác định Git đã tạo kiểu lịch sử nào. Không phải mọi thao tác merge đều tạo merge commit.

### Merge commit

Một merge commit thường có ít nhất hai parent. Parent thứ nhất thường là tip của branch đang checkout; parent thứ hai là tip của branch được merge vào.

~~~text
          A1 --- A2  (feature)
         /          \
Base ---              M  (main)
         \          /
          B1 --- B2
~~~

M ghi nhận hai lịch sử đã được kết nối và tree của kết quả hợp nhất.

### Fast-forward

Nếu tip của branch đích là ancestor của branch nguồn, Git có thể di chuyển branch đích tiến lên mà không tạo merge commit:

~~~text
Trước:
A --- B  (main)
       \
        C --- D  (feature)

Sau:
A --- B --- C --- D  (main, feature)
~~~

Trong trường hợp này, HEAD sau merge thường chính là source tip. Lịch sử không có commit mới với hai parent.

### Squash merge

git merge --squash chuẩn bị thay đổi của nhánh nguồn trong index và working tree nhưng không ghi nhận quan hệ parent của nhánh nguồn trong commit được tạo sau đó. Nếu bạn commit kết quả, commit mới thường có một parent là branch đích trước merge.

Vì vậy, log có thể không cho thấy commit gốc của feature là ancestor của branch đích, dù nội dung của feature đã được đưa vào. Khi đánh giá squash merge, hãy so sánh tree và nội dung với source tip đã ghi lại, không chỉ kiểm tra quan hệ ancestor.

## 4. Đọc đồ thị lịch sử sau merge

~~~bash
git log --graph --oneline --decorate --all -20
~~~

Các phần:

- --graph vẽ quan hệ nhánh bằng ký tự.
- --oneline rút gọn mỗi commit thành một dòng.
- --decorate hiển thị branch, tag và ref ở commit tương ứng.
- --all đưa các ref local và remote-tracking vào phạm vi duyệt.

Đồ thị giúp bạn thấy merge commit nối các nhánh hay branch chỉ được fast-forward. Tuy nhiên, output có thể dài và thứ tự hiển thị không phải lúc nào cũng trực quan với repository có nhiều nhánh.

### Xem riêng lịch sử first-parent

~~~bash
git log --first-parent --oneline --decorate main
git log --first-parent --oneline <target-before>..HEAD
~~~

First-parent history đi theo parent thứ nhất của từng commit. Đây là góc nhìn hữu ích để xem các lần tích hợp vào branch main, đặc biệt khi nhóm dùng merge commit.

Vì tùy chọn này chỉ đi theo parent thứ nhất, nó không liệt kê các commit chỉ nằm trên second-parent branch. Để xem commit của nhánh nguồn, dùng git log target-before..source-before hoặc xem toàn bộ graph.

### Kiểm tra commit nguồn đã trở thành ancestor chưa

Với merge commit hoặc fast-forward merge thông thường:

~~~bash
git merge-base --is-ancestor <source-before> HEAD
~~~

Mã thoát 0 nghĩa là source-before là ancestor của HEAD. Nếu lệnh thất bại, có thể merge chưa tích hợp source tip, branch đã thay đổi, hoặc bạn đang đánh giá squash/rebase workflow vốn không giữ nguyên commit ID nguồn.

Kiểm tra branch đích cũ còn là ancestor:

~~~bash
git merge-base --is-ancestor <target-before> HEAD
~~~

Với merge thông thường, target-before thường vẫn là ancestor của kết quả. Không dùng kiểm tra ancestor làm bằng chứng duy nhất cho squash merge: squash giữ nội dung nhưng không giữ quan hệ parent của các commit nguồn.

## 5. Xác định merge commit và các parent

Nếu HEAD là merge commit, xem OID, tree và parent:

~~~bash
git show -s --format="commit=%H%ntree=%T%nparents=%P%nsubject=%s" HEAD
git rev-list --parents -n 1 HEAD
git cat-file -p HEAD
~~~

Trong merge hai nhánh thông thường:

- HEAD^1 là first parent, thường là branch đích trước merge.
- HEAD^2 là second parent, thường là branch nguồn trước merge.

Đừng mặc định thứ tự parent chỉ từ tên branch trong thông điệp. Hãy đọc OID parent và đối chiếu với các OID đã ghi lại:

~~~bash
git rev-parse 'HEAD^1'
git rev-parse 'HEAD^2'
~~~

Nếu first parent bằng target-before và second parent bằng source-before, cấu trúc parent phù hợp với merge dự kiến. Với octopus merge có nhiều hơn hai parent; hãy xem toàn bộ danh sách trong %P.

Nếu HEAD không có hai parent, có thể kết quả là fast-forward, squash commit, commit thường hoặc bạn đang đứng trên commit khác. Đừng chạy phép so sánh HEAD^2 trước khi xác nhận số parent.

## 6. So sánh kết quả với branch đích trước merge

Đây thường là phép so sánh quan trọng nhất để biết merge đã thêm gì vào branch đích.

~~~bash
git diff --stat <target-before> HEAD
git diff --name-status <target-before> HEAD
git diff <target-before> HEAD
~~~

Ý nghĩa:

- --stat cho biết phạm vi thay đổi theo file và số dòng.
- --name-status liệt kê file cùng trạng thái thêm, sửa, xóa hoặc đổi tên.
- Diff đầy đủ cho biết nội dung cụ thể được thêm hoặc loại bỏ.

Phép so sánh này trả lời: từ snapshot của branch đích trước merge đến snapshot hiện tại, repository đã thay đổi những gì?

Hãy kiểm tra tất cả file thuộc yêu cầu merge, file bị xóa hoặc sửa ngoài dự kiến, cấu hình, migration, dependency và test. Xác nhận thay đổi từ branch đích trước merge không bị mất và các dòng giải quyết conflict giữ đúng ý định của hai phía.

Nếu chỉ xem git show HEAD, bạn có thể thấy thay đổi của merge commit so với một parent mặc định nhưng không có bối cảnh đầy đủ. Dùng OID mốc rõ ràng giúp phép so sánh dễ giải thích và lặp lại.

## 7. So sánh merge result với từng parent

Với merge commit M có hai parent, hãy xem cả hai phía:

~~~bash
git diff --stat 'HEAD^1' HEAD
git diff 'HEAD^1' HEAD

git diff --stat 'HEAD^2' HEAD
git diff 'HEAD^2' HEAD
~~~

So sánh với first parent cho thấy tất cả thay đổi cần thiết để branch đích trước merge trở thành kết quả hợp nhất. Đây thường là diff phù hợp khi review tác động của merge lên main.

So sánh với second parent cho thấy kết quả cuối cùng khác nhánh nguồn như thế nào. Nó có thể làm lộ ra các thay đổi đến từ branch đích hoặc quyết định xử lý conflict trong merge.

~~~text
First parent (main trước merge):      M
Second parent (feature trước merge):  F
Merge result:                         R

diff M..R: thay đổi được thêm vào main
diff F..R: khác biệt giữa kết quả cuối và feature
~~~

Nếu R khác F, điều đó không tự động có nghĩa merge sai. Có thể main chứa các thay đổi cần giữ hoặc người giải quyết conflict đã kết hợp hai cách triển khai. Hãy đọc từng hunk và xác minh bằng yêu cầu chức năng.

Fast-forward không tạo merge commit nên HEAD^2 thường không tồn tại. Squash commit cũng thường chỉ có một parent. Trong hai trường hợp này, dùng target-before và source-before đã ghi lại để so sánh.

## 8. Dùng combined diff để xem merge commit

~~~bash
git show --cc HEAD
git show --combined-all-paths --cc HEAD
~~~

--cc yêu cầu combined diff cho merge commit. Kiểu hiển thị này hữu ích để tập trung vào các phần khác nhau so với nhiều parent, đặc biệt là vùng có kết quả hợp nhất riêng.

Combined diff có cách trình bày dấu cộng/trừ và header hunk khác unified diff thông thường. Nó không nhất thiết liệt kê mọi thay đổi của merge so với từng parent. Nếu cần review toàn bộ nội dung, vẫn xem riêng diff với first parent và second parent.

Combined diff cũng thường chỉ hiển thị file có thay đổi so với tất cả parent. Vì vậy, không thấy một file trong output --cc không có nghĩa file đó không thay đổi so với một parent cụ thể.

### Dùng --remerge-diff để kiểm tra cách giải quyết conflict

Trên phiên bản Git hỗ trợ:

~~~bash
git show --remerge-diff HEAD
~~~

Git dựng lại kết quả merge tự động từ các parent rồi so sánh với tree thực tế của merge commit. Diff này có thể làm nổi bật những chỉnh sửa thủ công được thực hiện để giải quyết conflict.

Đây là bằng chứng hữu ích khi review merge commit, nhưng chỉ có ý nghĩa với merge commit và kết quả dựng lại phụ thuộc merge machinery cùng phiên bản Git. Không phải mọi khác biệt giữa parent và merge result đều là sửa conflict; chúng cũng có thể là thay đổi có chủ đích khác. Nếu Git cũ không hỗ trợ tùy chọn, dùng diff với từng parent và đọc commit thủ công.

## 9. Kiểm tra nội dung conflict resolution

Một merge có thể hoàn tất nhưng phần giải quyết conflict vẫn sai logic. Ví dụ, hai nhánh cùng sửa một điều kiện:

~~~text
main:     if (user.isActive) { allow(); }
feature:  if (user.hasAccess) { allow(); }
~~~

Kết quả đúng có thể cần cả hai điều kiện:

~~~javascript
if (user.isActive && user.hasAccess) {
  allow();
}
~~~

Nếu người giải quyết conflict chỉ giữ một phía, merge vẫn có thể tạo commit và test hiện có có thể chưa bao phủ trường hợp còn thiếu.

### Kiểm tra index không còn unmerged entry

~~~bash
git ls-files -u
~~~

Sau khi merge được hoàn tất, lệnh này thường không in entry nào. Nếu còn output, index vẫn có các stage chưa giải quyết; merge chưa được hoàn tất đúng quy trình.

### Kiểm tra trạng thái repository

~~~bash
git status
git status --porcelain=v1
~~~

Với merge commit đã hoàn tất, status thường không còn thông báo merge đang diễn ra hoặc file unmerged. Working tree có thể vẫn có thay đổi mới do người dùng tạo sau merge; hãy phân biệt chúng với nội dung của commit.

### Tìm conflict marker còn sót

Bạn có thể tìm dấu marker thường gặp trong các file văn bản:

~~~bash
git grep -n -E '^(<<<<<<<|=======|>>>>>>>)'
~~~

Đây là phép quét hỗ trợ, không phải bằng chứng tuyệt đối. Dòng ======= có thể là nội dung hợp lệ trong tài liệu hoặc file khác; kết quả cần được mở và kiểm tra thủ công. Một số conflict ở binary, file cấu hình hoặc cấu trúc dữ liệu không thể được phát hiện bằng tìm kiếm marker.

### Đọc diff của file từng conflict

~~~bash
git diff 'HEAD^1' HEAD -- src/config.js
git diff 'HEAD^2' HEAD -- src/config.js
~~~

Xem nội dung cuối cùng, đối chiếu hai parent và xác nhận quyết định hợp nhất có giữ được yêu cầu từ hai phía.

## 10. Kiểm tra whitespace và lỗi định dạng

~~~bash
git diff --check <target-before> HEAD
git diff --check
~~~

Lệnh đầu kiểm tra whitespace trong thay đổi của merge so với target-before. Lệnh thứ hai kiểm tra phần thay đổi chưa stage giữa working tree và index theo phạm vi mặc định của git diff --check.

Các lỗi thường gặp gồm khoảng trắng thừa ở cuối dòng, dòng mới hoặc định dạng bị thay đổi ngoài ý muốn, line ending bị chuyển toàn bộ, thụt lề hoặc dấu phân cách cấu hình bị sai.

git diff --check không phát hiện lỗi logic, lỗi cú pháp mọi ngôn ngữ hoặc conflict marker trong mọi loại file. Nó chỉ là một bước kiểm tra nhỏ trong quy trình. Nếu repository có quy tắc format hoặc lint, hãy chạy đúng lệnh dự án yêu cầu trên merge result.

## 11. Đánh giá khi merge là fast-forward

Fast-forward không tạo merge commit, vì vậy không có second parent để xem. Hãy dùng các mốc trước merge:

~~~bash
git diff --stat <target-before> HEAD
git diff --name-status <target-before> HEAD
git diff <target-before> HEAD
git log --oneline --decorate <target-before>..HEAD
~~~

Nếu source-before là tip của nhánh nguồn tại thời điểm merge:

~~~bash
git merge-base --is-ancestor <source-before> HEAD
~~~

Lệnh thành công cho thấy source tip đã nằm trong lịch sử hiện tại. Nếu HEAD đúng bằng source-before, đây là trường hợp fast-forward điển hình.

Xem branch hiện tại và commit tip:

~~~bash
git status -sb
git log -1 --oneline --decorate
~~~

Đừng kết luận không có merge chỉ vì không thấy merge commit. Fast-forward là một kiểu merge hợp lệ; lịch sử được cập nhật bằng cách di chuyển ref.

## 12. Đánh giá khi dùng squash merge

Với squash, Git không ghi các commit nguồn làm parent của commit mới. Do đó:

- Commit mới thường có một parent là target-before.
- Source-before có thể không phải ancestor của HEAD.
- git log target-before..HEAD thường chỉ thấy commit squash mới.
- Nội dung vẫn có thể chứa toàn bộ thay đổi mong muốn từ branch nguồn.

Kiểm tra:

~~~bash
git show --stat --oneline HEAD
git diff <target-before> HEAD
git diff <source-before> HEAD
~~~

Phép so sánh target-before với HEAD cho biết thay đổi được thêm vào branch đích. Phép so sánh source-before với HEAD giúp xem kết quả cuối khác snapshot của nhánh nguồn như thế nào.

Với squash, việc không thấy source commit trong log không nhất thiết là thiếu thay đổi. Hãy đánh giá cả tree và nội dung, không chỉ quan hệ parent.

## 13. Đánh giá lịch sử bằng log và phạm vi commit

Diff cho biết snapshot khác nhau ra sao; log cho biết commit nào và thông điệp nào đã đi vào lịch sử.

~~~bash
git log --oneline --decorate <target-before>..HEAD
git log --graph --oneline --decorate --all -20
git log --first-parent --oneline <target-before>..HEAD
git log --format=fuller -5 HEAD
~~~

Hãy đối chiếu các commit dự kiến của feature, commit message, commit không liên quan, commit bị bỏ sót do branch nguồn chưa được fetch hoặc chọn sai base, và parent của merge commit.

Nếu vẫn còn source branch:

~~~bash
git log --left-right --cherry-pick --oneline main...origin/feature/payment
~~~

Ký hiệu < và > cho biết commit thuộc phía nào. --cherry-pick bỏ qua một số cặp commit có patch-equivalent trong phạm vi so sánh, hữu ích khi lịch sử có cherry-pick hoặc rebase. Lệnh này giúp phát hiện khác biệt lịch sử, nhưng không chứng minh code hoạt động đúng.

## 14. Kiểm thử phải chạy trên merge result

Sau khi merge, code cần được kiểm thử trong đúng snapshot mà bạn định chia sẻ. Nếu test chạy trên branch nguồn trước merge, nó không kiểm tra các thay đổi được thêm từ branch đích hoặc phần conflict resolution.

| Lớp | Mục đích | Ví dụ kiểm tra |
| --- | --- | --- |
| Unit test | Xác minh hàm hoặc module riêng lẻ | Quy tắc tính toán, validation, edge case |
| Integration test | Xác minh các thành phần kết hợp | API với database, service với queue |
| Regression test | Bảo đảm hành vi cũ không bị phá | Bug đã sửa, luồng quan trọng |
| Lint/static analysis | Phát hiện lỗi định dạng và vấn đề code | Linter, type checker, static analyzer |
| Build/package | Xác minh dự án tạo artifact được | Compile, bundle, package |
| End-to-end/manual | Kiểm tra luồng người dùng hoặc hệ thống | Đăng nhập, thanh toán, deploy thử |

Không phải dự án nào cũng có đủ các lớp này. Chọn tập kiểm thử theo rủi ro và quy định CI của repository.

### Chạy test tập trung trước

Nếu merge có thay đổi trong parser, bắt đầu bằng test parser và các test liên quan đến input biên. Nếu thay đổi schema hoặc migration, kiểm tra nâng cấp từ trạng thái dữ liệu mà dự án hỗ trợ.

### Chạy toàn bộ kiểm tra bắt buộc

Sau test tập trung, chạy full test suite, lint, type check và build theo tài liệu dự án. Đừng đoán lệnh từ một stack khác; dùng script hoặc CI job chính thức của repository.

### Ghi nhận đúng commit được test

~~~bash
git rev-parse HEAD
git status --short
~~~

Ghi lại OID trong báo cáo kiểm thử. Nếu HEAD thay đổi sau khi test, kết quả trước đó không chứng minh commit mới đã được kiểm tra.

## 15. Khi test thất bại sau merge

Một test fail sau merge chưa đủ để kết luận merge gây lỗi. Hãy tìm phạm vi thay đổi và xác định lỗi đến từ đâu.

~~~bash
git log -1 --oneline --decorate
git status -sb
git diff <target-before> HEAD -- path/to/affected-file
git log --oneline -- path/to/affected-file
~~~

Với merge commit, so sánh file với từng parent:

~~~bash
git diff 'HEAD^1' HEAD -- path/to/affected-file
git diff 'HEAD^2' HEAD -- path/to/affected-file
~~~

Nếu một dòng chỉ khác so với source parent, có thể đó là phần conflict resolution hoặc thay đổi từ target. Đọc logic và test để xác định ý định đúng. Đồng thời xác nhận dữ liệu test, biến môi trường, dependency và service phụ trợ; lỗi có thể đến từ môi trường hoặc test không ổn định.

Nếu merge result đã được commit, tạo commit sửa tiếp theo hoặc làm theo quy trình sửa lỗi của nhóm. Không sửa trực tiếp merge commit đã chia sẻ bằng cách viết lại lịch sử nếu chưa được thống nhất.

## 16. Kiểm tra trạng thái cuối trước khi chia sẻ

~~~bash
git status -sb
git status --porcelain=v1
git ls-files -u
git diff --check
git log --graph --oneline --decorate -12
git show --stat --oneline HEAD
git rev-parse HEAD
~~~

Mong đợi:

- Không còn merge đang diễn ra.
- Không còn unmerged index entries.
- Không có thay đổi local ngoài dự kiến.
- Không có whitespace error trong diff được kiểm tra.
- OID được ghi lại đúng là commit đã chạy test.

Nếu working tree có thay đổi được tạo sau merge, đừng gộp chúng vào báo cáo merge result. Hãy commit hoặc lưu riêng theo workflow của nhóm rồi chạy lại các kiểm tra cần thiết.

## 17. Quy trình đánh giá merge hoàn chỉnh

Giả sử branch main cần merge feature/payment. Bạn muốn xác nhận thay đổi, lịch sử và test trước khi push.

### Trước merge

~~~bash
git fetch origin
git switch main
git status -sb
git rev-parse HEAD
git rev-parse origin/feature/payment
git merge-base main origin/feature/payment
git log --graph --oneline --decorate main...origin/feature/payment
git diff --stat main...origin/feature/payment
~~~

Ghi lại OID target-before và source-before. Review diff và commit nguồn, xác nhận đúng phạm vi.

### Thực hiện merge

~~~bash
git merge --no-ff --no-edit origin/feature/payment
~~~

Ví dụ này yêu cầu tạo merge commit nếu merge có thể hoàn tất; tùy chính sách nhóm, bạn có thể dùng fast-forward hoặc squash thay thế. Lệnh merge chỉ là bước tích hợp, chưa phải xác nhận cuối.

### Sau merge

~~~bash
git status -sb
git rev-list --parents -n 1 HEAD
git log --graph --oneline --decorate --all -20
git diff --stat <target-before> HEAD
git diff <target-before> HEAD
git diff 'HEAD^1' HEAD
git diff 'HEAD^2' HEAD
git show --cc HEAD
git show --remerge-diff HEAD
~~~

Chỉ chạy các lệnh so sánh parent khi HEAD là merge commit có đủ parent. Nếu Git không hỗ trợ --remerge-diff, bỏ qua tùy chọn đó và review diff với từng parent.

### Kiểm tra và test

~~~bash
git ls-files -u
git diff --check <target-before> HEAD
~~~

Tiếp theo chạy test tập trung, full test suite, lint, build và các kiểm tra tích hợp theo yêu cầu dự án. Ghi lại OID đã test cùng kết quả.

### Báo cáo

Một báo cáo merge dễ review nên ghi branch nguồn và branch đích, OID target-before/source-before/merge result, loại kết quả, file và thay đổi quan trọng, conflict đã giải quyết, test/lint/build đã chạy cùng kết quả và giới hạn chưa kiểm tra.

## 18. Những nhầm lẫn thường gặp

### Merge thành công có nghĩa code đúng?

Không. Git xác nhận thao tác hợp nhất hoàn tất theo quy tắc của nó. Bạn vẫn phải review diff và chạy test.

### git show HEAD luôn cho thấy mọi thay đổi của cả hai nhánh?

Không nhất thiết. Với merge commit, git show mặc định có thể không trình bày diff theo cách bạn mong đợi. Dùng git diff với từng parent và git show --cc để xem các góc nhìn khác nhau.

### HEAD^1 luôn là main và HEAD^2 luôn là feature?

Không. First parent thường là branch đang checkout, nhưng cần xác minh OID parent với mốc đã ghi trước merge.

### Không có merge commit nghĩa là merge thất bại?

Không. Fast-forward cập nhật ref mà không tạo merge commit. Squash merge tạo một commit thường chứa kết quả nhưng không lưu parent của branch nguồn.

### git log A...B và git diff A...B có cùng ý nghĩa?

Không. git log dùng symmetric difference của commit reachable; git diff dùng merge base của A với B để so sánh snapshot. Hãy chọn lệnh theo câu hỏi.

### git diff --check có thay thế test?

Không. Nó phát hiện một số lỗi whitespace trong diff, không kiểm tra logic, build hoặc hành vi runtime.

### Không còn conflict marker nghĩa là conflict đã giải quyết đúng?

Không. Marker có thể đã được xóa nhưng logic vẫn sai. Cần so sánh với hai parent và test các trường hợp liên quan.

### Squash merge phải làm source branch thành ancestor?

Không. Squash không giữ quan hệ parent của các commit nguồn. Đánh giá bằng nội dung tree và diff, không chỉ bằng ancestry.

## 19. Tự kiểm tra

Bạn merge feature/search vào main và Git tạo merge commit M. Trước merge, bạn đã ghi lại OID của main là T và feature/search là S. Sau merge, HEAD là M.

Hãy trả lời:

1. Lệnh nào xem đồ thị lịch sử sau merge?
2. Lệnh nào xác định parent của M?
3. Phép so sánh nào cho biết tác động của merge lên main?
4. Phép so sánh nào cho biết kết quả cuối khác feature/search như thế nào?
5. Vì sao nên xem git show --cc và --remerge-diff khi merge có conflict?
6. Lệnh nào xác nhận S đã trở thành ancestor của M trong merge thông thường?
7. Vì sao test phải chạy trên M thay vì chỉ chạy trên S?
8. Nếu merge là squash, tại sao kiểm tra ancestor của S có thể thất bại dù nội dung đã được đưa vào?

**Gợi ý:** Dùng git log --graph --oneline --decorate --all để xem graph; git rev-list --parents -n 1 M để xem parent. Dùng git diff T M để xem thay đổi so với main trước merge và git diff S M để xem khác biệt so với feature. Combined/remerge diff giúp soi kết quả hợp nhất và chỉnh sửa conflict. Dùng git merge-base --is-ancestor S M cho merge giữ topology. Test trên M vì đó là tree thực tế chứa cả hai phía và conflict resolution. Squash chỉ ghi một parent nên không lưu source commit S trong ancestry.

## Kết luận

Đánh giá merge cần kết hợp diff, log và kiểm thử. Hãy ghi lại OID của branch đích và nguồn trước merge, xác định loại kết quả sau merge, đọc graph và parent, rồi so sánh snapshot cuối với từng đầu vào. Với merge commit, diff với first parent cho thấy tác động lên branch đích; diff với second parent giúp xem phần kết quả khác branch nguồn; combined diff và remerge diff hỗ trợ review conflict resolution. Với fast-forward hoặc squash, dùng OID mốc trước merge thay cho giả định luôn có hai parent. Cuối cùng, xác nhận index và working tree sạch, không còn unmerged entries, chạy test trên đúng merge result và ghi lại OID đã kiểm thử trước khi chia sẻ.
