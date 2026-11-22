# Ngừng theo dõi tệp nhưng giữ bản cục bộ bằng git rm --cached

Có những tệp cần tồn tại trên máy của mỗi lập trình viên nhưng không nên nằm trong repository, chẳng hạn file cấu hình môi trường, thông tin kết nối database, file log hoặc dữ liệu phát sinh khi chạy ứng dụng. Nếu một tệp đã được commit, thêm tên tệp vào .gitignore không làm Git ngừng theo dõi nó. Git vẫn xem đường dẫn đó là tracked và tiếp tục ghi nhận các thay đổi.

Lệnh **git rm --cached** giải quyết tình huống này: nó gỡ đường dẫn khỏi index để Git không còn đưa tệp vào các commit tiếp theo, đồng thời giữ bản tệp hiện tại trên working tree. Khi kết hợp với quy tắc ignore phù hợp và commit thay đổi, repository ngừng quản lý tệp trong tương lai còn bản cục bộ vẫn ở trên máy đang thực hiện thao tác.

Bài học này giải thích chính xác lệnh thay đổi những gì, cách dùng an toàn cho một tệp hoặc cả thư mục, cách xác minh kết quả, sự khác nhau với git restore --staged và git rm thông thường, cũng như ảnh hưởng đến các thành viên khác khi thay đổi được push lên remote.

## 1. Hiểu đúng mục tiêu của git rm --cached

### 1.1. Git theo dõi đường dẫn qua index

Git xác định snapshot tiếp theo thông qua index (staging area). Với một tệp đã được commit, đường dẫn đó thường có mặt trong commit hiện tại và trong index.

Kiểm tra một đường dẫn có đang được theo dõi hay không:

~~~bash
git ls-files -- .env
~~~

Nếu lệnh hiển thị .env, đường dẫn đang có trong index. Nếu không có kết quả, Git hiện không có entry tương ứng trong index.

Có thể yêu cầu Git báo lỗi rõ nếu đường dẫn không được theo dõi:

~~~bash
git ls-files --error-unmatch -- .env
~~~

Trước khi thay đổi, kiểm tra trạng thái:

~~~bash
git status --short --branch
~~~

### 1.2. --cached chỉ gỡ khỏi index

Cú pháp:

~~~bash
git rm --cached -- .env
~~~

Lệnh này loại .env khỏi index nhưng giữ tệp trên working tree. Với tệp đã tồn tại trong HEAD, thao tác được ghi nhận như một thay đổi xóa khỏi snapshot tiếp theo.

Có thể hình dung:

| Thành phần | Trước lệnh | Sau git rm --cached |
| --- | --- | --- |
| Commit HEAD hiện tại | Có .env | Vẫn có .env |
| Index | Có .env | Không còn .env |
| Working tree | Có .env | Vẫn có .env |
| Trạng thái Git | Không thay đổi nếu tệp clean | Xóa đã stage |

Điểm quan trọng: lệnh không xóa commit cũ và cũng không xóa tệp khỏi working tree. Nó chỉ cập nhật index để chuẩn bị snapshot tiếp theo không còn đường dẫn đó.

### 1.3. Sau commit, repository và máy local có trạng thái khác nhau

Khi commit thay đổi xóa khỏi index:

~~~bash
git commit -m "Stop tracking local environment file"
~~~

Commit mới không còn chứa .env. Trên máy đang thực hiện thao tác, tệp vẫn tồn tại trên đĩa. Vì Git không còn theo dõi nó, tệp sẽ trở thành untracked nếu không có quy tắc ignore phù hợp, hoặc ignored nếu được khớp bởi .gitignore hay quy tắc ignore khác.

Đây chính là mục tiêu thường gặp: repository không còn quản lý file local, nhưng người đang làm việc vẫn giữ cấu hình của mình.

Nếu file mới chỉ vừa được stage nhưng chưa từng có trong HEAD, git rm --cached cũng gỡ entry khỏi index và giữ file trên đĩa. Trong trường hợp này, không có một đường dẫn đã commit để tạo thành staged deletion; file trở lại trạng thái untracked hoặc ignored tùy quy tắc ignore.

### 1.4. --cached khác với xóa tệp

Lệnh:

~~~bash
git rm -- .env
~~~

