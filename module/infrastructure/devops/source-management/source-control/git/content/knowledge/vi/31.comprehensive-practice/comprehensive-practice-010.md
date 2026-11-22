# Thực hành worktree, sparse checkout và kho mã có submodule

Git có thể quản lý nhiều working tree từ cùng một repository, chỉ checkout một phần cây thư mục và nhúng repository khác dưới dạng submodule. Ba khả năng này giải quyết những nhu cầu khác nhau: worktree giúp làm nhiều nhánh song song mà không phải clone cả repository; sparse checkout giới hạn tệp xuất hiện trong working tree; submodule giúp dự án cha ghim một commit cụ thể của repository con.

Bài thực hành kết hợp cả ba khả năng trong một lab riêng. Bạn sẽ tạo một thư viện Git cục bộ, thêm nó vào ứng dụng dưới dạng submodule, tạo linked worktree cho nhánh tính năng, bật sparse checkout để chỉ lấy các khu vực cần thiết, cập nhật submodule và kiểm tra trạng thái giữa các working tree.

## 1. Mục tiêu và điều kiện

Sau bài thực hành, bạn có thể:

- Tạo linked worktree bằng git worktree add và kiểm tra danh sách worktree.
- Hiểu branch và object database được chia sẻ trong khi HEAD, index và working tree được tách theo worktree.
- Bật sparse checkout ở cone mode và chỉ định các thư mục cần làm việc.
- Nhận biết sparse checkout thay đổi working tree, không tự làm repository chỉ tải một phần object.
- Thêm, khởi tạo và kiểm tra submodule được ghim bằng gitlink.
- Phối hợp worktree, sparse checkout và submodule trong một workflow có thể kiểm chứng.
- Dọn worktree đúng cách mà không xóa nhầm nhánh hoặc dữ liệu chưa commit.

Yêu cầu: Git phiên bản hiện đại có hỗ trợ git switch, git worktree và git sparse-checkout; terminal Bash, Git Bash hoặc WSL; dung lượng đủ để tạo vài thư mục lab. Bài dùng repository local để không phụ thuộc dịch vụ Git bên ngoài.

## 2. Phân biệt ba khái niệm

| Tính năng | Quản lý điều gì? | Trường hợp sử dụng |
|---|---|---|
| Worktree | Nhiều working tree liên kết với cùng một repository | Mở nhánh hotfix trong thư mục riêng trong khi vẫn giữ nhánh feature đang làm |
| Sparse checkout | Tập đường dẫn được checkout vào working tree | Repository lớn nhưng công việc chỉ cần src/api và docs |
| Submodule | Một repository Git độc lập được tham chiếu tại một đường dẫn trong kho cha | Dùng thư viện hoặc thành phần có lịch sử và quyền phát hành riêng |

Worktree không phải là một clone độc lập: các worktree liên kết dùng chung object database và refs của repository chính, nhưng mỗi worktree có HEAD, index và working tree riêng. Sparse checkout quyết định phần nào của cây được hiện diện trong một working tree. Submodule có repository riêng; kho cha ghi nhận commit cụ thể của submodule bằng gitlink.

## 3. Tạo thư mục lab và repository thư viện

Tạo thư mục lab ở vị trí riêng. Biến LAB_ROOT trong ví dụ là đường dẫn tuyệt đối đến thư mục thực hành:

~~~bash
LAB_ROOT="$(pwd)/git-worktree-sparse-lab"
mkdir -p "$LAB_ROOT"
~~~

Tạo bare repository làm remote local cho thư viện:

~~~bash
git init --bare --initial-branch=main "$LAB_ROOT/math-core.git"
~~~

Tạo working repository để phát triển thư viện:

~~~bash
git init --initial-branch=main "$LAB_ROOT/math-core-work"
git -C "$LAB_ROOT/math-core-work" config user.name "Git Learner"
git -C "$LAB_ROOT/math-core-work" config user.email "learner@example.test"

