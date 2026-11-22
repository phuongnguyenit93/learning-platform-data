# Chỉ mục biểu diễn cây dự kiến và các stage khi có xung đột

Trong Git, staging area thường được hiểu là nơi chuẩn bị nội dung cho commit tiếp theo. Bên trong, nó được lưu dưới dạng **index**: một cấu trúc dữ liệu ghi nhận đường dẫn, mode, mã object và trạng thái của từng mục. Khi repository ở trạng thái bình thường, mỗi đường dẫn được theo dõi thường có một index entry ở stage 0. Khi merge hoặc một thao tác tích hợp khác phát sinh xung đột, một đường dẫn có thể có nhiều entry ở các stage 1, 2 và 3 để giữ lại những phiên bản cần thiết cho việc giải quyết.

Hiểu index giúp bạn đọc được Git đang chuẩn bị commit cây thư mục nào, vì sao một tệp xung đột có nhiều phiên bản và lệnh nào sẽ chuyển các phiên bản đó thành kết quả cuối cùng. Bài học này tập trung vào cấu trúc index, ý nghĩa stage 0–3, cách kiểm tra bằng plumbing commands và quy trình giải quyết conflict an toàn.

## 1. Index là gì và nằm ở đâu?

### 1.1. Index là staging area

Index là cấu trúc dữ liệu Git dùng để ghi nhận snapshot dự kiến cho commit tiếp theo. Khi chạy:

~~~bash
git add src/PaymentService.java
~~~

Git đọc nội dung tệp trong working tree, tạo hoặc tìm blob object tương ứng rồi cập nhật entry trong index. Từ thời điểm đó, nội dung đã stage được giữ trong index ngay cả khi bạn tiếp tục chỉnh sửa tệp trên đĩa.

Có thể kiểm tra ba trạng thái bằng:

~~~bash
git status
git diff
git diff --cached
~~~

- **git diff** so sánh working tree với index, cho biết thay đổi chưa stage.
- **git diff --cached** so sánh index với HEAD, cho biết thay đổi đã stage để commit.
- **git status** tổng hợp trạng thái branch, index và working tree.

Index không phải bản sao nguyên văn của toàn bộ working tree. Nó ghi nhận nội dung đã được chọn cho snapshot tiếp theo. Vì vậy, một tệp có thể đồng thời có phần staged và phần unstaged nếu bạn sửa tệp sau khi đã chạy git add.

### 1.2. Vị trí file index

Trong một repository thông thường, index thường nằm ở .git/index. Tuy nhiên, không nên mặc định đường dẫn đó luôn đúng, vì linked worktree và một số cách bố trí repository có thể dùng Git directory riêng.

Lấy đường dẫn chính xác:

~~~bash
git rev-parse --git-path index
~~~

Xem Git directory và gốc working tree:

~~~bash
git rev-parse --git-dir
git rev-parse --show-toplevel
~~~

Index là file nhị phân do Git quản lý. Không chỉnh sửa trực tiếp bằng text editor hoặc script tùy tiện. Dùng các lệnh như git add, git rm, git restore --staged và các lệnh Git tương ứng để thay đổi index.

### 1.3. Index lưu những thông tin gì?

Một index entry thông thường gắn với:

- **Path:** đường dẫn tương đối từ gốc working tree.
- **Mode:** kiểu và quyền thực thi của mục.
- **Object ID (OID):** mã định danh blob hoặc gitlink được tham chiếu.
- **Stage:** số stage, cho biết entry là trạng thái bình thường hay một phiên bản của đường dẫn đang xung đột.
- **Flags và metadata:** thông tin phục vụ hiệu năng, trạng thái và cách Git xử lý entry.

Index không lưu toàn bộ nội dung tệp trực tiếp trong entry. Nội dung thường nằm trong Git object database; index tham chiếu đến object bằng OID.

## 2. Stage 0 và các stage khi có xung đột

### 2.1. Stage 0 là entry bình thường

Khi không có conflict, một đường dẫn thường có một entry ở stage 0. Đây là nội dung hiện được index chọn để đưa vào cây commit tiếp theo.

Ví dụ:

