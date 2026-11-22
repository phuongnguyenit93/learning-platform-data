# Tìm danh sách tệp xung đột bằng git status và git diff

Khi merge, rebase, cherry-pick hoặc áp dụng một thay đổi từ nơi khác, Git có thể gặp những chỉnh sửa không thể tự kết hợp. Ví dụ, hai nhánh cùng sửa một đoạn trong `LoginService.java`, hoặc một nhánh xóa tệp trong khi nhánh còn lại tiếp tục chỉnh sửa tệp đó. Git đánh dấu các đường dẫn liên quan là **unmerged** để người phát triển quyết định nội dung cuối cùng.

Trước khi giải quyết, cần biết chính xác những tệp nào đang xung đột và mỗi tệp thuộc loại xung đột nào. `git status` cho biết trạng thái tổng thể của repository; `git diff` giúp lọc danh sách đường dẫn unmerged và xem phần khác biệt cần xử lý. Kết hợp hai lệnh này giúp bạn xác định phạm vi công việc trước khi chỉnh sửa.

## 1. Khi nào Git xem một tệp là đang xung đột?

Trong lúc tích hợp hai dòng lịch sử, Git cố gắng kết hợp thay đổi tự động. Nếu không thể xác định một kết quả duy nhất, Git giữ thông tin của các phiên bản liên quan trong *index* (staging area) và đánh dấu đường dẫn là chưa hợp nhất (*unmerged path*).

Một số tình huống thường gặp:

- **Cùng sửa một vùng nội dung:** hai nhánh thay đổi những dòng chồng lấn trong cùng một tệp.
- **Thêm cùng một đường dẫn:** hai nhánh độc lập tạo tệp có cùng tên nhưng nội dung khác nhau.
- **Xóa và sửa:** một nhánh xóa tệp trong khi nhánh kia sửa tệp đó.
- **Đổi tên hoặc di chuyển:** các nhánh thực hiện những thao tác đổi tên, xóa hoặc thêm tệp mà Git không thể ghép thành một kết quả rõ ràng.
- **Xung đột nhị phân:** hai phía thay đổi cùng một tệp nhị phân, chẳng hạn ảnh hoặc tệp thiết kế, nên Git không thể ghép nội dung như với văn bản.

Với xung đột nội dung dạng văn bản, tệp trong working tree thường có các dấu phân cách như `<<<<<<<`, `=======` và `>>>>>>>`. Tuy nhiên, không phải mọi xung đột đều có các dấu này. Xung đột xóa/sửa, đổi tên hoặc nhị phân có thể không tạo ra một khối marker trong tệp. Vì vậy, trạng thái unmerged trong Git mới là căn cứ để xác định danh sách xung đột; tìm marker chỉ là cách hỗ trợ đọc một số loại xung đột văn bản.

## 2. Dùng git status để xem trạng thái xung đột

Đầu tiên, chạy lệnh tại một thư mục nằm trong repository:

```bash
git status
```

Khi một thao tác merge gặp xung đột, kết quả thường cho biết nhánh hiện tại, thao tác đang thực hiện và các nhóm tệp. Ví dụ:

```text
On branch feature/login
You have unmerged paths.
  (fix conflicts and run "git commit")
  (use "git merge --abort" to abort the merge)

Changes to be committed:
        new file:   src/login/Validator.java

Unmerged paths:
  (use "git add/rm <file>..." as appropriate to mark resolution)
        both modified:   src/login/LoginService.java
        deleted by them: src/login/LegacyLogin.java
        both added:      src/config/security.yml
```

Phần `Unmerged paths` liệt kê các đường dẫn Git chưa thể hợp nhất. Trong ví dụ trên, có ba tệp cần kiểm tra. `Changes to be committed` là nhóm thay đổi đã được stage; nhóm này có thể chứa những tệp đã được xử lý hoặc thay đổi độc lập, nên không đồng nghĩa với danh sách xung đột còn lại.

### Xem trạng thái dạng ngắn

