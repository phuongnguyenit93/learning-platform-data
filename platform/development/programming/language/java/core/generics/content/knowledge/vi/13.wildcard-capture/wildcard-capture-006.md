# Giới hạn trên và dưới của kiểu được bắt giữ (wildcard capture) trong Java Generics

**Wildcard capture** (*bắt giữ wildcard*) là cơ chế của trình biên dịch Java: khi gặp một kiểu generic chứa `?`, compiler có thể thay đối số kiểu chưa biết bằng **một biến kiểu tạm thời, riêng biệt**. Biến kiểu đó thường xuất hiện trong thông báo lỗi dưới tên như `CAP#1` hoặc `capture of ? extends Number`. Dù ta không thể viết trực tiếp tên `CAP#1` trong mã nguồn, compiler vẫn dùng các **giới hạn trên và dưới** (*upper bound* và *lower bound*) của nó để quyết định phép đọc, ghi, gán và gọi phương thức có an toàn hay không.

Tóm tắt với `List<E>`, nơi `E` không khai báo cận đặc biệt (cận trên mặc định là `Object`):

| Đối số wildcard | Kiểu được bắt giữ: cận trên | Cận dưới | Đọc từ `get` dưới kiểu nào? | Có thể thêm loại giá trị nào? |
| --- | --- | --- | --- | --- |
| `?` | `Object` | Kiểu `null` | `Object` | Chỉ literal `null` về mặt hệ kiểu |
| `? extends Number` | `Number` | Kiểu `null` | `Number` | Chỉ literal `null` về mặt hệ kiểu |
| `? super Integer` | `Object` | `Integer` | `Object` | `Integer` và những kiểu con phù hợp |
| `? super Number` | `Object` | `Number` | `Object` | `Number` và các kiểu con |

Bảng thể hiện **bảo đảm tĩnh của hệ kiểu**, không cam kết collection ở runtime hỗ trợ sửa đổi hoặc chấp nhận `null`. Với generic có tham số kiểu tự khai báo cận trên, ví dụ `Box<T extends Number>`, cận trên của kiểu được capture có thể là `Number` thay vì `Object`; phần này được giải thích chi tiết ở dưới.

## 1. Vì sao phải bắt giữ wildcard?

Xét:

```java
List<? extends Number> numbers = List.of(1, 2);
Number number = numbers.get(0);
```

Đối số kiểu thực tế của danh sách có thể là `Integer`, `Double`, `Number` hoặc một kiểu con khác của `Number`. Compiler không biết chính xác, nhưng cần lý giải **một kiểu nhất quán** cho các phần tử của cùng danh sách.

Có thể hình dung compiler tạm đặt tên cho kiểu phần tử ấy:

```text
List<? extends Number>
          |
          v
List<CAP#1>
  với CAP#1 <: Number
```

Ký hiệu `CAP#1` chỉ để diễn giải. Không tồn tại cú pháp khai báo `class CAP#1` hay `List<CAP#1>` hợp lệ trong chương trình Java thông thường.

Vì kiểu được capture nằm dưới `Number`, kết quả `numbers.get(0)` luôn có thể xem là `Number`. Nhưng compiler không thể tự giả định `CAP#1` chính là `Integer`:

```java
Number n = numbers.get(0);  // Đúng.
// Integer i = numbers.get(0); // Không biên dịch.
// numbers.add(42);           // Không biên dịch.
```

Nếu danh sách thật là `List<Double>`, việc thêm một `Integer` sẽ phá hợp đồng kiểu phần tử. Bắt giữ wildcard giúp compiler giữ được thông tin quan hệ kiểu mà không đoán đối số kiểu thực tế.

## 2. Cận trên và cận dưới của một biến kiểu được capture

Về trực giác, một biến kiểu được bắt giữ `CAP` có thể bị ràng buộc hai phía:

```text
UpperBound
     ^
     | CAP <: UpperBound
    CAP
     ^
     | LowerBound <: CAP
LowerBound
```

