# Bảo vệ log, bản vá và bản sao kho mã khi chứa dữ liệu riêng

Repository Git thường được xem như nơi lưu mã nguồn, nhưng log, patch và bản sao repository cũng có thể chứa nhiều dữ liệu riêng. Commit message có thể ghi tên khách hàng hoặc mã sự cố; diff có thể chứa cấu hình, dữ liệu thử nghiệm hoặc token vô tình được thêm vào; bản clone và bundle có thể mang theo toàn bộ lịch sử, branch và tag. Một file log được gửi để nhờ hỗ trợ hoặc một bản sao repository được tải lên dịch vụ bên ngoài có thể làm lộ nhiều thông tin hơn phần mã nguồn đang nhìn thấy.

Muốn bảo vệ repository, cần xem mọi đầu ra được tạo từ Git như một bản dữ liệu có mức nhạy cảm tương ứng với nội dung nguồn. Trước khi tạo hoặc chia sẻ, hãy xác định mục đích, giới hạn phạm vi, loại bỏ dữ liệu không cần thiết và dùng kênh lưu trữ có quyền truy cập phù hợp. Nếu bí mật đã được commit hoặc phát tán, phải xử lý bí mật và các bản sao liên quan; xóa một file ở branch hiện tại không làm nó biến mất khỏi lịch sử hay khỏi bản clone đã tồn tại.

## 1. Vì sao log, patch và bản sao repository cần được bảo vệ?

Git lưu nội dung và metadata trong các object, ref và cấu hình. Nhiều lệnh tạo ra đầu ra dễ chia sẻ, nhưng đầu ra đó có thể tiết lộ dữ liệu riêng.

| Đầu ra | Thông tin có thể bị lộ |
|---|---|
| Commit log | Tên, email tác giả, thời gian, commit message, mã ticket, tên branch hoặc tag |
| Diff và patch | Nội dung thêm/xóa, cấu hình, dữ liệu mẫu, đường dẫn nội bộ, token hoặc khóa bị commit nhầm |
| Clone đầy đủ | Lịch sử, branch, tag, object còn được tham chiếu, remote URL và một phần cấu hình local |
| Mirror hoặc bundle | Nhiều ref và lịch sử; có thể bao gồm commit đã không còn trên branch mặc định |
| Source archive | Snapshot mã nguồn tại một commit, bao gồm mọi file được đưa vào tree |
| Log CI và hook | Lệnh đã chạy, đường dẫn, biến môi trường bị in ra, thông báo lỗi và một phần nội dung file |

Thông tin riêng không chỉ là mật khẩu. Nó còn có thể là dữ liệu cá nhân, địa chỉ email, tên khách hàng, mã hợp đồng, URL nội bộ, kiến trúc hệ thống, lỗ hổng chưa công bố hoặc thông tin vận hành.

Một repository private vẫn có thể bị sao chép bởi người có quyền truy cập. Nhãn private giới hạn đối tượng được truy cập trên nền tảng, nhưng không biến nội dung thành bí mật tuyệt đối và không ngăn người được cấp quyền tạo bản clone hoặc patch.

## 2. Nhận diện dữ liệu nhạy cảm trong Git

Trước khi tạo log, patch hoặc bản sao, xác định loại dữ liệu mà dự án không được phát tán.

### 2.1. Secret và thông tin xác thực

Ví dụ:

- Password, API token, access key và refresh token.
- Private key, certificate riêng và file cấu hình xác thực.
- Connection string có username/password.
- URL remote có nhúng token hoặc thông tin đăng nhập.
- File .env, file cấu hình local và credential cache.

Secret có thể xuất hiện trong source code, commit message, diff, test fixture, script, log lỗi hoặc lệnh được ghi lại trong CI.

### 2.2. Dữ liệu cá nhân và dữ liệu khách hàng

Ví dụ:

- Họ tên, email, số điện thoại hoặc địa chỉ.
- Mã định danh tài khoản, hồ sơ hoặc giao dịch.
- Dữ liệu sản xuất được sao chép vào test fixture.
- Nội dung request/response có thông tin người dùng.
- File export, dump cơ sở dữ liệu hoặc log ứng dụng.

