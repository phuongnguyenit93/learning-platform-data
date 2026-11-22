# Bảo toàn ngữ nghĩa

## 1. Bảo toàn ngữ nghĩa là gì?

Trong quá trình biến đổi một ngôn ngữ chuyên biệt miền (Domain-Specific Language — DSL), compiler hoặc công cụ có thể thay đổi cách biểu diễn chương trình: chuẩn hóa cú pháp, xây dựng AST, chuyển sang IR, tối ưu biểu thức hoặc sinh mã cho một ngôn ngữ đích. **Bảo toàn ngữ nghĩa (semantics preservation)** là yêu cầu rằng chương trình sau biến đổi vẫn giữ ý nghĩa và hành vi được quy định của chương trình ban đầu trong phạm vi điều kiện đã xác định.

Ví dụ, DSL có biểu thức:

~~~text
total = (price * quantity) + shipping
~~~

Một bước chuẩn hóa có thể bỏ cặp ngoặc không cần thiết:

~~~text
total = price * quantity + shipping
~~~

Nếu grammar và precedence của DSL xác định hai biểu thức có cùng cách nhóm, kết quả và hành vi, biến đổi này bảo toàn ngữ nghĩa.

Ngược lại, đổi:

~~~text
total = price * (quantity + shipping)
~~~

không phải là một thay đổi trình bày đơn thuần. Nó thay đổi cấu trúc tính toán và thường tạo kết quả khác.

Bảo toàn ngữ nghĩa không chỉ là giữ nguyên giá trị cuối cùng trong một ví dụ. Tùy DSL, ngữ nghĩa còn bao gồm:

- Giá trị và kiểu của biểu thức.
- Thứ tự đánh giá.
- Thay đổi trạng thái.
- Tác dụng phụ như ghi dữ liệu hoặc gửi thông báo.
- Ngoại lệ và cách lỗi được truyền.
- Quyền truy cập và các ràng buộc bảo mật.
- Hành vi thời gian, tiền tệ, đơn vị và làm tròn.
- Thứ tự sự kiện hoặc kết quả quan sát được của workflow.

Một phép biến đổi chỉ đúng khi nó giữ các khía cạnh quan sát được mà hợp đồng DSL yêu cầu.

## 2. Vì sao bảo toàn ngữ nghĩa quan trọng?

Biến đổi ngôn ngữ thường nhằm làm chương trình dễ đọc, dễ phân tích hoặc chạy hiệu quả hơn. Nếu thay đổi làm mất ý nghĩa, người dùng có thể nhận kết quả sai dù mã sinh ra vẫn hợp lệ về cú pháp.

Ví dụ, một DSL tính phí:

~~~text
fee = amount * rate
~~~

Generator có thể chuyển biểu thức sang Java, SQL hoặc một IR. Nếu một target làm tròn ở từng phép nhân trong khi DSL quy định chỉ làm tròn sau khi tính tổng, kết quả có thể khác. Cả hai chương trình đều chạy thành công nhưng không còn tương đương.

Bảo toàn ngữ nghĩa giúp:

- Tối ưu hóa không làm thay đổi kết quả.
- Chuyển DSL sang target language mà không đổi quy tắc nghiệp vụ.
- Chuẩn hóa AST mà không làm mất thông tin cần thiết.
- Thay đổi cách lưu trữ hoặc biểu diễn mà giữ hành vi.
- Tái cấu trúc chương trình an toàn.
- So sánh kết quả giữa các backend.
- Tạo cơ sở để kiểm thử và chứng minh tính đúng của compiler.

Trong DSL nghiệp vụ, sai lệch nhỏ có thể ảnh hưởng đến tiền, quyền truy cập, quy trình phê duyệt hoặc dữ liệu được lưu. Vì vậy, cần xác định rõ điều gì được xem là hành vi quan sát được.

## 3. Ngữ nghĩa của chương trình và hành vi quan sát được

Để nói hai chương trình tương đương, trước hết cần định nghĩa ý nghĩa của chúng.

Một chương trình có thể được hiểu thông qua:

- Kết quả trả về.
- Trạng thái sau khi thực thi.
- Chuỗi tác dụng phụ.
- Ngoại lệ hoặc lỗi.
- Tương tác với môi trường.
- Thời gian hoặc thứ tự sự kiện nếu chúng thuộc hợp đồng.

### 3.1 Giá trị trả về chưa đủ

Hai chương trình có thể trả về cùng một số nhưng tạo tác động phụ khác nhau.

~~~text
original:
  log("start")
  return calculate()

transformed:
  return calculate()
~~~

Nếu log là một hành vi quan sát được, hai chương trình không tương đương dù giá trị trả về giống nhau.

### 3.2 Trạng thái sau thực thi

Xét:

~~~text
balance = balance - amount
~~~

Một biến đổi có thể tính giá trị mới bằng một biểu thức khác. Để bảo toàn ngữ nghĩa, cần giữ trạng thái balance sau thực thi và các invariant liên quan.

### 3.3 Chuỗi tác dụng phụ

Hai hành động:

~~~text
reserve_inventory()
charge_payment()
~~~

có thể không hoán đổi được. Nếu reserve thất bại, việc charge trước có thể tạo ra trạng thái không mong muốn. Một biến đổi đổi thứ tự có thể thay đổi hành vi ngay cả khi cả hai hành động đều được gọi.

### 3.4 Lỗi và ngoại lệ

Nếu chương trình ban đầu phát sinh DivisionByZero nhưng chương trình biến đổi trả về 0, hành vi đã thay đổi. Lỗi là một phần của ngữ nghĩa nếu DSL định nghĩa cách quan sát hoặc xử lý lỗi.

### 3.5 Môi trường

