# Sửa tác giả, email và thời gian của commit đúng phạm vi

Mỗi commit Git lưu hai nhóm danh tính và thời gian: **author** (người tạo ra thay đổi ban đầu) và **committer** (người tạo commit object hiện tại). Hai nhóm này có thể giống nhau, nhưng thường khác nhau khi một commit được cherry-pick, rebase hoặc áp dụng lại bởi người khác.

Khi phát hiện commit dùng sai email, tên tác giả hoặc thời gian, trước tiên cần xác định chính xác trường nào sai và commit đó đã được chia sẻ hay chưa. Thay đổi cấu hình Git chỉ ảnh hưởng đến commit tạo sau này; muốn sửa metadata của commit đã tồn tại, Git phải tạo commit object mới. Với commit mới nhất có thể dùng `git commit --amend`; với commit cũ hơn thường cần interactive rebase. Việc này làm thay đổi mã commit và có thể ảnh hưởng đến các commit con, tag, chữ ký và người đang dùng lịch sử cũ.

Bài học này hướng dẫn cách kiểm tra metadata, cấu hình danh tính cho đúng phạm vi, sửa author/committer và thời gian cho commit mới hoặc commit đã có, lựa chọn amend hay rebase, rồi xác minh kết quả an toàn.

## 1. Author và committer là hai vai trò khác nhau

### 1.1. Author — người tạo ra thay đổi

Author là người được ghi nhận đã viết hoặc tạo ra nội dung thay đổi. Commit lưu:

- Author name.
- Author email.
- Author date.

Ví dụ, một lập trình viên tạo patch, sau đó gửi patch cho người bảo trì áp dụng vào repository. Author thường là lập trình viên tạo patch.

### 1.2. Committer — người tạo commit object

Committer là người tạo commit object được lưu trong lịch sử hiện tại. Commit lưu:

- Committer name.
- Committer email.
- Committer date.

Nếu bạn tự sửa code và commit, author và committer thường giống nhau. Nếu bạn cherry-pick commit của người khác hoặc rebase một commit, author có thể vẫn là người ban đầu, còn committer là người thực hiện thao tác tạo commit mới.

### 1.3. Author date và committer date

Hai mốc thời gian cũng có ý nghĩa khác nhau:

| Trường | Ý nghĩa |
| --- | --- |
| Author date | Thời điểm được ghi nhận là lúc tác giả tạo thay đổi |
| Committer date | Thời điểm commit object hiện tại được tạo |

Ví dụ:

- Alice viết thay đổi ngày 10/03.
- Bob cherry-pick thay đổi đó vào nhánh tích hợp ngày 12/03.

Commit mới có thể ghi author là Alice với author date 10/03, còn committer là Bob với committer date 12/03.

Không nên coi hai ngày này là cùng một trường hoặc cố làm chúng giống nhau nếu điều đó không phản ánh đúng lịch sử.

### 1.4. Metadata nằm trong commit object

Commit object lưu tree, parent, author, committer và message. Các trường này là một phần của nội dung commit, vì vậy thay đổi bất kỳ trường nào cũng tạo OID/hash mới.

Một commit không thể được chỉnh sửa tại chỗ như một dòng trong cơ sở dữ liệu. Các thao tác amend hoặc rebase tạo commit object mới và cập nhật ref để trỏ đến lịch sử mới.

## 2. Kiểm tra metadata hiện tại

### 2.1. Xem author và committer của commit mới nhất

~~~bash
git log -1 --format=fuller --date=iso-strict
~~~

Đầu ra thường có các dòng:

~~~text
Author:     Alice Example <alice@example.com>
AuthorDate: 2025-03-10T09:30:00+07:00
Commit:     Bob Example <bob@example.com>
CommitDate: 2025-03-12T14:15:00+07:00
~~~

Đây là cách nhanh để nhận diện trường nào đang sai.

### 2.2. In từng trường theo định dạng rõ ràng

