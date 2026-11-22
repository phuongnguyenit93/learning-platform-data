# Đổi hoặc xóa tag cục bộ, tag từ xa và phối hợp với người đã tải

Tag là nhãn tham chiếu tới một đối tượng Git, thường dùng để đánh dấu phiên bản hoặc mốc phát hành. Khi tag bị tạo nhầm, trỏ sai commit hoặc cần loại bỏ, bạn có thể đổi hoặc xóa tag ở máy local và remote. Tuy nhiên, tag đã được đồng đội tải về hoặc đã gắn với bản phát hành cần được xử lý có phối hợp: thay đổi tag trên máy chủ không tự cập nhật các bản tag mà người khác đang giữ.

## 1. Tag trỏ tới điều gì?

Tag là một ref có tên, thường nằm dưới `refs/tags/`. Khác với branch, tag thường được dùng như mốc cố định để tham chiếu một commit, ví dụ `v1.2.0` hoặc `release-2026-11`.

Git có hai loại tag phổ biến:

| Loại tag | Đặc điểm |
|---|---|
| Lightweight tag | Ref trực tiếp trỏ tới đối tượng, thường là commit; không tạo tag object riêng |
| Annotated tag | Tạo một tag object chứa tagger, thời điểm, thông điệp và có thể có chữ ký; tag object trỏ tới commit hoặc đối tượng Git khác |

Annotated tag thường phù hợp với release vì có thông tin mô tả và có thể ký để xác minh nguồn gốc. Lightweight tag hữu ích cho nhãn local hoặc mốc tạm thời.

Kiểm tra các tag local:

```bash
git tag --list
git tag --list "v1.*"
git show-ref --tags
```

Xem một tag cụ thể:

```bash
git show v1.2.0
```

Với annotated tag, `git show` hiển thị metadata của tag cùng nội dung commit được trỏ tới. Với lightweight tag, lệnh hiển thị đối tượng mà ref trỏ trực tiếp tới.

## 2. Xác định tag đang trỏ tới đâu trước khi thay đổi

Trước khi đổi hoặc xóa tag, hãy xác nhận đúng tên và commit đích:

```bash
git show --no-patch --decorate v1.2.0
git rev-parse "v1.2.0^{}"
git cat-file -t v1.2.0
```

- `git show` giúp kiểm tra tag và commit được tham chiếu.
- `git rev-parse "v1.2.0^{}"` phân giải tag về đối tượng đích cuối cùng; với annotated tag, biểu thức này bóc tag object để lấy commit được gắn nhãn.
- `git cat-file -t` cho biết đối tượng mà ref trỏ trực tiếp tới, thường là `tag` với annotated tag hoặc `commit` với lightweight tag.

Có thể kiểm tra tag trên remote mà không cần fetch toàn bộ repository:

```bash
git ls-remote --tags origin
git ls-remote --tags origin v1.2.0
```

Với annotated tag, kết quả thường có hai dòng: một dòng cho tag object và một dòng có hậu tố `^{}` cho đối tượng mà tag được bóc tới. Điều này giúp so sánh tag local và tag trên máy chủ.

Không chỉ dựa vào tên tag. Hai repository có thể cùng có `v1.2.0` nhưng tag trỏ tới hai commit khác nhau.

## 3. Đổi tag cục bộ

Git không sửa trực tiếp một tag object đã tồn tại. Khi muốn đổi tag local sang commit khác, bạn cập nhật ref của tag để nó trỏ tới đối tượng mới. Dùng `-f` (`--force`) để cho phép thay tag cùng tên.

### 3.1. Cập nhật lightweight tag

Ví dụ chuyển `v1.2.0` sang commit mới:

```bash
git tag -f v1.2.0 <new-commit>
```

Lệnh này cập nhật tag local `v1.2.0` để trỏ tới `<new-commit>`. Thay placeholder bằng hash hoặc ref đã xác minh. Nếu bỏ qua đối số đích, Git dùng `HEAD` làm đích.

### 3.2. Tạo lại annotated tag

Để thay một annotated tag và tạo tag object mới:

```bash
git tag -f -a -m "Release v1.2.0" v1.2.0 <new-commit>
```

Tag object mới có metadata và thông điệp mới. Nếu tag cũ được ký, việc tạo lại tag sẽ tạo chữ ký mới; chữ ký cũ không còn xác minh cho tag mới.

