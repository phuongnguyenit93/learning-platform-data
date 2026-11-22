# Phân biệt Git LFS với khả năng lưu trữ đối tượng của Git

Git có thể lưu mọi loại nội dung dưới dạng object, bao gồm ảnh, video, bản thiết kế, mô hình 3D và các file nhị phân lớn. Tuy nhiên, việc Git lưu được một file không có nghĩa repository sẽ luôn gọn hoặc thao tác clone, fetch và push sẽ hiệu quả khi file lớn thay đổi thường xuyên. Git LFS (Large File Storage) bổ sung một cơ chế lưu nội dung lớn ở máy chủ riêng, còn repository Git chỉ lưu một file con trỏ nhỏ để xác định chính xác phiên bản nội dung cần dùng.

Điểm cần phân biệt là: **Git lưu nội dung file trực tiếp trong object database; Git LFS lưu con trỏ trong Git và chuyển nội dung thực sang kho LFS bên ngoài.** Hai cơ chế vẫn phối hợp để commit có thể ghim chính xác phiên bản của từng file.

## 1. Git lưu file bằng object như thế nào?

Git sử dụng mô hình lưu trữ nội dung theo mã định danh (*content-addressable storage*). Mỗi nội dung được lưu thành một object có mã định danh được tính từ loại object và dữ liệu của nó. Với file thông thường, Git tạo một **blob object** chứa nội dung file.

Một số loại object cơ bản:

| Object | Vai trò |
|---|---|
| Blob | Lưu byte nội dung của một file; không tự lưu tên file hoặc đường dẫn |
| Tree | Lưu danh sách tên, mode và object được tham chiếu trong một thư mục |
| Commit | Ghi nhận một tree, commit cha, tác giả, người tạo commit, thời gian và thông điệp |
| Tag | Có thể là ref trực tiếp hoặc tag object có metadata trỏ tới object khác |

Ví dụ, khi commit một ảnh `assets/banner.png`, Git lưu byte của ảnh trong blob. Tree của thư mục `assets/` ghi tên `banner.png` cùng mode và mã object của blob đó. Commit trỏ tới tree chứa thư mục này.

Tên file và đường dẫn không nằm trong blob. Vì vậy, cùng một nội dung có thể được nhiều tree hoặc commit tham chiếu mà không cần lưu một bản blob riêng chỉ vì file được đổi tên.

## 2. Git lưu các phiên bản file lớn ra sao?

Git lưu snapshot của nội dung ở từng commit. Khi file thay đổi, phiên bản mới có thể tạo blob mới với mã object mới. Nếu nội dung giống hệt một blob đã có, Git có thể tái sử dụng object đó nhờ cơ chế định danh theo nội dung.

Trong repository thực tế, Git thường đóng gói object vào packfile. Khi đóng gói, Git có thể dùng nén và delta compression để lưu khác biệt giữa những object tương tự thay vì lưu nguyên vẹn từng bản lặp. Cách này tiết kiệm đáng kể với nhiều file văn bản hoặc nội dung có cấu trúc tương tự.

Tuy nhiên, file nhị phân lớn như video, ảnh đã nén, file thiết kế hoặc archive thường khó tạo delta nhỏ. Một thay đổi nhỏ ở file cũng có thể làm phần lớn byte thay đổi, khiến phiên bản mới vẫn tốn nhiều dung lượng. Kết quả là repository có thể tăng nhanh theo số phiên bản file lớn.

Git không có một giới hạn kích thước file cố định áp dụng cho mọi repository. Giới hạn thực tế có thể đến từ nhà cung cấp hosting, cấu hình máy chủ, hệ thống file, bộ nhớ, thời gian truyền tải hoặc chính sách nhóm. Một file lớn có thể commit thành công trên máy local nhưng bị remote từ chối khi push.

## 3. Vì sao lưu file lớn trực tiếp trong Git có thể bất tiện?

Khi file lớn được lưu trực tiếp trong object database, các object của nó trở thành một phần lịch sử repository. Các thao tác như clone hoặc fetch có thể cần tải các object đó tùy lịch sử và ref được lấy.

Một số hệ quả thường gặp:

- **Repository tăng dung lượng:** nhiều phiên bản của file nhị phân có thể làm packfile lớn dần.
- **Clone và fetch chậm:** người chỉ cần mã nguồn vẫn có thể phải tải nhiều object lớn thuộc lịch sử được lấy về.
- **Push tốn thời gian:** phiên bản mới của file lớn cần được truyền lên remote cùng các object Git khác.
- **Khó loại bỏ dữ liệu đã commit:** xóa file ở commit mới không tự xóa blob cũ khỏi lịch sử; muốn loại bỏ cần viết lại lịch sử và phối hợp với người dùng repository.
- **Khó đáp ứng giới hạn hosting:** nhà cung cấp có thể áp dụng giới hạn kích thước object hoặc tổng dung lượng repository.

