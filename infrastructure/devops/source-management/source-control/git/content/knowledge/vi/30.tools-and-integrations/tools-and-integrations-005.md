# Phân biệt Git core, phần mở rộng và tính năng của dịch vụ lưu trữ

Khi làm việc với Git, bạn có thể dùng lệnh `git` trong terminal, cài thêm Git LFS, dùng credential manager, cài plugin cho IDE và thao tác trên GitHub, GitLab hoặc một dịch vụ lưu trữ khác. Những thành phần này thường xuất hiện trong cùng một quy trình, nhưng chúng không thuộc cùng một lớp. Nếu không phân biệt ranh giới, rất dễ cho rằng một tính năng của hosting là tính năng có sẵn trong Git, hoặc nghĩ rằng cài Git là đã có mọi công cụ cần thiết.

Có thể chia hệ sinh thái thành ba nhóm chính:

1. **Git core:** mô hình dữ liệu, lệnh tích hợp, cấu hình, giao thức và cơ chế quản lý phiên bản của Git.
2. **Phần mở rộng và công cụ bên ngoài:** chương trình bổ sung hoặc tích hợp với Git để xử lý nhu cầu riêng, chẳng hạn Git LFS, credential helper, công cụ viết lại lịch sử và plugin IDE.
3. **Tính năng của dịch vụ lưu trữ:** pull request/merge request, review, branch protection, CI runners, issue, release, webhook và quyền truy cập do nền tảng server cung cấp.

Ba nhóm có thể phối hợp với nhau, nhưng có cách cài đặt, cấu hình, vận hành và giới hạn tương thích khác nhau. Bài học này giúp nhận diện thành phần đang thực hiện công việc, biết nơi cần kiểm tra khi có lỗi và chọn đúng tài liệu hỗ trợ.

## 1. Git core là gì?

Git core là phần nền tảng của hệ thống quản lý phiên bản phân tán. Nó định nghĩa cách Git lưu object, tạo commit, quản lý branch và tag, so sánh nội dung, trao đổi dữ liệu giữa repository và thực hiện các thao tác quản lý lịch sử.

Những thành phần cốt lõi gồm:

- **Object database:** lưu blob, tree, commit và tag object.
- **Index (staging area):** chuẩn bị snapshot cho commit tiếp theo.
- **Refs:** tên branch, tag và các tham chiếu khác đến object.
- **Working tree:** các tệp được checkout để người dùng chỉnh sửa.
- **Configuration:** điều khiển hành vi Git theo phạm vi system, global hoặc local.
- **Transport/protocol:** trao đổi object và refs qua local path, SSH, HTTP(S) hoặc giao thức Git phù hợp.
- **Hooks và attributes:** cơ chế tích hợp để chạy script hoặc áp dụng quy tắc xử lý tệp tại các điểm cụ thể.

Các lệnh quen thuộc như `git init`, `git clone`, `git status`, `git add`, `git commit`, `git switch`, `git merge`, `git rebase`, `git fetch`, `git push`, `git tag` và `git log` thuộc bộ lệnh Git. Chúng làm việc trên repository và lịch sử theo mô hình Git.

Git còn có các lệnh cấp thấp (*plumbing*) phục vụ truy cập cấu trúc bên trong, ví dụ `git cat-file`, `git hash-object`, `git update-ref`, `git rev-parse` và `git ls-tree`. Những lệnh cấp cao (*porcelain*) như `git status`, `git log` và `git switch` được thiết kế thuận tiện cho công việc thường ngày.

## 2. Tính năng tích hợp sẵn trong Git

Một số tính năng có thể ít được dùng trong công việc cơ bản nhưng vẫn là chức năng của Git, không cần cài extension riêng.

