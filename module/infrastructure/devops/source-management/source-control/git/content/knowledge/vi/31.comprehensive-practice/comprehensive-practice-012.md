# Diễn tập sự cố bí mật bị commit và phối hợp thu hồi, làm sạch lịch sử

Một developer vô tình commit file cấu hình chứa API token vào nhánh tính năng, sau đó push lên remote và mở pull request. Token xuất hiện trong lịch sử commit và có thể đã được máy chủ Git, CI, reviewer, fork hoặc clone của thành viên khác tải xuống. Xóa file ở commit mới nhất không loại token khỏi các commit cũ; viết lại lịch sử cũng không làm token mất hiệu lực và không tự xóa những bản sao đã được tạo.

Bài thực hành này mô phỏng cách nhóm xử lý sự cố từ lúc phát hiện tới khi đóng sự cố: cô lập nguy cơ, thu hồi secret tại hệ thống phát hành, xác định phạm vi lộ lọt, làm sạch lịch sử bằng công cụ chuyên dụng, cập nhật remote và phối hợp đồng bộ các bản sao. Trọng tâm là thứ tự hành động và trách nhiệm giữa developer, người quản trị repository, chủ sở hữu secret và đội vận hành CI/CD.

Trong dịch vụ quản lý mã nguồn Git, bảo vệ lịch sử chỉ là một phần của phản ứng sự cố. Secret cần được thu hồi hoặc thay thế tại nơi phát hành trước khi làm sạch Git. Các bản sao cũ, log, artifact và cache phải được xử lý riêng theo chính sách bảo mật của tổ chức.

## 1. Mục tiêu của buổi diễn tập

Sau bài thực hành, nhóm có thể:

- Nhận diện một secret bị commit và đánh giá nó đã được push hay chưa.
- Cô lập nguy cơ và thu hồi credential tại hệ thống phát hành.
- Ghi nhận bằng chứng cần thiết mà không sao chép secret vào ticket hoặc log.
- Xác định commit, branch, tag, pull request và hệ thống có thể chứa secret.
- Dùng `git filter-repo` để loại đường dẫn hoặc thay thế nội dung trong lịch sử.
- Kiểm tra lịch sử mới trước khi cập nhật remote.
- Phối hợp force update branch/tag, xử lý ref do nền tảng quản lý và hướng dẫn thành viên đồng bộ clone.
- Làm sạch CI workspace, cache, artifact, fork và LFS theo đúng phạm vi.
- Xác minh sự cố đã được khống chế và lập hồ sơ đóng sự cố.

## 2. Kịch bản giả lập

Một developer thêm file `config/production.env` để chạy ứng dụng local. File có chứa API token dùng để gọi dịch vụ thanh toán. Developer commit file này cùng một thay đổi tính năng:

```text
A --- B --- C --- D  feature/payment
                  ^
                  D chứa config/production.env
```

Sau đó nhánh được push lên remote và pull request được mở. CI đã chạy trên commit D; một reviewer đã fetch branch; một thành viên khác có thể đã clone repository.

Thông tin giả lập của sự cố:

| Thuộc tính | Giá trị giả lập |
| --- | --- |
| Repository | `team/payment-service` |
| Nhánh | `feature/payment` |
| File bị lộ | `config/production.env` |
| Loại secret | API token có quyền gọi dịch vụ thanh toán |
| Commit phát hiện | `D` |
| Trạng thái | Đã push lên remote, pull request đang mở |
| Hệ thống liên quan | Secret provider, Git host, CI, developer clone, pull request |

Toàn bộ tên repository, file và mã commit trong bài chỉ là ví dụ. Không đưa token thật vào nội dung thực hành, ảnh chụp màn hình, chat, lệnh shell hoặc file hướng dẫn.

## 3. Nguyên tắc phản ứng sự cố

**Thu hồi hoặc vô hiệu hóa secret trước khi viết lại lịch sử.** Nếu token còn hiệu lực, người có bản sao commit cũ vẫn có thể sử dụng nó. Làm sạch Git có thể mất thời gian và không thể thu hồi credential ở nhà cung cấp.

Các nguyên tắc cần tuân thủ:

1. Coi secret đã push tới remote là có khả năng bị lộ, kể cả khi repository là private.
2. Không chờ xác minh có người dùng token trái phép mới thu hồi token.
3. Không paste secret vào issue, chat, email, terminal output hoặc báo cáo sự cố.
4. Không force push ngay khi chưa kiểm kê refs và chưa thông báo đóng băng ghi.
5. Giữ bằng chứng audit cần thiết trong vùng hạn chế truy cập; không nhân bản secret vào nhiều bản backup thông thường.
6. Không cho phép clone cũ hoặc pipeline cũ đẩy lịch sử trước khi rewrite trở lại remote.
7. Xử lý riêng các bản sao ngoài Git như CI logs, artifact, fork, cache và LFS.

Viết lại lịch sử làm thay đổi commit ID. Nó không thay thế quy trình quản lý secret, điều tra truy cập hoặc thông báo sự cố theo chính sách tổ chức.

## 4. Phân vai trong buổi diễn tập

