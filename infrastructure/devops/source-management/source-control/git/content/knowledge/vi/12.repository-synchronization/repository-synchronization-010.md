# Đồng bộ tag một cách tường minh và các giới hạn khi cập nhật tag

Tag giúp gắn một tên dễ nhớ vào một đối tượng Git, thường là commit đại diện cho một phiên bản phát hành như `v1.2.0`. Khi làm việc với remote, việc đồng bộ branch và tag có quy tắc khác nhau: Git có thể tự lấy một số tag trong lúc fetch, nhưng push tag cần được yêu cầu rõ ràng hoặc bật theo một chính sách cụ thể.

Hiểu các quy tắc này giúp bạn tránh thiếu tag phát hành khi clone/fetch, tránh đẩy nhầm tag nội bộ lên máy chủ và tránh vô tình thay đổi một tag mà nhóm đã dùng để xác định phiên bản.

## 1. Tag được lưu ở đâu và có gì khác branch?

Branch là một tham chiếu thường xuyên tiến lên commit mới khi bạn tạo commit. Tag thường được dùng để đánh dấu một mốc ổn định, chẳng hạn phiên bản phát hành. Tên tag nằm trong namespace `refs/tags/` của repository.

Git có hai loại tag phổ biến:

- **Lightweight tag** chỉ là một tham chiếu trực tiếp đến đối tượng được đánh dấu. Tạo nhanh bằng `git tag v1.2.0`.
- **Annotated tag** là một đối tượng tag riêng, có thể lưu người tạo, thời điểm, thông điệp và chữ ký. Tạo bằng `git tag -a v1.2.0 -m "Release v1.2.0"`.

Ví dụ tạo và xem tag:

```bash
git tag -a v1.2.0 -m "Release v1.2.0"
git tag --list
git show v1.2.0
```

Với tag có chữ ký, bạn có thể xác minh bằng:

```bash
git tag -s v1.2.0 -m "Release v1.2.0"
git tag -v v1.2.0
```

Lệnh `git tag -s` cần môi trường ký đã được cấu hình, chẳng hạn khóa GPG. Việc fetch một tag có chữ ký chỉ tải đối tượng tag và chữ ký về; Git không tự xác minh rằng chữ ký đó đáng tin. Hãy chạy `git tag -v` và kiểm tra danh tính người ký theo chính sách của nhóm.

Tag là tham chiếu cục bộ trong repository, không phải nhánh theo dõi remote như `origin/main`. Khi bạn fetch tag từ một remote, tag được tạo trong `refs/tags/` của repository hiện tại. Nếu fetch cùng tên tag từ một remote khác, Git vẫn phải dùng chung tên tag đó; không có namespace riêng kiểu `origin/v1.2.0` và `upstream/v1.2.0`.

## 2. Git tự động lấy tag như thế nào khi fetch?

Lệnh fetch thông thường:

```bash
git fetch origin
```

Ngoài các ref được cấu hình để fetch, Git có cơ chế *auto-follow*: khi một đối tượng được tải về có tag trỏ đến nó, Git có thể tự lấy tag liên quan đó. Vì vậy, bạn có thể thấy một số tag mới sau khi fetch branch dù chưa dùng `--tags`.

Auto-follow không có nghĩa là Git luôn tải mọi tag trên remote. Nếu cần đồng bộ toàn bộ tag từ remote, hãy chỉ định rõ:

```bash
git fetch --tags origin
```

Lệnh này lấy tất cả tag từ `origin` cùng các đối tượng cần thiết. Các ref branch vẫn được fetch theo refspec và cấu hình fetch hiện có; `--tags` không có nghĩa là chỉ fetch tag.

Nếu repository không muốn tự động lấy tag trong các lần fetch thông thường, có thể dùng:

```bash
git fetch --no-tags origin
```

`--no-tags` tắt cơ chế auto-follow cho lần fetch đó. Nó không xóa các tag đã có trong local repository. Bạn vẫn có thể lấy một tag cụ thể bằng lệnh fetch tường minh.

Có thể cấu hình hành vi auto-follow cho một remote:

```bash
git config remote.origin.tagOpt --no-tags
```

Sau cấu hình này, các lần fetch thông thường từ `origin` không tự động theo tag. Khi cần lấy toàn bộ tag, vẫn có thể chạy `git fetch --tags origin`.

## 3. Lấy một tag cụ thể

Khi chỉ cần một phiên bản, lấy đúng tag sẽ rõ ràng hơn việc tải tất cả tag:

```bash
git fetch origin tag v1.2.0
```

Cú pháp trên yêu cầu Git lấy tag `v1.2.0` từ `origin` và ghi nó vào local tag cùng tên. Một cách viết tường minh bằng refspec là:

```bash
git fetch origin refs/tags/v1.2.0:refs/tags/v1.2.0
```

Kiểm tra tag đã có trong local:

```bash
git tag --list v1.2.0
git show v1.2.0
```

Để xem các tag mà remote đang công bố:

```bash
git ls-remote --tags origin
```