| Tính năng | Lệnh tiêu biểu | Công dụng |
|---|---|---|
| Quản lý nhiều worktree | `git worktree` | Tạo nhiều thư mục làm việc cùng dùng chung repository |
| Checkout chọn lọc | `git sparse-checkout` | Giới hạn đường dẫn được đưa ra working tree |
| Quản lý submodule | `git submodule` | Ghi nhận repository con bằng gitlink và cấu hình URL |
| Bảo trì object database | `git gc`, `git maintenance`, `git count-objects` | Đo lường, gom object và bảo trì repository |
| Tìm kiếm lịch sử | `git log`, `git blame`, `git bisect`, `git grep` | Truy tìm commit, thay đổi và nội dung |
| Xác minh object | `git fsck`, `git cat-file` | Kiểm tra cấu trúc và nội dung object |
| Quản lý cấu hình | `git config` | Thiết lập hành vi Git theo phạm vi |
| Hook và attribute | hook directory, `.gitattributes` | Tích hợp script và quy tắc xử lý tệp |

Ví dụ, `git worktree` và `git sparse-checkout` không phải sản phẩm của hosting. Chúng hoạt động local trên repository với Git client hỗ trợ. Bạn có thể sử dụng chúng khi làm việc với remote Git thông thường, miễn là phiên bản Git và môi trường phù hợp.

Tương tự, `git submodule` là tính năng của Git, nhưng repository con mà submodule trỏ đến vẫn cần được lưu trữ ở một nơi có thể truy cập. Git quản lý gitlink và quá trình checkout; quyền truy cập, tính sẵn sàng và chính sách của server repository con thuộc môi trường lưu trữ.

## 3. Phần mở rộng và công cụ bên ngoài là gì?

Phần mở rộng là chương trình hoặc công cụ bổ sung chức năng cho workflow Git. Nó có thể được gọi từ lệnh Git, được cấu hình như helper/filter, được kích hoạt qua hook hoặc chạy bên trong IDE. Không phải mọi công cụ bên ngoài đều là extension chính thức của Git; một số do cộng đồng, nhà cung cấp hoặc tổ chức tự phát triển.

Một số ví dụ:

| Công cụ | Vai trò | Cách tích hợp thường gặp |
|---|---|---|
| Git LFS | Lưu nội dung tệp lớn ngoài object database Git thông thường | Lệnh `git lfs`, filter và hook |
| Git Credential Manager | Quản lý thông tin xác thực cho remote | Git credential helper |
| `git-filter-repo` | Lọc hoặc viết lại lịch sử repository | Chương trình riêng chạy với repository local |
| `git-annex` | Quản lý tệp lớn và nội dung bên ngoài Git theo mô hình riêng | Lệnh và metadata của công cụ |
| IDE Git integration | Hiển thị diff, branch, commit và thao tác Git trong giao diện | Gọi Git executable hoặc API tích hợp của IDE |
| GUI client | Cung cấp giao diện đồ họa cho thao tác Git | Gọi Git hoặc triển khai một phần thao tác qua thư viện riêng |

Một công cụ có thể tích hợp sâu với Git nhưng vẫn có vòng đời cài đặt, phiên bản và cấu hình riêng. Khi gặp lỗi, cần xác định lỗi đến từ Git core, extension, IDE hay server thay vì mặc định tất cả đều là lỗi Git.

## 4. Phân biệt lệnh Git tích hợp và external subcommand

Khi chạy một lệnh như:

```bash
git status
git log
```

Git gọi các lệnh tích hợp sẵn trong bộ cài. Nhưng một số lệnh có dạng:

```bash
git lfs version
git filter-repo --help
```

`git lfs` thường được cung cấp bởi executable riêng tên `git-lfs`. Git tìm external subcommand theo quy tắc tìm chương trình trong môi trường thực thi. Các công cụ kiểu này thường cần được cài riêng và phải có trong PATH.

Có thể xem các lệnh Git mà bản cài hiện tại nhận diện:

```bash
git help -a
```

Kiểm tra đường dẫn executable của Git và một external subcommand:

```bash
# macOS, Linux hoặc Git Bash
command -v git
command -v git-lfs

# Windows PowerShell
where.exe git
where.exe git-lfs
```

Nếu `git lfs` báo không tìm thấy lệnh, Git core vẫn có thể hoạt động bình thường; vấn đề có thể là Git LFS chưa được cài hoặc chưa có trong PATH. Hãy xác minh bằng `git lfs version` và kiểm tra executable.

