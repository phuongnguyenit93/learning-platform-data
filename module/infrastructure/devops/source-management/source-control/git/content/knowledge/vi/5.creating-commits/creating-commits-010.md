# Kiểm tra mã định danh và nội dung commit vừa tạo bằng git show

Sau khi chạy `git commit`, bạn cần xác nhận commit đã được tạo đúng: mã định danh nào được sinh ra, commit có author/committer nào, message có chính xác không, những tệp nào đã thay đổi và nội dung patch có đúng với mục tiêu hay không. Lệnh `git show` là công cụ trực tiếp để đọc một commit cùng metadata và nội dung thay đổi của nó.

Với commit mới nhất, `git show` thường dùng `HEAD` làm đối tượng cần xem. Bạn có thể chọn cách hiển thị đầy đủ patch, chỉ metadata, thống kê, danh sách tệp hoặc dữ liệu thô. Khi cần kiểm tra một tệp, có hai cú pháp cần phân biệt: `git show HEAD -- path/to/file` hiển thị phần thay đổi của tệp trong commit; `git show HEAD:path/to/file` hiển thị toàn bộ nội dung tệp được lưu trong snapshot đó.

Bài học này hướng dẫn cách xác định commit ID, đọc metadata, kiểm tra patch và danh sách tệp, xem nội dung tệp tại commit, so sánh với parent, xử lý merge commit và nhận biết giới hạn với file nhị phân, submodule và Git LFS.

## 1. git show dùng để làm gì?

### 1.1. Xem một đối tượng Git

Cú pháp tổng quát:

~~~bash
git show [options] <object>
~~~

`<object>` có thể là:

- Commit: `HEAD`, hash commit, branch hoặc tag.
- Annotated tag: Git hiển thị thông tin tag và đối tượng được tag trỏ tới.
- Tree: hiển thị các mục trong cây.
- Blob: hiển thị nội dung đối tượng file.

Trong workflow tạo commit, đối tượng thường dùng nhất là `HEAD`, vì HEAD trỏ đến commit hiện tại sau khi commit thành công.

Ví dụ:

~~~bash
git show HEAD
~~~

Với một commit thông thường, đầu ra bao gồm thông tin commit và diff của commit đó so với parent. Commit đầu tiên không có parent; Git có thể trình bày nội dung của nó như phần thêm mới so với một cây rỗng.

### 1.2. git show không tạo hoặc sửa commit

`git show` là lệnh đọc. Nó không thay đổi:

- HEAD hoặc branch hiện tại.
- Index (staging area).
- Working tree.
- Commit message hoặc metadata.
- Remote repository.

Vì vậy, bạn có thể dùng nó để kiểm tra sau commit mà không làm thay đổi trạng thái repository.

### 1.3. Phân biệt git show và git status

| Lệnh | Mục đích |
| --- | --- |
| `git status` | Cho biết branch, staged, unstaged và untracked changes hiện tại |
| `git show HEAD` | Đọc commit hiện tại, metadata và thay đổi của commit |
| `git log` | Duyệt danh sách commit trong lịch sử |
| `git diff` | So sánh hai trạng thái hoặc hai tree |
| `git show HEAD:path` | Đọc nội dung một file trong snapshot của commit |

Một repository có thể clean sau commit nhưng bạn vẫn cần `git show` để xác nhận nội dung commit vừa tạo. Ngược lại, `git status` cho biết còn thay đổi nào chưa commit hay không, chứ không giải thích đầy đủ nội dung của commit.

## 2. Xác định commit vừa tạo

### 2.1. HEAD là commit hiện tại

Sau khi lệnh `git commit` thành công, HEAD thường được cập nhật đến commit mới trên branch hiện tại.

Kiểm tra commit mới nhất:

~~~bash
git log -1 --oneline --decorate
git show --no-patch --oneline HEAD
~~~

Ví dụ đầu ra:

~~~text
a81c9f2 (HEAD -> feature/billing) Validate billing address before checkout
~~~

Trong ví dụ:

- `a81c9f2` là mã commit rút gọn.
- `HEAD -> feature/billing` cho biết branch hiện tại đang trỏ đến commit đó.
- Phần còn lại là subject của commit.

### 2.2. Lấy commit ID đầy đủ

Dùng:

