# Kiểm tra tính toàn vẹn bằng git fsck và tìm đối tượng không còn được tham chiếu

Git lưu commit, tree, blob và tag thành các object trong object database. Các branch, tag và những tham chiếu khác giúp Git tìm đến các object đó. Khi lịch sử bị viết lại, nhánh bị xóa hoặc một thao tác phục hồi chưa hoàn tất, object vẫn có thể còn trong repository nhưng không còn được tham chiếu từ những điểm bắt đầu quen thuộc.

Lệnh **git fsck** kiểm tra tính hợp lệ và khả năng kết nối của object database. Nó giúp phát hiện object bị thiếu, liên kết hỏng, dữ liệu không hợp lệ và tìm những object không còn reachable như commit, tree hoặc blob. Đây là công cụ chẩn đoán quan trọng khi điều tra repository bất thường hoặc tìm lại commit sau reset, amend, rebase hay xóa nhánh.

Trong chương **Tìm lỗi và phục hồi** của module **SOURCE_CONTROL_GIT**, bài học này hướng dẫn cách đọc kết quả fsck, phân biệt object dangling với unreachable, lần theo nội dung còn sót và tạo tham chiếu cứu hộ khi tìm được commit cần giữ. Mục tiêu là kiểm tra có phương pháp và bảo toàn object trước khi chúng bị dọn khỏi repository.

Sau bài học, bạn có thể:

- Giải thích object database và các loại object cơ bản của Git.
- Chạy fsck để kiểm tra tính toàn vẹn và kết nối.
- Phân biệt dangling object, unreachable object và object bị thiếu hoặc hỏng.
- Hiểu vai trò của refs, index và reflog khi Git xác định object có thể truy cập.
- Kiểm tra commit, tree và blob tìm được bằng các lệnh cat-file, show và ls-tree.
- Tạo nhánh cứu hộ hoặc lưu nội dung cần thiết mà không làm mất dấu object gốc.
- Nhận biết khi nào cần lấy lại object từ remote hoặc bản sao lưu.

## 1. Git lưu dữ liệu trong object database

Git không lưu lịch sử chỉ bằng tên file hoặc một danh sách thay đổi. Nội dung được lưu thành các object có mã định danh dựa trên hash của nội dung và metadata.

Các loại object chính:

| Loại object | Chứa gì? | Ví dụ sử dụng |
| --- | --- | --- |
| **blob** | Nội dung của một file, không lưu tên file hoặc đường dẫn | Nội dung source code, tài liệu hoặc binary |
| **tree** | Danh sách entry gồm tên, mode và object được tham chiếu | Cấu trúc thư mục và file tại một snapshot |
| **commit** | Tham chiếu đến tree gốc, parent commit và metadata commit | Một điểm trong lịch sử phát triển |
| **tag** | Metadata của annotated tag và object mà tag trỏ tới | Mốc phiên bản có thông điệp hoặc chữ ký |

Ví dụ, một commit thường trỏ đến một tree; tree trỏ đến các blob và tree con; commit còn trỏ đến parent commit:

~~~text
        commit C
        /      \
   parent B   tree T
                |
          +-----+------+
          |            |
       blob A       tree src
                         |
                       blob B
~~~

Branch và tag là các tham chiếu có tên đến object. Chúng giúp Git xác định các điểm bắt đầu để lần theo lịch sử và nội dung. Reflog ghi lại một số lần tham chiếu local được cập nhật. Index cũng có thể giữ tham chiếu đến blob đang được stage.

Khi một branch bị xóa hoặc di chuyển, object cũ có thể không còn được branch đó tham chiếu. Điều đó không có nghĩa object biến mất ngay lập tức. Nó có thể còn trong object database và có thể được tìm lại cho đến khi Git dọn các object không còn cần thiết.

## 2. git fsck kiểm tra điều gì?

Tên fsck bắt nguồn từ khái niệm kiểm tra tính nhất quán của hệ thống file. Trong Git, lệnh này kiểm tra object database và các liên kết giữa object.

Chạy kiểm tra cơ bản:

~~~bash
git fsck
~~~

Có thể yêu cầu kiểm tra đầy đủ:

~~~bash
git fsck --full
~~~

fsck kiểm tra object có đọc được và có cấu trúc hợp lệ hay không, đồng thời kiểm tra các liên kết cần thiết để xây dựng lịch sử và snapshot. Tùy trạng thái repository, kết quả có thể gồm:

