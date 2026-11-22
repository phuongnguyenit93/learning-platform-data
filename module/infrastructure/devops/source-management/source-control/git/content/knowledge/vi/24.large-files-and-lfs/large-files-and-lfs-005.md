# Commit, clone, pull và push khi kho mã dùng LFS

Git Large File Storage (Git LFS) giúp quản lý các file lớn như ảnh thiết kế, video, dữ liệu kiểm thử, mô hình 3D hoặc binary build mà không đưa toàn bộ nội dung của chúng vào lịch sử Git thông thường. Khi dùng LFS, Git vẫn quản lý commit và branch như trước, nhưng file lớn được thay bằng **pointer file** trong Git; nội dung thật được lưu ở LFS server.

Vì vậy, quy trình làm việc có thêm một lớp trao đổi dữ liệu: khi commit, Git ghi pointer; khi clone hoặc pull, Git LFS tải object tương ứng về working tree; khi push, Git LFS upload object trước khi Git cập nhật branch trên remote. Hiểu đúng thứ tự này giúp tránh tình trạng commit đã có nhưng đồng đội không tải được file, hoặc push branch thành công trong khi LFS object chưa được upload.

## 1. Git LFS thay đổi cách lưu file lớn như thế nào?

Với Git thông thường, khi thêm một file binary, Git lưu nội dung file dưới dạng blob trong object database. Các phiên bản file tiếp theo có thể làm repository phình to, đặc biệt với định dạng khó nén hoặc thường xuyên thay đổi như PSD, video, archive và file dữ liệu.

Git LFS thay nội dung file được theo dõi bằng một pointer nhỏ. Pointer chứa thông tin để tìm nội dung thật trên LFS server, thường gồm:

- Phiên bản định dạng pointer.
- SHA-256 object ID của nội dung thật.
- Kích thước nội dung theo byte.

Ví dụ một pointer file:

~~~text
version https://git-lfs.github.com/spec/v1
oid sha256:4cac19622fc3ada9c0fdeadb33f88f367b541f38b891c2a3f6f3f7a1c2b3d4e5
size 84977953
~~~

Hash và kích thước ở trên chỉ là ví dụ minh họa. Git commit pointer này như một file văn bản nhỏ. Nội dung binary 84.977.953 byte được lưu riêng trong LFS storage.

Khi checkout, Git LFS dùng pointer để tải object có đúng OID, sau đó đặt nội dung thật vào working tree. Khi stage lại file, Git LFS clean filter tạo pointer tương ứng để Git commit.

## 2. Git và Git LFS phối hợp với nhau ra sao?

Có thể chia quy trình thành hai lớp:

| Thành phần | Vai trò |
|---|---|
| Git repository | Lưu commit, branch, tag, tree và pointer file |
| Git LFS local client | Áp dụng clean/smudge filter, quản lý cache object và giao tiếp LFS API |
| LFS server | Lưu và cung cấp nội dung file lớn |
| Git remote | Nhận các ref Git như branch và tag |
| Git LFS pre-push hook | Upload LFS object cần thiết trước khi push ref Git |

Sơ đồ đơn giản:

~~~text
Working tree
  file binary thật
       |
       | git add (LFS clean filter)
       v
Git index / commit
  pointer file nhỏ
       |
       | git push
       +--------------------------+
       |                          |
       v                          v
Git remote                    LFS server
  branch/commit                 binary object
       |                          |
       +------------+-------------+
                    |
             Đồng đội clone/pull
                    |
          Git lấy pointer và LFS object
                    |
                    v
          Working tree có binary thật
~~~

Git và Git LFS có endpoint, cơ chế xác thực và dung lượng lưu trữ riêng. Một lần push có thể bao gồm việc upload object lên LFS server rồi mới cập nhật branch trên Git remote.

## 3. Cài đặt và khởi tạo Git LFS

Git LFS là công cụ mở rộng được cài riêng bên cạnh Git. Kiểm tra đã cài chưa:

~~~bash
git lfs version
~~~

Nếu lệnh không tồn tại, hãy cài Git LFS theo hệ điều hành hoặc bộ cài mà tổ chức sử dụng.

Sau khi cài, khởi tạo cấu hình và hook:

~~~bash
git lfs install
~~~

