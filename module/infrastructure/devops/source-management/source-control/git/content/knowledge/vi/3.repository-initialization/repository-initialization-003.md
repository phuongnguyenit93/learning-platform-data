# Vai trò của .git, thư mục làm việc và kho mã bare

Một repository Git thường có ba phần gắn bó với nhau: **thư mục làm việc** (working tree) chứa các file bạn đọc và chỉnh sửa, **index** lưu nội dung đã stage để chuẩn bị commit, và **Git directory** chứa object cùng metadata để Git quản lý lịch sử. Trong một repository thông thường, Git directory thường nằm ở thư mục ẩn `.git` tại gốc dự án.

Một **bare repository** vẫn có object database, refs và cấu hình Git, nhưng không có working tree để checkout và chỉnh sửa file. Bare repository thường được dùng làm remote trung tâm hoặc nơi lưu bản sao repository. Hiểu vai trò của từng phần giúp bạn biết lệnh Git đang đọc hoặc cập nhật dữ liệu ở đâu, đồng thời chọn đúng kiểu repository khi khởi tạo dự án hay dựng máy chủ Git.

## 1. Ba thành phần trong repository thông thường

Khi chạy `git init` trong một thư mục dự án, Git tạo metadata cần thiết để quản lý repository. Mô hình khái quát:

```text
storefront/                 <- working tree (thư mục làm việc)
|-- .git/                   <- Git directory
|   |-- HEAD
|   |-- config
|   |-- index               <- staging area (được lưu trong file index)
|   |-- objects/            <- object database
|   |-- refs/               <- branch, tag và refs khác
|   |-- hooks/              <- hook mẫu hoặc hook của repository
|   `-- logs/               <- reflog, nếu được bật/tạo
|-- src/
|-- README.md
`-- .gitignore
```

Ba thành phần chính có vai trò khác nhau:

| Thành phần | Lưu gì? | Bạn dùng nó khi nào? |
|---|---|---|
| Working tree | Các file và thư mục có thể mở, sửa, tạo hoặc xóa | Viết code, chỉnh tài liệu, chạy build và kiểm thử |
| Index (staging area) | Snapshot nội dung được chọn cho commit tiếp theo | Chọn chính xác thay đổi nào sẽ đi vào commit |
| Git directory | Object database, refs, `HEAD`, cấu hình và metadata khác | Lưu lịch sử, xác định branch/commit, quản lý repository |

Một thay đổi trong working tree chưa tự động trở thành dữ liệu lịch sử. Bạn thường đưa nội dung cần commit vào index bằng `git add`, sau đó tạo commit bằng `git commit`. Commit lưu snapshot của index và metadata lịch sử trong Git directory.

## 2. Working tree: nơi bạn làm việc với file

Working tree là thư mục chứa phiên bản file mà bạn đang thao tác. Khi checkout một branch hoặc commit, Git cập nhật working tree để phản ánh snapshot được chọn. Bạn có thể sửa file bằng IDE, terminal hoặc bất kỳ công cụ nào; Git nhận biết khác biệt khi bạn chạy các lệnh như `git status` và `git diff`.

Ví dụ:

```bash
git status
git diff
```

- `git status` cho biết file nào đã thay đổi, đã stage, chưa được theo dõi hoặc bị xóa.
- `git diff` so sánh working tree với index, hiển thị thay đổi chưa stage.

Working tree có thể chứa file tracked, untracked và ignored. Git không tự lưu mọi file đang có trong thư mục. File untracked chỉ được đưa vào index khi bạn chủ động add; file ignored thường bị bỏ qua theo quy tắc `.gitignore`, trừ khi bạn chỉ rõ cách thêm phù hợp.

Bạn có thể xem gốc working tree hiện tại:

```bash
git rev-parse --show-toplevel
```

Lệnh này hữu ích khi bạn đang ở một thư mục con và muốn biết repository root. Trong bare repository, không có working tree nên lệnh này không trả về một gốc working tree thông thường.

## 3. Index: vùng staging giữa working tree và commit

Index (còn gọi là staging area) là nơi Git lưu trạng thái nội dung đã chọn cho commit tiếp theo. Trong repository thông thường, index thường được lưu ở file `.git/index`. File này là dữ liệu nội bộ của Git; không nên tự chỉnh sửa bằng trình soạn thảo.

Ví dụ quy trình:

```bash
# Sửa README.md và src/app.js trong working tree
git status

# Chọn hai file để đưa vào index
git add README.md src/app.js

# Xem thay đổi đã stage
git diff --cached

# Tạo commit từ index
git commit -m "Update application setup"
```

Điểm quan trọng là commit được tạo từ index, không phải trực tiếp từ toàn bộ working tree. Nhờ vậy, bạn có thể chia thay đổi thành các commit nhỏ, có mục đích rõ ràng, ngay cả khi một file còn nhiều phần đang làm dở.

