# Kết nối nhiều remote cho kho chính và bản fork

Khi tham gia một dự án mã nguồn mở hoặc cộng tác qua fork, lập trình viên thường làm việc với ít nhất hai repository từ xa: **repository chính** của dự án và **fork** thuộc tài khoản của mình. Repository chính là nơi nhóm duy trì phiên bản chuẩn; fork là repository riêng để bạn có quyền đẩy nhánh công việc lên. Git cho phép một repository local lưu nhiều remote để lấy thay đổi từ nơi này và gửi công việc đến nơi khác.

Mô hình thường dùng là đặt remote `upstream` trỏ đến repository chính và `origin` trỏ đến fork. Bạn fetch từ `upstream` để cập nhật kiến thức về dự án, tạo nhánh công việc từ lịch sử mới nhất, rồi push nhánh lên `origin` để mở pull request hoặc merge request về repository chính.

## 1. Phân biệt repository chính, fork và remote

**Repository chính (canonical repository)** là kho mã nguồn mà dự án xem là nguồn chuẩn. Nhóm duy trì repository này, xem xét đóng góp và tích hợp thay đổi.

**Fork** là một repository độc lập được tạo từ repository khác trên nền tảng lưu trữ mã nguồn. Fork thường thuộc tài khoản cá nhân hoặc tổ chức của người đóng góp. Bạn có thể có quyền ghi vào fork ngay cả khi chỉ có quyền đọc repository chính.

**Remote** là một tên cấu hình trong repository local, dùng để tham chiếu đến một repository từ xa. Tên `origin` và `upstream` chỉ là quy ước phổ biến:

| Tên thường dùng | Trỏ đến | Mục đích phổ biến |
|---|---|---|
| `origin` | Fork của bạn | Push nhánh cá nhân và lưu bản làm việc trên máy chủ |
| `upstream` | Repository chính của dự án | Fetch thay đổi mới từ dự án gốc |

Git không tự hiểu `origin` là fork hay `upstream` là kho chính. Chúng chỉ là bí danh do người dùng đặt. Bạn có thể đặt tên `my-fork`, `canonical` hoặc tên khác; điều quan trọng là biết mỗi tên đang trỏ đến đâu.

Fork cũng không phải là một nhánh Git. Fork là repository riêng trên dịch vụ lưu trữ; nhánh như `main` hoặc `feature/login` là các tham chiếu commit bên trong từng repository. Việc tạo fork thường được thực hiện trên giao diện của GitHub, GitLab hoặc dịch vụ tương tự. Lệnh `git remote add` chỉ đăng ký địa chỉ của repository đó trong repository local, không tạo fork trên máy chủ.

## 2. Mô hình kết nối thường gặp

Giả sử dự án gốc có địa chỉ `https://github.com/example-org/sample-app.git`, còn fork của bạn có địa chỉ `git@github.com:my-account/sample-app.git`.

```text
       Repository chính của dự án
       https://github.com/example-org/sample-app.git
                       |
                       | fetch
                       v
              Remote: upstream
                       |
                       v
             Repository local
                       |
                       | push
                       v
               Remote: origin
                       |
                       v
                  Fork của bạn
       git@github.com:my-account/sample-app.git
```

Trong repository local, sau khi fetch, bạn thường thấy các remote-tracking branch như `upstream/main` và `origin/main`. Đây là các tham chiếu local ghi nhận trạng thái nhánh đã biết ở từng remote tại lần fetch gần nhất. Chúng không phải nhánh làm việc mà bạn trực tiếp chỉnh sửa.

Nhánh `main` là nhánh local của bạn. Bạn có thể cập nhật nó từ `upstream/main`, sau đó push kết quả lên `origin/main` để đồng bộ fork. Các nhánh tính năng thường được tạo từ `upstream/main` hoặc từ `main` đã được đồng bộ.

## 3. Clone fork và thêm remote của repository chính

Trong quy trình fork phổ biến, trước tiên bạn tạo fork trên nền tảng lưu trữ mã nguồn. Sau đó clone fork về máy:

```bash
# Clone fork của bạn
git clone git@github.com:my-account/sample-app.git
cd sample-app

# Kiểm tra remote được tạo tự động bởi git clone
git remote -v
```

Lệnh `git clone` thường tạo remote tên `origin` trỏ đến URL đã dùng để clone. Vì URL trên thuộc fork, `origin` sẽ trỏ đến fork của bạn.

