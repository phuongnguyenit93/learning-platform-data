# Ngữ nghĩa vận hành

Trong ngôn ngữ chuyên biệt miền (Domain-Specific Language, DSL), cú pháp quy định chương trình được viết như thế nào, còn ngữ nghĩa xác định chương trình có ý nghĩa gì. Một cách mô tả ngữ nghĩa có nền tảng vững chắc trong khoa học máy tính là **ngữ nghĩa vận hành (operational semantics)**. Phương pháp này giải thích ý nghĩa của chương trình bằng cách mô tả các bước mà một máy trừu tượng thực hiện khi chạy chương trình.

Thay vì chỉ nói một biểu thức “có giá trị là 12” hoặc một quy tắc “cho phép giao hàng”, ngữ nghĩa vận hành chỉ ra trạng thái ban đầu, thao tác được thực hiện, trạng thái tiếp theo và điều kiện để quá trình tiếp tục hoặc kết thúc. Nhờ đó, người thiết kế DSL có thể mô tả chính xác cách biểu thức được đánh giá, biến được cập nhật, điều kiện được kiểm tra, quy tắc được kích hoạt, sự kiện được phát ra và lỗi được xử lý.

Ngữ nghĩa vận hành đặc biệt hữu ích khi DSL có biểu thức, câu lệnh, luồng điều khiển, trạng thái hoặc tác động đến hệ thống bên ngoài. Nó cũng giúp nhóm phát triển xây dựng interpreter, runtime, bộ kiểm thử và tài liệu có cùng một cách hiểu về hành vi của ngôn ngữ.

## 1. Ngữ nghĩa vận hành là gì?

**Ngữ nghĩa vận hành** mô tả ý nghĩa của một chương trình thông qua sự tiến triển của nó trong một hệ thống thực thi trừu tượng. Chương trình được xem là một cấu trúc đang được thực hiện; mỗi bước thực thi có thể biến đổi cấu trúc chương trình, trạng thái bộ nhớ hoặc cả hai.

Ví dụ, xét một DSL biểu thức đơn giản:

```text
so_luong * don_gia + phi_giao_hang
```

Ngữ nghĩa vận hành cần xác định:

1. `so_luong`, `don_gia` và `phi_giao_hang` được tra cứu ở đâu.
2. Giá trị của từng tên được lấy như thế nào.
3. Phép nhân được thực hiện trước phép cộng hay không.
4. Kiểu và đơn vị của các toán hạng có tương thích không.
5. Phép toán tạo ra giá trị mới hay thay đổi trạng thái nào.
6. Điều gì xảy ra nếu thiếu biến, sai kiểu hoặc có lỗi số học.

Nếu `so_luong = 2`, `don_gia = 100000 VND/đơn_vị` và `phi_giao_hang = 15000 VND`, kết quả có thể là `215000 VND`, với điều kiện DSL định nghĩa phép nhân và cộng tiền tệ theo cách đó. Mô tả vận hành làm rõ quá trình tạo ra kết quả thay vì chỉ đưa ra một ví dụ đầu ra.

### 1.1. Máy trừu tượng

Ngữ nghĩa vận hành thường giả định một **máy trừu tượng (abstract machine)**. Đây không nhất thiết là CPU hay máy ảo được triển khai thật. Nó là mô hình đơn giản hóa những thành phần cần thiết để giải thích hành vi của DSL.

Một máy trừu tượng có thể gồm:

- Chương trình hoặc biểu thức đang được đánh giá.
- Môi trường tên (environment) ánh xạ tên biến sang giá trị hoặc vị trí lưu trữ.
- Bộ nhớ trừu tượng (store) chứa trạng thái có thể thay đổi.
- Ngăn xếp lời gọi hoặc ngữ cảnh điều khiển nếu DSL có hàm.
- Tập hàm miền mà chương trình được phép gọi.
- Hệ thống sự kiện hoặc trạng thái nghiệp vụ nếu DSL mô tả quy trình.
- Quy tắc lỗi và điều kiện kết thúc.

Máy trừu tượng chỉ cần đủ để định nghĩa những hành vi mà người dùng DSL có thể quan sát. Nếu DSL không có biến thay đổi, có thể không cần store. Nếu DSL chỉ khai báo ràng buộc, máy có thể chỉ cần mô hình dữ liệu và bộ đánh giá biểu thức.

### 1.2. Ý nghĩa được mô tả bằng bước thực thi

Một bước vận hành có thể được viết bằng mũi tên chuyển trạng thái:

```text
trang_thai_ban_dau  ->  trang_thai_tiep_theo
```

Ví dụ, trong một DSL mệnh lệnh:

```text
x = 2 + 3
```

có thể diễn ra theo các bước trừu tượng:

```text
x = 2 + 3
    -> x = 5
    -> trạng thái bộ nhớ có x = 5
```

Mỗi mũi tên biểu diễn một chuyển đổi được ngữ nghĩa cho phép. Các quy tắc phải đủ rõ để hai cách triển khai tuân thủ cùng đặc tả không tự chọn những hành vi khác nhau.

## 2. Vì sao DSL cần ngữ nghĩa vận hành?

Một DSL có thể có cú pháp ngắn gọn và dễ đọc nhưng vẫn mơ hồ về hành vi. Ngữ nghĩa vận hành cung cấp mô tả chính xác cho runtime và người dùng.

### 2.1. Xác định hành vi thực thi

Ngữ nghĩa vận hành trả lời các câu hỏi như:

- Biểu thức được đánh giá theo thứ tự nào?
- Điều kiện `AND` có đánh giá ngắn mạch không?
- Câu lệnh gán thay đổi biến ở phạm vi nào?
- Một quy tắc được áp dụng một lần hay lặp lại khi điều kiện còn đúng?
- Khi nhiều quy tắc cùng thỏa mãn, quy tắc nào chạy trước?
- Khi một bước thất bại, chương trình dừng hay tiếp tục?

Đây là những quyết định có thể ảnh hưởng trực tiếp đến kết quả nghiệp vụ.

### 2.2. Làm rõ ngữ nghĩa của cấu trúc miền

DSL thường có các thao tác mang nghĩa miền như `tinh_phi`, `phe_duyet`, `chuyen_trang_thai`, `phan_bo_tai_nguyen` hoặc `ap_dung_chinh_sach`. Ngữ nghĩa vận hành có thể mô tả dữ liệu được đọc, điều kiện cần, tác động được tạo và kết quả trả về của từng thao tác.

Ví dụ, `chuyen_trang_thai don_hang den DA_GIAO` có thể chỉ hợp lệ khi đơn đã được bàn giao và có xác nhận giao thành công. Ngữ nghĩa phải nói rõ bước kiểm tra và biến đổi trạng thái.

### 2.3. Tạo nền tảng cho interpreter và runtime

