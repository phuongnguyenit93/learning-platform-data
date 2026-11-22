# Ký tự đại diện và biểu thức mẫu theo cú pháp công cụ trong pointcut AOP

## 1. Vì sao pointcut cần ký tự đại diện và biểu thức mẫu?

Trong **lập trình hướng khía cạnh (Aspect-Oriented Programming — AOP)**, một **pointcut** xác định những **join point** nào sẽ được chọn để áp dụng **advice**. Join point là điểm mà mô hình thực thi và cơ chế AOP cho phép can thiệp, chẳng hạn một lần gọi hoặc thực thi phương thức nếu công cụ hỗ trợ.

Nếu chỉ định từng phương thức bằng tên đầy đủ, pointcut có thể trở nên dài, lặp và khó duy trì. **Ký tự đại diện (wildcard)** và **biểu thức mẫu (pattern expression)** cho phép mô tả một tập các tên, kiểu, chữ ký hoặc vị trí chương trình bằng quy tắc tổng quát.

Ví dụ, một yêu cầu có thể được mô tả bằng lời:

> Ghi nhận thời gian cho tất cả phương thức công khai của các lớp dịch vụ trong một nhóm package, không phụ thuộc tên phương thức và số tham số.

Thay vì viết hàng chục biểu thức cho từng phương thức, một ngôn ngữ pointcut có thể cung cấp ký hiệu để mô tả tập tương ứng. Tuy nhiên, **không tồn tại một bộ ký tự đại diện và cú pháp pointcut thống nhất cho mọi giải pháp AOP**. Mỗi công cụ quyết định cú pháp, loại join point, cách khớp tên/kiểu, độ ưu tiên toán tử và cơ chế weaving của chính nó.

Bài này phân biệt **nguyên tắc chung** với **cú pháp cụ thể**, sau đó dùng **AspectJ** làm ví dụ cho một ngôn ngữ pointcut AOP có tài liệu chính thức. Các biểu thức AspectJ bên dưới chỉ có hiệu lực khi dùng công cụ và phạm vi weaving hỗ trợ ngữ nghĩa tương ứng; không phải mã Java thuần tự chạy được.

### Kết quả học tập

Sau bài này, bạn cần:

1. Hiểu vì sao wildcard hữu ích nhưng có rủi ro chọn nhầm join point.
2. Phân biệt mẫu tên, mẫu kiểu, mẫu chữ ký và điều kiện theo ngữ cảnh.
3. Đọc được ý nghĩa của `*`, `..`, `+` và các toán tử logic trong **cú pháp AspectJ**.
4. Phân biệt mẫu chọn *method call* và *method execution*, cùng ý nghĩa của `within`, `args`, `this`, `target`.
5. Tự xác minh tập join point được chọn bằng ca phải khớp/không được khớp, và không nhầm biểu thức pointcut với Java regex hay glob thông thường.

## 2. Từ mục tiêu chọn điểm đến một biểu thức pointcut

Hãy xem quy trình suy nghĩ:

```text
Mục tiêu chính sách
    |
    v
Cần can thiệp sự kiện nào?
    |        (call, execution, field access, ...)
    v
Cần lọc cấu trúc tĩnh nào?
    |        (package, kiểu khai báo, chữ ký, modifier, ...)
    v
Cần lọc ngữ cảnh động nào?
    |        (kiểu đối tượng thực tế, giá trị tham số, luồng chạy, ...)
    v
Biểu thức pointcut theo cú pháp công cụ
    |
    v
Weaving / interception tại các join point được hỗ trợ
    |
    v
Advice chạy cho những lần thực thi thực sự khớp
```

Có ba lớp thông tin dễ nhầm:

| Lớp | Ví dụ | Vai trò |
| --- | --- | --- |
| **Loại điểm** | Method execution | Chọn dạng sự kiện có thể can thiệp |
| **Mẫu tĩnh** | Phương thức tên `save*`, thuộc kiểu `*Service` | Chọn theo cấu trúc của chương trình |
| **Điều kiện động** | Đối tượng/đối số tại lần chạy cụ thể | Lọc những lần xuất hiện thực sự phù hợp |

Một wildcard như `*` thường hoạt động **trong một vị trí của ngữ pháp**, không phải tự động quét mọi hoạt động của chương trình. Trước khi đọc `*`, phải hỏi: **nó đang thay cho tên phương thức, kiểu trả về, tên kiểu, hay một kiểu tham số?**

## 3. Cú pháp ví dụ được dùng trong bài: AspectJ

Để có ngữ nghĩa kiểm chứng được, phần này dùng cú pháp biểu thức pointcut từ **AspectJ**. Đây là một ngôn ngữ/cơ chế AOP cho Java, có mô hình pointcut và weaving riêng.

Một biểu thức thường có dạng:

```aspectj
execution(public * com.example.service.OrderService.placeOrder(..))
```

Có thể đọc từ ngoài vào trong:

- `execution(...)`: chọn **lần thực thi phương thức**, khi phần thân phương thức tương ứng được chạy.
- `public`: yêu cầu modifier phù hợp.
- `*` sau `public`: chấp nhận **bất kỳ kiểu trả về**.
- `com.example.service.OrderService`: tên kiểu khai báo trong mẫu.
- `placeOrder`: tên phương thức.
- `(..)`: chấp nhận **không, một hoặc nhiều tham số** thuộc các kiểu bất kỳ.

Trong ví dụ, package/lớp chỉ là **tên giả định phục vụ giải thích**; đoạn trên là **biểu thức AspectJ**, không phải một dòng Java có thể đặt trực tiếp trong `main()`.

