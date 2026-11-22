# Cập nhật commit được ghim và thứ tự đẩy kho con trước kho cha

Git submodule cho phép một repository cha sử dụng một repository khác như một thành phần phụ thuộc. Repository cha không lưu toàn bộ nội dung của kho con trong commit của mình; nó lưu một tham chiếu đến commit cụ thể của kho con. Tham chiếu này được gọi là **gitlink**. Vì vậy, khi cập nhật submodule, bạn cần hiểu commit nào đang được ghim, commit nào đang có trong working tree của kho con và commit đó đã được đẩy lên remote hay chưa.

Trong chương **Submodule** của module **SOURCE_CONTROL_GIT**, bài học này tập trung vào hai việc thường dễ làm sai: cập nhật commit được ghim trong superproject và đẩy thay đổi theo đúng thứ tự. Kho con phải có commit trên remote để người khác có thể lấy được; sau đó kho cha mới nên ghi nhận và đẩy gitlink trỏ đến commit đó. Nếu đẩy kho cha trước khi commit kho con có thể truy cập được, đồng đội có thể checkout superproject nhưng không tải được đúng phiên bản submodule.

Sau bài học, bạn có thể:

- Giải thích gitlink và cách superproject ghi nhận commit của submodule.
- Phân biệt cập nhật theo commit đã ghim với cập nhật theo remote branch bằng --remote.
- Xác định branch hoặc commit mà submodule đang sử dụng.
- Tạo, commit và push thay đổi bên trong kho con.
- Stage gitlink, commit và push superproject sau khi kho con đã được công bố.
- Kiểm tra trạng thái submodule và xác nhận remote có chứa commit được ghim.
- Dùng push.recurseSubmodules để kiểm tra hoặc tự động push submodule khi phù hợp.

## 1. Superproject ghim một commit bằng gitlink

Khi một thư mục được thêm làm submodule, superproject lưu một entry đặc biệt trong tree:

~~~text
100644 blob    .gitmodules
160000 commit  libs/common
100644 blob    README.md
~~~

Entry có mode **160000** là gitlink. Nó chứa hash của commit trong repository submodule. Superproject không lưu các file của libs/common như những blob thông thường của chính nó; nội dung file và lịch sử thuộc repository kho con.

Có thể hình dung mối quan hệ:

~~~text
Superproject commit P
        |
        +-- tree của kho cha
               |
               +-- .gitmodules
               |
               +-- gitlink libs/common
                         |
                         v
                 Submodule commit C
                         |
                         +-- tree của kho con
                                +-- source files
                                +-- tests
~~~

Commit P ghi nhận rằng phiên bản của superproject sử dụng đúng commit C trong libs/common. Khi branch của kho con tiếp tục phát triển lên commit D, superproject vẫn ghim C cho đến khi bạn cập nhật gitlink và commit thay đổi đó trong kho cha.

Đây là điểm quan trọng: **cập nhật branch bên trong submodule không tự động cập nhật commit được ghim trong superproject**. Superproject chỉ ghi nhận commit mới khi gitlink được stage và đưa vào commit của kho cha.

## 2. Kiểm tra cấu hình và commit đang được ghim

File .gitmodules trong superproject khai báo đường dẫn và URL của từng submodule. Ví dụ:

~~~ini
[submodule "libs/common"]
    path = libs/common
    url = https://example.com/team/common.git
    branch = stable
~~~

Các trường thường gặp:

- **path**: đường dẫn thư mục submodule trong superproject.
- **url**: địa chỉ repository kho con.
- **branch**: branch mà lệnh cập nhật từ remote dùng làm đích khi chạy git submodule update --remote. Nếu không khai báo, Git dùng remote HEAD mặc định của submodule.

Kiểm tra danh sách và trạng thái:

~~~bash
git submodule status
git submodule status --recursive
git config --file .gitmodules --get-regexp '^submodule\..*\.(path|url|branch)$'
~~~

