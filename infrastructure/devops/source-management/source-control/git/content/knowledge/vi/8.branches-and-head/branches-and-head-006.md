# Giữ kết quả thử nghiệm khi đang ở detached HEAD

Detached HEAD là trạng thái Git checkout trực tiếp một commit thay vì đứng trên một branch. Bạn vẫn có thể đọc code, chạy thử nghiệm, sửa file và tạo commit. Điểm cần chú ý là khi tạo commit trong trạng thái này, HEAD di chuyển theo commit mới nhưng không có branch thông thường nào tự cập nhật để giữ kết quả. Nếu chuyển sang branch khác mà chưa tạo một ref lưu commit thử nghiệm, bạn có thể khó tìm lại kết quả sau đó.

Trong chương **Nhánh và HEAD** của module **SOURCE_CONTROL_GIT**, bài học này hướng dẫn cách nhận biết detached HEAD và bảo toàn công việc trước khi rời trạng thái đó. Bạn sẽ biết cách tạo branch ngay tại commit đang thử nghiệm, lưu thay đổi chưa commit bằng stash, tìm commit đã bị bỏ lại bằng reflog và chọn quy trình phù hợp để tiếp tục, chia sẻ hoặc loại bỏ thử nghiệm.

Sau bài học, bạn có thể:

- Giải thích HEAD hoạt động thế nào trong trạng thái attached và detached.
- Nhận biết detached HEAD bằng git status, git branch và git symbolic-ref.
- Tạo commit khi đang detached và hiểu vì sao branch hiện tại không tự di chuyển.
- Tạo branch tại commit thử nghiệm để giữ toàn bộ kết quả.
- Bảo toàn thay đổi chưa commit bằng branch hoặc stash.
- Phục hồi commit sau khi đã rời detached HEAD bằng reflog.
- Phân biệt commit còn được ref giữ với commit chỉ còn trong reflog.
- Chọn cách tiếp tục thử nghiệm, chia sẻ kết quả hoặc quay về branch làm việc an toàn.

## 1. HEAD bình thường trỏ đến đâu?

HEAD là tham chiếu cho biết vị trí checkout hiện tại. Trong trạng thái thông thường, HEAD là symbolic ref trỏ đến branch đang làm việc.

Ví dụ khi bạn đang ở branch main:

~~~text
HEAD
  |
  v
refs/heads/main
  |
  v
commit C
~~~

Nội dung HEAD về mặt logic tương đương:

~~~text
ref: refs/heads/main
~~~

Khi bạn tạo commit mới trên main, Git cập nhật ref refs/heads/main để trỏ đến commit mới. HEAD vẫn trỏ đến branch main; vì branch di chuyển nên vị trí commit hiện tại cũng thay đổi.

Kiểm tra HEAD đang gắn với branch nào:

~~~bash
git branch --show-current
git symbolic-ref --short HEAD
~~~

Nếu đang ở main, các lệnh thường trả về main. Lệnh symbolic-ref đọc symbolic ref; nó sẽ thất bại nếu HEAD đang detached.

## 2. Detached HEAD là gì?

Detached HEAD xảy ra khi HEAD trỏ trực tiếp đến một commit thay vì trỏ đến branch. Trạng thái này thường xuất hiện khi bạn checkout:

- Một commit hash cụ thể.
- Một tag như v2.0.0.
- Một remote-tracking branch như origin/main.
- Một revision expression như HEAD~2.

Ví dụ:

~~~bash
git switch --detach v2.0.0
~~~

HEAD lúc này trỏ trực tiếp đến commit mà tag v2.0.0 phân giải tới:

~~~text
HEAD
  |
  v
commit C  <--- tag v2.0.0

refs/heads/main ---> commit D
~~~

Branch main không bị di chuyển. Tag v2.0.0 cũng không thay đổi. Bạn đang xem snapshot tại commit C mà không đứng trên một branch local.

Detached HEAD là trạng thái hợp lệ, không phải lỗi hoặc repository bị hỏng. Nó hữu ích khi review một release, chạy kiểm thử tại một commit cụ thể, so sánh phiên bản hoặc thử nghiệm độc lập.

## 3. Nhận biết detached HEAD