~~~bash
git show -s --format="Author: %an <%ae>%nAuthor date: %aI%nCommitter: %cn <%ce>%nCommitter date: %cI" HEAD
~~~

Các placeholder thường dùng:

| Placeholder | Giá trị |
| --- | --- |
| %an | Author name |
| %ae | Author email |
| %aI | Author date theo ISO 8601 nghiêm ngặt |
| %cn | Committer name |
| %ce | Committer email |
| %cI | Committer date theo ISO 8601 nghiêm ngặt |
| %H | Commit hash đầy đủ |
| %s | Subject của commit |

Để kiểm tra commit cụ thể, thay `HEAD` bằng tag, branch hoặc commit ID.

### 2.3. Xem dữ liệu thô của commit object

~~~bash
git cat-file -p HEAD
~~~

Commit object hiển thị các trường như:

~~~text
tree <tree-oid>
parent <parent-oid>
author Alice Example <alice@example.com> 1741573800 +0700
committer Bob Example <bob@example.com> 1741763700 +0700

Commit message
~~~

Git lưu timestamp dạng Unix time cùng offset múi giờ. Dữ liệu thô hữu ích khi cần điều tra chính xác, nhưng thông thường `git log --format=fuller` dễ đọc hơn.

### 2.4. Xác định đúng commit trước khi sửa

Xem một số commit gần nhất:

~~~bash
git log --oneline --decorate -10
~~~

Xem commit cùng metadata:

~~~bash
git log --format=fuller --date=iso-strict -5
~~~

Không dựa vào vị trí hiển thị trong một log đã rút gọn để sửa commit. Hãy xác định commit bằng hash hoặc thông tin đủ chắc chắn, đặc biệt khi có nhiều commit cùng subject.

## 3. Cấu hình danh tính cho các commit tiếp theo

### 3.1. Xem cấu hình đang được áp dụng

~~~bash
git config --show-origin --get user.name
git config --show-origin --get user.email
~~~

Lệnh hiển thị giá trị cùng nguồn cấu hình, giúp phân biệt cấu hình system, global và local.

Có thể xem danh tính Git sẽ dùng:

~~~bash
git var GIT_AUTHOR_IDENT
git var GIT_COMMITTER_IDENT
~~~

Các lệnh này cho biết danh tính hiệu lực trong môi trường hiện tại. Biến môi trường như `GIT_AUTHOR_NAME` hoặc `GIT_COMMITTER_EMAIL` có thể ghi đè cấu hình.

### 3.2. Cấu hình cho một repository

Nếu email công việc chỉ nên áp dụng trong repository hiện tại:

~~~bash
git config --local user.name "Nguyen Van An"
git config --local user.email "an@company.example"
~~~

Cấu hình local được lưu trong Git config của repository và chỉ áp dụng ở đó, trừ khi có cấu hình hoặc biến môi trường có độ ưu tiên cao hơn.

Kiểm tra:

~~~bash
git config --show-origin --get user.name
git config --show-origin --get user.email
~~~

### 3.3. Cấu hình global cho người dùng hiện tại

Nếu danh tính này phù hợp với phần lớn repository của bạn:

~~~bash
git config --global user.name "Nguyen Van An"
git config --global user.email "an@example.com"
~~~

Không nên đặt global một email công việc nếu bạn cũng dùng máy cho các repository cá nhân có quy tắc danh tính khác. Trong trường hợp đó, cấu hình local phù hợp hơn.

### 3.4. Cấu hình đúng không sửa commit cũ

Các lệnh `git config user.name` và `git config user.email` chỉ ảnh hưởng đến danh tính được dùng cho commit mới. Chúng không thay đổi author hoặc committer đã lưu trong commit cũ.

Nếu commit mới nhất đã dùng email sai, bạn phải tạo lại commit bằng amend. Nếu commit cũ hơn sai, cần thao tác viết lại lịch sử hoặc chấp nhận giữ nguyên lịch sử đã chia sẻ theo quy ước nhóm.

## 4. Phân biệt cách đặt author và committer

