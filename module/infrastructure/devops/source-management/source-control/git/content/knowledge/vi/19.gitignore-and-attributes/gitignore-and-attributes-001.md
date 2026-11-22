# Phân biệt .gitignore với .gitattributes

Trong một repository Git, có những tệp bạn không muốn đưa vào lịch sử, chẳng hạn thư mục build, log, tệp cấu hình riêng hoặc dữ liệu sinh ra khi chạy chương trình. Cũng có những tệp cần được Git xử lý theo quy tắc thống nhất giữa các máy, chẳng hạn chuẩn hóa dấu xuống dòng, xác định tệp nhị phân, chọn cách diff hoặc merge. Git cung cấp hai cơ chế riêng cho hai nhóm nhu cầu đó: **`.gitignore` quyết định đường dẫn nào cần được bỏ qua khi tìm tệp chưa được theo dõi; `.gitattributes` quy định thuộc tính và cách Git xử lý nội dung của đường dẫn**.

Hai tệp có thể cùng xuất hiện trong một dự án, nhưng chúng giải quyết hai vấn đề khác nhau. `.gitignore` không thay đổi cách Git xử lý nội dung của một tệp đã được theo dõi. `.gitattributes` cũng không làm cho một tệp biến mất khỏi `git status` hay ngăn Git thêm tệp vào index.

## 1. Mục đích của từng tệp

| Tiêu chí | `.gitignore` | `.gitattributes` |
|---|---|---|
| Mục đích | Bỏ qua các đường dẫn chưa được theo dõi phù hợp với mẫu | Gán thuộc tính cho đường dẫn để Git xử lý nhất quán |
| Câu hỏi cần trả lời | Tệp hoặc thư mục nào không nên được đề xuất để thêm vào repository? | Git nên chuẩn hóa, diff, merge hoặc xuất tệp này như thế nào? |
| Tác động chính | Ảnh hưởng đến việc phát hiện và thêm tệp chưa được theo dõi | Ảnh hưởng đến cách Git diễn giải và xử lý nội dung của đường dẫn |
| Có áp dụng với tệp đã tracked không? | Quy tắc ignore không ngừng theo dõi tệp đã được quản lý | Có. Thuộc tính có thể áp dụng cho cả tệp đã tracked và chưa tracked |
| Thường được chia sẻ thế nào? | Commit `.gitignore` để cả nhóm dùng chung quy tắc bỏ qua | Commit `.gitattributes` để cả nhóm dùng chung quy tắc xử lý tệp |
| Ví dụ | `build/`, `*.log`, `.env` | `*.sh text eol=lf`, `*.png binary` |

Có thể nhớ ngắn gọn: `.gitignore` chọn đường dẫn nào không cần đưa vào lịch sử; `.gitattributes` mô tả Git cần làm gì với đường dẫn đó khi xử lý nội dung.

## 2. `.gitignore` hoạt động như thế nào?

Git dùng các mẫu trong `.gitignore` để nhận diện tệp chưa được theo dõi mà bạn không muốn Git đề xuất thêm vào index. Ví dụ một dự án Java có thể sinh ra `target/`, tệp `.class`, log và cấu hình môi trường riêng. Có thể đặt các quy tắc sau trong `.gitignore` ở thư mục gốc:

```gitignore
# Thư mục sinh ra khi build
/target/
/build/

# Tệp log và bytecode
*.log
*.class

# Cấu hình môi trường riêng
.env
!.env.example

# Cấu hình IDE cá nhân
.idea/
```

Khi các đường dẫn phù hợp chưa được theo dõi, Git sẽ không liệt kê chúng như các tệp untracked thông thường trong `git status` và sẽ bỏ qua chúng khi quét để thêm tệp. Quy tắc này giúp tránh đưa sản phẩm build, log, bí mật hoặc thiết lập riêng của máy vào commit.

### Ignore không bỏ theo dõi tệp đã được commit

Một nhầm lẫn phổ biến là thêm một tệp vào `.gitignore` sẽ khiến Git ngừng theo dõi tệp đó. Điều này không đúng. Nếu `config/local.json` đã được commit, thêm mẫu `config/local.json` vào `.gitignore` không xóa tệp khỏi index và Git vẫn tiếp tục nhận biết các thay đổi của nó.

