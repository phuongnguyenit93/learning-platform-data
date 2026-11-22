# Trao đổi bản vá, tạo bundle và kiểm tra khả năng khôi phục ngoại tuyến

Bài thực hành này mô phỏng tình huống hai nhóm phát triển phải trao đổi thay đổi Git khi không có remote chung hoặc không thể kết nối mạng trực tiếp. Nhóm gửi cần chuyển một nhánh tính năng cho nhóm nhận. Nhóm nhận phải kiểm tra bản vá, nhập commit vào repository của mình, đồng thời có một gói bundle đủ để khôi phục repository trong môi trường ngoại tuyến.

Bạn sẽ thực hiện hai cách trao đổi bổ trợ nhau:

- **Patch:** chuyển phần thay đổi dưới dạng diff hoặc chuỗi email patch. Patch phù hợp để review, gửi từng commit và áp dụng lên một repository có lịch sử nền phù hợp.
- **Git bundle:** đóng gói object và ref thành một file. Bundle phù hợp để clone hoặc fetch lịch sử Git mà không cần kết nối remote.

Cuối bài, bạn sẽ khôi phục một repository thử nghiệm từ bundle vào thư mục mới và xác nhận branch, commit, tag cùng nội dung file. Việc khôi phục vào thư mục riêng giúp kiểm tra khả năng phục hồi mà không ghi đè repository đang làm việc.

## 1. Mục tiêu thực hành

Sau khi hoàn thành, bạn có thể:

1. Chuẩn bị một nhánh tính năng sạch để bàn giao.
2. Tạo diff patch và format-patch từ một commit nền.
3. Kiểm tra patch trước khi áp dụng.
4. Áp dụng patch bằng git apply hoặc git am đúng với loại patch.
5. Tạo bundle đầy đủ và bundle tăng dần.
6. Xác minh prerequisite và ref được bundle cung cấp.
7. Clone hoặc fetch từ bundle trong môi trường ngoại tuyến.
8. Khôi phục repository vào một thư mục mới và đối chiếu kết quả.
9. Xác minh tính toàn vẹn và nguồn gốc của file bàn giao.

## 2. Bối cảnh và sơ đồ bài lab

Giả sử có hai máy:

- **Máy A — Sender:** có repository gốc và nhánh feature/offline-report đã phát triển.
- **Máy B — Receiver:** có repository được clone từ commit nền trước khi nhận thay đổi.

Hai máy không kết nối trực tiếp với nhau. File patch, bundle và manifest được chuyển qua thư mục trung gian hoặc thiết bị lưu trữ được tổ chức cho phép.

~~~text
Máy A: Sender
  Repository gốc
      |
      +--> Tạo diff patch
      |
      +--> Tạo format-patch (mbox)
      |
      +--> Tạo Git bundle
      |
      v
  Gói bàn giao + checksum/manifest
      |
      |  USB / thư mục chuyển giao / kho ngoại tuyến
      v
Máy B: Receiver
  Repository có commit nền
      |
      +--> Kiểm tra patch --> git apply hoặc git am
      |
      +--> Verify bundle --> fetch hoặc clone
      |
      v
  Review, đối chiếu lịch sử và chạy test
      |
      v
  Clone bundle vào thư mục restore-test
      |
      v
  Xác minh khả năng khôi phục
~~~

Patch và bundle có mục đích khác nhau. Patch thể hiện phần thay đổi cần review hoặc áp dụng; bundle mang theo object và ref để tiếp tục làm việc với lịch sử. Một quy trình bàn giao tốt có thể cung cấp cả hai để người nhận vừa xem được thay đổi vừa có phương án phục hồi.

## 3. Chuẩn bị repository và commit nền

Chọn một repository thử nghiệm không chứa credential hoặc dữ liệu khách hàng. Nếu dùng repository công việc, hãy bảo đảm bạn có quyền tạo nhánh và file bàn giao.

Trên cả hai máy, cần có Git và một thư mục làm việc riêng. Xác định phiên bản Git:

~~~sh
git --version
~~~

### 3.1. Trên máy A — kiểm tra trạng thái ban đầu

Vào repository nguồn:

~~~sh
git rev-parse --show-toplevel
git status -sb
git branch --show-current
git log --oneline --decorate -5
~~~

Trước khi tạo patch hoặc bundle:

