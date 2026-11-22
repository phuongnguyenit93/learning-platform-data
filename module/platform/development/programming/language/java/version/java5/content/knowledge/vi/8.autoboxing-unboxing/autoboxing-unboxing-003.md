# Unboxing trong phép tính, so sánh và điều kiện

## 1. Khi nào một wrapper phải trở thành primitive?

Các lớp bao như `Integer`, `Long`, `Double` và `Boolean` là kiểu tham chiếu. Các phép toán số học và điều kiện logic thường cần giá trị nguyên thủy tương ứng. **Unboxing** là phép chuyển từ một wrapper sang primitive, chẳng hạn `Integer` → `int` hoặc `Boolean` → `boolean`.

```java
Integer quantity = 6;
int next = quantity + 1;
```

Để thực hiện phép cộng, Java lấy giá trị `int` từ `quantity`, rồi cộng với `1`. Có thể đọc về ý nghĩa như `quantity.intValue() + 1`, dù không cần viết lời gọi ấy bằng tay.

Điểm cần nhớ: wrapper có thể là `null`, còn primitive không có trạng thái `null`. Unboxing một tham chiếu `null` gây `NullPointerException`; Java không tự coi `null` là `0` hoặc `false`.

Bài này dùng kiến thức vẫn áp dụng trong Java hiện hành. Các ví dụ đầy đủ chạy với Java 17 trở lên; không sử dụng constructor wrapper đã bị deprecated để minh họa.

## 2. Unboxing trong phép tính số học

### Hai wrapper có thể cùng được unbox

```java
Integer quantity = 6;
Double unitPrice = 2.5;
double amount = quantity * unitPrice;
```

`quantity` được unbox thành `int`, `unitPrice` thành `double`. Quy tắc nâng kiểu số của phép toán tiếp tục chuyển số nguyên sang kiểu phù hợp để thực hiện phép nhân dưới kiểu `double`; kết quả là `15.0`.

Unboxing chỉ là một phần của quá trình. Cần xét tiếp kiểu primitive của phép toán:

```java
Integer total = 5;
Integer count = 2;
double truncated = total / count;          // 2.0
double fractional = (double) total / count; // 2.5
```

Ở dòng đầu, hai wrapper đều trở thành `int`, nên phép chia là chia nguyên, cho kết quả `2`; sau đó mới mở rộng sang `double`. Kiểu của biến nhận kết quả không quay ngược để biến phép chia ấy thành chia thực.

Ở dòng sau, biểu thức bên trái phép chia đã được chuyển sang `double`, nên phép chia dùng số thực. Việc cast vẫn cần unbox `total`; nếu `total` là `null`, cast này không tránh được lỗi.

### Kiểu nhỏ có thể được nâng lên int

```java
Byte small = 2;
int result = small + 1;
```

`small` được unbox thành `byte`, rồi tham gia phép toán sau nâng kiểu số. Kết quả của phép cộng này có kiểu `int`, không phải `Byte` chỉ vì đầu vào là wrapper đó.

Không dùng unboxing như một phép kiểm tra tràn số. Các quy tắc chia cho `0`, tràn số nguyên và độ chính xác số thực vẫn áp dụng theo kiểu primitive của phép toán.

### Tăng giá trị wrapper có cả unboxing và boxing trở lại

```java
Integer counter = 6;
Integer before = counter;
counter++;
System.out.println(counter); // 7
System.out.println(before);  // 6
```

Java lấy giá trị số, tăng nó rồi gán lại kết quả đã boxing cho `counter`. Nó không sửa trạng thái của đối tượng `Integer` cũ; wrapper số là bất biến. Nếu `counter` là `null`, phép tăng thất bại khi cần unbox.

## 3. Không phải mọi dấu + đều là phép cộng số

```java
Integer missing = null;
String message = "value=" + missing; // "value=null"
// int next = missing + 1; // Chạy sẽ gây NullPointerException.
```

Dòng tạo chuỗi dùng phép nối chuỗi và chuyển biểu diễn của đối tượng sang văn bản; nó không cần lấy một giá trị `int` từ `missing` để cộng. Vì vậy, việc in được wrapper đang null không chứng minh wrapper đó an toàn để dùng trong phép tính.

Ngược lại, `"value=" + (missing + 1)` phải tính biểu thức trong ngoặc trước khi nối chuỗi, nên vẫn lỗi do unboxing `null`.

## 4. So sánh số: <, >, <=, >= cần giá trị số

```java
Integer score = 80;
Integer passMark = 60;
boolean passed = score >= passMark;
```

