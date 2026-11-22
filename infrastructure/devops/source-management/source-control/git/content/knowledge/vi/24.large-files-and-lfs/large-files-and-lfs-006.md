# Kiểm tra tệp được theo dõi và trạng thái bằng git lfs ls-files, status

Git LFS (Large File Storage) giúp quản lý các tệp lớn như ảnh thiết kế, video, mô hình 3D, dữ liệu huấn luyện hoặc gói nhị phân. Thay vì lưu toàn bộ nội dung lớn dưới dạng Git blob trong lịch sử repository, Git lưu một tệp pointer nhỏ chứa mã định danh và kích thước; nội dung thật được lưu trong kho đối tượng LFS và trao đổi qua LFS server.

Khi làm việc với Git LFS, bạn cần trả lời được những câu hỏi như: tệp nào đang được quản lý bởi LFS, phiên bản hiện tại đang là pointer hay nội dung đầy đủ, tệp nào đã thay đổi và cần commit, đối tượng nào còn phải upload khi push? Hai lệnh quan trọng để kiểm tra là `git lfs ls-files` và `git lfs status`.

Bài học này tập trung vào cách đọc kết quả của hai lệnh, chọn phạm vi kiểm tra, phân biệt trạng thái LFS với trạng thái Git thông thường và điều tra khi một tệp lớn chưa được tải hoặc chưa được upload.

## 1. Git LFS lưu gì trong repository?

### 1.1. Tệp pointer và nội dung thật

Khi một đường dẫn được Git LFS quản lý, Git thường lưu một pointer file có dạng:

~~~text
version https://git-lfs.github.com/spec/v1
oid sha256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef
size 52428800
~~~

Đây là ví dụ minh họa. Pointer chứa:

- **version:** phiên bản định dạng pointer.
- **oid:** mã SHA-256 định danh nội dung LFS.
- **size:** kích thước nội dung thật tính bằng byte.

Nội dung nhị phân thực tế được lưu trong kho LFS local và đồng bộ với LFS server. Git commit pointer như một blob nhỏ, còn Git LFS chịu trách nhiệm tải và upload nội dung lớn tương ứng.

### 1.2. Clean filter và smudge filter

Git LFS tích hợp với Git thông qua các filter:

- **clean:** khi thêm tệp vào index, filter chuyển nội dung lớn thành pointer để Git lưu trong commit.
- **smudge:** khi checkout, filter đọc pointer và tìm hoặc tải nội dung thật để đưa vào working tree.

Git LFS cũng cài hook `pre-push` để upload các đối tượng LFS cần thiết trước khi Git cập nhật nhánh trên remote. Nếu upload LFS thất bại, thao tác push thường bị dừng để tránh cập nhật commit mà thiếu dữ liệu LFS tương ứng.

Vì vậy, cùng một đường dẫn có thể có các dạng khác nhau tùy vị trí:

| Vị trí | Nội dung thường thấy |
| --- | --- |
| Git commit | Pointer file |
| Git index | Pointer blob được chuẩn bị cho commit |
| Working tree sau checkout thành công | Nội dung tệp thật |
| Working tree khi skip smudge hoặc chưa tải object | Pointer file |

Đây là lý do kiểm tra LFS cần nhìn cả Git và trạng thái đối tượng LFS.

### 1.3. Xác nhận Git LFS đã được cài

Kiểm tra phiên bản:

~~~bash
git lfs version
~~~

Xem môi trường Git LFS:

~~~bash
git lfs env
~~~

Thiết lập filter và hook cho người dùng hiện tại:

~~~bash
git lfs install
~~~

Thông thường chỉ cần chạy `git lfs install` một lần cho mỗi tài khoản người dùng trên máy. Lệnh thiết lập clean/smudge filter và cài hook pre-push cho repository hiện tại nếu được gọi bên trong repository.

Nếu repository dùng `core.hooksPath` hoặc hook tùy chỉnh, hãy kiểm tra cấu hình để bảo đảm hook Git LFS được tích hợp mà không ghi đè hook khác. Không nên xóa hook hiện có chỉ để làm cho LFS hoạt động.

## 2. Xác định đường dẫn nào được cấu hình theo dõi bởi LFS

