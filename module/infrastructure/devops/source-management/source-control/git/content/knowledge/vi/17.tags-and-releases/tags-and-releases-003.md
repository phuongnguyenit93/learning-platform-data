# Liệt kê, lọc và xem thông tin tag

Tag là một tham chiếu có tên dùng để đánh dấu một vị trí cụ thể trong lịch sử Git, thường là commit tương ứng với một phiên bản phần mềm như `v1.0.0` hoặc `v2.3.1`. Khi cần chuẩn bị phát hành, kiểm tra phiên bản đã tạo hoặc tìm commit được đánh dấu, bạn cần biết cách liệt kê và đọc thông tin tag.

Git cung cấp `git tag --list` để xem tag trong repository local, các bộ lọc để tìm nhóm tag theo tên hoặc quan hệ với commit, và `git show` để xem nội dung tại một tag. Cần phân biệt tag local với tag mà remote đang công bố: lệnh liệt kê tag mặc định đọc các ref đã có trong repository local, không tự truy vấn máy chủ.

## 1. Tag được lưu như thế nào?

Tag là ref nằm trong namespace `refs/tags/`. Ví dụ, tag `v1.2.0` tương ứng với ref `refs/tags/v1.2.0`. Không giống branch thường di chuyển khi tạo commit mới, tag thường được dùng như một mốc ổn định để tham chiếu lại một phiên bản.

Git có hai kiểu tag phổ biến:

- **Lightweight tag:** một ref đơn giản trỏ trực tiếp đến object được đánh dấu, thường là commit. Nó không có tag message, tagger hay thời điểm tạo tag riêng.
- **Annotated tag:** một tag object chứa object đích, tên tag, thông tin tagger, thời gian và thông điệp. Kiểu này phù hợp để đánh dấu release chính thức vì lưu metadata về việc phát hành.

Ví dụ tạo hai loại tag:

```bash
# Lightweight tag.
git tag v1.0.0

# Annotated tag có thông điệp.
git tag -a v1.1.0 -m "Release version 1.1.0"
```

Các lệnh trong bài chủ yếu đọc và lọc tag đã tồn tại. Khi cần tạo tag mới, hãy chọn đúng kiểu tag và commit đích theo quy ước phát hành của nhóm.

## 2. Liệt kê tag bằng git tag --list

Để liệt kê tất cả tag local:

```bash
git tag --list
```

Dạng rút gọn thường dùng:

```bash
git tag -l
```

Ví dụ kết quả:

```text
v1.0.0
v1.1.0
v1.2.0
v2.0.0-rc.1
v2.0.0
```

Mỗi dòng là tên một tag có trong repository local. Lệnh này chỉ hiển thị tên; nó không cho biết tag trỏ đến commit nào, tag thuộc loại lightweight hay annotated, hoặc nội dung thông điệp phát hành.

Nếu repository chưa có tag nào, lệnh có thể không in kết quả. Điều đó chỉ cho biết không có tag phù hợp trong repository local hiện tại; không thể từ đó kết luận remote cũng không có tag.

## 3. Lọc tag theo tên bằng pattern

`git tag --list` nhận một hoặc nhiều pattern dạng glob để lọc tên tag. Ví dụ:

```bash
# Chỉ liệt kê tag thuộc dòng 1.x.
git tag --list "v1.*"

# Tìm tag ứng viên phát hành.
git tag --list "*-rc.*"

# Tìm tag có tiền tố beta.
git tag --list "beta-*"
```

Đặt pattern trong dấu nháy để shell không tự mở rộng `*` trước khi truyền đối số cho Git. Pattern được áp dụng trên tên tag, không phải commit message hoặc nội dung source code.

Có thể truyền nhiều pattern:

```bash
git tag --list "v1.*" "v2.*"
```

Git liệt kê tag khớp với một trong các pattern. Cách này hữu ích khi muốn xem một số dòng phiên bản cùng lúc.

