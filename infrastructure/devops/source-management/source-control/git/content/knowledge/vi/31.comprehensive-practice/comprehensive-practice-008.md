# Phục hồi nhánh bị xóa hoặc reset nhầm bằng reflog

Một nhánh Git chỉ là một tên tham chiếu tới commit. Khi xóa nhánh hoặc reset nhầm, tên tham chiếu có thể biến mất hoặc trỏ sang commit khác, nhưng commit cũ thường vẫn còn trong repository một thời gian. **Reflog** ghi lại các lần tham chiếu local thay đổi, giúp tìm lại commit trước đó và tạo nhánh phục hồi.

Điểm quan trọng là phải tìm đúng commit, giữ nó bằng một ref mới rồi mới quyết định khôi phục tên nhánh. Đừng vội chạy garbage collection, dọn object hoặc tiếp tục reset khi chưa xác định trạng thái. Reflog có thời hạn lưu và không thay thế bản sao lưu.

Bài này tập trung vào các tình huống thường gặp: xóa nhánh local, reset nhầm, rebase làm thay đổi tip, xóa remote-tracking branch và tìm commit không còn được tham chiếu.

## 1. Hiểu nhánh Git trước khi phục hồi

Một branch như <code>feature/payment</code> là một ref trỏ tới commit tip của nhánh. Khi tạo commit mới trên nhánh đó, ref được cập nhật để trỏ tới commit mới.

Ví dụ:

~~~text
A---B---C  main
     \
      D---E  feature/payment
~~~

Trong ví dụ, <code>feature/payment</code> trỏ tới commit E. Nếu xóa nhánh:

~~~bash
git branch -D feature/payment
~~~

Git xóa ref mang tên <code>refs/heads/feature/payment</code>. Commit D và E không nhất thiết bị xóa ngay khỏi object database. Chúng có thể vẫn được giữ bởi:

- Reflog của HEAD hoặc một ref khác.
- Một branch, tag hoặc ref khác.
- Một clone khác của repository.
- Một object chưa bị garbage collection dọn đi.

Nếu không còn ref nào trỏ tới E, commit có thể trở thành unreachable (không còn reachable từ các ref đang tồn tại). Git vẫn có thể tìm thấy nó trong reflog hoặc bằng <code>git fsck</code> cho tới khi object thực sự bị prune.

## 2. Reflog là gì?

Reflog (reference log) là nhật ký local ghi lại các lần một ref thay đổi giá trị. Reflog hữu ích để biết HEAD hoặc branch từng trỏ tới commit nào.

Một số hoạt động thường được ghi vào reflog:

- Commit mới cập nhật branch tip.
- Checkout hoặc switch làm HEAD chuyển sang branch/commit khác.
- Reset di chuyển branch hoặc HEAD tới commit khác.
- Rebase thay thế chuỗi commit và cập nhật branch.
- Một số thao tác merge, cherry-pick hoặc cập nhật ref khác.

Reflog khác với lịch sử commit:

| Lịch sử commit | Reflog |
|---|---|
| Mô tả quan hệ cha/con giữa các commit | Ghi lại các lần ref thay đổi |
| Được chia sẻ khi push/fetch thông qua commit và refs | Là nhật ký local, không được push lên remote |
| Có thể duyệt bằng <code>git log</code> | Xem bằng <code>git reflog</code> |
| Thể hiện lịch sử dự án | Hỗ trợ tìm trạng thái ref trong quá khứ |

Reflog không phải lịch sử toàn diện của mọi file đã từng có trên máy. Nó ghi lại chuyển động của refs, không lưu riêng mọi thay đổi chưa commit trong working tree.

## 3. HEAD reflog và branch reflog

Git thường có reflog cho HEAD và cho các branch local.

- **HEAD reflog** ghi các lần HEAD di chuyển, ví dụ checkout, switch, commit hoặc reset.
- **Branch reflog** ghi các lần một branch ref thay đổi tip.

Xem HEAD reflog:

~~~bash
git reflog
~~~

Hoặc chỉ rõ:

~~~bash
git reflog show HEAD
~~~

Xem reflog của một branch còn tồn tại:

~~~bash
git reflog show refs/heads/feature/payment
~~~

Xem các reflog hiện có:

~~~bash
git reflog show --all
~~~

Có thể thêm thời gian dễ đọc:

~~~bash
git reflog show --date=iso
git reflog show HEAD --date=local
~~~

