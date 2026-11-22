# Phân biệt tệp chưa theo dõi, tệp bị bỏ qua và tệp đã được theo dõi

Khi làm việc trong repository Git, không phải mọi file đang nằm trong thư mục dự án đều có cùng trạng thái. Git phân biệt **tệp đã được theo dõi (tracked)**, **tệp chưa được theo dõi (untracked)** và **tệp bị bỏ qua (ignored)**. Ba trạng thái này quyết định file có được đưa vào snapshot tiếp theo hay xuất hiện trong kết quả git status.

Hiểu đúng sự khác nhau giúp bạn tránh commit nhầm file sinh tự động, không bỏ sót file nguồn mới và không nhầm rằng thêm một quy tắc .gitignore sẽ tự động ngừng theo dõi file đã commit. Bài viết sử dụng working tree, index và commit để giải thích trạng thái của file, sau đó hướng dẫn kiểm tra và xử lý từng loại.

## 1. Ba trạng thái file trong Git

Git quản lý nội dung dựa trên commit, index (staging area) và working tree. Với một đường dẫn cụ thể, có thể phân biệt ba nhóm:

| Trạng thái | Git có ghi nhận đường dẫn trong index không? | Có thể xuất hiện trong git status mặc định? | Ý nghĩa |
|---|---:|---:|---|
| **Tracked** | Có | Khi có thay đổi so với index hoặc HEAD | Git đã biết đường dẫn và theo dõi trạng thái của nó |
| **Untracked** | Không | Có, nếu không bị ignore | File tồn tại trong working tree nhưng chưa được đưa vào index |
| **Ignored** | Thông thường không | Không trong danh sách untracked thông thường; có thể hiện với --ignored | File chưa được theo dõi và khớp quy tắc ignore |

Một file mới tạo trong thư mục dự án ban đầu thường là untracked. Sau khi chạy git add, Git đưa nội dung file vào index; file trở thành tracked trong trạng thái staging, dù chưa có commit chứa nó. Khi commit, snapshot mới ghi nhận file đó trong lịch sử.

Ignored là một cách lọc các file chưa được theo dõi khỏi danh sách untracked mà Git hiển thị thông thường. Quy tắc ignore không xóa file, không tự stage file và không tự gỡ một file khỏi index.

## 2. Tracked: tệp đã được Git theo dõi

Một file là tracked khi đường dẫn của nó có trong index. Thông thường, file được tracked vì đã xuất hiện trong commit trước đó hoặc đã được stage bằng git add.

Ví dụ, repository có:

```text
project/
├── README.md
├── src/
│   └── Main.java
└── config/
    └── app.yml
```

Nếu các file này đã được commit, Git theo dõi chúng. Khi bạn chỉnh sửa README.md, file vẫn là tracked; chỉ nội dung của nó thay đổi so với index hoặc commit hiện tại.

Kiểm tra file tracked:

```bash
git ls-files -- README.md
git ls-files -- src/Main.java
```

Nếu đường dẫn được in ra, file có entry trong index. Lệnh git ls-files mặc định liệt kê các đường dẫn trong index, vì vậy nó hữu ích để xác định file nào Git đang theo dõi.

Xem trạng thái:

```bash
git status --short
```

Ví dụ:

```text
 M README.md
M  src/Main.java
```

Hai cột trạng thái có ý nghĩa khác nhau:

- Cột đầu (X) mô tả thay đổi trong index so với HEAD.
- Cột thứ hai (Y) mô tả thay đổi trong working tree so với index.

Vì vậy:

- ` M` README.md: file tracked đã sửa trong working tree nhưng thay đổi chưa được stage.
- `M ` src/Main.java: thay đổi đã được stage trong index.
- `MM` README.md: file có thay đổi đã stage, sau đó lại được chỉnh sửa thêm trong working tree.

Tracked không có nghĩa file luôn sạch hoặc đã commit mới nhất. Nó chỉ có nghĩa Git đang quản lý đường dẫn đó; file vẫn có thể modified, staged, deleted hoặc unmerged.

## 3. Untracked: tệp chưa được theo dõi

