# Tra cứu trách nhiệm từng dòng bằng git blame và giới hạn diễn giải

## Mục tiêu

Khi đọc một file trong dự án, đôi khi bạn cần biết một dòng được đưa vào lịch sử từ commit nào, ai được ghi nhận là tác giả của commit đó và thay đổi xảy ra vào thời điểm nào. Git cung cấp lệnh `git blame` để lần theo nguồn gốc của từng dòng trong một phiên bản file.

Lệnh cơ bản:

~~~bash
git blame src/PaymentService.java
~~~

`git blame` giúp trả lời câu hỏi: **dòng này được ghi nhận lần cuối là thay đổi trong commit nào?** Nó không tự trả lời ai chịu trách nhiệm nghiệp vụ, ai đưa ra quyết định thiết kế, ai review hay vì sao thay đổi được thực hiện.

Sau bài học, bạn có thể:

- Tra cứu commit gắn với từng dòng trong file.
- Chỉ xem một vùng dòng hoặc một hàm cụ thể.
- Tra cứu file tại một commit, branch hoặc tag đã chọn.
- Đọc các trường thông tin trong kết quả blame.
- Dùng `-w`, `-M`, `-C` để giảm một số sai lệch do định dạng hoặc di chuyển mã.
- Bỏ qua commit định dạng hàng loạt bằng ignore-revs khi có căn cứ.
- Dùng reverse blame để tìm revision cuối cùng trong một khoảng lịch sử mà dòng còn tồn tại.
- Kết hợp blame với `git show`, `git log` và diff để điều tra có ngữ cảnh.
- Trình bày kết quả một cách chính xác, không biến thông tin quy nguồn của Git thành kết luận về trách nhiệm cá nhân.

## git blame hoạt động như thế nào?

Git lưu lịch sử dưới dạng các commit liên kết với nhau. Mỗi commit chứa snapshot của cây thư mục và tham chiếu tới commit cha. Khi chạy `git blame`, Git bắt đầu từ revision được yêu cầu (mặc định là `HEAD`), rồi lần ngược lịch sử để xác định commit gần nhất đã làm thay đổi từng dòng của file.

Có thể hình dung:

~~~text
Commit A: tạo file và thêm các dòng ban đầu
        |
        v
Commit B: sửa dòng 12
        |
        v
Commit C: đổi tên biến ở dòng 20
        |
        v
Commit D: sửa định dạng toàn file
        |
        v
HEAD: phiên bản hiện tại
~~~

Khi blame một dòng trong `HEAD`, Git tìm commit gần nhất mà nó quy nguồn cho nội dung dòng đó. Nếu dòng đã được giữ nguyên qua nhiều commit, kết quả có thể trỏ về một commit cũ hơn commit gần nhất sửa file.

Git thực hiện việc đối chiếu dựa trên nội dung và cấu trúc lịch sử. Khi phát hiện dòng được di chuyển hoặc sao chép, các tùy chọn phù hợp có thể giúp Git lần theo nguồn gốc xa hơn. Đây là quá trình quy nguồn theo thuật toán, không phải hồ sơ kiểm toán về mọi người từng chạm vào dòng mã.

### Ví dụ đơn giản

Giả sử file có nội dung:

~~~java
public class PaymentService {
    public void validateAmount(long amount) {
        if (amount <= 0) {
            throw new IllegalArgumentException("Invalid amount");
        }
    }
}
~~~

Chạy:

~~~bash
git blame src/PaymentService.java
~~~

Kết quả minh họa:

~~~text
a12bc34d (An Nguyen     2025-02-10 09:30:00 +0700 1) public class PaymentService {
b23cd45e (Binh Tran     2025-02-12 14:20:00 +0700 2)     public void validateAmount(long amount) {
b23cd45e (Binh Tran     2025-02-12 14:20:00 +0700 3)         if (amount <= 0) {
b23cd45e (Binh Tran     2025-02-12 14:20:00 +0700 4)             throw new IllegalArgumentException("Invalid amount");
a12bc34d (An Nguyen     2025-02-10 09:30:00 +0700 5)         }
a12bc34d (An Nguyen     2025-02-10 09:30:00 +0700 6)     }
a12bc34d (An Nguyen     2025-02-10 09:30:00 +0700 7) }
~~~

Các mã commit và danh tính ở đây chỉ là dữ liệu giả để minh họa. Kết quả thật phụ thuộc lịch sử của repository.

Có thể đọc:

- Mã ở đầu dòng là commit mà Git quy nguồn cho dòng.
- Tên và thời gian là metadata tác giả của commit đó.
- Số dòng cho biết vị trí trong file đang được blame.
- Phần cuối là nội dung dòng.

Nếu nhiều dòng liền nhau được quy về cùng commit, Git thường trình bày thông tin commit theo cách rút gọn để dễ đọc. Đừng dựa vào khoảng trắng hoặc việc một trường được lặp lại để viết bộ phân tích tự động cho output mặc định.

## Cú pháp cơ bản

Dạng tổng quát:

~~~bash
git blame [options] [revision] -- <path>
~~~

Trong đó:

- `options` điều khiển phạm vi dòng, cách phát hiện di chuyển hoặc định dạng output.
- `revision` xác định phiên bản lịch sử cần tra cứu; nếu bỏ qua, Git dùng `HEAD`.
- `--` phân tách revision/options với đường dẫn file.
- `<path>` là đường dẫn tương đối từ repository root hoặc đường dẫn được Git phân giải trong working tree.

Ví dụ:

~~~bash
# Blame file ở HEAD
git blame -- src/PaymentService.java

# Blame file ở branch main
git blame main -- src/PaymentService.java

# Blame file ở một commit cụ thể
git blame a12bc34d -- src/PaymentService.java

# Blame file tại một tag phát hành
git blame v2.4.0 -- src/PaymentService.java
~~~

Khi chỉ định revision, Git tra cứu nội dung file tại revision đó. Nếu đường dẫn không tồn tại trong revision được chọn, lệnh sẽ báo lỗi hoặc không có nội dung để quy nguồn.

Dùng tên revision rõ ràng và kiểm tra commit trước khi đưa kết quả vào báo cáo:

~~~bash
git rev-parse main
git show --no-patch --oneline main
~~~

Điều này giúp tránh nhầm branch hoặc tag khi repository đang có nhiều dòng phát triển.

### Blame không đọc thay đổi chưa commit trong working tree

`git blame` tra cứu nội dung tại một revision, mặc định là `HEAD`. Nếu bạn đang sửa file nhưng chưa commit, các dòng mới sửa trong working tree không tự trở thành đầu vào của blame. Hãy commit thay đổi vào một nhánh thử nghiệm nếu cần truy nguồn phiên bản đó, hoặc chọn một revision đã tồn tại trong lịch sử. Dùng `git diff` để xem phần thay đổi chưa commit.

## Chỉ tra cứu một vùng dòng với -L

Trong file lớn, bạn thường chỉ cần điều tra một đoạn mã. Tùy chọn `-L` giới hạn phạm vi dòng.

### Chỉ định số dòng bắt đầu và kết thúc

~~~bash
git blame -L 20,45 -- src/PaymentService.java
~~~

Lệnh trên chỉ tra cứu dòng 20 đến dòng 45 của file ở revision mặc định `HEAD`.

Có thể dùng số dòng bắt đầu cùng số lượng dòng:

~~~bash
git blame -L 20,+10 -- src/PaymentService.java
~~~

Lệnh này bắt đầu từ dòng 20 và lấy 10 dòng.

Có thể lặp lại `-L` để tra cứu nhiều vùng:

~~~bash
git blame -L 20,35 -L 80,95 -- src/PaymentService.java
~~~

### Chỉ định vùng bằng biểu thức chính quy

`-L` cũng có thể nhận một biểu thức chính quy để tìm dòng bắt đầu:

~~~bash
git blame -L '/public void validateAmount/,+20' -- src/PaymentService.java
~~~

Lệnh này tìm dòng khớp biểu thức, rồi lấy thêm 20 dòng tính từ vị trí bắt đầu.

Có thể dùng hai biểu thức để xác định hai đầu vùng:

~~~bash
git blame -L '/public void validateAmount/','/^[[:space:]]*}/' -- src/PaymentService.java
~~~

Cú pháp biểu thức cần phù hợp với cách Git và shell xử lý dấu nháy. Nếu lệnh có nhiều dấu nháy hoặc ký tự đặc biệt, hãy thử trong terminal của shell đang dùng và kiểm tra phạm vi kết quả.

### Vì sao nên dùng -L?

Giới hạn vùng dòng giúp:

- Giảm output khi file rất dài.
- Tập trung vào một hàm hoặc khối logic.
- Dễ so sánh kết quả trước và sau refactor.
- Giảm thời gian tra cứu trong repository lớn.
- Tránh bị phân tán bởi các thay đổi không liên quan trong cùng file.

