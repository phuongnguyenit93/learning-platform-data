# Xem thống kê thay đổi bằng --stat, --name-only và --name-status

Khi review một thay đổi, đôi khi bạn chưa cần đọc từng dòng diff. Trước hết, bạn muốn biết có bao nhiêu file bị tác động, thay đổi tập trung ở thư mục nào, file nào được thêm hoặc xóa, và có file nào bị đổi tên. Git cung cấp các tùy chọn thống kê để trả lời nhanh những câu hỏi đó.

Ba tùy chọn thường dùng là <code>--stat</code>, <code>--name-only</code> và <code>--name-status</code>. <code>--stat</code> cho biết quy mô thay đổi theo từng file bằng số dòng thêm/xóa và biểu đồ; <code>--name-only</code> chỉ liệt kê đường dẫn; <code>--name-status</code> liệt kê đường dẫn kèm trạng thái như thêm, sửa, xóa hoặc đổi tên. Chúng có thể kết hợp với các dạng so sánh khác nhau, từ working tree và staging area đến hai commit hoặc hai branch.

Bài thuộc chương **So sánh thay đổi** của module **SOURCE_CONTROL_GIT**. Module hướng dẫn Git từ working tree, staging area, commit và lịch sử đến branch, merge, rebase, remote và tag; đồng thời rèn cách cộng tác qua nhánh, giải quyết xung đột, truy tìm thay đổi và khôi phục thao tác sai mà vẫn bảo toàn lịch sử quan trọng. Biết đọc thống kê giúp bạn đánh giá phạm vi thay đổi trước khi xem diff chi tiết, commit hoặc tích hợp branch.

## 1. Vì sao cần xem thống kê thay đổi?

Một diff có thể chứa hàng nghìn dòng. Trước khi đọc chi tiết, hãy xác định phạm vi:

- Có bao nhiêu file thay đổi?
- File nào được thêm, sửa, xóa hoặc đổi tên?
- Thay đổi tập trung ở thư mục hoặc thành phần nào?
- Có file nào thay đổi rất lớn bất thường?
- Một commit có chỉ sửa tài liệu hay còn tác động mã nguồn?
- Hai branch khác nhau ở những đường dẫn nào?

Thống kê không thay thế việc review nội dung. Nó là bước định hướng để bạn biết nên mở file nào và cần chú ý điều gì.

## 2. Hiểu ba tùy chọn chính

| Tùy chọn | Nội dung hiển thị | Phù hợp khi |
|---|---|---|
| <code>--stat</code> | Mỗi file, số dòng thêm/xóa và thanh biểu đồ; cuối cùng có tổng số file/dòng | Đánh giá quy mô thay đổi nhanh |
| <code>--name-only</code> | Chỉ đường dẫn của các file thay đổi | Lấy danh sách file để kiểm tra hoặc truyền cho công cụ khác |
| <code>--name-status</code> | Trạng thái thay đổi và đường dẫn file | Biết file được thêm, sửa, xóa, đổi tên hoặc sao chép |

Ví dụ:

~~~bash
git diff --stat
git diff --name-only
git diff --name-status
~~~

Ba lệnh trên dùng cùng phạm vi so sánh mặc định của <code>git diff</code>: thay đổi trong working tree so với index. Vì vậy, kết quả không nhất thiết bao gồm nội dung đã stage.

## 3. Chọn đúng phạm vi so sánh trước khi xem thống kê

Các tùy chọn thống kê chỉ thay đổi cách trình bày kết quả. Phần quan trọng vẫn là bạn đang so sánh hai trạng thái nào.

### Working tree so với index

~~~bash
git diff --stat
git diff --name-only
git diff --name-status
~~~

Đây là thay đổi chưa stage. Nếu bạn vừa sửa file nhưng chưa chạy <code>git add</code>, chúng sẽ xuất hiện ở đây.

### Index so với commit hiện tại

~~~bash
git diff --cached --stat
git diff --cached --name-only
git diff --cached --name-status
~~~

<code>--cached</code> là alias của <code>--staged</code>. Các lệnh này cho biết nội dung đã stage so với <code>HEAD</code>, tức phần sẽ được đưa vào commit tiếp theo nếu bạn commit ngay.

### Toàn bộ thay đổi chưa commit

Muốn xem working tree so với <code>HEAD</code>, bao gồm cả phần đã stage và chưa stage:

~~~bash
git diff HEAD --stat
git diff HEAD --name-only
git diff HEAD --name-status
~~~

