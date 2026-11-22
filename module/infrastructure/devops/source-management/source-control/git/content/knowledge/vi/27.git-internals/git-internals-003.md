# Định dạng kho SHA-1, SHA-256 và giới hạn tương thích công cụ

Git nhận diện object trong repository bằng một mã định danh nội dung (*object ID* hoặc OID). Theo truyền thống, Git dùng SHA-1; các phiên bản Git mới cũng hỗ trợ định dạng repository dùng SHA-256. Hai định dạng tạo ra OID có độ dài khác nhau và ảnh hưởng đến toàn bộ object database, không chỉ một tệp riêng lẻ.

SHA-256 cung cấp biên an toàn mật mã tốt hơn trước các tấn công va chạm đã biết đối với SHA-1. Tuy nhiên, định dạng repository là một quyết định ảnh hưởng đến Git client, máy chủ lưu trữ, API, CI, IDE và script của cả nhóm. Một repository SHA-256 không thể được xem như repository SHA-1 chỉ bằng cách đổi một giá trị cấu hình. Trước khi chọn định dạng, cần hiểu cách Git tính OID, cách kiểm tra định dạng hiện tại và giới hạn tương thích của hệ sinh thái.

## 1. Object ID là gì?

Git lưu dữ liệu trong các object như blob, tree, commit và annotated tag. Mỗi object có một mã định danh được tính bằng cách băm phần header cùng nội dung object. Header chứa loại object và kích thước nội dung; do đó, OID không đơn giản là hash của riêng byte trong tệp.

Ví dụ về cấu trúc khái niệm:

```text
<type> <size>\0<content>
```

Với blob, `content` là nội dung tệp. Với commit, nội dung gồm tree OID, parent OID, author, committer, message và các trường khác. Tree chứa các mục đường dẫn cùng OID của object tương ứng. Khi nội dung hoặc cấu trúc object thay đổi, OID cũng thay đổi.

Git dùng OID để liên kết các object:

```text
commit
  └── tree
       ├── blob (README.md)
       └── tree (src/)
            └── blob (App.java)
```

Vì commit tham chiếu tree và parent bằng OID, thay đổi thuật toán hash của repository ảnh hưởng đến cách định danh blob, tree, commit và tag. OID xuất hiện trong log, ref, packfile, index, giao thức trao đổi và các công cụ tích hợp.

## 2. SHA-1 và SHA-256 khác nhau thế nào?

Git hỗ trợ hai định dạng object chính:

| Đặc điểm | SHA-1 | SHA-256 |
|---|---|---|
| Kích thước digest | 160 bit | 256 bit |
| Độ dài dạng hex đầy đủ | 40 ký tự | 64 ký tự |
| Định dạng mặc định truyền thống của Git | Có | Không |
| Mức độ hỗ trợ trong hệ sinh thái | Rất rộng và lâu đời | Cần kiểm tra phiên bản Git, hosting và công cụ tích hợp |
| Khả năng chống va chạm | Có điểm yếu mật mã đã biết | Biên an toàn mạnh hơn trước các tấn công va chạm hiện biết |

Ví dụ hình dạng OID:

```text
SHA-1:   8b1a9953c4611296a827abf8c47804d7f1e9f1d2
SHA-256: 2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824
```

Các chuỗi trên chỉ minh họa độ dài và hình dạng hex; chúng không đại diện cho cùng một object trong hai repository. OID phụ thuộc thuật toán hash và nội dung object.

## 3. Vì sao Git chuyển dần sang SHA-256?

SHA-1 từng được dùng rộng rãi trong nhiều hệ thống. Tuy nhiên, các nghiên cứu và thực nghiệm đã chứng minh khả năng tạo va chạm SHA-1 với chi phí thấp hơn mức an toàn mong muốn. Va chạm xảy ra khi hai nội dung khác nhau tạo cùng digest, làm suy yếu giả định rằng OID duy nhất đại diện cho một nội dung.

Git đã tích hợp các biện pháp phát hiện va chạm SHA-1, nhưng việc dùng SHA-1 vẫn mang theo một thuật toán có biên an toàn mật mã suy giảm. SHA-256 có digest dài hơn và hiện cung cấp mức chống va chạm tốt hơn.

