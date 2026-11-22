# Thứ tự áp dụng và giới hạn đưa lại tệp nằm trong thư mục bị bỏ qua

Trong repository thực tế, một quy tắc ignore có thể được khai báo ở nhiều nơi: trong file .gitignore ở thư mục gốc, trong .gitignore của thư mục con, trong cấu hình riêng của repository hoặc trong cấu hình cá nhân trên máy. Khi các quy tắc cùng khớp một đường dẫn, Git phải xác định quy tắc nào có hiệu lực. Ngoài ra, việc bỏ qua cả một thư mục tạo ra một giới hạn quan trọng: bạn không thể chỉ viết một quy tắc phủ định để đưa một tệp con trở lại nếu Git vẫn bỏ qua thư mục cha của nó.

Bài học này giải thích thứ tự ưu tiên của các nguồn ignore, cách quy tắc trong nhiều file .gitignore phối hợp với nhau, cách dùng dấu phủ định và cách thiết kế pattern để giữ lại một số tệp cần thiết trong thư mục chứa nhiều tệp sinh tự động.

Sau bài này, bạn có thể:

- Xác định nguồn ignore nào có quyền ưu tiên cao hơn.
- Giải thích quy tắc cuối cùng khớp đường dẫn quyết định kết quả như thế nào.
- Hiểu phạm vi của pattern trong .gitignore ở thư mục gốc và thư mục con.
- Dùng dấu ! để đưa một tệp trở lại phạm vi theo dõi.
- Nhận biết vì sao không thể đưa lại tệp nằm dưới thư mục cha đang bị bỏ qua.
- Thiết kế pattern để Git vẫn đi vào thư mục cha và nhận diện đúng tệp cần giữ.
- Dùng git check-ignore để tìm quy tắc gây ra trạng thái ignore.
- Phân biệt chức năng ignore với thuộc tính tệp trong .gitattributes.

## 1. Git tìm quy tắc ignore ở những đâu?

Git có nhiều nguồn quy tắc ignore. Với một đường dẫn chưa được theo dõi, các nguồn này có mức ưu tiên khác nhau:

| Mức ưu tiên | Nguồn | Phạm vi |
| --- | --- | --- |
| Cao nhất | Pattern truyền trực tiếp cho lệnh Git có hỗ trợ exclude pattern. | Chỉ áp dụng trong lần gọi lệnh đó. |
| Tiếp theo | Các file .gitignore trong thư mục chứa đường dẫn và những thư mục cha của nó. | Chia sẻ cùng repository; file sâu hơn có thể ghi đè file ở cấp cao hơn. |
| Tiếp theo | .git/info/exclude. | Chỉ repository local hiện tại; không được commit và chia sẻ qua remote. |
| Thấp nhất | File ignore toàn cục được cấu hình bằng core.excludesFile. | Áp dụng cho người dùng trên máy hiện tại. |

Không phải mọi lệnh Git đều nhận pattern trực tiếp trên dòng lệnh; mức đầu tiên chỉ liên quan đến những lệnh có hỗ trợ cơ chế exclude đó. Trong công việc thường ngày, ba nguồn cần quan tâm nhất là .gitignore, .git/info/exclude và file ignore toàn cục.

Xem file ignore toàn cục đang cấu hình:

~~~bash
git config --show-origin --get core.excludesFile
~~~

Xem các giá trị cấu hình có liên quan:

~~~bash
git config --show-origin --get-all core.excludesFile
~~~

File .gitignore thường được commit để cả nhóm dùng chung. .git/info/exclude phù hợp với các tệp riêng của repository trên máy bạn, còn core.excludesFile phù hợp với tệp cá nhân thường bị tạo ở nhiều dự án, ví dụ file tạm của trình soạn thảo.

## 2. Thứ tự ưu tiên giữa nhiều file .gitignore

Một repository có thể có nhiều file .gitignore:

~~~text
project/
+-- .gitignore
+-- src/
|   +-- .gitignore
|   +-- main.java
|   +-- generated/
|       +-- .gitignore
+-- build/
    +-- output.bin
~~~