Interpreter cần biết cách đánh giá từng node AST. Nếu đặc tả ngữ nghĩa chỉ nói chung chung, mỗi lập trình viên có thể viết evaluator theo một cách khác nhau. Mô tả vận hành cung cấp các quy tắc làm cơ sở cho việc triển khai.

### 2.4. Hỗ trợ kiểm thử và gỡ lỗi

Khi ngữ nghĩa được mô tả bằng các bước và điều kiện, nhóm có thể tạo test cho từng quy tắc, quan sát trạng thái trước và sau, cũng như xác định bước đầu tiên khác với kết quả mong đợi.

### 2.5. Phân biệt hành vi hợp lệ và không hợp lệ

Ngữ nghĩa vận hành có thể định nghĩa rõ khi nào chương trình tiến triển, khi nào phát sinh lỗi, khi nào bị treo hoặc khi nào kết thúc bình thường. Điều này quan trọng với DSL có quyền tác động đến dữ liệu hoặc quy trình.

## 3. Cấu hình thực thi và ký hiệu hình thức

Để mô tả ngữ nghĩa vận hành, trước hết cần xác định một **cấu hình (configuration)**. Cấu hình chứa những thành phần đủ để mô tả trạng thái hiện tại của chương trình.

### 3.1. Cấu hình đơn giản

Với DSL chỉ có biểu thức thuần, cấu hình có thể chỉ là biểu thức đang đánh giá:

```text
<e>
```

Trong đó `e` là một biểu thức. Chuyển đổi từ biểu thức này sang biểu thức khác được ký hiệu:

```text
e -> e'
```

Đọc là “biểu thức `e` thực hiện một bước và trở thành biểu thức `e'`”.

### 3.2. Cấu hình có môi trường và bộ nhớ

Với DSL có biến, một cấu hình có thể được viết:

```text
<c, env, store>
```

Trong đó:

- `c` là câu lệnh hoặc biểu thức đang thực hiện.
- `env` ánh xạ tên biến sang vị trí hoặc giá trị.
- `store` ánh xạ vị trí lưu trữ sang giá trị hiện tại.

Nếu DSL không phân biệt tên và vị trí lưu trữ, có thể gộp `env` và `store` thành một ánh xạ đơn giản. Việc tách chúng hữu ích khi mô tả biến có thể được gán lại, tham chiếu hoặc có phạm vi lồng nhau.

### 3.3. Quan hệ chuyển trạng thái

Một bước thực thi được biểu diễn bằng quan hệ:

```text
<c, env, store> -> <c', env', store'>
```

Nó cho biết cấu hình hiện tại chuyển sang cấu hình tiếp theo. Dấu phẩy trên (`'`) chỉ phiên bản sau của thành phần tương ứng; nó không phải phép đạo hàm.

Nếu một lần thực thi cần nhiều bước, ta có thể viết:

```text
S0 -> S1 -> S2 -> ... -> Sn
```

`S0` là cấu hình ban đầu và `Sn` là cấu hình cuối cùng nếu quá trình kết thúc.

### 3.4. Phán đoán (judgment)

Một **phán đoán ngữ nghĩa** là phát biểu hình thức về một chương trình hoặc cấu hình. Ví dụ:

```text
env, store |- e : T
```

Đọc là “trong môi trường `env` và bộ nhớ `store`, biểu thức `e` có kiểu `T`”. Đây là phán đoán kiểu, thường thuộc ngữ nghĩa tĩnh hoặc hệ thống kiểu.

Một phán đoán đánh giá big-step có thể viết:

```text
<e, env, store> ⇓ <v, store'>
```

Đọc là “biểu thức `e`, trong môi trường và bộ nhớ ban đầu, được đánh giá thành giá trị `v` và bộ nhớ sau `store'`”.

Ký hiệu có thể thay đổi giữa các tài liệu. Điều quan trọng là định nghĩa rõ ý nghĩa của từng ký hiệu trước khi dùng.

## 4. Quy tắc suy diễn

Ngữ nghĩa vận hành thường được trình bày bằng **quy tắc suy diễn (inference rule)**. Mỗi quy tắc có các tiền đề ở phía trên gạch ngang và kết luận ở phía dưới.

Ví dụ dạng tổng quát:

```text
Tiền đề 1    Tiền đề 2    ...    Tiền đề n
-------------------------------------------
                  Kết luận
```

Nếu mọi tiền đề đều đúng, kết luận được phép suy ra. Quy tắc không chỉ mô tả kết quả mà còn cho biết điều kiện để kết quả đó hợp lệ.

### 4.1. Quy tắc cho literal

Một literal số tự đánh giá thành chính giá trị của nó:

```text
---------------------------  (E-Number)
<n, env, store> ⇓ <n, store>
```

Quy tắc này nói rằng giá trị số `n` không cần tra cứu môi trường và không làm thay đổi bộ nhớ.

### 4.2. Quy tắc cho biến

Giả sử `env(x) = l` và `store(l) = v`, trong đó `l` là vị trí lưu trữ của biến `x`. Khi đó:

```text
env(x) = l       store(l) = v
--------------------------------  (E-Variable)
<x, env, store> ⇓ <v, store>
```

Quy tắc yêu cầu tên biến phải được liên kết đến vị trí hợp lệ và vị trí đó phải có giá trị. Nếu không, ngữ nghĩa cần định nghĩa lỗi tham chiếu hoặc lỗi chưa khởi tạo.

### 4.3. Quy tắc cho phép cộng

Giả sử cả hai toán hạng được đánh giá thành số và phép cộng được hỗ trợ:

```text
<e1, env, store> ⇓ <n1, store1>
<e2, env, store1> ⇓ <n2, store2>
-------------------------------------------  (E-Add)
<e1 + e2, env, store> ⇓ <n1 + n2, store2>
```

Quy tắc này minh họa đánh giá trái trước, rồi đánh giá phải trong trạng thái bộ nhớ đã được cập nhật sau vế trái. Nếu DSL chỉ cho phép biểu thức thuần, `store1` và `store2` sẽ bằng `store`.

Với kiểu miền như `Money`, phép cộng còn cần điều kiện hai giá trị cùng loại tiền tệ hoặc có quy tắc quy đổi rõ ràng. Điều kiện kiểu có thể được bảo đảm ở bước kiểm tra tĩnh hoặc được kiểm tra khi chạy.

### 4.4. Tiền đề và điều kiện áp dụng

Một quy tắc cần nêu đủ điều kiện để tránh hành vi không xác định. Ví dụ, phép chia cần điều kiện mẫu số khác 0. Nếu điều kiện không thỏa mãn, có thể có một quy tắc lỗi riêng:

```text
<e1, env, store> ⇓ <n1, store1>
<e2, env, store1> ⇓ <0, store2>
-------------------------------------------  (E-DivideByZero)
<e1 / e2, env, store> ⇓ <error(DIVIDE_BY_ZERO), store2>
```

