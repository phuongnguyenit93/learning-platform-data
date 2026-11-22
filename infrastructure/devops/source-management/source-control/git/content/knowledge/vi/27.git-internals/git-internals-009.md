# Phân giải đối tượng và tham chiếu bằng git rev-parse

Git thường cho phép bạn dùng tên dễ nhớ như HEAD, main, origin/main hoặc v1.0.0 thay cho object ID dài. Trước khi một lệnh thao tác với lịch sử, Git cần phân giải tên hoặc biểu thức đó thành object cụ thể. Lệnh **git rev-parse** giúp kiểm tra và chuẩn hóa các revision, ref, object ID, đường dẫn metadata và một số thông tin về repository.

Trong chương **Cấu trúc bên trong** của module **SOURCE_CONTROL_GIT**, bài học này tập trung vào cách Git hiểu tên commit và object. Bạn sẽ học cách phân giải ref, đọc cú pháp revision như HEAD~2 hoặc tag^{commit}, kiểm tra loại object, xử lý hash prefix và dùng rev-parse an toàn trong script. Mục tiêu là biết chính xác một tên đang trỏ đến đâu trước khi dùng nó cho reset, checkout, merge, release hoặc tự động hóa.

Sau bài học, bạn có thể:

- Giải thích sự khác nhau giữa ref, revision expression và object ID.
- Dùng git rev-parse để phân giải HEAD, branch, remote-tracking branch và tag.
- Dùng ^, ~, ^{type}, @{upstream} và biểu thức đường dẫn trong revision.
- Kiểm tra một revision có tồn tại và có đúng loại object hay không.
- Nhận diện ref ngắn bị mơ hồ và dùng tên đầy đủ để tránh nhầm.
- Hiểu hash abbreviation, object format và cách xử lý prefix không duy nhất.
- Dùng --show-toplevel, --git-dir, --git-path và các tùy chọn repository trong script.
- Bảo vệ script khỏi revision đầu vào không hợp lệ hoặc bắt đầu bằng dấu gạch ngang.

## 1. Ref, revision và object ID

Git lưu commit, tree, blob và tag thành các object. Mỗi object có một object ID được tính từ nội dung và metadata của nó. Trong giao diện thường ngày, bạn hiếm khi cần nhập toàn bộ object ID; thay vào đó, Git cho phép dùng tên tham chiếu hoặc biểu thức revision.

| Khái niệm | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| Object ID (OID) | Định danh của một object trong object database | a1b2c3... |
| Ref | Tên tham chiếu đến một object | refs/heads/main, refs/tags/v1.0.0 |
| Revision expression | Biểu thức Git phân giải thành object hoặc tập revision | HEAD~2, main^{commit} |
| Symbolic ref | Ref trỏ đến một ref khác | HEAD thường trỏ đến refs/heads/main |

Branch là ref có thể di chuyển khi có commit mới. Tag thông thường được dùng làm mốc cố định. HEAD cho biết vị trí checkout hiện tại: thường là symbolic ref trỏ đến branch, nhưng cũng có thể trỏ trực tiếp đến commit trong trạng thái detached HEAD.

Ví dụ:

~~~text
HEAD
  |
  v
refs/heads/main
  |
  v
commit C (OID: a1b2c3...)
  |
  v
tree -> blob / tree con
~~~

Khi bạn chạy git rev-parse HEAD, Git phân giải HEAD qua branch hiện tại đến object ID của commit. Khi chạy git rev-parse refs/heads/main, Git đọc trực tiếp ref của branch main. Hai kết quả giống nhau nếu HEAD đang checkout main và branch chưa bị thay đổi giữa hai lần gọi.

## 2. git rev-parse dùng để làm gì?

rev-parse là công cụ phân tích và chuẩn hóa đối số Git. Nó có thể:

- Chuyển tên ref hoặc revision expression thành object ID.
- Kiểm tra một revision có phân giải được thành commit, tree hoặc blob không.
- Trả về tên đầy đủ của ref hoặc dạng viết tắt của branch.
- Hiển thị đường dẫn repository, Git directory, common directory hoặc metadata.
- Hiển thị object format mà repository đang sử dụng.
- Phân tích một số cú pháp revision và tham số mà script truyền cho Git.

Ví dụ cơ bản:

~~~bash
git rev-parse HEAD
git rev-parse main
git rev-parse origin/main
git rev-parse v1.0.0
~~~

