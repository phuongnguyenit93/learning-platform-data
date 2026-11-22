# Tạo, liệt kê và đổi tên nhánh cục bộ

Branch (nhánh) là một tham chiếu có tên trỏ tới một commit. Nhờ branch, mỗi phần việc có thể tiến triển độc lập trên cùng một repository mà không cần sao chép toàn bộ thư mục mã nguồn. Trong Git, tạo một branch mới thường chỉ tạo thêm một tham chiếu nhẹ; thao tác này không nhân bản toàn bộ lịch sử commit.

Ba việc cơ bản khi quản lý nhánh cục bộ là tạo nhánh cho công việc mới, liệt kê để biết repository đang có những nhánh nào và đổi tên khi tên hiện tại không còn phù hợp. Nắm rõ các lệnh này giúp tổ chức công việc theo tính năng, sửa lỗi hoặc mục tiêu phát hành, đồng thời tránh nhầm lẫn giữa branch local và remote-tracking branch.

Trong dịch vụ quản lý mã nguồn Git, branch là cách phân chia luồng phát triển. Tên nhánh rõ ràng, danh sách nhánh dễ đọc và quy trình đổi tên có kiểm soát giúp nhóm phối hợp tốt hơn khi review, tích hợp và bàn giao thay đổi.

## 1. Branch là gì?

Một branch trong Git là một tên tham chiếu tới commit. Ví dụ, `main` có thể trỏ tới commit mới nhất của nhánh chính, còn `feature/payment-summary` trỏ tới commit mới nhất của nhánh phát triển tính năng thanh toán.

Minh họa:

~~~text
A --- B --- C  main
           \
            D --- E  feature/payment-summary
~~~

Trong hình:

- `main` trỏ tới commit `C`.
- `feature/payment-summary` trỏ tới commit `E`.
- Hai branch chia sẻ lịch sử từ `A` tới `C`.
- Commit `D` và `E` chỉ thuộc lịch sử nhánh tính năng tại thời điểm minh họa.

Branch không phải bản sao thư mục chứa file. Nó là một ref trỏ tới commit. Khi tạo branch, Git thường chỉ ghi một ref mới trỏ vào commit hiện tại hoặc commit được chỉ định.

### HEAD và branch hiện tại

`HEAD` cho biết vị trí làm việc hiện tại. Thông thường, `HEAD` là symbolic ref trỏ tới branch đang checkout. Ví dụ, khi đang ở `feature/payment-summary`, `HEAD` trỏ tới `refs/heads/feature/payment-summary`.

Kiểm tra:

~~~bash
git branch --show-current
git symbolic-ref --short HEAD
git rev-parse --short HEAD
~~~

Hai lệnh đầu cho biết tên branch hiện tại khi `HEAD` đang gắn với một branch. Lệnh thứ ba hiển thị commit mà `HEAD` đang trỏ tới.

Nếu repository đang ở detached HEAD, `git branch --show-current` có thể không in tên branch và `git symbolic-ref` không trả về branch. Trạng thái này khác với việc branch bị mất; `HEAD` đang trỏ trực tiếp tới một commit. Bài này tập trung vào thao tác với branch cục bộ trong trạng thái làm việc thông thường.

## 2. Kiểm tra trước khi tạo branch

Trước khi tạo nhánh cho một phần việc, xem trạng thái repository:

~~~bash
git status -sb
git branch --show-current
git log --oneline --decorate -5
~~~

Các lệnh giúp xác định:

- Bạn đang ở branch nào.
- Working tree có thay đổi chưa commit hay không.
- Commit hiện tại là gì.
- Repository có đang ở trạng thái cần hoàn tất merge hoặc rebase hay không.

Tạo branch không tự commit các thay đổi đang có. Nếu working tree có chỉnh sửa, branch mới vẫn bắt đầu từ commit hiện tại, còn những chỉnh sửa chưa commit vẫn nằm trong working tree và có thể đi theo khi chuyển branch nếu không xung đột.

Để giữ công việc dễ quản lý, nên hiểu rõ thay đổi hiện tại thuộc phần việc nào trước khi tạo hoặc chuyển nhánh. Nếu cần tách hai phần việc, có thể commit phần đã hoàn tất hoặc stash phần tạm thời theo quy trình của nhóm.

