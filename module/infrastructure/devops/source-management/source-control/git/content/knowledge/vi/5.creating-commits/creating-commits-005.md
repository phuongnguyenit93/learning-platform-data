# Viết thông điệp commit có tiêu đề, ngữ cảnh và lý do thay đổi

Một commit lưu snapshot của index cùng thông tin tác giả, committer, thời điểm và thông điệp mô tả thay đổi. Nội dung code cho biết dự án đã thay đổi như thế nào; thông điệp commit giúp người đọc hiểu thay đổi đó nhằm giải quyết việc gì và vì sao cần thực hiện. Một thông điệp rõ ràng giúp review lịch sử, tìm nguyên nhân hồi quy, chọn commit để revert hoặc hiểu quyết định kỹ thuật sau nhiều tháng.

Thông điệp tốt thường có ba phần: tiêu đề ngắn nêu hành động chính, phần thân cung cấp ngữ cảnh và lý do, và các trailer có cấu trúc khi cần gắn thông tin như issue, người review hoặc sign-off. Không phải commit nào cũng cần đủ cả ba phần, nhưng người viết cần biết khi nào phần thân hoặc trailer thực sự có giá trị.

Sau bài này, bạn có thể:

- Viết subject ngắn gọn, mô tả đúng thay đổi.
- Viết body giải thích bối cảnh, lý do và hệ quả quan trọng.
- Phân biệt nội dung thông điệp với phần diff của commit.
- Dùng quy ước câu chữ, độ dài dòng và thì động từ nhất quán.
- Thêm trailer như Refs, Fixes, Reviewed-by hoặc Signed-off-by đúng mục đích.
- Nhập thông điệp bằng editor, -m hoặc template.
- Kiểm tra thông điệp sau khi commit và cải thiện thông điệp yếu.

## 1. Thông điệp commit giúp người đọc điều gì?

Một người đọc lịch sử có thể chưa biết bối cảnh lúc thay đổi được tạo ra. Họ thường cần trả lời nhanh ba câu hỏi:

1. **Thay đổi chính là gì?** Subject nên cho biết hành động hoặc kết quả quan trọng nhất.
2. **Vì sao cần thay đổi?** Body giải thích vấn đề, yêu cầu hoặc quyết định dẫn tới thay đổi.
3. **Thay đổi liên quan tới việc nào?** Trailer có thể liên kết issue, ghi nhận sign-off hoặc metadata theo quy trình của nhóm.

Không nên dùng thông điệp để chép lại từng dòng code. Diff đã chứa chi tiết đó. Thông điệp bổ sung thông tin mà diff không thể tự nói rõ, chẳng hạn nguyên nhân của một workaround, giới hạn tương thích, trade-off hoặc điều kiện vận hành.

Ví dụ:

~~~text
Fix search results when the query contains accents

Normalize the query before matching so that user input and
stored labels use the same comparison form. Keep the original
query for display to avoid changing what the user entered.

Fixes: #184
~~~

Subject nêu kết quả chính. Body giải thích vì sao cần chuẩn hóa và nêu quyết định giữ nguyên chuỗi hiển thị. Trailer liên kết commit với issue.

## 2. Cấu trúc subject, body và trailer

Một thông điệp commit nhiều dòng thường có dạng:

~~~text
Short subject that summarizes the change

Context: what problem or requirement led to this change.
Reason: why this approach is appropriate and what it changes.
Important constraints, side effects, or trade-offs.

Trailer-Name: value
Another-Trailer: value
~~~

| Phần | Mục đích | Câu hỏi cần trả lời |
| --- | --- | --- |
| Subject | Tóm tắt thay đổi chính trong một dòng. | Commit này làm gì? |
| Body | Cung cấp bối cảnh, lý do, cách tiếp cận và hệ quả đáng chú ý. | Vì sao làm và người đọc cần biết điều gì? |
| Trailer | Ghi metadata có cấu trúc ở cuối thông điệp. | Commit liên quan tới issue, sign-off hoặc người nào? |

Giữa subject và body để một dòng trống. Nếu có body và trailer, nên để một dòng trống giữa phần giải thích và các trailer để dễ đọc.