Chạy:

~~~bash
git status
git branch --show-current
git rev-parse --short HEAD
git symbolic-ref -q HEAD
~~~

Các dấu hiệu thường gặp:

- git status hiển thị thông báo như HEAD detached at v2.0.0.
- git branch --show-current không in tên branch.
- git rev-parse HEAD vẫn in object ID của commit hiện tại.
- git symbolic-ref -q HEAD trả mã khác 0 vì HEAD không phải symbolic ref.

Để xem branch và vị trí HEAD:

~~~bash
git branch --all --verbose
git log -1 --oneline --decorate
~~~

Trong output log, HEAD có thể được hiển thị cạnh tag hoặc commit hash thay vì tên branch local.

Không nên chỉ dựa vào việc git branch đánh dấu branch nào bằng dấu sao rồi kết luận bạn đang ở branch đó. Trong detached state, dấu sao có thể không xuất hiện cạnh branch local nào.

## 4. Bạn vẫn có thể sửa file và tạo commit khi detached

Detached HEAD không khóa repository ở chế độ chỉ đọc. Bạn có thể:

- Sửa file trong working tree.
- Stage thay đổi bằng git add.
- Tạo commit bằng git commit.
- Tạo tag hoặc chạy các lệnh kiểm tra khác.

Ví dụ:

~~~bash
git switch --detach v2.0.0
git status --short

# Chỉnh sửa source và test
git add src/parser.js test/parser.test.js
git commit -m "experiment: improve parser for legacy input"
~~~

Sau commit, HEAD di chuyển đến commit mới, nhưng không có branch local nào tự được cập nhật:

~~~text
Trước commit:

tag v2.0.0 ---> C <--- HEAD
main --------> D

Sau commit:

tag v2.0.0 ---> C
                 |
                 v
                 E <--- HEAD
main ------------> D
~~~

Commit E tồn tại và có parent là C. Bạn vẫn có thể xem nó bằng git log hoặc git show khi HEAD đang ở đó. Tuy nhiên, khi chuyển sang main, không có branch tên riêng nào giữ E. Nếu không còn ref nào trỏ đến E hoặc commit con của nó, commit có thể trở thành unreachable sau khi HEAD rời đi.

## 5. Cách an toàn nhất: tạo branch để giữ kết quả

Nếu thử nghiệm có giá trị và bạn muốn tiếp tục phát triển, hãy tạo branch tại vị trí hiện tại trước khi rời detached HEAD.

### Tạo branch ngay tại commit đang checkout

~~~bash
git switch -c experiment/parser-v2
~~~

Lệnh này tạo branch mới bắt đầu từ commit hiện tại và chuyển HEAD sang branch đó. Nếu bạn đã tạo một hoặc nhiều commit khi detached, branch mới sẽ giữ cả chuỗi commit đến HEAD hiện tại.

Sau lệnh:

~~~text
HEAD
  |
  v
refs/heads/experiment/parser-v2
  |
  v
commit E
  |
  v
commit C
~~~

Từ đây, các commit tiếp theo sẽ di chuyển branch experiment/parser-v2 như bình thường.

Xác minh:

~~~bash
git status -sb
git branch --show-current
git log --oneline --decorate -5
~~~

### Tạo branch rồi mới chuyển sang branch đó

Hai lệnh sau cũng có tác dụng tương đương:

~~~bash
git branch experiment/parser-v2
git switch experiment/parser-v2
~~~

Lệnh git branch tạo ref tại commit hiện tại nhưng chưa chuyển HEAD. Lệnh git switch sau đó đưa HEAD sang branch vừa tạo.

Nếu chỉ chạy git branch mà vẫn ở detached HEAD, HEAD vẫn trỏ trực tiếp đến commit. Branch mới đã giữ commit, nhưng muốn tiếp tục làm việc theo branch thì cần switch sang branch đó.

### Tạo branch từ commit cụ thể

Nếu bạn đã có OID của commit cần giữ:

~~~bash
git switch -c rescue/parser-experiment <commit-oid>
~~~

Hoặc:

~~~bash
git branch rescue/parser-experiment <commit-oid>
git switch rescue/parser-experiment
~~~