Hai giới hạn cần nhớ:

1. Biểu thức hợp lệ **chưa đủ** bảo đảm advice chạy. Phải có join point đúng loại và phạm vi mã được weaving.
2. Khi một công cụ khác cũng dùng từ `execution` hay `*`, không nên tự suy diễn rằng nó hỗ trợ mọi thành phần cú pháp và kiểu join point giống nhau.

## 4. Wildcard `*`: ý nghĩa phụ thuộc vào vị trí

Trong các mẫu kiểu, tên và chữ ký của AspectJ, `*` là ký hiệu đại diện cơ bản. Nhưng cách đọc chính xác thay đổi theo cấu trúc biểu thức.

### 4.1. Thay cho bất kỳ kiểu trả về nào

```aspectj
execution(* com.example.OrderService.find(..))
```

`*` trước tên kiểu có nghĩa là kiểu trả về của phương thức có thể là `void`, một kiểu nguyên thủy hoặc một kiểu tham chiếu, miễn các phần khác của mẫu khớp.

Nếu muốn chỉ phương thức trả `boolean`:

```aspectj
execution(boolean com.example.OrderService.isValid(..))
```

Đừng nhầm dấu `*` trong vị trí **kiểu trả về** với dấu `*` dùng làm **tên phương thức** trong ví dụ khác.

### 4.2. Thay cho tên phương thức

```aspectj
execution(* com.example.OrderService.*(..))
```

Dấu `*` ngay trước `(..)` nằm ở vị trí **tên phương thức**, nên mẫu này chọn các lần thực thi phương thức có tên bất kỳ trong kiểu tương ứng, với kiểu trả về và danh sách tham số bất kỳ.

Có thể dùng `*` như một phần của tên:

```aspectj
execution(* com.example.OrderService.find*(..))
```

Tên `find`, `findById`, `findAll` có thể khớp phần `find*`, còn `save` thì không. Ký tự `*` ở đây đại diện chuỗi ký tự có độ dài **từ không trở lên** trong phần tên được mẫu cho phép.

**Cẩn thận:** `find*` không có nghĩa chỉ chọn các phương thức *thật sự chỉ đọc*. Nếu mã nghiệp vụ có phương thức `findAndDelete`, nó vẫn có thể khớp theo tên. Mẫu tên không tự kiểm chứng ngữ nghĩa nghiệp vụ.

### 4.3. Mẫu tên kiểu

```aspectj
within(com.example.service.*Service)
```

Biểu thức trên dùng `*Service` để khớp tên kiểu kết thúc bằng `Service`, trong package phù hợp. Đây là mẫu **kiểu**, không phải mẫu tên phương thức.

Một dấu `*` trong mẫu tên kiểu không tự ý đi qua mọi dấu chấm phân cách package. Vì vậy, không nên suy từ `com.example.service.*Service` rằng nó luôn bao phủ cả các package con.

### 4.4. Một kiểu tham số bất kỳ

```aspectj
execution(* com.example.OrderService.find(*))
```

Dấu `*` bên trong danh sách tham số, trong ngữ nghĩa signature pattern của AspectJ, nghĩa là **chính xác một tham số thuộc kiểu bất kỳ**.

So sánh:

| Mẫu phần tham số | Ý nghĩa |
| --- | --- |
| `()` | Không có tham số |
| `(*)` | Chính xác một tham số, kiểu bất kỳ |
| `(*,*)` | Chính xác hai tham số, mỗi kiểu bất kỳ |
| `(java.lang.String)` | Chính xác một tham số `String` |
| `(..)` | Bất kỳ số lượng tham số, bao gồm không có |
| `(java.lang.String,..)` | Tham số đầu là `String`, theo sau có thể có thêm bất kỳ số lượng tham số |

Đây là một trong những sai lầm phổ biến nhất: **`(*)` không đồng nghĩa `(..)`**.

## 5. Ký hiệu `..`: hai vai trò quan trọng

Trong cú pháp AspectJ, `..` xuất hiện ở ít nhất hai ngữ cảnh khác nhau. Không nên đọc mọi cặp dấu chấm như “mọi thứ” một cách chung chung.

### 5.1. Bỏ qua không hoặc nhiều thành phần package trong mẫu kiểu

```aspectj
within(com.example.service..*)
```

Ở vị trí mẫu kiểu, `..` cho phép khớp qua các mức package hoặc kiểu lồng theo các quy tắc của AspectJ. Theo ý định thông thường, mẫu trên bao gồm các kiểu nằm dưới namespace `com.example.service`, kể cả những mức con phù hợp.

So sánh:

```aspectj
within(com.example.service.*)
within(com.example.service..*)
```

Mẫu thứ nhất chỉ có một wildcard tên kiểu trong package được viết. Mẫu thứ hai cho phép biểu diễn phạm vi rộng hơn qua các package con. Đây là lý do ký hiệu `..` rất hay xuất hiện trong các chính sách chọn theo package.

Ví dụ giả định:

| Tên kiểu | `com.example.service.*` | `com.example.service..*` |
| --- | --- | --- |
| `com.example.service.OrderService` | Khớp | Khớp |
| `com.example.service.payment.PaymentService` | Không | Khớp |
| `com.example.repository.OrderRepository` | Không | Không |

Ý nghĩa này được mô tả theo **cú pháp mẫu kiểu AspectJ**; cách xử lý package lồng của công cụ khác có thể khác.

### 5.2. Bỏ qua không hoặc nhiều tham số trong signature pattern