Nếu branch bị xóa, reflog riêng của branch đó thường cũng bị xóa cùng ref. HEAD reflog vẫn có thể giữ dấu vết nếu branch từng được checkout trên repository này. Nếu branch chưa từng được checkout tại clone hiện tại, cần tìm trong reflog khác, clone khác hoặc object unreachable.

## 4. Đọc một dòng reflog

Ví dụ:

~~~text
a12bc34 HEAD@{0}: checkout: moving from feature/payment to main
e56fa78 HEAD@{1}: commit: Add payment validation
91ab234 HEAD@{2}: commit: Create payment service
~~~

Cách đọc:

- <code>HEAD@{0}</code> là vị trí HEAD hiện tại được ghi nhận gần nhất.
- <code>HEAD@{1}</code> là trạng thái ngay trước entry mới nhất.
- OID ở đầu dòng là commit mà ref trỏ tới sau lần cập nhật được ghi trong entry.
- Phần sau dấu hai chấm mô tả thao tác gây ra cập nhật.

Trong ví dụ, HEAD hiện tại trỏ tới commit của <code>main</code>. Entry trước đó ghi commit <code>Add payment validation</code>, có thể là tip gần nhất của <code>feature/payment</code> trước khi chuyển sang main.

Không nên đoán rằng <code>HEAD@{1}</code> luôn là commit cần phục hồi. Số thứ tự reflog thay đổi sau mỗi thao tác Git mới. Hãy đọc message, kiểm tra OID và lưu hash đầy đủ trước khi dùng.

## 5. Tình huống 1: Xóa nhầm branch local

Giả sử bạn xóa nhánh:

~~~bash
git branch -D feature/payment
~~~

Sau đó nhận ra nhánh có các commit chưa được merge.

### Bước 1 — Kiểm tra branch và refs hiện có

~~~bash
git branch -avv
git show-ref
~~~

Xác nhận branch local đã mất hay vẫn còn ở remote-tracking ref. Nếu <code>origin/feature/payment</code> còn tồn tại, có thể tạo lại branch local trực tiếp từ ref đó:

~~~bash
git switch -c feature/payment origin/feature/payment
~~~

Nếu remote-tracking ref cũng không còn, tiếp tục tìm bằng reflog.

### Bước 2 — Tìm dấu vết trong HEAD reflog

~~~bash
git reflog show HEAD --date=local
~~~

Tìm entry có message như:

~~~text
checkout: moving from feature/payment to main
~~~

Entry ngay trước đó thường là commit HEAD cuối cùng trên branch trước khi rời nhánh. Đọc các dòng lân cận và xác định commit có chứa thay đổi mong muốn.

### Bước 3 — Kiểm tra commit ứng viên

Giả sử OID đầy đủ tìm được là <code>e56fa78...</code>:

~~~bash
git show --stat --oneline e56fa78
git show -s --format=fuller e56fa78
git log --graph --oneline --decorate e56fa78
~~~

Kiểm tra author, thời gian, message và các file đã thay đổi để chắc chắn đó là tip cần phục hồi.

### Bước 4 — Tạo branch phục hồi

~~~bash
git branch rescue/payment-before-delete e56fa78
~~~

Hoặc tạo lại đúng tên branch nếu tên đó đang trống:

~~~bash
git switch -c feature/payment e56fa78
~~~

Tạo ref mới giúp commit trở thành reachable trở lại và giảm nguy cơ bị garbage collection dọn. Nên tạo branch cứu hộ trước, rồi mới quyết định có cần đổi tên hoặc cập nhật remote hay không.

## 6. Tình huống 2: Reset nhầm bằng git reset --hard

Giả sử bạn đang ở <code>feature/payment</code> và chạy nhầm:

~~~bash
git reset --hard HEAD~3
~~~

Branch hiện tại bị di chuyển lùi ba commit; index và tracked working tree cũng được đưa về trạng thái của commit mới. Các commit cũ có thể vẫn được tìm thấy trong reflog.

Kiểm tra:

~~~bash
git reflog show HEAD --date=local
git reflog show refs/heads/feature/payment --date=local
~~~

Một kết quả minh họa:

~~~text
91ab234 HEAD@{0}: reset: moving to HEAD~3
e56fa78 HEAD@{1}: commit: Add payment validation
a12bc34 HEAD@{2}: commit: Add payment endpoint
~~~

OID <code>e56fa78</code> là vị trí trước reset. Hãy xác nhận nó bằng <code>git show</code>, sau đó tạo branch cứu hộ:

~~~bash
git branch rescue/payment-before-reset e56fa78
~~~

