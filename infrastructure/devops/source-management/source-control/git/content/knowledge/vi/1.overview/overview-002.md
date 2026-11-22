# Vấn đề Git giải quyết: lưu vết, cộng tác và khôi phục thay đổi

Khi một dự án phần mềm phát triển, mã nguồn thay đổi mỗi ngày. Một người có thể sửa nhiều tệp cùng lúc; nhiều người có thể làm việc trên cùng một tính năng; một bản sửa có thể vô tình làm hỏng chức năng đang chạy tốt. Nếu chỉ lưu tệp trên máy tính hoặc sao chép thư mục theo từng phiên bản, nhóm rất nhanh gặp các câu hỏi khó trả lời: thay đổi nào đã được thực hiện, vì sao có thay đổi đó, ai đang làm phần nào, làm sao kết hợp công việc và có thể quay lại trạng thái tốt trước đó hay không?

Git giải quyết những vấn đề này bằng cách quản lý lịch sử thay đổi của dự án. Git giúp ghi lại các trạng thái đã được xác nhận, tổ chức công việc độc lập trên các nhánh, trao đổi lịch sử giữa các bản sao của kho mã và khôi phục những thay đổi không mong muốn. Đây là nền tảng của quy trình làm việc trong module `SOURCE_CONTROL_GIT`, từ working tree, staging area và commit đến branch, merge, remote, tag và các thao tác phục hồi.

## 1. Những khó khăn khi quản lý mã nguồn thủ công

Hãy hình dung một nhóm có ba người cùng phát triển một ứng dụng. Nếu không có hệ thống quản lý phiên bản, nhóm thường phải tự xử lý các vấn đề sau:

- **Không biết chính xác điều gì đã thay đổi:** một tệp bị sửa nhiều lần nhưng không có bản ghi rõ ràng về nội dung trước và sau.
- **Khó tìm nguyên nhân của lỗi:** khi chức năng đang chạy tốt bỗng bị hỏng, nhóm phải so sánh thủ công các bản sao hoặc hỏi từng người xem họ đã sửa gì.
- **Dễ ghi đè công việc của nhau:** hai người cùng sửa một tệp rồi gửi lại toàn bộ tệp có thể khiến phần sửa của người đến sau xóa mất phần sửa của người trước.
- **Khó thử nghiệm ý tưởng:** lập trình viên muốn thử một cách triển khai mới nhưng ngại làm ảnh hưởng đến phiên bản đang ổn định.
- **Khôi phục tốn thời gian:** nếu một lần sửa gây lỗi, nhóm phải tự tìm bản sao cũ hoặc sửa ngược bằng tay.
- **Thiếu bối cảnh:** nhìn thấy một dòng mã đã thay đổi nhưng không biết thay đổi đó nhằm giải quyết yêu cầu nào, có liên quan đến lỗi hay tính năng nào.

Việc đặt tên thư mục như `project-final`, `project-final-new` hoặc `project-final-fixed` chỉ tạo ra các bản sao rời rạc. Cách làm này không cung cấp một lịch sử có cấu trúc, không thể hiện quan hệ giữa các thay đổi và cũng không có cơ chế hợp nhất công việc đáng tin cậy.

Git đưa lịch sử thay đổi vào ngay trong quy trình làm việc của dự án.

## 2. Git giải quyết vấn đề lưu vết thay đổi

### 2.1. Commit ghi lại một trạng thái có ý nghĩa

Trong Git, một **commit** là một mốc lịch sử ghi nhận trạng thái của dự án tại một thời điểm. Người tạo commit thường kèm theo thông điệp mô tả mục đích, chẳng hạn:

- `Add password reset endpoint`
- `Fix rounding error in invoice total`
- `Update deployment instructions`

Commit giúp trả lời ba câu hỏi cơ bản:

1. Dự án đã được ghi nhận ở trạng thái nào?
2. Thay đổi được ghi nhận trong commit nào và nằm ở đâu trong lịch sử?
3. Vì sao người thực hiện tạo ra thay đổi đó?

