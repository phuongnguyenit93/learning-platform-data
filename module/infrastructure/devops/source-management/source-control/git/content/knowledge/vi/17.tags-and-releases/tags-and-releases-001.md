# Tag là tham chiếu cố định theo quy ước, khác với nhánh

Trong Git, branch và tag đều là tham chiếu có tên trỏ đến một đối tượng trong repository, thường là một commit khi quản lý mã nguồn. Tuy nhiên, chúng phục vụ những mục đích khác nhau. Branch là con trỏ di động được cập nhật khi có commit mới; tag thường được dùng để đánh dấu một mốc có ý nghĩa như phiên bản phát hành và được giữ nguyên sau khi tạo.

Điểm cần hiểu chính xác là Git không tự biến tag thành bất biến. Tag được xem là mốc cố định theo quy ước làm việc của nhóm. Người có quyền phù hợp vẫn có thể xóa hoặc di chuyển tag. Vì vậy, quy trình phát hành nên bảo vệ tag trên máy chủ, xác minh commit đích và ghi nhận thông tin phát hành để mọi người có thể tin cậy cùng một mốc.

## 1. Tag là gì?

Tag là một tham chiếu có tên trong repository, thường dùng để đánh dấu một commit quan trọng. Ví dụ:

- v1.0.0: phiên bản đầu tiên được phát hành.
- v1.1.0: phiên bản bổ sung tính năng tương thích.
- v1.1.1: phiên bản sửa lỗi.
- v2.0.0: phiên bản có thay đổi lớn hoặc không tương thích.

Khi tạo tag v1.1.0 tại commit A, tên tag tiếp tục trỏ tới commit A ngay cả khi branch main có thêm commit B, C hoặc D. Nhờ đó, nhóm có thể tìm lại chính xác mốc mã nguồn đã được gắn nhãn phiên bản.

Ví dụ:

~~~text
A---B---C---D  main
 \
  v1.0.0
~~~

Sau khi main tiến thêm commit:

~~~text
A---B---C---D---E---F  main
 \
  v1.0.0
~~~

Tag v1.0.0 vẫn trỏ tới A. Branch main di chuyển từ commit này sang commit khác khi có commit mới, còn tag giữ nguyên mốc đã đánh dấu theo quy ước.

Tag thường được dùng cho:

- Đánh dấu phiên bản phát hành.
- Ghi nhận mốc bàn giao hoặc mốc ổn định.
- Tạo đầu vào xác định cho pipeline build và deploy.
- Đối chiếu mã nguồn của một bản phát hành khi điều tra lỗi.
- Xác minh nguồn gốc bằng chữ ký tag trong quy trình bảo mật.

Tag không chứa toàn bộ gói cài đặt hay artifact đã build. Nó đánh dấu một đối tượng trong lịch sử Git; artifact, release note và các tài sản phát hành thường được quản lý bởi hệ thống khác.

## 2. Tag và branch khác nhau như thế nào?

Branch và tag đều là ref, nhưng cách sử dụng khác nhau:

| Tiêu chí | Branch | Tag |
|---|---|---|
| Mục đích | Theo dõi một dòng phát triển | Đánh dấu một mốc cụ thể |
| Khi tạo commit mới trên nhánh | Ref branch thường được di chuyển tới commit mới | Tag không tự di chuyển |
| Cách dùng thường gặp | Phát triển tính năng, sửa lỗi, bảo trì phiên bản | Đánh dấu release, mốc ổn định, mốc kiểm thử |
| Tên ref lưu trong Git | refs/heads/ | refs/tags/ |
| Có thể xóa hoặc di chuyển không? | Có | Có, nhưng nên tránh với tag đã công bố |
| Thông lệ cộng tác | Thường xuyên cập nhật | Giữ nguyên sau khi phát hành |

Hình dung đơn giản: branch giống như con trỏ theo dõi nơi công việc đang tiếp tục; tag giống như nhãn gắn vào một mốc lịch sử mà nhóm muốn tham chiếu lại.

### 2.1. Branch là tham chiếu di động