Để ngừng theo dõi tệp nhưng giữ bản sao trên máy, dùng:

```bash
# Thêm đường dẫn vào .gitignore trước
git rm --cached config/local.json

# Kiểm tra thay đổi trong index
git status
git diff --cached

# Ghi nhận việc bỏ tệp khỏi repository
git commit -m "Stop tracking local configuration"
```

`git rm --cached` gỡ đường dẫn khỏi index nhưng giữ tệp trong working tree. Sau khi commit, repository không còn quản lý tệp đó; mỗi máy cần có cách cung cấp cấu hình riêng phù hợp. Hãy bảo đảm tệp đã được sao lưu hoặc giá trị cần thiết đã được chuyển sang một cơ chế cấu hình an toàn trước khi bỏ theo dõi.

Nếu thật sự muốn thêm một tệp đang bị ignore, có thể dùng `git add -f <path>`. Đây là thao tác chủ động vượt qua quy tắc ignore; chỉ làm khi đã xác nhận tệp phù hợp để đưa vào lịch sử.

## 3. Cú pháp và phạm vi mẫu trong `.gitignore`

Mỗi dòng thường là một mẫu. Dòng trống bị bỏ qua; dòng bắt đầu bằng `#` là chú thích. Dấu `!` ở đầu mẫu dùng để loại trừ một đường dẫn khỏi quy tắc ignore trước đó, nếu các quy tắc thư mục cha cho phép Git đi vào đường dẫn đó.

| Mẫu | Ý nghĩa |
|---|---|
| `*.log` | Bỏ qua các tệp có đuôi `.log` ở mọi cấp thư mục bên dưới vị trí của file ignore |
| `/build/` | Bỏ qua thư mục `build` ngay tại vị trí của `.gitignore` này |
| `build/` | Bỏ qua thư mục tên `build` ở các cấp bên dưới vị trí của file ignore |
| `doc/*.pdf` | Bỏ qua các tệp PDF trực tiếp trong thư mục `doc` tương ứng |
| `**/target/` | Bỏ qua thư mục `target` ở bất kỳ cấp nào bên dưới vị trí của file ignore |
| `*.tmp` | Bỏ qua các tệp tạm có đuôi `.tmp` |
| `!important.log` | Ngoại lệ cho mẫu trước đó đối với `important.log`, nếu thư mục cha không bị loại khỏi quá trình duyệt |

Một dấu `/` ở đầu mẫu neo mẫu vào thư mục chứa `.gitignore`. Dấu `/` ở giữa mẫu làm cho đường dẫn được xét tương đối với vị trí file ignore. Mẫu không có dấu `/` (ngoài dấu `/` cuối chỉ thư mục) có thể khớp ở nhiều cấp bên dưới. Dấu `/` cuối chỉ áp dụng cho thư mục.

### Thứ tự và phạm vi áp dụng

Git có thể đọc nhiều nguồn ignore:

- Các file `.gitignore` trong thư mục chứa tệp và các thư mục cha. File `.gitignore` gần đường dẫn hơn có thể ghi đè quy tắc từ thư mục cha.
- `$GIT_DIR/info/exclude`, dành cho quy tắc riêng của repository local và không được commit.
- File ignore toàn cục do `core.excludesFile` chỉ định, thường dùng cho tệp do IDE hoặc hệ điều hành sinh ra trên máy cá nhân.

Trong cùng một mức ưu tiên, quy tắc khớp sau cùng thường quyết định trạng thái ignore. Quy tắc ở nguồn có ưu tiên cao hơn có thể ghi đè nguồn thấp hơn. Hãy dùng `git check-ignore -v` để xem chính xác file và dòng đã tạo ra kết quả.

Ví dụ, nhóm có thể commit các quy tắc chung trong `.gitignore` ở gốc, còn mỗi lập trình viên thêm các quy tắc cá nhân vào `.git/info/exclude` hoặc file ignore toàn cục:

```bash
# Xem cấu hình ignore toàn cục hiện tại
git config --get core.excludesFile

# Đặt file ignore toàn cục cho người dùng hiện tại
git config --global core.excludesFile ~/.config/git/ignore
```