### 4.1. Dùng --author để đặt tác giả

Tùy chọn:

~~~bash
git commit --author="Nguyen Van An <an@company.example>" -m "Add invoice validation"
~~~

đặt author cho commit đang tạo. Nó không phải tùy chọn để đặt committer.

Thông thường committer lấy từ danh tính Git hiện tại (cấu hình và biến môi trường tương ứng).

### 4.2. Dùng --date để đặt author date

Ví dụ:

~~~bash
git commit --date="2025-03-10T09:30:00+07:00" -m "Add invoice validation"
~~~

`--date` điều khiển **author date**. Nó không trực tiếp đặt committer date.

Để hiển thị rõ sau khi commit:

~~~bash
git log -1 --format=fuller --date=iso-strict
~~~

Nên dùng ngày giờ có offset múi giờ rõ ràng, chẳng hạn `+07:00`, để tránh nhập nhằng khi làm việc giữa các khu vực.

### 4.3. Biến môi trường cho author và committer

Git hỗ trợ các biến môi trường:

| Biến | Trường được đặt |
| --- | --- |
| GIT_AUTHOR_NAME | Author name |
| GIT_AUTHOR_EMAIL | Author email |
| GIT_AUTHOR_DATE | Author date |
| GIT_COMMITTER_NAME | Committer name |
| GIT_COMMITTER_EMAIL | Committer email |
| GIT_COMMITTER_DATE | Committer date |

Các biến này có thể đặt riêng cho một lệnh để không thay đổi cấu hình dùng lâu dài.

Trong Bash:

~~~bash
GIT_AUTHOR_NAME="Nguyen Van An" \
GIT_AUTHOR_EMAIL="an@company.example" \
GIT_AUTHOR_DATE="2025-03-10T09:30:00+07:00" \
GIT_COMMITTER_NAME="Build Maintainer" \
GIT_COMMITTER_EMAIL="maintainer@company.example" \
GIT_COMMITTER_DATE="2025-03-12T14:15:00+07:00" \
git commit -m "Add invoice validation"
~~~

Trong PowerShell, đặt biến cho phiên shell hiện tại trước khi gọi Git:

~~~powershell
$env:GIT_AUTHOR_NAME = "Nguyen Van An"
$env:GIT_AUTHOR_EMAIL = "an@company.example"
$env:GIT_AUTHOR_DATE = "2025-03-10T09:30:00+07:00"

git commit -m "Add invoice validation"
~~~

Sau đó khôi phục hoặc xóa các biến môi trường đã đặt để chúng không ảnh hưởng đến lệnh Git tiếp theo. Nếu biến đã tồn tại từ trước, hãy lưu giá trị cũ và khôi phục thay vì xóa tùy tiện.

### 4.4. Không nhầm --date với committer date

Ví dụ:

~~~bash
git commit --date="2025-03-10T09:30:00+07:00" -m "Add invoice validation"
~~~

sẽ đặt author date theo giá trị chỉ định. Committer date vẫn là thời điểm commit object được tạo, trừ khi bạn đặt `GIT_COMMITTER_DATE`.

Khi kiểm tra, luôn đọc cả AuthorDate và CommitDate để chắc chắn bạn sửa đúng trường.

## 5. Sửa metadata của commit mới nhất bằng amend

### 5.1. Khi nào dùng git commit --amend?

`git commit --amend` tạo một commit mới thay thế commit tip hiện tại của branch. Đây là cách phù hợp khi vừa tạo commit cuối cùng và phát hiện author, email, date hoặc message chưa đúng.

Trước khi amend, kiểm tra:

~~~bash
git status --short --branch
git diff --cached
git log -1 --format=fuller --date=iso-strict
~~~

Đặc biệt chú ý index: mọi thay đổi đang staged sẽ được đưa vào commit amend. Nếu mục tiêu chỉ sửa metadata, không để thay đổi staged ngoài ý muốn.

### 5.2. Đổi author name và email, giữ commit message

