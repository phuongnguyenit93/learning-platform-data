# Dùng worktree cho bản sửa khẩn cấp, xem xét và thử nghiệm song song

Khi đang làm một tính năng nhưng cần sửa lỗi khẩn cấp, xem xét một nhánh khác hoặc thử hai hướng triển khai, việc liên tục stash, commit tạm rồi chuyển branch làm gián đoạn công việc. Git worktree cho phép tạo nhiều thư mục làm việc gắn với cùng một repository. Mỗi thư mục có working tree và index riêng, vì vậy bạn có thể mở nhiều công việc cùng lúc mà không cần clone repository thêm lần nữa.

Trong chương **Nhiều thư mục làm việc** của module **SOURCE_CONTROL_GIT**, bài học này tập trung vào ba tình huống thực tế: tạo worktree riêng để sửa hotfix, mở một worktree chỉ để review hoặc kiểm thử, và chạy nhiều thử nghiệm trên các nhánh độc lập. Bạn sẽ hiểu dữ liệu nào được chia sẻ giữa các worktree, quy tắc một branch chỉ được checkout tại một worktree, và cách quản lý vòng đời worktree an toàn.

Sau bài học, bạn có thể:

- Giải thích linked worktree và sự khác nhau giữa worktree với một bản clone độc lập.
- Tạo, liệt kê, khóa, di chuyển và gỡ worktree.
- Dùng worktree riêng cho hotfix khi công việc chính vẫn đang mở.
- Xem xét một branch hoặc commit trong worktree riêng mà không làm thay đổi working tree hiện tại.
- Tạo các worktree thử nghiệm với branch độc lập.
- Hiểu cách HEAD, index, branch, tag và object database được chia sẻ hoặc tách riêng.
- Xử lý worktree cũ, đường dẫn đã di chuyển và metadata còn sót.

## 1. Worktree giải quyết vấn đề gì?

Một repository thông thường có một working tree. Khi checkout branch khác, Git cập nhật nội dung trong thư mục đó theo branch mới. Nếu đang có thay đổi chưa commit, bạn có thể phải commit, stash hoặc xử lý xung đột trước khi chuyển.

Git worktree cho phép một repository có nhiều working tree cùng lúc:

~~~text
Repository Git dùng chung
       |
       +-- Main working tree
       |      branch: feature/payment
       |      index riêng
       |
       +-- Linked worktree A
       |      branch: hotfix/login
       |      index riêng
       |
       +-- Linked worktree B
              detached HEAD: origin/feature/search
              index riêng
~~~

Ví dụ, bạn đang triển khai thanh toán trong thư mục chính. Một lỗi đăng nhập nghiêm trọng xuất hiện và cần sửa ngay trên main. Thay vì cất công việc thanh toán rồi checkout main, bạn có thể tạo một worktree mới ở thư mục bên cạnh, checkout branch hotfix tại đó, sửa lỗi và chạy kiểm thử. Thư mục làm việc thanh toán vẫn giữ nguyên trạng thái.

Worktree cũng hữu ích khi:

- Review pull request trong khi tiếp tục làm việc ở branch hiện tại.
- Chạy test hoặc build trên hai phiên bản code khác nhau.
- So sánh hai hướng triển khai song song.
- Giữ một worktree ổn định cho môi trường demo hoặc tái hiện lỗi.
- Mở một commit cũ để điều tra mà không di chuyển branch đang làm việc.

## 2. Worktree chia sẻ gì và tách riêng gì?

Linked worktree không phải một repository độc lập. Nó gắn với repository chính và chia sẻ phần lớn dữ liệu Git.

| Thành phần | Cách hoạt động |
| --- | --- |
| Object database | Dùng chung commit, tree, blob và tag object |
| Branch và tag refs | Dùng chung; thay đổi ref ở một worktree có thể được nhìn thấy từ các worktree khác |
| Remote và remote-tracking refs | Dùng chung; fetch từ một worktree cập nhật thông tin remote cho cả repository |
| Working tree | Riêng cho từng đường dẫn worktree |
| Index (staging area) | Riêng cho từng worktree |
| HEAD | Riêng cho từng worktree; mỗi nơi có thể checkout branch hoặc commit khác |
| Trạng thái file đang sửa chưa commit | Riêng trong working tree tương ứng |

