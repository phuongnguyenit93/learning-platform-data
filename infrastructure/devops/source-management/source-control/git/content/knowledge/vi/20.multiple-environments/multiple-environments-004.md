# Phân biệt chữ hoa chữ thường và xử lý đổi tên chỉ khác hoa thường

Git lưu tên đường dẫn với đúng chữ hoa, chữ thường trong cây commit và index. Tuy nhiên, việc hệ điều hành có thể tạo hoặc phân biệt hai tệp chỉ khác casing hay không phụ thuộc filesystem và cấu hình của môi trường. Vì vậy, một thao tác đổi tên như `PaymentService.js` thành `paymentService.js` có thể hoạt động bình thường trên filesystem phân biệt hoa thường nhưng không được nhận diện như mong muốn trên Windows hoặc macOS với cấu hình filesystem mặc định không phân biệt hoa thường.

Khi dự án được phát triển trên nhiều hệ điều hành, khác biệt này có thể gây lỗi checkout, merge, build hoặc import. Bài học này giải thích cách Git xử lý casing, vai trò của `core.ignorecase`, cách đổi tên chỉ khác hoa thường an toàn và cách xử lý xung đột khi các nhánh dùng tên đường dẫn khác casing.

## 1. Git lưu tên đường dẫn như thế nào?

### 1.1. Casing là một phần của tên đường dẫn

Trong commit, Git lưu cây thư mục gồm tên đường dẫn, mode và đối tượng nội dung. Tên tệp được lưu theo đúng ký tự, bao gồm chữ hoa và chữ thường.

Ví dụ, Git có thể lưu hai đường dẫn khác nhau:

- `src/PaymentService.js`
- `src/paymentService.js`

Trên filesystem phân biệt hoa thường, hai đường dẫn này có thể là hai tệp độc lập. Trên filesystem không phân biệt hoa thường, chúng có thể cùng được xem là một tên. Điều này tạo ra giới hạn khi checkout repository có hai đường dẫn chỉ khác casing.

Có thể xem chính xác tên đường dẫn được lưu trong commit hiện tại:

~~~bash
git ls-tree -r --name-only HEAD
~~~

Xem các đường dẫn đang được index theo dõi:

~~~bash
git ls-files
~~~

Các lệnh này giúp phát hiện casing mà Git ghi nhận, kể cả khi cách hiển thị trong File Explorer hoặc trình quản lý tệp không thể hiện rõ sự khác biệt.

### 1.2. Phân biệt case-sensitive và case-insensitive

Một filesystem **case-sensitive** phân biệt chữ hoa và chữ thường. Ví dụ, `Config.yml` và `config.yml` là hai đường dẫn khác nhau.

Một filesystem **case-insensitive** không phân biệt casing khi tìm đường dẫn. Hai tên trên có thể được xem là cùng một tệp, dù filesystem vẫn giữ cách viết hoa/thường ban đầu để hiển thị. Đây thường là chế độ mặc định trên nhiều máy Windows và macOS, nhưng cấu hình cụ thể có thể khác.

| Môi trường | Hành vi thường gặp | Lưu ý |
| --- | --- | --- |
| Linux với ext4 | Phân biệt hoa thường | Một số filesystem hoặc lớp lưu trữ khác có hành vi riêng |
| Windows với NTFS | Thường không phân biệt hoa thường, nhưng giữ casing | Windows có hỗ trợ bật case sensitivity theo từng thư mục trong một số cấu hình |
| macOS với APFS | Thường không phân biệt hoa thường, nhưng giữ casing | APFS có thể được định dạng theo chế độ case-sensitive hoặc case-insensitive |

Không nên chỉ dựa vào tên hệ điều hành để kết luận. Một máy macOS có thể dùng volume case-sensitive; một thư mục Windows có thể được bật case sensitivity. Hành vi thực tế phụ thuộc filesystem và cấu hình thư mục chứa repository.

### 1.3. Vấn đề khi làm việc đa môi trường