~~~bash
git rev-parse --verify HEAD^{commit}
~~~

Hoặc:

~~~bash
git show -s --format=%H HEAD
~~~

Kết quả là object ID đầy đủ của commit. Độ dài ID phụ thuộc object format của repository; không nên mặc định mọi repository đều dùng chuỗi 40 ký tự.

Kiểm tra object format:

~~~bash
git rev-parse --show-object-format
~~~

Repository có thể dùng SHA-1 hoặc SHA-256. Khi lưu mã commit trong ticket, release note hoặc báo cáo, dùng giá trị đầy đủ để tránh nhầm lẫn giữa các hash rút gọn.

### 2.3. Mã rút gọn có thể thay đổi theo ngữ cảnh

Một mã rút gọn thường đủ để Git phân giải commit nếu không bị trùng với object khác. Độ dài rút gọn có thể thay đổi theo số lượng object trong repository và cấu hình.

Để ghi nhận chính xác commit vừa tạo:

~~~bash
git show -s --format="%H" HEAD
~~~

Không cắt hash thủ công khi cần lưu bằng chứng hoặc liên kết giữa các hệ thống.

### 2.4. Xác nhận commit thuộc branch mong muốn

~~~bash
git status --short --branch
git branch --show-current
git log -1 --decorate --oneline
~~~

Nếu bạn đang ở detached HEAD, `git show HEAD` vẫn hiển thị commit hiện tại nhưng commit mới có thể chưa được gắn vào branch mà bạn dự định. Hãy kiểm tra branch trước khi tiếp tục push hoặc tạo pull request.

## 3. Đọc thông tin commit và danh tính

### 3.1. Xem metadata đầy đủ bằng --format=fuller

~~~bash
git show --format=fuller --no-patch HEAD
~~~

Đầu ra có thể giống:

~~~text
commit a81c9f2...
Author:     Nguyen Van An <an@company.example>
AuthorDate: Mon Mar 10 09:30:00 2025 +0700
Commit:     Nguyen Van An <an@company.example>
CommitDate: Mon Mar 10 10:05:00 2025 +0700

    Validate billing address before checkout
~~~

Các trường quan trọng:

- Dòng `commit`: mã định danh của commit object.
- Author: người được ghi nhận tạo thay đổi.
- AuthorDate: thời điểm author được ghi nhận tạo thay đổi.
- Dòng `Commit:` trong phần metadata: danh tính committer, người tạo commit object hiện tại.
- CommitDate: thời điểm commit object được tạo.
- Message: thông điệp commit.

Author và committer có thể khác nhau khi cherry-pick, rebase hoặc áp dụng patch từ người khác.

Các trường author và email là metadata do người tạo commit cung cấp; bản thân chúng không chứng minh danh tính ngoài đời hoặc quyền sở hữu tài khoản. Nếu repository yêu cầu commit đã ký, có thể kiểm tra chữ ký bằng:

~~~bash
git verify-commit HEAD
~~~

Kết quả xác minh chữ ký còn phụ thuộc khóa công khai và chính sách tin cậy đã được thiết lập. Một chữ ký hợp lệ xác nhận commit được ký bằng khóa tương ứng; nó không tự chứng minh mọi thông tin author trong metadata là đúng.

### 3.2. Hiển thị timestamp theo ISO 8601

~~~bash
git show --format=fuller --date=iso-strict --no-patch HEAD
~~~

Định dạng ISO strict giúp đọc ngày giờ cùng offset múi giờ, ví dụ:

~~~text
AuthorDate: 2025-03-10T09:30:00+07:00
CommitDate: 2025-03-10T10:05:00+07:00
~~~

Dùng định dạng này khi đối chiếu với hệ thống review, ticket hoặc log phát hành có lưu timestamp.

### 3.3. Chỉ in các trường cần thiết

Có thể tự định dạng đầu ra:

~~~bash
git show -s --format="Commit: %H%nTree: %T%nParents: %P%nAuthor: %an <%ae>%nAuthor date: %aI%nCommitter: %cn <%ce>%nCommitter date: %cI%nSubject: %s" HEAD
~~~

Các placeholder thường dùng:

| Placeholder | Ý nghĩa |
| --- | --- |
| `%H` | Commit hash đầy đủ |
| `%h` | Commit hash rút gọn |
| `%T` | Tree hash của snapshot |
| `%P` | Hash của các parent |
| `%an` | Author name |
| `%ae` | Author email |
| `%aI` | Author date theo ISO 8601 strict |
| `%cn` | Committer name |
| `%ce` | Committer email |
| `%cI` | Committer date theo ISO 8601 strict |
| `%s` | Subject |
| `%b` | Body của commit message |

Tùy chọn `-s` hoặc `--no-patch` yêu cầu không hiển thị diff. Đây là cách phù hợp khi chỉ cần metadata.

### 3.4. Xem dữ liệu commit ở dạng raw

~~~bash
git show --format=raw --no-patch HEAD
~~~

Dạng raw giúp thấy rõ:

- Tree object mà commit tham chiếu.
- Parent commit hoặc các parent.
- Author và timestamp.
- Committer và timestamp.

Có thể đọc trực tiếp object:

~~~bash
git cat-file -p HEAD
~~~

`git cat-file -p` là plumbing command hiển thị nội dung object. `git show` thuận tiện hơn cho việc đọc commit theo góc nhìn người dùng và có thể trình bày diff.

### 3.5. Kiểm tra message

~~~bash
git show -s --format=%B HEAD
~~~

`%B` hiển thị toàn bộ commit message, gồm subject và body. Dùng để xác nhận message không bị cắt, thiếu phần giải thích hoặc chứa thông tin không nên đưa vào lịch sử.

Nếu message có tham chiếu issue, mã ticket hoặc quy ước Conventional Commits, kiểm tra đúng định dạng của dự án.

## 4. Xem nội dung thay đổi của commit

### 4.1. Xem commit cùng patch mặc định

~~~bash
git show HEAD
~~~

Đầu ra thường gồm commit metadata và patch so sánh snapshot của commit với parent.

Patch dùng:

- Dòng bắt đầu bằng dấu trừ: nội dung có trong parent nhưng bị loại.
- Dòng bắt đầu bằng dấu cộng: nội dung được thêm trong commit.
- Dòng không có dấu cộng/trừ: context giúp định vị thay đổi.

Ví dụ:

~~~diff
-    if (address == null) {
-        return true;
-    }
+    if (address == null || address.isBlank()) {
+        return false;
+    }
~~~

Hãy đọc cả context xung quanh để hiểu thay đổi trong luồng xử lý, không chỉ nhìn các dòng được thêm hoặc xóa.

### 4.2. Kết hợp metadata và patch

~~~bash
git show --format=fuller --patch HEAD
~~~

Đây là lựa chọn hữu ích khi review commit vừa tạo: phần đầu cho biết ai tạo commit và khi nào, phần sau cho biết nội dung thay đổi.

Nếu output quá dài, có thể dùng thống kê hoặc giới hạn đường dẫn trước khi đọc toàn bộ.

### 4.3. Chỉ xem patch, ẩn phần metadata

~~~bash
git show --format= --patch HEAD
~~~

Format rỗng làm phần header commit không được in, còn patch vẫn được hiển thị. Cách này phù hợp khi muốn tập trung vào nội dung thay đổi hoặc đưa patch vào một bước xử lý khác.

### 4.4. Xem word diff

~~~bash
git show --word-diff HEAD -- docs/api/checkout.md
~~~

Word diff làm nổi bật từ hoặc token thay đổi thay vì chỉ dòng. Nó hữu ích với tài liệu, JSON, cấu hình hoặc dòng dài.

Có thể chọn chế độ:

~~~bash
git show --word-diff=plain HEAD -- docs/api/checkout.md
~~~

Kết quả dễ nhìn hơn với nội dung có nhiều từ được thay đổi trên cùng một dòng.

### 4.5. Kiểm tra whitespace trong patch

~~~bash
git show --check HEAD
~~~

Lệnh kiểm tra các vấn đề whitespace phổ biến trong diff, như trailing whitespace hoặc lỗi khoảng trắng ở dòng mới. Nó không thay thế formatter, linter hay test.

## 5. Xem thống kê và danh sách tệp thay đổi

### 5.1. Thống kê bằng --stat

~~~bash
git show --stat HEAD
~~~

Ví dụ:

~~~text
 src/order/CheckoutService.java       | 12 ++++++++----
 src/order/AddressValidator.java      | 18 ++++++++++++++++++
 test/order/CheckoutServiceTest.java  | 24 ++++++++++++++++++++++++
 docs/api/checkout.md                 |  6 +++++-
 4 files changed, 54 insertions(+), 6 deletions(-)
~~~

Thống kê giúp trả lời:

- Có bao nhiêu tệp thay đổi?
- Tệp nào có nhiều dòng thêm/xóa?
- Commit có phạm vi lớn bất thường không?

Dùng dạng ngắn kết hợp subject:

~~~bash
git show --stat --oneline HEAD
~~~

### 5.2. Chỉ liệt kê tên file bằng --name-only

~~~bash
git show --name-only --format= HEAD
~~~

Lệnh hiển thị các đường dẫn bị ảnh hưởng mà không in patch. Hữu ích khi cần xác nhận phạm vi commit.

### 5.3. Liệt kê tên và loại thay đổi bằng --name-status

~~~bash
git show --name-status --format= HEAD
~~~

Các mã thường gặp:

| Mã | Ý nghĩa |
| --- | --- |
| A | Thêm tệp |
| M | Sửa tệp |
| D | Xóa tệp |
| R | Đổi tên |
| C | Sao chép |

Với rename hoặc copy, Git có thể hiển thị thêm phần trăm độ tương đồng, ví dụ `R095`.

### 5.4. Dùng --numstat cho số dòng

~~~bash
git show --numstat HEAD
~~~

Đầu ra thường có ba cột phân tách bằng tab:

~~~text
12    6    src/order/CheckoutService.java
18    0    src/order/AddressValidator.java
24    0    test/order/CheckoutServiceTest.java
~~~

Hai cột đầu là số dòng thêm và xóa. Với file nhị phân, Git thường hiển thị dấu gạch ngang thay vì số dòng.

### 5.5. Xem raw diff và mode/OID

~~~bash
git show --raw HEAD
~~~

Raw diff có thể cho biết:

- Mode cũ và mode mới.
- Object ID cũ và mới.
- Trạng thái thay đổi.
- Đường dẫn liên quan.

Đây là cách hữu ích khi thay đổi liên quan đến executable bit, symbolic link, submodule hoặc cần đối chiếu OID.

## 6. Chọn đúng commit để xem

### 6.1. Xem commit hiện tại

~~~bash
git show HEAD
~~~

HEAD là lựa chọn phù hợp nhất sau khi vừa commit thành công.

### 6.2. Xem commit trước đó

~~~bash
git show HEAD^
~~~

`HEAD^` là parent thứ nhất của HEAD. Với lịch sử tuyến tính thông thường, đây là commit ngay trước HEAD.

~~~bash
git show HEAD~2
~~~

`HEAD~2` đi theo parent thứ nhất hai bước từ HEAD.

Lưu ý: `git show HEAD^` hiển thị chính commit parent đó cùng diff của nó so với parent trước nó; nó không phải lệnh hiển thị diff giữa HEAD và HEAD^.

### 6.3. Xem commit bằng hash

~~~bash
git show a81c9f2
~~~

Có thể dùng hash đầy đủ hoặc hash rút gọn đủ duy nhất trong repository. Nếu cần bằng chứng hoặc lưu vào hệ thống bên ngoài, ưu tiên hash đầy đủ.

### 6.4. Xem commit bằng branch hoặc tag

~~~bash
git show main
git show v1.2.0
~~~

Với branch, Git phân giải branch đến commit mà ref đang trỏ tới. Với annotated tag, `git show` có thể hiển thị thông tin tag và commit đích.

Để xác nhận tag trỏ đến commit nào:

~~~bash
git rev-parse 'v1.2.0^{commit}'
~~~

### 6.5. Xem nhiều commit

~~~bash
git show HEAD HEAD^
~~~

Lệnh hiển thị từng đối tượng được chỉ định. Nếu mục tiêu là duyệt một dải lịch sử, `git log` thường phù hợp hơn:

~~~bash
git log --oneline -5
~~~

Sau đó dùng `git show <commit>` để xem chi tiết từng commit.

## 7. Xem thay đổi của một tệp cụ thể

### 7.1. Cú pháp xem diff của file trong commit

~~~bash
git show HEAD -- src/order/CheckoutService.java
~~~

