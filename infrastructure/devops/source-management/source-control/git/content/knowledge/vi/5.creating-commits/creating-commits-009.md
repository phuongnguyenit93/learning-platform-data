# Dùng trailer để lưu thông tin đồng tác giả và tham chiếu công việc

Một commit thường cần trả lời hai câu hỏi: thay đổi này làm gì và nó liên quan đến ai hoặc công việc nào. Subject và phần mô tả giải thích mục đích, còn trailer ở cuối commit message có thể ghi thêm thông tin có cấu trúc như đồng tác giả, người review, ticket hoặc yêu cầu tuân thủ quy trình đóng góp.

Ví dụ, một commit có thể kết thúc bằng:

~~~text
Co-authored-by: Linh Nguyen <linh@example.com>
Reviewed-by: Minh Tran <minh@example.com>
Refs: PAY-482
~~~

Những dòng này vẫn là văn bản trong commit message, nhưng tuân theo định dạng trailer mà Git và nhiều nền tảng có thể nhận diện. Bài này hướng dẫn cấu trúc trailer, cách thêm và đọc chúng bằng Git, cách ghi nhận đồng tác giả và tham chiếu công việc, cùng những khác biệt giữa trailer, sign-off và chữ ký mật mã.

Bài thuộc chương **Tạo commit** của module **SOURCE_CONTROL_GIT**. Module hướng dẫn Git từ working tree, staging area, commit và lịch sử đến branch, merge, rebase, remote và tag; đồng thời rèn cách cộng tác qua nhánh, giải quyết xung đột, truy tìm thay đổi và khôi phục thao tác sai mà vẫn bảo toàn lịch sử quan trọng. Dùng trailer đúng cách giúp lịch sử commit dễ truy vết và ghi nhận đóng góp rõ ràng hơn.

## 1. Trailer là gì?

Trailer là một dòng metadata đặt ở phần cuối commit message. Dạng phổ biến:

~~~text
Token: value
~~~

Ví dụ:

~~~text
Co-authored-by: An Le <an@example.com>
Refs: PROJ-123
Reviewed-by: Binh Pham <binh@example.com>
~~~

Trong đó:

- **Token** là tên trường, chẳng hạn <code>Co-authored-by</code>, <code>Reviewed-by</code>, <code>Refs</code>.
- **Separator** thường là dấu hai chấm <code>:</code>.
- **Value** là nội dung của trường, chẳng hạn tên/email hoặc mã ticket.

Trailer thường nằm trong một khối riêng ở cuối commit message, sau một dòng trống ngăn cách với phần mô tả. Ví dụ:

~~~text
feat(payment): retry request when gateway times out

Retry transient gateway failures with a bounded backoff.
Keep the original request identifier across attempts.

Co-authored-by: An Le <an@example.com>
Refs: PAY-482
Reviewed-by: Binh Pham <binh@example.com>
~~~

Phần đầu là subject, đoạn tiếp theo là body, còn các dòng cuối là trailer. Cách bố trí này giúp người đọc phân biệt nội dung giải thích với metadata.

### Trailer không phải một trường riêng trong commit object

Git lưu commit message như một phần văn bản của commit object. Trailer không được lưu thành một bảng metadata độc lập bên cạnh author, committer, tree và parent. Git có quy tắc để nhận diện các dòng trailer ở cuối message, còn công cụ hoặc nền tảng khác quyết định cách diễn giải từng token.

Vì vậy, một trailer tùy chỉnh như <code>Refs: PAY-482</code> có thể hữu ích cho nhóm dù Git core không tự biết PAY-482 là ticket của hệ thống nào. Nền tảng quản lý dự án hoặc script của nhóm có thể đọc nó và tạo liên kết.

## 2. Cấu trúc một commit message có trailer

Một commit message dễ đọc thường có ba phần:

1. Subject ngắn gọn mô tả thay đổi.
2. Body giải thích lý do hoặc cách triển khai khi cần.
3. Trailer ở cuối, mỗi dòng ghi một thông tin có cấu trúc.

