# Tạo tree và commit bằng các lệnh plumbing để hiểu cơ chế

Những lệnh Git quen thuộc như <code>git add</code>, <code>git commit</code> và <code>git status</code> thuộc nhóm porcelain: chúng cung cấp giao diện thuận tiện cho công việc hằng ngày. Bên dưới lớp giao diện đó, Git có các lệnh plumbing để thao tác trực tiếp với object database, index và references. Khi hiểu các lệnh này, bạn sẽ thấy một commit không phải là một gói thay đổi mơ hồ: nó là một object trỏ đến tree, tree trỏ đến blob hoặc tree con, còn branch là một reference trỏ đến commit.

Bài này hướng dẫn tạo một snapshot và commit bằng các lệnh plumbing như <code>git hash-object</code>, <code>git update-index</code>, <code>git write-tree</code>, <code>git commit-tree</code> và <code>git update-ref</code>. Sau đó, bạn sẽ dùng <code>git mktree</code> để dựng tree trực tiếp, kiểm tra object bằng <code>git cat-file</code> và đối chiếu quy trình này với <code>git add</code> cùng <code>git commit</code>.

Bài thuộc chương **Cấu trúc bên trong** của module **SOURCE_CONTROL_GIT**. Module hướng dẫn Git từ working tree, staging area, commit và lịch sử đến branch, merge, rebase, remote và tag; đồng thời rèn cách cộng tác qua nhánh, giải quyết xung đột, truy tìm thay đổi và khôi phục thao tác sai mà vẫn bảo toàn lịch sử quan trọng. Nắm được plumbing giúp bạn hiểu nền tảng của staging, snapshot, commit và ref, từ đó chẩn đoán repository và tự động hóa thao tác Git chính xác hơn.

## 1. Porcelain và plumbing khác nhau thế nào?

Git chia nhiều lệnh thành hai nhóm theo mục đích:

| Nhóm | Vai trò | Ví dụ |
|---|---|---|
| Porcelain | Giao diện cấp cao cho người dùng, gom nhiều bước thành một thao tác dễ dùng | <code>git add</code>, <code>git commit</code>, <code>git switch</code>, <code>git merge</code> |
| Plumbing | Lệnh cấp thấp để thao tác với object, index, refs và dữ liệu nội bộ | <code>git hash-object</code>, <code>git update-index</code>, <code>git write-tree</code>, <code>git commit-tree</code>, <code>git update-ref</code> |

Ví dụ, khi chạy <code>git commit</code>, Git phối hợp trạng thái index để tạo tree, tạo commit object chứa tree và parent, rồi cập nhật branch ref. Với plumbing, bạn gọi từng bước một và tự chịu trách nhiệm ghép chúng theo đúng thứ tự.

Plumbing hữu ích khi:

- Muốn hiểu chính xác Git lưu snapshot và commit ra sao.
- Viết script hoặc công cụ quản lý repository ở mức thấp.
- Phân tích object database, index và references.
- Tạo tree hoặc commit trong một quy trình tự động đặc biệt.
- Điều tra trạng thái repository khi porcelain không cho thấy đủ chi tiết.

Trong công việc hằng ngày, porcelain thường an toàn và thuận tiện hơn. Plumbing không tự kiểm tra mọi ý định nghiệp vụ thay bạn; một lệnh cập nhật ref sai có thể làm branch trỏ đến commit không mong muốn.

## 2. Mô hình dữ liệu cần nhớ

Một commit Git thường liên kết đến các object theo cấu trúc:

~~~text
                  refs/heads/main
                         |
                         v
                      Commit
                    /        \
                 tree        parent
                  |
             +----+------+
             |           |
          blob        subtree
             |           |
          file data    ...
~~~

Các thành phần:

- **Blob:** lưu nội dung của một file. Blob không tự lưu tên file hoặc đường dẫn.
- **Tree:** lưu các entry gồm mode, tên và object ID; entry có thể trỏ đến blob hoặc tree con.
- **Commit:** lưu tree gốc của snapshot, parent commit, thông tin author/committer, thời gian và message.
- **Reference:** tên dễ đọc như <code>refs/heads/main</code> trỏ đến object ID, thường là commit.
- **Index:** staging area riêng của working tree, chứa các entry sẽ được dùng để tạo tree tiếp theo.

