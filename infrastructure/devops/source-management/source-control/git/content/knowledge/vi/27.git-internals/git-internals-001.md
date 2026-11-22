# Mô hình đối tượng blob, tree, commit và annotated tag

Git lưu lịch sử bằng các **object** bất biến được nhận diện bằng mã băm nội dung. Bốn loại object thường gặp nhất là **blob**, **tree**, **commit** và **tag**. Chúng liên kết với nhau để mô tả nội dung file, cấu trúc thư mục, snapshot của dự án và các mốc phát hành.

Hiểu mô hình này giúp bạn biết vì sao Git có thể so sánh hai phiên bản, vì sao nhiều file có nội dung giống nhau có thể dùng chung dữ liệu, vì sao branch chỉ là tham chiếu có thể di chuyển và vì sao annotated tag khác lightweight tag. Đây là nền tảng để đọc lịch sử, kiểm tra object và hiểu cách Git lưu trữ dữ liệu trong repository.

## 1. Git lưu snapshot bằng các object

Một commit trong Git không phải là bản vá chỉ chứa những dòng vừa thay đổi. Commit trỏ tới một **tree** mô tả toàn bộ trạng thái thư mục tại thời điểm commit. Tree lại trỏ tới các blob chứa nội dung file và các tree con mô tả thư mục con.

```text
Commit C
  |
  +-- tree: root
        |
        +-- blob: README.md
        |
        +-- tree: src
        |     |
        |     +-- blob: Main.java
        |     +-- blob: Parser.java
        |
        +-- tree: docs
              |
              +-- blob: guide.md
```

Mỗi object có một mã định danh nội dung (object ID, thường viết tắt là OID). Tree lưu tên, mode, loại và OID của từng mục bên trong. Commit lưu OID của tree gốc cùng thông tin lịch sử. Annotated tag lưu thông tin về một object được gắn nhãn, thường là commit phát hành.

Các object liên kết với nhau bằng OID chứ không phải bằng đường dẫn tuyệt đối trên máy. Vì vậy, cùng một commit có thể được checkout vào nhiều thư mục làm việc khác nhau mà vẫn tham chiếu cùng object database.

## 2. Bốn loại object chính

| Loại object | Lưu gì? | Tham chiếu tới |
|---|---|---|
| **blob** | Nội dung byte của một file | Không tham chiếu object khác |
| **tree** | Danh sách mục trong một thư mục: tên, mode, loại và OID | Blob, tree con hoặc gitlink tới commit submodule |
| **commit** | Một snapshot cùng metadata và thông điệp commit | Một tree và không hoặc nhiều commit cha |
| **tag** | Metadata của một annotated tag và thông điệp gắn nhãn | Một object được tag, thường là commit |

Tên file không được lưu trong blob. Tên và vị trí file nằm trong tree. Commit không lưu trực tiếp toàn bộ nội dung file; nó trỏ tới tree. Annotated tag không tạo snapshot mới; nó tạo một object mô tả nhãn và object đích.

## 3. Blob: nội dung của file

Blob (binary large object) lưu byte nội dung của một file. Nó không lưu tên file, đường dẫn, thời gian sửa đổi hay quyền sở hữu của file trên hệ điều hành.

Ví dụ, hai file ở hai thư mục khác nhau nhưng có nội dung byte giống hệt nhau có thể cùng trỏ tới một blob:

```text
tree root
  |
  +-- README.md --------+
  |                     |
  +-- docs/intro.txt ---+----> blob B
```

Git nhận diện blob theo nội dung, nên không cần lưu hai bản sao object riêng chỉ vì file nằm ở hai đường dẫn khác nhau. Nếu nội dung thay đổi, OID thường sẽ khác; về mặt lý thuyết vẫn có thể xảy ra va chạm hàm băm, dù Git dùng các thuật toán được thiết kế để khiến việc này rất khó khai thác.

Có thể lấy OID của nội dung file đã được commit:

```bash
git rev-parse HEAD:README.md
```

Sau đó xem loại object và nội dung:

```bash
git cat-file -t HEAD:README.md
git cat-file -p HEAD:README.md
git cat-file -s HEAD:README.md
```

- **-t** in loại object; với file thông thường kết quả là blob.
- **-p** in nội dung object.
- **-s** in kích thước nội dung tính bằng byte.

