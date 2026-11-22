# Git reset --hard và điều kiện bảo vệ thay đổi chưa commit

Lệnh **git reset --hard** đưa nhánh hiện tại (hoặc HEAD đang detached) về một commit đích, đồng thời cập nhật staging area và working tree theo commit đó. Đây là thao tác mạnh: các thay đổi đã stage và chưa stage trên những file được Git theo dõi có thể bị loại bỏ khỏi working tree. Nếu chưa kiểm tra trạng thái repository và chưa bảo vệ phần công việc cần giữ, bạn có thể mất những chỉnh sửa chưa commit.

Trong chương **Chuyển và hoàn tác** của module **SOURCE_CONTROL_GIT**, bài học này tập trung vào cách hiểu chính xác tác động của reset hard và những điều kiện cần xác nhận trước khi chạy. Mục tiêu là biết lúc nào có thể dùng lệnh để đưa repository về trạng thái mong muốn, cách bảo vệ thay đổi đang làm dở, và cách xử lý khi lỡ reset nhầm.

Sau bài học, bạn có thể:

- Giải thích reset hard thay đổi HEAD, index và working tree như thế nào.
- Phân biệt commit đã lưu, thay đổi đã stage, thay đổi chưa stage, file chưa được theo dõi và file bị ignore.
- Kiểm tra trạng thái repository trước khi reset.
- Bảo vệ công việc bằng commit, stash hoặc bản sao phù hợp.
- Chọn commit đích và xác minh kết quả sau khi reset.
- Nhận biết giới hạn phục hồi khi đã chạy reset nhầm.

## 1. Ba khu vực cần hiểu trước khi reset

Git làm việc với ba khu vực chính:

1. **HEAD và lịch sử commit**: HEAD thường trỏ đến commit hiện tại thông qua nhánh đang checkout. Commit lưu một snapshot của nội dung được ghi nhận tại thời điểm commit.
2. **Index (staging area)**: nơi chứa nội dung sẽ được đưa vào commit tiếp theo. Một file có thể có phiên bản đã stage khác với nội dung hiện tại trong working tree.
3. **Working tree**: các file và thư mục đang hiển thị trong thư mục làm việc. Đây là nơi bạn chỉnh sửa mã nguồn và tài liệu.

Ngoài ba khu vực này còn có file **untracked** chưa được Git quản lý và file **ignored** bị quy tắc ignore loại khỏi trạng thái thông thường. Hai loại file này không phải là commit hoặc nội dung trong index.

Ví dụ, sau khi chỉnh sửa một file và stage một phần:

~~~text
HEAD (commit A)
       |
       v
Index:       phiên bản đã stage
Working tree: phiên bản mới nhất đang chỉnh sửa
Untracked:   file mới chưa được Git theo dõi
~~~

Trước khi chạy một lệnh reset, hãy xác định thay đổi nào đang nằm ở từng khu vực. Một trạng thái git status có thể cho biết file đã sửa, đã stage hoặc chưa được theo dõi; các lệnh diff giúp đọc chính xác nội dung khác nhau.

## 2. git reset --hard tác động lên những gì?

Cú pháp tổng quát:

~~~bash
git reset --hard <commit>
~~~

Git thực hiện ba việc chính:

- Di chuyển HEAD và nhánh hiện tại đến commit đích.
- Làm cho index khớp với snapshot của commit đích.
- Cập nhật working tree để khớp với index đó.

Kết quả là trạng thái tracked trong index và working tree được đưa về commit đích. Thay đổi đã stage hoặc chưa stage trên các file tracked sẽ bị thay thế bởi nội dung của commit đích.

Ví dụ, nhánh hiện tại đang ở commit C và muốn đưa về B:

~~~text
Trước:
A---B---C  (HEAD -> feature)

Sau git reset --hard B:
A---B      (HEAD -> feature)
     \
      C    (không còn được nhánh feature trỏ tới)
~~~

Nhánh feature giờ trỏ đến B. Commit C không còn nằm trên lịch sử có thể đi tới từ nhánh đó, nhưng có thể vẫn tìm được qua reflog trong một khoảng thời gian. Reset không xóa ngay mọi dữ liệu của commit C khỏi kho đối tượng Git.

