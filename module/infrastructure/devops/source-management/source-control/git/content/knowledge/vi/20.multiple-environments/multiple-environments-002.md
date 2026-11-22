# Phối hợp `core.autocrlf`, `core.eol` với thuộc tính `text` và `eol`

Một dự án Git thường được phát triển trên nhiều hệ điều hành. Windows thường dùng CRLF (`\r\n`) làm ký tự kết thúc dòng, trong khi Linux và macOS thường dùng LF (`\n`). Nếu mỗi máy lưu cùng một file với kiểu xuống dòng khác nhau, Git có thể hiển thị hàng loạt dòng thay đổi dù nội dung logic không đổi. Một số công cụ còn gặp lỗi khi đọc script hoặc file cấu hình có kiểu xuống dòng không phù hợp.

Git cung cấp hai lớp điều khiển để xử lý vấn đề này. Các cấu hình `core.autocrlf` và `core.eol` quy định cách Git chuyển đổi line ending trong môi trường local; thuộc tính `.gitattributes` với `text` và `eol` xác định chính sách cho từng loại file trong repository. Khi phối hợp đúng, dự án có thể lưu nội dung văn bản theo một chuẩn thống nhất trong Git, đồng thời checkout ra kiểu xuống dòng phù hợp với công cụ hoặc hệ điều hành cần dùng.

Trong dịch vụ quản lý mã nguồn Git, đây là một phần của việc cộng tác đa môi trường. Một chính sách rõ ràng giúp giảm diff nhiễu, tránh xung đột giả và giữ cho script, mã nguồn, tài liệu hoạt động ổn định trên các máy khác nhau.

## 1. LF và CRLF là gì?

Ký tự kết thúc dòng đánh dấu vị trí xuống dòng trong file văn bản. Hai kiểu phổ biến là:

| Kiểu | Ký hiệu | Byte biểu diễn | Môi trường thường gặp |
| --- | --- | --- | --- |
| LF | Line Feed | `0A` | Linux, macOS và nhiều công cụ phát triển hiện đại |
| CRLF | Carriage Return + Line Feed | `0D 0A` | Windows và một số định dạng văn bản cũ |

Ví dụ, hai file sau có thể hiển thị giống nhau trong trình soạn thảo:

```text
Hello
Git
```

Nhưng byte thực tế khác nhau:

```text
File LF:    48 65 6C 6C 6F 0A 47 69 74 0A
File CRLF:  48 65 6C 6C 6F 0D 0A 47 69 74 0D 0A
```

Nếu Git không chuẩn hóa line ending, một lần chuyển file từ LF sang CRLF có thể khiến Git xem tất cả dòng là đã thay đổi. Điều này làm code review khó đọc, tăng khả năng xung đột merge và che khuất thay đổi logic thật sự.

### Git lưu nội dung ở đâu?

Khi commit, Git lưu snapshot nội dung file trong object database. Với file văn bản được cấu hình chuẩn hóa, Git thường lưu dạng LF trong blob, còn lúc checkout có thể chuyển thành CRLF hoặc LF tùy chính sách. Vì vậy, kiểu xuống dòng nhìn thấy trong working tree không nhất thiết giống byte được lưu trong blob.

Có thể hình dung quy trình:

```text
Working tree
  File CRLF hoặc LF
        |
        | clean conversion khi git add
        v
Index / blob được chuẩn hóa
  Nội dung văn bản dùng LF
        |
        | smudge conversion khi checkout
        v
Working tree
  Kiểu xuống dòng theo thuộc tính và cấu hình
```

Git thực hiện chuyển đổi thông qua các bước clean khi đưa nội dung vào index và smudge khi đưa nội dung ra working tree. `.gitattributes` xác định file nào cần xử lý; cấu hình local ảnh hưởng tới kiểu line ending khi checkout.

## 2. `core.autocrlf` điều khiển điều gì?

`core.autocrlf` là cấu hình Git ở local, thường được đặt theo thói quen của người dùng hoặc môi trường làm việc. Có ba giá trị thường gặp:

| Giá trị | Khi đưa nội dung vào Git | Khi checkout ra working tree |
| --- | --- | --- |
| `true` | Chuyển CRLF thành LF | Chuyển LF thành CRLF |
| `input` | Chuyển CRLF thành LF | Không tự chuyển LF thành CRLF |
| `false` | Không tự chuyển đổi theo cấu hình này | Không tự chuyển đổi theo cấu hình này |

### `core.autocrlf=true`

```bash
git config --global core.autocrlf true
```

Thiết lập này thường được dùng trên Windows. Git chuẩn hóa CRLF thành LF khi đưa nội dung vào index và chuyển LF thành CRLF khi checkout. Nó gần tương đương với việc áp dụng chính sách `text=auto` cùng kiểu checkout CRLF cho các file được nhận diện là văn bản.

Ví dụ: file Java trong repository được lưu với LF, nhưng khi checkout trên máy Windows có thể xuất hiện CRLF trong working tree. Khi stage và commit, Git chuyển CRLF về LF để giữ nội dung chuẩn hóa.

### `core.autocrlf=input`

```bash
git config --global core.autocrlf input
```

Thiết lập này phù hợp với môi trường thường dùng LF như Linux hoặc macOS. Git chuyển CRLF thành LF khi đưa nội dung vào index nhưng không tự chuyển LF thành CRLF khi checkout. File checkout thường giữ LF.

### `core.autocrlf=false`

```bash
git config --global core.autocrlf false
```

Git không tự chuyển đổi line ending theo `core.autocrlf`. Nội dung working tree được giữ nguyên theo dữ liệu và các quy tắc thuộc tính đang áp dụng. Nếu repository cần chính sách chuẩn hóa, hãy mô tả rõ trong `.gitattributes` thay vì trông chờ mỗi máy có cùng thiết lập toàn cục.

### Xem và đặt cấu hình

```bash
git config --show-origin --get core.autocrlf
git config --global --get core.autocrlf
git config --local core.autocrlf false
```

`--show-origin` cho biết giá trị đến từ file cấu hình nào. `--global` đặt cho người dùng hiện tại; `--local` chỉ đặt trong repository đang đứng. Nếu lệnh `--get` không trả kết quả, cấu hình có thể chưa được đặt và Git sẽ dùng giá trị mặc định.

Không nên tùy tiện đổi `core.autocrlf` toàn cục giữa nhiều dự án có chính sách khác nhau. Cấu hình toàn cục tác động tới nhiều repository; cấu hình local giúp điều chỉnh hành vi cho một dự án cụ thể.

## 3. `core.eol` quy định line ending khi checkout

`core.eol` xác định kiểu kết thúc dòng Git sử dụng khi checkout các file được xử lý như văn bản. Các giá trị phổ biến:

| Giá trị | Kết quả khi checkout |
| --- | --- |
| `lf` | LF |
| `crlf` | CRLF |
| `native` | Kiểu xuống dòng mặc định của hệ điều hành hiện tại |

Ví dụ:

```bash
git config --local core.eol lf
```

Hoặc:

```bash
git config --local core.eol crlf
```

`core.eol` chủ yếu có ý nghĩa với file được đánh dấu là text. Git dùng cấu hình này khi `core.autocrlf` không được đặt hoặc được đặt thành `false`. Khi `core.autocrlf` là `true` hoặc `input`, cấu hình đó quyết định hành vi checkout mặc định và `core.eol` không còn là lựa chọn quyết định. Vì vậy, khi phân tích một file cụ thể, cần kiểm tra cả cấu hình lẫn thuộc tính của file.

Xem cấu hình:

```bash
git config --show-origin --get core.eol
```

Nếu không đặt `core.eol`, giá trị mặc định là `native` trong trường hợp Git cần quyết định kiểu checkout dựa trên cấu hình này.

## 4. Thuộc tính `.gitattributes` và vai trò của `text`

`.gitattributes` là file chính sách được commit cùng repository. Nó cho phép nhóm xác định cách Git xử lý từng loại file, không phụ thuộc hoàn toàn vào cấu hình cá nhân trên mỗi máy.

Thuộc tính `text` kiểm soát việc chuẩn hóa line ending:

- `text`: coi file là văn bản và chuẩn hóa CRLF thành LF khi đưa vào index.
- `text=auto`: để Git tự nhận diện file văn bản rồi chuẩn hóa các file được nhận diện.
- `-text`: không thực hiện chuẩn hóa line ending cho file đó; thường dùng cho file nhị phân.

