# Phạm vi và thứ tự ưu tiên của thuộc tính tệp

Git attributes cho phép quy định cách Git xử lý từng loại tệp, chẳng hạn chuẩn hóa dòng kết thúc, hiển thị diff, hợp nhất nội dung hoặc áp dụng bộ lọc khi đưa dữ liệu vào và lấy dữ liệu ra khỏi repository. Một thuộc tính có thể được khai báo ở cấp toàn repository, trong một thư mục con, trong cấu hình riêng của repository hoặc trong file cấu hình dùng chung của người dùng. Hiểu phạm vi và thứ tự ưu tiên giúp bạn biết quy tắc nào đang có hiệu lực khi nhiều file cùng khai báo thuộc tính cho một đường dẫn.

## 1. Git attributes dùng để làm gì?

Git attributes là các quy tắc gắn thuộc tính với đường dẫn. Chúng thường được khai báo trong file `.gitattributes`. Git và một số công cụ tích hợp đọc các thuộc tính này để quyết định cách xử lý nội dung.

Một số thuộc tính thường gặp:

| Thuộc tính | Tác dụng khái quát |
|---|---|
| `text` | Điều khiển việc chuẩn hóa dòng kết thúc khi đưa nội dung vào Git |
| `eol` | Chỉ định kiểu dòng kết thúc trong working tree, thường là `lf` hoặc `crlf` |
| `diff` | Điều khiển cách Git tạo diff cho loại tệp |
| `merge` | Chỉ định hành vi hoặc driver khi hợp nhất tệp |
| `filter` | Chỉ định bộ lọc clean/smudge khi dữ liệu đi vào hoặc ra khỏi repository |
| `working-tree-encoding` | Khai báo encoding của tệp trong working tree để Git chuyển đổi khi lưu và lấy nội dung |
| `ident` | Cho phép mở rộng dấu `$Id$` theo cơ chế của Git |
| `export-ignore` | Loại đường dẫn khỏi archive được tạo bằng `git archive` |
| `export-subst` | Cho phép thay thế một số placeholder khi tạo archive |

Ví dụ file `.gitattributes` ở thư mục gốc:

```gitattributes
* text=auto
*.sh text eol=lf
*.bat text eol=crlf
*.png binary
```

Trong ví dụ này, Git tự nhận diện và chuẩn hóa nội dung văn bản theo `text=auto`; file shell được checkout với LF, file batch với CRLF, còn file PNG được xử lý như dữ liệu nhị phân. `binary` là macro attribute dựng sẵn, tương đương với việc tắt xử lý text, diff và merge thông thường (`-text -diff -merge`).

Attributes áp dụng cho đường dẫn trong repository, kể cả tệp đã tracked và tệp chưa tracked khi Git cần xác định thuộc tính. Chúng không quyết định một tệp có được đưa vào commit hay không; đó là vai trò của index và quy tắc ignore.

## 2. Phân biệt `.gitattributes` với `.gitignore`

Hai file có cú pháp pattern gần nhau nhưng giải quyết hai vấn đề khác nhau:

| File | Mục đích | Ví dụ |
|---|---|---|
| `.gitignore` | Bỏ qua tệp chưa được theo dõi để Git không liên tục liệt kê chúng như untracked | `build/`, `.env.local` |
| `.gitattributes` | Gán thuộc tính để Git xử lý nội dung hoặc đường dẫn theo quy tắc xác định | `*.sh text eol=lf` |

Thêm một đường dẫn vào `.gitignore` không tự động ngừng theo dõi tệp đã được commit. Tương tự, gán `-text` trong `.gitattributes` không làm tệp biến mất khỏi `git status` hoặc loại tệp khỏi repository.

Một repository có thể dùng cả hai file cho cùng loại đường dẫn. Ví dụ, `.gitignore` bỏ qua thư mục `build/`, còn `.gitattributes` quy định cách xử lý các file văn bản được theo dõi trong `src/`.

## 3. Các vị trí có thể khai báo attributes

Git có thể đọc thuộc tính từ nhiều nguồn. Những nguồn quan trọng gồm:

1. **`$GIT_DIR/info/attributes`**: file riêng của repository hiện tại, có độ ưu tiên cao nhất. Thường dùng cho quy tắc local không muốn commit hoặc chia sẻ với nhóm.
2. **`.gitattributes` trong repository**: file ở cùng thư mục với đường dẫn hoặc ở các thư mục cha. File càng gần đường dẫn được xét thì càng có độ ưu tiên cao.
3. **File attributes toàn cục của người dùng**: đường dẫn được cấu hình bằng `core.attributesFile`, dùng làm quy tắc mặc định cho các repository của người dùng đó.
4. **File attributes cấp hệ thống**: quy tắc mặc định ở cấp cài đặt Git, có độ ưu tiên thấp nhất.

Thứ tự này được xét từ ưu tiên cao xuống thấp. Vì vậy, quy tắc local trong `info/attributes` có thể ghi đè quy tắc trong `.gitattributes` của dự án; quy tắc trong dự án có thể ghi đè quy tắc toàn cục hoặc cấp hệ thống.

File `.gitattributes` được commit vào repository nên có thể chia sẻ với mọi thành viên. `info/attributes` và file attributes toàn cục thường không được commit cùng dự án, vì vậy chúng phù hợp cho ngoại lệ riêng của máy hoặc người dùng.

## 4. Phạm vi của `.gitattributes` theo thư mục

Một file `.gitattributes` áp dụng cho đường dẫn nằm trong thư mục chứa file đó và các thư mục con theo quy tắc pattern. Khi Git xét một đường dẫn, nó đọc `.gitattributes` ở thư mục của đường dẫn trước, sau đó đi dần lên các thư mục cha.

Ví dụ cấu trúc:

```text
project/
  .gitattributes
  src/
    .gitattributes
    main/
      App.java
    vendor/
      .gitattributes
      Legacy.java
  docs/
    Guide.md
```

Giả sử các file khai báo:

`project/.gitattributes`

```gitattributes
*.txt text eol=lf
```

`project/src/.gitattributes`

```gitattributes
*.txt eol=crlf
```

`project/src/vendor/.gitattributes`

```gitattributes
*.txt -text
```

Với `src/vendor/notes.txt`, Git xét file gần đường dẫn nhất trước. `-text` từ `src/vendor/.gitattributes` có thể ghi đè trạng thái `text` được khai báo ở cấp cha. Với `src/notes.txt`, quy tắc ở `src/.gitattributes` ghi đè `eol=lf` của file gốc nhưng vẫn có thể giữ thuộc tính `text` được kế thừa từ file gốc vì hai dòng đang tác động tới hai thuộc tính khác nhau.

Một file `.gitattributes` trong thư mục con không ảnh hưởng ngược lên thư mục cha hoặc thư mục ngang hàng. Ví dụ, `src/.gitattributes` không thay đổi cách Git xử lý `docs/Guide.md`.

## 5. Thứ tự ưu tiên khi nhiều nguồn cùng khai báo

Khi nhiều nguồn gán giá trị cho cùng một thuộc tính của cùng một đường dẫn, nguồn có độ ưu tiên cao hơn sẽ quyết định kết quả. Trong nhóm `.gitattributes` của repository, file gần đường dẫn hơn có ưu tiên cao hơn file ở thư mục cha.

Thứ tự khái quát:

```text
$GIT_DIR/info/attributes             cao nhất
          |
          v
<dir-của-file>/.gitattributes
          |
          v
<thư-mục-cha>/.gitattributes
          |
          v
<thư-mục-gốc>/.gitattributes
          |
          v
core.attributesFile (user/global)
          |
          v
attributes cấp hệ thống              thấp nhất
```

Ví dụ, file gốc khai báo:

```gitattributes
*.md text eol=lf
```

File `docs/.gitattributes` khai báo:

```gitattributes
*.md eol=crlf
```

Với `docs/Guide.md`, thuộc tính `text` vẫn có thể là `set`, trong khi `eol` là `crlf`. Git giải quyết theo từng thuộc tính, không phải chọn nguyên một dòng hoặc một file làm kết quả duy nhất.