- Working tree không có thay đổi ngoài phạm vi bài lab.
- Đã xác định branch nền, ví dụ main.
- Đã xác định commit nền mà máy B sẽ có.
- Không có secret hoặc file local trong các commit sắp chia sẻ.

Ghi lại commit nền:

~~~sh
git rev-parse main
~~~

Lưu mã commit này trong ghi chú bàn giao của bài lab. Đây là mốc để hai bên so sánh lịch sử và tạo incremental bundle.

### 3.2. Trên máy B — chuẩn bị repository nhận

Nếu máy B có thể chuẩn bị trước khi ngắt mạng, clone repository và checkout branch nền:

~~~sh
git clone <repository-url> receiver-project
git clone <repository-url> receiver-am
git clone <repository-url> receiver-bundle
git -C receiver-project switch main
git -C receiver-project rev-parse HEAD
git -C receiver-project status -sb
~~~

Ba bản clone được dùng độc lập để thử git apply, git am và fetch bundle. Mã commit của main trên mỗi bản phải khớp với commit nền đã ghi ở máy A. Nếu hai bên không có cùng commit nền, không áp dụng patch hoặc incremental bundle theo giả định. Hãy đồng bộ lại hoặc dùng bundle đầy đủ.

Nếu không có remote trong môi trường lab, có thể tạo repository nhận từ một bản clone hoặc bundle nền đã chuẩn bị trước. Mục tiêu là máy B có cùng commit gốc mà máy A dùng làm điểm xuất phát.

## 4. Trên máy A — tạo nhánh và commit thay đổi

Tạo nhánh công việc:

~~~sh
git switch -c feature/offline-report
~~~

Thực hiện thay đổi trong một hoặc nhiều file của dự án. Ví dụ, cập nhật phần tạo báo cáo và bổ sung test. Sau đó kiểm tra:

~~~sh
git status --short
git diff
~~~

Stage đúng các file cần bàn giao:

~~~sh
git add src/report/
git add tests/report/
git diff --cached --check
git diff --cached
~~~

Nếu cần stage từng phần:

~~~sh
git add -p src/report/report-service.java
~~~

Tạo commit với message mô tả rõ thay đổi:

~~~sh
git commit -m "feat(report): add offline report export"
~~~

Với thay đổi lớn, tách thành nhiều commit nhỏ có mục đích rõ ràng. Điều này giúp người nhận review từng bước và giúp format-patch tạo một chuỗi commit dễ theo dõi.

### 4.1. Kiểm tra lịch sử sau commit

~~~sh
git status -sb
git log --oneline --decorate main..feature/offline-report
git diff --stat main...feature/offline-report
git diff --check main...feature/offline-report
~~~

Kết quả mong đợi:

- Nhánh hiện tại là feature/offline-report.
- Không còn file ngoài ý muốn chưa commit.
- Log liệt kê các commit mới so với main.
- Diff chỉ gồm phần tính năng cần bàn giao.
- Không có lỗi whitespace phổ biến.

Nếu status còn thay đổi, quyết định rõ có cần commit bổ sung hay phải giữ lại ở máy A. Không để thay đổi chưa commit vô tình bị bỏ sót trong patch và bundle.

## 5. Tạo diff patch để chuyển phần thay đổi

Diff patch lưu khác biệt giữa hai tree. Nó không lưu đầy đủ metadata commit như format-patch và khi áp dụng bằng git apply sẽ không tự tạo commit.

Tạo patch từ main tới nhánh tính năng:

~~~sh
git diff --binary --full-index main..feature/offline-report > ../offline-report.diff
~~~

- --binary cho phép biểu diễn thay đổi binary theo định dạng patch của Git.
- --full-index ghi đầy đủ object ID trong header index của diff.
- main..feature/offline-report so sánh tree của main với tree ở tip của nhánh tính năng.

Patch này mô tả tổng thay đổi cuối cùng giữa hai mốc. Nếu cần bảo toàn ranh giới từng commit, dùng format-patch ở phần tiếp theo.

### 5.1. Kiểm tra patch trước khi gửi

Xem thống kê patch:

~~~sh
git apply --stat ../offline-report.diff
~~~

Khả năng áp dụng cần được kiểm tra trên working tree sạch có commit nền main. Phần 5.2 thực hiện kiểm tra đó trên máy B; không chạy trên nhánh feature đã chứa chính patch này. Lệnh check chỉ xác minh khả năng áp dụng trong trạng thái hiện tại; nó không chứng minh thay đổi đúng nghiệp vụ hoặc an toàn. Đọc nội dung patch, xem tên file, đường dẫn, dòng bị xóa/thêm và dữ liệu nhạy cảm trước khi gửi.