Biểu thức **HEAD:README.md** có nghĩa là lấy object tại đường dẫn README.md trong tree được commit HEAD tham chiếu. Nếu file không tồn tại ở commit đó hoặc đường dẫn sai, Git sẽ báo không phân giải được object.

### Tạo và kiểm tra blob bằng hash-object

Có thể yêu cầu Git tính OID cho nội dung mà không cần thêm file vào repository:

```bash
printf 'hello\n' | git hash-object --stdin
```

Lệnh trả về OID của blob tương ứng. Mặc định, git hash-object chỉ tính mã băm; nó không ghi object vào object database.

Thêm tùy chọn **-w** để ghi object vào repository:

```bash
printf 'hello\n' | git hash-object -w --stdin
```

Git in OID của object vừa ghi. Thay **<blob-oid>** bằng OID thực tế để kiểm tra:

Các chuỗi đặt trong dấu ngoặc nhọn như `<blob-oid>`, `<commit-oid>` hoặc `<target-oid>` là chỗ giữ chỗ trong ví dụ; hãy thay bằng OID thật trước khi chạy lệnh.

```bash
git cat-file -t <blob-oid>
git cat-file -p <blob-oid>
git cat-file -s <blob-oid>
```

Đây là lệnh plumbing hữu ích khi tìm hiểu object database hoặc xây dựng công cụ. Object được ghi bằng -w nhưng chưa được branch, tag hay commit nào tham chiếu có thể là object unreachable cho tới khi được liên kết vào lịch sử.

## 4. Tree: cấu trúc thư mục

Tree mô tả các mục trực tiếp trong một thư mục. Mỗi mục gồm mode, loại object, OID và tên. Ví dụ đầu ra của:

```bash
git ls-tree HEAD
```

có thể trông như sau:

```text
100644 blob 7a1b...    README.md
040000 tree 9c2d...    src
040000 tree 1e8f...    docs
100755 blob 4d6a...    scripts/build.sh
```

Các cột thể hiện:

1. **Mode**: kiểu/quyền mà Git theo dõi cho mục đó.
2. **Type**: loại object được tham chiếu.
3. **OID**: mã định danh object.
4. **Name**: tên mục trong thư mục.

Một số mode thường gặp:

| Mode | Ý nghĩa |
|---|---|
| **100644** | File thông thường không có bit executable |
| **100755** | File thông thường có bit executable |
| **120000** | Symbolic link; nội dung blob lưu đích liên kết |
| **040000** | Thư mục được biểu diễn bằng tree con |
| **160000** | Gitlink tới commit của submodule |

Tree chỉ liệt kê các mục ngay bên trong thư mục đó. Khi gặp mục tree, Git tham chiếu tới tree con để mô tả nội dung thư mục sâu hơn. Thư mục rỗng không được lưu như một mục độc lập trong tree; Git lưu file và cấu trúc cần thiết để tái tạo các đường dẫn có nội dung.

Xem tree gốc và toàn bộ mục bên dưới:

```bash
git cat-file -p 'HEAD^{tree}'
git ls-tree -r HEAD
git ls-tree -r --name-only HEAD
```

- **HEAD^{tree}** phân giải commit hiện tại về tree gốc.
- **-r** duyệt đệ quy qua các tree con.
- **--name-only** chỉ in đường dẫn, không in mode/type/OID.

Tree không lưu timestamp hoặc chủ sở hữu file như filesystem. Git tập trung vào nội dung, tên, cấu trúc và một số mode cần thiết để tái tạo working tree.

## 5. Commit: snapshot và lịch sử

Commit object ghi nhận một snapshot của dự án và thông tin về cách snapshot đó tham gia lịch sử. Một commit thông thường có các thành phần:

- OID của tree gốc.
- Một hoặc nhiều parent commit; commit đầu tiên của repository thường không có parent.
- Thông tin author: người tạo ra thay đổi.
- Thông tin committer: người tạo commit object đó.
- Timestamp và múi giờ tương ứng.
- Commit message.
- Có thể có header bổ sung như chữ ký GPG/SSH hoặc encoding.

Có thể xem nội dung commit object:

```bash
git cat-file -p HEAD
```

Ví dụ cấu trúc:

```text
tree <root-tree-oid>
parent <parent-commit-oid>
author Nguyen Van A <a@example.com> 1700000000 +0700
committer Nguyen Van A <a@example.com> 1700000100 +0700

Add parser support
```

Các OID và timestamp trong ví dụ chỉ minh họa cấu trúc. Header parent có thể xuất hiện nhiều lần trong merge commit; commit gốc không có header parent.

