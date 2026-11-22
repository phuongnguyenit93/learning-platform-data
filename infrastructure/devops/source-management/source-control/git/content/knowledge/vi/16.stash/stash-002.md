# Tạo stash có mô tả và xem danh sách stash

Khi đang làm một công việc dở dang nhưng cần chuyển sang xử lý việc khác, bạn có thể cất tạm thay đổi bằng **Git stash**. Mỗi stash lưu một trạng thái công việc tại thời điểm tạo. Bạn có thể thêm mô tả để nhận biết mục đích của lần cất đó, rồi xem danh sách các stash đang có để tìm lại đúng phần việc.

Lệnh thường dùng nhất là `git stash push -m "mo-ta"`. Sau đó, `git stash list` hiển thị các mục stash theo thứ tự mới nhất trước. Bài này tập trung vào cách tạo stash có mô tả, xác định nội dung và đọc danh sách stash.

## 1. Stash dùng để làm gì?

Stash giúp tạm cất các thay đổi chưa commit để working tree trở về trạng thái sạch hơn, thuận tiện cho việc chuyển nhánh, cập nhật code hoặc xử lý một yêu cầu khẩn cấp.

Ví dụ, bạn đang sửa hai file của tính năng thanh toán nhưng chưa muốn tạo commit. Một lỗi cần xử lý ngay xuất hiện trên nhánh khác. Bạn có thể cất thay đổi hiện tại, chuyển nhánh để sửa lỗi, rồi quay lại lấy phần việc đã cất.

Stash là dữ liệu được lưu trong repository local. Nó không tự động được push lên remote như branch và không phải bản sao lưu dài hạn. Nếu cần chia sẻ công việc hoặc lưu lịch sử bền vững, hãy tạo branch và commit phù hợp.

## 2. Tạo stash kèm mô tả

Cú pháp hiện đại:

```bash
git stash push -m "mo-ta-ngan"
```

Hoặc dùng tên tùy chọn đầy đủ:

```bash
git stash push --message "mo-ta-ngan"
```

Ví dụ trong dự án:

```bash
git status
git stash push -m "Tam dung phan xu ly thanh toan"
git status
```

Thông điệp được lưu cùng mục stash và hiển thị trong danh sách. Hãy mô tả mục đích hoặc phạm vi thay đổi, chẳng hạn:

```bash
git stash push -m "WIP: validate payment request"
git stash push -m "Tam cat giao dien trang dang nhap"
git stash push -m "Luu thay doi truoc khi cap nhat main"
```

Một mô tả tốt giúp bạn nhận ra stash sau vài ngày, khi danh sách đã có nhiều mục. Có thể dùng mã ticket, tên tính năng hoặc lý do tạm cất; tránh những mô tả chung chung như `test`, `tmp` hay `fix`.

Nếu không có thay đổi phù hợp để cất, Git thông báo không có thay đổi local để lưu và không tạo một stash mới. Vì vậy, hãy kiểm tra `git status` trước khi tạo.

### Stash một số file được chọn

Bạn có thể giới hạn stash vào các đường dẫn cụ thể bằng pathspec đặt sau `--`:

```bash
git stash push -m "Tam cat file cau hinh" -- src/config.yml
```

Lệnh này chỉ cất thay đổi phù hợp với `src/config.yml`; những file khác vẫn ở working tree. Dấu `--` phân tách tùy chọn của Git với đường dẫn, đặc biệt hữu ích khi tên file có thể bị hiểu nhầm là revision hoặc tùy chọn.

Có thể chỉ định nhiều đường dẫn:

```bash
git stash push -m "Tam cat phan API" -- src/api/PaymentController.java src/api/PaymentService.java
```

Trước khi dùng pathspec, hãy kiểm tra `git status` để biết chính xác file nào sẽ được cất và file nào sẽ còn lại.

## 3. Những loại thay đổi nào được đưa vào stash?

Mặc định, `git stash push` lưu các thay đổi trên file đã được Git theo dõi (tracked), bao gồm thay đổi đã stage và chưa stage. File untracked và ignored không được đưa vào stash mặc định.