Khi đang ở branch main và tạo commit mới:

~~~
git switch main
git commit -m "Add order search"
~~~

Git cập nhật ref main để trỏ tới commit mới. Commit trước vẫn tồn tại trong lịch sử, nhưng branch đã tiến lên.

### 2.2. Tag không tự tiến theo branch

Tạo tag tại commit hiện tại:

~~~
git tag v1.0.0
~~~

Tag v1.0.0 trỏ đến commit mà HEAD đang chỉ tới tại thời điểm tạo. Khi main có commit tiếp theo, tag vẫn giữ nguyên vị trí. Nếu muốn đánh dấu phiên bản mới, tạo tag mới:

~~~
git tag v1.1.0
~~~

Không nên dùng một tag phiên bản đã công bố để đại diện cho nhiều commit khác nhau. Việc di chuyển tag cũ làm cho cùng một tên phiên bản có thể trỏ tới nội dung khác nhau trên các máy hoặc hệ thống build.

## 3. Lightweight tag và annotated tag

Git có hai dạng tag phổ biến: lightweight tag và annotated tag.

### 3.1. Lightweight tag

Lightweight tag là một ref đơn giản trỏ trực tiếp tới đối tượng được đánh dấu. Khi dùng cho commit, nó trỏ thẳng tới commit đó. Nó không tạo thêm một tag object chứa metadata riêng.

Tạo lightweight tag:

~~~
git tag v1.2.0
~~~

Hoặc chỉ định commit cụ thể:

~~~
git tag v1.2.0 3f2a9c1
~~~

Lightweight tag hữu ích khi cần đánh dấu tạm thời, mốc nội bộ hoặc một điểm kiểm tra không yêu cầu metadata phát hành. Tuy nhiên, nó không lưu người tạo tag, thời điểm tạo, thông điệp tag hay chữ ký tag.

### 3.2. Annotated tag

Annotated tag tạo một tag object riêng. Object này lưu thông tin tagger, thời điểm, thông điệp và đối tượng được tag. Đây là dạng thường phù hợp để đánh dấu phiên bản phát hành.

Tạo annotated tag:

~~~
git tag -a v1.2.0 -m "Release version 1.2.0"
~~~

Chỉ định commit rõ ràng:

~~~
git tag -a v1.2.0 3f2a9c1 -m "Release version 1.2.0"
~~~

Annotated tag giúp lưu lý do và thông tin của mốc phát hành ngay trong Git. Có thể xem nội dung:

~~~
git show v1.2.0
~~~

Với annotated tag, git show thường hiển thị thông tin tagger, ngày tạo, thông điệp và commit được đánh dấu. Với lightweight tag, git show hiển thị nội dung commit mà tag trỏ tới.

### 3.3. So sánh hai dạng tag

| Tiêu chí | Lightweight | Annotated |
|---|---|---|
| Cấu trúc | Ref trỏ trực tiếp tới object | Ref trỏ tới tag object |
| Người tạo và thời điểm tag | Không có metadata tag riêng | Có |
| Thông điệp tag | Không | Có |
| Chữ ký tag | Không có chữ ký tag riêng | Có thể ký |
| Phù hợp | Mốc tạm hoặc nội bộ | Phiên bản phát hành và mốc cần truy vết |

Khi tạo release chính thức, nên ưu tiên annotated tag để có thông tin phát hành và khả năng ký xác minh. Lightweight tag vẫn có thể hữu ích trong công việc hằng ngày, nhưng không cung cấp metadata tương đương.

## 4. Đặt tên tag và quy ước phiên bản

Tên tag là chuỗi do nhóm quy định. Git không bắt buộc tag phải theo Semantic Versioning, nhưng nhiều dự án dùng SemVer để truyền đạt mức độ thay đổi.

### 4.1. Semantic Versioning

Một phiên bản SemVer cơ bản có dạng:

~~~text
MAJOR.MINOR.PATCH
~~~

- **MAJOR:** Tăng khi có thay đổi không tương thích với API hoặc hành vi công khai trước đó.
- **MINOR:** Tăng khi bổ sung chức năng tương thích ngược.
- **PATCH:** Tăng khi sửa lỗi tương thích ngược.

