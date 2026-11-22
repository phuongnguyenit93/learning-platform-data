# Lọc commit theo tác giả, thời gian, thông điệp và đường dẫn

Lịch sử Git có thể chứa hàng nghìn commit từ nhiều người, nhiều nhánh và nhiều giai đoạn phát triển. Khi cần tìm ai đã tạo một thay đổi, thay đổi xuất hiện trong khoảng thời gian nào, commit có nhắc đến một mã lỗi hay file nào, bạn không cần đọc toàn bộ lịch sử. Lệnh **git log** cung cấp các bộ lọc để thu hẹp danh sách commit theo metadata và đường dẫn.

Trong chương **Tra cứu lịch sử** của module **SOURCE_CONTROL_GIT**, bài học này hướng dẫn cách lọc commit theo author, committer, thời gian, nội dung message và file/thư mục bị tác động. Bạn sẽ biết cách kết hợp điều kiện, phân biệt điều kiện lọc với cách trình bày output, xử lý lịch sử đổi tên file và tránh những kết luận sai khi timestamp hoặc tên hiển thị không phản ánh toàn bộ nguồn gốc thay đổi.

Sau bài học, bạn có thể:

- Tìm commit theo author hoặc committer.
- Giới hạn lịch sử bằng mốc thời gian tương đối hoặc tuyệt đối.
- Tìm commit có từ khóa trong subject, body hoặc trailers.
- Lọc commit chạm đến một file hoặc thư mục cụ thể.
- Kết hợp nhiều bộ lọc và hiểu cách Git kết hợp điều kiện.
- Dùng revision range để giới hạn phạm vi branch trước khi lọc.
- Tùy chỉnh output để xem người tạo, ngày, message và file thay đổi.
- Theo dõi lịch sử một file sau khi đổi tên bằng --follow.
- Nhận biết giới hạn của lọc theo metadata và xác minh kết quả trước khi kết luận.

## 1. Bắt đầu với git log

Lệnh cơ bản:

~~~bash
git log
~~~

Git hiển thị các commit reachable từ HEAD theo thứ tự lịch sử mặc định, thường gồm commit hash, author, date và message. Có thể dùng dạng ngắn:

~~~bash
git log --oneline
~~~

Để xem đồ thị branch:

~~~bash
git log --oneline --graph --decorate --all
~~~

Trước khi lọc, xác định phạm vi lịch sử. Nếu không truyền revision hoặc revision range, git log thường bắt đầu từ HEAD. Dùng --all để xem commit reachable từ mọi ref mà Git đưa vào phạm vi đó, gồm branch và tag phù hợp.

Ví dụ:

~~~bash
git log main
git log origin/main
git log main..feature/payment
git log --all --oneline
~~~

Lệnh main..feature/payment tìm commit reachable từ feature/payment nhưng không reachable từ main. Các bộ lọc tác giả, thời gian, message hoặc path sau đó sẽ tiếp tục thu hẹp phạm vi commit này.

## 2. Lọc theo tác giả với --author

Author là người được ghi nhận đã tạo thay đổi ban đầu trong commit. Dùng --author để chỉ hiển thị commit có trường author khớp với mẫu:

~~~bash
git log --author="An Nguyen"
~~~

Mẫu có thể khớp tên hoặc email trong author header. Ví dụ:

~~~bash
git log --author="an@example.com"
git log --author="An Nguyen <an@example.com>"
~~~

--author dùng biểu thức chính quy, không phải phép so sánh chuỗi tuyệt đối. Nếu chỉ muốn tìm một chuỗi cố định, có thể dùng tùy chọn --fixed-strings cùng --grep cho message; với author, hãy viết pattern đủ cụ thể và kiểm tra output.

### Tìm theo một phần tên hoặc email

~~~bash
git log --author="example.com"
git log --author="^An Nguyen"
~~~

Pattern đầu có thể khớp nhiều địa chỉ email cùng domain. Pattern thứ hai dùng dấu ^ của regex để yêu cầu phần tên bắt đầu bằng chuỗi đó. Kết quả phụ thuộc dữ liệu author thực tế trong commit.