Branch không phải bản sao thư mục và cũng không chứa toàn bộ commit. Một branch local thường là một ref trỏ đến commit mới nhất của nhánh. Khi commit mới được tạo, Git cập nhật ref để trỏ sang commit mới.

## 3. Chuẩn bị repository thử nghiệm

Hãy thực hành trong một repository mới, không dùng repository đang chứa công việc thật. Ví dụ dưới đây dùng Bash:

~~~bash
mkdir plumbing-lab
cd plumbing-lab
git init -b main

git config user.name "Git Plumbing Learner"
git config user.email "learner@example.test"
~~~

Nếu phiên bản Git chưa hỗ trợ tùy chọn <code>git init -b</code>, có thể chạy <code>git init</code> rồi đặt symbolic HEAD:

~~~bash
git symbolic-ref HEAD refs/heads/main
~~~

Kiểm tra repository:

~~~bash
git status
git symbolic-ref HEAD
git rev-parse --show-object-format
~~~

Lệnh cuối cho biết định dạng hash của repository, chẳng hạn <code>sha1</code> hoặc <code>sha256</code>. Đừng giả định mọi object ID đều có độ dài cố định 40 ký tự; độ dài phụ thuộc object format.

## 4. Bước 1: tạo blob bằng git hash-object

Tạo một file:

~~~bash
printf 'Hello from Git plumbing\n' > hello.txt
~~~

Dùng <code>git hash-object</code> để tính object ID:

~~~bash
git hash-object hello.txt
~~~

Lệnh trên tính và in object ID nhưng không ghi object vào object database. Muốn lưu blob vào repository, thêm tùy chọn <code>-w</code>:

~~~bash
blob=$(git hash-object -w hello.txt)
printf '%s\n' "$blob"
~~~

Kiểm tra object vừa tạo:

~~~bash
git cat-file -t "$blob"
git cat-file -s "$blob"
git cat-file -p "$blob"
~~~

Kết quả lần lượt cho biết:

- <code>-t</code>: loại object, ở đây là <code>blob</code>.
- <code>-s</code>: kích thước nội dung blob theo byte.
- <code>-p</code>: in nội dung object.

Blob chỉ lưu bytes của nội dung. Tên <code>hello.txt</code> chưa được gắn vào blob. Tên và đường dẫn sẽ được ghi trong tree object ở bước sau.

### Git tạo object ID từ gì?

Git không hash trực tiếp riêng phần nội dung. Object được định danh từ header gồm loại object và kích thước, dấu NUL, rồi đến payload:

~~~text
blob <size><NUL><file bytes>
~~~

Do đó, cùng bytes được lưu dưới dạng blob sẽ cho cùng object ID trong cùng một object format. Nếu nội dung thay đổi, object ID cũng thay đổi với xác suất va chạm cực thấp theo thuật toán hash của repository.

### Lưu ý về attributes và clean filter

Ví dụ trên dùng file đơn giản, không có filter đặc biệt. Trong repository thực tế, <code>.gitattributes</code> có thể khai báo clean filter hoặc quy tắc chuyển đổi nội dung trước khi Git lưu blob. Nếu muốn <code>hash-object</code> xử lý file như khi nó nằm ở một đường dẫn cụ thể, có thể dùng tùy chọn <code>--path</code>:

~~~bash
git hash-object -w --path=hello.txt hello.txt
~~~

Điều này quan trọng khi tự xây dựng object bằng plumbing: nếu bỏ qua clean filter mà porcelain <code>git add</code> sẽ áp dụng, object bạn tạo có thể khác nội dung mà quy trình thông thường mong đợi.

## 5. Bước 2: thêm blob vào index bằng git update-index

Blob đã được lưu, nhưng index vẫn chưa có entry cho file. Dùng:

~~~bash
git update-index --add --cacheinfo "100644,$blob,hello.txt"
~~~

Giải thích:

- <code>--add</code> cho phép thêm entry mới vào index.
- <code>--cacheinfo</code> cung cấp trực tiếp mode, object ID và đường dẫn.
- <code>100644</code> là mode thông dụng cho file thường không có quyền executable.
- <code>$blob</code> là object ID của blob vừa tạo.
- <code>hello.txt</code> là tên đường dẫn được lưu trong index.

Xem index:

~~~bash
git ls-files --stage
~~~