Về mặt khái niệm, Git lưu trạng thái của các tệp trong commit, thay vì chỉ lưu một danh sách thao tác chỉnh sửa. Các đối tượng bên trong Git được định danh bằng nội dung (content-addressed). Commit liên kết đến cây thư mục và commit cha, tạo thành một đồ thị lịch sử. Git có thể tối ưu dung lượng lưu trữ nội bộ, nhưng khi sử dụng, ta nên hiểu mỗi commit như một ảnh chụp trạng thái dự án tại thời điểm đó.

Một commit thường chứa thông tin về:

- Cây thư mục đại diện cho trạng thái dự án.
- Commit cha, thể hiện commit này nối tiếp lịch sử nào.
- Tác giả và người ghi commit, cùng thời điểm tương ứng.
- Thông điệp mô tả mục đích thay đổi.

Vì vậy, lịch sử Git không chỉ là danh sách các phiên bản được đặt tên tùy ý. Nó là một chuỗi hoặc đồ thị các mốc có quan hệ với nhau.

### 2.2. Working tree, staging area và repository tạo thành quy trình ghi nhận

Git chia quá trình chuẩn bị một commit thành các khu vực có vai trò khác nhau:

| Khu vực | Vai trò | Ví dụ |
| --- | --- | --- |
| Working tree | Các tệp mà bạn đang xem và chỉnh sửa trong thư mục dự án | Sửa `src/Invoice.java` |
| Staging area (index) | Tập hợp nội dung đã chọn để đưa vào commit kế tiếp | Chỉ đưa phần sửa tính tiền vào staging |
| Local repository | Nơi lưu các commit và lịch sử trên máy hiện tại | Commit đã tạo và các nhánh local |

Quy trình cơ bản:

~~~bash
git status
git diff
git add src/Invoice.java
git diff --staged
git commit -m "Fix invoice total rounding"
~~~

Các lệnh trên thể hiện từng bước:

- `git status` cho biết tệp nào đã sửa, tệp nào đang được staging và tệp nào chưa được Git theo dõi.
- `git diff` xem phần thay đổi trong working tree chưa được staging.
- `git add` đưa nội dung hiện tại của tệp vào staging area.
- `git diff --staged` kiểm tra chính xác nội dung đã chọn để commit.
- `git commit` tạo một mốc lịch sử từ nội dung trong staging area.

Staging area đặc biệt hữu ích khi một lần làm việc có nhiều thay đổi nhưng không phải tất cả đều thuộc cùng một mục đích. Ví dụ, bạn vừa sửa lỗi tính tiền vừa định dạng lại một tệp khác. Bạn có thể chọn phần sửa lỗi để commit riêng, giúp mỗi commit có một ý nghĩa rõ ràng và dễ xem xét.

Lưu ý: `git add` ghi nhận nội dung tại thời điểm chạy lệnh. Nếu tiếp tục sửa tệp sau đó, phần sửa mới sẽ nằm trong working tree và chưa tự động được thêm vào staging area. Vì thế, trước khi commit, hãy kiểm tra lại bằng `git diff` và `git diff --staged`.

### 2.3. Lịch sử giúp truy tìm thay đổi

Sau khi có các commit, Git cung cấp công cụ để xem lại lịch sử và so sánh các trạng thái:

~~~bash
git log --oneline
git log --oneline --graph --decorate --all
git show <commit>
git diff <commit-cu> <commit-moi>
~~~

- `git log` liệt kê các commit theo lịch sử.
- `git log --graph --all` giúp quan sát các nhánh và quan hệ giữa những dòng lịch sử.
- `git show` hiển thị thông tin và thay đổi được ghi nhận trong một commit.
- `git diff` so sánh nội dung giữa hai trạng thái.

Ví dụ, khi người dùng báo tổng hóa đơn bị làm tròn sai, nhóm có thể tìm commit gần thời điểm lỗi xuất hiện, xem các dòng liên quan và đọc thông điệp commit để hiểu mục đích sửa đổi. Nếu commit được chia nhỏ hợp lý, việc truy tìm nguyên nhân sẽ dễ hơn nhiều so với việc so sánh hàng loạt bản sao thư mục.

Lịch sử chỉ có giá trị khi commit được tạo có chủ đích. Một commit chứa quá nhiều thay đổi không liên quan, hoặc có thông điệp chung chung như `update`, sẽ làm giảm khả năng truy vết.

