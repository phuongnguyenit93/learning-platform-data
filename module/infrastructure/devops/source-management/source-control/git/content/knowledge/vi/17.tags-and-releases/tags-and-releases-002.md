# Tạo lightweight tag và annotated tag

Tag là một nhãn có tên gắn với một đối tượng Git, thường là commit. Tag giúp đánh dấu những mốc quan trọng như phiên bản phát hành, bản dựng đã kiểm thử hoặc điểm cần tham chiếu trong lịch sử. Khác với branch, tag thông thường không di chuyển theo commit mới: nó giữ nguyên mốc đã được đánh dấu cho đến khi người dùng chủ động thay đổi hoặc xóa.

Git có hai loại tag phổ biến: **lightweight tag** và **annotated tag**. Cả hai đều giúp gọi tên một mốc trong lịch sử, nhưng cách Git lưu trữ và lượng thông tin đi kèm khác nhau. Hiểu sự khác biệt này giúp chọn đúng loại tag khi đánh dấu phiên bản và chia sẻ mốc phát hành với nhóm.

## 1. Tag là gì?

Một tag là một tham chiếu có tên trong không gian `refs/tags/`. Ví dụ, tag `v1.2.0` thường trỏ tới commit chứa mã nguồn của phiên bản 1.2.0.

Hình dung repository có lịch sử:

~~~text
A---B---C---D---E  main
        ^
        |
      v1.0.0
~~~

Tag `v1.0.0` đánh dấu commit `C`. Khi nhánh `main` tiếp tục có commit `D` và `E`, tag vẫn trỏ về `C`. Đây là điểm khác biệt quan trọng so với branch: branch là tham chiếu di chuyển theo commit mới khi ta tạo commit trên nhánh đó, còn tag thường được dùng như một mốc cố định.

Tag không phải là một bản sao của repository và cũng không tạo commit mới trong lịch sử phát triển. Việc tạo tag chỉ thêm một tham chiếu hoặc một đối tượng tag tùy loại tag được chọn.

## 2. Phân biệt lightweight tag và annotated tag

Git cung cấp hai cách tạo tag:

| Đặc điểm | Lightweight tag | Annotated tag |
|---|---|---|
| Cách lưu | Ref trỏ trực tiếp tới đối tượng được đánh dấu, thường là commit | Tạo một tag object riêng, object này trỏ tới đối tượng đích |
| Thông tin người tạo | Không lưu metadata tag riêng | Có tagger, thời gian tạo và thông điệp |
| Thông điệp mô tả | Không có | Có |
| Chữ ký mật mã | Không có trong tag | Có thể ký bằng GPG/SSH tùy cấu hình |
| Mục đích thường gặp | Đánh dấu tạm hoặc mốc cá nhân | Đánh dấu phiên bản, release hoặc mốc cần chia sẻ chính thức |

### Lightweight tag

Lightweight tag giống một nhãn tham chiếu đơn giản. Git tạo một ref dưới `refs/tags/` trỏ trực tiếp tới object được chỉ định. Nếu tag được tạo ở một commit, ref trỏ thẳng tới commit đó.

Ví dụ:

~~~bash
git tag v1.2.0
~~~

Lệnh tạo tag `v1.2.0` tại commit hiện tại (HEAD). Git không tạo tag object, không ghi tagger hay thông điệp đi kèm.

### Annotated tag

Annotated tag tạo một đối tượng tag riêng. Đối tượng này chứa loại đối tượng được trỏ tới, tên tag, thông tin tagger, thời gian và thông điệp. Có thể ký số tag để người nhận xác minh nguồn gốc.

Ví dụ:

~~~bash
git tag -a v1.2.0 -m "Release version 1.2.0"
~~~

Tùy chọn `-a` yêu cầu Git tạo annotated tag; `-m` cung cấp thông điệp. Nếu bỏ `-m`, Git mở trình soạn thảo để nhập nội dung.

Với phiên bản phát hành chính thức, annotated tag thường phù hợp hơn vì nó lưu được thông tin mô tả mốc phát hành và có thể được ký số. Lightweight tag phù hợp cho nhãn cá nhân hoặc mốc đơn giản khi không cần metadata.

