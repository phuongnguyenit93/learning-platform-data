# Phân biệt danh tính trong commit với xác thực khi truy cập remote

Khi dùng Git, bạn có thể thấy tên và email xuất hiện trong lịch sử commit, đồng thời Git cũng có thể yêu cầu đăng nhập khi push hoặc fetch từ máy chủ. Hai việc này có liên quan đến danh tính nhưng phục vụ những mục đích khác nhau. Tên và email trong commit mô tả ai được ghi nhận là người tạo thay đổi; xác thực remote giúp máy chủ nhận diện client, sau đó phân quyền quyết định client có được truy cập repository hay không.

Nếu nhầm lẫn hai khái niệm, bạn có thể cấu hình đúng email nhưng vẫn không push được, hoặc đăng nhập thành công nhưng commit lại hiển thị sai tên tác giả. Bài học thuộc chương **Bảo mật kho mã** của module SOURCE_CONTROL_GIT. Module hướng dẫn working tree, staging area, commit, lịch sử, branch, merge, rebase, remote và tag; hiểu đúng danh tính và xác thực giúp lịch sử có thông tin rõ ràng và thao tác với remote được bảo vệ.

## 1. Hai câu hỏi khác nhau

Khi làm việc với Git, hãy tách hai câu hỏi:

- **Commit được ghi nhận bởi ai?** Git lưu author và committer name/email trong metadata của commit.
- **Client được xác thực bằng cách nào và được cấp quyền gì?** Máy chủ nhận diện người dùng hoặc máy khách qua HTTPS token/OAuth, SSH key hay cơ chế của nhà cung cấp, rồi kiểm tra quyền đọc/ghi tương ứng.

| Khái niệm | Lưu hoặc kiểm tra ở đâu? | Mục đích |
| --- | --- | --- |
| Author name/email | Metadata của commit | Ghi nhận người viết thay đổi ban đầu |
| Committer name/email | Metadata của commit | Ghi nhận người tạo commit hiện tại |
| Commit signature | Chữ ký gắn với commit object | Kiểm tra commit có được ký bằng khóa tương ứng và nội dung có bị thay đổi không |
| HTTPS credential | Credential helper, token/OAuth hoặc cơ chế đăng nhập | Xác thực khi truy cập remote qua HTTPS |
| SSH key | Private key ở máy client và public key đăng ký trên dịch vụ | Xác thực client khi truy cập remote qua SSH |
| Server identity | TLS certificate hoặc SSH host key | Giúp client xác minh đang kết nối đúng máy chủ |

Cấu hình author/email không cấp quyền push. Ngược lại, việc xác thực remote thành công không tự thay đổi author/email của commit.

## 2. Author và committer trong commit

Một commit Git lưu hai nhóm thông tin danh tính:

- **Author**: người được ghi nhận là người viết thay đổi ban đầu.
- **Committer**: người tạo commit object hiện tại.

Trong tình huống thông thường, cùng một người là author và committer. Nhưng khi cherry-pick, rebase, apply patch hoặc commit thay mặt người khác, hai danh tính có thể khác nhau.

Xem thông tin commit:

~~~bash
git log -1 --format=fuller
~~~

Kết quả có thể tương tự:

~~~text
commit 8ac41d2...
Author:     Nguyen An <an@example.com>
AuthorDate: Tue Nov 17 09:30:00 2026 +0700
Commit:     Tran Binh <binh@example.com>
CommitDate: Tue Nov 17 10:15:00 2026 +0700

    Fix invoice calculation
~~~

Author cho biết người viết bản sửa; Commit cho biết người tạo commit hiện tại. Hai mốc thời gian cũng có thể khác nhau.

### Cấu hình danh tính mặc định

Đặt tên và email cho mọi repository của người dùng:

~~~bash
git config --global user.name "Nguyen An"
git config --global user.email "an@example.com"
~~~

Đặt riêng cho repository hiện tại:

~~~bash
git config --local user.name "Nguyen An"
git config --local user.email "an@company.example"
~~~

Cấu hình local có ưu tiên cao hơn global trong repository đó. Điều này hữu ích khi bạn dùng một máy cho nhiều dự án hoặc cần email công việc riêng.

Kiểm tra giá trị đang được sử dụng:

~~~bash
git config --get user.name
git config --get user.email
git config --show-origin --get user.name
git config --show-origin --get user.email
~~~

Lệnh có --show-origin cho biết giá trị đến từ file cấu hình nào. Có thể xem danh sách cấu hình cùng nguồn:

~~~bash
git config --list --show-origin
~~~

