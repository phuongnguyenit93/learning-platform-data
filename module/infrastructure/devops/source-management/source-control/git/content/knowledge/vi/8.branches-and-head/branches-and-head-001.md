# Nhánh là con trỏ có thể di chuyển trong đồ thị commit

Trong Git, branch không phải là một bản sao thư mục, cũng không phải một tập hợp file riêng. Một branch là một reference có tên, thường trỏ đến commit mới nhất của một dòng phát triển. Khi bạn tạo commit mới trên branch đang checkout, Git tạo commit object mới rồi di chuyển reference đó đến commit mới. Các commit cũ vẫn còn trong lịch sử và được nối với commit mới bằng quan hệ parent.

Mô hình này giải thích vì sao tạo branch rất nhanh, vì sao hai branch có thể cùng trỏ đến một commit, và vì sao merge hoặc rebase làm thay đổi vị trí con trỏ branch. Bài này tập trung vào branch, đồ thị commit và vai trò của HEAD: branch cho biết một dòng phát triển đang kết thúc ở đâu, còn HEAD cho Git biết bạn đang đứng trên branch nào hoặc đang xem trực tiếp commit nào.

Bài thuộc chương **Nhánh và HEAD** của module **SOURCE_CONTROL_GIT**. Module hướng dẫn Git từ working tree, staging area, commit và lịch sử đến branch, merge, rebase, remote và tag; đồng thời rèn cách cộng tác qua nhánh, giải quyết xung đột, truy tìm thay đổi và khôi phục thao tác sai mà vẫn bảo toàn lịch sử quan trọng. Hiểu branch như một con trỏ trong đồ thị commit là nền tảng để sử dụng branch, chuyển nhánh và phối hợp lịch sử một cách an toàn.

## 1. Đồ thị commit là nền tảng của branch

Mỗi commit là một object bất biến chứa snapshot của project, thông tin author/committer, message và một hoặc nhiều parent commit. Parent cho biết commit được tạo dựa trên lịch sử nào. Các quan hệ parent tạo thành một đồ thị có hướng không chu trình (DAG).

Ví dụ một lịch sử tuyến tính:

~~~text
A --- B --- C
          main
~~~

Branch <code>main</code> trỏ đến commit <code>C</code>. Commit <code>C</code> có parent là <code>B</code>, <code>B</code> có parent là <code>A</code>. Khi nhìn từ commit mới về trước, ta lần theo các parent để đi ngược lịch sử.

Khi tạo một branch mới từ <code>C</code>, Git chỉ cần tạo thêm một reference trỏ đến cùng commit:

~~~text
A --- B --- C
          main
          feature
~~~

Hai tên branch cùng trỏ đến <code>C</code>. Không có commit nào được sao chép và không có thư mục nào được nhân đôi. Hai branch chỉ bắt đầu có vị trí khác nhau khi một trong hai được cập nhật bằng commit mới hoặc thao tác thay đổi ref.

Sau khi tạo commit <code>D</code> trên <code>feature</code>:

~~~text
A --- B --- C --- D
          main    feature
~~~

<code>main</code> vẫn trỏ đến <code>C</code>, còn <code>feature</code> trỏ đến <code>D</code>. Commit <code>D</code> có parent là <code>C</code>. Hai branch chia sẻ toàn bộ lịch sử đến <code>C</code>, sau đó một branch đi xa hơn.

## 2. Branch thực chất là reference

Branch local thường được lưu dưới tên reference thuộc không gian:

~~~text
refs/heads/<branch-name>
~~~

Ví dụ:

~~~text
refs/heads/main
refs/heads/feature/payment-retry
~~~

Reference chứa object ID của commit mà branch đang trỏ đến. Git quản lý reference và có thể lưu chúng dưới thư mục <code>.git/refs/heads/</code> hoặc gộp vào file <code>packed-refs</code>. Cách lưu vật lý có thể thay đổi theo repository và thao tác bảo trì; hãy dùng lệnh Git để đọc hoặc cập nhật ref thay vì sửa file nội bộ bằng tay.

Một số lệnh để xem branch và ref:

~~~bash
# Liệt kê branch local
git branch

# Xem object ID của các branch local
git show-ref --heads

# Xem commit mà branch main trỏ tới
git rev-parse main