gỡ đường dẫn khỏi index và xóa tệp khỏi working tree. Đây không phải hành động phù hợp nếu bạn muốn giữ bản local.

Lệnh:

~~~bash
git rm --cached -- .env
~~~

chỉ gỡ khỏi index và để tệp trên đĩa.

Luôn kiểm tra có tùy chọn --cached trước khi thực hiện với tệp chứa cấu hình hoặc dữ liệu local quan trọng.

## 2. Vì sao thêm .gitignore vẫn chưa đủ?

### 2.1. .gitignore chủ yếu áp dụng cho đường dẫn chưa được theo dõi

Ví dụ, thêm quy tắc:

~~~gitignore
.env
~~~

Quy tắc này ngăn một file .env mới, chưa được Git theo dõi, xuất hiện như untracked trong trạng thái thông thường và được thêm nhầm bằng các thao tác add phổ biến.

Nhưng nếu .env đã được commit, Git vẫn tiếp tục theo dõi nó. Khi bạn sửa file, Git vẫn báo modified dù .env có trong .gitignore.

Lý do là ignore không phải cơ chế bỏ theo dõi. Git không áp dụng quy tắc ignore để tự loại các đường dẫn đã có trong index.

### 2.2. Cần kết hợp ignore và rm --cached

Với một file local cần giữ lại, quy trình thường gồm hai thay đổi:

1. Thêm pattern vào .gitignore để Git bỏ qua file sau khi nó không còn tracked.
2. Dùng git rm --cached để loại file khỏi index.

Ví dụ:

~~~bash
printf ".env\n" >> .gitignore
git rm --cached -- .env
git add .gitignore
git status --short
~~~

Nếu .gitignore đã có quy tắc phù hợp, không cần thêm lại dòng trùng lặp. Hãy kiểm tra nội dung file trước khi sửa để tránh tạo pattern không cần thiết.

### 2.3. Chọn nơi đặt quy tắc ignore

Có ba vị trí thường dùng:

| Vị trí | Phạm vi | Khi nào dùng |
| --- | --- | --- |
| .gitignore | Chia sẻ cùng repository | File local hoặc file sinh tự động mà mọi thành viên nên bỏ qua |
| .git/info/exclude | Chỉ repository local hiện tại | File riêng của máy bạn, không cần chia sẻ quy tắc với nhóm |
| core.excludesFile | Nhiều repository của người dùng hiện tại | Quy tắc cá nhân áp dụng toàn cục, ví dụ file tạm của IDE |

Nếu cả nhóm đều không nên commit .env, hãy đưa pattern vào .gitignore để quy tắc được chia sẻ. Nếu chỉ máy bạn có file tạm riêng, .git/info/exclude hoặc file ignore toàn cục có thể phù hợp hơn.

Dù đặt pattern ở đâu, quy tắc ignore vẫn không tự gỡ đường dẫn đã tracked. Với file đã được commit, bạn vẫn cần thay đổi index bằng git rm --cached.

## 3. Quy trình chuẩn cho một tệp

Giả sử repository đang theo dõi file .env và bạn muốn giữ nội dung hiện tại trên máy, đồng thời ngừng đưa file này vào các commit tương lai.

### Bước 1 — Xác nhận file đang tồn tại và được theo dõi

Trên Bash hoặc macOS/Linux:

~~~bash
test -f .env && echo "Local file exists"
git ls-files --error-unmatch -- .env
git status --short -- .env
~~~

Trên PowerShell:

~~~powershell
Test-Path -LiteralPath .env
git ls-files --error-unmatch -- .env
git status --short -- .env
~~~

Nếu file không tồn tại trên working tree nhưng mục tiêu là giữ bản local, hãy khôi phục từ bản sao an toàn hoặc nguồn cấu hình trước khi tiếp tục. Không giả định --cached có thể tạo lại nội dung bị thiếu.

### Bước 2 — Kiểm tra và thêm quy tắc ignore

Mở .gitignore, kiểm tra pattern hiện có rồi thêm:

~~~gitignore
.env
~~~

Nếu muốn ignore các biến thể môi trường nhưng vẫn giữ file mẫu, có thể dùng:

~~~gitignore
.env
.env.*
!.env.example
~~~