~~~bash
git commit --amend --no-edit --author="Nguyen Van An <an@company.example>"
~~~

`--no-edit` giữ nguyên commit message hiện tại. `--author` thay thông tin author; committer của commit mới được lấy từ danh tính hiện tại.

Nếu cần giữ author date cũ một cách tường minh, ghi nhận giá trị trước khi amend:

~~~bash
git show -s --format=%aI HEAD
~~~

Sau đó truyền ngày mong muốn bằng `--date`:

~~~bash
git commit --amend --no-edit --author="Nguyen Van An <an@company.example>" --date="2025-03-10T09:30:00+07:00"
~~~

Hãy dùng giá trị author date đã xác minh, không tự suy đoán ngày.

### 5.3. Đổi author date

~~~bash
git commit --amend --no-edit --date="2025-03-10T09:30:00+07:00"
~~~

Lệnh thay author date cho commit mới. Nó không đặt committer date theo giá trị đó; committer date mặc định là thời điểm amend được thực hiện.

### 5.4. Đặt author hiện tại và làm mới author date

Nếu mục tiêu là ghi nhận người đang thực hiện amend làm author, dùng:

~~~bash
git commit --amend --reset-author --no-edit
~~~

`--reset-author` đặt author theo danh tính committer hiện tại và làm mới author timestamp. Không dùng tùy chọn này nếu cần giữ người tạo thay đổi ban đầu.

### 5.5. Sửa committer identity

Nếu committer name/email của commit mới nhất sai, có thể đặt danh tính đúng cho lệnh amend bằng biến môi trường. Ví dụ trong Bash:

~~~bash
GIT_COMMITTER_NAME="Release Maintainer" \
GIT_COMMITTER_EMAIL="release@company.example" \
git commit --amend --no-edit
~~~

Author của commit amend được giữ theo commit hiện tại nếu không chỉ định `--author` hoặc `--reset-author`. Committer identity được lấy từ biến môi trường cho lần tạo commit mới này.

Nếu muốn sửa cả author và committer, kết hợp `--author` với các biến `GIT_COMMITTER_*`.

### 5.6. Sửa committer date

Để đặt committer date, dùng `GIT_COMMITTER_DATE`, không dùng `--date`.

Trong Bash:

~~~bash
GIT_COMMITTER_DATE="2025-03-12T14:15:00+07:00" \
git commit --amend --no-edit
~~~

Có thể kết hợp với author:

~~~bash
GIT_COMMITTER_DATE="2025-03-12T14:15:00+07:00" \
git commit --amend --no-edit \
  --author="Nguyen Van An <an@company.example>" \
  --date="2025-03-10T09:30:00+07:00"
~~~

Trong PowerShell, dùng biến môi trường `$env:GIT_COMMITTER_DATE` cho lệnh amend và khôi phục giá trị cũ sau khi chạy. Nếu không có nhu cầu sửa committer date, để Git ghi thời điểm thực tế của thao tác amend.

### 5.7. Sửa commit message cùng metadata

Nếu cần sửa cả message:

~~~bash
git commit --amend --author="Nguyen Van An <an@company.example>"
~~~

Git mở editor để chỉnh message. Hoặc truyền message mới:

~~~bash
git commit --amend --author="Nguyen Van An <an@company.example>" -m "Validate invoice before payment"
~~~

Không dùng `--no-edit` nếu mục tiêu bao gồm thay đổi thông điệp.

## 6. Sửa metadata của commit cũ hơn

### 6.1. Vì sao cần interactive rebase?

`git commit --amend` chỉ thay thế commit tip hiện tại. Nếu commit cần sửa nằm sâu hơn trong lịch sử, bạn có thể dùng interactive rebase để dừng tại commit đó, amend rồi phát lại các commit phía sau.

Ví dụ lịch sử:

~~~text
A --- B --- C --- D  (HEAD)
      ^
      commit B có email sai
~~~

Bạn muốn sửa B. Các commit C và D là hậu duệ của B nên khi rebase, Git phải tạo lại chúng trên commit B mới.