~~~bash
git ls-files --stage -- src/PaymentService.java
~~~

Đầu ra minh họa:

~~~text
100644 6f1a... 0    src/PaymentService.java
~~~

Cấu trúc mỗi dòng:

~~~text
<mode> <object-id> <stage><TAB><path>
~~~

Trong đó:

- **100644:** tệp thường không có bit executable.
- **100755:** tệp thường có bit executable.
- **120000:** symbolic link; OID trỏ đến nội dung đích được lưu dưới dạng blob.
- **160000:** gitlink; OID trỏ đến commit của submodule.
- **6f1a...:** OID của object được index tham chiếu.
- **0:** stage 0, entry bình thường.
- **src/PaymentService.java:** đường dẫn.

**Stage 0 không có nghĩa là “chưa stage”.** Stage là số phân loại entry trong index; stage 0 vẫn là nội dung đã nằm trong staging area. Khái niệm staged/unstaged và số stage là hai cách mô tả khác nhau.

### 2.2. Stage 1, 2 và 3 lưu các phiên bản conflict

Khi Git không thể tự kết hợp một đường dẫn trong merge, index có thể giữ tối đa ba phiên bản:

| Stage | Ý nghĩa | Tên thường dùng |
| --- | --- | --- |
| 1 | Phiên bản từ merge base chung | Base |
| 2 | Phiên bản từ phía đang nhận thay đổi | Ours |
| 3 | Phiên bản từ phía được tích hợp vào | Theirs |

Ví dụ, hai nhánh cùng sửa một dòng:

- Base: timeout=30
- Ours: timeout=45
- Theirs: timeout=60

Index có thể chứa:

~~~text
100644 <oid-base>   1    config/app.properties
100644 <oid-ours>   2    config/app.properties
100644 <oid-theirs> 3    config/app.properties
~~~

Đường dẫn đang xung đột có nhiều entry cùng tên nhưng khác stage. Git chưa có một kết quả duy nhất ở stage 0 cho đường dẫn đó.

Khi bạn chỉnh sửa nội dung cuối cùng và chạy git add, Git ghi một blob mới vào index ở stage 0, đồng thời loại bỏ các entry conflict 1, 2 và 3 của đường dẫn đó.

### 2.3. Các stage không phải ba bản sao trong working tree

Index giữ các phiên bản base, ours và theirs dưới dạng tham chiếu đến object. Working tree thường chỉ có một đường dẫn vật lý cho tên tệp đó.

Với conflict văn bản, Git có thể ghi các marker vào working tree:

~~~text
<<<<<<< HEAD
timeout=45
=======
timeout=60
>>>>>>> feature/tune-timeout
~~~

Các marker giúp người dùng nhìn thấy vùng cần xử lý. Chúng không phải ba stage trong index và cũng không được tự động commit như kết quả mong muốn. Bạn phải chỉnh nội dung thành phiên bản cuối cùng rồi stage lại.

Với tệp nhị phân, Git không thể chèn marker văn bản có ý nghĩa. Bạn cần chọn hoặc tạo nội dung nhị phân cuối cùng bằng công cụ phù hợp rồi stage tệp.

## 3. Đọc index bằng git ls-files

### 3.1. Xem tất cả entry và stage

Lệnh:

~~~bash
git ls-files --stage
~~~

Hiển thị các entry trong index cùng mode, OID và stage. Đây là lệnh hữu ích nhất để quan sát trực tiếp cấu trúc index.

Giới hạn vào một tệp:

~~~bash
git ls-files --stage -- config/app.properties
~~~

Giới hạn vào một thư mục:

~~~bash
git ls-files --stage -- src/
~~~

Khi repository lớn, nên giới hạn đường dẫn để đầu ra dễ đọc.

### 3.2. Chỉ xem các entry chưa hợp nhất

Dùng:

~~~bash
git ls-files --unmerged
~~~

Hoặc:

~~~bash
git ls-files -u
~~~

Hai cách gọi này liệt kê các entry unmerged, thường là stage 1, 2 và 3. Nếu không có output, index hiện không có entry unmerged theo cách Git báo cáo.

