# Vì sao mã commit đổi khi nội dung, metadata hoặc commit cha đổi

## Commit ID là gì?

Trong Git, mỗi commit là một object được lưu trong object database. Git gán cho object đó một mã định danh nội dung (object ID hoặc OID) bằng cách băm dữ liệu đã được tuần tự hóa của object.

Vì vậy, mã commit không phải số thứ tự, mã ngẫu nhiên hay mã được cấp bởi máy chủ. Nó được tính từ chính nội dung của commit object. Hai commit có cùng dữ liệu object và cùng thuật toán băm sẽ có cùng object ID; chỉ cần một byte trong dữ liệu object thay đổi thì kết quả băm gần như chắc chắn sẽ khác.

Điều này giải thích vì sao một commit có thể đổi mã dù phần mã nguồn nhìn thấy gần như không đổi. Metadata, commit cha, thông điệp, chữ ký hoặc cấu trúc cây tệp đều tham gia vào dữ liệu được băm.

## Git băm object như thế nào?

Git không chỉ băm phần nội dung thuần của object. Trước khi băm, Git tạo một chuỗi dữ liệu có dạng khái quát:

~~~text
<type> <size>\0<payload>
~~~

Trong đó:

- **type** là loại object, chẳng hạn blob, tree, commit hoặc tag.
- **size** là số byte của phần payload.
- **\0** là byte NUL phân cách phần header object với payload.
- **payload** là dữ liệu thực của object.

Với commit object, Git băm header object cùng toàn bộ payload commit. Bởi vậy, loại object, kích thước và từng byte trong dữ liệu object đều ảnh hưởng tới object ID.

Ví dụ khái niệm:

~~~text
commit 180\0
tree 0123...
parent 4567...
author Linh <linh@example.invalid> 1700000000 +0700
committer Linh <linh@example.invalid> 1700000100 +0700

Add report validation
~~~

Chuỗi trên chỉ minh họa cấu trúc. Mã commit thực tế được tính từ đúng byte của object, không phải từ đoạn văn đã được trình bày hoặc định dạng lại ở đây.

### Thuật toán băm và định dạng object

Repository Git truyền thống thường dùng SHA-1 để tạo object ID dài 40 ký tự hex. Git hiện hỗ trợ repository sử dụng SHA-256, tạo object ID dài 64 ký tự hex.

Kiểm tra định dạng object của repository hiện tại:

~~~bash
git rev-parse --show-object-format
~~~

Khởi tạo repository mới dùng SHA-256:

~~~bash
git init --object-format=sha256 new-project
~~~

Không thể suy ra thuật toán chỉ bằng cách nhìn một chuỗi hash ngắn đã bị rút gọn. Hãy kiểm tra object format của repository.

SHA-1 có các điểm yếu chống va chạm đã được nghiên cứu và chứng minh trong thực tế. Git có các biện pháp giảm thiểu rủi ro liên quan đến va chạm SHA-1, nhưng object ID không nên được hiểu như chữ ký số hay bằng chứng xác thực người tạo commit. Chữ ký commit, quyền truy cập và chính sách máy chủ giải quyết những mục tiêu khác.

Repository dùng SHA-1 và repository dùng SHA-256 không tạo cùng một object ID cho cùng nội dung, vì thuật toán và định dạng object khác nhau. Khả năng trao đổi giữa các repository khác object format còn phụ thuộc phiên bản Git và công cụ xung quanh; không nên tự ý đổi định dạng repository đang dùng chung.

## Cấu trúc của một commit object

Payload của commit object chứa các header và thông điệp commit. Một commit thông thường có cấu trúc khái quát:

~~~text
tree <tree-object-id>
parent <parent-commit-id>
author <name> <email> <timestamp> <timezone>
committer <name> <email> <timestamp> <timezone>
[optional headers]

<commit message>
~~~

Các header trong ngoặc vuông là tùy chọn, không phải literal bắt buộc trong mọi commit.

Ý nghĩa các thành phần:

| Thành phần | Vai trò |
|---|---|
| tree | Object tree gốc mô tả snapshot tệp của commit |
| parent | Commit cha; commit thường có một parent, merge commit có từ hai parent trở lên |
| author | Người được ghi nhận là tác giả thay đổi và thời điểm tác giả tạo thay đổi |
| committer | Người tạo commit object này và thời điểm commit được ghi |
| optional headers | Metadata bổ sung như encoding, chữ ký hoặc thông tin merge tag |
| commit message | Nội dung mô tả commit, bắt đầu sau dòng trống phân cách header và message |

Các header có thứ tự và cách tuần tự hóa cụ thể. Khi bất kỳ phần nào trong payload thay đổi, object ID của commit thay đổi.

Xem cấu trúc commit hiện tại:

~~~bash
git cat-file -p HEAD
~~~

Hoặc xem thông tin commit ở dạng raw:

~~~bash
git show --no-patch --pretty=raw HEAD
~~~

Xem metadata author và committer theo định dạng dễ đọc:

~~~bash
git show --no-patch --pretty=fuller HEAD
~~~

git cat-file -p hiển thị payload đã giải nén của object. Nó giúp đọc tree, parent, author, committer và message; object header dạng commit và kích thước được Git xử lý bên ngoài payload.

## Nội dung snapshot ảnh hưởng tới commit ID như thế nào?

Commit không lưu trực tiếp toàn bộ nội dung của từng file. Header tree trỏ tới một tree object đại diện cho snapshot của thư mục tại commit đó. Tree object lại trỏ tới blob, tree con hoặc gitlink.

Có thể hình dung:

~~~text
Commit
  |
  +-- tree
       |
       +-- blob: src/App.java
       |
       +-- tree: config/
       |     |
       |     +-- blob: application.yml
       |
       +-- blob: README.md
       |
       +-- gitlink: libs/ui-kit
~~~

Blob chứa nội dung tệp. Tree chứa tên, mode, loại entry và object ID của từng mục trong thư mục. Gitlink trong tree trỏ tới commit của submodule.

### Thay đổi nội dung file

Giả sử file src/ReportService.java có nội dung A. Git lưu nội dung đó thành blob. Khi nội dung đổi thành B, blob ID thay đổi.

~~~text
Trước:
tree T1
  └── ReportService.java -> blob A

Sau:
tree T2
  └── ReportService.java -> blob B
~~~

Vì tree T2 tham chiếu blob B thay vì blob A, tree ID thay đổi. Commit trỏ tới tree T2 thay vì T1 nên commit ID cũng thay đổi, ngay cả khi parent và metadata khác không đổi.

Có thể xem blob ID của một file trong working tree:

~~~bash
git hash-object src/ReportService.java
~~~

Lệnh này tính object ID theo loại blob nhưng không ghi object vào object database nếu không dùng tùy chọn -w. Đường dẫn file không được đưa vào payload blob; Git băm nội dung file dưới dạng blob object.

Xem blob được commit lưu cho một đường dẫn:

~~~bash
git rev-parse HEAD:src/ReportService.java
git cat-file -p HEAD:src/ReportService.java
~~~

Hai lệnh trên lần lượt cho biết object ID và nội dung blob được tree của HEAD tham chiếu.

### Thêm hoặc xóa file

Thêm file mới làm tree có thêm entry tham chiếu tới blob mới. Xóa file làm entry tương ứng biến mất khỏi tree. Trong cả hai trường hợp, tree ID thường thay đổi và commit ID cũng thay đổi.

~~~text
Trước:
tree T1
  ├── App.java -> blob A
  └── README.md -> blob R

Sau khi thêm LICENSE:
tree T2
  ├── App.java -> blob A
  ├── README.md -> blob R
  └── LICENSE -> blob L
~~~

Ngay cả khi tất cả file cũ giữ nguyên nội dung, tree vẫn khác vì danh sách entry đã thay đổi.

### Đổi tên hoặc di chuyển file

Git không lưu thao tác rename thành một object riêng trong commit. Một lần rename thường được biểu diễn trong snapshot mới bằng việc bỏ entry ở đường dẫn cũ và thêm entry ở đường dẫn mới.

Nếu nội dung file không đổi, blob ID có thể vẫn giữ nguyên. Tuy nhiên, tree chứa tên và đường dẫn entry đã thay đổi, nên tree ID và commit ID thay đổi.