Không đưa quy tắc chỉ phục vụ máy cá nhân vào `.gitignore` chung nếu nó không phù hợp với cả nhóm. Ngược lại, các thư mục build hoặc tệp sinh ra bởi dự án nên được khai báo trong `.gitignore` được commit để mọi người có cùng hành vi.

### Ngoại lệ trong thư mục đã bị ignore

Nếu bỏ qua cả thư mục bằng `cache/`, Git không duyệt vào thư mục đó để tìm một tệp con được mở ngoại lệ. Muốn giữ lại một tệp con, hãy bỏ qua các mục bên trong rồi mở ngoại lệ cụ thể:

```gitignore
cache/*
!cache/keep.txt
```

Khi cần mở ngoại lệ sâu hơn nhiều cấp, các thư mục cha trên đường dẫn cũng phải được phép đi vào. Chẳng hạn, nếu `cache/generated/` vẫn bị ignore như một thư mục, chỉ thêm `!cache/generated/keep.txt` có thể không đủ. Hãy thiết kế các mẫu sao cho Git có thể duyệt đến tệp cần giữ.

## 4. `.gitattributes` hoạt động như thế nào?

`.gitattributes` gán thuộc tính cho đường dẫn. Thuộc tính cho Git biết cách chuẩn hóa nội dung, cách hiển thị diff, cách hợp nhất hoặc cách xử lý dữ liệu khi xuất archive. Một dòng có dạng tổng quát:

```gitattributes
<pattern> <attribute> <attribute>...
```

Ví dụ:

```gitattributes
# Tự nhận diện tệp văn bản và chuẩn hóa nội dung
* text=auto

# Quy định kiểu xuống dòng trong working tree
*.sh text eol=lf
*.bat text eol=crlf

# Xác định các định dạng nhị phân
*.png binary
*.jpg binary
*.pdf binary
```

Trong ví dụ này, Git tự nhận diện phần lớn tệp văn bản để chuẩn hóa; các script shell dùng LF, tệp batch dùng CRLF, còn ảnh và PDF được xem là nhị phân. Quy tắc thuộc tính có thể tác động đến các tệp đã tracked, kể cả những tệp không bị ignore.

### Bốn trạng thái của một thuộc tính

Một thuộc tính có thể ở một trong các trạng thái sau:

| Cách viết | Trạng thái | Ý nghĩa |
|---|---|---|
| `text` | Set | Bật thuộc tính, tương đương giá trị boolean true |
| `-text` | Unset | Tắt thuộc tính, tương đương giá trị boolean false |
| `text=auto` | Set value | Gán giá trị chuỗi `auto` cho thuộc tính |
| `!text` | Unspecified | Hủy trạng thái đã gán trước đó để thuộc tính trở về chưa xác định |

Không có dòng nào gán thuộc tính cũng có nghĩa là thuộc tính đang unspecified. Trạng thái unset và unspecified khác nhau: unset là một quyết định rõ ràng tắt thuộc tính; unspecified cho phép Git hoặc nguồn cấu hình có ưu tiên thấp hơn quyết định theo mặc định của chúng.

Trong cùng một file `.gitattributes`, nếu nhiều dòng khớp cùng một đường dẫn và cùng thuộc tính, dòng khớp sau cùng có hiệu lực cho thuộc tính đó. Những thuộc tính khác nhau có thể được lấy từ các dòng khác nhau.

### Phạm vi và thứ tự ưu tiên của attributes

Git có thể lấy thuộc tính từ nhiều nơi:

1. `$GIT_DIR/info/attributes` có ưu tiên cao nhất và chỉ áp dụng cho repository local.
2. Các file `.gitattributes` trong thư mục chứa đường dẫn và các thư mục cha. File ở thư mục gần đường dẫn hơn có ưu tiên cao hơn file ở thư mục cha.
3. File attributes toàn cục được cấu hình qua `core.attributesFile`.

Trong cùng một file, dòng khớp sau cùng quyết định giá trị của thuộc tính tương ứng. `.gitattributes` được commit trong repository là nơi phù hợp để nhóm thống nhất quy tắc xử lý tệp. `info/attributes` và file toàn cục phù hợp cho điều chỉnh riêng của máy hoặc repository local.