Pattern trong file .gitignore được áp dụng tương đối với thư mục chứa file đó. Khi cùng một đường dẫn khớp nhiều quy tắc trong các file .gitignore, file nằm sâu hơn trong cây thư mục có mức ưu tiên cao hơn file ở thư mục cha. Trong cùng một file, quy tắc khớp cuối cùng quyết định kết quả.

Ví dụ, file .gitignore ở gốc:

~~~gitignore
*.log
~~~

File src/.gitignore:

~~~gitignore
!debug.log
~~~

Với src/debug.log, pattern ở file src/.gitignore nằm sâu hơn nên có thể phủ định quy tắc *.log từ file gốc, miễn là các thư mục cha không bị ignore. Một file src/trace.log vẫn bị ignore bởi quy tắc ở thư mục gốc vì không có quy tắc sâu hơn đưa nó trở lại.

Nếu trong cùng file có hai quy tắc cùng khớp:

~~~gitignore
*.log
important.log
!important.log
~~~

Quy tắc cuối cùng khớp important.log là !important.log, nên tệp được đưa trở lại. Nếu đổi thứ tự:

~~~gitignore
!important.log
*.log
~~~

Quy tắc *.log nằm sau và khớp lại, vì vậy important.log bị ignore.

Quy tắc cần nhớ: trước tiên xét mức ưu tiên của nguồn, sau đó xét quy tắc khớp trong nguồn đó. Không nên chỉ tìm thấy một dòng !pattern rồi kết luận tệp chắc chắn được theo dõi; vẫn phải kiểm tra xem có quy tắc ưu tiên cao hơn hoặc quy tắc sâu hơn khớp lại hay không.

## 3. Phạm vi của pattern theo vị trí file

Một pattern không có dấu gạch chéo ở giữa thường có thể khớp tên ở bất kỳ cấp thư mục nào bên dưới file .gitignore chứa pattern đó.

Ví dụ trong .gitignore ở gốc:

~~~gitignore
*.tmp
~~~

Pattern này có thể bỏ qua:

~~~text
draft.tmp
src/cache.tmp
src/generated/output.tmp
~~~

Nếu pattern có dấu gạch chéo ở đầu hoặc có dấu gạch chéo ở giữa, nó được hiểu tương đối với thư mục chứa file .gitignore:

~~~gitignore
/build/
src/generated/
~~~

Trong file .gitignore ở gốc:

- /build/ chỉ khớp thư mục build ngay tại gốc repository.
- src/generated/ chỉ khớp đường dẫn src/generated tính từ gốc repository.

Trong file src/.gitignore, pattern /generated/ lại chỉ khớp thư mục src/generated, vì gốc của pattern là thư mục src.

Dấu gạch chéo ở cuối biểu thị chỉ khớp thư mục:

~~~gitignore
cache/
~~~

Pattern này khớp các thư mục tên cache và nội dung bên trong chúng, không phải tệp thường tên cache.

Một vài pattern minh họa:

| Pattern | Phạm vi khớp |
| --- | --- |
| *.class | Tệp có đuôi .class ở bất kỳ cấp nào bên dưới file .gitignore. |
| /dist/ | Thư mục dist ngay cạnh file .gitignore. |
| docs/*.pdf | Tệp PDF trực tiếp trong docs, không khớp các cấp sâu hơn. |
| **/cache/ | Thư mục cache ở bất kỳ cấp nào bên dưới vị trí đặt pattern. |
| logs/** | Mọi nội dung bên trong thư mục logs, kể cả các cấp con. |

Các pattern có thể dùng dấu sao kép để mô tả nhiều cấp thư mục. Khi pattern phức tạp, hãy thử với git check-ignore thay vì chỉ suy luận bằng mắt.

## 4. Dấu phủ định ! đưa tệp trở lại như thế nào?

Một pattern bắt đầu bằng dấu ! phủ định một quy tắc ignore trước đó. Ví dụ:

~~~gitignore
*.log
!keep.log
~~~

Tất cả tệp .log bị bỏ qua, ngoại trừ keep.log trong phạm vi của file .gitignore đó.

Có thể dùng đường dẫn cụ thể:

~~~gitignore
/logs/*
!/logs/release.log
~~~

Pattern /logs/* bỏ qua các mục trực tiếp bên trong logs. Nó không bỏ qua chính thư mục logs. Vì thư mục cha vẫn được Git đi vào, quy tắc !/logs/release.log có thể đưa tệp release.log trở lại.

Dấu ! không tự theo dõi một tệp. Nó chỉ làm cho tệp không còn bị ignore bởi các pattern có mức ưu tiên tương ứng. Tệp vẫn cần được Git nhìn thấy và được thêm bằng git add nếu chưa được theo dõi.

Nếu tên tệp bắt đầu bằng ký tự # hoặc !, cần escape ký tự đầu bằng dấu gạch chéo ngược để phân biệt tên tệp với comment hoặc pattern phủ định. Khoảng trắng ở cuối pattern cũng có quy tắc xử lý riêng; nếu thực sự muốn khớp khoảng trắng cuối tên, hãy escape khoảng trắng đó.

## 5. Giới hạn quan trọng: không thể đưa lại tệp nếu thư mục cha bị ignore

Đây là giới hạn thường gây nhầm lẫn nhất của .gitignore. Nếu một thư mục bị ignore, Git thường không đi vào thư mục đó để tìm các tệp bên trong. Vì vậy, một quy tắc phủ định nhắm tới tệp con không có tác dụng nếu thư mục cha vẫn đang bị bỏ qua.

Ví dụ không hoạt động như mong muốn:

~~~gitignore
/artifacts/
!/artifacts/release.json
~~~

Bạn muốn bỏ qua toàn bộ thư mục artifacts nhưng giữ lại release.json. Tuy nhiên, /artifacts/ bỏ qua chính thư mục cha. Git không đi vào đó để phát hiện release.json, nên dòng phủ định phía sau không thể đưa tệp trở lại.

Hãy hình dung:

~~~text
Repository
|
+-- artifacts/       <- bị ignore
|   +-- debug.log
|   +-- package.zip
|   +-- release.json <- quy tắc phủ định không được xét tới
~~~

Git bỏ qua thư mục artifacts ngay ở cấp cha. Nó không duyệt nội dung của thư mục này để áp dụng quy tắc cho release.json.

Đây là giới hạn có chủ đích để Git không phải duyệt mọi tệp trong các cây thư mục đã bị loại trừ. Vì vậy, muốn giữ lại tệp con, cần để Git tiếp tục đi vào mọi thư mục cha trên đường dẫn đó.

## 6. Cách viết pattern để giữ lại một tệp trực tiếp trong thư mục

Nếu bạn muốn bỏ qua mọi nội dung trực tiếp trong artifacts nhưng giữ release.json, hãy bỏ qua các mục bên trong thay vì bỏ qua chính thư mục:

~~~gitignore
/artifacts/*
!/artifacts/release.json
~~~

Pattern /artifacts/* khớp các mục bên trong thư mục artifacts, còn thư mục artifacts vẫn có thể được duyệt. Dòng phủ định đưa release.json trở lại.

Kết quả:

~~~text
Repository
|
+-- artifacts/          <- không bị ignore
|   +-- debug.log       <- bị ignore
|   +-- package.zip     <- bị ignore
|   +-- release.json    <- được đưa lại
~~~

Nếu muốn giữ một thư mục con cùng một tệp bên trong, cần đưa cả thư mục con trở lại trước:

~~~gitignore
/artifacts/*
!/artifacts/release/
/artifacts/release/*
!/artifacts/release/manifest.json
~~~

Kết quả mong muốn:

~~~text
artifacts/
|   +-- debug.log                 <- ignore
|   +-- package.zip               <- ignore
|   +-- release/                  <- được đưa lại để Git duyệt
|       +-- build.log             <- ignore
|       +-- manifest.json         <- được đưa lại
~~~

Nếu manifest.json nằm sâu hơn một cấp, mọi thư mục trung gian cũng phải được đưa lại. Ví dụ giữ artifacts/release/meta/manifest.json:

~~~gitignore
/artifacts/*
!/artifacts/release/
/artifacts/release/*
!/artifacts/release/meta/
/artifacts/release/meta/*
!/artifacts/release/meta/manifest.json
~~~

Mỗi thư mục cha bị một pattern ignore phải có quy tắc phủ định tương ứng trước khi Git có thể xét tới tệp nằm bên trong. Trong thực tế, nếu cấu trúc thư mục có nhiều cấp và thay đổi thường xuyên, nên thiết kế pattern để không ignore thư mục cha ngay từ đầu; cách đó thường dễ đọc và ít lỗi hơn.

## 7. Phân biệt hai cách ignore thư mục

Hai pattern sau nhìn gần giống nhau nhưng có hành vi khác nhau:

~~~gitignore
/build/
~~~

và:

~~~gitignore
/build/*
~~~

Pattern /build/ bỏ qua chính thư mục build. Git không duyệt các mục bên trong, nên không thể chỉ dùng !/build/keep.txt để đưa một tệp con trở lại.

Pattern /build/* bỏ qua các mục trực tiếp bên trong build nhưng không bỏ qua chính thư mục build. Điều này cho phép các quy tắc sau đó đưa một mục cụ thể trở lại:

~~~gitignore
/build/*
!/build/keep.txt
~~~

Nếu muốn đưa một thư mục con trở lại, phải phủ định thư mục đó rồi quyết định các mục bên trong:

~~~gitignore
/build/*
!/build/reports/
/build/reports/*
!/build/reports/summary.txt
~~~

Không nên thay mọi pattern kết thúc bằng dấu / thành dấu * một cách máy móc. Chọn cách viết theo đúng mục tiêu:

- Nếu không cần giữ bất kỳ nội dung nào, ignore cả thư mục bằng /build/.
- Nếu cần chọn lọc nội dung bên trong, giữ thư mục cha có thể duyệt và ignore các mục con bằng /build/*.

## 8. Quy tắc trong .gitignore con có thể ghi đè quy tắc ở gốc, nhưng không vượt qua thư mục cha bị ignore

Một file .gitignore trong thư mục con có thể điều chỉnh quy tắc ở gốc cho các đường dẫn bên dưới nó, nếu Git có thể đi vào thư mục con.

Ví dụ:

File .gitignore ở gốc:

~~~gitignore
*.log
~~~

File src/.gitignore:

~~~gitignore
!debug.log
~~~

src/debug.log được đưa lại vì file ignore ở src có mức ưu tiên cao hơn file gốc.

Nhưng ví dụ sau không hoạt động:

File .gitignore ở gốc:

~~~gitignore
/src/
~~~

File src/.gitignore:

~~~gitignore
!debug.log
~~~

Git không duyệt src vì thư mục này đã bị ignore. Do đó, file src/.gitignore không được đọc để áp dụng quy tắc cho debug.log.

Nếu cần giữ chọn lọc tệp trong src, sửa quy tắc ở gốc để không ignore chính thư mục:

~~~gitignore
/src/*
!/src/debug.log
~~~

Hãy đặt các quy tắc tại nơi dễ hiểu nhất và tránh tạo nhiều file .gitignore có các ngoại lệ chồng chéo nếu không thực sự cần.

## 9. Xác định chính xác quy tắc nào đang ignore một đường dẫn

Khi một tệp không xuất hiện trong git status, đừng vội thêm nhiều dòng phủ định. Trước hết, hỏi Git quy tắc nào đang khớp:

~~~bash
git check-ignore -v path/to/file
~~~

Tùy chọn -v hiển thị nguồn quy tắc, số dòng và pattern đã khớp. Ví dụ kết quả có thể cho biết file .gitignore ở gốc, dòng 12, pattern /artifacts/ đã bỏ qua đường dẫn.

Để kiểm tra cả tệp đã được theo dõi, có thể dùng:

~~~bash
git check-ignore -v --no-index path/to/file
~~~

--no-index yêu cầu lệnh xem xét quy tắc ignore kể cả khi đường dẫn đã nằm trong index. Mặc định, tệp đã được theo dõi không bị cơ chế ignore tác động theo cách của tệp chưa được theo dõi.

Muốn kiểm tra nhiều đường dẫn:

~~~bash
git check-ignore -v path/to/file path/to/another-file
~~~

Nếu không có kết quả, đường dẫn có thể không khớp quy tắc ignore. Hãy kiểm tra xem tệp đã được lưu xuống đĩa chưa, đang nằm trong repository nào và có bị loại khỏi phạm vi tìm kiếm bởi một thư mục cha hay không.

## 10. .gitignore không bỏ theo dõi tệp đã được commit

Quy tắc ignore chủ yếu ảnh hưởng tới các tệp chưa được theo dõi. Nếu một tệp đã được commit, thêm tên tệp vào .gitignore không tự xóa tệp khỏi index và không ngừng theo dõi nó.

Ví dụ file .env đã được commit. Sau đó bạn thêm:

~~~gitignore
.env
~~~

Git vẫn tiếp tục theo dõi các thay đổi của .env. Nếu muốn giữ file trên máy nhưng ngừng theo dõi trong commit tiếp theo:

~~~bash
git rm --cached .env
git add .gitignore
git commit -m "Stop tracking local environment file"
~~~

--cached bỏ đường dẫn khỏi index nhưng giữ tệp trong working tree. Sau commit, các bản clone hoặc checkout mới sẽ không nhận file đó từ repository nữa, còn máy hiện tại vẫn giữ file local. Nếu file từng chứa mật khẩu hoặc token, xóa khỏi index ở commit mới không loại bỏ bí mật khỏi lịch sử cũ; cần xử lý thông tin bí mật và lịch sử theo quy trình bảo mật của nhóm.

## 11. Vai trò của .git/info/exclude và ignore toàn cục

Không phải mọi tệp sinh ra đều cần quy tắc trong .gitignore được commit. Ví dụ, một thành viên có thể muốn bỏ qua file workspace riêng của IDE nhưng nhóm vẫn muốn người khác theo dõi loại file đó.

Trong trường hợp này, có thể thêm pattern vào .git/info/exclude:

~~~gitignore
# Chỉ áp dụng cho repository trên máy này
.idea/workspace.xml
local-notes.txt
~~~

Hoặc cấu hình file ignore toàn cục:

~~~bash
git config --global core.excludesFile ~/.config/git/ignore
~~~

File ignore toàn cục có thể chứa:

~~~gitignore
.DS_Store
Thumbs.db
*.swp
~~~

Các nguồn này có mức ưu tiên thấp hơn .gitignore của repository. Vì vậy, một quy tắc ignore toàn cục không thể dùng dấu ! để đưa lại tệp mà .gitignore của dự án đã bỏ qua. Nếu cần ngoại lệ cho cả nhóm, hãy sửa quy tắc trong .gitignore được chia sẻ.

## 12. Đừng nhầm .gitignore với .gitattributes

Hai file có tên gần giống nhưng giải quyết hai vấn đề khác nhau:

| File | Vai trò | Ví dụ |
| --- | --- | --- |
| .gitignore | Quyết định đường dẫn chưa được theo dõi nào nên bị bỏ qua. | Bỏ qua build/, *.log hoặc file .env local. |
| .gitattributes | Gán thuộc tính cho đường dẫn được Git quản lý hoặc xử lý. | Chọn chuẩn hóa dòng cuối bằng text/eol, driver diff/merge hoặc filter. |

Ví dụ .gitattributes:

~~~gitattributes
*.sh text eol=lf
*.png binary
*.md text
~~~

Các thuộc tính này ảnh hưởng cách Git xử lý nội dung tệp, chẳng hạn chuẩn hóa line ending hoặc xem tệp là binary trong diff. Chúng không phải quy tắc đưa một tệp bị ignore trở lại và không thay thế .gitignore.

Nếu một tệp bị ignore vì thư mục cha, thêm thuộc tính cho nó trong .gitattributes không làm Git bắt đầu duyệt thư mục đó. Trước hết cần xử lý quy tắc ignore để đường dẫn được nhận diện; sau đó mới áp dụng thuộc tính phù hợp.

## 13. Quy trình chẩn đoán và sửa một ngoại lệ ignore

Giả sử repository bỏ qua thư mục generated nhưng nhóm cần giữ file generated/manifest.json:

~~~text
project/
|-- .gitignore
+-- generated/
|   +-- cache.bin
|   +-- preview.log
|   +-- manifest.json
~~~

Bước 1: kiểm tra trạng thái và quy tắc:

~~~bash
git status --short
git check-ignore -v generated/manifest.json
~~~

Bước 2: nếu quy tắc hiện tại là:

~~~gitignore
/generated/
~~~

thì thay bằng:

~~~gitignore
/generated/*
!/generated/manifest.json
~~~

Bước 3: kiểm tra lại:

~~~bash
git check-ignore -v generated/cache.bin
git check-ignore -v generated/preview.log
git status --short
~~~

manifest.json cần xuất hiện như tệp chưa được theo dõi nếu nó chưa từng được add. cache.bin và preview.log vẫn bị ignore. Nếu manifest.json nằm trong một thư mục con, đưa từng thư mục cha cần thiết trở lại trước khi phủ định tệp.

Bước 4: thêm đúng tệp cần theo dõi và kiểm tra staging:

~~~bash
git add .gitignore generated/manifest.json
git status --short
git diff --cached
~~~

Chỉ commit sau khi staged diff chứa đúng file quy tắc và tệp ngoại lệ cần chia sẻ.

## 14. Những lỗi thường gặp

### Viết !file nhưng tệp vẫn bị ignore

Kiểm tra thư mục cha có bị ignore hay không. Nếu có, thay quy tắc bỏ qua cả thư mục bằng quy tắc chỉ bỏ qua các mục bên trong, rồi đưa tệp cần giữ trở lại.

### Quy tắc ở file con không có tác dụng

Kiểm tra thư mục chứa file .gitignore con có bị ignore bởi file cha hay không. Git không đi vào thư mục bị loại trừ để đọc các quy tắc bên trong.

### Dấu ! không ghi đè được quy tắc mong muốn

Kiểm tra thứ tự các dòng trong cùng file và mức ưu tiên của file chứa pattern. Quy tắc khớp cuối cùng trong cùng mức có hiệu lực; file .gitignore sâu hơn có thể ghi đè file ở cấp cha.

### File đã commit vẫn hiện thay đổi dù đã thêm vào .gitignore

Đây là hành vi bình thường. Dùng git rm --cached nếu mục tiêu là ngừng theo dõi file nhưng giữ nó trên máy.

### Ignore toàn cục làm thành viên khác có kết quả khác

Kiểm tra core.excludesFile và .git/info/exclude trên máy. Nếu quy tắc cần chia sẻ cho cả nhóm, đưa nó vào .gitignore của repository thay vì dựa vào cấu hình cá nhân.

## 15. Ghi nhớ

- Nguồn ignore có thứ tự ưu tiên: pattern của lệnh nếu được hỗ trợ, .gitignore theo cấp thư mục, .git/info/exclude rồi file ignore toàn cục.
- Trong các file .gitignore, file sâu hơn có thể ghi đè file ở cấp cha; trong cùng file, quy tắc khớp cuối cùng quyết định.
- Pattern được hiểu tương đối với vị trí file .gitignore chứa nó.
- Dấu ! phủ định một quy tắc ignore nhưng không thể đưa tệp trở lại nếu thư mục cha của nó vẫn bị ignore.
- Để giữ một số tệp trong thư mục lớn, thường ignore các mục bên trong bằng /dir/* thay vì ignore chính /dir/.
- Với đường dẫn sâu, phải để Git đi vào từng thư mục cha trên đường dẫn đó.
- Dùng git check-ignore -v để tìm nguồn, số dòng và pattern đã khớp.
- .gitignore không ngừng theo dõi tệp đã được commit; dùng git rm --cached khi cần bỏ khỏi index mà giữ tệp local.
- .gitattributes điều khiển cách Git xử lý nội dung tệp; nó không thay thế cơ chế ignore.

Khi hiểu thứ tự ưu tiên và giới hạn duyệt thư mục, bạn có thể viết quy tắc ignore dễ dự đoán, giữ lại đúng các tệp cần thiết và tránh vô tình đưa dữ liệu sinh tự động vào repository.