Để xem commit mà superproject hiện tại ghim cho submodule:

~~~bash
git ls-tree HEAD -- libs/common
~~~

Kết quả có dạng:

~~~text
160000 commit 1a2b3c4d...    libs/common
~~~

Hash sau từ commit là commit được ghim trong HEAD của superproject. Để xem commit đang checkout trong working tree submodule:

~~~bash
git -C libs/common rev-parse HEAD
git -C libs/common status -sb
~~~

Nếu hash từ git ls-tree khác hash của git -C libs/common rev-parse HEAD, working tree submodule đang ở commit khác với commit được superproject ghi nhận. Điều này có thể là thay đổi đang chờ cập nhật gitlink, hoặc chỉ là trạng thái checkout tạm thời để review.

## 3. Hiểu các dấu trong git submodule status

Lệnh git submodule status thường thêm ký hiệu trước hash:

| Ký hiệu | Ý nghĩa |
| --- | --- |
| Dấu cách | Submodule đã checkout đúng commit được superproject ghim. |
| - | Submodule chưa được khởi tạo hoặc chưa checkout. |
| + | Commit đang checkout trong submodule khác commit được superproject ghim. |
| U | Submodule đang có xung đột gitlink cần giải quyết. |

Ví dụ:

~~~text
 1a2b3c4d libs/common (heads/stable)
+5e6f7a8b libs/ui (heads/feature)
-9c0d1e2f libs/legacy
U3a4b5c6d libs/parser
~~~

Trong ví dụ:

- libs/common ở đúng commit đã ghim.
- libs/ui đang checkout một commit khác với gitlink của superproject.
- libs/legacy chưa được khởi tạo.
- libs/parser có xung đột gitlink.

Để khởi tạo các submodule chưa có working tree:

~~~bash
git submodule update --init
~~~

Với cả submodule lồng nhau:

~~~bash
git submodule update --init --recursive
~~~

Nếu chỉ muốn khởi tạo một đường dẫn:

~~~bash
git submodule update --init -- libs/common
~~~

## 4. Phân biệt cập nhật theo commit ghim và cập nhật theo remote

Hai lệnh dưới đây phục vụ hai mục tiêu khác nhau.

### Checkout đúng commit được superproject ghi nhận

~~~bash
git submodule update --init -- libs/common
~~~

Lệnh này đưa submodule về commit mà superproject hiện tại đang ghim trong index/checkout. Đây là thao tác thường dùng sau khi clone, chuyển branch hoặc pull superproject để đồng bộ các submodule về đúng phiên bản đã khai báo.

Lệnh update thông thường không có nghĩa là lấy commit mới nhất trên branch remote. Nếu superproject ghim C còn remote branch đã tiến đến D, lệnh trên vẫn checkout C.

### Cập nhật theo branch trên remote

~~~bash
git submodule update --remote -- libs/common
~~~

Tùy chọn **--remote** yêu cầu Git fetch remote của submodule rồi cập nhật working tree theo branch được cấu hình. Branch có thể được khai báo trong .gitmodules bằng trường branch. Nếu không khai báo, Git dùng remote HEAD mặc định.

Mặc định, update --remote checkout commit đích theo detached HEAD. Nó không tự tạo commit mới trong submodule và cũng không tự commit gitlink trong superproject. Sau khi cập nhật, superproject thường hiển thị submodule đã thay đổi; bạn cần stage đường dẫn submodule để ghi nhận gitlink mới.

Nếu muốn tích hợp branch remote vào branch đang checkout trong submodule, có thể dùng --merge hoặc --rebase:

~~~bash
git submodule update --remote --merge -- libs/common
~~~

Hoặc:

~~~bash
git submodule update --remote --rebase -- libs/common
~~~