Nếu mục tiêu là đưa branch đang làm việc trở lại tip cũ, có thể reset branch về OID đó sau khi đã kiểm tra working tree và bảo toàn mọi thay đổi mới:

~~~bash
git status
git reset --hard e56fa78
~~~

Lệnh reset cuối thay đổi branch hiện tại, index và tracked working tree. Chỉ chạy khi bạn thực sự muốn khôi phục cả ba về commit đó và đã lưu mọi thay đổi cần giữ. Nếu chưa chắc, chỉ tạo rescue branch và tiếp tục phân tích.

## 7. Phân biệt reset --soft, --mixed và --hard

Các chế độ reset ảnh hưởng khác nhau tới branch, index và working tree:

| Lệnh | Branch/HEAD | Index | Tracked working tree |
|---|---|---|---|
| <code>git reset --soft &lt;commit&gt;</code> | Di chuyển tới commit đích | Giữ nguyên | Giữ nguyên |
| <code>git reset --mixed &lt;commit&gt;</code> | Di chuyển tới commit đích | Đặt theo commit đích | Giữ nguyên file đang có |
| <code>git reset --hard &lt;commit&gt;</code> | Di chuyển tới commit đích | Đặt theo commit đích | Đặt theo commit đích |

Reflog có thể giúp phục hồi branch tip sau cả ba loại reset. Nhưng khả năng khôi phục file trong working tree khác nhau.

Đặc biệt, <code>reset --hard</code> có thể làm mất thay đổi tracked chưa commit bằng cách ghi đè working tree. Reflog không lưu các nội dung đó. File untracked cũng có thể bị xóa nếu cản trở checkout/reset; các file untracked khác không được reflog ghi lại.

Nếu reset nhầm làm mất nội dung chưa commit, hãy kiểm tra IDE local history, backup, filesystem snapshot hoặc bản sao khác. Không hứa rằng reflog có thể khôi phục mọi file đã bị ghi đè.

## 8. Tình huống 3: Rebase làm branch trỏ sang lịch sử khác

Rebase tạo commit mới với parent mới, nên OID của các commit được rebase thường thay đổi.

Ví dụ trước rebase:

~~~text
A---B---C  main
     \
      D---E  feature/payment
~~~

Sau khi rebase lên main mới:

~~~text
A---B---C---D'---E'  feature/payment
~~~

Nếu rebase nhầm hoặc muốn tìm lại tip trước rebase, xem reflog:

~~~bash
git reflog show HEAD --date=local
git reflog show refs/heads/feature/payment --date=local
~~~

Tìm entry có message liên quan đến rebase hoặc thao tác checkout/reset ngay sau đó. Kiểm tra OID trước rebase rồi giữ nó bằng branch cứu hộ:

~~~bash
git branch rescue/payment-before-rebase <old-commit>
~~~

Nếu rebase đang diễn ra và chưa hoàn tất, trước hết kiểm tra trạng thái:

~~~bash
git status
~~~

Nếu mục tiêu chỉ là hủy rebase đang chạy, lệnh thường dùng là:

~~~bash
git rebase --abort
~~~

Lệnh này đưa repository về trạng thái trước khi bắt đầu rebase nếu Git vẫn đang ở trạng thái rebase. Nếu rebase đã hoàn tất, dùng reflog để tìm tip cũ.

## 9. Tình huống 4: Reset nhầm branch khác

Đôi khi terminal đang ở branch <code>main</code> nhưng bạn tưởng đang ở <code>feature/payment</code>. Một lệnh reset có thể di chuyển nhầm branch quan trọng.

Trước tiên kiểm tra branch hiện tại và reflog:

~~~bash
git branch --show-current
git reflog show HEAD --date=local
git reflog show refs/heads/main --date=local
~~~

Nếu <code>main</code> bị reset, branch reflog của main thường giữ giá trị trước đó:

~~~bash
git reflog show refs/heads/main
~~~

Tìm OID trước reset, xác nhận commit rồi tạo branch cứu hộ:

~~~bash
git branch rescue/main-before-reset <old-main-commit>
~~~

Đừng vội reset lại <code>main</code> nếu branch đã được người khác cập nhật hoặc có commit mới sau sự cố. Đối chiếu với remote và phối hợp nhóm trước khi thay đổi ref dùng chung.

## 10. Tình huống 5: Branch remote bị xóa

Xóa branch remote thường được thực hiện bằng:

~~~bash
git push origin --delete feature/payment
~~~

Hoặc branch bị xóa trên giao diện hosting. Thao tác này xóa ref trên server; nó không tự động xóa mọi bản sao commit trong các clone.

Kiểm tra remote-tracking refs local:

~~~bash
git branch -r
git show-ref
~~~

Có thể lọc output theo tên branch. Trong Git Bash/Linux/macOS dùng <code>grep</code>; trong PowerShell dùng <code>Select-String</code>:

~~~powershell
git show-ref | Select-String 'feature/payment'
~~~

Nếu <code>origin/feature/payment</code> còn tồn tại, tạo lại branch local từ đó. Nếu đã bị prune, kiểm tra reflog của remote-tracking ref nếu còn:

~~~bash
git reflog show refs/remotes/origin/feature/payment
~~~

Remote-tracking reflog cũng là dữ liệu local và có thể đã bị xóa cùng ref. Nếu không còn, tìm commit từ HEAD reflog, branch local khác, tag, clone đồng đội hoặc bản sao lưu.

### Khôi phục branch trên remote

Sau khi đã có branch local cứu hộ và xác minh commit, có thể đẩy lại đúng tên branch:

~~~bash
git push origin rescue/payment-before-delete:refs/heads/feature/payment
~~~

Lệnh này tạo/cập nhật branch remote <code>feature/payment</code> từ tip của branch cứu hộ. Trước khi push, kiểm tra remote hiện tại để tránh ghi đè một branch mới mà người khác đã tạo lại sau sự cố.

## 11. Reflog không có entry cần tìm: dùng git fsck

Nếu branch đã bị xóa và reflog không còn dấu vết, commit có thể vẫn tồn tại dưới dạng unreachable object. <code>git fsck</code> giúp tìm những object như vậy.

Chạy:

~~~bash
git fsck --full --no-reflogs --unreachable
~~~

Git có thể liệt kê các dòng như:

~~~text
unreachable commit e56fa78...
unreachable tree 91ab234...
unreachable blob a12bc34...
~~~

Ưu tiên các dòng <code>unreachable commit</code>. Chúng là ứng viên có thể đại diện cho tip của branch cũ hoặc commit trung gian.

Kiểm tra từng ứng viên:

~~~bash
git show -s --format=fuller e56fa78
git show --stat --oneline e56fa78
git log --graph --oneline e56fa78
~~~

Khi đã xác định đúng commit:

~~~bash
git branch rescue/recovered-payment e56fa78
~~~

Sau khi branch rescue được tạo, commit trở lại reachable từ ref đó.

<code>git fsck</code> có thể liệt kê nhiều object không liên quan. Cần đối chiếu commit message, thời gian, parent và file thay đổi; không chọn commit chỉ vì nó có timestamp gần sự cố.

## 12. Có thể dùng git fsck --lost-found không?

Git hỗ trợ:

~~~bash
git fsck --full --no-reflogs --lost-found
~~~

Tùy chọn <code>--lost-found</code> ghi các object unreachable được tìm thấy vào thư mục <code>.git/lost-found/</code> để hỗ trợ kiểm tra thủ công. Commit và blob có thể được ghi ở các khu vực tương ứng.

Đây là thao tác ghi dữ liệu vào metadata của repository. Chỉ dùng khi cần một nơi tập hợp object để kiểm tra; thường thì đọc OID trực tiếp từ output <code>git fsck</code> rồi dùng <code>git show</code> là đủ.

Không xóa thư mục <code>lost-found</code> trước khi xác định các object có cần giữ hay không.

## 13. Dùng ORIG_HEAD khi phù hợp

Git có thể lưu một số vị trí HEAD trước thao tác lớn trong ref đặc biệt <code>ORIG_HEAD</code>. Ref này đôi khi hữu ích sau reset, merge hoặc rebase.

Kiểm tra:

~~~bash
git show -s --format=fuller ORIG_HEAD
git log -1 --oneline ORIG_HEAD
~~~

Nếu đúng là commit cần khôi phục, tạo branch cứu hộ:

~~~bash
git branch rescue/orig-head ORIG_HEAD
~~~

Tuy nhiên, <code>ORIG_HEAD</code> có thể bị ghi đè bởi thao tác khác và không phải nhật ký đầy đủ. Luôn đối chiếu với reflog và nội dung commit trước khi dùng.

## 14. Tạo rescue branch trước khi khôi phục tên branch cũ

Khi tìm thấy commit nghi ngờ, cách an toàn là tạo một branch cứu hộ riêng trước:

~~~bash
git branch rescue/recovered-feature <commit-oid>
~~~

Sau đó kiểm tra:

~~~bash
git show --stat --oneline rescue/recovered-feature
git log --graph --decorate --oneline rescue/recovered-feature
git status
~~~

