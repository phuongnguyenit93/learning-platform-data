# So sánh tệp nhị phân và sử dụng git difftool

Git quản lý nội dung file dưới dạng blob, tức là chuỗi byte. Khi tạo diff, Git cần quyết định có thể đọc nội dung như văn bản hay nên coi đó là dữ liệu nhị phân. Với file văn bản, Git thường hiển thị các dòng thêm, xóa và sửa. Với ảnh, PDF, archive, font hoặc file thực thi, một bản diff dạng dòng thường không có ý nghĩa. Khi đó bạn cần biết cách xem metadata, tạo binary patch hoặc mở hai phiên bản bằng công cụ so sánh phù hợp.

Bài học này trình bày cách Git nhận diện file nhị phân, các lệnh diff hữu ích khi nội dung không thể hiển thị như văn bản, cách tạo và áp dụng binary patch, cách cấu hình text conversion để so sánh biểu diễn văn bản của file, và cách dùng git difftool để mở công cụ bên ngoài. Mục tiêu là chọn đúng cách so sánh theo loại dữ liệu và hiểu chính xác công cụ đang cho bạn thấy điều gì.

## 1. Git lưu file nhị phân như thế nào?

Git không có một loại object riêng tên là binary file. Nội dung của file, dù là source code, ảnh PNG, PDF hay archive ZIP, đều được lưu trong blob dưới dạng byte. Tree ghi tên đường dẫn, mode và object ID trỏ tới blob đó.

Khái niệm văn bản hay nhị phân chủ yếu ảnh hưởng tới cách Git tạo và hiển thị diff:

- Với nội dung văn bản, Git có thể so sánh theo dòng và tạo patch dễ đọc.
- Với nội dung nhị phân, Git thường không cố diễn giải byte thành dòng văn bản.
- Với một số định dạng nhị phân, công cụ chuyên dụng có thể trích xuất metadata hoặc chuyển nội dung thành dạng văn bản để hỗ trợ review.

Ví dụ, một repository có thể chứa:

~~~text
design/
  logo.png
  architecture.pdf
assets/
  product-demo.mp4
  icon-font.woff2
release/
  application.zip
~~~

Các file này vẫn được Git lưu và versioning như những file khác. Điều khác biệt nằm ở cách xem thay đổi và cách review chúng.

## 2. Git nhận diện nội dung nhị phân

Git thường dùng heuristic để nhận biết nội dung có byte NUL hoặc dấu hiệu không phù hợp với văn bản. Ngoài heuristic, repository có thể khai báo rõ thuộc tính cho từng pattern trong file .gitattributes.

Ví dụ:

~~~gitattributes
# Text files
*.java text
*.md text
*.yml text

# Binary files
*.png binary
*.jpg binary
*.pdf binary
*.zip binary
*.woff2 binary
*.mp4 binary
~~~

Attribute macro binary tương đương với việc tắt xử lý text, diff và merge thông thường cho đường dẫn khớp pattern. Điều này giúp Git không cố tạo line diff cho file vốn không phù hợp với cách so sánh văn bản.

Kiểm tra attribute đang áp dụng:

~~~bash
git check-attr -a -- design/logo.png
git check-attr -a -- architecture.pdf
~~~

Lệnh cho biết các attribute Git tính cho đường dẫn. Nếu muốn xem nguồn cấu hình và quy tắc trong file, mở các file .gitattributes liên quan từ root tới thư mục con.

Một số điểm cần nhớ:

- Attribute được áp dụng theo đường dẫn và có thể được khai báo ở nhiều file .gitattributes.
- Quy tắc ở thư mục con có thể bổ sung hoặc ghi đè quy tắc từ thư mục cha.
- Dòng quy tắc xuất hiện sau có thể thay đổi kết quả cho pattern khớp.
- Attribute không thay đổi byte đã lưu trong commit; nó thay đổi cách Git xử lý đường dẫn ở các thao tác phù hợp.

## 3. Xem diff mặc định của file nhị phân

Giả sử bạn đã thay ảnh logo và muốn xem thay đổi:

~~~bash
git diff -- design/logo.png
~~~

Nếu Git nhận diện file là binary, output thường thông báo hai phiên bản khác nhau thay vì hiển thị các dòng thay đổi:

~~~text
Binary files a/design/logo.png and b/design/logo.png differ
~~~

Đây không phải lỗi. Git đang thông báo nội dung blob khác nhau nhưng không thể biểu diễn hữu ích bằng line diff.

Với file đã stage, xem thay đổi so với HEAD:

~~~bash
git diff --cached -- design/logo.png
~~~

Với hai commit:

~~~bash
git diff v1.2.0 v1.3.0 -- design/logo.png
~~~

Các lệnh trên trả lời câu hỏi file có thay đổi hay không, nhưng không cho biết trực quan vùng ảnh nào đổi, trang PDF nào khác hoặc nội dung archive nào được thêm.

## 4. Dùng thống kê và metadata khi không thể đọc nội dung

Khi diff nhị phân không hiển thị nội dung, bạn vẫn có thể xem phạm vi thay đổi.

### 4.1. Thống kê theo file

~~~bash
git diff --stat HEAD~1 HEAD
git diff --stat -- design/
~~~

Output cho biết file nào thay đổi và kích thước tương đối của thay đổi. Với file binary, Git không thể tính số dòng thêm/xóa theo cách thông thường.

### 4.2. Thống kê dạng máy đọc

~~~bash
git diff --numstat HEAD~1 HEAD
~~~

Với file nhị phân, hai cột số dòng thường được hiển thị là dấu gạch ngang:

~~~text
-       -       design/logo.png
~~~

Dấu gạch ngang có nghĩa Git không cung cấp số dòng thêm và xóa cho file đó.

### 4.3. Xem tên và trạng thái đường dẫn

~~~bash
git diff --name-status HEAD~1 HEAD
~~~

Một số trạng thái thường gặp:

| Ký hiệu | Ý nghĩa |
|---|---|
| A | Thêm file |
| M | Sửa file |
| D | Xóa file |
| R | Đổi tên |
| C | Sao chép |
| T | Thay đổi loại hoặc mode |

### 4.4. Xem metadata thay đổi

~~~bash
git diff --summary HEAD~1 HEAD
git diff --raw HEAD~1 HEAD
~~~

Summary có thể hiển thị file được tạo, xóa, đổi tên hoặc thay đổi mode. Raw output hiển thị mode cũ/mới, object ID cũ/mới và trạng thái thay đổi. Các thông tin này hữu ích khi review binary asset hoặc điều tra vì sao một file được xem là thay đổi.

## 5. Phân biệt thay đổi nội dung và thay đổi metadata

Một file có thể được xem là thay đổi vì nội dung byte đổi, nhưng cũng có thể thay đổi mode hoặc đường dẫn.

Ví dụ:

- Ảnh được xuất lại với cùng hình ảnh nhưng metadata EXIF hoặc timestamp bên trong khác.
- PDF được tạo lại với cùng nội dung hiển thị nhưng metadata, ID hoặc thứ tự object khác.
- File thực thi đổi executable bit.
- Một asset được đổi tên nhưng byte không đổi.
- Archive được đóng gói lại với thứ tự entry hoặc timestamp khác.

Dùng các lệnh sau để điều tra:

~~~bash
git diff --summary BASE..HEAD
git diff --raw BASE..HEAD
git diff --name-status BASE..HEAD
~~~

Nếu file được rename, Git thường phát hiện rename dựa trên mức độ tương đồng nội dung; tên file thay đổi không nhất thiết có nghĩa blob đã thay đổi. Có thể xem chi tiết rename bằng:

~~~bash
git diff --summary -M BASE..HEAD
git diff --name-status -M BASE..HEAD
~~~

Nếu cần xem object ID của file ở từng commit:

~~~bash
git rev-parse 'BASE:design/logo.png'
git rev-parse 'HEAD:design/logo.png'
~~~

Nếu object ID giống nhau, hai snapshot tham chiếu cùng blob. Nếu khác nhau, byte nội dung đã lưu khác nhau, kể cả khi ảnh nhìn bằng mắt có vẻ giống hệt.

## 6. Vì sao không nên ép mọi file binary thành text diff?

Git hỗ trợ tùy chọn --text (hoặc -a) để coi mọi file là văn bản:

~~~bash
git diff --text -- path/to/archive.zip
~~~

Tùy chọn này hữu ích trong trường hợp file thực chất là văn bản nhưng Git nhận diện nhầm, hoặc bạn đang điều tra dữ liệu có cấu trúc dạng text. Tuy nhiên, với ảnh, video, archive hoặc executable, output có thể chứa byte điều khiển, ký tự không in được hoặc lượng dữ liệu khổng lồ.

Không nên dùng --text như cách review binary thông thường vì:

- Output có thể khó đọc hoặc làm terminal hiển thị bất thường.
- Các dòng không có ý nghĩa với cấu trúc định dạng file.
- Diff theo dòng không thể giải thích thay đổi trực quan hoặc logic bên trong file.
- Có thể tạo log và patch rất lớn.

Nếu cần buộc Git xử lý một file như văn bản, trước tiên hãy xác nhận định dạng thực sự là text và cân nhắc khai báo attribute text phù hợp. Không nên thay đổi attribute của định dạng binary chỉ để tránh thông báo “Binary files differ”.

## 7. Tạo binary patch bằng git diff --binary

Diff mặc định của binary file thường chỉ báo khác biệt. Nếu cần đóng gói thay đổi binary vào patch để chuyển sang repository khác, dùng --binary:

~~~bash
git diff --binary BASE HEAD -- design/logo.png > logo-change.patch
~~~

Tùy chọn --binary yêu cầu Git tạo biểu diễn binary patch có thể áp dụng bằng git apply. Với thay đổi văn bản trong cùng patch, Git vẫn tạo diff văn bản thông thường.

Kiểm tra patch trước khi áp dụng:

~~~bash
git apply --stat logo-change.patch
git apply --check logo-change.patch
~~~

Nếu kiểm tra thành công và bạn muốn áp dụng:

~~~bash
git apply logo-change.patch
~~~

Một số lưu ý:

- Binary patch lưu dữ liệu cần thiết để tái tạo phiên bản đích; kích thước patch có thể lớn.
- Patch cần áp dụng trên trạng thái phù hợp với base đã tạo ra nó.
- --check chỉ kiểm tra khả năng áp dụng, không xác minh ý nghĩa của nội dung file.
- git apply cập nhật working tree theo patch; nó không tự tạo commit.
- Nếu patch chứa đường dẫn hoặc thay đổi ngoài phạm vi mong muốn, hãy đọc thống kê và kiểm tra nội dung trước khi áp dụng.

Để tạo patch cho toàn bộ thay đổi tracked giữa hai commit:

~~~bash
git diff --binary BASE HEAD > release-assets.patch
~~~

Để áp dụng vào repository đích:

~~~bash
git apply --check release-assets.patch
git apply release-assets.patch
~~~

Sau khi áp dụng, kiểm tra lại:

~~~bash
git status --short
git diff --stat
~~~

Không gửi patch qua kênh công khai nếu nó chứa binary asset, dữ liệu nội bộ hoặc nội dung không được phép chia sẻ.

## 8. Khi nào cần công cụ so sánh chuyên dụng?

Không có một cách hiển thị duy nhất phù hợp cho mọi binary file. Chọn công cụ dựa trên định dạng và câu hỏi review:

| Loại file | Câu hỏi thường gặp | Công cụ phù hợp |
|---|---|---|
| Ảnh PNG/JPEG/SVG rasterized | Pixel, vùng ảnh hoặc kích thước nào đổi? | Image diff, overlay, side-by-side viewer |
| PDF | Trang nào đổi, văn bản hay bố cục thay đổi? | PDF compare hoặc renderer theo trang |
| DOCX/ODT | Văn bản, bảng và cấu trúc tài liệu đổi ra sao? | Office document compare hoặc chuyển sang text |
| ZIP/JAR | Entry nào được thêm, xóa hoặc thay thế? | Archive listing, checksum và binary viewer |
| Font | Glyph, bảng font hoặc metadata nào đổi? | Font inspection tool |
| Audio/video | Nội dung media, codec, duration hay metadata thay đổi? | Media inspector hoặc công cụ so sánh theo định dạng |
| Executable | Byte, section, symbol hoặc dependency nào đổi? | Hex diff, binary analysis và package inspection |

