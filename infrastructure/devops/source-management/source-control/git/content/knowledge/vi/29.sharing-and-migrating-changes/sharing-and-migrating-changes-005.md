# Trao đổi ngoại tuyến bằng git bundle create, verify và clone

Git thường được cộng tác qua remote như GitHub, GitLab hoặc máy chủ Git nội bộ. Tuy nhiên, có lúc hai máy không thể kết nối trực tiếp: môi trường bị cô lập mạng, máy phát triển không có quyền truy cập Internet, cần chuyển mã nguồn qua thiết bị lưu trữ hoặc phải gửi một tập commit cho nhóm ở địa điểm khác. Trong những tình huống đó, **git bundle** cho phép đóng gói object và ref cần thiết vào một file để chuyển giao ngoại tuyến.

Một bundle có thể được dùng làm nguồn để clone một repository mới hoặc fetch commit vào repository đã có. Người nhận có thể kiểm tra bundle, xem các ref mà bundle cung cấp, xác minh những commit nền cần thiết và sau đó nhập thay đổi vào lịch sử của mình.

Bundle không phải bản sao được mã hóa. Nó có thể chứa mã nguồn, lịch sử cũ, branch và tag; vì vậy cần kiểm tra phạm vi dữ liệu, bảo vệ file khi lưu/chuyển và xác minh nguồn gốc trước khi sử dụng.

## 1. git bundle giải quyết vấn đề gì?

git bundle tạo một file có định dạng Git chứa các object cần thiết cùng thông tin ref và, nếu là bundle tăng dần, các prerequisite mà người nhận phải có sẵn.

Bundle hữu ích khi:

- Chuyển repository giữa hai môi trường không có kết nối mạng trực tiếp.
- Gửi một branch hoặc nhóm commit để review ngoại tuyến.
- Di chuyển lịch sử Git qua USB hoặc vùng lưu trữ trung gian được kiểm soát.
- Cung cấp snapshot có lịch sử cho môi trường build cô lập.
- Tạo gói incremental để chỉ chuyển các commit mới kể từ một mốc đã biết.

Bundle giữ thông tin Git cần thiết để tiếp tục làm việc với commit và ref. Người nhận có thể clone từ bundle hoặc fetch các ref được quảng bá vào repository hiện tại.

### 1.1. Bundle khác source archive như thế nào?

| Tiêu chí | Git bundle | Source archive (tar/zip) |
|---|---|---|
| Nội dung | Git objects và ref được chọn | Snapshot file của một tree |
| Lịch sử commit | Có, theo phạm vi bundle | Không |
| Có thể clone/fetch | Có | Không |
| Có thể chứa nhiều branch/tag | Có, nếu chọn các ref đó | Không |
| Dùng để tiếp tục phát triển Git | Có | Cần khởi tạo repository mới nếu muốn quản lý bằng Git |
| Phù hợp | Trao đổi lịch sử và commit ngoại tuyến | Phân phối mã nguồn tại một phiên bản |

Nếu người nhận chỉ cần chạy ứng dụng từ một phiên bản, source archive có thể phù hợp hơn. Nếu người nhận cần xem lịch sử, tạo branch, merge hoặc tiếp tục commit, bundle phù hợp hơn.

### 1.2. Bundle không thay thế backup hoặc remote lâu dài

Bundle là một file chuyển giao. Nó không tự đồng bộ hai phía sau khi được tạo. Nếu người gửi tiếp tục commit sau khi tạo bundle, file bundle cũ không tự thay đổi.

Khi cần trao đổi nhiều vòng, hãy tạo bundle mới hoặc incremental bundle dựa trên một commit nền mà hai bên đã thống nhất.

## 2. Xem trước repository trước khi tạo bundle

Trước khi đóng gói, xác định repository, trạng thái working tree và các ref cần chia sẻ.

~~~sh
git rev-parse --show-toplevel
git status -sb
git branch --all
git tag --list
git remote -v
~~~