## 3. Tạo lightweight tag tại commit hiện tại

Trước khi tạo tag, kiểm tra bạn đang ở đúng repository và commit mong muốn:

~~~bash
git status
git branch --show-current
git log -1 --oneline
~~~

Nếu muốn đánh dấu commit hiện tại bằng lightweight tag:

~~~bash
git tag v1.2.0
~~~

Lệnh không có `-a`, `-s` hoặc `-m` sẽ tạo lightweight tag. Để xem tag vừa tạo:

~~~bash
git tag --list
git show v1.2.0
~~~

`git show` hiển thị đối tượng mà tag trỏ tới. Với lightweight tag trỏ tới commit, kết quả thường hiển thị thông tin commit và diff tương ứng.

Nếu tên tag đã tồn tại, Git từ chối tạo tag trùng tên. Hãy kiểm tra tag hiện có trước khi quyết định dùng tên khác hay cập nhật tag.

## 4. Tạo annotated tag tại commit hiện tại

Để đánh dấu phiên bản có thông điệp:

~~~bash
git tag -a v1.2.0 -m "Release version 1.2.0"
~~~

Có thể thêm thông tin hữu ích vào thông điệp, ví dụ:

~~~bash
git tag -a v1.2.0 -m "Release 1.2.0

- Add payment retry handling
- Improve report export
- Fix session timeout"
~~~

Thông điệp của annotated tag là phần mô tả gắn với mốc phiên bản. Nên ghi nội dung ngắn gọn, có thể tra cứu và phù hợp với release note của dự án.

Nếu muốn nhập thông điệp bằng trình soạn thảo:

~~~bash
git tag -a v1.2.0
~~~

Git sẽ mở editor được cấu hình qua `core.editor` hoặc biến môi trường tương ứng. Lưu và đóng editor để hoàn tất việc tạo tag.

## 5. Tạo tag cho một commit cụ thể

Không nhất thiết phải checkout commit cần đánh dấu. Có thể truyền commit hash hoặc một biểu thức tham chiếu làm đối số:

~~~bash
git log --oneline --decorate -8
git tag -a v1.2.0 4f8c2a1 -m "Release version 1.2.0"
~~~

Trong ví dụ, `4f8c2a1` là commit hash minh họa. Hãy thay bằng hash đúng của repository.

Có thể dùng tên nhánh, tag hoặc biểu thức Git revision:

~~~bash
git tag -a v1.2.0 main -m "Release version 1.2.0"
git tag -a v1.1.1 "v1.1.0^{}" -m "Release version 1.1.1"
~~~

Ví dụ thứ hai dùng biểu thức `^{}` để peel annotated tag về đối tượng đích. Dấu ngoặc kép giúp truyền nguyên biểu thức revision cho Git trong các shell có quy tắc phân tích ký tự riêng. Trong thực hành, cách đơn giản và rõ ràng nhất vẫn là dùng commit hash đã kiểm tra.

Với lightweight tag, cú pháp tương tự:

~~~bash
git tag v1.2.0 4f8c2a1
~~~

Điểm cần nhớ: tag được tạo tại commit được chỉ định, không nhất thiết là commit HEAD. Trước khi đánh dấu release, hãy xác nhận commit đó đã bao gồm đúng thay đổi cần phát hành.

## 6. Tạo tag có chữ ký số

Annotated tag có thể được ký số để người nhận xác minh tag được tạo bởi người sở hữu khóa tương ứng. Git hỗ trợ ký tag bằng GPG hoặc SSH tùy phiên bản Git và cấu hình.

Ký tag bằng GPG:

~~~bash
git tag -s v1.2.0 -m "Signed release version 1.2.0"
~~~

Tùy chọn `-s` tạo signed annotated tag. Nếu có nhiều khóa, có thể chỉ định khóa ký bằng `-u`:

~~~bash
git tag -s -u <key-id> v1.2.0 -m "Signed release version 1.2.0"
~~~

Để xác minh chữ ký:

~~~bash
git tag -v v1.2.0
~~~