# Xem commit mà HEAD hiện tại phân giải thành
git rev-parse HEAD
~~~

Tên branch là tên dễ nhớ cho một vị trí trong lịch sử. Object ID mới là định danh của commit. Khi branch di chuyển, tên branch vẫn giữ nguyên nhưng object ID mà nó trỏ đến thay đổi.

### Branch không chứa thay đổi chưa commit

Branch trỏ đến commit, không trỏ đến trạng thái đang sửa dở trong working tree. Thay đổi chưa stage nằm trong working tree; thay đổi đã stage nằm trong index. Chúng không trở thành một phần của lịch sử branch cho đến khi được commit.

Vì vậy, hai branch có thể cùng trỏ đến một commit nhưng working tree có thay đổi chưa commit. Những thay đổi đó thuộc trạng thái local hiện tại, không phải dữ liệu được lưu trong branch reference.

## 3. HEAD cho biết vị trí làm việc hiện tại

Trong trạng thái thông thường, <code>HEAD</code> là một symbolic reference trỏ đến branch local đang checkout. Ví dụ:

~~~text
HEAD -> refs/heads/main -> commit C
~~~

Khi đó:

- <code>HEAD</code> cho biết branch hiện tại là <code>main</code>.
- <code>refs/heads/main</code> trỏ đến commit <code>C</code>.
- <code>git rev-parse HEAD</code> trả về object ID của commit <code>C</code>.
- Khi tạo commit mới, Git cập nhật <code>refs/heads/main</code>.

Kiểm tra bằng:

~~~bash
# Tên branch đang checkout
git branch --show-current

# HEAD đang trỏ tượng trưng đến ref nào
git symbolic-ref HEAD

# Object ID mà HEAD phân giải thành
git rev-parse HEAD
~~~

Thông thường <code>git symbolic-ref HEAD</code> in:

~~~text
refs/heads/main
~~~

HEAD không phải là một bản sao của branch. Nó là con trỏ cho biết branch nào đang được chọn trong working tree hiện tại.

## 4. Tạo branch chỉ tạo con trỏ mới

Giả sử bạn đang ở <code>main</code>, tại commit <code>C</code>. Lệnh:

~~~bash
git branch feature/payment-retry
~~~

tạo branch <code>feature/payment-retry</code> trỏ đến cùng commit mà HEAD hiện tại đang phân giải. Lệnh này không chuyển sang branch mới.

Kiểm tra:

~~~bash
git branch --list
git rev-parse main
git rev-parse feature/payment-retry
git branch --show-current
~~~

Ngay sau khi tạo, hai branch thường có cùng object ID và branch hiện tại vẫn là <code>main</code>.

Muốn vừa tạo branch vừa chuyển sang đó:

~~~bash
git switch -c feature/payment-retry
~~~

Lệnh này thực hiện hai việc: tạo branch tại commit hiện tại và cập nhật HEAD để trỏ đến branch mới. Có thể viết thành hai bước:

~~~bash
git branch feature/payment-retry
git switch feature/payment-retry
~~~

<code>git switch -c</code> là cách gọn hơn khi bạn muốn bắt đầu làm việc ngay trên branch mới.

### Tạo branch từ một commit cụ thể

Bạn không bắt buộc phải tạo branch từ HEAD hiện tại. Có thể chỉ định start point:

~~~bash
git branch hotfix/payment-timeout v1.8.0
~~~

Nếu <code>v1.8.0</code> là tag trỏ đến commit phát hành, branch <code>hotfix/payment-timeout</code> sẽ bắt đầu tại commit đó. Chuyển sang branch:

~~~bash
git switch hotfix/payment-timeout
~~~

Khi cần tạo và chuyển cùng lúc từ một start point:

~~~bash
git switch -c hotfix/payment-timeout v1.8.0
~~~

## 5. Điều gì xảy ra khi tạo commit trên branch?

Giả sử bạn đang checkout <code>feature/payment-retry</code>, branch trỏ đến commit <code>C</code>. Sau khi sửa file, stage và commit:

~~~bash
git add src/payment/RetryPolicy.java
git commit -m "Add bounded payment retry"
~~~

Git tạo commit <code>D</code> với parent là <code>C</code>, rồi cập nhật branch hiện tại từ <code>C</code> sang <code>D</code>:

~~~text
A --- B --- C --- D
          |       |
         main   feature/payment-retry