## 6. Thứ tự các dòng trong cùng một file

Nếu nhiều pattern trong cùng một file cùng khớp với một đường dẫn, dòng xuất hiện sau có thể ghi đè giá trị do dòng trước đặt. Việc ghi đè được thực hiện theo từng thuộc tính.

Ví dụ:

```gitattributes
*.txt text eol=lf
generated/*.txt -text
generated/keep.txt text
```

- Với `notes.txt`, dòng đầu đặt `text` và `eol=lf`.
- Với `generated/output.txt`, dòng thứ hai đặt `text` thành unset; thuộc tính `eol` từ dòng đầu không bị thay đổi bởi dòng thứ hai.
- Với `generated/keep.txt`, dòng cuối đặt lại `text` thành set.

Khi có nhiều quy tắc, hãy đọc tất cả pattern khớp và xác định thuộc tính nào bị ghi đè. Không nên giả định rằng dòng sau xóa toàn bộ hiệu lực của dòng trước.

## 7. Bốn trạng thái của một thuộc tính

Một thuộc tính có thể ở một trong bốn trạng thái:

| Cách viết | Trạng thái | Ý nghĩa |
|---|---|---|
| `text` | Set | Thuộc tính được bật |
| `-text` | Unset | Thuộc tính bị tắt |
| `eol=lf` | Value | Thuộc tính có giá trị chuỗi cụ thể |
| `!text` | Unspecified | Đặt thuộc tính về trạng thái không xác định |

Ví dụ:

```gitattributes
*.txt text
archive/*.txt -text
archive/legacy.txt !text
```

`archive/legacy.txt` có trạng thái `text` là unspecified do dòng cuối đặt lại trạng thái thuộc tính. `!text` khác với `-text`: `-text` khẳng định tắt thuộc tính, còn `!text` đánh dấu thuộc tính không được chỉ định trong kết quả.

Lưu ý: `!text` là cú pháp trạng thái của thuộc tính. Nó không phải pattern phủ định đường dẫn. Pattern phủ định kiểu `!path` không được phép dùng trong `.gitattributes`; muốn điều chỉnh ngoại lệ, hãy viết pattern cụ thể hơn và đặt trạng thái thuộc tính tương ứng.

## 8. Cách viết pattern và phạm vi khớp

Pattern trong `.gitattributes` được diễn giải tương đối với thư mục chứa file `.gitattributes` đó. Các quy tắc gần giống `.gitignore`, nhưng có một số điểm cần nhớ:

- Pattern không có dấu `/` thường khớp tên tệp ở các cấp bên dưới thư mục chứa `.gitattributes`.
- Pattern có dấu `/` được xét tương đối từ thư mục chứa file `.gitattributes`.
- `*` khớp một phần tên trong một thành phần đường dẫn; `**` có thể khớp qua nhiều cấp thư mục.
- Pattern phủ định bắt đầu bằng `!` không được hỗ trợ trong `.gitattributes`.
- Pattern khớp một thư mục không tự động áp dụng đệ quy cho mọi tệp bên trong thư mục đó; dùng dạng như `directory/**` nếu muốn khớp nội dung bên dưới.

Ví dụ:

```gitattributes
*.java text
src/generated/** -text
docs/*.md text eol=lf
```

`*.java` có thể áp dụng cho file Java ở các cấp dưới file `.gitattributes`. `src/generated/**` giới hạn quy tắc vào nội dung trong thư mục sinh tự động. `docs/*.md` giới hạn vào các file Markdown nằm trực tiếp trong thư mục `docs` tương ứng với vị trí file `.gitattributes`.

Nếu cần ngoại lệ cho một tệp, hãy thêm pattern cụ thể sau pattern tổng quát:

```gitattributes
*.sh text eol=lf
scripts/vendor/*.sh -text
```

Điều này giúp quy tắc dễ đọc và dễ kiểm tra hơn so với việc tạo nhiều pattern rộng chồng lấn.