Hãy hiểu rõ pattern trước khi dùng. Quy tắc .env.* cũng khớp các tên như .env.production và .env.local; ngoại lệ .env.example giữ file mẫu có thể commit.

### Bước 3 — Gỡ file khỏi index, giữ working tree

~~~bash
git rm --cached -- .env
~~~

Không thêm tùy chọn -f ngay từ đầu. Nếu Git từ chối vì file có thay đổi staged hoặc working tree khác với index, hãy xem trạng thái và diff trước khi quyết định.

### Bước 4 — Stage quy tắc ignore

~~~bash
git add .gitignore
~~~

Nếu .gitignore đã được stage cùng các thay đổi khác, hãy kiểm tra kỹ để tránh commit nhầm nội dung không liên quan.

### Bước 5 — Xác minh index không còn file

~~~bash
git ls-files -- .env
git check-ignore -v -- .env
git status --short
git diff --cached --name-status
~~~

Kết quả mong đợi:

- git ls-files không còn liệt kê .env.
- git check-ignore chỉ ra pattern trong .gitignore đang áp dụng cho .env.
- git status cho thấy thao tác xóa đã stage và thay đổi .gitignore.
- git diff --cached --name-status thể hiện .env bị xóa khỏi snapshot tiếp theo.

Không dùng git diff --cached -- .env để chia sẻ kết quả nếu file chứa bí mật, vì diff có thể in nội dung nhạy cảm ra terminal hoặc log.

### Bước 6 — Xác nhận bản local vẫn còn

Trên Bash:

~~~bash
test -f .env && echo "Local file is preserved"
~~~

Trên PowerShell:

~~~powershell
Test-Path -LiteralPath .env
~~~

Nếu file tồn tại, bản local vẫn được giữ. Khi quy tắc ignore áp dụng, Git không liệt kê file này như untracked trong trạng thái mặc định.

### Bước 7 — Commit việc ngừng theo dõi

~~~bash
git diff --cached --name-status
git status
git commit -m "Stop tracking local environment file"
~~~

Commit ghi nhận việc bỏ file khỏi repository và cập nhật quy tắc ignore. File local trên máy hiện tại vẫn tồn tại.

## 4. Đọc trạng thái trước và sau thao tác

### 4.1. Trước khi chạy git rm --cached

Nếu .env đang tracked và clean, lệnh:

~~~bash
git status --short
~~~

có thể không hiển thị .env vì không có thay đổi.

Nếu .env đã modified, trạng thái có thể là:

~~~text
 M .env
~~~

Nếu thay đổi đã staged, trạng thái có thể là:

~~~text
M  .env
~~~

Đừng bỏ qua các trạng thái này. Chúng ảnh hưởng đến việc Git cho phép xóa entry khỏi index mà không cần ép.

### 4.2. Sau git rm --cached nhưng trước commit

Với file đã có trong HEAD, Git thường hiển thị xóa staged:

~~~text
D  .env
~~~

Đây là dấu hiệu index không còn đường dẫn, trong khi working tree vẫn có file nếu nó đã tồn tại trước lệnh.

Nếu file được ignore, lệnh kiểm tra:

~~~bash
git check-ignore -v -- .env
~~~

giúp xác nhận quy tắc áp dụng. Có thể xem trạng thái ignored:

~~~bash
git status --short --ignored
~~~

### 4.3. Sau commit

Sau khi commit thành công:

~~~bash
git status --short
git ls-files -- .env
git check-ignore -v -- .env
~~~

Nếu mọi thứ đúng:

- .env không còn trong index.
- .env vẫn có mặt trên máy hiện tại.
- .env được ignore nếu pattern phù hợp.
- Repository không còn thay đổi pending liên quan đến thao tác này.

Nếu không có quy tắc ignore, file local sẽ xuất hiện như untracked sau commit. Đây là lý do nên chuẩn bị .gitignore cùng lúc nếu mục tiêu là giữ file nhưng không muốn Git tiếp tục liệt kê nó.

## 5. Ngừng theo dõi cả thư mục

### 5.1. Dùng -r để xử lý đệ quy

Nếu một thư mục chứa nhiều file local đã tracked, ví dụ config/local/, có thể gỡ toàn bộ nội dung tracked khỏi index:

~~~bash
git rm -r --cached -- config/local/
~~~