Một commit nhỏ, hiển nhiên có thể chỉ cần subject. Một thay đổi ảnh hưởng tới hành vi, sửa lỗi khó hiểu hoặc có quyết định thiết kế thường nên có body. Chỉ thêm trailer khi dự án có quy ước hoặc thông tin đó thực sự cần được máy móc và con người đọc.

## 3. Viết subject ngắn và có thông tin

Subject là phần thường xuất hiện trong git log --oneline, danh sách pull request và thông báo commit. Người đọc nên hiểu được ý chính mà không cần mở diff ngay.

Một subject tốt thường:

- Bắt đầu bằng động từ mô tả hành động: Add, Fix, Remove, Prevent, Document, Refactor.
- Nêu đối tượng hoặc hành vi bị tác động.
- Tránh câu chung chung như “Update code” hoặc “Fix bug”.
- Không kết thúc bằng dấu chấm nếu nhóm dùng quy ước subject dạng câu lệnh.
- Tập trung vào một thay đổi chính.

Ví dụ:

| Subject yếu | Subject rõ hơn |
| --- | --- |
| Update search | Normalize accented search queries |
| Fix bug | Prevent duplicate invoices after retry |
| Changes | Reject expired access tokens |
| Refactor code | Extract date parsing from report service |
| Update files | Document local hook installation |

### Dùng dạng mệnh lệnh hay mô tả?

Nhiều dự án chọn dạng mệnh lệnh trong subject, ví dụ Add retry limit thay vì Added retry limit hoặc Adds retry limit. Có thể hiểu subject như câu hoàn thành “If applied, this commit will …”.

Đây là quy ước giúp lịch sử nhất quán, không phải điều kiện kỹ thuật bắt buộc của Git. Nếu dự án đã có style guide khác, hãy theo quy ước hiện hành.

### Độ dài subject

Một quy ước phổ biến là giữ subject khoảng 50 ký tự và tránh vượt 72 ký tự. Đây là hướng dẫn giúp subject hiển thị tốt trong terminal và công cụ review, không phải giới hạn cứng của Git. Nếu cần dài hơn để tránh mơ hồ, hãy ưu tiên sự rõ ràng và cắt bỏ từ thừa.

Subject không nên chứa toàn bộ giải thích. Nếu cần thêm lý do, hãy viết body thay vì biến subject thành một đoạn văn.

## 4. Body giải thích ngữ cảnh và lý do

Body không cần lặp lại subject bằng cách diễn đạt khác. Hãy dùng phần này để ghi những thông tin mà người đọc khó suy ra từ diff.

Những câu hỏi hữu ích khi viết body:

- Vấn đề nào đang xảy ra?
- Hành vi cũ gây khó khăn hoặc rủi ro gì?
- Vì sao chọn cách giải quyết này?
- Có phương án nào đã cân nhắc nhưng không chọn không, và vì sao?
- Có ảnh hưởng tới API, dữ liệu, hiệu năng hoặc vận hành không?
- Có giới hạn hoặc bước triển khai nào người khác cần biết không?

Ví dụ body cho một thay đổi sửa lỗi:

~~~text
Prevent duplicate invoices after retry

The payment provider can retry a callback when the first response
times out. The old handler created a new invoice for each callback,
even when the provider sent the same event identifier.

Store the provider event ID with a uniqueness constraint and return
the existing invoice for repeated events. This makes callback
processing idempotent without changing the customer-facing flow.
~~~

Body nêu bối cảnh timeout, nguyên nhân tạo bản ghi trùng, cách xử lý và lý do chọn uniqueness constraint. Người đọc hiểu quyết định mà không phải tự suy luận từ nhiều file.

### Ghi cả điều không thay đổi khi điều đó quan trọng

Một thông điệp tốt có thể nói rõ một ranh giới dễ bị hiểu nhầm. Ví dụ, “Keep the original query for display” giải thích rằng việc chuẩn hóa chỉ dùng cho matching, không thay đổi nội dung người dùng nhìn thấy. Không cần liệt kê mọi phần không thay đổi; chỉ nêu điều có ý nghĩa với review hoặc vận hành.

### Không biến body thành bản sao diff