Đây thường là cách hữu ích để xem tổng phạm vi thay đổi trước commit. Với repository mới chưa có commit đầu tiên, <code>HEAD</code> chưa tồn tại; khi đó hãy kiểm tra trạng thái index và working tree riêng.

### File untracked không xuất hiện trong diff thông thường

Các lệnh <code>git diff</code> không tự đưa file untracked vào kết quả vì file đó chưa nằm trong index. Kiểm tra chúng bằng:

~~~bash
git status --short
~~~

File untracked thường có trạng thái <code>??</code>. Nếu cần xem nội dung file mới trong diff trước khi stage toàn bộ, có thể đánh dấu intent-to-add:

~~~bash
git add -N path/to/new-file.txt
git diff --stat
git diff --name-status
~~~

<code>git add -N</code> tạo entry intent-to-add trong index để Git có thể hiển thị diff của file mới; nó chưa stage toàn bộ nội dung file như <code>git add</code> thông thường. Sau khi kiểm tra, bạn có thể stage file đầy đủ hoặc bỏ entry này theo nhu cầu. File bị ignore cũng không tự xuất hiện; dùng <code>git status --ignored</code> để kiểm tra nếu nghi ngờ quy tắc ignore đang che file.

### So sánh hai commit

~~~bash
git diff --stat <commit-a> <commit-b>
git diff --name-only <commit-a> <commit-b>
git diff --name-status <commit-a> <commit-b>
~~~

Git hiển thị các đường dẫn khác nhau giữa snapshot của hai commit. Thứ tự hai đầu mút có ý nghĩa đối với hướng thêm/xóa trong <code>--name-status</code>: file có trong commit thứ hai nhưng không có ở commit thứ nhất sẽ được xem là thêm.

### So sánh commit hiện tại với commit cha

~~~bash
git diff --stat HEAD^ HEAD
git diff --name-status HEAD^ HEAD
~~~

Với commit thông thường, đây là thay đổi được giới thiệu bởi commit mới nhất. Commit merge có nhiều parent; <code>HEAD^</code> mặc định chỉ parent thứ nhất. Nếu cần so với parent khác, chỉ định rõ, ví dụ <code>HEAD^2</code>.

### So sánh hai branch

So sánh snapshot tại tip của hai branch:

~~~bash
git diff --stat main feature/payment
git diff --name-status main feature/payment
~~~

Nếu muốn xem những thay đổi trên branch feature kể từ điểm hai branch tách nhau, dùng cú pháp ba chấm:

~~~bash
git diff --stat main...feature/payment
git diff --name-status main...feature/payment
~~~

Với <code>git diff</code>, <code>main...feature/payment</code> tương đương so sánh merge-base của hai branch với tip của <code>feature/payment</code>. Nó hữu ích khi review phần branch feature mang đến so với nhánh nền. Cú pháp này không có cùng ý nghĩa với mọi lệnh Git; đặc biệt, cách dùng ba chấm trong <code>git log</code> có cách diễn giải khác.

## 4. Đọc kết quả của --stat

Ví dụ:

~~~text
 src/payment/RetryPolicy.java | 24 ++++++++++++++++++------
 src/payment/RetryPolicyTest.java | 18 ++++++++++++++++++
 README.md | 4 ++--
 3 files changed, 38 insertions(+), 8 deletions(-)
~~~

Ý nghĩa:

- Cột đầu là đường dẫn file.
- Con số sau dấu <code>|</code> là tổng số dòng thay đổi được thống kê cho file.
- Các dấu <code>+</code> biểu thị dòng thêm.
- Các dấu <code>-</code> biểu thị dòng xóa.
- Thanh biểu đồ giúp so sánh tương đối quy mô giữa các file.
- Dòng cuối tổng hợp số file thay đổi, số dòng thêm và số dòng xóa.

Trong ví dụ, có ba file thay đổi, tổng cộng 38 dòng thêm và 8 dòng xóa. Điều này không có nghĩa ứng dụng tăng đúng 30 dòng mã nguồn có ý nghĩa: diff tính dòng theo cách Git so sánh nội dung, và thay đổi định dạng hoặc dòng bị thay thế cũng được tính.

Với file nhị phân, Git không đếm số dòng như file văn bản. <code>--stat</code> có thể hiển thị thông tin dạng <code>Bin old-size -> new-size bytes</code>; hãy đọc nó như thay đổi kích thước object/file được so sánh, không phải số dòng thêm hoặc xóa.

