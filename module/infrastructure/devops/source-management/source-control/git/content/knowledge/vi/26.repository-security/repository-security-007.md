# Ký commit hoặc tag bằng GPG và SSH

Chữ ký số giúp người nhận kiểm tra một commit hoặc tag có được ký bằng khóa tương ứng hay không và nội dung được ký có bị thay đổi sau đó không. Git hỗ trợ ký bằng OpenPGP thông qua GPG và bằng khóa SSH. Hai cách dùng cơ chế khóa khác nhau, nhưng đều có thể gắn chữ ký vào commit hoặc annotated tag để người khác xác minh.

Trong chương **Bảo mật kho mã** của module **SOURCE_CONTROL_GIT**, bài học này hướng dẫn cách thiết lập, tạo và xác minh chữ ký commit/tag bằng GPG và SSH. Bạn sẽ phân biệt chữ ký của đối tượng Git với chữ ký của một lần push, hiểu cách phân phối khóa công khai, và biết vì sao một chữ ký hợp lệ về mật mã vẫn cần được đối chiếu với danh tính đáng tin cậy.

Sau bài học, bạn có thể:

- Giải thích chữ ký được lưu trong commit và annotated tag.
- Phân biệt ký bằng GPG/OpenPGP và SSH.
- Tạo hoặc chọn khóa ký, cấu hình Git và ký commit/tag.
- Xác minh chữ ký bằng các lệnh Git.
- Thiết lập allowed signers cho SSH và hiểu vai trò của trust trong GPG.
- Tự động ký commit hoặc tag theo chính sách cá nhân/dự án.
- Phân biệt signed commit, signed tag và signed push.
- Xử lý trường hợp chữ ký không hợp lệ, thiếu khóa hoặc metadata danh tính không khớp.

## 1. Chữ ký số trong Git giải quyết điều gì?

Một commit Git chứa snapshot, parent commit, thông tin tác giả, người tạo commit, thời gian và thông điệp. Khi ký commit, Git tạo chữ ký mật mã gắn vào nội dung commit. Một annotated tag cũng có thể chứa chữ ký gắn với tag object.

Chữ ký giúp người xác minh kiểm tra:

- Nội dung commit hoặc tag có khớp với chữ ký hay không.
- Chữ ký có được tạo bởi khóa tương ứng hay không.
- Khóa đó có được liên kết với danh tính mà tổ chức tin cậy hay không.

Chữ ký không mã hóa source code và không che giấu nội dung commit. Bất kỳ ai có quyền đọc repository vẫn có thể đọc file và lịch sử. Chữ ký cung cấp bằng chứng xác thực và toàn vẹn, không thay thế quyền truy cập repository, review, kiểm thử hoặc chính sách branch.

Git có thể ký bằng:

- **OpenPGP/GPG**: dùng cặp khóa OpenPGP và cơ sở dữ liệu khóa/trust của GPG.
- **SSH**: dùng khóa SSH để tạo chữ ký; khi xác minh, Git cần danh sách khóa công khai được phép và principal tương ứng.

Chọn một phương thức phù hợp với hạ tầng hiện có của nhóm. Các thành viên vẫn có thể dùng phương thức khác nhau nếu hệ thống xác minh được cấu hình để chấp nhận chúng.

## 2. Chữ ký commit và chữ ký tag khác nhau thế nào?

### Signed commit

Chữ ký commit được lưu trong chính commit object. Khi xác minh, Git kiểm tra chữ ký trên commit đó.

Tạo commit có chữ ký:

~~~bash
git commit -S -m "feat: add signed release metadata"
~~~

Tùy chọn -S yêu cầu Git ký commit bằng định dạng và khóa đã cấu hình. Có thể chỉ định khóa cụ thể nếu môi trường có nhiều khóa:

~~~bash
git commit -S<key-id> -m "fix: validate signed request"
~~~

Giữa -S và key ID không có khoảng trắng trong dạng viết gắn liền; có thể dùng dạng tùy chọn tương ứng theo phiên bản Git. Nếu đã đặt user.signingKey, thường chỉ cần -S.

### Signed tag