Có thể kết hợp đường dẫn:

~~~bash
git ls-files -u -- config/
~~~

Lệnh này giúp xác định các tệp trong thư mục cấu hình vẫn còn conflict.

### 3.3. Xem thông tin chi tiết của index entry

Dùng:

~~~bash
git ls-files --debug -- config/app.properties
~~~

Tùy chọn --debug bổ sung thông tin nội bộ như flags và metadata của entry. Đầu ra chủ yếu phục vụ điều tra; định dạng có thể thay đổi theo phiên bản Git, nên không nên dùng làm giao diện ổn định cho script.

### 3.4. Phân biệt index với cây commit

Index là snapshot đang chuẩn bị. Cây commit là cấu trúc đã được ghi nhận trong một commit.

Xem cây của commit hiện tại:

~~~bash
git ls-tree -r HEAD
~~~

Xem entry trong index:

~~~bash
git ls-files --stage
~~~

Hai đầu ra có thể khác nhau khi bạn đã stage thay đổi nhưng chưa commit. Cây commit phản ánh snapshot của HEAD; index phản ánh snapshot dự kiến cho commit kế tiếp.

## 4. Đọc từng phiên bản bằng cú pháp stage

### 4.1. Dùng git show :<stage>:<path>

Git cho phép truy cập nội dung từng stage bằng revision có dạng dấu hai chấm, số stage, dấu hai chấm và đường dẫn. Ví dụ, để đọc stage 2 của một tệp, dùng lệnh cụ thể ở phần dưới. Các ký hiệu giữ chỗ như tên stage hoặc path trong tài liệu không phải đối số cần gõ nguyên văn vào shell.

Ví dụ:

~~~bash
git show :1:config/app.properties
git show :2:config/app.properties
git show :3:config/app.properties
~~~

Ba lệnh lần lượt hiển thị base, ours và theirs của đường dẫn đang xung đột.

Nếu một stage không tồn tại, lệnh sẽ báo lỗi. Đây là tình huống hợp lệ với một số kiểu conflict, không nhất thiết là index hỏng.

Có thể dùng git cat-file -p để đọc object được stage tham chiếu:

~~~bash
git cat-file -p :2:config/app.properties
~~~

### 4.2. Lưu ý khi tên đường dẫn có ký tự đặc biệt

Nếu đường dẫn có khoảng trắng hoặc ký tự shell đặc biệt, hãy đặt trong dấu nháy:

~~~bash
git show ':2:config/production settings.yml'
~~~

Cú pháp revision-stage được Git phân tích; dấu nháy giúp shell chuyển nguyên đối số mà không tách hoặc diễn giải các ký tự trong đường dẫn.

### 4.3. Đối chiếu với working tree

Trong lúc conflict, bạn có thể so sánh phiên bản đang có trong working tree với các stage bằng các lệnh diff chuyên biệt:

~~~bash
git diff --base -- config/app.properties
git diff --ours -- config/app.properties
git diff --theirs -- config/app.properties
git diff --cc -- config/app.properties
~~~

- **--base:** so sánh working tree với stage 1.
- **--ours:** so sánh working tree với stage 2.
- **--theirs:** so sánh working tree với stage 3.
- **--cc:** hiển thị combined diff cho vùng conflict.

Các tùy chọn so sánh chỉ có ý nghĩa khi stage tương ứng tồn tại. Nếu stage 1 hoặc một phía bị thiếu, hãy kiểm tra git ls-files -u trước khi dùng.

## 5. Vì sao Git tạo nhiều stage?

### 5.1. Xung đột nội dung khi merge

Giả sử main và feature cùng sửa một dòng trong config/app.properties. Git tìm merge base, lấy phiên bản từ hai nhánh và thử kết hợp.

Nếu các thay đổi không chồng lấn, Git có thể tự merge. Nếu cả hai thay đổi cùng vùng và không thể kết hợp tự động, Git giữ lại ba phiên bản ở stage 1, 2, 3 để người dùng quyết định.

Trạng thái:

~~~text
HEAD (main)       -> phiên bản ours
MERGE_HEAD        -> phiên bản theirs
Index:
  stage 1         -> merge base
  stage 2         -> ours
  stage 3         -> theirs