Kiểm tra OID trước khi tạo branch:

~~~bash
git show --stat --oneline <commit-oid>
~~~

Không đoán commit từ một hash prefix quá ngắn; hãy dùng OID đầy đủ hoặc xác minh prefix phân giải duy nhất.

## 6. Tạo branch trước khi bắt đầu thử nghiệm

Nếu bạn biết trước rằng sẽ chỉnh sửa và có thể commit, cách gọn nhất là tạo branch ngay sau khi checkout commit/tag:

~~~bash
git status -sb
git switch --detach v2.0.0
git switch -c experiment/parser-v2
~~~

Hãy bắt đầu từ working tree sạch hoặc lưu riêng những thay đổi đang có trước khi checkout tag. Nếu repository đang có chỉnh sửa chưa commit, thao tác chuyển sang tag có thể bị Git từ chối hoặc mang theo các thay đổi nếu không ghi đè file.

Sau đó sửa file, stage và commit:

~~~bash
git add -- src/parser.js test/parser.test.js
git commit -m "experiment: improve parser for legacy input"
~~~

Khi đó HEAD đã attached vào experiment/parser-v2. Bạn không cần nhớ tạo branch sau khi thử nghiệm xong.

Nếu mục tiêu chỉ là kiểm tra nhanh và không dự định lưu commit, có thể giữ detached HEAD trong lúc review. Nhưng trước khi tạo commit có giá trị, hãy tạo branch hoặc ghi lại cách giữ commit.

## 7. Bảo toàn thay đổi chưa commit

Không phải thử nghiệm nào cũng đã có commit. Có thể bạn đang ở detached HEAD và mới sửa file, stage một phần hoặc tạo file mới.

Kiểm tra trạng thái:

~~~bash
git status --short
git diff
git diff --cached
~~~

Nếu thay đổi thuộc về thử nghiệm, bạn có thể tạo branch ngay tại HEAD hiện tại:

~~~bash
git switch -c experiment/parser-v2
~~~

Các thay đổi trong working tree và index thường được giữ nguyên khi tạo branch từ đúng commit hiện tại, vì branch mới không yêu cầu thay đổi snapshot checkout. Kiểm tra lại status sau khi switch.

Nếu cần rời sang một branch có nội dung khác, Git có thể từ chối switch khi thao tác sẽ ghi đè thay đổi local. Đừng ép chuyển branch khi chưa lưu phần việc cần giữ.

### Dùng stash khi cần chuyển đi tạm thời

Nếu bạn muốn tạm cất thay đổi chưa commit:

~~~bash
git stash push -u -m "detached-head parser experiment"
~~~

- git stash push lưu các thay đổi tracked.
- -u (hoặc --include-untracked) đưa cả file untracked vào stash.
- File ignored không được đưa vào theo mặc định.

Nếu thực sự cần lưu cả file ignored, Git có tùy chọn -a, nhưng hãy xem kỹ vì nó có thể đưa cả build output hoặc file lớn vào stash:

~~~bash
git stash push -a -m "detached-head experiment including ignored files"
~~~

Sau khi stash, kiểm tra:

~~~bash
git stash list
git status --short
~~~

Bạn có thể chuyển sang branch khác và áp dụng lại:

~~~bash
git stash apply 'stash@{0}'
~~~

Ưu tiên apply khi chưa chắc kết quả vì stash vẫn được giữ lại. Sau khi kiểm tra file và xác nhận công việc đã được phục hồi đầy đủ, mới xóa stash nếu không còn cần:

~~~bash
git stash drop 'stash@{0}'
~~~

git stash pop vừa áp dụng vừa cố gắng xóa stash nếu áp dụng thành công. Nếu có conflict, stash thường được giữ lại để bạn xử lý. Dù dùng apply hay pop, hãy kiểm tra trạng thái và nội dung sau khi áp dụng.

Nếu muốn tạo branch ngay từ commit nền nơi stash được tạo rồi áp dụng thay đổi lên branch đó, có thể dùng:

~~~bash
git stash branch experiment/parser-stashed 'stash@{0}'
~~~

