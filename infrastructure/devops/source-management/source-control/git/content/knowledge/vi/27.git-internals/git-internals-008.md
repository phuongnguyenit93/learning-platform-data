# Đọc đối tượng bằng `git cat-file` và `git ls-tree`

Git lưu lịch sử dưới dạng các object liên kết với nhau. Commit trỏ tới tree, tree liệt kê tên và mode của các mục trong thư mục, còn blob chứa byte nội dung của file. Annotated tag tạo thêm một object mô tả mốc được gắn nhãn. Hai lệnh `git cat-file` và `git ls-tree` cho phép đọc cấu trúc này trực tiếp mà không cần checkout một phiên bản ra working tree. Khi biết cách dùng chúng, bạn có thể kiểm tra chính xác commit chứa gì, một đường dẫn đã từng có nội dung nào và một tag đang trỏ tới loại object nào.

## 1. Mô hình object mà hai lệnh giúp quan sát

Git có bốn loại object cơ bản:

| Loại object | Nội dung chính | Vai trò |
|---|---|---|
| Blob | Byte nội dung của file | Lưu nội dung file, không lưu tên hoặc đường dẫn |
| Tree | Các mục con gồm mode, tên và object ID | Mô tả một thư mục trong snapshot |
| Commit | Tree ID, parent ID, author, committer, thời gian và message | Ghi nhận một snapshot cùng quan hệ lịch sử |
| Tag | Object đích, loại đích, tên tag, tagger, thời gian và message | Ghi metadata cho một mốc, thường là release |

Một commit không chứa toàn bộ nội dung file bên trong nó. Commit trỏ tới một tree gốc; tree có thể trỏ tới tree con và blob. Vì vậy, cấu trúc snapshot có thể hình dung như sau:

```text
commit
  |
  v
root tree
  |--------------------|
  v                    v
tree: src/          blob: README.md
  |
  |--------------------|
  v                    v
blob: App.java      tree: config/
                       |
                       v
                    blob: app.yml
```

`git ls-tree` giúp xem các mục mà một tree tham chiếu. `git cat-file` giúp xác định loại, kích thước và nội dung của từng object.

## 2. Xác định object cần đọc

Các lệnh object thường nhận một object name. Bạn có thể truyền:

- Object ID đầy đủ hoặc tiền tố đủ duy nhất.
- Tên ref như `HEAD`, `main`, `v1.2.0`.
- Biểu thức commit như `HEAD~2`, `main^{tree}` hoặc `v1.2.0^{}`.
- Biểu thức đường dẫn trong một tree-ish như `HEAD:README.md`.

Ví dụ:

```bash
git rev-parse HEAD
git rev-parse 'HEAD^{tree}'
git rev-parse 'HEAD:README.md'
```

`git rev-parse` phân giải các biểu thức thành object ID. Với `HEAD^{tree}`, Git lấy tree gốc của commit `HEAD`. Với `HEAD:README.md`, Git tìm object được tham chiếu bởi đường dẫn `README.md` trong tree của `HEAD`.

Object ID thường được hiển thị bằng SHA-1 (40 ký tự hex) trong nhiều repository, nhưng Git cũng hỗ trợ repository dùng SHA-256 (64 ký tự hex). Không nên viết script giả định mọi object ID luôn có độ dài 40 ký tự.

## 3. Dùng `git cat-file -t` để xem loại object

Tùy chọn `-t` in loại object mà tên được chỉ định phân giải tới:

```bash
git cat-file -t HEAD
git cat-file -t 'HEAD^{tree}'
git cat-file -t 'HEAD:README.md'
```

Kết quả thường lần lượt là:

```text
commit
tree
blob
```

Điều này giúp kiểm tra một biểu thức đang trỏ tới commit, tree hay blob trước khi đọc nội dung. Với annotated tag, `git cat-file -t v1.2.0` thường trả về `tag` vì ref trỏ tới tag object. Với lightweight tag, kết quả thường là `commit` vì ref trỏ trực tiếp tới commit.

Có thể kiểm tra một object có tồn tại mà không in nội dung:

```bash
git cat-file -e 'HEAD:README.md'
```