Việc xác minh thành công cho biết chữ ký hợp lệ theo khóa mà môi trường của bạn tin cậy. Nhóm vẫn cần phân phối và xác minh fingerprint/public key của người phát hành qua kênh đáng tin cậy. Một chữ ký hợp lệ không tự chứng minh rằng nội dung release an toàn hoặc đã qua quy trình review.

Nếu chưa cấu hình khóa ký, lệnh ký sẽ báo lỗi. Có thể dùng annotated tag không ký khi chính sách dự án không yêu cầu chữ ký.

## 7. Xem, tìm và lọc tag

Liệt kê tất cả tag:

~~~bash
git tag
~~~

Liệt kê tag cùng vài dòng đầu của thông điệp annotated tag:

~~~bash
git tag -n
git tag -n99
~~~

Tìm tag theo mẫu:

~~~bash
git tag --list "v1.*"
git tag --list "v*"
~~~

Sắp xếp theo tên phiên bản:

~~~bash
git tag --sort=-version:refname
~~~

Sắp xếp phiên bản giúp `v1.10.0` đứng trước `v1.9.0` theo thứ tự version, thay vì chỉ so sánh ký tự. Nếu dự án có quy tắc đặt tên riêng, hãy dùng mẫu lọc phù hợp.

Xem nội dung một tag:

~~~bash
git show v1.2.0
~~~

Xem tag đang trỏ tới commit nào:

~~~bash
git rev-parse v1.2.0
git rev-parse "v1.2.0^{commit}"
~~~

Với annotated tag, lệnh đầu trả về object ID của tag object, còn biểu thức `^{commit}` yêu cầu Git phân giải tag về commit được đánh dấu (nếu tag cuối cùng trỏ tới commit).

Có thể xem các tag tham chiếu trong repository:

~~~bash
git show-ref --tags
~~~

## 8. Kiểm tra loại tag và cấu trúc bên trong

Có thể dùng `git cat-file` để phân biệt hai loại tag.

Với lightweight tag trỏ tới commit:

~~~bash
git cat-file -t v1.2.0
~~~

Kết quả thường là:

~~~text
commit
~~~

Với annotated tag:

~~~bash
git cat-file -t v1.2.0
~~~

Kết quả là:

~~~text
tag
~~~

Điều này xảy ra vì lightweight tag trỏ thẳng tới commit object, còn annotated tag trỏ tới một tag object riêng.

Để xem nội dung tag object:

~~~bash
git cat-file -p v1.2.0
~~~

Kết quả minh họa:

~~~text
object 4f8c2a1...
type commit
tag v1.2.0
tagger Nguyen Van A <dev@example.com> 1794900000 +0700

Release version 1.2.0
~~~

Các giá trị hash, tên người tạo, email và timestamp ở trên chỉ là ví dụ. Với tag đã ký, nội dung object còn có phần chữ ký.

Có thể kiểm tra loại đối tượng mà một ref trỏ tới bằng `git cat-file -t`, thay vì suy luận chỉ từ tên tag hoặc cách đặt phiên bản.

## 9. Chia sẻ tag lên remote

Tag được tạo trong repository local không tự động được gửi lên remote chỉ vì bạn chạy `git push origin main`. Cần chỉ định tag hoặc dùng tùy chọn phù hợp.

Đẩy một tag cụ thể:

~~~bash
git push origin v1.2.0
~~~

Đẩy tất cả tag local:

~~~bash
git push origin --tags
~~~

Tùy chọn `--tags` yêu cầu gửi tất cả tag local lên remote. Nếu remote đã có tag cùng tên nhưng trỏ tới object khác, Git thường từ chối cập nhật tag đó thay vì tự ghi đè; cần kiểm tra và xử lý riêng nếu chính sách dự án cho phép thay thế. Chỉ dùng khi bạn thực sự muốn chia sẻ toàn bộ tập tag, vì repository có thể chứa tag thử nghiệm hoặc tag cá nhân.

Đẩy các annotated tag có thể tiếp cận từ những commit đang push:

~~~bash
git push --follow-tags origin main
~~~

`--follow-tags` tự động đẩy các annotated tag chưa có trên remote và trỏ tới đối tượng có thể tiếp cận từ các ref đang được push. Nó không đẩy tất cả lightweight tag local. Đây là lựa chọn hữu ích khi đẩy nhánh phát hành cùng các annotated tag liên quan.