Ví dụ file `.gitattributes` ở thư mục gốc:

```gitattributes
# Mặc định nhận diện file văn bản và chuẩn hóa về LF trong Git
* text=auto

# Mã nguồn và tài liệu dùng LF trong working tree
*.java text eol=lf
*.kt text eol=lf
*.js text eol=lf
*.ts text eol=lf
*.json text eol=lf
*.yml text eol=lf
*.yaml text eol=lf
*.md text eol=lf
*.sh text eol=lf

# File batch và một số script Windows dùng CRLF khi checkout
*.bat text eol=crlf
*.cmd text eol=crlf

# File nhị phân không chuyển đổi line ending
*.png -text
*.jpg -text
*.jar -text
*.zip -text
```

Quy tắc `* text=auto` là chính sách nền cho file được Git nhận diện là văn bản. Các quy tắc cụ thể phía sau chỉ định kiểu checkout rõ ràng cho từng phần mở rộng. Hãy điều chỉnh danh sách theo loại file thực tế của dự án; không phải mọi file có phần mở rộng giống nhau đều nhất thiết có cùng chính sách.

### Vì sao file nhị phân cần `-text`?

File nhị phân như ảnh, archive, font hoặc file thực thi không có khái niệm line ending theo nghĩa văn bản. Nếu Git cố chuyển CRLF/LF trong các byte của file đó, dữ liệu có thể bị hỏng. Đánh dấu `-text` giúp Git không áp dụng chuẩn hóa line ending.

Có thể dùng thuộc tính `binary` cho file nhị phân:

```gitattributes
*.png binary
*.jpg binary
*.pdf binary
```

Thuộc tính macro `binary` tương đương với việc tắt diff, merge văn bản và chuẩn hóa text cho file đó. Nếu chỉ cần kiểm soát line ending, `-text` là đủ.

## 5. Thuộc tính `eol` chỉ định kiểu checkout theo từng file

Thuộc tính `eol` cho phép repository quy định kiểu xuống dòng trong working tree cho một nhóm file:

- `eol=lf`: checkout file với LF.
- `eol=crlf`: checkout file với CRLF.

Ví dụ:

```gitattributes
*.sh text eol=lf
*.bat text eol=crlf
```

Với `*.sh`, Git chuẩn hóa nội dung lưu trong repository về LF và checkout thành LF. Điều này quan trọng vì shell trên Linux thường không chấp nhận CRLF trong một số script, dẫn tới lỗi như ký tự `\r` không mong muốn ở cuối dòng lệnh hoặc lỗi interpreter.

Với `*.bat`, Git vẫn chuẩn hóa nội dung lưu trong repository về LF nhưng checkout ra CRLF để phù hợp với một số công cụ Windows. Nhờ đó, người dùng ở hai hệ điều hành có thể làm việc trên cùng repository mà không tạo ra thay đổi line ending hàng loạt.

Khi một file có thuộc tính `eol=lf` hoặc `eol=crlf`, Git xử lý nó như file text và áp dụng kiểu checkout được chỉ định. Đây là cách khai báo chính sách rõ ràng hơn so với phụ thuộc vào `core.eol` của từng máy.

## 6. Phối hợp `core.autocrlf`, `core.eol`, `text` và `eol`

Các cơ chế này không hoàn toàn thay thế nhau. Có thể hiểu vai trò như sau:

| Cơ chế | Phạm vi | Vai trò |
| --- | --- | --- |
| `core.autocrlf` | Cấu hình local của người dùng/repository | Bật quy tắc chuyển đổi tự động phổ quát cho file được nhận diện là text |
| `core.eol` | Cấu hình local | Chọn kiểu checkout mặc định cho file text khi không có quy tắc cụ thể chi phối |
| `text` | Thuộc tính theo đường dẫn trong `.gitattributes` | Bật hoặc tắt chuẩn hóa line ending khi đưa nội dung vào Git |
| `eol` | Thuộc tính theo đường dẫn trong `.gitattributes` | Chỉ định LF hoặc CRLF cho file khi checkout |

Thứ tự suy nghĩ khi kiểm tra một file:

1. Xác định file có được xử lý như text hay không qua `text`, `text=auto` hoặc `-text`.
2. Kiểm tra file có quy định `eol=lf` hoặc `eol=crlf` hay không.
3. Nếu không có kiểu checkout cụ thể, xem `core.autocrlf` và `core.eol` để hiểu hành vi local.
4. Kiểm tra line ending thực tế trong index và working tree.

Một chính sách repository có thể viết rõ:

```gitattributes
* text=auto
*.java text eol=lf
*.sh text eol=lf
*.bat text eol=crlf
*.png -text
```

Trong khi đó, mỗi máy có thể đặt cấu hình local phù hợp với môi trường:

```bash
# Ví dụ cấu hình trên máy Windows
git config --global core.autocrlf true

# Ví dụ cấu hình trên máy Linux/macOS
git config --global core.autocrlf input
```

Các thuộc tính rõ ràng trong `.gitattributes` giúp thống nhất hành vi giữa thành viên. Cấu hình local vẫn hữu ích cho file chưa có quy tắc cụ thể hoặc repository không cung cấp chính sách chi tiết.

### Tránh hiểu nhầm về độ ưu tiên

`.gitattributes` xác định chính sách theo đường dẫn và có thể ghi đè hành vi mặc định do cấu hình local cung cấp. `core.autocrlf` và `core.eol` không phải là hai file cấu hình dự án có thể đồng bộ cho cả nhóm; chúng thuộc cấu hình Git của từng máy. Khi một file có `eol` cụ thể, hãy xem đó là quy định checkout của file ấy thay vì cố suy ra từ `core.eol` toàn cục.

## 7. Kiểm tra thuộc tính và line ending thực tế

Không nên phỏng đoán chỉ từ hệ điều hành. Git có các lệnh giúp xem thuộc tính đang áp dụng và line ending ở từng vùng.

### Dùng `git check-attr`

```bash
git check-attr text eol -- src/main/java/example/App.java
git check-attr --all -- scripts/deploy.sh
```

Lệnh đầu cho biết giá trị `text` và `eol` Git áp dụng cho file Java. Lệnh thứ hai liệt kê tất cả thuộc tính đang áp dụng cho script. Kết quả có thể cho biết thuộc tính được đặt, không đặt (`unset`) hoặc không có quy tắc cụ thể (`unspecified`).

### Dùng `git ls-files --eol`

```bash
git ls-files --eol
git ls-files --eol -- '*.java'
```

Lệnh hiển thị line ending trong index, working tree và thuộc tính áp dụng cho mỗi file. Ví dụ:

```text
i/lf    w/crlf  attr/text eol=crlf    src/main/java/example/App.java
i/lf    w/lf    attr/text eol=lf      scripts/deploy.sh
```

Ý nghĩa:

- `i/lf`: nội dung trong index dùng LF.
- `w/crlf`: file trong working tree dùng CRLF.
- `w/lf`: file trong working tree dùng LF.
- `attr/text eol=...`: thuộc tính text và kiểu checkout đang áp dụng.

Nếu thấy `i/crlf`, repository có thể đang lưu CRLF trong index, hoặc file chưa được chuẩn hóa theo chính sách mong muốn. Nếu thấy `w/mixed`, file có thể chứa nhiều kiểu line ending; hãy kiểm tra trước khi chuẩn hóa.

### Kiểm tra cấu hình thực tế

```bash
git config --show-origin --get-all core.autocrlf
git config --show-origin --get-all core.eol
git config --show-origin --get-all core.safecrlf
```

`--show-origin` giúp nhận ra cấu hình đến từ system, global hay local. Có thể có nhiều giá trị do nhiều cấp cấu hình; cần xem giá trị hiệu lực và nguồn trước khi thay đổi.

## 8. `core.safecrlf` và cảnh báo chuyển đổi không an toàn

`core.safecrlf` giúp Git cảnh báo hoặc từ chối một số chuyển đổi line ending không thể đảo ngược an toàn. Các giá trị thường dùng:

| Giá trị | Hành vi |
| --- | --- |
| `false` | Không bật kiểm tra an toàn này |
| `warn` | Cảnh báo khi phát hiện chuyển đổi có thể gây mất thông tin |
| `true` | Từ chối thao tác khi chuyển đổi không thể đảo ngược theo kiểm tra của Git |

