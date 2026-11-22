# Cài đặt Git LFS và khai báo mẫu tệp bằng git lfs track

Git lưu lịch sử mã nguồn hiệu quả với các tệp văn bản và nhiều loại tệp thông thường. Tuy nhiên, những tệp nhị phân lớn như video, ảnh thiết kế, bản dựng, mô hình 3D hoặc dữ liệu kiểm thử có thể làm repository tăng nhanh về dung lượng. Mỗi lần nội dung tệp lớn thay đổi, Git thông thường có thể phải lưu thêm một phiên bản blob trong lịch sử.

**Git LFS (Large File Storage)** là phần mở rộng cho Git, giúp quản lý nội dung tệp lớn thông qua các đối tượng lưu trữ LFS. Trong repository Git, tệp lớn được thay bằng một *pointer file* nhỏ chứa mã định danh và kích thước của nội dung thật. Nội dung thật được lưu trên LFS server và được tải khi cần. Để sử dụng, bạn cài Git LFS, khởi tạo tích hợp với Git bằng `git lfs install`, rồi khai báo các mẫu tệp cần quản lý bằng `git lfs track`.

## 1. Git LFS giải quyết vấn đề gì?

Giả sử một dự án có các tệp:

```text
project/
├── src/
├── docs/
└── assets/
    ├── product-demo.mp4
    ├── logo-source.psd
    └── model-final.blend
```

Các tệp video, thiết kế và mô hình có thể có dung lượng lớn, đồng thời thay đổi thường xuyên. Nếu lưu chúng trực tiếp như blob thông thường, repository có thể tăng nhanh và việc clone hoặc fetch lịch sử trở nên tốn thời gian, dung lượng mạng và ổ đĩa.

Git LFS tách phần nội dung lớn ra khỏi object database Git thông thường:

- Git commit lưu pointer file nhỏ thay cho nội dung nhị phân lớn.
- Pointer chứa OID (thường là SHA-256) và kích thước của nội dung thật.
- Git LFS client tải hoặc đẩy nội dung thật đến LFS server theo cơ chế riêng.
- Git vẫn quản lý lịch sử, branch, merge và commit của pointer như các tệp khác.

Git LFS phù hợp với tài sản nhị phân lớn mà nhóm cần quản lý phiên bản cùng mã nguồn. Nó không tự động nén mọi tệp, không làm repository Git biến mất và cũng không thay thế việc chọn lọc dữ liệu cần commit.

## 2. Git LFS hoạt động qua pointer file

Khi một tệp được cấu hình theo dõi bởi LFS và được `git add`, Git LFS clean filter chuyển nội dung tệp thành pointer trong index. Khi checkout, Git LFS smudge filter hoặc cơ chế checkout tương ứng thay pointer bằng nội dung thật nếu đối tượng LFS có thể được tải.

Một pointer file có dạng minh họa:

```text
version https://git-lfs.github.com/spec/v1
oid sha256:4cac196befb372e4a4e1c1f2f9c0c3b5d7e9a1b3c5d7e9f1029384756abcdef0
size 12345678
```

Các trường có ý nghĩa:

| Trường | Ý nghĩa |
|---|---|
| `version` | Phiên bản đặc tả pointer của Git LFS |
| `oid sha256:...` | Mã định danh nội dung LFS dựa trên SHA-256 |
| `size` | Kích thước nội dung thật tính bằng byte |

Khi commit, Git ghi pointer file vào tree. Khi push, Git LFS thường dùng pre-push hook để tải các đối tượng LFS cần thiết lên máy chủ trước hoặc cùng quy trình push ref. Khi clone hoặc checkout, client dùng OID trong pointer để lấy đúng nội dung từ LFS server.

Điều này giúp lịch sử Git chứa metadata nhỏ, còn nội dung lớn được truyền qua dịch vụ LFS. Repository vẫn phụ thuộc vào LFS server để lấy các tệp thật khi cần làm việc với chúng.

## 3. Cài đặt Git LFS trên Windows

Git LFS là chương trình cài riêng, dù máy đã có Git for Windows. Trước tiên, xác minh Git đã hoạt động:

```powershell
git --version
```

### Dùng bộ cài chính thức

