# Phát hiện đổi tên, sao chép và giới hạn của suy luận tương đồng

Git lưu snapshot của cây thư mục trong mỗi commit. Một snapshot ghi nhận đường dẫn nào trỏ tới object nào; nó không lưu một thao tác riêng có tên “rename” hoặc “copy”. Khi hiển thị khác biệt giữa hai snapshot, Git có thể suy luận rằng một file bị xóa ở đường dẫn cũ đã được chuyển sang đường dẫn mới, hoặc nội dung của một file được sao chép sang file khác. Suy luận này dựa chủ yếu vào mức độ tương đồng nội dung.

Khả năng nhận diện rename và copy giúp lịch sử dễ đọc hơn khi file được di chuyển, đổi tên hoặc nhân bản. Tuy nhiên, đây là heuristic: Git không biết ý định của người sửa. Ngưỡng tương đồng, số lượng file và lựa chọn nguồn để so sánh đều ảnh hưởng tới kết quả. Hiểu các giới hạn này giúp bạn đọc đúng output, chọn tùy chọn phù hợp và không nhầm cách Git trình bày diff với cấu trúc dữ liệu thực sự được lưu trong commit.

Sau bài này, bạn có thể:

- Giải thích vì sao rename và copy được suy luận khi hiển thị diff.
- Dùng -M hoặc --find-renames để phát hiện đổi tên.
- Dùng -C hoặc --find-copies để phát hiện sao chép.
- Điều chỉnh ngưỡng tương đồng và hiểu mã R/C cùng phần trăm.
- Dùng --find-copies-harder khi nguồn copy không thay đổi.
- Tắt hoặc giới hạn phát hiện rename/copy khi cần.
- Đọc kết quả bằng --name-status, --summary và --raw.
- Nhận biết trường hợp heuristic bỏ sót hoặc ghép nhầm file.

## 1. Git lưu snapshot, không lưu thao tác rename

Giả sử bạn đổi tên:

~~~text
src/OldParser.java  ->  src/Parser.java
~~~

Ở mức snapshot, cây thư mục mới chỉ cần ghi nhận:

- Đường dẫn src/OldParser.java không còn tồn tại.
- Đường dẫn src/Parser.java trỏ tới nội dung object tương ứng.

Nếu nội dung file gần như không đổi, khi so sánh hai commit Git có thể nhận ra cặp xóa/thêm này rất giống nhau và trình bày nó như một rename.

Điều này có nghĩa:

- Commit tree không chứa một bản ghi thao tác “đổi tên file”.
- Rename detection là bước phân tích diff để tạo output dễ hiểu.
- Cùng một cặp commit có thể được trình bày khác nhau nếu thay đổi tùy chọn rename detection hoặc ngưỡng tương đồng.
- Một file được di chuyển nhưng thay đổi nội dung quá nhiều có thể được hiển thị thành xóa file cũ và thêm file mới.

Tương tự, copy được suy luận khi một đường dẫn mới có nội dung tương đồng với một đường dẫn đã tồn tại. Git không lưu một bản ghi “copy từ file A sang file B” trong commit.

## 2. Git nhận diện rename bằng mức độ tương đồng

Rename detection tìm các cặp file bị xóa và file được thêm trong hai phía của diff, rồi ước lượng mức độ giống nhau giữa nội dung. Nếu điểm tương đồng đạt ngưỡng, Git có thể ghép chúng thành một rename.

Mức tương đồng được biểu diễn bằng phần trăm:

- 100%: nội dung giống hệt.
- 90%: phần lớn nội dung được giữ lại, có một số thay đổi.
- 50%: đạt ngưỡng mặc định phổ biến cho rename detection.

Điểm này phản ánh mức độ giống nhau theo thuật toán của Git, không phải đánh giá ngữ nghĩa của mã nguồn. Hai file có thể rất giống về nội dung nhưng không có quan hệ lịch sử; ngược lại, một file được đổi tên thật nhưng viết lại gần như hoàn toàn có thể không đạt ngưỡng.

### Ví dụ đổi tên bằng git mv

Trong working tree:

~~~bash
git mv src/OldParser.java src/Parser.java
git status --short
~~~

git mv thực hiện việc di chuyển file và cập nhật index. Git có thể hiển thị trạng thái rename trong git status nhờ cơ chế nhận diện tương đồng.

Có thể thực hiện việc di chuyển bằng công cụ hệ thống tệp rồi stage thay đổi:

~~~bash
mv src/OldParser.java src/Parser.java
git add -A
~~~

