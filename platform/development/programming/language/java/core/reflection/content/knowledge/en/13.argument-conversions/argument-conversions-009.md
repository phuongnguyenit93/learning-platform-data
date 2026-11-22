# Phân biệt không có đối số với một đối số `null` khi gọi Java Reflection

Trong Java Reflection, hai cách gọi sau **khác nhau hoàn toàn**:

```java
method.invoke(target);                 // Không truyền đối số nào cho method đích.
method.invoke(target, (Object) null); // Truyền MỘT đối số, giá trị là null.
```

Sự khác biệt bắt nguồn từ khai báo `Method.invoke(Object obj, Object... args)`: tham số `obj` là **receiver** (đối tượng mà phương thức được gọi trên đó), còn `args` là **danh sách đối số của phương thức đích**. Vì `args` là Java varargs kiểu `Object...` (thực chất `Object[]`), biểu thức `null` ở vị trí này có thể mang hai nghĩa: **mảng đối số `null`** hoặc **một phần tử `null` bên trong mảng đối số**.

Nếu nhầm hai nghĩa, một lời gọi đến phương thức chỉ nhận một tham số tham chiếu có thể phát sinh `IllegalArgumentException` vì Reflection thực tế nhìn thấy **0 đối số**; ngược lại, một phương thức không có tham số có thể bị gọi với **1 đối số thừa**.

Bài học này giải thích chính xác cách Java xử lý varargs ở bên ngoài `Method.invoke`, cách Reflection kiểm tra chữ ký của method đích và các trường hợp với `null`, array, primitive, overload và method khai báo varargs.

## 1. Nhận diện đúng ba tầng của lời gọi

Giả sử có hai phương thức:

```java
public void ping() { /* không có tham số */ }

public void label(String text) { /* có đúng một tham số String */ }
```

Đây là đoạn minh họa nằm trong một class; chương trình chạy độc lập được cung cấp ở phần sau.

**Tầng 1 — Lookup:** phải lấy đúng `Method` theo chữ ký khai báo:

```java
Method ping = Target.class.getMethod("ping");
Method label = Target.class.getMethod("label", String.class);
```

Khi tìm method, `ping` có `getParameterCount() == 0`; `label` có `getParameterCount() == 1`. Giá trị `null` lúc gọi không thay đổi chữ ký này và không khiến Reflection tự chọn một overload khác.

**Tầng 2 — Đóng gói đối số cho `invoke`:** compiler Java xử lý lời gọi đến API `Method.invoke(Object, Object...)`. Đối số sau `target` có thể được đóng gói thành mảng `Object[]`, hoặc một mảng `Object[]` có sẵn có thể được truyền nguyên làm tham số varargs.

**Tầng 3 — Reflection gọi method đích:** `Method.invoke` diễn giải danh sách đối số và so với chữ ký phương thức đích. Với API này, **mảng đối số bằng `null` được xử lý như danh sách không có đối số**. Nhưng mảng `new Object[] { null }` chứa **một** đối số có giá trị `null`.

Vì vậy:

```text
invoke(target)                      -> args: 0 phần tử
invoke(target, new Object[0])       -> args: 0 phần tử
invoke(target, (Object[]) null)     -> args: null -> coi là 0 đối số
invoke(target, (Object) null)       -> args: [null] -> 1 đối số
invoke(target, new Object[]{null})  -> args: [null] -> 1 đối số
```

Đừng nhầm `null` của biến receiver `target` với một đối số `null` của phương thức đích. Chúng thuộc hai vị trí khác nhau trong chữ ký của `Method.invoke`.

## 2. Bảng so sánh lời gọi quan trọng nhất

Giả sử `target` là đối tượng `Target` hợp lệ; `ping` đại diện `void ping()` và `label` đại diện `void label(String text)`.

| Lời gọi Reflection | Số đối số method đích nhìn thấy | Kết quả |
| --- | ---: | --- |
| `ping.invoke(target)` | 0 | Thành công |
| `ping.invoke(target, new Object[0])` | 0 | Thành công |
| `ping.invoke(target, (Object[]) null)` | 0 | Thành công |
| `ping.invoke(target, (Object) null)` | 1 | `IllegalArgumentException` (thừa đối số) |
| `label.invoke(target)` | 0 | `IllegalArgumentException` (thiếu đối số) |
| `label.invoke(target, (Object[]) null)` | 0 | `IllegalArgumentException` (thiếu đối số) |
| `label.invoke(target, (Object) null)` | 1, giá trị `null` | Thành công: `text == null` |
| `label.invoke(target, new Object[] { null })` | 1, giá trị `null` | Thành công: `text == null` |
| `label.invoke(target, (Object) "Java")` | 1, giá trị `"Java"` | Thành công: `text.equals("Java")` |