Không phải lệnh nào có tên sau `git` cũng là external subcommand. Ví dụ, `git co` có thể là alias được cấu hình:

```bash
git config --get-regexp '^alias\.'
```

Alias chỉ là tên thay thế được cấu hình, không nhất thiết là chương trình riêng. Phân biệt alias, lệnh tích hợp và external subcommand giúp tìm đúng nguồn khi lệnh không chạy.

## 5. Git LFS: ví dụ về extension tích hợp với Git core

Git LFS là một ví dụ điển hình cho phần mở rộng. Git core lưu pointer file nhỏ trong commit, còn Git LFS client chuyển nội dung nhị phân lớn đến LFS server.

Sau khi cài Git LFS, chạy:

```bash
git lfs version
git lfs install
git lfs track "*.psd"
```

`git lfs track` ghi quy tắc vào `.gitattributes`. File `.gitattributes` được commit trong repository để các clone khác biết đường dẫn nào dùng LFS filter. Nội dung thật được truyền đến LFS endpoint khi fetch/push theo cơ chế của Git LFS.

Ở đây có ba thành phần phối hợp:

1. Git core quản lý commit, tree, index, refs và push/fetch thông thường.
2. Git LFS client thực hiện clean/smudge filter và chuyển LFS object.
3. Dịch vụ lưu trữ cung cấp LFS endpoint, quota, xác thực và lưu trữ nội dung lớn.

Nếu push commit thành công nhưng LFS object chưa được tải lên, người khác có thể clone repository nhưng không lấy được nội dung tệp lớn. Do đó, xác minh Git refs và LFS objects là hai bước riêng.

## 6. Credential helper: công cụ xác thực bên ngoài

Git core hỗ trợ cơ chế credential helper để lấy và lưu thông tin xác thực. Helper có thể là chương trình đi kèm Git, chương trình riêng hoặc tích hợp của hệ điều hành.

Xem helper được cấu hình:

```bash
git config --show-origin --get-all credential.helper
```

Ví dụ cấu hình một helper:

```bash
git config --global credential.helper manager
```

Tên helper và cách gọi phụ thuộc bản cài đặt. Trên Windows, Git Credential Manager thường được dùng để hỗ trợ xác thực HTTPS và tích hợp kho lưu trữ thông tin xác thực của hệ điều hành. Một số môi trường macOS/Linux cũng có thể cài và cấu hình GCM riêng.

Điểm cần phân biệt:

- Git core định nghĩa giao thức gọi credential helper.
- Credential manager thực hiện lưu, lấy hoặc làm mới thông tin xác thực.
- Hosting quyết định tài khoản/token/key có quyền truy cập repository hay không.

Nếu xác thực thất bại, kiểm tra remote URL, helper đang được cấu hình, phiên đăng nhập và quyền tài khoản trên hosting. Việc `git status` chạy được không chứng minh remote authentication đã hoạt động, vì `status` không cần truy cập server.

## 7. Hooks, filters và attributes nằm ở ranh giới tích hợp

Git core cung cấp cơ chế gọi hook và áp dụng attribute/filter, còn script hoặc chương trình thực hiện công việc có thể do dự án hoặc công cụ bên ngoài cung cấp.

### Hooks

Ví dụ `pre-commit`, `commit-msg` hoặc `pre-push` được Git gọi tại các thời điểm nhất định. Git cung cấp điểm móc và hợp đồng đầu vào; nội dung hook là script được cài trong thư mục hooks hoặc thư mục `core.hooksPath`.

```bash
git config --show-origin --get core.hooksPath
git rev-parse --git-path hooks
```

Hook local giúp kiểm tra sớm nhưng có thể không tồn tại ở clone khác hoặc bị bỏ qua bởi một số tùy chọn. Nếu một quy tắc là bắt buộc cho mọi người, nên thực thi thêm trong CI hoặc server-side policy.

### Attributes và filters