printf '# Math Core\n\nLocal library for the Git lab.\n' > "$LAB_ROOT/math-core-work/README.md"
printf 'def add(a, b):\n    return a + b\n' > "$LAB_ROOT/math-core-work/math_core.py"

git -C "$LAB_ROOT/math-core-work" add README.md math_core.py
git -C "$LAB_ROOT/math-core-work" commit -m "Create math core library"
git -C "$LAB_ROOT/math-core-work" remote add origin "$LAB_ROOT/math-core.git"
git -C "$LAB_ROOT/math-core-work" push -u origin main
~~~

Kiểm tra bare remote đã nhận nhánh main:

~~~bash
git --git-dir="$LAB_ROOT/math-core.git" show-ref
~~~

Bare repository chỉ có dữ liệu Git, không có working tree. Trong bài lab, nó đóng vai trò remote local để submodule có thể fetch commit đã được push.

## 4. Tạo repository ứng dụng và commit nền

Khởi tạo ứng dụng:

~~~bash
git init --initial-branch=main "$LAB_ROOT/sample-app"
git -C "$LAB_ROOT/sample-app" config user.name "Git Learner"
git -C "$LAB_ROOT/sample-app" config user.email "learner@example.test"

mkdir -p "$LAB_ROOT/sample-app/src/api"
mkdir -p "$LAB_ROOT/sample-app/src/web"
mkdir -p "$LAB_ROOT/sample-app/docs"
mkdir -p "$LAB_ROOT/sample-app/tools"

printf '# Sample App\n' > "$LAB_ROOT/sample-app/README.md"
printf 'route=/api/v1\n' > "$LAB_ROOT/sample-app/src/api/routes.conf"
printf 'page=home\n' > "$LAB_ROOT/sample-app/src/web/page.conf"
printf '# Architecture\n' > "$LAB_ROOT/sample-app/docs/architecture.md"
printf '#!/bin/sh\necho build\n' > "$LAB_ROOT/sample-app/tools/build.sh"

git -C "$LAB_ROOT/sample-app" add README.md src docs tools
git -C "$LAB_ROOT/sample-app" commit -m "Create sample application"
~~~

Kiểm tra repository sạch:

~~~bash
git -C "$LAB_ROOT/sample-app" status --short
git -C "$LAB_ROOT/sample-app" log --oneline --decorate -1
~~~

Đây là commit nền cho nhánh main. Tạo commit trước khi thêm submodule giúp bài lab có một lịch sử cha rõ ràng.

## 5. Thêm thư viện dưới dạng submodule

Trong dự án thật, URL submodule nên là địa chỉ HTTPS hoặc SSH ổn định mà các thành viên có quyền truy cập. Bài lab dùng đường dẫn local tuyệt đối đến bare repository vừa tạo:

~~~bash
# Chỉ dành cho lab local: cho phép giao thức file trong cấu hình repository này
git -C "$LAB_ROOT/sample-app" config protocol.file.allow always

git -C "$LAB_ROOT/sample-app" submodule add "$LAB_ROOT/math-core.git" libs/math-core
~~~

Lệnh submodule add clone repository thư viện vào libs/math-core và cập nhật hai phần trong kho cha:

- File .gitmodules lưu tên, đường dẫn và URL của submodule.
- Gitlink mode 160000 lưu OID commit mà kho cha yêu cầu submodule checkout.

Kiểm tra:

~~~bash
git -C "$LAB_ROOT/sample-app" status
git -C "$LAB_ROOT/sample-app" diff --cached --submodule=log
git -C "$LAB_ROOT/sample-app" ls-files --stage -- libs/math-core
cat "$LAB_ROOT/sample-app/.gitmodules"
~~~

Stage của gitlink phải là 0 và mode thường là 160000. Commit việc thêm submodule:

~~~bash
git -C "$LAB_ROOT/sample-app" commit -m "Add math-core submodule"
git -C "$LAB_ROOT/sample-app" ls-tree HEAD -- libs/math-core
git -C "$LAB_ROOT/sample-app" submodule status --recursive
~~~

Đường dẫn absolute trong .gitmodules chỉ dùng được trên máy tạo lab này. Không dùng URL absolute kiểu này cho repository nhóm. Khi làm việc thật, thay bằng URL remote ổn định và bảo đảm commit được gitlink tham chiếu đã có trên remote của submodule.

## 6. Tạo linked worktree cho nhánh tính năng

Repository sample-app đang có main được checkout ở thư mục sample-app. Tạo worktree thứ hai ở thư mục anh em, đồng thời tạo nhánh feature/api-v2 từ main:

~~~bash
git -C "$LAB_ROOT/sample-app" worktree add -b feature/api-v2 "$LAB_ROOT/sample-app-api" main
~~~

Kiểm tra danh sách worktree:

~~~bash
git -C "$LAB_ROOT/sample-app" worktree list
git -C "$LAB_ROOT/sample-app" worktree list --porcelain
~~~

Bạn sẽ thấy hai working tree:

| Working tree | Nhánh |
|---|---|
| sample-app | main |
| sample-app-api | feature/api-v2 |

Hai thư mục có thể được mở trong hai terminal hoặc IDE riêng. Commit ở worktree feature/api-v2 sẽ cập nhật branch dùng chung trong repository; working tree main vẫn giữ trạng thái riêng của nó.

### Kiểm tra Git directory của linked worktree

Trong repository thông thường, .git thường là thư mục. Trong linked worktree, .git tại thư mục làm việc thường là một file trỏ đến Git directory riêng của worktree:

~~~bash
git -C "$LAB_ROOT/sample-app-api" rev-parse --show-toplevel
git -C "$LAB_ROOT/sample-app-api" rev-parse --absolute-git-dir
git -C "$LAB_ROOT/sample-app-api" rev-parse --git-common-dir
~~~

Git directory riêng lưu dữ liệu như HEAD và index của worktree; common Git directory chứa dữ liệu dùng chung như object database và refs. Dùng các lệnh rev-parse để xác định đường dẫn thực tế, không giả định mọi worktree đều có thư mục .git riêng ở root.

### Một branch không thể được checkout đồng thời ở hai worktree

Git thường ngăn cùng một branch được checkout trong hai linked worktree cùng lúc. Ví dụ, main đang được checkout trong sample-app, nên không thể tạo một worktree khác cũng checkout main theo cách thông thường. Hãy tạo branch khác bằng -b hoặc dùng detached HEAD khi cần xem một commit mà không gắn vào branch:

~~~bash
git -C "$LAB_ROOT/sample-app" worktree add --detach "$LAB_ROOT/sample-app-review" main
~~~

Worktree detached phù hợp cho review hoặc thử nghiệm tạm thời. Nếu tạo commit và muốn giữ nó, hãy tạo branch trước khi xóa worktree.

Đây là ví dụ tùy chọn; nếu thực hiện, xóa worktree review sau khi xem xong:

~~~
git -C "$LAB_ROOT/sample-app" worktree remove "$LAB_ROOT/sample-app-review"
~~~

## 7. Bật sparse checkout trong worktree tính năng

Chuyển sang linked worktree sample-app-api và bật cone mode:

~~~bash
git -C "$LAB_ROOT/sample-app-api" sparse-checkout init --cone
~~~

Chỉ checkout các khu vực cần cho công việc API, tài liệu và thư viện:

~~~bash
git -C "$LAB_ROOT/sample-app-api" sparse-checkout set src/api docs libs/math-core
~~~

Liệt kê các thư mục đang được chọn:

~~~bash
git -C "$LAB_ROOT/sample-app-api" sparse-checkout list
~~~

