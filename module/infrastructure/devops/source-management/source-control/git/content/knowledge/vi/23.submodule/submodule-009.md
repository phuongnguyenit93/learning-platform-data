# Đổi URL, đồng bộ cấu hình và gỡ submodule có kiểm soát

Submodule cho phép một repository superproject ghi nhận một repository Git khác như một thành phần phụ thuộc. Khi địa chỉ repository con thay đổi, mỗi bản clone hiện có cần cập nhật cấu hình URL để tiếp tục fetch và update được submodule. Khi không còn cần một submodule, nhóm cần gỡ liên kết khỏi superproject, xử lý dữ liệu local và quyết định có giữ hay xóa repository cache của submodule.

Các thao tác này liên quan tới nhiều nơi lưu thông tin: file .gitmodules được commit và chia sẻ, cấu hình local trong .git/config, gitlink trong index của superproject, thư mục làm việc của submodule và repository Git được lưu trong .git/modules. Nếu nhầm lẫn các thành phần đó, bạn có thể đổi URL mà máy khác không nhận được, xóa thư mục nhưng vẫn để metadata cũ, hoặc làm mất commit local trong submodule.

Sau bài này, bạn có thể:

- Phân biệt URL trong .gitmodules với URL local trong .git/config.
- Đổi URL submodule bằng git submodule set-url.
- Đồng bộ cấu hình URL bằng git submodule sync.
- Cập nhật submodule theo commit mà superproject ghi nhận.
- Kiểm tra trạng thái và commit riêng trong repository con trước khi gỡ.
- Tạm ngừng khởi tạo submodule bằng deinit.
- Gỡ submodule khỏi superproject và commit thay đổi đúng cách.
- Hiểu khi nào nên giữ hoặc xóa repository cache trong .git/modules.

## 1. Submodule được lưu ở nhiều lớp

Một submodule không chỉ là thư mục chứa mã nguồn. Superproject quản lý submodule bằng một số thành phần:

| Thành phần | Vai trò | Được chia sẻ qua commit? |
| --- | --- | --- |
| .gitmodules | Khai báo tên, đường dẫn và URL của submodule; có thể có branch hoặc cấu hình update. | Có. |
| Gitlink trong index/tree | Ghi mã commit của repository con mà superproject yêu cầu. | Có. |
| .git/config | Lưu cấu hình local, gồm URL và trạng thái khởi tạo của submodule. | Không. |
| Thư mục làm việc của submodule | Chứa tệp nguồn đang checkout tại commit được chỉ định. | Nội dung thuộc repository con. |
| .git/modules/ | Lưu repository Git riêng của các submodule trong clone hiện tại. | Không được commit như nội dung superproject. |

Ví dụ cấu trúc:

~~~text
product/
|-- .git/
|   +-- modules/
|       +-- shared-lib/       <- repository Git của submodule
|-- .gitmodules
|-- src/
+-- vendor/
    +-- shared-lib/           <- working tree của submodule
        |-- .git              <- file trỏ tới .git/modules/shared-lib
        +-- library files
~~~

Thư mục làm việc của submodule thường chứa một file .git trỏ tới repository con nằm trong .git/modules/NAME của superproject. Nhờ vậy, repository con có metadata Git riêng nhưng vẫn được quản lý gọn trong vùng dữ liệu của superproject.

Trong superproject, đường dẫn vendor/shared-lib được lưu như một gitlink có mode 160000. Gitlink trỏ tới một commit cụ thể trong repository con. Nó không lưu toàn bộ tệp của submodule vào tree của superproject.

File .gitmodules là cấu hình có thể chia sẻ với đồng đội. Cấu hình tương ứng trong .git/config thuộc clone hiện tại. Vì vậy, sửa URL trong .gitmodules và đồng bộ URL local là hai việc có liên quan nhưng không đồng nhất.

## 2. Kiểm tra submodule và URL hiện tại

Trước khi đổi URL hoặc gỡ submodule, hãy xem trạng thái:

~~~bash
git submodule status --recursive
git status --short --branch
git config -f .gitmodules --get-regexp '^submodule\..*\.'
~~~

git submodule status --recursive liệt kê commit mà mỗi submodule đang checkout và trạng thái của nó. Ký tự đầu dòng thường có ý nghĩa:

| Ký tự | Ý nghĩa |
| --- | --- |
| Dấu cách | Submodule đang checkout đúng commit được superproject ghi nhận. |
| - | Submodule chưa được khởi tạo. |
| + | Submodule đang checkout commit khác với gitlink được superproject ghi nhận. |
| U | Gitlink đang ở trạng thái xung đột. |

Xem nội dung .gitmodules:

~~~bash
git config -f .gitmodules --list
~~~

Ví dụ:

~~~text
submodule.shared-lib.path=vendor/shared-lib
submodule.shared-lib.url=https://git.example.com/team/shared-lib.git
~~~

Tên trong section submodule.shared-lib là tên submodule; giá trị path mới là đường dẫn thư mục trong superproject. Hai giá trị thường giống nhau nhưng không bắt buộc. Khi tìm repository cache trong .git/modules, cần dùng tên section, không nên mặc định tên đó luôn bằng path.

Xem URL local đã được cấu hình:

~~~bash
git config --get-regexp '^submodule\..*\.url$'
~~~

URL trong .gitmodules cho biết địa chỉ chia sẻ mà repository khai báo. URL trong .git/config cho biết clone hiện tại đang dùng địa chỉ nào. Hai giá trị có thể khác nhau nếu URL đã được thay đổi ở upstream nhưng clone local chưa chạy sync.

## 3. Đổi URL bằng git submodule set-url

Giả sử submodule vendor/shared-lib chuyển từ máy chủ cũ sang máy chủ mới. Dùng:

~~~bash
git submodule set-url vendor/shared-lib https://git.example.com/platform/shared-lib.git
~~~

Lệnh này cập nhật URL của submodule trong .gitmodules và cấu hình local tương ứng. Nó giúp clone hiện tại biết địa chỉ mới, đồng thời thay đổi .gitmodules có thể được commit để các clone khác nhận được.

Kiểm tra thay đổi:

~~~bash
git diff -- .gitmodules
git config -f .gitmodules --get-regexp '^submodule\..*\.url$'
git config --get-regexp '^submodule\..*\.url$'
~~~

Nếu muốn chỉnh sửa .gitmodules bằng tay, hãy thay đúng giá trị url trong section của submodule, rồi đồng bộ cấu hình local bằng git submodule sync. Dùng set-url thường ít nhầm section hơn.

### Đổi URL không đồng nghĩa đổi commit của submodule

URL chỉ cho Git biết nơi lấy repository con. Superproject vẫn ghi nhận mã commit của submodule trong gitlink. Nếu repository mới chứa commit được ghi nhận, submodule có thể tiếp tục checkout đúng nội dung cũ từ địa chỉ mới.

Nếu repository mới không có commit mà gitlink yêu cầu, git submodule update có thể thất bại. Khi đó, cần xác nhận repository mới có lịch sử tương ứng hay không, hoặc cập nhật submodule tới một commit mới rồi commit gitlink trong superproject.

### Dùng URL tương đối

.gitmodules có thể dùng URL tương đối, ví dụ:

~~~ini
[submodule "shared-lib"]
    path = vendor/shared-lib
    url = ../shared-lib.git
~~~

URL tương đối được Git phân giải dựa trên URL remote mặc định của superproject. Cách này hữu ích khi nhiều repository nằm cạnh nhau trên cùng máy chủ và được mirror cùng nhau. Với repository superproject team/product.git, URL ../shared-lib.git thường trỏ tới team/shared-lib.git.

Không nên tùy tiện thay ../shared-lib.git bằng ./shared-lib.git; dấu chấm và hai dấu chấm có ý nghĩa đường dẫn khác nhau. Nếu repository được chuyển sang máy chủ hoặc namespace khác, hãy xác minh URL tương đối được phân giải thành địa chỉ mong muốn.

## 4. Đồng bộ URL bằng git submodule sync

Khi một commit mới thay đổi URL trong .gitmodules, các clone đã khởi tạo submodule vẫn có thể giữ URL cũ trong .git/config. Chạy:

~~~bash
git submodule sync
~~~

Lệnh đọc URL trong .gitmodules và đồng bộ chúng vào cấu hình local của các submodule đã khởi tạo. Để áp dụng đệ quy cho submodule lồng nhau:

~~~bash
git submodule sync --recursive
~~~

Hoặc chỉ đồng bộ một submodule:

~~~bash
git submodule sync -- vendor/shared-lib
~~~

Sync chỉ cập nhật cấu hình URL. Nó không fetch object, không checkout commit mới và không tự thay đổi gitlink trong superproject.

Một trình tự thường dùng khi nhận thay đổi URL từ đồng đội:

~~~bash
# Lấy commit mới của superproject
git pull

# Cập nhật URL local theo .gitmodules mới
git submodule sync --recursive

# Khởi tạo hoặc checkout các submodule theo gitlink
git submodule update --init --recursive
~~~

Nếu superproject được cập nhật bằng merge hoặc rebase, hãy kiểm tra .gitmodules sau khi tích hợp trước khi chạy sync. Với submodule đã có local override URL riêng, sync sẽ đưa cấu hình URL về giá trị được khai báo trong .gitmodules; chỉ chạy khi đó là điều bạn muốn.

## 5. Khởi tạo và cập nhật submodule theo commit được ghi nhận

Sau khi URL đã đúng, dùng:

~~~bash
git submodule update --init --recursive
~~~

- --init đăng ký và khởi tạo các submodule chưa được khởi tạo.
- update lấy object cần thiết và checkout commit được superproject ghi trong gitlink.
- --recursive tiếp tục xử lý các submodule nằm bên trong submodule.

Theo mặc định, submodule thường được checkout ở detached HEAD tại commit mà superproject yêu cầu. Điều này là bình thường: superproject ghim một commit cụ thể để các clone có thể tái tạo cùng một phiên bản phụ thuộc.

Kiểm tra kết quả:

~~~bash
git submodule status --recursive
git diff --submodule
~~~

Nếu dòng submodule bắt đầu bằng dấu +, commit đang checkout không trùng gitlink. Có thể cập nhật lại bằng git submodule update --init --recursive, nhưng trước đó hãy xác nhận thay đổi local trong submodule không cần giữ.

### Khi muốn theo dõi nhánh mới nhất thay vì commit được ghim

git submodule update --remote là thao tác khác với update thông thường:

~~~bash
git submodule update --remote -- vendor/shared-lib
~~~

Lệnh này fetch và cập nhật submodule theo nhánh remote được cấu hình (hoặc nhánh remote mặc định nếu không chỉ định). Nó có thể di chuyển submodule tới commit mới hơn gitlink hiện tại. Khi superproject cần ghi nhận phiên bản mới đó, stage đường dẫn submodule và commit gitlink:

~~~bash
git add vendor/shared-lib
git diff --cached --submodule
git commit -m "Update shared library revision"
~~~

Không dùng --remote như cách thay thế mặc định cho git submodule update. Trong quy trình build tái lập, checkout commit được ghim thường là lựa chọn đúng; chỉ dùng update --remote khi nhóm chủ động muốn nâng phiên bản phụ thuộc theo nhánh.

## 6. Kiểm tra công việc local trước khi gỡ submodule

Trước khi deinit hoặc remove, hãy kiểm tra repository con. Đi vào thư mục submodule:

~~~bash
git -C vendor/shared-lib status --short --branch
git -C vendor/shared-lib branch -vv
git -C vendor/shared-lib log --oneline --decorate -n 12
~~~

Xác định:

- Có thay đổi chưa commit trong working tree của submodule không?
- Có commit local nào chưa push lên remote không?
- Submodule đang detached HEAD hay ở một branch?
- Có tệp chưa được theo dõi hoặc tệp bị ignore chứa dữ liệu cần giữ không?
- Các commit local có cần được chia sẻ, chuyển sang branch khác hoặc lưu thành patch không?

Commit của repository con không tự động trở thành commit của superproject. Superproject chỉ ghi nhận một mã commit thông qua gitlink. Nếu submodule có commit mới mà bạn muốn đồng đội nhận được, trước hết phải đảm bảo commit đó có thể truy cập từ remote của submodule, rồi mới cập nhật gitlink và commit trong superproject.

Ví dụ, nếu submodule có commit local cần giữ:

~~~bash
git -C vendor/shared-lib switch -c backup/shared-lib-work
git -C vendor/shared-lib push -u origin backup/shared-lib-work
~~~

Thay tên branch và remote theo thực tế. Nếu commit chưa sẵn sàng để push, hãy sao lưu hoặc tạo patch theo quy trình nhóm. Đừng xóa repository cache trước khi chắc chắn mọi commit và thay đổi quan trọng đã được lưu.