Nếu chạy không ghi commit đích:

~~~bash
git reset --hard
~~~

Git dùng HEAD hiện tại làm đích. Lệnh này không di chuyển nhánh sang commit khác, nhưng vẫn làm index và working tree khớp với HEAD. Do đó, các thay đổi tracked đã stage và chưa stage có thể bị loại bỏ.

**Điểm quan trọng:** reset không chuyển sang một nhánh khác. Nó di chuyển tham chiếu hiện tại (khi HEAD đang gắn với nhánh) và cập nhật nội dung làm việc theo commit đích. Nếu HEAD đang detached, nó cập nhật HEAD detached.

## 3. Phân biệt reset --soft, --mixed và --hard

Ba chế độ reset khác nhau ở cách xử lý index và working tree:

| Chế độ | Di chuyển HEAD/nhánh | Cập nhật index | Cập nhật working tree |
| --- | --- | --- | --- |
| --soft | Có | Giữ nguyên | Giữ nguyên |
| --mixed | Có | Đưa về commit đích | Giữ thay đổi trong file |
| --hard | Có | Đưa về commit đích | Đưa về commit đích |

Nếu không chỉ định chế độ, git reset mặc định dùng --mixed.

Ví dụ nhánh hiện tại đang ở C, muốn quay về B:

~~~bash
git reset --soft B
~~~

Commit C bị bỏ khỏi đầu nhánh hiện tại, nhưng thay đổi của commit C vẫn nằm trong index và working tree. Chúng sẵn sàng để tạo một commit khác.

~~~bash
git reset --mixed B
~~~

Commit C bị bỏ khỏi đầu nhánh hiện tại. Index trở về B, còn thay đổi được giữ trong working tree dưới dạng chưa stage. Đây là cách thường dùng khi muốn sửa lại nội dung hoặc chia lại staging trước khi commit.

~~~bash
git reset --hard B
~~~

Commit C bị bỏ khỏi đầu nhánh hiện tại, index và working tree đều được đưa về B. Những thay đổi tracked chưa commit không còn trong working tree.

Hãy chọn chế độ theo kết quả mong muốn. Nếu chỉ muốn bỏ stage một file mà vẫn giữ chỉnh sửa trong working tree, dùng git restore --staged <file> thường rõ ràng hơn reset toàn bộ nhánh. Nếu muốn bỏ thay đổi trong working tree của một file, có thể dùng git restore <file> sau khi đã xác nhận không cần nội dung đó.

## 4. Những thay đổi nào có nguy cơ bị mất?

Không phải mọi loại file đều được xử lý giống nhau khi chạy reset hard.

| Loại nội dung | Tác động thường gặp của git reset --hard |
| --- | --- |
| Commit đã được tạo | Nhánh hiện tại có thể bị di chuyển khỏi commit đó nếu commit đích cũ hơn. Commit vẫn có thể phục hồi qua reflog trong thời gian còn lưu. |
| Thay đổi tracked đã stage | Index và working tree được đưa về commit đích; nội dung chưa commit có thể mất. |
| Thay đổi tracked chưa stage | Working tree được cập nhật theo commit đích; nội dung chưa commit có thể mất. |
| File untracked không cản trở file tracked | Thông thường vẫn còn nguyên. |
| File untracked hoặc thư mục untracked cản trở việc ghi file tracked từ commit đích | Git có thể xóa chúng để ghi nội dung tracked cần thiết. |
| File ignored | Thông thường vẫn còn, nhưng có thể bị ảnh hưởng nếu cản trở việc checkout/ghi một đường dẫn tracked. |

Vì vậy, câu nói reset hard xóa mọi file untracked là không chính xác. Lệnh này chủ yếu đồng bộ nội dung tracked với commit đích, nhưng file untracked có thể bị xóa nếu chúng nằm ở vị trí cản trở Git ghi file tracked. File ignored cũng không nên mặc định là an toàn trong mọi tình huống.

Lệnh git clean là công cụ riêng để xóa file untracked. Ví dụ:

~~~bash
git clean -nd
~~~