### 2.1. Xem quy tắc trong .gitattributes

Git LFS dùng thuộc tính Git để xác định đường dẫn nào đi qua filter LFS. Lệnh:

~~~bash
git lfs track
~~~

hiển thị các pattern đang được cấu hình. Ví dụ, nếu repository theo dõi tệp PSD và video:

~~~gitattributes
*.psd filter=lfs diff=lfs merge=lfs -text
*.mp4 filter=lfs diff=lfs merge=lfs -text
~~~

Các quy tắc này thường được ghi trong `.gitattributes` ở gốc repository hoặc thư mục con.

Thêm pattern mới:

~~~bash
git lfs track "*.psd"
git lfs track "*.mp4"
~~~

Sau đó cần commit thay đổi `.gitattributes` cùng các tệp liên quan:

~~~bash
git add .gitattributes
git add design/banner.psd
git commit -m "Track design assets with Git LFS"
~~~

Lệnh `git lfs track` thay đổi quy tắc thuộc tính. Nó không tự chuyển toàn bộ các phiên bản cũ trong lịch sử Git sang LFS.

### 2.2. Kiểm tra thuộc tính của một đường dẫn

Dùng:

~~~bash
git check-attr filter diff merge -- design/banner.psd
~~~

Nếu đường dẫn được cấu hình đúng, kết quả thường cho thấy các thuộc tính `filter`, `diff` và `merge` mang giá trị `lfs`.

Lệnh này kiểm tra quy tắc thuộc tính áp dụng cho đường dẫn. Nó không chứng minh rằng nội dung hiện tại đã được lưu thành pointer LFS trong commit hoặc object đã được upload.

### 2.3. Pattern không đồng nghĩa tệp đã được chuyển đổi

Một tình huống dễ gặp là bạn thêm pattern vào `.gitattributes` sau khi tệp đã được Git theo dõi như blob thông thường. Chỉ thêm quy tắc mới không tự động chuyển blob hiện tại thành pointer.

Với các tệp đã được theo dõi, cần chuẩn hóa lại index theo thuộc tính mới:

~~~bash
git add --renormalize .
git status
git diff --cached
~~~

Sau khi kiểm tra diff, commit việc chuyển đổi. Nếu muốn chuyển cả lịch sử cũ sang LFS, đó là một thao tác migration riêng và có thể viết lại lịch sử repository; không thể giải quyết chỉ bằng `git lfs track` hoặc `git add`.

## 3. Liệt kê tệp LFS bằng git lfs ls-files

### 3.1. Liệt kê tệp LFS trong nhánh hiện tại

Lệnh cơ bản:

~~~bash
git lfs ls-files
~~~

Nếu không truyền revision, Git LFS quét cây của nhánh đang checkout và hiển thị các đường dẫn được lưu dưới dạng LFS trong revision đó.

Ví dụ đầu ra minh họa:

~~~text
3c2f7aedfb * design/banner.psd
a8149c30de - assets/model.bin
~~~

Mỗi dòng thường gồm mã định danh LFS, dấu trạng thái và đường dẫn.

- Dấu `*` sau OID biểu thị full object.
- Dấu `-` biểu thị LFS pointer.

Mặc định OID có thể chỉ hiển thị một phần để dễ đọc. Dùng `--long` nếu cần toàn bộ mã SHA-256.

**Lưu ý:** dấu `*` và `-` là thông tin trạng thái hiển thị của lệnh, không phải phép kiểm tra toàn vẹn mật mã. Cách lệnh xác định nội dung đã được checkout dựa trên trạng thái working tree; trong một số tình huống, dấu này không chứng minh object cache local có đủ nội dung hoặc nội dung có hash đúng. Khi cần xác minh object, dùng `git lfs fsck` và các bước kiểm tra phù hợp.

### 3.2. Hiển thị đầy đủ OID với --long

~~~bash
git lfs ls-files --long
~~~

Mặc định lệnh có thể rút gọn OID để đầu ra ngắn hơn. `--long` hiển thị toàn bộ OID 64 ký tự.

Dùng khi cần:

- Đối chiếu pointer với object trong LFS storage.
- So sánh hai phiên bản tệp lớn.
- Ghi nhận mã định danh trong báo cáo điều tra.
- Xác định chính xác nội dung LFS mà một commit tham chiếu.

OID là mã định danh nội dung, không phải tên phiên bản dễ đọc. Để biết phiên bản thuộc commit nào, hãy kết hợp với `git log`, `git show` hoặc revision cụ thể.

### 3.3. Hiển thị kích thước với --size

~~~bash
git lfs ls-files --size
~~~

Tùy chọn `--size` thêm kích thước object ở cuối dòng. Điều này hữu ích khi kiểm tra repository có đang quản lý đúng các tài sản lớn hay không.

Kích thước trong danh sách là metadata của LFS object. Nó không cho biết object đã upload thành công hay đang nằm trong cache local.

### 3.4. Chỉ hiển thị tên tệp với --name-only

~~~bash
git lfs ls-files --name-only
~~~

Dùng khi bạn chỉ cần danh sách đường dẫn, ví dụ để đối chiếu với quy ước thư mục hoặc kiểm tra phạm vi tài sản.

Tùy chọn này bỏ OID và marker, vì vậy không phù hợp nếu cần xem pointer hay full object.

### 3.5. Xem thông tin debug

~~~bash
git lfs ls-files --debug
~~~

`--debug` hiển thị nhiều thông tin hơn để điều tra thủ công. Định dạng debug có thể thay đổi theo phiên bản Git LFS; không nên dựa vào nó làm giao diện ổn định cho script tự động.

### 3.6. Lọc theo đường dẫn

Có thể chỉ xem những đường dẫn phù hợp với pattern:

~~~bash
git lfs ls-files --include="assets/**"
~~~

Loại trừ một nhóm:

~~~bash
git lfs ls-files --exclude="assets/archive/**"
~~~

Hoặc kết hợp:

~~~bash
git lfs ls-files --include="assets/**" --exclude="assets/archive/**"
~~~

Pattern include/exclude giúp giới hạn danh sách trong repository lớn. Cú pháp pattern tuân theo quy tắc lọc đường dẫn của Git LFS; hãy dùng dấu nháy để shell không tự mở rộng wildcard trước khi Git LFS nhận đối số.

## 4. Kiểm tra lịch sử và tệp đã xóa với ls-files

### 4.1. Liệt kê tệp LFS trong một revision

Có thể truyền tên nhánh, tag hoặc commit:

~~~bash
git lfs ls-files main
git lfs ls-files v2.0.0
git lfs ls-files 4a1b2c3
~~~

Cách này hữu ích khi muốn biết một phiên bản phát hành hoặc nhánh cụ thể đang tham chiếu những LFS object nào.

### 4.2. So sánh hai revision

Cú pháp:

~~~bash
git lfs ls-files <ref-cu> <ref-moi>
~~~

Ví dụ:

~~~bash
git lfs ls-files main feature/new-assets
~~~

Lệnh hiển thị các LFS file có thay đổi giữa hai revision. Các đường dẫn bị xóa không được liệt kê trong chế độ so sánh hai ref này. Nếu cần điều tra file đã xóa, dùng tùy chọn lịch sử như `--all` hoặc `--deleted` theo mục tiêu.

### 4.3. Xem toàn bộ lịch sử với --all

~~~bash
git lfs ls-files --all
~~~

`--all` kiểm tra toàn bộ lịch sử repository thay vì chỉ cây của HEAD hoặc revision đang chỉ định. Kết quả có thể bao gồm phiên bản LFS cũ không còn xuất hiện trong cây hiện tại.

Điều này hữu ích khi:

- Tìm tệp LFS từng được commit rồi xóa.
- Điều tra vì sao repository vẫn có object LFS cũ.
- Kiểm tra lịch sử trước khi migration.
- Tìm phiên bản tài sản được một nhánh hoặc tag cũ tham chiếu.

Repository có lịch sử dài có thể trả về rất nhiều dòng. Hãy kết hợp `--include` hoặc `--exclude` nếu chỉ cần kiểm tra một nhóm đường dẫn.

### 4.4. Bao gồm đối tượng đã xóa với --deleted