Tùy chọn -r cho phép xử lý các đường dẫn bên trong thư mục theo đệ quy. Tùy chọn -- kết thúc phần tùy chọn để đường dẫn có dấu gạch đầu dòng ở đầu không bị hiểu nhầm là option.

Lệnh giữ các file hiện có trên working tree, nhưng stage việc xóa các đường dẫn đó khỏi snapshot tiếp theo.

### 5.2. Thêm quy tắc ignore cho thư mục

Trong .gitignore:

~~~gitignore
config/local/
~~~

Sau đó stage .gitignore:

~~~bash
git add .gitignore
~~~

Kiểm tra các file cụ thể:

~~~bash
git check-ignore -v -- config/local/settings.yml
git ls-files -- config/local/
git status --short
~~~

Đảm bảo chỉ các file dự định ngừng theo dõi bị loại khỏi index. Nếu trong thư mục có file mẫu cần commit, hãy tạo ngoại lệ cụ thể hoặc đặt file mẫu ở một thư mục khác để quy tắc ignore dễ hiểu.

### 5.3. Chỉ gỡ một nhóm file theo pattern

Có thể dùng pathspec:

~~~bash
git rm --cached -- '*.log'
~~~

Dấu nháy giúp shell chuyển pattern nguyên vẹn cho Git xử lý. Git chỉ gỡ các đường dẫn tracked khớp pathspec trong phạm vi áp dụng.

Trước khi dùng pattern rộng, xem trước danh sách:

~~~bash
git ls-files -- '*.log'
~~~

Không chạy lệnh xóa index theo wildcard mà chưa xác nhận danh sách file khớp.

## 6. Khi Git từ chối git rm --cached

### 6.1. Kiểm tra staged và unstaged changes

Git có các kiểm tra an toàn để tránh vô tình bỏ nội dung chưa được bảo toàn. Khi lệnh báo file có thay đổi hoặc khác biệt giữa HEAD, index và working tree, hãy kiểm tra:

~~~bash
git status --short
git diff -- .env
git diff --cached --name-status
~~~

Nếu file có dữ liệu local cần giữ, hãy xác nhận nó vẫn còn trên đĩa và có bản sao an toàn trước khi thực hiện thao tác ép.

### 6.2. Dùng -f chỉ khi đã hiểu khác biệt

Tùy chọn force:

~~~bash
git rm -f --cached -- .env
~~~

cho phép Git gỡ entry khỏi index ngay cả khi các kiểm tra thông thường phát hiện khác biệt giữa HEAD, index hoặc working tree.

Vì có --cached, mục tiêu vẫn là gỡ khỏi index và giữ file trong working tree. Tuy nhiên, -f bỏ qua một lớp bảo vệ quan trọng; chỉ dùng sau khi đã xem trạng thái, xác nhận đúng đường dẫn và bảo đảm nội dung local được giữ.

Không dùng -f để che một lỗi chưa hiểu rõ hoặc để xóa hàng loạt theo pattern mà chưa kiểm tra danh sách.

### 6.3. Nếu file không có trong index

Nếu lệnh báo pathspec không khớp, kiểm tra:

~~~bash
git ls-files -- .env
git status --short --ignored -- .env
~~~

Một số khả năng:

- File vốn đã untracked: chỉ cần thêm quy tắc ignore.
- File đã được gỡ khỏi index trước đó: không cần gỡ lần nữa.
- Sai tên hoặc sai chữ hoa/thường trên filesystem phân biệt casing.
- Đang đứng trong repository hoặc thư mục khác dự kiến.

Không cần dùng git rm --cached cho một file vốn chưa được tracked.

### 6.4. Nếu bản local đã bị xóa trước đó

Nếu file không còn tồn tại trên đĩa, --cached không thể giữ lại bản local. Trước hết, khôi phục từ bản sao an toàn hoặc nguồn cấu hình được quản lý.

Nếu file vẫn còn trong HEAD và bạn xác định muốn lấy lại phiên bản đã commit, có thể khôi phục working tree:

~~~bash
git restore --source=HEAD --worktree -- .env
~~~

Chỉ dùng khi bạn muốn lấy đúng nội dung từ HEAD. Nếu file có giá trị riêng hoặc chứa credential khác với phiên bản đã commit, không ghi đè; hãy phục hồi từ nguồn an toàn của môi trường.