Một công cụ có thể cho thấy hai file khác nhau nhưng không chứng minh thay đổi là đúng. Ví dụ, hai ảnh khác pixel có thể là thay đổi thiết kế hợp lệ hoặc lỗi xuất ảnh; cần review theo yêu cầu sản phẩm.

## 9. git difftool là gì?

git difftool là giao diện tích hợp Git với một chương trình diff bên ngoài. Thay vì in diff ra terminal, Git chuẩn bị hai phiên bản file và gọi công cụ được cấu hình để hiển thị chúng.

Difftool sử dụng cùng cách xác định hai phía so sánh như git diff:

| Lệnh | Hai phía được so sánh |
|---|---|
| git difftool -- file | Index và working tree |
| git difftool --cached -- file | HEAD và index |
| git difftool A B -- file | Tree của A và tree của B |
| git difftool A..B -- file | Snapshot A và snapshot B |
| git difftool --dir-diff A B -- folder/ | Hai cây thư mục theo phạm vi chỉ định |

Difftool chỉ hỗ trợ xem và so sánh. Nó không tự tạo commit, không tự merge và không giải quyết conflict. Khi cần giải quyết xung đột merge, hãy tìm hiểu git mergetool và workflow xử lý conflict riêng.

## 10. Xem các công cụ diff được Git hỗ trợ

Chạy:

~~~bash
git difftool --tool-help
~~~

Git liệt kê tên các công cụ mà bản cài đặt hiện tại biết cách gọi. Danh sách thực tế phụ thuộc hệ điều hành, chương trình đã cài và cấu hình Git.

Một số công cụ thường gặp:

- vimdiff: so sánh trong Vim.
- meld: giao diện đồ họa để xem hai hoặc nhiều file.
- kdiff3: so sánh và hỗ trợ hợp nhất nội dung.
- bc: giao diện Beyond Compare trên các môi trường được hỗ trợ.
- opendiff: công cụ FileMerge trên macOS.
- p4merge: công cụ so sánh của Perforce.
- winmerge: công cụ WinMerge khi Git được cấu hình để gọi nó.

Tên công cụ khả dụng có thể khác giữa các bản Git. Hãy dùng đúng tên mà --tool-help hiển thị, không giả định mọi công cụ đều được cài sẵn.

## 11. Chọn công cụ cho một lần so sánh

Bạn có thể chỉ định tool trực tiếp mà không đổi cấu hình mặc định:

~~~bash
git difftool --tool=meld HEAD~1 HEAD -- design/logo.png
~~~

Ví dụ này yêu cầu Git mở Meld để so sánh file logo giữa hai commit.

So sánh thay đổi chưa stage trong working tree:

~~~bash
git difftool --tool=meld -- design/logo.png
~~~

So sánh nội dung đã stage với HEAD:

~~~bash
git difftool --cached --tool=meld -- design/logo.png
~~~

So sánh toàn bộ thư mục asset:

~~~bash
git difftool --dir-diff --tool=meld HEAD~1 HEAD -- design/
~~~

Tùy chọn --dir-diff yêu cầu Git tạo một phép so sánh theo thư mục. Công cụ được chọn cần hỗ trợ directory comparison để hiển thị tốt. Nếu tool chỉ hỗ trợ so sánh từng file, dùng lệnh difftool thông thường theo file hoặc để Git mở lần lượt các file thay đổi.

## 12. Cấu hình công cụ mặc định cho repository

Nếu thường xuyên dùng cùng một công cụ, có thể cấu hình trong repository hiện tại:

~~~bash
git config --local diff.tool meld
~~~

Sau đó gọi:

~~~bash
git difftool HEAD~1 HEAD -- design/logo.png
~~~

Git dùng tool đã cấu hình nếu không có tùy chọn --tool chỉ định công cụ khác.

Có thể điều khiển việc Git hỏi xác nhận trước khi mở từng file:

~~~bash
git config --local difftool.prompt false
~~~

Khi prompt được tắt, Git gọi công cụ mà không hỏi trước từng lần. Nếu muốn giữ prompt, xóa cấu hình local đó:

~~~bash
git config --local --unset difftool.prompt
~~~

Xem cấu hình cùng nguồn:

~~~bash
git config --show-origin --show-scope --get diff.tool
git config --show-origin --show-scope --get difftool.prompt
~~~

Cấu hình --local chỉ áp dụng cho repository hiện tại. Nếu muốn dùng mặc định cho mọi repository của người dùng, có thể chọn --global, nhưng hãy hiểu rằng thay đổi đó ảnh hưởng tới các dự án khác.

## 13. Cấu hình custom difftool command

Nếu công cụ của bạn không nằm trong danh sách tool có sẵn, Git cho phép khai báo lệnh riêng. Ví dụ, một chương trình giả định tên binary-viewer nhận hai đường dẫn file:

~~~bash
git config --local diff.tool binaryviewer
git config --local difftool.binaryviewer.cmd 'binary-viewer "$LOCAL" "$REMOTE"'
~~~

Sau đó:

~~~bash
git difftool --tool=binaryviewer -- path/to/file.bin
~~~

Trong custom command:

- $LOCAL là đường dẫn tới phiên bản file phía local trong phép so sánh.
- $REMOTE là đường dẫn tới phiên bản phía còn lại.
- Git tạo các file tạm phù hợp cho công cụ được gọi.
- Lệnh phải được viết đúng cú pháp shell của môi trường chạy Git.

Tên LOCAL và REMOTE được giữ theo quy ước của difftool; chúng không nhất thiết có nghĩa là working tree local và Git server remote. Chúng chỉ đại diện cho hai phía trong phép so sánh đang chạy.

Nếu muốn thử lệnh mà không lưu cấu hình:

~~~bash
git difftool --extcmd='binary-viewer' -- path/to/file.bin
~~~

Tùy chọn --extcmd yêu cầu Git gọi chương trình bên ngoài theo cơ chế được hỗ trợ cho lần chạy đó. Hãy kiểm tra help của phiên bản Git đang dùng nếu custom command có nhiều tham số hoặc cần xử lý đường dẫn đặc biệt.

Không đưa lệnh không rõ nguồn gốc vào cấu hình diff. Difftool là chương trình chạy với quyền của tài khoản hiện tại; chỉ cấu hình executable bạn đã cài và xác minh.

## 14. Dùng textconv cho file nhị phân có thể chuyển thành văn bản

Một số định dạng nhị phân có thể được chuyển thành biểu diễn văn bản hữu ích. Ví dụ:

- PDF có thể trích xuất text theo trang.
- Ảnh có thể trích xuất metadata như kích thước, camera hoặc profile màu.
- Tài liệu office có thể được chuyển thành text hoặc cấu trúc XML để review.
- Archive có thể được liệt kê tên entry, checksum và kích thước.

Git hỗ trợ text conversion driver (*textconv*). Driver nhận nội dung file và xuất một biểu diễn văn bản để Git so sánh.

Ví dụ với file PDF và công cụ pdftotext:

Trong .gitattributes:

~~~gitattributes
*.pdf diff=pdftext
~~~

Trong cấu hình Git local:

~~~bash
git config --local diff.pdftext.textconv 'pdftotext -layout'
~~~

Sau đó:

~~~bash
git diff HEAD~1 HEAD -- docs/manual.pdf
~~~

Git gọi textconv cho các phiên bản file và so sánh phần văn bản được trích xuất. Điều này có thể giúp review nội dung câu chữ thay đổi mà không cần mở từng PDF.

Tên công cụ và cú pháp phụ thuộc chương trình chuyển đổi đã cài. Nếu textconv không hoạt động, kiểm tra executable có trong PATH và cấu hình driver:

~~~bash
git config --show-origin --show-scope --get-regexp '^diff\.pdftext\.'
git check-attr diff -- docs/manual.pdf
~~~

### 14.1. Textconv không phải binary patch

Textconv là phép chuyển đổi một chiều phục vụ hiển thị. Output text được tạo ra không phải nội dung gốc của file và không thể dùng như patch để tái tạo PDF hoặc ảnh.

Không dùng textconv output để thay thế binary object trong repository. Khi cần truyền file nhị phân, dùng Git object, binary patch hoặc hệ thống lưu trữ artifact phù hợp.

### 14.2. Textconv có thể bỏ qua khác biệt quan trọng