Khi commit trong một linked worktree, commit object mới được ghi vào object database dùng chung và branch đang checkout tại worktree đó được cập nhật. Các worktree khác có thể nhìn thấy commit thông qua refs hoặc lịch sử mới, nhưng nội dung chưa commit trong working tree của chúng không tự thay đổi.

Vì branch refs được chia sẻ, Git bảo vệ một quy tắc quan trọng: **một branch local chỉ được checkout trong một worktree tại một thời điểm**. Quy tắc này tránh hai index độc lập cùng ghi commit lên một branch, gây khó dự đoán trạng thái.

Ví dụ, nếu branch feature/payment đang checkout trong thư mục chính, lệnh tạo worktree khác cũng checkout feature/payment sẽ bị từ chối. Bạn có thể tạo worktree bằng một branch khác hoặc dùng detached HEAD để xem cùng một commit mà không gắn branch đó vào worktree thứ hai.

## 3. Kiểm tra worktree hiện có

Từ bất kỳ worktree nào thuộc repository, chạy:

~~~bash
git worktree list
~~~

Ví dụ:

~~~text
/projects/shop                 2ab34cd [feature/payment]
/projects/shop-hotfix          8de901a [hotfix/login]
/projects/shop-review          4fa567b (detached HEAD)
~~~

Kết quả cho biết đường dẫn, commit hiện tại và branch được checkout. Nếu worktree ở detached HEAD, Git hiển thị trạng thái detached thay vì tên branch.

Để dùng output có cấu trúc dễ xử lý hơn:

~~~bash
git worktree list --porcelain
~~~

Kết quả dạng porcelain có các trường như worktree, HEAD, branch, detached, locked hoặc prunable. Nó phù hợp cho script hoặc khi cần kiểm tra chính xác trạng thái từng thư mục.

Có thể xác định thư mục Git chung và thư mục Git của worktree hiện tại:

~~~bash
git rev-parse --git-dir
git rev-parse --git-common-dir
~~~

Ở linked worktree, đường dẫn Git riêng thường trỏ đến metadata dành cho worktree đó; git-common-dir trỏ đến khu vực dữ liệu dùng chung. Không nên chỉnh sửa thủ công các file trong những thư mục này.

## 4. Tạo worktree cho bản sửa khẩn cấp

Giả sử bạn đang làm tính năng thanh toán trên branch feature/payment. Nhóm phát hiện lỗi nghiêm trọng ở main và cần tạo branch hotfix/login-timeout.

### Bước 1: cập nhật thông tin remote

Từ một worktree bất kỳ:

~~~bash
git fetch origin
git status -sb
~~~

Fetch cập nhật remote-tracking branch như origin/main. Nó không thay đổi các file đang sửa chưa commit trong worktree hiện tại.

### Bước 2: tạo worktree và branch hotfix

Tạo thư mục làm việc mới ở cùng cấp với repository hiện tại:

~~~bash
git worktree add -b hotfix/login-timeout ../shop-hotfix origin/main
~~~

Lệnh này:

- Tạo linked worktree tại ../shop-hotfix.
- Tạo branch local hotfix/login-timeout từ commit origin/main.
- Checkout branch mới trong worktree vừa tạo.
- Giữ nguyên branch feature/payment và nội dung đang làm trong worktree chính.

Nếu branch hotfix/login-timeout đã tồn tại và chưa được checkout ở worktree nào, dùng:

~~~bash
git worktree add ../shop-hotfix hotfix/login-timeout
~~~

Không dùng lại tên branch đang được checkout ở worktree khác. Nếu cần xem cùng một commit mà không tạo branch mới, dùng detached HEAD như phần review bên dưới.

### Bước 3: làm việc trong thư mục hotfix

Chuyển terminal sang thư mục mới:

~~~bash
cd ../shop-hotfix
git status -sb
git branch --show-current
~~~

Thực hiện sửa lỗi, chạy test và xem diff như trong một working tree thông thường:

~~~bash
git diff
git status
git add -- src/auth/LoginService.java
git diff --cached
git commit -m "fix(auth): handle login timeout"
~~~

### Bước 4: push branch hotfix

~~~bash
git push -u origin hotfix/login-timeout
~~~