**Author** là người được ghi nhận đã tạo ra thay đổi. **Committer** là người tạo commit object hiện tại. Hai thông tin có thể khác nhau, ví dụ khi một maintainer cherry-pick commit của tác giả khác.

Commit tham chiếu tới tree, vì vậy nó mô tả snapshot hoàn chỉnh tại thời điểm đó. Git xác định phần thay đổi giữa hai commit bằng cách so sánh các tree mà chúng tham chiếu, chứ không cần commit lưu sẵn một bản diff đầy đủ.

### Parent tạo thành lịch sử

Commit có một parent thường nằm trên lịch sử tuyến tính:

```text
A --- B --- C
            ^
           HEAD
```

Commit merge có từ hai parent trở lên:

```text
      B ---- C
     /        \
A --           M
     \        /
      D ---- E
```

Commit M tham chiếu tree kết quả merge và có cả hai parent. Quan hệ parent giúp Git duyệt lịch sử, tìm merge base, xác định ancestor và so sánh các nhánh.

Xem parent của commit:

```bash
git cat-file -p HEAD
git rev-list --parents -n 5 HEAD
git log --oneline --graph --decorate --all
```

git rev-list --parents hiển thị OID commit kèm các parent OID. git log --graph vẽ quan hệ lịch sử để bạn dễ thấy branch và merge.

## 6. Annotated tag: object dành cho một mốc có metadata

Git có hai cách tạo tag phổ biến:

- **Lightweight tag**: một ref đơn giản trỏ trực tiếp tới object, thường là commit. Nó không tạo tag object riêng.
- **Annotated tag**: tạo một object loại tag chứa tên tag, người tạo tag, thời điểm, thông điệp và object đích. Có thể ký số tag nếu cần.

Tạo lightweight tag:

```bash
git tag v1.0.0
```

Tạo annotated tag:

```bash
git tag -a v1.0.0 -m "Release 1.0.0"
```

Có thể chỉ rõ commit đích:

```bash
git tag -a v1.0.0 <commit-oid> -m "Release 1.0.0"
```

Một annotated tag object có cấu trúc khái quát:

```text
object <target-oid>
type commit
tag v1.0.0
tagger Nguyen Van A <a@example.com> 1700000200 +0700

Release 1.0.0
```

- **object** là OID của object được tag.
- **type** cho biết loại object đích, thường là commit.
- **tag** là tên nhãn.
- **tagger** là người tạo annotated tag và thời điểm tạo.
- Phần sau dòng trống là thông điệp tag.

Annotated tag thường phù hợp với release vì có thông điệp và thông tin tagger. Lightweight tag phù hợp với nhãn tạm hoặc mốc nội bộ đơn giản. Một tag object có thể trỏ tới loại object khác, thậm chí tới một tag object khác, dù trường hợp thông thường là trỏ tới commit.

Kiểm tra loại tag:

```bash
git cat-file -t v1.0.0
```

Nếu là annotated tag, kết quả là tag. Nếu là lightweight tag trỏ trực tiếp tới commit, kết quả thường là commit.

Xem nội dung annotated tag:

```bash
git cat-file -p v1.0.0
git show v1.0.0
```

Với annotated tag, cat-file -p hiển thị tag object; git show tiếp tục hiển thị đối tượng được tag cùng nội dung liên quan.

## 7. Object ID và content-addressable storage

Git tính OID từ loại object, kích thước nội dung và chính nội dung đó. Về khái niệm, dữ liệu trước khi băm có dạng:

```text
<type> <size>\0<content>
```

Ví dụ blob chứa sáu byte hello theo sau bởi newline có phần header khái quát:

```text
blob 6\0hello\n
```

Byte NUL trong biểu diễn trên là dấu kết thúc header; nó không phải ký tự nội dung. Git băm toàn bộ chuỗi object đã có header, không chỉ băm phần nội dung file.

Do OID phụ thuộc vào type, size và content:

- Cùng nội dung và cùng loại object tạo ra cùng OID trong cùng object format.
- Đổi nội dung một byte sẽ tạo OID khác.
- Cùng byte nhưng object type khác nhau cũng có OID khác.
- Tên file không ảnh hưởng OID blob; tên file được lưu trong tree.