Branch rescue có ba lợi ích:

1. Giữ commit khỏi trạng thái unreachable.
2. Cho phép so sánh với branch hiện tại.
3. Giúp nhóm xem xét trước khi khôi phục tên branch chính thức.

Khi đã xác nhận commit, nếu tên cũ chưa tồn tại, có thể tạo lại:

~~~bash
git switch -c feature/payment rescue/recovered-feature
~~~

Nếu tên branch đã được tạo lại với tip khác, không ghi đè ngay. So sánh hai lịch sử và phối hợp với người đang làm việc trên branch đó.

## 15. Phân biệt phục hồi commit và phục hồi thay đổi chưa commit

Reflog chủ yếu phục hồi vị trí ref, không khôi phục mọi nội dung từng có trong working tree.

| Dữ liệu bị mất | Reflog có giúp không? | Hướng xử lý |
|---|---|---|
| Commit đã tạo rồi branch bị xóa | Thường có | Tìm OID qua reflog hoặc fsck, tạo branch mới |
| Branch bị reset sang commit cũ | Thường có | Tìm tip trước reset trong reflog |
| Commit bị thay thế sau rebase | Thường có | Tìm tip trước rebase trong reflog |
| Thay đổi tracked chưa commit bị reset --hard ghi đè | Không trực tiếp | IDE local history, backup hoặc filesystem recovery |
| File untracked bị xóa bởi clean/reset | Không | Backup, snapshot hoặc công cụ phục hồi file |
| File đã stage nhưng chưa commit và bị ghi đè | Không bảo đảm | Kiểm tra backup; index không phải nhật ký phiên bản |
| Commit đã bị prune khỏi object database | Không | Tìm clone khác, remote, bundle hoặc backup |

Nếu có thay đổi chưa commit quan trọng, hãy sao chép working tree hoặc dùng patch/backup trước khi chạy lệnh phục hồi tiếp theo. Tránh để các thao tác mới ghi đè dữ liệu còn sót lại.

## 16. Vì sao cần hành động sớm?

Reflog có chính sách hết hạn. Mặc định thường gặp:

- Reflog entry có thể hết hạn sau khoảng 90 ngày nếu commit còn reachable.
- Entry trỏ tới commit không còn reachable có thể hết hạn sau khoảng 30 ngày.

Các giá trị thực tế phụ thuộc cấu hình và phiên bản Git. Kiểm tra:

~~~bash
git config --show-origin --get gc.reflogExpire
git config --show-origin --get gc.reflogExpireUnreachable
git config --show-origin --get gc.pruneExpire
~~~

Nếu không có giá trị tường minh, Git dùng mặc định của phiên bản đang cài.

Khi reflog entry hết hạn, object không còn được ref nào giữ có thể bị garbage collection prune sau đó. Một khi object đã bị xóa vật lý khỏi mọi bản sao, reflog không thể tái tạo nội dung commit.

Vì vậy, ngay khi phát hiện reset/xóa nhầm:

1. Dừng các lệnh dọn dẹp không cần thiết.
2. Tìm commit bằng reflog.
3. Tạo branch cứu hộ để giữ commit.
4. Chỉ sau khi dữ liệu đã an toàn mới tiếp tục công việc.

## 17. Các lệnh nên tránh trong lúc đang phục hồi

Trong khi chưa xác định commit cần giữ, tránh:

~~~bash
git gc --prune=now
git reflog expire --expire=now --all
git prune
~~~

Các lệnh này có thể làm mất dấu vết reflog hoặc xóa object không còn được tham chiếu. Đặc biệt, <code>--prune=now</code> loại bỏ khoảng thời gian chờ an toàn thường dùng để bảo vệ object mới trở thành unreachable.

Cũng tránh reset, rebase hoặc force push thêm lần nữa trước khi ghi lại OID cần khôi phục. Mỗi thao tác có thể thêm entry mới, làm thay đổi vị trí <code>HEAD@{n}</code> và gây khó đọc hơn.

Không cần chạy <code>git gc</code> chỉ vì vừa phục hồi branch. Khi branch cứu hộ đã giữ commit, Git sẽ tự quản lý object theo quy trình thông thường.

## 18. Tìm commit qua clone khác hoặc bản sao lưu

Reflog là local, nên một clone khác có thể còn branch hoặc commit mà clone hiện tại đã mất.

Có thể nhờ thành viên kiểm tra:

~~~bash
git branch -avv
git reflog --all --date=local
git log --all --graph --decorate --oneline
~~~