Sau đó tạo pull request hoặc thực hiện quy trình review và phát hành của nhóm. Worktree chính vẫn có thể tiếp tục phát triển thanh toán.

### Bước 5: quay lại công việc chính

Chuyển terminal về thư mục ban đầu:

~~~bash
cd ../shop
git status -sb
git branch --show-current
~~~

Bạn vẫn ở feature/payment với index và working tree trước đó. Khi hotfix đã được tích hợp, có thể gỡ worktree riêng theo quy trình ở phần quản lý vòng đời.

## 5. Dùng worktree để review một branch hoặc commit

Review thường cần đọc code, chạy test, tái hiện lỗi và so sánh với nhánh đích. Worktree riêng giúp thực hiện việc này mà không làm xáo trộn công việc đang mở.

### Chỉ xem và kiểm thử một remote branch

Cập nhật refs trước:

~~~bash
git fetch origin
~~~

Tạo worktree detached từ branch remote:

~~~bash
git worktree add --detach ../shop-review origin/feature/search
~~~

Detached HEAD có nghĩa worktree trỏ trực tiếp đến commit, không checkout một branch local. Cách này phù hợp khi chỉ cần đọc, build hoặc test và không định tạo commit review.

Vào thư mục review:

~~~bash
cd ../shop-review
git status -sb
git log -1 --oneline --decorate
~~~

Nếu cần thử sửa file để kiểm tra một nhận xét, có thể chỉnh trong worktree này. Các chỉnh sửa chưa commit chỉ nằm ở thư mục review. Tuy nhiên, nếu muốn giữ thay đổi thành commit, hãy tạo branch riêng trước:

~~~bash
git switch -c review/search-followup
~~~

Commit tạo ra sẽ cập nhật branch review/search-followup dùng chung trong repository.

### Review với một branch local có thể commit

Nếu remote branch cần được kiểm tra và có thể phát sinh commit sửa thử, tạo branch local riêng từ remote-tracking branch:

~~~bash
git fetch origin
git worktree add -b review/feature-search ../shop-review origin/feature/search
~~~

Kiểm tra upstream:

~~~bash
cd ../shop-review
git branch -vv
~~~

Nếu branch chưa theo dõi remote branch như mong muốn, có thể đặt upstream rõ ràng:

~~~bash
git branch --set-upstream-to=origin/feature/search review/feature-search
~~~

Branch review/feature-search là branch local riêng. Việc commit hoặc reset branch này không trực tiếp di chuyển origin/feature/search; muốn chia sẻ commit cần push theo quy trình của nhóm.

### Mở một commit cũ để tái hiện lỗi

Không cần tạo branch nếu chỉ muốn xem snapshot:

~~~bash
git worktree add --detach ../shop-old-release 4f8a21c
~~~

Worktree mới checkout commit 4f8a21c trong detached HEAD. Bạn có thể chạy test, so sánh hành vi hoặc kiểm tra cấu hình ở thời điểm đó. Nếu cần giữ một chuỗi commit mới từ mốc này, hãy tạo branch trong worktree:

~~~bash
git switch -c investigation/old-release
~~~

## 6. Dùng nhiều worktree cho thử nghiệm song song

Giả sử nhóm đang cân nhắc hai phương án cache. Có thể tạo hai worktree, mỗi nơi có branch riêng:

~~~bash
git worktree add -b experiment/cache-memory ../shop-cache-memory origin/main
git worktree add -b experiment/cache-disk ../shop-cache-disk origin/main
~~~

Hai branch bắt đầu từ cùng commit origin/main. Bạn có thể mở hai thư mục trong hai cửa sổ IDE hoặc terminal khác nhau:

~~~text
../shop-cache-memory
    branch: experiment/cache-memory
    thử cache trong bộ nhớ

../shop-cache-disk
    branch: experiment/cache-disk
    thử cache trên đĩa
~~~

Mỗi worktree có index và file riêng. Bạn có thể stage ở thư mục này mà không làm thay đổi staging area của thư mục kia. Commit ở mỗi nơi cập nhật branch tương ứng và object database dùng chung.

Nếu chỉ muốn thử nghiệm tạm thời và không cần giữ commit, tạo worktree detached:

~~~bash
git worktree add --detach ../shop-prototype <base-commit>
~~~

