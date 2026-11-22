# Đọc thay đổi của một commit bằng git show

Khi xem lịch sử Git, biết commit nào đã xuất hiện chỉ là bước đầu. Bạn còn cần trả lời commit đó thay đổi những tệp nào, nội dung trước và sau ra sao, ai tạo commit, commit có thuộc một nhánh hoặc tag cụ thể không và nội dung đang xem có phải đúng snapshot đã được lưu hay chỉ là thay đổi chưa commit trên máy.

Lệnh `git show` là công cụ trực tiếp để đọc một commit. Với commit, Git hiển thị metadata, thông điệp và diff mà commit giới thiệu. Bạn cũng có thể yêu cầu chỉ xem thống kê, tên tệp, trạng thái chữ ký hoặc nội dung của một tệp tại snapshot cụ thể.

Bài học thuộc chương **Tra cứu lịch sử** của module `SOURCE_CONTROL_GIT`. Module hướng dẫn working tree, staging area, commit, lịch sử, branch, merge, rebase, remote và tag; đọc commit chính xác giúp truy vết thay đổi, review lỗi và hiểu lịch sử cộng tác.

## 1. git show cho biết điều gì?

Cú pháp cơ bản:

~~~bash
git show <commit>
~~~

Ví dụ xem commit hiện tại:

~~~bash
git show HEAD
~~~

Lệnh này thường hiển thị:

1. Tên commit và thông tin nhận diện commit.
2. Author và thời điểm tạo thay đổi ban đầu.
3. Committer và thời điểm tạo commit object hiện tại.
4. Thông điệp commit.
5. Diff mô tả thay đổi được commit đó giới thiệu.

Với commit thông thường, phần diff thể hiện khác biệt giữa snapshot của commit và parent của nó. Với commit đầu tiên không có parent, có thể dùng tùy chọn root để hiển thị các tệp được thêm vào so với cây rỗng.

Một commit lưu snapshot của repository tại một thời điểm. Diff mà git show trình bày giúp bạn hiểu snapshot đó khác parent như thế nào; nó không phải bản so sánh trực tiếp với working tree hiện tại.

## 2. Chọn đúng commit cần xem

git show nhận commit hash, tên branch, tag và nhiều biểu thức revision mà Git có thể phân giải thành object.

### Xem commit hiện tại và các commit trước

~~~bash
git show HEAD
git show HEAD~1
git show HEAD~2
~~~

- HEAD là commit mà branch hiện tại đang trỏ tới.
- HEAD~1 là parent thứ nhất của HEAD.
- HEAD~2 là parent thứ nhất của parent thứ nhất.

Có thể dùng hash đầy đủ hoặc hash rút gọn:

~~~bash
git show a1b2c3d
~~~

Hash rút gọn chỉ hợp lệ nếu Git phân giải được duy nhất một object trong repository.

### Phân biệt ^ và ~

Ký hiệu ~n đi theo parent thứ nhất lặp lại n lần. Ký hiệu ^n chọn parent thứ n của commit hiện tại.

~~~bash
git show HEAD^
git show HEAD^1
git show HEAD^2
git show HEAD~2
~~~

Với commit thường chỉ có một parent, HEAD^ và HEAD^1 giống nhau. Với merge commit có hai hoặc nhiều parent, HEAD^1 là parent thứ nhất, HEAD^2 là parent thứ hai. Vì vậy, HEAD~1 không có nghĩa là “commit đứng trước trong mọi nhánh”; nó luôn đi theo parent thứ nhất.

### Xem commit theo branch hoặc tag

~~~bash
git show main
git show release/v2.1
git show v2.1.0
~~~

Tên branch trỏ đến commit tip hiện tại của branch đó. Tag có thể là lightweight tag trỏ thẳng đến commit hoặc annotated tag có tag object riêng. Với annotated tag, git show có thể hiển thị thông tin tag và sau đó nội dung object được tag tham chiếu.

Muốn xác nhận một tên tag phân giải đến commit:

~~~bash
git rev-parse --verify "v2.1.0^{commit}"
~~~

Biểu thức ^{commit} yêu cầu Git phân giải tag/object về một commit. Cách này hữu ích khi script cần bảo đảm đối tượng đích đúng kiểu commit.

## 3. Đọc metadata mà không cần xem patch

Khi chỉ cần biết ai tạo commit, thời gian và thông điệp, dùng --no-patch:

~~~bash
git show --no-patch --format=fuller HEAD
~~~

--format=fuller hiển thị Author, AuthorDate, Committer và CommitDate ở dạng đầy đủ.

Một số định dạng thường dùng:

| Tùy chọn | Nội dung |
| --- | --- |
| --format=oneline | Hash và subject trên một dòng |
| --format=short | Header commit và subject |
| --format=medium | Metadata và thông điệp theo dạng thường dùng |
| --format=fuller | Thêm thông tin author/committer date đầy đủ |
| --format=raw | Dạng gần với nội dung commit object, gồm tree và parent |
| --no-patch | Không in phần diff |

Ví dụ xem metadata và parent:

~~~bash
git show --no-patch --format=raw HEAD
~~~

Dạng raw hữu ích khi điều tra merge, parent hoặc xác minh cấu trúc commit. Nó vẫn là cách hiển thị object, không phải kết quả so sánh nội dung tệp.

### Phân biệt Author và Committer

Author là người được ghi nhận đã viết thay đổi ban đầu. Committer là người tạo commit object hiện tại. Hai người có thể khác nhau khi cherry-pick, rebase, apply patch hoặc tạo lại commit thay mặt người khác.

Ví dụ:

~~~text
Author:     Nguyen An <an@example.com>
AuthorDate: Mon Nov 16 09:10:00 2026 +0700
Commit:     Tran Binh <binh@example.com>
CommitDate: Mon Nov 16 10:25:00 2026 +0700
~~~

Không suy ra quyền truy cập remote từ tên/email trong commit. Đây là metadata lịch sử; xác thực remote là cơ chế riêng.

## 4. Xem patch của commit

Để xem patch với metadata đầy đủ:

~~~bash
git show --format=fuller HEAD
~~~

Mỗi đoạn diff thường có dạng:

~~~diff
diff --git a/src/payment.js b/src/payment.js
index 12ab34c..56de78f 100644
--- a/src/payment.js
+++ b/src/payment.js
@@ -10,6 +10,9 @@ function calculateTotal(items) {
   return items.reduce((sum, item) => {
     return sum + item.price;
   }, 0);
+}
+
+function calculateTax(total, rate) {
+  return total * rate;
 }
~~~

Cách đọc:

- diff --git a/... b/... cho biết đường dẫn trước và sau trong diff.
- index hiển thị object ID cũ và mới cùng file mode.
- --- là phía cũ; +++ là phía mới.
- Dòng bắt đầu bằng dấu trừ bị loại khỏi snapshot mới.
- Dòng bắt đầu bằng dấu cộng được thêm vào snapshot mới.
- Dòng không có dấu cộng hoặc trừ là context giúp định vị thay đổi.
- Header @@ -x,y +a,b @@ cho biết vùng dòng trong phiên bản cũ và mới.

Dòng context không phải thay đổi được commit. Chỉ các dòng thêm/xóa mới biểu diễn nội dung khác nhau trong hunk đó.

### Đọc patch dễ hơn với context hoặc word diff

Giảm số dòng context:

~~~bash
git show -U2 HEAD
~~~

Tăng số dòng context:

~~~bash
git show -U10 HEAD
~~~

Với thay đổi văn bản ngắn, có thể xem khác biệt theo từ:

~~~bash
git show --word-diff HEAD
~~~

--word-diff giúp nhận ra một câu hoặc biểu thức bị sửa ở giữa dòng. Nó không thay thế review diff thông thường, đặc biệt với mã nguồn có cấu trúc hoặc tệp nhị phân.

