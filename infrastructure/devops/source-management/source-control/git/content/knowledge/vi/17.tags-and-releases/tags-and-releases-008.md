# Tag có chữ ký và kiểm tra bằng git tag -v

Khi đánh dấu một phiên bản phát hành, nhóm thường muốn biết tag đó có thực sự do người phát hành được ủy quyền tạo ra hay không và tag có trỏ đúng commit đã được duyệt hay không. Git hỗ trợ **signed tag**: tag có chữ ký mật mã gắn với đối tượng được đánh dấu và thông tin của tag.

Bạn tạo signed tag bằng `git tag -s` và kiểm tra chữ ký bằng `git tag -v`. Việc kiểm tra giúp xác nhận chữ ký hợp lệ với khóa công khai đang có trong môi trường của bạn. Để kết luận tag đáng tin cậy, bạn còn phải xác minh danh tính người ký và việc người đó có quyền phát hành phiên bản hay không.

## 1. Phân biệt lightweight, annotated và signed tag

Git có hai dạng tag cơ bản:

- **Lightweight tag** là một tham chiếu đơn giản trỏ trực tiếp đến một đối tượng Git, thường là commit. Nó không tạo tag object riêng, không lưu thông điệp tagger như annotated tag và không có chỗ để gắn chữ ký tag.
- **Annotated tag** tạo một tag object riêng, lưu tên tag, người tạo tag, thời điểm, thông điệp và đối tượng đích. Nó phù hợp để đánh dấu phiên bản phát hành.

Signed tag là một annotated tag có thêm chữ ký mật mã. Các lệnh tạo thường dùng:

```bash
# Lightweight tag
git tag v2.4.0

# Annotated tag, không ký
git tag -a v2.4.0 -m "Release v2.4.0"

# Annotated tag có chữ ký
git tag -s v2.4.0 -m "Release v2.4.0"
```

Trong thực tế, không tạo cả ba tag cùng tên trong một repository. Ví dụ chỉ nhằm so sánh cú pháp. Với phiên bản phát hành cần xác thực người ký, hãy dùng signed tag. `-s` tạo annotated tag và ký tag object; `-a` chỉ tạo annotated tag, không ký.

Chữ ký gắn với tag object, bao gồm đối tượng đích và metadata của tag. Vì commit có mã hash riêng và tag chứa mã đối tượng đích, chữ ký tag cũng ràng buộc đến commit được đánh dấu. Chữ ký tag khác chữ ký commit: `git tag -v` kiểm tra tag, còn `git verify-commit` kiểm tra chữ ký của commit.

## 2. Chuẩn bị khóa ký OpenPGP

Git thường dùng GPG/OpenPGP để ký tag. Máy tạo tag cần có chương trình GPG và khóa riêng tương ứng. Khóa riêng phải được giữ an toàn; người khác chỉ cần khóa công khai để kiểm tra chữ ký.

Liệt kê các khóa bí mật đang có:

```bash
gpg --list-secret-keys --keyid-format=long
```

Kết quả có thể chứa một dòng `sec` với mã khóa. Chọn khóa phát hành đã được tổ chức phê duyệt, rồi cấu hình Git sử dụng khóa đó:

```bash
git config --global user.signingkey <KEY_ID>
```

Nếu máy có nhiều khóa, hãy chọn đúng khóa thay vì dựa vào khóa mặc định. Có thể kiểm tra cấu hình:

```bash
git config --show-origin --get user.signingkey
```

Git có thể gọi GPG để ký; tùy môi trường, bạn sẽ cần mở khóa bằng passphrase hoặc xác nhận qua pinentry. Nếu lệnh ký báo không tìm thấy GPG, hãy kiểm tra GPG đã được cài đặt và có trong `PATH` hay chưa.

Để người khác xác minh, xuất khóa công khai:

```bash
gpg --armor --export <KEY_ID> > release-public-key.asc
```

Chỉ chia sẻ khóa công khai. Không gửi tệp khóa riêng, không commit khóa riêng vào repository và không lưu passphrase trong script hoặc file cấu hình dự án.

## 3. Tạo một signed tag

Trước khi tạo tag, xác định commit sẽ phát hành và kiểm tra working tree:

```bash
git status
git log -1 --oneline
```

Nếu cần gắn tag vào commit hiện tại:

```bash
git tag -s v2.4.0 -m "Release v2.4.0"
```

Nếu muốn chỉ rõ commit đích:

```bash
git tag -s v2.4.0 <COMMIT_ID> -m "Release v2.4.0"
```

Git tạo tag object và ký bằng khóa đã cấu hình. Nếu cần dùng một khóa cụ thể cho riêng lần tạo tag này, có thể chỉ định bằng `-u`:

```bash
git tag -s -u <KEY_ID> v2.4.0 -m "Release v2.4.0"
```

