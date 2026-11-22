# Phạm vi bỏ qua: .gitignore, .git/info/exclude và core.excludesFile

Git có nhiều nơi để khai báo những đường dẫn không nên xuất hiện như file chưa được theo dõi trong working tree. Ba nơi thường gặp là file `.gitignore` trong repository, file `.git/info/exclude` của từng repository và file được cấu hình qua `core.excludesFile` cho người dùng. Cả ba đều dùng cú pháp pattern ignore tương tự nhau, nhưng khác nhau về phạm vi chia sẻ và mục đích sử dụng.

Chọn đúng nơi đặt quy tắc giúp nhóm cùng bỏ qua file sinh tự động, đồng thời mỗi người vẫn có thể bỏ qua file cá nhân hoặc file chỉ liên quan tới máy của mình. Hiểu thứ tự ưu tiên và cách Git đánh giá pattern cũng giúp tìm ra lý do một file bị ignore hoặc vì sao một quy tắc mới chưa có tác dụng.

## 1. Ba nơi khai báo ignore khác nhau thế nào?

| Nơi khai báo | Phạm vi | Có được chia sẻ qua Git không? | Khi nào nên dùng |
|---|---|---|---|
| `.gitignore` | Repository hoặc một thư mục con và các thư mục bên dưới | Có, khi file được commit | Quy tắc chung của dự án: output build, file sinh tự động, cache |
| `.git/info/exclude` | Chỉ repository hiện tại | Không | File cá nhân chỉ muốn bỏ qua trong repository này |
| `core.excludesFile` | Các repository dùng chung cấu hình Git của người dùng (thường cấu hình global) | Không, trừ khi người dùng tự chia sẻ file cấu hình | File hệ điều hành, IDE hoặc công cụ cá nhân xuất hiện ở nhiều dự án |

### .gitignore: quy tắc của dự án

File `.gitignore` thường đặt ở thư mục gốc repository. Bạn cũng có thể đặt file cùng tên trong thư mục con để áp dụng quy tắc cho thư mục đó và các thư mục bên dưới.

Ví dụ cấu trúc:

```text
project/
├── .gitignore
├── src/
│   └── Main.java
├── build/
└── tools/
    └── .gitignore
```

File `project/.gitignore` có thể chứa quy tắc chung cho toàn dự án. File `project/tools/.gitignore` chỉ điều chỉnh các đường dẫn trong `tools/` và các thư mục con của nó.

Vì `.gitignore` là file trong working tree, nhóm có thể commit nó để mọi người dùng chung quy tắc. Khi thêm hoặc sửa quy tắc, hãy đưa chính file `.gitignore` vào commit nếu muốn thay đổi được chia sẻ.

### .git/info/exclude: quy tắc riêng của repository

Mỗi repository có thể có file exclude trong thư mục Git metadata. Đường dẫn thường thấy là `.git/info/exclude`:

```text
.git/
└── info/
    └── exclude
```

File này không nằm trong working tree thông thường và không được commit. Nó phù hợp với file phụ chỉ xuất hiện trên máy bạn trong repository hiện tại, chẳng hạn file ghi chú cá nhân hoặc cấu hình công cụ thử nghiệm.

Không phải lúc nào thư mục Git cũng nằm trong thư mục `.git` thông thường. Với linked worktree hoặc một số cách bố trí repository, `.git` có thể là file trỏ tới Git directory thật. Dùng lệnh sau để lấy đúng đường dẫn:

```bash
git rev-parse --git-path info/exclude
```

Lệnh trả về đường dẫn tới file exclude mà repository hiện tại đang sử dụng.

### core.excludesFile: quy tắc riêng của người dùng

Bạn có thể cấu hình một file ignore bên ngoài repository bằng biến cấu hình `core.excludesFile`. Khi đặt ở cấu hình global, các repository của người dùng đó cùng sử dụng các pattern trong file:

```bash
git config --global core.excludesFile "$HOME/.config/git/ignore"
```

Tạo file tại đường dẫn đã cấu hình rồi thêm các quy tắc cá nhân, ví dụ:

```gitignore
# File hệ điều hành
.DS_Store
Thumbs.db

# File cấu hình riêng của editor
.idea/
.vscode/
```

Các quy tắc này không được chia sẻ cùng repository. Nếu nhóm cần bỏ qua một thư mục cấu hình IDE cụ thể vì nó không thuộc sản phẩm, hãy cân nhắc đặt quy tắc trong `.gitignore`; nếu chỉ bạn muốn bỏ qua thiết lập editor của mình, dùng file global.

Để xem giá trị và nguồn cấu hình hiện tại:

```bash
git config --show-origin --get core.excludesFile
git config --global --show-origin --get core.excludesFile
```