Đây là cách mô tả minh họa. DSL cũng có thể dùng ngoại lệ, kiểu kết quả `Result` hoặc dừng thực thi ngay khi gặp lỗi.

## 5. Ngữ nghĩa big-step

**Ngữ nghĩa big-step** (còn gọi là natural semantics) mô tả mối quan hệ giữa chương trình ban đầu và kết quả cuối cùng của nó. Thay vì ghi lại mọi bước trung gian, nó tập trung vào câu hỏi: chương trình này được đánh giá thành giá trị hoặc trạng thái nào?

### 5.1. Ký hiệu đánh giá

Với biểu thức, có thể dùng:

```text
<e, env, store> ⇓ <v, store'>
```

Trong đó `⇓` biểu thị quan hệ đánh giá hoàn tất. Với một biểu thức thuần không thay đổi trạng thái, ký hiệu có thể rút gọn thành:

```text
e ⇓ v
```

### 5.2. Ví dụ đánh giá biểu thức số học

Giả sử DSL có biểu thức `2 + 3 * 4`, và phép nhân có độ ưu tiên cao hơn phép cộng. Các quy tắc big-step có thể cho kết quả:

```text
3 * 4 ⇓ 12
2 + 12 ⇓ 14
```

Kết quả toàn biểu thức là `14`. Mô tả big-step không nhất thiết thể hiện từng bước thay thế cú pháp, nhưng có thể trình bày cây suy diễn để cho thấy các quy tắc con đã được áp dụng.

### 5.3. Quy tắc cho điều kiện

Với câu lệnh `if`, hai quy tắc big-step cơ bản là:

```text
<b, env, store> ⇓ <true, store1>
<c1, env, store1> ⇓ <result, store2>
------------------------------------------------  (S-IfTrue)
<if b then c1 else c2, env, store> ⇓ <result, store2>
```

```text
<b, env, store> ⇓ <false, store1>
<c2, env, store1> ⇓ <result, store2>
------------------------------------------------  (S-IfFalse)
<if b then c1 else c2, env, store> ⇓ <result, store2>
```

Hai quy tắc cho biết chỉ nhánh được chọn mới được thực hiện. Nếu `b` không trả về Boolean hợp lệ hoặc trả về `unknown`, DSL cần có quy tắc riêng.

### 5.4. Ưu điểm của big-step

- Dễ trình bày kết quả cuối cùng của biểu thức hoặc câu lệnh.
- Phù hợp với DSL có đánh giá biểu thức và quy tắc tương đối đơn giản.
- Giúp mô tả quan hệ giữa đầu vào, kết quả và trạng thái sau thực thi.
- Có thể gần với cách viết evaluator đệ quy.

### 5.5. Giới hạn của big-step

Big-step thường không cho thấy các trạng thái trung gian. Nếu một vòng lặp không bao giờ kết thúc, không có quan hệ big-step thành công để mô tả nó. Khi một chương trình chạy vô hạn hoặc mắc kẹt, big-step đơn giản có thể không cho biết nó đã tiến triển đến đâu.

Big-step cũng có thể che khuất thời điểm phát sinh tác động phụ, thứ tự gọi hàm hoặc cách một lỗi xuất hiện giữa các bước. Khi những chi tiết đó quan trọng, small-step thường phù hợp hơn.

## 6. Ngữ nghĩa small-step

**Ngữ nghĩa small-step** mô tả chương trình tiến triển qua từng bước nhỏ. Mỗi bước thay đổi một phần biểu thức hoặc cấu hình. Cách này còn được gọi là structural operational semantics (SOS) khi các quy tắc chuyển trạng thái được xây dựng theo cấu trúc cú pháp.

### 6.1. Ký hiệu chuyển bước

Với biểu thức thuần:

```text
e -> e'
```

Với chương trình có trạng thái:

```text
<c, store> -> <c', store'>
```

Một chuỗi chuyển bước được ký hiệu:

```text
S0 -> S1 -> S2 -> ...
```

Mỗi mũi tên là một bước nhỏ được một quy tắc cho phép.

### 6.2. Quy tắc tính toán cơ bản

Ví dụ, phép cộng hai literal có thể được rút gọn:

```text
2 + 3 -> 5
```

Với biểu thức lồng nhau:

```text
2 + (3 * 4)
-> 2 + 12
-> 14
```

Small-step thể hiện rõ phép nhân được rút gọn trước khi phép cộng hoàn tất.

### 6.3. Quy tắc đánh giá bên trái

Nếu DSL quy định đánh giá toán hạng trái trước, có thể có quy tắc:

```text
e1 -> e1'
-------------------------  (E-AddLeft)
e1 + e2 -> e1' + e2
```

Khi vế trái đã là giá trị `v1`, mới cho phép rút gọn vế phải:

```text
e2 -> e2'
-------------------------  (E-AddRight)
v1 + e2 -> v1 + e2'
```

Cuối cùng, khi cả hai vế là số:

```text
n1 + n2 -> n3
-------------------------  (E-AddCompute)
```

Trong đó `n3` là kết quả phép cộng được định nghĩa trên kiểu số tương ứng.

### 6.4. Trạng thái cuối và trạng thái mắc kẹt

Một cấu hình là **trạng thái cuối (final state)** nếu không cần hoặc không thể thực hiện thêm bước nào và nó biểu diễn kết quả hợp lệ.

Một cấu hình **mắc kẹt (stuck state)** là cấu hình không phải kết quả hợp lệ nhưng cũng không có bước chuyển tiếp được định nghĩa. Ví dụ, nếu DSL không cho phép cộng Boolean với số mà đặc tả không có quy tắc lỗi, biểu thức `true + 2` có thể bị mắc kẹt.

Một đặc tả tốt nên tránh trạng thái mắc kẹt không chủ đích. Nó có thể định nghĩa lỗi kiểu rõ ràng hoặc bảo đảm mọi chương trình được kiểm tra tĩnh đều không thể đi đến cấu hình sai kiểu.

### 6.5. Ưu điểm của small-step

- Thể hiện được trạng thái trung gian và thứ tự thực hiện.
- Phù hợp với vòng lặp, đệ quy, điều khiển luồng và tác động phụ.
- Có thể mô tả chương trình chạy vô hạn hoặc mắc kẹt.
- Hữu ích cho debugger, trace và kiểm thử từng bước.
- Giúp phân tích thứ tự đánh giá và tương tác giữa các câu lệnh.

### 6.6. Giới hạn của small-step

Số lượng quy tắc có thể lớn hơn big-step. Một biểu thức đơn giản cần nhiều quy tắc để mô tả từng vị trí đánh giá. Đặc tả vì vậy có thể dài và khó đọc nếu DSL có nhiều cấu trúc.

## 7. So sánh big-step và small-step