## 7. Deinit: ngừng khởi tạo nhưng giữ khai báo submodule

git submodule deinit dùng khi bạn muốn loại bỏ working tree của submodule khỏi clone hiện tại nhưng vẫn giữ submodule trong superproject.

~~~bash
git submodule deinit -- vendor/shared-lib
~~~

Lệnh này gỡ đăng ký submodule khỏi cấu hình local và xóa working tree của nó. Khai báo trong .gitmodules và gitlink trong commit của superproject vẫn còn. Repository Git local thường được giữ trong .git/modules, nên có thể khởi tạo lại sau:

~~~bash
git submodule update --init -- vendor/shared-lib
~~~

Để deinit tất cả submodule:

~~~bash
git submodule deinit --all
~~~

Thao tác này hữu ích khi clone chỉ cần một phần repository trong một thời gian, hoặc khi bạn muốn dọn working tree nhưng vẫn giữ cấu trúc phụ thuộc của dự án.

### Deinit có force

Nếu submodule còn thay đổi local hoặc không thể deinit theo cách an toàn, Git có thể từ chối. Tùy chọn -f buộc deinit:

~~~bash
git submodule deinit -f -- vendor/shared-lib
~~~

Force có thể loại bỏ working tree chứa thay đổi chưa lưu. Trước khi dùng, hãy commit, push, stash hoặc sao lưu mọi dữ liệu cần giữ. Deinit không phải cách xóa vĩnh viễn submodule khỏi lịch sử superproject.

## 8. Gỡ submodule vĩnh viễn khỏi superproject

Nếu dự án không còn phụ thuộc vào submodule, cần xóa gitlink và khai báo tương ứng khỏi superproject. Trước hết kiểm tra trạng thái và lưu công việc trong repository con như phần trước.

Một quy trình rõ ràng là:

~~~bash
# 1. Gỡ đăng ký local và working tree của submodule
git submodule deinit -- vendor/shared-lib

# 2. Xóa gitlink khỏi index và working tree của superproject
git rm -- vendor/shared-lib

# 3. Kiểm tra thay đổi
git status --short
git diff -- .gitmodules
git diff --cached --submodule

# 4. Commit việc gỡ submodule
git commit -m "Remove shared library submodule"
~~~

git rm stage việc xóa gitlink khỏi superproject và thường đồng thời loại section tương ứng khỏi .gitmodules. Hãy kiểm tra cả .gitmodules và staged diff trước khi commit. Nếu Git không tự loại đúng section vì cấu trúc hoặc thao tác trước đó, chỉnh sửa đúng section trong .gitmodules, stage file đó và xác minh lại.

Sau commit, các clone khác nhận được việc gỡ submodule khi pull hoặc checkout commit mới. Working tree của họ sẽ phản ánh rằng đường dẫn submodule không còn là thành phần của superproject.

### Khi git rm từ chối

Nếu submodule có thay đổi local, Git có thể từ chối để bảo vệ dữ liệu. Không vội thêm -f. Hãy kiểm tra:

~~~bash
git -C vendor/shared-lib status --short --branch
git submodule status --recursive
~~~

Lưu commit và tệp cần thiết trước. Nếu đã xác nhận mọi thay đổi có thể bỏ, có thể dùng:

~~~bash
git rm -f -- vendor/shared-lib
~~~

-f bỏ qua một số kiểm tra an toàn của git rm và có thể làm mất nội dung local trong working tree submodule. Chỉ dùng khi đã kiểm tra chính xác đường dẫn và chấp nhận hậu quả.

## 9. Repository cache trong .git/modules có nên xóa không?

Sau khi deinit hoặc remove submodule, repository Git riêng có thể vẫn được giữ trong .git/modules. Điều này giúp tái khởi tạo submodule hoặc khôi phục commit local khi cần.

Kiểm tra thư mục quản trị của submodule:

~~~bash
git rev-parse --git-path modules/shared-lib
~~~

Tên shared-lib trong ví dụ là tên section submodule. Nếu tên trong .gitmodules khác với path vendor/shared-lib, hãy dùng tên section thực tế. Có thể tra ánh xạ bằng:

~~~bash
git config -f .gitmodules --get-regexp '^submodule\..*\.path$'
~~~