Một tag muốn có chữ ký phải là annotated tag vì chữ ký được gắn vào tag object. Lightweight tag chỉ là một ref trỏ trực tiếp đến object và không có tag object để lưu chữ ký.

Tạo signed annotated tag:

~~~bash
git tag -s v1.2.0 -m "Release v1.2.0"
~~~

Gắn tag vào một commit cụ thể:

~~~bash
git tag -s v1.2.0 <commit> -m "Release v1.2.0"
~~~

Lệnh này tạo tag object có metadata tagger, thông điệp và chữ ký. Tag sẽ trỏ đến commit được chỉ định, dù HEAD hiện tại đang ở commit khác.

### Chữ ký không tự động được thêm vào mọi thao tác

Tùy chọn -S ký đối tượng được tạo trong lệnh đó. Nếu không bật cấu hình tự ký, commit hoặc tag mới có thể không được ký. Một tag ký cũng không làm các commit trước đó trở thành signed commit; ngược lại, ký commit không tự tạo signed tag.

## 3. Cấu hình chung của Git cho việc ký

Git dùng một số key cấu hình để chọn định dạng, chương trình và khóa ký.

| Key | Vai trò |
| --- | --- |
| gpg.format | Chọn định dạng chữ ký: openpgp, ssh hoặc x509 |
| user.signingKey | Khóa hoặc định danh khóa dùng để ký |
| gpg.program | Chương trình ký/xác minh OpenPGP hoặc chương trình tương ứng theo cấu hình |
| gpg.ssh.program | Chương trình SSH dùng để tạo/xác minh chữ ký SSH |
| gpg.ssh.allowedSignersFile | File ánh xạ principal với khóa công khai được phép xác minh chữ ký SSH |
| gpg.ssh.revocationFile | File chứa thông tin khóa SSH bị thu hồi để kiểm tra khi xác minh |
| commit.gpgsign | Tự động ký commit khi tạo commit |
| tag.gpgSign | Tự động ký annotated tag khi tạo tag |

Kiểm tra các cấu hình liên quan:

~~~bash
git config --show-origin --show-scope --get-regexp '^(gpg|user\.signingkey|commit\.gpgsign|tag\.gpgsign)'
~~~

Đặt cấu hình ở global nếu muốn dùng cho mọi repository của người dùng; đặt local nếu chỉ muốn áp dụng cho dự án hiện tại. Cấu hình local có thể ghi đè global.

Không lưu private key hoặc passphrase vào Git config. Git config chỉ nên chứa đường dẫn, fingerprint hoặc định danh khóa; private key cần được bảo vệ bằng công cụ khóa và cơ chế xác thực phù hợp.

## 4. Ký bằng GPG/OpenPGP

### Bước 1: kiểm tra GPG

Xác nhận GPG có trong PATH:

~~~bash
gpg --version
~~~

Nếu Git không tìm thấy chương trình GPG, cài GPG theo hệ điều hành hoặc chỉ định đường dẫn executable bằng gpg.program:

~~~bash
git config --global gpg.program gpg
~~~

Giá trị trên giả định chương trình có tên gpg trong PATH. Nếu dùng đường dẫn cụ thể, hãy đặt đúng đường dẫn của máy.

### Bước 2: tạo hoặc chọn khóa bí mật

Nếu chưa có khóa OpenPGP, tạo khóa:

~~~bash
gpg --full-generate-key
~~~

Làm theo hướng dẫn để chọn loại khóa, độ dài hoặc thuật toán, thời hạn và danh tính. Dùng email phù hợp với danh tính commit hoặc chính sách của tổ chức. Đặt passphrase mạnh để bảo vệ private key.

Liệt kê khóa bí mật:

~~~bash
gpg --list-secret-keys --keyid-format=long
~~~

Xem fingerprint:

~~~bash
gpg --fingerprint <key-id>
~~~

Ưu tiên dùng fingerprint đầy đủ để xác định khóa, tránh nhầm giữa các key ID ngắn có thể trùng. Nếu đã có khóa được tổ chức cấp, dùng khóa đó theo hướng dẫn thay vì tự tạo thêm một khóa không được chấp nhận.

