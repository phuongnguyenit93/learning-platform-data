# Đặt tên nhánh khởi tạo và các mặc định của clone, fetch, pull, push

Khi bắt đầu một repository mới hoặc clone dự án từ máy chủ, Git phải chọn một số mặc định: tên nhánh ban đầu, tên remote, cách cập nhật thông tin từ remote, cách tích hợp thay đổi khi pull và cách gửi commit khi push. Các lựa chọn này ảnh hưởng trực tiếp tới cách thành viên làm việc và cách lịch sử được chia sẻ trong nhóm.

Git cho phép cấu hình các mặc định đó bằng `git config`. Ta có thể đặt cấu hình ở cấp system, global, local, worktree hoặc chỉ cho một lần chạy lệnh. Một chính sách phù hợp giúp các repository mới có quy ước nhất quán, đồng thời tránh phải truyền lặp lại nhiều tùy chọn trong từng thao tác.

Trong dịch vụ quản lý mã nguồn Git, hiểu các mặc định của `init`, `clone`, `fetch`, `pull` và `push` giúp thiết lập môi trường làm việc rõ ràng, giảm nhầm lẫn về nhánh upstream, remote đích và cách đồng bộ giữa các thành viên.

## 1. Cấu hình Git và phạm vi áp dụng

Git có nhiều cấp cấu hình. Một giá trị ở cấp cụ thể có thể ghi đè giá trị ở cấp rộng hơn.

| Cấp cấu hình | Phạm vi | Cách đặt phổ biến |
| --- | --- | --- |
| System | Toàn hệ thống hoặc máy tính | `git config --system ...` |
| Global | Người dùng hiện tại | `git config --global ...` |
| Local | Repository hiện tại | `git config --local ...` |
| Worktree | Một working tree cụ thể trong repository hỗ trợ nhiều worktree | `git config --worktree ...` |
| Command | Chỉ một lần gọi Git | `git -c key=value <command>` |

Ví dụ đặt tên nhánh mặc định cho tất cả repository mới của người dùng:

```bash
git config --global init.defaultBranch main
```

Đặt chính sách pull riêng cho repository hiện tại:

```bash
git config --local pull.rebase true
```

Chỉ áp dụng fast-forward cho một lần pull:

```bash
git -c pull.ff=only pull
```

### Xem cấu hình và nguồn của giá trị

```bash
git config --list --show-origin
git config --show-origin --get init.defaultBranch
git config --show-origin --get-all pull.rebase
```

`--show-origin` cho biết cấu hình đến từ file nào. `--get-all` hiển thị tất cả giá trị được khai báo cho một khóa, hữu ích khi cấu hình xuất hiện ở nhiều cấp.

Có thể xem trợ giúp cho từng khóa:

```bash
git help config
```

Một số khóa cấu hình được bổ sung ở các phiên bản Git mới hơn. Nếu lệnh không nhận khóa hoặc hành vi khác mô tả, hãy kiểm tra `git --version` và tài liệu tương ứng với phiên bản đang dùng.

## 2. Đặt tên nhánh mặc định khi khởi tạo repository

Khi chạy `git init`, Git tạo nhánh đầu tiên cho repository mới. Nếu không có cấu hình hoặc tùy chọn chỉ định tên, Git dùng tên mặc định của phiên bản/cách đóng gói đang cài; tên truyền thống là `master`, còn nhiều nhóm hiện dùng `main`, `trunk` hoặc tên khác theo quy ước dự án.

### Cấu hình `init.defaultBranch`

Đặt tên `main` cho các repository khởi tạo mới:

```bash
git config --global init.defaultBranch main
```

Kiểm tra:

```bash
git config --global --get init.defaultBranch
```

Tạo repository mới và xem nhánh hiện tại:

```bash
mkdir demo-project
cd demo-project
git init
git branch --show-current
```

Nếu repository chưa có commit, `git branch --show-current` có thể trả về tên nhánh khởi tạo, ví dụ `main`. Cấu hình này áp dụng cho lần `git init` mới; nó không tự đổi tên nhánh của các repository đã tồn tại.

### Chỉ định tên nhánh cho một lần init

Có thể chỉ định trực tiếp:

```bash
git init --initial-branch=main
```

Hoặc dùng dạng rút gọn:

```bash
git init -b main
```

Tùy chọn dòng lệnh áp dụng cho lần khởi tạo đó và có thể dùng để ghi đè mặc định cấu hình.

### Đổi tên nhánh đã tồn tại

Nếu repository đã có nhánh `master` và nhóm quyết định đổi thành `main`:

```bash
git branch -m master main
```

Nếu đang đứng trên nhánh cần đổi tên, có thể dùng:

```bash
git branch -m main
```

Đổi tên local branch không tự đổi tên nhánh trên remote hoặc cập nhật cấu hình máy chủ. Nếu nhánh đã được chia sẻ, cần phối hợp cập nhật remote, upstream, pull request và tài liệu nhóm theo quy trình dự án.

### `init.defaultBranch` không quyết định nhánh được clone

`init.defaultBranch` điều khiển tên nhánh khi tạo repository mới bằng `git init`. Khi clone repository đã tồn tại, Git thường checkout nhánh mà remote quảng bá qua `HEAD` (thường là nhánh mặc định trên máy chủ). Muốn chọn nhánh khác khi clone, dùng `--branch` hoặc `-b`:

```bash
git clone --branch develop https://example.com/team/project.git
```

Không nên nhầm tên nhánh khởi tạo local với nhánh mặc định được quản trị trên máy chủ.

## 3. Mặc định của `git clone`

`git clone` tạo repository local từ một nguồn khác. Ngoài URL và nhánh được checkout, Git còn phải đặt tên remote đại diện cho nguồn đó.

### Tên remote mặc định `origin`

Thông thường, clone tạo remote có tên `origin`:

```bash
git clone https://example.com/team/project.git
cd project
git remote -v
```

`origin` là tên quy ước phổ biến, không phải tên bắt buộc. Nó đại diện cho repository nguồn mà bản clone lấy dữ liệu ban đầu.

### Cấu hình `clone.defaultRemoteName`

Có thể đặt tên remote mặc định khác:

```bash
git config --global clone.defaultRemoteName upstream
```

Từ đó, các lần clone mới có thể dùng tên `upstream` thay cho `origin`:

```bash
git clone https://example.com/team/project.git
cd project
git remote -v
```

Thiết lập này chỉ đổi tên remote được tạo trong repository mới. Nó không đổi URL, không đổi nhánh mặc định và không tác động tới các remote đã cấu hình trong repository cũ. Giá trị mặc định là `origin`. Khóa này có thể không có trên một số phiên bản Git cũ; nếu không được hỗ trợ, dùng tùy chọn `--origin` khi clone.

### Chỉ định tên remote cho một lần clone

```bash
git clone --origin source https://example.com/team/project.git
```

Hoặc dạng ngắn:

```bash
git clone -o source https://example.com/team/project.git
```

Remote mới sẽ mang tên `source`. Tên này cũng được dùng trong tên remote-tracking branch, ví dụ `source/main`.

### Chọn nhánh khi clone

```bash
git clone --branch release/2.4 https://example.com/team/project.git
```

`--branch` chọn nhánh hoặc tag cần checkout. Nếu chọn một nhánh, Git tạo nhánh local tương ứng và cấu hình theo dõi remote branch. Nếu chọn tag, Git checkout tag và thường ở trạng thái detached HEAD.

### Một số tùy chọn clone khác

| Tùy chọn | Ý nghĩa |
| --- | --- |
| `--branch <name>` / `-b <name>` | Chọn nhánh hoặc tag để checkout |
| `--origin <name>` / `-o <name>` | Đặt tên remote nguồn thay cho mặc định |
| `--depth <n>` | Tạo shallow clone với độ sâu lịch sử giới hạn |
| `--single-branch` | Chỉ clone lịch sử của một nhánh |
| `--no-single-branch` | Lấy lịch sử các nhánh theo cấu hình clone/fetch thay vì giới hạn một nhánh |
| `--filter=<spec>` | Dùng partial clone để lọc object được tải ban đầu nếu server hỗ trợ |
| `--sparse` | Bắt đầu clone với sparse checkout |

Ví dụ clone nhánh `develop` với lịch sử giới hạn:

```bash
git clone --branch develop --depth 20 https://example.com/team/project.git
```