## 9. Cấu hình file attributes toàn cục

Bạn có thể khai báo thuộc tính mặc định dùng cho các repository của riêng mình bằng cấu hình `core.attributesFile`:

```bash
git config --global core.attributesFile <path-to-global-attributes-file>
```

Sau đó tạo file tại đường dẫn đã cấu hình, ví dụ:

```gitattributes
*.psd -text -diff
*.docx -text -diff
```

Quy tắc toàn cục hữu ích khi bạn muốn xử lý một số định dạng giống nhau trong mọi repository local. Tuy nhiên, vì nó không được commit trong dự án nên đồng đội có thể không có cùng quy tắc. Những yêu cầu định dạng cần thống nhất cho cả nhóm nên được khai báo trong `.gitattributes` của repository.

Kiểm tra cấu hình và nguồn file:

```bash
git config --show-origin --get core.attributesFile
git rev-parse --git-path info/attributes
```

Lệnh đầu hiển thị nguồn cấu hình `core.attributesFile` nếu đã được đặt. Lệnh thứ hai cho biết vị trí file `info/attributes` trong repository hiện tại. Bạn có thể đọc hai file này để tìm quy tắc local hoặc global đang ảnh hưởng tới đường dẫn.

## 10. Dùng `info/attributes` cho ngoại lệ riêng của repository

File `$GIT_DIR/info/attributes` có độ ưu tiên cao nhất trong các nguồn attributes. Nó phù hợp khi bạn cần ghi đè quy tắc của dự án chỉ trên máy hiện tại, chẳng hạn để thử một diff driver hoặc tắt một bộ lọc trong quá trình điều tra.

Ví dụ nội dung:

```gitattributes
large-data/sample.csv -diff
```

Quy tắc này có thể ghi đè cấu hình `.gitattributes` đã commit cho đường dẫn `large-data/sample.csv` trong repository hiện tại. Thành viên khác không nhận được quy tắc này khi clone hoặc pull vì file `info/attributes` không thuộc lịch sử commit.

Do có độ ưu tiên cao, một quy tắc cũ trong `info/attributes` có thể khiến bạn tưởng rằng `.gitattributes` trong dự án không hoạt động. Khi kết quả không như mong đợi, hãy kiểm tra file này trước khi chỉnh sửa quy tắc chung của nhóm.

## 11. Kiểm tra thuộc tính thực tế bằng `git check-attr`

Không cần đoán nguồn nào đang có hiệu lực. Dùng `git check-attr` để hỏi Git trạng thái thuộc tính của một đường dẫn:

```bash
git check-attr text eol diff merge filter -- src/main/App.java
```

Kết quả cho biết từng thuộc tính là `set`, `unset`, giá trị cụ thể hoặc `unspecified`. Để liệt kê các thuộc tính đang được gán cho đường dẫn:

```bash
git check-attr --all -- src/main/App.java
```

Nếu muốn kiểm tra thuộc tính theo nội dung trong index thay vì file `.gitattributes` trong working tree, dùng:

```bash
git check-attr --cached text eol diff -- src/main/App.java
```

Tùy chọn `--cached` hữu ích khi bạn vừa sửa `.gitattributes` nhưng chưa stage và muốn biết index hiện tại đang quy định điều gì. Kết quả của `git check-attr` cho biết trạng thái cuối cùng; để tìm nguồn khai báo, hãy kiểm tra `.gitattributes` từ thư mục gần file lên thư mục gốc, `info/attributes` và file toàn cục.

## 12. Ví dụ tổng hợp: chuẩn hóa dòng kết thúc theo thư mục

Giả sử dự án Java có cấu trúc:

```text
project/
  .gitattributes
  src/
    .gitattributes
    main/App.java
    generated/Model.java
  docs/
    .gitattributes
    Guide.md
```

File gốc:

```gitattributes
* text=auto
*.java text eol=lf
*.md text eol=lf
```

File `src/.gitattributes`:

```gitattributes
generated/** -text
```

File `docs/.gitattributes`:

```gitattributes
*.md eol=crlf
```

