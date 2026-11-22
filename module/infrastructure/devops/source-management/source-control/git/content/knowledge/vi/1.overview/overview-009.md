# Giới hạn của Git đối với triển khai, sao lưu và quản lý bí mật

Git là hệ thống quản lý phiên bản phân tán. Nó ghi lại các phiên bản của tệp, tổ chức lịch sử bằng commit, và hỗ trợ nhiều người cộng tác qua branch, merge, rebase, remote và tag. Nhờ vậy, nhóm phát triển có thể biết thay đổi nào đã xảy ra, ai tạo ra thay đổi, thay đổi dựa trên phiên bản nào và có thể quay lại một mốc mã nguồn trước đó.

Tuy nhiên, quản lý phiên bản chỉ là một phần của vòng đời phần mềm. Một commit không tự biến thành một bản phát hành đã được triển khai an toàn; một remote không tự trở thành hệ thống sao lưu thảm họa; và một tệp bị xóa khỏi working tree không có nghĩa bí mật đã biến mất khỏi lịch sử. Muốn vận hành phần mềm đáng tin cậy, cần hiểu ranh giới của Git và kết hợp nó với hệ thống triển khai, sao lưu và quản lý bí mật phù hợp.

## 1. Git giải quyết vấn đề nào?

Git quản lý nội dung nằm trong repository. Khi tạo commit, Git lưu một mốc trạng thái của các tệp được theo dõi cùng thông tin tác giả, thời điểm, thông điệp và commit cha. Các branch và tag là những tham chiếu giúp con người đặt tên cho các mốc commit. Remote cho phép trao đổi commit và tham chiếu giữa các repository.

Git có thể lưu mã nguồn, tài liệu, cấu hình, script triển khai và định nghĩa hạ tầng dưới dạng văn bản. Lịch sử đó rất hữu ích để review, truy vết và tái tạo trạng thái mã nguồn tại một commit cụ thể.

Git không trực tiếp quản lý toàn bộ hệ thống chạy phần mềm. Nó không tự biết máy chủ đang có cấu hình gì, dịch vụ nào đang chạy, cơ sở dữ liệu đã được migration đến đâu, bản build nào đang phục vụ người dùng hay một lần phát hành có vượt qua kiểm tra sức khỏe hay không. Git cũng không tự cung cấp kho lưu trữ bản build, bản sao lưu độc lập hoặc kho bí mật có kiểm soát truy cập.

Có thể phân biệt ba câu hỏi:

- **Quản lý phiên bản:** Mã nguồn và cấu hình đã thay đổi như thế nào? Git trả lời tốt câu hỏi này.
- **Triển khai:** Phiên bản nào được đóng gói, đưa đến môi trường nào và có hoạt động đúng hay không? Cần thêm CI/CD, công cụ phát hành và cơ chế giám sát.
- **Bảo vệ dữ liệu và bí mật:** Có thể phục hồi sau sự cố không, và thông tin xác thực có được bảo vệ không? Cần hệ thống backup và secret manager riêng.

## 2. Giới hạn của Git trong triển khai phần mềm

### 2.1. Commit không phải là một bản phát hành hoàn chỉnh

Một commit xác định nội dung repository tại một thời điểm. Nó không đảm bảo rằng mã nguồn có thể build thành công hoặc chạy giống nhau ở mọi môi trường. Kết quả build còn phụ thuộc vào nhiều yếu tố khác:

- Phiên bản compiler, runtime, SDK và công cụ build.
- Dependency được tải về, phiên bản thực tế và tính sẵn có của registry.
- Biến môi trường, cấu hình theo từng môi trường và quyền truy cập dịch vụ.
- Hệ điều hành, kiến trúc CPU, thư viện hệ thống và các dịch vụ bên ngoài.
- Dữ liệu, trạng thái cơ sở dữ liệu và thứ tự thực hiện migration.

