# Sao chép kho mã bằng git clone: URL, thư mục đích và nhánh ban đầu

Khi tham gia một dự án đã có repository trên GitHub, GitLab, máy chủ nội bộ hoặc một máy khác, bước đầu tiên thường là lấy một bản sao để làm việc. Lệnh <code>git clone</code> tạo repository local, tải dữ liệu Git từ nguồn, cấu hình remote mặc định và checkout nhánh ban đầu để bạn có thể bắt đầu đọc mã nguồn hoặc phát triển.

Để clone đúng, bạn cần hiểu ba lựa chọn: URL xác định nguồn repository, thư mục đích xác định nơi đặt bản sao trên máy, và nhánh ban đầu xác định phiên bản nào được checkout. Git thường tự chọn nhánh mặc định do remote công bố, nhưng bạn có thể chỉ định nhánh hoặc tag cụ thể khi cần.

Bài học thuộc chương **Khởi tạo kho mã** của module **SOURCE_CONTROL_GIT**. Module hướng dẫn Git từ working tree, staging area, commit và lịch sử đến branch, merge, rebase, remote và tag; đồng thời rèn cách cộng tác qua nhánh, giải quyết xung đột, truy tìm thay đổi và khôi phục thao tác sai mà vẫn bảo toàn lịch sử quan trọng. Nắm được cách clone giúp bạn bắt đầu làm việc với repository có sẵn và hiểu mối liên hệ giữa bản local với remote.

## 1. git clone thực hiện những việc gì?

Lệnh cơ bản:

~~~bash
git clone <repository-url> [<directory>]
~~~

Khi chạy lệnh, Git thường thực hiện các công việc:

1. Tạo thư mục đích và khởi tạo cấu trúc repository local.
2. Kết nối đến nguồn repository qua URL hoặc đường dẫn local.
3. Tải object và các refs cần thiết từ nguồn.
4. Tạo remote mặc định tên <code>origin</code> trỏ về nguồn clone.
5. Tạo các remote-tracking refs, ví dụ <code>origin/main</code>.
6. Tạo branch local cho nhánh mặc định và thiết lập upstream.
7. Checkout snapshot của nhánh ban đầu vào working tree, trừ khi bạn yêu cầu không checkout.

Sau khi clone thành công, bạn có một repository độc lập trên máy. Các commit mới bạn tạo ở local chưa tự động xuất hiện trên remote; bạn cần push khi muốn chia sẻ chúng.

## 2. Tìm URL repository cần clone

URL là địa chỉ mà Git dùng để lấy dữ liệu. Hãy sao chép URL từ trang repository hoặc lấy đường dẫn do người quản lý dự án cung cấp. Các hình thức thường gặp:

| Kiểu kết nối | Ví dụ | Đặc điểm |
|---|---|---|
| HTTPS | <code>https://github.com/acme/payment-service.git</code> | Dễ dùng qua mạng HTTPS; máy chủ có thể yêu cầu đăng nhập bằng token hoặc credential manager |
| SSH dạng scp-like | <code>git@github.com:acme/payment-service.git</code> | Dùng SSH key hoặc agent đã được cấp quyền |
| SSH dạng URL | <code>ssh://git@github.com/acme/payment-service.git</code> | Cùng cơ chế xác thực SSH, thể hiện rõ scheme và host |
| Đường dẫn local | <code>../payment-service.git</code> hoặc <code>/srv/git/payment-service.git</code> | Clone từ repository có sẵn trên máy hoặc filesystem được mount |

### HTTPS

Ví dụ:

~~~bash
git clone https://github.com/acme/payment-service.git
~~~

HTTPS phù hợp khi tổ chức dùng đăng nhập qua trình duyệt, personal access token hoặc Git Credential Manager. Nhiều nền tảng không còn chấp nhận mật khẩu tài khoản thông thường cho Git qua HTTPS; hãy dùng phương thức xác thực được nhà cung cấp hỗ trợ.

Không nhúng token hoặc mật khẩu trực tiếp vào URL, ví dụ dạng <code>https://user:token@host/...</code>. URL có thể xuất hiện trong shell history, log, cấu hình remote hoặc danh sách tiến trình. Hãy để credential manager hoặc cơ chế đăng nhập an toàn xử lý thông tin xác thực.

### SSH

Ví dụ:

~~~bash
git clone git@github.com:acme/payment-service.git
~~~

