# Interactive rebase: reword, edit, squash, fixup và drop

Trong quá trình phát triển, một nhánh có thể tích lũy nhiều commit nhỏ: commit sửa lỗi đánh máy, commit bổ sung kiểm thử, commit sửa lại cùng một đoạn mã hoặc commit có thông điệp chưa rõ nghĩa. Trước khi gửi pull request, bạn có thể muốn sắp xếp các commit thành một chuỗi dễ đọc và dễ review hơn. Git cung cấp **interactive rebase** để xem và điều chỉnh danh sách commit sẽ được phát lại, chẳng hạn đổi thông điệp, dừng lại để sửa nội dung, gộp nhiều commit hoặc loại bỏ một commit.

Bài này thuộc chương **Rebase** của module **SOURCE_CONTROL_GIT**. Module hướng dẫn Git từ working tree, staging area, commit và lịch sử đến branch, merge, rebase, remote và tag; đồng thời rèn cách cộng tác qua nhánh, giải quyết xung đột, truy tìm thay đổi và khôi phục thao tác sai mà vẫn bảo toàn lịch sử quan trọng. Interactive rebase là công cụ hữu ích để làm rõ lịch sử của nhánh riêng trước khi tích hợp, miễn là bạn hiểu commit nào sẽ bị viết lại và ai đang dựa vào chúng.

## 1. Interactive rebase là gì?

Rebase thông thường phát lại các commit của nhánh hiện tại trên một commit nền khác. Với tùy chọn interactive, Git mở một danh sách các commit sẽ được xử lý và cho phép bạn chọn hành động cho từng commit. Danh sách này thường được gọi là **todo list**.

Bạn có thể:

- Giữ commit như hiện tại bằng <code>pick</code>.
- Đổi thông điệp commit bằng <code>reword</code>.
- Tạm dừng để chỉnh sửa nội dung commit bằng <code>edit</code>.
- Gộp commit vào commit đứng trước bằng <code>squash</code> hoặc <code>fixup</code>.
- Loại bỏ commit khỏi lịch sử mới bằng <code>drop</code>.
- Thay đổi thứ tự các commit trong danh sách nếu các thay đổi vẫn có thể áp dụng đúng theo thứ tự mới.

Interactive rebase không sửa trực tiếp các commit cũ. Git tạo một chuỗi commit mới bằng cách phát lại các thay đổi theo todo list. Vì danh tính commit phụ thuộc vào nội dung, commit cha và metadata, các commit được phát lại thường có hash mới, kể cả khi nội dung mã nguồn không đổi.

## 2. Chọn đúng phạm vi commit

Trước khi chạy interactive rebase, cần xác định commit nền và các commit sẽ được đưa vào todo list. Cú pháp phổ biến:

~~~bash
# Chỉnh sửa 4 commit gần nhất trên nhánh hiện tại
git rebase -i HEAD~4

# Chỉnh sửa các commit trên nhánh hiện tại chưa có trong origin/main
git fetch origin
git rebase -i origin/main
~~~

Với lệnh <code>git rebase -i HEAD~4</code>, <code>HEAD~4</code> là commit nền; todo list chứa bốn commit phía sau nó trên lịch sử tuyến tính hiện tại. Commit nền không xuất hiện trong danh sách. Nếu bạn chọn sai phạm vi, có thể vô tình chỉnh sửa commit không thuộc công việc đang làm.

Với <code>git rebase -i origin/main</code>, Git xác định các commit thuộc nhánh hiện tại mà chưa có trong upstream rồi phát lại chúng trên nền upstream. Hãy fetch trước để remote-tracking branch phản ánh dữ liệu mới nhất. Nếu nhánh có lịch sử phân nhánh phức tạp hoặc có merge commit, hãy kiểm tra đồ thị commit trước khi chọn cách rebase.

Các lệnh kiểm tra hữu ích:

~~~bash
# Xem nhánh hiện tại và trạng thái working tree
git status
git branch --show-current

