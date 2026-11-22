# Sao lưu có kiểm chứng và phân biệt bản mirror với bản sao lưu lịch sử

Repository Git lưu lịch sử bằng object và refs, nhưng một bản sao repository chưa chắc là một bản sao lưu có thể phục hồi sau sự cố. Nếu bản sao được đồng bộ liên tục theo trạng thái hiện tại, việc xóa branch hoặc viết lại lịch sử ở nguồn có thể lan sang bản sao. Một bản backup đúng nghĩa cần giữ được các mốc lịch sử tại những thời điểm khác nhau, được kiểm tra tính toàn vẹn và có thể khôi phục trong một môi trường độc lập.

Bài học thuộc chương **Bảo trì và hiệu năng** của module SOURCE_CONTROL_GIT. Module hướng dẫn working tree, staging area, commit, lịch sử, branch, merge, rebase, remote và tag; sao lưu có kiểm chứng giúp bảo vệ lịch sử cộng tác và bảo đảm có thể phục hồi khi repository gặp sự cố.

## 1. Mirror và backup lịch sử giải quyết hai nhu cầu khác nhau

**Mirror** là bản sao phản ánh các refs và object hiện có của repository nguồn. Nó hữu ích khi cần một replica gần với trạng thái hiện tại để phục vụ chuyển máy chủ, dự phòng truy cập hoặc tạo bản sao đồng bộ.

**Backup lịch sử** là các bản chụp được giữ lại theo thời điểm, có chính sách retention và không bị thay thế ngay khi nguồn thay đổi. Nó giúp khôi phục branch, tag hoặc commit đã bị xóa hay viết lại.

| Đặc điểm | Mirror | Backup lịch sử theo thời điểm |
| --- | --- | --- |
| Mục tiêu | Phản ánh refs hiện tại của nguồn | Giữ các mốc repository tại nhiều thời điểm |
| Cập nhật | Đồng bộ theo lịch hoặc theo yêu cầu | Tạo snapshot mới, giữ snapshot cũ theo retention |
| Khi nguồn xóa branch | Mirror có thể xóa ref tương ứng khi prune | Snapshot cũ vẫn giữ ref và object nếu được lưu riêng |
| Khi nguồn force-push | Mirror có thể chuyển ref sang lịch sử mới | Snapshot trước đó vẫn giữ commit cũ |
| Phục hồi lịch sử đã mất ở nguồn | Có thể không còn bản cũ | Có thể chọn snapshot trước sự cố |
| Phù hợp | Replica, migration, standby | Disaster recovery, audit, phục hồi lịch sử |

Một mirror rất hữu ích, nhưng không nên là bản backup duy nhất. Nếu mirror được đồng bộ với prune hoặc phản ánh ref bị force-update, nó có thể tiếp nhận chính thay đổi phá hủy mà bạn đang muốn phục hồi.

## 2. Tạo mirror bằng git clone --mirror

Để tạo mirror của một repository từ xa:

~~~bash
git clone --mirror https://example.com/team/app.git /backup/app.git
~~~

`--mirror` tạo một bare repository và cấu hình fetch để ánh xạ toàn bộ refs từ nguồn vào repository đích. Mirror không có working tree thông thường. Nó phù hợp để lưu một bản sao refs/object phục vụ đồng bộ và migration.

Kiểm tra repository mirror:

~~~bash
git -C /backup/app.git rev-parse --is-bare-repository
git -C /backup/app.git show-ref
git -C /backup/app.git remote -v
~~~

`rev-parse` thường trả `true` vì mirror là bare repository. `show-ref` liệt kê các refs hiện có, còn `remote -v` hiển thị nguồn mirror.

### Cập nhật mirror

Có thể cập nhật mirror từ nguồn bằng:

~~~bash
git -C /backup/app.git remote update --prune
~~~

`remote update` fetch các remote được cấu hình; `--prune` xóa refs đã bị nguồn xóa theo refspec tương ứng. Với mirror clone, refspec được thiết lập để ánh xạ rộng các refs.