SSH yêu cầu máy của bạn có khóa phù hợp và public key đã được đăng ký ở tài khoản hoặc máy chủ có quyền đọc repository. Kiểm tra kết nối SSH theo hướng dẫn của nhà cung cấp trước khi clone nếu đây là lần đầu sử dụng.

SSH thuận tiện khi bạn thường xuyên fetch và push vì có thể dùng SSH agent hoặc cơ chế quản lý khóa của hệ điều hành. Private key cần được bảo vệ và không được đưa vào repository.

### Đường dẫn local

Nếu repository nguồn nằm trên cùng máy hoặc một filesystem đã mount:

~~~bash
git clone ../payment-service
~~~

Đường dẫn tương đối được tính từ thư mục hiện tại của terminal. Đường dẫn tuyệt đối cũng có thể được dùng. Git có thể tối ưu local clone bằng hardlink khi phù hợp; nếu muốn buộc sao chép object thay vì hardlink, có tùy chọn <code>--no-hardlinks</code>.

Không xóa hoặc di chuyển repository nguồn khi chưa hiểu cách bản clone được tạo và nơi object được lưu. Với thao tác clone thông thường, bản đích có object database riêng; tùy chọn như <code>--shared</code> là một trường hợp khác và có thể khiến bản clone phụ thuộc object database của nguồn.

## 3. Xác thực trước khi clone

Clone chỉ thành công nếu bạn có quyền đọc repository và phương thức xác thực hoạt động.

Với HTTPS, kiểm tra:

- URL đúng và repository tồn tại.
- Tài khoản có quyền đọc.
- Credential manager hoặc token có phạm vi quyền phù hợp.
- Token chưa hết hạn hoặc bị thu hồi.

Với SSH, kiểm tra:

- SSH client có sẵn.
- Public key đã được đăng ký đúng tài khoản hoặc máy chủ.
- Private key được nạp vào agent hoặc được SSH client tìm thấy.
- Host key của máy chủ được xác minh theo chính sách của tổ chức.

Nếu repository là private và Git báo không tìm thấy repository, nguyên nhân có thể là URL sai hoặc tài khoản không có quyền. Một số nhà cung cấp cố ý trả thông báo chung để không tiết lộ repository private có tồn tại hay không.

## 4. Chọn thư mục đích

Bạn có thể để Git tự đặt tên thư mục hoặc chỉ định tên mong muốn.

### Để Git tự tạo thư mục

~~~bash
git clone https://github.com/acme/payment-service.git
~~~

Git tạo thư mục dựa trên tên repository ở cuối nguồn. Với ví dụ trên, thư mục thường là <code>payment-service</code>; phần hậu tố <code>.git</code> ở cuối tên nguồn thường được loại bỏ.

### Chỉ định tên thư mục

~~~bash
git clone https://github.com/acme/payment-service.git payment-local
~~~

Git tạo repository tại thư mục <code>payment-local</code> tính từ thư mục hiện tại của terminal. Tên thư mục local không cần giống tên repository trên máy chủ.

Ví dụ trên Windows PowerShell:

~~~powershell
Set-Location C:\Projects
git clone https://github.com/acme/payment-service.git payment-local
~~~

Sau lệnh, repository nằm ở <code>C:\Projects\payment-local</code>.

### Clone vào thư mục hiện tại

~~~bash
mkdir payment-local
cd payment-local
git clone https://github.com/acme/payment-service.git .
~~~

Dấu chấm chỉ thư mục hiện tại. Thư mục đích phải rỗng để Git có thể đặt nội dung clone vào đó. Nếu thư mục đã chứa file hoặc thư mục con, Git thường từ chối clone nhằm tránh ghi đè dữ liệu hiện có.

### Quy tắc chọn thư mục đích

| Trạng thái thư mục đích | Kết quả thường gặp |
|---|---|
| Không truyền đối số directory | Git tự tạo thư mục theo tên nguồn |
| Truyền tên thư mục chưa tồn tại | Git tạo thư mục đó |
| Truyền thư mục đã tồn tại và rỗng | Git có thể clone vào thư mục đó |
| Truyền thư mục đã tồn tại và không rỗng | Git từ chối clone |
| Truyền dấu chấm vào thư mục hiện tại đang rỗng | Git clone vào thư mục hiện tại |

Trước khi clone vào một đường dẫn đã tồn tại, hãy kiểm tra nội dung trong đó. Không xóa thư mục chỉ để làm cho clone chạy được nếu chưa xác nhận dữ liệu bên trong không còn cần thiết.

