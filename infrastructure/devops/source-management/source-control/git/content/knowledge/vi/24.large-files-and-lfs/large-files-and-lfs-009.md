# Lựa chọn LFS, kho artifact hoặc loại tệp khỏi quản lý phiên bản

Không phải mọi file lớn đều nên được commit trực tiếp vào Git. Mã nguồn, cấu hình và tài liệu cần lịch sử thay đổi chi tiết; trong khi file build, gói cài đặt, bản sao lưu hoặc dữ liệu sinh ra có thể tăng kích thước repository nhanh chóng mà không đem lại lợi ích tương xứng khi lưu từng phiên bản trong Git. Với các tài sản nhị phân cần gắn với từng commit, Git LFS là một lựa chọn. Với đầu ra build và gói phát hành, kho artifact thường phù hợp hơn. Với file tạm hoặc dữ liệu có thể tạo lại, loại chúng khỏi quản lý phiên bản bằng `.gitignore` có thể là quyết định đúng.

Lựa chọn cần dựa trên vòng đời và cách nhóm sử dụng file, không chỉ dựa vào kích thước. Một file 20 MB có thể là tài liệu thiết kế quan trọng cần versioning; một thư mục build 2 GB có thể chỉ cần tạo lại từ mã nguồn. Bài học này trình bày tiêu chí lựa chọn giữa Git thông thường, Git LFS, kho artifact và việc bỏ file khỏi Git, đồng thời hướng dẫn quy trình chuyển đổi an toàn.

## 1. Vì sao cần lựa chọn cách lưu file lớn?

Git được tối ưu cho việc lưu và so sánh các phiên bản nội dung. Với file văn bản, Git có thể hiển thị diff theo dòng và thường nén tốt. Với file nhị phân lớn như video, ảnh độ phân giải cao, mô hình 3D, dữ liệu khoa học hoặc gói cài đặt, Git thường không thể tạo diff có ý nghĩa như với mã nguồn. Mỗi lần file thay đổi đáng kể, repository có thể phải lưu thêm một blob lớn.

Hệ quả thường gặp:

- Repository tăng kích thước theo thời gian, kể cả khi file lớn đã bị xóa khỏi working tree hiện tại.
- Clone và fetch có thể chậm vì người dùng phải tải nhiều dữ liệu lịch sử không cần cho công việc hiện tại.
- Các bản sao local, CI runner và mirror cần thêm dung lượng lưu trữ.
- Review pull request khó hiểu nếu thay đổi chỉ là một blob nhị phân không thể đọc diff.
- Việc chia sẻ và backup repository trở nên tốn kém hơn.

Git LFS và kho artifact giải quyết các nhu cầu khác nhau. `.gitignore` chỉ ngăn file chưa được theo dõi đi vào Git; nó không tự di chuyển dữ liệu đã commit ra ngoài repository.

## 2. Bốn lựa chọn lưu trữ chính

| Cách lưu | Phù hợp với | Cách quản lý phiên bản | Ảnh hưởng tới Git repository |
| --- | --- | --- | --- |
| Git thông thường | Mã nguồn, cấu hình, tài liệu văn bản, file nhỏ cần diff | Commit trực tiếp nội dung file | Nội dung được lưu trong object database và lịch sử Git |
| Git LFS | File nhị phân lớn cần gắn chính xác với commit hoặc branch | Git lưu pointer; nội dung file được lưu trên LFS server | Clone Git chủ yếu tải pointer; file LFS được tải theo nhu cầu/cấu hình |
| Kho artifact | Gói build, binary phát hành, dependency nội bộ, container image, kết quả CI | Quản lý theo version, tọa độ, tag, digest hoặc build ID | Git chỉ lưu mã nguồn, manifest hoặc tham chiếu tới artifact |
| Bỏ khỏi quản lý phiên bản | Cache, log, thư mục build, file tạm, dữ liệu local có thể tạo lại | Không version trong Git; có thể tạo lại hoặc lưu ở nơi khác | Không thêm blob mới vào lịch sử Git |

Một dự án có thể phối hợp nhiều cách. Ví dụ, file `.java` lưu trực tiếp trong Git; file thiết kế `.psd` được quản lý bằng LFS; file `.jar` phát hành được đưa vào kho artifact; thư mục `build/` và log local bị loại khỏi Git.

## 3. Cây quyết định chọn nơi lưu