Lệnh không in kết quả nếu object tồn tại và trả mã thoát khác `0` nếu không phân giải được object. Điều này hữu ích trong script kiểm tra trước khi đọc.

## 4. Dùng `git cat-file -s` để xem kích thước object

Tùy chọn `-s` in kích thước payload của object tính bằng byte:

```bash
git cat-file -s 'HEAD:README.md'
git cat-file -s HEAD
```

Với blob, kích thước là số byte nội dung file. Với commit, tree hoặc tag, kích thước là số byte dữ liệu được lưu trong object tương ứng.

Đây là kích thước nội dung object, không phải dung lượng object chiếm trong packfile trên ổ đĩa. Git có thể nén object hoặc lưu delta trong packfile, nên hai con số này không nhất thiết bằng nhau.

Để xem kích thước blob trong danh sách tree, có thể dùng `git ls-tree -l` như phần sau.

## 5. Dùng `git cat-file -p` để đọc nội dung object

Tùy chọn `-p` yêu cầu Git hiển thị nội dung object theo cách dễ đọc:

```bash
git cat-file -p HEAD
```

Với commit, kết quả thường có dạng:

```text
tree 6f3a...
parent 8c21...
author Linh Nguyen <linh@example.invalid> 1760000000 +0700
committer Linh Nguyen <linh@example.invalid> 1760000100 +0700

Add report endpoint
```

- `tree` là object ID của snapshot gốc mà commit ghi nhận.
- Mỗi dòng `parent` là một commit cha; merge commit thường có từ hai parent trở lên.
- `author` ghi người tạo thay đổi và thời điểm tác giả.
- `committer` ghi người tạo commit object và thời điểm tạo commit.
- Sau dòng trống là commit message.

Commit có thể có thêm header như `encoding`, `gpgsig` hoặc metadata khác. Không nên giả định mọi commit chỉ có đúng các dòng trong ví dụ.

Đọc blob của một file:

```bash
git cat-file -p 'HEAD:README.md'
```

Với blob văn bản, Git in nội dung file. Với blob nhị phân, terminal có thể hiển thị ký tự khó đọc hoặc dữ liệu điều khiển. Không nên in file nhị phân trực tiếp ra terminal; có thể ghi object ra file để một công cụ phù hợp đọc:

```bash
git cat-file blob 'HEAD:assets/logo.png' > logo-from-commit.png
```

Lệnh này ghi byte blob ra file đích. Hãy chọn tên file đầu ra không ghi đè dữ liệu đang có.

## 6. Đọc tree object bằng `git cat-file -p`

Lấy tree gốc từ commit rồi hiển thị:

```bash
git cat-file -p 'HEAD^{tree}'
```

Một tree được hiển thị dưới dạng các dòng gồm mode, loại object, object ID và tên mục. Ví dụ:

```text
100644 blob 2f8a...    README.md
040000 tree 9b31...    src
100755 blob 6c20...    scripts/build.sh
```

Tree chỉ lưu danh sách mục con trực tiếp. Dòng `src` trỏ tới một tree khác; để xem nội dung bên trong, bạn phải đọc tree con đó hoặc dùng `git ls-tree -r` để duyệt đệ quy.

`git cat-file -p` hữu ích để quan sát nội dung object, còn `git ls-tree` thuận tiện hơn khi cần lọc, liệt kê hoặc xử lý các mục trong tree.

## 7. Đọc annotated tag object

Annotated tag tạo một object riêng chứa thông tin về mốc được gắn nhãn. Xem loại và nội dung:

```bash
git cat-file -t v1.2.0
git cat-file -p v1.2.0
```

Ví dụ kết quả:

```text
object 7ab3...
type commit
tag v1.2.0
tagger Linh Nguyen <linh@example.invalid> 1760000200 +0700

Release version 1.2.0
```

- `object` là object ID được tag trỏ tới.
- `type` cho biết loại object đích, thường là `commit`.
- `tag` là tên tag.
- `tagger` và phần message mô tả người tạo tag và mục đích của mốc.

Để bóc annotated tag về object đích cuối cùng, dùng biểu thức `^{}`:

```bash
git cat-file -t 'v1.2.0^{}'
git cat-file -p 'v1.2.0^{}'
```

Nếu tag trỏ tới commit, lệnh thứ nhất trả về `commit` và lệnh thứ hai hiển thị commit object. Với lightweight tag, ref thường đã trỏ thẳng tới commit nên `^{}` không cần bóc qua tag object riêng.

## 8. Dùng `git ls-tree` để xem nội dung tree

Lệnh cơ bản:

```bash
git ls-tree HEAD
```

Lệnh liệt kê các mục trực tiếp ở root tree của commit `HEAD`. Kết quả thường có dạng:

```text
100644 blob 2f8a...    README.md
040000 tree 9b31...    src
100644 blob 7c12...    pom.xml
```

Mỗi dòng có các thành phần:

1. **Mode:** quyền hoặc loại mục trong tree.
2. **Object type:** `blob`, `tree` hoặc `commit`.
3. **Object ID:** object mà mục đó tham chiếu.
4. **Path:** tên đường dẫn tương đối với tree đang liệt kê.

`git ls-tree` đọc snapshot đã được lưu trong object database. Nó không liệt kê file untracked và không phản ánh chỉnh sửa chưa commit trong working tree.

## 9. Hiểu mode của các mục trong tree

Mode giúp Git phân biệt file thường, file thực thi, symbolic link, thư mục và gitlink:

| Mode | Object type | Ý nghĩa |
|---|---|---|
| `100644` | `blob` | File thường không có bit executable |
| `100755` | `blob` | File thường có bit executable |
| `120000` | `blob` | Symbolic link; blob chứa đường dẫn đích của link |
| `040000` | `tree` | Thư mục con |
| `160000` | `commit` | Gitlink trỏ tới commit của submodule |

Với symbolic link, blob không chứa nội dung file đích; nó chứa chuỗi đường dẫn mà link trỏ tới. Với gitlink, superproject ghi nhận commit của repository con chứ không lưu các file bên trong submodule như blob thông thường.

Nếu thấy mode `160000`, hãy nhận diện đây là submodule. Commit được tham chiếu thuộc repository con; object đó có thể không có trong object database của superproject, vì vậy `git cat-file` chạy ở superproject có thể không đọc được commit này nếu object chưa tồn tại ở đó.

## 10. Duyệt tree đệ quy bằng `-r`

Mặc định, `git ls-tree` chỉ hiển thị các mục trực tiếp của tree được chỉ định. Dùng `-r` để đi vào các thư mục con:

```bash
git ls-tree -r HEAD
```

Kết quả liệt kê các file ở mọi cấp với đường dẫn tương đối từ tree gốc. Nếu muốn hiển thị cả các tree trung gian trong khi duyệt đệ quy, kết hợp `-t`:

```bash
git ls-tree -r -t HEAD
```

Một số tùy chọn hữu ích:

| Tùy chọn | Tác dụng |
|---|---|
| `-r` | Duyệt các tree con đệ quy |
| `-t` | Hiển thị cả tree entry, kể cả khi dùng `-r` |
| `-d` | Chỉ hiển thị các tree entry |
| `-l` | Hiển thị thêm kích thước object, hữu ích với blob |
| `--name-only` | Chỉ in đường dẫn |
| `--object-only` | Chỉ in object ID |
| `--full-tree` | Liệt kê từ gốc tree, không giới hạn theo thư mục làm việc hiện tại |
| `-z` | Kết thúc trường bằng NUL, phù hợp xử lý tên file có ký tự đặc biệt trong script |

Ví dụ chỉ lấy tên file:

```bash
git ls-tree -r --name-only HEAD
```

Ví dụ xem kích thước blob:

```bash
git ls-tree -r -l HEAD
```

Kích thước hiển thị là kích thước nội dung object, không phải số byte mà object chiếm trong packfile.

## 11. Xem một thư mục hoặc đường dẫn cụ thể

Bạn có thể chỉ định đường dẫn để giới hạn kết quả:

```bash
git ls-tree HEAD src
git ls-tree -r HEAD -- src/
```

Lệnh đầu hiển thị mục `src` trong tree; lệnh thứ hai duyệt các mục bên trong `src/`. Để đọc tree của thư mục đó bằng `cat-file`, có thể dùng biểu thức đường dẫn:

```bash
git cat-file -t 'HEAD:src'
git cat-file -p 'HEAD:src'
```

`HEAD:src` phân giải tới tree object của thư mục `src` trong commit `HEAD`. Nếu đường dẫn là file, biểu thức tương ứng phân giải tới blob.

Nếu đang đứng trong thư mục con của working tree và muốn liệt kê từ root của repository, dùng `--full-tree`:

```bash
git ls-tree --full-tree -r HEAD
```

Đường dẫn được chỉ định cần tương ứng với snapshot trong tree, không phải một đường dẫn tùy ý bên ngoài repository.

## 12. So sánh tree giữa hai commit

`git ls-tree` có thể đọc tree của bất kỳ commit nào còn truy cập được trong repository. Điều này giúp kiểm tra file tồn tại ở một phiên bản cũ hay không và object ID đã thay đổi thế nào.

Ví dụ:

```bash
git ls-tree HEAD~1
git ls-tree HEAD
```

Nếu muốn so sánh hai snapshot ở mức thay đổi đường dẫn, `git diff-tree` thường phù hợp hơn:

```bash
git diff-tree --no-commit-id --name-status -r HEAD~1 HEAD
```

Sau đó có thể lấy object ID của một đường dẫn ở từng commit bằng:

```bash
git rev-parse 'HEAD~1:src/App.java'
git rev-parse 'HEAD:src/App.java'
```

Nếu hai object ID giống nhau, nội dung blob được tham chiếu giống nhau. Nếu khác nhau, cần đọc từng phiên bản:

```bash
git cat-file -p 'HEAD~1:src/App.java'
git cat-file -p 'HEAD:src/App.java'
```

Đối với file nhị phân, hãy tránh in trực tiếp nội dung ra terminal; dùng `git cat-file blob` để ghi ra file tạm hoặc dùng công cụ phù hợp để so sánh.

## 13. Dùng `git cat-file --batch` khi cần đọc nhiều object

Khi cần kiểm tra nhiều object trong script hoặc phân tích repository, chế độ batch tránh phải khởi chạy một tiến trình Git riêng cho từng object.

Để lấy metadata của nhiều object:

```bash
printf '%s\n' HEAD 'HEAD^{tree}' 'HEAD:README.md' |
  git cat-file --batch-check='%(objectname) %(objecttype) %(objectsize)'
```

Đầu ra có object ID, loại và kích thước cho từng object được yêu cầu. Các placeholder thường dùng trong format gồm:

- `%(objectname)`: object ID.
- `%(objecttype)`: loại object.
- `%(objectsize)`: kích thước nội dung object.
- `%(rest)`: phần còn lại của dòng đầu vào trong những workflow batch phù hợp.

Để đọc nội dung nhiều object, dùng:

```bash
printf '%s\n' HEAD 'HEAD^{tree}' 'HEAD:README.md' | git cat-file --batch
```

`--batch` in header mô tả object rồi nội dung object theo kích thước được báo. Với blob nhị phân, đầu ra có thể chứa byte không phải văn bản. Script xử lý batch cần đọc đúng kích thước byte trong header thay vì tách nội dung bằng dòng mới hoặc giả định mọi object là text.

`--batch-check` chỉ trả metadata nên thường an toàn và tiện hơn khi thống kê. Có thể dùng `--batch-all-objects` cùng chế độ batch thích hợp để duyệt mọi object trong object database, kể cả object không còn được ref thông thường trỏ tới; cần cân nhắc lượng dữ liệu và thời gian trên repository lớn.

Ví dụ trên dùng cú pháp shell có `printf`; trong PowerShell, có thể truyền danh sách qua pipeline bằng cách tạo các dòng văn bản rồi đưa vào `git cat-file --batch-check`.

## 14. Phân biệt tree object, index và working tree

`git ls-tree` chỉ đọc tree được lưu trong commit hoặc tree object. Nó không phải công cụ xem staging area hay file trên ổ đĩa hiện tại.

