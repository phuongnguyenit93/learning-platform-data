# Thêm, đổi tên, liệt kê và xóa remote bằng git remote

## Remote trong Git là gì?

Khi làm việc với Git, một **remote** là tên viết tắt mà kho cục bộ dùng để tham chiếu tới một kho Git khác. Remote thường trỏ tới kho được lưu trên GitHub, GitLab, Bitbucket hoặc máy chủ Git của tổ chức. Nó cũng có thể trỏ tới một kho trên máy khác hoặc một đường dẫn cục bộ.

Remote giúp Git biết nơi lấy commit và nơi gửi commit khi thực hiện các thao tác như `fetch`, `pull` và `push`. Mỗi remote có tên, URL và các thiết lập đồng bộ liên quan. Những tên thường gặp là:

- `origin`: tên remote mặc định được tạo khi clone một kho.
- `upstream`: thường dùng để chỉ kho gốc mà một fork theo dõi.
- `backup`: có thể dùng cho một kho dự phòng hoặc kho sao lưu.
- `team`: có thể dùng cho kho chia sẻ nội bộ của nhóm.

Các tên trên chỉ là quy ước. Git không bắt buộc phải dùng `origin` hay `upstream`; người dùng có thể đặt tên phù hợp với cách tổ chức dự án.

Cần phân biệt ba khái niệm:

- **Remote:** cấu hình tham chiếu tới một kho khác, ví dụ `origin`.
- **Remote-tracking branch:** tham chiếu cục bộ ghi nhận trạng thái nhánh mà Git đã biết ở remote, ví dụ `origin/main`.
- **Local branch:** nhánh làm việc trong kho cục bộ, ví dụ `main` hoặc `feature/login`.

`origin/main` không phải nhánh đang làm việc trực tiếp trên máy chủ. Đây là tham chiếu cục bộ được cập nhật khi fetch dữ liệu từ remote. Nhánh `main` là nhánh cục bộ của bạn; hai nhánh có thể tiến triển khác nhau.

## Xem danh sách remote

Lệnh `git remote` liệt kê tên các remote đã cấu hình trong kho hiện tại:

~~~bash
git remote
~~~

Ví dụ kết quả:

~~~text
origin
upstream
~~~

Để xem cả URL dùng cho fetch và push, thêm tùy chọn `-v` (verbose):

~~~bash
git remote -v
~~~

Ví dụ:

~~~text
origin    git@github.com:alice/inventory-app.git (fetch)
origin    git@github.com:alice/inventory-app.git (push)
upstream  https://github.com/company/inventory-app.git (fetch)
upstream  https://github.com/company/inventory-app.git (push)
~~~

Một remote có thể có URL fetch và URL push riêng. Vì vậy, hãy đọc cả hai dòng nếu cần xác định Git đang lấy dữ liệu từ đâu và gửi dữ liệu tới đâu.

Để xem thông tin chi tiết về một remote:

~~~bash
git remote show origin
~~~

Lệnh này có thể kết nối tới remote để hiển thị URL, nhánh mặc định (HEAD), các nhánh ở remote và cấu hình theo dõi giữa nhánh cục bộ với nhánh từ xa. Nếu chỉ muốn xem thông tin đã lưu cục bộ mà không truy vấn mạng, dùng:

~~~bash
git remote show -n origin
~~~

Nếu cần liệt kê các remote-tracking branch mà kho cục bộ đang biết:

~~~bash
git branch -r
~~~

Lệnh `git branch -r` liệt kê nhánh từ xa đã được fetch về kho cục bộ; nó không phải lệnh liệt kê tên remote. Muốn xem cả nhánh cục bộ và remote-tracking branch, dùng `git branch -a`.

## Thêm remote bằng git remote add

Dùng `git remote add` khi muốn kết nối kho hiện tại với một kho Git khác. Cú pháp cơ bản:

~~~bash
git remote add <ten-remote> <url>
~~~

Ví dụ thêm kho chia sẻ của nhóm với tên `origin`:

~~~bash
git remote add origin git@github.com:company/inventory-app.git
~~~

Hoặc thêm kho gốc để theo dõi khi đang làm việc trên một fork:

~~~bash
git remote add upstream https://github.com/company/inventory-app.git
~~~