Ví dụ:

~~~text
fix(api): handle expired access token

Refresh the access token once before returning an authentication error.
Preserve the request body so the retry does not lose user input.

Co-authored-by: Ha Vo <ha@example.com>
Refs: AUTH-219
Reviewed-by: Nam Do <nam@example.com>
~~~

Không bắt buộc mọi commit phải có đủ cả ba phần. Một sửa đổi nhỏ có thể chỉ cần subject và một trailer; một thay đổi phức tạp có thể cần body giải thích.

Nên giữ trailer ở cuối message. Đặt ghi chú thông thường hoặc đoạn giải thích sau trailer có thể khiến parser không còn nhận diện khối trailer như mong muốn.

### Trailer có thể có nhiều dòng value

Một số trailer có value dài hoặc có dòng tiếp nối. Các dòng tiếp nối thường bắt đầu bằng khoảng trắng. Tuy nhiên, để tương thích giữa công cụ, nên ưu tiên value gọn trên một dòng nếu không thật sự cần nội dung nhiều dòng.

## 3. Ghi nhận đồng tác giả bằng Co-authored-by

Trong một commit Git thông thường, commit object có một trường <code>author</code> và một trường <code>committer</code>. Khi nhiều người cùng thực hiện thay đổi, trailer <code>Co-authored-by</code> là cách phổ biến để ghi nhận thêm người cộng tác trong commit message.

Định dạng:

~~~text
Co-authored-by: Full Name <email@example.com>
~~~

Ví dụ:

~~~text
feat(checkout): add address validation

Validate required address fields before creating an order.

Co-authored-by: Mai Nguyen <mai@example.com>
Co-authored-by: Khoa Tran <khoa@example.com>
~~~

Có thể có nhiều dòng <code>Co-authored-by</code> trong cùng một commit. Nhiều nền tảng lưu trữ mã nguồn nhận diện token này và hiển thị người đồng tác giả trong giao diện commit hoặc hồ sơ đóng góp. Cách hiển thị cụ thể phụ thuộc nền tảng và cấu hình của dự án.

### Dùng email nào?

Nếu nền tảng cần liên kết đồng tác giả với tài khoản, email trong trailer phải là địa chỉ mà nền tảng nhận diện cho tài khoản đó. Một số dịch vụ hỗ trợ địa chỉ noreply; hãy dùng đúng địa chỉ mà người cộng tác đã đăng ký hoặc được tổ chức cho phép công khai.

Không tự đoán email của đồng tác giả. Hãy hỏi người đó hoặc dùng địa chỉ được họ cung cấp. Email trong trailer sẽ trở thành một phần lịch sử commit và có thể được công khai khi repository được chia sẻ.

### Co-authored-by không thay đổi author field

Trailer này giúp nền tảng hoặc công cụ nhận diện thêm người cộng tác, nhưng không biến commit object thành commit có nhiều trường author. Git vẫn lưu một author chính. Nếu cần kiểm tra author/committer gốc:

~~~bash
git show -s --format=fuller HEAD
~~~

Để đọc trailer của commit:

~~~bash
git show -s --format='%(trailers)' HEAD
~~~

## 4. Tham chiếu ticket và công việc

Trailer tùy chỉnh có thể liên kết commit với issue, ticket, task hoặc change request. Ví dụ:

~~~text
Refs: PAY-482
Refs: https://tracker.example.com/browse/PAY-482
~~~

Một nhóm có thể chọn token khác như:

| Token | Ý nghĩa thường dùng |
|---|---|
| <code>Refs</code> | Tham chiếu đến ticket hoặc issue liên quan |
| <code>Issue</code> | Mã issue mà commit xử lý |
| <code>Task</code> | Công việc hoặc task trong hệ thống quản lý dự án |
| <code>Reviewed-by</code> | Người đã review thay đổi |
| <code>Tested-by</code> | Người hoặc hệ thống đã kiểm thử |
| <code>Related-to</code> | Công việc có liên quan |

