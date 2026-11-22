# Fetch lấy đối tượng và cập nhật nhánh theo dõi từ xa như thế nào

Trong một nhóm phát triển, repository trên máy của mỗi người thường không tự biết những commit mới mà đồng đội đã đẩy lên máy chủ. Git cung cấp lệnh **fetch** để kết nối tới remote, lấy về các đối tượng Git còn thiếu và cập nhật những tham chiếu theo dõi từ xa (remote-tracking refs). Nhờ vậy, bạn có thể xem trạng thái mới nhất của nhánh trên remote trước khi quyết định hợp nhất hoặc rebase công việc của mình.

Fetch là thao tác đồng bộ dữ liệu và thông tin tham chiếu. Nó không tự đưa commit mới vào nhánh local đang làm, không sửa tệp trong working tree và không thay đổi staging area. Hiểu rõ ranh giới này giúp bạn cập nhật thông tin từ nhóm mà vẫn chủ động kiểm tra trước khi tích hợp thay đổi.

Sau bài này, bạn có thể:

- Giải thích remote, remote-tracking branch và refspec.
- Mô tả cách fetch lấy các đối tượng Git và cập nhật tham chiếu local.
- Phân biệt remote-tracking refs với nhánh local và tệp FETCH_HEAD.
- Chọn cách fetch phù hợp cho một remote hoặc một nhánh cụ thể.
- Kiểm tra commit mới, nhánh bị xóa và khác biệt sau khi fetch.
- Quyết định khi nào nên merge, rebase hoặc tiếp tục làm việc độc lập.

## 1. Remote và nhánh theo dõi từ xa

Một **remote** là tên viết tắt mà repository local dùng để chỉ một repository khác, thường nằm trên máy chủ Git của nhóm. Khi clone một repository, Git thường tạo remote tên là **origin**. Tên này chỉ là bí danh trong cấu hình local; bạn có thể thêm remote khác như upstream hoặc company.

Xem các remote đã cấu hình:

~~~bash
git remote -v
~~~

Kết quả thường có URL dùng để fetch và URL dùng để push. Hai URL có thể giống hoặc khác nhau, tùy cấu hình. Muốn xem thông tin chi tiết của một remote:

~~~bash
git remote show origin
~~~

Một **nhánh local** như main hoặc feature/login là tham chiếu bạn có thể checkout và tạo commit trên đó. Một **nhánh theo dõi từ xa** như origin/main là tham chiếu local ghi lại vị trí nhánh main mà Git quan sát được ở remote origin trong lần đồng bộ gần nhất.

| Loại tham chiếu | Ví dụ | Vai trò |
| --- | --- | --- |
| Nhánh local | main | Nhánh làm việc trong repository hiện tại; có thể nhận commit mới. |
| Nhánh theo dõi từ xa | origin/main | Bản ghi local về vị trí nhánh main trên remote origin sau lần fetch gần nhất. |
| Nhánh remote thực tế | refs/heads/main trên máy chủ | Tham chiếu nằm trong repository remote. |

Tên origin/main thường là cách viết rút gọn của tham chiếu refs/remotes/origin/main trong repository local. Nó không phải một kết nối trực tiếp, cập nhật theo thời gian thực tới máy chủ. Nếu đồng đội vừa push commit mới, origin/main chỉ phản ánh commit đó sau khi bạn fetch thành công.

Nhánh theo dõi từ xa thường không phải nơi bạn checkout để phát triển tính năng. Bạn dùng nó làm mốc so sánh với nhánh local, rồi quyết định tích hợp commit bằng merge hoặc rebase.

## 2. Fetch thực hiện những việc gì

Khi chạy **git fetch origin**, Git thực hiện một chuỗi công việc khái quát:

1. Kết nối tới repository được cấu hình cho remote origin, xử lý xác thực và trao đổi thông tin về các tham chiếu mà remote đang công bố.
2. Xác định những tham chiếu cần lấy theo refspec trên dòng lệnh hoặc cấu hình fetch của remote.
3. Thương lượng với remote để xác định những đối tượng mà local còn thiếu.
4. Tải các đối tượng cần thiết, thường được đóng gói để truyền hiệu quả.
5. Ghi hoặc cập nhật các tham chiếu local theo ánh xạ đã cấu hình, chẳng hạn origin/main.
6. Ghi thông tin về các nhánh vừa lấy vào FETCH_HEAD để những lệnh tích hợp tiếp theo có thể sử dụng khi phù hợp.