Khi xem lịch sử, Git có thể suy luận rename dựa trên độ tương đồng nội dung. Đó là khả năng phát hiện rename khi trình bày diff/log, không có nghĩa commit object lưu một trường rename riêng.

### Thay đổi quyền hoặc mode file

Tree entry lưu mode, chẳng hạn file thường, executable, symbolic link hoặc gitlink. Vì mode nằm trong tree, thay đổi executable bit có thể làm tree ID thay đổi dù byte nội dung blob không đổi.

Ví dụ:

~~~bash
git update-index --chmod=+x scripts/deploy.sh
git diff --cached --summary
~~~

Khi thay đổi mode được đưa vào commit, tree mới chứa mode khác và commit ID thay đổi.

### Thay đổi symbolic link hoặc submodule

Với symbolic link, Git lưu nội dung blob là đường dẫn đích của link và tree entry có mode symlink. Đổi đích link có thể đổi blob; đổi loại hoặc mode cũng ảnh hưởng tree.

Với submodule, tree entry dùng mode gitlink và chứa commit ID được superproject ghim. Nếu superproject cập nhật submodule sang commit khác, gitlink thay đổi, tree ID đổi và commit superproject mới có ID khác.

## Metadata làm commit ID thay đổi

Ngay cả khi snapshot tệp giống hệt, thay đổi metadata trong commit object cũng tạo ra payload khác.

### Author và committer là hai danh tính khác nhau

Author là người được ghi nhận đã tạo ra thay đổi. Committer là người tạo commit object đang lưu thay đổi đó vào lịch sử hiện tại.

Trong một commit thông thường, hai trường này thường giống nhau. Nhưng khi cherry-pick, rebase hoặc áp dụng patch từ người khác, author có thể được giữ lại trong khi committer là người thực hiện thao tác mới.

Ví dụ:

~~~text
author Alice <alice@example.invalid> 1700000000 +0700
committer Bob <bob@example.invalid> 1700005000 +0700
~~~

Nếu thay đổi tên hoặc email author/committer, payload commit đổi và object ID đổi.

Thiết lập danh tính cho commit mới:

~~~bash
git config user.name "Developer Name"
git config user.email "dev@example.invalid"
~~~

Kiểm tra metadata đã được ghi vào commit:

~~~bash
git show --no-patch --pretty=fuller HEAD
~~~

Thay đổi user.name hoặc user.email trong cấu hình chỉ ảnh hưởng commit tạo sau đó. Nó không sửa metadata của commit đã tồn tại.

### Timestamp và múi giờ

Author date và committer date được ghi trong commit object dưới dạng timestamp cùng thông tin múi giờ. Cùng một thời điểm nhưng biểu diễn với offset khác có thể tạo ra byte header khác và vì vậy object ID khác.

Ví dụ hai header có cùng thời điểm thực tế nhưng offset khác nhau:

~~~text
author Dev <dev@example.invalid> 1700000000 +0700
author Dev <dev@example.invalid> 1700000000 +0000
~~~

Hai dòng này không giống nhau về byte, nên commit object chứa chúng có hash khác.

Git có thể nhận ngày từ biến môi trường hoặc tùy chọn lệnh trong một số thao tác. Khi điều tra vì sao commit ID khác, hãy xem cả author date và committer date, không chỉ tên/email.

### Commit message

Thông điệp commit là một phần payload. Chỉ cần thay một ký tự, dấu câu, khoảng trắng hoặc newline trong message cũng có thể làm commit ID thay đổi.

Ví dụ:

~~~text
Add report validation
~~~

và:

~~~text
Add report validation.
~~~

là hai thông điệp khác nhau. Nếu các thành phần khác giống nhau, commit object vẫn khác vì message khác.

Sửa message của commit gần nhất:

~~~bash
git commit --amend -m "Add report validation"
~~~

Lệnh amend tạo commit object mới. Dù nội dung file không đổi, committer date thường được cập nhật; nếu message hoặc metadata khác thì ID chắc chắn thay đổi.

### Encoding và header tùy chọn

Commit có thể chứa header bổ sung như encoding khi message dùng encoding được khai báo, gpgsig khi commit được ký, hoặc mergetag trong một số trường hợp merge tag.