### Phân biệt author và committer

Một commit có thể được viết bởi Alice nhưng được cherry-pick, rebase hoặc áp dụng bởi Bob. Khi đó author và committer khác nhau.

~~~bash
git log --author="Alice"
git log --committer="Bob"
~~~

- --author lọc theo author header.
- --committer lọc theo committer header.

Nếu bạn muốn tìm người đã đưa commit vào lịch sử hiện tại, committer có thể hữu ích. Nếu muốn tìm người được ghi nhận là tác giả thay đổi ban đầu, dùng author.

Lưu ý: --author không tự tìm mọi trailer như Co-authored-by trong commit message. Nó chỉ kiểm tra trường author của commit. Muốn tìm co-author được ghi trong message, dùng --grep.

## 3. Lọc theo committer với --committer

Dùng --committer để tìm commit có thông tin committer khớp pattern:

~~~bash
git log --committer="build-bot"
git log --committer="ci@example.com"
~~~

Bộ lọc này hữu ích khi:

- Một người áp dụng patch do người khác viết.
- Commit được tạo qua git am hoặc cherry-pick.
- CI/bot tạo commit tự động.
- Bạn cần điều tra ai hoặc tiến trình nào đã tạo commit object hiện tại.

Không suy ra tác giả ban đầu chỉ từ committer. Hãy hiển thị cả hai trường nếu cần đối chiếu:

~~~bash
git log --format="%h | author=%an <%ae> | committer=%cn <%ce> | %s"
~~~

## 4. Lọc theo thời gian

Git hỗ trợ các tùy chọn giới hạn commit theo ngày.

| Tùy chọn | Ý nghĩa |
| --- | --- |
| --since hoặc --after | Chỉ hiển thị commit mới hơn mốc thời gian |
| --until hoặc --before | Chỉ hiển thị commit cũ hơn mốc thời gian |
| --since-as-filter | Lọc theo mốc since nhưng tiếp tục duyệt toàn bộ phạm vi thay vì dừng sớm khi gặp commit cũ |

Ví dụ tìm commit sau ngày 1 tháng 1 năm 2026:

~~~bash
git log --since="2026-01-01"
~~~

Tìm commit trước ngày 1 tháng 4 năm 2026:

~~~bash
git log --until="2026-04-01"
~~~

Giới hạn một khoảng thời gian:

~~~bash
git log --since="2026-01-01" --until="2026-03-31"
~~~

Các tùy chọn --after tương đương --since; --before tương đương --until.

### Dùng thời gian tương đối

Git hiểu nhiều cách diễn đạt thời gian:

~~~bash
git log --since="2 weeks ago"
git log --since="yesterday"
git log --since="last month"
git log --since="3 days ago"
~~~

Thời gian tương đối tiện khi điều tra công việc gần đây. Kết quả phụ thuộc thời điểm chạy và cách Git diễn giải múi giờ của môi trường.

### Dùng mốc tuyệt đối có múi giờ

Trong báo cáo hoặc script có thể chạy trên nhiều máy, nên chỉ định ngày giờ và UTC offset:

~~~bash
git log --since="2026-03-01T00:00:00+07:00" --until="2026-04-01T00:00:00+07:00"
~~~

ISO 8601 với offset rõ ràng giúp tránh nhầm giữa giờ địa phương và UTC. Git dùng date parser của nó để diễn giải giá trị; hãy dùng định dạng nhất quán trong script và kiểm tra trên phiên bản Git của môi trường triển khai.

### Lưu ý về author date và committer date

Các bộ lọc thời gian của git log dựa trên ngày commit theo cách Git duyệt lịch sử, thông thường là committer date. Một commit có author date cũ nhưng được cherry-pick hôm nay có thể xuất hiện trong khoảng thời gian gần đây vì committer date mới.

Bạn có thể xem cả hai ngày:

~~~bash
git log --format="%h author=%aI committer=%cI %s"
~~~

Không dùng timestamp như bằng chứng duy nhất về thứ tự quan hệ lịch sử. Parent graph mới xác định commit nào là tổ tiên của commit nào.

