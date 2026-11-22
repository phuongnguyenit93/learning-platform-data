# So sánh theo từ và điều chỉnh số dòng ngữ cảnh

Khi xem thay đổi bằng `git diff`, Git thường trình bày khác biệt theo từng dòng. Cách này rất phù hợp khi thêm, xóa hoặc di chuyển cả dòng, nhưng có thể khó đọc khi một dòng dài chỉ thay đổi một vài từ, một biểu thức hoặc một tham số. Ví dụ, sửa điều kiện từ `status == "NEW"` thành `status != "CANCELLED"` có thể khiến cả dòng được đánh dấu thay đổi dù phần lớn nội dung vẫn giống nhau.

Git cung cấp **word diff** để làm nổi bật phần thay đổi ở mức từ và cho phép điều chỉnh số dòng không thay đổi xung quanh mỗi vùng diff. Hai khả năng này giúp review chính xác hơn: word diff cho biết phần nào trong dòng thực sự khác, còn context lines cung cấp đủ mã hoặc nội dung lân cận để hiểu thay đổi được đặt trong ngữ cảnh nào.

Trong quy trình quản lý mã nguồn, hãy chọn cách hiển thị phù hợp với loại nội dung và mục đích review. Word diff hỗ trợ đọc thay đổi nhỏ trong dòng; context lines giúp kiểm tra luồng xử lý, điều kiện và cấu trúc xung quanh. Cả hai chỉ thay đổi cách Git trình bày diff, không sửa working tree, staging area hay commit.

## 1. Khi nào cần word diff?

Diff theo dòng đánh dấu một dòng cũ và một dòng mới khi nội dung dòng thay đổi. Với dòng ngắn, điều này thường đủ rõ. Với dòng dài, JSON, tài liệu, câu truy vấn hoặc danh sách tham số, phần khác biệt có thể bị chìm giữa nhiều ký tự giống nhau.

Ví dụ trước và sau:

```java
String message = "Payment is pending for order " + orderId;
```

Sau khi chỉnh:

```java
String message = "Payment is completed for order " + orderId;
```

Diff theo dòng sẽ đánh dấu toàn bộ dòng cũ và dòng mới. Word diff có thể chỉ ra hai cụm `pending` và `completed` khác nhau, giúp reviewer tập trung vào thay đổi nghiệp vụ.

Word diff hữu ích khi:

- Một dòng dài chỉ thay đổi một từ hoặc một biểu thức.
- Sửa nội dung tài liệu, thông điệp, câu truy vấn SQL hoặc cấu hình.
- Thêm/bớt tham số trong lời gọi hàm.
- Đổi tên biến hoặc thay một hằng số trong dòng hiện có.
- Review thay đổi định dạng có nhiều nội dung giữ nguyên trên cùng dòng.

Word diff ít hữu ích hơn khi:

- Thay đổi chủ yếu là di chuyển hoặc tái cấu trúc nhiều dòng.
- Nội dung phụ thuộc mạnh vào thụt lề hoặc cấu trúc khối.
- File là nhị phân, file sinh tự động hoặc có định dạng đặc thù.
- Cần kiểm tra thứ tự dòng, vị trí khai báo hay phạm vi khối lệnh.

Với code, hãy xem word diff cùng diff theo dòng và ngữ cảnh xung quanh. Một thay đổi vài ký tự có thể làm đổi điều kiện, quyền truy cập hoặc hành vi của cả hàm.

## 2. Cú pháp word diff cơ bản

Thêm `--word-diff` vào lệnh diff:

```bash
git diff --word-diff
```

Git đánh dấu phần từ bị xóa và thêm ngay trong dòng. Mặc định, từ được phân tách theo khoảng trắng và chế độ hiển thị là `plain`.

Có thể dùng với các dạng diff khác:

```bash
# Thay đổi trong working tree so với index
git diff --word-diff

# Thay đổi đã stage so với HEAD
git diff --cached --word-diff

# So sánh hai commit
git diff --word-diff HEAD~1 HEAD

# Xem thay đổi của một commit
git show --word-diff HEAD
```