Nếu tổ chức yêu cầu tag có chữ ký, dùng quy trình ký đã được cấu hình, ví dụ `-s` thay cho `-a`, và xác nhận khóa ký đúng trước khi công bố.

### 3.3. Kiểm tra sau khi đổi

Sau khi cập nhật, xác nhận tag trỏ đúng commit:

```bash
git show --no-patch --decorate v1.2.0
git rev-parse "v1.2.0^{}"
git cat-file -t v1.2.0
```

Hãy kiểm tra cả tên tag, commit đích, thông điệp và chữ ký (nếu có). Thay tag local không làm thay đổi tag trên remote và cũng không tự cập nhật tag ở máy đồng đội.

## 4. Xóa tag cục bộ

Để xóa một tag local:

```bash
git tag -d v1.2.0
```

Lệnh này xóa ref `refs/tags/v1.2.0` trong repository hiện tại. Nó không xóa commit được tag trỏ tới, không xóa tag trên remote và không ảnh hưởng bản tag ở repository khác.

Kiểm tra tag đã được xóa khỏi danh sách local:

```bash
git tag --list v1.2.0
```

Nếu không có kết quả, tag không còn trong danh sách tag local. Commit vẫn có thể được giữ bởi branch, tag khác, reflog hoặc ref khác.

## 5. Đẩy tag mới lên remote

Tag không tự được push trong mọi thao tác `git push` thông thường. Để gửi một tag cụ thể:

```bash
git push origin refs/tags/v1.2.0:refs/tags/v1.2.0
```

Hoặc dùng dạng ngắn khi muốn push một tag cụ thể:

```bash
git push origin v1.2.0
```

Nên chỉ định tag cụ thể thay vì dùng `git push --tags` nếu bạn chỉ muốn công bố một mốc. `--tags` có thể đẩy tất cả tag local chưa có trên remote, bao gồm cả tag tạm hoặc tag chưa được review.

Kiểm tra tag sau khi push:

```bash
git ls-remote --tags origin v1.2.0
```

So sánh object ID và commit được bóc ra với tag local để xác nhận máy chủ đang giữ đúng tag dự kiến.

## 6. Đổi tag đã có trên remote

Đổi tag đã công bố là thao tác viết lại mốc tham chiếu trên máy chủ. Nó có thể làm các pipeline, gói phát hành, checksum, tài liệu và máy của người dùng trỏ tới những nội dung khác nhau dù cùng mang một tên phiên bản.

Theo quy ước an toàn, tag release đã công bố nên được xem là bất biến. Nếu phát hiện bản phát hành `v1.2.0` sai, lựa chọn thường tốt hơn là tạo bản sửa mới, chẳng hạn `v1.2.1`, với commit và ghi chú phát hành rõ ràng. Việc giữ tag cũ giúp mọi người có thể xác định chính xác nội dung đã được phát hành trước đó.

Chỉ đổi tag remote khi tổ chức cho phép và những người phụ thuộc vào tag đã được thông báo, thống nhất. Trước khi cập nhật, kiểm tra cả local và remote:

```bash
git show --no-patch --decorate v1.2.0
git ls-remote --tags origin v1.2.0
```

Sau khi đã cập nhật tag local và xác nhận đúng đối tượng đích, có thể cập nhật ref trên remote bằng force push với refspec rõ ràng:

```bash
git push --force origin refs/tags/v1.2.0:refs/tags/v1.2.0
```

`--force` cho phép thay tag đã tồn tại trên remote. Lệnh này có thể bị server từ chối bởi quyền hoặc chính sách bảo vệ tag. Không dùng nó như cách sửa mặc định cho tag release đã được công bố.

Sau khi cập nhật, xác minh lại tag từ máy chủ:

```bash
git ls-remote --tags origin v1.2.0
```

Kiểm tra cả dòng tag object và dòng peeled `^{}` nếu tag là annotated. Đối chiếu với kết quả local để chắc chắn tag remote đã trỏ tới đúng commit.

## 7. Xóa tag trên remote

Xóa tag local và xóa tag remote là hai thao tác độc lập. Để xóa tag trên remote `origin`:

```bash
git push origin --delete refs/tags/v1.2.0
```

