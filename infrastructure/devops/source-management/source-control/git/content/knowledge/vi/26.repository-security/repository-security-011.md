# Quyền sở hữu thư mục, safe.directory và rủi ro tin cậy quá rộng

Git kiểm tra quyền sở hữu repository trước khi tin cấu hình và thực hiện một số hành vi có thể chạy mã từ repository. Nếu thư mục làm việc hoặc Git directory thuộc về người dùng khác, Git có thể dừng và báo:

~~~text
fatal: detected dubious ownership in repository at '/path/to/repository'
To add an exception for this directory, call:

    git config --global --add safe.directory /path/to/repository
~~~

Thông báo này không nhất thiết có nghĩa bạn thiếu quyền đọc hoặc ghi tệp. Git đang cảnh báo rằng repository thuộc sở hữu của một danh tính khác với người đang chạy Git. Bạn cần xác định nguyên nhân trước khi đánh dấu repository là đáng tin cậy.

Bài học thuộc chương **Bảo mật kho mã** của module SOURCE_CONTROL_GIT. Module hướng dẫn working tree, staging area, commit, lịch sử, branch, merge, rebase, remote và tag; hiểu quyền sở hữu và ranh giới tin cậy giúp bạn dùng Git an toàn trên máy cá nhân, máy dùng chung, container và CI.

## 1. Vì sao Git kiểm tra quyền sở hữu?

Repository có thể chứa cấu hình và thành phần ảnh hưởng đến cách Git hoạt động. Một số cấu hình có thể gọi chương trình bên ngoài, thay đổi cách xử lý tệp hoặc chỉ định nơi lưu hook. Hook có thể chạy lệnh khi commit, checkout, merge, push hoặc trong các thao tác khác.

Nếu Git tự động tin mọi repository mà người dùng có thể truy cập, một repository do người khác kiểm soát có thể đưa cấu hình hoặc mã thực thi không mong muốn vào quy trình làm việc của bạn.

Vì vậy, Git kiểm tra ownership để phân biệt repository thuộc về người dùng hiện tại với repository thuộc về một danh tính khác. Khi phát hiện repository có chủ sở hữu đáng ngờ, Git có thể từ chối đọc cấu hình repository hoặc thực hiện các hành vi phụ thuộc vào cấu hình đó.

Thông báo **detected dubious ownership** là một ranh giới bảo mật. Hãy xem nó như yêu cầu xác minh nguồn gốc repository, không phải lỗi cần bỏ qua bằng một lệnh cố định.

## 2. Quyền sở hữu khác quyền truy cập tệp

Cần phân biệt ba khái niệm:

| Khái niệm | Câu hỏi được trả lời | Ví dụ |
| --- | --- | --- |
| Ownership | Tài khoản hoặc UID nào sở hữu thư mục/tệp? | Thư mục repository thuộc root nhưng Git chạy bằng tài khoản dev |
| Filesystem permissions/ACL | Người dùng hiện tại được đọc, ghi hoặc thực thi tệp không? | Người dùng có quyền đọc nhưng không có quyền ghi vào .git/index |
| Git trust (safe.directory) | Git có chấp nhận repository khác chủ sở hữu là đáng tin để xử lý không? | Cho phép một đường dẫn repository cụ thể dù owner khác user hiện tại |

safe.directory chỉ giải quyết kiểm tra trust theo ownership của Git. Nó không đổi owner, không cấp quyền filesystem và không sửa ACL.

Nếu bạn không có quyền ghi vào repository, thêm safe.directory cũng không làm git add, git commit hoặc thao tác ghi khác thành công. Khi đó cần sửa quyền hệ điều hành theo chính sách của máy hoặc nhờ quản trị viên.

## 3. Những tình huống thường gây dubious ownership

Một số nguyên nhân phổ biến:

- Clone hoặc giải nén repository bằng tài khoản quản trị, sau đó chạy Git bằng tài khoản thường.
- Chạy sudo git clone hoặc sudo git trong thư mục dự án rồi tiếp tục làm việc bằng user khác.
- Dùng Docker/CI với volume mount có UID/GID bên trong container khác với owner trên host.
- Dùng thư mục làm việc chung giữa nhiều tài khoản trên máy build.
- Di chuyển repository từ máy hoặc tài khoản khác sang.
- Dùng ổ đĩa mạng, NFS, WSL hoặc thư mục được mount với ánh xạ ownership khác.
- Linked worktree có thư mục làm việc hoặc Git directory nằm ở vị trí có owner khác.

Ví dụ, bạn clone bằng root:

~~~bash
sudo git clone https://example.com/team/app.git /work/app
~~~

Sau đó đăng nhập bằng tài khoản developer và chạy:

~~~bash
cd /work/app
git status
~~~

Nếu thư mục thuộc root, Git có thể từ chối vì tiến trình hiện tại chạy dưới danh tính developer.

Cách tốt hơn thường là clone và thao tác Git bằng đúng tài khoản sẽ sử dụng repository. Không dùng sudo cho các lệnh Git thông thường nếu không có lý do quản trị rõ ràng.

## 4. Xác định owner và danh tính đang chạy Git

Trước khi thêm ngoại lệ, hãy xác định ai đang chạy Git và ai sở hữu repository.

### Linux

Xem danh tính hiện tại:

~~~bash
id
id -u
id -un
~~~

Xem owner và quyền của thư mục repository:

~~~bash
stat -c '%U:%G (%u:%g) %A %n' .
stat -c '%U:%G (%u:%g) %A %n' .git
~~~

Lệnh thứ hai áp dụng khi .git là thư mục. Với linked worktree, .git có thể là tệp trỏ đến Git directory khác; cần xác định owner của cả thư mục làm việc và Git directory thực tế.

### macOS

~~~bash
id
stat -f '%Su:%Sg (%u:%g) %Sp %N' .
stat -f '%Su:%Sg (%u:%g) %Sp %N' .git
~~~

Định dạng stat trên macOS khác GNU/Linux; dùng đúng cú pháp theo hệ điều hành.

### Windows PowerShell

Xem tài khoản hiện tại:

~~~powershell
whoami
~~~

Xem owner của thư mục làm việc và .git:

~~~powershell
Get-Acl -LiteralPath . | Select-Object Owner
Get-Acl -LiteralPath .git | Select-Object Owner
~~~

Nếu .git là tệp trong linked worktree, lệnh trên cho biết owner của tệp trỏ; Git directory thực tế có thể nằm ở nơi khác và cần được kiểm tra riêng.

Đừng chỉ xem owner của một tệp mã nguồn. Git có thể kiểm tra thư mục làm việc hoặc Git directory liên quan. Khi cấu trúc worktree hoặc submodule phức tạp, xác định đúng đường dẫn đang gây cảnh báo trước khi thay đổi cấu hình.

## 5. Xác định đúng đường dẫn repository

safe.directory nhận đường dẫn repository được tin cậy. Nên dùng đường dẫn tuyệt đối, chính xác và trỏ đến đúng worktree hoặc repository.

Nếu Git hoạt động bình thường, lấy đường dẫn gốc của working tree:

~~~bash
git rev-parse --show-toplevel
~~~

Với bare repository không có working tree, đường dẫn cần tin cậy là thư mục bare repository tương ứng.

Khi Git đang từ chối repository do dubious ownership, lệnh Git trong repository đó có thể cũng bị chặn. Trong trường hợp này, xác định đường dẫn bằng shell hoặc File Explorer trước:

~~~bash
pwd -P
~~~

Trên PowerShell:

~~~powershell
(Get-Location).Path
~~~

Hãy chuyển đến thư mục gốc của repository trước khi lấy đường dẫn. Nếu đang ở thư mục con, đường dẫn hiện tại không nhất thiết là đường dẫn cần thêm vào safe.directory.

Sau khi đã xác minh đường dẫn, bạn có thể dùng ngoại lệ tạm thời ở dòng lệnh để kiểm tra:

~~~bash
git -c safe.directory=/absolute/path/to/repository -C /absolute/path/to/repository status
~~~

-c chỉ áp dụng cấu hình cho lần chạy này. Chỉ dùng khi bạn đã xác nhận repository đáng tin cậy; không dùng nó để che giấu một repository không rõ nguồn gốc.

## 6. safe.directory hoạt động như thế nào?

safe.directory là một cấu hình nhiều giá trị. Mỗi giá trị khai báo một đường dẫn repository mà Git có thể tin cậy dù owner khác với người dùng hiện tại.

Thêm một repository cụ thể vào cấu hình global:

~~~bash
git config --global --add safe.directory /absolute/path/to/repository
~~~

Trên Windows PowerShell, nếu terminal đang ở thư mục gốc repository:

~~~powershell
$repoPath = (Get-Location).Path
git config --global --add safe.directory $repoPath
~~~

Sau đó kiểm tra:

~~~bash
git config --global --get-all safe.directory
git status
~~~

Cấu hình global áp dụng cho người dùng hiện tại trên các repository của họ. Đây thường là phạm vi phù hợp khi bạn cần tin cậy một repository cụ thể trên máy cá nhân.

