# Dừng trước khi tạo commit bằng git merge --no-commit

Khi hợp nhất một branch, Git thường chuẩn bị snapshot kết quả rồi tạo merge commit ngay nếu hai lịch sử đã phân kỳ. Trong một số tình huống, bạn muốn kiểm tra kết quả kết hợp trước khi commit: xem file nào thay đổi, chạy test, rà soát cấu hình hoặc xác nhận nội dung đã giải quyết conflict. Tùy chọn <code>git merge --no-commit</code> cho phép dừng ở thời điểm đó để bạn quyết định có tạo merge commit hay không.

Điều quan trọng là hiểu đúng điểm dừng: Git đã thực hiện việc kết hợp vào index và working tree, nhưng chưa ghi merge commit và chưa di chuyển branch hiện tại đến commit kết quả. Nếu merge phát sinh conflict, Git cũng dừng để bạn giải quyết. Nếu có thể fast-forward, tùy chọn <code>--no-commit</code> một mình không thể ngăn branch di chuyển, vì fast-forward không tạo merge commit; khi cần kiểm tra trước commit, hãy kết hợp <code>--no-ff --no-commit</code>.

Bài thuộc chương **Hợp nhất nhánh** của module **SOURCE_CONTROL_GIT**. Module hướng dẫn Git từ working tree, staging area, commit và lịch sử đến branch, merge, rebase, remote và tag; đồng thời rèn cách cộng tác qua nhánh, giải quyết xung đột, truy tìm thay đổi và khôi phục thao tác sai mà vẫn bảo toàn lịch sử quan trọng. Nắm được cách dừng merge trước commit giúp bạn kiểm soát snapshot tích hợp và chỉ ghi lịch sử khi đã kiểm tra kết quả.

## 1. git merge thông thường làm gì?

Giả sử bạn đang ở branch <code>main</code> và muốn tích hợp branch <code>feature/payment</code>. Khi lịch sử đã phân kỳ, lệnh:

~~~bash
git switch main
git merge feature/payment
~~~

thường thực hiện các bước:

1. Tìm merge base, tức commit chung làm nền cho việc kết hợp.
2. So sánh snapshot của base, branch hiện tại và branch được merge.
3. Kết hợp các thay đổi vào index và working tree.
4. Nếu không có conflict và merge commit cần thiết, tạo merge commit.
5. Di chuyển branch hiện tại đến merge commit mới.

Ví dụ lịch sử trước merge:

~~~text
          D --- E  feature/payment
         /
A --- B --- C --- F  main
~~~

Nếu merge thành công theo kiểu three-way, Git tạo commit <code>M</code> có hai parent là <code>F</code> và <code>E</code>:

~~~text
          D --- E -----------.
         /                    \
A --- B --- C --- F ----------- M  main
~~~

Merge commit lưu snapshot đã kết hợp. Branch <code>main</code> chuyển từ <code>F</code> đến <code>M</code>; branch nguồn <code>feature/payment</code> vẫn trỏ đến <code>E</code>.

Trong một lần merge thông thường không có conflict, bạn có thể không có cơ hội kiểm tra snapshot cuối cùng trước khi merge commit được tạo. Đây là lúc <code>--no-commit</code> hữu ích.

## 2. --no-commit dừng ở đâu?

Chạy:

~~~bash
git switch main
git merge --no-commit feature/payment
~~~

Nếu cần merge commit, Git thực hiện kết hợp và dừng ngay trước bước tạo commit. Khi đó:

- Branch hiện tại vẫn trỏ đến commit trước merge, ví dụ <code>F</code>.
- <code>HEAD</code> vẫn phân giải về commit hiện tại đó.
- Index chứa kết quả merge đã stage nếu không có conflict.
- Working tree phản ánh nội dung kết quả merge.
- Git giữ trạng thái merge đang chờ hoàn tất, trong đó có thông tin về commit được merge.
- Chưa có merge commit mới trong lịch sử.

Minh họa:

~~~text
Lịch sử branch vẫn như trước:
          D --- E  feature/payment
         /
A --- B --- C --- F  main, HEAD

Index và working tree:
Snapshot kết quả kết hợp F với E
đang chờ được kiểm tra và commit.
~~~

Bạn có thể xem nội dung đã stage:

~~~bash
git status
git diff --cached --stat
git diff --cached
~~~

Sau khi kiểm tra và quyết định chấp nhận kết quả:

~~~bash
git commit
~~~