Kết quả có dạng:

~~~text
100644 <object-id> 0	hello.txt
~~~

Mỗi entry hiển thị mode, object ID, stage và đường dẫn. Stage <code>0</code> là entry bình thường đã được giải quyết. Khi có conflict, index có thể chứa các stage 1, 2 và 3 đại diện cho base, ours và theirs; khi đó không thể ghi một tree bình thường cho đến khi conflict được giải quyết.

### Một số mode phổ biến

| Mode | Ý nghĩa |
|---|---|
| <code>100644</code> | File thường, không executable |
| <code>100755</code> | File thường, executable |
| <code>120000</code> | Symbolic link; blob lưu nội dung đường dẫn đích |
| <code>040000</code> | Tree entry trong cấu trúc tree |
| <code>160000</code> | Gitlink trỏ đến commit của submodule |

Mode phản ánh cách Git lưu entry, không phải toàn bộ metadata quyền truy cập của hệ điều hành.

## 6. Bước 3: tạo tree từ index bằng git write-tree

Khi index đã chứa các entry cần commit, chạy:

~~~bash
tree=$(git write-tree)
printf '%s\n' "$tree"
~~~

<code>git write-tree</code> đọc index và tạo tree object đại diện cho snapshot được stage. Nó in object ID của tree gốc. Nếu index có các đường dẫn trong thư mục con, Git sẽ tạo các tree con cần thiết rồi liên kết chúng vào tree gốc.

Kiểm tra:

~~~bash
git cat-file -t "$tree"
git cat-file -p "$tree"
~~~

Bạn sẽ thấy entry chứa mode, loại object, object ID và tên:

~~~text
100644 blob <blob-object-id>	hello.txt
~~~

Tree lưu tên và quan hệ thư mục. Blob lưu nội dung. Sự tách biệt này cho phép Git tái sử dụng blob giống nhau ở nhiều vị trí hoặc snapshot mà không cần lưu lại nội dung trùng lặp.

### Điều kiện để write-tree thành công

Index cần có trạng thái hợp lệ để tạo snapshot. Nếu còn unmerged entries do merge hoặc rebase conflict, <code>git write-tree</code> sẽ thất bại. Hãy giải quyết conflict và đưa entry về stage 0 trước.

<code>git write-tree</code> không tạo commit và cũng không di chuyển branch. Nó chỉ tạo tree object từ index hiện tại.

## 7. Bước 4: tạo commit object bằng git commit-tree

Khi đã có tree, có thể tạo commit:

~~~bash
commit=$(git commit-tree "$tree" -m "Add hello file")
printf '%s\n' "$commit"
~~~

Vì đây là commit đầu tiên, không truyền parent. Git tạo một commit gốc (root commit).

Kiểm tra:

~~~bash
git cat-file -t "$commit"
git cat-file -p "$commit"
~~~

Một commit object có cấu trúc khái quát:

~~~text
tree <tree-object-id>
author Git Plumbing Learner <learner@example.test> <timestamp> <timezone>
committer Git Plumbing Learner <learner@example.test> <timestamp> <timezone>

Add hello file
~~~

Thông tin cụ thể gồm:

- <code>tree</code>: tree gốc của snapshot.
- <code>parent</code>: commit cha; root commit không có dòng này.
- <code>author</code>: người tạo thay đổi được ghi nhận.
- <code>committer</code>: người tạo commit object.
- Phần sau dòng trống: commit message.

Git lấy thông tin author và committer từ cấu hình hoặc biến môi trường. Nếu thiếu thông tin cần thiết, lệnh có thể thất bại. Trong repository thử nghiệm, ta đã cấu hình tên và email ở bước chuẩn bị.

### Commit object chưa phải là branch mới

Đây là điểm quan trọng: <code>git commit-tree</code> tạo object commit và in object ID, nhưng không tự cập nhật branch hiện tại. Commit đã tồn tại trong object database, nhưng chưa chắc có ref dễ tìm trỏ đến nó.

Trong khoảng thời gian chưa có ref giữ commit, bạn vẫn có thể truy cập nó bằng object ID vừa nhận. Tuy nhiên, object không được ref hoặc reflog bảo vệ có thể trở thành unreachable và được Git dọn trong một lần garbage collection sau thời hạn phù hợp. Vì vậy, nếu muốn giữ commit, hãy cập nhật một ref có chủ đích sau khi xác minh object ID.

