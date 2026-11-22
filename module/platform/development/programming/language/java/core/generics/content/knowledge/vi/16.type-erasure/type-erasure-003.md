# Xóa tham số có giới hạn về giới hạn đứng đầu trong Java Generics

## 1. Vấn đề cần hiểu

Generics cho phép viết một thuật toán làm việc với nhiều kiểu mà vẫn được trình biên dịch kiểm tra kiểu. Ví dụ:

```java
static <T extends Number> int asInt(T value) {
    return value.intValue();
}
```

`T` có **giới hạn trên** (*upper bound*) là `Number`: mọi kiểu dùng làm đối số cho `T` phải phù hợp với `Number`. Nhưng sau khi biên dịch, JVM không có một phiên bản `asInt(Integer)` riêng và một phiên bản `asInt(Double)` riêng. Trình biên dịch Java áp dụng **xóa kiểu** (*type erasure*) để chuyển các khai báo generic sang kiểu có thể biểu diễn trong bytecode.

Quy tắc trọng tâm của bài:

> **Kiểu bị xóa của một tham số kiểu là kiểu bị xóa của giới hạn đứng đầu (leftmost bound) của tham số đó. Nếu không khai báo giới hạn, giới hạn ngầm định là `Object`.**

Vì vậy:

```java
<T>                                   // T bị xóa thành Object
<T extends Number>                    // T bị xóa thành Number
<T extends Number & Comparable<T>>    // T bị xóa thành Number
<T extends Comparable<T> & java.io.Serializable>
                                      // T bị xóa thành Comparable
<T extends Runnable & AutoCloseable>  // T bị xóa thành Runnable
```

Các ví dụ trên là **đoạn chữ ký generic để phân tích**, chưa phải chương trình Java độc lập.

Chú ý sự khác biệt: **giới hạn đầu tiên quyết định kiểu đại diện sau xóa kiểu**; các giới hạn tiếp theo **không biến mất khỏi yêu cầu kiểm tra kiểu của mã nguồn**. Trình biên dịch vẫn biết `T` phải đáp ứng *toàn bộ* những giới hạn đã khai báo.

## 2. Giải nghĩa cú pháp nhiều giới hạn

Một khai báo có thể ràng buộc `T` bằng nhiều kiểu:

```java
<T extends B1 & B2 & B3>
```

Trong đó:

- `T` là biến kiểu (*type variable*), được khai báo cho class, interface, method hoặc constructor.
- `B1` là giới hạn đứng đầu; `B2`, `B3` là các giới hạn bổ sung.
- `extends` ở vị trí này diễn tả điều kiện kiểu con, bao gồm cả **class** và **interface**.
- Dấu `&` nối các giới hạn tạo thành một **giới hạn giao nhau** (*intersection bound*).
- Một kiểu làm đối số cho `T` phải thỏa mãn **tất cả** giới hạn, không phải một trong số đó.

Ví dụ:

```java
<T extends Number & Comparable<T> & java.io.Serializable>
```

Một đối số kiểu hợp lệ vừa phải là subtype của `Number`, vừa phù hợp với `Comparable<T>`, vừa thực thi `Serializable`. `Integer` đáp ứng bộ điều kiện này; `String` thì không phải subtype của `Number`.

Quy tắc sắp xếp cú pháp:

1. Nếu có giới hạn là **class**, nó phải đứng **đầu tiên**.
2. Sau giới hạn class có thể là các giới hạn interface.
3. Không thể dùng hai class độc lập làm hai giới hạn class trong một danh sách `&`.
4. Nếu chỉ có interface, interface đứng đầu do người viết khai báo sẽ quyết định erasure.
5. Các kiểu trong danh sách giới hạn cũng chịu các ràng buộc hợp lệ của Java, chẳng hạn không được chứa các giới hạn có cùng erasure theo cách bị JLS cấm.

Ví dụ hợp lệ:

```java
<T extends Number & Comparable<T>>
<T extends Runnable & AutoCloseable>
<T extends AutoCloseable & Runnable>
```

Ví dụ **không hợp lệ**:

```java
<T extends Comparable<T> & Number> // Number là class nhưng không đứng đầu
<T extends Number & Thread>        // Có hai class: Number và Thread
```

Hai ví dụ không hợp lệ chỉ nhằm minh họa lỗi cú pháp/giới hạn; không đưa chúng vào chương trình cần biên dịch.

## 3. Quy tắc erasure chính xác

Theo mô hình của Java Language Specification, khi xóa một biến kiểu `T`, trình biên dịch lấy **erasure của giới hạn đứng đầu** của `T`. Có hai bước tư duy:

1. Xác định giới hạn đầu tiên của `T`. Nếu `<T>` không có `extends`, coi giới hạn là `Object`.
2. Xóa kiểu của giới hạn đầu tiên. Nếu giới hạn đó đã là class/interface không tham số hóa, tên kiểu giữ nguyên; nếu nó là kiểu tham số hóa, các đối số generic của chính giới hạn đó cũng bị xóa.

Bảng đối chiếu:

| Khai báo | Giới hạn đầu tiên | Erasure của `T` | Điều kiện thêm vẫn được kiểm tra ở mã nguồn |
|---|---|---|---|
| `<T>` | `Object` ngầm định | `Object` | Không có |
| `<T extends Object>` | `Object` | `Object` | Không có |
| `<T extends Number>` | `Number` | `Number` | Không có |
| `<T extends Number & Comparable<T>>` | `Number` | `Number` | `Comparable<T>` |
| `<T extends Comparable<T> & java.io.Serializable>` | `Comparable<T>` | `Comparable` | `Serializable` |
| `<T extends Runnable & AutoCloseable>` | `Runnable` | `Runnable` | `AutoCloseable` |
| `<T extends java.util.List<String> & java.util.RandomAccess>` | `List<String>` | `List` | `RandomAccess` |

Dòng `List<String>` cho thấy một điểm dễ bỏ qua: erasure không giữ đối số `<String>`. Đó là lý do `T` cuối cùng có kiểu đại diện là `java.util.List`, không phải `List<String>` theo nghĩa bytecode descriptor thông thường.

**Không được hiểu** quy tắc là "`T` trở thành `Object` trong mọi trường hợp". Điều đó chỉ đúng với type parameter không có giới hạn hoặc có erasure của giới hạn đầu là `Object`.

### Phạm vi áp dụng

Quy tắc này áp dụng cho **biến kiểu** ở nhiều vị trí:

```java
class Holder<T extends Number & Comparable<T>> {
    T value;

    T get() {
        return value;
    }

    void set(T newValue) {
        value = newValue;
    }
}
```

Đây là đoạn class hợp lệ; không có phương thức `main`, nên chưa phải chương trình tự chạy. Trong mô tả kiểu ở bytecode, trường `value`, tham số `set` và kết quả `get` dùng kiểu đại diện `Number`. Thông tin generic như `T` và các bound có thể được giữ trong thuộc tính `Signature` để công cụ và reflection đọc, nhưng đó **không phải** cơ chế JVM tạo nhiều class cho nhiều giá trị `T`.

## 4. Ví dụ chạy được: class đầu tiên và interface bổ sung

Tạo tệp `LeftmostBoundDemo.java`:

```java
public class LeftmostBoundDemo {

    static <T extends Number & Comparable<T>> String compare(T left, T right) {
        int first = left.intValue();
        int second = right.intValue();
        boolean greater = left.compareTo(right) > 0;
        return first + " vs " + second + " => " + greater;
    }

    static <T extends Runnable & AutoCloseable> void execute(T task)
            throws Exception {
        task.run();
        task.close();
    }

    static final class Task implements Runnable, AutoCloseable {
        @Override
        public void run() {
            System.out.println("run");
        }

        @Override
        public void close() {
            System.out.println("close");
        }
    }

    public static void main(String[] args) throws Exception {
        System.out.println(compare(9, 4));
        execute(new Task());
    }
}
```

Biên dịch và chạy với Java 17 trở lên:

```bash
javac LeftmostBoundDemo.java
java LeftmostBoundDemo
```

Stdout:

```text
9 vs 4 => true
run
close
```

### Phân tích `compare`

```java
static <T extends Number & Comparable<T>> String compare(T left, T right)
```

- Giới hạn đứng đầu của `T` là `Number`.
- `T` bị xóa thành `Number`.
- Hai tham số của phương thức sau erasure được biểu diễn bằng `Number`.
- `intValue()` có trên `Number`, nên việc gọi thành viên này khớp trực tiếp với khả năng do giới hạn đầu cung cấp.
- `compareTo(T)` đến từ `Comparable<T>`, là **giới hạn thứ hai**. Dù `Number` không tự khai báo `compareTo`, lời gọi vẫn hợp lệ ở mã nguồn nhờ compiler kiểm tra đầy đủ các bound.

Để thực hiện lời gọi tới một phương thức của giới hạn bổ sung trong bytecode, compiler có thể chèn phép ép kiểu tới interface thích hợp (ở ví dụ này là `Comparable`) trước khi gọi phương thức trên interface. Việc xóa `T` thành `Number` **không làm lời gọi `compareTo` bị cấm**.

### Phân tích `execute`

```java
static <T extends Runnable & AutoCloseable> void execute(T task)
```

Cả `Runnable` lẫn `AutoCloseable` đều là interface. Vì `Runnable` đứng đầu, erasure của `T` là `Runnable`; compiler vẫn kiểm tra `task.close()` nhờ giới hạn thứ hai là `AutoCloseable`. Tương tự, có thể xuất hiện ép kiểu ở bytecode trước khi gọi `close()`.

Lời gọi `execute(new Task())` chỉ hợp lệ vì `Task` triển khai **cả hai** interface. Một đối tượng chỉ triển khai `Runnable` mà không triển khai `AutoCloseable` sẽ không đáp ứng giới hạn của phương thức.

Lưu ý riêng về ví dụ: phương thức dùng `run()` và `close()` theo thứ tự để minh họa hai giới hạn. Nếu `run()` ném exception thì `close()` trong ví dụ chưa chắc được gọi; trong mã quản lý tài nguyên thực tế, hãy thiết kế xử lý lỗi và đóng tài nguyên phù hợp, chẳng hạn `try/finally` hoặc `try-with-resources` khi áp dụng được.

## 5. Quan sát kiểu đã xóa bằng `javap`

JDK có công cụ `javap` để xem chữ ký và bytecode. Sau khi biên dịch tệp `LeftmostBoundDemo.java`, chạy:

```bash
javap -p -s LeftmostBoundDemo
```

Tập trung vào hai descriptor của các phương thức (trích riêng phần liên quan, không phải toàn bộ đầu ra `javap`):

```text
compare(java.lang.Number, java.lang.Number)
  descriptor: (Ljava/lang/Number;Ljava/lang/Number;)Ljava/lang/String;

execute(java.lang.Runnable)
  descriptor: (Ljava/lang/Runnable;)V
```

Vì `compare` trả về `String` nên kiểu trả về trong descriptor là `String`. `execute` là `void` nên descriptor kết thúc bằng `V`. Các descriptor này cho thấy giới hạn đứng đầu quyết định kiểu của vị trí có biến kiểu `T` trong chữ ký đã xóa.

Để quan sát lời gọi thực thi và cast do trình biên dịch sinh, dùng:

```bash
javap -p -c LeftmostBoundDemo
```

Kết quả chi tiết có offset lệnh và constant-pool index phụ thuộc bản JDK/biên dịch. Những điểm quan trọng cần tìm gồm:

- Lời gọi `Number.intValue()` từ giới hạn đầu tiên.
- Phép chuyển phù hợp sang `Comparable` và lời gọi `Comparable.compareTo(...)` khi dùng giới hạn bổ sung.
- Lời gọi `Runnable.run()` và thao tác với `AutoCloseable.close()` trong `execute`.

