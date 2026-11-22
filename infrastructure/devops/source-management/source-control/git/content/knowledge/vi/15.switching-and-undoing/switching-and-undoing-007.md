# Hoàn tác merge commit bằng revert -m và hệ quả cho lần hợp nhất sau

## Vì sao hoàn tác merge commit cần chọn mainline?

Trong Git, một merge commit ghi nhận việc kết hợp lịch sử của ít nhất hai nhánh. Khi một lần hợp nhất đưa thay đổi không mong muốn vào nhánh chính, bạn có thể cần hoàn tác phần thay đổi đó nhưng vẫn giữ lịch sử commit đã chia sẻ với nhóm.

Với một commit thông thường, lệnh git revert tạo một commit mới có nội dung đảo ngược thay đổi của commit được chỉ định. Với merge commit, Git cần biết bạn muốn xem nhánh cha nào là đường phát triển chính để tính phần thay đổi cần đảo ngược. Vì vậy, lệnh phải có tùy chọn -m:

~~~bash
git revert -m <parent-number> <merge-commit>
~~~

Tùy chọn -m là viết tắt của mainline. Giá trị theo sau là số thứ tự của parent được chọn, bắt đầu từ 1. Đây là số thứ tự parent trong merge commit, không phải mã commit, tên nhánh hoặc thông điệp commit.

Trong phần lớn tình huống nhóm hợp nhất một nhánh tính năng vào main, parent 1 là commit của main trước khi merge, còn parent 2 là đầu nhánh tính năng được hợp nhất. Khi đó:

~~~bash
git revert -m 1 <merge-commit>
~~~

Lệnh này tạo một commit mới đảo ngược phần thay đổi mà merge commit đã đưa vào so với parent 1. Lịch sử merge vẫn còn trong đồ thị commit. Đây là điểm có ảnh hưởng trực tiếp tới lần merge nhánh đó về sau.

## Merge commit lưu những gì?

Một commit Git thông thường có một parent, trỏ tới commit đứng trước nó. Merge commit có từ hai parent trở lên. Với merge hai nhánh thông thường, nó thường có hai parent:

- Parent 1: commit HEAD của nhánh đang đứng khi thực hiện merge.
- Parent 2: commit tip của nhánh được hợp nhất vào.

Ví dụ, bạn đang ở main và chạy git merge --no-ff feature/payment. Đồ thị có thể trông như sau:

~~~text
          C1---C2  feature/payment
         /       \
A---B---M          main
     parent 1  parent 2
~~~

M là merge commit. Parent 1 là B, parent 2 là C2. Thứ tự này phản ánh thứ tự parent được ghi vào commit, thường tương ứng với nhánh hiện tại trước và nhánh được merge sau.

Nếu dùng fast-forward, Git chỉ di chuyển con trỏ nhánh tới commit mới hơn và không tạo merge commit. Khi đó không có một merge commit để truyền cho git revert -m. Nếu merge theo kiểu squash, kết quả thường là một commit đơn có một parent, vì vậy hoàn tác commit đó bằng git revert thông thường, không dùng -m.

Merge có thể có nhiều hơn hai parent, chẳng hạn octopus merge. Khi đó phải xác định rõ parent nào là mainline cần giữ trước khi chạy revert.

## Xác định đúng merge commit và thứ tự parent

Không nên chọn commit chỉ dựa vào vị trí gần nhất trong git log. Hãy xem đồ thị và metadata của commit.

Liệt kê lịch sử dạng đồ thị:

~~~bash
git log --oneline --graph --decorate --all
~~~

Lọc các merge commit:

~~~bash
git log --oneline --merges
~~~

Xem chi tiết một commit:

~~~bash
git show --no-patch --pretty=raw <merge-commit>
~~~

Kết quả của commit merge thường có các dòng parent như sau:

~~~text
commit 7f8a9b0
tree 3d4e5f6
parent 111aaaa
parent 222bbbb
author ...
committer ...
~~~