Tiếp theo, thêm repository chính với tên `upstream`:

```bash
git remote add upstream https://github.com/example-org/sample-app.git

# Kiểm tra cả hai remote
git remote -v
```

Kết quả có dạng:

```text
origin    git@github.com:my-account/sample-app.git (fetch)
origin    git@github.com:my-account/sample-app.git (push)
upstream  https://github.com/example-org/sample-app.git (fetch)
upstream  https://github.com/example-org/sample-app.git (push)
```

Thông thường bạn chỉ cần đọc từ `upstream`. Nếu không có quyền ghi vào repository chính, đừng cấu hình hoặc sử dụng nó làm đích push. URL trong ví dụ có thể thay bằng HTTPS hoặc SSH tùy cách xác thực mà tổ chức hỗ trợ.

Nếu remote `upstream` đã tồn tại, không thêm lại. Hãy kiểm tra bằng `git remote -v`; nếu địa chỉ sai, cập nhật bằng:

```bash
git remote set-url upstream https://github.com/example-org/sample-app.git
```

## 4. Fetch từ từng remote và đọc remote-tracking branch

Mỗi remote có thể có lịch sử và nhánh riêng. Dùng tên remote để chọn nguồn fetch:

```bash
# Lấy nhánh và commit mới từ repository chính
git fetch upstream

# Lấy trạng thái mới từ fork của bạn
git fetch origin

# Liệt kê các nhánh remote-tracking
git branch -r

# Xem các nhánh local cùng upstream branch đang theo dõi
git branch -vv
```

Sau `git fetch upstream`, Git cập nhật các tham chiếu như `upstream/main` theo refspec fetch đã cấu hình. Sau `git fetch origin`, các tham chiếu như `origin/main` được cập nhật. Fetch không tự hợp nhất những thay đổi này vào `main` và thông thường không sửa working tree.

Bạn có thể xem lịch sử giữa hai nhánh:

```bash
# Các commit có trong repository chính nhưng chưa có trong main local
git log --oneline main..upstream/main

# Các commit có trong main local nhưng chưa có trong upstream/main
git log --oneline upstream/main..main

# Xem đồ thị lịch sử của mọi remote và nhánh local
git log --oneline --graph --decorate --all
```

Hai biểu thức `A..B` có nghĩa là các commit có thể đi tới từ `B` nhưng không có trong tập commit có thể đi tới từ `A`. Chúng giúp nhận biết nhánh nào đang đi trước hoặc có thay đổi riêng.

## 5. Đồng bộ nhánh chính local với repository chính

Fork thường bị chậm hơn repository chính vì nhóm dự án tiếp tục tích hợp thay đổi. Bạn nên đồng bộ nhánh chính của fork trước khi bắt đầu công việc mới.

Trước tiên, bảo đảm working tree không có thay đổi chưa xử lý:

```bash
git status
```

Nếu đang có chỉnh sửa chưa commit, hãy commit hoặc cất tạm theo quy trình phù hợp trước khi chuyển nhánh hay tích hợp lịch sử. Sau đó fetch và cập nhật `main`:

```bash
# Lấy trạng thái mới nhất của repository chính
git fetch upstream

# Chuyển sang nhánh chính local
git switch main

# Chỉ cập nhật nếu main có thể tiến thẳng đến upstream/main
git merge --ff-only upstream/main
```

`--ff-only` yêu cầu cập nhật theo kiểu fast-forward. Nếu `main` local chỉ đang đứng sau `upstream/main`, Git di chuyển nhánh `main` đến commit mới mà không tạo merge commit. Nếu hai lịch sử đã phân kỳ, lệnh sẽ dừng để bạn xem xét cách tích hợp.

Khi `main` local đã được cập nhật, đẩy nó lên fork:

```bash
git push origin main
```

Lệnh này cập nhật nhánh `main` trên fork nếu máy chủ cho phép và lịch sử đáp ứng quy tắc cập nhật. Nếu fork đã có commit riêng hoặc bị phân kỳ, hãy xem đồ thị và thống nhất cách xử lý với quy trình của dự án. Có thể dùng merge hoặc rebase theo chính sách nhóm; không dùng force push chỉ để làm cho lệnh thành công.

Nếu nhóm cho phép rebase và `main` local có các commit riêng chưa chia sẻ, một lựa chọn là:

```bash
git fetch upstream
git switch main
git rebase upstream/main
```

