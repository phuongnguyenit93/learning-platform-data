# Pointer file, kho đối tượng LFS và vai trò của .gitattributes

Git được tối ưu cho việc quản lý mã nguồn và lịch sử thay đổi. Khi repository chứa nhiều tệp nhị phân lớn như video, ảnh thiết kế, mô hình 3D, bộ dữ liệu hoặc tệp âm thanh, mỗi lần clone và đồng bộ có thể trở nên nặng nề. Git Large File Storage (Git LFS) giải quyết vấn đề này bằng cách lưu một pointer nhỏ trong lịch sử Git, còn nội dung thực tế được lưu trong kho đối tượng LFS riêng.

Để cơ chế hoạt động đúng, repository cần khai báo loại tệp bằng .gitattributes, máy phát triển cần cài Git LFS và remote phải có dịch vụ lưu trữ LFS tương ứng. Bài học thuộc chương **Tệp lớn và LFS** của module SOURCE_CONTROL_GIT, nơi bạn học cách quản lý working tree, staging area, commit, branch, remote và tag để cộng tác và phát hành có thể truy vết.

## 1. Vì sao cần Git LFS?

Trong Git thông thường, nội dung mỗi phiên bản tệp được lưu dưới dạng blob trong object database. Git có thể nén và lưu delta giữa các phiên bản, nhưng với nhiều tệp nhị phân lớn, việc thay đổi một phần nhỏ cũng có thể tạo ra blob mới có dung lượng đáng kể. Khi clone hoặc fetch lịch sử chứa những tệp đó, người dùng có thể phải tải nhiều dữ liệu mà công việc hiện tại không cần.

Git LFS tách phần nội dung lớn ra khỏi Git object database:

- Git lưu một **pointer file** nhỏ, có thể được commit, merge và gắn với lịch sử như các tệp khác.
- Nội dung tệp lớn được lưu thành **LFS object** trong kho lưu trữ LFS trên server.
- Pointer chứa định danh nội dung (OID) và kích thước, giúp Git LFS tìm đúng object khi checkout hoặc tải về.

Ví dụ, thay vì lưu trực tiếp tệp assets/product-demo.mp4 nặng 300 MB trong Git blob, Git commit một pointer chỉ vài dòng. Nội dung video được tải lên LFS storage khi push và tải xuống khi máy khác cần checkout tệp đó.

Git LFS không thay thế Git. Git vẫn quản lý commit, branch, tag và pointer; LFS quản lý nội dung nhị phân lớn được pointer tham chiếu.

## 2. Pointer file có cấu trúc như thế nào?

Một pointer LFS phiên bản 1 điển hình là tệp văn bản UTF-8/ASCII nhỏ với các trường:

~~~text
version https://git-lfs.github.com/spec/v1
oid sha256:4cac196e6f2f4c2f7d5a1c9f6b8e3d4a2c1f0e9d8b7a6c5d4e3f2a1b0c9d8e7f
size 314572800
~~~

Đây là ví dụ minh họa định dạng; OID thực tế phải là SHA-256 của nội dung tệp tương ứng.

| Trường | Ý nghĩa |
| --- | --- |
| version | Phiên bản đặc tả pointer LFS |
| oid sha256:<hash> | Mã định danh nội dung dựa trên SHA-256 |
| size <bytes> | Kích thước nội dung gốc tính bằng byte |

OID giúp Git LFS xác định object theo nội dung. Nếu hai đường dẫn hoặc hai commit tham chiếu đến cùng nội dung, chúng có thể dùng chung một LFS object vì OID giống nhau. Khi nội dung thay đổi, SHA-256 thay đổi và pointer sẽ trỏ đến object khác.

Pointer không chứa tên tệp. Tên và đường dẫn nằm trong Git tree như các mục khác; pointer chỉ xác định nội dung cần lấy. Đặc tả có thể có thêm thông tin mở rộng (extension) trong các trường hợp dùng extension của LFS, nhưng ba trường trên là dạng cơ bản thường gặp.

### Phân biệt OID LFS và Git blob ID

Đây là hai định danh khác nhau:

- **OID trong pointer LFS** là SHA-256 của nội dung tệp lớn.
- **Git blob ID** là hash của pointer text được Git lưu trong object database. Tùy định dạng repository, Git có thể dùng SHA-1 hoặc SHA-256 cho object ID.