Dòng parent đầu tiên là parent 1, dòng thứ hai là parent 2. Có thể lấy commit cùng danh sách parent bằng:

~~~bash
git rev-list --parents -n 1 <merge-commit>
~~~

Ví dụ kết quả:

~~~text
7f8a9b0 111aaaa 222bbbb
~~~

Trong ví dụ này, 111aaaa là parent 1 và 222bbbb là parent 2. Hãy đối chiếu các parent với nhánh và commit thực tế:

~~~bash
git show --no-patch --oneline 111aaaa
git show --no-patch --oneline 222bbbb
~~~

Xem thêm phần thống kê và nội dung merge:

~~~bash
git show --stat --summary <merge-commit>
git diff <merge-commit>^1 <merge-commit>
git diff <merge-commit>^2 <merge-commit>
~~~

Các biểu thức ^1 và ^2 lần lượt tham chiếu parent 1 và parent 2. So sánh merge commit với từng parent giúp hiểu kết quả merge khác nhau ra sao so với mỗi phía.

Nếu chưa xác định được parent nào là nhánh chính cần giữ, dừng lại và kiểm tra lịch sử trước. Chọn nhầm mainline có thể đảo ngược phần thay đổi bạn muốn bảo toàn.

## -m 1 và -m 2 có ý nghĩa gì?

Giả sử merge commit M có hai parent:

~~~text
P1 ---\
       M
P2 ---/
~~~

- git revert -m 1 M chọn P1 làm mainline. Git tính phần thay đổi của M so với P1 rồi đảo ngược phần đó trên HEAD hiện tại.
- git revert -m 2 M chọn P2 làm mainline. Git tính phần thay đổi của M so với P2 rồi đảo ngược phần đó trên HEAD hiện tại.

Trong quy trình merge feature vào main, thông thường bạn muốn giữ đường phát triển main và đảo ngược phần được đưa từ feature vào. Khi merge được tạo từ main, parent 1 thường là main trước merge, do đó -m 1 thường là lựa chọn cần dùng.

Không nên mặc định luôn chọn -m 1. Nếu merge được tạo khi đang đứng ở nhánh khác, thứ tự parent có thể khác. Hãy kiểm tra parent trước khi chọn.

Tùy chọn -m không có nghĩa là chọn thông điệp commit, chọn số commit cần revert hay chọn nhánh bằng tên. Nó xác định parent được xem là mainline để Git tính patch đảo ngược.

## Hoàn tác merge commit bằng git revert -m

Giả sử nhánh main đã nhận merge commit 7f8a9b0 từ feature/payment. Sau khi triển khai, nhóm phát hiện thay đổi trong lần merge đó gây lỗi và cần hoàn tác phần được merge.

Trước khi revert, kiểm tra trạng thái kho:

~~~bash
git status
git branch --show-current
~~~

Nên bắt đầu từ nhánh cần nhận commit hoàn tác, thường là main hoặc nhánh phát hành đang chứa merge commit đó. Nếu working tree có thay đổi chưa commit, hãy xử lý chúng trước theo quy trình của nhóm.

Xác định parent của merge commit:

~~~bash
git rev-list --parents -n 1 7f8a9b0
~~~

Giả sử kết quả xác nhận parent 1 là main trước merge. Thực hiện:

~~~bash
git revert -m 1 7f8a9b0
~~~

Git áp dụng phần đảo ngược của merge commit lên HEAD hiện tại và tạo một commit mới. Git có thể mở trình soạn thảo để xác nhận thông điệp, ví dụ:

~~~text
Revert "Merge branch 'feature/payment' into main"

This reverts commit 7f8a9b0, reversing
changes made to 7f8a9b0.
~~~

Thông điệp thực tế do Git tạo có thể khác tùy phiên bản và cấu hình. Sau khi hoàn tất, xem commit mới và trạng thái kho:

~~~bash
git status
git log --oneline --graph --decorate -n 12
git show --stat --oneline HEAD
~~~