Giả sử một lập trình viên trên Linux đổi tên:

~~~text
src/PaymentService.js
        ->
src/paymentService.js
~~~

Trên Linux, Git và filesystem có thể nhận diện hai tên là khác nhau. Khi commit, cây Git ghi nhận tên mới chính xác.

Một đồng đội trên Windows có thể gặp vấn đề nếu filesystem không phân biệt hoa thường:

- Lệnh checkout hoặc merge có thể không thể tạo đường dẫn mới do đường dẫn cũ được xem là cùng tên.
- Một thao tác đổi casing trong File Explorer có thể không tạo ra thay đổi mà Git nhận diện.
- Các tệp hoặc import có casing không thống nhất có thể vẫn chạy trên máy này nhưng thất bại trong môi trường Linux.
- Hai nhánh tạo hai đường dẫn chỉ khác casing có thể không thể checkout đồng thời trên cùng working tree.

Đây là vấn đề phối hợp giữa tên đường dẫn trong Git và khả năng biểu diễn của filesystem, không nhất thiết là lỗi nội dung của tệp.

## 2. Vai trò của core.ignorecase

### 2.1. core.ignorecase là gì?

`core.ignorecase` là cấu hình ảnh hưởng cách Git xử lý khác biệt hoa thường của tên đường dẫn trong working tree. Git thường kiểm tra filesystem khi tạo hoặc clone repository và thiết lập giá trị phù hợp cho các filesystem không phân biệt hoa thường.

Xem cấu hình hiện tại:

~~~bash
git config --show-origin --get core.ignorecase
~~~

Nếu lệnh không in giá trị, khóa này có thể chưa được đặt tường minh trong các file cấu hình. Có thể xem các cấu hình liên quan:

~~~bash
git config --show-origin --list
~~~

Khi `core.ignorecase=true`, Git áp dụng cách xử lý tương thích với filesystem không phân biệt hoa thường. Điều đó giúp Git tránh một số nhầm lẫn khi dò tìm đường dẫn trong working tree.

### 2.2. core.ignorecase không thay đổi filesystem

Cần phân biệt:

- Filesystem quyết định hệ điều hành có thể tạo và phân biệt các đường dẫn khác casing hay không.
- `core.ignorecase` điều chỉnh cách Git xử lý tên đường dẫn trong môi trường đó.

Đặt `core.ignorecase=false` không biến NTFS hoặc APFS case-insensitive thành filesystem case-sensitive. Nếu filesystem vẫn coi hai tên là một, Git có thể gặp trạng thái khó xử lý khi index chứa đường dẫn khác casing so với working tree.

Không nên đổi cấu hình chỉ để ép Git nhận một lần đổi tên. Hãy dùng quy trình đổi tên phù hợp với filesystem và chỉ điều chỉnh cấu hình khi bạn hiểu rõ hành vi môi trường, có lý do cụ thể và đã kiểm tra ảnh hưởng.

### 2.3. Không đồng nhất cấu hình của mọi máy

Trong nhóm đa môi trường, các máy có thể có giá trị `core.ignorecase` khác nhau do filesystem khác nhau. Đây không nhất thiết là lỗi cấu hình.

Điều nhóm cần thống nhất là:

- Quy ước casing cho tên tệp, thư mục, package và module.
- Không tạo hai đường dẫn chỉ khác hoa thường trong cùng một thư mục nếu dự án phải hỗ trợ filesystem case-insensitive.
- Mọi lần đổi casing phải được Git ghi nhận rõ ràng.
- CI nên có môi trường phù hợp để phát hiện đường dẫn hoặc import sai casing.

Không nên commit một giá trị `core.ignorecase` dùng chung với mục đích ép tất cả máy có filesystem khác nhau hành xử giống nhau.

## 3. Đổi tên tệp chỉ khác hoa thường

### 3.1. Vì sao đổi tên trực tiếp có thể không được ghi nhận?

Giả sử tệp đang được theo dõi có tên:

`src/PaymentService.js`

Bạn muốn đổi thành:

`src/paymentService.js`

Trên filesystem case-insensitive, lệnh đổi tên trực tiếp hoặc thao tác qua giao diện có thể bị xem như đổi tên thành chính tệp đó. Git có thể không hiển thị thay đổi, hoặc working tree giữ casing cũ.

Kiểm tra trước:

~~~bash
git status --short
git ls-files -- src/PaymentService.js
~~~

Nếu thao tác đổi casing không được Git nhận diện, dùng một tên trung gian để tạo hai bước đổi tên rõ ràng.

### 3.2. Cách an toàn: đổi qua tên tạm

Giả sử muốn đổi `PaymentService.js` thành `paymentService.js`. Dùng một tên tạm khác hoàn toàn:

~~~bash
git mv -- src/PaymentService.js src/PaymentService.__case_tmp__
git mv -- src/PaymentService.__case_tmp__ src/paymentService.js
~~~

Bước đầu chuyển tệp sang tên trung gian. Bước thứ hai chuyển từ tên trung gian sang tên đích với casing mong muốn. Vì tên trung gian khác hẳn tên ban đầu, filesystem case-insensitive vẫn có thể thực hiện được.

Tên tạm chỉ là một bước trong working tree và index; bạn không cần tạo commit riêng cho tên tạm. Sau hai lệnh, kiểm tra:

~~~bash
git status --short
git diff --cached --summary
git ls-files -- src/paymentService.js
~~~

Kết quả mong đợi là index ghi nhận đường dẫn đích với casing mới và không còn đường dẫn cũ. Nếu tên tạm đã tồn tại, chọn một tên khác chưa được sử dụng.

### 3.3. Có thể đổi trực tiếp bằng git mv không?

Trên một số filesystem và phiên bản Git, lệnh đổi tên trực tiếp có thể hoạt động:

~~~bash
git mv -- src/PaymentService.js src/paymentService.js
~~~

Tuy nhiên, trên môi trường case-insensitive, thao tác này có thể không được xử lý như mong muốn do filesystem xem nguồn và đích là cùng một đường dẫn. Quy trình qua tên tạm thường dễ dự đoán hơn khi cần bảo đảm casing được ghi vào index.

Tùy chọn `-f` của `git mv` cho phép ghi đè đích trong một số tình huống, nhưng không biến filesystem thành case-sensitive và không nên dùng để giải quyết mù quáng một xung đột casing. Hãy kiểm tra đường dẫn đích trước khi dùng.

### 3.4. Nếu đã đổi tên bằng File Explorer hoặc trình quản lý tệp

Nếu thao tác đổi tên bên ngoài Git không được nhận diện:

1. Kiểm tra tên Git đang theo dõi bằng `git ls-files`.
2. Đổi sang tên trung gian khác casing rõ ràng.
3. Đổi từ tên trung gian sang tên đích mong muốn.
4. Kiểm tra lại bằng `git status` và `git diff --cached --summary`.
5. Nếu cần, stage đường dẫn đã đổi bằng `git add -A -- src`.

Không nên xóa index hoặc chỉnh sửa trực tiếp các tệp metadata trong thư mục Git để ép thay đổi casing.

## 4. Kiểm tra rename đã được ghi nhận đúng

### 4.1. Xem trạng thái trước commit

Sau khi dùng `git mv`, Git thường stage thao tác đổi đường dẫn ngay lập tức. Kiểm tra:

~~~bash
git status
git diff --cached --summary
git diff --cached --name-status
~~~

Git có thể hiển thị dạng:

~~~text
R100    src/PaymentService.js    src/paymentService.js
~~~

`R100` là cách Git trình bày thay đổi được nhận diện là rename với độ tương đồng 100%. Git không lưu một loại đối tượng rename riêng; khi so sánh hai cây, Git suy luận rename từ đường dẫn bị xóa và đường dẫn được thêm dựa trên nội dung tương đồng.

Vì vậy, phần trăm và cách hiển thị rename có thể thay đổi nếu nội dung tệp cũng được chỉnh sửa đáng kể.

