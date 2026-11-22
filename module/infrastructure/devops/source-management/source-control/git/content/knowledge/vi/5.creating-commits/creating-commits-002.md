# Chuẩn bị một commit tập trung vào một thay đổi có ý nghĩa

Một commit tốt là một đơn vị thay đổi có thể đọc, kiểm thử, review và hoàn tác với ít suy đoán. Khi một commit chứa nhiều việc không liên quan, người review khó hiểu mục tiêu, lỗi khó truy tìm và việc revert một phần có thể kéo theo thay đổi không mong muốn. Ngược lại, tách mọi dòng chỉnh sửa thành những commit quá nhỏ, rời rạc cũng làm lịch sử khó theo dõi.

Mục tiêu là tạo một commit tập trung vào **một thay đổi có ý nghĩa và nhất quán**. Commit có thể gồm mã nguồn, kiểm thử, tài liệu và cấu hình nếu tất cả cùng phục vụ một mục tiêu. Những việc độc lập như đổi định dạng hàng loạt, nâng cấp dependency không liên quan hoặc sửa một lỗi khác nên được tách riêng.

Bài học này hướng dẫn cách xác định phạm vi, chọn nội dung đưa vào index, stage theo tệp hoặc từng hunk, kiểm tra snapshot sẽ commit, chạy kiểm thử phù hợp và viết thông điệp giúp người đọc hiểu thay đổi.

## 1. Thế nào là một commit tập trung?

### 1.1. Commit là một đơn vị thay đổi có thể hiểu được

Một commit tập trung trả lời được câu hỏi: **Commit này thay đổi điều gì và vì sao cần thay đổi đó?**

Ví dụ một mục tiêu rõ ràng:

- Thêm kiểm tra địa chỉ thanh toán trước khi tạo đơn hàng.
- Sửa lỗi làm tròn tổng tiền khi áp dụng mã giảm giá.
- Cập nhật hướng dẫn cấu hình biến môi trường cho dịch vụ.
- Thay đổi timeout của client để xử lý một lỗi kết nối đã xác định.

Một commit có thể sửa nhiều tệp nếu chúng là các phần cần thiết của cùng một thay đổi. Ví dụ, bổ sung kiểm tra địa chỉ thanh toán có thể cần:

- Mã kiểm tra dữ liệu đầu vào.
- Unit test cho các trường hợp hợp lệ và không hợp lệ.
- API test xác nhận phản hồi.
- Tài liệu API nếu hợp đồng bên ngoài thay đổi.

Các tệp này thuộc cùng một mục tiêu nên có thể nằm trong một commit.

### 1.2. Phân biệt thay đổi liên quan và thay đổi chỉ tình cờ xuất hiện cùng lúc

Trong lúc làm một tính năng, bạn có thể nhận thấy một lỗi chính tả ở tài liệu khác, một file log cũ hoặc một đoạn code cần format. Không phải mọi thay đổi xuất hiện trong working tree đều thuộc cùng commit.

Ví dụ:

| Thay đổi | Nên đưa vào commit thêm kiểm tra địa chỉ? | Lý do |
| --- | --- | --- |
| Validation cho địa chỉ | Có | Là phần chính của mục tiêu |
| Unit test cho validation | Có | Chứng minh hành vi mới |
| API test cho phản hồi lỗi | Có | Kiểm tra hợp đồng API |
| Tài liệu mô tả trường địa chỉ bắt buộc | Có | Cập nhật cách sử dụng tính năng |
| Đổi format toàn bộ module không liên quan | Không | Khó review và không cần cho mục tiêu |
| Sửa lỗi logging ở một dịch vụ khác | Không | Là công việc độc lập |
| Nâng dependency không liên quan | Không | Tăng phạm vi và rủi ro của commit |

Đây là nguyên tắc về tính liên quan, không phải quy tắc số lượng tệp. Một commit có thể thay đổi nhiều tệp hoặc chỉ một tệp; điều quan trọng là người đọc có thể hiểu chúng cùng phục vụ một kết quả.