Commit revert là một commit mới có một parent là HEAD trước khi revert. Merge commit gốc vẫn tồn tại trong lịch sử và vẫn là tổ tiên của nhánh.

### Dùng --no-edit hoặc --no-commit

Nếu muốn dùng thông điệp mặc định mà không mở trình soạn thảo:

~~~bash
git revert --no-edit -m 1 7f8a9b0
~~~

Nếu muốn kiểm tra kết quả đảo ngược trước khi tạo commit:

~~~bash
git revert --no-commit -m 1 7f8a9b0
~~~

Với --no-commit, Git áp dụng thay đổi đảo ngược vào working tree và staging area nhưng không tự tạo commit. Hãy xem lại:

~~~bash
git status
git diff
git diff --cached
git diff --cached --check
~~~

Sau khi xác nhận nội dung, chạy kiểm thử cần thiết rồi tạo commit theo quy trình của nhóm:

~~~bash
git commit -m "Revert payment feature merge"
~~~

Không chạy git revert --no-commit chỉ để xem thử nếu bạn chưa hiểu trạng thái index và working tree sẽ thay đổi. Đây là thao tác sửa kho cục bộ; nếu kết quả không đúng, cần xử lý theo trạng thái thực tế trước khi tiếp tục.

## Revert merge có thể phát sinh conflict

Nếu nhánh main đã có những thay đổi tiếp theo dựa trên nội dung của merge commit, patch đảo ngược có thể không áp dụng tự động. Git sẽ dừng và báo conflict.

Bắt đầu bằng:

~~~bash
git status
git diff --name-only --diff-filter=U
~~~

Đọc các vùng xung đột và xác định kết quả mong muốn. Khi hoàn tác merge, mục tiêu là đảo ngược phần thay đổi của merge so với mainline đã chọn, đồng thời bảo toàn những thay đổi hợp lệ khác đã có trên HEAD sau merge.

Sau khi chỉnh sửa tệp, stage kết quả:

~~~bash
git add -- src/PaymentService.java config/application.yml
~~~

Nếu một tệp cần bị xóa trong kết quả revert:

~~~bash
git rm -- path/to/file
~~~

Kiểm tra index và diff:

~~~bash
git status
git ls-files -u
git diff --cached
git diff --cached --check
~~~

Khi đã giải quyết tất cả conflict, tiếp tục thao tác revert:

~~~bash
git revert --continue
~~~

Nếu quyết định dừng và hủy lần revert đang dang dở:

~~~bash
git revert --abort
~~~

--abort trong ngữ cảnh này hủy tiến trình revert hiện tại. Nó không phải git rebase --abort và cũng không xóa merge commit gốc.

Sau khi revert hoàn tất, chạy lại test liên quan tới chức năng vừa hoàn tác và các thành phần phụ thuộc. Việc patch áp dụng thành công không đảm bảo hệ thống vẫn đúng về nghiệp vụ.

## Hệ quả quan trọng: revert merge không xóa lịch sử merge

Đây là điểm cần hiểu kỹ trước khi lên kế hoạch hợp nhất lại nhánh.

Khi chạy git revert -m 1 M, Git tạo một commit mới có nội dung đảo ngược thay đổi của M so với parent 1. Tuy nhiên, commit M và các commit thuộc nhánh được merge vẫn nằm trong đồ thị tổ tiên của main.

Minh họa:

~~~text
                 C1---C2  feature/payment
                /       \
A---B-----------M---R     main
                 merge  revert M
~~~

Trong sơ đồ:

- M đã đưa C1 và C2 vào lịch sử main.
- R là commit revert M, đảo ngược nội dung thay đổi của merge.
- C1, C2 và M vẫn là tổ tiên của main thông qua R.

Git quyết định phần nào cần merge dựa trên quan hệ tổ tiên và merge base của hai nhánh. Revert chỉ thay đổi nội dung cây làm việc qua một commit mới; nó không xóa quan hệ tổ tiên của merge commit.