| Vai trò | Trách nhiệm |
| --- | --- |
| Người phát hiện | Báo sự cố qua kênh bảo mật, cung cấp repository, commit và đường dẫn bị ảnh hưởng; không chia sẻ giá trị secret |
| Incident commander / người điều phối | Xác định mức độ, phân công, quyết định thời điểm đóng băng và mở lại ghi |
| Chủ sở hữu secret / service owner | Thu hồi token cũ, phát hành credential mới, kiểm tra log truy cập và phạm vi quyền |
| Repository maintainer | Kiểm kê refs, backup, chạy filter, xác minh và cập nhật remote |
| CI/CD owner | Xoay vòng secret trong pipeline, dừng job có quyền ghi, xóa workspace/cache/artifact theo chính sách |
| Developer và reviewer | Dừng push, bảo vệ thay đổi local, clone lại hoặc chuyển phần công việc đã được kiểm tra |
| Security / platform team | Kiểm tra audit log, fork, ref ẩn, cache máy chủ và các bản sao không do developer quản lý |

Một người có thể đảm nhận nhiều vai trò trong nhóm nhỏ, nhưng phải xác định rõ ai chịu trách nhiệm thu hồi secret và ai được phép cập nhật remote.

## 5. Giai đoạn 1 — Tiếp nhận và cô lập sự cố

Ngay khi phát hiện:

1. Ghi nhận thời điểm phát hiện và người báo cáo.
2. Xác định repository, branch, commit và đường dẫn có thể chứa secret.
3. Báo cho incident commander và chủ sở hữu secret qua kênh được phê duyệt.
4. Tạm dừng job hoặc workflow có khả năng sử dụng credential bị lộ.
5. Yêu cầu nhóm tạm dừng push, merge, tạo tag và cập nhật branch liên quan trong cửa sổ xử lý.
6. Hạn chế quyền truy cập repository nếu đánh giá rủi ro yêu cầu; việc này do repository/security owner thực hiện theo chính sách.

Không xóa repository, branch hoặc pull request ngay khi phát hiện. Trước tiên cần giữ lại metadata và audit evidence cần thiết để điều tra, đồng thời tránh sao chép nội dung secret ra ngoài phạm vi kiểm soát.

### Thông tin cần ghi nhận

- URL repository và tên nhánh.
- Commit ID nghi ngờ chứa secret.
- Đường dẫn file và loại credential.
- Thời điểm commit, push và thời điểm phát hiện.
- Pull request, pipeline run và artifact liên quan.
- Người hoặc hệ thống có quyền truy cập trong khoảng thời gian bị ảnh hưởng.

Không ghi giá trị token, mật khẩu hoặc private key vào incident ticket. Nếu cần đối chiếu secret, dùng fingerprint hoặc định danh do secret provider cung cấp, theo quy trình bảo mật nội bộ.

## 6. Giai đoạn 2 — Thu hồi và thay thế secret

Chủ sở hữu secret thực hiện thu hồi ở nơi phát hành credential. Ví dụ:

| Loại secret | Hành động khống chế |
| --- | --- |
| Personal access token / API token | Revoke token cũ; tạo token mới với quyền tối thiểu nếu ứng dụng còn cần |
| Mật khẩu database | Đổi mật khẩu, kiểm tra user/service account và connection pool |
| Private key | Thu hồi hoặc thay key/certificate tương ứng; cập nhật hệ thống xác thực |
| OAuth refresh token | Revoke token/session liên quan và xác thực lại ứng dụng |
| Cloud access key | Disable key cũ, tạo identity/key mới hoặc chuyển sang identity ngắn hạn |
| Signing key | Thực hiện quy trình key compromise, thu hồi chứng thư hoặc thay khóa theo chính sách phát hành |

Quy trình tổng quát:

1. Xác định owner và nơi phát hành secret.
2. Vô hiệu hóa secret cũ ngay khi đủ thông tin để định danh.
3. Kiểm tra audit log của provider trong khoảng thời gian credential có thể đã bị lộ.
4. Xác định quyền và tài nguyên token có thể truy cập.
5. Tạo credential thay thế với quyền nhỏ nhất và thời hạn phù hợp.
6. Cập nhật secret store, deployment và ứng dụng được phép sử dụng credential mới.
7. Kiểm tra ứng dụng hoạt động với credential mới.
8. Xác nhận credential cũ không còn dùng được.

Không chép token mới vào file cấu hình được commit. Dùng secret manager hoặc cơ chế cấp credential được tổ chức phê duyệt.

### Kiểm tra dấu hiệu sử dụng trái phép

Chủ sở hữu dịch vụ cần xem audit log để tìm:

- Đăng nhập hoặc API call từ địa chỉ, thiết bị hay khu vực bất thường.
- Truy cập repository, package, dữ liệu hoặc tài nguyên ngoài nhu cầu.
- Thay đổi quyền, tạo credential mới hoặc thao tác quản trị không mong đợi.
- Hoạt động xảy ra sau thời điểm commit/push và trước khi token bị thu hồi.