```aspectj
execution(* com.example.OrderService.update(..))
```

Trong `update(..)`, ký hiệu `..` có nghĩa **danh sách tham số dài tùy ý**, kể cả rỗng.

```aspectj
execution(* com.example.OrderService.update(java.lang.String,..))
```

Mẫu thứ hai yêu cầu **ít nhất một tham số**, trong đó tham số đầu là `String`, và cho phép có thêm tham số bất kỳ sau nó.

So sánh bốn chữ ký giả định:

| Phương thức | `update()` | `update(*)` | `update(..)` | `update(String,..)` |
| --- | --- | --- | --- | --- |
| `update()` | Có | Không | Có | Không |
| `update(String)` | Không | Có | Có | Có |
| `update(int)` | Không | Có | Có | Không |
| `update(String,int)` | Không | Không | Có | Có |

Ký hiệu `String` trong bảng viết gọn cho `java.lang.String`. Bảng giả định mọi phần khác của pointcut đều tương ứng đúng với phương thức.

### 5.3. Không nhầm `..` với `.*` của regular expression

Trong Java regex, `.*` có nghĩa **không hoặc nhiều ký tự bất kỳ** theo quy tắc của regular expression. Trong AspectJ, `..` nằm ở **mẫu package** hoặc **danh sách tham số** lại có ngữ nghĩa riêng.

Không nên biến chuỗi `com.example..*` thành Java regex rồi khẳng định kết quả khớp giống pointcut của công cụ. Có thể dùng regex trong mã ứng dụng, nhưng đó là một ngôn ngữ mẫu **khác**.

## 6. Ký hiệu `+`: kiểu cùng các kiểu con phù hợp

Một số biểu thức AspectJ dùng `+` **sau type pattern** để biểu diễn kiểu đó và các kiểu con của nó:

```aspectj
execution(* com.example.PaymentService+.*(..))
```

Theo ngữ nghĩa mẫu subtype của AspectJ, `PaymentService+` bao gồm `PaymentService` và các subtype phù hợp, bao gồm lớp triển khai giao diện nếu `PaymentService` là giao diện.

Điều này hữu ích khi chính sách phải áp dụng nhất quán cho cả một họ kiểu. Tuy nhiên, cần phân biệt:

- **Kiểu khai báo mà mẫu đang nhắm đến**, ví dụ `PaymentService+`.
- **Kiểu runtime cụ thể** của đối tượng lúc chạy, có thể là một lớp triển khai.
- **Loại join point được chọn**, ở đây là execution theo mẫu chữ ký.

Không suy rằng cứ có đối tượng thuộc subtype thì mọi lời gọi của nó chắc chắn được can thiệp: kết quả còn phụ thuộc phạm vi weaving, kiểu điểm và những điều kiện khác.

### 6.1. `+` không phải wildcard tên phương thức

`PaymentService+` là dạng **subtype type pattern**. Không dùng `+` tùy tiện sau tên phương thức như `find+` để diễn đạt một phần tên theo cách Java regex; điều đó không phải ngữ nghĩa tương ứng của ký hiệu này trong cú pháp AspectJ.

## 7. Phép toán logic để kết hợp nhiều điều kiện

Khi mẫu đơn chưa đủ chính xác, các phép toán logic kết hợp pointcut:

- `&&` — **AND**: phải thỏa cả hai điều kiện.
- `||` — **OR**: thỏa ít nhất một điều kiện.
- `!` — **NOT**: loại những điểm thỏa điều kiện bị phủ định.
- `(...)` — dùng **ngoặc** để biểu diễn rõ nhóm điều kiện.

Ví dụ:

```aspectj
execution(* com.example..*Service.*(..))
    && !within(com.example..*Generated*)
```

Đây là biểu thức AspectJ chia thành nhiều dòng để dễ đọc. Nó chọn điểm thực thi phương thức theo mẫu `*Service`, đồng thời loại những join point được định nghĩa bên trong các kiểu phù hợp với `*Generated*` theo điều kiện `within`.

Một ví dụ kết hợp hai nhóm:

```aspectj
execution(* com.example.order..*Service.*(..))
    || execution(* com.example.payment..*Service.*(..))
```

Nếu muốn loại các điểm được định nghĩa trong một tập kiểu khỏi **cả hai nhánh**, nên đặt ngoặc rõ ràng:

```aspectj
(
    execution(* com.example.order..*Service.*(..))
    || execution(* com.example.payment..*Service.*(..))
)
&& !within(com.example..*Generated*)
```

Ngoặc có thể quyết định kết quả chọn điểm. Thay vì dựa vào trí nhớ về độ ưu tiên toán tử ở từng DSL, viết ngoặc và đặt tên các pointcut con giúp người đọc kiểm tra mục đích dễ hơn.

### 7.1. Kết hợp mẫu rộng với điều kiện loại trừ

Một mẫu rộng có thể giúp phủ nhiều nơi, nhưng dễ tạo hiệu ứng không mong muốn. Mẫu loại trừ cải thiện độ chính xác **chỉ khi tập loại trừ có ý nghĩa và được duy trì**.

Nếu chính sách đặc biệt quan trọng, nên ưu tiên dấu hiệu cấu trúc ổn định — kiểu hoặc annotation có hợp đồng rõ — hơn là dựa hoàn toàn vào hậu tố tên như `*Service` hoặc `*Generated*`.

## 8. Mẫu chữ ký có cấu trúc: đừng đọc như một glob duy nhất