Mỗi lệnh in ra object ID mà tên tương ứng phân giải tới. Với annotated tag, object ID đầu tiên có thể là tag object chứ chưa phải commit được tag trỏ tới. Khi cần commit cuối cùng, dùng cú pháp peel như v1.0.0^{commit}.

rev-parse không thay thế git show hoặc git log. Nó trả lời “tên này phân giải thành object/ref nào?”; git show đọc nội dung object, còn git log duyệt lịch sử commit.

## 3. Phân giải ref ngắn và ref đầy đủ

Một ref đầy đủ thường nằm trong một namespace:

| Loại ref | Dạng đầy đủ | Ví dụ |
| --- | --- | --- |
| Branch local | refs/heads/name | refs/heads/main |
| Tag | refs/tags/name | refs/tags/v1.0.0 |
| Remote-tracking branch | refs/remotes/remote/branch | refs/remotes/origin/main |
| Ref khác | refs/namespace/name | refs/notes/commits |

Git hỗ trợ viết ngắn như main, v1.0.0 hoặc origin/main. Nó áp dụng quy tắc tìm kiếm ref để đoán tên đầy đủ phù hợp. Đây là tiện ích DWIM (do what I mean), nhưng có thể gây nhầm khi nhiều ref có cùng tên ngắn.

Ví dụ repository có cả branch và tag cùng tên release:

~~~bash
git show-ref --heads --tags
git rev-parse release
git rev-parse refs/heads/release
git rev-parse refs/tags/release
~~~

Tên ngắn được phân giải theo quy tắc tìm kiếm ref của Git; nếu có nhiều cách hiểu, Git có thể cảnh báo rằng tên bị mơ hồ. Dùng tên đầy đủ như refs/heads/release hoặc refs/tags/release khi kết quả cần chính xác, đặc biệt trong script và quy trình phát hành.

### Xem ref đầy đủ mà một tên phân giải tới

~~~bash
git rev-parse --symbolic-full-name main
git rev-parse --symbolic-full-name v1.0.0
~~~

Tùy chọn --symbolic-full-name yêu cầu Git hiển thị tên đầy đủ của ref khi đối số phân giải thành ref. Nó hữu ích để kiểm tra một tên ngắn đang trỏ đến namespace nào.

Để xem tên branch hiện tại:

~~~bash
git rev-parse --abbrev-ref HEAD
~~~

Nếu HEAD đang detached, kết quả thường là HEAD thay vì tên branch. Có thể kiểm tra trạng thái detached bằng:

~~~bash
git symbolic-ref --quiet --short HEAD
~~~

Lệnh symbolic-ref thất bại khi HEAD không phải symbolic ref; trong script, kiểm tra mã thoát thay vì chỉ dựa vào output.

## 4. Kiểm tra revision có tồn tại và đúng loại object

Một revision có thể phân giải thành commit, tree, blob hoặc tag object. Nếu script cần commit, chỉ kiểm tra “có object” là chưa đủ.

### Dùng --verify

~~~bash
git rev-parse --verify HEAD
git rev-parse --verify main
~~~

--verify yêu cầu Git phân giải một đối số thành đúng một object ID. Nếu không phân giải được, lệnh trả mã lỗi. Dùng --quiet để ẩn thông báo lỗi khi script chỉ cần kiểm tra thành công/thất bại:

~~~bash
git rev-parse --verify --quiet HEAD
~~~

### Yêu cầu object phải là commit

~~~bash
git rev-parse --verify 'HEAD^{commit}'
git rev-parse --verify 'refs/tags/v1.0.0^{commit}'
~~~

Biểu thức ^{commit} yêu cầu Git peel object thành commit. Nếu tag trỏ đến tree hoặc blob thay vì commit, phép kiểm tra này thất bại.

Các kiểu thường dùng:

| Biểu thức | Điều kiện |
| --- | --- |
| ^{object} | Object tồn tại, không yêu cầu một loại cụ thể |
| ^{commit} | Phân giải được thành commit |
| ^{tree} | Phân giải được thành tree |
| ^{blob} | Phân giải được thành blob |
| ^{tag} | Object là annotated tag object |
| ^{} | Peel các lớp tag cho đến object không còn là tag |

Ví dụ kiểm tra tag:

~~~bash
git rev-parse --verify 'v1.0.0^{tag}'
git rev-parse --verify 'v1.0.0^{commit}'
~~~