Lệnh này thường cấu hình các filter Git LFS trong cấu hình người dùng và cài hook cần thiết, đặc biệt là pre-push hook. Thông thường chỉ cần chạy một lần cho mỗi tài khoản người dùng trên máy.

Nếu chỉ muốn cấu hình trong repository hiện tại:

~~~bash
git lfs install --local
~~~

Có thể chạy lại lệnh install để đảm bảo cấu hình/hook đã được cài. Kiểm tra thông tin môi trường:

~~~bash
git lfs env
~~~

Kết quả cho biết phiên bản Git LFS, đường dẫn Git, LFS endpoint và một số cấu hình liên quan. Không chia sẻ nguyên văn output nếu nó chứa đường dẫn hoặc thông tin nội bộ nhạy cảm của môi trường.

**Lưu ý:** cài Git LFS không tự động biến mọi file lớn thành LFS. Repository cần quy tắc tracking trong <code>.gitattributes</code>, và file phải được stage qua filter LFS.

## 4. Khai báo loại file cần theo dõi bằng git lfs track

Trong repository, chọn các pattern file cần lưu bằng LFS. Ví dụ theo dõi file Photoshop:

~~~bash
git lfs track "*.psd"
~~~

Theo dõi thêm video và archive:

~~~bash
git lfs track "*.mp4"
git lfs track "*.zip"
~~~

Lệnh <code>git lfs track</code> cập nhật file <code>.gitattributes</code>. Nội dung minh họa:

~~~gitattributes
*.psd filter=lfs diff=lfs merge=lfs -text
*.mp4 filter=lfs diff=lfs merge=lfs -text
*.zip filter=lfs diff=lfs merge=lfs -text
~~~

Các thuộc tính có ý nghĩa:

- <code>filter=lfs</code>: dùng Git LFS clean/smudge filter.
- <code>diff=lfs</code>: dùng cơ chế diff của LFS cho file được theo dõi.
- <code>merge=lfs</code>: khai báo driver merge của LFS.
- <code>-text</code>: không áp dụng chuyển đổi text/line-ending như file văn bản.

Nên dùng <code>git lfs track</code> để cập nhật <code>.gitattributes</code> thay vì tự viết rule thủ công, trừ khi bạn hiểu rõ quy tắc Git attributes.

### Kiểm tra rule có áp dụng cho file không

~~~bash
git check-attr filter diff merge text -- assets/design.psd
~~~

Kết quả mong đợi có <code>filter: lfs</code>, <code>diff: lfs</code>, <code>merge: lfs</code> và <code>text: unset</code>.

Liệt kê file được LFS theo dõi trong repository:

~~~bash
git lfs ls-files
~~~

Lệnh này giúp xác nhận các file đang được Git LFS quản lý. Pattern trong <code>.gitattributes</code> cần được commit cùng thay đổi để các máy khác nhận được quy tắc giống nhau.

## 5. Stage và commit file lớn

Giả sử dự án có file <code>assets/product-model.psd</code>. Sau khi cấu hình pattern, stage cả rule và file:

~~~bash
git add .gitattributes
git add assets/product-model.psd
git status
~~~

Khi <code>git add</code> chạy, Git LFS clean filter đọc nội dung binary và tạo pointer để đưa vào index. File trong working tree vẫn là binary thật để bạn tiếp tục mở bằng ứng dụng thiết kế.

Kiểm tra thay đổi đã stage:

~~~bash
git diff --cached --stat
git diff --cached --summary
git ls-files --stage -- assets/product-model.psd
~~~

Để xem pointer đang nằm trong index:

~~~bash
git show :assets/product-model.psd
~~~

Nếu file đã được commit, xem pointer trong commit:

~~~bash
git show HEAD:assets/product-model.psd
~~~

Kết quả thường là vài dòng pointer chứ không phải nội dung binary. Đây là dấu hiệu bình thường khi file được lưu bằng LFS.

Sau khi kiểm tra:

~~~bash
git commit -m "Add product model asset"
~~~

Commit Git chỉ lưu pointer và thay đổi <code>.gitattributes</code>. LFS object thật có thể đã nằm trong local LFS cache, nhưng chưa chắc đã được upload lên server.

### Vì sao phải commit .gitattributes?

<code>.gitattributes</code> là một phần của repository. Nếu chỉ cấu hình LFS trên máy cá nhân mà không commit file này, các thành viên khác có thể không biết file nào cần được xử lý qua LFS.