Hai PDF có thể trích xuất ra cùng văn bản nhưng khác bố cục, hình ảnh, font hoặc metadata. Tương tự, hai ảnh có thể có cùng metadata nhưng khác pixel. Textconv chỉ so sánh phần mà công cụ chuyển đổi xuất ra.

Vì vậy, hãy dùng textconv như một góc nhìn bổ sung. Với thay đổi quan trọng, mở file bằng viewer hoặc công cụ chuyên dụng để xác minh cả nội dung hiển thị và metadata cần thiết.

### 14.3. Bật hoặc tắt textconv theo lần chạy

Có thể yêu cầu Git dùng textconv:

~~~bash
git diff --textconv HEAD~1 HEAD -- docs/manual.pdf
~~~

Hoặc tắt textconv để xem cách Git xử lý blob gốc:

~~~bash
git diff --no-textconv HEAD~1 HEAD -- docs/manual.pdf
~~~

Khi debug, so sánh cả hai kết quả để biết sự khác biệt đến từ dữ liệu gốc hay từ bộ chuyển đổi.

## 15. So sánh ảnh bằng difftool

Giả sử repository có hai phiên bản logo PNG. Một công cụ image compare có thể hiển thị hai ảnh cạnh nhau, overlay hoặc tạo bản đồ pixel khác biệt.

Quy trình:

1. Xác định hai commit hoặc trạng thái cần so sánh.
2. Kiểm tra file thực sự thay đổi bằng git diff --name-status.
3. Chọn image viewer hoặc tool diff có hỗ trợ ảnh.
4. Mở hai phiên bản qua git difftool.
5. Kiểm tra kích thước, alpha channel, profile màu và nội dung hiển thị nếu các yếu tố đó quan trọng.

Ví dụ:

~~~bash
git difftool --tool=meld HEAD~1 HEAD -- assets/logo.png
~~~

Nếu Meld hoặc tool đang dùng không thể hiển thị PNG theo cách mong muốn, hãy dùng viewer chuyên dụng hoặc custom difftool command. Git chỉ chuyển hai phiên bản file cho tool; khả năng so sánh ảnh do chương trình ngoài quyết định.

Đừng kết luận ảnh giống nhau chỉ vì metadata giống nhau. Nếu cần pixel comparison, hãy dùng công cụ có chức năng so sánh pixel hoặc tạo overlay.

## 16. So sánh PDF và tài liệu office

Với PDF, có thể kết hợp hai cách:

- Textconv để phát hiện câu chữ được thêm, xóa hoặc thay đổi.
- PDF compare để xem bố cục, trang, hình ảnh, bảng và font.

Với DOCX hoặc ODT, một công cụ có thể trích xuất XML/text hoặc mở trực tiếp hai phiên bản trong ứng dụng văn phòng. Hãy lưu ý các file office dạng ZIP chứa nhiều thành phần nội bộ; một thay đổi nhỏ có thể làm nhiều entry XML đổi theo.

Ví dụ cấu hình textconv có thể dùng công cụ chuyển đổi phù hợp định dạng. Không nên giả định mọi file DOCX đều có thể được so sánh hữu ích bằng cách ép Git đọc như text.

Đối với tài liệu có ý nghĩa pháp lý, kỹ thuật hoặc nghiệp vụ, hãy review cả nội dung và bố cục cuối cùng. Một diff text sạch không bảo đảm trang in hoặc biểu đồ không bị vỡ.

## 17. So sánh archive, package và file thực thi

Với ZIP, JAR hoặc package binary, một quy trình review thường gồm:

1. Xem git diff --stat để biết file nào đổi và kích thước thay đổi.
2. Kiểm tra checksum hoặc object ID để xác định blob có đổi.
3. Liệt kê nội dung archive ở hai phiên bản bằng công cụ phù hợp.
4. So sánh file entry được thêm, xóa hoặc thay thế.
5. Nếu cần, trích xuất các entry quan trọng rồi so sánh nội dung riêng.
6. Với executable, dùng công cụ phân tích binary, symbol hoặc dependency khi cần hiểu thay đổi.

