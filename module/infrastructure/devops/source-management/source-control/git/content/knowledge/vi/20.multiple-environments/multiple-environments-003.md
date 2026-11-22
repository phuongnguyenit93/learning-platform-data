# Chuẩn hóa tệp đã theo dõi bằng git add --renormalize

Khi nhiều người làm việc trên Windows, macOS và Linux, cùng một tệp văn bản có thể xuất hiện với kiểu kết thúc dòng khác nhau: LF hoặc CRLF. Nếu Git chưa được cấu hình thống nhất, thay đổi chỉ ở dấu kết thúc dòng có thể khiến một file trông như đã sửa toàn bộ, tạo diff rất lớn hoặc làm lịch sử khó đọc.

Git cung cấp `git add --renormalize` để chạy lại quy trình làm sạch (clean) trên các tệp đã được theo dõi và cập nhật nội dung tương ứng trong index. Lệnh này đặc biệt hữu ích sau khi thay đổi thuộc tính văn bản trong `.gitattributes` hoặc cấu hình chuyển đổi line ending. Khi dùng đúng cách, repository lưu nội dung văn bản theo một dạng chuẩn, còn mỗi working tree có thể dùng kiểu kết thúc dòng phù hợp với môi trường.

## 1. Vì sao cần chuẩn hóa tệp?

Trong một repository có nhiều hệ điều hành, cùng một dòng văn bản có thể được lưu với hai kiểu kết thúc:

- **LF** (`\n`): thường dùng trên Linux và macOS.
- **CRLF** (`\r\n`): thường gặp trên Windows.

Nếu không có quy tắc rõ ràng, một thành viên có thể commit file với CRLF, người khác checkout rồi lưu lại thành LF. Git có thể hiển thị hàng loạt dòng thay đổi dù nội dung logic của chương trình không đổi.

Ví dụ, một file có 100 dòng. Nếu chỉ kiểu kết thúc dòng thay đổi, diff có thể báo cả 100 dòng bị xóa và thêm lại. Điều này gây nhiễu khi review và làm khó việc tìm thay đổi thực sự.

Một cách giải quyết là thống nhất nội dung lưu trong Git index/repository theo LF, sau đó để Git chuyển đổi sang kiểu line ending mong muốn khi checkout về working tree.

## 2. Git chuyển đổi line ending ở đâu?

Có thể hình dung quy trình như sau:

```text
Working tree
  (CRLF hoặc LF theo môi trường)
        |
        | clean filter khi git add
        v
Index / Git object database
  (nội dung chuẩn, thường là LF)
        |
        | smudge / checkout conversion
        v
Working tree
  (LF hoặc CRLF theo thuộc tính)
```

Khi bạn chạy `git add`, Git đọc nội dung từ working tree rồi áp dụng quy trình clean trước khi ghi nội dung vào index. Khi checkout, Git áp dụng quy trình chuyển đổi ngược hoặc smudge filter để tạo nội dung trong working tree.

Với line ending, các thuộc tính trong `.gitattributes` giúp Git biết file nào là văn bản và kiểu kết thúc dòng mong muốn. Các thuộc tính thường dùng:

| Thuộc tính | Ý nghĩa |
|---|---|
| `text` | Xem file là văn bản và chuẩn hóa line ending trong index |
| `text=auto` | Để Git tự nhận diện file văn bản trước khi chuẩn hóa |
| `-text` | Tắt chuẩn hóa văn bản cho đường dẫn khớp |
| `eol=lf` | Checkout file văn bản với LF |
| `eol=crlf` | Checkout file văn bản với CRLF |

Ví dụ `text` làm cho nội dung văn bản được chuẩn hóa trong index thành LF. Thuộc tính `eol` quy định kiểu line ending khi Git ghi file ra working tree.

## 3. Khai báo quy tắc bằng .gitattributes

Để repository có quy tắc rõ ràng cho mọi thành viên, tạo hoặc cập nhật file `.gitattributes` ở thư mục gốc.

Ví dụ:

```gitattributes
# Tự nhận diện file văn bản và chuẩn hóa line ending
* text=auto

# Script shell dùng LF
*.sh text eol=lf

# Script batch trên Windows dùng CRLF
*.bat text eol=crlf
*.cmd text eol=crlf

# File nhị phân không chuyển đổi line ending
*.png -text
*.jpg -text
*.jpeg -text
*.pdf -text
```