Nếu họ tìm được commit, có thể gửi OID và push branch cứu hộ lên remote theo quy trình nhóm. Không gửi thư mục <code>.git</code> qua kênh không an toàn nếu repository chứa dữ liệu nhạy cảm.

Các nguồn khác:

- Tag đã tạo trước đó.
- Pull Request/Merge Request ref hoặc commit được nền tảng lưu.
- Git bundle đã tạo.
- Mirror hoặc backup repository.
- Clone CI/workspace còn giữ object.
- Bản sao lưu filesystem.

Không giả định hosting provider luôn giữ reflog hoặc object đã xóa. Chính sách retention và khả năng phục hồi phụ thuộc nền tảng; cần quản trị viên hoặc nhà cung cấp xác nhận.

## 19. Phục hồi branch đã bị xóa khi đang có nhiều clone

Trong nhóm, một thành viên có thể xóa branch local trong khi đồng đội vẫn còn branch đó. Trước khi viết lại remote, hỏi xem branch còn trong clone nào không.

Nếu đồng đội có branch:

~~~bash
git log --oneline --decorate feature/payment
git show -s --format=%H feature/payment
~~~

Họ có thể tạo branch cứu hộ và push lên remote:

~~~bash
git branch rescue/payment-team-copy feature/payment
git push -u origin rescue/payment-team-copy
~~~

Sau khi branch rescue xuất hiện trên remote, người gặp sự cố có thể fetch và tạo lại branch:

~~~bash
git fetch origin
git switch -c feature/payment origin/rescue/payment-team-copy
~~~

Cách này chia sẻ commit thông qua một ref mới, không cần gửi thủ công object database. Xác nhận OID và quyền truy cập trước khi dùng.

## 20. Quy trình phục hồi đầy đủ cho branch bị xóa

Giả sử branch <code>feature/report-export</code> bị xóa nhầm và remote-tracking ref cũng không còn.

**Bước 1 — Kiểm tra trạng thái hiện tại**

~~~bash
git status
git branch -avv
git show-ref
~~~

Ghi nhận branch hiện tại và các thay đổi chưa commit.

**Bước 2 — Tìm reflog**

~~~bash
git reflog show HEAD --date=local
git reflog show --all --date=local
~~~

Tìm entry liên quan tới lần checkout cuối cùng của <code>feature/report-export</code>.

**Bước 3 — Kiểm tra commit ứng viên**

~~~bash
git show -s --format=fuller <candidate-oid>
git show --stat --oneline <candidate-oid>
git log --graph --oneline <candidate-oid>
~~~

**Bước 4 — Tạo branch cứu hộ**

~~~bash
git branch rescue/report-export <candidate-oid>
~~~

**Bước 5 — Khôi phục tên branch local**

Nếu tên cũ chưa tồn tại:

~~~bash
git switch -c feature/report-export rescue/report-export
~~~

Nếu tên đã tồn tại, so sánh trước khi quyết định đổi tên hoặc cập nhật ref.

**Bước 6 — Xác minh**

~~~bash
git log --graph --decorate --oneline --all
git status
git show-ref
~~~

**Bước 7 — Khôi phục remote nếu cần**

Sau khi xác nhận branch local đúng và remote chưa có branch cùng tên với công việc mới:

~~~bash
git push -u origin feature/report-export
~~~

Nếu cần push từ branch rescue tới tên branch remote:

~~~bash
git push origin rescue/report-export:refs/heads/feature/report-export
~~~

**Bước 8 — Thông báo cho nhóm**

Gửi OID và thời điểm khôi phục trong kênh làm việc phù hợp. Nhắc mọi người đồng bộ lại refs và tránh force push từ clone cũ.

## 21. Quy trình phục hồi đầy đủ cho reset nhầm

Giả sử branch <code>feature/payment</code> bị reset lùi ba commit.

**Bước 1 — Không reset thêm**

Kiểm tra:

~~~bash
git status
git branch --show-current
~~~

Nếu có thay đổi local mới, bảo toàn trước.

**Bước 2 — Đọc reflog**

~~~bash
git reflog show HEAD --date=local
git reflog show refs/heads/feature/payment --date=local
~~~

Tìm entry <code>reset: moving to ...</code> và OID trước thao tác.

**Bước 3 — Kiểm tra commit cũ**

~~~bash
git show --stat --oneline <old-tip>
git log --graph --oneline <old-tip>
~~~

**Bước 4 — Tạo branch cứu hộ**

~~~bash
git branch rescue/payment-before-reset <old-tip>
~~~

**Bước 5 — Chọn cách tiếp tục**