Các tùy chọn này lần lượt merge hoặc rebase branch remote vào branch hiện tại trong submodule. Chỉ dùng khi bạn chủ động làm việc trên branch đó và hiểu ảnh hưởng đến lịch sử. Nếu chỉ muốn lấy đúng commit remote để kiểm thử hoặc cập nhật gitlink, chế độ checkout mặc định thường dễ dự đoán hơn.

## 5. Chọn branch theo dõi cho submodule

Nếu không có branch trong .gitmodules, --remote sử dụng remote HEAD mặc định của submodule. Để quy định branch ổn định, có thể khai báo trong .gitmodules:

~~~ini
[submodule "libs/common"]
    path = libs/common
    url = https://example.com/team/common.git
    branch = stable
~~~

Hoặc đặt bằng lệnh:

~~~bash
git submodule set-branch --branch stable -- libs/common
~~~

Lệnh này cập nhật .gitmodules trong superproject. Hãy kiểm tra và commit thay đổi .gitmodules cùng với gitlink nếu đó là một phần của thay đổi dự án:

~~~bash
git diff -- .gitmodules
git status --short
~~~

Trường branch là quy ước để chọn nguồn cập nhật khi dùng --remote; nó không tự động làm submodule checkout branch đó ngay khi mở repository. Cũng không nên nhầm branch trong .gitmodules với commit được ghim. Commit được ghim vẫn là hash trong gitlink.

Để xem branch hiện tại và upstream của submodule:

~~~bash
git -C libs/common branch --show-current
git -C libs/common branch -vv
git -C libs/common remote -v
~~~

Nếu branch chưa có upstream, cần xác định remote và branch đúng trước khi push.

## 6. Quy trình cập nhật submodule lên commit mới

Giả sử superproject dùng libs/common và muốn cập nhật từ commit C lên commit D trên branch stable.

### Bước 1: kiểm tra trạng thái superproject và submodule

~~~bash
git status -sb
git submodule status
git -C libs/common status -sb
~~~

Đảm bảo không có thay đổi chưa commit mà bạn chưa biết. Nếu submodule có chỉnh sửa riêng, hãy commit, stash hoặc sao lưu theo nhu cầu trước khi checkout commit khác.

### Bước 2: cập nhật thông tin từ remote của kho con

~~~bash
git -C libs/common fetch origin
git -C libs/common log --oneline --decorate --graph -8 origin/stable
~~~

Kiểm tra commit trên origin/stable. Nếu branch remote thực tế có tên khác, thay stable bằng tên branch đúng. Không mặc định branch là main hoặc master.

### Bước 3: checkout hoặc tích hợp commit cần dùng

Nếu chỉ muốn ghim commit đã có trên remote:

~~~bash
git -C libs/common switch --detach <target-commit>
~~~

Nếu muốn tiếp tục làm việc trên branch stable và cập nhật branch theo remote:

~~~bash
git -C libs/common switch stable
git -C libs/common merge --ff-only origin/stable
~~~

Merge --ff-only chỉ cho phép branch local tiến thẳng đến origin/stable. Nếu branch đã phân kỳ, lệnh dừng để bạn xem xét; không tự tạo merge commit.

### Bước 4: xác minh commit kho con

~~~bash
git -C libs/common rev-parse HEAD
git -C libs/common show --no-patch --oneline HEAD
git -C libs/common status -sb
~~~

Xác nhận HEAD đúng commit mong muốn và working tree không còn thay đổi ngoài dự kiến. Nếu commit vừa tạo local, ghi lại hash.

### Bước 5: cập nhật gitlink trong superproject

Quay về thư mục gốc superproject và stage đường dẫn submodule:

~~~bash
git add -- libs/common
git diff --cached --submodule=log
git status --short
~~~

Lệnh git add đường dẫn submodule ghi nhận commit mà working tree submodule đang checkout vào index của superproject. Nó không stage từng file bên trong repository kho con. Diff dạng submodule log giúp xem commit cũ và commit mới.

### Bước 6: commit thay đổi ở kho cha