Ký hiệu `A <: B` có nghĩa `A` là kiểu con của `B` theo quan hệ kiểu Java. Khi biết cận trên, ta biết giá trị có kiểu `CAP` có thể **đọc ra** và xem như kiểu cận trên. Khi biết cận dưới, ta có thể **đưa vào** giá trị của kiểu cận dưới, vì mọi kiểu `CAP` hợp lệ đều phải là kiểu cha của cận dưới đó.

Hai giới hạn khác nhau về tác dụng:

- **Cận trên (`upper bound`):** một đối tượng có kiểu `CAP` có thể được chuyển lên kiểu này, nên giúp xác định những API có thể gọi khi đọc.
- **Cận dưới (`lower bound`):** kiểu này và các kiểu con phù hợp có thể được đưa vào vị trí cần `CAP`, nên giúp kiểm tra những giá trị có thể ghi.
- **Cả hai cận không xác định một class runtime cố định.** Capture được dùng trong phân tích kiểu khi biên dịch, không tạo một class mới.

Java còn có **kiểu `null`** đặc biệt. Trong cách mô tả quy tắc capture của ngôn ngữ, đây là cận dưới của `?` và `? extends B`. Nó giải thích vì sao literal `null` có thể được truyền vào nơi yêu cầu một kiểu tham chiếu capture, nhưng không hứa collection chấp nhận giá trị ấy khi chạy.

Không nên hiểu “cận dưới là kiểu `null`” là mọi phần tử đang tồn tại đều `null`, hoặc cận trên `Number` nghĩa mọi giá trị luôn khác `null`. Đó là hai kết luận sai.

## 3. Capture của `? extends Number`: cận trên mạnh, cận dưới yếu

Với `List<? extends Number>`:

- `CAP` có **cận trên `Number`** (trong trường hợp đơn giản này);
- cận dưới là kiểu `null`;
- compiler cho đọc ra như `Number`;
- compiler không cho thêm một `Integer`, `Double` hoặc `Number` cụ thể tùy ý.

Ví dụ:

```java
static void readSource(List<? extends Number> source) {
    for (Number value : source) {
        System.out.println(value);
    }

    // source.add(1);           // Không biên dịch.
    // source.add(1.5);         // Không biên dịch.
    // source.add((Number) 3);  // Không biên dịch.
    source.add(null);           // Hợp lệ về kiểu; có thể lỗi ở runtime.
}
```

Trong `source.add(1)`, `Integer` chỉ được biết là kiểu con của `Number`, không được chứng minh là kiểu con của chính `CAP`. Có thể nguồn là `List<Double>` nên phép thêm không an toàn.

Cận dưới kiểu `null` giải thích vì sao `source.add(null)` được chấp nhận bởi compiler. Nhưng nếu `source` thực sự là danh sách không sửa đổi của `List.of(...)` thì `add(null)` vẫn ném `UnsupportedOperationException`; nếu implementation cấm `null` thì có thể ném `NullPointerException`. Các điều kiện runtime độc lập với wildcard capture.

Một ví dụ thường gặp: `? extends Number` là **producer** trong nguyên tắc PECS (*Producer Extends, Consumer Super*). Nó phù hợp khi ta cần lấy giá trị dưới kiểu `Number`, không cần thêm một đối tượng `Number` mới qua tham chiếu wildcard.

## 4. Capture của `? super Integer`: cận dưới mạnh, cận trên tùy khai báo

Với `List<? super Integer>`:

- `CAP` có **cận dưới `Integer`**;
- cận trên mặc định là `Object` vì tham số `E` của `List<E>` không có cận chặt hơn;
- compiler cho thêm `Integer`;
- compiler chỉ bảo đảm khi đọc nhận được `Object`.

Ví dụ:

```java
static void writeDestination(List<? super Integer> destination) {
    destination.add(10); // Hợp lệ.
    destination.add(20); // Hợp lệ.

    // destination.add(2.5); // Không biên dịch.

    Object value = destination.get(0); // Hợp lệ.
    // Integer n = destination.get(0); // Không biên dịch.
}
```