### 1.3. Giữ các phần phụ thuộc cần thiết trong cùng commit

Đôi khi một thay đổi không thể build hoặc test nếu thiếu phần đi kèm. Ví dụ, cập nhật API cần cập nhật interface, implementation, test và generated lockfile do dependency bắt buộc thay đổi. Nếu các phần này cần nhau để tạo trạng thái nhất quán, hãy giữ chúng cùng commit.

Không tách một commit đến mức mỗi commit trung gian làm repository không build được, test thất bại hoặc tạo trạng thái không thể review độc lập, trừ khi dự án có quy ước rõ cho chuỗi commit như vậy.

### 1.4. Tự kiểm tra phạm vi bằng một câu

Trước khi stage, thử mô tả commit trong một câu:

- "Thêm kiểm tra địa chỉ thanh toán trước khi tạo đơn."
- "Sửa cách tính tổng tiền khi có giảm giá phần trăm."
- "Bổ sung hướng dẫn chạy migration cho môi trường staging."

Nếu phải dùng nhiều câu không liên quan để mô tả một commit, hãy xem có nên chia nó thành các commit riêng.

## 2. Xem toàn bộ thay đổi trước khi chọn commit

### 2.1. Xác nhận branch và trạng thái repository

Bắt đầu bằng:

~~~bash
git status --short --branch
git branch --show-current
git log -1 --oneline
~~~

Các lệnh này cho biết:

- Bạn đang ở branch nào.
- Có thay đổi staged, unstaged hoặc untracked hay không.
- Commit hiện tại là commit nào.

Nếu đang ở detached HEAD hoặc branch không đúng, dừng lại và xác nhận workflow trước khi commit. Không nên tạo commit trên nhầm branch chỉ vì working tree đang có nội dung cần lưu.

### 2.2. Xem danh sách tệp thay đổi

~~~bash
git status
git diff --name-status
git diff --cached --name-status
git ls-files --others --exclude-standard
~~~

Ý nghĩa:

- git diff --name-status: tệp tracked có thay đổi chưa stage so với index.
- git diff --cached --name-status: thay đổi đã stage so với HEAD.
- git ls-files --others --exclude-standard: tệp untracked không bị ignore.

Xem thống kê:

~~~bash
git diff --stat
git diff --cached --stat
~~~

Danh sách tệp giúp phát hiện thay đổi lạc phạm vi trước khi đọc chi tiết.

### 2.3. Đọc nội dung thay đổi chưa stage

~~~bash
git diff
~~~

Lệnh hiển thị khác biệt giữa working tree và index. Dùng để hiểu những gì đang có trên đĩa nhưng chưa được stage.

Giới hạn một tệp:

~~~bash
git diff -- src/BillingService.java
~~~

Có thể dùng thêm:

~~~bash
git diff --word-diff
~~~

để quan sát thay đổi ở mức từ hoặc token, hữu ích với tài liệu hoặc dòng cấu hình dài.

### 2.4. Đọc nội dung đã stage

~~~bash
git diff --cached
~~~

Đây là bước quan trọng vì commit thông thường lấy nội dung từ index, không lấy toàn bộ nội dung working tree.

Nếu đã stage từ trước, không mặc định rằng phần staged vẫn thuộc công việc hiện tại. Hãy đọc lại toàn bộ diff đã stage để phát hiện file hoặc thay đổi còn sót từ lần làm việc trước.

### 2.5. So sánh tất cả thay đổi với HEAD

~~~bash
git diff HEAD
~~~

Lệnh này cho thấy tổng khác biệt của working tree và index so với commit hiện tại. Nó hữu ích để nhìn tổng thể trước khi chọn phần đưa vào commit.

Tuy nhiên, để biết chính xác nội dung commit kế tiếp, vẫn cần xem git diff --cached vì đó là snapshot đang nằm trong index.

## 3. Lập phạm vi commit trước khi stage

### 3.1. Viết mục tiêu và danh sách phần cần có