Ví dụ:

```bash
git config --global core.safecrlf warn
```

Thiết lập này có ích khi nhóm đang chuyển đổi chính sách line ending hoặc khi một file có thể chứa line ending hỗn hợp. Nó giúp phát hiện tình huống Git có nguy cơ chuẩn hóa làm thay đổi byte không mong muốn.

`core.safecrlf` không thay thế `.gitattributes` và cũng không bảo đảm mọi file đều có kiểu xuống dòng nhất quán. Hãy kết hợp nó với thuộc tính rõ ràng, kiểm tra `git ls-files --eol` và review diff trước khi commit.

## 9. Chuẩn hóa repository đã có lịch sử line ending không nhất quán

Nếu repository đã tồn tại lâu, có thể một số file đang lưu LF, số khác lưu CRLF hoặc cùng một file có kiểu xuống dòng hỗn hợp. Khi thêm `.gitattributes`, Git chưa tự động viết lại toàn bộ blob hiện có. Cần yêu cầu Git áp dụng lại quy tắc clean cho các file tracked.

### Bước 1: Bảo vệ công việc hiện tại

Kiểm tra trạng thái:

```bash
git status -sb
```

Hãy commit hoặc stash các thay đổi đang làm và bảo đảm có thể khôi phục nếu kết quả chuẩn hóa không như mong muốn. Việc chuẩn hóa có thể tạo ra diff lớn ở index.

### Bước 2: Tạo `.gitattributes`

Ví dụ chính sách cho dự án:

```gitattributes
* text=auto
*.java text eol=lf
*.kt text eol=lf
*.sh text eol=lf
*.bat text eol=crlf
*.cmd text eol=crlf
*.png -text
*.jpg -text
*.jar -text
```

Điều chỉnh quy tắc theo công nghệ và công cụ thực tế. Stage file thuộc tính trước:

```bash
git add .gitattributes
```

### Bước 3: Chuẩn hóa lại các file tracked

```bash
git add --renormalize .
```

`--renormalize` yêu cầu Git chạy lại quy trình clean trên tất cả file tracked để đưa nội dung vào index theo thuộc tính mới. Tùy chọn này ngầm bao gồm cập nhật các file tracked (`-u`); nó không tự thêm các file untracked mới như `.gitattributes` nếu file đó chưa được stage.

### Bước 4: Kiểm tra diff

```bash
git status --short
git diff --cached --stat
git diff --cached --ignore-space-at-eol
git ls-files --eol
```

Đảm bảo thay đổi chủ yếu là chuẩn hóa line ending. Nếu diff cho thấy nội dung logic bị xóa hoặc thay đổi, dừng lại và kiểm tra thuộc tính, encoding hoặc file có line ending hỗn hợp trước khi commit.

`git diff --ignore-space-at-eol` giúp bỏ qua khác biệt ở cuối dòng khi so sánh nội dung, nhưng không có nghĩa là mọi thay đổi trong diff đều an toàn. Vẫn cần xem các file thay đổi và kiểm tra những dòng có nội dung thực sự khác.

### Bước 5: Commit thay đổi chuẩn hóa

```bash
git commit -m "Normalize text file line endings"
```

Nên thực hiện thay đổi chính sách và chuẩn hóa trong một commit riêng, không trộn với refactor hay thay đổi chức năng. Review sẽ dễ nhận ra commit này chỉ nhằm đồng nhất line ending.

Sau khi commit, thông báo cho nhóm để mọi người cập nhật repository và tránh tạo ra một đợt diff line ending lặp lại. Nếu thành viên đang có thay đổi local, họ cần lưu công việc trước khi đồng bộ với commit chuẩn hóa.

## 10. Ví dụ chính sách cho nhóm Windows, Linux và macOS

Giả sử dự án Java có thành viên dùng Windows, Linux và macOS. Nhóm quyết định:

- Mã nguồn Java, Kotlin, JSON, YAML, Markdown và shell script lưu LF trong repository và checkout LF.
- Script Windows `.bat` và `.cmd` checkout CRLF.
- File ảnh, archive và thư viện đóng gói không chuyển đổi line ending.