Vì vậy, nếu bạn merge lại chính nhánh feature/payment mà không có commit mới, Git thường không đưa C1 và C2 vào lần nữa. Những commit đó đã là tổ tiên của main, dù nội dung của chúng đã bị revert trong cây làm việc.

Một thông báo kiểu Already up to date có thể xuất hiện nếu nhánh nguồn không có commit mới để tích hợp.

## Ví dụ: lần merge thứ hai không khôi phục thay đổi đã revert

Giả sử lịch sử ban đầu:

~~~text
A---B---M---R       main
     \   /
      C1---C2       feature/payment
~~~

M là merge commit. R là commit hoàn tác M bằng git revert -m 1 M.

Nếu feature/payment vẫn ở C2 và không có commit mới, chạy:

~~~bash
git switch main
git merge feature/payment
~~~

Git nhận ra C1 và C2 đã nằm trong lịch sử của main thông qua M. Commit R không xóa quan hệ đó. Vì vậy, merge không tự áp dụng lại thay đổi mà R đã đảo ngược.

Đây không phải lỗi của Git. Đây là kết quả đúng của mô hình lịch sử phân tán: một revert là commit mới sửa nội dung, không viết lại quá khứ.

### Nếu nhánh nguồn có commit mới

Giả sử nhóm tiếp tục phát triển feature/payment và tạo C3 sau C2:

~~~text
A---B---M---R          main
     \   /       \
      C1---C2---C3     feature/payment
~~~

Khi merge feature/payment vào main, Git thường chỉ cần tích hợp các commit mới kể từ merge base M, tức phần thay đổi của C3. Nội dung từ C1 và C2 vẫn được xem là đã hợp nhất trước đó, dù R đã đảo ngược chúng trong cây làm việc.

Điều này có thể tạo ra tình huống khó xử: C3 có thể phụ thuộc vào chức năng hoặc cấu trúc dữ liệu đã bị R loại bỏ. Merge chỉ mang phần commit mới, nhưng phần mới có thể không chạy đúng nếu các thay đổi cũ chưa được khôi phục.

Trước khi merge tiếp, hãy kiểm tra phụ thuộc của các commit mới và quyết định có cần khôi phục thay đổi cũ hay phải điều chỉnh nhánh nguồn.

## Cách đưa thay đổi đã revert trở lại

Nếu nhóm xác nhận muốn khôi phục toàn bộ thay đổi của merge đã bị revert, cách thường dùng là revert chính commit revert.

Giả sử:

- M là merge commit gốc.
- R là commit được tạo bởi git revert -m 1 M.

Thực hiện trên nhánh cần khôi phục:

~~~bash
git revert R
~~~

Lệnh này đảo ngược nội dung của R, tức áp dụng lại phần thay đổi mà R đã hoàn tác. Git tạo một commit mới, thường được gọi là revert-of-revert.

Minh họa:

~~~text
A---B---M---R---RR     main
     \   /       ^
      C1---C2    revert R
~~~

Sau RR, nội dung của merge ban đầu được khôi phục trong cây làm việc. Quan hệ tổ tiên vẫn được giữ nguyên. Nếu feature/payment có thêm C3, nhóm có thể tiếp tục merge phần commit mới sau khi xác nhận trạng thái và phụ thuộc.

Kiểm tra commit revert trước khi đảo ngược nó:

~~~bash
git show --stat --oneline R
git show R
~~~

Sau đó thực hiện:

~~~bash
git revert R
~~~

Nếu có conflict, giải quyết như một thao tác revert thông thường, stage các tệp và chạy git revert --continue. Cuối cùng kiểm tra diff, lịch sử và test.

Không nên revert-of-revert chỉ để làm cho lần merge sau hết báo Already up to date. Hãy xác nhận nhóm thực sự muốn khôi phục hành vi cũ. Nếu chỉ cần một phần tính năng, có thể tạo commit mới triển khai lại phần cần thiết hoặc sửa nhánh nguồn để phù hợp với trạng thái hiện tại.

