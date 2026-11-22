# Xóa worktree đúng cách và dọn thông tin cũ bằng prune

Git worktree cho phép một repository có nhiều thư mục làm việc cùng lúc. Bạn có thể giữ nhánh main ở thư mục chính, mở một nhánh tính năng trong thư mục thứ hai và dùng thư mục thứ ba để review một nhánh khác. Các worktree chia sẻ dữ liệu Git và lịch sử chung, nhưng mỗi worktree có thư mục làm việc, index và HEAD riêng.

Khi một phần việc kết thúc, cần đóng worktree đúng cách để Git giải phóng thông tin quản lý của nó. Nếu chỉ xóa thư mục bằng File Explorer hoặc lệnh xóa thư mục, Git có thể vẫn giữ metadata của worktree đã mất. Lệnh git worktree prune dùng để dọn những metadata cũ như vậy.

Bài học này trình bày cách kiểm tra trạng thái, loại bỏ một linked worktree an toàn, xử lý worktree còn thay đổi hoặc bị khóa, và dùng prune để làm sạch thông tin còn sót lại.

Sau bài này, bạn có thể:

- Liệt kê worktree và xác định worktree cần xóa.
- Kiểm tra nhánh, commit và thay đổi chưa lưu trong worktree đó.
- Dùng git worktree remove để xóa linked worktree đúng cách.
- Hiểu khi nào cần --force và rủi ro của nó.
- Nhận biết metadata cũ sau khi thư mục worktree bị xóa thủ công.
- Dùng git worktree prune để xem trước và dọn metadata hết hạn.
- Phân biệt việc xóa worktree với việc xóa nhánh Git.

## 1. Worktree gồm những phần nào?

Một repository có thể có worktree chính và nhiều linked worktree:

~~~text
project/
|-- .git/
|-- src/
|-- README.md
|
../project-feature/
|-- .git              <- file trỏ về metadata của linked worktree
|-- src/
|-- README.md
|
../project-review/
|-- .git              <- file trỏ về metadata của linked worktree
|-- src/
|-- README.md
~~~

Worktree chính thường chứa thư mục .git của repository. Trong một linked worktree, mục .git thường là một file trỏ tới thư mục quản trị tương ứng bên trong repository chính, thường ở .git/worktrees/ID.

Các worktree dùng chung object database và các tham chiếu branch/tag của repository. Mỗi worktree có HEAD và index riêng, nên bạn có thể checkout các nhánh khác nhau và stage thay đổi độc lập ở từng thư mục.

Ví dụ:

| Worktree | Nhánh đang checkout | Vai trò |
| --- | --- | --- |
| project | main | Công việc chính |
| project-feature | feature/search | Phát triển tính năng |
| project-review | bugfix/session-timeout | Review hoặc sửa lỗi |

Một branch thông thường chỉ có thể được checkout trong một worktree tại một thời điểm. Quy tắc này giúp tránh hai thư mục cùng cập nhật một nhánh theo cách gây nhầm lẫn. Worktree có thể ở trạng thái detached HEAD nếu không checkout một branch.

Xóa một linked worktree không xóa repository dùng chung và cũng không tự xóa branch mà worktree đó đang checkout.

## 2. Liệt kê và xác định đúng worktree

Trước khi xóa, hãy xem tất cả worktree mà repository đang quản lý:

~~~bash
git worktree list
~~~

Để nhận kết quả dạng máy có thể phân tích, dùng:

~~~bash
git worktree list --porcelain
~~~

Kết quả dạng dễ đọc có thể trông như sau:

~~~text
worktree C:/dev/project
HEAD 7a21d3f...
branch refs/heads/main

worktree C:/dev/project-feature
HEAD 9b82e10...
branch refs/heads/feature/search

worktree C:/dev/project-review
HEAD 4f10c2a...
detached
~~~

Mỗi khối bắt đầu bằng worktree và đường dẫn thư mục. Các dòng tiếp theo cho biết commit HEAD, branch đang checkout hoặc trạng thái detached. Kết quả thực tế có thể chứa thêm thông tin như locked hoặc prunable.

Đừng dựa riêng vào tên thư mục. Hãy xác nhận:

- Đường dẫn có đúng worktree bạn định kết thúc không?
- Worktree đang checkout branch nào hoặc đang ở detached HEAD?
- Có thay đổi chưa commit hoặc tệp chưa được theo dõi không?
- Có người khác hoặc tiến trình build/test đang sử dụng thư mục đó không?