Git dùng thông tin merge đang chờ để tạo merge commit. Branch hiện tại sau đó mới di chuyển đến commit merge mới.

Nếu quyết định không tiếp tục, có thể hủy merge bằng <code>git merge --abort</code>; phần này được trình bày ở các mục sau.

## 3. Vì sao cần ghép --no-ff với --no-commit?

Đây là điểm dễ nhầm nhất của tùy chọn này.

### Khi merge có thể fast-forward

Giả sử <code>main</code> đang ở <code>C</code>, còn <code>feature</code> có thêm hai commit <code>D</code> và <code>E</code>:

~~~text
A --- B --- C --- D --- E
          main            feature
~~~

Commit <code>C</code> là tổ tiên của <code>E</code>. Git có thể fast-forward bằng cách di chuyển branch <code>main</code> thẳng đến <code>E</code>, không tạo merge commit.

Lệnh sau không đảm bảo dừng trước khi cập nhật branch:

~~~bash
git merge --no-commit feature
~~~

Vì không có merge commit cần tạo, Git có thể fast-forward và cập nhật <code>main</code> ngay. Tùy chọn <code>--no-commit</code> không ngăn thao tác này.

### Buộc tạo điểm dừng trước merge commit

Kết hợp hai tùy chọn:

~~~bash
git merge --no-ff --no-commit feature
~~~

- <code>--no-ff</code> ngăn fast-forward, yêu cầu tạo merge commit ngay cả khi có thể fast-forward.
- <code>--no-commit</code> yêu cầu dừng trước khi tạo merge commit.

Kết quả là Git chuẩn bị merge state để bạn kiểm tra, trong khi branch <code>main</code> vẫn ở commit cũ. Khi bạn chạy <code>git commit</code>, merge commit mới mới được tạo và branch mới tiến lên.

| Tùy chọn | Fast-forward có thể xảy ra? | Có dừng trước merge commit? |
|---|---|---|
| Không có tùy chọn | Có, nếu lịch sử cho phép | Không |
| <code>--no-commit</code> | Có | Không bảo đảm; fast-forward không tạo merge commit |
| <code>--no-ff</code> | Không | Không; merge commit thường được tạo ngay |
| <code>--no-ff --no-commit</code> | Không | Có, nếu merge cần được thực hiện và không bị dừng do lỗi khác |

Nếu hai branch đã ở trạng thái up-to-date và không có gì để tích hợp, Git không tạo merge commit chỉ để thỏa mãn các tùy chọn. <code>--no-commit</code> cũng không biến một lần merge không có thay đổi thành một phiên merge đang chờ.

## 4. Chuẩn bị trước khi merge có kiểm tra

Trước khi chạy merge, xác định branch đích, branch nguồn và trạng thái local.

### Xác nhận branch hiện tại

~~~bash
git branch --show-current
git status --short --branch
~~~

Branch hiện tại là branch sẽ được cập nhật. Nếu bạn muốn tích hợp feature vào <code>main</code>, hãy checkout <code>main</code> trước.

### Kiểm tra thay đổi chưa commit

~~~bash
git diff
git diff --cached
~~~

Nên bắt đầu với working tree và index sạch để việc kiểm tra merge result không bị lẫn với thay đổi cá nhân có từ trước. Nếu có nội dung cần giữ, hãy commit hoặc stash theo quy trình của nhóm trước khi merge.

### Cập nhật remote-tracking refs

Nếu branch nguồn hoặc đích lấy từ remote:

~~~bash
git fetch origin
git branch -vv
~~~

Fetch cập nhật các remote-tracking refs local như <code>origin/main</code> và <code>origin/feature/payment</code>. Nó không tự cập nhật branch local <code>main</code>.

### Kiểm tra phạm vi thay đổi trước merge

~~~bash
git log --oneline --graph --decorate main..feature/payment
git diff --stat main...feature/payment
git diff --name-status main...feature/payment
~~~

Các lệnh này giúp bạn xem commit chỉ có trên feature và phạm vi file thay đổi kể từ điểm tách nhánh. Nếu chưa rõ nội dung, đọc diff chi tiết trước khi bắt đầu merge.

## 5. Quy trình merge và kiểm tra từng bước

Ví dụ muốn merge branch local <code>feature/payment</code> vào <code>main</code> và cần kiểm tra snapshot trước khi tạo commit.

### Bước 1: chuyển đến branch đích

~~~bash
git switch main
~~~

Xác nhận:

~~~bash
git branch --show-current
git status --short
~~~

