# Git worktree giải quyết việc chuyển ngữ cảnh giữa các nhánh

Khi đang phát triển một tính năng dài ngày, bạn có thể bất ngờ phải chuyển sang nhánh khác để sửa lỗi khẩn cấp, review pull request hoặc kiểm tra một phiên bản cũ. Nếu chỉ có một working tree, việc chuyển nhánh có thể yêu cầu commit tạm, stash thay đổi, chờ công cụ build dừng hoặc khôi phục lại môi trường làm việc ban đầu. Git cung cấp **worktree** để một repository có thể có nhiều thư mục làm việc cùng lúc, mỗi thư mục checkout một nhánh hoặc commit riêng.

Với worktree, bạn có thể mở tính năng đang làm trong một thư mục, xử lý hotfix trong thư mục khác và giữ thêm một thư mục chỉ để review. Các worktree dùng chung dữ liệu Git và các tham chiếu của repository, nhưng mỗi worktree có HEAD, index và working tree riêng. Điều này giúp chuyển ngữ cảnh nhanh mà không phải tạo nhiều bản clone độc lập.

Bài này thuộc chương **Nhiều thư mục làm việc** của module **SOURCE_CONTROL_GIT**. Module hướng dẫn Git từ working tree, staging area, commit và lịch sử đến branch, merge, rebase, remote và tag; đồng thời rèn cách cộng tác qua nhánh, giải quyết xung đột, truy tìm thay đổi và khôi phục thao tác sai mà vẫn bảo toàn lịch sử quan trọng. Worktree là công cụ hữu ích khi cần làm nhiều việc song song trên cùng một repository mà vẫn quản lý nhánh và lịch sử nhất quán.

## 1. Git worktree là gì?

Một repository thông thường có một working tree chính. Khi thêm linked worktree, Git tạo thêm một thư mục làm việc được liên kết với repository đó. Mỗi thư mục có thể checkout một nhánh khác nhau hoặc một commit ở trạng thái detached HEAD.

Ví dụ:

~~~text
workspace/
|-- payment-service/          # worktree chính, đang làm feature/payment
|-- payment-hotfix/           # linked worktree, đang làm hotfix/login
|-- payment-review/           # linked worktree, dùng để review nhánh khác
|-- payment-investigation/    # linked worktree, kiểm tra một commit cũ
~~~

Các thư mục này cùng sử dụng object database và các tham chiếu chung của repository. Git không tạo một bản sao đầy đủ của toàn bộ lịch sử cho mỗi worktree như khi chạy nhiều lệnh clone độc lập.

Một linked worktree có file <code>.git</code> nhỏ trỏ về vùng metadata do repository chính quản lý. File này thường không phải thư mục <code>.git</code> đầy đủ. Vì vậy, không nên sao chép thủ công một worktree sang vị trí khác rồi tự sửa file <code>.git</code>; hãy dùng các lệnh <code>git worktree</code> để tạo, di chuyển, sửa chữa hoặc xóa worktree.

## 2. Worktree giải quyết vấn đề gì?

Không có worktree, quy trình chuyển ngữ cảnh thường diễn ra như sau:

1. Dừng công việc đang làm.
2. Commit tạm hoặc stash thay đổi chưa hoàn tất.
3. Checkout sang nhánh cần xử lý.
4. Sửa lỗi hoặc review.
5. Quay lại nhánh cũ và khôi phục trạng thái làm việc.

Quy trình này có thể làm gián đoạn công việc, đặc biệt khi nhánh hiện tại có thay đổi chưa sẵn sàng commit hoặc dự án cần build lâu.

Với worktree, bạn có thể giữ hai nhánh ở hai thư mục riêng:

- Thư mục thứ nhất tiếp tục chứa tính năng đang phát triển.
- Thư mục thứ hai chứa nhánh hotfix hoặc nhánh cần review.

Bạn có thể mở cả hai trong IDE, chạy test độc lập và chuyển giữa chúng bằng cách chuyển cửa sổ hoặc tab. Mỗi worktree giữ trạng thái working tree và index riêng nên việc sửa tệp trong thư mục này không trực tiếp thay đổi tệp trong thư mục kia.

Worktree đặc biệt hữu ích khi:

- Đang làm tính năng nhưng cần sửa lỗi khẩn cấp trên nhánh release.
- Cần review một pull request trong khi vẫn giữ nguyên môi trường phát triển hiện tại.
- Cần so sánh hai nhánh hoặc chạy test trên hai phiên bản.
- Muốn kiểm tra một commit cũ mà không chuyển nhánh đang làm.
- Cần nhiều môi trường làm việc song song cho các tác vụ độc lập.

## 3. Worktree chia sẻ gì và tách riêng gì?

Để sử dụng worktree an toàn, cần hiểu dữ liệu nào được dùng chung và dữ liệu nào thuộc riêng từng thư mục.

| Thành phần | Phạm vi |
|---|---|
| Object database (commit, tree, blob) | Dùng chung trong repository |
| Nhánh local và tag | Tham chiếu chung |
| Cấu hình remote và phần lớn cấu hình repository | Dùng chung theo cấu hình repository |
| HEAD | Riêng cho từng worktree |
| Index / staging area | Riêng cho từng worktree |
| Working tree và file chưa tracked | Riêng cho từng thư mục |
| Reflog của HEAD | Theo từng worktree |
| Remote-tracking refs | Dùng chung trong repository |

Ví dụ, nếu bạn commit trong worktree đang checkout nhánh <code>hotfix/login</code>, tham chiếu nhánh <code>hotfix/login</code> được cập nhật trong repository chung. Các worktree khác có thể nhìn thấy commit mới qua lịch sử và tham chiếu, nhưng nội dung file trong working tree của chúng không tự động được checkout lại.

Tương tự, nếu một worktree chạy <code>git fetch origin</code>, các remote-tracking refs được cập nhật trong repository chung và các worktree khác có thể thấy thông tin mới đó. Tuy nhiên, fetch không tự merge hoặc rebase thay đổi vào nhánh đang làm ở từng thư mục.

Điểm cần nhớ: worktree có index và working tree riêng, nhưng không có bản sao branch riêng. Thao tác di chuyển một nhánh local ảnh hưởng đến tham chiếu dùng chung, vì vậy cần tránh cập nhật một nhánh theo cách làm bất ngờ cho các worktree khác.

## 4. Kiểm tra các worktree hiện có

Trong bất kỳ worktree nào thuộc repository, chạy:

~~~bash
git worktree list
~~~

Ví dụ kết quả:

~~~text
/workspace/payment-service          a1b2c3d [feature/payment]
/workspace/payment-hotfix           e4f5a6b [hotfix/login]
/workspace/payment-investigation    123abcd (detached HEAD)
~~~

Mỗi dòng hiển thị đường dẫn worktree, commit hiện tại và nhánh đang được checkout nếu có. Dòng có <code>(detached HEAD)</code> cho biết worktree đang checkout trực tiếp một commit thay vì một nhánh local.

Để dùng đầu ra dễ phân tích bằng script:

~~~bash
git worktree list --porcelain
~~~

Chế độ porcelain xuất từng trường trên dòng riêng, có phân cách giữa các worktree. Đây là lựa chọn phù hợp cho công cụ tự động vì định dạng ít phụ thuộc cách trình bày cho người đọc.

Bạn cũng có thể kiểm tra nhánh đang dùng ở từng thư mục bằng:

~~~bash
git branch -vv
git status
~~~

<code>git branch -vv</code> hiển thị nhánh local và upstream; <code>git status</code> cho biết working tree hiện tại có thay đổi staged, unstaged hoặc untracked hay không. Hãy chạy trong đúng thư mục worktree mà bạn muốn kiểm tra.

## 5. Tạo worktree mới cho một nhánh mới

Giả sử bạn đang làm tính năng trên worktree chính và cần một nhánh hotfix dựa trên <code>main</code>. Có thể tạo worktree mới cùng lúc tạo nhánh:

~~~bash
git fetch origin
git worktree add -b hotfix/login ../payment-hotfix origin/main
~~~

Ý nghĩa:

- <code>git worktree add</code> tạo linked worktree.
- <code>-b hotfix/login</code> tạo nhánh local mới tên <code>hotfix/login</code>.
- <code>../payment-hotfix</code> là đường dẫn thư mục làm việc mới.
- <code>origin/main</code> là commit nền để tạo nhánh mới.

Sau lệnh, thư mục <code>../payment-hotfix</code> được tạo và checkout nhánh <code>hotfix/login</code>. Bạn có thể mở thư mục này trong IDE và làm hotfix độc lập với worktree chính.

Nếu muốn tạo nhánh từ <code>main</code> local hiện tại, có thể dùng:

~~~bash
git worktree add -b hotfix/login ../payment-hotfix main
~~~

Trước khi dùng <code>main</code> làm điểm bắt đầu, hãy xác nhận nó đã cập nhật theo trạng thái mà nhóm mong muốn. Nếu nhánh nền cần lấy từ máy chủ, fetch trước rồi chỉ rõ remote-tracking branch.

### Cú pháp tổng quát

~~~bash
git worktree add <path> [<commit-ish>]
git worktree add -b <new-branch> <path> [<commit-ish>]
~~~

Nếu bỏ qua <code>&lt;commit-ish&gt;</code>, Git dùng HEAD hiện tại làm điểm bắt đầu. Hãy đặt worktree mới ở một thư mục riêng, thường là thư mục ngang cấp với repository chính, để dễ nhận biết và quản lý.

## 6. Tạo worktree cho một nhánh local đã tồn tại

Nếu nhánh đã được tạo và chưa được checkout trong worktree khác, có thể thêm worktree trực tiếp:

~~~bash
git worktree add ../payment-review feature/payment
~~~

Lệnh tạo thư mục <code>../payment-review</code> và checkout nhánh local <code>feature/payment</code> tại đó. Đây là cách thuận tiện để review một nhánh mà không làm thay đổi thư mục đang phát triển.

Nếu nhánh <code>feature/payment</code> chưa được checkout ở worktree nào khác, bạn có thể dùng <code>payment-review</code> để chạy test, đọc diff và kiểm tra nhánh. Nếu nhánh này đang được checkout trong worktree chính <code>payment-service</code>, lệnh thêm worktree ở trên sẽ bị từ chối. Khi đó, hãy tạo một nhánh review riêng từ cùng điểm bắt đầu:

~~~bash
git worktree add -b review/payment ../payment-review feature/payment
~~~

Hoặc tạo worktree detached nếu chỉ cần đọc mã nguồn và chạy test:

~~~bash
git worktree add --detach ../payment-review feature/payment
~~~

Như vậy, worktree chính tiếp tục giữ nhánh <code>feature/payment</code>, còn thư mục review dùng nhánh riêng hoặc detached HEAD.

Nếu một worktree được tạo trên nhánh <code>feature/payment</code>, mọi commit được tạo trong worktree đó đều cập nhật cùng tham chiếu nhánh mà repository dùng chung. Vì thế, nếu worktree khác cũng đang sử dụng nhánh đó thì Git sẽ không cho phép tạo worktree thứ hai checkout cùng nhánh theo cách thông thường.

### Trường hợp nhánh nằm trên remote

Nếu nhánh chỉ có trên remote và bạn muốn tạo một nhánh local để review, có thể tạo worktree với nhánh tracking:

~~~bash
git fetch origin
git worktree add --track -b review/payment ../payment-review origin/feature/payment
~~~

Lệnh này tạo nhánh local <code>review/payment</code> theo dõi <code>origin/feature/payment</code>, rồi checkout nhánh mới trong worktree review. Cách đặt tên riêng giúp tránh chiếm nhánh local có thể đang được sử dụng ở worktree chính.

## 7. Tạo worktree detached để kiểm tra commit

Không phải lúc nào bạn cũng cần tạo nhánh. Khi chỉ muốn chạy thử một commit cũ hoặc xem nội dung của một mốc lịch sử, dùng detached HEAD:

~~~bash
git worktree add --detach ../payment-investigation 123abcd
~~~

Git tạo worktree tại <code>../payment-investigation</code> và checkout commit <code>123abcd</code> mà không tạo nhánh local mới.

Detached worktree phù hợp để:

- Chạy test trên một bản phát hành cũ.
- So sánh hành vi trước và sau một commit.
- Kiểm tra một lỗi được báo chỉ xuất hiện ở phiên bản cụ thể.
- Xem mã nguồn tại một mốc lịch sử mà không tác động đến nhánh đang làm.

Nếu bạn tạo commit trong detached HEAD, commit mới không tự gắn vào một nhánh local. Hãy tạo nhánh trước hoặc ngay sau khi tạo commit nếu muốn giữ kết quả dễ tìm:

~~~bash
git switch -c investigation/fix-at-123abcd
~~~

Lệnh trên tạo nhánh từ commit hiện tại trong worktree detached và chuyển HEAD sang nhánh mới. Khi đã tạo nhánh, commit tiếp theo sẽ được ghi vào nhánh đó.