### 6.2. Tạo điểm khôi phục trước khi viết lại lịch sử

Trước khi bắt đầu:

~~~bash
git status --short --branch
git log --oneline --decorate
git branch backup/before-metadata-fix
~~~

Đảm bảo working tree và index sạch hoặc đã bảo toàn mọi thay đổi cần giữ. Nhánh backup giúp bạn quay lại lịch sử trước khi rewrite nếu có sự cố.

Tên backup nên phù hợp quy ước nhóm và không trùng với ref hiện có.

### 6.3. Mở interactive rebase từ cha của commit cần sửa

Nếu commit cần sửa là B:

~~~bash
git rebase -i B^
~~~

Thay B bằng hash thực tế. Git mở todo list chứa B và các commit sau nó.

Với commit gốc không có parent, dùng:

~~~bash
git rebase -i --root
~~~

Nếu lịch sử có merge commit và cần giữ topology, hãy đọc tài liệu về `--rebase-merges` và chọn cách viết lại phù hợp. Interactive rebase mặc định có thể làm thay đổi cấu trúc merge.

### 6.4. Đánh dấu commit cần sửa bằng edit

Todo list có thể có dạng:

~~~text
pick <hash-B> Add invoice validation
pick <hash-C> Add invoice tests
pick <hash-D> Update API documentation
~~~

Đổi `pick` thành `edit` ở dòng B:

~~~text
edit <hash-B> Add invoice validation
pick <hash-C> Add invoice tests
pick <hash-D> Update API documentation
~~~

Lưu và đóng editor. Rebase dừng lại tại commit B để bạn chỉnh sửa.

### 6.5. Amend commit đang được rebase

Kiểm tra commit hiện tại:

~~~bash
git log -1 --format=fuller --date=iso-strict
~~~

Sửa author:

~~~bash
git commit --amend --no-edit --author="Nguyen Van An <an@company.example>"
~~~

Hoặc sửa author và author date:

~~~bash
git commit --amend --no-edit \
  --author="Nguyen Van An <an@company.example>" \
  --date="2025-03-10T09:30:00+07:00"
~~~

Nếu cần sửa committer date, đặt `GIT_COMMITTER_DATE` chỉ cho lệnh amend. Nếu không, Git ghi committer identity và thời gian của người đang thực hiện thao tác.

### 6.6. Tiếp tục rebase

Sau khi amend:

~~~bash
git rebase --continue
~~~

Git phát lại các commit sau B. Có thể phát sinh conflict nếu các thay đổi không còn áp dụng tự động trên commit mới.

Giải quyết conflict theo quy trình thông thường, kiểm tra test rồi tiếp tục:

~~~bash
git status
git diff
git add -- path/to/resolved-file
git rebase --continue
~~~

Lặp lại nếu còn commit hoặc conflict cần xử lý.

### 6.7. Xác minh toàn bộ lịch sử sau rebase

~~~bash
git log --format=fuller --date=iso-strict --oneline
git show -s --format=fuller --date=iso-strict <new-hash>
git status --short --branch
~~~

Xác nhận:

- Commit mục tiêu có author/email/date đúng.
- Committer identity/date đúng với người thực hiện rewrite.
- Các commit con vẫn còn và đúng thứ tự.
- Nội dung tree và test không bị thay đổi ngoài dự định.
- Working tree sạch hoặc chỉ còn các thay đổi đã biết.

Nếu rebase có vấn đề và bạn chưa tiếp tục hoàn tất, có thể cân nhắc `git rebase --abort` để quay lại trạng thái trước rebase. Nhánh backup cũng giữ điểm tham chiếu cũ.

## 7. Đặt metadata cho commit mới mà không sửa lịch sử cũ

### 7.1. Dùng cấu hình local cho công việc tiếp theo

Nếu từ nay repository phải dùng danh tính khác:

~~~bash
git config --local user.name "Nguyen Van An"
git config --local user.email "an@company.example"
~~~