Sau khi push, kiểm tra tag trên remote:

~~~bash
git ls-remote --tags origin
~~~

Với annotated tag, kết quả có thể có hai dòng: ref tag object và dòng có hậu tố `^{}` biểu diễn đối tượng mà tag được peel tới, thường là commit. Lightweight tag thường chỉ có dòng ref trỏ trực tiếp tới commit.

## 10. Lấy tag từ remote

Khi cần lấy tag từ remote:

~~~bash
git fetch origin --tags
~~~

Lệnh này tải các tag từ remote `origin` và các đối tượng cần thiết. Có thể kiểm tra lại:

~~~bash
git tag --list
git show v1.2.0
~~~

Thông thường, `git fetch` cũng lấy các tag trỏ tới những đối tượng được tải về theo quy tắc auto-follow. `--tags` yêu cầu lấy tất cả tag từ remote, kể cả tag không trỏ tới các đối tượng vừa được fetch qua refspec nhánh.

Khi clone repository thông thường, Git thường lấy các tag liên quan tới lịch sử được clone. Trong một số cấu hình fetch tùy chỉnh hoặc shallow clone, tập tag có thể khác; hãy kiểm tra bằng `git tag` và fetch thêm khi cần.

## 11. Checkout tag và tạo nhánh từ tag

Tag là mốc tham chiếu, không phải nhánh làm việc. Khi chuyển trực tiếp tới tag:

~~~bash
git switch --detach v1.2.0
~~~

HEAD ở trạng thái detached (không gắn với một branch). Bạn có thể xem mã nguồn đúng tại phiên bản đó và chạy kiểm thử. Nếu tạo commit mới trong trạng thái này mà không tạo nhánh, commit có thể khó tìm lại khi chuyển đi nơi khác.

Nếu muốn tiếp tục phát triển hoặc sửa lỗi từ phiên bản đó, tạo nhánh mới:

~~~bash
git switch -c hotfix/1.2.x v1.2.0
~~~

Nhánh `hotfix/1.2.x` bắt đầu từ commit mà tag `v1.2.0` đánh dấu. Các commit mới sẽ di chuyển nhánh hotfix, còn tag vẫn giữ nguyên mốc ban đầu.

## 12. Xóa tag local và remote

Xóa tag trong repository local:

~~~bash
git tag -d v1.2.0
~~~

Lệnh này chỉ xóa ref tag local, không xóa tag trên remote.

Xóa tag trên remote:

~~~bash
git push origin --delete v1.2.0
~~~

Hoặc dùng refspec với nguồn rỗng:

~~~bash
git push origin :refs/tags/v1.2.0
~~~

Xóa tag đã phát hành có thể ảnh hưởng đến người dùng, pipeline, tài liệu hoặc hệ thống triển khai đang tham chiếu phiên bản đó. Hãy phối hợp với nhóm trước khi xóa tag công khai.

## 13. Cập nhật hoặc thay thế tag

Git cho phép di chuyển tag local bằng `-f`:

~~~bash
git tag -f v1.2.0 <new-commit>
~~~

Với annotated tag, tạo lại tag cùng tên và thông điệp mới:

~~~bash
git tag -f -a v1.2.0 <new-commit> -m "Corrected release tag"
~~~

Nếu tag đã tồn tại trên remote, push thông thường thường từ chối cập nhật tag đã có. Có thể force push:

~~~bash
git push --force origin refs/tags/v1.2.0
~~~

Đây là thao tác thay thế mốc đã công bố. Người dùng khác có thể đã tải tag cũ và sẽ không tự động biết tag đã bị di chuyển. Với phiên bản phát hành, thông lệ an toàn là không sửa hoặc tái sử dụng tên tag đã công bố; nếu cần sửa lỗi, tạo phiên bản mới như `v1.2.1` và giải thích trong release note.

Nếu buộc phải thay tag theo chính sách dự án, hãy thông báo rõ hash cũ và hash mới, lý do thay đổi, cách người dùng cập nhật tag local và tác động tới pipeline hoặc artifact đã phát hành.

## 14. Quy trình mẫu đánh dấu một phiên bản

