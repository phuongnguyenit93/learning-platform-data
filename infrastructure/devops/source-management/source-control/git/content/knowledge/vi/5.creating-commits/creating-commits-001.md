# Commit chứa gì: cây tệp, commit cha, tác giả, thời gian và thông điệp

Một commit Git không đơn giản là bản sao của thư mục dự án hay một gói chứa các dòng code đã thay đổi. Commit là một object ghi lại snapshot của cây tệp, liên kết đến commit cha và lưu metadata như tác giả, người tạo commit, thời gian, thông điệp và có thể cả chữ ký số. Các thành phần này kết hợp lại tạo nên lịch sử có thể truy vết của repository.

Trong chương **Tạo commit** của module **SOURCE_CONTROL_GIT**, bài học này giải thích cấu trúc bên trong một commit và cách Git liên kết commit với tree, blob và commit cha. Bạn sẽ biết vì sao author khác committer, merge commit có nhiều parent, timestamp không quyết định thứ tự lịch sử, và vì sao chỉ một thay đổi nhỏ trong metadata cũng có thể tạo ra commit ID hoàn toàn khác.

Sau bài học, bạn có thể:

- Mô tả các trường chính trong một commit object.
- Giải thích commit trỏ đến tree snapshot thay vì lưu trực tiếp diff.
- Phân biệt commit cha với cây tệp mà commit ghi nhận.
- Đọc quan hệ parent của commit thường, root commit và merge commit.
- Phân biệt author, committer, ngày tác giả và ngày tạo commit.
- Giải thích vai trò của commit message, body và trailers.
- Dùng git cat-file, git show, git log, git rev-list và git ls-tree để kiểm tra cấu trúc commit.
- Hiểu commit ID được tạo từ toàn bộ nội dung object và vì sao amend/rebase tạo ID mới.

## 1. Commit là một object có cấu trúc

Git lưu dữ liệu trong object database. Những loại object cơ bản gồm:

| Object | Vai trò |
| --- | --- |
| blob | Lưu nội dung file |
| tree | Lưu danh sách entry trong một thư mục: tên, mode và object ID |
| commit | Ghi nhận một tree snapshot, parent và metadata lịch sử |
| tag | Lưu metadata của annotated tag và trỏ đến object khác |

Một commit object thường có các thành phần:

~~~text
tree <tree-object-id>
parent <parent-commit-id>
author <name> <email> <timestamp> <timezone>
committer <name> <email> <timestamp> <timezone>

<commit message>
~~~

Commit có thể có nhiều dòng parent nếu là merge commit. Root commit không có dòng parent. Ngoài các trường chính, object có thể chứa header khác như encoding, chữ ký GPG/SSH hoặc mergetag.

Điểm quan trọng: commit trỏ đến một tree object đại diện cho toàn bộ snapshot của repository tại thời điểm commit. Tree lại trỏ đến blob và tree con. Commit không lưu một bản diff dạng các dòng cộng/trừ. Diff được Git tính ra khi so sánh tree của hai commit.

## 2. Tree là snapshot của cây thư mục

Trường tree trong commit chứa object ID của tree ở thư mục gốc. Tree mô tả cấu trúc file tại commit đó.

Ví dụ một tree có thể chứa:

~~~text
100644 blob  1a2b3c...  README.md
100644 blob  4d5e6f...  app.js
100755 blob  7a8b9c...  scripts/build.sh
040000 tree  0a1b2c...  src
~~~

Các trường quan trọng:

- Mode cho biết loại entry và một số thuộc tính file.
- Loại object cho biết entry trỏ đến blob hay tree.
- Object ID xác định nội dung hoặc cây con.
- Tên entry là tên file hoặc thư mục trong tree.

Một số mode thường gặp:

| Mode | Ý nghĩa |
| --- | --- |
| 100644 | File thông thường không có quyền thực thi |
| 100755 | File thông thường có quyền thực thi |
| 120000 | Symbolic link; blob chứa đường dẫn đích |
| 040000 | Tree con, đại diện thư mục |
| 160000 | Gitlink, tham chiếu commit của submodule |