`.gitattributes` có thể khai báo cách xử lý line ending, diff, merge hoặc filter cho tệp. Git core đọc các thuộc tính, nhưng chương trình filter được gọi có thể là công cụ ngoài.

Kiểm tra thuộc tính hiệu lực:

```bash
git check-attr -a -- path/to/file
```

Xem các filter được cấu hình:

```bash
git config --show-origin --get-regexp '^filter\.'
```

Nếu filter yêu cầu executable không có trên máy, thao tác checkout hoặc stage có thể thất bại. Khi đó cần cài đúng công cụ và xác minh cấu hình filter thay vì chỉnh nội dung commit một cách tùy tiện.

## 8. Tính năng nào thuộc dịch vụ lưu trữ?

Git là hệ thống phân tán; bản thân repository không cần một website trung tâm để tạo commit, branch hoặc merge local. Dịch vụ lưu trữ như GitHub, GitLab, Bitbucket hoặc máy chủ Git tự quản lý bổ sung giao diện và workflow cộng tác.

Những tính năng thường thuộc hosting:

| Tính năng | Vai trò của dịch vụ lưu trữ |
|---|---|
| Pull request / Merge request | Tạo không gian đề xuất, review và thảo luận thay đổi giữa các branch |
| Branch protection / Ruleset | Áp dụng điều kiện trước khi cập nhật branch được bảo vệ |
| Review approval | Lưu ý kiến, phê duyệt và trạng thái review của thành viên |
| Issues / Boards | Theo dõi lỗi, yêu cầu và công việc |
| CI/CD runners | Cấp môi trường chạy pipeline và lưu kết quả |
| Secrets / Variables | Lưu dữ liệu cấu hình nhạy cảm cho workflow hoặc runner |
| Webhooks | Gửi sự kiện đến hệ thống tích hợp khi repository thay đổi |
| Release UI / Assets | Quản lý trang phát hành và tệp đính kèm |
| Package/Container registry | Lưu package hoặc image do pipeline và người dùng phát hành |
| Access control | Quản lý thành viên, nhóm, token, deploy key và quyền repository |

Một số hosting dùng Git refs và Git protocol bên dưới, nhưng phần review, approval, issue và policy thường được lưu trong cơ sở dữ liệu của dịch vụ. Chúng không tự động đi theo khi chỉ mirror Git repository sang máy chủ khác.

## 9. File cấu hình trong repository và tính năng chạy trên hosting

Một số tính năng hosting được khai báo bằng file nằm trong repository. Điều này dễ gây nhầm rằng toàn bộ tính năng là của Git.

Ví dụ:

- `.github/workflows/build.yml` chứa định nghĩa workflow cho GitHub Actions.
- `.gitlab-ci.yml` chứa cấu hình pipeline cho GitLab CI/CD.
- File cấu hình pipeline khác có thể được đọc bởi hệ thống CI bên ngoài.

Git core chỉ theo dõi những file này như các file văn bản bình thường. Hosting hoặc CI service đọc file, khởi tạo runner, cấp secrets, thực thi job và lưu kết quả. Nếu clone repository về máy không có dịch vụ đó, file cấu hình vẫn tồn tại nhưng pipeline không tự chạy.

Tương tự, một file `CODEOWNERS` có thể được hosting dùng để đề xuất reviewer hoặc áp dụng quy tắc review. Git core chỉ lưu nội dung file; hành vi thực tế phụ thuộc nền tảng và cấu hình repository.

## 10. Git protocol không đồng nghĩa với toàn bộ tính năng hosting

Các thao tác `clone`, `fetch` và `push` trao đổi object cùng refs giữa Git client và server. Thành công của những thao tác này chỉ chứng minh phần giao tiếp Git tương ứng hoạt động.

Ví dụ:

```bash
git clone https://git.example.com/team/project.git
git fetch origin
git push origin feature/login
```

Những lệnh này không tự tạo pull request, không xin approval, không chạy CI và không cấu hình branch protection. Các hành động đó cần giao diện, API, webhook hoặc automation của hosting.