Các token trên là quy ước do nhóm hoặc nền tảng lựa chọn; chúng không phải tất cả đều có ý nghĩa chuẩn trong Git core. Hãy thống nhất cách viết, hệ thống ticket và quy tắc kiểm tra để mọi thành viên dùng nhất quán.

### Refs không tự động đóng issue

<code>Refs: PAY-482</code> chỉ ghi nhận tham chiếu. Nó không tự động đóng ticket nếu hệ thống quản lý công việc không được cấu hình để đọc token đó.

Một số nền tảng hỗ trợ closing keyword trong commit message, ví dụ <code>Fixes #123</code>, <code>Closes #123</code> hoặc <code>Resolves #123</code>. Đây là cú pháp do nền tảng quy định; không nên giả định mọi trailer tùy chỉnh như <code>Issue: #123</code> đều kích hoạt chức năng đóng issue. Hãy kiểm tra quy tắc của nền tảng đang dùng và đặt closing keyword theo đúng định dạng được hỗ trợ.

Ví dụ khi nhóm muốn vừa lưu tham chiếu dạng trailer vừa dùng closing keyword:

~~~text
fix(api): reject expired refresh token

Return an authentication error when the refresh token is expired.
Fixes #123

Refs: AUTH-219
Reviewed-by: Linh Nguyen <linh@example.com>
~~~

Trong ví dụ này, <code>Refs</code> là metadata theo quy ước nhóm; <code>Fixes #123</code> là dòng trong body theo quy tắc đóng issue của nền tảng hỗ trợ cú pháp đó.

## 5. Signed-off-by và Developer Certificate of Origin

Một trailer thường gặp trong dự án mã nguồn mở là:

~~~text
Signed-off-by: Full Name <email@example.com>
~~~

Trailer này thường được dùng để thể hiện người đóng góp xác nhận điều khoản đóng góp, chẳng hạn Developer Certificate of Origin (DCO). Chính sách dự án sẽ quy định chính xác ý nghĩa của sign-off và khi nào cần có nó.

Git hỗ trợ thêm sign-off bằng:

~~~bash
git commit -s -m "Fix request validation"
~~~

Tùy cấu hình identity, Git thêm trailer <code>Signed-off-by</code> dùng tên và email của committer. Hãy kiểm tra nội dung commit trước khi gửi để chắc chắn thông tin chính xác.

### Sign-off không phải chữ ký mật mã

<code>Signed-off-by</code> là một tuyên bố bằng văn bản trong commit message. Nó không tự tạo chữ ký mật mã và không chứng minh rằng người ghi tên sở hữu private key.

Để ký commit bằng khóa mật mã, Git có tùy chọn <code>-S</code>:

~~~bash
git commit -S -m "Fix request validation"
~~~

Có thể kiểm tra chữ ký:

~~~bash
git verify-commit HEAD
~~~

Hai tùy chọn có mục đích khác nhau:

| Tùy chọn | Kết quả |
|---|---|
| <code>-s</code> | Thêm trailer <code>Signed-off-by</code> |
| <code>-S</code> | Ký commit bằng khóa ký đã cấu hình |

Một dự án có thể yêu cầu sign-off, chữ ký mật mã hoặc cả hai. Hãy theo chính sách đóng góp của dự án.

## 6. Thêm trailer khi tạo commit

Có nhiều cách tạo commit message có trailer. Chọn cách phù hợp với mức độ tự động hóa và khả năng kiểm tra.

### Viết trực tiếp bằng nhiều đối số -m

Mỗi lần dùng <code>-m</code> tạo một paragraph trong commit message:

~~~bash
git commit \
  -m "feat(payment): add retry policy" \
  -m "Retry transient gateway failures with a bounded backoff." \
  -m "Co-authored-by: An Le <an@example.com>