Vì Git lưu pointer text, nên khi xem blob của một tệp LFS trong commit, bạn thường thấy vài dòng pointer chứ không thấy nội dung nhị phân gốc:

~~~bash
git show HEAD:assets/product-demo.mp4
~~~

Trong working tree sau khi LFS smudge thành công, tệp assets/product-demo.mp4 lại chứa nội dung video thực tế.

## 3. LFS object được lưu ở đâu?

Git LFS lưu nội dung theo OID trong một kho object riêng, tách khỏi object database Git. Trong bản cài đặt thông thường, bản sao object cục bộ nằm dưới Git directory, thường ở:

~~~text
.git/lfs/objects/
~~~

Đường dẫn thực tế có thể thay đổi theo cấu hình lfs.storage, linked worktree hoặc cách tổ chức repository. Dùng lệnh sau để xem các đường dẫn và endpoint mà Git LFS đang sử dụng:

~~~bash
git lfs env
~~~

LFS object thường được tổ chức theo các phần đầu của OID để tránh tập trung quá nhiều tệp trong một thư mục. Không nên tự di chuyển, đổi tên hoặc chỉnh sửa các object trong kho này; hãy để Git LFS quản lý bằng các lệnh fetch, pull, push và prune tương ứng.

Trên máy chủ, LFS object được lưu trong dịch vụ lưu trữ LFS, có thể được tích hợp với nền tảng Git hoặc triển khai riêng. Kho Git và kho LFS là hai lớp lưu trữ khác nhau:

| Thành phần | Lưu trữ | Vai trò |
| --- | --- | --- |
| Git object database | Commit, tree, blob và tag | Lịch sử, cấu trúc thư mục và pointer file |
| LFS object storage | Nội dung nhị phân lớn | Dữ liệu thực tế được pointer tham chiếu |
| Git remote refs | Branch và tag | Cho biết commit nào là mốc hiện tại hoặc phiên bản phát hành |
| LFS endpoint | Dịch vụ HTTP/API của LFS | Xác thực và trao đổi LFS object giữa client và server |

Do tách biệt này, việc push Git commit thành công không tự chứng minh rằng mọi LFS object đã có trên server. Quy trình push thông thường cần Git LFS upload các object trước khi cập nhật ref Git.

## 4. Vai trò của .gitattributes

.gitattributes cho Git biết những đường dẫn nào cần được xử lý bởi Git LFS. Khi chạy git lfs track, Git LFS thêm pattern vào tệp này.

Ví dụ:

~~~gitattributes
*.psd filter=lfs diff=lfs merge=lfs -text
*.mp4 filter=lfs diff=lfs merge=lfs -text
*.zip filter=lfs diff=lfs merge=lfs -text
~~~

Ý nghĩa các thuộc tính:

| Thuộc tính | Vai trò |
| --- | --- |
| filter=lfs | Chỉ định clean/smudge/process filter của Git LFS |
| diff=lfs | Dùng diff driver của LFS cho pointer và thông tin tệp LFS |
| merge=lfs | Dùng merge driver của LFS để xử lý pointer trong quá trình merge |
| -text | Tắt chuẩn hóa line ending dạng văn bản cho tệp nhị phân |

.gitattributes được commit vào repository để mọi thành viên nhận cùng quy tắc theo đường dẫn. Cấu hình filter thực thi của Git LFS lại được cài trên từng máy bằng git lfs install.

### Track một loại tệp

Sau khi cài Git LFS, chạy:

~~~bash
git lfs install
git lfs track "*.psd"
git lfs track "*.mp4"
git lfs track "*.zip"
~~~

Lệnh git lfs track cập nhật .gitattributes. Hãy kiểm tra và commit tệp này cùng với thay đổi:

~~~bash
git status
git diff -- .gitattributes
git add .gitattributes
~~~

Pattern cần được đặt trong dấu nháy khi gọi từ shell để Git LFS nhận đúng pattern thay vì shell tự mở rộng wildcard theo các tệp đang có.

### Kiểm tra thuộc tính hiệu lực

Dùng git check-attr để xem Git sẽ xử lý đường dẫn như thế nào:

~~~bash
git check-attr filter diff merge text -- assets/design.psd
~~~

Kết quả mong đợi cho một tệp được track bằng LFS có dạng tương tự:

~~~text
assets/design.psd: filter: lfs
assets/design.psd: diff: lfs
assets/design.psd: merge: lfs
assets/design.psd: text: unset
~~~