Không nên đưa dữ liệu production vào repository hoặc patch chỉ để tái hiện lỗi. Hãy dùng dữ liệu giả lập, đã ẩn danh và chỉ giữ các trường cần thiết cho test.

### 2.3. Metadata cũng có thể là dữ liệu riêng

Commit message, author/committer name, email, thời gian, tên branch, tên file và đường dẫn thư mục có thể tiết lộ:

- Danh tính hoặc địa chỉ email cá nhân.
- Tên dự án nội bộ và mã khách hàng.
- Lịch phát hành hoặc thời gian xử lý sự cố.
- Cấu trúc thư mục và tên hệ thống chưa công bố.

Vì vậy, khi chia sẻ log, không chỉ kiểm tra nội dung diff. Hãy xem cả metadata mà lệnh đang xuất.

## 3. Phân loại và giảm thiểu dữ liệu trước khi tạo đầu ra

Một quy trình đơn giản có thể gồm bốn câu hỏi:

1. **Ai cần nhận dữ liệu?** Một đồng đội, nhóm hỗ trợ, nhà cung cấp hay công chúng?
2. **Họ cần biết điều gì?** Trạng thái, mã commit, một đoạn diff hay toàn bộ lịch sử?
3. **Dữ liệu nào không cần thiết?** Token, email, dữ liệu khách hàng, file không liên quan hoặc branch khác.
4. **Kênh nào được phép?** Hệ thống quản lý mã nguồn, kho artifact nội bộ, kênh hỗ trợ được phê duyệt hay thiết bị được mã hóa.

Chỉ tạo phần đầu ra nhỏ nhất đáp ứng mục đích. Nếu người nhận chỉ cần biết commit nào gây lỗi, có thể gửi mã SHA và một đoạn log đã lọc thay vì một bản mirror của repository.

### 3.1. Ưu tiên dữ liệu giả lập

Khi tạo test hoặc patch:

- Thay tên, email và mã định danh thật bằng dữ liệu giả.
- Không dùng dump database production làm fixture.
- Xóa token và credential khỏi log mẫu.
- Giữ nguyên cấu trúc cần thiết để tái hiện lỗi nhưng thay giá trị riêng.
- Ghi rõ dữ liệu nào đã được giả lập hoặc ẩn danh.

Ẩn danh phải được đánh giá theo khả năng nhận diện lại. Chỉ thay tên nhưng giữ số tài khoản, timestamp chính xác hoặc tổ hợp thuộc tính đặc biệt vẫn có thể cho phép suy ra danh tính.

### 3.2. Không đưa secret vào command line hoặc commit message

Tránh truyền token trực tiếp trong lệnh:

~~~sh
# Không nên: giá trị có thể lưu trong shell history hoặc log tiến trình
git remote set-url origin https://user:token@example.com/team/app.git
~~~

Hãy dùng credential manager của hệ điều hành, SSH agent hoặc cơ chế cấp credential được tổ chức phê duyệt. Remote URL nên chứa địa chỉ repository, không chứa mật khẩu hoặc token.

Commit message nên mô tả thay đổi và tham chiếu mã ticket được phép chia sẻ. Không chép nội dung khách hàng, thông tin đăng nhập hoặc chi tiết sự cố nhạy cảm vào message.

## 4. Bảo vệ Git log

Các lệnh log có thể hiển thị nhiều metadata hơn mong đợi. Chọn format phù hợp với người nhận.

### 4.1. Chỉ xuất thông tin cần thiết

Ví dụ xem commit ngắn gọn:

~~~sh
git log --oneline -10
~~~

Xem tác giả, ngày và subject:

~~~sh
git log -5 --format="%h %an %ad %s" --date=short
~~~

Xem thống kê file thay đổi mà không hiển thị patch:

~~~sh
git log -5 --stat
~~~

Lệnh --stat vẫn có thể tiết lộ tên file hoặc đường dẫn nội bộ. Nếu tên file nhạy cảm, không chia sẻ nguyên đầu ra.

Trước khi gửi log, đọc lại toàn bộ nội dung. Tìm token, email, tên khách hàng, mã định danh, URL nội bộ và đường dẫn máy cá nhân. Đừng giả định lệnh chỉ hiển thị mã SHA nên không có dữ liệu nhạy cảm.