Hãy đưa <code>.gitattributes</code> vào cùng commit hoặc một commit cấu hình riêng đã được chia sẻ. Điều này giúp clone, checkout, diff và stage trên các máy khác áp dụng cùng quy tắc.

## 6. Điều gì xảy ra khi clone repository có LFS?

Khi Git LFS đã được cài và cấu hình trước khi clone, Git thường gọi smudge filter trong quá trình checkout. Filter đọc pointer, tải object tương ứng từ LFS server và đặt file thật vào working tree.

Quy trình clone thông thường:

~~~bash
git lfs install
git clone https://example.com/team/design-assets.git
cd design-assets
git lfs ls-files
~~~

Sau khi clone thành công, các file LFS cần thiết cho branch được checkout thường đã có nội dung thật. Kiểm tra bằng cách mở file hoặc xem dung lượng của file trong working tree.

### Nếu clone trước khi cài Git LFS

Nếu Git LFS chưa được cài/cấu hình khi clone, Git có thể checkout pointer dưới dạng file văn bản. Sau khi cài LFS, chạy:

~~~bash
git lfs install
git lfs pull
~~~

<code>git lfs pull</code> lấy các LFS object cần thiết cho ref hiện tại và checkout chúng vào working tree.

Nếu file vẫn là pointer, kiểm tra cấu hình filter, biến môi trường skip-smudge, quyền truy cập LFS endpoint và log của lệnh.

### Bỏ tải LFS object khi clone

Một số môi trường chỉ cần source code để kiểm tra nhanh và chưa cần tải các asset lớn. Có thể bỏ qua smudge khi clone:

~~~bash
GIT_LFS_SKIP_SMUDGE=1 git clone https://example.com/team/design-assets.git
cd design-assets
~~~

Lúc này các file LFS có thể xuất hiện dưới dạng pointer trong working tree. Khi cần nội dung thật:

~~~bash
git lfs pull
~~~

Trong PowerShell, có thể đặt biến môi trường cho phiên terminal hiện tại:

~~~powershell
$env:GIT_LFS_SKIP_SMUDGE = "1"
git clone https://example.com/team/design-assets.git
Remove-Item Env:GIT_LFS_SKIP_SMUDGE
Set-Location design-assets
git lfs pull
~~~

Biến môi trường chỉ bỏ qua bước tải tự động; nó không xóa pointer hoặc object khỏi repository. Hãy nhớ bỏ biến trước các thao tác checkout mà bạn muốn LFS tự tải file.

## 7. Phân biệt git lfs fetch, checkout và pull

Ba lệnh có liên quan nhưng mục tiêu khác nhau:

| Lệnh | Tác dụng |
|---|---|
| <code>git lfs fetch</code> | Tải LFS object vào local cache, không cập nhật file trong working tree |
| <code>git lfs checkout</code> | Điền các object đã có trong cache vào working tree cho file LFS tương ứng |
| <code>git lfs pull</code> | Kết hợp fetch và checkout cho ref hiện tại |

Ví dụ tải object từ remote origin cho branch main:

~~~bash
git lfs fetch origin main
~~~

Sau đó, nếu object đã có trong cache, có thể checkout:

~~~bash
git lfs checkout
~~~

Hoặc thực hiện thao tác thường dùng:

~~~bash
git lfs pull
~~~

<code>git lfs fetch</code> hữu ích khi muốn tải trước object trong một bước riêng, ví dụ chuẩn bị cache cho job build. <code>git lfs pull</code> tiện hơn khi muốn file thật xuất hiện ngay trong working tree.

### Fetch không giống Git fetch

<code>git fetch origin</code> lấy commit, tree, blob Git và cập nhật remote-tracking refs theo cấu hình Git. Nó không có nghĩa là mọi LFS object cần thiết đã được tải vào working tree.

<code>git lfs fetch origin main</code> lấy LFS object cho ref được chỉ định nhưng không tự cập nhật branch Git local. Hai lệnh phục vụ hai lớp dữ liệu khác nhau.

## 8. Pull thay đổi mới từ remote

Khi đồng đội push commit mới có chứa pointer LFS, bạn cần lấy thay đổi Git và object LFS tương ứng.

Quy trình thông thường:

~~~bash
git switch main
git pull --ff-only
git lfs pull
~~~