Không phải mọi file lớn đều cần LFS. Nếu file ít thay đổi, dung lượng vừa phải, cần hoạt động offline hoàn toàn hoặc repository có chính sách lưu trữ phù hợp, lưu trực tiếp trong Git có thể đơn giản hơn. LFS hữu ích khi file lớn hoặc nhị phân thay đổi thường xuyên và chi phí tải toàn bộ lịch sử trở thành vấn đề.

## 4. Git LFS thay đổi mô hình lưu trữ như thế nào?

Git LFS giữ file lớn trong một kho đối tượng LFS riêng, thường được phục vụ bởi nền tảng hosting hoặc máy chủ LFS. Trong Git repository, nội dung file được thay bằng một **pointer file** dạng văn bản nhỏ.

Ví dụ pointer LFS:

```text
version https://git-lfs.github.com/spec/v1
oid sha256:4cac19622fc3ada9c0fdeadb33f88f367b541f38b8914d9d6c6f9c1e6c9a4f1b
size 84977953
```

Các dòng có ý nghĩa:

- `version` xác định phiên bản định dạng pointer.
- `oid sha256` là mã SHA-256 của nội dung file thực được lưu trong kho LFS.
- `size` là kích thước nội dung file thực tính bằng byte.

Git commit pointer file như một blob thông thường. Khi checkout, Git LFS dùng OID và kích thước trong pointer để tìm đúng nội dung nhị phân ở máy chủ LFS rồi đặt nội dung đó vào working tree.

Do đó, Git vẫn quản lý lịch sử phiên bản: commit A có thể trỏ tới pointer OID thứ nhất, commit B trỏ tới pointer OID thứ hai. Mỗi commit xác định chính xác phiên bản file lớn cần dùng mà không cần lưu toàn bộ byte của file lớn trong Git object database.

## 5. So sánh Git object storage và Git LFS

| Tiêu chí | Git lưu trực tiếp | Git LFS |
|---|---|---|
| Nội dung trong Git commit | Blob chứa byte file thực | Blob chứa pointer văn bản |
| Nơi lưu nội dung lớn | Object database của repository Git | Kho LFS bên ngoài Git object database |
| Phiên bản được xác định bằng | Git object ID của blob | OID SHA-256 trong pointer LFS |
| Clone repository | Có thể cần tải các object lớn thuộc lịch sử được lấy | Tải pointer; LFS tải nội dung cần thiết theo cấu hình checkout |
| Push | Gửi Git objects tới remote Git | Upload LFS objects và cập nhật Git refs |
| Diff file nhị phân | Thường không hữu ích nếu không có diff driver riêng | Pointer thay đổi khi nội dung LFS đổi; nội dung lớn vẫn cần công cụ phù hợp để so sánh |
| Phụ thuộc dịch vụ | Chỉ cần Git remote | Cần cả Git remote và LFS endpoint có quyền truy cập |
| Dung lượng | Làm tăng dung lượng Git object database | Làm tăng dung lượng lưu trữ và băng thông LFS |
| Phù hợp | Mã nguồn, văn bản, file nhỏ/vừa hoặc ít thay đổi | File lớn, nhị phân và thay đổi thường xuyên |

LFS không làm biến mất chi phí lưu trữ. Nó chuyển chi phí lưu nội dung lớn sang dịch vụ LFS và giúp repository Git giữ lịch sử con trỏ nhỏ gọn hơn. Nhà cung cấp LFS vẫn có thể tính quota dung lượng và băng thông tải xuống.

## 6. Git LFS dùng clean và smudge filter

Git LFS tích hợp với Git thông qua cơ chế filter:

- **Clean filter:** khi nội dung được đưa vào index, filter chuyển file lớn thành pointer LFS trước khi Git tạo blob.
- **Smudge filter:** khi checkout nội dung ra working tree, filter đọc pointer và thay bằng file thực đã tải hoặc lấy từ cache LFS.

Lệnh `git lfs install` cấu hình các filter cần thiết và cài hook hỗ trợ Git LFS cho người dùng hiện tại. Vì vậy, khi clone hoặc checkout một repository có pointer LFS, máy cần Git LFS được cài và cấu hình để tự động lấy nội dung thực.

Nếu Git LFS chưa được cài, Git vẫn có thể checkout pointer văn bản như một file bình thường. Khi đó, bạn có thể thấy nội dung bắt đầu bằng `version https://git-lfs.github.com/spec/v1` thay vì file nhị phân mong muốn.