Bundle được tạo từ commit và ref đã lưu trong Git. Thay đổi chưa commit hoặc file chưa được track trong working tree không tự động được đưa vào bundle. Nếu cần chia sẻ thay đổi đó, hãy commit chúng vào branch riêng hoặc dùng cơ chế patch phù hợp.

### 2.1. Chọn đúng ref

Không phải lúc nào cũng nên gửi toàn bộ repository. Xác định người nhận cần:

- Một branch như main hoặc feature/report.
- Một tag phát hành như v2.1.0.
- Một số branch và tag liên quan.
- Toàn bộ ref hiện có để backup hoặc di chuyển repository.

Xem các ref có thể chia sẻ:

~~~sh
git for-each-ref --format="%(objectname) %(refname)" refs/heads/ refs/tags/
~~~

Lưu ý tùy chọn --all có thể bao gồm nhiều ref hơn người nhận cần, chẳng hạn branch local, tag và remote-tracking ref. Trước khi dùng, xem danh sách ref và cân nhắc thông tin mà chúng tiết lộ.

### 2.2. Kiểm tra dữ liệu nhạy cảm

Bundle có thể chứa cả lịch sử cũ, kể cả file đã bị xóa khỏi branch hiện tại. Trước khi tạo:

- Quét secret trong các ref và lịch sử có liên quan.
- Kiểm tra commit message, author metadata và tên branch/tag.
- Không đưa dữ liệu khách hàng hoặc file cấu hình local vào commit.
- Xác nhận người nhận có quyền xem toàn bộ lịch sử được đóng gói.
- Dùng kênh lưu trữ và chuyển giao được tổ chức phê duyệt.

Nếu một secret đã từng được commit, việc xóa file ở commit mới không loại bỏ secret khỏi bundle nếu lịch sử chứa commit cũ đó.

## 3. Tạo bundle đầy đủ bằng git bundle create

### 3.1. Bundle chứa một branch

Giả sử cần gửi branch main:

~~~sh
git bundle create ../project-main.bundle refs/heads/main
~~~

Lệnh tạo file project-main.bundle ở thư mục cha của repository hiện tại. Bundle chứa các object cần thiết cho lịch sử của branch main và quảng bá ref đó cho người nhận.

Nếu muốn người nhận làm việc với branch khác, thay tên ref bằng ref cần chia sẻ, ví dụ:

~~~sh
git bundle create ../feature-report.bundle refs/heads/feature/report
~~~

Dùng tên ref đầy đủ giúp thể hiện rõ branch được đóng gói.

### 3.2. Bundle chứa nhiều branch và tag được chọn

Có thể chỉ định nhiều ref:

~~~sh
git bundle create ../release-transfer.bundle refs/heads/main refs/heads/release/2.x refs/tags/v2.0.0
~~~

Người nhận sẽ có thể xem các ref được bundle quảng bá. Cách này phù hợp khi cần chuyển một nhánh phát triển cùng một số mốc phát hành liên quan.

### 3.3. Bundle toàn bộ ref

Để tạo bundle từ các ref có thể được liệt kê trong repository:

~~~sh
git bundle create ../project-all.bundle --all
~~~

Đây là lựa chọn tiện cho backup hoặc di chuyển repository. Tuy nhiên, bundle có thể mang theo nhiều branch, tag và remote-tracking ref hơn nhu cầu. Kiểm tra danh sách ref trước khi chia sẻ.

Không dùng --all chỉ vì muốn “chắc chắn không thiếu gì” nếu người nhận chỉ cần một branch. Phạm vi càng lớn, file càng nặng và nguy cơ tiết lộ lịch sử không cần thiết càng cao.

## 4. Bundle đầy đủ và bundle tăng dần