## 4. Sắp xếp tag theo phiên bản hoặc thời gian

Mặc định, tên tag có thể được sắp xếp theo thứ tự từ điển. Với số phiên bản, thứ tự từ điển đôi khi không đúng mong muốn: `v1.10.0` có thể xuất hiện trước hoặc sau `v1.2.0` theo cách so sánh chuỗi thay vì giá trị từng phần của phiên bản.

Dùng `--sort=version:refname` để sắp xếp theo cách hiểu phiên bản:

```bash
# Tăng dần theo phiên bản.
git tag --list --sort=version:refname

# Giảm dần, tag phiên bản mới hơn thường nằm đầu danh sách.
git tag --list --sort=-version:refname
```

Có thể dùng bí danh `v:refname` cho `version:refname`:

```bash
git tag --list --sort=-v:refname
```

Nếu muốn sắp xếp theo ngày tạo, dùng:

```bash
git tag --list --sort=-creatordate
```

`creatordate` là trường ngày tạo phù hợp để sắp xếp cả lightweight và annotated tag: với annotated tag, Git dùng ngày của tagger; với lightweight tag, trường này được lấy từ đối tượng được tag tham chiếu, thường là ngày commit. Vì vậy, đây không nhất thiết là thời điểm một lightweight tag được tạo trên máy.

Thứ tự mặc định cũng có thể bị ảnh hưởng bởi cấu hình `tag.sort`. Nếu kết quả cần nhất quán trong script hoặc tài liệu phát hành, hãy ghi rõ `--sort` trong lệnh thay vì dựa vào cấu hình của từng máy.

## 5. Hiển thị thông điệp ngắn với git tag -n

Để liệt kê tag kèm một phần thông điệp:

```bash
git tag -n
```

Mặc định, Git hiển thị dòng đầu của annotation đối với annotated tag; với lightweight tag, Git hiển thị dòng đầu của commit message tại commit được tag tham chiếu. Có thể yêu cầu hiển thị nhiều dòng hơn:

```bash
git tag -n5
```

Ví dụ:

```text
v1.0.0          Initial stable release
v1.1.0          Release version 1.1.0
v2.0.0-rc.1     Release candidate 1 for version 2.0.0
```

`-n` hữu ích để rà nhanh danh sách release. Tuy nhiên, đây chỉ là phần tóm tắt; nếu cần xem đầy đủ tag message, tagger, ngày tạo và commit đích, hãy dùng `git show`.

## 6. Xem chi tiết một tag bằng git show

Lệnh phổ biến nhất để xem tag và nội dung mà tag đánh dấu:

```bash
git show v1.1.0
```

Với annotated tag, output thường gồm thông tin tag object như tagger, ngày tạo, thông điệp, sau đó là nội dung đối tượng được tag (thường là commit cùng diff). Với lightweight tag, ref trỏ trực tiếp đến commit nên `git show` hiển thị thông tin commit và thay đổi tương ứng.

Nếu chỉ muốn xem commit mà tag phân giải đến:

```bash
git rev-parse 'v1.1.0^{commit}'
```

Lệnh trả về object ID của commit. Cú pháp `^{commit}` yêu cầu Git phân giải tag đến một commit; nó cũng hữu ích khi tag trỏ gián tiếp qua annotated tag object.

Để xem một vài dòng lịch sử quanh tag:

```bash
git log --oneline --decorate -5 v1.1.0
```

Lệnh này hiển thị lịch sử bắt đầu từ commit được tag tham chiếu. Nó giúp xác định tag đang đánh dấu commit nào trong mạch phát triển.

## 7. Phân biệt lightweight và annotated tag khi kiểm tra

Có thể kiểm tra loại object mà tên tag trỏ đến:

```bash
git cat-file -t v1.0.0
git cat-file -t v1.1.0
```

Ví dụ:

```text
commit
tag
```

Nếu kết quả là `commit`, tag đó thường là lightweight tag trỏ trực tiếp đến commit. Nếu kết quả là `tag`, ref trỏ đến một annotated tag object.