### 4.2. Giới hạn phạm vi commit

Thay vì xuất toàn bộ lịch sử, giới hạn số commit hoặc khoảng thời gian:

~~~sh
git log --oneline -20
git log --since="2026-11-01" --until="2026-11-15" --oneline
git log -- path/to/component
~~~

Ngày trong ví dụ chỉ minh họa. Chọn khoảng thời gian và đường dẫn phù hợp với mục tiêu hỗ trợ. Đường dẫn file có thể tiết lộ tên khách hàng hoặc mã dự án, nên vẫn cần rà soát.

### 4.3. Lưu log vào file

Log được chuyển hướng vào file có thể tồn tại lâu hơn dự kiến, được đồng bộ lên cloud hoặc đính kèm vào ticket. Trên shell POSIX, có thể tạo file riêng với quyền hạn chế:

~~~sh
umask 077
git log --oneline -20 > incident-git-log.txt
~~~

Quyền file thực tế còn phụ thuộc hệ điều hành và filesystem. Trên Windows, dùng thư mục có ACL giới hạn người đọc và lưu file trong ổ đĩa được mã hóa theo chính sách tổ chức.

Không bật chế độ trace hoặc shell debug khi lệnh có thể in credential. Trước khi gửi log CI, xem cả dòng lệnh, biến môi trường được in, output của test và thông báo lỗi.

### 4.4. Log dùng cho điều tra sự cố

Trong sự cố bảo mật, giữ bản gốc phục vụ điều tra theo chính sách evidence của tổ chức. Tạo một bản sao đã lọc để chia sẻ với người không cần xem dữ liệu nhạy cảm.

Không sửa đè bản log gốc rồi tuyên bố đó là bằng chứng nguyên trạng. Ghi nhận ai đã tạo bản sao, thời điểm, bộ lọc đã áp dụng và nơi lưu bản gốc.

## 5. Bảo vệ diff và patch

Patch là dữ liệu có thể tái áp dụng vào source code. Nó thường chứa cả metadata commit và nội dung thay đổi, vì vậy cần bảo vệ như một phần của mã nguồn.

### 5.1. Diff có thể chứa dữ liệu gì?

Lệnh diff có thể hiển thị:

- Dòng code mới và dòng code bị xóa.
- Secret bị xóa khỏi working tree nhưng vẫn còn trong patch.
- Giá trị cấu hình hoặc dữ liệu thử nghiệm.
- Tên file, đường dẫn và cấu trúc thư mục.
- Thông tin nhúng trong binary khi dùng định dạng phù hợp.

Ví dụ:

~~~sh
git diff
git diff --cached
git diff main...feature/payment
~~~

Lệnh đầu xem thay đổi chưa stage, lệnh thứ hai xem thay đổi đã stage, lệnh thứ ba so sánh thay đổi của branch feature với điểm phân kỳ từ main. Cả ba đều có thể tiết lộ nội dung riêng.

### 5.2. Tạo patch từ commit

Lệnh git format-patch tạo file patch có thể dùng trong quy trình gửi patch:

~~~sh
git format-patch -1 <commit-sha>
~~~

Patch có thể bao gồm author, ngày, subject, commit message và diff. Nếu commit chứa dữ liệu riêng, patch cũng có thể chứa dữ liệu đó dù file hiện tại đã được sửa hoặc xóa.

Để xem patch mà không tạo file trong thư mục hiện tại:

~~~sh
git format-patch --stdout -1 <commit-sha>
~~~

Output vẫn cần được xem xét trước khi chia sẻ. Không đưa thẳng vào kênh chat công khai hoặc ticket có quyền truy cập rộng.

### 5.3. Chia sẻ patch an toàn

Trước khi gửi:

1. Xác nhận người nhận có quyền xem toàn bộ nội dung patch.
2. Kiểm tra message, author metadata, đường dẫn và diff.
3. Loại bỏ dữ liệu không liên quan bằng cách tạo patch mới từ thay đổi đã được làm sạch.
4. Dùng hệ thống trao đổi được tổ chức phê duyệt.
5. Đặt thời hạn lưu và thu hồi quyền truy cập sau khi hoàn thành.

