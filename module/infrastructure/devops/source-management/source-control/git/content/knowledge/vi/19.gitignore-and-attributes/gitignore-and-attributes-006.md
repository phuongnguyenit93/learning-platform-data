# Vì sao thêm `.gitignore` không làm ngừng theo dõi tệp đã commit

Khi một dự án bắt đầu sinh ra tệp build, log, cache hoặc cấu hình riêng trên máy lập trình viên, ta thường thêm các đường dẫn đó vào `.gitignore`. Tuy nhiên, nếu một tệp đã được Git theo dõi và commit từ trước, việc thêm tên tệp vào `.gitignore` **không làm Git ngừng theo dõi tệp đó**.

Lý do nằm ở cách Git phân biệt hai việc: **ignore rule quyết định có bỏ qua một tệp chưa được theo dõi hay không; index (staging area) ghi nhận những đường dẫn Git đang theo dõi để đưa vào commit**. Khi một đường dẫn đã có trong index, Git tiếp tục theo dõi nó dù đường dẫn đó khớp với mẫu trong `.gitignore`.

Muốn ngừng theo dõi một tệp nhưng vẫn giữ bản hiện tại trên máy, ta cần xóa đường dẫn khỏi index bằng `git rm --cached`, rồi commit thay đổi đó. Bài học này giải thích vì sao hai bước có vai trò khác nhau và cách thực hiện an toàn.

## 1. Git phân biệt tracked, untracked và ignored như thế nào?

Git làm việc với các đường dẫn trong repository theo những trạng thái khác nhau:

| Trạng thái | Ý nghĩa | Git có theo dõi thay đổi của tệp không? |
|---|---|---|
| **Tracked** | Đường dẫn đã nằm trong index hoặc có trong commit mà Git đang quản lý. | Có. Git phát hiện thay đổi nội dung, xóa hoặc đổi tên. |
| **Untracked** | Tệp tồn tại trong working tree nhưng chưa được Git đưa vào index. | Chưa. Git có thể hiển thị tệp là untracked. |
| **Ignored** | Tệp chưa được theo dõi và khớp với một ignore rule có hiệu lực. | Git thường không liệt kê nó như untracked trong trạng thái thông thường. |

Một tệp tracked có thể được sửa, stage, commit và theo dõi qua nhiều phiên bản. Một tệp ignored thường là tệp chưa được thêm vào Git và ta không muốn đưa nó vào repository.

### 1.1. Index quyết định Git đang theo dõi đường dẫn nào

Khi chạy:

```bash
git add config/local.json
git commit -m "chore: add local config"
```

Git đưa đường dẫn `config/local.json` vào index rồi ghi nhận nó trong commit. Từ thời điểm đó, đường dẫn là tracked. Nếu sau này thêm dòng sau vào `.gitignore`:

```gitignore
config/local.json
```

Git vẫn theo dõi `config/local.json`, vì đường dẫn đó đã được index quản lý. Nếu nội dung tệp thay đổi, `git status` vẫn báo thay đổi như bình thường.

Ignore rule không xóa đường dẫn khỏi index, không tạo commit xóa tệp và không sửa lịch sử đã có.

### 1.2. Vì sao Git không tự ngừng theo dõi?

Nếu `.gitignore` có thể tự động bỏ theo dõi tệp đã commit, một quy tắc mới có thể âm thầm làm biến mất các tệp dự án mà đồng đội đang sử dụng. Git yêu cầu người dùng thực hiện thao tác thay đổi index một cách rõ ràng để việc bỏ theo dõi được ghi nhận trong commit.

Đây là hành vi có chủ đích: ignore rule giúp kiểm soát các tệp chưa được thêm vào repository; index và commit mới quyết định nội dung nào đang được quản lý.

## 2. Ví dụ: thêm `.gitignore` nhưng tệp vẫn xuất hiện trong `git status`

Giả sử dự án đã commit thư mục `build/` từ trước. Ta thêm quy tắc:

```gitignore
/build/
```

Sau đó chạy:

```bash
git status
```

Nếu một tệp tracked trong `build/` thay đổi, Git vẫn hiển thị thay đổi đó. Quy tắc `/build/` chỉ ngăn các tệp chưa được theo dõi trong thư mục `build/` được báo như untracked; nó không bỏ các tệp đã có trong index.

Có thể kiểm tra một đường dẫn có đang tracked không:

```bash
git ls-files -- build/
```