## 8. Bước 5: cập nhật branch bằng git update-ref

Repository được khởi tạo với HEAD trỏ tượng trưng đến <code>refs/heads/main</code>. Sau khi tạo commit, cập nhật branch:

~~~bash
git update-ref refs/heads/main "$commit"
~~~

Kiểm tra:

~~~bash
git symbolic-ref HEAD
git rev-parse main
git log --oneline --decorate -1
git status
~~~

HEAD vẫn trỏ đến branch <code>main</code>; branch giờ trỏ đến commit vừa tạo. Vì file trên working tree và index trùng với snapshot đã commit, trạng thái thông thường sẽ sạch.

### Cập nhật ref có kiểm tra giá trị cũ

Khi cập nhật một branch đang tồn tại, có thể truyền object ID cũ để Git chỉ thay ref nếu giá trị hiện tại vẫn đúng như mong đợi:

~~~bash
git update-ref refs/heads/main "$new_commit" "$old_commit"
~~~

Đây là thao tác so sánh rồi cập nhật (compare-and-swap). Nếu branch đã bị tiến trình khác cập nhật từ <code>$old_commit</code>, lệnh thất bại thay vì ghi đè thay đổi mới. Cách này hữu ích trong script hoặc công cụ tự động làm việc với refs.

## 9. Tạo commit thứ hai và liên kết parent

Một commit mới thường có parent trỏ đến commit trước đó. Sửa file:

~~~bash
printf 'Hello from Git plumbing\nSecond line\n' > hello.txt
~~~

Tạo blob mới và cập nhật index:

~~~bash
blob2=$(git hash-object -w hello.txt)
git update-index --cacheinfo "100644,$blob2,hello.txt"
~~~

Tạo tree và commit mới với parent là commit đầu:

~~~bash
tree2=$(git write-tree)
commit2=$(git commit-tree "$tree2" -p "$commit" -m "Update hello file")
~~~

Cập nhật branch. Truyền commit cũ ở đối số cuối để bảo vệ khỏi việc ref đã thay đổi ngoài dự kiến:

~~~bash
git update-ref refs/heads/main "$commit2" "$commit"
~~~

Kiểm tra lịch sử:

~~~bash
git log --oneline --decorate --graph
git cat-file -p "$commit2"
~~~

Commit mới chứa tree mới và parent trỏ đến commit trước. Tree mới tham chiếu đến blob mới. Commit cũ và blob cũ vẫn được giữ để lịch sử có thể khôi phục nội dung trước đó.

## 10. Tạo tree trực tiếp bằng git mktree

<code>git write-tree</code> tạo tree từ index. Nếu muốn dựng tree trực tiếp từ danh sách entry, có thể dùng <code>git mktree</code>.

Định dạng input cơ bản của <code>git mktree</code> là:

~~~text
<mode> SP <type> SP <object-id> TAB <name>
~~~

Ví dụ tạo tree có một file:

~~~bash
printf '100644 blob %s\thello.txt\n' "$blob" | git mktree
~~~

Lệnh in object ID của tree vừa tạo. Có thể kiểm tra bằng:

~~~bash
manual_tree=$(printf '100644 blob %s\thello.txt\n' "$blob" | git mktree)
git cat-file -p "$manual_tree"
~~~

Tree này có thể giống tree được tạo bởi <code>git write-tree</code> nếu danh sách entry và nội dung object giống hệt. Vì tree được định danh theo nội dung, cùng cấu trúc tree sẽ cho cùng object ID trong cùng object format.

### Dựng tree có thư mục con

Để tạo cấu trúc:

~~~text
root
└── src
    └── app.txt
~~~

Trước hết tạo blob:

~~~bash
printf 'print("hello")\n' > app.txt
app_blob=$(git hash-object -w app.txt)
~~~

Tạo tree con tên <code>src</code>:

~~~bash
src_tree=$(printf '100644 blob %s\tapp.txt\n' "$app_blob" | git mktree)
~~~

Rồi tạo tree gốc tham chiếu đến tree con:

~~~bash
root_tree=$(printf '040000 tree %s\tsrc\n' "$src_tree" | git mktree)
git cat-file -p "$root_tree"
~~~