## 3. Tạo branch bằng git branch

Cú pháp đơn giản:

~~~bash
git branch <branch-name>
~~~

Ví dụ:

~~~bash
git branch feature/payment-summary
~~~

Lệnh tạo branch `feature/payment-summary` tại commit mà `HEAD` đang trỏ tới. Nó không tự chuyển sang branch mới. Sau lệnh này, branch hiện tại vẫn là branch cũ.

Kiểm tra:

~~~bash
git branch
git branch --show-current
~~~

Trong danh sách branch, dấu `*` đánh dấu branch hiện tại. Branch vừa tạo sẽ xuất hiện nhưng chưa có dấu `*` nếu bạn chưa chuyển sang nó.

### Tạo branch từ một commit cụ thể

Có thể chỉ định start point:

~~~bash
git branch feature/payment-summary origin/main
~~~

Branch mới bắt đầu từ commit mà `origin/main` đang trỏ tới. Start point có thể là:

- Tên branch local, ví dụ `main`.
- Remote-tracking branch, ví dụ `origin/main`.
- Mã commit.
- Tag.
- Một biểu thức revision mà Git có thể phân giải thành commit.

Ví dụ tạo branch từ một commit đã biết:

~~~bash
git branch fix/payment-timeout a1b2c3d
~~~

Trước khi dùng commit ID hoặc ref làm start point, xác nhận nó thuộc lịch sử mong muốn. Nếu tạo từ sai điểm, branch vẫn hợp lệ về mặt Git nhưng có thể chứa nền tảng mã nguồn không đúng.

## 4. Tạo branch và chuyển sang branch mới

Trong thực tế, khi bắt đầu tính năng hoặc sửa lỗi, ta thường muốn tạo branch và chuyển sang đó ngay.

### Dùng git switch -c

~~~bash
git switch -c feature/payment-summary
~~~

`-c` có nghĩa là create. Git tạo branch mới từ commit hiện tại rồi chuyển `HEAD` sang branch đó.

Có thể chỉ định start point:

~~~bash
git switch -c feature/payment-summary origin/main
~~~

Lệnh này tạo branch local từ commit mà remote-tracking branch `origin/main` đang trỏ tới và chuyển sang branch mới.

### Dùng git checkout -b

~~~bash
git checkout -b feature/payment-summary
~~~

Đây là cú pháp quen thuộc trước khi `git switch` được giới thiệu. Nó cũng tạo branch và chuyển sang branch mới.

Với thao tác branch thông thường, nên ưu tiên `git switch` vì tên lệnh mô tả rõ việc chuyển nhánh. `git checkout` vẫn hữu ích trong các quy trình cũ và còn hỗ trợ nhiều chế độ thao tác khác.

### So sánh các lệnh tạo nhánh

| Lệnh | Tạo branch? | Chuyển sang branch mới? |
| --- | --- | --- |
| `git branch feature/x` | Có | Không |
| `git branch feature/x main` | Có, từ `main` | Không |
| `git switch -c feature/x` | Có | Có |
| `git switch -c feature/x main` | Có, từ `main` | Có |
| `git checkout -b feature/x` | Có | Có |

Không cần chạy `git branch feature/x` rồi tiếp tục `git switch -c feature/x`; branch đã tồn tại thì lệnh create lần thứ hai sẽ báo lỗi. Chọn một cách phù hợp với mục đích.

## 5. Đặt tên branch dễ hiểu

Tên branch nên cho người khác biết loại công việc và mục tiêu chính. Một số quy ước phổ biến:

| Loại công việc | Ví dụ |
| --- | --- |
| Tính năng | `feature/payment-summary` |
| Sửa lỗi | `fix/payment-timeout` |
| Hotfix | `hotfix/failed-login` |
| Công việc bảo trì | `chore/update-gradle-wrapper` |
| Tài liệu | `docs/git-branch-guide` |
| Thử nghiệm | `experiment/new-cache-policy` |