Không chỉ xóa một dòng nhạy cảm khỏi email nhưng vẫn đính kèm patch gốc. Kiểm tra cả file đính kèm, tên file, nội dung archive và lịch sử trao đổi.

### 5.4. Không dùng patch như công cụ xóa dấu vết

Nếu patch đã được gửi ra ngoài, xóa file local không thu hồi được bản mà người nhận đã tải xuống. Cần đánh giá phạm vi người nhận, yêu cầu xóa theo quy trình, thu hồi secret nếu có và ghi nhận sự cố theo chính sách.

## 6. Bảo vệ bản clone và bản sao repository

Clone Git có thể mang theo nhiều dữ liệu hơn branch mặc định. Một clone đầy đủ thường chứa object database, các ref được fetch, lịch sử liên quan, tag và cấu hình local. Mirror clone có thể chứa nhiều ref hơn nữa.

### 6.1. Các dạng bản sao phổ biến

| Dạng bản sao | Đặc điểm | Rủi ro cần chú ý |
|---|---|---|
| Clone thông thường | Working tree và lịch sử được fetch | Có thể chứa commit cũ với secret hoặc dữ liệu riêng |
| Shallow clone | Giới hạn một phần lịch sử theo depth | Không phải ranh giới bảo mật; vẫn chứa dữ liệu của snapshot được lấy |
| Mirror clone | Sao chép các ref theo chế độ mirror | Có thể bao gồm nhiều branch, tag và ref nội bộ |
| Git bundle | Đóng gói object và ref được chọn vào một file | Là file có thể chuyển đi nơi khác; mặc định không được mã hóa |
| Source archive | Snapshot của tree tại một mốc | Có thể chứa mọi file được track trong snapshot |
| Bản sao thư mục làm việc | Có thể gồm cả file chưa track và cấu hình local | Có thể chứa .env, log, cache và dữ liệu máy cá nhân |

Đừng coi shallow clone, archive hoặc bundle là cách tự động ẩn dữ liệu. Hãy kiểm tra nội dung thực tế và ref được đưa vào.

### 6.2. Clone mirror cần kiểm soát chặt

Mirror clone thường được dùng cho backup hoặc di chuyển repository:

~~~sh
git clone --mirror https://example.com/team/project.git project.git
~~~

Bản mirror có thể lưu nhiều ref hơn clone làm việc thông thường. Nó nên được đặt trong vùng backup có quyền truy cập hạn chế, mã hóa và chính sách lưu giữ rõ ràng.

Không tải mirror lên dịch vụ chia sẻ file cá nhân hoặc đính kèm vào ticket chỉ để nhờ xem một lỗi. Nếu người hỗ trợ chỉ cần một commit hoặc một patch, tạo đầu ra nhỏ hơn.

### 6.3. Git bundle cũng là dữ liệu nhạy cảm

Có thể tạo bundle từ một tập ref:

~~~sh
git bundle create support.bundle main
git bundle verify support.bundle
git bundle list-heads support.bundle
~~~

Bundle chứa object cần thiết cho ref được chỉ định và các object lịch sử liên quan. Bundle không tự mã hóa nội dung. Nếu cần chuyển bundle, đặt nó trong vùng lưu trữ được bảo vệ hoặc mã hóa bằng công cụ đã được tổ chức phê duyệt.

Checksum có thể giúp kiểm tra file có bị thay đổi trong quá trình truyền, nhưng checksum không che giấu nội dung và không thay thế mã hóa.

### 6.4. Bản sao thư mục có thể chứa dữ liệu ngoài Git

Khi nén cả thư mục dự án, có thể vô tình đưa vào:

- File .env hoặc cấu hình local.
- File log và báo cáo test.
- Thư mục cache, build output hoặc dữ liệu tạm.
- Credential helper file hoặc cấu hình công cụ.
- File chưa track và file ignored.
- Thư mục .git với toàn bộ lịch sử và cấu hình repository.

Trước khi tạo archive thư mục, kiểm tra danh sách file và dùng allowlist nếu phù hợp. Source archive từ git archive có phạm vi rõ hơn bản nén working directory, nhưng vẫn phải rà soát nội dung được track.