Lý do: `destination` có thể là `List<Integer>`, `List<Number>`, `List<Object>`, thậm chí `List<java.io.Serializable>`. Mọi danh sách này nhận `Integer`, nhưng một `List<Object>` có thể chứa sẵn `String`. Vì thế không thể coi mỗi phần tử đọc ra là `Integer` hoặc `Number`.

Điều này tạo ra mô hình hai chiều cần nhớ:

```text
? extends Number                 ? super Integer
-----------------------          -----------------------
Đọc:  Number                    Đọc:  Object
Ghi:  không thêm Number cụ thể   Ghi:  Integer
Upper: Number                   Upper: Object (với List<E>)
Lower: kiểu null                 Lower: Integer
```

Cận trên của `? super Integer` **không nhất thiết luôn là `Object`**, bởi nó còn phụ thuộc cận của tham số kiểu khai báo trong generic. Sự khác biệt đó rất quan trọng.

## 5. Ví dụ Java 17 hoàn chỉnh: đọc/ghi theo cận của capture

Lưu thành `CaptureBoundsDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;

public class CaptureBoundsDemo {
    static void fromExtends(List<? extends Number> source) {
        Number first = source.get(0);
        System.out.println("upper read=" + first);

        // source.add(99); // Không biên dịch: không biết CAP#1.
        source.add(null);   // Chỉ hợp lệ vì null tương thích với CAP#1.
    }

    static void fromSuper(List<? super Integer> destination) {
        destination.add(10);
        Object first = destination.get(0);
        System.out.println("lower read=" + first);

        // Number n = destination.get(0); // Không biên dịch.
    }

    public static void main(String[] args) {
        List<Integer> source = new ArrayList<>(List.of(1, 2));
        fromExtends(source);
        System.out.println("source=" + source);

        List<Number> destination = new ArrayList<>();
        fromSuper(destination);
        System.out.println("destination=" + destination);
    }
}
```

Lệnh:

```bash
javac CaptureBoundsDemo.java
java CaptureBoundsDemo
```

Kết quả:

```text
upper read=1
source=[1, 2, null]
lower read=10
destination=[10]
```

Chương trình dùng `ArrayList` để bảo đảm thao tác thêm `null` được hỗ trợ. Khi dùng collection khác, không thể suy từ tính hợp lệ về kiểu sang kết quả runtime. Hai phương thức cũng cho thấy quyền đọc/ghi được xác định từ **chữ ký tham số**, không phải từ cách tạo list tại điểm gọi.

## 6. Cận khai báo của generic ảnh hưởng cận trên capture

Đây là khác biệt quan trọng giữa một `List<E>` thông thường và generic có cận trên tự khai báo.

Xét:

```java
class NumberBox<T extends Number> {
    private T value;

    NumberBox(T value) {
        this.value = value;
    }

    T get() {
        return value;
    }

    void set(T value) {
        this.value = value;
    }
}
```

Ở đây, kiểu `T` **bắt buộc là `Number` hoặc kiểu con của `Number`**. Vì thế cả khi dùng wildcard cận dưới, cận trên của kiểu capture vẫn không thể rộng quá `Number`.

| Kiểu | Cận trên của kiểu capture | Cận dưới |
| --- | --- | --- |
| `List<? super Integer>` | `Object` | `Integer` |
| `NumberBox<? super Integer>` | `Number` | `Integer` |
| `NumberBox<?>` | `Number` | Kiểu `null` |
| `NumberBox<? extends Integer>` | `Integer` | Kiểu `null` |

Với `NumberBox<? super Integer>`, ta **đọc được `Number`** và **ghi được `Integer`**. Điều này không mâu thuẫn với quy tắc `List<? super Integer>` chỉ đọc được `Object`. Sự khác biệt đến từ cận trên `T extends Number` được khai báo tại `NumberBox`.

### Ví dụ chạy được: capture vừa có upper `Number` vừa có lower `Integer`

Lưu thành `BoundedBoxCaptureDemo.java`:

```java
public class BoundedBoxCaptureDemo {
    static final class NumberBox<T extends Number> {
        private T value;

        NumberBox(T value) {
            this.value = value;
        }

        T get() {
            return value;
        }

        void set(T value) {
            this.value = value;
        }
    }

    static void useBox(NumberBox<? super Integer> box) {
        Number before = box.get(); // Cận trên là Number.
        box.set(42);               // Cận dưới là Integer.
        Number after = box.get();

        System.out.println("before=" + before);
        System.out.println("after=" + after);
    }

    public static void main(String[] args) {
        NumberBox<Number> numbers = new NumberBox<>(2.5);
        useBox(numbers);
        System.out.println("actual=" + numbers.get());

        NumberBox<Integer> integers = new NumberBox<>(7);
        useBox(integers);
        System.out.println("actual=" + integers.get());
    }
}
```

```bash
javac BoundedBoxCaptureDemo.java
java BoundedBoxCaptureDemo
```

Kết quả:

```text
before=2.5
after=42
actual=42
before=7
after=42
actual=42
```

Cả `NumberBox<Number>` lẫn `NumberBox<Integer>` đều phù hợp với `NumberBox<? super Integer>`. Mọi đối số kiểu được chấp nhận của `NumberBox` phải là kiểu con của `Number`, nên đọc ra dưới `Number` luôn an toàn; mọi ứng viên cho `? super Integer` đều nhận `Integer`, nên gọi `set(42)` cũng an toàn.

Bài học: không nên học máy móc “`? super` chỉ đọc được `Object`” cho **mọi** generic. Đúng hơn phải nói: đọc được giá trị dưới **cận trên của biến capture**; ở `List<E>` cận này thông thường là `Object`, còn với `NumberBox<T extends Number>` là `Number`.

## 7. Cách compiler xác định upper và lower bound

Với một tham số kiểu khai báo `T` của generic, compiler xem xét **cận khai báo của `T`** trước, rồi kết hợp nó với wildcard tại nơi sử dụng. Có thể ghi nhớ ba trường hợp cơ bản:

### Trường hợp A: wildcard không giới hạn `?`

- **Upper bound:** cận trên khai báo của tham số kiểu `T` (thông thường `Object`).
- **Lower bound:** kiểu `null`.

Do đó `List<?>` đọc được `Object`, còn `NumberBox<?>` đọc được `Number`.

### Trường hợp B: wildcard `? extends B`

- **Upper bound:** được kết hợp từ cận `B` của wildcard và cận khai báo của `T`, về mặt ngôn ngữ là *greatest lower bound* (`glb`) của các cận cần thỏa.
- **Lower bound:** kiểu `null`.

Trong trường hợp đơn giản `List<? extends Number>`, cận khai báo của `List<E>` là `Object` nên kết quả upper là `Number`. Với `NumberBox<? extends Integer>`, upper là `Integer` vì `Integer` nằm dưới `Number`.

Khi cận khai báo có nhiều interface, cận trên có thể được mô tả bằng một **kiểu giao (intersection type)** ở phía compiler. Chẳng hạn, một class khai báo `T extends Number & java.io.Serializable` cùng wildcard có cận trên khác có thể buộc CAP thỏa đồng thời nhiều ràng buộc. Không được tự nghĩ rằng compiler luôn giữ đúng nguyên văn duy nhất kiểu viết sau `extends`.

### Trường hợp C: wildcard `? super B`

- **Upper bound:** cận trên **khai báo của `T`**, sau khi xét các tham số generic liên quan.
- **Lower bound:** `B`.

Với `List<? super Integer>`, upper là `Object`, lower `Integer`. Với `NumberBox<? super Integer>`, upper là `Number`, lower `Integer`.

Các quy tắc này mô tả ý tưởng về capture conversion được quy định trong *Java Language Specification*, mục 5.1.10. Những generic có cận tự tham chiếu hoặc nhiều tham số kiểu phụ thuộc nhau có thể tạo các cận sau khi thay thế phức tạp hơn; nhưng nguyên tắc đọc từ upper và truyền giá trị tương thích lower vẫn là nền tảng hữu ích.