## 5. Chỉ xem một tệp hoặc một thư mục trong commit

Để xem patch của một đường dẫn do commit đó giới thiệu, đặt dấu phân cách -- trước pathspec:

~~~bash
git show HEAD -- src/payment.js
~~~

Dấu -- phân tách revision/options với đường dẫn. Nó tránh Git nhầm một tên tệp với tên branch hoặc revision.

Có thể xem nhiều đường dẫn:

~~~bash
git show HEAD -- src/payment.js tests/payment.test.js
~~~

Hoặc một thư mục:

~~~bash
git show HEAD -- src/
~~~

Kết quả là diff của các đường dẫn đó trong commit đang chọn, so với parent tương ứng.

### Xem tên tệp và trạng thái thay đổi

~~~bash
git show --name-status --format=medium HEAD
~~~

Một số trạng thái thường gặp:

| Ký hiệu | Ý nghĩa |
| --- | --- |
| A | Added — tệp được thêm |
| M | Modified — tệp được sửa |
| D | Deleted — tệp bị xóa |
| R | Renamed — Git nhận diện đổi tên |
| C | Copied — Git nhận diện sao chép khi bật/cấu hình phát hiện copy phù hợp |

Git lưu snapshot và object, không lưu thao tác rename như một loại object độc lập. Trạng thái R hoặc C được suy ra bằng thuật toán so sánh nội dung khi hiển thị diff.

Nếu chỉ cần danh sách đường dẫn:

~~~bash
git show --name-only --format= HEAD
~~~

Để chỉ xem thống kê thay đổi:

~~~bash
git show --stat --oneline HEAD
~~~

Các tùy chọn này phù hợp khi bạn muốn xác định phạm vi commit trước khi đọc từng đoạn patch.

## 6. Xem snapshot của một tệp tại commit

Một cú pháp quan trọng khác:

~~~bash
git show <commit>:<path>
~~~

Cú pháp này đọc nội dung object tại đường dẫn trong snapshot của commit, không hiển thị patch.

Ví dụ xem nội dung file ở HEAD:

~~~bash
git show HEAD:src/payment.js
~~~

Xem cùng file ở commit cũ:

~~~bash
git show HEAD~3:src/payment.js
~~~

So sánh hai snapshot bằng git diff với hai revision/path phù hợp.

Phân biệt hai dạng:

| Lệnh | Kết quả |
| --- | --- |
| git show HEAD -- src/payment.js | Patch của commit HEAD đối với đường dẫn đó |
| git show HEAD:src/payment.js | Nội dung đầy đủ của tệp trong snapshot HEAD |

Nếu đường dẫn không tồn tại trong snapshot đã chọn, Git báo lỗi vì không tìm thấy object tại path đó.

### Xem nội dung tệp nhị phân

Không nên in trực tiếp blob nhị phân ra terminal. Có thể redirect nội dung snapshot ra một file tạm để mở bằng ứng dụng phù hợp:

~~~bash
git show HEAD:assets/diagram.png > /tmp/diagram-at-head.png
~~~

Trên PowerShell:

~~~powershell
git show HEAD:assets/diagram.png > "$env:TEMP/diagram-at-head.png"
~~~

Lệnh này chỉ xuất nội dung trong commit ra file đích. Hãy chọn đường dẫn tạm riêng để tránh ghi đè tệp đang làm việc.

## 7. So sánh commit với parent và so sánh hai snapshot

git show <commit> thường cho biết thay đổi commit đó giới thiệu so với parent. Nếu muốn so sánh hai snapshot bất kỳ, dùng git diff:

~~~bash
git diff HEAD~2 HEAD
~~~

Sự khác biệt:

| Nhu cầu | Lệnh |
| --- | --- |
| Xem commit đã thêm/sửa/xóa gì so với parent | git show <commit> |
| So sánh snapshot của hai commit | git diff <commit-A> <commit-B> |
| Xem thay đổi từ một commit đến HEAD | git diff <commit> HEAD |
| Xem nội dung tệp ở một snapshot | git show <commit>:path/to/file |
| Xem thay đổi chưa stage | git diff |
| Xem thay đổi đã stage so với HEAD | git diff --cached |