Trước khi thêm file lớn, hãy trả lời lần lượt:

1. File có phải là đầu ra tạm thời, cache hoặc có thể tái tạo từ mã nguồn và cấu hình không? Nếu có, loại khỏi Git.
2. File có phải là gói build, binary phát hành, container image hoặc kết quả pipeline cần phân phối theo version không? Nếu có, ưu tiên kho artifact.
3. File có cần xuất hiện như một phần của snapshot commit để mọi người checkout đúng phiên bản cùng mã nguồn không? Nếu có, cân nhắc Git LFS.
4. File có nhỏ, chủ yếu là văn bản và cần diff/review trực tiếp không? Nếu có, lưu trong Git thông thường.
5. Nếu là dữ liệu lớn thay đổi liên tục hoặc cần truy vấn, chia sẻ theo tập dữ liệu và quản lý vòng đời riêng, cân nhắc hệ thống lưu trữ dữ liệu chuyên dụng hoặc object storage kèm manifest và checksum.

Không có một ngưỡng kích thước cố định áp dụng cho mọi dự án. Hãy xét tần suất thay đổi, số phiên bản cần giữ, số người phải tải, khả năng tái tạo, chính sách backup, quota và năng lực của máy chủ.

## 4. Khi nào nên dùng Git LFS?

Git LFS (Large File Storage) phù hợp khi file lớn là một phần của sản phẩm hoặc nội dung dự án và cần được liên kết với commit cụ thể. Một số ví dụ:

- File thiết kế đồ họa, ảnh gốc hoặc tài nguyên âm thanh/video được chỉnh sửa qua nhiều phiên bản.
- Mô hình 3D, asset game, bản vẽ CAD hoặc dữ liệu nhị phân cần đồng bộ giữa các nhánh.
- File kiểm thử lớn mà kết quả cần tái hiện theo đúng commit mã nguồn.
- Tài liệu nhị phân mà nhóm cần checkout cùng repository và quản lý theo lịch sử Git.

LFS phù hợp khi nhóm muốn giữ trải nghiệm branch, commit, merge và tag của Git cho file lớn. Khi checkout một commit, Git xác định phiên bản file qua pointer được lưu trong commit; Git LFS tải nội dung tương ứng từ LFS server.

### LFS lưu gì trong Git?

Khi một file được theo dõi bằng LFS, Git thường lưu một file pointer văn bản nhỏ thay cho nội dung nhị phân đầy đủ. Pointer chứa phiên bản đặc tả, mã định danh nội dung (OID, thường là SHA-256) và kích thước file.

Ví dụ minh họa pointer:

```text
version https://git-lfs.github.com/spec/v1
oid sha256:4cac19622fc3ada9c0fdeadb33f88f367b541f38b89102a3f1261f6c5b4a4f2f
size 84977953
```

Giá trị OID và kích thước trên chỉ là ví dụ. Blob pointer nằm trong Git history; nội dung thực tế được lưu riêng trên dịch vụ LFS. Khi checkout, Git LFS dùng pointer để lấy đúng object. Vì thế, một commit vẫn xác định được phiên bản file lớn mà không cần nhúng toàn bộ binary vào Git object database.

LFS không làm cho file lớn biến mất khỏi mọi chi phí lưu trữ. Máy chủ LFS vẫn phải lưu các object; người dùng và CI vẫn phải tải nội dung khi cần. Dịch vụ lưu trữ có thể áp dụng giới hạn dung lượng, băng thông, quota, xác thực và chính sách retention riêng.

## 5. Cài đặt và theo dõi file bằng Git LFS

Git LFS cần được cài trên máy làm việc và dịch vụ Git từ xa phải hỗ trợ LFS.

### Bước 1: Cài Git LFS

Sau khi cài Git LFS theo hệ điều hành, kiểm tra:

```bash
git lfs version
```

Khởi tạo tích hợp LFS cho tài khoản hiện tại:

```bash
git lfs install
```

Lệnh này cấu hình các hook cần thiết để Git LFS hoạt động với Git. Nếu chỉ muốn cấu hình trong repository hiện tại, có thể dùng:

```bash
git lfs install --local
```

### Bước 2: Chọn pattern cần theo dõi

Ví dụ muốn quản lý file thiết kế Photoshop và video bằng LFS:

```bash
git lfs track "*.psd"
git lfs track "*.mp4"
```