### Đọc thanh biểu đồ đúng cách

Thanh biểu đồ là hình ảnh tương đối để nhận biết file nào có thay đổi lớn hơn. Độ dài thanh phụ thuộc cấu hình chiều rộng và giới hạn hiển thị. Không dùng chiều dài thanh để suy ra chính xác số dòng; hãy đọc số liệu ở trước thanh.

Một file có nhiều dòng thay đổi chưa chắc phức tạp nhất. Ví dụ, file generated hoặc file khóa dependency có thể thay đổi hàng nghìn dòng nhưng ít logic cần review hơn một thay đổi nhỏ trong xử lý phân quyền.

### Tùy chỉnh chiều rộng thống kê

<code>--stat</code> cho phép điều chỉnh chiều rộng tổng thể, chiều rộng cột tên và số file tối đa:

~~~bash
# Giới hạn chiều rộng tổng thể
git diff --stat=100

# Chiều rộng tổng thể, cột tên file, số file hiển thị
git diff --stat=100,60,20
~~~

Nếu thống kê bị cắt tên file hoặc quá rộng trong terminal, hãy điều chỉnh các giá trị này. Bỏ qua các giới hạn nếu bạn cần output đầy đủ để đọc hoặc lưu vào báo cáo.

## 5. Chỉ liệt kê file bằng --name-only

Ví dụ:

~~~bash
git diff --name-only HEAD
~~~

Kết quả có thể là:

~~~text
README.md
src/payment/RetryPolicy.java
src/payment/RetryPolicyTest.java
~~~

Tùy chọn này hữu ích khi bạn chỉ muốn biết phạm vi file, không cần biết số dòng thêm/xóa hoặc loại thay đổi.

Một số tình huống:

- Tạo danh sách file cần review thủ công.
- Xác định file nào thay đổi giữa hai release.
- Kiểm tra một commit chỉ chạm đến thư mục tài liệu hay có ảnh hưởng mã nguồn.
- Kết hợp với lệnh khác để lọc hoặc phân nhóm đường dẫn.

Ví dụ chỉ lấy danh sách file trong commit mới nhất:

~~~bash
git diff-tree --no-commit-id --name-only -r HEAD
~~~

Hoặc dùng <code>git show</code>:

~~~bash
git show --format= --name-only HEAD
~~~

Với các lệnh lịch sử, hãy chọn đúng commit hoặc khoảng commit. <code>git diff --name-only HEAD</code> không phải cách liệt kê file của riêng commit mới nhất; nếu chỉ định một đầu mút, Git có thể so sánh working tree với commit đó.

## 6. Biết loại thay đổi bằng --name-status

<code>--name-status</code> thêm mã trạng thái trước mỗi đường dẫn:

~~~bash
git diff --name-status HEAD^ HEAD
~~~

Ví dụ:

~~~text
M	README.md
A	src/payment/RetryPolicy.java
D	src/legacy/OldRetry.java
R087	src/payment/RetryHandler.java	src/payment/RetryPolicy.java
~~~

Các mã phổ biến:

| Mã | Ý nghĩa |
|---|---|
| <code>A</code> | Added — file được thêm |
| <code>M</code> | Modified — file được sửa |
| <code>D</code> | Deleted — file bị xóa |
| <code>R</code> | Renamed — file được nhận diện là đổi tên |
| <code>C</code> | Copied — file được nhận diện là bản sao |
| <code>T</code> | Type changed — loại file hoặc mode thay đổi |
| <code>U</code> | Unmerged — file đang ở trạng thái conflict |
| <code>X</code> | Unknown — Git không xác định được trạng thái |
| <code>B</code> | Pairing broken — trường hợp ghép cặp tên file bị phá vỡ trong một số output diff |

Với rename hoặc copy, Git có thể kèm điểm tương đồng từ 0 đến 100, ví dụ <code>R087</code> nghĩa là rename được nhận diện với mức tương đồng 87%. Đây là kết quả phát hiện dựa trên nội dung và ngưỡng cấu hình, không phải bằng chứng file đã được đổi tên bằng một thao tác cụ thể.

### Rename detection

Git lưu snapshot của file, không lưu một thao tác rename độc lập như một event bắt buộc. Khi so sánh hai snapshot, Git cố gắng nhận diện một file bị xóa và một file được thêm có nội dung đủ giống nhau để coi là rename.

Để điều chỉnh:

~~~bash
# Bật phát hiện rename
git diff --find-renames --name-status HEAD^ HEAD