### 5.2. Áp dụng diff patch trên máy B

Đảm bảo máy B đang ở đúng commit nền và working tree sạch:

~~~sh
git switch main
git status -sb
git rev-parse HEAD
~~~

Chạy kiểm tra trước:

~~~sh
git apply --check ../offline-report.diff
~~~

Nếu kiểm tra thành công, áp dụng patch:

~~~sh
git apply ../offline-report.diff
git status --short
git diff
~~~

git apply cập nhật working tree nhưng không tạo commit. Nếu muốn stage cùng lúc, có thể dùng git apply --index, nhưng trong bài lab nên kiểm tra nội dung trước rồi mới stage.

Sau khi review:

~~~sh
git add src/report/ tests/report/
git diff --cached
git commit -m "feat(report): add offline report export"
~~~

Commit trên máy B có thể có mã SHA khác commit ở máy A vì diff patch không mang toàn bộ thông tin commit và Git tạo commit mới theo trạng thái, metadata hiện tại. Đây là kết quả bình thường của quy trình áp dụng diff.

Nếu git apply --check thất bại, không ép áp dụng. Xác nhận commit nền, kiểm tra patch đã bị áp dụng một phần hay chưa, rồi yêu cầu patch đúng hoặc xử lý khác biệt có chủ đích.

## 6. Tạo format-patch để giữ thông tin commit

Khi muốn gửi từng commit cùng author, ngày, subject và message, dùng git format-patch. Định dạng này phù hợp với quy trình gửi patch qua email hoặc file mbox.

Trên máy A:

~~~sh
git format-patch --stdout --binary --full-index main..feature/offline-report > ../offline-report.mbox
~~~

Nếu nhánh có nhiều commit, file mbox chứa chuỗi patch tương ứng với các commit trong khoảng. Người nhận có thể áp dụng chúng bằng git am để tạo commit mới và giữ metadata tác giả từ patch.

### 6.1. Phân biệt git apply và git am

| Tiêu chí | git apply | git am |
|---|---|---|
| Đầu vào điển hình | Diff patch | Email patch từ format-patch |
| Giữ ranh giới commit | Không tự tạo commit | Có, mỗi message patch tạo một commit |
| Giữ author metadata | Không tự tạo commit | Giữ thông tin tác giả từ patch |
| Cập nhật working tree | Có | Có, đồng thời tạo commit |
| Có thể kiểm tra trước | git apply --check | Xem patch, kiểm tra base và dùng thử trên clone |
| Khi có conflict | Lệnh apply thất bại, working tree cần được kiểm tra | Dùng trạng thái am, sửa conflict rồi --continue hoặc --abort |

Không dùng git am cho một file diff thuần không có định dạng email. Không dùng git apply nếu mục tiêu là tự động tái tạo chuỗi commit từ format-patch.

### 6.2. Áp dụng mbox trên máy B

Trên máy B, dùng bản clone receiver-am riêng để thử format-patch. Không dùng lại receiver-project đã áp dụng diff patch ở phần trước:

~~~sh
cd receiver-am
git switch main
git status -sb
git rev-parse HEAD
~~~

Tạo nhánh nhận patch:

~~~sh
git switch -c review/offline-report-am
~~~

Áp dụng chuỗi patch:

~~~sh
git am --3way ../offline-report.mbox
~~~

Tùy chọn --3way cho phép Git thử áp dụng bằng cách dùng thông tin blob trong patch và object có sẵn nếu áp dụng trực tiếp thất bại. Nó chỉ hữu ích khi các blob cần thiết có sẵn trong repository và patch có thông tin phù hợp.

Kiểm tra kết quả:

~~~sh
git status -sb
git log --oneline --decorate main..HEAD
git show --stat --oneline HEAD
~~~

Nếu mbox chứa nhiều commit, kiểm tra đủ số commit và thứ tự như trên máy A. Author được giữ theo patch, nhưng committer thường là người áp dụng; commit SHA có thể khác.

### 6.3. Xử lý conflict khi git am

Nếu Git dừng do conflict:

~~~sh
git status
git am --show-current-patch=diff
~~~

