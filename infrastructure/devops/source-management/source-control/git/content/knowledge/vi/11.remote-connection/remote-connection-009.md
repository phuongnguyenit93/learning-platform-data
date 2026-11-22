# Thay đổi địa chỉ remote khi di chuyển kho mã

Khi một repository được chuyển sang máy chủ khác, đổi tên trên nền tảng lưu trữ hoặc chuyển từ HTTPS sang SSH, bản sao Git trên máy phát triển vẫn giữ địa chỉ remote cũ. Nếu tiếp tục dùng địa chỉ đó, các thao tác fetch, pull hoặc push có thể thất bại, hoặc vô tình kết nối đến kho mã cũ. Bạn có thể cập nhật địa chỉ remote ngay trong repository hiện tại mà vẫn giữ working tree, commit, branch và lịch sử local.

Bài này thuộc chương **Kết nối remote** của module **SOURCE_CONTROL_GIT**. Module hướng dẫn Git từ working tree, staging area, commit và lịch sử đến branch, merge, rebase, remote và tag; đồng thời rèn cách cộng tác qua nhánh, giải quyết xung đột, truy tìm thay đổi và khôi phục thao tác sai mà vẫn bảo toàn lịch sử quan trọng. Việc quản lý đúng địa chỉ remote giúp các thao tác cộng tác tiếp tục trỏ đến repository mà nhóm đang sử dụng.

## 1. Remote là gì và địa chỉ remote nằm ở đâu?

Remote là tên viết tắt mà Git dùng để tham chiếu đến một repository khác. Khi clone một repository, Git thường tạo remote tên <code>origin</code> trỏ đến địa chỉ nguồn đã clone. Tên <code>origin</code> là quy ước phổ biến, không phải tên bắt buộc hay từ khóa đặc biệt. Một dự án có thể có nhiều remote, chẳng hạn <code>origin</code> trỏ đến repository chính của nhóm và <code>upstream</code> trỏ đến repository gốc mà dự án đang fork.

Địa chỉ remote có thể dùng nhiều giao thức:

~~~text
# HTTPS
https://github.com/acme/payment-service.git

# SSH dạng scp-like
git@github.com:acme/payment-service.git

# SSH dạng URL đầy đủ
ssh://git@git.example.com:2222/platform/payment-service.git
~~~

Git lưu cấu hình remote trong file cấu hình local của repository, thường là <code>.git/config</code>. Vì vậy, thay đổi URL remote bằng lệnh Git chỉ cập nhật cấu hình của bản sao local đang thao tác. Mỗi thành viên trong nhóm có bản clone riêng và cần cập nhật URL trong bản clone của họ khi địa chỉ chính thức thay đổi.

Remote thường có hai loại địa chỉ cần chú ý:

- **Fetch URL:** địa chỉ Git dùng để lấy dữ liệu từ remote khi fetch hoặc pull.
- **Push URL:** địa chỉ Git dùng khi đẩy commit lên remote. Nếu chưa cấu hình riêng, push URL thường dùng cùng địa chỉ với fetch URL.

Một remote có thể hiển thị hai URL khác nhau. Vì vậy, chỉ kiểm tra một dòng địa chỉ là chưa đủ nếu nhóm đang cấu hình riêng nơi lấy và nơi đẩy dữ liệu.

## 2. Khi nào cần thay đổi URL?

Các tình huống thường gặp:

| Tình huống | Ví dụ thay đổi |
|---|---|
| Repository được chuyển sang tổ chức hoặc nhóm mới | <code>acme/app.git</code> chuyển thành <code>platform/app.git</code> |
| Repository được đổi tên | <code>old-service.git</code> chuyển thành <code>service-api.git</code> |
| Nhóm chuyển nhà cung cấp Git | GitHub chuyển sang GitLab hoặc máy chủ Git nội bộ |
| Máy chủ thay đổi tên miền hoặc cổng SSH | <code>git.old.example.com</code> chuyển thành <code>git.example.com:2222</code> |
| Thay đổi phương thức xác thực | HTTPS chuyển sang SSH hoặc ngược lại |

