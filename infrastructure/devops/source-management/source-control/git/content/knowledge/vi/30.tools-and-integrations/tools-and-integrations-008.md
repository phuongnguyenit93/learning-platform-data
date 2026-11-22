# Giới hạn sao chép cache .git và bảo vệ thông tin xác thực trong log

Thư mục .git thường bị xem như một phần phụ có thể sao chép hoặc loại bỏ tùy ý. Thực tế, đây là vùng dữ liệu quan trọng của repository: nó chứa object database, branch và tag, index, cấu hình local, reflog, hook và metadata cho worktree hoặc submodule. Sao chép toàn bộ thư mục này có thể làm lộ lịch sử đã xóa khỏi phiên bản hiện tại, URL remote nội bộ, cấu hình xác thực hoặc script được chạy tự động. Ngược lại, xóa nó như một cache thông thường có thể khiến thư mục mã nguồn không còn là repository Git.

Log chẩn đoán cũng có thể chứa thông tin xác thực. Khi bật trace để tìm lỗi fetch, pull hoặc push, output có thể ghi lại URL, header HTTP, tham số lệnh, đường dẫn máy và dữ liệu môi trường. Vì vậy, cần giới hạn việc sao chép .git theo đúng mục đích, chọn phương thức clone hoặc export phù hợp, và xử lý log như dữ liệu có thể chứa bí mật.

## 1. .git là metadata của repository, không chỉ là cache

Trong một repository thông thường, .git thường là thư mục chứa dữ liệu và cấu hình nội bộ mà Git dùng để quản lý lịch sử. Nó không đơn thuần là cache có thể xóa rồi tạo lại mà không ảnh hưởng.

Một số thành phần thường gặp:

| Thành phần | Vai trò | Lưu ý khi sao chép |
|---|---|---|
| objects/ | Commit, tree, blob và tag object | Có thể chứa toàn bộ lịch sử và nội dung cũ |
| refs/ và packed-refs | Branch, tag và các ref khác | Tiết lộ tên nhánh, mốc phát hành và lịch sử được tham chiếu |
| HEAD | Branch hoặc commit hiện tại | Phản ánh trạng thái checkout |
| index | Snapshot staging hiện tại | Là trạng thái làm việc, không phải dữ liệu phân phối |
| config | Cấu hình local và remote | Có thể chứa URL, header hoặc đường dẫn nội bộ |
| logs/ | Reflog của HEAD và ref | Có thể tiết lộ lịch sử thao tác và metadata |
| hooks/ | Script chạy khi Git thực hiện một số thao tác | Có thể thực thi lệnh với quyền của người dùng |
| modules/ | Metadata repository submodule | Có thể chứa nhiều object và cấu hình riêng |
| worktrees/ | Metadata của linked worktree | Không thể tùy tiện tách khỏi các working tree liên quan |
| rr-cache/ | Dữ liệu ghi nhớ cách giải quyết conflict | Có thể chứa nội dung từ các phiên bản file |
| lfs/ | Object cache của Git LFS nếu dùng | Có thể chứa file lớn, dữ liệu nội bộ hoặc dữ liệu khách hàng |
| objects/info/alternates | Đường dẫn tới object database bên ngoài | Bản sao có thể thiếu object nếu không mang theo kho được tham chiếu |

Tùy phiên bản, cấu hình và loại repository, cấu trúc thực tế có thể khác. Không nên dựa vào một danh sách cố định để tự chọn file bên trong .git rồi sao chép thủ công.

### 1.1. Object database có thể giữ dữ liệu đã bị xóa khỏi branch

Khi một file được commit rồi bị xóa ở commit sau, object chứa nội dung cũ vẫn có thể tồn tại trong lịch sử. Nếu tạo bản sao đầy đủ của repository hoặc đóng gói toàn bộ ref, nội dung đó có thể tiếp tục đi theo bản sao.

Ví dụ:

~~~text
Commit A: thêm config/local.env có token
       |
       v
