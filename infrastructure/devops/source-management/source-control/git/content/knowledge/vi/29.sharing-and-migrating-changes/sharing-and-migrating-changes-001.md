# Xuất mã nguồn tại một mốc bằng git archive

Khi cần gửi mã nguồn cho người kiểm thử, tạo gói phát hành, cung cấp ví dụ cho đối tác hoặc lưu một snapshot để build, bạn có thể muốn xuất đúng nội dung của một commit mà không gửi toàn bộ lịch sử Git. Lệnh git archive tạo một gói từ cây tệp của một mốc Git như commit, branch hoặc tag.

Khác với clone hoặc bundle, archive chỉ chứa các tệp thuộc snapshot được chọn và không chứa lịch sử commit hay thư mục metadata .git. Vì vậy, đây là cách phù hợp để tạo gói source code tại một phiên bản cụ thể, nhưng không phải phương pháp sao lưu toàn bộ repository.

Bài học này trình bày cách chọn mốc xuất, tạo ZIP hoặc TAR, đặt thư mục gốc bằng prefix, giới hạn đường dẫn, điều khiển nội dung bằng .gitattributes và kiểm tra các giới hạn với thay đổi chưa commit, submodule và Git LFS.

## 1. git archive dùng để làm gì?

### 1.1. Xuất một snapshot của cây Git

Cú pháp cơ bản:

~~~bash
git archive <tree-ish>
~~~

Trong đó tree-ish là một tham chiếu hoặc biểu thức Git có thể phân giải thành cây thư mục, thường là:

- HEAD: commit hiện tại.
- Tên branch: ví dụ main.
- Tag: ví dụ v1.2.0.
- Mã commit: ví dụ 4a1b2c3.
- Remote-tracking branch đã fetch: ví dụ origin/main.

Ví dụ xuất mã nguồn tại tag phát hành:

~~~bash
git archive --format=zip --output=../app-v1.2.0.zip v1.2.0
~~~

Lệnh tạo file ZIP ở thư mục cha của working tree, chứa các tệp được ghi nhận trong cây của tag v1.2.0.

Nếu dùng HEAD, archive phản ánh commit hiện tại của HEAD:

~~~bash
git archive --format=zip --output=../app-current.zip HEAD
~~~

### 1.2. Archive không phải bản sao của working tree

git archive xuất nội dung từ cây Git của tree-ish đã chọn. Nó không lấy toàn bộ những gì đang có trên đĩa.

Vì vậy, archive thông thường:

- Bao gồm tệp được theo dõi và đã có trong commit được chọn.
- Không bao gồm thay đổi chỉ mới stage nhưng chưa commit.
- Không bao gồm thay đổi chưa stage trong working tree.
- Không bao gồm tệp untracked.
- Không bao gồm thư mục .git, lịch sử commit hoặc cấu hình local.

Ví dụ, nếu bạn sửa README.md nhưng chưa commit, lệnh archive HEAD vẫn xuất phiên bản README.md trong commit HEAD. Nội dung đang sửa trên đĩa không được đưa vào gói.

Kiểm tra trạng thái trước khi xuất:

~~~bash
git status --short --branch
git log -1 --oneline --decorate
~~~

Nếu mục tiêu là xuất một commit đã được review hoặc phát hành, hãy chọn đúng tag hoặc commit thay vì vô tình dùng HEAD đang trỏ đến một nhánh phát triển.

### 1.3. Khi nào nên dùng git archive?

Các tình huống phù hợp:

- Tạo gói source code cho một bản phát hành.
- Gửi snapshot cho người kiểm thử hoặc đối tác.
- Cung cấp mã nguồn ví dụ mà không chia sẻ lịch sử nội bộ.
- Tạo source package cho quy trình build.
- Xuất một thư mục con của monorepo.
- Lưu nội dung của một tag để đối chiếu về sau.

Nếu người nhận cần tiếp tục phát triển với lịch sử commit, branch và remote, hãy dùng clone hoặc bundle thay vì archive.

## 2. Chọn đúng mốc cần xuất

### 2.1. Xuất từ HEAD

~~~bash
git archive --format=zip --output=../source-head.zip HEAD
~~~

Dùng khi muốn xuất snapshot của commit hiện tại. Trước khi chạy, kiểm tra branch và commit:

~~~bash
git branch --show-current
git log -1 --format="%H %s"
~~~