Git truyền thống dùng SHA-1 với OID 40 ký tự hex. Các phiên bản Git hiện đại cũng hỗ trợ repository dùng SHA-256 với OID 64 ký tự hex. Thuật toán object format được chọn khi khởi tạo repository; không thể chỉ đổi một cấu hình thông thường để chuyển toàn bộ repository đang dùng SHA-1 sang SHA-256.

Kiểm tra object format:

```bash
git rev-parse --show-object-format
```

Khởi tạo một repository mới dùng SHA-256 (chỉ là ví dụ cho repository mới):

```bash
git init --object-format=sha256 new-project
```

Không phải mọi công cụ hoặc hệ thống lưu trữ Git cũ đều hỗ trợ SHA-256, vì vậy cần kiểm tra khả năng tương thích trước khi chọn object format cho dự án cần cộng tác rộng.

OID giúp Git nhận diện object theo nội dung. Nó không phải cơ chế mã hóa: nội dung không được giữ bí mật nhờ băm. OID cũng không tự chứng minh ai đã tạo object; chữ ký commit/tag và quy trình xác thực danh tính giải quyết mục tiêu tin cậy ở lớp khác.

## 8. Object database: loose objects và packfiles

Object được lưu trong object database của repository. Với loose object, Git thường nén nội dung object bằng zlib và lưu theo đường dẫn được tạo từ OID:

```text
.git/objects/ab/cdef...
```

Trong một repository có Git directory thông thường, hai ký tự đầu của OID tạo thành tên thư mục; phần còn lại là tên file. Tuy nhiên, bạn không nên mở rồi chỉnh sửa trực tiếp dữ liệu bên trong object database. Đây là dữ liệu nội bộ được Git quản lý.

Khi repository có nhiều object, Git có thể gom chúng vào packfile để tiết kiệm không gian và tăng hiệu quả truy xuất. Packfile có thể dùng delta compression: thay vì lưu lặp lại toàn bộ object, Git lưu phần khác biệt so với object khác khi phù hợp. File index đi kèm giúp Git tìm object trong pack.

Có thể xem thống kê object database:

```bash
git count-objects -v
```

Lệnh báo số loose object, dung lượng và thông tin pack liên quan. Đầu ra cụ thể tùy repository và tình trạng garbage collection.

Git có thể chạy garbage collection để đóng gói object và dọn object không còn được tham chiếu theo chính sách thời hạn:

```bash
git gc
```

Thông thường Git tự quản lý việc này; người dùng không cần chạy thường xuyên. Không xóa thủ công file trong .git/objects hoặc packfiles vì có thể làm hỏng lịch sử và object database.

## 9. Refs và HEAD không phải là object

Một điểm quan trọng là branch và tên tag thường không phải object. Chúng là **ref** (tham chiếu) chứa OID của object.

Ví dụ:

```text
refs/heads/main  ------> commit C
refs/tags/v1.0.0 ------> tag object T
                              |
                              +----> commit C

HEAD -----------------> refs/heads/main
```

- Branch main là ref trỏ tới commit hiện tại của branch.
- Annotated tag v1.0.0 là ref trỏ tới tag object; tag object lại trỏ tới commit.
- Lightweight tag v1.0.0 là ref trỏ thẳng tới commit.
- HEAD thường là symbolic ref trỏ tới branch hiện tại. Khi detached HEAD, nó trỏ trực tiếp tới OID commit.

Khi tạo commit mới trên branch, Git tạo commit object mới và cập nhật ref branch để trỏ tới OID mới. Object cũ không bị sửa tại chỗ; nó vẫn tồn tại nếu còn được tham chiếu hoặc chưa bị garbage collection dọn.

Xem các ref:

```bash
git show-ref
git show-ref --heads
git show-ref --tags
git symbolic-ref HEAD
git rev-parse HEAD
```

git symbolic-ref HEAD hiển thị branch mà HEAD đang theo dõi trong trạng thái bình thường. Nếu HEAD detached, lệnh này không phân giải được symbolic ref; dùng git rev-parse HEAD để lấy OID commit hiện tại.

## 10. Quan sát một commit từ đầu tới cuối

Có thể dùng chuỗi lệnh sau để lần theo các object của commit hiện tại:

**Bước 1: Xác định commit.**

```bash
git rev-parse HEAD
git cat-file -t HEAD
```

Loại object của HEAD phải là commit.

**Bước 2: Đọc commit object.**

```bash
git cat-file -p HEAD
```

Tìm dòng tree để lấy OID tree gốc và dòng parent để biết commit cha.