Tag cần có tên duy nhất trong repository. Nếu `v2.4.0` đã tồn tại, Git thường từ chối tạo lại. Đừng dùng `-f` chỉ để vượt qua lỗi này; trước tiên hãy kiểm tra tag hiện có và quy trình sửa tag của nhóm. Tag phát hành đã công bố thường nên được giữ bất biến.

Kiểm tra tag vừa tạo:

```bash
git show --no-patch --decorate v2.4.0
git cat-file -p refs/tags/v2.4.0
```

Với annotated tag, `git cat-file -p` hiển thị tag object, bao gồm đối tượng đích, tagger, thông điệp và phần chữ ký nếu tag được ký. Lệnh `git show` giúp xem nội dung commit mà tag trỏ đến.

## 4. Kiểm tra chữ ký bằng git tag -v

Lệnh xác minh:

```bash
git tag -v v2.4.0
```

Git đọc tag object, trích chữ ký và gọi công cụ xác minh tương ứng. Với OpenPGP, công cụ thường là GPG. Khi chữ ký hợp lệ và khóa công khai đã có, đầu ra thường cho biết chữ ký tốt cùng danh tính hoặc mã khóa của người ký.

Bạn cũng có thể dùng lệnh chuyên biệt:

```bash
git verify-tag v2.4.0
```

`git verify-tag` kiểm tra chữ ký của tag; `git tag -v` là cách thường thấy khi kiểm tra một tag cụ thể. Cả hai đều không thay thế việc xác nhận khóa đó thuộc về đúng người phát hành.

### Các kết quả thường gặp

| Kết quả | Ý nghĩa | Việc cần làm |
|---|---|---|
| Chữ ký hợp lệ (Good signature) | Chữ ký khớp với tag object và khóa công khai được dùng để xác minh | Xác minh fingerprint và quyền phát hành của chủ khóa |
| Không tìm thấy khóa công khai | Máy chưa có khóa cần thiết để kiểm tra | Nhận khóa công khai từ nguồn tin cậy, nhập khóa và kiểm tra fingerprint |
| Chữ ký không hợp lệ (BAD signature) | Dữ liệu tag hoặc chữ ký không khớp | Không tin cậy tag; kiểm tra nguồn lấy tag và tính toàn vẹn dữ liệu |
| Tag không có chữ ký hoặc không phải annotated tag có chữ ký | Không có chữ ký tag để xác minh | Xác nhận tag có đúng loại theo chính sách phát hành hay không |
| Công cụ ký không chạy được | Git không gọi được GPG hoặc chương trình xác minh được cấu hình | Kiểm tra chương trình, đường dẫn và cấu hình Git |

Một thông báo `Good signature` chứng minh chữ ký hợp lệ theo khóa đang dùng, nhưng không tự chứng minh người ký là nhân viên được phép phát hành. Một khóa công khai có thể được nhập vào keyring mà chưa được xác minh danh tính; vì vậy, không bỏ qua bước kiểm tra fingerprint.

## 5. Nhận và xác minh khóa công khai

Khi nhận khóa công khai của người phát hành, hãy xác minh fingerprint qua một kênh độc lập, chẳng hạn danh bạ khóa nội bộ hoặc xác nhận trực tiếp từ người quản lý khóa. Không lấy fingerprint từ chính tệp khóa rồi coi đó là bằng chứng độc lập.

Nhập khóa công khai sau khi xác nhận nguồn:

```bash
gpg --import release-public-key.asc
```

Xem fingerprint:

```bash
gpg --fingerprint <KEY_ID>
```

Đối chiếu fingerprint đầy đủ với thông tin do tổ chức công bố. Sau đó kiểm tra tag:

```bash
git tag -v v2.4.0
```

Nếu GPG hiển thị chữ ký hợp lệ nhưng trạng thái tin cậy của khóa chưa được xác lập, hãy làm theo chính sách xác minh danh tính của nhóm. Cơ chế trust của GPG và việc tổ chức cấp quyền phát hành là hai vấn đề liên quan nhưng không đồng nhất.

## 6. Dùng SSH key để ký tag

Các phiên bản Git hiện đại còn hỗ trợ ký bằng SSH. Đây là lựa chọn hữu ích khi tổ chức đã quản lý SSH key cho nhà phát triển. Ví dụ cấu hình:

```bash
git config --global gpg.format ssh
git config --global user.signingkey ~/.ssh/id_ed25519
```

Tạo tag như bình thường:

```bash
git tag -s v2.4.0 -m "Release v2.4.0"
```

Để xác minh SSH signature, Git cần danh sách người ký được phép thông qua `gpg.ssh.allowedSignersFile`. Tệp này sử dụng định dạng allowed signers của OpenSSH, trong đó mỗi dòng liên kết principal (thường là email) với public key được phép ký. Ví dụ dạng một dòng:

```text
release@example.com namespaces="git" ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAA... release-key
```

Cấu hình đường dẫn tới tệp đó:

```bash
git config --global gpg.ssh.allowedSignersFile ~/.config/git/allowed_signers
```

Sau khi cấu hình danh sách khóa được phép, chạy:

```bash
git tag -v v2.4.0
```

Không chép nguyên chuỗi khóa minh họa vào cấu hình thật. Hãy dùng public key SSH đã được quản trị viên xác nhận và principal đúng theo danh tính tagger. Nếu nhóm dùng OpenPGP, không cần cấu hình SSH signing; nếu dùng SSH, phải chuẩn bị allowed signers file trên máy xác minh.

## 7. Phát hành và xác minh tag qua remote

Tag được tạo trong local repository. Sau khi xác minh tag tại máy tạo, đẩy tag lên remote một cách tường minh:

```bash
git push origin v2.4.0
```

Kiểm tra remote có công bố tag:

```bash
git ls-remote --tags origin v2.4.0
```

Lệnh `ls-remote` chỉ hiển thị tham chiếu trên máy chủ; nó không xác minh chữ ký tag. Ở một clone khác, fetch tag rồi xác minh độc lập:

```bash
git fetch origin tag v2.4.0
git tag -v v2.4.0
git show --no-patch --decorate v2.4.0
```

Clone xác minh cần có khóa công khai của người phát hành và cấu hình công cụ xác minh tương ứng. Nếu tag dùng SSH signature, máy xác minh cần allowed signers file phù hợp. Việc push thành công cũng không có nghĩa máy chủ đã tự xác minh chữ ký; điều đó phụ thuộc chính sách và hook của máy chủ Git.

## 8. Giới hạn và nguyên tắc bảo vệ tag phát hành

- **Chữ ký không thay thế chính sách phát hành.** Hãy kiểm tra người ký có được phép phát hành phiên bản đó không.
- **Chữ ký không làm tag bất biến.** Người có quyền ghi trên remote vẫn có thể xóa hoặc thay ref tag nếu máy chủ cho phép; tag signature chỉ giúp phát hiện nội dung tag object khác với chữ ký.
- **Không sửa tag phát hành đã công bố một cách âm thầm.** Nếu phát hiện sai sót, hãy phát hành tag phiên bản mới hoặc công bố quy trình thu hồi/thay thế rõ ràng.
- **Không chia sẻ khóa riêng.** Chỉ phân phối public key và fingerprint đã được xác minh.
- **Xác minh sau khi tải.** Tag nhận từ remote không nên được xem là đáng tin chỉ vì nó nằm trên máy chủ quen thuộc.
- **Phân biệt tag và commit signature.** Nếu chính sách yêu cầu cả tag lẫn commit được ký, hãy kiểm tra riêng từng loại chữ ký.

## 9. Quy trình phát hành có signed tag

Một quy trình cơ bản có thể gồm các bước sau:

1. Xác nhận commit đã qua review và kiểm thử.
2. Chọn khóa ký đã được tổ chức phê duyệt; kiểm tra cấu hình `user.signingkey`.
3. Tạo annotated signed tag bằng `git tag -s` và ghi thông điệp phiên bản.
4. Chạy `git tag -v` tại máy tạo để kiểm tra chữ ký và xác nhận commit đích.
5. Đẩy tag cụ thể bằng `git push origin <tag>`.
6. Trong clone độc lập, fetch tag và chạy `git tag -v`; xác minh fingerprint và quyền phát hành.
7. Lưu lại thông tin phiên bản, commit đích và người ký theo quy trình phát hành của nhóm.

Ví dụ lệnh rút gọn:

```bash
git status
git log -1 --oneline
git tag -s v2.4.0 -m "Release v2.4.0"
git tag -v v2.4.0
git push origin v2.4.0
```

## 10. Bài tập thực hành

Trong một repository thử nghiệm, chuẩn bị khóa OpenPGP dành cho môi trường học tập hoặc dùng khóa thử nghiệm được cấp sẵn. Không dùng khóa riêng của tổ chức trong bài tập cá nhân.

1. Dùng `gpg --list-secret-keys --keyid-format=long` để xác định khóa ký.
2. Cấu hình `user.signingkey` trỏ đến khóa đó.
3. Tạo một annotated signed tag `v0.1.0` bằng `git tag -s`.
4. Chạy `git tag -v v0.1.0` và đọc kết quả xác minh.
5. Xuất public key, nhập vào keyring của một môi trường thử nghiệm khác và xác minh fingerprint qua kênh độc lập.
6. Fetch tag trong clone thứ hai, chạy `git tag -v` và so sánh kết quả.
7. Thử xác minh một lightweight tag để quan sát vì sao nó không có chữ ký tag object.

Bạn hoàn thành bài tập khi tạo được signed tag, kiểm tra được chữ ký bằng `git tag -v`, phân biệt xác thực mật mã với xác minh danh tính và giải thích được vì sao cần bảo vệ khóa riêng.