Hai wrapper được unbox để so sánh số. Nếu một trong hai là `null`, biểu thức có thể gây `NullPointerException` tại bước unbox tương ứng.

Đối với các kiểu số khác nhau, quy tắc nâng kiểu số tiếp tục áp dụng sau unboxing. Ví dụ `Integer` với `Double` có thể được so sánh về mặt số học qua `<`, nhưng điều này không có nghĩa hai lớp wrapper là cùng kiểu hoặc `equals` sẽ coi chúng là bằng nhau.

Nếu API cần một giá trị số bắt buộc, nên xác nhận điều kiện ấy tại ranh giới nhận dữ liệu thay vì để lỗi xuất hiện sâu trong một biểu thức nhiều phép toán.

## 5. Dấu == phụ thuộc kiểu tĩnh của hai toán hạng

### Wrapper so với primitive: có thể unbox

```java
Integer count = 1000;
boolean sameValue = count == 1000;
```

Một phía là `int`, nên Java unbox `count` để so sánh giá trị số. Với giá trị trên, kết quả là `true`. Nếu `count` là `null`, biểu thức gây `NullPointerException`.

### Hai wrapper cùng kiểu: so sánh tham chiếu

```java
Integer left = Integer.valueOf(1000);
Integer right = Integer.valueOf(1000);
boolean sameReference = left == right;
boolean sameValue = left.equals(right);
```

`left == right` trong ví dụ so sánh hai tham chiếu `Integer`; nó không tự đổi thành phép so sánh `int`. Đừng dùng kết quả quan sát được của `==` làm quy tắc so sánh giá trị: việc các wrapper có dùng chung đối tượng hay không có thể phụ thuộc phạm vi giá trị và cơ chế tái sử dụng đối tượng.

Không cần tạo hai wrapper bằng constructor deprecated để tránh cache. Hãy chọn đúng phép so sánh theo hợp đồng mong muốn:

- Nếu cần bằng nhau theo giá trị cùng lớp wrapper, dùng `equals` khi bên nhận chắc chắn khác `null`.
- Nếu cần xử lý cả hai tham chiếu có thể null, cân nhắc `Objects.equals(left, right)` và quyết định rõ null có được coi bằng null hay không.
- Nếu cần so sánh số giữa các kiểu khác nhau, xác định phép chuyển đổi primitive phù hợp với độ chính xác của miền dữ liệu.

`Integer.valueOf(1).equals(Long.valueOf(1))` là `false`: hai wrapper khác lớp không được `Integer.equals` coi là cùng giá trị. `Objects.equals` cũng không tự chuẩn hóa các lớp số khác nhau thành một kiểu số chung.

### So sánh với null không cần unbox

```java
Integer value = null;
boolean absent = value == null; // true, kiểm tra tham chiếu.
// boolean zero = value == 0;   // Gây NullPointerException khi chạy.
```

Đây là khác biệt thiết yếu khi đọc một điều kiện kiểm tra dữ liệu thiếu.

| Biểu thức, với các biến đúng kiểu tương ứng | Cơ chế chính | Nếu wrapper là null |
| --- | --- | --- |
| `Integer a; a < 10` | Unbox và so sánh số | Ném `NullPointerException` |
| `Integer a; a == 10` | Unbox và so sánh số | Ném `NullPointerException` |
| `Integer a, b; a == b` | So sánh tham chiếu | Không unbox; hai null cho `true` |
| `Integer a; a == null` | So sánh tham chiếu | Cho `true` |
| `Boolean flag; flag == true` | Unbox và so sánh boolean | Ném `NullPointerException` |

Không suy ra cơ chế chỉ bằng ký hiệu `==`; hãy đọc kiểu của cả hai toán hạng.

## 6. Điều kiện Boolean cần boolean

```java
Boolean enabled = Boolean.TRUE;
if (enabled) {
    System.out.println("enabled");
}
```

Điều kiện `if` cần `boolean`, nên `enabled` được unbox. Quy tắc tương tự xuất hiện ở điều kiện `while`, `do-while`, phần điều kiện của `for` thông thường và toán tử phủ định `!`.

Nếu `enabled` là `null`, `if (enabled)` và `!enabled` đều có thể gây `NullPointerException`. Viết `enabled == true` không làm điều kiện null-safe; literal `true` là primitive nên vẫn có unboxing.

Có hai chính sách phổ biến, cần chọn theo ý nghĩa dữ liệu:

```java
Boolean enabled = null;
boolean allowWhenTrue = Boolean.TRUE.equals(enabled);
```