Hãy xác định đúng repository đích trước khi sửa cấu hình. Một địa chỉ mới có thể trông gần giống địa chỉ cũ nhưng thuộc repository khác, chẳng hạn repository cá nhân thay cho repository của tổ chức. Nếu kho được sao chép sang máy chủ mới, cần xác nhận kho đích đã nhận đủ commit, branch, tag và các dữ liệu bổ sung mà dự án sử dụng.

**Thay URL chỉ đổi nơi Git kết nối.** Lệnh này không tự di chuyển dữ liệu, không sao chép commit lên máy chủ mới, không thay đổi nội dung working tree và cũng không xóa repository cũ.

## 3. Kiểm tra cấu hình hiện tại trước khi sửa

Trước khi cập nhật, hãy xác định remote name và cả fetch/push URL:

~~~bash
# Liệt kê remote cùng fetch URL và push URL
git remote -v

# Liệt kê tên remote
git remote

# Xem fetch URL của origin
git remote get-url origin

# Xem push URL của origin
git remote get-url --push origin

# Xem tất cả URL nếu remote có cấu hình nhiều URL
git remote get-url --all origin
git remote get-url --push --all origin
~~~

Ví dụ kết quả:

~~~text
origin  https://github.com/acme/payment-service.git (fetch)
origin  https://github.com/acme/payment-service.git (push)
upstream https://github.com/example/payment-service.git (fetch)
upstream https://github.com/example/payment-service.git (push)
~~~

Kết quả cho biết repository hiện có hai remote. Nếu nhóm chỉ chuyển repository của tổ chức, bạn có thể chỉ cần cập nhật <code>origin</code>; <code>upstream</code> có thể vẫn trỏ đến repository gốc. Không thay tất cả URL một cách máy móc.

Nên kiểm tra thêm nhánh hiện tại và liên kết theo dõi:

~~~bash
git status
git branch -vv
git branch --show-current
~~~

<code>git branch -vv</code> hiển thị nhánh local và remote-tracking branch mà nhánh đó đang theo dõi, ví dụ <code>main</code> theo dõi <code>origin/main</code>. Thông tin này hữu ích để xác nhận các liên kết upstream vẫn đúng sau khi thay URL.

Nếu working tree có thay đổi chưa commit, hãy hiểu rõ trạng thái đó trước khi tiếp tục các thao tác tích hợp khác. Việc đổi URL remote không cần xóa hoặc stash các thay đổi local; tuy nhiên, luôn nên kiểm tra trạng thái để tránh nhầm lẫn giữa lỗi kết nối và thay đổi đang có trong dự án.

## 4. Cập nhật địa chỉ bằng git remote set-url

Lệnh chuẩn để thay fetch URL của một remote:

~~~bash
git remote set-url origin https://git.example.com/platform/payment-service.git
~~~

Trong ví dụ này:

- <code>origin</code> là tên remote cần cập nhật.
- Địa chỉ cuối lệnh là URL mới của repository đích.

Nếu dự án chuyển từ HTTPS sang SSH:

~~~bash
git remote set-url origin git@git.example.com:platform/payment-service.git
~~~

Nếu máy chủ SSH dùng cổng không mặc định, có thể dùng URL dạng đầy đủ:

~~~bash
git remote set-url origin ssh://git@git.example.com:2222/platform/payment-service.git
~~~

Sau khi chạy lệnh, kiểm tra lại:

~~~bash
git remote -v
git remote get-url origin
~~~

<code>git remote set-url</code> cập nhật URL cho remote có tên được chỉ định. Tên remote vẫn là <code>origin</code>, nên các cấu hình upstream đang tham chiếu đến remote name này thường vẫn giữ nguyên. Bạn không cần xóa rồi tạo lại remote chỉ vì địa chỉ repository thay đổi.

### Cập nhật push URL riêng

Trong một số nhóm, fetch và push đi qua hai địa chỉ khác nhau. Ví dụ nhóm lấy dữ liệu qua HTTPS nhưng đẩy dữ liệu qua SSH. Khi đó, cập nhật push URL riêng bằng tùy chọn <code>--push</code>:

~~~bash
# Cập nhật fetch URL
git remote set-url origin https://git.example.com/platform/payment-service.git

# Cập nhật push URL riêng
git remote set-url --push origin git@git.example.com:platform/payment-service.git
~~~

Kiểm tra cả hai chiều:

~~~bash
git remote get-url origin
git remote get-url --push origin
git remote -v
~~~

Nếu remote đã có push URL riêng, việc cập nhật fetch URL không đồng nghĩa push URL riêng cũng được thay đổi. Hãy nhìn cả hai dòng <code>(fetch)</code> và <code>(push)</code> trong <code>git remote -v</code> để chắc chắn thao tác push không còn trỏ đến máy chủ cũ.

### Thay một URL cụ thể khi remote có nhiều URL

Git cho phép một remote có nhiều URL phục vụ các cấu hình đặc biệt. Trước khi chỉnh sửa loại cấu hình này, hãy xem toàn bộ URL bằng <code>git remote get-url --all &lt;remote-name&gt;</code> và <code>git remote get-url --push --all &lt;remote-name&gt;</code>.

Có thể chỉ định URL cũ để thay đúng mục tiêu:

~~~bash
git remote set-url origin https://git.example.com/platform/payment-service.git https://old.example.com/acme/payment-service.git
~~~

Các tùy chọn <code>--add</code> và <code>--delete</code> của <code>git remote set-url</code> dùng để thêm hoặc xóa URL trong cấu hình nhiều địa chỉ. Chỉ sử dụng chúng khi thực sự muốn duy trì nhiều endpoint; với một repository được chuyển địa chỉ thông thường, một fetch URL và một push URL rõ ràng thường dễ quản lý hơn.

## 5. Xác minh kết nối sau khi đổi địa chỉ

Việc lệnh <code>set-url</code> chạy thành công chỉ cho biết cấu hình local đã được cập nhật. Nó chưa chứng minh địa chỉ mới tồn tại, bạn có quyền truy cập hoặc repository đích chứa đúng dữ liệu. Hãy xác minh theo từng bước.

### Bước 1: Kiểm tra URL được lưu

~~~bash
git remote -v
git remote get-url origin
git remote get-url --push origin
~~~

Đối chiếu hostname, tổ chức, tên repository, giao thức và cổng nếu có với thông tin di chuyển đã được nhóm xác nhận.

### Bước 2: Kiểm tra remote có phản hồi

~~~bash
git ls-remote origin
~~~

<code>git ls-remote</code> truy vấn các tham chiếu mà remote công bố mà không cập nhật working tree hoặc tạo commit local. Nếu lệnh trả về các dòng hash và tên tham chiếu như <code>refs/heads/main</code> hoặc <code>refs/tags/v1.0.0</code>, Git đã liên hệ được với repository và đọc được danh sách tham chiếu.

Có thể kiểm tra nhánh mặc định mà máy chủ công bố:

~~~bash
git ls-remote --symref origin HEAD
~~~

Nếu lệnh báo lỗi, hãy phân loại nguyên nhân:

- **Repository không tồn tại hoặc sai URL:** kiểm tra lại đường dẫn, tên tổ chức, tên repository và cổng.
- **Permission denied hoặc HTTP 403:** xác minh tài khoản, quyền thành viên, token hoặc SSH key.
- **Could not resolve host / timeout:** kiểm tra DNS, mạng nội bộ, VPN, proxy hoặc trạng thái máy chủ.
- **Host key verification failed:** xác minh fingerprint SSH host theo hướng dẫn đáng tin cậy của nhà cung cấp hoặc quản trị viên trước khi chấp nhận host key.
- **Authentication failed:** kiểm tra credential manager, token hết hạn hoặc SSH agent và key đang được nạp.

Không đưa mật khẩu hoặc access token trực tiếp vào URL rồi lưu trong cấu hình repository. URL có thể xuất hiện trong file cấu hình, log lệnh, bản sao lưu hoặc ảnh chụp màn hình. Hãy dùng credential manager của Git hoặc SSH key theo chính sách của tổ chức.

### Bước 3: Fetch và kiểm tra nhánh remote

Sau khi <code>ls-remote</code> hoạt động và bạn xác nhận đây là repository đúng:

~~~bash
git fetch origin
git branch -r
git branch -vv
~~~

<code>git fetch origin</code> tải các đối tượng và cập nhật remote-tracking refs theo cấu hình fetch của remote. Lệnh này không tự merge thay đổi vào nhánh local và không ghi đè các chỉnh sửa trong working tree.

Nếu repository mới không có một số branch hoặc tag mà repository cũ từng có, hãy dừng lại để xác nhận việc di chuyển đã hoàn tất chưa. Đừng vội push dữ liệu local lên một repository đích chưa được kiểm tra.

## 6. Điều gì được giữ nguyên sau khi thay URL?

Nếu bạn chỉ thay URL của remote có tên <code>origin</code>, phần lớn cấu trúc local vẫn giữ nguyên:

| Thành phần | Ảnh hưởng của <code>git remote set-url origin ...</code> |
|---|---|
| Working tree | Không thay đổi |
| Index / staging area | Không thay đổi |
| Commit và lịch sử local | Không thay đổi |
| Tên nhánh local | Không thay đổi |
| Tên remote <code>origin</code> | Không thay đổi |
| Liên kết upstream như <code>origin/main</code> | Thường vẫn giữ nguyên vì remote name không đổi |
| Fetch/push URL của <code>origin</code> | URL được chỉ định sẽ thay đổi |
| Repository trên máy chủ | Không tự thay đổi hoặc được sao chép |

Đây là lý do thay URL thường là cách phù hợp khi cùng một repository được di chuyển sang địa chỉ mới nhưng vẫn giữ cấu trúc nhánh và lịch sử.

### Khi nhánh mặc định hoặc tên nhánh đã thay đổi

Đôi khi việc di chuyển đi kèm thay đổi tên nhánh mặc định, ví dụ <code>master</code> chuyển thành <code>main</code>. Thay URL không tự đổi tên nhánh local hoặc upstream. Sau khi fetch, kiểm tra:

~~~bash
git branch -r
git branch -vv
git ls-remote --symref origin HEAD
~~~

Nếu nhánh local <code>main</code> cần theo dõi <code>origin/main</code>, có thể cấu hình rõ:

~~~bash
git branch --set-upstream-to=origin/main main
~~~

Thay <code>main</code> bằng tên nhánh local thực tế. Chỉ thực hiện khi remote thực sự có nhánh đích và bạn muốn nhánh local theo dõi nhánh đó. Nếu nhóm vẫn dùng tên nhánh khác, không tự đổi upstream theo phỏng đoán.

## 7. Ví dụ hoàn chỉnh: chuyển origin sang máy chủ mới

Giả sử repository cũ là:

~~~text
https://github.com/acme/inventory-api.git
~~~

Nhóm đã chuyển repository sang:

~~~text
https://git.example.com/platform/inventory-api.git
~~~

Các bước thực hiện trong bản clone hiện tại:

~~~bash
# 1. Xem trạng thái local và remote hiện tại
git status
git remote -v
git branch -vv

# 2. Cập nhật địa chỉ origin
git remote set-url origin https://git.example.com/platform/inventory-api.git

# 3. Xác nhận cấu hình fetch và push
git remote -v

# 4. Kiểm tra máy chủ và quyền đọc
git ls-remote origin

# 5. Lấy tham chiếu mới về local
git fetch origin

# 6. Kiểm tra branch và upstream
git branch -r
git branch -vv

# 7. Kiểm tra trạng thái làm việc
git status
~~~

Nếu nhóm sử dụng SSH, bước 2 có thể dùng:

~~~bash
git remote set-url origin git@git.example.com:platform/inventory-api.git
~~~

Nếu cần xác nhận thao tác push có thể thực hiện mà chưa gửi cập nhật:

~~~bash
git push --dry-run origin HEAD
~~~

<code>--dry-run</code> yêu cầu Git thực hiện kiểm tra cho thao tác push nhưng không gửi cập nhật ref thực tế. Nó hữu ích để phát hiện một số vấn đề về kết nối hoặc quyền ghi, nhưng không thay thế việc xác minh chính sách branch protection và quy trình review của nhóm.