Điều này không có nghĩa mọi repository SHA-1 hiện tại đều đã bị xâm phạm. Git còn có các kiểm tra và biện pháp phòng vệ riêng; rủi ro thực tế phụ thuộc mô hình đe dọa và môi trường. Việc chọn SHA-256 là một bước tăng cường định dạng định danh object, nhưng không thay thế chữ ký commit/tag, xác thực transport, phân quyền, review hay kiểm tra mã nguồn.

## 4. Định dạng object được lưu ở đâu?

Định dạng object là thuộc tính của repository. Với repository SHA-256, Git ghi extension `objectFormat` trong cấu hình repository, thường ở `.git/config`:

```ini
[extensions]
    objectFormat = sha256
```

Với repository SHA-1 truyền thống, `sha1` là mặc định và mục `extensions.objectFormat` có thể không xuất hiện trong file cấu hình.

Không nên sửa trực tiếp `.git/config` để đổi `objectFormat` của một repository đã có dữ liệu. Định dạng ảnh hưởng đến OID của mọi object; thay một dòng cấu hình không chuyển đổi object database, ref, index hoặc packfile.

## 5. Kiểm tra định dạng repository hiện tại

Lệnh trực tiếp nhất:

```bash
git rev-parse --show-object-format
```

Kết quả có thể là:

```text
sha1
```

hoặc:

```text
sha256
```

Lệnh này cho biết định dạng object mà repository hiện tại sử dụng. Nếu Git quá cũ và không nhận tùy chọn `--show-object-format`, hãy kiểm tra phiên bản Git và cấu hình repository.

Có thể kiểm tra extension trong cấu hình:

```bash
git config --local --get extensions.objectFormat
```

Nếu kết quả là `sha256`, repository khai báo SHA-256. Nếu không có output, repository thường dùng mặc định SHA-1. Dùng thêm:

```bash
git config --show-origin --get extensions.objectFormat
git --version
```

`--show-origin` cho biết file cấu hình chứa giá trị nếu có. Hãy chạy các lệnh trong đúng repository, vì mỗi repository có thể dùng định dạng khác nhau.

## 6. Tạo repository SHA-256 mới

Git hỗ trợ chọn object format khi khởi tạo repository mới bằng `git init --object-format`.

Ví dụ tạo repository SHA-256:

```bash
mkdir project-sha256
cd project-sha256
git init --object-format=sha256
```

Kiểm tra:

```bash
git rev-parse --show-object-format
```

Kết quả mong đợi:

```text
sha256
```

Để so sánh, repository thông thường:

```bash
mkdir project-sha1
cd project-sha1
git init --object-format=sha1
```

`sha1` là định dạng mặc định truyền thống nên có thể bỏ tùy chọn `--object-format=sha1`. Tùy chọn này được giữ trong ví dụ để làm rõ định dạng đang chọn.

Hỗ trợ SHA-256 được đưa vào Git từ dòng phiên bản 2.29. Các phiên bản và công cụ xung quanh có mức hỗ trợ khác nhau; tài liệu Git vẫn lưu ý cần xem xét tính tương thích của SHA-256. Hãy kiểm tra phiên bản Git trên máy phát triển, máy CI và máy chủ trước khi áp dụng cho dự án chung.

## 7. Clone và làm việc với remote SHA-256

Khi clone repository, Git cần hiểu định dạng object mà remote sử dụng. Một Git client hỗ trợ SHA-256 có thể làm việc với remote được triển khai theo định dạng tương ứng, nhưng không nên giả định mọi dịch vụ hosting hoặc server Git đều đã hỗ trợ định dạng này.

Sau khi clone, kiểm tra:

```bash
git clone <repository-url>
cd <repository-directory>
git rev-parse --show-object-format
git remote -v
```

Nếu repository remote dùng SHA-256, local clone cần được tạo bằng Git có hỗ trợ định dạng đó. Nếu server hoặc client không hỗ trợ, thao tác clone/fetch có thể thất bại hoặc dịch vụ không cho phép tạo repository định dạng này.

Khi đánh giá hosting, cần xác minh ít nhất:

- Dịch vụ có cho tạo repository SHA-256 hay không.
- Giao thức clone, fetch và push có hỗ trợ object format đó hay không.
- API trả về OID có chấp nhận chuỗi 64 ký tự hay vẫn giả định 40 ký tự.
- Web UI, pull/merge request, release, archive và webhook có xử lý đúng OID SHA-256 không.
- Runner CI, cache, artifact và công cụ tích hợp có hỗ trợ không.

Không suy ra khả năng hỗ trợ chỉ từ việc dịch vụ cho phép lưu file hoặc chạy Git command thông thường. Hãy thử nghiệm trên repository không quan trọng trước khi chọn định dạng cho dự án thật.

## 8. Giới hạn tương thích giữa SHA-1 và SHA-256

Hai repository có cùng nội dung source nhưng dùng định dạng object khác nhau sẽ có OID khác nhau. Một commit SHA-1 và commit SHA-256 tương ứng không có cùng mã định danh vì thuật toán hash và các tham chiếu object bên trong khác nhau.

Do đó, không thể coi OID SHA-1 40 ký tự là OID SHA-256 64 ký tự hoặc thay thế trực tiếp một chuỗi bằng chuỗi kia. Các thao tác trao đổi giữa repository khác định dạng có giới hạn; không nên giả định có thể fetch hoặc push trực tiếp giữa SHA-1 và SHA-256 trong mọi phiên bản Git và mọi giao thức.

Git có thiết kế chuyển đổi hash và các cơ chế tương thích phục vụ quá trình chuyển đổi, nhưng hỗ trợ liên thông phụ thuộc phiên bản, tính năng cụ thể và hạ tầng ở hai đầu. Với workflow thông thường, hãy giả định các repository trao đổi trực tiếp phải dùng định dạng tương thích, trừ khi tài liệu của phiên bản Git và máy chủ xác nhận rõ đường chuyển đổi được hỗ trợ.

Trước khi tích hợp một hệ thống SHA-256 vào hệ sinh thái SHA-1 hiện có, hãy kiểm tra kỹ:

- Git client tối thiểu của mọi thành viên.
- Phiên bản Git server và giao thức remote.
- Công cụ mirror, backup, code review và CI.
- API hoặc script có parse OID cố định 40 ký tự.
- Submodule, dependency repository và công cụ quản lý source bên ngoài.
- Cách chuyển đổi, lưu trữ và xác minh chữ ký khi lịch sử được tái tạo.

## 9. OID ngắn và script giả định SHA-1

Người dùng thường thấy OID rút gọn trong `git log --oneline`, ví dụ `a1b2c3d`. Độ dài rút gọn không phải lúc nào cũng cố định; Git chọn đủ ký tự để phân biệt object trong repository theo cấu hình và trạng thái hiện tại.

Không nên viết script giả định OID luôn dài 40 ký tự. Ví dụ regex sau chỉ phù hợp với SHA-1:

```regex
^[0-9a-f]{40}$
```

Nếu công cụ cần xử lý cả hai định dạng, có thể chấp nhận 40 hoặc 64 ký tự hex:

```regex
^[0-9a-f]{40}([0-9a-f]{24})?$
```

Tuy nhiên, tốt hơn là không tự parse OID bằng regex khi Git có thể cung cấp giá trị chuẩn. Dùng các lệnh plumbing hoặc porcelain để lấy object ID và xác định định dạng:

```bash
git rev-parse --show-object-format
git rev-parse HEAD
git rev-parse HEAD^{tree}
git cat-file -t HEAD
```

Trong script, nên xử lý OID như chuỗi có độ dài thay đổi theo repository. Tránh cắt cố định 40 ký tự, cấp cột database quá ngắn hoặc dùng kiểu dữ liệu giả định OID luôn có kích thước SHA-1.

## 10. Tên branch, tag và ref có thay đổi không?

Tên branch và tag vẫn là tên ref như `refs/heads/main` hoặc `refs/tags/v1.0.0`. Chúng không tự dài thêm khi dùng SHA-256. Tuy nhiên, giá trị mà ref trỏ đến sẽ là OID theo định dạng repository.

Ví dụ:

```text
refs/heads/main -> OID 40 ký tự trong SHA-1 repository
refs/heads/main -> OID 64 ký tự trong SHA-256 repository
```