~~~bash
git lfs ls-files --deleted main
~~~

Tùy chọn `--deleted` hiển thị lịch sử của revision được chỉ định, bao gồm các object đã bị xóa khỏi cây hiện tại. Dùng khi muốn truy tìm một tài sản không còn trong phiên bản mới nhưng từng được lưu bằng LFS.

Không nhầm `--deleted` với việc khôi phục tệp. Lệnh chỉ liệt kê thông tin lịch sử; để lấy lại nội dung, cần xác định commit hoặc pointer phù hợp rồi checkout/fetch object tương ứng.

## 5. Đọc trạng thái bằng git lfs status

### 5.1. Lệnh này kiểm tra điều gì?

Chạy:

~~~bash
git lfs status
~~~

Lệnh hiển thị trạng thái các LFS object trong working tree. Nó phân loại các đường dẫn theo ba nhóm chính:

1. **Chưa được push lên LFS server:** object có thể được upload khi chạy `git push`.
2. **Khác biệt giữa index và HEAD:** object sẽ được đưa vào commit tiếp theo.
3. **Khác biệt giữa working tree và index:** tệp có thay đổi có thể được stage bằng `git add`.

Lệnh cần chạy trong repository không phải bare repository.

### 5.2. Ví dụ đầu ra

Đầu ra có thể có dạng minh họa:

~~~text
On branch feature/design-refresh

Objects to be pushed to origin/feature/design-refresh:

    design/banner.psd (sha256:...)

Objects to be committed:

    design/banner.psd (sha256:...)

Objects not staged for commit:

    assets/model.bin (sha256:...)
~~~

Tên nhóm và cách trình bày cụ thể có thể khác theo phiên bản Git LFS và trạng thái repository. Ý nghĩa cần tập trung là:

- **Objects to be pushed:** object LFS còn cần gửi lên LFS server theo các commit cần push.
- **Objects to be committed:** thay đổi pointer LFS đã nằm trong index nhưng chưa được ghi thành commit.
- **Objects not staged for commit:** thay đổi LFS trong working tree chưa được đưa vào index.

Nếu một nhóm không có nội dung, Git LFS có thể không hiển thị đường dẫn nào bên dưới nhóm đó.

### 5.3. Phân biệt git status và git lfs status

Hai lệnh bổ sung cho nhau:

| Lệnh | Trọng tâm | Câu hỏi |
| --- | --- | --- |
| `git status` | Trạng thái Git thông thường: branch, staged, unstaged, untracked | Những đường dẫn nào đang thay đổi trong repository? |
| `git lfs status` | Trạng thái LFS object: cần commit, cần stage, cần upload | Những LFS object nào đang chờ ở từng giai đoạn? |

Một tệp LFS có thể xuất hiện trong `git status` như một tệp đã sửa, trong khi `git lfs status` cho biết object tương ứng còn cần upload hay chưa được stage.

Không nên chỉ dùng một trong hai lệnh khi điều tra vấn đề LFS.

### 5.4. Kiểm tra trạng thái theo từng bước

Trước khi commit:

~~~bash
git status
git lfs status
git diff
git diff --cached
~~~

Nếu có thay đổi chưa staging, stage tệp:

~~~bash
git add assets/model.bin
~~~

Kiểm tra lại:

~~~bash
git status
git lfs status
git diff --cached
~~~

Sau khi commit:

~~~bash
git commit -m "Update 3D model asset"
git lfs status
~~~

Sau khi push:

~~~bash
git push origin feature/design-refresh
git lfs status
~~~

Nếu hook pre-push hoạt động, Git LFS upload các object cần thiết trước khi cập nhật nhánh Git trên remote. Sau khi push thành công, nhóm object cần upload thường không còn xuất hiện. Tuy nhiên, `git lfs status` không thay thế xác nhận phía server hoặc kiểm tra tính toàn vẹn object.

## 6. Dùng output có cấu trúc cho script

### 6.1. Porcelain output

`git lfs status` hỗ trợ:

~~~bash
git lfs status --porcelain
~~~