Một nền tảng có thể cung cấp thêm ref đặc biệt để đại diện cho pull request, nhưng review comments, approvals, checks và trạng thái merge vẫn là dữ liệu của nền tảng. Khi chuyển repository, phải xác minh riêng khả năng di chuyển các dữ liệu này.

## 11. Xác định lỗi nằm ở Git, extension hay hosting

Khi một thao tác thất bại, hãy phân loại theo nơi thực thi.

| Triệu chứng | Thành phần nên kiểm tra đầu tiên |
|---|---|
| `git status` hoặc `git commit` không chạy | Git client, repository local, index, hook hoặc filesystem |
| `git lfs` không được nhận diện | Git LFS executable và PATH |
| Checkout báo lỗi filter | `.gitattributes`, filter config và công cụ bên ngoài |
| Clone/fetch báo authentication failed | Credential helper, SSH key/token và quyền hosting |
| Push bị từ chối do branch protected | Quy tắc branch protection trên server |
| Pull request không xuất hiện | Hosting UI/API, quyền và trạng thái branch; push Git thành công chưa đủ |
| Pipeline không chạy | CI config, webhook, runner, secrets và trạng thái dịch vụ CI |
| Clone được nhưng thiếu file LFS | LFS endpoint, quyền và LFS objects |
| Submodule không checkout được | URL repository con, commit gitlink, credential và quyền truy cập submodule |

Một quy trình chẩn đoán gọn:

1. Ghi lại lệnh chính xác và thông báo lỗi.
2. Xác định thao tác là local, external tool hay server-side.
3. Kiểm tra phiên bản Git và executable cần thiết.
4. Xem cấu hình liên quan bằng `git config --show-origin`.
5. Kiểm tra remote và quyền truy cập nếu thao tác cần server.
6. Đối chiếu log của extension hoặc hosting khi Git client đã hoàn tất bước của nó.

Không gửi toàn bộ output cấu hình hoặc log xác thực công khai nếu chưa rà soát token, URL nội bộ, tên người dùng và thông tin nhạy cảm.

## 12. Kiểm tra môi trường Git đang sử dụng

Các lệnh sau giúp xác định bộ công cụ trên máy:

```bash
# Phiên bản Git core.
git --version

# Các lệnh Git mà bản cài nhận diện.
git help -a

# Vị trí executable Git (macOS/Linux/Git Bash).
command -v git

# Kiểm tra Git LFS nếu dự án dùng LFS.
git lfs version

# Remote đang cấu hình.
git remote -v

# Cấu hình có nguồn gốc.
git config --show-origin --list
```

Trên PowerShell, dùng `where.exe git` thay cho `command -v git`. `git config --show-origin --list` có thể hiển thị thông tin riêng tư hoặc cấu hình nội bộ; chỉ chia sẻ phần cần thiết sau khi rà soát.

Nếu IDE có cấu hình đường dẫn Git riêng, kiểm tra executable mà IDE đang gọi. Một máy có thể có nhiều bản Git trong PATH hoặc một IDE dùng Git đi kèm riêng; sự khác biệt phiên bản có thể khiến hành vi giữa terminal và IDE không giống nhau.

## 13. Ví dụ một workflow có đủ ba lớp

Giả sử nhóm phát triển một ứng dụng có mã nguồn, tệp thiết kế lớn và quy trình review trên hosting.

**Bước 1 — Git core:** nhà phát triển tạo branch, sửa code, stage và commit:

```bash
git switch -c feature/new-checkout
git add src/
git commit -m "feat: add checkout flow"
```

**Bước 2 — Extension:** tệp thiết kế lớn được quản lý bằng Git LFS:

```bash
git lfs track "*.psd"
git add .gitattributes assets/checkout.psd
git commit -m "chore: track checkout design with LFS"
```

**Bước 3 — Hosting:** đẩy branch lên server:

```bash
git push -u origin feature/new-checkout
```

Sau đó, nhà phát triển mở pull request hoặc merge request trên hosting. Nền tảng chạy CI, yêu cầu review và áp dụng branch protection. Khi các điều kiện đạt, người có quyền merge thay đổi vào branch chính.