### 4.2. Kiểm tra đường dẫn chính xác trong index

~~~bash
git ls-files --stage
~~~

Hoặc giới hạn vào thư mục:

~~~bash
git ls-files --stage -- src
~~~

Kiểm tra rằng chỉ có đường dẫn đúng casing mà nhóm đã thống nhất. Trên filesystem case-insensitive, không thể chỉ dựa vào việc mở tệp theo tên khác casing vì hệ điều hành có thể vẫn mở cùng một tệp.

### 4.3. Commit và kiểm tra sau commit

Sau khi xác nhận diff:

~~~bash
git diff --cached
git commit -m "Rename PaymentService with canonical casing"
~~~

Kiểm tra cây commit:

~~~bash
git ls-tree -r --name-only HEAD
git show --summary --format=short HEAD
~~~

Cây commit cần chứa đúng đường dẫn với casing mới. Đây là bằng chứng quan trọng hơn việc File Explorer đang hiển thị tên tệp như thế nào.

## 5. Xử lý hai nhánh đổi tên khác casing

### 5.1. Tình huống rename/rename

Giả sử hai nhánh cùng bắt đầu từ `src/PaymentService.js`:

- Nhánh A đổi tên thành `src/paymentService.js`.
- Nhánh B đổi tên thành `src/PAYMENTSERVICE.js`.

Hoặc hai nhánh đổi cùng một tệp thành hai tên khác nhau về chữ hoa/thường. Git có thể phát hiện rename conflict hoặc path collision tùy nội dung, filesystem và cách phát hiện rename.

Trên filesystem case-sensitive, hai tên khác casing có thể cùng tồn tại. Trên filesystem case-insensitive, chúng có thể đụng nhau vì hệ điều hành coi là cùng đường dẫn.

### 5.2. Kiểm tra trước khi giải quyết

Bắt đầu bằng:

~~~bash
git status
git diff --name-only --diff-filter=U
git ls-files -u
git log --oneline --graph --decorate --all -10
~~~

Nếu cần xem các phiên bản ở từng stage của một đường dẫn đang conflict:

~~~bash
git show :1:src/PaymentService.js
git show :2:src/PaymentService.js
git show :3:src/PaymentService.js
~~~

Stage 1 là base, stage 2 là ours và stage 3 là theirs trong merge thông thường. Một số stage có thể không tồn tại nếu một phía đã đổi tên hoặc xóa đường dẫn. Khi đó hãy kiểm tra cả danh sách từ `git ls-files -u` và các đường dẫn mới mà Git báo.

Trong rebase, cách hiểu ours/theirs có thể gây nhầm lẫn; hãy xác định thao tác hiện tại và xem nội dung commit thực tế trước khi chọn.

### 5.3. Thống nhất một cách viết chuẩn

Nhóm cần quyết định một đường dẫn cuối cùng. Ví dụ, thống nhất dùng:

`src/paymentService.js`

Sau đó:

1. So sánh nội dung từ các nhánh và giữ lại tất cả thay đổi cần thiết.
2. Xác định đường dẫn chuẩn và loại bỏ đường dẫn casing cũ nếu không còn dùng.
3. Nếu filesystem không nhận diện đổi casing, di chuyển qua tên tạm.
4. Stage cả thay đổi thêm, sửa, xóa liên quan.
5. Kiểm tra index để bảo đảm chỉ còn một đường dẫn chuẩn.

Ví dụ khi working tree đã được sắp xếp theo quyết định:

~~~bash
git add -A -- src
git status
git ls-files --stage -- src
git diff --cached --summary
~~~

Chỉ stage thư mục hoặc đường dẫn sau khi đã kiểm tra các thay đổi khác trong phạm vi đó để tránh đưa nội dung không liên quan vào merge.

Khi không còn mục unmerged và nội dung đã được kiểm tra, hoàn tất:

~~~bash
git merge --continue
~~~