## 7. Bảo vệ cấu hình và credential khi sao chép repository

Remote URL, Git config và công cụ xác thực có thể để lộ thông tin.

### 7.1. Kiểm tra remote URL

~~~sh
git remote -v
git config --show-origin --get-regexp '^remote\.'
~~~

Kiểm tra URL không chứa username/password/token. Nếu phát hiện credential được nhúng trong URL, hãy coi nó là secret đã có nguy cơ bị lộ, thu hồi hoặc xoay vòng và thay bằng URL sạch.

### 7.2. Dùng credential manager

Ưu tiên:

- Credential manager tích hợp của hệ điều hành.
- SSH key được bảo vệ bằng passphrase và quản lý qua agent.
- Token có phạm vi quyền tối thiểu và thời hạn ngắn.
- Secret manager của tổ chức cho automation.

Tránh lưu token dạng plaintext trong file cấu hình hoặc script. Không commit private key, token hay credential vào repository.

### 7.3. Tách cấu hình local khỏi dữ liệu chia sẻ

Git có các scope cấu hình system, global, local, worktree và command. File local như .git/config thường chứa remote URL, branch tracking và cấu hình riêng của repository. Khi sao chép cả thư mục .git, người nhận có thể nhận cả những giá trị này.

Trước khi gửi bản sao, xem:

~~~sh
git config --local --list --show-origin
git remote -v
~~~

Không gửi file cấu hình nếu người nhận không cần. Nếu phải cung cấp, tạo bản đã lọc và loại credential, đường dẫn máy cá nhân hoặc cấu hình nội bộ không liên quan.

## 8. .gitignore không bảo vệ dữ liệu đã được track

Thêm file vào .gitignore chỉ khiến Git bỏ qua file chưa được theo dõi theo các quy tắc ignore. Nó không tự xóa file đã được commit hoặc đưa vào index.

Ví dụ thêm file môi trường vào ignore:

~~~gitignore
.env
.env.*
!.env.example
*.pem
*.key
~~~

Các pattern chỉ là ví dụ; hãy điều chỉnh theo file hợp lệ mà dự án cần phân phối. Không nên bỏ qua mọi file key một cách máy móc nếu repository cần chứng thư công khai hoặc fixture hợp lệ.

Nếu file đã được track và cần ngừng theo dõi:

~~~sh
git rm --cached -- .env
git add .gitignore
git commit -m "Stop tracking local environment file"
~~~

Lệnh git rm --cached bỏ file khỏi index nhưng giữ file trong working tree. Commit mới sẽ không còn chứa file đó, nhưng commit cũ vẫn có thể chứa nội dung. Nếu file chứa secret, phải xử lý như một sự cố lộ secret.

## 9. Tìm kiếm và phát hiện dữ liệu nhạy cảm

Không có một lệnh đơn giản bảo đảm phát hiện mọi secret. Kết hợp kiểm tra tự động và review thủ công.

### 9.1. Tìm trong working tree

Có thể tìm một số mẫu nghi vấn bằng công cụ tìm kiếm văn bản:

~~~sh
git grep -n -I -E 'password|token|secret|api[_-]?key' HEAD
~~~

Đây chỉ là tìm từ khóa trong nội dung tree tại HEAD. Nó có thể bỏ sót secret đã mã hóa, tên biến khác, binary, dữ liệu trong commit cũ hoặc giá trị không chứa các từ khóa này.

### 9.2. Kiểm tra lịch sử

Một file đã bị xóa khỏi branch hiện tại vẫn có thể tồn tại trong commit cũ. Có thể tìm lịch sử thay đổi của một đường dẫn:

~~~sh
git log --all --full-history -- path/to/config-file
~~~

Lệnh này giúp xem commit liên quan tới đường dẫn, nhưng không thay thế công cụ quét secret toàn bộ object database.

### 9.3. Dùng secret scanner

Các công cụ quét secret có thể kiểm tra working tree, commit và đôi khi cả toàn bộ lịch sử. Khi chọn công cụ:

- Xác định công cụ quét local hay chỉ chạy trong CI.
- Bảo đảm scanner không gửi nội dung repository tới dịch vụ ngoài nếu chưa được phép.
- Đọc chính sách telemetry và lưu trữ kết quả.
- Cấu hình allowlist cho test fixture giả lập hợp lệ.
- Không in giá trị secret đầy đủ trong log báo lỗi.
- Đặt quy trình xử lý false positive và xác nhận phát hiện thật.

Secret scanning giúp giảm rủi ro nhưng không chứng minh repository hoàn toàn sạch. Review và kiểm soát quy trình vẫn cần thiết.

## 10. Xử lý khi secret đã được commit hoặc chia sẻ

Khi phát hiện token, password hoặc private key trong Git, hãy coi credential đó có thể đã bị lộ. Xóa file khỏi branch hiện tại chưa đủ.

### 10.1. Ưu tiên thu hồi hoặc xoay vòng secret

Thứ tự ưu tiên:

1. Xác định loại credential, hệ thống cấp phát và quyền của nó.
2. Thu hồi, vô hiệu hóa hoặc xoay vòng credential ngay theo quy trình.
3. Cấp credential mới với phạm vi quyền tối thiểu.
4. Kiểm tra log sử dụng để tìm hoạt động bất thường.
5. Cập nhật dịch vụ, CI, máy triển khai và người dùng hợp lệ.

Viết lại lịch sử Git không làm credential cũ mất hiệu lực. Nếu token vẫn còn dùng được, người đã có bản sao cũ có thể tiếp tục sử dụng nó.

### 10.2. Xác định phạm vi phát tán

Kiểm tra:

- Repository và các branch/tag có chứa commit.
- Pull request, merge request và diff đã hiển thị trên nền tảng.
- Clone, fork, mirror, bundle và patch đã gửi.
- Log CI, artifact, cache và backup.
- Kênh chat, ticket, email hoặc hệ thống hỗ trợ.
- Những người hoặc hệ thống đã tải dữ liệu.

Giữ bằng chứng cần thiết theo quy trình ứng phó sự cố, đồng thời giới hạn quyền truy cập vào dữ liệu có secret.

### 10.3. Xóa dữ liệu khỏi lịch sử khi cần

Sau khi credential đã được thu hồi, tổ chức có thể quyết định viết lại lịch sử để giảm khả năng người khác vô tình lấy lại dữ liệu.

Việc này cần phối hợp với tất cả người dùng repository vì viết lại lịch sử thay đổi mã commit và có thể yêu cầu force push. Công cụ chuyên dụng như git-filter-repo thường được dùng để xóa đường dẫn hoặc thay thế chuỗi nhạy cảm trên các ref được chọn.

Ví dụ, trong một bản clone làm việc riêng đã được backup và sau khi thống nhất phạm vi:

~~~sh
git filter-repo --path config/private.env --invert-paths
~~~

Lệnh minh họa loại đường dẫn khỏi lịch sử mà công cụ xử lý. Tùy phiên bản và trạng thái repository, git-filter-repo có thể yêu cầu clone mới hoặc tùy chọn xác nhận ghi đè. Đọc hướng dẫn của phiên bản đang dùng và kiểm tra ref đầu ra trước khi đẩy thay đổi.

Nếu cần thay một giá trị secret trong nhiều file, dùng chức năng replace-text của công cụ với file biểu thức được bảo vệ. Không ghi secret thật trong ticket hoặc log công khai; file biểu thức cũng phải được xử lý như dữ liệu nhạy cảm.

Không chạy rewrite trên repository dùng chung mà chưa có kế hoạch, backup và thông báo. Sau khi viết lại, cần phối hợp force push các ref liên quan, yêu cầu đồng đội đồng bộ lại clone theo hướng dẫn, và xử lý các bản sao ngoài repository.

### 10.4. Hiểu giới hạn của việc rewrite

Viết lại lịch sử có thể làm secret biến mất khỏi các ref mới, nhưng không bảo đảm mọi bản sao đều bị xóa:

- Clone cũ có thể vẫn giữ object.
- Fork có thể không được cập nhật.
- Pull request hoặc trang diff có thể được nền tảng lưu cache.
- Bundle, patch và artifact đã tải xuống vẫn tồn tại.
- Backup có thể giữ snapshot theo chính sách lưu trữ.
- Object không còn được tham chiếu có thể tồn tại một thời gian trước khi garbage collection.