Trong workflow này, Git core tạo và chuyển commit; Git LFS chuyển nội dung lớn; hosting quản lý review, policy và pipeline. Nếu pipeline không chạy dù push thành công, cần kiểm tra hosting/CI. Nếu người review không tải được file PSD, kiểm tra LFS. Nếu commit local không tạo được, kiểm tra Git core hoặc hook local.

## 14. Lựa chọn công cụ theo nhu cầu

Không phải dự án nào cũng cần cài mọi extension hoặc sử dụng toàn bộ tính năng hosting. Hãy chọn theo nhu cầu thực tế:

| Nhu cầu | Thành phần phù hợp |
|---|---|
| Theo dõi thay đổi, branch, merge và remote | Git core |
| Làm việc với file nhị phân lớn | Git LFS hoặc giải pháp lưu trữ phù hợp của dự án |
| Lưu thông tin xác thực HTTPS an toàn | Credential manager/helper |
| Chia lịch sử thành nhiều thư mục làm việc | `git worktree` tích hợp trong Git |
| Chỉ checkout một phần monorepo | `git sparse-checkout` tích hợp trong Git |
| Review thay đổi và phê duyệt | Pull request/merge request trên hosting |
| Kiểm tra tự động trước khi merge | CI service và branch protection |
| Tự động thông báo hoặc triển khai sau push | Webhook, CI/CD hoặc automation của hosting |
| Viết lại lịch sử phức tạp | Công cụ như `git-filter-repo`, theo quy trình được kiểm soát |

Trước khi cài công cụ mới, kiểm tra liệu Git core đã có lệnh đáp ứng nhu cầu hay chưa, sau đó xác định extension có tương thích với phiên bản Git và hosting không. Dùng công cụ được dự án hỗ trợ để giảm khác biệt giữa máy phát triển và CI.

## 15. Những hiểu nhầm thường gặp

| Hiểu nhầm | Cách hiểu đúng |
|---|---|
| Cài Git là đã có Git LFS | Git LFS là công cụ riêng cần cài và khởi tạo |
| Pull request là một lệnh Git core | Pull request/merge request là workflow của hosting, thường dùng Git refs và API phía dưới |
| Push thành công nghĩa là CI đã chạy | Push chỉ cập nhật refs; CI cần dịch vụ, runner và cấu hình riêng |
| Branch protection được lưu trong commit | Quy tắc bảo vệ branch thuộc cấu hình server/hosting |
| `.gitlab-ci.yml` là tính năng thực thi của Git | Git chỉ theo dõi file; GitLab CI đọc file và chạy pipeline |
| Hook là một plugin hoàn chỉnh của Git | Git cung cấp cơ chế hook; script thực thi có thể do dự án hoặc công cụ ngoài cung cấp |
| Mọi lệnh bắt đầu bằng `git` đều là lệnh tích hợp | Một số là alias hoặc external subcommand như `git lfs` |
| Mirror repository sẽ chuyển cả issue và review | Mirror chuyển refs/object trong phạm vi Git; dữ liệu hosting cần migration riêng |

## 16. Ghi nhớ

Git core cung cấp mô hình object, index, refs, working tree, lệnh quản lý lịch sử và giao thức trao đổi repository. Các phần mở rộng như Git LFS, credential manager và công cụ viết lại lịch sử bổ sung khả năng cho workflow nhưng có executable, cấu hình hoặc dịch vụ riêng. Dịch vụ hosting cung cấp review, branch protection, CI/CD, issue, quyền truy cập, webhook và các tính năng cộng tác ở phía server.

Khi điều tra lỗi, hãy xác định thành phần đang thực hiện thao tác: Git client, extension, IDE, transport hay hosting. Dùng `git --version`, `git help -a`, `git remote -v`, `git lfs version` và `git config --show-origin` để kiểm tra môi trường. Hiểu đúng ranh giới giúp chọn đúng công cụ, tìm đúng tài liệu và tránh kỳ vọng một lệnh Git có thể điều khiển tính năng chỉ tồn tại trên dịch vụ lưu trữ.