Refs: PAY-482"
~~~

Với cách này, mỗi lần <code>-m</code> tạo một paragraph. Hai dòng trailer được đặt trong cùng đối số cuối nên cùng nằm trong một paragraph. Khi cần nhiều trailer, không tách mỗi trailer thành một đối số <code>-m</code> riêng vì chúng sẽ trở thành các paragraph riêng; hãy dùng một khối nhiều dòng như ví dụ hoặc dùng file message kết hợp <code>git interpret-trailers</code>.

### Dùng file commit message

Tạo file <code>commit-message.txt</code>:

~~~text
feat(payment): add retry policy

Retry transient gateway failures with a bounded backoff.
Preserve the request identifier across retries.

Co-authored-by: An Le <an@example.com>
Refs: PAY-482
Reviewed-by: Binh Pham <binh@example.com>
~~~

Sau đó:

~~~bash
git commit -F commit-message.txt
~~~

Tùy chọn <code>-F</code> đọc toàn bộ nội dung file làm commit message. Cách này thuận tiện cho script tạo message hoặc khi cần review message trước khi commit.

### Dùng git commit --trailer

Các phiên bản Git hỗ trợ tùy chọn <code>--trailer</code> cho <code>git commit</code> có thể thêm trailer trực tiếp:

~~~bash
git commit \
  -m "feat(payment): add retry policy" \
  --trailer "Co-authored-by: An Le <an@example.com>" \
  --trailer "Refs: PAY-482"
~~~

Nếu lệnh báo tùy chọn không được hỗ trợ, kiểm tra phiên bản Git và dùng file message kết hợp <code>git interpret-trailers</code> như phần tiếp theo. Không nên giả định mọi máy trong nhóm đều đang dùng cùng phiên bản Git.

## 7. Thêm và chuẩn hóa trailer bằng git interpret-trailers

<code>git interpret-trailers</code> là lệnh plumbing dành cho việc đọc, thêm và xử lý trailer trong commit message. Nó hữu ích cho script vì có thể áp dụng quy tắc nhất quán mà không cần tự viết parser chuỗi.

### Thêm trailer vào file message

Tạo file message trước:

~~~bash
cat > commit-message.txt <<'EOF'
feat(search): improve query normalization

Normalize whitespace before building the search request.
EOF
~~~

Thêm trailer:

~~~bash
git interpret-trailers \
  --trailer "Co-authored-by: An Le <an@example.com>" \
  --trailer "Refs: SEARCH-91" \
  --in-place commit-message.txt
~~~

Đọc lại file:

~~~bash
cat commit-message.txt
~~~

Sau đó tạo commit:

~~~bash
git commit -F commit-message.txt
~~~

<code>--in-place</code> yêu cầu cập nhật file message trực tiếp. Nếu không dùng tùy chọn này, lệnh thường ghi message đã xử lý ra standard output để bạn chuyển tiếp hoặc lưu ở nơi khác.

### Đọc trailer đã có

Để parse trailer từ file:

~~~bash
git interpret-trailers --parse < commit-message.txt
~~~

Để xem trailer của commit hiện tại:

~~~bash
git show -s --format='%(trailers)' HEAD
~~~

Để xem toàn bộ body và trailer:

~~~bash
git show -s --format='%B' HEAD
~~~

<code>%(trailers)</code> là placeholder trong pretty format của Git. Nó giúp script hoặc người review lấy trailer mà không phải phân tích thủ công toàn bộ commit message.

## 8. Cấu hình quy tắc trailer cho nhóm

Git cho phép cấu hình cách thêm trailer thông qua nhóm cấu hình <code>trailer.*</code>. Ví dụ, nhóm muốn chuẩn hóa token <code>Refs</code> và tránh thêm trùng cùng một tham chiếu:

~~~bash
git config trailer.refs.key "Refs"
git config trailer.refs.ifexists addIfDifferent
git config trailer.refs.ifmissing add
git config trailer.refs.where end
~~~