### --since-as-filter khi ngày commit không đơn điệu

Git có thể dừng duyệt một nhánh lịch sử khi gặp commit có committer date cũ hơn mốc --since. Điều này thường nhanh, nhưng lịch sử có thể chứa commit được nhập hoặc tạo với ngày không theo thứ tự đồ thị. Khi cần duyệt toàn bộ phạm vi rồi lọc theo mốc thời gian, dùng:

~~~bash
git log --since-as-filter="2026-01-01"
~~~

Tùy chọn này không thay đổi ngày commit; nó thay đổi cách duyệt để tránh bỏ qua commit phía sau trong đồ thị chỉ vì đã gặp một commit có ngày cũ.

## 5. Lọc theo commit message với --grep

Commit message có thể gồm subject, body và trailers. Dùng --grep để tìm pattern trong message:

~~~bash
git log --grep="fix"
git log --grep="AUTH-142"
git log --grep="breaking change"
~~~

--grep tìm trong nội dung commit message, không chỉ dòng subject. Vì vậy, từ khóa trong body hoặc trailer cũng có thể làm commit khớp.

### Tìm không phân biệt chữ hoa/chữ thường

~~~bash
git log -i --grep="timeout"
~~~

-i hoặc --regexp-ignore-case làm tìm kiếm regex không phân biệt hoa thường.

### Tìm chuỗi cố định thay vì regex

~~~bash
git log --fixed-strings --grep="fix(auth):"
~~~

--fixed-strings (viết tắt -F) coi pattern của --grep là chuỗi cố định. Điều này hữu ích khi message có dấu ngoặc, dấu chấm hoặc ký tự có ý nghĩa đặc biệt trong regex.

### Nhiều từ khóa: OR và AND

Mặc định, nhiều tùy chọn --grep được kết hợp theo OR: commit khớp ít nhất một pattern sẽ được hiển thị.

~~~bash
git log --grep="AUTH-142" --grep="AUTH-198"
~~~

Nếu muốn commit phải khớp tất cả pattern --grep, thêm --all-match:

~~~bash
git log --all-match --grep="auth" --grep="security"
~~~

Ở đây mỗi pattern vẫn được kiểm tra trên toàn bộ message. --all-match yêu cầu commit khớp tất cả pattern đã truyền qua --grep.

### Đảo kết quả tìm kiếm message

~~~bash
git log --invert-grep --grep="WIP"
~~~

--invert-grep loại các commit có message khớp pattern và giữ những commit không khớp. Tùy chọn này chỉ đảo điều kiện grep message, không đảo các bộ lọc author, date hay path.

### Kết hợp subject và body

Nếu chỉ muốn hiển thị subject:

~~~bash
git log --format="%h %s"
~~~

Nếu muốn xem toàn bộ message:

~~~bash
git log --format="%h%n%B"
~~~

Lọc bằng --grep vẫn kiểm tra toàn bộ message dù output chỉ hiển thị subject.

## 6. Lọc theo file hoặc thư mục

Để chỉ xem commit có thay đổi một file:

~~~bash
git log -- src/api/auth.js
~~~

Đường dẫn phải đứng sau dấu -- để Git phân biệt revision/options với pathspec. Nếu không có dấu phân cách, một tên đường dẫn có thể bị hiểu nhầm là tên revision.

Tìm commit tác động đến một thư mục:

~~~bash
git log -- src/api/
~~~

Tìm commit tác động đến một số file:

~~~bash
git log -- src/api/auth.js src/api/session.js
~~~

Nếu truyền nhiều pathspec, Git hiển thị commit có thay đổi phù hợp với ít nhất một đường dẫn được chỉ định.

### Xem file nào thay đổi trong từng commit

~~~bash
git log --name-only -- src/api/
git log --stat -- src/api/
git log --name-status -- src/api/
~~~

- --name-only hiển thị tên file.
- --stat hiển thị thống kê thay đổi.
- --name-status hiển thị trạng thái file như A, M, D hoặc R.

Để xem patch của từng commit:

~~~bash
git log -p -- src/api/auth.js
~~~

