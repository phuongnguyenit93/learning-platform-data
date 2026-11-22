# Kiểm tra chỉ mục bằng git ls-files và các trạng thái hợp nhất

Git không chỉ theo dõi những file đang nhìn thấy trong working tree. Git còn duy trì một chỉ mục (index) ghi nhận phiên bản nội dung và metadata của các đường dẫn sẽ được đưa vào commit tiếp theo. Khi cần biết chính xác index đang chứa những gì, lệnh **git ls-files** là công cụ quan trọng. Lệnh này có thể liệt kê đường dẫn được theo dõi, hiển thị object ID và stage của từng mục, tìm file đã sửa hoặc bị xóa, và đặc biệt giúp kiểm tra các mục đang ở trạng thái xung đột khi merge hoặc rebase.

Trong một thao tác merge có xung đột, một đường dẫn có thể có nhiều entry trong index thay vì một entry bình thường. Các entry này được đánh số stage 1, 2 và 3 để lưu phiên bản cơ sở cùng hai phía đang được hợp nhất. Hiểu cách đọc những stage này giúp bạn xác định Git đang giữ những phiên bản nào, chọn cách giải quyết phù hợp và xác nhận xung đột đã thực sự được xử lý.

Sau bài này, bạn có thể:

- Liệt kê file tracked và các entry đang có trong index bằng git ls-files.
- Đọc mode, object ID và stage qua --stage.
- Tìm đường dẫn chưa được hợp nhất bằng --unmerged.
- Phân biệt stage 0, stage 1, stage 2 và stage 3.
- Dùng các tùy chọn để tìm file modified, deleted, untracked và ignored.
- Kết hợp git status, git diff và git ls-files để điều tra xung đột.
- Giải quyết conflict, stage kết quả và xác minh index đã trở về trạng thái bình thường.

## 1. Index lưu những gì?

Index là vùng trung gian giữa working tree và commit. Khi chạy git add, Git ghi nội dung được chọn vào index. Khi chạy git commit, Git tạo snapshot từ index tại thời điểm đó.

~~~text
Working tree                 Index                       Commit
file đang chỉnh sửa  --add--> phiên bản đã stage --commit--> snapshot
        ^                          |
        |                          |
        +------ restore ------------+
~~~

Một entry thông thường trong index chứa các thông tin như:

- Đường dẫn file tương đối với repository root.
- File mode, ví dụ file thường hoặc symbolic link.
- Object ID của nội dung được lưu trong object database.
- Stage number.
- Một số metadata về stat và cờ nội bộ.

Index không đơn giản là danh sách tên file. Nó lưu phiên bản nội dung đã stage. Vì thế, cùng một file có thể khác nhau giữa HEAD, index và working tree.

Ví dụ:

~~~bash
git add src/Search.java
git status --short
git ls-files --stage -- src/Search.java
~~~

git status cho biết file đang thay đổi ở vùng nào; git ls-files --stage cho biết entry cụ thể trong index trỏ tới object nào và đang ở stage nào.

## 2. Liệt kê các file được theo dõi

Chạy lệnh cơ bản:

~~~bash
git ls-files
~~~

Mặc định, Git liệt kê các đường dẫn có trong index, tức các file được Git theo dõi trong snapshot chuẩn hiện tại của index. Lệnh không liệt kê mọi file trong working tree và cũng không tự liệt kê file chưa được theo dõi.

Muốn xem đường dẫn đầy đủ từ root thay vì cách hiển thị rút gọn theo thư mục hiện tại:

~~~bash
git ls-files --full-name
~~~

Muốn giới hạn kết quả theo một pathspec:

~~~bash
git ls-files -- src/
git ls-files -- '*.java'
~~~

Dấu -- tách tùy chọn khỏi pathspec, giúp tên file bắt đầu bằng dấu gạch ngang không bị hiểu nhầm là option. Khi viết script, nên quote pathspec theo cú pháp shell đang dùng.

Nếu muốn lệnh báo lỗi khi pathspec không khớp với file nào trong index:

~~~bash
git ls-files --error-unmatch src/DoesNotExist.java
~~~