## 8. Giới hạn: một nhánh local chỉ được checkout ở một worktree

Git thường ngăn cùng một nhánh local được checkout trong nhiều worktree cùng lúc. Điều này tránh hai thư mục cùng cập nhật một tham chiếu nhánh nhưng có index và working tree riêng, gây nhầm lẫn hoặc mất công việc.

Ví dụ, nếu <code>feature/payment</code> đang được checkout trong worktree chính, lệnh:

~~~bash
git worktree add ../payment-second feature/payment
~~~

có thể bị từ chối với thông báo rằng nhánh đang được sử dụng ở worktree khác.

Đây là hành vi bảo vệ có chủ đích. Hãy chọn một trong các cách:

- Tạo nhánh mới từ nhánh hiện tại bằng <code>git worktree add -b</code>.
- Dùng một nhánh review riêng theo dõi remote branch.
- Dùng detached HEAD nếu chỉ cần đọc hoặc chạy thử commit.
- Chuyển nhánh đang dùng sang worktree khác sau khi kiểm tra trạng thái và thống nhất công việc.

Tùy chọn <code>--force</code> có thể vượt qua một số kiểm tra bảo vệ, nhưng không nên dùng chỉ để ép cùng nhánh xuất hiện ở nhiều worktree. Làm vậy có thể khiến hai nơi cùng thao tác trên một tham chiếu và làm tăng rủi ro ghi đè hoặc tạo trạng thái khó hiểu.

## 9. Làm việc độc lập trong từng worktree

Sau khi tạo worktree, hãy đi vào đúng thư mục:

~~~bash
cd ../payment-hotfix
git status
git branch --show-current
~~~

Bạn có thể sửa file, stage và commit như trong một repository bình thường:

~~~bash
git add src/auth/
git diff --staged
git commit -m "fix: handle expired login token"
~~~

Commit được tạo sẽ cập nhật nhánh <code>hotfix/login</code>. Worktree chính vẫn giữ nguyên working tree và index của nó. Khi quay lại thư mục chính, bạn có thể xem nhánh và lịch sử mới; không cần fetch để thấy commit local vừa tạo vì các worktree thuộc cùng repository.

Mỗi worktree có thể chạy build hoặc test riêng. Tuy nhiên, hãy lưu ý các thư mục output hoặc dịch vụ dùng chung bên ngoài repository. Nếu hai worktree cùng ghi vào một database phát triển, cùng cổng máy chủ hoặc cùng thư mục cache bên ngoài, chúng vẫn có thể xung đột dù file Git được tách riêng.

## 10. Quy trình thực tế: hotfix song song với feature

Giả sử bạn đang phát triển <code>feature/payment</code> nhưng nhóm yêu cầu sửa lỗi đăng nhập trên nhánh <code>main</code>.

~~~mermaid
flowchart TD
    A["Worktree chính: feature/payment"] --> B["Giữ nguyên công việc đang làm"]
    B --> C["Tạo worktree mới từ origin/main"]
    C --> D["Worktree hotfix: hotfix/login"]
    D --> E["Sửa lỗi, chạy test và commit"]
    E --> F["Push hotfix và mở review"]
    F --> G["Tích hợp hotfix theo quy trình nhóm"]
    G --> H["Xóa worktree khi không còn cần"]
    B --> I["Tiếp tục feature/payment"]
~~~

Các lệnh:

~~~bash
# Từ worktree chính
git status
git fetch origin
git worktree add -b hotfix/login ../payment-hotfix origin/main

# Trong worktree hotfix
cd ../payment-hotfix
git status
git add src/auth/
git commit -m "fix: handle expired login token"
git push -u origin hotfix/login

# Quay lại worktree chính để tiếp tục feature
cd ../payment-service
git status
git branch -vv
~~~

Hai nhánh được phát triển ở hai thư mục riêng. Bạn không cần stash hoặc commit tạm thay đổi đang làm trên <code>feature/payment</code> chỉ để chuyển sang hotfix.

## 11. Quản lý vòng đời worktree

Worktree thường được tạo cho một nhiệm vụ cụ thể. Khi nhiệm vụ kết thúc, hãy dọn worktree để repository không tích lũy các thư mục cũ.

### Liệt kê worktree

~~~bash
git worktree list
git worktree list --porcelain
~~~

Chạy lệnh từ một worktree còn hoạt động để xem các đường dẫn được liên kết và trạng thái của chúng.