Không giả định rằng không có audit event nghĩa là token chưa bị sử dụng. Khả năng ghi log phụ thuộc dịch vụ và thời hạn lưu log.

## 7. Giai đoạn 3 — Xác định phạm vi secret trong Git

Sau khi credential đã được thu hồi hoặc vô hiệu hóa, repository maintainer xác định phạm vi lịch sử cần làm sạch.

### Kiểm tra trạng thái hiện tại

Trong clone phục vụ điều tra:

```bash
git status -sb
git branch -a
git tag --list
git log --all --oneline --decorate -- config/production.env
```

Các lệnh này cho biết trạng thái working tree, branch/tag local và các commit có thay đổi đường dẫn được chỉ định. `git log --all -- <path>` không tự chứng minh mọi bản sao hoặc ref ẩn của máy chủ đều sạch; nó chỉ xét refs mà clone hiện tại biết tới.

### Kiểm kê refs

```bash
git show-ref
git for-each-ref --format='%(refname) %(objectname)'
```

Ghi nhận branch và tag được quảng bá. Với pull request refs, fork hoặc ref nội bộ của Git host, cần kiểm tra bằng công cụ quản trị hoặc nhờ platform owner vì clone thông thường có thể không tải được mọi ref.

### Tìm các đường dẫn cũ

Nếu file từng được đổi tên hoặc di chuyển, liệt kê tất cả đường dẫn có thể chứa secret. Ví dụ:

```text
config/production.env
deploy/legacy/production.env
ops/credentials/payment.env
```

Chỉ lọc đường dẫn hiện tại có thể bỏ sót bản cũ ở đường dẫn trước đó. Kiểm tra lịch sử rename và commit liên quan, nhưng không in giá trị secret ra output.

### Xác định nội dung ngoài file

Secret có thể đã được commit trong:

- File cấu hình hoặc source code.
- Commit message hoặc annotated tag message.
- Script, fixture, tài liệu hoặc file mẫu.
- Log và file output do CI sinh ra.
- File nhị phân hoặc LFS object.

Nếu secret xuất hiện trong nội dung blob ở nhiều file, cần dùng secret scanner hoặc quy tắc thay thế nội dung trên toàn bộ lịch sử. Nếu secret chỉ nằm trong một file riêng, lọc đường dẫn có thể là cách rõ ràng hơn.

## 8. Giai đoạn 4 — Đóng băng thao tác ghi và tạo bản làm việc riêng

Trước khi viết lại lịch sử:

- Thông báo rõ thời gian bắt đầu và kết thúc cửa sổ bảo trì.
- Tạm dừng push, merge, tạo tag và workflow có quyền ghi.
- Yêu cầu developer không tiếp tục push từ clone cũ.
- Ghi nhận refs hiện tại và commit đầu nhánh cần xử lý.
- Xác nhận ai được phép chạy filter và cập nhật remote.

Tạo mirror clone mới từ remote:

```bash
git clone --mirror https://git.example.com/team/payment-service.git payment-service-rewrite.git
```

Mirror clone là repository bare và phù hợp để làm việc với nhiều branch/tag. Chuyển vào thư mục:

```bash
cd payment-service-rewrite.git
git show-ref
git remote -v
```

`git filter-repo` thường yêu cầu clone mới để tránh viết lại nhầm repository đang có công việc local. Nếu công cụ từ chối do repository không được nhận diện là fresh clone, hãy tạo mirror clone mới thay vì tùy tiện thêm `--force`.

### Bảo vệ bản sao và bằng chứng

Mirror clone trước khi lọc sẽ chứa secret. Nếu cần giữ bản sao để phục vụ điều tra hoặc khôi phục, lưu trong vùng cách ly có mã hóa, quyền truy cập giới hạn và thời hạn lưu rõ ràng. Không dùng nó như clone làm việc hoặc remote thông thường.

Ưu tiên lưu audit metadata, commit ID, ref map và thời gian sự cố theo chính sách. Nếu chính sách yêu cầu loại bỏ mọi bản sao của secret, phối hợp security owner để xử lý backup cũ; không tự giữ một bản backup chứa secret vô thời hạn.

Nếu repository dùng Git LFS, mirror clone Git không bảo đảm đã tải đầy đủ nội dung LFS. Chỉ tải/backup LFS object trong vùng cách ly khi quy trình điều tra yêu cầu và có quyền truy cập phù hợp:

```bash
git lfs fetch --all origin
```

## 9. Giai đoạn 5 — Chọn cách làm sạch lịch sử

Trước khi lọc, chọn đúng phương án:

| Tình huống | Phương án |
| --- | --- |
| Secret chỉ nằm trong một file cấu hình | Loại đường dẫn khỏi toàn bộ lịch sử |
| Secret bị chép vào nhiều file văn bản | Thay thế chuỗi trong lịch sử và kiểm tra bằng scanner |
| File cấu hình cần giữ mẫu nhưng bỏ credential | Thay bằng placeholder an toàn hoặc loại file rồi thêm mẫu mới |
| Secret nằm trong nhiều đường dẫn cũ | Lọc toàn bộ đường dẫn đã từng sử dụng |
| Secret nằm trong LFS object | Làm sạch pointer trong Git và xử lý LFS storage theo quy trình host |
| Secret nằm trong log/artifact ngoài Git | Xóa hoặc hạn chế artifact/log theo quy trình CI và storage |