Hai phong cách mô tả bổ sung cho nhau. Không phải DSL chỉ được chọn một; có thể dùng big-step cho phần biểu thức thuần và small-step cho phần trạng thái hoặc tác động phụ.

| Tiêu chí | Big-step | Small-step |
|---|---|---|
| Trọng tâm | Kết quả cuối cùng | Từng bước chuyển trạng thái |
| Ký hiệu thường dùng | `⇓` | `->` hoặc `→` |
| Trạng thái trung gian | Thường không thể hiện | Thể hiện trực tiếp |
| Vòng lặp vô hạn | Khó mô tả tiến triển | Có thể mô tả chuỗi vô hạn |
| Lỗi giữa các bước | Có thể được gộp vào kết quả lỗi | Có thể chỉ rõ bước phát sinh |
| Độ dài đặc tả | Thường ngắn hơn | Thường chi tiết hơn |
| Ứng dụng | Đánh giá biểu thức, quy tắc thuần | Runtime có trạng thái, luồng điều khiển và tác động |

Ví dụ, với `x = 1; x = x + 1`, big-step có thể mô tả trạng thái cuối `x = 2`. Small-step có thể cho thấy lần lượt biến được khởi tạo thành 1 rồi cập nhật thành 2.

## 8. Môi trường, bộ nhớ và trạng thái

DSL có biến hoặc đối tượng thay đổi cần một mô hình trạng thái. Ngữ nghĩa vận hành phải nói rõ tên được phân giải thế nào và giá trị được lưu ở đâu.

### 8.1. Environment

Environment (`env`) ánh xạ tên biến sang giá trị hoặc vị trí lưu trữ. Ví dụ:

```text
env = {
    "so_luong" -> location_1,
    "don_gia"  -> location_2
}
```

Environment có thể được lồng để hỗ trợ phạm vi cục bộ và toàn cục. Khi tra cứu tên, runtime tìm trong phạm vi hiện tại rồi có thể tiếp tục tìm ở phạm vi cha theo quy tắc scope.

### 8.2. Store

Store ánh xạ vị trí lưu trữ sang giá trị:

```text
store = {
    location_1 -> 2,
    location_2 -> Money(100000, VND)
}
```

Khi gán lại biến, environment có thể giữ nguyên ánh xạ tên-vị trí, còn store thay đổi giá trị tại vị trí đó. Cách tách này hữu ích để mô tả tham chiếu và biến có thể thay đổi.

### 8.3. Phạm vi biến

DSL cần xác định biến tồn tại trong phạm vi nào:

- Toàn chương trình hoặc module.
- Trong một hàm.
- Trong một khối lệnh.
- Trong một lần thực thi.
- Trong một phiên workflow kéo dài.

Quy tắc phạm vi ảnh hưởng đến việc tra cứu tên, che khuất biến và thời điểm thu hồi giá trị.

### 8.4. Gán và cập nhật trạng thái

Với câu lệnh `x = e`, runtime đánh giá `e` trước, sau đó cập nhật vị trí lưu trữ của `x`.

Pseudocode:

```text
evaluate e in env and store -> value v and store1
resolve x in env -> location l
store2 = store1 updated with l -> v
result = store2
```

Đặc tả cần nói rõ điều gì xảy ra nếu `x` chưa được khai báo, thuộc tính chỉ đọc hoặc kiểu của `v` không phù hợp.

## 9. Ngữ nghĩa vận hành của câu lệnh

Biểu thức tạo ra giá trị; câu lệnh thường điều khiển trạng thái hoặc thứ tự thực hiện. Một DSL mệnh lệnh cần quy tắc cho từng loại câu lệnh.

### 9.1. Câu lệnh rỗng

Câu lệnh rỗng không thay đổi trạng thái:

```text
<skip, store> -> <done, store>
```

Tên `skip` và `done` chỉ là ký hiệu minh họa.

### 9.2. Gán

Với `x = e`, trước tiên đánh giá `e`, sau đó cập nhật `x`. Nếu biểu thức có tác động phụ, thứ tự này phải được công bố.

### 9.3. Tuần tự

Với `c1; c2`, runtime thực hiện `c1` trước. Khi `c1` hoàn tất bình thường, mới tiếp tục `c2`.

```text
<c1, store> -> <c1', store1>
--------------------------------  (S-SequenceStep)
<c1; c2, store> -> <c1'; c2, store1>
```

Khi `c1` kết thúc:

```text
<done; c2, store> -> <c2, store>
```

Nếu `c1` phát sinh lỗi hoặc hủy, DSL cần quy định `c2` có được chạy hay không. Thông thường, lỗi không phục hồi sẽ kết thúc chuỗi câu lệnh.

### 9.4. Điều kiện

Với `if`, chỉ nhánh tương ứng với giá trị điều kiện được thực hiện. Nếu điều kiện có giá trị unknown, cần một quy tắc bổ sung hoặc lỗi điều kiện chưa xác định.

### 9.5. Vòng lặp

Với `while b do c`, nếu `b` đúng thì thực hiện `c` rồi đánh giá lại `b`; nếu sai thì kết thúc vòng lặp.

```text
while true do c
-> c; while true do c
```

Đây là dạng khai triển khái niệm. Khi DSL cho phép vòng lặp, runtime cần giới hạn tài nguyên hoặc cung cấp cơ chế hủy để tránh chạy vô hạn ngoài dự kiến.

### 9.6. Hàm và lời gọi

Ngữ nghĩa lời gọi hàm cần xác định cách đánh giá đối số, tạo phạm vi tham số, thực thi thân hàm, xử lý giá trị trả về và khôi phục môi trường của bên gọi.

Nếu DSL cho phép hàm đệ quy, cần quy định giới hạn stack hoặc cơ chế thực thi tương ứng. Nếu hàm gọi dịch vụ ngoài, cần xác định lỗi và tác động phụ được truyền về như thế nào.

## 10. Ngữ nghĩa vận hành cho kiểu dữ liệu miền

DSL thường có kiểu miền như tiền tệ, khoảng cách, thời gian, khối lượng, trạng thái hoặc định danh. Các phép toán trên chúng phải được định nghĩa theo ý nghĩa của miền.

### 10.1. Tiền tệ

Phép cộng hai giá trị tiền tệ thường chỉ hợp lệ khi cùng mã tiền tệ:

```text
Money(100000, VND) + Money(20000, VND)
    -> Money(120000, VND)
```

Nếu hai mã tiền khác nhau, DSL có thể báo lỗi kiểu hoặc yêu cầu phép chuyển đổi có tỷ giá và thời điểm rõ ràng. Không nên tự cộng hai con số rồi giữ một mã tiền tùy ý.

### 10.2. Đơn vị đo

Khoảng cách có thể được chuẩn hóa về đơn vị cơ sở trước khi so sánh:

```text
5 km -> 5000 m
5000 m == 5 km -> true
```