- Object hợp lệ và kết nối được.
- Object dangling không được object khác sử dụng trực tiếp theo cách Git xác định.
- Object unreachable không thể đi tới từ các root được tính trong lần kiểm tra.
- Object bị thiếu, liên kết trỏ đến object không tồn tại hoặc dữ liệu object không khớp hash.

Mặc định, fsck thường chỉ in các object dangling thay vì liệt kê toàn bộ object unreachable. Nó có thể không in gì khi không phát hiện vấn đề cần báo. Không có output không đồng nghĩa mọi file trong working tree đều đúng; fsck tập trung vào object database, không thay thế test, kiểm tra file ngoài Git hoặc kiểm tra nội dung ứng dụng.

Có thể bật kiểm tra nghiêm ngặt hơn:

~~~bash
git fsck --full --strict
~~~

Tùy chọn strict yêu cầu Git kiểm tra thêm một số điều kiện về định dạng object. Nó hữu ích khi kiểm tra repository có dấu hiệu hỏng hoặc khi cần rà soát chất lượng object kỹ hơn.

## 3. Hiểu reachable, unreachable và dangling

Ba thuật ngữ này mô tả cách object liên hệ với các điểm bắt đầu và object khác.

### Reachable

Một object reachable nếu Git có thể đi đến nó từ các root được tính trong lần kiểm tra, chẳng hạn refs, index và reflogs theo cấu hình mặc định. Ví dụ, commit ở đầu branch và mọi object cần thiết để dựng snapshot của commit đó đều reachable.

~~~text
main -> commit C -> tree T -> blob A
                    |
                    +------> blob B
~~~

Từ branch main, Git có thể lần theo commit, tree và blob để dựng lại snapshot.

### Unreachable

Object unreachable nếu Git không thể đi đến nó từ các root đang được tính trong lần kiểm tra. Ví dụ, sau khi di chuyển branch khỏi một commit cũ, commit đó và một phần object chỉ được lịch sử cũ sử dụng có thể trở thành unreachable.

~~~text
main -> commit D -> tree mới

commit C -> tree cũ -> blob cũ
   ^
   không còn branch hoặc root đang xét trỏ tới
~~~

Unreachable không có nghĩa object đã bị xóa. Nó vẫn có thể tồn tại trong object database và được khôi phục nếu chưa bị garbage collection dọn đi.

### Dangling

Dangling mô tả object tồn tại nhưng không được object khác sử dụng trực tiếp theo cách fsck xác định. Trong các tình huống phục hồi thường gặp, đó thường là commit đầu mút của một lịch sử đã bị bỏ khỏi branch. Khái niệm này nói về việc object có được object khác dùng trực tiếp hay không; đừng đồng nhất tùy chọn --dangling với --unreachable vì hai tùy chọn báo cáo theo tiêu chí khác nhau.

~~~text
main -> A---B---D

        C---E
            ^
       commit E dangling
~~~

Trong ví dụ, commit E không còn được branch nào tham chiếu. Nếu E là đầu mút của một chuỗi commit không reachable, nó có thể được báo là dangling commit. Những commit cha, tree và blob nằm trong chuỗi đó cũng có thể unreachable nhưng không nhất thiết từng object đều được báo dangling.

Vì vậy:

- **Unreachable**: object không thể đi tới từ các root được xét.
- **Dangling**: object không được object khác sử dụng trực tiếp; trong tình huống phục hồi lịch sử, nó thường là đầu mút của một chuỗi unreachable.
- Một object dangling có thể là commit, tag, tree hoặc blob; không phải mọi dangling object đều là commit có thể checkout.

## 4. Các root ảnh hưởng đến kết quả fsck

Kết quả fsck phụ thuộc những điểm bắt đầu Git dùng để tính reachable.

Thông thường, Git xét các tham chiếu như branch, tag và một số tham chiếu khác; index và reflog cũng có thể giữ object reachable. Điều này giải thích vì sao một commit sau reset đôi khi chưa xuất hiện trong danh sách unreachable: reflog vẫn còn ghi nhận vị trí HEAD trước đó.

Để kiểm tra cả object chỉ còn được giữ bởi reflog, có thể yêu cầu bỏ qua reflog khi tính reachable:

~~~bash
git fsck --full --no-reflogs --unreachable
~~~

