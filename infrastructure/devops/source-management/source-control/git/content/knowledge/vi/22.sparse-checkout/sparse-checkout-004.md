# Giới hạn nhánh tải về bằng --single-branch và refspec

Một repository trên máy chủ có thể có hàng chục hoặc hàng trăm nhánh. Khi clone một repository lớn, bạn có thể chỉ cần làm việc với một nhánh ổn định hoặc một nhánh phát hành cụ thể. Git cung cấp tùy chọn **--single-branch** để giới hạn lịch sử được lấy theo một nhánh, cùng với **refspec** để xác định rõ tham chiếu nào được fetch và lưu vào đâu trong repository local.

Hai cơ chế này giúp giảm số nhánh theo dõi từ xa và giới hạn phạm vi cập nhật khi đồng bộ. Chúng điều khiển **nhánh và tham chiếu Git được lấy về**. Chúng không chọn các thư mục hoặc tệp xuất hiện trong working tree; việc chọn đường dẫn thuộc phạm vi của sparse-checkout.

Sau bài này, bạn có thể:

- Clone một repository chỉ theo dõi một nhánh bằng --single-branch.
- Hiểu quan hệ giữa --single-branch và remote.origin.fetch.
- Đọc và viết refspec nguồn:đích.
- Chỉ fetch một nhánh hoặc một nhóm nhánh cụ thể.
- Mở rộng hoặc thay đổi danh sách nhánh được theo dõi sau khi clone.
- Kiểm tra nhánh remote bằng git branch -r và git ls-remote.
- Phân biệt giới hạn nhánh với sparse-checkout, shallow clone và partial clone.

## 1. Phân biệt nhánh được fetch và tệp trong working tree

Git có nhiều cách giảm phạm vi dữ liệu mà một bản sao cần sử dụng. Mỗi cách điều khiển một khía cạnh khác nhau:

| Cơ chế | Giới hạn điều gì? | Ví dụ |
| --- | --- | --- |
| --single-branch và refspec | Các nhánh hoặc refs được fetch và cập nhật trong local. | Chỉ theo dõi main hoặc một số nhánh release. |
| sparse-checkout | Các đường dẫn được hiện diện trong working tree. | Chỉ checkout thư mục src/service và docs. |
| --depth hoặc --shallow-since | Độ sâu lịch sử commit được lấy. | Chỉ lấy một số commit gần đây. |
| Partial clone với --filter | Loại đối tượng Git được tải ngay. | Hoãn tải blob cho tới khi cần. |

Ví dụ, clone với --single-branch main vẫn lấy nội dung cây tệp cần thiết cho lịch sử của main. Nó không tự chọn riêng thư mục src/ hoặc bỏ qua thư mục docs/. Ngược lại, sparse-checkout có thể giới hạn đường dẫn trong working tree nhưng không có nghĩa là chỉ fetch một nhánh remote.

Trong chương Kho mã chọn lọc, các kỹ thuật này có thể được phối hợp để giảm footprint theo nhu cầu. Hãy xác định bạn muốn giới hạn refs, đường dẫn, lịch sử hay loại object trước khi chọn tùy chọn.

## 2. --single-branch trong git clone

Khi clone thông thường:

~~~bash
git clone https://example.com/team/product.git
~~~

Git tạo remote mặc định tên origin, checkout nhánh mặc định của remote và thường cấu hình fetch để theo dõi nhiều nhánh từ xa. Các nhánh theo dõi từ xa có thể được xem bằng:

~~~bash
git branch -r
~~~

Nếu chỉ cần một nhánh, dùng:

~~~bash
git clone --single-branch --branch main https://example.com/team/product.git product-main
~~~

Lệnh trên clone lịch sử dẫn tới tip của nhánh main và cấu hình repository mới để các lần fetch tiếp theo chỉ cập nhật nhánh được chọn theo cấu hình single-branch. Nếu không truyền --branch, Git dùng nhánh mà HEAD của remote chỉ tới làm nhánh mặc định:

~~~bash
git clone --single-branch https://example.com/team/product.git
~~~

Sau clone, thường chỉ có một remote-tracking branch:

~~~bash
git branch -r
~~~

Ví dụ:

~~~text
origin/main
~~~

Các nhánh khác vẫn tồn tại trên máy chủ. Chúng không bị xóa hoặc thay đổi; bản clone local chỉ không lấy và theo dõi chúng theo cấu hình hiện tại.

### Chọn nhánh khác với --branch

Tùy chọn --branch chọn nhánh sẽ checkout sau clone. Nó không tự giới hạn số nhánh được fetch. Nếu muốn chỉ lấy lịch sử của nhánh được chọn, kết hợp hai tùy chọn:

~~~bash
git clone --branch release/2.x --single-branch https://example.com/team/product.git product-release
~~~

Lệnh này checkout release/2.x và chỉ lấy lịch sử của nhánh đó theo chế độ single-branch. Nếu bỏ --single-branch, việc chỉ định --branch không đồng nghĩa với việc các nhánh khác sẽ không được fetch.

### Cho phép lấy tất cả nhánh

Nếu muốn clone theo cách thông thường và theo dõi phạm vi nhánh rộng hơn, có thể dùng:

~~~bash
git clone --no-single-branch https://example.com/team/product.git
~~~

--no-single-branch cũng hữu ích khi cần ghi đè hành vi single-branch được kích hoạt ngầm bởi một tùy chọn khác trong lệnh clone, chẳng hạn --depth.

## 3. --single-branch được lưu trong cấu hình fetch như thế nào?

Sau khi clone, Git lưu quy tắc fetch của remote trong cấu hình repository. Kiểm tra:

~~~bash
git config --get-all remote.origin.fetch
~~~

Với clone single-branch main, kết quả thường tương tự:

~~~text
+refs/heads/main:refs/remotes/origin/main
~~~

Đây là một refspec:

- refs/heads/main là nhánh nguồn trên remote.
- refs/remotes/origin/main là remote-tracking ref đích trong repository local.
- Dấu + ở đầu cho phép cập nhật ref đích kể cả khi lịch sử remote đã bị viết lại và cập nhật không còn là fast-forward.

Với clone thông thường theo dõi mọi nhánh, cấu hình phổ biến là:

~~~text
+refs/heads/*:refs/remotes/origin/*
~~~

Dấu * là wildcard, cho phép ánh xạ nhiều nhánh theo cùng một mẫu. Ví dụ refs/heads/feature/search trên remote được ánh xạ thành refs/remotes/origin/feature/search trong local.

Điểm quan trọng: --single-branch không phải một cơ chế hoàn toàn tách biệt với fetch. Khi clone, Git thiết lập refspec hẹp để những lần fetch tiếp theo chỉ cập nhật nhánh đã chọn. Vì vậy, xem remote.origin.fetch giúp bạn hiểu chính xác repository đang theo dõi những nhánh nào.

## 4. Cú pháp refspec

Refspec fetch có dạng tổng quát:

~~~text
[+]SOURCE:DESTINATION
~~~

| Thành phần | Ý nghĩa |
| --- | --- |
| SOURCE | Ref ở phía remote mà Git cần lấy. |
| DESTINATION | Ref local nhận kết quả, thường là remote-tracking ref. |
| Dấu + tùy chọn | Cho phép cập nhật ref đích dù thay đổi không phải fast-forward. |

Ví dụ ánh xạ một nhánh:

~~~text
+refs/heads/main:refs/remotes/origin/main
~~~

Ví dụ ánh xạ một nhóm nhánh:

~~~text
+refs/heads/release/*:refs/remotes/origin/release/*
~~~

Trong ví dụ thứ hai, các nhánh release/2.x và release/3.x trên remote được ánh xạ thành origin/release/2.x và origin/release/3.x ở local. Wildcard ở nguồn và đích phải tương ứng để Git thay phần khớp vào vị trí đích.

Refspec có thể được truyền trực tiếp cho git fetch hoặc lưu trong remote.origin.fetch. Khi lưu trong cấu hình, nó trở thành phạm vi fetch mặc định cho remote đó.

### Fetch một nhánh và chỉ định rõ đích

Để fetch nhánh feature/search và cập nhật remote-tracking ref tương ứng:

~~~bash
git fetch origin +refs/heads/feature/search:refs/remotes/origin/feature/search
~~~

Lệnh này nêu rõ cả nguồn và đích. Dùng refspec tường minh giúp tránh nhầm giữa việc lấy một nhánh vào FETCH_HEAD và việc cập nhật một remote-tracking ref có tên ổn định.

Nếu bỏ phần đích trong refspec, Git ghi thông tin fetch vào FETCH_HEAD:

~~~bash
git fetch origin refs/heads/feature/search
~~~

FETCH_HEAD ghi lại những gì lần fetch đó lấy được và có thể được dùng bởi bước tích hợp tiếp theo. Nếu cần một remote-tracking ref lâu dài để so sánh và theo dõi, hãy chỉ định đích hoặc cấu hình refspec tương ứng.

## 5. Dùng refspec để chỉ lấy một số nhánh

Giả sử repository có nhiều nhánh nhưng nhóm triển khai chỉ cần main và hai nhánh bảo trì. Có thể cấu hình remote chỉ theo dõi các nhánh đó.

Dùng git remote set-branches:

~~~bash
git remote set-branches origin main maintenance/2.x maintenance/3.x
git fetch origin
~~~

Lệnh set-branches thay danh sách nhánh được theo dõi bởi remote origin bằng danh sách được nêu. Sau fetch, kiểm tra:

~~~bash
git config --get-all remote.origin.fetch
git branch -r
~~~

Nếu chỉ muốn bổ sung một nhánh vào danh sách hiện tại mà giữ các nhánh đã cấu hình, dùng --add:

~~~bash
git remote set-branches --add origin feature/search
git fetch origin
~~~

Sau đó, remote-tracking ref origin/feature/search có thể được dùng để tạo nhánh local:

~~~bash
git switch --track -c feature/search origin/feature/search
~~~

Lệnh trên tạo nhánh local feature/search và thiết lập upstream là origin/feature/search.

### Cấu hình bằng git config

Bạn cũng có thể quản lý refspec trực tiếp trong cấu hình local:

~~~bash
# Thay toàn bộ danh sách fetch bằng một nhánh main
git config --replace-all remote.origin.fetch "+refs/heads/main:refs/remotes/origin/main"

# Bổ sung một nhánh khác
git config --add remote.origin.fetch "+refs/heads/feature/search:refs/remotes/origin/feature/search"

# Xem lại các refspec đang áp dụng
git config --get-all remote.origin.fetch
~~~

Đây là cấu hình riêng của repository hiện tại, thường nằm trong .git/config. Không commit file cấu hình local này như một thay thế cho tài liệu quy trình của nhóm.

Nếu muốn mở rộng phạm vi từ single-branch, hãy thêm refspec hoặc dùng remote set-branches --add. Chỉ chạy git fetch sau khi xác nhận danh sách mới đúng.

## 6. Dùng wildcard để theo dõi một nhóm nhánh

Khi tên nhánh có quy ước, wildcard giúp tránh khai báo từng nhánh. Ví dụ, chỉ lấy các nhánh bắt đầu bằng release/:

~~~bash
git fetch origin "+refs/heads/release/*:refs/remotes/origin/release/*"
~~~

Lệnh này fetch các refs phù hợp với mẫu và cập nhật remote-tracking refs trong namespace origin/release/. Nó không tạo các nhánh local tự động.

Muốn cấu hình mẫu này cho các lần fetch sau:

~~~bash
git config --add remote.origin.fetch "+refs/heads/release/*:refs/remotes/origin/release/*"
git fetch origin
~~~

Nếu cấu hình cũ vẫn chứa wildcard rộng:

~~~text
+refs/heads/*:refs/remotes/origin/*
~~~

thì thêm refspec release/* không giới hạn fetch, vì refspec rộng vẫn yêu cầu lấy mọi nhánh. Muốn giới hạn thực sự, cần thay thế refspec rộng bằng các refspec hẹp, ví dụ dùng git remote set-branches origin main "release/*" hoặc thay cấu hình bằng --replace-all và --add.

Trên shell, hãy đặt dấu ngoặc kép quanh refspec có ký tự * để shell không diễn giải wildcard trước khi Git nhận được nó. Cách quote cụ thể có thể khác giữa Bash, PowerShell và các shell khác; ví dụ trên dùng dấu ngoặc kép phù hợp với các shell phổ biến.

## 7. Mở rộng phạm vi sau một clone single-branch

Giả sử ban đầu bạn clone:

~~~bash
git clone --single-branch --branch main https://example.com/team/product.git
cd product
~~~

Sau một thời gian, bạn cần thêm nhánh feature/search. Có thể thực hiện:

~~~bash
git remote set-branches --add origin feature/search
git fetch origin
git branch -r
~~~

Kết quả remote-tracking branches sẽ có main và feature/search:

~~~text
origin/main
origin/feature/search
~~~

Tạo nhánh local để làm việc:

~~~bash
git switch --track -c feature/search origin/feature/search
~~~

Nếu sau đó không cần theo dõi feature/search nữa, có thể thay danh sách nhánh:

~~~bash
git remote set-branches origin main
~~~

Thay đổi cấu hình không tự xóa branch local feature/search và cũng không nhất thiết xóa remote-tracking ref đã có. Muốn dọn remote-tracking refs không còn được remote công bố trong phạm vi refspec hiện tại, có thể dùng prune:

~~~bash
git fetch --prune origin
~~~

Prune hoạt động dựa trên ánh xạ fetch đang cấu hình. Khi thay đổi refspec, hãy xem danh sách refs và hiểu phạm vi prune trước khi thực hiện; prune không xóa branch local cùng tên.

## 8. Xem tất cả nhánh trên remote mà không fetch

Sau clone single-branch, git branch -r chỉ hiển thị remote-tracking refs mà local đã biết. Nó không phải danh sách đầy đủ các nhánh đang tồn tại trên máy chủ.

Muốn xem nhánh remote mà không tải object và không cập nhật remote-tracking refs, dùng:

~~~bash
git ls-remote --heads origin
~~~

Lệnh này truy vấn các refs nhánh trên remote. Có thể lọc theo mẫu:

~~~bash
git ls-remote --heads origin "refs/heads/release/*"
~~~

So sánh hai lệnh:

| Lệnh | Kết quả |
| --- | --- |
| git branch -r | Liệt kê remote-tracking refs đã có trong local. |
| git ls-remote --heads origin | Liệt kê refs nhánh mà remote đang công bố tại thời điểm truy vấn. |
| git fetch origin <refspec> | Lấy object cần thiết và cập nhật ref local theo refspec. |

Nếu git ls-remote hiển thị nhánh nhưng git branch -r không có nhánh đó, điều này có thể chỉ có nghĩa là bạn chưa fetch nhánh ấy.

## 9. Fetch --all không có nghĩa là lấy mọi nhánh

Một hiểu lầm phổ biến là:

~~~bash
git fetch --all
~~~

sẽ lấy tất cả branch của mọi remote. Thực tế, --all yêu cầu fetch từ tất cả remote đã cấu hình, nhưng mỗi remote vẫn dùng các refspec fetch của chính nó. Nếu origin được cấu hình single-branch, fetch --all vẫn chỉ lấy phạm vi refs mà cấu hình origin cho phép.

Ví dụ:

~~~bash
git remote -v
git config --get-all remote.origin.fetch
git config --get-all remote.upstream.fetch
git fetch --all
~~~

origin có thể chỉ theo dõi main, trong khi upstream theo dõi mọi nhánh. Lệnh fetch --all áp dụng hai cấu hình riêng đó; nó không tự mở rộng refspec hẹp thành wildcard.

## 10. Prune và các remote-tracking refs cũ

Khi một nhánh bị xóa trên remote, remote-tracking ref tương ứng có thể vẫn còn trong local cho đến khi được dọn. Dùng:

~~~bash
git fetch --prune origin
~~~

Git xóa những remote-tracking refs nằm trong phạm vi ánh xạ fetch mà không còn nhánh nguồn tương ứng trên remote. Điều này giúp git branch -r phản ánh trạng thái hiện tại hơn.

Prune không xóa branch local:

~~~bash
git branch --list
git branch -r
~~~

Một branch local feature/search vẫn tồn tại dù origin/feature/search đã bị prune. Nếu muốn xóa branch local, đó là quyết định riêng và cần kiểm tra xem commit của nó đã được hợp nhất hoặc lưu ở nơi khác chưa.

Nếu cấu hình refspec bị thu hẹp, các remote-tracking refs cũ nằm ngoài ánh xạ mới có thể không còn được lệnh prune hiện tại quản lý. Kiểm tra git branch -r và cấu hình remote.origin.fetch trước khi dọn thủ công.

## 11. Kết hợp --single-branch với shallow clone

Khi repository rất lớn, có thể kết hợp giới hạn nhánh và giới hạn độ sâu lịch sử:

~~~bash
git clone --single-branch --branch main --depth 20 https://example.com/team/product.git product-main
~~~

Lệnh này chỉ lấy lịch sử của nhánh main trong phạm vi độ sâu được yêu cầu. --depth giới hạn số lớp lịch sử commit; --single-branch giới hạn nhánh được lấy. Hai tùy chọn giải quyết hai chiều khác nhau.

Lưu ý, --depth tự động hàm ý --single-branch trừ khi được kết hợp với --no-single-branch. Nếu muốn shallow clone nhưng vẫn lấy lịch sử giới hạn độ sâu của nhiều nhánh, có thể dùng:

~~~bash
git clone --depth 20 --no-single-branch https://example.com/team/product.git
~~~

Shallow repository có giới hạn trong một số thao tác lịch sử như merge hoặc truy tìm tổ tiên xa. Khi cần lịch sử đầy đủ, có thể lấy thêm commit bằng fetch --deepen hoặc bỏ giới hạn bằng fetch --unshallow, tùy trạng thái repository.

## 12. Quy trình thực hành: chỉ lấy nhánh cần thiết

Giả sử nhóm có remote origin với nhiều nhánh, nhưng môi trường triển khai chỉ cần main và các nhánh release. Một quy trình có thể là:

~~~bash
# 1. Clone chỉ nhánh main
git clone --single-branch --branch main https://example.com/team/product.git product
cd product

# 2. Kiểm tra refspec single-branch đã được tạo
git config --get-all remote.origin.fetch

# 3. Xem nhánh local đang biết và nhánh remote thực tế
git branch -r
git ls-remote --heads origin

# 4. Thay cấu hình để theo dõi main và các nhánh release
git remote set-branches origin main "release/*"

# 5. Fetch theo phạm vi mới
git fetch origin

# 6. Kiểm tra remote-tracking refs
git branch -r

# 7. Nếu cần làm việc trên một nhánh release cụ thể
git switch --track -c release/2.x origin/release/2.x
~~~

Nếu shell hoặc phiên bản Git không xử lý wildcard theo cách bạn mong muốn, có thể dùng refspec tường minh với git config hoặc fetch trực tiếp. Luôn xem lại remote.origin.fetch để xác nhận phạm vi thực tế.

## 13. Lỗi thường gặp

### Dùng --branch nhưng vẫn thấy nhiều remote-tracking branches

--branch chỉ chọn nhánh checkout. Muốn giới hạn số nhánh fetch, thêm --single-branch khi clone.

### Đã clone single-branch nhưng cần thêm một nhánh

Dùng git remote set-branches --add origin BRANCH rồi git fetch origin. Sau đó tạo nhánh local từ remote-tracking ref nếu cần.

### Thêm refspec hẹp nhưng fetch vẫn lấy nhiều nhánh

Kiểm tra toàn bộ giá trị remote.origin.fetch. Một refspec wildcard rộng vẫn còn trong cấu hình sẽ tiếp tục yêu cầu fetch nhiều nhánh; cần thay thế nó thay vì chỉ thêm một refspec hẹp.

### git branch -r không hiển thị nhánh mà đồng đội nói đang có

Kiểm tra bằng git ls-remote --heads origin. Nếu remote có nhánh đó, bổ sung refspec và fetch.

### Fetch một nhánh nhưng không thấy remote-tracking ref tương ứng

Kiểm tra refspec có phần đích hay không. Nếu không có đích, lần fetch có thể chỉ ghi thông tin vào FETCH_HEAD. Dùng refspec nguồn:đích để cập nhật remote-tracking ref rõ ràng.

### git fetch --all vẫn không lấy mọi nhánh

--all chỉ mở rộng số remote được fetch; phạm vi branch của mỗi remote vẫn phụ thuộc refspec tương ứng.

### Nghĩ rằng --single-branch chỉ tải một thư mục

Không đúng. Tùy chọn này giới hạn nhánh và lịch sử reachable từ nhánh đó. Muốn chọn thư mục trong working tree, dùng sparse-checkout; muốn giảm loại object tải xuống, xem partial clone và object filter.

## 14. Ghi nhớ

- --single-branch giới hạn nhánh được clone và phạm vi remote-tracking refs được cập nhật về sau.
- --branch chọn nhánh checkout; tự nó không giới hạn các nhánh được fetch.
- Refspec có dạng SOURCE:DESTINATION và có thể thêm dấu + để cho phép cập nhật không fast-forward.
- remote.origin.fetch lưu các refspec fetch mặc định của remote origin.
- git remote set-branches thay danh sách nhánh theo dõi; --add bổ sung nhánh vào danh sách hiện tại.
- Wildcard refspec hữu ích khi chỉ theo dõi một nhóm nhánh theo quy ước tên.
- git branch -r hiển thị refs local đã fetch; git ls-remote --heads xem refs đang có trên máy chủ mà không fetch.
- git fetch --all vẫn tuân theo refspec riêng của từng remote.
- --prune dọn remote-tracking refs stale trong phạm vi refspec; nó không xóa branch local.
- Giới hạn refs bằng --single-branch/refspec khác với giới hạn đường dẫn bằng sparse-checkout, giới hạn lịch sử bằng --depth và lọc object bằng --filter.

Khi cấu hình đúng --single-branch và refspec, bạn có thể giữ repository local chỉ theo dõi những nhánh phục vụ công việc hiện tại. Điều này giúp danh sách remote-tracking refs gọn hơn và làm rõ phạm vi đồng bộ, đồng thời vẫn cho phép mở rộng danh sách nhánh khi nhu cầu thay đổi.