Kết quả mong muốn:

- `src/main/App.java` nhận `text` và `eol=lf` từ file gốc.
- `src/generated/Model.java` có `text` bị unset bởi quy tắc gần hơn trong `src/.gitattributes`.
- `docs/Guide.md` vẫn có `text` được bật từ file gốc, còn `eol` được ghi đè thành `crlf` từ `docs/.gitattributes`.

Kiểm tra từng đường dẫn:

```bash
git check-attr text eol -- src/main/App.java
git check-attr text eol -- src/generated/Model.java
git check-attr text eol -- docs/Guide.md
```

Nếu kết quả không đúng như dự kiến, kiểm tra thêm `info/attributes` và `core.attributesFile`, bởi hai nguồn này có thể ghi đè các file trong repository.

## 13. Những nhầm lẫn thường gặp

- **Cho rằng `.gitattributes` chỉ có một file ở thư mục gốc.** Git có thể đọc file ở nhiều thư mục; file gần đường dẫn hơn có ưu tiên cao hơn.
- **Cho rằng một dòng ghi đè toàn bộ thuộc tính trước đó.** Việc ghi đè diễn ra theo từng thuộc tính; thuộc tính không bị tác động vẫn giữ giá trị đã được xác định.
- **Nhầm `!attr` với `-attr`.** Một trạng thái là unspecified, trạng thái kia là unset.
- **Dùng pattern phủ định như `.gitignore`.** Pattern phủ định đường dẫn không được hỗ trợ trong `.gitattributes`.
- **Quên `info/attributes`.** Đây là nguồn có ưu tiên cao nhất và có thể làm quy tắc dự án dường như không có tác dụng.
- **Đặt yêu cầu chung của nhóm trong file attributes toàn cục.** Thành viên khác không tự nhận được cấu hình local đó; hãy đưa quy tắc chung vào repository.
- **Dùng `.gitattributes` để bỏ qua tệp.** Việc bỏ qua tệp chưa tracked thuộc `.gitignore`; attributes điều khiển cách Git xử lý đường dẫn.
- **Không kiểm tra index sau khi sửa `.gitattributes`.** Working tree và index có thể chứa hai phiên bản quy tắc khác nhau; dùng `git check-attr --cached` khi cần kiểm tra phiên bản đã stage.

## 14. Quy trình xác định thuộc tính đang có hiệu lực

Khi một tệp được xử lý khác với mong đợi, hãy làm theo trình tự:

1. Xác định đường dẫn repository tương đối và các thuộc tính cần kiểm tra.
2. Chạy `git check-attr` cho đường dẫn đó để xem trạng thái cuối cùng.
3. Đọc `.gitattributes` trong thư mục của tệp, sau đó lần lượt kiểm tra các thư mục cha.
4. Kiểm tra `$GIT_DIR/info/attributes` vì file này có độ ưu tiên cao nhất.
5. Kiểm tra `core.attributesFile` và quy tắc cấp hệ thống nếu vẫn chưa tìm được nguồn.
6. Xem thứ tự các pattern khớp trong từng file; dòng sau có thể ghi đè dòng trước theo từng thuộc tính.
7. Nếu quy tắc vừa sửa chưa stage, so sánh kết quả working tree với index bằng `git check-attr --cached`.
8. Sau khi điều chỉnh, kiểm tra lại thuộc tính và xác nhận hành vi thực tế như diff, line ending hoặc filter.

## 15. Ghi nhớ

Git attributes được hợp nhất từ nhiều nguồn theo thứ tự ưu tiên: `info/attributes` cao nhất, tiếp đến `.gitattributes` gần đường dẫn rồi các file ở thư mục cha, sau đó là file attributes toàn cục và cấp hệ thống. Trong một file, pattern khớp sau có thể ghi đè thuộc tính của pattern trước; việc ghi đè diễn ra riêng cho từng thuộc tính. Dùng `git check-attr` để xem kết quả Git thực sự áp dụng, đồng thời phân biệt rõ quy tắc dùng chung trong repository với ngoại lệ local của từng máy.