Vì vậy, phải kết hợp thu hồi credential, giới hạn truy cập, yêu cầu xử lý bản sao và kiểm tra lại phạm vi phát tán.

## 11. Lưu trữ và truyền dữ liệu Git an toàn

Khi cần lưu hoặc chuyển log, patch, bundle hay clone:

- Dùng kho lưu trữ nội bộ được phê duyệt.
- Mã hóa khi truyền và khi lưu theo chính sách tổ chức.
- Cấp quyền tối thiểu cho người nhận.
- Đặt thời hạn lưu và xóa bản sao khi hết mục đích.
- Ghi nhận người tạo, người nhận, thời điểm và lý do chia sẻ.
- Kiểm tra checksum khi cần xác minh tính toàn vẹn.
- Không dùng email cá nhân, cloud drive cá nhân hoặc thiết bị USB không được phép.

Checksum chỉ xác nhận dữ liệu có khớp với giá trị băm đã ghi nhận; nó không xác thực người gửi và không mã hóa nội dung. Nếu cần xác thực nguồn gốc, dùng chữ ký số hoặc cơ chế xác minh được tổ chức quy định.

### 11.1. Bảo vệ backup

Backup repository nên:

- Được mã hóa và giới hạn người có quyền khôi phục.
- Có chính sách retention rõ ràng.
- Được kiểm tra khả năng khôi phục định kỳ.
- Có log truy cập và cảnh báo khi tải xuống bất thường.
- Được xử lý khi có yêu cầu xóa dữ liệu hoặc sự cố secret theo chính sách lưu trữ.

Backup là bản sao dữ liệu có giá trị cao. Đừng để quyền truy cập backup rộng hơn quyền truy cập repository nguồn nếu không có lý do nghiệp vụ.

### 11.2. Bản sao hỗ trợ kỹ thuật

Khi gửi repository cho nhà cung cấp:

1. Hỏi rõ họ cần log, patch, archive hay clone.
2. Xác nhận kênh truyền và nơi lưu dữ liệu.
3. Tạo bản tối thiểu, bỏ branch/tag không liên quan.
4. Quét secret và dữ liệu cá nhân.
5. Mã hóa nếu chính sách yêu cầu.
6. Cấp quyền tạm thời và ghi nhận thời hạn xóa.

Nếu chỉ cần tái hiện lỗi, hãy cân nhắc tạo repository mẫu đã loại dữ liệu riêng thay vì gửi bản sao của repository production.

## 12. Ví dụ: chuẩn bị gói chẩn đoán đã giảm thiểu dữ liệu

Giả sử nhóm hỗ trợ cần xác định commit nào làm hỏng một chức năng. Họ không cần toàn bộ repository hoặc dữ liệu khách hàng.

**Bước 1 — Chọn commit liên quan**

~~~sh
git log --oneline -15 -- src/payment
~~~

**Bước 2 — Tạo log tối thiểu**

~~~sh
git log -5 --format="%h %ad %s" --date=short -- src/payment
~~~

Nếu subject hoặc đường dẫn có dữ liệu riêng, tạo bản sao đã biên tập trước khi gửi.

**Bước 3 — Tạo patch cho commit cần xem**

~~~sh
git format-patch --stdout -1 <commit-sha> > payment-fix.patch
~~~

Kiểm tra patch:

~~~sh
git show --format=fuller --stat <commit-sha>
~~~

Sau đó mở patch và rà soát author, message, đường dẫn và nội dung diff. Nếu có dữ liệu riêng, tạo patch mới từ commit đã làm sạch; không chỉ xóa thủ công một phần output trong khi vẫn gửi file gốc.

**Bước 4 — Đóng gói và chuyển giao**

Chỉ chuyển log và patch qua kho hỗ trợ được phê duyệt. Đặt quyền truy cập cho đúng nhóm, ghi thời hạn lưu và kiểm tra người nhận.

**Bước 5 — Thu hồi và dọn dữ liệu**

Khi ticket kết thúc, xóa bản sao theo chính sách retention. Nếu phát hiện secret, xử lý credential và các bản sao theo quy trình ứng phó sự cố thay vì chỉ xóa gói chẩn đoán.

