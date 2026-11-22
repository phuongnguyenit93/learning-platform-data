# Reflog ghi lại sự di chuyển của tham chiếu và thời hạn lưu giữ

Đôi khi bạn vừa chạy <code>git reset --hard</code>, rebase nhầm nhánh, amend một commit hoặc xóa nhánh local rồi mới nhận ra mình cần lại commit cũ. Lịch sử thông thường bằng <code>git log</code> có thể không còn hiển thị commit đó vì commit không còn nằm trong chuỗi tổ tiên của nhánh hiện tại. Trong tình huống này, **reflog** là nơi nên kiểm tra đầu tiên: nó ghi lại các lần tham chiếu local di chuyển và có thể giúp tìm lại commit trước thao tác nhầm.

Reflog rất hữu ích cho việc phục hồi, nhưng không phải bản sao lưu vô thời hạn. Các mục reflog có chính sách hết hạn; sau khi mục hết hạn và đối tượng Git không còn được tham chiếu, quá trình garbage collection có thể dọn các đối tượng không còn dùng đến. Hiểu reflog ghi gì, lưu ở đâu và giữ trong bao lâu giúp bạn phục hồi đúng lúc và tránh dựa vào nó như một phương án sao lưu duy nhất.

Bài này thuộc chương **Tìm lỗi và phục hồi** của module **SOURCE_CONTROL_GIT**. Module hướng dẫn Git từ working tree, staging area, commit và lịch sử đến branch, merge, rebase, remote và tag; đồng thời rèn cách cộng tác qua nhánh, giải quyết xung đột, truy tìm thay đổi và khôi phục thao tác sai mà vẫn bảo toàn lịch sử quan trọng. Reflog bổ sung một góc nhìn quan trọng cho việc truy tìm và phục hồi các thao tác đã làm thay đổi tham chiếu trong repository local.

## 1. Reflog là gì?

Reflog là viết tắt của **reference log**. Đây là nhật ký ghi lại các lần giá trị của một tham chiếu Git được cập nhật trong repository local. Tham chiếu là tên trỏ đến một đối tượng Git, thường là commit, ví dụ:

- <code>HEAD</code>: vị trí hiện tại mà repository đang checkout.
- <code>refs/heads/main</code>: nhánh local có tên <code>main</code>.
- <code>refs/heads/feature/login</code>: nhánh local <code>feature/login</code>.
- <code>refs/remotes/origin/main</code>: remote-tracking branch ghi nhận vị trí nhánh <code>main</code> trên remote <code>origin</code>.

Khi một tham chiếu di chuyển từ commit này sang commit khác, Git có thể ghi lại sự kiện đó trong reflog. Ví dụ, khi bạn tạo commit mới trên nhánh hiện tại, nhánh và HEAD được cập nhật. Khi checkout sang nhánh khác, HEAD chuyển sang vị trí mới. Khi reset, rebase hoặc cherry-pick, các tham chiếu cũng có thể được cập nhật và reflog ghi nhận những lần di chuyển này.

Một mục reflog thường cho biết:

- Giá trị commit mà tham chiếu trỏ đến sau lần cập nhật.
- Thông tin hành động, chẳng hạn commit, checkout, reset hoặc rebase.
- Thời điểm sự kiện xảy ra.
- Danh tính người thực hiện theo môi trường Git hiện tại.

Reflog là dữ liệu phục vụ quản lý tham chiếu trong bản clone hiện tại. Nó không phải một phần của đồ thị commit được chia sẻ giữa các thành viên qua fetch hoặc push.

## 2. Reflog khác git log như thế nào?

Hai lệnh trả lời hai câu hỏi khác nhau:

- <code>git log</code> hiển thị các commit có thể đi đến từ commit hoặc tham chiếu được chọn theo quan hệ cha-con.
- <code>git reflog</code> hiển thị lịch sử các lần tham chiếu local được cập nhật, kể cả khi một commit không còn nằm trong lịch sử hiện tại của nhánh.

Ví dụ, bạn có lịch sử:

~~~text
A---B---C   main
~~~

Sau đó chạy:

~~~bash
git reset --hard HEAD~1
~~~

Nhánh <code>main</code> di chuyển từ commit <code>C</code> về <code>B</code>:

~~~text
A---B   main
     \
      C   (không còn là tip của main)
~~~

Lúc này <code>git log main</code> chỉ hiển thị <code>B</code> và các commit tổ tiên của nó. Commit <code>C</code> không còn nằm trong lịch sử có thể đi đến từ <code>main</code>. Tuy nhiên, reflog của HEAD hoặc nhánh <code>main</code> có thể vẫn ghi nhận vị trí trước khi reset, giúp bạn tìm lại hash của <code>C</code>.

| Tiêu chí | git log | git reflog |
|---|---|---|
| Ghi nhận | Lịch sử commit theo quan hệ cha-con | Các lần tham chiếu local di chuyển |
| Commit không còn thuộc nhánh hiện tại | Thường không thấy nếu không có ref khác trỏ tới | Có thể vẫn thấy nếu mục reflog còn hiệu lực |
| Phạm vi | Đồ thị commit có thể truy cập từ ref được chọn | Nhật ký trong repository local |
| Chia sẻ qua push/fetch | Lịch sử commit có thể được chia sẻ | Reflog không được push/fetch sang máy khác |
| Thời hạn | Commit còn tồn tại khi được tham chiếu hoặc đối tượng chưa bị dọn | Mục reflog có chính sách hết hạn riêng |

Reflog không thay thế <code>git log</code>. Khi muốn hiểu lịch sử dự án và các commit đã tích hợp, hãy dùng log. Khi muốn biết HEAD hoặc nhánh local đã từng trỏ đến đâu, hãy kiểm tra reflog.

## 3. Những thao tác thường tạo mục reflog

Reflog có thể ghi lại các thao tác làm thay đổi tham chiếu, chẳng hạn:

| Thao tác | Điều có thể xuất hiện trong reflog |
|---|---|
| <code>git commit</code> | HEAD và nhánh hiện tại tiến đến commit mới |
| <code>git switch</code> hoặc <code>git checkout</code> | HEAD chuyển sang nhánh hoặc commit khác |
| <code>git reset</code> | HEAD và nhánh hiện tại di chuyển đến commit được chọn |
| <code>git commit --amend</code> | HEAD và nhánh được cập nhật sang commit thay thế |
| <code>git rebase</code> | HEAD và nhánh di chuyển qua các commit được phát lại |
| <code>git merge</code> | Nhánh hiện tại được cập nhật sau khi merge hoàn tất |
| <code>git cherry-pick</code> | HEAD và nhánh di chuyển đến commit mới sau khi áp dụng thành công |
| <code>git fetch</code> | Remote-tracking ref có thể được cập nhật |

Không phải mọi lệnh Git đều tạo một mục reflog. Các thao tác chỉ sửa working tree hoặc index mà không cập nhật tham chiếu thường không tạo mục reflog tương ứng. Ví dụ, sửa một tệp trong editor, chạy <code>git add</code> hoặc xem <code>git diff</code> không làm nhánh di chuyển.

Trong repository không bare, Git thường bật reflog cho HEAD và các nhánh local; remote-tracking refs cũng có thể có reflog theo cấu hình. Cấu hình <code>core.logAllRefUpdates</code> điều khiển việc tạo reflog cho các nhóm tham chiếu mặc định. Với giá trị <code>always</code>, Git tạo reflog cho nhiều tham chiếu hơn. Vì vậy, không nên giả định mọi ref trong mọi repository đều chắc chắn có reflog.

## 4. Xem reflog

Lệnh cơ bản:

~~~bash
# Xem reflog của HEAD
git reflog

# Cách viết tường minh
git reflog show HEAD

# Xem reflog của một nhánh local
git reflog show main

# Xem reflog của tất cả tham chiếu có reflog
git reflog show --all
~~~

Kết quả thường có dạng:

~~~text
e4f5a6b HEAD@{0}: reset: moving to HEAD~1
c3d4e5f HEAD@{1}: commit: add payment validation
b2c3d4e HEAD@{2}: commit: create payment endpoint
a1b2c3d HEAD@{3}: checkout: moving from feature/payment to main
~~~

Trong ví dụ:

- <code>HEAD@{0}</code> là mục mới nhất của reflog HEAD.
- <code>HEAD@{1}</code> là mục đứng ngay trước mục mới nhất.
- Mục có thông điệp <code>commit: add payment validation</code> cho biết HEAD từng trỏ đến commit <code>c3d4e5f</code>.
- Mục reset mới nhất ghi nhận lần di chuyển HEAD về <code>HEAD~1</code>.

Có thể thêm thời gian để dễ xác định sự kiện:

~~~bash
git reflog --date=local
git reflog show --date=iso main
git reflog show --all --date=relative
~~~

Các định dạng thời gian thường dùng gồm <code>relative</code>, <code>local</code>, <code>iso</code> và <code>iso-strict</code>. Chọn định dạng phù hợp để đối chiếu với thời điểm bạn thực hiện thao tác.

### Xem chi tiết một mục reflog

Reflog hiển thị hash commit mà bạn có thể kiểm tra bằng các lệnh khác:

~~~bash
# Xem nội dung commit được ghi nhận
git show c3d4e5f

# Xem danh sách tệp thay đổi
git show --stat c3d4e5f

# Xem commit và lịch sử xung quanh
git log --oneline --graph --decorate c3d4e5f
~~~

Đừng phục hồi chỉ dựa vào một dòng thông điệp. Hãy xác minh hash, nội dung commit, nhánh và thời điểm để chắc chắn bạn chọn đúng trạng thái.

## 5. Cú pháp tham chiếu reflog

Git cho phép tham chiếu một mục reflog bằng cú pháp:

~~~text
<ref>@{<selector>}
~~~

Một số cách chọn phổ biến:

| Cú pháp | Ý nghĩa |
|---|---|
| <code>HEAD@{0}</code> | Mục reflog mới nhất của HEAD |
| <code>HEAD@{1}</code> | Mục ngay trước mục mới nhất |
| <code>main@{2}</code> | Mục thứ ba tính từ mới nhất trong reflog của nhánh main |
| <code>HEAD@{yesterday}</code> | Vị trí HEAD tại mốc thời gian được Git phân tích là hôm qua |
| <code>main@{2.hours.ago}</code> | Vị trí nhánh main khoảng hai giờ trước |

Chỉ số trong <code>@{n}</code> là thứ tự mục reflog, không phải số commit cha. <code>HEAD~2</code> đi ngược hai quan hệ cha trong đồ thị commit; <code>HEAD@{2}</code> chọn mục reflog thứ ba gần nhất. Hai cách tham chiếu này có ý nghĩa hoàn toàn khác nhau.

Ví dụ:

~~~bash
# Xem vị trí HEAD ở mục reflog trước đó
git show "HEAD@{1}"

# Xem trạng thái nhánh main ở một mốc thời gian
git show "main@{yesterday}"

# So sánh commit hiện tại với trạng thái HEAD trước đó
git diff "HEAD@{1}" HEAD
~~~

Trong PowerShell, đặt tham chiếu có dấu ngoặc nhọn trong dấu nháy kép để tránh shell diễn giải ký tự đặc biệt. Trên Bash hoặc shell khác, cũng nên đặt trong dấu nháy khi tham chiếu thời gian có khoảng trắng.

## 6. Phục hồi sau git reset --hard

Một tình huống phổ biến là reset nhầm commit:

~~~bash
# Trạng thái trước thao tác
git log --oneline -5

# Lệnh nhầm: lùi nhánh một commit và loại thay đổi khỏi index/working tree
git reset --hard HEAD~1
~~~

Nếu nhận ra ngay sau đó rằng commit vừa bỏ vẫn cần thiết, đừng tiếp tục commit hoặc reset thêm. Kiểm tra reflog:

~~~bash
git reflog --date=local
~~~

Giả sử mục reflog cho thấy commit trước reset là <code>c3d4e5f</code>. Trước khi di chuyển nhánh, hãy tạo một nhánh cứu hộ trỏ đến commit đó:

~~~bash
git show c3d4e5f
git branch rescue/main-before-reset c3d4e5f
~~~

Nhánh cứu hộ giúp giữ commit ở một tham chiếu dễ tìm. Sau khi kiểm tra nội dung, nếu mục tiêu là đưa nhánh hiện tại trở lại commit đó và bạn đã xác nhận không có công việc mới cần giữ, có thể dùng:

~~~bash
git switch main
git reset --hard rescue/main-before-reset
~~~

Lệnh reset hard cập nhật cả nhánh, index và working tree. Chỉ chạy sau khi đã kiểm tra trạng thái và xác nhận không có thay đổi cần giữ; nếu có công việc mới, hãy tích hợp hoặc sao lưu trước.

Nếu chỉ muốn lấy lại nội dung để tiếp tục làm việc mà chưa muốn di chuyển nhánh, có thể tạo nhánh cứu hộ rồi so sánh hoặc cherry-pick commit cần thiết. Luôn chọn phương án ít tác động nhất phù hợp với mục tiêu.

**Giới hạn quan trọng:** reflog ghi lại sự di chuyển của tham chiếu, không ghi lại mọi nội dung chưa commit trong working tree. Nếu <code>git reset --hard</code> xóa các chỉnh sửa chưa từng được commit, reflog không thể tự khôi phục chúng. Các đối tượng nội dung từng được ghi vào Git, chẳng hạn qua staging, đôi khi còn có thể tìm thấy bằng công cụ phục hồi đối tượng, nhưng không có bảo đảm.

## 7. Phục hồi sau rebase hoặc amend nhầm

Rebase và amend thường tạo commit mới, khiến hash cũ không còn nằm trên nhánh hiện tại. Nếu muốn quay lại lịch sử trước thao tác, kiểm tra reflog:

~~~bash
git reflog --date=local
~~~

Ví dụ kết quả:

~~~text
91ab234 HEAD@{0}: rebase (finish): returning to refs/heads/feature/report
91ab234 HEAD@{1}: rebase (pick): docs: update report guide
7cd8910 HEAD@{2}: rebase (start): checkout main
45ef678 HEAD@{3}: commit (amend): feat: generate report
12ab345 HEAD@{4}: commit: feat: generate report
~~~

Trong trường hợp này, commit <code>12ab345</code> là phiên bản trước amend. Nếu rebase đã làm lịch sử thay đổi không như mong muốn, bạn có thể tạo nhánh cứu hộ từ commit trước khi rebase:

~~~bash
git branch rescue/report-before-rebase 12ab345
~~~

Hãy kiểm tra commit đó bằng <code>git show</code> và so sánh với nhánh hiện tại trước khi quyết định reset hoặc cherry-pick. Với một chuỗi commit đã viết lại, có thể cần khôi phục cả tip của nhánh trước rebase thay vì chỉ lấy một commit riêng lẻ.

Nếu rebase vẫn đang chạy và chưa hoàn tất, cách hủy trực tiếp thường là:

~~~bash
git rebase --abort
~~~

Reflog hữu ích hơn khi thao tác đã hoàn tất hoặc trạng thái rebase không còn hoạt động. Không cần dùng reflog để thay thế lệnh abort khi Git vẫn đang quản lý một phiên rebase dở dang.

## 8. Phục hồi nhánh local bị xóa

Nếu xóa nhánh local nhưng sau đó nhận ra cần lại commit cuối cùng của nhánh, hãy tìm hash trong reflog:

~~~bash
git reflog show --all --date=local
~~~

Tìm mục có thông điệp checkout, commit, merge hoặc rebase liên quan đến nhánh đã xóa. Nếu tìm được hash tip trước khi xóa, tạo lại nhánh:

~~~bash
git branch feature/recovered <commit-hash>
~~~

Việc xóa nhánh local có thể đồng thời xóa reflog riêng của nhánh đó. Trong trường hợp này, reflog HEAD hoặc reflog của tham chiếu khác có thể vẫn giữ mục liên quan. Nếu không tìm thấy, có thể cần kiểm tra các đối tượng unreachable bằng công cụ khác; kết quả phụ thuộc việc đối tượng còn tồn tại và chưa bị garbage collection dọn đi.

Đối với nhánh trên remote đã bị xóa, reflog local chỉ có thể giúp tìm commit nếu bản clone của bạn từng ghi nhận commit đó hoặc còn tham chiếu đến nó. Reflog trên máy của bạn không phải nhật ký của máy chủ Git.