Tuy nhiên, chỉ nhìn một vùng nhỏ có thể bỏ qua khai báo, helper hoặc điều kiện ở ngoài vùng đó. Sau khi xác định commit, hãy mở thêm ngữ cảnh xung quanh bằng `git show` hoặc IDE.

## Đọc thông tin trong kết quả blame

Output mặc định hướng tới người đọc. Một dòng thường gồm mã commit rút gọn, thông tin tác giả, ngày, số dòng và nội dung.

Ví dụ:

~~~text
d34ef56a (Chi Le 2025-03-04 11:15:00 +0700 42) return account.isActive();
~~~

Có thể diễn giải:

- `d34ef56a`: mã commit được Git gắn với dòng.
- `Chi Le`: tên tác giả ghi trong metadata commit.
- `2025-03-04 11:15:00 +0700`: thời gian tác giả được ghi trong commit, kèm offset múi giờ.
- `42`: vị trí dòng trong file đang được blame.
- Phần sau dấu ngoặc: nội dung dòng.

Metadata author không nhất thiết là người trực tiếp gõ dòng đó. Một commit có thể được tạo bởi người khác với author được giữ lại, chẳng hạn khi cherry-pick hoặc áp dụng patch.

### Hiển thị email tác giả

Dùng `-e` để hiển thị email thay cho tên:

~~~bash
git blame -e -L 42,55 -- src/PaymentService.java
~~~

Email cũng là metadata commit. Nó không phải bằng chứng xác thực danh tính ngoài hệ thống Git. Email có thể là địa chỉ cá nhân, địa chỉ công ty, địa chỉ ẩn danh do nền tảng cung cấp hoặc chuỗi được cấu hình tùy ý.

Không đưa email hoặc thông tin cá nhân vào báo cáo công khai nếu không cần thiết.

### Định dạng ngày

Có thể chọn cách trình bày ngày:

~~~bash
git blame --date=short -- src/PaymentService.java
git blame --date=iso -- src/PaymentService.java
~~~

Ngày hiển thị vẫn lấy từ metadata commit. Nó không chứng minh thời điểm thay đổi được triển khai lên production hoặc thời điểm người dùng bắt đầu gặp lỗi.

### Output phục vụ máy đọc

Không nên viết script dựa trên cách căn cột của output mặc định. Dùng porcelain format:

~~~bash
git blame --line-porcelain -- src/PaymentService.java
~~~

`--line-porcelain` xuất metadata có cấu trúc cho từng dòng, phù hợp hơn khi cần xử lý bằng script. Nó có thể lặp lại nhiều trường metadata nên output dài hơn đáng kể.

Một lựa chọn khác là:

~~~bash
git blame --porcelain -- src/PaymentService.java
~~~

Porcelain format cũng cung cấp các trường có cấu trúc nhưng có thể tối ưu bằng cách không lặp lại một số metadata khi các dòng liền nhau cùng commit. Nếu cần parse độc lập từng dòng, `--line-porcelain` dễ xử lý hơn.

Khi viết automation:

- Đọc tài liệu format của phiên bản Git đang dùng.
- Xử lý mã commit đầy đủ, không giả định hash có độ dài cố định.
- Xử lý tên tác giả và nội dung có ký tự Unicode.
- Không giả định mọi commit đều có email hoặc trường metadata giống nhau.
- Phân biệt dữ liệu metadata với nội dung source code.
- Kiểm tra mã thoát và trường hợp file không tồn tại ở revision yêu cầu.

## Khi dòng bị đổi định dạng: dùng -w

Một thay đổi chỉ về khoảng trắng hoặc định dạng có thể khiến blame gán nhiều dòng cho commit formatter, dù logic không đổi.

Ví dụ:

~~~text
Commit A:
if (amount <= 0) {
    reject();
}

Commit B:
if (amount <= 0)
{
    reject();
}
~~~

Nếu blame thông thường xem cách bố trí dòng là khác biệt, kết quả có thể trỏ tới commit B. Tùy chọn `-w` yêu cầu Git bỏ qua thay đổi whitespace khi tìm nguồn gốc dòng:

~~~bash
git blame -w -- src/PaymentService.java
~~~

Có thể kết hợp với phạm vi dòng:

~~~bash
git blame -w -L 20,45 -- src/PaymentService.java
~~~

`-w` hữu ích khi dự án có commit format code, đổi indentation hoặc chuẩn hóa khoảng trắng.