`--depth` thường khiến Git mặc định chỉ lấy một nhánh; thêm `--no-single-branch` nếu cần lấy thêm lịch sử các nhánh khác.

## 4. Mặc định của `git fetch`

`git fetch` lấy dữ liệu và cập nhật các remote-tracking refs theo cấu hình remote. Nó không tự merge hoặc rebase thay đổi vào nhánh local đang đứng.

### Ref mapping của remote

Khi clone, Git thường cấu hình refspec fetch cho remote, ví dụ:

```text
remote.origin.fetch=+refs/heads/*:refs/remotes/origin/*
```

Refspec này cho biết khi fetch `origin`, Git lấy các nhánh trên remote và cập nhật các remote-tracking refs tương ứng như `origin/main`, `origin/develop`.

Kiểm tra cấu hình:

```bash
git config --get-all remote.origin.fetch
git remote show origin
```

Nếu remote có cấu hình refspec giới hạn, `git fetch origin` chỉ cập nhật các ref được chỉ định. Vì vậy, không phải mọi nhánh trên máy chủ đều chắc chắn xuất hiện trong local.

### `fetch.prune`: dọn remote-tracking branch đã bị xóa

Mặc định, `fetch.prune` là `false`: khi một nhánh bị xóa trên remote, remote-tracking ref tương ứng có thể vẫn còn trong repository local cho tới khi được dọn. Bật prune toàn cục:

```bash
git config --global fetch.prune true
```

Hoặc chỉ bật trong repository:

```bash
git config --local fetch.prune true
```

Khi fetch, Git sẽ loại bỏ remote-tracking refs không còn khớp với refspec trên remote. Có thể chạy một lần:

```bash
git fetch --prune origin
```

Prune tác động tới tham chiếu remote-tracking local; nó không xóa nhánh local cùng tên và cũng không xóa nhánh trên máy chủ.

### `fetch.pruneTags`: dọn tag không còn trên remote

Tag có cách xử lý khác branch. Mặc định, tag được fetch theo cơ chế auto-follow khi tag trỏ tới commit thuộc lịch sử đang được fetch. Tag local thường không tự bị xóa khi tag tương ứng bị xóa trên remote.

Nếu nhóm muốn prune tag theo remote, có thể cấu hình:

```bash
git config --global fetch.pruneTags true
```

`fetch.pruneTags` mặc định là `false`. Khi bật, khóa này yêu cầu Git xử lý prune tag cùng với prune; nó không tự bật `fetch.prune`. Hãy hiểu rõ rằng tag local không được quản lý riêng có thể bị xóa nếu không còn tồn tại trên remote được fetch. Có thể chạy tường minh:

```bash
git fetch --prune --prune-tags origin
```

Trước khi bật chính sách prune tag toàn cục, cần thống nhất cách nhóm sử dụng tag. Một số tag local có thể chỉ phục vụ thử nghiệm hoặc đánh dấu cá nhân và không có trên remote.

### `--no-tags` và `remote.<name>.tagOpt`

Nếu không muốn tự động lấy tag trong một lần fetch:

```bash
git fetch --no-tags origin
```

Có thể đặt hành vi cho một remote:

```bash
git config remote.origin.tagOpt --no-tags
```

Thông thường, Git tự động lấy các tag trỏ tới commit thuộc lịch sử đang được fetch (auto-follow). Dùng `--tags` để lấy tất cả tag được remote quảng bá, hoặc `--no-tags` để tắt auto-follow cho lần gọi đó.

## 5. Mặc định của `git pull`

`git pull` về cơ bản fetch từ remote upstream rồi tích hợp thay đổi vào nhánh hiện tại bằng merge hoặc rebase. Cách tích hợp ảnh hưởng tới lịch sử và cách xử lý khi nhánh local, remote đã phân kỳ.

### `pull.rebase`: merge hay rebase khi pull?

Mặc định của `pull.rebase` là `false`, nghĩa là pull dùng merge. Có thể đặt:

```bash
git config --global pull.rebase false
```

Khi đó, nếu nhánh local và upstream phân kỳ, Git có thể tạo merge commit để kết hợp hai lịch sử.

Nếu nhóm muốn lịch sử tuyến tính hơn, có thể đặt:

```bash
git config --global pull.rebase true
```

