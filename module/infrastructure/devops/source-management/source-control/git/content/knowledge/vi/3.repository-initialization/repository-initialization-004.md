# Kiểm tra kho mã bằng git status và git rev-parse

Sau khi mở terminal, điều đầu tiên cần biết là bạn đang đứng trong repository nào, repository có working tree hay không, và những thay đổi nào đang chờ xử lý. Git cung cấp hai lệnh bổ trợ cho việc này: `git status` mô tả trạng thái làm việc của repository; `git rev-parse` giúp xác định các đường dẫn và thuộc tính nội bộ của repository.

Hai lệnh thường được dùng cùng nhau trong thao tác hằng ngày và trong script. `git status` trả lời câu hỏi “đang có thay đổi gì?”, còn `git rev-parse` trả lời “Git đang nhận diện repository này như thế nào và các thư mục quản trị nằm ở đâu?”.

Sau bài này, bạn có thể:

- Đọc trạng thái working tree và staging area bằng `git status`.
- Phân biệt thay đổi đã stage, chưa stage, chưa được theo dõi và bị ignore.
- Dùng chế độ short và porcelain để đọc kết quả ổn định.
- Nhận diện branch, detached HEAD và trạng thái upstream.
- Xác định repository root, Git directory và common directory bằng `git rev-parse`.
- Phân biệt repository thường, bare repository, thư mục con và linked worktree.
- Kết hợp hai lệnh để chẩn đoán vị trí và trạng thái repository trong script.

## 1. Kiểm tra nhanh bằng git status

Chạy:

~~~bash
git status
~~~

Lệnh cho biết branch hiện tại, trạng thái so với upstream nếu có, các thay đổi trong staging area, thay đổi chưa stage và file chưa được theo dõi. Đây là lệnh nên chạy trước khi commit, merge, rebase, checkout hoặc áp dụng một patch.

Ví dụ kết quả:

~~~text
On branch feature/search
Your branch is up to date with 'origin/feature/search'.

Changes to be committed:
  modified:   src/Search.java

Changes not staged for commit:
  modified:   README.md

Untracked files:
  docs/search-notes.md
~~~

Trong ví dụ:

- `src/Search.java` đã được stage và sẽ nằm trong snapshot nếu tạo commit ngay.
- `README.md` đã thay đổi trong working tree nhưng chưa được stage.
- `docs/search-notes.md` là file mới mà Git chưa theo dõi.

`git status` không tự thay đổi file, index hoặc lịch sử. Đây là lệnh đọc trạng thái an toàn.

## 2. Working tree, staging area và trạng thái file

Để hiểu output của `git status`, cần phân biệt ba vùng:

~~~text
        git add                 git commit
Working tree ----------> Staging area ----------> Repository
     ^                         |
     |                         |
     +------ git restore ------+
~~~

- Working tree là các file và thư mục bạn nhìn thấy, mở và chỉnh sửa.
- Staging area được Git lưu trong index, chứa nội dung sẽ được đưa vào commit tiếp theo.
- Repository chứa các commit và object đã được ghi vào lịch sử.

Một file tracked có thể khác với commit hiện tại, khác với index hoặc khác ở cả hai nơi. Vì vậy, Git phân biệt thay đổi trong index với thay đổi trong working tree.

Ví dụ:

~~~bash
# Stage thay đổi của file
git add src/Search.java

# Sửa tiếp file sau khi đã stage
git status
~~~

Lúc này file có thể xuất hiện ở cả phần “Changes to be committed” và “Changes not staged for commit”. Điều đó có nghĩa snapshot trong index và nội dung hiện tại của working tree khác nhau.

Để xem chi tiết:

~~~bash
# Thay đổi chưa stage: working tree so với index
git diff

# Thay đổi đã stage: index so với HEAD
git diff --cached
~~~

`git status` tóm tắt trạng thái; `git diff` giúp xem nội dung khác biệt.

## 3. Đọc trạng thái dạng ngắn

Khi cần kết quả gọn, dùng:

~~~bash
git status --short
~~~

Mỗi dòng bắt đầu bằng hai vị trí trạng thái:

~~~text
XY path
~~~

- `X` mô tả thay đổi trong index so với commit hiện tại.
- `Y` mô tả thay đổi trong working tree so với index.

Một số mã thường gặp:

| Mã | Ý nghĩa |
| --- | --- |
| ` M` | File tracked bị sửa trong working tree, chưa stage. |
| `M ` | File đã stage thay đổi. |
| `MM` | File đã stage một thay đổi rồi tiếp tục bị sửa trong working tree. |
| `A ` | File mới đã được stage. |
| `D ` | File đã stage việc xóa. |
| ` D` | File bị xóa trong working tree nhưng thay đổi chưa stage. |
| `??` | File chưa được Git theo dõi. |
| `!!` | File bị ignore, khi yêu cầu hiển thị ignored files. |

Khoảng trắng trong hai cột có ý nghĩa. Ví dụ ` M` và `M ` mô tả hai vùng khác nhau, nên không xóa khoảng trắng khi đọc output.

Với rename hoặc copy, output có thể hiển thị mã trạng thái tương ứng và đường dẫn cũ/mới. Với xung đột merge, các mã như `UU`, `AA` hoặc `DD` cho biết trạng thái unmerged cụ thể. Khi cần hiểu chi tiết xung đột, dùng thêm `git diff` và `git status` dạng đầy đủ.

## 4. Hiển thị branch và upstream

Để xem branch cùng trạng thái file trong một output ngắn:

~~~bash
git status --short --branch
~~~

Ví dụ:

~~~text
## feature/search...origin/feature/search [ahead 2]
 M src/Search.java
?? docs/search-notes.md
~~~

Dòng đầu cho biết branch hiện tại và quan hệ với upstream nếu branch đã được cấu hình theo dõi. `[ahead 2]` cho biết local branch có hai commit chưa có trên upstream. Tùy tình trạng, Git cũng có thể hiển thị `behind`, `ahead` và `behind` cùng lúc, hoặc trạng thái up to date.

Nếu branch chưa có upstream, Git có thể chỉ hiển thị tên branch mà không có phần so sánh. Nếu HEAD đang detached, output sẽ thông báo trạng thái detached thay vì tên branch thông thường.

Lệnh này không fetch remote. Thông tin ahead/behind được tính dựa trên các remote-tracking refs local hiện có, nên có thể đã cũ nếu remote vừa thay đổi mà bạn chưa fetch.

Muốn cập nhật thông tin remote trước khi xem trạng thái so sánh:

~~~bash
git fetch
git status --short --branch
~~~

Fetch cập nhật remote-tracking refs nhưng không tự merge hoặc rebase branch hiện tại.

## 5. Hiển thị file chưa theo dõi và file bị ignore

Theo mặc định, Git thường gom các file chưa theo dõi trong cùng một thư mục thành một dòng để output dễ đọc. Nếu cần liệt kê từng file:

~~~bash
git status --untracked-files=all
~~~

Để xem cả file bị ignore:

~~~bash
git status --short --ignored
~~~

File ignored thường được đánh dấu `!!` trong output short. Điều này hữu ích khi cần xác nhận vì sao một file build hoặc file cấu hình local không xuất hiện trong danh sách untracked.

`git status` không có nghĩa là file ignored sẽ được stage tự động. Muốn xem quy tắc ignore nào đang áp dụng, dùng:

~~~bash
git check-ignore -v path/to/file
~~~

Chỉ bỏ ignore hoặc force-add file khi bạn hiểu vì sao file bị ignore và chắc chắn file đó nên được lưu trong repository.

## 6. Dùng porcelain output cho script

Output mặc định của `git status` được thiết kế cho con người đọc. Nội dung và cách trình bày có thể thay đổi giữa phiên bản Git, nên script không nên phân tích các câu tiếng Anh như “Changes not staged for commit”.

Git cung cấp porcelain format để chương trình đọc. Ví dụ:

~~~bash
git status --porcelain=v1
~~~

Hoặc phiên bản 2:

~~~bash
git status --porcelain=v2 --branch
~~~

Porcelain output có định dạng ổn định hơn output dành cho người dùng. Version 1 sử dụng mã trạng thái hai ký tự và đường dẫn. Version 2 có cấu trúc record rõ hơn, cung cấp thêm thông tin về branch và trạng thái file.

Khi tên file có dấu cách, tab, ký tự xuống dòng hoặc ký tự đặc biệt, việc phân tích output theo dòng có thể không an toàn. Dùng `-z` để phân tách bằng NUL:

~~~bash
git status --porcelain=v1 -z
~~~

Trong script, hãy dùng parser hiểu đúng định dạng porcelain và xử lý đường dẫn kết thúc bằng NUL. Không tự tách output bằng khoảng trắng vì tên file hợp lệ có thể chứa khoảng trắng.