Ví dụ, mục tiêu: "Thêm kiểm tra địa chỉ thanh toán trước khi tạo đơn".

Danh sách có thể gồm:

~~~text
src/order/CheckoutService.java
src/order/AddressValidator.java
test/order/CheckoutServiceTest.java
docs/api/checkout.md
~~~

Mỗi tệp có lý do xuất hiện trong commit:

- CheckoutService gọi validator.
- AddressValidator chứa quy tắc kiểm tra.
- Test xác nhận hành vi.
- Tài liệu mô tả yêu cầu địa chỉ.

Nếu git status còn hiển thị file cấu hình IDE hoặc một thay đổi format ở module khác, không stage nó chỉ vì đang có sẵn.

### 3.2. Tách thay đổi độc lập

Giả sử bạn đồng thời:

1. Sửa lỗi kiểm tra địa chỉ.
2. Đổi toàn bộ dấu cách trong module.
3. Nâng version một dependency không liên quan.

Ba việc này có thể review và kiểm thử độc lập. Hãy chuẩn bị commit riêng cho từng mục tiêu nếu dự án cần cả ba.

Nếu thay đổi format là điều kiện để thực hiện refactor hoặc sửa lỗi, hãy giải thích mối quan hệ và cân nhắc giữ phần bắt buộc trong cùng commit. Không tách máy móc theo loại file.

### 3.3. Đừng tách test khỏi hành vi mà test bảo vệ

Một commit thêm validation nhưng không có test liên quan có thể khó review và dễ bị lỗi hồi quy. Nếu test là phần cần thiết để chứng minh thay đổi, hãy đưa test vào cùng commit.

Tương tự, khi thay đổi public API hoặc cách cấu hình, cập nhật tài liệu cần thiết trong cùng commit để snapshot thể hiện một thay đổi hoàn chỉnh.

## 4. Stage đúng nội dung bằng git add

### 4.1. Stage các tệp liên quan theo đường dẫn

Khi thay đổi đã được chia thành các tệp rõ ràng:

~~~bash
git add -- src/order/CheckoutService.java
git add -- src/order/AddressValidator.java
git add -- test/order/CheckoutServiceTest.java
git add -- docs/api/checkout.md
~~~

Có thể stage nhiều đường dẫn cùng lúc:

~~~bash
git add -- src/order/CheckoutService.java src/order/AddressValidator.java test/order/CheckoutServiceTest.java docs/api/checkout.md
~~~

Dấu -- kết thúc phần tùy chọn, giúp đường dẫn bắt đầu bằng dấu gạch đầu dòng không bị hiểu nhầm là option.

Stage theo đường dẫn phù hợp khi mỗi tệp chỉ chứa thay đổi thuộc một mục tiêu.

### 4.2. Hiểu phạm vi của git add -A và git add -u

~~~bash
git add -A
~~~

cập nhật index cho mọi thay đổi trong working tree: thêm, sửa và xóa. Nếu không có pathspec, phạm vi là toàn bộ working tree.

~~~bash
git add -u
~~~

stage thay đổi và xóa của các đường dẫn đã được theo dõi; nó không thêm tệp untracked mới.

Có thể giới hạn phạm vi:

~~~bash
git add -A -- src/order/
git add -u -- src/order/
~~~

Khi mục tiêu là một commit tập trung, tránh dùng git add -A theo thói quen trước khi xem danh sách thay đổi. Nó có thể đưa vào index những tệp không liên quan.

### 4.3. Stage từng phần bằng git add -p

Một tệp có thể chứa nhiều thay đổi thuộc các mục tiêu khác nhau. Khi đó, stage theo toàn bộ tệp sẽ đưa tất cả hunk vào cùng commit.

Dùng:

~~~bash
git add -p -- src/order/CheckoutService.java
~~~

Git hiển thị từng hunk và hỏi bạn muốn xử lý thế nào. Các lựa chọn phổ biến:

| Lựa chọn | Tác dụng |
| --- | --- |
| y | Stage hunk hiện tại |
| n | Bỏ qua hunk hiện tại |
| s | Chia nhỏ hunk nếu có thể |
| e | Chỉnh sửa patch thủ công |
| q | Thoát khỏi chế độ tương tác |
| ? | Hiển thị trợ giúp các lựa chọn |

Ví dụ, CheckoutService có cả thay đổi validation và một đoạn log debug không liên quan. Bạn có thể stage hunk validation, bỏ qua hunk log, rồi xử lý log trong commit riêng.

Sau khi kết thúc, kiểm tra:

~~~bash
git diff --cached -- src/order/CheckoutService.java
git diff -- src/order/CheckoutService.java
~~~

Lệnh đầu hiển thị phần đã chọn; lệnh sau hiển thị phần còn lại chưa stage.

### 4.4. Chia nhỏ hunk để chọn chính xác hơn

Nếu một hunk chứa nhiều dòng thay đổi và Git có thể tách nhỏ, chọn s trong chế độ git add -p.

Nếu Git không thể chia tự động, bạn có thể:

- Chọn stage toàn bộ hunk nếu mọi dòng đều liên quan.
- Dùng e để chỉnh patch nếu hiểu định dạng patch.
- Sắp xếp lại thay đổi trong working tree thành các phần dễ stage hơn.

Không nên chỉnh patch bằng tay nếu chưa hiểu ngữ cảnh dòng context, dấu cộng/trừ và header hunk. Patch sai có thể bị từ chối hoặc tạo snapshot khác với dự định.

### 4.5. Stage patch đã chỉnh sửa bằng editor

~~~bash
git add -e -- src/order/CheckoutService.java
~~~

Lệnh mở patch trong editor để bạn chỉnh những dòng sẽ được stage. Đây là kỹ thuật nâng cao, hữu ích khi cần chọn chính xác phần thay đổi trong một file.

Sau khi lưu patch, Git kiểm tra và áp dụng patch vào index. Hãy kiểm tra ngay:

~~~bash
git diff --cached -- src/order/CheckoutService.java
git diff -- src/order/CheckoutService.java
~~~

Không giả định patch đã chỉnh sửa phản ánh đúng ý định chỉ vì Git chấp nhận nó.

## 5. Kiểm tra và điều chỉnh index

### 5.1. Xem chính xác các tệp sẽ được commit

~~~bash
git diff --cached --name-only
git diff --cached --name-status
~~~

Đọc danh sách này và xác nhận mọi đường dẫn đều thuộc mục tiêu commit.

Xem thống kê:

~~~bash
git diff --cached --stat
~~~

Nếu có file không liên quan, bỏ staging riêng file đó:

~~~bash
git restore --staged -- path/to/unrelated-file
~~~

Lệnh này đưa entry trong index về trạng thái của HEAD cho đường dẫn đó, nhưng giữ nội dung trong working tree. File có thể tiếp tục xuất hiện như modified hoặc untracked tùy trạng thái ban đầu.

### 5.2. Xem patch sẽ được commit

~~~bash
git diff --cached
~~~

Đọc toàn bộ patch, không chỉ phần đầu hoặc thống kê. Kiểm tra:

- Logic có đúng mục tiêu không?
- Có dòng debug hoặc mã thử nghiệm không?
- Có thay đổi định dạng không cần thiết không?
- Có file sinh tự động hoặc file tạm không?
- Có mật khẩu, token, khóa riêng hoặc dữ liệu cá nhân không?
- Có xóa nhầm file hoặc bỏ sót cập nhật liên quan không?
- Test có phản ánh đúng hành vi mới không?

Nếu commit chứa tệp nhị phân, diff có thể không hiển thị nội dung. Kiểm tra tên file, kích thước, loại file và nguồn dữ liệu trước khi commit.

### 5.3. Kiểm tra lỗi whitespace

~~~bash
git diff --cached --check
~~~

