# Lập kế hoạch di chuyển remote, refs, tag, LFS và submodule

Khi chuyển repository Git sang máy chủ hoặc nền tảng lưu trữ mới, chỉ sao chép thư mục source code là chưa đủ. Một repository có thể chứa nhiều branch, tag, notes, commit đã ký, nội dung Git LFS và các submodule trỏ đến repository khác. Ngoài ra, URL remote, branch mặc định, quyền truy cập, branch protection, CI và webhook thường được lưu ở cấu hình hoặc dịch vụ hosting chứ không nằm trong object database Git.

Một lần di chuyển an toàn cần có kế hoạch kiểm kê, sao lưu, chuyển object và refs, chuyển riêng LFS objects, xử lý từng submodule, đồng bộ lần cuối rồi xác minh trên remote đích. Bài này trình bày cách chọn phương án `git push --all`/`--tags` hoặc mirror, cách bảo toàn dữ liệu và cách chuyển người dùng sang remote mới với thời gian gián đoạn có kiểm soát.

## 1. Xác định phạm vi di chuyển

Trước khi chạy lệnh, hãy xác định chính xác thứ cần chuyển và thứ cần cấu hình lại. Git repository và nền tảng hosting không lưu cùng một loại dữ liệu.

| Thành phần | Nơi lưu chính | Cách xử lý khi di chuyển |
|---|---|---|
| Commit, tree, blob, annotated tag object | Git object database | Chuyển bằng clone/fetch/push hoặc mirror |
| Branch và tag refs | Git refs | Chuyển bằng `push --all`, `push --tags` hoặc `push --mirror` tùy phạm vi |
| Notes và custom refs | Namespace `refs/*` | Kiểm kê riêng; mirror có thể chuyển nhiều ref hơn |
| Git LFS content | LFS object storage | Fetch/push LFS objects riêng, không chỉ push Git refs |
| Submodule repository | Repository độc lập | Di chuyển từng repository con và kiểm tra gitlink commit |
| Remote URL, fetch/push refspec | Cấu hình local `.git/config` | Cấu hình lại trên clone hoặc máy mới |
| Branch mặc định, protection, quyền, webhook | Hosting/server | Tạo lại hoặc cấu hình ở nền tảng đích |
| Pull/merge request, issue, review, discussion | Hosting/server | Dùng công cụ/API migration của nền tảng nếu cần giữ |
| CI secrets, variables, runners, release assets | Hosting/CI | Lập danh sách và chuyển theo quy trình riêng |

Git transfer có thể bảo toàn lịch sử và object, nhưng không tự chuyển các thiết lập hoặc dữ liệu quản lý dự án của nền tảng. Hãy xác định phạm vi dự án cần giữ nguyên trước khi lên lịch cutover.

## 2. Kiểm kê repository nguồn

Trước khi sao chép, thu thập thông tin về repository nguồn. Thực hiện từ một clone có quyền đọc đầy đủ hoặc từ repository server phù hợp.

### Xác định remote và trạng thái local

```bash
git status --short --branch
git remote -v
git branch --all --verbose
git tag --list --sort=version:refname
```

Kiểm tra xem clone hiện tại có thay đổi chưa commit hay không. Một clone làm việc thông thường có thể không chứa tất cả refs trên server, đặc biệt nếu fetch refspec bị giới hạn hoặc một số branch chưa từng được fetch.

### Liệt kê refs và object ID

Để kiểm kê refs local:

```bash
git for-each-ref --format='%(refname) %(objectname)' refs
```

Để xem refs mà remote đang quảng bá:

```bash
git ls-remote --refs origin
```

Kiểm tra symbolic HEAD và branch mặc định của remote:

```bash
git ls-remote --symref origin HEAD
```

`git ls-remote` chỉ hiển thị refs được remote quảng bá. Một số hosting có refs nội bộ hoặc refs ẩn không xuất hiện qua lệnh này. Nếu cần chuyển toàn bộ refs nội bộ, phải xác minh quyền truy cập và chính sách của server.

### Kiểm tra các namespace quan trọng

