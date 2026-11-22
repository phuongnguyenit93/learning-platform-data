# Vì sao tệp nhị phân lớn làm lịch sử kho mã tăng nhanh

Một repository Git có thể bắt đầu rất nhỏ nhưng tăng lên hàng gigabyte sau một thời gian phát triển. Nguyên nhân thường không chỉ là số lượng file hiện tại, mà còn là các phiên bản của tệp lớn đã được ghi vào lịch sử commit. Một file video, ảnh thiết kế, bản dựng, gói dữ liệu hoặc mô hình máy học có thể được thay đổi nhiều lần; mỗi phiên bản được commit có thể làm object database tăng thêm đáng kể.

Git được thiết kế để quản lý lịch sử mã nguồn hiệu quả. Với tệp văn bản, các phiên bản thường có nhiều dòng giống nhau nên Git có thể nén và lưu delta khá tốt. Với nhiều định dạng nhị phân, chỉ một thay đổi nhỏ về mặt ý nghĩa cũng có thể làm phần lớn byte trong file thay đổi. Khi đó, delta compression có thể không tiết kiệm được nhiều dung lượng. Việc thay thế hoặc xóa file ở commit mới cũng không tự xóa phiên bản cũ khỏi lịch sử.

Bài này thuộc chương **Tệp lớn và LFS** của module **SOURCE_CONTROL_GIT**. Module hướng dẫn Git từ working tree, staging area, commit và lịch sử đến branch, merge, rebase, remote và tag; đồng thời rèn cách cộng tác qua nhánh, giải quyết xung đột, truy tìm thay đổi và khôi phục thao tác sai mà vẫn bảo toàn lịch sử quan trọng. Hiểu nguyên nhân repository tăng nhanh giúp nhóm quyết định dữ liệu nào nên được version hóa trực tiếp, dữ liệu nào nên lưu ở hệ thống quản lý artifact hoặc Git LFS.

## 1. Tệp nhị phân và tệp văn bản khác nhau thế nào?

Tệp văn bản thường được tổ chức thành các dòng ký tự có thể đọc được, chẳng hạn mã nguồn, YAML, JSON, Markdown hoặc file cấu hình. Khi sửa một vài dòng, phần lớn nội dung còn lại thường giữ nguyên. Điều này tạo cơ hội cho Git biểu diễn khác biệt giữa các phiên bản bằng các đoạn thay đổi nhỏ.

Tệp nhị phân lưu dữ liệu theo định dạng mà không thể xử lý đơn giản như văn bản thuần. Ví dụ:

- Ảnh PNG, JPEG, TIFF và file thiết kế đồ họa.
- Video, audio và dữ liệu media.
- File PDF lớn, bản trình chiếu và tài liệu nhị phân.
- Mô hình 3D, CAD, bản vẽ kỹ thuật.
- Dataset, checkpoint và model machine learning.
- File archive, package, installer và binary build.

Một số định dạng nhị phân có cấu trúc nội bộ hoặc nén sẵn. Khi lưu lại sau khi sửa, phần header, bảng chỉ mục, metadata hoặc vị trí dữ liệu có thể thay đổi, khiến nhiều byte khác đi dù người dùng chỉ chỉnh một thành phần nhỏ. Vì thế, Git có thể không tìm được một delta nhỏ tương ứng với thay đổi thực tế.

Không phải mọi file nhị phân đều khó nén delta như nhau. Một số định dạng có cấu trúc ổn định hoặc các phiên bản gần nhau vẫn có thể tạo delta tốt. Vấn đề là hiệu quả phụ thuộc định dạng, cách công cụ tạo file và mức độ thay đổi giữa các phiên bản.

## 2. Git lưu nội dung trong lịch sử như thế nào?

Git quản lý nội dung bằng các đối tượng. Với một file thông thường, nội dung được lưu trong một blob. Một tree mô tả tên file, thư mục và blob tương ứng. Commit trỏ đến tree đại diện cho snapshot của repository tại thời điểm commit.