Danh sách này có thể chứa URL hoặc thông tin cấu hình nhạy cảm; hãy xem kỹ và che dữ liệu riêng tư trước khi chia sẻ output.

### Xác nhận danh tính hiệu lực trước khi commit

Git có thể hiển thị danh tính sẽ dùng cho author và committer:

~~~bash
git var GIT_AUTHOR_IDENT
git var GIT_COMMITTER_IDENT
~~~

Đây là cách kiểm tra hữu ích trước khi tạo commit trong repository có nhiều cấu hình hoặc biến môi trường.

### Ngăn Git tự đoán danh tính

Nếu muốn Git yêu cầu cấu hình rõ ràng thay vì tự suy đoán tên/email từ tài khoản hệ điều hành:

~~~bash
git config --global user.useConfigOnly true
~~~

Khi chưa có user.name hoặc user.email phù hợp, thao tác tạo commit sẽ báo lỗi yêu cầu cấu hình. Tùy chọn này giúp tránh commit với danh tính không mong muốn.

## 3. Nguồn cấu hình và ghi đè danh tính

Git đọc cấu hình từ nhiều phạm vi, ví dụ system, global, local và worktree. Cấu hình có phạm vi cụ thể hơn thường ghi đè giá trị chung. Các tham số trên command line và biến môi trường có thể cung cấp giá trị cho một lần chạy.

Một số biến môi trường ảnh hưởng trực tiếp đến metadata:

| Biến | Ảnh hưởng |
| --- | --- |
| GIT_AUTHOR_NAME | Author name |
| GIT_AUTHOR_EMAIL | Author email |
| GIT_AUTHOR_DATE | Author date |
| GIT_COMMITTER_NAME | Committer name |
| GIT_COMMITTER_EMAIL | Committer email |
| GIT_COMMITTER_DATE | Committer date |

Ví dụ, một script có thể đặt danh tính riêng cho một commit trong shell POSIX:

~~~bash
GIT_AUTHOR_NAME="Release Bot" GIT_AUTHOR_EMAIL="release-bot@example.com" GIT_COMMITTER_NAME="Release Bot" GIT_COMMITTER_EMAIL="release-bot@example.com" git commit -m "Prepare release metadata"
~~~

Trong PowerShell, đặt biến môi trường trước lệnh rồi xóa sau khi hoàn tất:

~~~powershell
$env:GIT_AUTHOR_NAME = "Release Bot"
$env:GIT_AUTHOR_EMAIL = "release-bot@example.com"
$env:GIT_COMMITTER_NAME = "Release Bot"
$env:GIT_COMMITTER_EMAIL = "release-bot@example.com"
git commit -m "Prepare release metadata"
Remove-Item Env:GIT_AUTHOR_NAME
Remove-Item Env:GIT_AUTHOR_EMAIL
Remove-Item Env:GIT_COMMITTER_NAME
Remove-Item Env:GIT_COMMITTER_EMAIL
~~~

Nếu một commit có tên/email khác dự kiến, hãy kiểm tra cả config lẫn môi trường của terminal, IDE, script hoặc CI. Không chỉ nhìn file global config rồi kết luận đó là nguồn duy nhất.

## 4. Author, committer và chữ ký commit không giống nhau

Metadata author/committer là các chuỗi văn bản được ghi trong commit. Git không tự xác minh rằng người khai báo tên hoặc email thực sự sở hữu danh tính đó.

Chữ ký commit là một cơ chế bổ sung. Người tạo commit dùng khóa ký để ký commit object; người khác có thể kiểm tra chữ ký bằng khóa công khai hoặc danh sách khóa tin cậy.

Chữ ký giúp xác minh commit được ký bằng khóa tương ứng và nội dung commit được ký không bị thay đổi sau khi ký. Khóa ký có thể được liên kết với một người hoặc tài khoản theo chính sách của tổ chức.

Chữ ký không thay thế xác thực remote. Bạn vẫn cần quyền truy cập remote để push, và một commit có chữ ký hợp lệ không tự cấp quyền ghi vào repository.

### Ký commit bằng GPG

Sau khi cài và cấu hình GPG key, chỉ định khóa ký:

~~~bash
git config --global user.signingkey <GPG-KEY-ID>
git config --global commit.gpgsign true
~~~

Tạo commit có chữ ký:

~~~bash
git commit -S -m "Add invoice validation"
~~~

Nếu đã bật commit.gpgsign, các commit mới sẽ được ký mặc định.

### Ký commit bằng SSH

Các phiên bản Git hỗ trợ SSH signing có thể dùng khóa SSH để ký commit:

~~~bash
git config --global gpg.format ssh
git config --global user.signingkey ~/.ssh/id_ed25519.pub
git config --global commit.gpgsign true
git commit -S -m "Add invoice validation"
~~~

Trong PowerShell, thay đường dẫn khóa bằng đường dẫn public key thực tế:

~~~powershell
git config --global user.signingkey "$env:USERPROFILE/.ssh/id_ed25519.pub"
~~~

Khóa dùng để ký commit có vai trò khác với thao tác dùng private key để xác thực SSH tới remote. Một số dịch vụ cho phép đăng ký cùng một khóa cho nhiều mục đích, nhưng cần tuân theo chính sách bảo mật và quy trình quản lý khóa của tổ chức.

### Kiểm tra chữ ký

Xem commit và trạng thái chữ ký:

~~~bash
git log -1 --show-signature
~~~

Xác minh một commit cụ thể:

~~~bash
git verify-commit <commit>
~~~

Kết quả xác minh phụ thuộc khóa công khai, trust configuration và công cụ ký đã cài. Chỉ thấy metadata Author/Committer không có nghĩa commit đã được ký.

## 5. Xác thực khi truy cập remote

Remote là repository trên máy chủ hoặc một địa chỉ repository khác. Xem các remote đã cấu hình:

~~~bash
git remote -v
~~~

Một remote có thể dùng URL HTTPS hoặc SSH. Giao thức trong URL quyết định cơ chế xác thực thường được sử dụng.

### HTTPS: token, OAuth hoặc credential manager

URL HTTPS thường có dạng:

~~~text
https://git.example.com/team/project.git
~~~

Khi fetch hoặc push, máy chủ có thể yêu cầu xác thực bằng token cá nhân (PAT), OAuth hoặc cơ chế đăng nhập do nhà cung cấp hỗ trợ. Git thường tích hợp credential helper để lưu hoặc lấy credential mà không cần nhập lại mỗi lần.

Kiểm tra credential helper đang cấu hình:

~~~bash
git config --show-origin --get-all credential.helper
~~~

Trên Windows, Git Credential Manager thường được dùng để mở quy trình đăng nhập và lưu credential trong kho bảo mật của hệ điều hành. Cách cài đặt phụ thuộc phiên bản Git và tổ chức.

Với token, hãy:

- Chọn quyền tối thiểu cần thiết, ví dụ chỉ quyền đọc nếu chỉ fetch.
- Đặt thời hạn và xoay vòng theo chính sách của tổ chức.
- Lưu bằng credential manager hoặc secret store được phê duyệt.
- Không ghi token trực tiếp vào remote URL, script, log hoặc lịch sử shell.
- Không gửi token trong ảnh chụp màn hình hoặc output hỗ trợ.

Không nên dùng mật khẩu tài khoản thông thường nếu nhà cung cấp yêu cầu token/OAuth. Chính sách cụ thể tùy nền tảng Git đang sử dụng.

### SSH: public key và private key

URL SSH thường có dạng:

~~~text
git@git.example.com:team/project.git
~~~

SSH dùng một cặp khóa:

- **Private key** ở máy client, phải được giữ bí mật.
- **Public key** được đăng ký trong tài khoản hoặc hệ thống quản lý quyền trên dịch vụ Git.

Khi kết nối, client chứng minh quyền sở hữu private key mà không gửi private key lên server. SSH agent có thể giữ khóa đã mở để giảm việc nhập passphrase nhiều lần.

Liệt kê khóa đang được nạp vào agent:

~~~bash
ssh-add -l
~~~

Thêm một private key vào agent nếu cần:

~~~bash
ssh-add ~/.ssh/id_ed25519
~~~

Trên Windows PowerShell, đường dẫn thường có dạng:

~~~powershell
ssh-add "$env:USERPROFILE/.ssh/id_ed25519"
~~~

Kiểm tra kết nối SSH bằng lệnh phù hợp với hostname và dịch vụ Git của tổ chức. Ví dụ tổng quát:

~~~bash
ssh -T git@git.example.com
~~~

Thông báo thành công thường cho biết tài khoản đã được nhận diện; một số máy chủ không cấp shell tương tác nên việc lệnh không mở shell không đồng nghĩa xác thực thất bại.

### Xác minh máy chủ là một bước khác

Khi dùng HTTPS, TLS certificate giúp client xác minh máy chủ. Khi dùng SSH, host key và file known_hosts giúp client xác minh server endpoint.