1. Mở trang chính thức <https://git-lfs.com/> hoặc trang phát hành <https://github.com/git-lfs/git-lfs/releases>.
2. Tải bộ cài phù hợp với kiến trúc Windows.
3. Chạy bộ cài và hoàn tất hướng dẫn.
4. Đóng rồi mở lại PowerShell, Windows Terminal hoặc Git Bash để nạp PATH mới.

### Xác minh cài đặt

```powershell
git lfs version
where.exe git-lfs
```

Nếu `git lfs version` in ra phiên bản, Git đã tìm thấy chương trình Git LFS. `where.exe git-lfs` giúp xác định executable được gọi qua PATH.

## 4. Cài đặt Git LFS trên macOS

Nếu máy đã cài Homebrew, chạy:

```bash
brew install git-lfs
```

Kiểm tra chương trình:

```bash
git lfs version
command -v git-lfs
```

Nếu chưa dùng Homebrew, có thể tải gói cài đặt phù hợp từ <https://github.com/git-lfs/git-lfs/releases> và làm theo hướng dẫn của bản phát hành. Nếu máy có nhiều bản Git hoặc nhiều nguồn cài LFS, kiểm tra đường dẫn để bảo đảm terminal đang dùng đúng executable.

## 5. Cài đặt Git LFS trên Linux

Nhiều bản phân phối Linux cung cấp package `git-lfs`. Dùng trình quản lý gói phù hợp với hệ thống:

### Ubuntu và Debian

```bash
sudo apt update
sudo apt install git-lfs
```

### Fedora và các bản tương thích dùng DNF

```bash
sudo dnf install git-lfs
```

### Arch Linux

```bash
sudo pacman -S git-lfs
```

### openSUSE

```bash
sudo zypper install git-lfs
```

Nếu package không có trong repository đã cấu hình hoặc phiên bản quá cũ so với yêu cầu dự án, tham khảo hướng dẫn cài đặt và package chính thức tại <https://github.com/git-lfs/git-lfs>. Trên máy công ty, ưu tiên nguồn package được tổ chức phê duyệt.

Xác minh sau khi cài:

```bash
git lfs version
command -v git-lfs
```

## 6. Khởi tạo tích hợp Git LFS bằng git lfs install

Cài executable mới chỉ hoàn thành phần cài đặt. Bạn cần chạy `git lfs install` để cấu hình Git filters và hook cần thiết cho Git LFS.

Thông thường, chạy một lần cho tài khoản người dùng:

```bash
git lfs install
```

Lệnh này thiết lập các filter `lfs` trong cấu hình Git và cài pre-push hook cho repository hiện tại nếu đang chạy bên trong repository. Hook giúp Git LFS đẩy nội dung lớn cần thiết khi bạn push commit chứa pointer.

Nếu chỉ muốn cấu hình cho repository hiện tại:

```bash
git lfs install --local
```

`--local` giới hạn cấu hình Git LFS ở repository hiện tại thay vì thiết lập ở phạm vi người dùng. Điều này hữu ích trên máy dùng chung hoặc khi dự án có yêu cầu cấu hình riêng.

Kiểm tra thông tin môi trường:

```bash
git lfs env
```

Lệnh hiển thị đường dẫn Git, thư mục lưu LFS object, endpoint và một số cấu hình liên quan. Hãy xem output trước khi chia sẻ vì thông tin môi trường có thể tiết lộ đường dẫn nội bộ hoặc URL máy chủ riêng.

## 7. Khai báo mẫu tệp bằng git lfs track

Sau khi Git LFS đã được cài và khởi tạo, đi đến thư mục gốc repository rồi chọn mẫu tệp cần lưu bằng LFS.

Ví dụ, theo dõi mọi tệp Photoshop:

```bash
git lfs track "*.psd"
```

Theo dõi các video trong thư mục `assets/video/`:

```bash
git lfs track "assets/video/*.mp4"
```

Theo dõi một nhóm tệp thiết kế và dữ liệu nén:

```bash
git lfs track "*.blend" "*.zip" "*.7z"
```

`git lfs track` ghi các mẫu vào file `.gitattributes` ở repository. File này cho Git biết những đường dẫn nào dùng filter LFS, diff/merge driver và cách xử lý nội dung. Nó là file cấu hình thuộc repository, nên cần được commit để các thành viên khác nhận cùng quy tắc.