Không chỉ dựa vào việc file có cùng tên hoặc dung lượng gần giống nhau. Hai archive có thể khác vì timestamp hoặc thứ tự entry, dù file bên trong không đổi; ngược lại, một thay đổi nhỏ bên trong có thể làm checksum toàn bộ archive thay đổi.

Nếu package là artifact build, cân nhắc lưu trong artifact registry thay vì commit vào repository source. Nếu cần versioning cùng source, thống nhất chính sách về Git LFS hoặc hệ thống artifact.

## 18. Git LFS và binary diff

Git LFS lưu nội dung file lớn bên ngoài object database thông thường và commit một pointer file vào Git. Pointer chứa thông tin nhận dạng object LFS, chẳng hạn OID và kích thước.

Vì vậy, khi diff hai commit có file LFS, bạn có thể thấy thay đổi của pointer thay vì byte nội dung thật. Điều này không phải lỗi; Git đang so sánh nội dung được lưu trong repository chính.

Khi cần review file LFS:

- Xác nhận LFS object đã được tải về và có thể truy cập.
- Dùng công cụ Git LFS và viewer phù hợp để mở hai phiên bản thật.
- So sánh metadata/checksum và nội dung theo định dạng.
- Không chỉ kết luận dựa trên pointer thay đổi.

Với repository dùng LFS, đảm bảo thành viên và CI cài Git LFS, có quyền truy cập endpoint và tải đủ object cần thiết trước khi chạy kiểm thử hoặc phát hành.

## 19. Dùng difftool cho nhiều file và thư mục

Nếu một commit thay đổi nhiều binary asset, directory diff giúp xem tổng quan file thêm, xóa và sửa.

Ví dụ:

~~~bash
git difftool --dir-diff --tool=meld HEAD~1 HEAD -- assets/
~~~

Công cụ sẽ nhận hai cây thư mục đại diện cho hai phía. Bạn có thể duyệt file và mở các file khác biệt trong viewer tương ứng.

Nếu tool không hỗ trợ directory diff hoặc không hiển thị được binary, dùng danh sách file thay đổi:

~~~bash
git diff --name-status HEAD~1 HEAD -- assets/
~~~

Sau đó mở từng đường dẫn cần review:

~~~bash
git difftool --tool=meld HEAD~1 HEAD -- assets/logo.png
git difftool --tool=meld HEAD~1 HEAD -- assets/banner.png
~~~

Không phải mọi difftool đều có thể xử lý hàng trăm file binary hiệu quả. Hãy giới hạn pathspec theo nhóm asset hoặc loại file cần review.

## 20. Kiểm tra cấu hình và chẩn đoán difftool

Nếu Git không mở công cụ như mong đợi, kiểm tra cấu hình:

~~~bash
git config --show-origin --show-scope --get diff.tool
git config --show-origin --show-scope --get difftool.prompt
git config --show-origin --show-scope --get-regexp '^difftool\.'
~~~

Xem tool có được nhận diện:

~~~bash
git difftool --tool-help
~~~

Các lỗi thường gặp:

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| Git mở editor khác | diff.tool đang trỏ tới tool khác | Xem config cùng origin |
| Không tìm thấy executable | Tool chưa cài hoặc PATH chưa có | Kiểm tra executable trong shell |
| Git hỏi trước mỗi file | difftool.prompt đang bật | Dùng --no-prompt hoặc cấu hình local |
| Tool mở nhưng không đọc được binary | Tool chỉ hỗ trợ text | Chọn viewer phù hợp định dạng |
| Không có nội dung textconv | Driver chưa gắn hoặc executable lỗi | Kiểm tra .gitattributes và diff.<driver>.textconv |
| Diff PDF chỉ thấy một phần | Textconv chỉ trích xuất text | Mở PDF compare để kiểm tra layout |
| Directory diff không hoạt động | Tool không hỗ trợ so sánh thư mục | Dùng tool khác hoặc so sánh từng file |

Để chạy một lần không hỏi prompt:

~~~bash
git difftool --no-prompt --tool=meld HEAD~1 HEAD -- assets/
~~~

Nếu custom command bị lỗi, chạy thử executable trực tiếp với hai file mẫu trước khi gọi qua Git. Đọc thông báo lỗi và kiểm tra quoting của đường dẫn có dấu cách.