Nếu hai máy checkout cùng một commit nhưng dùng dependency hoặc môi trường build khác nhau, kết quả có thể khác nhau. Git chỉ ghi lại những tệp đã được commit; nó không tự khóa toàn bộ môi trường thực thi. Vì vậy, dự án nên quản lý dependency bằng lockfile, chuẩn hóa môi trường build, ghi lại phiên bản công cụ và kiểm tra build trong CI.

Một quy trình phát hành tốt thường build một lần, lưu artifact cùng mã định danh hoặc checksum, rồi triển khai chính artifact đó qua các môi trường. Cách này giúp tránh tình trạng build lại ở production tạo ra một gói khác với gói đã kiểm thử.

### 2.2. Git không điều phối việc triển khai

Các lệnh như checkout, pull và merge thay đổi nội dung repository. Chúng không tự thực hiện đầy đủ các bước phát hành như:

1. Kiểm tra chất lượng và chạy test.
2. Build, đóng gói và lưu artifact.
3. Cấp cấu hình và bí mật đúng cho môi trường đích.
4. Cập nhật dịch vụ theo chiến lược rolling, blue-green hoặc canary.
5. Kiểm tra health check, log, metric và lỗi sau triển khai.
6. Dừng rollout hoặc rollback khi có sự cố.

Chạy git pull trực tiếp trên máy production có thể là một lựa chọn trong môi trường rất đơn giản, nhưng bản thân lệnh này không phải một quy trình triển khai an toàn. Nó không đảm bảo dependency đã được cài đúng, build đã hoàn tất, tiến trình đã khởi động lại, nhiều máy được cập nhật đồng bộ hay phiên bản mới tương thích với schema cơ sở dữ liệu. Nếu một bước giữa chừng thất bại, hệ thống có thể ở trạng thái nửa cũ nửa mới.

Nên để pipeline CI/CD hoặc nền tảng triển khai thực hiện các bước này. Git cung cấp mã nguồn và mốc phiên bản làm đầu vào; pipeline chịu trách nhiệm kiểm thử, build, phát hành và ghi nhận kết quả.

### 2.3. Branch và tag không tự bảo đảm phiên bản đang chạy

Tên branch như main là một tham chiếu có thể tiến lên commit mới. Nếu triển khai từ đầu branch vào những thời điểm khác nhau, mỗi lần có thể lấy một commit khác nhau. Tag cũng là tham chiếu có tên; tùy quyền hạn và chính sách của máy chủ, tag có thể bị xóa hoặc di chuyển.

Khi phát hành, nên ghi lại commit SHA cụ thể, phiên bản artifact và môi trường đích. Không nên chỉ ghi “đã triển khai main” vì tên branch không mô tả chính xác nội dung đã chạy. Có thể tạo tag cho phiên bản phát hành, bảo vệ tag trên máy chủ và ký tag nếu quy trình yêu cầu xác minh nguồn gốc.

Ví dụ tạo và kiểm tra một tag có chữ ký:

~~~
git tag -s v1.4.0 -m "Release v1.4.0"
git tag -v v1.4.0
git rev-parse "v1.4.0^{commit}"
~~~

Tag có chữ ký giúp người nhận kiểm tra chữ ký của tag theo khóa tin cậy đã cấu hình. Nó không thay thế việc bảo vệ quyền ghi tag, kiểm tra pipeline hay xác minh artifact. Pipeline vẫn nên ghi lại commit SHA và checksum của gói được triển khai.

### 2.4. Git không quản lý trạng thái thực tế của môi trường

Một repository có thể chứa Terraform, manifest Kubernetes, file cấu hình hoặc script triển khai. Những tệp này mô tả trạng thái mong muốn, nhưng trạng thái thực tế có thể khác do thao tác thủ công, lỗi mạng, quyền thiếu, tài nguyên được tạo ngoài quy trình hoặc một lần triển khai thất bại.

Git không tự phát hiện và sửa mọi sai lệch đó. Với mô hình GitOps, Git lưu cấu hình mong muốn còn một bộ điều khiển như Argo CD hoặc Flux theo dõi repository, đối chiếu với cluster và thực hiện đồng bộ. Bộ điều khiển, nền tảng chạy ứng dụng và hệ thống quan sát vẫn là các thành phần riêng.