`git rm` rồi commit chỉ loại file khỏi snapshot mới nhất. `git revert` tạo commit đảo ngược thay đổi, nhưng commit cũ vẫn chứa secret. Để loại nội dung khỏi các commit lịch sử, cần viết lại lịch sử.

## 10. Dùng git-filter-repo để loại file khỏi toàn bộ lịch sử

Giả sử file `config/production.env` chứa secret và không cần giữ bất kỳ phiên bản nào của file đó trong Git. Trong mirror clone mới, chạy:

```bash
git filter-repo --path config/production.env --invert-paths
```

Nếu file từng tồn tại ở nhiều đường dẫn:

```bash
git filter-repo \
  --path config/production.env \
  --path deploy/legacy/production.env \
  --path ops/credentials/payment.env \
  --invert-paths
```

`--invert-paths` đảo phạm vi chọn, tức loại các đường dẫn đã nêu khỏi lịch sử được lọc. Đường dẫn tính từ gốc repository. Hãy kiểm tra mọi tên cũ và mới trước khi chạy.

Nếu muốn giữ một file mẫu không chứa secret, tạo lại file đó sau khi lọc bằng nội dung mẫu đã được review, ví dụ:

```dotenv
PAYMENT_API_TOKEN=
PAYMENT_API_URL=https://api.example.test
```

File mẫu chỉ khai báo tên biến; ứng dụng cần đọc giá trị thật từ secret store hoặc environment được bảo vệ. Không commit token thật.

## 11. Thay thế secret đã xuất hiện trong nhiều file

Nếu token được sao chép vào nhiều file văn bản, `git filter-repo` hỗ trợ `--replace-text`. Tạo file thay thế bên ngoài repository rewrite, ví dụ `../secret-replacements.txt`, theo định dạng:

```text
literal:EXAMPLE_OLD_TOKEN_VALUE==>***REDACTED***
literal:EXAMPLE_OLD_PASSWORD==>***REDACTED***
```

Các chuỗi là placeholder giả lập. Với sự cố thật, file thay thế có thể cần chứa giá trị bí mật để tìm đúng chuỗi; phải tạo và lưu file đó trong vùng hạn chế truy cập, không in nội dung ra terminal hoặc đưa vào repository.

Chạy:

```bash
git filter-repo --replace-text ../secret-replacements.txt
```

Có thể kết hợp lọc đường dẫn và thay thế nội dung khi cần:

```bash
git filter-repo \
  --path config/production.env \
  --invert-paths \
  --replace-text ../secret-replacements.txt
```

`--replace-text` xử lý nội dung blob văn bản; nó không thay thế nội dung commit message hoặc annotated tag message. File biểu thức hỗ trợ các dạng như `literal:`, `regex:` hoặc `glob:` tùy phiên bản công cụ; kiểm tra `git filter-repo --help` trước khi dùng pattern phức tạp. Nếu secret nằm trong message, dùng `--replace-message` với file biểu thức riêng:

```bash
git filter-repo --replace-message ../message-replacements.txt
```

`--replace-message` áp dụng cho commit và tag messages. File biểu thức cần được bảo vệ như file thay thế nội dung nếu có chứa chuỗi secret thật. Nếu secret nằm trong blob nhị phân, `--replace-text` không phải công cụ phù hợp; xác định file chứa dữ liệu và loại đường dẫn hoặc dùng quy trình chuyên dụng cho định dạng đó.

Không đưa secret thật vào tham số dòng lệnh, shell history hoặc lệnh được copy vào ticket. Khi cần file thay thế chứa giá trị thật, bảo vệ file bằng quyền truy cập của hệ điều hành và xóa theo quy trình sau khi hoàn tất.

Thay thế nội dung trong Git không thu hồi token. Secret phải được revoke/rotate tại provider, kể cả khi scanner xác nhận chuỗi không còn trong lịch sử mới.

## 12. Xác minh lịch sử đã làm sạch

Không push ngay sau khi filter kết thúc. Kiểm tra kết quả trong mirror clone trước:

### Kiểm tra đường dẫn

```bash
git log --all --oneline -- config/production.env
git log --all --oneline -- deploy/legacy/production.env
git show-ref
```

Các lệnh log theo đường dẫn không nên còn commit thay đổi những file đã loại trong refs được lọc. Kiểm tra lại danh sách refs để bảo đảm phạm vi xử lý đúng mục tiêu.

### Kiểm tra tính toàn vẹn

```bash
git fsck --full
git count-objects -vH
```

Đọc kết quả `fsck` và xử lý lỗi missing/corrupt object. Cảnh báo dangling/unreachable cần được đánh giá theo trạng thái repository; không nhầm chúng với bằng chứng rằng secret vẫn reachable từ branch/tag.

### Quét secret trên toàn bộ lịch sử