### Bước 3: cấu hình Git dùng GPG

Chọn định dạng OpenPGP và khóa ký:

~~~bash
git config --global gpg.format openpgp
git config --global user.signingKey <fingerprint>
~~~

Nếu muốn Git tự ký mọi commit và annotated tag mới:

~~~bash
git config --global commit.gpgsign true
git config --global tag.gpgSign true
~~~

Nếu chỉ muốn ký một số commit/tag, không bật hai thiết lập tự động; dùng -S ở đúng lệnh cần ký.

### Bước 4: ký commit

~~~bash
git commit -S -m "feat: add account recovery"
~~~

Nếu commit.gpgsign đã bật, lệnh git commit thông thường cũng sẽ yêu cầu ký. GPG có thể hỏi passphrase hoặc hiển thị hộp thoại xác thực tùy cấu hình agent và môi trường.

### Bước 5: ký annotated tag

~~~bash
git tag -s v2.0.0 -m "Release v2.0.0"
~~~

Nếu tag.gpgSign đã bật, lệnh tạo annotated tag thông thường theo cấu hình có thể tự ký. Để thể hiện rõ ý định trong tài liệu release, nhóm vẫn nên dùng cú pháp -s ở các ví dụ phát hành.

## 5. Phân phối và xác minh khóa GPG

Người nhận cần có khóa công khai tương ứng để xác minh chữ ký. Xuất khóa công khai:

~~~bash
gpg --armor --export <fingerprint> > signing-public-key.asc
~~~

Chia sẻ file khóa công khai qua kênh mà nhóm chấp nhận. Người nhận nhập khóa:

~~~bash
gpg --import signing-public-key.asc
~~~

Sau khi nhập, kiểm tra fingerprint bằng một kênh tin cậy độc lập, chẳng hạn danh bạ khóa nội bộ hoặc xác nhận trực tiếp với chủ khóa. Không chỉ dựa vào tên và email hiển thị trong khóa; các trường đó có thể được tự khai báo.

GPG có cơ chế trust riêng. Một thông báo chữ ký hợp lệ cho biết chữ ký khớp với khóa công khai, nhưng mức độ tin cậy rằng khóa thuộc đúng người vẫn phụ thuộc cách tổ chức xác minh và đánh dấu trust. Hãy phân biệt:

- **Signature validity**: dữ liệu được ký không bị thay đổi và chữ ký khớp khóa.
- **Key identity/trust**: khóa có thực sự thuộc người hoặc tổ chức mà bạn tin cậy hay không.

Không coi việc import một public key bất kỳ là đã xác minh danh tính người ký.

## 6. Xác minh signed commit và signed tag bằng GPG

Xác minh commit hiện tại:

~~~bash
git verify-commit HEAD
~~~

Xác minh một commit cụ thể:

~~~bash
git verify-commit <commit>
~~~

Xem chữ ký khi đọc lịch sử:

~~~bash
git log --show-signature --format=fuller -1
~~~

Xác minh tag:

~~~bash
git verify-tag v2.0.0
~~~

Hoặc xem thông tin tag cùng chữ ký:

~~~bash
git tag -v v2.0.0
~~~

Nếu chữ ký không xác minh được, kiểm tra:

- Public key tương ứng đã được import chưa?
- Fingerprint có khớp nguồn tin cậy không?
- Private key được dùng để ký có đúng khóa đã cấu hình không?
- GPG executable hoặc agent có sẵn trong môi trường không?
- Khóa có hết hạn, bị thu hồi hoặc không còn được chấp nhận không?

Một thông báo cảnh báo trust không nhất thiết có nghĩa chữ ký mật mã sai. Hãy đọc đầy đủ output và kiểm tra trạng thái khóa theo chính sách của tổ chức.

## 7. Ký bằng SSH

Git có thể dùng SSH key để ký commit và annotated tag. Cách này thuận tiện nếu nhóm đã quản lý SSH key cho việc truy cập repository và muốn dùng cùng hạ tầng khóa.

SSH signing khác với việc dùng SSH key để xác thực khi git fetch hoặc git push. Một key dùng để đăng nhập server không tự động được Git coi là khóa ký; cần cấu hình gpg.format và khóa ký.