Nếu lệnh liệt kê các tệp trong `build/`, chúng vẫn đang nằm trong index. Vì vậy, thêm `.gitignore` thôi chưa giải quyết được vấn đề.

## 3. Ngừng theo dõi nhưng giữ tệp local bằng `git rm --cached`

Lệnh cần nhớ là:

```bash
git rm --cached -- config/local.json
```

`--cached` yêu cầu Git xóa đường dẫn khỏi index mà giữ tệp trong working tree. Sau lệnh này:

- Git chuẩn bị ghi nhận việc xóa đường dẫn khỏi repository trong commit kế tiếp.
- Bản tệp hiện tại vẫn còn trên máy đang thực hiện lệnh.
- Nếu `.gitignore` có quy tắc khớp đường dẫn, tệp local được giữ lại nhưng không còn xuất hiện như untracked thông thường.
- Các commit cũ vẫn chứa phiên bản đã commit trước đây.

Đối với cả thư mục, dùng `-r`:

```bash
git rm -r --cached -- build/
```

Lệnh này bỏ theo dõi các tệp trong `build/` ở index nhưng giữ nội dung thư mục trên working tree hiện tại. Trước khi chạy, hãy kiểm tra chính xác đường dẫn để không bỏ theo dõi nhầm mã nguồn cần quản lý.

Nếu Git từ chối vì nội dung trong index và working tree khác nhau, hãy dừng lại, xem `git status`, `git diff` và `git diff --cached` để xác định phần nào cần giữ. Đừng thêm `-f` theo phản xạ: ép xóa có thể loại bỏ phiên bản đang stage khỏi index. Hãy bảo toàn patch hoặc bản sao cần thiết rồi mới quyết định cách xử lý.

### 3.1. Quy trình đầy đủ cho một tệp

Giả sử `config/local.json` đã được commit nhưng từ nay mỗi lập trình viên cần giữ cấu hình riêng trên máy.

**Bước 1: Thêm quy tắc ignore**

Trong `.gitignore` ở repository root:

```gitignore
# Cấu hình riêng của máy lập trình viên
/config/local.json
```

**Bước 2: Bỏ đường dẫn khỏi index, giữ tệp local**

```bash
git rm --cached -- config/local.json
```

**Bước 3: Kiểm tra trạng thái**

```bash
git status --short
git ls-files -- config/local.json
git check-ignore -v --no-index -- config/local.json
```

Kết quả mong đợi:

- `git status` cho thấy việc xóa khỏi index đang được stage.
- `git ls-files -- config/local.json` không còn liệt kê đường dẫn đó.
- `git check-ignore` chỉ ra dòng trong `.gitignore` đã khớp với tệp.
- Tệp `config/local.json` vẫn tồn tại trên máy hiện tại.

**Bước 4: Commit thay đổi**

```bash
git add .gitignore
git commit -m "chore: stop tracking local config"
```

Sau commit, repository ghi nhận việc bỏ tệp khỏi phiên bản hiện tại và quy tắc ignore mới. Những lần thay đổi `config/local.json` trên máy này không còn được Git theo dõi trong trạng thái thông thường.

### 3.2. Quy trình cho một thư mục sinh tự động

Giả sử thư mục `build/` đang được tracked và muốn bỏ khỏi repository:

```gitignore
/build/
```

Chạy:

```bash
git rm -r --cached -- build/
git status --short
git add .gitignore
git commit -m "chore: stop tracking build output"
```

Sau commit, Git không còn quản lý các tệp trong `build/` ở phiên bản hiện tại. Thư mục build trên máy hiện tại vẫn còn. Khi đồng đội lấy commit mới, Git sẽ áp dụng việc xóa các đường dẫn đó khỏi working tree của họ; nếu họ cần dữ liệu sinh ra, họ phải tạo lại bằng build hoặc lưu riêng theo quy trình dự án.

Điểm này đặc biệt quan trọng: `--cached` giữ file local cho người chạy lệnh, nhưng commit xóa tracked path sẽ được chia sẻ cho cả nhóm. Nó không có nghĩa mọi clone khác cũng giữ nguyên tệp sau khi pull.

## 4. Hiểu kết quả trong `git status`

Sau `git rm --cached`, Git thường hiển thị đường dẫn như một thay đổi đã stage để xóa khỏi index. Ví dụ:

```text
D  config/local.json
M  .gitignore
```