# Xem lịch sử dưới dạng đồ thị
git log --oneline --graph --decorate -15

# Xem commit sẽ nằm trong phạm vi so với nhánh nền
git log --oneline origin/main..HEAD
~~~

Nếu muốn đưa toàn bộ lịch sử từ commit gốc vào interactive rebase, có thể dùng <code>git rebase -i --root</code>. Đây là phạm vi rất rộng và thường không cần thiết khi chỉ muốn làm gọn vài commit của một nhánh tính năng.

## 3. Chuẩn bị trước khi viết lại lịch sử

Interactive rebase nên được thực hiện khi working tree sạch và bạn đã hiểu các commit trong phạm vi. Trước khi bắt đầu:

1. Kiểm tra thay đổi chưa commit.
2. Xác định đúng nhánh và commit nền.
3. Đọc nội dung các commit có thể bị đổi, gộp hoặc loại bỏ.
4. Tạo một tham chiếu dự phòng nếu lịch sử có giá trị hoặc bạn chưa quen thao tác.
5. Xác nhận các commit trong phạm vi chưa được chia sẻ hoặc nhóm đã thống nhất cho phép viết lại.

Ví dụ:

~~~bash
git status
git log --oneline --graph --decorate -10

# Tạo nhánh dự phòng trỏ đến trạng thái trước khi rebase
git branch backup/feature-before-rebase
~~~

Nhánh dự phòng giữ lại vị trí commit ban đầu để bạn có thể đối chiếu hoặc khôi phục nếu cần. Hãy chọn tên chưa tồn tại và xóa nhánh dự phòng sau khi đã xác nhận kết quả, theo quy trình quản lý nhánh của dự án.

Nếu working tree đang có thay đổi chưa commit, hãy commit chúng hoặc lưu lại an toàn trước khi rebase. Rebase có thể từ chối bắt đầu khi các thay đổi sẽ bị ghi đè; không cố tiếp tục bằng cách xóa thay đổi mà chưa hiểu rõ nội dung.

**Quan trọng:** chỉ nên viết lại lịch sử riêng của bạn. Commit đã push lên nhánh nhiều người dùng, nhánh chính, nhánh release hoặc commit mà đồng đội đã tạo nhánh dựa trên đó được xem là lịch sử đã chia sẻ. Hãy phối hợp trước khi rebase các commit này. Trong trường hợp cần sửa thay đổi đã tích hợp vào lịch sử chung, thường nên tạo commit mới hoặc dùng <code>git revert</code>.

## 4. Mở todo list và hiểu cấu trúc

Giả sử nhánh hiện tại có sáu commit mới kể từ commit nền:

~~~text
a1b2c3d feat: add export endpoint
b2c3d4e docs: add export API docs
c3d4e5f feat: validate export filters
d4e5f6a test: add export validation tests
e5f6a7b fix: correct filter edge case
f6a7b8c chore: add temporary debug logging
~~~

Chạy:

~~~bash
git rebase -i HEAD~6
~~~

Git mở trình soạn thảo với todo list tương tự:

~~~text
pick a1b2c3d feat: add export endpoint
pick b2c3d4e docs: add export API docs
pick c3d4e5f feat: validate export filters
pick d4e5f6a test: add export validation tests
pick e5f6a7b fix: correct filter edge case
pick f6a7b8c chore: add temporary debug logging

# Rebase a1b2c3d..f6a7b8c onto ...
# Commands:
# p, pick <commit> = use commit
# r, reword <commit> = use commit, but edit the commit message
# e, edit <commit> = use commit, but stop for amending
# s, squash <commit> = use commit, but meld into previous commit
# f, fixup [-C | -c] <commit> = like squash, but discard this commit's log message
# d, drop <commit> = remove commit
~~~

Mỗi dòng bắt đầu bằng một lệnh, tiếp theo là commit hash và thông điệp. Các dòng chú thích bắt đầu bằng dấu <code>#</code> chỉ giải thích cú pháp, không phải lệnh được thực hiện.