### Bước 2: chạy merge có điểm dừng

~~~bash
git merge --no-ff --no-commit feature/payment
~~~

Nếu không có conflict, Git chuẩn bị kết quả trong index và working tree rồi dừng trước khi tạo merge commit.

### Bước 3: kiểm tra trạng thái merge

~~~bash
git status
git rev-parse HEAD
git rev-parse MERGE_HEAD
~~~

<code>MERGE_HEAD</code> ghi nhận commit được merge vào trong tiến trình merge đang chờ. Với merge hai branch đơn giản, nó thường phân giải thành tip của branch nguồn tại thời điểm bắt đầu merge. Nếu lệnh <code>rev-parse MERGE_HEAD</code> báo không tìm thấy revision, có thể không có merge đang chờ, ví dụ thao tác đã fast-forward hoặc không có gì để merge.

### Bước 4: xem snapshot đã chuẩn bị

~~~bash
# Tổng quan file thay đổi so với HEAD
git diff --cached --stat

# Loại thay đổi theo file
git diff --cached --name-status

# Nội dung kết quả đã stage
git diff --cached
~~~

Vì Git đã đưa kết quả merge vào index, <code>git diff --cached</code> là lệnh quan trọng để xem snapshot dự kiến sẽ được ghi vào merge commit. <code>git diff</code> chỉ hiển thị phần thay đổi chưa stage so với index; nếu bạn chưa chỉnh gì sau merge thì lệnh này có thể không có output.

### Bước 5: chạy kiểm tra dự án

Chạy các test, build hoặc kiểm tra thủ công phù hợp. Ví dụ:

~~~bash
./gradlew test
~~~

Hoặc với dự án dùng npm:

~~~bash
npm test
~~~

Đây là ví dụ minh họa; hãy dùng lệnh kiểm tra thật của dự án. Nếu test tạo file hoặc sửa file, kiểm tra lại trạng thái để không đưa artifact ngoài ý muốn vào merge commit.

### Bước 6: tạo merge commit khi đã chấp nhận

~~~bash
git status
git diff --cached
git commit
~~~

Git mở editor với merge message mặc định hoặc sử dụng message được chuẩn bị sẵn. Bạn có thể chỉnh message nếu quy ước nhóm cho phép, rồi lưu và đóng editor.

Kiểm tra sau commit:

~~~bash
git log --oneline --graph --decorate -5
git show --stat --oneline HEAD
git status
~~~

Branch <code>main</code> lúc này trỏ đến merge commit mới. Working tree nên sạch nếu không có thay đổi phát sinh sau merge.

## 6. Kiểm tra những gì đã stage sau merge

Trong một merge không có conflict, Git thường ghi kết quả kết hợp vào index ở trạng thái stage 0. Vì vậy:

~~~bash
git diff --cached
~~~

cho biết khác biệt giữa index và HEAD hiện tại. Đây là nội dung được ghi vào commit nếu bạn hoàn tất merge.

Các lệnh hữu ích khác:

~~~bash
# Danh sách file và trạng thái
git diff --cached --name-status

# Thống kê theo file
git diff --cached --stat

# Kiểm tra whitespace error
git diff --cached --check

# Xem index ở dạng stage
git ls-files --stage
~~~

Nếu đã chỉnh file sau khi merge nhưng chưa stage lại, thay đổi mới nằm trong working tree. Khi đó:

~~~bash
git diff
git diff --cached
~~~

cho thấy hai phần khác nhau: phần đã nằm trong index và phần sửa thêm sau đó. Hãy quyết định có đưa phần sửa thêm vào merge commit hay không trước khi commit.

## 7. Khi merge phát sinh conflict

<code>--no-commit</code> không có nghĩa Git luôn chuẩn bị được một kết quả hoàn chỉnh. Nếu hai branch sửa cùng vùng hoặc có thay đổi không thể kết hợp tự động, Git dừng ở trạng thái conflict để bạn giải quyết.

Kiểm tra:

~~~bash
git status
git diff --name-only --diff-filter=U
git ls-files -u
~~~

Các file chưa giải quyết có thể xuất hiện trong index ở nhiều stage:

| Stage | Nội dung |
|---|---|
| 1 | Merge base |
| 2 | Ours, tức phiên bản từ branch hiện tại |
| 3 | Theirs, tức phiên bản từ branch được merge |

Khi conflict, không có entry stage 0 hoàn chỉnh cho đường dẫn đó cho đến khi bạn giải quyết và stage kết quả.