Ví dụ, để xem toàn bộ thay đổi từ commit A đến commit B:

~~~bash
git diff A B
~~~

Nếu dùng git show B, bạn chỉ đang xem thay đổi được commit B giới thiệu so với parent của B. Hai kết quả có thể khác nhau đáng kể nếu giữa A và B có nhiều commit.

## 8. Kiểm tra commit có những thay đổi nào bằng các chế độ output

git show có nhiều tùy chọn để thu hẹp output:

| Tùy chọn | Khi nào dùng |
| --- | --- |
| --stat | Xem số dòng thêm/xóa theo từng tệp |
| --shortstat | Chỉ xem tổng số tệp và dòng thêm/xóa |
| --numstat | Thống kê dạng số, thuận tiện cho script |
| --name-only | Chỉ liệt kê đường dẫn |
| --name-status | Liệt kê đường dẫn kèm A/M/D/R... |
| --summary | Hiển thị tạo/xóa mode, rename hoặc thông tin tóm tắt |
| --raw | Xem thay đổi ở mức mode và object ID |
| --check | Kiểm tra whitespace error trong patch |
| --no-patch | Chỉ hiển thị phần commit, không in diff |

Ví dụ:

~~~bash
git show --shortstat HEAD
git show --numstat HEAD
git show --summary HEAD
git show --check HEAD
~~~

--check hữu ích khi review whitespace như trailing whitespace hoặc dấu cách trước tab. Nó không phải bộ kiểm tra chất lượng mã nguồn hay test ứng dụng.

### Kết hợp nhiều tùy chọn

~~~bash
git show --format=fuller --stat --summary HEAD
git show --format= --name-status HEAD
git show --format= --numstat HEAD
~~~

Dùng --format= để bỏ phần thông điệp/metadata khi bạn chỉ muốn danh sách hoặc thống kê. Trong script, nên cố định format để output không thay đổi theo cấu hình format.pretty của máy.

## 9. Đọc merge commit

Merge commit có từ hai parent trở lên. Khi xem merge commit, cần hiểu diff đang được tạo theo cách nào vì không có một parent duy nhất đại diện cho toàn bộ lịch sử trước merge.

Xem metadata và danh sách parent:

~~~bash
git show --no-patch --format=raw <merge-commit>
~~~

Xem patch so với từng parent:

~~~bash
git show -m <merge-commit>
~~~

-m yêu cầu hiển thị diff của merge commit đối với từng parent. Đây là cách hữu ích để xem merge đã thay đổi kết quả so với mỗi nhánh đầu vào như thế nào.

Xem combined diff:

~~~bash
git show --cc <merge-commit>
~~~

Combined diff tập trung vào những phần khác nhau giữa các parent và kết quả merge. Nó có thể không hiển thị mọi thay đổi nếu một thay đổi chỉ khác so với một parent; do đó nếu cần phân tích đầy đủ, xem thêm -m hoặc diff với từng parent cụ thể.

Ví dụ so sánh merge result với parent thứ nhất:

~~~bash
git diff <merge-commit>^1 <merge-commit>
~~~

So sánh với parent thứ hai:

~~~bash
git diff <merge-commit>^2 <merge-commit>
~~~

Không nên chỉ dựa vào một dạng diff để kết luận merge đã đưa những gì vào branch. Xác định parent và góc nhìn so sánh trước khi đọc.

## 10. Đọc root commit và commit đặc biệt

Root commit là commit đầu tiên trong lịch sử, không có parent. Để xem thông tin:

~~~bash
git show --no-patch --format=fuller <root-commit>
~~~

Để thể hiện các tệp được thêm vào so với cây rỗng:

~~~bash
git show --root --stat <root-commit>
~~~