Các lệnh cập nhật `.gitattributes` để các file khớp pattern được xử lý bởi LFS. Kiểm tra file thuộc tính:

```bash
git diff -- .gitattributes
```

Ví dụ nội dung:

```gitattributes
*.psd filter=lfs diff=lfs merge=lfs -text
*.mp4 filter=lfs diff=lfs merge=lfs -text
```

Nên commit `.gitattributes` cùng thay đổi thêm file LFS để các thành viên và CI nhận được cùng quy tắc. Pattern có thể được giới hạn theo thư mục, chẳng hạn `assets/**/*.psd`; hãy kiểm tra quy tắc Git attributes thực tế cho đường dẫn dự án.

### Bước 3: Add và commit file

```bash
git add .gitattributes
git add assets/design/mockup.psd
git status --short
git commit -m "Add design assets with Git LFS"
```

Khi Git stage file, filter LFS tạo pointer trong index. Nội dung binary được chuyển tới LFS storage khi push thông qua quy trình LFS.

### Bước 4: Kiểm tra file được quản lý bằng LFS

```bash
git lfs ls-files
git lfs status
git show HEAD:assets/design/mockup.psd
```

`git lfs ls-files` liệt kê các file LFS trong revision hiện tại; `git lfs status` cho biết trạng thái file LFS trong working tree và index. `git show` trên file LFS thường hiển thị nội dung pointer được lưu trong Git thay vì toàn bộ binary.

### Bước 5: Push và tải nội dung LFS

```bash
git push origin feature/design-assets
```

Khi push, Git LFS upload object cần thiết lên LFS server và Git push commit pointer lên remote. Nếu server không hỗ trợ LFS, xác thực lỗi hoặc quota hết, thao tác có thể thất bại dù commit pointer đã tồn tại local.

Khi clone repository, người dùng cần Git LFS để tự động tải nội dung tương ứng theo cấu hình smudge mặc định. Nếu clone mà bỏ qua tải LFS, working tree có thể chỉ chứa pointer. Có thể tải nội dung sau:

```bash
git lfs pull
```

`git lfs pull` lấy các object LFS cần cho checkout hiện tại và cập nhật file trong working tree. Trong môi trường CI, hãy bảo đảm cài Git LFS và cấu hình xác thực trước bước checkout hoặc tải LFS.

## 6. Lợi ích và giới hạn của Git LFS

**Lợi ích:**

- Git history lưu pointer nhỏ, giảm dung lượng blob nhị phân lớn trong repository chính.
- File lớn vẫn được liên kết với commit, branch và tag.
- Thành viên có thể tải đúng phiên bản tài sản khi checkout.
- Có thể dùng pattern trong `.gitattributes` để chọn file cụ thể.

**Giới hạn cần tính đến:**

- Cần cài Git LFS ở máy developer và môi trường CI/CD.
- Remote phải hỗ trợ LFS và cung cấp endpoint, quyền truy cập, dung lượng lưu trữ và băng thông phù hợp.
- Lần clone hoặc checkout có thể cần tải lượng dữ liệu lớn nếu có nhiều file LFS.
- Git diff không thể review nội dung binary như mã nguồn; nhóm vẫn cần công cụ preview hoặc quy trình review riêng.
- LFS object cần được backup và retention độc lập với Git object database.
- Xóa pointer trong commit mới không tự động giải phóng object LFS trên server; việc dọn dẹp phụ thuộc dịch vụ và chính sách lưu trữ.

LFS không thay thế kho artifact khi mục tiêu là phân phối package có version, dependency metadata, quyền truy cập, retention hoặc quy trình phát hành. Nó cũng không phải nơi lưu bí mật như token, private key hoặc thông tin đăng nhập.

## 7. Khi nào nên dùng kho artifact?

Kho artifact phù hợp với file được tạo ra bởi build, test, đóng gói hoặc phát hành, đặc biệt khi nhiều hệ thống cần tải theo phiên bản. Ví dụ:

- JAR, WAR, ZIP, installer, binary executable.
- Package nội bộ như Maven, npm, NuGet hoặc package tương đương.
- Container image được định danh bằng tag và digest.
- Báo cáo kiểm thử, coverage, SBOM, log build hoặc bundle triển khai.
- Bộ dữ liệu, mô hình đã huấn luyện hoặc tài nguyên lớn được pipeline tạo ra.