Giả sử nhóm chuẩn bị phát hành `v2.0.0` từ nhánh `main`.

**Bước 1 — Kiểm tra trạng thái repository và commit phát hành**

~~~bash
git status
git switch main
git pull --ff-only
git log -1 --oneline
~~~

Đảm bảo working tree sạch và commit hiện tại đã qua các kiểm tra cần thiết.

**Bước 2 — Tạo annotated tag**

~~~bash
git tag -a v2.0.0 -m "Release version 2.0.0"
~~~

Nếu dự án yêu cầu ký tag, dùng `git tag -s` và xác minh bằng `git tag -v`.

**Bước 3 — Kiểm tra tag**

~~~bash
git show v2.0.0
git cat-file -t v2.0.0
~~~

Với annotated tag, loại object sẽ là `tag`. Xác nhận tag trỏ đúng commit và thông điệp mô tả đúng phiên bản.

**Bước 4 — Push tag lên remote**

~~~bash
git push origin v2.0.0
~~~

**Bước 5 — Xác nhận remote đã nhận tag**

~~~bash
git ls-remote --tags origin v2.0.0
~~~

Sau khi tag được chia sẻ, nhóm có thể tạo release trên nền tảng lưu trữ Git, đính kèm release note và artifact build tương ứng. Tag đánh dấu commit nguồn; release page và artifact là các nội dung bổ sung do nền tảng hoặc quy trình phát hành quản lý.

## 15. Lỗi thường gặp khi làm việc với tag

| Tình huống | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| `fatal: tag 'v1.2.0' already exists` | Tên tag đã tồn tại local | Kiểm tra bằng `git show v1.2.0`; chọn tên mới hoặc chỉ cập nhật khi có chủ đích |
| Push tag bị từ chối vì tag đã tồn tại | Remote đang có tag cùng tên, Git không tự ghi đè | Xác minh tag remote; ưu tiên tạo phiên bản mới |
| Tag không xuất hiện sau khi push branch | Push branch không tự động gửi mọi tag | Push tag cụ thể, `--tags` hoặc `--follow-tags` |
| Không thấy tag của đồng đội | Tag chưa được fetch hoặc refspec fetch tùy chỉnh | Chạy `git fetch origin --tags` |
| `git describe` không nhận tag mong muốn | Mặc định lệnh có thể chỉ xét annotated tag | Dùng `git describe --tags` nếu muốn xét cả lightweight tag |
| Checkout tag rồi tạo commit nhưng không thấy trên branch | HEAD đang detached | Tạo branch bằng `git switch -c <branch> <tag>` trước khi phát triển |

Khi gặp lỗi, hãy kiểm tra tên tag, loại tag, commit đích và trạng thái local/remote trước khi xóa hoặc ghi đè.

## 16. Những điểm cần ghi nhớ

- Lightweight tag là ref đơn giản trỏ trực tiếp tới object; annotated tag tạo tag object có tagger, thời gian và thông điệp.
- Dùng `git tag <name>` để tạo lightweight tag tại HEAD.
- Dùng `git tag -a <name> -m "<message>"` để tạo annotated tag.
- Có thể truyền commit hash hoặc revision để gắn tag vào một commit cụ thể.
- Annotated tag phù hợp để đánh dấu release; signed tag cho phép xác minh chữ ký nếu nhóm quản lý khóa tin cậy.
- Dùng `git show`, `git tag --list`, `git cat-file -t` và `git ls-remote --tags` để kiểm tra tag.
- Tag local không tự động được push cùng branch; hãy push rõ tag hoặc chọn `--tags` / `--follow-tags`.
- Checkout tag tạo detached HEAD; tạo branch từ tag nếu cần tiếp tục commit.
- Không nên di chuyển hoặc tái sử dụng tag release đã công bố. Tạo tag phiên bản mới giúp lịch sử phát hành ổn định và dễ kiểm chứng.

Tag là mốc có tên giúp mọi thành viên và hệ thống phát hành cùng tham chiếu tới một phiên bản cụ thể. Khi dùng annotated tag cho release và chia sẻ tag một cách có chủ đích, nhóm có thể lưu lại nguồn gốc, mô tả và tính toàn vẹn của từng mốc phát hành.