Kết quả lưu trong index cũng là snapshot với đường dẫn cũ bị xóa và đường dẫn mới được thêm. git mv là tiện ích giúp thao tác và stage đồng bộ; nó không tạo ra một loại object rename đặc biệt.

## 3. Dùng -M hoặc --find-renames

Tùy chọn -M bật phát hiện rename. Dạng dài tương ứng là --find-renames:

~~~bash
git diff -M HEAD~1 HEAD
git diff --find-renames HEAD~1 HEAD
~~~

Trong nhiều lệnh diff thông dụng, rename detection đã được bật theo cấu hình mặc định. Viết -M tường minh giúp thể hiện ý định của lệnh và dễ điều chỉnh ngưỡng.

Nếu muốn yêu cầu nội dung phải tương đồng ít nhất 80%:

~~~bash
git diff --find-renames=80% HEAD~1 HEAD
~~~

-M<n> hoặc --find-renames=<n> đặt ngưỡng tương đồng. Ví dụ --find-renames=90% yêu cầu cặp file giống nhau ở mức cao hơn --find-renames=50%.

Nên viết rõ dấu % khi truyền ngưỡng để tránh nhầm cách diễn giải giá trị số. Ngưỡng càng cao thì Git càng thận trọng khi ghép cặp; ngưỡng thấp hơn giúp phát hiện file đã được chỉnh sửa nhiều hơn nhưng có thể tạo ra ghép cặp kém thuyết phục.

## 4. Đọc kết quả rename

Xem tên file và trạng thái:

~~~bash
git diff --name-status -M HEAD~1 HEAD
~~~

Ví dụ:

~~~text
R095    src/OldParser.java    src/Parser.java
~~~

Trong output --name-status, mã R095 cho biết Git nhận diện một rename với điểm tương đồng 95%. Tùy thay đổi cụ thể, output có thể chỉ có dòng rename hoặc có thêm các thay đổi khác.

Xem thông tin tóm tắt:

~~~bash
git diff --summary -M HEAD~1 HEAD
~~~

Ví dụ:

~~~text
rename src/OldParser.java => src/Parser.java (95%)
~~~

Xem diff nội dung sau khi Git nhận diện rename:

~~~bash
git diff -M HEAD~1 HEAD -- src/
~~~

Khi một rename có chỉnh sửa nội dung, Git có thể hiển thị diff từ nội dung file cũ sang nội dung file mới. Người đọc sẽ thấy phần dòng thay đổi trong cùng một file logic, thay vì chỉ thấy một file bị xóa và một file mới được thêm.

## 5. Điều chỉnh ngưỡng rename

Ngưỡng là một lựa chọn giữa độ nhạy và độ chắc chắn:

~~~bash
# Ngưỡng thấp hơn: có thể nhận ra file đã thay đổi nhiều
git diff --find-renames=30% BASE TARGET

# Ngưỡng cao hơn: chỉ ghép các cặp rất giống nhau
git diff --find-renames=90% BASE TARGET
~~~

Ví dụ:

- File đổi tên và chỉ sửa một dòng thường dễ đạt ngưỡng cao.
- File đổi tên đồng thời tái cấu trúc phần lớn nội dung có thể chỉ đạt ngưỡng thấp.
- Hai file độc lập có boilerplate giống nhau đôi khi có thể bị ghép nhầm ở ngưỡng thấp.

Không có một ngưỡng duy nhất đúng cho mọi repository. Nếu output rename trông không hợp lý, hãy thử một ngưỡng khác và kiểm tra nội dung của cả hai phía.

## 6. Phát hiện sao chép bằng -C

Rename thường ghép một file bị xóa với một file được thêm. Copy detection tìm một file nguồn vẫn còn tồn tại và một file mới có nội dung tương tự.

Tùy chọn -C hoặc --find-copies bật copy detection:

~~~bash
git diff -C BASE TARGET
git diff --find-copies=80% BASE TARGET
~~~

Khi phát hiện copy, output có thể dùng mã C cùng điểm tương đồng, ví dụ C100.

### Ví dụ sao chép file

Giả sử bạn giữ nguyên src/BaseParser.java và tạo src/StrictParser.java bằng cách sao chép rồi chỉnh sửa một số dòng:

~~~bash
cp src/BaseParser.java src/StrictParser.java
# Chỉnh sửa src/StrictParser.java
git add src/StrictParser.java
~~~

Khi so sánh index hoặc commit, copy detection có thể nhận ra file mới bắt nguồn từ một file đã tồn tại:

~~~bash
git diff --cached --find-copies=80%
~~~

Kết quả phụ thuộc vào việc Git có xem file nguồn là ứng viên phù hợp hay không. Mặc định, copy detection thường chỉ xét các file nguồn đã được sửa trong cùng changeset, nhằm tránh phải so sánh mọi file không thay đổi.