Với annotated tag, kết quả thường có hai dòng: một dòng cho đối tượng tag tại `refs/tags/v1.2.0` và một dòng có hậu tố `^{}` cho đối tượng mà tag đó trỏ tới sau khi được bóc (peeled), thường là commit. Lightweight tag thường chỉ có dòng tham chiếu trực tiếp. Đây là cách hữu ích để so sánh tag trên máy chủ với tag trong local mà chưa cần fetch.

## 4. Đẩy tag lên remote

Git không mặc định đẩy mọi tag khi bạn push branch. Có ba cách thường dùng.

### Đẩy một tag được chọn

Khi tạo tag phát hành, cách an toàn và dễ kiểm soát là chỉ đẩy tag đó:

```bash
git push origin v1.2.0
```

Lệnh này đẩy tag `v1.2.0` lên `origin`. Bạn cũng có thể viết rõ refspec:

```bash
git push origin refs/tags/v1.2.0:refs/tags/v1.2.0
```

### Đẩy tất cả tag local

```bash
git push --tags origin
```

`--tags` đẩy tất cả tag local có trong `refs/tags/`, bao gồm cả lightweight và annotated tag. Hãy kiểm tra `git tag --list` trước khi chạy vì repository có thể chứa tag thử nghiệm, tag cá nhân hoặc tag không thuộc phạm vi phát hành hiện tại.

### Đẩy các annotated tag liên quan đến commit đang push

```bash
git push --follow-tags origin main
```

`--follow-tags` bổ sung các annotated tag còn thiếu trên remote và có thể tiếp cận từ các ref đang được push. Tùy chọn này không đẩy tất cả tag trong repository và không tự đẩy lightweight tag. Nó phù hợp khi quy trình phát hành dùng annotated tag và muốn đẩy tag liên quan cùng branch.

Có thể bật hành vi này mặc định cho các lần push bằng:

```bash
git config push.followTags true
```

Khi đó, push thông thường sẽ áp dụng chính sách follow-tags. Hãy thống nhất cấu hình này với quy trình nhóm để tránh bất ngờ khi phát hành.

| Nhu cầu | Lệnh | Phạm vi tag được đẩy |
|---|---|---|
| Đẩy một phiên bản cụ thể | `git push origin v1.2.0` | Chỉ tag được chỉ định |
| Đồng bộ toàn bộ tag local | `git push --tags origin` | Mọi lightweight và annotated tag local |
| Đẩy tag phát hành liên quan tới branch | `git push --follow-tags origin main` | Annotated tag còn thiếu trên remote và reachable từ ref đang push |

## 5. Kiểm tra trước và sau khi đồng bộ

Trước khi đẩy tag, hãy xác nhận tag trỏ đến commit mong muốn:

```bash
git show --no-patch --decorate v1.2.0
git rev-parse 'v1.2.0^{commit}'
git status
```

Nếu tag được ký, xác minh chữ ký:

```bash
git tag -v v1.2.0
```

Sau khi push, kiểm tra remote:

```bash
git ls-remote --tags origin v1.2.0
```

Bạn cũng có thể fetch lại tag cụ thể vào một clone khác để kiểm tra rằng người dùng khác có thể lấy đúng mốc phát hành:

```bash
git fetch origin tag v1.2.0
git show v1.2.0
```

Lưu ý rằng `git ls-remote` cho biết ref mà remote đang công bố; nó không xác minh chữ ký tag. Muốn xác minh chữ ký, phải có đối tượng tag trong local và chạy `git tag -v`.

## 6. Khi tag cùng tên nhưng trỏ đến đối tượng khác

Tag phát hành thường được xem là bất biến. Khi `v1.2.0` đã được công bố, nhóm nên giữ nguyên đích mà tag trỏ tới. Nếu phát hiện lỗi trong phiên bản, thông thường hãy tạo tag phiên bản mới hoặc phát hành bản vá, thay vì âm thầm di chuyển tag cũ.

Git bảo vệ tag đã tồn tại khỏi việc bị thay đổi ngoài ý muốn. Khi fetch một tag cùng tên nhưng trỏ tới đối tượng khác, các phiên bản Git hiện đại thường từ chối cập nhật trừ khi bạn yêu cầu force. Push một tag đã tồn tại trên remote nhưng trỏ tới đối tượng khác cũng thường bị từ chối.

Trước khi xử lý xung đột, so sánh đối tượng tag ở local và remote:

```bash
git rev-parse v1.2.0
git ls-remote --tags origin v1.2.0
```

Với annotated tag, mã đối tượng tag và mã commit sau khi peeled có thể khác nhau. Để so sánh chính xác đích commit, xem dòng `^{}` từ `git ls-remote` hoặc dùng `git rev-parse 'v1.2.0^{commit}'` trong local.

Nếu nhóm đã thống nhất phải cập nhật một tag cụ thể trong local từ remote, hãy dùng refspec có dấu `+` cho đúng tag:

```bash
git fetch origin +refs/tags/v1.2.0:refs/tags/v1.2.0
```

