# Thay commit mới nhất bằng git commit --amend

Khi commit mới nhất có thông điệp chưa rõ, thiếu một file hoặc chứa một chỉnh sửa cần sửa lại, Git cho phép bạn thay commit đó bằng lệnh git commit --amend. Lệnh này tạo một commit object mới từ trạng thái index hiện tại, dùng commit mới thay vị trí tip của branch và giữ commit cũ trong reflog một thời gian. Nó không chỉnh sửa object cũ tại chỗ.

Trong chương **Tạo commit** của module **SOURCE_CONTROL_GIT**, bài học này hướng dẫn cách sửa commit mới nhất có chủ đích. Bạn sẽ biết amend lấy nội dung từ đâu, cách sửa message, bổ sung hoặc loại bỏ file, cập nhật metadata author, và cách xử lý khi commit đã được push. Bạn cũng sẽ học cách khôi phục nếu amend nhầm bằng reflog mà vẫn giữ được phần công việc cần thiết.

Sau bài học, bạn có thể:

- Giải thích amend tạo commit mới và di chuyển ref hiện tại.
- Kiểm tra trạng thái trước khi amend để biết nội dung nào sẽ được đưa vào commit.
- Sửa commit message hoặc giữ nguyên message bằng --no-edit.
- Bổ sung file đã quên và cập nhật snapshot của commit.
- Loại bỏ file hoặc thay đổi không nên có trong commit.
- Phân biệt author, committer và thời gian sau amend.
- Ký lại commit hoặc thêm sign-off khi cần.
- Hiểu tác động của amend đến lịch sử đã chia sẻ và push an toàn.
- Tìm commit cũ bằng reflog và khôi phục theo mục tiêu.

## 1. Amend thay thế commit tip như thế nào?

Một commit Git là object bất biến. Khi bạn chạy git commit --amend, Git tạo một commit object mới, thường dùng:

- Tree được xây dựng từ index hiện tại.
- Parent của commit tip cũ.
- Author metadata của commit cũ, trừ khi bạn yêu cầu thay đổi.
- Committer metadata mới của lần amend.
- Message cũ hoặc message mới mà bạn cung cấp.
- Chữ ký mới nếu commit được ký.

Sau đó Git di chuyển branch hiện tại (hoặc HEAD trong trạng thái detached) đến commit mới. Commit cũ không bị sửa nội dung.

Trước amend:

~~~text
A --- B
      ^
      main / HEAD
~~~

Sau khi amend:

~~~text
A --- B'
      ^
      main / HEAD

B vẫn là commit object cũ, không còn là tip của main.
~~~

Commit mới B' thường có cùng parent với B, nhưng tree, message hoặc metadata có thể khác. Vì nội dung commit object thay đổi nên object ID của B' khác B.

### Amend không phải thao tác sửa file trong commit object

Git không mở commit B rồi ghi đè. Object B được giữ nguyên; Git tạo object B' và cập nhật ref. Vì vậy:

- Hash commit thay đổi.
- Các commit con của B nếu có sẽ vẫn trỏ đến B cũ.
- Tag đang trỏ đến B vẫn trỏ đến B.
- Remote đang giữ B không tự chuyển sang B'.
- Reflog thường ghi lại lần HEAD chuyển từ B sang B'.

Đây là một thao tác viết lại lịch sử. Hãy kiểm tra xem commit đã được chia sẻ hay chưa trước khi amend.

## 2. Amend lấy nội dung từ index

Điểm quan trọng nhất khi dùng amend là commit mới lấy snapshot từ **index**, giống như khi tạo commit thông thường. Nội dung chưa stage trong working tree không tự động được đưa vào commit.

Kiểm tra trước khi amend:

~~~bash
git status --short
git diff --cached
git diff
git diff HEAD
~~~

Ý nghĩa:

- git diff --cached: nội dung đã stage so với commit hiện tại.
- git diff: nội dung sửa trên đĩa nhưng chưa stage.
- git diff HEAD: tổng khác biệt của working tree so với HEAD.

Ví dụ file đang có trạng thái MM:

~~~text
MM src/service.js
~~~

Cột X cho biết index khác HEAD; cột Y cho biết working tree khác index. Khi amend, Git dùng nội dung trong index. Phần chỉ xuất hiện trong git diff vẫn nằm ngoài commit mới.