### Bước 1: tạo hoặc chọn SSH key

Nếu chưa có khóa phù hợp, tạo khóa Ed25519:

~~~bash
ssh-keygen -t ed25519 -C "developer@example.com" -f ~/.ssh/id_ed25519
~~~

Đặt passphrase cho private key. Nếu tổ chức đã cấp khóa ký riêng, dùng khóa đó và tuân thủ chính sách lưu trữ.

Public key có phần mở rộng .pub; private key là file còn lại. Chỉ chia sẻ public key. Không gửi hoặc commit private key vào repository.

### Bước 2: nạp private key vào SSH agent

Trên môi trường Unix-like:

~~~bash
eval "$(ssh-agent -s)"
ssh-add ~/.ssh/id_ed25519
~~~

Trên Windows có OpenSSH Agent, có thể khởi động dịch vụ theo chính sách máy rồi nạp key:

~~~powershell
ssh-add $env:USERPROFILE\.ssh\id_ed25519
~~~

Kiểm tra key đã được nạp:

~~~bash
ssh-add -l
~~~

Nếu Git không tìm được ssh-keygen, cấu hình gpg.ssh.program trỏ đến chương trình phù hợp trong môi trường. Đường dẫn executable có thể khác giữa Windows, macOS và Linux.

### Bước 3: cấu hình Git dùng SSH signing

Chọn SSH làm định dạng:

~~~bash
git config --global gpg.format ssh
git config --global user.signingKey ~/.ssh/id_ed25519.pub
~~~

Ví dụ này dùng đường dẫn public key và giả định private key tương ứng đã được nạp vào SSH agent. Git gọi chương trình SSH signing để tạo chữ ký; private key phải sẵn sàng cho agent hoặc cơ chế khóa mà bạn sử dụng.

Nếu chỉ muốn bật tự ký commit:

~~~bash
git config --global commit.gpgsign true
~~~

Nếu muốn tự ký annotated tag:

~~~bash
git config --global tag.gpgSign true
~~~

### Bước 4: tạo commit hoặc tag có chữ ký SSH

~~~bash
git commit -S -m "fix: validate signed payload"
git tag -s v2.1.0 -m "Release v2.1.0"
~~~

Git dùng SSH signing vì gpg.format đã được đặt thành ssh. Cú pháp -S vẫn được dùng cho cả GPG và SSH; định dạng được chọn bởi cấu hình.

## 8. Thiết lập allowed signers để xác minh chữ ký SSH

Để xác minh SSH signature, Git cần biết public key nào được phép và principal nào gắn với key đó. File allowed signers chứa principal cùng public key.

Ví dụ một dòng:

~~~text
developer@example.com namespaces="git" ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIExamplePublicKeyMaterial
~~~

Thay email, key type và nội dung public key bằng giá trị thật. Chuỗi ví dụ ở trên chỉ minh họa định dạng, không phải khóa có thể sử dụng.

Tạo file allowed signers trong thư mục cấu hình cá nhân, sau đó đặt:

~~~bash
git config --global gpg.ssh.allowedSignersFile ~/.ssh/allowed_signers
~~~

Principal thường được gắn với email danh tính commit mà tổ chức chấp nhận. Tùy chọn namespaces="git" giới hạn key entry này cho namespace chữ ký Git. Nếu không có allowed signers phù hợp, Git có thể không xác minh được SSH signature dù public key đã có trên máy.

File allowed signers là chính sách tin cậy của người xác minh. Nó không phải private key và không cần nằm trong repository. Nhóm có thể phân phối file này qua cấu hình quản trị hoặc một nguồn tin cậy được kiểm soát.

### Kiểm tra SSH signature

~~~bash
git verify-commit HEAD
git verify-tag v2.1.0
git log --show-signature -1
~~~

Nếu xác minh thất bại, kiểm tra:

- gpg.format có đang là ssh không?
- gpg.ssh.allowedSignersFile có trỏ đến file tồn tại và đọc được không?
- Principal trong file có khớp danh tính được kiểm tra không?
- Public key trong file có đúng key đã ký không?
- Entry có namespace phù hợp không?
- Khóa có bị thu hồi theo cấu hình xác minh không?