Một dạng refspec tương đương là:

```bash
git push origin :refs/tags/v1.2.0
```

Hai cách trên yêu cầu máy chủ xóa ref tag. Chúng không xóa tag local của bạn hoặc của người khác. Sau đó kiểm tra:

```bash
git ls-remote --tags origin v1.2.0
```

Nếu không còn kết quả, remote không còn công bố tag đó tại thời điểm truy vấn. Một số máy chủ có chính sách bảo vệ tag hoặc hạn chế xóa; khi đó cần làm theo quy trình của quản trị repository.

## 8. Người đã fetch tag sẽ thấy gì?

Tag không giống remote-tracking branch. Khi một người fetch tag, Git tạo ref tag local trong repository của họ, ví dụ `refs/tags/v1.2.0`. Ref local này không tự di chuyển khi tag trên máy chủ được đổi hoặc xóa.

### 8.1. Remote tag bị xóa

Nếu remote xóa `v1.2.0`, người đã fetch tag trước đó vẫn có thể thấy tag trong máy local:

```bash
git tag --list v1.2.0
```

Đó là vì việc xóa ref trên remote không phát lệnh xóa ref local tới mọi máy đã clone. Người dùng cần xác nhận thông báo từ nhóm trước khi tự xóa tag local:

```bash
git tag -d v1.2.0
```

Sau đó, nếu cần xác nhận tag đã biến mất khỏi remote, truy vấn lại:

```bash
git ls-remote --tags origin v1.2.0
```

`git fetch --prune --prune-tags origin` có thể đồng bộ việc prune tag local theo tập tag mà remote công bố, nhưng cần cẩn trọng: tùy refspec và cấu hình fetch, thao tác này có thể xóa cả tag local không có trên remote. Hãy đọc cấu hình và danh sách tag trước khi dùng, nhất là repository có tag riêng chỉ tồn tại local.

### 8.2. Remote tag được chuyển sang commit khác

Nếu tag `v1.2.0` đã được fetch trước đó rồi remote đổi tag sang commit mới, máy của người dùng vẫn giữ ref local cũ. Fetch thông thường có thể từ chối cập nhật tag đã tồn tại hoặc báo tag would clobber, bởi Git không tự ghi đè tag local đang có.

Sau khi xác nhận với nhóm rằng tag đã được đổi có chủ đích, người dùng có thể xóa tag local cũ rồi fetch lại tag mới:

```bash
git tag -d v1.2.0
git fetch origin tag v1.2.0
```

Hoặc dùng force fetch cho đúng ref tag đã xác nhận:

```bash
git fetch --force origin refs/tags/v1.2.0:refs/tags/v1.2.0
```

Sau đó kiểm tra lại:

```bash
git show --no-patch --decorate v1.2.0
git rev-parse "v1.2.0^{}"
```

Không nên chạy force fetch hoặc xóa tag local chỉ vì thấy tag khác nhau. Hãy chắc chắn thông báo đổi tag là chính thức và commit đích mới đã được kiểm tra.

### 8.3. Người đã tạo branch hoặc checkout từ tag cũ

Nếu ai đó đã tạo branch từ commit cũ hoặc đang ở trạng thái detached HEAD tại tag cũ, đổi tag không di chuyển branch hoặc HEAD của họ. Tag chỉ là một ref tên gọi; branch và commit đã checkout vẫn giữ quan hệ với commit mà chúng từng trỏ tới.

Nếu họ cần chuyển sang nội dung mới, phải chủ động cập nhật branch hoặc checkout commit mới theo hướng dẫn của nhóm. Không nên cho rằng cập nhật tag local tự thay đổi mã nguồn đang làm việc.

## 9. Quy trình phối hợp khi cần thay hoặc xóa release tag

Trước khi thay đổi một tag đã được công bố, người phụ trách release nên thông báo rõ:

1. Tên tag bị ảnh hưởng, ví dụ `v1.2.0`.
2. Object ID và commit đích hiện tại trên remote.
3. Lý do đổi hoặc xóa tag và commit đích mới nếu có.
4. Thời điểm thực hiện và người chịu trách nhiệm.
5. Hướng dẫn cho người đã fetch tag, pipeline hoặc môi trường triển khai đang sử dụng tag đó.
6. Tag thay thế nếu cần, cùng ghi chú phát hành cập nhật.