Working tree      -> nội dung cần người dùng giải quyết
~~~

Trong merge thông thường, stage 2 tương ứng với nhánh hiện tại và stage 3 tương ứng với nhánh được merge vào.

### 5.2. Xung đột add/add

Nếu cả hai nhánh cùng tạo một đường dẫn mới với nội dung khác nhau, có thể không tồn tại phiên bản chung trong merge base.

Ví dụ:

- Nhánh hiện tại thêm config/new-feature.yml.
- Nhánh được merge cũng thêm cùng đường dẫn với nội dung khác.

Index có thể chỉ có stage 2 và stage 3; stage 1 không tồn tại vì tệp chưa có ở base.

~~~text
100644 <oid-ours>   2    config/new-feature.yml
100644 <oid-theirs> 3    config/new-feature.yml
~~~

Đừng coi việc thiếu stage 1 là lỗi. Đây là kết quả phù hợp với lịch sử add/add.

### 5.3. Xung đột modify/delete

Một nhánh sửa tệp trong khi nhánh kia xóa tệp. Index chỉ có phiên bản từ phía còn tệp; stage của phía đã xóa sẽ không có entry.

Ví dụ, nếu ours sửa và theirs xóa:

~~~text
100644 <oid-ours> 2    docs/old-guide.md
~~~

Trong trường hợp ngược lại, entry có thể chỉ ở stage 3. Hãy kiểm tra git status và git ls-files -u để xác định phía nào còn nội dung.

### 5.4. Rename và directory/file conflict

Xung đột đổi tên hoặc xung đột giữa tệp và thư mục có thể làm đường dẫn trong index khác với tên bạn dự kiến. Không phải mọi conflict đều biểu diễn bằng ba dòng cùng một path.

Khi gặp trường hợp này:

~~~bash
git status
git ls-files -u
~~~

Đọc tất cả đường dẫn được liệt kê, so sánh lịch sử hai nhánh và quyết định cấu trúc cuối cùng. Đừng chỉ chạy git show :1:old-path nếu Git đã chuyển đường dẫn trong một phía sang tên mới.

## 6. Quy trình đọc và giải quyết conflict

### Bước 1 — Xác định thao tác đang dở

~~~bash
git status
git branch --show-current
~~~

Thông báo của Git thường cho biết đang merge, rebase, cherry-pick hoặc revert. Cùng một index stage có thể xuất hiện trong nhiều thao tác tích hợp; cần biết thao tác nào đang được thực hiện để chọn lệnh tiếp tục phù hợp.

### Bước 2 — Liệt kê đường dẫn unmerged

~~~bash
git diff --name-only --diff-filter=U
git ls-files -u
~~~

Lệnh đầu liệt kê đường dẫn chưa hợp nhất theo trạng thái diff. Lệnh thứ hai hiển thị các entry index và stage tương ứng.

### Bước 3 — Đọc các phiên bản

Với mỗi tệp có đủ ba stage:

~~~bash
git show :1:config/app.properties
git show :2:config/app.properties
git show :3:config/app.properties
~~~

So sánh base, ours và theirs để hiểu mỗi nhánh đã thay đổi gì. Với stage bị thiếu, dùng những phiên bản hiện có và lịch sử commit để suy luận kết quả cần giữ.

### Bước 4 — Chỉnh nội dung cuối cùng trong working tree

Mở tệp và xử lý các marker:

~~~text
<<<<<<< HEAD
timeout=45
=======
timeout=60
>>>>>>> feature/tune-timeout
~~~

Ví dụ, sau khi thống nhất giá trị phù hợp:

~~~properties
timeout=60
~~~

Xóa toàn bộ marker và kiểm tra nội dung xung quanh. Không chọn máy móc một phía nếu thay đổi của cả hai phía đều cần được giữ.

### Bước 5 — Đưa kết quả vào stage 0

Nếu giữ tệp với nội dung đã giải quyết:

~~~bash
git add -- config/app.properties
~~~

Nếu quyết định xóa tệp:

~~~bash
git rm -- docs/old-guide.md
~~~