## 9. Thu hồi khóa SSH và khóa GPG

Khi private key bị lộ, mất kiểm soát hoặc chủ sở hữu rời tổ chức, cần thu hồi quyền tin cậy của key đó.

### Với SSH

Git hỗ trợ file thu hồi SSH thông qua gpg.ssh.revocationFile. File này có thể dùng định dạng Key Revocation List (KRL) của OpenSSH.

Ví dụ tạo KRL từ public key bị thu hồi:

~~~bash
ssh-keygen -k -f ~/.ssh/revoked_keys.krl ~/.ssh/compromised_key.pub
~~~

Cấu hình Git dùng file:

~~~bash
git config --global gpg.ssh.revocationFile ~/.ssh/revoked_keys.krl
~~~

Khi xác minh, Git có thể kiểm tra chữ ký bằng khóa đã bị thu hồi và đánh dấu không hợp lệ theo dữ liệu thu hồi. File revocation phải được cập nhật và phân phối cho các máy xác minh.

### Với GPG

GPG có cơ chế thu hồi chứng chỉ/khóa OpenPGP. Chủ khóa có thể tạo revocation certificate theo quy trình GPG và công bố nó qua kênh phân phối khóa phù hợp. Người xác minh cần cập nhật keyring để nhận trạng thái thu hồi mới.

Thu hồi khóa không tự xóa các commit hoặc tag đã ký. Nó thay đổi trạng thái tin cậy của khóa khi xác minh. Tổ chức cần xác định từ thời điểm nào chữ ký của key không còn được chấp nhận và cách xử lý các bản phát hành đã ký trước đó.

## 10. Tự động ký commit và tag

Nếu chính sách yêu cầu mọi commit mới của người dùng đều được ký:

~~~bash
git config --global commit.gpgsign true
~~~

Nếu muốn annotated tag mới tự động được ký:

~~~bash
git config --global tag.gpgSign true
~~~

Hai thiết lập độc lập. Bạn có thể tự động ký commit nhưng chỉ ký tag phát hành, hoặc yêu cầu cả hai.

Đặt ở local nếu chỉ repository hiện tại yêu cầu:

~~~bash
git config --local commit.gpgsign true
git config --local tag.gpgSign true
~~~

Kiểm tra nguồn cấu hình:

~~~bash
git config --show-origin --show-scope --get commit.gpgsign
git config --show-origin --show-scope --get tag.gpgSign
git config --show-origin --show-scope --get gpg.format
git config --show-origin --show-scope --get user.signingKey
~~~

Nếu một môi trường CI tạo commit hoặc tag, cần cấp khóa ký cho runner qua secret store hoặc cơ chế ký tập trung. Không đưa private key vào source tree, artifact công khai hoặc log pipeline.

## 11. Xác minh chữ ký trước khi review hoặc phát hành

Chữ ký chỉ hữu ích nếu quy trình thực sự kiểm tra nó. Người review có thể kiểm tra commit:

~~~bash
git verify-commit <commit>
~~~

Kiểm tra tag phát hành:

~~~bash
git verify-tag v2.1.0
~~~

Xem lịch sử cùng trạng thái chữ ký:

~~~bash
git log --show-signature --oneline --decorate -10
~~~

Một quy trình release có thể yêu cầu:

1. Commit phát hành được ký bởi khóa thuộc thành viên hoặc bot được phép.
2. Tag là annotated và được ký.
3. Người xác minh có public key hoặc allowed signers tương ứng.
4. Fingerprint hoặc principal được xác nhận qua nguồn tin cậy.
5. CI kiểm tra chữ ký trước khi tạo artifact hoặc triển khai.
6. Metadata artifact lưu commit hash, tag và kết quả xác minh.

Chữ ký hợp lệ không chứng minh code an toàn hoặc đã được review. Nó chỉ giúp xác minh nguồn ký và tính toàn vẹn của đối tượng. Các kiểm tra bảo mật, review, test và phê duyệt phát hành vẫn cần được thực hiện.

## 12. Chữ ký commit/tag khác signed push