Người dùng đã tải tag cần xác minh thông tin trước khi xóa hoặc cập nhật tag local. Nếu tag đã được dùng để tạo artifact hoặc triển khai, nhóm cần xác định artifact cũ có còn hợp lệ không, có cần phát hành lại và cách phân biệt artifact cũ/mới.

Một quy trình có kiểm soát có thể là:

```text
Kiểm tra tag local và remote
          |
          v
Xác định tag có phải mốc release đã công bố?
          |
     +----+----+
     |         |
    Không      Có
     |         |
     v         v
Sửa tag local  Thông báo và thống nhất với người phụ thuộc
     |         |
     v         v
Kiểm tra lại   Cân nhắc phát hành tag mới thay cho retag
     |         |
     +----+----+
          |
          v
Push hoặc xóa tag theo quyền và chính sách
          |
          v
Xác minh remote và hướng dẫn đồng bộ local
```

## 10. Những lỗi và rủi ro thường gặp

- **Nghĩ `git tag -d` xóa tag trên máy chủ.** Lệnh này chỉ xóa tag local; cần lệnh push delete để xóa remote tag.
- **Nghĩ xóa remote tag sẽ xóa tag ở mọi máy.** Mỗi clone có ref tag local riêng; người dùng phải cập nhật theo hướng dẫn.
- **Dùng `git push --tags` để đẩy một tag.** Lệnh này có thể công bố thêm nhiều tag local không liên quan. Dùng refspec cho tag cụ thể.
- **Force push tag release mà không thông báo.** Người dùng, CI và artifact có thể cùng tên tag nhưng trỏ tới nội dung khác nhau.
- **Không kiểm tra annotated tag object.** Hai tag có thể cùng trỏ tới một commit nhưng khác thông điệp, tagger hoặc chữ ký; việc tạo lại tag có thể thay đổi các metadata này.
- **Xóa tag rồi cho rằng commit cũng bị xóa.** Commit có thể vẫn được branch, tag khác, reflog hoặc ref khác giữ lại.
- **Prune tất cả tag mà không xem cấu hình.** Có thể làm mất tag local chỉ tồn tại trong repository của bạn.
- **Không hướng dẫn người đã checkout tag cũ.** Di chuyển tag không tự di chuyển branch hoặc HEAD đã được tạo từ commit cũ.

## 11. Ví dụ thực hành: sửa một tag release tạo nhầm

Giả sử nhóm phát hiện tag `v2.3.0` đang trỏ tới commit kiểm thử thay vì commit phát hành. Trước tiên, xác minh trạng thái:

```bash
git show --no-patch --decorate v2.3.0
git rev-parse "v2.3.0^{}"
git ls-remote --tags origin v2.3.0
```

Nếu tag chưa được công bố và chỉ sai ở local, cập nhật tag local tới commit phát hành đã xác nhận:

```bash
git tag -f -a -m "Release v2.3.0" v2.3.0 <release-commit>
git show --no-patch --decorate v2.3.0
```

Nếu tag đã được công bố, ưu tiên tạo tag phiên bản sửa mới theo chính sách release, chẳng hạn `v2.3.1`. Nếu tổ chức quyết định phải sửa tag hiện có, thông báo cho mọi người và cập nhật remote theo quy trình được duyệt:

```bash
git push --force origin refs/tags/v2.3.0:refs/tags/v2.3.0
git ls-remote --tags origin v2.3.0
```

Người đã fetch tag cũ cần xác nhận thông báo, xóa tag local cũ rồi fetch lại. Pipeline và artifact được tạo từ tag cũ cũng cần được rà soát; việc di chuyển ref không tự thay đổi các bản build đã tồn tại.

## 12. Ghi nhớ

Đổi hoặc xóa tag local chỉ tác động tới repository hiện tại; đổi hoặc xóa tag remote cần một thao tác push riêng. Người đã fetch tag vẫn giữ bản local cũ cho tới khi họ chủ động cập nhật. Với tag release đã công bố, hãy ưu tiên giữ mốc bất biến và phát hành tag sửa mới; nếu buộc phải retag hoặc xóa, cần xác minh commit đích, thông báo cho người phụ thuộc, hướng dẫn đồng bộ và kiểm tra lại pipeline cùng artifact.