Nếu đang rebase, dùng `git rebase --continue`. Không xóa thủ công tệp conflict hoặc metadata để kết thúc thao tác.

### 5.4. Nếu checkout hoặc merge không thể tạo hai đường dẫn khác casing

Nếu repository có đồng thời `Config.yml` và `config.yml`, filesystem case-insensitive có thể không thể checkout cả hai. Lệnh checkout/merge có thể báo lỗi tạo tệp, ghi đè hoặc path collision.

Cách giải quyết bền vững là thống nhất đổi tên một hoặc cả hai đường dẫn để chúng khác nhau ngoài casing, rồi commit việc chuẩn hóa trên nhánh có thể xử lý được. Nếu cần kiểm tra hoặc giải quyết nội dung hiện tại mà filesystem không thể biểu diễn, dùng một clone hoặc môi trường làm việc trên filesystem case-sensitive.

Không cố khắc phục bằng cách chỉ đặt `core.ignorecase=false`: cấu hình đó không thay đổi khả năng phân biệt tên của filesystem.

## 6. Lỗi casing trong code và cấu hình dự án

### 6.1. Code chạy trên máy này nhưng lỗi trên máy khác

Một đường dẫn import hoặc tham chiếu có thể dùng casing không khớp với tên tệp thật:

~~~text
Tên tệp: src/paymentService.js
Import:   ./PaymentService.js
~~~

Trên môi trường không phân biệt hoa thường, import có thể vẫn được phân giải. Trên môi trường case-sensitive, đường dẫn không khớp và build hoặc test thất bại.

Các vị trí cần kiểm tra:

- Import trong mã nguồn.
- Đường dẫn trong cấu hình build.
- Tên package, module và thư mục.
- Script triển khai và script test.
- Đường dẫn tài nguyên trong HTML, CSS hoặc cấu hình.
- Liên kết tài liệu và đường dẫn sinh tự động.

Tên định danh trong ngôn ngữ lập trình cũng có thể phân biệt hoa thường, ngay cả khi filesystem không phân biệt. Không nên giả định quy tắc của tên biến, class hoặc package giống với quy tắc của filesystem.

### 6.2. Kiểm tra trên môi trường case-sensitive

CI chạy trên Linux thường giúp phát hiện các đường dẫn import sai casing mà máy Windows hoặc macOS case-insensitive có thể bỏ qua.

Một quy trình phù hợp:

1. Kiểm tra tên tệp chính xác trong Git bằng `git ls-files`.
2. Đối chiếu các import hoặc tham chiếu với casing của đường dẫn.
3. Chạy build và test trên môi trường case-sensitive.
4. Kiểm tra cả script và tài nguyên được tải bằng đường dẫn.
5. Sửa tham chiếu và đổi tên tệp bằng quy trình Git đã thống nhất.

CI không tự sửa tên đường dẫn. Nó giúp phát hiện lỗi sớm trước khi thay đổi được tích hợp hoặc phát hành.

## 7. Quy ước nhóm để tránh xung đột casing

Một nhóm làm việc đa hệ điều hành nên có quy ước rõ ràng:

- Chọn cách viết nhất quán cho tên thư mục và tệp, ví dụ PascalCase cho tên class Java hoặc kebab-case cho tài liệu.
- Không tạo hai tệp trong cùng thư mục chỉ khác chữ hoa/thường.
- Khi đổi casing, dùng `git mv` và tên trung gian nếu filesystem không nhận diện thay đổi trực tiếp.
- Kiểm tra đường dẫn trong import, cấu hình, script và tài liệu sau khi rename.
- Review diff rename trước commit; không chỉ dựa vào thông báo của trình quản lý tệp.
- Chạy CI trên filesystem case-sensitive nếu dự án cần hỗ trợ Linux.
- Khi phát sinh collision giữa các nhánh, thống nhất một đường dẫn chuẩn và tích hợp nội dung trước khi hoàn tất merge.

