# Tạo nhánh mới từ commit hoặc nhánh có sẵn

Trong Git, tạo nhánh mới là tạo một tham chiếu tên mới trỏ tới một commit đã tồn tại. Bạn có thể bắt đầu nhánh từ commit hiện tại, tip của một nhánh khác, một commit cũ, tag phát hành hoặc remote-tracking branch. Điểm bắt đầu quyết định lịch sử mà nhánh mới kế thừa.

Việc tạo nhánh và việc chuyển sang nhánh đó là hai thao tác khác nhau. Lệnh git branch tạo tham chiếu nhưng giữ nguyên HEAD; git switch -c vừa tạo nhánh vừa chuyển HEAD và working tree sang nhánh mới. Hiểu rõ khác biệt này giúp tránh tạo nhánh ở sai commit hoặc tiếp tục sửa trên nhánh cũ.

## 1. Branch là một tham chiếu tới commit

Một branch trong Git không phải bản sao thư mục mã nguồn. Branch là một ref thường nằm trong namespace refs/heads/ và trỏ tới commit tip của một dòng phát triển.

Ví dụ:

~~~text
A---B---C  main
     \
      D---E  feature/report
~~~

Trong đồ thị trên:

- main trỏ tới commit C.
- feature/report trỏ tới commit E.
- Hai nhánh có chung lịch sử tới commit B.
- Nhánh feature/report được tạo từ commit B, sau đó có các commit D và E riêng.

Khi tạo branch từ main tại thời điểm main trỏ tới C, branch mới cũng trỏ tới C. Sau này main tiến lên D hoặc E, branch mới không tự di chuyển theo. Hai ref độc lập và chỉ cùng trỏ tới một commit tại thời điểm tạo.

### 1.1. Xem branch và commit hiện tại

~~~sh
git status -sb
git branch --show-current
git branch --list
git log --oneline --decorate --graph --all
~~~

Các lệnh này cho biết branch hiện tại, danh sách branch local và cách các commit liên kết. Nếu muốn xem chính xác ref cùng object ID:

~~~sh
git show-ref --heads
git rev-parse HEAD
~~~

Branch hiện tại thường được nhận biết qua dấu sao trong git branch. HEAD cho biết vị trí checkout hiện tại và thường là symbolic ref trỏ tới branch đó.

## 2. Chọn điểm bắt đầu trước khi tạo nhánh

Lệnh tạo nhánh nhận một start-point tùy chọn. Start-point có thể là:

- HEAD hoặc tên branch local.
- Tên remote-tracking branch như origin/main.
- SHA của một commit.
- Tag trỏ tới commit.
- Revision expression như HEAD~2 hoặc main^.

Nếu không chỉ định start-point, Git dùng HEAD hiện tại.

### 2.1. Tạo từ HEAD hiện tại

~~~sh
git branch feature/report
~~~

Lệnh tạo branch feature/report tại commit mà HEAD đang trỏ tới. HEAD không thay đổi; bạn vẫn đang ở branch cũ.

Muốn tạo và chuyển sang nhánh mới ngay:

~~~sh
git switch -c feature/report
~~~

Đây là cách thường dùng khi bắt đầu công việc mới từ branch hiện tại.

### 2.2. Tạo từ một branch local có sẵn

Giả sử repository có main và bạn muốn tạo feature/search từ tip hiện tại của main:

~~~sh
git branch feature/search main
~~~

Lệnh tạo ref feature/search trỏ tới cùng commit mà main đang trỏ tới. Nó không chuyển branch.

Nếu muốn tạo và chuyển sang branch mới:

~~~sh
git switch -c feature/search main
~~~

Sau lệnh, HEAD trỏ tới feature/search và working tree được cập nhật theo commit bắt đầu của nhánh.

### 2.3. Tạo từ một commit cụ thể

Khi cần bắt đầu nhánh từ một mốc cũ, dùng SHA commit:

~~~sh
git log --oneline --decorate -10
git branch hotfix/report-timeout <commit-sha>
git switch hotfix/report-timeout
~~~

Hoặc tạo và chuyển trong một lệnh:

~~~sh
git switch -c hotfix/report-timeout <commit-sha>
~~~

Nhánh mới trỏ tới commit đã chọn, kể cả khi commit đó không phải tip của branch hiện tại. Những commit là hậu duệ của điểm bắt đầu không tự xuất hiện trong nhánh mới.

### 2.4. Tạo từ một revision expression