Một bundle đầy đủ có thể cung cấp toàn bộ lịch sử cần thiết cho các ref được chọn. Bundle tăng dần chỉ chứa phần lịch sử mới và ghi lại prerequisite mà repository nhận phải có sẵn.

### 4.1. Tạo bundle đầy đủ

Ví dụ:

~~~sh
git bundle create ../main-full.bundle refs/heads/main
~~~

Bundle này chứa lịch sử cần thiết để người nhận tạo lại branch main mà không cần một repository nền đã có trước, miễn là ref và object cần thiết được bao gồm.

### 4.2. Tạo bundle tăng dần từ một commit nền

Giả sử hai bên đã có commit nền A. Người gửi muốn chuyển các commit mới trên branch feature/report kể từ A:

~~~sh
git bundle create ../feature-incremental.bundle refs/heads/feature/report ^<base-commit>
~~~

Trong đó <base-commit> là commit đã có trong repository của người nhận. Phần ^<base-commit> loại commit nền và các tổ tiên của nó khỏi tập object cần chuyển; bundle ghi nhận commit nền là prerequisite.

Có thể dùng một biểu thức revision range tương đương:

~~~sh
git bundle create ../feature-incremental.bundle <base-commit>..refs/heads/feature/report
~~~

Khi tạo incremental bundle, hãy thống nhất chính xác commit nền với người nhận. Nếu người nhận không có prerequisite, họ không thể nhập đầy đủ phần thay đổi chỉ từ bundle đó.

### 4.3. Khi nào nên dùng bundle tăng dần?

Bundle tăng dần phù hợp khi:

- Hai bên đã trao đổi một bundle đầy đủ trước đó.
- Người nhận có clone hoặc repository chứa commit nền.
- Lịch sử mới chỉ gồm một phần nhỏ so với repository.
- Kết nối bị giới hạn và cần giảm dung lượng chuyển giao.

Nếu không chắc người nhận có commit nền nào, hãy gửi bundle đầy đủ hoặc trao đổi một bundle nền trước. Không giả định hai repository có cùng lịch sử chỉ vì chúng dùng branch cùng tên.

## 5. Kiểm tra bundle bằng git bundle verify

Trước khi sử dụng bundle, người nhận nên kiểm tra cấu trúc và prerequisite.

~~~sh
git bundle verify ../project-main.bundle
~~~

git bundle verify kiểm tra bundle và cho biết các ref mà bundle cung cấp, đồng thời xác minh những prerequisite có sẵn trong repository hiện tại. Với bundle đầy đủ không có prerequisite, có thể kiểm tra trong một repository trống.

### 5.1. Verify bundle tăng dần

Với incremental bundle, chạy verify trong repository đã có commit nền:

~~~sh
git bundle verify ../feature-incremental.bundle
~~~

Nếu thiếu prerequisite, Git báo bundle không thể áp dụng trong repository hiện tại. Khi đó:

1. Xác định commit prerequisite được liệt kê.
2. Kiểm tra repository có đúng lịch sử nền hay không.
3. Yêu cầu bundle đầy đủ hoặc bundle nền cần thiết nếu commit chưa có.
4. Chạy verify lại trước khi fetch.

Không bỏ qua thông báo thiếu prerequisite. Thiếu commit nền có thể khiến việc nhập lịch sử thất bại hoặc làm người nhận không thể tái tạo branch đúng.

### 5.2. Verify không chứng minh ai tạo bundle

git bundle verify kiểm tra cấu trúc bundle và khả năng đáp ứng prerequisite. Nó không xác thực danh tính người gửi và không chứng minh nội dung được người có thẩm quyền phát hành.

Để xác minh nguồn gốc, dùng chữ ký số hoặc checksum được truyền qua một kênh đáng tin cậy:

- So sánh checksum với giá trị đã nhận qua kênh xác thực.
- Xác minh chữ ký số nếu tổ chức ký bundle hoặc manifest.
- Đối chiếu commit SHA với thông tin phát hành đã được xác nhận.