Bảng trên mô tả số đối số đến **phương thức đích**, không tính receiver `target` là một đối số của method đích.

**Cú pháp rõ ràng nên dùng:** không có đối số → `invoke(target)`; một đối số `null` → `invoke(target, (Object) null)` hoặc `invoke(target, new Object[] { null })`. Khi cần tạo đối số động, nên chủ động tạo mảng `Object[]` với số phần tử khớp chữ ký.

## 3. Vì sao `invoke(target, null)` dễ gây lỗi?

Một trong những lỗi tinh vi là viết:

```java
label.invoke(target, null);
```

Với khai báo `invoke(Object, Object...)`, tham số cuối cùng là `Object[]`. Ở Java, literal `null` tương thích với cả `Object` và `Object[]`, nhưng khi viết lời gọi trên, compiler có thể sử dụng **lời gọi varargs ở dạng truyền thẳng mảng** (fixed-arity invocation) vì `Object[]` là kiểu cụ thể của tham số cuối. Compiler cũng có thể phát cảnh báo tương tự:

```text
non-varargs call for last parameter of varargs method;
cast to Object for a varargs call
cast to Object[] for a non-varargs call
```

Hệ quả là `null` được hiểu thành **mảng `Object[]` bằng `null`**, và đối với `Method.invoke`, nó tương đương với không có đối số. Nếu method đích `label(String)` cần một tham số, Reflection sẽ ném `IllegalArgumentException` trước khi method đích được chạy.

So sánh ba biểu thức:

```java
label.invoke(target, null);             // Mơ hồ với người đọc; thường là 0 đối số.
label.invoke(target, (Object[]) null);  // Rõ ràng là 0 đối số.
label.invoke(target, (Object) null);    // Rõ ràng là 1 đối số null.
```

**Ép kiểu `(Object) null` là cách buộc compiler tạo mảng varargs một phần tử.** Ép kiểu `(Object[]) null` là cách nói rõ rằng toàn bộ mảng varargs bằng `null`. Hai cú pháp không đồng nghĩa.

Đây là quyết định tại **thời điểm biên dịch lời gọi Java tới `Method.invoke`**, chứ không phải thuật toán Reflection cố đoán người viết định truyền gì.

## 4. Ví dụ Java 17+ chạy độc lập

Lưu toàn bộ chương trình sau vào tệp `NullArgumentDemo.java`. Chương trình kiểm tra lời gọi không đối số, một đối số `null`, tham số primitive, tham số mảng và method đích khai báo `String...`.

```java
import java.lang.reflect.Method;

public class NullArgumentDemo {
    public static class Target {
        public void ping() {
            System.out.println("ping: zero");
        }

        public void label(String text) {
            System.out.println("label: "
                    + (text == null ? "<null>" : text));
        }

        public void count(int n) {
            System.out.println("count: " + n);
        }

        public void array(String[] value) {
            System.out.println("array: "
                    + (value == null ? "<null>" : value.length));
        }

        public void join(String... value) {
            System.out.println("join: "
                    + (value == null ? "<null>" : value.length));
        }
    }

    public static void main(String[] args) throws Exception {
        Target target = new Target();

        Method ping = Target.class.getMethod("ping");
        Method label = Target.class.getMethod("label", String.class);
        Method count = Target.class.getMethod("count", int.class);
        Method array = Target.class.getMethod("array", String[].class);
        Method join = Target.class.getMethod("join", String[].class);

        // Ba cách biểu thị lời gọi method không có đối số.
        ping.invoke(target);
        ping.invoke(target, (Object[]) null);
        ping.invoke(target, new Object[0]);

        // Hai cách truyền đúng một giá trị null cho label(String).
        label.invoke(target, (Object) null);
        label.invoke(target, new Object[] {null});

        // Không có đối số -> thiếu tham số String.
        try {
            label.invoke(target, (Object[]) null);
        } catch (IllegalArgumentException e) {
            System.out.println(
                    "label + zero args: IllegalArgumentException");
        }

        // Một đối số null -> thừa tham số với ping().
        try {
            ping.invoke(target, (Object) null);
        } catch (IllegalArgumentException e) {
            System.out.println(
                    "ping + one null: IllegalArgumentException");
        }

        // Một đối số null không hợp lệ với primitive int.
        try {
            count.invoke(target, (Object) null);
        } catch (IllegalArgumentException e) {
            System.out.println(
                    "count + null: IllegalArgumentException");
        }

        // String[] phải được truyền như MỘT đối số.
        array.invoke(target, (Object) new String[] {"A", "B"});
        array.invoke(target, (Object) null);

        // Method đích khai báo varargs vẫn có chữ ký String[].
        System.out.println("join isVarArgs: " + join.isVarArgs());
        join.invoke(target, (Object) new String[] {"A", "B"});

        // Reflection không tự gom hai String thành String[] cho join.
        try {
            join.invoke(target, "A", "B");
        } catch (IllegalArgumentException e) {
            System.out.println(
                    "join + two direct strings: IllegalArgumentException");
        }
    }
}
```