## 7. Cài đặt và cấu hình Git LFS

Git LFS là công cụ mở rộng cài riêng bên cạnh Git. Sau khi cài theo hướng dẫn phù hợp với hệ điều hành, xác minh:

```bash
git lfs version
```

Cài cấu hình cho tài khoản hiện tại:

```bash
git lfs install
```

Lệnh này thiết lập filter và hook để Git tích hợp với Git LFS. Trong môi trường CI hoặc máy dùng chung, cần xác định rõ tài khoản và nơi cài đặt; không mặc định rằng mọi máy clone đều đã có Git LFS.

Kiểm tra thông tin môi trường LFS:

```bash
git lfs env
```

Lệnh hiển thị endpoint, thư mục lưu object LFS local và một số cấu hình liên quan. Tránh chia sẻ đầu ra nguyên vẹn nếu nó chứa đường dẫn nội bộ hoặc thông tin endpoint riêng của tổ chức.

## 8. Chọn file nào được quản lý bằng LFS

Git LFS dùng `.gitattributes` để xác định pattern file cần chuyển qua filter LFS. Ví dụ theo dõi mọi file PSD:

```bash
git lfs track "*.psd"
```

Lệnh cập nhật `.gitattributes` với quy tắc tương tự:

```gitattributes
*.psd filter=lfs diff=lfs merge=lfs -text
```

Bạn có thể theo dõi thêm các loại file khác:

```bash
git lfs track "*.mp4"
git lfs track "*.zip"
git lfs track "*.blend"
```

Pattern trong `.gitattributes` xác định đường dẫn áp dụng LFS. Hãy kiểm tra quy tắc đã được ghi đúng và tránh đưa các file không cần thiết vào LFS.

Sau khi cấu hình pattern, thêm cả `.gitattributes` và file lớn:

```bash
git add .gitattributes
git add assets/banner.psd
git status
git check-attr filter diff merge text -- assets/banner.psd
```

Lệnh `git check-attr` giúp xác nhận file có các thuộc tính LFS mong muốn hay không. Sau đó tạo commit:

```bash
git commit -m "Track design assets with Git LFS"
```

Commit sẽ lưu `.gitattributes` cùng pointer của file LFS trong Git. Nội dung nhị phân được Git LFS quản lý riêng.

## 9. `git lfs track` không tự chuyển lịch sử cũ

Một điểm rất dễ nhầm: chạy `git lfs track "*.psd"` không tự di chuyển các blob PSD đã có trong những commit trước sang kho LFS. Lệnh chỉ cập nhật quy tắc `.gitattributes` để các lần add tiếp theo xử lý file theo LFS.

Nếu file đã được Git theo dõi trực tiếp, sau khi thêm pattern, bạn cần đưa file qua quy trình add/commit mới để phiên bản mới trở thành pointer. Các phiên bản cũ vẫn còn là blob Git trong lịch sử.

Nếu mục tiêu là chuyển các phiên bản cũ trong lịch sử sang LFS, có thể cần dùng công cụ migration:

```bash
git lfs migrate import --include="*.psd" --everything
```

Thao tác này viết lại các commit có liên quan để thay blob thông thường bằng pointer LFS. Vì commit object thay đổi, hash commit và lịch sử branch/tag liên quan có thể thay đổi. Đây là công việc ảnh hưởng toàn repository, cần lập kế hoạch, sao lưu, phối hợp với mọi người và chuẩn bị quy trình cập nhật clone trước khi push lịch sử mới. Không chạy migration trên nhánh dùng chung một cách tùy tiện.

## 10. Clone repository có Git LFS

Khi Git LFS đã được cài và `git lfs install` đã được thực hiện, clone repository thường sẽ tải pointer và nội dung LFS cần thiết cho working tree:

```bash
git clone https://git.example.com/team/design-assets.git
```

Git clone repository và checkout commit; filter LFS xử lý pointer để lấy nội dung file thực từ LFS endpoint. Nếu không có quyền truy cập endpoint LFS, clone có thể tải được repository Git nhưng không lấy được file lớn.

Trong môi trường cần clone nhanh hoặc không muốn tải ngay các file LFS, có thể bỏ qua smudge khi clone rồi tải sau:

```bash
GIT_LFS_SKIP_SMUDGE=1 git clone https://git.example.com/team/design-assets.git
cd design-assets
git lfs pull
```

Trong PowerShell trên Windows, có thể đặt biến môi trường cho tiến trình hiện tại trước khi clone:

```powershell
$env:GIT_LFS_SKIP_SMUDGE = "1"
git clone https://git.example.com/team/design-assets.git
Set-Location design-assets
git lfs pull
Remove-Item Env:GIT_LFS_SKIP_SMUDGE
```

Khi bỏ qua smudge, working tree có thể giữ pointer thay vì nội dung file thực cho đến khi bạn chạy `git lfs pull` hoặc thao tác checkout LFS tương ứng.

## 11. Fetch và pull nội dung LFS

Git fetch tải Git objects và cập nhật remote-tracking refs. Nội dung LFS được tải theo cơ chế riêng của Git LFS.

Một số lệnh thường dùng:

```bash
git lfs fetch origin main
```

Lệnh tải các LFS objects được tham chiếu bởi phạm vi ref đã chỉ định vào cache local; nó không nhất thiết thay nội dung pointer trong working tree.

```bash
git lfs pull origin main
```

`git lfs pull` kết hợp fetch LFS với checkout nội dung LFS vào working tree cho ref/checkout hiện tại theo cách Git LFS hỗ trợ. Đây là lệnh hữu ích sau khi chuyển nhánh hoặc khi cần lấy lại nội dung LFS bị bỏ qua lúc clone.

Để chỉ tải một nhóm file phù hợp pattern, có thể dùng include/exclude:

```bash
git lfs fetch --include="assets/**/*.psd" --exclude="assets/archive/**" origin main
```

Phạm vi include/exclude giúp giảm lượng dữ liệu tải về khi repository chứa nhiều file LFS. Hãy kiểm tra pattern và ref trước khi tải.

## 12. Push commit có chứa file LFS

Khi đẩy commit có pointer LFS, Git cần bảo đảm nội dung LFS tương ứng đã được upload lên LFS server. Hook `pre-push` do `git lfs install` cài đặt thường tự động upload các object cần thiết trước khi Git cập nhật ref trên remote:

```bash
git push origin main
```

Nếu hook bị tắt hoặc môi trường push không chạy hook, Git ref có thể được gửi mà object LFS cần thiết chưa được upload; người khác sẽ gặp lỗi khi tải file. Trong trường hợp cần upload rõ ràng, có thể dùng:

```bash
git lfs push origin main
```

Hoặc upload mọi object LFS được tham chiếu bởi các ref local:

```bash
git lfs push --all origin
```

`--all` có thể gửi nhiều dữ liệu, nên cân nhắc dung lượng và quyền trước khi dùng. Với quy trình bình thường, cài đặt hook đúng và dùng `git push` thường là đủ.

## 13. Kiểm tra file nào đang dùng LFS

Liệt kê file LFS được theo dõi:

```bash
git lfs ls-files
```

Kiểm tra trạng thái LFS:

```bash
git lfs status
```

Xem các thuộc tính được áp dụng cho một file:

```bash
git check-attr filter diff merge text -- assets/banner.psd
```

Xem pointer đã commit trong Git:

```bash
git show HEAD:assets/banner.psd
```

Nếu file đã được chuyển sang LFS, lệnh trên thường hiển thị pointer văn bản, không phải nội dung nhị phân. Đây là bằng chứng rằng Git object database lưu pointer cho đường dẫn đó.

Ngược lại, `git lfs ls-files` cho biết các đường dẫn được nhận diện là LFS trong revision hiện tại và OID tương ứng. Kết hợp hai lệnh sẽ giúp xác định file đang được quản lý theo cơ chế nào.

## 14. Phân biệt dung lượng Git và dung lượng LFS

Lệnh sau thống kê object trong kho Git local:

```bash
git count-objects -vH
```

Kết quả phản ánh loose objects và packfiles của Git. Nó không phải số liệu tổng dung lượng LFS trên máy chủ. Cache LFS local được lưu ở vị trí do Git LFS cấu hình; xem đường dẫn bằng:

```bash
git lfs env
```

Dung lượng LFS trên server cần kiểm tra bằng giao diện hoặc API/quản trị của nhà cung cấp. Git không thể suy ra quota lưu trữ và băng thông còn lại chỉ từ object database local.

Khi repository vẫn rất lớn sau khi chuyển một số file sang LFS, có thể do các blob cũ vẫn còn trong lịch sử Git. Cần xác định file lớn đã từng được commit trực tiếp hay chưa và có cần migration viết lại lịch sử hay không.

## 15. Những giới hạn và đánh đổi của Git LFS

Git LFS giải quyết vấn đề lưu trữ và truyền file lớn, nhưng tạo thêm phụ thuộc vận hành:

- **Cần LFS server:** Git remote và LFS endpoint có thể có quyền truy cập, URL và chính sách riêng.
- **Có thể phát sinh quota:** nhà cung cấp có thể tính dung lượng lưu trữ và băng thông tải xuống.
- **Không phải mọi công cụ đều hiểu pointer:** công cụ build, archive hoặc xử lý file ngoài Git có thể nhận pointer nếu LFS chưa materialize nội dung.
- **Làm việc offline cần chuẩn bị:** file LFS chưa tải về sẽ không có nội dung thực trong working tree.
- **Migration có ảnh hưởng lịch sử:** chuyển blob cũ sang LFS có thể viết lại commit và buộc các clone khác đồng bộ lại.
- **Không thay thế quản lý artifact:** file build đầu ra, bản phát hành và dữ liệu triển khai có thể phù hợp hơn với artifact registry hoặc object storage chuyên dụng.

LFS cũng không tự giải quyết việc cộng tác chỉnh sửa nhị phân. Nếu nhiều người cùng sửa file thiết kế hoặc file media, Git LFS có thể hỗ trợ locking ở những máy chủ và workflow được cấu hình, nhưng nhóm vẫn cần quy trình tránh ghi đè phiên bản của nhau.

## 16. Chọn Git hay Git LFS cho một loại file

Hãy cân nhắc các yếu tố sau:

| Câu hỏi | Nếu câu trả lời là “Có” |
|---|---|
| File có dung lượng lớn và thay đổi thường xuyên không? | Cân nhắc Git LFS |
| File là binary khó delta-compress như video, PSD, model 3D hoặc archive? | LFS thường phù hợp hơn khi lịch sử tăng nhanh |
| Mọi thành viên cần clone đầy đủ nội dung offline ngay lập tức? | Lưu trực tiếp trong Git có thể đơn giản hơn; nếu dùng LFS cần quy trình tải/cache rõ ràng |
| Máy chủ Git có hỗ trợ LFS và nhóm có quota phù hợp không? | Có thể triển khai LFS; cần kiểm tra chi phí lưu trữ và băng thông |
| File là artifact build có thể tái tạo hoặc dữ liệu triển khai? | Cân nhắc artifact registry hoặc object storage thay vì đưa vào Git/LFS |
| File nhỏ, văn bản và cần diff/merge theo dòng? | Git trực tiếp thường phù hợp hơn |

Không nên chọn LFS chỉ vì phần mở rộng file. Hãy dựa trên dung lượng, tần suất thay đổi, khả năng so sánh nội dung, yêu cầu offline, chính sách hosting và nhu cầu lưu giữ lịch sử.

## 17. Quy trình thực hành từ đầu đến cuối

Giả sử dự án có file thiết kế `assets/product-mockup.psd` dung lượng lớn và nhóm quyết định quản lý bằng LFS.

1. Cài Git LFS và xác nhận công cụ:

   ```bash
   git lfs version
   git lfs install
   ```

2. Đăng ký pattern:

   ```bash
   git lfs track "*.psd"
   ```

3. Kiểm tra và stage `.gitattributes` cùng file thiết kế:

   ```bash
   git check-attr filter diff merge text -- assets/product-mockup.psd
   git add .gitattributes assets/product-mockup.psd
   git status
   ```

4. Tạo commit:

   ```bash
   git commit -m "Add product mockup through Git LFS"
   ```

5. Xác nhận Git lưu pointer và LFS nhận diện file:

   ```bash
   git show HEAD:assets/product-mockup.psd
   git lfs ls-files
   git lfs status
   ```

6. Push lên remote có hỗ trợ LFS:

   ```bash
   git push origin main
   ```

7. Trên một clone khác có Git LFS, clone repository và xác nhận nội dung thực được tải:

   ```bash
   git clone https://git.example.com/team/product.git
   git -C product lfs ls-files
   ```

Nếu clone được thực hiện với `GIT_LFS_SKIP_SMUDGE=1`, chạy `git lfs pull` trong repository để tải và materialize nội dung.

## 18. Ghi nhớ

Git lưu nội dung file trực tiếp dưới dạng blob trong object database; packfile và delta compression có thể giảm dung lượng nhưng không bảo đảm file nhị phân lớn thay đổi thường xuyên sẽ rẻ để lưu và truyền. Git LFS giữ pointer nhỏ trong Git, còn nội dung thực được lưu ở LFS server và được tải khi cần checkout. Commit vẫn ghim đúng phiên bản qua OID và kích thước trong pointer. Hãy chọn LFS dựa trên đặc điểm file và chi phí vận hành, cài Git LFS trên máy làm việc/CI, kiểm tra endpoint và quota, đồng thời nhớ rằng `git lfs track` không tự chuyển các blob cũ trong lịch sử.