Sau khi có lại bản local, mới thực hiện quy trình gỡ khỏi index và thêm ignore.

## 7. Phân biệt với các lệnh dễ nhầm

### 7.1. git rm --cached và git restore --staged

Hai lệnh này có mục tiêu khác nhau:

| Lệnh | Tác động đến index | Tác động đến working tree | Kết quả với file đã tracked trong HEAD |
| --- | --- | --- | --- |
| git rm --cached -- file | Gỡ entry khỏi index | Giữ file | Stage việc xóa khỏi snapshot tiếp theo |
| git restore --staged -- file | Khôi phục entry trong index từ HEAD | Giữ file | Bỏ staging, tiếp tục tracked |
| git rm -- file | Gỡ entry khỏi index | Xóa file | Stage việc xóa và xóa bản local |

Nếu chỉ stage nhầm một thay đổi và muốn đưa index trở về HEAD, dùng git restore --staged. Nếu muốn repository ngừng theo dõi file trong các commit tiếp theo, dùng git rm --cached và commit thay đổi.

### 7.2. git rm --cached và git reset HEAD

Trong Git cũ hoặc hướng dẫn cũ, có thể gặp:

~~~bash
git reset HEAD -- .env
~~~

Lệnh này bỏ staging của đường dẫn và đưa index về nội dung trong HEAD. File vẫn được tracked vì entry được khôi phục vào index.

Nó không thay thế git rm --cached khi mục tiêu là ngừng theo dõi file đã commit.

### 7.3. git rm --cached và git update-index --assume-unchanged

Có người dùng:

~~~bash
git update-index --assume-unchanged .env
~~~

để yêu cầu Git tạm giả định file không thay đổi trong một số thao tác kiểm tra. Đây là gợi ý hiệu năng cho Git, không phải cách ngừng theo dõi file. Đường dẫn vẫn nằm trong index và vẫn thuộc repository.

Tương tự, --skip-worktree có mục đích khác, thường được dùng trong một số workflow đặc biệt như sparse checkout. Không dùng các cờ này để thay thế quy trình bỏ theo dõi và ignore.

### 7.4. git rm --cached không xóa lịch sử

Khi commit việc bỏ file khỏi repository, các commit cũ vẫn chứa file. Git chỉ tạo snapshot mới không còn đường dẫn đó.

Nếu file từng chứa mật khẩu, token hoặc private key, xóa khỏi index và commit mới không làm bí mật biến mất khỏi lịch sử. Hãy thu hồi hoặc thay mới credential trước, sau đó đánh giá việc làm sạch lịch sử theo quy trình bảo mật.

## 8. Ảnh hưởng đến các thành viên khác

### 8.1. Commit xóa file sẽ được chia sẻ lên remote

Khi bạn push commit có thay đổi xóa .env, nhánh remote cũng sẽ không còn file này trong snapshot mới.

Các thành viên khác đang ở commit cũ có thể vẫn có .env được Git theo dõi. Khi họ pull commit xóa file, Git có thể xóa bản làm việc đó nếu không có thay đổi local cản trở việc cập nhật.

Vì vậy, trước khi tích hợp commit, nhóm nên:

1. Thông báo file nào sẽ ngừng được theo dõi.
2. Hướng dẫn mọi người sao lưu hoặc chuyển giá trị local sang nơi lưu an toàn.
3. Cung cấp .env.example hoặc tài liệu cấu hình.
4. Hướng dẫn lấy credential từ secret manager hoặc quy trình onboarding.
5. Sau khi pull, tạo lại file local nếu cần.

Không giả định rằng việc bạn giữ được bản local sau git rm --cached có nghĩa các máy khác cũng tự giữ được file khi pull.

### 8.2. Cung cấp file mẫu thay cho file cá nhân

Ví dụ repository trước đây có .env chứa giá trị riêng của từng người. Thay bằng file mẫu:

~~~dotenv
APP_ENV=development
DATABASE_URL=
API_TOKEN=
~~~

Commit file mẫu:

~~~bash
git add .env.example .gitignore
git commit -m "Add environment template"
~~~