Phép toán phải giữ chiều đại lượng. `5 km + 2 kg` là không hợp lệ dù cả hai có thể được lưu bằng số.

### 10.3. Thời gian

Với ngày giờ, cần xác định múi giờ, lịch, độ chính xác và cách tính thời lượng. `DateTime + Duration` có thể tạo thời điểm mới, còn `DateTime - DateTime` có thể tạo `Duration`.

Các phép tính theo tháng hoặc năm không luôn tương đương với số ngày cố định. Ví dụ cộng một tháng vào ngày cuối tháng cần quy tắc lịch rõ ràng.

### 10.4. Trạng thái và enum

Các giá trị enum thường có thể so sánh bằng/khác. Chỉ cho phép thứ tự như `PENDING < APPROVED` nếu mô hình miền định nghĩa rõ thứ tự đó. Thứ tự tên hoặc thứ tự khai báo không tự động là thứ tự nghiệp vụ.

### 10.5. Tham chiếu đối tượng

So sánh hai tham chiếu có thể kiểm tra cùng danh tính, không phải cùng nội dung. DSL cần xác định `==` trên đối tượng là so sánh identity hay structural equality.

## 11. Ngữ nghĩa vận hành cho DSL khai báo và DSL quy tắc

Không phải DSL nào cũng chạy câu lệnh theo thứ tự. DSL khai báo thường mô tả trạng thái mong muốn hoặc ràng buộc; runtime tìm cách đánh giá, kiểm tra hoặc chuyển mô tả thành hành động.

### 11.1. Đánh giá ràng buộc

Một ràng buộc như:

```text
may_chu.cpu >= 4
```

có thể được đánh giá trên mô hình tài nguyên. Kết quả là `true`, `false`, `unknown` hoặc lỗi nếu thuộc tính không hợp lệ, tùy ngữ nghĩa DSL.

### 11.2. Ngữ nghĩa của quy tắc điều kiện

Một quy tắc có thể có dạng:

```text
rule mien_phi_giao_hang {
    when don_hang.tong_tien >= 500000 VND
    then ap_dung_mien_phi
}
```

Runtime cần định nghĩa:

- Quy tắc được đánh giá trên một đối tượng hay toàn bộ tập dữ liệu.
- Điều kiện được đánh giá một lần hay mỗi khi dữ liệu thay đổi.
- Hành động được thực hiện ngay hay chỉ tạo quyết định.
- Một quy tắc có thể kích hoạt nhiều lần hay chỉ một lần.
- Nếu nhiều quy tắc cùng kích hoạt, thứ tự hoặc ưu tiên được xác định ra sao.
- Khi một hành động thay đổi dữ liệu, có đánh giá lại các quy tắc hay không.

### 11.3. Rule engine và vòng lặp suy diễn

Một rule engine có thể thực hiện chu trình:

1. Đọc trạng thái dữ liệu hiện tại.
2. Tìm các quy tắc có điều kiện thỏa mãn.
3. Tạo tập quy tắc đang chờ kích hoạt (agenda).
4. Chọn quy tắc theo chiến lược ưu tiên.
5. Thực hiện hoặc đề xuất hành động.
6. Cập nhật trạng thái và đánh giá lại nếu cần.
7. Dừng khi không còn quy tắc phù hợp hoặc đạt điều kiện kết thúc.

Đây là một mô hình vận hành có trạng thái. Đặc tả cần tránh kích hoạt lặp vô hạn, xác định thứ tự và giải quyết xung đột.

### 11.4. DSL khai báo hạ tầng

Với DSL mô tả trạng thái mong muốn, runtime có thể so sánh cấu hình khai báo với trạng thái thực tế rồi lập kế hoạch tạo, cập nhật hoặc xóa tài nguyên. Ngữ nghĩa cần phân biệt việc **tính kế hoạch** với việc **áp dụng kế hoạch**.

Ví dụ, `server.count = 3` có thể nghĩa là mong muốn có ba máy chủ. Runtime không nhất thiết tạo ba máy chủ ngay khi parse; nó có thể tạo plan rồi chờ xác nhận trước khi áp dụng.

## 12. Tác động phụ và tương tác với môi trường

Một chương trình DSL có thể đọc dữ liệu, ghi dữ liệu, gọi dịch vụ, gửi thông báo hoặc thay đổi trạng thái bên ngoài. Những hành vi này là tác động phụ (side effects) và cần được mô tả trong ngữ nghĩa vận hành.

### 12.1. Hàm thuần và hàm có tác động phụ

Hàm thuần chỉ phụ thuộc vào tham số và trả kết quả, không thay đổi trạng thái bên ngoài. Hàm có tác động phụ có thể đọc hoặc ghi hệ thống ngoài.

Ví dụ:

- `tinh_tong(a, b)` có thể là hàm thuần.
- `ghi_nhat_ky(event)` ghi log.
- `gui_email(address, content)` gửi email.
- `cap_nhat_ton_kho(sku, amount)` thay đổi dữ liệu kho.

Ngữ nghĩa cần chỉ rõ hàm nào được phép gọi, quyền nào cần có và lỗi được truyền về ra sao.

### 12.2. Tách đánh giá khỏi áp dụng hành động

Với DSL chính sách, một thiết kế an toàn là đánh giá trước để tạo ra quyết định, rồi để ứng dụng chủ áp dụng quyết định đó theo quy trình riêng.

```text
Chương trình DSL + dữ liệu đầu vào
              |
              v
       Đánh giá quy tắc
              |
              v
      Quyết định / Action Plan
              |
              v
    Kiểm tra quyền và trạng thái
              |
              v
       Áp dụng tác động
```

Cách tách này hỗ trợ dry run, xem trước và kiểm tra quyết định trước khi ghi dữ liệu.

### 12.3. Giao dịch và hoàn tác

Nếu một quy tắc tạo nhiều thay đổi, DSL hoặc host cần xác định tính nguyên tử. Ví dụ cập nhật trạng thái đơn hàng và trừ tồn kho có thể phải thành công cùng nhau.

Không phải mọi dịch vụ ngoài đều tham gia cùng giao dịch. Với hành động phân tán, ứng dụng chủ có thể cần cơ chế bù trừ hoặc workflow để xử lý trường hợp một bước thành công còn bước khác thất bại.

### 12.4. Tính xác định

Một chương trình là xác định (deterministic) nếu cùng chương trình và cùng trạng thái đầu vào luôn dẫn đến cùng hành vi/kết quả theo mô hình được định nghĩa. Đọc đồng hồ hệ thống, số ngẫu nhiên, dữ liệu mạng hoặc thứ tự không ổn định có thể làm kết quả thay đổi.

Nếu DSL cho phép những nguồn không xác định, cần đưa chúng vào execution context hoặc mô tả rõ trong ngữ nghĩa. Điều này giúp kiểm thử, tái lập và audit.