## 5. Nhánh nào được checkout sau khi clone?

Khi bạn không chỉ định nhánh, Git thường checkout nhánh mặc định mà remote công bố qua symbolic reference <code>HEAD</code>. Nhánh mặc định thường có tên <code>main</code>, nhưng tên thực tế có thể là <code>master</code>, <code>develop</code> hoặc một tên khác do dự án cấu hình.

Ví dụ, remote công bố <code>refs/heads/main</code> là nhánh mặc định:

~~~bash
git clone https://github.com/acme/payment-service.git
cd payment-service
git branch --show-current
~~~

Lệnh cuối thường hiển thị <code>main</code>. Nếu remote đặt nhánh mặc định là <code>develop</code>, Git sẽ checkout <code>develop</code> thay vì tự đoán rằng mọi repository đều dùng <code>main</code>.

### Remote HEAD là gì?

Remote HEAD là thông tin symbolic HEAD do remote công bố, cho biết branch mặc định của repository. Trong bản clone, Git thường tạo symbolic ref:

~~~text
refs/remotes/origin/HEAD -> refs/remotes/origin/main
~~~

Đây là tham chiếu giúp Git và người dùng biết nhánh mặc định ở remote. Nó không phải branch local và cũng không phải một commit riêng.

Bạn có thể xem:

~~~bash
git remote show origin
git symbolic-ref refs/remotes/origin/HEAD
~~~

Nếu máy chủ không công bố HEAD hợp lệ hoặc HEAD trỏ đến branch không còn tồn tại, clone có thể tải object nhưng không tự checkout được branch. Khi đó hãy hỏi người quản lý repository nhánh mặc định đúng là gì hoặc chỉ định rõ branch bằng tùy chọn <code>--branch</code>.

## 6. Chọn nhánh ban đầu bằng --branch

Nếu muốn bắt đầu từ một nhánh cụ thể, dùng <code>-b</code> hoặc <code>--branch</code>:

~~~bash
git clone --branch develop https://github.com/acme/payment-service.git
~~~

Hoặc:

~~~bash
git clone -b develop https://github.com/acme/payment-service.git
~~~

Git lấy nhánh <code>develop</code> từ remote và checkout nó thành branch local. Branch local thường được cấu hình theo dõi remote-tracking branch tương ứng, ví dụ <code>origin/develop</code>.

Kiểm tra:

~~~bash
git branch --show-current
git branch -vv
git status -sb
~~~

Trong <code>git branch -vv</code>, bạn có thể thấy upstream của branch local. Upstream cho biết branch local đang theo dõi nhánh remote nào để hỗ trợ status, pull và push.

### --branch không tạo nhánh mới trên remote

Tùy chọn <code>--branch develop</code> chỉ chọn nhánh hoặc tag đã có ở nguồn để checkout. Nó không tạo một branch mới trên máy chủ và cũng không tự push thay đổi.

Nếu cần tạo nhánh làm việc mới sau khi clone:

~~~bash
git switch -c feature/payment-retry
~~~

Lệnh này tạo branch local mới từ commit hiện tại. Khi muốn chia sẻ branch, push với upstream:

~~~bash
git push -u origin feature/payment-retry
~~~

## 7. Clone một tag và trạng thái detached HEAD

Tùy chọn <code>--branch</code> cũng nhận tên tag. Ví dụ:

~~~bash
git clone --branch v2.4.0 https://github.com/acme/payment-service.git
~~~

Nếu <code>v2.4.0</code> là tag, Git checkout commit mà tag trỏ đến ở trạng thái detached HEAD. Khi đó HEAD không trỏ đến một branch local.

Kiểm tra:

~~~bash
git status -sb
git branch --show-current
git describe --tags --exact-match
~~~

<code>git branch --show-current</code> có thể không in tên branch vì đang detached. Điều này phù hợp khi bạn chỉ cần đọc mã nguồn, chạy test hoặc kiểm tra đúng phiên bản release.

Nếu muốn phát triển từ tag, tạo branch mới:

~~~bash
git switch -c hotfix/v2.4.0
~~~

Branch mới bắt đầu tại commit của tag. Commit tiếp theo sẽ được ghi vào branch đó và không làm thay đổi tag đã phát hành.

## 8. Chỉ tải một nhánh bằng --single-branch

Repository có thể có nhiều nhánh remote. Nếu chỉ cần một nhánh, bạn có thể dùng:

~~~bash
git clone --single-branch --branch release/2.x https://github.com/acme/payment-service.git
~~~

Git chỉ lấy lịch sử liên quan đến nhánh được chọn thay vì tải lịch sử các nhánh khác theo cách clone thông thường. Điều này có thể giảm lượng dữ liệu cần tải trong repository có nhiều nhánh dài hoặc nhiều lịch sử.

Nếu dùng:

~~~bash
git clone --single-branch https://github.com/acme/payment-service.git
~~~

Git chỉ lấy nhánh mặc định mà remote công bố.

Khi clone theo kiểu này, remote-tracking refs của các nhánh khác có thể không xuất hiện. Nếu sau đó cần một nhánh khác, bạn có thể fetch rõ nhánh đó:

~~~bash
git fetch origin feature/payment
git switch -c feature/payment FETCH_HEAD
~~~

Lệnh fetch với tên nhánh nguồn đơn lẻ thường ghi commit vừa lấy vào <code>FETCH_HEAD</code>; nó không nhất thiết tạo remote-tracking ref <code>origin/feature/payment</code>. Nếu muốn tạo remote-tracking ref để theo dõi lâu dài, dùng refspec rõ ràng:

~~~bash
git fetch origin refs/heads/feature/payment:refs/remotes/origin/feature/payment
git switch -c feature/payment --track origin/feature/payment
~~~

Không nên nhầm việc chưa thấy branch trong danh sách local với việc branch đó không tồn tại trên remote.

## 9. Clone nông bằng --depth

Với repository có lịch sử rất dài, có thể chỉ tải một số commit gần đầu nhánh:

~~~bash
git clone --depth 1 https://github.com/acme/payment-service.git
~~~

<code>--depth 1</code> tạo shallow clone với lịch sử bị giới hạn ở một tầng commit gần tip của nhánh được lấy. Điều này hữu ích cho CI job chỉ cần source code hiện tại hoặc môi trường thử nghiệm không cần lịch sử sâu.

Khi dùng <code>--depth</code>, Git mặc định hàm ý <code>--single-branch</code>, trừ khi bạn yêu cầu khác bằng <code>--no-single-branch</code>. Vì thế, clone nông thường chỉ có lịch sử của một nhánh.

### Giới hạn của shallow clone

- Một số commit cha không có trong bản clone.
- Lệnh cần lịch sử sâu như một số thao tác merge, bisect hoặc phân tích lịch sử có thể bị giới hạn.
- Không thể xem toàn bộ lịch sử cũ chưa được tải.
- Một số thao tác chia sẻ hoặc tích hợp nhánh cần tải thêm lịch sử trước khi thực hiện.

Khi cần mở rộng lịch sử:

~~~bash
git fetch --deepen 50
~~~

Lệnh này tải thêm 50 tầng commit so với ranh giới shallow hiện tại. Nếu muốn chuyển thành clone đầy đủ lịch sử:

~~~bash
git fetch --unshallow
~~~

Chỉ dùng shallow clone khi bạn hiểu công việc cần làm không phụ thuộc lịch sử đầy đủ. Với môi trường phát triển lâu dài, clone thông thường thường đơn giản hơn.

## 10. Clone nhưng chưa checkout working tree

Tùy chọn <code>--no-checkout</code> (hoặc <code>-n</code>) yêu cầu Git tải repository nhưng không checkout file vào working tree ngay:

~~~bash
git clone --no-checkout https://github.com/acme/payment-service.git payment-inspect
~~~

Chế độ này có thể hữu ích khi bạn muốn kiểm tra refs, cấu hình hoặc chuẩn bị index trước khi chọn nội dung cần checkout. Sau đó có thể checkout branch mong muốn:

~~~bash
cd payment-inspect
git reset --hard HEAD
~~~

Trong clone có <code>--no-checkout</code>, HEAD thường đã được thiết lập theo branch ban đầu nhưng working tree và index chưa được populate. Lệnh reset trên cập nhật index và working tree theo snapshot mà HEAD đang trỏ tới. Chỉ chạy trong clone mới chưa có thay đổi local cần giữ, vì <code>--hard</code> ghi lại trạng thái index và working tree.

## 11. Clone bare và mirror: trường hợp không có working tree

Clone thông thường tạo working tree để bạn sửa file. Trong một số tình huống quản trị, bạn chỉ muốn một repository Git không checkout file:

~~~bash
git clone --bare https://github.com/acme/payment-service.git payment-service.git
~~~