Khi pull, Git phát lại các commit local chưa có trên upstream lên trên commit mới nhận được. Rebase tạo mã commit mới cho các commit được phát lại; không nên dùng tùy tiện trên commit đã chia sẻ mà người khác đang dựa vào.

Ngoài `true` và `false`, `pull.rebase` còn hỗ trợ các lựa chọn như `merges` để cố gắng giữ cấu trúc merge trong quá trình rebase, hoặc `interactive` để dùng interactive rebase. Hãy kiểm tra tài liệu phiên bản Git trước khi dùng các chế độ nâng cao.

### `pull.ff`: chính sách fast-forward

`pull.ff` điều khiển cách Git xử lý fast-forward khi pull; giá trị mặc định là `true`:

| Giá trị | Hành vi |
| --- | --- |
| `true` | Cho phép fast-forward nếu có thể; nếu nhánh đã phân kỳ, merge có thể tạo merge commit |
| `false` | Tạo merge commit ngay cả khi có thể fast-forward |
| `only` | Chỉ cho phép cập nhật fast-forward; dừng nếu lịch sử local và upstream đã phân kỳ |

Ví dụ chỉ cho phép fast-forward:

```bash
git config --global pull.ff only
```

Thiết lập này phù hợp với nhóm muốn pull an toàn và tự quyết định cách xử lý khi nhánh phân kỳ. Nếu dùng `pull.rebase=true`, Git sẽ rebase các commit local theo chính sách đó; không nên đưa ra nhiều cấu hình pull mâu thuẫn mà không hiểu tương tác giữa chúng.

### Tự stash trước khi merge hoặc rebase

Khi working tree có thay đổi chưa commit, pull có thể bị chặn hoặc gặp khó khăn khi tích hợp. Git có cấu hình `merge.autoStash` và `rebase.autoStash` để tự stash trước khi merge/rebase rồi áp dụng lại sau:

```bash
git config --global merge.autoStash true
git config --global rebase.autoStash true
```

Có thể yêu cầu cho một lần pull bằng tùy chọn:

```bash
git pull --autostash --rebase
```

Autostash hữu ích khi thay đổi local không xung đột với thay đổi được pull. Nếu việc áp dụng lại stash phát sinh conflict, người dùng vẫn phải giải quyết thủ công. Nó không thay thế việc lưu trữ công việc quan trọng hoặc kiểm tra trạng thái trước khi pull.

### Chỉ định chính sách cho một lần pull

```bash
git pull --rebase
git pull --no-rebase
git pull --ff-only
```

Các tùy chọn dòng lệnh có thể ghi đè cấu hình cho lần gọi đó. Khi làm việc trong nhóm, nên thống nhất quy tắc pull để lịch sử giữa các thành viên dễ dự đoán.

## 6. Upstream và cấu hình nhánh ảnh hưởng tới pull

Để `git pull` không cần truyền remote và tên nhánh mỗi lần, nhánh local thường theo dõi một nhánh từ xa gọi là upstream.

Một nhánh local có thể có các cấu hình:

```text
branch.main.remote = origin
branch.main.merge = refs/heads/main
```

Điều này cho biết nhánh `main` local theo dõi nhánh `main` trên remote `origin`.

Kiểm tra:

```bash
git branch -vv
git config --get branch.main.remote
git config --get branch.main.merge
```

### `branch.autoSetupMerge`

Khi tạo nhánh từ một remote-tracking branch, Git có thể tự cấu hình upstream. `branch.autoSetupMerge` mặc định là `true`; khóa này điều khiển hành vi đó:

```bash
git config --global branch.autoSetupMerge true
```

Các giá trị thường gặp gồm:

- `true`: tự thiết lập upstream khi điểm bắt đầu là remote-tracking branch.
- `false`: không tự thiết lập upstream.
- `always`: luôn thiết lập quan hệ theo dõi khi tạo nhánh từ điểm bắt đầu phù hợp.
- `inherit`: kế thừa cấu hình upstream từ nhánh bắt đầu.
- `simple`: chỉ tự thiết lập khi tên nhánh local và nhánh bắt đầu phù hợp theo quy tắc đơn giản.

Ví dụ tạo nhánh theo dõi remote branch:

```bash
git switch --track origin/feature/payment
```

Hoặc tạo nhánh với tên local khác:

```bash
git switch -c payment-work --track origin/feature/payment
```