## 7. Khi nào cần --find-copies-harder?

Nếu file nguồn không thay đổi, copy detection mặc định có thể không xét file đó làm nguồn. Dùng --find-copies-harder cùng -C để Git xem cả các file không thay đổi như ứng viên nguồn:

~~~bash
git diff -C --find-copies-harder BASE TARGET
~~~

Ví dụ, src/BaseParser.java vẫn giữ nguyên nhưng src/StrictParser.java được tạo từ nó. --find-copies-harder cho phép Git so sánh file mới với cả những file nguồn không thay đổi.

Tùy chọn này có thể tốn thời gian đáng kể trong repository lớn vì số cặp file cần so sánh tăng lên. Chỉ dùng khi cần tìm nguồn copy từ một file không thay đổi, thay vì bật thường xuyên cho mọi diff.

Có thể kết hợp ngưỡng:

~~~bash
git diff -C80% --find-copies-harder BASE TARGET
~~~

Hoặc dùng cách viết dài:

~~~bash
git diff --find-copies=80% --find-copies-harder BASE TARGET
~~~

--find-copies-harder không thay thế -C; hãy bật copy detection bằng -C hoặc --find-copies cùng với tùy chọn này.

## 8. Phân biệt rename và copy

| Tình huống | Dấu hiệu trong snapshot | Kết quả diff có thể nhận diện |
| --- | --- | --- |
| Đổi tên file, nội dung giữ nguyên | Path cũ mất, path mới xuất hiện | R100 |
| Đổi tên và sửa một phần | Path cũ mất, path mới xuất hiện với nội dung tương tự | Rnnn nếu đạt ngưỡng |
| Sao chép file, giữ file nguồn | Path nguồn còn, path mới xuất hiện | Cnnn nếu copy detection tìm được nguồn |
| Sao chép từ file nguồn không thay đổi | Path nguồn không có thay đổi trong changeset | Cần -C --find-copies-harder để xét nguồn này |
| Viết lại file hoàn toàn sau khi đổi tên | Path cũ mất, path mới xuất hiện nhưng nội dung ít tương đồng | Có thể hiển thị D và A |

R và C là nhãn do diff tạo ra để trình bày. Chúng không phải loại trạng thái riêng được lưu trực tiếp trong commit tree.

## 9. Tắt rename detection bằng --no-renames

Đôi khi bạn muốn xem chính xác thay đổi ở dạng xóa và thêm, không muốn Git ghép các file thành rename:

~~~bash
git diff --no-renames BASE TARGET
~~~

Lệnh này hữu ích khi:

- Bạn đang kiểm tra heuristic có ghép nhầm cặp file hay không.
- Muốn xem nội dung file cũ bị xóa và file mới được thêm độc lập.
- Muốn đơn giản hóa output cho một công cụ downstream không cần rename detection.
- Cần so sánh kết quả có và không có rename detection.

So sánh:

~~~bash
git diff -M --name-status BASE TARGET
git diff --no-renames --name-status BASE TARGET
~~~

Nếu một cặp được hiển thị là R ở lệnh đầu, lệnh thứ hai có thể hiển thị D cho path cũ và A cho path mới.

## 10. Giới hạn chi phí phát hiện rename/copy

Rename/copy detection cần so sánh các ứng viên xóa, thêm và nguồn copy. Khi changeset có rất nhiều file, số phép so sánh có thể tăng nhanh và làm diff chậm.

Tùy chọn -l<num> đặt giới hạn số lượng ứng viên rename/copy:

~~~bash
git diff -M -l200 BASE TARGET
~~~

Nếu số lượng mục tiêu cần xét vượt ngưỡng này, Git có thể bỏ qua bước phát hiện rename/copy để tránh chi phí quá lớn. Giá trị này là giới hạn hiệu năng, không phải ngưỡng tương đồng.

Có thể cấu hình giới hạn mặc định cho repository hoặc người dùng:

~~~bash
git config diff.renameLimit 200
~~~

Tùy chọn -l của từng lệnh cho phép đặt giới hạn trực tiếp. Khi điều tra vì sao Git không phát hiện rename trong changeset lớn, hãy kiểm tra cả ngưỡng tương đồng và giới hạn rename/copy.

## 11. Các thiết lập liên quan

Git có cấu hình diff.renames để điều khiển việc nhận diện:

~~~bash
# Bật phát hiện rename
git config diff.renames true

# Tắt phát hiện rename
git config diff.renames false

# Bật nhận diện copy cùng rename
git config diff.renames copies
~~~