Lệnh kiểm tra các lỗi whitespace phổ biến trong patch đã stage, chẳng hạn trailing whitespace hoặc dòng mới có vấn đề. Nó không thay thế formatter, linter hay review code.

### 5.4. Kiểm tra cả phần chưa stage

~~~bash
git diff
git status --short
~~~

Phần chưa stage có thể là thay đổi bạn cố ý để dành cho commit sau. Hãy xác nhận chúng không làm bạn hiểu nhầm rằng commit hiện tại đã chứa mọi nội dung đang nhìn thấy trong editor.

Nếu một file có cả staged và unstaged changes, trạng thái ngắn có thể hiển thị MM hoặc các ký hiệu tương ứng. Đọc cả hai cột để phân biệt thay đổi trong index với thay đổi bổ sung ở working tree.

### 5.5. Đưa một file ra khỏi staging

Nếu stage nhầm toàn bộ một file:

~~~bash
git restore --staged -- src/UnrelatedService.java
~~~

Nếu chỉ muốn bỏ stage một số hunk, có thể dùng:

~~~bash
git restore --staged -p -- src/order/CheckoutService.java
~~~

Trong các phiên bản Git cũ, có thể dùng:

~~~bash
git reset -p HEAD -- src/order/CheckoutService.java
~~~

Các lệnh trên thay đổi index; chúng không có mục đích xóa nội dung working tree. Sau khi bỏ staging, hãy xem lại cả git diff và git diff --cached.

## 6. Kiểm thử đúng thay đổi sẽ commit

### 6.1. Chọn kiểm thử phù hợp với phạm vi

Commit tập trung nên có bằng chứng kiểm thử tương ứng. Ví dụ:

- Thay đổi hàm xử lý: chạy unit test liên quan.
- Thay đổi API: chạy API/integration test phù hợp.
- Thay đổi migration: kiểm tra migration trên database thử nghiệm.
- Thay đổi cấu hình build: chạy build hoặc task xác minh cấu hình.
- Thay đổi tài liệu: kiểm tra liên kết, cú pháp hoặc lệnh được hướng dẫn nếu có.

Không nhất thiết mọi commit đều cần chạy toàn bộ test suite. Hãy chọn kiểm thử đủ để xác nhận mục tiêu và nêu rõ giới hạn nếu có test chưa chạy.

### 6.2. Kiểm thử sau khi stage

Một quy trình tốt là stage phần thay đổi liên quan, xem lại patch rồi chạy test trước commit. Điều này giúp bạn biết snapshot dự định đưa vào lịch sử.

Tuy nhiên, nếu một tệp có cả phần staged và unstaged, chương trình test thường đọc nội dung working tree, tức là có thể bao gồm cả phần chưa stage. Khi đó, kết quả test chưa chắc chứng minh chính xác snapshot trong index hoạt động.

### 6.3. Cô lập phần chưa stage khi cần kiểm thử chính xác

Nếu bạn đã stage một số hunk và muốn test đúng phiên bản staged, có thể tạm cất phần còn lại:

~~~bash
git stash push --keep-index -u -m "Temporarily save unstaged work"
~~~

Tùy chọn --keep-index giữ thay đổi đã stage trong index và working tree; phần chưa stage cùng tệp untracked được đưa vào stash khi dùng -u. Sau đó chạy test trên nội dung còn lại trong working tree.

Khi hoàn tất kiểm thử, khôi phục phần công việc đã cất:

~~~bash
git stash pop
~~~

Lưu ý, stash pop có thể phát sinh conflict nếu trạng thái repository đã thay đổi. Kiểm tra git status trước và sau thao tác; không xóa stash cho đến khi xác nhận các thay đổi đã được khôi phục.

Nếu workflow của bạn không cần staging từng hunk trong cùng một file, cách đơn giản hơn là hoàn thành một nhóm thay đổi, stage và test nhóm đó trước khi bắt đầu nhóm tiếp theo.

### 6.4. Chạy kiểm tra sau khi hook thay đổi nội dung