Tùy chọn -n chỉ xem trước và -d cho phép liệt kê thư mục untracked. Không thêm -f nếu chưa xem kỹ danh sách; git clean -fd thực sự xóa các mục được liệt kê. File ignored cần tùy chọn khác như -X hoặc -x, và càng cần xem trước kỹ vì có thể bao gồm đầu ra build, dữ liệu local hoặc file cấu hình riêng.

## 5. Điều kiện bảo vệ thay đổi chưa commit

Trước khi chạy git reset --hard, hãy xác nhận các điều kiện sau:

1. **Biết rõ commit đích**: xác nhận đúng branch, commit hash hoặc remote-tracking branch mà bạn muốn đưa về.
2. **Đã kiểm tra working tree**: biết file nào đã stage, file nào sửa chưa stage, file nào untracked và file nào ignored có giá trị cần giữ.
3. **Không còn thay đổi tracked cần giữ ở index hoặc working tree**, hoặc đã lưu chúng ở một nơi có thể khôi phục.
4. **Đã bảo vệ file untracked/ignored có thể bị ghi đè** nếu chúng trùng đường dẫn với file tracked trong commit đích.
5. **Hiểu ảnh hưởng đến lịch sử**: nếu reset lùi qua commit đã push, nhánh local sẽ khác remote; không push ghi đè lịch sử dùng chung khi chưa phối hợp.
6. **Có cách xác minh sau thao tác**: biết commit hiện tại phải là gì và những file nào cần được kiểm tra.

Một working tree sạch là điều kiện thuận lợi nhưng không đủ để kết luận mọi dữ liệu local đều an toàn. git status mặc định không liệt kê file ignored, và file untracked có thể không xuất hiện trong trạng thái rút gọn nếu bạn không yêu cầu hiển thị chi tiết. Hãy kiểm tra đúng loại file có thể bị ảnh hưởng.

## 6. Quy trình kiểm tra trước khi reset

### Bước 1: xác định repository và nhánh hiện tại

~~~bash
git status -sb
git branch --show-current
git log -1 --oneline --decorate
~~~

Đọc tên nhánh và commit hiện tại. Nếu đang ở detached HEAD, hãy hiểu rằng reset sẽ di chuyển HEAD detached; nếu cần giữ trạng thái hiện tại, hãy tạo một nhánh bảo vệ trước.

### Bước 2: xem thay đổi đã stage và chưa stage

~~~bash
git diff --cached
git diff
~~~

git diff --cached cho biết nội dung trong index so với HEAD. git diff cho biết thay đổi trong working tree so với index. Đọc cả hai để không bỏ sót trường hợp một file có phần đã stage và phần khác chưa stage.

### Bước 3: liệt kê file untracked

~~~bash
git status --short --untracked-files=all
~~~

Tùy chọn --untracked-files=all hiển thị file untracked chi tiết thay vì gộp thư mục. Xác định file nào chứa dữ liệu cần giữ và liệu commit đích có file tracked trùng đường dẫn hay không.

### Bước 4: kiểm tra file ignored khi cần

~~~bash
git status --short --ignored
~~~

Lệnh này giúp nhận diện các file bị ignore, chẳng hạn file cấu hình local, cache, thư mục build hoặc dữ liệu phát sinh. Không phải tất cả file ignored đều quan trọng, nhưng một số có thể chứa dữ liệu khó tạo lại. Nếu chúng nằm ở đường dẫn mà commit đích cần ghi file tracked, hãy sao lưu trước.

### Bước 5: xác minh commit đích

~~~bash
git show --no-patch --oneline <target>
git log --oneline --decorate -8 <target>
~~~

Thay <target> bằng commit hash hoặc tham chiếu dự kiến, ví dụ HEAD~1 hay origin/main. Đảm bảo commit đó thuộc đúng repository và nhánh mà bạn định dùng làm mốc.

### Bước 6: quyết định có thể reset hay cần bảo vệ thêm

Nếu mọi thay đổi tracked chưa commit đều có thể bỏ và không có file untracked/ignored cần giữ bị đường dẫn tracked cản trở, bạn có thể tiếp tục. Nếu còn nghi ngờ, hãy dùng commit hoặc stash trước khi reset.

## 7. Bảo vệ công việc trước khi chạy reset --hard

Có nhiều cách lưu lại thay đổi. Chọn cách phù hợp với loại nội dung và mục tiêu công việc.