Nếu muốn đưa phần sửa mới nhất vào amend, stage nó trước:

~~~bash
git add -- src/service.js
git diff --cached -- src/service.js
~~~

Sau đó mới chạy amend. Nếu muốn giữ phần chưa stage để làm tiếp sau, đừng stage phần đó.

## 3. Sửa commit message mới nhất

Khi chạy lệnh không kèm tùy chọn message:

~~~bash
git commit --amend
~~~

Git mở editor để bạn chỉnh sửa commit message. Bạn có thể sửa subject, body hoặc trailers, sau đó lưu và đóng editor để tạo commit mới.

Nếu chỉ muốn thay message bằng một dòng:

~~~bash
git commit --amend -m "fix(api): validate empty request body"
~~~

Lệnh trên thay message của commit tip bằng nội dung mới. Các thay đổi đã stage trong index cũng được đưa vào tree của commit mới.

### Giữ nguyên message và chỉ thay nội dung commit

Nếu đã stage file bị quên hoặc chỉnh sửa bổ sung, nhưng muốn giữ nguyên message:

~~~bash
git add -- src/validator.js
git commit --amend --no-edit
~~~

--no-edit yêu cầu Git giữ message hiện tại và không mở editor. Commit mới vẫn được tạo với tree lấy từ index; committer metadata và hash có thể thay đổi.

### Sửa cả message và nội dung

~~~bash
git add -- src/validator.js
git commit --amend -m "fix(validation): reject malformed input"
~~~

Lệnh này tạo commit mới gồm nội dung trong index và message mới. Trước khi chạy, kiểm tra git diff --cached để bảo đảm index không chứa thay đổi ngoài phạm vi mong muốn.

## 4. Bổ sung file đã quên sau khi commit

Một tình huống thường gặp là bạn commit xong mới nhận ra đã quên stage một file cần thiết.

Giả sử commit mới nhất thay đổi src/api.js nhưng quên thêm test/api.test.js.

### Bước 1: kiểm tra file bị quên

~~~bash
git status --short
git diff -- test/api.test.js
~~~

Nếu file mới chưa được theo dõi, git status thường hiển thị ??; git diff thông thường không hiển thị nội dung file untracked.

### Bước 2: stage file cần bổ sung

~~~bash
git add -- test/api.test.js
git diff --cached -- test/api.test.js
~~~

Kiểm tra nội dung file đã được đưa vào index đúng như mong muốn.

### Bước 3: thay commit tip

~~~bash
git commit --amend --no-edit
~~~

Commit mới giữ message cũ và chứa cả nội dung đã stage. Nếu commit cũ chưa được chia sẻ, đây thường là cách gọn để hoàn thiện commit.

### Bước 4: xác minh

~~~bash
git show --stat --oneline HEAD
git show --format=fuller --no-patch HEAD
git status --short
~~~

Xác nhận file test có trong commit mới và working tree còn trạng thái đúng dự kiến.

## 5. Loại bỏ file hoặc nội dung khỏi commit

Nếu commit mới nhất đã đưa nhầm file vào lịch sử, bạn có thể cập nhật index rồi amend.

### Xóa file khỏi repository và commit

~~~bash
git rm -- src/debug.log
git commit --amend --no-edit
~~~

git rm stage việc xóa file; amend tạo commit mới có tree không còn file đó.

### Bỏ file khỏi commit nhưng giữ bản sao trên đĩa

Nếu muốn file tiếp tục tồn tại local nhưng không được theo dõi trong commit:

~~~bash
git rm --cached -- local-secrets.txt
git commit --amend --no-edit
~~~

--cached gỡ file khỏi index nhưng giữ file trong working tree. Sau amend, file sẽ không còn trong tree của commit mới. Nếu file đã chứa secret và từng được push, amend không xóa bản sao ở remote, clone khác, cache hoặc lịch sử đã sao chép. Cần xử lý lộ lọt theo quy trình bảo mật của dự án; chỉ viết lại commit không thay thế việc thu hồi credential.

### Sửa nội dung file trong commit

Mở file, chỉnh sửa, rồi stage phiên bản đúng:

~~~bash
git add -- src/config.js
git diff --cached -- src/config.js
git commit --amend --no-edit
~~~