Mỗi thành viên tạo .env cục bộ từ mẫu và lấy giá trị thật qua kênh được phê duyệt. Không commit credential thật vào file mẫu.

### 8.3. Giữ quy trình onboarding nhất quán

Tài liệu dự án nên ghi:

- Tên file local cần tạo.
- Các biến môi trường bắt buộc.
- Nguồn lấy giá trị.
- Cách tạo cấu hình từ file mẫu.
- Cách kiểm tra ứng dụng đã đọc cấu hình.
- Cách thay mới hoặc thu hồi credential.

Việc này giúp repository có thể clone và build được mà không cần commit file bí mật.

## 9. Các vị trí ignore và cách kiểm tra

### 9.1. Xem pattern đang áp dụng

~~~bash
git check-ignore -v -- .env
~~~

Đầu ra cho biết file cấu hình chứa pattern và dòng quy tắc áp dụng. Đây là cách tốt để tìm lý do file được ignore.

Nếu muốn kiểm tra cả đường dẫn đã tracked, có thể dùng tùy chọn --no-index:

~~~bash
git check-ignore -v --no-index -- .env
~~~

Tùy chọn này kiểm tra quy tắc ignore mà không loại các đường dẫn đang tracked khỏi kết quả. Nó hữu ích khi điều tra vì sao một pattern đáng lẽ khớp nhưng file vẫn đang được theo dõi.

### 9.2. Xem cấu hình ignore toàn cục

Kiểm tra file ignore toàn cục:

~~~bash
git config --show-origin --get core.excludesFile
~~~

Nếu có giá trị, Git sẽ dùng file đó cho các repository của người dùng hiện tại. File này thường phù hợp cho quy tắc cá nhân như file tạm của editor, không phải chính sách bắt buộc cho mọi thành viên.

### 9.3. Xem trạng thái ignored

~~~bash
git status --short --ignored
~~~

Lệnh hiển thị cả các đường dẫn bị ignore. Dạng ngắn có thể dùng ký hiệu !! cho ignored path.

Mặc định git status không liệt kê tất cả file ignored để tránh làm đầu ra quá dài. Vì vậy, không thấy .env trong git status thông thường chưa đủ để kết luận file đã được ignore; hãy dùng git check-ignore hoặc --ignored.

## 10. Quy trình tổng hợp cho nhóm

Giả sử nhóm cần ngừng theo dõi thư mục config/local/ nhưng mỗi thành viên vẫn cần giữ các file cấu hình trên máy của mình.

**Bước 1 — Kiểm tra các đường dẫn đang tracked**

~~~bash
git ls-files -- config/local/
~~~

**Bước 2 — Thêm quy tắc ignore**

Trong .gitignore:

~~~gitignore
config/local/
~~~

**Bước 3 — Gỡ các file khỏi index**

~~~bash
git rm -r --cached -- config/local/
~~~

**Bước 4 — Stage quy tắc ignore**

~~~bash
git add .gitignore
~~~

**Bước 5 — Kiểm tra**

~~~bash
git ls-files -- config/local/
git check-ignore -v -- config/local/settings.yml
git status --short
git diff --cached --name-status
~~~

**Bước 6 — Xác nhận file local vẫn còn**

Trên Bash:

~~~bash
find config/local -type f
~~~

Trên PowerShell:

~~~powershell
Get-ChildItem -LiteralPath config/local -File -Recurse
~~~

**Bước 7 — Commit**

~~~bash
git commit -m "Stop tracking local configuration"
~~~

**Bước 8 — Thông báo cách tạo cấu hình cho các thành viên**

Cung cấp file mẫu và hướng dẫn lấy giá trị thật từ secret manager hoặc nguồn cấu hình của từng môi trường.

Sau commit, thư mục config/local/ không còn thuộc snapshot Git mới. Bản local trên máy thực hiện lệnh vẫn còn; các máy khác cần lưu bản cấu hình trước khi cập nhật commit xóa.