Điều này hữu ích trong script cần phân biệt file không tồn tại trong index với một kết quả rỗng hợp lệ.

## 3. Xem object ID, file mode và stage bằng --stage

Dùng:

~~~bash
git ls-files --stage
~~~

Hoặc dạng ngắn:

~~~bash
git ls-files -s
~~~

Output có cấu trúc:

~~~text
<mode> <object-id> <stage><TAB><path>
~~~

Ví dụ:

~~~text
100644 7a1b... 0    README.md
100644 91c2... 0    src/Search.java
100755 a83d... 0    scripts/build.sh
~~~

Các cột có ý nghĩa:

| Thành phần | Ý nghĩa |
| --- | --- |
| mode | Kiểu và quyền file được Git ghi nhận, ví dụ 100644 là file thường không executable, 100755 là file thường executable. |
| object-id | OID của blob hoặc object mà entry trỏ tới. |
| stage | Stage number của entry trong index. |
| path | Đường dẫn file trong repository. |

Trong index bình thường, entry có stage 0. Khi một đường dẫn bị conflict, Git có thể giữ nhiều entry ở stage 1, 2 và 3 cho cùng một path.

OID ở đây đại diện cho nội dung đã được stage hoặc một phiên bản đang tham gia giải quyết xung đột. Nó không nhất thiết bằng OID của file hiện tại trong working tree.

## 4. Stage 0, 1, 2 và 3 có nghĩa gì?

Index sử dụng stage number để biểu diễn trạng thái hợp nhất:

| Stage | Ý nghĩa | Vai trò |
| --- | --- | --- |
| 0 | Entry bình thường, không còn conflict cho đường dẫn đó. | Nội dung hiện đang được stage. |
| 1 | Phiên bản cơ sở (merge base). | Điểm chung trước khi hai phía thay đổi. |
| 2 | Phiên bản phía hiện tại, thường gọi là ours trong merge. | Nội dung từ HEAD/current side. |
| 3 | Phiên bản phía được đưa vào, thường gọi là theirs trong merge. | Nội dung từ phía incoming side. |

Khi có xung đột, Git giữ các phiên bản cần thiết trong index để bạn có thể so sánh và chọn cách kết hợp. Đối với một path đang unmerged, stage 0 thường chưa tồn tại; thay vào đó có một hoặc nhiều entry ở stage 1, 2, 3.

Không phải loại conflict nào cũng có đủ ba stage:

- Với xung đột sửa/sửa, thường có stage 1, 2 và 3.
- Với xung đột thêm/thêm, hai phía đều thêm file mới nên có thể chỉ có stage 2 và 3, không có base stage 1.
- Với xung đột sửa/xóa, một phía có thể không có file nên chỉ có base và entry từ phía còn lại.
- Với xung đột rename hoặc rename/delete, quan hệ giữa đường dẫn có thể phức tạp hơn; cần kiểm tra toàn bộ các path unmerged.

Stage number là metadata trong index, không phải ba file riêng được Git tạo trong working tree.

## 5. Tìm các đường dẫn đang unmerged

Khi merge hoặc rebase xảy ra conflict, dùng:

~~~bash
git ls-files --unmerged
~~~

Hoặc dạng ngắn:

~~~bash
git ls-files -u
~~~

Tùy chọn này hiển thị các entry chưa được hợp nhất và bao gồm thông tin stage. Ví dụ:

~~~text
100644 111aaa... 1    src/Search.java
100644 222bbb... 2    src/Search.java
100644 333ccc... 3    src/Search.java
~~~

Kết quả cho biết src/Search.java có ba phiên bản trong index:

- Stage 1: nội dung chung trước khi hai phía chỉnh sửa.
- Stage 2: nội dung phía hiện tại.
- Stage 3: nội dung phía incoming.

Muốn xem cả entry bình thường và entry conflict:

~~~bash
git ls-files --stage
~~~

Muốn chỉ xem một file:

~~~bash
git ls-files --unmerged -- src/Search.java
~~~