Nếu thuộc tính không như mong đợi, kiểm tra pattern, vị trí .gitattributes và các tệp attributes có mức ưu tiên cao hơn như $GIT_DIR/info/attributes.

## 5. Clean, smudge và process filter hoạt động thế nào?

Git LFS tích hợp với Git thông qua filter. Hai thao tác quan trọng là clean và smudge:

- **Clean filter** chạy khi nội dung được đưa vào Git, thường qua git add. Nó lưu nội dung thực tế vào LFS object store cục bộ rồi trả về pointer để Git đưa vào index và commit.
- **Smudge filter** chạy khi Git checkout nội dung từ index/commit ra working tree. Nó đọc pointer, tìm LFS object tương ứng trong cache; nếu chưa có, có thể tải từ LFS endpoint rồi ghi nội dung thực tế ra tệp.

Git LFS hiện đại thường cấu hình thêm process filter để xử lý nhiều yêu cầu hiệu quả hơn. git lfs install thiết lập các khóa cấu hình filter cần thiết cho Git.

### Luồng khi thêm tệp

Giả sử bạn thêm assets/scene.psd:

1. .gitattributes khớp pattern *.psd.
2. Bạn chạy git add assets/scene.psd.
3. Git gọi LFS clean/process filter.
4. Git LFS tính SHA-256, ghi nội dung vào LFS object store local và tạo pointer.
5. Git index nhận pointer text thay cho toàn bộ nội dung PSD.
6. Khi commit, Git lưu pointer dưới dạng Git blob.

### Luồng khi checkout

Khi một thành viên clone hoặc checkout commit có pointer:

1. Git đọc pointer blob từ Git object database.
2. Git gọi LFS smudge/process filter theo thuộc tính.
3. Git LFS tra OID trong kho object local.
4. Nếu object chưa có, Git LFS yêu cầu LFS endpoint tải object.
5. Git LFS xác minh nội dung theo OID/kích thước và ghi tệp thực tế vào working tree.

Nếu bỏ qua smudge hoặc chưa tải được LFS object, working tree có thể hiển thị pointer text thay vì nội dung gốc. Đây không có nghĩa pointer bị hỏng; nó cho biết nội dung LFS chưa được materialize vào thư mục làm việc.

## 6. Quy trình làm việc với Git LFS

### Bước 1: Cài Git LFS

Cài Git LFS theo hệ điều hành hoặc package manager, sau đó khởi tạo cấu hình:

~~~bash
git lfs install
git lfs version
~~~

git lfs install cấu hình filter và hook cần thiết trong phạm vi cấu hình Git tương ứng. Nếu chỉ muốn thiết lập cho repository hiện tại:

~~~bash
git lfs install --local
~~~

Mỗi thành viên và môi trường CI cần có Git LFS nếu muốn tự động chuyển pointer thành nội dung tệp hoặc upload/download object.

### Bước 2: Khai báo pattern trong .gitattributes

~~~bash
git lfs track "*.psd"
git lfs track "*.mp4"
git diff -- .gitattributes
git add .gitattributes
~~~

Commit .gitattributes để quy tắc được chia sẻ với cả nhóm.

### Bước 3: Thêm tệp lớn

~~~bash
git add assets/design.psd assets/product-demo.mp4
git status
git lfs ls-files
~~~

git lfs ls-files liệt kê các tệp được Git LFS quản lý trong phạm vi ref/index mà lệnh kiểm tra. Kiểm tra pointer trong commit sau khi commit:

~~~bash
git commit -m "Add design assets with Git LFS"
git show HEAD:assets/design.psd
~~~

Lệnh git show ở đây hiển thị pointer, không phải dữ liệu PSD.

### Bước 4: Push lên remote

~~~bash
git push origin main
~~~

Với hook pre-push do git lfs install thiết lập, Git LFS upload các object cần thiết cho ref được push trước khi Git cập nhật branch trên remote. Sau đó Git push commit và pointer như bình thường.

Nếu hook bị bỏ qua hoặc không được cài, remote có thể nhận commit chứa pointer nhưng thiếu LFS object tương ứng. Người khác sẽ thấy pointer nhưng không tải được nội dung tệp. Trong quy trình đặc biệt, có thể upload rõ ràng:

~~~bash
git lfs push origin main
~~~

Không nên tắt hook pre-push trong quy trình thông thường.

### Bước 5: Clone và tải nội dung trên máy khác

