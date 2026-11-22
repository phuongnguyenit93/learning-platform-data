# HEAD gắn với nhánh và trạng thái detached HEAD

HEAD là tên tham chiếu đặc biệt cho biết Git đang đứng tại commit nào trong repository hiện tại. Trong workflow thông thường, HEAD gắn với một branch local như main hoặc feature/login. Khi đó, commit mới sẽ làm branch hiện tại tiến lên. Nhưng bạn cũng có thể checkout trực tiếp một commit, tag hoặc remote-tracking branch; lúc này HEAD trỏ thẳng tới commit và Git ở trạng thái detached HEAD.

Detached HEAD không phải lỗi. Đây là trạng thái hữu ích khi cần xem lại một phiên bản cũ, chạy thử một commit cụ thể, điều tra regression hoặc để CI kiểm tra chính xác một commit. Điều cần hiểu là commit tạo ra khi detached HEAD không tự cập nhật branch nào. Nếu muốn giữ công việc đó lâu dài, hãy tạo branch trước khi rời commit.

## 1. HEAD là gì?

Git lưu lịch sử bằng các commit có quan hệ cha-con. Một branch local là một tên tham chiếu trỏ tới commit đầu nhánh. HEAD cho biết vị trí làm việc hiện tại của repository.

Khi bạn đang ở branch main, cấu trúc khái niệm là:

~~~text
HEAD
  |
  v
refs/heads/main
  |
  v
commit C
~~~

HEAD thường không lưu trực tiếp hash của commit khi đang gắn với branch. Nó là một symbolic ref trỏ tới tên branch, ví dụ refs/heads/main. Branch đó mới trỏ tới commit hiện tại.

Trong thư mục Git, nội dung .git/HEAD ở trạng thái này thường tương tự:

~~~text
ref: refs/heads/main
~~~

Đường dẫn .git có thể là thư mục hoặc file trỏ tới Git directory, chẳng hạn trong linked worktree. Dùng các lệnh Git để truy vấn thay vì phụ thuộc vào vị trí vật lý của metadata.

## 2. HEAD và branch di chuyển cùng nhau khi commit

Giả sử main đang trỏ tới commit C và bạn checkout branch main:

~~~text
      HEAD
        |
        v
main -> C
~~~

Sau khi tạo commit mới D, Git cập nhật branch main trỏ tới D. Vì HEAD vẫn gắn với main, vị trí HEAD cũng được hiểu là commit D:

~~~text
HEAD
  |
  v
main -> D
         |
         v
         C
~~~

Vì vậy, khi đang ở branch bình thường, bạn không phải tự di chuyển HEAD sau mỗi commit. Git cập nhật ref branch hiện tại và symbolic HEAD tiếp tục trỏ tới branch đó.

Kiểm tra vị trí hiện tại:

~~~bash
git status -sb
git branch --show-current
git rev-parse HEAD
~~~

git branch --show-current in tên branch local đang checkout. git rev-parse HEAD in object ID của commit mà HEAD phân giải tới.

## 3. Kiểm tra HEAD đang gắn với branch nào

Dùng git symbolic-ref:

~~~bash
git symbolic-ref HEAD
~~~

Khi đang gắn với main, kết quả là:

~~~text
refs/heads/main
~~~

Lệnh này hỏi Git symbolic ref mà HEAD trỏ tới. Nếu HEAD đang detached, lệnh thường trả mã thoát khác 0 vì HEAD không còn là symbolic ref tới branch.

Có thể xem tên branch ngắn:

~~~bash
git branch --show-current
~~~

Nếu kết quả rỗng, bạn có thể đang ở detached HEAD hoặc repository chưa có branch được checkout, chẳng hạn trạng thái chưa có commit đầu tiên. Vì vậy, hãy kết hợp với git status và git symbolic-ref để xác định chính xác.

Xem commit hiện tại và branch liên quan:

~~~bash
git log -1 --oneline --decorate
git show-ref --heads
~~~

git show-ref --heads liệt kê các branch local và object ID của chúng. HEAD có thể đang trỏ tới một commit mà không branch nào hiện tại trỏ trực tiếp tới.

## 4. Chuyển branch bằng git switch

Khi chuyển sang branch đã tồn tại:

~~~bash
git switch main
~~~

Git cập nhật HEAD thành symbolic ref tới refs/heads/main và cập nhật working tree/index để phản ánh snapshot của branch đó, trong giới hạn an toàn với thay đổi local hiện có.

Tạo branch mới và chuyển sang branch đó:

~~~bash
git switch -c feature/inventory-search
~~~

Lệnh tương đương về mục đích với tạo branch rồi checkout:

~~~bash
git branch feature/inventory-search
git switch feature/inventory-search
~~~

