# Địa chỉ theo nội dung và vai trò mã băm đối tượng

Git nhận diện dữ liệu bằng **địa chỉ theo nội dung** (content-addressed storage): mỗi object được định danh bằng mã băm tính từ nội dung đã tuần tự hóa của object đó. Vì mã băm phụ thuộc vào dữ liệu, cùng một object trong repository có cùng object ID; nếu dữ liệu thay đổi, ID cũng thay đổi. Nhờ cơ chế này, Git có thể lưu snapshot, tái sử dụng dữ liệu trùng lặp và kiểm tra tính toàn vẹn của lịch sử.

Object ID (OID) thường được gọi là hash hoặc mã băm. OID xuất hiện trong commit, tree, tag, index, reflog và các lệnh tra cứu Git. Để hiểu cách Git lưu lịch sử, cần phân biệt object hash với tên branch/tag, hiểu những thành phần được đưa vào phép băm và biết hash có thể chứng minh điều gì.

## 1. Địa chỉ theo nội dung là gì?

Trong hệ thống lưu trữ thông thường, dữ liệu thường được tìm theo tên file hoặc vị trí. Với địa chỉ theo nội dung, hệ thống tính một mã từ dữ liệu rồi dùng mã đó làm định danh. Git áp dụng ý tưởng này cho các object.

Ví dụ, khi hai file ở hai thư mục có cùng nội dung byte, Git có thể lưu chung một blob object. Tên file và đường dẫn không nằm trong blob; chúng nằm trong tree object. Vì vậy, đổi tên file mà không đổi nội dung không làm thay đổi blob ID, dù tree chứa đường dẫn đó sẽ thay đổi.

Mô hình khái quát:

```text
Nội dung object
       |
       v
Tuần tự hóa: loại + kích thước + byte nội dung
       |
       v
Hàm băm của object
       |
       v
Object ID (OID)
       |
       v
Địa chỉ để lưu, tìm và tham chiếu object
```

OID không phải số thứ tự commit. Nó không nói commit mới hay cũ, branch nào chứa commit, hoặc commit thuộc phiên bản phát hành nào. Nó chỉ định danh một object theo nội dung và định dạng object của repository.

## 2. Git tính object ID như thế nào?

Git không băm riêng phần byte nội dung file. Trước khi băm, Git tạo một phần header gồm loại object và kích thước nội dung, theo dạng:

```text
<type> <size>\0<payload>
```

Trong đó:

- `<type>` là loại object, ví dụ `blob`, `tree`, `commit` hoặc `tag`.
- `<size>` là kích thước payload tính bằng byte, biểu diễn dưới dạng số thập phân.
- `\0` là byte NUL phân tách header và payload.
- `<payload>` là nội dung thực của object sau khi tuần tự hóa.

Với repository dùng SHA-1, cách tính có thể hình dung như sau:

```text
OID = SHA1("blob " + decimal(size) + NUL + payload)
```

Với object blob có nội dung `hello\n`, Git băm chuỗi header `blob 6`, byte NUL, rồi sáu byte nội dung. Header giúp cùng một chuỗi byte nhưng thuộc loại object khác nhau có ID khác nhau. Kích thước cũng là một phần của dữ liệu được băm.

Git dùng hàm băm theo object format của repository. SHA-1 là định dạng phổ biến lâu đời, còn Git hiện hỗ trợ định dạng object SHA-256 trong các phiên bản và hệ thống tương thích. Vì vậy, không nên mặc định mọi OID đều có cùng độ dài hoặc luôn là SHA-1.

## 3. Bốn loại object chính

Git lưu lịch sử bằng một số loại object có vai trò khác nhau:

| Loại object | Payload chứa gì? | Vai trò |
|---|---|---|
| Blob | Nội dung file | Lưu byte nội dung, không lưu tên hoặc đường dẫn file |
| Tree | Danh sách entry gồm mode, tên và OID của object con | Mô tả cấu trúc thư mục và liên kết file/subtree |
| Commit | OID của tree, parent commit, tác giả, committer, thời gian và thông điệp | Ghi nhận một snapshot cùng quan hệ với lịch sử trước đó |
| Annotated tag | OID object đích, loại đích, tên tag, tagger, thời gian, thông điệp và có thể có chữ ký | Gắn nhãn có metadata vào object, thường là commit phát hành |

