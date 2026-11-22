# Chẩn đoán quy tắc bỏ qua bằng git check-ignore -v

Khi một tệp không xuất hiện trong `git status`, nguyên nhân thường gặp là tệp đang được một quy tắc ignore áp dụng. Quy tắc đó có thể nằm trong `.gitignore` ở thư mục gốc, một `.gitignore` lồng bên trong, `.git/info/exclude` hoặc file ignore toàn cục của người dùng. Nếu chỉ nhìn tên tệp hoặc nội dung `.gitignore` ở thư mục gốc, bạn có thể bỏ sót nguồn thực sự khiến Git bỏ qua đường dẫn.

Lệnh `git check-ignore -v` giúp xác định **nguồn quy tắc, số dòng, pattern và đường dẫn** đã khớp. Nhờ đó, bạn có thể tìm đúng file cần sửa, hiểu vì sao một tệp bị ignore hoặc vì sao một ngoại lệ `!pattern` chưa có tác dụng. Lệnh này chỉ chẩn đoán; nó không sửa `.gitignore`, không xóa tệp và không thay đổi index.

## 1. Vì sao cần chẩn đoán quy tắc ignore?

Trong dự án, Git thường bỏ qua những tệp sinh ra trong quá trình làm việc như output build, cache, log hoặc tệp cấu hình local. Ví dụ:

```gitignore
build/
*.log
.env.local
```

Các quy tắc này giúp tránh đưa tệp tạm hoặc dữ liệu riêng của máy phát triển vào commit. Tuy nhiên, khi một tệp mới không xuất hiện trong `git status`, bạn cần biết chính xác quy tắc nào đã loại nó ra.

Những tình huống thường gặp:

- Một tệp log bị bỏ qua nhưng bạn không biết quy tắc nằm ở `.gitignore` nào.
- Một quy tắc trong `.gitignore` lồng bên trong ghi đè quy tắc ở thư mục cha.
- Một tệp cần theo dõi bị khớp bởi pattern ignore quá rộng.
- Bạn đã thêm `!pattern` để giữ ngoại lệ nhưng Git vẫn bỏ qua tệp.
- Một tệp đã được commit trước đây nên việc thêm nó vào `.gitignore` không làm Git ngừng theo dõi.
- Tệp bị ignore bởi cấu hình toàn cục, dù repository không có quy tắc tương ứng.

`git check-ignore -v` giúp phân biệt các trường hợp này trước khi chỉnh sửa quy tắc.

## 2. Cú pháp cơ bản

Cú pháp thường dùng:

```bash
git check-ignore -v -- <path>...
```

Trong đó:

- `git check-ignore`: yêu cầu Git kiểm tra đường dẫn có bị ignore hay không.
- `-v` hoặc `--verbose`: hiển thị quy tắc đã khớp cùng nguồn và số dòng.
- `--`: kết thúc phần tùy chọn; các đối số phía sau được hiểu là đường dẫn.
- `<path>`: đường dẫn cần kiểm tra, thường được viết tương đối với thư mục hiện tại.

Ví dụ:

```bash
git check-ignore -v -- build/output.log
```

Output minh họa:

```text
.gitignore:12:build/    build/output.log
```

Kết quả cho biết:

| Thành phần | Ý nghĩa |
|---|---|
| `.gitignore` | File chứa quy tắc đã khớp; có thể là đường dẫn tương đối hoặc tuyệt đối tùy nguồn |
| `12` | Số dòng trong file chứa quy tắc |
| `build/` | Pattern ignore đã khớp với đường dẫn |
| `build/output.log` | Đường dẫn được kiểm tra |

Với file ignore toàn cục hoặc `.git/info/exclude`, cột nguồn sẽ chỉ đến file tương ứng. Đây là thông tin quan trọng nhất để biết cần chỉnh sửa ở đâu.

## 3. Đọc kết quả verbose

Khi chạy:

```bash
git check-ignore -v -- notes/debug.log
```

Bạn có thể nhận kết quả dạng:

```text
config/gitignore:8:*.log    notes/debug.log
```

Điều đó có nghĩa dòng 8 trong `config/gitignore` chứa pattern `*.log`, và pattern này đang bỏ qua `notes/debug.log`.

Nguồn quy tắc có thể là:

- `.gitignore` ở thư mục gốc repository.
- `.gitignore` trong một thư mục con, áp dụng cho thư mục đó và các thư mục bên dưới.
- `.git/info/exclude`, có hiệu lực trong repository hiện tại nhưng không được commit cùng dự án.
- File được cấu hình qua `core.excludesFile`, thường là file ignore dùng chung cho người dùng trên máy.