Dấu `--` phân cách revision với pathspec. Lệnh hiển thị phần thay đổi của tệp trong commit HEAD so với parent của commit.

Đây là cú pháp phù hợp khi bạn muốn trả lời: "Commit vừa tạo đã sửa tệp này như thế nào?"

### 7.2. Cú pháp xem toàn bộ nội dung file tại commit

~~~bash
git show HEAD:src/order/CheckoutService.java
~~~

Cú pháp `<tree-ish>:<path>` hiển thị nội dung blob được lưu tại đường dẫn trong snapshot của commit.

Hai lệnh sau có mục tiêu khác nhau:

| Lệnh | Kết quả |
| --- | --- |
| `git show HEAD -- path/to/file` | Patch của file trong commit |
| `git show HEAD:path/to/file` | Toàn bộ nội dung file tại commit |

Không thêm dấu `--` giữa HEAD và dấu hai chấm trong cú pháp đọc blob.

### 7.3. So sánh file giữa commit mới và parent

Xem nội dung file trước commit:

~~~bash
git show HEAD^:src/order/CheckoutService.java
~~~

Xem nội dung sau commit:

~~~bash
git show HEAD:src/order/CheckoutService.java
~~~

Có thể so sánh hai nội dung bằng diff của Git:

~~~bash
git diff HEAD^ HEAD -- src/order/CheckoutService.java
~~~

Cách này giúp kiểm tra chính xác một file đã thay đổi ra sao giữa hai snapshot.

### 7.4. Xem file trong commit có đường dẫn chứa khoảng trắng

Đặt pathspec trong dấu nháy:

~~~bash
git show HEAD -- "docs/release notes.md"
~~~

Để đọc nội dung blob:

~~~bash
git show "HEAD:docs/release notes.md"
~~~

Dấu nháy giúp shell chuyển nguyên đường dẫn thành một đối số. Với tên file có ký tự đặc biệt, hãy bảo đảm cú pháp pathspec được truyền đúng.

### 7.5. File đã bị xóa trong commit

Nếu commit xóa một file, `git show HEAD:path/to/file` không thể đọc blob tại đường dẫn đó từ snapshot mới vì đường dẫn không còn tồn tại.

Có thể đọc phiên bản trước khi xóa:

~~~bash
git show HEAD^:path/to/file
~~~

Và xem diff xóa:

~~~bash
git show HEAD -- path/to/file
~~~

### 7.6. File mới được thêm trong commit

Với file mới, không có phiên bản trong parent:

~~~bash
git show HEAD:path/to/new-file
~~~

hiển thị nội dung file trong commit mới. Còn:

~~~bash
git show HEAD -- path/to/new-file
~~~

hiển thị patch thêm file, thường gồm các dòng được thêm.

## 8. Hiểu commit ID, tree và parent

### 8.1. Commit ID định danh nội dung commit

Commit hash được tính từ nội dung commit object, gồm tree, parent, author, committer và message. Vì vậy, sửa message hoặc metadata có thể làm commit hash thay đổi ngay cả khi nội dung file không đổi.

Lấy hash:

~~~bash
git show -s --format=%H HEAD
~~~

### 8.2. Tree ID định danh snapshot file

Một commit tham chiếu đến tree object chứa cấu trúc thư mục và các file tại snapshot đó.

Xem tree ID:

~~~bash
git show -s --format=%T HEAD
~~~

Hai commit có thể có cùng tree nhưng khác author, committer, parent hoặc message nên vẫn có commit hash khác nhau.

### 8.3. Parent commit

Xem parent:

~~~bash
git show -s --format=%P HEAD
~~~

Commit thông thường có một parent; commit gốc không có parent; merge commit thường có từ hai parent trở lên.

Thông tin parent giúp xác định commit đang được so sánh với snapshot nào.

### 8.4. Xem commit object thô

~~~bash
git show --format=raw --no-patch HEAD
~~~

Đầu ra giúp kiểm tra tree và parent mà commit tham chiếu. Khi cần kiểm tra nội dung commit chính xác, có thể kết hợp:

~~~bash
git cat-file -p HEAD
~~~

Không chỉnh sửa object trong object database bằng tay. Nếu metadata sai, dùng amend hoặc quy trình rewrite history phù hợp.