Sau khi chuyển branch, xác minh:

~~~bash
git branch --show-current
git symbolic-ref HEAD
git status -sb
~~~

Tên branch xuất hiện trong git branch --show-current, còn symbolic ref thường là refs/heads/feature/inventory-search.

## 5. Detached HEAD là gì?

Detached HEAD xảy ra khi HEAD trỏ trực tiếp tới một commit thay vì trỏ tới tên branch. Ví dụ:

~~~text
HEAD -> commit C

main -> commit D
~~~

HEAD đang ở commit C, trong khi branch main vẫn trỏ tới commit D. Không có branch local nào được di chuyển chỉ vì bạn checkout C.

Trong .git/HEAD, trạng thái này thường được biểu diễn bằng object ID của commit thay vì dòng ref:

~~~text
<commit-id>
~~~

Detached HEAD thường xuất hiện khi checkout:

- Một commit bằng hash.
- Một tag release.
- Một remote-tracking branch như origin/main.
- Một biểu thức revision như HEAD~2.

Git hiển thị trạng thái này trong git status, thường bằng thông báo tương tự HEAD detached at ...

## 6. Chủ động checkout một commit để kiểm tra

Ví dụ, xem trạng thái của commit trước branch hiện tại:

~~~bash
git switch --detach HEAD~1
~~~

Hoặc checkout commit cụ thể:

~~~bash
git switch --detach a1b2c3d
~~~

Bạn có thể đọc file, chạy test hoặc build ở phiên bản đó mà không di chuyển branch main. Đây là cách hữu ích để xác định một lỗi đã xuất hiện từ commit nào hoặc xác minh một bản build cũ.

Kiểm tra:

~~~bash
git status -sb
git branch --show-current
git rev-parse HEAD
git symbolic-ref HEAD
~~~

Khi detached, git branch --show-current thường không in tên branch và git symbolic-ref HEAD thất bại. git rev-parse HEAD vẫn trả về commit ID đang được checkout.

Lệnh cũ git checkout <commit> cũng có thể đưa repository vào detached HEAD. Cú pháp git switch --detach diễn đạt rõ ý định chuyển vị trí mà không checkout branch.

## 7. Checkout tag cũng thường tạo detached HEAD

Tag thường dùng để đánh dấu một phiên bản cụ thể. Khi muốn xem đúng nội dung tại tag:

~~~bash
git switch --detach v1.4.0
~~~

Git checkout commit mà tag phân giải tới. Nếu tag là annotated tag, Git bóc tag object để lấy commit đích. HEAD sẽ detached tại commit đó.

Đây là hành vi mong muốn khi bạn chỉ cần xem hoặc kiểm thử release. Nếu định phát triển bản vá từ phiên bản này, hãy tạo branch mới thay vì tiếp tục commit trong trạng thái detached mà không có tên branch giữ lại.

## 8. Checkout remote-tracking branch

Remote-tracking branch như origin/main là ref local ghi nhận trạng thái branch main trên remote ở lần fetch gần nhất. Nó không phải branch local để làm việc trực tiếp.

Để kiểm tra chính xác commit đang có trên remote-tracking ref:

~~~bash
git fetch origin
git switch --detach origin/main
~~~

Lệnh đầu cập nhật thông tin remote. Lệnh thứ hai checkout commit mà origin/main đang trỏ tới và tạo trạng thái detached HEAD.

Nếu muốn làm việc tiếp trên branch local theo dõi remote, tạo branch local có upstream:

~~~bash
git switch --track origin/main
~~~

Hoặc chỉ định tên branch local:

~~~bash
git switch -c main --track origin/main
~~~

Nếu branch local main đã tồn tại, dùng git switch main để chuyển sang branch đó; không tạo branch trùng tên.

## 9. Commit khi đang ở detached HEAD

Git vẫn cho phép commit trong trạng thái detached nếu working tree và index hợp lệ:

~~~bash
git switch --detach HEAD~1
# chỉnh sửa file
git add src/main/App.java
git commit -m "test: inspect behavior on previous revision"
~~~

Commit mới được tạo với commit hiện tại làm parent. HEAD di chuyển tới commit mới, nhưng không có branch local nào tự động cập nhật để trỏ tới commit đó.

Sơ đồ trước và sau commit:

~~~text
Trước commit:                 Sau commit:

main -> D                     main -> D
         |                             |
         C  <- HEAD                   C
                                      |
                                      E  <- HEAD
~~~

Commit E tồn tại trong object database và được HEAD tham chiếu trong lúc bạn còn ở đó. Nếu sau đó chuyển sang branch khác, không còn branch nào giữ E nếu bạn chưa tạo ref mới. Reflog thường giúp tìm lại trong một khoảng thời gian, nhưng commit không được đặt tên có thể cuối cùng bị garbage collection thu hồi.