**Bước 3: Xem các mục trong tree.**

```bash
git ls-tree HEAD
git cat-file -p 'HEAD^{tree}'
```

Đọc mode, type, OID và tên của từng mục. Nếu mục là tree con, có thể tiếp tục dùng OID của tree đó với git ls-tree.

**Bước 4: Xem nội dung blob của một file.**

```bash
git cat-file -t HEAD:README.md
git cat-file -p HEAD:README.md
```

Git phân giải đường dẫn trong tree của commit thành blob rồi hiển thị nội dung.

**Bước 5: Xem tag nếu commit có tag.**

```bash
git tag --points-at HEAD
git cat-file -t v1.0.0
git cat-file -p v1.0.0
```

Lệnh cat-file -p cuối dành cho annotated tag. Nếu tag là lightweight, loại object sẽ là commit và lệnh sẽ hiển thị commit object thay vì tag metadata.

Chuỗi kiểm tra này cho thấy commit không chứa tất cả file trực tiếp. Nó nối tới tree, tree nối tới blob/tree con, còn tag có thể tạo thêm một lớp metadata trỏ tới commit.

## 11. Index và working tree liên hệ với object ra sao?

Working tree là các file mà bạn nhìn thấy và chỉnh sửa. Index (staging area) là trạng thái chuẩn bị cho commit tiếp theo. Object database lưu các object đã được ghi nhận.

Khi chạy:

```bash
git add README.md
```

Git đọc nội dung file, áp dụng clean filter/attributes nếu có, tạo hoặc tái sử dụng blob tương ứng và cập nhật index để mục README.md trỏ tới blob đó. Index cũng giữ thông tin mode và đường dẫn.

Khi tạo commit, Git ghi tree object từ trạng thái index rồi tạo commit object tham chiếu tới tree đó. Vì vậy, nội dung đã stage là cơ sở cho snapshot mới, không nhất thiết là toàn bộ nội dung đang có trong working tree nếu file tiếp tục được sửa sau khi stage.

Có thể yêu cầu Git tạo tree object từ index bằng lệnh plumbing:

```bash
git write-tree
```

Lệnh trả về OID của tree được tạo từ index hiện tại. Nó không tự tạo commit hoặc di chuyển branch. Nếu tree object chưa được ref nào tham chiếu, nó có thể là object unreachable cho tới khi được dùng trong commit hoặc object khác.

Điều này giải thích ba vùng thường được nhắc đến:

| Vùng | Vai trò |
|---|---|
| Working tree | Nội dung file đang làm việc |
| Index | Snapshot chuẩn bị cho commit kế tiếp |
| Object database | Blob, tree, commit, tag và các object Git lưu trữ |

## 12. Những nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu đúng |
|---|---|
| Blob lưu cả tên file và nội dung | Blob chỉ lưu byte nội dung; tên và đường dẫn nằm trong tree |
| Commit là một diff | Commit trỏ tới snapshot tree và parent; diff được tính khi so sánh các snapshot |
| Tree là thư mục vật lý trong .git | Tree là object mô tả các mục trong một thư mục |
| Tên branch là commit object | Branch là ref trỏ tới commit và có thể di chuyển |
| Lightweight tag và annotated tag giống nhau | Lightweight tag là ref trực tiếp; annotated tag có object tag riêng |
| Mỗi file có một blob riêng dù nội dung giống nhau | Nội dung giống nhau có thể dùng chung blob object |
| Git lưu mọi metadata filesystem | Git theo dõi một số mode cần thiết, không lưu đầy đủ owner, mtime hay mọi quyền filesystem |
| OID là mã hóa nội dung | OID là digest nhận diện nội dung, không bảo mật hay xác thực người tạo |
| Có thể chỉnh file trong .git/objects | Object database là dữ liệu nội bộ; dùng plumbing command để kiểm tra/thao tác |

## Kết luận

Git xây dựng lịch sử từ các object có liên kết bằng OID. Blob lưu nội dung file, tree lưu cấu trúc thư mục và mode, commit lưu snapshot cùng parent/metadata, còn annotated tag lưu thông tin về một mốc được gắn nhãn. Branch và tag name là refs trỏ tới object; chúng không thay thế object và có thể có cách trỏ khác nhau tùy loại tag. Dùng git cat-file, git ls-tree, git rev-parse, git hash-object và git count-objects để quan sát mô hình này mà không cần sửa trực tiếp dữ liệu nội bộ của repository.