Không nên học thuộc offset bytecode; hãy so sánh **descriptor** và **kiểu chủ sở hữu của lời gọi**. Điều đó giải thích được cả kết quả compile time lẫn cách JVM thi hành chương trình.

## 6. Nếu giới hạn đầu tiên là interface

Giả sử một phương thức cần tham số vừa có khả năng so sánh, vừa serializable:

```java
static <T extends Comparable<T> & java.io.Serializable> T choose(T a, T b) {
    return a.compareTo(b) >= 0 ? a : b;
}
```

Đây là một **đoạn phương thức**, cần đặt bên trong class nếu muốn biên dịch. Ở đây:

- Giới hạn đầu tiên là `Comparable<T>`, một interface tham số hóa.
- Erasure của `Comparable<T>` là interface raw `Comparable`.
- Do đó erasure của biến kiểu `T` là `Comparable`.
- Các vị trí kiểu `T` trong descriptor phương thức dùng `Comparable`.
- `Serializable` vẫn là yêu cầu bắt buộc đối với đối số kiểu ở thời điểm biên dịch.

Chữ ký đã xóa tương ứng về mặt descriptor:

```text
(Ljava/lang/Comparable;Ljava/lang/Comparable;)Ljava/lang/Comparable;
```

**Thứ tự interface có ý nghĩa đối với erasure.** Nếu về mặt cú pháp hai khai báo sau đều hợp lệ:

```java
<T extends Runnable & AutoCloseable>
<T extends AutoCloseable & Runnable>
```

thì trường hợp đầu xóa `T` về `Runnable`, còn trường hợp sau xóa `T` về `AutoCloseable`. Tập điều kiện cần thỏa ở mã nguồn có thể giống nhau, nhưng **kiểu đại diện trong chữ ký đã xóa** lại khác.

### Vì sao không đổi thứ tự cho đẹp?

Nếu khai báo generic xuất hiện trong API công khai và bạn đổi vị trí các interface trong danh sách giới hạn, descriptor của field/method dùng biến kiểu có thể đổi. Việc này có thể ảnh hưởng tới tương thích nhị phân của thư viện, các class đã biên dịch trước đó, và cách tạo bridge method.

Vì thế, thứ tự bound không chỉ là lựa chọn trình bày. Khi thiết kế API, hãy chọn giới hạn đầu tiên có chủ đích, đặc biệt nếu class/interface được sử dụng bởi module khác hoặc xuất bản thành thư viện.

## 7. Giới hạn class bắt buộc đứng trước interface

Ví dụ:

```java
static <T extends Number & Comparable<T> & java.io.Serializable>
T pick(T first, T second) {
    return first.compareTo(second) >= 0 ? first : second;
}
```

Với `<T extends Number & ...>`, `Number` là class bound và bắt buộc đứng đầu. Bạn **không thể** thay đổi thứ tự thành `<T extends Comparable<T> & Number>` để ép erasure của `T` chuyển sang `Comparable`; Java sẽ từ chối khai báo vì giới hạn class đứng sai vị trí.

Nếu thực sự không cần thành viên của `Number`, bạn có thể thiết kế một API khác chỉ dựa trên interface:

```java
static <T extends Comparable<T> & java.io.Serializable>
T pickComparable(T first, T second) {
    return first.compareTo(second) >= 0 ? first : second;
}
```

Việc bỏ `Number` làm thay đổi **hợp đồng đầu vào**: phương thức bây giờ có thể chấp nhận những kiểu non-number thỏa hai interface, ví dụ `String`. Đây là thay đổi thiết kế API, không đơn thuần là thay đổi erasure.

## 8. Erasure ảnh hưởng phương thức, field và overload như thế nào?

### Trường, tham số, kết quả

Xét class:

```java
class NumberHolder<T extends Number & Comparable<T>> {
    T item;

    NumberHolder(T item) {
        this.item = item;
    }

    T get() {
        return item;
    }
}
```

Khi xóa kiểu, các chỗ dùng `T` liên quan được biểu diễn bằng `Number`:

```java
// Mô hình minh họa kết quả sau erasure; không phải mã Java do
// javac trực tiếp in ra và không thay thế class generic ban đầu.
class NumberHolderErasedModel {
    Number item;

    NumberHolderErasedModel(Number item) {
        this.item = item;
    }

    Number get() {
        return item;
    }
}
```

Đây là **hai class khác nhau nhằm so sánh**, không phải yêu cầu tạo hai tệp khi sử dụng `NumberHolder`. Compiler/JVM thực sự dùng mô tả kiểu đã xóa trong bytecode, đồng thời compiler có thể tạo cast và các phương thức cầu nối nếu cần để duy trì hành vi generic.

Khi gọi:

```java
NumberHolder<Integer> holder = new NumberHolder<>(12);
Integer value = holder.get();
```

Mã nguồn trên có kiểu kết quả `Integer` đã được kiểm tra; ở bytecode, nếu cần, compiler có thể chèn cast từ `Number` về `Integer` tại nơi nhận. Không có hai bản runtime khác nhau cho `NumberHolder<Integer>` và `NumberHolder<Double>`.

### Không thể overload nếu chữ ký sau xóa bị trùng

Ví dụ **sai**, chỉ dùng để phân tích lỗi compile time:

```java
class BadOverload {
    static <T extends Number & Comparable<T>> void log(T value) {}

    static void log(Number value) {} // name clash vì cùng erasure
}
```

Ở phương thức đầu, `T` bị xóa thành `Number`. Hai lời khai báo sẽ có cùng tên `log` và cùng danh sách tham số sau erasure, nên không thể tồn tại như hai overload hợp lệ trong cùng class. Trình biên dịch sẽ báo lỗi trùng tên/chữ ký (*name clash*).

Cách khắc phục tùy mục tiêu: dùng tên phương thức khác, thống nhất thành một phương thức generic, hoặc thay đổi hợp đồng tham số theo cách tạo ra chữ ký thực sự khác biệt. Đừng kỳ vọng hai bound khác nhau hoặc hai đối số generic khác nhau luôn đủ để overload.

### Xóa kiểu khác với overload resolution ở mã nguồn

Compiler trước tiên kiểm tra tính hợp lệ và phân giải lời gọi theo hệ thống kiểu Java; erasure phục vụ việc sinh bytecode và duy trì mô hình tương thích. Không nên suy luận "mọi biến kiểu đã là `Number` ngay từ đầu" trong khi đọc chương trình Java nguồn. Ở nguồn, compiler vẫn biết `T` cùng một kiểu ở hai tham số và phải đáp ứng toàn bộ các bound.

## 9. Bridge method: giữ đúng hành vi override sau erasure

Một hệ quả đáng học là phương thức **cầu nối** (*bridge method*). Hãy tạo tệp `LeftmostBridgeDemo.java`:

```java
public class LeftmostBridgeDemo {

    static class Store<T extends Number & Comparable<T>> {
        T next(T value) {
            return value;
        }
    }

    static final class IntegerStore extends Store<Integer> {
        @Override
        Integer next(Integer value) {
            return value + 1;
        }
    }

    public static void main(String[] args) {
        Store<Integer> store = new IntegerStore();
        System.out.println(store.next(10));

        @SuppressWarnings("rawtypes")
        Store rawStore = new IntegerStore();

        try {
            rawStore.next(2.5);
        } catch (ClassCastException ex) {
            System.out.println("ClassCastException");
        }
    }
}
```

Biên dịch và chạy:

```bash
javac LeftmostBridgeDemo.java
java LeftmostBridgeDemo
```

Stdout:

```text
11
ClassCastException
```

`Store<T>.next(T)` có erasure tương ứng với `Number next(Number)`, vì `Number` là giới hạn đầu tiên. Trong khi đó, `IntegerStore.next(Integer)` nhận và trả `Integer`. Để lời gọi qua biến kiểu `Store<Integer>` vẫn dispatch đến override của `IntegerStore`, `javac` có thể sinh ra trong class con một bridge method ở cấp bytecode, có chữ ký tương thích với `next(Number)`; bridge này thực hiện cast phù hợp rồi gọi `next(Integer)`.