Có thể chọn commit bằng các biểu thức tương đối:

~~~sh
git switch -c experiment/previous-release main~2
git switch -c hotfix/parent HEAD^
~~~

- main~2 là commit cách tip main hai bước theo chuỗi first-parent.
- HEAD^ là parent đầu tiên của commit mà HEAD đang trỏ tới.

Với merge commit, dấu ^ và dấu ~ có ý nghĩa khác nhau. Nếu cần chọn parent cụ thể, dùng HEAD^1 hoặc HEAD^2. Xác minh commit trước khi tạo branch:

~~~sh
git show --no-patch --oneline main~2
git rev-parse main~2
~~~

## 3. Tạo branch từ tag phát hành

Tag thường đánh dấu một phiên bản ổn định. Khi cần sửa lỗi trên phiên bản đã phát hành, có thể tạo hotfix branch từ tag trỏ tới commit:

~~~sh
git tag --list
git show --no-patch v2.4.0
git switch -c hotfix/2.4.1 v2.4.0
~~~

Nhánh hotfix/2.4.1 bắt đầu tại commit được tag v2.4.0 tham chiếu. Tag vẫn giữ nguyên; branch mới có thể tiến lên khi bạn tạo commit sửa lỗi.

Trước khi dùng tag, kiểm tra tag trỏ tới commit nào:

~~~sh
git rev-parse "v2.4.0^{commit}"
~~~

Branch cần một commit làm điểm bắt đầu. Nếu tag trỏ tới một loại object khác thay vì commit, revision đó không phải start-point phù hợp.

## 4. Tạo branch từ remote-tracking branch

Remote-tracking branch như origin/main là ref local ghi nhận trạng thái branch trên remote tại lần fetch gần nhất. Nó là điểm bắt đầu hữu ích khi tạo branch làm việc từ một nhánh chia sẻ.

Trước tiên cập nhật thông tin remote:

~~~sh
git fetch origin
git branch --remotes
git log --oneline --decorate -5 origin/main
~~~

Tạo branch local từ origin/main:

~~~sh
git switch -c feature/audit origin/main
~~~

Lệnh này tạo branch local feature/audit tại commit mà origin/main đang trỏ tới và chuyển sang branch mới. Muốn thiết lập upstream rõ ràng để pull/push thuận tiện, hãy dùng tùy chọn --track:

~~~sh
git switch --track -c feature/audit origin/main
~~~

Có thể tạo ref trước rồi chuyển sau:

~~~sh
git branch --track feature/audit origin/main
git switch feature/audit
~~~

Kiểm tra upstream:

~~~sh
git branch -vv
git status -sb
~~~

Kết quả thường cho thấy feature/audit theo dõi origin/main. Upstream là cấu hình liên kết để Git biết nhánh nào được dùng làm mặc định khi fetch, pull hoặc push theo cấu hình.

### 4.1. Điểm bắt đầu là snapshot, không phải liên kết trực tiếp

Khi tạo feature/audit từ origin/main, branch local nhận commit mà origin/main trỏ tới tại thời điểm tạo. Khi người khác push commit mới lên main, branch local không tự cập nhật.

Chạy fetch để cập nhật remote-tracking ref:

~~~sh
git fetch origin
git log --oneline --decorate --graph feature/audit..origin/main
~~~

Sau đó, bạn quyết định merge hoặc rebase thay đổi mới vào branch làm việc theo quy trình của nhóm. Không nhầm upstream với việc branch local tự động di chuyển theo remote.

## 5. Tạo nhánh nhưng không chuyển branch

Đôi khi bạn muốn chuẩn bị trước một branch, nhưng tiếp tục làm việc trên branch hiện tại. Dùng git branch:

~~~sh
git branch feature/documentation main
git branch --list
git status -sb
~~~

HEAD vẫn ở branch hiện tại. Branch mới chỉ là một ref khác cùng trỏ tới commit của main tại thời điểm tạo.

Khi sẵn sàng chuyển:

~~~sh
git switch feature/documentation
~~~

Kiểm tra:

~~~sh
git branch --show-current
git rev-parse HEAD
~~~

### 5.1. So sánh các lệnh tạo branch

| Lệnh | Tạo branch | Chuyển HEAD | Working tree |
|---|---|---|---|
| git branch name | Có | Không | Không đổi |
| git branch name start-point | Có | Không | Không đổi |
| git switch -c name | Có | Có | Checkout branch mới |
| git switch -c name start-point | Có | Có | Checkout từ start-point |
| git checkout -b name start-point | Có | Có | Checkout từ start-point |