Tùy chọn này tạo đầu ra dễ phân tích hơn trong script so với dạng trình bày cho người dùng. Nếu viết automation, hãy kiểm tra định dạng theo phiên bản Git LFS mà hệ thống hỗ trợ và không phân tích output thông thường bằng cách tách chuỗi tùy tiện.

### 6.2. JSON output

Có thể yêu cầu JSON:

~~~bash
git lfs status --json
~~~

JSON phù hợp khi một công cụ khác cần đọc trạng thái theo cấu trúc. Nếu đồng thời dùng `--porcelain`, chế độ porcelain được ưu tiên.

Với `git lfs ls-files`, có thể dùng:

~~~bash
git lfs ls-files --json
~~~

Nếu dùng `--debug` cùng `--json`, tùy chọn debug có mức ưu tiên theo tài liệu lệnh. Khi dùng JSON cho script, nên kiểm tra schema theo phiên bản cài đặt và xử lý trường hợp lệnh thất bại hoặc repository không có tệp LFS.

Không nên coi JSON là bằng chứng rằng object đã được upload hoặc kiểm tra hash thành công; nó chỉ là cách biểu diễn thông tin mà lệnh thu thập được.

## 7. Phân biệt trạng thái được liệt kê với tính toàn vẹn object

### 7.1. ls-files không phải lệnh kiểm tra checksum

`git lfs ls-files` giúp xác định đường dẫn LFS, OID, kích thước và marker full object/pointer. Nó không thay thế việc xác minh nội dung object.

Đặc biệt, marker `*` không nên được diễn giải như một cam kết rằng object trong cache local chắc chắn tồn tại và có nội dung đúng SHA-256. Marker chủ yếu phản ánh cách Git LFS nhận diện tệp đã được checkout trong working tree; trong một số tình huống skip smudge hoặc cache, cách hiển thị có thể không phản ánh đầy đủ trạng thái object storage.

### 7.2. Dùng fsck để kiểm tra

Kiểm tra LFS object trong HEAD:

~~~bash
git lfs fsck
~~~

Kiểm tra object được tham chiếu và sự tồn tại trên đĩa:

~~~bash
git lfs fsck --objects
~~~

Kiểm tra tính chuẩn của pointer và việc các tệp phù hợp thuộc tính LFS có được lưu đúng dạng pointer:

~~~bash
git lfs fsck --pointers
~~~

Có thể chỉ định revision hoặc khoảng commit:

~~~bash
git lfs fsck --pointers main..HEAD
~~~

`git lfs fsck` kiểm tra tính nhất quán của object/pointer trong phạm vi được chỉ định. Khi phát hiện object bị hỏng, Git LFS có thể di chuyển object hỏng vào thư mục `.git/lfs/bad`; hãy đọc trợ giúp và cân nhắc `--dry-run` nếu muốn kiểm tra mà không di chuyển object.

### 7.3. Kiểm tra nội dung pointer trong commit

Có thể xem nội dung Git lưu cho một đường dẫn:

~~~bash
git show HEAD:design/banner.psd
~~~

Nếu tệp được lưu bằng LFS, kết quả thường là pointer text, không phải nội dung PSD thật.

Có thể đối chiếu OID và size của pointer với kết quả `git lfs ls-files --long --size`. Nếu pointer không đúng định dạng hoặc file đáng lẽ dùng LFS nhưng lại được lưu thành blob thông thường, cần xem lại `.gitattributes`, filter và quá trình stage.

## 8. Điều tra khi working tree hiển thị pointer thay vì tệp thật

### 8.1. Nhận diện pointer file

Nếu mở một tệp đáng lẽ là ảnh, video hoặc tài sản lớn nhưng thấy nội dung dạng:

~~~text
version https://git-lfs.github.com/spec/v1
oid sha256:...
size ...
~~~

thì working tree đang chứa pointer thay vì nội dung thật.

Một số nguyên nhân:

- Git LFS chưa được cài hoặc chưa chạy `git lfs install`.
- Clone hoặc checkout được thực hiện với skip smudge.
- LFS object chưa được tải về.
- LFS server không truy cập được hoặc người dùng không có quyền.
- Hook/filter bị cấu hình sai hoặc bị công cụ khác ghi đè.

### 8.2. Kiểm tra cài đặt và trạng thái