Khác với `.gitignore`, cú pháp attributes không cho phép mẫu phủ định bắt đầu bằng `!` để loại trừ đường dẫn khỏi quy tắc trước đó. Muốn thay đổi thuộc tính, hãy gán trạng thái mới cho thuộc tính cần điều chỉnh, chẳng hạn `-text` hoặc `!text` trong dòng phù hợp.

## 5. Ví dụ quan trọng: chuẩn hóa dấu xuống dòng

Windows thường dùng CRLF (`\r\n`) trong working tree, còn Linux và macOS thường dùng LF (`\n`). Nếu mỗi người commit theo thiết lập riêng, diff có thể hiển thị cả tệp bị thay đổi chỉ vì dấu xuống dòng. `.gitattributes` giúp repository thống nhất cách lưu nội dung văn bản.

Ví dụ cấu hình ở gốc:

```gitattributes
# Git tự nhận diện tệp văn bản để chuẩn hóa khi đưa vào repository
* text=auto

# Các loại tệp cần LF trong working tree
*.sh text eol=lf
*.py text eol=lf

# Tệp batch cần CRLF trong working tree
*.bat text eol=crlf

# Tệp nhị phân không thực hiện chuyển đổi xuống dòng
*.png binary
*.jpg binary
*.pdf binary
```

Với `text=auto`, Git tự nhận diện nội dung văn bản và chuẩn hóa dấu xuống dòng trong repository theo quy tắc text normalization. Thuộc tính `eol` chỉ định kiểu xuống dòng khi checkout ra working tree. Ví dụ `text eol=lf` lưu nội dung chuẩn hóa và tạo working tree dùng LF; `text eol=crlf` vẫn chuẩn hóa nội dung trong repository nhưng checkout ra CRLF.

`binary` là macro thuộc tính có sẵn, tương đương cấu hình tệp không phải văn bản cho các thao tác liên quan: tắt text normalization, diff dạng văn bản và merge thông thường. Với tệp nhị phân, Git không nên cố gắng ghép các dòng như mã nguồn.

Nếu repository đã tồn tại nhiều tệp với dấu xuống dòng không đồng nhất, thêm `.gitattributes` không tự động làm sạch mọi working tree ngay lập tức. Nhóm cần thống nhất quy trình renormalize, thường dùng `git add --renormalize .` sau khi xem xét tác động, rồi kiểm tra diff trước khi commit. Trước khi thực hiện trên dự án đang làm việc, nên tạo commit hoặc backup để có thể đối chiếu thay đổi.

## 6. Attributes cho diff, merge và filter

Ngoài xử lý xuống dòng, `.gitattributes` còn điều khiển các hành vi khác:

| Thuộc tính | Công dụng | Ví dụ |
|---|---|---|
| `diff` / `-diff` | Bật hoặc tắt cách hiển thị diff dạng văn bản cho đường dẫn | `*.pdf -diff` |
| `merge` / `-merge` | Bật hoặc tắt merge văn bản thông thường hoặc chọn merge driver | `*.lock -merge` |
| `filter=<name>` | Chỉ định clean/smudge filter đã cấu hình | `*.asset filter=asset-clean` |
| `export-ignore` | Bỏ đường dẫn khỏi archive được tạo bằng `git archive` | `docs/internal/ export-ignore` |
| `export-subst` | Thay thế một số placeholder như `$Format:%H$` khi tạo archive | `VERSION.txt export-subst` |
| `working-tree-encoding=<encoding>` | Khai báo encoding trong working tree để Git chuyển đổi khi lưu và checkout | `*.ps1 working-tree-encoding=UTF-16LE` |

Các thuộc tính như `diff=<driver>`, `merge=<driver>` hoặc `filter=<driver>` có thể cần cấu hình bổ sung trong Git config của máy. Chỉ ghi tên driver vào `.gitattributes` chưa đủ để một lệnh tùy chỉnh tự chạy trên mọi máy. Nhóm cần thống nhất cài đặt, đường dẫn chương trình, phiên bản và cách xử lý khi driver không có sẵn.

Ví dụ một dự án dùng Git LFS có thể đánh dấu các tệp lớn bằng filter tương ứng:

```gitattributes
*.psd filter=lfs diff=lfs merge=lfs -text
*.mp4 filter=lfs diff=lfs merge=lfs -text
```

Các dòng này chỉ gán thuộc tính; Git LFS và cấu hình filter cần được cài đặt, thiết lập đúng trên máy của người cộng tác. `.gitattributes` không tự cài Git LFS hoặc tự tải nội dung LFS nếu công cụ chưa được cấu hình.

## 7. Hai file có thể cùng áp dụng cho một đường dẫn

Một tệp có thể đồng thời chịu quy tắc ignore và attributes, nhưng hai cơ chế vẫn độc lập. Ví dụ:

`.gitignore`:

```gitignore
/build/
*.log
.env
```

`.gitattributes`:

```gitattributes
* text=auto
*.sh text eol=lf
*.png binary
```

Trong tình huống này:

- `build/app.log` chưa tracked sẽ bị `.gitignore` bỏ qua.
- `src/run.sh` vẫn có thể được thêm và commit; `.gitattributes` yêu cầu Git xử lý nó như tệp văn bản với LF trong working tree.
- `assets/logo.png` vẫn có thể được thêm và commit; Git áp dụng thuộc tính `binary`.
- `.env` chưa tracked sẽ bị ignore; nếu `.env` đã tracked, Git vẫn theo dõi thay đổi của nó dù mẫu ignore khớp.

Không dùng `.gitattributes` để cố gắng che giấu tệp bí mật, và không dùng `.gitignore` để điều khiển chuyển đổi nội dung. Nếu một tệp nhạy cảm đã được commit, cần xử lý việc ngừng theo dõi và đánh giá lịch sử chứa bí mật theo quy trình bảo mật riêng; chỉ thêm mẫu ignore không xóa dữ liệu đã công bố.

## 8. Kiểm tra quy tắc ignore và attributes

### Tìm quy tắc đã bỏ qua một đường dẫn

Dùng `git check-ignore -v` để biết mẫu, file và số dòng tạo ra kết quả:

```bash
git check-ignore -v build/output.log
```

Nếu muốn kiểm tra cả đường dẫn đang tracked để xem mẫu ignore nào sẽ khớp, thêm `--no-index`:

```bash
git check-ignore -v --no-index config/local.json
```

`git check-ignore` chủ yếu phục vụ chẩn đoán các đường dẫn bị ignore; nếu không có quy tắc phù hợp, lệnh có thể không in kết quả. Tùy chọn `-v` giúp truy ngược nguồn quy tắc thay vì phải đoán từ nhiều file ignore.

### Xem thuộc tính hiệu lực

Dùng `git check-attr`:

```bash
# Xem các thuộc tính được gán cho một đường dẫn
git check-attr --all -- src/run.sh

# Kiểm tra riêng thuộc tính text và eol
git check-attr text eol -- src/run.sh

# Kiểm tra thuộc tính binary/diff
git check-attr binary diff -- assets/logo.png
```

Nếu muốn kiểm tra phiên bản `.gitattributes` đã nằm trong index thay vì phiên bản working tree, có thể dùng `--cached`:

```bash
git check-attr --cached --all -- src/run.sh
```

Điều này hữu ích khi bạn vừa chỉnh `.gitattributes` nhưng chưa stage, hoặc muốn so sánh cấu hình sắp commit với cấu hình hiện có trong working tree.

## 9. Một quy trình thiết lập cho dự án

Khi bắt đầu dự án mới hoặc chuẩn hóa repository hiện tại, có thể làm theo trình tự:

1. Liệt kê các thư mục và tệp sinh ra từ build, test, IDE, log, cache và cấu hình môi trường cá nhân.
2. Đưa các quy tắc bỏ qua dùng chung vào `.gitignore` ở gốc; giữ quy tắc riêng của máy trong `.git/info/exclude` hoặc file ignore toàn cục.
3. Xác định loại tệp cần xử lý đặc biệt: văn bản, nhị phân, script, file lớn, file cần merge driver hoặc filter.
4. Đưa quy tắc xử lý dùng chung vào `.gitattributes` và kiểm tra bằng `git check-attr`.
5. Kiểm tra các tệp đã tracked có vô tình bị coi là ignore hay không; nếu cần bỏ theo dõi, thực hiện `git rm --cached` có chủ đích.
6. Xem lại diff, stage hai file cấu hình và commit để cả nhóm nhận được quy tắc thống nhất.