Lệnh này tạo và chuyển sang branch từ commit nền của stash, sau đó áp dụng nội dung stash. Khi áp dụng thành công, stash entry được xóa. Cách này hữu ích nếu stash được tạo khi detached HEAD và bạn muốn tiếp tục thử nghiệm từ đúng commit gốc; vẫn cần kiểm tra status và diff sau lệnh.

Stash phù hợp với thay đổi chưa commit và việc chuyển chỗ làm tạm thời. Nếu đã tạo commit thử nghiệm, tạo branch để giữ commit sẽ rõ ràng và bền vững hơn.

## 8. Rời detached HEAD mà không mất kết quả

Trước khi chuyển về branch chính, hãy kiểm tra xem đã có commit thử nghiệm nào cần giữ chưa.

~~~bash
git status --short
git log --oneline --decorate -5
git rev-parse HEAD
~~~

Nếu đã tạo commit cần giữ, tạo branch:

~~~bash
git switch -c experiment/parser-v2
~~~

Sau đó mới chuyển sang branch khác:

~~~bash
git switch main
~~~

Nếu chưa tạo commit nhưng thay đổi cần giữ, bạn có thể tạo branch ngay tại HEAD rồi tiếp tục chỉnh sửa, hoặc stash trước khi chuyển branch.

Nếu thử nghiệm không cần giữ, xác nhận không còn thay đổi chưa commit và không có commit cần bảo toàn rồi mới rời detached HEAD. Đừng nhầm việc chuyển branch thành thao tác xóa commit ngay lập tức; commit có thể vẫn còn trong reflog một thời gian, nhưng không nên dựa vào đó như cách lưu trữ chính.

## 9. Đã rời detached HEAD rồi mới nhớ ra commit thử nghiệm

Nếu bạn đã chạy git switch main và sau đó nhớ ra một commit được tạo trong detached HEAD, hãy tìm commit qua reflog.

### Bước 1: xem lịch sử HEAD

~~~bash
git reflog --date=local -n 20
~~~

Ví dụ:

~~~text
d7a8b9c HEAD@{0}: checkout: moving from e5f6a7b to main
e5f6a7b HEAD@{1}: commit: experiment: improve parser
c3d4e5f HEAD@{2}: checkout: moving from main to v2.0.0
...
~~~

Tìm dòng commit thử nghiệm và ghi lại OID của nó. Nội dung thực tế sẽ khác tùy lịch sử thao tác.

### Bước 2: kiểm tra commit tìm được

~~~bash
git show --stat --oneline <commit-oid>
git log --oneline --decorate -5 <commit-oid>
~~~

Xác nhận đây đúng là kết quả thử nghiệm, không phải commit khác có thông điệp tương tự.

### Bước 3: tạo branch cứu hộ

~~~bash
git branch rescue/parser-experiment <commit-oid>
~~~

Branch rescue/parser-experiment giữ commit và các commit cha của nó khỏi bị xem là không còn được tham chiếu.

### Bước 4: chuyển sang branch cứu hộ

~~~bash
git switch rescue/parser-experiment
git status -sb
git log --oneline --decorate -5
~~~

Giờ bạn có thể tiếp tục làm việc, so sánh với main hoặc tạo pull request.

Không nên dựa vào HEAD@{1} một cách máy móc. Sau vài thao tác checkout hoặc reset, vị trí reflog thay đổi. Hãy đọc thông điệp và OID của từng dòng rồi xác minh bằng git show.

## 10. Reflog giữ commit được bao lâu?

Reflog là lịch sử thay đổi ref ở local. Nó thường giúp tìm lại commit sau amend, reset, checkout hoặc khi rời detached HEAD. Tuy nhiên:

- Reflog không được push lên remote.
- Mỗi repository hoặc worktree có reflog riêng theo cấu trúc lưu trữ.
- Entry reflog có thể hết hạn theo cấu hình.
- Garbage collection có thể dọn object không còn được ref nào giữ sau khi các điều kiện hết hạn thỏa mãn.

Kiểm tra cấu hình thời hạn:

~~~bash
git config --show-origin --get gc.reflogExpire
git config --show-origin --get gc.reflogExpireUnreachable
~~~

