# LF, CRLF và lý do thay đổi dòng có thể xuất hiện hàng loạt

Một file văn bản có thể dùng LF hoặc CRLF để kết thúc mỗi dòng. LF thường gặp trên Linux và macOS; CRLF thường gặp trên Windows. Khi thành viên trong nhóm dùng hệ điều hành, editor hoặc cấu hình Git khác nhau, một lần checkout, lưu file hay stage có thể làm thay đổi cách kết thúc dòng của rất nhiều file. Git có thể hiển thị gần như toàn bộ file là đã sửa dù logic chương trình không thay đổi.

Trong chương **Đa môi trường** của module **SOURCE_CONTROL_GIT**, bài học này giải thích cách Git xử lý line ending giữa working tree và object database, vai trò của core.autocrlf, core.eol và .gitattributes, cùng cách tìm nguyên nhân khi diff xuất hiện hàng loạt. Bạn sẽ biết cách thiết lập quy ước chung cho repository và chuẩn hóa file mà vẫn kiểm tra được những thay đổi nội dung thực sự.

Sau bài học, bạn có thể:

- Phân biệt LF, CRLF và file có line ending hỗn hợp.
- Giải thích vì sao cùng một nội dung có thể tạo diff lớn khi line ending thay đổi.
- Hiểu cách Git chuẩn hóa nội dung khi đưa file vào index và khi checkout.
- Kiểm tra cấu hình line ending ở cấp hệ thống, người dùng và repository.
- Dùng .gitattributes để quy định line ending nhất quán cho nhóm.
- Chẩn đoán bằng git ls-files --eol, git check-attr và các lệnh diff.
- Chuẩn hóa file đang được theo dõi và xác minh kết quả an toàn.

## 1. LF và CRLF là gì?

Máy tính biểu diễn văn bản bằng các ký tự. Ký tự kết thúc dòng cho biết nơi một dòng dừng và dòng tiếp theo bắt đầu.

| Kiểu | Ký tự | Cách biểu diễn thường thấy |
| --- | --- | --- |
| LF | Line Feed, byte 0A | \n |
| CRLF | Carriage Return rồi Line Feed, byte 0D 0A | \r\n |
| CR | Carriage Return, byte 0D | \r |

LF phổ biến trên Linux và macOS hiện đại. CRLF phổ biến trên Windows và thường được một số editor hoặc công cụ Windows sử dụng theo mặc định. CR đơn chủ yếu gặp trong dữ liệu hoặc hệ thống cũ.

Ví dụ cùng ba dòng văn bản:

~~~text
alpha
beta
gamma
~~~

Nếu file dùng LF, mỗi dòng kết thúc bằng một byte 0A. Nếu dùng CRLF, mỗi dòng kết thúc bằng hai byte 0D 0A. Khi hiển thị trên editor, nội dung nhìn có thể giống hệt nhau, nhưng chuỗi byte trong file khác nhau.

Một file cũng có thể chứa line ending hỗn hợp: một số dòng kết thúc bằng LF, số khác bằng CRLF. Điều này có thể xảy ra khi ghép nội dung từ nhiều nguồn, copy/paste, dùng editor có cấu hình không thống nhất hoặc chạy công cụ chuyển đổi chỉ trên một phần file.

Line ending khác với encoding. UTF-8, UTF-16, BOM và các bảng mã khác quyết định cách biểu diễn ký tự; LF và CRLF quyết định cách phân tách dòng. Đổi encoding có thể làm thay đổi nhiều byte khác, vì vậy khi điều tra diff hàng loạt hãy xác định đó là thay đổi line ending hay thay đổi encoding.

## 2. Vì sao thay đổi line ending tạo ra diff lớn?

Git lưu nội dung file thành blob. Hash của blob được tính từ nội dung byte, vì vậy hai file có cùng chữ nhưng một file dùng LF và file kia dùng CRLF vẫn có thể tạo ra hai blob khác nhau.

Giả sử commit hiện tại chứa file LF:

~~~text
alpha<LF>
beta<LF>
gamma<LF>
~~~

Một editor lưu lại toàn bộ file với CRLF:

~~~text
alpha<CRLF>
beta<CRLF>
gamma<CRLF>
~~~

Với Git, mỗi dòng đã thay đổi ở cấp byte. Diff có thể đánh dấu tất cả dòng cũ bị xóa và tất cả dòng mới được thêm, dù từ ngữ và logic không đổi.