Việc rollback mã nguồn cũng không đồng nghĩa rollback toàn bộ hệ thống. Một migration cơ sở dữ liệu có thể đã xóa hoặc chuyển đổi dữ liệu theo cách không thể đảo ngược. Một dịch vụ bên ngoài có thể đã nhận sự kiện hoặc giao dịch. Vì vậy, cần thiết kế migration tương thích ngược, có kế hoạch phục hồi dữ liệu và kiểm tra hành vi sau rollback.

## 3. Giới hạn của Git trong sao lưu và phục hồi

### 3.1. Repository chỉ bao gồm những gì đã được đưa vào lịch sử

Git chủ yếu bảo vệ các nội dung đã được commit và còn có thể truy cập thông qua các tham chiếu hoặc object trong repository. Một bản sao repository không tự bao gồm:

- Thay đổi chưa commit trong working tree hoặc staging area.
- Tệp chưa được theo dõi, tệp bị bỏ qua bởi .gitignore và dữ liệu nằm ngoài repository.
- Artifact build, dữ liệu runtime, database, volume, file upload hoặc object storage.
- Nội dung thực tế của Git LFS nếu chỉ sao chép phần repository chứa các tệp pointer.
- Nội dung của repository submodule nếu chỉ sao chép repository cha.
- Metadata của nền tảng lưu trữ như pull request, issue, release asset, quyền truy cập, biến bí mật CI và cấu hình dự án.

Một clone đầy đủ thường có lịch sử commit của các tham chiếu mà remote cho phép truy cập, nhưng shallow clone chỉ chứa một phần lịch sử. Clone cũng không thể mang theo thay đổi chưa commit ở máy nguồn. Vì vậy, trước khi xem clone là một phần của kế hoạch backup, cần xác định chính xác phạm vi dữ liệu cần phục hồi.

### 3.2. Remote không đồng nghĩa với bản sao lưu độc lập

Đẩy commit lên GitHub, GitLab hoặc một máy chủ Git khác giúp dữ liệu tồn tại ngoài máy cá nhân. Đây là một lớp bảo vệ hữu ích, nhưng remote vẫn có thể chịu cùng nhóm rủi ro với hệ thống chính:

- Tài khoản hoặc token bị chiếm quyền.
- Repository bị xóa, ghi đè tham chiếu hoặc bị thay đổi quyền.
- Lỗi vận hành hoặc sự cố của nhà cung cấp.
- Mã độc hoặc thao tác phá hoại ảnh hưởng đến cả nguồn và bản sao đang đồng bộ.
- Lịch sử bị force-push khiến các commit không còn được tham chiếu.

Một bản mirror được cập nhật liên tục cũng có thể nhận thay đổi xóa tham chiếu từ remote. Do đó, bản mirror đơn lẻ không thay thế các snapshot có lịch sử lưu giữ riêng. Bản sao lưu cần nằm trên hệ thống hoặc tài khoản có quyền quản trị độc lập, có chính sách retention và có bản bất biến hoặc offline nếu mức độ quan trọng của dữ liệu yêu cầu.

### 3.3. Tạo bản sao repository và kiểm tra khả năng phục hồi

Có thể tạo một bản mirror để sao chép các tham chiếu mà remote công bố:

~~~
git clone --mirror <remote-url> project-backup.git
~~~

Với repository nhỏ hoặc khi cần một bản lưu tại một thời điểm, có thể tạo Git bundle từ các tham chiếu hiện có:

~~~
git bundle create project-2026-11-17.bundle --all
git bundle verify project-2026-11-17.bundle
~~~

Bundle có thể được lưu ở một vị trí backup độc lập. Có thể thử clone từ bundle để kiểm tra khả năng đọc lại:

~~~
git clone project-2026-11-17.bundle project-restore-test
~~~

Các lệnh trên chỉ xử lý dữ liệu Git có thể truy cập qua những tham chiếu được đóng gói. Chúng không tự sao lưu Git LFS objects, repository submodule, database, artifact, cấu hình nền tảng hay các thay đổi chưa commit. Với Git LFS, cần sao lưu cả kho LFS; với submodule, cần sao lưu từng repository con và đảm bảo commit được tham chiếu vẫn tồn tại.