Các header này là một phần dữ liệu commit object. Thêm, bỏ hoặc thay đổi chúng làm payload thay đổi và tạo object ID khác.

Chữ ký commit không phải dữ liệu nằm ngoài commit object. Header chữ ký được đưa vào commit object đã ký, vì vậy commit có chữ ký có ID khác commit không ký với nội dung và metadata tương đương.

Chữ ký giúp xác minh commit theo khóa và chính sách tin cậy. Object ID chỉ định danh nội dung object; nó không thay thế quá trình xác minh chữ ký.

## Commit cha ảnh hưởng tới commit ID như thế nào?

Header parent lưu object ID của commit cha. Vì vậy, commit ID phụ thuộc vào commit cha mà nó tham chiếu.

Ví dụ:

~~~text
A---B---C
~~~

Giả sử commit C có parent là B. Nếu tạo một commit mới B2 có cùng snapshot và message với B nhưng metadata khác, B2 có ID khác. Khi phát lại thay đổi của C lên B2, commit mới C2 phải tham chiếu B2 làm parent.

~~~text
A---B---C

A---B2---C2
~~~

Ngay cả khi C2 có cùng snapshot tệp và message với C, parent ID khác khiến commit object khác. Do đó C2 có mã khác C.

Đây là cơ chế tạo thành chuỗi liên kết của lịch sử Git. Mỗi commit tham chiếu commit cha bằng object ID, nên thay đổi ở commit cũ có thể lan tới mã của các commit con được tạo lại.

### Merge commit lưu nhiều parent

Merge commit thường có hai parent hoặc nhiều hơn. Thứ tự parent là một phần payload commit object.

Ví dụ:

~~~text
A---B-------M
     \     /
      C---D
~~~

Commit M có thể lưu:

~~~text
parent B
parent D
~~~

Nếu thứ tự parent đổi thành D rồi B, payload khác và object ID khác, dù tree cuối cùng có thể giống nhau.

Thứ tự parent còn ảnh hưởng ý nghĩa của một số thao tác, ví dụ lựa chọn mainline khi revert merge bằng git revert -m. Vì vậy, không coi các parent chỉ là một tập không có thứ tự.

## Vì sao amend, rebase và cherry-pick thường tạo mã commit mới?

Các thao tác này tạo commit object mới hoặc phát lại commit trên một nền lịch sử khác. Chúng không sửa byte của commit cũ tại chỗ.

### git commit --amend

Amend thay commit tip bằng một commit mới. Nó có thể thay đổi tree, message, author/committer hoặc timestamp.

~~~bash
git commit --amend
~~~

Nếu chỉ muốn sửa message:

~~~bash
git commit --amend -m "Clarify report validation"
~~~

Nếu chỉ muốn cập nhật metadata, dù tree giữ nguyên, commit object vẫn có thể khác. Commit cũ không bị sửa trực tiếp; ref nhánh được di chuyển để trỏ tới commit mới.

### git rebase

Rebase phát lại commit của nhánh lên một base khác. Parent của commit được phát lại thay đổi, và committer metadata thường được tạo lại. Vì parent ID là một phần commit object, các commit mới có ID khác.

~~~bash
git rebase main
~~~

Nếu một commit cũ C có parent B, sau rebase nó có thể thành C' với parent B2. Dù patch và snapshot cuối giống nhau, C' vẫn là commit object khác.

Khi một commit được phát lại, các commit con của nó cũng phải tham chiếu parent mới. Do đó, rebase một chuỗi commit thường tạo lại mã cho toàn bộ chuỗi được phát lại.

### git cherry-pick

Cherry-pick áp dụng thay đổi của commit nguồn lên HEAD hiện tại và tạo commit mới:

~~~bash
git cherry-pick <source-commit>
~~~

Commit mới thường có parent là HEAD hiện tại, khác parent của commit nguồn. Author metadata thường được giữ lại, còn committer metadata phản ánh lần tạo commit mới. Vì parent hoặc committer khác, mã commit thường khác.