Bare repository không có working tree thông thường. Nó thường được dùng làm repository trung tâm trên máy chủ hoặc nơi lưu trữ dữ liệu Git.

Mirror clone:

~~~bash
git clone --mirror https://github.com/acme/payment-service.git payment-mirror.git
~~~

Mirror clone là dạng bare clone được cấu hình để phản chiếu refs từ nguồn rộng hơn clone thông thường. Nó phù hợp cho mục đích mirror hoặc sao lưu refs, không phải thư mục phát triển hằng ngày.

Hãy cẩn thận khi dùng mirror push: thao tác mirror có thể cập nhật hoặc xóa refs đích để khớp với nguồn. Đừng dùng clone mirror như một working copy thông thường.

## 12. Kiểm tra repository sau khi clone

Sau khi clone, chuyển vào thư mục:

~~~bash
cd payment-service
~~~

Chạy các lệnh:

~~~bash
# Kiểm tra remote
git remote -v

# Kiểm tra branch local và upstream
git branch -vv

# Kiểm tra cả branch local và remote-tracking
git branch -a

# Kiểm tra trạng thái working tree
git status

# Xem commit hiện tại
git log -1 --oneline --decorate
~~~

Thông thường bạn sẽ thấy:

- Remote tên <code>origin</code> có URL fetch và push.
- Branch local đang checkout, chẳng hạn <code>main</code>.
- Upstream tương ứng, chẳng hạn <code>origin/main</code>.
- Working tree sạch nếu không có thay đổi sau clone.

Để xem thông tin chi tiết về remote:

~~~bash
git remote show origin
~~~

Lệnh này có thể hiển thị URL, nhánh HEAD, các nhánh remote được theo dõi và trạng thái local so với remote.

## 13. Đổi tên remote mặc định hoặc chọn tên khác ngay khi clone

Mặc định Git đặt tên remote là <code>origin</code>. Nếu muốn tên khác ngay từ đầu, dùng:

~~~bash
git clone --origin upstream https://github.com/acme/payment-service.git
~~~

Hoặc dạng ngắn:

~~~bash
git clone -o upstream https://github.com/acme/payment-service.git
~~~

Điều này hữu ích khi clone một fork nhưng muốn remote gốc có tên <code>upstream</code>, hoặc khi nhóm có quy ước đặt tên remote riêng.

Nếu đã clone và muốn đổi tên:

~~~bash
git remote rename origin upstream
~~~

Tên remote là alias local. Đổi tên không đổi URL của repository trên máy chủ.

## 14. Khi nhánh mặc định của remote thay đổi

Giả sử repository trước đây dùng <code>master</code> nhưng sau đó chuyển sang <code>main</code>. Remote có thể đã cập nhật symbolic HEAD, nhưng bản clone cũ vẫn giữ thông tin remote HEAD cũ cho đến khi được làm mới.

Kiểm tra:

~~~bash
git remote show origin
git symbolic-ref refs/remotes/origin/HEAD
~~~

Để yêu cầu Git dò lại nhánh HEAD trên remote:

~~~bash
git remote set-head origin --auto
~~~

Lệnh này cập nhật symbolic ref <code>refs/remotes/origin/HEAD</code> dựa trên thông tin remote. Nó không tự đổi branch local hiện tại của bạn. Nếu muốn chuyển sang nhánh mặc định mới, hãy kiểm tra trạng thái working tree rồi switch rõ ràng:

~~~bash
git fetch origin
git switch main
~~~

Nếu branch local <code>main</code> chưa có, tạo branch tracking:

~~~bash
git switch --track origin/main
~~~

## 15. Clone khác gì với git init và git remote add?

Hai cách này có mục tiêu khác nhau:

| Cách làm | Kết quả |
|---|---|
| <code>git clone &lt;url&gt;</code> | Lấy repository đã tồn tại, tải object và refs, cấu hình remote, tạo branch ban đầu và checkout |
| <code>git init</code> | Khởi tạo repository local mới, ban đầu chưa có lịch sử từ remote |
| <code>git init</code> + <code>git remote add</code> + <code>git fetch</code> | Tự tạo repository local rồi kết nối và lấy dữ liệu từ remote theo các bước riêng |

Nếu mục tiêu là tham gia một repository có sẵn, <code>git clone</code> thường là lựa chọn đúng. Nếu bạn đang bắt đầu một dự án mới trên máy và muốn sau đó publish lên máy chủ, thường bắt đầu bằng <code>git init</code> rồi cấu hình remote khi cần.