-p hoặc --patch hiển thị diff của mỗi commit phù hợp. Nếu lịch sử dài, giới hạn số commit bằng -n:

~~~bash
git log -p -n 5 -- src/api/auth.js
~~~

### Theo dõi file sau khi đổi tên

Nếu file được rename, đường dẫn mới có thể không cho thấy lịch sử cũ theo cách bạn mong đợi. Dùng --follow:

~~~bash
git log --follow -- src/api/client.js
~~~

--follow cố gắng tiếp tục theo lịch sử của một file khi phát hiện rename. Tùy chọn này chỉ hỗ trợ một path và có giới hạn với lịch sử phức tạp, đặc biệt khi merge hoặc có nhiều nhánh đổi tên khác nhau. Git phát hiện rename dựa trên mức độ tương đồng nội dung, không lưu rename như một object riêng.

### Pathspec nâng cao

Pathspec có thể giới hạn theo mẫu:

~~~bash
git log -- ":(glob)**/*.js"
git log -- ":(icase)readme.md"
~~~

- :(glob) cho phép pattern glob áp dụng theo cú pháp pathspec.
- :(icase) yêu cầu so khớp đường dẫn không phân biệt hoa thường.

Để loại một đường dẫn khỏi tập pathspec, có thể dùng magic exclude:

~~~bash
git log -- "src/" ":(exclude)src/generated/"
~~~

Pathspec nâng cao hữu ích trong repository lớn; với tác vụ thông thường, chỉ cần đường dẫn cụ thể sau -- sẽ dễ đọc và ít nhầm hơn.

## 7. Kết hợp nhiều bộ lọc

Bạn có thể kết hợp author, committer, thời gian, message và path trong cùng lệnh.

Ví dụ tìm commit của An trong quý đầu năm 2026, message nhắc đến AUTH-142 và có thay đổi file trong src/auth:

~~~bash
git log --author="An Nguyen" --since="2026-01-01" --until="2026-04-01" --grep="AUTH-142" -- src/auth/
~~~

Các nhóm điều kiện author, committer, thời gian, message, path và revision range thường được kết hợp theo AND: commit phải đáp ứng từng nhóm điều kiện đã chỉ định.

Riêng khi lặp lại một số bộ lọc:

- Nhiều --grep mặc định là OR; dùng --all-match để yêu cầu tất cả pattern grep.
- Nhiều --author có thể khớp bất kỳ author pattern nào được chỉ định.
- Nhiều --committer có thể khớp bất kỳ committer pattern nào được chỉ định.
- Nhiều pathspec chọn commit chạm đến ít nhất một đường dẫn phù hợp.

Ví dụ tìm commit của Alice hoặc Bob:

~~~bash
git log --author="Alice" --author="Bob"
~~~

Ví dụ yêu cầu message có cả hai từ khóa:

~~~bash
git log --all-match --grep="security" --grep="token"
~~~

Nếu kết quả không như mong đợi, tách từng điều kiện thành lệnh riêng để xem bộ lọc nào loại commit.

## 8. Giới hạn phạm vi branch trước khi lọc

Bộ lọc metadata không tự xác định bạn muốn tìm ở branch nào. Mặc định git log duyệt từ HEAD. Dùng revision hoặc range để chọn lịch sử:

~~~bash
git log main --author="An"
git log origin/main --since="1 month ago"
git log main..feature/api -- src/api/
git log --all --grep="migration"
~~~

Một số dạng phạm vi:

| Revision | Phạm vi |
| --- | --- |
| HEAD | Lịch sử reachable từ commit hiện tại |
| main | Lịch sử reachable từ branch main |
| origin/main | Lịch sử reachable từ remote-tracking branch |
| A..B | Commit reachable từ B nhưng không reachable từ A |
| A...B | Symmetric difference giữa lịch sử A và B |
| --all | Lịch sử reachable từ các ref được Git đưa vào phạm vi all |

Ví dụ:

~~~bash
git log main..feature/api --author="Lan" -- src/api/
~~~

Lệnh này chỉ xét commit có trong feature/api nhưng không có trong main, sau đó lọc theo author và đường dẫn.