Ví dụ kiểm tra nhanh xem repository có thay đổi hay không:

~~~bash
if test -z "$(git status --porcelain)"; then
    echo "Working tree and index are clean."
else
    echo "Repository has pending changes."
fi
~~~

Đoạn ví dụ này phù hợp cho kiểm tra đơn giản trong shell. Nếu cần xử lý mọi tên file có ký tự đặc biệt hoặc đưa ra quyết định dựa trên loại thay đổi, hãy dùng porcelain với `-z` và parser phù hợp.

## 7. git rev-parse dùng để làm gì?

`git rev-parse` là lệnh cấp thấp giúp Git diễn giải revision và in ra thông tin nội bộ. Trong công việc kiểm tra repository, nó thường được dùng để xác định:

- Repository root.
- Đường dẫn Git directory.
- Đường dẫn common directory được chia sẻ giữa các worktree.
- Bạn đang ở trong working tree, Git directory hay bare repository.
- Đường dẫn tới một file nội bộ như index hoặc object database.
- Định dạng hash object của repository.

Lệnh này đặc biệt hữu ích trong script vì không cần giả định người dùng đang chạy từ thư mục gốc.

## 8. Xác định repository root và vị trí hiện tại

Để lấy đường dẫn tuyệt đối tới thư mục gốc working tree:

~~~bash
git rev-parse --show-toplevel
~~~

Ví dụ, dù terminal đang ở `src/service/search`, lệnh vẫn trả về root của repository.

Để xem đường dẫn tương đối từ root tới thư mục hiện tại:

~~~bash
git rev-parse --show-prefix
~~~

Để xem số thư mục cần đi lên từ vị trí hiện tại để tới root:

~~~bash
git rev-parse --show-cdup
~~~

Ví dụ, nếu đang ở root, `--show-prefix` và `--show-cdup` trả chuỗi rỗng. Nếu đang ở `src/service`, `--show-prefix` có thể trả `src/service/`, còn `--show-cdup` có thể trả `../../`.

Ba lệnh này giúp script tìm file theo đường dẫn repository thay vì phụ thuộc vào thư mục terminal đang đứng.

## 9. Phân biệt Git directory và common directory

Lấy Git directory của repository hiện tại:

~~~bash
git rev-parse --git-dir
~~~

Muốn đường dẫn tuyệt đối:

~~~bash
git rev-parse --absolute-git-dir
~~~

Với repository thông thường, Git directory thường là `.git`. Nhưng không phải lúc nào `.git` cũng là một thư mục. Trong linked worktree, `.git` bên trong working tree có thể là file trỏ tới Git directory riêng của worktree.

Để lấy common directory:

~~~bash
git rev-parse --git-common-dir
~~~

Trong linked worktree, Git directory riêng chứa thông tin như HEAD và index của worktree đó, còn common directory chứa object database và các refs được chia sẻ. Với repository không dùng linked worktree, hai đường dẫn này thường trỏ cùng một nơi.

Vì vậy, không nên viết script bằng cách giả định `.git` luôn là thư mục ngay dưới repository root. Dùng `git rev-parse --git-dir` hoặc `--git-common-dir` để lấy đường dẫn Git đã phân giải.

## 10. Nhận diện loại repository và vị trí hiện tại

Một số lệnh kiểm tra boolean:

~~~bash
git rev-parse --is-inside-work-tree
git rev-parse --is-inside-git-dir
git rev-parse --is-bare-repository
~~~

Kết quả là `true` hoặc `false`.

| Trạng thái | is-inside-work-tree | is-inside-git-dir | is-bare-repository |
| --- | --- | --- | --- |
| Trong working tree thông thường | true | false | false |
| Trong thư mục .git của repository không bare | false | true | false |
| Trong thư mục bare repository (Git directory) | false | true | true |

Nếu đang ở một thư mục con của working tree, `--is-inside-work-tree` vẫn trả `true`. Nếu đang ở bên ngoài repository, lệnh thường báo lỗi và trả exit code khác 0 thay vì trả `false`.

Một bare repository chứa dữ liệu Git nhưng không có working tree để chỉnh sửa file. Nó thường được dùng làm remote trung tâm hoặc kho lưu trữ dùng chung. `git status` không thể hiển thị thay đổi file working tree trong bare repository vì không có working tree như repository thông thường.