### `branch.autoSetupRebase`

Khóa này quy định việc tự đặt `branch.<name>.rebase` khi tạo nhánh có upstream:

```bash
git config --global branch.autoSetupRebase remote
```

Các giá trị có thể gồm `never` (mặc định), `local`, `remote` hoặc `always`. Ví dụ `remote` áp dụng rebase mặc định cho nhánh theo dõi remote branch. Khóa này là một cách thiết lập chi tiết hơn bên cạnh `pull.rebase`; hãy xem cấu hình cụ thể của nhánh nếu hành vi pull khác kỳ vọng.

## 7. Mặc định của `git push`

`git push` gửi commit từ repository local lên remote. Git cần xác định remote đích và nhánh nào sẽ được cập nhật.

### `push.default`: chọn nhánh được push

Khóa `push.default` quy định hành vi khi chạy `git push` mà không truyền refspec. Từ Git 2.0, giá trị mặc định là `simple`:

| Giá trị | Hành vi |
| --- | --- |
| `nothing` | Không push nếu chưa chỉ định refspec rõ ràng |
| `current` | Push nhánh hiện tại lên nhánh cùng tên trên remote đích |
| `upstream` | Push nhánh hiện tại lên nhánh upstream đang theo dõi |
| `simple` | Push nhánh hiện tại lên upstream khi tên nhánh local và upstream khớp; đây là mặc định phổ biến hiện nay |
| `matching` | Push tất cả nhánh local có nhánh cùng tên tồn tại trên remote |

Có thể đặt rõ mặc định phổ biến:

```bash
git config --global push.default simple
```

`simple` giúp tránh push nhầm nhánh khi local branch theo dõi một upstream khác tên. `current` phù hợp nếu nhóm muốn luôn đẩy nhánh hiện tại lên nhánh cùng tên. `matching` có phạm vi rộng hơn và có thể gửi nhiều nhánh cùng lúc, vì vậy cần hiểu rõ trước khi sử dụng.

### `push.autoSetupRemote`: tự thiết lập upstream lần đầu

Thông thường, lần push đầu tiên của một nhánh mới cần chỉ rõ remote và tên nhánh, đồng thời đặt upstream:

```bash
git push --set-upstream origin feature/payment
```

`push.autoSetupRemote` mặc định là `false`. Có thể bật tự thiết lập upstream cho lần push mặc định:

```bash
git config --global push.autoSetupRemote true
```

Khi nhánh hiện tại chưa có upstream và push mặc định được dùng, Git có thể tự thiết lập quan hệ theo dõi tới nhánh cùng tên trên remote mặc định. Khóa này hữu ích với workflow `push.default=simple` hoặc `current`; hãy kiểm tra phiên bản Git nếu không thấy hành vi này.

### Chọn remote mặc định bằng `remote.pushDefault`

Trong quy trình fork, một nhánh có thể fetch từ `upstream` nhưng push lên `origin`. Có thể đặt remote mặc định cho push:

```bash
git config --global remote.pushDefault origin
```

Khóa này chọn remote push mặc định khi nhánh không có cấu hình push riêng. `branch.<name>.pushRemote` của nhánh hiện tại có mức ưu tiên cao hơn; nếu không có cấu hình push riêng, Git mới xét `remote.pushDefault` rồi các quy tắc remote/upstream khác. Nó không thay đổi remote upstream dùng cho pull.

### `branch.<name>.pushRemote`: remote push riêng cho một nhánh

Một nhánh cụ thể có thể ghi đè remote push mặc định:

```bash
git config branch.feature-payment.pushRemote origin
```

Trong khi nhánh local vẫn có thể theo dõi `upstream/main` để pull, push của `feature-payment` sẽ hướng tới `origin`. Cấu hình này rất hữu ích trong workflow fork.

### `push.followTags`

Khi push commit, có thể gửi kèm annotated tag liên quan tới các commit đang được đẩy:

```bash
git config --global push.followTags true
```

`push.followTags` làm cho push mặc định hoạt động như có tùy chọn `--follow-tags`: Git gửi các annotated tag chưa có trên remote và trỏ tới commit reachable từ các ref đang push. Nó không tự gửi mọi tag local; nếu cần gửi tất cả tag, dùng `git push --tags`.