Nếu index đã có các thay đổi khác được stage từ trước, amend sẽ đưa tất cả nội dung trong index vào tree mới. Hãy xem toàn bộ git diff --cached, không chỉ file vừa sửa.

## 6. Sửa author và committer metadata

Amend có thể thay đổi metadata của commit. Mặc định, Git giữ author information của commit cũ nhưng ghi committer là người đang thực hiện amend.

Xem metadata trước khi amend:

~~~bash
git show -s --format=fuller HEAD
~~~

### Đặt author cụ thể

~~~bash
git commit --amend --author="Lan Nguyen <lan@example.com>" --no-edit
~~~

--author thay author name và email của commit mới. Committer vẫn là danh tính hiện tại của người chạy lệnh, trừ khi có cấu hình hoặc biến môi trường khác.

### Đặt lại author theo người đang amend

~~~bash
git commit --amend --reset-author --no-edit
~~~

--reset-author đặt author theo danh tính hiện tại và làm mới author date. Đây là lựa chọn khi bạn muốn nhận mình là author của commit được tạo lại, không phải chỉ đổi người committer.

### Thay author date

~~~bash
git commit --amend --date="2026-11-17T10:00:00+07:00" --no-edit
~~~

--date đặt author date cho commit mới. Committer date được tạo cho lần amend hiện tại, trừ khi bị điều khiển riêng qua biến môi trường.

Không sửa author hoặc timestamp chỉ để làm lịch sử trông thuận mắt. Metadata nên phản ánh đúng nguồn gốc thay đổi và quy trình cộng tác.

## 7. Thay đổi commit message và trailers

Commit message là một phần của commit object. Khi sửa message, Git tạo object ID mới ngay cả khi tree không đổi.

Bạn có thể chỉnh sửa bằng editor:

~~~bash
git commit --amend
~~~

Hoặc thay toàn bộ message:

~~~bash
git commit --amend -m "docs: clarify installation steps"
~~~

Nếu cần nhiều dòng:

~~~bash
git commit --amend -m "fix(auth): reject expired sessions" -m "Check expiry before loading the user session.
Return a clear error so clients can refresh credentials."
~~~

Mỗi tùy chọn -m tạo một đoạn message; Git đặt dòng trống giữa subject và body.

### Thêm sign-off trailer

~~~bash
git commit --amend --signoff --no-edit
~~~

--signoff (viết tắt -s) thêm trailer Signed-off-by theo danh tính committer. Trailer này là một xác nhận theo quy ước DCO; nó không phải chữ ký mật mã.

### Ký lại commit

~~~bash
git commit --amend -S --no-edit
~~~

-S yêu cầu ký commit mới bằng định dạng và khóa đã cấu hình, ví dụ GPG hoặc SSH. Nếu commit cũ có chữ ký, chữ ký đó không thể dùng lại cho commit mới vì nội dung object đã thay đổi. Hãy xác minh lại:

~~~bash
git verify-commit HEAD
~~~

## 8. Amend commit root

Root commit là commit đầu tiên của một lịch sử và không có parent. Bạn vẫn có thể thay root commit mới nhất nếu HEAD hiện tại chính là root:

~~~bash
git commit --amend -m "chore: initialize project structure"
~~~

Commit mới vẫn không có parent, nhưng tree, metadata hoặc message có thể thay đổi và object ID mới được tạo. Nếu repository có các nhánh hoặc ref khác đang trỏ đến root commit cũ, chúng không tự được cập nhật.

Kiểm tra parent:

~~~bash
git rev-list --parents -n 1 HEAD
~~~

Nếu output chỉ có một OID commit mà không có OID parent, đó là root commit.

## 9. Amend chỉ tác động đến commit mới nhất

git commit --amend thay commit mà HEAD hiện tại trỏ đến. Nó không tìm một commit cũ bất kỳ theo message hoặc hash.

Nếu muốn sửa một commit nằm sâu hơn trong lịch sử, bạn cần viết lại chuỗi commit bằng interactive rebase hoặc công cụ phù hợp:

~~~bash
git rebase -i <parent-of-target>
~~~

Trong editor rebase, đổi lệnh của commit cần sửa thành edit, sau đó Git dừng tại commit đó để bạn chạy amend. Các commit phía sau được phát lại và nhận hash mới.