Hiện tượng này thường xảy ra trong các tình huống:

- Một thành viên checkout file thành CRLF, sau đó commit trong khi repository đang lưu LF.
- Một editor tự chuyển toàn bộ file sang line ending mặc định của hệ điều hành.
- Cấu hình core.autocrlf khác nhau giữa máy của các thành viên.
- Repository thiếu .gitattributes hoặc chỉ định line ending không nhất quán.
- Một lần chuyển đổi line ending được trộn chung với thay đổi logic trong cùng commit.
- File đã có line ending hỗn hợp và công cụ lưu file chuẩn hóa toàn bộ thành một kiểu.

Hậu quả không chỉ là pull request khó review. Diff nhiễu còn làm merge conflict nhiều hơn, gây khó truy vết bằng blame và khiến người review khó nhận ra thay đổi chức năng thật sự.

## 3. Git xử lý line ending ở hai thời điểm

Để hiểu cấu hình, hãy phân biệt hai chiều chuyển đổi:

1. **Check-in**: nội dung đi từ working tree vào index rồi được ghi thành blob trong commit.
2. **Checkout**: nội dung từ commit hoặc index được đưa ra working tree.

Khi Git áp dụng cơ chế text normalization, Git có thể chuẩn hóa CRLF thành LF ở chiều check-in. Khi checkout, Git có thể chuyển LF trong nội dung đã chuẩn hóa thành kiểu line ending phù hợp với cấu hình hoặc thuộc tính của file.

~~~text
Working tree trên Windows
        CRLF
         |
         | clean / check-in conversion
         v
Index và blob được chuẩn hóa
         LF
         |
         | checkout conversion
         v
Working tree theo quy ước
        CRLF
~~~

Sơ đồ trên mô tả trường hợp repository quy định lưu text chuẩn hóa bằng LF và working tree dùng CRLF. Không phải mọi file đều tự động được chuyển đổi: Git cần cấu hình phù hợp hoặc thuộc tính text trong .gitattributes.

Nếu không có quy tắc chuẩn hóa, Git có thể lưu nguyên byte line ending đang có trong file. Vì vậy, không nên mặc định mọi blob trong repository đều dùng LF. Muốn biết trạng thái thực tế, hãy kiểm tra index, working tree và attributes.

## 4. Cấu hình core.autocrlf

Git có thiết lập core.autocrlf để kiểm soát chuyển đổi line ending tự động cho file text khi không có quy tắc thuộc tính cụ thể ghi đè.

| Giá trị | Khi đưa nội dung vào Git | Khi checkout |
| --- | --- | --- |
| true | Chuẩn hóa CRLF thành LF đối với file được nhận diện là text | Chuyển LF thành CRLF trong working tree |
| input | Chuẩn hóa CRLF thành LF đối với file được nhận diện là text | Không chuyển LF thành CRLF |
| false | Không tự động chuyển đổi theo thiết lập này | Không tự động chuyển đổi theo thiết lập này |

Trên Windows, một số người dùng đặt:

~~~bash
git config --global core.autocrlf true
~~~

Trên Linux hoặc macOS, nhóm thường chọn:

~~~bash
git config --global core.autocrlf input
~~~

Các ví dụ này là cấu hình theo người dùng, không phải quy tắc bắt buộc cho mọi máy. Khi repository có .gitattributes rõ ràng, thuộc tính của file là cơ sở quan trọng để thống nhất hành vi giữa các thành viên.

Kiểm tra giá trị và nguồn cấu hình:

~~~bash
git config --show-origin --get core.autocrlf
~~~

Nếu không có kết quả, giá trị có thể chưa được đặt và Git dùng mặc định. Dùng --show-origin để biết cấu hình đến từ file nào, chẳng hạn system, global hoặc local. Cấu hình local của repository có thể khiến hai repository trên cùng một máy có hành vi khác nhau.

## 5. Cấu hình core.eol

core.eol quy định kiểu line ending Git dùng khi checkout file text đã được đánh dấu cần xử lý line ending và không có thuộc tính eol cụ thể hơn.

Các giá trị thường gặp:

- **lf**: working tree dùng LF.
- **crlf**: working tree dùng CRLF.
- **native**: dùng kiểu line ending native của hệ điều hành.

Ví dụ:

~~~bash
git config --global core.eol lf
~~~

Hoặc cấu hình cho repository hiện tại:

~~~bash
git config --local core.eol native
~~~

Kiểm tra:

~~~bash
git config --show-origin --get core.eol
~~~

core.eol không tự biến mọi file thành text. Git cần nhận diện file là text thông qua thuộc tính hoặc cơ chế autocrlf. Nếu muốn chính sách rõ ràng theo loại file và áp dụng đồng nhất cho cả nhóm, nên khai báo trong .gitattributes.

## 6. Dùng .gitattributes để thống nhất trong repository

.gitattributes là file quy định thuộc tính cho đường dẫn trong repository. Vì file này được commit cùng source code, mọi thành viên và CI có thể dùng chung chính sách line ending.

Ví dụ chính sách phổ biến:

~~~gitattributes
# Tự nhận diện file văn bản và chuẩn hóa line ending trong repository
* text=auto

# Các script shell luôn dùng LF
*.sh text eol=lf

# Script Windows dùng CRLF trong working tree
*.bat text eol=crlf
*.cmd text eol=crlf

# File nhị phân không thực hiện chuyển đổi text
*.png -text
*.jpg -text
*.pdf -text
~~~

Ý nghĩa:

- **text=auto** yêu cầu Git tự nhận diện file text và chuẩn hóa line ending của các file được nhận diện là text khi check-in.
- **text eol=lf** đánh dấu file là text và yêu cầu working tree dùng LF.
- **text eol=crlf** đánh dấu file là text và yêu cầu working tree dùng CRLF.
- **-text** tắt text normalization cho loại file được chỉ định.

Nếu muốn các loại file văn bản phổ biến dùng LF trong working tree, hãy giữ quy tắc tự nhận diện chung rồi chỉ định rõ các nhóm file cần LF:

~~~gitattributes
* text=auto
*.txt text eol=lf
*.md text eol=lf
*.java text eol=lf
~~~

Không đặt eol=lf một cách tổng quát cho mọi đường dẫn nếu repository có file nhị phân. Thuộc tính eol buộc đường dẫn được xử lý như text; hãy chỉ áp dụng nó cho các loại file văn bản đã xác định.

Hãy chọn chính sách phù hợp với công cụ và môi trường chạy của dự án. Ví dụ, script shell thường cần LF để chạy ổn định trên Linux; một số file batch hoặc cấu hình phục vụ công cụ Windows có thể cần CRLF. Không nên áp dụng một quy tắc cứng cho mọi loại file nếu dự án có yêu cầu khác nhau.

Đối với file nhị phân, dùng -text hoặc thuộc tính macro binary nếu phù hợp. Không ép chuẩn hóa line ending cho ảnh, PDF, archive, font hoặc file dữ liệu nhị phân.

## 7. Thuộc tính text, eol và binary khác nhau thế nào?

| Thuộc tính | Tác dụng |
| --- | --- |
| text | Xem file là text và chuẩn hóa CRLF thành LF khi check-in |
| text=auto | Để Git tự nhận diện file text trước khi chuẩn hóa |
| eol=lf | Yêu cầu line ending LF trong working tree; đồng thời bật xử lý text |
| eol=crlf | Yêu cầu line ending CRLF trong working tree; đồng thời bật xử lý text |
| -text | Không áp dụng text normalization cho file |
| binary | Macro thuộc tính thường dùng cho file nhị phân; tắt text, diff và merge text thông thường |

Thuộc tính có thể được đặt theo phần mở rộng, thư mục hoặc tên file cụ thể. Ví dụ:

~~~gitattributes
* text=auto
docs/**/*.md text eol=lf
scripts/**/*.sh text eol=lf
windows/**/*.cmd text eol=crlf
assets/** -text
~~~

Các mẫu đường dẫn trong .gitattributes có quy tắc khớp riêng. Hãy đặt file ở vị trí phù hợp và kiểm tra kết quả áp dụng thay vì giả định một pattern đã khớp mọi đường dẫn mong muốn.

Kiểm tra thuộc tính của một file:

~~~bash
git check-attr text eol -- README.md
git check-attr --all -- scripts/build.sh
~~~

Lệnh đầu cho biết giá trị text và eol áp dụng cho README.md. Lệnh thứ hai liệt kê tất cả thuộc tính áp dụng cho script. Nếu kết quả là unspecified, file có thể đang chịu ảnh hưởng từ cấu hình tự động hoặc quy tắc ở cấp khác.

## 8. Chẩn đoán bằng git ls-files --eol

Khi nhiều file bị báo modified, lệnh hữu ích nhất để so sánh line ending trong index, working tree và thuộc tính là:

~~~bash
git ls-files --eol
~~~

Ví dụ kết quả:

~~~text
i/lf    w/crlf  attr/text eol=crlf    src/App.java
i/lf    w/lf    attr/text eol=lf      scripts/build.sh
i/-text w/-text attr/-text            assets/logo.png
~~~

Các cột:

- **i/**: kiểu line ending được phát hiện trong nội dung index.
- **w/**: kiểu line ending được phát hiện trong working tree.
- **attr/**: thuộc tính line ending/text áp dụng cho file.
- Phần cuối: đường dẫn file.

Một số giá trị có thể gặp:

- lf: Git phát hiện LF.
- crlf: Git phát hiện CRLF.
- mixed: file có line ending không đồng nhất.
- none: không phát hiện line ending.
- -text hoặc unspecified: không có text normalization theo thuộc tính tương ứng.

Nếu thấy i/lf và w/crlf cùng với attr/text eol=crlf, đây có thể là trạng thái bình thường: index lưu nội dung đã chuẩn hóa bằng LF, còn working tree dùng CRLF theo quy ước. Không nhất thiết có diff chỉ vì hai cột khác nhau.

Nếu thấy i/lf, w/crlf nhưng thuộc tính không được đặt như mong đợi, hãy kiểm tra core.autocrlf, core.eol và .gitattributes. Nếu w/mixed, file có thể đã bị chỉnh sửa bằng công cụ giữ lại một số dòng LF và chuyển các dòng khác thành CRLF.

Có thể kiểm tra riêng một file:

~~~bash
git ls-files --eol -- src/App.java
~~~

Kết hợp lệnh này với git check-attr và git config --show-origin để xác định nguồn gốc chính sách.

## 9. Xác định thay đổi hàng loạt có chỉ do line ending hay không

Khi diff báo nhiều file modified, đừng vội stage hoặc commit. Hãy xác định phạm vi và so sánh theo nhiều góc nhìn.

### Kiểm tra trạng thái

~~~bash
git status --short
git diff --stat
git diff --numstat
~~~

Nếu rất nhiều file có số dòng xóa và thêm gần bằng nhau, có thể đang có chuyển đổi line ending hoặc định dạng toàn file. Đây là dấu hiệu để điều tra, chưa phải bằng chứng kết luận.

### Bỏ qua khác biệt ở cuối dòng khi so sánh

~~~bash
git diff --ignore-space-at-eol
~~~

Tùy chọn này bỏ qua khác biệt khoảng trắng ở cuối dòng khi hiển thị diff. Nó hữu ích để xem thay đổi logic còn lại sau khi bỏ qua khác biệt cuối dòng. Nếu diff gần như biến mất, nguyên nhân có thể chủ yếu là line ending hoặc khoảng trắng cuối dòng.

Có thể kiểm tra một file:

~~~bash
git diff --ignore-space-at-eol -- src/App.java
~~~

Đừng dùng kết quả này thay cho việc kiểm tra diff bình thường. Khoảng trắng cuối dòng đôi khi có ý nghĩa với file dữ liệu, định dạng hoặc công cụ xử lý. Hãy xác nhận bằng cấu hình và trạng thái byte thực tế.

### Kiểm tra line ending và attributes

~~~bash
git ls-files --eol
git check-attr --all -- src/App.java
git config --show-origin --get core.autocrlf
git config --show-origin --get core.eol
~~~

So sánh kết quả giữa một file bị ảnh hưởng và file tương tự không bị ảnh hưởng. Nếu thuộc tính hoặc cấu hình khác nhau, đó có thể là nguyên nhân làm hành vi checkout/check-in không thống nhất.

## 10. Vì sao các thành viên có thể thấy trạng thái khác nhau?

Git config có thể được đặt ở nhiều cấp:

| Cấp | Phạm vi | Ví dụ |
| --- | --- | --- |
| system | Toàn hệ thống | Cấu hình do quản trị máy đặt |
| global | Người dùng hiện tại | Cấu hình trong file cấu hình người dùng |
| local | Repository hiện tại | Cấu hình riêng của dự án |
| worktree | Worktree cụ thể nếu được bật hỗ trợ | Cấu hình riêng một worktree |

Giá trị hiệu lực có thể đến từ cấp ưu tiên cao hơn. Vì vậy, hai thành viên có thể cùng clone repository nhưng nhận line ending khác nhau do core.autocrlf, core.eol hoặc editor settings khác nhau.

Ngoài Git config, editor có thể có thiết lập riêng:

- Tự dùng line ending theo hệ điều hành.
- Giữ line ending của file đang mở.
- Chuyển toàn bộ file sang LF hoặc CRLF khi lưu.
- Chỉ thay đổi line ending của phần nội dung được dán vào.

Một file .editorconfig có thể giúp editor dùng chung quy ước:

~~~editorconfig
root = true

[*]
charset = utf-8
end_of_line = lf
insert_final_newline = true

[*.{bat,cmd}]
end_of_line = crlf
~~~

.editorconfig hướng dẫn editor khi mở và lưu file; .gitattributes quy định cách Git xử lý file trong repository. Hai file bổ trợ cho nhau nhưng không thay thế nhau. Nếu editor không hỗ trợ EditorConfig, quy tắc trong file có thể không được áp dụng.

## 11. Thiết lập chính sách line ending cho nhóm

Một quy trình dễ duy trì thường gồm các bước:

1. Chọn line ending chuẩn trong repository, thường là LF cho phần lớn file text.
2. Xác định các loại file cần ngoại lệ, ví dụ script shell hoặc file batch.
3. Ghi chính sách vào .gitattributes và commit cùng repository.
4. Cân nhắc thêm .editorconfig để editor của các thành viên lưu đúng kiểu.
5. Hướng dẫn thành viên kiểm tra core.autocrlf và không tự ý thay đổi cấu hình riêng khi chưa hiểu tác động.
6. Chuẩn hóa repository trong một commit riêng, review diff và kiểm thử.

Ví dụ một chính sách đơn giản:

~~~gitattributes
* text=auto
*.sh text eol=lf
*.bat text eol=crlf
*.cmd text eol=crlf
*.png -text
*.jpg -text
*.zip -text
~~~

Quy tắc phải phản ánh thực tế dự án. Nếu file đặc thù cần line ending khác, thêm pattern cụ thể và kiểm tra bằng git check-attr. Không để nhiều quy tắc chồng chéo khiến thành viên khó đoán thuộc tính cuối cùng.

## 12. Chuẩn hóa repository đã có nhiều line ending

Nếu repository đã có nhiều file LF/CRLF, cần thống nhất chính sách trước khi chuyển đổi. Không nên vừa sửa logic vừa chuyển toàn bộ line ending trong cùng một commit nếu có thể tách riêng.

### Bước 1: xem tình trạng hiện tại

~~~bash
git status --short
git ls-files --eol
~~~

Đảm bảo working tree sạch hoặc đã lưu riêng mọi thay đổi đang làm. Ghi nhận file nào đang có LF, CRLF hoặc mixed.

### Bước 2: thêm hoặc cập nhật .gitattributes

Chọn quy tắc theo loại file. Ví dụ:

~~~gitattributes
* text=auto
*.sh text eol=lf
*.bat text eol=crlf
*.cmd text eol=crlf
*.png -text
*.jpg -text
~~~

Đọc lại thuộc tính cho các file đại diện:

~~~bash
git check-attr --all -- src/App.java scripts/build.sh windows/run.cmd assets/logo.png
~~~

### Bước 3: áp dụng lại clean process cho file đã theo dõi

Sau khi đã chọn và kiểm tra chính sách, dùng:

~~~bash
git add --renormalize .
~~~

Tùy chọn --renormalize yêu cầu Git áp dụng lại quy trình clean cho các file đã được theo dõi. Các thay đổi chuẩn hóa sẽ xuất hiện trong index. Lệnh này không tự commit.

Chỉ chạy khi hiểu chính sách và đã lưu thay đổi đang làm dở. Nếu .gitattributes sai, renormalize có thể tạo ra một lượng lớn thay đổi không mong muốn.

### Bước 4: review phần đã stage

~~~bash
git status --short
git diff --cached --stat
git diff --cached
git diff --cached --ignore-space-at-eol
~~~

Diff thông thường cho thấy thay đổi byte được stage. Diff bỏ qua khoảng trắng cuối dòng giúp nhìn rõ phần nội dung thực sự thay đổi. Kiểm tra các file bị ảnh hưởng có đúng với phạm vi chính sách không.

### Bước 5: commit chuẩn hóa riêng

Khi diff chỉ chứa thay đổi line ending dự kiến và các file cần chuẩn hóa, tạo một commit riêng với thông điệp rõ ràng, ví dụ:

~~~bash
git commit -m "chore: normalize text file line endings"
~~~

Commit riêng giúp pull request chức năng sau này dễ review và giúp người điều tra biết một thay đổi lớn chỉ nhằm chuẩn hóa line ending.

### Bước 6: xác minh sau commit

~~~bash
git status --short
git ls-files --eol
git diff HEAD^ HEAD --ignore-space-at-eol
~~~

Xác nhận working tree sạch, trạng thái EOL phù hợp với thuộc tính và diff sau khi bỏ qua khác biệt cuối dòng không chứa thay đổi logic ngoài dự kiến.

## 13. Xử lý khi một pull request có diff hàng loạt do EOL

Khi review phát hiện một pull request thay đổi gần như toàn bộ file, có thể làm theo quy trình:

1. Kiểm tra git diff --stat để xác định phạm vi.
2. Chạy git ls-files --eol cho các file đại diện.
3. Kiểm tra .gitattributes và git check-attr.
4. Kiểm tra core.autocrlf, core.eol và cấu hình editor.
5. Dùng git diff --ignore-space-at-eol để nhận diện phần logic còn lại.
6. Trao đổi với tác giả để tách thay đổi EOL khỏi thay đổi chức năng nếu cần.

Nếu thay đổi line ending chỉ xảy ra trong working tree và chưa được stage, sau khi bảo đảm không có chỉnh sửa cần giữ, có thể khôi phục file về nội dung của HEAD:

~~~bash
git restore --source=HEAD --worktree -- path/to/file
~~~

Lệnh này ghi đè nội dung working tree của file được chỉ định. Nếu file có chỉnh sửa thật, những chỉnh sửa đó cũng bị bỏ. Hãy sao lưu hoặc commit trước khi chạy.

Nếu thay đổi đã stage và bạn muốn bỏ cả phiên bản trong index lẫn working tree cho một file:

~~~bash
git restore --source=HEAD --staged --worktree -- path/to/file
~~~

Lệnh này cũng loại bỏ thay đổi đã stage của file đó. Chỉ dùng sau khi xác nhận nội dung không cần giữ. Sau đó áp dụng chính sách .gitattributes và kiểm tra lại line ending.

Không dùng git reset --hard hoặc git clean chỉ để xử lý một diff EOL nếu chưa phân loại các thay đổi khác. Hai lệnh đó có thể ảnh hưởng rộng hơn file đang review.

## 14. Các lưu ý về file đặc thù và chuyển đổi không an toàn

### File nhị phân

File nhị phân không nên bị chuẩn hóa như file văn bản. Nếu Git nhận diện nhầm hoặc chính sách text áp dụng sai, có thể làm hỏng nội dung. Dùng thuộc tính -text hoặc binary cho các loại file phù hợp.

### File có line ending hỗn hợp

Chuẩn hóa có thể thay đổi toàn bộ line ending trong file. Trước khi stage, hãy kiểm tra diff và xác định editor có tự chuyển tất cả dòng sang một kiểu không. Đừng giả định các dòng nhìn giống nhau sẽ có cùng byte kết thúc.

### Khoảng trắng cuối dòng

CRLF chứa ký tự CR trước LF. Một số công cụ hiển thị CR như ký tự ^M hoặc tính nó vào khác biệt cuối dòng. Tùy chọn ignore-space-at-eol giúp so sánh, nhưng không nên bỏ qua whitespace một cách mặc định trong file mà khoảng trắng có ý nghĩa.

### core.safecrlf

Có thể dùng core.safecrlf để Git cảnh báo hoặc từ chối một số chuyển đổi line ending có khả năng không đảo ngược:

~~~bash
git config --global core.safecrlf warn
~~~

Giá trị warn yêu cầu Git cảnh báo khi phát hiện chuyển đổi có thể không khôi phục nguyên trạng. Tùy chọn này là lớp hỗ trợ phát hiện, không thay thế .gitattributes và chính sách nhóm.

### Không sửa blob trực tiếp

Không nên chỉnh file trong .git/objects bằng trình soạn thảo. Nếu cần chuẩn hóa nội dung, hãy làm trên working tree, cấu hình thuộc tính, stage bằng Git và kiểm tra diff.

## 15. Những nhầm lẫn thường gặp

### Git luôn lưu file với LF?

Không. Git có thể chuẩn hóa file text thành LF nếu thuộc tính hoặc cấu hình yêu cầu. Nếu không có quy tắc phù hợp, blob có thể giữ nguyên CRLF hoặc line ending khác.

### i/lf và w/crlf trong git ls-files --eol có nghĩa file đang lỗi?

Không nhất thiết. Đây có thể là trạng thái dự kiến khi index đã chuẩn hóa LF còn working tree được yêu cầu dùng CRLF.

### Chỉ cần đặt core.autocrlf là đủ cho cả nhóm?

Không. core.autocrlf là cấu hình theo máy hoặc repository và có thể khác giữa thành viên. .gitattributes giúp ghi chính sách chung vào repository.

### Đổi line ending có thay đổi logic chương trình không?

Thông thường không, nhưng Git vẫn có thể ghi nhận byte khác nhau và tạo diff lớn. Với file script hoặc dữ liệu đặc thù, line ending sai có thể ảnh hưởng cách công cụ đọc hoặc thực thi.

### .editorconfig có thay thế .gitattributes?

Không. EditorConfig hướng dẫn editor; .gitattributes điều khiển thuộc tính và quá trình xử lý nội dung của Git.

### Có nên chạy git add --renormalize . ngay khi thấy nhiều file modified?

Không. Trước tiên cần xác định nguyên nhân, chọn chính sách, bảo vệ thay đổi đang làm và review phạm vi. Renormalize chỉ nên chạy sau khi repository đã có thuộc tính đúng.

## 16. Tự kiểm tra

Một thành viên Windows mở nhiều file Java trong editor và lưu lại. Pull request sau đó báo 80 file modified, dù tác giả chỉ thay đổi logic ở hai file. Một số file có trạng thái i/lf w/crlf, repository chưa có .gitattributes, và máy của tác giả đặt core.autocrlf=true.

Hãy trả lời:

1. Vì sao Git có thể hiển thị hàng loạt dòng thay đổi dù nội dung chữ giống nhau?
2. i/lf và w/crlf cho biết điều gì?
3. Lệnh nào kiểm tra cấu hình core.autocrlf và nguồn cấu hình?
4. Vì sao nhóm nên thêm .gitattributes?
5. Sau khi thống nhất thuộc tính, lệnh nào chuẩn hóa lại các file đã được theo dõi?
6. Làm thế nào review phần thay đổi logic sau khi bỏ qua khác biệt cuối dòng?
7. Vì sao nên tách commit chuẩn hóa line ending khỏi commit chức năng?

**Gợi ý:** Git so sánh byte của blob và file, nên CRLF khác LF dù chữ giống nhau. i/lf là line ending trong index; w/crlf là line ending working tree. Dùng git config --show-origin --get core.autocrlf để kiểm tra giá trị và nguồn. .gitattributes lưu chính sách chung cho repository. Sau khi kiểm tra thuộc tính, dùng git add --renormalize . rồi review git diff --cached và git diff --cached --ignore-space-at-eol. Tách commit giúp review, blame và điều tra lỗi dễ hơn.

## Kết luận

LF và CRLF là hai cách biểu diễn kết thúc dòng; nếu cấu hình giữa editor, Git và các máy không thống nhất, một lần lưu file có thể tạo diff lớn dù logic không đổi. Git có thể chuẩn hóa nội dung ở chiều check-in và chuyển đổi line ending khi checkout, dựa trên core.autocrlf, core.eol và đặc biệt là .gitattributes. Khi gặp thay đổi hàng loạt, hãy kiểm tra i/ và w/ bằng git ls-files --eol, xem thuộc tính và nguồn cấu hình, rồi chuẩn hóa trong một commit riêng bằng git add --renormalize . sau khi đã xác nhận chính sách. Quy ước rõ ràng giúp nhóm review sạch hơn và tránh xung đột không cần thiết khi làm việc trên nhiều hệ điều hành.