Máy nhận cần cài Git LFS trước khi clone:

~~~bash
git lfs install
git clone https://example.com/team/large-app.git
~~~

Trong quá trình checkout, smudge filter sẽ tải các LFS object cần thiết và thay pointer bằng nội dung thật. Nếu muốn clone repository nhưng tạm bỏ qua tải nội dung LFS:

~~~bash
GIT_LFS_SKIP_SMUDGE=1 git clone https://example.com/team/large-app.git
~~~

Trong PowerShell, có thể đặt biến môi trường cho một phiên:

~~~powershell
$env:GIT_LFS_SKIP_SMUDGE = "1"
git clone https://example.com/team/large-app.git
Remove-Item Env:GIT_LFS_SKIP_SMUDGE
Set-Location large-app
git lfs pull
~~~

## 7. Phân biệt fetch, pull, checkout và push của LFS

Git LFS có các lệnh riêng để quản lý nội dung:

| Lệnh | Tác dụng |
| --- | --- |
| git lfs fetch origin main | Tải LFS object cần thiết cho ref được chỉ định về cache local, không tự cập nhật working tree |
| git lfs checkout | Ghi các LFS object đã có trong cache vào working tree cho những pointer phù hợp |
| git lfs pull origin main | Fetch LFS object cho ref rồi checkout nội dung vào working tree |
| git lfs push origin main | Upload các LFS object cần thiết cho ref lên LFS server |
| git lfs ls-files | Liệt kê các đường dẫn được quản lý bằng LFS |
| git lfs env | Hiển thị phiên bản, thư mục lưu trữ và endpoint LFS |

git fetch của Git lấy commit/tree/blob Git thông thường và cập nhật remote-tracking refs; nó không đồng nghĩa với git lfs fetch. Tương tự, git pull tích hợp lịch sử Git nhưng nội dung LFS được xử lý bởi filter hoặc lệnh LFS tương ứng.

Nếu muốn chuẩn bị nội dung LFS trước khi ngắt mạng, có thể fetch object cho nhánh cần làm việc:

~~~bash
git lfs fetch origin main
git lfs checkout
~~~

## 8. Điều gì xảy ra khi tệp đã được commit trước khi track LFS?

git lfs track chỉ thêm quy tắc cho các lần Git xử lý tệp tiếp theo. Nếu tệp lớn đã được commit trước đó như Git blob thông thường, việc thêm pattern không tự chuyển toàn bộ lịch sử cũ thành pointer.

Để chuyển phiên bản hiện tại sang LFS, sau khi thêm pattern, có thể stage lại tệp để clean filter chạy:

~~~bash
git lfs track "*.psd"
git add .gitattributes
git add --renormalize assets/design.psd
git status
~~~

Lệnh này giúp phiên bản được stage tiếp theo dùng pointer LFS. Tuy nhiên, các commit cũ vẫn chứa blob lớn trong lịch sử Git.

Nếu muốn loại các tệp đó khỏi lịch sử cũ và chuyển lịch sử sang LFS, cần dùng công cụ migration:

~~~bash
git lfs migrate info --everything
git lfs migrate import --include="*.psd,*.mp4" --everything
~~~

git lfs migrate import viết lại commit history để thay các blob phù hợp bằng pointer LFS. Hash commit thay đổi, vì vậy thao tác này ảnh hưởng đến mọi người đang dùng lịch sử cũ. Chỉ thực hiện khi nhóm thống nhất kế hoạch, đã sao lưu và có lịch phối hợp force-push/cập nhật lại các bản clone. Không chạy migration tùy tiện trên branch dùng chung hoặc repository đã phát hành.

## 9. Bảo mật, quyền truy cập và dung lượng

LFS object có thể chứa dữ liệu lớn hoặc nhạy cảm như video nội bộ, thiết kế sản phẩm hay bộ dữ liệu. Quyền truy cập LFS thường được xác thực qua dịch vụ Git/LFS endpoint; người dùng cần có quyền đọc/ghi object tương ứng.

Một số giới hạn cần kiểm tra:

- Dung lượng tối đa cho mỗi LFS object.
- Quota lưu trữ LFS và băng thông tải xuống.
- Quyền upload/download theo repository hoặc nhóm.
- Chính sách retention, backup và xóa object trên server.
- Khả năng hỗ trợ Git LFS của nhà cung cấp hoặc máy chủ tự quản lý.