Khi repository đích đã được xác nhận đầy đủ và bạn thực sự cần đẩy nhánh hiện tại lên đó, dùng tên remote và branch rõ ràng:

~~~bash
git push -u origin main
~~~

Lệnh trên đẩy nhánh <code>main</code> local lên <code>origin</code> và thiết lập upstream cho các lần push/pull sau. Hãy thay <code>main</code> bằng nhánh đã được nhóm cho phép cập nhật. Không dùng <code>git push --mirror</code> như một bước thử nghiệm: tùy chọn mirror có thể cập nhật hoặc xóa các ref trên máy chủ đích để phản chiếu local, gây ảnh hưởng rộng đến repository dùng chung.

## 8. Đổi URL, đổi tên remote và thêm remote mới là ba việc khác nhau

Ba thao tác thường bị nhầm lẫn:

| Mục tiêu | Lệnh | Kết quả |
|---|---|---|
| Cùng remote name, địa chỉ repository thay đổi | <code>git remote set-url origin &lt;new-url&gt;</code> | <code>origin</code> vẫn là <code>origin</code>, URL được cập nhật |
| Giữ URL nhưng đổi tên remote | <code>git remote rename origin upstream</code> | Remote được đổi tên; cấu hình tham chiếu liên quan được Git cập nhật |
| Giữ remote cũ và khai báo thêm repository khác | <code>git remote add new-origin &lt;new-url&gt;</code> | Tạo remote mới tên <code>new-origin</code> |

Nếu muốn kiểm tra repository mới song song với repository cũ trong giai đoạn chuyển đổi, thêm remote mới có thể hữu ích:

~~~bash
git remote add new-origin https://git.example.com/platform/inventory-api.git
git remote -v
git ls-remote new-origin
git fetch new-origin
~~~

Sau khi nhóm xác nhận repository mới là đích chính, có thể quyết định cập nhật <code>origin</code> theo quy ước của dự án. Đừng đổi tên remote chỉ vì URL thay đổi; đổi tên có thể làm thay đổi cách các lệnh và tài liệu nội bộ tham chiếu đến remote.

## 9. Những trường hợp cần kiểm tra thêm

### Repository có submodule

Submodule có cấu hình URL riêng trong file <code>.gitmodules</code>. Đổi URL của remote cấp trên không tự động thay đổi URL của các repository con. Nếu địa chỉ submodule cũng được di chuyển, hãy cập nhật URL tương ứng trong <code>.gitmodules</code>, commit thay đổi đó theo quy trình của dự án, rồi đồng bộ cấu hình local:

~~~bash
git submodule sync --recursive
git submodule update --init --recursive
~~~

Nếu chỉ địa chỉ repository cha thay đổi và URL submodule vẫn hợp lệ, không cần thay đổi submodule.

### Repository sử dụng Git LFS

Git LFS lưu nội dung tệp lớn trong hệ thống lưu trữ LFS riêng, bên cạnh các đối tượng Git thông thường. Khi chuyển máy chủ, cần xác nhận nhà cung cấp đã di chuyển cả LFS objects và cấu hình endpoint tương ứng. Một lần <code>git fetch</code> thành công chưa chứng minh tất cả dữ liệu LFS đã có trên máy chủ mới.

Với quy trình chuyển máy chủ do nhóm quản trị thực hiện, hãy kiểm tra tài liệu migration của nhà cung cấp và xác nhận các tệp LFS có thể tải về từ remote mới trước khi ngừng máy chủ cũ.

### URL bị viết lại bởi cấu hình Git

Git hỗ trợ quy tắc <code>url.*.insteadOf</code> để tự động viết lại URL. Nếu <code>git remote get-url</code> hiển thị địa chỉ khác với chuỗi đã cấu hình, kiểm tra các quy tắc viết lại trong cấu hình Git:

~~~bash
git config --get-regexp '^url\..*\.insteadof$'
~~~

Quy tắc có thể nằm trong cấu hình local, global hoặc system. Chỉ sửa quy tắc sau khi xác định được phạm vi và tác động của nó đến các repository khác.