Các commit mới sẽ dùng danh tính này nếu không có biến môi trường hoặc tùy chọn khác ghi đè.

### 7.2. Đặt author riêng cho một commit

Có thể dùng:

~~~bash
git commit --author="Original Contributor <contributor@example.com>" -m "Apply contributor patch"
~~~

Điều này hữu ích khi bạn áp dụng patch do người khác tạo và muốn giữ thông tin author chính xác. Committer vẫn là người đang tạo commit.

### 7.3. Đặt author date cho một commit mới

~~~bash
git commit --date="2025-03-10T09:30:00+07:00" -m "Apply contributor patch"
~~~

Dùng khi author date đã được xác minh từ nguồn đáng tin cậy. Không đặt ngày giả để làm lịch sử trông cũ hơn hoặc thay đổi thứ tự công việc.

### 7.4. Không dùng cấu hình toàn cục để giả mạo một commit riêng lẻ

Thay đổi `user.name` và `user.email` global chỉ để sửa một commit có thể làm các repository khác dùng nhầm danh tính. Với thay đổi chỉ áp dụng cho một repository, dùng `--local`; với một commit đơn lẻ, dùng tùy chọn hoặc biến môi trường tương ứng.

## 8. Thời gian commit và múi giờ

### 8.1. Ưu tiên timestamp có timezone

Dạng ngày giờ nên dùng:

~~~text
2025-03-10T09:30:00+07:00
~~~

Offset `+07:00` giúp Git hiểu mốc thời gian theo múi giờ đã xác định. Nếu nhập thời gian không có timezone, kết quả có thể phụ thuộc môi trường và cách Git phân tích chuỗi.

### 8.2. Phân biệt thời gian hiển thị và thời gian lưu

Git lưu timestamp và offset. Các tùy chọn hiển thị như `--date=iso-strict` chỉ định cách trình bày, không sửa timestamp trong commit.

Ví dụ:

~~~bash
git log -1 --date=iso-strict --format=fuller
~~~

là lệnh xem dữ liệu theo định dạng rõ ràng. Nó không thay đổi author date hoặc committer date.

### 8.3. Không tự ý backdate

Có thể cần khôi phục author date chính xác từ patch hoặc hệ thống quản lý thay đổi. Khi đó hãy dùng nguồn xác minh như email patch, timestamp từ hệ thống review hoặc metadata được tổ chức lưu.

Không nên đặt ngày giờ tùy tiện để che giấu thời điểm thực hiện, vượt qua kiểm soát phát hành hoặc làm sai lệch audit trail. Commit date không phải công cụ để thay thế nhật ký thay đổi chính thức.

## 9. Hệ quả khi viết lại commit đã tồn tại

### 9.1. Commit hash thay đổi

Vì author, committer và timestamp là một phần của commit object, sửa chúng tạo hash mới ngay cả khi tree và message không đổi.

Ví dụ:

~~~text
Trước: A --- B --- C
Sau:   A --- B' --- C'
~~~

B' có metadata mới. C' được tạo lại vì parent của nó giờ là B' và do đó hash cũng thay đổi. Mọi hậu duệ tiếp theo có thể cần được tạo lại.

### 9.2. Nhánh remote có thể bị lệch lịch sử

Nếu commit đã được push và đồng đội đã dựa vào nó, rewrite lịch sử local tạo ra lịch sử khác với remote.

Không force push một cách bất ngờ. Trước khi viết lại lịch sử đã chia sẻ:

1. Trao đổi với người đang dùng branch.
2. Xác định các commit mới phát sinh sau mốc chung.
3. Tạo backup ref.
4. Thống nhất thời điểm cập nhật.
5. Push theo quy trình được nhóm cho phép, thường dùng `--force-with-lease` nếu được phê duyệt.

`--force-with-lease` giúp tránh ghi đè ref remote đã thay đổi ngoài dự kiến, nhưng không thay thế việc phối hợp với nhóm.

### 9.3. Chữ ký commit và tag