Kiểm tra lại cấu hình:

~~~bash
git remote -v
~~~

### Thêm remote có tải dữ liệu ngay

Mặc định, `git remote add` chỉ lưu cấu hình remote. Để thêm remote và fetch dữ liệu ngay sau đó, dùng tùy chọn `-f`:

~~~bash
git remote add -f upstream https://github.com/company/inventory-app.git
~~~

Sau khi fetch, có thể xem các remote-tracking branch:

~~~bash
git branch -r
~~~

Ví dụ kết quả:

~~~text
upstream/HEAD -> upstream/main
upstream/main
upstream/release
~~~

Nếu không dùng `-f`, remote vẫn được tạo nhưng các tham chiếu nhánh từ xa chưa được cập nhật cho đến khi bạn chạy:

~~~bash
git fetch upstream
~~~

Một số tùy chọn khác có thể gặp:

- `-t <branch>`: chỉ định nhánh muốn theo dõi khi fetch.
- `-m <branch>`: đặt nhánh mặc định (remote HEAD) cho remote.
- `--no-tags`: không tự động lấy tag liên quan khi fetch từ remote này.
- `--tags`: lấy tất cả tag có thể lấy được khi fetch.
- `--mirror=fetch` hoặc `--mirror=push`: cấu hình remote theo cách mirror chuyên biệt; chỉ dùng khi hiểu rõ tác động lên tham chiếu.

Trong phần lớn quy trình phát triển thông thường, lệnh thêm remote đơn giản là đủ. Sau khi thêm, hãy xác minh URL bằng `git remote -v` trước khi push để tránh gửi mã nguồn tới nhầm kho.

### Chọn URL HTTPS hay SSH

Git thường kết nối remote bằng HTTPS hoặc SSH. Ví dụ:

~~~text
HTTPS: https://github.com/company/inventory-app.git
SSH:   git@github.com:company/inventory-app.git
~~~

HTTPS thường dùng thông tin xác thực qua credential manager hoặc token theo chính sách của nền tảng. SSH sử dụng khóa SSH đã được cấu hình và cấp quyền trên dịch vụ lưu trữ Git.

Không nhúng mật khẩu, token hay khóa bí mật trực tiếp vào URL rồi lưu trong cấu hình remote. URL có thể xuất hiện trong log, bản chụp cấu hình hoặc khi chia sẻ thông tin chẩn đoán.

## Đổi tên remote bằng git remote rename

Dùng `git remote rename` khi muốn thay tên một remote mà vẫn giữ kết nối và dữ liệu đã fetch:

~~~bash
git remote rename <ten-cu> <ten-moi>
~~~

Ví dụ đổi tên `origin` thành `company`:

~~~bash
git remote rename origin company
~~~

Kiểm tra kết quả:

~~~bash
git remote -v
git branch -r
~~~

Git cập nhật cấu hình remote và đổi tên các remote-tracking reference tương ứng. Ví dụ, tham chiếu `origin/main` sẽ chuyển sang `company/main`. Các thiết lập liên quan tới remote cũng được cập nhật theo thao tác đổi tên.

Đổi tên remote không đổi tên kho trên GitHub/GitLab và không đổi URL của kho đó. Nếu mục tiêu là chuyển sang một URL mới, hãy dùng `git remote set-url`.

Không thể đổi tên remote thành một tên đã được dùng bởi remote khác. Nếu lệnh báo tên đích đã tồn tại, hãy chọn tên khác hoặc xử lý remote trùng tên sau khi xác định rõ cấu hình cần giữ.

## Thay đổi URL của remote

Khi kho được chuyển sang máy chủ mới, đổi chủ sở hữu, đổi đường dẫn hoặc chuyển từ HTTPS sang SSH, có thể cập nhật URL bằng `git remote set-url`:

~~~bash
git remote set-url origin git@github.com:company/inventory-app.git
~~~

Xác minh:

~~~bash
git remote -v
git remote get-url origin
~~~

Nếu remote có nhiều URL, xem tất cả URL bằng:

~~~bash
git remote get-url --all origin
~~~

Git hỗ trợ cấu hình URL push riêng. Khi muốn thay URL chỉ dùng cho push, thêm `--push`:

~~~bash
git remote set-url --push origin git@github.com:company/inventory-app.git
~~~

Có thể thêm một URL push bổ sung bằng `--add`, hoặc xóa một URL khớp bằng `--delete`. Hãy kiểm tra kết quả với `git remote -v` sau khi thay đổi, đặc biệt khi remote có nhiều URL. Việc thay URL chỉ cập nhật cấu hình trong kho cục bộ; nó không di chuyển dữ liệu hay đổi địa chỉ của kho trên máy chủ.

## Xóa remote bằng git remote remove

Dùng `git remote remove` khi không còn cần kết nối tới một remote:

~~~bash
git remote remove <ten-remote>
~~~

Ví dụ:

~~~bash
git remote remove upstream
~~~

Lệnh viết tắt tương đương là:

~~~bash
git remote rm upstream
~~~

Sau khi xóa, kiểm tra danh sách:

~~~bash
git remote -v
~~~

Thao tác này xóa cấu hình remote và các remote-tracking branch thuộc remote đó khỏi kho cục bộ. Nó **không xóa kho Git trên máy chủ**, không xóa fork trên GitHub/GitLab và không xóa các commit hay nhánh cục bộ của bạn.

Nếu một nhánh cục bộ từng theo dõi remote vừa bị xóa, thông tin upstream của nhánh có thể không còn hữu ích. Kiểm tra bằng:

~~~bash
git branch -vv
~~~

Nếu cần tiếp tục theo dõi một remote khác, thêm hoặc chọn remote phù hợp rồi thiết lập lại upstream, ví dụ:

~~~bash
git branch --set-upstream-to=origin/main main
~~~

Chỉ xóa remote sau khi xác định đúng tên. Nếu kho có nhiều remote, xem `git remote -v` trước để tránh xóa nhầm cấu hình đang được nhóm sử dụng.

## Làm sạch remote-tracking branch đã cũ

Xóa một remote và làm sạch nhánh từ xa đã bị xóa trên máy chủ là hai thao tác khác nhau.

Giả sử remote `origin` vẫn tồn tại nhưng nhánh `feature/old-report` đã bị xóa trên máy chủ. Tham chiếu cục bộ `origin/feature/old-report` có thể vẫn còn cho đến khi được prune.

Xem các tham chiếu sẽ bị loại bỏ:

~~~bash
git remote prune --dry-run origin
~~~

Thực hiện dọn dẹp:

~~~bash
git remote prune origin
~~~

Hoặc kết hợp prune trong lúc fetch:

~~~bash
git fetch --prune origin
~~~

Prune chỉ loại bỏ remote-tracking reference đã không còn tương ứng với nhánh trên remote. Nó không xóa nhánh cục bộ như `feature/old-report` và không xóa nhánh trên máy chủ.

## Quy trình thực tế: làm việc với fork và kho gốc

Một tình huống phổ biến là lập trình viên fork dự án về tài khoản cá nhân, sau đó clone fork về máy. Trong ví dụ này:

- `origin` trỏ tới fork của lập trình viên, nơi họ có quyền push.
- `upstream` trỏ tới kho gốc của dự án, nơi nhóm duy trì phiên bản chính.

Có thể kiểm tra và cấu hình như sau:

~~~bash
# Clone fork về máy; Git tự tạo remote origin
git clone git@github.com:alice/inventory-app.git
cd inventory-app

# Thêm kho gốc để nhận các thay đổi mới
git remote add upstream https://github.com/company/inventory-app.git

# Xem hai remote và URL tương ứng
git remote -v

# Lấy commit mới từ kho gốc
git fetch upstream

# Chuyển sang nhánh main cục bộ
git switch main

# Tích hợp thay đổi từ nhánh main của kho gốc
git merge upstream/main

# Chia sẻ main đã cập nhật lên fork của mình
git push origin main
~~~

Luồng dữ liệu trong ví dụ:

~~~mermaid
flowchart LR
    U[Kho gốc<br/>upstream] -->|fetch| L[Kho cục bộ]
    L -->|push| O[Fork cá nhân<br/>origin]
~~~

Khi dự án yêu cầu giữ lịch sử tuyến tính, nhóm có thể dùng `git rebase upstream/main` thay cho merge, theo chính sách cộng tác đã thống nhất. Không nên rebase một nhánh dùng chung mà người khác đã dựa vào nếu chưa phối hợp với họ.