### Blob: mã băm của nội dung file

Blob lưu nội dung file. Tên file không được lưu trong blob, nên hai file có nội dung giống hệt nhau có thể dùng cùng một blob ID.

Ví dụ:

```text
src/config.yml  ----+
                   +----> blob 9f... (cùng nội dung)
backup/config.yml -+
```

Nếu bạn đổi tên `src/config.yml` thành `src/app-config.yml` mà không đổi nội dung, blob vẫn có thể được tái sử dụng. Tree chứa tên cũ và tree chứa tên mới có nội dung khác nhau nên có OID khác nhau.

### Tree: mã băm của cấu trúc thư mục

Tree object ghi các entry con. Mỗi entry có mode, tên và OID của blob hoặc tree con. Do tên và cấu trúc thư mục nằm trong tree, đổi tên file hoặc di chuyển thư mục sẽ làm tree tương ứng thay đổi, ngay cả khi blob file không đổi.

Xem tree của commit hiện tại:

```bash
git ls-tree HEAD
git ls-tree -r HEAD
```

`git ls-tree` hiển thị mode, loại object, OID và tên entry. Tùy chọn `-r` duyệt đệ quy các tree con.

### Commit: mã băm của snapshot và lịch sử cha

Commit object tham chiếu đến một tree đại diện snapshot tại thời điểm commit. Nó cũng chứa thông tin tác giả, người tạo commit, thời gian, thông điệp và một hoặc nhiều parent commit.

Ví dụ minh họa nội dung commit:

```text
tree 8a...
parent 3c...
author An Nguyen <an@example.com> 1730000000 +0700
committer An Nguyen <an@example.com> 1730000000 +0700

Add payment validation
```

Commit hash phụ thuộc cả tree và parent cùng metadata. Do đó, cùng nội dung file nhưng tạo commit ở thời điểm khác, với thông điệp khác hoặc parent khác thì thường có OID khác.

Merge commit thường có từ hai parent trở lên. Rebase tạo commit mới với parent mới, vì thế commit được phát lại nhận OID mới dù phần thay đổi file có thể giống commit cũ.

### Annotated tag: object có metadata riêng

Annotated tag là một object riêng, có thể chứa thông điệp và chữ ký. Lightweight tag chỉ là một ref trỏ trực tiếp đến object đích nên không có tag object riêng.

Xem nội dung annotated tag:

```bash
git cat-file -p refs/tags/v1.2.0
```

Payload của tag object chứa OID đích và thông tin tagger. Nếu tag được ký, phần chữ ký cũng thuộc nội dung tag object; thay đổi nội dung hoặc đối tượng đích sẽ làm tag object khác đi.

## 4. OID là địa chỉ của object, không phải tên branch

Branch và tag là các **ref** (tham chiếu) trỏ đến object. Chúng không phải object ID và không có cùng tính chất bất biến.

Ví dụ:

```text
refs/heads/main  ---------> commit 4a...
refs/heads/feature -------> commit 9c...
refs/tags/v1.2.0 --------> tag object 7e... ---> commit 4a...
```

Khi tạo commit mới trên `main`, Git cập nhật ref `refs/heads/main` sang commit mới. Commit cũ vẫn tồn tại nếu còn được tham chiếu hoặc chưa bị dọn. Ngược lại, OID của một object đã tạo không thay đổi khi branch di chuyển.

`HEAD` thường là symbolic ref trỏ đến branch hiện tại, chẳng hạn `refs/heads/main`. Khi ở detached HEAD, `HEAD` chứa trực tiếp OID của commit thay vì tên branch.

Kiểm tra:

```bash
git symbolic-ref -q HEAD
git rev-parse HEAD
git show-ref --heads --tags
```