Cách này chỉ trả `true` khi giá trị là đúng; cả `false` và `null` đều dẫn tới `false`. Nó **chủ động gộp** trạng thái thiếu dữ liệu với trạng thái không cho phép. Chỉ dùng khi hợp đồng nghiệp vụ chấp nhận việc gộp ấy.

Nếu `null` là dữ liệu không hợp lệ, nên từ chối rõ ràng hoặc yêu cầu đầu vào là primitive `boolean` ở nơi phù hợp. Đừng âm thầm đổi thành `false` chỉ để tránh ngoại lệ mà làm mất ý nghĩa “chưa biết”.

## 7. Short-circuit có thể bảo vệ bước unboxing

```java
Integer limit = null;
boolean positive = limit != null && limit > 0;
```

`&&` chỉ đánh giá vế phải khi vế trái là `true`. Vì `limit != null` là `false`, phép so sánh `limit > 0` không được thực hiện, nên không có unboxing từ null ở đây.

Tương tự:

```java
Boolean allowed = null;
boolean selected = allowed != null && allowed;
```

Vế kiểm tra null cần đứng trước. Nếu viết `allowed && allowed != null`, Java đã cần unbox `allowed` ở vế đầu nên không được bảo vệ.

Không thay `&&` bằng `&` với mong đợi tương đương:

```java
// Với allowed == null, câu lệnh sau gây NullPointerException:
// boolean selected = allowed != null & allowed;
```

Toán tử `&` trên các giá trị boolean đánh giá cả hai vế, nên vế phải vẫn được unbox. Với `||`, vế phải chỉ chạy khi vế trái là `false`; với `|`, cả hai vế đều được đánh giá. Chọn đúng toán tử khi điều kiện có kiểm tra dữ liệu thiếu hoặc có tác động phụ.

## 8. Toán tử điều kiện ?: cũng có thể làm unboxing

Một trường hợp dễ bỏ sót:

```java
boolean useOptional = true;
Integer optional = null;
// Integer chosen = useOptional ? optional : 0;
```

Nếu bỏ chú thích dòng cuối và chạy với dữ liệu trên, nó gây `NullPointerException`. Hai nhánh `Integer` và `int` của biểu thức điều kiện số dẫn tới kiểu kết quả primitive `int` trong trường hợp này. Nhánh được chọn là `optional`, nên phải unbox nó, dù biến đích `chosen` có kiểu `Integer`.

Chỉ nhánh được chọn mới được đánh giá; lỗi không phải do Java luôn tính cả hai nhánh. Vấn đề là nhánh ấy cần chuyển đổi theo kiểu của toàn bộ biểu thức.

Nếu cần bảo toàn khả năng null và hợp đồng cho phép, có thể tránh trộn hai kiểu nhánh trong trường hợp cụ thể này:

```java
Integer chosen = useOptional ? optional : Integer.valueOf(0);
```

Ở đây hai nhánh cùng có kiểu `Integer`, nên kết quả có thể giữ `null`. Điều đó không khiến `chosen` an toàn để dùng trong phép tính sau đó. Khi ý nghĩa nhánh và chính sách null khó đọc, tách thành `if/else` thường rõ hơn việc dựa vào một biểu thức điều kiện phức tạp.

## 9. Chương trình chạy đầy đủ

Lưu thành **`UnboxingExpressionsDemo.java`**:

```java
import java.util.Objects;

public class UnboxingExpressionsDemo {
    public static void main(String[] args) {
        Integer quantity = 6;
        Double unitPrice = 2.5;
        System.out.println("amount=" + (quantity * unitPrice));

        Integer total = 5;
        Integer count = 2;
        double truncated = total / count;
        double fractional = (double) total / count;
        System.out.println("integer division=" + truncated);
        System.out.println("floating division=" + fractional);

        Integer a = Integer.valueOf(1000);
        Integer b = Integer.valueOf(1000);
        System.out.println("value equal=" + Objects.equals(a, b));
        System.out.println("primitive equal=" + (a == 1000));

        Boolean enabled = null;
        System.out.println("true only=" + Boolean.TRUE.equals(enabled));
        Integer limit = null;
        System.out.println("guarded=" + (limit != null && limit > 0));

        Integer missing = null;
        try {
            int next = missing + 1;
            System.out.println(next);
        } catch (NullPointerException ex) {
            System.out.println("arithmetic unboxing failed");
        }

        try {
            if (enabled) {
                System.out.println("enabled");
            }
        } catch (NullPointerException ex) {
            System.out.println("condition unboxing failed");
        }

        boolean useOptional = true;
        Integer optional = null;
        try {
            Integer chosen = useOptional ? optional : 0;
            System.out.println(chosen);
        } catch (NullPointerException ex) {
            System.out.println("conditional unboxing failed");
        }

        Integer counter = 6;
        Integer previous = counter;
        counter++;
        System.out.println("counter=" + counter + ", previous=" + previous);
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -Xlint:all UnboxingExpressionsDemo.java
java UnboxingExpressionsDemo
```