Đây là xác minh **server identity**, khác với việc server xác thực **client identity** bằng token hoặc public key. Không bỏ qua cảnh báo host key hoặc tắt kiểm tra TLS chỉ để làm lệnh chạy được; hãy xác minh fingerprint/certificate qua kênh tin cậy.

## 6. Xác thực thành công không đồng nghĩa có quyền ghi

Một người có thể đăng nhập thành công nhưng vẫn không push được. Xác thực trả lời câu hỏi “bạn là ai?”; phân quyền trả lời câu hỏi “bạn được phép làm gì?”.

Ví dụ:

- Credential hợp lệ nhưng tài khoản chỉ có quyền đọc.
- Tài khoản có quyền ghi repository nhưng branch được bảo vệ.
- Token hết hạn hoặc thiếu scope cần thiết.
- SSH key hợp lệ nhưng chưa được cấp quyền vào repository.
- Quy tắc review yêu cầu pull request thay vì push trực tiếp vào branch chính.
- Server từ chối cập nhật do branch đang có commit mới hơn hoặc chính sách hook.

Khi push thất bại, hãy đọc thông báo để phân biệt lỗi xác thực, phân quyền, branch protection và non-fast-forward. Không đổi user.name/email để xử lý lỗi quyền remote nếu nguyên nhân nằm ở token, SSH key hoặc policy.

## 7. Kiểm tra cấu hình trước khi commit và push

Một quy trình kiểm tra hữu ích:

~~~bash
git status
git branch --show-current
git var GIT_AUTHOR_IDENT
git var GIT_COMMITTER_IDENT
git config --show-origin --get user.name
git config --show-origin --get user.email
git remote -v
~~~

Trước khi chia sẻ output, hãy kiểm tra URL remote có nhúng username/token hoặc thông tin nội bộ hay không. Che thông tin nhạy cảm nếu gửi log cho người khác.

Sau khi tạo commit, xác nhận metadata thực tế:

~~~bash
git log -1 --format=fuller
~~~

Khi cần xác nhận chữ ký:

~~~bash
git log -1 --show-signature
git verify-commit HEAD
~~~

Khi cần kiểm tra quyền truy cập, thực hiện một thao tác đọc như fetch hoặc ls-remote theo remote của dự án. Thao tác push thử có thể tạo thay đổi trên server, vì vậy hãy dùng branch thử nghiệm hoặc quy trình được nhóm cho phép.

## 8. Sửa danh tính của commit đã tạo

Cấu hình user.name và user.email chỉ ảnh hưởng đến commit được tạo sau khi cấu hình. Nó không sửa metadata của các commit cũ.

Nếu commit mới nhất chưa chia sẻ và bạn muốn sửa author, có thể dùng:

~~~bash
git commit --amend --reset-author
~~~

Lệnh này tạo lại commit hiện tại, đặt author theo danh tính hiện tại và cập nhật metadata committer. Nếu chỉ muốn thay author bằng một giá trị khác, có thể dùng:

~~~bash
git commit --amend --author="Nguyen An <an@example.com>"
~~~

Hãy kiểm tra lại:

~~~bash
git log -1 --format=fuller
~~~

Amend thay đổi commit hash. Nếu commit đã push hoặc người khác đã dựa vào nó, việc viết lại lịch sử cần phối hợp với nhóm và có thể phải force-push theo chính sách. Không sửa lịch sử branch dùng chung một cách tùy tiện.

Nếu cần sửa nhiều commit cũ, đó là thao tác viết lại lịch sử (ví dụ rebase tương tác hoặc công cụ lọc lịch sử). Hãy sao lưu, thống nhất phạm vi và chuẩn bị kế hoạch cập nhật các bản clone trước khi thực hiện.

## 9. Danh tính email và hệ thống hosting

Nhiều nền tảng Git dùng email trong commit để liên kết hoạt động với tài khoản người dùng. Nếu email commit chưa được xác minh hoặc không được thêm vào tài khoản, giao diện web có thể không gắn commit với đúng hồ sơ dù commit vẫn hợp lệ.

Bạn có thể dùng địa chỉ email riêng tư hoặc địa chỉ no-reply do nền tảng cung cấp nếu chính sách tài khoản hỗ trợ. Khi đó, commit vẫn lưu email được cấu hình, còn nền tảng có thể ánh xạ email này tới tài khoản.

Điều cần phân biệt:

- Git lưu email như metadata; Git không gửi email để xác minh quyền truy cập remote.
- Nền tảng hosting có thể dùng email để hiển thị attribution.
- Xác thực push vẫn dùng token/OAuth hoặc SSH key.
- Chữ ký commit là lớp xác minh bổ sung, không phải thay thế email hoặc credential.

