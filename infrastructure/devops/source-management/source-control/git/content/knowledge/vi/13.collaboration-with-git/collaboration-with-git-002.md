# Chu trình nhận việc, tạo nhánh, commit, đồng bộ và bàn giao

Git giúp nhiều người cùng phát triển một dự án bằng cách lưu lịch sử thay đổi và cho phép mỗi người làm việc trên nhánh riêng. Nhưng có Git trong dự án chưa đủ để việc cộng tác diễn ra trôi chảy. Nhóm cần một chu trình thống nhất: nhận yêu cầu, cập nhật mã nguồn nền, tạo nhánh, thực hiện thay đổi, commit, đồng bộ, review và bàn giao kết quả.

Một chu trình rõ ràng giúp mọi người biết ai đang xử lý việc gì, thay đổi nằm ở đâu, phiên bản nào đã được kiểm thử và người tiếp nhận cần làm bước tiếp theo nào. Bài học này trình bày quy trình cộng tác thường dùng trong nhóm phát triển, từ lúc nhận một công việc đến khi nhánh được tích hợp và bàn giao.

## 1. Bức tranh tổng thể của một công việc

Một công việc thường đi qua các bước sau:

1. **Nhận việc:** Đọc yêu cầu, xác định kết quả cần đạt, phạm vi và tiêu chí hoàn thành.
2. **Chuẩn bị:** Kiểm tra repository, remote, working tree và cập nhật branch nền.
3. **Tạo nhánh:** Tạo branch riêng từ commit nền mới nhất để cô lập thay đổi.
4. **Thực hiện:** Sửa mã nguồn, chạy kiểm tra và chia thay đổi thành các commit có ý nghĩa.
5. **Đồng bộ:** Lấy thay đổi mới từ remote và tích hợp vào nhánh công việc theo quy ước của nhóm.
6. **Chia sẻ và review:** Push branch, mở pull request hoặc merge request, giải thích thay đổi và xử lý phản hồi.
7. **Tích hợp:** Nhánh được merge theo chính sách của dự án sau khi đạt các điều kiện review và kiểm tra.
8. **Bàn giao:** Cung cấp trạng thái, commit, kết quả kiểm thử, phần còn lại và thông tin cần thiết cho người tiếp nhận.

~~~mermaid
flowchart TD
    A[Nhận yêu cầu và tiêu chí hoàn thành] --> B[Kiểm tra repository và cập nhật branch nền]
    B --> C[Tạo branch công việc]
    C --> D[Sửa mã và chạy kiểm tra]
    D --> E[Review diff và tạo commit]
    E --> F[Fetch và đồng bộ thay đổi mới]
    F --> G[Push branch và mở PR/MR]
    G --> H[Review, sửa phản hồi và kiểm tra lại]
    H --> I{Đạt điều kiện tích hợp?}
    I -- Chưa --> D
    I -- Đạt --> J[Merge theo chính sách dự án]
    J --> K[Bàn giao và dọn branch]
~~~

Các bước có thể lặp lại. Chẳng hạn, reviewer yêu cầu sửa thêm thì người thực hiện tiếp tục commit và push lên cùng branch; pull request thường tự cập nhật theo các commit mới.

## 2. Nhận việc và thống nhất phạm vi

Trước khi sửa mã, hãy hiểu điều cần thay đổi. Một ticket hoặc yêu cầu công việc nên giúp trả lời được:

- Vấn đề hiện tại là gì và ai chịu ảnh hưởng?
- Hành vi mong muốn sau khi hoàn thành là gì?
- Phần nào nằm trong phạm vi và phần nào chưa cần xử lý?
- Có tiêu chí chấp nhận cụ thể hoặc trường hợp kiểm thử nào?
- Có phụ thuộc vào API, dữ liệu, cấu hình hoặc công việc của người khác không?
- Ai review và ai có quyền tích hợp thay đổi?

Ví dụ, yêu cầu “thêm bộ lọc trạng thái cho danh sách đơn hàng” cần được làm rõ bộ lọc gồm những trạng thái nào, có kết hợp với tìm kiếm hiện tại hay không, cách xử lý khi không có kết quả và giao diện cần giữ trạng thái bộ lọc như thế nào.