## 8. Cần phân biệt cận của wildcard với cận của kiểu capture

Biểu thức:

```java
List<? super Integer> sink;
```

có một **wildcard ghi rõ cận dưới `Integer`**. Khi được capture, compiler tạo kiểu tạm thời có cả hai phía giới hạn: upper từ `List<E>` là `Object`, lower `Integer`.

Vì vậy, cụm “giới hạn trên và dưới của kiểu được bắt giữ” nói về **đầy đủ hai mặt** của kiểu tạm thời CAP, chứ không chỉ đọc chữ `extends` hay `super` trong mã nguồn.

Một sơ đồ minh họa:

```text
List<? super Integer>      -> CAP#1:
                                  Integer <: CAP#1 <: Object

NumberBox<? super Integer> -> CAP#2:
                                  Integer <: CAP#2 <: Number

List<? extends Number>     -> CAP#3:
                                  null-type <: CAP#3 <: Number

NumberBox<?>               -> CAP#4:
                                  null-type <: CAP#4 <: Number
```

`null-type` ở đây là cách diễn giải cận dưới của hệ kiểu, không phải tên một class. Mỗi lần capture có thể tạo biến kiểu riêng; ký hiệu `CAP#1`, `CAP#2` trong lỗi compiler không ổn định giữa trình biên dịch hoặc vị trí biên dịch.

## 9. Hai capture từ hai wildcard khác nhau không đồng nhất

Ngay cả khi hai tham số dùng cùng cú pháp `List<? extends Number>`, compiler **không mặc nhiên xem kiểu phần tử capture của chúng là một kiểu**.

Ví dụ:

```java
static void moveFirst(
        List<? extends Number> source,
        List<? extends Number> destination) {

    Number value = source.get(0); // Đọc được Number.

    // destination.add(value); // Không biên dịch.
}
```

`source` có thể là `List<Integer>`, còn `destination` có thể là `List<Double>`. Capture của hai wildcard là các kiểu tạm thời khác nhau. Cả hai cùng có cận trên `Number` không làm chúng bằng nhau.

Muốn chuyển số từ nguồn sang một **đích consumer**, có thể khai báo:

```java
static void append(
        List<? extends Number> source,
        List<? super Number> destination) {
    for (Number value : source) {
        destination.add(value);
    }
}
```

Ở đây upper `Number` giúp đọc nguồn dưới `Number`, lower `Number` giúp đích nhận mọi `Number`. Đó chính là cách kết hợp producer/consumer của PECS. Đích có thể là `List<Number>` hoặc `List<Object>`, nhưng không thể là `List<Integer>` nếu nguồn có thể chứa `Double`.

Nếu cần dùng một kiểu chung do caller quyết định, chữ ký tổng quát hơn là:

```java
static <T> void appendGeneric(
        List<? extends T> source,
        List<? super T> destination) {
    for (T value : source) {
        destination.add(value);
    }
}
```

Cách này dùng cùng một `T` để liên kết cận trên của producer và cận dưới của consumer, trong khi vẫn cho phép hai đối số generic khác nhau.

## 10. Helper giữ cận trên khi xử lý một captured type

Ở `List<? extends Number>`, compiler biết element type ẩn là một subtype của `Number`, nhưng không cho ghi một `Integer` bất kỳ: danh sách thật có thể là `List<Double>`.

Nếu cần **lặp lại chính một phần tử đã tồn tại**, dùng helper có bound tương ứng:

```java
static void repeatFirstNumber(List<? extends Number> source) {
    repeatCapturedNumber(source);
}

private static <E extends Number> void repeatCapturedNumber(List<E> source) {
    if (!source.isEmpty()) {
        E first = source.get(0);
        double numericalValue = first.doubleValue();
        source.add(first);
        System.out.println("repeated=" + numericalValue);
    }
}
```