<code>git pull</code> fetch commit và tích hợp chúng vào branch hiện tại theo cấu hình pull. Trong quá trình checkout/merge, Git LFS có thể tự tải object qua filter và hook nếu được cấu hình. Chạy <code>git lfs pull</code> tường minh giúp bảo đảm các LFS file cần cho ref hiện tại được tải/checkout, đặc biệt khi clone/pull đã bỏ qua smudge hoặc hook không chạy.

Nếu chỉ muốn lấy object trước mà chưa thay đổi working tree:

~~~bash
git lfs fetch origin main
~~~

Sau khi cần sử dụng file:

~~~bash
git lfs checkout
~~~

### Pull khi có thay đổi local

Trước khi pull, kiểm tra:

~~~bash
git status
git lfs status
~~~

Nếu đang sửa file lớn, hãy lưu hoặc commit thay đổi trước. Git LFS quản lý nội dung file qua filter, nhưng xung đột merge của file binary thường không thể tự hòa giải như file văn bản. Nhóm cần quyết định phiên bản nào được giữ hoặc dùng ứng dụng chuyên dụng để hợp nhất nội dung.

## 9. Push branch có chứa file LFS

Khi commit đã chứa pointer LFS, push branch sẽ cần upload các object tương ứng lên LFS server. <code>git lfs install</code> thường cài pre-push hook để thực hiện việc này tự động.

Ví dụ:

~~~bash
git status
git lfs status
git push -u origin feature/design-assets
~~~

Quy trình tổng quát:

1. Git xác định các commit/ref sẽ push.
2. Pre-push hook của Git LFS tìm LFS object được tham chiếu bởi các commit cần gửi.
3. Git LFS upload object còn thiếu lên LFS server.
4. Khi upload thành công, Git tiếp tục cập nhật branch trên Git remote.

Vì vậy, push có thể mất nhiều thời gian hơn nếu có file lớn hoặc nhiều object mới. Trong khi upload, không đóng terminal hoặc ngắt kết nối nếu chưa biết trạng thái đã hoàn tất.

### Kiểm tra trước khi push

~~~bash
git lfs status
git lfs ls-files
git status
~~~

<code>git lfs status</code> hiển thị các LFS object liên quan tới thay đổi local và trạng thái push. Nếu file mong muốn không xuất hiện trong danh sách LFS, kiểm tra <code>.gitattributes</code> và filter trước khi push.

### Upload LFS object thủ công

Nếu pre-push hook không chạy hoặc cần upload object trước, có thể dùng:

~~~bash
git lfs push origin feature/design-assets
~~~

Sau đó push branch Git:

~~~bash
git push origin feature/design-assets
~~~

Lệnh <code>git lfs push</code> upload LFS object được tham chiếu bởi ref chỉ định. Không nhầm nó với <code>git push</code>: lệnh đầu xử lý object LFS, lệnh sau cập nhật branch/tag Git.

Tránh bỏ qua pre-push hook hoặc đặt <code>GIT_LFS_SKIP_PUSH=1</code> trong quy trình thông thường. Nếu Git branch được cập nhật mà object chưa có trên LFS server, người khác sẽ nhận pointer nhưng không tải được nội dung thật.

## 10. LFS server và xác thực

Git remote và LFS endpoint có thể là hai địa chỉ dịch vụ khác nhau. Ví dụ remote dùng SSH để trao đổi Git, trong khi LFS client dùng HTTPS và Batch API để upload/download object.

Kiểm tra endpoint mà Git LFS đang dùng:

~~~bash
git lfs env
git remote -v
~~~

Nếu clone/pull/push báo lỗi xác thực, kiểm tra:

- Tài khoản hoặc token có quyền đọc LFS object không?
- Người push có quyền ghi LFS object không?
- Credential helper có cung cấp thông tin xác thực đúng không?
- LFS endpoint có đúng với repository hoặc tổ chức không?
- Token có hết hạn hoặc thiếu scope không?

Một số nền tảng dùng cùng thông tin xác thực cho Git và LFS, một số cấu hình credential hoặc token riêng. Đừng giả định SSH key dùng để push Git tự động có quyền truy cập LFS endpoint.

Nếu repository dùng endpoint LFS tùy chỉnh qua <code>.lfsconfig</code>, hãy review file này như cấu hình nguồn dữ liệu. Không ghi token, mật khẩu hoặc thông tin bí mật vào <code>.lfsconfig</code> hay commit.