Nếu output không có dòng nào, index không còn entry unmerged được lệnh này liệt kê. Tuy nhiên, vẫn cần kiểm tra git status và kết quả merge/rebase để xác nhận toàn bộ thao tác đã hoàn tất.

## 6. Xem nội dung từng stage

Khi đã có OID từ git ls-files --unmerged, có thể đọc nội dung từng phiên bản bằng git show hoặc git cat-file.

Với một file đang conflict:

~~~bash
# Xem nội dung base
git show :1:src/Search.java

# Xem nội dung ours
git show :2:src/Search.java

# Xem nội dung theirs
git show :3:src/Search.java
~~~

Cú pháp :<stage>:<path> là cách tham chiếu một entry trong index. Nếu stage tương ứng không tồn tại, lệnh sẽ thất bại. Điều này thường gặp trong conflict thêm/thêm hoặc sửa/xóa.

Cũng có thể dùng OID lấy từ git ls-files -u:

~~~bash
git cat-file -p 111aaa...
~~~

git show :2:path tiện khi đã biết stage và path; git cat-file -p tiện khi đã có OID. Hai cách đều giúp xem nội dung object mà không cần ghi đè working tree.

### Lưu ý về ours và theirs khi rebase

Trong merge thông thường, stage 2 là phía hiện tại và stage 3 là phía được merge vào. Khi rebase, Git đang replay commit của bạn lên một base mới, nên cách gọi “ours” và “theirs” có thể ngược với trực giác: stage 2 thường là nhánh đang rebase onto, còn stage 3 là commit đang được replay. Hãy kiểm tra nội dung stage và mục tiêu lịch sử thay vì chỉ dựa vào tên gọi.

## 7. Các tùy chọn lọc file hữu ích

git ls-files có thể lọc index và working tree theo nhiều loại trạng thái:

| Tùy chọn | Ý nghĩa |
| --- | --- |
| --cached | Liệt kê file có trong index; đây là hành vi mặc định. |
| --stage | Hiển thị mode, OID và stage của từng entry. |
| --unmerged | Chỉ liệt kê entry chưa được hợp nhất; ngụ ý hiển thị stage. |
| --modified | Liệt kê file tracked có working-tree content khác index. |
| --deleted | Liệt kê file tracked đã bị xóa khỏi working tree. |
| --others | Liệt kê file không có trong index, tức untracked. |
| --ignored | Bao gồm file bị ignore; phải kết hợp với --cached hoặc --others. |
| --exclude-standard | Dùng các quy tắc ignore chuẩn như .gitignore, .git/info/exclude và global excludes. |

Ví dụ:

~~~bash
# File tracked trong index
git ls-files --cached

# File tracked đã sửa trong working tree
git ls-files --modified

# File tracked đã bị xóa khỏi working tree
git ls-files --deleted

# File chưa được theo dõi, bỏ qua file bị ignore
git ls-files --others --exclude-standard

# File untracked bị ignore theo các quy tắc chuẩn
git ls-files --others --ignored --exclude-standard
~~~

Các tùy chọn này giúp điều tra trạng thái file cụ thể. Chúng không thay thế git status, vốn tổng hợp trạng thái branch, index, working tree và upstream trong một góc nhìn dễ đọc hơn.

## 8. Phân biệt ls-files với status và diff

Ba lệnh trả lời những câu hỏi khác nhau:

| Lệnh | Câu hỏi chính |
| --- | --- |
| git status | Repository đang có thay đổi gì và branch đang ở trạng thái nào? |
| git diff / git diff --cached | Nội dung thay đổi giữa working tree, index và HEAD là gì? |
| git ls-files | Những path và entry nào đang nằm trong index, và chúng ở stage nào? |

Ví dụ khi có conflict:

~~~bash
git status --short
git diff
git diff --cached
git ls-files --unmerged
git ls-files --stage
~~~

git status giúp nhận diện path conflict. git diff có thể hiển thị nội dung xung đột hoặc khác biệt tùy trạng thái. git ls-files --unmerged cho thấy chính xác các entry stage còn trong index.

Khi cần biết một file đang bị stage ở phiên bản nào, git ls-files --stage cung cấp OID và stage. Khi cần đọc nội dung thay đổi theo cách dễ hiểu, git diff thường phù hợp hơn.