## 10. Giữ commit detached bằng cách tạo branch

Nếu bạn muốn tiếp tục phát triển hoặc giữ commit vừa tạo, tạo branch ngay tại vị trí hiện tại:

~~~bash
git switch -c fix/legacy-behavior
~~~

Lệnh tạo branch fix/legacy-behavior trỏ tới commit mà HEAD đang đứng và đồng thời chuyển HEAD sang branch mới.

Sơ đồ sau khi tạo branch:

~~~text
fix/legacy-behavior -> E <- HEAD
                       |
                       C
                       |
                       ...

main ----------------> D
~~~

Commit E giờ được giữ bởi branch mới. Bạn có thể tiếp tục commit, push branch hoặc mở pull request theo quy trình nhóm.

Nếu chưa tạo commit mà chỉ muốn bắt đầu phát triển từ commit detached hiện tại, git switch -c <branch> cũng là cách an toàn để đặt tên cho điểm bắt đầu.

## 11. Khôi phục commit sau khi đã rời detached HEAD

Giả sử bạn tạo commit E khi detached, sau đó chuyển sang main mà quên tạo branch. Có thể dùng reflog để tìm lại vị trí HEAD trước đó:

~~~bash
git reflog --date=local
~~~

Reflog ghi lại các lần cập nhật ref local, gồm những lần HEAD di chuyển khi checkout và commit. Tìm dòng có commit message hoặc hash của commit detached.

Sau khi xác định đúng commit, tạo branch cứu lại:

~~~bash
git switch -c rescue/detached-work <commit-id>
~~~

Hoặc dùng biểu thức reflog nếu đã xác minh đúng entry:

~~~bash
git switch -c rescue/detached-work HEAD@{2}
~~~

Con số trong HEAD@{2} chỉ là ví dụ; vị trí reflog thay đổi theo thao tác thực tế. Hãy đọc git reflog và thay bằng entry đúng, không sao chép nguyên chỉ số minh họa.

Reflog là cơ chế local, không được push như một phần lịch sử branch thông thường và có thể bị dọn theo chính sách expiry/garbage collection. Khi tìm lại được commit cần giữ, hãy tạo branch hoặc tag để nó có ref ổn định.

## 12. Phân biệt HEAD, branch local, remote-tracking branch và tag

| Tên | Loại ref | Vai trò |
|---|---|---|
| HEAD | Pseudoref; thường là symbolic ref hoặc detached object ID | Vị trí hiện tại của repository/worktree |
| refs/heads/main | Local branch | Tên branch local, thường di chuyển khi commit trên branch đó |
| refs/remotes/origin/main | Remote-tracking branch | Ghi nhận trạng thái branch remote ở lần fetch gần nhất |
| refs/tags/v1.4.0 | Tag ref | Đánh dấu object, thường là commit phát hành |

Các ref này đều có thể giúp Git tìm tới commit, nhưng ý nghĩa và cách cập nhật khác nhau. Checkout origin/main hoặc v1.4.0 thường tạo detached HEAD; checkout main gắn HEAD với local branch main.

## 13. Kiểm tra nội dung HEAD và ref bằng lệnh Git

Một số lệnh hữu ích:

~~~bash
git rev-parse HEAD
git symbolic-ref HEAD
git rev-parse --symbolic-full-name HEAD
git branch --show-current
git show-ref --heads
git show-ref --tags
~~~

- git rev-parse HEAD in commit ID hiện tại.
- git symbolic-ref HEAD in symbolic target nếu HEAD đang gắn với ref.
- git rev-parse --symbolic-full-name HEAD hiển thị tên ref đầy đủ khi phân giải được symbolic ref.
- git branch --show-current in tên branch local hiện tại; detached HEAD thường cho kết quả rỗng.
- git show-ref --heads liệt kê local branches.
- git show-ref --tags liệt kê tag refs.

Muốn xem vị trí HEAD file trực tiếp, có thể dùng:

~~~bash
git rev-parse --git-path HEAD
~~~

Lệnh trả về vị trí HEAD file theo Git directory hiện tại. Trên repository thường, đó là .git/HEAD; trong linked worktree, vị trí có thể nằm dưới thư mục quản trị worktree. Ưu tiên các lệnh Git để truy vấn vì chúng xử lý cả hai trường hợp.

## 14. HEAD trong repository chưa có commit đầu tiên

Sau git init, Git có thể đã đặt HEAD làm symbolic ref tới branch khởi tạo, ví dụ refs/heads/main, dù branch ref chưa tồn tại vì repository chưa có commit.