Đọc patch hiện tại và chỉnh các file conflict. Sau đó:

~~~sh
git add <resolved-file>
git am --continue
~~~

Lặp lại cho tới khi chuỗi patch hoàn tất. Nếu không muốn tiếp tục:

~~~sh
git am --abort
~~~

Abort kết thúc phiên am đang dở và khôi phục trạng thái trước khi bắt đầu phiên đó. Trước khi abort hoặc tiếp tục, đọc status để hiểu Git đang ở bước nào.

## 7. Tạo Git bundle đầy đủ để chuyển lịch sử

Patch chỉ mang thay đổi; bundle mang object và ref được chọn. Trên máy A, tạo bundle chứa branch nền, branch tính năng và tag phát hành liên quan:

~~~sh
git bundle create ../offline-report-full.bundle refs/heads/main refs/heads/feature/offline-report
~~~

Nếu cần chuyển thêm tag:

~~~sh
git bundle create ../offline-report-release.bundle refs/heads/main refs/heads/feature/offline-report refs/tags/v1.0.0
~~~

Bundle đầy đủ chứa các object cần thiết để dựng lại những ref được chọn mà không yêu cầu repository nhận phải có commit nền trước đó. Phạm vi thực tế phụ thuộc ref được chỉ định; không mặc định bundle chứa mọi branch/tag nếu không yêu cầu.

### 7.1. Xem ref và xác minh bundle ở máy gửi

~~~sh
git bundle list-heads ../offline-report-full.bundle
git bundle verify ../offline-report-full.bundle
~~~

list-heads cho biết object ID và ref được quảng bá. verify kiểm tra định dạng bundle và prerequisite. Với bundle đầy đủ, không có prerequisite lịch sử bên ngoài cần có trước.

Kiểm tra danh sách phải có:

- refs/heads/main
- refs/heads/feature/offline-report
- Tag nếu đã chọn đưa vào.

Nếu thiếu ref, tạo lại bundle với ref đầy đủ. Không sửa file bundle bằng công cụ văn bản.

### 7.2. Vì sao cần bundle đầy đủ?

Bundle đầy đủ phù hợp khi:

- Máy nhận chưa có repository hoặc không chắc có commit nền nào.
- Cần tạo bản khôi phục độc lập.
- Chuyển repository giữa hai vùng mạng cô lập.
- Cần kiểm tra khả năng clone mà không dựa vào remote cũ.

Đổi lại, bundle đầy đủ có thể lớn vì chứa toàn bộ lịch sử cần thiết của các ref đã chọn. Nếu người nhận chắc chắn có commit nền, có thể dùng incremental bundle.

## 8. Tạo incremental bundle khi hai bên có commit nền

Giả sử máy B đã có commit nền giống máy A. Trên máy A, lưu SHA của commit nền:

~~~sh
git rev-parse main
~~~

Tạo bundle chỉ chứa các object mới trên branch tính năng kể từ base:

~~~sh
git bundle create ../offline-report-incremental.bundle refs/heads/feature/offline-report ^<base-commit>
~~~

Thay <base-commit> bằng SHA đã thống nhất. Cách viết này khai báo commit nền là prerequisite. Máy B phải có object đó trước khi bundle được áp dụng.

Có thể tạo bundle từ revision range:

~~~sh
git bundle create ../offline-report-incremental.bundle <base-commit>..refs/heads/feature/offline-report
~~~

### 8.1. Verify incremental bundle trên máy B

Trên máy B, chuyển vào repository receiver-bundle đã có commit nền rồi chạy verify:

~~~sh
cd receiver-bundle
git rev-parse <base-commit>
git bundle verify ../offline-report-incremental.bundle
~~~

Nếu thiếu prerequisite, Git sẽ báo repository hiện tại chưa có đủ commit cần thiết. Không bỏ qua lỗi này. Yêu cầu bundle nền hoặc bundle đầy đủ, rồi verify lại.

### 8.2. Fetch incremental bundle

Sau khi verify thành công, dùng bản clone receiver-bundle đã giữ nguyên commit nền:

~~~sh
git fetch ../offline-report-incremental.bundle refs/heads/feature/offline-report:refs/remotes/offline/incremental/feature/offline-report
git log --oneline --decorate main..refs/remotes/offline/incremental/feature/offline-report
~~~

Fetch cập nhật remote-tracking ref offline/incremental/feature/offline-report. Sau đó có thể tạo branch local để review:

~~~sh
git switch -c review/offline-report-incremental refs/remotes/offline/incremental/feature/offline-report
~~~

Nếu máy B chưa có base commit hoặc lịch sử đã bị rebase/force push, incremental bundle có thể không còn dùng được. Khi đó hãy xác định lại base hoặc dùng bundle đầy đủ.

## 9. Kiểm tra tính toàn vẹn và nguồn gốc file bàn giao

Bundle verify kiểm tra định dạng và prerequisite, nhưng không chứng minh ai tạo bundle. Patch cũng có thể bị thay đổi trong quá trình chuyển. Dùng checksum để phát hiện thay đổi file, và dùng chữ ký số hoặc kênh xác thực độc lập để xác minh nguồn gốc khi cần.

Trên Linux:

~~~sh
sha256sum ../offline-report.diff ../offline-report.mbox ../offline-report-full.bundle
~~~

Trên macOS:

~~~sh
shasum -a 256 ../offline-report.diff ../offline-report.mbox ../offline-report-full.bundle
~~~

Trên Windows PowerShell:

~~~powershell
Get-FileHash .\offline-report.diff -Algorithm SHA256
Get-FileHash .\offline-report.mbox -Algorithm SHA256
Get-FileHash .\offline-report-full.bundle -Algorithm SHA256
~~~

Ghi các checksum vào manifest:

~~~text
offline-report.diff        SHA256: <hash>
offline-report.mbox        SHA256: <hash>
offline-report-full.bundle SHA256: <hash>
base-commit                <commit-sha>
feature-tip                <commit-sha>
sender                     <team-or-person>
created-at                 <timestamp>
~~~

Manifest chỉ có giá trị xác thực nếu người nhận lấy nó từ nguồn đáng tin cậy. Nếu file và checksum cùng được tải từ một nơi không tin cậy, kẻ tấn công có thể thay cả hai.

Trước khi gửi:

- Rà soát patch và lịch sử để tìm secret.
- Xác nhận đúng ref và commit.
- Lưu bundle, patch và manifest trong vùng được phép.
- Mã hóa file khi chính sách yêu cầu.
- Giới hạn người nhận và thời gian lưu.

## 10. Khôi phục repository từ bundle vào thư mục mới

Đây là phần kiểm tra quan trọng nhất của bài lab. Không chỉ tạo bundle thành công; cần chứng minh người nhận có thể dựng lại repository từ file đó.

Trên máy B, chọn một đường dẫn đích mới chưa tồn tại, ví dụ restore-test:

~~~sh
git clone --branch feature/offline-report ../offline-report-full.bundle restore-test
~~~

Lệnh clone bundle tạo repository độc lập và checkout branch feature/offline-report. Nếu bundle không có branch này, xem list-heads và dùng đúng tên ref.

Đi vào thư mục khôi phục:

~~~sh
cd restore-test
git status -sb
git branch -a
git tag --list
git log --oneline --decorate --graph --all
~~~

Kiểm tra:

- Branch feature/offline-report tồn tại và đang được checkout.
- Commit tip khớp SHA đã ghi trong manifest.
- Các tag được chọn có mặt.
- Working tree sạch ngay sau clone.
- Nội dung file chính xác với phiên bản bàn giao.

### 10.1. So sánh commit tip

Trên máy A:

~~~sh
git rev-parse refs/heads/feature/offline-report
~~~

Trên repository restore-test:

~~~sh
git rev-parse HEAD
~~~

Hai SHA phải khớp nếu bundle được tạo từ cùng ref và không có bước viết lại lịch sử sau đó.

### 10.2. So sánh tree

Trên máy A:

~~~sh
git rev-parse "refs/heads/feature/offline-report^{tree}"
~~~

Trên máy B:

~~~sh
git rev-parse "HEAD^{tree}"
~~~

Tree SHA phải giống nhau nếu đang so sánh đúng cùng commit. Đây là cách xác nhận snapshot file được khôi phục.

### 10.3. Kiểm tra object database

~~~sh
git fsck --full
~~~

git fsck kiểm tra tính nhất quán object và liên kết trong repository. Nó có thể báo object unreachable trong một số repository; đọc kết quả theo ngữ cảnh, không mặc định mọi dòng cảnh báo đều là lỗi khôi phục.

### 10.4. Kiểm tra build và test