Tree không lưu đường dẫn tuyệt đối của file. Mỗi tree lưu các entry trực tiếp bên trong nó; Git đi qua các tree con để tìm đường dẫn đầy đủ.

### Xem tree của commit

Lấy object ID của tree mà HEAD trỏ đến:

~~~bash
git rev-parse 'HEAD^{tree}'
~~~

Liệt kê entry ở thư mục gốc:

~~~bash
git ls-tree HEAD
~~~

Liệt kê đệ quy mọi file:

~~~bash
git ls-tree -r HEAD
~~~

Xem nội dung một tree object:

~~~bash
git cat-file -p 'HEAD^{tree}'
~~~

Nếu muốn xem nội dung file tại commit:

~~~bash
git show HEAD:src/app.js
~~~

Git tìm entry src/app.js trong tree của HEAD rồi đọc blob tương ứng. Nếu file thay đổi giữa hai commit, blob có thể có object ID khác; nếu nội dung giống hệt và không bị bộ lọc làm thay đổi, Git có thể tái sử dụng cùng blob.

## 3. Commit ghi snapshot, không ghi danh sách dòng thay đổi

Giả sử commit A có tree T1 và commit B có tree T2:

~~~text
Commit A                  Commit B
   |                         |
   v                         v
 Tree T1                   Tree T2
   |                         |
   +-- README.md             +-- README.md
   +-- app.js                +-- app.js
   +-- config.json           +-- config.json
~~~

Commit B thường lưu tree snapshot T2 và parent là A. Khi bạn chạy git show hoặc git diff để xem thay đổi giữa A và B, Git so sánh T1 với T2 và tính ra phần khác biệt.

Điều này có một số hệ quả:

- Một commit chứa trạng thái đầy đủ của cây tệp, kể cả những file không thay đổi so với parent thông qua việc tái sử dụng object.
- Commit không cần lưu lại bản sao mới của mọi file nếu blob/tree không thay đổi.
- Có thể so sánh bất kỳ hai commit nào, kể cả khi chúng không nằm trực tiếp cạnh nhau.
- Một commit có thể có tree giống parent nhưng vẫn là commit riêng, ví dụ empty commit.

Tạo empty commit:

~~~bash
git commit --allow-empty -m "chore: mark maintenance checkpoint"
~~~

Tree của commit mới có thể giống tree của parent, nhưng commit object vẫn khác vì parent, metadata hoặc thông điệp khác. Empty commit đôi khi hữu ích cho automation hoặc đánh dấu sự kiện, nhưng không nên tạo nếu không có mục đích rõ ràng.

## 4. Commit cha tạo thành đồ thị lịch sử

Trường parent liên kết commit mới với commit trước đó. Commit thông thường có một parent:

~~~text
A --- B --- C
          ^
          HEAD
~~~

Commit C ghi parent là B. Git có thể đi ngược theo các liên kết parent để dựng lịch sử.

### Root commit

Commit đầu tiên của một lịch sử không có parent:

~~~text
Root
  |
  v
  A --- B
~~~

Trong object của root commit không có dòng parent. Repository có thể có nhiều root commit nếu lịch sử được tạo độc lập rồi kết hợp bằng cách khác.

### Merge commit

Khi hợp nhất hai nhánh, Git thường tạo commit có ít nhất hai parent:

~~~text
       A1 --- A2
      /        \
Base             M
      \        /
       B1 --- B2
~~~

Merge commit M có hai parent. Parent thứ nhất thường là tip của branch đang checkout khi chạy merge; parent thứ hai là commit được merge vào. Với octopus merge, commit có thể có nhiều hơn hai parent.

Thứ tự parent có ý nghĩa với một số lệnh như HEAD^1, HEAD^2 và cách hiển thị first-parent history. Không nên xem merge commit chỉ là một commit chứa thay đổi kết hợp; nó còn ghi nhận các lịch sử nào đã được nối lại.

