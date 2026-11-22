# Ranh giới giữa Git tag, phiên bản phần mềm và bản phát hành trên nền tảng

Khi một nhóm chuẩn bị giao phần mềm cho người dùng, mọi người thường nhắc tới tag, version và release như thể chúng là một khái niệm. Trong Git và quy trình phát hành, ba khái niệm này có liên quan nhưng đảm nhiệm những vai trò khác nhau:

- **Git tag** là một tham chiếu trong repository, thường dùng để đánh dấu một commit cụ thể trong lịch sử.
- **Phiên bản phần mềm** là nhãn phiên bản theo quy ước của dự án, chẳng hạn 2.4.1 hoặc 2.5.0-rc.2.
- **Bản phát hành trên nền tảng** là một mục phát hành được quản lý bởi dịch vụ lưu trữ mã nguồn hoặc hệ thống phân phối, thường gắn với tag và có thể chứa ghi chú, tệp cài đặt, chữ ký, checksum và thông tin phát hành.

Một dự án có thể đặt tên tag là v2.4.1, xem đó là phiên bản 2.4.1 và tạo một release trên GitHub, GitLab hoặc nền tảng khác từ tag ấy. Tuy nhiên, Git không tự hiểu chính sách versioning của dự án và việc tạo tag không tự tạo một trang release trên mọi nền tảng.

Sau bài này, bạn có thể:

- Phân biệt tag, version và release.
- Giải thích tag nhẹ và tag có chú giải.
- Tạo, liệt kê, kiểm tra, ký và chia sẻ tag.
- Áp dụng quy ước phiên bản như Semantic Versioning.
- Liên kết tag với một commit và bản phát hành cụ thể.
- Xử lý việc sửa, xóa hoặc thay thế tag một cách có kiểm soát.

## 1. Ba khái niệm và ranh giới của chúng

| Khái niệm | Được quản lý ở đâu? | Trả lời câu hỏi nào? |
| --- | --- | --- |
| Git tag | Trong Git repository, dưới namespace refs/tags. | Mốc lịch sử nào được đánh dấu? |
| Phiên bản phần mềm | Theo quy ước versioning của dự án hoặc sản phẩm. | Đây là dòng phiên bản và mức thay đổi nào? |
| Release trên nền tảng | Trong dịch vụ quản lý phát hành hoặc hệ thống phân phối. | Người dùng có thể xem ghi chú và tải những gói phát hành nào? |

Ví dụ, nhóm có thể quyết định:

- Commit 8f31abc là nội dung sẽ phát hành.
- Tag v2.4.1 trỏ tới commit đó.
- Phiên bản sản phẩm được công bố là 2.4.1.
- Release trên nền tảng có tiêu đề “Product 2.4.1”, ghi chú sửa lỗi và các tệp cài đặt cho Windows, macOS và Linux.

Tag cho biết vị trí trong lịch sử Git. Version thể hiện định danh theo chính sách của sản phẩm. Release là gói thông tin phát hành dành cho người dùng hoặc hệ thống triển khai. Một tag có thể tồn tại mà không có release trên nền tảng; một nền tảng cũng có thể tạo release từ một tag đã có.

Git lưu tag trong repository. Trang release, trạng thái draft, nội dung đính kèm hoặc nhãn “latest” là tính năng của nền tảng và có thể khác nhau giữa các nhà cung cấp. Không nên suy ra rằng một thao tác Git đã tạo xong mọi thông tin phát hành.

## 2. Git tag là gì?

Tag là một tên tham chiếu có thể dùng để tìm lại một đối tượng Git, thường là commit. Thay vì phải nhớ mã commit dài, bạn có thể dùng tên tag để chỉ một mốc quan trọng:

~~~bash
git show v2.4.1
~~~

Tag thường được đặt tại các mốc như:

- Phiên bản phần mềm đã phát hành.
- Bản build được bàn giao cho kiểm thử hoặc triển khai.
- Mốc ổn định trước khi thực hiện thay đổi lớn.
- Phiên bản thư viện mà một ứng dụng khác đang phụ thuộc.

Git không bắt buộc tag phải có dạng số phiên bản. Bạn có thể đặt tag như release-candidate, demo-2026-11 hoặc migration-baseline. Tuy nhiên, nhóm nên thống nhất cách đặt tên để người khác hiểu mục đích của tag.