## 9. Reflog lưu ở đâu và có phạm vi ra sao?

Reflog là dữ liệu local bên trong repository. Trong cấu trúc Git truyền thống, các tệp reflog thường nằm dưới:

~~~text
.git/logs/HEAD
.git/logs/refs/heads/main
.git/logs/refs/remotes/origin/main
~~~

Với linked worktree, Git có thể lưu một số dữ liệu trong thư mục quản lý chung hoặc thư mục worktree riêng; vì vậy không nên tự chỉnh sửa các tệp reflog bằng editor. Hãy dùng lệnh Git để đọc và quản lý chúng.

Các đặc điểm cần nhớ:

- Reflog thuộc về bản clone hoặc repository local đang thao tác.
- Clone repository mới không nhận reflog từ máy đã clone nguồn.
- Push commit không gửi reflog lên máy chủ.
- Fetch cập nhật remote-tracking refs và có thể ghi reflog local cho các refs đó nếu cấu hình cho phép.
- Máy chủ có thể có reflog riêng để quản trị, nhưng bạn không thể xem nhật ký đó bằng <code>git reflog</code> trong bản clone thông thường.

Do đó, khi một đồng đội cần phục hồi commit không còn được tham chiếu trong bản clone của họ, reflog trên máy của bạn có thể không giúp trực tiếp. Bạn có thể chia sẻ commit hash hoặc tạo một nhánh cứu hộ và push theo quy trình của nhóm nếu đối tượng vẫn còn tồn tại và được phép chia sẻ.

## 10. Thời hạn lưu giữ reflog mặc định

Reflog không lưu mọi mục mãi mãi. Git có các cấu hình điều khiển thời gian hết hạn:

| Cấu hình | Mặc định thường dùng | Áp dụng |
|---|---:|---|
| <code>gc.reflogExpire</code> | 90 ngày | Mục reflog có đối tượng còn được xem là reachable |
| <code>gc.reflogExpireUnreachable</code> | 30 ngày | Mục reflog trỏ đến đối tượng không còn reachable từ tip hiện tại của ref |

Hai thời hạn này là giá trị mặc định của Git và có thể được thay đổi bởi cấu hình repository, cấu hình người dùng hoặc cấu hình theo từng ref. Mục reflog của một ref có thể có chính sách riêng nếu dự án thiết lập cấu hình phù hợp.

Ví dụ:

- Commit vẫn nằm trong lịch sử của nhánh hiện tại thường được xem là reachable. Mục reflog cũ liên quan có thể được giữ theo thời hạn <code>gc.reflogExpire</code>.
- Commit bị bỏ khỏi tip sau reset hoặc rebase và không còn được ref nào khác giữ lại có thể là unreachable. Mục reflog liên quan thường có thời hạn ngắn hơn theo <code>gc.reflogExpireUnreachable</code>.

Đây là thời hạn áp dụng cho **mục reflog**, không phải cam kết rằng đối tượng commit sẽ bị xóa đúng vào ngày đó. Sau khi mục reflog hết hạn, đối tượng unreachable có thể vẫn tồn tại một thời gian cho đến khi garbage collection prune đối tượng không còn được tham chiếu. Ngược lại, không nên dựa vào khoảng thời gian này để trì hoãn việc phục hồi.

### Kiểm tra cấu hình hiện tại

~~~bash
git config --show-origin --get gc.reflogExpire
git config --show-origin --get gc.reflogExpireUnreachable
git config --show-origin --get core.logAllRefUpdates
~~~

Nếu lệnh không in giá trị, có thể cấu hình đó chưa được đặt tường minh và Git đang dùng mặc định phù hợp với phiên bản hoặc môi trường hiện tại. <code>--show-origin</code> cho biết file cấu hình cung cấp giá trị, giúp bạn xác định nó đến từ local, global hay system.

### Điều chỉnh thời hạn

Nếu dự án cần giữ reflog lâu hơn, có thể cấu hình ở cấp repository:

~~~bash
# Ví dụ: giữ các mục reachable trong 180 ngày
git config gc.reflogExpire 180.days

# Ví dụ: giữ các mục unreachable trong 60 ngày
git config gc.reflogExpireUnreachable 60.days
~~~