Tránh các câu như:

~~~text
Changed line 10.
Added a new if statement.
Updated method search().
~~~

Những câu này mô tả thao tác sửa code, nhưng không nói lý do. Hãy giải thích hành vi hoặc vấn đề mà thay đổi giải quyết.

## 5. Độ dài dòng và cách trình bày

Một quy ước thường dùng:

- Subject khoảng 50 ký tự.
- Body wrap ở khoảng 72 ký tự mỗi dòng.
- Để dòng trống giữa subject và body.
- Để dòng trống trước trailer.
- Dùng đoạn văn ngắn, mỗi đoạn tập trung vào một ý.

Đây là quy ước đọc dễ hơn, không phải giới hạn của định dạng commit. Git có thể lưu thông điệp dài hơn hoặc một dòng duy nhất. Điều quan trọng là thông điệp không bị cắt cụt, khó đọc hoặc thiếu ngữ cảnh.

Không cần xuống dòng thủ công sau mỗi vài từ trong subject. Với body dài, wrap theo câu để terminal và công cụ xem lịch sử trình bày tốt.

## 6. Viết thông điệp cho các loại thay đổi khác nhau

### Thêm tính năng

Subject nên nói rõ tính năng hoặc khả năng mới:

~~~text
Add export to CSV for monthly reports
~~~

Body có thể giải thích ai cần chức năng, dữ liệu nào được xuất, các giới hạn định dạng hoặc vì sao chọn CSV.

### Sửa lỗi

Subject nêu hành vi lỗi được sửa:

~~~text
Prevent empty passwords from passing validation
~~~

Body giải thích điều kiện gây lỗi, tác động và cách xử lý mới. Nếu lỗi chỉ xảy ra trong một môi trường cụ thể, ghi lại môi trường đó khi nó giúp người đọc hiểu nguyên nhân.

### Refactor

Subject mô tả cấu trúc hoặc trách nhiệm được thay đổi:

~~~text
Extract token parsing into a dedicated service
~~~

Body nên nói lý do cần tách, ranh giới trách nhiệm mới và xác nhận hành vi bên ngoài có được giữ nguyên hay không nếu đó là điều quan trọng.

### Thay đổi tài liệu hoặc cấu hình

~~~text
Document the required local Git hooks
~~~

Body có thể nêu đối tượng người đọc, bước thiết lập mới hoặc tác động của cấu hình tới môi trường phát triển.

### Thay đổi phá vỡ tương thích

Nếu thay đổi làm client hoặc hệ thống phụ thuộc phải điều chỉnh, hãy nêu rõ trong body và dùng trailer theo quy ước dự án nếu có:

~~~text
Remove the legacy token response field

All supported clients now read the token from the response header.
Keeping the old field would expose two competing sources of truth.
Update integrations before deploying this version.

BREAKING CHANGE: The token field is no longer included in the JSON response.
~~~

Đừng gắn nhãn breaking change chỉ vì nội bộ code được refactor. Chỉ dùng khi có thay đổi tương thích thực sự cần người dùng hoặc hệ thống phụ thuộc biết.

## 7. Trailer là gì?

Trailer là các dòng metadata có cấu trúc ở cuối thông điệp commit. Chúng thường có dạng Token: value và được đặt sau phần body.

Một số trailer thường gặp:

| Trailer | Ý nghĩa thường dùng |
| --- | --- |
| Refs: #123 | Liên kết commit với issue hoặc công việc liên quan. |
| Fixes: #123 | Đánh dấu commit sửa issue theo quy ước của nền tảng hoặc dự án. |
| Reviewed-by: Name <email> | Ghi nhận người review nếu quy trình yêu cầu. |
| Signed-off-by: Name <email> | Ghi nhận sign-off theo Developer Certificate of Origin hoặc chính sách dự án. |
| Co-authored-by: Name <email> | Ghi nhận đồng tác giả theo quy ước được công cụ hỗ trợ. |
| BREAKING CHANGE: description | Mô tả thay đổi không tương thích trong các quy ước như Conventional Commits. |

