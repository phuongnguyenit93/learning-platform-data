# Xử lý xung đột đổi tên, đổi kiểu tệp và tệp nhị phân

Khi hai nhánh cùng thay đổi một tệp, Git thường có thể kết hợp nội dung tự động. Tuy nhiên, không phải thay đổi nào cũng chỉ là sửa vài dòng văn bản. Một nhánh có thể đổi tên tệp trong khi nhánh kia tiếp tục sửa tên cũ; hai nhánh có thể chuyển một tệp từ thường sang symbolic link hoặc thay đổi quyền thực thi; hoặc cả hai cùng cập nhật một ảnh, tài liệu thiết kế hay tệp lưu trữ nhị phân. Những tình huống này đòi hỏi người phát triển hiểu Git đang giữ những phiên bản nào và quyết định trạng thái cuối cùng của tệp.

Bài học này tập trung vào ba nhóm xung đột: đổi tên, đổi kiểu hoặc thuộc tính tệp mà Git theo dõi, và tệp nhị phân. Mục tiêu là biết cách nhận diện xung đột, kiểm tra dữ liệu ở từng phía, chọn hoặc kết hợp phiên bản đúng, rồi hoàn tất merge hoặc rebase mà vẫn giữ được lịch sử có ý nghĩa.

## 1. Hiểu trạng thái xung đột trước khi sửa

### 1.1. Xung đột không phải lúc nào cũng có dấu đánh dấu trong tệp

Với tệp văn bản, Git thường chèn các dấu phân cách như `<<<<<<<`, `=======` và `>>>>>>>` vào vùng không thể tự kết hợp. Người phát triển có thể mở tệp, chỉnh nội dung rồi xóa các dấu này.

Nhưng với đổi tên, thay đổi kiểu tệp hoặc dữ liệu nhị phân, xung đột có thể nằm ở tên đường dẫn, loại đối tượng hoặc phiên bản dữ liệu. Khi đó, Git có thể không chèn dấu phân cách vào tệp. Một tệp nhị phân cũng không thể được ghép theo từng dòng như mã nguồn.

Vì vậy, hãy bắt đầu bằng trạng thái repository thay vì chỉ tìm dấu `<<<<<<<`.

~~~bash
git status
git status --short
git diff --name-only --diff-filter=U
git ls-files -u
~~~

Các lệnh này có mục đích khác nhau:

- `git status` mô tả thao tác đang dở và các đường dẫn còn xung đột.
- `git status --short` cho trạng thái ngắn gọn, thuận tiện khi có nhiều tệp.
- `git diff --name-only --diff-filter=U` liệt kê những đường dẫn đang ở trạng thái chưa hợp nhất.
- `git ls-files -u` hiển thị các mục chưa hợp nhất trong index, gồm mode, mã đối tượng, số stage và đường dẫn.

Không nên bắt đầu sửa bằng cách xóa tệp hoặc chạy `git add .` ngay lập tức. Trước tiên cần biết tệp nào đang xung đột, Git nhìn thấy những phiên bản nào và thay đổi cuối cùng cần đáp ứng yêu cầu gì.

### 1.2. Ba stage trong index

Trong một thao tác merge ba chiều, Git có thể giữ tối đa ba phiên bản cho một đường dẫn xung đột:

| Stage | Ý nghĩa | Cách hiểu |
| --- | --- | --- |
| 1 | Base | Phiên bản chung tại điểm hai nhánh tách nhau |
| 2 | Ours | Phiên bản của nhánh hiện tại đang nhận thay đổi |
| 3 | Theirs | Phiên bản từ nhánh được tích hợp vào |

Có thể xem các mục này bằng:

~~~bash
git ls-files -u -- path/to/file
~~~

Kết quả thường có dạng gồm mode, mã đối tượng, stage và đường dẫn. Stage 1 là cơ sở để so sánh; stage 2 và stage 3 là hai phía đang cần hòa giải. Một đường dẫn có thể thiếu một stage, chẳng hạn khi một phía đã xóa tệp.

Trong thao tác merge thông thường, “ours” là nhánh đang đứng và “theirs” là nhánh được merge vào. Khi rebase, cách gọi này dễ gây nhầm: “ours” thường là nhánh đích mà các commit đang được phát lại lên, còn “theirs” là commit của nhánh đang rebase. Vì vậy, trước khi chọn một phía bằng lệnh, hãy kiểm tra bạn đang thực hiện merge hay rebase và xác định nội dung thực tế của từng phiên bản.