Chương trình thường chạy trong một environment gồm input, cấu hình, thời gian, trạng thái bên ngoài và dịch vụ. So sánh hai chương trình cần dùng cùng môi trường hoặc xác định rõ quan hệ giữa các môi trường.

## 4. Mô hình hình thức để mô tả ngữ nghĩa

Một cách khái quát là xem chương trình P được đánh giá trong môi trường E và trạng thái S để tạo ra kết quả, trạng thái mới và các hiệu ứng:

\[
\operatorname{Eval}(P, E, S) = (R, S', Trace)
\]

Trong đó:

- P là chương trình hoặc biểu thức.
- E là environment chứa binding và cấu hình.
- S là trạng thái ban đầu.
- R là kết quả hoặc lỗi.
- S' là trạng thái sau khi thực thi.
- Trace là chuỗi sự kiện hoặc tác dụng phụ có thể quan sát.

Một phép biến đổi T bảo toàn ngữ nghĩa nếu chương trình P và T(P) tạo hành vi tương đương trong mọi môi trường và trạng thái thuộc phạm vi áp dụng.

Ký hiệu minh họa:

\[
P \simeq T(P)
\]

Ký hiệu này chỉ có ý nghĩa sau khi đã định nghĩa quan hệ tương đương. Có DSL chỉ quan tâm giá trị cuối cùng; DSL khác phải quan tâm cả trace, lỗi và trạng thái.

### 4.1 Big-step semantics

Big-step semantics mô tả chương trình từ đầu đến kết quả cuối:

\[
\langle e, \sigma \rangle \Downarrow v
\]

Có thể đọc là biểu thức e trong trạng thái σ đánh giá thành giá trị v.

Nếu biểu thức có tác dụng phụ, mô hình có thể mở rộng:

\[
\langle e, \sigma \rangle \Downarrow (v, \sigma')
\]

Phép biến đổi cần giữ quan hệ giữa kết quả và trạng thái mới.

### 4.2 Small-step semantics

Small-step semantics mô tả từng bước chuyển:

\[
e \rightarrow e'
\]

Nó hữu ích khi thứ tự đánh giá, trạng thái trung gian, ngoại lệ hoặc vòng lặp có ý nghĩa.

Ví dụ:

~~~text
(1 + 2) * 3
    -> 3 * 3
    -> 9
~~~

Một biến đổi có thể tạo ra chuỗi bước khác nhưng vẫn kết thúc ở hành vi tương đương. Khi đó, không cần từng bước giống hệt nhau; cần chứng minh các bước mô phỏng được nhau theo quan hệ đã chọn.

### 4.3 Operational và denotational view

Operational semantics tập trung vào cách chương trình thực thi. Denotational semantics ánh xạ chương trình sang một đối tượng toán học biểu diễn ý nghĩa.

Hai cách nhìn hỗ trợ các mục đích khác nhau:

- Operational semantics hữu ích khi kiểm tra thứ tự, trạng thái và hiệu ứng.
- Denotational semantics hữu ích khi chứng minh hai biểu thức có cùng ý nghĩa trừu tượng.

Không nhất thiết phải dùng ký hiệu hình thức cho mọi phép biến đổi. Tuy nhiên, cần có một mô hình ngữ nghĩa đủ rõ để xác định điều kiện đúng.

## 5. Các mức độ tương đương ngữ nghĩa

Từ "tương đương" có thể mang nhiều nghĩa.

### 5.1 Tương đương giá trị

Hai biểu thức tạo cùng giá trị trong một tập input:

~~~text
2 * 3
3 + 3
~~~

Nếu miền số học và kiểu dữ liệu xác định phép nhân, cộng như số nguyên không tràn, hai biểu thức có cùng giá trị 6.

### 5.2 Tương đương trạng thái

Hai chương trình tạo cùng trạng thái quan sát được sau khi chạy. Trạng thái nội bộ có thể khác nếu không thể quan sát từ bên ngoài.

### 5.3 Tương đương quan sát

Hai chương trình được xem là tương đương nếu mọi quan sát mà môi trường được phép thực hiện đều giống nhau. Quan sát có thể bao gồm output, exception, event, file được tạo hoặc trạng thái tài nguyên.

### 5.4 Tương đương theo ngữ cảnh

Hai biểu thức tương đương theo ngữ cảnh nếu thay biểu thức này bằng biểu thức kia trong mọi chương trình/ngữ cảnh hợp lệ không làm thay đổi hành vi quan sát được.

Đây là yêu cầu mạnh hơn việc hai biểu thức cho cùng kết quả trong một test cụ thể.

### 5.5 Refinement

Một phép biến đổi đôi khi không giữ hành vi chính xác mà thu hẹp tập hành vi có thể xảy ra. Đây có thể là refinement nếu đặc tả cho phép.

Ví dụ, một chương trình trước đó có thể trả về một trong nhiều kết quả không xác định thứ tự; chương trình mới chọn một thứ tự cố định. Điều này chỉ được xem là hợp lệ nếu hợp đồng DSL cho phép implementation chọn thứ tự đó.

Không nên gọi refinement là equivalence nếu người dùng kỳ vọng hành vi chính xác được giữ nguyên.

## 6. Điều kiện và tiền đề của một phép biến đổi

Nhiều phép biến đổi chỉ đúng dưới một số giả định.

Ví dụ:

~~~text
x + 0  ->  x
~~~

Phép biến đổi này có vẻ hiển nhiên, nhưng cần biết:

- x có phải kiểu số không?
- Phép cộng có tác dụng phụ không?
- Có giá trị NaN hoặc signed zero không?
- Có overflow hoặc trap không?
- Kiểu số có quy tắc làm tròn đặc biệt không?

Một phép biến đổi nên có **precondition** (tiền điều kiện) mô tả khi nào nó được phép áp dụng.

Ví dụ:

~~~text
Transformation: x + 0 -> x
Preconditions:
  - x has an integer type with the specified arithmetic semantics
  - evaluating x has no duplicated or removed side effect
  - no observable distinction is made by the target arithmetic model
~~~

Đây là mô tả khái quát. Tiền điều kiện thực tế phụ thuộc kiểu và semantics của DSL.

### 6.1 Hoare-style reasoning

Có thể mô tả phép biến đổi bằng precondition P và postcondition Q:

\[
\{P\}\ T\ \{Q\}
\]

Trong đó P nêu giả định trước khi biến đổi, T là transformation và Q nêu tính chất cần được giữ sau biến đổi.

### 6.2 Không áp dụng khi thiếu thông tin

Nếu compiler không chứng minh được precondition, lựa chọn an toàn thường là giữ chương trình gốc. Không nên giả định dữ liệu luôn hợp lệ chỉ vì một số ví dụ chạy đúng.

## 7. Bảo toàn cấu trúc điều khiển và thứ tự đánh giá

Thứ tự đánh giá là một phần quan trọng của semantics.

Ví dụ:

~~~text
check_balance(account) and reserve_funds(account)
~~~

Nếu AND dùng short-circuit, reserve_funds chỉ được gọi khi check_balance trả true. Biến đổi thành:

~~~text
reserve_funds(account) and check_balance(account)
~~~

có thể làm thay đổi tác dụng phụ hoặc trạng thái.

### 7.1 Left-to-right evaluation

Nếu DSL quy định đánh giá từ trái sang phải, compiler phải giữ thứ tự đó khi biểu thức có thể tạo tác dụng phụ hoặc lỗi.

Ví dụ:

~~~text
f() + g()
~~~

Nếu f và g thay đổi trạng thái, đổi thứ tự gọi có thể làm thay đổi kết quả.

### 7.2 Short-circuit

Với AND:

~~~text
false and expensive_check()
~~~

Nếu DSL quy định short-circuit, expensive_check không được gọi. Thay bằng một hàm kết hợp luôn đánh giá cả hai vế có thể thay đổi hành vi.

Với OR:

~~~text
true or fallback()
~~~

fallback không được gọi nếu OR short-circuit.

### 7.3 Conditional expression

~~~text
if condition then a() else b()
~~~

Chỉ một nhánh được thực thi. Biến đổi thành:

~~~text
a() + b()
~~~

không bảo toàn ngữ nghĩa nếu cả hai hàm có tác dụng phụ hoặc một trong hai phát sinh lỗi.

### 7.4 Reordering

Đổi thứ tự hai biểu thức chỉ an toàn khi có thể chứng minh chúng độc lập, không có hiệu ứng quan sát được ảnh hưởng lẫn nhau và không có khác biệt về lỗi hoặc đồng thời.

## 8. Tác dụng phụ và trạng thái

Một biểu thức được gọi là pure nếu kết quả chỉ phụ thuộc vào đầu vào và việc đánh giá không thay đổi trạng thái bên ngoài.

Ví dụ có thể thuần:

~~~text
subtotal * tax_rate
~~~

Ví dụ có tác dụng phụ:

~~~text
account.balance = account.balance - amount
send_email(customer.email)
write_audit_log(event)
~~~

### 8.1 Không xóa lời gọi có tác dụng phụ

Biến đổi:

~~~text
log_access()
return 0
~~~

thành:

~~~text
return 0
~~~

chỉ hợp lệ nếu log_access không có tác dụng phụ quan sát được hoặc tác dụng đó được đặc tả là không quan trọng.

### 8.2 Không nhân đôi lời gọi

Từ:

~~~text
let x = read_next_value()
return x + x
~~~

thành:

~~~text
return read_next_value() + read_next_value()
~~~

có thể đọc hai giá trị khác nhau. Một biểu thức có tác dụng phụ không thể được nhân đôi tùy tiện.

### 8.3 Alias và shared state

Hai biến có thể tham chiếu cùng một đối tượng. Nếu compiler giả định chúng độc lập rồi đổi thứ tự ghi/đọc, kết quả có thể sai.

Phân tích alias giúp xác định hai biểu thức có thể truy cập cùng vùng nhớ hay không. Nếu không chứng minh được chúng độc lập, cần giữ thứ tự an toàn.

### 8.4 Volatile và concurrent state

Trong môi trường có luồng đồng thời hoặc biến volatile, việc đọc lặp lại hoặc loại bỏ một lần đọc có thể thay đổi hành vi quan sát được. Semantics của DSL và target phải xác định memory model và mức bảo đảm cần giữ.

## 9. Ngoại lệ, lỗi và kết quả thất bại

Một phép biến đổi không được bỏ qua lỗi có thể quan sát.

Ví dụ:

~~~text
10 / x
~~~

Nếu x bằng 0, biểu thức có thể phát sinh lỗi. Biến đổi thành:

~~~text
if x == 0 then 0 else 10 / x
~~~

đã thay đổi hành vi lỗi thành một giá trị bình thường.

### 9.1 Exception order

Nếu hai biểu thức đều có thể lỗi, đổi thứ tự có thể thay đổi exception nào được quan sát trước.

### 9.2 Error recovery

Một compiler có thể tiếp tục phân tích sau lỗi cú pháp để báo thêm diagnostic. Tuy nhiên, không nên sinh mã thực thi từ một phần chương trình chưa có semantics đáng tin cậy, trừ khi chế độ đó được thiết kế rõ.

### 9.3 Lỗi nghiệp vụ và lỗi hạ tầng

Không đủ điều kiện khuyến mãi là một kết quả nghiệp vụ. Không kết nối được database là lỗi hạ tầng. Biến đổi không nên gộp hai trường hợp thành false nếu hợp đồng DSL phân biệt chúng.

## 10. Số học, overflow và số thực

Các phép biến đổi đại số chỉ đúng trong một mô hình số cụ thể.

### 10.1 Số nguyên có giới hạn

Với số nguyên toán học không giới hạn:

\[
(a+b)-b = a
\]

Nhưng với số nguyên có giới hạn và overflow, kết quả phụ thuộc chính sách:

- Wraparound.
- Trap hoặc exception.
- Saturating arithmetic.
- Undefined hoặc implementation-defined behavior.

Ví dụ, nếu phép cộng overflow theo wraparound, một số phép biến đổi vẫn có thể đúng trong arithmetic modulo. Nếu overflow phát sinh exception, đổi thứ tự hoặc loại bỏ phép toán có thể làm mất exception.

### 10.2 Số thực dấu phẩy động

Số thực IEEE 754 có NaN, positive/negative infinity và signed zero. Các phép biến đổi đại số quen thuộc có thể không còn đúng.

Ví dụ:

~~~text
x * 0 -> 0
~~~

Nếu x là NaN, x * 0 thường vẫn là NaN chứ không phải 0. Nếu x là infinity, kết quả cũng có thể là NaN.

Ví dụ:

~~~text
x + 0 -> x
~~~

Với signed zero, NaN payload hoặc rounding mode, phép biến đổi có thể làm thay đổi kết quả quan sát được trong một số mô hình.

### 10.3 Reassociation

~~~text
(a + b) + c -> a + (b + c)
~~~

Với số thực dấu phẩy động, phép cộng không luôn kết hợp do làm tròn. Hai cách nhóm có thể tạo kết quả khác nhau.

### 10.4 Decimal và tiền tệ

DSL tài chính có thể dùng decimal arithmetic với precision và rounding mode cụ thể. Không nên thay phép tính decimal bằng double chỉ vì target thuận tiện hơn.

Cần giữ:

- Precision.
- Scale.
- Rounding mode.
- Thời điểm làm tròn.
- Currency và đơn vị.
- Quy tắc overflow.

### 10.5 Phép biến đổi có điều kiện

Nếu DSL có chế độ fast-math hoặc approximate arithmetic, một số phép biến đổi có thể được cho phép theo hợp đồng. Cần làm rõ đây là thay đổi về độ chính xác được chấp nhận, không phải tương đương chính xác.

## 11. Null, unknown và giá trị thiếu

Nếu DSL có kiểu nullable hoặc logic ba giá trị, phép biến đổi Boolean phải giữ semantics tương ứng.

Ví dụ, trong logic ba giá trị:

~~~text
unknown and false = false
unknown and true  = unknown
~~~

Không thể tùy tiện áp dụng các luật Boolean hai giá trị nếu kết quả có thể là unknown.

### 11.1 Null coalescing

~~~text
value ?? fallback()
~~~

Thông thường fallback chỉ được đánh giá khi value là null. Biến đổi thành:

~~~text
if value is null then fallback() else value
~~~

có thể bảo toàn nếu kiểm tra null và cách đánh giá value giống nhau, không có thay đổi giữa hai lần đọc.

### 11.2 Missing khác null

Nếu DSL phân biệt field bị thiếu với field có giá trị null, biến đổi dữ liệu phải giữ được presence information. Chuyển cả hai thành một giá trị null duy nhất có thể làm mất ý nghĩa của default hoặc lệnh cập nhật.

## 12. Thời gian, tiền tệ và kiểu miền

Trong DSL nghiệp vụ, các kiểu miền thường có quy tắc riêng mà phép biến đổi tổng quát không được bỏ qua.

### 12.1 Thời gian và timezone

~~~text
start_at + 1 day
~~~

không nhất thiết tương đương:

~~~text
start_at + 24 hours
~~~

Khi có timezone và daylight saving time, một ngày lịch có thể dài hơn hoặc ngắn hơn 24 giờ. Compiler cần giữ đúng kiểu và semantics của phép cộng thời gian.

### 12.2 Tiền tệ

~~~text
100 USD + 100 EUR
~~~

có thể không hợp lệ nếu không có tỷ giá hoặc chính sách quy đổi. Biến đổi không được loại bỏ đơn vị hoặc coi mọi số tiền là cùng một kiểu số.

### 12.3 Đơn vị đo

~~~text
distance = speed * duration
~~~

Phân tích đơn vị có thể chứng minh kết quả có kiểu Length. Nếu generator bỏ metadata đơn vị quá sớm, các bước sau có thể thực hiện phép toán sai.

### 12.4 Domain invariant

Một biến đổi có thể giữ giá trị số nhưng vi phạm invariant của miền. Ví dụ, đổi thứ tự cập nhật startDate và endDate có thể tạo trạng thái trung gian không hợp lệ nếu hệ thống quan sát từng bước.

## 13. Bảo toàn binding và phạm vi tên

Một phép biến đổi AST phải giữ các tham chiếu đến đúng symbol.

Ví dụ:

~~~text
let rate = 5

scope {
  let rate = 10
  print(rate)
}
~~~

Tên rate bên trong scope trỏ đến biến nội bộ. Nếu một transformation chỉ thay chuỗi văn bản hoặc di chuyển khai báo mà không cập nhật binding, print có thể trỏ sang biến bên ngoài.

### 13.1 Alpha-renaming

Đổi tên biến cục bộ có thể bảo toàn ngữ nghĩa nếu:

- Chỉ đổi đúng symbol.
- Cập nhật mọi reference đã resolve đến symbol đó.
- Không tạo capture hoặc shadowing ngoài ý muốn.
- Không thay đổi tên công khai nếu API phụ thuộc vào nó.

Ví dụ:

~~~text
let x = 10
print(x)
~~~

có thể đổi thành:

~~~text
let temporary = 10
print(temporary)
~~~

### 13.2 Variable capture

Khi di chuyển biểu thức vào một scope khác, tên tự do trong biểu thức có thể bị bắt bởi một khai báo cùng tên.

Ví dụ:

~~~text
let x = 1
function f() {
  let y = x + 1
}
~~~

Nếu inline hoặc di chuyển y vào scope có một x khác, kết quả có thể thay đổi. Transformation cần dùng symbol identity và alpha-renaming để tránh capture.

### 13.3 Closure

Lambda hoặc closure có thể capture biến từ scope bên ngoài. Khi chuyển đổi closure thành class hoặc callback ở target, cần giữ đúng biến được capture và thời điểm đọc giá trị.

## 14. Các phép biến đổi thường gặp và điều kiện đúng

### 14.1 Constant folding

Constant folding tính trước biểu thức chỉ phụ thuộc vào hằng số:

~~~text
2 * 3 + 4
~~~

thành:

~~~text
10
~~~

Chỉ an toàn nếu:

- Các toán tử có semantics xác định tại compile time.
- Kiểu và overflow được xử lý giống runtime.
- Không có tác dụng phụ.
- Không phụ thuộc clock, random hoặc môi trường.
- Diagnostic hoặc source mapping vẫn có thể truy nguyên nếu cần.

### 14.2 Constant propagation

~~~text
let limit = 10
if count > limit
  reject()
~~~

có thể thay limit bằng 10 nếu compiler chứng minh binding không bị thay đổi và giá trị thực sự là hằng.

### 14.3 Dead code elimination

~~~text
if false
  send_notification()
~~~

Có thể loại bỏ nhánh nếu điều kiện chắc chắn false và việc không thực thi nhánh không làm mất hành vi như compile-time diagnostic hoặc khai báo có hiệu lực.

### 14.4 Common subexpression elimination

~~~text
let a = x * y
let b = x * y
~~~

có thể tính x * y một lần nếu:

- x và y không thay đổi giữa hai lần.
- Đánh giá không có tác dụng phụ.
- Không phát sinh lỗi khác nhau do trạng thái.
- Không có concurrency hoặc volatile semantics làm thay đổi kết quả.

### 14.5 Inline function

~~~text
result = double(value)
~~~

thành:

~~~text
result = value * 2
~~~

có thể bảo toàn nếu hàm thực sự tương đương biểu thức đó, không có tác dụng phụ, exception, khác biệt về overload hoặc đánh giá đối số.

### 14.6 Loop transformation

Loop unrolling hoặc loop fusion có thể cải thiện hiệu năng nhưng cần giữ:

- Số lần lặp.
- Thứ tự phần tử.
- Tác dụng phụ.
- Điều kiện break/continue.
- Exception order.
- Phụ thuộc dữ liệu giữa các vòng.

### 14.7 Boolean simplification

~~~text
condition and true -> condition
~~~

có thể đúng với Boolean hai giá trị và semantics toán tử phù hợp. Nếu biểu thức có nullable Boolean hoặc logic ba giá trị, cần kiểm tra bảng chân trị cụ thể.

## 15. Biến đổi từ DSL sang IR và target language

Một compiler thường có nhiều biểu diễn:

~~~text
DSL source
    |
    v
Parse tree
    |
    v
AST
    |
    v
Typed AST
    |
    v
Intermediate Representation (IR)
    |
    v
Target code
~~~

Mỗi bước cần bảo toàn phần ngữ nghĩa mà bước sau phải sử dụng.

### 15.1 Parse tree sang AST

AST có thể bỏ dấu ngoặc hoặc token không cần thiết, nhưng phải giữ precedence, associativity, literal, binding và source location cần cho các bước sau.

### 15.2 AST sang typed AST

Gắn kiểu và symbol reference không nên thay đổi ý nghĩa chương trình. Nếu một biểu thức không thể xác định kiểu, compiler cần báo lỗi thay vì tự chọn một kiểu tùy tiện.

### 15.3 Typed AST sang IR

IR có thể hạ các cấu trúc DSL cấp cao thành phép toán thấp hơn. Ví dụ, một rule giảm giá có thể được biểu diễn thành các phép so sánh, nhánh và phép tính tiền. Cần giữ:

- Điều kiện kích hoạt.
- Đơn vị và kiểu.
- Thứ tự kiểm tra.
- Kết quả từ chối hoặc lỗi.
- Tác dụng phụ và transaction boundary.

### 15.4 IR sang target

Target language có thể có semantics khác DSL. Generator phải mô phỏng semantics DSL bằng cấu trúc target tương đương, không chỉ dịch từ khóa theo mặt chữ.

Ví dụ, nếu DSL dùng decimal chính xác và target mặc định dùng binary floating point, generator cần chọn kiểu hoặc thư viện thích hợp.

## 16. Quan hệ mô phỏng giữa hai biểu diễn

Khi source và target có cấu trúc khác nhau, không thể yêu cầu từng bước thực thi giống nhau. Có thể định nghĩa một quan hệ mô phỏng (simulation relation) giữa trạng thái source và target.

Ký hiệu:

\[
S \mathrel{\mathcal{R}} T
\]

nghĩa là trạng thái source S tương ứng với trạng thái target T.

Một lập luận bảo toàn có thể gồm:

1. Trạng thái ban đầu của source và target liên hệ với nhau.
2. Mỗi bước source được mô phỏng bởi một hoặc nhiều bước target.
3. Quan hệ giữa trạng thái vẫn được giữ sau các bước.
4. Kết quả cuối và các hành vi quan sát được tương ứng.

### 16.1 Forward simulation

Forward simulation thường chứng minh mọi bước của source có thể được mô phỏng bởi target. Đây là cách lập luận hữu ích khi chuyển từ DSL sang một target cụ thể.

### 16.2 Bisimulation

Bisimulation yêu cầu hai hệ thống mô phỏng lẫn nhau theo một quan hệ. Đây là yêu cầu mạnh hơn và có thể phù hợp khi muốn chứng minh hai semantics tương đương về hành vi trong cả hai chiều.

### 16.3 Không cần mọi compiler dùng chứng minh hình thức đầy đủ

Các khái niệm này giúp định hình điều cần giữ. Trong dự án thực tế, có thể kết hợp đặc tả quy tắc, unit test, property-based test, differential test và translation validation thay vì chứng minh toàn bộ compiler bằng logic hình thức.

## 17. Bảo toàn semantics trong tối ưu hóa

Optimizer áp dụng chuỗi transformation lên IR hoặc AST. Mỗi pass cần có hợp đồng rõ:

- Input representation.
- Output representation.
- Preconditions.
- Invariants được giả định.
- Phần semantics phải giữ.
- Diagnostic hoặc metadata được cập nhật.

### 17.1 Pass ordering

Hai phép biến đổi có thể không giao hoán. Áp dụng A rồi B có thể khác B rồi A, nhất là khi một pass tạo hoặc xóa cấu trúc mà pass kia sử dụng.

Optimizer nên định nghĩa thứ tự pass hoặc dùng dependency giữa pass.

### 17.2 Idempotence

Một pass chuẩn hóa thường nên có tính idempotent:

\[
T(T(P)) = T(P)
\]

Điều này nghĩa chạy lại pass không tiếp tục thay đổi chương trình. Không phải mọi optimization đều idempotent, nhưng tính chất này hữu ích cho normalization và formatter.

### 17.3 Termination

Nếu các pass liên tục tạo cấu trúc mà pass khác lại biến đổi ngược, pipeline có thể không hội tụ. Cần có chiến lược:

- Một thứ tự pass cố định.
- Giới hạn số vòng.
- Measure giảm theo mỗi lần biến đổi.
- Phát hiện trạng thái IR lặp.

### 17.4 Không tối ưu qua ranh giới semantics

Một optimizer không nên giả định mọi lời gọi hàm là pure hoặc mọi biến là bất biến. Cần effect analysis, alias analysis hoặc annotation đáng tin cậy để xác định điều kiện.

## 18. Bảo toàn semantics trong DSL nghiệp vụ

DSL nghiệp vụ thường có semantics vượt ra ngoài phép toán thông thường.

### 18.1 Rule và policy

~~~text
when customer.tier == GOLD
 and order.total >= 2000000 VND
then discount 10 percent
~~~

Biến đổi có thể gom điều kiện hoặc tạo IR, nhưng phải giữ:

- Hai điều kiện đều cần đúng.
- Đơn vị VND.
- Cơ sở tính giảm giá.
- Thứ tự hoặc short-circuit nếu có ý nghĩa.
- Quy tắc khi customer hoặc order thiếu dữ liệu.

### 18.2 Workflow

~~~text
reserve inventory
charge payment
confirm order
~~~

Không được đổi thứ tự chỉ vì target có thể chạy song song. Các bước có phụ thuộc trạng thái và failure compensation.

### 18.3 Authorization

Một phép biến đổi không được loại bỏ kiểm tra quyền hoặc đổi thứ tự khiến thao tác xảy ra trước authorization.

### 18.4 Audit

Nếu DSL yêu cầu ghi audit event, biến đổi loại bỏ hoặc gộp các event có thể vi phạm contract ngay cả khi kết quả nghiệp vụ cuối giống nhau.

### 18.5 Currency, rounding và timezone

Giữ nguyên kiểu miền, precision, rounding mode, currency conversion và quy tắc thời gian. Đừng hạ tất cả thành số hoặc timestamp không có metadata nếu điều đó làm mất semantics.

## 19. Bảo toàn semantics và bảo toàn thông tin nguồn

Hai yêu cầu này liên quan nhưng không giống nhau.

**Bảo toàn ngữ nghĩa** tập trung vào hành vi chương trình.

**Bảo toàn thông tin nguồn** tập trung vào khả năng giữ comment, formatting, tên gốc, source range và cấu trúc để phục vụ IDE, diagnostic hoặc round-trip.

Ví dụ, hai biểu thức có thể tương đương về runtime nhưng khác comment:

~~~text
// Important business rule
discount = amount * 0.1
~~~

Nếu AST loại bỏ comment, semantics runtime có thể vẫn giữ nguyên, nhưng công cụ format hoặc refactor không thể phục hồi comment.

Một pipeline DSL thường cần giữ cả hai loại thông tin:

- Semantic model cho compiler.
- Trivia/source map/metadata cho tooling.

Không nên coi việc giữ comment là điều kiện bắt buộc của semantic equivalence nếu hợp đồng không yêu cầu, nhưng cần bảo toàn nếu công cụ có yêu cầu round-trip hoặc chỉnh sửa source.

## 20. Kiểm chứng phép biến đổi

Có nhiều mức kiểm chứng, từ test ví dụ đến chứng minh hình thức.

### 20.1 Unit test cho từng transformation

Với phép constant folding:

- Input AST trước biến đổi.
- Output AST sau biến đổi.
- Kết quả đánh giá của hai cây.
- Các trường hợp biên như overflow, division by zero và kiểu nullable.

Không chỉ kiểm tra output string; cần kiểm tra semantics theo mô hình của DSL.

### 20.2 Differential testing

Chạy chương trình gốc và chương trình đã biến đổi trên cùng input, cùng environment và trạng thái. So sánh:

- Result.
- State.
- Exception.
- Trace.

Ví dụ:

~~~text
original = evaluate(sourceProgram, context)
transformed = evaluate(transform(sourceProgram), context)

assert equivalent(original, transformed)
~~~

Hàm equivalent phải phản ánh đúng contract. Nếu chỉ so sánh result mà bỏ qua side effects, test có thể bỏ sót lỗi.

### 20.3 Property-based testing

Sinh nhiều input theo miền giá trị và kiểm tra một tính chất:

~~~text
for all valid x:
  evaluate(x + 0) == evaluate(x)
~~~

Tính chất cần được giới hạn theo kiểu và semantics. Với floating point hoặc nullable values, không nên áp dụng luật số học tổng quát mà không xét các trường hợp đặc biệt.

### 20.4 Metamorphic testing

Metamorphic testing dùng quan hệ giữa các input/output khi không dễ biết kết quả đúng tuyệt đối.

Ví dụ, nếu normalization được định nghĩa idempotent:

~~~text
normalize(normalize(program)) == normalize(program)
~~~

Hoặc hai backend cần tương đương:

~~~text
runJava(generateJava(program))
    is equivalent to
runPython(generatePython(program))
~~~

### 20.5 Translation validation

Thay vì chứng minh toàn bộ compiler, translation validation kiểm tra một lần biến đổi cụ thể hoặc output cụ thể có giữ tính chất mong muốn hay không.

Có thể so sánh IR trước/sau, kiểm tra invariant hoặc dùng một validator độc lập. Cách này đặc biệt hữu ích khi optimizer phức tạp hoặc có nhiều pass.

### 20.6 Golden test

Golden test so sánh mã sinh ra với file kết quả mong đợi. Nó hữu ích để phát hiện thay đổi output ngoài ý muốn, nhưng không chứng minh semantics. Hai file khác nhau có thể tương đương; hai file giống định dạng mong đợi vẫn có thể chứa bug runtime.

## 21. Bằng chứng và proof obligation cho mỗi transformation

Một transformation nên có mô tả rõ về điều cần chứng minh.

Mẫu tài liệu:

~~~text
Rule ID: fold-integer-add
Input: Add(IntegerLiteral(a), IntegerLiteral(b))
Output: IntegerLiteral(a + b)

Preconditions:
  - Both operands are compile-time constants
  - The DSL integer overflow policy is known
  - The operation does not raise an observable exception

Preserved properties:
  - Result value
  - Result type
  - Observable diagnostics required by the language

Validation:
  - Boundary tests
  - Differential evaluation
  - Overflow cases
~~~

### 21.1 Proof obligation

Một proof obligation là mệnh đề cần được chứng minh để transformation được xem là hợp lệ. Ví dụ:

- Giá trị biểu thức trước và sau bằng nhau.
- Mọi tác dụng phụ được giữ đúng số lần và thứ tự.
- Binding của mọi identifier không đổi.
- Không tạo thêm exception hoặc bỏ mất exception.
- Kiểu đầu ra vẫn tương thích.

### 21.2 Rule không chứng minh được

Nếu một transformation không đáp ứng tiền điều kiện, optimizer nên bỏ qua nó. Việc không tối ưu thường an toàn hơn việc áp dụng một phép biến đổi dựa trên giả định không có căn cứ.

### 21.3 Ghi nhận giả định

Nếu semantics phụ thuộc vào cấu hình như overflow mode hoặc fast-math, cần ghi nhận cấu hình đó trong compilation context hoặc IR. Không nên để pass tự suy đoán.

## 22. Sai lệch semantics giữa các target

Một DSL có thể sinh Java, Python, JavaScript hoặc SQL. Các target có thể khác nhau về:

- Kiểu số và overflow.
- Null và missing.
- Đánh giá Boolean.
- Thứ tự thực thi.
- Exception.
- Date/time.
- Unicode và string comparison.
- Transaction và concurrency.

### 22.1 Không dịch theo từ khóa

Ví dụ, DSL có phép AND short-circuit. Nếu target backend dùng một phép toán luôn đánh giá cả hai toán hạng, generator cần tạo control flow tương đương thay vì dịch thành operator trực tiếp.

### 22.2 Runtime support library

Một backend có thể cần helper library để mô phỏng semantics DSL:

- Decimal arithmetic.
- Three-valued Boolean.
- Duration và timezone.
- Null/missing distinction.
- Error/result propagation.

Các helper này là một phần của translation strategy và cần được version hóa cùng runtime.

### 22.3 Target không biểu diễn được semantics

Nếu target không thể biểu diễn chính xác một hành vi DSL, có ba lựa chọn:

- Dùng runtime support hoặc lowering bổ sung.
- Giới hạn DSL feature ở backend đó.
- Báo lỗi không hỗ trợ thay vì sinh mã sai.

Không nên âm thầm thay đổi semantics để phù hợp target.

## 23. Những sai lầm thường gặp

### Chỉ so sánh giá trị cuối cùng

Hai chương trình có thể trả cùng giá trị nhưng khác tác dụng phụ, trạng thái hoặc exception.

**Cách khắc phục:** xác định tập hành vi quan sát được và so sánh đủ các thành phần.

### Áp dụng luật đại số không xét kiểu

Luật đúng với số nguyên toán học có thể sai với floating point, overflow hoặc decimal.

**Cách khắc phục:** gắn transformation với kiểu và arithmetic mode cụ thể.

### Bỏ qua thứ tự đánh giá

Đổi thứ tự biểu thức có tác dụng phụ có thể làm thay đổi trạng thái.

**Cách khắc phục:** dùng effect analysis và giữ thứ tự theo semantics.

### Giả định hàm là pure

Lời gọi hàm có thể ghi log, đọc clock, truy cập mạng hoặc thay đổi state.

**Cách khắc phục:** chỉ tối ưu khi có bằng chứng purity hoặc effect contract.

### Mất binding khi đổi tên hoặc di chuyển code

Thay tên bằng chuỗi có thể tạo variable capture hoặc đổi symbol được tham chiếu.

**Cách khắc phục:** thao tác trên symbol identity và cập nhật reference graph.

### Chỉ kiểm thử output source

Generated code có thể đúng hình thức nhưng sai hành vi.

**Cách khắc phục:** kết hợp golden test với differential, property-based và integration test.

### Tự giả định target tương đương

Java, Python, JavaScript và SQL có semantics khác nhau.

**Cách khắc phục:** định nghĩa semantics DSL độc lập và kiểm tra từng backend.

### Áp dụng transformation khi thiếu precondition

Một tối ưu hóa có thể đúng trong phần lớn trường hợp nhưng sai ở null, NaN hoặc overflow.

**Cách khắc phục:** kiểm tra precondition; nếu không chứng minh được thì giữ nguyên chương trình.

## 24. Quy trình thiết kế và kiểm chứng phép biến đổi

Khi thêm một transformation vào DSL compiler, có thể thực hiện:

1. **Xác định mục tiêu:** chuẩn hóa, tối ưu, lowering hay chuyển target.
2. **Định nghĩa semantics:** mô tả kết quả, state, effects, lỗi và quan sát.
3. **Xác định phạm vi tương đương:** value, state, trace hay contextual equivalence.
4. **Viết preconditions:** kiểu, constantness, purity, alias, overflow và cấu hình liên quan.
5. **Định nghĩa transformation:** input node, output node và source mapping.
6. **Nêu proof obligations:** các tính chất phải giữ.
7. **Cập nhật IR metadata:** giữ symbol binding, type, effect và source location cần thiết.
8. **Viết test:** ví dụ thường, biên, lỗi, side effect và target-specific cases.
9. **So sánh trước/sau:** dùng evaluator hoặc runtime tham chiếu khi có thể.
10. **Theo dõi regression:** kiểm tra nhiều backend và các lần compiler thay đổi.

Một transformation nên có thể bị từ chối khi điều kiện không rõ. Đây là hành vi bình thường của optimizer: chỉ áp dụng những thay đổi mà nó có đủ cơ sở.

## 25. Ví dụ tổng hợp: tối ưu biểu thức trong DSL tính giá

DSL:

~~~text
let subtotal = unit_price * quantity
let tax = subtotal * tax_rate
let total = subtotal + tax
return total
~~~

Giả sử:

- unit_price và subtotal có kiểu Money.
- quantity là Integer không âm.
- tax_rate là Decimal.
- Các phép tính dùng decimal arithmetic.
- Làm tròn chỉ thực hiện tại bước được đặc tả.
- Các biến local là immutable.

### 25.1 Constant propagation

Nếu tax_rate là hằng số 0.1, compiler có thể thay tham chiếu bằng literal 0.1 nếu binding bất biến và precision được giữ.

### 25.2 Inlining biểu thức

Có thể thay:

~~~text
let tax = subtotal * 0.1
~~~

bằng biểu thức tương đương, nhưng cần cân nhắc có cần giữ subtotal để tránh tính unit_price * quantity nhiều lần hay không.

### 25.3 Common subexpression

Nếu biểu thức subtotal được dùng ở nhiều nơi, compiler có thể tính một lần và tái sử dụng. Điều này hợp lệ nếu phép tính thuần và input không đổi.

### 25.4 Rounding

Không được chuyển:

~~~text
round(subtotal * tax_rate)
~~~

thành:

~~~text
round(subtotal) * round(tax_rate)
~~~

trừ khi đặc tả toán học và quy tắc làm tròn chứng minh hai biểu thức tương đương. Trong nghiệp vụ tiền tệ, làm tròn ở thời điểm khác nhau thường tạo kết quả khác.

### 25.5 Kiểm chứng

Chạy chương trình gốc và chương trình tối ưu trên cùng các input:

- Giá trị nhỏ.
- Số lượng bằng 0.
- Giá trị sát giới hạn.
- Decimal có nhiều chữ số thập phân.
- Giá trị có thể gây overflow theo policy.
- Trường hợp lỗi dữ liệu.

So sánh tổng tiền, currency, trạng thái và diagnostic theo contract. Nếu hai backend tạo kết quả khác nhau, cần xác định backend nào đang vi phạm semantics DSL.

## 26. Câu hỏi tự kiểm tra

1. Bảo toàn ngữ nghĩa có nghĩa gì trong biến đổi ngôn ngữ?
2. Vì sao kết quả trả về giống nhau chưa đủ để chứng minh hai chương trình tương đương?
3. Phân biệt value equivalence, observational equivalence và contextual equivalence.
4. Precondition của transformation dùng để làm gì?
5. Vì sao thứ tự đánh giá và short-circuit cần được giữ?
6. Side effect và aliasing ảnh hưởng optimization ra sao?
7. Vì sao các luật đại số có thể sai với floating point?
8. Null, unknown, currency và timezone có thể làm phép biến đổi sai như thế nào?
9. Alpha-renaming cần tránh variable capture ra sao?
10. Quan hệ simulation giúp chứng minh source và target tương ứng như thế nào?
11. Phân biệt constant folding, constant propagation và common subexpression elimination.
12. Differential testing và property-based testing kiểm chứng transformation ra sao?
13. Translation validation khác chứng minh toàn bộ compiler như thế nào?
14. Vì sao mỗi target backend cần kiểm tra semantics riêng?

Bảo toàn ngữ nghĩa là hợp đồng cốt lõi của mọi phép biến đổi DSL. Khi xác định rõ hành vi quan sát được, tiền điều kiện, tác dụng phụ, kiểu dữ liệu và proof obligations, compiler có thể chuẩn hóa, tối ưu và sinh mã mà vẫn giữ ý nghĩa mà người viết DSL đã mô tả.