### Cách 1: tạo commit tạm khi thay đổi đã đủ rõ

Nếu thay đổi đã có ý nghĩa và có thể lưu thành commit, hãy tạo một commit tạm:

~~~bash
git add -A
git diff --cached
git commit -m "wip: save work before reset"
~~~

Commit giúp lưu snapshot tracked và các file mới đã được stage. Sau đó, nếu cần giữ mốc hiện tại dù nhánh sẽ reset, có thể tạo nhánh bảo vệ:

~~~bash
git branch backup/before-reset
~~~

Không nên tạo commit tạm nếu việc gom toàn bộ file bằng git add -A có thể đưa nhầm secret, file sinh tự động hoặc dữ liệu không thuộc thay đổi. Hãy xem diff staged trước khi commit.

### Cách 2: dùng stash cho thay đổi đang làm dở

Stash lưu thay đổi tracked đã stage và chưa stage để working tree trở nên sạch hơn:

~~~bash
git stash push -m "before reset --hard"
~~~

Nếu muốn lưu cả file untracked:

~~~bash
git stash push -u -m "before reset --hard"
~~~

Tùy chọn -u (hoặc --include-untracked) đưa file untracked vào stash. File ignored không được đưa vào stash với -u; nếu thực sự cần lưu cả file ignored, có thể dùng -a:

~~~bash
git stash push -a -m "before reset --hard"
~~~

-a bao gồm cả file ignored, có thể làm stash rất lớn hoặc lưu cả dữ liệu sinh tự động. Chỉ dùng sau khi xác định các file đó cần được bảo vệ.

Sau khi stash, kiểm tra:

~~~bash
git status --short --untracked-files=all
git stash list
~~~

Xác nhận stash mới xuất hiện và các thay đổi cần giữ đã được lưu. Đừng chỉ dựa vào việc working tree trông sạch; hãy kiểm tra nội dung stash nếu phần công việc quan trọng.

Sau khi reset xong, áp dụng stash:

~~~bash
git stash apply --index 'stash@{0}'
~~~

--index yêu cầu Git cố gắng khôi phục cả trạng thái stage ban đầu. Nếu áp dụng thành công, kiểm tra diff, chạy test và xác nhận đầy đủ file. Chỉ xóa stash sau khi đã xác minh nội dung được phục hồi:

~~~bash
git stash drop 'stash@{0}'
~~~

Nếu có xung đột khi apply, giải quyết như một lần tích hợp thay đổi. Giữ stash lại cho đến khi xác nhận đã khôi phục đủ nội dung.

### Cách 3: lưu patch và sao lưu file untracked riêng

Với thay đổi tracked, có thể lưu diff ra file ở một vị trí an toàn, tốt nhất là ngoài working tree:

~~~bash
git diff > working-tree.patch
git diff --cached > staged.patch
~~~

Lệnh git diff ghi patch cho phần chưa stage (working tree so với index). Lệnh git diff --cached ghi patch cho phần đã stage (index so với HEAD). Hai patch này không chứa nội dung file untracked và không phải bản sao đầy đủ của repository. Hãy sao chép file untracked hoặc dữ liệu local cần giữ sang vị trí an toàn riêng.

Sau khi reset, có thể xem patch trước khi áp dụng:

~~~bash
git apply --stat working-tree.patch
git apply --stat staged.patch
~~~

Việc áp dụng lại patch có thể cần xử lý nếu nội dung đích đã thay đổi. Không xóa bản sao patch hoặc file sao lưu trước khi xác nhận kết quả.

## 8. Thực hiện reset --hard có kiểm soát

Khi đã xác minh commit đích và bảo vệ mọi thay đổi cần giữ, chạy lệnh:

~~~bash
git reset --hard <target>
~~~

Ví dụ, đưa nhánh hiện tại về commit ngay trước đó:

~~~bash
git reset --hard HEAD~1
~~~

Hoặc đưa nhánh local về đúng trạng thái remote-tracking branch sau khi fetch:

~~~bash
git fetch origin
git reset --hard origin/main
~~~

