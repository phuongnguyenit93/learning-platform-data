# Kiểm tra thuộc tính hiệu lực bằng git check-attr

File `.gitattributes` cho phép repository quy định Git xử lý từng loại file như thế nào. Thuộc tính có thể điều khiển chuẩn hóa line ending, cách nhận diện file nhị phân, diff, merge hoặc bộ lọc nội dung. Khi kết quả không như mong đợi, bạn cần biết thuộc tính nào đang có hiệu lực đối với một đường dẫn cụ thể.

Lệnh `git check-attr` trả lời câu hỏi đó. Nó tính toán giá trị thuộc tính theo các quy tắc và nguồn cấu hình Git đang áp dụng, rồi hiển thị kết quả cho đường dẫn được yêu cầu. Lệnh này đặc biệt hữu ích khi nhiều file `.gitattributes` hoặc cấu hình attributes cùng tác động đến một file.

## 1. Thuộc tính Git là gì?

Attribute là một cặp tên và trạng thái/giá trị gắn với đường dẫn. Git dùng các attribute này để quyết định cách xử lý nội dung file trong một số thao tác.

Một dòng trong `.gitattributes` có dạng tổng quát:

```text
<pattern> <attribute> <attribute>...
```

Ví dụ:

```gitattributes
*.sh text eol=lf
*.bat text eol=crlf
*.png -text
*.md diff=markdown
```

Trong ví dụ trên:

- File shell được xử lý như văn bản và dùng LF trong working tree.
- File batch được xử lý như văn bản và dùng CRLF trong working tree.
- File PNG tắt chuẩn hóa text vì là dữ liệu nhị phân.
- File Markdown được gán diff driver tên `markdown` nếu driver đó được cấu hình.

Git không yêu cầu mọi attribute đều phải là thuộc tính dựng sẵn. Một số attribute như `text`, `eol`, `diff`, `merge`, `filter`, `export-ignore` có ý nghĩa đặc biệt với Git; những tên khác có thể được công cụ hoặc script của dự án sử dụng.

## 2. Cú pháp gán attribute

Một attribute có thể ở một trong bốn trạng thái:

| Cách viết trong `.gitattributes` | Ý nghĩa | Kết quả thường thấy từ `git check-attr` |
|---|---|---|
| `text` | Bật attribute | `text: set` |
| `-text` | Tắt attribute | `text: unset` |
| `text=auto` | Gán giá trị chuỗi `auto` | `text: auto` |
| `!text` | Đưa attribute về trạng thái unspecified | `text: unspecified` |

Nếu không có quy tắc nào gán attribute, trạng thái của nó cũng là `unspecified`. Trạng thái unspecified khác với unset: unset là một quyết định rõ ràng tắt attribute, còn unspecified nghĩa là attribute không có giá trị được gán. Khi viết `!text`, bạn chủ động đặt attribute về trạng thái unspecified để hủy giá trị được gán bởi quy tắc có độ ưu tiên thấp hơn.

Ví dụ:

```gitattributes
*.txt text
*.bin -text
special.txt !text
*.dat encoding=utf-8
```

`special.txt` được đặt lại trạng thái `text` thành unspecified ở dòng cuối cùng khớp với file đó. `encoding=utf-8` là attribute có giá trị tùy chỉnh; Git chỉ tự xử lý nó nếu có cơ chế hoặc công cụ hiểu attribute đó.

Trong một file `.gitattributes`, quy tắc khớp xuất hiện sau có thể ghi đè trạng thái attribute được đặt bởi quy tắc khớp trước đó. Việc ghi đè diễn ra theo từng attribute, không nhất thiết thay thế toàn bộ các attribute trên dòng trước.

## 3. Lệnh git check-attr cơ bản

Cú pháp thông dụng:

```bash
git check-attr <attribute>... -- <path>...
```

Ví dụ kiểm tra hai attribute `text` và `eol` của file shell:

```bash
git check-attr text eol -- scripts/deploy.sh
```

Kết quả minh họa:

```text
scripts/deploy.sh: text: set
scripts/deploy.sh: eol: lf
```

Mỗi dòng thể hiện đường dẫn, tên attribute và giá trị hiệu lực. Giá trị có thể là `set`, `unset`, `unspecified` hoặc một chuỗi được gán, chẳng hạn `lf`, `crlf`, `auto` hay tên filter.

Kiểm tra nhiều file cùng lúc:

```bash
git check-attr text eol -- scripts/deploy.sh scripts/build.bat
```

Kiểm tra tất cả attribute đang được gán cho một file:

```bash
git check-attr --all -- assets/logo.png
```

`--all` hữu ích khi bạn chưa biết file đang chịu ảnh hưởng bởi những attribute nào. Lệnh chỉ liệt kê các attribute có giá trị được gán; để hỏi rõ một attribute cụ thể và nhận cả trạng thái `unspecified`, hãy nêu tên attribute đó:

```bash
git check-attr text eol filter diff merge -- assets/logo.png
```

Đặt `--` trước danh sách đường dẫn để phân tách rõ tên attribute/tùy chọn với path. Điều này cũng tránh nhầm tên file bắt đầu bằng dấu gạch ngang với tùy chọn của lệnh.

## 4. Đọc kết quả và xác định thuộc tính đang có hiệu lực

Giả sử file `.gitattributes` ở gốc repository có nội dung:

```gitattributes
* text=auto
*.sh text eol=lf
*.bat text eol=crlf
*.png -text
*.jpg binary
```

Kiểm tra các file:

```bash
git check-attr text eol -- README.md
git check-attr text eol -- scripts/deploy.sh
git check-attr text eol -- scripts/build.bat
git check-attr text diff merge -- images/logo.jpg
```

Kết quả có thể có dạng:

```text
README.md: text: auto
README.md: eol: unspecified
scripts/deploy.sh: text: set
scripts/deploy.sh: eol: lf
scripts/build.bat: text: set
scripts/build.bat: eol: crlf
images/logo.jpg: text: unset
images/logo.jpg: diff: unset
images/logo.jpg: merge: unset
```

Trong ví dụ, `binary` là macro attribute dựng sẵn tương đương với việc tắt `diff`, `merge` và `text`. Nếu bạn kiểm tra `text`, `diff` và `merge`, Git hiển thị các trạng thái unset tương ứng.

Đừng chỉ nhìn vào file `.gitattributes` ở thư mục gốc rồi kết luận. Một file `.gitattributes` gần file hơn có thể ghi đè quy tắc ở thư mục cha; ngoài ra, cấu hình local hoặc global cũng có thể tham gia. `git check-attr` giúp nhìn kết quả sau khi Git áp dụng thứ tự ưu tiên.

## 5. Các nguồn attribute và thứ tự ưu tiên

Git có thể đọc attribute từ nhiều nơi. Theo thứ tự ưu tiên từ cao xuống thấp:

1. `$GIT_DIR/info/attributes` của repository hiện tại.
2. Các file `.gitattributes` trong thư mục chứa file và các thư mục cha, với file gần đường dẫn hơn có ưu tiên cao hơn file ở thư mục cha.
3. File attributes toàn cục được chỉ định bởi cấu hình `core.attributesFile`.
4. File attributes cấp hệ thống, nếu được cài đặt.

Trong cùng một file `.gitattributes`, quy tắc khớp sau có thể ghi đè attribute do quy tắc khớp trước đặt ra. Giữa các file khác nhau, nguồn có ưu tiên cao hơn sẽ thắng nguồn thấp hơn đối với attribute được gán.

Ví dụ cấu trúc:

```text
repository/
|-- .gitattributes
|-- src/
|   |-- .gitattributes
|   `-- main.c
`-- .git/
    `-- info/
        `-- attributes
```