git checkout -b là cú pháp truyền thống kết hợp tạo branch và checkout. Với workflow mới, git switch thường thể hiện mục đích chuyển branch rõ ràng hơn.

## 6. Kiểm tra tên branch trước khi tạo

Tên branch trở thành một phần của ref. Nên dùng tên ngắn, có ý nghĩa và tuân theo quy ước nhóm.

Ví dụ:

~~~text
feature/user-search
bugfix/login-timeout
hotfix/2.4.1
release/3.0
experiment/new-index
~~~

Kiểm tra tên có hợp lệ:

~~~sh
git check-ref-format --branch feature/user-search
~~~

Một số quy tắc:

- Không dùng dấu cách trong tên branch.
- Tránh tên có dấu .. hoặc ký tự đặc biệt bị Git cấm.
- Không kết thúc tên bằng dấu chấm hoặc .lock.
- Không bắt đầu bằng dấu gạch chéo hoặc kết thúc bằng dấu gạch chéo.
- Dùng chữ thường và dấu gạch ngang hoặc dấu gạch chéo theo quy ước nhóm.

Trước khi tạo, kiểm tra branch đã tồn tại:

~~~sh
git branch --list feature/user-search
git show-ref --verify refs/heads/feature/user-search
~~~

Nếu tên đã tồn tại, chọn tên khác hoặc xác định rõ branch hiện có có phải branch bạn cần dùng hay không.

## 7. Tạo branch khi working tree có thay đổi

Git có thể giữ một số thay đổi chưa commit khi bạn chuyển branch nếu chúng không xung đột với nội dung ở branch đích. Tuy nhiên, dựa vào hành vi đó để tạo nhánh có thể gây nhầm lẫn: thay đổi đang làm có thể được mang theo và sau đó commit nhầm branch.

Trước khi bắt đầu:

~~~sh
git status -sb
git diff
git diff --cached
~~~

Nếu thay đổi thuộc công việc mới, cách rõ ràng là tạo branch rồi mới tiếp tục sửa:

~~~sh
git switch -c feature/new-export
~~~

Nếu thay đổi đã được thực hiện trên branch khác, hãy quyết định có commit, stash hoặc chuyển chúng theo quy trình của nhóm trước khi đổi branch.

### 7.1. Tạo branch không tự động stage hoặc commit

Lệnh git branch chỉ tạo ref. Nó không đưa file vào index và không tạo commit.

Lệnh git switch -c có thể cập nhật working tree theo điểm bắt đầu, nhưng cũng không tự commit các thay đổi chưa lưu. Sau khi chuyển, kiểm tra:

~~~sh
git status --short
git diff
git diff --cached
~~~

Không dùng switch như cách lưu trữ thay đổi. Hãy commit hoặc stash khi cần bảo toàn trạng thái làm việc.

## 8. Branch từ commit cũ và detached HEAD

Khi checkout một commit trực tiếp bằng git switch --detach, HEAD không trỏ tới branch local mà trỏ trực tiếp tới commit. Trạng thái này gọi là detached HEAD.

~~~sh
git switch --detach <commit-sha>
git status -sb
~~~

Detached HEAD hữu ích khi kiểm tra một phiên bản hoặc chạy thử lịch sử cũ. Nếu tạo commit ở trạng thái này, commit mới chưa được một branch bình thường giữ lại. Có thể tạo branch ngay tại vị trí hiện tại để tiếp tục phát triển:

~~~sh
git switch -c experiment/from-old-commit
~~~

Lệnh tạo branch mới trỏ tới commit hiện tại và chuyển HEAD sang branch đó. Nếu muốn tạo branch từ commit cũ mà không vào detached HEAD, dùng trực tiếp:

~~~sh
git switch -c experiment/from-release <commit-sha>
~~~

## 9. Khi branch đã tồn tại

Lệnh tạo branch thông thường sẽ từ chối nếu tên đã được dùng:

~~~sh
git branch feature/report
~~~

Nếu feature/report tồn tại, Git báo lỗi để tránh di chuyển ref ngoài ý muốn.

Trước khi thao tác, kiểm tra:

~~~sh
git branch -vv
git log --oneline --decorate feature/report -5
~~~

Nếu mục tiêu chỉ là tiếp tục làm việc trên branch đó:

~~~sh
git switch feature/report
~~~