## 11. Lấy đường dẫn nội bộ bằng --git-path

Đừng tự ghép đường dẫn như `.git/index` hoặc `.git/objects` trong script. Dùng:

~~~bash
git rev-parse --git-path index
git rev-parse --git-path objects
git rev-parse --git-path hooks
~~~

`--git-path` yêu cầu Git phân giải đường dẫn bên trong Git directory. Nó có thể tính đến các thiết lập như `GIT_OBJECT_DIRECTORY`, `GIT_INDEX_FILE` và một số cấu hình lưu trữ đặc biệt.

Ví dụ lấy đường dẫn index:

~~~bash
git rev-parse --git-path index
~~~

Đây là staging index của repository hiện tại. Trong một linked worktree, index riêng của worktree có thể nằm trong thư mục quản trị worktree thay vì common directory.

Để xác định object format:

~~~bash
git rev-parse --show-object-format
~~~

Kết quả thường là `sha1` hoặc `sha256`. Điều này hữu ích cho công cụ cần xử lý OID mà không giả định độ dài cố định.

## 12. Kiểm tra HEAD và branch bằng rev-parse

Để xem tên branch hiện tại:

~~~bash
git rev-parse --abbrev-ref HEAD
~~~

Nếu HEAD đang gắn với branch, lệnh trả về tên ngắn như `main` hoặc `feature/search`. Nếu HEAD detached, kết quả có thể là `HEAD`, vì không có branch ngắn tương ứng.

Để kiểm tra HEAD có phân giải được thành commit hay không:

~~~bash
git rev-parse --verify HEAD
~~~

Trong repository chưa có commit đầu tiên, branch có thể đang ở trạng thái unborn và `HEAD` chưa phân giải được thành object commit. Lệnh `--verify` sẽ thất bại. Đây là tình huống bình thường với repository mới sau `git init` nhưng trước commit đầu tiên.

Nếu branch có upstream, có thể truy vấn tên đầy đủ của upstream:

~~~bash
git rev-parse --abbrev-ref --symbolic-full-name '@{upstream}'
~~~

Lệnh này sẽ thất bại nếu branch hiện tại chưa cấu hình upstream. Hãy xử lý exit code thay vì giả định branch nào cũng theo dõi một remote branch.

## 13. Kết hợp status và rev-parse trong một quy trình

Khi tiếp nhận một thư mục dự án hoặc chạy script từ thư mục con, có thể kiểm tra lần lượt:

~~~bash
# 1. Xác nhận đây là working tree
git rev-parse --is-inside-work-tree

# 2. Lấy repository root
git rev-parse --show-toplevel

# 3. Lấy Git directory và common directory
git rev-parse --absolute-git-dir
git rev-parse --git-common-dir

# 4. Xem branch và trạng thái thay đổi
git status --short --branch

# 5. Kiểm tra thay đổi chi tiết
git diff
git diff --cached
~~~

Nếu `--is-inside-work-tree` không trả `true`, hãy xác định bạn đang ở bare repository, bên trong Git directory hay ngoài repository. Đừng chạy các lệnh thao tác file dựa trên giả định rằng luôn có working tree.

Một đoạn script shell minh họa:

~~~bash
#!/bin/sh
set -eu

if ! git rev-parse --git-dir >/dev/null 2>&1; then
    echo "Current directory is not inside a Git repository."
    exit 1
fi

if [ "$(git rev-parse --is-bare-repository)" = "true" ]; then
    echo "This is a bare repository."
    exit 0
fi

if [ "$(git rev-parse --is-inside-work-tree)" != "true" ]; then
    echo "Current directory is inside Git metadata, not a working tree."
    exit 1
fi

root=$(git rev-parse --show-toplevel)
echo "Repository root: $root"
git status --short --branch
~~~

Script này phân biệt ba trường hợp cơ bản: không phải repository, bare repository và working tree. Nếu đang ở trong Git directory nhưng không ở working tree, script báo riêng để tránh coi thư mục metadata như thư mục mã nguồn.

## 14. Tình huống thực tế

### Terminal đang ở thư mục con

Bạn mở terminal tại `project/src/service` và muốn xác định root trước khi gọi script:

~~~bash
git rev-parse --show-toplevel
git rev-parse --show-prefix
git status --short --branch
~~~

`git status` vẫn báo trạng thái toàn repository nếu không truyền pathspec. `--show-prefix` giúp biết vị trí hiện tại tương đối với root.