Nếu cả bốn nguồn cùng đặt attribute `diff` cho `src/main.c`, cấu hình trong `.git/info/attributes` có ưu tiên cao nhất. Nếu không có quy tắc ở đó, `.gitattributes` trong `src/` có ưu tiên cao hơn file ở gốc repository.

### Kiểm tra cấu hình attributes toàn cục

Xem cấu hình `core.attributesFile` cùng nguồn khai báo:

```bash
git config --show-origin --get-all core.attributesFile
```

Nếu lệnh không trả về kết quả, có thể chưa cấu hình file attributes toàn cục tường minh. Git vẫn có thể sử dụng đường dẫn mặc định theo môi trường. Cấu hình này khác với `.gitignore` toàn cục; `core.excludesFile` là thiết lập riêng cho ignore rules.

### Kiểm tra file local info/attributes

`$GIT_DIR/info/attributes` có ưu tiên cao nhưng không được commit cùng repository. Nó hữu ích cho ngoại lệ chỉ áp dụng trên máy hiện tại, nhưng cũng có thể khiến kết quả giữa hai máy khác nhau. Khi attribute có vẻ bất ngờ, hãy nhớ kiểm tra nguồn local này.

## 6. Kiểm tra attributes trong working tree, index và commit

Trong lúc chỉnh sửa, nội dung `.gitattributes` ở working tree có thể khác nội dung đã stage. Vì vậy, kết quả kiểm tra có thể thay đổi tùy nguồn attribute bạn muốn xem.

### Kiểm tra theo cấu hình hiện tại

Lệnh thông thường đọc các file `.gitattributes` đang có trong working tree cùng các nguồn attributes khác:

```bash
git check-attr text eol -- src/main.c
```

Đây là cách kiểm tra nhanh quy tắc đang có hiệu lực khi làm việc trên working tree.

### Kiểm tra nội dung `.gitattributes` đã stage

Nếu bạn vừa sửa `.gitattributes` và đã `git add`, có thể kiểm tra theo index:

```bash
git check-attr --cached text eol -- src/main.c
```

`--cached` yêu cầu Git dùng các file `.gitattributes` trong index thay vì bản trong working tree. Tùy chọn này hữu ích khi muốn biết cấu hình attributes sẽ đi cùng nội dung staged trong commit tiếp theo.

### Kiểm tra theo một commit hoặc tree cụ thể

Khi cần so sánh với một phiên bản đã commit, dùng `--source`:

```bash
git check-attr --source=HEAD text eol -- src/main.c
git check-attr --source=HEAD~1 text eol -- src/main.c
```

Lệnh đầu kiểm tra theo cây của `HEAD`; lệnh thứ hai kiểm tra theo commit cha. Cách này hữu ích khi tìm nguyên nhân một file từng có line ending hoặc diff behavior khác trước đây. `--source` có ở các phiên bản Git hiện đại; nếu Git báo tùy chọn không hợp lệ, xem `git check-attr -h` để xác nhận phiên bản và cú pháp hỗ trợ.

Ba cách kiểm tra trả lời ba câu hỏi khác nhau: working tree phản ánh thay đổi hiện tại, `--cached` phản ánh cấu hình đã stage, còn `--source` phản ánh cấu hình trong tree được chỉ định.

## 7. Những attribute thường cần kiểm tra

### `text` và `eol`: chuẩn hóa line ending

Ví dụ:

```gitattributes
* text=auto
*.sh text eol=lf
*.bat text eol=crlf
*.png -text
```

- `text` bật hoặc tắt xử lý chuẩn hóa nội dung văn bản khi Git đưa nội dung vào index.
- `text=auto` để Git tự nhận diện file văn bản phù hợp để chuẩn hóa.
- `eol=lf` yêu cầu LF trong working tree.
- `eol=crlf` yêu cầu CRLF trong working tree.
- `-text` tắt xử lý text cho file nhị phân.

Kiểm tra:

```bash
git check-attr text eol -- scripts/deploy.sh
git check-attr text eol -- scripts/build.bat
```

Nếu kết quả khác dự kiến, hãy xem các `.gitattributes` theo thư mục, `info/attributes`, `core.attributesFile` và cấu hình `core.autocrlf`. Attribute cho biết quy tắc được gán; trạng thái file hiện có trong index có thể vẫn cần được chuẩn hóa lại theo quy trình riêng, ví dụ stage lại file sau khi thay đổi quy tắc.

### `diff` và `merge`: cách Git so sánh và hợp nhất

Một số ví dụ:

```gitattributes
*.jpg binary
*.md diff=markdown
generated/** -diff -merge
```

- `diff` bật hành vi diff văn bản mặc định; `-diff` tắt diff văn bản thông thường cho đường dẫn đó.
- `diff=<driver>` chọn diff driver có tên, nếu driver được cấu hình.
- `merge` bật xử lý merge mặc định; `-merge` báo Git không dùng merge text thông thường cho file đó.
- `merge=<driver>` chọn merge driver tùy chỉnh nếu đã được cấu hình.

Kiểm tra:

```bash
git check-attr diff merge -- images/logo.jpg
git check-attr diff merge -- docs/guide.md
```

Kết quả chỉ cho biết attribute hiệu lực. Nó không xác nhận driver tùy chỉnh đã cài đặt đúng hoặc sẽ chạy thành công. Với driver tùy chỉnh, hãy kiểm tra thêm cấu hình tương ứng như `diff.<driver>.*` hoặc `merge.<driver>.*`.

### `filter`: bộ lọc clean/smudge

Attribute `filter` gắn một tên driver vào file:

```gitattributes
*.data filter=normalize-data
```

Driver có thể được cấu hình bằng các khóa như:

```bash
git config filter.normalize-data.clean "command-to-clean"
git config filter.normalize-data.smudge "command-to-smudge"
```

`clean` xử lý nội dung khi đưa file vào Git; `smudge` xử lý nội dung khi checkout ra working tree. Các bộ lọc có thể làm việc với định dạng dữ liệu hoặc tích hợp Git LFS. Kiểm tra attribute:

```bash
git check-attr filter -- datasets/sample.data
```

Nếu kết quả là `filter: normalize-data`, điều đó chỉ xác nhận tên filter được gán. Nó không chứng minh lệnh clean/smudge tồn tại hoặc chạy được. Hãy kiểm tra cấu hình filter và trạng thái công cụ bên ngoài.

### `export-ignore` và `export-subst`

Các attribute này tác động đến nội dung khi tạo archive bằng `git archive`:

```gitattributes
docs/internal-notes/** export-ignore
src/version.txt export-subst
```

`export-ignore` loại đường dẫn khỏi archive; `export-subst` cho phép thay thế một số placeholder commit trong nội dung file khi xuất archive. Kiểm tra:

```bash
git check-attr export-ignore export-subst -- docs/internal-notes/plan.md
git check-attr export-ignore export-subst -- src/version.txt
```

Những attribute này không xóa file khỏi repository và không phải quy tắc ignore khi Git hiển thị trạng thái working tree.

## 8. Phân biệt git check-attr với git check-ignore

Hai lệnh có tên gần giống nhau nhưng giải quyết hai vấn đề khác nhau:

| Lệnh | Câu hỏi | Ví dụ |
|---|---|---|
| `git check-attr` | Attribute nào đang có hiệu lực với đường dẫn? | `git check-attr text eol -- src/main.c` |
| `git check-ignore` | Quy tắc ignore nào khiến đường dẫn bị bỏ qua? | `git check-ignore -v build/output.log` |

`.gitattributes` điều khiển cách Git xử lý file; `.gitignore` điều khiển file untracked nào bị bỏ qua khi hiển thị trạng thái và xét add thông thường. Một file có thể được ignore nhưng vẫn có attributes, hoặc được tracked và vẫn chịu attributes. Hai cơ chế độc lập với nhau.