## 3. Git giải quyết vấn đề cộng tác

### 3.1. Nhánh cho phép phát triển các công việc độc lập

Nếu mọi người cùng sửa trực tiếp trên một dòng lịch sử, thay đổi đang làm dở có thể ảnh hưởng đến công việc của người khác. Git dùng **branch** (nhánh) để mỗi công việc có thể phát triển trên một dòng lịch sử riêng.

Một nhánh Git về cơ bản là một tham chiếu nhẹ đến một commit. Tạo nhánh không có nghĩa là sao chép toàn bộ dự án thành một kho độc lập. Nó tạo một tên tham chiếu để nhóm commit của công việc đó lại với nhau.

Ví dụ, một lập trình viên tạo nhánh để phát triển chức năng đặt lại mật khẩu:

~~~bash
git switch -c feature/password-reset
~~~

Sau khi sửa mã nguồn và tạo commit, lập trình viên có thể tiếp tục làm việc trên nhánh này mà chưa phải đưa thay đổi vào nhánh chính. Một người khác có thể làm việc trên nhánh sửa lỗi thanh toán. Hai công việc được phát triển độc lập và có thể được xem xét trước khi tích hợp.

Tên nhánh nên thể hiện mục đích, ví dụ `feature/password-reset`, `bugfix/invoice-rounding` hoặc `docs/setup-guide`. Quy ước đặt tên cụ thể tùy thuộc vào nhóm.

### 3.2. Merge kết hợp lịch sử của các nhánh

Khi một công việc hoàn thành, nhóm có thể tích hợp nhánh đó vào nhánh đích bằng merge:

~~~bash
git switch main
git merge feature/password-reset
~~~

Git tìm điểm chung trong lịch sử và kết hợp các thay đổi. Nếu các nhánh sửa những phần không xung đột, Git thường có thể tự động hoàn tất việc merge. Nếu cùng một vùng nội dung được sửa theo những cách không thể tự quyết định, Git đánh dấu xung đột để người phát triển xem xét.

Merge giúp bảo toàn quan hệ giữa các dòng lịch sử. Trong một số tình huống, Git có thể thực hiện fast-forward: nhánh đích chỉ cần di chuyển tham chiếu đến commit mới hơn vì không có commit phân nhánh cần kết hợp. Trong tình huống khác, Git tạo merge commit để ghi nhận việc tích hợp hai dòng lịch sử.

### 3.3. Xung đột là điểm cần con người quyết định

Xung đột merge không nhất thiết có nghĩa là mã nguồn sai. Nó có nghĩa Git không thể tự xác định nội dung cuối cùng nên là gì.

Ví dụ, hai người cùng sửa một dòng:

- Người A đổi mức phí mặc định từ 5% thành 6%.
- Người B đổi mức phí mặc định từ 5% thành 7%.

Git không biết quyết định nghiệp vụ nào đúng. Người xử lý xung đột cần trao đổi với người phụ trách, kiểm tra yêu cầu và chọn hoặc kết hợp nội dung phù hợp.

Quy trình xử lý thường gồm:

1. Chạy merge hoặc thao tác tích hợp và đọc danh sách tệp bị xung đột bằng `git status`.
2. Mở từng tệp, xem các dấu phân cách xung đột do Git chèn vào.
3. Chỉnh nội dung thành phiên bản đúng theo yêu cầu.
4. Đánh dấu tệp đã xử lý bằng `git add <file>`.
5. Hoàn tất merge theo hướng dẫn Git đang hiển thị, thường bằng `git commit` nếu Git yêu cầu tạo merge commit.

Không nên chỉ xóa các dấu phân cách để làm cho Git hết báo lỗi. Điều quan trọng là nội dung sau khi giải quyết phải đúng về mặt chức năng và nghiệp vụ.

### 3.4. Remote giúp các bản sao trao đổi lịch sử

Git là hệ thống quản lý phiên bản phân tán. Mỗi bản clone thông thường có repository riêng và chứa phần lớn lịch sử cần thiết để làm việc độc lập. Nhờ đó, lập trình viên có thể xem log, tạo commit và phát triển nhánh ngay cả khi tạm thời không kết nối máy chủ. Các bản clone nông hoặc clone một phần có thể chỉ tải một phần lịch sử hay đối tượng theo cấu hình.