Nếu đang ở thư mục chính, có thể kiểm tra worktree khác mà không cần chuyển terminal:

~~~bash
git -C ../project-feature status --short --branch
git -C ../project-feature log --oneline -n 8
~~~

Tùy chọn -C yêu cầu Git thực hiện lệnh như thể đang chạy từ thư mục được chỉ định. Trên Windows, có thể dùng đường dẫn tuyệt đối hoặc đường dẫn tương đối phù hợp với vị trí terminal hiện tại.

## 3. Kiểm tra và bảo toàn công việc trước khi xóa

Lệnh remove thông thường chỉ xóa worktree khi nó sạch. Vì vậy, hãy kiểm tra trạng thái của chính worktree cần xóa:

~~~bash
git -C ../project-feature status --short --branch
~~~

Nếu có thay đổi, hãy quyết định giữ lại chúng trước khi xóa:

- Commit nếu phần việc đã hoàn tất và nên trở thành một phần của lịch sử.
- Stash nếu cần cất tạm thay đổi theo quy trình của nhóm.
- Tạo patch hoặc sao lưu tệp nếu cần chuyển nội dung sang nơi khác.
- Bỏ thay đổi chỉ khi đã xác nhận chúng không còn cần thiết.

Kiểm tra cả tệp chưa được theo dõi và tệp bị ignore nếu chúng chứa dữ liệu quan trọng. Trạng thái Git không phải lúc nào cũng hiển thị mọi tệp bị ignore; có thể cần xem thư mục bằng trình quản lý tệp hoặc lệnh liệt kê phù hợp.

Ví dụ, nếu muốn giữ một thay đổi đã hoàn tất:

~~~bash
git -C ../project-feature add src/SearchService.java
git -C ../project-feature commit -m "Add search service"
~~~

Sau đó kiểm tra lại:

~~~bash
git -C ../project-feature status --short --branch
~~~

Nếu cần stash:

~~~bash
git -C ../project-feature stash push -u -m "Save feature work before removing worktree"
~~~

Tùy chọn -u đưa cả tệp chưa được theo dõi vào stash. Các tệp bị ignore không được đưa vào stash với -u; nếu cần giữ chúng, hãy sao lưu hoặc dùng lựa chọn phù hợp sau khi kiểm tra nội dung. Stash được lưu trong repository chung và có thể được áp dụng từ worktree khác.

Không xóa worktree khi chưa biết thay đổi nào sẽ mất. Việc xóa thư mục không thay thế cho commit, stash hoặc sao lưu.

## 4. Xóa linked worktree bằng git worktree remove

Khi đã xác nhận đúng đường dẫn và xử lý xong các thay đổi cần giữ, chạy từ một worktree khác, ví dụ worktree chính:

~~~bash
git worktree remove ../project-feature
~~~

Git kiểm tra worktree có thể được gỡ an toàn hay không, sau đó xóa thư mục linked worktree và metadata quản trị tương ứng. Đây là cách chuẩn để kết thúc vòng đời của một linked worktree.

Sau khi remove, kiểm tra:

~~~bash
git worktree list
git status --short --branch
~~~

Worktree vừa xóa không còn trong danh sách. Các branch và commit trong repository vẫn tồn tại nếu còn được tham chiếu bởi branch, tag hoặc ref khác.

Lệnh git worktree remove dùng cho linked worktree. Worktree chính của repository không thể được loại bỏ bằng lệnh này. Nếu muốn xóa toàn bộ repository, đó là thao tác quản lý thư mục repository riêng và cần xác định rõ rằng mọi công việc cần giữ đã được lưu.

Không chạy lệnh remove từ bên trong chính thư mục worktree đang định xóa. Hãy chuyển terminal sang worktree khác hoặc thư mục phù hợp trước khi thực hiện.

## 5. Khi nào dùng --force?

Nếu linked worktree còn thay đổi chưa commit, lệnh remove thông thường sẽ từ chối để bảo vệ công việc. Tùy chọn --force bỏ qua kiểm tra an toàn đó:

~~~bash
git worktree remove --force ../project-feature
~~~