Ý nghĩa:

- `D` ở cột trạng thái staged: commit kế tiếp sẽ bỏ đường dẫn khỏi repository.
- `M` ở cột trạng thái staged: `.gitignore` đã được sửa và đang chờ commit.

Tệp local vẫn còn trên ổ đĩa. Có thể kiểm tra bằng cách xem tệp trong file manager hoặc dùng lệnh phù hợp với hệ điều hành. Nếu tệp khớp ignore rule, `git status --short --ignored` có thể hiển thị nó với ký hiệu ignored.

Đừng nhầm việc Git hiển thị `D` trong vùng staged với việc tệp đã bị xóa khỏi ổ đĩa. `git rm --cached` xóa khỏi index; `git rm` không có `--cached` còn xóa tệp khỏi working tree.

## 5. Kiểm tra ignore rule và đường dẫn tracked

Khi quy tắc `.gitignore` không hoạt động như mong đợi, hãy kiểm tra cả hai phía: tệp có đang tracked không và quy tắc nào đang khớp.

### 5.1. Xem đường dẫn đang tracked

```bash
git ls-files -- path/to/file
```

Nếu Git in ra đường dẫn, tệp đang nằm trong index. Nếu không có kết quả, tệp có thể chưa tracked hoặc đường dẫn được cung cấp chưa chính xác.

Để liệt kê các tệp tracked đang khớp với ignore rules:

```bash
git ls-files -ci --exclude-standard
```

Lệnh này hữu ích khi `.gitignore` mới được bổ sung nhưng repository đã có những tệp tương ứng được commit trước đó.

### 5.2. Xem quy tắc nào đang bỏ qua tệp

```bash
git check-ignore -v -- path/to/file
```

Kết quả hiển thị nguồn quy tắc, số dòng và mẫu đã khớp, nếu đường dẫn là đối tượng được ignore. `git check-ignore` mặc định bỏ qua các đường dẫn tracked vì ignore rule không áp dụng cho chúng.

Nếu cần kiểm tra mẫu ignore ngay cả với đường dẫn tracked, thêm `--no-index`:

```bash
git check-ignore -v --no-index -- path/to/file
```

Lệnh này giúp phân biệt hai câu hỏi:

- Đường dẫn có khớp một ignore rule hay không?
- Đường dẫn có đang được Git theo dõi hay không?

Một tệp có thể khớp `.gitignore` nhưng vẫn tracked. Khi đó, `--no-index` giúp nhìn thấy quy tắc khớp, còn `git ls-files` cho biết nó vẫn nằm trong index.

### 5.3. Xem các tệp ignored

```bash
git status --short --ignored
```

Lệnh này bổ sung trạng thái ignored vào kết quả. Thông thường, `!!` là ký hiệu cho đường dẫn ignored. Nó giúp kiểm tra quy tắc có tác dụng với tệp chưa tracked, nhưng không chứng minh rằng tệp tracked đã được bỏ khỏi index.

## 6. Những nơi có thể định nghĩa ignore rule

Git có nhiều nguồn quy tắc ignore:

| Nguồn | Phạm vi |
|---|---|
| `.gitignore` ở repository root | Quy tắc được chia sẻ qua commit với cả nhóm. |
| `.gitignore` trong thư mục con | Quy tắc áp dụng theo vị trí của file `.gitignore` đó và các thư mục con bên dưới. |
| `.git/info/exclude` | Quy tắc riêng của repository local, không được commit như một tệp dự án. |
| File global excludes | Quy tắc cá nhân áp dụng cho các repository trên máy theo cấu hình Git. |

Các nguồn này chỉ quyết định việc bỏ qua những đường dẫn chưa được theo dõi. Không nguồn ignore nào tự động loại một đường dẫn đã tracked khỏi index.

Xem file excludes global đang cấu hình:

```bash
git config --get core.excludesfile
```

Nếu không có kết quả, có thể repository hoặc máy chưa cấu hình file global excludes. Không nên thêm quy tắc dự án vào file global nếu muốn cả nhóm cùng áp dụng; hãy đặt quy tắc chung trong `.gitignore` được commit.

## 7. Viết pattern `.gitignore` đúng cách

Một số mẫu thường dùng:

```gitignore
# Bỏ qua thư mục build ở repository root
/build/

# Bỏ qua file log ở mọi cấp
*.log

# Bỏ qua file cấu hình local cụ thể
/config/local.json

# Bỏ qua file môi trường
.env
.env.*

# Cho phép giữ lại một mẫu cấu hình được chia sẻ
!.env.example
```