Rebase phát lại các commit riêng của `main` trên nền `upstream/main` và tạo commit mới. Nếu có xung đột, giải quyết từng tệp rồi dùng `git add` và `git rebase --continue`; nếu cần quay lại trước khi rebase, dùng `git rebase --abort`. Hãy tuân theo quy tắc của dự án, đặc biệt nếu các commit đó đã được chia sẻ với người khác.

## 6. Tạo nhánh tính năng từ repository chính và push lên fork

Khi bắt đầu một thay đổi mới, hãy tạo nhánh từ nền tảng đã được cập nhật. Có thể tạo trực tiếp từ remote-tracking branch:

```bash
# Cập nhật thông tin từ repository chính
git fetch upstream

# Tạo nhánh mới từ upstream/main
git switch -c feature/search upstream/main
```

Thực hiện chỉnh sửa, kiểm tra và tạo commit trên nhánh `feature/search`:

```bash
git status
git add src/search
git commit -m "Add search support"
```

Sau đó push nhánh lên fork:

```bash
git push -u origin feature/search
```

Tùy chọn `-u` (hay `--set-upstream`) thiết lập nhánh remote-tracking mặc định cho nhánh local. Trong trường hợp này, `feature/search` local sẽ theo dõi `origin/feature/search`. Những lần push hoặc pull tiếp theo có thể dùng mặc định của nhánh mà không cần ghi lại đầy đủ tên remote và nhánh.

Trên nền tảng lưu trữ mã nguồn, tạo pull request hoặc merge request với:

- **Source/head:** fork của bạn, nhánh `feature/search`.
- **Target/base:** repository chính, nhánh `main` (hoặc nhánh đích mà dự án quy định).

Fork là nơi lưu nhánh để người khác xem xét; repository chính là nơi nhận thay đổi sau khi được chấp thuận và tích hợp.

## 7. Cập nhật nhánh tính năng khi repository chính có commit mới

Trong lúc bạn phát triển, `upstream/main` có thể tiếp tục thay đổi. Fetch định kỳ để biết trạng thái mới:

```bash
git fetch upstream
git switch feature/search
```

Nếu chính sách nhóm yêu cầu lịch sử tuyến tính và nhánh chỉ do bạn sử dụng, có thể rebase nhánh tính năng lên nền mới:

```bash
git rebase upstream/main
```

Nếu có xung đột, Git tạm dừng rebase. Mở các tệp được báo, giải quyết nội dung, đánh dấu đã xử lý rồi tiếp tục:

```bash
git add src/search/SearchService.java
git rebase --continue
```

Nếu quyết định không tiếp tục:

```bash
git rebase --abort
```

Rebase thay đổi mã commit của các commit được phát lại. Nếu nhánh đã được nhiều người cùng sử dụng, hãy phối hợp trước khi viết lại lịch sử; trong trường hợp đó, merge `upstream/main` vào nhánh tính năng có thể phù hợp hơn:

```bash
git merge upstream/main
```

Sau khi tích hợp xong, push nhánh lên fork:

```bash
git push origin feature/search
```

Nếu bạn đã push nhánh trước khi rebase, push thông thường có thể bị từ chối vì lịch sử remote không còn là tổ tiên của lịch sử local. Hãy xem xét tác động và quy định của nhóm trước khi cập nhật nhánh đã chia sẻ; không tự động dùng `--force`.

## 8. Hiểu đúng hai khái niệm upstream

Trong Git, từ “upstream” xuất hiện ở hai ngữ cảnh dễ gây nhầm:

1. **Remote tên `upstream`:** bí danh do người dùng đặt, thường trỏ đến repository chính của dự án.
2. **Upstream branch của một nhánh local:** nhánh remote-tracking mà nhánh local được cấu hình để theo dõi, chẳng hạn `origin/feature/search`.

Hai khái niệm này không đồng nghĩa. Một nhánh local có thể theo dõi `origin/main`, `upstream/main` hoặc một nhánh khác tùy cấu hình. Sau lệnh `git push -u origin feature/search`, upstream branch của `feature/search` thường là `origin/feature/search`, mặc dù repository chính vẫn được đặt tên remote là `upstream`.

Kiểm tra cấu hình theo dõi:

```bash
git branch -vv
```

Nếu cần thay đổi nhánh mà `main` local theo dõi:

```bash
git branch --set-upstream-to=upstream/main main
```