Checksum giúp phát hiện file bị thay đổi nhưng không tự chứng minh ai tạo file. Nếu kẻ tấn công có thể thay cả bundle và checksum trên cùng kênh, phép so sánh đó không đủ để xác thực nguồn.

## 6. Xem ref được quảng bá bằng git bundle list-heads

Trước khi clone hoặc fetch, có thể liệt kê các ref trong bundle:

~~~sh
git bundle list-heads ../project-all.bundle
~~~

Kết quả gồm object ID và tên ref. Ví dụ:

~~~text
<commit-id> refs/heads/main
<commit-id> refs/heads/feature/report
<tag-object-id> refs/tags/v2.0.0
~~~

Danh sách giúp xác nhận bundle có branch hoặc tag mong đợi. Nếu bundle không quảng bá ref cần thiết, kiểm tra lại lệnh create ở phía người gửi.

Với annotated tag, object ID được liệt kê có thể là tag object thay vì commit trực tiếp. Đây là hành vi bình thường.

## 7. Clone repository mới từ bundle

Nếu người nhận chưa có repository, có thể clone trực tiếp từ bundle:

~~~sh
git clone --branch main ../project-main.bundle project-offline
~~~

Lệnh tạo repository mới trong thư mục project-offline và checkout branch main được bundle cung cấp. Nếu bundle không có branch tên main, hãy chọn branch khác có trong kết quả list-heads.

Sau khi clone:

~~~sh
cd project-offline
git status -sb
git branch -a
git log --oneline --decorate -10
git remote -v
~~~

Kiểm tra branch hiện tại, lịch sử và remote được tạo. Khi clone từ đường dẫn bundle, remote origin có thể trỏ tới file bundle hoặc đường dẫn nguồn ban đầu; điều đó không tạo ra một máy chủ mạng. Người dùng cần cập nhật remote theo quy trình offline hoặc thiết lập remote mới khi có kết nối.

### 7.1. Nếu bundle có nhiều branch

Chọn branch mặc định bằng tùy chọn --branch khi clone:

~~~sh
git clone --branch release/2.x ../release-transfer.bundle project-release
~~~

Nếu chưa biết tên branch, chạy git bundle list-heads trước. Tránh giả định tên branch mặc định của bundle luôn là main hoặc master.

### 7.2. Clone bundle đầy đủ rồi tiếp tục làm việc

Sau khi clone, người nhận có thể tạo branch mới:

~~~sh
git switch -c feature/offline-adjustment
~~~

Sửa file, stage và commit như repository bình thường:

~~~sh
git add src/
git commit -m "Apply offline adjustment"
~~~

Commit mới chỉ tồn tại trong clone local cho tới khi được chuyển lại bằng bundle khác hoặc một remote có thể truy cập.

## 8. Fetch bundle vào repository đã có

Nếu người nhận đã có repository và chỉ muốn nhập một branch từ bundle, dùng git fetch với đường dẫn file bundle.

Ví dụ:

~~~sh
git fetch ../feature-report.bundle refs/heads/feature/report:refs/remotes/offline/feature/report
~~~

Lệnh lấy ref refs/heads/feature/report trong bundle và cập nhật ref local refs/remotes/offline/feature/report. Không cần clone lại repository.

Kiểm tra:

~~~sh
git show-ref refs/remotes/offline/feature/report
git log --oneline --decorate -10 refs/remotes/offline/feature/report
~~~

Tạo branch local để review:

~~~sh
git switch -c review/feature-report refs/remotes/offline/feature/report
~~~

Sau khi review, có thể merge hoặc cherry-pick theo quy trình dự án:

~~~sh
git switch main
git merge --no-ff review/feature-report
~~~

Không merge chỉ vì fetch thành công. Hãy xem diff, chạy test và xác nhận commit đến từ đúng người gửi.

## 9. Trao đổi hai chiều hoàn toàn ngoại tuyến