Nếu yêu cầu còn mơ hồ, trao đổi với người giao việc trước khi mở rộng phạm vi bằng suy đoán. Có thể ghi lại các quyết định quan trọng trong ticket hoặc pull request để người review và người nhận bàn giao có cùng ngữ cảnh.

Một công việc đủ rõ thường có:

- Mục tiêu và kết quả mong đợi.
- Phạm vi tệp hoặc thành phần dự kiến bị ảnh hưởng.
- Tiêu chí chấp nhận có thể kiểm tra.
- Rủi ro, phụ thuộc và người cần phối hợp.

Tên branch và commit message nên phản ánh công việc đã thống nhất. Không nên dùng một branch chung cho nhiều ticket không liên quan vì review, rollback và truy tìm nguyên nhân sẽ khó hơn.

## 3. Chuẩn bị repository trước khi tạo nhánh

### 3.1. Kiểm tra repository và remote

Nếu chưa có repository local, clone từ địa chỉ mà nhóm cung cấp:

~~~
git clone https://example.com/team/store.git
cd store
~~~

Nếu repository đã có trên máy, chuyển vào đúng thư mục dự án rồi kiểm tra:

~~~
git rev-parse --show-toplevel
git remote -v
git status -sb
git branch -vv
~~~

Các lệnh này giúp xác nhận:

- git rev-parse --show-toplevel cho biết thư mục gốc của repository.
- git remote -v cho biết địa chỉ fetch và push.
- git status -sb cho biết branch hiện tại và trạng thái working tree.
- git branch -vv cho biết branch local và upstream mà chúng theo dõi.

Nếu remote trỏ nhầm dự án hoặc tài khoản không có quyền truy cập, cần xử lý trước khi tiếp tục. Đừng push mã nguồn vào một remote chưa xác minh.

### 3.2. Kiểm tra thay đổi đang có

Trước khi đổi branch hoặc đồng bộ, kiểm tra trạng thái:

~~~
git status
git diff
git diff --cached
~~~

Nếu có thay đổi đang làm dở, hãy xác định chúng thuộc công việc nào. Có thể commit khi phần thay đổi đã thành một đơn vị có ý nghĩa, hoặc stash khi cần tạm cất thay đổi để chuyển ngữ cảnh:

~~~
git stash push -m "WIP: save local filter changes"
git stash list
~~~

Sau khi quay lại đúng branch, có thể khôi phục stash:

~~~
git stash apply
~~~

git stash apply giữ lại stash để bạn kiểm tra. Khi đã xác nhận nội dung được khôi phục an toàn, mới cân nhắc xóa stash bằng git stash drop. git stash pop vừa áp dụng vừa xóa stash nếu thành công, nên cần hiểu rõ thao tác trước khi dùng.

Không dùng git reset --hard hoặc git clean -fd chỉ để làm working tree sạch khi chưa biết thay đổi hiện có là gì. Những lệnh này có thể làm mất công việc chưa được lưu.

### 3.3. Cập nhật branch nền

Giả sử nhóm dùng main làm branch nền và branch local theo dõi origin/main:

~~~
git switch main
git fetch origin
git status -sb
git pull --ff-only
~~~

fetch cập nhật thông tin từ remote; pull --ff-only đưa main local tiến lên khi có thể fast-forward. Nếu Git từ chối vì lịch sử đã phân nhánh, hãy xem các commit hai phía và làm theo chính sách đồng bộ của nhóm. Không tự ý reset branch nền để ép nó giống remote.

Một số dự án dùng develop, trunk hoặc một branch release làm nền. Hãy dùng branch được quy định trong dự án, không mặc định mọi repository đều dùng main.

## 4. Tạo branch riêng cho công việc

### 4.1. Vì sao nên làm việc trên branch riêng?

Branch giúp cô lập thay đổi của một công việc. Người thực hiện có thể commit nhiều lần, thử nghiệm và nhận review mà không làm thay đổi trực tiếp branch nền. Nhiều người cũng có thể phát triển các tính năng khác nhau song song.

Tạo branch từ branch nền vừa cập nhật:

~~~
git switch -c feature/order-status-filter
~~~

Hoặc dùng tên branch gắn với mã ticket:

~~~
git switch -c feature/ORD-142-status-filter
~~~

Tên branch nên ngắn, dễ đọc, không chứa khoảng trắng và giúp người khác hiểu mục đích. Một số quy ước thường gặp:

| Tiền tố | Mục đích | Ví dụ |
|---|---|---|
| feature/ | Tính năng mới | feature/order-filter |
| fix/ | Sửa lỗi | fix/order-total-rounding |
| docs/ | Tài liệu | docs/deployment-guide |
| refactor/ | Tái cấu trúc | refactor/payment-service |
| chore/ | Công việc bảo trì | chore/update-build-tool |

Tiền tố chỉ là quy ước; hãy ưu tiên chuẩn đặt tên mà repository đang sử dụng. Branch nên phục vụ một mục tiêu có thể review và tích hợp độc lập.

### 4.2. Xác nhận branch trước khi sửa

Sau khi tạo branch, kiểm tra:

~~~
git branch --show-current
git status -sb
git log --oneline --decorate -5
~~~

Đảm bảo branch hiện tại là branch công việc vừa tạo và điểm xuất phát đúng với branch nền. Nếu lỡ tạo branch từ commit cũ, có thể cần cập nhật branch trước khi bắt đầu; hãy làm việc đó trước khi tạo nhiều commit riêng.

## 5. Thực hiện thay đổi và tạo commit

### 5.1. Làm thay đổi theo từng đơn vị nhỏ

Trong lúc làm việc, nên chia thay đổi thành các phần có thể giải thích và kiểm tra. Ví dụ, công việc thêm bộ lọc đơn hàng có thể gồm:

1. Thêm tham số trạng thái vào lớp truy vấn.
2. Bổ sung xử lý trạng thái ở API.
3. Thêm điều khiển bộ lọc ở giao diện.
4. Bổ sung kiểm thử cho các trạng thái và trường hợp không có kết quả.

Không nhất thiết mỗi bước phải là một commit riêng. Mục tiêu là giữ diff dễ hiểu và commit đại diện cho một thay đổi hoàn chỉnh, có ý nghĩa. Một commit quá lớn thường khó review; quá nhiều commit vụn như “fix”, “try again”, “update” cũng làm lịch sử khó đọc.

### 5.2. Xem lại thay đổi trước khi stage

Các lệnh sau giúp kiểm tra nội dung:

~~~
git status
git diff
git diff --check
~~~

git diff --check phát hiện một số lỗi khoảng trắng như trailing whitespace. Hãy xem lại các tệp bị sửa, tránh đưa vào commit file sinh tự động, log, dữ liệu cá nhân, tệp môi trường hoặc thay đổi ngoài phạm vi ticket.

### 5.3. Stage và commit có chủ đích

Stage đúng các tệp liên quan:

~~~
git add src/orders/order-query.ts
git add tests/orders/order-query.test.ts
git diff --cached
git status
~~~

Nếu toàn bộ thay đổi trong working tree đều thuộc công việc và đã được xem xét, có thể dùng git add -A. Không nên dùng git add . theo thói quen khi chưa kiểm tra các tệp mới hoặc tệp nhạy cảm.

Tạo commit với thông điệp mô tả kết quả:

~~~
git commit -m "Add order status filter"
~~~

Một commit message tốt giúp người khác hiểu thay đổi mà không phải mở ngay từng tệp. Có thể dùng cấu trúc:

~~~
<type>: <mô tả ngắn>

<lý do hoặc ngữ cảnh nếu cần>
~~~

Ví dụ:

~~~
feat: add order status filter

Allow users to narrow the order list by its current status.
~~~

Các type như feat, fix, docs, refactor hay test là quy ước phổ biến, không phải yêu cầu bắt buộc của Git. Hãy tuân thủ convention của dự án.

Sau commit, kiểm tra:

~~~
git status -sb
git log -1 --oneline
git show --stat --oneline HEAD
~~~

Nếu working tree còn thay đổi, xác định đó là phần việc chưa hoàn tất hay nội dung vô tình bị bỏ sót. Không cho rằng một commit đã chứa mọi thay đổi chỉ vì lệnh commit chạy thành công.

## 6. Đồng bộ branch công việc với thay đổi mới

Trong khi bạn làm việc, đồng đội có thể cập nhật branch nền. Nếu branch công việc tồn tại lâu, nên đồng bộ định kỳ để phát hiện xung đột sớm.

Trước hết lấy dữ liệu mới:

~~~
git fetch origin
git log --oneline --graph --decorate --all
~~~

Sau đó chọn cách tích hợp theo quy ước nhóm.

### 6.1. Merge branch nền vào branch công việc

~~~
git switch feature/order-status-filter
git merge origin/main
~~~

Merge tạo một commit kết hợp khi lịch sử hai phía đã phân nhánh. Cách này giữ nguyên commit đã chia sẻ và thể hiện rõ điểm tích hợp. Nó thường phù hợp khi branch được nhiều người cùng sử dụng hoặc nhóm muốn tránh viết lại lịch sử.

### 6.2. Rebase branch công việc lên branch nền

~~~
git switch feature/order-status-filter
git rebase origin/main
~~~

Rebase phát lại các commit riêng của branch trên nền mới hơn, giúp lịch sử tuyến tính. Vì commit được phát lại có mã định danh mới, chỉ nên rebase branch mà bạn sở hữu hoặc branch chưa được người khác dựa vào, trừ khi nhóm đã thống nhất cách phối hợp.

Không có lựa chọn merge hoặc rebase đúng cho mọi nhóm. Hãy chọn theo chính sách của repository và giữ cách làm nhất quán trong cùng một nhánh công việc.

## 7. Giải quyết conflict khi đồng bộ

Conflict xảy ra khi Git không thể tự kết hợp các thay đổi. Nó thường xuất hiện khi hai nhánh sửa cùng một vùng nội dung hoặc một bên xóa tệp mà bên kia tiếp tục sửa.

Khi merge hoặc rebase dừng vì conflict, bắt đầu bằng:

~~~
git status
~~~

Git sẽ liệt kê các tệp cần xử lý. Trong tệp xung đột, bạn có thể thấy:

~~~
<<<<<<< HEAD
const statusLabel = "Processing";
=======
const statusLabel = "In progress";
>>>>>>> origin/main
~~~

Các dấu <<<<<<<, ======= và >>>>>>> phân chia nội dung từ hai phía. Hãy đọc ngữ cảnh, trao đổi với người tạo thay đổi nếu ý nghĩa nghiệp vụ chưa rõ, rồi chỉnh thành kết quả cuối cùng. Không đơn giản chọn một phía chỉ để làm sạch dấu conflict.

Sau khi chỉnh:

~~~
git diff
git add src/orders/status-label.ts
git status
~~~

Nếu đang merge, hoàn tất bằng commit theo yêu cầu của Git:

~~~
git commit
~~~

Nếu đang rebase, tiếp tục:

~~~
git rebase --continue
~~~

Nếu nhận ra đã chọn sai hướng hoặc muốn quay lại trước thao tác đang thực hiện, có thể hủy quy trình:

~~~
git merge --abort
~~~

hoặc:

~~~
git rebase --abort
~~~

Chỉ dùng lệnh abort khi đúng quy trình tương ứng đang diễn ra. Sau khi hoàn tất, chạy lại các kiểm tra phù hợp và xem diff để chắc chắn việc giải quyết conflict không làm mất logic từ một phía.

## 8. Push branch và mở yêu cầu review

### 8.1. Push branch lần đầu

Sau khi có commit, chia sẻ branch lên remote:

~~~
git push -u origin feature/order-status-filter
~~~

Tùy chọn -u thiết lập upstream cho branch local. Những lần push tiếp theo thường có thể dùng:

~~~
git push
~~~

Nếu push bị từ chối vì non-fast-forward, remote có thể đã có commit mới. Hãy fetch, xem lịch sử, tích hợp thay đổi đó bằng merge hoặc rebase theo chính sách nhóm rồi push lại. Không dùng git push --force như cách sửa mặc định vì nó có thể làm mất commit của người khác.

### 8.2. Tạo pull request hoặc merge request

Trên nền tảng lưu trữ Git, tạo pull request (PR) hoặc merge request (MR) từ branch công việc vào branch đích. Tên gọi tùy nền tảng; mục đích là đề nghị nhóm review và tích hợp thay đổi.

Một PR/MR hữu ích nên cung cấp:

- **Mục tiêu:** Liên kết ticket và mô tả vấn đề được giải quyết.
- **Thay đổi chính:** Những hành vi, API, cấu trúc hoặc tệp quan trọng đã thay đổi.
- **Cách kiểm tra:** Test đã chạy, lệnh đã dùng và kết quả.
- **Ảnh hưởng:** Thay đổi schema, cấu hình, dependency, dữ liệu hoặc khả năng tương thích.
- **Rủi ro và giới hạn:** Những trường hợp chưa xử lý hoặc điều cần reviewer chú ý.
- **Ảnh minh họa:** Với thay đổi giao diện, thêm ảnh hoặc video ngắn khi có ích.

Chọn reviewer theo khu vực mã nguồn và kiến thức cần thiết. Tránh chỉ định người review mà không cung cấp ngữ cảnh về phần cần chú ý.

### 8.3. Review là quá trình trao đổi

Người review thường xem:

- Thay đổi có đáp ứng yêu cầu và không mở rộng phạm vi không?
- Logic có đúng ở trường hợp biên và lỗi không?
- Có kiểm thử đủ cho hành vi mới không?
- Tên, cấu trúc và cách xử lý lỗi có phù hợp convention không?
- Có lộ bí mật, dữ liệu cá nhân hoặc thông tin nội bộ không?
- Thay đổi có ảnh hưởng đến hiệu năng, bảo mật, khả năng tương thích hoặc vận hành không?

Khi nhận phản hồi, hãy làm rõ nếu nhận xét chưa đủ cụ thể. Nếu đồng ý, cập nhật mã, chạy lại kiểm tra và commit. Push commit mới lên cùng branch để PR/MR được cập nhật.

Không nên sửa đổi âm thầm một thay đổi nghiệp vụ quan trọng mà không giải thích. Nếu không đồng ý với một đề xuất, trình bày lý do kỹ thuật và cùng reviewer thống nhất phương án.

## 9. Điều kiện tích hợp và hoàn tất công việc

Trước khi merge, kiểm tra các điều kiện mà dự án quy định. Thông thường gồm:

- Review đã được phê duyệt bởi đúng người hoặc số lượng reviewer yêu cầu.
- CI chạy thành công và các kiểm tra bắt buộc đã đạt.
- Branch không còn conflict với branch đích.
- Các cuộc thảo luận quan trọng đã được giải quyết.
- Nội dung tài liệu, migration, cấu hình và release note đã được cập nhật nếu cần.
- Người có thẩm quyền đã chấp thuận khi thay đổi có rủi ro hoặc ảnh hưởng production.

Nền tảng có thể hỗ trợ merge commit, squash merge hoặc rebase merge. Mỗi cách tạo lịch sử khác nhau:

| Cách tích hợp | Đặc điểm | Khi thường dùng |
|---|---|---|
| Merge commit | Giữ các commit của branch và tạo commit kết hợp | Muốn lưu dấu mốc branch được tích hợp |
| Squash merge | Gộp thay đổi của branch thành một commit trên branch đích | Muốn lịch sử branch chính gọn, mỗi PR thành một đơn vị |
| Rebase merge | Phát lại commit của branch trên branch đích rồi tích hợp tuyến tính | Nhóm yêu cầu lịch sử tuyến tính và commit riêng đã có chất lượng |

Chọn cách mà repository quy định. Sau khi merge, cập nhật branch nền ở local:

~~~
git switch main
git fetch origin
git pull --ff-only
~~~

Nếu nhóm dùng branch nền khác, thay main bằng tên branch tương ứng. Branch công việc đã merge thường có thể xóa theo chính sách dự án:

~~~
git branch -d feature/order-status-filter
git fetch --prune origin
~~~

git branch -d chỉ xóa branch local khi Git xác nhận branch đã được tích hợp. Nếu cần giữ branch để điều tra hoặc phục vụ công việc tiếp theo, hãy làm theo chính sách nhóm. Việc xóa branch remote thường được thực hiện qua nền tảng sau khi merge hoặc theo quy trình được phê duyệt.

## 10. Bàn giao công việc cho người khác

Bàn giao không chỉ là gửi đường dẫn repository. Người nhận cần biết trạng thái hiện tại và cách tiếp tục mà không phải tự đoán.

### 10.1. Nếu công việc đã hoàn tất và được merge

Ghi lại:

- Ticket hoặc yêu cầu đã hoàn thành.
- PR/MR và commit hoặc merge commit liên quan.
- Kết quả review và CI.
- Những thay đổi về cấu hình, migration hoặc vận hành cần chú ý.
- Tài liệu hoặc nơi có hướng dẫn sử dụng.
- Việc tiếp theo còn phụ thuộc vào release hoặc triển khai.

Không khẳng định thay đổi đã chạy trên production chỉ vì PR đã merge. Trạng thái triển khai cần được xác nhận qua pipeline hoặc hệ thống vận hành.

### 10.2. Nếu công việc đang làm dở

Hãy bàn giao rõ:

- Tên branch và remote/upstream tương ứng.
- Commit mới nhất đã push và phần nào chưa hoàn tất.
- Các tệp còn thay đổi trong working tree hoặc staging area.
- Lệnh kiểm tra đã chạy và kết quả.
- Cách tái hiện vấn đề, log hoặc ảnh minh họa cần thiết.
- Quyết định đã thống nhất và câu hỏi còn mở.
- Rủi ro, phụ thuộc và bước tiếp theo đề xuất.

Nếu có thể, commit các phần đang ở trạng thái nhất quán với thông điệp thể hiện rõ đây là công việc đang tiến hành, rồi push branch để người nhận có thể lấy được. Nếu chưa thể commit, hãy ghi rõ những thay đổi chưa được lưu vào lịch sử và bàn giao chúng bằng phương thức an toàn đã thống nhất.

Trước khi kết thúc phiên làm việc, có thể chạy:

~~~
git status -sb
git log --oneline --decorate -5
git diff
git diff --cached
git branch -vv
~~~

Các lệnh này giúp tạo một bản chụp trạng thái ngắn gọn cho người tiếp nhận. Không gửi thông tin xác thực, token, file .env hoặc dữ liệu nhạy cảm trong ghi chú bàn giao.

### 10.3. Bàn giao giữa hai người trên cùng một branch

Nếu hai người luân phiên làm việc trên cùng branch:

1. Người đang làm push commit mới nhất lên remote.
2. Gửi cho người tiếp nhận tên branch, commit SHA và trạng thái công việc.
3. Người tiếp nhận fetch và checkout branch:

~~~
git fetch origin
git switch --track origin/feature/order-status-filter
~~~

Nếu branch local đã tồn tại, chuyển sang branch đó và cập nhật theo upstream thay vì tạo lại. Trước khi sửa, người tiếp nhận kiểm tra git status để đảm bảo working tree sạch hoặc hiểu rõ thay đổi còn dang dở.

Tránh để hai người cùng push các commit khác nhau lên một branch mà không trao đổi. Nếu cần làm song song, có thể tạo branch riêng cho từng phần và tích hợp qua PR/MR.

## 11. Quy ước cộng tác giúp giảm xung đột

Git có thể kết hợp nhiều thay đổi, nhưng không tự giải quyết được mọi bất đồng về thiết kế hoặc nghiệp vụ. Nhóm có thể giảm chi phí phối hợp bằng các quy ước sau:

- Mỗi branch tập trung vào một ticket hoặc mục tiêu có thể review.
- Cập nhật branch nền trước khi bắt đầu và đồng bộ định kỳ khi công việc kéo dài.
- Commit theo đơn vị nhỏ, có nội dung rõ và không trộn thay đổi không liên quan.
- Push thường xuyên khi commit đã ở trạng thái có thể chia sẻ.
- Mở PR/MR sớm dưới dạng draft khi cần trao đổi hướng triển khai.
- Giữ diff gọn; tách refactor diện rộng khỏi thay đổi chức năng nếu có thể.
- Thông báo trước khi thay đổi file hoặc API mà nhiều người cùng sửa.
- Không rebase hoặc force push branch dùng chung khi chưa phối hợp.
- Bật bảo vệ branch nền, yêu cầu review và CI theo mức độ rủi ro của dự án.
- Ghi lại quyết định và kết quả kiểm thử để người khác tiếp tục được.

Một số xung đột có thể giảm bằng cách chia module rõ ràng, tránh nhiều người chỉnh cùng một file lớn và thống nhất format hoặc sinh mã tự động. Tuy nhiên, công cụ không thay thế trao đổi khi hai thay đổi có ý nghĩa nghiệp vụ mâu thuẫn nhau.

## 12. Ví dụ trọn vẹn từ nhận việc đến bàn giao