Lệnh archive không thay đổi branch, index hoặc working tree.

### 2.2. Xuất từ branch

~~~bash
git archive --format=zip --output=../source-main.zip main
~~~

Branch là tham chiếu có thể di chuyển. Nếu main tiến lên commit mới sau này, chạy lại lệnh có thể tạo archive khác.

Để ghi nhận chính xác mốc đã xuất, lưu lại mã commit:

~~~bash
git rev-parse main
~~~

Trong tài liệu phát hành, nên ghi cả tên tag/branch và commit ID thực tế.

### 2.3. Xuất từ tag phát hành

~~~bash
git archive --format=zip --output=../app-v2.1.0.zip v2.1.0
~~~

Tag thường được dùng để đánh dấu phiên bản phát hành. Với annotated tag, Git phân giải tag đến đối tượng được gắn nhãn và lấy cây của commit tương ứng.

Kiểm tra tag trỏ đến commit nào:

~~~bash
git show -s --format=fuller v2.1.0
git rev-parse 'v2.1.0^{commit}'
~~~

Tag có thể bị di chuyển hoặc tạo lại nếu người có quyền thay đổi ref. Với quy trình phát hành cần kiểm soát chặt, hãy lưu commit ID và xác minh tag theo chính sách ký/xác thực tag của nhóm.

### 2.4. Xuất từ remote-tracking branch

Muốn xuất snapshot mới nhất mà bạn đã fetch từ remote:

~~~bash
git fetch origin
git archive --format=zip --output=../app-origin-main.zip origin/main
~~~

origin/main là remote-tracking branch local. Nó chỉ phản ánh trạng thái remote ở lần fetch gần nhất; nếu remote đã có commit mới mà bạn chưa fetch, archive sẽ không bao gồm những commit đó.

Không cần checkout branch để archive một tree-ish đã có trong repository.

### 2.5. Xuất từ mã commit cụ thể

~~~bash
git archive --format=zip --output=../app-4a1b2c3.zip 4a1b2c3
~~~

Dùng mã commit khi cần tạo lại một snapshot cụ thể hoặc khi branch đã di chuyển. Với quy trình tự động, lưu mã commit đầy đủ thay vì chỉ lưu tên branch.

Có thể kiểm tra tree mà commit tham chiếu:

~~~bash
git rev-parse '4a1b2c3^{tree}'
~~~

Lệnh in OID của tree tương ứng, giúp xác nhận snapshot được chọn.

## 3. Tạo archive ở định dạng ZIP và TAR

### 3.1. Tạo file ZIP

Cú pháp:

~~~bash
git archive --format=zip --output=../project-v1.0.zip v1.0.0
~~~

ZIP thuận tiện cho người dùng Windows, macOS và Linux vì có nhiều công cụ giải nén hỗ trợ.

Có thể xem các định dạng archive mà Git hiện tại hỗ trợ:

~~~bash
git archive --list
~~~

Nếu ZIP không xuất hiện trong danh sách, kiểm tra bản Git và cách đóng gói đang sử dụng.

### 3.2. Tạo file TAR

~~~bash
git archive --format=tar --output=../project-v1.0.tar v1.0.0
~~~

TAR thường được dùng trong môi trường Unix/Linux, container và pipeline build.

Để tạo TAR nén gzip trong Bash:

~~~bash
git archive --format=tar v1.0.0 | gzip -c > ../project-v1.0.tar.gz
~~~

Git tạo luồng TAR; gzip nén luồng đó. Cách này không yêu cầu Git phải hỗ trợ một format tên tar.gz riêng.

Trên Windows, có thể tạo ZIP trực tiếp hoặc dùng Git Bash/WSL và công cụ gzip nếu quy trình cần TAR.GZ.

### 3.3. Dùng --output để ghi file

Ví dụ:

~~~bash
git archive --format=zip --output=../release.zip v1.2.0
~~~

Nếu không dùng --output, dữ liệu archive được ghi ra standard output:

~~~bash
git archive --format=tar v1.2.0 > ../release.tar
~~~

Chỉ định rõ --format giúp lệnh dễ đọc và không phụ thuộc việc Git suy luận định dạng từ tên file.

### 3.4. Tên file archive nên thể hiện mốc nguồn

Nên đặt tên gói có phiên bản hoặc commit:

~~~text
app-v1.2.0.zip
app-v1.2.0.tar.gz
app-4a1b2c3.zip
~~~

Tránh tên chung chung như latest.zip nếu gói cần lưu trữ lâu dài, vì tên đó không cho biết snapshot nào được đóng gói.

## 4. Đặt thư mục gốc trong archive bằng --prefix

### 4.1. Vì sao cần prefix?

Nếu archive được giải nén vào một thư mục đang chứa nhiều nội dung khác, các tệp ở gốc có thể bị trộn với nội dung hiện có.

Dùng --prefix để đặt toàn bộ đường dẫn bên trong archive dưới một thư mục:

~~~bash
git archive --format=zip --prefix=app-v1.2.0/ --output=../app-v1.2.0.zip v1.2.0
~~~

Khi giải nén, cấu trúc sẽ có dạng:

~~~text
app-v1.2.0/
├── README.md
├── src/
├── docs/
└── pom.xml
~~~

Prefix nên kết thúc bằng dấu / để Git nối nó với các đường dẫn trong cây.

### 4.2. Prefix không đổi tên tệp trong repository

--prefix chỉ thay đổi đường dẫn bên trong archive. Nó không rename file trong working tree, không thay đổi index và không tạo commit.

Có thể dùng tên thư mục có version, tên sản phẩm hoặc mã build để người nhận biết gói thuộc phiên bản nào.

### 4.3. Kết hợp prefix với TAR

~~~bash
git archive --format=tar --prefix=app-v1.2.0/ v1.2.0 | gzip -c > ../app-v1.2.0.tar.gz
~~~

Khi giải nén, các tệp vẫn nằm dưới thư mục app-v1.2.0.

## 5. Chỉ xuất một phần repository bằng pathspec

### 5.1. Xuất một thư mục con

git archive nhận pathspec sau tree-ish. Dùng dấu -- để phân cách revision với các đường dẫn:

~~~bash
git archive --format=zip --output=../docs-v1.2.0.zip v1.2.0 -- docs
~~~

Lệnh chỉ xuất nội dung trong thư mục docs thuộc cây của tag v1.2.0.

### 5.2. Xuất nhiều thư mục

~~~bash
git archive --format=zip --output=../source-subset.zip HEAD -- src docs scripts
~~~

Archive chứa các đường dẫn được chỉ định và các nội dung con tương ứng.

Nếu chỉ định các thư mục con, các tệp ở gốc repository như README.md hoặc LICENSE có thể không được đưa vào. Hãy thêm rõ các đường dẫn cần thiết:

~~~bash
git archive --format=zip --output=../source-package.zip HEAD -- README.md LICENSE src
~~~

### 5.3. Pathspec phải thuộc tree-ish

Archive lấy đường dẫn từ cây commit đã chọn. Một tệp untracked hoặc chỉ mới được tạo trong working tree không xuất hiện chỉ vì bạn ghi đường dẫn đó trong pathspec.

Nếu pathspec không khớp đường dẫn trong tree-ish, Git có thể báo lỗi hoặc không xuất nội dung mong đợi. Kiểm tra đường dẫn ở commit:

~~~bash
git ls-tree -r --name-only v1.2.0
~~~

Không dùng pathspec như một cách để thêm tệp local chưa commit vào archive. Nếu cần đóng gói các file phát sinh ngoài Git, hãy thực hiện bước bổ sung riêng và ghi rõ nguồn của chúng.

## 6. Điều khiển nội dung bằng .gitattributes

Git archive có thể áp dụng một số thuộc tính đặc biệt để quyết định tệp nào được xuất và thay thế placeholder trong nội dung.

### 6.1. Loại tệp khỏi archive bằng export-ignore

Có thể đánh dấu đường dẫn không đưa vào archive bằng thuộc tính export-ignore.

Ví dụ trong .gitattributes:

~~~gitattributes
docs/internal/meeting-notes.md export-ignore
*.map export-ignore
~~~

Khi xuất archive, các đường dẫn khớp quy tắc sẽ bị bỏ qua:

~~~bash
git archive --format=zip --output=../public-source.zip v1.2.0
~~~

Thuộc tính này hữu ích để loại tài liệu nội bộ, file map hoặc tệp chỉ phục vụ phát triển khỏi gói source phân phối.

Cần nhớ:

- export-ignore chỉ tác động đến kết quả archive.
- Tệp vẫn có thể tồn tại trong commit và lịch sử Git.
- Người có quyền truy cập repository vẫn có thể đọc tệp đó.
- Không dùng export-ignore làm biện pháp bảo vệ bí mật hoặc thay thế việc phân quyền repository.

Nếu một tệp chứa password, token hoặc private key, không commit nó. Nếu đã commit, phải xử lý như sự cố lộ bí mật.

### 6.2. Thay thế thông tin commit bằng export-subst

Thuộc tính export-subst cho phép Git thay thế placeholder dạng $Format:...$ trong tệp khi tạo archive.

Ví dụ, thêm vào .gitattributes:

~~~gitattributes
VERSION.txt export-subst
~~~

Nội dung VERSION.txt trong repository:

~~~text
Project build information
Commit: $Format:%H$
Commit date: $Format:%cI$
Subject: $Format:%s$
~~~

Khi archive từ một commit:

~~~bash
git archive --format=zip --output=../project-release.zip v1.2.0
~~~

Git thay các placeholder bằng thông tin của commit được archive. File trong working tree và nội dung khi xem trực tiếp từ commit vẫn giữ placeholder; phép thay thế áp dụng cho bản xuất.

Một số format string hữu ích:

| Placeholder | Nội dung |
| --- | --- |
| %H | Mã commit đầy đủ |
| %h | Mã commit rút gọn |
| %cI | Thời gian committer theo định dạng ISO 8601 nghiêm ngặt |
| %s | Subject của commit |

Không đặt token, password hoặc dữ liệu bí mật trong placeholder. export-subst chỉ là cơ chế thay thế metadata commit, không phải hệ thống quản lý secret.

### 6.3. Dùng thuộc tính trong commit được xuất

Mặc định, Git lấy .gitattributes từ cây được archive. Vì vậy, quy tắc export-ignore và export-subst được version hóa cùng commit.

Điều này giúp cùng một commit có quy tắc xuất ổn định ngay cả khi branch sau đó thay đổi .gitattributes.

### 6.4. --worktree-attributes

Có thể yêu cầu Git dùng .gitattributes từ working tree hiện tại:

~~~bash
git archive --worktree-attributes --format=zip --output=../custom-export.zip HEAD
~~~

Tùy chọn này hữu ích khi cần thử quy tắc export chưa commit. Tuy nhiên, nội dung file trong archive vẫn lấy từ tree-ish đã chọn, còn quyết định thuộc tính có thể lấy từ working tree.

Vì vậy, kết quả có thể không hoàn toàn phản ánh chính sách đã được commit tại mốc đó. Với archive phát hành cần tái lập, nên dùng thuộc tính trong commit thay vì --worktree-attributes, trừ khi có lý do rõ ràng.

## 7. Xuất archive từ remote

### 7.1. Dùng --remote

git archive có thể yêu cầu một remote cung cấp archive trực tiếp:

~~~bash
git archive --remote=ssh://git@example.com/team/project.git --format=tar v1.2.0
~~~

Lệnh này yêu cầu máy chủ hỗ trợ dịch vụ git-upload-archive. Không phải mọi Git hosting provider đều bật hoặc cho phép dịch vụ này.

Nếu server không hỗ trợ, lệnh có thể báo không hỗ trợ upload-archive hoặc không mở được dịch vụ. Khi đó, fetch/clone repository về local rồi dùng git archive trên ref đã tải là cách thay thế phổ biến.

### 7.2. Chỉ định chương trình phía server bằng --exec

Trong một số môi trường, đường dẫn chương trình upload-archive phía server không nằm ở vị trí mặc định. Có thể chỉ định bằng --exec:

~~~bash
git archive --remote=ssh://git@example.com/team/project.git --exec=git-upload-archive --format=tar v1.2.0
~~~

Chỉ dùng khi quản trị viên hoặc tài liệu của server cung cấp chính xác đường dẫn/chương trình cần thiết. Tùy chọn này không tự bật dịch vụ trên máy chủ.

### 7.3. Remote archive không phải remote name

Giá trị của --remote là địa chỉ repository phía server, không đơn thuần là tên remote đã khai báo như origin. Ví dụ:

~~~bash
git archive --remote=origin v1.2.0
~~~

không phải cách dùng phổ quát để yêu cầu archive từ remote tên origin. Hãy truyền URL hoặc địa chỉ repository mà dịch vụ upload-archive chấp nhận.