Các method cần đặt trong class có import `java.util.List`. Lời gọi `repeatCapturedNumber(source)` capture `? extends Number` thành một `E` thỏa `E extends Number`. Do đó `doubleValue()` hợp lệ **và** giá trị lấy từ chính `List<E>` có thể được thêm lại cùng list dưới dạng `E`.

Trái lại, `source.add(42)` ngay trên `List<? extends Number>` không biên dịch, và helper cũng không cho tự tạo ra một `E` mới từ `42`. Runtime vẫn phải xét list có cho thêm phần tử không; `List.of` không sửa được. Với `? super Integer`, quyền đọc còn phụ thuộc **cận trên của type parameter khai báo**: `List<E>` cho đọc `Object`, còn `NumberBox<E extends Number>` cho đọc `Number`.

Trọng tâm ở đây là **bound của captured type quyết định thao tác hợp lệ**, không phải thuật toán swap hay đặt tên `CAP#` trong diagnostic.

## 11. Đọc/ghi với upper và lower không đồng nghĩa ép kiểu tự động

Xét `NumberBox<? super Integer>`: có thể đọc `Number`, ghi `Integer`. Điều này **không** có nghĩa compiler tự chuyển tất cả giá trị đọc thành `Integer`:

```java
NumberBox<? super Integer> box = new NumberBox<Number>(2.5);
Number read = box.get(); // Đúng.
// Integer i = box.get(); // Không biên dịch.
box.set(3);              // Đúng.
// box.set(3.5);          // Không biên dịch.
```

Các đoạn ở mục này dựa vào khai báo `NumberBox<T extends Number>` từ mục 6 và dùng làm minh họa chữ ký, không phải file Java độc lập.

`box.get()` có thể trả `Double` vì đối tượng thực sự là `NumberBox<Number>`. Nếu ép kiểu tường minh sang `Integer` thì cast có thể gây `ClassCastException`; không dùng cast để xóa sự không chắc chắn về kiểu capture.

Ngược lại, lời gọi `box.set(3)` hợp lệ vì `Integer` có thể đi vào mọi loại `NumberBox` đáp ứng `? super Integer` cùng cận `T extends Number`. Cận dưới cho biết loại giá trị nào an toàn **đưa vào**, không phải loại giá trị nào chắc chắn **lấy ra**.

## 12. Type erasure và phạm vi của capture

Wildcard capture là thao tác của **hệ kiểu tĩnh**, không phải một cuộc kiểm tra đối số generic khi chạy. Java thường dùng *type erasure* cho generic, nên tại runtime không tồn tại một đối tượng kiểu riêng tên `CAP#1` để ta truy vấn trực tiếp.

Ví dụ:

```java
List<? extends Number> first = new ArrayList<Integer>();
List<? extends Number> second = new ArrayList<Double>();

System.out.println(first.getClass() == second.getClass());
```

Kết quả là `true` vì hai đối tượng runtime đều là `ArrayList`; khác biệt giữa `Integer` và `Double` được phản ánh qua ràng buộc compile time của từng khai báo, không qua hai lớp runtime riêng biệt `ArrayList<Integer>` và `ArrayList<Double>`.

Một chương trình hoàn chỉnh để chạy đoạn này cần class chứa phương thức `main` cùng `import java.util.List;` và `import java.util.ArrayList;`. Đoạn hiện tại chỉ nhằm giải thích erasure.

Điều đó cũng không cho phép tự ý ép `List<Integer>` thành `List<Double>`. Chính hệ kiểu trước khi chạy đã ngăn các thao tác làm hỏng tính nhất quán của dữ liệu. Raw type hoặc cast unchecked có thể né kiểm tra, nhưng là nguyên nhân của lỗi kiểu xuất hiện muộn và cần tránh.

## 13. Các bẫy thường gặp

### Bẫy 1: cho rằng `? super T` luôn đọc được `Object` bất kể khai báo generic