Nếu commit cũ được ký GPG/SSH, amend hoặc rebase tạo commit mới và chữ ký cũ không còn xác thực commit mới. Cần ký lại theo chính sách dự án nếu commit phải được ký.

Tag trỏ đến commit cũ không tự chuyển sang commit mới. Nếu cần di chuyển tag, phải thực hiện theo quy trình phát hành và quản trị tag; tag đã ký cũng cần được xử lý lại.

### 9.4. Các bản clone và tham chiếu khác

Viết lại branch không tự sửa:

- Clone local của thành viên khác.
- Fork.
- Pull request đang mở.
- Tag hoặc branch khác trỏ đến commit cũ.
- Artifact, log hoặc bản sao lưu đã tạo.

Vì vậy, rewrite history cần kế hoạch đồng bộ và kiểm tra mọi tham chiếu liên quan.

### 9.5. Khi nào nên giữ lịch sử cũ?

Nếu commit đã được chia sẻ rộng rãi, thuộc branch bảo vệ hoặc nằm trong bản phát hành, có thể phù hợp hơn khi giữ nguyên lịch sử và tạo commit mới giải thích hoặc sửa vấn đề liên quan.

Commit mới không sửa metadata của commit cũ, nhưng tránh buộc mọi người phải đồng bộ lịch sử đã viết lại. Hãy theo quy định của repository và yêu cầu audit.

## 10. Những sai lầm thường gặp

- **Nhầm author với committer:** người tạo thay đổi ban đầu và người tạo commit object có thể khác nhau. Kiểm tra cả hai trường.
- **Nghĩ git config sửa commit cũ:** config chỉ ảnh hưởng đến commit mới; commit đã tồn tại cần amend hoặc rewrite history.
- **Dùng --date để sửa committer date:** --date đặt author date. Dùng GIT_COMMITTER_DATE nếu thực sự cần sửa committer date.
- **Dùng --reset-author khi cần giữ tác giả ban đầu:** tùy chọn này thay author bằng danh tính hiện tại và làm mới author timestamp.
- **Amend khi index có thay đổi staged không liên quan:** thay đổi đó sẽ được đưa vào commit mới. Kiểm tra git diff --cached trước.
- **Dùng amend cho commit không phải tip:** amend chỉ thay commit hiện tại; commit cũ hơn cần interactive rebase hoặc quy trình rewrite phù hợp.
- **Quên các commit con bị đổi hash:** rebase tạo lại các hậu duệ của commit đã sửa.
- **Rewrite branch đã chia sẻ mà không báo nhóm:** có thể gây lịch sử phân kỳ và mất công đồng bộ.
- **Cho rằng tag và chữ ký tự cập nhật:** tag vẫn có thể trỏ commit cũ; chữ ký cũ không xác thực commit mới.
- **Nhập ngày không rõ timezone:** kết quả có thể không đúng mốc mong muốn. Dùng ISO 8601 kèm offset.
- **Đặt timestamp giả:** làm sai lệch lịch sử và audit trail. Chỉ sửa khi có căn cứ.

## 11. Quy trình mẫu: sửa email của commit mới nhất

Giả sử commit HEAD dùng email cũ nhưng nội dung và message đều đúng.

**Bước 1 — Kiểm tra trạng thái và metadata**

~~~bash
git status --short --branch
git diff --cached
git log -1 --format=fuller --date=iso-strict
~~~

**Bước 2 — Cấu hình danh tính đúng cho repository nếu cần**

~~~bash
git config --local user.name "Nguyen Van An"
git config --local user.email "an@company.example"
~~~

**Bước 3 — Amend author, giữ message**

~~~bash
git commit --amend --no-edit --author="Nguyen Van An <an@company.example>"
~~~

Nếu cần đặt author date chính xác, bổ sung `--date` với timestamp đã xác minh. Committer sẽ là danh tính hiện tại và thời điểm amend, trừ khi bạn chủ động đặt biến môi trường committer.

**Bước 4 — Xác minh**