Xem trạng thái của index:

```bash
git ls-files --stage
```

Lệnh hiển thị các mục đã được stage cùng mode, object ID và stage number. Trong xung đột merge, index có thể chứa nhiều stage cho cùng một đường dẫn cho đến khi bạn giải quyết xung đột và stage kết quả.

## 4. Git directory và vai trò của thư mục .git

Git directory là nơi Git lưu dữ liệu quản lý repository. Với repository thông thường được tạo bằng `git init`, Git directory thường là thư mục `.git` ở gốc working tree.

Các thành phần quan trọng thường gặp:

| Đường dẫn trong Git directory | Vai trò |
|---|---|
| `HEAD` | Cho biết commit hiện tại hoặc symbolic ref của branch đang checkout |
| `config` | Cấu hình local của repository như remote, tên người dùng, thiết lập merge và các tùy chọn khác |
| `index` | Nội dung và trạng thái staging area |
| `objects/` | Object database chứa blob, tree, commit, tag và các object liên quan |
| `refs/` | Các tham chiếu như branch và tag; một số ref có thể nằm trong `packed-refs` |
| `hooks/` | Hook được chạy ở những thời điểm Git xác định, nếu được cấu hình |
| `logs/` | Reflog ghi lại các lần ref thay đổi, nếu reflog được bật và có dữ liệu |
| `info/` | Metadata local như `exclude` và `attributes` áp dụng riêng cho clone |

Không phải mọi repository đều có đủ tất cả file/thư mục kể trên ngay từ đầu. Git tạo một số thành phần khi chúng cần thiết; một số ref có thể được đóng gói thay vì nằm thành file riêng. Đây là cấu trúc nội bộ, nên hãy dùng lệnh Git để đọc và thay đổi thay vì thao tác trực tiếp trong `.git`.

### HEAD và branch

Trong repository thông thường, `HEAD` thường là symbolic ref trỏ đến branch hiện tại, ví dụ:

```text
ref: refs/heads/main
```

Branch `main` sau đó trỏ đến một commit. Khi bạn tạo commit mới, Git cập nhật ref branch để trỏ đến commit mới; các object commit cũ vẫn tồn tại nếu còn được tham chiếu hoặc chưa bị dọn.

Kiểm tra:

```bash
git symbolic-ref -q HEAD
git rev-parse HEAD
git branch --show-current
```

Nếu đang ở detached `HEAD`, `git branch --show-current` không in tên branch và `HEAD` chứa trực tiếp OID commit thay vì symbolic ref.

### Objects và lịch sử

Thư mục `objects/` lưu nội dung theo địa chỉ nội dung. Git sử dụng các loại object chính:

- **Blob:** nội dung file.
- **Tree:** cấu trúc thư mục và liên kết đến blob/tree con.
- **Commit:** snapshot tree, parent commit và metadata.
- **Tag object:** metadata của annotated tag, có thể có chữ ký.

Git có thể lưu object dạng loose hoặc gom vào packfile. Không nên tự xóa hoặc sửa file trong `objects/`; làm vậy có thể khiến commit hoặc file không đọc được.

## 5. .git không phải lúc nào cũng là thư mục

Trong repository thông thường đơn giản, `.git` là một thư mục. Nhưng ở một số cấu trúc Git, `.git` có thể là **file văn bản** trỏ đến Git directory nằm ở nơi khác.

Các trường hợp thường gặp:

- **Linked worktree:** mỗi worktree phụ có file `.git` trỏ đến metadata riêng của worktree; phần lớn object và refs được chia sẻ với Git directory chung.
- **Submodule:** thư mục submodule thường có file `.git` trỏ đến metadata được quản lý trong Git directory của superproject.
- **Separate Git directory:** khi khởi tạo hoặc clone với tùy chọn tách Git directory, working tree và metadata có thể nằm ở hai vị trí khác nhau.

Vì vậy, đừng giả định có thể tìm toàn bộ metadata bằng cách mở `<project>/.git/`. Hãy hỏi Git về vị trí thực tế:

```bash
git rev-parse --git-dir
git rev-parse --git-common-dir
git rev-parse --show-toplevel
```

- `--git-dir` cho biết Git directory đang dùng cho repository/worktree hiện tại.
- `--git-common-dir` cho biết Git directory chung, đặc biệt hữu ích với linked worktree.
- `--show-toplevel` cho biết gốc working tree nếu có.

Đường dẫn được in ra có thể là tương đối hoặc tuyệt đối tùy môi trường và vị trí chạy lệnh. Dùng `git rev-parse` đáng tin cậy hơn việc tự suy luận từ tên thư mục.

### Tách Git directory khỏi working tree

Bạn có thể tạo repository với Git directory đặt riêng:

```bash
git init --separate-git-dir=/srv/git-metadata/storefront.git ./storefront
```