### Đọc conflict marker

Trong file văn bản, Git có thể chèn marker:

~~~text
<<<<<<< HEAD
Nội dung từ branch hiện tại
=======
Nội dung từ branch được merge
>>>>>>> feature/payment
~~~

Hãy xem đây là gợi ý về hai phía, không phải quy tắc bắt buộc chọn nguyên một phía. Bạn có thể kết hợp cả hai, chỉnh lại logic hoặc viết nội dung mới để giữ đúng hành vi mong muốn.

### Giải quyết và stage file

Sau khi sửa nội dung:

~~~bash
git add src/payment/PaymentService.java
~~~

Kiểm tra không còn unmerged entries:

~~~bash
git diff --name-only --diff-filter=U
git status
~~~

Sau khi tất cả conflict được giải quyết, kiểm tra snapshot kết quả:

~~~bash
git diff --cached --check
git diff --cached --stat
git diff --cached
~~~

Chạy test phù hợp rồi tạo merge commit:

~~~bash
git commit
~~~

Không commit khi vẫn còn file unmerged. Nếu muốn bỏ toàn bộ merge đang dở và quay lại trạng thái trước khi merge, xem <code>git merge --abort</code>.

## 8. --no-commit không phải là --squash

Hai tùy chọn đều có thể để bạn kiểm tra nội dung trước khi tạo commit, nhưng kết quả lịch sử khác nhau.

| Tiêu chí | <code>--no-commit</code> | <code>--squash</code> |
|---|---|---|
| Mục đích | Dừng trước khi tạo merge commit | Chuẩn bị thay đổi của nhánh nguồn như một thay đổi để commit gộp |
| Giữ thông tin merge parent | Có, khi hoàn tất merge commit | Không |
| Merge state | Có trạng thái merge đang chờ, thường có <code>MERGE_HEAD</code> | Không ghi nhận merge parent như một merge thông thường |
| Commit sau đó | Merge commit có parent của các lịch sử được kết hợp | Commit thường có một parent là HEAD hiện tại |
| Cách hoàn tất | <code>git commit</code> | <code>git commit</code> để tạo commit thường |

Ví dụ squash:

~~~bash
git switch main
git merge --squash feature/payment
git diff --cached
git commit -m "Add payment retry support"
~~~

Commit cuối chứa thay đổi của feature nhưng không ghi quan hệ parent đến tip feature như merge commit. Hãy chọn squash khi muốn gom thay đổi thành một commit tuyến tính theo quy ước nhóm; chọn <code>--no-commit</code> khi muốn tạo merge commit nhưng cần kiểm tra trước khi ghi nó.

## 9. Phân biệt --no-commit với --no-ff

Hai tùy chọn giải quyết hai vấn đề khác nhau:

- <code>--no-ff</code> điều khiển cách Git tích hợp lịch sử, ngăn fast-forward để tạo merge commit.
- <code>--no-commit</code> điều khiển thời điểm tạo merge commit, dừng trước bước ghi commit.

Ví dụ:

~~~bash
git merge --no-ff --no-commit feature/payment
~~~

Lệnh này vừa yêu cầu giữ merge node, vừa cho phép review kết quả trước khi tạo node đó.

Nếu chỉ chạy:

~~~bash
git merge --no-ff feature/payment
~~~

Git vẫn tạo merge commit ngay sau khi kết hợp thành công, không chờ bạn review thủ công.

Nếu chỉ chạy:

~~~bash
git merge --no-commit feature/payment
~~~

Git có thể fast-forward nếu lịch sử cho phép, và khi đó không có merge commit để dừng trước.

## 10. Hủy merge hoặc thoát khỏi trạng thái merge

Nếu kết quả merge không đúng hoặc bạn muốn làm lại từ đầu, có thể dùng:

~~~bash
git merge --abort
~~~

Lệnh này cố gắng đưa index và working tree về trạng thái trước khi merge bắt đầu. Nó đặc biệt hữu ích khi đang xử lý conflict hoặc đang ở trạng thái merge chờ commit.

Nếu muốn kết thúc việc theo dõi trạng thái merge nhưng giữ nguyên index và working tree hiện tại, có:

~~~bash
git merge --quit
~~~

Hai lệnh không giống nhau:

| Lệnh | Tác động |
|---|---|
| <code>git merge --abort</code> | Hủy merge và cố gắng khôi phục trạng thái trước merge |
| <code>git merge --quit</code> | Xóa trạng thái merge đang theo dõi nhưng giữ index và working tree |