`git diff` mặc định không hiển thị file untracked. Nếu vừa tạo file mới, cần stage file hoặc dùng công cụ khác để xem nội dung trước khi stage; word diff chỉ hoạt động trên các nội dung mà phép so sánh Git đang xét.

## 3. Các chế độ hiển thị của --word-diff

Git hỗ trợ bốn mode:

| Mode | Cách hiển thị | Khi nên dùng |
| --- | --- | --- |
| `color` | Tô màu phần thêm và xóa trong terminal | Review trực tiếp, dễ nhận biết thay đổi nhỏ |
| `plain` | Bao phần xóa bằng `[- -]`, phần thêm bằng `{+ +}` | Terminal không hỗ trợ màu hoặc cần đọc output dạng chữ |
| `porcelain` | Xuất theo dòng, ký hiệu phần thêm/xóa và dòng mới | Xử lý output bằng script hoặc công cụ khác |
| `none` | Tắt word diff, trở về cách hiển thị thông thường | Muốn ghi đè thiết lập word diff từ cấu hình |

### Mode color

```bash
git diff --word-diff=color
```

Phần bị xóa và phần được thêm sẽ dùng màu theo cấu hình diff của Git. Màu cụ thể có thể khác nhau theo theme, terminal và cấu hình `color.diff`.

`color` thường dễ đọc nhất khi review trực tiếp. Nếu terminal không hiển thị màu, hãy dùng `plain` hoặc kiểm tra cấu hình màu và pager.

### Mode plain

```bash
git diff --word-diff=plain
```

Ví dụ minh họa:

```text
const status = [-"PENDING";-]{+"PAID";+}
```

`[- ... -]` biểu thị nội dung bị xóa; `{+ ... +}` biểu thị nội dung được thêm. Các dấu này là ký hiệu trình bày của Git, không phải ký tự được chèn vào file nguồn.

Mode plain thuận tiện khi copy output vào nơi không giữ màu. Tuy nhiên, nếu file thật chứa chuỗi giống các dấu đánh dấu, người đọc cần dựa vào cấu trúc diff để phân biệt.

### Mode porcelain

```bash
git diff --word-diff=porcelain
```

Porcelain tạo output theo dòng với tiền tố biểu thị phần không đổi, phần thêm và phần xóa. Dòng `~` được dùng để biểu diễn ranh giới dòng mới. Mode này hướng tới việc phân tích bằng chương trình, không phải định dạng trình bày thân thiện nhất cho review thủ công.

Nếu cần dùng output trong script, nên đọc tài liệu phiên bản Git đang cài và tránh giả định mỗi token luôn nằm trên đúng một dòng hiển thị.

### Mode none

```bash
git diff --word-diff=none
```

Mode `none` hữu ích khi cấu hình cá nhân đã bật word diff nhưng một lệnh cụ thể cần diff theo dòng thông thường.

## 4. Dùng --color-words

Lệnh sau là cách viết ngắn:

```bash
git diff --color-words
```

`--color-words` tương đương `--word-diff=color`. Có thể truyền regex để xác định thế nào là một từ:

```bash
git diff --color-words='[[:alnum:]_]+'
```

Ví dụ này coi chuỗi gồm chữ, số và dấu gạch dưới là một từ. Lưu ý: mọi ký tự nằm giữa các lần khớp regex sẽ được xem như khoảng trắng và bị bỏ qua khi tìm khác biệt. Vì vậy, regex chỉ khớp chữ/số có thể làm thay đổi dấu câu mà không được thể hiện. Phần regex sẽ được giải thích kỹ hơn ở mục tiếp theo.

Có thể dùng `--word-diff=color --word-diff-regex=...` khi muốn ghi rõ cả mode lẫn quy tắc token:

```bash
git diff --word-diff=color \
  --word-diff-regex='[[:alnum:]_]+|[^[:space:][:alnum:]_]'
```

Hai cách trên đều có thể tô màu phần thay đổi ở mức từ; cú pháp thứ hai giúp nhìn rõ từng tùy chọn và dễ kết hợp với các lệnh khác.