Chạy secret scanner được tổ chức phê duyệt trên repository rewrite và các refs liên quan. Cấu hình scanner để quét lịch sử, branch và tag; quét working tree hiện tại thôi là chưa đủ.

Kết quả báo cáo không được in giá trị secret. Chỉ lưu loại phát hiện, đường dẫn, commit ID và trạng thái xử lý theo định dạng an toàn.

### Kiểm tra commit và ref map

`git filter-repo` có thể tạo metadata như `commit-map` và `ref-map` trong thư mục metadata của công cụ. Các bản đồ này giúp đối chiếu commit/ref cũ với mới và cập nhật liên kết trong hệ thống ngoài Git.

Lưu metadata cần thiết trong hồ sơ sự cố có kiểm soát. Không đưa nội dung bí mật hoặc bản sao lịch sử cũ vào nơi lưu trữ công khai.

### Kiểm tra trạng thái sau filter

```bash
git log --all --oneline --decorate -20
git branch --all
git tag --list
git rev-parse --is-bare-repository
```

Với mirror clone, `git rev-parse --is-bare-repository` xác nhận repository đang ở chế độ bare. Tập trung kiểm tra refs, commit graph, scanner và object database.

## 13. Giai đoạn 6 — Khôi phục remote và cập nhật branch/tag

`git filter-repo` thường xóa remote `origin` khỏi cấu hình để tránh push nhầm lịch sử đã viết lại. Kiểm tra:

```bash
git remote -v
```

Nếu không còn remote, thêm lại URL chính thức:

```bash
git remote add origin https://git.example.com/team/payment-service.git
git remote -v
```

Xác nhận URL đúng repository đích và không chứa username/token.

Chỉ cập nhật remote khi:

- Secret cũ đã được thu hồi hoặc vô hiệu hóa.
- Kết quả filter đã được kiểm tra và scanner xác nhận.
- Backup/evidence được bảo vệ theo chính sách.
- Developer và CI đã được thông báo không push từ clone cũ.
- Repository maintainer được ủy quyền cập nhật refs.

### Cập nhật branch

```bash
git push --force --all origin
```

Lệnh này cập nhật các branch local lên remote. Nó không tự xóa mọi branch remote không còn tồn tại trong local và không xử lý mọi ref ẩn do nền tảng quản lý.

### Cập nhật tag

```bash
git push --force --tags origin
```

Kiểm tra tag phát hành sau rewrite. Annotated tag có thể được tạo lại và chữ ký cũ không còn xác thực cho object mới. Nếu tag cần bị xóa hoàn toàn, xử lý riêng theo tên sau khi được release owner phê duyệt:

```bash
git push origin --delete v2.4.0
```

Không xóa tag release chỉ vì thao tác rewrite; cần xác định chính sách versioning và audit của dự án.

### Ref đặc biệt của Git host

Pull request refs, merge request refs, refs nội bộ hoặc refs do host quản lý có thể không được clone/push như branch thông thường. Repository maintainer cần phối hợp platform owner hoặc support của nhà cung cấp để xử lý cached view, PR refs và các bản sao máy chủ mà người dùng không thể cập nhật.

Tránh dùng `git push --mirror` một cách máy móc trên remote dùng chung. Lệnh mirror có thể xóa refs không tồn tại trong mirror clone, bao gồm refs do nền tảng quản lý. Chọn phạm vi branch/tag và xử lý ref đặc biệt theo hướng dẫn của host.

## 14. Giai đoạn 7 — Đồng bộ clone của developer

Clone cũ vẫn có commit chứa secret. Nếu thành viên tiếp tục push branch cũ, lịch sử cũ có thể được đưa trở lại remote. Vì vậy, cần hướng dẫn mọi người dừng sử dụng clone cũ và chuyển sang lịch sử mới.

### Phương án khuyến nghị: clone lại

1. Lưu phần công việc local chưa được chia sẻ theo quy trình an toàn.
2. Không tạo archive hoặc gửi clone cũ qua chat/email.
3. Di chuyển clone cũ vào vùng cách ly nếu cần điều tra; nếu không cần, xử lý theo chính sách xóa dữ liệu.
4. Clone lại từ remote đã được làm sạch.
5. Kiểm tra branch, tag và scanner trên clone mới.
6. Áp dụng lại các thay đổi local đã được review, bảo đảm patch không chứa secret.
7. Không merge branch cũ vào branch mới vì việc đó có thể nối lịch sử cũ trở lại.

Ví dụ:

```bash
git clone https://git.example.com/team/payment-service.git payment-service-clean
```

### Nếu cần giữ thay đổi local

Không cherry-pick hoặc merge mù quáng commit từ clone cũ. Một commit có thể chứa secret trong diff hoặc trong file không còn thấy ở tip. Hãy xem xét thay đổi cần giữ, loại bỏ secret và áp dụng phần logic hợp lệ lên branch mới bằng patch đã kiểm tra hoặc chỉnh sửa lại thủ công.

Nếu dùng cherry-pick, chỉ chọn commit đã được xác minh không đưa secret hoặc parent history cũ trở lại. Cherry-pick tạo commit mới trên lịch sử hiện tại nhưng vẫn có thể áp dụng lại nội dung bí mật nếu diff của commit chứa nó.