Để tìm commit đã bị loại khỏi branch hiện tại nhưng vẫn có thể được giữ bởi ref khác, --all có thể giúp mở rộng phạm vi. Nếu commit không còn reachable từ ref nào và đã bị dọn khỏi object database, git log không thể tìm thấy nó.

## 9. Tùy chỉnh output để đọc kết quả

Khi lọc theo nhiều điều kiện, output mặc định đôi khi không hiển thị đủ thông tin để xác minh.

### Hiển thị gọn

~~~bash
git log --oneline --decorate
~~~

### Hiển thị author, committer, ngày và subject

~~~bash
git log --format="%h | %an <%ae> | %cn <%ce> | %aI | %cI | %s"
~~~

Các placeholder thường dùng:

| Placeholder | Nội dung |
| --- | --- |
| %H | Commit hash đầy đủ |
| %h | Commit hash rút gọn |
| %an / %ae | Author name / email |
| %cn / %ce | Committer name / email |
| %aI | Author date ISO 8601 nghiêm ngặt |
| %cI | Committer date ISO 8601 nghiêm ngặt |
| %s | Subject |
| %b | Body |
| %B | Subject và body đầy đủ |
| %P | Parent hash hoặc các parent hash |

### Chọn cách hiển thị ngày

Tùy chọn --date điều khiển định dạng ngày trong output, ví dụ:

~~~bash
git log --date=short
git log --date=iso-strict
git log --date=relative
~~~

--date chỉ định dạng ngày được in ra; nó không thay đổi điều kiện lọc thời gian. Dùng --since/--until để lọc, dùng --date để trình bày.

### Hiển thị số lượng và giới hạn output

~~~bash
git log -n 10
git log --max-count=20
git log --skip=10 -n 10
~~~

-n hoặc --max-count giới hạn số commit được hiển thị.
- --skip bỏ qua một số commit đầu tiên trong kết quả theo thứ tự duyệt.

Khi lọc nhiều điều kiện, hãy nhớ -n giới hạn số kết quả sau khi Git áp dụng điều kiện, không phải giới hạn số commit thô trước khi lọc.

## 10. Ví dụ thực tế

### Tìm ai sửa một file trong tháng vừa qua

~~~bash
git log --since="1 month ago" --format="%h %an <%ae> %cI %s" -- src/payment/processor.js
~~~

Đọc author để biết người được ghi nhận là tác giả, committer date để biết thời điểm commit được tạo và subject để hiểu mục đích.

### Tìm commit liên quan một mã ticket

~~~bash
git log --all --fixed-strings --grep="PAY-284"
~~~

--all mở rộng lịch sử đến các ref; --fixed-strings giúp mã ticket được tìm như chuỗi nguyên văn.

### Tìm commit của bot trong một thư mục

~~~bash
git log --committer="release-bot@example.com" -- src/release/
~~~

Nếu bot chỉ xuất hiện trong author hoặc message trailer, hãy chọn bộ lọc tương ứng; --committer chỉ kiểm tra committer header.

### Loại commit có message chứa WIP

~~~bash
git log --invert-grep --grep="WIP"
~~~

--invert-grep đảo điều kiện grep và giữ commit có message không khớp WIP. Nếu muốn kết hợp logic phức tạp như “có fix nhưng không có WIP”, đừng giả định nhiều --grep cùng với --invert-grep tạo được hai điều kiện độc lập; hãy tách bước tìm kiếm hoặc xử lý kết quả bằng script có kiểm tra rõ ràng.

### Xem commit thêm/xóa file trong lịch sử

~~~bash
git log --diff-filter=A --name-status -- src/config/
git log --diff-filter=D --name-status -- src/config/
~~~

--diff-filter giới hạn commit theo loại thay đổi trong diff: A là thêm, D là xóa, M là sửa. Có thể kết hợp với --name-status để nhìn thấy file tương ứng.

### Tìm commit thay đổi một dòng cụ thể

git log lọc theo file nhưng không phải công cụ tốt nhất để tìm chính xác dòng code. Dùng -S hoặc -G:

~~~bash
git log -S"calculateTotal" -- src/payment/
git log -G"timeout[[:space:]]*=" -- src/config/
~~~

-S tìm commit làm thay đổi số lần xuất hiện của chuỗi.
-G tìm commit có diff chứa dòng khớp regex.

Hai tùy chọn này tìm thay đổi nội dung trong diff; chúng bổ sung cho bộ lọc path chứ không thay thế --author, --since hoặc --grep.

## 11. Phân biệt lọc commit với tìm nội dung khác

| Nhu cầu | Công cụ phù hợp |
| --- | --- |
| Tìm commit theo author, ngày, message, path | git log |
| Tìm commit làm thay đổi số lần xuất hiện của chuỗi | git log -S |
| Tìm commit có dòng diff khớp regex | git log -G |
| Tìm ai sửa từng dòng trong file hiện tại | git blame |
| Xem chi tiết một commit | git show |
| Xem đồ thị quan hệ commit | git log --graph |
| Tìm commit theo nội dung file đã biết | git log -S hoặc git log -G |

git blame cho biết commit gần nhất được gán cho từng dòng hiện tại, nhưng không phải lúc nào cũng tìm được nguồn gốc đầy đủ của một thay đổi đã bị di chuyển hoặc viết lại. git log lọc theo metadata cho phép xem nhiều commit và bối cảnh rộng hơn.

## 12. Các giới hạn cần hiểu khi đọc kết quả

### Author name/email có thể không đồng nhất

Một người có thể dùng nhiều email hoặc tên khác nhau. --author="An Nguyen" không chắc tìm được commit ghi email khác hoặc tên viết tắt. Khi điều tra nghiêm túc, tìm theo nhiều pattern hoặc kiểm tra trực tiếp author metadata.

### Message không phải metadata có cấu trúc bắt buộc

Mã ticket có thể nằm trong subject, body hoặc trailer; cũng có thể không được ghi trong message. --grep chỉ tìm nội dung message, không tìm source code hoặc tên branch.

### Timestamp có thể khác ngày làm việc thực tế

Author date có thể được giữ qua cherry-pick hoặc rebase; committer date thường phản ánh lúc commit object mới được tạo. Đồng hồ máy hoặc timezone có thể không chính xác. Nếu cần thứ tự lịch sử, xem parent graph.

### Path filter phản ánh diff và lịch sử đơn giản hóa

Git có thể đơn giản hóa lịch sử khi lọc theo path, đặc biệt quanh merge commit. Một merge có thể được xử lý theo quy tắc history simplification; vì vậy, nếu điều tra thay đổi qua nhiều nhánh, thử xem thêm đồ thị với --graph, --full-history hoặc kiểm tra từng parent.

### Rename được phát hiện theo nội dung

Git không lưu một sự kiện rename độc lập trong commit object. Khi hiển thị diff, Git phát hiện rename dựa trên mức tương đồng. --follow có thể giúp đi qua một lần đổi tên nhưng chỉ hỗ trợ một path và có giới hạn.

## 13. Quy trình điều tra lịch sử theo yêu cầu

Giả sử bạn cần tìm các commit của một kỹ sư đã tác động đến src/auth trong tháng 2, có nhắc đến token.

### Bước 1: xác định phạm vi branch

~~~bash
git branch -a
git log --oneline --decorate --all -n 20
~~~

Chọn branch hoặc revision range phù hợp với câu hỏi. Nếu cần lịch sử đã có trên remote, fetch trước theo quy trình nhóm rồi dùng remote-tracking branch.

### Bước 2: lọc theo thời gian

~~~bash
git log --since="2026-02-01T00:00:00+07:00" --until="2026-03-01T00:00:00+07:00"
~~~

### Bước 3: thêm author và message

~~~bash
git log --since="2026-02-01T00:00:00+07:00" --until="2026-03-01T00:00:00+07:00" --author="engineer@example.com" --grep="token"
~~~

### Bước 4: giới hạn đường dẫn

~~~bash
git log --since="2026-02-01T00:00:00+07:00" --until="2026-03-01T00:00:00+07:00" --author="engineer@example.com" --grep="token" -- src/auth/
~~~