### Xem parent của commit

Hiển thị commit cùng parent:

~~~bash
git rev-list --parents -n 1 HEAD
~~~

Chỉ lấy các parent OID:

~~~bash
git show -s --format=%P HEAD
~~~

Lấy tree OID:

~~~bash
git show -s --format=%T HEAD
~~~

Đếm số parent bằng cách đọc output của %P hoặc dùng git cat-file -p HEAD. Không có parent nghĩa là root commit; một parent là commit thường; từ hai parent trở lên là merge commit.

## 5. Commit không chứa tên branch

Branch không được ghi bên trong commit object. Branch là một ref có thể di chuyển, trỏ đến commit hiện tại của branch.

Ví dụ:

~~~text
refs/heads/main -----------+
                           |
refs/heads/release --------+----> Commit C
                           |
HEAD ---------------------+
~~~

Nhiều ref có thể cùng trỏ đến một commit. Khi branch tiến lên commit mới, ref thay đổi nhưng commit cũ vẫn tồn tại nếu còn được tham chiếu hoặc chưa bị garbage collection.

Kiểm tra ref:

~~~bash
git show-ref --heads
git branch --contains HEAD
git rev-parse HEAD
~~~

Commit object không ghi tên branch đã tạo ra nó, remote URL, trạng thái working tree hay staging area tại thời điểm sau commit. Những thông tin đó thuộc ref, cấu hình hoặc trạng thái repository bên ngoài commit.

## 6. Author và committer là hai vai trò khác nhau

Một commit thường có hai trường danh tính:

- **author**: người viết thay đổi ban đầu được ghi nhận trong commit.
- **committer**: người hoặc tiến trình tạo ra commit object hiện tại.

Trong tình huống đơn giản, cùng một người vừa viết vừa commit nên hai trường giống nhau. Nhưng khi commit được áp dụng, viết lại hoặc tạo bởi automation, chúng có thể khác.

Ví dụ:

~~~text
author Alice Nguyen <alice@example.com> 1763371200 +0700
committer Bob Tran <bob@example.com> 1763457600 +0700
~~~

Trong ví dụ này, Alice là tác giả của thay đổi; Bob là người tạo commit object được lưu trong repository. Timestamp chỉ mang tính minh họa.

### Các tình huống thường gặp

| Thao tác | Author | Committer |
| --- | --- | --- |
| Tạo commit thông thường | Người tạo thay đổi | Người chạy git commit |
| Cherry-pick | Thường giữ author của commit được chọn | Người chạy cherry-pick |
| Rebase | Thường giữ thông tin author của commit được phát lại | Người tạo commit mới trong quá trình rebase |
| Áp dụng mailbox bằng git am | Theo metadata author trong patch | Người áp dụng patch |
| Tạo commit bằng CI/bot | Có thể là tác giả được chỉ định | Bot hoặc tài khoản chạy job |

Đây là hành vi mặc định phổ biến; các tùy chọn và biến môi trường có thể thay đổi metadata. Ví dụ --reset-author hoặc các biến GIT_AUTHOR_* có thể thay đổi author.

### Xem author và committer

~~~bash
git show -s --format=fuller HEAD
~~~

Output fuller hiển thị Author, AuthorDate, Commit, CommitDate và thông điệp. Có thể lấy riêng từng trường:

~~~bash
git show -s --format='%an <%ae>' HEAD
git show -s --format='%cn <%ce>' HEAD
git show -s --format='%aI' HEAD
git show -s --format='%cI' HEAD
~~~

Trong format:

- %an và %ae là author name/email.
- %cn và %ce là committer name/email.
- %aI là author date theo ISO 8601 nghiêm ngặt.
- %cI là committer date theo ISO 8601 nghiêm ngặt.

## 7. Timestamp và múi giờ

Trong commit object, author và committer date được lưu dưới dạng:

~~~text
<Unix timestamp> <timezone offset>
~~~

Ví dụ:

~~~text
author Linh Le <linh@example.com> 1763371200 +0700
committer Linh Le <linh@example.com> 1763371500 +0700
~~~

Timestamp là số giây tính từ Unix epoch. Phần timezone offset cho biết độ lệch múi giờ tại thời điểm được ghi, ví dụ +0700 là UTC+7. Git không lưu một tên vùng như Asia/Ho_Chi_Minh trong trường này.

Author date và committer date có thể khác nhau. Author date thường phản ánh thời điểm thay đổi được tạo ra; committer date phản ánh thời điểm commit object hiện tại được tạo.

### Timestamp không quyết định thứ tự lịch sử

Thứ tự lịch sử được xác định bởi các liên kết parent, không phải chỉ bằng timestamp. Đồng hồ máy có thể sai, commit có thể được nhập từ máy khác hoặc date có thể được chỉ định lại. Vì vậy:

- Commit có timestamp mới hơn chưa chắc là hậu duệ của commit có timestamp cũ hơn.
- Hai commit ở hai nhánh có thể có thời gian chồng lấn hoặc đảo thứ tự.
- git log mặc định có cách sắp xếp lịch sử dựa trên đồ thị và tùy chọn hiển thị; không nên suy ra quan hệ ancestor chỉ từ ngày.

Để kiểm tra quan hệ tổ tiên, dùng:

~~~bash
git merge-base --is-ancestor <older> <newer>
~~~

Lệnh trả mã 0 nếu older là ancestor của newer. Đây là kiểm tra quan hệ lịch sử dựa trên parent graph, phù hợp hơn việc so sánh timestamp.

## 8. Git lấy danh tính và thời gian từ đâu?

Danh tính mặc định thường đến từ Git config:

~~~bash
git config --global user.name "Linh Le"
git config --global user.email "linh@example.com"
~~~

Kiểm tra nguồn cấu hình:

~~~bash
git config --show-origin --get user.name
git config --show-origin --get user.email
~~~

Git cũng nhận các biến môi trường có thể ghi đè giá trị cấu hình:

| Biến | Trường được ảnh hưởng |
| --- | --- |
| GIT_AUTHOR_NAME | Author name |
| GIT_AUTHOR_EMAIL | Author email |
| GIT_AUTHOR_DATE | Author date |
| GIT_COMMITTER_NAME | Committer name |
| GIT_COMMITTER_EMAIL | Committer email |
| GIT_COMMITTER_DATE | Committer date |

Các biến này thường được dùng trong script, CI hoặc khi cần tái tạo metadata. Không nên đặt chúng lâu dài ở cấp người dùng nếu không có chủ đích, vì commit sau đó có thể ghi sai danh tính hoặc thời gian.

### Chỉ định author date cho một commit

Có thể dùng tùy chọn --date:

~~~bash
git commit --date="2026-11-17T09:30:00+07:00" -m "docs: add setup guide"
~~~

--date chỉ định author date cho commit. Committer date vẫn phản ánh thời điểm tạo commit, trừ khi được điều khiển riêng qua môi trường. Hãy tránh thay đổi thời gian chỉ để làm lịch sử trông đẹp hơn; metadata nên phản ánh đúng nguồn gốc và quy trình.

## 9. Commit message gồm subject, body và trailers

Sau các header metadata, commit object có một dòng trống rồi đến commit message.

Một message thường có cấu trúc:

~~~text
fix(auth): reject expired session tokens

Check the token expiry before loading the user session.
Return a clear error so clients can refresh credentials.

Reviewed-by: Minh Nguyen <minh@example.com>
Issue: AUTH-142
~~~

Các phần:

- **Subject**: dòng đầu, ngắn gọn mô tả mục đích thay đổi.
- **Body**: giải thích bối cảnh, lý do và tác động nếu cần.
- **Trailers**: các dòng metadata theo quy ước ở cuối message.

Git lưu message như nội dung văn bản của commit object. Git không tự hiểu mọi từ trong subject hay body; nhiều quy tắc như Conventional Commits, Issue ID hoặc Reviewed-by là quy ước của nhóm và công cụ.