Với workflow thông thường, cách dễ kiểm soát hơn là:

~~~bash
git fetch origin --tags
git archive --format=zip --output=../app-v1.2.0.zip v1.2.0
~~~

Archive được tạo từ ref local đã fetch và bạn có thể kiểm tra commit ID trước khi xuất.

## 8. Kiểm tra archive sau khi tạo

### 8.1. Kiểm tra file có tồn tại và kích thước hợp lý

Sau khi lệnh chạy thành công, xác nhận file đầu ra được tạo. Không nên chỉ dựa vào thông báo của script bao quanh lệnh.

Trên PowerShell:

~~~powershell
Get-Item ..\app-v1.2.0.zip | Select-Object Name, Length, LastWriteTime
~~~

Trên Bash:

~~~bash
ls -lh ../app-v1.2.0.zip
~~~

Nếu file có kích thước 0 byte hoặc nhỏ bất thường, kiểm tra ref, pathspec, định dạng và quyền ghi.

### 8.2. Liệt kê nội dung ZIP

Dùng unzip:

~~~bash
unzip -l ../app-v1.2.0.zip
~~~

Hoặc công cụ 7-Zip:

~~~bash
7z l ../app-v1.2.0.zip
~~~

Kiểm tra các điểm:

- Có đúng thư mục gốc/prefix không.
- Có README, LICENSE và các file build cần thiết không.
- Có tệp nội bộ cần loại trừ không.
- Có đủ source code và tài nguyên cần phân phối không.

### 8.3. Liệt kê nội dung TAR

~~~bash
tar -tf ../app-v1.2.0.tar
~~~

Với TAR.GZ:

~~~bash
tar -tzf ../app-v1.2.0.tar.gz
~~~

Kiểm tra danh sách trước khi giải nén vào vị trí dùng chung hoặc thư mục phát hành.

### 8.4. Tính checksum cho gói xuất

Để người nhận có thể xác nhận file không bị thay đổi trong quá trình truyền:

Trên PowerShell:

~~~powershell
Get-FileHash ..\app-v1.2.0.zip -Algorithm SHA256
~~~

Trên Linux/macOS:

~~~bash
sha256sum ../app-v1.2.0.zip
~~~

Gửi checksum qua kênh phát hành phù hợp. Checksum chỉ xác nhận tính toàn vẹn so với giá trị tham chiếu; nó không chứng minh nguồn gói đáng tin nếu cả gói và checksum đều lấy từ cùng một nguồn bị xâm phạm.

### 8.5. Kiểm tra archive có đúng commit không

Ghi lại commit ID trước khi xuất:

~~~bash
git rev-parse v1.2.0
git rev-parse 'v1.2.0^{tree}'
~~~

Có thể lưu thông tin này trong release note hoặc metadata của artifact. Nếu tag được di chuyển sau đó, commit ID giúp xác định chính xác snapshot đã tạo gói.

## 9. Giới hạn với submodule và Git LFS

### 9.1. git archive không tự đóng gói nội dung submodule

Trong cây Git, submodule được biểu diễn bằng gitlink trỏ đến một commit của repository con. git archive không tự clone hoặc đệ quy xuất nội dung repository submodule.

Nếu dự án phụ thuộc submodule, archive của repository cha có thể thiếu nội dung cần thiết để build. Hãy kiểm tra:

~~~bash
git submodule status
git ls-tree HEAD
~~~

Quy trình đóng gói cần lấy đúng commit submodule được ghi trong cây của repository cha, sau đó tạo archive riêng hoặc checkout nội dung submodule theo commit đó và đặt vào đúng đường dẫn trong gói phát hành.

Không lấy branch mới nhất của submodule một cách tùy tiện; nó có thể khác commit mà repository cha đã ghim.

### 9.2. Git LFS: archive có thể chứa pointer thay vì nội dung lớn

Git lưu pointer file của Git LFS trong cây commit. Vì vậy, git archive thông thường xuất pointer blob được commit, không tự động tải nội dung LFS thật để thay vào archive.

Một pointer có dạng:

~~~text
version https://git-lfs.github.com/spec/v1
oid sha256:...
size ...
~~~

Nếu gói phát hành cần ảnh, video hoặc mô hình nhị phân thật, chỉ chạy git archive có thể tạo gói chứa pointer text.