## 11. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Thêm .gitignore nhưng file vẫn hiện modified | File đã tracked trong index | Dùng git rm --cached rồi commit |
| Chạy git rm --cached nhưng file biến mất trên đĩa | Đã dùng git rm không có --cached hoặc thao tác khác xóa file | Khôi phục từ bản sao hoặc nguồn cấu hình an toàn |
| Pathspec không khớp | File không tracked, sai đường dẫn hoặc đã bị gỡ khỏi index | Kiểm tra git ls-files và tên đường dẫn |
| Git từ chối do local changes | Index hoặc working tree khác trạng thái mà Git cho phép xóa an toàn | Xem git status và diff; bảo toàn nội dung rồi mới cân nhắc -f |
| File xuất hiện như untracked sau commit | Chưa có pattern ignore phù hợp | Thêm quy tắc vào .gitignore hoặc ignore local |
| File vẫn bị theo dõi sau khi thêm pattern | Ignore không tác động đến entry đã có trong index | Gỡ entry bằng git rm --cached |
| Đồng đội mất file sau khi pull | Commit mới đã xóa đường dẫn tracked khỏi repository | Khôi phục cấu hình từ bản sao hoặc secret manager; dùng file mẫu |
| Credential vẫn tìm thấy trong lịch sử | Commit cũ vẫn chứa nội dung | Thu hồi credential và xử lý lịch sử theo quy trình bảo mật |

## 12. Checklist trước khi commit việc ngừng theo dõi

- [ ] Đã xác nhận đúng repository và đúng đường dẫn.
- [ ] File local tồn tại và nội dung cần giữ đã được bảo toàn.
- [ ] Đã kiểm tra staged và unstaged changes.
- [ ] Đã thêm pattern ignore phù hợp nếu không muốn file trở lại như untracked.
- [ ] Đã chạy git rm --cached, có -- nếu cần phân tách pathspec.
- [ ] Đã xác nhận git ls-files không còn liệt kê đường dẫn.
- [ ] Đã dùng git check-ignore -v để xác nhận pattern.
- [ ] Đã kiểm tra git diff --cached --name-status để chỉ commit các thay đổi dự định.
- [ ] Đã chuẩn bị file mẫu hoặc tài liệu cấu hình cho thành viên khác.
- [ ] Nếu file từng chứa secret, credential đã được thu hồi/thay mới theo quy trình.

## 13. Bảng tra cứu nhanh

| Mục tiêu | Lệnh |
| --- | --- |
| Kiểm tra file đang tracked | git ls-files -- .env |
| Gỡ một file khỏi index, giữ bản local | git rm --cached -- .env |
| Gỡ thư mục khỏi index, giữ nội dung local | git rm -r --cached -- config/local/ |
| Gỡ theo pattern | git rm --cached -- '*.log' |
| Ép gỡ khỏi index sau khi đã kiểm tra | git rm -f --cached -- .env |
| Thêm quy tắc ignore | Thêm pattern vào .gitignore |
| Stage file ignore | git add .gitignore |
| Xem pattern ignore áp dụng | git check-ignore -v -- .env |
| Kiểm tra cả quy tắc với file tracked | git check-ignore -v --no-index -- .env |
| Xem trạng thái gồm ignored | git status --short --ignored |
| Xem các đường dẫn đã stage xóa | git diff --cached --name-status |
| Bỏ staging nhưng tiếp tục tracked | git restore --staged -- .env |
| Xóa file khỏi index và working tree | git rm -- .env |

## 14. Tổng kết

git rm --cached gỡ một đường dẫn khỏi index nhưng giữ bản hiện có trên working tree. Với file đã được commit, thao tác này stage việc xóa khỏi snapshot tiếp theo. Sau khi commit, repository không còn theo dõi file; bản local vẫn tồn tại trên máy đã thực hiện lệnh.

Để Git không liệt kê file như untracked và tránh thành viên khác thêm lại nhầm, hãy kết hợp với quy tắc .gitignore phù hợp. Kiểm tra bằng git ls-files, git check-ignore -v, git status và git diff --cached --name-status trước khi commit.

Hãy phân biệt rõ git rm --cached với git restore --staged: lệnh đầu ngừng theo dõi đường dẫn trong snapshot tương lai, còn lệnh sau chỉ bỏ staging và khôi phục entry từ HEAD. Nếu file chứa secret đã được commit, thao tác này không xóa lịch sử; cần thu hồi credential trước và xử lý lịch sử riêng. Khi thay đổi được chia sẻ, hãy hướng dẫn đồng đội sao lưu hoặc tạo lại cấu hình local trước khi họ pull commit xóa file.