## 5. Tùy chỉnh cách Git nhận diện một từ

Mặc định, Git xem chuỗi ký tự không có khoảng trắng là một từ. Với code, điều đó có nghĩa `paymentTotal;` có thể là một token, bao gồm cả dấu chấm phẩy. Khi sửa thành `paymentAmount;`, cả token được xem là thay đổi.

Tùy chọn `--word-diff-regex=<regex>` cho phép xác định token theo quy tắc riêng:

```bash
git diff --word-diff=color \
  --word-diff-regex='[[:alnum:]_]+|[^[:space:][:alnum:]_]'
```

Trong ví dụ:

- `[[:alnum:]_]+` khớp một chuỗi chữ/số hoặc dấu gạch dưới, thường tương ứng identifier.
- `[^[:space:][:alnum:]_]` khớp một ký tự không phải khoảng trắng, chữ/số hoặc dấu gạch dưới; nhờ vậy dấu câu được giữ thành token riêng.
- Ký tự khoảng trắng nằm giữa các token không được xem là nội dung từ.

Với regex này, đổi `calculateTotal()` thành `calculateAmount()` cho thấy identifier thay đổi; dấu ngoặc và dấu câu vẫn được xét riêng.

### Chú ý quan trọng về regex

Git xem mỗi lần khớp không chồng lấn của regex là một từ. Phần văn bản nằm giữa các lần khớp được coi như khoảng trắng và bị bỏ qua khi tìm khác biệt. Nếu regex không khớp dấu chấm, dấu phẩy, dấu ngoặc hoặc toán tử, các thay đổi ở những ký tự đó có thể bị ẩn.

Ví dụ, regex:

```bash
--word-diff-regex='[[:alnum:]_]+'
```

có thể hữu ích khi chỉ quan tâm tới từ trong văn bản, nhưng không phù hợp để review code nếu dấu câu có ý nghĩa. Một thay đổi `a == b` thành `a != b` cần hiển thị toán tử; hãy dùng regex giữ dấu câu hoặc diff theo dòng thông thường.

Regex nên khớp các token nằm trên một dòng. Git không xử lý một match kéo dài qua newline như một từ nhiều dòng; match có newline sẽ bị cắt tại ranh giới dòng. Dùng regex dễ hiểu, kiểm tra trên một diff nhỏ và đối chiếu kết quả với nội dung thực.

## 6. Một số regex theo loại nội dung

Các mẫu dưới đây là gợi ý. Hãy kiểm tra với ngôn ngữ, locale và phiên bản Git đang dùng.

| Mục đích | Regex gợi ý | Đặc điểm |
| --- | --- | --- |
| Từ theo khoảng trắng | Không truyền regex | Giữ cách chia từ mặc định của Git |
| Identifier và dấu câu | `[[:alnum:]_]+|[^[:space:][:alnum:]_]` | Giữ identifier và ký hiệu riêng |
| Chỉ từ trong văn bản | `[[:alnum:]_]+` | Dấu câu và khoảng trắng không khớp sẽ bị bỏ qua |
| Token gồm chữ, số, dấu chấm và gạch nối | `[[:alnum:]_.-]+|[^[:space:][:alnum:]_.-]` | Hợp với một số tên cấu hình hoặc phiên bản |

### So sánh văn bản

Khi review nội dung tài liệu, có thể chỉ quan tâm từ ngữ:

```bash
git diff --word-diff=color \
  --word-diff-regex='[[:alnum:]_]+'
```

Ví dụ đổi câu:

```text
The service accepts pending payments.
The service accepts completed payments.
```

Word diff làm nổi bật `pending` và `completed`. Nhưng nếu thay dấu chấm thành dấu hỏi, regex trên có thể không hiển thị khác biệt dấu câu. Vì vậy, với nội dung cần kiểm tra chính tả, dấu câu hoặc định dạng, hãy dùng diff theo dòng bổ sung.

### So sánh code

Với source code, giữ identifier và dấu câu:

```bash
git diff --word-diff=color \
  --word-diff-regex='[[:alnum:]_]+|[^[:space:][:alnum:]_]'
```