Bundle có thể dùng để gửi thay đổi đi và nhận thay đổi quay lại.

### 9.1. Người gửi tạo bundle cho branch công việc

~~~sh
git bundle create ../feature-payment.bundle refs/heads/feature/payment
git bundle verify ../feature-payment.bundle
git bundle list-heads ../feature-payment.bundle
~~~

Chuyển file bundle và checksum/manifest qua thiết bị lưu trữ được phép.

### 9.2. Người nhận fetch và phát triển

~~~sh
git bundle verify /media/transfer/feature-payment.bundle
git fetch /media/transfer/feature-payment.bundle refs/heads/feature/payment:refs/remotes/offline/feature/payment
git switch -c feature/payment refs/remotes/offline/feature/payment
~~~

Người nhận có thể sửa, commit và tạo bundle phản hồi:

~~~sh
git bundle create ../payment-feedback.bundle refs/heads/feature/payment
~~~

### 9.3. Người gửi nhập bundle phản hồi

~~~sh
git bundle verify ../payment-feedback.bundle
git fetch ../payment-feedback.bundle refs/heads/feature/payment:refs/remotes/offline/feature/payment-feedback
git log --oneline --graph --decorate main..refs/remotes/offline/feature/payment-feedback
~~~

Sau khi xem xét, người gửi có thể merge hoặc cherry-pick các commit phù hợp. Hai bên nên thống nhất cách đặt tên ref offline để tránh ghi đè branch local hoặc remote-tracking branch đang tồn tại.

## 10. Quy trình incremental bundle qua nhiều lần chuyển giao

Khi hai bên đã có cùng commit nền, có thể giảm dung lượng bằng các bundle tăng dần.

Giả sử:

- Bundle đầu tiên đã giúp người nhận có commit A.
- Người gửi tiếp tục tạo commit B và C trên branch feature/report.
- Người nhận chưa có B và C.

Người gửi tạo bundle từ A tới tip hiện tại:

~~~sh
git bundle create ../report-update.bundle refs/heads/feature/report ^<A>
~~~

Người nhận xác minh trong repository đã có A:

~~~sh
git bundle verify ../report-update.bundle
~~~

Sau đó fetch branch:

~~~sh
git fetch ../report-update.bundle refs/heads/feature/report:refs/remotes/offline/feature/report
~~~

Khi chuyển giao tiếp theo, hai bên phải thống nhất commit nền mới đã được nhận thành công. Không dùng một base cũ theo thói quen nếu lịch sử đã thay đổi hoặc branch bị force push.

Nếu branch bị rebase hoặc viết lại lịch sử, incremental bundle dựa trên commit cũ có thể không còn phù hợp. Khi đó, cần xác định lại điểm chung hoặc tạo bundle đầy đủ.

## 11. Xử lý lỗi khi tạo hoặc nhận bundle

**Không tạo được bundle vì thiếu object.** Kiểm tra repository có đầy đủ object cần thiết không. Nếu clone là shallow hoặc partial, có thể cần fetch thêm dữ liệu từ remote trước khi tạo bundle.

**Bundle verify báo thiếu prerequisite.** Đây là incremental bundle và repository nhận chưa có commit nền. Hãy chuyển bundle nền hoặc tạo bundle đầy đủ.

**Không thấy branch mong muốn trong list-heads.** Người gửi có thể đã không đưa ref đó vào lệnh create. Tạo lại bundle với tên ref đầy đủ.

**Clone báo không có branch được chọn.** Kiểm tra danh sách ref và dùng đúng tên trong tùy chọn --branch.

**Fetch không cập nhật ref.** Kiểm tra source ref trong bundle, destination ref, quyền ghi và quy tắc fast-forward của ref đích. Nếu ref đích đã có lịch sử khác, không ép ghi đè trước khi review.