## 9. Xung đột merge được lưu trong index ra sao?

Giả sử hai branch cùng sửa src/Search.java ở một vùng không thể tự động hợp nhất. Khi merge, Git không thể tạo một nội dung stage 0 duy nhất cho file đó. Thay vào đó, index giữ các phiên bản:

~~~text
stage 1  common ancestor
stage 2  current branch
stage 3  branch being merged
~~~

Working tree thường chứa file có conflict markers như:

~~~text
<<<<<<< HEAD
return normalize(query);
=======
return sanitize(query);
>>>>>>> feature/sanitize
~~~

Các marker là cách Git biểu diễn xung đột văn bản trong working tree. Index vẫn giữ các entry stage riêng để có thể truy xuất từng phía. Với conflict nhị phân hoặc một số conflict về rename/delete, file có thể không có marker văn bản như ví dụ.

Để xem các path conflict:

~~~bash
git ls-files -u
~~~

Để xem nội dung từng phía:

~~~bash
git show :1:src/Search.java
git show :2:src/Search.java
git show :3:src/Search.java
~~~

Sau khi quyết định nội dung cuối cùng, chỉnh sửa working tree và stage kết quả. Git sẽ thay các entry unmerged bằng entry stage 0.

## 10. Giải quyết conflict bằng cách chỉnh sửa nội dung

Quy trình thường dùng:

~~~bash
# 1. Xác định các file conflict
git status
git ls-files --unmerged

# 2. Mở file và kết hợp nội dung phù hợp
#    Xóa các conflict markers sau khi giải quyết

# 3. Stage kết quả đã giải quyết
git add src/Search.java

# 4. Xác nhận file không còn unmerged entry
git ls-files --unmerged
git ls-files --stage -- src/Search.java

# 5. Xem lại nội dung sẽ commit
git diff --cached
~~~

Sau khi git add, file đã giải quyết thường xuất hiện ở stage 0:

~~~text
100644 444ddd... 0    src/Search.java
~~~

Nếu git ls-files --unmerged không còn liệt kê path đó, các stage 1/2/3 của path đã được loại khỏi index. Đây là một dấu hiệu quan trọng cho thấy Git đã ghi nhận kết quả giải quyết.

Nếu quyết định giữ việc xóa file, dùng:

~~~bash
git rm -- src/Search.java
~~~

Lệnh này stage việc xóa và loại các entry conflict tương ứng khỏi index. Chỉ dùng khi quyết định cuối cùng là file không còn tồn tại trong kết quả hợp nhất.

## 11. Chọn một phía bằng ours hoặc theirs

Nếu muốn dùng nguyên nội dung từ một phía cho một file conflict, có thể checkout phiên bản tương ứng:

~~~bash
# Chọn nội dung phía hiện tại
git checkout --ours -- src/Search.java

# Hoặc chọn nội dung phía incoming
git checkout --theirs -- src/Search.java
~~~

Các lệnh trên cập nhật working tree từ stage 2 hoặc stage 3. Chúng chưa hoàn tất việc giải quyết conflict trong index. Sau khi chọn, cần stage kết quả:

~~~bash
git add src/Search.java
git ls-files --unmerged
~~~

Có thể dùng git restore trong Git hiện đại để lấy một phía từ index cho working tree:

~~~bash
git restore --ours --worktree -- src/Search.java
git add src/Search.java
~~~

Chọn ours hoặc theirs chỉ phù hợp khi bạn hiểu nội dung phía đó và chấp nhận bỏ phần thay đổi của phía còn lại cho path đang xử lý. Đặc biệt khi rebase, hãy kiểm tra lại ý nghĩa hai phía vì góc nhìn có thể đảo so với suy nghĩ thông thường.

## 12. Theo dõi trạng thái conflict trong merge và rebase

Sau khi giải quyết tất cả path conflict, Git vẫn cần hoàn tất thao tác đang dở.

Với merge:

~~~bash
git status
git ls-files --unmerged
git diff --cached
git commit
~~~