Chỉ dùng cách này khi hiểu phạm vi lịch sử sẽ bị viết lại. Nếu commit cũ đã được chia sẻ, cần phối hợp với người đang dựa trên lịch sử đó.

## 10. Kiểm tra kết quả sau amend

Không nên chỉ nhìn thấy thông báo commit thành công rồi tiếp tục. Hãy xác nhận tree, message, metadata và trạng thái working tree.

### Xem commit mới

~~~bash
git show --stat --oneline HEAD
git show --format=fuller --no-patch HEAD
~~~

### Xem nội dung commit

~~~bash
git show --format=fuller --find-renames HEAD
~~~

### Xem tree và parent

~~~bash
git show -s --format="commit=%H%ntree=%T%nparent=%P" HEAD
~~~

### Kiểm tra working tree

~~~bash
git status --short
git diff
git diff --cached
~~~

Nếu amend được dùng để thêm file đã quên, kiểm tra file có trong tree:

~~~bash
git ls-tree -r --name-only HEAD
~~~

Nếu muốn so sánh commit mới với commit cũ, trước hết lấy OID cũ từ reflog hoặc từ nơi đã ghi lại:

~~~bash
git diff <old-commit> HEAD
git show --stat <old-commit>
git show --stat HEAD
~~~

So sánh hai commit giúp bạn xác nhận phần thay đổi được bổ sung, loại bỏ hoặc chỉnh sửa.

## 11. Tìm commit cũ sau khi amend bằng reflog

Vì amend di chuyển HEAD từ commit cũ sang commit mới, reflog thường lưu lại lần di chuyển này.

Xem các lần HEAD thay đổi gần đây:

~~~bash
git reflog -n 10
~~~

Ví dụ:

~~~text
9f8e7d6 HEAD@{0}: commit (amend): fix(api): validate input
3a2b1c0 HEAD@{1}: commit: fix(api): validate
...
~~~

Trong ví dụ:

- HEAD@{0} là commit sau amend.
- HEAD@{1} là commit trước amend.

Reflog là dữ liệu local và có thời hạn lưu theo cấu hình. Nó không được push lên remote và không thay thế backup dài hạn.

### Giữ commit cũ bằng một branch cứu hộ

Nếu muốn bảo toàn commit cũ trước khi thực hiện bước khôi phục:

~~~bash
git branch backup-before-amend <old-commit>
~~~

Thay <old-commit> bằng OID đã xác minh từ reflog. Branch mới giữ một ref trỏ đến commit cũ để bạn có thể so sánh hoặc khôi phục sau này.

## 12. Khôi phục sau khi amend nhầm

Trước tiên, dừng các thao tác viết lại lịch sử tiếp theo và xem reflog:

~~~bash
git reflog -n 10
git status --short
~~~

Xác định đúng OID trước amend. Không dựa mù quáng vào HEAD@{1} nếu đã có thêm thao tác checkout, reset hoặc commit sau đó; hãy đọc nội dung reflog.

### Trở lại commit cũ và giữ nội dung amend trong index

Nếu mục tiêu là đưa branch về commit cũ nhưng giữ snapshot của commit mới dưới dạng thay đổi đã stage:

~~~bash
git reset --soft <old-commit>
~~~

--soft di chuyển HEAD/ref đến commit cũ và giữ nguyên index cùng working tree. Chênh lệch giữa commit cũ và snapshot đã amend sẽ nằm trong index. Bạn có thể xem:

~~~bash
git status --short
git diff --cached
git diff
~~~

Đây thường là cách phù hợp khi muốn bỏ lần amend nhưng vẫn giữ nội dung đã thêm để chỉnh sửa tiếp.

### Chỉ giữ commit cũ làm mốc dự phòng

Nếu chưa chắc muốn khôi phục ngay, tạo branch backup như bước trước. Sau đó so sánh:

~~~bash
git show <old-commit>
git show HEAD
git diff <old-commit> HEAD
~~~

Chọn phương án khôi phục sau khi đã hiểu tree và các thay đổi khác biệt.

### Reflog không lưu mọi chỉnh sửa chưa commit

Reflog ghi nhận việc ref di chuyển, không phải bản sao đầy đủ của working tree. Nếu trước amend bạn có thay đổi chưa stage hoặc untracked, thao tác reset/restore sau đó có thể ảnh hưởng đến chúng. Hãy kiểm tra trạng thái và lưu riêng phần công việc cần giữ trước khi khôi phục.