Một số nguyên tắc:

- Dấu `/` ở đầu mẫu giới hạn đường dẫn tương đối với vị trí `.gitignore` đó.
- Dấu `/` ở cuối mẫu chỉ thư mục.
- `*` khớp một phần tên đường dẫn trong một cấp; `**` có thể khớp nhiều cấp thư mục.
- Dấu `!` phủ định một quy tắc ignore trước đó để đưa một đường dẫn trở lại tập được xét.
- Nếu thư mục cha đã bị ignore, không thể chỉ phủ định tệp con bên trong mà không làm các thư mục cha cần thiết được xét lại.
- Ignore rule không ngăn lệnh `git add -f` thêm tệp vào index; người dùng vẫn có thể chủ động force-add một tệp đang bị ignore.

Ví dụ muốn bỏ qua mọi file `.log` nhưng giữ `important.log` ở repository root:

```gitignore
*.log
!/important.log
```

Những pattern này ảnh hưởng tới tệp chưa tracked. Nếu `important.log` hoặc một file `.log` khác đã được commit, Git vẫn theo dõi nó cho tới khi đường dẫn được bỏ khỏi index bằng thao tác riêng.

## 8. `.gitignore` không xóa dữ liệu đã commit trong lịch sử

Một hiểu lầm nghiêm trọng là thêm tệp nhạy cảm vào `.gitignore` sẽ xóa nó khỏi repository. Thực tế:

1. `.gitignore` không xóa tệp khỏi index.
2. `git rm --cached` chỉ ghi nhận việc bỏ theo dõi trong commit mới; nó không sửa các commit cũ.
3. Người có quyền truy cập lịch sử vẫn có thể xem phiên bản tệp trong commit trước đó.
4. Nếu tệp chứa mật khẩu, token hoặc khóa riêng đã được commit, cần coi thông tin đó là đã lộ.

Nếu lỡ commit secret:

- Thu hồi hoặc xoay vòng credential ngay theo quy trình bảo mật của hệ thống.
- Bỏ tệp khỏi tracking và thêm quy tắc ignore phù hợp nếu đó là dữ liệu local.
- Nếu chính sách yêu cầu loại secret khỏi lịch sử, cần dùng quy trình viết lại history có kiểm soát, phối hợp với mọi người đang dùng repository và xử lý các clone, fork, cache hoặc bản sao khác.
- Kiểm tra lại repository và hệ thống triển khai để chắc chắn secret mới không tiếp tục bị commit.

Việc viết lại lịch sử có thể cần force push và khiến các clone phải đồng bộ lại. Không thực hiện chỉ bằng cách thêm `.gitignore` hoặc xóa tệp trong commit mới.

## 9. `.gitignore` khác `.gitattributes` như thế nào?

Hai tệp có tên gần giống nhưng mục đích khác nhau:

| Tệp | Vai trò chính | Ví dụ |
|---|---|---|
| `.gitignore` | Bỏ qua các đường dẫn chưa được theo dõi khi Git xét tệp mới. | Không thêm `build/`, `.env`, `*.log` vào index. |
| `.gitattributes` | Gán thuộc tính cho đường dẫn được Git quản lý, ảnh hưởng cách xử lý nội dung. | Chuẩn hóa line ending, chọn diff driver, merge driver hoặc filter. |

`.gitattributes` không thay thế `.gitignore` và cũng không quyết định bỏ theo dõi một tệp đã commit. Nếu cần ngừng theo dõi, hãy xử lý index bằng `git rm --cached`.

## 10. Các lỗi thường gặp và cách xử lý

### 10.1. Thêm `.gitignore` nhưng `git status` vẫn báo file modified

Nguyên nhân: tệp đã tracked. Kiểm tra:

```bash
git ls-files -- path/to/file
```

Nếu có kết quả, bỏ đường dẫn khỏi index nếu mục tiêu là ngừng theo dõi:

```bash
git rm --cached -- path/to/file
```

Sau đó commit thay đổi cùng `.gitignore`.

### 10.2. Chạy `git rm --cached` nhưng file biến mất khỏi máy