## Một quy trình thay thế: tạo commit mới cho phần cần khôi phục

Không phải lúc nào cũng cần revert commit revert. Nếu nhóm chỉ muốn một phần thay đổi quay trở lại, có thể tạo commit mới trên main để triển khai lại phần cần thiết.

Ví dụ:

- Merge ban đầu đưa toàn bộ module thanh toán vào main.
- Revert merge vì một phương thức xử lý chưa an toàn.
- Sau khi sửa, nhóm chỉ muốn khôi phục API tra cứu giao dịch trước.
- Thay vì khôi phục toàn bộ merge, nhóm tạo commit mới chỉ đưa API tra cứu đã được sửa và kiểm thử trở lại.

Cách này giữ phạm vi khôi phục rõ ràng. Tuy nhiên, cần lưu ý rằng lịch sử của C1/C2 vẫn đã được merge. Commit mới là thay đổi mới trên main, không phải lần merge lại của những commit cũ.

Nếu nhóm muốn tiếp tục phát triển nhánh feature, cần đồng bộ nhánh đó với main và kiểm tra các commit mới có phụ thuộc vào phần đã bị revert hay không. Có thể cần rebase hoặc merge main vào nhánh feature theo quy ước của dự án.

## Phân biệt revert merge, revert commit thường và reset

| Thao tác | Dùng khi | Tác động lịch sử |
|---|---|---|
| git revert <commit> | Đảo ngược một commit thông thường | Tạo commit mới đảo ngược thay đổi |
| git revert -m 1 <merge> | Đảo ngược thay đổi của merge so với parent 1 | Tạo commit mới; merge gốc vẫn là tổ tiên |
| git revert <revert-commit> | Khôi phục thay đổi đã bị revert | Tạo commit mới áp dụng lại patch đã đảo ngược |
| git reset | Di chuyển HEAD và có thể thay đổi index/working tree tùy tùy chọn | Có thể viết lại lịch sử nhánh hiện tại |

Với lịch sử đã chia sẻ cho nhóm, revert thường là cách rõ ràng để ghi nhận một lần hoàn tác mà không xóa commit cũ khỏi đồ thị. Reset có thể phù hợp cho công việc cục bộ chưa chia sẻ, nhưng cần hiểu rõ tác động trước khi dùng trên nhánh chung.

Không thể dùng git revert -m cho một commit không phải merge commit. Nếu Git báo commit không phải merge, hãy kiểm tra số parent và chọn thao tác phù hợp.

## Những tình huống cần cân nhắc trước khi revert merge

### Merge commit đã được các nhánh khác dựa vào

Nếu nhiều nhánh khác đã lấy commit từ merge hoặc dựa trên nội dung được hợp nhất, revert có thể làm thay đổi hành vi mà các nhánh đó đang mong đợi. Trao đổi với nhóm và xác định các phụ thuộc trước khi hoàn tác.

### Merge đã đưa cả thay đổi tốt và thay đổi lỗi

Revert toàn bộ merge có thể loại bỏ cả phần đúng. Nếu chỉ một phần gây lỗi, cân nhắc tạo commit sửa lỗi hoặc revert có chọn lọc các commit phù hợp nếu cấu trúc lịch sử cho phép. Với merge commit, -m đảo ngược delta tổng thể so với mainline, không phải một bộ lọc chọn từng tệp hay từng commit con.

### Nhánh nguồn tiếp tục phát triển

Sau khi revert merge, các commit cũ vẫn được xem là đã hợp nhất. Hãy thông báo rõ cho người phát triển nhánh nguồn và thống nhất cách khôi phục thay đổi: revert-of-revert, commit mới có chọn lọc hoặc tạo nhánh mới dựa trên trạng thái main hiện tại.

### Merge commit có nhiều parent