Git còn có cơ chế ký một lần push:

~~~bash
git push --signed origin main
~~~

Đây là signed push certificate. Nó ký yêu cầu cập nhật ref gửi đến server, giúp server có thể ghi nhận thông tin về người gửi và các ref được cập nhật nếu server hỗ trợ cơ chế này.

Phân biệt:

| Cơ chế | Đối tượng được ký | Mục đích |
| --- | --- | --- |
| Signed commit | Commit object | Xác minh commit được ký và nội dung không bị thay đổi |
| Signed tag | Annotated tag object | Xác minh mốc phiên bản và metadata tag |
| Signed push | Push certificate cho lần cập nhật ref | Xác minh thông tin của yêu cầu push |

Một lần push có thể chứa signed commit, signed tag hoặc cả hai; điều đó không tự động có nghĩa push certificate cũng được ký. Ngược lại, signed push không tự ký các commit trong lịch sử.

## 13. Điều gì xảy ra khi commit được viết lại?

Chữ ký gắn với nội dung và metadata của commit object. Nếu dùng amend, rebase hoặc thao tác khác tạo commit mới, hash commit thay đổi và chữ ký cũ không còn là chữ ký của commit mới.

Ví dụ:

~~~bash
git commit --amend
~~~

Commit sau amend là object mới. Nếu cần ký lại:

~~~bash
git commit --amend -S
~~~

Rebase cũng tạo lại commit trên nền mới; nếu chính sách yêu cầu signed commit, hãy cấu hình commit.gpgsign hoặc ký lại các commit được tạo. Khi branch đã được chia sẻ, viết lại lịch sử cần phối hợp và có thể cần push với cơ chế cập nhật an toàn theo quy ước nhóm.

Tag đã ký cũng nên được xem là mốc phát hành cố định. Nếu tag bị di chuyển sang commit khác, tag object và chữ ký phải được tạo lại; không tự ý ghi đè tag đã công bố vì người dùng có thể đã tải và xác minh phiên bản cũ.

## 14. Lỗi thường gặp khi ký và xác minh

### Git không tìm thấy GPG

Kiểm tra:

~~~bash
gpg --version
git config --show-origin --get gpg.program
~~~

Đảm bảo GPG có trong PATH hoặc gpg.program trỏ đúng executable. Nếu Git chạy trong IDE hoặc CI, kiểm tra PATH của chính tiến trình đó.

### Không tìm thấy khóa ký

Với GPG:

~~~bash
gpg --list-secret-keys --keyid-format=long
git config --show-origin --get user.signingKey
~~~

Với SSH:

~~~bash
ssh-add -l
git config --show-origin --get user.signingKey
~~~

Kiểm tra khóa private tương ứng có sẵn trong GPG agent hoặc SSH agent và key được cấu hình đúng.

### SSH signature không xác minh được

Kiểm tra file allowed signers:

~~~bash
git config --show-origin --get gpg.ssh.allowedSignersFile
~~~

Đảm bảo file tồn tại, đúng định dạng, chứa principal và public key tương ứng. Việc chỉ thêm public key vào tài khoản truy cập Git hosting không tự động làm key đó trở thành allowed signer trong Git.

### Commit hiển thị chữ ký không hợp lệ sau rebase

Rebase tạo commit mới với hash và chữ ký mới hoặc không có chữ ký tùy cấu hình. Hãy xác minh commit mới; đừng dùng kết quả xác minh của commit cũ để kết luận commit mới hợp lệ.

### Máy khác báo thiếu public key

Người nhận cần import public key GPG hoặc có entry SSH trong allowedSignersFile. Chia sẻ public key và fingerprint qua nguồn tin cậy; không chia sẻ private key.

## 15. Quy trình mẫu cho một release có ký

Giả sử nhóm chuẩn bị phát hành v3.0.0 bằng GPG:

### Bước 1: xác nhận cấu hình và khóa

~~~bash
git config --show-origin --get gpg.format
git config --show-origin --get user.signingKey
gpg --list-secret-keys --keyid-format=long
~~~

Đảm bảo đúng khóa và fingerprint được tổ chức chấp nhận.