### Không push clone cũ

Thông báo rõ:

- Không push branch cũ.
- Không mở lại PR từ commit cũ.
- Không merge branch backup chứa secret vào branch đã làm sạch.
- Không dùng tag cũ trỏ tới commit trước rewrite.
- Báo maintainer nếu phát hiện remote có commit cũ xuất hiện trở lại.

## 15. Giai đoạn 8 — Làm sạch CI/CD, fork và artifact

Git remote không phải nơi duy nhất lưu nội dung commit. CI và các hệ thống phụ trợ có thể giữ snapshot cũ.

### CI/CD

CI owner cần:

1. Revoke/rotate credential được lưu trong secret store của pipeline.
2. Dừng job cũ có khả năng push hoặc publish.
3. Xóa workspace/cache Git theo quy trình runner.
4. Kiểm tra log, test report, artifact và build output có thể chứa secret.
5. Xóa hoặc hạn chế truy cập artifact/log theo chính sách retention.
6. Clone/fetch lại từ lịch sử mới.
7. Kiểm tra job mới không sử dụng credential cũ và không push ref cũ.

Không bật debug logging hoặc in biến môi trường để xác minh secret. Dùng trạng thái secret provider và cơ chế kiểm tra được phê duyệt.

### Fork và pull request

Fork có thể vẫn giữ commit cũ. Chủ sở hữu fork và platform owner cần phối hợp đồng bộ hoặc xóa fork theo chính sách. Pull request có thể lưu diff, comment, patch hoặc ref nội bộ; rewrite branch không bảo đảm xóa mọi bản sao PR.

Kiểm tra:

- Fork thuộc tổ chức và fork cá nhân có quyền truy cập.
- PR/MR đang mở hoặc đã đóng.
- Patch download, review bundle và liên kết commit.
- Cache hoặc trang diff được host giữ lại.

Nếu người dùng không có quyền xóa ref/cache, chuyển yêu cầu tới quản trị nền tảng hoặc support của nhà cung cấp.

### Git LFS và artifact storage

Nếu file chứa secret được theo dõi bằng Git LFS, filter pointer trong Git không tự xóa object nhị phân khỏi LFS server. Cần xác định OID và làm theo quy trình xóa/purge của nhà cung cấp sau khi bảo đảm không còn phiên bản hợp lệ cần giữ.

Nếu file được publish thành package, release asset, container image hoặc artifact CI, xử lý chúng trong hệ thống tương ứng. Xóa commit không tự xóa package hoặc image đã phát hành.

## 16. Giai đoạn 9 — Kiểm tra remote sau khi cập nhật

Sau khi force update refs, tạo một clone mới độc lập từ remote:

```bash
git clone https://git.example.com/team/payment-service.git payment-service-verify
cd payment-service-verify
git show-ref
git log --all --oneline --decorate -20
```

Chạy secret scanner trên toàn bộ lịch sử được clone. Xác minh:

- File hoặc chuỗi nhạy cảm không còn trong branch/tag được quảng bá.
- Branch và tag mong muốn đã trỏ tới commit mới.
- Pull request và ref đặc biệt đã được xử lý theo quy trình host.
- Không có developer hoặc pipeline nào push lại commit cũ.
- CI mới chạy thành công với credential đã rotate.
- Ứng dụng dùng secret mới từ secret store.

Theo dõi remote trong khoảng thời gian sau mở lại ghi. Nếu commit cũ xuất hiện lại, tạm dừng push, xác định actor/ref nguồn và lặp lại quy trình xử lý từ nguồn phát sinh.

## 17. Bảo vệ backup và xử lý bản sao chứa secret

Backup trước rewrite có thể chứa secret đã thu hồi. Cần phân loại:

| Bản sao | Cách xử lý |
| --- | --- |
| Mirror backup phục vụ điều tra | Cách ly, mã hóa, giới hạn người truy cập và đặt hạn xóa |
| Clone local của developer | Clone lại; xóa hoặc cách ly clone cũ theo chính sách |
| CI workspace/cache | Xóa workspace/cache cũ và cấp credential mới |
| Log/artifact | Xác định phạm vi lộ, hạn chế truy cập hoặc xóa theo retention |
| Fork | Phối hợp owner/platform để đồng bộ hoặc xóa |
| LFS object | Dùng quy trình purge LFS của host |
| Release/package/container image | Thu hồi hoặc thay thế artifact theo quy trình phát hành |

Không giữ một bản backup chứa secret vô thời hạn chỉ vì có thể cần rollback. Nếu cần bảo toàn bằng chứng, ưu tiên audit metadata và bản sao cách ly có kiểm soát; quyết định lưu hoặc hủy nội dung nhạy cảm phải theo incident commander và security owner.

## 18. Kịch bản phối hợp theo mốc thời gian