Ví dụ:

```java
if (amount > limit) {
```

được sửa thành:

```java
if (amount >= limit) {
```

Regex trên giữ `>` và `=` thành token riêng, nhờ đó phép so sánh được nhìn thấy. Đây là lý do nên tránh regex chỉ nhận chữ và số khi review code.

### So sánh cấu hình hoặc JSON

JSON có nhiều dấu ngoặc, dấu hai chấm, dấu phẩy và dấu nháy. Nếu regex bỏ dấu câu, thay đổi cấu trúc có thể bị che khuất. Dùng regex giữ dấu câu:

```bash
git diff --word-diff=color \
  --word-diff-regex='[[:alnum:]_]+|[^[:space:][:alnum:]_]'
```

Với file cấu hình có dấu gạch nối hoặc dấu chấm trong key, cân nhắc đưa chúng vào nhóm identifier nếu muốn giữ cả key như một token. Khi cấu trúc JSON hoặc YAML thay đổi đáng kể, formatter-aware diff hoặc diff theo dòng có thể dễ review hơn.

## 7. Kết hợp word diff với context lines

Word diff chỉ làm rõ phần thay đổi trong dòng. Nó không tự cho biết dòng đó nằm trong hàm nào, được gọi từ đâu hoặc thuộc nhánh điều kiện nào. Thêm số dòng ngữ cảnh để giữ các dòng không thay đổi xung quanh vùng diff:

```bash
git diff --word-diff=color -U5
```

`-U5` yêu cầu Git hiển thị năm dòng ngữ cảnh trước và sau mỗi vùng thay đổi. Có thể dùng dạng dài:

```bash
git diff --word-diff=color --unified=5
```

Context lines là các dòng không thay đổi được đưa vào output để người đọc hiểu vị trí thay đổi. Chúng không phải một phần của nội dung được thêm hoặc xóa.

## 8. Điều chỉnh số dòng ngữ cảnh với -U

Tùy chọn `-U<n>` hoặc `--unified=<n>` quy định số dòng ngữ cảnh quanh mỗi hunk:

| Lệnh | Kết quả |
| --- | --- |
| `git diff` | Mặc định thường là 3 dòng ngữ cảnh |
| `git diff -U0` | Không hiển thị dòng ngữ cảnh |
| `git diff -U2` | Hiển thị 2 dòng trước và sau |
| `git diff -U5` | Hiển thị 5 dòng trước và sau |
| `git diff --unified=10` | Hiển thị 10 dòng trước và sau |

### Ít context: -U0

```bash
git diff -U0
```

Chế độ này giúp output ngắn, thuận tiện khi cần xác định chính xác dòng bị thay đổi hoặc khi một công cụ khác đã cung cấp ngữ cảnh. Tuy nhiên, reviewer có thể khó biết thay đổi thuộc hàm, khối điều kiện hay cấu hình nào.

Không nên dùng `-U0` làm lựa chọn duy nhất cho review nghiệp vụ.

### Context vừa phải: -U3 hoặc -U5

```bash
git diff --word-diff=color -U3
git diff --word-diff=color -U5
```

Ba dòng là mặc định phổ biến của unified diff. Năm dòng có thể hữu ích khi code có nhiều điều kiện hoặc đoạn cấu hình liên quan nằm gần nhau.

### Nhiều context: -U10

```bash
git diff --word-diff=color -U10
```

Tăng context giúp người review hiểu logic bao quanh, nhưng output sẽ dài hơn. Với file lớn có nhiều vùng thay đổi, quá nhiều context có thể làm diff khó quét nhanh.

## 9. Hiểu hunk và header trong unified diff

Một diff thường được chia thành các vùng gọi là hunk. Header có dạng:

```text
@@ -20,7 +20,8 @@
```

Ý nghĩa:

- `-20,7`: phía cũ bắt đầu tại dòng 20 và có 7 dòng trong vùng được mô tả.
- `+20,8`: phía mới bắt đầu tại dòng 20 và có 8 dòng trong vùng được mô tả.
- Các dòng tiếp theo biểu diễn nội dung cũ, mới và phần không thay đổi.