Một **remote** là tên dùng để tham chiếu đến một repository khác, thường nằm trên máy chủ hoặc dịch vụ lưu trữ mã nguồn. Remote không phải là một thư mục làm việc dùng chung; nó là đầu mối để trao đổi commit và tham chiếu giữa các repository.

Các lệnh thường dùng:

~~~bash
git clone <url>
git remote -v
git fetch origin
git pull
git push origin feature/password-reset
~~~

- `git clone` tạo bản sao repository để bắt đầu làm việc.
- `git remote -v` xem các địa chỉ remote đã cấu hình.
- `git fetch` tải thông tin và lịch sử mới từ remote về repository local nhưng không tự tích hợp vào nhánh đang làm việc.
- `git pull` thực hiện fetch rồi tích hợp thay đổi vào nhánh hiện tại, thường thông qua merge hoặc rebase tùy cấu hình và tùy cách gọi.
- `git push` gửi các commit local lên remote để người khác có thể lấy về.

Một quy trình cộng tác phổ biến là mỗi người phát triển trên nhánh riêng, push nhánh lên remote rồi tạo Pull Request hoặc Merge Request để nhóm xem xét. Pull Request và Merge Request là tính năng của các nền tảng lưu trữ mã nguồn; chúng sử dụng Git để trao đổi lịch sử nhưng không phải bản thân các lệnh Git cốt lõi.

Nhờ cơ chế này, nhóm có thể làm việc song song, xem xét thay đổi trước khi tích hợp và giữ lịch sử chung có thể truy xuất.

## 4. Git giải quyết vấn đề khôi phục thay đổi

Không phải mọi thay đổi đều đúng ngay từ đầu. Một lệnh chạy nhầm, một lần sửa vội hoặc một commit sai có thể khiến dự án rơi vào trạng thái không mong muốn. Git cung cấp nhiều cách khôi phục tùy thuộc thay đổi đang nằm ở đâu và đã được chia sẻ hay chưa.

### 4.1. Khôi phục thay đổi chưa staging

Nếu một tệp đang có thay đổi trong working tree và bạn muốn bỏ những thay đổi đó để trở lại nội dung trong commit hiện tại, có thể dùng:

~~~bash
git restore src/Invoice.java
~~~

Lệnh này mặc định khôi phục tệp trong working tree từ staging area (index). Nếu tệp chưa có thay đổi được staging, nội dung trong index thường trùng với `HEAD`. Những thay đổi chưa được lưu ở nơi khác có thể bị mất, vì vậy hãy xem `git diff` trước khi chạy.

### 4.2. Bỏ staging nhưng giữ nội dung đã sửa

Nếu đã chạy `git add` nhưng quyết định chưa đưa tệp vào commit kế tiếp, có thể bỏ staging:

~~~bash
git restore --staged src/Invoice.java
~~~

Lệnh này gỡ tệp khỏi staging area, còn nội dung sửa trong working tree vẫn được giữ lại. Bạn có thể tiếp tục chỉnh sửa hoặc chọn lại phần cần commit.

### 4.3. Đảo ngược một commit đã chia sẻ bằng revert

Nếu một commit đã được push và người khác có thể đã dựa trên nó, cách an toàn thường là tạo một commit mới để đảo ngược thay đổi:

~~~bash
git revert <commit>
~~~

Revert không xóa commit cũ khỏi lịch sử. Nó tạo một commit mới có tác dụng ngược lại với commit được chỉ định. Nhờ vậy, lịch sử vẫn cho biết thay đổi ban đầu đã từng xảy ra và sau đó được đảo ngược.

Đây thường là lựa chọn phù hợp khi cần sửa lịch sử chung trên nhánh mà nhiều người đang sử dụng.

### 4.4. Di chuyển nhánh bằng reset

`git reset` di chuyển tham chiếu của nhánh hiện tại về một commit khác và tùy tùy chọn mà cập nhật staging area hoặc working tree:

~~~bash
git reset --soft <commit>
git reset --mixed <commit>
git reset --hard <commit>
~~~