## 13. Điều gì xảy ra nếu commit đã được push?

Nếu commit cũ đã được push, remote branch vẫn trỏ đến commit cũ. Sau amend, local branch trỏ đến commit mới có cùng parent nhưng object ID khác. Khi push bình thường, Git thường từ chối vì cập nhật không phải fast-forward.

~~~text
Remote trước amend:
A --- B (origin/main)

Local sau amend:
A --- B' (main)
~~~

B' không phải hậu duệ của B; nó có cùng parent A nhưng là object khác. Push thường không thể thay origin/main từ B sang B'.

### Ưu tiên tránh amend commit đã chia sẻ

Nếu người khác đã fetch hoặc tạo commit dựa trên B, thay B bằng B' có thể khiến lịch sử của họ phân kỳ. Họ có thể cần rebase, reset hoặc xử lý commit trùng. Trong branch dùng chung, cách ít gây gián đoạn thường là tạo một commit mới sửa lỗi thay vì viết lại commit đã công bố.

### Nếu nhóm đã thống nhất viết lại branch

Chỉ khi có sự đồng thuận và bạn đã xác minh remote tip, có thể dùng quy trình:

~~~bash
git fetch origin
git log --oneline --decorate --graph --left-right main...origin/main
git push --force-with-lease origin main
~~~

Trước lệnh push, đọc kết quả so sánh để chắc chắn không có commit mới của đồng đội cần tích hợp. --force-with-lease yêu cầu remote ref vẫn ở giá trị mà local dự kiến, giúp tránh ghi đè một cập nhật mới xảy ra sau lần kiểm tra. Tuy vậy, nó không thay thế việc phối hợp với đồng đội, xem lịch sử remote và xác nhận đúng branch.

Nếu remote đã tiến lên bằng commit mới của đồng đội, dừng lại và tích hợp lịch sử mới trước khi quyết định viết lại. Force-with-lease có thể từ chối nếu remote không còn ở giá trị mong đợi; hãy fetch và kiểm tra lại thay vì bỏ qua cảnh báo.

### Branch được bảo vệ

Một số nền tảng hoặc repository cấu hình từ chối force push vào main, release hoặc branch được bảo vệ. Đây là chính sách phía server. Hãy dùng commit sửa tiếp theo hoặc quy trình được nhóm cho phép.

## 14. Tác động đến tag, chữ ký và pipeline

Amend tạo commit có OID mới. Những tham chiếu khác không tự động di chuyển theo:

- Tag đang trỏ đến commit cũ vẫn trỏ đến commit cũ.
- Branch khác vẫn trỏ đến commit cũ.
- Remote branch không tự thay đổi.
- Pull request hoặc CI có thể tiếp tục tham chiếu commit cũ cho đến khi branch được cập nhật.

Nếu tag phát hành đã trỏ đến commit cũ, không tự ý di chuyển tag đã công bố. Hãy tuân thủ chính sách phát hành của nhóm; việc thay đổi tag có thể làm người dùng khác có hai cách hiểu về cùng một phiên bản.

Chữ ký commit cũ cũng không áp dụng cho commit mới. Nếu dự án yêu cầu signed commit, hãy ký lại:

~~~bash
git commit --amend -S --no-edit
git verify-commit HEAD
~~~

Khi push commit mới, CI hoặc automation có thể chạy lại. Kiểm tra trạng thái build, review và các quy trình phát hành gắn với branch.

## 15. Các tình huống amend thường gặp

| Mục tiêu | Lệnh gợi ý | Kết quả |
| --- | --- | --- |
| Sửa message trong editor | git commit --amend | Tạo commit mới với message được chỉnh |
| Thay message trực tiếp | git commit --amend -m ... | Thay message và dùng index hiện tại |
| Thêm file bị quên | git add file rồi git commit --amend --no-edit | Thêm file vào tree commit mới, giữ message |
| Sửa nội dung đã commit | Sửa file, git add file, rồi amend | Tree commit mới chứa nội dung đã stage |
| Giữ message, chỉ cập nhật tree | git commit --amend --no-edit | Dùng snapshot index hiện tại |
| Đổi author | git commit --amend --author=... | Ghi author mới |
| Đặt author theo người amend | git commit --amend --reset-author | Đặt lại author và author date |
| Ký commit mới | git commit --amend -S --no-edit | Tạo chữ ký mới |
| Bổ sung DCO sign-off | git commit --amend -s --no-edit | Thêm trailer Signed-off-by |
| Bỏ file khỏi commit nhưng giữ local | git rm --cached file rồi amend | Xóa entry khỏi tree mới, giữ file trên đĩa |