Trong trường hợp này, working tree nằm ở `./storefront`, còn metadata nằm ở `/srv/git-metadata/storefront.git`; Git tạo file `.git` trong working tree để trỏ đến vị trí metadata. Tùy chọn này hữu ích khi cần đặt metadata ở ổ đĩa hoặc vùng lưu trữ riêng, nhưng hãy giữ nguyên đường dẫn và quyền truy cập để repository tiếp tục hoạt động.

## 6. Bare repository là gì?

Bare repository là repository không có working tree. Git directory của nó nằm trực tiếp ở thư mục repository, thường có tên kết thúc bằng `.git` theo quy ước:

```text
storefront.git/
|-- HEAD
|-- config
|-- objects/
|-- refs/
|-- hooks/
`-- ...
```

Không có thư mục `.git` lồng bên trong và không có các file dự án đã checkout. Bare repository vẫn có object database, branch refs, tags, `HEAD`, cấu hình và hook. Trong bare repository, `core.bare` thường được đặt là `true`.

Tên có hậu tố `.git` chỉ là quy ước phổ biến, không phải điều kiện bắt buộc. Một thư mục có tên `storefront` vẫn có thể là bare repository nếu được khởi tạo ở chế độ bare.

Kiểm tra repository hiện tại:

```bash
git rev-parse --is-bare-repository
git rev-parse --is-inside-work-tree
```

Trong bare repository, lệnh đầu trả về `true`; lệnh thứ hai không xác nhận một working tree thông thường. Các lệnh cần working tree như chỉnh sửa file hoặc xem diff working tree không có nơi để thao tác.

## 7. Tạo repository thường và bare repository

### Khởi tạo repository có working tree

Tạo thư mục dự án và khởi tạo Git:

```bash
mkdir storefront
cd storefront
git init
```

Git tạo Git directory (thường là `.git`) bên trong working tree. Bạn có thể thêm file và commit:

```bash
echo "# Storefront" > README.md
git add README.md
git commit -m "Initial commit"
```

Nếu muốn chọn tên branch ban đầu ngay khi khởi tạo:

```bash
git init --initial-branch=main
```

Trên phiên bản Git chưa hỗ trợ `--initial-branch`, có thể cấu hình `init.defaultBranch` trước khi init hoặc đổi tên branch sau khi tạo.

### Khởi tạo bare repository

Để tạo repository không có working tree:

```bash
git init --bare storefront.git
```

Hoặc chỉ định branch mặc định trên phiên bản hỗ trợ:

```bash
git init --bare --initial-branch=main storefront.git
```

Bare repository thường được dùng làm remote trung tâm. Developer làm việc trong clone thông thường rồi push commit lên bare remote. Bare repository nhận object và cập nhật refs mà không phải checkout file vào một working tree dùng chung.

### So sánh nhanh

| Tiêu chí | Repository thường | Bare repository |
|---|---|---|
| Working tree | Có | Không |
| Index phục vụ staging | Có | Không có index working tree thông thường |
| Git directory | Thường là `.git/` bên trong dự án | Chính thư mục repository |
| Có object database và refs | Có | Có |
| Dùng `git status` để xem file đang sửa | Có | Không có working tree để xem |
| Dùng làm nơi nhận push trung tâm | Không phải lựa chọn phù hợp mặc định | Phù hợp |
| Dùng để trực tiếp sửa và build dự án | Có | Cần clone sang working tree riêng |

## 8. Vì sao remote trung tâm thường là bare repository?

Nếu nhiều người push vào một repository có working tree đang checkout, ref được cập nhật có thể không khớp với file đang nằm trong working tree. Điều này tạo nguy cơ gây nhầm lẫn hoặc để working tree ở trạng thái không phản ánh branch mới.

Bare repository tránh vấn đề đó vì không có working tree đang checkout. Khi nhận push, Git chỉ cập nhật object và refs. Các thành viên khác fetch hoặc pull để cập nhật clone của họ.

Ví dụ quy trình:

```text
Developer A (clone thường) ----+
                               |
                               v
                        Bare remote
                               ^
                               |