Tùy chọn **--no-reflogs** khiến fsck không tính các commit chỉ được tham chiếu bởi reflog là reachable. Lệnh này hữu ích khi tìm object sau reset hoặc rebase. Nó có thể liệt kê nhiều object hơn so với lần chạy mặc định.

Nếu chỉ muốn xem các object unreachable:

~~~bash
git fsck --unreachable
~~~

Nếu muốn xem các object dangling mà không liệt kê toàn bộ unreachable, có thể chạy:

~~~bash
git fsck --dangling
~~~

Đây cũng là nhóm thông tin fsck thường báo mặc định. Có thể ẩn thông báo dangling khi cần tập trung vào lỗi khác:

~~~bash
git fsck --no-dangling
~~~

Không nên so sánh kết quả của hai lần fsck nếu tùy chọn root khác nhau mà không ghi nhận điều đó. Một object có thể reachable trong lần kiểm tra mặc định nhưng trở thành unreachable khi thêm --no-reflogs.

## 5. Chạy fsck và đọc kết quả

### Kiểm tra ban đầu

~~~bash
git status -sb
git fsck --full
~~~

Lệnh status cho biết branch và thay đổi trong working tree; fsck kiểm tra object database. Hai lệnh phục vụ hai mục đích khác nhau và nên được đọc cùng nhau khi điều tra.

Một số dạng kết quả thường gặp:

~~~text
dangling commit 0123456789abcdef...
dangling blob abcdef0123456789...
unreachable commit 1234567890abcdef...
missing blob fedcba9876543210...
broken link from tree 0123... to blob 4567...
~~~

Ý nghĩa tổng quát:

| Thông báo | Cách hiểu |
| --- | --- |
| dangling commit | Có commit không còn được tham chiếu và không được object khác sử dụng trực tiếp theo cách fsck xác định. Có thể là đầu mút của lịch sử cũ. |
| dangling blob | Có nội dung file không được object khác sử dụng trực tiếp theo cách fsck xác định. Blob không chứa tên file nên cần điều tra thêm. |
| unreachable commit | Commit không thể đi tới từ các root đang được xét. Nó có thể là một commit giữa chuỗi lịch sử unreachable. |
| missing blob | Một object cần thiết được tham chiếu nhưng không tìm thấy trong object database. Đây là dấu hiệu cần điều tra tính toàn vẹn. |
| broken link | Một object có liên kết đến object đích không tồn tại hoặc không hợp lệ. |

Thông báo cụ thể và thứ tự dòng có thể khác theo phiên bản Git và trạng thái repository. Hãy giữ lại hash object để kiểm tra tiếp.

### Phân biệt cảnh báo với lỗi hỏng dữ liệu

Dangling hoặc unreachable object thường xuất hiện sau các thao tác hợp lệ như amend commit, rebase, reset, xóa branch hoặc tạo lại commit. Chúng không tự động chứng minh repository bị hỏng.

Missing object, broken link, hash mismatch hoặc lỗi đọc object đáng quan tâm hơn. Chúng có thể chỉ ra object database không đầy đủ hoặc dữ liệu bị hỏng. Hãy lưu log fsck, xác định object nào bị ảnh hưởng và kiểm tra bản sao khác trước khi sửa.

## 6. Tìm object không còn được tham chiếu

Khi mục tiêu là tìm commit hoặc file cũ sau một thao tác viết lại lịch sử, dùng:

~~~bash
git fsck --full --no-reflogs --unreachable
~~~

Lệnh này có thể trả về nhiều loại object. Tập trung tìm các dòng unreachable commit trước, sau đó kiểm tra object liên quan.

Nếu chỉ cần tìm commit dangling:

~~~bash
git fsck --full --no-reflogs --dangling
~~~

Ví dụ output:

~~~text
dangling commit 9a1b2c3d4e5f...
dangling commit 7f8e9d0c1b2a...
~~~

Các hash là ví dụ minh họa. Đừng chọn commit chỉ dựa trên hash hoặc ngày tạo; hãy xem nội dung và parent để xác định lịch sử nào cần phục hồi.

## 7. Kiểm tra dangling commit

Commit là loại object thuận tiện nhất để phục hồi vì nó chứa tham chiếu đến tree và parent commit.

Xem thông tin commit:

~~~bash
git show --no-patch --format=fuller <commit-hash>
git show --stat <commit-hash>
~~~

Đọc thông điệp, tác giả, ngày tạo, parent và danh sách file thay đổi. Để xem lịch sử bắt đầu từ commit đó:

~~~bash
git log --oneline --graph --decorate <commit-hash>
~~~

Nếu commit có nhiều parent, đó có thể là merge commit. Kiểm tra cả đồ thị và nội dung để tránh khôi phục nhầm một nhánh lịch sử khác.

Xem diff của commit:

~~~bash
git show --format=fuller --no-ext-diff <commit-hash>
~~~

Nếu đã xác định đây là commit cần giữ, tạo branch cứu hộ:

~~~bash
git branch rescue/recovered-work <commit-hash>
~~~

Branch mới tạo một ref trỏ đến commit, giúp commit và lịch sử tổ tiên của nó reachable trở lại. Sau đó có thể checkout nhánh cứu hộ, cherry-pick các commit cần thiết hoặc so sánh với nhánh hiện tại.

Nếu muốn chuyển nhánh hiện tại về commit đó, hãy xác minh kỹ trước khi reset. Tạo branch cứu hộ trước giúp giữ lại mốc tìm được ngay cả khi quyết định tiếp theo chưa đúng.

## 8. Kiểm tra dangling tree và blob

Không phải object tìm được nào cũng là commit. Khi chỉ còn tree hoặc blob, bạn vẫn có thể xem nội dung nhưng cần xác định file và đường dẫn theo cách khác.

### Kiểm tra loại và kích thước object

~~~bash
git cat-file -t <object-hash>
git cat-file -s <object-hash>
~~~

Lệnh đầu trả về loại object như commit, tree, blob hoặc tag. Lệnh thứ hai cho biết kích thước nội dung object.

### Xem tree

~~~bash
git ls-tree <tree-hash>
git ls-tree -r <tree-hash>
~~~

Tree lưu cấu trúc thư mục và các object con. Tùy chọn -r liệt kê đệ quy các entry bên trong. Nếu tree thuộc một snapshot cũ, kết quả giúp tìm đường dẫn và blob tương ứng.

### Xem blob

~~~bash
git cat-file -p <blob-hash>
~~~

Blob chỉ lưu nội dung file, không lưu tên file hoặc đường dẫn. Nếu nội dung là văn bản, có thể đọc để nhận diện. Nếu là binary, không nên in trực tiếp ra terminal; hãy kiểm tra loại, kích thước và ghi nội dung ra một file phục hồi riêng để mở bằng công cụ phù hợp.

Ví dụ lưu blob ra file:

~~~bash
git cat-file blob <blob-hash> > recovered-file
~~~

File recovered-file là bản sao nội dung blob, không tự động được Git quản lý và không chứng minh đường dẫn gốc. Hãy xác định tên, vị trí và phiên bản phù hợp trước khi đưa file vào working tree.

### Tìm blob liên quan đến một commit

Nếu tìm được một dangling commit, hãy ưu tiên kiểm tra tree của commit đó thay vì tìm blob rời rạc:

~~~bash
git show --format=raw --no-patch <commit-hash>
git ls-tree -r <commit-hash>
~~~

Lệnh show cho biết tree hash của commit. Lệnh ls-tree liệt kê file và blob mà snapshot đó sử dụng. Nhờ vậy, bạn có thể xác định đường dẫn của blob từ tree, điều mà bản thân blob không lưu.

## 9. Dùng --lost-found để lưu dấu object tìm được

Tùy chọn **--lost-found** yêu cầu fsck ghi các object dangling ra thư mục lost-found bên trong Git directory:

~~~bash
git fsck --full --no-reflogs --lost-found
~~~

Git thường ghi dangling commit vào thư mục **lost-found/commit** và các loại object khác vào **lost-found/other** bên trong Git directory. Đây là các bản ghi giúp người phát triển mở và kiểm tra nội dung dễ hơn; chúng không tự tạo branch hoặc khôi phục lịch sử vào nhánh đang làm việc.

Đường dẫn Git directory có thể khác nhau giữa repository thường, worktree và môi trường dùng git-dir riêng. Có thể hỏi Git đường dẫn thực tế:

~~~bash
git rev-parse --git-path lost-found
~~~

Sau khi chạy lost-found, kiểm tra các object được ghi và tạo ref cứu hộ cho commit cần giữ. Đừng xem việc có file trong lost-found là đã phục hồi hoàn tất; bạn vẫn cần xác định object, kiểm tra nội dung và tạo tham chiếu ổn định.