Với `List<? super Integer>`, đọc `Object` là bảo đảm thông thường. Nhưng với `NumberBox<? super Integer>`, cận khai báo `T extends Number` cho phép đọc dưới `Number`. Cần xét **cả wildcard lẫn cận của tham số kiểu được khai báo**.

### Bẫy 2: nhìn thấy `? extends Number` thì tưởng capture luôn là `Number`

Sai. Kiểu thực tế có thể là `Integer` hay `Double`. `CAP <: Number` chỉ là giới hạn trên, không phải phương trình `CAP = Number`. Vì thế vẫn không thêm được tùy ý một `Number` cụ thể.

### Bẫy 3: thấy `? super Integer` thì tưởng mọi phần tử hiện hữu là `Integer`

Sai. `List<? super Integer>` có thể là `List<Object>` chứa sẵn chuỗi. Cận dưới bảo đảm có thể thêm `Integer`, không bảo đảm mọi phần tử đọc ra thuộc `Integer`.

### Bẫy 4: nghĩ các wildcard có cùng cận là cùng một capture

Hai nguồn `List<? extends Number>` có thể chứa các kiểu con khác nhau. Không được chép phần tử từ một nguồn trực tiếp vào nguồn kia chỉ dựa trên cùng cận trên.

### Bẫy 5: dùng `List<Object>` thay cho `List<?>` để xử lý capture

`List<Object>` không thể nhận trực tiếp `List<String>` vì generic bất biến. `List<?>` mới là chữ ký phù hợp khi thuật toán chỉ đọc các giá trị chung dưới `Object` và không cần một kiểu phần tử chính xác.

### Bẫy 6: nghĩ helper method làm mất giới hạn kiểu

Generic helper không cho phép thêm sai kiểu. Nó chỉ đặt tên một capture để chuyển **chính giá trị cùng kiểu `E`** giữa các vị trí an toàn. Nếu cố `items.add((E) someObject)` bằng cast unchecked thì vẫn có nguy cơ sai kiểu.

### Bẫy 7: tin rằng upper bound `Number` cấm giá trị `null`

Không. Một `ArrayList<Integer>` có thể chứa `null`, và khi đọc qua `List<? extends Number>`, giá trị nhận được có thể là `null`. Cận kiểu mô tả quan hệ subtype, không phải cam kết non-null.

### Bẫy 8: nhầm lỗi capture với lỗi dữ liệu runtime

Thông báo chứa `CAP#1` thường liên quan compiler không chứng minh được quan hệ kiểu tại lời gọi generic. `UnsupportedOperationException`, `NullPointerException` hoặc `ClassCastException` khi chạy lại phải điều tra theo hợp đồng collection, dữ liệu thực tế và các cast đã dùng; không nên gọi chung là “lỗi wildcard”.

## 14. Cách đọc thông báo lỗi capture của compiler

Khi thử truyền một `Integer` vào `List<? extends Number>`:

```java
static void addBad(List<? extends Number> values) {
    // values.add(10); // Không biên dịch.
}
```

Một thông báo compiler có thể đề cập `CAP#1`, kiểu `Integer` không chuyển được sang `CAP#1`, hoặc “where CAP#1 is a fresh type-variable”. Đây là cách compiler diễn đạt:

- `CAP#1` là kiểu phần tử chưa biết của `values`;
- `CAP#1` được biết có cận trên `Number`;
- nhưng không có bằng chứng `Integer <: CAP#1`;
- vì vậy lời gọi `add(10)` không an toàn.

Không phụ thuộc vào chính xác số thứ tự `CAP#1` hay wording của thông báo, vì các bản compiler có thể trình bày khác nhau.

Khi gặp lỗi kiểu này, nên lần lượt tự hỏi:

1. Generic ở vị trí tham số có khai báo cận `T extends ...` không?
2. Wildcard tại điểm dùng là `?`, `? extends B` hay `? super B`?
3. Từ hai thông tin đó, cận trên/cận dưới của capture là gì?
4. Code đang **đọc** từ capture hay **ghi** một giá trị vào capture?
5. Nếu cần đọc và ghi cùng một kiểu chưa biết, có nên chuyển thao tác vào generic helper `<E>` để compiler giữ liên kết kiểu không?

