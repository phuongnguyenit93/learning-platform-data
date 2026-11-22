# Thiết lập upstream bằng git push -u và git branch --set-upstream-to

Khi làm việc với branch trên máy cá nhân và branch tương ứng trên remote, Git cần biết hai branch nào có quan hệ theo dõi với nhau. Quan hệ này được gọi là **upstream** hoặc *tracking branch*. Khi upstream đã được thiết lập, Git có thể cho biết branch local đang ahead hay behind so với remote, đồng thời giúp các lệnh như `git pull` và `git push` xác định nơi đồng bộ theo cấu hình.

Hai cách thường dùng để thiết lập quan hệ đó là `git push -u` và `git branch --set-upstream-to`. Cách thứ nhất thường dùng khi lần đầu đẩy một branch local lên remote; cách thứ hai dùng khi branch trên remote đã tồn tại và bạn muốn gắn branch local với branch đó.

## 1. Upstream là gì?

Giả sử repository có branch `feature/login` trên máy cá nhân và branch `feature/login` trên remote `origin`. Khi branch local theo dõi branch remote tương ứng, Git lưu thông tin upstream để biết nơi cần so sánh và đồng bộ.

Ví dụ:

```text
Local branch:            feature/login
Remote:                  origin
Remote-tracking branch:  origin/feature/login
Upstream:                origin/feature/login
```

Ở đây cần phân biệt ba khái niệm:

- **Local branch** (`feature/login`): branch bạn đang phát triển trong repository local.
- **Remote branch** (`refs/heads/feature/login`): branch thật được lưu trong repository trên server.
- **Remote-tracking branch** (`origin/feature/login`): ref local phản ánh lần fetch gần nhất của branch remote đó.

Khi bạn chạy `git fetch origin`, Git cập nhật các remote-tracking branch theo cấu hình fetch. Upstream của branch local thường trỏ đến một remote-tracking branch như `origin/feature/login`, chứ không phải kết nối trực tiếp đến server ở mọi thao tác.

Upstream giúp Git trả lời những câu hỏi sau:

- Branch local đang có commit nào chưa được đẩy lên remote?
- Remote có commit nào mà local chưa tích hợp?
- Khi chạy `git pull` trên branch hiện tại, nên lấy thay đổi từ remote và branch nào?
- Khi chạy `git push` không ghi rõ remote và branch đích, Git nên dùng đích nào theo cấu hình push?

## 2. Thiết lập upstream ngay lần đầu push bằng `git push -u`

Đây là cách thuận tiện khi bạn vừa tạo branch local và muốn đẩy nó lên remote lần đầu.

Giả sử bạn đang đứng trên branch `feature/login`:

```bash
git switch -c feature/login
```

Sau khi tạo commit và sẵn sàng chia sẻ branch, chạy:

```bash
git push -u origin feature/login
```

Tùy chọn `-u` là viết tắt của `--set-upstream`. Khi push thành công, Git thiết lập branch remote vừa đẩy làm upstream cho branch local tương ứng. Nếu remote chưa có branch `feature/login`, lệnh push sẽ tạo branch đó (miễn là bạn có quyền và không có quy tắc phía server ngăn cản).

Sau lần đầu này, nếu bạn vẫn đang ở `feature/login`, thường có thể dùng:

```bash
git push
git pull
```

Git sử dụng upstream đã lưu kết hợp với cấu hình push/pull để xác định nguồn và đích mặc định. Bạn vẫn có thể ghi rõ remote và branch khi muốn kiểm soát chính xác thao tác.

Lệnh dài tương đương với `-u` là:

```bash
git push --set-upstream origin feature/login
```

### Ví dụ một vòng làm việc

```bash
# Tạo branch mới từ vị trí hiện tại.
git switch -c feature/login

# Chỉnh sửa và tạo commit.
git add src/login/LoginService.java
git commit -m "feat: add login service"

# Đẩy branch và thiết lập upstream.
git push -u origin feature/login

# Các lần đồng bộ sau trên branch này.
git push
git pull
```