Lệnh thứ hai di chuyển nhánh local hiện tại đến commit được tham chiếu bởi origin/main. Hãy chắc chắn bạn đang đứng trên đúng nhánh local muốn thay đổi. Nếu nhánh local có commit riêng chưa được chia sẻ, reset về origin/main sẽ làm nhánh không còn trỏ tới các commit đó; hãy tạo nhánh bảo vệ hoặc lưu commit trước nếu cần giữ.

Sau khi lệnh chạy thành công, kiểm tra:

~~~bash
git status -sb
git log -1 --oneline --decorate
git diff
git diff --cached
~~~

Xác nhận HEAD ở commit đích, index và working tree không còn các thay đổi tracked ngoài dự kiến. Kiểm tra file untracked và ignored quan trọng vẫn còn nếu chúng cần được bảo vệ.

## 9. Những trường hợp không nên chạy ngay

### Working tree còn thay đổi chưa được xem xét

Nếu git status hiển thị file modified hoặc staged mà bạn chưa đọc diff, chưa xác định có cần giữ hay không, chưa đủ điều kiện chạy hard reset. Hãy phân loại và commit, stash hoặc sao lưu trước.

### Có file untracked chứa dữ liệu quan trọng

File untracked không phải lúc nào cũng bị reset xóa, nhưng có thể bị xóa nếu cản trở Git ghi một file tracked từ commit đích. Nếu dữ liệu đó quan trọng, hãy stash với -u hoặc sao chép sang nơi an toàn trước.

### Có file ignored chứa dữ liệu local

Các file ignored thường không xuất hiện trong git status thông thường. Kiểm tra git status --ignored và sao lưu file quan trọng nếu có khả năng bị ghi đè. Không dùng git clean -fdx như một bước dọn dẹp tùy tiện; lệnh đó có thể xóa cả file ignored.

### Đang ở nhánh đã chia sẻ và định reset lùi lịch sử

Reset nhánh local về commit cũ không tự thay đổi remote. Nhưng nếu sau đó push bằng force, lịch sử remote có thể bị viết lại và ảnh hưởng đến đồng đội. Hãy phối hợp trước, kiểm tra trạng thái remote và dùng --force-with-lease nếu quy trình cho phép viết lại lịch sử.

### Chưa biết commit đích có đúng không

Không dùng HEAD~1, origin/main hoặc hash được sao chép từ nơi khác theo thói quen. Hãy kiểm tra commit bằng git show, log và tên nhánh trước khi chạy. Một commit đích hợp lệ về cú pháp vẫn có thể là mốc sai về nghiệp vụ.

## 10. Nếu lỡ chạy reset --hard

Trước tiên, dừng các thao tác ghi đè tiếp theo. Không chạy thêm reset, clean, garbage collection hoặc thao tác dọn repository trong khi chưa kiểm tra khả năng phục hồi.

### Kiểm tra reflog

Reflog ghi lại các lần cập nhật tham chiếu local, bao gồm những lần di chuyển HEAD. Xem lịch sử:

~~~bash
git reflog --date=local
~~~

Tìm mục ngay trước lần reset nhầm. Có thể kiểm tra commit đó:

~~~bash
git show --stat <old-commit>
~~~

Nếu xác nhận đó là commit cần khôi phục, tạo một nhánh bảo vệ trỏ đến commit cũ:

~~~bash
git branch rescue/before-reset <old-commit>
~~~

Sau đó có thể quyết định đưa nhánh hiện tại về commit này hoặc cherry-pick các commit cần lấy. Tạo nhánh cứu hộ giúp giữ tham chiếu đến commit trong khi tiếp tục điều tra.

Git thường cập nhật ORIG_HEAD khi reset, nhưng giá trị này có thể bị thao tác khác ghi đè. Hãy kiểm tra trước khi sử dụng:

~~~bash
git show --no-patch --oneline ORIG_HEAD
~~~

Không mặc định ORIG_HEAD luôn là commit mong muốn.

### Giới hạn phục hồi thay đổi chưa commit

Reflog theo dõi các tham chiếu và commit, không phải bản sao của mọi nội dung từng có trong working tree. Nếu reset hard đã thay thế thay đổi tracked chưa commit, Git thường không có commit hoặc reflog entry để khôi phục chính phần nội dung đó.