Tag khác với branch ở cách sử dụng thông thường. Branch là tham chiếu di chuyển khi có commit mới trên nhánh; tag thường được dùng như một mốc cố định để nhận diện một đối tượng trong lịch sử. Git vẫn cho phép di chuyển hoặc xóa tag, vì vậy tính cố định của tag phát hành chủ yếu là quy ước và chính sách của nhóm.

## 3. Tag nhẹ và tag có chú giải

Git hỗ trợ hai loại tag phổ biến.

### Tag nhẹ (lightweight tag)

Tag nhẹ là một tham chiếu đơn giản trỏ trực tiếp tới đối tượng, thường là commit. Tạo tag:

~~~bash
git tag v2.4.1
~~~

Nếu không chỉ định commit, tag được tạo tại HEAD hiện tại. Có thể chỉ định commit khác:

~~~bash
git tag v2.4.1 8f31abc
~~~

Tag nhẹ phù hợp với một số mốc nội bộ hoặc dấu mốc tạm thời khi nhóm không cần metadata riêng cho tag. Nó không chứa thông điệp tagger như tag có chú giải.

### Tag có chú giải (annotated tag)

Tag có chú giải tạo một đối tượng tag riêng, chứa thông tin người tạo tag, thời gian, thông điệp và đối tượng được gắn tag. Tạo tag:

~~~bash
git tag -a v2.4.1 -m "Release version 2.4.1"
~~~

Hoặc gắn tag vào một commit cụ thể:

~~~bash
git tag -a v2.4.1 8f31abc -m "Release version 2.4.1"
~~~

Đối với mốc phát hành chính thức, tag có chú giải thường phù hợp hơn vì nó lưu thông tin mô tả về mốc phát hành. Nhiều quy trình release cũng yêu cầu tag có chữ ký để xác minh người tạo.

### So sánh

| Đặc điểm | Tag nhẹ | Tag có chú giải |
| --- | --- | --- |
| Cấu trúc | Tham chiếu trực tiếp tới đối tượng. | Có đối tượng tag riêng. |
| Thông điệp | Không có metadata thông điệp của tag. | Có thông điệp tag. |
| Người tạo và thời gian tag | Không lưu metadata tag riêng. | Lưu tagger và thời gian. |
| Chữ ký tag | Không ký theo cơ chế annotated tag. | Có thể ký bằng tùy chọn -s hoặc -u. |
| Mục đích thường gặp | Mốc tạm hoặc dấu mốc nội bộ đơn giản. | Phiên bản và mốc phát hành chính thức. |

Có thể xem loại đối tượng mà tên tag phân giải tới:

~~~bash
git cat-file -t v2.4.1
~~~

Với tag nhẹ trỏ tới commit, kết quả thường là commit. Với tag có chú giải, kết quả là tag. Lệnh sau hiển thị nội dung đối tượng được tag:

~~~bash
git show v2.4.1
~~~

## 4. Tag phải gắn với đúng commit

Tag phát hành cần chỉ đúng nội dung đã được kiểm tra và phê duyệt. Không nên chỉ tạo tag ở HEAD vì HEAD có thể đang ở nhánh hoặc commit khác với dự định.

Trước khi tag, kiểm tra:

~~~bash
git status --short --branch
git log --oneline --decorate -n 10
git show --stat 8f31abc
~~~

Sau khi xác nhận commit:

~~~bash
git tag -a v2.4.1 8f31abc -m "Release version 2.4.1"
git show --no-patch --decorate v2.4.1
~~~

Lệnh tag không tạo commit và không thay đổi nội dung working tree. Nó chỉ tạo tham chiếu hoặc đối tượng tag trỏ tới đối tượng được chỉ định. Nếu tag trỏ tới một commit cũ, release sẽ đại diện cho nội dung tại commit đó, không phải nội dung mới nhất của branch.

Nếu dự án build từ commit được tag, nên lưu lại mã commit, tag và thông tin build trong hệ thống CI/CD hoặc metadata phát hành. Điều này giúp truy nguyên gói binary về đúng nguồn đã tạo ra nó.

## 5. Đặt tên phiên bản phần mềm

Git cho phép tên tag tùy ý; quy tắc đặt phiên bản là chính sách của sản phẩm. Một quy ước phổ biến là **Semantic Versioning (SemVer)** với cấu trúc:

~~~text
MAJOR.MINOR.PATCH
~~~

- MAJOR tăng khi có thay đổi không tương thích với API công khai.
- MINOR tăng khi bổ sung chức năng tương thích ngược.
- PATCH tăng khi sửa lỗi tương thích ngược.

Ví dụ:

| Phiên bản | Ý nghĩa minh họa |
| --- | --- |
| 2.4.0 | Thêm chức năng tương thích ngược trong dòng 2.x. |
| 2.4.1 | Sửa lỗi tương thích ngược của phiên bản 2.4.0. |
| 2.5.0 | Bổ sung chức năng mới tương thích với API 2.x. |
| 3.0.0 | Thay đổi API công khai theo cách không tương thích với 2.x. |

SemVer mô tả ý nghĩa của số phiên bản dựa trên API công khai. Với ứng dụng không có API công khai hoặc sản phẩm dùng lịch phát hành theo ngày, nhóm có thể chọn một quy ước khác; điều quan trọng là tài liệu hóa quy tắc và dùng nhất quán.

### Phiên bản trước khi phát hành

Một phiên bản có thể có định danh prerelease:

~~~text
2.5.0-alpha.1
2.5.0-beta.2
2.5.0-rc.1
~~~

Các nhãn alpha, beta và rc thường biểu thị những giai đoạn thử nghiệm trước bản ổn định. Theo SemVer, phiên bản có phần prerelease có độ ưu tiên thấp hơn phiên bản phát hành chính thức tương ứng. Ví dụ 2.5.0-rc.1 thấp hơn 2.5.0.

### Build metadata

SemVer cho phép thêm metadata sau dấu cộng:

~~~text
2.5.0+build.184
~~~

Build metadata có thể ghi số build hoặc thông tin môi trường. Theo quy tắc SemVer, metadata này không làm thay đổi thứ tự ưu tiên của phiên bản. Không dùng build metadata để thay thế phần prerelease khi cần phân biệt phiên bản thử nghiệm với phiên bản ổn định.

### Tiền tố v trong Git tag

Nhiều dự án đặt tên tag theo dạng v2.5.0 thay vì 2.5.0. Chữ v là quy ước đặt tên tag; nó không phải thành phần bắt buộc của SemVer. Hãy thống nhất quy ước trong repository và công cụ phát hành để tránh tạo cả v2.5.0 lẫn 2.5.0 cho cùng một bản phát hành.

Git không tự kiểm tra tag có tuân thủ SemVer hay không. Git xem tên tag là chuỗi ký tự; việc phân tích và so sánh phiên bản phải do quy trình hoặc công cụ phù hợp đảm nhiệm.

## 6. Liệt kê, tìm kiếm và so sánh tag

Liệt kê tag:

~~~bash
git tag
~~~

Lọc tag theo mẫu:

~~~bash
git tag -l "v2.*"
git tag -l "*-rc.*"
~~~

Xem thông tin tag:

~~~bash
git show v2.4.1
git show --no-patch --format=fuller v2.4.1
~~~

Sắp xếp theo thứ tự version:

~~~bash
git tag --sort=-version:refname
~~~

Sắp xếp theo phiên bản giúp đọc các tag dạng số thuận tiện hơn sắp xếp chữ cái thông thường. Tuy vậy, kết quả vẫn phụ thuộc cách đặt tên tag; hãy giữ quy ước nhất quán để tránh thứ tự khó hiểu.

Xem commit nằm giữa hai mốc:

~~~bash
git log --oneline v2.3.0..v2.4.1
~~~

Lệnh trên liệt kê commit có thể đi tới từ v2.4.1 nhưng không đi tới từ v2.3.0. Có thể xem thay đổi nội dung:

~~~bash
git diff v2.3.0..v2.4.1
~~~

Nếu muốn xem thay đổi kể từ điểm phân nhánh chung giữa hai mốc:

~~~bash
git diff v2.3.0...v2.4.1
~~~

Hãy chọn phép so sánh theo câu hỏi: so sánh hai cây tại đầu mút hay xem thay đổi của một phía kể từ merge base.

## 7. Kiểm tra tag đang trỏ tới đâu

Để lấy mã commit mà tag phân giải tới:

~~~bash
git rev-parse v2.4.1^{commit}
~~~

Trong một số shell, ký tự đặc biệt trong biểu thức có thể cần đặt trong dấu nháy:

~~~bash
git rev-parse "v2.4.1^{commit}"
~~~

Để so sánh với commit của nhánh:

~~~bash
git rev-parse main
git rev-parse "v2.4.1^{commit}"
~~~

Hai mã commit giống nhau khi tag trỏ tới đúng commit đầu nhánh main tại thời điểm kiểm tra. Tuy nhiên, main có thể tiếp tục di chuyển sau khi release; vì vậy, không nên kỳ vọng tag luôn bằng HEAD của một branch đang phát triển.