## 13. Ngữ nghĩa lỗi và ngoại lệ

Ngữ nghĩa vận hành phải định nghĩa điều gì xảy ra khi một bước không thể hoàn tất bình thường.

### 13.1. Các loại lỗi

- Lỗi cú pháp: chương trình không được parser chấp nhận.
- Lỗi tham chiếu: tên hoặc đối tượng không tồn tại.
- Lỗi kiểu: toán hạng không tương thích.
- Lỗi miền: vi phạm bất biến hoặc quy tắc nghiệp vụ.
- Lỗi thực thi: chia cho 0, vượt giới hạn hoặc điều kiện không hợp lệ.
- Lỗi tích hợp: dịch vụ bên ngoài không phản hồi hoặc trả dữ liệu sai.
- Lỗi quyền: chương trình không được phép thực hiện thao tác.
- Lỗi hạ tầng: thiếu bộ nhớ, timeout hoặc tiến trình bị gián đoạn.

### 13.2. Ngoại lệ như một kết quả vận hành

Có thể mô hình hóa kết quả đánh giá bằng hai dạng:

```text
Normal(value, state)
Error(errorInfo, state)
```

Khi đó, quy tắc tuần tự cần nói rõ nếu câu lệnh đầu trả `Error` thì câu lệnh tiếp theo có chạy không. Với lỗi không phục hồi, thường không tiếp tục phần còn lại.

### 13.3. Xử lý lỗi có thể phục hồi

DSL có thể hỗ trợ cấu trúc `try/catch`, kết quả `Result` hoặc nhánh xử lý lỗi. Cần định nghĩa loại lỗi nào có thể bắt, lỗi nào không thể bắt và trạng thái sau lỗi có còn hợp lệ không.

### 13.4. Lỗi một phần

Với DSL thực hiện nhiều hành động, một phần có thể đã thành công trước khi phần sau lỗi. Ngữ nghĩa cần cho biết trạng thái nào được giữ, thao tác nào được hoàn tác và kết quả trả về có đánh dấu partial success hay không.

## 14. Ngữ nghĩa thời gian và sự kiện

DSL quy trình hoặc lịch biểu thường phụ thuộc thời gian và sự kiện. Ngữ nghĩa vận hành cần xác định cách các sự kiện làm thay đổi trạng thái và kích hoạt quy tắc.

### 14.1. Sự kiện

Sự kiện biểu diễn điều đã xảy ra, chẳng hạn `DonHangDaThanhToan`, `KienHangDaBanGiao` hoặc `PipelineFailed`. Runtime có thể nhận sự kiện, cập nhật mô hình và đánh giá các quy tắc liên quan.

### 14.2. Thời điểm và thời lượng

Một biểu thức `now + 24 hours` cần biết `now` lấy từ đâu, múi giờ nào được dùng và đơn vị thời lượng có ý nghĩa gì. Nếu dùng thời gian thực, nên truyền đồng hồ vào context để có thể kiểm thử bằng thời điểm cố định.

### 14.3. Timeout và deadline

DSL có thể mô tả một bước phải hoàn tất trước deadline. Runtime cần định nghĩa mốc bắt đầu, cách tính thời gian, hành vi khi deadline bị bỏ lỡ và cách xử lý khi hệ thống tạm dừng.

### 14.4. Sự kiện trùng lặp và thứ tự đến

Trong hệ thống phân tán, sự kiện có thể đến trùng hoặc sai thứ tự. Nếu DSL xử lý luồng sự kiện, cần xác định việc khử trùng lặp, khóa thứ tự, cửa sổ thời gian và cách xử lý sự kiện đến muộn.

## 15. Tính đồng thời và không xác định

Một số DSL cho phép nhiều tác vụ hoặc quy tắc được thực hiện đồng thời. Khi đó, thứ tự thực hiện có thể ảnh hưởng kết quả.

### 15.1. Thực thi tuần tự

Trong mô hình tuần tự, các bước chạy theo thứ tự đã định. Đây là mô hình đơn giản, dễ dự đoán và thường phù hợp với DSL nhỏ.

### 15.2. Thực thi song song

Nếu hai tác vụ độc lập, runtime có thể chạy đồng thời. Nhưng nếu chúng cùng đọc hoặc ghi một trạng thái, cần quy tắc đồng bộ và giải quyết xung đột.

### 15.3. Race condition

Race condition xảy ra khi kết quả phụ thuộc vào thứ tự xen kẽ của các thao tác đồng thời. Ví dụ hai quy tắc cùng kiểm tra số lượng tồn kho là 1 rồi cả hai cùng đặt giữ một sản phẩm có thể dẫn đến số lượng âm.

Ngữ nghĩa cần quy định khóa, giao dịch, thứ tự ưu tiên hoặc cơ chế xử lý xung đột phù hợp.

### 15.4. Tính xác định trong môi trường đồng thời

Một runtime có thể cho phép thực thi song song nhưng vẫn cần bảo đảm kết quả xác định khi các tác vụ độc lập. Nếu thứ tự có ảnh hưởng, đặc tả phải quy định thứ tự hoặc thừa nhận nhiều kết quả hợp lệ.

## 16. Ngữ nghĩa vận hành và các cách mô tả ngữ nghĩa khác

Ngữ nghĩa vận hành là một trong nhiều cách định nghĩa ý nghĩa ngôn ngữ. Nó có thể kết hợp với ngữ nghĩa denotational và axiomatic.

### 16.1. Ngữ nghĩa denotational

Ngữ nghĩa denotational ánh xạ cấu trúc chương trình sang một đối tượng toán học biểu diễn ý nghĩa của nó. Ví dụ một biểu thức có thể được ánh xạ thành một hàm từ môi trường sang giá trị.

Điểm mạnh là mô tả ý nghĩa ở mức trừu tượng và hỗ trợ lập luận toán học. Nó thường ít tập trung vào từng bước máy thực hiện.

### 16.2. Ngữ nghĩa axiomatic

Ngữ nghĩa axiomatic mô tả chương trình qua các mệnh đề logic về trạng thái trước và sau khi chạy. Một hình thức phổ biến là Hoare triple:

```text
{P} C {Q}
```

Đọc là: nếu điều kiện trước `P` đúng và câu lệnh `C` kết thúc bình thường, thì điều kiện sau `Q` đúng.

Ví dụ:

```text
{x = 2}
x = x + 3
{x = 5}
```

### 16.3. So sánh

| Cách tiếp cận | Trọng tâm | Câu hỏi chính |
|---|---|---|
| Operational | Các bước thực thi | Chương trình tiến triển như thế nào? |
| Denotational | Đối tượng toán học biểu diễn ý nghĩa | Chương trình tương ứng với hàm hoặc giá trị nào? |
| Axiomatic | Điều kiện logic trước/sau | Chương trình bảo đảm thuộc tính nào? |