File `.gitattributes`:

```gitattributes
* text=auto

*.java text eol=lf
*.kt text eol=lf
*.json text eol=lf
*.yml text eol=lf
*.yaml text eol=lf
*.md text eol=lf
*.sh text eol=lf

*.bat text eol=crlf
*.cmd text eol=crlf

*.png -text
*.jpg -text
*.gif -text
*.jar -text
*.zip -text
```

Thành viên Windows có thể đặt:

```bash
git config --global core.autocrlf true
```

Thành viên Linux hoặc macOS có thể đặt:

```bash
git config --global core.autocrlf input
```

Các file được quy định `eol=lf` hoặc `eol=crlf` sẽ tuân theo chính sách trong repository. Cấu hình local là lớp hỗ trợ cho các file chưa có quy tắc cụ thể.

Sau khi clone, mỗi thành viên kiểm tra:

```bash
git check-attr text eol -- src/main/java/example/App.java
git ls-files --eol -- src/main/java/example/App.java scripts/deploy.sh scripts/deploy.bat
```

Kết quả nên thể hiện index đã chuẩn hóa và working tree dùng kiểu xuống dòng theo từng loại file. Nếu một thành viên thấy nhiều file thay đổi ngay sau checkout, hãy kiểm tra cấu hình và thuộc tính trước khi stage hoặc commit.

## 11. Những nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu đúng |
| --- | --- |
| `core.autocrlf` là chính sách dùng chung của repository | Đây là cấu hình local; chính sách theo file nên được chia sẻ qua `.gitattributes` |
| `core.eol` tự chuẩn hóa mọi file | Nó điều khiển kiểu checkout cho file text khi áp dụng; thuộc tính xác định file nào được xử lý |
| `text` và `eol` giống nhau | `text` bật chuẩn hóa; `eol` chỉ định kiểu checkout cụ thể |
| Git luôn lưu CRLF trên Windows | File text được chuẩn hóa có thể lưu LF trong blob dù working tree dùng CRLF |
| Chỉ cần đổi cấu hình là lịch sử cũ được chuẩn hóa | Cần áp dụng lại quy tắc cho file tracked bằng `git add --renormalize .` |
| File ảnh có thể dùng `text=auto` an toàn | File nhị phân nên được đánh dấu `-text` hoặc `binary` |
| `core.safecrlf` tự sửa file có line ending hỗn hợp | Nó cảnh báo hoặc từ chối một số chuyển đổi; người dùng vẫn cần kiểm tra và xử lý file |
| `git diff` lớn luôn là thay đổi logic | Có thể là khác biệt line ending; kiểm tra bằng `git ls-files --eol` và diff bỏ qua EOL |

## 12. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân có thể có | Cách kiểm tra hoặc xử lý |
| --- | --- | --- |
| Sau checkout, rất nhiều file báo modified | Cấu hình `autocrlf` không nhất quán hoặc thuộc tính thay đổi | Xem `git config --show-origin`, `git check-attr`, `git ls-files --eol` |
| Commit tạo diff toàn bộ file | Line ending trong working tree khác cách lưu hiện tại | Thêm chính sách `.gitattributes`, chuẩn hóa và review riêng |
| Script shell báo lỗi ký tự `^M` | File script đang có CRLF ở môi trường cần LF | Đặt `*.sh text eol=lf`, chuẩn hóa và kiểm tra lại |
| File nhị phân bị thay đổi ngoài ý muốn | File bị xử lý như text | Đặt `-text` hoặc `binary` cho loại file đó |
| Git cảnh báo safecrlf | Chuyển đổi có thể không đảo ngược hoặc file có line ending hỗn hợp | Kiểm tra byte, thuộc tính và nội dung trước khi stage |
| `git add --renormalize .` tạo diff lớn | Chính sách mới đang thay đổi nhiều file hoặc có file không đồng nhất | Kiểm tra phạm vi, thuộc tính, nội dung và tách commit chuẩn hóa |
| Máy cá nhân có cấu hình khác thành viên khác | Khác biệt ở global/local config | Dùng `.gitattributes` làm chính sách dự án và kiểm tra cấu hình local |

Nếu muốn xem một file cụ thể có bị chuyển đổi không, có thể xem thuộc tính và trạng thái EOL:

```bash
git check-attr --all -- path/to/file
git ls-files --eol -- path/to/file
```

Để xác định nội dung trong blob đang lưu, có thể xuất blob ra file tạm hoặc xem byte bằng công cụ phù hợp. Không nên kết luận chỉ dựa trên cách trình soạn thảo hiển thị dòng.

## 13. `.gitattributes` và `.editorconfig` phối hợp ra sao?

`.gitattributes` điều khiển cách Git xử lý nội dung khi add, checkout, diff và merge. `.editorconfig` hướng dẫn trình soạn thảo cách tạo hoặc định dạng file khi người dùng chỉnh sửa, ví dụ kiểu kết thúc dòng, charset và thụt lề.

Ví dụ `.editorconfig`:

```ini
root = true

[*]
charset = utf-8
end_of_line = lf
insert_final_newline = true

[*.bat]
end_of_line = crlf
```

Hai file nên nhất quán: `.gitattributes` quy định chuẩn khi lưu/chia sẻ qua Git; `.editorconfig` giúp editor tạo file đúng chuẩn ngay từ đầu. Editor không thay thế bộ quy tắc Git, và Git cũng không bảo đảm mọi editor tuân theo `.gitattributes` khi người dùng đang nhập nội dung.

## 14. Thực hành

Thực hiện trên repository thử nghiệm có ít nhất một file văn bản và một file nhị phân:

1. Chạy `git config --show-origin --get core.autocrlf` và `git config --show-origin --get core.eol` để ghi nhận cấu hình hiện tại.
2. Chạy `git ls-files --eol` để xem line ending trong index và working tree.
3. Tạo `.gitattributes` với `* text=auto`, một quy tắc `eol=lf`, một quy tắc `eol=crlf` và một quy tắc `-text`.
4. Dùng `git check-attr --all -- <file>` để kiểm tra từng quy tắc.
5. Stage `.gitattributes`, sau đó chạy `git add --renormalize .`.
6. Kiểm tra `git diff --cached --stat`, `git diff --cached --ignore-space-at-eol` và `git ls-files --eol`.
7. Xác nhận file nhị phân không bị chuẩn hóa và script có kiểu checkout phù hợp.
8. Commit riêng thay đổi chính sách và chuẩn hóa sau khi review.
9. Clone repository trong môi trường hoặc tài khoản có `core.autocrlf` khác và so sánh `git ls-files --eol`.

Sau thực hành, hãy giải thích vì sao blob trong Git có thể dùng LF trong khi working tree trên Windows dùng CRLF, và vì sao thuộc tính theo file giúp nhóm phối hợp ổn định hơn việc yêu cầu mọi người đặt cùng một giá trị `core.autocrlf`.

## 15. Tự kiểm tra kiến thức

1. LF và CRLF khác nhau ở byte nào?
2. `core.autocrlf=true`, `input` và `false` khác nhau ở bước add và checkout như thế nào?
3. `core.eol` điều khiển phần nào của quá trình chuyển đổi?
4. Thuộc tính `text` có tác dụng gì đối với nội dung trong index?
5. `eol=lf` và `eol=crlf` giúp giải quyết vấn đề gì?
6. Vì sao file nhị phân cần `-text` hoặc `binary`?
7. Dùng lệnh nào để xem thuộc tính áp dụng cho một file?
8. `git ls-files --eol` cho biết những thông tin gì?
9. Khi nào nên chạy `git add --renormalize .`?
10. `.gitattributes` và `.editorconfig` khác nhau như thế nào?

## Kết luận

`core.autocrlf` và `core.eol` điều khiển hành vi line ending trong môi trường local; `text` và `eol` trong `.gitattributes` xác định chính sách theo từng file và có thể chia sẻ cùng repository. Hãy chọn một chuẩn lưu trữ nhất quán, quy định rõ file cần LF hoặc CRLF, loại trừ file nhị phân khỏi chuẩn hóa, rồi kiểm tra bằng `git check-attr` và `git ls-files --eol`. Khi thay đổi chính sách cho repository đã tồn tại, dùng `git add --renormalize .` sau khi bảo vệ công việc hiện tại và review kỹ diff trước khi commit.