Todo list thường được sắp xếp từ commit cũ đến commit mới. Git thực hiện từng dòng theo thứ tự từ trên xuống. Khi lưu và đóng trình soạn thảo, Git bắt đầu rebase theo các hành động bạn đã chọn.

## 5. Các lệnh quan trọng trong interactive rebase

### pick – giữ commit

~~~text
pick a1b2c3d feat: add export endpoint
~~~

<code>pick</code> yêu cầu Git phát lại commit với thay đổi và thông điệp tương ứng. Đây là hành động mặc định khi bạn chưa cần chỉnh sửa một commit cụ thể. Commit mới vẫn có thể có hash khác do được tạo lại trên nền mới hoặc có commit trước đó đã được viết lại.

### reword – đổi thông điệp commit

~~~text
reword b2c3d4e docs: add export API docs
~~~

<code>reword</code> giữ thay đổi mã nguồn của commit nhưng yêu cầu bạn nhập thông điệp mới. Sau khi lưu todo list, Git mở trình soạn thảo thông điệp cho commit đó. Ví dụ, có thể đổi thông điệp chung chung thành:

~~~text
docs: document export endpoint parameters
~~~

Chọn <code>reword</code> khi nội dung thay đổi đã đúng nhưng thông điệp chưa mô tả rõ mục đích. Vì thông điệp là một phần của commit metadata, commit được tạo lại và hash thay đổi.

### edit – dừng để sửa nội dung commit

~~~text
edit c3d4e5f feat: validate export filters
~~~

<code>edit</code> yêu cầu Git phát lại commit đó rồi tạm dừng để bạn có thể sửa nội dung. Khi rebase dừng, HEAD đang ở commit được chọn để chỉnh sửa. Bạn có thể cập nhật tệp, staging thay đổi và amend commit:

~~~bash
# Xem trạng thái khi rebase đang dừng
git status

# Sửa tệp bằng editor, sau đó stage phần muốn đưa vào commit
git add src/ExportFilter.java

# Thay commit đang dừng bằng phiên bản đã chỉnh sửa
git commit --amend

# Tiếp tục phát lại các commit còn lại
git rebase --continue
~~~

Nếu chỉ muốn sửa thông điệp mà không thay nội dung, có thể dùng <code>git commit --amend</code> rồi giữ hoặc nhập thông điệp phù hợp. Nếu muốn giữ nguyên thông điệp hiện tại, có thể dùng <code>git commit --amend --no-edit</code> sau khi staging thay đổi.

Trong lúc dừng tại <code>edit</code>, bạn cũng có thể tách một commit thành nhiều commit nhỏ hơn. Cần thao tác cẩn thận với HEAD, index và working tree; hãy đọc <code>git status</code> và xem diff trước khi tạo lại từng commit. Sau khi hoàn tất, chạy <code>git rebase --continue</code> để Git phát lại phần còn lại.

### squash – gộp commit và kết hợp thông điệp

~~~text
pick c3d4e5f feat: validate export filters
squash d4e5f6a test: add export validation tests
~~~

<code>squash</code> gộp thay đổi của commit hiện tại vào commit được chọn gần nhất ở phía trên trong todo list. Git kết hợp thông điệp của các commit và thường mở trình soạn thảo để bạn chỉnh sửa thông điệp cuối cùng.

Trong ví dụ, thay đổi kiểm thử được gộp vào commit thêm chức năng kiểm tra bộ lọc. Commit mới có thể mang thông điệp:

~~~text
feat: validate export filters

Add tests for accepted and rejected filter values.
~~~

Commit được gộp không còn xuất hiện như một commit riêng trong lịch sử mới, nhưng thay đổi của nó vẫn nằm trong snapshot kết quả nếu không bị chỉnh sửa hoặc xung đột.

<code>squash</code> cần có một commit trước đó để gộp vào. Không đặt một dòng <code>squash</code> ở đầu todo list khi chưa có commit nào được giữ trước nó.