### Vì sao artifact không nên nằm trong Git?

Artifact thường có thể được tái tạo từ source code, dependency đã khóa và cấu hình build. Mỗi lần build có thể tạo binary mới; nếu commit mọi binary vào Git, lịch sử sẽ tăng nhanh và không giúp review logic. Kho artifact quản lý chúng theo version hoặc build ID, hỗ trợ tải đúng gói mà không phải clone toàn bộ Git history.

Một quy trình điển hình:

```text
Git commit / tag
       |
       v
CI checkout source và dependencies
       |
       v
Build + test + package
       |
       v
Publish artifact với version/build ID
       |
       v
Deploy / downstream project tải artifact
```

Trong Git, lưu những thông tin cần để tái tạo hoặc truy xuất artifact, chẳng hạn:

- Tệp cấu hình build và dependency lockfile.
- Phiên bản ứng dụng, build ID hoặc release tag.
- Manifest mô tả artifact được tạo ra.
- Digest/checksum để xác minh nội dung tải về.
- Đường dẫn hoặc tọa độ package trong kho artifact.

Không nên chỉ ghi một URL trỏ tới `latest`, vì nội dung của `latest` có thể thay đổi. Nên dùng version bất biến hoặc digest để bảo đảm build và triển khai có thể tái lập.

### Ví dụ manifest tham chiếu artifact

```yaml
application: payment-service
source_commit: 8a21d5c4
version: 2.4.0
artifact:
  repository: releases
  name: payment-service-2.4.0.jar
  sha256: 2a7f...example-digest...
```

Đây là cấu trúc minh họa; tên field và cách xác thực phụ thuộc công cụ của tổ chức. Không ghi token hoặc thông tin xác thực trong manifest. Pipeline nên lấy credential từ secret manager hoặc cơ chế CI an toàn.

## 8. Khi nào nên loại file khỏi quản lý phiên bản?

File nên được bỏ khỏi Git khi không phải đầu vào nguồn cần chia sẻ theo lịch sử và có thể tái tạo hoặc lưu ở nơi phù hợp hơn. Ví dụ:

- Thư mục build: `build/`, `dist/`, `target/` nếu là đầu ra sinh tự động.
- Cache: `.gradle/`, `.m2/` local, `node_modules/`, cache compiler.
- Log, file tạm, crash dump và file editor tạo ra.
- File cấu hình cá nhân, biến môi trường chứa thông tin riêng hoặc secret.
- File dữ liệu thử nghiệm lớn được sinh lại từ fixture hoặc pipeline.
- Bản sao lưu local, export tạm và file tải về.

### Dùng `.gitignore`

Ví dụ:

```gitignore
# Build outputs
build/
target/
dist/

# Dependency/cache
node_modules/
.gradle/

# Logs and temporary files
*.log
*.tmp
*.swp

# Local environment and secrets
.env
.env.*.local
*.pem
*.key

# Local IDE settings
.idea/
.vscode/
```

Đây chỉ là ví dụ. Một số file cấu hình IDE hoặc `.env.example` có thể cần commit để chia sẻ thiết lập mẫu; hãy phân biệt file mẫu không chứa secret với file local chứa dữ liệu riêng. Không nên ignore rộng một pattern nếu dự án cần theo dõi một số file cùng loại.

### `.gitignore` không bỏ theo dõi file đã commit

Nếu file đã được Git track, thêm pattern vào `.gitignore` không làm Git ngừng theo dõi nó. Để giữ file trong working tree nhưng bỏ khỏi index:

```bash
git rm --cached path/to/large-generated-file.zip
```

Sau đó commit việc bỏ theo dõi:

```bash
git add .gitignore
git commit -m "Stop tracking generated archive"
```

File vẫn còn trên máy hiện tại; các clone mới không nhận file đó từ commit mới. Nếu file vẫn cần cho người dùng hoặc pipeline, hãy lưu nó trong kho artifact hoặc nơi chia sẻ phù hợp và cập nhật hướng dẫn tải/tạo lại.

Lưu ý: commit mới chỉ loại file khỏi phiên bản hiện tại. Các commit cũ vẫn chứa blob lớn trong lịch sử. Vì vậy, repository có thể vẫn lớn cho đến khi lịch sử được viết lại và các bản sao cũ được xử lý.