Context lines giúp nối phần thay đổi với nội dung xung quanh. Khi giảm `-U`, hunk ngắn hơn; khi tăng `-U`, hunk chứa nhiều dòng không thay đổi hơn.

Ví dụ cấu trúc minh họa:

```diff
@@ -20,5 +20,5 @@
 public void settle(Payment payment) {
     validate(payment);
-    payment.complete();
+    payment.completeWithReceipt();
     publishEvent(payment);
 }
```

Nếu dùng `-U0`, các dòng `validate`, `publishEvent` và dấu ngoặc có thể không xuất hiện. Reviewer sẽ thấy thay đổi nhưng ít thông tin hơn về luồng xử lý.

## 10. Dùng --inter-hunk-context để nối các vùng diff gần nhau

Một file có thể có nhiều hunk riêng biệt. Khi hai hunk nằm gần nhau, `--inter-hunk-context=<n>` cho phép Git đưa thêm tối đa `<n>` dòng giữa chúng và gộp chúng thành một hunk lớn hơn:

```bash
git diff --inter-hunk-context=5
```

Tùy chọn này khác `-U`:

- `-U<n>` điều chỉnh số dòng ngữ cảnh quanh mỗi hunk.
- `--inter-hunk-context=<n>` quyết định có gộp các hunk gần nhau hay không bằng cách hiển thị phần nằm giữa chúng.

Ví dụ:

```bash
git diff -U2 --inter-hunk-context=5
```

Lệnh này dùng hai dòng ngữ cảnh quanh vùng thay đổi và gộp các hunk cách nhau không quá năm dòng. Nó hữu ích khi các thay đổi gần nhau thuộc cùng một đoạn logic.

Nếu đặt giá trị quá lớn, nhiều thay đổi độc lập có thể bị gom vào một hunk dài. Chọn giá trị nhỏ vừa đủ để giữ quan hệ giữa các thay đổi.

## 11. Hiển thị toàn bộ hàm bằng --function-context

Đôi khi vài dòng ngữ cảnh chưa đủ để hiểu một thay đổi. Dùng:

```bash
git diff --function-context
```

Hoặc dạng rút gọn:

```bash
git diff -W
```

Tùy chọn này hiển thị toàn bộ phần hàm bao quanh vùng thay đổi theo quy tắc nhận diện function của Git. Nó hữu ích khi một dòng thay đổi phụ thuộc vào nhiều dòng trong cùng hàm.

Git không phân tích cú pháp mọi ngôn ngữ như compiler. Cách nhận diện function phụ thuộc vào diff driver và các mẫu xfuncname mà Git biết. Với ngôn ngữ hoặc định dạng riêng, phần function context có thể không chính xác như mong đợi.

Có thể kết hợp function context với word diff:

```bash
git diff --word-diff=color --function-context
```

Nếu function quá dài, output có thể rất lớn. Chỉ dùng khi reviewer cần toàn bộ thân hàm để hiểu thay đổi.

## 12. Kết hợp các tùy chọn trong những workflow thường gặp

### Review thay đổi chưa stage

```bash
git diff --word-diff=color -U5
```

Lệnh này xem thay đổi trong working tree so với index, làm nổi bật từ bị thay đổi và giữ năm dòng ngữ cảnh.

### Review nội dung sắp commit

```bash
git diff --cached --word-diff=color -U5
```

`--cached` là bí danh của `--staged`. Nó so sánh index với `HEAD`, tức phần nội dung đã stage để commit.

### Review một commit

```bash
git show --word-diff=color -U5 <commit>
```

`git show` hiển thị commit cùng diff của nó. Có thể dùng `--function-context` nếu cần xem toàn bộ hàm liên quan.

### Review khác biệt giữa hai nhánh

```bash
git diff --word-diff=color -U5 main...feature/payment
```

Với cú pháp ba chấm, Git so sánh merge base của hai nhánh với đầu nhánh thứ hai. Đây thường là cách xem phần thay đổi của branch tính năng kể từ khi tách khỏi `main`.