## 13. Các lỗi bảo mật thường gặp

**Nghĩ rằng repository private có thể chia sẻ tự do.** Người có quyền clone có thể tạo bản sao. Hãy giới hạn quyền và kiểm soát cả các bản export.

**Chỉ quét branch hiện tại.** Secret có thể nằm trong commit cũ, tag hoặc branch khác. Cần quét lịch sử và các ref có liên quan.

**Dùng .gitignore để xóa secret khỏi lịch sử.** Ignore không xóa nội dung đã track. Bỏ track chỉ ảnh hưởng commit mới; credential cũ vẫn cần thu hồi.

**Gửi patch mà không đọc diff.** Patch có thể chứa cả dòng bị xóa, metadata và file không liên quan.

**Gửi mirror thay vì log tối thiểu.** Mirror thường mang theo nhiều ref và lịch sử. Chỉ tạo khi người nhận thực sự cần.

**Cho rằng bundle được mã hóa.** Git bundle là file dữ liệu có thể đọc được nếu người khác lấy được file. Cần bảo vệ bằng kênh và lớp mã hóa riêng.

**Đưa token vào remote URL hoặc command line.** Token có thể xuất hiện trong shell history, process listing, config hoặc log. Dùng credential manager.

**Chỉ xóa secret khỏi commit mới.** Các clone, fork, cache, backup và patch cũ vẫn có thể giữ secret. Thu hồi credential trước, sau đó xử lý lịch sử và bản sao.

**Bỏ qua log CI.** Lệnh debug hoặc biến môi trường bị in có thể làm lộ token. Tắt tracing nhạy cảm và lọc output.

## 14. Checklist bảo vệ log, patch và bản sao

**Trước khi tạo**

- [ ] Xác định người nhận và mục đích.
- [ ] Chọn phạm vi commit, ref và file nhỏ nhất cần thiết.
- [ ] Kiểm tra secret, dữ liệu cá nhân, metadata và đường dẫn.
- [ ] Ưu tiên dữ liệu giả lập hoặc đã ẩn danh.
- [ ] Không đưa credential vào URL, message hoặc command line.

**Trước khi chia sẻ**

- [ ] Đọc lại toàn bộ log, diff, patch hoặc danh sách file.
- [ ] Loại branch, tag và file không liên quan.
- [ ] Dùng kênh lưu trữ được phê duyệt.
- [ ] Mã hóa và cấp quyền tối thiểu khi cần.
- [ ] Ghi nhận người nhận và thời hạn lưu.

**Khi có secret bị lộ**

- [ ] Thu hồi hoặc xoay vòng credential ngay.
- [ ] Kiểm tra log sử dụng và xác định phạm vi phát tán.
- [ ] Bảo toàn bằng chứng theo quy trình.
- [ ] Lập kế hoạch rewrite lịch sử nếu cần.
- [ ] Xử lý clone, fork, bundle, patch, cache, artifact và backup.
- [ ] Xác minh secret cũ không còn được sử dụng.

**Sau khi chia sẻ**

- [ ] Thu hồi quyền truy cập khi hết mục đích.
- [ ] Xóa bản sao theo chính sách retention.
- [ ] Ghi nhận việc xử lý và ngoại lệ nếu có.
- [ ] Cập nhật quy trình để ngăn sự cố lặp lại.

## 15. Kết luận

Git log, patch, clone, mirror, bundle và archive đều có thể chứa dữ liệu riêng. Mức độ nhạy cảm phụ thuộc vào commit, ref, file và metadata được đưa vào, vì vậy hãy kiểm tra đầu ra trước khi chia sẻ và chỉ cung cấp phần cần thiết cho mục đích cụ thể.

Nếu secret đã xuất hiện trong lịch sử hoặc bản sao, thu hồi credential trước, xác định nơi dữ liệu đã được phát tán, rồi phối hợp xử lý lịch sử và các bản sao liên quan. .gitignore hoặc một lần xóa file không thể thu hồi dữ liệu đã được clone hay tải xuống. Bảo vệ repository cần bao gồm cả dữ liệu nguồn, đầu ra hỗ trợ, backup, quyền truy cập và thời hạn lưu trữ.