Để đọc nội dung thô của annotated tag object:

```bash
git cat-file -p v1.1.0
```

Ví dụ nội dung:

```text
object 4a5b6c7d8e9f00112233445566778899aabbccdd
type commit
tag v1.1.0
tagger Dev Example <dev@example.com> 1735689600 +0700

Release version 1.1.0
```

Các dòng cho biết object đích, loại object, tên tag, tagger và thông điệp. Đây là cách hữu ích khi cần kiểm tra metadata release hoặc phân tích vì sao `git show` hiển thị một tag theo cách nhất định.

## 8. Lọc tag theo quan hệ với commit

Ngoài pattern tên, Git còn cho phép lọc tag theo quan hệ giữa commit được tag và một commit khác.

### Tag có chứa một commit: --contains

```bash
git tag --contains <commit>
```

Lệnh liệt kê các tag mà lịch sử commit được tag có chứa commit chỉ định. Nếu bỏ `<commit>`, Git dùng HEAD hiện tại. Ví dụ:

```bash
git tag --contains HEAD
```

Điều này hữu ích khi muốn biết commit hiện tại đã nằm trong lịch sử của tag nào.

### Tag đã được hợp nhất vào một commit: --merged

```bash
git tag --merged main
```

Lệnh liệt kê các tag có commit được tag đã nằm trong lịch sử có thể đi tới từ `main`. Nó có thể giúp tìm những mốc release đã được tích hợp vào branch đó.

Ngược lại:

```bash
git tag --no-merged main
```

Lệnh liệt kê tag có commit chưa nằm trong lịch sử của `main`. Kết quả có thể giúp rà soát release hoặc tag thử nghiệm chưa được tích hợp vào nhánh đang kiểm tra.

### Tag trỏ đến một object: --points-at

```bash
git tag --points-at HEAD
```

Lệnh liệt kê các tag trỏ đến object được chỉ định, ví dụ commit hiện tại. Nếu muốn kiểm tra một commit cụ thể:

```bash
git tag --points-at 4a5b6c7
```

Các bộ lọc này dựa trên quan hệ object và lịch sử commit, không chỉ dựa trên tên tag. Chúng đặc biệt hữu ích khi repository có nhiều release, hotfix và tag thử nghiệm.

## 9. Tùy chỉnh output với git tag --format

Khi cần danh sách có cấu trúc hơn, `--format` cho phép chọn các trường hiển thị:

```bash
git tag --list --sort=-version:refname --format="%(refname:short) %(objectname:short) %(creatordate:short) %(subject)"
```

Ví dụ output:

```text
v2.0.0  7a8b9c0  2026-04-10  Release version 2.0.0
v1.1.0  4d5e6f7  2026-02-18  Release version 1.1.0
v1.0.0  1a2b3c4  2025-12-01  Initial stable release
```

Một số placeholder hữu ích:

| Placeholder | Ý nghĩa |
|---|---|
| `%(refname:short)` | Tên tag rút gọn, không có tiền tố `refs/tags/` |
| `%(objectname:short)` | Object ID rút gọn mà ref tag trỏ đến |
| `%(creatordate:short)` | Ngày tạo phù hợp với loại object được tham chiếu |
| `%(subject)` | Dòng tiêu đề của nội dung tag hoặc commit tương ứng |
| `%(taggername)` | Tên tagger đối với annotated tag; có thể rỗng với lightweight tag |

Nếu cần dữ liệu đầy đủ để script xử lý, hãy cân nhắc `git for-each-ref` với namespace `refs/tags/`. Lệnh này hỗ trợ nhiều placeholder và bộ lọc ref, phù hợp để xây báo cáo release tự động.

## 10. Tag local và tag trên remote

`git tag --list` chỉ liệt kê tag đang có trong repository local. Nó không gửi truy vấn đến remote để kiểm tra danh sách tag mới nhất trên server.