Bundle khôi phục thành công về mặt Git chưa đảm bảo ứng dụng chạy đúng. Chạy test hoặc build theo hướng dẫn của dự án sau khi xác nhận dependency và dữ liệu cần thiết có sẵn.

Với repository có submodule:

~~~sh
git submodule status
git submodule update --init --recursive
~~~

Trong môi trường ngoại tuyến, các repository con cũng cần có nguồn dữ liệu riêng; lệnh update có thể thất bại nếu URL submodule không truy cập được.

Với Git LFS:

~~~sh
git lfs ls-files
git lfs pull
~~~

Bundle Git thông thường không tự mang các LFS object được lưu ngoài Git object database. Cần chuyển LFS object theo quy trình riêng hoặc bảo đảm máy nhận có cache/remote LFS hợp lệ.

## 11. Khôi phục từ bundle vào repository đã có

Không phải lúc nào cũng cần clone mới. Nếu máy B đã có repository và muốn nhập branch:

~~~sh
git bundle verify ../offline-report-full.bundle
git bundle list-heads ../offline-report-full.bundle
git fetch ../offline-report-full.bundle refs/heads/feature/offline-report:refs/remotes/offline/full/feature/offline-report
~~~

Kiểm tra lịch sử:

~~~sh
git log --oneline --graph --decorate main..refs/remotes/offline/full/feature/offline-report
git diff --stat main...refs/remotes/offline/full/feature/offline-report
~~~

Sau khi review, tạo branch local:

~~~sh
git switch -c review/offline-report-bundle refs/remotes/offline/full/feature/offline-report
~~~

Clone mới phù hợp để kiểm tra khả năng phục hồi độc lập. Fetch phù hợp khi muốn nhập một ref vào repository đã có. Cả hai đều cần xác minh bundle và chọn đúng ref.

## 12. Đối chiếu kết quả Patch và Bundle

Patch và bundle có thể được tạo từ cùng một nhánh nhưng kết quả nhập khác nhau.

| Tiêu chí | Diff patch + git apply | Format-patch + git am | Bundle + clone/fetch |
|---|---|---|---|
| Nội dung thay đổi | Có | Có | Có qua object |
| Commit metadata | Không tự mang đầy đủ | Mang author/message của từng commit | Giữ nguyên commit object |
| Giữ nguyên commit SHA | Không tạo commit | Thường tạo SHA mới khi áp dụng | Có nếu lấy đúng object |
| Yêu cầu base | Thường cần tree tương thích | Cần lịch sử nền phù hợp | Full bundle độc lập; incremental cần prerequisite |
| Kết quả | Working tree (hoặc index nếu dùng --index) | Commit mới | Ref và object được fetch/clone |
| Dùng để review | Rất phù hợp | Rất phù hợp | Xem được lịch sử và diff |
| Dùng để khôi phục repository | Không | Không đầy đủ | Phù hợp trong phạm vi ref được đóng gói |

Nếu người nhận cần đúng commit SHA và toàn bộ lịch sử liên quan, bundle là phương án phù hợp hơn patch. Nếu cần review nội dung và áp dụng chọn lọc, patch thuận tiện hơn.

## 13. Xử lý lỗi trong bài thực hành

**Patch không áp dụng được.**

- Kiểm tra commit nền và trạng thái working tree.
- Chạy git apply --check trước khi áp dụng.
- Kiểm tra patch đã được áp dụng một phần hay chưa.
- Không ép bỏ qua lỗi nếu patch không khớp.

**git am dừng ở conflict.**

- Dùng git status và git am --show-current-patch=diff.
- Sửa conflict, stage file đã giải quyết rồi chạy git am --continue.
- Dùng git am --abort nếu cần hủy cả phiên.

**Bundle verify báo thiếu prerequisite.**

- Kiểm tra SHA base trên máy nhận.
- Xác minh bundle có phải incremental không.
- Chuyển bundle nền hoặc yêu cầu bundle đầy đủ.

**Bundle không có ref cần thiết.**

- Chạy git bundle list-heads.
- Kiểm tra tên ref được đưa vào lệnh create.
- Tạo lại bundle với ref đầy đủ.

**Clone bundle không chọn được branch.**

- Liệt kê ref.
- Dùng đúng tên branch trong --branch.
- Nếu bundle chỉ có tag hoặc ref khác, fetch ref cụ thể thay vì giả định branch mặc định.

**Restore clone thành công nhưng SHA không khớp.**