Nếu cherry-pick một commit lên đúng parent và tái tạo toàn bộ byte giống hệt, về mặt nguyên tắc object ID sẽ giống nhau; nhưng thao tác thực tế thường tạo metadata committer mới nên không nên kỳ vọng hash trùng.

### Squash merge

Squash merge gom thay đổi của nhiều commit thành một commit mới trên nhánh đích. Commit mới có parent và metadata riêng; dù tổng diff giống với nhánh nguồn, object ID không phải ID của các commit ban đầu.

## Thay đổi ref không làm thay đổi commit object

Một điểm quan trọng khác: tên nhánh và tên tag không nằm trong commit object.

Nhánh Git về cơ bản là một ref trỏ tới commit. Ví dụ refs/heads/main trỏ tới commit A. Khi nhánh di chuyển từ A sang B, commit A và B không bị sửa; chỉ giá trị ref thay đổi.

~~~text
Trước:
refs/heads/main -> A

Sau:
refs/heads/main -> B
~~~

Tương tự, checkout một nhánh khác hoặc tạo nhánh mới không làm thay đổi object ID của các commit đã tồn tại.

Một số thao tác chỉ cập nhật ref:

~~~bash
git branch feature/report
git branch -f main <commit-id>
git update-ref refs/heads/recovery <commit-id>
~~~

Các lệnh này thay đổi hoặc tạo tham chiếu. Chúng không chỉnh sửa payload của commit object.

### HEAD cũng không phải một phần của commit

HEAD thường trỏ tới nhánh hiện tại thông qua symbolic ref, hoặc trỏ trực tiếp tới commit khi ở detached HEAD. Thay đổi HEAD bằng switch hoặc checkout không làm commit ID đổi.

Kiểm tra HEAD và nhánh hiện tại:

~~~bash
git symbolic-ref -q HEAD
git rev-parse HEAD
git branch --show-current
~~~

Khi detached HEAD, lệnh symbolic-ref có thể không trả về nhánh; đó không phải lỗi commit object.

### Tag có hai dạng

Lightweight tag chỉ là một ref trỏ tới object, thường là commit. Đổi tên hoặc di chuyển ref tag không thay đổi commit object.

Annotated tag là một tag object riêng, có thể chứa target object ID, tagger, thời gian, message và chữ ký. Tag object có object ID riêng. Thay đổi metadata hoặc message của annotated tag làm tag object ID thay đổi, nhưng không tự làm commit được tag trỏ tới thay đổi.

Xem object mà tag tham chiếu:

~~~bash
git cat-file -t v1.0.0
git show --no-patch --format=fuller v1.0.0
~~~

Nếu là annotated tag, object type thường là tag. Nếu là lightweight tag trỏ trực tiếp tới commit, object type có thể là commit.

## Thay đổi ở commit cũ có thể làm thay đổi cả chuỗi hash

Do mỗi commit chứa parent ID, lịch sử Git có tính chất liên kết. Nếu bạn viết lại một commit cũ, commit con được tạo lại sẽ phải tham chiếu parent mới.

Ví dụ ban đầu:

~~~text
A---B---C---D  main
~~~

Giả sử B được viết lại thành B2. Các commit C và D nếu được phát lại trên B2 sẽ trở thành C2 và D2:

~~~text
A---B---C---D

A---B2---C2---D2
~~~

Tree của C2 có thể giống C, tree của D2 có thể giống D, nhưng parent chain khác. Vì vậy các commit ID sau điểm viết lại cũng khác.

Đây là lý do rebase hoặc amend một commit đã chia sẻ có thể khiến lịch sử local khác lịch sử remote và cần phối hợp trước khi cập nhật nhánh chung.

Nếu commit cũ vẫn được nhánh khác, tag hoặc reflog tham chiếu, object cũ vẫn có thể còn truy cập được. Việc nhánh chính trỏ tới lịch sử mới không có nghĩa object cũ bị sửa hoặc lập tức bị xóa.

## Phân tích một commit ID bằng các lệnh Git

### Xem commit ID hiện tại

~~~bash
git rev-parse HEAD
git log -1 --oneline --decorate
~~~

git rev-parse HEAD trả về object ID đầy đủ của commit hiện tại theo object format repository.

### Xem loại object và payload