Đầu ra cho thấy entry <code>src</code> có type <code>tree</code>, không phải blob. Khi cần tạo nhiều cấp, hãy tạo tree từ dưới lên: blob trước, tree con tiếp theo, rồi tree cha.

<code>git mktree</code> phù hợp để hiểu định dạng tree hoặc tạo snapshot từ dữ liệu đã chuẩn bị. Trong script thông thường, cập nhật index rồi dùng <code>git write-tree</code> thường dễ bảo trì hơn.

## 11. Nhiều parent: tạo merge commit bằng plumbing

Commit có thể có nhiều parent. Một commit merge thông thường có hai parent: commit của nhánh hiện tại và commit của nhánh được merge.

Giả sử repository thử nghiệm đã có hai branch tên <code>main</code> và <code>feature</code>:

~~~bash
ours=$(git rev-parse main)
theirs=$(git rev-parse feature)
~~~

Sau khi tự chuẩn bị index chứa tree kết quả đã merge và tạo tree:

~~~bash
merge_tree=$(git write-tree)
merge_commit=$(git commit-tree "$merge_tree" -p "$ours" -p "$theirs" -m "Merge feature")
~~~

Commit object có hai dòng parent theo thứ tự truyền vào:

~~~text
tree <merge-tree-id>
parent <ours-commit-id>
parent <theirs-commit-id>
...
~~~

Sau đó, cập nhật branch đích với điều kiện branch vẫn trỏ đến commit ours:

~~~bash
git update-ref refs/heads/main "$merge_commit" "$ours"
~~~

Ví dụ này chỉ minh họa cấu trúc commit merge. Để tạo kết quả merge đúng, index phải chứa nội dung đã kết hợp và đã giải quyết mọi conflict. <code>commit-tree</code> không tự chạy thuật toán merge, không tự chọn phiên bản file và không tự giải quyết xung đột.

## 12. Đối chiếu plumbing với git add và git commit

Quy trình plumbing vừa thực hiện tương ứng gần đúng với các bước porcelain:

| Thao tác plumbing | Vai trò tương ứng trong quy trình thông thường |
|---|---|
| <code>git hash-object -w</code> | Tạo và lưu blob cho nội dung file |
| <code>git update-index</code> | Đưa phiên bản file vào staging area |
| <code>git write-tree</code> | Tạo tree từ snapshot trong index |
| <code>git commit-tree</code> | Tạo commit object từ tree và parent |
| <code>git update-ref</code> | Di chuyển branch ref đến commit mới |

Trong công việc hằng ngày, bạn thường chỉ cần:

~~~bash
git add hello.txt
git commit -m "Update hello file"
~~~

Porcelain còn xử lý nhiều chi tiết khác như thông điệp mặc định, hook, signing, cleanup, reflog và kiểm tra trạng thái. Chuỗi plumbing trong bài là mô hình học tập để thấy các object và ref được tạo ra; nó không phải bản thay thế hoàn chỉnh cho mọi hành vi của <code>git commit</code>.

## 13. Quan sát object và ref sau khi tạo commit

Các lệnh sau giúp lần theo cấu trúc:

~~~bash
# Xem commit hiện tại
git cat-file -p HEAD

# Xem tree mà commit trỏ tới
git cat-file -p HEAD^{tree}

# Liệt kê file và tree con trong snapshot
git ls-tree HEAD
git ls-tree -r HEAD

# Xem index hiện tại
git ls-files --stage

# Xem HEAD là symbolic ref hay detached OID
git symbolic-ref -q HEAD
git rev-parse HEAD

# Xem branch ref trỏ đến đâu
git show-ref --heads
~~~

Phân biệt hai cách kiểm tra:

- <code>git cat-file -p HEAD</code> hiển thị nội dung commit object.
- <code>git cat-file -p HEAD^{tree}</code> hiển thị nội dung tree gốc của commit.

Nếu <code>HEAD</code> đang detached, <code>git symbolic-ref -q HEAD</code> có thể trả về mã lỗi vì HEAD chứa trực tiếp object ID thay vì trỏ tượng trưng đến branch.