Với octopus merge hoặc merge nhiều nhánh, xác định đúng parent cần giữ. -m 1 không phải lúc nào cũng là nhánh phát hành. Dùng git show --pretty=raw hoặc git rev-list --parents để đọc thứ tự parent.

### Merge không tạo merge commit

Nếu thao tác trước đó là fast-forward, sẽ không có merge commit để chọn mainline. Nếu là squash merge, kết quả thường là commit đơn có một parent. Trong các trường hợp đó, hoàn tác commit tương ứng bằng git revert thông thường.

## Quy trình thực hành từ kiểm tra tới xác minh

Ví dụ cần hoàn tác merge commit 7f8a9b0 trên main:

~~~bash
# Kiểm tra trạng thái và nhánh hiện tại
git status
git branch --show-current

# Xem đồ thị lịch sử và các merge commit
git log --oneline --graph --decorate --all
git log --oneline --merges

# Xác định parent của merge commit
git rev-list --parents -n 1 7f8a9b0
git show --no-patch --pretty=raw 7f8a9b0

# Đối chiếu parent và phần thay đổi của merge
git show --no-patch --oneline 111aaaa
git show --no-patch --oneline 222bbbb
git diff 7f8a9b0^1 7f8a9b0

# Khi đã xác nhận parent 1 là main trước merge, hoàn tác
git revert -m 1 7f8a9b0

# Xem commit revert và trạng thái sau thao tác
git status
git log --oneline --graph --decorate -n 12
git show --stat --oneline HEAD

# Chạy kiểm thử và xem phần thay đổi
git diff HEAD^ HEAD
~~~

Nếu revert phát sinh conflict, giải quyết từng tệp, stage kết quả rồi chạy git revert --continue. Nếu quyết định hủy thao tác revert đang dang dở, dùng git revert --abort.

Sau khi hoàn tác, nếu nhóm muốn khôi phục thay đổi ban đầu, xác định commit R vừa tạo rồi xem xét:

~~~bash
git show --stat --oneline R
git revert R
~~~

Thay R bằng mã commit thực tế. Sau khi khôi phục, kiểm tra lịch sử, diff và test trước khi tiếp tục merge các commit mới từ nhánh nguồn.

## Checklist trước và sau khi revert merge

- [ ] Xác định đúng merge commit cần hoàn tác.
- [ ] Kiểm tra số lượng và thứ tự parent.
- [ ] Xác định parent nào là mainline cần giữ.
- [ ] Đảm bảo đang ở nhánh cần nhận commit revert.
- [ ] Kiểm tra working tree và các thay đổi chưa commit.
- [ ] Đọc diff của merge so với mainline.
- [ ] Hiểu phần thay đổi nào sẽ bị đảo ngược.
- [ ] Giải quyết conflict nếu có và stage kết quả đúng.
- [ ] Chạy test cho chức năng bị ảnh hưởng.
- [ ] Xác nhận commit revert mới và trạng thái nhánh.
- [ ] Thông báo hệ quả cho người phát triển nhánh nguồn.
- [ ] Nếu cần hợp nhất lại, lập kế hoạch revert-of-revert hoặc triển khai commit mới có chọn lọc.

## Ghi nhớ

Merge commit có nhiều parent nên cần chỉ rõ mainline khi hoàn tác bằng git revert -m. Trong quy trình merge feature vào main, parent 1 thường là main trước merge, nhưng phải kiểm tra metadata thay vì giả định. Lệnh revert tạo commit mới đảo ngược nội dung của merge và giữ nguyên quan hệ tổ tiên trong lịch sử. Vì vậy, lần merge lại cùng nhánh thường không tự khôi phục các thay đổi cũ đã bị revert; Git chỉ tích hợp các commit mới kể từ merge base. Muốn khôi phục toàn bộ thay đổi, nhóm thường revert commit revert; muốn khôi phục một phần, có thể tạo commit mới có chọn lọc. Luôn kiểm tra parent, diff, phụ thuộc, lịch sử và hành vi ứng dụng trước khi hoàn tất.