Dấu `+` cho phép cập nhật ref đích dù không phải fast-forward. Chỉ thực hiện sau khi xác nhận tag remote là nguồn chuẩn, vì thao tác này sẽ thay tag cùng tên trong local.

Nếu có phê duyệt rõ ràng để thay tag trên remote, có thể force push đúng tag:

```bash
git push --force origin refs/tags/v1.2.0:refs/tags/v1.2.0
```

Đây là thao tác thay đổi tham chiếu đã công bố. Những clone khác vẫn có thể giữ tag cũ và sẽ cần phối hợp cập nhật. Không dùng force push tag như cách sửa lỗi phát hành thông thường.

## 7. Xóa tag và giới hạn khi prune

Xóa tag ở local:

```bash
git tag -d v1.2.0
```

Xóa tag trên remote:

```bash
git push origin --delete v1.2.0
```

Hai thao tác này độc lập. Xóa tag trên remote không tự xóa tag đã có trong các clone của đồng nghiệp; mỗi clone cần xóa tag local nếu muốn loại bỏ nó.

Thông thường, `git fetch --prune origin` dọn các remote-tracking ref không còn tồn tại trên remote theo refspec fetch. Cơ chế auto-follow tag không phải là một refspec ánh xạ toàn bộ `refs/tags/*`, nên `--prune` đơn lẻ không mặc nhiên xóa mọi tag local không còn trên remote.

Nếu muốn đồng bộ tập tag local theo remote và xóa tag local không còn tồn tại trên remote, có thể dùng:

```bash
git fetch --prune --prune-tags origin
```

`--prune-tags` thêm ánh xạ tag tường minh và kết hợp prune. Lệnh này có thể xóa tag local không có trên `origin`, kể cả tag cá nhân hoặc tag được lấy từ remote khác. Tag cùng tên nhưng trỏ đến đối tượng khác vẫn chịu quy tắc bảo vệ cập nhật tag của Git; prune không đồng nghĩa với việc force ghi đè mọi tag. Vì tất cả remote dùng chung namespace `refs/tags/` trong một repository, prune theo một remote có thể ảnh hưởng tag mà bạn cần cho remote khác.

Nếu chỉ muốn xem remote có tag nào trước khi dọn, hãy kiểm tra:

```bash
git tag --list
git ls-remote --tags origin
```

Không nhầm `git remote prune origin` với việc dọn tag. Lệnh này dọn các remote-tracking branch đã lỗi thời của remote; nó không phải lệnh đồng bộ hoặc xóa toàn bộ tag local.

## 8. Quy trình đồng bộ tag cho nhóm

Một quy trình phát hành có thể thực hiện theo thứ tự sau:

1. **Tạo tag sau khi xác nhận commit.** Dùng annotated tag, hoặc signed tag nếu chính sách yêu cầu.
2. **Kiểm tra tag.** Xem commit đích bằng `git show` hoặc `git rev-parse`; xác minh chữ ký nếu có.
3. **Đẩy đúng tag phát hành.** Dùng `git push origin v1.2.0`; chỉ dùng `--tags` khi chủ đích đồng bộ mọi tag local.
4. **Xác nhận remote.** Dùng `git ls-remote --tags origin v1.2.0` để kiểm tra tag đã được công bố.
5. **Hướng dẫn clone khác cập nhật.** Dùng `git fetch origin tag v1.2.0` hoặc `git fetch --tags origin` tùy nhu cầu.
6. **Giữ lịch sử phát hành ổn định.** Nếu tag đã công bố cần sửa, trao đổi với nhóm và thống nhất cách xử lý trước khi force update hoặc xóa.

Ví dụ đầy đủ:

```bash
git tag -a v1.2.0 -m "Release v1.2.0"
git show --no-patch v1.2.0
git push origin v1.2.0
git ls-remote --tags origin v1.2.0
```

Trong một clone khác:

```bash
git fetch origin tag v1.2.0
git show v1.2.0
```

## 9. Bài tập thực hành

Giả sử nhóm chuẩn bị phát hành `v2.4.0`. Repository local có một số tag thử nghiệm cũ, vì vậy bạn chỉ muốn công bố tag phát hành này.

1. Tạo một annotated tag `v2.4.0` trỏ tới commit phát hành đã được xác nhận.
2. Dùng `git show v2.4.0` để xem thông tin tag và commit đích.
3. Dùng `git push origin v2.4.0` để đẩy riêng tag này.
4. Dùng `git ls-remote --tags origin v2.4.0` để xác nhận remote đã nhận tag.
5. Trong clone khác, dùng `git fetch origin tag v2.4.0` và kiểm tra tag.
6. So sánh kết quả của `git push --tags` và `git push --follow-tags` trong một repository thử nghiệm có cả lightweight tag và annotated tag.

Bạn hoàn thành bài tập khi giải thích được vì sao fetch thông thường có thể chỉ lấy một phần tag, sự khác nhau giữa ba cách push tag, và rủi ro khi force update hoặc prune tag.
