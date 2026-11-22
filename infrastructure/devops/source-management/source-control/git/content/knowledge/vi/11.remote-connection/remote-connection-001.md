# Remote là gì và vì sao origin chỉ là tên theo quy ước

Khi làm việc với Git trên một máy, các commit và nhánh được lưu trong repository cục bộ. Khi cần chia sẻ lịch sử với đồng đội, đồng bộ giữa nhiều máy hoặc nhận thay đổi từ một dự án khác, ta cần kết nối repository đó với một repository khác. Git gọi địa chỉ repository bên ngoài này là **remote**.

Một remote có hai phần dễ nhận ra: một **tên ngắn** để dùng trong lệnh Git và một **URL hoặc đường dẫn** cho biết repository nằm ở đâu. Tên `origin` thường xuất hiện ngay sau khi clone dự án, nhưng nó chỉ là tên mặc định theo quy ước. Hiểu rõ điều này giúp ta làm việc với fork, repository gốc và nhiều máy chủ mà không nhầm tên remote với địa chỉ thật.

## 1. Remote trong Git là gì?

Remote là một tên đại diện cho một repository Git khác mà repository hiện tại có thể trao đổi dữ liệu. Repository đó thường nằm trên dịch vụ như GitHub, GitLab hoặc Bitbucket, nhưng cũng có thể là một máy chủ Git tự quản lý, một thư mục trên cùng máy hoặc một đường dẫn mạng.

Ví dụ, nhóm đang lưu dự án tại:

~~~text
https://github.com/acme/store-api.git
~~~

Trong repository cục bộ, ta có thể đặt tên ngắn cho địa chỉ này là `origin`. Sau đó, thay vì phải gõ URL dài trong từng lệnh, ta dùng tên remote:

~~~bash
git fetch origin
git push origin main
~~~

Remote không phải là một bản sao thư mục đang tự động cập nhật. Git lưu cấu hình remote trong repository cục bộ, gồm tên, địa chỉ và quy tắc lấy các nhánh từ remote. Khi chạy `fetch`, `pull` hoặc `push`, Git mới thực hiện việc trao đổi dữ liệu theo yêu cầu.

Cũng cần nhớ rằng Git là hệ thống quản lý phiên bản phân tán. Repository cục bộ vẫn có lịch sử commit riêng và có thể tạo commit ngay cả khi mất kết nối mạng. Remote là nơi để trao đổi lịch sử đó với repository khác; nó không làm cho repository cục bộ phụ thuộc vào kết nối liên tục tới máy chủ.

## 2. Vì sao tên mặc định thường là origin?

Khi clone một repository bằng lệnh:

~~~bash
git clone https://github.com/acme/store-api.git
~~~

Git tạo repository cục bộ, tải dữ liệu cần thiết và tự thêm remote trỏ về địa chỉ đã clone. Tên mặc định của remote này là `origin`.

Có thể kiểm tra bằng:

~~~bash
cd store-api
git remote -v
~~~

Kết quả minh họa:

~~~text
origin  https://github.com/acme/store-api.git (fetch)
origin  https://github.com/acme/store-api.git (push)
~~~

Tên `origin` có nghĩa là nguồn repository ban đầu mà ta clone từ đó. Đây là quy ước phổ biến của Git, không phải từ khóa bắt buộc hay tên máy chủ đặc biệt. Git không yêu cầu mọi repository phải có remote tên `origin`, và cũng không tự hiểu `origin` luôn là repository chính thức của dự án.

Ta có thể đặt tên khác:

~~~bash
git clone --origin company https://github.com/acme/store-api.git
~~~

Trong ví dụ này, remote được tạo với tên `company`. Với một repository đã tồn tại, ta cũng có thể thêm remote mang tên tùy chọn:

~~~bash
git remote add team https://git.example.com/platform/store-api.git
~~~

Tên remote là bí danh do người dùng đặt. Điều quan trọng là tên đó phải giúp mọi người hiểu repository nào đang được tham chiếu.

## 3. Phân biệt remote, remote-tracking branch và upstream branch

Ba khái niệm sau thường xuất hiện cùng nhau nhưng có ý nghĩa khác nhau:

| Khái niệm | Ví dụ | Ý nghĩa |
|---|---|---|
| Remote | `origin` | Tên bí danh trỏ tới một repository khác |
| Remote-tracking branch | `origin/main` | Mốc tham chiếu cục bộ ghi nhận trạng thái nhánh `main` trên remote ở lần Git cập nhật gần nhất |
| Upstream branch của nhánh local | Nhánh `main` theo dõi `origin/main` | Quan hệ cấu hình để Git biết nhánh local thường lấy thay đổi từ đâu và đẩy thay đổi tới đâu |

### Remote-tracking branch là gì?

Sau khi chạy `git fetch origin`, Git cập nhật các remote-tracking branch, ví dụ `origin/main` hoặc `origin/feature/login`. Các tham chiếu này nằm trong repository cục bộ và phản ánh trạng thái remote tại lần fetch gần nhất.

Vì vậy, `origin/main` không phải là một nhánh local mà ta đang trực tiếp chỉnh sửa trên máy chủ. Nó là mốc tham chiếu để so sánh hoặc tích hợp thay đổi từ remote. Muốn xem các remote-tracking branch, dùng:

~~~bash
git branch -r
~~~

Muốn xem cả nhánh local lẫn remote-tracking branch:

~~~bash
git branch -a
~~~

### Upstream branch có phải remote tên upstream không?

Không. Trong ngữ cảnh theo dõi nhánh, upstream là nhánh mà một nhánh local được cấu hình để theo dõi. Ví dụ, nhánh local `main` có thể theo dõi `origin/main`. Ta thường thiết lập quan hệ này khi push lần đầu bằng `-u`.

Ngoài ra, nhiều nhóm đặt tên một remote là `upstream` để chỉ repository gốc mà fork được tạo ra. Đây lại là tên remote theo quy ước. Hai cách dùng từ “upstream” có liên quan về ý nghĩa nguồn thay đổi, nhưng không phải cùng một cấu hình.

## 4. Xem các remote đang được cấu hình

Các lệnh thường dùng:

~~~bash
# Liệt kê tên remote
git remote

# Hiển thị URL dùng để fetch và push
git remote -v

# Xem URL của một remote cụ thể
git remote get-url origin

# Xem thông tin chi tiết về remote
git remote show origin
~~~

`git remote -v` đọc cấu hình cục bộ nên thường không cần kết nối mạng. `git remote show origin` có thể liên hệ với máy chủ để lấy thêm thông tin về các nhánh và trạng thái remote.

Thông tin cấu hình remote thường được lưu trong file `.git/config` của repository. Một cấu hình đơn giản có thể trông như sau:

~~~ini
[remote "origin"]
    url = https://github.com/acme/store-api.git
    fetch = +refs/heads/*:refs/remotes/origin/*
~~~

Dòng `url` xác định địa chỉ repository. Dòng `fetch` cho biết Git ánh xạ các nhánh từ remote thành các remote-tracking branch cục bộ dưới tên `origin/*`. Thông thường, nên quản lý cấu hình bằng các lệnh `git remote` thay vì sửa trực tiếp file này.

## 5. Thêm remote cho repository hiện có

Nếu đã tạo repository bằng `git init` hoặc đang làm việc trong một repository chưa có remote, có thể thêm remote bằng:

~~~bash
git remote add origin https://github.com/acme/store-api.git
git remote -v
~~~

Lệnh `git remote add` chỉ lưu cấu hình kết nối. Nó không tự đẩy commit lên máy chủ. Sau khi đã có ít nhất một commit và xác định đúng tên nhánh local, ta có thể đẩy nhánh đó:

~~~bash
git branch --show-current
git push -u origin main
~~~

Ví dụ trên giả định nhánh hiện tại tên là `main`. Nếu nhánh hiện tại có tên khác, hãy dùng đúng tên nhánh đó. Tùy chọn `-u` (hay `--set-upstream`) thiết lập quan hệ theo dõi giữa nhánh local và nhánh remote vừa push. Những lần sau, khi đang ở nhánh đó, ta thường chỉ cần chạy `git push` hoặc `git pull`.

Nếu repository được tạo bằng `git clone`, remote mặc định thường đã tồn tại. Hãy kiểm tra `git remote -v` trước khi thêm để tránh lỗi remote trùng tên.

## 6. Trao đổi dữ liệu: fetch, pull và push

Ba lệnh này đều liên quan tới remote nhưng thực hiện những việc khác nhau.

### Fetch: lấy thông tin và commit từ remote

~~~bash
git fetch origin
~~~

Git kết nối tới remote `origin`, tải các đối tượng Git còn thiếu và cập nhật remote-tracking branch như `origin/main`. Lệnh này không tự thay đổi nhánh local hiện tại hoặc nội dung working tree. Vì vậy, fetch là cách an toàn để cập nhật hiểu biết về remote trước khi quyết định tích hợp thay đổi.

Có thể lấy dữ liệu từ tất cả remote đã cấu hình và dọn các remote-tracking branch không còn tồn tại trên remote:

~~~bash
git fetch --all --prune
~~~

Tùy chọn `--prune` dọn các tham chiếu theo dõi đã lỗi thời trong repository cục bộ. Nó không xóa nhánh local và cũng không xóa nhánh trên máy chủ.

Sau khi fetch, có thể so sánh nhánh local với mốc remote:

~~~bash
git log --oneline --graph --decorate --all
git diff main..origin/main
~~~

### Pull: lấy dữ liệu rồi tích hợp vào nhánh hiện tại

~~~bash
git pull
~~~

Về cơ bản, `git pull` thực hiện fetch rồi tích hợp thay đổi từ nhánh upstream của nhánh hiện tại. Cách tích hợp phụ thuộc cấu hình và tùy chọn được dùng: mặc định thường là merge, còn có thể yêu cầu rebase bằng `git pull --rebase`.

Nếu muốn chỉ cập nhật khi có thể fast-forward, có thể dùng:

~~~bash
git pull --ff-only
~~~

Lệnh này sẽ dừng nếu hai nhánh đã phân kỳ và cần tạo merge commit hoặc rebase. Khi gặp tình huống đó, hãy xem trạng thái và lịch sử trước khi chọn cách tích hợp phù hợp với quy ước của nhóm.

### Push: gửi commit lên remote

~~~bash
git push origin main
~~~

Lệnh này gửi các commit cần thiết từ nhánh local `main` lên nhánh `main` của remote `origin`, nếu thao tác được máy chủ chấp nhận.

Khi tạo nhánh tính năng mới, thường dùng:

~~~bash
git switch -c feature/login
# chỉnh sửa và commit thay đổi
git push -u origin feature/login
~~~

Sau lần push đầu tiên, nhánh local `feature/login` đã theo dõi nhánh remote tương ứng. Git có thể suy ra đích push trong những lần tiếp theo.

Push có thể bị từ chối nếu remote đã có commit mà local chưa tích hợp. Khi đó, hãy fetch, xem phần lịch sử khác nhau và tích hợp thay đổi theo quy trình của nhóm. Không nên vội dùng `--force`, vì thao tác đó có thể ghi đè lịch sử mà người khác đã đẩy lên.

## 7. Làm việc với nhiều remote: ví dụ fork và repository gốc

Một tình huống phổ biến là đóng góp cho dự án mà ta không có quyền push trực tiếp. Ta fork dự án về tài khoản của mình, clone fork đó về máy và thêm repository gốc làm remote thứ hai.

Giả sử:

- `origin` trỏ tới fork của bạn.
- `upstream` trỏ tới repository gốc của nhóm hoặc dự án.

Có thể cấu hình như sau:

~~~bash
git remote add upstream https://github.com/original-owner/store-api.git
git remote -v
~~~

Khi cần lấy thay đổi mới từ repository gốc:

~~~bash
git fetch upstream
~~~

Sau đó, tích hợp nhánh chính của repository gốc vào nhánh local theo quy trình của dự án, ví dụ:

~~~bash
git switch main
git merge upstream/main
~~~

Khi phát triển tính năng, bạn có thể đẩy nhánh lên fork:

~~~bash
git switch -c feature/login
git push -u origin feature/login
~~~

Từ fork đó, bạn tạo Pull Request hoặc Merge Request về repository gốc. Trong mô hình này, `origin` và `upstream` chỉ là hai bí danh giúp phân biệt hai địa chỉ. Một dự án có thể dùng các tên khác nếu nhóm thống nhất cách đặt tên.

## 8. Đổi URL, đổi tên hoặc xóa remote

Khi repository được chuyển máy chủ hoặc đổi địa chỉ, cập nhật URL bằng:

~~~bash
git remote set-url origin https://git.example.com/platform/store-api.git
~~~

Nếu muốn đổi tên remote:

~~~bash
git remote rename team company
~~~

Nếu không còn cần một remote trong repository cục bộ:

~~~bash
git remote remove company
~~~

Các lệnh này thay đổi cấu hình remote của repository hiện tại. `git remote remove` không xóa repository ở địa chỉ bên ngoài; nó xóa cấu hình remote và các remote-tracking branch tương ứng trong repository cục bộ.

Sau khi thay đổi, nên kiểm tra lại:

~~~bash
git remote -v
~~~

## 9. Một số lỗi thường gặp

| Thông báo hoặc tình huống | Nguyên nhân thường gặp | Cách kiểm tra và xử lý |
|---|---|---|
| `fatal: 'origin' does not appear to be a git repository` | Chưa có remote tên `origin`, hoặc URL của remote sai | Chạy `git remote -v`; thêm remote hoặc sửa URL nếu cần |
| `Authentication failed` hoặc lỗi quyền truy cập | Tài khoản, token, SSH key hoặc quyền trên repository chưa phù hợp | Kiểm tra URL HTTPS/SSH, thông tin xác thực và quyền truy cập |
| `[rejected] ... non-fast-forward` | Remote có commit mà nhánh local chưa tích hợp | Fetch, xem lịch sử, tích hợp thay đổi rồi push lại |
| `src refspec main does not match any` | Không có nhánh local tên `main`, hoặc repository chưa có commit | Kiểm tra `git branch --show-current` và `git log`; tạo commit đầu tiên nếu repository chưa có commit |
| `There is no tracking information for the current branch` | Nhánh local chưa cấu hình upstream branch | Push lần đầu với `git push -u origin <ten-nhanh>` hoặc cấu hình, ví dụ `git branch --set-upstream-to=origin/main main` |

Khi lỗi liên quan tới remote, hãy kiểm tra lần lượt tên remote, URL, nhánh đích và quyền truy cập. Không nên thay đổi URL hoặc xóa cấu hình khi chưa biết remote đó đang được dùng cho mục đích nào.

## 10. Quy trình mẫu khi làm việc với remote

Một quy trình cơ bản cho thành viên nhóm có thể gồm:

1. Clone repository nếu chưa có bản local: `git clone <URL>`.
2. Xem remote hiện tại: `git remote -v`.
3. Cập nhật thông tin trước khi bắt đầu: `git fetch origin`.
4. Chuyển sang nhánh làm việc hoặc tạo nhánh mới: `git switch -c feature/<ten-tinh-nang>`.
5. Sửa file, kiểm tra thay đổi bằng `git status` và `git diff`, sau đó tạo commit.
6. Đẩy nhánh lần đầu bằng `git push -u origin feature/<ten-tinh-nang>`.
7. Mở Pull Request hoặc Merge Request theo quy trình của nhóm.
8. Khi nhánh chính đã có thay đổi mới, fetch và tích hợp theo chiến lược mà nhóm đang sử dụng.

Tên nhánh, cách merge hoặc rebase và quy tắc bảo vệ nhánh có thể khác nhau giữa các dự án. Hãy tuân theo quy ước của repository đang tham gia.

## 11. Những điểm cần ghi nhớ

- **Remote** là bí danh trỏ tới một repository Git khác; nó có thể trỏ tới máy chủ hoặc đường dẫn repository khác.
- **`origin`** thường được Git tạo khi clone, nhưng chỉ là tên mặc định theo quy ước. Ta có thể đổi tên hoặc dùng nhiều remote.
- **`origin/main`** là remote-tracking branch cục bộ, ghi nhận trạng thái nhánh `main` trên remote ở lần cập nhật gần nhất.
- **Upstream branch** là quan hệ theo dõi giữa nhánh local và một nhánh khác; đừng nhầm nó với remote có tên `upstream`.
- **`fetch`** cập nhật dữ liệu và remote-tracking branch; **`pull`** còn tích hợp thay đổi vào nhánh hiện tại; **`push`** gửi commit lên remote.
- Thêm remote chỉ tạo cấu hình kết nối. Việc trao đổi dữ liệu diễn ra khi chạy các lệnh tương ứng.

Khi đọc một lệnh như `git push origin main`, hãy tách nó thành ba phần: hành động `push`, remote đích `origin` và nhánh đích `main`. Cách đọc này giúp hiểu rõ Git đang gửi dữ liệu đi đâu và giảm nhầm lẫn khi repository có nhiều remote.