Trong AspectJ, một **method signature pattern** có thể chứa các vị trí như:

```text
[modifiers] return-type declaring-type.method-name(parameter-patterns)
```

Một ví dụ:

```aspectj
execution(public * com.example.api.*Service.find*(java.lang.String,..))
```

Đọc từng thành phần:

1. `execution`: loại join point.
2. `public`: modifier yêu cầu.
3. `*`: mọi kiểu trả về.
4. `com.example.api.*Service`: kiểu có tên phù hợp ở package được chỉ định.
5. `find*`: tên phương thức bắt đầu bằng `find`.
6. `java.lang.String,..`: tham số đầu là `String`, sau đó thêm không hoặc nhiều tham số.

Nếu một thành phần không khớp, toàn bộ biểu thức không khớp. Bởi vậy, khi debug biểu thức, nên tách thành từng câu hỏi về modifier, return type, declaring type, method name và parameters.

### 8.1. Ví dụ so sánh theo số tham số và kiểu trả về

Giả sử có các phương thức trong cùng kiểu `com.example.api.OrderService`:

```java
void save();
void save(String id);
boolean save(String id, int quantity);
String find(String id);
```

Đây là **mã minh họa chữ ký**, không phải Java class độc lập.

| Biểu thức AspectJ | Những phương thức khớp trong tập trên |
| --- | --- |
| `execution(* com.example.api.OrderService.save(..))` | Cả ba `save` |
| `execution(* com.example.api.OrderService.save())` | Chỉ `save()` |
| `execution(* com.example.api.OrderService.save(*))` | Chỉ `save(String)` |
| `execution(boolean com.example.api.OrderService.save(..))` | Chỉ `save(String,int)` trả `boolean` |
| `execution(* com.example.api.OrderService.find*(..))` | Chỉ `find(String)` |

Đừng chỉ đọc “save có wildcard” rồi bỏ qua vị trí của wildcard. Dấu `*` trước kiểu khai báo và dấu `*` trong tham số đang giải quyết **hai yêu cầu khác nhau**.

## 9. Mẫu tên và điều kiện theo vị trí khác nhau thế nào?

Một pointcut có thể chọn loại join point bằng `execution`, `call`, và lọc thêm ngữ cảnh tĩnh bằng `within` hoặc `withincode`, nếu công cụ cung cấp các designator tương ứng.

### 9.1. `execution(...)` và `call(...)`

```aspectj
execution(* com.example.PaymentGateway.pay(..))
call(* com.example.PaymentGateway.pay(..))
```

- `execution` chọn **việc thực thi thân phương thức phù hợp**, về phía được gọi.
- `call` chọn **vị trí gọi phương thức phù hợp**, về phía bên gọi.

Một phương thức có thể được gọi từ nhiều nơi. Nếu cần quan sát các vị trí gọi cụ thể, `call` có thể biểu đạt yêu cầu khác với `execution`. Một số cơ chế AOP chỉ hỗ trợ subset của các loại join point, vì vậy không thể thay designator rồi mặc định công cụ hoạt động.

### 9.2. `within(TypePattern)` giới hạn phạm vi từ vựng

```aspectj
within(com.example.checkout..*)
```

Trong ngữ nghĩa AspectJ, `within` chọn các join point thuộc **mã được định nghĩa trong các kiểu phù hợp**. Nó thiên về **vị trí trong cấu trúc mã**, không phải “mọi đối tượng runtime thuộc package này”.

Ví dụ chọn **lời gọi đến** `pay` xuất phát từ mã nằm trong nhóm kiểu checkout:

```aspectj
call(* com.example.PaymentGateway.pay(..))
    && within(com.example.checkout..*)
```

Đây không giống việc chọn tất cả **execution** của `pay`, vì call pointcut gắn với mã phía gọi.

### 9.3. `withincode(Signature)` lọc theo vị trí mã chứa điểm

```aspectj
call(* com.example.PaymentGateway.pay(..))
    && withincode(* com.example.CheckoutService.checkout(..))
```

Theo ngữ nghĩa AspectJ, ví dụ hướng tới những call join point của `pay` nằm trong phần mã được định nghĩa của `checkout(..)` tương ứng. `withincode` không đơn giản là “mọi lời gọi xảy ra trong cây lời gọi runtime bắt đầu từ `checkout`”.

### 9.4. `args`, `this`, `target` và `cflow` không chỉ là wildcard tên

Các designator sau có thể xét **ngữ cảnh động**:

```aspectj
args(java.lang.String,..)
this(com.example.CheckoutService)
target(com.example.PaymentGateway+)
cflow(execution(* com.example.CheckoutService.checkout(..)))
```

- `args` mô tả kiểu/khớp đối số trong ngữ cảnh join point; có thể hỗ trợ bind đối số tùy khai báo.
- `this` liên quan đến đối tượng hiện tại theo mô hình join point của AspectJ.
- `target` liên quan đến đối tượng đích.
- `cflow` liên quan đến **luồng điều khiển động**, kể cả các điểm nằm trong phạm vi một điểm gốc được chọn.

Không được nhầm các designator động với wildcard dựa hoàn toàn vào tên lớp trong mã. Ví dụ `within` xét **vị trí từ vựng**, trong khi `cflow` xét **diễn tiến lời gọi runtime**. Mức độ hỗ trợ và chi phí kiểm tra khác nhau theo công cụ và điểm được weaving.

## 10. Mẫu tên, regex và glob: ba ngôn ngữ khác nhau

Một điểm dễ gây lỗi là mang cú pháp từ ngôn ngữ này sang ngôn ngữ kia:

| Hệ biểu thức | Ví dụ | Ý nghĩa được minh họa |
| --- | --- | --- |
| **AspectJ name pattern** | `save*` | Tên có tiền tố `save` trong vị trí tên phù hợp |
| **Java regex** | `save.*` | Biểu thức chính quy khớp `save` theo sau là không hoặc nhiều ký tự |
| **Glob tệp** | `*.java` | Tên tệp có phần kết `.java` trong quy tắc glob tương ứng |

Có thể cả ba cùng khớp một vài chuỗi như `save` và `saveAll`, nhưng **cú pháp không hoán đổi được**. Trong regex, dấu chấm là ký tự đặc biệt; trong biểu thức tên kiểu AOP, dấu chấm thường phân tách thành phần package/kiểu và có ngữ nghĩa khác.

Những giả định sai thường thấy:

- **`*` không tự động là “mọi thứ qua nhiều package”**.
- **`(*)` không đồng nghĩa “mọi danh sách tham số”**.
- **`..` không phải `.*` của regex**.
- **`+` trong type pattern không có nghĩa regex “một hoặc nhiều lần lặp tên ký tự”**.
- **`?` không thể mặc định là wildcard một ký tự trong mọi DSL AOP**.
- **`**` không tự động mang ý nghĩa “đệ quy mọi package” theo thói quen glob tệp**.

Cần tra đúng tài liệu của ngôn ngữ pointcut, bao gồm phiên bản đang dùng. Ví dụ trong bài về AspectJ nhằm minh họa một bộ cú pháp **cụ thể**, không đại diện tuyệt đối cho tất cả công cụ.

## 11. Ví dụ Java 17 chạy được: chọn phương thức theo mẫu tên và số tham số

Để kiểm chứng ý tưởng **một biểu thức mẫu chọn một tập phương thức**, ta có thể dùng JDK thuần với `java.lang.reflect.Proxy`. Ví dụ này tự tạo một quy tắc tên dạng `save*` bằng cách kiểm tra tiền tố `save`, rồi kiểm tra số tham số bằng reflection.

**Đây là bộ lọc minh họa do ứng dụng tự viết**, không phải parser hay engine pointcut AspectJ. Một công cụ AOP có DSL riêng còn quyết định cú pháp, join point, weaving và điều kiện khớp của nó.

Tạo `PointcutPatternDemo.java`:

```java
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.lang.reflect.Proxy;

public class PointcutPatternDemo {
    interface Store {
        void save(String id);
        void saveAll(String id);
        void delete(String id);
    }

    static final class SimpleStore implements Store {
        @Override
        public void save(String id) {
            System.out.println("business:save " + id);
        }

        @Override
        public void saveAll(String id) {
            System.out.println("business:saveAll " + id);
        }

        @Override
        public void delete(String id) {
            System.out.println("business:delete " + id);
        }
    }

    static Object dispatch(Store target, Method method, Object[] args)
            throws Throwable {
        boolean nameMatches = method.getName().startsWith("save");
        boolean oneParameter = method.getParameterCount() == 1;
        boolean selected = nameMatches && oneParameter;

        if (selected) {
            System.out.println("advice:before " + method.getName());
        }
        try {
            return method.invoke(target, args);
        } catch (InvocationTargetException ex) {
            throw ex.getCause();
        } finally {
            if (selected) {
                System.out.println("advice:after " + method.getName());
            }
        }
    }

    public static void main(String[] args) {
        Store target = new SimpleStore();
        Store proxy = (Store) Proxy.newProxyInstance(
                Store.class.getClassLoader(),
                new Class<?>[] { Store.class },
                (ignored, method, values) -> dispatch(target, method, values)
        );

        proxy.save("A");
        proxy.saveAll("B");
        proxy.delete("C");
    }
}
```

Biên dịch/chạy với JDK 17 trở lên:

```bash
javac PointcutPatternDemo.java
java PointcutPatternDemo
```

Đầu ra dự kiến:

```text
advice:before save
business:save A
advice:after save
advice:before saveAll
business:saveAll B
advice:after saveAll
business:delete C
```

### 11.1. Phân tích kết quả

- `save` và `saveAll` đều có tiền tố `save`, tương ứng ý tưởng tên mẫu `save*` có wildcard độ dài từ không trở lên.
- Cả hai phương thức nhận chính xác **một tham số**, nên thỏa điều kiện bổ sung.
- `delete` cũng có một tham số nhưng **không** khớp tên; phương thức vẫn chạy nghiệp vụ nhưng không nhận hai dòng advice.
- Logic `before/after` nằm trong bộ chặn lời gọi, nên mã `SimpleStore` không cần gọi nó trực tiếp.

Nếu thêm `saveAll()` **không tham số** vào giao diện và đích, nó sẽ khớp điều kiện tên nhưng **không** thỏa điều kiện một tham số — tương tự việc một mẫu pointcut thực cần khớp **toàn bộ điều kiện**, không chỉ khớp tên.

### 11.2. Giới hạn cố ý của ví dụ

- Dấu `*` không hề được một trình phân tích DSL xử lý; chương trình dùng `startsWith("save")` để minh họa **một quy tắc đơn giản**.
- Proxy JDK chỉ can thiệp các lời gọi tới phương thức giao diện **đi qua proxy**. Lời gọi trực tiếp tới `target` hoặc một lời gọi nội bộ trên cùng đối tượng không mặc nhiên đi qua handler.
- `Method.getParameterCount()` phản ánh số tham số khai báo; nó khác việc áp dụng những điều kiện `args` động của ngôn ngữ pointcut.
- `finally` được dùng để minh họa phần xử lý sau lời gọi; với advice thật, thời điểm và cách xử lý kết quả/ngoại lệ thuộc ngữ nghĩa cụ thể của công cụ.