Nhưng không phải mọi whitespace đều vô nghĩa. Trong một số ngôn ngữ và định dạng, khoảng trắng có thể ảnh hưởng cách phân tích hoặc kết quả, chẳng hạn Python, Makefile, YAML hay chuỗi literal. `-w` chỉ thay đổi cách quy nguồn trong blame; nó không chứng minh thay đổi whitespace không ảnh hưởng hành vi chương trình.

Hãy so sánh blame thông thường và blame với `-w`, sau đó đọc diff của commit formatter để xác nhận đó thực sự là thay đổi định dạng.

## Khi dòng được di chuyển hoặc sao chép: dùng -M và -C

Refactor có thể di chuyển một khối mã sang vị trí khác hoặc sang file khác. Nếu chỉ nhìn blame mặc định, Git có thể gán dòng cho commit thực hiện thao tác di chuyển/sao chép.

Các tùy chọn `-M` và `-C` giúp Git tìm nội dung tương tự ở nơi khác trong lịch sử.

### -M: tìm dòng di chuyển trong cùng file

Dùng:

~~~bash
git blame -M -- src/PaymentService.java
~~~

`-M` yêu cầu Git phát hiện các dòng được di chuyển hoặc sao chép trong cùng file. Điều này hữu ích khi một hàm được sắp xếp lại hoặc một khối mã chuyển sang vị trí khác trong cùng file.

Git dùng ngưỡng tương đồng để quyết định nội dung có đủ giống nhau hay không. Có thể truyền ngưỡng cho `-M` trong trường hợp cần điều chỉnh; ngưỡng thấp hơn có thể tìm được nhiều trường hợp hơn nhưng cũng dễ ghép nhầm các đoạn ngắn phổ biến.

### -C: tìm dòng được chuyển từ file khác

Dùng:

~~~bash
git blame -C -- src/PaymentService.java
~~~

`-C` mở rộng tìm kiếm sang file khác được sửa trong cùng commit. Điều này hữu ích khi refactor tách một lớp hoặc hàm sang file mới.

Có thể tăng phạm vi tìm kiếm bằng cách lặp lại `-C`:

~~~bash
git blame -M -C -- src/PaymentService.java
git blame -M -C -C -- src/PaymentService.java
git blame -M -C -C -C -- src/PaymentService.java
~~~

Khái quát:

- Một `-C`: tìm nội dung được chuyển/sao chép từ file khác có thay đổi trong cùng commit.
- Hai `-C`: mở rộng thêm sang các file trong commit đã tạo file đang được blame.
- Ba `-C`: mở rộng tìm kiếm sang các file khác trong lịch sử.

Các mức tìm kiếm rộng có thể tốn thời gian hơn, nhất là repository lớn. Git vẫn dùng heuristic và ngưỡng tương đồng; kết quả có thể không tìm được nguồn nếu nội dung đã thay đổi quá nhiều hoặc đoạn mã quá ngắn.

### Kết hợp -w, -M và -C

Khi một file vừa được format vừa được tách hàm, có thể thử:

~~~bash
git blame -w -M -C -- src/PaymentValidator.java
~~~

Nếu cần điều tra kỹ hơn, chạy từng biến thể và so sánh kết quả:

~~~bash
git blame -- src/PaymentValidator.java
git blame -w -- src/PaymentValidator.java
git blame -M -C -- src/PaymentValidator.java
~~~

Không mặc định kết quả có nhiều tùy chọn hơn là đúng hơn. Hãy kiểm tra commit mà Git chỉ ra và xác nhận đoạn mã có thực sự được di chuyển hay sao chép từ nguồn đó.

## Bỏ qua commit định dạng hàng loạt bằng ignore-revs

Một commit chỉ thay đổi formatter, line ending hoặc quy ước định dạng có thể làm blame trở nên khó đọc. Git hỗ trợ bỏ qua một số revision khi quy nguồn.

### Bỏ qua một commit cụ thể

~~~bash
git blame --ignore-rev a12bc34d -- src/PaymentService.java
~~~

Git cố gắng bỏ qua thay đổi được tạo bởi revision chỉ định để tiếp tục quy nguồn về commit có ý nghĩa trước đó.

Đây không phải là xóa commit khỏi lịch sử. Commit vẫn tồn tại, vẫn xuất hiện trong `git log` và vẫn ảnh hưởng snapshot của repository. Tùy chọn chỉ thay đổi cách blame diễn giải revision đó.