## 11. Làm việc với branch và Pull Request/Merge Request

Trong workflow theo nhánh, mỗi branch có thể thêm hoặc cập nhật LFS object. Ví dụ:

~~~bash
git switch -c feature/new-texture
git lfs track "*.tif"
git add .gitattributes
git add assets/textures/stone.tif
git commit -m "Add stone texture"
git push -u origin feature/new-texture
~~~

Sau đó tạo Pull Request/Merge Request như một thay đổi Git bình thường. Reviewer có thể xem pointer, diff metadata và lịch sử commit; nội dung binary thật cần được xem bằng công cụ phù hợp.

Một số điểm cần lưu ý khi review:

- Kiểm tra <code>.gitattributes</code> có đúng pattern không.
- Kiểm tra file mới thực sự được lưu dưới dạng LFS pointer.
- Xác nhận LFS object đã được upload để CI hoặc reviewer tải được.
- Với file binary, mô tả nội dung, nguồn tạo và cách kiểm thử trong PR/MR.
- Nếu nhiều người cùng sửa một binary, thống nhất người chịu trách nhiệm cập nhật để tránh ghi đè phiên bản.

Khi merge branch, Git tích hợp pointer file và <code>.gitattributes</code>; LFS server đã lưu object theo OID. Các máy clone sau đó tải object theo pointer trong commit mới.

## 12. File LFS có được tải tự động trong CI/CD không?

CI runner cần cả Git LFS client lẫn quyền truy cập LFS server nếu job sử dụng nội dung file lớn.

Một workflow tổng quát:

~~~bash
git lfs install
git clone https://example.com/team/game-assets.git
cd game-assets
git lfs pull
./gradlew test
~~~

Nếu pipeline dùng bước checkout do nền tảng cung cấp, hãy bật tùy chọn hỗ trợ LFS hoặc chạy các lệnh tương ứng sau checkout. Tên tùy chọn phụ thuộc hệ thống CI.

Nếu chỉ build phần code không cần asset lớn, có thể bỏ smudge để tiết kiệm thời gian:

~~~bash
GIT_LFS_SKIP_SMUDGE=1 git clone https://example.com/team/app.git
~~~

Sau đó chỉ tải file cần thiết khi job thực sự sử dụng chúng. Tuy nhiên, các test hoặc build cần binary sẽ thất bại nếu chưa gọi <code>git lfs pull</code> hoặc fetch object phù hợp.

### Cache LFS trong CI

Git LFS lưu object trong local cache. Runner có thể tái sử dụng cache giữa các job nếu nền tảng hỗ trợ và quy trình cache được cấu hình đúng.

Cần bảo đảm:

- Cache được khóa theo repository hoặc LFS object identity phù hợp.
- Job không dùng cache từ nguồn không tin cậy.
- Khi cache miss, runner vẫn có quyền tải object từ LFS server.
- Không coi cache local là bản lưu trữ chính thức của asset.

LFS server vẫn là nguồn lưu trữ được chia sẻ; cache chỉ giúp giảm tải lặp lại.

## 13. Lỗi thường gặp khi clone, pull và push

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra và xử lý |
|---|---|---|
| File trong working tree chỉ hiện vài dòng pointer | Smudge filter bị bỏ qua, Git LFS chưa cài hoặc tải object thất bại | Chạy <code>git lfs version</code>, <code>git lfs env</code>, rồi <code>git lfs pull</code> |
| Clone thành công nhưng mở file LFS báo lỗi | LFS object chưa tải hoặc thiếu quyền truy cập | Kiểm tra endpoint, xác thực và chạy <code>git lfs pull</code> |
| Push branch bị báo thiếu LFS object | Pre-push hook không chạy hoặc object chưa được upload | Kiểm tra <code>git lfs install</code>, <code>git lfs status</code>, chạy <code>git lfs push origin &lt;branch&gt;</code> |
| Git báo file lớn vượt giới hạn | File đã được commit như blob Git thông thường | Kiểm tra <code>git check-attr</code>, <code>.gitattributes</code>; nếu đã nằm trong lịch sử, cân nhắc migrate |
| <code>git lfs track</code> đã chạy nhưng file vẫn là blob Git | File chưa được stage lại sau khi thêm rule hoặc pattern không khớp | Dùng <code>git check-attr filter -- &lt;file&gt;</code>, stage lại file và kiểm tra pointer |
| HTTP 401/403 khi tải LFS | Credential thiếu quyền hoặc token hết hạn | Làm mới credential và xác nhận quyền đọc/ghi LFS |
| LFS endpoint trả 404 | Endpoint sai, object chưa upload hoặc server không lưu object | Kiểm tra <code>git lfs env</code>, remote và trạng thái object |
| Pull xong nhưng file chưa đổi từ pointer | Skip-smudge còn bật hoặc checkout filter không hoạt động | Bỏ biến skip-smudge và chạy <code>git lfs pull</code> |
| Push rất lâu | Có nhiều object lớn hoặc băng thông thấp | Kiểm tra <code>git lfs status</code>, kích thước file và giới hạn server |
| Server báo quota hoặc bandwidth exceeded | Hết hạn mức lưu trữ hoặc truyền tải | Kiểm tra quota của dịch vụ và chính sách nhóm |