Lệnh này có thể xóa worktree chứa thay đổi chưa commit, tệp chưa được theo dõi hoặc nội dung local mà bạn chưa sao lưu. Hãy xem đây là thao tác có thể làm mất dữ liệu.

Trước khi dùng --force:

1. Chạy git -C PATH status --short --branch.
2. Kiểm tra nội dung thay đổi và các tệp chưa được theo dõi.
3. Commit, stash hoặc sao lưu phần cần giữ.
4. Xác nhận đường dẫn thực sự thuộc worktree muốn loại bỏ.
5. Chỉ dùng --force nếu bạn chủ động chấp nhận bỏ phần còn lại.

Worktree có thể được khóa bằng git worktree lock để tránh bị prune hoặc xóa ngoài ý muốn, ví dụ khi thư mục nằm trên ổ đĩa ngoài hoặc vị trí tạm thời không luôn kết nối. Nếu remove báo worktree đang locked, kiểm tra lý do và người quản lý trước khi mở khóa:

~~~bash
git worktree unlock ../project-feature
git worktree remove ../project-feature
~~~

Không mở khóa chỉ để vượt qua một cảnh báo mà chưa hiểu tại sao worktree được khóa. Nếu worktree vừa dirty vừa locked, cần xử lý cả hai điều kiện; --force không phải lý do để bỏ qua bước kiểm tra công việc.

## 6. Phân biệt remove với xóa thư mục thủ công

Nếu bạn xóa thư mục linked worktree bằng File Explorer, rm hoặc Remove-Item, phần thư mục có thể biến mất nhưng metadata quản trị bên trong repository vẫn còn.

Ví dụ:

~~~text
Repository chính
|
+-- .git/
    +-- worktrees/
        +-- project-feature/
        +-- project-review/

Thư mục linked worktree:
../project-feature/       <- đã bị xóa thủ công
../project-review/        <- vẫn tồn tại
~~~

Git vẫn có thể giữ metadata cho project-feature vì thao tác xóa thư mục không thông báo cho Git rằng worktree đã kết thúc. Kết quả là git worktree list có thể hiển thị worktree không còn tồn tại hoặc đánh dấu nó là prunable.

Nếu thư mục vẫn tồn tại, hãy ưu tiên git worktree remove. Nếu thư mục đã bị xóa thủ công và metadata trở thành cũ, dùng git worktree prune để dọn phần metadata còn sót lại.

Không tự xóa thư mục .git/worktrees/ID bằng tay. Metadata có các liên kết và thông tin quản trị mà Git cần để nhận diện worktree; hãy để lệnh worktree quản lý chúng.

## 7. Prune là gì và dọn những gì?

Lệnh:

~~~bash
git worktree prune
~~~

Prune dọn các metadata quản trị của linked worktree không còn thư mục làm việc tương ứng và đã đến hạn hết hiệu lực. Nó xử lý các bản ghi worktree cũ trong vùng quản trị của repository.

Prune không:

- Xóa một thư mục worktree còn tồn tại.
- Xóa branch local mà worktree từng checkout.
- Xóa commit chỉ vì worktree bị xóa.
- Xóa tag hoặc remote branch.
- Thay thế việc sao lưu hoặc commit công việc chưa lưu.

Ví dụ, nếu thư mục ../project-feature đã bị xóa thủ công, prune có thể loại metadata cũ của worktree đó. Branch feature/search vẫn còn nếu branch ref vẫn tồn tại.

## 8. Xem trước trước khi prune

Trước khi dọn metadata, liệt kê worktree:

~~~bash
git worktree list --porcelain
~~~

Sau đó chạy chế độ xem trước:

~~~bash
git worktree prune --dry-run --verbose
~~~

--dry-run yêu cầu Git chỉ báo những gì sẽ được prune, không thực hiện xóa. --verbose hiển thị chi tiết các mục được xem xét hoặc loại bỏ.

Đọc kết quả và xác nhận các mục được đánh dấu là stale thực sự thuộc những worktree đã bị xóa hoặc không còn được sử dụng. Nếu đường dẫn chỉ vừa được di chuyển, hãy xử lý việc sửa liên kết worktree thay vì prune metadata của nó.

Khi đã xác nhận, chạy:

~~~bash
git worktree prune --verbose
~~~

Lệnh sẽ áp dụng chính sách hết hạn hiện tại để loại metadata stale đủ điều kiện. Nếu cần dọn ngay các mục stale thay vì chờ thời gian hết hạn:

~~~bash
git worktree prune --expire now --verbose
~~~

--expire now làm cho các metadata stale đủ điều kiện được xem là đã hết hạn ngay. Nó không biến worktree còn tồn tại thành stale và cũng không xóa các thư mục làm việc còn nguyên.

Nên dùng --dry-run trước, nhất là repository có nhiều linked worktree hoặc có worktree được khóa.

## 9. Ý nghĩa của thời gian hết hạn và worktree bị khóa

Git có thể trì hoãn việc xóa metadata stale để tránh xử lý quá sớm một worktree tạm thời không truy cập được. Tùy chọn --expire TIME điều khiển mốc tuổi tối thiểu của metadata stale đủ điều kiện prune.

Ví dụ:

~~~bash
git worktree prune --dry-run --verbose --expire "30.days.ago"
~~~

Lệnh trên xem trước metadata stale cũ hơn 30 ngày. Cú pháp thời gian tương đối được Git hiểu theo định dạng thời gian của nó.

Để xem cấu hình hết hạn liên quan tới garbage collection:

~~~bash
git config --show-origin --get gc.worktreePruneExpire
~~~

Nếu không có cấu hình riêng, Git sử dụng giá trị mặc định của phiên bản đang chạy. Vì chính sách mặc định có thể phụ thuộc cấu hình và phiên bản Git, hãy xem trước kết quả thay vì dựa vào một khoảng thời gian cố định.

Worktree bị khóa thường không được prune tự động. Đây là biện pháp bảo vệ cho worktree nằm trên thiết bị hoặc vị trí không phải lúc nào cũng có mặt. Nếu một worktree đã thực sự kết thúc, xác nhận lý do khóa, mở khóa có chủ đích rồi remove hoặc prune theo trạng thái thực tế.

## 10. Nếu worktree đã được di chuyển thì sao?

Một worktree có thể được di chuyển bằng thao tác hệ thống tệp, chẳng hạn chuyển thư mục từ ổ đĩa này sang ổ đĩa khác. Khi đó, metadata trong repository có thể vẫn lưu đường dẫn cũ.

Nếu worktree còn nguyên nhưng được di chuyển, đừng dùng prune ngay. Hãy sửa liên kết metadata bằng:

~~~bash
git worktree repair ../project-feature-moved
~~~

Chạy lệnh từ repository hoặc worktree phù hợp và cung cấp đường dẫn worktree đã di chuyển theo yêu cầu của Git. Sau đó kiểm tra:

~~~bash
git worktree list
git -C ../project-feature-moved status --short --branch
~~~

Repair dành cho worktree còn tồn tại nhưng thông tin liên kết cần được cập nhật. Prune dành cho metadata của worktree không còn thư mục tương ứng. Nhầm hai trường hợp có thể khiến bạn dọn metadata của một worktree vẫn còn dữ liệu cần giữ.

## 11. Xóa worktree không đồng nghĩa xóa branch

Giả sử worktree ../project-feature đang checkout branch feature/search. Sau khi chạy:

~~~bash
git worktree remove ../project-feature
~~~

Branch feature/search vẫn còn trong repository. Kiểm tra:

~~~bash
git branch --list
git branch -vv
~~~

Nếu muốn xóa branch sau khi worktree đã được gỡ, đó là quyết định riêng:

~~~bash
git branch -d feature/search
~~~

-d chỉ xóa branch khi Git xác định nó đã được hợp nhất theo điều kiện an toàn. Nếu branch chưa được merge, Git từ chối để bảo vệ commit chưa tích hợp.

Không dùng -D chỉ để dọn danh sách branch. -D buộc xóa branch kể cả khi chưa merge và có thể khiến commit khó tìm lại nếu không còn ref nào khác. Trước khi xóa branch, kiểm tra log, merge status và xác nhận công việc đã được đưa vào nơi cần thiết.

Nếu branch vẫn được một worktree khác checkout, Git cũng sẽ không cho xóa theo cách thông thường. Hãy kiểm tra git worktree list trước.

## 12. Quy trình đầy đủ: remove worktree rồi prune metadata cũ

### Trường hợp A: thư mục worktree vẫn còn

~~~bash
# 1. Xem các worktree
git worktree list --porcelain

# 2. Kiểm tra worktree sắp xóa
git -C ../project-feature status --short --branch
git -C ../project-feature log --oneline -n 8