Giả sử bạn nhận ticket ORD-142: thêm bộ lọc trạng thái cho danh sách đơn hàng. Nhóm dùng main làm branch nền, PR để review và squash merge để tích hợp.

**Bước 1 — Cập nhật và tạo branch**

~~~
git switch main
git fetch origin
git pull --ff-only
git switch -c feature/ORD-142-status-filter
~~~

**Bước 2 — Sửa mã và kiểm tra**

Sau khi chỉnh API, giao diện và test:

~~~
git status
git diff
git diff --check
~~~

**Bước 3 — Stage và commit**

~~~
git add src/orders/order-query.ts
git add src/orders/order-list.tsx
git add tests/orders/order-query.test.ts
git diff --cached
git commit -m "feat: add order status filter"
~~~

**Bước 4 — Chia sẻ branch**

~~~
git push -u origin feature/ORD-142-status-filter
~~~

Tạo PR vào main, liên kết ticket, mô tả hành vi mới, ghi test đã chạy và chỉ định reviewer.

**Bước 5 — Đồng bộ và xử lý phản hồi**

Nếu main có thay đổi mới, fetch rồi merge hoặc rebase theo quy ước. Sửa các nhận xét review, chạy lại test và push commit bổ sung. PR/MR sẽ cập nhật với nội dung mới.

**Bước 6 — Tích hợp và bàn giao**

Sau khi review và CI đạt, squash merge PR. Cập nhật main local và ghi nhận PR, commit tích hợp, kết quả kiểm tra. Nếu có bước triển khai tiếp theo, nêu rõ ai phụ trách và trạng thái pipeline.

Chu trình này tạo ra đường truy vết từ yêu cầu đến branch, commit, review và kết quả tích hợp. Người khác có thể kiểm tra lịch sử và hiểu vì sao thay đổi được thực hiện.

## 13. Checklist trước khi kết thúc một công việc

**Trước khi bắt đầu**

- [ ] Hiểu mục tiêu, phạm vi và tiêu chí chấp nhận.
- [ ] Xác nhận đúng repository, remote và branch nền.
- [ ] Kiểm tra working tree để không bỏ sót thay đổi đang làm.
- [ ] Cập nhật branch nền và tạo branch riêng cho công việc.

**Trong khi thực hiện**

- [ ] Chia thay đổi thành các đơn vị dễ review.
- [ ] Kiểm tra diff và stage đúng tệp.
- [ ] Viết commit message mô tả nội dung thực tế.
- [ ] Chạy test và kiểm tra phù hợp.
- [ ] Đồng bộ thay đổi mới theo quy ước nhóm.
- [ ] Push branch để chia sẻ và dự phòng công việc.

**Trước khi tích hợp**

- [ ] PR/MR có ngữ cảnh, liên kết ticket và hướng dẫn kiểm tra.
- [ ] Review đã được phê duyệt.
- [ ] CI và các kiểm tra bắt buộc đã đạt.
- [ ] Conflict đã được giải quyết và kiểm tra lại.
- [ ] Chọn đúng merge strategy của repository.

**Khi bàn giao**

- [ ] Nêu branch, commit và PR/MR liên quan.
- [ ] Ghi kết quả test, phần còn dở và rủi ro.
- [ ] Nêu rõ trạng thái tích hợp và triển khai.
- [ ] Hướng dẫn người tiếp nhận cách lấy branch hoặc tiếp tục công việc.
- [ ] Không để thay đổi local chưa được bàn giao một cách rõ ràng.

## 14. Kết luận

Một chu trình cộng tác Git hiệu quả bắt đầu bằng yêu cầu rõ ràng, sử dụng branch riêng để cô lập công việc, commit có chủ đích để lưu lịch sử, đồng bộ có kiểm soát để theo kịp đồng đội, và dùng PR/MR để review trước khi tích hợp. Bàn giao hoàn chỉnh cần cho người tiếp nhận biết mã nguồn đang ở đâu, đã kiểm tra những gì và bước tiếp theo là gì.

Git cung cấp công cụ quản lý lịch sử và trao đổi thay đổi. Chất lượng cộng tác đến từ cách nhóm tổ chức công việc, thống nhất quy ước, trao đổi khi có xung đột và ghi lại đủ ngữ cảnh để người khác tiếp tục.