Quy ước thực tế phụ thuộc nhóm. Có nhóm dùng `feat/`, `bugfix/`, `task/` hoặc gắn mã ticket như `feature/PROJ-123-payment-summary`. Điều quan trọng là dùng thống nhất và tránh tên chung chung như `test`, `new`, `branch1`.

### Quy tắc tên ref

Tên branch phải tuân theo quy tắc ref của Git. Ví dụ, tên branch không được chứa một số ký tự đặc biệt như khoảng trắng, `~`, `^`, `:`, `?`, `*`, `[`, dấu gạch chéo ngược; cũng không được chứa các chuỗi hoặc cấu trúc không hợp lệ như `..`, `@{`, dấu `/` ở cuối hoặc thành phần kết thúc bằng `.lock`.

Dùng Git để kiểm tra tên:

~~~bash
git check-ref-format --branch feature/payment-summary
~~~

Nếu tên hợp lệ, lệnh kết thúc thành công. Nếu không, Git báo lỗi. Có thể dùng lệnh này trong script tạo branch hoặc hook kiểm tra quy ước đặt tên.

### Một số lưu ý khi đặt tên

- Dùng chữ thường và dấu gạch ngang để dễ đọc nếu đó là quy ước của nhóm.
- Tránh nhúng thông tin nhạy cảm vào tên branch.
- Không dùng tên đã dành cho branch bảo vệ như `main`, `release` hoặc `production`.
- Dùng prefix có ý nghĩa để lọc và phân nhóm.
- Tránh đổi tên branch liên tục sau khi đã chia sẻ với nhiều người.

## 6. Liệt kê branch local

Lệnh cơ bản:

~~~bash
git branch
~~~

Git hiển thị các branch local. Dấu `*` đánh dấu branch hiện tại.

Ví dụ:

~~~text
  feature/payment-summary
* main
  fix/payment-timeout
~~~

Trong ví dụ, `main` là branch hiện tại. Hai branch còn lại tồn tại trong repository nhưng không được checkout.

Lệnh này không hiển thị tất cả branch trên remote. Muốn xem remote-tracking branch, dùng các tùy chọn ở phần tiếp theo.

### Liệt kê theo mẫu

~~~bash
git branch --list 'feature/*'
~~~

Lệnh chỉ hiển thị branch local có tên khớp mẫu `feature/*`.

Một số mẫu khác:

~~~bash
git branch --list 'fix/*'
git branch --list '*payment*'
git branch --list 'release/*'
~~~

Khi truyền pattern có ký tự `*`, nên đặt trong dấu nháy để shell không tự mở rộng pattern trước khi Git nhận được.

### Xem branch hiện tại

~~~bash
git branch --show-current
~~~

Lệnh in tên branch hiện tại và phù hợp cho script cần biết đang thao tác trên nhánh nào. Nếu `HEAD` detached, kết quả có thể rỗng.

## 7. Liệt kê branch local và remote-tracking branch

Git phân biệt branch local với remote-tracking branch:

- Branch local thường nằm dưới `refs/heads/`, ví dụ `feature/payment-summary`.
- Remote-tracking branch thường nằm dưới `refs/remotes/`, ví dụ `origin/main`.

Remote-tracking branch là tham chiếu local phản ánh trạng thái remote ở lần fetch gần nhất. Nó không phải branch local đang checkout và cũng không tự cập nhật nếu chưa fetch.

### Xem branch remote-tracking

~~~bash
git branch --remotes
~~~

Hoặc dạng ngắn:

~~~bash
git branch -r
~~~

Ví dụ:

~~~text
  origin/HEAD -> origin/main
  origin/main
  origin/release/2.x
  origin/feature/payment-summary
~~~

### Xem cả local và remote-tracking

~~~bash
git branch --all
~~~

Hoặc:

~~~bash
git branch -a
~~~

Ví dụ:

~~~text
* main
  feature/payment-summary
  remotes/origin/HEAD -> origin/main
  remotes/origin/main
  remotes/origin/feature/payment-summary
~~~

Đừng nhầm `feature/payment-summary` với `origin/feature/payment-summary`. Một cái là branch local, cái còn lại là remote-tracking ref. Chúng có thể trỏ tới cùng commit hoặc khác nhau.