Ví dụ:

~~~text
Commit A
  |
  +-- Tree A
       |
       +-- src/app.java
       +-- assets/design.bin  --> Blob X

Commit B
  |
  +-- Tree B
       |
       +-- src/app.java
       +-- assets/design.bin  --> Blob Y
~~~

Nếu nội dung của <code>assets/design.bin</code> thay đổi, snapshot mới sẽ tham chiếu đến blob đại diện cho nội dung mới. Commit cũ vẫn tham chiếu đến snapshot cũ. Đây là cách Git giữ khả năng checkout và so sánh lịch sử.

Git sử dụng hash nội dung để định danh object. Nếu hai đường dẫn hoặc hai commit dùng cùng nội dung file, Git có thể tái sử dụng cùng blob thay vì lưu một bản giống hệt khác. Nhưng nếu nội dung thay đổi, hash thường thay đổi và Git cần lưu object tương ứng với phiên bản mới.

Điều này giải thích vì sao một file lớn được commit nhiều lần có thể làm repository tăng nhanh: mỗi phiên bản nội dung khác nhau phải được giữ lại nếu commit chứa phiên bản đó vẫn thuộc lịch sử cần bảo toàn.

## 3. Git có lưu nguyên vẹn mọi phiên bản file không?

Về mặt mô hình lịch sử, mỗi commit trỏ đến snapshot riêng và các phiên bản nội dung phải có thể được khôi phục. Tuy nhiên, khi Git đóng gói object vào packfile, Git có thể dùng compression và delta compression để lưu object hiệu quả hơn.

Delta compression lưu một object dưới dạng khác biệt so với một object khác thay vì giữ toàn bộ nội dung độc lập. Nếu hai phiên bản file gần nhau, delta có thể nhỏ. Điều này thường hiệu quả với nhiều thay đổi văn bản vì phần lớn dòng không đổi.

Với file nhị phân:

- File được nén sẵn như JPEG, MP4 hoặc ZIP có thể ít dư địa để nén thêm.
- Một thay đổi nhỏ có thể làm thay đổi nhiều vùng byte do thuật toán mã hóa hoặc nén nội bộ.
- Công cụ xuất file có thể ghi lại metadata, thứ tự chunk hoặc cấu trúc chỉ mục, khiến nội dung khác biệt lớn.
- Một số file có tính chất ngẫu nhiên hoặc dữ liệu phân tán nên hai phiên bản gần nhau về ý nghĩa nhưng không gần nhau ở mức byte.

Vì vậy, Git có thể phải lưu delta lớn hoặc lưu object gần như toàn bộ. Không nên hiểu rằng mỗi commit luôn tạo thêm một bản sao nguyên vẹn, nhưng cũng không nên giả định Git sẽ nén được mọi phiên bản nhị phân thành một thay đổi rất nhỏ.

### Minh họa tăng dung lượng

Giả sử một nhóm quản lý file thiết kế 120 MB và giữ 15 phiên bản khác nhau. Nếu các phiên bản không thể delta-compress hiệu quả, phần dữ liệu lưu trong lịch sử có thể tiến gần tổng kích thước của các phiên bản được giữ lại, tức khoảng 1,8 GB trước khi tính overhead và các dữ liệu khác.

Nếu các phiên bản có nhiều vùng byte giống nhau và Git nén delta tốt, mức tăng thực tế có thể thấp hơn đáng kể. Nhưng với file nén hoặc file được công cụ xuất lại toàn bộ, mức tăng có thể gần với tổng các phiên bản.

<escape>Ví dụ minh họa, không phải dự báo chính xác cho mọi định dạng:</escape>

| Số phiên bản được giữ | Kích thước mỗi phiên bản | Trường hợp gần như không delta |
|---:|---:|---:|
| 1 | 120 MB | 120 MB |
| 3 | 120 MB | 360 MB |
| 8 | 120 MB | 960 MB |
| 15 | 120 MB | 1.800 MB |