Đây là hành vi phù hợp khi mục tiêu là replica phản ánh trạng thái hiện tại. Tuy nhiên, nếu branch bị xóa hoặc force-push ở nguồn, mirror có thể cũng loại bỏ hoặc di chuyển ref đó. Khi commit cũ không còn được tham chiếu, Git có thể dọn object không còn reachable sau các chu kỳ maintenance/GC.

### Cẩn thận với git push --mirror

`git push --mirror` đồng bộ toàn bộ refs từ repository local lên remote đích. Các refs không có ở nguồn có thể bị xóa ở đích; refs hiện có có thể bị force-update để khớp nguồn.

~~~bash
git push --mirror backup
~~~

Chỉ dùng lệnh này khi remote đích được dành riêng làm mirror và bạn chủ ý muốn đồng bộ toàn bộ namespace refs. Không chạy trên remote làm việc chính hoặc repository có refs riêng cần giữ. Trước khi chạy, kiểm tra `git remote -v`, `git show-ref` và xác nhận rõ remote đích.

## 3. Vì sao mirror không phải backup lịch sử bất biến?

Giả sử repository nguồn có branch `main` trỏ đến commit A. Mirror cũng có `main` trỏ đến A.

Sau đó ai đó force-push nguồn để `main` trỏ đến commit B. Khi mirror cập nhật, ref `main` cũng chuyển từ A sang B. Nếu không còn ref nào giữ A, commit A có thể trở thành unreachable trong mirror. Sau thời gian và quy trình garbage collection, object A có thể bị thu hồi.

Tương tự, khi một branch bị xóa ở nguồn và mirror chạy với prune, ref branch đó bị xóa khỏi mirror. Mirror phản ánh trạng thái hiện tại chính xác, nhưng không tự giữ bản lịch sử cũ.

Một mirror không prune có thể giữ một số refs đã biến mất ở nguồn, nhưng không giải quyết đầy đủ việc force-push thay thế refs hiện tại. Không nên dựa vào refs stale hoặc object dangling như một chính sách backup có thể kiểm chứng.

Để giữ lịch sử, hãy tạo snapshot có tên và thời điểm riêng, hoặc dùng hệ thống backup có versioning/immutability. Không ghi đè snapshot cũ khi tạo bản mới.

## 4. Tạo snapshot lịch sử bằng Git bundle

Git bundle đóng gói object và refs thành một tệp có thể lưu trữ hoặc chuyển sang máy khác. Bundle rất hữu ích cho backup point-in-time, lưu trữ offline và chuyển lịch sử giữa các hệ thống.

Tạo một bundle đầy đủ từ các refs hiện có:

~~~bash
git bundle create /backup/app-2026-11-17.bundle --all
~~~

`--all` yêu cầu đưa các refs vào bundle; Git đóng gói các object cần thiết để phục hồi những refs đó. Mỗi lần backup nên tạo tên file riêng theo thời điểm hoặc mã snapshot, thay vì ghi đè bản cũ.

Xem các refs có trong bundle:

~~~bash
git bundle list-heads /backup/app-2026-11-17.bundle
~~~

Kiểm tra bundle:

~~~bash
git bundle verify /backup/app-2026-11-17.bundle
~~~

`verify` kiểm tra cấu trúc bundle và các prerequisite cần thiết. Một bundle độc lập được tạo từ toàn bộ refs sẽ không yêu cầu commit prerequisite từ repository khác. Nếu tạo bundle incremental, prerequisite phải có sẵn khi khôi phục.

### Khôi phục từ bundle vào repository mới

Có thể clone trực tiếp từ bundle:

~~~bash
git clone /backup/app-2026-11-17.bundle /restore/app
~~~

Sau đó kiểm tra refs và lịch sử:

~~~bash
git -C /restore/app show-ref
git -C /restore/app log --oneline --decorate --all -20
git -C /restore/app fsck --full
~~~

Khôi phục vào thư mục mới giúp kiểm tra độc lập mà không ảnh hưởng repository đang hoạt động. Sau khi xác minh branch, tag và commit cần thiết, mới chuyển repository phục hồi vào quy trình sử dụng.