Các namespace phổ biến:

- `refs/heads/`: branch local hoặc branch trên server.
- `refs/tags/`: tag.
- `refs/notes/`: Git notes.
- `refs/replace/`: replace refs dùng để thay thế cách Git nhìn nhận object.
- `refs/remotes/`: remote-tracking refs trong clone thông thường.
- Các namespace tùy chỉnh do workflow hoặc hosting tạo ra.

Không phải mọi ref đều nên xuất hiện ở remote đích. Ví dụ, `refs/remotes/origin/*` thường là trạng thái theo dõi remote trong clone local, còn `refs/pull/*` hoặc `refs/merge-requests/*` có thể là refs nội bộ do hosting sinh ra. Hãy quyết định namespace nào cần chuyển và namespace nào thuộc riêng nền tảng nguồn.

### Kiểm tra object database và tính toàn vẹn

```bash
git count-objects -vH
git fsck --full
```

`git count-objects` giúp ước lượng dung lượng object storage; `git fsck --full` kiểm tra object database. Nếu nguồn có lỗi object hoặc dữ liệu thiếu, xử lý trước khi migration để tránh mang lỗi sang đích.

## 3. Sao lưu và chuẩn bị remote đích

Trước khi chuyển, tạo bản sao lưu có thể khôi phục. Với repository bare hoặc mirror, sao lưu toàn bộ repository directory theo quy trình backup của tổ chức; với clone làm việc, bảo toàn cả thay đổi chưa commit và cấu hình cần thiết.

Kiểm tra remote đích:

- Repository đích đã được tạo và có quyền push.
- Định dạng object và phiên bản Git tương thích với client nguồn.
- Dung lượng, quota và chính sách lưu trữ đủ cho Git objects và LFS objects.
- Dịch vụ đích bật Git LFS nếu repository sử dụng LFS.
- Các tài khoản hoặc deploy keys có quyền đọc submodule sau khi chuyển.
- Đã xác định branch mặc định và quy tắc bảo vệ branch.

Nếu muốn dùng `git push --mirror`, nên tạo repository đích rỗng và dành riêng một mirror clone cho công việc này. Không dùng một clone phát triển đang làm việc để mirror toàn bộ refs mà chưa kiểm tra phạm vi.

## 4. Chọn cách chuyển branch và tag

Có hai cách thường dùng cho phần Git refs. Chúng không tương đương và cần chọn theo yêu cầu.

### Cách A: đẩy branch và tag cần thiết

Trong clone thông thường, thêm remote đích:

```bash
git remote add new-origin https://git.example.com/team/project.git
git fetch --all --tags --prune
```

Đẩy tất cả branch local:

```bash
git push new-origin --all
```

Đẩy tất cả tag local:

```bash
git push new-origin --tags
```

`--all` đẩy các branch local trong `refs/heads/`; nó không đẩy mọi remote-tracking branch và không tự bao gồm tất cả namespace tùy chỉnh. `--tags` đẩy tag local trong `refs/tags/`. Nếu cần notes hoặc custom refs, phải đẩy rõ namespace tương ứng sau khi đã kiểm kê, ví dụ:

```bash
git push new-origin 'refs/notes/*:refs/notes/*'
```

Chỉ dùng refspec cụ thể sau khi xác nhận namespace đó có ý nghĩa trên remote đích. Nếu remote đích đã có branch cùng tên nhưng lịch sử khác, push thông thường có thể bị từ chối do non-fast-forward. Không tự động dùng `--force` để vượt qua; hãy xác định lịch sử đích có cần giữ hay không.

Sau khi push branch chính, thiết lập upstream cho branch làm việc nếu cần:

```bash
git push --set-upstream new-origin main
```

Thao tác này cấu hình quan hệ tracking cho branch local hiện tại hoặc branch được chỉ định theo lệnh, giúp các lần `pull`/`push` sau dùng remote và branch mặc định phù hợp.

### Cách B: mirror toàn bộ refs

Nếu yêu cầu là sao chép gần như toàn bộ ref namespace của repository, dùng một bare mirror clone:

```bash
git clone --mirror https://git.example.com/old/project.git project.git
cd project.git
git remote add target https://git.example.com/new/project.git
git push --mirror target
```

`git clone --mirror` tạo repository bare và cấu hình fetch refspec để lấy toàn bộ refs mà nguồn cho phép quảng bá. `git push --mirror` yêu cầu đích phản chiếu refs local: refs mới được tạo, refs thay đổi có thể được cập nhật cưỡng bức và refs không còn ở mirror local có thể bị xóa ở đích.

Vì vậy, chỉ mirror vào repository đích rỗng hoặc đích đã được xác nhận có thể ghi đè/xóa theo đúng kế hoạch. Lệnh này có tính phá hủy đối với refs ở đích nếu chúng không tồn tại trong mirror nguồn. Không dùng `--mirror` để “thử xem có gì” trên remote đang chứa dữ liệu cần giữ.

Mirror clone không có working tree để chỉnh sửa source code. Đây là lựa chọn phù hợp cho chuyển repository ở cấp refs/object, không phải clone làm việc hằng ngày.

## 5. Hiểu rõ những gì --mirror có thể chuyển

Mirror có phạm vi rộng hơn `--all` và `--tags`, nhưng không có nghĩa nó chuyển toàn bộ dữ liệu của nền tảng hosting.

| Phương thức | Phạm vi chính | Điều cần lưu ý |
|---|---|---|
| `git push --all` | Branch local | Không tự đẩy tag, notes hoặc mọi custom refs |
| `git push --tags` | Tag local | Không đẩy branch |
| Push refspec cụ thể | Namespace/ref được chỉ định | Cần kiểm soát chính xác nguồn và đích |
| `git push --mirror` | Mọi ref local trong phạm vi mirror | Có thể force-update và xóa refs ở remote đích |

Mirror có thể bao gồm notes, replace refs hoặc namespace tùy chỉnh nếu chúng đã được fetch vào mirror local. Tuy nhiên, remote đích có thể từ chối một số namespace được bảo vệ hoặc không cho người dùng tạo. Hosting cũng có thể ẩn refs nội bộ khỏi client. Hãy xem xét output push và kiểm tra lại refs sau khi chuyển.

Không nên kỳ vọng mirror giữ nguyên:

- Pull request hoặc merge request cùng thảo luận/review.
- Issues, wiki nếu wiki được lưu ở repository riêng.
- Branch protection, ruleset, quyền thành viên và nhóm.
- Webhook, deploy key, CI secret, variable, runner và lịch chạy.
- Release assets, package registry, artifact và cấu hình tích hợp.

Những dữ liệu này cần được chuyển bằng công cụ/API hoặc cấu hình lại trên nền tảng đích.

## 6. Đồng bộ lần cuối và kiểm soát thời điểm cutover

Nếu repository nguồn vẫn nhận commit trong lúc sao chép, bản mirror đầu tiên có thể nhanh chóng lỗi thời. Cách an toàn là chia migration thành lần sao chép ban đầu và lần đồng bộ cuối.

Một lịch trình phổ biến:

1. Thông báo thời điểm migration và yêu cầu nhóm không tạo thay đổi trong khoảng cutover.
2. Thực hiện initial mirror khi nguồn vẫn ở chế độ hoạt động hoặc hạn chế ghi theo khả năng nền tảng.
3. Đến cửa sổ cutover, đặt repository nguồn thành read-only hoặc tạm dừng push.
4. Fetch lại toàn bộ refs từ nguồn vào mirror và đẩy mirror lần cuối.
5. Đồng bộ LFS objects còn thiếu.
6. Xác minh branch, tag, LFS, submodule và cấu hình đích.
7. Đổi URL trong tài liệu, CI, bot và clone của thành viên; mở quyền ghi ở đích.
8. Giữ nguồn ở read-only trong khoảng thời gian rollback đã thống nhất.

Với mirror clone có remote nguồn tên `origin` và remote đích tên `target`, lần đồng bộ cuối có thể là:

```bash
git fetch --prune origin
git push --mirror target
```