## 8. Một bộ cấu hình mẫu cho nhóm phát triển

Không có một bộ mặc định phù hợp với mọi nhóm. Ví dụ dưới đây minh họa một chính sách thường gặp cho nhóm dùng `main`, muốn dọn remote-tracking refs cũ, dùng rebase khi pull và push nhánh hiện tại theo upstream.

```bash
# Nhánh mặc định khi git init
git config --global init.defaultBranch main

# Remote mặc định được tạo bởi clone
git config --global clone.defaultRemoteName origin

# Dọn remote-tracking branch đã bị xóa trên remote
git config --global fetch.prune true

# Pull bằng rebase để giữ lịch sử tuyến tính
git config --global pull.rebase true

# Tự thiết lập upstream khi push nhánh mới lần đầu
git config --global push.autoSetupRemote true

# Push nhánh hiện tại theo upstream một cách rõ ràng
git config --global push.default simple

# Gửi annotated tag liên quan khi push commit
git config --global push.followTags true
```

Nếu nhóm muốn pull chỉ fast-forward và tự xử lý khi nhánh phân kỳ, có thể chọn:

```bash
git config --global --unset pull.rebase
git config --global pull.ff only
```

Chọn một chính sách pull nhất quán với cách nhóm quản lý lịch sử. Đừng sao chép bộ cấu hình mẫu mà không kiểm tra quy trình review, release và quy định nhánh bảo vệ của dự án.

## 9. Kiểm tra cấu hình hiệu lực

Khi Git có hành vi khác dự kiến, hãy kiểm tra các khóa cấu hình liên quan trước khi thay đổi.

```bash
git config --show-origin --get init.defaultBranch
git config --show-origin --get clone.defaultRemoteName
git config --show-origin --get fetch.prune
git config --show-origin --get fetch.pruneTags
git config --show-origin --get pull.rebase
git config --show-origin --get pull.ff
git config --show-origin --get push.default
git config --show-origin --get push.autoSetupRemote
git config --show-origin --get remote.pushDefault
```

Xem cấu hình của nhánh hiện tại:

```bash
git branch -vv
git config --get-regexp '^branch\.'
```

Xem cấu hình remote:

```bash
git remote -v
git config --get-regexp '^remote\.'
```

Nếu cần xóa một cấu hình local hoặc global:

```bash
git config --global --unset pull.rebase
git config --local --unset push.default
```

`--unset` chỉ xóa khóa trong phạm vi được chỉ định. Nếu khóa được khai báo ở nhiều cấp, xóa một giá trị có thể chưa làm thay đổi giá trị hiệu lực; hãy kiểm tra lại bằng `--show-origin`.

## 10. Các tình huống thường gặp

| Tình huống | Nguyên nhân có thể có | Cách xử lý |
| --- | --- | --- |
| Repository mới vẫn tạo nhánh `master` | `init.defaultBranch` chưa được đặt hoặc bị cấu hình cấp khác ghi đè | Kiểm tra `git config --show-origin`; dùng `git init -b main` cho lần tạo cụ thể |
| Clone tạo remote tên khác `origin` | `clone.defaultRemoteName` hoặc `--origin` đã đặt tên khác | Dùng `git remote -v` để xác nhận và truyền đúng tên remote trong lệnh |
| Nhánh local không tự theo dõi upstream | Nhánh được tạo không dùng `--track` hoặc `branch.autoSetupMerge` không bật theo cách mong muốn | Dùng `git branch --set-upstream-to=<remote>/<branch>` hoặc tạo nhánh với `--track` |
| Pull báo nhánh đã phân kỳ | Local và upstream đều có commit riêng; chính sách pull chưa rõ | Chọn merge, rebase hoặc fast-forward-only theo quy ước nhóm |
| Pull tạo merge commit ngoài ý muốn | `pull.rebase=false` và fast-forward không thể thực hiện | Đặt `pull.rebase=true` hoặc `pull.ff=only` tùy workflow |
| Push báo không có upstream | Nhánh mới chưa được gắn upstream | Dùng `git push -u <remote> <branch>` hoặc cân nhắc `push.autoSetupRemote` |
| Push đi sai remote | `remote.pushDefault` hoặc `branch.<name>.pushRemote` trỏ tới remote khác dự kiến | Kiểm tra `git remote -v` và cấu hình branch/remote |
| Remote-tracking branch cũ vẫn còn | `fetch.prune` chưa bật | Dùng `git fetch --prune` hoặc bật `fetch.prune` |
| Tag local biến mất sau fetch prune | Đã bật prune tag và tag không tồn tại trên remote | Kiểm tra chính sách `fetch.pruneTags` và cách nhóm quản lý tag |