Lệnh đầu tìm cấu hình hiệu lực theo các scope Git đọc được; lệnh thứ hai chỉ hỏi cấu hình global. Nếu chưa cấu hình, lệnh có thể không in giá trị.

## 2. Git ưu tiên các nguồn ignore như thế nào?

Khi một đường dẫn chưa được theo dõi khớp nhiều quy tắc, Git áp dụng thứ tự ưu tiên từ cao xuống thấp:

1. Pattern được truyền trực tiếp qua các tùy chọn loại trừ của những lệnh Git hỗ trợ cơ chế này.
2. Các file `.gitignore` áp dụng cho đường dẫn đó. File ở thư mục sâu hơn có mức ưu tiên cao hơn file ở thư mục cha.
3. File `.git/info/exclude` của repository.
4. File được chỉ định bởi `core.excludesFile`.

Trong cùng một mức ưu tiên, pattern xuất hiện sau cùng sẽ quyết định kết quả nếu nhiều pattern cùng khớp. Vì vậy, một quy tắc trong `.gitignore` của thư mục con có thể ghi đè quy tắc ở file cha; file `.gitignore` cũng có ưu tiên cao hơn `.git/info/exclude` và file global.

Ví dụ, file global có:

```gitignore
*.log
```

Nhưng repository có `.gitignore`:

```gitignore
!important.log
```

Trong phạm vi áp dụng của file `.gitignore`, quy tắc này có thể cho phép lại file `important.log` dù nó khớp pattern global `*.log`.

Thứ tự ưu tiên không có nghĩa mọi pattern phủ định đều có thể cứu một file. Nếu một thư mục cha đã bị ignore, Git không duyệt vào thư mục đó để tìm các file con được mở lại. Phần tiếp theo sẽ minh họa trường hợp này.

## 3. Cú pháp pattern thường dùng

Các file `.gitignore`, `.git/info/exclude` và `core.excludesFile` dùng cùng một cú pháp pattern cơ bản.

| Pattern | Ý nghĩa |
|---|---|
| `*.log` | Bỏ qua file hoặc thư mục có tên kết thúc bằng `.log` ở mọi cấp thư mục |
| `/build/` | Chỉ bỏ qua thư mục `build` ở cùng cấp với file ignore chứa pattern |
| `build/` | Bỏ qua thư mục có tên `build` ở bất kỳ cấp nào trong phạm vi áp dụng |
| `/config/local.yml` | Chỉ bỏ qua đường dẫn đó tính từ thư mục chứa file ignore |
| `doc/*.pdf` | Bỏ qua file PDF ngay trong thư mục `doc`, không khớp các thư mục con sâu hơn |
| `**/cache/` | Bỏ qua thư mục `cache` ở bất kỳ độ sâu nào |
| `!important.log` | Phủ định một quy tắc ignore trước đó, cho phép file khớp trở lại nếu Git có thể duyệt tới nó |

Một số quy tắc đọc pattern quan trọng:

- Dòng trống không tạo quy tắc.
- Dòng bắt đầu bằng `#` là comment. Dùng `\#` nếu muốn ký tự `#` là một phần của tên pattern.
- Dấu `!` ở đầu pattern dùng để phủ định một quy tắc ignore trước đó. Dùng `\!` nếu tên file thật bắt đầu bằng dấu chấm than.
- Dấu gạch chéo ở cuối pattern giới hạn pattern vào thư mục; ví dụ `cache/` khớp thư mục `cache`, không khớp file thường cùng tên.
- Nếu pattern không chứa dấu gạch chéo (ngoại trừ dấu gạch chéo cuối để chỉ thư mục), nó có thể khớp ở mọi cấp bên dưới thư mục chứa file ignore.
- Nếu pattern chứa dấu gạch chéo ở giữa hoặc bắt đầu bằng dấu gạch chéo, đường dẫn được xét tương đối với thư mục chứa file ignore đó.
- `**` có ý nghĩa đặc biệt trong một số vị trí, cho phép khớp nhiều cấp thư mục.

Ví dụ:

```gitignore
# Bỏ qua file log ở mọi cấp
*.log

# Bỏ qua thư mục build ngay tại gốc repository
/build/

# Bỏ qua mọi thư mục cache trong phạm vi file này
cache/

# Bỏ qua file PDF trong doc và các thư mục con
doc/**/*.pdf
```

Pattern trong `.gitignore` con được tính tương đối từ thư mục chứa file con, không phải luôn từ root repository. Khi di chuyển quy tắc từ file gốc xuống một thư mục con, hãy xem lại đường dẫn pattern vì phạm vi tương đối đã thay đổi.

## 4. Dùng phủ định để mở lại file