Để có kết quả gọn, dễ quét hoặc dùng trong ghi chú, chạy:

```bash
git status --short
```

Ví dụ:

```text
M  README.md
UU src/login/LoginService.java
UD src/login/LegacyLogin.java
AA src/config/security.yml
```

Hai ký tự đầu mỗi dòng biểu diễn trạng thái ở index và working tree. Với các mã unmerged, có thể đọc như sau:

| Mã | Ý nghĩa |
|---|---|
| `DD` | Cả hai phía đều xóa tệp |
| `AU` | Tệp được thêm ở phía hiện tại, chưa được hợp nhất với phía còn lại |
| `UD` | Phía còn lại xóa tệp |
| `UA` | Phía còn lại thêm tệp |
| `DU` | Phía hiện tại xóa tệp |
| `AA` | Cả hai phía cùng thêm một đường dẫn |
| `UU` | Cả hai phía cùng sửa tệp |

Các mã trên mô tả trạng thái xung đột trong định dạng ngắn của `git status`. Chữ `U` có nghĩa là *updated but unmerged*. Dòng `M  README.md` trong ví dụ là thay đổi đã stage thông thường, không phải mã unmerged.

Từ “phía hiện tại” và “phía còn lại” cần được hiểu theo thao tác đang chạy. Trong merge, `ours` thường là nhánh đang đứng và `theirs` là nhánh được merge vào. Trong rebase, ý nghĩa thực tế của `ours` và `theirs` có thể khiến người mới nhầm: `ours` thường là nhánh đích/upstream mà commit đang được phát lại lên đó, còn `theirs` là commit từ nhánh đang rebase. Hãy kiểm tra thao tác hiện tại trước khi chọn nội dung theo một phía.

## 3. Dùng git diff để lọc đúng danh sách tệp unmerged

`git diff` có thể lọc theo trạng thái thay đổi. Bộ lọc `U` đại diện cho các đường dẫn unmerged. Để chỉ lấy tên tệp đang xung đột, chạy:

```bash
git diff --name-only --diff-filter=U
```

Ví dụ kết quả:

```text
src/login/LoginService.java
src/login/LegacyLogin.java
src/config/security.yml
```

Đây là lệnh hữu ích nhất khi bạn chỉ cần danh sách đường dẫn còn xung đột. Nó không đưa các tệp chỉ đang modified hoặc staged thông thường vào danh sách. Nếu không có kết quả, hiện tại Git không còn đường dẫn unmerged được lệnh này phát hiện; hãy dùng `git status` để kiểm tra xem thao tác merge/rebase đã hoàn tất hay còn đang chờ bước kết thúc.

Một số biến thể hữu ích:

```bash
# Hiển thị tên tệp cùng trạng thái lọc U.
git diff --name-status --diff-filter=U

# Xem phần khác biệt của các đường dẫn unmerged.
git diff --diff-filter=U

# Xem thống kê thay đổi của các đường dẫn unmerged.
git diff --stat --diff-filter=U
```

Nếu cần kiểm tra một đường dẫn cụ thể, hãy đặt đường dẫn sau `--` để Git hiểu đó là pathspec, kể cả khi tên tệp có ký tự đặc biệt:

```bash
git diff -- "src/login/LoginService.java"
```

Để xem phần khác biệt kết hợp của một tệp đang xung đột, có thể dùng:

```bash
git diff --cc -- "src/login/LoginService.java"
```

Định dạng combined diff thể hiện những dòng liên quan đến các phía của xung đột. Với một tệp văn bản có conflict marker, mở trực tiếp tệp trong editor cũng giúp đọc rõ các đoạn `<<<<<<<`, `=======`, `>>>>>>>` và nội dung cần chọn hoặc kết hợp.

## 4. Phân biệt danh sách xung đột với các thay đổi thông thường

Không phải mọi tệp xuất hiện trong `git status` hoặc `git diff` đều là tệp xung đột. Một repository có thể đồng thời có:

- Thay đổi chưa stage trong working tree.
- Thay đổi đã stage để chuẩn bị commit.
- Tệp chưa được Git theo dõi.
- Đường dẫn unmerged cần giải quyết.

Các lệnh sau phục vụ những mục đích khác nhau:

| Lệnh | Nội dung chính |
|---|---|
| `git status` | Trạng thái tổng thể, bao gồm nhánh và các nhóm tệp |
| `git status --short` | Trạng thái gọn của từng đường dẫn |
| `git diff` | Khác biệt giữa working tree và index đối với thay đổi thông thường |
| `git diff --staged` | Khác biệt đã stage so với commit hiện tại |
| `git diff --name-only --diff-filter=U` | Chỉ tên các đường dẫn đang unmerged |
| `git diff --diff-filter=U` | Phần diff được lọc theo đường dẫn unmerged |

Nếu mục tiêu là lập danh sách tệp còn xung đột, không nên dùng riêng `git diff --name-only`, vì lệnh đó có thể liệt kê các thay đổi thông thường và khiến phạm vi xử lý bị hiểu rộng hơn. Hãy thêm `--diff-filter=U`.

## 5. Đọc chi tiết một tệp đang xung đột

Sau khi xác định đường dẫn bằng `git status` hoặc `git diff --name-only --diff-filter=U`, bạn có thể kiểm tra từng tệp.

### Xem các conflict marker trong tệp văn bản

Ví dụ `LoginService.java` có thể chứa:

```java
public User authenticate(String username) {
<<<<<<< HEAD
    return userRepository.findByUsername(username);
=======
    return userRepository.findActiveUser(username);
>>>>>>> feature/active-user
}
```

Các phần thường có ý nghĩa:

- `<<<<<<< HEAD`: bắt đầu phần nội dung ở một phía của xung đột.
- `=======`: phân cách hai phía.
- `>>>>>>> feature/active-user`: kết thúc phần còn lại; nhãn thường cho biết nguồn thay đổi.

Nếu repository được cấu hình dùng conflict style `diff3` hoặc `zdiff3`, marker `|||||||` có thể xuất hiện để hiển thị cả phiên bản cơ sở (*base*). Không nên mặc định mọi xung đột chỉ có đúng hai dòng nội dung đơn giản; hãy đọc toàn bộ vùng liên quan và ngữ cảnh của hàm hoặc cấu hình.

### So sánh working tree với từng phiên bản trong index

Khi cần biết nội dung hiện tại khác từng phía ra sao, Git cung cấp các lựa chọn dành cho đường dẫn unmerged:

```bash
# So sánh với phiên bản cơ sở chung.
git diff --base -- "src/login/LoginService.java"

# So sánh với phiên bản ours.
git diff --ours -- "src/login/LoginService.java"

# So sánh với phiên bản theirs.
git diff --theirs -- "src/login/LoginService.java"
```

Các lệnh này giúp xem sự khác nhau giữa working tree và từng phiên bản được lưu trong index. Chúng hữu ích khi marker trong tệp khó đọc hoặc khi cần hiểu một thay đổi đến từ phía nào. Nhớ rằng `ours` và `theirs` phụ thuộc ngữ cảnh merge/rebase như đã giải thích ở trên.

## 6. Quy trình xác định phạm vi xung đột

Khi một thao tác tích hợp bị dừng vì conflict, có thể thực hiện lần lượt:

1. Chạy `git status` để xác nhận repository đang ở trạng thái nào và Git báo thao tác gì đang chờ xử lý.
2. Chạy `git status --short` để quét nhanh trạng thái từng đường dẫn.
3. Chạy `git diff --name-only --diff-filter=U` để lấy danh sách chính xác các đường dẫn còn unmerged.
4. Với từng đường dẫn, xem loại xung đột trong `git status`, mở tệp nếu là văn bản và dùng `git diff --cc -- <path>` hoặc các lựa chọn `--base`, `--ours`, `--theirs` khi cần so sánh.
5. Ghi nhận các tệp cần xử lý và xác định quyết định nội dung với ngữ cảnh của chức năng, cấu hình hoặc tài nguyên tương ứng.