Lệnh đầu hiển thị branch mà `HEAD` trỏ tới nếu đang ở trạng thái symbolic; lệnh thứ hai in OID commit hiện tại; lệnh thứ ba liệt kê các ref branch và tag cùng OID tương ứng.

## 5. Thực hành tính và ghi object bằng git hash-object

`git hash-object` cho phép tính OID của nội dung mà không cần tạo commit. Ví dụ tính ID của một file:

```bash
git hash-object README.md
```

Theo mặc định, lệnh tính OID nhưng không ghi object vào object database. Muốn vừa tính vừa lưu object, dùng `-w`:

```bash
git hash-object -w README.md
```

Bạn có thể dùng nội dung từ standard input:

```bash
git hash-object --stdin < README.md
```

Lưu object được tính từ standard input:

```bash
git hash-object -w --stdin < README.md
```

Sau khi ghi bằng `-w`, object có thể được tra cứu theo OID:

```bash
git cat-file -t <OID>
git cat-file -s <OID>
git cat-file -p <OID>
```

- `-t` cho biết loại object.
- `-s` cho biết kích thước payload.
- `-p` hiển thị nội dung đã giải mã ở dạng phù hợp với loại object.

Nếu object là blob, `-p` in nội dung file. Nếu là tree, commit hoặc tag, Git hiển thị cấu trúc tương ứng. Lệnh `hash-object` rất hữu ích để quan sát rằng cùng nội dung trong cùng object format sẽ tạo cùng blob OID.

### Thử nghiệm tính bất biến theo nội dung

Trong repository thử nghiệm, tạo hai file có cùng nội dung:

```bash
git hash-object file-a.txt
git hash-object file-b.txt
```

Nếu hai file có byte nội dung giống nhau và được xử lý cùng cách, hai lệnh sẽ in cùng OID. Sau đó sửa một ký tự trong `file-b.txt` và tính lại; OID sẽ thay đổi.

Tên file không được đưa vào blob payload. Tuy nhiên, nếu stage hoặc commit hai file này, tên và đường dẫn sẽ được ghi trong tree object.

## 6. Tra cứu object bằng git cat-file

`git cat-file` là công cụ đọc object theo OID hoặc revision có thể phân giải thành OID.

Ví dụ đọc commit hiện tại:

```bash
git cat-file -t HEAD
git cat-file -p HEAD
```

Lấy tree OID mà commit trỏ đến:

```bash
git rev-parse 'HEAD^{tree}'
```

Đọc tree:

```bash
git cat-file -p 'HEAD^{tree}'
```

Đọc một blob theo đường dẫn tại commit:

```bash
git rev-parse 'HEAD:README.md'
git cat-file -p 'HEAD:README.md'
```

`HEAD:README.md` là cú pháp revision:path. Git tìm object được đường dẫn đó tham chiếu trong tree của `HEAD`, rồi trả về OID hoặc nội dung tương ứng.

Để tra cứu nhiều object hiệu quả, `git cat-file --batch` nhận danh sách OID hoặc revision từ standard input và xuất thông tin theo từng object. Chế độ batch hữu ích cho script phân tích repository lớn vì tránh khởi chạy một tiến trình Git cho mỗi object.

## 7. Object ID giúp Git tái sử dụng và phát hiện thay đổi như thế nào?

### Tái sử dụng nội dung trùng lặp

Vì blob được định danh theo nội dung, nếu nhiều file hoặc nhiều snapshot chứa cùng byte dữ liệu, Git có thể tham chiếu cùng một blob object. Điều này giúp tiết kiệm dung lượng và tránh lưu lặp nội dung không cần thiết.

Ví dụ, một file `LICENSE` không thay đổi qua 100 commit thường không cần 100 blob riêng. Các tree của từng snapshot có thể tiếp tục tham chiếu cùng blob OID.

### Phát hiện nội dung không khớp