Lệnh đầu yêu cầu tên v1.0.0 trỏ đến một tag object. Lệnh thứ hai yêu cầu tag phân giải cuối cùng thành commit. Một lightweight tag trỏ trực tiếp đến commit có thể vượt qua kiểm tra ^{commit} nhưng không vượt qua ^{tag}.

### Dùng cat-file khi cần kiểm tra sâu hơn

~~~bash
git cat-file -t <object-id>
git cat-file -e 'HEAD^{commit}'
git show --no-patch --oneline HEAD
~~~

rev-parse phù hợp để phân giải tên và kiểm tra kiểu theo revision syntax. cat-file -t hiển thị loại object thực tế; cat-file -e kiểm tra object có tồn tại và đọc được; git show hiển thị nội dung có ý nghĩa với người dùng.

## 5. Cú pháp chọn parent: ^ và ~

Revision syntax cho phép đi từ một commit đến parent của nó.

### Dấu ^ chọn parent

- HEAD^ hoặc HEAD^1: parent thứ nhất.
- HEAD^2: parent thứ hai.
- HEAD^3: parent thứ ba nếu commit có đủ parent.

Commit thông thường có một parent; merge commit có từ hai parent trở lên. Vì vậy, HEAD^ và HEAD^1 thường giống nhau, còn HEAD^2 chọn nhánh được merge vào trong merge commit theo thứ tự parent.

### Dấu ~ đi theo first-parent

- HEAD~1: parent thứ nhất của HEAD.
- HEAD~2: parent thứ nhất của parent thứ nhất.
- HEAD~3: tiếp tục đi theo chuỗi first-parent ba lần.

Ví dụ:

~~~text
          M (HEAD)
         / \
        A   B
       /
      P
~~~

Với merge commit M:

- HEAD^1 là A.
- HEAD^2 là B.
- HEAD~2 là parent thứ nhất của A, tức P trong sơ đồ.

Vì vậy HEAD~2 không có nghĩa là “commit thứ hai gần nhất trong mọi nhánh”. Nó đi theo first-parent. Dùng ^n khi cần chọn parent cụ thể của merge commit.

Kiểm tra kết quả:

~~~bash
git rev-parse HEAD^
git rev-parse HEAD^2
git rev-parse HEAD~3
git show --no-patch --oneline 'HEAD^2'
~~~

## 6. Peel tag và chọn object bên trong tree

Annotated tag trỏ đến một tag object; tag object lại trỏ đến commit hoặc object khác. Cú pháp peel giúp lấy object cuối cùng hoặc yêu cầu loại object cụ thể.

Ví dụ:

~~~bash
git rev-parse 'v2.0.0^{tag}'
git rev-parse 'v2.0.0^{}'
git rev-parse 'v2.0.0^{commit}'
git rev-parse 'v2.0.0^{tree}'
~~~

Các lệnh trả về object ID của tag object, object cuối sau khi peel, commit hoặc tree tương ứng. Không phải mọi biểu thức đều thành công: nếu tag cuối cùng không trỏ đến loại object được yêu cầu, Git báo lỗi.

### Chọn file tại một revision

Revision có thể kết hợp với đường dẫn trong tree:

~~~bash
git rev-parse 'HEAD:src/app.js'
git rev-parse 'HEAD^{tree}'
~~~

HEAD:src/app.js phân giải thành blob của file tại commit HEAD. HEAD^{tree} phân giải thành tree gốc của commit đó.

Để lấy blob từ index hiện tại:

~~~bash
git rev-parse ':src/app.js'
~~~

Nếu index đang có xung đột, có thể chọn từng stage:

~~~bash
git rev-parse ':1:src/app.js'
git rev-parse ':2:src/app.js'
git rev-parse ':3:src/app.js'
~~~

Trong một merge conflict thông thường, các stage có ý nghĩa:

- Stage 1: phiên bản base chung.
- Stage 2: phiên bản ours.
- Stage 3: phiên bản theirs.

Các biểu thức stage chỉ có ý nghĩa khi index đang chứa các entry tương ứng, thường là trong lúc giải quyết merge conflict. Với rebase, cách hiểu ours/theirs có thể gây nhầm vì vai trò của nhánh đang rebase và nhánh nền khác với một merge thông thường; hãy xác định operation và xem nội dung từng stage trước khi chọn. Với file không xung đột, stage 0 là entry bình thường; cú pháp :0:path có thể dùng để chỉ rõ stage 0.