Không xóa cache chỉ vì thư mục working tree đã biến mất. Cache có thể chứa commit local chưa được push, branch dự phòng hoặc dữ liệu cần để khôi phục. Chỉ cân nhắc xóa khi:

1. Submodule đã được gỡ khỏi superproject và thay đổi đã commit.
2. Không còn worktree hoặc tiến trình nào dùng repository con.
3. Mọi commit và dữ liệu local cần giữ đã được push hoặc sao lưu.
4. Bạn đã xác định đúng thư mục cache của đúng submodule.

Nếu thực sự muốn xóa repository cache, dùng công cụ hệ thống tệp trên đúng đường dẫn được git rev-parse --git-path trả về. Đây là thao tác xóa dữ liệu local không được Git tự động hoàn tác. Không xóa toàn bộ .git/modules vì thư mục đó có thể chứa nhiều submodule khác.

Với nhiều nhóm, giữ cache thêm một thời gian sau khi gỡ là lựa chọn thận trọng. Nó không ảnh hưởng tới commit của superproject và giúp phục hồi nếu phát hiện còn cần dữ liệu.

## 10. Đổi URL và gỡ submodule lồng nhau

Submodule có thể chứa submodule khác. Trong trường hợp đó, hãy dùng tùy chọn đệ quy khi đồng bộ hoặc khởi tạo:

~~~bash
git submodule sync --recursive
git submodule update --init --recursive
~~~

Nếu chỉ đổi URL của một submodule ở cấp sâu, xác định đúng path tương đối trong superproject hoặc submodule cha. Chạy lệnh ở đúng repository chứa file .gitmodules khai báo submodule đó.

Khi gỡ một submodule cha, hãy kiểm tra các submodule con bên trong và dữ liệu local của chúng trước. Việc loại working tree cha có thể làm toàn bộ cây thư mục con biến mất khỏi working tree; repository cache của các submodule lồng nhau có thể vẫn còn trong vùng quản trị. Đừng xóa cache theo phỏng đoán tên đường dẫn; xác định từng tên section và nơi lưu tương ứng trước khi dọn.

## 11. Kiểm tra thay đổi submodule trong superproject

Superproject ghi nhận commit của submodule như một gitlink. Một số lệnh hữu ích:

~~~bash
# Xem trạng thái tất cả submodule
git submodule status --recursive

# Xem thay đổi gitlink so với commit hiện tại
git diff --submodule

# Xem gitlink được lưu trong commit
git ls-tree HEAD vendor/shared-lib

# Xem thay đổi đã stage
git diff --cached --submodule
~~~

git ls-tree có thể hiển thị mode 160000, loại commit và mã commit của repository con. Đây là bằng chứng cho thấy superproject lưu một con trỏ commit chứ không lưu nội dung tệp submodule như tệp thông thường.

Nếu chỉ đổi URL, staged diff chủ yếu thể hiện thay đổi .gitmodules. Nếu cập nhật phiên bản submodule, staged diff sẽ thể hiện gitlink chuyển từ commit cũ sang commit mới. Nếu gỡ submodule, staged diff thể hiện gitlink bị xóa và .gitmodules được cập nhật.

## 12. Quy trình thực hành: chuyển submodule sang URL mới

Giả sử vendor/shared-lib chuyển từ máy chủ cũ sang máy chủ mới, nhưng superproject vẫn cần đúng commit hiện tại:

~~~bash
# 1. Xác nhận trạng thái ban đầu
git status --short --branch
git submodule status --recursive

# 2. Đổi URL được khai báo
git submodule set-url vendor/shared-lib https://git.example.com/platform/shared-lib.git

# 3. Xem thay đổi cấu hình
git diff -- .gitmodules

# 4. Đồng bộ URL local, gồm cả submodule lồng nhau nếu có
git submodule sync --recursive

# 5. Fetch và checkout commit mà superproject ghi nhận
git submodule update --init --recursive

# 6. Kiểm tra
git submodule status --recursive
git status --short

# 7. Commit thay đổi URL trong superproject
git add .gitmodules
git diff --cached
git commit -m "Update shared library submodule URL"
~~~

Nếu URL mới không có commit mà gitlink yêu cầu, dừng lại và xác nhận lịch sử repository. Không tự ý cập nhật gitlink sang commit mới nếu chưa được nhóm chấp thuận.