Giá trị mặc định phụ thuộc phiên bản và cấu hình; không nên xem reflog là nơi lưu giữ vĩnh viễn.

Một khi tìm được commit cần giữ, hãy tạo branch hoặc tag phù hợp. Ref mới là cách rõ ràng để bảo toàn kết quả trong repository.

## 11. Chia sẻ kết quả thử nghiệm

Sau khi đã tạo branch giữ kết quả, bạn có thể push branch lên remote:

~~~bash
git push -u origin experiment/parser-v2
~~~

Lệnh này tạo branch trên remote và thiết lập upstream cho branch local nếu push thành công.

Trước khi push, kiểm tra:

~~~bash
git status -sb
git log --oneline --decorate --graph -10
git remote -v
~~~

Nếu thử nghiệm bắt đầu từ một tag cũ, branch mới vẫn chứa lịch sử bắt đầu từ commit tag đó. Điều này giúp người review hiểu rõ thử nghiệm dựa trên phiên bản nào.

Không push trực tiếp một detached HEAD bằng cách dựa vào trạng thái tạm thời. Hãy tạo branch có tên mô tả mục đích rồi push branch đó. Tên branch giúp người khác tham chiếu, review và tiếp tục công việc dễ dàng.

## 12. Phân biệt checkout tag, remote branch và local branch

Ba thao tác sau có thể dẫn đến trạng thái khác nhau:

~~~bash
git switch main
git switch --detach v2.0.0
git switch --detach origin/main
~~~

- git switch main chuyển sang branch local main; HEAD attached.
- git switch --detach v2.0.0 checkout commit mà tag trỏ tới; HEAD detached.
- git switch --detach origin/main checkout commit của remote-tracking branch; HEAD detached.

Nếu muốn tiếp tục phát triển từ remote-tracking branch, tạo local branch theo dõi nó:

~~~bash
git switch -c feature/api --track origin/feature/api
~~~

Nếu muốn thử nghiệm độc lập tại tag, detached HEAD là lựa chọn phù hợp. Khi kết quả cần được giữ, tạo branch từ commit hiện tại.

## 13. Detached HEAD trong linked worktree

Một linked worktree có thể được tạo trực tiếp ở một commit:

~~~bash
git worktree add --detach ../repo-review v2.0.0
~~~

Worktree mới bắt đầu ở detached HEAD. Cách này hữu ích để review hoặc kiểm thử phiên bản cũ trong thư mục riêng mà không cần thay đổi branch đang làm việc ở worktree chính.

Nếu cần giữ kết quả thử nghiệm trong worktree đó, tạo branch ngay trong worktree:

~~~bash
git -C ../repo-review switch -c experiment/review-v2
~~~

Branch mới sẽ giữ commit tại điểm thử nghiệm. Git thường không cho cùng một branch được checkout đồng thời trong hai linked worktree; nếu branch đã được dùng ở nơi khác, chọn tên branch khác hoặc xử lý worktree đang giữ branch đó theo quy trình.

## 14. Quy trình hoàn chỉnh: thử nghiệm một release cũ

Giả sử bạn cần kiểm tra một lỗi chỉ xuất hiện trên tag v2.4.0 và muốn giữ bản sửa nếu thử nghiệm thành công.

### Bước 1: xác nhận repository sạch

~~~bash
git status -sb
~~~

Nếu có thay đổi cần giữ, commit, tạo branch hoặc stash trước khi checkout tag.

### Bước 2: checkout tag ở detached HEAD

~~~bash
git switch --detach v2.4.0
git status
git log -1 --oneline --decorate
~~~

Xác nhận đang ở đúng commit phát hành.

### Bước 3: tạo branch thử nghiệm ngay

~~~bash
git switch -c experiment/fix-v2.4
~~~

Từ đây HEAD attached vào branch experiment/fix-v2.4.

### Bước 4: sửa và commit

~~~bash
git add -- src/legacy-parser.js test/legacy-parser.test.js
git diff --cached
git commit -m "fix(parser): handle legacy escape sequence"
~~~

### Bước 5: xác minh kết quả

~~~bash
git status -sb
git log --oneline --decorate --graph -5
git show --stat --oneline HEAD
~~~

### Bước 6: chia sẻ nếu cần