Nếu tên tác giả hiển thị sai trên giao diện, kiểm tra metadata bằng git log trước rồi kiểm tra email đã xác minh trên nền tảng. Đừng tạo token mới nếu vấn đề chỉ là email attribution.

## 10. Chẩn đoán lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| Commit hiển thị sai tên hoặc email | user.name/email, config scope hoặc biến môi trường ghi đè | Dùng git var, git config --show-origin và kiểm tra môi trường |
| Push qua HTTPS yêu cầu đăng nhập liên tục | Credential hết hạn, helper chưa cấu hình hoặc token sai | Đăng nhập lại qua credential manager, kiểm tra quyền và thời hạn token |
| Push qua SSH báo Permission denied (publickey) | Private key chưa được nạp, public key chưa đăng ký hoặc SSH dùng sai key | Kiểm tra ssh-add -l, ssh config và quyền tài khoản |
| Đăng nhập thành công nhưng push bị từ chối | Tài khoản chỉ có quyền đọc hoặc branch protection | Kiểm tra role, branch policy và quy trình pull request |
| Commit có author đúng nhưng committer khác | Cherry-pick, rebase hoặc người khác tạo commit mới | Xem git log --format=fuller và xác định quy trình tạo commit |
| Nền tảng không gắn commit với tài khoản | Email commit chưa xác minh hoặc chưa liên kết | Kiểm tra email attribution trên dịch vụ hosting |
| Chữ ký commit không xác minh được | Thiếu public key, cấu hình trust hoặc signing format sai | Kiểm tra signing key, allowed signers/keyring và git verify-commit |
| SSH cảnh báo host key thay đổi | Máy chủ thay key hoặc kết nối sai endpoint | Xác minh fingerprint qua quản trị viên trước khi cập nhật known_hosts |

## 11. Sơ đồ luồng danh tính và xác thực

~~~mermaid
flowchart TD
    A[Chuẩn bị commit] --> B[Git đọc user.name và user.email]
    B --> C[Author và committer được ghi vào commit]
    C --> D{Có bật ký commit?}
    D -- Có --> E[Ký commit bằng GPG hoặc SSH signing key]
    D -- Không --> F[Commit không có chữ ký]
    E --> G[Commit nằm trong lịch sử local]
    F --> G
    G --> H[Push hoặc fetch qua remote]
    H --> I{Transport}
    I -- HTTPS --> J[Token hoặc OAuth qua credential helper]
    I -- SSH --> K[Private key chứng minh quyền sở hữu]
    J --> L[Server xác thực client]
    K --> L
    L --> M[Server kiểm tra quyền repository và branch policy]
    M --> N[Cho phép hoặc từ chối thao tác]
~~~

Trước khi kết thúc, hãy tự xác nhận:

1. Author và committer có đúng người, đúng email theo chính sách dự án không?
2. Có cấu hình local hoặc biến môi trường nào đang ghi đè global không?
3. Remote dùng HTTPS hay SSH và credential tương ứng đã được cấu hình chưa?
4. Bạn đã phân biệt xác thực client, xác minh server và phân quyền repository chưa?
5. Nếu cần chữ ký commit, khóa ký và quy trình xác minh đã được cấu hình chưa?
6. Commit đã được chia sẻ chưa trước khi amend hoặc viết lại lịch sử?

Danh tính trong commit giúp lịch sử thể hiện ai viết và ai tạo commit. Xác thực remote kiểm soát client được phép kết nối bằng credential nào; phân quyền quyết định client được đọc hay ghi. Chữ ký commit cung cấp thêm bằng chứng mật mã về nguồn gốc và tính toàn vẹn. Khi tách rõ ba lớp này, bạn có thể cấu hình Git chính xác, xử lý lỗi push đúng nguyên nhân và giữ lịch sử cộng tác đáng tin cậy.

## Tài liệu tham khảo

- [Git documentation: git-config](https://git-scm.com/docs/git-config) — cấu hình user.name, user.email và các phạm vi cấu hình.
- [Git documentation: git-var](https://git-scm.com/docs/git-var) — xem danh tính author và committer hiệu lực.
- [Git documentation: git-commit](https://git-scm.com/docs/git-commit) — author, amend và ký commit.
- [Git documentation: gitcredentials](https://git-scm.com/docs/gitcredentials) — credential helper và xác thực qua transport.
- [Git documentation: git-push](https://git-scm.com/docs/git-push) — gửi refs lên remote.
- [Git documentation: git-verify-commit](https://git-scm.com/docs/git-verify-commit) — xác minh chữ ký commit.