Các cách tiếp cận không loại trừ nhau. Có thể dùng operational semantics để định nghĩa hành vi, Hoare logic để chứng minh một quy tắc bảo toàn bất biến và denotational semantics để nghiên cứu tính tương đương.

## 17. Từ ngữ nghĩa vận hành đến interpreter

Một interpreter có thể được xây dựng trực tiếp theo các quy tắc vận hành. Mỗi loại node AST được đánh giá theo một hàm hoặc nhánh xử lý tương ứng.

### 17.1. Bộ đánh giá biểu thức

Pseudocode:

```java
Value evaluate(Expression expression, Environment env) {
    return switch (expression) {
        case NumberLiteral n -> new NumberValue(n.value());
        case VariableReference v -> env.lookup(v.name());
        case BinaryExpression b -> {
            Value left = evaluate(b.left(), env);
            Value right = evaluate(b.right(), env);
            yield applyOperator(b.operator(), left, right);
        }
    };
}
```

Đây là ví dụ giản lược. Nếu DSL định nghĩa short-circuit cho `AND` hoặc `OR`, evaluator không được đánh giá cả hai toán hạng theo cách trên một cách vô điều kiện. Nó phải đánh giá vế trái trước và chỉ đánh giá vế phải khi cần.

### 17.2. Bộ thực thi câu lệnh

Interpreter cho câu lệnh có thể trả về trạng thái mới:

```java
ExecutionState execute(Statement statement, ExecutionState state) {
    if (statement instanceof Assignment assignment) {
        Value value = evaluate(assignment.expression(), state.environment());
        return state.withUpdatedVariable(assignment.name(), value);
    }

    if (statement instanceof Sequence sequence) {
        ExecutionState next = execute(sequence.first(), state);
        return execute(sequence.second(), next);
    }

    throw new EvaluationException("Unsupported statement");
}
```

Trong triển khai thật, cần mô hình hóa kết quả lỗi, return, break, continue, tác động phụ, giới hạn tài nguyên và source location.

### 17.3. Big-step hay small-step khi triển khai?

Evaluator đệ quy thường gần với big-step: nhận một node và trả kết quả cuối. Một máy ảo hoặc debugger từng bước thường gần với small-step: giữ cấu hình hiện tại và thực hiện một chuyển đổi mỗi lần.

Kiến trúc runtime có thể dùng cả hai. Ví dụ, một biểu thức thuần được đánh giá đệ quy trong khi workflow engine dùng state machine để điều phối các bước dài.

### 17.4. Giữ ánh xạ về mã nguồn

AST node nên lưu source span để lỗi runtime trỏ về đúng biểu thức hoặc câu lệnh. Nếu chương trình được biên dịch thành bytecode, cần source map từ instruction về node hoặc vị trí nguồn.

## 18. Kiểm thử ngữ nghĩa vận hành

Đặc tả ngữ nghĩa cần được chuyển thành các trường hợp kiểm thử có thể chạy. Mỗi quy tắc vận hành nên có ví dụ chứng minh cả điều kiện áp dụng và kết quả.

### 18.1. Kiểm thử từng quy tắc

Với mỗi loại biểu thức hoặc câu lệnh, kiểm tra:

- Trường hợp hợp lệ cơ bản.
- Trường hợp biên.
- Kiểu không tương thích.
- Dữ liệu thiếu hoặc unknown.
- Lỗi khi đánh giá.
- Trạng thái trước và sau.

### 18.2. Kiểm thử chuỗi bước

Với small-step, có thể kiểm tra từng trạng thái trung gian. Ví dụ:

```text
<x = 2 + 3, store0>
-> <x = 5, store0>
-> <done, store1>
```

Trong đó `store1` chứa giá trị `x = 5`.

### 18.3. Kiểm thử tính tương đương big-step và small-step

Với các chương trình kết thúc bình thường, có thể kiểm tra big-step và small-step cho cùng kết quả cuối. Đây là một cách phát hiện khác biệt giữa hai cách mô tả hoặc hai phần triển khai.

### 18.4. Kiểm thử bất biến

Nếu DSL có invariant, kiểm tra rằng mọi bước chuyển hợp lệ đều giữ invariant hoặc chỉ cho phép chuyển sang trạng thái thỏa invariant. Ví dụ, số lượng tồn kho không được âm sau thao tác đặt giữ hàng.

### 18.5. Kiểm thử lỗi và tác động phụ

Kiểm tra hàm mở rộng chỉ được gọi khi điều kiện cho phép, hành động không chạy khi dry run, và lỗi giữa chuỗi câu lệnh có đúng chính sách dừng hoặc rollback.

### 18.6. Kiểm thử xác định và đồng thời

Chạy lại cùng chương trình với cùng context để xác minh kết quả ổn định. Với tác vụ song song, kiểm tra các thứ tự xen kẽ được cho phép và bảo đảm không phát sinh trạng thái ngoài đặc tả.

## 19. Ví dụ xuyên suốt: ngữ nghĩa vận hành của DSL tính phí giao hàng

Giả sử DSL cho phép khai báo quy tắc miễn phí và tính phí vận chuyển:

```text
policy giao_hang_chuan {
    free_when tong_tien >= 500000 VND
    base_fee = 30000 VND
    fee_per_km = 5000 VND/km
}
```

Runtime nhận dữ liệu đơn hàng:

```text
order = {
    tong_tien: 650000 VND,
    khoang_cach: 8 km
}
```

### 19.1. Xác định trạng thái ban đầu

Có thể mô hình hóa context:

```text
env = {
    tong_tien -> loc_1,
    khoang_cach -> loc_2
}

store = {
    loc_1 -> Money(650000, VND),
    loc_2 -> Distance(8, km)
}
```

### 19.2. Đánh giá điều kiện miễn phí

Biểu thức:

```text
tong_tien >= 500000 VND
```

Được đánh giá bằng cách tra cứu `tong_tien`, tạo literal tiền tệ và áp dụng phép so sánh. Vì `650000 >= 500000`, kết quả là `true`.

### 19.3. Chọn nhánh chính sách

Ngữ nghĩa chính sách có thể quy định:

```text
if free_when then shipping_fee = 0
else shipping_fee = base_fee + distance * fee_per_km
```

Với điều kiện đúng, runtime chọn nhánh miễn phí và không cần tính nhánh còn lại nếu DSL định nghĩa đánh giá nhánh có điều kiện theo kiểu short-circuit.

### 19.4. Kết quả

```text
Decision {
    order_id: DH102,
    shipping_fee: 0 VND,
    reason: FREE_THRESHOLD_MET
}
```

Kết quả trên giả định chính sách miễn phí áp dụng cho toàn bộ phí vận chuyển. Nếu doanh nghiệp vẫn thu phụ phí vùng xa hoặc phụ phí hàng nặng, ngữ nghĩa phải mô tả thứ tự áp dụng và ngoại lệ. Không thể suy ra điều đó chỉ từ cú pháp `free_when`.