~~~bash
git push -u origin experiment/fix-v2.4
~~~

Branch thử nghiệm hiện được giữ bằng ref local và remote. Bạn có thể mở pull request hoặc tiếp tục review mà không phụ thuộc vào reflog.

## 15. Những nhầm lẫn thường gặp

### Detached HEAD có nghĩa là Git đã mất branch?

Không. Branch vẫn tồn tại và vẫn trỏ đến commit của nó. Chỉ có HEAD không gắn với branch trong thời điểm hiện tại.

### Có thể tạo commit khi detached HEAD không?

Có. Commit mới được tạo bình thường và HEAD trỏ trực tiếp đến commit mới. Branch local không tự di chuyển.

### Chỉ cần nhớ commit hash là đủ?

Hash giúp tìm commit nếu object còn tồn tại, nhưng không phải ref giữ commit lâu dài. Hãy tạo branch hoặc tag để bảo toàn kết quả.

### Tạo branch sau khi commit detached có giữ cả chuỗi commit?

Có. Nếu tạo branch tại HEAD hiện tại, branch giữ commit đó và toàn bộ tổ tiên của nó. Ví dụ git switch -c experiment/save-results.

### Stash có lưu file untracked không?

Mặc định không. Dùng git stash push -u để thêm file untracked. File ignored cần tùy chọn -a và nên được cân nhắc kỹ.

### Rời detached HEAD là commit bị xóa ngay?

Không. Commit có thể còn trong reflog và object database một thời gian. Tuy nhiên, nếu không có ref giữ nó, commit có nguy cơ bị dọn sau này.

### Reflog có được chia sẻ qua push không?

Không. Reflog là dữ liệu local. Muốn chia sẻ commit, tạo branch/tag rồi push ref đó.

## 16. Tự kiểm tra

Bạn checkout tag v3.1.0 bằng:

~~~bash
git switch --detach v3.1.0
~~~

Sau đó sửa code, tạo hai commit thử nghiệm E1 và E2. Bạn chạy git switch main để quay lại công việc chính, rồi nhận ra chưa giữ kết quả thử nghiệm bằng branch.

Hãy trả lời:

1. Vì sao HEAD được gọi là detached sau khi checkout tag?
2. Hai commit E1 và E2 có bị xóa ngay khi switch main không?
3. Lệnh nào tìm lại OID của commit thử nghiệm?
4. Lệnh nào tạo branch rescue trỏ đến E2?
5. Nếu vẫn đang ở detached HEAD tại E2, lệnh nào tạo branch và chuyển HEAD cùng lúc?
6. Nếu có thay đổi chưa commit và file untracked, lệnh stash nào lưu cả hai loại?
7. Vì sao branch phù hợp hơn reflog để giữ kết quả lâu dài và chia sẻ với đồng đội?

**Gợi ý:** HEAD trỏ trực tiếp đến commit tag thay vì branch. Các commit detached không bị xóa ngay nhưng có thể trở thành unreachable sau khi chuyển đi. Dùng git reflog để tìm OID E2, kiểm tra bằng git show, rồi git branch rescue/experiment <OID> hoặc git switch -c rescue/experiment khi vẫn ở E2. Dùng git stash push -u để lưu thay đổi tracked và untracked. Branch là ref có tên, được giữ trong repository và có thể push lên remote; reflog chỉ là lịch sử local có thời hạn.

## Kết luận

Detached HEAD là trạng thái HEAD trỏ trực tiếp đến một commit thay vì một branch. Bạn vẫn có thể sửa file và tạo commit, nhưng branch local không tự giữ các commit mới đó. Khi kết quả thử nghiệm có giá trị, hãy tạo branch tại HEAD hiện tại bằng git switch -c trước khi rời đi. Nếu chỉ có thay đổi chưa commit, tạo branch để tiếp tục hoặc stash với -u khi cần cất cả file untracked. Nếu đã chuyển đi, dùng reflog tìm commit, xác minh OID rồi tạo branch cứu hộ. Reflog giúp phục hồi trong ngắn hạn; branch hoặc tag mới là cách rõ ràng để giữ và chia sẻ kết quả lâu dài.