Developer B (clone thường) ----+
```

Tạo bare remote trên máy chủ:

```bash
git init --bare --initial-branch=main /srv/git/storefront.git
```

Trong clone của developer:

```bash
git remote add origin ssh://git@git.example.com/srv/git/storefront.git
git push -u origin main
```

Developer khác clone từ remote:

```bash
git clone ssh://git@git.example.com/srv/git/storefront.git
```

Bare repository chỉ là kho Git trên máy chủ. Để hoạt động qua mạng, nó cần được cung cấp qua SSH, Git protocol, HTTP(S) hoặc nền tảng hosting và được bảo vệ bằng xác thực, phân quyền, backup và chính sách nhận push.

## 9. Bare repository khác mirror clone như thế nào?

Bare mô tả repository không có working tree. Mirror mô tả một cách clone/cấu hình để sao chép các refs mà remote công bố.

```bash
git clone --bare https://git.example.com/platform/storefront.git storefront-bare.git
git clone --mirror https://git.example.com/platform/storefront.git storefront-mirror.git
```

`--bare` tạo repository bare, thường lấy branch heads theo quy tắc clone bare. `--mirror` cũng tạo bare repository nhưng cấu hình refspec rộng `+refs/*:refs/*`, nhằm ánh xạ mọi ref mà nguồn công bố trong cùng namespace. Mirror clone thích hợp cho mục đích sao chép refs; bare clone có thể phù hợp khi chỉ cần một repository bare với các branch thông thường.

Không phải mọi dữ liệu của dịch vụ hosting đều nằm trong Git refs và object. Pull request, issue, comment, quyền truy cập, branch protection, artifact, Git LFS object và repository submodule có thể cần được sao lưu riêng. Mirror clone cũng không thể lấy refs mà server ẩn hoặc không cho truy cập.

## 10. Nhận diện vị trí repository khi làm việc

Khi gặp một thư mục dự án không rõ cấu trúc, hãy dùng các lệnh sau:

```bash
git rev-parse --show-toplevel
git rev-parse --git-dir
git rev-parse --git-common-dir
git rev-parse --is-inside-work-tree
git rev-parse --is-bare-repository
```

Chúng lần lượt cho biết gốc working tree, Git directory, Git directory chung, trạng thái nằm trong working tree và trạng thái bare. Một số lệnh có thể không trả về giá trị như mong đợi nếu bạn chạy ngoài repository hoặc trong bare repository; hãy đọc lỗi cùng trạng thái để xác định vị trí hiện tại.

Bạn cũng có thể xem cấu hình local:

```bash
git config --local --list
```

Trong repository thông thường, cấu hình local thường nằm trong `.git/config`; với linked worktree hoặc cấu trúc Git directory tách rời, vị trí thực tế có thể khác. Dùng `git rev-parse --git-dir` để xác định Git directory đang được dùng.

## 11. Những thao tác không nên làm trực tiếp trong .git

Thư mục `.git` chứa dữ liệu quan trọng để Git hiểu lịch sử. Không nên:

- Xóa hoặc đổi tên tùy tiện `objects/`, `refs/`, `HEAD` hay `index`.
- Sửa file object nén trong `objects/` bằng trình soạn thảo.
- Xóa `index.lock` khi chưa xác nhận không còn tiến trình Git đang sử dụng.
- Copy riêng `.git` để thay cho quy trình backup đã kiểm chứng, nhất là khi repository dùng worktree, alternate object store, LFS hoặc submodule.
- Coi `.gitignore` là nơi lưu lịch sử; file này chỉ quy định đường dẫn untracked nào được bỏ qua.

Nếu cần sao lưu repository, hãy dùng chiến lược phù hợp như clone mirror, bundle hoặc backup toàn bộ repository và các thành phần liên quan. Nếu cần thay đổi refs hoặc cấu hình, dùng lệnh Git như `git branch`, `git update-ref`, `git config` theo đúng mục tiêu.

## 12. Bài tập thực hành

Thực hành trong thư mục thử nghiệm để quan sát cấu trúc repository mà không ảnh hưởng dự án thật.

1. Tạo thư mục `repo-normal`, chạy `git init` và liệt kê nội dung ẩn để xác định thư mục `.git`.
2. Tạo `README.md`, stage file bằng `git add`, rồi dùng `git status`, `git diff --cached` và `git ls-files --stage` để quan sát working tree và index.
3. Commit file, sau đó đọc `HEAD`, `config`, `refs` và `objects` bằng các lệnh Git phù hợp; không sửa trực tiếp metadata.
4. Chạy `git rev-parse --show-toplevel`, `--git-dir`, `--is-inside-work-tree` và `--is-bare-repository` để nhận diện repository thường.
5. Tạo bare repository bằng `git init --bare repo-remote.git`, rồi kiểm tra `--is-bare-repository`, `show-ref` và `symbolic-ref HEAD`.
6. Push branch từ repository thường lên bare repository, sau đó clone bare remote vào một working tree mới.
7. So sánh cấu trúc thư mục của repository thường và bare repository; giải thích vì sao bare remote không có file dự án đã checkout.
8. Nếu có môi trường phù hợp, tạo một linked worktree và kiểm tra `.git` trong worktree phụ là file trỏ đến metadata thay vì thư mục.

Bạn hoàn thành bài tập khi giải thích được working tree, index và Git directory khác nhau ra sao; xác định được `.git` thực tế nằm ở đâu; và chọn đúng giữa repository thường với bare repository cho nhu cầu làm việc hoặc lưu trữ remote.