Nếu merge được khởi tạo bằng git merge, sau khi mọi conflict được stage, tạo merge commit bằng git commit hoặc lệnh tiếp tục phù hợp với quy trình đang dùng.

Với rebase:

~~~bash
git status
git ls-files --unmerged
git diff --cached
git rebase --continue
~~~

Nếu cần hủy rebase đang dở:

~~~bash
git rebase --abort
~~~

Nếu cần hủy merge đang dở:

~~~bash
git merge --abort
~~~

Không chạy --continue khi vẫn còn path unmerged. Dùng git ls-files -u để xác nhận index không còn entry conflict trước khi tiếp tục.

## 13. Conflict thêm/thêm, sửa/xóa và rename

Không phải conflict nào cũng giống sửa/sửa:

### Thêm/thêm (add/add)

Hai phía cùng tạo một path mới nhưng nội dung khác nhau. Vì chưa có file trong merge base, index thường có stage 2 và stage 3 mà không có stage 1. Dùng:

~~~bash
git ls-files --unmerged
git show :2:docs/guide.md
git show :3:docs/guide.md
~~~

Kết hợp hai phiên bản trong working tree rồi git add.

### Sửa/xóa (modify/delete)

Một phía sửa file trong khi phía kia xóa file. Index có thể giữ base và phiên bản đã sửa từ một phía, còn phía xóa không có blob tương ứng. Quyết định giữ nội dung đã sửa hay giữ việc xóa:

~~~bash
# Nếu giữ file đã sửa
git add path/to/file

# Nếu giữ quyết định xóa
git rm -- path/to/file
~~~

### Rename conflict

Khi hai phía đổi tên hoặc đổi tên đồng thời chỉnh sửa nội dung, Git có thể báo conflict trên một hoặc nhiều path. Không chỉ xem một dòng output; kiểm tra toàn bộ:

~~~bash
git status --short
git ls-files --unmerged
git ls-files --stage
~~~

Sau khi chọn tên đích và nội dung cuối cùng, stage đúng path cần giữ. Kiểm tra lại cả path cũ và mới để tránh vô tình giữ hai bản hoặc bỏ sót file.

## 14. Resolve-undo entries

Git có thể giữ thông tin về các entry conflict trước đó trong index sau khi bạn đã giải quyết xung đột. Dùng:

~~~bash
git ls-files --resolve-undo
~~~

Thông tin resolve-undo có thể giúp tái tạo trạng thái conflict trước đó bằng các lệnh hỗ trợ như:

~~~bash
git checkout -m -- path/to/file
~~~

Đây là khả năng nâng cao và không phải mọi path đều có resolve-undo entry. Nếu lệnh không trả kết quả, có thể Git không còn lưu thông tin đó cho path cần kiểm tra.

Không nhầm resolve-undo với stage 1/2/3 đang unmerged. --unmerged hiển thị conflict còn đang tồn tại; --resolve-undo hiển thị thông tin lưu lại về conflict đã được resolve.

## 15. Dùng -z khi xử lý tên file đặc biệt

Tên file trong repository có thể chứa dấu cách, tab hoặc ký tự xuống dòng. Nếu script phân tích output theo từng dòng, tên file có thể làm sai cấu trúc dữ liệu.

Dùng:

~~~bash
git ls-files -z
git ls-files --unmerged -z
git ls-files --stage -z
~~~

Tùy chọn -z phân tách record bằng byte NUL và không quote các ký tự đặc biệt theo cách output dành cho con người. Script cần đọc dữ liệu theo NUL, không split bằng newline hoặc space.

Ví dụ, trong shell có thể truyền output sang công cụ hiểu NUL:

~~~bash
git ls-files -z | xargs -0 -r printf '%s\n'
~~~

Hành vi xargs -0 phổ biến trên GNU và một số môi trường Unix; nếu dùng Windows hoặc môi trường khác, hãy chọn công cụ có hỗ trợ NUL tương ứng.

## 16. Quy trình chẩn đoán đầy đủ khi có conflict

Khi một thao tác merge hoặc rebase dừng vì conflict, thực hiện:

~~~bash
# 1. Xem trạng thái tổng quan
git status --short --branch