| Mốc | Người chịu trách nhiệm | Hành động | Bằng chứng hoàn tất |
| --- | --- | --- | --- |
| T0 — Phát hiện | Developer | Báo repository, commit, file và loại secret qua kênh bảo mật | Ticket có metadata, không chứa giá trị secret |
| T0+ | Secret owner | Revoke token cũ, kiểm tra audit, tạo credential mới nếu cần | Provider xác nhận token cũ không còn hiệu lực |
| T1 | Incident commander | Đóng băng push/merge và phân công owner | Thông báo maintenance được gửi |
| T1 | Repository maintainer | Kiểm kê refs, PR, tag và phạm vi đường dẫn | Danh sách refs và commit liên quan |
| T2 | Repository maintainer | Backup cách ly, chạy filter trong mirror clone | Commit map/ref map và log thao tác |
| T2 | Security owner | Quét lịch sử mới | Kết quả scanner không còn phát hiện cần xử lý |
| T3 | Repository maintainer | Force update branch/tag được duyệt | Remote refs trỏ tới lịch sử mới |
| T3+ | Platform/CI owner | Xử lý PR refs, cache, CI, LFS và artifact | Xác nhận hệ thống phụ trợ đã xử lý |
| T4 | Developer | Clone lại, áp dụng thay đổi local đã kiểm tra | Developer xác nhận dùng lịch sử mới |
| T5 | Incident commander | Mở lại ghi, theo dõi và đóng sự cố | Biên bản xác minh và hành động phòng ngừa |

Các mốc là thứ tự phối hợp, không phải SLA. Sự cố nghiêm trọng có thể cần đóng băng lâu hơn hoặc yêu cầu quy trình ứng phó riêng.

## 19. Mẫu thông báo nội bộ không chứa secret

Khi thông báo cho nhóm, chỉ nêu thông tin cần thiết:

```text
Tiêu đề: Tạm dừng push vào payment-service để xử lý sự cố credential

Một credential đã xuất hiện trong lịch sử Git của nhánh feature/payment.
Credential cũ đang được thu hồi/đã được thu hồi bởi service owner.

Trong cửa sổ xử lý:
- Tạm dừng push, merge và tạo tag vào repository.
- Không tiếp tục sử dụng clone cũ để push.
- Không sao chép hoặc gửi file cấu hình nghi ngờ qua chat/email.
- Chờ hướng dẫn clone lại sau khi maintainer xác nhận lịch sử mới.

Repository maintainer sẽ thông báo khi remote và CI đã được xác minh.
Nếu bạn có thay đổi local chưa push, hãy giữ nguyên tại máy và liên hệ
maintainer để chuyển phần công việc đã được kiểm tra.
```

Không đính kèm token, file cấu hình, ảnh chụp màn hình có credential hoặc bản diff chứa secret.

## 20. Lỗi thường gặp trong xử lý sự cố

| Sai lầm | Vì sao không đủ hoặc nguy hiểm | Cách xử lý đúng |
| --- | --- | --- |
| Chỉ xóa file trong commit mới nhất | Commit cũ vẫn chứa blob | Thu hồi secret và rewrite toàn bộ lịch sử liên quan |
| Revert commit đã lộ token | Commit cũ vẫn reachable trong history | Revoke token; dùng filter chuyên dụng khi cần loại khỏi history |
| Rewrite history trước khi revoke token | Token vẫn có thể được sử dụng trong lúc xử lý | Revoke/disable ngay ở provider trước |
| Chỉ quét working tree hiện tại | Secret có thể còn trong commit cũ hoặc tag | Quét toàn bộ lịch sử và refs được quảng bá |
| Chỉ lọc tên file hiện tại | Bản cũ có thể nằm ở đường dẫn trước khi rename | Liệt kê mọi đường dẫn lịch sử |
| Push force ngay sau filter | Có thể bỏ sót ref, ghi đè commit mới hoặc xóa ref host | Đóng băng ghi, kiểm kê và cập nhật refs theo kế hoạch |
| Dùng `--mirror` mà không kiểm tra | Có thể xóa ref đặc biệt trên remote | Push branch/tag có phạm vi rõ và nhờ platform owner xử lý ref ẩn |
| Cho developer tiếp tục dùng clone cũ | Commit cũ có thể được push trở lại | Yêu cầu clone lại hoặc chuyển patch đã kiểm tra |
| Quên CI cache và artifact | Secret vẫn còn ở nơi ngoài Git | Xử lý workspace, log, artifact và secret store riêng |
| Cho rằng xóa LFS pointer là xóa LFS object | Binary vẫn có thể còn trên LFS server | Thực hiện quy trình purge LFS của host |
| Lưu backup chứa secret ở nơi thường | Tạo thêm bản sao có nguy cơ lộ | Cách ly, mã hóa, giới hạn quyền và đặt retention |

## 21. Checklist đóng sự cố

### Credential

- [ ] Secret cũ đã bị revoke/disable.
- [ ] Credential thay thế đã được phát hành với quyền tối thiểu.
- [ ] Ứng dụng và pipeline đã chuyển sang credential mới.
- [ ] Audit log đã được kiểm tra theo phạm vi có thể.

### Git history