~~~bash
git show -s --format=fuller --date=iso-strict HEAD
git status --short --branch
~~~

**Bước 5 — Nếu commit đã được push**

Dừng trước khi push ghi đè. Trao đổi với nhóm và xác định branch có cho phép rewrite hay không. Nếu không thể viết lại lịch sử đã chia sẻ, giữ commit cũ và xử lý theo quy trình của dự án.

## 12. Checklist trước và sau khi sửa metadata

- [ ] Đã xác định đúng commit bằng hash hoặc ref.
- [ ] Đã phân biệt author với committer.
- [ ] Đã xác định trường sai là name, email, author date hay committer date.
- [ ] Đã xác minh giá trị đúng từ nguồn đáng tin cậy.
- [ ] Đã kiểm tra working tree và index trước amend/rebase.
- [ ] Đã tạo backup ref trước khi viết lại commit cũ.
- [ ] Đã chọn amend cho tip hoặc interactive rebase cho commit cũ hơn.
- [ ] Đã hiểu commit hash và các hậu duệ sẽ thay đổi.
- [ ] Đã xem xét remote, tag, chữ ký và các clone khác.
- [ ] Đã phối hợp nếu branch đã được chia sẻ.
- [ ] Đã xác minh author/committer và cả hai timestamp sau thao tác.
- [ ] Đã chạy test phù hợp nếu có rewrite/rebase nội dung commit.
- [ ] Đã đồng bộ remote theo chính sách của nhóm.

## 13. Bảng tra cứu nhanh

| Mục tiêu | Lệnh |
| --- | --- |
| Xem author, committer và thời gian | git log -1 --format=fuller --date=iso-strict |
| Xem author email | git show -s --format=%ae HEAD |
| Xem committer email | git show -s --format=%ce HEAD |
| Xem author date | git show -s --format=%aI HEAD |
| Xem committer date | git show -s --format=%cI HEAD |
| Xem danh tính cấu hình | git config --show-origin --get user.name và user.email |
| Xem author identity hiệu lực | git var GIT_AUTHOR_IDENT |
| Xem committer identity hiệu lực | git var GIT_COMMITTER_IDENT |
| Cấu hình danh tính local | git config --local user.name / user.email |
| Sửa author commit mới nhất | git commit --amend --no-edit --author="Name <email>" |
| Sửa author date | git commit --amend --no-edit --date="ISO-8601-with-offset" |
| Đặt author theo người đang commit | git commit --amend --reset-author --no-edit |
| Sửa committer date | Đặt GIT_COMMITTER_DATE cho lệnh git commit --amend |
| Sửa commit cũ hơn | git rebase -i <commit>^ |
| Rebase từ commit gốc | git rebase -i --root |
| Tiếp tục rebase | git rebase --continue |
| Hủy rebase đang chạy | git rebase --abort |
| Xem lại lịch sử | git log --format=fuller --date=iso-strict |

## 14. Tổng kết

Git lưu author và committer cùng các mốc thời gian riêng. Author mô tả người tạo thay đổi ban đầu; committer mô tả người tạo commit object hiện tại. `--author` đặt author, `--date` đặt author date, còn các biến `GIT_COMMITTER_*` điều khiển committer metadata.

Cấu hình `user.name` và `user.email` chỉ áp dụng cho commit mới. Để sửa commit tip, dùng `git commit --amend`; để sửa commit cũ hơn, dùng interactive rebase và đánh dấu commit cần chỉnh bằng `edit`. Trước khi làm, kiểm tra index để tránh đưa thay đổi staged ngoài ý muốn, xác định đúng timestamp và tạo điểm khôi phục.

Mọi thay đổi metadata đều tạo commit hash mới. Nếu commit đã được chia sẻ, cần đánh giá tác động đến commit con, remote branch, tag, chữ ký và các bản clone. Chỉ viết lại lịch sử khi có căn cứ và đã phối hợp; nếu lịch sử cần được giữ ổn định, chọn cách xử lý theo quy ước của nhóm.