Khi object được đọc, Git có thể tính lại hash từ header và payload để kiểm tra OID có khớp hay không. Nếu dữ liệu bị hỏng hoặc bị thay đổi mà không cập nhật định danh phù hợp, kiểm tra tính toàn vẹn có thể phát hiện lỗi.

Kiểm tra object database:

```bash
git fsck --full
```

`git fsck` kiểm tra kết nối và tính nhất quán của object trong repository, bao gồm các object có thể không còn được ref tham chiếu. Lệnh này hữu ích khi nghi ngờ object bị hỏng hoặc lịch sử có tham chiếu thiếu.

### Thay đổi nhỏ có thể làm thay đổi nhiều OID

Nếu bạn sửa một file, blob của file đó đổi OID. Tree chứa file đó đổi OID; các tree cha có thể đổi theo; commit tham chiếu đến tree mới cũng đổi OID. Nếu commit mới là parent của commit khác, các commit con được tạo lại cũng có thể đổi OID.

```text
Sửa byte trong file
       |
       v
Blob OID mới
       |
       v
Tree OID mới
       |
       v
Commit OID mới
       |
       v
Các commit con được tạo lại có parent mới
```

Đây là lý do rebase, amend hoặc lọc lịch sử có thể thay đổi mã commit dù chỉ sửa một file ở một commit cũ.

## 8. OID trong loose object và packfile

Khi Git ghi một object mới, object có thể được lưu dưới dạng **loose object** trong `.git/objects`. Đường dẫn được tạo từ OID: hai ký tự đầu làm tên thư mục, phần còn lại làm tên file. Nội dung object được nén, thường bằng zlib.

Ví dụ dạng đường dẫn:

```text
.git/objects/ab/cdef0123456789...
```

Trong repository lớn, Git thường gom object vào **packfile** để tiết kiệm dung lượng và giảm số lượng file. Packfile có thể dùng delta compression: lưu khác biệt giữa các object liên quan thay vì lưu lại toàn bộ payload.

Điểm quan trọng là OID được tính từ nội dung object logic đã giải nén, không phải từ byte nén hoặc vị trí object trong packfile. Git có thể thay cách đóng gói object mà không làm thay đổi OID của object đó.

Kiểm tra thống kê object:

```bash
git count-objects -vH
```

Lệnh này hiển thị số lượng loose object, dung lượng và thông tin pack. Nếu muốn xem chi tiết object trong pack, có thể dùng `git verify-pack -v` với file `.idx` tương ứng trong `.git/objects/pack/`.

## 9. SHA-1 và SHA-256 trong Git

OID SHA-1 thường có 40 ký tự hexadecimal (160 bit). Git cũng hỗ trợ repository dùng SHA-256 với OID dài 64 ký tự hexadecimal (256 bit), tùy phiên bản Git và mức hỗ trợ của dịch vụ hosting/tooling.

Kiểm tra object format của repository hiện tại:

```bash
git rev-parse --show-object-format
```

Kết quả thường là `sha1` hoặc `sha256`.

Tạo repository thử nghiệm dùng SHA-256:

```bash
git init --object-format=sha256 sha256-lab
```

Lệnh yêu cầu phiên bản Git hiện tại hỗ trợ object format SHA-256. Trước khi dùng trong dự án thật, hãy xác nhận máy chủ Git, công cụ CI, IDE, thư viện Git và các tích hợp khác đều hỗ trợ cùng định dạng. Repository SHA-1 và SHA-256 không thể được coi là thay thế trực tiếp cho nhau chỉ bằng cách đổi độ dài OID; cần cơ chế tương thích mà hệ sinh thái đang sử dụng hỗ trợ.

SHA-1 đã có các tấn công va chạm thực tế trong lĩnh vực mật mã. Git có các biện pháp phát hiện va chạm đã biết trong một số đường xử lý, nhưng không nên xem SHA-1 là nền tảng bảo mật mới có mức chống va chạm hiện đại. SHA-256 có biên an toàn rộng hơn, nhưng việc chọn object format còn phụ thuộc khả năng tương thích của server và công cụ.

## 10. Hash không phải mã hóa và không chứng minh danh tính