- `--soft`: di chuyển nhánh, giữ nguyên staging area và working tree.
- `--mixed`: di chuyển nhánh và cập nhật staging area; giữ nội dung working tree. Đây là chế độ mặc định nếu không chỉ định tùy chọn.
- `--hard`: di chuyển nhánh, cập nhật staging area và working tree theo commit đích. Những thay đổi chưa commit trên các tệp đã được Git theo dõi có thể bị ghi đè và mất; các tệp chưa được theo dõi thường vẫn còn.

Reset hữu ích khi chỉnh lại lịch sử local, chẳng hạn gộp hoặc bỏ các commit chưa push. Tuy nhiên, viết lại lịch sử đã chia sẻ có thể khiến nhánh của người khác lệch với remote và gây khó khăn khi đồng bộ. Vì vậy, hãy cân nhắc phạm vi ảnh hưởng trước khi reset một commit đã push; với thay đổi đã chia sẻ, `git revert` thường dễ phối hợp hơn.

### 4.5. Tìm lại commit bằng reflog

Có trường hợp một commit không còn xuất hiện trong log của nhánh hiện tại vì nhánh đã được reset hoặc di chuyển. Nếu commit đó vẫn còn trong dữ liệu local và chưa bị Git dọn dẹp, reflog có thể giúp tìm lại dấu vết di chuyển của các tham chiếu:

~~~bash
git reflog
~~~

Sau khi xác định được mã commit cần phục hồi, có thể tạo một nhánh mới trỏ đến commit đó:

~~~bash
git branch rescue-work <commit>
~~~

Reflog là nhật ký cục bộ về những lần tham chiếu được cập nhật. Nó rất hữu ích để cứu các commit vừa bị tách khỏi nhánh, nhưng không phải bản sao lưu vĩnh viễn: các mục reflog có thể hết hạn và đối tượng không còn được tham chiếu có thể bị dọn dẹp. Vì vậy, khi phát hiện mất commit, nên kiểm tra reflog sớm.

### 4.6. Tạm cất công việc bằng stash

Đôi khi bạn đang sửa một tính năng nhưng cần chuyển sang nhánh khác để xử lý lỗi khẩn cấp. Nếu chưa muốn tạo commit, có thể tạm cất thay đổi:

~~~bash
git stash push -m "WIP password reset"
git stash list
git stash pop
~~~

Stash lưu tạm các thay đổi để working tree có thể trở về trạng thái sạch hơn. Sau đó có thể áp dụng lại chúng bằng `git stash pop` hoặc `git stash apply`. Tệp chưa được Git theo dõi thường không được đưa vào stash mặc định; nếu cần lưu cả những tệp đó, hãy tìm hiểu tùy chọn `-u`.

Stash phù hợp cho việc chuyển ngữ cảnh ngắn hạn. Với một công việc kéo dài hoặc cần chia sẻ, tạo commit trên nhánh riêng thường giúp lịch sử rõ ràng hơn.

## 5. Một tình huống tổng hợp

Giả sử nhóm đang phát triển ứng dụng thanh toán. Một người nhận nhiệm vụ sửa lỗi làm tròn tổng hóa đơn. Có thể áp dụng Git theo trình tự sau:

**Bước 1 — Đồng bộ và tạo nhánh công việc**

~~~bash
git switch main
git pull
git switch -c bugfix/invoice-rounding
~~~

Người phát triển bắt đầu từ trạng thái mới nhất của nhánh chính và làm việc trong nhánh riêng.

**Bước 2 — Kiểm tra và chọn thay đổi**

Sau khi sửa mã nguồn:

~~~bash
git status
git diff
git add src/Invoice.java
git diff --staged
~~~

Người phát triển xem lại thay đổi và chỉ staging nội dung liên quan đến lỗi làm tròn.

**Bước 3 — Ghi lại mốc thay đổi**

~~~bash
git commit -m "Fix invoice total rounding"
~~~

Commit tạo một mốc có thể xem lại và so sánh về sau.

**Bước 4 — Chia sẻ để nhóm xem xét**

~~~bash
git push -u origin bugfix/invoice-rounding
~~~

Nhánh được gửi lên remote. Nhóm có thể mở Pull Request, trao đổi, yêu cầu chỉnh sửa và xem xét trước khi tích hợp.

**Bước 5 — Tích hợp và xử lý xung đột nếu có**