Biên dịch và chạy từ thư mục chứa file:

```bash
javac NullArgumentDemo.java
java NullArgumentDemo
```

Kết quả:

```text
ping: zero
ping: zero
ping: zero
label: <null>
label: <null>
label + zero args: IllegalArgumentException
ping + one null: IllegalArgumentException
count + null: IllegalArgumentException
array: 2
array: <null>
join isVarArgs: true
join: 2
join + two direct strings: IllegalArgumentException
```

Giải thích kết quả:

1. Ba dòng `ping: zero` đến từ danh sách đối số có 0 phần tử: bỏ hẳn varargs, truyền mảng `null`, hoặc truyền mảng rỗng. Cách đầu là dễ đọc nhất.
2. Hai dòng `label: <null>` chứng minh `label(String)` thật sự được gọi, với một đối số tham chiếu có giá trị `null`.
3. `label + zero args` báo lỗi **thiếu đối số**, dù trong mã gọi có xuất hiện từ khóa `null`; vì `(Object[]) null` đại diện cho **cả mảng đối số**, không phải một phần tử.
4. `ping + one null` báo lỗi **thừa đối số** do chữ ký `ping()` không nhận tham số.
5. `count + null` báo lỗi **kiểu đối số**: `int` là primitive, không thể nhận giá trị `null` để unbox. Với `Method.invoke`, lỗi này được báo là `IllegalArgumentException`.
6. `array: 2` chứng minh `String[]` được truyền như **một đối số chứa mảng**. Nếu thiếu ép kiểu `(Object)`, compiler có thể hiểu `String[]` là chính mảng varargs `Object[]` bên ngoài và chia các phần tử thành nhiều đối số.
7. `join.isVarArgs() == true` xác nhận khai báo method đích là `join(String...)`. Tuy nhiên, `Method.invoke` không tự đóng hai đối số `"A", "B"` thành mảng `String[]` của method đích. Phải truyền chính mảng `String[]` như một đối số.

Những kết quả này minh họa hành vi ổn định của Reflection, không phụ thuộc vào việc method đích có body phức tạp hay không.

## 5. Hai loại `null` khác nhau về mặt cấu trúc

Để hiểu rõ điều quan trọng nhất, hãy tưởng tượng các đối số của method đích nằm trong một container:

```java
Object[] noArguments = new Object[0];         // []
Object[] oneNullArgument = new Object[] {null}; // [null]
Object[] nullArray = null;                     // không có mảng
```

Hai mảng đầu **không bằng nhau về độ dài**: `noArguments.length == 0` và `oneNullArgument.length == 1`. Giá trị `nullArray` không có thuộc tính `length`, nhưng API `Method.invoke` **định nghĩa `args == null` tương đương không có đối số**.

Đây là quy tắc **riêng ở tầng Reflection**: không có nghĩa Java tự xem mọi tham số varargs bằng `null` như mảng rỗng trong mọi hàm tự viết. Ví dụ, một hàm bình thường `void f(Object... values)` nếu được gọi bằng `f((Object[]) null)` thì bên trong `f`, biến `values` thực sự bằng `null`; truy cập `values.length` sẽ ném `NullPointerException`. Với `Method.invoke`, việc diễn giải `null` là danh sách đối số trống xảy ra bên trong API này.

Một chương trình muốn biểu diễn hợp đồng số lượng đối số rõ ràng nên ưu tiên:

```java
Object[] zero = {};
Object[] oneNull = {null};

ping.invoke(target, zero);
label.invoke(target, oneNull);
```

Cách này đặc biệt hữu ích khi đối số đến từ parser, router HTTP, JSON hoặc các nguồn dữ liệu động. Mảng chứa giá trị `null` vẫn là **mảng có phần tử**, không được xóa phần tử chỉ vì giá trị của nó là `null`.

## 6. Null của receiver khác null của đối số

Cú pháp Reflection là:

```java
method.invoke(receiver, args...);
```

Với method **instance**:

- `receiver` phải là một đối tượng hợp lệ của class khai báo method (hoặc subtype phù hợp).
- Nếu `receiver == null`, không có đối tượng để gọi instance method và có thể phát sinh `NullPointerException`.
- Nếu `receiver != null` nhưng một đối số của method đích bằng `null`, đây là vấn đề **tương thích tham số**, không phải receiver.

Với method **static**, đối số receiver bị bỏ qua và có thể truyền `null`:

```java
public static void notifyMessage(String message) {
    System.out.println(message == null ? "<null>" : message);
}
```

Đoạn trên là minh họa khai báo method trong một class. Nếu lấy đúng `Method` static:

```java
Method m = Demo.class.getMethod("notifyMessage", String.class);
m.invoke(null, (Object) null);
```

Trong minh họa này, giả định `Demo` là class công khai chứa method `notifyMessage` và đã import `Method`. `null` thứ nhất là **receiver của static method** (được phép), `(Object) null` thứ hai là **một đối số truyền vào method đích**. Nếu chỉ gọi `m.invoke(null)`, Reflection sẽ nhìn thấy **0 đối số** và method đích `notifyMessage(String)` thiếu tham số.

Đừng dùng số lượng literal `null` có mặt trong câu lệnh để suy ra số lượng tham số của method đích. Phải xác định **vị trí** và **kiểu biên dịch** của từng biểu thức.

## 7. Tham số primitive không thể nhận một giá trị null

Một method khai báo:

```java
public void count(int n) {
    System.out.println(n);
}
```

Chữ ký của nó là một tham số `int.class`; Reflection có thể nhận `Integer.valueOf(3)` và unbox thành `int` trong lúc gọi. Nhưng `null` không thể unbox thành `int`:

```java
Method m = Target.class.getMethod("count", int.class);
m.invoke(target, Integer.valueOf(3)); // hợp lệ: Integer -> int
m.invoke(target, (Object) null);      // IllegalArgumentException
```

Đây là **đoạn minh họa với `Target` chứa method `count(int)` và `target` là instance hợp lệ**. Lưu ý sự khác biệt giữa lời gọi trực tiếp `count((Integer) null)`, vốn có thể gây `NullPointerException` ở bước unboxing do compiler sinh ra, và `Method.invoke(target, (Object) null)`, nơi Reflection kiểm tra đối số và ném `IllegalArgumentException`.

Với tham số reference type như `String`, `Integer`, `List<?>`, một phần tử `null` có thể được truyền nếu method đích chấp nhận giá trị đó về mặt logic. Reflection chỉ kiểm tra tính hợp lệ của lời gọi theo chữ ký, không bảo đảm phần thân method sẽ không ném `NullPointerException` khi tự dereference biến tham số.

## 8. Tự kiểm tra

**Câu 1.** Method đích khai báo `void save(String code)`. Lệnh nào truyền **một giá trị `null`**?

```java
saveMethod.invoke(target, (Object) null);
```

Đúng. Nếu dùng `saveMethod.invoke(target, (Object[]) null)`, Reflection diễn giải 0 đối số và báo thiếu.

**Câu 2.** Method đích khai báo `void ping()`. `pingMethod.invoke(target, (Object) null)` có hợp lệ không?

Không. Đây là một đối số dù giá trị của nó bằng `null`; method `ping()` không nhận tham số nào. Dùng `pingMethod.invoke(target)`.

**Câu 3.** Method đích khai báo `void sum(int value)`. Tại sao `sumMethod.invoke(target, (Object) null)` sai?

Vì danh sách đối số có đúng một phần tử, nhưng `null` không thể chuyển thành `int`; lỗi là kiểu đối số, không phải số lượng.

**Câu 4.** Với `void send(String... items)`, `sendMethod.invoke(target, "a", "b")` có tự đóng gói thành `String[]` không?

Không. `Method.invoke` kiểm tra tham số đích là một `String[]`. Phải dùng `sendMethod.invoke(target, (Object) new String[]{"a", "b"})` hoặc mảng ngoài `new Object[]{new String[]{"a","b"}}`.

**Câu 5.** Một method `static void report(String s)` có thể gọi với receiver `null` và tham số `null` không?

Có: `reportMethod.invoke(null, (Object) null)`. `null` ở receiver được bỏ qua với static method, còn `(Object) null` trong danh sách đối số là giá trị truyền cho `s`.

## Ghi nhớ

- **0 đối số:** `method.invoke(target)`, `method.invoke(target, new Object[0])` hoặc `method.invoke(target, (Object[]) null)`.
- **1 đối số có giá trị `null`:** `method.invoke(target, (Object) null)` hoặc `method.invoke(target, new Object[] {null})`.
- **`invoke(target, null)` dễ bị hiểu nhầm:** với tham số varargs `Object[]`, compiler có thể truyền một mảng `null` chứ không phải một phần tử.
- **Mảng cũng là giá trị của một đối số:** dùng `(Object) myArray` nếu method đích có một tham số array.
- **Reflection không chọn lại overload, cũng không tự gom varargs của method đích.** Người gọi phải chọn đúng `Method` và tạo danh sách đối số phù hợp với chữ ký đã khai báo.

Phân biệt rõ **receiver**, **mảng `Object[]` của `Method.invoke`** và **từng phần tử trong mảng đó** sẽ loại bỏ phần lớn nhầm lẫn giữa “không có đối số” và “một đối số `null`” khi sử dụng Java Reflection.