## 2. Xử lý xung đột đổi tên tệp

### 2.1. Vì sao đổi tên có thể tạo xung đột?

Git lưu cây thư mục và nội dung tệp trong các commit. Git không lưu một thao tác “rename” riêng như một đối tượng lịch sử. Khi so sánh hai trạng thái, Git suy luận một tệp đã được đổi tên dựa trên mức độ tương đồng giữa nội dung cũ và nội dung mới.

Cơ chế phát hiện đổi tên giúp Git nhận ra nhiều trường hợp di chuyển tệp, nhưng kết quả phụ thuộc vào nội dung và ngưỡng tương đồng. Nếu hai nhánh cùng đổi tên một tệp theo hai hướng khác nhau, hoặc một nhánh đổi tên trong khi nhánh kia sửa hay xóa tệp cũ, Git có thể không tự quyết định được đường dẫn cuối cùng.

Các trường hợp thường gặp:

- **Rename/rename:** cả hai nhánh đổi cùng một tệp sang hai tên khác nhau.
- **Rename/delete:** một nhánh đổi tên, nhánh còn lại xóa tệp.
- **Rename/modify:** một nhánh đổi tên, nhánh còn lại sửa nội dung ở đường dẫn cũ.
- **Rename/add hoặc trùng đường dẫn:** tên mới được dùng cho một tệp khác ở nhánh còn lại.
- **File/directory:** một nhánh dùng một đường dẫn làm tệp, nhánh kia dùng cùng đường dẫn làm thư mục chứa các tệp con.

Không phải trường hợp nào cũng có cùng cách hiển thị. Hãy dùng `git status` để xem thông báo và đường dẫn cụ thể.

### 2.2. Ví dụ hai nhánh đổi tên cùng một tài liệu

Giả sử nhánh `feature/setup-guide` đổi:

- `docs/guide.md` thành `docs/setup.md`.

Trong khi đó, nhánh `main` đổi cùng tệp:

- `docs/guide.md` thành `docs/installation.md`, đồng thời cập nhật nội dung hướng dẫn.

Khi merge, Git có thể báo xung đột rename/rename. Git không thể tự biết tên nào là tên chuẩn mà dự án muốn sử dụng.

Trước tiên, kiểm tra trạng thái:

~~~bash
git status
git ls-files -u
~~~

Sau đó quyết định đường dẫn cuối cùng dựa trên cấu trúc tài liệu và quy ước đặt tên của dự án. Ví dụ, nhóm thống nhất dùng `docs/setup.md`, nhưng vẫn cần giữ phần cập nhật hữu ích trong phiên bản `docs/installation.md`.

Quy trình xử lý:

1. Mở các phiên bản hiện có và so sánh nội dung. Có thể dùng `git show` với stage cụ thể để xem nội dung từng phía khi đường dẫn tương ứng còn trong index.
2. Chọn tên cuối cùng. Nếu cần, kết hợp nội dung từ cả hai phiên bản vào tệp ở đường dẫn đó.
3. Xóa hoặc di chuyển các đường dẫn không còn dùng trong working tree.
4. Kiểm tra rằng chỉ còn tệp cuối cùng ở đúng vị trí và nội dung đã đầy đủ.
5. Stage các đường dẫn liên quan, bao gồm cả đường dẫn bị xóa và đường dẫn mới.

Ví dụ sau khi đã sắp xếp working tree theo quyết định của nhóm:

~~~bash
git add -A -- docs/guide.md docs/setup.md docs/installation.md
git status
~~~

Tùy trạng thái conflict cụ thể, danh sách đường dẫn cần stage có thể khác. Hãy lấy đúng các đường dẫn Git hiển thị trong `git status`. Tùy chọn `-A` giúp cập nhật cả nội dung mới, nội dung sửa và việc xóa trong phạm vi đường dẫn được chỉ định.

### 2.3. Một nhánh đổi tên, nhánh kia sửa nội dung

Giả sử nhánh A đổi `src/PaymentService.java` thành `src/payment/PaymentService.java`. Nhánh B vẫn sửa `src/PaymentService.java` để thêm kiểm tra đầu vào.