# Dùng ngưỡng tương đồng 60%
git diff --find-renames=60% --name-status HEAD^ HEAD

# Tắt phát hiện rename
git diff --no-renames --name-status HEAD^ HEAD
~~~

Nếu tắt rename detection, một lần đổi tên có thể hiển thị thành <code>D</code> cho đường dẫn cũ và <code>A</code> cho đường dẫn mới. Khi kiểm tra lịch sử refactor hoặc di chuyển file, hãy cân nhắc bật rename detection.

### Copy detection

Copy detection có thể được yêu cầu bằng:

~~~bash
git diff --find-copies --name-status <commit-a> <commit-b>
~~~

Git cần xác định nguồn có khả năng được sao chép. Tùy chọn <code>--find-copies-harder</code> yêu cầu xét cả file không thay đổi làm nguồn copy, nhưng có thể tăng đáng kể chi phí tính toán trong repository lớn:

~~~bash
git diff --find-copies-harder --name-status <commit-a> <commit-b>
~~~

Chỉ bật chế độ này khi cần phát hiện copy kỹ hơn và chấp nhận thời gian xử lý tăng.

## 7. Kết hợp thống kê với git show và git log

### Xem thống kê của một commit

~~~bash
git show --stat <commit>
~~~

Muốn chỉ liệt kê tên file:

~~~bash
git show --format= --name-only <commit>
~~~

Muốn xem trạng thái file:

~~~bash
git show --format= --name-status <commit>
~~~

<code>git show</code> mặc định hiển thị nội dung commit và diff. Các tùy chọn trên thay đổi phần diff được trình bày.

### Xem thống kê của nhiều commit

~~~bash
git log --stat -5
~~~

Lệnh hiển thị năm commit gần nhất cùng thống kê thay đổi của mỗi commit.

Các biến thể:

~~~bash
git log --name-only -5
git log --name-status -5
~~~

Bạn có thể kết hợp với giới hạn theo branch, tác giả, thời gian hoặc đường dẫn:

~~~bash
git log --stat --since="2 weeks ago" main
git log --name-status --author="Linh" -10
git log --name-only -- src/payment/
~~~

Lưu ý <code>git log --name-only -- src/payment/</code> lọc lịch sử theo đường dẫn được chỉ định. Nó không có nghĩa chỉ hiển thị các file nằm trong thư mục đó cho mọi commit không liên quan.

## 8. Các kiểu thống kê bổ sung

Ngoài ba tùy chọn chính, Git có các định dạng khác hữu ích khi đọc hoặc tự động hóa.

### --shortstat

Chỉ hiển thị dòng tổng kết cuối, không liệt kê từng file:

~~~bash
git diff --shortstat
~~~

Ví dụ:

~~~text
 3 files changed, 38 insertions(+), 8 deletions(-)
~~~

Dùng khi bạn chỉ cần số tổng hợp cho báo cáo hoặc kiểm tra nhanh.

### --numstat

Hiển thị số dòng thêm, số dòng xóa và đường dẫn theo định dạng thuận tiện cho xử lý bằng script:

~~~bash
git diff --numstat
~~~

Ví dụ:

~~~text
18	6	src/payment/RetryPolicy.java
18	0	src/payment/RetryPolicyTest.java
2	2	README.md
~~~

Với file nhị phân, hai cột số thường là <code>-</code> vì Git không thống kê số dòng thêm/xóa như file văn bản.

### --compact-summary

Hiển thị thống kê gọn kèm một số thông tin như mode, tạo file hoặc xóa file:

~~~bash
git diff --compact-summary
~~~

Tùy chọn này hữu ích khi bạn muốn một báo cáo ngắn hơn <code>--stat</code> nhưng vẫn cần biết thay đổi loại file hoặc mode.

### --summary

Hiển thị thông tin tổng quan về thay đổi như tạo file, xóa file, mode thay đổi, rename hoặc copy được phát hiện:

~~~bash
git diff --summary
~~~

### --dirstat

Thống kê tỷ lệ thay đổi theo thư mục:

~~~bash
git diff --dirstat
~~~

Một số biến thể:

~~~bash
# Tính theo thay đổi nội dung
git diff --dirstat=changes

# Tính theo số file
git diff --dirstat=files

# Bao gồm tỷ lệ cộng dồn ở thư mục cha
git diff --dirstat=cumulative
~~~