Nếu danh sách remote-tracking branch chưa phản ánh trạng thái mới nhất của server, cập nhật bằng:

~~~bash
git fetch origin
git branch -a
~~~

`fetch` tải thông tin refs và object mới từ remote; nó không tự chuyển branch hiện tại.

## 8. Xem thông tin commit cuối của từng branch

Thêm `-v`:

~~~bash
git branch -v
~~~

Git hiển thị mỗi branch cùng mã commit rút gọn và subject của commit cuối.

Ví dụ:

~~~text
  feature/payment-summary  a1b2c3d Add payment summary
* main                    d4e5f6a Merge release preparation
  fix/payment-timeout     123abcd Handle gateway timeout
~~~

Đây là cách nhanh để xem branch nào đã tiến tới commit nào mà không cần chạy `git log` riêng cho từng branch.

### Xem upstream và trạng thái ahead/behind

~~~bash
git branch -vv
~~~

`-vv` bổ sung thông tin upstream nếu branch đã được cấu hình theo dõi một remote-tracking branch. Ví dụ:

~~~text
  feature/payment-summary a1b2c3d [origin/feature/payment-summary: ahead 2] Add payment summary
* main                   d4e5f6a [origin/main] Merge release preparation
  fix/payment-timeout    123abcd [origin/fix/payment-timeout: behind 1] Handle gateway timeout
~~~

Các trạng thái `ahead` và `behind` phản ánh chênh lệch giữa branch local và upstream theo thông tin commit hiện có trong repository. Hãy fetch trước nếu cần đánh giá trạng thái remote mới nhất.

Nếu branch chưa có upstream, `-vv` không hiển thị phần theo dõi cho branch đó. Việc không có upstream không có nghĩa branch bị lỗi; branch local có thể chưa từng được push hoặc chưa được cấu hình tracking.

## 9. Sắp xếp và định dạng danh sách branch

Khi repository có nhiều branch, thứ tự mặc định có thể không giúp tìm nhánh cần thiết. Dùng `--sort`:

~~~bash
# Sắp xếp theo tên
git branch --sort=refname

# Commit mới nhất trước
git branch --sort=-committerdate

# Theo ngày commit tăng dần
git branch --sort=committerdate
~~~

Dấu `-` trước tên trường đảo thứ tự sắp xếp. `committerdate` là ngày commit cuối cùng mà branch trỏ tới.

### Dùng --format để tùy chỉnh cột

~~~bash
git branch --format='%(refname:short) %(objectname:short) %(subject)'
~~~

Các placeholder thường dùng:

| Placeholder | Ý nghĩa |
| --- | --- |
| `%(refname:short)` | Tên branch rút gọn |
| `%(objectname:short)` | Mã commit rút gọn |
| `%(subject)` | Subject của commit |
| `%(committerdate:short)` | Ngày commit theo định dạng ngắn |
| `%(upstream:short)` | Tên upstream rút gọn nếu có |

Ví dụ:

~~~bash
git branch --sort=-committerdate \
  --format='%(refname:short) | %(committerdate:short) | %(subject)'
~~~

Định dạng này hữu ích khi cần rà soát branch cũ, chuẩn bị dọn dẹp hoặc xuất danh sách phục vụ báo cáo. Hãy nhớ `git branch` chỉ hiển thị refs trong phạm vi tùy chọn đã chọn; danh sách không tự bao gồm mọi branch trên server.

## 10. Lọc branch theo quan hệ commit

Git có thể lọc branch theo việc branch đó đã chứa một commit hay chưa.

### Branch đã được merge vào một nhánh

~~~bash
git branch --merged main
~~~

Lệnh liệt kê branch local có tip đã reachable từ `main`, tức nội dung commit của branch đã được tích hợp vào lịch sử `main` theo quan hệ tổ tiên.

### Branch chưa được merge

~~~bash
git branch --no-merged main
~~~

Lệnh liệt kê branch local chưa được merge vào `main`. Các branch này cần được kiểm tra trước khi xóa hoặc bỏ sử dụng.

### Branch chứa một commit

~~~bash
git branch --contains a1b2c3d
~~~