- [ ] Đã kiểm kê branch, tag và ref liên quan.
- [ ] Đã lọc mọi đường dẫn cũ/mới hoặc nội dung secret đã xác định.
- [ ] Secret scanner đã quét toàn bộ lịch sử mới.
- [ ] `git fsck --full` không có lỗi object missing/corrupt.
- [ ] Branch/tag remote đã được cập nhật theo kế hoạch.
- [ ] Ref ẩn và pull request refs đã được platform owner xử lý.

### Bản sao và hệ thống phụ trợ

- [ ] Developer đã clone lại hoặc đồng bộ theo hướng dẫn.
- [ ] Không còn clone cũ được phép push.
- [ ] CI workspace/cache và credential đã được xử lý.
- [ ] Log, artifact, release, package và container image đã được đánh giá.
- [ ] Fork và LFS object đã có kết quả xử lý.
- [ ] Backup cũ được cách ly hoặc hủy theo chính sách.

### Theo dõi và phòng ngừa

- [ ] Repository đã mở lại ghi sau khi owner xác nhận.
- [ ] Theo dõi việc commit cũ có xuất hiện lại hay không.
- [ ] Đã bật hoặc điều chỉnh secret scanning/pre-commit controls.
- [ ] Đã cập nhật hướng dẫn dùng secret manager và file mẫu.
- [ ] Đã ghi lại bài học và owner của hành động phòng ngừa.

## 22. Thực hành trên repository giả lập

Chỉ dùng token giả, không dùng credential thật hoặc dữ liệu production.

### Giai đoạn A — Tạo sự cố

1. Tạo repository thử nghiệm với một file `config/demo.env`.
2. Đưa một chuỗi giả như `DEMO_TOKEN_DO_NOT_USE` vào file.
3. Commit file và thực hiện thêm một commit khác.
4. Tạo branch/tag thử nghiệm và push lên remote do bạn kiểm soát.
5. Ghi lại commit ID, branch và tag có chứa file.

### Giai đoạn B — Thu hồi giả lập và lập phạm vi

1. Đóng băng thao tác ghi trên remote thử nghiệm.
2. Ghi nhận refs bằng `git show-ref`.
3. Kiểm tra lịch sử file bằng `git log --all -- config/demo.env`.
4. Xác định mọi đường dẫn cũ nếu file được rename.
5. Ghi nhận metadata sự cố mà không đưa chuỗi giả vào ticket công khai.

### Giai đoạn C — Làm sạch

1. Tạo mirror clone mới.
2. Chạy `git filter-repo --analyze` nếu cần.
3. Dùng `git filter-repo --path config/demo.env --invert-paths`.
4. Kiểm tra refs và lịch sử sau lọc.
5. Chạy scanner thử nghiệm hoặc kiểm tra đường dẫn trên mọi refs.
6. Thêm lại remote chính thức của môi trường lab.
7. Force update branch/tag trên remote thử nghiệm.

### Giai đoạn D — Đồng bộ và xác minh

1. Clone lại remote vào một thư mục mới.
2. Xác nhận file demo không còn trong lịch sử mới.
3. Mô phỏng developer có clone cũ và giải thích vì sao không được push clone đó.
4. Thử chuyển một thay đổi hợp lệ sang clone mới bằng patch đã review.
5. Ghi checklist đóng sự cố và các hệ thống ngoài Git cần xử lý.

Không thực hiện force push lên repository dùng chung hoặc production trong bài lab.

## 23. Tự kiểm tra kiến thức

1. Vì sao phải thu hồi token trước khi viết lại Git history?
2. Vì sao repository private vẫn phải coi token đã push là có khả năng bị lộ?
3. `git rm` và `git revert` có loại secret khỏi commit cũ không?
4. Khi nào nên dùng `--path ... --invert-paths` và khi nào cần `--replace-text`?
5. Vì sao phải kiểm tra mọi đường dẫn cũ sau khi file được rename?
6. Vì sao mirror clone backup trước rewrite cần được cách ly?
7. `git push --force --all` và `git push --force --tags` cập nhật những ref nào?
8. Vì sao không nên dùng `git push --mirror` một cách máy móc trên Git host?
9. Những hệ thống nào có thể giữ secret ngoài Git object database?
10. Vì sao developer nên clone lại thay vì merge branch cũ vào lịch sử mới?
11. Secret scanner cần quét phạm vi nào để xác minh kết quả?
12. Điều kiện nào cần đạt trước khi mở lại quyền push?

## Kết luận

Khi secret bị commit và push, hãy xử lý như một sự cố credential: cô lập nguy cơ, thu hồi hoặc vô hiệu hóa secret tại provider, kiểm tra audit log, rồi mới làm sạch Git history. Dùng `git filter-repo` trong mirror clone riêng để loại đường dẫn hoặc thay nội dung, quét toàn bộ lịch sử và xác minh refs trước khi cập nhật remote. Sau rewrite, phối hợp developer clone lại, làm sạch CI/cache/artifact/fork/LFS và ngăn clone cũ đẩy commit cũ trở lại. Chỉ đóng sự cố khi credential cũ đã vô hiệu, lịch sử mới đã được xác minh và các bản sao ngoài Git đã có owner cùng kết quả xử lý.