<code>--dirstat</code> hữu ích khi muốn biết thay đổi tập trung ở thành phần nào của repository. Đây là thống kê theo cách tính của tùy chọn được chọn, không phải tỷ lệ rủi ro hay mức độ quan trọng nghiệp vụ.

## 9. Dùng thống kê để review branch

Giả sử bạn chuẩn bị review branch <code>feature/payment-retry</code> trước khi merge vào <code>main</code>.

Trước hết, cập nhật thông tin remote:

~~~bash
git fetch origin
~~~

Xem số file và quy mô thay đổi kể từ điểm tách branch:

~~~bash
git diff --stat origin/main...feature/payment-retry
~~~

Xem file nào bị tác động:

~~~bash
git diff --name-only origin/main...feature/payment-retry
~~~

Xem loại thay đổi:

~~~bash
git diff --name-status origin/main...feature/payment-retry
~~~

Sau đó mở diff chi tiết:

~~~bash
git diff origin/main...feature/payment-retry
~~~

Quy trình này giúp bạn đi từ phạm vi tổng thể đến từng dòng thay đổi. Nếu thống kê cho thấy có file cấu hình production, migration database hoặc thay đổi dependency lớn, hãy ưu tiên review các file đó.

## 10. Lọc thống kê theo đường dẫn

Bạn có thể giới hạn thống kê ở một file hoặc thư mục:

~~~bash
git diff --stat HEAD^ HEAD -- src/payment/
git diff --name-status main...feature/payment -- src/payment/
~~~

Dấu <code>--</code> phân tách tùy chọn/commit range với pathspec. Nó giúp Git hiểu phần sau là đường dẫn, kể cả khi tên đường dẫn có thể bị hiểu nhầm là một revision.

Ví dụ chỉ xem một file:

~~~bash
git diff --name-only HEAD^ HEAD -- README.md
~~~

Nếu pathspec có ký tự đặc biệt hoặc bạn muốn khớp chính xác một đường dẫn, hãy tìm hiểu thêm các dạng pathspec như <code>:(literal)</code> hoặc <code>:(glob)</code>.

## 11. Dùng output cho script và công cụ khác

<code>--name-only</code> và <code>--name-status</code> thường dễ đọc với con người, nhưng đường dẫn file có thể chứa khoảng trắng, tab hoặc thậm chí newline. Nếu script phân tích output theo từng dòng hoặc tách bằng tab, nó có thể xử lý sai tên file đặc biệt.

Đối với script, ưu tiên tùy chọn <code>-z</code> để dùng NUL làm dấu phân cách:

~~~bash
git diff --name-only -z <commit-a> <commit-b>
git diff --name-status -z <commit-a> <commit-b>
git diff --numstat -z <commit-a> <commit-b>
~~~

Output NUL-delimited cần được đọc bằng công cụ có hỗ trợ chuỗi byte/NUL; không nên đưa thẳng vào biến shell thông thường vì nhiều shell không giữ được ký tự NUL.

Ví dụ Bash xử lý danh sách tên file an toàn:

~~~bash
while IFS= read -r -d '' path; do
    printf 'Changed path: %q\n' "$path"
done < <(git diff --name-only -z HEAD^ HEAD)
~~~

Với <code>--name-status -z</code>, parser cần xử lý số lượng path theo loại trạng thái: A/M/D thường có một path; R/C có path nguồn và path đích. Hãy đọc tài liệu <code>git diff</code> cho định dạng NUL của phiên bản Git đang dùng thay vì giả định mọi record đều chỉ có một đường dẫn.

### Khi cần số dòng cho báo cáo máy đọc

~~~bash
git diff --numstat -z origin/main...HEAD
~~~

<code>--numstat</code> cung cấp số dòng thêm/xóa riêng cho từng file. File nhị phân có thể trả <code>-</code> ở hai cột số. Không nên ép các giá trị đó thành số 0 mà không giữ lại thông tin rằng file là nhị phân.

## 12. Kết hợp với diff filter

Git có tùy chọn <code>--diff-filter</code> để chỉ hiển thị một số loại thay đổi:

~~~bash
# Chỉ file được thêm hoặc sửa
git diff --name-status --diff-filter=AM

# Chỉ file bị xóa
git diff --name-only --diff-filter=D

# File được thêm, sửa, đổi tên hoặc sao chép
git diff --name-status --diff-filter=AMRC
~~~

Các chữ cái tương ứng với trạng thái như A, C, D, M, R, T, U, X, B. Chữ thường có thể dùng để loại trừ trạng thái tương ứng trong một số cách kết hợp; tham khảo <code>git help diff</code> để kiểm tra cú pháp cụ thể.