Không phải mọi hệ thống đều tự động hiểu mọi trailer. Một số nền tảng nhận diện Fixes, Closes hoặc Signed-off-by; dự án khác có thể dùng token riêng. Hãy theo quy ước đang được cấu hình.

Trailer khác với câu văn thông thường ở chỗ chúng có cấu trúc để công cụ có thể trích xuất. Không thêm tên người hoặc email giả định; chỉ ghi thông tin đã được xác nhận và phù hợp với quy trình.

### Kiểm tra trailer bằng Git

Git có lệnh interpret-trailers để đọc, thêm hoặc chuẩn hóa trailer:

~~~bash
git interpret-trailers --parse
~~~

Lệnh đọc thông điệp từ standard input. Ví dụ:

~~~bash
git log -1 --format=%B | git interpret-trailers --parse
~~~

Để thêm trailer vào một file thông điệp:

~~~bash
git interpret-trailers --trailer "Refs: #184" --in-place commit-message.txt
~~~

Hãy kiểm tra kết quả file trước khi dùng nó làm commit message. Cách diễn giải trailer và quy tắc trùng lặp có thể được cấu hình, nên không giả định mọi token đều được xử lý giống nhau ở mọi dự án.

## 8. Conventional Commits là một quy ước tùy chọn

Một số nhóm dùng Conventional Commits để chuẩn hóa subject:

~~~text
<type>[optional scope]: <description>

[optional body]

[optional footer(s)]
~~~

Ví dụ:

~~~text
feat(search): normalize accented queries

Normalize user input before matching so that accented and
unaccented labels can be compared consistently.

Fixes: #184
~~~

Các type phổ biến:

| Type | Cách dùng thường gặp |
| --- | --- |
| feat | Thêm tính năng. |
| fix | Sửa lỗi. |
| docs | Thay đổi tài liệu. |
| refactor | Thay đổi cấu trúc code mà không nhằm thêm tính năng hoặc sửa lỗi trực tiếp. |
| test | Thêm hoặc sửa kiểm thử. |
| build | Thay đổi hệ thống build hoặc dependency. |
| ci | Thay đổi cấu hình CI. |
| chore | Công việc bảo trì khác theo quy ước nhóm. |

Scope trong ngoặc giúp giới hạn khu vực thay đổi, ví dụ feat(auth): add role-based access checks. Dấu ! sau type/scope có thể dùng để biểu thị breaking change:

~~~text
feat(api)!: remove the legacy token field
~~~

Conventional Commits không phải định dạng bắt buộc của Git. Nếu nhóm dùng nó, cần thống nhất type, scope, quy tắc breaking change và cách liên kết issue. Không nên trộn nhiều quy ước trong cùng một lịch sử nếu không có lý do.

## 9. Tạo commit message bằng editor

Thông thường, chạy:

~~~bash
git commit
~~~

Git mở editor được cấu hình để bạn viết nhiều dòng. Mẫu cơ bản:

~~~text
Add retry limit to webhook delivery

The provider retries callbacks when the response is delayed.
Limit repeated attempts and record the final delivery status so
operators can identify callbacks that need manual review.

Refs: #246
~~~

Lưu và đóng editor để tạo commit. Nếu thông điệp chỉ có subject thì có thể bỏ body và trailer.

Git dùng editor theo cấu hình core.editor hoặc biến môi trường liên quan. Xem cấu hình:

~~~bash
git config --show-origin --get core.editor
~~~

Nếu editor không mở đúng, cấu hình editor phù hợp với môi trường của bạn:

~~~bash
git config --global core.editor "code --wait"
~~~

Ví dụ trên phù hợp khi Visual Studio Code đã được cài và lệnh code có trong PATH. Thay bằng editor nhóm đang dùng nếu khác.

## 10. Dùng -m khi thông điệp ngắn

Với commit đơn giản, có thể truyền subject trực tiếp:

~~~bash
git commit -m "Fix null handling in search results"
~~~

Để truyền body, dùng nhiều tùy chọn -m; mỗi giá trị tạo thành một đoạn thông điệp, giữa các đoạn có dòng trống:

~~~bash
git commit -m "Fix null handling in search results" -m "The API can return a missing label for archived records. Treat the label as optional so the result list remains available."
~~~