## 9. So sánh LFS, artifact và ignore theo tình huống

| Tình huống | Lựa chọn thường phù hợp | Lý do |
| --- | --- | --- |
| File Photoshop được chỉnh sửa thường xuyên và cần checkout theo branch | Git LFS | Mỗi commit tham chiếu đúng phiên bản asset |
| File video gốc dùng trong dự án nội dung | Git LFS hoặc object storage có versioning | Chọn LFS nếu cần liên kết commit; chọn object storage nếu cần quản lý dữ liệu độc lập |
| JAR được tạo bởi CI cho mỗi release | Kho artifact | Package có version, metadata, retention và cơ chế phân phối |
| Container image | Container registry | Lưu layer, tag, digest và quyền pull/push phù hợp |
| Thư mục `build/` hoặc `target/` | `.gitignore` | Có thể tái tạo từ source và build configuration |
| Log local hoặc cache | `.gitignore` | Không phải dữ liệu nguồn cần chia sẻ |
| File cấu hình chứa token | Secret manager và `.gitignore` | Không đưa secret vào Git history |
| Dataset lớn thay đổi theo đợt và được pipeline xử lý | Object storage/data versioning kèm manifest | Quản lý dữ liệu, metadata và lifecycle độc lập với source |
| File PDF hướng dẫn nhỏ cần review cùng mã nguồn | Git thông thường | Dễ diff metadata và giữ cùng commit |

Kích thước chỉ là một yếu tố. Hãy hỏi ai cần file, khi nào cần, có cần checkout đúng phiên bản cùng commit hay không, và ai chịu trách nhiệm backup/retention.

## 10. Chuyển file đang được Git theo dõi sang LFS

Nếu file đã tồn tại trong repository và muốn các phiên bản tiếp theo dùng LFS, có hai hướng.

### Hướng A: Chuyển các phiên bản tương lai

Nếu chấp nhận lịch sử cũ vẫn giữ blob lớn, có thể thêm pattern vào LFS và commit lại file:

```bash
git lfs track "*.psd"
git add .gitattributes
git add --renormalize assets/design/mockup.psd
git status --short
git commit -m "Track design files with Git LFS"
```

Kiểm tra `git lfs ls-files` để xác nhận file hiện tại được quản lý bằng LFS. Lưu ý: chỉ thêm `git lfs track` không tự chuyển các commit cũ sang LFS; nó chỉ ảnh hưởng tới những lần add/commit sau khi thuộc tính được áp dụng.

### Hướng B: Chuyển cả lịch sử bằng `git lfs migrate`

Nếu repository quá lớn do nhiều phiên bản cũ của file, có thể cần migrate lịch sử sang LFS. Đây là thao tác viết lại commit, thay đổi mã hash của các commit liên quan và có thể ảnh hưởng tới mọi nhánh/tag được chuyển đổi.

Trước tiên, tạo bản sao lưu hoặc clone mirror để có thể khôi phục:

```bash
git clone --mirror https://example.com/team/project.git project-backup.git
git -C project-backup.git lfs fetch --all origin
```

Mirror clone sao chép Git refs và object; `git lfs fetch --all` tải các LFS object được tham chiếu bởi các refs để bản sao lưu có cả nội dung binary. Xác nhận lệnh fetch hoàn tất trước khi xem bản mirror là bản backup đầy đủ.

Chạy dry-run để xem phạm vi:

```bash
git lfs migrate info --everything --include="*.psd,*.mp4"
git lfs migrate import --dry-run --everything --include="*.psd,*.mp4"
```

Sau khi review kết quả, thực hiện migrate trong clone chuyên dụng hoặc working copy đã sao lưu:

```bash
git lfs migrate import --everything --include="*.psd,*.mp4"
```

Kiểm tra lịch sử và danh sách file LFS:

```bash
git lfs ls-files
git log --oneline --all --decorate -20
git status -sb
```

Migrate lịch sử cần phối hợp với toàn bộ thành viên vì commit hash thay đổi. Các nhánh local, pull request, tag và clone hiện có có thể cần cập nhật hoặc clone lại. Khi cập nhật remote, cần đẩy lại các ref đã viết lại, bao gồm nhánh và tag có liên quan; thao tác thường cần force push theo kế hoạch được thống nhất. Chỉ thực hiện sau khi xác nhận phạm vi, backup cả Git lẫn LFS object, quyền ghi và lịch bảo trì. Không force push một repository dùng chung mà chưa thông báo và thống nhất với nhóm.