Nếu cần tạo một branch mới, dùng tên chưa tồn tại. Tránh dùng tùy chọn force chỉ để vượt qua lỗi trùng tên.

### 9.1. Cẩn trọng với -f và -C

git branch -f có thể di chuyển branch đã tồn tại tới start-point khác. git switch -C có thể tạo branch hoặc đặt lại branch hiện có rồi chuyển sang đó. Đây là thao tác viết lại vị trí branch, có thể làm commit hiện tại không còn được branch đó tham chiếu.

Chỉ sử dụng khi đã kiểm tra:

- Branch có đang được dùng ở worktree khác không.
- Commit cũ có được ref khác giữ lại không.
- Có thay đổi chưa commit trong working tree không.
- Việc di chuyển ref có làm mất dấu commit mà nhóm đang cần không.

Ví dụ cú pháp:

~~~sh
git branch -f feature/report <new-start-point>
git switch -C experiment/retry <start-point>
~~~

Không chạy các lệnh trên như cách sửa lỗi trùng tên. Hãy xác định trước vì sao branch đã tồn tại và có quyền di chuyển nó hay không. Git cũng từ chối một số thao tác force với branch đang được checkout trong worktree khác.

## 10. Xác minh branch mới được tạo đúng

Sau khi tạo branch, kiểm tra tên, commit và quan hệ lịch sử:

~~~sh
git branch --show-current
git branch -vv
git rev-parse HEAD
git log --oneline --decorate --graph --all -15
~~~

Nếu dùng git branch name start-point và chưa chuyển branch, kiểm tra ref mới:

~~~sh
git rev-parse refs/heads/feature/report
git show --no-patch --oneline feature/report
~~~

So sánh với điểm bắt đầu:

~~~sh
git rev-parse main
git rev-parse feature/report
~~~

Nếu branch vừa được tạo từ main và chưa có commit mới, hai SHA phải giống nhau tại thời điểm kiểm tra. Nếu main đã di chuyển sau khi tạo, so sánh với commit start-point đã ghi lại thay vì kỳ vọng hai ref luôn giống nhau.

## 11. Quy trình mẫu: tạo feature branch từ main

Giả sử nhóm phát triển tính năng tìm kiếm người dùng. Công việc cần bắt đầu từ main mới nhất.

**Bước 1 — cập nhật và kiểm tra main**

~~~sh
git switch main
git status -sb
git fetch origin
git log --oneline --decorate -5 origin/main
~~~

Nếu quy trình yêu cầu cập nhật main local, tích hợp origin/main theo chính sách của nhóm trước khi tạo branch.

**Bước 2 — tạo nhánh từ điểm bắt đầu đã chọn**

~~~sh
git switch -c feature/user-search origin/main
~~~

Lệnh tạo branch mới tại commit mà origin/main đang tham chiếu và chuyển sang branch đó. Nếu muốn thiết lập upstream ngay, dùng:

~~~sh
git switch --track -c feature/user-search origin/main
~~~

**Bước 3 — xác minh**

~~~sh
git status -sb
git branch -vv
git log --oneline --decorate -3
~~~

**Bước 4 — phát triển**

Sửa mã nguồn, chạy test, stage phần thay đổi liên quan và tạo commit:

~~~sh
git add src/user-search/
git commit -m "feat(search): add user search endpoint"
~~~

**Bước 5 — kiểm tra branch**

~~~sh
git log --oneline --decorate main..HEAD
git status -sb
~~~

Khi cần chia sẻ branch lên remote, push theo quy ước nhóm. Việc tạo branch local không tự tạo branch trên remote.

## 12. Quy trình mẫu: tạo hotfix từ commit phát hành cũ

Giả sử phiên bản v2.4.0 đã phát hành và nhóm cần sửa lỗi chỉ xuất hiện ở phiên bản đó.

**Bước 1 — xác minh tag**

~~~sh
git show --no-patch --oneline v2.4.0
git rev-parse "v2.4.0^{commit}"
~~~

**Bước 2 — tạo branch hotfix**

~~~sh
git switch -c hotfix/2.4.1 v2.4.0
~~~

**Bước 3 — xác minh điểm bắt đầu**

~~~sh
git log --oneline --decorate -5
git rev-parse HEAD
~~~

HEAD phải khớp commit được tag v2.4.0 tham chiếu. Các commit mới trên main không tự xuất hiện trong branch hotfix này.

**Bước 4 — sửa lỗi và commit**

~~~sh
git add src/
git commit -m "fix: handle report timeout in 2.4"
~~~