Trong mirror clone, fetch refspec thường bao phủ refs theo cấu hình mirror. Kiểm tra `git config --get-all remote.origin.fetch` và refs local trước khi đồng bộ. `--prune` xóa refs local không còn được nguồn quảng bá theo refspec; lần `push --mirror` sau đó có thể xóa các refs tương ứng ở đích. Đây là hành vi cần thiết để mirror chính xác nhưng phải được dự kiến trước.

Nếu không thể khóa ghi ở nguồn, cần một quy trình đồng bộ lặp và thời điểm chốt rõ ràng. Tránh cho cả hai remote tiếp tục nhận ghi độc lập trong thời gian dài: hai bên có thể phát sinh commit cùng branch, tag bị di chuyển hoặc lịch sử phân kỳ khiến việc hợp nhất khó kiểm soát.

## 7. Di chuyển Git LFS objects riêng

Một Git repository có thể chuyển commit và pointer file thành công nhưng người dùng vẫn không tải được tệp lớn nếu LFS objects chưa được chuyển. Pointer trong Git chỉ chứa OID và kích thước; nội dung thật nằm trong LFS storage.

### Kiểm kê LFS

Trong clone có các refs cần chuyển, xem các tệp LFS:

```bash
git lfs ls-files --all
git lfs env
```

Kiểm tra `.gitattributes` và `.lfsconfig` nếu repository có dùng. `.lfsconfig` có thể khai báo endpoint LFS; cấu hình local hoặc cấu hình remote có thể ghi đè endpoint. Không đưa token hoặc thông tin xác thực vào file được commit.

### Lấy tất cả LFS objects từ nguồn

Sau khi đã fetch đầy đủ refs và tags:

```bash
git lfs fetch --all origin
```

`--all` yêu cầu tải LFS objects được tham chiếu bởi các refs mà Git LFS xét trong repository, phù hợp cho migration thay vì chỉ lấy object của branch hiện tại. Nếu mirror clone không có LFS client hoặc quyền truy cập nguồn, cài Git LFS và xác thực trước.

### Đẩy tất cả LFS objects lên đích

```bash
git lfs push --all target
```

Lệnh này đẩy các LFS objects cần thiết cho các refs trong repository local lên endpoint của remote đích. Chạy nó sau khi đã lấy đủ LFS objects từ nguồn và trước khi mở quyền sử dụng remote mới cho thành viên.

Một thứ tự an toàn cho cutover:

1. Fetch refs mới nhất từ nguồn.
2. `git lfs fetch --all origin` để lấy các LFS objects cần thiết.
3. Đẩy Git refs lên đích.
4. `git lfs push --all target` để bảo đảm LFS storage đích có nội dung tương ứng.
5. Thử clone từ đích và tải LFS objects bằng `git lfs pull`.

Nếu hosting yêu cầu LFS objects phải tồn tại trước khi refs được công bố, có thể đẩy LFS objects lên đích trước bước đẩy refs. Dù chọn thứ tự nào, chỉ mở cutover khi cả refs và LFS content đã đầy đủ.

### Xác minh LFS sau migration

Tạo một clone thử từ remote đích:

```bash
git clone https://git.example.com/new/project.git verify-project
cd verify-project
git lfs pull
git lfs ls-files
```

Mở một số tệp lớn đại diện và kiểm tra nội dung, kích thước hoặc checksum theo quy trình dự án. Nếu working tree chỉ có pointer text, kiểm tra LFS endpoint, quyền truy cập và việc `git lfs pull` có tải object thành công không.

## 8. Di chuyển submodule và cập nhật URL

Submodule là một repository Git riêng. Superproject không lưu toàn bộ nội dung submodule; nó lưu một gitlink (mode `160000`) trỏ đến commit cụ thể trong repository con. Vì vậy, di chuyển superproject không tự động di chuyển các repository submodule.

### Kiểm kê submodule

Xem cấu hình:

```bash
git config --file .gitmodules --get-regexp 'submodule\..*\.path'
git config --file .gitmodules --get-regexp 'submodule\..*\.url'
git submodule status --recursive
```