git add ghi nội dung working tree thành một entry bình thường ở stage 0 và loại các entry conflict của đường dẫn đó. git rm ghi nhận quyết định xóa bằng cách loại đường dẫn khỏi index.

### Bước 6 — Xác nhận không còn stage conflict

~~~bash
git ls-files -u
git ls-files --stage -- config/app.properties
git status
~~~

Nếu đường dẫn đã giải quyết, git ls-files -u không còn liệt kê nó. Với tệp vẫn tồn tại, git ls-files --stage thường hiển thị một entry ở stage 0. Với tệp đã được giải quyết bằng cách xóa, đường dẫn không còn entry trong index.

### Bước 7 — Kiểm tra snapshot chuẩn bị commit

~~~bash
git diff --cached
git diff
git status
~~~

Kiểm tra phần đã stage và phần còn chưa stage. Chạy test liên quan để xác nhận kết quả merge đúng về mặt chức năng.

### Bước 8 — Hoàn tất thao tác tích hợp

Nếu đang merge:

~~~bash
git merge --continue
~~~

Nếu đang rebase:

~~~bash
git rebase --continue
~~~

Nếu đang cherry-pick:

~~~bash
git cherry-pick --continue
~~~

Mỗi thao tác có quy trình tiếp tục riêng. Dùng lệnh tương ứng với trạng thái Git đang báo, không dùng git commit thay thế một cách máy móc.

## 7. Chọn ours hoặc theirs bằng lệnh Git

### 7.1. Lấy một phía làm nội dung working tree

Nếu sau khi kiểm tra bạn quyết định dùng toàn bộ phiên bản ours:

~~~bash
git restore --ours -- config/app.properties
git add -- config/app.properties
~~~

Nếu chọn theirs:

~~~bash
git restore --theirs -- config/app.properties
git add -- config/app.properties
~~~

git restore --ours lấy nội dung từ stage 2; git restore --theirs lấy nội dung từ stage 3. Sau đó phải stage lại để thay các entry unmerged bằng entry stage 0.

Các lệnh này chỉ phù hợp khi stage tương ứng tồn tại. Với conflict delete/modify, phía muốn chọn có thể không có nội dung để restore; khi muốn giữ quyết định xóa, dùng git rm.

### 7.2. Cẩn thận với ý nghĩa ours/theirs khi rebase

Trong merge thông thường:

- Ours thường là nhánh hiện tại đang nhận merge.
- Theirs thường là nhánh được merge vào.

Trong rebase, Git đặt lại commit của bạn trên một nền mới. Khi đó, ours thường là nhánh nền mà bạn đang rebase lên, còn theirs là commit đang được phát lại. Điều này có thể ngược với cách người dùng mô tả “nhánh của tôi” và “nhánh của họ”.

Trước khi dùng --ours hoặc --theirs trong rebase, hãy đọc trạng thái thao tác, commit đang được replay và nội dung từng stage. Không chọn chỉ dựa vào tên nhánh hoặc cảm giác rằng ours luôn là phần của mình.

### 7.3. Chọn một phía không phải lúc nào cũng là giải pháp tốt

Nếu cả hai nhánh đều có thay đổi cần thiết, chọn toàn bộ ours hoặc theirs sẽ làm mất logic ở phía còn lại. Khi đó, đọc từng phiên bản và chỉnh kết quả cuối cùng bằng tay thường phù hợp hơn.

Sau khi chọn một phía, vẫn phải:

~~~bash
git diff
git add -- config/app.properties
git diff --cached
~~~

Để xác nhận nội dung được đưa vào index đúng như dự định.

## 8. Index được chuyển thành tree và commit như thế nào?

### 8.1. Từ index sang tree object

Khi index không còn entry unmerged, Git có thể tạo tree object đại diện cho snapshot dự kiến:

~~~bash
git write-tree
~~~

Lệnh ghi tree object dựa trên các entry hợp lệ trong index và in ra OID của tree mới. Đây là plumbing command hữu ích để hiểu mối quan hệ giữa index và tree.