## 9. Kiểm tra commit merge

### 9.1. Merge commit có nhiều parent

Một merge commit thường có ít nhất hai parent. Khi chạy:

~~~bash
git show HEAD
~~~

Git có thể trình bày combined diff cho merge commit. Dạng combined diff không giống patch của commit tuyến tính và có quy tắc hiển thị riêng.

Xem các parent:

~~~bash
git show -s --format="%H%n%P" HEAD
~~~

### 9.2. Xem diff riêng với từng parent bằng -m

~~~bash
git show -m HEAD
~~~

Tùy chọn `-m` tạo diff riêng cho từng parent của merge commit. Điều này hữu ích khi muốn xem merge commit thay đổi gì so với từng nhánh cha.

### 9.3. Xem kết quả merge so với first parent

Có thể so sánh tree merge với parent thứ nhất:

~~~bash
git diff HEAD^1 HEAD
~~~

So với parent thứ hai:

~~~bash
git diff HEAD^2 HEAD
~~~

Cách này thường dễ đọc hơn khi muốn biết nội dung cuối cùng khác gì so với nhánh đang được merge vào hoặc nhánh được tích hợp.

### 9.4. Combined diff bằng --cc

~~~bash
git show --cc HEAD
~~~

Combined diff tập trung vào phần khác biệt liên quan giữa kết quả merge và các parent. Không phải mọi thay đổi của từng parent đều xuất hiện giống một diff tuyến tính thông thường.

Nếu cần audit từng phía, dùng `-m` hoặc `git diff HEAD^1 HEAD` và `git diff HEAD^2 HEAD`.

## 10. Xem rename, mode và file nhị phân

### 10.1. Nhận diện rename

~~~bash
git show --summary --find-renames HEAD
~~~

Git suy luận rename bằng cách so sánh nội dung và đường dẫn giữa các snapshot. Rename không phải một loại object riêng trong commit.

Có thể điều chỉnh ngưỡng tương đồng:

~~~bash
git show --find-renames=80% HEAD
~~~

Nếu nội dung thay đổi nhiều, Git có thể hiển thị delete và add thay vì rename.

### 10.2. Nhận diện thay đổi mode

~~~bash
git show --raw HEAD
~~~

Ví dụ, thay đổi executable bit có thể làm mode chuyển từ `100644` sang `100755` dù nội dung file không đổi.

Đây là lý do không nên chỉ kiểm tra patch văn bản; cần xem raw diff hoặc summary khi commit có thay đổi quyền file.

### 10.3. File nhị phân

Với file nhị phân, Git thường không hiển thị patch dạng văn bản dễ đọc. Dùng:

~~~bash
git show --stat HEAD
git show --numstat HEAD
git show --raw HEAD
~~~

để kiểm tra đường dẫn, kích thước thay đổi tương đối và OID.

Tùy chọn `--binary` tạo biểu diễn patch nhị phân có thể dùng bởi `git apply`:

~~~bash
git show --binary HEAD
~~~

Nó không biến dữ liệu nhị phân thành nội dung dễ đọc. Nếu cần xác minh file ảnh, archive hoặc model, hãy trích xuất và dùng công cụ phù hợp với định dạng.

### 10.4. Submodule

Trong commit của repository cha, submodule được biểu diễn bằng gitlink trỏ đến commit của repository con. `git show` có thể cho thấy OID submodule thay đổi, nhưng không tự hiển thị toàn bộ nội dung repository con.

Có thể xem thông tin submodule trong diff:

~~~bash
git show --submodule=log HEAD
~~~

Để kiểm tra nội dung, vào repository submodule và xem commit được ghi nhận. Đảm bảo submodule đang ở đúng commit mà tree của repository cha tham chiếu.

### 10.5. Git LFS

Trong commit, Git thường lưu LFS pointer thay vì nội dung nhị phân lớn. Vì vậy:

~~~bash
git show HEAD:assets/model.bin
~~~

có thể hiển thị nội dung pointer dạng văn bản gồm version, OID và size, chứ không phải file model thật.

Để lấy nội dung thật, cần Git LFS và object tương ứng đã được tải. `git show` chỉ hiển thị blob được Git lưu trong commit; nó không tự tải LFS object từ server.

## 11. Lọc và định dạng output

### 11.1. Chỉ hiển thị thống kê, không có patch