Có thể dùng lệnh sau để kiểm tra tính nhất quán của object database trong một repository:

~~~
git fsck --full
~~~

Kết quả fsck tốt là một tín hiệu về tính toàn vẹn của object database, không chứng minh rằng toàn bộ hệ thống đã có thể phục hồi. Kiểm tra backup chỉ hoàn tất khi nhóm thực hiện restore thử vào môi trường riêng, xác minh lịch sử, file, LFS, submodule và các dữ liệu liên quan.

### 3.4. Thiết kế backup theo mục tiêu phục hồi

Kế hoạch backup nên xác định:

- **Phạm vi:** Repository, LFS, submodule, artifact, database, file người dùng, cấu hình và metadata nào cần bảo vệ.
- **RPO (Recovery Point Objective):** Có thể chấp nhận mất tối đa bao nhiêu dữ liệu hoặc bao nhiêu thời gian thay đổi.
- **RTO (Recovery Time Objective):** Hệ thống cần hoạt động trở lại trong bao lâu.
- **Tần suất và thời hạn lưu:** Backup mỗi giờ, mỗi ngày hay theo sự kiện; giữ snapshot trong bao lâu.
- **Tính độc lập:** Bản sao nằm ở tài khoản, hệ thống lưu trữ hoặc miền quyền hạn riêng nào.
- **Quyền và mã hóa:** Ai được đọc, xóa hoặc khôi phục backup; khóa mã hóa được lưu ở đâu.
- **Kiểm thử:** Ai thực hiện restore, kiểm tra điều gì và bao lâu thực hiện một lần.

Backup chưa được kiểm tra phục hồi chỉ là dữ liệu đã được sao chép. Một buổi diễn tập restore định kỳ thường phát hiện sớm các thiếu sót như thiếu khóa, thiếu LFS objects, thiếu submodule hoặc thiếu quyền truy cập.

## 4. Giới hạn của Git trong quản lý bí mật

### 4.1. .gitignore không phải cơ chế bảo mật

Các tệp như .env, khóa riêng, token, mật khẩu database và chứng chỉ có thể bị đưa vào repository do thao tác nhầm. Thêm tên tệp vào .gitignore giúp Git bỏ qua tệp chưa được theo dõi trong các lần thêm sau, nhưng không tự bỏ một tệp đã được track khỏi index hoặc lịch sử.

Ví dụ, nếu .env đã được commit, chỉ thêm dòng .env vào .gitignore là chưa đủ. Có thể bỏ tệp khỏi index nhưng vẫn giữ tệp trên máy làm việc:

~~~
echo .env >> .gitignore
git rm --cached -- .env
git add .gitignore
git commit -m "Stop tracking local environment file"
~~~

Sau thao tác này, commit mới không còn theo dõi .env, nhưng các commit cũ vẫn có thể chứa nội dung của tệp. Bất kỳ ai có quyền đọc lịch sử cũ đều có thể lấy lại bí mật đó.

### 4.2. Xóa bí mật khỏi commit mới không xóa được lịch sử cũ

Commit Git tham chiếu đến các object nội dung. Một thay đổi xóa token khỏi tệp hiện tại chỉ tạo ra một trạng thái mới; object và commit cũ vẫn có thể tồn tại trong lịch sử, reflog, clone của cộng tác viên, fork, cache hoặc bản backup.

Nếu bí mật đã bị commit hoặc đẩy lên remote, cần xử lý như một sự cố lộ bí mật:

1. **Thu hồi hoặc xoay vòng bí mật ngay.** Vô hiệu hóa token, mật khẩu, khóa hoặc chứng chỉ cũ; cấp thông tin mới và kiểm tra quyền sử dụng. Đây là bước giảm rủi ro trực tiếp.
2. **Xác định phạm vi lộ.** Kiểm tra commit, branch, tag, pull request, fork, log CI, artifact và các bản sao có thể đã nhận nội dung.
3. **Loại bỏ nội dung khỏi lịch sử khi cần.** Có thể dùng công cụ chuyên dụng như git-filter-repo để viết lại lịch sử, sau đó cập nhật các tham chiếu trên remote theo kế hoạch phối hợp.
4. **Đồng bộ lại các bản clone.** Cộng tác viên cần làm theo hướng dẫn của nhóm vì lịch sử đã viết lại có thể khiến thao tác pull, push hoặc merge trên clone cũ tạo lại commit chứa bí mật.
5. **Kiểm tra các bản sao và hệ thống liên quan.** Liên hệ quản trị viên nền tảng để xử lý cache, fork hoặc bản lưu theo chính sách của nhà cung cấp; rà soát log và artifact.

Viết lại lịch sử là thao tác ảnh hưởng đến mọi người đang dùng repository và không đảm bảo thu hồi được mọi bản sao đã phát tán. Nó cũng không thay thế việc thu hồi bí mật cũ. Không nên chỉ force-push rồi cho rằng sự cố đã được xử lý.

### 4.3. Nơi phù hợp để lưu bí mật

Repository nên chứa tên biến, cấu trúc cấu hình và giá trị mẫu không nhạy cảm. Ví dụ, có thể commit tệp .env.example với các placeholder:

~~~
DATABASE_HOST=localhost
DATABASE_USER=app_user
DATABASE_PASSWORD=replace-me
API_TOKEN=replace-me
~~~

Giá trị thực nên được cấp từ secret manager hoặc cơ chế quản lý biến bí mật của nền tảng CI/CD và môi trường chạy. Một số nguyên tắc hữu ích:

- Chỉ cấp bí mật cho đúng ứng dụng, môi trường và khoảng thời gian cần thiết.
- Dùng token ngắn hạn hoặc cơ chế định danh workload như OIDC khi nền tảng hỗ trợ.
- Phân quyền tối thiểu; tách quyền đọc bí mật production khỏi quyền phát triển thông thường.
- Không in bí mật vào log, thông báo lỗi, URL hoặc output của pipeline.
- Luân chuyển khóa theo chính sách và có quy trình thu hồi khi nghi ngờ bị lộ.
- Bật secret scanning ở nơi phù hợp và xử lý cảnh báo trước khi merge.

Trong một số quy trình, nhóm có thể lưu cấu hình đã mã hóa trong Git bằng công cụ như SOPS. Khi đó, khóa giải mã phải được quản lý độc lập và chỉ cấp cho người hoặc workload được phép. Mã hóa giúp bảo vệ dữ liệu lưu trữ, nhưng không bảo vệ được nếu plaintext bị ghi vào log, máy build hoặc tệp tạm không an toàn.

Hook pre-commit có thể giúp phát hiện bí mật trước khi commit, nhưng người dùng có thể bỏ qua hook và hook ở máy cá nhân không áp dụng đồng đều cho mọi contributor. Nên kết hợp kiểm tra phía server hoặc CI, chính sách bảo vệ branch và secret manager. Việc giới hạn quyền truy cập repository cũng quan trọng vì người có quyền đọc repository có thể đọc toàn bộ lịch sử mà nền tảng cung cấp.

## 5. Chọn công cụ theo đúng trách nhiệm

| Nhu cầu | Git có thể làm gì? | Thành phần cần bổ sung |
|---|---|---|
| Theo dõi mã nguồn và cấu hình | Commit, branch, merge, tag, diff và lịch sử | Quy tắc review, bảo vệ branch và phân quyền repository |
| Phát hành phần mềm | Cung cấp commit hoặc tag làm đầu vào | CI/CD, build runner, artifact registry, deployment controller và monitoring |
| Theo dõi cấu hình hạ tầng | Lưu cấu hình mong muốn dưới dạng văn bản | Terraform hoặc công cụ cấu hình, GitOps controller và cơ chế phát hiện drift |
| Sao lưu mã nguồn | Clone, mirror, bundle và kiểm tra object | Backup độc lập, snapshot, retention, bảo vệ quyền xóa và diễn tập restore |
| Sao lưu toàn bộ ứng dụng | Không bao gồm tự động dữ liệu runtime | Backup database, object storage, volume, LFS, submodule và metadata cần thiết |
| Quản lý bí mật | Lưu placeholder hoặc tham chiếu cấu hình | Secret manager, biến bí mật CI/CD, OIDC, phân quyền và secret scanning |