Repository có thể cấu hình pre-commit hook hoặc công cụ tự động format/lint. Một số hook chỉ kiểm tra; một số hook có thể sửa file hoặc index.

Sau khi chạy commit hoặc hook, kiểm tra lại:

~~~bash
git status
git diff
git diff --cached
~~~

Nếu hook thay đổi nội dung, hãy xem diff, stage phần cần thiết và chạy lại kiểm tra phù hợp trước khi tạo commit hoàn chỉnh.

## 7. Viết thông điệp commit rõ ràng

### 7.1. Subject nên mô tả thay đổi

Một thông điệp commit có subject ngắn gọn giúp người đọc hiểu mục tiêu ngay trong log.

Ví dụ tốt:

~~~text
Validate billing address before checkout
~~~

Một số ví dụ kém rõ:

~~~text
Update code
Fix bug
Changes
Work in progress
~~~

Subject nên dùng động từ chủ động, mô tả hành động hoặc kết quả. Không cần đưa mọi chi tiết triển khai vào dòng đầu.

### 7.2. Dùng body để giải thích lý do

Khi thay đổi cần thêm bối cảnh, dùng body:

~~~text
Validate billing address before checkout

Reject checkout requests when the billing address is missing
or incomplete. This prevents orders from being created with
unusable billing information.

Add unit and API tests for valid and invalid address cases.
~~~

Body nên giải thích vì sao thay đổi cần thiết, hành vi nào thay đổi và điểm nào người review cần chú ý. Không lặp lại subject bằng những câu khác.

### 7.3. Đặt quy ước subject nhất quán

Một số nhóm dùng Conventional Commits:

~~~text
feat: validate billing address before checkout
fix: round discounted totals correctly
docs: explain staging deployment settings
test: cover invalid checkout addresses
~~~

Đây là quy ước tùy chọn của dự án, không phải yêu cầu bắt buộc của Git. Nếu repository đã có CONTRIBUTING.md hoặc commit convention, hãy tuân theo quy ước của nhóm.

Một số gợi ý phổ biến:

- Dùng một dòng subject ngắn, dễ đọc trong log.
- Tránh dấu chấm ở cuối subject nếu quy ước nhóm không yêu cầu.
- Dùng body cho lý do và bối cảnh.
- Có thể tham chiếu issue hoặc ticket theo định dạng dự án.
- Tránh đưa thông tin bí mật hoặc dữ liệu cá nhân vào commit message.

### 7.4. Tạo commit bằng -m hoặc editor

Commit với một dòng:

~~~bash
git commit -m "Validate billing address before checkout"
~~~

Commit có body:

~~~bash
git commit -m "Validate billing address before checkout" -m "Reject incomplete addresses before creating an order. Add unit and API coverage for invalid input."
~~~

Hoặc mở editor:

~~~bash
git commit
~~~

Editor cho phép viết subject và body nhiều dòng. Git thường dùng dòng đầu làm subject; dòng trống phân cách subject và body.

### 7.5. Kiểm tra danh tính commit

Nếu Git báo thiếu author identity, kiểm tra:

~~~bash
git config --show-origin --get user.name
git config --show-origin --get user.email
~~~

Cấu hình cho repository hiện tại:

~~~bash
git config user.name "Developer Name"
git config user.email "developer@example.com"
~~~

Chỉ dùng thông tin danh tính được tổ chức hoặc dự án yêu cầu. Không đưa email riêng hoặc thông tin cá nhân vào repository nếu chính sách yêu cầu địa chỉ no-reply.

## 8. Tạo commit và xác minh kết quả

### 8.1. Kiểm tra lần cuối trước commit

~~~bash
git status
git diff --cached --name-status
git diff --cached --check
git diff --cached
~~~

Xác nhận:

- Đúng branch.
- Đúng các tệp và hunk.
- Không còn nội dung debug hoặc bí mật.
- Test phù hợp đã chạy.
- Commit message mô tả đúng mục tiêu.

### 8.2. Tạo commit

~~~bash
git commit -m "Validate billing address before checkout"
~~~