Kiểm tra từng submodule và các submodule lồng nhau. Ghi lại URL, branch nếu có cấu hình, commit gitlink đang được superproject tham chiếu và các tệp LFS nếu repository con có dùng LFS.

### Di chuyển từng repository submodule

Mỗi submodule cần được chuyển branch, tag, refs, LFS và các submodule con theo quy trình tương ứng. Đảm bảo commit mà gitlink của superproject trỏ đến đã tồn tại trên remote submodule mới. Nếu chỉ chuyển branch tip mà thiếu commit cũ được gitlink tham chiếu, checkout superproject có thể thất bại.

Với từng repository submodule, có thể dùng clone/mirror riêng, kiểm tra refs và xác minh commit đích. Nếu submodule có LFS, chuyển LFS objects riêng như phần trước.

### Cập nhật URL trong superproject

Sau khi remote submodule mới sẵn sàng, sửa URL trong `.gitmodules` bằng lệnh phù hợp hoặc chỉnh file rồi commit:

```bash
git config -f .gitmodules submodule.shared-lib.url https://git.example.com/team/shared-lib.git
git add .gitmodules
git commit -m "chore: update submodule remote URLs"
```

Tên `shared-lib` phải khớp section submodule trong `.gitmodules`. Nếu dùng URL tương đối, kiểm tra cấu trúc namespace giữa superproject và submodule ở hosting mới; URL tương đối có thể tiếp tục hoạt động nếu vị trí repository được giữ tương ứng.

Trên clone đã tồn tại, đồng bộ URL từ `.gitmodules` vào cấu hình local:

```bash
git submodule sync --recursive
git submodule update --init --recursive
```

`sync` cập nhật URL trong cấu hình submodule local theo `.gitmodules`; nó không di chuyển nội dung repository con. `update --init --recursive` khởi tạo và checkout đúng commit gitlink, bao gồm submodule lồng nhau.

### Kiểm tra submodule

```bash
git submodule status --recursive
git -C path/to/shared-lib rev-parse HEAD
```

Trong output `git submodule status`, dấu đầu dòng có ý nghĩa: dấu cách thường cho biết submodule đang ở đúng commit được ghi trong superproject; `-` cho biết chưa được khởi tạo; `+` cho biết HEAD submodule khác gitlink; `U` cho biết xung đột gitlink. Hãy xác minh commit thực tế và quyền clone của từng submodule trước khi cutover.

## 9. Tag, annotated tag và chữ ký

Tag thường được chuyển cùng refs khi dùng `git push --tags` hoặc `git push --mirror`. Annotated tag là object riêng chứa tagger, message và có thể có chữ ký; nếu object được chuyển nguyên vẹn, metadata và chữ ký vẫn nằm trong tag object.

Sau khi chuyển, kiểm tra danh sách và một số tag quan trọng:

```bash
git ls-remote --tags target
git verify-tag v2.0.0
git show --show-signature v2.0.0
```

Chữ ký được bảo toàn trong object không đồng nghĩa máy mới đã tin cậy khóa ký. Máy xác minh cần có public key/certificate, allowed signers hoặc trust store theo chính sách. Với tag nhẹ (lightweight tag), không có tag object/chữ ký tag riêng.

Nếu remote đích đã có tag cùng tên nhưng trỏ đến object khác, push thông thường có thể từ chối. Không force-update tag phát hành đã chia sẻ nếu chưa có quyết định rõ ràng; tag thường được xem là mốc bất biến trong quy trình release.

## 10. Cấu hình remote không tự đi theo Git objects

Khi push commit và refs sang remote mới, URL remote và các thiết lập local của clone không tự chuyển theo. Sau migration, mỗi clone cần được cập nhật remote phù hợp.

Kiểm tra:

```bash
git remote -v
git branch -vv
```

Đổi URL remote hiện tại:

```bash
git remote set-url origin https://git.example.com/new/project.git
```

Hoặc thêm remote mới và giữ remote cũ trong giai đoạn xác minh:

```bash
git remote add new-origin https://git.example.com/new/project.git
git fetch new-origin --prune --tags
```

Nếu cần xem refspec hoặc push URL, dùng các lệnh đọc cấu hình phù hợp:

```bash
git config --get-regexp '^remote\.'
git config --get-regexp '^branch\.'
```

Các lệnh này có thể hiển thị URL nội bộ hoặc thông tin nhạy cảm được nhúng sai cách trong URL. Rà soát output trước khi chia sẻ. Ưu tiên credential helper hoặc SSH agent thay vì lưu token trực tiếp trong remote URL.

Sau khi đổi remote, kiểm tra upstream của branch. Nếu branch đang theo dõi remote cũ, cập nhật upstream bằng:

```bash
git branch --set-upstream-to=new-origin/main main
```

Lệnh cần được chạy với branch tồn tại và remote-tracking ref đã fetch. Có thể dùng `git push -u new-origin main` khi đẩy branch lần đầu để thiết lập upstream trong cùng thao tác.

## 11. Xác minh repository đích

Không nên xem migration hoàn tất chỉ vì lệnh push trả exit code `0`. Cần so sánh refs, kiểm tra object và thử clone độc lập từ đích.

### So sánh refs

Kiểm tra branch/tag trên remote đích:

```bash
git ls-remote --heads target
git ls-remote --tags target
git ls-remote --symref target HEAD
```

So sánh với danh sách đã ghi lại từ nguồn. Với mirror, có thể so sánh toàn bộ refs được phép quảng bá:

```bash
git ls-remote --refs origin
git ls-remote --refs target
```

Khác biệt có thể xuất phát từ namespace server không cho tạo, refs ẩn hoặc quy tắc hosting. Hãy phân loại từng khác biệt thay vì bỏ qua tất cả.

### Kiểm tra tính toàn vẹn và clone thử

```bash
git clone --recurse-submodules https://git.example.com/new/project.git verify-project
cd verify-project
git fsck --full
git submodule update --init --recursive
git lfs pull
```

Kiểm tra branch mặc định, tag phát hành, commit quan trọng, tệp LFS và từng submodule. Chạy build/test cơ bản để xác nhận clone từ remote mới có thể tái tạo môi trường làm việc.

### Kiểm tra cấu hình hosting

Xác nhận trên nền tảng đích:

- Branch mặc định trỏ đến branch mong muốn.
- Branch protection/ruleset được bật đúng.
- Thành viên, nhóm, deploy keys và bot có quyền phù hợp.
- CI workflow, secrets, variables, runners và webhook hoạt động.
- Release, package, wiki và tài liệu dự án đã được chuyển nếu nằm trong phạm vi.

## 12. Kế hoạch rollback

Trước khi cutover, xác định điều kiện để quay lại nguồn và cách xử lý thay đổi phát sinh sau khi mở remote đích.

Một kế hoạch rollback nên trả lời:

1. Ai có quyền quyết định quay lại nguồn?
2. Nguồn có còn read-only và giữ nguyên refs không?
3. Nếu đã có commit mới trên đích, sẽ chuyển ngược về nguồn bằng cách nào?
4. LFS objects mới được tạo trên đích đã có ở nguồn chưa?
5. URL trong submodule, CI, bot và clone của thành viên sẽ được đổi lại ra sao?
6. Thời hạn giữ remote cũ và backup là bao lâu?

Tránh cho cả nguồn và đích cùng nhận push trong thời gian dài. Nếu cần rollback sau khi đích đã nhận commit mới, phải đồng bộ các refs và LFS objects phát sinh trước khi mở lại nguồn. Không force-push hoặc mirror ngược mà chưa kiểm kê thay đổi ở cả hai phía.

## 13. Checklist migration tham khảo

### Trước migration