# 2. Liệt kê path và stage đang unmerged
git ls-files --unmerged

# 3. Xem toàn bộ entry index cho các path liên quan
git ls-files --stage

# 4. Đọc từng phiên bản nếu cần
git show :1:path/to/file
git show :2:path/to/file
git show :3:path/to/file

# 5. Sau khi sửa và stage
git add path/to/file

# 6. Xác nhận không còn entry unmerged
git ls-files --unmerged

# 7. Xem snapshot sắp được ghi
git diff --cached
~~~

Nếu bước 6 vẫn trả kết quả, còn path conflict chưa được giải quyết. Tiếp tục xử lý từng path, bao gồm trường hợp chọn xóa bằng git rm.

Khi danh sách unmerged đã rỗng, kiểm tra git status để biết còn thay đổi nào khác chưa stage hoặc chưa được theo dõi. Một index không còn conflict không có nghĩa toàn bộ working tree sạch.

## 17. Những lỗi thường gặp

### git ls-files không hiển thị file mới

Lệnh mặc định liệt kê các path trong index, không liệt kê file untracked. Dùng git ls-files --others --exclude-standard hoặc git status để xem file chưa được theo dõi.

### git ls-files --stage chỉ hiển thị stage 0

Repository hiện không có unmerged entry cho các path được liệt kê. Nếu đang điều tra conflict, dùng git ls-files --unmerged để lọc riêng các entry stage 1/2/3.

### Nhìn thấy conflict markers nhưng git ls-files -u không có kết quả

File có thể chứa marker được nhập thủ công hoặc đã được stage như nội dung bình thường. Git dựa vào index stage để nhận diện conflict, không quét nội dung file để tìm chuỗi <<<<<<<. Kiểm tra git status và nội dung staged.

### git add xong nhưng vẫn còn conflict

Có thể bạn chỉ stage một số file trong khi các path khác vẫn unmerged. Chạy git ls-files -u để tìm toàn bộ path còn lại.

### Chọn --ours trong rebase nhưng nhận nhầm nội dung

Trong rebase, ours/theirs có thể ngược với trực giác vì HEAD đang ở nhánh đích mà commit được replay lên. Xem git show :2:path và git show :3:path trước khi chọn.

### Nghĩ stage 1 luôn tồn tại

Conflict thêm/thêm không có phiên bản base cho path đó, nên stage 1 có thể không xuất hiện. Các conflict sửa/xóa cũng có thể thiếu stage của phía đã xóa.

### Phân tích output có tên file đặc biệt bằng khoảng trắng

Tên file có thể chứa khoảng trắng hoặc newline. Dùng -z và parser NUL-safe khi viết script.

## 18. Ghi nhớ

- git ls-files mặc định liệt kê các đường dẫn trong index, không phải mọi file trong working tree.
- git ls-files --stage hiển thị mode, OID và stage của từng entry.
- Stage 0 là entry bình thường; stage 1 là base; stage 2 là current/ours; stage 3 là incoming/theirs trong merge thông thường.
- git ls-files --unmerged hoặc -u liệt kê các entry conflict còn trong index.
- Không phải mọi conflict đều có đủ stage 1, 2 và 3.
- Dùng git show :1:path, :2:path, :3:path để xem nội dung từng stage khi entry tồn tại.
- git add stage kết quả đã giải quyết; git rm stage quyết định xóa file.
- Sau khi resolve, xác nhận git ls-files -u không còn kết quả rồi mới tiếp tục merge hoặc rebase.
- git ls-files --others, --modified, --deleted, --ignored giúp lọc các nhóm file khác nhau.
- Dùng -z khi script cần xử lý an toàn tên file có ký tự đặc biệt.

git status cho bạn bức tranh tổng quan, còn git ls-files cho phép nhìn trực tiếp vào các entry của index. Khi hiểu stage 1/2/3 và biết cách kiểm tra chúng, bạn có thể xác định chính xác dữ liệu Git đang giữ trong một conflict, giải quyết từng đường dẫn và xác nhận index đã sẵn sàng cho commit hoặc bước tiếp theo của rebase.