Chỉ nên bỏ qua commit khi đã xác nhận phạm vi của nó, ví dụ một commit format toàn bộ code không làm thay đổi logic. Không bỏ qua commit có thay đổi nghiệp vụ chỉ vì nó làm output khó đọc.

### Quản lý danh sách revision cần bỏ qua

Với dự án có một số commit format lớn, có thể lưu danh sách hash trong file được version control, ví dụ `.git-blame-ignore-revs`:

~~~text
a12bc34d
b23cd45e
~~~

Sau đó chạy:

~~~bash
git blame --ignore-revs-file .git-blame-ignore-revs -- src/PaymentService.java
~~~

Có thể cấu hình local để Git tự sử dụng file này:

~~~bash
git config blame.ignoreRevsFile .git-blame-ignore-revs
~~~

Nếu cấu hình trong repository, nhóm có thể thống nhất cách tra cứu blame. Hãy ghi rõ mục đích file và chỉ thêm commit đã được review.

### Khi dùng ignore-revs cần lưu ý

- File ignore-revs không sửa lịch sử commit.
- Mỗi người có thể có cấu hình khác nhau, nên kết quả blame có thể khác nếu không dùng cùng danh sách.
- Một commit bị bỏ qua vẫn có thể chứa thay đổi logic ngoài ý muốn; phải review trước khi thêm.
- Khi báo cáo kết quả, hãy nêu rõ có dùng ignore-revs hay không.

## Chọn cách đi qua merge commit với --first-parent

Một merge commit có nhiều parent. Khi truy tìm lịch sử, Git có thể lần qua các nhánh khác nhau để tìm commit nguồn của dòng.

Nếu muốn chỉ đi theo parent thứ nhất khi gặp merge commit, dùng:

~~~bash
git blame --first-parent main -- src/PaymentService.java
~~~

Parent thứ nhất thường là nhánh được checkout tại thời điểm merge, nhưng điều đó phụ thuộc cách merge được thực hiện. Nó không phải lúc nào cũng đồng nghĩa với nhánh `main`.

`--first-parent` hữu ích khi bạn muốn xem lịch sử theo tuyến tích hợp chính của dự án. Kết quả có thể khác blame mặc định vì các commit nằm ở parent thứ hai không được đi qua theo cùng cách.

So sánh:

~~~bash
git blame main -- src/PaymentService.java
git blame --first-parent main -- src/PaymentService.java
~~~

Nếu hai kết quả khác nhau, kiểm tra merge commit và các parent của nó:

~~~bash
git log --graph --oneline --decorate --all
git show --no-patch --pretty=raw <merge-commit>
~~~

Không dùng `--first-parent` như một bộ lọc “ai chịu trách nhiệm”. Nó chỉ giới hạn đường đi trong đồ thị commit.

## Dùng reverse blame để xem dòng tồn tại tới revision nào

Blame mặc định đi ngược từ revision hiện tại về quá khứ để tìm commit đã đưa dòng vào phiên bản đang xem.

`--reverse` đi theo chiều ngược lại trong một khoảng revision, giúp tìm revision cuối cùng mà dòng đã tồn tại:

~~~bash
git blame --reverse v1.0.0..main -- src/PaymentService.java
~~~

Cách dùng này cần một khoảng revision dạng `START..END`. Đường dẫn phải tồn tại ở đầu khoảng để Git có thể theo dõi dòng từ mốc bắt đầu.

Reverse blame hữu ích khi điều tra:

- Một dòng từng tồn tại trong bản phát hành cũ nhưng đã biến mất.
- Dòng bị xóa hoặc thay đổi ở giai đoạn nào.
- Nội dung cũ còn tồn tại tới commit nào trong một nhánh phát triển.

Reverse blame không phải công cụ tìm mọi commit từng sửa dòng. Nó trả lời một câu hỏi khác với blame thông thường. Để xem toàn bộ các lần thay đổi, hãy dùng `git log -p` hoặc các lệnh tìm kiếm lịch sử.

## Từ blame đi tới commit và diff

Blame chỉ ra một commit đáng để điều tra tiếp. Sau đó hãy mở commit và xem thay đổi thực tế.

### Xem commit đầy đủ

~~~bash
git show --format=fuller <commit-id>
~~~

Kết quả cho biết:

- Author và committer.
- Ngày tác giả và ngày commit.
- Commit message.
- Parent commit.
- Diff của commit.

Chỉ xem thay đổi của một file:

~~~bash
git show <commit-id> -- src/PaymentService.java
~~~