~~~bash
git commit -m "chore: update common submodule"
~~~

Commit superproject lưu gitlink mới và, nếu có, thay đổi .gitmodules. Lúc này commit kho con đã được ghi nhận trong lịch sử kho cha nhưng cần đảm bảo nó có thể lấy được từ remote kho con.

Bạn có thể tạo commit superproject ở local trước hoặc sau khi push submodule, nhưng **không push commit superproject lên remote trước khi commit được gitlink trỏ tới đã có thể truy cập từ remote submodule**. Quy trình bên dưới thực hiện push kho con trước để thứ tự dễ kiểm tra.

## 7. Vì sao phải push kho con trước kho cha?

Một commit superproject chứa gitlink chỉ lưu hash commit của submodule. Khi người khác clone superproject, Git phải liên hệ với remote của submodule để lấy đúng commit đó.

Giả sử:

~~~text
Submodule remote:
C---D  (origin/stable)
    ^
    commit mới cần dùng

Superproject local:
P---Q  (HEAD)
    |
    +-- gitlink libs/common -> D
~~~

Nếu commit D mới chỉ tồn tại trong repository local của bạn, superproject Q đã tham chiếu đến D nhưng remote kho con chưa cung cấp D. Khi đồng đội clone hoặc update, Git có thể báo không tìm thấy commit submodule hoặc không checkout được đúng phiên bản.

Thứ tự an toàn:

1. Tạo và kiểm tra commit trong submodule.
2. Push branch hoặc tag chứa commit đó lên remote submodule.
3. Xác minh remote submodule đã có commit.
4. Stage gitlink và commit superproject.
5. Push branch superproject lên remote.

~~~text
Submodule local
   | commit D
   v
Push submodule
   |
   v
Submodule remote có D
   |
   v
Superproject stage gitlink -> D
   | commit Q
   v
Push superproject
   |
   v
Người khác clone/update lấy được Q và D
~~~

Nếu commit submodule đã có sẵn trên remote và có thể lấy được từ nguồn mà đồng đội sử dụng, không cần push lại. Điều cần bảo đảm là commit được gitlink tham chiếu đã có thể truy cập qua remote submodule phù hợp.

## 8. Quy trình push đầy đủ từ kho con đến kho cha

Ví dụ bạn đã sửa code trong libs/common và muốn cập nhật cả hai repository.

### Bước 1: commit trong submodule

~~~bash
git -C libs/common switch -c fix/empty-response
git -C libs/common status -sb
git -C libs/common diff
git -C libs/common add -- src/CommonClient.java
git -C libs/common diff --cached
git -C libs/common commit -m "fix: handle empty response"
~~~

Ví dụ giả định branch fix/empty-response chưa tồn tại. Nếu branch đã có, chuyển sang branch đó và xác nhận đúng base trước khi sửa. Commit này thuộc lịch sử của repository libs/common, không phải superproject.

### Bước 2: push commit submodule

~~~bash
git -C libs/common branch -vv
git -C libs/common push -u origin fix/empty-response
~~~

Thay fix/empty-response bằng branch chứa commit cần chia sẻ. Nếu branch đã tồn tại trên remote, push theo upstream hoặc remote/branch đã cấu hình.

Sau push, kiểm tra:

~~~bash
git -C libs/common ls-remote origin refs/heads/fix/empty-response
git -C libs/common fetch origin fix/empty-response
git -C libs/common merge-base --is-ancestor HEAD FETCH_HEAD
~~~

Lệnh ls-remote xác nhận branch tồn tại trên remote. Lệnh fetch lấy tip branch về FETCH_HEAD; merge-base --is-ancestor trả về thành công nếu commit HEAD hiện tại là tổ tiên của tip remote, nghĩa là remote branch đã chứa commit đó. Nếu lệnh kiểm tra thất bại, đừng push superproject cho đến khi xác định và công bố đúng commit.