Ví dụ, một nhóm có thể dùng các lệnh sau để bắt đầu kiểm tra:

```bash
git status
git status --short
git diff --name-only --diff-filter=U
git diff --cc -- "src/login/LoginService.java"
```

Sau khi chỉnh sửa và giải quyết một tệp, `git add <path>` (hoặc `git rm <path>` nếu quyết định xóa tệp) thông báo cho Git rằng đường dẫn đó đã được xử lý. Khi đó, đường dẫn không còn ở trạng thái unmerged. Lặp lại việc kiểm tra:

```bash
git diff --name-only --diff-filter=U
git status
```

Khi lệnh lọc không còn liệt kê đường dẫn nào, hãy đọc `git status` để xem còn bước kết thúc merge, rebase hoặc cherry-pick nào đang chờ. Không suy luận rằng toàn bộ thao tác đã hoàn tất chỉ từ việc danh sách unmerged rỗng.

## 7. Kiểm tra bổ sung và lỗi dễ mắc

### Kiểm tra định dạng khác biệt

```bash
git diff --check
```

Lệnh này phát hiện một số lỗi whitespace trong diff, chẳng hạn khoảng trắng ở cuối dòng. Nó hữu ích sau khi chỉnh sửa nhưng **không thay thế** `git diff --name-only --diff-filter=U` và không chứng minh rằng mọi xung đột đã được giải quyết.

### Dùng output ổn định khi viết script

Nếu cần đưa trạng thái vào script, có thể dùng:

```bash
git status --porcelain=v1
```

Định dạng porcelain được thiết kế để máy đọc ổn định hơn output mô tả dành cho người dùng. Khi xử lý kết quả, cần lưu ý tên tệp có thể chứa dấu cách hoặc ký tự đặc biệt; không nên tách dòng một cách ngây thơ bằng khoảng trắng.

### Những lỗi thường gặp

- **Dùng `git diff --name-only` rồi coi tất cả kết quả là conflict:** lệnh này không lọc riêng đường dẫn unmerged. Dùng `--diff-filter=U`.
- **Chỉ tìm `<<<<<<<` trong source code:** xung đột nhị phân, xóa/sửa hoặc đổi tên có thể không có marker. Kiểm tra `git status`.
- **Thấy marker đã biến mất và nghĩ Git đã ghi nhận giải quyết:** chỉnh sửa văn bản chưa tự xóa trạng thái unmerged trong index. Cần stage kết quả bằng `git add` hoặc xác nhận thao tác xóa bằng `git rm`.
- **Nhầm thay đổi đã stage với tệp còn conflict:** đọc phần `Unmerged paths` hoặc lọc trạng thái `U` để xác định đúng nhóm.
- **Hiểu sai ours/theirs khi rebase:** xem thông tin thao tác trong `git status` và xác định nhánh đích cùng commit đang được phát lại trước khi chọn một phía.
- **Cho rằng danh sách unmerged rỗng nghĩa là merge đã kết thúc:** có thể vẫn còn bước tạo commit hoặc tiếp tục rebase/cherry-pick. Kiểm tra trạng thái tổng thể.

## 8. Ghi nhớ

`git status` là điểm bắt đầu để hiểu trạng thái repository và biết Git đang chờ xử lý những gì. `git status --short` giúp quét nhanh các mã trạng thái; `git diff --name-only --diff-filter=U` là cách trực tiếp để lấy danh sách đường dẫn chưa hợp nhất. Sau khi có danh sách, dùng `git diff --cc`, các tùy chọn `--base`/`--ours`/`--theirs` và nội dung tệp để hiểu từng trường hợp.

Hãy luôn xác nhận lại bằng `git status` sau khi xử lý. Git dựa vào trạng thái trong index để biết một đường dẫn đã được giải quyết; việc chỉ sửa hoặc xóa conflict marker trong editor chưa đủ để hoàn tất bước này.