Khi thay đổi được chấp nhận, nhánh công việc được merge vào nhánh đích theo quy trình của nhóm. Nếu Git báo xung đột, người phát triển giải quyết nội dung, kiểm tra lại và hoàn tất thao tác tích hợp.

**Bước 6 — Khôi phục nếu phát hiện lỗi sau khi tích hợp**

Nếu thay đổi đã được chia sẻ và gây lỗi, nhóm có thể tạo commit đảo ngược bằng `git revert`, sau đó tiếp tục điều tra và sửa đúng nguyên nhân. Lịch sử vẫn giữ cả commit ban đầu lẫn commit đảo ngược, giúp mọi người hiểu diễn biến.

Tình huống này cho thấy ba lợi ích liên kết với nhau: commit tạo dấu vết, branch và remote hỗ trợ cộng tác, còn các lệnh phục hồi giúp xử lý sai sót có kiểm soát.

## 6. Git không tự quyết định chất lượng của thay đổi

Git quản lý lịch sử và hỗ trợ phối hợp, nhưng không tự biết một thay đổi có đúng yêu cầu nghiệp vụ hay không. Git cũng không thay thế kiểm thử, review mã nguồn, quy trình phát hành hoặc sao lưu dữ liệu vận hành.

Một số giới hạn cần hiểu rõ:

- **Commit tốt không đồng nghĩa mã nguồn tốt:** thông điệp rõ ràng và lịch sử sạch không đảm bảo chức năng không có lỗi.
- **Merge thành công không đồng nghĩa logic đúng:** Git có thể kết hợp văn bản mà không phát hiện hai thay đổi mâu thuẫn về nghiệp vụ.
- **Remote không phải bản sao lưu duy nhất:** lỗi quyền truy cập, xóa repository hoặc sự cố máy chủ vẫn có thể xảy ra. Dự án quan trọng cần chính sách sao lưu phù hợp.
- **Git chủ yếu quản lý nội dung tệp:** dữ liệu lớn, tệp nhị phân thường xuyên thay đổi hoặc tài sản đặc thù có thể cần giải pháp bổ sung như Git LFS.
- **Git không tự bảo vệ bí mật:** không nên commit mật khẩu, token, khóa riêng hoặc dữ liệu nhạy cảm. Nếu bí mật đã được commit và chia sẻ, cần xử lý cả việc thu hồi hoặc xoay vòng bí mật; xóa tệp ở commit mới không làm bí mật biến mất khỏi lịch sử cũ.
- **Git không tự loại trừ tệp đã được theo dõi:** thêm tên tệp vào `.gitignore` chủ yếu ảnh hưởng đến các tệp chưa được theo dõi. Tệp đã được Git theo dõi vẫn cần được xử lý riêng nếu muốn ngừng theo dõi.

Do đó, Git phát huy hiệu quả nhất khi được kết hợp với quy ước commit, chiến lược nhánh, review, kiểm thử và quy trình phát hành rõ ràng.

## 7. Tổng kết

Git giải quyết ba nhóm vấn đề quan trọng trong quá trình phát triển phần mềm:

| Vấn đề | Cơ chế Git hỗ trợ | Kết quả |
| --- | --- | --- |
| Không biết thay đổi nào đã xảy ra và vì sao | Staging area, commit, log, diff, show | Có lịch sử để kiểm tra, so sánh và truy tìm nguyên nhân |
| Nhiều người làm việc đồng thời | Branch, merge, remote, fetch, pull, push | Có thể phát triển độc lập, chia sẻ và tích hợp công việc |
| Sửa sai hoặc cần quay lại trạng thái trước | Restore, revert, reset, reflog, stash | Có cách xử lý thay đổi ở nhiều giai đoạn khác nhau |

Khi hiểu Git theo ba mục tiêu này, các lệnh không còn là những câu lệnh rời rạc cần học thuộc. Mỗi thao tác đều phục vụ một việc cụ thể: kiểm soát thay đổi đang làm, ghi nhận một trạng thái đáng tin cậy, chia sẻ lịch sử với người khác hoặc phục hồi khi cần. Đó là nền tảng để sử dụng Git an toàn và hiệu quả trong các dự án cá nhân lẫn nhóm phát triển.