# 3. Commit hoặc stash công việc cần giữ nếu có

# 4. Gỡ linked worktree đúng cách
git worktree remove ../project-feature

# 5. Xác minh
git worktree list
git branch -vv
~~~

Thông thường, remove đã xóa metadata tương ứng, nên không cần prune ngay sau đó. Có thể chạy prune định kỳ để dọn metadata stale còn sót lại từ những lần xóa thủ công trước đây.

### Trường hợp B: thư mục worktree đã bị xóa thủ công

~~~bash
# 1. Xem các mục worktree và trạng thái prunable
git worktree list --porcelain

# 2. Xem trước metadata sẽ được dọn
git worktree prune --dry-run --verbose

# 3. Sau khi xác nhận, dọn metadata stale
git worktree prune --verbose

# 4. Kiểm tra lại danh sách
git worktree list
~~~

Nếu metadata chưa đủ tuổi hết hạn theo chính sách hiện tại nhưng bạn đã xác nhận worktree không còn tồn tại, có thể dùng --expire now sau khi xem trước.

### Trường hợp C: cần dọn cả worktree và branch đã hoàn tất

~~~bash
# Gỡ worktree trước
git worktree remove ../project-feature

# Kiểm tra branch có được merge hay chưa
git branch --merged main

# Chỉ xóa branch đã hoàn tất và không còn được sử dụng
git branch -d feature/search

# Kiểm tra cuối
git worktree list
git branch --list
~~~

Việc xóa branch là bước riêng, không phải tác dụng của remove hoặc prune.

## 13. Lỗi thường gặp

### Remove từ chối vì worktree còn thay đổi

Chạy git -C PATH status --short --branch, sau đó commit, stash hoặc sao lưu phần cần giữ. Chỉ dùng --force khi chấp nhận xóa nội dung chưa lưu.

### Remove báo worktree đang được khóa

Kiểm tra lý do khóa và xác nhận worktree không còn được bảo vệ cho một thiết bị hoặc người dùng khác. Nếu an toàn, dùng git worktree unlock PATH rồi thử remove lại.

### Prune không xóa mục đang thấy trong danh sách

Kiểm tra đường dẫn còn tồn tại không, mục đó có bị khóa không và thời gian hết hạn đã đạt chưa. Dùng --dry-run --verbose và --expire now chỉ sau khi xác nhận mục thực sự stale.

### Prune xong nhưng branch vẫn còn

Đó là hành vi đúng. Prune chỉ dọn metadata worktree. Xóa branch là thao tác riêng và cần xác nhận branch đã được merge hoặc không còn cần thiết.

### Worktree còn tồn tại nhưng Git đánh dấu đường dẫn cũ

Có thể thư mục đã được di chuyển. Dùng git worktree repair để sửa liên kết thay vì prune.

### Đã xóa thư mục nhưng Git vẫn báo worktree

Đó là metadata cũ. Chạy git worktree prune --dry-run --verbose để xem trước, sau đó prune nếu đúng là worktree không còn tồn tại.

## 14. Ghi nhớ

- Worktree dùng chung object database và branch refs, nhưng có working tree, HEAD và index riêng.
- Dùng git worktree list để xác định đúng đường dẫn và branch trước khi xóa.
- Dùng git worktree remove cho linked worktree còn tồn tại; kiểm tra và lưu mọi thay đổi cần giữ trước đó.
- --force có thể làm mất nội dung chưa commit hoặc tệp local trong worktree.
- Nếu thư mục đã bị xóa thủ công, git worktree prune dọn metadata stale còn lại.
- Dùng --dry-run --verbose trước khi prune; --expire now chỉ nên dùng sau khi xác nhận các mục stale.
- Worktree bị khóa có thể cần được kiểm tra và unlock có chủ đích.
- Nếu thư mục chỉ được di chuyển, dùng git worktree repair thay vì prune.
- Remove và prune không tự xóa branch; xóa branch là quyết định riêng.

Khi kết thúc worktree theo đúng quy trình, bạn giữ được lịch sử và branch cần thiết, đồng thời loại bỏ metadata không còn sử dụng. Thói quen kiểm tra trước khi remove và xem trước trước khi prune giúp tránh xóa nhầm công việc hoặc dọn một worktree vẫn còn cần thiết.