### Xóa một linked worktree

Khi đã hoàn tất hotfix và không cần thư mục nữa, quay về worktree chính hoặc một worktree khác rồi chạy:

~~~bash
git worktree remove ../payment-hotfix
~~~

Git xóa linked worktree và metadata liên quan nếu worktree đáp ứng các điều kiện an toàn. Theo mặc định, Git bảo vệ worktree có thay đổi chưa commit hoặc file chưa được theo dõi để tránh xóa nhầm dữ liệu.

Trước khi xóa, kiểm tra:

~~~bash
git -C ../payment-hotfix status
git -C ../payment-hotfix log --oneline -5
~~~

Đảm bảo các commit cần giữ đã được push, merge hoặc có tham chiếu khác bảo vệ. Nếu worktree còn thay đổi chưa commit, hãy commit, stash hoặc sao lưu chúng trước khi remove.

Tùy chọn <code>--force</code> có thể vượt qua kiểm tra bảo vệ khi xóa worktree. Chỉ dùng sau khi đã xác nhận nội dung bên trong không còn cần thiết:

~~~bash
git worktree remove --force ../payment-hotfix
~~~

Không dùng <code>--force</code> như bước dọn dẹp mặc định. Nó có thể xóa những thay đổi local mà bạn chưa lưu ở nơi khác.

Với worktree đang bị khóa, Git yêu cầu thao tác cưỡng bức rõ ràng hơn; một số trường hợp cần lặp tùy chọn <code>--force</code>. Hãy mở khóa nếu có thể và kiểm tra lại trạng thái trước khi xóa.

### Xóa nhánh sau khi bỏ worktree

Xóa worktree không tự động xóa nhánh local. Nếu nhánh đã được tích hợp và không còn cần thiết, bạn có thể xóa riêng:

~~~bash
git branch -d hotfix/login
~~~

<code>-d</code> yêu cầu Git kiểm tra nhánh đã được merge phù hợp trước khi xóa. Nếu nhánh chưa được tích hợp, Git thường từ chối. Đừng chuyển sang <code>-D</code> nếu chưa xác nhận commit chưa merge không còn cần thiết.

### Khóa và mở khóa worktree

Nếu worktree nằm trên ổ đĩa rời hoặc vị trí mạng có thể tạm thời không truy cập được, bạn có thể khóa nó:

~~~bash
git worktree lock --reason "External drive temporarily offline" ../payment-review
~~~

Khóa giúp Git không xem worktree đang vắng mặt là thư mục có thể dọn dẹp khi prune. Khi vị trí đã sẵn sàng, mở khóa:

~~~bash
git worktree unlock ../payment-review
~~~

Bạn có thể xem trạng thái khóa bằng <code>git worktree list</code>; thông tin lý do khóa có thể được hiển thị cùng đường dẫn.

## 12. Prune metadata của worktree không còn tồn tại

Nếu một thư mục linked worktree bị xóa thủ công bằng File Explorer hoặc công cụ hệ thống, metadata trong repository có thể vẫn còn. Git có thể đánh dấu worktree đó là prunable.

Kiểm tra trước:

~~~bash
git worktree list --porcelain
git worktree prune --dry-run --verbose
~~~

Nếu danh sách chỉ chứa metadata mồ côi mà bạn xác nhận không còn cần, chạy:

~~~bash
git worktree prune --verbose
~~~

<code>prune</code> dọn metadata quản lý worktree không còn hợp lệ; nó không phải lệnh xóa một worktree đang tồn tại và cũng không xóa branch local chỉ vì branch từng được checkout ở worktree đó. Git có thời hạn chờ trước khi prune metadata cũ, vì vậy một mục vừa trở thành prunable có thể chưa bị dọn ngay. Nếu đã xác nhận thư mục worktree bị xóa vĩnh viễn và muốn kiểm tra việc dọn ngay, có thể dùng <code>--expire now</code> sau bước dry-run:

~~~bash
git worktree prune --dry-run --verbose --expire now
git worktree prune --verbose --expire now
~~~

Đừng chạy prune khi worktree chỉ tạm thời không truy cập được, chẳng hạn ổ đĩa rời chưa gắn hoặc thư mục mạng đang offline. Trong trường hợp đó, khóa worktree trước khi vị trí biến mất hoặc chờ đến khi nó có thể truy cập lại.

## 13. Di chuyển hoặc sửa chữa worktree