## 10. Quy trình điều tra sau reset, rebase hoặc xóa nhánh

Giả sử bạn lỡ reset nhánh feature về commit cũ, sau đó phát hiện một commit chứa thay đổi quan trọng đã rời khỏi đầu nhánh.

### Bước 1: dừng thao tác dọn object

Không chạy git prune, git gc với thời hạn prune bằng 0 hoặc lệnh xóa object trong lúc đang điều tra. Các thao tác này có thể loại bỏ object không còn reachable mà bạn đang muốn phục hồi.

### Bước 2: xem reflog trước

~~~bash
git reflog --date=local
~~~

Reflog thường là nơi nhanh nhất để tìm commit trước lần reset hoặc rebase. Nếu tìm được hash, xem commit và tạo branch cứu hộ.

### Bước 3: dùng fsck nếu reflog không đủ

~~~bash
git fsck --full --no-reflogs --unreachable
~~~

Tìm các commit phù hợp với thời điểm và nội dung công việc. Vì lệnh có thể trả về nhiều object, hãy kiểm tra từng commit bằng show, log và tree.

### Bước 4: xác minh commit và lịch sử

~~~bash
git show --stat <candidate-commit>
git log --oneline --graph <candidate-commit>
~~~

Đối chiếu thông điệp, file thay đổi, parent và nội dung. Nếu đó là commit mong muốn, giữ lại hash.

### Bước 5: tạo branch cứu hộ

~~~bash
git branch rescue/feature-before-reset <candidate-commit>
~~~

Branch này tạo một tham chiếu ổn định đến commit. Kiểm tra:

~~~bash
git show --no-patch --oneline rescue/feature-before-reset
git log --oneline --decorate -8 rescue/feature-before-reset
~~~

### Bước 6: chọn cách đưa thay đổi trở lại

Tùy mục tiêu, bạn có thể:

- Checkout branch cứu hộ để tiếp tục làm việc trên lịch sử cũ.
- Cherry-pick một hoặc nhiều commit cần thiết sang branch hiện tại.
- So sánh tree và file rồi khôi phục có chọn lọc.
- Giữ branch cứu hộ để nhóm review trước khi tích hợp.

Không reset branch chính ngay khi vừa tìm thấy commit. Trước hết hãy giữ object bằng branch cứu hộ, sau đó chọn phương án tích hợp phù hợp.

## 11. Khi fsck báo thiếu hoặc hỏng object

Dangling object thường là kết quả bình thường của việc viết lại lịch sử. Ngược lại, thông báo missing object hoặc broken link cho biết một object được tham chiếu nhưng không thể đọc hoặc không tồn tại tại nơi Git mong đợi.

Quy trình điều tra:

1. Lưu lại toàn bộ output của fsck, gồm hash và loại object.
2. Xác định object bị thiếu là commit, tree, blob hay tag.
3. Kiểm tra repository khác, remote hoặc bản sao lưu có chứa object đó không.
4. Nếu remote có object và ref liên quan, fetch từ nguồn đáng tin cậy.
5. Chạy lại fsck để xác nhận lỗi đã được giải quyết.

Ví dụ kiểm tra object:

~~~bash
git cat-file -t <object-hash>
git cat-file -p <object-hash>
~~~

Nếu object không đọc được, việc chạy fsck lần nữa không thể tự tạo nội dung bị mất. Cần lấy object từ một bản sao repository có dữ liệu hợp lệ hoặc từ backup. Không tự tạo file object bằng cách sửa trực tiếp thư mục .git/objects.

Nếu remote có branch hoặc tag chứa commit cần thiết, có thể fetch tham chiếu tương ứng:

~~~bash
git fetch origin <branch-name>
~~~

Sau khi fetch, kiểm tra lại object và lịch sử. Một remote không chứa commit bị mất sẽ không thể cung cấp object đó; khi ấy cần tìm bản clone khác hoặc backup.

## 12. Bảo toàn object tìm được

Khi tìm thấy commit hoặc object quan trọng, hãy tạo một ref ổn định càng sớm càng tốt. Branch cứu hộ là cách dễ hiểu với commit:

~~~bash
git branch rescue/found-commit <commit-hash>
~~~

Nếu cần giữ một tag object hoặc object không phải commit, cân nhắc tạo một ref phù hợp sau khi đã xác định loại object và quy ước repository. Không tạo branch trỏ đến blob hoặc tree vì branch trong workflow thông thường cần trỏ đến commit.