### Vì sao phải đặt ở protected configuration?

Git chỉ tôn trọng safe.directory khi giá trị đến từ protected configuration, như system, global hoặc command scope. Giá trị trong cấu hình local của chính repository không được dùng để tự đánh dấu repository là an toàn.

Điều này rất quan trọng: nếu repository không đáng tin có thể tự thêm safe.directory vào .git/config, nó có thể tự vượt qua chính kiểm tra đang bảo vệ người dùng.

Vì vậy, cấu hình sau không phải cách giải quyết hợp lệ:

~~~bash
git config --local safe.directory /path/to/repository
~~~

Hãy dùng global cho ngoại lệ của người dùng hiện tại hoặc system khi quản trị viên cần thiết lập chính sách chung cho máy.

### Kiểm tra nguồn và phạm vi cấu hình

~~~bash
git config --show-origin --show-scope --get-all safe.directory
~~~

Kết quả cho biết giá trị đến từ file nào và phạm vi cấu hình nào. Đây là cách tìm một ngoại lệ được thêm từ trước, đặc biệt khi repository đang được tin cậy bởi một wildcard ở system hoặc global config.

## 7. Wildcard và phạm vi tin cậy quá rộng

Git hỗ trợ một số giá trị wildcard cho safe.directory.

| Giá trị | Phạm vi tin cậy |
| --- | --- |
| /work/team-a/app | Chỉ repository tại đường dẫn cụ thể |
| /work/team-a/* | Các repository nằm bên dưới thư mục /work/team-a |
| * | Mọi repository, bỏ qua kiểm tra ownership |

Ví dụ wildcard cho một vùng làm việc:

~~~bash
git config --global --add safe.directory '/work/team-a/*'
~~~

Giá trị * có tác động rộng nhất:

~~~bash
git config --global --add safe.directory '*'
~~~

Cấu hình này làm Git tin cậy tất cả repository bất kể owner. Nó loại bỏ ranh giới bảo vệ ownership và có thể khiến Git đọc cấu hình hoặc chạy hook từ repository mà bạn không thực sự tin tưởng.

Không dùng safe.directory '*' như cách sửa lỗi mặc định cho máy cá nhân, máy dùng chung hoặc CI. Nếu chỉ có một repository cần truy cập, hãy khai báo đúng đường dẫn đó.

Wildcard theo thư mục cũng cần được giới hạn vào vùng mà bạn kiểm soát. Không thêm cả thư mục dùng chung rộng lớn chỉ để một dự án chạy được.

## 8. Xóa hoặc thu hẹp ngoại lệ đã thêm

Kiểm tra các giá trị hiện tại và nguồn của chúng:

~~~bash
git config --show-origin --show-scope --get-all safe.directory
~~~

Để xóa một đường dẫn cụ thể khỏi global config:

~~~bash
git config --global --fixed-value --unset-all safe.directory '/absolute/path/to/repository'
~~~

Nếu muốn xóa tất cả giá trị safe.directory trong global config:

~~~bash
git config --global --unset-all safe.directory
~~~

Lưu ý: lệnh trên chỉ xóa giá trị trong file global. Nếu system config vẫn có wildcard, giá trị đó có thể tiếp tục có hiệu lực.

Để đặt lại danh sách kế thừa từ cấu hình có mức ưu tiên thấp hơn rồi chỉ thêm các đường dẫn đã chọn, có thể thêm một giá trị rỗng trước:

~~~bash
git config --global --add safe.directory ''
git config --global --add safe.directory '/work/team-a/app'
~~~

Giá trị rỗng đặt lại danh sách safe.directory đã tích lũy trước đó tại thời điểm Git đọc cấu hình; các giá trị được khai báo sau đó sẽ tạo danh sách mới. Hãy kiểm tra lại nguồn và kết quả sau khi thay đổi.

Không xóa cấu hình system do quản trị viên quản lý nếu bạn không có trách nhiệm quản trị máy. Nếu một wildcard được áp dụng từ system config, trao đổi với người quản trị để thu hẹp phạm vi theo chính sách.

## 9. Khắc phục ownership thay vì thêm ngoại lệ

Nếu repository đáng lẽ thuộc về tài khoản hiện tại nhưng owner bị thay đổi do thao tác trước đó, cách đúng có thể là sửa ownership ở cấp hệ điều hành.

Trên Linux, quản trị viên có thể điều chỉnh owner theo chính sách của thư mục. Ví dụ sau thay đổi ownership đệ quy, chỉ dùng khi toàn bộ repository thực sự phải thuộc user và group hiện tại:

~~~bash
sudo chown -R "$(id -u):$(id -g)" /absolute/path/to/repository
~~~

Đây là thao tác trên toàn bộ cây thư mục; không chạy nếu repository dùng chung hoặc có tệp cần owner khác. Với linked worktree, Git directory có thể nằm ngoài thư mục làm việc, nên cần xác định cả hai vị trí trước khi sửa.

Trên Windows, kiểm tra owner và ACL qua Security > Advanced trong Properties hoặc nhờ quản trị viên điều chỉnh quyền sở hữu theo chính sách của tổ chức. safe.directory không thay thế thao tác sửa owner hoặc ACL.

Nếu repository được chia sẻ cho nhiều tài khoản, hãy thiết kế quyền group/ACL và quyền ghi phù hợp. Một ngoại lệ trust không phải cơ chế cấp quyền cộng tác.

## 10. Container, CI và thư mục dùng chung

Các môi trường container thường gặp lỗi ownership khi thư mục trên host được mount vào container với UID/GID khác. Ví dụ, host tạo tệp bằng UID 1000 nhưng tiến trình trong container chạy bằng UID 1001.

Trước khi thêm safe.directory, kiểm tra:

~~~bash
id
stat -c '%u:%g %n' /workspace /workspace/project
git config --show-origin --show-scope --get-all safe.directory
~~~

Các cách xử lý nên cân nhắc theo thứ tự:

1. Chạy tiến trình Git bằng UID/GID phù hợp với owner của workspace.
2. Cấu hình volume mount và quyền sở hữu đúng ngay từ bước chuẩn bị runner.
3. Nếu workspace là nguồn tin cậy và ownership khác là chủ đích, thêm đúng đường dẫn workspace vào protected config của job.
4. Chỉ dùng wildcard nếu vùng thư mục đó được quản lý chặt và phạm vi tin cậy đã được đánh giá.

Trong CI, tránh ghi safe.directory=* vào image dùng chung hoặc cấu hình runner toàn cục chỉ để bỏ qua cảnh báo. Một job có thể xử lý repository do pull request hoặc nhánh không tin cậy cung cấp; trust quá rộng có thể làm tăng rủi ro khi Git đọc cấu hình hoặc chạy hook.

## 11. Trường hợp chạy Git bằng root qua sudo

Trên Linux, khi Git chạy dưới root trong môi trường sudo, Git có thể kiểm tra biến môi trường SUDO_UID và cũng tin cậy repository thuộc UID đã gọi sudo. Cơ chế này giúp một số lệnh quản trị vẫn thao tác được với repository của người dùng ban đầu.

Kiểm tra biến:

~~~bash
printf '%s' "$SUDO_UID"
~~~

Nếu có lý do rõ ràng để Git chỉ tin repository thuộc root trong lần chạy đó, có thể bỏ biến SUDO_UID khỏi môi trường:

~~~bash
sudo env -u SUDO_UID git -C /path/to/repository status
~~~

Đây là hành vi đặc biệt của môi trường sudo, không phải cách sửa ownership. Trong công việc phát triển thông thường, nên chạy Git bằng tài khoản sở hữu repository thay vì dùng root.

## 12. Quy trình xử lý thông báo dubious ownership

Khi gặp lỗi, làm theo trình tự:

1. Đọc đường dẫn chính xác trong thông báo.
2. Xác minh nguồn gốc repository và người tạo thư mục.
3. Kiểm tra user/UID hiện tại cùng owner của working tree và Git directory.
4. Xác định đây là lỗi ownership hay lỗi filesystem permissions.
5. Nếu owner sai ngoài ý muốn, sửa ownership theo chính sách hệ điều hành.
6. Nếu repository thuộc owner khác nhưng bạn đã xác minh nguồn gốc và cần tin cậy nó, thêm đúng đường dẫn vào protected config.
7. Kiểm tra lại safe.directory cùng nguồn cấu hình và thử lệnh Git chỉ đọc.
8. Review cấu hình repository và hooks trước khi chạy thao tác có thể thực thi mã.

Ví dụ trên PowerShell, sau khi xác nhận đúng thư mục repository và nguồn gốc đáng tin:

~~~powershell
Set-Location 'C:/work/team-app'
$repoPath = (Get-Location).Path
Get-Acl -LiteralPath . | Select-Object Owner
git config --global --add safe.directory $repoPath
git config --show-origin --show-scope --get-all safe.directory
git status
~~~

Ví dụ trên Linux:

~~~bash
cd /work/team-app
id
stat -c '%U:%G (%u:%g) %A %n' .
git config --global --add safe.directory "$(pwd -P)"
git config --show-origin --show-scope --get-all safe.directory
git status
~~~

Chỉ thực hiện bước thêm ngoại lệ sau khi đã xác nhận repository đáng tin. Nếu không xác định được nguồn gốc hoặc owner, hãy dừng và nhờ quản trị viên kiểm tra.

## 13. Những lỗi và cách hiểu sai thường gặp

- **Thêm safe.directory để sửa lỗi không có quyền ghi:** cấu hình này không thay đổi ACL hoặc filesystem permission.
- **Đặt safe.directory trong .git/config:** Git không tin giá trị này vì nó đến từ chính repository cần được kiểm tra.
- **Dùng safe.directory=* để hết cảnh báo:** cách này tắt kiểm tra ownership trên diện rộng và làm mất ranh giới bảo vệ.
- **Tin mọi repository trong thư mục cha quá rộng:** wildcard theo thư mục cũng mở rộng vùng trust; hãy chọn thư mục hẹp nhất.
- **Nhầm author/committer với owner thư mục:** metadata commit không quyết định ownership của repository trên filesystem.
- **Chạy mọi lệnh Git bằng sudo:** dễ tạo tệp do root sở hữu và gây lỗi khi quay lại user thường.
- **Sửa owner đệ quy trên repository dùng chung:** có thể phá quyền sở hữu và ACL mà nhóm đang dựa vào.
- **Bỏ qua cấu hình system:** một wildcard từ system config có thể vẫn có hiệu lực sau khi xóa giá trị global.
- **Cho rằng safe.directory chứng minh nội dung repository an toàn:** nó chỉ xác nhận Git được phép xử lý repository theo trust policy; bạn vẫn cần review nguồn gốc, cấu hình và hook.

## 14. Sơ đồ chọn cách xử lý

~~~mermaid
flowchart TD
    A[Git báo detected dubious ownership] --> B[Xác định đúng repository path]
    B --> C[Kiểm tra user và owner]
    C --> D{Owner sai ngoài ý muốn?}
    D -- Có --> E[Sửa ownership hoặc ACL theo chính sách]
    D -- Không --> F{Repository có nguồn gốc đáng tin?}
    F -- Không --> G[Dừng và nhờ quản trị viên xác minh]
    F -- Có --> H[Thêm đúng path vào protected safe.directory]
    E --> I[Kiểm tra quyền và Git status]
    H --> J[Kiểm tra nguồn cấu hình và Git status]
    I --> K[Review config và hooks]
    J --> K
    K --> L[Tiếp tục công việc]
~~~

Trước khi hoàn tất, hãy tự xác nhận:

1. Tôi đã xác minh nguồn gốc repository và owner thực tế chưa?
2. Vấn đề là ownership hay filesystem permissions?
3. Tôi đã xác định đúng đường dẫn worktree/Git directory chưa?
4. safe.directory được thêm từ global/system/command config chứ không phải local config chưa?
5. Ngoại lệ chỉ bao phủ repository hoặc vùng thư mục thực sự cần thiết chưa?
6. Tôi đã kiểm tra wildcard và cấu hình kế thừa từ system chưa?
7. Tôi có tin cậy cấu hình repository và hooks trước khi cho Git xử lý không?

Quyền sở hữu thư mục là một phần của ranh giới bảo mật khi Git xử lý repository. safe.directory là danh sách ngoại lệ có chủ đích, không phải công cụ sửa quyền tệp hoặc cách tắt cảnh báo hàng loạt. Hãy xác minh owner và nguồn gốc trước, sửa ownership khi đó là lỗi môi trường, và chỉ thêm đường dẫn cụ thể khi bạn thực sự tin cậy repository.

## Tài liệu tham khảo

- [Git documentation: git-config — safe.directory](https://git-scm.com/docs/git-config#Documentation/git-config.txt-safedirectory) — protected configuration, nhiều giá trị, wildcard và giá trị rỗng.
- [Git documentation: git-config — protected configuration](https://git-scm.com/docs/git-config#SCOPES) — phạm vi cấu hình được xem là protected.
- [Git documentation: git](https://git-scm.com/docs/git) — các tùy chọn -c, -C và hành vi chung của lệnh Git.
- [Git security advisory CVE-2022-24765](https://github.blog/2022-04-12-git-security-vulnerability-announced/) — bối cảnh bảo mật liên quan đến repository ownership và việc Git xử lý repository không tin cậy.