### Bước 3: stage gitlink ở superproject

~~~bash
git add -- libs/common
git diff --cached --submodule=log
~~~

Nếu .gitmodules cũng thay đổi, kiểm tra riêng:

~~~bash
git diff --cached -- .gitmodules
~~~

### Bước 4: commit và push superproject

~~~bash
git commit -m "chore: update common submodule"
git push origin main
~~~

Thay main bằng branch superproject mà nhóm đang dùng. Sau khi push, người khác có thể fetch superproject và submodule để lấy đúng commit.

## 9. Tự động kiểm tra hoặc push submodule cùng superproject

Git hỗ trợ tùy chọn --recurse-submodules cho lệnh push. Nó giúp giảm nguy cơ quên push kho con trước kho cha.

### Chế độ check

~~~bash
git push --recurse-submodules=check origin main
~~~

Chế độ check yêu cầu các commit submodule được superproject sắp push phải có sẵn trên ít nhất một remote của submodule. Nếu Git không xác định được commit cần thiết đã có thể truy cập từ remote, lệnh push superproject bị từ chối.

Chế độ này phù hợp khi nhóm muốn tự push submodule theo quy trình riêng nhưng cần một bước kiểm tra để ngăn superproject tham chiếu đến commit chưa được công bố.

### Chế độ on-demand

~~~bash
git push --recurse-submodules=on-demand origin main
~~~

Chế độ on-demand yêu cầu Git push các submodule cần thiết cho lần push superproject. Nếu push submodule thất bại, push superproject cũng không được tiếp tục theo quy trình đó.

Để đặt mặc định:

~~~bash
git config --local push.recurseSubmodules on-demand
~~~

Hoặc dùng check làm mặc định:

~~~bash
git config --local push.recurseSubmodules check
~~~

Chọn một chính sách phù hợp với workflow. On-demand tiện khi remote và branch trong các submodule đã được cấu hình rõ ràng. Check phù hợp khi nhóm muốn tự quyết định cách push kho con nhưng vẫn chặn việc push kho cha quá sớm.

Các chế độ này không thay thế việc kiểm tra branch, quyền push và remote URL của từng submodule. Nếu submodule không có remote/upstream phù hợp hoặc commit không thể push theo cấu hình, thao tác on-demand vẫn có thể thất bại. Hãy đọc output của Git để biết repository con nào chưa được cập nhật.

## 10. Xác minh superproject đang ghim đúng commit

Sau khi commit kho cha, kiểm tra cả index, HEAD và working tree submodule.

~~~bash
git ls-tree HEAD -- libs/common
git -C libs/common rev-parse HEAD
git submodule status
git diff HEAD --submodule=log
~~~

Hash trong gitlink của HEAD phải trùng với HEAD của submodule nếu working tree đang checkout đúng commit đã ghi nhận. Nếu có dấu + trong git submodule status, working tree submodule đang ở commit khác với gitlink hiện tại.

Kiểm tra commit gitlink được stage trước khi commit:

~~~bash
git ls-files --stage -- libs/common
git diff --cached --submodule=log
~~~

Entry stage của submodule có mode 160000. Sau khi commit superproject, dùng git ls-tree HEAD để xác minh gitlink đã được ghi vào commit.

Kiểm tra remote superproject:

~~~bash
git fetch origin
git log -1 --oneline --decorate origin/main
git ls-tree origin/main -- libs/common
~~~

Hash gitlink trên origin/main phải là commit mà nhóm muốn phát hành. Để xác minh remote kho con có thể cung cấp commit đó, kiểm tra remote refs của submodule hoặc thử fetch branch/tag chứa commit trong một clone kiểm thử.

## 11. Khi cập nhật submodule gây xung đột

Nếu hai branch superproject cùng thay đổi gitlink của một submodule, merge hoặc rebase kho cha có thể báo xung đột ở đường dẫn submodule.

Kiểm tra:

~~~bash
git status
git diff --submodule
git ls-files -u -- libs/common
~~~

Index có thể chứa nhiều stage cho gitlink, tương ứng các phiên bản base, ours và theirs. Xác định commit nào cần dùng bằng cách kiểm tra lịch sử trong repository submodule:

~~~bash
git -C libs/common show --no-patch --oneline <ours-commit>
git -C libs/common show --no-patch --oneline <theirs-commit>
~~~

Nếu cần kết hợp hai dòng phát triển, thực hiện merge hoặc rebase trong repository submodule theo quy trình của kho con, commit kết quả ở đó và push commit mới lên remote. Sau đó checkout commit kết quả trong submodule và stage lại gitlink ở superproject:

~~~bash
git add -- libs/common
git diff --cached --submodule=log
~~~

Không chọn một hash gitlink chỉ vì nó nằm ở stage 2 hoặc stage 3. Hãy kiểm tra nội dung và lịch sử của commit trong kho con trước khi quyết định.

## 12. Cập nhật submodule sau khi pull superproject

Khi pull superproject, Git cập nhật gitlink trong branch cha. Working tree submodule có thể vẫn ở commit cũ cho đến khi chạy update.

~~~bash
git pull --ff-only
git submodule update --init --recursive
~~~

Lệnh update checkout đúng commit được superproject ghim. Đây là hành vi cần thiết để mọi thành viên dùng cùng phiên bản dependency.

Nếu muốn cập nhật submodule lên remote branch mới nhất thay vì commit đang ghim:

~~~bash
git submodule update --remote --recursive
~~~

Sau thao tác --remote, nếu commit mới khác gitlink của superproject, hãy review và commit thay đổi gitlink như một thay đổi dependency có chủ đích. Không chạy --remote chỉ để “đồng bộ cho mới” nếu dự án yêu cầu build tái lập theo commit đã ghim.

Để clone superproject và khởi tạo tất cả submodule ngay từ đầu:

~~~bash
git clone --recurse-submodules <superproject-url>
~~~

Nếu đã clone mà chưa khởi tạo submodule:

~~~bash
git submodule update --init --recursive
~~~

## 13. Cập nhật URL submodule và đồng bộ cấu hình local

Khi URL trong .gitmodules thay đổi, superproject có thể đã lưu URL mới nhưng cấu hình local của người dùng vẫn còn URL cũ. Đồng bộ:

~~~bash
git submodule sync --recursive
git submodule update --init --recursive
~~~

sync cập nhật URL trong cấu hình local của submodule theo .gitmodules. Nó không thay thế thao tác commit thay đổi .gitmodules trong superproject.

Kiểm tra URL:

~~~bash
git config --file .gitmodules --get submodule.libs/common.url
git -C libs/common remote -v
~~~

Nếu URL chứa credential, không đưa output nhạy cảm vào log chia sẻ. Nên dùng credential manager hoặc cơ chế xác thực riêng thay vì nhúng token vào URL được commit.

## 14. Những lỗi thường gặp

### Superproject đã push nhưng người khác không lấy được submodule commit

Nguyên nhân thường là gitlink trỏ đến commit chỉ tồn tại local hoặc chưa được đẩy lên remote mà người dùng có quyền truy cập. Kiểm tra hash gitlink, remote submodule và branch/tag chứa commit. Push kho con trước, rồi xác nhận lại khả năng fetch.

### git submodule update --remote không cập nhật gitlink trong commit cha

Đây là hành vi bình thường. Lệnh cập nhật working tree submodule theo remote branch. Muốn ghi nhận commit mới trong superproject, chạy git add -- <submodule-path>, xem diff và commit kho cha.

### Submodule chuyển sang detached HEAD sau update

Đây là mặc định thường gặp của git submodule update. Git checkout commit được ghim, không nhất thiết checkout một branch. Nếu cần phát triển tiếp, tạo hoặc checkout branch phù hợp trong repository submodule.