| Loại thay đổi | Mặc định | Tùy chọn |
|---|---|---|
| File tracked đã chỉnh sửa nhưng chưa stage | Được cất | Không cần thêm tùy chọn |
| File tracked đã stage | Được cất | Không cần thêm tùy chọn |
| File mới chưa được Git theo dõi (untracked) | Không được cất | `-u` hoặc `--include-untracked` |
| File bị ignore | Không được cất | `-a` hoặc `--all` |

Đưa cả file untracked vào stash:

```bash
git stash push -u -m "Luu ca file moi chua add"
```

Đưa cả file ignored vào stash:

```bash
git stash push -a -m "Luu ca file ignored"
```

`-a` bao gồm cả untracked và ignored. Hãy thận trọng với tùy chọn này vì thư mục build, file log, file sinh tự động hoặc dữ liệu local có thể chiếm dung lượng lớn. Không nên cất file chứa bí mật hoặc dữ liệu nhạy cảm vào stash nếu chính sách repository không cho phép.

### Chỉ cất thay đổi chưa stage

Nếu muốn giữ nguyên nội dung đã stage trong index và chỉ cất phần chỉnh sửa chưa stage, dùng `--keep-index`:

```bash
git stash push --keep-index -m "Tam cat phan chua stage"
```

Tùy chọn này hữu ích khi bạn đã stage một phần thay đổi để chuẩn bị commit, nhưng cần tạm cất phần còn lại. Các thay đổi đã stage được giữ trong index và working tree theo mục đích của tùy chọn. Hãy kiểm tra lại `git status` để xác nhận trạng thái sau lệnh.

Nếu chỉ muốn cất phần đã stage, Git có tùy chọn `--staged` ở các phiên bản hỗ trợ:

```bash
git stash push --staged -m "Tam cat phan da stage"
```

Tùy chọn này chỉ đưa các thay đổi đã stage vào stash. Nếu phiên bản Git đang dùng chưa hỗ trợ, hãy xem `git stash push -h` để kiểm tra tùy chọn khả dụng.

## 4. Kiểm tra stash vừa tạo

Sau khi stash, xem trạng thái working tree:

```bash
git status
```

Nếu không còn thay đổi tracked cần giữ, working tree sẽ trở về trạng thái sạch đối với những thay đổi đã được cất. Nếu vẫn còn file untracked, có thể bạn chưa dùng `-u`; nếu còn file ignored, có thể cần `-a` tùy mục đích.

Xem mục stash mới nhất:

```bash
git stash list
```

Ví dụ kết quả:

```text
stash@{0}: On feature/payment: WIP: validate payment request
stash@{1}: On main: Tam cat giao dien trang dang nhap
stash@{2}: On feature/report: Luu thay doi truoc khi cap nhat main
```

Mỗi dòng thường chứa:

- `stash@{n}`: bộ chọn tham chiếu tới mục stash trong reflog.
- Tên nhánh tại thời điểm tạo, nếu Git ghi nhận được.
- Thông điệp mô tả đã truyền qua `-m`/`--message`.

`stash@{0}` là mục mới nhất. Khi thêm stash mới hoặc xóa một mục, chỉ số `n` có thể thay đổi. Vì vậy, hãy xem lại `git stash list` ngay trước khi dùng một chỉ số, đặc biệt nếu có nhiều thao tác stash liên tiếp.

## 5. Lọc cách hiển thị danh sách stash

`git stash list` nhận các tùy chọn định dạng của `git log`. Ví dụ, hiển thị selector, thời gian và thông điệp:

```bash
git stash list --date=local --format="%gd | %cd | %gs"
```

Các placeholder thường hữu ích:

- `%gd`: tên selector dạng `stash@{0}`.
- `%cd`: ngày tạo commit theo định dạng ngày được chọn.
- `%gs`: thông điệp của mục reflog, thường chứa nhánh và mô tả stash.
- `%H`: mã hash đầy đủ của commit stash.

Nếu danh sách dài, có thể giới hạn số dòng:

```bash
git stash list -n 5
```

Hoặc chỉ hiển thị thông tin ngắn gọn:

```bash
git stash list --format="%gd %gs"
```

Thông điệp là văn bản để người dùng nhận diện; Git không tự áp đặt quy tắc đặt tên hoặc đảm bảo nội dung mô tả phản ánh chính xác file bên trong. Hãy xem diff trước khi áp dụng stash.

## 6. Xem nội dung một stash trong danh sách

Để xem tóm tắt thay đổi của stash mới nhất:

```bash
git stash show 'stash@{0}'
```

Hiển thị thống kê theo file:

```bash
git stash show --stat 'stash@{0}'
```

Xem toàn bộ patch:

```bash
git stash show -p 'stash@{0}'
```

Thay `stash@{0}` bằng selector cần kiểm tra. Nếu stash được tạo với `-u` hoặc `-a` và bạn muốn xem cả file untracked, dùng tùy chọn `--include-untracked` trên các phiên bản Git hỗ trợ:

```bash
git stash show --include-untracked --stat 'stash@{0}'
git stash show --include-untracked -p 'stash@{0}'
```

Kiểm tra `git stash show -h` nếu phiên bản đang dùng chưa nhận tùy chọn này.

Bạn cũng có thể xem commit stash bằng:

```bash
git show --stat 'stash@{0}'
git log -1 --oneline 'stash@{0}'
```

Stash thường được biểu diễn bằng một commit đặc biệt, có thể chứa thông tin về trạng thái working tree và index tại thời điểm cất. Đối với stash có file untracked, Git lưu thêm dữ liệu cần thiết để khôi phục chúng. Khi sử dụng stash, không cần tự thao tác trực tiếp với cấu trúc commit này; các lệnh `git stash` cung cấp giao diện phù hợp hơn.

## 7. Ví dụ quy trình tạo và tìm stash

Giả sử bạn đang sửa API thanh toán, có thay đổi ở file tracked và thêm một file test mới chưa được Git theo dõi. Bạn cần tạm chuyển sang nhánh `hotfix/login`.

Kiểm tra trạng thái trước khi cất:

```bash
git status --short
```

Tạo stash có mô tả và kèm file untracked:

```bash
git stash push -u -m "WIP: payment API and new tests"
```

Kiểm tra working tree và danh sách:

```bash
git status
git stash list
```

Tìm mục vừa tạo và xem nội dung:

```bash
git stash show --stat 'stash@{0}'
git stash show --include-untracked -p 'stash@{0}'
```

Giờ bạn có thể chuyển sang nhánh cần xử lý:

```bash
git switch hotfix/login
```

Khi quay lại nhánh tính năng, hãy kiểm tra danh sách stash một lần nữa để xác nhận selector đúng trước khi áp dụng. Việc áp dụng và xóa stash là chủ đề của các thao tác tiếp theo; tạo stash và xem danh sách chưa tự động khôi phục thay đổi.

## 8. Lưu ý khi quản lý nhiều stash

- Đặt mô tả có ngữ cảnh: tên tính năng, ticket hoặc lý do tạm cất.
- Dùng `git stash list` trước khi tham chiếu `stash@{n}` vì chỉ số thay đổi theo thời gian.
- Xem `git stash show -p` trước khi áp dụng một stash cũ nếu bạn không nhớ chính xác nội dung.
- Dùng `-u` khi cần giữ file untracked; chỉ dùng `-a` khi thật sự cần lưu cả file ignored.
- Stash nằm trong repository local và có thể bị xóa; không dùng nó thay cho commit hoặc bản sao lưu.
- Nếu có nhiều thay đổi độc lập hoặc cần chia sẻ với đồng đội, tạo branch riêng và commit sẽ dễ quản lý hơn.

## 9. Bài tập thực hành

Trong repository thử nghiệm, chỉnh sửa một file tracked, tạo thêm một file untracked và để một file ignored nếu dự án có cấu hình ignore phù hợp.

1. Chạy `git status --short` để nhận biết ba loại trạng thái.
2. Tạo stash chỉ với thay đổi tracked bằng `git stash push -m "WIP: tracked files"`.
3. Kiểm tra `git stash list` và xem nội dung bằng `git stash show -p 'stash@{0}'`.
4. Tạo stash khác có kèm file untracked bằng `git stash push -u -m "WIP: include new test"`.
5. Chạy `git stash list --format="%gd | %cd | %gs" --date=local` để xem selector, ngày và mô tả.
6. So sánh danh sách và nội dung sau khi tạo hai stash; giải thích vì sao mục mới nhất có selector `stash@{0}`.

Bạn hoàn thành bài tập khi có thể tạo stash với mô tả dễ nhận biết, chọn đúng phạm vi file cần cất và tìm lại đúng stash trong danh sách.