Với body dài hoặc có trailer, editor thường dễ viết và rà soát hơn. Khi dùng shell, cần chú ý dấu nháy và ký tự đặc biệt theo cú pháp của shell hiện tại.

Không truyền một đoạn body quá dài vào một chuỗi -m nếu nó khó đọc hoặc khó review. Mục tiêu là thông điệp dễ hiểu trong lịch sử, không chỉ là làm lệnh chạy được.

## 11. Dùng template để thống nhất cách viết

Nếu nhóm muốn mọi người nhớ đủ bối cảnh và lý do, có thể tạo file template:

~~~text
<Short subject: action and affected behavior>

Context:
Why is this change needed?

Approach:
What was changed and why was this approach chosen?

Impact:
Any compatibility, data, performance, or operational notes?

Refs:
~~~

Cấu hình template cho repository:

~~~bash
git config --local commit.template .gitmessage
~~~

Hoặc cấu hình global nếu muốn dùng cho nhiều repository:

~~~bash
git config --global commit.template ~/.gitmessage
~~~

File template là gợi ý mở trong editor; người viết vẫn cần thay nội dung mẫu bằng thông tin thực tế. Tránh commit template chứa placeholder chưa được thay. Nếu nhóm dùng template ở cấp repository, hãy lưu file template trong repository và hướng dẫn thành viên cấu hình local.

## 12. Xem diff khi đang viết thông điệp

Để Git hiển thị diff staged trong editor khi tạo commit:

~~~bash
git commit -v
~~~

Chế độ verbose giúp bạn đối chiếu subject và body với thay đổi thực tế. Diff được đưa vào vùng hỗ trợ khi soạn thảo và không trở thành nội dung thông điệp commit sau khi Git xử lý cleanup.

Trước khi commit, vẫn nên kiểm tra staging area:

~~~bash
git status
git diff --cached
~~~

Thông điệp tốt không thể bù cho việc stage nhầm file. Hãy xác nhận snapshot dự kiến đúng phạm vi rồi mới mô tả nó.

## 13. Kiểm tra thông điệp sau khi tạo commit

Xem commit mới nhất:

~~~bash
git log -1
~~~

Xem riêng subject:

~~~bash
git log -1 --format=%s
~~~

Xem toàn bộ message body:

~~~bash
git log -1 --format=%B
~~~

Xem author và committer:

~~~bash
git log -1 --format=fuller
~~~

Xem message cùng diff:

~~~bash
git show --format=fuller --stat HEAD
~~~

Đọc lại thông điệp trong bối cảnh người khác không tham gia thay đổi. Nếu subject mơ hồ hoặc body không giải thích được lý do, hãy cải thiện trước khi chia sẻ commit với nhóm.

## 14. Sửa thông điệp commit gần nhất

Nếu commit gần nhất chưa được chia sẻ và bạn chỉ cần sửa message, dùng:

~~~bash
git commit --amend
~~~

Editor mở thông điệp cũ để chỉnh sửa. Nếu chỉ thay message mà không thay nội dung staged, commit mới vẫn có object ID khác vì message là một phần của commit object.

Có thể thay subject trực tiếp:

~~~bash
git commit --amend -m "Clarify search fallback behavior"
~~~

--amend thay thế commit gần nhất bằng một commit mới. Nếu commit cũ đã được push hoặc người khác dựa vào nó, amend làm thay đổi lịch sử và có thể cần phối hợp trước khi cập nhật remote. Với commit đã chia sẻ, hãy theo chính sách nhóm thay vì tự ý rewrite lịch sử.

Nếu amend cả nội dung, kiểm tra staging area trước vì Git sẽ dùng index hiện tại để tạo snapshot mới:

~~~bash
git status
git diff --cached
git commit --amend
~~~

## 15. Những lỗi thường gặp

### Subject chỉ ghi “Update code”

Người đọc không biết khu vực hoặc hành vi nào thay đổi. Thêm động từ và đối tượng cụ thể, ví dụ Reject expired refresh tokens.

### Body lặp lại subject

Body nên bổ sung bối cảnh, lý do, cách tiếp cận hoặc hệ quả. Nếu không có gì đáng bổ sung, một subject tốt có thể đủ.