- Nếu chỉ cần giữ lại các commit cũ, branch rescue đã đủ.
- Nếu muốn đưa branch hiện tại trở lại tip cũ, kiểm tra trạng thái rồi reset có chủ ý.
- Nếu đã có commit mới sau reset, so sánh hai nhánh và chọn merge/cherry-pick/rebase theo mục tiêu.

**Bước 6 — Xác minh và chia sẻ**

~~~bash
git log --graph --decorate --oneline --all
git status
~~~

Chỉ push sau khi đã xác nhận lịch sử và thống nhất với nhóm.

## 22. Một số câu lệnh phục hồi thường dùng

| Mục tiêu | Lệnh |
|---|---|
| Xem HEAD reflog | <code>git reflog show HEAD</code> |
| Xem reflog của branch | <code>git reflog show refs/heads/&lt;branch&gt;</code> |
| Xem tất cả reflog còn có | <code>git reflog show --all</code> |
| Xem commit theo OID | <code>git show &lt;oid&gt;</code> |
| Xem metadata commit | <code>git show -s --format=fuller &lt;oid&gt;</code> |
| Tạo branch cứu hộ | <code>git branch rescue/&lt;name&gt; &lt;oid&gt;</code> |
| Tìm object unreachable | <code>git fsck --full --no-reflogs --unreachable</code> |
| Kiểm tra ORIG_HEAD | <code>git show ORIG_HEAD</code> |
| Xem branch và remote refs | <code>git branch -avv</code> |
| Kiểm tra lịch sử mọi refs | <code>git log --all --graph --decorate --oneline</code> |

Luôn thay placeholder bằng OID đầy đủ đã được xác minh. Tránh dùng các tên tương đối như <code>HEAD@{1}</code> sau khi đã chạy thêm nhiều lệnh làm reflog thay đổi; lưu hash cụ thể trước.

## 23. Những hiểu lầm thường gặp

| Hiểu lầm | Thực tế |
|---|---|
| Xóa branch là xóa commit ngay lập tức | Xóa ref; commit có thể còn trong reflog hoặc unreachable objects |
| Reflog được push lên remote | Reflog local không được push/fetch như branch |
| <code>HEAD@{1}</code> luôn là commit trước khi lỗi | Nó phụ thuộc các thao tác mới nhất và cần đọc message/OID |
| Reflog khôi phục được file bị reset --hard | Reflog phục hồi ref/commit, không lưu thay đổi working tree chưa commit |
| <code>git fsck</code> luôn tìm lại được mọi commit | Chỉ tìm object còn tồn tại trong object database |
| Xóa branch remote sẽ xóa branch trong mọi clone | Các clone có thể còn local branch hoặc object |
| ORIG_HEAD luôn chứa commit cần tìm | Ref này có thể bị ghi đè và chỉ hỗ trợ một số thao tác |
| Có thể chạy gc ngay sau khi xóa branch | Garbage collection có thể prune object unreachable sau khi hết thời gian bảo vệ |

## 24. Phòng ngừa xóa hoặc reset nhầm

Một số thói quen giúp giảm rủi ro:

- Trước khi xóa branch, kiểm tra đã merge hoặc có bản sao cần giữ chưa.
- Dùng <code>git branch --merged</code> để xem branch đã được merge vào branch hiện tại.
- Kiểm tra tên branch hiện tại trước khi chạy reset hoặc rebase.
- Ưu tiên tạo branch backup trước thao tác viết lại lịch sử quan trọng.
- Trước <code>reset --hard</code>, chạy <code>git status</code> và lưu thay đổi chưa commit.
- Không chạy cleanup/gc ngay sau sự cố.
- Với branch dùng chung, phối hợp nhóm trước khi force push hoặc khôi phục tên remote.
- Dùng backup, bundle hoặc mirror cho repository quan trọng.
- Hiểu rằng reflog có thời hạn lưu và có thể không tồn tại trong clone khác.

Có thể tạo một ref backup trước khi thao tác rủi ro:

~~~bash
git branch backup/payment-before-rewrite feature/payment
~~~

Ref này giữ tip hiện tại cho tới khi bạn chủ động xóa branch backup. Đây là cách đơn giản để có điểm quay lại trước rebase hoặc reset có chủ đích.

## 25. Bài tập thực hành trong repository thử nghiệm

Hãy tạo một repository riêng để thực hành, không dùng repository đang làm việc.

### Bài tập A — Xóa branch rồi khôi phục