Khi lỗi xuất hiện, phân biệt lỗi Git ref với lỗi LFS object. Git branch có thể tồn tại bình thường trong khi object LFS tương ứng chưa thể tải.

## 14. File đã commit trước khi bắt đầu dùng LFS

<code>git lfs track</code> chỉ thiết lập quy tắc cho những lần stage/commit tiếp theo. Nó không tự chuyển toàn bộ lịch sử cũ sang LFS.

Nếu một file lớn đã được commit như blob Git thông thường, các commit cũ vẫn giữ blob đó. Để chuyển lịch sử, Git LFS có lệnh migrate:

~~~bash
git lfs migrate import --include="*.psd"
~~~

Thao tác này có thể viết lại lịch sử commit, thay đổi hash của commit và yêu cầu force push. Chỉ thực hiện sau khi:

1. Sao lưu hoặc tạo một bản clone dự phòng.
2. Thống nhất phạm vi file cần migrate.
3. Thông báo cho tất cả người đang dùng repository.
4. Kiểm tra kết quả trong repository thử nghiệm.
5. Lập kế hoạch để đồng đội clone lại hoặc đồng bộ lịch sử đã viết lại.

Với repository đã chia sẻ rộng rãi, không tự chạy migrate trên branch chính. Nếu chỉ cần bắt đầu quản lý LFS từ phiên bản tiếp theo, có thể thêm rule và commit lại file theo LFS; lịch sử cũ vẫn giữ blob ban đầu.

## 15. Quản lý dung lượng và cache

LFS giảm dung lượng object Git thông thường nhưng không làm mất chi phí lưu trữ. Nội dung thật vẫn chiếm dung lượng trên LFS server và có thể bị tính quota hoặc bandwidth.

Một số nguyên tắc:

- Chỉ đưa vào LFS các file phù hợp: binary lớn, khó diff hoặc thường xuyên thay đổi.
- Tránh track mọi loại file theo một pattern quá rộng nếu repository có nhiều file nhỏ.
- Xóa file khỏi working tree và commit không nhất thiết xóa LFS object khỏi server.
- Xóa branch hoặc tag cũng không có nghĩa object LFS lập tức bị xóa; chính sách garbage collection thuộc server.
- Giữ lại bản sao lưu của asset quan trọng theo chính sách dự án.

Kiểm tra thông tin và file LFS local:

~~~bash
git lfs env
git lfs ls-files
~~~

Dọn object cache không còn cần trong local bằng:

~~~bash
git lfs prune
~~~

<code>git lfs prune</code> chỉ dọn cache LFS local theo quy tắc an toàn của công cụ; nó không xóa object trên LFS server. Tuy vậy, sau khi prune, nếu cần dùng lại file cũ, máy có thể phải tải object từ server. Đảm bảo object quan trọng vẫn có trên server hoặc ở bản sao lưu trước khi dọn cache.

## 16. Kiểm tra tính toàn vẹn của LFS object

Nếu nghi ngờ object bị thiếu hoặc hỏng, có thể kiểm tra:

~~~bash
git lfs fsck
~~~

Lệnh kiểm tra tính nhất quán của các LFS object và pointer liên quan trong repository. Nếu có lỗi, đọc output để xác định pointer hoặc object nào không khớp.

Có thể liệt kê file LFS:

~~~bash
git lfs ls-files
~~~