### Bước 5: đọc nội dung và xác minh

~~~bash
git log -p --since="2026-02-01T00:00:00+07:00" --until="2026-03-01T00:00:00+07:00" --author="engineer@example.com" --grep="token" -- src/auth/
~~~

Đọc diff của từng commit, xem parent và kiểm tra author/committer khi cần:

~~~bash
git show --format=fuller <commit>
git show --stat <commit>
~~~

Không kết luận rằng một người đã thực hiện toàn bộ công việc chỉ vì author pattern khớp. Xác minh email, committer, review và bối cảnh branch nếu thông tin được dùng cho audit hoặc báo cáo.

## 14. Những nhầm lẫn thường gặp

### --author tìm người chạy git commit?

Không nhất thiết. Nó tìm author header. Người chạy lệnh thường là committer; hai trường có thể khác nhau.

### --since lọc theo AuthorDate?

Thông thường, giới hạn thời gian của git log dựa trên committer date. Nếu cần xem cả author date và committer date, hãy hiển thị chúng bằng %aI và %cI.

### --date=short chỉ hiển thị commit trong ngày?

Không. --date định dạng ngày output. --since và --until mới là bộ lọc thời gian.

### Nhiều --grep mặc định yêu cầu mọi từ khóa?

Không. Mặc định nhiều --grep là OR. Dùng --all-match để yêu cầu tất cả pattern.

### git log -- file tìm cả commit có message nhắc tên file?

Không. Path filter chọn commit có thay đổi liên quan đến đường dẫn trong diff. Muốn tìm message nhắc tên file, dùng --grep.

### --follow hỗ trợ nhiều file cùng lúc?

Không. --follow chỉ áp dụng cho một path. Nếu cần theo dõi nhiều file, chạy từng lệnh riêng hoặc dùng các cách duyệt lịch sử khác.

### Kết quả git log là toàn bộ commit từng tồn tại trong repository?

Không. git log chỉ duyệt commit reachable từ các revision/ref trong phạm vi. Commit không còn được ref nào giữ có thể không xuất hiện, dù object chưa bị dọn.

## 15. Tự kiểm tra

Bạn cần tìm commit do người có email dev@example.com tạo, trong tháng 5 năm 2026, message có cả hai từ khóa security và token, đồng thời commit có thay đổi file trong src/auth. Bạn muốn xem author, committer, ngày và subject.

Hãy trả lời:

1. Dùng tùy chọn nào để lọc author?
2. Dùng tùy chọn nào để giới hạn thời gian?
3. Làm thế nào để yêu cầu message khớp cả hai từ khóa?
4. Dấu phân cách nào đặt trước pathspec?
5. Dùng format placeholder nào để hiển thị author, committer, hai ngày và subject?
6. Nếu file đã được đổi tên, tùy chọn nào có thể theo lịch sử tên file cũ?
7. Vì sao không nên chỉ dựa vào author date để kết luận thời điểm commit được tạo?

**Gợi ý:** Dùng --author, --since và --until; dùng --all-match cùng hai --grep; đặt -- trước src/auth. Các placeholder hữu ích là %an/%ae, %cn/%ce, %aI/%cI và %s. Dùng --follow cho một file sau rename. Author date có thể được giữ khi cherry-pick hoặc rebase, còn committer date thường phản ánh lần tạo commit object hiện tại.

## Kết luận

git log có thể lọc lịch sử theo author, committer, thời gian, message và đường dẫn. Hãy chọn đúng phạm vi branch trước, kết hợp điều kiện một cách có chủ đích và nhớ rằng nhiều --grep mặc định là OR, còn --all-match yêu cầu mọi pattern grep cùng khớp. Dùng dấu -- để phân tách pathspec, --follow để theo một file qua rename và --format để hiển thị metadata cần xác minh. Khi điều tra nguồn gốc thay đổi, phân biệt author với committer và author date với committer date; nếu kết quả quan trọng cho audit, hãy đọc diff và parent graph thay vì chỉ dựa vào một bộ lọc.