Untracked là file có trong working tree nhưng chưa có entry tương ứng trong index và không bị quy tắc ignore loại khỏi danh sách thông thường.

Ví dụ, bạn vừa tạo src/Helper.java:

```bash
git status --short
```

Kết quả:

```text
?? src/Helper.java
```

Ký hiệu ?? cho biết Git chưa theo dõi file này. Git không đưa nội dung file vào commit cho tới khi bạn stage nó.

Nếu file cần được quản lý trong repository:

```bash
git add -- src/Helper.java
git status --short
```

Kết quả có thể là:

```text
A  src/Helper.java
```

`A ` biểu thị file mới đã được thêm vào index. Từ thời điểm này, file được tracked trong index, dù commit chưa được tạo. Nếu bạn tiếp tục sửa file sau khi stage, Git có thể hiển thị cả thay đổi staged và unstaged.

Để liệt kê các file untracked, dùng:

```bash
git ls-files --others --exclude-standard
```

- --others yêu cầu liệt kê file không có trong index.
- --exclude-standard áp dụng các nguồn ignore chuẩn như .gitignore, .git/info/exclude và file global được cấu hình qua core.excludesFile.

Nếu muốn xem từng file bên trong thư mục untracked thay vì chỉ một thư mục được gộp:

```bash
git status --short --untracked-files=all
```

Tùy chọn này hữu ích khi bạn cần kiểm tra chính xác file mới nào sẽ được thêm vào commit.

## 4. Ignored: tệp bị bỏ qua

Ignored là file chưa được theo dõi và khớp với một quy tắc ignore. Git thường không liệt kê những file này trong phần untracked của git status.

Ví dụ, file .gitignore có:

```gitignore
# Thư mục sinh ra khi build
/build/

# File log
*.log

# Cấu hình local
.env
```

Nếu repository có build/output.class, debug.log và .env, các file đó sẽ được ignore theo những pattern trên, miễn là chúng chưa được tracked.

Kiểm tra cả ignored files:

```bash
git status --short --ignored
```

Ví dụ đầu ra:

```text
 M README.md
?? src/Helper.java
!! .env
!! build/
!! debug.log
```

Ký hiệu !! biểu thị đường dẫn bị ignore. Tùy cách Git nhóm thư mục, output có thể hiển thị thư mục bị ignore thay vì mọi file con.

Ignored không có nghĩa file bị xóa hoặc không tồn tại. File vẫn nằm trên máy và chương trình vẫn có thể đọc nó; Git chỉ bỏ qua file đó trong các hoạt động phát hiện file mới thông thường.

## 5. So sánh nhanh bằng các lệnh kiểm tra

Các lệnh sau giúp xác định trạng thái của một đường dẫn:

| Mục tiêu | Lệnh |
|---|---|
| Kiểm tra file có trong index hay không | git ls-files -- path/to/file |
| Xem thay đổi tracked và untracked | git status --short |
| Hiển thị từng file untracked | git status --short --untracked-files=all |
| Hiển thị cả ignored files | git status --short --ignored |
| Liệt kê file untracked không bị ignore | git ls-files --others --exclude-standard |
| Liệt kê file ignored | git ls-files --others --ignored --exclude-standard |
| Tìm quy tắc ignore khớp với file | git check-ignore -v -- path/to/file |

Có thể kết hợp lệnh để chẩn đoán:

```bash
git status --short --untracked-files=all --ignored
git ls-files -- path/to/file
git check-ignore -v -- path/to/file
```

Lệnh git check-ignore không thay thế git ls-files: nó kiểm tra quy tắc ignore, còn git ls-files kiểm tra đường dẫn có trong index hay không.

## 6. Dùng git check-ignore để tìm nguyên nhân

Khi một file không xuất hiện trong danh sách untracked, có thể file đó bị ignore. Dùng:

```bash
git check-ignore -v -- build/output.class
```

Nếu file khớp quy tắc, Git có thể in nguồn, số dòng, pattern và đường dẫn, ví dụ:

```text
.gitignore:4:/build/    build/output.class
```