Git lưu dữ liệu repository dưới dạng các đối tượng. Các loại đối tượng quan trọng gồm:

| Loại đối tượng | Nội dung |
| --- | --- |
| Commit | Thông tin về một phiên bản, gồm cây thư mục, cha, tác giả, người commit và thông điệp. |
| Tree | Cấu trúc thư mục và các mục con tại một phiên bản. |
| Blob | Nội dung của một tệp. |
| Tag object | Đối tượng tag có chú giải, có thể chứa thông tin người tạo và thông điệp. |

Commit mới thường tham chiếu tới tree, các tree lại tham chiếu tới blob và tree con. Vì vậy, lấy một commit có thể cần lấy cả chuỗi đối tượng mà repository local chưa có. Git không cần tải lại mọi đối tượng đã tồn tại; nó trao đổi thông tin để chỉ truyền dữ liệu cần thiết cho các tham chiếu được yêu cầu. Các đối tượng có thể được truyền trong packfile.

Sau khi tải dữ liệu, Git cập nhật tham chiếu theo ánh xạ fetch. Ví dụ, refspec mặc định thường ánh xạ các nhánh trên remote:

~~~text
+refs/heads/*:refs/remotes/origin/*
~~~

Phần bên trái chỉ các nhánh nguồn trên remote. Phần bên phải là nơi lưu tham chiếu theo dõi từ xa trong local. Dấu cộng ở đầu cho phép cập nhật tham chiếu đích kể cả khi lịch sử remote đã được viết lại và không còn là fast-forward. Điều này phù hợp với các tham chiếu theo dõi từ xa vì chúng cần phản ánh vị trí hiện tại của remote; không nên tự động áp dụng cùng cách đó cho nhánh local chứa công việc của bạn.

Fetch cập nhật dữ liệu và tham chiếu, nhưng không tự tích hợp commit vào nhánh local đang checkout. Do đó, fetch thông thường không tạo xung đột merge và không sửa nội dung trong working tree.

## 3. Vai trò của refspec

**Refspec** mô tả tham chiếu nào cần lấy từ remote và tham chiếu đó sẽ được lưu ở đâu trong local. Dạng tổng quát thường gặp là:

~~~text
[+]nguồn:đích
~~~

- Nguồn chỉ tham chiếu ở phía remote, ví dụ refs/heads/main.
- Đích chỉ tham chiếu local nhận giá trị, ví dụ refs/remotes/origin/main.
- Dấu cộng tùy chọn cho phép cập nhật đích khi thay đổi không phải fast-forward.
- Ký tự đại diện có thể ánh xạ nhiều nhánh cùng lúc.

Xem cấu hình fetch của origin:

~~~bash
git config --get-all remote.origin.fetch
~~~

Với cấu hình phổ biến, kết quả là:

~~~text
+refs/heads/*:refs/remotes/origin/*
~~~

Điều đó có nghĩa là khi fetch origin mà không chỉ rõ nhánh, Git lấy các nhánh được cấu hình và cập nhật các remote-tracking refs tương ứng. Một repository có thể dùng refspec khác để chỉ theo dõi một số nhánh, hoặc ánh xạ chúng vào namespace khác.

Bạn không cần tự viết refspec trong công việc hằng ngày nếu cấu hình remote mặc định đã đúng. Tuy nhiên, hiểu cấu trúc này giúp giải thích vì sao một lệnh fetch cập nhật origin/main, trong khi một lệnh fetch chỉ rõ một nhánh có thể chỉ ghi thông tin vào FETCH_HEAD.

## 4. Những cách fetch thường dùng

### Fetch remote mặc định

~~~bash
git fetch
~~~

Khi không truyền remote, Git chọn remote mặc định theo cấu hình và upstream của nhánh hiện tại. Nếu muốn thao tác rõ ràng, hãy chỉ tên remote:

~~~bash
git fetch origin
~~~

Lệnh này dùng các refspec fetch đã cấu hình cho origin. Với cấu hình thông dụng, các nhánh remote được ánh xạ sang origin/<ten-nhanh>. Đây là lựa chọn thường dùng khi bạn muốn cập nhật thông tin từ đồng đội trước khi tiếp tục làm việc.

### Fetch một nhánh cụ thể

~~~bash
git fetch origin main
~~~

Lệnh trên yêu cầu lấy nhánh main từ origin và ghi thông tin nhánh được lấy vào FETCH_HEAD. Vì refspec trên dòng lệnh không nêu đích, bạn không nên mặc định rằng lệnh này sẽ cập nhật origin/main như cấu hình fetch tổng quát. Nếu mục tiêu là cập nhật rõ ràng remote-tracking ref, có thể chỉ định cả nguồn và đích:

~~~bash
git fetch origin +refs/heads/main:refs/remotes/origin/main
~~~

Trong đa số trường hợp, **git fetch origin** với cấu hình fetch mặc định đơn giản và dễ hiểu hơn. Chỉ dùng refspec tường minh khi bạn cần kiểm soát chính xác tham chiếu nào được lấy và nơi lưu nó.

### Fetch từ mọi remote

~~~bash
git fetch --all
~~~

Lệnh này fetch từ tất cả remote đã cấu hình. Nó hữu ích khi repository làm việc với nhiều máy chủ, chẳng hạn origin là fork cá nhân và upstream là repository chính. Fetch tất cả remote có thể tốn thời gian hơn và không có nghĩa là Git sẽ hợp nhất mọi nhánh vào nhánh local.

### Fetch và dọn nhánh theo dõi từ xa đã bị xóa

~~~bash
git fetch --prune origin
~~~

Nếu một nhánh đã bị xóa trên remote, tham chiếu origin/<ten-nhanh> cũ có thể vẫn tồn tại trong local. Tùy chọn --prune yêu cầu Git xóa các remote-tracking refs tương ứng không còn có nguồn trên remote theo refspec đã cấu hình.

Prune chỉ dọn các tham chiếu theo dõi từ xa thuộc phạm vi ánh xạ; nó không xóa nhánh local có tên tương tự và không xóa commit đang được nhánh local tham chiếu. Dù vậy, trước khi dùng trong môi trường có cấu hình refspec đặc biệt, hãy kiểm tra remote và phạm vi fetch để hiểu những tham chiếu nào sẽ bị dọn.

### Fetch tag

~~~bash
git fetch --tags origin
~~~

Tùy chọn --tags yêu cầu lấy các tag từ remote. Theo mặc định, Git cũng có thể tự động lấy tag trỏ tới các lịch sử mà lần fetch đang lấy; hành vi này khác với việc yêu cầu lấy toàn bộ tag. Tag được lưu trong namespace refs/tags, không phải nhánh theo dõi từ xa origin/*.

Nếu cần đồng bộ tag và dùng prune cho tag, hãy đọc kỹ cấu hình và tùy chọn prune-tags của phiên bản Git đang dùng. Việc dọn tag local có thể xóa các tag mà nhóm đang sử dụng nếu chúng không tồn tại trên remote được chọn.

## 5. FETCH_HEAD là gì

FETCH_HEAD là tệp Git quản lý trong thư mục metadata của repository. Sau một lần fetch, tệp này ghi lại các tham chiếu và commit đã được lấy. Một số lệnh tích hợp có thể dùng thông tin này để biết lần fetch gần nhất đã lấy nội dung nào.

Xác định vị trí tệp FETCH_HEAD:

~~~bash
git rev-parse --git-path FETCH_HEAD
~~~

Lệnh trên in đường dẫn thực tế của tệp FETCH_HEAD. Bạn có thể đọc tệp đó bằng công cụ xem văn bản phù hợp nếu cần điều tra. Một lần fetch tiếp theo thường thay thế nội dung FETCH_HEAD; tùy chọn --append có thể nối thêm thông tin thay vì ghi đè.

FETCH_HEAD và remote-tracking branch có vai trò khác nhau:

| Thành phần | Dùng để làm gì | Vòng đời |
| --- | --- | --- |
| FETCH_HEAD | Ghi lại các tham chiếu đã lấy trong lần fetch gần nhất. | Có thể được cập nhật hoặc thay thế ở lần fetch tiếp theo. |
| origin/main | Ghi lại vị trí nhánh main trên origin theo lần fetch cập nhật ref đó. | Tồn tại như một tham chiếu local cho đến khi được cập nhật hoặc prune. |

Vì vậy, khi cần so sánh trạng thái nhánh remote với nhánh local trong thời gian dài, hãy dùng remote-tracking branch. FETCH_HEAD hữu ích để hiểu một lần fetch cụ thể vừa lấy gì.

## 6. Kiểm tra kết quả sau khi fetch

Sau khi fetch, hãy kiểm tra các tham chiếu và commit mới trước khi tích hợp:

~~~bash
git status --short --branch
git branch -r
git branch -vv
git log --oneline --graph --decorate --all -n 20
~~~

- **git status --short --branch** hiển thị trạng thái nhánh hiện tại; nếu upstream đã được cấu hình và đã fetch, Git có thể báo ahead hoặc behind.
- **git branch -r** liệt kê các remote-tracking branches local đang biết.
- **git branch -vv** hiển thị nhánh local và upstream mà nó theo dõi.
- **git log --all** cho phép nhìn lịch sử từ các tham chiếu local hiện có, bao gồm nhánh theo dõi từ xa.

Giả sử nhánh local là main và remote-tracking branch là origin/main. So sánh commit chỉ có ở một phía:

~~~bash
# Commit có trên origin/main nhưng chưa có trong main
git log --oneline main..origin/main

# Commit có trong main nhưng chưa có trên origin/main
git log --oneline origin/main..main
~~~

Toán tử hai chấm trong git log A..B chọn các commit có thể đi tới từ B nhưng không đi tới từ A. Vì vậy, hãy đọc theo thứ tự hai đầu mút: main..origin/main là phần remote đang có thêm; origin/main..main là phần local đang có thêm.

Muốn xem nội dung tệp giữa hai đầu nhánh:

~~~bash
git diff main..origin/main
~~~

Lệnh này so sánh hai cây nội dung tại các đầu mút. Nó không phải lệnh hợp nhất và không thay đổi working tree. Nếu cần xem thay đổi kể từ điểm phân nhánh chung, có thể dùng dạng ba chấm:

~~~bash
git diff main...origin/main
~~~

Dạng ba chấm so sánh cây ở đầu origin/main với merge base của hai nhánh. Chọn phép so sánh theo câu hỏi bạn muốn trả lời.

## 7. Fetch xong thì tích hợp thay đổi như thế nào

Fetch chỉ cập nhật thông tin. Sau khi xem xét commit mới, bạn quyết định cách đưa chúng vào nhánh local.

### Merge

~~~bash
git switch main
git merge origin/main
~~~

Merge kết hợp lịch sử từ origin/main vào nhánh local hiện tại. Nếu hai phía có thay đổi xung đột, Git dừng để bạn giải quyết conflict rồi hoàn tất merge. Nếu fast-forward được phép và lịch sử phù hợp, Git có thể chỉ di chuyển con trỏ nhánh local tới commit mới.

### Rebase

~~~bash
git switch feature/login
git rebase origin/main
~~~

Rebase đặt lại các commit riêng của nhánh feature/login lên trên đầu origin/main. Cách này tạo lịch sử tuyến tính hơn trong nhiều quy trình, nhưng có thể thay đổi mã định danh commit của phần lịch sử được viết lại. Không rebase các commit đã chia sẻ mà người khác đang dựa vào nếu nhóm chưa thống nhất cách xử lý lịch sử.

### Pull

~~~bash
git pull
~~~

Pull kết hợp fetch với bước tích hợp vào nhánh hiện tại. Tùy cấu hình và tùy chọn, bước tích hợp có thể là merge hoặc rebase. Nếu muốn kiểm tra trước những gì remote vừa thay đổi, chạy fetch riêng rồi xem log và diff trước khi merge hoặc rebase.

Không có lựa chọn tích hợp nào bắt buộc cho mọi nhóm. Hãy theo quy ước của repository, kiểm tra trạng thái working tree trước khi tích hợp và xử lý các thay đổi local đang dang dở theo quy trình của nhóm.

## 8. Ví dụ: cập nhật nhánh main an toàn

Giả sử bạn đang làm việc trên nhánh main và muốn biết đồng đội đã push những commit nào lên origin. Một trình tự có thể dùng:

~~~bash
# 1. Xác nhận nhánh và trạng thái hiện tại
git status --short --branch
git branch -vv

# 2. Lấy thông tin mới từ remote
git fetch origin

# 3. Kiểm tra trạng thái và các nhánh remote
git status --short --branch
git branch -r

# 4. Xem commit remote có thêm
git log --oneline main..origin/main

# 5. Xem khác biệt nội dung trước khi tích hợp
git diff main...origin/main

# 6. Khi đã sẵn sàng, tích hợp theo quy ước của nhóm
git merge origin/main

# 7. Xác minh kết quả
git status --short --branch
git log --oneline --decorate -n 8
~~~

Nếu nhóm dùng rebase cho nhánh đang phát triển, thay bước merge bằng rebase trên nhánh thích hợp. Nếu có thay đổi local chưa commit, hãy xử lý chúng trước khi tích hợp để tránh làm gián đoạn công việc.

## 9. Sự cố thường gặp khi fetch

### Không kết nối được remote

Kiểm tra URL bằng **git remote -v**, trạng thái mạng, quyền truy cập và thông tin xác thực. Nếu remote dùng SSH, xác nhận khóa SSH và quyền của tài khoản; nếu dùng HTTPS, xử lý thông tin xác thực theo công cụ được tổ chức hỗ trợ. Không đưa token hoặc mật khẩu vào URL được lưu trong lịch sử shell hay tài liệu chia sẻ.

### Fetch thành công nhưng không thấy origin/main thay đổi

Kiểm tra xem remote có thực sự có commit mới hay không, nhánh local có đang theo dõi origin/main không, và refspec fetch đang cấu hình thế nào:

~~~bash
git remote show origin
git config --get-all remote.origin.fetch
git branch -vv
~~~

Nếu bạn dùng lệnh chỉ rõ nguồn như **git fetch origin main**, thông tin có thể chỉ được ghi vào FETCH_HEAD vì refspec không chỉ định đích. Hãy dùng fetch origin với cấu hình mặc định hoặc refspec nguồn:đích phù hợp nếu muốn cập nhật một remote-tracking ref cụ thể.

### Nhánh remote đã bị xóa nhưng vẫn xuất hiện trong git branch -r

Fetch với --prune để dọn các remote-tracking refs không còn tồn tại theo cấu hình fetch:

~~~bash
git fetch --prune origin
~~~

Nhánh local có tên tương tự không bị xóa bởi thao tác prune này.

### Fetch báo lỗi object hoặc dữ liệu repository

Đọc đầy đủ thông báo lỗi và kiểm tra lại kết nối, dung lượng lưu trữ, quyền ghi trong thư mục repository và tình trạng repository remote. Không tự xóa thư mục .git hoặc các tệp object để thử sửa lỗi. Nếu nghi ngờ repository bị hỏng, hãy giữ nguyên bằng chứng và làm theo quy trình phục hồi của nhóm hoặc quản trị viên repository.

### Fetch không giải quyết được xung đột

Đó là hành vi đúng. Fetch không áp dụng commit mới lên nhánh local, nên nó không tạo merge conflict trong working tree. Xung đột chỉ xuất hiện ở bước tích hợp như merge hoặc rebase; khi đó hãy đọc thông báo Git, xử lý từng tệp xung đột, chạy kiểm tra và hoàn tất đúng quy trình.

## 10. Những điểm cần ghi nhớ

- Remote là bí danh local trỏ tới repository khác; origin chỉ là tên mặc định thường gặp.
- Remote-tracking branch như origin/main là mốc local phản ánh nhánh remote sau lần fetch cập nhật gần nhất.
- Fetch lấy các đối tượng còn thiếu và cập nhật refs theo refspec.
- FETCH_HEAD ghi lại các tham chiếu vừa fetch; nó không thay thế vai trò lâu dài của remote-tracking refs.
- Fetch không tự sửa nhánh local, staging area hoặc working tree.
- Dùng git log A..B để xem commit chỉ có ở B và git diff để xem khác biệt nội dung.
- Sau khi kiểm tra, chọn merge, rebase hoặc pull theo quy ước của nhóm.
- Dùng --prune khi cần dọn remote-tracking refs đã biến mất trên remote và đã hiểu phạm vi refspec.

Fetch tạo cho bạn một điểm quan sát mới về repository từ xa. Khi tách bước lấy dữ liệu khỏi bước tích hợp lịch sử, bạn có thể xem commit, đánh giá khác biệt và chọn thời điểm cập nhật nhánh local một cách có kiểm soát.