Ví dụ giúp nhìn thấy **điều kiện tên + điều kiện chữ ký + hành vi chặn lời gọi**, trong khi các biểu thức AspectJ trước đó giải thích cú pháp thực tế của một công cụ AOP cụ thể.

## 12. Viết pointcut tập trung và dễ bảo trì

Các mẫu càng ngắn và rộng thì càng dễ viết, nhưng cũng càng dễ áp dụng lời khuyên sai cho quá nhiều phương thức.

Giả sử mục tiêu là ghi metric cho phương thức public trong một nhóm service, đồng thời loại những điểm được định nghĩa trong kiểu nội bộ phục vụ thử nghiệm. Một biểu thức AspectJ minh họa:

```aspectj
execution(public * com.example.business..*Service.*(..))
    && !within(com.example.business..*Test*)
```

Nên thẩm định từng điều kiện:

1. **Loại join point:** có thực sự muốn method execution không?
2. **Modifier:** public có đúng ranh giới nghiệp vụ cần quan sát không?
3. **Kiểu khai báo:** các lớp cần theo dõi có nhất quán theo hậu tố `Service` không?
4. **Package:** có cần các package con? Có bỏ sót module liên quan?
5. **Loại trừ:** lớp có `Test` trong tên có thật sự là lớp cần loại? Có lớp dùng tên khác?
6. **Phạm vi weaving:** các lớp đã được công cụ xử lý chưa?
7. **Tác động advice:** nếu advice thay đổi kết quả hay từ chối thực thi, rủi ro có lớn hơn việc chỉ ghi metric không?

Một thiết kế có thể dùng **named pointcut** để biểu đạt ý nghĩa rõ hơn. Ví dụ sau là một **mảnh cú pháp AspectJ** đặt bên trong khai báo aspect phù hợp, chưa phải chương trình có thể biên dịch độc lập:

```aspectj
pointcut businessOperations():
    execution(public * com.example.business..*Service.*(..));

pointcut measuredOperations():
    businessOperations()
    && !within(com.example.business..*Test*);
```

Lợi ích của pointcut có tên là tách **mục đích** và **biểu thức kỹ thuật**, cho phép tái sử dụng và đọc lại dễ dàng. Nhưng named pointcut không tự động bảo đảm chọn đúng mọi phương thức: vẫn cần kiểm thử tập khớp.

## 13. Những tình huống mẫu thường gặp và cách diễn giải

Bảng sau dùng **cú pháp AspectJ**, với package và kiểu giả định:

| Mong muốn | Biểu thức minh họa | Lưu ý |
| --- | --- | --- |
| Mọi lần thực thi phương thức | `execution(* *(..))` | Rất rộng, tùy phạm vi weaving |
| Phương thức `save` có số tham số tùy ý | `execution(* *.save(..))` | Mẫu tên chính xác `save` |
| Phương thức bắt đầu bằng `find` | `execution(* *.find*(..))` | Khớp theo tên, không xác nhận tính chỉ đọc |
| Phương thức có một tham số kiểu bất kỳ | `execution(* *.*(*))` | Khác `(..)` |
| Các kiểu trong một package | `within(com.example.api.*)` | Không mặc định gồm mọi package con |
| Các kiểu trong package và package con | `within(com.example.api..*)` | Phạm vi từ vựng của kiểu |
| Method call tên `pay` | `call(* *.pay(..))` | Phía vị trí gọi |
| Chỉ method execution trả `boolean` | `execution(boolean *.*(..))` | Ràng buộc kiểu trả về |
| Các loại triển khai thuộc họ kiểu | `execution(* com.example.PaymentService+.*(..))` | `+` là subtype pattern |
| Loại trừ một vùng mã | `execution(* *(..)) && !within(com.example.generated..*)` | Phải giữ điều kiện loại trừ đúng ngữ nghĩa |

Không nên sao chép bảng vào dự án chỉ vì biểu thức nhìn hợp lý. Việc chọn đúng join point còn phụ thuộc loại điểm thực thi, giới hạn công cụ và quyền truy cập vào mã cần weaving.

### 13.1. Mẫu “rộng trước, hẹp sau” có rủi ro gì?

Biểu thức như `execution(* *(..))` có thể chạm tới rất nhiều phương thức trong mã được weaving, kể cả những điểm mà advice không nên chạy. Điều này gây overhead và có thể tạo log dày đặc, đệ quy không mong muốn nếu aspect ghi log bằng một phương thức cũng nằm trong tập khớp.

Cần định nghĩa ranh giới rõ: package, kiểu, dấu đánh dấu có ý nghĩa hoặc tập pointcut con đã được kiểm chứng. **Mẫu rộng không phải mặc định tốt nhất** chỉ vì nó giảm số ký tự.

## 14. Điều kiện điểm tĩnh và điều kiện runtime

Wildcard tên/chữ ký chủ yếu mô tả **cấu trúc tĩnh**. Nhưng một số pointcut còn dùng điều kiện runtime như kiểu đối tượng thực, đối số hoặc luồng điều khiển.

Ví dụ:

```aspectj
execution(* com.example.TransferService.transfer(..))
    && args(java.lang.String, long)
```