Một `.gitattributes` được tạo có thể chứa các dòng như:

```gitattributes
*.psd filter=lfs diff=lfs merge=lfs -text
*.blend filter=lfs diff=lfs merge=lfs -text
*.zip filter=lfs diff=lfs merge=lfs -text
```

Ý nghĩa các thuộc tính:

- `filter=lfs`: dùng Git LFS clean/smudge filter khi stage và checkout.
- `diff=lfs`: dùng driver diff của Git LFS.
- `merge=lfs`: dùng driver merge của Git LFS theo cấu hình hỗ trợ.
- `-text`: không áp dụng chuyển đổi line ending dạng text cho tệp nhị phân.

Không nên sửa hoặc xóa các thuộc tính này một cách tùy tiện. Nếu chỉnh sửa `.gitattributes` bằng tay, hãy giữ đúng cú pháp và kiểm tra kết quả bằng `git check-attr`.

## 8. Chọn pattern phù hợp

Pattern của `.gitattributes` có cú pháp gần với `.gitignore` nhưng không hoàn toàn giống nhau. Một số nguyên tắc thực tế:

- `*.psd` phù hợp khi muốn áp dụng cho tệp có phần mở rộng `.psd` ở nhiều vị trí trong repository.
- `assets/video/*.mp4` giới hạn vào nhóm video ở đường dẫn đã nêu.
- `models/**` có thể dùng để bao phủ cây thư mục mô hình theo nhu cầu dự án.
- Dùng dấu nháy quanh pattern khi truyền qua shell để tránh shell tự mở rộng ký tự `*` trước khi Git nhận đối số.

Nên theo dõi theo phần mở rộng hoặc thư mục có mục đích rõ ràng. Tránh khai báo pattern quá rộng như `*` hoặc toàn bộ thư mục repository nếu không có chủ đích, vì có thể khiến cả tệp văn bản, cấu hình và script cũng bị đưa vào LFS.

Liệt kê những mẫu LFS đã khai báo:

```bash
git lfs track
```

Lệnh hiển thị các pattern được cấu hình trong `.gitattributes` của repository. Để xem thay đổi do lệnh tạo ra:

```bash
git status --short
git diff -- .gitattributes
```

## 9. Kiểm tra một đường dẫn có được cấu hình dùng LFS không

`git check-attr` cho biết các thuộc tính hiệu lực đối với một đường dẫn. Ví dụ:

```bash
git check-attr filter diff merge text -- assets/design/logo-source.psd
```

Nếu pattern LFS khớp, output thường tương tự:

```text
assets/design/logo-source.psd: filter: lfs
assets/design/logo-source.psd: diff: lfs
assets/design/logo-source.psd: merge: lfs
assets/design/logo-source.psd: text: unset
```

Kết quả cho biết Git sẽ dùng filter LFS cho đường dẫn đó và thuộc tính `text` bị tắt. Nếu `filter` không phải `lfs`, hãy kiểm tra pattern trong `.gitattributes`, vị trí file và quy tắc ở các thư mục cha.

Bạn cũng có thể kiểm tra các tệp đã được ghi nhận bởi LFS:

```bash
git lfs ls-files
```

Lệnh liệt kê những tệp LFS trong trạng thái repository hiện tại cùng OID rút gọn và tên tệp. Nếu chưa có tệp LFS nào được stage hoặc commit, danh sách có thể rỗng dù `.gitattributes` đã có pattern.

## 10. Thêm tệp mới sau khi khai báo track

Quy trình thông thường cho một tệp mới:

```bash
# 1. Khai báo pattern.
git lfs track "*.psd"

# 2. Kiểm tra quy tắc được ghi vào .gitattributes.
git diff -- .gitattributes

# 3. Thêm file cấu hình và tệp lớn.
git add .gitattributes
git add assets/design/logo-source.psd

# 4. Kiểm tra trạng thái và danh sách LFS.
git status
git lfs ls-files

# 5. Commit cả cấu hình lẫn tệp.
git commit -m "chore: track design assets with Git LFS"
```