- Kiểm tra manifest và bundle đã nhận.
- Xác nhận branch nguồn có bị cập nhật sau khi tạo bundle không.
- Kiểm tra có bước rebase hoặc rewrite history sau bàn giao không.
- Không tự sửa ref để làm SHA khớp khi chưa xác định nguyên nhân.

**Repository khôi phục thiếu file LFS hoặc submodule.**

- Kiểm tra pointer LFS và gitlink.
- Chuyển object LFS và repository con theo quy trình riêng.
- Không kết luận bundle hỏng nếu phần thiếu nằm ngoài Git object database.

## 14. Bàn giao file và thông tin cho người nhận

Một gói bàn giao nên có cấu trúc rõ ràng:

~~~text
offline-handoff/
├── offline-report.diff
├── offline-report.mbox
├── offline-report-full.bundle
├── SHA256SUMS.txt
└── HANDOFF.txt
~~~

HANDOFF.txt nên ghi:

- Repository và mục đích chuyển giao.
- Branch và commit nền.
- Branch tip và tag liên quan.
- Bundle đầy đủ hay incremental.
- Prerequisite nếu có.
- Lệnh verify, clone hoặc fetch được đề xuất.
- Checksum/chữ ký và cách xác minh.
- Người gửi, thời điểm và kênh liên hệ được phép.

Không ghi token, password, private key hoặc dữ liệu khách hàng vào HANDOFF.txt. Không đưa file cấu hình local hoặc credential helper vào gói bàn giao.

## 15. Tiêu chí hoàn thành bài lab

Đánh dấu hoàn thành khi tất cả điều kiện phù hợp đều đạt:

- [ ] Máy A có nhánh feature/offline-report với commit đã kiểm tra.
- [ ] Đã tạo diff patch và kiểm tra bằng git apply --check.
- [ ] Đã tạo format-patch mbox và hiểu cách áp dụng bằng git am.
- [ ] Máy B đã áp dụng được ít nhất một loại patch trên đúng commit nền.
- [ ] Đã tạo bundle đầy đủ và xác minh thành công.
- [ ] Đã liệt kê và xác nhận ref trong bundle.
- [ ] Đã thử incremental bundle hoặc giải thích rõ prerequisite.
- [ ] Đã tạo checksum/manifest và xác minh file nhận.
- [ ] Đã clone bundle vào thư mục restore-test riêng.
- [ ] SHA commit và tree được khôi phục khớp với nguồn.
- [ ] git status sau clone sạch và git fsck được kiểm tra.
- [ ] Đã xác định phần Git LFS, submodule, config và hook cần chuyển riêng.
- [ ] Không đưa credential hoặc dữ liệu riêng vào gói bàn giao.

## 16. Câu hỏi tự đánh giá

1. Vì sao diff patch và format-patch cần các lệnh áp dụng khác nhau?
2. Khi nào git apply phù hợp hơn git am?
3. Vì sao git am có thể tạo commit SHA khác với máy gửi?
4. Bundle đầy đủ khác incremental bundle ở prerequisite như thế nào?
5. Vì sao cần chạy git bundle verify trên repository nhận?
6. Checksum có chứng minh ai là người tạo bundle không? Vì sao?
7. Khi nào nên clone từ bundle và khi nào nên fetch bundle?
8. Vì sao cần clone vào thư mục restore-test thay vì ghi đè repository hiện tại?
9. Git bundle có tự chuyển Git LFS object, submodule, hook và credential không?
10. Nếu restore clone có SHA khác nguồn, bạn sẽ kiểm tra điều gì trước khi sửa ref?

## 17. Kết luận

Trao đổi ngoại tuyến an toàn cần kết hợp đúng công cụ và kiểm tra kết quả. Diff patch giúp chuyển phần thay đổi; format-patch và git am giúp tái tạo chuỗi commit với metadata tác giả; Git bundle giúp chuyển object và ref để clone hoặc fetch khi không có remote trực tiếp.

Đừng dừng ở việc tạo file thành công. Hãy xác minh patch, prerequisite, ref, checksum và nguồn gốc; sau đó clone bundle vào một thư mục mới, đối chiếu commit SHA và tree, kiểm tra object database rồi chạy test phù hợp. Một bản bàn giao chỉ đáng tin khi người nhận có thể kiểm tra và khôi phục được trong điều kiện dự kiến.