Các lệnh trên thay đổi cấu hình local của repository hiện tại. Nếu dùng <code>--global</code>, giá trị sẽ áp dụng cho các repository của người dùng có cấu hình kế thừa. Hãy thống nhất chính sách với nhóm; giữ reflog lâu hơn cần thêm dung lượng và vẫn không thay thế backup.

Có thể dùng giá trị <code>never</code> để yêu cầu không hết hạn theo chính sách đó, nhưng không nên áp dụng tùy tiện cho mọi repository. Cần hiểu tác động lưu trữ và quy trình bảo trì trước khi thay đổi.

## 11. Git gc và việc dọn dẹp đối tượng

Garbage collection là quá trình bảo trì repository. Git dùng các hoạt động này để tối ưu dữ liệu và dọn các đối tượng không còn được tham chiếu sau khi các điều kiện hết hạn phù hợp.

Lệnh:

~~~bash
git gc
~~~

có thể thực hiện bảo trì repository và xử lý reflog hết hạn theo chính sách cấu hình. Trong nhiều trường hợp, Git tự chạy bảo trì hoặc auto-gc sau một số thao tác; người dùng không cần chạy thủ công thường xuyên.

Không nên dùng các lệnh dọn dẹp mạnh như <code>git reflog expire --expire=now --all</code> hoặc <code>git gc --prune=now</code> trong lúc đang cần phục hồi dữ liệu. Chúng có thể làm mất các dấu vết hoặc đối tượng unreachable mà bạn đang dựa vào để tìm lại commit.

Nếu cần đánh giá trước khi dọn dẹp, hãy kiểm tra cấu hình và trạng thái repository, tạo backup phù hợp, rồi thực hiện theo chính sách bảo trì. Việc xóa mục reflog và việc xóa đối tượng Git là các bước có liên quan nhưng không phải một thao tác đồng nhất.

## 12. Khi reflog không tìm thấy commit

Nếu reflog không còn mục cần tìm, có thể do:

- Mục đã hết hạn theo chính sách reflog.
- Reflog của nhánh đã bị xóa cùng nhánh.
- Reflog không được bật cho tham chiếu cần kiểm tra.
- Bạn đang xem reflog của một bản clone khác.
- Commit chưa từng được tạo, hoặc thay đổi chỉ tồn tại trong working tree/index.
- Đối tượng Git đã bị garbage collection dọn đi.

Nếu đối tượng có thể vẫn còn trong cơ sở dữ liệu Git nhưng không còn ref hoặc reflog trỏ tới, một công cụ chẩn đoán có thể giúp tìm đối tượng unreachable:

~~~bash
git fsck --full --no-reflogs --unreachable
~~~

Lệnh này liệt kê các đối tượng không còn reachable theo phạm vi kiểm tra. Kết quả có thể gồm commit, tree hoặc blob. Nếu tìm được commit nghi ngờ, hãy xem nó bằng <code>git show</code> rồi tạo nhánh cứu hộ để giữ lại:

~~~bash
git show <commit-hash>
git branch rescue/found-commit <commit-hash>
~~~

Không phải đối tượng unreachable nào cũng là commit bạn cần. Hãy xác minh nội dung và quan hệ lịch sử trước khi tạo nhánh hoặc tích hợp. Nếu đối tượng đã bị prune, reflog và fsck đều không thể tái tạo nội dung đã mất; lúc đó cần tìm bản clone, backup hoặc artifact khác còn giữ dữ liệu.

## 13. Quy trình phục hồi dựa trên reflog

Khi phát hiện thao tác Git nhầm, hãy làm theo trình tự:

1. Dừng các thao tác có thể tiếp tục di chuyển nhánh hoặc ghi đè trạng thái.
2. Chạy <code>git status</code> để biết working tree và index hiện tại.
3. Xem <code>git reflog --date=local</code> và <code>git reflog show --all</code>.
4. Xác định entry trước thao tác nhầm bằng thời gian, thông điệp và hash.
5. Dùng <code>git show</code> để xác minh commit cần phục hồi.
6. Tạo nhánh cứu hộ trỏ đến commit đó trước khi di chuyển bất kỳ ref nào.
7. So sánh nhánh cứu hộ với trạng thái hiện tại và chọn cách phục hồi phù hợp.
8. Chỉ reset hoặc push sau khi đã kiểm tra các thay đổi cần giữ và phối hợp với người liên quan.