`git push -u` chỉ thiết lập upstream khi thao tác push thành công hoặc branch đã được cập nhật thành công theo kết quả push. Nếu push bị từ chối, ví dụ do non-fast-forward hoặc không đủ quyền, hãy xử lý nguyên nhân trước rồi kiểm tra lại quan hệ upstream.

## 3. Gắn upstream cho branch đã tồn tại bằng `git branch --set-upstream-to`

Có trường hợp branch trên remote đã tồn tại, nhưng branch local chưa được thiết lập upstream. Ví dụ, đồng nghiệp đã tạo và push `feature/login`, bạn đã fetch remote rồi tạo một branch local cùng tên nhưng chưa có tracking information.

Trước tiên, cập nhật thông tin remote:

```bash
git fetch origin
```

Kiểm tra remote-tracking branch đã có:

```bash
git branch -r
```

Nếu kết quả có `origin/feature/login`, gắn nó làm upstream cho branch local:

```bash
git branch --set-upstream-to=origin/feature/login feature/login
```

Lệnh này cấu hình branch local `feature/login` theo dõi `origin/feature/login`. Nó **không push**, không tạo branch trên server và không tự merge hoặc rebase nội dung. Lệnh chỉ thiết lập quan hệ theo dõi trong cấu hình repository local.

Nếu bạn đang đứng ngay trên branch `feature/login`, có thể bỏ tên branch ở cuối:

```bash
git branch --set-upstream-to=origin/feature/login
```

Git sẽ thiết lập upstream cho branch hiện tại. Dạng rút gọn của tùy chọn là `-u`, nhưng để tránh nhầm với `git push -u`, khi học nên dùng tên đầy đủ `--set-upstream-to`.

### Trường hợp local branch chưa có

Nếu bạn muốn tạo local branch mới dựa trên branch remote và thiết lập tracking ngay lúc tạo, có thể dùng:

```bash
git switch --track -c feature/login origin/feature/login
```

Lệnh này tạo branch local `feature/login` từ `origin/feature/login` và cấu hình upstream. Nó khác với `git branch --set-upstream-to`, vốn gắn upstream cho một branch local đã tồn tại.

## 4. So sánh hai cách thiết lập upstream

| Tiêu chí | `git push -u` | `git branch --set-upstream-to` |
|---|---|---|
| Mục đích chính | Push branch và thiết lập upstream | Thiết lập hoặc đổi upstream của branch local |
| Yêu cầu branch remote | Có thể chưa tồn tại; push có thể tạo branch | Remote-tracking branch đích cần tồn tại ở local |
| Có gửi commit lên server không? | Có, thực hiện push | Không |
| Có thể dùng khi branch remote đã có sẵn? | Có | Có, thường là lựa chọn trực tiếp khi chỉ cần gắn tracking |
| Trường hợp thường gặp | Lần đầu publish branch local | Branch local đã có, cần theo dõi branch remote hiện hữu hoặc đổi upstream |

Ví dụ nhanh:

```bash
# Branch local mới, đẩy lên origin và thiết lập upstream.
git push -u origin feature/login

# Branch local đã tồn tại, remote-tracking branch đã được fetch.
git fetch origin
git branch --set-upstream-to=origin/feature/login feature/login
```

Chọn lệnh theo trạng thái branch và mục tiêu hiện tại. Nếu bạn cần chia sẻ branch lần đầu, `git push -u` thực hiện cả hai việc trong một bước. Nếu branch remote đã có và bạn chỉ cần gắn quan hệ theo dõi cho branch local, `git branch --set-upstream-to` thể hiện rõ ý định đó.

## 5. Kiểm tra upstream đã được thiết lập

Sau khi cấu hình, nên xác minh Git đang theo dõi đúng branch.

### Dùng git branch -vv

```bash
git branch -vv
```

Ví dụ:

```text
  main           1a2b3c4 [origin/main] initial commit
* feature/login  5d6e7f8 [origin/feature/login: ahead 1] add login service
```

Phần trong ngoặc vuông cho biết upstream. `ahead 1` nghĩa là branch local có một commit chưa có trong upstream theo lần đồng bộ gần nhất. Nếu thấy `behind 2`, upstream có hai commit mà local chưa có. Nếu thấy `ahead 1, behind 2`, hai phía đã phân kỳ và cần tích hợp thay đổi theo quy trình của nhóm.

Thông tin ahead/behind dựa trên các commit và remote-tracking ref hiện có trong local. Để có dữ liệu mới nhất từ server, hãy fetch trước khi đánh giá:

```bash
git fetch origin
git branch -vv
```

### Dùng git status

```bash
git status -sb
```

Ví dụ:

```text
## feature/login...origin/feature/login [ahead 1]
```

Dòng này cho biết branch hiện tại là `feature/login`, upstream là `origin/feature/login`, và local đang ahead một commit.

### Xem tên upstream bằng biểu thức @{upstream}

```bash
git rev-parse --abbrev-ref --symbolic-full-name '@{upstream}'
```

Nếu upstream được thiết lập, kết quả thường là:

```text
origin/feature/login
```

Nếu branch hiện tại chưa có upstream, Git sẽ báo lỗi vì không thể phân giải `@{upstream}`.

### Xem cấu hình branch

Git lưu quan hệ tracking trong cấu hình repository. Với branch `feature/login`, có thể xem:

```bash
git config --get branch.feature/login.remote
git config --get branch.feature/login.merge
```

Kết quả thường là:

```text
origin
refs/heads/feature/login
```

`branch.<name>.remote` xác định remote được theo dõi; `branch.<name>.merge` xác định ref của branch trên remote đó. Git kết hợp hai giá trị này để xác định upstream tương ứng.

## 6. Thay đổi hoặc gỡ upstream

Nếu branch local đang theo dõi sai remote hoặc sai branch, bạn có thể gắn lại upstream.

Ví dụ, chuyển branch local `feature/login` sang theo dõi branch cùng tên trên remote `upstream`:

```bash
git fetch upstream
git branch --set-upstream-to=upstream/feature/login feature/login
```

Thao tác này thay đổi cấu hình tracking của branch local. Nó không di chuyển commit và không thay đổi nội dung working tree.

Nếu muốn xóa quan hệ upstream khỏi branch local:

```bash
git branch --unset-upstream feature/login
```

Hoặc nếu đang đứng trên branch cần gỡ:

```bash
git branch --unset-upstream
```

Sau khi gỡ, branch local vẫn tồn tại và các commit vẫn được giữ nguyên. Tuy nhiên, các lệnh dựa vào upstream mặc định có thể yêu cầu bạn chỉ rõ remote/branch hoặc thiết lập lại tracking.

## 7. Những lỗi thường gặp và cách xử lý

### Không có upstream configured

Khi chạy `git pull` hoặc `git push` mà branch chưa có upstream, Git có thể báo rằng branch hiện tại không có tracking information.

Nếu muốn push branch local lên remote và thiết lập upstream:

```bash
git push -u origin feature/login
```

Nếu branch remote đã tồn tại và bạn chỉ cần gắn tracking:

```bash
git fetch origin
git branch --set-upstream-to=origin/feature/login feature/login
```

### Không tìm thấy remote-tracking branch

Lệnh sau có thể thất bại nếu `origin/feature/login` chưa tồn tại trong repository local:

```bash
git branch --set-upstream-to=origin/feature/login feature/login
```

Trước hết, kiểm tra remote và fetch:

```bash
git remote -v
git fetch origin
git branch -r
```

Nếu branch vẫn không xuất hiện, kiểm tra tên branch trên server bằng:

```bash
git ls-remote --heads origin
```

Xác nhận đúng remote, đúng tên branch và quyền truy cập trước khi thiết lập lại.