Giá trị cấu hình ảnh hưởng tới cách các lệnh diff trình bày thay đổi. Có thể kiểm tra cấu hình đang có và nguồn cấu hình:

~~~bash
git config --show-origin --get diff.renames
git config --show-origin --get diff.renameLimit
~~~

Không có output thường có nghĩa giá trị chưa được đặt tường minh; Git sẽ dùng mặc định của phiên bản và lệnh đang chạy. Tùy chọn dòng lệnh như --no-renames, -M hoặc -C giúp thể hiện rõ hành vi mong muốn cho một lần chạy.

## 12. Đọc các dạng output khác nhau

### --name-status

Phù hợp khi chỉ cần tên file và trạng thái:

~~~bash
git diff --name-status -M -C BASE TARGET
~~~

Các mã chính:

| Mã | Ý nghĩa |
| --- | --- |
| A | File được thêm. |
| D | File bị xóa. |
| M | File bị sửa. |
| Rnnn | Rename với điểm tương đồng nnn%. |
| Cnnn | Copy với điểm tương đồng nnn%. |

Với rename/copy, output thường chứa cả path nguồn và path đích. Đừng giả định mỗi dòng chỉ có một đường dẫn.

### --summary

Phù hợp để xem thông tin tổng quan:

~~~bash
git diff --summary -M -C BASE TARGET
~~~

Output có thể cho biết rename, copy, file mode thay đổi, file được tạo hoặc xóa.

### --raw

Phù hợp khi cần mode và OID:

~~~bash
git diff --raw -M BASE TARGET
~~~

Raw diff chứa thông tin mode cũ/mới, object ID cũ/mới và mã trạng thái. Với rename hoặc copy, output có thêm thông tin điểm tương đồng và hai đường dẫn. Đây là định dạng thấp hơn, phù hợp cho công cụ chuyên biệt nhưng khó đọc bằng mắt hơn --name-status.

### --stat

~~~bash
git diff --stat -M BASE TARGET
~~~

Thống kê có thể gom cặp rename vào một dòng hiển thị đường dẫn cũ và mới. Nó hữu ích để nắm phạm vi thay đổi, nhưng không thay thế việc xem diff nội dung.

## 13. Xem rename/copy trong lịch sử commit

Các tùy chọn tương tự có thể dùng khi đọc lịch sử:

~~~bash
# Tóm tắt rename trong commit mới nhất
git show --summary -M HEAD

# Liệt kê file thay đổi qua các commit
git log --name-status -M

# Hiển thị thống kê với rename detection
git log --stat -M
~~~

Nếu muốn tăng ngưỡng:

~~~bash
git log --name-status --find-renames=90%
~~~

Các lệnh lịch sử vẫn đang phân tích sự khác nhau giữa các snapshot. Việc một commit được hiển thị có rename không có nghĩa object commit chứa một thao tác rename riêng.

## 14. Tình huống heuristic có thể bỏ sót hoặc ghép nhầm

### Đổi tên rồi viết lại gần như toàn bộ file

Nếu nội dung mới khác nhiều so với nội dung cũ, điểm tương đồng có thể thấp hơn ngưỡng. Git sẽ hiển thị delete/add thay vì rename. Có thể thử ngưỡng thấp hơn, nhưng cần xác nhận cặp file bằng ngữ cảnh thực tế.

### Hai file độc lập có nội dung gần giống

Các file mẫu, file sinh tự động hoặc nhiều module có boilerplate giống nhau có thể bị ghép nhầm. Ngưỡng thấp làm rủi ro này tăng lên. Hãy kiểm tra đường dẫn, nội dung và lịch sử liên quan.

### Copy từ file nguồn không thay đổi

Nếu chỉ dùng -C, Git có thể không xét file nguồn không thay đổi. Thử -C --find-copies-harder khi cần, nhưng cân nhắc chi phí trên repository lớn.

### Một changeset có quá nhiều file

Git có thể bỏ qua phát hiện rename/copy do giới hạn số ứng viên. Kiểm tra -l<num> và diff.renameLimit, hoặc chạy lại trên phạm vi hẹp hơn.

### File binary hoặc file được sinh tự động

Điểm tương đồng vẫn là heuristic về nội dung; nó không hiểu cấu trúc nghiệp vụ hay ý nghĩa của file. Với file binary, generated code hoặc dữ liệu lớn, hãy xác nhận bằng metadata và ngữ cảnh thay đổi thay vì chỉ dựa vào phần trăm.

## 15. Quy trình thực hành: kiểm tra một lần đổi tên

Giả sử bạn đổi tên và sửa một phần file:

~~~bash
git mv src/OldParser.java src/Parser.java
# Chỉnh sửa src/Parser.java
git add -A
~~~