Muốn tìm commit mới nhất được mô tả bằng tag gần nhất:

~~~bash
git describe --tags
~~~

Có thể thêm --dirty để đánh dấu working tree có thay đổi chưa commit, hoặc --always để có kết quả dự phòng khi không tìm được tag phù hợp:

~~~bash
git describe --tags --dirty --always
~~~

Lệnh này thường được dùng trong script build để tạo thông tin phiên bản từ lịch sử Git. Kết quả phụ thuộc các tag có trong repository local; nếu clone nông hoặc chưa fetch tag, thông tin có thể không đầy đủ.

## 8. Ký và xác minh tag

Với release yêu cầu xác thực nguồn gốc, nhóm có thể dùng tag có chữ ký. Tạo signed tag:

~~~bash
git tag -s v2.4.1 8f31abc -m "Release version 2.4.1"
~~~

Tùy cấu hình, Git sử dụng khóa ký đã thiết lập, thường thông qua GPG hoặc cơ chế ký được hỗ trợ. Nếu cần chọn khóa cụ thể, có thể dùng tùy chọn -u với định danh khóa phù hợp:

~~~bash
git tag -u KEY-ID v2.4.1 8f31abc -m "Release version 2.4.1"
~~~

Xác minh chữ ký:

~~~bash
git tag -v v2.4.1
~~~

Kết quả xác minh cho biết chữ ký có hợp lệ theo khóa được dùng hay không. Người nhận vẫn cần có cơ sở tin cậy cho khóa đó, ví dụ khóa đã được xác minh qua kênh nội bộ hoặc danh sách khóa phát hành chính thức. Chữ ký hợp lệ chỉ xác minh nội dung được ký và khóa ký; nó không tự chứng minh mã nguồn an toàn hay bản build không bị thay thế.

Nếu nhóm không cấu hình chữ ký tag, có thể dùng tag có chú giải để lưu người tạo và thông điệp. Chính sách bảo vệ tag trên nền tảng cũng có thể hạn chế ai được tạo, cập nhật hoặc xóa tag phát hành.

## 9. Chia sẻ tag với remote

Khác với branch được push mặc định trong nhiều tình huống, tag không phải lúc nào cũng được gửi lên remote khi bạn push branch. Hãy chủ động chia sẻ tag phát hành.

Push một tag cụ thể:

~~~bash
git push origin v2.4.1
~~~

Push tất cả tag local:

~~~bash
git push origin --tags
~~~

Lệnh --tags có thể gửi cả tag nội bộ hoặc tag thử nghiệm mà bạn không định công bố. Trước khi dùng, hãy xem danh sách tag và chính sách của repository.

Nếu muốn push branch cùng các annotated tag liên quan tới commit đang push:

~~~bash
git push --follow-tags
~~~

--follow-tags chỉ bổ sung các annotated tag phù hợp theo lịch sử của các ref được push; nó không tương đương với việc gửi tất cả tag local.

Xem tag mà remote đang công bố:

~~~bash
git ls-remote --tags origin
~~~

Lệnh này truy vấn các tham chiếu tag trên remote mà không cần cập nhật chúng vào local. Sau khi fetch tag:

~~~bash
git fetch origin --tags
~~~

Tag được lưu trong namespace refs/tags, không phải remote-tracking branch như origin/main. Vì vậy, không có khái niệm origin/v2.4.1 tương tự origin/main theo cách thông thường.

## 10. Git tag và release trên nền tảng

Sau khi tag đã được push lên remote, nhóm có thể tạo một release trên nền tảng lưu trữ mã nguồn hoặc hệ thống phát hành. Một release thường có thể chứa:

- Tag hoặc commit làm nguồn nội dung.
- Tên phát hành dễ đọc, ví dụ Product 2.4.1.
- Release notes mô tả chức năng mới, lỗi đã sửa và thay đổi có ảnh hưởng.
- Tệp binary, gói cài đặt, container image hoặc tài liệu phát hành.
- Checksum và chữ ký để người dùng xác minh tệp tải xuống.
- Trạng thái draft, prerelease hoặc published tùy nền tảng.

Ví dụ quy trình trên một nền tảng Git hosting:

1. Tạo tag v2.4.1 tại commit đã qua kiểm thử.
2. Push tag lên origin.
3. Mở trang Releases hoặc giao diện quản lý phát hành của nền tảng.
4. Tạo release dựa trên tag v2.4.1.
5. Viết ghi chú, đính kèm artifact và kiểm tra thông tin.
6. Publish release theo quyền và quy trình của nhóm.