### Push bị từ chối do non-fast-forward

Nếu remote đã có commit mà local chưa tích hợp, push có thể bị từ chối vì non-fast-forward. `-u` không giải quyết xung đột lịch sử. Hãy fetch và xem trạng thái trước:

```bash
git fetch origin
git status -sb
git log --oneline --graph --decorate --all -20
```

Sau đó chọn cách tích hợp theo quy ước nhóm, chẳng hạn merge hoặc rebase, giải quyết conflict nếu có, chạy kiểm tra cần thiết rồi mới push lại. Tránh dùng `--force` chỉ để vượt qua lỗi khi chưa hiểu lịch sử remote.

### Theo dõi nhầm branch hoặc nhầm remote

Nếu `git status -sb` hiển thị upstream không như mong đợi, dùng:

```bash
git branch -vv
git remote -v
```

Sau khi xác định đúng remote và branch, chạy `git branch --set-upstream-to=<remote>/<branch> <local-branch>` để sửa tracking. Không đổi upstream theo phỏng đoán, vì `git pull` sau đó có thể tích hợp thay đổi từ một branch không liên quan.

### Push mặc định không dùng branch như mong muốn

Upstream và đích push mặc định có liên quan nhưng không hoàn toàn đồng nhất. Cách `git push` chọn đích còn phụ thuộc cấu hình `push.default` và các tùy chọn liên quan. Trong nhiều repository mới, `push.default=simple` là mặc định: Git thường yêu cầu branch local và branch upstream có cùng tên khi push không ghi rõ refspec.

Khi cần rõ ràng, hãy ghi remote và branch đích:

```bash
git push origin feature/login
```

Hoặc kiểm tra cấu hình:

```bash
git config --get push.default
```

Không nên thay đổi cấu hình toàn cục chỉ để xử lý một branch nếu chưa hiểu ảnh hưởng đến các repository khác.

## 8. Quy trình thực tế cho branch mới

Giả sử bạn được giao phát triển chức năng đăng nhập và muốn chia sẻ branch `feature/login` lên remote `origin`.

```bash
# 1. Cập nhật thông tin từ remote.
git fetch origin

# 2. Tạo branch làm việc.
git switch -c feature/login

# 3. Thực hiện thay đổi và commit.
git add src/login/LoginService.java
git commit -m "feat: add login service"

# 4. Push lần đầu và thiết lập upstream.
git push -u origin feature/login

# 5. Xác minh upstream.
git branch -vv
git status -sb

# 6. Các lần làm việc tiếp theo.
git pull
git push
```

Nếu branch `feature/login` đã được tạo trên remote bởi thành viên khác, bạn có thể fetch, tạo local branch dựa trên remote-tracking branch và thiết lập tracking ngay:

```bash
git fetch origin
git switch --track -c feature/login origin/feature/login
```

Nếu local branch đã tồn tại từ trước, dùng `git branch --set-upstream-to` để gắn nó với remote-tracking branch đã fetch.

## 9. Ghi nhớ

Upstream là quan hệ giữa branch local và branch mà nó theo dõi trên remote. Quan hệ này giúp Git so sánh ahead/behind và xác định nguồn đồng bộ mặc định.

- Dùng `git push -u origin <branch>` khi muốn push branch và thiết lập upstream trong cùng thao tác.
- Dùng `git branch --set-upstream-to=<remote>/<branch> <local-branch>` khi branch local đã tồn tại và bạn muốn gắn hoặc đổi upstream.
- Dùng `git fetch` trước khi tham chiếu một remote-tracking branch chưa có trong local.
- Dùng `git branch -vv`, `git status -sb` hoặc `git rev-parse '@{upstream}'` để xác minh cấu hình.

Sau khi thiết lập, hãy kiểm tra upstream có đúng remote và đúng branch dự định hay không. Một tracking relationship chính xác giúp quá trình đồng bộ repository rõ ràng và giảm nguy cơ pull hoặc push nhầm dòng phát triển.