Nếu index còn stage 1, 2 hoặc 3 chưa giải quyết, Git không thể tạo một tree thông thường từ trạng thái đó và git write-tree sẽ báo lỗi.

### 8.2. Tree object và commit object

Một tree object ghi tên mục, mode, loại object và OID của các tệp hoặc thư mục con. Commit object tham chiếu đến một tree cùng thông tin parent, tác giả, committer và thông điệp.

Mô hình khái quát:

~~~text
Working tree
    |
    | git add
    v
Index (stage 0 entries)
    |
    | git write-tree
    v
Tree object
    |
    | git commit
    v
Commit object
~~~

Khi commit, Git tạo tree từ index rồi tạo commit tham chiếu tree đó. Vì vậy, nội dung trong working tree chưa stage không tự xuất hiện trong commit.

### 8.3. Vì sao không thể commit khi còn unmerged entries?

Một commit cần tham chiếu đến một cây thư mục nhất quán. Các stage 1, 2 và 3 là những phiên bản trung gian để người dùng giải quyết, không phải ba tệp cần cùng đưa vào cây cuối cùng.

Nếu còn đường dẫn unmerged, Git thường từ chối commit và yêu cầu giải quyết trước. Kiểm tra:

~~~bash
git ls-files -u
git status
~~~

Chỉ khi tất cả conflict đã được giải quyết và index có trạng thái hợp lệ, Git mới tạo được snapshot commit thông thường.

## 9. Trạng thái conflict và mã trong git status

Khi có conflict, git status có thể hiển thị các mã như:

| Mã | Tình huống thường gặp |
| --- | --- |
| DD | Cả hai phía đều xóa đường dẫn |
| AU | Được thêm bởi ours, chưa được giải quyết |
| UD | Ours sửa, theirs xóa |
| UA | Được thêm bởi theirs, chưa được giải quyết |
| DU | Ours xóa, theirs sửa |
| AA | Cả hai phía cùng thêm |
| UU | Cả hai phía cùng sửa |

Mã chính xác phụ thuộc loại conflict và cách Git trình bày trạng thái. Hãy dùng git ls-files -u để xem các stage thực tế thay vì chỉ dựa vào hai ký tự.

Có thể xem dạng ngắn:

~~~bash
git status --short
~~~

Với các đường dẫn chưa hợp nhất, git status thường đánh dấu chúng bằng các mã unmerged. Sau khi stage kết quả giải quyết, trạng thái chuyển sang staged hoặc biến mất khỏi danh sách nếu tệp đã được xóa.

## 10. Các tình huống thực tế

### 10.1. Cùng sửa một tệp cấu hình

Hai nhánh cùng sửa config/app.properties. Khi merge, kiểm tra:

~~~bash
git ls-files -u -- config/app.properties
git show :1:config/app.properties
git show :2:config/app.properties
git show :3:config/app.properties
~~~

Chọn giá trị cuối cùng, chỉnh working tree, stage và xác nhận:

~~~bash
git add -- config/app.properties
git ls-files --stage -- config/app.properties
git diff --cached -- config/app.properties
~~~

### 10.2. Cả hai nhánh thêm cùng một tệp

Với add/add, stage 1 có thể không tồn tại:

~~~bash
git ls-files -u -- config/new-feature.yml
~~~

Xem stage 2 và 3, kết hợp nội dung phù hợp rồi ghi kết quả:

~~~bash
git show :2:config/new-feature.yml
git show :3:config/new-feature.yml
git add -- config/new-feature.yml
~~~

### 10.3. Một nhánh xóa, nhánh kia sửa

Kiểm tra stage nào tồn tại:

~~~bash
git ls-files -u -- docs/old-guide.md
~~~

Nếu quyết định giữ phiên bản đã sửa, bảo đảm working tree có nội dung đúng rồi stage bằng git add. Nếu quyết định xóa:

~~~bash
git rm -- docs/old-guide.md
~~~

Sau đó kiểm tra không còn entry unmerged.

### 10.4. Hủy merge thay vì giải quyết

Nếu chưa muốn tiếp tục merge đang diễn ra:

~~~bash
git merge --abort
~~~