Đây là trạng thái branch chưa sinh commit (unborn branch), không phải detached HEAD. Một số lệnh như git branch --show-current vẫn in main, trong khi git rev-parse HEAD chưa phân giải được commit.

Sau commit đầu tiên, branch main được tạo và trỏ tới commit mới. Phân biệt unborn branch với detached HEAD giúp tránh chẩn đoán sai khi repository vừa được khởi tạo.

## 15. HEAD riêng trong linked worktree

Git worktree cho phép một repository có nhiều working tree. Mỗi worktree có vị trí HEAD riêng để có thể checkout các branch hoặc commit khác nhau cùng lúc.

Ví dụ:

~~~bash
git worktree add ../inventory-hotfix -b hotfix/1.4
~~~

Worktree chính có thể đang ở main, còn ../inventory-hotfix có HEAD gắn với hotfix/1.4. Hai worktree dùng chung object database và một số metadata, nhưng mỗi worktree có trạng thái checkout riêng.

Kiểm tra:

~~~bash
git worktree list
git -C ../inventory-hotfix status -sb
git -C ../inventory-hotfix symbolic-ref HEAD
~~~

Không giả định mọi worktree dùng chung một file .git/HEAD vật lý. Dùng git -C hoặc chạy lệnh từ đúng worktree để xem HEAD của nơi làm việc tương ứng.

## 16. Những thao tác dễ gây nhầm lẫn

- **Checkout hash rồi commit mà không tạo branch:** commit mới không được cập nhật vào branch local; hãy tạo branch ngay khi muốn giữ công việc.
- **Nhầm detached HEAD là lỗi:** đây là trạng thái hợp lệ khi kiểm tra commit/tag cụ thể.
- **Cho rằng commit trong detached HEAD bị mất ngay lập tức:** commit vẫn tồn tại và reflog thường ghi nhận, nhưng cần tạo ref để giữ ổn định.
- **Checkout origin/main để phát triển trực tiếp:** remote-tracking ref không phải branch local; dùng git switch --track origin/main hoặc tạo branch local.
- **Cho rằng tag di chuyển theo commit:** tag là ref riêng, thường được dùng làm mốc bất biến; tạo commit mới không tự di chuyển tag.
- **Dùng git branch --show-current rỗng rồi kết luận repository không có branch:** có thể đang detached hoặc đang ở trạng thái khác; kiểm tra git status và git symbolic-ref HEAD.
- **Dùng HEAD@{n} mà không đọc reflog:** chỉ số phụ thuộc lịch sử di chuyển HEAD; hãy xác minh entry trước khi tạo branch cứu lại.
- **Nhầm unborn branch với detached HEAD:** repository chưa có commit đầu tiên vẫn có thể có symbolic HEAD trỏ tới branch chưa tồn tại.

## 17. Quy trình an toàn khi cần kiểm tra một commit cũ

1. Kiểm tra trạng thái working tree hiện tại:

   ~~~bash
   git status -sb
   ~~~

2. Nếu có thay đổi local, commit, stash hoặc sao lưu theo nhu cầu trước khi chuyển vị trí.
3. Tìm commit cần kiểm tra:

   ~~~bash
   git log --oneline --decorate --all
   ~~~

4. Checkout commit ở detached mode:

   ~~~bash
   git switch --detach <commit-id>
   ~~~

5. Build/test và quan sát hành vi ở phiên bản đó.
6. Nếu tạo thay đổi cần giữ, tạo branch tại commit hiện tại:

   ~~~bash
   git switch -c investigate/fix-from-old-revision
   ~~~

7. Nếu chỉ kiểm tra xong, quay lại branch làm việc:

   ~~~bash
   git switch main
   ~~~

8. Xác nhận branch và trạng thái:

   ~~~bash
   git status -sb
   git branch --show-current
   ~~~

Nếu quên tạo branch và đã rời detached HEAD, dùng git reflog để tìm commit rồi tạo branch cứu lại như phần 11.

## 18. Ghi nhớ

Khi HEAD gắn với branch, nó là symbolic ref tới tên branch và commit mới làm branch đó tiến lên. Khi checkout trực tiếp commit, tag hoặc remote-tracking ref, HEAD trỏ thẳng tới commit trong trạng thái detached. Bạn vẫn có thể đọc, build, test và commit; commit mới chỉ di chuyển HEAD, không tự cập nhật branch nào. Tạo branch bằng git switch -c để giữ công việc, hoặc dùng reflog để tìm lại commit detached nếu đã rời đi. Luôn phân biệt local branch, remote-tracking branch, tag, detached HEAD và unborn branch trước khi quyết định thao tác tiếp theo.