Kết quả cho biết pattern /build/ ở dòng 4 của file .gitignore đã bỏ qua đường dẫn được kiểm tra.

Tùy chọn -v (verbose) giúp tìm chính xác file ignore và pattern gây ra kết quả. Các nguồn ignore thường gặp:

- .gitignore trong repository hoặc thư mục con.
- .git/info/exclude chỉ áp dụng cho repository hiện tại.
- File global được cấu hình qua core.excludesFile.

Nếu git check-ignore không in kết quả, file có thể không bị ignore, đường dẫn có thể sai hoặc file đã được tracked. Theo mặc định, git check-ignore không báo các file tracked là ignored vì quy tắc ignore không áp dụng để ngừng theo dõi chúng.

Để kiểm tra pattern kể cả với file đã tracked, thêm --no-index:

```bash
git check-ignore -v --no-index -- config/app.yml
```

Lệnh này chỉ kiểm tra xem đường dẫn có khớp pattern ignore hay không, bỏ qua việc file đang nằm trong index. Nó không làm file ngừng tracked.

## 7. Quy tắc ignore không ảnh hưởng file đã tracked

Đây là điểm dễ gây nhầm lẫn nhất. Giả sử config/app.yml đã được commit. Sau đó bạn thêm vào .gitignore:

```gitignore
config/app.yml
```

Git vẫn theo dõi config/app.yml. Nếu chỉnh sửa file, git status vẫn báo thay đổi. Pattern ignore chỉ giúp ngăn những file chưa được theo dõi khớp pattern xuất hiện như untracked.

Kiểm tra:

```bash
git ls-files -- config/app.yml
git status --short -- config/app.yml
git check-ignore -v --no-index -- config/app.yml
```

Có thể đồng thời nhận được hai kết quả:

- git ls-files in đường dẫn: file đang tracked.
- git check-ignore --no-index cho biết file cũng khớp một pattern ignore.

Điều đó không mâu thuẫn. Ignore không tự gỡ file khỏi index.

Nếu mục tiêu là ngừng theo dõi file nhưng giữ bản local, dùng:

```bash
git rm --cached -- config/app.yml
```

Lệnh này stage việc xóa đường dẫn khỏi index nhưng giữ file trong working tree. Sau khi commit thay đổi đó, file không còn tracked; nếu vẫn khớp .gitignore, Git sẽ bỏ qua nó trong các lần kiểm tra untracked tiếp theo.

Kiểm tra trước khi commit:

```bash
git status --short
git diff --cached -- config/app.yml
Test-Path config/app.yml
```

Test-Path là lệnh PowerShell để xác nhận file vẫn còn trên working tree. Trong Bash có thể dùng test -f config/app.yml.

Lưu ý: git rm --cached không xóa nội dung file khỏi các commit cũ. Nếu file chứa mật khẩu, token hoặc dữ liệu bí mật đã commit, cần xử lý việc lộ bí mật và làm sạch lịch sử theo quy trình riêng; thêm .gitignore không thu hồi dữ liệu đã lưu trong lịch sử.

## 8. Thêm file bị ignore một cách có chủ đích

Đôi khi file khớp .gitignore nhưng bạn vẫn muốn thêm nó vào repository, chẳng hạn một file mẫu hoặc một artifact được chọn để lưu trữ.

Có thể ép thêm một file cụ thể:

```bash
git add -f -- path/to/file
```

-f (force) cho phép thêm đường dẫn đang bị ignore. Sau khi file đã nằm trong index, Git sẽ theo dõi các thay đổi của nó như file tracked thông thường.

Trước khi dùng -f, hãy xác nhận file thực sự cần chia sẻ. Đặc biệt, không ép thêm .env, credential, private key hoặc file chứa dữ liệu nhạy cảm chỉ để làm mất cảnh báo ignore.

Một cách tốt hơn cho file cấu hình local là cung cấp file mẫu:

```text
project/
├── .env.example   # Được commit, chứa tên biến và giá trị minh họa
└── .env           # Bị ignore, chứa cấu hình riêng
```

Ví dụ .gitignore:

```gitignore
.env
!.env.example
```

File .env.example không khớp pattern .env vì tên khác; dòng phủ định chỉ cần thiết nếu một pattern rộng hơn đang ignore cả file mẫu.

## 9. Quy tắc ignore và pattern cơ bản

Các file ignore dùng pattern tương đối với thư mục chứa file ignore đó. Một vài ví dụ phổ biến:

| Pattern | Ý nghĩa |
|---|---|
| *.log | Bỏ qua file hoặc thư mục có tên khớp mẫu ở các cấp bên dưới |
| /build/ | Bỏ qua thư mục build ngay tại cấp của file ignore |
| build/ | Bỏ qua thư mục tên build ở mọi cấp trong phạm vi |
| config/local.yml | Bỏ qua đường dẫn tương đối với file ignore |
| !important.log | Phủ định một quy tắc ignore trước đó để mở lại đường dẫn nếu Git có thể duyệt tới nó |

Một số điểm cần nhớ:

- Dòng bắt đầu bằng # là comment.
- Dấu ! ở đầu pattern dùng để phủ định một quy tắc ignore trước đó.
- Dấu / ở cuối pattern giới hạn pattern vào thư mục.
- Pattern không có slash ở giữa thường có thể khớp tên ở nhiều cấp bên dưới file ignore.
- File .gitignore ở thư mục con áp dụng cho thư mục đó và các thư mục con của nó; pattern được tính tương đối từ vị trí file.

Ví dụ:

```gitignore
# Bỏ qua output build ở root
/build/

# Bỏ qua mọi file log
*.log

# Bỏ qua file cấu hình local
/config/local.yml
```

Nếu một thư mục cha đã bị ignore, việc phủ định riêng một file con có thể không đủ vì Git không duyệt vào thư mục cha bị bỏ qua. Khi cần giữ lại file con, phải mở lại các thư mục cha cần thiết trước.

Các quy tắc ignore được đọc theo nguồn và vị trí. Trong cùng mức ưu tiên, pattern khớp sau cùng quyết định kết quả. File .gitignore sâu hơn có thể ghi đè quy tắc ở thư mục cha; các quy tắc trong .gitignore có ưu tiên cao hơn .git/info/exclude và file global. Dùng git check-ignore -v để tìm quy tắc thực tế thay vì tự đoán precedence.

## 10. Phân biệt file bị xóa với file bị ignore

Nếu một file tracked bị xóa khỏi working tree, Git báo trạng thái deleted, ví dụ:

```text
 D README.md
```

Sau khi stage việc xóa:

```bash
git add -u -- README.md
git status --short
```

Git có thể hiển thị:

```text
D  README.md
```

Đây là thay đổi của một file tracked, không phải ignored. File đã biến mất khỏi working tree và thao tác xóa đang chờ commit.

Ngược lại, một file ignored vẫn tồn tại trong working tree nhưng bị quy tắc ignore loại khỏi danh sách untracked thông thường. Có thể xem ignored files bằng:

```bash
git status --short --ignored
```

Đừng dùng git clean để xử lý một file chỉ vì nó không xuất hiện trong git status thông thường. Trước khi dọn, xác định file là untracked hay ignored và xem trước danh sách sẽ bị xóa.

Ví dụ chỉ xem trước file untracked không bị ignore:

```bash
git clean -nd
```

Chỉ xem trước file ignored:

```bash
git clean -ndX
```

-n là dry-run, -d bao gồm thư mục và -X giới hạn vào file ignored. Bỏ -n sẽ thực hiện xóa; hãy đọc kỹ đầu ra trước khi chạy lệnh thật. Tránh git clean -fdx nếu chưa hiểu rõ vì nó có thể xóa cả file ignored và untracked.

## 11. Ví dụ thực tế trong một dự án

Giả sử dự án Java có các file:

```text
java-app/
├── .gitignore
├── README.md
├── src/
│   ├── Main.java
│   └── Helper.java
├── build/
│   └── classes/
│       └── Main.class
├── .env
└── notes.txt
```

Giả sử:

- README.md và src/Main.java đã được commit.
- src/Helper.java mới tạo, chưa stage.
- build/ và .env khớp quy tắc ignore.
- notes.txt mới tạo và không bị ignore.

File .gitignore:

```gitignore
/build/
/.env
```

Kiểm tra:

```bash
git status --short --untracked-files=all --ignored
```

Kết quả minh họa:

```text
?? notes.txt
?? src/Helper.java
!! .env
!! build/classes/Main.class
```

README.md và src/Main.java không xuất hiện vì chúng đang tracked và không có thay đổi. Helper.java và notes.txt là untracked. .env và Main.class là ignored.

Nếu muốn đưa Helper.java vào commit:

```bash
git add -- src/Helper.java
git status --short
```

Nó chuyển từ ?? sang A . notes.txt vẫn untracked. File .env và Main.class vẫn ignored.

Nếu cần lưu notes.txt vào repository, stage riêng file đó:

```bash
git add -- notes.txt
```

Không cần thêm các file build hoặc cấu hình local.

## 12. Quy trình quyết định trước khi stage

Trước khi chạy git add . hoặc git add -A, hãy phân loại file:

1. **Tracked và có thay đổi:** kiểm tra diff để xác nhận nội dung cần commit.
2. **Untracked:** xác định file có phải source, tài liệu hoặc tài nguyên cần chia sẻ không.
3. **Ignored:** kiểm tra quy tắc ignore và chỉ force-add khi có lý do rõ ràng.
4. **Deleted:** xác nhận việc xóa là chủ đích trước khi stage.
5. **File cấu hình local hoặc secret:** giữ ngoài lịch sử; nếu cần, cung cấp file mẫu an toàn.

Có thể dùng chuỗi lệnh sau để kiểm tra trước khi stage:

```bash
git status --short --untracked-files=all --ignored
git diff
git diff --cached
git check-ignore -v -- path/to/suspected-file
git ls-files -- path/to/suspected-file
```

Không nhất thiết phải chạy mọi lệnh cho mọi file. Chọn lệnh phù hợp với trạng thái đang cần xác minh. Sau khi stage, kiểm tra lại git status và git diff --cached để bảo đảm index chỉ chứa thay đổi dự định commit.

## 13. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| File mới không xuất hiện trong git status | File bị ignore hoặc nằm ngoài repository/pathspec | Dùng git status --ignored và git check-ignore -v |
| Thêm pattern .gitignore nhưng file vẫn báo modified | File đã tracked | Dùng git ls-files; ignore không gỡ file khỏi index |
| git add từ chối file | File đang bị ignore | Kiểm tra pattern; dùng git add -f chỉ khi thực sự cần |
| File untracked xuất hiện dưới dạng cả thư mục | Git đang gộp untracked directory | Dùng --untracked-files=all |
| git check-ignore không in file đã commit | Mặc định bỏ qua tracked paths | Dùng --no-index để kiểm tra pattern |
| Xóa file nhưng Git báo D | File tracked đã bị xóa khỏi working tree | Xác nhận và stage việc xóa nếu đó là chủ đích |
| git rm --cached làm file xuất hiện như untracked | File đã bị gỡ khỏi index và không khớp ignore | Thêm quy tắc ignore phù hợp nếu muốn giữ file local mà không theo dõi |
| File ignored biến mất sau khi chạy clean | Lệnh clean đã xóa file ignored | Dùng git clean -ndX để xem trước; bảo toàn dữ liệu cần giữ |

## Kết luận

Tracked là file có trong index; untracked là file chưa có trong index và không bị ignore; ignored là file chưa được theo dõi nhưng khớp quy tắc loại trừ. Dùng git ls-files để kiểm tra index, git status --short --ignored để xem trạng thái và git check-ignore -v để tìm pattern. Nhớ rằng .gitignore không ảnh hưởng file đã tracked: muốn ngừng theo dõi nhưng giữ file local, dùng git rm --cached, kiểm tra staged diff rồi commit thay đổi. Trước khi stage hàng loạt hoặc dọn file, luôn phân loại và xác nhận chính xác đường dẫn.