### Trailer không phải header của commit object

Các dòng như Signed-off-by, Co-authored-by, Reviewed-by hoặc Issue thường nằm trong message body. Chúng khác với header author, committer và chữ ký mật mã ở phần đầu commit object.

Ví dụ:

- Signed-off-by là một trailer theo quy ước Developer Certificate of Origin (DCO), không tự nó là chữ ký GPG/SSH.
- Co-authored-by ghi nhận người đồng tác giả theo quy ước mà nền tảng có thể nhận diện.
- Chữ ký commit được lưu dưới dạng header chữ ký trong commit object, được Git kiểm tra bằng verify-commit.

Tạo commit có trailer sign-off:

~~~bash
git commit -s -m "fix(api): validate request body"
~~~

Tùy chọn -s thêm trailer Signed-off-by dựa trên danh tính committer. Nó không giống -S, tùy chọn yêu cầu ký commit bằng khóa GPG/SSH đã cấu hình.

## 10. Header chữ ký và encoding trong commit object

Commit object có thể chứa các header ngoài tree, parent, author và committer.

Ví dụ:

~~~text
tree 1a2b3c...
parent 4d5e6f...
author Linh Le <linh@example.com> 1763371200 +0700
committer Linh Le <linh@example.com> 1763371500 +0700
gpgsig -----BEGIN PGP SIGNATURE-----
 ...
 -----END PGP SIGNATURE-----

fix(auth): reject expired token
~~~

Chữ ký có thể dùng OpenPGP hoặc SSH tùy cấu hình Git. Header chữ ký gắn với nội dung commit; thay đổi nội dung commit sau đó sẽ làm chữ ký cũ không còn khớp.

Một commit cũng có thể có header encoding nếu message được ghi bằng encoding khác mặc định. Phần lớn workflow hiện đại dùng UTF-8. Không nên tự chỉnh sửa raw commit object vì chỉ một thay đổi byte cũng làm thay đổi object ID và có thể phá vỡ chữ ký.

Kiểm tra chữ ký:

~~~bash
git verify-commit HEAD
~~~

Xem commit object:

~~~bash
git cat-file -p HEAD
~~~

## 11. Commit ID được tạo như thế nào?

Git object được định danh bằng hash của object header và payload. Với commit, dữ liệu được hash bao gồm loại object, kích thước và nội dung commit object. Vì vậy, commit ID phụ thuộc vào:

- Tree OID.
- Tất cả parent OID và thứ tự của chúng.
- Author name/email/date.
- Committer name/email/date.
- Commit message.
- Các header khác như encoding và chữ ký.

Nếu bất kỳ thành phần nào thay đổi, object ID của commit thay đổi. Repository SHA-1 và SHA-256 có object format khác nhau, nên không nên giả định mọi commit ID có cùng độ dài.

Kiểm tra:

~~~bash
git rev-parse --show-object-format
git rev-parse HEAD
git cat-file -t HEAD
git cat-file -s HEAD
~~~

- --show-object-format cho biết định dạng hash của repository.
- rev-parse HEAD in object ID.
- cat-file -t xác nhận object có loại commit.
- cat-file -s hiển thị kích thước payload của object.

Không có hai commit khác nội dung nhưng cùng ID trong điều kiện an toàn mật mã của object format; Git dựa vào content-addressed storage để nhận diện và tái sử dụng object.

## 12. Vì sao amend và rebase tạo commit ID mới?

Commit object được xem là bất biến. Khi bạn sửa commit, Git tạo một object mới với nội dung hoặc metadata mới.

### Amend

~~~bash
git commit --amend
~~~

Amend tạo commit mới thay cho commit tip hiện tại của branch. Tree có thể thay đổi nếu index khác; message có thể thay đổi; committer date và metadata có thể được cập nhật. Ngay cả khi tree giữ nguyên, commit ID thường vẫn đổi vì metadata hoặc message thay đổi.