### Bundle lưu gì và không lưu gì?

| Thành phần | Bundle có bao gồm? |
| --- | --- |
| Commit, tree, blob reachable từ refs được đóng gói | Có |
| Branch/tag refs được chọn trong bundle | Có |
| Object chỉ còn trong reflog hoặc unreachable, không được refs giữ | Không mặc định |
| Working tree chưa commit | Không |
| Tệp untracked/ignored | Không |
| Git config, hooks và credential | Không |
| Git LFS object thực tế | Không; Git chỉ lưu pointer blob |
| Repository của submodule | Không; superproject chỉ lưu gitlink commit |

Bundle là backup lịch sử Git ở mức refs/object. Để bảo vệ toàn bộ môi trường phát triển, cần sao lưu thêm những thành phần ngoài phạm vi bundle.

## 5. Bảo vệ commit đã bị xóa hoặc viết lại

Bundle với `--all` lưu object reachable từ refs. Nếu một commit chỉ còn trong reflog hoặc dangling object, nó có thể không nằm trong bundle thông thường.

Nếu phát hiện một commit quan trọng sắp mất ref, hãy tạo một ref backup có tên rõ ràng trước khi garbage collection loại object:

~~~bash
git branch backup/recovered-commit <commit-id>
~~~

Hoặc tạo tag backup nếu chính sách repository cho phép:

~~~bash
git tag backup/pre-rewrite-2026-11-17 <commit-id>
~~~

Sau đó tạo bundle với `--all` để đưa ref backup vào snapshot. Không tạo ref tùy tiện trên repository dùng chung; đặt namespace và retention rõ ràng để tránh lẫn với branch phát triển.

Nếu đang điều tra commit đã mất, có thể xem reflog:

~~~bash
git reflog --all
~~~

Reflog hữu ích để tìm commit mà branch từng trỏ tới, nhưng reflog có thời hạn lưu và có thể bị expire. Nó là công cụ phục hồi ngắn hạn, không phải backup dài hạn.

## 6. Sao lưu mirror theo cách có thể phục hồi

Một quy trình thường dùng là duy trì mirror để có replica nhanh, đồng thời tạo snapshot độc lập định kỳ:

~~~text
Repository nguồn
      |
      +----> Mirror cập nhật theo lịch
      |
      +----> Snapshot bundle theo thời điểm
                   |
                   +----> Lưu trữ versioned/offline
                   |
                   +----> Kiểm tra và diễn tập restore
~~~

Ví dụ lịch vận hành:

| Tác vụ | Tần suất gợi ý | Mục đích |
| --- | --- | --- |
| Cập nhật mirror | Theo giờ hoặc theo ngày tùy mức thay đổi | Có replica gần trạng thái hiện tại |
| Tạo bundle snapshot | Hằng ngày hoặc theo mốc release | Giữ refs/object tại thời điểm cụ thể |
| Kiểm tra bundle | Sau mỗi lần tạo | Phát hiện snapshot lỗi sớm |
| Restore drill | Định kỳ theo RPO/RTO | Xác minh thực sự phục hồi được |
| Lưu bản offline/immutable | Theo chính sách retention | Bảo vệ khi tài khoản hoặc máy chủ nguồn bị xâm nhập |

Không lưu tất cả backup duy nhất trên cùng server, volume hoặc credential domain với repository nguồn. Nếu sự cố xóa dữ liệu hoặc ransomware tác động đến nguồn, bản backup cùng vùng có thể bị ảnh hưởng theo.

## 7. Tính nhất quán khi sao lưu repository đang hoạt động

Repository có thể được cập nhật trong khi backup đang chạy. Nếu nhiều refs thay đổi giữa lúc liệt kê refs và đóng gói object, snapshot có thể không đại diện cho một trạng thái nghiệp vụ mà nhóm mong muốn.