Nếu cần chuyển một linked worktree sang đường dẫn mới, ưu tiên lệnh:

~~~bash
# Đảm bảo thư mục cha đích đã tồn tại
git worktree move ../payment-review ../reviews/payment-review
~~~

Git cập nhật metadata để worktree tiếp tục được nhận diện ở vị trí mới. Không dùng lệnh này để di chuyển worktree chính; hãy làm theo hướng dẫn Git cho trường hợp thư mục chính.

Nếu thư mục đã được di chuyển thủ công và metadata không còn khớp, Git cung cấp:

~~~bash
git worktree repair
~~~

Lệnh repair giúp sửa liên kết metadata trong những trường hợp đường dẫn worktree hoặc repository chính đã thay đổi. Với tình huống cụ thể, hãy đọc <code>git worktree list</code> và thông báo Git trước khi chạy repair; tránh tự sửa file quản lý nội bộ dưới <code>.git/worktrees</code>.

## 14. Worktree và clone khác nhau thế nào?

Worktree và clone đều có thể tạo thêm một thư mục để làm việc, nhưng mục tiêu và cách lưu trữ khác nhau.

| Tiêu chí | git worktree | git clone |
|---|---|---|
| Dữ liệu lịch sử Git | Dùng chung object database của repository gốc | Có object database riêng, thường tải lịch sử từ remote |
| Tham chiếu local | Nhánh và tag dùng chung trong repository | Nhánh local độc lập trong bản clone |
| HEAD và index | Riêng cho từng worktree | Riêng trong bản clone |
| Remote và fetch | Dùng chung cấu hình repository và refs | Có cấu hình remote và refs riêng |
| Mục tiêu | Nhiều thư mục làm việc cho cùng một repository | Tạo một bản clone độc lập, phù hợp cộng tác hoặc môi trường tách biệt |
| Dung lượng ban đầu | Thường tiết kiệm vì không nhân đôi object database | Có thể lớn hơn do có kho dữ liệu Git riêng |

Chọn worktree khi bạn muốn làm nhiều việc song song trong cùng repository và chấp nhận dùng chung branch refs. Chọn clone khi cần môi trường độc lập hơn, ví dụ thử nghiệm cấu hình Git khác, làm việc với fork khác hoặc tách biệt quyền và dữ liệu repository.

## 15. Những lưu ý khi dùng worktree với IDE và công cụ build

Mỗi worktree là một thư mục dự án riêng, vì vậy bạn có thể mở nhiều cửa sổ IDE cùng lúc. Điều này thuận tiện cho review và phát triển song song, nhưng có một số điểm cần quản lý:

- **Dependency và cache:** mỗi thư mục có thể cần cài dependency hoặc tạo cache riêng, tùy công cụ. Một số công cụ dùng cache chung ở ngoài repository.
- **Build output:** tránh cấu hình hai worktree ghi vào cùng một thư mục output bên ngoài cây dự án.
- **Port và dịch vụ:** hai ứng dụng chạy song song cần cổng khác nhau hoặc cấu hình môi trường riêng.
- **File cấu hình local:** nếu file bị ignore và mỗi worktree cần một cấu hình riêng, hãy tạo cấu hình tương ứng trong từng thư mục.
- **IDE metadata:** một số IDE lưu workspace state theo đường dẫn dự án; mở worktree mới có thể tạo cấu hình riêng.
- **Script phụ thuộc đường dẫn:** script dùng đường dẫn tuyệt đối của worktree chính có thể không chạy đúng trong worktree phụ.

Worktree tách working tree và index, nhưng không tự cô lập mọi tài nguyên mà ứng dụng sử dụng. Hãy kiểm tra database, container, cổng mạng và thư mục tạm khi chạy nhiều phiên bản cùng lúc.