Nếu không cần giảm kích thước lịch sử cũ, hướng A đơn giản hơn. Nếu mục tiêu là giảm dung lượng Git history hiện có, hướng A không đủ; cần migrate history hoặc giữ nguyên repository và tạo repository mới theo kế hoạch.

## 11. Xử lý file lớn đã commit nhầm

Nếu một file lớn đã được commit vào Git thông thường, việc xóa file ở commit mới không xóa blob khỏi lịch sử. Cần phân biệt ba mục tiêu:

1. **Không tiếp tục theo dõi:** thêm ignore và `git rm --cached` để các commit sau không đưa file vào nữa.
2. **Lưu các phiên bản mới bằng LFS:** thêm pattern, stage lại file và commit pointer mới; lịch sử cũ vẫn giữ blob.
3. **Giảm kích thước lịch sử:** viết lại lịch sử bằng công cụ như `git lfs migrate` hoặc `git filter-repo`, sau khi backup và thống nhất vì mã commit thay đổi.

Nếu file chứa secret, credential hoặc dữ liệu nhạy cảm, chỉ xóa file khỏi commit mới là chưa đủ. Cần thu hồi/thay credential, xử lý lịch sử theo quy trình bảo mật, kiểm tra bản sao/fork/cache và phối hợp với quản trị dịch vụ Git. Không xem việc viết lại history là cách thay thế việc rotate secret.

## 12. Lập chính sách cho repository

Một chính sách thực tế nên trả lời rõ:

- Loại file nào được commit trực tiếp?
- Pattern nào được theo dõi bằng LFS?
- Artifact nào do CI tạo và nơi lưu trữ của chúng?
- File nào bị ignore và cách tái tạo?
- Ai chịu trách nhiệm quyền truy cập, quota, backup và retention cho LFS/artifact?
- CI cần bước nào để tải file LFS hoặc artifact?
- Version và checksum được ghi ở đâu để có thể tái lập build?

Ví dụ cấu trúc repository:

```text
project/
├── src/                 # Source code: Git thường
├── docs/                # Tài liệu văn bản: Git thường
├── assets/              # Asset nhị phân cần version: Git LFS
├── .gitattributes       # Quy tắc LFS và thuộc tính Git
├── .gitignore           # Cache, build output, file local
├── build.gradle         # Build configuration: Git thường
└── artifact-manifest.yml # Version/digest artifact: Git thường
```

Đầu ra build và package release được CI publish tới kho artifact, không đặt vào `build/` rồi commit cùng source. File asset trong `assets/` được LFS quản lý nếu cần checkout theo commit. Manifest lưu version và digest để pipeline tải đúng artifact.

## 13. Quy trình review trước khi thêm file lớn

Trước khi stage một file lớn, kiểm tra:

```bash
git status --short
git check-attr filter diff merge -- path/to/file
git lfs ls-files
```

Nếu file chưa có quy tắc phù hợp, xác định nó thuộc nhóm source, LFS, artifact hay ignore. Kiểm tra thêm kích thước:

```bash
git diff --stat
git status --short
```

Với file đã stage, xem kích thước và nội dung thay đổi trước khi commit. Không dựa hoàn toàn vào giới hạn kích thước của host: giới hạn push chỉ là rào chắn cuối cùng, không thay thế chính sách lưu trữ.

Một checklist review:

1. File có cần lịch sử phiên bản trong Git không?
2. Có cần checkout đúng phiên bản cùng commit không?
3. File có thể tái tạo từ source hoặc pipeline không?
4. Có kho artifact hoặc object storage phù hợp không?
5. Remote có hỗ trợ LFS và đủ quota/bandwidth không?
6. CI và developer đã cài/configure LFS nếu cần chưa?
7. `.gitattributes`, `.gitignore` và manifest đã được cập nhật chưa?
8. Có checksum, version và hướng dẫn tải/tạo lại không?