Một commit có thể là empty commit (không thay đổi tree so với parent) nhưng vẫn có metadata và thông điệp. Khi git show không có patch, không nhất thiết commit bị lỗi; có thể commit không thay đổi nội dung tệp.

## 11. Kiểm tra chữ ký commit khi cần

Nếu dự án yêu cầu commit được ký, có thể hiển thị chữ ký cùng thông tin commit:

~~~bash
git show --show-signature --no-patch HEAD
~~~

Xác minh commit cụ thể:

~~~bash
git verify-commit HEAD
~~~

Chữ ký giúp xác minh commit object được ký bằng khóa tương ứng và nội dung đã ký không bị thay đổi. Kết quả tin cậy còn phụ thuộc khóa công khai, cấu hình trust hoặc allowed signers và công cụ ký đã cài.

Author name/email hiển thị trong git show chỉ là metadata. Nó không chứng minh người đó đã xác thực với remote hoặc chữ ký commit hợp lệ.

## 12. Lưu ý với Git LFS và submodule

git show <commit>:path đọc nội dung blob mà Git lưu tại snapshot. Với tệp được quản lý bằng Git LFS, blob trong Git thường là pointer text, không phải nội dung tệp lớn thực tế.

Ví dụ:

~~~bash
git show HEAD:assets/video.mp4
~~~

Bạn thường thấy pointer gồm version, OID và size. Muốn tải nội dung LFS thực tế, cần Git LFS và object tương ứng trên LFS server.

Với submodule, superproject lưu gitlink chứa commit ID mà submodule được yêu cầu checkout. Khi xem diff, bạn có thể thấy commit ID của submodule thay đổi; git show trong superproject không tự hiển thị toàn bộ patch của repository submodule. Hãy chuyển vào thư mục submodule và dùng git show ở repository đó để đọc commit tương ứng.

## 13. Quy trình review một commit

Một quy trình thực tế khi nhận yêu cầu “kiểm tra commit này đã thay đổi gì”:

**Bước 1: Xác định commit**

~~~bash
git rev-parse --verify "<revision>^{commit}"
~~~

Dùng hash hoặc ref cụ thể để tránh xem nhầm branch tip đã di chuyển.

**Bước 2: Xem metadata và thông điệp**

~~~bash
git show --no-patch --format=fuller <commit>
~~~

Kiểm tra author, committer, thời gian, parent và thông điệp.

**Bước 3: Xem phạm vi tệp**

~~~bash
git show --stat --summary <commit>
git show --name-status --format= <commit>
~~~

Xác định tệp nào được thêm, sửa, xóa hoặc đổi tên.

**Bước 4: Đọc patch**

~~~bash
git show --format=fuller <commit>
~~~

Đọc từng hunk, chú ý dòng thêm/xóa và các file ảnh hưởng.

**Bước 5: Đối chiếu snapshot nếu cần**

~~~bash
git show <commit>:path/to/file
git diff <commit>^ <commit> -- path/to/file
~~~

Lệnh đầu cho biết nội dung file trong snapshot; lệnh thứ hai cho biết patch của đường dẫn đó so với parent thứ nhất. Với merge commit, chỉ rõ parent cần so sánh.

**Bước 6: Kiểm tra working tree riêng**

~~~bash
git status --short
git diff
git diff --cached
~~~

Các lệnh này cho biết thay đổi local hiện tại. Chúng không phải một phần của commit đã lưu trừ khi đã được stage và commit.

## 14. Những nhầm lẫn thường gặp