~~~bash
git cat-file -t HEAD
git cat-file -s HEAD
git cat-file -p HEAD
~~~

- -t cho biết loại object.
- -s cho biết kích thước payload tính bằng byte.
- -p hiển thị nội dung object theo dạng phù hợp để đọc.

Với commit, payload cho biết tree, parent, author, committer, header tùy chọn và message.

### Xem tree và các entry

~~~bash
git ls-tree HEAD
git ls-tree -r HEAD
~~~

git ls-tree hiển thị mode, loại object, object ID và tên entry trong tree. Tùy chọn -r đi đệ quy qua các tree con.

Xem riêng tree object:

~~~bash
git rev-parse HEAD^{tree}
git cat-file -p HEAD^{tree}
~~~

Cú pháp ^{tree} yêu cầu Git phân giải tới tree object của commit hoặc tag đã chỉ định.

### So sánh hai commit

~~~bash
git diff <old-commit> <new-commit>
git diff-tree --no-commit-id --name-status -r <new-commit>
~~~

Lệnh đầu so sánh snapshot hai commit. Lệnh thứ hai liệt kê tệp thay đổi trong commit được chỉ định so với parent mặc định; với merge commit, cần chọn cách so sánh phù hợp vì có nhiều parent.

Xem các trường metadata của hai commit:

~~~bash
git show --no-patch --pretty=raw <old-commit>
git show --no-patch --pretty=raw <new-commit>
~~~

Đối chiếu tree ID, parent ID, author, committer và message để tìm thành phần đã đổi.

### Kiểm tra object ID của blob

~~~bash
git hash-object src/ReportService.java
git rev-parse HEAD:src/ReportService.java
~~~

Lệnh đầu băm nội dung file hiện tại trên working tree dưới dạng blob. Lệnh sau lấy blob ID mà commit HEAD tham chiếu cho đường dẫn đó. Nếu khác nhau, nội dung hiện tại không trùng blob được commit lưu, hoặc có khác biệt do cách đọc/clean filter cần được kiểm tra thêm.

Để băm nội dung sau khi áp dụng clean filter theo đường dẫn, Git hỗ trợ tùy chọn --path:

~~~bash
git hash-object --path=src/ReportService.java src/ReportService.java
~~~

Điều này hữu ích trong repository có attributes và clean filter. Khi điều tra hash, cần so sánh cùng cách Git chuẩn hóa nội dung.

## Ví dụ thực hành: cùng nội dung file nhưng commit ID khác

Giả sử bạn tạo một commit trên nhánh feature:

~~~bash
git add src/ReportService.java
git commit -m "Add report validation"
git rev-parse HEAD
~~~

Sau đó amend chỉ để sửa message:

~~~bash
git commit --amend -m "Add report input validation"
git rev-parse HEAD
~~~

So sánh hai mã commit trước và sau. Dù file không thay đổi, message đã khác và committer date thường cũng khác; do đó object ID mới.

Nếu muốn kiểm tra snapshot có thay đổi không, so sánh tree:

~~~bash
git rev-parse HEAD^{tree}
~~~

Trước khi amend, ghi lại tree ID; sau amend, so sánh. Nếu tree ID giống nhau nhưng commit ID khác, khác biệt nằm ở header hoặc message của commit object, không nằm trong snapshot tệp.

## Ví dụ thực hành: parent đổi sau rebase

Giả sử feature được tạo từ main tại B:

~~~text
A---B---C---D  feature
     \
      E---F    main
~~~

Rebase feature lên main:

~~~bash
git switch feature
git rebase main
~~~

Sau rebase:

~~~text
A---B---E---F---C'---D'  feature
~~~

C' và D' là commit mới được phát lại trên nền F. Chúng có parent mới và thường có committer metadata mới, nên ID khác C và D.

Xác minh:

~~~bash
git log --oneline --graph --decorate --all
git show --no-patch --pretty=raw <old-commit>
git show --no-patch --pretty=raw <new-commit>
~~~

Trong thực tế, thay old-commit và new-commit bằng mã commit cũ và mới đã ghi lại trước/sau rebase.

## Những điều không làm commit ID thay đổi

Các hành động sau không tự thay đổi byte của commit object đã tồn tại:

- Đổi tên nhánh đang trỏ tới commit.
- Tạo hoặc xóa một nhánh khác.
- Chuyển HEAD sang nhánh khác hoặc detached HEAD.
- Fetch thêm object hoặc ref từ remote.
- Push một commit lên remote mà không viết lại object.
- Thêm lightweight tag trỏ tới commit.
- Di chuyển ref tag hoặc branch.
- Thay đổi user.name hoặc user.email sau khi commit đã được tạo.

Chúng có thể thay đổi trạng thái repository hoặc khả năng truy cập object, nhưng không sửa commit object đã lưu.

Các thao tác sau thường tạo commit ID mới:

- Sửa nội dung snapshot rồi commit.
- Thêm, xóa, đổi tên hoặc đổi mode file trong snapshot.
- Thay đổi parent hoặc thứ tự parent.
- Thay author, committer, timestamp hoặc timezone.
- Thay commit message.
- Thêm, bỏ hoặc thay đổi header như chữ ký.
- Amend, rebase, cherry-pick hoặc squash tạo commit mới.

Từ “thường” được dùng vì object ID được quyết định bởi byte cuối cùng. Nếu toàn bộ object bytes vẫn giống hệt và cùng hash format, ID sẽ giống nhau dù lệnh tạo object là gì.

## Một số hiểu lầm thường gặp

| Hiểu lầm | Cách hiểu chính xác |
|---|---|
| Commit ID chỉ băm nội dung file | Commit ID băm toàn bộ commit object, gồm tree, parent, metadata, header và message |
| Đổi tên branch làm commit ID đổi | Branch chỉ là ref trỏ tới commit; đổi ref không sửa commit |
| Hai commit có cùng file thì cùng ID | Parent, metadata hoặc message khác vẫn tạo ID khác |
| Rebase chỉ di chuyển commit cũ | Rebase phát lại commit trên parent mới, tạo commit object mới |
| Blob lưu cả tên file | Blob lưu nội dung; tên và mode nằm trong tree |
| Author và committer luôn giống nhau | Có thể khác, nhất là cherry-pick, rebase hoặc áp dụng patch |
| SHA-1 là chữ ký xác thực | Object ID là định danh nội dung; chữ ký số là cơ chế riêng |
| Reset xóa hoặc sửa commit object ngay | Reset chủ yếu di chuyển ref và cập nhật index/working tree tùy tùy chọn; object cũ có thể vẫn còn |
| Annotated tag và commit là cùng một object | Annotated tag có tag object riêng trỏ tới object đích |

## Checklist khi điều tra vì sao commit ID thay đổi

- [ ] Đã ghi lại object format của repository bằng git rev-parse --show-object-format.
- [ ] Đã xem commit object bằng git cat-file -p.
- [ ] Đã so sánh tree ID trước và sau.
- [ ] Đã kiểm tra các parent và thứ tự parent.
- [ ] Đã đối chiếu author, committer, timestamp và timezone.
- [ ] Đã so sánh commit message và các header tùy chọn.
- [ ] Đã kiểm tra mode, path, symlink và gitlink nếu tree thay đổi.
- [ ] Đã xác định thao tác có phải amend, rebase, cherry-pick hoặc squash hay không.
- [ ] Đã phân biệt thay đổi commit object với thay đổi branch/tag/HEAD ref.
- [ ] Đã xác minh object ID đầy đủ, không chỉ hash rút gọn.

## Ghi nhớ

Commit ID là hash của commit object đã được Git tuần tự hóa, không chỉ là hash của các file. Commit object trỏ tới tree và parent, đồng thời chứa author, committer, thời gian, message cùng các header tùy chọn. Tree lại chứa tên, mode và object ID của blob, tree con hoặc gitlink. Vì vậy, đổi nội dung hoặc cấu trúc snapshot, metadata, message, chữ ký, parent hay thứ tự parent đều có thể làm commit ID thay đổi. Ngược lại, đổi tên nhánh, chuyển HEAD hoặc di chuyển tag chỉ thay đổi ref, không sửa commit object. Khi cần tìm nguyên nhân, hãy so sánh payload commit, tree ID, parent và metadata thay vì chỉ nhìn hash rút gọn.