**Bundle quá lớn.** Chỉ đóng gói branch/tag cần thiết, cân nhắc incremental bundle nếu người nhận có base commit. Tránh --all khi không cần.

**Bundle bị lỗi khi truyền.** So sánh checksum, sao chép lại file từ nguồn đáng tin cậy và chạy verify trước khi import.

**Bundle hợp lệ nhưng không tin cậy.** Verify không chứng minh danh tính người tạo. Đối chiếu chữ ký, checksum qua kênh độc lập và commit SHA với người gửi.

## 12. Bảo vệ bundle khi lưu và chuyển giao

Bundle là file có thể chứa mã nguồn và lịch sử. Nó không tự mã hóa hoặc giới hạn người đọc.

Trước khi chuyển:

- Xác định ref và lịch sử được bao gồm.
- Quét secret và dữ liệu cá nhân trong các commit liên quan.
- Dùng thiết bị hoặc kho lưu trữ được phê duyệt.
- Mã hóa khi chính sách yêu cầu.
- Giới hạn người được truy cập file.
- Tạo checksum và, nếu cần, ký manifest.
- Ghi nhận người tạo, người nhận, thời gian và mục đích.

Sau khi nhận:

- Kiểm tra checksum hoặc chữ ký qua kênh đáng tin cậy.
- Chạy git bundle verify.
- Xem git bundle list-heads.
- Clone/fetch vào repository thử nghiệm nếu nội dung không rõ nguồn.
- Review lịch sử và diff trước khi merge.
- Xóa file trung gian theo chính sách retention.

### 12.1. Checksum ví dụ

Trên Linux:

~~~sh
sha256sum project-main.bundle
~~~

Trên macOS:

~~~sh
shasum -a 256 project-main.bundle
~~~

Trên Windows PowerShell:

~~~powershell
Get-FileHash .\project-main.bundle -Algorithm SHA256
~~~

Gửi checksum qua một kênh độc lập với nơi truyền bundle nếu mục tiêu là phát hiện thay thế file. Nếu cả file và checksum cùng đến từ một nguồn không xác thực, checksum không chứng minh nguồn gốc.

## 13. Bundle và các tình huống di chuyển repository

### 13.1. Chuyển repository giữa hai máy ngoại tuyến

1. Người gửi tạo bundle từ ref cần thiết.
2. Người gửi kiểm tra list-heads và verify.
3. Tạo checksum hoặc chữ ký theo chính sách.
4. Chuyển file qua phương tiện được phép.
5. Người nhận xác minh checksum/chữ ký và bundle.
6. Clone hoặc fetch vào repository.
7. Kiểm tra branch, tag, log và chạy test.

### 13.2. Di chuyển repository sang máy chủ mới

Bundle có thể dùng để chuyển lịch sử giữa các môi trường, nhưng cần xác định rõ ref nào phải được bảo toàn. Với migration đầy đủ, kiểm tra:

- Branch và tag cần thiết.
- Remote-tracking ref có cần giữ hay không.
- Notes hoặc ref đặc biệt của dự án.
- Git LFS hoặc nội dung ngoài object database.
- Submodule và repository con.
- Hook, config, permission và quy trình CI/CD.

Bundle chỉ chứa Git objects và ref được chọn. Nó không tự chuyển Git config, hook server, credential, working tree chưa commit, Git LFS object ngoài Git hoặc nội dung submodule. Các thành phần đó cần kế hoạch di chuyển riêng.

### 13.3. Bundle không tự đồng bộ nhiều remote

Khi người nhận clone từ bundle, remote được tạo có thể trỏ tới đường dẫn bundle. Đó không phải một remote server luôn cập nhật. Nếu sau này có mạng, cấu hình remote URL đúng:

~~~sh
git remote set-url origin https://example.com/team/project.git
git remote -v
git fetch origin
~~~

Trước khi push, so sánh lịch sử và xác định branch có diverge hay không. Không push force chỉ để làm hai repository “giống nhau”.