Có thể quan sát thông tin class con bằng:

```bash
javap -p -s 'LeftmostBridgeDemo$IntegerStore'
javap -p -v 'LeftmostBridgeDemo$IntegerStore'
```

Dùng dấu nháy đơn quanh tên nested class để ký tự `$` được giữ nguyên trong shell thường gặp (bao gồm PowerShell và bash). Trong dữ liệu được in ra, tìm hai phương thức `next` có descriptor tương ứng với `Integer` và `Number`; bản bridge được đánh dấu `ACC_BRIDGE` và `ACC_SYNTHETIC`.

`rawStore` là **raw type** và cố ý bỏ qua tham số generic để minh họa giới hạn an toàn kiểu khi trộn code cũ. Ở lời gọi `rawStore.next(2.5)`, đối số `Double` vẫn thuộc `Number`, nên có thể đi qua chữ ký đã xóa `next(Number)`. Nhưng bridge của `IntegerStore` cần chuyển đối số thành `Integer`; cast thất bại và ném `ClassCastException`. Phần này là tình huống cần **tránh** trong ứng dụng bình thường, không phải cách khuyến nghị sử dụng generic.

Thông báo biên dịch về raw/unchecked có thể xuất hiện khi thêm tùy chọn lint, nhưng chương trình vẫn được biên dịch với cú pháp trên. Không nên nuốt `ClassCastException` trong business logic; đây chỉ là phần minh họa có kiểm soát.

## 10. Có phải mọi giới hạn phía sau đều bị loại bỏ hoàn toàn?

Không. Cần phân biệt ba góc nhìn.

### Góc nhìn 1: hệ thống kiểu ở mã nguồn

Với:

```java
<T extends Number & Comparable<T>>
```

Compiler biết `T` có hành vi từ `Number` **và** `Comparable<T>`. Nó từ chối một đối số kiểu không thỏa cả hai. Erasure dùng `Number` làm kiểu đại diện không làm việc kiểm tra `Comparable<T>` bị hủy bỏ.

### Góc nhìn 2: mô tả kiểu JVM và mã máy ảo

Đối với các vị trí kiểu `T` trong field descriptor hoặc method descriptor, JVM thấy kiểu bị xóa theo bound đứng đầu. Các lệnh cần thực thi qua giới hạn phụ có thể bao gồm `checkcast` tương ứng. Tại nơi kiểu generic được chuyên biệt hóa, compiler có thể sinh thêm cast và bridge method.

Đây không phải phép biến đổi có thể thực hiện chính xác bằng cách xóa một vài chuỗi `<...>` trong mã nguồn. Erasure của Java là một cơ chế biên dịch có quy tắc cho type variables, parameterized types, arrays, method signatures, override và các phép chuyển kiểu cần thiết.

### Góc nhìn 3: metadata generic và reflection

Thông tin generic khai báo vẫn có thể được lưu vào classfile, ví dụ thuộc tính `Signature`. Reflection như `TypeVariable.getBounds()` có khả năng trả về danh sách giới hạn đã khai báo, theo thứ tự. Việc thấy metadata đó **không có nghĩa** JVM lưu đầy đủ đối số kiểu runtime cho mỗi instance generic.

Ví dụ độc lập trong tệp `BoundsReflectionDemo.java`:

```java
import java.lang.reflect.Type;
import java.lang.reflect.TypeVariable;

public class BoundsReflectionDemo {

    static class Sample<T extends Number & Comparable<T>> {}

    public static void main(String[] args) {
        TypeVariable<?> type = Sample.class.getTypeParameters()[0];
        System.out.println(type.getName());
        for (Type bound : type.getBounds()) {
            System.out.println(bound.getTypeName());
        }
    }
}
```

Biên dịch và chạy:

```bash
javac BoundsReflectionDemo.java
java BoundsReflectionDemo
```

Stdout trên JDK 17+ thông dụng:

```text
T
java.lang.Number
java.lang.Comparable<T>
```