Sau khi kiểm thử và phát hành, nhóm có thể merge hoặc cherry-pick hotfix sang nhánh phát triển chính theo chính sách release.

## 13. Lỗi thường gặp

**Tạo branch xong nhưng vẫn ở branch cũ.**

- Nếu dùng git branch, đây là hành vi đúng.
- Dùng git switch <name> để chuyển sang branch mới.

**Branch được tạo từ sai commit.**

- Kiểm tra start-point trong lệnh.
- Dùng git show hoặc git rev-parse để xác minh commit.
- Tạo lại branch bằng tên khác nếu branch hiện tại đã được chia sẻ hoặc có commit mới.

**Git báo branch đã tồn tại.**

- Chạy git branch -a và git branch -vv.
- Kiểm tra branch local hay remote-tracking ref.
- Dùng branch hiện có nếu đúng mục tiêu; nếu không, chọn tên mới.

**Không tìm thấy origin/main.**

- Kiểm tra remote bằng git remote -v.
- Chạy git fetch origin.
- Xác nhận remote có branch main và refspec fetch phù hợp.

**Chuyển branch bị từ chối do thay đổi local.**

- Đọc git status.
- Commit hoặc stash thay đổi nếu cần.
- Không dùng force discard khi chưa xác định nội dung cần giữ.

**Branch mới không tự cập nhật theo branch nguồn.**

- Branch chỉ trỏ tới commit nguồn tại thời điểm tạo.
- Fetch và merge/rebase khi cần tích hợp commit mới.

**Đã tạo commit trong detached HEAD.**

- Chạy git switch -c <new-branch> để giữ commit hiện tại bằng branch mới.
- Xác minh SHA và log sau khi chuyển.

## 14. Checklist tạo branch

**Trước khi tạo**

- [ ] Xác định đúng repository và branch hiện tại.
- [ ] Kiểm tra working tree và index.
- [ ] Chọn start-point: HEAD, branch, commit, tag hay remote-tracking ref.
- [ ] Fetch remote nếu start-point là branch trên remote.
- [ ] Kiểm tra tên branch hợp lệ và chưa được sử dụng.

**Khi tạo**

- [ ] Dùng git branch nếu chỉ muốn tạo ref.
- [ ] Dùng git switch -c nếu muốn tạo và chuyển branch.
- [ ] Dùng --track nếu cần cấu hình upstream cho remote branch.
- [ ] Không dùng force khi chưa xác minh tác động.

**Sau khi tạo**

- [ ] Xác nhận branch hiện tại.
- [ ] Kiểm tra commit SHA của điểm bắt đầu.
- [ ] Xem graph để xác nhận quan hệ lịch sử.
- [ ] Xác nhận upstream nếu branch theo dõi remote.
- [ ] Kiểm tra working tree không có thay đổi ngoài dự kiến.

## 15. Câu hỏi tự đánh giá

1. Branch trong Git lưu những gì và trỏ tới loại object nào?
2. Khác biệt giữa git branch feature/x và git switch -c feature/x là gì?
3. Khi tạo branch từ main, main tiến lên sau đó thì branch mới có tự di chuyển không?
4. Làm thế nào để tạo branch từ một commit SHA cũ?
5. Khi nào nên tạo branch từ tag phát hành?
6. Remote-tracking branch như origin/main khác local branch như thế nào?
7. Tùy chọn --track thiết lập điều gì?
8. Vì sao cần kiểm tra working tree trước khi chuyển branch?
9. Detached HEAD là gì và làm sao giữ commit tạo ra trong trạng thái đó?
10. Vì sao cần cẩn trọng với git branch -f và git switch -C?

## 16. Kết luận

Tạo branch là chọn một commit làm điểm bắt đầu và tạo ref mới trỏ tới commit đó. Start-point có thể là HEAD, branch local, commit cụ thể, tag hoặc remote-tracking branch. Điểm bắt đầu quyết định lịch sử được kế thừa; sau khi tạo, branch mới và branch nguồn di chuyển độc lập.

Hãy phân biệt git branch với git switch -c, xác minh commit trước khi tạo và kiểm tra working tree sau khi chuyển. Với branch bắt đầu từ remote, fetch trước và thiết lập upstream khi cần. Khi hiểu rõ các bước này, bạn có thể tạo nhánh cho tính năng, hotfix hoặc thử nghiệm mà vẫn giữ lịch sử Git dễ theo dõi.