Git tạo commit từ index hiện tại. Những thay đổi chỉ có trong working tree mà chưa stage không được đưa vào commit.

### 8.3. Xác minh commit mới

~~~bash
git show --stat --oneline HEAD
git show --format=fuller --no-ext-diff HEAD
git status --short --branch
~~~

Đọc lại commit để xác nhận đúng nội dung đã được ghi. Nếu còn thay đổi chưa stage hoặc untracked, chúng vẫn xuất hiện trong trạng thái repository sau commit.

### 8.4. Commit không đồng nghĩa với push

git commit ghi snapshot vào lịch sử local. Nó không tự gửi commit lên remote.

Khi đã review và sẵn sàng chia sẻ, mới push theo workflow của nhóm:

~~~bash
git push
~~~

Commit tập trung giúp người khác review dễ hơn sau khi bạn push hoặc mở pull request.

## 9. Ví dụ thực tế: tách một thay đổi khỏi công việc đang dang dở

Giả sử bạn đang làm tính năng checkout và working tree có các thay đổi:

~~~text
 M src/order/CheckoutService.java
 M src/order/AddressValidator.java
 M test/order/CheckoutServiceTest.java
 M docs/api/checkout.md
 M src/report/MonthlyReport.java
?? tmp/request-dump.txt
~~~

Mục tiêu commit hiện tại là thêm kiểm tra địa chỉ thanh toán. Thay đổi MonthlyReport và file dump không thuộc mục tiêu.

### Bước 1 — Xem diff và xác định phạm vi

~~~bash
git diff -- src/order/CheckoutService.java
git diff -- src/order/AddressValidator.java
git diff -- test/order/CheckoutServiceTest.java
git diff -- docs/api/checkout.md
git diff -- src/report/MonthlyReport.java
~~~

Xác nhận file dump không chứa dữ liệu cần lưu. Không stage file tạm.

### Bước 2 — Stage các tệp liên quan

~~~bash
git add -- src/order/CheckoutService.java src/order/AddressValidator.java test/order/CheckoutServiceTest.java docs/api/checkout.md
~~~

### Bước 3 — Kiểm tra snapshot staged

~~~bash
git diff --cached --name-status
git diff --cached
git diff --cached --check
~~~

Nếu nội dung MonthlyReport hoặc tmp/request-dump.txt xuất hiện trong staged diff, bỏ staging hoặc sửa lại phạm vi trước khi tiếp tục.

### Bước 4 — Chạy test

Ví dụ:

~~~bash
./gradlew test --tests "com.example.order.CheckoutServiceTest"
~~~

Chọn task và tên test đúng với dự án thực tế. Nếu test phụ thuộc các thay đổi chưa stage khác, hãy cô lập chúng hoặc ghi rõ giới hạn kiểm thử.

### Bước 5 — Commit

~~~bash
git commit -m "Validate billing address before checkout"
~~~

### Bước 6 — Xác nhận phần còn lại

~~~bash
git status --short
git show --stat --oneline HEAD
~~~

Các thay đổi MonthlyReport và file tạm không thuộc commit. Chúng vẫn ở working tree để xử lý trong công việc riêng.

## 10. Những sai lầm thường gặp

- **Stage toàn bộ theo thói quen:** git add -A có thể đưa thay đổi không liên quan vào index. Xem status và diff trước khi stage.
- **Chỉ xem danh sách file mà không đọc patch:** một file có thể chứa nhiều mục tiêu khác nhau. Dùng git diff --cached để đọc nội dung thực tế.
- **Tách test khỏi tính năng:** commit có thể không chứng minh được hành vi mới. Đưa test liên quan vào cùng đơn vị thay đổi.
- **Gộp format diện rộng với sửa logic:** review khó phân biệt thay đổi chức năng. Tách format độc lập nếu không cần thiết cho mục tiêu.
- **Nghĩ commit lấy mọi thứ trong editor:** commit thông thường lấy index. Kiểm tra staged diff trước khi commit.
- **Bỏ qua phần unstaged trong cùng file:** file có thể chứa cả phiên bản staged và phần sửa mới. Kiểm tra cả git diff và git diff --cached.
- **Chạy test trên working tree rồi mặc định staged snapshot đã được test:** khi cùng file còn unstaged edits, test có thể chạy cả phần chưa stage.
- **Commit message quá chung chung:** người đọc không hiểu mục tiêu hoặc lý do. Viết subject cụ thể và body khi cần.
- **Đưa secret vào commit:** kiểm tra diff để tránh token, password, private key hoặc dữ liệu nhạy cảm.
- **Cho rằng commit đã được chia sẻ:** commit chỉ nằm trong lịch sử local cho đến khi push hoặc được trao đổi bằng phương thức khác.