Lệnh liệt kê branch có lịch sử chứa commit được chỉ định.

Có thể đảo điều kiện:

~~~bash
git branch --no-contains a1b2c3d
~~~

Các bộ lọc này giúp kiểm kê branch, nhưng không tự quyết định branch nào an toàn để xóa. Một branch chưa merge có thể chứa công việc đang làm; một branch đã merge vẫn có thể được giữ lại vì lý do release hoặc audit.

## 11. Đổi tên branch hiện tại

Khi đang đứng trên branch cần đổi tên, dùng:

~~~bash
git branch -m feature/payment-summary
~~~

Lệnh đổi tên branch hiện tại thành `feature/payment-summary`. Tùy chọn `-m` là `--move`.

Ví dụ đang ở `feature/payment`, muốn đổi thành `feature/payment-summary`:

~~~bash
git branch -m feature/payment-summary
~~~

Kiểm tra:

~~~bash
git branch --show-current
git status -sb
git branch -vv
~~~

Commit không bị tạo lại chỉ vì đổi tên branch. Branch mới vẫn trỏ tới commit cũ; `HEAD` tiếp tục gắn với branch hiện tại nhưng tên ref đã đổi.

### Đổi tên branch không checkout

Nếu đang ở branch khác nhưng muốn đổi tên một branch local khác:

~~~bash
git branch -m old-feature-name new-feature-name
~~~

Ví dụ:

~~~bash
git branch -m feature/payment feature/payment-summary
~~~

Lệnh này đổi tên ref local `feature/payment` thành `feature/payment-summary`. Branch đang checkout không đổi nếu nó là một branch khác.

## 12. Đổi tên bằng --move và --force

Hai cách viết:

~~~bash
git branch --move old-name new-name
git branch -m old-name new-name
~~~

Tương đương nhau.

Nếu tên đích đã tồn tại, `git branch -m` từ chối để tránh ghi đè nhầm. Có tùy chọn `-M` hoặc `--move --force`:

~~~bash
git branch -M old-name new-name
~~~

`-M` cho phép đổi tên ngay cả khi branch đích đã tồn tại. Đây là thao tác có thể thay thế ref đang mang tên đích; chỉ dùng khi đã kiểm tra rõ branch đích và chủ đích thay thế.

Trước khi dùng `-M`, kiểm tra:

~~~bash
git branch -vv
git log --oneline --decorate old-name -5
git log --oneline --decorate new-name -5
~~~

Nếu branch đích chứa công việc cần giữ, không dùng force rename để ghi đè. Hãy chọn tên khác hoặc phối hợp tích hợp nội dung trước.

## 13. Điều gì thay đổi khi rename branch?

Đổi tên branch local làm thay đổi tên ref dưới `refs/heads/`. Nó không tự đổi:

- Tên branch trên remote server.
- Pull request hoặc merge request đang gắn với branch remote.
- Branch local trong clone của thành viên khác.
- Tên branch mặc định của repository.
- Nội dung commit hoặc mã commit.

Git có thể di chuyển reflog và cấu hình branch liên quan theo tên mới khi rename. Tuy nhiên, remote vẫn có thể giữ branch cũ cho tới khi được cập nhật theo quy trình chia sẻ.

### Kiểm tra sau khi rename

~~~bash
git branch --list
git branch -vv
git reflog show feature/payment-summary
git config --get branch.feature/payment-summary.remote
git config --get branch.feature/payment-summary.merge
~~~

Lệnh `git config --get` cuối cùng có thể không in giá trị nếu branch chưa có upstream. Đây không nhất thiết là lỗi.

## 14. Rename branch đã có upstream

Giả sử branch local `feature/payment` đang theo dõi `origin/feature/payment`. Khi đổi tên local:

~~~bash
git branch -m feature/payment-summary
~~~

Branch local mang tên mới. Cấu hình theo dõi có thể vẫn trỏ tới upstream cũ `origin/feature/payment`; kiểm tra bằng:

~~~bash
git branch -vv
~~~

Nếu nhóm cũng muốn đổi tên branch trên remote, cần thực hiện riêng theo quy trình của Git host. Sau khi branch remote mới được tạo hoặc push, có thể thiết lập upstream:

~~~bash
git push -u origin feature/payment-summary
~~~

Lệnh này publish branch local mới lên `origin` và cấu hình upstream tương ứng nếu push thành công.

Nếu remote branch cũ cần được xóa, hãy kiểm tra pull request, pipeline, bảo vệ branch và người đang sử dụng nó trước. Xóa remote branch là thao tác riêng; đổi tên local không tự xóa branch trên server.

## 15. Đổi tên branch có đang được dùng trong worktree khác?

Một repository có thể có nhiều linked worktree. Mỗi worktree có thể checkout một branch riêng. Git thường từ chối một số thao tác rename nếu branch đang được checkout ở worktree khác, nhằm tránh làm thay đổi ref mà worktree khác đang sử dụng.

Liệt kê worktree:

~~~bash
git worktree list
~~~

Nếu không thể đổi tên branch, kiểm tra branch có đang được checkout ở worktree khác không. Phối hợp giải phóng branch tại worktree đó trước khi rename, hoặc chọn tên khác nếu công việc đang được thực hiện song song.

Không xóa thư mục worktree bằng thao tác file thông thường để né kiểm tra của Git. Dùng các lệnh `git worktree` phù hợp với trạng thái thực tế của repository.

## 16. Đổi tên branch có tên không phù hợp

Giả sử branch hiện tại tên `test` nhưng nhóm yêu cầu prefix `feature/`:

~~~bash
git branch -m feature/payment-summary
~~~

Nếu branch chưa được push, thay đổi chủ yếu nằm ở local và tương đối đơn giản. Nếu branch đã được push hoặc xuất hiện trong pull request, cần phối hợp để:

1. Thông báo tên branch mới.
2. Push branch local với tên mới.
3. Cập nhật pull request hoặc tạo pull request mới tùy nền tảng.
4. Cập nhật tham chiếu trong tài liệu, ticket và pipeline nếu có.
5. Xác nhận không còn người dùng phụ thuộc vào tên cũ.
6. Xóa branch remote cũ nếu được phép và không còn cần thiết.

Một tên branch là tham chiếu được nhiều công cụ và người dùng sử dụng. Rename local không tự cập nhật mọi tích hợp bên ngoài.

## 17. Tạo branch từ branch hiện tại hay từ upstream?

Một quyết định quan trọng là start point.

### Tạo từ branch hiện tại

~~~bash
git switch -c feature/payment-summary
~~~

Branch mới bắt đầu từ commit hiện tại. Cách này phù hợp khi bạn đang ở đúng nhánh nền và đã cập nhật nó.

### Tạo từ remote-tracking branch

~~~bash
git fetch origin
git switch -c feature/payment-summary origin/main
~~~

Branch mới bắt đầu từ trạng thái `origin/main` tại lần fetch gần nhất. Đây là lựa chọn rõ ràng khi nhóm quy định mọi feature branch phải tách từ `main`.

### Tạo branch từ một branch local khác

~~~bash
git branch feature/report-export release/2.x
~~~

Lệnh tạo branch mới từ `release/2.x` mà không chuyển sang branch mới.

Trước khi tạo, hãy kiểm tra đúng commit nguồn:

~~~bash
git log --oneline --decorate -1 main
git log --oneline --decorate -1 origin/main
~~~

Nếu `main` local chưa fetch hoặc chưa cập nhật, nó có thể khác `origin/main`. Chọn ref phù hợp với quy trình dự án.

## 18. Tạo branch theo dõi remote branch

Khi muốn tạo branch local tương ứng với một remote-tracking branch, có thể dùng:

~~~bash
git switch --track origin/feature/payment-summary
~~~

Git tạo branch local có tên phù hợp và cấu hình upstream tới remote-tracking branch được chỉ định. Nếu muốn đặt tên local khác:

~~~bash
git switch --track -c payment-summary origin/feature/payment-summary
~~~

Lệnh này tạo local branch `payment-summary` theo dõi `origin/feature/payment-summary`.