~~~bash
git init --initial-branch=main recovery-lab
cd recovery-lab
echo base > README.md
git add README.md
git commit -m "Initial commit"
git switch -c feature/demo
echo first > feature.txt
git add feature.txt
git commit -m "Create feature"
echo second >> feature.txt
git commit -am "Extend feature"
git switch main
git branch -D feature/demo
git reflog show HEAD
~~~

Tùy chọn <code>--initial-branch</code> có từ Git 2.28. Nếu dùng phiên bản cũ hơn, chạy <code>git init recovery-lab</code>; sau commit đầu tiên, đổi tên branch khởi tạo thành <code>main</code> bằng <code>git branch -M main</code> nếu cần.

Tìm commit tip cuối của feature trước khi chuyển sang main và tạo lại branch:

~~~bash
git branch rescue/demo <commit-oid>
git log --oneline rescue/demo
~~~

### Bài tập B — Reset nhầm

~~~bash
git switch rescue/demo
git reset --hard HEAD~1
git reflog show HEAD
~~~

Tìm commit trước reset, tạo branch cứu hộ thứ hai:

~~~bash
git branch rescue/demo-before-reset <old-oid>
git log --oneline rescue/demo-before-reset
~~~

So sánh branch hiện tại với branch rescue:

~~~bash
git diff rescue/demo-before-reset...HEAD
git log --graph --decorate --oneline --all
~~~

### Bài tập C — Tìm commit unreachable

Trong repository lab, xóa một branch rescue phụ để tạo commit unreachable, sau đó tìm:

~~~bash
git branch -D rescue/demo-before-reset
git fsck --full --no-reflogs --unreachable
~~~

Tìm dòng <code>unreachable commit</code>, xem commit và tạo lại một branch mới. Thử nghiệm giúp hiểu rằng commit có thể còn trong object database dù không còn tên branch.

## 26. Checklist khi gặp sự cố

- [ ] Đã dừng các thao tác reset, rebase, gc hoặc prune không cần thiết.
- [ ] Đã kiểm tra working tree và bảo toàn thay đổi local còn lại.
- [ ] Đã kiểm tra branch, tag, remote-tracking refs và các clone khác.
- [ ] Đã đọc HEAD reflog và branch reflog còn tồn tại.
- [ ] Đã xác định OID commit ứng viên bằng nội dung, parent và thời gian.
- [ ] Đã kiểm tra ORIG_HEAD nếu phù hợp.
- [ ] Đã dùng git fsck nếu reflog không có entry cần tìm.
- [ ] Đã tạo branch rescue để giữ commit trước khi chỉnh sửa tiếp.
- [ ] Đã phân biệt phục hồi commit với phục hồi file chưa commit.
- [ ] Đã xác minh lịch sử trước khi push hoặc khôi phục tên branch remote.
- [ ] Đã thông báo cho nhóm nếu branch dùng chung bị ảnh hưởng.

## 27. Những điểm cần ghi nhớ

- Branch là ref trỏ tới commit; xóa branch không đồng nghĩa object bị xóa ngay.
- Reflog ghi lại các lần HEAD và branch ref thay đổi trên máy local.
- Xem reflog bằng <code>git reflog</code>, <code>git reflog show HEAD</code> hoặc <code>git reflog show &lt;ref&gt;</code>.
- Sau khi xóa branch, branch reflog có thể mất cùng ref; HEAD reflog hoặc clone khác có thể vẫn giữ dấu vết.
- Sau reset hoặc rebase, tìm tip cũ trong reflog và kiểm tra commit trước khi phục hồi.
- <code>git fsck --full --no-reflogs --unreachable</code> giúp tìm commit không còn được refs/reflog giữ nhưng object vẫn tồn tại.
- Tạo branch rescue để giữ commit khỏi trạng thái unreachable.
- <code>ORIG_HEAD</code> đôi khi hữu ích nhưng có thể bị ghi đè.
- Reflog không khôi phục thay đổi working tree chưa commit bị <code>reset --hard</code> ghi đè.
- Reflog có thời hạn; tránh chạy expire, prune hoặc gc trong lúc chưa phục hồi xong.
- Reflog local không được push; clone khác và backup có thể là nguồn phục hồi bổ sung.

Reflog là một trong những công cụ cứu hộ quan trọng nhất của Git. Khi nhánh bị xóa hoặc di chuyển nhầm, hãy tìm commit cũ, xác minh nội dung, tạo branch cứu hộ rồi mới khôi phục tên nhánh hoặc cập nhật remote. Hành động sớm và tránh dọn object sẽ tăng đáng kể khả năng lấy lại lịch sử đã mất.