Có thể kiểm tra pointer trong commit:

~~~bash
git show v1.2.0:assets/scene.fbx
~~~

Nếu đầu ra là pointer, cần một bước đóng gói khác để lấy nội dung thật. Ví dụ:

1. Checkout đúng tag/commit trong một working tree riêng.
2. Chạy git lfs pull để tải object tương ứng.
3. Xác nhận nội dung file là dữ liệu thật.
4. Dùng công cụ đóng gói thư mục working tree đã materialize.

Không giả định git archive chạy smudge filter để tải LFS object. Hãy kiểm tra nội dung artifact cuối cùng trước khi phát hành.

### 9.3. Kiểm tra các thành phần ngoài Git tree

Một gói build hoàn chỉnh có thể cần thêm:

- Nội dung submodule.
- Git LFS object đã checkout.
- File sinh tự động.
- Dependency tải từ package registry.
- Cấu hình môi trường không được commit.

Các thành phần này cần được quản lý bằng quy trình build/package rõ ràng. git archive chỉ xuất cây Git theo mốc đã chọn và các quy tắc archive áp dụng.

## 10. Bảo mật khi xuất mã nguồn

### 10.1. Archive không tự loại bỏ bí mật

Nếu commit chứa file .env, token, private key hoặc mật khẩu, archive có thể chứa chúng trừ khi file bị loại theo export-ignore hoặc pathspec.

Không dựa vào export-ignore để xử lý sự cố secret. Thuộc tính này chỉ tác động đến archive, còn bí mật vẫn nằm trong repository và lịch sử commit.

Trước khi chia sẻ gói:

~~~bash
git status --short
git ls-tree -r --name-only v1.2.0
~~~

Rà soát các đường dẫn và dùng secret scanner phù hợp. Nếu phát hiện credential đã commit, thu hồi hoặc thay mới credential trước khi xử lý lịch sử.

### 10.2. Archive không chứa .git nhưng vẫn có thể lộ dữ liệu

Việc không có .git giúp người nhận không nhận được lịch sử và cấu hình local. Tuy nhiên, nội dung trong cây commit vẫn có thể chứa:

- Source code nội bộ.
- Tài liệu không dành cho bên ngoài.
- File cấu hình có endpoint riêng.
- Chứng thư hoặc khóa bị commit nhầm.
- Dữ liệu mẫu chứa thông tin cá nhân.

Hãy xác định phạm vi đường dẫn được phép phân phối và kiểm tra archive trước khi gửi.

### 10.3. Không dùng archive làm cơ chế xóa dữ liệu lịch sử

Loại file khỏi archive không xóa file khỏi Git. Nếu một file cần bị gỡ khỏi repository, phải xử lý tracked content và nếu cần cả lịch sử bằng quy trình riêng. Nếu file chứa credential, thu hồi credential trước.

## 11. So sánh archive với clone, bundle và checkout

| Cách | Nội dung | Có lịch sử commit? | Mục đích |
| --- | --- | --- | --- |
| git archive | Snapshot của một tree-ish | Không | Gói source tại một mốc |
| git clone | Repository và working tree | Có, tùy clone/filter | Phát triển và cộng tác |
| git bundle | Object và refs được đóng gói | Có trong phạm vi bundle | Chuyển repository/ref khi không dùng remote trực tiếp |
| git checkout/switch | Cập nhật working tree theo ref | Repository vẫn giữ lịch sử local | Chuyển phiên bản để làm việc |

Chọn công cụ theo nhu cầu:

- Người nhận chỉ cần source code của một phiên bản: archive.
- Người nhận cần tiếp tục commit, branch hoặc merge: clone.
- Cần chuyển lịch sử qua file khi không có kết nối remote: bundle.
- Cần thay đổi phiên bản trong repository hiện có: switch/checkout.

Archive thường gọn hơn vì không chứa lịch sử, nhưng không thể dùng như một repository Git đầy đủ để tiếp tục thao tác commit hoặc xem log.

## 12. Ví dụ tổng hợp: tạo gói source cho bản phát hành

Giả sử nhóm chuẩn bị phát hành phiên bản v2.4.0.

### Bước 1 — Fetch tag và xác nhận mốc

~~~bash
git fetch origin --tags
git show -s --format=fuller v2.4.0
git rev-parse 'v2.4.0^{commit}'
~~~