Nếu Git nhận ra quan hệ đổi tên, nó có thể tự áp dụng phần sửa vào đường dẫn mới. Nếu không thể kết hợp, hãy kiểm tra cả hai đường dẫn và lịch sử thay đổi. Đích đến hợp lý thường là giữ tên mới và đưa phần sửa hợp lệ vào tệp ở vị trí mới.

Không nên xóa tệp ở đường dẫn cũ trước khi đã xác nhận nội dung sửa của nhánh kia được giữ lại. Sau khi hợp nhất nội dung và sắp xếp đường dẫn, stage cả thao tác thêm, sửa và xóa:

~~~bash
git add -A -- src/PaymentService.java src/payment/PaymentService.java
git status
~~~

Nếu nhánh kia xóa tệp trong khi nhánh hiện tại đổi tên, nhóm cần quyết định việc xóa có còn đúng với yêu cầu hay không. Nếu chức năng đã bị loại bỏ, có thể chấp nhận xóa. Nếu tệp vẫn cần thiết, giữ phiên bản đã đổi tên và giải thích quyết định trong quá trình review.

### 2.4. Kiểm tra lịch sử đổi tên

Vì Git suy luận việc đổi tên khi so sánh, lịch sử không có một bản ghi rename độc lập. Một số lệnh hữu ích:

~~~bash
git log --follow -- path/to/current-file
git diff -M <commit-cu> <commit-moi>
git diff --summary <commit-cu> <commit-moi>
~~~

- `git log --follow` cố gắng tiếp tục theo lịch sử của tệp qua các lần đổi tên; tùy chọn này chủ yếu hữu ích khi xem lịch sử một tệp.
- `git diff -M` bật phát hiện đổi tên khi so sánh hai trạng thái.
- `git diff --summary` tóm tắt các thay đổi như tạo, xóa, đổi tên hoặc thay đổi mode khi có thể nhận diện.

Các lệnh này giúp hiểu đường đi của tệp, nhưng quyết định tên và nội dung cuối cùng vẫn phải dựa trên yêu cầu của dự án.

## 3. Xử lý xung đột đổi kiểu hoặc thuộc tính tệp

### 3.1. Git theo dõi những thuộc tính nào?

Git không lưu toàn bộ quyền truy cập của hệ điều hành cho mỗi tệp. Với một mục trong cây Git, mode thường gặp gồm:

| Mode | Ý nghĩa |
| --- | --- |
| `100644` | Tệp thường, không có quyền thực thi |
| `100755` | Tệp thường có quyền thực thi |
| `120000` | Symbolic link |
| `160000` | Gitlink, tham chiếu đến một commit của submodule |

Git cũng lưu nội dung tệp, đường dẫn và các đối tượng liên quan. Git không quản lý thư mục rỗng như một đối tượng độc lập.

Có thể kiểm tra mode đã được ghi trong index bằng:

~~~bash
git ls-files --stage -- path/to/file
~~~

Trong lúc xung đột, dùng `git ls-files -u` để so sánh mode và stage của từng phía. Mode khác nhau có thể cho thấy hai nhánh không chỉ sửa nội dung mà còn thay đổi cách Git hiểu đối tượng tại đường dẫn đó.

### 3.2. Thay đổi quyền thực thi

Một tệp script có thể được một nhánh đánh dấu là có quyền thực thi, trong khi nhánh khác bỏ quyền đó. Git chủ yếu quan tâm đến bit thực thi mà nó hỗ trợ, không lưu toàn bộ bộ quyền Unix hoặc ACL của Windows.

Ví dụ, script triển khai cần chạy trực tiếp:

~~~bash
./scripts/deploy.sh
~~~

Nếu tệp phải có quyền thực thi trong repository, mode cần là `100755`. Nếu chỉ là tệp văn bản thông thường, mode thường là `100644`.

Sau khi thống nhất nội dung và kiểu tệp cuối cùng, hãy stage tệp để thay các mục conflict bằng một mục đã chọn trong index. Sau đó đặt rõ mode cần lưu:

~~~bash
git add -- scripts/deploy.sh
git update-index --chmod=+x -- scripts/deploy.sh
~~~

Hoặc bỏ quyền thực thi:

~~~bash
git add -- scripts/deploy.sh
git update-index --chmod=-x -- scripts/deploy.sh
~~~

Kiểm tra lại:

~~~bash
git ls-files --stage -- scripts/deploy.sh
git diff --cached --summary
~~~

Lệnh `git update-index --chmod` cập nhật mode trong index. Nếu nội dung tệp cũng thay đổi, hãy bảo đảm nội dung đúng đã được stage trước khi đặt mode, rồi kiểm tra kết quả cuối cùng.

Trên một số hệ thống tệp hoặc môi trường Windows, quyền thực thi có thể không được hệ thống tệp thể hiện giống Unix. Cấu hình `core.filemode` ảnh hưởng đến việc Git có nhận diện thay đổi bit thực thi từ working tree hay không. Có thể xem cấu hình hiện tại bằng:

~~~bash
git config --get core.filemode
~~~

Không nên thay đổi cấu hình này chỉ để làm biến mất cảnh báo. Hãy xác định mode mà dự án mong muốn và kiểm tra mode đã được lưu trong index.

### 3.3. Tệp thường và symbolic link

Symbolic link là một kiểu đối tượng khác với tệp thường. Git ghi nhận symbolic link bằng mode `120000`; nội dung blob của nó là đường dẫn đích của liên kết. Tệp thường tương ứng có mode `100644` hoặc `100755`.

Ví dụ, một nhánh thay tệp `config/current` thành symbolic link trỏ đến `config/prod.yml`, trong khi nhánh kia tiếp tục cập nhật `config/current` như một tệp cấu hình thông thường. Đây là xung đột về kiểu đối tượng và có thể ảnh hưởng đến cách ứng dụng đọc cấu hình.

Cần xác định ý định của dự án:

- Nếu đường dẫn phải là symbolic link, tạo liên kết đúng đích theo cách được hỗ trợ trên hệ điều hành và môi trường phát triển của nhóm.
- Nếu đường dẫn phải là tệp thường, tạo tệp với nội dung cấu hình đúng.
- Nếu cần đổi sang một đường dẫn mới, cập nhật cả nội dung tham chiếu trong mã nguồn hoặc cấu hình liên quan.

Sau khi working tree có đúng kiểu đối tượng và nội dung, stage đường dẫn:

~~~bash
git add -- config/current
git ls-files --stage -- config/current
~~~

Kết quả cần phản ánh mode mong muốn. Nếu môi trường hiện tại không hỗ trợ tạo symbolic link, hãy phối hợp dùng môi trường có hỗ trợ để kiểm tra kết quả trước khi hoàn tất. Không nên thay symbolic link bằng một tệp văn bản chứa đường dẫn mà không xác nhận dự án có chủ ý dùng cách đó.

### 3.4. Xung đột liên quan đến submodule

Submodule được Git ghi nhận bằng mode `160000`, tức là một tham chiếu đến commit trong repository con. Khi hai nhánh cập nhật submodule đến các commit khác nhau, Git ở repository cha không tự hợp nhất nội dung của repository con như một thư mục mã nguồn bình thường.

Cách xử lý:

1. Kiểm tra đường dẫn submodule và trạng thái bằng `git status`.
2. Chuyển vào repository con, xem log và xác định commit cần sử dụng.
3. Nếu hai dòng lịch sử có thể kết hợp, thực hiện merge hoặc rebase bên trong repository con theo quy trình của dự án.
4. Nếu cần chọn một commit cụ thể, checkout commit đó trong submodule.
5. Quay lại repository cha và stage đường dẫn submodule.

~~~bash
git -C libs/shared status
git -C libs/shared log --oneline --graph --all
git add -- libs/shared
git ls-files --stage -- libs/shared
~~~

Lệnh `git add` trong repository cha ghi nhận commit hiện tại mà submodule đang trỏ tới. Nó không thay thế thao tác giải quyết xung đột nội dung bên trong repository con.

## 4. Xử lý xung đột tệp nhị phân

### 4.1. Vì sao Git không tự ghép tệp nhị phân?

Tệp văn bản có thể được so sánh theo dòng và thường có thể kết hợp những vùng thay đổi độc lập. Tệp nhị phân như ảnh PNG, ảnh thiết kế, tệp âm thanh, video, PDF hoặc tệp lưu trữ thường không có cấu trúc dòng văn bản để Git áp dụng phép ghép ba chiều thông thường.

Nếu hai nhánh cùng thay đổi một tệp nhị phân, Git thường yêu cầu chọn một phiên bản hoặc dùng công cụ chuyên dụng. Có thể thấy thông báo tương tự:

~~~text
warning: Cannot merge binary files: assets/banner.png
CONFLICT (content): Merge conflict in assets/banner.png
~~~

Không có dấu `<<<<<<<` trong tệp ảnh để chỉnh sửa. Mở tệp bằng trình soạn thảo văn bản cũng không giúp giải quyết xung đột và có thể làm hỏng dữ liệu.

### 4.2. Chọn phiên bản từ một phía

Nếu nhóm quyết định dùng nguyên phiên bản từ nhánh hiện tại trong một thao tác merge:

~~~bash
git restore --ours --worktree -- assets/banner.png
git add -- assets/banner.png
~~~

Nếu quyết định dùng phiên bản từ nhánh được merge vào:

~~~bash
git restore --theirs --worktree -- assets/banner.png
git add -- assets/banner.png
~~~

Hai tùy chọn `--ours` và `--theirs` lấy nội dung từ stage 2 hoặc stage 3 để cập nhật working tree. Sau đó cần `git add` để đánh dấu đường dẫn đã được giải quyết trong index.

Trước khi chọn, hãy xác nhận ý nghĩa của từng phía. Với rebase, cách hiểu ours/theirs đảo chiều so với cách người mới thường suy nghĩ: hãy kiểm tra nhánh đích và commit đang được phát lại, không chọn theo tên một cách máy móc.

### 4.3. Kết hợp thủ công bằng ứng dụng chuyên dụng

Không phải lúc nào một phiên bản cũng chứa toàn bộ thay đổi cần giữ. Ví dụ:

- Nhánh A chỉnh bố cục và màu sắc của ảnh banner.
- Nhánh B cập nhật logo và nội dung chữ trên cùng ảnh.
- Kết quả mong muốn là bố cục của A cùng logo và nội dung mới của B.

Trong trường hợp này, người phụ trách tài sản có thể mở từng phiên bản bằng ứng dụng phù hợp, kết hợp thành một tệp cuối cùng rồi lưu vào đúng đường dẫn trong working tree. Với tài liệu hoặc định dạng có công cụ so sánh chuyên dụng, hãy dùng công cụ đó để kiểm tra nội dung, lớp, trang hoặc thành phần có liên quan.

Sau khi lưu phiên bản đã kết hợp:

~~~bash
git add -- assets/banner.png
git status
~~~

Nếu dự án cấu hình một merge tool hoặc merge driver chuyên dụng cho định dạng tệp, có thể sử dụng công cụ đó. Cấu hình phải phù hợp với định dạng và được thống nhất trong nhóm; Git không tự có khả năng hiểu cấu trúc của mọi định dạng nhị phân.

### 4.4. Khai báo tệp nhị phân trong .gitattributes

Git thường tự nhận diện nhiều định dạng nhị phân, nhưng nhóm nên khai báo rõ những loại tệp không nên xử lý như văn bản. Ví dụ trong tệp `.gitattributes`:

~~~gitattributes
*.png binary
*.jpg binary
*.psd binary
*.pdf binary
*.zip binary
~~~

Thuộc tính `binary` yêu cầu Git không xử lý nội dung theo cơ chế text thông thường. Điều này giúp tránh hiển thị diff văn bản không có ý nghĩa và tránh áp dụng phép ghép dòng cho các định dạng nhị phân.

Nếu dự án dùng Git LFS, cần tuân theo quy trình LFS của repository để đảm bảo đối tượng nhị phân tương ứng được tải lên và có thể truy xuất. Tệp pointer LFS trong Git không có nghĩa là dữ liệu nhị phân thực tế đã được lưu đầy đủ trong mọi bản sao.

### 4.5. Quy tắc chọn phiên bản nhị phân

Trước khi chấp nhận một phiên bản, nên xác nhận:

- Phiên bản nào đáp ứng yêu cầu nghiệp vụ hoặc thiết kế mới nhất?
- Có cần giữ một phần nội dung từ phiên bản còn lại không?
- Tệp cuối cùng có đúng định dạng, kích thước, độ phân giải hoặc cấu trúc mà ứng dụng yêu cầu không?
- Những tệp khác có tham chiếu đến tên hoặc phiên bản tài sản này không?
- Nếu tệp nằm trong Git LFS, đối tượng LFS đã được lưu trữ và có thể tải về chưa?