Commit B: xóa config/local.env
       |
       v
Branch main hiện tại không còn file
Nhưng lịch sử vẫn chứa Commit A và nội dung file
~~~

Xóa file khỏi working tree hoặc thêm nó vào .gitignore không làm nội dung cũ biến mất khỏi commit trước đó. Vì vậy, không thể chỉ kiểm tra cây file hiện tại trước khi chia sẻ .git.

### 1.2. Cấu hình local có thể chứa thông tin nhạy cảm

File .git/config thường chứa remote URL, branch upstream và các thiết lập riêng của repository. Một số cấu hình HTTP có thể lưu header bổ sung hoặc thông tin xác thực; include có thể kéo thêm cấu hình từ file khác.

Kiểm tra cấu hình cần cẩn trọng:

~~~sh
git config --local --list --show-origin
git remote -v
~~~

Các lệnh trên có thể hiển thị giá trị nhạy cảm nếu repository từng nhúng credential vào URL hoặc cấu hình header. Chỉ xem tại máy được phép và không gửi nguyên output vào ticket, chat hoặc log công khai.

### 1.3. .git có thể là file thay vì thư mục

Trong linked worktree và submodule, mục .git tại working tree có thể là một file trỏ tới Git directory thật, ví dụ:

~~~text
gitdir: ../.git/worktrees/feature-a
~~~

Do đó, sao chép riêng working tree hoặc riêng file .git có thể làm mất liên kết tới Git directory chung. Hãy dùng Git để xác định đường dẫn:

~~~sh
git rev-parse --show-toplevel
git rev-parse --git-dir
git rev-parse --git-common-dir
~~~

Không giả định mọi repository đều có một thư mục .git độc lập nằm ngay tại root.

## 2. Xác định mục đích trước khi sao chép

Trước khi sao chép repository, hãy xác định người nhận thực sự cần gì.

| Mục đích | Cách phù hợp thường dùng | Có cần toàn bộ .git? |
|---|---|---|
| Chạy hoặc build một phiên bản mã nguồn | Source archive hoặc checkout sạch | Không |
| Review một thay đổi | Pull request, patch hoặc bundle giới hạn ref | Không cần toàn bộ |
| Tiếp tục phát triển lịch sử | Clone từ remote hoặc bundle | Dùng Git để tạo bản sao |
| Tạo mirror để di chuyển repository | git clone --mirror | Cần lịch sử/ref được chọn, nhưng không phải bản sao nguyên trạng mọi metadata |
| Sao lưu trạng thái làm việc local chính xác | Backup/snapshot filesystem có kiểm soát | Có thể cần, phải bảo toàn cả working tree và Git directory |
| Thu thập bằng chứng sự cố | Quy trình forensic và snapshot nhất quán | Theo quy trình evidence, không tự ý chỉnh sửa |

Không gửi cả .git chỉ vì người nhận cần xem một file hoặc một commit. Hãy chọn đầu ra có phạm vi nhỏ nhất đáp ứng mục tiêu.

## 3. Khi nào không nên sao chép .git?

Không đưa .git vào:

- Gói cài đặt hoặc artifact phát hành ứng dụng.
- Build context của container nếu build không cần lịch sử Git.
- File ZIP gửi khách hàng hoặc nhà cung cấp chỉ cần source code.
- Ticket hỗ trợ chỉ cần log hoặc một patch cụ thể.
- Thư mục chia sẻ công khai hoặc cloud drive cá nhân.
- Bản backup tạm không có mã hóa và kiểm soát quyền truy cập.

Một bản sao .git có thể cung cấp lịch sử, branch và file đã xóa. Nếu repository từng chứa secret hoặc dữ liệu riêng, người nhận có thể truy cập nội dung đó dù working tree hiện tại đã sạch.

### 3.1. Không dùng .gitignore để kiểm soát gói ZIP hoặc build context

.gitignore chỉ điều khiển việc Git bỏ qua các file chưa được theo dõi. Nó không tự động loại .git khỏi:

- Lệnh nén thư mục bằng ZIP hoặc TAR.
- Docker build context.
- Artifact do CI đóng gói.
- Công cụ đồng bộ file.
- Bản sao thư mục qua ổ đĩa hoặc mạng.

Hãy cấu hình exclude riêng cho từng công cụ.

Ví dụ file .dockerignore:

~~~text
.git
.git/**
.env
.env.*
*.pem
*.key
~~~

Các pattern secret chỉ là ví dụ. Điều chỉnh theo cấu trúc và file hợp lệ của dự án. Không loại bỏ dữ liệu mà build thực sự cần nếu chưa thiết kế cách cung cấp thay thế an toàn.

Với lệnh rsync, có thể loại thư mục Git:

~~~sh
rsync -a --exclude='.git' ./ ../source-export/
~~~

Kiểm tra kỹ thư mục đích và các file được đưa vào trước khi chia sẻ. Lệnh sao chép thư mục làm việc vẫn có thể lấy theo file ignored hoặc file chưa track nếu không có exclude bổ sung.

## 4. Dùng git archive khi chỉ cần mã nguồn

Nếu người nhận chỉ cần snapshot của một commit, git archive tạo archive từ tree đã được Git theo dõi mà không mang theo object database và lịch sử.

Tạo file ZIP:

~~~sh
git archive --format=zip --output=../source-main.zip HEAD
~~~

Tạo file TAR:

~~~sh
git archive --format=tar --output=../source-main.tar HEAD
~~~

Archive chứa nội dung tree tại commit được chọn. Nó không bao gồm các thay đổi chưa commit, file untracked hoặc metadata .git.

Kiểm tra trước khi tạo:

~~~sh
git status -sb
git show --stat --oneline HEAD
~~~

Nếu cần đưa thay đổi chưa commit vào archive, hãy commit vào branch riêng hoặc tạo một tree/commit tạm có kiểm soát. Không giả định git archive sẽ lấy các file đang mở trong IDE.

### 4.1. Giới hạn với submodule và Git LFS

git archive không tự đóng gói nội dung repository submodule. Trong tree của repository cha, submodule được biểu diễn bằng gitlink trỏ tới commit của repository con. Nếu người nhận cần nội dung submodule, phải cung cấp repository con hoặc một gói riêng.

Với Git LFS, tree thường chứa pointer file; object lớn thực tế được lưu ngoài Git object database. Archive có thể chỉ chứa pointer thay vì file nội dung thực tế, tùy cách tạo và cấu hình. Kiểm tra quy trình LFS riêng trước khi phát hành archive.

## 5. Dùng clone hoặc bundle khi cần lịch sử

Nếu người nhận cần tiếp tục làm việc với Git, dùng lệnh Git thay vì sao chép thủ công một phần .git.

### 5.1. Clone repository làm việc

~~~sh
git clone https://example.com/team/project.git project-copy
~~~

Clone tạo repository mới với lịch sử và remote cần thiết cho công việc. Tuy nhiên, clone thông thường chỉ lấy các ref theo cấu hình fetch và không sao chép mọi metadata local, hook server, reflog hoặc file chưa commit.

Không dùng URL có nhúng token hoặc mật khẩu. Hãy dùng credential manager hoặc cơ chế SSH được tổ chức phê duyệt.

### 5.2. Tạo mirror cho mục đích migration

~~~sh
git clone --mirror https://example.com/team/project.git project.git
~~~

Mirror clone phù hợp để di chuyển hoặc đồng bộ các ref được remote cung cấp. Nó không phải bản sao nguyên trạng của thư mục .git ban đầu: cấu hình local, hook, reflog, index và working tree không được chuyển như một bản backup filesystem.

Mirror cũng chỉ sao chép object có thể truy cập qua các ref được lấy. Object unreachable hoặc dữ liệu chỉ còn trong reflog có thể không nằm trong mirror.

### 5.3. Repository dùng object alternates hoặc shared clone

Một repository có thể mượn object từ một object database khác thông qua objects/info/alternates. Điều này thường xuất hiện khi tạo shared clone:

~~~sh
git clone --shared /path/to/source.git shared-copy
~~~

Shared clone tiết kiệm dung lượng bằng cách tham chiếu object từ repository nguồn. Nếu nguồn bị xóa hoặc chạy garbage collection trong khi bản sao vẫn cần object được mượn, bản sao có thể bị thiếu object.

Nếu muốn mượn object từ một repository tham chiếu để tăng tốc clone nhưng không giữ phụ thuộc sau khi clone, dùng --reference cùng --dissociate:

~~~sh
git clone --reference /path/to/reference.git --dissociate https://example.com/team/project.git independent-copy
~~~

Nếu đã có một bản clone được tạo bằng --shared và muốn tách object khỏi nguồn, có thể đóng gói object cần thiết vào kho local:

~~~
git repack -a
git fsck --full
~~~

Chỉ ngừng cung cấp object store nguồn sau khi đã xác minh bản sao hoạt động độc lập và có backup phù hợp. Nếu nhận một bản sao có sẵn, kiểm tra đường dẫn alternates và bảo đảm mọi object cần thiết được cung cấp trước khi di chuyển.

### 5.4. Dùng Git bundle khi cần trao đổi ngoại tuyến

~~~sh
git bundle create ../project-main.bundle refs/heads/main
git bundle verify ../project-main.bundle
~~~

Bundle mang object và ref được chọn, nhưng không đóng gói toàn bộ cấu hình local, hook, credential, working tree hoặc mọi object unreachable. Chọn ref tối thiểu và kiểm tra lịch sử nhạy cảm trước khi chuyển.

## 6. Không tự xóa hoặc sửa file trong .git như cache thông thường

Một số dữ liệu bên trong .git có thể được Git tạo lại hoặc tối ưu, nhưng không nên tự xóa bằng file manager.

Ví dụ, index, packfile, commit-graph và cache khác có quy tắc nhất quán riêng. Xóa sai file có thể khiến trạng thái staging mất đi, làm giảm hiệu năng hoặc gây lỗi repository.

Khi cần tối ưu object database, dùng lệnh Git:

~~~sh
git gc
git maintenance run
~~~

Chỉ chạy tác vụ bảo trì khi phù hợp với môi trường và quy trình repository. Không chạy cleanup để cố xóa secret khỏi lịch sử: object vẫn có thể được tham chiếu bởi branch, tag, reflog hoặc bản sao khác.

### 6.1. Không sao chép .git trong lúc Git đang ghi

Một thao tác commit, fetch, repack hoặc gc có thể thay đổi nhiều file metadata. Sao chép .git trong lúc tiến trình đang chạy có nguy cơ thu được snapshot không nhất quán.

Nếu cần backup nguyên trạng:

1. Xác định tất cả tiến trình Git và IDE đang dùng repository.
2. Dừng hoặc chờ các thao tác ghi hoàn tất theo quy trình.
3. Tạo snapshot filesystem nhất quán hoặc dùng công cụ backup có hỗ trợ snapshot.
4. Bảo toàn quyền file, symlink và cấu trúc thư mục.
5. Khôi phục vào môi trường thử nghiệm và xác minh repository trước khi tin cậy backup.

Không chỉ copy riêng objects/ hoặc refs/ trong khi Git vẫn đang cập nhật.

### 6.2. Kiểm tra repository sau khi nhận bản sao

~~~sh
git status
git show-ref
git fsck --full
~~~

git fsck có thể phát hiện object hoặc liên kết không nhất quán, nhưng không chứng minh bản sao chứa mọi dữ liệu mà bạn kỳ vọng. Đối chiếu thêm branch, tag, remote, worktree và mục tiêu backup.

## 7. Các nguồn làm lộ credential trong log

Thông tin xác thực có thể xuất hiện ở nhiều lớp:

| Nguồn | Ví dụ dữ liệu có thể lộ |
|---|---|
| Remote URL | Username, password hoặc token nhúng trong URL |
| Git config | http.extraHeader, URL rewrite, credential settings |
| Shell history | Token trong tham số lệnh |
| Process arguments | Credential truyền trực tiếp qua command line |
| Git trace | Lệnh, đường dẫn, hoạt động transport và metadata |
| HTTP/cURL trace | URL, header, cookie hoặc chi tiết xác thực |
| SSH debug log | Host, username, đường dẫn key và thông tin kết nối |
| CI log | Biến môi trường, lệnh debug, output của script |
| IDE log | Lỗi xác thực, URL remote, đường dẫn workspace |
| Ticket hoặc file đính kèm | Log chưa lọc, screenshot terminal, file cấu hình |

Không phải mọi log đều luôn ghi secret. Tuy nhiên, hãy coi log bật ở chế độ debug là dữ liệu nhạy cảm cho tới khi đã kiểm tra và lọc.

## 8. Tránh nhúng credential vào remote URL

Không nên cấu hình remote kiểu:

~~~sh
git remote set-url origin https://user:token@example.com/team/project.git
~~~

Giá trị có thể xuất hiện trong .git/config, output của git remote -v, log, screenshot hoặc file cấu hình được sao chép.

Dùng URL không chứa credential:

~~~sh
git remote set-url origin https://example.com/team/project.git
git remote -v
~~~

Sau đó xác thực bằng credential manager hoặc phương thức đăng nhập được phê duyệt.

Với SSH, dùng remote dạng:

~~~sh
git remote set-url origin git@example.com:team/project.git
~~~

Private key cần được bảo vệ riêng, có thể dùng passphrase và SSH agent. Không đưa private key vào repository hoặc thư mục chia sẻ.

### 8.1. Credential helper

Credential helper cho phép Git lấy thông tin xác thực từ một cơ chế lưu trữ thay vì ghi token vào remote URL hoặc script.

Các lựa chọn thường gặp:

- Git Credential Manager tích hợp với kho thông tin xác thực của hệ điều hành.
- SSH agent để quản lý key trong phiên làm việc.
- Credential helper do tổ chức cung cấp.
- Credential cache trong thời gian ngắn nếu môi trường hỗ trợ.

Tránh helper lưu credential dạng plaintext nếu chính sách tổ chức không cho phép. Ví dụ, helper store có thể ghi credential vào file người dùng như .git-credentials dưới dạng văn bản thuần.

Không chia sẻ file credential helper hoặc thư mục home chỉ để giúp người khác clone repository. Cấp quyền truy cập riêng cho từng người.

### 8.2. Không truyền token trực tiếp qua command line

Tránh:

~~~sh
git -c http.extraHeader="Authorization: Bearer <token>" fetch origin
~~~

Credential trong tham số có thể bị ghi vào shell history, process listing, trace hoặc log của công cụ điều phối. Hãy dùng credential manager hoặc secret injection được thiết kế cho công cụ tự động.

Không in biến môi trường chứa token bằng echo, set, env hoặc lệnh dump toàn bộ environment.

## 9. Bảo vệ Git trace và log chẩn đoán

Git cung cấp một số biến môi trường để ghi trace khi điều tra lỗi. Các chế độ này hữu ích nhưng cần giới hạn.

| Biến hoặc chế độ | Mục đích | Rủi ro |
|---|---|---|
| GIT_TRACE | Trace hoạt động lệnh Git | Có thể ghi tham số, đường dẫn và hoạt động nội bộ |
| GIT_TRACE_CURL | Trace HTTP/cURL | Có thể ghi URL, header và chi tiết transport |
| GIT_CURL_VERBOSE | Bật output verbose cho cURL | Có thể làm log chứa thông tin kết nối nhạy cảm |
| GIT_TRACE_PACKET | Trace packet protocol | Có thể ghi dữ liệu trao đổi và tên ref |
| GIT_TRACE2_EVENT | Ghi sự kiện trace2 dạng có cấu trúc | Có thể ghi command, argv, đường dẫn và metadata môi trường |

Hành vi che giấu dữ liệu nhạy cảm phụ thuộc phiên bản Git, loại trace và cấu hình. Không mặc định rằng mọi token hoặc header đều đã được che.

### 9.1. Chỉ bật trace trong thời gian cần thiết

Trên shell POSIX, có thể giới hạn trace vào một lệnh và một file riêng:

~~~sh
umask 077
GIT_TRACE=1 git fetch origin 2>git-fetch-trace.log
~~~

Với HTTP trace:

~~~sh
umask 077
GIT_TRACE_CURL=1 git fetch origin 2>git-http-trace.log
~~~

Chỉ bật GIT_TRACE_CURL khi thực sự cần điều tra transport. Không bật trace rộng trong toàn bộ phiên làm việc hoặc CI production nếu không có lý do.

Trên Windows PowerShell, dùng biến môi trường trong phạm vi một lệnh và xóa ngay sau khi chạy:

~~~powershell
$env:GIT_TRACE = "1"
git fetch origin 2> git-fetch-trace.log
Remove-Item Env:GIT_TRACE
~~~

Đường dẫn file log phải nằm trong thư mục có quyền truy cập hạn chế. Không đưa file trace vào commit hoặc artifact mặc định.

### 9.2. Không bật shell debug quanh lệnh có secret

Trong shell script, set -x có thể in lệnh sau khi mở rộng biến. Nếu lệnh chứa token, password hoặc header xác thực, giá trị đã mở rộng có thể xuất hiện trong log.

Không bật set -x cho đoạn script xử lý credential. Nếu cần debug, log tên bước và mã trạng thái, không log giá trị secret.

### 9.3. Giới hạn log CI

Trong CI/CD:

- Lưu secret trong secret store của nền tảng.
- Dùng biến masked/protected nếu nền tảng hỗ trợ.
- Không echo secret hoặc dump toàn bộ environment.
- Tắt verbose/trace sau khi điều tra xong.
- Không upload log thô thành artifact có quyền truy cập rộng.
- Giới hạn quyền đọc log và thời gian lưu.
- Xem lại log của job thất bại trước khi gửi ra ngoài.

Tính năng mask của CI có thể không nhận diện mọi cách mã hóa, cắt chuỗi hoặc biến đổi secret. Không dựa hoàn toàn vào masking; tránh để secret đi vào output ngay từ đầu.

## 10. Rà soát log trước khi chia sẻ

Trước khi đính kèm log vào ticket hoặc gửi cho nhà cung cấp, kiểm tra:

- Authorization và Proxy-Authorization header.
- Cookie, Set-Cookie và session ID.
- Access token, refresh token, API key và password.
- URL có userinfo hoặc query parameter chứa credential.
- Private key hoặc nội dung chứng thư riêng.
- Đường dẫn home, tên người dùng và tên máy nội bộ.
- Repository URL, tên branch và mã dự án chưa công bố.
- Dữ liệu khách hàng, request/response hoặc nội dung file.

Nếu log cần được giữ nguyên làm bằng chứng, lưu bản gốc trong vùng evidence có quyền hạn chế. Tạo một bản sao đã biên tập để chia sẻ. Ghi lại ai lọc, lọc trường nào và thời điểm thực hiện.

### 10.1. Redact đúng cách

Thay giá trị bằng placeholder có ý nghĩa:

~~~text
Authorization: Bearer [REDACTED]
Cookie: [REDACTED]
remote: https://example.com/team/project.git
token=[REDACTED]
~~~

Không chỉ che vài ký tự đầu hoặc cuối của token. Không gửi screenshot có terminal phía sau vẫn hiển thị secret. Kiểm tra cả tên file, metadata và nội dung nén trước khi chia sẻ.

Không chỉnh sửa bản log gốc trong quy trình điều tra. Lưu bản gốc riêng, tạo bản đã lọc và đánh dấu rõ đó là bản phục vụ chia sẻ.

## 11. Kiểm tra credential trong repository và môi trường

### 11.1. Kiểm tra remote

~~~sh
git remote -v
git config --local --get-regexp '^remote\.'
~~~

Các lệnh có thể hiển thị URL nhạy cảm. Chỉ chạy trong môi trường tin cậy và không paste nguyên output nếu chưa rà soát.

### 11.2. Kiểm tra các cấu hình HTTP

Một số cấu hình như http.extraHeader có thể chứa header xác thực. Không in giá trị ra log hỗ trợ. Nếu cần kiểm tra, xem cấu hình cục bộ bằng công cụ quản trị được phép và xử lý kết quả như secret.

~~~sh
git config --show-origin --get-regexp '^http\.'
~~~

Không chia sẻ nguyên output của lệnh này. Sau khi kiểm tra, xóa hoặc thay cấu hình chứa credential theo quy trình; thu hồi token nếu có khả năng đã bị lộ.

### 11.3. Kiểm tra file credential bên ngoài repository

Credential helper có thể lưu dữ liệu ngoài .git, ví dụ trong thư mục người dùng. Khi chuẩn bị bàn giao máy hoặc tạo backup profile, kiểm tra các vị trí credential theo chính sách hệ điều hành và tổ chức.

Không sao chép toàn bộ thư mục home chỉ để chuyển repository. Dùng cơ chế cấp quyền và đăng nhập lại trên máy nhận.

## 12. Xử lý khi credential đã xuất hiện trong log

Nếu token, password hoặc private key đã đi vào log, screenshot, artifact hoặc file được chia sẻ, hãy coi nó có thể đã bị lộ.

Quy trình cơ bản:

1. Xác định loại credential, hệ thống phát hành và quyền mà nó có.
2. Thu hồi hoặc xoay vòng credential ngay theo quy trình.
3. Kiểm tra log truy cập để tìm hoạt động bất thường.
4. Xác định mọi bản sao: CI log, artifact, ticket, chat, email, backup và máy cá nhân.
5. Hạn chế quyền truy cập hoặc xóa bản sao theo quy trình retention/evidence.
6. Làm sạch remote URL, config, script và pipeline để secret không tiếp tục được ghi.
7. Ghi nhận sự cố và biện pháp phòng ngừa tái diễn.

Viết lại lịch sử Git không thu hồi credential. Nếu secret nằm trong commit, cần xử lý credential trước, sau đó mới quyết định rewrite lịch sử và xử lý các bản clone.

## 13. Quy trình chia sẻ repository an toàn

Giả sử một đồng nghiệp cần kiểm tra lỗi xảy ra ở commit gần nhất.

**Bước 1 — Xác định đúng repository và commit**

~~~sh
git rev-parse --show-toplevel
git status -sb
git log -5 --oneline
~~~

**Bước 2 — Chọn loại dữ liệu cần gửi**

- Chỉ cần source snapshot: dùng git archive.
- Cần một thay đổi: tạo patch hoặc pull request.
- Cần lịch sử Git: clone hoặc bundle với ref giới hạn.
- Cần bản sao local chính xác: dùng backup/snapshot có kiểm soát.

**Bước 3 — Kiểm tra secret và metadata**

Rà soát lịch sử, URL, log và file được đưa vào. Không gửi .git nếu người nhận không cần lịch sử.

**Bước 4 — Chia sẻ qua kênh được phép**

Giới hạn quyền người nhận, mã hóa theo chính sách và đặt thời hạn lưu.

**Bước 5 — Thu hồi quyền và dọn bản sao**

Khi công việc kết thúc, thu hồi quyền truy cập tạm thời và xóa file trung gian theo retention policy.

## 14. Những sai lầm thường gặp

**Coi .git là cache có thể xóa.** .git chứa lịch sử và trạng thái repository. Dùng Git để bảo trì, không xóa tùy tiện.

**Nén cả thư mục dự án để gửi source code.** Archive có thể kèm .git, file ignored, .env và log. Dùng git archive hoặc allowlist rõ ràng.

**Nghĩ .gitignore sẽ loại .git khỏi Docker hoặc ZIP.** Các công cụ đó có cơ chế exclude riêng. Cấu hình .dockerignore hoặc danh sách file đóng gói.

**Copy .git trong lúc fetch hoặc gc đang chạy.** Snapshot có thể không nhất quán. Dùng snapshot filesystem có kiểm soát hoặc clone/bundle.

**Nghĩ clone --mirror là backup nguyên trạng.** Mirror không mang mọi cấu hình local, reflog, hook và working tree. Xác định rõ yêu cầu backup.

**Bật GIT_TRACE_CURL rồi gửi log thô.** Trace có thể chứa dữ liệu kết nối nhạy cảm. Lưu riêng, rà soát và redact trước khi chia sẻ.

**Nhúng token vào remote URL.** URL có thể được lưu trong .git/config, output và log. Dùng credential manager.

**Bật set -x trong pipeline xác thực.** Shell có thể in giá trị biến sau khi mở rộng. Tắt debug quanh đoạn xử lý secret.

**Chỉ xóa log sau khi token đã lộ.** Người khác có thể đã tải bản sao. Thu hồi credential và xác định phạm vi trước.

## 15. Checklist sao chép .git và bảo vệ log

**Trước khi sao chép**

- [ ] Xác định người nhận cần source, patch, lịch sử hay backup local.
- [ ] Không đưa .git vào archive/build context nếu không cần.
- [ ] Kiểm tra object history, ref, config và hook có dữ liệu nhạy cảm.
- [ ] Xác định linked worktree, submodule, LFS và object alternates.
- [ ] Không copy .git trong khi Git đang ghi.

**Trước khi bật trace**

- [ ] Xác định lỗi cần điều tra và loại trace tối thiểu.
- [ ] Dùng file log riêng với quyền truy cập hạn chế.
- [ ] Không bật trace rộng trong CI production nếu không cần.
- [ ] Không dùng set -x quanh lệnh chứa credential.
- [ ] Tắt trace ngay sau khi thu thập đủ dữ liệu.

**Trước khi chia sẻ log**

- [ ] Kiểm tra Authorization, cookie, token và password.
- [ ] Kiểm tra URL, header, query parameter và đường dẫn nội bộ.
- [ ] Kiểm tra dữ liệu khách hàng và metadata.
- [ ] Giữ bản gốc riêng nếu cần điều tra.
- [ ] Redact trên bản sao và xác minh lại trước khi gửi.

**Khi phát hiện rò rỉ**

- [ ] Thu hồi hoặc xoay vòng credential.
- [ ] Kiểm tra log truy cập và phạm vi phát tán.
- [ ] Xác định CI artifact, ticket, chat, email và backup liên quan.
- [ ] Hạn chế quyền hoặc xử lý bản sao theo chính sách.
- [ ] Sửa cấu hình và quy trình để ngăn tái diễn.

## 16. Kết luận

.git là metadata cốt lõi của repository, không phải một cache vô hại. Nó có thể chứa object lịch sử, ref, cấu hình local, hook, reflog và metadata worktree hoặc submodule. Chỉ sao chép toàn bộ khi mục tiêu thực sự cần một bản backup có kiểm soát; nếu chỉ cần source code, patch hoặc lịch sử được chọn, hãy dùng git archive, patch, clone hoặc bundle phù hợp.

Log chẩn đoán cũng cần được bảo vệ như dữ liệu có thể chứa credential. Hãy dùng credential manager, tránh token trong URL và command line, giới hạn thời gian bật trace, không in secret trong CI và rà soát log trước khi chia sẻ. Khi credential đã lộ, thu hồi nó trước rồi xử lý log, artifact, lịch sử và các bản sao liên quan.