Biểu thức trên minh họa việc kết hợp **method execution** với điều kiện theo **kiểu/cấu trúc đối số** theo ngữ nghĩa `args` của AspectJ.

Đừng tự coi `args` luôn là cùng một phép so khớp chữ ký `(String,long)`: các designator xét đối tượng hoặc giá trị runtime có thể mang ngữ nghĩa khác với signature pattern; đặc biệt khi có overload, kiểu con, tham số kiểu tham chiếu và dữ liệu được bind.

Nếu yêu cầu là “chỉ khi số tiền vượt 1000”, điều kiện đó phụ thuộc **giá trị thực tế của lần gọi**. Không thể suy ra từ wildcard tên hoặc chữ ký. Cần dùng chức năng pointcut động/advice tương ứng nếu công cụ hỗ trợ và xác định rõ thời điểm kiểm tra.

### 14.1. Chi phí của điều kiện động

Một biểu thức có nhiều điều kiện tĩnh có thể được công cụ tối ưu sớm tại những vị trí không có khả năng khớp. Điều kiện runtime vẫn có thể phải được đánh giá ở mỗi invocation tiềm năng. Với điểm rất “nóng” (hot path), sự khác biệt này ảnh hưởng chi phí thực thi và tần suất advice.

Tránh đưa tác vụ I/O đắt hoặc gọi mạng vào điều kiện chọn điểm nếu không có lý do mạnh. Pointcut nên giữ mục đích rõ; logic phức tạp thường cần được cân nhắc ở lớp chính sách phù hợp và kiểm thử hiệu năng.

## 15. Kiểm thử pointcut: kiểm tra cả tập khớp lẫn tập loại trừ

Một pointcut đúng không chỉ cần bắt được phương thức mong muốn; nó còn phải **không bắt nhầm** những phương thức khác. Trước khi triển khai, lập một bảng các ca khớp và không khớp.

Ví dụ mục tiêu: các method execution `find*` của kiểu `*Repository` dưới `com.example.data`, có danh sách tham số bất kỳ.

Mẫu minh họa:

```aspectj
execution(* com.example.data..*Repository.find*(..))
```

Bảng dự đoán theo tên/chữ ký, giả định các join point có thể được weaving:

| Phương thức | Dự đoán | Lý do |
| --- | --- | --- |
| `com.example.data.OrderRepository.find(String)` | Khớp | Kiểu và tên phương thức phù hợp |
| `com.example.data.archive.ArchiveRepository.findAll()` | Khớp | Có package con, tên `find*` |
| `com.example.data.OrderRepository.save(String)` | Không | Tên không bắt đầu `find` |
| `com.example.api.OrderRepository.find(String)` | Không | Package nằm ngoài mẫu |
| `com.example.data.OrderReader.find(String)` | Không | Tên kiểu không có hậu tố `Repository` |

Bảng chỉ minh họa **điều kiện cấu trúc**, không tự chứng minh behavior runtime. Bước xác minh thực tế là thực hiện những ca gọi tương ứng, quan sát số lần advice chạy và đối chiếu với tập join point mà công cụ thông báo/ghi nhận.

### 15.1. Quy trình debug khi biểu thức không khớp

1. **Đọc chính xác thông báo từ compiler/weaver:** lỗi cú pháp khác với biểu thức hợp lệ nhưng không khớp.
2. **Rút gọn biểu thức:** bắt đầu từ một mẫu chữ ký cụ thể đã biết, sau đó thêm từng wildcard hoặc điều kiện.
3. **Kiểm tra package/declaring type thực tế:** chú ý lớp kế thừa, giao diện, lớp lồng, lớp sinh ra và package con.
4. **Kiểm tra overload/return type/modifier:** cùng tên phương thức chưa chắc cùng chữ ký.
5. **Kiểm tra loại join point:** `call` và `execution` không thay thế nhau.
6. **Kiểm tra phạm vi weaving/interception:** lời gọi đã đi qua điểm công cụ hỗ trợ chưa?
7. **Kiểm tra điều kiện động:** `args`, `this`, `target`, `cflow` nếu có.
8. **Kiểm tra hiệu ứng từ advice khác:** advice bên ngoài có thể từ chối lời gọi hoặc đổi đường thực thi.
9. **Thử ca âm tính:** đảm bảo mẫu không khớp vùng không mong muốn.

Đừng sửa wildcard bằng cách làm nó rộng tối đa ngay khi có lỗi thiếu điểm; điều đó có thể vô tình mở rộng chính sách sang những vùng không được phép.

## 16. Các lỗi phổ biến và cách sửa

**Lỗi 1 — Dùng `(*)` khi muốn mọi danh sách tham số.** Trong signature pattern AspectJ, `(*)` chọn đúng **một** tham số. Dùng `(..)` khi muốn không hoặc nhiều tham số.

**Lỗi 2 — Dùng `*` cho tên kiểu rồi cho rằng có cả package con.** Cần hiểu sự khác nhau giữa `package.*` và `package..*` trong cú pháp mẫu kiểu cụ thể.

**Lỗi 3 — Coi `save*` là Java regex `save.*`.** Có thể cùng mô tả một tiền tố trong trường hợp đơn giản, nhưng ngôn ngữ biểu thức khác nhau; không sao chép nguyên văn qua lại.

**Lỗi 4 — Áp dụng `+` cho mẫu tên phương thức.** `+` được dùng cho quan hệ subtype trong type pattern, không phải cú pháp chung để lặp ký tự của tên.

**Lỗi 5 — Lạm dụng `execution(* *(..))`.** Mẫu quá rộng có thể chạm tới nhiều phương thức, làm tăng chi phí và gây ảnh hưởng ngoài mong muốn.