Sau đó có thể thêm trailer bằng:

~~~bash
git interpret-trailers --trailer "refs: PAY-482" --in-place commit-message.txt
~~~

Trong cấu hình:

- <code>key</code> xác định tên trailer chuẩn được xuất ra.
- <code>ifexists</code> quy định cách xử lý khi token đã có.
- <code>ifmissing</code> quy định hành động khi chưa có trailer tương ứng.
- <code>where</code> xác định vị trí thêm trailer.

Một số giá trị thường gặp cho <code>ifexists</code> gồm <code>add</code>, <code>addIfDifferent</code>, <code>addIfDifferentNeighbor</code>, <code>replace</code> và <code>doNothing</code>. Vị trí có thể cấu hình theo các lựa chọn như <code>end</code>, <code>start</code>, <code>after</code> hoặc <code>before</code> tùy ngữ cảnh và phiên bản Git. Tham khảo <code>git help interpret-trailers</code> để kiểm tra đầy đủ cú pháp được cài đặt hỗ trợ.

### Tránh tạo trailer trùng

Nếu script có thể chạy nhiều lần trên cùng file message, hãy chọn chính sách trùng lặp phù hợp. Ví dụ:

- <code>add</code>: luôn thêm, kể cả value đã tồn tại.
- <code>addIfDifferent</code>: chỉ thêm khi chưa có trailer cùng token và value.
- <code>replace</code>: thay trailer hiện có theo quy tắc cấu hình.
- <code>doNothing</code>: không làm gì nếu token đã tồn tại.

Không nên dùng <code>replace</code> một cách chung chung cho token cho phép nhiều giá trị như <code>Co-authored-by</code>, vì có thể làm mất thông tin đồng tác giả trước đó.

## 9. Trailer nhiều giá trị và thứ tự

Một commit có thể chứa nhiều trailer cùng token:

~~~text
Co-authored-by: An Le <an@example.com>
Co-authored-by: Binh Pham <binh@example.com>
Reviewed-by: Chi Nguyen <chi@example.com>
Reviewed-by: Dung Tran <dung@example.com>
Refs: PAY-482
Refs: PAY-496
~~~

Thứ tự có thể có ý nghĩa với quy trình hoặc giao diện hiển thị. Hãy thống nhất thứ tự trong nhóm, ví dụ:

1. Đồng tác giả.
2. Người review hoặc kiểm thử.
3. Tham chiếu công việc.
4. Sign-off.

Đây chỉ là quy ước minh họa. Nếu dự án có mẫu commit message hoặc hook kiểm tra riêng, hãy theo mẫu của dự án.

### Một token có nhiều value

Đối với <code>Co-authored-by</code>, mỗi người nên có một trailer riêng thay vì gộp nhiều email vào cùng một value. Cách viết riêng giúp công cụ dễ nhận diện từng người và giảm lỗi định dạng.

Đối với ticket, một trailer có thể chứa một mã hoặc nhiều mã theo quy ước. Nếu muốn parser liên kết từng ticket độc lập, nhiều dòng <code>Refs</code> thường rõ ràng hơn.

## 10. Trailer được Git nhận diện như thế nào?

Git tìm trailer trong phần cuối commit message theo định dạng token và separator. Khối trailer thường là paragraph cuối cùng. Dòng thông thường sau khối trailer có thể khiến parser không còn nhận diện đúng phần cuối như mong đợi.

Ví dụ dễ nhận diện:

~~~text
Add retry handling

Retry the request after transient gateway failures.

Refs: PAY-482
Reviewed-by: Linh Nguyen <linh@example.com>
~~~

Ví dụ dễ gây nhầm:

~~~text
Add retry handling

Refs: PAY-482

Additional note: this is still experimental.
~~~

Trong ví dụ thứ hai, đoạn văn cuối không phải trailer block. Hãy đặt ghi chú trước khối trailer để parser và người đọc có thể nhận diện rõ ràng.