Trong cone mode, Git giữ các file ở repository root, các file trong thư mục cha của đường dẫn được chọn và toàn bộ nội dung bên trong thư mục đã chọn. Với tập đường dẫn trên, src/api, docs và libs/math-core xuất hiện; src/web không được checkout. Quy tắc này giúp chọn thư mục dễ hiểu và có hiệu năng tốt hơn các mẫu path tùy ý trong chế độ non-cone.

Kiểm tra cây tệp:

~~~bash
find "$LAB_ROOT/sample-app-api" -maxdepth 3 -type f
git -C "$LAB_ROOT/sample-app-api" status --short
~~~

Trên Windows PowerShell, có thể liệt kê tệp bằng Get-ChildItem thay cho find.

### Thêm hoặc thay đổi phạm vi sparse checkout

Để thêm một thư mục mà vẫn giữ các thư mục đã chọn:

~~~bash
git -C "$LAB_ROOT/sample-app-api" sparse-checkout add tools
~~~

Để thay toàn bộ danh sách thư mục, dùng sparse-checkout set với danh sách mới. Để áp dụng lại mẫu sau một thao tác checkout hoặc cập nhật đặc biệt:

~~~bash
git -C "$LAB_ROOT/sample-app-api" sparse-checkout reapply
~~~

Để trở lại working tree đầy đủ:

~~~bash
git -C "$LAB_ROOT/sample-app-api" sparse-checkout disable
~~~

Disable tắt sparse checkout và khôi phục các tệp tracked còn thiếu vào working tree. Nó không xóa lịch sử hoặc object của repository.

### Sparse checkout không đồng nghĩa với partial clone

Sparse checkout giới hạn đường dẫn được checkout vào working tree. Với một clone thông thường, object database vẫn có thể chứa toàn bộ object đã được clone, kể cả object của các thư mục hiện không hiển thị.

Nếu mục tiêu là giảm cả lượng object tải từ remote, có thể kết hợp sparse checkout với partial clone, ví dụ clone với filter blob:none rồi chọn thư mục cần thiết. Đây là cấu hình nâng cao phụ thuộc server hỗ trợ filtering; sparse checkout riêng lẻ không bảo đảm giảm dung lượng object database tương ứng với số tệp đang hiển thị.

## 8. Khởi tạo submodule trong linked worktree

Submodule được kho cha ghim tại một commit cụ thể. Trong một working tree mới, submodule có thể cần được khởi tạo và checkout về commit gitlink. Vì bài lab chọn libs/math-core trong sparse checkout, đường dẫn submodule nằm trong phạm vi được checkout.

Chạy:

~~~bash
git -C "$LAB_ROOT/sample-app-api" submodule update --init --recursive
~~~

Kiểm tra:

~~~bash
git -C "$LAB_ROOT/sample-app-api" submodule status --recursive
git -C "$LAB_ROOT/sample-app-api" status --short
git -C "$LAB_ROOT/sample-app-api" ls-tree HEAD -- libs/math-core
~~~

Submodule thường ở detached HEAD tại OID mà gitlink chỉ định. Đây là hành vi mong đợi vì kho cha pin một commit cụ thể, không yêu cầu submodule tự theo đầu nhánh mới nhất.

Nếu submodule không được chọn trong sparse checkout, thư mục của nó có thể không được hiện diện hoặc chưa được khởi tạo trong working tree. Hãy đưa đường dẫn submodule vào tập sparse checkout trước, sau đó chạy submodule update. Với repository thật, bảo đảm URL và quyền truy cập submodule hợp lệ.

Khi clone repository cha mới, có thể lấy submodule đệ quy ngay từ đầu:

~~~bash
git clone --recurse-submodules <superproject-url> sample-app
~~~

Nếu đã clone mà chưa khởi tạo submodule:

~~~bash
git submodule update --init --recursive
~~~

## 9. Thực hiện thay đổi trong worktree tính năng

Trong worktree sample-app-api, sửa một tệp thuộc phạm vi sparse checkout:

~~~bash
printf 'route=/api/v2\n' > "$LAB_ROOT/sample-app-api/src/api/routes.conf"
printf 'endpoint=/users\n' > "$LAB_ROOT/sample-app-api/src/api/users.conf"

git -C "$LAB_ROOT/sample-app-api" status --short
git -C "$LAB_ROOT/sample-app-api" diff
~~~

Stage và commit:

~~~bash
git -C "$LAB_ROOT/sample-app-api" add src/api/routes.conf src/api/users.conf
git -C "$LAB_ROOT/sample-app-api" diff --cached
git -C "$LAB_ROOT/sample-app-api" commit -m "Add API v2 routes"
~~~

Xác nhận branch feature/api-v2 đã tiến lên:

~~~bash
git -C "$LAB_ROOT/sample-app-api" log --oneline --decorate -3
git -C "$LAB_ROOT/sample-app" branch --list
git -C "$LAB_ROOT/sample-app" worktree list
~~~

Quay lại worktree main và kiểm tra:

~~~bash
cat "$LAB_ROOT/sample-app/src/api/routes.conf"
git -C "$LAB_ROOT/sample-app" status --short
~~~

Worktree main vẫn hiển thị nội dung của commit trên main, chưa tự động lấy thay đổi của feature/api-v2. Hai worktree dùng chung repository và refs nhưng mỗi thư mục có trạng thái checkout riêng.

## 10. Cập nhật code bên trong submodule

Submodule đang được checkout ở detached HEAD theo gitlink. Với bài lab, hãy thay đổi thư viện trong working repository riêng math-core-work, push commit lên bare remote, rồi cập nhật submodule trong worktree tính năng. Cách này giữ rõ hai bước: phát triển repository con và cập nhật con trỏ ở kho cha.

Tạo branch và commit mới trong repository thư viện:

~~~bash
git -C "$LAB_ROOT/math-core-work" switch -c feature/math-multiply
printf 'def multiply(a, b):\n    return a * b\n' >> "$LAB_ROOT/math-core-work/math_core.py"

git -C "$LAB_ROOT/math-core-work" add math_core.py
git -C "$LAB_ROOT/math-core-work" commit -m "Add multiply helper"
git -C "$LAB_ROOT/math-core-work" push -u origin feature/math-multiply
~~~

Trong submodule của worktree tính năng, fetch branch vừa push rồi checkout commit mới. Checkout OID qua FETCH_HEAD để submodule tiếp tục ở detached HEAD:

~~~bash
git -C "$LAB_ROOT/sample-app-api/libs/math-core" fetch origin feature/math-multiply
git -C "$LAB_ROOT/sample-app-api/libs/math-core" checkout FETCH_HEAD
git -C "$LAB_ROOT/sample-app-api/libs/math-core" log --oneline -1
~~~

Commit trong submodule chỉ thay đổi lịch sử repository con. Kho cha vẫn đang ghi nhận OID gitlink cũ. Để cập nhật con trỏ trong kho cha:

~~~bash
git -C "$LAB_ROOT/sample-app-api" status --short
git -C "$LAB_ROOT/sample-app-api" diff --submodule=log
git -C "$LAB_ROOT/sample-app-api" add libs/math-core
git -C "$LAB_ROOT/sample-app-api" diff --cached --submodule=log
git -C "$LAB_ROOT/sample-app-api" commit -m "Advance math-core submodule"
~~~

Thứ tự chia sẻ trong workflow thật là push commit repository con trước, sau đó mới push commit kho cha chứa gitlink mới. Nếu kho cha trỏ đến một commit submodule chưa có trên remote, thành viên khác có thể không tải được đúng phiên bản.

Trong bài lab, remote của thư viện là bare repository local. Branch feature/math-multiply đã được push tới đó để OID mới có thể được fetch. URL local tuyệt đối trong .gitmodules vẫn chỉ phù hợp cho máy lab; không chia sẻ cấu hình này cho nhóm.