Việc tạo release trên nền tảng không phải lệnh Git chuẩn. Tùy nhà cung cấp, thao tác có thể thực hiện qua giao diện web, CLI, API hoặc pipeline CI/CD. Tên trường, trạng thái và khả năng đính kèm file cũng khác nhau.

Một release có thể trỏ tới tag đã có. Nếu nền tảng cho phép tạo release và tag cùng lúc, hãy kiểm tra tag được tạo ở commit nào trước khi công bố. Không nên để giao diện tự tạo một tag mới từ branch mặc định khi bạn định phát hành một commit khác.

## 11. Quy trình phát hành từ commit đến release

Một quy trình đơn giản có thể chia thành các bước:

~~~text
Chọn commit đã phê duyệt
          |
          v
Kiểm tra lịch sử và working tree
          |
          v
Tạo annotated hoặc signed tag
          |
          v
Xác minh tag và commit đích
          |
          v
Push tag lên remote
          |
          v
CI/CD tạo và kiểm tra artifact
          |
          v
Tạo release notes và đính kèm artifact
          |
          v
Publish theo quy trình của nhóm
~~~

Ví dụ lệnh ở repository:

~~~bash
# Kiểm tra trạng thái
git status --short --branch

# Xác nhận commit sẽ phát hành
git show --stat 8f31abc

# Tạo tag có chú giải tại commit đó
git tag -a v2.4.1 8f31abc -m "Release version 2.4.1"

# Kiểm tra tag và commit
git show --no-patch --decorate v2.4.1
git rev-parse "v2.4.1^{commit}"

# Chia sẻ tag
git push origin v2.4.1
~~~

Sau khi pipeline tạo artifact, lưu checksum và thông tin build theo chính sách phát hành. Release notes nên phản ánh đúng những gì có trong tag; nếu cần, tạo ghi chú từ danh sách commit giữa hai tag:

~~~bash
git log --oneline v2.4.0..v2.4.1
~~~

Không tự động coi mọi commit trong khoảng này là thay đổi hướng tới người dùng. Hãy tổng hợp và rà soát ghi chú theo nhóm chức năng, sửa lỗi, thay đổi tương thích và vấn đề cần lưu ý.

## 12. Tag đã phát hành nên được xem là mốc ổn định

Git cho phép di chuyển tag, nhưng tag đã công bố thường được xem là mốc bất biến theo quy ước. Nếu tag v2.4.1 ban đầu trỏ tới commit A rồi bị di chuyển sang commit B, người dùng có thể đã tải artifact từ A trong khi repository lại cho thấy tag trỏ tới B. Điều này làm mất khả năng truy nguyên.

Không nên sửa tag phát hành đã công bố chỉ để trỏ tới commit mới. Nếu phát hiện lỗi, thông thường hãy tạo phiên bản tiếp theo, ví dụ v2.4.2, rồi phát hành artifact và ghi chú sửa lỗi. Cách này giữ nguyên dấu vết của phiên bản cũ.

Nếu tag chỉ là tag nội bộ chưa chia sẻ và cần sửa nhầm vị trí, có thể cập nhật local bằng:

~~~bash
# Di chuyển tag nhẹ tới commit mới
git tag -f v2.4.1 8f31abc

# Di chuyển tag có chú giải và giữ metadata annotated
git tag -fa v2.4.1 8f31abc -m "Release version 2.4.1"
~~~

Chỉ làm vậy khi hiểu rõ tag sẽ được di chuyển và chưa có người khác dựa vào nó. Tùy chọn -f ghi đè tag local; thêm -a nếu cần giữ tag ở dạng annotated. Nếu tag đã tồn tại trên remote, việc cập nhật remote cần quyền và quy trình riêng; không nên dùng force push tag như thao tác sửa thông thường.

## 13. Xóa hoặc thay thế tag

Xóa tag local:

~~~bash
git tag -d v2.4.1
~~~

Xóa tag trên remote:

~~~bash
git push origin --delete v2.4.1
~~~

Một cú pháp khác để xóa ref trên remote:

~~~bash
git push origin :refs/tags/v2.4.1
~~~

Xóa tag không xóa commit được tag trỏ tới. Commit vẫn có thể được giữ bởi branch, tag khác hoặc đối tượng tham chiếu khác.

Nếu cần đổi tên tag, Git không có thao tác rename tag trực tiếp. Quy trình thường là tạo tag mới tại cùng commit, xác minh tag mới, chia sẻ tag mới rồi xóa tag cũ theo chính sách:

~~~bash
git tag -a v2.4.1 8f31abc -m "Release version 2.4.1"
git show v2.4.1
git push origin v2.4.1
~~~

Nếu tag cũ đã được dùng trong bản phát hành công khai, hãy cân nhắc giữ nguyên và giải thích bằng release notes hoặc tạo phiên bản sửa lỗi. Việc xóa tag cũ có thể làm hỏng liên kết tải xuống, script triển khai hoặc tham chiếu trong tài liệu của người dùng.

## 14. Một số lệnh hữu ích khi làm việc với tag

| Mục đích | Lệnh |
| --- | --- |
| Liệt kê tag | git tag |
| Lọc tag theo mẫu | git tag -l "v2.*" |
| Tạo tag nhẹ | git tag v2.4.1 |
| Tạo annotated tag | git tag -a v2.4.1 -m "Release version 2.4.1" |
| Tạo signed tag | git tag -s v2.4.1 -m "Release version 2.4.1" |
| Xem tag | git show v2.4.1 |
| Xác minh chữ ký | git tag -v v2.4.1 |
| Tìm tag gần nhất | git describe --tags |
| Sắp xếp theo version | git tag --sort=-version:refname |
| Push một tag | git push origin v2.4.1 |
| Push mọi tag local | git push origin --tags |
| Fetch tag | git fetch origin --tags |
| Xem tag trên remote | git ls-remote --tags origin |
| Xóa tag local | git tag -d v2.4.1 |
| Xóa tag remote | git push origin --delete v2.4.1 |

## 15. Những hiểu lầm thường gặp

### Tạo tag đồng nghĩa đã tạo release

Không đúng. Tag là tham chiếu trong Git. Release trên nền tảng là mục phát hành riêng, có thể gắn với tag và chứa thông tin hoặc artifact.

### Git tự hiểu số phiên bản

Không đúng. Git lưu tên tag như chuỗi. Quy tắc MAJOR.MINOR.PATCH, prerelease và build metadata thuộc chính sách versioning của dự án.

### Mọi tag đều có thông điệp và người tạo

Không đúng. Tag nhẹ chỉ là tham chiếu đơn giản. Annotated tag mới có metadata tag riêng.

### Tag luôn bất biến

Không đúng về mặt kỹ thuật. Git cho phép di chuyển và xóa tag. Tính bất biến của tag phát hành cần được bảo vệ bằng quy ước, quyền hạn và quy trình.

### Push branch sẽ luôn push tag liên quan

Không nên giả định điều này. Hãy push tag cụ thể, dùng --follow-tags khi phù hợp hoặc push --tags sau khi kiểm tra danh sách tag.

### Chữ ký tag chứng minh artifact an toàn

Chữ ký xác minh đối tượng tag được ký bởi khóa tương ứng. Nó không tự xác minh toàn bộ pipeline, dependency, binary hoặc môi trường triển khai. Artifact cần checksum, chữ ký và quy trình kiểm tra riêng nếu sản phẩm yêu cầu.

## 16. Ghi nhớ

- Git tag đánh dấu một đối tượng trong lịch sử; phiên bản phần mềm là định danh theo quy ước; release trên nền tảng là mục phát hành có metadata và artifact.
- Tag nhẹ là tham chiếu đơn giản; annotated tag lưu thông tin người tạo, thời gian và thông điệp.
- Với phiên bản chính thức, nhóm thường chọn annotated tag và có thể yêu cầu signed tag.
- Tag phải trỏ tới đúng commit đã được kiểm tra và phê duyệt.
- SemVer quy định ý nghĩa của MAJOR, MINOR, PATCH và prerelease; Git không tự áp dụng quy tắc này.
- Push tag lên remote là bước riêng; tạo tag không tự tạo release trên nền tảng.
- Xem tag phát hành đã công bố là mốc ổn định. Nếu có lỗi, thường phát hành một phiên bản mới để giữ lịch sử truy nguyên.
- Release notes, artifact, checksum và chữ ký cần phản ánh đúng commit/tag đã phát hành.

Khi phân biệt rõ Git tag, version và release, nhóm có thể truy ngược một bản phát hành về đúng commit, giải thích ý nghĩa phiên bản và cung cấp artifact có thể xác minh. Ba thành phần phối hợp với nhau trong quy trình phát hành, nhưng mỗi thành phần vẫn có vòng đời và trách nhiệm riêng.