Các lệnh này đều thay commit tip. Trước khi chạy, xem git status, git diff và git diff --cached để xác định chính xác tree mới sẽ chứa gì.

## 16. Những nhầm lẫn thường gặp

### --amend sửa commit object cũ tại chỗ?

Không. Git tạo commit object mới và di chuyển ref. Commit cũ vẫn tồn tại cho đến khi không còn được giữ bởi ref/reflog và có thể được dọn sau này.

### Amend tự đưa mọi chỉnh sửa trên đĩa vào commit?

Không. Tree mới được lấy từ index. Phần chưa stage vẫn ở working tree.

### --no-edit chỉ đổi timestamp?

Không. Nó giữ nguyên commit message và không mở editor. Tree vẫn lấy từ index; committer metadata và hash có thể thay đổi.

### Amend commit đã push có thể push bình thường?

Thông thường không, vì commit mới không phải hậu duệ của commit cũ. Cần phối hợp nếu muốn viết lại lịch sử và dùng force-with-lease khi được cho phép.

### Amend một commit cũ có cần interactive rebase?

Có. --amend chỉ thay commit mà HEAD hiện tại trỏ đến. Muốn sửa commit cũ hơn, dùng rebase tương tác hoặc quy trình viết lại lịch sử phù hợp.

### Tag tự chuyển sang commit sau amend?

Không. Tag là ref riêng. Nếu tag trỏ đến commit cũ, nó vẫn giữ nguyên đích cho đến khi có thao tác thay đổi tag.

### Reflog là backup vĩnh viễn?

Không. Reflog chỉ là lịch sử ref local và có thể hết hạn hoặc bị dọn. Hãy tạo branch backup hoặc lưu OID nếu cần giữ commit cũ.

## 17. Tự kiểm tra

Bạn vừa commit fix(api): validate request, sau đó phát hiện quên thêm test/api.test.js. Working tree có file test mới và chưa có thay đổi khác. Commit chưa được push.

Hãy trả lời:

1. Vì sao cần chạy git add trước amend?
2. Lệnh nào thêm file test vào commit nhưng giữ nguyên message?
3. Commit mới có giữ nguyên OID cũ không?
4. Author và committer có nhất thiết giống nhau sau amend không?
5. Lệnh nào kiểm tra commit mới có chữ ký hợp lệ?
6. Nếu amend nhầm, làm thế nào tìm OID commit cũ?
7. Nếu commit cũ đã được push lên branch dùng chung, vì sao cần phối hợp trước khi force push?

**Gợi ý:** git add đưa file vào index; git commit --amend --no-edit tạo commit mới từ index và giữ message. OID mới khác OID cũ. Author thường được giữ, committer là người thực hiện amend. Dùng git verify-commit HEAD để kiểm tra chữ ký. Dùng git reflog để tìm commit cũ. Viết lại lịch sử đã chia sẻ có thể làm branch đồng đội phân kỳ hoặc khiến commit của họ bị mất khỏi tip; chỉ force push khi nhóm đã thống nhất và remote đã được kiểm tra.

## Kết luận

git commit --amend thay commit tip bằng một commit object mới, lấy tree từ index và giữ hoặc thay message/metadata theo tùy chọn. Dùng nó để sửa message, bổ sung file bị quên hoặc chỉnh lại nội dung trước khi chia sẻ lịch sử. Hãy kiểm tra staged và unstaged changes trước khi amend, xác minh tree, message và chữ ký sau khi chạy. Nếu amend nhầm, reflog giúp tìm commit cũ; reset --soft có thể đưa branch trở lại commit đó trong khi giữ snapshot mới ở index. Nếu commit đã được push hoặc có người khác dựa vào, phối hợp trước khi viết lại lịch sử và chỉ force push theo chính sách của nhóm.