### Mô tả file thay vì mô tả lý do

“Changed Search.java” không giải thích mục tiêu. Hãy nói hành vi nào được sửa và vấn đề nào được giải quyết.

### Nhồi mọi thông tin vào subject

Subject cần tóm tắt. Chuyển nguyên nhân, trade-off và lưu ý triển khai sang body.

### Trailer đặt giữa body

Đặt trailer ở cuối thông điệp và tách khỏi body bằng dòng trống để người và công cụ dễ nhận diện.

### Dùng Fixes cho issue không thực sự được sửa

Chỉ dùng trailer đóng issue khi commit thực sự giải quyết issue và nền tảng hiểu cú pháp đó. Nếu chỉ liên quan, dùng Refs hoặc token theo quy ước.

### Nghĩ Git tự bắt buộc subject 50 ký tự hoặc body 72 ký tự

Đây là hướng dẫn style, không phải giới hạn cứng của Git. Dự án có thể dùng hook hoặc CI để kiểm tra quy tắc riêng.

### Dùng --amend sau khi commit đã được chia sẻ

Amend tạo commit mới và thay đổi lịch sử. Kiểm tra trạng thái chia sẻ và chính sách nhóm trước khi rewrite commit đã được người khác sử dụng.

## 16. Quy trình thực hành: viết một commit message đầy đủ

Giả sử bạn vừa sửa lỗi webhook được gửi lặp:

~~~bash
# 1. Xác nhận trạng thái
git status --short

# 2. Xem chính xác nội dung đã stage
git diff --cached

# 3. Mở editor để viết subject, body và trailer
git commit

# 4. Đọc lại message và metadata
git log -1 --format=fuller

# 5. Kiểm tra snapshot của commit
git show --stat --oneline HEAD
~~~

Thông điệp có thể là:

~~~text
Prevent duplicate invoices after webhook retries

The payment provider can resend an event when the first callback
times out. The previous handler created a second invoice because
it did not check whether the event had already been processed.

Store the provider event ID with a uniqueness constraint and
return the existing invoice for repeated callbacks. This keeps
processing idempotent without changing the customer workflow.

Fixes: #246
~~~

Trước khi hoàn tất, tự hỏi:

- Subject có cho biết hành động và đối tượng chính không?
- Body có giải thích bối cảnh và lý do, thay vì chép lại diff không?
- Có nêu trade-off hoặc tác động mà reviewer cần biết không?
- Trailer có đúng cú pháp và đúng mục đích của dự án không?
- Thông điệp có mô tả đúng những gì đã stage không?

## 17. Ghi nhớ

- Subject tóm tắt thay đổi chính; body giải thích ngữ cảnh, lý do và hệ quả đáng chú ý.
- Để một dòng trống giữa subject và body; đặt trailer ở cuối và tách bằng dòng trống.
- Ưu tiên subject cụ thể, thường bắt đầu bằng động từ và nêu hành vi hoặc đối tượng thay đổi.
- Quy ước subject khoảng 50 ký tự và body khoảng 72 ký tự là hướng dẫn đọc dễ, không phải giới hạn Git.
- Không chép lại diff trong body; giải thích thông tin mà diff không thể tự nói rõ.
- Trailer như Refs, Fixes, Reviewed-by, Signed-off-by và Co-authored-by cần theo quy ước dự án.
- Conventional Commits là một style tùy chọn, không phải yêu cầu bắt buộc của Git.
- Dùng editor cho thông điệp nhiều dòng; -m phù hợp với message ngắn.
- Kiểm tra staging area trước khi commit và đọc lại message bằng git log sau khi tạo.
- git commit --amend tạo commit mới và có thể rewrite lịch sử đã chia sẻ.

Một thông điệp commit tốt giúp người đọc hiểu thay đổi, bối cảnh và lý do mà không phải tái dựng toàn bộ câu chuyện từ diff. Khi subject rõ, body đủ ngữ cảnh và trailer đúng quy ước, lịch sử Git trở thành tài liệu kỹ thuật hữu ích cho review, bảo trì và điều tra sự cố.