Giải quyết đúng thường là đổi chữ ký sang producer `? extends T`, consumer `? super T`, hoặc generic helper, thay vì ép kiểu không kiểm tra.

## 15. Câu hỏi luyện tập

**Câu 1.** Với `List<? extends Number> values`, compiler bảo đảm gì?

- Cận trên capture: `Number`.
- Cận dưới capture: kiểu `null`.
- `Number n = values.get(0)` hợp lệ nếu chỉ xét kiểu, nhưng `get(0)` vẫn có thể gặp danh sách rỗng.
- `values.add(10)` không hợp lệ; `values.add(null)` hợp lệ về kiểu nhưng chưa chắc thành công khi chạy.

**Câu 2.** Với `List<? super Integer> values`, cận trên và dưới là gì?

- Cận trên: `Object`, do `List<E>` không có cận chặt hơn.
- Cận dưới: `Integer`.
- `values.add(10)` hợp lệ; `Object v = values.get(0)` hợp lệ.
- `Number n = values.get(0)` không được đảm bảo.

**Câu 3.** Với `NumberBox<T extends Number>` và `NumberBox<? super Integer>`, kiểu kết quả của `get` có thể nhận vào biến nào?

**`Number`.** Upper của CAP là `Number`; lower là `Integer`. Vì vậy `Number n = box.get()` được chấp nhận mà không cần cast.

**Câu 4.** `NumberBox<?>` có đọc `Number` được không?

**Có.** Wildcard không giới hạn lấy cận trên từ tham số `T extends Number` của class; dấu `?` không làm biến `T` mất cận khai báo.

**Câu 5.** Có thể sao chép trực tiếp từ `List<? extends Number> a` sang `List<? extends Number> b` bằng `b.add(a.get(0))` không?

**Không.** Capture của hai nguồn độc lập; `b` có thể là `List<Integer>` còn `a` có thể là `List<Double>`. Nếu đích phải nhận mọi `Number`, khai báo đích `List<? super Number>`.

**Câu 6.** Vì sao generic helper `<E> void helper(List<E> values)` khắc phục một số lỗi liên quan `List<?>`?

Vì compiler suy luận `E` là **kiểu capture cụ thể cho một lời gọi**, rồi dùng đúng một tham số kiểu `E` xuyên suốt thân helper. Nhờ vậy có thể lấy một phần tử kiểu `E` và đặt lại vào danh sách cùng `E` an toàn.

## 16. Ghi nhớ để áp dụng

- Wildcard capture tạo **kiểu tạm thời chưa biết nhưng có giới hạn**; nó không tạo kiểu runtime mới.
- `? extends B` cho **upper** từ `B` kết hợp cận khai báo, **lower** là kiểu `null`: thuận tiện để **đọc**.
- `? super B` cho **lower** là `B`, **upper** từ cận khai báo của tham số generic: thuận tiện để **ghi** giá trị `B`.
- `?` cũng có upper từ cận khai báo, lower là kiểu `null`; vì vậy `NumberBox<?>` có thể đọc `Number` trong khi `List<?>` thường chỉ đọc `Object`.
- Hai wildcard nhìn giống nhau có thể là **hai capture riêng**; cận giống nhau không buộc đối số kiểu thực tế giống nhau.
- Khi phải chuyển giá trị giữa những vị trí thực sự dùng **cùng một kiểu chưa biết**, generic helper `<E>` đặt tên kiểu capture và bảo toàn quan hệ ấy.
- Luôn phân biệt **hợp lệ về kiểu** với collection có thể sửa đổi, cho phép `null` hoặc bảo đảm dữ liệu runtime thỏa yêu cầu.

Câu hỏi quyết định khi phân tích một đoạn Java Generics là: **“Kiểu CAP này có upper nào để đọc được gì, lower nào để ghi được gì, và các vị trí đang thao tác có thực sự dùng cùng một CAP không?”**