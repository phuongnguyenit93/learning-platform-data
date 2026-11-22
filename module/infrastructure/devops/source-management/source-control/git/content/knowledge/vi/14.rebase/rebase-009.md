# Đối chiếu chuỗi commit trước và sau bằng git range-diff

Rebase có thể thay đổi mã định danh commit, thứ tự commit hoặc nội dung patch khi bạn chỉnh sửa lịch sử. Sau khi rebase, nhìn vào danh sách commit mới chỉ cho biết lịch sử hiện tại; nó chưa trả lời được liệu các thay đổi ban đầu có còn nguyên vẹn hay không, commit nào đã được sửa, commit nào bị bỏ hoặc có thay đổi nào mới được thêm vào.

Git cung cấp lệnh **git range-diff** để so sánh hai phiên bản của một chuỗi commit. Lệnh này ghép các commit tương ứng giữa hai chuỗi dựa trên nội dung patch và hiển thị điểm giống, khác, bị loại bỏ hoặc được thêm mới. Đây là công cụ hữu ích để tự review sau rebase, đặc biệt khi bạn rebase tương tác, squash, tách commit hoặc đưa branch lên nền mới.

## 1. Vì sao cần đối chiếu chuỗi commit sau rebase?

Rebase lấy các commit của branch và phát lại chúng trên một commit nền khác. Vì mỗi commit mới có commit cha mới, mã định danh commit thường thay đổi dù nội dung thay đổi có thể vẫn tương đương.

Ví dụ, trước rebase branch có chuỗi:

~~~text
A---B---C---D  main
         \
          E---F---G  feature/search
~~~

Sau khi main có thêm commit H và bạn rebase feature/search lên H:

~~~text
A---B---C---D---H  main
                 \
                  E'---F'---G'  feature/search
~~~

Các commit E', F' và G' là những commit mới được tạo ra. Chúng không có cùng mã định danh với E, F và G. Nếu rebase chỉ đổi commit cha mà không đổi patch, nội dung thay đổi vẫn có thể tương đương. Nhưng khi rebase tương tác, bạn có thể đã:

- Chỉnh sửa nội dung một commit bằng reword hoặc edit.
- Gộp nhiều commit bằng squash hoặc fixup.
- Tách một commit lớn thành nhiều commit nhỏ.
- Đổi thứ tự commit.
- Bỏ một commit không còn cần thiết.
- Giải quyết conflict và vô tình làm thay đổi logic.
- Thêm một commit mới trong quá trình chỉnh sửa.

Vì vậy, sau rebase cần xem lại cả lịch sử lẫn nội dung. **git range-diff** giúp kiểm tra chuỗi patch trước và sau, phát hiện những khác biệt mà việc chỉ nhìn tên commit hoặc chạy git log có thể bỏ sót.

## 2. git range-diff so sánh điều gì?

git range-diff nhận hai commit range và so sánh các commit trong hai range đó. Thông thường, mỗi range biểu diễn các commit thuộc branch công việc kể từ một commit nền:

~~~text
base..tip
~~~

Trong đó:

- **base** là commit nền của chuỗi thay đổi.
- **tip** là commit cuối cùng của branch tại thời điểm cần đối chiếu.
- Các commit nằm trong range là những commit có thể đi tới từ tip nhưng không nằm trong lịch sử của base.

Nếu hai chuỗi cùng dùng một base không đổi và bạn đã lưu tip cũ bằng một ref:

~~~
git range-diff origin/main..backup/search-before-rebase origin/main..feature/search
~~~

Lệnh trên so sánh chuỗi commit cũ và chuỗi commit mới nếu cả hai đều dùng cùng một base. Trong tình huống rebase lên một base mới, cần dùng base tương ứng của từng phiên bản:

~~~
git range-diff old-base..old-tip new-base..new-tip
~~~

Đây là điểm quan trọng: nếu base của branch thay đổi sau rebase, không nên mặc định dùng một base duy nhất cho cả hai chuỗi. Nếu lấy range quá rộng, các commit đã thuộc branch nền có thể bị đưa vào phép so sánh và làm kết quả khó đọc.

git range-diff tập trung vào chuỗi patch của commit. Nó không phải phép so sánh toàn bộ hai working tree, cũng không thay thế git diff khi cần biết trạng thái tệp cuối cùng khác nhau ra sao.

## 3. Chuẩn bị trước khi rebase