Một số hiểu nhầm thường gặp:

- **Hash không phải mã hóa.** Từ OID không thể giải mã để lấy lại nội dung object. Muốn đọc object, bạn cần dữ liệu object trong repository.
- **Hash không che giấu nội dung.** Người có repository vẫn có thể đọc blob và commit; OID chỉ là định danh, không phải cơ chế bảo mật dữ liệu.
- **Hash không tự chứng minh ai tạo object.** Commit có trường author/committer nhưng các trường này là dữ liệu trong object, không phải bằng chứng danh tính được xác thực.
- **Hash không thay chữ ký số.** Signed commit hoặc signed tag có thể chứng minh người giữ khóa đã ký object tương ứng, nếu khóa và danh tính được xác minh đúng.
- **Va chạm là khả năng lý thuyết và thực tế phụ thuộc thuật toán.** Không nên diễn giải OID như một giá trị không thể trùng trong mọi điều kiện.

Để xác minh nguồn phát hành, hãy dùng chữ ký commit/tag và quy trình quản lý khóa. Để bảo vệ nội dung riêng tư, dùng quyền truy cập repository và cơ chế bảo mật phù hợp; không dựa vào việc OID khó đoán.

## 11. Quy trình lần theo OID trong repository

Khi cần hiểu một file hoặc commit được lưu dưới dạng object nào, có thể thực hiện:

1. **Xem object format.** Chạy `git rev-parse --show-object-format` để biết thuật toán hash của repository.
2. **Tìm OID của commit.** Dùng `git rev-parse HEAD` hoặc `git log --oneline`.
3. **Đọc commit object.** Dùng `git cat-file -p HEAD` để xem tree, parent, author, committer và message.
4. **Lấy tree OID.** Dùng `git rev-parse 'HEAD^{tree}'`, rồi đọc tree bằng `git cat-file -p` hoặc `git ls-tree`.
5. **Tìm blob của file.** Dùng `git rev-parse 'HEAD:path/to/file'`, rồi kiểm tra bằng `git cat-file -t` và `-p`.
6. **Kiểm tra tính toàn vẹn.** Chạy `git fsck --full` nếu đang điều tra object bị thiếu hoặc hỏng.

Ví dụ:

```bash
git rev-parse --show-object-format
git rev-parse HEAD
git cat-file -p HEAD
git ls-tree HEAD
git rev-parse 'HEAD:README.md'
git cat-file -p 'HEAD:README.md'
```

Các lệnh này cho thấy đường đi từ ref `HEAD` đến commit, từ commit đến tree, rồi từ tree đến blob chứa nội dung file.

## 12. Bài tập thực hành

Trong một repository thử nghiệm:

1. Tạo hai file có nội dung byte giống nhau và chạy `git hash-object` cho cả hai. Ghi nhận OID.
2. Đổi tên một file nhưng giữ nguyên nội dung; stage thay đổi và so sánh blob OID với tree entry trước đó.
3. Sửa một ký tự trong file, tính lại OID và giải thích vì sao blob hash thay đổi.
4. Chạy `git cat-file -t`, `-s`, `-p` với một blob OID, rồi thử với `HEAD` để so sánh các loại object.
5. Dùng `git cat-file -p HEAD` để tìm tree và parent commit; dùng `git ls-tree` để xem OID của file và thư mục.
6. Tạo commit mới, so sánh OID commit trước và sau. Giải thích tác động của tree, parent, author/committer và message.
7. Chạy `git count-objects -vH` và `git fsck --full` để xem thống kê và kiểm tra object database.
8. Trong repository mới chỉ dùng cho thử nghiệm, thử `git init --object-format=sha256` nếu phiên bản Git hỗ trợ và so sánh độ dài OID với repository SHA-1.

Bạn hoàn thành bài tập khi giải thích được Git băm header cùng payload, phân biệt blob/tree/commit/tag, hiểu vì sao branch có thể di chuyển nhưng OID của object không đổi và biết giới hạn bảo mật của mã băm.