Ví dụ:

```bash
git check-ignore -v .env.local
git check-attr --all -- .env.local
```

Lệnh thứ nhất tìm quy tắc ignore; lệnh thứ hai hiển thị attributes được gán cho đường dẫn. Nếu file bị ignore, `git check-attr` vẫn có thể trả về attribute vì việc tra cứu attributes không đồng nghĩa với việc thêm file vào repository.

## 9. Quy trình tìm nguyên nhân attribute không như mong đợi

Khi Git xử lý một file sai line ending, diff hoặc filter, hãy kiểm tra theo thứ tự:

1. **Xác định đường dẫn chính xác.** Attribute được áp dụng theo path, nên hãy dùng đường dẫn tương đối từ gốc repository hoặc vị trí phù hợp.
2. **Liệt kê attribute hiệu lực.** Chạy `git check-attr --all -- <path>` để xem những attribute đang được gán.
3. **Hỏi trực tiếp attribute nghi ngờ.** Dùng `git check-attr text eol diff merge filter -- <path>` để thấy cả trạng thái unspecified.
4. **So sánh working tree với index.** Chạy thêm `git check-attr --cached ...` nếu `.gitattributes` đã được stage.
5. **So sánh với commit.** Dùng `--source=HEAD` hoặc commit khác để xác định quy tắc đã thay đổi ở đâu.
6. **Kiểm tra nguồn có ưu tiên cao.** Xem `.git/info/attributes`, các `.gitattributes` trong đường dẫn cha và `core.attributesFile`.
7. **Kiểm tra cấu hình driver/filter.** Nếu attribute có giá trị tên driver, xác minh driver tương ứng đã được cấu hình và công cụ bên ngoài sẵn sàng.

Ví dụ một nhóm lệnh chẩn đoán:

```bash
git check-attr --all -- src/main.c
git check-attr text eol diff merge filter -- src/main.c
git check-attr --cached text eol -- src/main.c
git check-attr --source=HEAD text eol -- src/main.c
git config --show-origin --get-all core.attributesFile
```

`git check-attr` hiển thị giá trị cuối cùng Git tính được nhưng không cho biết chính xác dòng nào trong file nào đã tạo ra giá trị đó. Khi cần truy nguồn, hãy tìm các quy tắc khớp trong từng `.gitattributes`, `info/attributes` và file attributes toàn cục theo thứ tự ưu tiên.

## 10. Bài tập thực hành

Trong một repository thử nghiệm, tạo file `.gitattributes` ở gốc với nội dung:

```gitattributes
* text=auto
*.sh text eol=lf
*.bat text eol=crlf
*.png -text
*.jpg binary
```

Tạo các file mẫu hoặc dùng những đường dẫn tương ứng trong dự án, rồi thực hiện:

1. Chạy `git check-attr text eol -- scripts/deploy.sh` và giải thích hai giá trị nhận được.
2. Chạy `git check-attr text eol -- scripts/build.bat` để xác nhận quy tắc CRLF.
3. Chạy `git check-attr --all -- images/logo.jpg` và giải thích macro `binary`.
4. Thêm một `.gitattributes` trong thư mục `scripts/` để ghi đè `eol` cho một file cụ thể, rồi kiểm tra lại.
5. Stage thay đổi `.gitattributes`, sửa tiếp bản working tree và so sánh `git check-attr` với `git check-attr --cached`.
6. Commit cấu hình, sau đó dùng `git check-attr --source=HEAD~1` để so sánh với phiên bản trước.
7. Giải thích vì sao `git check-attr` không thay thế `git check-ignore`.

Bạn hoàn thành bài tập khi xác định được attribute hiệu lực cho một đường dẫn, giải thích được nguồn ưu tiên nào quyết định kết quả và phân biệt được giá trị trong working tree, index và commit.