## 14. Những lỗi dễ gặp khi dùng plumbing

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| <code>git write-tree</code> thất bại | Index còn conflict stages hoặc không hợp lệ | Kiểm tra <code>git ls-files --stage</code>, giải quyết conflict |
| Tree không chứa file mong muốn | Blob chưa được thêm vào index hoặc sai path | Kiểm tra <code>git ls-files --stage</code> trước khi write-tree |
| Commit được tạo nhưng không thấy trong branch | <code>commit-tree</code> không cập nhật ref | Dùng <code>git update-ref</code> sau khi xác minh commit |
| Branch trỏ sai commit | Đã cập nhật nhầm ref hoặc dùng sai object ID | Kiểm tra <code>git show-ref</code> và <code>git cat-file -p</code> trước khi sửa |
| <code>hash-object</code> cho ID nhưng không tìm thấy object | Thiếu tùy chọn <code>-w</code> nên chỉ tính hash | Dùng <code>git hash-object -w</code> để lưu object |
| Nội dung blob khác với file sau khi dùng porcelain | Clean filter hoặc attributes chưa được áp dụng | Kiểm tra attributes và dùng <code>hash-object --path</code> khi phù hợp |
| Commit không có parent | Không truyền tùy chọn <code>-p</code> | Root commit không có parent; commit tiếp theo phải chỉ rõ parent |
| Commit object có nhưng HEAD không đổi | Tạo object không đồng nghĩa cập nhật HEAD/ref | Cập nhật đúng branch ref bằng <code>update-ref</code> |

## 15. Quy trình thực hành tổng hợp

Trong repository thử nghiệm, hãy thực hiện lại từ đầu mà không dùng <code>git add</code> hoặc <code>git commit</code>:

1. Khởi tạo repository và cấu hình author/committer.
2. Tạo file văn bản.
3. Dùng <code>git hash-object -w</code> để tạo blob.
4. Dùng <code>git update-index --add --cacheinfo</code> để thêm entry vào index.
5. Dùng <code>git ls-files --stage</code> để xác nhận stage 0.
6. Dùng <code>git write-tree</code> để tạo tree.
7. Dùng <code>git cat-file -p</code> để xem tree.
8. Dùng <code>git commit-tree</code> để tạo commit.
9. Dùng <code>git update-ref</code> để cập nhật branch.
10. Tạo thay đổi mới, lặp lại quy trình và truyền parent commit.
11. Dùng <code>git log</code>, <code>git cat-file</code>, <code>git ls-tree</code> và <code>git show-ref</code> để kiểm tra lịch sử.
12. Tạo một tree tương đương bằng <code>git mktree</code> và so sánh object ID.

Sau khi hoàn thành, chạy quy trình porcelain trên một repository thử nghiệm thứ hai và so sánh object graph. Bạn sẽ nhận ra Git vẫn tạo blob, tree, commit và cập nhật refs theo cùng mô hình; porcelain chỉ tự động hóa các bước và thêm các kiểm tra cần thiết cho người dùng.

## 16. Bài tập tự kiểm tra

1. Giải thích vì sao blob không lưu tên file nhưng tree có tên file.
2. Tạo hai file có cùng nội dung bằng <code>git hash-object -w</code>. Kiểm tra chúng có cùng blob object ID hay không.
3. Sửa một file rồi tạo blob mới. So sánh object ID và kích thước.
4. Thêm hai file vào index bằng <code>update-index</code> và tạo tree. Quan sát tree chứa hai entry.
5. Tạo thư mục con bằng <code>git mktree</code> rồi liên kết nó từ tree gốc.
6. Tạo root commit bằng <code>commit-tree</code>, xác nhận chưa có branch ref trỏ đến nó, rồi dùng <code>update-ref</code>.
7. Tạo commit thứ hai với tùy chọn <code>-p</code> và quan sát dòng parent.
8. Tạo commit hai parent bằng <code>commit-tree</code> trong repository thử nghiệm có hai nhánh.
9. Giải thích vì sao <code>write-tree</code> thất bại khi index còn unmerged entries.
10. Mô tả các bước porcelain <code>git add</code> và <code>git commit</code> tự động hóa từ chuỗi plumbing.

Khi có thể tạo blob, index entry, tree, commit và cập nhật ref một cách độc lập, bạn đã hiểu được đường đi từ nội dung file đến lịch sử Git. Hãy dùng plumbing để học và xây công cụ có chủ đích; với công việc thông thường, ưu tiên porcelain vì nó gom các bước, kiểm tra trạng thái và bảo vệ quy trình commit tốt hơn.