Với repository server-side hoặc hệ thống có nhiều lần push đồng thời, hãy dùng snapshot/storage backup được nền tảng hỗ trợ hoặc tạm dừng ghi trong cửa sổ backup để có điểm nhất quán rõ ràng. Nếu tạo bundle từ bản clone riêng đã fetch xong, hãy ghi lại thời điểm và refs đã được lấy.

Đối với backup filesystem của bare repository, cần bảo đảm snapshot bao phủ nhất quán toàn bộ Git directory, bao gồm object database, refs và packed-refs. Không copy một vài thư mục riêng lẻ trong khi Git đang cập nhật chúng rồi coi đó là bản backup hợp lệ.

Sau khi tạo snapshot, lưu metadata đi kèm:

- Tên repository và nguồn backup.
- Thời điểm snapshot, múi giờ và mã lần chạy.
- Phiên bản Git và phương thức backup.
- Danh sách refs hoặc output `git bundle list-heads`.
- Kết quả verify/fsck.
- Hash/checksum của file backup.
- Vị trí lưu trữ và thời hạn retention.

## 8. Xác minh tính toàn vẹn

Một backup chỉ hữu ích khi có thể đọc và khôi phục. Hãy kiểm tra nhiều lớp.

### Kiểm tra bundle

~~~bash
git bundle verify /backup/app-2026-11-17.bundle
git bundle list-heads /backup/app-2026-11-17.bundle
~~~

### Kiểm tra repository đã khôi phục

~~~bash
git -C /restore/app fsck --full
git -C /restore/app show-ref
git -C /restore/app log --oneline --decorate --all -20
~~~

`git fsck --full` kiểm tra tính toàn vẹn và khả năng kết nối của Git object database. Nó không kiểm tra nội dung nghiệp vụ của ứng dụng, không xác minh LFS object trên server và không chứng minh toàn bộ cấu hình hệ thống đã được sao lưu.

### Kiểm tra checksum file backup

Trên Linux:

~~~bash
sha256sum /backup/app-2026-11-17.bundle
~~~

Trên Windows PowerShell:

~~~powershell
Get-FileHash -Algorithm SHA256 -LiteralPath 'D:/backup/app-2026-11-17.bundle'
~~~

Lưu checksum ở nơi độc lập với file backup để phát hiện hỏng dữ liệu khi lưu trữ hoặc truyền tải.

## 9. Những thành phần phải sao lưu riêng

### Git LFS

Git commit chỉ lưu pointer file; bundle và mirror Git không tự chứa nội dung LFS thực tế. Nếu repository dùng Git LFS, hãy sao lưu cả LFS object store hoặc dùng chức năng backup của LFS server.

Có thể fetch các LFS object của mọi refs về cache local bằng:

~~~bash
git lfs fetch --all origin
~~~

Kiểm tra cấu hình và vị trí lưu trữ:

~~~bash
git lfs env
git lfs ls-files
~~~

Sau đó sao lưu LFS object store theo đường dẫn thực tế mà `git lfs env` cung cấp, hoặc backup trực tiếp storage phía server. Một bản Git bundle chỉ có pointer mà không có LFS object tương ứng sẽ không khôi phục được nội dung tệp lớn.

### Submodule

Superproject lưu đường dẫn và commit gitlink của submodule. Nội dung lịch sử của repository submodule nằm ở repository riêng. Vì vậy, cần backup từng repository submodule và bảo đảm commit được tham chiếu vẫn có thể truy cập.

Tệp `.gitmodules` nằm trong lịch sử superproject, nhưng nó không chứa object database của submodule.

### Config, hooks và chính sách máy chủ

Bundle và clone mirror không phải bản sao đầy đủ của cấu hình server hoặc môi trường vận hành. Cần lưu riêng những thành phần cần phục hồi:

- Cấu hình repository và remote cần thiết.
- Server-side hooks hoặc cấu hình hook path.
- Branch protection, access control, deploy key và chính sách review.
- Cấu hình CI/CD, webhook và integration.
- Metadata issue, pull request, release hoặc artifact nếu nền tảng lưu chúng ngoài Git.
- Credential và secret theo quy trình backup bí mật riêng, có mã hóa và kiểm soát truy cập.