Nếu một dự án đã có nhiều đường dẫn chỉ khác casing, hãy lập kế hoạch chuẩn hóa riêng. Đổi tên hàng loạt có thể ảnh hưởng import, build, script và liên kết; nên chia nhỏ theo nhóm chức năng và kiểm tra sau mỗi nhóm.

## 8. Ví dụ tổng hợp: đổi tên tệp chỉ khác casing trên Windows

Giả sử repository đang theo dõi:

`src/PaymentService.js`

Nhóm quyết định chuẩn hóa thành:

`src/paymentService.js`

Trên máy Windows với filesystem mặc định case-insensitive, đổi tên trực tiếp có thể không được Git ghi nhận. Thực hiện:

**Bước 1 — Kiểm tra trạng thái**

~~~bash
git status --short
git ls-files -- src/PaymentService.js
~~~

**Bước 2 — Đổi qua tên tạm**

~~~bash
git mv -- src/PaymentService.js src/PaymentService.__case_tmp__
git mv -- src/PaymentService.__case_tmp__ src/paymentService.js
~~~

**Bước 3 — Kiểm tra thay đổi được stage**

~~~bash
git status
git diff --cached --summary
git ls-files --stage -- src
~~~

Xác nhận index có đường dẫn `src/paymentService.js` và không còn đường dẫn cũ.

**Bước 4 — Cập nhật các tham chiếu**

Tìm và sửa import, cấu hình build, script hoặc tài liệu đang dùng tên cũ. Casing trong tham chiếu phải khớp chính xác với tên mới.

**Bước 5 — Kiểm tra và commit**

~~~bash
git diff --cached
git diff
~~~

Chạy build/test theo dự án, sau đó:

~~~bash
git add -- path/to/changed-importer
git diff --cached --check
git commit -m "Normalize PaymentService filename casing"
~~~

**Bước 6 — Kiểm tra cây commit**

~~~bash
git ls-tree -r --name-only HEAD
git show --summary --format=short HEAD
~~~

Nếu commit đã được push, các thành viên cần fetch và cập nhật nhánh theo quy trình nhóm. Máy case-insensitive có thể cần thao tác checkout mới hoặc đổi tên qua tên tạm nếu đang giữ đường dẫn cũ.

## 9. Bảng tra cứu nhanh

| Nhu cầu | Lệnh |
| --- | --- |
| Xem casing trong commit hiện tại | `git ls-tree -r --name-only HEAD` |
| Xem đường dẫn trong index | `git ls-files` |
| Xem cấu hình ignorecase | `git config --show-origin --get core.ignorecase` |
| Đổi tên qua tên tạm | `git mv -- old-name temp-name` rồi `git mv -- temp-name new-name` |
| Kiểm tra rename đã stage | `git diff --cached --summary` |
| Xem tên và trạng thái thay đổi | `git status --short` |
| Xem các đường dẫn conflict | `git diff --name-only --diff-filter=U` |
| Xem index stage khi conflict | `git ls-files -u` |
| Stage lại thay đổi theo đường dẫn | `git add -A -- path` |
| Xem tên tệp trong commit mới | `git ls-tree -r --name-only HEAD` |

## 10. Tổng kết

Git lưu tên đường dẫn với đúng casing, nhưng filesystem của máy phát triển có thể phân biệt hoặc không phân biệt chữ hoa thường. `core.ignorecase` giúp Git thích ứng với filesystem, nhưng không thay đổi quy tắc của hệ điều hành.

Khi đổi tên chỉ khác hoa thường trên filesystem case-insensitive, quy trình qua một tên tạm với hai lệnh `git mv` thường giúp Git ghi nhận chính xác. Sau đó hãy kiểm tra index, diff và cây commit để xác nhận tên mới đã được lưu đúng.

Trong nhóm đa môi trường, cần thống nhất casing, tránh hai đường dẫn chỉ khác hoa thường và chạy CI trên môi trường case-sensitive khi phù hợp. Cách làm này giúp hạn chế lỗi checkout, merge, import và build khi cùng một repository được sử dụng trên Windows, macOS và Linux.