Nếu cần giữ author như commit cũ, Git thường giữ author information theo mặc định. Tùy chọn --reset-author yêu cầu đặt lại author theo người đang tạo commit mới.

### Rebase

Rebase phát lại các commit lên base mới. Mỗi commit được tạo lại có parent mới, nên object ID thay đổi ngay cả khi nội dung file sau từng bước giống với commit cũ.

~~~text
Trước rebase:

      A --- B (feature)
     /
Base
     \
      C --- D (main)

Sau khi rebase feature lên main:

Base --- C --- D --- A' --- B'
~~~

A' và B' là commit object mới. Chúng có parent mới và thường có committer date mới; author information thường được giữ lại. Không dùng hash cũ để nhận diện commit mới sau rebase.

### Cherry-pick

Cherry-pick cũng tạo commit mới trên branch hiện tại. Nội dung thay đổi có thể tương đương commit nguồn, nhưng parent và committer metadata khác nên commit ID khác.

## 13. Merge commit lưu nhiều parent

Khi merge hai nhánh mà cần tạo merge commit, Git ghi nhiều dòng parent trong commit object:

~~~text
tree <result-tree>
parent <current-branch-tip>
parent <merged-branch-tip>
author ...
committer ...

Merge branch 'feature/search'
~~~

Tree là kết quả sau khi hợp nhất. Hai parent lưu hai lịch sử đã được nối. Nếu merge có conflict, bạn giải quyết conflict trước; tree trong merge commit lưu kết quả cuối cùng, không lưu riêng các marker conflict đã được xử lý.

Xem commit merge:

~~~bash
git cat-file -p HEAD
git rev-list --parents -n 1 HEAD
git show --cc HEAD
~~~

--cc hiển thị combined diff cho merge commit trong những trường hợp phù hợp. Một merge commit không nhất thiết có diff dễ đọc theo cách so sánh với một parent đơn lẻ; hãy xác định rõ bạn muốn so với parent nào.

## 14. Đọc commit object theo từng lớp

Giả sử HEAD là commit bạn muốn điều tra. Có thể dùng quy trình:

### Bước 1: xác nhận loại object và kích thước

~~~bash
git cat-file -t HEAD
git cat-file -s HEAD
~~~

Kết quả mong đợi của loại object là commit.

### Bước 2: đọc header và message

~~~bash
git cat-file -p HEAD
~~~

Tìm các dòng tree, parent, author, committer và phần message sau dòng trống. Nếu có gpgsig hoặc header khác, chú ý chúng là metadata của object.

### Bước 3: kiểm tra tree

~~~bash
git show -s --format=%T HEAD
git ls-tree HEAD
~~~

Xem snapshot root và các entry. Dùng -r nếu muốn liệt kê đệ quy.

### Bước 4: kiểm tra parent

~~~bash
git show -s --format=%P HEAD
git log --graph --oneline --decorate -10
~~~

Xác định commit có bao nhiêu parent và vị trí của nó trong đồ thị lịch sử.

### Bước 5: kiểm tra danh tính và message

~~~bash
git show -s --format=fuller HEAD
git show -s --format=%B HEAD
~~~

So sánh author/committer, ngày và thông điệp. Nếu metadata khác kỳ vọng, kiểm tra config và biến môi trường trong tiến trình tạo commit.

## 15. Phân biệt commit, tree và diff

| Thành phần | Lưu gì? | Có lưu parent không? | Có lưu message không? |
| --- | --- | --- | --- |
| Commit | Tree OID, parent, author/committer, thời gian, message và header khác | Có | Có |
| Tree | Danh sách entry, mode, tên và OID của blob/tree con | Không | Không |
| Blob | Nội dung file | Không | Không |
| Diff | Kết quả so sánh hai trạng thái | Không phải object commit mặc định | Không |

Một commit không lưu toàn bộ diff so với parent. Git tạo diff bằng cách so sánh tree của commit với tree của parent hoặc một commit khác. Vì vậy, cùng một commit có thể được so sánh với nhiều mốc khác nhau và tạo ra các diff khác nhau.