Không có một lệnh Git đơn lẻ nào thay thế được các thành phần trên. Git phát huy hiệu quả khi là nguồn lịch sử có thể truy vết và là đầu vào có phiên bản cho các quy trình chuyên trách.

## 6. Quy trình thực tế nên áp dụng

Một quy trình có thể kết hợp Git với các hệ thống khác như sau:

1. Nhà phát triển tạo branch, commit thay đổi và mở pull request. Review tập trung vào diff, test và ảnh hưởng của thay đổi.
2. CI kiểm tra mã nguồn, dependency, secret và policy. Khi đạt yêu cầu, pipeline build artifact và gắn artifact với commit SHA.
3. Release được đánh dấu bằng tag được bảo vệ; pipeline ghi nhận tag, commit SHA, checksum artifact và người phê duyệt.
4. CD triển khai artifact đã kiểm thử vào môi trường đích, lấy cấu hình và bí mật từ nguồn được quản lý, sau đó chạy health check và theo dõi metric.
5. Khi có sự cố, nhóm xác định artifact và commit đang chạy, đánh giá khả năng rollback ứng dụng, migration và dữ liệu trước khi thực hiện.
6. Backup chạy theo lịch và phạm vi đã xác định. Bản sao được lưu độc lập, có retention, có kiểm soát quyền xóa và được restore thử định kỳ.
7. Nếu bí mật bị commit, nhóm thu hồi hoặc xoay vòng bí mật trước, sau đó xử lý lịch sử và các bản sao theo quy trình ứng phó sự cố.

Quy trình này tạo ra mối liên hệ có thể truy vết giữa thay đổi mã nguồn, artifact, lần triển khai và môi trường. Nó cũng giúp phân biệt lỗi ở mã nguồn, lỗi build, lỗi triển khai, sai lệch cấu hình và sự cố dữ liệu.

## 7. Checklist cần nhớ

**Trước khi triển khai**

- [ ] Xác định commit SHA và artifact cụ thể sẽ triển khai.
- [ ] Kiểm tra test, dependency, cấu hình và kết quả build.
- [ ] Đảm bảo bí mật được cấp từ secret manager hoặc cơ chế tương đương.
- [ ] Có health check, giám sát và phương án xử lý migration hoặc rollback.

**Khi thiết kế backup**

- [ ] Liệt kê repository, LFS, submodule, database, file người dùng và metadata cần bảo vệ.
- [ ] Xác định RPO, RTO, tần suất và thời hạn lưu.
- [ ] Lưu bản sao độc lập với quyền truy cập và quyền xóa riêng.
- [ ] Thực hiện restore thử và ghi nhận kết quả.

**Khi phát hiện bí mật trong Git**

- [ ] Thu hồi hoặc xoay vòng bí mật ngay.
- [ ] Xác định các commit, branch, tag, fork, log và artifact bị ảnh hưởng.
- [ ] Phối hợp viết lại lịch sử nếu cần và hướng dẫn cộng tác viên đồng bộ lại.
- [ ] Kiểm tra các bản sao, tăng cường secret scanning và rà soát nguyên nhân.

Điểm cốt lõi là dùng Git cho lịch sử phiên bản và khả năng truy vết. Triển khai cần pipeline và cơ chế vận hành; phục hồi cần backup độc lập đã được kiểm thử; bí mật cần kho lưu trữ và quy trình cấp phát, thu hồi riêng. Hiểu đúng các giới hạn này giúp nhóm tận dụng Git mà không đặt lên nó những trách nhiệm mà một hệ thống quản lý phiên bản không được thiết kế để đảm nhận.