## 14. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân có thể có | Hướng xử lý |
| --- | --- | --- |
| Push báo file vượt giới hạn | File được commit trực tiếp vào Git hoặc host giới hạn kích thước | Đánh giá LFS/artifact; xóa khỏi lịch sử nếu cần giảm blob cũ |
| File LFS checkout ra nội dung pointer | Chưa cài Git LFS, chưa tải object hoặc smudge bị bỏ qua | Cài LFS, xác thực và chạy `git lfs pull` |
| Push pointer thành công nhưng LFS upload lỗi | Thiếu quyền, quota hoặc endpoint LFS không sẵn sàng | Kiểm tra cấu hình remote LFS, xác thực và quota của dịch vụ |
| `git lfs track` rồi mà repository vẫn lớn | Các blob cũ vẫn nằm trong history | Migrate lịch sử nếu cần giảm kích thước, hoặc chấp nhận lịch sử cũ |
| File đã thêm vào `.gitignore` vẫn hiện trong Git | File đã được track từ trước | Dùng `git rm --cached`, commit và giữ file local nếu cần |
| CI tải source nhưng thiếu asset LFS | Runner không cài LFS hoặc checkout bỏ qua smudge | Cài Git LFS và chạy `git lfs pull` với credential phù hợp |
| Clone LFS quá chậm | Tải nhiều object lớn hoặc băng thông/quota hạn chế | Chỉ fetch LFS object cần thiết, xem xét artifact/object storage hoặc quy trình tải theo nhu cầu |
| Artifact không tái lập được | Tham chiếu `latest` hoặc thiếu checksum/build metadata | Dùng version bất biến, digest, source commit và manifest |

## 15. Thực hành

Thực hiện trên repository thử nghiệm, không dùng dữ liệu nhạy cảm hoặc file độc quyền không được phép chia sẻ:

1. Tạo file văn bản nhỏ, file nhị phân thử nghiệm và thư mục build giả lập.
2. Commit file văn bản vào Git thông thường.
3. Tạo `.gitattributes` và dùng `git lfs track` cho file nhị phân.
4. Stage `.gitattributes` và file nhị phân, sau đó kiểm tra `git lfs ls-files`.
5. Commit và push tới remote thử nghiệm có hỗ trợ LFS; clone lại để kiểm tra nội dung được tải.
6. Thêm thư mục build vào `.gitignore` và xác nhận Git không đưa file mới trong thư mục đó vào status.
7. Tạo một file đã track rồi thêm pattern ignore; quan sát file vẫn được theo dõi.
8. Dùng `git rm --cached` để bỏ theo dõi file thử nghiệm, commit và xác nhận file local vẫn còn.
9. Tạo manifest artifact chứa version, source commit và checksum giả lập; thảo luận cách CI publish và tải package.
10. So sánh dung lượng và lịch sử khi lưu binary trực tiếp với khi dùng LFS; giải thích vì sao LFS migration cần kế hoạch viết lại lịch sử.

## 16. Tự kiểm tra kiến thức

1. Vì sao file nhị phân lớn thường không phù hợp với Git thông thường?
2. Git LFS lưu gì trong Git commit và lưu nội dung thực tế ở đâu?
3. Khi nào nên chọn LFS thay vì kho artifact?
4. Vì sao JAR hoặc container image được tạo từ CI thường nên nằm trong kho artifact?
5. `.gitignore` có tác dụng gì với file đã được track?
6. `git rm --cached` khác xóa file khỏi working tree như thế nào?
7. Vì sao thêm pattern bằng `git lfs track` không tự chuyển các blob lịch sử cũ?
8. `git lfs migrate import` ảnh hưởng tới commit hash và các clone khác ra sao?
9. Vì sao artifact nên được tham chiếu bằng version bất biến hoặc digest thay vì `latest`?
10. Những yếu tố nào cần kiểm tra trước khi quyết định dùng LFS trong CI/CD?

## Kết luận

Hãy lưu trong Git những file là nguồn sự thật và cần diff/lịch sử cùng mã nguồn; dùng Git LFS cho tài sản nhị phân lớn cần checkout theo commit; dùng kho artifact cho package, binary phát hành và đầu ra pipeline; loại cache, file tạm và dữ liệu có thể tái tạo khỏi quản lý phiên bản. Khi chuyển đổi file đã được commit, cần phân biệt việc ngừng theo dõi, chuyển các phiên bản tương lai sang LFS và viết lại toàn bộ lịch sử. Một chính sách rõ ràng về version, checksum, quyền truy cập, quota và backup giúp repository gọn hơn mà vẫn bảo đảm nhóm có thể tái tạo và phân phối đúng tài sản cần thiết.