### fixup – gộp commit và bỏ thông điệp của commit sau

~~~text
pick c3d4e5f feat: validate export filters
fixup e5f6a7b fix: correct filter edge case
~~~

<code>fixup</code> cũng gộp thay đổi của commit hiện tại vào commit trước đó, nhưng loại bỏ thông điệp của commit được gộp. Thông điệp của commit trước được giữ lại. Dùng <code>fixup</code> khi commit sau chỉ là chỉnh sửa bổ sung, sửa typo hoặc sửa một lỗi nhỏ thuộc cùng một thay đổi, và bạn không muốn giữ thông điệp riêng cho nó.

So sánh:

| Lệnh | Thay đổi mã nguồn | Thông điệp sau khi gộp |
|---|---|---|
| <code>squash</code> | Gộp vào commit trước | Kết hợp thông điệp, cho phép biên tập lại |
| <code>fixup</code> | Gộp vào commit trước | Bỏ thông điệp commit được gộp, giữ thông điệp commit trước |

### drop – loại bỏ commit khỏi lịch sử mới

~~~text
drop f6a7b8c chore: add temporary debug logging
~~~

<code>drop</code> loại commit đó khỏi chuỗi lịch sử được tạo lại. Bạn cũng có thể xóa hẳn dòng tương ứng khỏi todo list; Git hiểu rằng commit không được chọn sẽ bị bỏ qua.

Chỉ dùng <code>drop</code> khi đã xác nhận thay đổi trong commit không còn cần thiết. Nếu commit chứa một phần sửa lỗi hoặc thay đổi mà các commit sau đang phụ thuộc, loại bỏ nó có thể khiến commit phía sau không áp dụng được hoặc làm sản phẩm sai hành vi.

Trước khi drop, hãy xem nội dung:

~~~bash
git show --stat f6a7b8c
git show f6a7b8c
~~~

Nếu chỉ muốn loại một phần thay đổi, hãy cân nhắc dùng <code>edit</code> để sửa commit thay vì drop toàn bộ.

## 6. Ví dụ hoàn chỉnh: làm gọn sáu commit

Giả sử nhánh tính năng có sáu commit như ví dụ ở trên. Mục tiêu:

- Giữ commit thêm endpoint.
- Đổi thông điệp tài liệu cho rõ nghĩa.
- Dừng ở commit validation để bổ sung một điều kiện.
- Gộp commit test vào commit validation.
- Gộp commit sửa edge case vào cùng thay đổi validation nhưng không giữ thông điệp riêng.
- Bỏ commit debug tạm thời.

Trước tiên, kiểm tra và tạo nhánh dự phòng:

~~~bash
git status
git log --oneline --graph --decorate -10
git branch backup/feature-before-rebase
~~~

Mở todo list:

~~~bash
git rebase -i HEAD~6
~~~

Chỉnh các dòng thành:

~~~text
pick a1b2c3d feat: add export endpoint
reword b2c3d4e docs: add export API docs
edit c3d4e5f feat: validate export filters
squash d4e5f6a test: add export validation tests
fixup e5f6a7b fix: correct filter edge case
drop f6a7b8c chore: add temporary debug logging
~~~

Sau khi lưu và đóng todo list:

1. Git xử lý commit đầu tiên.
2. Git dừng tại commit có lệnh <code>reword</code> để bạn nhập thông điệp mới.
3. Git phát lại commit <code>edit</code> rồi dừng. Bạn sửa mã nguồn, chạy kiểm tra cần thiết, stage và amend commit.
4. Chạy <code>git rebase --continue</code>. Git gộp commit test bằng <code>squash</code> và yêu cầu biên tập thông điệp kết hợp.
5. Git gộp commit sửa edge case bằng <code>fixup</code>, không giữ thông điệp riêng của commit đó.
6. Git bỏ qua commit debug có lệnh <code>drop</code> và hoàn tất các bước còn lại.

Sau khi hoàn tất, kiểm tra lịch sử và nội dung:

~~~bash
git status
git log --oneline --graph --decorate -10
git diff backup/feature-before-rebase..HEAD
git show --stat HEAD
~~~

So sánh diff giữa nhánh dự phòng và nhánh mới để kiểm tra thay đổi tổng thể. Nếu mục tiêu của rebase là sắp xếp lịch sử nhưng không đổi sản phẩm, nội dung cuối cùng nên tương đương với trước khi rebase, ngoại trừ các thay đổi mà bạn chủ ý sửa hoặc loại bỏ. Với phạm vi phức tạp, hãy chạy test và review từng commit mới trước khi push.

## 7. Sắp xếp lại thứ tự commit

Todo list cho phép di chuyển các dòng lên hoặc xuống. Git sẽ phát lại commit theo thứ tự mới. Điều này hữu ích khi bạn muốn đặt commit nền tảng trước commit phụ thuộc hoặc nhóm các thay đổi liên quan gần nhau.

Ví dụ:

~~~text
pick aaaaaaa feat: add export model
pick bbbbbbb test: add export model tests
pick ccccccc docs: document export model
~~~

Bạn có thể sắp xếp lại thành:

~~~text
pick aaaaaaa feat: add export model
pick ccccccc docs: document export model
pick bbbbbbb test: add export model tests
~~~

Tuy nhiên, thứ tự mới có thể tạo xung đột hoặc khiến một commit không còn áp dụng được vì nó phụ thuộc vào thay đổi của commit đứng sau. Chỉ di chuyển khi hiểu quan hệ phụ thuộc giữa các thay đổi. Nếu todo list được sắp xếp lại và có xung đột, xử lý như quy trình conflict thông thường của rebase.

## 8. Xử lý xung đột trong interactive rebase

Rebase phát lại từng commit. Nếu thay đổi của commit không thể áp dụng tự động lên trạng thái hiện tại, Git tạm dừng và báo các đường dẫn xung đột.

Quy trình:

~~~bash
# Xem các tệp đang xung đột
git status

# Mở tệp, giải quyết nội dung mong muốn
# Sau đó đánh dấu từng tệp đã giải quyết
git add src/ExportFilter.java

# Tiếp tục rebase
git rebase --continue
~~~

Nếu có nhiều tệp xung đột, hãy giải quyết và staging từng tệp. Sau đó review nội dung đã staging trước khi tiếp tục:

~~~bash
git diff
git diff --staged
git status
git rebase --continue
~~~

Khi rebase dừng do conflict:

- <code>git rebase --continue</code> tiếp tục phát lại các commit còn lại sau khi bạn giải quyết xung đột.
- <code>git rebase --skip</code> bỏ qua commit đang được phát lại. Chỉ dùng khi chủ đích loại bỏ toàn bộ thay đổi của commit đó khỏi lịch sử mới.
- <code>git rebase --abort</code> hủy toàn bộ phiên rebase và đưa nhánh trở về trạng thái trước khi bắt đầu.

Đừng dùng <code>--skip</code> chỉ để thoát khỏi lỗi conflict. Commit đang dừng có thể chứa thay đổi quan trọng. Nếu chưa chắc, hãy xem commit đang được áp dụng và trao đổi với người phụ trách trước khi quyết định.

## 9. Sửa todo list khi rebase đang tạm dừng

Nếu đang ở giữa phiên interactive rebase và nhận ra cần đổi hành động của các commit chưa được xử lý, có thể mở lại danh sách:

~~~bash
git rebase --edit-todo
~~~

Chỉnh các dòng còn lại, lưu và tiếp tục bằng:

~~~bash
git rebase --continue
~~~

Lệnh này chỉ chỉnh phần todo chưa được thực hiện. Nó không tự đảo ngược các commit đã được phát lại trong phiên hiện tại. Nếu bạn đã chọn sai một hành động và cần làm lại toàn bộ quy trình, có thể abort rồi bắt đầu lại với phạm vi và todo list đúng, sau khi đã kiểm tra trạng thái.