Ví dụ:

| Phiên bản | Ý nghĩa minh họa |
|---|---|
| 1.0.0 | Mốc phát hành ổn định đầu tiên |
| 1.1.0 | Thêm tính năng tương thích |
| 1.1.1 | Sửa lỗi, giữ tương thích |
| 2.0.0 | Thay đổi lớn có thể yêu cầu người dùng cập nhật cách tích hợp |

SemVer là quy ước về ý nghĩa phiên bản. Git chỉ lưu tên tag và đối tượng mà tag trỏ tới; Git không tự kiểm tra việc tăng MAJOR, MINOR hoặc PATCH có đúng với thay đổi hay không.

### 4.2. Phiên bản tiền phát hành

SemVer hỗ trợ nhãn pre-release sau dấu gạch ngang:

~~~text
2.0.0-alpha.1
2.0.0-beta.1
2.0.0-rc.1
~~~

Các nhãn này thường dùng trong giai đoạn thử nghiệm:

- alpha: phiên bản sớm, tính năng hoặc giao diện có thể còn thay đổi.
- beta: phiên bản đã có phạm vi rộng hơn để kiểm thử.
- rc: release candidate, ứng viên phát hành nếu không còn lỗi nghiêm trọng.

Đây là cách diễn giải phổ biến của dự án; ý nghĩa cụ thể và tiêu chí chuyển giai đoạn cần được nhóm thống nhất. Phiên bản tiền phát hành có thứ tự ưu tiên thấp hơn phiên bản ổn định tương ứng, ví dụ 2.0.0-rc.1 đứng trước 2.0.0 theo quy tắc SemVer.

### 4.3. Chọn quy ước đặt tên nhất quán

Một số dự án đặt tên tag có tiền tố v:

~~~text
v1.0.0
v1.1.0
v1.1.1
~~~

Một số dự án dùng trực tiếp:

~~~text
1.0.0
1.1.0
1.1.1
~~~

Cả hai đều có thể dùng trong Git. Điều quan trọng là chọn một quy ước thống nhất để script, pipeline, tài liệu và người dùng không phải đoán tên phiên bản.

## 5. Tạo, xem và tìm tag

### 5.1. Liệt kê tag

Xem toàn bộ tag:

~~~
git tag
~~~

Lọc theo mẫu:

~~~
git tag -l "v1.*"
~~~

Sắp xếp theo phiên bản:

~~~
git tag --sort=-version:refname
~~~

Sắp xếp phiên bản hữu ích hơn sắp xếp từ điển thông thường. Ví dụ, thứ tự từ điển có thể đặt v1.10.0 trước v1.2.0 do so sánh ký tự; version sort hiểu các thành phần số của phiên bản.

### 5.2. Xem tag trỏ tới đâu

Xem nội dung tag và commit:

~~~
git show v1.2.0
~~~

Lấy commit SHA mà tag phân giải tới:

~~~
git rev-parse "v1.2.0^{commit}"
~~~

Cú pháp ^{commit} yêu cầu Git phân giải tag tới commit được tag, kể cả khi tag là annotated tag trỏ qua tag object.

Có thể xem loại object và object được tag:

~~~
git cat-file -t v1.2.0
git cat-file -p v1.2.0
~~~

Với lightweight tag, lệnh đầu thường trả về commit. Với annotated tag, nó trả về tag và lệnh thứ hai hiển thị metadata của tag object cùng object đích.

### 5.3. Tìm tag gần nhất từ một commit

Lệnh git describe giúp đặt tên dễ đọc cho commit dựa trên tag gần nhất trong lịch sử:

~~~
git describe --tags
git describe --tags --always
~~~

Nếu commit hiện tại đúng tại một tag, kết quả có thể là tên tag. Nếu có commit mới hơn tag gần nhất, kết quả thường có dạng tên tag, số commit phía sau và một phần mã SHA.