Để kiểm tra nội dung blob:

~~~bash
git cat-file -p 'HEAD:src/app.js'
~~~

Không nhầm blob ID với đường dẫn file. Blob chỉ chứa nội dung; tên và vị trí file được lưu trong tree.

## 7. Reflog và các selector theo thời gian

Reflog lưu lại một số lần ref local thay đổi. Revision syntax cho phép chọn trạng thái trước đó của HEAD hoặc branch.

Ví dụ:

~~~bash
git rev-parse 'HEAD@{0}'
git rev-parse 'HEAD@{1}'
git rev-parse 'main@{yesterday}'
~~~

- HEAD@{0}: giá trị HEAD hiện tại theo reflog.
- HEAD@{1}: giá trị trước đó của HEAD trong reflog.
- main@{yesterday}: trạng thái ref main tại thời điểm được diễn giải là hôm qua, nếu reflog có dữ liệu phù hợp.

Selector reflog phụ thuộc dữ liệu local và thời gian lưu reflog. Nó không phải ref ổn định để chia sẻ cho đồng đội.

### Upstream và push destination

Khi branch có upstream:

~~~bash
git rev-parse --symbolic-full-name '@{upstream}'
git rev-parse '@{upstream}^{commit}'
~~~

@{upstream} phân giải thành upstream của branch hiện tại, thường là remote-tracking branch như refs/remotes/origin/main.

Trong workflow đẩy lên một remote khác hoặc triangular workflow, push destination có thể khác upstream:

~~~bash
git rev-parse --symbolic-full-name '@{push}'
~~~

Nếu chưa cấu hình upstream hoặc push destination, các biểu thức này có thể không phân giải được. Kiểm tra:

~~~bash
git branch -vv
git config --get-regexp '^branch\..*\.(remote|merge|pushRemote)$'
~~~

### Branch được checkout trước đó

Biểu thức:

~~~bash
git rev-parse '@{-1}'
~~~

chọn vị trí branch/checkout trước đó theo lịch sử checkout. Nó hữu ích khi chuyển qua lại giữa hai branch, nhưng phụ thuộc trạng thái checkout local và không phù hợp làm tên ref ổn định trong script chia sẻ.

## 8. Xử lý tên ref mơ hồ và object ID prefix

### Ref ngắn có thể mơ hồ

Nếu branch, tag hoặc remote-tracking branch có tên trùng, dùng tên đầy đủ:

~~~bash
git rev-parse refs/heads/release
git rev-parse refs/tags/release
git rev-parse refs/remotes/origin/release
~~~

Có thể liệt kê ref:

~~~bash
git show-ref
git for-each-ref --format='%(refname) %(objectname)'
~~~

Trong script, tránh dựa vào quy tắc đoán tên ngắn khi ref có thể trùng. Dùng full ref hoặc xác minh tên trước khi thao tác.

### Hash prefix

Bạn có thể dùng một phần đầu object ID nếu phần đó đủ dài và duy nhất trong repository:

~~~bash
git rev-parse a1b2c3d
~~~

Nếu prefix khớp nhiều object, Git không thể xác định duy nhất và sẽ báo ambiguous. Không nên mặc định hash luôn dài 40 ký tự; repository có thể dùng SHA-1 hoặc SHA-256.

Xem object format:

~~~bash
git rev-parse --show-object-format
~~~

Kết quả thường là sha1 hoặc sha256. Độ dài OID đầy đủ tương ứng khác nhau. Khi lưu ID trong hệ thống tự động hóa, nên lấy output thực tế thay vì cắt chuỗi theo một độ dài cố định.

### Liệt kê object khớp prefix

~~~bash
git rev-parse --disambiguate=a1b2
~~~

--disambiguate liệt kê các object ID bắt đầu bằng prefix được cung cấp. Prefix cần có tối thiểu bốn ký tự hex. Dùng lệnh này khi điều tra prefix mơ hồ; nó có thể trả về nhiều loại object chứ không chỉ commit.

## 9. --short và --abbrev-ref

Để hiển thị OID ngắn hơn:

~~~bash
git rev-parse --short HEAD
git rev-parse --short=12 HEAD
~~~

Git chọn độ dài đủ duy nhất trong repository; khi yêu cầu độ dài cụ thể, nó vẫn có thể tăng độ dài nếu cần tránh trùng.

Để hiển thị tên branch rút gọn:

~~~bash
git rev-parse --abbrev-ref HEAD
git rev-parse --abbrev-ref=strict HEAD
~~~

--abbrev-ref chuyển ref thành dạng ngắn dễ đọc. Chế độ strict yêu cầu cách rút gọn nghiêm ngặt hơn; nếu ref name mơ hồ theo quy tắc DWIM, Git có thể không rút gọn như mong đợi.

Không dùng short hash làm định danh lâu dài trong tài liệu phát hành hoặc hệ thống lưu trữ nếu có thể lưu OID đầy đủ. Short hash chủ yếu tiện hiển thị và gõ lệnh tương tác.

## 10. Dùng --verify và --end-of-options an toàn trong script

Script thường nhận revision từ tham số, biến môi trường, file cấu hình hoặc đầu vào người dùng. Đầu vào có thể rỗng, sai hoặc bắt đầu bằng dấu gạch ngang. Nếu truyền trực tiếp vào lệnh Git, Git có thể hiểu nó là tùy chọn thay vì revision.

Dùng --verify để yêu cầu đúng một object và --end-of-options để đánh dấu rằng các đối số tiếp theo là dữ liệu revision:

~~~bash
candidate=$1

if ! oid=$(git rev-parse --verify --quiet --end-of-options "$candidate^{commit}")
then
    echo "Invalid commit revision" >&2
    exit 1
fi

printf 'Resolved commit: %s\n' "$oid"
~~~

Biểu thức ^{commit} yêu cầu kết quả là commit. --end-of-options ngăn chuỗi đầu vào bắt đầu bằng dấu gạch ngang bị diễn giải thành tùy chọn của rev-parse. --quiet giúp script xử lý lỗi bằng mã thoát mà không cần hiển thị thông báo phân giải mặc định.

Trên PowerShell:

~~~powershell
$candidate = 'main'
$resolved = git rev-parse --verify --quiet --end-of-options "$candidate^{commit}"
if ($LASTEXITCODE -ne 0) {
    throw 'Invalid commit revision'
}
$resolved
~~~

Đối với script production, vẫn cần xác thực đầu vào theo yêu cầu nghiệp vụ và kiểm tra mã thoát của Git. Không dùng eval hoặc ghép chuỗi lệnh shell từ revision do người dùng cung cấp.

### Vì sao cần kiểm tra loại object?

Nếu script gọi git reset --hard với một tên tag có thể trỏ đến tree hoặc blob, thao tác có thể thất bại hoặc không đáp ứng ý định. Xác nhận ^{commit} trước khi truyền revision vào lệnh cần commit giúp phát hiện sai loại sớm.

Ví dụ:

~~~bash
target=$(git rev-parse --verify --quiet --end-of-options 'v1.0.0^{commit}') || exit 1
git show --no-patch --oneline "$target"
~~~

## 11. Các tùy chọn hiển thị vị trí repository

rev-parse cũng hữu ích trong script cần biết repository hiện tại hoặc vị trí metadata.

| Lệnh | Kết quả |
| --- | --- |
| git rev-parse --show-toplevel | Đường dẫn tuyệt đối đến root working tree |
| git rev-parse --show-prefix | Đường dẫn tương đối từ root đến thư mục hiện tại |
| git rev-parse --show-cdup | Số cấp thư mục cần đi lên để đến root |
| git rev-parse --git-dir | Git directory đang được sử dụng |
| git rev-parse --git-common-dir | Common Git directory dùng chung, hữu ích với linked worktree |
| git rev-parse --git-path path | Đường dẫn đến một file hoặc thư mục bên trong Git directory |
| git rev-parse --is-inside-work-tree | true nếu thư mục hiện tại nằm trong working tree |
| git rev-parse --is-inside-git-dir | true nếu thư mục hiện tại nằm trong Git directory |
| git rev-parse --is-bare-repository | true nếu repository là bare |

Ví dụ:

~~~bash
git rev-parse --show-toplevel
git rev-parse --show-prefix
git rev-parse --git-dir
git rev-parse --git-common-dir
git rev-parse --git-path hooks
~~~

### Vì sao dùng --git-path thay vì tự ghép .git?

Trong repository thông thường, người dùng thường thấy thư mục .git. Nhưng trong linked worktree, submodule hoặc repository dùng git-dir riêng, metadata có thể nằm ở vị trí khác hoặc có file trỏ đến Git directory thật.

Ví dụ lấy đường dẫn index:

~~~bash
git rev-parse --git-path index
~~~

Ví dụ lấy thư mục hooks mặc định trong Git directory:

~~~bash
git rev-parse --git-path hooks
~~~

Git tính đường dẫn theo layout repository và các biến môi trường liên quan. Script nên hỏi Git thay vì giả định index luôn nằm ở .git/index.

Lưu ý: --git-path hooks trả về vị trí hooks mặc định trong Git directory. Nếu repository đặt core.hooksPath, Git sẽ dùng thư mục được cấu hình đó thay cho vị trí mặc định. Hãy kiểm tra riêng:

~~~bash
git config --show-origin --get core.hooksPath
~~~

Không diễn giải kết quả --git-path hooks là thư mục hook đang hoạt động trong mọi repository.

### Kiểm tra repository và bare repository

~~~bash
git rev-parse --is-inside-work-tree
git rev-parse --is-inside-git-dir
git rev-parse --is-bare-repository
~~~

Các lệnh trả true hoặc false. Trong script, kiểm tra mã thoát và output để quyết định có thể chạy thao tác cần working tree hay không. Bare repository không có working tree thông thường; nhiều hook server chạy trong bare repository.

## 12. Phân giải revision range

rev-parse có thể phân tích các biểu thức range và chuyển chúng thành đối số revision mà lệnh khác hiểu.

### A..B

Biểu thức A..B biểu thị các commit reachable từ B nhưng không reachable từ A. Khi phân tích bằng rev-parse:

~~~bash
git rev-parse 'main..feature/login'
~~~

Git biểu diễn phạm vi này bằng một đầu vào loại trừ A và một đầu vào bao gồm B, tương đương dạng:

~~~text
^<OID-của-main>
<OID-của-feature-login>
~~~

Để liệt kê các commit thực tế trong phạm vi, dùng:

~~~bash
git log --oneline main..feature/login
~~~

### A...B

Biểu thức A...B biểu thị symmetric difference: các commit reachable từ A hoặc B nhưng không reachable từ cả hai, dựa trên merge base. Đây là cách hữu ích để so sánh hai nhánh phân kỳ:

~~~bash
git log --oneline main...feature/login
~~~

rev-parse có thể chuẩn hóa revision range cho các lệnh Git khác, nhưng không phải công cụ hiển thị nội dung lịch sử. Khi mục tiêu là đọc commit, dùng git log; khi cần lấy OID hoặc xác nhận revision, dùng rev-parse.

## 13. Phân biệt rev-parse với các lệnh gần giống

| Lệnh | Vai trò chính | Khi nên dùng |
| --- | --- | --- |
| git rev-parse | Phân giải revision/ref, kiểm tra kiểu, hiển thị metadata repository | Script cần OID, ref đầy đủ hoặc đường dẫn Git |
| git show-ref | Liệt kê ref và object ID mà chúng trỏ tới | Kiểm tra ref tồn tại và tránh tên trùng |
| git cat-file | Kiểm tra loại, kích thước và nội dung object | Điều tra object database |
| git show | Hiển thị nội dung commit, tag, tree hoặc blob theo dạng dễ đọc | Review một object |
| git log | Duyệt lịch sử commit | Xem tiến trình và quan hệ commit |
| git symbolic-ref | Đọc hoặc cập nhật symbolic ref | Kiểm tra HEAD đang gắn với branch nào |
| git merge-base | Tìm điểm chung giữa các lịch sử commit | Kiểm tra ancestor hoặc base của hai branch |

Không nên dùng rev-parse thay cho mọi lệnh Git khác. Hãy dùng đúng công cụ theo câu hỏi cần trả lời.

## 14. Quy trình thực tế: xác minh target trước thao tác

Giả sử script nhận tên revision để tạo tag phát hành. Trước khi tạo tag, script cần xác nhận target tồn tại và là commit.

### Bước 1: phân giải commit

~~~bash
target=$(git rev-parse --verify --quiet --end-of-options "$1^{commit}") || {
    echo "Target must resolve to a commit" >&2
    exit 1
}
~~~

### Bước 2: xem metadata commit

~~~bash
git show --no-patch --format=fuller "$target"
~~~

Đối chiếu commit với pull request, bản build hoặc thông tin phát hành đã được phê duyệt.

### Bước 3: xác nhận tag chưa tồn tại

~~~bash
git show-ref --verify --quiet refs/tags/v4.0.0
~~~