### Separator và token tùy chỉnh

Mặc định, dấu hai chấm là separator phổ biến:

~~~text
Refs: PAY-482
Reviewed-by: Linh Nguyen <linh@example.com>
~~~

Git cũng có thể cấu hình separator khác qua <code>trailer.separators</code>. Nhóm nên dùng một định dạng thống nhất thay vì trộn nhiều kiểu phân cách trong cùng repository.

Tên token không nên chứa dấu phân cách hoặc được đặt tùy tiện. Chọn tên ngắn, ổn định, có ý nghĩa rõ và tránh tạo nhiều biến thể như <code>Ref</code>, <code>Refs</code>, <code>Reference</code> nếu chúng cùng một mục đích.

## 11. Kiểm tra trailer trước khi chia sẻ commit

Trước khi push, hãy xem lại commit message:

~~~bash
git show -s --format=fuller HEAD
git show -s --format='%(trailers)' HEAD
~~~

Kiểm tra:

- Subject và body mô tả đúng thay đổi.
- Email đồng tác giả chính xác và đã được người đó đồng ý dùng.
- Ticket hoặc issue tham chiếu đúng.
- Trailer không bị lặp do script chạy nhiều lần.
- Không có token hoặc dữ liệu bí mật trong value.
- Sign-off có mặt nếu chính sách dự án yêu cầu.

Nếu commit chưa được chia sẻ, bạn có thể sửa commit message bằng:

~~~bash
git commit --amend
~~~

Nếu commit đã được push và người khác dựa trên nó, sửa message sẽ viết lại commit hash. Hãy phối hợp với nhóm trước khi force push; nếu mục tiêu chỉ là bổ sung thông tin, có thể cân nhắc commit bổ sung theo quy trình của dự án.

## 12. Tự động kiểm tra trailer trong hook hoặc CI

Nhóm có thể kiểm tra trailer để bảo đảm commit tuân thủ quy ước. Ví dụ, lấy trailer của commit hiện tại:

~~~bash
git show -s --format='%(trailers)' HEAD
~~~

Hoặc kiểm tra commit trong một khoảng:

~~~bash
git log --format='%h %s%n%(trailers)' origin/main..HEAD
~~~

Script có thể xác nhận mỗi commit trong nhánh phát hành có <code>Refs</code>, hoặc có <code>Signed-off-by</code> nếu chính sách yêu cầu. Khi kiểm tra đồng tác giả, có thể yêu cầu định dạng tên và email cụ thể.

Không nên mặc định mọi commit đều phải có cùng một trailer. Merge commit tự động, commit sửa tài liệu, commit revert hoặc commit do bot tạo có thể có quy tắc khác. Hãy xác định loại commit và phạm vi kiểm tra trong CI.

### Kiểm tra trailer không đồng nghĩa xác minh sự thật

Một script có thể xác nhận dòng <code>Reviewed-by</code> tồn tại, nhưng không thể chỉ dựa vào dòng đó để chứng minh người review thực sự đã phê duyệt thay đổi. Nếu cần bằng chứng phê duyệt, hãy lấy trạng thái từ hệ thống Pull Request/Merge Request hoặc nền tảng quản lý thay đổi.

Tương tự, <code>Co-authored-by</code> ghi nhận người cộng tác theo khai báo trong commit message. Quy trình nhóm vẫn cần đảm bảo người tạo commit có sự đồng ý của đồng tác giả.

## 13. Những lỗi thường gặp