Xác nhận tag trỏ đến commit đã được phê duyệt.

### Bước 2 — Kiểm tra thuộc tính archive

~~~bash
git show v2.4.0:.gitattributes
~~~

Kiểm tra export-ignore và export-subst có đúng chính sách phát hành hay không. Nếu cần, xem file VERSION.txt trong commit:

~~~bash
git show v2.4.0:VERSION.txt
~~~

### Bước 3 — Tạo ZIP với prefix

~~~bash
git archive --format=zip --prefix=product-v2.4.0/ --output=../product-v2.4.0.zip v2.4.0
~~~

### Bước 4 — Kiểm tra nội dung

~~~bash
unzip -l ../product-v2.4.0.zip
~~~

Xác nhận README, LICENSE, source và các tài nguyên cần thiết có trong gói; file nội bộ cần loại bỏ không xuất hiện.

### Bước 5 — Kiểm tra dependency ngoài cây Git

~~~bash
git submodule status
git lfs ls-files
~~~

Nếu dự án có submodule hoặc LFS, thực hiện bước lấy nội dung tương ứng theo commit đã ghim và đóng gói bổ sung. Không phát hành gói chỉ chứa pointer hoặc thư mục submodule rỗng khi ứng dụng cần nội dung thật.

### Bước 6 — Tạo checksum và lưu metadata

Trên PowerShell:

~~~powershell
Get-FileHash ..\product-v2.4.0.zip -Algorithm SHA256
~~~

Ghi lại:

- Tag: v2.4.0.
- Commit ID đầy đủ.
- Tên file archive.
- SHA-256 của archive.
- Phiên bản công cụ đóng gói nếu quy trình yêu cầu.
- Các thành phần submodule/LFS đã được bổ sung.

Sau đó đưa artifact vào nơi lưu trữ phát hành đã được phê duyệt.

## 13. Bảng tra cứu nhanh

| Nhu cầu | Lệnh |
| --- | --- |
| Xuất HEAD thành ZIP | git archive --format=zip --output=../source.zip HEAD |
| Xuất tag thành ZIP | git archive --format=zip --output=../release.zip v1.2.0 |
| Xuất thành TAR | git archive --format=tar --output=../source.tar HEAD |
| Xuất TAR.GZ | git archive --format=tar HEAD, sau đó pipe qua gzip -c > ../source.tar.gz |
| Đặt thư mục gốc trong archive | git archive --format=zip --prefix=app-v1.2.0/ --output=../app.zip v1.2.0 |
| Chỉ xuất thư mục docs | git archive --format=zip --output=../docs.zip HEAD -- docs |
| Xuất nhiều thư mục | git archive --format=zip --output=../subset.zip HEAD -- src docs |
| Liệt kê format hỗ trợ | git archive --list |
| Xem commit của tag | git rev-parse 'v1.2.0^{commit}' |
| Xem tree của tag | git rev-parse 'v1.2.0^{tree}' |
| Xem đường dẫn trong commit | git ls-tree -r --name-only v1.2.0 |
| Kiểm tra archive ZIP | unzip -l ../source.zip |
| Kiểm tra archive TAR | tar -tf ../source.tar |
| Tính SHA-256 trên PowerShell | Get-FileHash ..\source.zip -Algorithm SHA256 |

## 14. Tổng kết

git archive xuất snapshot của một tree-ish thành archive mà không mang theo lịch sử commit hoặc thư mục .git. Chọn đúng HEAD, branch, tag hoặc commit giúp bạn tạo gói source code tại mốc mong muốn. Dùng --format để chọn ZIP/TAR, --output để ghi file, --prefix để tạo thư mục gốc và pathspec để giới hạn phần cây được xuất.

.gitattributes có thể điều khiển archive qua export-ignore và export-subst. --worktree-attributes cho phép thử quy tắc từ working tree, nhưng có thể làm chính sách xuất khác với metadata đã commit. Luôn kiểm tra danh sách file, checksum và các thành phần phụ thuộc trước khi phát hành.

Hãy nhớ archive không chứa thay đổi chưa commit, không tự đệ quy nội dung submodule và thường chứa pointer thay vì nội dung Git LFS thật. Nếu người nhận cần lịch sử Git, dùng clone hoặc bundle. Nếu cần gói source của một phiên bản, git archive là lựa chọn đơn giản và có thể kiểm tra được.