git describe hữu ích để hiển thị phiên bản phát triển trong ứng dụng hoặc log build. Nó phụ thuộc vào tag có thể truy cập trong repository và không phải nguồn duy nhất để xác định artifact production. Pipeline vẫn nên ghi commit SHA cụ thể.

## 6. Tag có thể được tạo tại commit nào?

Nếu không chỉ định commit, lệnh git tag thường dùng HEAD. Nhưng trong quy trình phát hành, nên xác định rõ commit cần đánh dấu.

Ví dụ xem lịch sử:

~~~
git log --oneline --decorate -8
~~~

Tạo tag annotated tại commit đã chọn:

~~~
git tag -a v1.4.0 8d3c2f1 -m "Release version 1.4.0"
~~~

Kiểm tra lại:

~~~
git show --no-patch --decorate v1.4.0
git rev-parse "v1.4.0^{commit}"
~~~

Tag nên trỏ tới commit đại diện cho nội dung thực sự được phát hành. Không nên tạo tag trên một working tree còn thay đổi chưa commit rồi cho rằng tag đã bao gồm các thay đổi đó. Tag đánh dấu object trong lịch sử, không đánh dấu trạng thái tệp chưa được commit.

Một quy trình release thường tạo tag sau khi thay đổi đã được review và tích hợp vào branch phát hành hoặc branch chính. Nếu nhóm tạo tag trên commit merge, hãy chắc chắn đó là commit đã được kiểm thử và đủ điều kiện phát hành.

## 7. Chia sẻ tag với remote

Tag mới tạo ở local chưa tự xuất hiện trên remote. Cần push tag để các thành viên và pipeline khác có thể truy cập.

### 7.1. Push một tag cụ thể

~~~
git push origin v1.4.0
~~~

Đây là cách rõ ràng khi chỉ muốn công bố một tag. Có thể dùng ref đầy đủ:

~~~
git push origin refs/tags/v1.4.0
~~~

### 7.2. Push tất cả tag

~~~
git push origin --tags
~~~

Lệnh này yêu cầu đẩy tất cả tag local lên remote. Nếu remote đã có cùng tên tag nhưng trỏ tới object khác, việc cập nhật có thể bị từ chối. Chỉ dùng khi bạn đã xem danh sách tag và chắc chắn mọi tag đó đều được phép chia sẻ. Trong nhóm lớn, push tag cụ thể thường dễ kiểm soát hơn.

### 7.3. Push annotated tag có thể được tự động theo sau

~~~
git push --follow-tags
~~~

Tùy chọn --follow-tags đẩy các annotated tag còn thiếu trên remote mà trỏ tới commit có thể được đẩy theo lần push đó. Nó không có nghĩa là đẩy mọi lightweight tag. Hãy hiểu khác biệt này khi thiết kế script release.

### 7.4. Kiểm tra tag trên remote

Liệt kê tag mà remote quảng bá:

~~~
git ls-remote --tags origin
~~~

Có thể lọc theo một tên cụ thể trong shell:

~~~
git ls-remote --tags origin "refs/tags/v1.4.0*"
~~~

Đối với annotated tag, remote có thể hiển thị cả ref tag object và ref peeled kết thúc bằng ^{} trỏ tới object được tag. Điều này là bình thường: tag object và commit đích có SHA khác nhau.

Sau khi push, một máy khác có thể lấy tag qua fetch:

~~~
git fetch origin --tags
~~~

Git thường tự động lấy tag liên quan đến các commit được fetch theo cấu hình mặc định, nhưng --tags yêu cầu lấy toàn bộ tag mà remote công bố. Dùng lệnh này khi cần đồng bộ danh sách tag đầy đủ.

## 8. Xóa hoặc di chuyển tag

Git cho phép sửa tag, nhưng tag đã công bố nên được xem là mốc lịch sử cần giữ nguyên. Thay đổi tag phát hành có thể khiến hai người cùng dùng tên v1.4.0 nhưng thực tế build từ hai commit khác nhau.

### 8.1. Xóa tag local

~~~
git tag -d v1.4.0
~~~

Lệnh này xóa ref tag trong repository local. Nó không tự xóa tag trên remote và cũng không nhất thiết xóa ngay các object mà tag từng trỏ tới.