Ví dụ tổng quát:

~~~bash
# Kiểm tra trạng thái
git status

# Tìm các vị trí HEAD từng trỏ đến
git reflog --date=local

# Xem commit nghi ngờ
git show <commit-hash>

# Giữ commit bằng một nhánh cứu hộ
git branch rescue/recovered-state <commit-hash>

# So sánh với nhánh hiện tại
git log --oneline --graph --decorate rescue/recovered-state
git diff rescue/recovered-state..HEAD
~~~

Tạo nhánh cứu hộ là bước ít tác động và giúp giữ commit không bị mất thêm trong lúc phân tích. Sau đó mới quyết định reset, merge hoặc cherry-pick tùy mục tiêu.

## 14. Những hiểu lầm thường gặp

| Hiểu lầm | Cách hiểu chính xác |
|---|---|
| Reflog là lịch sử commit thứ hai | Reflog ghi các lần ref local di chuyển; git log thể hiện quan hệ cha-con của commit. |
| <code>HEAD@{2}</code> tương đương <code>HEAD~2</code> | Một bên là mục reflog thứ ba gần nhất, bên kia là commit tổ tiên cách hai bước. |
| Reflog được chia sẻ cho cả nhóm | Mỗi bản clone có reflog riêng; push và fetch không truyền reflog. |
| Reflog giữ mọi thay đổi trong editor | Reflog theo dõi ref, không lưu các chỉnh sửa chưa commit trong working tree. |
| Reflog luôn giữ commit mãi mãi | Các mục có thời hạn hết hạn; đối tượng unreachable có thể được garbage collection dọn sau đó. |
| Reset hard xong luôn khôi phục được mọi tệp bằng reflog | Reflog có thể tìm lại commit, nhưng không bảo đảm khôi phục dữ liệu chưa từng được commit. |
| Nhánh bị xóa thì commit chắc chắn mất ngay | Commit có thể vẫn còn trong reflog khác hoặc object database cho đến khi bị dọn. |
| Chạy gc là xóa tất cả commit cũ | Git dọn các đối tượng không còn được tham chiếu theo điều kiện và thời hạn, không xóa toàn bộ lịch sử hợp lệ. |

## 15. Bài tập tự kiểm tra

Thực hành trong một repository thử nghiệm:

1. Tạo hai commit trên nhánh <code>feature/reflog-demo</code>, sau đó chạy <code>git reflog</code>. Xác định entry tương ứng với từng commit.
2. Chuyển sang nhánh khác rồi quay lại. Quan sát các entry checkout trong reflog HEAD.
3. Chạy <code>git reset --hard HEAD~1</code> trong repository thử nghiệm. Dùng reflog tìm hash commit vừa bị bỏ khỏi tip.
4. Tạo nhánh <code>rescue/demo</code> trỏ đến hash tìm được. Kiểm tra commit bằng <code>git show</code>.
5. So sánh <code>git log</code> và <code>git reflog</code> sau reset. Vì sao chúng hiển thị các thông tin khác nhau?
6. Xem reflog của nhánh bằng <code>git reflog show feature/reflog-demo</code> và so sánh với reflog HEAD.
7. Kiểm tra giá trị <code>gc.reflogExpire</code> và <code>gc.reflogExpireUnreachable</code>. Giải thích vì sao hai thời hạn mặc định khác nhau.
8. Thử cấu hình thời hạn trong repository thử nghiệm rồi đọc lại bằng <code>git config --show-origin</code>.
9. Giải thích vì sao reflog không thể bảo đảm phục hồi một tệp đã sửa nhưng chưa từng được commit.

Khi biết cách đọc reflog, chọn đúng commit theo thứ tự hoặc thời gian, giữ commit bằng nhánh cứu hộ và hiểu giới hạn lưu giữ, bạn có thêm một công cụ quan trọng để xử lý thao tác Git nhầm. Hãy phục hồi càng sớm càng tốt, xác minh nội dung trước khi di chuyển nhánh và duy trì backup phù hợp cho dữ liệu quan trọng.