Xem metadata mà không hiển thị patch:

~~~bash
git show --no-patch --format=fuller <commit-id>
~~~

Đối chiếu phiên bản file trước commit:

~~~bash
git show <commit-id>^:src/PaymentService.java
~~~

Với commit thường có một parent, cú pháp `^` trỏ tới parent thứ nhất. Nếu commit là merge, cần xác định parent muốn so sánh; có thể dùng `^1` hoặc `^2`.

### Xem lịch sử file

~~~bash
git log --oneline -- src/PaymentService.java
~~~

Xem patch của các commit thay đổi file:

~~~bash
git log -p -- src/PaymentService.java
~~~

Theo dõi file qua các lần rename khi xem log:

~~~bash
git log --follow --oneline -- src/PaymentService.java
~~~

`--follow` hữu ích với một đường dẫn file và lịch sử rename tuyến tính; nó có giới hạn với lịch sử phức tạp hoặc các thao tác copy. Dùng kết hợp `git blame -M -C` khi cần điều tra nội dung được di chuyển hoặc sao chép.

### Tìm commit đã thêm hoặc xóa một chuỗi

Nếu dòng hiện tại không còn trong file, blame trên phiên bản hiện tại không thể chỉ ra commit của dòng đã bị xóa. Hãy tìm trong lịch sử:

~~~bash
git log -S'validateAmount' --oneline -- src/
~~~

`-S` tìm commit làm thay đổi số lần xuất hiện của chuỗi chỉ định trong diff.

Nếu cần tìm theo biểu thức chính quy xuất hiện trong các dòng diff:

~~~bash
git log -G'validateAmount|checkAmount' --oneline -- src/
~~~

`-G` tìm các patch có dòng thêm hoặc xóa khớp biểu thức. Hai tùy chọn `-S` và `-G` có ý nghĩa khác nhau; chọn theo câu hỏi cần trả lời.

## Quy trình điều tra một dòng mã trong thực tế

Giả sử một lỗi được phát hiện ở dòng kiểm tra số tiền trong `PaymentService.java`. Bạn muốn hiểu thay đổi đó xuất hiện từ đâu.

### Bước 1: Xác định repository và phiên bản

~~~bash
git rev-parse --show-toplevel
git status --short --branch
git rev-parse HEAD
~~~

Xác nhận đang xem đúng repository, branch và working tree. Nếu cần điều tra phiên bản đã phát hành, chọn tag hoặc commit tương ứng thay vì mặc định dùng HEAD.

### Bước 2: Blame đúng vùng dòng

~~~bash
git blame -L 35,55 HEAD -- src/PaymentService.java
~~~

Ghi lại commit ID được gắn với dòng cần xem. Không kết luận trách nhiệm chỉ từ tên author trong output.

### Bước 3: Kiểm tra các trường hợp format hoặc di chuyển

~~~bash
git blame -w -L 35,55 HEAD -- src/PaymentService.java
git blame -M -C -L 35,55 HEAD -- src/PaymentService.java
~~~

Nếu kết quả thay đổi, so sánh commit và kiểm tra nội dung để hiểu Git đã nhận diện whitespace hoặc đoạn mã di chuyển như thế nào.

### Bước 4: Mở commit được quy nguồn

~~~bash
git show --format=fuller --find-renames <commit-id> -- src/PaymentService.java
~~~

Đọc patch, author, committer, message và parent. Kiểm tra xem commit có thực sự thay đổi logic đang điều tra hay chỉ format hoặc di chuyển code.

### Bước 5: Xem bối cảnh trước và sau

~~~bash
git log --oneline --decorate -- src/PaymentService.java
git log -p --follow -- src/PaymentService.java
~~~

Nếu commit là một phần của merge hoặc thay đổi được chuyển từ file khác, xem graph và các parent để hiểu đầy đủ đường đi.

### Bước 6: Tìm lý do thay đổi

Git commit message có thể cung cấp manh mối, nhưng quyết định kỹ thuật thường nằm trong:

- Pull Request hoặc Merge Request.
- Review comments và approval.
- Issue hoặc ticket liên quan.
- Tài liệu thiết kế.
- Trao đổi kỹ thuật của nhóm.
- Test được thêm hoặc sửa cùng commit.

`git blame` không lưu nội dung review hoặc lý do nghiệp vụ. Cần mở hệ thống quản lý công việc tương ứng để tìm bối cảnh đó.

### Bước 7: Ghi nhận phát hiện có giới hạn

Một cách ghi nhận chính xác:

> Git blame của `src/PaymentService.java` tại commit `<revision>` quy dòng 42 về commit `<commit-id>`. Commit ghi author là `<author>` và có thông điệp `<message>`. Diff cho thấy commit thay đổi điều kiện kiểm tra số tiền. Cần xem thêm review/ticket để xác nhận lý do và quyết định thiết kế.

Cách diễn đạt này tách dữ liệu Git quan sát được khỏi kết luận về con người hoặc nguyên nhân.

## Những giới hạn quan trọng của git blame

### Blame không xác định người chịu trách nhiệm

Author trong commit là trường metadata. Nó không chứng minh người đó là người trực tiếp gõ code, chủ sở hữu module, người phê duyệt hay người phải chịu trách nhiệm về lỗi.

Một commit có thể được tạo qua pair programming, cherry-pick, bot, patch từ bên ngoài hoặc quy trình tự động. Thông tin author có thể được giữ lại trong khi committer là người khác.

### Blame chỉ phản ánh nội dung trong lịch sử Git

Git không biết:

- Ai đã trao đổi về yêu cầu.
- Ai review và phê duyệt.
- Ai quyết định kiến trúc.
- Ai kiểm thử trên môi trường thực tế.
- Vì sao thay đổi được triển khai.
- Ai chịu trách nhiệm vận hành sau release.

Những dữ liệu này có thể nằm trong PR/MR, issue tracker, CI, hệ thống triển khai hoặc tài liệu nội bộ.

### Di chuyển và sao chép có thể làm attribution thay đổi

Nếu không bật `-M` hoặc `-C`, blame có thể gán dòng cho commit di chuyển hoặc sao chép. Khi bật các tùy chọn này, Git dùng heuristic để tìm nguồn nội dung tương tự. Đoạn code ngắn, phổ biến hoặc nhiều lần được sửa có thể khiến kết quả không rõ ràng.

Luôn kiểm tra diff của commit nguồn và đường dẫn cũ.

### Commit format có thể làm nhiễu lịch sử

Formatter, chuẩn hóa line ending hoặc thay đổi indentation có thể khiến nhiều dòng được gán cho một commit lớn. Dùng `-w` hoặc ignore-revs khi phù hợp, nhưng phải xác nhận commit thực sự không đổi logic.

### Merge strategy ảnh hưởng đường đi lịch sử

Merge commit có nhiều parent. Blame mặc định và `--first-parent` có thể dẫn tới kết quả khác nhau. Cần biết câu hỏi đang muốn theo dõi lịch sử đầy đủ hay tuyến tích hợp chính.

### Dòng đã bị xóa không có trong file hiện tại

Blame trên HEAD chỉ tra cứu các dòng trong phiên bản file được chọn. Nếu dòng đã bị xóa, hãy chọn revision cũ nơi dòng còn tồn tại hoặc dùng `git log -S`, `git log -G` và `git log -p`.

### Shallow clone hoặc thiếu lịch sử làm kết quả không đầy đủ

Nếu clone chỉ chứa một phần lịch sử, Git không thể truy cập các commit cũ chưa được tải. Kiểm tra:

~~~bash
git rev-parse --is-shallow-repository
~~~

Nếu repository là shallow clone và bạn có quyền lấy thêm lịch sử, có thể fetch sâu hơn hoặc unshallow theo chính sách dự án:

~~~bash
git fetch --unshallow origin
~~~

Sau đó chạy lại blame. Không nên kết luận commit được hiển thị là nguồn gốc đầu tiên nếu lịch sử trước đó chưa có trong clone.

### File sinh tự động hoặc mã vendor có thể không phản ánh nguồn phát triển

Một file generated, bundle, vendored dependency hoặc mã được sao chép từ thư viện ngoài có thể được commit bởi người chạy generator hoặc người nhập dependency. Blame cho biết commit đưa nội dung vào repository; nó không tự xác định tác giả gốc của mã bên ngoài.

Hãy kiểm tra script generator, manifest dependency, nguồn upstream và quy trình vendor.

## Các lệnh thường dùng