### 8.2. Xóa tag trên remote

~~~
git push origin --delete v1.4.0
~~~

Thao tác này xóa tag trên remote. Những người đã fetch tag có thể vẫn giữ tag local. Cần thông báo rõ và hướng dẫn đồng bộ nếu việc xóa là một phần của quy trình sửa sai.

### 8.3. Di chuyển tag local

Có thể buộc tạo lại tag:

~~~
git tag -f -a v1.4.0 <new-commit> -m "Release version 1.4.0"
~~~

Lệnh trên thay đổi tag local. Nếu tag cũ đã được công bố, không nên dùng cách này như một thao tác sửa nhanh mà không phối hợp. Việc đẩy tag đã di chuyển lên remote thường bị từ chối vì cập nhật không phải fast-forward.

### 8.4. Cập nhật tag đã tồn tại trên remote

Trong trường hợp đặc biệt, người quản trị có thể xóa tag cũ trên remote rồi push tag mới, hoặc dùng force update theo chính sách của máy chủ. Đây là thao tác có ảnh hưởng tới mọi người đang dựa vào tag đó.

Nếu phát hành có lỗi, thông thường nên tạo phiên bản mới, ví dụ v1.4.1, thay vì di chuyển v1.4.0 đã công bố. Cách này giữ lịch sử phát hành minh bạch và giúp hệ thống build, người dùng, bản sao repository và tài liệu không bị hiểu khác nhau về cùng một tên tag.

## 9. Tag có chữ ký và xác minh nguồn gốc

Tag annotated có thể được ký bằng khóa GPG hoặc cơ chế ký được Git hỗ trợ. Chữ ký giúp người nhận xác minh tag được ký bởi khóa mà họ tin cậy và nội dung tag object không bị thay đổi sau khi ký.

### 9.1. Tạo signed tag

~~~
git tag -s v1.5.0 -m "Release version 1.5.0"
~~~

Nếu cần chọn khóa ký cụ thể:

~~~
git tag -u <key-id> v1.5.0 -m "Release version 1.5.0"
~~~

Khóa riêng phải được bảo vệ và chỉ người hoặc hệ thống được ủy quyền mới có quyền sử dụng. Không đưa private key vào repository.

### 9.2. Xác minh chữ ký

~~~
git tag -v v1.5.0
~~~

Git kiểm tra chữ ký theo cơ chế ký đã cấu hình và hiển thị kết quả xác minh. Để kết luận tag đáng tin, người nhận còn cần biết khóa công khai thuộc về ai và khóa đó có nằm trong danh sách tin cậy của tổ chức hay không. Một chữ ký hợp lệ từ khóa không đáng tin không tự chứng minh người phát hành được ủy quyền.

### 9.3. Chữ ký tag và bảo vệ tag trên máy chủ

Chữ ký xác minh nội dung tag object và danh tính khóa ký theo trust configuration. Nó không tự ngăn người có quyền xóa tag hoặc tạo một tag khác cùng tên trên remote. Nên kết hợp:

- Quy tắc bảo vệ tag phát hành trên máy chủ.
- Giới hạn quyền tạo, xóa hoặc cập nhật tag.
- Quy trình phê duyệt release.
- Chữ ký tag và kiểm tra khóa tin cậy.
- Ghi lại commit SHA và checksum artifact.

Đối với release quan trọng, pipeline có thể xác minh chữ ký trước khi build hoặc deploy. Điều này giúp kiểm tra rằng đầu vào release là mốc đã được ký bởi khóa được phép.

## 10. Tag và Release khác nhau như thế nào?

Tag là khái niệm của Git. Release thường là đối tượng do nền tảng lưu trữ hoặc quy trình phát hành cung cấp, gắn với một tag và có thể bao gồm nhiều thông tin bổ sung.