## 11. Checklist trước khi tạo commit

- [ ] Đã xác nhận branch và mục tiêu thay đổi.
- [ ] Có thể mô tả commit bằng một câu rõ ràng.
- [ ] Các tệp trong commit đều phục vụ cùng mục tiêu.
- [ ] Những thay đổi độc lập đã được tách riêng.
- [ ] Đã kiểm tra cả staged và unstaged diff.
- [ ] Đã stage đúng tệp hoặc hunk.
- [ ] Đã đọc toàn bộ git diff --cached.
- [ ] Đã kiểm tra whitespace bằng git diff --cached --check.
- [ ] Không có debug code, file tạm, secret hoặc dữ liệu không cần thiết.
- [ ] Đã chạy test, build hoặc kiểm tra phù hợp.
- [ ] Nếu có phần unstaged cùng tệp, đã hiểu test đang chạy trên nội dung nào.
- [ ] Commit message mô tả hành động và lý do đủ rõ.
- [ ] Sau commit đã kiểm tra lại git show và git status.

## 12. Bảng tra cứu nhanh

| Mục tiêu | Lệnh |
| --- | --- |
| Xem branch và trạng thái | git status --short --branch |
| Xem tệp thay đổi chưa stage | git diff --name-status |
| Xem tệp đã stage | git diff --cached --name-status |
| Xem toàn bộ thay đổi so với HEAD | git diff HEAD |
| Stage tệp cụ thể | git add -- path/to/file |
| Stage tất cả thay đổi | git add -A |
| Stage thay đổi của file tracked | git add -u |
| Stage từng hunk | git add -p -- path/to/file |
| Chỉnh patch trước khi stage | git add -e -- path/to/file |
| Xem patch đã stage | git diff --cached |
| Kiểm tra whitespace | git diff --cached --check |
| Bỏ stage cả tệp | git restore --staged -- path/to/file |
| Bỏ stage từng hunk | git restore --staged -p -- path/to/file |
| Tạm cất phần chưa stage để test | git stash push --keep-index -u |
| Khôi phục phần đã cất | git stash pop |
| Tạo commit có subject | git commit -m "message" |
| Xem commit vừa tạo | git show --stat --oneline HEAD |
| Kiểm tra trạng thái sau commit | git status --short --branch |

## 13. Tổng kết

Một commit tập trung gom những thay đổi cần thiết để tạo ra một kết quả nhất quán, có thể hiểu, review, kiểm thử và hoàn tác. Hãy bắt đầu bằng việc xác định mục tiêu, xem toàn bộ thay đổi, tách phần độc lập rồi stage đúng tệp hoặc từng hunk.

Trước khi commit, đọc git diff --cached, kiểm tra whitespace, chạy test phù hợp và viết thông điệp mô tả rõ hành động cùng lý do. Nhớ rằng commit lấy nội dung từ index; phần còn lại trong working tree không tự động được đưa vào lịch sử.

Lịch sử có các commit rõ ràng giúp việc review, tìm nguyên nhân lỗi, cherry-pick và revert trở nên dễ kiểm soát. Chất lượng commit được quyết định bởi tính nhất quán của thay đổi, không phải bởi số lượng tệp hay số dòng thay đổi.