Đây là thao tác kết nối branch local với upstream, khác với việc chỉ tạo branch local bằng `git branch`. Upstream giúp các lệnh như `git status -sb`, `git pull` và `git push` biết nhánh remote liên quan theo cấu hình.

## 19. Kiểm tra branch trùng tên

Git không cho tạo branch local mới nếu tên đó đã tồn tại:

~~~bash
git branch feature/payment-summary
~~~

Nếu branch đã có, Git báo tên branch đã tồn tại. Kiểm tra trước:

~~~bash
git branch --list feature/payment-summary
git show-ref --verify refs/heads/feature/payment-summary
~~~

Nếu muốn chuyển sang branch đã có:

~~~bash
git switch feature/payment-summary
~~~

Nếu branch chưa tồn tại và muốn tạo mới, dùng `git switch -c`. Không dùng `-M` chỉ để vượt qua lỗi trùng tên; trước hết xác định branch hiện tại có chứa công việc cần giữ hay không.

## 20. Phân biệt rename, copy và tạo branch mới

Các thao tác có mục tiêu khác nhau:

| Thao tác | Lệnh | Kết quả |
| --- | --- | --- |
| Tạo branch mới | `git branch new-name` | Tạo ref mới trỏ tới commit được chọn |
| Tạo và chuyển branch | `git switch -c new-name` | Tạo ref mới và chuyển `HEAD` sang đó |
| Đổi tên branch | `git branch -m old-name new-name` | Di chuyển ref local sang tên mới |
| Copy điểm bắt đầu thành branch khác | `git branch new-name old-name` | Tạo ref mới cùng trỏ tới commit hiện tại của `old-name` |

Git không có lệnh `git branch --copy` phổ biến như thao tác rename; muốn tạo thêm một branch cùng điểm xuất phát, dùng `git branch new-name old-name`. Hai branch ban đầu trỏ tới cùng commit nhưng có thể tiến triển độc lập sau đó.

## 21. Branch name và cấu trúc refs

Branch local được lưu dưới namespace `refs/heads/`. Ví dụ:

~~~text
refs/heads/main
refs/heads/feature/payment-summary
refs/heads/fix/payment-timeout
~~~

Tên có dấu `/` tạo cảm giác phân cấp khi liệt kê, nhưng Git vẫn xem đó là tên ref. Prefix giúp nhóm và lọc branch theo quy ước.

Xem ref đầy đủ:

~~~bash
git for-each-ref --format='%(refname) %(objectname:short)' refs/heads/
~~~

Xem một ref cụ thể:

~~~bash
git show-ref --verify refs/heads/feature/payment-summary
~~~

Việc hiểu ref giúp phân biệt branch local với remote-tracking branch và tag, vốn nằm trong các namespace khác nhau.

## 22. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| `branch already exists` | Tên branch local đã được dùng | Liệt kê branch, chuyển sang branch có sẵn hoặc chọn tên mới |
| Tạo branch xong nhưng vẫn ở branch cũ | Dùng `git branch` chỉ tạo ref | Chạy `git switch <branch-name>` |
| Không thấy branch remote mới | Chưa fetch hoặc đang chỉ xem branch local | Chạy `git fetch` rồi `git branch -a` |
| `git branch --show-current` không in tên | Có thể đang ở detached HEAD | Kiểm tra `git status` và `git symbolic-ref HEAD` |
| Rename báo branch đích đã tồn tại | Tên mới đã được dùng | Kiểm tra nội dung branch đích; chọn tên khác hoặc chỉ dùng `-M` khi thực sự muốn thay thế |
| Không rename được branch | Branch có thể đang checkout ở worktree khác | Kiểm tra `git worktree list` và phối hợp giải phóng branch |
| Sau rename, upstream vẫn là tên cũ | Remote-tracking ref không tự đổi tên theo local | Kiểm tra `git branch -vv`, push branch mới và thiết lập upstream khi cần |
| Thành viên khác vẫn thấy tên cũ | Rename chỉ thay đổi local ref của bạn | Thông báo nhóm và phối hợp cập nhật remote/clone |

## 23. Quy trình thực hành: tạo và đổi tên branch tính năng

Thực hiện trong repository thử nghiệm hoặc repository dự án theo quy trình nhóm:

### Bước 1 — Kiểm tra trạng thái

~~~bash
git status -sb
git branch --show-current
git log --oneline --decorate -5
~~~

Xác nhận đang ở nhánh nền phù hợp và không có thao tác merge/rebase dang dở.

### Bước 2 — Cập nhật nhánh nền

~~~bash
git fetch origin
git log --oneline --decorate -1 origin/main
~~~

Nếu nhóm yêu cầu bắt đầu từ `origin/main`, dùng ref này làm start point.

### Bước 3 — Tạo branch

~~~bash
git switch -c feature/payment-summary origin/main
~~~

Kiểm tra:

~~~bash
git branch --show-current
git status -sb
~~~

### Bước 4 — Liệt kê branch và thông tin commit

~~~bash
git branch
git branch -a
git branch -vv
git branch --sort=-committerdate
~~~

Quan sát dấu `*`, các remote-tracking branch và thông tin upstream.

### Bước 5 — Đổi tên branch local

Nếu tên branch cần sửa theo quy ước:

~~~bash
git branch -m feature/payment-summary-v2
~~~

Kiểm tra:

~~~bash
git branch --show-current
git branch -vv
git reflog show feature/payment-summary-v2
~~~

### Bước 6 — Bàn giao tên mới

Nếu branch chưa từng push:

~~~bash
git push -u origin feature/payment-summary-v2
~~~

Nếu branch cũ đã được chia sẻ, thông báo cho nhóm và xử lý remote branch cũ theo chính sách. Không xóa branch remote cũ trước khi kiểm tra pull request, pipeline và người đang sử dụng.

## 24. Checklist quản lý branch local

- [ ] Đã kiểm tra branch hiện tại bằng `git branch --show-current`.
- [ ] Đã xem trạng thái working tree bằng `git status -sb`.
- [ ] Đã xác định đúng start point trước khi tạo branch.
- [ ] Tên branch tuân theo quy ước nhóm và `git check-ref-format`.
- [ ] Đã phân biệt `git branch` với `git switch -c`.
- [ ] Đã biết liệt kê local, remote-tracking và tất cả branch.
- [ ] Đã kiểm tra commit cuối và upstream bằng `git branch -vv` khi cần.
- [ ] Đã xác nhận branch đích chưa tồn tại trước khi rename.
- [ ] Đã hiểu `-M` có thể thay thế branch đích.
- [ ] Đã kiểm tra worktree khác nếu rename bị từ chối.
- [ ] Đã phối hợp với nhóm nếu branch cũ đã được push hoặc gắn với pull request.

## 25. Tự kiểm tra kiến thức

1. Branch trong Git là gì và nó trỏ tới đối tượng nào?
2. `git branch feature/x` khác `git switch -c feature/x` như thế nào?
3. Làm thế nào tạo branch từ `origin/main` mà không cần chuyển sang branch mới?
4. Dấu `*` trong output `git branch` biểu thị điều gì?
5. `git branch -r`, `-a` và `-vv` cung cấp thông tin gì?
6. Vì sao cần chạy `git fetch` trước khi đánh giá remote-tracking branch?
7. `git branch --merged main` và `--no-merged main` khác nhau thế nào?
8. Làm thế nào đổi tên branch hiện tại và branch không được checkout?
9. `-m` và `-M` khác nhau ở điểm nào?
10. Rename branch local có tự đổi tên branch trên remote không?
11. Upstream có vai trò gì sau khi branch được push?
12. Vì sao cần kiểm tra `git worktree list` khi rename branch bị từ chối?

## Kết luận

`git branch` tạo và liệt kê branch local; `git switch -c` tạo branch rồi chuyển sang branch đó. Dùng `git branch -a`, `-r`, `-v`, `-vv`, `--sort` và `--format` để quan sát branch cùng commit và upstream. Khi đổi tên, `git branch -m` di chuyển ref local; `-M` cho phép thay thế tên đích đã tồn tại và cần được dùng thận trọng. Rename local không tự đổi branch trên remote hoặc clone của đồng đội, vì vậy hãy kiểm tra upstream và phối hợp cập nhật các tham chiếu được chia sẻ.