## 10. Autosquash với fixup commit

Khi đang phát triển, bạn có thể tạo một commit nhỏ để sửa commit trước mà không cần mở interactive rebase ngay lập tức. Git hỗ trợ tạo commit có thông điệp nhận diện bằng <code>--fixup</code>:

~~~bash
# Tạo commit sửa bổ sung cho một commit đã có
git add src/ExportFilter.java
git commit --fixup=c3d4e5f
~~~

Commit mới có thông điệp dạng <code>fixup! ...</code>. Trước khi hoàn thiện nhánh, chạy:

~~~bash
git rebase -i --autosquash origin/main
~~~

Git tự di chuyển commit fixup đến gần commit mục tiêu và đánh dấu hành động <code>fixup</code> trong todo list. Bạn vẫn cần xem lại danh sách trước khi lưu để chắc chắn commit được ghép vào đúng mục tiêu.

Tương tự, <code>git commit --squash=&lt;commit&gt;</code> tạo commit có thông điệp nhận diện <code>squash! ...</code>; tùy chọn <code>--autosquash</code> sẽ sắp xếp nó để gộp theo kiểu squash. Autosquash chỉ hỗ trợ sắp xếp todo list, không tự chứng minh thay đổi có thể gộp an toàn.

## 11. Hoàn tất, kiểm tra và cập nhật remote

Khi Git báo rebase hoàn tất, đừng vội push. Hãy kiểm tra:

~~~bash
git status
git log --oneline --graph --decorate -15
git diff origin/main...HEAD
~~~

Sau đó:

- Chạy test và các kiểm tra cần thiết của dự án.
- Xem từng commit mới để xác nhận thông điệp và phạm vi thay đổi hợp lý.
- Xác nhận các thay đổi chủ ý bị drop thực sự không còn trong kết quả.
- Kiểm tra không có tệp tạm, debug log hoặc dữ liệu nhạy cảm bị đưa vào commit.

Nếu đây là nhánh riêng của bạn và chưa có ai dựa vào lịch sử đã push, cập nhật remote có thể cần force push có điều kiện:

~~~bash
git push --force-with-lease origin feature/export
~~~

Chỉ thực hiện sau khi đã xác nhận chính sách của nhóm cho phép viết lại nhánh đó. Nếu remote đã có commit mới mà bạn chưa fetch hoặc xử lý, <code>--force-with-lease</code> thường từ chối push; hãy dừng lại, fetch và xem lịch sử thay vì cố lặp lại bằng <code>--force</code>.

Nếu commit đã được chia sẻ hoặc nhánh có nhiều người cùng làm, không force push chỉ để đưa lịch sử về dạng đẹp hơn. Hãy giữ lịch sử đã chia sẻ và bổ sung commit sửa đổi, hoặc phối hợp với tất cả người liên quan nếu thực sự cần viết lại.

## 12. Khôi phục khi kết quả rebase không như mong muốn

### Hủy phiên rebase đang chạy

Nếu chưa hoàn tất rebase và muốn quay lại trạng thái trước khi bắt đầu:

~~~bash
git rebase --abort
~~~

Git hủy phiên rebase hiện tại và khôi phục nhánh về vị trí ban đầu. Đây là cách phù hợp khi nhận ra đã chọn sai phạm vi, todo list hoặc không muốn tiếp tục giải quyết các xung đột.

### Đã hoàn tất rebase nhưng muốn quay lại

Nếu rebase đã hoàn tất và bạn muốn tìm vị trí trước đó, kiểm tra reflog:

~~~bash
git reflog
~~~

Reflog ghi lại các lần cập nhật tham chiếu local, bao gồm thao tác rebase. Tìm entry trước khi rebase, xác nhận đúng commit rồi có thể tạo một nhánh khôi phục trỏ đến commit đó:

~~~bash
git branch recovery/before-rebase <commit-hash>
~~~