~~~bash
git lfs version
git lfs env
git lfs ls-files
git lfs status
git status --short
~~~

Nếu chưa cài filter/hook:

~~~bash
git lfs install
~~~

Tải object và cập nhật working tree cho ref hiện tại:

~~~bash
git lfs pull
~~~

`git lfs pull` thường tương đương fetch object LFS cho ref hiện tại rồi checkout nội dung cần thiết vào working tree. Nó không tạo commit mới.

Nếu object đã được tải nhưng working tree vẫn chứa pointer, có thể checkout lại nội dung LFS:

~~~bash
git lfs checkout
~~~

Trước khi chạy, hãy xác nhận working tree không có thay đổi local cần bảo toàn. Checkout có thể cập nhật nội dung các tệp LFS trong working tree.

### 8.3. Khi clone với skip smudge

Một số môi trường cố ý tắt tải LFS tự động trong lúc clone để tiết kiệm thời gian hoặc bộ nhớ. Ví dụ, biến môi trường `GIT_LFS_SKIP_SMUDGE=1` khiến Git LFS bỏ bước chuyển pointer thành nội dung thật khi checkout.

Sau khi clone, có thể tải nội dung theo nhu cầu:

~~~bash
git lfs pull
~~~

Nếu chỉ cần một số đường dẫn, dùng tùy chọn include/exclude được hỗ trợ bởi lệnh fetch/pull để giới hạn phạm vi. Kiểm tra trợ giúp của phiên bản Git LFS đang cài:

~~~bash
git lfs pull -h
~~~

Không nên nhầm pointer file với tệp bị hỏng. Pointer có thể là trạng thái mong đợi khi smudge bị tắt hoặc object chưa được checkout.

## 9. Điều tra khi LFS object chưa được upload

### 9.1. Xem nhóm Objects to be pushed

Sau khi commit tệp LFS, chạy:

~~~bash
git lfs status
~~~

Nếu tệp còn nằm trong nhóm object cần push, kiểm tra remote và upstream:

~~~bash
git remote -v
git branch -vv
git status -sb
~~~

Xác nhận bạn đang push đúng remote và nhánh. Git remote URL và LFS endpoint có thể được cấu hình khác nhau; kiểm tra môi trường LFS:

~~~bash
git lfs env
~~~

### 9.2. Kiểm tra hook pre-push

Git LFS dùng hook pre-push để upload object trước khi Git cập nhật ref trên remote. Nếu hook bị thiếu, bị ghi đè hoặc bị bỏ qua, commit Git có thể được push mà LFS object chưa được upload.

Kiểm tra đường dẫn hook:

~~~bash
git config --show-origin --get core.hooksPath
~~~

Nếu không có `core.hooksPath`, hook thường nằm trong Git directory của repository. Có thể cài lại hook/filter:

~~~bash
git lfs install
~~~

Nếu repository có hook tùy chỉnh, hãy hợp nhất logic Git LFS với hook hiện có theo hướng dẫn của nhóm; không ghi đè hook đang thực hiện kiểm tra bảo mật hoặc quy trình phát hành.

### 9.3. Push và xác nhận lại

Thực hiện push theo quy trình:

~~~bash
git push origin main
~~~

Sau đó kiểm tra:

~~~bash
git lfs status
git status -sb
~~~

Nếu upload thất bại, đọc thông báo lỗi về xác thực, quota, kích thước, endpoint hoặc mạng. Không chỉ dựa vào việc nhánh Git đã xuất hiện trên remote để kết luận LFS object đã có sẵn.

Có thể dùng `git lfs push --dry-run` để xem các object sẽ được push mà không upload thật:

~~~bash
git lfs push --dry-run origin main
~~~

Dry-run hỗ trợ xem trước phạm vi object, nhưng không xác nhận server sẽ chấp nhận upload khi chạy thật.

## 10. Quy trình kiểm tra LFS trước và sau commit

Giả sử bạn cập nhật `assets/scene.fbx`.

**Bước 1 — Xác nhận đường dẫn được track**

~~~bash
git check-attr filter diff merge -- assets/scene.fbx
git lfs track
~~~

**Bước 2 — Xem danh sách LFS**