## 11. Kiểm tra trạng thái của cả ba thành phần

Trước khi kết thúc, kiểm tra riêng từng lớp:

~~~bash
# Repository cha trong worktree tính năng
git -C "$LAB_ROOT/sample-app-api" status
git -C "$LAB_ROOT/sample-app-api" branch --show-current
git -C "$LAB_ROOT/sample-app-api" sparse-checkout list

# Danh sách linked worktree của repository cha
git -C "$LAB_ROOT/sample-app" worktree list --porcelain

# Submodule và commit được ghim
git -C "$LAB_ROOT/sample-app-api" submodule status --recursive
git -C "$LAB_ROOT/sample-app-api" ls-tree HEAD -- libs/math-core

# Repository cha ở worktree main
git -C "$LAB_ROOT/sample-app" status
git -C "$LAB_ROOT/sample-app" branch --show-current
~~~

Kết quả cần xác nhận:

- sample-app đang ở main; sample-app-api đang ở feature/api-v2.
- Mỗi worktree có working tree và index riêng.
- Sparse checkout trong sample-app-api chỉ hiển thị các thư mục đã chọn; nếu thực hiện bước mở rộng ở phần 7, tools cũng được hiển thị.
- Submodule đã được khởi tạo và checkout đúng OID gitlink của commit kho cha.
- Thay đổi API đã commit trong feature/api-v2; main chưa có commit đó.
- Không còn thay đổi ngoài ý muốn trong working tree.

## 12. Dọn worktree sau thực hành

Trước khi xóa linked worktree, bảo đảm thay đổi cần giữ đã được commit hoặc đã được sao lưu. Sau đó remove worktree:

~~~bash
git -C "$LAB_ROOT/sample-app" worktree remove "$LAB_ROOT/sample-app-api"
git -C "$LAB_ROOT/sample-app" worktree list
~~~

Lệnh remove xóa working tree được chỉ định và metadata liên kết của nó. Nó không tự xóa branch feature/api-v2. Branch vẫn tồn tại trong repository chung và có thể được merge hoặc giữ lại:

~~~bash
git -C "$LAB_ROOT/sample-app" branch --list feature/api-v2
~~~

Nếu muốn xóa branch, chỉ làm sau khi xác nhận branch đã được merge hoặc không còn commit cần giữ:

~~~bash
git -C "$LAB_ROOT/sample-app" branch -d feature/api-v2
~~~

Không dùng -D để ép xóa khi chưa xác minh. Nếu bạn xóa thư mục worktree thủ công bằng hệ điều hành, Git có thể vẫn giữ metadata cũ; sau khi xác nhận đường dẫn đó thật sự không còn, chạy:

~~~bash
git -C "$LAB_ROOT/sample-app" worktree prune
~~~

Prune dọn metadata của worktree đã mất, không phải lệnh xóa branch đang sử dụng. Không chạy prune để thay cho worktree remove khi working tree còn dữ liệu cần giữ.

## 13. Các lỗi thường gặp và cách xử lý

| Tình huống | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Không thể checkout branch ở worktree mới | Branch đã được checkout ở worktree khác | Tạo branch mới bằng -b hoặc dùng --detach |
| Worktree báo dirty khi remove | Còn thay đổi chưa commit hoặc chưa được lưu | Kiểm tra status, commit hoặc sao lưu rồi remove lại |
| Tệp không xuất hiện trong sparse worktree | Đường dẫn không nằm trong tập sparse checkout | Dùng sparse-checkout add hoặc set để thêm thư mục |
| Submodule chưa có nội dung | Chưa init/update hoặc đường dẫn chưa nằm trong sparse selection | Chọn đường dẫn submodule rồi chạy submodule update --init --recursive |
| Submodule ở detached HEAD | Kho cha checkout gitlink cụ thể | Bình thường khi chỉ sử dụng; tạo branch con nếu cần sửa và commit |
| Commit con mới nhưng kho cha không đổi | Chưa stage gitlink trong repository cha | Chạy git add <submodule-path> rồi commit kho cha |
| Thành viên khác không fetch được commit submodule | Gitlink trỏ đến commit chưa được push hoặc URL không truy cập được | Push repository con trước, kiểm tra URL và quyền |
| Sparse checkout không giảm dung lượng clone như mong đợi | Sparse checkout chỉ giới hạn working tree, không nhất thiết giới hạn object được tải | Cân nhắc partial clone nếu remote hỗ trợ |