### Repository mới chưa có commit

Sau `git init`, kiểm tra:

~~~bash
git status --short --branch
git rev-parse --is-inside-work-tree
git rev-parse --verify HEAD
~~~

Repository đã có working tree, nhưng HEAD có thể chưa trỏ tới commit hợp lệ. `git rev-parse --verify HEAD` thất bại cho tới khi commit đầu tiên được tạo. Không nên coi điều này là repository hỏng.

### Đang làm việc trong linked worktree

Kiểm tra:

~~~bash
git rev-parse --show-toplevel
git rev-parse --absolute-git-dir
git rev-parse --git-common-dir
git status --short --branch
~~~

Git directory của worktree có thể khác common directory. Mỗi worktree có HEAD và index riêng, còn object database được chia sẻ. Điều này giúp giải thích vì sao đường dẫn `.git` có thể là file và vì sao không nên hard-code `.git/index`.

### Script cần biết có thay đổi chưa commit

Dùng porcelain:

~~~bash
git status --porcelain
~~~

Nếu output rỗng, index và working tree không có thay đổi được status báo cáo. Nếu cần bao gồm file ignored hoặc untracked chi tiết, thêm tùy chọn tương ứng. Đừng dùng output mặc định để quyết định rằng không có file ignored nào trong thư mục.

## 15. Những lỗi thường gặp

### Chạy git status ở ngoài repository

Git báo không phải repository. Dùng `git rev-parse --git-dir` để kiểm tra trước khi script thực hiện các bước phụ thuộc repository.

### Nghĩ git status chỉ hiển thị thay đổi chưa stage

Không đúng. Nó hiển thị cả thay đổi staged, unstaged, untracked và một số thông tin branch/upstream. Dùng `git diff` và `git diff --cached` để xem nội dung từng vùng.

### Không thấy file mới trong git status

File có thể đang bị ignore hoặc nằm ngoài working tree. Dùng `git status --short --ignored` và `git check-ignore -v path/to/file` để chẩn đoán.

### Nhầm M ở cột đầu và cột thứ hai

Cột đầu là index; cột thứ hai là working tree. `M ` là thay đổi đã stage, còn ` M` là thay đổi chưa stage.

### Phân tích output git status thông thường trong script

Không nên dựa vào câu chữ dành cho người dùng. Dùng `--porcelain=v1` hoặc `--porcelain=v2`; dùng `-z` nếu cần xử lý an toàn tên file có ký tự đặc biệt.

### Giả định .git luôn là thư mục

Trong linked worktree hoặc submodule, `.git` có thể là file trỏ tới Git directory thực. Dùng `git rev-parse --git-dir`, `--absolute-git-dir` và `--git-common-dir`.

### git rev-parse --verify HEAD thất bại sau git init

Repository có thể chưa có commit đầu tiên. Kiểm tra `git status` và trạng thái branch; tạo commit đầu tiên khi đã có nội dung cần lưu.

## 16. Ghi nhớ

- `git status` cho biết branch, upstream và thay đổi trong index/working tree.
- `git status --short` dùng hai cột: X là trạng thái index, Y là trạng thái working tree.
- `??` biểu thị file chưa được theo dõi; `!!` biểu thị file ignored khi bật hiển thị ignored.
- Dùng `--porcelain=v1` hoặc `--porcelain=v2` khi script cần output ổn định; thêm `-z` để xử lý tên file đặc biệt.
- `git rev-parse --show-toplevel` lấy repository root; `--show-prefix` và `--show-cdup` mô tả vị trí hiện tại so với root.
- `--git-dir`, `--absolute-git-dir` và `--git-common-dir` giúp xác định vùng metadata, kể cả với linked worktree.
- `--is-inside-work-tree`, `--is-inside-git-dir` và `--is-bare-repository` phân biệt ngữ cảnh repository.
- `--git-path` phân giải đường dẫn nội bộ mà không cần hard-code `.git`.
- `git rev-parse --verify HEAD` có thể thất bại ở repository chưa có commit đầu tiên.

Kết hợp `git status` và `git rev-parse` giúp bạn biết repository đang ở đâu, có loại working tree nào và những thay đổi nào đang chờ xử lý. Đây là nền tảng để thao tác an toàn trong terminal, viết script Git đáng tin cậy và chẩn đoán repository ở các cấu trúc khác nhau.