Không đưa token, private key hoặc secret vào bundle hay backup công khai. Backup cũng cần được bảo vệ bằng quyền truy cập tối thiểu và mã hóa phù hợp.

### Working tree chưa commit

Git bundle và mirror chỉ bảo vệ lịch sử đã được refs giữ. Chúng không chứa thay đổi chưa commit, tệp untracked hoặc ignored.

Nếu cần bảo vệ công việc local, hãy commit vào branch phù hợp hoặc tạo archive/filesystem snapshot riêng cho working tree. Trước khi archive, kiểm tra:

~~~bash
git status --short
git diff
git diff --cached
~~~

Không giả định stash là backup dài hạn; stash vẫn là refs trong repository và có thể bị xóa hoặc mất cùng repository.

## 10. Thiết kế retention và khả năng phục hồi

Một chính sách backup cần trả lời hai câu hỏi:

- **RPO (Recovery Point Objective):** có thể chấp nhận mất dữ liệu kể từ thời điểm backup gần nhất trong bao lâu?
- **RTO (Recovery Time Objective):** cần bao lâu để khôi phục repository và dịch vụ trở lại hoạt động?

Ví dụ, nếu RPO là 24 giờ, snapshot hằng ngày có thể phù hợp nhưng cần xem xét giờ chạy và thời gian hoàn tất. Nếu RPO là 1 giờ, cần backup thường xuyên hơn hoặc giải pháp replication/snapshot có tần suất cao hơn.

Có thể áp dụng nguyên tắc 3-2-1:

- Giữ ít nhất ba bản dữ liệu.
- Dùng ít nhất hai loại phương tiện hoặc miền lưu trữ khác nhau.
- Có ít nhất một bản ở vị trí offsite hoặc vùng quản trị độc lập.

Đối với repository quan trọng, nên có ít nhất một bản backup immutable hoặc offline để người có quyền xóa repository nguồn không thể xóa luôn bản lịch sử. Thời gian retention cần đủ dài để phát hiện sự cố xóa nhầm hoặc thay đổi lịch sử muộn.

## 11. Diễn tập restore thay vì chỉ kiểm tra file tồn tại

Backup job thành công hoặc file bundle có mặt chưa đủ. Hãy định kỳ tạo một thư mục restore thử nghiệm và khôi phục snapshot vào đó.

Ví dụ:

~~~bash
git bundle verify /backup/app-2026-11-17.bundle
git clone /backup/app-2026-11-17.bundle /restore-drill/app
git -C /restore-drill/app fsck --full
git -C /restore-drill/app show-ref
git -C /restore-drill/app log --oneline --decorate --all -20
~~~

Sau đó xác nhận:

1. Branch quan trọng có đúng commit tại thời điểm snapshot không?
2. Tag release có còn và trỏ đúng commit không?
3. Các commit cần phục hồi có đọc được không?
4. Submodule có thể clone và checkout commit tương ứng không?
5. LFS object có thể tải và nội dung có đúng kích thước/hash không?
6. Cấu hình, hook, quyền truy cập và pipeline có thể tái tạo không?
7. Thời gian restore có đáp ứng RTO không?

Diễn tập restore nên chạy trong môi trường cô lập. Không ghi đè repository production hoặc remote đang hoạt động trong một bài kiểm tra.

## 12. Quy trình backup mẫu

Một quy trình snapshot Git bundle cho repository đã có sẵn local clone:

~~~bash
# 1. Cập nhật refs từ remote
git fetch --all --tags --prune

# 2. Kiểm tra trạng thái và tính toàn vẹn nguồn
git status
git fsck --full

# 3. Tạo snapshot có tên riêng
git bundle create /backup/app-2026-11-17.bundle --all

# 4. Xác minh bundle và danh sách refs
git bundle verify /backup/app-2026-11-17.bundle
git bundle list-heads /backup/app-2026-11-17.bundle

# 5. Kiểm tra checksum
sha256sum /backup/app-2026-11-17.bundle