Sau khi thử nghiệm, có thể gỡ worktree nếu không cần giữ nội dung. Nếu phát hiện hướng triển khai tốt, hãy tạo branch hoặc commit trong worktree đó trước khi dọn.

Một lưu ý thực tế: worktree tách thư mục mã nguồn, nhưng không tự tách mọi tài nguyên ngoài repository. Nếu hai bản chạy cùng ghi vào một database local, dùng chung cổng server, cache ngoài thư mục hoặc thư mục output được cấu hình tuyệt đối, chúng vẫn có thể xung đột. Hãy đặt port, database/schema và đường dẫn build riêng cho mỗi lần chạy khi cần.

## 7. Quy tắc branch và các lỗi thường gặp

### Một branch không thể checkout ở hai worktree

Giả sử branch feature/payment đang được checkout tại worktree chính. Lệnh:

~~~bash
git worktree add ../shop-payment-review feature/payment
~~~

sẽ bị từ chối vì branch đó đã được checkout ở nơi khác.

Có ba cách xử lý:

- Dùng worktree hiện có nếu mục tiêu chỉ là truy cập branch.
- Tạo branch mới từ feature/payment nếu cần làm việc độc lập.
- Dùng detached HEAD từ commit của branch nếu chỉ cần xem hoặc test.

Ví dụ tạo branch thử nghiệm:

~~~bash
git worktree add -b experiment/payment-review ../shop-payment-review feature/payment
~~~

Branch mới bắt đầu từ commit của feature/payment nhưng có ref riêng. Các commit mới trên experiment/payment-review không di chuyển feature/payment.

### Không dùng force để bỏ qua bảo vệ branch

Git có tùy chọn force trong một số thao tác worktree, nhưng ép checkout cùng branch ở nhiều nơi có thể làm mất lợi ích bảo vệ của Git và tạo ra trạng thái khó kiểm soát. Hãy dùng branch độc lập hoặc detached HEAD thay vì ép một branch dùng chung hai index.

### Commit trong worktree khác có xuất hiện ở nơi hiện tại không?

Object commit được chia sẻ, nhưng branch của commit đó cũng là ref dùng chung. Nếu branch khác được cập nhật, bạn có thể nhìn thấy nó qua git branch hoặc log; working tree hiện tại không tự checkout commit mới.

### Fetch từ một worktree có ảnh hưởng worktree khác không?

Có. Remote-tracking refs thuộc dữ liệu chung của repository. Khi fetch origin trong một worktree, thông tin origin/main được cập nhật và có thể được dùng trong các worktree còn lại.

### Stash có tách biệt theo worktree không?

Không nên coi stash là vùng lưu trữ riêng của từng worktree. Stash được quản lý qua ref chung của repository. Khi nhiều worktree cùng tạo stash, hãy ghi message rõ ràng và kiểm tra git stash list trước khi apply hoặc drop để tránh nhầm thay đổi.

## 8. Quản lý vòng đời worktree

Worktree nên được quản lý bằng lệnh Git để metadata và thư mục làm việc luôn đồng bộ.

### Liệt kê trước khi dọn

~~~bash
git worktree list --porcelain
~~~

Xác nhận đường dẫn, branch và trạng thái của worktree. Đặc biệt kiểm tra có thay đổi chưa commit, branch còn cần giữ hoặc worktree đang bị khóa không.

### Gỡ một linked worktree sạch

Khi công việc đã hoàn tất và working tree không còn thay đổi cần giữ:

~~~bash
git worktree remove ../shop-review
~~~

Lệnh remove gỡ linked worktree và metadata tương ứng. Git thường từ chối nếu worktree còn thay đổi chưa commit hoặc file chưa được theo dõi cần bảo vệ. Đây là cơ chế giúp tránh xóa nhầm công việc.

Nếu worktree còn thay đổi, hãy kiểm tra status, commit, stash hoặc sao lưu trước. Chỉ dùng force khi đã xác nhận có thể bỏ toàn bộ nội dung trong worktree:

~~~bash
git worktree remove --force ../shop-review
~~~

Force có thể xóa dữ liệu chưa commit. Không dùng như một cách dọn thư mục nhanh khi chưa kiểm tra.

Sau khi gỡ worktree, branch của nó không tự động bị xóa. Nếu branch không còn cần thiết và đã được tích hợp, có thể xóa riêng:

~~~bash
git branch -d review/feature-search
~~~

Chỉ xóa branch sau khi xác nhận không còn commit riêng cần giữ và branch đã được tích hợp theo chính sách của nhóm. Nếu Git từ chối vì branch chưa được merge vào branch hiện tại, hãy kiểm tra lịch sử trước khi cân nhắc hành động khác; không dùng -D chỉ để bỏ qua cảnh báo.

### Worktree bị xóa thủ công hoặc đường dẫn không còn tồn tại

Nếu thư mục worktree đã bị xóa ngoài Git, metadata có thể còn trong repository. Xem danh sách worktree và các mục có thể prune:

~~~bash
git worktree prune --dry-run --verbose
~~~

Lệnh này chỉ xem trước metadata stale sẽ được dọn. Sau khi xác nhận đúng đường dẫn không còn tồn tại và không cần phục hồi, chạy:

~~~bash
git worktree prune --verbose
~~~

Prune dọn metadata của worktree không còn hợp lệ; nó không phải lệnh thay thế cho remove đối với một worktree vẫn tồn tại.

### Khóa worktree cần giữ lâu dài

Nếu worktree nằm trên ổ đĩa rời hoặc vị trí thường xuyên offline, có thể khóa để Git không coi nó là worktree stale khi đường dẫn tạm thời không truy cập được:

~~~bash
git worktree lock --reason "release validation on external drive" ../shop-release
~~~

Mở khóa khi worktree đã sẵn sàng được quản lý bình thường:

~~~bash
git worktree unlock ../shop-release
~~~

Kiểm tra trạng thái khóa bằng git worktree list --porcelain. Khóa không bảo vệ nội dung khỏi việc người dùng tự xóa file; nó chỉ đánh dấu worktree để quản lý và prune.

### Di chuyển worktree

Với linked worktree, dùng lệnh move để cập nhật cả đường dẫn và metadata:

~~~bash
git worktree move ../shop-review ../reviews/shop-review
~~~

Worktree chính không thể được di chuyển bằng lệnh này. Nếu đã di chuyển thư mục thủ công và metadata bị lệch, Git có lệnh repair trong các tình huống phù hợp:

~~~bash
git worktree repair
~~~

Ưu tiên move thay vì tự di chuyển thư mục. Nếu buộc phải sửa vị trí bên ngoài Git, kiểm tra hướng dẫn của lệnh repair và xác minh lại git worktree list sau thao tác.

## 9. Quy trình hoàn chỉnh: hotfix trong lúc vẫn làm tính năng

Ví dụ bạn đang ở feature/checkout và có lỗi cần sửa trên main.

**Tạo worktree hotfix**

~~~bash
git fetch origin
git worktree add -b hotfix/checkout-crash ../shop-hotfix origin/main
~~~

**Sửa và kiểm thử trong worktree mới**

~~~bash
cd ../shop-hotfix
git status -sb
git diff
git add -- src/checkout/CheckoutService.java
git diff --cached
git commit -m "fix(checkout): prevent crash on empty cart"
git push -u origin hotfix/checkout-crash
~~~

**Tiếp tục công việc chính**

~~~bash
cd ../shop
git status -sb
git branch --show-current
~~~

Nhánh feature/checkout và các thay đổi chưa commit vẫn nằm trong worktree ban đầu.

**Sau khi pull request hotfix được tích hợp**

~~~bash
git fetch origin
git worktree list
git worktree remove ../shop-hotfix
~~~

Nếu branch local hotfix không còn cần, xác minh đã được tích hợp rồi xóa riêng. Việc gỡ worktree và xóa branch là hai thao tác độc lập.

## 10. Checklist trước khi tạo hoặc gỡ worktree

Trước khi tạo:

- Xác nhận đang ở đúng repository.
- Fetch remote nếu worktree cần bắt đầu từ branch mới nhất.
- Chọn đường dẫn riêng, dễ nhận biết và không nằm bên trong một worktree khác.
- Chọn branch mới, branch local chưa được checkout hoặc detached HEAD.
- Kiểm tra branch đang được checkout ở đâu bằng git worktree list.

Trước khi gỡ:

- Xác nhận đúng đường dẫn worktree.
- Kiểm tra git status trong worktree cần gỡ.
- Commit, stash hoặc sao lưu nội dung cần giữ.
- Xác nhận branch không còn commit riêng cần bảo toàn.
- Dùng git worktree remove và xác minh lại bằng git worktree list.

## 11. Những nhầm lẫn thường gặp

### Worktree có tạo thêm một bản sao toàn bộ repository không?

Không. Linked worktree có thư mục file riêng nhưng dùng chung object database và nhiều metadata của repository. Nó thường tiết kiệm dung lượng và thời gian hơn việc clone thêm một bản độc lập.

### Có thể checkout cùng branch ở nhiều worktree không?

Theo quy tắc thông thường, không. Git từ chối để tránh hai index độc lập cùng làm việc trên một branch. Hãy tạo branch riêng hoặc dùng detached HEAD.

### Xóa thư mục worktree bằng File Explorer có đủ không?

Không nên. Xóa thủ công có thể để lại metadata stale. Dùng git worktree remove khi thư mục còn tồn tại; nếu đã xóa thủ công, kiểm tra và prune metadata stale sau khi xác nhận.

### Commit trong một worktree có xuất hiện trong repository chung không?

Có. Object database và branch refs được chia sẻ. Tuy nhiên, các thay đổi chưa commit trong working tree đó không xuất hiện trong worktree khác.

### Có thể gỡ worktree đang có thay đổi chưa commit không?

Git thường từ chối remove để bảo vệ dữ liệu. Hãy kiểm tra và lưu thay đổi trước; chỉ force remove khi đã xác nhận có thể bỏ nội dung đó.

### Detached HEAD có phù hợp để review không?

Có, nếu chỉ cần đọc và kiểm thử. Nếu muốn tạo commit để giữ lại, hãy tạo branch trước hoặc ngay trong worktree.

## 12. Tự kiểm tra

Bạn đang làm việc ở branch feature/payment trong thư mục chính. Một lỗi nghiêm trọng trên main cần sửa ngay, đồng thời một đồng nghiệp gửi branch feature/search để bạn review. Bạn cũng muốn thử hai cách cache song song.

Hãy trả lời:

1. Lệnh nào tạo worktree hotfix từ origin/main và tạo branch mới?
2. Lệnh nào tạo worktree detached để chỉ review origin/feature/search?
3. Nếu muốn commit sửa thử trong worktree review, cần làm gì trước?
4. Vì sao không thể checkout feature/payment ở worktree thứ hai khi branch đó đang được dùng trong thư mục chính?
5. Hai worktree thử nghiệm cần dùng branch và đường dẫn như thế nào?
6. Commit trong worktree hotfix có được nhìn thấy từ repository chính không?
7. Sau khi hotfix được tích hợp, lệnh nào gỡ worktree và lệnh nào xóa branch local?

**Gợi ý:** Dùng git worktree add -b hotfix/urgent ../shop-hotfix origin/main để tạo hotfix. Dùng git worktree add --detach ../shop-review origin/feature/search để review. Nếu cần commit, tạo branch bằng git switch -c review/search-fix. Tạo branch riêng cho từng thử nghiệm vì branch refs dùng chung và một branch chỉ được checkout ở một worktree. Commit object và branch ref được chia sẻ, nhưng thay đổi chưa commit thì riêng từng thư mục. Dùng git worktree remove để gỡ thư mục, rồi git branch -d sau khi xác nhận branch đã được tích hợp.

## Kết luận

Git worktree giúp làm nhiều công việc song song trong các thư mục riêng mà vẫn dùng chung object database và branch refs của một repository. Tạo worktree riêng cho hotfix giúp xử lý sự cố mà không phải ngắt tính năng đang làm; detached worktree phù hợp để review hoặc kiểm thử; branch riêng giúp thử nghiệm và commit độc lập. Hãy nhớ mỗi branch local chỉ được checkout ở một worktree tại một thời điểm, kiểm tra trạng thái trước khi remove, và dùng lệnh worktree để quản lý metadata. Khi phân biệt rõ phần dữ liệu dùng chung và phần trạng thái riêng, bạn có thể chuyển đổi giữa nhiều nhiệm vụ nhanh chóng mà vẫn giữ lịch sử Git có tổ chức.