Nếu muốn so sánh trực tiếp hai snapshot:

```bash
git diff --word-diff=color -U5 main feature/payment
```

Hai revision tách biệt so sánh tree của hai đầu được chỉ định; kết quả có thể khác cú pháp ba chấm khi nhánh nền đã tiến lên.

### Review một file cụ thể

```bash
git diff --word-diff=color -U5 -- src/PaymentService.java
```

Giới hạn path giúp tập trung vào một file và giảm lượng output. Với tên file bắt đầu bằng dấu gạch ngang hoặc có ký tự đặc biệt, dùng `--` để phân tách tùy chọn và path.

## 13. Lưu mặc định bằng Git config

Nếu thường xuyên dùng cùng một số dòng ngữ cảnh, có thể cấu hình mặc định:

```bash
git config --global diff.context 5
```

Giá trị này áp dụng cho các lệnh diff sử dụng cấu hình tương ứng. Khi cần output ngắn hơn, vẫn có thể ghi đè tại lệnh:

```bash
git diff -U0
```

Có thể đặt quy tắc token mặc định:

```bash
git config --global diff.wordRegex '[[:alnum:]_]+|[^[:space:][:alnum:]_]'
```

Thiết lập regex toàn cục ảnh hưởng tới những lần dùng word diff mà không truyền regex riêng. Vì regex có thể làm bỏ qua dấu câu nếu viết không đầy đủ, hãy thử trên một diff nhỏ trước khi áp dụng cho mọi repository.

Xem giá trị và nguồn cấu hình:

```bash
git config --show-origin --get diff.context
git config --show-origin --get diff.wordRegex
```

Xóa một giá trị global khi không còn cần:

```bash
git config --global --unset diff.context
git config --global --unset diff.wordRegex
```

Nếu repository có quy ước riêng, có thể dùng `--local` để chỉ cấu hình trong repository hiện tại.

## 14. Ví dụ thực tế: review thay đổi điều kiện

Giả sử code ban đầu:

```java
if (payment.getAmount() > account.getLimit()) {
    reject(payment);
}
```

Code sau chỉnh:

```java
if (payment.getAmount() >= account.getLimit()) {
    reject(payment);
}
```

Diff theo dòng đánh dấu cả dòng điều kiện. Word diff với regex giữ dấu câu có thể làm nổi bật toán tử `>` đổi thành `>=`:

```bash
git diff --word-diff=color \
  --word-diff-regex='[[:alnum:]_]+|[^[:space:][:alnum:]_]' \
  -U5
```

Khi review, cần kiểm tra nghiệp vụ: giới hạn có bao gồm giá trị bằng limit hay không? Word diff chỉ giúp thấy ký tự thay đổi, không kết luận logic đúng.

## 15. Ví dụ thực tế: review thay đổi câu truy vấn

Trước:

```sql
SELECT id, status
FROM payments
WHERE status = 'PENDING' AND deleted_at IS NULL;
```

Sau:

```sql
SELECT id, status
FROM payments
WHERE status IN ('PENDING', 'PROCESSING') AND deleted_at IS NULL;
```

Dùng:

```bash
git diff --word-diff=color -U4 -- db/queries/payment.sql
```

Word diff cho thấy điều kiện `=` được thay bằng `IN` và thêm trạng thái `PROCESSING`. Context lines giữ lại `SELECT`, `FROM` và phần điều kiện xung quanh để reviewer hiểu truy vấn đang lọc bảng nào.

Reviewer vẫn cần kiểm tra index, cardinality, kết quả nghiệp vụ và ảnh hưởng hiệu năng. Cách hiển thị diff không thay thế việc chạy query test.

## 16. Ví dụ thực tế: review thay đổi tài liệu

Trước:

```text
The payment request is stored after validation.
```

Sau:

```text
The payment request is published after validation.
```

Dùng word diff:

```bash
git diff --word-diff=plain -U2 -- docs/payment-flow.md
```