~~~bash
git lfs ls-files --long --size
~~~

Xác nhận tệp xuất hiện và OID/kích thước phù hợp.

**Bước 3 — Kiểm tra thay đổi**

~~~bash
git status
git lfs status
git diff
git diff --cached
~~~

**Bước 4 — Stage và xem lại**

~~~bash
git add assets/scene.fbx
git status
git lfs status
git diff --cached
~~~

**Bước 5 — Commit**

~~~bash
git commit -m "Update environment scene"
~~~

**Bước 6 — Kiểm tra object cần upload**

~~~bash
git lfs status
git lfs push --dry-run origin main
~~~

**Bước 7 — Push**

~~~bash
git push origin main
~~~

**Bước 8 — Kiểm tra sau push**

~~~bash
git lfs status
git lfs ls-files --long --size
git status -sb
~~~

Nếu cần kiểm tra tính toàn vẹn object local:

~~~bash
git lfs fsck --objects
~~~

Chuỗi kiểm tra này giúp phân biệt rõ tệp có được cấu hình LFS, pointer đã được commit, object còn cần upload và nội dung local có thể kiểm tra được hay không.

## 11. Bảng tra cứu nhanh

| Nhu cầu | Lệnh |
| --- | --- |
| Xem phiên bản Git LFS | `git lfs version` |
| Xem môi trường LFS | `git lfs env` |
| Liệt kê tệp LFS của nhánh hiện tại | `git lfs ls-files` |
| Hiển thị OID đầy đủ | `git lfs ls-files --long` |
| Hiển thị kích thước | `git lfs ls-files --size` |
| Chỉ hiển thị đường dẫn | `git lfs ls-files --name-only` |
| Xem lịch sử LFS | `git lfs ls-files --all` |
| Xem object đã xóa | `git lfs ls-files --deleted` |
| So sánh hai revision | `git lfs ls-files main feature/assets` |
| Xem trạng thái LFS | `git lfs status` |
| Output dễ phân tích | `git lfs status --porcelain` |
| Output JSON | `git lfs status --json` |
| Kiểm tra thuộc tính tệp | `git check-attr filter diff merge -- path/to/file` |
| Tải LFS object và checkout | `git lfs pull` |
| Checkout object đã tải | `git lfs checkout` |
| Kiểm tra object local | `git lfs fsck --objects` |
| Kiểm tra pointer | `git lfs fsck --pointers` |
| Xem trước object sẽ push | `git lfs push --dry-run origin main` |

## 12. Tổng kết

`git lfs ls-files` trả lời câu hỏi repository đang tham chiếu những tệp LFS nào, OID và kích thước ra sao, có thể mở rộng phạm vi sang revision hoặc lịch sử. `git lfs status` cho biết các object nào còn cần upload, thay đổi nào đã staging để commit và thay đổi nào vẫn nằm trong working tree.

Hai lệnh không thay thế nhau: `ls-files` thiên về liệt kê và tra cứu đường dẫn LFS; `status` thiên về trạng thái thay đổi theo các giai đoạn Git. Kết hợp chúng với `git status`, `git check-attr`, `git lfs pull` và `git lfs fsck` sẽ giúp phân biệt cấu hình track, pointer, nội dung đã checkout, object cần commit và object cần upload.

Khi điều tra, hãy xác định đúng đường dẫn và revision, kiểm tra trạng thái index/working tree, xác nhận object local rồi mới kết luận về việc upload lên server. Nhờ đó, nhóm có thể quản lý tệp lớn có kiểm soát mà vẫn giữ lịch sử Git gọn và dễ cộng tác.

## Tài liệu tham khảo

- [git lfs ls-files — Git LFS reference](https://github.com/git-lfs/git-lfs/blob/main/docs/man/git-lfs-ls-files.adoc)
- [git lfs status — Git LFS reference](https://github.com/git-lfs/git-lfs/blob/main/docs/man/git-lfs-status.adoc)
- [git lfs fsck — Git LFS reference](https://github.com/git-lfs/git-lfs/blob/main/docs/man/git-lfs-fsck.adoc)
- [Git LFS specification](https://github.com/git-lfs/git-lfs/blob/main/docs/spec.md)