Stdout chính xác:

```text
amount=15.0
integer division=2.0
floating division=2.5
value equal=true
primitive equal=true
true only=false
guarded=false
arithmetic unboxing failed
condition unboxing failed
conditional unboxing failed
counter=7, previous=6
```

Các ngoại lệ trong chương trình được tạo và bắt có chủ đích để phân biệt ba nơi cần unboxing: phép cộng, điều kiện boolean và nhánh của toán tử điều kiện. Trong mã ứng dụng, chính sách xử lý null nên được đặt tại nơi thích hợp, không coi việc bắt mọi `NullPointerException` như cách thay thế cho một hợp đồng dữ liệu rõ ràng.

## 10. Cách đọc và sửa một biểu thức có wrapper

1. Ghi lại kiểu tĩnh của từng toán hạng: primitive, wrapper số, `Boolean`, `String` hay một kiểu tham chiếu khác.
2. Xác định toán tử đang dùng theo ngữ cảnh: cộng số hay nối chuỗi, so sánh số hay so sánh tham chiếu.
3. Đánh dấu vị trí cần unbox và kiểm tra khả năng null tại từng vị trí.
4. Xét nâng kiểu số, chia nguyên, short-circuit và kiểu của `?:`, thay vì chỉ nhìn kiểu của biến đích.
5. Chọn hợp đồng xử lý dữ liệu thiếu: từ chối, mặc định có chủ đích hoặc giữ ba trạng thái. Sau đó mới viết điều kiện tương ứng.

Không sửa mọi lỗi bằng cách thay wrapper thành primitive nếu `null` đang mang một ý nghĩa cần bảo toàn. Ngược lại, nếu một giá trị luôn bắt buộc tồn tại và không cần tương tác với API tham chiếu ở tầng đó, primitive có thể biểu đạt hợp đồng rõ hơn và giảm các bước unboxing không cần thiết.

## 11. Tự thực hành

1. Đổi `count` trong phép chia thành `null`, rồi thành `0`. Phân biệt `NullPointerException` do unboxing với `ArithmeticException` do chia nguyên cho 0.
2. Với `Integer value = null`, so sánh `value == null`, `value == 0` và `Objects.equals(value, 0)`. Chỉ ra phép nào cần unbox và ý nghĩa của từng kết quả.
3. Thử `Boolean flag` lần lượt là `true`, `false`, `null`. So sánh `if (flag)` với `Boolean.TRUE.equals(flag)` và giải thích chính sách dữ liệu khác nhau.
4. Đảo thứ tự hai vế trong `flag != null && flag` để kiểm chứng vì sao short-circuit chỉ bảo vệ khi điều kiện được đặt đúng chỗ.
5. So sánh hai nhánh `Integer`/`int` với hai nhánh cùng `Integer` trong `?:`; xác định trường hợp nào giữ được `null` và trường hợp nào cần unbox.

Unboxing giúp mã dùng wrapper trông giống mã primitive, nhưng các chuyển đổi vẫn có hệ quả thật. Đọc đúng kiểu toán hạng và nơi phát sinh chuyển đổi là cách xác định chính xác phép tính, phép so sánh và điều kiện có an toàn với dữ liệu hiện có hay không.

## Tài liệu đối chiếu

- [JLS §5.1.8 — Unboxing Conversion](https://docs.oracle.com/javase/specs/jls/se25/html/jls-5.html#jls-5.1.8): chuyển đổi wrapper sang primitive và trường hợp null.
- [JLS §15.20.1 — Numerical Comparison Operators](https://docs.oracle.com/javase/specs/jls/se25/html/jls-15.html#jls-15.20.1): so sánh số và nâng kiểu.
- [JLS §15.21 — Equality Operators](https://docs.oracle.com/javase/specs/jls/se25/html/jls-15.html#jls-15.21): khác biệt giữa bằng nhau số, boolean và tham chiếu.
- [JLS §15.23 — Conditional-And Operator](https://docs.oracle.com/javase/specs/jls/se25/html/jls-15.html#jls-15.23): quy tắc đánh giá ngắn mạch.
- [JLS §15.25 — Conditional Operator](https://docs.oracle.com/javase/specs/jls/se25/html/jls-15.html#jls-15.25): xác định kiểu và đánh giá toán tử điều kiện.