Quy tắc này có các mục đích:

- `* text=auto` để Git tự nhận diện file văn bản và chuẩn hóa các file được nhận diện là text.
- `*.sh text eol=lf` bảo đảm script shell được checkout với LF.
- `*.bat` và `*.cmd` được checkout với CRLF, phù hợp với một số công cụ Windows.
- Các file hình ảnh và PDF được đánh dấu `-text` để không bị xử lý như văn bản.

Bạn có thể điều chỉnh danh sách phần mở rộng theo loại file thực tế của dự án. Với định dạng nhị phân hoặc định dạng văn bản đặc biệt, hãy khai báo thuộc tính tường minh thay vì phụ thuộc hoàn toàn vào nhận diện tự động.

File `.gitattributes` nên được commit cùng repository để mọi người nhận được cùng quy tắc. Thuộc tính áp dụng cho đường dẫn tương đối với vị trí file `.gitattributes`; file ở thư mục con có thể đặt quy tắc riêng cho các file bên dưới nó.

Kiểm tra thuộc tính Git đang áp dụng cho một file:

```bash
git check-attr text eol -- src/Main.java
git check-attr text eol -- scripts/build.sh
git check-attr text eol -- tools/build.bat
```

Kết quả cho biết giá trị thuộc tính hiệu lực như `text: auto`, `text: set`, `eol: lf` hoặc `eol: crlf`. Nếu kết quả là `unspecified`, không có quy tắc tường minh cho thuộc tính đó ở các nguồn đang được xét.

## 4. git add --renormalize thực hiện điều gì?

Cú pháp cơ bản:

```bash
git add --renormalize .
```

Lệnh yêu cầu Git áp dụng lại quy trình clean cho các file đã được theo dõi trong phạm vi pathspec `.`, rồi cập nhật index bằng kết quả mới. Tùy chọn `--renormalize` tương đương việc áp dụng lại clean process cho các tracked files và ngầm bao gồm hành vi cập nhật tracked path (`-u`).

Điều này có nghĩa:

- Các file đã tracked được đọc lại từ working tree và xử lý theo thuộc tính/configuration hiện tại.
- Index được cập nhật nếu nội dung sau clean khác nội dung đang lưu.
- File untracked không tự động được thêm chỉ vì bạn chạy `--renormalize`.
- Lệnh không tự tạo commit và không tự push thay đổi lên remote.
- Pathspec quyết định phạm vi; chạy từ thư mục con với `.` chỉ tác động các đường dẫn bên dưới thư mục đó.

Vì vậy, nếu vừa tạo file `.gitattributes` mới, hãy stage file đó riêng:

```bash
git add .gitattributes
```

Sau đó chạy renormalize trên repository từ thư mục gốc:

```bash
git add --renormalize .
```

Stage `.gitattributes` riêng là cần thiết khi file mới chưa được theo dõi, vì `--renormalize` chỉ xử lý tracked files. Nếu `.gitattributes` đã được theo dõi, thay đổi của nó cũng sẽ được cập nhật khi chạy renormalize.

## 5. Quy trình chuẩn hóa an toàn

Trước khi chuẩn hóa, kiểm tra trạng thái repository:

```bash
git status
```

Nên bắt đầu từ working tree sạch để tránh vô tình đưa thay đổi đang làm dở vào cùng một lần chuẩn hóa. Nếu có thay đổi cần giữ, hãy commit hoặc stash chúng trước; ghi nhận rõ các thay đổi đó để có thể phục hồi sau.

Một quy trình phổ biến:

**Bước 1: Xác định quy tắc line ending của dự án.**

Quyết định file nào là text, kiểu line ending trong index và kiểu line ending mong muốn khi checkout. Không nên thay đổi cấu hình toàn cục hoặc thêm pattern một cách tùy tiện trước khi hiểu file nào cần được chuẩn hóa.

**Bước 2: Tạo hoặc cập nhật .gitattributes.**

Ví dụ:

```gitattributes
* text=auto
*.sh text eol=lf
*.bat text eol=crlf
```

**Bước 3: Stage file quy tắc.**

```bash
git add .gitattributes
```

Nếu file `.gitattributes` đã tracked, lệnh này stage thay đổi của file. Nếu nó mới được tạo, lệnh đưa file mới vào index.

**Bước 4: Chuẩn hóa các file đã theo dõi.**

Chạy tại thư mục gốc repository:

```bash
git add --renormalize .
```

Git chạy lại clean process cho các tracked files trong phạm vi repository.

**Bước 5: Kiểm tra phạm vi thay đổi.**

```bash
git status
git diff --cached --stat
git diff --cached --check
git diff --cached
```

Xem danh sách file bị thay đổi và nội dung diff. Nếu nhiều file thay đổi hơn dự kiến, kiểm tra lại thuộc tính, filter và line ending trước khi commit.

**Bước 6: Commit thay đổi đã xác minh.**

```bash
git commit -m "Normalize tracked files"
```

Commit thường bao gồm cả file `.gitattributes` và những nội dung trong index đã được chuẩn hóa. Nếu nhóm muốn tách thay đổi quy tắc và thay đổi dữ liệu thành hai commit, có thể tổ chức staging và commit theo kế hoạch riêng, nhưng phải bảo đảm commit đầu tiên không để repository ở trạng thái quy tắc chưa nhất quán.

## 6. Kiểm tra line ending trong index và working tree

Git có lệnh hữu ích để kiểm tra trạng thái line ending của từng file:

```bash
git ls-files --eol
```

Ví dụ đầu ra:

```text
i/lf    w/crlf  attr/text eol=crlf    scripts/build.bat
i/lf    w/lf    attr/text eol=lf      scripts/build.sh
i/-text w/-text attr/-text            images/logo.png
```

Các cột có ý nghĩa:

- `i/`: line ending của nội dung trong index.
- `w/`: line ending trong working tree.
- `attr/`: thuộc tính áp dụng cho đường dẫn đó.

Ví dụ `i/lf w/crlf attr/text eol=crlf` là trạng thái hợp lệ: Git lưu nội dung chuẩn hóa bằng LF trong index, nhưng checkout ra working tree bằng CRLF theo thuộc tính. Không nên kết luận file sai chỉ vì cột `i` và `w` khác nhau; cần đối chiếu với thuộc tính mong muốn.

Kết hợp với `git check-attr` để xác minh quy tắc:

```bash
git check-attr --all -- scripts/build.bat
git ls-files --eol -- scripts/build.bat
```

Nếu thuộc tính không như dự kiến, xem lại vị trí `.gitattributes`, pattern và các nguồn attributes khác. Nếu thuộc tính đúng nhưng file trong working tree chưa có kiểu line ending mong muốn, có thể cần checkout lại file sau khi đã bảo toàn mọi thay đổi chưa commit.

## 7. Phân biệt renormalize với các lệnh add khác

Các lệnh `git add` có mục tiêu khác nhau:

| Lệnh | Tác dụng chính |
|---|---|
| `git add file` | Stage nội dung hiện tại của file được chỉ định |
| `git add .` | Stage thay đổi và file mới trong phạm vi pathspec hiện tại |
| `git add -A` | Stage thêm, sửa và xóa trên phạm vi được chỉ định (mặc định toàn working tree nếu không có pathspec) |
| `git add -u` | Stage thay đổi và xóa của các file đã tracked, không thêm file mới |
| `git add --renormalize .` | Chạy lại clean process cho các file đã tracked trong phạm vi pathspec và cập nhật index |

Điểm khác biệt quan trọng là `--renormalize` yêu cầu Git áp dụng lại quy trình clean, nên phù hợp sau khi thay đổi `.gitattributes` hoặc quy tắc line ending. `git add .` đơn thuần không diễn đạt ý định chuẩn hóa lại toàn bộ file đã tracked theo quy tắc mới.

Nếu cần thêm file mới, hãy dùng `git add` thông thường cho file đó. Nếu cần chuẩn hóa tracked files, dùng `--renormalize` với pathspec rõ ràng.

## 8. Ảnh hưởng của core.autocrlf và thuộc tính text

Git có cấu hình `core.autocrlf` để hỗ trợ chuyển đổi line ending theo môi trường:

| Giá trị | Hành vi khái quát |
|---|---|
| `true` | Chuyển LF trong nội dung được nhận diện là text sang CRLF khi checkout trên môi trường phù hợp; chuẩn hóa CRLF về LF khi add |
| `input` | Chuẩn hóa CRLF về LF khi add, không chuyển LF thành CRLF khi checkout |
| `false` | Không bật chuyển đổi tự động theo cấu hình này |

Xem giá trị hiện tại và nguồn cấu hình:

```bash
git config --show-origin --get core.autocrlf
git config --show-origin --get core.safecrlf
```

`core.autocrlf` thường là lựa chọn theo máy người dùng. `.gitattributes` giúp repository mô tả quy tắc cho từng loại file rõ ràng hơn, để các thành viên không phải dựa hoàn toàn vào cấu hình cá nhân.

Khi thay đổi `core.autocrlf` hoặc thuộc tính `text`, nội dung đã có trong index không tự động được làm mới chỉ vì cấu hình thay đổi. Đây là một trường hợp điển hình để dùng:

```bash
git add --renormalize .
```

Không nên thay đổi `core.autocrlf` của mọi thành viên cùng lúc mà không có quy ước dự án. Hãy thống nhất `.gitattributes`, chuẩn hóa index trong một commit có review và hướng dẫn nhóm cập nhật theo commit đó.

## 9. Những trường hợp cần thận trọng

**File nhị phân:** Không áp dụng chuẩn hóa text lên ảnh, archive, executable hoặc file nhị phân khác. Dùng `-text` cho các nhóm file cần bảo vệ khỏi chuyển đổi line ending. Với `text=auto`, Git cố gắng nhận diện file văn bản, nhưng dự án vẫn nên khai báo tường minh những định dạng quan trọng.

**Clean/smudge filter tùy chỉnh:** `--renormalize` chạy lại clean process, bao gồm filter được cấu hình cho file. Nếu filter biến đổi nội dung, kết quả có thể khác đáng kể so với chỉ đổi CRLF/LF. Trước khi chạy trên repository lớn, kiểm tra filter và thử trên một nhóm file đại diện.

**Thay đổi chưa commit:** Vì lệnh cập nhật index từ nội dung working tree của tracked files, các chỉnh sửa đang làm dở trên những file đó có thể bị stage cùng lần chuẩn hóa. Hãy commit hoặc stash công việc riêng trước khi chạy.

**Phạm vi pathspec:** `git add --renormalize .` chỉ bao phủ thư mục hiện tại và các đường dẫn bên dưới. Nếu chạy từ một thư mục con, các tracked files ở nơi khác trong repository không được xử lý. Hãy chạy từ root repository để chuẩn hóa toàn bộ.

**File đã bị xóa:** Vì tùy chọn này ngầm bao gồm cập nhật tracked paths, các thay đổi xóa trong phạm vi pathspec cũng có thể được cập nhật vào index. Kiểm tra kỹ `git status` và staged diff trước khi commit.

**Lịch sử đã commit:** Renormalize chỉ cập nhật index hiện tại. Nó không viết lại các commit cũ và không xóa những phiên bản trước của file khỏi lịch sử Git.

## 10. Xử lý khi diff sau renormalize quá lớn

Nếu sau khi chạy lệnh, Git báo hàng trăm file thay đổi, đừng commit ngay. Hãy kiểm tra theo thứ tự:

1. Xác nhận `.gitattributes` có được stage và chứa đúng pattern không.
2. Dùng `git check-attr text eol -- <file>` để kiểm tra thuộc tính trên một số file đại diện.
3. Dùng `git ls-files --eol` để xem line ending trong index và working tree.
4. Xem `git diff --cached --stat` và `git diff --cached` để phân biệt thay đổi line ending với thay đổi nội dung thực.
5. Kiểm tra các clean filter nếu dự án có cấu hình filter riêng.
6. Nếu quy tắc sai, sửa `.gitattributes`, sau đó chạy lại `git add --renormalize .` khi đã bảo toàn các thay đổi cần giữ.

Nếu một file có thay đổi logic thực sự trước khi chuẩn hóa, hãy xác định và review thay đổi đó riêng. Mục tiêu là bảo đảm commit chuẩn hóa chỉ chứa những thay đổi mà nhóm hiểu và chấp nhận.

## Kết luận

Dùng `.gitattributes` để thống nhất cách Git xử lý file giữa nhiều môi trường, rồi chạy `git add --renormalize .` từ root repository để áp dụng lại clean process cho các file đã tracked. Stage `.gitattributes` riêng nếu file mới, kiểm tra index và working tree bằng `git ls-files --eol`, xác minh thuộc tính bằng `git check-attr`, sau đó review staged diff trước khi commit. Renormalize cập nhật index hiện tại; nó không tự thêm file untracked và không viết lại lịch sử cũ.