Lệnh này chỉ thay đổi cấu hình theo dõi của nhánh local `main`; nó không đổi URL của remote và cũng không fetch dữ liệu. Hãy fetch trước để tham chiếu `upstream/main` đã được cập nhật.

## 9. Các lệnh quản lý nhiều remote

| Mục đích | Lệnh |
|---|---|
| Liệt kê tên remote | `git remote` |
| Xem URL fetch/push | `git remote -v` |
| Xem chi tiết một remote | `git remote show upstream` |
| Thêm repository chính | `git remote add upstream <url>` |
| Đổi URL của remote | `git remote set-url upstream <url>` |
| Đổi tên remote | `git remote rename upstream canonical` |
| Xóa remote khỏi cấu hình local | `git remote remove upstream` |
| Fetch một remote | `git fetch upstream` |
| Fetch mọi remote | `git fetch --all` |

Xóa remote chỉ xóa cấu hình kết nối trong repository local và các tham chiếu remote-tracking liên quan; thao tác này không xóa repository trên máy chủ. Trước khi đổi tên hoặc xóa remote, kiểm tra các nhánh local đang theo dõi remote đó bằng `git branch -vv` và điều chỉnh cấu hình nếu cần.

## 10. Những lỗi thường gặp khi làm việc với fork

| Tình huống | Nguyên nhân thường gặp và cách kiểm tra |
|---|---|
| Push báo không có quyền | Có thể bạn đang push vào repository chính. Kiểm tra `git remote -v` và dùng remote trỏ đến fork. |
| Không thấy commit mới của dự án | Có thể bạn mới fetch `origin` mà chưa fetch `upstream`. Chạy `git fetch upstream`. |
| `git remote add upstream` báo remote đã tồn tại | Remote đã được cấu hình. Kiểm tra URL bằng `git remote -v`; dùng `git remote set-url` nếu cần sửa. |
| Không thấy `upstream/main` | Chưa fetch repository chính, tên nhánh mặc định khác `main`, hoặc refspec không lấy nhánh đó. Kiểm tra `git branch -r` và `git remote show upstream`. |
| Push nhánh tính năng nhưng pull lại theo nhánh khác | Nhánh local chưa thiết lập upstream branch như mong muốn. Kiểm tra `git branch -vv` và dùng `git push -u origin <branch>`. |
| Push bị từ chối non-fast-forward | Nhánh remote có commit chưa có trong local hoặc lịch sử đã được viết lại. Fetch, xem đồ thị và tích hợp theo chính sách nhóm. |

Trước mỗi lần push, đặc biệt khi repository local có nhiều remote, hãy xác nhận remote đích và nhánh đích. Một lệnh `git push origin ...` và `git push upstream ...` có thể gửi cùng một commit đến hai repository hoàn toàn khác nhau.

## 11. Tự kiểm tra

1. **Trong workflow fork thông thường, `origin` và `upstream` thường trỏ đến đâu?**
   - `origin` trỏ đến fork của bạn; `upstream` trỏ đến repository chính của dự án.
2. **Lệnh nào cập nhật thông tin từ repository chính mà không tự merge vào `main` local?**
   - `git fetch upstream`.
3. **`upstream/main` có phải nhánh local để bạn trực tiếp commit không?**
   - Không. Đây là remote-tracking branch phản ánh trạng thái nhánh `main` ở remote `upstream` tại lần fetch gần nhất.
4. **Vì sao dùng `git push -u origin feature/search`?**
   - Đẩy nhánh lên fork và thiết lập `origin/feature/search` làm upstream branch của nhánh local để các lần đồng bộ sau thuận tiện hơn.
5. **Remote tên `upstream` và upstream branch có giống nhau không?**
   - Không. Một cái là bí danh remote; cái còn lại là nhánh mà nhánh local được cấu hình theo dõi.

## Kết luận

Kết nối nhiều remote cho phép repository local lấy lịch sử từ repository chính và gửi nhánh công việc đến fork của bạn. Với quy ước phổ biến, `upstream` là nguồn cập nhật, `origin` là nơi lưu nhánh cá nhân. Hãy kiểm tra URL bằng `git remote -v`, fetch đúng remote, đồng bộ nhánh nền trước khi phát triển, tạo nhánh tính năng từ lịch sử phù hợp và dùng `git push -u origin <branch>` để công bố nhánh trên fork. Việc xác định rõ repository đích và nhánh đích giúp quá trình đóng góp diễn ra có kiểm soát.