| Thành phần | Vai trò |
|---|---|
| Git tag | Đánh dấu commit hoặc object trong repository |
| Release note | Mô tả tính năng, sửa lỗi, thay đổi không tương thích và hướng dẫn nâng cấp |
| Artifact | Gói build, binary, container image hoặc file cài đặt |
| Checksum | Giúp kiểm tra tính toàn vẹn của artifact |
| Chữ ký | Giúp xác minh nguồn gốc và tính toàn vẹn theo khóa tin cậy |
| Release trên nền tảng | Kết hợp tag với mô tả, file đính kèm, thời điểm và thông tin phát hành |

Tạo tag không tự build ứng dụng, không tự tạo release note và không tự upload artifact. Các bước này cần pipeline hoặc nền tảng release.

Một release có thể chứa:

- Tên phiên bản và tag tương ứng.
- Ngày phát hành và ghi chú phát hành.
- Artifact hoặc link tới container image.
- Checksum hoặc chữ ký artifact.
- Hướng dẫn cài đặt, nâng cấp và rollback.
- Danh sách thay đổi hoặc issue đã đóng.

## 11. Quy trình tạo tag và phát hành

Một quy trình release có kiểm soát có thể gồm:

1. **Chốt phạm vi:** Xác định tính năng, lỗi đã sửa và các thay đổi sẽ được phát hành.
2. **Chuẩn bị commit:** Tích hợp các thay đổi đã review vào branch phát hành hoặc branch chính.
3. **Kiểm tra:** Chạy test, kiểm tra bảo mật, build thử và xác nhận tương thích.
4. **Chọn commit:** Ghi lại commit SHA chính xác sẽ được phát hành.
5. **Tạo tag:** Tạo annotated hoặc signed tag theo chính sách, dùng tên phiên bản đã thống nhất.
6. **Xác minh:** Dùng git show, git rev-parse và git tag -v nếu có chữ ký để xác nhận tag trỏ đúng commit.
7. **Push tag:** Công bố tag cụ thể lên remote.
8. **Build artifact:** Pipeline build từ commit được tag, lưu checksum và thông tin truy vết.
9. **Tạo release:** Đính kèm release note, artifact và hướng dẫn nâng cấp trên nền tảng phát hành.
10. **Triển khai và theo dõi:** Triển khai artifact đã xác định, kiểm tra health, metric và log sau phát hành.

Ví dụ:

~~~
git switch main
git fetch origin
git pull --ff-only
git log --oneline --decorate -5
git tag -a v1.4.0 HEAD -m "Release version 1.4.0"
git show v1.4.0
git rev-parse "v1.4.0^{commit}"
git push origin v1.4.0
~~~

Ví dụ giả định commit HEAD đã được review và kiểm thử, branch main là nguồn phát hành được nhóm chấp nhận, và tag v1.4.0 chưa tồn tại. Trong quy trình yêu cầu ký, dùng signed tag thay cho annotated tag thông thường và xác minh chữ ký trước khi công bố.

Nếu pipeline được cấu hình kích hoạt khi có tag mới, thao tác push tag có thể bắt đầu build hoặc deploy. Hãy kiểm tra trigger của pipeline và môi trường đích trước khi công bố tag, vì tên tag có thể là tín hiệu phát hành tự động.

## 12. Tag trong bảo trì nhiều phiên bản

Một số dự án phải bảo trì nhiều phiên bản song song. Khi đó branch và tag phối hợp với nhau:

~~~text
main:       ---A---B---C---D---E
                 \
release/1.x:      R1---R2
                  |     |
                v1.0.0 v1.0.1
~~~

Branch release/1.x tiếp tục nhận các commit sửa lỗi cho dòng phiên bản 1.x. Tag v1.0.0 và v1.0.1 đánh dấu từng bản phát hành trên dòng đó. Trong khi đó, main có thể tiếp tục phát triển phiên bản tiếp theo.

Một quy trình có thể:

- Tạo branch release khi cần ổn định một dòng phiên bản.
- Chỉ đưa các sửa lỗi được chấp nhận vào branch release.
- Tạo tag mới sau mỗi lần phát hành patch.
- Chuyển các sửa lỗi cần thiết về main bằng cherry-pick hoặc merge theo chính sách.
- Ghi rõ phiên bản nào còn được hỗ trợ và thời điểm kết thúc hỗ trợ.