Nên commit `.gitattributes` cùng thay đổi sử dụng LFS. Nhờ đó, các thành viên khác nhận được quy tắc trước hoặc cùng lúc với tệp lớn và Git có thể áp dụng filter phù hợp khi checkout.

## 11. Nếu tệp đã được Git theo dõi trước khi chạy git lfs track

`git lfs track` tạo hoặc cập nhật quy tắc cho những lần stage tiếp theo. Nó không tự động viết lại toàn bộ lịch sử đã có. Nếu một tệp lớn đã được commit như blob Git thông thường, các commit cũ vẫn giữ blob đó.

Có hai tình huống cần phân biệt:

- **Chỉ muốn các phiên bản thay đổi từ bây giờ dùng LFS:** sau khi khai báo pattern, stage phiên bản mới của tệp theo quy tắc LFS và kiểm tra `git lfs ls-files`. Các phiên bản cũ trong lịch sử vẫn là blob Git thông thường.
- **Muốn chuyển cả lịch sử cũ sang LFS:** cần dùng công cụ migration như `git lfs migrate import`. Đây là thao tác viết lại commit và thay đổi mã commit trong phạm vi được chọn; phải lên kế hoạch, sao lưu và phối hợp với tất cả người dùng repository trước khi thực hiện.

Không nên chạy migration trên repository đã chia sẻ chỉ để thử nghiệm. Nếu mục tiêu là loại bỏ blob lớn khỏi toàn bộ lịch sử, hãy thống nhất branch/ref cần chuyển, cách force-push và hướng dẫn các thành viên clone hoặc đồng bộ lại sau khi lịch sử thay đổi.

## 12. Push và lấy nội dung LFS từ remote

Khi repository đã cấu hình Git LFS, thao tác push branch thường dùng như Git thông thường:

```bash
git push origin feature/design-assets
```

Git LFS pre-push hook tìm các đối tượng LFS cần thiết và tải chúng lên LFS server. Sau đó Git đẩy commit và ref. Remote hosting phải hỗ trợ Git LFS và tài khoản cần có quyền truy cập cả repository lẫn LFS storage.

Khi clone repository có tệp LFS, Git LFS thường tải nội dung thật trong quá trình checkout. Nếu cần lấy nội dung LFS sau khi đã clone hoặc fetch:

```bash
git lfs pull
```

`git lfs fetch` tải LFS objects về local storage nhưng không nhất thiết checkout chúng vào working tree; `git lfs pull` kết hợp fetch và checkout nội dung phù hợp cho ref hiện tại.

Nếu chỉ muốn clone mà chưa tải nội dung LFS ngay, có thể dùng:

```bash
GIT_LFS_SKIP_SMUDGE=1 git clone https://example.com/team/project.git
```

Trên PowerShell, đặt biến môi trường cho một lệnh có cú pháp khác; ví dụ:

```powershell
$env:GIT_LFS_SKIP_SMUDGE = "1"
git clone https://example.com/team/project.git
```

Khi muốn tải nội dung thật sau đó, chạy `git lfs pull`. Cách này hữu ích khi muốn clone nhanh để xem mã nguồn trước, nhưng hãy nhớ các tệp LFS trong working tree có thể vẫn là pointer cho đến khi tải nội dung.

## 13. Những lỗi thường gặp

### Lệnh git lfs không được nhận diện

Nếu `git lfs version` báo không tìm thấy lệnh, Git LFS có thể chưa được cài hoặc executable chưa có trong PATH. Kiểm tra cài đặt theo hệ điều hành, mở terminal mới và chạy lại:

```bash
git lfs version
```

### Đã cài Git LFS nhưng tệp vẫn được commit như blob thông thường

Kiểm tra đã chạy `git lfs install` chưa, pattern có khớp đường dẫn không và `git check-attr filter -- <path>` có trả về `lfs` không. Nếu tệp đã được stage trước khi thêm pattern, hãy stage lại sau khi cấu hình đúng rồi kiểm tra `git lfs ls-files`.

### Tệp không xuất hiện trong git lfs ls-files

`git lfs track` chỉ khai báo pattern; nó không tự thêm tệp vào index. Hãy chạy `git add <path>` sau khi track và kiểm tra trạng thái. Với tệp đã commit trước đó, xác định rõ bạn chỉ cần các phiên bản mới dùng LFS hay cần migration lịch sử.