Không nên chọn phiên bản chỉ vì nó thuộc nhánh chính hoặc nhánh đang đứng. Quyết định phải dựa trên nội dung thực tế và yêu cầu của thay đổi.

## 5. Quy trình hoàn tất sau khi giải quyết

Dù là xung đột đổi tên, mode/type hay nhị phân, bước kết thúc đều cần kiểm tra index và working tree. Một tệp trông đúng khi mở trong trình soạn thảo chưa đủ để chứng minh Git đã ghi nhận quyết định đó.

### 5.1. Stage đúng các đường dẫn đã xử lý

Với tệp đã sửa hoặc chọn một phía:

~~~bash
git add -- path/to/file
~~~

Với tệp cần xóa khỏi repository:

~~~bash
git rm -- path/to/obsolete-file
~~~

Với trường hợp đổi tên hoặc nhiều đường dẫn liên quan, stage cả đường dẫn cũ và mới trong phạm vi đã kiểm tra:

~~~bash
git add -A -- old/path new/path
~~~

Chỉ stage những đường dẫn đã xác minh. Tránh dùng `git add .` một cách máy móc vì working tree có thể chứa thay đổi khác không thuộc lần tích hợp này.

### 5.2. Xác nhận không còn mục chưa hợp nhất

Chạy:

~~~bash
git status
git diff --name-only --diff-filter=U
git ls-files -u
git diff --cached --check
git diff --cached --summary
~~~

Các điều cần xác nhận:

- `git status` không còn báo đường dẫn unmerged.
- `git diff --name-only --diff-filter=U` không liệt kê tệp chưa giải quyết.
- `git ls-files -u` không còn mục stage 1, 2 hoặc 3.
- `git diff --cached --check` không phát hiện lỗi khoảng trắng phổ biến trong phần thay đổi đã stage.
- `git diff --cached --summary` giúp kiểm tra tóm tắt đổi tên, tạo/xóa tệp hoặc thay đổi mode.

Sau đó xem lại nội dung và cấu trúc cuối cùng. Với tệp nhị phân, mở bằng ứng dụng phù hợp. Với symbolic link, kiểm tra đích liên kết. Với submodule, xác nhận commit được repository cha ghi nhận là commit mong muốn.

### 5.3. Tiếp tục hoặc hủy thao tác tích hợp

Nếu đang merge và mọi xung đột đã được giải quyết:

~~~bash
git merge --continue
~~~

Nếu đang rebase:

~~~bash
git rebase --continue
~~~

Nếu cần dừng thao tác và quay về trạng thái trước khi bắt đầu:

~~~bash
git merge --abort
~~~

Hoặc:

~~~bash
git rebase --abort
~~~

Abort phù hợp khi quyết định tích hợp chưa thể tiếp tục hoặc cần trao đổi lại với nhóm. Hãy lưu riêng các chỉnh sửa phát sinh trong lúc giải quyết nếu muốn giữ chúng, vì thao tác abort đưa repository trở lại trạng thái trước merge hoặc rebase và có thể loại bỏ phần chỉnh sửa đang dở.

Sau khi hoàn tất, kiểm tra lại lịch sử và trạng thái:

~~~bash
git status
git log --oneline --graph --decorate -8
~~~

Nếu đang merge, lịch sử có thể có merge commit tùy kiểu tích hợp. Nếu đang rebase, các commit được phát lại trên nền lịch sử mới. Trong cả hai trường hợp, cần đảm bảo working tree ở trạng thái mong muốn và thay đổi đã được ghi nhận.

## 6. Ví dụ tổng hợp

Một nhóm đang phát triển ứng dụng thương mại điện tử. Trong cùng thời gian:

- Nhánh `feature/new-branding` đổi tên `assets/logo-old.png` thành `assets/logo.png` và cập nhật thiết kế.
- Nhánh `main` thay ảnh logo ở đường dẫn cũ bằng một phiên bản mới do bộ phận thương hiệu cung cấp.
- Nhánh `feature/deploy` thay `scripts/deploy.sh` và đánh dấu tệp này có quyền thực thi.

Khi tích hợp, người phát triển kiểm tra:

~~~bash
git status
git diff --name-only --diff-filter=U
git ls-files -u
~~~