Sau khi xác nhận nhánh khôi phục có đúng nội dung, hãy quyết định cách đưa nhánh làm việc trở lại. Không chạy reset hoặc force push ngay khi chưa kiểm tra commit hash và các thay đổi được tạo sau rebase.

Nhánh dự phòng đã tạo trước đó cũng là một điểm tham chiếu hữu ích. Reflog và nhánh dự phòng giúp tìm lại commit, nhưng không thay thế việc sao lưu hoặc phối hợp khi thao tác trên lịch sử đã chia sẻ.

## 13. Những lỗi và hiểu lầm thường gặp

| Hiện tượng hoặc hiểu lầm | Giải thích và cách xử lý |
|---|---|
| Reword không đổi mã nguồn nhưng hash commit đổi | Thông điệp commit là một phần metadata; commit được tạo lại nên hash thay đổi. |
| Squash báo không có commit trước đó | <code>squash</code> phải đứng sau một commit đã được chọn để gộp vào. |
| Fixup vẫn giữ thông điệp commit cũ | <code>fixup</code> bỏ thông điệp của commit được gộp và giữ thông điệp của commit trước. |
| Edit dừng rebase và không biết tiếp tục thế nào | Sửa tệp, stage, amend commit rồi chạy <code>git rebase --continue</code>. |
| Drop làm mất thay đổi cần thiết | Kiểm tra commit bằng <code>git show</code> và xem các commit sau có phụ thuộc vào nó không trước khi drop. |
| Rebase tạo conflict | Giải quyết từng tệp, stage kết quả rồi continue; abort nếu cần hủy toàn bộ phiên. |
| Push bị từ chối sau rebase | Remote có thể vẫn giữ lịch sử cũ hoặc đã có commit mới. Fetch và kiểm tra trước khi quyết định. |
| Force-with-lease luôn an toàn | Lệnh chỉ kiểm tra ref remote theo kỳ vọng của client; nó không biết ai đã dùng commit cũ. |
| Có thể rebase mọi nhánh đã push | Nhánh đã chia sẻ cần phối hợp; với nhánh chung nên ưu tiên commit sửa mới hoặc revert. |

## 14. Bài tập tự kiểm tra

Thực hành trên repository thử nghiệm với một nhánh chưa chia sẻ:

1. Tạo năm commit nhỏ trên nhánh tính năng, mỗi commit có mục đích khác nhau.
2. Chạy <code>git rebase -i HEAD~5</code> và xác định commit nền cùng thứ tự todo list.
3. Đổi thông điệp một commit bằng <code>reword</code>; kiểm tra hash commit trước và sau.
4. Chọn một commit bằng <code>edit</code>, sửa nội dung, stage và amend rồi tiếp tục rebase.
5. Gộp một commit kiểm thử vào commit tính năng bằng <code>squash</code>, sau đó gộp một commit sửa nhỏ bằng <code>fixup</code>.
6. Xem nội dung một commit tạm và dùng <code>drop</code> để loại nó khỏi lịch sử mới.
7. So sánh diff tổng thể trước và sau rebase để xác nhận các thay đổi mong muốn vẫn còn.
8. Thử tạo conflict trong lúc rebase, giải quyết rồi continue; lặp lại trong một lần thử khác và dùng abort.
9. Tạo một commit <code>--fixup</code> rồi chạy <code>git rebase -i --autosquash</code> để quan sát Git sắp xếp todo list.
10. Giải thích vì sao không nên force push lịch sử mới lên nhánh mà đồng đội đã dựa vào.

Khi sử dụng thành thạo <code>reword</code>, <code>edit</code>, <code>squash</code>, <code>fixup</code> và <code>drop</code>, bạn có thể tổ chức lịch sử nhánh tính năng thành các commit rõ ràng, tập trung và dễ review. Hãy thực hiện việc đó trước khi lịch sử được chia sẻ rộng rãi, đồng thời giữ nguyên lịch sử chung của nhóm trừ khi mọi người đã phối hợp cho một lần viết lại có chủ đích.