| Nơi dữ liệu | Lệnh phù hợp | Nội dung phản ánh |
|---|---|---|
| Commit/tree đã lưu | `git ls-tree <tree-ish>` | Snapshot của commit hoặc tree object |
| Index (staging area) | `git ls-files --stage` | Các entry đã stage, gồm mode, object ID và stage number |
| Working tree | `git status`, `git diff` và công cụ hệ thống | File hiện có trên ổ đĩa và thay đổi chưa stage |

Ví dụ một file đã sửa nhưng chưa commit:

```bash
git ls-tree HEAD -- src/App.java
git ls-files --stage -- src/App.java
git diff -- src/App.java
```

Ba lệnh có thể cho kết quả khác nhau vì chúng đang xem ba trạng thái khác nhau. Nếu `git ls-tree` vẫn hiển thị blob cũ trong khi `git diff` cho thấy nội dung mới, điều đó bình thường: commit chưa thay đổi.

## 15. Ví dụ thực hành: lần từ commit tới nội dung file

Giả sử bạn muốn biết commit `HEAD` lưu phiên bản nào của `src/main/App.java`.

1. Xem commit object:

   ```bash
   git cat-file -p HEAD
   ```

2. Lấy tree ID mà commit tham chiếu:

   ```bash
   git rev-parse 'HEAD^{tree}'
   ```

3. Liệt kê các mục ở root tree:

   ```bash
   git ls-tree HEAD
   ```

4. Liệt kê các file dưới `src/main`:

   ```bash
   git ls-tree -r HEAD -- src/main/
   ```

5. Xác định object type và kích thước của file:

   ```bash
   git cat-file -t 'HEAD:src/main/App.java'
   git cat-file -s 'HEAD:src/main/App.java'
   ```

6. Đọc nội dung blob:

   ```bash
   git cat-file -p 'HEAD:src/main/App.java'
   ```

Quy trình này đi từ commit tới tree, từ tree tới đường dẫn và cuối cùng tới blob. Bạn có thể thực hiện tương tự với commit cũ, tag hoặc branch khác mà không cần checkout chúng.

## 16. Những lỗi thường gặp

- **Dùng `cat-file -p HEAD` rồi nghĩ đó là nội dung file.** `HEAD` thường là commit object; dùng `HEAD:path` để lấy blob hoặc `HEAD^{tree}` để lấy tree.
- **Nhầm annotated tag với lightweight tag.** `cat-file -t` có thể trả `tag` hoặc `commit`; dùng `^{}` để bóc tag tới đối tượng đích.
- **Cho rằng blob chứa tên file.** Blob chỉ chứa byte nội dung; tên và mode nằm trong tree.
- **Cho rằng `ls-tree` hiển thị file đang sửa.** Lệnh đọc snapshot trong object database, không đọc working tree hoặc index.
- **Chỉ dùng `ls-tree` mặc định rồi kết luận repository không có file con.** Mặc định chỉ hiển thị entry trực tiếp; dùng `-r` để duyệt đệ quy.
- **Nhầm kích thước object với dung lượng packfile.** `cat-file -s` và `ls-tree -l` báo kích thước payload, không phải kích thước lưu trữ sau nén.
- **In blob nhị phân trực tiếp ra terminal.** Ghi ra file hoặc dùng công cụ đọc định dạng phù hợp.
- **Coi gitlink là blob của submodule.** Mode `160000` là commit được tham chiếu bởi superproject; nội dung repository con nằm trong repository riêng.
- **Giả định object ID luôn có 40 ký tự.** Repository có thể dùng SHA-256; hãy xử lý độ dài theo hash algorithm.

## 17. Ghi nhớ

`git cat-file` đọc loại, kích thước và nội dung của object; `git ls-tree` cho biết một tree ánh xạ tên đường dẫn, mode và object ID như thế nào. Bắt đầu từ commit, lấy root tree bằng `^{tree}`, duyệt đường dẫn bằng `ls-tree` rồi đọc blob bằng `cat-file`. Hãy nhớ blob không chứa tên file, tree chỉ liệt kê mục con trực tiếp nếu không dùng `-r`, và các lệnh này đọc snapshot đã lưu chứ không phản ánh index hoặc working tree chưa commit.