Ví dụ:

~~~bash
git diff HEAD^ HEAD
git diff main HEAD
git diff HEAD~3 HEAD
~~~

Các lệnh trên chọn những cặp snapshot khác nhau để so sánh. Với merge commit, hãy chỉ định parent rõ ràng nếu muốn biết thay đổi so với một nhánh cụ thể.

## 16. Những nhầm lẫn thường gặp

### Commit là bản sao toàn bộ thư mục?

Commit trỏ đến tree snapshot. Tree tham chiếu blob và tree con; Git tái sử dụng object không thay đổi. Không phải mỗi commit đều sao chép lại toàn bộ nội dung file.

### Commit lưu diff so với commit cha?

Không. Commit lưu tree OID và parent OID. Diff được tính khi so sánh các tree.

### Author và committer luôn là một người?

Không. Khi cherry-pick, rebase, git am hoặc automation, author có thể là người viết thay đổi ban đầu còn committer là người tạo commit object hiện tại.

### Commit date quyết định commit nào đứng trước?

Không. Quan hệ lịch sử được quyết định bởi parent graph. Timestamp có thể lệch do đồng hồ, nhập lịch sử hoặc metadata được chỉ định.

### Branch name nằm trong commit?

Không. Branch là ref trỏ đến commit. Một commit có thể được nhiều branch hoặc tag cùng tham chiếu.

### Merge commit chỉ có một parent?

Không. Merge commit thông thường có ít nhất hai parent; root commit không có parent.

### Signed-off-by là chữ ký mật mã?

Không. Signed-off-by là trailer trong commit message theo một quy ước. Chữ ký mật mã được lưu trong header chữ ký và xác minh bằng git verify-commit.

### Sửa message bằng amend có giữ nguyên commit ID?

Không. Message là một phần của commit object. Thay đổi message tạo object mới và ID mới.

## 17. Tự kiểm tra

Bạn đang kiểm tra một commit có output rút gọn như sau:

~~~text
tree 111aaa...
parent 222bbb...
parent 333ccc...
author An Nguyen <an@example.com> 1763371200 +0700
committer Binh Tran <binh@example.com> 1763457600 +0700

Merge feature/payment
~~~

Hãy trả lời:

1. Commit này trỏ đến object nào để mô tả snapshot?
2. Có bao nhiêu parent và điều đó gợi ý loại commit nào?
3. Ai là author và ai là committer?
4. Hai timestamp có ý nghĩa gì?
5. Commit object có lưu diff so với parent không?
6. Nếu chỉ sửa commit message bằng amend, vì sao commit ID thay đổi?
7. Lệnh nào xem tree entry và lệnh nào xem raw commit object?

**Gợi ý:** Tree OID là snapshot root. Hai dòng parent cho thấy merge commit có hai parent. An là author, Binh là committer. Timestamp đi cùng timezone offset, author date và committer date có thể khác. Commit lưu tree và parent, còn diff được tính khi so sánh tree. Message là một phần nội dung commit nên amend tạo object ID mới. Dùng git ls-tree HEAD để xem tree entry và git cat-file -p HEAD để đọc commit object.

## Kết luận

Commit Git là một object liên kết tree snapshot với một hoặc nhiều parent và ghi lại author, committer, thời gian, thông điệp cùng các header khác. Tree mô tả file và thư mục bằng blob/tree object; commit không lưu diff mà Git tính ra khi so sánh snapshot. Author ghi nhận người tạo thay đổi ban đầu, committer ghi nhận người hoặc tiến trình tạo commit object hiện tại. Parent graph xác định quan hệ lịch sử, còn timestamp chỉ là metadata thời gian. Dùng git cat-file, git show, git rev-list và git ls-tree để kiểm tra từng thành phần; nhớ rằng thay đổi tree, parent, danh tính, thời gian, message hoặc chữ ký đều có thể tạo commit ID mới.