Các lệnh quen thuộc vẫn giữ cách dùng tương tự:

```bash
git branch --show-current
git log --oneline --decorate -5
git show HEAD
git rev-parse HEAD
```

Điểm cần chú ý nằm ở công cụ xử lý OID, dữ liệu trao đổi và những tích hợp dùng định dạng cố định. Các tên ref, thông điệp commit và cấu trúc làm việc branch vẫn quen thuộc.

## 11. Ảnh hưởng đến API, CI và công cụ tích hợp

Một số hệ thống bên ngoài có thể giả định OID là SHA-1 40 ký tự. Ví dụ:

- Database schema dùng `CHAR(40)` để lưu commit ID.
- Regex trong webhook handler chỉ chấp nhận 40 ký tự hex.
- Pipeline cắt commit SHA bằng `substring(0, 40)`.
- Công cụ review, dashboard hoặc plugin dùng OID làm khóa nhưng validation cố định độ dài.
- Script shell dùng pattern `[0-9a-f]{40}` để xác nhận object ID.
- Hệ thống lưu cache theo key được tạo từ OID SHA-1.

Trước khi bật SHA-256, cần rà soát các giả định này. Nên dùng trường dữ liệu đủ dài, parse OID theo định dạng trả về từ Git và kiểm thử luồng webhook, API, build, release cùng backup.

Nếu hệ thống có hỗ trợ nhiều định dạng, lưu thêm thông tin hash algorithm cùng OID để tránh nhầm hai chuỗi hoặc cùng một giá trị được hiểu trong namespace khác nhau. Không nên dùng riêng độ dài làm cơ chế xác thực dữ liệu; hãy đọc object format từ repository hoặc giao thức đã xác thực.

## 12. Chữ ký, tag và các tích hợp khác

Thay đổi object format làm thay đổi OID của object. Nếu lịch sử được chuyển đổi từ SHA-1 sang SHA-256 bằng cách tạo lại object, các commit và tag có thể có OID mới. Những chữ ký gắn với object cũ không tự động trở thành chữ ký hợp lệ của object mới; cần có kế hoạch ký lại và xác minh provenance theo quy trình phát hành.

Các tích hợp cần được rà soát gồm:

- **Submodule:** superproject lưu gitlink trỏ đến commit của repository con; cần kiểm tra hỗ trợ object format ở cả hai repository và công cụ checkout.
- **Git LFS:** pointer LFS có OID nội dung riêng; việc Git repository dùng SHA-1 hay SHA-256 không đồng nghĩa có thể bỏ qua cấu hình hoặc kiểm tra tương thích của LFS server/client.
- **Backup/mirror:** công cụ sao chép object database phải hiểu đúng định dạng repository.
- **Patch và archive:** các workflow dùng commit ID, tag hoặc metadata release cần kiểm tra lại cách biểu diễn OID.
- **Chữ ký:** kiểm tra signer, trust và chính sách ký lại nếu object được tạo lại trong quá trình chuyển đổi.

Không phải tất cả tích hợp đều hỏng khi đổi định dạng, nhưng không nên coi chúng tương thích nếu chưa kiểm tra bằng phiên bản và cấu hình thực tế.

## 13. Có nên chọn SHA-256 cho repository mới không?

Quyết định phụ thuộc khả năng tương thích của toàn bộ hệ thống, không chỉ Git client trên máy cá nhân.

| Bối cảnh | Hướng cân nhắc |
|---|---|
| Repository cá nhân, công cụ đều mới và không cần kết nối dịch vụ cũ | Có thể thử SHA-256 để đánh giá workflow |
| Dự án dùng hosting, CI và plugin của tổ chức | Kiểm tra hỗ trợ chính thức của từng thành phần trước |
| Monorepo có nhiều script và hệ thống tích hợp cũ | Đánh giá mọi giả định OID 40 ký tự và thử nghiệm toàn pipeline |
| Dự án cần tương thích rộng với clone/client cũ | SHA-1 thường vẫn là lựa chọn tương thích hơn hiện nay |
| Repository hiện tại đã dùng SHA-1 và hoạt động ổn định | Không đổi định dạng chỉ để chạy theo xu hướng; cần lý do và kế hoạch chuyển đổi rõ ràng |