## 16. Lỗi thường gặp khi clone

| Thông báo hoặc hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Repository not found | URL sai hoặc tài khoản không có quyền đọc | Xác nhận URL và quyền truy cập với người quản lý |
| Authentication failed | Token hết hạn, credential sai hoặc phương thức xác thực không được hỗ trợ | Làm mới credential qua credential manager hoặc dùng phương thức được nền tảng hỗ trợ |
| Permission denied (publickey) | SSH key chưa được đăng ký, chưa nạp hoặc sai tài khoản | Kiểm tra SSH agent, public key và quyền repository |
| Host key verification failed | Host key không khớp hoặc chưa được xác minh | Kiểm tra fingerprint máy chủ qua kênh tin cậy rồi cập nhật known_hosts theo hướng dẫn |
| Destination path already exists and is not an empty directory | Thư mục đích đã chứa dữ liệu | Chọn đường dẫn khác hoặc kiểm tra, di chuyển dữ liệu hiện có trước |
| Remote HEAD refers to nonexistent ref | Nhánh mặc định remote không hợp lệ hoặc chưa được cấu hình | Hỏi người quản lý nhánh mặc định hoặc clone với <code>--branch</code> rõ ràng |
| Clone rất chậm | Repository hoặc lịch sử lớn, mạng chậm, máy chủ hạn chế | Kiểm tra mạng; cân nhắc shallow/single-branch nếu công việc cho phép |
| Clone thành công nhưng thiếu branch mong muốn | Dùng <code>--single-branch</code> hoặc refspec giới hạn | Fetch branch cụ thể hoặc điều chỉnh refspec |
| Working tree không có file sau clone | Có thể dùng <code>--no-checkout</code> hoặc clone bare | Kiểm tra tùy chọn clone và checkout branch nếu là repository thường |

Khi báo lỗi cho quản trị viên, hãy gửi thông báo, URL đã che thông tin nhạy cảm, phương thức kết nối và thời điểm xảy ra. Không gửi token, mật khẩu hoặc private key.

## 17. Quy trình clone gợi ý cho người mới

Một quy trình đơn giản có thể áp dụng:

1. Mở trang repository và sao chép URL HTTPS hoặc SSH do nhóm khuyến nghị.
2. Xác nhận tài khoản hoặc SSH key có quyền đọc.
3. Chọn thư mục cha để lưu dự án.
4. Chạy <code>git clone</code>, chỉ định thư mục đích nếu muốn tên khác.
5. Nếu dự án yêu cầu nhánh cụ thể, dùng <code>--branch</code>; chỉ dùng <code>--single-branch</code> hoặc <code>--depth</code> khi hiểu giới hạn.
6. Đi vào thư mục mới.
7. Kiểm tra remote, branch, upstream và working tree.
8. Tạo branch làm việc riêng trước khi phát triển tính năng.

Ví dụ:

~~~bash
git clone --branch main https://github.com/acme/payment-service.git payment-service
cd payment-service
git remote -v
git branch -vv
git status
git switch -c feature/payment-retry
~~~

## 18. Bài tập tự kiểm tra

Thực hành với một repository công khai hoặc repository thử nghiệm do bạn quản lý:

1. Clone bằng HTTPS và để Git tự đặt tên thư mục.
2. Clone cùng repository vào một thư mục có tên khác.
3. Thử clone vào thư mục đã có file và quan sát vì sao Git từ chối.
4. Dùng <code>git branch --show-current</code> để xác định nhánh mặc định được checkout.
5. Clone lại bằng <code>--branch</code> để chọn một branch cụ thể.
6. Clone một tag và xác nhận trạng thái detached HEAD; sau đó tạo branch mới từ tag.
7. Dùng <code>--single-branch</code> và so sánh danh sách remote-tracking refs với clone thông thường.
8. Dùng <code>--depth 1</code>, xem giới hạn lịch sử rồi thử <code>git fetch --unshallow</code>.
9. Dùng <code>--origin upstream</code> và kiểm tra tên remote bằng <code>git remote -v</code>.
10. Giải thích vai trò của remote HEAD, branch local và remote-tracking branch.

Khi clone, hãy kiểm tra kỹ URL, nơi lưu bản sao và nhánh được checkout. Sau khi clone thành công, xác nhận remote cùng upstream để biết bản local lấy dữ liệu từ đâu và sẽ đồng bộ với nhánh nào.