Metadata cho biết `T` khai báo **hai** bound; quy tắc erasure vẫn chọn bound đầu là `Number`. Chỉ nhìn `getBounds()` không chứng minh một instance cụ thể của `Sample<Integer>` còn giữ được `Integer` làm đối số runtime. Bạn cũng không thể viết `new T()` hoặc `T.class` trong mã generic thông thường.

## 11. Mối liên hệ với `Comparable` và generic API

Một mẫu thường gặp khi làm thuật toán so sánh:

```java
static <T extends Comparable<? super T>> T greater(T first, T second) {
    return first.compareTo(second) >= 0 ? first : second;
}
```

Ở đây giới hạn đầu tiên là `Comparable<? super T>`, nên erasure của `T` là **raw `Comparable`**. `? super T` mở rộng khả năng chấp nhận một kiểu mà phép so sánh được định nghĩa trên một supertype của `T`, đồng thời không thay đổi quy tắc erasure của biến kiểu `T`.

Chữ ký khác:

```java
static <T extends Number & Comparable<? super T>>
T greaterNumber(T first, T second) {
    return first.compareTo(second) >= 0 ? first : second;
}
```

Ở đây giới hạn đầu tiên là `Number`, nên erasure của `T` là **`Number`**, mặc dù chính thao tác so sánh được cung cấp bởi giới hạn thứ hai. Đây là hai hợp đồng generic khác nhau.

Đối với các thuật toán tổng quát, không nên chọn bound đầu dựa trên mong muốn làm descriptor ngắn hơn. Hãy chọn các điều kiện đúng cho miền đầu vào của API; trong những giới hạn mà Java cho phép sắp xếp, quan tâm đến việc giữ ổn định thứ tự nếu API đã được phát hành.

## 12. Các nhầm lẫn thường gặp

**Nhầm lẫn 1 — "Bound cuối cùng quyết định erasure."** Sai. Với `<T extends Number & Comparable<T>>`, erasure của `T` là `Number`. Toàn bộ các bound được kiểm tra tại compile time, nhưng **bound đứng đầu** quyết định kiểu đại diện khi xóa.

**Nhầm lẫn 2 — "Các interface sau dấu `&` không còn dùng được."** Sai. Chương trình `LeftmostBoundDemo` đã gọi được cả `compareTo` và `close` từ giới hạn phụ. Compiler có thể tạo cast ở bytecode để truy cập interface phù hợp.

**Nhầm lẫn 3 — "Giới hạn đầu tiên luôn phải là class."** Sai. Nếu không có class bound, một interface có thể đứng đầu. Ví dụ `<T extends Runnable & AutoCloseable>` có erasure `Runnable`.

**Nhầm lẫn 4 — "Đổi thứ tự giới hạn không bao giờ ảnh hưởng thư viện."** Sai. Với các interface, đổi bound đầu tiên có thể thay đổi field/method descriptor hoặc cầu nối liên quan. Nếu class/method công khai đã được các binary khác dùng, phải đánh giá tương thích nhị phân trước khi sửa.

**Nhầm lẫn 5 — "Type erasure xảy ra trước nên compiler không biết các bound khác."** Sai. Compiler phân tích và kiểm tra hệ thống kiểu generic, rồi tạo bytecode theo erasure. Các phép cast cần thiết có thể được chèn trong quá trình sinh mã.

**Nhầm lẫn 6 — "Mọi generic đều xóa thành `Object`."** Sai. `<T>` thường xóa về `Object`, nhưng `<T extends Number>` xóa về `Number`, và `<T extends Comparable<T>>` xóa về `Comparable`.

**Nhầm lẫn 7 — "Generic metadata có nghĩa type arguments tồn tại riêng cho từng instance ở runtime."** Sai. Có thể đọc bound được khai báo của class/method bằng reflection, nhưng đối số kiểu của một instance thông thường không được tái hiện đầy đủ chỉ vì có metadata generic.

**Nhầm lẫn 8 — "Giới hạn `<T extends Number & Comparable<T>>` tương đương hai overload."** Sai. Đây là một phương thức generic có một biến kiểu phải đáp ứng cả hai ràng buộc; compiler không tạo một overload riêng cho `Number` và một overload riêng cho `Comparable`.