<code>--quit</code> không phải lựa chọn thay thế an toàn cho abort nếu bạn muốn bỏ kết quả merge. Nó có thể để lại file đã kết hợp hoặc conflict trong working tree/index mà không còn metadata merge để tiếp tục.

### Lưu ý về thay đổi local trước merge

Git khuyến nghị không bắt đầu merge khi đang có thay đổi chưa commit mà có thể bị ghi đè. Trong một số trường hợp, Git có thể giữ lại thay đổi local, nhưng <code>git merge --abort</code> không phải lúc nào cũng khôi phục hoàn hảo nếu trước merge đã có nội dung chưa commit phức tạp.

Vì vậy, trước khi chạy merge có điểm dừng:

1. Kiểm tra <code>git status</code>.
2. Commit hoặc stash nội dung cần giữ.
3. Chạy merge.
4. Nếu hủy, kiểm tra lại working tree và index bằng <code>git status</code>.

## 11. Kiểm tra trạng thái merge bằng các dấu hiệu nội bộ

Trong lúc merge đang chờ hoàn tất, Git giữ metadata cho biết tiến trình đang diễn ra. Bạn có thể kiểm tra qua lệnh Git:

~~~bash
# Xem trạng thái repository
git status

# Xem commit nguồn của merge đang chờ
git rev-parse -q --verify MERGE_HEAD

# Xem commit hiện tại trước khi merge commit được tạo
git rev-parse HEAD

# Xem các file còn conflict
git diff --name-only --diff-filter=U
~~~

Không chỉnh sửa hoặc xóa thủ công các file trạng thái trong thư mục <code>.git</code>. Hãy dùng lệnh merge/commit/abort để Git cập nhật metadata nhất quán.

Trong merge nhiều đầu vào hoặc các tình huống phức tạp, có thể có nhiều thông tin parent hơn một merge hai branch đơn giản. Đừng giả định <code>MERGE_HEAD</code> luôn chỉ có một dòng; dùng các lệnh Git để quan sát thay vì viết script dựa vào cấu trúc file nội bộ.

## 12. Dùng merge --no-commit trong quy trình review

Ví dụ nhóm yêu cầu kiểm tra test và file cấu hình trước khi merge feature:

~~~bash
# Cập nhật remote-tracking refs
git fetch origin

# Đảm bảo đang ở branch đích và working tree sạch
git switch main
git status --short

# Xem trước phạm vi thay đổi
git diff --stat origin/main...feature/payment
git diff --name-status origin/main...feature/payment

# Chuẩn bị merge nhưng chưa tạo merge commit
git merge --no-ff --no-commit feature/payment

# Xem snapshot đã stage
git diff --cached --check
git diff --cached --stat
git diff --cached

# Chạy test dự án
./gradlew test

# Nếu đạt yêu cầu, tạo merge commit
git commit
~~~

Nếu test thất bại hoặc phát hiện thay đổi không được chấp nhận:

~~~bash
git merge --abort
git status
~~~

Sau đó quay lại branch nguồn để chỉnh sửa, hoặc trao đổi với người tạo branch. Không tiếp tục commit chỉ vì Git đã chuẩn bị xong snapshot; merge commit nên phản ánh kết quả mà nhóm đã chấp nhận.

## 13. Các tình huống không có merge commit để dừng

<code>--no-commit</code> chỉ có ý nghĩa khi Git đang chuẩn bị tạo merge commit. Có những trường hợp lệnh merge không tạo commit:

| Tình huống | Kết quả |
|---|---|
| Branch nguồn đã được tích hợp, không có thay đổi mới | Git báo up to date; không có merge state để chờ |
| Fast-forward được phép | Branch đích có thể di chuyển trực tiếp; <code>--no-commit</code> không chặn |
| Dùng <code>--no-ff --no-commit</code> khi fast-forward có thể xảy ra | Git tạo merge state và dừng trước merge commit |
| Merge bị conflict | Git dừng để giải quyết conflict; chưa tạo merge commit |
| Merge bị từ chối vì trạng thái local không an toàn | Git không thực hiện merge; xử lý working tree/index rồi thử lại |
| Merge bị hủy bằng <code>--abort</code> | Quay lại trạng thái trước merge trong phạm vi Git có thể khôi phục |