Kết quả sẽ cho thấy từ `stored` được thay bằng `published`. Trong tài liệu, thay một từ có thể làm đổi ý nghĩa kiến trúc hoặc cam kết API; reviewer cần kiểm tra xem mô tả mới có khớp với hành vi thực tế hay không.

## 17. Đọc output và tránh hiểu nhầm

Một số điểm cần nhớ:

- Word diff phân tích các token theo regex, không hiểu ngữ nghĩa ngôn ngữ lập trình.
- Regex không khớp ký tự nào thì ký tự đó có thể bị bỏ qua trong phép so sánh từ.
- Tokenizer khác nhau có thể làm output khác nhau dù file không đổi.
- Context lines chỉ thêm dòng không đổi vào output; chúng không làm thay đổi phạm vi nội dung được stage.
- `--inter-hunk-context` gộp hunk gần nhau; nó không thay thế số dòng context quanh hunk.
- `--function-context` dựa trên quy tắc nhận diện function, không bảo đảm hiểu đúng mọi ngôn ngữ.
- Diff không tự hiển thị file untracked trong phép so sánh mặc định.

Nếu output trông lạ, chạy lại diff thông thường:

```bash
git diff
```

Sau đó thử từng tùy chọn riêng:

```bash
git diff --word-diff=color
git diff -U5
git diff --word-diff=color -U5
```

So sánh các kết quả giúp xác định vấn đề đến từ tokenizer, context hay chính nội dung thay đổi.

## 18. Lựa chọn thiết lập phù hợp khi review

| Mục đích | Gợi ý |
| --- | --- |
| Review code thông thường | `git diff --word-diff=color -U3` |
| Review dòng dài hoặc JSON | Word diff với regex giữ dấu câu, kết hợp `-U5` |
| Review thay đổi trong một hàm | `--function-context` hoặc `-W` |
| Nhóm nhiều hunk gần nhau | `--inter-hunk-context=3` hoặc giá trị nhỏ phù hợp |
| Output ngắn cho kiểm tra tự động | `-U0` hoặc `--word-diff=porcelain` tùy mục đích |
| Review tài liệu và câu chữ | Word diff với regex theo từ; kiểm tra thêm dấu câu bằng diff thường |

Không có một cấu hình phù hợp cho mọi loại file. Chọn cách hiển thị sao cho reviewer thấy được thay đổi và đủ ngữ cảnh để đánh giá tác động.

## 19. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Word diff không hiển thị thay đổi dấu câu | Regex chỉ khớp chữ và số nên dấu câu bị bỏ qua | Dùng regex giữ dấu câu hoặc bỏ regex tùy chỉnh |
| Word diff đánh dấu cả từ dài | Token mặc định tách theo khoảng trắng | Chọn `--word-diff-regex` phù hợp |
| Output không có màu | Mode không phải `color`, terminal/pager không hỗ trợ hoặc màu bị tắt | Dùng `--word-diff=plain` hoặc kiểm tra `color.diff` |
| Diff quá ngắn, khó hiểu | Dùng `-U0` hoặc context quá ít | Tăng `-U3`, `-U5` hoặc dùng `-W` |
| Diff quá dài | Context lớn hoặc hunk bị nối quá rộng | Giảm `-U` và `--inter-hunk-context` |
| Hai vùng thay đổi gần nhau vẫn tách biệt | Khoảng cách giữa hunk vượt ngưỡng inter-hunk | Tăng `--inter-hunk-context` vừa đủ |
| Function context không đúng | Git không nhận diện được ranh giới hàm của ngôn ngữ | Dùng context cố định hoặc cấu hình diff driver phù hợp |
| File mới không xuất hiện | File untracked không thuộc phép so sánh mặc định | Kiểm tra trạng thái và stage file khi phù hợp |

## 20. Quy trình review đề xuất

Khi review một thay đổi có dòng dài hoặc logic quan trọng:

1. Kiểm tra trạng thái repository:

   ```bash
   git status -sb
   ```

2. Xem diff theo dòng để nắm phạm vi tổng thể:

   ```bash
   git diff
   ```

3. Xem phần thay đổi trong từng dòng:

   ```bash
   git diff --word-diff=color -U5
   ```