## 13. Các bước kiểm tra một chữ ký generic

Khi cần dự đoán erasure của một API:

1. Tìm phần khai báo tham số kiểu, ví dụ `<T extends Number & Comparable<T>>`.
2. Xác định **giới hạn đứng đầu**: ở đây là `Number`.
3. Xóa chính kiểu giới hạn đầu nếu nó có đối số generic, ví dụ `List<String>` thành `List`.
4. Thay các vị trí dùng biến kiểu `T` trong descriptor bằng kiểu đã xóa tương ứng.
5. Kiểm tra các giới hạn còn lại để hiểu vì sao phương thức nguồn có thể gọi thành viên của chúng.
6. Nếu có override với đối số kiểu cụ thể, xem khả năng sinh bridge method.
7. Nếu có overload, kiểm tra va chạm chữ ký sau erasure.
8. Nếu API công khai thay đổi thứ tự bound, đánh giá tương thích với client đã biên dịch.

Ví dụ tự luyện:

**Tình huống A**

```java
<T extends java.util.List<String> & java.util.RandomAccess>
```

Đáp án: giới hạn đầu là `List<String>`, erasure của `T` là `java.util.List`. `RandomAccess` vẫn là yêu cầu đối với đối số kiểu.

**Tình huống B**

```java
<T extends AutoCloseable & Runnable>
```

Đáp án: erasure của `T` là `AutoCloseable`. Nếu đảo thứ tự thành `Runnable & AutoCloseable`, erasure đổi sang `Runnable`.

**Tình huống C**

```java
<T extends Object & Runnable>
```

Đáp án: erasure của `T` là `Object`, dù trong mã nguồn `T` cũng phải triển khai `Runnable`. Đây là một ví dụ cho thấy chọn `Object` làm bound đầu tiên có thể tạo khác biệt về descriptor so với `<T extends Runnable>`.

**Tình huống D**

```java
<T extends Number & java.io.Serializable>
```

Đáp án: erasure của `T` là `Number`. `Serializable` là điều kiện bổ sung; nó không ghi đè giới hạn đầu tiên.

**Tình huống E**

```java
<T extends Comparable<T> & java.io.Serializable>
```

Đáp án: erasure của `T` là raw `Comparable`. Phần `<T>` bên trong `Comparable<T>` cũng bị xóa khỏi biểu diễn descriptor.

## 14. Ghi nhớ và tài liệu đối chiếu

Mệnh đề cần ghi nhớ là **erasure của type variable dựa vào erasure của bound đứng đầu**. Nếu không viết bound, `Object` là giới hạn ngầm định. Class bound, nếu có, luôn đứng trước các interface; nếu chỉ có interface, interface đứng đầu quyết định kiểu đại diện. Các bound tiếp theo vẫn có hiệu lực đối với kiểm tra kiểu ở mã nguồn.

Từ quy tắc nhỏ này có các hệ quả rất thực tế: field/method descriptor dùng kiểu đã xóa, compiler có thể chèn cast để dùng interface bổ sung, phương thức override có thể cần bridge method, và hai overload có thể bị từ chối vì trùng chữ ký sau erasure. Khi thiết kế thư viện, hãy coi thứ tự các giới hạn là một phần của chữ ký có thể tác động đến tương thích nhị phân.

Tài liệu chuẩn để tra cứu thêm:

- [Java Language Specification, §4.4 — Type Variables](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.4): cú pháp, tính hợp lệ và ý nghĩa của các bound.
- [Java Language Specification, §4.6 — Type Erasure](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.6): quy tắc erasure của parameterized type, type variable và method signature.
- [Java Language Specification, §8.4.8.3 — Requirements in Overriding and Hiding](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.4.8.3): các quy tắc liên quan tới override và name clash.
- Công cụ `javap` của JDK: dùng `-s` để kiểm tra descriptor, `-c` để xem bytecode và `-v` để xem metadata như `Signature` hoặc cờ bridge method.