Dung lượng thật của packfile phụ thuộc mức độ giống nhau giữa các phiên bản, compression, cấu hình Git và lịch sử object. Bảng chỉ cho thấy vì sao một file lớn được commit lặp lại có thể trở thành chi phí dài hạn.

## 4. Vì sao xóa file không làm repository nhỏ lại ngay?

Giả sử bạn commit file <code>assets/video-demo.mp4</code> ở commit A, rồi xóa file đó trong commit B:

~~~text
A: add assets/video-demo.mp4
|
B: delete assets/video-demo.mp4
~~~

Ở snapshot của commit B, đường dẫn file không còn tồn tại. Nhưng commit A vẫn giữ snapshot có file đó. Nếu commit A còn nằm trong lịch sử reachable từ nhánh, tag hoặc ref khác, Git vẫn phải giữ blob để có thể checkout commit A.

Lệnh:

~~~bash
git rm assets/video-demo.mp4
git commit -m "chore: remove demo video"
~~~

chỉ loại file khỏi snapshot hiện tại và các commit tiếp theo. Nó không xóa blob khỏi các commit trước đó.

Tương tự, thêm file lớn vào <code>.gitignore</code> chỉ ngăn những file chưa được theo dõi phù hợp với mẫu được đề xuất trong tương lai. Nó không loại bỏ file đã commit và không làm lịch sử cũ nhẹ đi.

### Git gc có tự xóa file lớn cũ không?

Garbage collection có thể dọn các object không còn được tham chiếu sau khi các điều kiện hết hạn phù hợp. Nhưng nếu commit chứa file lớn vẫn reachable từ nhánh, tag hoặc ref khác, blob vẫn cần được giữ lại.

Vì vậy, chạy:

~~~bash
git gc
~~~

không phải giải pháp để xóa file lớn khỏi lịch sử còn được tham chiếu. Muốn loại bỏ blob khỏi toàn bộ lịch sử, nhóm phải viết lại lịch sử bằng công cụ phù hợp và phối hợp cập nhật mọi bản clone liên quan.

## 5. Hệ quả của repository chứa nhiều file lớn

Repository lớn ảnh hưởng đến nhiều khâu hơn là dung lượng thư mục làm việc.

### Clone và fetch tốn thời gian

Khi clone một repository, Git cần tải các object cần thiết theo phạm vi lịch sử và tùy chọn clone. Nếu packfile lớn, quá trình truyền dữ liệu, giải nén và ghi object sẽ lâu hơn. Fetch cũng có thể phải tải thêm object lớn khi lịch sử mới chứa phiên bản file mới.

### CI/CD chậm và tốn tài nguyên

Pipeline thường checkout repository trong nhiều job hoặc nhiều môi trường. Repository lớn làm tăng thời gian khởi tạo job, băng thông, dung lượng cache và chi phí lưu trữ. Khi runner tạo clone mới thường xuyên, tác động tích lũy rõ rệt hơn.

### Mỗi thành viên cần nhiều dung lượng

Các bản clone có thể chứa lịch sử object lớn. Người dùng cần dung lượng cho object database, working tree, file build và cache. Với laptop hoặc môi trường phát triển có dung lượng hạn chế, việc clone repository lớn có thể trở thành trở ngại.

### Backup, mirror và chuyển repository nặng hơn

Hệ thống backup hoặc mirror cần giữ object database và refs. Khi lịch sử phình to, thời gian sao lưu, truyền bản mirror và phục hồi repository cũng tăng.

### Xóa file trong phiên bản mới không giải quyết chi phí lịch sử

Ngay cả khi working tree hiện tại chỉ còn mã nguồn nhỏ, object database có thể vẫn lớn vì các commit cũ giữ file nhị phân. Kích thước thư mục hiện tại và kích thước lịch sử Git là hai đại lượng khác nhau.

## 6. Phân biệt kích thước working tree và object database

Kích thước thư mục dự án nhìn thấy trong File Explorer không cho biết toàn bộ chi phí lưu lịch sử. Có thể có hai tình huống:

- Working tree hiện tại lớn vì chứa dataset hoặc output cần cho lần chạy hiện tại.
- Working tree nhỏ nhưng thư mục Git lớn vì lịch sử chứa nhiều phiên bản file đã xóa khỏi snapshot hiện tại.

Để kiểm tra sơ bộ:

~~~bash
# Dung lượng object database dạng dễ đọc
git count-objects -vH

# Kích thước các file trong snapshot hiện tại
git ls-tree -r -l HEAD

# Dung lượng thư mục làm việc do hệ điều hành báo cáo
# Dùng công cụ dung lượng của hệ điều hành tại thư mục dự án
~~~

<code>git count-objects -vH</code> cho biết số object loose, dung lượng loose object, số pack và kích thước pack. Đây là thông tin tổng quan về object database, không trực tiếp cho biết file nào đóng góp nhiều nhất.

<code>git ls-tree -r -l HEAD</code> liệt kê các blob trong snapshot hiện tại cùng kích thước nội dung logic của blob, không phải dung lượng packfile thực tế. Lệnh này không tìm được mọi file lớn đã bị xóa trong lịch sử. Để kiểm tra lịch sử, cần duyệt object reachable từ các refs.

## 7. Tìm các blob lớn trong lịch sử

Một cách chẩn đoán là liệt kê object có thể truy cập từ các refs rồi lấy kích thước blob. Ví dụ trong Bash:

~~~bash
git rev-list --objects --all |
  git cat-file --batch-check='%(objecttype) %(objectname) %(objectsize) %(rest)' |
  awk '$1 == "blob" { print $3, $2, $4 }' |
  sort -nr |
  head -20
~~~

Kết quả cho biết các blob lớn theo kích thước object, kèm hash và đường dẫn nếu Git có thể cung cấp. Một blob có thể được dùng bởi nhiều commit hoặc nhiều đường dẫn; danh sách này giúp tìm ứng viên cần xem xét, không tự quyết định có thể xóa hay không.

Trên Windows PowerShell, có thể lấy dữ liệu tương tự rồi sắp xếp:

~~~powershell
git rev-list --objects --all |
  git cat-file --batch-check='%(objecttype) %(objectname) %(objectsize) %(rest)' |
  ForEach-Object {
    $parts = $_ -split ' ', 4
    if ($parts.Count -ge 3 -and $parts[0] -eq 'blob') {
      [PSCustomObject]@{
        Bytes = [int64]$parts[2]
        Object = $parts[1]
        Path = if ($parts.Count -eq 4) { $parts[3] } else { '' }
      }
    }
  } |
  Sort-Object Bytes -Descending |
  Select-Object -First 20
~~~

Để xem chi tiết một blob:

~~~bash
git cat-file -s <object-hash>
git cat-file -t <object-hash>
~~~

Lệnh đầu in kích thước object theo byte; lệnh sau xác nhận loại object. Nếu muốn xem nội dung nhị phân, tránh in trực tiếp ra terminal vì dữ liệu có thể không đọc được. Có thể trích xuất vào file tạm trong môi trường kiểm tra phù hợp.

### Xem dung lượng packfile

Trong repository dùng packfile, có thể kiểm tra:

~~~bash
git count-objects -vH
~~~

Các trường thường gặp:

- <code>count</code>: số object loose.
- <code>size</code>: dung lượng loose object; với tùy chọn <code>-H</code>, Git hiển thị theo đơn vị dễ đọc.
- <code>in-pack</code>: số object đã đóng gói.
- <code>packs</code>: số packfile.
- <code>size-pack</code>: tổng dung lượng packfile; với tùy chọn <code>-H</code>, Git hiển thị theo đơn vị dễ đọc.
- <code>prune-packable</code>: object loose đã có bản trong pack.
- <code>garbage</code> và <code>size-garbage</code>: file không hợp lệ mà Git nhận diện trong object directory.