- **Nghĩ git show HEAD là nội dung working tree hiện tại:** lệnh hiển thị commit HEAD; thay đổi chưa commit không nằm trong snapshot đó.
- **Nhầm git show commit -- file với git show commit:file:** dạng đầu hiển thị patch; dạng sau hiển thị nội dung tệp ở snapshot.
- **Nghĩ git show so sánh hai commit bất kỳ:** nó tập trung vào object được chọn và parent của commit; dùng git diff A B để so sánh hai snapshot.
- **Dùng HEAD~2 như parent thứ hai:** ~ đi theo parent thứ nhất; dùng ^2 để chọn parent thứ hai của merge commit.
- **Chỉ xem metadata mà kết luận đã hiểu commit:** cần xem thêm file list và patch nếu mục tiêu là hiểu nội dung.
- **Đọc merge commit như commit thường:** phải xác định parent và chọn -m, --cc hoặc git diff phù hợp.
- **Cho rằng Git lưu rename thành loại object riêng:** rename được phát hiện khi hiển thị diff bằng cách so sánh nội dung.
- **Cho rằng git show giải mã nội dung LFS:** Git thường chỉ lưu pointer blob; LFS object được quản lý riêng.
- **Đưa git show <commit>:<path> vào terminal với tệp nhị phân:** output có thể làm terminal hiển thị ký tự rác; hãy redirect sang file.
- **Chia sẻ output mà không rà soát dữ liệu nhạy cảm:** commit message, diff hoặc đường dẫn có thể chứa thông tin nội bộ.

## 15. Sơ đồ chọn lệnh

~~~mermaid
flowchart TD
    A[Cần kiểm tra một commit] --> B[Chọn revision và xác minh thành commit]
    B --> C{Cần xem phần nào?}
    C -- Metadata --> D[git show --no-patch --format=fuller]
    C -- Danh sách file --> E[git show --name-status]
    C -- Thống kê --> F[git show --stat]
    C -- Patch --> G[git show commit]
    C -- Nội dung file tại snapshot --> H[git show commit:path]
    G --> I{Commit là merge?}
    I -- Có --> J[Chọn -m, --cc hoặc diff với parent]
    I -- Không --> K[Đọc patch so với parent]
    D --> L[Đối chiếu với status/index nếu cần]
    E --> L
    F --> L
    H --> L
    J --> L
    K --> L
~~~

Trước khi kết thúc review, hãy tự xác nhận:

1. Tôi đã chọn đúng commit hash/ref và xác minh nó phân giải thành commit chưa?
2. Tôi cần metadata, danh sách tệp, thống kê, patch hay nội dung snapshot?
3. Tôi đã phân biệt snapshot commit với working tree/index hiện tại chưa?
4. Nếu là merge commit, tôi đã xác định parent và góc nhìn diff chưa?
5. Nếu có LFS hoặc submodule, tôi đã kiểm tra dữ liệu ở repository/kho lưu trữ tương ứng chưa?
6. Tôi đã đọc toàn bộ patch liên quan và kiểm tra dữ liệu nhạy cảm trước khi chia sẻ chưa?

git show là cách nhanh để đọc một commit từ metadata đến patch. Khi cần xem tên tệp, thống kê, nội dung snapshot hoặc chữ ký, hãy chọn tùy chọn phù hợp; khi so sánh hai snapshot hoặc phân tích merge, hãy chỉ rõ parent và dùng git diff khi cần. Luôn tách lịch sử đã commit khỏi index và working tree để kết luận đúng về những gì thực sự được lưu trong commit.

## Tài liệu tham khảo

- [Git documentation: git-show](https://git-scm.com/docs/git-show) — hiển thị commit, tag, tree, blob và diff.
- [Git documentation: gitrevisions](https://git-scm.com/docs/gitrevisions) — cú pháp HEAD~n, HEAD^n và biểu thức revision.
- [Git documentation: git-diff](https://git-scm.com/docs/git-diff) — so sánh hai tree/snapshot và các chế độ diff.
- [Git documentation: diff-merges](https://git-scm.com/docs/git-log#_diff_formatting) — cách hiển thị diff của merge commit.
- [Git documentation: git-verify-commit](https://git-scm.com/docs/git-verify-commit) — xác minh chữ ký commit.
- [Pro Git: Viewing the Commit History](https://git-scm.com/book/en/v2/Git-Basics-Viewing-the-Commit-History) — đọc và lọc lịch sử commit.
