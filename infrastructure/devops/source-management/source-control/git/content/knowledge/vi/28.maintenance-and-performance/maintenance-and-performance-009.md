# Kho bare, mirror clone và ý nghĩa của mirror push

Git có thể lưu repository mà không cần working tree. Repository dạng này gọi là **bare repository** và thường được dùng làm remote trung tâm để nhiều người push/fetch. Một cách sử dụng khác là tạo **mirror clone** để sao chép các ref và object Git từ một repository nguồn. Khi cần đồng bộ bản sao sang đích, `git push --mirror` cập nhật toàn bộ ref, bao gồm cả việc ghi đè hoặc xóa ref ở đích.

Ba khái niệm có liên quan nhưng không đồng nghĩa: bare mô tả cấu trúc repository không có working tree; mirror clone mô tả cách clone và ánh xạ ref; mirror push mô tả phạm vi cập nhật ref lên remote. Hiểu đúng sự khác nhau giúp bạn dựng remote dùng chung, tạo bản sao dự phòng và tránh vô tình xóa branch hoặc tag trên máy chủ.

## 1. Bare repository là gì?

Một repository thông thường có working tree, index và thư mục Git metadata. Bạn checkout branch, chỉnh sửa file, stage và commit trong working tree đó. Bare repository chỉ có dữ liệu Git cần thiết như object database, refs và cấu hình repository; nó không có working tree để chỉnh sửa file theo cách thông thường.

Ví dụ cấu trúc rút gọn:

```text
Repository thông thường           Bare repository
project/                           project.git/
|-- .git/                           |-- objects/
|   |-- objects/                    |-- refs/
|   |-- refs/                       |-- HEAD
|   `-- HEAD                        |-- config
|-- src/                            `-- ...
`-- README.md
```

Trong repository thường, thư mục `.git` chứa metadata và object database. Với bare repository, nội dung tương ứng nằm ngay ở gốc thư mục `project.git`; không có thư mục `.git` lồng bên trong và không có file dự án được checkout thành working tree.

Bare repository phù hợp để làm remote nhận push vì máy chủ không cần một branch đang checkout vào working tree. Khi client push commit, Git cập nhật object database và refs trong bare repository. Người dùng khác fetch các refs đó về clone của họ.

Bare repository không tự biến thành một dịch vụ mạng. Nó chỉ là repository trên đĩa; để người khác truy cập, bạn cần cung cấp nó qua SSH, Git protocol, HTTP(S) hoặc cơ chế hosting phù hợp và cấu hình quyền truy cập.

## 2. Tạo bare repository làm remote trung tâm

Tạo một bare repository mới:

```bash
git init --bare --initial-branch=main /srv/git/storefront.git
```

`--bare` tạo repository không có working tree. `--initial-branch=main` đặt branch mặc định ban đầu là `main` trên các phiên bản Git hỗ trợ tùy chọn này. Nếu phiên bản Git chưa hỗ trợ, có thể tạo repository rồi đặt symbolic `HEAD`:

```bash
git init --bare /srv/git/storefront.git
git --git-dir=/srv/git/storefront.git symbolic-ref HEAD refs/heads/main
```

Từ repository làm việc, thêm remote và push branch:

```bash
git remote add origin ssh://git@git.example.com/srv/git/storefront.git
git push -u origin main
```

Sau khi push, bare repository có ref `refs/heads/main` trỏ tới commit vừa gửi. Thành viên khác có thể clone:

```bash
git clone ssh://git@git.example.com/srv/git/storefront.git
```

Nếu nhiều người cùng sử dụng bare repository, hãy quản lý quyền ghi, xác thực SSH, backup và hook phía server. Không mở quyền ghi tùy tiện vào thư mục repository; quyền filesystem và chính sách nhận push cần được cấu hình theo mô hình triển khai.

### Xem bare repository

Nếu đang ở bên trong bare repository, kiểm tra:

```bash
git rev-parse --is-bare-repository
git show-ref
git symbolic-ref HEAD
```

Kết quả `true` xác nhận repository hiện tại là bare. `show-ref` liệt kê các refs đang có; `symbolic-ref HEAD` cho biết branch mặc định mà `HEAD` của bare repository trỏ tới, nếu nó là symbolic ref.

Bạn cũng có thể chạy lệnh từ ngoài thư mục bằng cách chỉ rõ Git directory:

```bash
git --git-dir=/srv/git/storefront.git show-ref
```

Không dùng `git switch` hoặc `git checkout` để tạo working tree trong bare repository. Hãy clone repository sang một thư mục làm việc thông thường nếu cần sửa file.

## 3. Phân biệt git clone --bare và git clone --mirror

Hai tùy chọn đều tạo repository không có working tree, nhưng phạm vi refs và cấu hình khác nhau.

### `git clone --bare`

```bash
git clone --bare https://git.example.com/platform/storefront.git storefront-bare.git
```

Lệnh tạo bare clone. Các branch heads được sao chép trực tiếp thành branch refs trong repository đích, thay vì tạo remote-tracking branch như clone thông thường. Clone bare không tạo working tree và không thiết lập hành vi mirror toàn bộ refs.

Đây là lựa chọn phù hợp khi bạn cần một repository bare để lưu hoặc phục vụ các branch thông thường. Nếu mục tiêu là sao chép mọi ref mà remote công bố, gồm cả những ref ngoài branch và tag thông thường, hãy xem `--mirror`.

### `git clone --mirror`

```bash
git clone --mirror https://git.example.com/platform/storefront.git storefront-mirror.git
```

`--mirror` bao hàm chế độ bare và cấu hình repository để mirror các refs. Thay vì chỉ lấy các branch heads và tags thông thường, nó ánh xạ toàn bộ namespace `refs/*` mà remote công bố sang cùng namespace trong local. Mirror clone thường có cấu hình tương tự:

```ini
[remote "origin"]
    url = https://git.example.com/platform/storefront.git
    fetch = +refs/*:refs/*
    mirror = true
```

Refspec `+refs/*:refs/*` ánh xạ refs từ remote vào đúng tên ref trong repository mirror. Dấu `+` cho phép cập nhật ref kể cả khi không phải fast-forward. Cấu hình mirror cũng ảnh hưởng hành vi push mặc định tới remote đó; vì vậy, cần kiểm tra remote trước khi chạy lệnh push trong mirror clone.

### Bảng so sánh

| Tiêu chí | Clone thông thường | `--bare` | `--mirror` |
|---|---|---|---|
| Có working tree | Có | Không | Không |
| Có branch local và remote-tracking branch theo cách thông thường | Có | Không tạo remote-tracking branch thông thường | Không ánh xạ theo kiểu remote-tracking; refs được đặt cùng namespace |
| Lấy branch và tag | Theo cấu hình clone/fetch | Branch heads và refs thông thường theo quy tắc bare clone | Tất cả refs được remote công bố trong phạm vi mirror |
| Cấu hình fetch `+refs/*:refs/*` | Không | Không mặc định | Có |
| Dùng làm bản sao mirror toàn bộ refs | Không phải mục đích mặc định | Không đầy đủ bằng mirror | Có |

Không nên coi `--bare` và `--mirror` là hai cách viết tương đương. Nếu cần sao lưu/nhân bản repository theo refs, `--mirror` thể hiện ý định rõ ràng hơn.

## 4. Mirror clone đồng bộ những gì?

Mirror clone lấy các refs mà remote cho phép client nhìn thấy và các Git object reachable từ những refs đó. Các refs có thể gồm:

- Branches trong `refs/heads/`.
- Tags trong `refs/tags/`.
- Notes, refs thay thế hoặc namespace tùy chỉnh khác nếu server công bố chúng.
- Các refs phục vụ workflow riêng của nền tảng nếu chúng được phép quảng bá qua giao thức.

Do mirror clone ánh xạ `refs/*`, nó có thể lưu các ref ngoài `heads` và `tags` mà clone thông thường không tạo thành remote-tracking branch. Tuy nhiên, server có thể ẩn một số refs bằng cấu hình hoặc chính sách hosting. Mirror không thể sao chép những refs mà remote không công bố hoặc không cho phép truy cập.

Kiểm tra refs trong mirror clone:

```bash
git show-ref
git for-each-ref --format="%(refname) %(objectname)"
```

Lệnh thứ hai liệt kê tên ref và OID để bạn so sánh với nguồn. Nếu cần đối chiếu từ xa, dùng:

```bash
git ls-remote --refs origin
```

`ls-remote` chỉ hiển thị refs remote công bố; nó không tải object về local.

## 5. Cập nhật mirror clone từ nguồn

Sau khi tạo mirror clone, các branch hoặc tag trên nguồn có thể thay đổi. Để cập nhật refs trong mirror, fetch từ remote nguồn:

```bash
git fetch --prune origin
```

Vì mirror clone có refspec `+refs/*:refs/*`, fetch sẽ cập nhật refs theo namespace được cấu hình. `--prune` xóa các ref local thuộc refspec fetch nếu chúng không còn tồn tại trên remote, giúp mirror phản ánh việc xóa ref ở nguồn.

Có thể xem cấu hình trước khi fetch:

```bash
git config --get-all remote.origin.fetch
git config --get remote.origin.mirror
```

Với mirror clone, không nên giả định một lệnh fetch trong clone thường có cùng phạm vi. Hãy kiểm tra refspec thực tế để biết những refs nào sẽ được cập nhật.

Nếu có nhiều remote hoặc nhiều nhóm remote, `git remote update` có thể fetch nhiều nguồn theo cấu hình. Trong quy trình mirror một nguồn, chỉ rõ `origin` giúp giới hạn phạm vi và dễ kiểm soát hơn.

## 6. git push --mirror có ý nghĩa gì?

Lệnh:

```bash
git push --mirror <remote>
```

yêu cầu Git đồng bộ toàn bộ refs trong namespace `refs/` của repository local lên remote đích. Hành vi gồm ba điểm quan trọng:

1. **Tạo refs mới:** ref có ở local nhưng chưa có ở remote sẽ được tạo.
2. **Cập nhật cưỡng bức refs hiện có:** ref đích có thể bị di chuyển tới OID local ngay cả khi cập nhật không phải fast-forward.
3. **Xóa refs ở remote:** ref có trên remote nhưng không còn tồn tại ở local sẽ bị xóa.

Do đó, mirror push không chỉ là push tất cả branch. Nó có thể cập nhật tags, notes và các namespace ref khác, đồng thời xóa ref không có trong bản mirror local.

Ví dụ:

```bash
git push --mirror backup
```

Lệnh này thích hợp khi `backup` là repository đích được quản lý như một bản mirror của nguồn. Không dùng nó một cách tùy tiện với remote đang có branch hoặc tag riêng mà bạn muốn giữ.

### Vì sao mirror push có thể nguy hiểm?

Giả sử remote đích có ba ref:

```text
refs/heads/main
refs/heads/release
refs/tags/v1.0
```

Trong khi local mirror chỉ có `main` và tag `v1.0`. Khi chạy `git push --mirror`, ref `refs/heads/release` ở remote có thể bị xóa vì không tồn tại trong local mirror. Nếu local `main` đã viết lại lịch sử, remote `main` cũng có thể bị force update.

Vì vậy, trước khi chạy mirror push:

- Xác nhận đúng remote đích và đúng repository.
- Kiểm tra các refs local và remote.
- Xác nhận đích được dành riêng cho mirror hoặc đã thống nhất rằng mọi refs ở đích phải khớp nguồn.
- Kiểm tra branch protection, quyền xóa ref và chính sách hosting.
- Có backup hoặc khả năng phục hồi nếu mirror push ghi đè/xóa ref ngoài dự kiến.

Không dùng `git push --mirror` để cập nhật một vài branch. Với nhu cầu thông thường, dùng `git push origin main` hoặc refspec cụ thể để giới hạn phạm vi.

## 7. Quy trình tạo và cập nhật bản mirror dự phòng

Giả sử repository nguồn là `origin` và bạn muốn duy trì một bare mirror ở máy chủ backup.

### Tạo mirror clone lần đầu

```bash
git clone --mirror https://git.example.com/platform/storefront.git storefront-mirror.git
```

Clone này đã có remote `origin` trỏ về nguồn. Thêm remote backup:

```bash
cd storefront-mirror.git
git remote add backup ssh://git@backup.example.com/srv/git/storefront.git
```

Repository đích `storefront.git` nên được tạo dưới dạng bare và được dành riêng cho bản mirror. Nếu chưa có:

```bash
ssh git@backup.example.com 'git init --bare /srv/git/storefront.git'
```

Lệnh khởi tạo từ xa cần quyền truy cập shell và quyền ghi thư mục phù hợp. Nếu nền tảng backup đã cấp repository bare, không cần tự khởi tạo lại.

Đẩy toàn bộ refs local lên backup:

```bash
git push --mirror backup
```

### Cập nhật mirror định kỳ

Mỗi lần đồng bộ:

```bash
git fetch --prune origin
git push --mirror backup
```

Lệnh fetch cập nhật mirror local từ nguồn và xóa refs local đã bị xóa ở nguồn theo refspec. Mirror push sau đó đồng bộ refs local sang đích, bao gồm cả xóa refs ở đích nếu chúng không còn ở local.

Nếu muốn tự động hóa, hãy chạy quy trình trong một job có quyền đọc nguồn và quyền ghi backup, có log, cảnh báo lỗi và lịch sử lần chạy. Tránh để nhiều job mirror push cùng ghi vào một repository đích nếu không có cơ chế điều phối.

### Kiểm tra sau đồng bộ

So sánh refs:

```bash
git ls-remote --refs origin
git ls-remote --refs backup
git show-ref
```

Kết quả phải phù hợp với chính sách mirror. Một số hosting có thể từ chối refs nội bộ hoặc refs được bảo vệ; khi đó, mirror không thể được coi là hoàn chỉnh nếu không xử lý rõ các khác biệt đó.

## 8. Cẩn trọng với remote.origin.mirror trong mirror clone

Mirror clone thường cấu hình:

```ini
remote.origin.mirror = true
```

Thiết lập này cho biết remote được xem là mirror trong hành vi push. Vì thế, khi đang ở trong mirror clone, không nên chạy lệnh `git push` không có remote mà không kiểm tra cấu hình push mặc định và remote được chọn. Có nguy cơ bạn thực hiện mirror push ngược lên repository nguồn.

Kiểm tra cấu hình:

```bash
git remote -v
git config --show-origin --get-regexp '^remote\..*\.(url|mirror|fetch)$'
git config --get push.default
```

Trong quy trình dự phòng, chỉ định remote đích một cách tường minh:

```bash
git push --mirror backup
```

Không sửa `remote.origin.mirror` nếu chưa hiểu hệ quả đối với fetch/push của mirror clone. Nếu muốn dùng repository đó cho một mục đích khác, hãy cân nhắc tạo clone thường riêng để làm việc hằng ngày.

## 9. Bare remote, mirror backup và working clone khác nhau

| Mục đích | Kiểu repository phù hợp | Lý do |
|---|---|---|
| Remote trung tâm nhận push của nhiều developer | Bare repository | Không có working tree đang checkout; phù hợp nhận ref updates |
| Bản sao refs/object từ một remote khác | Mirror clone | Ánh xạ toàn bộ refs được công bố và hỗ trợ mirror push |
| Nơi developer chỉnh sửa và commit | Clone thông thường | Có working tree, index và branch làm việc |
| Bản sao chỉ lấy một vài branch | Clone thường hoặc bare với refspec phù hợp | Không cần đồng bộ mọi namespace ref |

Một bare repository có thể là remote trung tâm mà không phải mirror của repository nào khác. Ngược lại, mirror clone cũng là bare repository, nhưng có cấu hình refspec và mirror nhằm sao chép refs từ nguồn.

## 10. Mirror không phải bản sao lưu toàn bộ dịch vụ hosting

`git clone --mirror` sao chép Git refs và object mà remote công bố và cho phép truy cập. Nó không mặc nhiên sao lưu toàn bộ dữ liệu và cấu hình của nền tảng hosting.

Các thành phần có thể cần backup riêng:

- **Pull request/merge request, issue, review và comment:** thường nằm trong cơ sở dữ liệu của dịch vụ hosting.
- **Release, artifact và file đính kèm:** có thể được lưu ngoài Git object database.
- **Hooks, branch protection, quyền truy cập và deploy key:** là cấu hình phía server, không được clone mirror sao chép.
- **Reflog:** là nhật ký cục bộ, không phải namespace ref được mirror push đồng bộ.
- **Git LFS objects:** pointer nằm trong Git, nhưng nội dung LFS được lưu ở endpoint riêng. Cần dùng các lệnh Git LFS phù hợp để tải và đẩy toàn bộ LFS object, ví dụ `git lfs fetch --all origin` và `git lfs push --all backup`, sau khi xác minh endpoint và quyền truy cập.
- **Nội dung repository submodule:** superproject chỉ lưu gitlink commit SHA. Mỗi repository submodule cần được mirror và backup riêng.
- **Refs bị ẩn hoặc không được server quảng bá:** mirror clone không thể lấy những refs mà server không cho truy cập.
- **HEAD mặc định và cấu hình repository:** `HEAD` là symbolic ref ở gốc repository, không nằm dưới `refs/`, nên `git push --mirror` không đồng bộ branch mặc định của bare đích. Cần cấu hình `HEAD` ở đích riêng, đồng thời sao lưu cấu hình và hook server nếu cần tái tạo môi trường.

Vì vậy, hãy xác định mục tiêu backup là Git repository hay toàn bộ dịch vụ phát triển phần mềm. Nếu cần khả năng khôi phục toàn diện, phối hợp mirror Git với backup database, cấu hình hosting, LFS storage, artifact và repository submodule.

## 11. Lưu ý về quyền, bảo vệ ref và dữ liệu

- **Dùng đích riêng cho mirror.** Không mirror push vào repository đang chứa branch cá nhân hoặc refs không thuộc nguồn.
- **Giới hạn quyền ghi.** Tài khoản đồng bộ chỉ nên có quyền cần thiết trên repository backup.
- **Bảo vệ nguồn.** Mirror clone là bản sao; không dùng nó làm working clone để phát triển và push ngược vào nguồn.
- **Xác thực URL.** Kiểm tra `git remote -v` trước mỗi lần push; tránh nhầm nguồn và đích.
- **Xem xét branch protection.** Máy chủ có thể từ chối force update hoặc xóa refs được bảo vệ. Không tắt bảo vệ chỉ để làm mirror push thành công nếu chưa có phê duyệt.
- **Lưu log đồng bộ.** Ghi lại thời gian, nguồn, đích, refs thay đổi và lỗi để điều tra khi backup không nhất quán.
- **Kiểm tra khả năng phục hồi.** Định kỳ clone từ bản backup vào thư mục thử nghiệm và xác minh branch, tag, commit cần thiết.

Mirror push là thao tác đồng bộ trạng thái refs, không phải thao tác append-only. Một nguồn bị xóa nhầm branch/tag rồi được mirror push có thể làm bản backup xóa theo. Nếu cần backup có khả năng giữ lại lịch sử đã bị xóa ở nguồn, hãy duy trì snapshot/backup bất biến theo thời gian bên cạnh mirror cập nhật liên tục.

## 12. Bài tập thực hành

Trong môi trường thử nghiệm, tạo một repository nguồn có branch `main`, branch `feature/demo`, tag `v1.0` và một ref tùy chỉnh nếu đã biết cách tạo. Không dùng remote sản xuất cho bài tập.

1. Tạo bare repository bằng `git init --bare` và push branch lên đó.
2. Tạo clone bằng `git clone --bare` và quan sát refs bằng `git show-ref`.
3. Tạo clone khác bằng `git clone --mirror`, đọc `remote.origin.fetch` và `remote.origin.mirror`.
4. Tạo một bare repository đích dành riêng cho backup, thêm nó làm remote `backup` trong mirror clone.
5. Chạy `git push --mirror backup`, rồi so sánh `git ls-remote --refs` giữa nguồn và đích.
6. Xóa một branch thử nghiệm ở nguồn, chạy `git fetch --prune origin` trong mirror clone và `git push --mirror backup`; quan sát branch tương ứng bị xóa ở đích.
7. Tạo một ref riêng chỉ ở đích trong repository thử nghiệm, sau đó quan sát vì sao lần mirror push tiếp theo có thể xóa ref đó.
8. Liệt kê những dữ liệu hosting, LFS và submodule mà mirror Git không tự sao lưu.

Bạn hoàn thành bài tập khi giải thích được bare repository dùng làm remote như thế nào, `--bare` khác `--mirror` ra sao và vì sao `git push --mirror` có thể tạo, ghi đè lẫn xóa refs trên remote đích.