Vì vậy, nếu output chỉ ra một đường dẫn như `C:/Users/.../.config/git/ignore`, nguyên nhân có thể nằm trong cấu hình toàn cục chứ không phải repository. Đừng vội thêm ngoại lệ vào `.gitignore` của dự án trước khi kiểm tra nguồn này.

## 4. Quy tắc nào được ưu tiên khi có nhiều pattern?

Git có thể đọc nhiều nguồn ignore cùng lúc. Theo thứ tự ưu tiên từ cao xuống thấp:

1. Pattern truyền trực tiếp qua tùy chọn dòng lệnh ở những lệnh Git có hỗ trợ kiểu lọc này; `git check-ignore` tập trung chẩn đoán các nguồn ignore được cấu hình.
2. Các file `.gitignore` áp dụng cho đường dẫn. File ở thư mục sâu hơn có thể ghi đè file ở thư mục cha.
3. `$GIT_DIR/info/exclude` của repository hiện tại.
4. File ignore toàn cục được cấu hình bằng `core.excludesFile`.

Trong cùng một mức ưu tiên, pattern xuất hiện sau cùng có hiệu lực nếu nhiều pattern cùng khớp. Dấu `!` tạo một quy tắc phủ định để đưa đường dẫn ra khỏi nhóm bị ignore, miễn là các điều kiện về thư mục cha cho phép Git xét đến đường dẫn đó.

Ví dụ cấu trúc:

```text
project/
├── .gitignore
├── src/
│   └── .gitignore
└── logs/
    ├── app.log
    └── keep.log
```

Root `.gitignore` có thể chứa:

```gitignore
*.log
```

File `src/.gitignore` có thể thêm quy tắc riêng cho source code. Khi kiểm tra một đường dẫn trong `src/`, `git check-ignore -v` cho biết chính xác file và dòng nào quyết định kết quả. Quy tắc trong file con có thể tạo ngoại lệ hoặc bổ sung quy tắc cho phạm vi của nó.

## 5. Chẩn đoán pattern quá rộng

Giả sử bạn muốn theo dõi `reports/release.log`, nhưng repository có quy tắc:

```gitignore
*.log
```

Kiểm tra:

```bash
git check-ignore -v -- reports/release.log
```

Git sẽ chỉ ra dòng chứa `*.log`. Bạn có thể điều chỉnh pattern theo mục đích thực tế. Ví dụ, nếu chỉ muốn bỏ qua log trong thư mục `logs/`:

```gitignore
logs/*.log
```

Sau khi sửa, kiểm tra lại:

```bash
git check-ignore -v -- reports/release.log
git status --short -- reports/release.log
```

Nếu `check-ignore` không còn báo quy tắc khớp và tệp chưa được theo dõi, tệp có thể xuất hiện trong `git status` dưới dạng untracked. Nếu tệp đã được theo dõi, kết quả status sẽ phản ánh trạng thái tracked thay vì untracked.

Không nên thu hẹp pattern chỉ để làm một tệp xuất hiện mà chưa xem các đường dẫn khác đang phụ thuộc quy tắc đó. Một thay đổi trong `.gitignore` có thể ảnh hưởng nhiều thành viên và nhiều loại output của dự án.

## 6. Chẩn đoán quy tắc phủ định !pattern

Một pattern bắt đầu bằng `!` dùng để bỏ ngoại lệ cho một đường dẫn đã bị ignore bởi pattern khác.

Ví dụ, muốn bỏ qua log nói chung nhưng giữ lại một file:

```gitignore
*.log
!release.log
```

Nếu `release.log` nằm ở đúng phạm vi mà pattern áp dụng, quy tắc phủ định có thể đưa tệp trở lại trạng thái untracked để Git hiển thị trong status.

Kiểm tra kết quả:

```bash
git check-ignore -v -n -- release.log
```

Tùy chọn `-n` (`--non-matching`) yêu cầu hiển thị cả đường dẫn không bị ignore; nó hữu ích khi kiểm tra xem pattern phủ định có phải là quy tắc cuối cùng khớp hay không. Khi dùng cùng `-v`, bạn có thêm thông tin để phân tích nguồn và pattern. Với một đường dẫn không khớp quy tắc nào, trường pattern sẽ rỗng.

### Vì sao ngoại lệ không có tác dụng trong thư mục bị ignore?

Git không đi sâu vào một thư mục đã bị ignore để tìm các tệp con được phủ định. Ví dụ:

```gitignore
logs/
!logs/keep.log
```