### git push của superproject không đẩy commit submodule

Push thông thường chỉ đẩy refs của superproject. Dùng --recurse-submodules=on-demand hoặc push submodule riêng trước. Đừng giả định việc push kho cha sẽ tự gửi object của kho con.

### Không thể tạo branch trong submodule vì branch đang được checkout ở worktree khác

Submodule cũng có thể sử dụng linked worktree hoặc branch đã được checkout ở nơi khác. Kiểm tra branch và worktree trong chính repository submodule, sau đó chọn branch khác hoặc detached HEAD theo mục đích.

### .gitmodules có branch stable nhưng submodule vẫn đang ở commit cũ

Trường branch chỉ định nguồn mà --remote dùng để tìm commit. Nó không tự cập nhật gitlink khi bạn checkout hoặc pull superproject. Hãy chạy update --remote, review commit mới và commit gitlink trong kho cha.

## 15. Checklist trước khi đẩy superproject

Trước khi push branch superproject có thay đổi submodule, xác nhận:

- Submodule đang checkout đúng commit dự kiến.
- Thay đổi bên trong submodule đã được commit.
- Commit submodule đã có trên remote mà đồng đội/CI có thể truy cập, hoặc push recurse on-demand đã thành công.
- Branch/tag chứa commit submodule đã được công bố và không chỉ tồn tại trong repository local.
- Gitlink đã được stage trong superproject.
- git diff --cached --submodule=log cho thấy đúng commit cũ và mới.
- Commit superproject đã ghi nhận gitlink mới.
- Remote superproject sau push trỏ đến đúng hash gitlink.
- Người khác có thể chạy git submodule update --init --recursive để lấy đúng phiên bản.

Nếu một điều kiện chưa đạt, dừng push superproject và xử lý kho con trước.

## 16. Tự kiểm tra

Superproject đang ghim libs/common ở commit C. Bạn sửa kho con, tạo commit D trên branch fix/api-response, rồi stage libs/common và tạo commit P trong superproject. Commit D hiện chỉ có ở máy bạn; branch fix/api-response chưa được push.

Hãy trả lời:

1. Gitlink trong commit P lưu nội dung các file của libs/common hay chỉ lưu hash commit?
2. Vì sao đồng đội có thể gặp lỗi khi checkout P?
3. Lệnh nào push branch chứa D lên remote kho con?
4. Sau khi push kho con, cần kiểm tra và đẩy phần nào của superproject?
5. git submodule update --init và git submodule update --remote khác nhau thế nào?
6. Chế độ push.recurseSubmodules=check và on-demand khác nhau ra sao?

**Gợi ý:** Gitlink lưu hash commit D, không lưu nội dung file kho con. Nếu D chưa có trên remote, người khác có thể không tải được commit mà P yêu cầu. Push branch fix/api-response của submodule trước, xác minh remote chứa D, rồi stage/commit/push gitlink của superproject. update --init đưa submodule về commit được superproject ghim; update --remote fetch và cập nhật theo branch remote đã cấu hình. check chặn push nếu commit submodule chưa có trên remote; on-demand yêu cầu Git push các submodule cần thiết trước khi hoàn tất push kho cha.

## Kết luận

Superproject ghi nhận phiên bản submodule bằng gitlink trỏ đến một commit cụ thể. Lệnh update thông thường đồng bộ working tree về commit được ghim; update --remote lấy commit theo branch trên remote và chỉ tạo thay đổi gitlink khi bạn stage, commit trong kho cha. Khi có commit mới ở submodule, hãy commit và push kho con trước, xác minh remote có thể cung cấp commit, rồi mới commit và push superproject. Dùng push.recurseSubmodules=check hoặc on-demand để hỗ trợ kiểm tra thứ tự, đồng thời xác minh gitlink và trạng thái submodule trước khi chia sẻ thay đổi.