Nếu lệnh trả mã 0, tag đã tồn tại. Script cần dừng hoặc xử lý theo chính sách thay vì tự ý ghi đè.

### Bước 4: tạo tag tại commit đã xác minh

~~~bash
git tag -a v4.0.0 "$target" -m "Release v4.0.0"
git rev-parse --verify 'refs/tags/v4.0.0^{commit}'
~~~

So sánh OID vừa phân giải với target để xác nhận tag trỏ đúng commit. Với tag đã được ký, dùng git tag -s và xác minh bằng git verify-tag.

## 15. Những nhầm lẫn thường gặp

### HEAD luôn là tên branch?

Không. HEAD thường là symbolic ref trỏ đến branch, nhưng khi checkout commit trực tiếp, HEAD ở detached state và trỏ trực tiếp đến commit.

### git rev-parse v1.0.0 luôn trả về commit?

Không. Nếu v1.0.0 là annotated tag, lệnh có thể trả về tag object. Dùng v1.0.0^{commit} để yêu cầu commit cuối cùng sau khi peel.

### HEAD~2 và HEAD^2 giống nhau?

Không. HEAD~2 đi theo first-parent hai lần; HEAD^2 chọn parent thứ hai của commit HEAD, thường dùng với merge commit.

### Short hash luôn đủ duy nhất?

Không. Prefix có thể mơ hồ nếu nhiều object bắt đầu bằng cùng chuỗi. Git có thể yêu cầu thêm ký tự. Dùng OID đầy đủ trong metadata quan trọng.

### @{-1} là commit trước đó?

Không nhất thiết. Nó chọn vị trí checkout/branch trước đó theo lịch sử checkout. Dùng HEAD@{1} nếu mục tiêu là trạng thái HEAD trước đó trong reflog.

### --verify chỉ kiểm tra commit?

Không. Nó kiểm tra một object có thể phân giải được. Dùng ^{commit}, ^{tree} hoặc ^{blob} để yêu cầu loại object cụ thể.

### --symbolic-full-name luôn trả OID?

Không. Tùy chọn này hiển thị tên ref đầy đủ nếu đối số là ref. Nếu cần OID, dùng rev-parse bình thường hoặc kết hợp với tùy chọn phù hợp.

## 16. Tự kiểm tra

Repository có branch main, branch feature/api, remote-tracking branch origin/main và annotated tag v2.0.0. HEAD hiện đang checkout feature/api.

Hãy trả lời:

1. Lệnh nào lấy OID commit mà HEAD đang trỏ tới?
2. Lệnh nào xác nhận v2.0.0 có thể phân giải thành commit?
3. Lệnh nào cho biết v2.0.0 là tag object hay object loại khác?
4. HEAD^2 có ý nghĩa gì nếu HEAD là merge commit?
5. HEAD~2 khác HEAD^2 như thế nào?
6. Lệnh nào xem upstream của branch hiện tại?
7. Vì sao script nên dùng --verify --end-of-options và ^{commit}?
8. Lệnh nào lấy đường dẫn hooks theo layout repository hiện tại?

**Gợi ý:** Dùng git rev-parse HEAD để lấy OID. Dùng git rev-parse --verify 'v2.0.0^{commit}' để yêu cầu commit. Dùng git cat-file -t v2.0.0 để xem loại object trực tiếp. HEAD^2 là parent thứ hai; HEAD~2 đi theo first-parent hai lần. Dùng git rev-parse --symbolic-full-name '@{upstream}' để xem upstream. --verify kiểm tra đúng một object, --end-of-options bảo vệ đầu vào khỏi bị hiểu thành tùy chọn và ^{commit} yêu cầu đúng loại. Dùng git rev-parse --git-path hooks để lấy đường dẫn hooks.

## Kết luận

git rev-parse giúp biến tên ref và revision expression thành object ID cụ thể, xác nhận kiểu object và tìm metadata repository. Hãy phân biệt ref với object, dùng ^ và ~ đúng mục đích, peel annotated tag bằng ^{commit}, kiểm tra tên ngắn có mơ hồ không và không giả định hash có độ dài cố định. Trong script, kết hợp --verify, --end-of-options và bộ lọc kiểu object để xác nhận target trước thao tác. Khi cần đường dẫn Git hoặc thông tin worktree, hỏi Git bằng --git-path, --git-dir và --git-common-dir thay vì tự đoán layout thư mục.