### Bước 2: tạo commit phát hành có chữ ký

~~~bash
git commit -S -m "chore: prepare v3.0.0"
git verify-commit HEAD
~~~

### Bước 3: tạo signed annotated tag

~~~bash
git tag -s v3.0.0 -m "Release v3.0.0"
git verify-tag v3.0.0
~~~

### Bước 4: push branch và tag

~~~bash
git push origin main
git push origin v3.0.0
~~~

### Bước 5: xác minh sau khi chia sẻ

~~~bash
git fetch origin --tags
git verify-commit origin/main
git verify-tag v3.0.0
~~~

Trong quy trình thực tế, xác minh commit phát hành bằng hash cụ thể hoặc ref release đã được xác nhận; origin/main có thể đã tiến lên sau lần push. CI nên kiểm tra đúng commit và tag mà artifact được tạo từ đó.

## 16. Những nhầm lẫn thường gặp

### Signed commit có mã hóa nội dung không?

Không. Chữ ký bảo vệ tính toàn vẹn và hỗ trợ xác thực nguồn ký. Nội dung commit vẫn có thể đọc được như bình thường.

### Chỉ cần thấy Good signature là chắc chắn đúng người?

Chưa đủ. Cần xác minh fingerprint GPG hoặc principal và SSH public key qua nguồn tin cậy. Chữ ký mật mã hợp lệ và danh tính đáng tin cậy là hai bước khác nhau.

### Lightweight tag có thể ký không?

Không theo cơ chế signed tag của Git. Hãy tạo annotated tag bằng -a hoặc signed annotated tag bằng -s.

### SSH key dùng để clone qua SSH có tự động ký commit không?

Không. Cần chọn gpg.format ssh, cấu hình user.signingKey và đảm bảo private key sẵn sàng cho SSH signing.

### Push commit đã ký có tự ký lần push không?

Không. Signed commit và signed push là hai cơ chế khác nhau. Muốn ký push certificate, dùng --signed nếu remote hỗ trợ.

### Rebase có giữ chữ ký cũ không?

Commit được tạo lại có hash mới và cần chữ ký mới nếu chính sách yêu cầu. Chữ ký cũ vẫn thuộc commit cũ.

## 17. Tự kiểm tra

Một nhóm yêu cầu commit trên main và tag phát hành phải được ký. Một thành viên dùng GPG, thành viên khác dùng SSH. CI cần xác minh cả hai loại chữ ký trước khi tạo artifact.

Hãy trả lời:

1. Cấu hình nào chọn OpenPGP hay SSH?
2. Lệnh nào tạo signed commit và signed annotated tag?
3. Vì sao lightweight tag không thể mang chữ ký tag?
4. Người xác minh cần làm gì để tin cậy public key GPG?
5. SSH signing cần file nào để ánh xạ principal với public key?
6. Vì sao rebase có thể làm chữ ký commit cũ không còn áp dụng cho commit mới?
7. Signed push có thay thế signed commit không?

**Gợi ý:** Dùng gpg.format để chọn openpgp hoặc ssh. Dùng git commit -S và git tag -s để ký. Signed tag cần annotated tag object. Với GPG, import public key rồi đối chiếu fingerprint qua kênh tin cậy. Với SSH, cấu hình gpg.ssh.allowedSignersFile. Rebase tạo commit object mới nên chữ ký cũ không còn ký object mới. Signed push ký yêu cầu cập nhật ref, không ký nội dung commit.

## Kết luận

Git hỗ trợ ký commit và annotated tag bằng OpenPGP/GPG hoặc SSH. Hãy cấu hình đúng định dạng và khóa, bảo vệ private key, ký đối tượng cần thiết rồi xác minh bằng verify-commit hoặc verify-tag. Người nhận cần kiểm tra fingerprint GPG hoặc principal/public key SSH qua nguồn tin cậy; một chữ ký hợp lệ về mật mã chưa tự chứng minh danh tính. Chữ ký commit, chữ ký tag và signed push bảo vệ các đối tượng khác nhau. Khi commit hoặc tag được viết lại, hãy tạo và xác minh chữ ký mới trước khi công bố lại mốc.