Giữ lại output fsck và ghi chú hash, loại object, nguồn tìm được và hành động đã thực hiện. Sau khi có ref ổn định, object trở thành reachable qua ref đó và ít có nguy cơ bị dọn như object không còn được tham chiếu.

Không dùng các lệnh sau trong lúc đang tìm cách phục hồi:

~~~bash
git prune
git gc --prune=now
~~~

Prune và garbage collection có thể xóa object unreachable đủ điều kiện dọn. Nếu chưa chắc object nào cần giữ, hãy hoàn tất điều tra và tạo ref cứu hộ trước khi chạy tác vụ dọn dẹp theo lịch.

## 13. Những nhầm lẫn thường gặp

### Có dangling object nghĩa là repository bị hỏng?

Không. Dangling object thường xuất hiện sau amend, rebase, reset hoặc xóa branch. Đây là object không còn được tham chiếu theo cấu trúc hiện tại, chưa chắc là lỗi dữ liệu.

### fsck có tự khôi phục commit không?

Không. Fsck kiểm tra và báo object. Tùy chọn lost-found có thể ghi bản sao object dangling vào thư mục hỗ trợ, nhưng muốn giữ commit trong lịch sử làm việc, bạn cần tạo branch hoặc ref phù hợp.

### Vì sao commit sau reset không xuất hiện trong fsck mặc định?

Commit có thể vẫn reachable qua reflog. Dùng --no-reflogs khi muốn tìm object mà chỉ reflog còn giữ.

### Unreachable và dangling có giống nhau không?

Không. Unreachable là nhóm rộng. Dangling là một trường hợp cụ thể thường không được object khác sử dụng trực tiếp. Một commit giữa chuỗi lịch sử unreachable có thể không được báo dangling vì commit con vẫn trỏ đến nó.

### Blob có cho biết tên file cũ không?

Không. Blob chỉ chứa nội dung. Cần tìm tree hoặc commit tham chiếu đến blob để biết đường dẫn và snapshot liên quan.

### Có thể chạy git gc để dọn dangling object ngay không?

Không nên khi đang điều tra hoặc có khả năng cần phục hồi. Hãy giữ object bằng ref cứu hộ và xác minh dữ liệu trước khi cho phép Git dọn object không còn tham chiếu.

## 14. Tự kiểm tra

Sau một lần rebase nhầm, bạn thấy kết quả:

~~~text
dangling commit 111111...
unreachable commit 222222...
dangling blob 333333...
~~~

Hãy trả lời:

1. Vì sao dangling commit không nhất thiết là lỗi?
2. Vì sao commit 222222 có thể unreachable nhưng không dangling?
3. Lệnh nào xem nội dung và parent của commit 111111?
4. Lệnh nào tạo branch cứu hộ trỏ đến commit cần giữ?
5. Nếu chỉ tìm thấy blob 333333, có thể suy ra tên file gốc từ blob không?
6. Vì sao cần tránh git prune hoặc git gc --prune=now trước khi phục hồi?
7. Nếu fsck báo missing blob, việc tạo branch cứu hộ có tự sửa được lỗi đó không?

**Gợi ý:** Dangling commit có thể là đầu mút của lịch sử cũ sau rebase. Commit 222222 có thể được một commit unreachable khác sử dụng nên không phải dangling. Dùng git show và git log để kiểm tra commit; dùng git branch rescue/recovered 111111 để tạo ref cứu hộ sau khi xác nhận đúng object. Blob không lưu tên file, cần tree hoặc commit để tìm đường dẫn. Prune/gc có thể xóa object unreachable; branch cứu hộ chỉ giữ object còn tồn tại, không thể tự tái tạo blob bị thiếu.

## Kết luận

git fsck giúp kiểm tra object database và phát hiện object dangling, unreachable hoặc liên kết bị thiếu. Khi tìm commit cũ, hãy đọc hash bằng git show, lần theo lịch sử và tạo branch cứu hộ để giữ object reachable. Với tree và blob, cần kiểm tra loại object và lần theo quan hệ trong snapshot để xác định nội dung, đường dẫn. Dangling không đồng nghĩa repository hỏng; missing object hoặc broken link cần được điều tra và lấy lại từ remote hay backup đáng tin cậy. Chỉ chạy prune hoặc garbage collection sau khi đã bảo toàn mọi object cần phục hồi.