### Push báo thiếu LFS object hoặc lỗi xác thực

Kiểm tra remote có hỗ trợ LFS, tài khoản có quyền truy cập LFS endpoint và pre-push hook có được cài không. Xem cấu hình bằng:

```bash
git lfs env
git config --show-origin --get-regexp '^lfs\.'
```

Không chia sẻ token, mật khẩu hoặc thông tin xác thực trong output hỗ trợ. Nếu hook bị bỏ qua hoặc không chạy, xử lý nguyên nhân trước khi push lại để bảo đảm pointer trên remote có nội dung tương ứng trên LFS server.

### Clone xong nhưng tệp chỉ chứa pointer text

Điều này có thể xảy ra nếu smudge bị bỏ qua, LFS object chưa tải hoặc client không truy cập được LFS server. Chạy:

```bash
git lfs pull
```

Nếu vẫn lỗi, kiểm tra `git lfs env`, quyền truy cập và kết nối đến LFS endpoint.

## 14. Quy trình thiết lập LFS cho repository mới

Một quy trình ngắn gọn có thể thực hiện như sau:

```bash
# 1. Xác nhận Git và Git LFS đã cài.
git --version
git lfs version

# 2. Khởi tạo tích hợp LFS.
git lfs install

# 3. Vào repository và khai báo mẫu.
git lfs track "*.psd" "*.mp4" "*.blend"

# 4. Kiểm tra .gitattributes.
git diff -- .gitattributes

# 5. Kiểm tra một đường dẫn mẫu.
git check-attr filter diff merge text -- assets/design/logo-source.psd

# 6. Stage cấu hình và tệp lớn.
git add .gitattributes
git add assets/design/logo-source.psd

# 7. Xác minh tệp được nhận diện bởi LFS.
git lfs ls-files

# 8. Commit và push.
git commit -m "chore: configure Git LFS for binary assets"
git push origin main
```

Hãy thay tên branch và đường dẫn bằng cấu trúc thực tế của repository. Trước khi push, xác nhận máy chủ lưu trữ đã bật Git LFS và người dùng có quyền tải lên nội dung LFS.

## 15. Những hiểu nhầm thường gặp

| Hiểu nhầm | Cách hiểu đúng |
|---|---|
| Cài Git là đã có Git LFS | Git LFS là chương trình mở rộng cần được cài và khởi tạo riêng |
| `git lfs track` tải tệp lên server | Lệnh này khai báo pattern trong `.gitattributes`; push mới chuyển LFS objects lên remote |
| `.gitattributes` không cần commit | Đây là cấu hình của repository, cần chia sẻ để mọi thành viên dùng cùng quy tắc |
| Track một phần mở rộng sẽ tự chuyển lịch sử cũ | Các commit cũ không tự thay đổi; migration lịch sử cần thao tác riêng |
| Pointer file là nội dung tệp bị hỏng | Pointer là metadata chuẩn để Git LFS tìm và tải nội dung thật |
| Git LFS làm repository không cần remote | Pointer nằm trong Git nhưng nội dung thật phụ thuộc LFS storage khi cần tải |
| Có thể dùng LFS mà không cần máy chủ hỗ trợ | Remote phải cung cấp endpoint LFS và quyền truy cập tương ứng |

## 16. Ghi nhớ

Để bắt đầu dùng Git LFS, hãy cài chương trình theo hệ điều hành, xác minh bằng `git lfs version`, rồi chạy `git lfs install`. Trong repository, dùng `git lfs track "<pattern>"` để ghi quy tắc vào `.gitattributes`; kiểm tra bằng `git check-attr` và `git lfs ls-files`.

Commit `.gitattributes` cùng các tệp được quản lý bởi LFS để mọi thành viên nhận cùng cấu hình. Khi push, Git LFS chuyển nội dung lớn đến LFS server; khi clone hoặc checkout, client lấy nội dung thật theo pointer. Nếu tệp đã nằm trong lịch sử Git trước khi được track, hãy phân biệt việc chuyển các phiên bản mới với migration toàn bộ lịch sử, vì migration sẽ viết lại commit và cần phối hợp với nhóm.