Ví dụ kiểm tra trước khi commit:

```bash
git status --short
git check-ignore -v build/output.log
git check-attr --all -- src/run.sh assets/logo.png
git diff -- .gitignore .gitattributes
git diff --cached -- .gitignore .gitattributes
```

Các lệnh `git diff` cuối giúp kiểm tra phần thay đổi chưa stage và phần đã stage. Hãy bảo đảm quy tắc mới không vô tình bỏ qua tệp nguồn cần commit hoặc áp dụng chuyển đổi không phù hợp cho dữ liệu nhị phân.

## 10. Những nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu chính xác |
|---|---|
| Thêm tệp vào `.gitignore` sẽ xóa tệp khỏi repository | Không. Tệp đã tracked vẫn được theo dõi; dùng `git rm --cached` nếu muốn bỏ khỏi index nhưng giữ bản local. |
| `.gitattributes` ngăn Git thêm tệp | Không. Attributes điều khiển cách xử lý đường dẫn, không thay thế cơ chế ignore. |
| `.gitignore` chỉ có hiệu lực nếu được commit | File ignore local cũng có thể hoạt động; commit nó để chia sẻ quy tắc với cả nhóm. |
| `.git/info/exclude` được chia sẻ qua commit | Không. Đây là cấu hình riêng của repository local. |
| Tất cả quy tắc ignore toàn cục đều nên đặt trong `.gitignore` dự án | Quy tắc cá nhân của IDE hoặc hệ điều hành phù hợp hơn với file ignore toàn cục. |
| `binary` và ignore có cùng tác dụng | `binary` gán thuộc tính xử lý nội dung; ignore bỏ qua đường dẫn chưa tracked. |
| Thêm `text=auto` sẽ lập tức sửa mọi tệp hiện có | Cần xem xét và có thể chạy quy trình renormalize có kiểm soát để chuẩn hóa nội dung đã có. |
| Gán `filter=name` là đủ để filter chạy trên mọi máy | Driver phải được cấu hình và cài đặt tương ứng trên máy của người dùng. |

## 11. Tự kiểm tra

1. **`.gitignore` giải quyết vấn đề gì?**
   - Bỏ qua các đường dẫn chưa được theo dõi phù hợp với mẫu để chúng không được đề xuất thêm vào repository.
2. **`.gitattributes` giải quyết vấn đề gì?**
   - Gán thuộc tính để Git xử lý nội dung của đường dẫn, chẳng hạn chuẩn hóa xuống dòng, diff, merge hoặc filter.
3. **Một tệp đã tracked có ngừng được theo dõi khi thêm vào `.gitignore` không?**
   - Không. Cần chủ động gỡ tệp khỏi index bằng `git rm --cached` rồi commit thay đổi đó.
4. **Lệnh nào cho biết file và dòng `.gitignore` đã khớp một đường dẫn?**
   - `git check-ignore -v <path>`.
5. **Lệnh nào kiểm tra thuộc tính hiệu lực của một tệp?**
   - `git check-attr --all -- <path>`.
6. **Vì sao nên commit `.gitattributes` trong repository?**
   - Để mọi thành viên dùng cùng quy tắc xử lý nội dung, giảm khác biệt do hệ điều hành hoặc cấu hình cá nhân.

## Kết luận

`.gitignore` kiểm soát việc bỏ qua đường dẫn chưa được theo dõi; `.gitattributes` quy định Git xử lý nội dung của đường dẫn như thế nào. Dùng `.gitignore` cho thư mục build, log và cấu hình riêng; dùng `.gitattributes` cho chuẩn hóa văn bản, dấu xuống dòng, diff, merge, filter và archive. Khi cần chẩn đoán, `git check-ignore -v` cho biết quy tắc ignore đã khớp, còn `git check-attr` cho biết thuộc tính đang có hiệu lực. Phân biệt đúng hai cơ chế giúp repository sạch hơn và hành vi Git nhất quán giữa các thành viên.