Kiểm tra trạng thái và output:

~~~bash
git status --short
git diff --cached --name-status -M
git diff --cached --summary -M
git diff --cached -M
~~~

Nếu Git không nhận ra rename:

~~~bash
# Thử ngưỡng thấp hơn
git diff --cached --find-renames=30%

# Tắt rename detection để xem xóa/thêm riêng
git diff --cached --no-renames
~~~

So sánh các output để biết Git đang ghép cặp như thế nào. Trước khi commit, xác nhận path cũ đã biến mất, path mới có nội dung đúng và diff thể hiện đúng ý định.

## 16. Quy trình thực hành: tìm nguồn của một file copy

Giả sử src/BaseParser.java vẫn tồn tại, còn src/StrictParser.java được tạo từ bản sao và chỉnh sửa:

~~~bash
cp src/BaseParser.java src/StrictParser.java
# Chỉnh sửa src/StrictParser.java
git add -A
~~~

Thử copy detection thông thường:

~~~bash
git diff --cached -C --name-status
~~~

Nếu không nhận diện vì nguồn không thay đổi, thử:

~~~bash
git diff --cached -C --find-copies-harder --name-status
~~~

Để tăng độ tương đồng tối thiểu:

~~~bash
git diff --cached --find-copies=80% --find-copies-harder
~~~

Nếu output báo Cnnn, hãy kiểm tra cả file nguồn và file đích. Điểm tương đồng cao cho thấy nội dung giống nhau theo thuật toán, nhưng không chứng minh người tạo file đã thực hiện thao tác copy theo một cách cụ thể.

## 17. Những lỗi thường gặp

### Nghĩ Git lưu rename thành một thao tác riêng

Không đúng. Commit lưu snapshot tree. Rename được suy luận khi Git so sánh path bị xóa với path được thêm.

### Nghĩ git mv bắt buộc để Git nhận ra rename

Không đúng. Di chuyển file bằng công cụ hệ thống rồi stage đúng thay đổi vẫn có thể được nhận diện. git mv là tiện ích thực hiện di chuyển và cập nhật index.

### Nghĩ -C luôn tìm mọi file nguồn có thể copy

Không đúng. Mặc định, copy detection thường giới hạn nguồn ở các file đã thay đổi. Dùng -C --find-copies-harder để xét cả file không thay đổi.

### Hạ ngưỡng similarity quá thấp để buộc nhận diện

Điều này có thể ghép nhầm các file không liên quan. Hãy xem cả hai path và nội dung thay vì chỉ cố đạt mã R.

### Nghĩ R100 và C100 là metadata commit

Đây là kết quả trình bày diff, không phải thuộc tính được lưu như một loại thao tác trong commit.

### Không nhận diện rename trong changeset lớn

Kiểm tra -l<num> và diff.renameLimit. Git có thể bỏ qua phát hiện vì giới hạn hiệu năng.

### Dùng --find-copies-harder cho mọi lệnh

Tùy chọn này có thể tốn nhiều thời gian vì mở rộng tập nguồn copy. Chỉ bật khi cần tìm nguồn không thay đổi.

## 18. Ghi nhớ

- Git lưu snapshot gồm path và object; rename/copy là suy luận khi tạo diff.
- -M hoặc --find-renames bật phát hiện rename; -C hoặc --find-copies bật phát hiện copy.
- Ngưỡng như --find-renames=80% quyết định mức tương đồng tối thiểu để ghép cặp.
- Rnnn là rename và Cnnn là copy cùng điểm tương đồng phần trăm.
- -C thường tìm nguồn copy trong các file đã thay đổi; -C --find-copies-harder xét cả file nguồn không thay đổi.
- --no-renames tắt rename detection để xem delete/add riêng.
- -l<num> và diff.renameLimit giới hạn chi phí phát hiện.
- --name-status, --summary, --raw và --stat cung cấp các góc nhìn khác nhau về kết quả.
- Ngưỡng thấp có thể ghép nhầm; ngưỡng cao có thể bỏ sót rename thật.
- Điểm tương đồng không chứng minh ý định hoặc quan hệ lịch sử của người tạo thay đổi.

Rename và copy detection làm cho diff dễ đọc hơn bằng cách suy luận mối liên hệ giữa các file ở hai snapshot. Khi hiểu ngưỡng tương đồng, cách chọn nguồn copy và giới hạn hiệu năng, bạn có thể diễn giải output chính xác hơn, điều chỉnh lệnh theo tình huống và tránh coi kết quả heuristic là sự thật tuyệt đối về cách thay đổi được tạo ra.