## 10. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| <code>git fetch</code> vẫn truy cập máy chủ cũ | Fetch URL chưa được cập nhật hoặc có URL rewrite | <code>git remote -v</code>, <code>git remote get-url origin</code> |
| <code>git push</code> vẫn đi đến máy chủ cũ | Push URL riêng còn giữ địa chỉ cũ | <code>git remote get-url --push origin</code> |
| <code>Repository not found</code> | Sai đường dẫn hoặc tài khoản không có quyền xem repository | Đối chiếu URL chính thức và quyền truy cập |
| <code>Permission denied (publickey)</code> | SSH key chưa được nạp, chưa đăng ký hoặc không có quyền | Kiểm tra SSH agent, key và quyền trên máy chủ |
| Fetch thành công nhưng push bị từ chối | Chỉ có quyền đọc, branch protection hoặc push URL khác | Kiểm tra push URL và chính sách repository |
| Nhánh local báo không có upstream | Nhánh mới chưa được thiết lập theo dõi hoặc upstream đã đổi tên | <code>git branch -vv</code>, sau đó cấu hình upstream đúng |
| Không thấy nhánh cũ trên remote mới | Migration chưa chuyển đủ branch hoặc nhánh đã đổi tên | <code>git ls-remote --heads origin</code> và xác nhận với nhóm |

Không nên xóa remote rồi thêm lại chỉ để thử sửa lỗi xác thực. Trước tiên hãy kiểm tra URL fetch/push, quyền truy cập và cấu hình xác thực; xóa remote có thể làm mất cấu hình fetch và các thông tin remote liên quan trong repository local.

## 11. Quy trình kiểm tra trước khi kết thúc migration

Trước khi coi việc chuyển địa chỉ remote ở máy local đã hoàn tất, hãy xác nhận:

- URL mới đúng với repository chính thức mà nhóm cung cấp.
- Fetch URL và push URL đều trỏ đúng đích dự kiến.
- <code>git ls-remote</code> đọc được refs từ máy chủ mới.
- <code>git fetch</code> hoàn tất và các remote-tracking branch cần thiết xuất hiện.
- Nhánh local vẫn theo dõi đúng upstream; nếu tên nhánh mặc định thay đổi, đã xác nhận và cấu hình lại rõ ràng.
- Quyền push, branch protection, submodule và Git LFS đã được kiểm tra theo nhu cầu của dự án.
- Các thành viên khác biết URL chuẩn để cập nhật bản clone của họ.

Việc cập nhật URL chỉ là một phần của migration toàn nhóm. Repository đích cần có dữ liệu và quyền truy cập phù hợp; các bản clone local của thành viên cũng cần trỏ về địa chỉ mới.

## 12. Bài tập tự kiểm tra

Thực hành trong một repository thử nghiệm hoặc repository cá nhân:

1. Chạy <code>git remote -v</code>. Có bao nhiêu remote và mỗi remote có fetch/push URL nào?
2. Chạy <code>git branch -vv</code>. Nhánh hiện tại đang theo dõi remote-tracking branch nào?
3. Thay URL của <code>origin</code> bằng một địa chỉ repository thử nghiệm hợp lệ. Chạy lại <code>git remote -v</code> để xác nhận.
4. Chạy <code>git ls-remote origin</code>. Lệnh này thay đổi working tree hay chỉ truy vấn tham chiếu từ remote?
5. Tạo một push URL riêng, sau đó kiểm tra vì sao fetch và push có thể hiển thị hai địa chỉ khác nhau.
6. Giải thích vì sao thay URL của <code>origin</code> thường không làm mất upstream <code>origin/main</code>.
7. Nếu repository có submodule, xác định URL của submodule nằm ở đâu và vì sao thay URL remote cha chưa đủ.

Bạn đã nắm được thao tác khi có thể tự xác định đúng remote, thay URL fetch/push có chủ đích, kiểm tra kết nối và xác nhận nhánh local vẫn theo dõi đúng repository. Thói quen kiểm tra trước và sau khi đổi địa chỉ giúp tránh đẩy commit lên nhầm máy chủ trong quá trình nhóm chuyển kho mã.