Với logo, nhóm mở hai phiên bản trong công cụ xem ảnh, xác định phiên bản chuẩn và lưu ở đường dẫn `assets/logo.png`. Sau đó xóa đường dẫn cũ nếu không còn dùng và stage các đường dẫn liên quan:

~~~bash
git add -A -- assets/logo-old.png assets/logo.png
~~~

Với script triển khai, nhóm xem mode đang có trong index và xác nhận tệp phải chạy trực tiếp. Nếu cần đặt quyền thực thi:

~~~bash
git add -- scripts/deploy.sh
git update-index --chmod=+x -- scripts/deploy.sh
~~~

Tiếp theo, nhóm kiểm tra:

~~~bash
git ls-files --stage -- assets/logo.png scripts/deploy.sh
git diff --cached --summary
git status
git ls-files -u
~~~

Khi không còn mục chưa hợp nhất và các phiên bản cuối cùng đã được xác nhận, người phát triển chạy `git merge --continue` hoặc `git rebase --continue` tùy thao tác ban đầu. Pull Request sau đó được review để xác nhận logo đúng thiết kế và script triển khai vẫn hoạt động trên môi trường mục tiêu.

Tình huống này cho thấy một lần tích hợp có thể bao gồm nhiều loại quyết định khác nhau. Đổi tên cần thống nhất đường dẫn và giữ nội dung; tệp nhị phân cần chọn hoặc tạo một phiên bản hoàn chỉnh; thay đổi mode cần xác nhận thuộc tính mà Git sẽ ghi vào index.

## 7. Những sai lầm thường gặp

- **Chỉ tìm dấu `<<<<<<<`:** xung đột rename, mode hoặc binary có thể không tạo dấu phân cách trong nội dung tệp. Hãy kiểm tra `git status` và `git ls-files -u`.
- **Xóa một đường dẫn trước khi kiểm tra nội dung:** có thể làm mất phần sửa ở nhánh còn lại. Hãy so sánh các phiên bản trước khi quyết định.
- **Nhầm tên ours và theirs khi rebase:** cách hiểu hai phía khác với merge thông thường. Hãy xác định thao tác đang chạy và kiểm tra nội dung từng phía.
- **Dùng trình soạn thảo văn bản cho tệp nhị phân:** có thể làm hỏng dữ liệu. Hãy dùng ứng dụng hiểu định dạng hoặc chọn một phiên bản đã được kiểm tra.
- **Stage toàn bộ repository khi chưa xem lại:** có thể đưa thay đổi không liên quan vào merge commit. Hãy stage theo đường dẫn đã giải quyết.
- **Cho rằng Git lưu toàn bộ quyền hệ điều hành:** Git chỉ lưu một số mode nhất định. Hãy kiểm tra mode bằng `git ls-files --stage`.
- **Coi remote là nơi tự giải quyết xung đột:** remote chỉ trao đổi commit và tham chiếu. Người phát triển hoặc công cụ merge phù hợp vẫn phải quyết định nội dung cuối cùng.

## 8. Tổng kết

Ba nhóm xung đột có đặc điểm và cách xử lý khác nhau:

| Nhóm xung đột | Điều cần quyết định | Công cụ kiểm tra hoặc xử lý |
| --- | --- | --- |
| Đổi tên | Đường dẫn cuối cùng và nội dung cần giữ | `git status`, `git ls-files -u`, `git add -A`, `git log --follow` |
| Đổi kiểu hoặc thuộc tính tệp | Tệp thường, quyền thực thi, symbolic link hoặc commit submodule | `git ls-files --stage`, `git update-index --chmod`, `git add` |
| Tệp nhị phân | Chọn một phía hoặc tạo phiên bản kết hợp bằng công cụ chuyên dụng | `git restore --ours/--theirs`, ứng dụng phù hợp, `git add` |

Nguyên tắc quan trọng là kiểm tra trạng thái và dữ liệu trước khi quyết định. Sau khi chọn đường dẫn, kiểu tệp và nội dung cuối cùng, hãy stage đúng phạm vi, xác nhận index không còn mục chưa hợp nhất rồi mới tiếp tục merge hoặc rebase. Làm theo trình tự này giúp xử lý được cả những xung đột không thể giải quyết bằng cách sửa dấu phân cách văn bản, đồng thời giữ lịch sử Git rõ ràng để nhóm có thể xem xét về sau.