Nếu cần phân tích sâu packfile, có thể dùng <code>git verify-pack -v</code> với file index của pack. Đường dẫn và wildcard khác nhau giữa Bash và PowerShell; hãy xác định pack index trong thư mục object của repository trước khi chạy.

## 8. Quyết định loại tệp nào nên đưa vào Git

Không phải cứ file lớn là phải loại khỏi Git. Một số binary nhỏ hoặc tài sản ít thay đổi vẫn phù hợp để version hóa trực tiếp. Quyết định nên dựa trên kích thước, tần suất thay đổi, mức độ cần review, khả năng tái tạo và nhu cầu truy cập lịch sử.

| Loại dữ liệu | Cách lưu thường phù hợp | Lý do |
|---|---|---|
| Mã nguồn và cấu hình văn bản | Git thông thường | Diff rõ, lịch sử dễ review |
| Icon nhỏ, ảnh minh họa ít thay đổi | Git thông thường | Kích thước và số phiên bản thường kiểm soát được |
| File thiết kế lớn, thay đổi thường xuyên | Cân nhắc Git LFS | Giữ pointer trong Git, lưu nội dung lớn qua LFS |
| Video, audio hoặc model lớn | Git LFS hoặc artifact storage | Tránh làm object database phình theo mọi phiên bản |
| Dataset lớn, có thể tái tạo hoặc tải lại | Object storage / data platform | Không nhất thiết cần nằm trong lịch sử mã nguồn |
| Build output, package được sinh ra | Artifact registry hoặc CI artifact | Có thể tái tạo từ source và pipeline |
| File tạm, cache, log local | <code>.gitignore</code> | Không phải đầu vào cần version hóa |

Một câu hỏi hữu ích là: nếu một thành viên checkout commit cách đây hai năm, họ có thật sự cần đúng phiên bản file này để tái tạo trạng thái dự án không? Nếu có, cần chọn một cơ chế lưu phiên bản đáng tin cậy. Nếu không, artifact hoặc storage chuyên dụng có thể phù hợp hơn.

## 9. Git LFS giải quyết phần nào?

Git Large File Storage (Git LFS) là phần mở rộng giúp quản lý file lớn bằng cách lưu một file pointer nhỏ trong Git, còn nội dung thực tế được lưu trên máy chủ LFS. Khi checkout, Git LFS tải nội dung tương ứng nếu môi trường có cấu hình và quyền truy cập phù hợp.

Thay vì đưa toàn bộ binary vào blob thông thường trong mỗi phiên bản, Git lưu pointer chứa thông tin nhận dạng object LFS và kích thước. Điều này giúp object database của repository nhẹ hơn và giảm lượng binary phải truyền trong các thao tác Git thông thường.

Ví dụ minh họa nội dung pointer:

~~~text
version https://git-lfs.github.com/spec/v1
oid sha256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef
size 104857600
~~~

Pointer không phải nội dung file thật. Nó cho biết object LFS cần lấy theo mã định danh và kích thước. Nếu máy clone không tải được object LFS, working tree có thể chỉ có pointer thay vì file nhị phân đầy đủ.

### Chuyển sang LFS không tự xóa lịch sử cũ

Nếu file lớn đã được commit trước khi nhóm bật LFS, chỉ thêm quy tắc tracking và commit lại file sẽ không tự xóa các blob cũ trong lịch sử. Các commit cũ vẫn tham chiếu đến binary thông thường.

Để loại các blob cũ khỏi lịch sử, cần một quy trình migration viết lại lịch sử, kiểm tra kết quả, cập nhật remote và phối hợp với mọi người đang có bản clone. Việc này ảnh hưởng hash commit và các nhánh dựa trên lịch sử cũ. Nội dung migration cụ thể cần được lên kế hoạch riêng, có backup và hướng dẫn đồng bộ lại bản clone.

## 10. Phòng tránh repository phình to ngay từ đầu

Các biện pháp phòng ngừa hiệu quả nhất thường được áp dụng trước khi commit file lớn:

1. Thống nhất giới hạn kích thước file và loại dữ liệu được phép đưa vào repository.
2. Thêm quy tắc <code>.gitignore</code> cho file build, cache, log và output có thể tái tạo.
3. Dùng Git LFS cho loại file lớn cần version hóa và có tần suất cập nhật đáng kể.
4. Đưa dataset hoặc artifact sinh ra sang hệ thống lưu trữ phù hợp.
5. Kiểm tra kích thước file trước khi stage hoặc commit.
6. Tích hợp kiểm tra dung lượng vào review hoặc pre-commit hook nếu nhóm cần.
7. Hướng dẫn thành viên cách cài Git LFS và tải object LFS sau khi clone.

Ví dụ, để tìm file lớn trong working tree bằng Bash:

~~~bash
find . -type f -size +50M -not -path './.git/*' -print
~~~

Trong PowerShell:

~~~powershell
Get-ChildItem -File -Recurse |
  Where-Object { $_.Length -gt 50MB -and $_.FullName -notmatch '[\\/]\.git[\\/]' } |
  Sort-Object Length -Descending |
  Select-Object -First 30 FullName, Length
~~~

Đây chỉ là kiểm tra working tree hiện tại. Nó không tìm các file lớn đã bị xóa khỏi snapshot hiện tại nhưng vẫn còn trong lịch sử; dùng cách kiểm tra blob trong phần trước cho trường hợp đó.

## 11. Xử lý khi file lớn đã được commit

Khi phát hiện một file lớn vừa được commit nhưng chưa push, có thể sửa commit trước khi chia sẻ:

~~~bash
# Gỡ file khỏi index nhưng giữ nội dung trong working tree
git rm --cached -- assets/large-model.bin

# Thêm quy tắc phù hợp để không stage nhầm lần sau
# Ví dụ: assets/generated/

# Sửa file .gitignore rồi kiểm tra
git status
git diff --staged
git diff
~~~

Nếu file đã nằm trong commit gần nhất và commit chưa được chia sẻ, bạn có thể sửa commit bằng amend sau khi kiểm tra index:

~~~bash
git add .gitignore
git commit --amend
~~~

Thao tác này tạo commit mới thay commit cũ trên nhánh hiện tại. Chỉ dùng khi commit chưa được người khác dựa vào hoặc nhóm đã thống nhất viết lại lịch sử.

Nếu file lớn đã được push hoặc đã có trong nhánh dùng chung, hãy đánh giá tác động trước khi rewrite. Có thể tạo commit mới để loại file khỏi snapshot hiện tại, nhưng thao tác đó không làm giảm dung lượng lịch sử cũ. Muốn xóa blob khỏi toàn bộ lịch sử, cần viết lại lịch sử bằng công cụ chuyên dụng và phối hợp cập nhật remote cùng mọi bản clone liên quan.

### Vì sao không nên tùy tiện rewrite lịch sử?

Viết lại lịch sử làm thay đổi hash của commit bị tác động và các commit con được tạo lại. Sau khi force push lịch sử mới:

- Nhánh local của thành viên khác có thể vẫn dựa trên commit cũ.
- Pull request, tag, release và pipeline có thể tham chiếu lịch sử trước đó.
- Các bản clone hiện có có thể tiếp tục giữ blob cũ cho đến khi được dọn.
- Việc đồng bộ cần có hướng dẫn cụ thể, thường yêu cầu fetch rồi reset hoặc clone lại theo kế hoạch.

Nếu file chứa bí mật hoặc thông tin xác thực, ngoài việc xử lý lịch sử cần thu hồi hoặc xoay vòng bí mật đó. Xóa blob khỏi Git không làm token đã lộ tự mất hiệu lực.

## 12. Một quy trình đánh giá file trước khi commit

Trước khi thêm tài sản lớn vào repository, nhóm có thể áp dụng checklist:

- File có cần tồn tại trong mọi snapshot lịch sử hay chỉ cần lưu như artifact?
- Kích thước file là bao nhiêu và tần suất cập nhật dự kiến thế nào?
- Định dạng có thể tạo delta tốt hay thường được nén sẵn?
- Người review có cần xem diff nội dung hay chỉ cần biết phiên bản và nguồn gốc?
- Có cần checkout file cũ để tái tạo một bản phát hành không?
- Nếu dùng LFS hoặc object storage, mọi môi trường build có quyền tải dữ liệu không?
- Có chính sách giới hạn kích thước file hoặc quota lưu trữ không?
- File đã được theo dõi trước đây hay đây là lần đầu đưa vào Git?

Ví dụ: một icon SVG nhỏ được sửa vài lần thường phù hợp với Git thông thường vì nội dung văn bản và diff dễ review. Một file video 800 MB được xuất lại mỗi tuần thường không phù hợp để lưu trực tiếp trong lịch sử Git thông thường. Nếu cần giữ từng phiên bản, LFS hoặc artifact storage là lựa chọn cần đánh giá.

## 13. Những hiểu lầm thường gặp

| Hiểu lầm | Cách hiểu chính xác |
|---|---|
| Git luôn lưu nguyên một bản đầy đủ cho mọi phiên bản | Git có thể dùng delta compression trong packfile; mức tiết kiệm tùy nội dung |
| Binary thay đổi một chút thì delta chắc chắn nhỏ | File nén hoặc cấu trúc nhị phân thay đổi nhiều byte có thể tạo delta lớn |
| Xóa file ở commit mới làm repository nhỏ ngay | Commit cũ vẫn tham chiếu đến blob; lịch sử vẫn cần giữ nội dung đó |
| Thêm file vào <code>.gitignore</code> sẽ xóa bản đã commit | Ignore không bỏ theo dõi file đã tracked và không sửa lịch sử |
| Chạy <code>git gc</code> sẽ xóa tất cả binary cũ | Object còn reachable từ refs vẫn phải được giữ |
| Git LFS tự động di chuyển các commit cũ | LFS cần migration nếu muốn thay blob cũ trong lịch sử bằng pointer |
| Kích thước thư mục dự án bằng kích thước lịch sử | Working tree và object database là hai phần khác nhau |
| Clone nông giải quyết mọi vấn đề file lớn | Shallow clone giới hạn lịch sử được tải, nhưng không thay thế chiến lược quản lý binary lâu dài |

## 14. Bài tập tự kiểm tra

Thực hành trong một repository thử nghiệm:

1. Tạo một file văn bản và một file nhị phân lớn, commit cả hai.
2. Thay đổi vài dòng trong file văn bản rồi commit phiên bản mới.
3. Thay đổi file nhị phân bằng công cụ phù hợp, commit lại và so sánh mức tăng dung lượng object database.
4. Chạy <code>git count-objects -vH</code> trước và sau khi tạo các commit.
5. Xóa file nhị phân ở commit mới, sau đó kiểm tra vì sao object database không giảm ngay.
6. Dùng <code>git rev-list --objects --all</code> kết hợp <code>git cat-file --batch-check</code> để tìm blob lớn trong lịch sử.
7. Thêm quy tắc ignore cho một file mới và xác nhận file đã tracked không tự ngừng được theo dõi.
8. Tạo một repository thử nghiệm khác để quan sát pointer của Git LFS và phân biệt pointer với nội dung binary.
9. Giải thích vì sao migration sang LFS cần xử lý lịch sử cũ nếu mục tiêu là giảm kích thước repository hiện hữu.

Khi hiểu cách snapshot, blob và packfile phối hợp với nhau, bạn có thể giải thích vì sao repository tăng dung lượng dù working tree hiện tại nhỏ. Hãy đánh giá kích thước và tần suất thay đổi trước khi commit binary, dùng ignore cho file không cần version hóa và chọn LFS hoặc artifact storage khi dữ liệu lớn cần được quản lý lâu dài.