~~~

HEAD vẫn trỏ tượng trưng đến <code>refs/heads/feature/payment-retry</code>. Reference branch được di chuyển đến <code>D</code>; HEAD không cần đổi tên hay lưu một commit mới riêng.

Kiểm tra:

~~~bash
git log --oneline --decorate --graph --all
git rev-parse HEAD
git rev-parse feature/payment-retry
git symbolic-ref HEAD
~~~

Kết quả cho thấy HEAD và branch hiện tại phân giải về cùng commit <code>D</code>.

Nếu bạn chuyển sang <code>main</code> rồi tạo commit, chỉ <code>main</code> được cập nhật. <code>feature/payment-retry</code> vẫn trỏ đến <code>D</code> cho đến khi có thao tác tác động trực tiếp đến branch đó.

## 6. Chuyển branch là đổi HEAD và cập nhật working tree

Lệnh:

~~~bash
git switch main
~~~

yêu cầu Git chuyển HEAD sang branch <code>main</code>, đồng thời cập nhật index và working tree để phản ánh snapshot của commit mà <code>main</code> trỏ đến.

Trước khi chuyển branch, Git kiểm tra thay đổi local để tránh ghi đè dữ liệu chưa được lưu. Nếu thay đổi trong working tree hoặc index có thể bị mất hoặc xung đột với snapshot đích, Git thường từ chối chuyển branch và yêu cầu bạn commit, stash hoặc xử lý thay đổi trước.

Kiểm tra branch sau khi chuyển:

~~~bash
git branch --show-current
git symbolic-ref HEAD
git status --short
~~~

### Branch và working tree là hai khái niệm riêng

Branch là reference đến commit. Working tree là các file đang hiển thị trên đĩa. Khi switch branch, Git thay đổi HEAD và thường cập nhật working tree để khớp snapshot của branch đích. Nếu hai branch trỏ đến cùng commit, việc switch có thể không làm nội dung file thay đổi, nhưng HEAD vẫn chuyển sang reference khác.

Đây là lý do bạn có thể đứng trên <code>main</code> hoặc <code>feature</code> dù cả hai đang trỏ đến cùng một commit.

## 7. Merge làm con trỏ branch đích tiến lên

Merge kết hợp lịch sử của một branch khác vào branch hiện tại. Bạn phải checkout branch đích trước; branch đang checkout là branch sẽ được cập nhật.

### Fast-forward merge

Giả sử <code>main</code> đang trỏ đến <code>C</code>, còn <code>feature</code> có thêm hai commit <code>D</code> và <code>E</code> dựa trên <code>C</code>:

~~~text
A --- B --- C --- D --- E
          main            feature
~~~

Nếu checkout <code>main</code> rồi merge <code>feature</code>:

~~~bash
git switch main
git merge feature
~~~

Git có thể fast-forward vì commit <code>C</code> là tổ tiên của <code>E</code>. Không cần tạo merge commit; Git chỉ di chuyển con trỏ <code>main</code> từ <code>C</code> đến <code>E</code>:

~~~text
A --- B --- C --- D --- E
                          main, feature
~~~

Hai branch giờ trỏ đến cùng commit. Các commit <code>D</code> và <code>E</code> vốn đã tồn tại trên feature; fast-forward chỉ cập nhật reference.

### Merge commit khi lịch sử đã phân nhánh

Nếu cả hai branch đều có commit riêng:

~~~text
          D --- E  feature
         /
A --- B --- C --- F  main
~~~

Khi merge feature vào main, Git tạo commit merge <code>M</code> có hai parent: <code>F</code> và <code>E</code>. Branch <code>main</code> di chuyển đến <code>M</code>, còn <code>feature</code> vẫn trỏ đến <code>E</code>:

~~~text
          D --- E -----------.
         /                    \
A --- B --- C --- F ----------- M  (main)
~~~

Sau merge, <code>feature</code> vẫn trỏ đến <code>E</code>, còn <code>main</code> trỏ đến <code>M</code>. Commit <code>M</code> có hai parent là <code>F</code> và <code>E</code>. Merge không viết lại commit cũ; nó thêm một commit kết hợp và di chuyển branch đích.

Bạn có thể yêu cầu tạo merge commit ngay cả khi fast-forward có thể thực hiện:

~~~bash
git switch main
git merge --no-ff feature
~~~

Điều này giữ một mốc merge rõ ràng trong lịch sử. Chính sách dùng fast-forward hay merge commit phụ thuộc quy ước của nhóm.

## 8. Rebase tạo commit mới rồi di chuyển branch

Rebase đặt lại các commit của branch hiện tại trên một commit nền khác. Git phát lại các thay đổi thành những commit mới, vì parent mới làm object ID của commit thay đổi.

Giả sử:

~~~text
          D --- E  feature
         /
A --- B --- C --- F  main
~~~

Khi checkout feature và chạy:

~~~bash
git switch feature
git rebase main
~~~

Git phát lại thay đổi của <code>D</code> và <code>E</code> trên <code>F</code>, tạo các commit mới <code>D'</code> và <code>E'</code>. Branch feature di chuyển đến commit mới cuối cùng:

~~~text
          D --- E                 (lịch sử cũ)
         /
A --- B --- C --- F --- D' --- E'  feature
                 main
~~~

Trong hình, <code>main</code> vẫn trỏ đến <code>F</code>, còn <code>feature</code> trỏ đến <code>E'</code>. Các commit cũ <code>D</code> và <code>E</code> không bị sửa tại chỗ; chúng có thể trở thành unreachable nếu không còn ref nào trỏ đến chúng và sau này có thể được dọn bởi garbage collection.

Điểm cần nhớ:

- Parent links bên trong commit đã tạo là bất biến.
- Rebase tạo commit object mới với parent mới.
- Branch hiện tại được cập nhật để trỏ đến commit mới sau khi rebase thành công.
- Branch nền không tự di chuyển chỉ vì bạn rebase branch khác lên nó.

Không rebase các commit đã chia sẻ nếu chưa thống nhất với nhóm, vì việc viết lại lịch sử có thể buộc người khác phải đồng bộ lại branch của họ.

## 9. Reset di chuyển branch hiện tại đến commit khác

<code>git reset</code> có thể di chuyển branch hiện tại về một commit khác. Nó cũng có các chế độ điều khiển cách index và working tree được cập nhật.

Ví dụ:

~~~bash
git reset --soft HEAD~1
~~~

Lệnh trên di chuyển branch hiện tại lùi một commit, nhưng giữ nguyên index và working tree. Nội dung commit vừa bỏ khỏi đầu branch vẫn ở trạng thái staged để bạn có thể sửa và commit lại.

Ba chế độ thường gặp:

| Lệnh | Branch ref | Index | Working tree |
|---|---|---|---|
| <code>git reset --soft &lt;commit&gt;</code> | Di chuyển đến commit đích | Giữ nguyên | Giữ nguyên |
| <code>git reset --mixed &lt;commit&gt;</code> | Di chuyển đến commit đích | Cập nhật theo commit đích | Giữ nội dung file đang có |
| <code>git reset --hard &lt;commit&gt;</code> | Di chuyển đến commit đích | Cập nhật theo commit đích | Cập nhật theo commit đích, có thể làm mất thay đổi local |

Nếu bỏ tùy chọn mode, <code>git reset</code> mặc định dùng <code>--mixed</code>.

Sơ đồ đơn giản trước và sau reset:

~~~text
Trước:
A --- B --- C --- D  main

git reset --soft HEAD~1

Sau:
A --- B --- C  main
          \
           D  (không còn ở đầu branch hiện tại)
~~~

Commit <code>D</code> không nhất thiết bị xóa ngay. Reflog thường ghi lại lần di chuyển ref, giúp bạn tìm lại commit cũ nếu cần:

~~~bash
git reflog
~~~

Reset trên branch đã chia sẻ có thể khiến lịch sử local khác remote và gây khó khăn cho người khác. Hãy hiểu rõ tác động trước khi dùng, đặc biệt với <code>--hard</code>.

## 10. Detached HEAD: HEAD trỏ thẳng đến commit

HEAD không phải lúc nào cũng trỏ đến branch. Khi bạn checkout một commit hoặc tag trực tiếp, HEAD có thể chứa object ID thay vì symbolic ref. Trạng thái này gọi là detached HEAD.

Ví dụ:

~~~bash
git switch --detach v1.8.0
~~~

Sơ đồ:

~~~text
refs/heads/main ---------> commit C
refs/tags/v1.8.0 --------> commit B
HEAD -------------------> commit B
~~~

Trong trạng thái này:

- Bạn đang xem snapshot tại commit <code>B</code>.
- Không có branch local nào được checkout.
- <code>git branch --show-current</code> thường in rỗng.
- Nếu tạo commit mới, HEAD di chuyển đến commit mới nhưng branch <code>main</code> không di chuyển.

Kiểm tra:

~~~bash
git status -sb
git branch --show-current
git symbolic-ref -q HEAD
git rev-parse HEAD
~~~

Lệnh <code>git symbolic-ref -q HEAD</code> trả mã lỗi khi HEAD không phải symbolic ref. Điều đó là bình thường trong detached HEAD.

### Giữ lại commit tạo trong detached HEAD

Nếu bạn tạo commit khi detached HEAD và muốn tiếp tục phát triển từ đó, hãy tạo branch:

~~~bash
git switch -c experiment/release-fix
~~~

Branch mới trỏ đến commit hiện tại và HEAD chuyển sang branch đó. Nếu đã rời detached HEAD mà chưa tạo branch, có thể tìm commit trong reflog rồi tạo branch cứu hộ:

~~~bash
git reflog
git switch -c rescue/release-fix <commit-id>
~~~

Đừng dựa vào việc commit detached luôn tồn tại mãi. Nếu không còn ref nào giữ commit, object có thể trở thành unreachable và được Git dọn sau này.

## 11. Xóa branch là xóa reference

Khi xóa branch:

~~~bash
git branch -d feature/payment-retry
~~~

Git xóa reference <code>refs/heads/feature/payment-retry</code>. Các commit mà branch từng trỏ đến không bị xóa trực tiếp. Nếu commit vẫn được branch khác, tag hoặc ref khác tham chiếu thì chúng vẫn reachable.

Git thường từ chối <code>-d</code> nếu branch chưa được merge vào upstream hoặc HEAD hiện tại, nhằm tránh xóa một branch có commit chưa được tích hợp. Tùy chọn ép:

~~~bash
git branch -D feature/payment-retry
~~~

chỉ nên dùng khi bạn đã xác nhận không cần branch đó. Nếu các commit chỉ còn được giữ bởi reflog hoặc không còn ref nào trỏ đến, khả năng khôi phục có thể bị giới hạn theo thời gian và chính sách garbage collection.

## 12. Branch local và remote-tracking branch

Branch local và remote-tracking branch đều là reference, nhưng có vai trò khác nhau:

| Loại ref | Ví dụ | Vai trò |
|---|---|---|
| Branch local | <code>refs/heads/main</code> | Dòng phát triển local mà bạn có thể checkout và commit |
| Remote-tracking | <code>refs/remotes/origin/main</code> | Ghi nhận trạng thái branch trên remote ở lần fetch gần nhất |
| Tag | <code>refs/tags/v1.8.0</code> | Đánh dấu một object, thường dùng cho mốc phát hành |

Remote-tracking ref không phải branch đang chạy trên máy chủ. Nó là bản ghi local được cập nhật khi fetch:

~~~bash
git fetch origin
git branch -r
git show-ref --verify refs/remotes/origin/main
~~~

Khi fetch nhận commit mới từ remote, reference <code>origin/main</code> có thể di chuyển. Branch local <code>main</code> không tự động di chuyển theo nếu bạn chưa pull, merge hoặc rebase.

Khi push thành công, máy chủ cập nhật branch remote theo yêu cầu push. Hãy fetch lại khi cần làm mới remote-tracking ref local; đừng giả định mọi thao tác push đều đã làm mới bản ghi local này.

## 13. Quan sát toàn bộ con trỏ và đồ thị

Những lệnh sau hữu ích khi muốn biết branch đang trỏ đến đâu:

~~~bash
# Hiển thị đồ thị commit cùng tên branch/tag
git log --oneline --decorate --graph --all

# Liệt kê branch local
git branch -vv

# Liệt kê remote-tracking branch
git branch -r

# Liệt kê mọi ref cùng object ID
git show-ref

# Kiểm tra HEAD có phải symbolic ref không
git symbolic-ref -q HEAD

# Phân giải HEAD thành object ID
git rev-parse HEAD
~~~

Đọc kết quả theo thứ tự:

1. Xác định HEAD đang trỏ đến branch nào hay đang detached.
2. Xác định branch local trỏ đến commit nào.
3. Xác định remote-tracking ref đang ghi nhận commit nào.
4. Xem đồ thị để biết các commit nào là tổ tiên, nhánh nào đã phân kỳ và điểm chung nằm ở đâu.

Không cần mở file trong thư mục <code>.git</code> để suy ra trạng thái. Lệnh Git sẽ đọc và cập nhật reference theo đúng định dạng lưu trữ của repository.

## 14. Phân biệt branch với tag

Branch và tag đều là ref có tên, nhưng mục đích khác nhau:

- Branch là con trỏ di chuyển theo dòng phát triển. Khi commit trên branch đang checkout, branch tiến đến commit mới.
- Tag thường đánh dấu một mốc cụ thể như release. Tag thông thường không tự di chuyển khi bạn tạo commit mới.

Ví dụ:

~~~bash
git tag v1.8.0
git switch main
git commit -m "Continue development"
~~~

Commit mới làm <code>main</code> tiến lên, còn tag <code>v1.8.0</code> vẫn đánh dấu commit đã được gắn tag. Tag có thể được tạo lại hoặc di chuyển bằng thao tác rõ ràng, nhưng không nên xem tag phát hành như branch làm việc.

## 15. Những nhầm lẫn thường gặp

| Nhầm lẫn | Thực tế |
|---|---|
| Branch là bản sao thư mục | Branch là reference trỏ đến commit |
| Tạo branch sẽ tự chuyển sang branch mới | <code>git branch</code> chỉ tạo ref; <code>git switch</code> mới chuyển HEAD |
| HEAD luôn chứa object ID trực tiếp | Thông thường HEAD là symbolic ref; detached HEAD mới trỏ trực tiếp đến commit |
| Commit mới làm mọi branch cùng tiến lên | Chỉ branch đang checkout thường được cập nhật |
| Merge luôn tạo commit mới | Fast-forward merge chỉ di chuyển ref; merge phân kỳ thường tạo merge commit |
| Rebase di chuyển commit cũ sang parent mới | Rebase tạo commit mới rồi cập nhật branch đến commit mới |
| Xóa branch sẽ xóa ngay các commit | Xóa ref; commit có thể còn reachable qua ref khác hoặc reflog |
| <code>origin/main</code> là branch remote trực tiếp | Đó là remote-tracking ref local được cập nhật qua fetch |
| Detached HEAD không thể tạo commit | Vẫn tạo được commit, nhưng không có branch local tự động giữ commit đó |

## 16. Bài tập tự kiểm tra

Thực hành trong repository thử nghiệm:

1. Tạo ba commit tuyến tính trên <code>main</code> và vẽ đồ thị bằng <code>git log --graph --oneline --decorate</code>.
2. Tạo branch <code>feature</code> từ HEAD; xác nhận hai branch ban đầu có cùng object ID.
3. Tạo một commit trên <code>feature</code>; quan sát chỉ con trỏ feature di chuyển.
4. Chuyển về <code>main</code> và tạo commit khác; giải thích vì sao hai branch phân kỳ.
5. Tạo branch từ một tag hoặc commit cũ thay vì HEAD hiện tại.
6. Thử fast-forward merge và quan sát branch đích tiến đến commit có sẵn.
7. Tạo hai nhánh có commit riêng rồi merge để quan sát merge commit hai parent.
8. Rebase branch thử nghiệm lên branch nền và so sánh object ID trước/sau.
9. Checkout detached HEAD, tạo commit rồi tạo branch cứu hộ để giữ commit.
10. Xóa branch đã merge và xác định commit còn reachable từ branch nào.
11. Fetch remote và phân biệt <code>main</code> với <code>origin/main</code>.
12. Dùng <code>git reflog</code> để quan sát các lần HEAD hoặc branch ref di chuyển.

Khi đọc đồ thị commit, hãy xem branch là những tên trỏ đến các commit tip và HEAD là chỉ dẫn về vị trí làm việc hiện tại. Commit tạo thêm node và parent link; các thao tác như switch, merge, rebase hoặc reset quyết định reference nào được di chuyển. Nắm được điều đó giúp bạn hiểu lịch sử Git thay vì chỉ ghi nhớ tên lệnh.