~~~bash
git show --stat --no-patch HEAD
~~~

Phù hợp khi cần xác nhận phạm vi nhanh mà không đọc toàn bộ diff.

### 11.2. Chỉ hiển thị tên tệp và trạng thái

~~~bash
git show --name-status --format= HEAD
~~~

Phù hợp với checklist review hoặc script cần xác nhận file nào được thêm, sửa, xóa hoặc rename.

### 11.3. Chỉ hiển thị patch của một thư mục

~~~bash
git show HEAD -- src/order/
~~~

Dùng pathspec để giới hạn nội dung theo khu vực. Điều này đặc biệt hữu ích trong monorepo.

### 11.4. Giới hạn số dòng context

~~~bash
git show -U3 HEAD -- src/order/CheckoutService.java
~~~

`-U3` hiển thị ba dòng context quanh mỗi hunk. Có thể tăng hoặc giảm tùy nhu cầu review.

### 11.5. Tắt external diff và textconv khi cần đầu ra trực tiếp

~~~bash
git show --no-ext-diff --no-textconv HEAD
~~~

Một số repository cấu hình external diff hoặc textconv để trình bày nội dung đặc biệt. Tùy chọn trên yêu cầu Git dùng diff nội bộ và bỏ qua textconv, hữu ích khi muốn đầu ra ít phụ thuộc công cụ bên ngoài.

### 11.6. Màu sắc và pager

Nếu output có màu hoặc được mở trong pager, đó là hành vi hiển thị của môi trường, không phải nội dung commit.

Có thể tắt pager cho một lệnh:

~~~bash
git --no-pager show HEAD
~~~

Hoặc tắt màu:

~~~bash
git -c color.ui=false show HEAD
~~~

Khi lưu output vào log hoặc automation, chọn format ổn định và tránh phân tích văn bản dành cho người đọc bằng cách tách dòng tùy tiện.

## 12. Quy trình kiểm tra commit vừa tạo

Giả sử bạn vừa tạo commit `Validate billing address before checkout`.

### Bước 1 — Xác nhận commit và branch

~~~bash
git status --short --branch
git branch --show-current
git show -s --format="%H%n%s" HEAD
~~~

Đảm bảo HEAD nằm trên branch mong muốn và subject đúng.

### Bước 2 — Kiểm tra author, committer và thời gian

~~~bash
git show --format=fuller --date=iso-strict --no-patch HEAD
~~~

Xác nhận tên, email, author date và committer date.

### Bước 3 — Xem danh sách tệp và thống kê

~~~bash
git show --stat --oneline HEAD
git show --name-status --format= HEAD
~~~

Kiểm tra không có file tạm, file bí mật hoặc thay đổi ngoài phạm vi.

### Bước 4 — Đọc patch

~~~bash
git show --format=fuller HEAD
~~~

Đọc logic, test và tài liệu trong commit. Nếu cần tập trung vào một tệp:

~~~bash
git show HEAD -- src/order/CheckoutService.java
~~~

### Bước 5 — Kiểm tra snapshot cuối của một file

~~~bash
git show HEAD:src/order/CheckoutService.java
~~~

Đối chiếu với nội dung mong muốn được commit. Nếu muốn xem phiên bản trước đó:

~~~bash
git show HEAD^:src/order/CheckoutService.java
~~~

### Bước 6 — Kiểm tra whitespace và trạng thái còn lại

~~~bash
git show --check HEAD
git status --short --branch
~~~

Nếu working tree còn thay đổi, xác định đó là phần cố ý để dành hay nội dung bị bỏ sót.

### Bước 7 — Lưu bằng chứng commit khi cần

~~~bash
git show -s --format="%H %aI %cI %s" HEAD
~~~

Ghi lại commit ID đầy đủ cùng thông tin release hoặc ticket nếu quy trình yêu cầu. Không cần lưu toàn bộ patch vào một tài liệu khác nếu commit đã là nguồn lịch sử chính thức.

## 13. Những sai lầm thường gặp