### Quy trình fork: fetch từ upstream, push lên origin

Giả sử `origin` là fork của nhóm, `upstream` là repository gốc:

```bash
git remote add upstream https://example.com/original/project.git
git config remote.pushDefault origin
git fetch upstream
git switch -c feature/payment upstream/main
git push -u origin feature/payment
```

Trong workflow này, nhánh tính năng bắt đầu từ `upstream/main`, nhưng push lên fork `origin`. Cấu hình `remote.pushDefault` giúp lệnh push mặc định hướng tới fork; `branch.feature-payment.pushRemote` có thể đặt cụ thể hơn nếu cần.

## 11. Thực hành

Thực hiện trong repository thử nghiệm để quan sát tác động của từng mặc định:

1. Kiểm tra `git config --show-origin --list` và ghi lại các giá trị hiện có.
2. Đặt `init.defaultBranch` thành `main`, tạo repository mới bằng `git init` và kiểm tra tên nhánh.
3. Clone một repository thử nghiệm, kiểm tra tên remote mặc định; thử `clone.defaultRemoteName` hoặc `--origin` trong một bản clone khác.
4. Tạo một nhánh remote thử nghiệm, fetch rồi xóa nhánh trên remote; bật `fetch.prune` và fetch lại để quan sát remote-tracking ref được dọn.
5. Tạo hai commit độc lập trên local và remote để làm nhánh phân kỳ; thử `pull.rebase=false`, `pull.rebase=true` và `pull.ff=only` trong các bản clone riêng.
6. Tạo nhánh local mới và thử push với `push.default=simple`; quan sát yêu cầu upstream.
7. Bật `push.autoSetupRemote`, push nhánh mới và kiểm tra bằng `git branch -vv`.
8. Tạo workflow fork giả lập với `origin` và `upstream`, đặt `remote.pushDefault` rồi xác minh remote đích.
9. Kiểm tra tác động của `fetch.pruneTags` trong repository chỉ dùng tag thử nghiệm.

Sau thực hành, hãy giải thích khóa nào ảnh hưởng tới repository mới, khóa nào chỉ điều khiển thao tác fetch/pull/push và vì sao cấu hình local có thể ghi đè global.

## 12. Tự kiểm tra kiến thức

1. `init.defaultBranch` ảnh hưởng tới `git init` như thế nào?
2. Vì sao `init.defaultBranch` không tự quyết định nhánh được checkout khi clone?
3. `clone.defaultRemoteName` khác `--origin` ở phạm vi áp dụng ra sao?
4. `fetch.prune` xóa loại tham chiếu nào và có tác động tới nhánh local hay không?
5. `fetch.pruneTags` cần được hiểu cùng với chính sách prune như thế nào?
6. `pull.rebase` và `pull.ff` điều khiển những lựa chọn nào khi pull?
7. Upstream branch được lưu qua các khóa cấu hình nào?
8. `push.default=simple` khác `current` và `upstream` như thế nào?
9. `remote.pushDefault` và `branch.<name>.pushRemote` phối hợp ra sao?
10. Vì sao cần kiểm tra nguồn cấu hình bằng `git config --show-origin`?

## Kết luận

`init.defaultBranch` đặt tên nhánh cho repository mới; `clone.defaultRemoteName` chọn tên remote mặc định; `fetch.prune` và `fetch.pruneTags` quản lý tham chiếu cũ; `pull.rebase` và `pull.ff` quyết định cách tích hợp thay đổi; `push.default`, `push.autoSetupRemote` và các khóa remote/branch xác định cách gửi commit. Hãy chọn chính sách theo workflow của nhóm, kiểm tra nguồn cấu hình và upstream trước khi thay đổi. Khi hiểu rõ phạm vi từng khóa, ta có thể tạo repository nhất quán và giảm lỗi do Git chọn sai nhánh hoặc remote mặc định.