## 16. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Không thể checkout cùng nhánh ở worktree mới | Nhánh local đã được checkout ở worktree khác | Dùng nhánh mới hoặc detached HEAD; không ép dùng <code>--force</code> khi chưa hiểu tác động |
| <code>git worktree add</code> báo đường dẫn đã tồn tại | Đích đã có nội dung hoặc metadata không phù hợp | Chọn một đường dẫn mới, hoặc kiểm tra kỹ thư mục hiện tại trước khi xử lý |
| Worktree hiện trạng thái prunable | Thư mục đã bị di chuyển hoặc xóa bên ngoài Git | Xác minh đường dẫn; dùng <code>repair</code> hoặc <code>prune</code> đúng trường hợp |
| <code>git worktree remove</code> từ chối | Worktree có thay đổi, file untracked hoặc đang bị khóa | Kiểm tra status, lưu dữ liệu cần thiết, unlock nếu phù hợp rồi remove |
| Xóa worktree nhưng branch vẫn còn | Remove worktree không xóa branch local | Dùng <code>git branch -d</code> sau khi xác nhận branch không còn cần |
| Commit ở worktree này xuất hiện trong worktree khác | Các worktree dùng chung branch refs và object database | Đây là hành vi bình thường; kiểm tra đúng branch và HEAD ở từng thư mục |
| Không thấy file đã sửa ở worktree khác | Working tree và index tách riêng | Mỗi worktree chỉ hiển thị file của checkout riêng; tích hợp thay đổi qua commit/merge/rebase |
| Prune sắp xóa metadata của ổ đĩa đang offline | Git không thấy đường dẫn worktree | Khóa worktree trước khi nó tạm vắng mặt hoặc đợi đường dẫn truy cập lại |

## 17. Quy trình sử dụng worktree an toàn

Một quy trình có thể áp dụng cho mỗi tác vụ song song:

1. Xác định nhánh nền và cập nhật remote-tracking refs bằng fetch.
2. Chọn đường dẫn worktree riêng, dễ nhận biết theo mục đích.
3. Tạo worktree với nhánh mới, nhánh đã tồn tại chưa được sử dụng hoặc detached HEAD.
4. Kiểm tra <code>git status</code> và <code>git branch --show-current</code> trong thư mục mới.
5. Làm việc, chạy test và commit như bình thường.
6. Push hoặc tích hợp commit theo quy trình cộng tác của nhóm.
7. Xác nhận không còn thay đổi hoặc commit cần giữ trước khi xóa worktree.
8. Dùng <code>git worktree remove</code>; chỉ xóa branch riêng sau khi xác nhận branch đã được tích hợp.
9. Dùng <code>git worktree list</code> để kiểm tra repository còn những worktree nào.

Các lệnh kiểm tra tổng quát:

~~~bash
git worktree list --porcelain
git branch -vv
git status
~~~

Khi có sự cố, giữ nguyên các thư mục còn dữ liệu cần thiết và kiểm tra trạng thái trước khi dùng <code>remove</code>, <code>prune</code> hoặc <code>--force</code>.

## 18. Bài tập tự kiểm tra

Thực hành trong repository thử nghiệm:

1. Từ worktree chính, chạy <code>git worktree list</code> và ghi lại đường dẫn cùng nhánh hiện tại.
2. Tạo linked worktree mới cho nhánh <code>hotfix/demo</code> từ <code>main</code> bằng <code>git worktree add -b</code>.
3. Mở thư mục mới, tạo một thay đổi và commit. Quay lại worktree chính rồi kiểm tra nhánh và lịch sử có nhìn thấy commit đó không.
4. Thử tạo worktree thứ hai cho cùng nhánh đang được checkout. Quan sát Git từ chối và giải thích giới hạn này.
5. Tạo worktree detached tại một commit cũ, chạy test rồi chuyển sang nhánh điều tra nếu muốn giữ commit mới.
6. Chạy <code>git worktree list --porcelain</code> và phân biệt worktree có nhánh với worktree detached.
7. Xóa một linked worktree sau khi đã lưu thay đổi. Kiểm tra vì sao branch local vẫn còn.
8. Tạo một thư mục worktree thử nghiệm rồi xóa thư mục bằng công cụ hệ điều hành. Dùng <code>git worktree prune --dry-run</code> để xem metadata có thể được dọn.
9. Khóa và mở khóa một worktree thử nghiệm; quan sát thông tin trạng thái trong danh sách.
10. Giải thích vì sao worktree phù hợp hơn clone khi cần xử lý hotfix song song mà vẫn dùng chung repository.

Khi hiểu rằng mỗi worktree có working tree, index và HEAD riêng nhưng chia sẻ dữ liệu Git cùng các branch refs, bạn có thể xử lý nhiều tác vụ song song mà không phải liên tục stash hoặc chuyển nhánh trong một thư mục. Hãy tạo worktree theo mục đích rõ ràng, kiểm tra trạng thái trước khi dọn và giữ nguyên mọi commit hoặc thay đổi local cần thiết.