## 14. Những nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu chính xác |
|---|---|
| Mỗi worktree là một clone độc lập | Linked worktree chia sẻ object database và refs của repository chung, nhưng có HEAD, index và working tree riêng. |
| Có thể checkout cùng một branch ở nhiều worktree | Git thường khóa branch đã được checkout ở worktree khác để tránh hai nơi cùng di chuyển một branch. |
| Xóa worktree cũng xóa branch | Worktree remove chỉ xóa working tree và metadata liên quan; branch vẫn còn. |
| Sparse checkout xóa các file khỏi repository | Nó điều chỉnh tập file hiện diện trong working tree, không xóa commit hay object khỏi lịch sử. |
| Sparse checkout tự giảm lượng object tải | Không nhất thiết; muốn giảm dữ liệu object tải cần kết hợp partial clone khi phù hợp. |
| Cone mode nhận mọi pattern file tùy ý | Cone mode được thiết kế quanh thư mục; dùng non-cone khi cần pattern tùy ý và hiểu chi phí của nó. |
| Submodule là thư mục được commit toàn bộ vào kho cha | Kho cha lưu .gitmodules và gitlink mode 160000 trỏ đến commit repository con. |
| Commit trong submodule tự cập nhật kho cha | Cần stage đường dẫn submodule và commit gitlink trong kho cha. |
| Submodule detached HEAD là lỗi | Đây là trạng thái thường gặp khi checkout commit được kho cha ghim. |

## 15. Tự kiểm tra

1. **Lệnh nào tạo linked worktree và branch mới từ main?**
   - git worktree add -b <branch> <path> main.
2. **Lệnh nào liệt kê tất cả worktree?**
   - git worktree list.
3. **Lệnh nào bật sparse checkout dạng cone?**
   - git sparse-checkout init --cone.
4. **Lệnh nào chọn các thư mục cần checkout?**
   - git sparse-checkout set <directory...>.
5. **Sparse checkout có tự loại object ngoài vùng được chọn khỏi object database không?**
   - Không. Nó chủ yếu giới hạn working tree; partial clone mới là cơ chế giảm object tải khi server hỗ trợ.
6. **Kho cha ghi nhận phiên bản submodule bằng gì?**
   - Gitlink mode 160000 chứa OID commit của repository con.
7. **Sau khi commit trong submodule, cần làm gì để kho cha ghi nhận commit mới?**
   - Stage đường dẫn submodule và commit thay đổi gitlink trong kho cha.
8. **Lệnh nào xóa linked worktree đúng cách?**
   - git worktree remove <path>, sau khi đã giữ lại mọi thay đổi cần thiết.

## Kết luận

Worktree tạo nhiều working tree dùng chung repository để làm việc song song trên các branch khác nhau. Sparse checkout giới hạn những thư mục xuất hiện trong một working tree, còn submodule giữ repository con ở commit được kho cha ghim. Trong workflow kết hợp, hãy tạo worktree riêng, bật sparse checkout, chọn cả đường dẫn submodule cần dùng, khởi tạo submodule rồi kiểm tra branch, tập đường dẫn và gitlink. Trước khi dọn dẹp, xác nhận mọi thay đổi đã được commit hoặc lưu lại; worktree remove không đồng nghĩa xóa branch và sparse checkout không đồng nghĩa xóa object khỏi repository.