Lệnh này yêu cầu Git quay lại trạng thái trước khi bắt đầu merge trong phạm vi Git có thể khôi phục. Các thay đổi local đã tồn tại trước merge có thể khiến việc khôi phục phức tạp; nên commit hoặc stash công việc trước khi bắt đầu tích hợp.

Sau khi abort:

~~~bash
git status
git ls-files -u
~~~

Nếu không còn merge conflict, danh sách unmerged sẽ trống.

## 11. Những sai lầm thường gặp

- **Nhầm stage 0 với unstaged:** stage 0 là entry bình thường trong index, tức nội dung đã được stage; số stage không phải trạng thái staged/unstaged.
- **Cho rằng mỗi đường dẫn luôn có một entry:** khi conflict, cùng một path có thể có các entry ở stage 1, 2 và 3.
- **Cho rằng stage 1 luôn tồn tại:** add/add hoặc trường hợp không có merge base phù hợp có thể thiếu stage 1.
- **Nghĩ conflict marker là nội dung index:** marker thường nằm trong working tree; index giữ các phiên bản riêng theo stage.
- **Chạy git add -A khi chưa rà soát:** có thể stage cả thay đổi không liên quan. Stage đúng đường dẫn đã giải quyết.
- **Chọn ours/theirs mà không đọc nội dung:** có thể bỏ mất logic cần thiết từ phía còn lại.
- **Áp dụng cách hiểu ours/theirs của merge vào rebase:** trong rebase, góc nhìn thường đảo so với cách gọi “nhánh của tôi”.
- **Tự sửa file .git/index:** có thể làm hỏng trạng thái repository. Dùng lệnh Git để cập nhật index.
- **Commit khi còn unmerged entries:** Git cần một cây hợp lệ, vì vậy phải giải quyết tất cả conflict trước.
- **Chỉ nhìn git status mà không kiểm tra stage:** status cho biết có conflict, còn git ls-files -u cho biết các phiên bản cụ thể.

## 12. Bảng tra cứu nhanh

| Mục tiêu | Lệnh |
| --- | --- |
| Xem đường dẫn file index | git rev-parse --git-path index |
| Xem tất cả index entries và stage | git ls-files --stage |
| Xem entry unmerged | git ls-files -u |
| Xem entry theo thư mục | git ls-files --stage -- src/ |
| Xem phiên bản base | git show :1:path/to/file |
| Xem phiên bản ours | git show :2:path/to/file |
| Xem phiên bản theirs | git show :3:path/to/file |
| Xem diff conflict kết hợp | git diff --cc |
| Lấy nội dung ours vào working tree | git restore --ours -- path/to/file |
| Lấy nội dung theirs vào working tree | git restore --theirs -- path/to/file |
| Stage kết quả đã giải quyết | git add -- path/to/file |
| Đánh dấu xóa đã giải quyết | git rm -- path/to/file |
| Kiểm tra index sau resolve | git ls-files --stage -- path/to/file |
| Tạo tree từ index | git write-tree |
| Xem cây commit hiện tại | git ls-tree -r HEAD |
| Hủy merge đang diễn ra | git merge --abort |

## 13. Tổng kết

Index là snapshot Git chuẩn bị dùng cho commit tiếp theo. Trong trạng thái bình thường, mỗi đường dẫn được theo dõi có entry ở stage 0. Khi conflict, Git có thể giữ các phiên bản base, ours và theirs ở stage 1, 2 và 3 để người dùng so sánh và quyết định nội dung cuối cùng.

Dùng git ls-files --stage và git ls-files -u để xem cấu trúc index; dùng git show :1:path, :2:path, :3:path để đọc từng phiên bản. Sau khi chỉnh kết quả, git add hoặc git rm đưa đường dẫn về trạng thái đã giải quyết. Khi không còn unmerged entries, Git có thể tạo tree object từ index và tiếp tục commit hoặc hoàn tất merge/rebase.

Nắm được mối quan hệ giữa working tree, index, tree và commit giúp bạn hiểu vì sao Git giữ nhiều stage khi conflict và cách chuyển chúng thành một snapshot nhất quán mà không làm mất thay đổi quan trọng.