Hãy kiểm tra chính xác lệnh đã chạy. `git rm --cached` được thiết kế để giữ working-tree file; `git rm` thông thường xóa cả index và working-tree file. Nếu tệp đã biến mất, đừng tạo hoặc ghi đè tệp vội vàng. Kiểm tra backup, commit, reflog nếu phù hợp và phục hồi nội dung cần thiết trước.

### 10.3. Đồng đội pull về nhưng file local biến mất

Commit bỏ theo dõi ghi nhận xóa đường dẫn khỏi repository. Khi đồng đội pull commit đó, file tracked trước đây có thể bị xóa khỏi working tree của họ. Họ cần tạo lại tệp local hoặc dùng mẫu cấu hình được chia sẻ. Trước khi bỏ theo dõi một tệp, hãy cung cấp file mẫu hoặc tài liệu hướng dẫn nếu các thành viên vẫn cần nó.

### 10.4. Tệp vẫn xuất hiện dù đã thêm pattern

Kiểm tra:

```bash
git check-ignore -v --no-index -- path/to/file
git status --short --ignored
```

Nếu không có quy tắc nào khớp, kiểm tra vị trí `.gitignore`, dấu `/`, wildcard và quy tắc phủ định. Nếu có quy tắc khớp nhưng tệp vẫn tracked, cần xử lý index.

### 10.5. Muốn xóa tệp khỏi lịch sử nhưng chỉ dùng `git rm --cached`

`git rm --cached` chỉ thay đổi phiên bản từ commit tiếp theo. Lịch sử cũ vẫn giữ nội dung. Với secret đã lộ, ưu tiên thu hồi credential; việc làm sạch history là công việc riêng cần phối hợp và kiểm tra tác động tới người cộng tác.

## 11. Quy trình thực hành và checklist

Khi muốn bỏ theo dõi một tệp đã commit nhưng giữ bản local, thực hiện theo thứ tự:

1. Xác định chính xác đường dẫn bằng `git ls-files -- path/to/file`.
2. Kiểm tra tệp có thay đổi staged hoặc unstaged cần giữ không bằng `git status` và `git diff`.
3. Thêm quy tắc phù hợp vào `.gitignore`.
4. Chạy `git rm --cached -- path/to/file` hoặc `git rm -r --cached -- directory/`.
5. Xác nhận tệp vẫn còn trong working tree và không còn trong kết quả `git ls-files`.
6. Dùng `git check-ignore -v --no-index` để xác nhận pattern đã khớp.
7. Xem `git status`, kiểm tra diff staged và bảo đảm commit sẽ chỉ xóa đúng đường dẫn khỏi repository.
8. Commit `.gitignore` cùng thay đổi index.
9. Thông báo cho đồng đội cách tạo lại tệp local hoặc dùng file mẫu nếu họ vẫn cần nội dung đó.

Các lệnh kiểm tra tổng hợp:

```bash
git status --short
git ls-files -- path/to/file
git check-ignore -v --no-index -- path/to/file
git diff --cached -- .gitignore path/to/file
```

Không dùng `git rm -f` hoặc `git clean` để xử lý nhanh nếu chưa kiểm tra nội dung staged, working tree và tệp cần giữ.

## 12. Ghi nhớ

- `.gitignore` bỏ qua tệp chưa được theo dõi; nó không tự bỏ tệp đã tracked khỏi index.
- Tệp đã commit tiếp tục được Git theo dõi dù khớp ignore pattern.
- Dùng `git rm --cached -- <path>` để bỏ một tệp khỏi index nhưng giữ bản local; dùng `-r` cho thư mục.
- Commit thao tác đó sẽ ghi nhận việc xóa đường dẫn khỏi phiên bản repository; đồng đội có thể mất bản tracked khi pull và cần tạo lại file local.
- `git ls-files` kiểm tra đường dẫn tracked; `git check-ignore -v --no-index` kiểm tra rule kể cả với đường dẫn tracked.
- `git rm --cached` không xóa phiên bản trong các commit cũ. Secret đã commit cần được thu hồi hoặc xoay vòng, và xử lý lịch sử riêng nếu cần.
- `.gitignore` điều khiển việc bỏ qua đường dẫn; `.gitattributes` điều khiển thuộc tính và cách Git xử lý nội dung.

Khi một tệp đã được commit, hãy nghĩ tới index trước khi nghĩ tới ignore rule. Thêm `.gitignore` để ngăn tệp mới bị thêm vào; dùng `git rm --cached` để chủ động ngừng theo dõi tệp đã có trong repository.