# 6. Diễn tập khôi phục trong thư mục riêng
git clone /backup/app-2026-11-17.bundle /restore/app-2026-11-17
git -C /restore/app-2026-11-17 fsck --full
~~~

Lưu ý: `git fetch --all --tags --prune` cập nhật các remote-tracking refs và có thể prune refs đã bị xóa ở remote. Đây là trạng thái bạn đang chọn để snapshot. Nếu cần giữ refs local hoặc refs đã bị xóa ở nguồn, hãy xác định và tạo ref backup trước khi fetch/prune; không để thao tác đồng bộ vô tình xóa dấu vết cần bảo toàn.

Với repository đang được nhiều người ghi đồng thời, thực hiện snapshot trên một clone backup đã fetch xong hoặc dùng cơ chế snapshot nhất quán của server. Nếu cần bảo toàn các refs tại đúng một thời điểm, ghi nhận thời điểm snapshot và tránh cập nhật refs trong lúc đóng gói.

## 13. Sơ đồ lựa chọn phương thức sao lưu

~~~mermaid
flowchart TD
    A[Cần bảo vệ repository] --> B{Cần replica trạng thái hiện tại?}
    B -- Có --> C[Tạo bare mirror bằng clone --mirror]
    C --> D[Đồng bộ theo lịch]
    B -- Không --> E{Cần khôi phục lịch sử cũ?}
    D --> E
    E -- Có --> F[Tạo snapshot bundle theo thời điểm]
    E -- Không --> G[Đánh giá retention và mục tiêu phục hồi]
    F --> H[Verify, checksum và restore drill]
    G --> H
    H --> I{Repository có LFS hoặc submodule?}
    I -- Có --> J[Backup LFS object và từng submodule riêng]
    I -- Không --> K[Backup config, hooks và metadata ngoài Git]
    J --> K
    K --> L[Lưu bản immutable/offline và kiểm tra định kỳ]
~~~

Trước khi hoàn tất, hãy tự xác nhận:

1. Tôi cần mirror để dự phòng hiện tại hay snapshot để phục hồi lịch sử?
2. Mirror có prune hoặc force-update refs khiến lịch sử cũ biến mất không?
3. Snapshot bundle đã chứa các refs cần bảo vệ chưa?
4. Tôi có bảo vệ commit chỉ còn trong reflog/dangling trước khi GC không?
5. LFS object, submodule, config, hooks và working tree đã được xử lý riêng chưa?
6. Bundle đã verify, checksum và restore thử nghiệm chưa?
7. Backup có bản offline/immutable và retention phù hợp RPO/RTO không?

Mirror giúp có một bản replica gần với trạng thái hiện tại; snapshot theo thời điểm giúp giữ lịch sử để phục hồi sau khi refs bị xóa hoặc viết lại. Một chiến lược backup Git đáng tin cậy kết hợp cả hai khi cần, lưu riêng LFS và dữ liệu ngoài Git, kiểm tra tính toàn vẹn và thường xuyên diễn tập restore. Chỉ khi khôi phục được trong môi trường độc lập, bạn mới có bằng chứng rằng bản backup thực sự sử dụng được.

## Tài liệu tham khảo

- [Git documentation: git-clone](https://git-scm.com/docs/git-clone) — bare clone và mirror clone.
- [Git documentation: git-bundle](https://git-scm.com/docs/git-bundle) — tạo, liệt kê, xác minh và khôi phục bundle.
- [Git documentation: git-fsck](https://git-scm.com/docs/git-fsck) — kiểm tra tính toàn vẹn object database.
- [Git documentation: git-push](https://git-scm.com/docs/git-push) — semantics của mirror push và cập nhật refs.
- [Git LFS documentation](https://github.com/git-lfs/git-lfs/blob/main/docs/man/git-lfs-fetch.adoc) — tải LFS object và tùy chọn --all.
- [Pro Git: Git Internals - Maintenance and Data Recovery](https://git-scm.com/book/en/v2/Git-Internals-Maintenance-and-Data-Recovery) — object database, reflog và phục hồi dữ liệu.