Nếu tổ chức chưa có chính sách SHA-256, hãy dùng định dạng được nền tảng hosting và công cụ nội bộ hỗ trợ chính thức. Với repository mới mang tính thử nghiệm, có thể tạo một repository SHA-256 riêng để đánh giá trước.

## 14. Quy trình thử nghiệm repository SHA-256

Có thể thử nghiệm trên thư mục độc lập, không ảnh hưởng repository đang làm việc:

```bash
# 1. Xác nhận Git có hỗ trợ object format.
git --version

# 2. Tạo repository SHA-256 mới.
mkdir git-sha256-lab
cd git-sha256-lab
git init --object-format=sha256

# 3. Xác minh định dạng.
git rev-parse --show-object-format

# 4. Tạo commit thử nghiệm.
echo "SHA-256 repository test" > README.md
git add README.md
git -c user.name="Git Lab" -c user.email="git-lab@example.com" commit -m "test: initialize sha256 repository"

# 5. Xem OID của commit và tree.
git rev-parse HEAD
git rev-parse HEAD^{tree}

# 6. Kiểm tra loại object.
git cat-file -t HEAD
git cat-file -t HEAD^{tree}
```

OID đầy đủ trong repository SHA-256 có 64 ký tự hex. Nếu lệnh `git init --object-format=sha256` không được hỗ trợ, kiểm tra phiên bản Git và tài liệu của bản cài đặt. Không thử bằng cách sửa thủ công `.git/config` của một repository hiện có.

Sau thử nghiệm local, chỉ kết nối remote thử nghiệm khi đã xác nhận server hỗ trợ SHA-256. Kiểm tra clone, fetch, push, pull request, CI, tag, release và backup trước khi xem định dạng này là sẵn sàng cho dự án.

## 15. Những hiểu nhầm thường gặp

| Hiểu nhầm | Cách hiểu đúng |
|---|---|
| SHA-256 chỉ làm OID dài hơn | Nó thay đổi định dạng định danh của toàn bộ object database và các công cụ xử lý OID |
| Có thể đổi SHA-1 sang SHA-256 bằng cách sửa `.git/config` | Cần chuyển đổi object và các tham chiếu; đổi cấu hình đơn thuần làm repository không nhất quán |
| Mọi Git hosting đều hỗ trợ SHA-256 | Hỗ trợ phụ thuộc dịch vụ, phiên bản, API và workflow tích hợp |
| OID luôn có 40 ký tự | SHA-1 có 40 ký tự hex; SHA-256 có 64 ký tự hex |
| Tên branch và tag phải đổi theo SHA-256 | Tên ref giữ nguyên; object ID mà ref trỏ đến thay đổi độ dài và giá trị |
| Chữ ký cũ tự động xác minh sau khi chuyển đổi lịch sử | Object mới có nội dung/ID mới; chữ ký và provenance cần được xử lý theo quy trình chuyển đổi |
| SHA-256 thay thế mọi lớp bảo mật Git | Nó tăng độ bền của định danh object, nhưng không thay thế xác thực, phân quyền, review hoặc chữ ký |

## 16. Ghi nhớ

Git truyền thống dùng SHA-1 và có hỗ trợ repository SHA-256 ở các phiên bản mới. SHA-1 tạo OID 40 ký tự hex; SHA-256 tạo OID 64 ký tự hex. OID được tính từ header cùng nội dung object nên định dạng hash ảnh hưởng đến blob, tree, commit và tag.

Dùng `git rev-parse --show-object-format` để kiểm tra repository và `git init --object-format=sha256` để tạo repository SHA-256 mới trên Git có hỗ trợ. Đừng sửa trực tiếp `extensions.objectFormat` để chuyển repository đang tồn tại.

Trước khi chọn SHA-256 cho dự án chung, xác minh hỗ trợ của Git client, hosting, remote protocol, API, CI, IDE, submodule, backup và script. Chữ ký và các quy trình release cũng cần được kiểm tra nếu lịch sử được chuyển đổi. Định dạng hash là quyết định ở cấp repository và hệ sinh thái; khả năng tương thích của toàn bộ chuỗi công cụ mới là điều kiện để sử dụng an toàn.