| Lệnh | Mục đích |
|---|---|
| `git blame -- file` | Tra cứu nguồn gốc dòng ở HEAD |
| `git blame main -- file` | Tra cứu ở branch main |
| `git blame <rev> -- file` | Tra cứu ở commit/tag cụ thể |
| `git blame -L 20,45 -- file` | Giới hạn vùng dòng |
| `git blame -L '/pattern/,+20' -- file` | Chọn vùng bắt đầu từ biểu thức |
| `git blame -w -- file` | Bỏ qua khác biệt whitespace khi quy nguồn |
| `git blame -M -- file` | Phát hiện dòng di chuyển trong cùng file |
| `git blame -C -- file` | Tìm dòng chuyển từ file khác |
| `git blame --ignore-rev <rev> -- file` | Bỏ qua một revision khi blame |
| `git blame --ignore-revs-file <path> -- file` | Bỏ qua danh sách revision |
| `git blame --first-parent main -- file` | Chỉ theo parent thứ nhất tại merge |
| `git blame --reverse A..B -- file` | Tìm revision cuối trong khoảng mà dòng tồn tại |
| `git blame --line-porcelain -- file` | Output có cấu trúc theo từng dòng |
| `git show <rev> -- file` | Xem patch của commit cho file |
| `git log -p -- file` | Xem lịch sử patch của file |
| `git log --follow -- file` | Theo dõi lịch sử file qua rename |
| `git log -S'text' -- file` | Tìm thay đổi số lần xuất hiện chuỗi |
| `git log -G'regex' -- file` | Tìm patch có dòng khớp regex |

## Những hiểu lầm thường gặp

| Hiểu lầm | Cách hiểu đúng |
|---|---|
| Blame cho biết ai chịu trách nhiệm về dòng code | Blame quy nguồn dòng về commit và metadata author |
| Author là người trực tiếp gõ code | Author là trường metadata có thể được giữ lại hoặc cấu hình |
| Commit được blame là commit đầu tiên tạo dòng | Đó thường là commit gần nhất Git quy nguồn cho nội dung dòng hiện tại |
| Blame luôn tìm đúng nguồn sau refactor | Cần heuristic `-M`/`-C` và kiểm tra diff |
| `-w` chứng minh whitespace không có ý nghĩa | Nó chỉ bỏ qua whitespace trong quá trình quy nguồn |
| Ignore-revs xóa commit khỏi lịch sử | Nó chỉ thay đổi cách blame diễn giải commit |
| Blame hiện tại tìm được dòng đã bị xóa | Cần chọn revision cũ hoặc tìm bằng log/pickaxe |
| `--first-parent` cho biết tác giả chính của dự án | Nó chỉ giới hạn đường đi qua merge commit |
| Email trong blame xác thực danh tính | Email là metadata commit, không phải bằng chứng xác thực |
| Dòng blame là toàn bộ lịch sử thay đổi | Cần xem log, diff, merge, PR/MR và ticket để hiểu bối cảnh |

## Checklist khi tra cứu bằng git blame

- [ ] Đã xác nhận đúng repository, branch và revision.
- [ ] Đã xác định đúng file và vùng dòng cần điều tra.
- [ ] Đã ghi lại commit ID được blame quy nguồn.
- [ ] Đã phân biệt author với committer.
- [ ] Đã kiểm tra commit bằng `git show`.
- [ ] Đã xem lịch sử file bằng `git log`.
- [ ] Đã thử `-w`, `-M` hoặc `-C` khi có dấu hiệu format/move/copy.
- [ ] Đã xem xét ignore-revs nếu có commit format hàng loạt được thống nhất.
- [ ] Đã hiểu ảnh hưởng của merge và `--first-parent`.
- [ ] Đã kiểm tra repository có shallow hay thiếu lịch sử không.
- [ ] Đã tìm PR/MR, review hoặc ticket khi cần biết lý do thay đổi.
- [ ] Đã diễn đạt kết quả như thông tin quy nguồn của Git, không kết luận thay cho quy trình xác minh trách nhiệm.

## Ghi nhớ

`git blame` cho biết Git quy nguồn từng dòng trong một phiên bản file về commit nào và hiển thị metadata author của commit đó. Dùng `-L` để tập trung vào vùng dòng, `-w` để xử lý thay đổi whitespace, `-M` và `-C` để tìm dòng di chuyển hoặc sao chép, ignore-revs để bỏ qua commit format đã được xác nhận, và `--first-parent` hoặc `--reverse` khi câu hỏi cần một đường đi lịch sử cụ thể. Sau khi tìm được commit, hãy mở `git show`, xem `git log` và tìm PR/MR hoặc ticket liên quan. Blame là công cụ điều tra nguồn gốc nội dung trong lịch sử Git; nó không phải bằng chứng độc lập về người chịu trách nhiệm, lý do thiết kế hay toàn bộ quá trình phát triển.