| Lỗi | Hệ quả | Cách khắc phục |
|---|---|---|
| Đặt trailer giữa body | Công cụ có thể không nhận diện là trailer cuối | Chuyển khối trailer xuống cuối message |
| Viết sai token | Nền tảng không nhận diện hoặc CI bỏ sót | Dùng đúng tên token đã thống nhất |
| Dùng email sai cho đồng tác giả | Nền tảng không liên kết được tài khoản | Xác nhận email với người cộng tác |
| Gộp nhiều đồng tác giả trong một dòng | Parser hoặc UI có thể không tách đúng | Dùng một dòng <code>Co-authored-by</code> cho mỗi người |
| Nghĩ <code>Refs</code> tự đóng issue | Ticket không được cập nhật tự động | Dùng closing keyword theo quy tắc nền tảng nếu cần |
| Nhầm <code>Signed-off-by</code> với chữ ký mật mã | Hiểu sai mức độ xác minh | Phân biệt <code>git commit -s</code> và <code>git commit -S</code> |
| Dùng <code>replace</code> cho trailer nhiều giá trị | Có thể làm mất người đồng tác giả trước đó | Chọn <code>addIfDifferent</code> hoặc chính sách phù hợp |
| Script thêm trailer lặp mỗi lần chạy | Commit message chứa metadata trùng | Cấu hình <code>ifexists</code> và kiểm tra trước khi thêm |
| Sửa trailer của commit đã chia sẻ mà không báo nhóm | Commit hash thay đổi, nhánh cộng tác bị lệch | Phối hợp rewrite hoặc tạo commit bổ sung |

## 14. Quy trình mẫu khi pair programming

Giả sử hai người cùng triển khai tính năng phân trang:

1. Hai người thống nhất ai là người tạo commit và xác nhận email sẽ dùng cho trailer.
2. Người tạo commit stage các thay đổi đã được review.
3. Commit message ghi subject và body mô tả hành vi mới.
4. Thêm một dòng <code>Co-authored-by</code> cho người cộng tác.
5. Thêm <code>Refs</code> cho ticket liên quan.
6. Nếu dự án yêu cầu, thêm <code>Signed-off-by</code> cho người tạo commit theo chính sách DCO.
7. Kiểm tra message bằng <code>git show -s --format='%(trailers)' HEAD</code>.
8. Push branch và mở Pull Request/Merge Request theo quy trình nhóm.

Ví dụ message:

~~~text
feat(list): add cursor pagination

Return a stable next cursor and avoid duplicate items between pages.

Co-authored-by: Lan Pham <lan@example.com>
Refs: LIST-308
Reviewed-by: Tuan Nguyen <tuan@example.com>
~~~

## 15. Bài tập tự kiểm tra

Thực hành trong repository thử nghiệm:

1. Tạo một commit có subject, body và hai trailer <code>Refs</code> cùng <code>Reviewed-by</code>.
2. Thêm hai dòng <code>Co-authored-by</code> và kiểm tra chúng bằng <code>git show</code>.
3. Dùng <code>git interpret-trailers --parse</code> để trích xuất trailer từ file message.
4. Dùng <code>git interpret-trailers --trailer</code> để thêm trailer vào file message.
5. Cấu hình <code>trailer.refs.key</code> và chính sách <code>ifexists</code>, sau đó thử thêm cùng một tham chiếu hai lần.
6. Tạo commit bằng <code>git commit -s</code> và xác định dòng <code>Signed-off-by</code>.
7. Tạo commit ký mật mã bằng <code>git commit -S</code> trong môi trường có signing key và kiểm tra bằng <code>git verify-commit</code>.
8. So sánh author/committer trong commit object với các dòng <code>Co-authored-by</code>.
9. Thử đặt một đoạn văn sau trailer block và quan sát parser nhận diện ra sao.
10. Viết quy ước trailer ngắn cho nhóm: token nào bắt buộc, token nào tùy chọn và ticket được liên kết thế nào.

Trailer giúp commit message mang thêm thông tin có cấu trúc mà vẫn giữ phần mô tả dễ đọc. Hãy dùng token nhất quán, đặt trailer ở cuối message, xác nhận thông tin đồng tác giả và tham chiếu chính xác, đồng thời phân biệt metadata khai báo với cơ chế phê duyệt hoặc chữ ký mật mã thực sự.