Dấu `!` cho phép loại một đường dẫn ra khỏi tập bị ignore bởi pattern trước đó. Ví dụ:

```gitignore
# Bỏ qua toàn bộ file log
*.log

# Nhưng giữ lại file này
!important.log
```

Nếu `important.log` chưa được theo dõi, Git sẽ xem nó là file có thể được thêm vào dù pattern `*.log` khớp với tên của nó.

Với thư mục, cần để Git có thể đi vào thư mục cha. Cấu hình sau không đạt mục tiêu mở lại file:

```gitignore
build/
!build/keep.txt
```

Lý do là `build/` đã loại cả thư mục khỏi quá trình duyệt; Git không đi vào đó để tìm `keep.txt`.

Có thể thay bằng cách chỉ ignore các mục bên trong thư mục, rồi phủ định file cần giữ:

```gitignore
/build/*
!/build/keep.txt
```

Ở đây thư mục `build` không bị ignore trực tiếp, nên Git có thể xét các mục bên trong. Pattern phủ định mở lại `keep.txt`. Nếu cần mở lại một file nằm sâu trong thư mục con, bạn cũng phải mở lại từng thư mục cha cần thiết để Git có thể duyệt tới file đó.

## 5. File đã được theo dõi không tự biến mất vì .gitignore

Quy tắc ignore chủ yếu áp dụng cho các file chưa được Git theo dõi. Nếu file đã được thêm vào index và commit, thêm nó vào `.gitignore` không làm Git ngừng theo dõi file đó.

Ví dụ, một file `.env` đã được commit trước khi bạn thêm:

```gitignore
.env
```

Git vẫn tiếp tục theo dõi thay đổi của `.env`. Để bỏ file khỏi index nhưng giữ bản file trong working tree:

```bash
git rm --cached -- .env
```

Sau đó kiểm tra và commit cả thay đổi trong index lẫn quy tắc ignore:

```bash
git status
git add .gitignore
git commit -m "Stop tracking local environment file"
```

Sau commit, file `.env` vẫn tồn tại trên máy bạn nhưng không còn được theo dõi trong các commit tiếp theo. Lưu ý rằng commit cũ vẫn chứa nội dung file. Nếu file từng chứa mật khẩu, token hoặc thông tin bí mật, việc bỏ theo dõi không xóa dữ liệu khỏi lịch sử; cần xử lý sự cố lộ bí mật và làm sạch lịch sử theo quy trình phù hợp.

Không nên ignore một file cấu hình mẫu mà dự án cần cung cấp cho người khác. Một cách phổ biến là commit `.env.example` với các tên biến và giá trị giả, còn ignore `.env` chứa cấu hình riêng của từng máy.

## 6. Chọn đúng nơi đặt quy tắc

Có thể dùng câu hỏi “ai cần quy tắc này?” để chọn nơi khai báo:

- **Mọi người trong dự án đều nên bỏ qua:** thêm vào `.gitignore` và commit.
- **Chỉ riêng repository trên máy tôi cần bỏ qua:** thêm vào `.git/info/exclude`.
- **Mọi repository của tài khoản tôi đều cần bỏ qua:** thêm vào file được cấu hình bằng `core.excludesFile`.

Ví dụ lựa chọn:

| File hoặc thư mục | Nơi thường phù hợp | Lý do |
|---|---|---|
| `build/`, `dist/`, file sinh từ compiler | `.gitignore` | Là output chung không nên đưa vào lịch sử dự án |
| File cache riêng của một công cụ chỉ dùng trên máy bạn | `.git/info/exclude` | Không cần áp dụng cho cả nhóm |
| `.DS_Store`, `Thumbs.db` | `core.excludesFile` hoặc `.gitignore` | Có thể là thói quen cá nhân hoặc quy tắc chung tùy nhóm |
| Cấu hình editor cá nhân | `core.excludesFile` | Không nên áp đặt editor của một người lên cả nhóm |
| File cấu hình local chứa secret | `.gitignore` | Cả nhóm cần tránh commit file cấu hình riêng; vẫn nên có file mẫu an toàn |

Đây là gợi ý theo mục đích, không phải quy định bắt buộc. Ví dụ một nhóm có thể thống nhất commit quy tắc bỏ qua `.DS_Store` trong `.gitignore` để tất cả thành viên dùng chung.

## 7. Kiểm tra vì sao một file bị ignore

Khi một file không xuất hiện trong danh sách file chưa theo dõi, hãy tìm quy tắc đã khớp thay vì đoán file nào đang gây ra vấn đề.

Dùng `git check-ignore -v` để xem nguồn, số dòng và pattern:

```bash
git check-ignore -v -- path/to/file.log
```

Ví dụ đầu ra có thể cho biết:

```text
.gitignore:12:*.log    path/to/file.log
```

Điều đó có nghĩa pattern `*.log` ở dòng 12 của file `.gitignore` đã bỏ qua đường dẫn được kiểm tra.

Nếu file đã được theo dõi, `git check-ignore` mặc định thường không báo nó là file bị ignore vì tracked file không bị quy tắc ignore loại khỏi index. Có thể thêm `--no-index` để kiểm tra pattern kể cả với file đã tracked:

```bash
git check-ignore -v --no-index -- path/to/file.log
```

Để xem các file ignored trong trạng thái repository:

```bash
git status --short --ignored
```

Các trạng thái ignore thường được hiển thị bằng `!!`. Lệnh này hữu ích khi bạn muốn biết file nào đang bị ẩn khỏi danh sách untracked thông thường.

Kiểm tra file có đang được theo dõi không:

```bash
git ls-files -- path/to/file.log
```

Nếu lệnh in đường dẫn, file đang nằm trong index. Khi đó, chỉnh `.gitignore` sẽ không làm file ngừng tracked; cần quyết định có bỏ nó khỏi index bằng `git rm --cached` hay không.

## 8. Quy trình thêm và xác minh quy tắc ignore

Một quy trình ngắn gọn khi một file sinh tự động xuất hiện trong repository:

1. Xác định file có cần được commit cho dự án hay không.
2. Kiểm tra file đã tracked chưa bằng `git ls-files -- path/to/file`.
3. Chọn nguồn ignore phù hợp với phạm vi: `.gitignore`, `.git/info/exclude` hoặc `core.excludesFile`.
4. Viết pattern đúng phạm vi đường dẫn và kiểm tra lại bằng `git check-ignore -v`.
5. Nếu file đã tracked, bỏ khỏi index bằng `git rm --cached` sau khi xác nhận giữ bản file local.
6. Kiểm tra `git status --short --ignored` và staged diff trước khi commit.
7. Nếu quy tắc cần chia sẻ, commit file `.gitignore` cùng thay đổi liên quan.

Ví dụ thêm quy tắc bỏ qua thư mục build ở root dự án:

```gitignore
/build/
```

Sau đó kiểm tra:

```bash
git check-ignore -v -- build/output.class
git status --short --ignored
```

Nếu `build/output.class` đã tracked, kiểm tra và bỏ theo dõi bằng:

```bash
git rm --cached -- build/output.class
```

Nếu nhiều file trong thư mục đã tracked, có thể dùng đường dẫn thư mục với `git rm -r --cached -- build/` sau khi xem kỹ danh sách file sẽ bị loại khỏi index. Lệnh này giữ các file trên working tree nhưng xóa chúng khỏi index; hãy kiểm tra staged diff trước khi commit.

## 9. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Thêm pattern nhưng file vẫn xuất hiện trong diff | File đã được tracked | Kiểm tra `git ls-files`; nếu phù hợp, dùng `git rm --cached` |
| Quy tắc ignore không có tác dụng | Pattern được viết tương đối với sai thư mục hoặc sai dấu gạch chéo | Dùng `git check-ignore -v` và kiểm tra vị trí file ignore |
| File cá nhân bị ignore trên máy đồng đội | Quy tắc riêng bị thêm nhầm vào `.gitignore` và commit | Chuyển quy tắc sang `.git/info/exclude` hoặc file global |
| File cần giữ vẫn bị ignore | Pattern phủ định không khớp hoặc thư mục cha đã bị ignore | Mở lại thư mục cha trước, sau đó mở lại file con |
| Global ignore không có hiệu lực | `core.excludesFile` trỏ sai đường dẫn hoặc file chưa tồn tại | Kiểm tra bằng `git config --show-origin --get core.excludesFile` |
| Không tìm thấy `.git/info/exclude` tại đường dẫn dự kiến | Repository dùng Git directory khác, ví dụ linked worktree | Dùng `git rev-parse --git-path info/exclude` |
| Đã bỏ tracked file nhưng vẫn thấy thay đổi trong lịch sử cũ | Ignore không xóa commit trước đó | Nếu có secret, xử lý riêng cả secret và lịch sử |

## Kết luận

Dùng `.gitignore` cho quy tắc chung cần chia sẻ trong dự án, `.git/info/exclude` cho ngoại lệ riêng của repository hiện tại và `core.excludesFile` cho thói quen ignore dùng chung của tài khoản. Git ưu tiên pattern theo nguồn và vị trí file; pattern sau cùng trong cùng mức ưu tiên quyết định kết quả. Hãy dùng `git check-ignore -v` để truy tìm quy tắc, và nhớ rằng ignore không làm file đã tracked biến mất khỏi index.