Để đối chiếu chính xác, hãy lưu lại mốc của branch trước khi viết lại lịch sử. Cách đáng tin cậy là tạo branch backup trỏ tới tip cũ và một branch backup trỏ tới base cũ.

Giả sử:

- Branch nền là origin/main.
- Branch đang làm việc là feature/search.
- Bạn muốn rebase feature/search lên origin/main mới nhất.

### 3.1. Kiểm tra trạng thái và cập nhật thông tin remote

~~~
git switch feature/search
git status -sb
git fetch origin
git log --oneline --graph --decorate --all
~~~

Trước khi rebase, working tree nên sạch. Nếu còn thay đổi chưa commit, hãy hoàn thành commit hoặc cất chúng bằng stash sau khi đã kiểm tra nội dung. Không bắt đầu rebase khi chưa biết rõ những thay đổi local đang nằm ở đâu.

### 3.2. Lưu tip cũ và base cũ

Tạo branch backup cho tip hiện tại:

~~~
git branch backup/search-before-rebase feature/search
~~~

Tạo branch backup cho commit nền chung giữa branch công việc và branch nền:

~~~
git branch backup/search-base-before "$(git merge-base origin/main feature/search)"
~~~

Hai branch backup này giữ lại các mốc để so sánh sau rebase. Tên backup nên duy nhất trong repository; nếu tên đã tồn tại, hãy chọn tên khác để không vô tình thay đổi một mốc đang cần giữ.

Có thể kiểm tra lại:

~~~
git show -s --oneline backup/search-before-rebase
git show -s --oneline backup/search-base-before
~~~

Lưu lại các mốc này cho đến khi hoàn tất review. Không nên chỉ dựa vào ORIG_HEAD hoặc HEAD@{1} làm bản lưu duy nhất: reflog và ORIG_HEAD có thể thay đổi sau những thao tác Git tiếp theo, trong khi branch backup có tên rõ ràng và dễ tham chiếu.

## 4. Thực hiện rebase

Sau khi đã lưu mốc:

~~~
git rebase origin/main
~~~

Nếu muốn chỉnh sửa chuỗi commit, có thể dùng rebase tương tác:

~~~
git rebase -i origin/main
~~~

Trong trình soạn thảo, bạn có thể chọn các hành động như:

| Hành động | Tác dụng |
|---|---|
| pick | Giữ commit |
| reword | Giữ patch, sửa commit message |
| edit | Dừng tại commit để chỉnh sửa |
| squash | Gộp commit vào commit trước và chỉnh message |
| fixup | Gộp commit vào commit trước, bỏ message của commit được gộp |
| drop | Bỏ commit khỏi chuỗi |

Sau khi rebase hoàn tất, kiểm tra branch hiện tại và lưu base mới:

~~~
git status -sb
git log --oneline --graph --decorate -10
git branch backup/search-base-after "$(git merge-base origin/main feature/search)"
~~~

Branch backup/search-base-after trỏ tới commit nền mới của chuỗi sau rebase. Nếu rebase bị dừng vì conflict, hãy giải quyết từng tệp, stage kết quả và chạy git rebase --continue. Nếu cần hủy toàn bộ lần rebase đang thực hiện, dùng git rebase --abort khi quy trình rebase vẫn còn hoạt động.

Không xóa branch backup cũ sau khi rebase chỉ vì branch mới đã chạy được. Hãy dùng chúng để đối chiếu và giữ lại cho đến khi bạn chắc chắn không cần khôi phục hoặc kiểm tra thêm.

## 5. Chạy git range-diff sau rebase

Khi đã có đủ bốn mốc, chạy:

~~~
git range-diff backup/search-base-before..backup/search-before-rebase backup/search-base-after..feature/search
~~~

Lệnh này so sánh:

- Chuỗi thứ nhất: các commit của feature/search trước rebase, từ base cũ đến tip cũ.
- Chuỗi thứ hai: các commit của feature/search sau rebase, từ base mới đến tip mới.

Nếu base không thay đổi, bạn có thể dùng cùng một base cho hai range. Tuy nhiên, giữ riêng base cũ và base mới giúp quy trình rõ ràng khi rebase lên branch nền đã tiến lên.

### Ví dụ kết quả

Giả sử trước rebase có ba commit:

~~~text
1:  a1b2c3d Add search endpoint
2:  b2c3d4e Handle empty query
3:  c3d4e5f Add search tests
~~~

Sau rebase, kết quả range-diff có thể trông như sau:

~~~text
1:  a1b2c3d = 1:  d4e5f6a Add search endpoint
2:  b2c3d4e ! 2:  e5f6a7b Handle empty query
3:  c3d4e5f < -:  ------- Add search tests
-:  ------- > 3:  f6a7b8c Add search and pagination tests
~~~

Ý nghĩa:

- Commit thứ nhất có patch tương đương trước và sau rebase.
- Commit thứ hai vẫn có cặp tương ứng nhưng patch đã thay đổi.
- Commit thứ ba của chuỗi cũ không còn cặp tương ứng trong chuỗi mới.
- Chuỗi mới có thêm một commit mà chuỗi cũ không có.

Kết quả này không tự kết luận thay đổi là đúng hay sai. Nó chỉ chỉ ra những điểm cần bạn xem xét. Ví dụ, commit cũ bị bỏ có thể đã được gộp vào commit mới; một commit mới có thể là phần tách ra có chủ đích. Hãy đối chiếu với mục tiêu ban đầu và nội dung patch.

## 6. Đọc các ký hiệu trong kết quả

git range-diff dùng ký hiệu để mô tả quan hệ giữa các commit:

| Ký hiệu | Ý nghĩa | Việc nên làm |
|---|---|---|
| = | Commit được ghép cặp và patch tương đương | Kiểm tra nhanh tiêu đề và ngữ cảnh |
| ! | Có commit tương ứng nhưng patch hoặc nội dung commit đã thay đổi | Mở phần diff để hiểu thay đổi |
| < | Commit chỉ xuất hiện trong range thứ nhất | Xác định commit bị bỏ hay đã được gộp/tách |
| > | Commit chỉ xuất hiện trong range thứ hai | Xác định commit mới có đúng mục đích không |

Mỗi dòng thường hiển thị vị trí và mã commit ở cả hai phía. Ví dụ:

~~~text
2: b2c3d4e ! 2: e5f6a7b Handle empty query
~~~

Số thứ nhất là vị trí commit trong chuỗi cũ; số thứ hai là vị trí trong chuỗi mới. Hai mã commit có thể khác nhau vì rebase tạo commit mới. Dấu ! cho biết cần xem phần so sánh chi tiết được hiển thị bên dưới dòng đó.

### 6.1. Dấu bằng không có nghĩa là toàn bộ branch giống hệt

Dấu = có nghĩa commit được ghép cặp có patch tương đương theo cách đối chiếu của range-diff. Base của hai branch có thể khác nhau và lịch sử tổng thể chắc chắn có thể khác do rebase.

Vì vậy, dấu = không chứng minh rằng:

- Hai branch có cùng mã định danh commit.
- Mọi tệp trong working tree đều giống nhau.
- Các thay đổi của branch nền mới không ảnh hưởng đến hành vi ứng dụng.
- Kiểm thử hoặc yêu cầu nghiệp vụ đã được đáp ứng.

Sau khi range-diff cho thấy chuỗi patch như mong đợi, vẫn cần chạy test và review trạng thái cuối.

### 6.2. Dấu chấm than cần được đọc kỹ

Dấu ! thường là phần quan trọng nhất khi kiểm tra rebase. Nó có thể xuất hiện khi:

- Bạn chỉnh sửa logic trong quá trình giải quyết conflict.
- Bạn sửa commit bằng rebase -i.
- Một thay đổi được viết lại để phù hợp với API mới ở branch nền.
- Commit message thay đổi cùng với patch.
- Commit được tách hoặc gộp khiến cách ghép cặp thay đổi.

Hãy đọc phần diff được range-diff trình bày, rồi xem lại commit mới:

~~~
git show --stat e5f6a7b
git show e5f6a7b
~~~

Nếu thay đổi là có chủ đích, ghi nhớ lý do hoặc cập nhật PR để reviewer hiểu. Nếu thay đổi là ngoài ý muốn, sửa lại trên branch mới và chạy test.

### 6.3. Commit chỉ có ở một phía

Dấu < cho biết commit chỉ nằm trong chuỗi cũ; dấu > cho biết commit chỉ nằm trong chuỗi mới. Khi bạn squash hai commit thành một, range-diff có thể hiển thị một commit cũ không còn ghép cặp và một commit mới đại diện cho phần thay đổi đã gộp.

Không nên tự động kết luận rằng mọi dấu < đều là mất dữ liệu hoặc mọi dấu > đều là thay đổi thừa. Hãy kiểm tra xem patch của commit cũ đã được đưa vào commit mới hay chưa. Bắt đầu bằng cách liệt kê hai chuỗi commit:

~~~
git log --oneline --reverse backup/search-base-before..backup/search-before-rebase
git log --oneline --reverse backup/search-base-after..feature/search
~~~

Sau đó dùng git show với mã commit cụ thể để đọc patch cũ và patch mới đã được ghép cặp. Các lệnh này giúp xác định thay đổi cũ đã được gộp vào commit nào hay thực sự bị bỏ.

## 7. Xem chi tiết những thay đổi được phát hiện

### 7.1. Đối chiếu một commit cụ thể

Khi range-diff báo một commit có dấu !, mở hai commit tương ứng bằng mã SHA hiển thị ở dòng kết quả:

~~~
git show <old-commit-sha>
git show <new-commit-sha>
~~~

Thay các placeholder bằng mã commit thực tế. Đọc cả phần thêm, xóa và ngữ cảnh xung quanh để xác định thay đổi có làm lệch yêu cầu hay không.

### 7.2. So sánh trạng thái tệp cuối cùng

range-diff so sánh các patch riêng lẻ trong hai chuỗi. Để xem toàn bộ nội dung thay đổi của branch trước và sau rebase, dùng diff với các base tương ứng:

~~~
git diff backup/search-base-before backup/search-before-rebase
git diff backup/search-base-after feature/search
~~~

Hai lệnh này giúp kiểm tra kết quả tổng thể của từng chuỗi. Nếu cần so sánh trực tiếp hai cây nội dung ở tip:

~~~
git diff backup/search-before-rebase feature/search
~~~

Lưu ý rằng diff trực tiếp giữa hai tip cũng phản ánh thay đổi của branch nền mới. Nó có thể bao gồm rất nhiều thay đổi không thuộc patch series của bạn. Vì vậy, hãy dùng range-diff để review chuỗi commit và dùng diff với base tương ứng để xem phạm vi thay đổi của từng phiên bản.

### 7.3. Kiểm tra thứ tự và cấu trúc lịch sử

Đọc danh sách commit theo thứ tự:

~~~
git log --oneline --reverse backup/search-base-before..backup/search-before-rebase
git log --oneline --reverse backup/search-base-after..feature/search
~~~

Nếu bạn đã sắp xếp lại commit bằng rebase tương tác, hãy xác nhận thứ tự mới phản ánh đúng phụ thuộc giữa các thay đổi. Ví dụ, commit thêm hàm cần xuất hiện trước commit gọi hàm đó nếu nhóm muốn từng commit có thể được kiểm thử độc lập.

## 8. Khi range-diff cho thấy khác biệt ngoài dự kiến

Không nên push ngay sau khi thấy output có nhiều dấu !, < hoặc >. Hãy phân loại nguyên nhân và kiểm tra theo trình tự.

### 8.1. Commit bị thiếu

Nếu một commit cũ chỉ có dấu <:

1. Xem nội dung commit cũ bằng git show.
2. Tìm xem thay đổi có được gộp vào commit mới hay không.
3. Kiểm tra diff tổng thể của chuỗi mới.
4. Nếu thay đổi thực sự bị mất, phục hồi patch hoặc tạo commit mới chứa phần còn thiếu.

Có thể áp dụng lại một commit cũ bằng cherry-pick nếu phù hợp, nhưng cần xem xét quan hệ phụ thuộc và tránh áp dụng trùng patch đã được gộp:

~~~
git cherry-pick <old-commit>
~~~

Trong ví dụ tài liệu, <old-commit> là chỗ giữ chỗ; thay bằng mã commit thực tế từ branch backup. Sau cherry-pick, kiểm tra conflict, diff và test.

### 8.2. Commit mới không mong muốn

Nếu một commit chỉ có ở chuỗi mới:

1. Xác định nó được tạo ra từ thao tác nào.
2. Kiểm tra patch có thuộc yêu cầu hay là thay đổi phát sinh ngoài phạm vi.
3. Nếu là thay đổi cần thiết để tương thích với base mới, ghi lại lý do.
4. Nếu là thay đổi vô tình, sửa lại branch bằng một commit có chủ đích hoặc thực hiện rebase tương tác sau khi đã lưu mốc.

Không xóa commit chỉ vì nó không có cặp tương ứng. Có thể đó là commit được tách ra hoặc phần sửa mới cần thiết.

### 8.3. Patch bị thay đổi ngoài ý muốn

Khi có dấu !, xem phần diff chi tiết và xác định:

- Có dòng logic nào bị bỏ?
- Có điều kiện hoặc trường hợp lỗi nào thay đổi?
- Có thay đổi tên hoặc cấu trúc nhưng vẫn giữ nguyên hành vi không?
- Conflict resolution có chọn nhầm một phía?
- Commit message có thay đổi khiến reviewer hiểu sai mục tiêu?

Nếu khác biệt có chủ đích, thêm ngữ cảnh vào mô tả PR. Nếu khác biệt không có chủ đích, sửa lại, chạy test và chạy range-diff lần nữa.

## 9. Một số tùy chọn hữu ích

### 9.1. Điều chỉnh ngưỡng ghép cặp

git range-diff dùng thuật toán ghép cặp để tìm commit tương ứng giữa hai chuỗi. Khi commit bị tách, gộp hoặc thay đổi lớn, thuật toán có thể ghép cặp chưa như mong muốn. Tùy chọn --creation-factor điều chỉnh mức độ linh hoạt khi ghép:

~~~
git range-diff --creation-factor=80 old-base..old-tip new-base..new-tip
~~~

Giá trị lớn hơn có thể giúp ghép những commit đã thay đổi nhiều hơn, nhưng cũng có thể tạo ra cặp ghép ít trực quan. Hãy dùng nó để hỗ trợ điều tra, không phải để ép kết quả trông giống nhau.

### 9.2. Chỉ xem commit thuộc một phía

Khi muốn tập trung vào những commit chỉ xuất hiện trong range cũ hoặc mới, có thể dùng:

~~~
git range-diff --left-only old-base..old-tip new-base..new-tip
git range-diff --right-only old-base..old-tip new-base..new-tip
~~~

--left-only giới hạn kết quả ở phía range thứ nhất; --right-only giới hạn ở phía range thứ hai. Chúng hữu ích khi cần tìm commit đã biến mất hoặc commit được thêm vào.

### 9.3. Xem trợ giúp và phiên bản Git

git range-diff có từ Git 2.19. Nếu lệnh không tồn tại trên máy, kiểm tra phiên bản:

~~~
git --version
git range-diff -h
~~~

Hãy dùng phiên bản Git đủ mới theo yêu cầu công cụ của dự án. Nếu môi trường chưa hỗ trợ, có thể so sánh thủ công bằng git log, git show và git diff, nhưng cách đó không có khả năng ghép cặp patch tự động như range-diff.

## 10. Những giới hạn cần hiểu

git range-diff là công cụ hỗ trợ review, không phải bộ xác minh tính đúng đắn của chương trình.

**Nó so sánh patch, không đánh giá ý nghĩa nghiệp vụ.** Hai patch có vẻ tương tự vẫn có thể tạo hành vi khác khi kết hợp với branch nền mới. Ngược lại, patch thay đổi lớn có thể vẫn đúng vì API hoặc thiết kế đã thay đổi.

**Kết quả ghép cặp dựa trên heuristic.** Khi commit được tách, gộp hoặc viết lại mạnh, thuật toán có thể ghép cặp khác với cách con người mong đợi. Hãy đọc cả hai range và điều chỉnh creation factor khi cần.

**Nó không thay thế test.** Dấu = không chứng minh ứng dụng chạy đúng; dấu ! cũng không tự động có nghĩa là lỗi. Chạy unit test, integration test, static analysis và các kiểm tra phù hợp với thay đổi.

**Nó không thay thế diff toàn cây.** Nếu cần biết trạng thái cuối của tất cả tệp khác nhau thế nào, hãy dùng git diff với các mốc phù hợp.

**Nó phù hợp nhất với chuỗi commit tuyến tính.** Khi lịch sử có nhiều merge commit hoặc topology phức tạp, range-diff có thể không diễn tả đầy đủ cấu trúc merge. Kết hợp git log --graph và git diff để xem lịch sử và nội dung.

**Nó cần hai chuỗi commit có thể truy cập.** Nếu không lưu tip cũ và các object cũ đã bị dọn khỏi repository, việc so sánh có thể khó hoặc không thể thực hiện. Hãy tạo branch backup trước khi rebase.

## 11. Quy trình kiểm tra sau rebase nên áp dụng

Một quy trình ngắn gọn có thể dùng cho mỗi lần rebase quan trọng:

1. Fetch thông tin mới từ remote và xác nhận working tree sạch.
2. Tạo branch backup cho tip cũ và base cũ.
3. Rebase branch lên base mới hoặc thực hiện rebase tương tác.
4. Tạo mốc base mới sau khi rebase hoàn tất.
5. Chạy git range-diff với hai cặp base-tip tương ứng.
6. Điều tra mọi dấu !, < và >; xác nhận thay đổi bị gộp, tách hoặc thêm mới là có chủ đích.
7. Dùng git log để kiểm tra thứ tự commit và git diff để kiểm tra trạng thái tệp.
8. Chạy test và kiểm tra chất lượng cần thiết.
9. Cập nhật mô tả PR/MR để reviewer biết lịch sử đã được viết lại và những khác biệt đáng chú ý.
10. Chỉ push sau khi đã hiểu tác động. Nếu branch đã được chia sẻ và rebase làm thay đổi commit, phối hợp với cộng tác viên; dùng --force-with-lease khi chính sách cho phép và hiểu rõ remote sẽ được cập nhật như thế nào.

Nếu cần cập nhật branch remote sau rebase, thao tác force push có thể cần thiết vì commit SHA đã thay đổi. Ưu tiên --force-with-lease thay cho --force để Git kiểm tra remote vẫn ở mốc mà local dự kiến. Đây vẫn là thao tác viết lại lịch sử và cần phối hợp nếu branch được người khác sử dụng.

## 12. Ví dụ hoàn chỉnh

Giả sử bạn có branch feature/search với ba commit đã được push lên remote. Nhóm yêu cầu rebase lên origin/main mới nhất và review lại để chắc chắn không mất thay đổi.

**Trước rebase:**

~~~
git switch feature/search
git fetch origin
git status -sb
git branch backup/search-before-rebase feature/search
git branch backup/search-base-before "$(git merge-base origin/main feature/search)"
~~~

**Rebase:**

~~~
git rebase origin/main
~~~

Nếu có conflict, giải quyết từng tệp, stage kết quả và tiếp tục:

~~~
git add src/search/search-service.ts
git rebase --continue
~~~

**Sau rebase:**

~~~
git status -sb
git branch backup/search-base-after "$(git merge-base origin/main feature/search)"
git range-diff backup/search-base-before..backup/search-before-rebase backup/search-base-after..feature/search
~~~

Giả sử output cho thấy hai commit có dấu =, một commit có dấu ! và một commit cũ có dấu <. Bạn cần đọc patch của commit có dấu !, sau đó xác định thay đổi của commit cũ có dấu < đã được gộp vào commit mới nào hay thực sự bị mất. Khi đã xác nhận, kiểm tra:

~~~
git log --oneline --reverse origin/main..feature/search
git diff origin/main..feature/search
~~~

Chạy test liên quan đến search, kiểm tra PR và cập nhật reviewer về những thay đổi đã thực hiện trong rebase. Nếu branch đã được push trước đó, chỉ cập nhật remote sau khi đã thống nhất cách force push an toàn với nhóm.

## 13. Checklist đối chiếu chuỗi commit

**Trước rebase**

- [ ] Working tree sạch và branch hiện tại đúng.
- [ ] Đã fetch branch nền mới nhất.
- [ ] Đã lưu tip cũ bằng branch backup.
- [ ] Đã lưu base cũ để xác định đúng phạm vi patch series.

**Sau rebase**

- [ ] Rebase hoàn tất và working tree ở trạng thái mong muốn.
- [ ] Đã lưu base mới tương ứng với chuỗi sau rebase.
- [ ] Đã chạy range-diff giữa hai cặp base-tip.
- [ ] Đã xem mọi commit có dấu !, < và >.
- [ ] Đã xác nhận commit bị gộp, tách, thêm hoặc bỏ đều có chủ đích.
- [ ] Đã kiểm tra thứ tự commit và diff của trạng thái cuối.
- [ ] Đã chạy test và các kiểm tra cần thiết.
- [ ] Đã thông báo cho reviewer và cộng tác viên nếu lịch sử branch thay đổi.

## 14. Kết luận

git range-diff giúp kiểm tra một chuỗi commit đã thay đổi thế nào sau rebase bằng cách ghép các patch cũ và mới. Dấu = cho biết patch tương đương, dấu ! báo patch đã thay đổi, dấu < và > giúp tìm commit chỉ có ở một phía. Để kết quả có ý nghĩa, cần lưu tip và base trước rebase, rồi so sánh đúng hai cặp range tương ứng.

Hãy dùng range-diff cùng git log, git diff và test. Công cụ giúp bạn nhìn thấy khác biệt trong lịch sử; việc xác nhận thay đổi có đúng yêu cầu hay không vẫn cần review nội dung và kiểm tra hành vi của chương trình.