- [ ] Kiểm kê remote, refs, branch, tag, notes và namespace tùy chỉnh.
- [ ] Ghi lại branch mặc định và commit quan trọng.
- [ ] Kiểm tra `git fsck --full` và đo dung lượng object/LFS.
- [ ] Kiểm kê `.gitattributes`, `.lfsconfig` và danh sách LFS objects.
- [ ] Kiểm kê `.gitmodules`, submodule lồng nhau và commit gitlink.
- [ ] Tạo backup có thể khôi phục.
- [ ] Tạo repository đích, xác nhận quota, LFS và quyền truy cập.
- [ ] Lập danh sách dữ liệu hosting/CI cần chuyển riêng.

### Trong migration

- [ ] Chọn push branch/tag riêng hoặc mirror trong bare clone.
- [ ] Không dùng `--mirror` lên đích có dữ liệu cần giữ nếu chưa được phê duyệt.
- [ ] Fetch đủ refs và đồng bộ lần cuối trong cửa sổ freeze.
- [ ] Chuyển LFS objects cho tất cả refs cần giữ.
- [ ] Di chuyển từng submodule và cập nhật URL trong `.gitmodules`.
- [ ] Giữ nguồn read-only trong thời gian xác minh.

### Sau migration

- [ ] So sánh refs và tag trên nguồn/đích.
- [ ] Xác minh chữ ký tag/commit theo trust store của môi trường mới.
- [ ] Clone thử từ đích, chạy `git fsck --full`, `git lfs pull` và cập nhật submodule.
- [ ] Kiểm tra branch mặc định, protection, quyền, CI, webhook và secrets.
- [ ] Cập nhật remote URL/upstream trong clone, bot và tài liệu.
- [ ] Chạy build/test đại diện và xác nhận nhóm có thể làm việc.
- [ ] Duy trì backup và kế hoạch rollback theo thời hạn đã thống nhất.

## 14. Những hiểu nhầm thường gặp

| Hiểu nhầm | Cách hiểu đúng |
|---|---|
| `git push --all` chuyển toàn bộ repository | Nó đẩy branch local; tag và namespace khác cần thao tác riêng |
| `git push --tags` đẩy cả branch | Nó chỉ đẩy tag local |
| `git push --mirror` an toàn với mọi remote | Nó có thể force-update và xóa refs ở đích; chỉ dùng khi đã kiểm soát phạm vi |
| Mirror Git là đã chuyển cả Git LFS | LFS objects nằm trong storage riêng và cần fetch/push riêng |
| Superproject chứa toàn bộ source submodule | Superproject chỉ ghi gitlink đến commit của repository con |
| Push Git refs sẽ tự đổi URL remote trong clone của thành viên | Remote URL và upstream là cấu hình local cần cập nhật |
| Tag ký hợp lệ nghĩa máy mới tự tin cậy signer | Cần cấu hình public key, fingerprint, allowed signers hoặc trust store |
| Git migration chuyển cả PR, issue và branch protection | Dữ liệu hosting/CI cần được chuyển bằng công cụ hoặc cấu hình riêng |
| Có thể mở remote mới ngay sau lần push đầu | Cần đồng bộ cuối, kiểm tra LFS/submodule và xác minh clone từ đích |

## 15. Ghi nhớ

Một kế hoạch di chuyển remote đầy đủ cần quản lý riêng Git objects/refs, Git LFS, submodule và cấu hình hosting. Với clone thông thường, `git push --all` chuyển branch local và `git push --tags` chuyển tag; với yêu cầu mirror refs, dùng bare mirror clone và `git push --mirror` chỉ sau khi xác nhận remote đích có thể bị force-update hoặc xóa refs.

Git LFS cần `git lfs fetch --all` từ nguồn và `git lfs push --all` lên đích. Mỗi submodule phải có repository đích chứa commit gitlink, URL trong `.gitmodules` cần cập nhật và clone cần chạy `git submodule sync --recursive` rồi `git submodule update --init --recursive`.

Cuối cùng, đóng băng ghi ở nguồn, đồng bộ lần cuối, xác minh refs/LFS/submodule bằng clone thử, cấu hình branch mặc định và quyền trên hosting, rồi mới chuyển người dùng sang remote mới. Giữ nguồn và backup trong thời hạn rollback để có thể xử lý sai lệch mà không mất lịch sử quan trọng.