## Các lệnh git remote thường dùng

| Lệnh | Công dụng |
|---|---|
| `git remote` | Liệt kê tên remote |
| `git remote -v` | Liệt kê remote cùng URL fetch/push |
| `git remote show origin` | Xem chi tiết một remote |
| `git remote add origin <url>` | Thêm remote mới |
| `git remote rename old new` | Đổi tên remote |
| `git remote set-url origin <url>` | Thay URL fetch của remote |
| `git remote get-url --all origin` | Xem tất cả URL của remote |
| `git remote remove origin` | Xóa cấu hình remote khỏi kho cục bộ |
| `git remote prune origin` | Xóa remote-tracking reference đã cũ |
| `git fetch --prune origin` | Fetch và dọn remote-tracking reference đã cũ |

## Lỗi thường gặp và cách xử lý

### Remote đã tồn tại

Khi chạy `git remote add origin ...` nhưng `origin` đã được cấu hình, Git báo remote đã tồn tại. Hãy kiểm tra URL hiện tại:

~~~bash
git remote -v
~~~

Nếu chỉ cần thay URL, dùng:

~~~bash
git remote set-url origin <url-moi>
~~~

Nếu cần kết nối thêm một kho khác, hãy đặt tên khác, chẳng hạn `upstream`.

### Không thấy nhánh remote sau khi thêm

`git remote add` không fetch dữ liệu theo mặc định. Chạy:

~~~bash
git fetch origin
git branch -r
~~~

Sau đó mới chọn remote-tracking branch để tạo hoặc cập nhật nhánh cục bộ.

### Push tới nhầm kho

Trước khi push, xác minh remote và URL:

~~~bash
git remote -v
git push -u origin feature/report
~~~

Nếu kho có nhiều remote, chỉ rõ remote đích trong lệnh push thay vì dựa vào giả định rằng `origin` luôn là nơi cần gửi mã nguồn.

### Không kết nối được sau khi đổi URL

Kiểm tra lại chính tả URL, quyền truy cập, khóa SSH hoặc credential HTTPS. Có thể kiểm tra kết nối tới remote bằng:

~~~bash
git ls-remote origin
~~~

Lệnh này đọc các tham chiếu từ remote mà không thay đổi nhánh hiện tại. Nếu không có quyền hoặc thông tin xác thực hợp lệ, cần xử lý cấu hình truy cập trước khi fetch/push.

### Xóa remote nhưng vẫn thấy nhánh cục bộ

Đây là hành vi bình thường. `git remote remove` xóa remote và các remote-tracking reference liên quan; nhánh cục bộ như `main` hoặc `feature/report` vẫn tồn tại. Kiểm tra bằng:

~~~bash
git branch
git branch -vv
~~~

## Thói quen làm việc an toàn

- Dùng tên remote mô tả được vai trò của kho, đặc biệt khi dự án có nhiều remote.
- Kiểm tra `git remote -v` trước lần push đầu tiên và sau mỗi lần đổi URL.
- Dùng `git fetch` để cập nhật thông tin từ remote trước khi quyết định merge hoặc rebase.
- Phân biệt `origin/main` với `main`; một bên là remote-tracking reference, một bên là nhánh cục bộ.
- Chỉ xóa remote sau khi xác định nó không còn cần thiết và kiểm tra nhánh nào đang theo dõi nó.
- Không lưu token hoặc mật khẩu trong URL remote.
- Thống nhất với nhóm về remote chính, quyền push và cách cập nhật nhánh dùng chung.

## Ghi nhớ

`git remote` quản lý các kết nối mà kho cục bộ dùng để trao đổi dữ liệu với những kho Git khác. Dùng `git remote` để liệt kê, `git remote -v` để kiểm tra URL, `git remote add` để thêm, `git remote rename` để đổi tên, `git remote set-url` để đổi địa chỉ và `git remote remove` để xóa cấu hình. Hãy nhớ rằng remote là cấu hình trong kho cục bộ: xóa remote không xóa kho trên máy chủ, đổi URL không di chuyển dữ liệu, và commit chỉ được chia sẻ khi được push tới đúng remote.