## 14. Ví dụ hoàn chỉnh: chuyển branch qua thiết bị lưu trữ

Giả sử máy A có repository project, máy B ở môi trường ngoại tuyến và cần nhận branch feature/report.

**Trên máy A — tạo bundle**

~~~sh
git status -sb
git log --oneline -10 refs/heads/feature/report
git bundle create ../feature-report.bundle refs/heads/feature/report
git bundle list-heads ../feature-report.bundle
git bundle verify ../feature-report.bundle
~~~

Tạo checksum:

~~~sh
sha256sum ../feature-report.bundle
~~~

Chuyển bundle và checksum qua phương tiện được phép.

**Trên máy B — xác minh và nhập**

~~~sh
git bundle verify /media/transfer/feature-report.bundle
git bundle list-heads /media/transfer/feature-report.bundle
git fetch /media/transfer/feature-report.bundle refs/heads/feature/report:refs/remotes/offline/feature/report
git switch -c review/feature-report refs/remotes/offline/feature/report
~~~

Review:

~~~sh
git log --oneline --graph --decorate -20
git diff main...review/feature-report
~~~

Chạy test, sau đó merge nếu được chấp thuận:

~~~sh
git switch main
git merge --no-ff review/feature-report
~~~

Nếu máy B cần gửi kết quả về máy A, tạo bundle mới từ branch đã cập nhật và chuyển theo quy trình tương tự.

## 15. Checklist sử dụng git bundle

**Trước khi tạo**

- [ ] Đã xác định branch/tag/ref cần chuyển.
- [ ] Đã kiểm tra working tree và commit cần chia sẻ.
- [ ] Đã rà soát secret, dữ liệu riêng và metadata.
- [ ] Đã quyết định bundle đầy đủ hay incremental.
- [ ] Nếu incremental, đã thống nhất prerequisite commit với người nhận.

**Sau khi tạo**

- [ ] File bundle được tạo thành công.
- [ ] Đã chạy git bundle list-heads.
- [ ] Đã chạy git bundle verify trong repository phù hợp.
- [ ] Đã tạo checksum hoặc chữ ký nếu chính sách yêu cầu.
- [ ] Đã lưu file ở vị trí có quyền truy cập phù hợp.

**Khi nhận**

- [ ] Đã xác minh nguồn gốc và tính toàn vẹn qua kênh đáng tin cậy.
- [ ] Đã chạy verify và kiểm tra prerequisite.
- [ ] Đã xác nhận ref cần thiết có trong bundle.
- [ ] Đã clone hoặc fetch vào đúng repository.
- [ ] Đã review log/diff và chạy test trước khi merge.

**Sau khi trao đổi**

- [ ] Đã cập nhật commit nền cho lần bundle tiếp theo.
- [ ] Đã lưu lại thông tin bàn giao cần thiết.
- [ ] Đã xóa file trung gian theo retention policy.
- [ ] Đã xử lý riêng Git LFS, submodule, hooks và config nếu migration yêu cầu.

## 16. Kết luận

git bundle cho phép trao đổi lịch sử Git khi không thể kết nối remote trực tiếp. git bundle create đóng gói object và ref được chọn; git bundle verify kiểm tra bundle cùng prerequisite; git bundle list-heads cho biết các ref được cung cấp; git clone hoặc git fetch giúp người nhận tạo repository mới hoặc nhập thay đổi vào repository hiện có.

Hãy chọn ref tối thiểu, phân biệt bundle đầy đủ với bundle tăng dần, và bảo đảm người nhận có prerequisite trước khi nhập. Verify không xác thực người gửi, checksum không mã hóa dữ liệu và bundle có thể chứa toàn bộ lịch sử nhạy cảm. Kết hợp kiểm tra nguồn gốc, bảo vệ file, review lịch sử và quản lý bản sao để trao đổi ngoại tuyến an toàn và có thể tái lập.