## 21. Phân biệt difftool với mergetool

Hai lệnh có mục tiêu khác nhau:

| Lệnh | Mục đích | Kết quả |
|---|---|---|
| git diff | Hiển thị khác biệt trong terminal | Diff text hoặc thông báo binary khác nhau |
| git difftool | Mở công cụ bên ngoài để xem hai phiên bản | Hỗ trợ review và so sánh |
| git mergetool | Mở công cụ để giải quyết file đang conflict | Tạo nội dung hợp nhất để stage |
| git apply | Áp dụng patch vào working tree | Thay đổi file theo patch |

Không dùng difftool với kỳ vọng tự giải quyết conflict. Khi merge đang dừng vì conflict, cần hiểu các phiên bản base/ours/theirs và dùng mergetool hoặc chỉnh sửa thủ công, sau đó stage file đã giải quyết.

## 22. Quy trình review thay đổi binary trước commit hoặc release

Một quy trình thực tế:

1. Chạy git status để xác định file binary nào mới, sửa hoặc xóa.
2. Dùng git diff --name-status và --stat để biết phạm vi.
3. Dùng git check-attr để xác nhận binary/text attributes.
4. Xác định hai phiên bản cần so sánh: index với working tree, HEAD với index hay hai commit.
5. Chọn viewer hoặc custom diff tool phù hợp với định dạng.
6. Kiểm tra metadata, checksum hoặc danh sách entry nếu cần.
7. Xem xét tác động tới dung lượng repository và chính sách LFS/artifact.
8. Review nội dung cuối cùng trước khi stage hoặc commit.
9. Ghi chú lý do thay đổi asset nếu người review không thể suy ra từ diff.

Ví dụ chuỗi lệnh:

~~~bash
git status --short
git diff --name-status
git diff --stat
git check-attr -a -- assets/logo.png
git difftool --tool=meld -- assets/logo.png
git diff --cached --stat
git diff --cached --check
~~~

Nếu file đã stage, thêm --cached vào lệnh difftool để so sánh đúng nội dung index với HEAD. Luôn xác nhận diff đang mở đúng hai phía bạn định review.

## 23. Những lỗi thường gặp

- **Nghĩ rằng Git không hỗ trợ binary file.** Git vẫn lưu blob bình thường; chỉ cách hiển thị diff khác.
- **Ép ảnh hoặc archive thành text.** Output có thể vô nghĩa và không giúp review.
- **Dùng --binary để xem ảnh trực quan.** Binary patch phục vụ truyền và áp dụng thay đổi, không phải viewer.
- **Tin rằng textconv cho thấy toàn bộ thay đổi.** Nó chỉ so sánh biểu diễn văn bản do converter xuất ra.
- **Nhầm difftool với mergetool.** Difftool phục vụ xem, mergetool phục vụ giải quyết conflict.
- **Cấu hình tool nhưng executable chưa cài.** Git biết tên tool nhưng hệ điều hành không tìm được chương trình.
- **Không xác định đúng hai phía so sánh.** Difftool có thể đang so index với working tree trong khi bạn muốn so hai commit.
- **Không kiểm tra file LFS thật.** Git diff có thể chỉ cho thấy pointer thay đổi.
- **Bỏ qua metadata và checksum.** Một file có thể đổi metadata nhưng không đổi nội dung hiển thị, hoặc ngược lại.
- **Chỉ review thống kê.** --stat không thay thế việc mở và kiểm tra nội dung asset.

## 24. Ghi nhớ

Git lưu binary file dưới dạng blob như mọi file khác, nhưng thường không tạo line diff cho nội dung không phải văn bản. Dùng --stat, --numstat, --summary, --raw và --name-status để biết file nào đổi; dùng --binary khi cần tạo patch có thể áp dụng; chỉ dùng --text khi đã xác nhận dữ liệu phù hợp để đọc như text. Với review trực quan, chọn git difftool cùng viewer phù hợp định dạng. Textconv hữu ích khi có thể trích xuất một biểu diễn văn bản, nhưng không thay thế việc kiểm tra nội dung gốc. Luôn xác định đúng hai phiên bản, đúng tool và đúng phạm vi trước khi kết luận một thay đổi binary là hợp lệ.