4. Nếu cần hiểu toàn bộ hàm, dùng:

   ```bash
   git diff --word-diff=color --function-context
   ```

5. Kiểm tra riêng nội dung đã stage:

   ```bash
   git diff --cached --word-diff=color -U5
   ```

6. Chạy test, formatter, linter hoặc kiểm tra nghiệp vụ phù hợp với thay đổi.
7. Đọc lại diff thông thường trước khi commit để chắc chắn không bỏ sót thay đổi cấu trúc, dấu câu hoặc whitespace.

Quy trình này giúp reviewer dùng word diff để phát hiện thay đổi nhỏ, đồng thời vẫn kiểm tra được cấu trúc và ngữ cảnh rộng hơn.

## 21. Bài thực hành

Thực hiện trong repository thử nghiệm:

### Bài 1 — So sánh theo từ

1. Tạo một file văn bản có một câu dài.
2. Commit phiên bản ban đầu.
3. Sửa một từ ở giữa câu.
4. Chạy `git diff` và quan sát diff theo dòng.
5. Chạy `git diff --word-diff=plain` rồi `git diff --word-diff=color`.
6. Xác định phần từ bị xóa và phần từ được thêm.

### Bài 2 — Thử regex

1. Tạo một dòng code có identifier và toán tử.
2. Thay `>` thành `>=`.
3. Chạy word diff với regex `[[:alnum:]_]+`.
4. Quan sát xem toán tử có được thể hiện hay không.
5. Chạy lại với regex giữ cả dấu câu:

   ```bash
   git diff --word-diff=color \
     --word-diff-regex='[[:alnum:]_]+|[^[:space:][:alnum:]_]'
   ```

6. Giải thích vì sao kết quả khác nhau.

### Bài 3 — Điều chỉnh context

1. Sửa hai vùng cách nhau vài dòng trong cùng file.
2. Chạy `git diff -U0`.
3. Chạy `git diff -U3` và `git diff -U8`.
4. Chạy `git diff -U2 --inter-hunk-context=5`.
5. So sánh cách Git nhóm các hunk.
6. Dùng `git diff -W` để xem function context và nhận xét mức độ hữu ích.

### Bài 4 — Review thay đổi đã stage

1. Stage một phần thay đổi.
2. Chạy `git diff --cached --word-diff=color -U5`.
3. So sánh với `git diff` để phân biệt staged và unstaged changes.
4. Kiểm tra lại nội dung dự kiến đưa vào commit.

## 22. Tự kiểm tra kiến thức

1. Word diff giải quyết hạn chế nào của diff theo dòng?
2. `--word-diff=color`, `plain`, `porcelain` và `none` khác nhau thế nào?
3. `--color-words` tương đương với tùy chọn nào?
4. Vì sao regex chỉ khớp chữ và số có thể che khuất thay đổi dấu câu?
5. `-U0`, `-U3` và `-U10` làm thay đổi phần nào của output?
6. `--inter-hunk-context` khác `-U` ở điểm nào?
7. `--function-context` dựa vào cơ chế gì và có giới hạn nào?
8. Làm thế nào xem word diff của thay đổi đã stage?
9. Vì sao nên xem diff theo dòng bên cạnh word diff khi review code?
10. Nếu file mới chưa stage, vì sao `git diff` có thể không hiển thị file đó?

## Kết luận

`--word-diff` giúp xem thay đổi ở mức từ; các mode `color`, `plain`, `porcelain` và `none` điều khiển cách trình bày. `--word-diff-regex` tùy chỉnh cách Git chia token, nhưng phần ký tự không khớp regex có thể bị bỏ qua khi tìm khác biệt, nên regex dùng cho code cần giữ cả dấu câu. `-U<n>` điều chỉnh số dòng ngữ cảnh, `--inter-hunk-context` nối các hunk gần nhau và `--function-context` mở rộng tới toàn bộ hàm theo quy tắc nhận diện của Git. Kết hợp các tùy chọn phù hợp giúp review rõ hơn mà không làm thay đổi nội dung repository.