Xóa pointer khỏi branch hoặc xóa một tag không nhất thiết lập tức xóa LFS object trên server. Object có thể còn được tham chiếu bởi commit khác, branch khác hoặc được giữ theo chính sách lưu trữ. Không tự xóa trực tiếp dữ liệu trong LFS storage.

## 10. Lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Checkout hiển thị vài dòng pointer thay vì tệp thật | Smudge bị bỏ qua, Git LFS chưa cài hoặc object chưa tải | Chạy git lfs install, kiểm tra cấu hình và git lfs pull |
| Push Git thành công nhưng người khác không tải được tệp | LFS object chưa được upload hoặc pre-push hook không chạy | Chạy git lfs push origin <branch> và kiểm tra hook/quyền |
| git add lưu cả tệp lớn thành Git blob | Pattern chưa khớp hoặc .gitattributes chưa có hiệu lực khi stage | Kiểm tra git check-attr, track pattern rồi stage lại |
| Clone báo lỗi xác thực LFS | Tài khoản không có quyền LFS hoặc credential không hợp lệ | Kiểm tra quyền repository, credential helper và endpoint |
| LFS download bị từ chối hoặc hết quota | Hạn mức hoặc chính sách server | Kiểm tra quota, kích thước object và quyền truy cập |
| Máy mới chỉ có pointer | Git LFS chưa được cài hoặc đã skip smudge | Cài Git LFS rồi chạy git lfs pull |
| Repository vẫn rất lớn sau khi bật LFS | Lịch sử cũ còn Git blob lớn | Xem git lfs migrate info; lên kế hoạch migrate nếu cần viết lại lịch sử |

Các lệnh hữu ích khi kiểm tra:

~~~bash
git lfs version
git lfs env
git lfs ls-files
git check-attr filter diff merge text -- path/to/large-file
git status
~~~

## 11. Quy trình tổng thể

~~~mermaid
flowchart TD
    A[Chọn loại tệp lớn cần quản lý] --> B[Cài Git LFS]
    B --> C[git lfs track pattern]
    C --> D[Commit .gitattributes]
    D --> E[git add tệp lớn]
    E --> F[Clean filter tạo LFS object và pointer]
    F --> G[Commit pointer vào Git]
    G --> H[Pre-push upload LFS object]
    H --> I[Push commit và refs Git]
    I --> J[Máy khác clone/fetch pointer]
    J --> K[Smudge hoặc git lfs pull tải nội dung]
    K --> L[Working tree có tệp thực tế]
~~~

Trước khi đưa Git LFS vào dự án, hãy tự xác nhận:

1. Loại tệp và pattern đã chọn có đúng với dữ liệu cần quản lý không?
2. .gitattributes đã được commit và git check-attr trả về đúng thuộc tính chưa?
3. git lfs install đã được thực hiện trên máy phát triển và CI chưa?
4. Pointer có OID và size hợp lệ, còn nội dung thật đã có trong LFS object store chưa?
5. Pre-push hook có upload object trước khi branch được cập nhật trên remote không?
6. Máy nhận có thể xác thực và tải LFS object không?
7. Nếu tệp đã tồn tại trong lịch sử Git, nhóm đã quyết định có cần migration hay không?

Git LFS tách pointer khỏi nội dung nhị phân lớn để lịch sử Git nhẹ hơn và việc đồng bộ có thể linh hoạt hơn. .gitattributes xác định đường dẫn nào dùng LFS; clean filter biến nội dung thành pointer khi stage; smudge filter khôi phục nội dung khi checkout; LFS object storage giữ dữ liệu thực tế và cung cấp nó qua endpoint. Khi hiểu rõ từng lớp, bạn có thể chẩn đoán chính xác lỗi pointer, upload, download và quản lý tệp lớn trong quy trình cộng tác.

## Tài liệu tham khảo

- [Git LFS documentation](https://git-lfs.com/) — tổng quan Git Large File Storage.
- [Git LFS specification](https://github.com/git-lfs/git-lfs/blob/main/docs/spec.md) — cấu trúc pointer file và giao thức LFS.
- [Git LFS command reference](https://github.com/git-lfs/git-lfs/tree/main/docs/man) — các lệnh track, fetch, pull, push, migrate và env.
- [Git documentation: gitattributes](https://git-scm.com/docs/gitattributes) — cơ chế filter, diff, merge và thuộc tính theo đường dẫn.