Diff filter rất hữu ích khi muốn tìm file mới được thêm, xác định file bị xóa hoặc tạo báo cáo chỉ gồm rename. Kết hợp với <code>--name-status</code> để giữ thông tin trạng thái.

## 13. Những nhầm lẫn thường gặp

| Nhầm lẫn | Thực tế | Cách kiểm tra đúng |
|---|---|---|
| <code>git diff --stat</code> hiển thị mọi thay đổi chưa commit | Mặc định nó chỉ so working tree với index | Dùng <code>git diff HEAD --stat</code> để so với HEAD |
| <code>--name-only</code> cho biết file được thêm hay xóa | Nó chỉ in đường dẫn | Dùng <code>--name-status</code> |
| <code>--stat</code> cho biết chính xác mức độ rủi ro | Nó chỉ thống kê quy mô dòng/file | Đọc diff và hiểu ngữ cảnh nghiệp vụ |
| Rename luôn được lưu thành trạng thái R | Git phát hiện rename khi so sánh snapshot | Dùng <code>--find-renames</code> và xem ngưỡng |
| <code>git diff A...B</code> giống <code>git log A...B</code> | Ba chấm có cách diễn giải phụ thuộc lệnh | Với diff, đó là merge-base của A và B so với B |
| File binary không xuất hiện trong thống kê | File vẫn có thể xuất hiện nhưng không có số dòng văn bản | Dùng <code>--stat</code>, <code>--name-status</code> hoặc <code>--summary</code> |
| Output theo dòng luôn an toàn cho script | Đường dẫn có thể chứa tab hoặc newline | Dùng <code>-z</code> và parser NUL-aware |
| <code>--name-status</code> chỉ trả một path mỗi dòng | Rename/copy có cả path nguồn và path đích | Xử lý trạng thái R/C riêng |

## 14. Quy trình kiểm tra thống kê trước khi commit hoặc merge

Trước khi commit:

~~~bash
# Thay đổi chưa stage
git diff --stat
git diff --name-status

# Thay đổi đã stage
git diff --cached --stat
git diff --cached --name-status

# Nội dung chính xác sẽ được commit
git diff --cached
~~~

Trước khi merge branch:

~~~bash
git fetch origin
git diff --stat origin/main...feature/payment-retry
git diff --name-status origin/main...feature/payment-retry
git diff origin/main...feature/payment-retry
~~~

Sau khi nhận một commit:

~~~bash
git show --stat --oneline HEAD
git show --format= --name-status HEAD
~~~

Thống kê là bước lọc đầu tiên. Khi thấy file lạ, số dòng tăng bất thường hoặc rename không mong đợi, hãy mở diff chi tiết và kiểm tra lý do trước khi chấp nhận thay đổi.

## 15. Bài tập tự kiểm tra

Tạo repository thử nghiệm với một vài commit:

1. Tạo một file mới, sửa một file hiện có và xóa một file khác.
2. Chạy <code>git diff --stat</code>, <code>git diff --name-only</code> và <code>git diff --name-status</code> trước khi stage.
3. Stage một phần thay đổi và chạy lại ba lệnh với <code>--cached</code>.
4. So sánh <code>git diff HEAD --stat</code> với <code>git diff --stat</code> để thấy khác biệt phạm vi.
5. Tạo commit mới rồi xem thống kê bằng <code>git show --stat HEAD</code>.
6. Đổi tên một file và so sánh kết quả với <code>--find-renames</code> và <code>--no-renames</code>.
7. Tạo hai branch và so sánh <code>main...feature</code> với <code>main feature</code>.
8. Chạy <code>--shortstat</code>, <code>--numstat</code>, <code>--summary</code> và <code>--dirstat</code>; giải thích mỗi định dạng phù hợp với câu hỏi nào.
9. Tạo file có khoảng trắng trong tên và dùng <code>-z</code> để lấy danh sách an toàn cho script.
10. Dùng <code>--diff-filter</code> để chỉ liệt kê file mới được thêm hoặc file bị xóa.

Khi đọc thống kê, hãy xác định đúng hai đầu mút của phép so sánh trước, rồi chọn định dạng phù hợp: <code>--stat</code> để đánh giá quy mô, <code>--name-only</code> để lấy danh sách đường dẫn và <code>--name-status</code> để biết loại thay đổi. Sau đó mở diff chi tiết để xác nhận nội dung và tác động thực tế.