Đối chiếu OID và kích thước trong pointer với object được lưu local. Không sửa thủ công OID trong pointer để “làm cho hết lỗi”; pointer phải khớp hash nội dung thật.

Nếu object thiếu local nhưng vẫn có trên server, fetch/pull lại. Nếu object không có trên server và không còn trong cache hoặc backup nào, cần tìm bản gốc từ người tạo hoặc nguồn lưu trữ khác.

## 17. Quy trình mẫu từ tạo commit tới đồng đội clone

Giả sử nhóm quản lý file mô hình 3D và texture trong repository <code>game-assets</code>.

### Người tạo thay đổi

~~~bash
git lfs install
git lfs track "*.blend"
git lfs track "*.tif"

git add .gitattributes
git add assets/character.blend assets/texture.tif
git lfs status
git commit -m "Add character model and texture"
git push -u origin feature/character-assets
~~~

Git commit pointer và <code>.gitattributes</code>. Khi push, pre-push hook upload object cần thiết lên LFS server rồi Git cập nhật branch.

### Thành viên khác clone và lấy nội dung

~~~bash
git lfs install
git clone https://example.com/team/game-assets.git
cd game-assets
git lfs ls-files
~~~

Nếu clone đã tải LFS object, file trong working tree có nội dung thật. Nếu clone bỏ qua smudge hoặc object chưa được tải:

~~~bash
git lfs pull
~~~

### Đồng bộ commit mới

Khi có thay đổi mới trên main:

~~~bash
git switch main
git pull --ff-only
git lfs pull
~~~

Kiểm tra file và chạy công cụ build/test cần thiết. Nếu file vẫn là pointer, xem lại cấu hình và quyền LFS.

## 18. Checklist trước khi commit và push

- [ ] Git LFS đã cài và <code>git lfs install</code> đã được chạy.
- [ ] Pattern file cần theo dõi đã có trong <code>.gitattributes</code>.
- [ ] <code>git check-attr filter -- &lt;file&gt;</code> trả về <code>lfs</code>.
- [ ] File đã được stage sau khi thêm rule LFS.
- [ ] <code>git lfs ls-files</code> liệt kê đúng file.
- [ ] Pointer trong index/commit có OID và size hợp lệ.
- [ ] <code>git lfs status</code> không báo thiếu object cần push.
- [ ] Pre-push hook không bị bỏ qua.
- [ ] LFS endpoint có thể truy cập và tài khoản có quyền ghi.
- [ ] CI và đồng đội có quyền tải object sau khi branch được push.
- [ ] File lớn đã commit trước đây có cần migrate lịch sử hay chỉ áp dụng LFS từ commit mới?

## 19. Những điểm cần ghi nhớ

- Git LFS lưu nội dung file lớn trên LFS server; Git commit pointer file nhỏ.
- <code>git lfs track</code> tạo/cập nhật <code>.gitattributes</code>; cần commit file này để chia sẻ quy tắc.
- <code>git add</code> đưa pointer vào index thông qua clean filter; working tree vẫn giữ binary thật.
- <code>git commit</code> lưu pointer, chưa đồng nghĩa object đã được upload.
- <code>git lfs install</code> cấu hình filter và hook; pre-push hook thường upload LFS object trước khi Git cập nhật branch.
- Clone/pull thường tải object qua smudge filter; <code>git lfs pull</code> giúp tải và checkout object cho ref hiện tại.
- <code>git lfs fetch</code> tải object vào cache; <code>git lfs checkout</code> đưa object đã có vào working tree.
- Git fetch/push và LFS fetch/push xử lý hai lớp dữ liệu khác nhau.
- Nếu thấy pointer trong working tree, kiểm tra Git LFS, skip-smudge, endpoint và quyền truy cập.
- <code>git lfs track</code> không chuyển lịch sử cũ; migrate có thể viết lại commit và cần phối hợp.
- LFS vẫn có quota, băng thông và chi phí lưu trữ; cache local không thay thế server hay backup.

Khi làm việc với kho mã dùng LFS, hãy nhớ quy trình có hai phần đi cùng nhau: Git quản lý pointer và lịch sử, còn Git LFS quản lý nội dung file lớn. Commit đúng pointer, upload object khi push và tải object khi clone/pull sẽ giúp mọi thành viên nhận được cùng một phiên bản mã nguồn lẫn tài nguyên.