### 19.5. Trường hợp điều kiện không đúng

Nếu tổng tiền là `400000 VND`, điều kiện miễn phí trả về false. Runtime đánh giá:

```text
base_fee + distance * fee_per_km
= 30000 + 8 * 5000
= 70000 VND
```

Runtime trả phí `70000 VND`. Đặc tả còn cần quy định làm tròn, giới hạn phí, đơn vị khoảng cách và xử lý khi không có `khoang_cach`.

## 20. Nguyên tắc viết đặc tả ngữ nghĩa vận hành

Một đặc tả có ích cần vừa chính xác vừa có thể dùng để triển khai và kiểm thử.

### 20.1. Xác định cấu hình

Nêu rõ chương trình, môi trường, bộ nhớ, context, dữ liệu miền và thành phần nào thuộc trạng thái thực thi.

### 20.2. Định nghĩa mọi dạng kết quả

Phân biệt kết thúc bình thường, giá trị trả về, lỗi, hủy, timeout, trạng thái unknown và tác động một phần nếu DSL có hỗ trợ.

### 20.3. Quy định thứ tự đánh giá

Nêu rõ thứ tự toán hạng, short-circuit, thứ tự câu lệnh, ưu tiên quy tắc và hành vi khi nhiều tác vụ cùng áp dụng.

### 20.4. Định nghĩa kiểu và thao tác miền

Mỗi toán tử và hàm miền cần hợp đồng kiểu, điều kiện áp dụng, kết quả và lỗi. Đơn vị, múi giờ, enum và định danh phải có ý nghĩa rõ.

### 20.5. Mô tả tác động phụ

Nêu dữ liệu nào được đọc hoặc ghi, quyền nào cần có, giao dịch có nguyên tử không và điều gì xảy ra nếu một bước thất bại.

### 20.6. Tránh hành vi không xác định

Nếu một trường hợp không được hỗ trợ, hãy định nghĩa lỗi hoặc hành vi từ chối. Không để runtime tự quyết định theo cách triển khai.

### 20.7. Dùng ví dụ có thể kiểm chứng

Mỗi quy tắc nên đi kèm ví dụ đầu vào, cấu hình ban đầu, kết quả hoặc chuỗi chuyển trạng thái và trường hợp lỗi. Ví dụ nên bao gồm trường hợp biên chứ không chỉ tình huống thuận lợi.

## 21. Những sai lầm thường gặp

### 21.1. Chỉ mô tả kết quả mà bỏ qua trạng thái

Với DSL có biến hoặc tác động phụ, kết quả cuối không cho biết các trạng thái trung gian và thứ tự thao tác. Hãy mô tả environment, store hoặc state machine khi chúng ảnh hưởng đến hành vi.

### 21.2. Không định nghĩa thứ tự đánh giá

Hai evaluator có thể gọi hàm theo thứ tự khác nhau và tạo tác động phụ khác nhau. Cần công bố thứ tự và short-circuit.

### 21.3. Nhầm lỗi với giá trị false

Điều kiện không thỏa mãn, dữ liệu chưa biết và lỗi đánh giá là những trường hợp khác nhau. Không nên tự động biến tất cả thành `false`.

### 21.4. Bỏ qua trạng thái cuối và trạng thái mắc kẹt

Một chương trình không còn bước chuyển không nhất thiết đã kết thúc thành công. Đặc tả cần phân biệt final state với stuck state.

### 21.5. Để hành động bên ngoài chạy ngay trong lúc đánh giá

Điều này làm khó dry run, rollback và kiểm thử. Với DSL chính sách, có thể tách quyết định khỏi bước áp dụng tác động.

### 21.6. Không định nghĩa hành vi khi nhiều quy tắc cùng đúng

Rule engine có thể kích hoạt nhiều quy tắc cùng lúc. Cần chính sách ưu tiên, thứ tự hoặc cơ chế giải quyết xung đột.

### 21.7. Dùng ví dụ không đại diện cho quy tắc

Một ví dụ tính phí đúng không chứng minh mọi trường hợp đều đúng. Cần thử ngưỡng, đơn vị khác nhau, dữ liệu thiếu, lỗi dịch vụ và ngoại lệ.

### 21.8. Đặc tả và interpreter không đồng bộ

Nếu code runtime thay đổi mà tài liệu không cập nhật, người dùng và người triển khai sẽ có hai cách hiểu. Bộ kiểm thử conformance nên gắn trực tiếp với các quy tắc vận hành.

## 22. Thuật ngữ cần nhớ

| Thuật ngữ | Ý nghĩa |
|---|---|
| Operational Semantics | Mô tả ý nghĩa chương trình qua các bước thực thi |
| Abstract Machine | Máy trừu tượng dùng để mô hình hóa việc chạy chương trình |
| Configuration | Trạng thái hiện tại của chương trình và môi trường thực thi |
| Transition Relation | Quan hệ mô tả một cấu hình chuyển sang cấu hình khác |
| Inference Rule | Quy tắc suy diễn với tiền đề và kết luận |
| Big-step Semantics | Mô tả quan hệ từ chương trình đến kết quả cuối |
| Small-step Semantics | Mô tả từng bước tiến triển của chương trình |
| Structural Operational Semantics (SOS) | Ngữ nghĩa vận hành được định nghĩa theo cấu trúc cú pháp |
| Environment | Ánh xạ tên biến sang giá trị hoặc vị trí lưu trữ |
| Store | Ánh xạ vị trí lưu trữ sang giá trị hiện tại |
| Final State | Cấu hình đã kết thúc theo cách hợp lệ |
| Stuck State | Cấu hình không phải kết quả hợp lệ và không có bước chuyển được định nghĩa |
| Side Effect | Tác động quan sát được ngoài giá trị trả về |
| Determinism | Tính chất cùng đầu vào và trạng thái tạo cùng hành vi/kết quả theo đặc tả |
| Hoare Triple | Dạng `{P} C {Q}` mô tả điều kiện trước và sau của câu lệnh |
| Denotational Semantics | Mô tả ý nghĩa bằng cách ánh xạ chương trình sang đối tượng toán học |
| Axiomatic Semantics | Mô tả tính đúng đắn bằng các mệnh đề logic |

Ngữ nghĩa vận hành cung cấp một cách diễn đạt có hệ thống về cách DSL thực sự hoạt động. Bằng cách xác định cấu hình, quy tắc suy diễn, thứ tự đánh giá, trạng thái, tác động và lỗi, nhóm phát triển có thể biến những mô tả ngôn ngữ thành một hợp đồng thực thi rõ ràng. Hợp đồng đó là cơ sở để xây dựng runtime nhất quán, kiểm thử được và có thể giải thích cho người dùng miền.