Tag không thay thế branch bảo trì. Tag đánh dấu mốc phát hành; branch cho phép tiếp tục phát triển trên dòng phiên bản đó.

## 13. Lỗi thường gặp khi làm việc với tag

**Tạo tag khi đang ở sai branch hoặc sai commit.** Trước khi tag, kiểm tra branch hiện tại và commit SHA. Nếu cần, chỉ định rõ commit thay vì dựa vào HEAD.

**Nghĩ rằng tag tự xuất hiện trên remote.** Tag tạo ở local cần được push. Dùng git ls-remote --tags origin để kiểm tra tag đã được công bố.

**Dùng tag như branch.** Tag không tự tiến khi có commit mới. Nếu cần tiếp tục phát triển, tạo hoặc checkout branch thích hợp.

**Dùng lại tên tag đã phát hành.** Di chuyển tag có thể làm các môi trường và người dùng trỏ tới commit khác nhau. Khi cần sửa release, ưu tiên phiên bản mới.

**Chỉ dựa vào tên tag để xác minh artifact.** Hãy ghi lại commit SHA, checksum artifact và thông tin pipeline.

**Nhầm tag với release.** Tag đánh dấu object Git; release trên nền tảng có thể bổ sung note và file build. Tạo tag không có nghĩa artifact đã được phát hành.

**Không xác minh chữ ký hoặc khóa tin cậy.** Chữ ký hợp lệ cần được kiểm tra với khóa công khai đáng tin cậy và chính sách ủy quyền của tổ chức.

## 14. Checklist quản lý tag và release

**Trước khi tạo tag**

- [ ] Đã xác nhận đúng repository và remote.
- [ ] Đã xác định branch phát hành và commit SHA cần đánh dấu.
- [ ] Thay đổi đã được review và kiểm thử theo chính sách.
- [ ] Tên phiên bản tuân theo quy ước của dự án.
- [ ] Tag chưa tồn tại hoặc đã có quyết định rõ ràng về cách xử lý.

**Khi tạo và công bố tag**

- [ ] Dùng annotated tag cho mốc phát hành cần metadata.
- [ ] Ký tag nếu quy trình yêu cầu.
- [ ] Kiểm tra tag bằng git show và git rev-parse.
- [ ] Xác minh chữ ký và khóa tin cậy nếu có.
- [ ] Push tag cụ thể lên đúng remote.
- [ ] Kiểm tra tag đã xuất hiện trên remote.

**Khi phát hành**

- [ ] Build artifact từ commit đã xác định.
- [ ] Ghi checksum và thông tin truy vết.
- [ ] Chuẩn bị release note và hướng dẫn nâng cấp.
- [ ] Đính kèm artifact vào release hoặc registry phù hợp.
- [ ] Theo dõi kết quả triển khai và có kế hoạch xử lý sự cố.

**Sau phát hành**

- [ ] Giữ tag đã công bố ổn định.
- [ ] Bảo vệ quyền tạo, xóa và cập nhật tag release.
- [ ] Tạo tag phiên bản mới khi có bản sửa lỗi.
- [ ] Lưu lại lịch sử phát hành và trạng thái hỗ trợ phiên bản.

## 15. Kết luận

Tag là tham chiếu có tên dùng để đánh dấu một mốc lịch sử trong Git. Branch di chuyển theo commit mới, còn tag thường được giữ nguyên để đại diện cho một phiên bản hoặc mốc đã thống nhất. Tuy vậy, Git vẫn cho phép xóa hoặc di chuyển tag; tính cố định đến từ quy ước, phân quyền và quy trình bảo vệ của nhóm.

Với release chính thức, annotated tag hoặc signed tag thường phù hợp hơn lightweight tag vì lưu được metadata và hỗ trợ xác minh. Hãy xác nhận tag trỏ tới đúng commit, push tag lên remote, tạo artifact và release note bằng quy trình phát hành riêng, rồi giữ tag đã công bố ổn định để mọi người cùng tham chiếu một phiên bản.