Quy tắc `logs/` loại cả thư mục; Git không xét tiếp `logs/keep.log`, nên ngoại lệ có thể không hoạt động. Một cách tổ chức khác là ignore nội dung bên trong nhưng để thư mục có thể được duyệt:

```gitignore
logs/*
!logs/keep.log
```

Sau khi thay đổi, kiểm tra cả thư mục và tệp:

```bash
git check-ignore -v -n -- logs logs/keep.log
```

Nếu ngoại lệ nằm sâu hơn nhiều cấp, bạn có thể cần bỏ ignore cho từng thư mục cha để Git có thể đi xuống đến tệp cần giữ. Hãy dùng output của `check-ignore` để xác minh từng đường dẫn thay vì đoán theo thứ tự dòng.

## 7. Khi tệp đã được tracked nhưng vẫn khớp quy tắc ignore

Quy tắc ignore chủ yếu áp dụng cho tệp chưa được theo dõi. Khi một tệp đã nằm trong index và được commit, thêm pattern tương ứng vào `.gitignore` không tự động ngừng theo dõi tệp đó.

Ví dụ, `config/local.yml` đã được commit. Sau đó nhóm thêm:

```gitignore
config/local.yml
```

Tệp vẫn là tracked. Vì mặc định `git check-ignore` không báo các tệp đang được index theo dõi, lệnh sau có thể không in kết quả:

```bash
git check-ignore -v -- config/local.yml
```

Để kiểm tra xem có quy tắc ignore nào khớp nếu bỏ qua trạng thái index, dùng `--no-index`:

```bash
git check-ignore -v --no-index -- config/local.yml
```

`--no-index` yêu cầu Git không dùng index khi kiểm tra. Đây là tùy chọn chẩn đoán hữu ích khi bạn nghi ngờ tệp đã được add/commit trước khi quy tắc ignore được tạo.

Nếu mục tiêu thực sự là ngừng theo dõi tệp nhưng vẫn giữ bản local, thao tác đó cần được thực hiện riêng:

```bash
git rm --cached -- config/local.yml
```

Sau đó commit thay đổi index cùng quy tắc ignore phù hợp. `git rm --cached` bỏ tệp khỏi index nhưng giữ file trong working tree; hãy chắc chắn nhóm không còn cần theo dõi file đó trước khi commit.

## 8. Kiểm tra file ignore toàn cục và exclude cục bộ

Nếu `check-ignore -v` chỉ ra nguồn không nằm trong repository, hãy kiểm tra cấu hình:

```bash
git config --show-origin --get core.excludesFile
```

Lệnh cho biết giá trị `core.excludesFile` và nơi cấu hình đó được đặt. Nếu không có giá trị, Git có thể không dùng file ignore toàn cục được khai báo theo cách này.

Để xem quy tắc exclude cục bộ của repository, mở:

```text
.git/info/exclude
```

File này phù hợp cho các quy tắc riêng của máy/repository mà bạn không muốn commit vào `.gitignore` chung. Vì file không được chia sẻ như nội dung dự án, một thành viên khác có thể có kết quả ignore khác trên cùng repository.

Nếu muốn kiểm tra vị trí gốc repository trước khi tìm các file ignore:

```bash
git rev-parse --show-toplevel
```

Điều này giúp tránh chạy lệnh từ một thư mục khác rồi nhầm đường dẫn tương đối.

## 9. Kiểm tra nhiều đường dẫn và dùng trong script

Có thể truyền nhiều đường dẫn trong cùng một lần gọi:

```bash
git check-ignore -v -- build/app.jar coverage/index.html notes/todo.txt
```

Git in quy tắc cho những đường dẫn bị ignore. Nếu muốn nhìn cả các đường dẫn không bị ignore:

```bash
git check-ignore -v -n -- build/app.jar coverage/index.html notes/todo.txt
```

Với danh sách đường dẫn được đưa qua standard input:

```bash
git check-ignore -v --stdin
```

Mặc định, `--stdin` đọc mỗi đường dẫn trên một dòng. Nếu tên file có newline hoặc cần giao tiếp an toàn với script, dùng chế độ NUL:

```bash
git check-ignore -v -z --stdin
```

`-z` dùng ký tự NUL làm dấu phân cách để tránh nhầm tên tệp có dấu cách hoặc ký tự xuống dòng. Khi xử lý output của `-z`, script cũng phải đọc theo NUL thay vì tách theo dòng.

### Dùng mã thoát để kiểm tra có đường dẫn bị ignore

Mã thoát hữu ích khi tự động hóa:

- `0`: có ít nhất một đường dẫn được xác định là ignored.
- `1`: không có đường dẫn nào được xác định là ignored.
- `128`: xảy ra lỗi nghiêm trọng khi thực hiện lệnh.

Vì vậy, nếu dùng lệnh trong script, đừng coi mọi mã khác `0` là lỗi hệ thống; mã `1` có thể chỉ có nghĩa là không có đường dẫn nào bị ignore. Khi cần chẩn đoán từng đường dẫn, dùng `-v` để lấy nguồn và pattern thay vì chỉ dựa vào mã thoát.

## 10. Quy trình chẩn đoán thực tế

Giả sử file `config/dev-local.yml` không xuất hiện trong `git status`, nhưng bạn muốn xác định lý do.

```bash
# 1. Kiểm tra trạng thái, bao gồm các file ignored.
git status --short --ignored -- config/dev-local.yml

# 2. Tìm nguồn, số dòng và pattern đã khớp.
git check-ignore -v -- config/dev-local.yml

# 3. Nếu tệp đã tracked, kiểm tra quy tắc mà không xét index.
git check-ignore -v --no-index -- config/dev-local.yml

# 4. Nếu không thấy kết quả, yêu cầu hiển thị cả trường hợp không khớp.
git check-ignore -v -n -- config/dev-local.yml

# 5. Xem nguồn ignore toàn cục nếu output trỏ đến cấu hình người dùng.
git config --show-origin --get core.excludesFile
```

Sau khi xác định nguyên nhân, chọn cách xử lý phù hợp:

- Nếu pattern quá rộng, chỉnh sửa đúng file ignore và kiểm tra lại các đường dẫn liên quan.
- Nếu ngoại lệ `!pattern` bị chặn bởi thư mục cha, điều chỉnh quy tắc để Git có thể duyệt đến tệp cần giữ.
- Nếu quy tắc nằm trong file ignore toàn cục nhưng chỉ ảnh hưởng một dự án, cân nhắc chuyển quy tắc sang `.gitignore` của repository hoặc điều chỉnh cấu hình cá nhân.
- Nếu tệp đã tracked, nhớ rằng ignore rule không tự ngừng theo dõi; chỉ dùng `git rm --cached` khi mục tiêu là bỏ tệp khỏi index.

## 11. Những hiểu nhầm thường gặp

| Hiểu nhầm | Cách hiểu đúng |
|---|---|
| `git check-ignore -v` chỉ ra mọi file `.gitignore` trong repository | Lệnh chỉ hiển thị quy tắc có liên quan đến các đường dẫn được kiểm tra |
| Không có output nghĩa là file chắc chắn không bị ignore | Tệp tracked thường không được báo mặc định; thử `--no-index` và kiểm tra `git status` |
| Quy tắc trong `.gitignore` gốc luôn thắng | `.gitignore` sâu hơn có thể ghi đè quy tắc ở thư mục cha; thứ tự và phủ định cũng ảnh hưởng kết quả |
| Thêm file vào `.gitignore` sẽ bỏ theo dõi file đã commit | Ignore không tác động đến tệp đã tracked; cần thao tác index riêng nếu muốn ngừng theo dõi |
| `!file` luôn đưa file trở lại | Git không thể tái xét tệp bên trong thư mục cha đã bị ignore nếu chưa bỏ ignore cho thư mục đó |
| Ignore toàn cục được chia sẻ với cả nhóm | `core.excludesFile` là cấu hình theo máy/người dùng; `.git/info/exclude` là riêng repository local |

## 12. Ghi nhớ

Khi cần biết vì sao một đường dẫn bị bỏ qua, hãy bắt đầu bằng:

```bash
git check-ignore -v -- <path>
```

Đọc bốn thông tin trong output: nguồn quy tắc, số dòng, pattern và đường dẫn. Nếu cần thấy cả trường hợp không khớp, thêm `-n`; nếu tệp có thể đã được tracked, thêm `--no-index`. Khi kiểm tra hàng loạt, dùng `--stdin` và `-z` nếu cần xử lý tên tệp đặc biệt.

Luôn nhớ rằng ignore rule dành cho việc quyết định có theo dõi tệp mới hay không. Nó không xóa tệp, không bỏ một tệp đã tracked khỏi index và không được chia sẻ đồng nhất nếu nằm trong cấu hình toàn cục hoặc `.git/info/exclude`. Chẩn đoán đúng nguồn trước khi sửa giúp giữ quy tắc ignore rõ ràng và tránh ảnh hưởng ngoài ý muốn đến các tệp khác trong dự án.