**Lỗi 6 — Không đặt ngoặc khi kết hợp OR với điều kiện loại trừ.** Một điều kiện `!within(...)` có thể chỉ áp dụng cho một nhánh nếu biểu thức được nhóm sai. Dùng `(...)` rõ ràng.

**Lỗi 7 — Nhầm `within` với việc đối tượng runtime thuộc kiểu nào.** `within` mô tả phạm vi từ vựng của mã ở join point, còn `this/target` mang ngữ nghĩa theo đối tượng phù hợp.

**Lỗi 8 — Nhầm call và execution.** Cùng tên phương thức có thể tạo các điểm ở hai phía khác nhau; cần xác định thiết kế muốn chặn vị trí gọi hay phần thực thi.

**Lỗi 9 — Chỉ kiểm thử các điểm phải khớp.** Cần kiểm thử cả điểm **không được khớp**; wildcard rộng có thể gây tác động ngoài ý muốn.

**Lỗi 10 — Quên khả năng của công cụ.** Biểu thức cú pháp đúng không bảo đảm mọi lớp được weaving hoặc mọi đường gọi đi qua proxy; đặc biệt lưu ý self-invocation và mã thư viện.

## 17. Câu hỏi luyện tập có đáp án

**Câu 1. Trong cú pháp AspectJ, `execution(* *.save(*))` có chọn `save()` không?**

Không. Vùng tham số `(*)` yêu cầu đúng một tham số; `save()` có không tham số. Nếu muốn khớp mọi số tham số, dùng `(..)`.

**Câu 2. Khác biệt giữa `com.example.api.*` và `com.example.api..*` là gì?**

Trong mẫu kiểu AspectJ, dạng có `..` có thể bao phủ các mức package con phù hợp, còn dạng `.*` ở cuối chỉ diễn đạt một thành phần tên kiểu trực tiếp theo mẫu.

**Câu 3. Trong `execution(* com.example.*Service.find*(java.lang.String,..))`, dấu `*` đầu tiên nghĩa gì?**

Nó ở vị trí **kiểu trả về**, nên cho phép kiểu trả về bất kỳ. `*Service` lại là phần mẫu tên kiểu, `find*` là phần mẫu tên phương thức.

**Câu 4. `PaymentService+` dùng để làm gì?**

Đây là subtype type pattern của AspectJ, mô tả `PaymentService` và các subtype phù hợp. Nó không phải quy tắc “mọi tên bắt đầu bằng PaymentService”.

**Câu 5. Tại sao `execution(* *.pay(..))` và `call(* *.pay(..))` có thể quan sát khác nhau?**

Vì `execution` mô tả việc thực thi thân phương thức, còn `call` mô tả vị trí gọi. Một phương thức có thể có nhiều call sites, trong khi execution thuộc ranh giới phần thân được gọi.

**Câu 6. Viết một mẫu theo cú pháp AspectJ để chọn method execution có tên bắt đầu bằng `find`, trong các kiểu kết thúc bằng `Repository` dưới package `com.example.data` và các package con.**

```aspectj
execution(* com.example.data..*Repository.find*(..))
```

Mẫu này cần được kiểm tra với các kiểu/chữ ký thật và phạm vi weaving thực tế trước khi dùng cho chính sách quan trọng.

**Câu 7. Một pointcut theo tên đã khớp nhưng advice không chạy. Có thể kết luận cú pháp wildcard sai không?**

Không. Cần kiểm tra loại join point, điều kiện động, phạm vi mã được weaving, đường đi qua proxy và các advice bao ngoài. “Khớp mẫu chữ ký” mới là một phần của điều kiện để advice thực sự chạy.

## 18. Ghi nhớ và nguồn tham khảo cú pháp

- **Wildcard là thành phần của ngữ pháp, không phải lời hứa rằng mọi ký tự hay mọi hành vi đều được khớp.**
- Trong ví dụ AspectJ, `*` đại diện cho tên/kiểu theo vị trí, `..` dùng cho phạm vi package hoặc số tham số tùy ngữ cảnh, `+` mở rộng subtype, và `&&`, `||`, `!` kết hợp các điều kiện.
- **Mẫu tĩnh và điều kiện động bổ sung cho nhau**: một biểu thức có thể hợp lệ nhưng không áp dụng cho mọi lần chạy.
- **Công cụ quyết định cú pháp lẫn khả năng can thiệp**. Khi chuyển sang một công cụ AOP khác, cần đọc lại ngữ pháp và loại join point được hỗ trợ.
- **Đánh giá pointcut bằng cả ca dương tính lẫn âm tính**, quan sát hành vi khi chạy và kiểm tra đúng phạm vi weaving.

Tham khảo để xác minh **riêng cú pháp AspectJ** được minh họa trong bài:

- [AspectJ Quick Reference — Pointcuts, Type Patterns, Advice](https://eclipse.dev/aspectj/doc/latest/progguide/quickreference.html)
- [AspectJ Programming Guide — Pointcuts và Pattern Syntax](https://eclipse.dev/aspectj/doc/released/progguide/semantics-pointcuts.html)

Hai tài liệu này mô tả cú pháp/khả năng của **một công cụ AOP cụ thể**. Ý tưởng tổng quát cần giữ là: chọn đúng điểm, hiểu đúng cách biểu thức mẫu hoạt động, kiểm chứng được hành vi thực tế và tránh áp dụng advice ngoài phạm vi đã thiết kế.