Có thể thử tìm trong local history của IDE, bản sao lưu hệ thống, file patch, stash đã tạo trước đó hoặc công cụ phục hồi dữ liệu. Kết quả phụ thuộc công cụ và hệ thống; không có bảo đảm rằng nội dung chưa commit sẽ phục hồi được. Đây là lý do cần bảo vệ thay đổi trước khi chạy lệnh.

## 11. Những nhầm lẫn thường gặp

### git reset --hard có xóa commit khỏi repository ngay lập tức không?

Không. Lệnh di chuyển nhánh khỏi commit cũ. Commit có thể vẫn được tìm qua reflog hoặc tham chiếu khác trong một khoảng thời gian. Sau khi không còn tham chiếu và hết thời gian lưu giữ, Git có thể dọn đối tượng không còn dùng.

### git reset --hard có xóa mọi file untracked không?

Không. File untracked thường được giữ nếu không cản trở việc ghi file tracked từ commit đích. Tuy nhiên, file untracked nằm đúng đường dẫn mà Git cần tạo hoặc cập nhật có thể bị xóa. Hãy kiểm tra và sao lưu nếu cần giữ.

### git reset --hard có giống git clean không?

Không. Reset đồng bộ HEAD, index và working tree tracked theo commit đích. Clean xóa file untracked theo các tùy chọn được chỉ định. Hai lệnh có phạm vi khác nhau; không kết hợp chúng nếu chưa hiểu danh sách file sẽ bị xóa.

### Có thể dùng git reset --hard để bỏ một file không?

Nếu chỉ muốn khôi phục một file tracked, dùng git restore --source=HEAD --staged --worktree -- <file> sau khi xác nhận không cần thay đổi của file đó. Lệnh này chỉ tác động đường dẫn được chỉ định, giúp tránh reset toàn bộ nhánh.

### Stash có lưu file ignored không?

Không với lệnh stash mặc định hoặc -u. Muốn đưa cả ignored file vào stash, dùng -a; hãy cân nhắc kích thước và dữ liệu local trước khi chọn.

## 12. Tự kiểm tra trước một lần reset

Giả sử nhánh feature/report đang ở commit C, còn commit B là commit trước đó. Bạn đã chỉnh sửa ReportService.java, stage một phần thay đổi, tạo thêm file report-local.json chưa được Git theo dõi và có file cấu hình local bị ignore.

Trước khi chạy:

~~~bash
git reset --hard B
~~~

Hãy tự trả lời:

1. Lệnh sẽ làm gì với HEAD, index và working tree?
2. Phần đã stage và phần chưa stage của ReportService.java có được giữ không?
3. File report-local.json có chắc chắn an toàn không?
4. Cần kiểm tra bằng lệnh nào để thấy file ignored?
5. Nếu muốn giữ tất cả thay đổi tracked và file untracked trước reset, có thể dùng lệnh nào?
6. Sau reset, nếu nhận ra đã bỏ khỏi nhánh một commit cần thiết, nên kiểm tra đâu trước?

**Gợi ý:** HEAD/nhánh, index và working tree tracked sẽ được đưa về B. Hai phần thay đổi của file tracked có thể mất. File untracked thường còn nếu không cản trở đường dẫn tracked trong B, nhưng không nên dựa vào giả định đó nếu dữ liệu quan trọng. Dùng git status --short --ignored để xem ignored file. Dùng git stash push -u -m "before reset --hard" để lưu thay đổi tracked và untracked; nếu cần giữ cả ignored file, cân nhắc -a. Nếu commit bị bỏ khỏi nhánh, kiểm tra git reflog và tạo nhánh cứu hộ khi xác định đúng commit.

## Kết luận

git reset --hard đưa HEAD/nhánh, index và working tree tracked về một commit đích, nên có thể loại bỏ thay đổi tracked chưa commit. Trước khi chạy, hãy xác nhận đúng repository, nhánh và commit; kiểm tra staged, unstaged, untracked và ignored; bảo vệ phần công việc cần giữ bằng commit, stash hoặc bản sao; rồi readback trạng thái sau thao tác. Reflog có thể giúp tìm lại commit đã bị bỏ khỏi đầu nhánh, nhưng không bảo đảm phục hồi nội dung working tree chưa commit. Kỷ luật kiểm tra và sao lưu trước reset là cách đáng tin cậy nhất để tránh mất công việc.