- **Dùng git show HEAD:path khi muốn xem diff:** cú pháp này in toàn bộ nội dung file trong commit. Dùng `git show HEAD -- path` để xem patch.
- **Nghĩ HEAD^ là diff của commit hiện tại:** HEAD^ là parent; `git show HEAD^` hiển thị commit parent. Dùng `git diff HEAD^ HEAD` để so sánh hai snapshot.
- **Chỉ kiểm tra subject:** message đúng không bảo đảm patch đúng. Hãy đọc diff và danh sách tệp.
- **Chỉ xem --stat:** thống kê không cho biết logic thay đổi. Đọc patch khi review.
- **Nhầm author với committer:** kiểm tra cả hai danh tính và timestamp.
- **Mặc định hash luôn dài 40 ký tự:** độ dài phụ thuộc object format. Dùng `git rev-parse --show-object-format`.
- **Bỏ qua file nhị phân:** patch có thể không hiển thị nội dung. Kiểm tra OID, kích thước và mở bằng công cụ phù hợp.
- **Cho rằng git show tự tải LFS object:** Git chỉ hiển thị pointer blob đã commit. Tải LFS object bằng Git LFS.
- **Cho rằng submodule chứa đầy đủ source trong commit cha:** tree cha chỉ ghi gitlink đến commit repository con.
- **Đọc merge commit như một commit tuyến tính:** dùng `-m`, `--cc` hoặc so sánh riêng từng parent.
- **Phân tích output dành cho người dùng bằng script:** dùng format/porcelain phù hợp hoặc cấu trúc dữ liệu ổn định; tên file có thể chứa khoảng trắng và ký tự đặc biệt.

## 14. Bảng tra cứu nhanh

| Nhu cầu | Lệnh |
| --- | --- |
| Xem commit mới nhất | `git show HEAD` |
| Lấy hash đầy đủ | `git show -s --format=%H HEAD` |
| Kiểm tra object format | `git rev-parse --show-object-format` |
| Xem author/committer | `git show --format=fuller --no-patch HEAD` |
| Xem timestamp ISO | `git show --format=fuller --date=iso-strict --no-patch HEAD` |
| Xem toàn bộ message | `git show -s --format=%B HEAD` |
| Xem tree và parent | `git show --format=raw --no-patch HEAD` |
| Xác minh chữ ký commit nếu có | `git verify-commit HEAD` |
| Xem patch đầy đủ | `git show --format=fuller HEAD` |
| Xem thống kê | `git show --stat HEAD` |
| Liệt kê file và trạng thái | `git show --name-status --format= HEAD` |
| Xem số dòng thêm/xóa | `git show --numstat HEAD` |
| Xem raw diff | `git show --raw HEAD` |
| Xem diff một file | `git show HEAD -- path/to/file` |
| Xem nội dung file tại commit | `git show HEAD:path/to/file` |
| Xem nội dung file trước commit | `git show HEAD^:path/to/file` |
| So sánh commit với parent | `git diff HEAD^ HEAD` |
| Xem merge diff theo từng parent | `git show -m HEAD` |
| Xem combined merge diff | `git show --cc HEAD` |
| Kiểm tra whitespace | `git show --check HEAD` |
| Xem file LFS pointer đã commit | `git show HEAD:assets/model.bin` |
| Kiểm tra trạng thái working tree | `git status --short --branch` |

## 15. Tổng kết

`git show` giúp xác minh commit vừa tạo từ mã định danh đến metadata và nội dung snapshot. Bắt đầu với `git show --format=fuller --no-patch HEAD` để kiểm tra author, committer, thời gian và message; dùng `git show HEAD` hoặc `git show --format=fuller HEAD` để đọc patch; dùng `--stat`, `--name-status`, `--numstat` hoặc `--raw` để xem phạm vi thay đổi.

Hãy nhớ phân biệt `git show HEAD -- path` (diff của file trong commit) với `git show HEAD:path` (nội dung file trong snapshot). Khi cần so sánh với phiên bản trước, dùng `HEAD^` hoặc `git diff HEAD^ HEAD`. Với merge commit, xem riêng từng parent; với binary, submodule và Git LFS, kiểm tra thêm object hoặc repository liên quan.

Một quy trình xác minh tốt không dừng ở việc commit đã tạo thành công. Hãy kiểm tra đúng branch, hash, danh tính, message, danh sách tệp, patch và trạng thái còn lại. Điều đó giúp phát hiện sớm commit sai phạm vi hoặc metadata không chính xác trước khi chia sẻ lên remote.