Để liệt kê tag mà remote đang quảng bá:

```bash
git ls-remote --tags origin
```

Để lấy tag từ remote về local:

```bash
git fetch --tags origin
```

Sau khi fetch, xem lại danh sách local:

```bash
git tag --list --sort=-version:refname
```

Git có cơ chế tự động lấy một số tag trỏ đến lịch sử đang được fetch. `git fetch --tags` yêu cầu lấy tất cả tag được remote công bố. Vì vậy, nếu cần đồng bộ danh sách tag đầy đủ từ remote, hãy dùng tùy chọn này và kiểm tra kết quả sau khi fetch.

Không nên suy luận rằng tag local đã được push lên server. Để xem tag trên remote, dùng `git ls-remote`; để chia sẻ tag mới, dùng lệnh push tag theo quy trình phát hành, ví dụ `git push origin v2.0.0` hoặc `git push --tags` nếu thực sự muốn gửi toàn bộ tag local phù hợp.

## 11. Quy trình rà soát tag trước một lần phát hành

Giả sử nhóm cần xác định những tag phiên bản đã có, xem thông điệp release và kiểm tra tag `v2.0.0` đang trỏ đến commit nào.

```bash
# 1. Liệt kê tag theo thứ tự phiên bản giảm dần.
git tag --list --sort=-version:refname

# 2. Tìm các tag thuộc dòng 2.x.
git tag --list "v2.*" --sort=-version:refname

# 3. Xem thông điệp ngắn của các tag.
git tag --list -n5 "v2.*"

# 4. Xem chi tiết một tag release.
git show v2.0.0

# 5. Lấy commit ID mà tag phân giải đến.
git rev-parse 'v2.0.0^{commit}'

# 6. Kiểm tra tag local đã có trên remote hay chưa.
git ls-remote --tags origin "refs/tags/v2.0.0"
```

Nếu tag chưa có trong local nhưng đã được công bố trên remote, fetch tag về trước khi xem chi tiết. Nếu tag đã có local nhưng remote chưa công bố, phối hợp với người phụ trách release trước khi push để tránh phát hành nhầm mốc.

## 12. Những hiểu nhầm thường gặp

| Hiểu nhầm | Cách hiểu đúng |
|---|---|
| `git tag --list` liệt kê tag trên server | Lệnh này đọc tag local; dùng `git ls-remote --tags <remote>` để xem tag remote đang quảng bá |
| Lightweight và annotated tag giống nhau | Annotated tag có tag object và metadata riêng; lightweight tag là ref trực tiếp đến object được đánh dấu |
| `git tag -n` hiển thị toàn bộ release note | Lệnh chỉ hiển thị số dòng annotation/commit message được yêu cầu, mặc định một dòng |
| Tên tag tự động sắp xếp đúng phiên bản | Dùng `--sort=version:refname` để sắp xếp theo phiên bản |
| `git show <tag>` chỉ in tên tag | Lệnh hiển thị đối tượng tag và nội dung đối tượng được tag, tùy loại tag |
| Tạo tag local đồng nghĩa đã chia sẻ release | Tag chỉ nằm local cho đến khi được push hoặc chia sẻ qua cơ chế khác |

## 13. Ghi nhớ

Để liệt kê tag local, dùng `git tag --list`; để lọc theo tên, truyền glob pattern; để sắp xếp phiên bản, dùng `--sort=-version:refname`; để xem thông điệp ngắn, dùng `-n`; và để đọc chi tiết một mốc, dùng `git show <tag>`.

Khi cần kiểm tra metadata của tag, kết hợp `git cat-file -t` và `git cat-file -p`. Khi cần lọc theo lịch sử, dùng `--contains`, `--merged`, `--no-merged` hoặc `--points-at`. Cuối cùng, hãy phân biệt tag local với tag remote: dùng `git ls-remote --tags` để kiểm tra server và `git fetch --tags` để lấy tag về repository local.