## 13. Quy trình thực hành: gỡ submodule đã hết nhu cầu

Giả sử dự án đã thay vendor/shared-lib bằng một thư viện khác:

~~~bash
# 1. Kiểm tra trạng thái superproject và submodule
git status --short --branch
git submodule status --recursive
git -C vendor/shared-lib status --short --branch
git -C vendor/shared-lib log --oneline -n 10

# 2. Lưu mọi commit hoặc tệp local cần giữ

# 3. Deinit để gỡ cấu hình local và working tree
git submodule deinit -- vendor/shared-lib

# 4. Xóa gitlink khỏi superproject
git rm -- vendor/shared-lib

# 5. Xác minh .gitmodules và index
git status --short
git diff -- .gitmodules
git diff --cached --submodule

# 6. Commit việc gỡ submodule
git commit -m "Remove shared library submodule"

# 7. Kiểm tra danh sách submodule còn lại
git submodule status --recursive
~~~

Sau commit, quyết định có giữ repository cache trong .git/modules hay không. Chỉ xóa cache sau khi đã xác minh không còn commit hoặc dữ liệu local cần bảo toàn.

## 14. Các lỗi thường gặp

### Đã sửa .gitmodules nhưng fetch vẫn dùng URL cũ

Clone hiện tại có thể còn cấu hình URL trong .git/config. Chạy git submodule sync hoặc git submodule sync --recursive, rồi kiểm tra cấu hình local. Nếu vừa thay URL bằng set-url, kiểm tra cả .gitmodules và .git/config.

### Sync xong nhưng nội dung submodule không thay đổi

Đây là hành vi bình thường. Sync chỉ đồng bộ URL, không fetch hoặc checkout commit. Dùng git submodule update --init --recursive để lấy commit mà superproject ghi nhận.

### Update submodule báo không tìm thấy commit

Repository tại URL mới có thể không chứa commit mà gitlink đang tham chiếu. Kiểm tra quyền truy cập, URL, lịch sử và việc mirror repository. Chỉ cập nhật gitlink sang commit khác sau khi xác nhận phiên bản phụ thuộc mới.

### Deinit xong nhưng submodule vẫn xuất hiện trong .gitmodules

Đây là hành vi đúng. Deinit chỉ bỏ khởi tạo local; nó giữ khai báo và gitlink trong superproject. Muốn gỡ vĩnh viễn, dùng git rm và commit.

### Đã xóa thư mục nhưng vẫn còn dữ liệu trong .git/modules

Repository cache được giữ để có thể khởi tạo lại. Đây không nhất thiết là lỗi. Chỉ dọn cache sau khi đã gỡ submodule khỏi superproject và xác nhận không còn dữ liệu cần giữ.

### Superproject báo submodule có commit khác

Dấu + trong git submodule status cho biết commit đang checkout khác gitlink. Kiểm tra thay đổi bên trong submodule; nếu commit mới là chủ đích, stage đường dẫn submodule và commit gitlink. Nếu không, chạy update để trở về commit được ghi nhận sau khi bảo toàn công việc local.

## 15. Ghi nhớ

- .gitmodules là cấu hình submodule được chia sẻ; .git/config chứa cấu hình local của clone.
- git submodule set-url đổi URL được khai báo; git submodule sync đồng bộ URL từ .gitmodules vào cấu hình local.
- Sync không fetch, không checkout và không đổi gitlink.
- git submodule update --init --recursive lấy và checkout commit được superproject ghim.
- Gitlink có mode 160000 và trỏ tới commit trong repository con.
- deinit gỡ working tree và đăng ký local nhưng giữ khai báo submodule trong superproject.
- git rm gỡ gitlink và cập nhật .gitmodules; commit thay đổi để đồng đội nhận được.
- Repository cache trong .git/modules có thể giữ commit local; chỉ xóa sau khi đã kiểm tra và sao lưu dữ liệu cần thiết.
- Đổi URL, cập nhật commit submodule và gỡ submodule là ba loại thay đổi khác nhau; hãy xem staged diff trước khi commit.

Khi hiểu rõ URL chia sẻ, cấu hình local, gitlink và repository cache, bạn có thể chuyển submodule sang máy chủ mới hoặc gỡ nó khỏi dự án mà vẫn kiểm soát được lịch sử và dữ liệu local.