## 14. Những lỗi và nhầm lẫn thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| <code>--no-commit</code> nhưng branch đã tiến lên | Merge đã fast-forward | Dùng thêm <code>--no-ff</code> |
| Không thấy <code>MERGE_HEAD</code> | Merge đã fast-forward, up-to-date hoặc không còn merge đang chờ | Kiểm tra log, branch và status |
| <code>git diff</code> không hiển thị kết quả merge | Kết quả đã nằm trong index | Dùng <code>git diff --cached</code> |
| <code>git commit</code> báo còn unmerged files | Chưa giải quyết hết conflict | Kiểm tra <code>git diff --name-only --diff-filter=U</code> |
| Merge commit được tạo ngay dù muốn review | Thiếu <code>--no-commit</code> | Dùng <code>--no-ff --no-commit</code> trong lần merge tiếp theo |
| Dùng <code>--squash</code> nhưng mong có hai parent | Squash không tạo merge parent relationship | Dùng merge thông thường với <code>--no-commit</code> nếu cần merge commit |
| Dùng <code>--quit</code> nhưng nghĩ đã khôi phục trước merge | Quit chỉ xóa merge state, giữ index/working tree | Dùng <code>--abort</code> khi cần hủy kết quả merge |
| Abort xong vẫn thấy thay đổi local | Có thay đổi trước merge hoặc dữ liệu không thể tự khôi phục hoàn toàn | Kiểm tra diff, stash/backup và trạng thái trước khi tiếp tục |
| Merge bị từ chối vì local changes | Working tree/index có nội dung có thể bị ghi đè | Commit hoặc stash thay đổi cần giữ rồi thử lại |

## 15. Checklist trước khi tạo merge commit

Trước khi chạy merge:

- Xác nhận branch đích bằng <code>git branch --show-current</code>.
- Xác nhận branch nguồn và cập nhật remote-tracking refs nếu cần.
- Kiểm tra working tree và index.
- Xem trước commit và file sẽ được tích hợp.
- Quyết định có cần giữ merge commit hay muốn squash.

Trong lúc merge đang chờ:

- Kiểm tra <code>git status</code> và <code>MERGE_HEAD</code>.
- Dùng <code>git diff --cached</code> để xem snapshot đã chuẩn bị.
- Giải quyết tất cả unmerged entries nếu có.
- Chạy test/build và kiểm tra whitespace.
- Xác nhận không có thay đổi ngoài ý muốn được đưa vào index.

Trước khi hoàn tất:

- Đọc lại staged diff.
- Xác nhận message merge phù hợp.
- Chạy <code>git commit</code> khi đã chấp nhận.
- Kiểm tra đồ thị commit và working tree sau merge.

## 16. Bài tập tự kiểm tra

Thực hành trong repository thử nghiệm có hai branch:

1. Tạo branch feature có hai commit đi sau main và chạy <code>git merge --no-commit</code>; quan sát Git có thể fast-forward.
2. Reset repository thử nghiệm về trạng thái ban đầu rồi chạy <code>git merge --no-ff --no-commit</code>; xác nhận branch đích chưa di chuyển.
3. Dùng <code>git status</code>, <code>git rev-parse HEAD</code> và <code>git rev-parse MERGE_HEAD</code> để xác nhận merge đang chờ.
4. Dùng <code>git diff --cached --stat</code> và <code>git diff --cached</code> để kiểm tra snapshot.
5. Tạo một thay đổi local sau khi merge đã chuẩn bị, rồi phân biệt output của <code>git diff</code> và <code>git diff --cached</code>.
6. Hoàn tất merge bằng <code>git commit</code> và xem merge commit có hai parent.
7. Lặp lại trong repository thử nghiệm khác, nhưng hủy bằng <code>git merge --abort</code>.
8. So sánh trạng thái sau <code>git merge --abort</code> và <code>git merge --quit</code>; chỉ thực hiện khi hiểu rõ dữ liệu sẽ còn lại.
9. Tạo conflict có chủ đích, giải quyết, stage và hoàn tất merge.
10. Thử <code>git merge --squash</code> và so sánh parent của commit kết quả với merge commit thông thường.
11. Viết quy trình review merge cho nhóm, xác định khi nào bắt buộc chạy test trước commit.

<code>git merge --no-commit</code> tạo một khoảng dừng để bạn kiểm tra kết quả kết hợp trước khi ghi merge commit. Hãy nhớ ghép <code>--no-ff</code> khi cần ngăn fast-forward, kiểm tra snapshot bằng <code>git diff --cached</code>, giải quyết hết conflict và chỉ commit sau khi đã chấp nhận kết quả.
