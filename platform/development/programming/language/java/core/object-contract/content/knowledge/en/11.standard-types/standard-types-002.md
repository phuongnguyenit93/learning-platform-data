# Lớp bao số nguyên khác kiểu không mặc nhiên bằng nhau

## 1. Hai đối tượng có cùng số chưa chắc bằng nhau theo `equals()`

Java có các **lớp bao (wrapper classes)** cho các kiểu số nguyên nguyên thủy:

| Kiểu nguyên thủy | Lớp bao | Ví dụ tạo giá trị |
| --- | --- | --- |
| `byte` | `Byte` | `Byte.valueOf((byte) 42)` |
| `short` | `Short` | `Short.valueOf((short) 42)` |
| `int` | `Integer` | `Integer.valueOf(42)` |
| `long` | `Long` | `Long.valueOf(42L)` |

Bốn đối tượng đó đều biểu diễn giá trị toán học **42**, nhưng chúng thuộc **bốn lớp Java khác nhau**. Với các lớp bao số nguyên tiêu chuẩn, phương thức `equals(Object)` đòi hỏi đối tượng còn lại thuộc **đúng kiểu wrapper tương ứng** và có cùng giá trị được lưu. Vì vậy:

```java
Integer integer = 42;
Long longNumber = 42L;

System.out.println(integer.equals(longNumber)); // false
System.out.println(longNumber.equals(integer));  // false
```

Đây là **fragment minh họa**; chương trình chạy đầy đủ có ở phần sau. Điểm cần nắm: `equals()` của wrapper định nghĩa quan hệ bằng nhau **theo kiểu và giá trị**; nó không tự động chuyển cả hai bên về một kiểu số chung.

Đây là một lựa chọn có chủ ý về bản sắc của **đối tượng Java**, không đồng nghĩa phép so sánh số học `42 == 42L` sai. Khi bạn muốn so sánh **giá trị số**, cần nêu rõ phép chuyển đổi hay quy tắc so sánh.

## 2. Cơ chế của `equals()` trong các wrapper số nguyên

Về ý nghĩa, các phương thức triển khai giống quy tắc sau:

```java
// Minh họa ngữ nghĩa; KHÔNG phải mã nguồn triển khai thật:
boolean integerEquals(Object other, int value) {
    return other instanceof Integer that && value == that.intValue();
}

boolean longEquals(Object other, long value) {
    return other instanceof Long that && value == that.longValue();
}
```

Đây là **hai hàm mô phỏng hành vi**. Khi `Integer.equals` nhận `Long`, kiểm tra `instanceof Integer` không đạt; kết quả ngay lập tức là `false`. Khi `Long.equals` nhận `Integer`, kiểm tra `instanceof Long` cũng không đạt.

Điều này áp dụng tương tự cho `Byte` và `Short`. Các cặp sau có kết quả:

| Bên trái | Bên phải | `left.equals(right)` |
| --- | --- | --- |
| `Integer.valueOf(42)` | `Integer.valueOf(42)` | `true` |
| `Integer.valueOf(42)` | `Long.valueOf(42L)` | `false` |
| `Short.valueOf((short) 42)` | `Byte.valueOf((byte) 42)` | `false` |
| `Long.valueOf(42L)` | `Long.valueOf(42L)` | `true` |
| `Integer.valueOf(42)` | `null` | `false` |

Bảng thể hiện quan hệ đối xứng cho những ví dụ này: hai wrapper khác kiểu đều không bằng nhau theo cả hai chiều. Việc trả về `false` giữa hai lớp khác nhau **không vi phạm** hợp đồng `equals()`. Hợp đồng chỉ đòi hỏi tính phản xạ, đối xứng, bắc cầu, nhất quán và `x.equals(null) == false`; nó không đòi Java phải xem mọi cách biểu diễn cùng một số là một đối tượng logic.

`Objects.equals(a, b)` là công cụ so sánh có xử lý `null`: nếu cả hai cùng null thì `true`, một bên null thì `false`; các trường hợp còn lại ủy quyền cho `a.equals(b)`. **`Objects.equals` không tự chuyển kiểu wrapper.**

## 3. Ví dụ Java 17 chạy được

Tạo tệp `IntegerWrapperEqualityDemo.java`:

```java
import java.util.HashSet;
import java.util.Objects;
import java.util.Set;

public class IntegerWrapperEqualityDemo {

    // Chỉ chấp nhận bốn loại wrapper số nguyên.
    static boolean isIntegerWrapper(Number number) {
        return number instanceof Byte
                || number instanceof Short
                || number instanceof Integer
                || number instanceof Long;
    }

    // Quy tắc RIÊNG cho nghiệp vụ cần so giá trị số nguyên.
    // longValue() là chuyển đổi chính xác cho bốn wrapper trên.
    static boolean sameIntegerValue(Number a, Number b) {
        return isIntegerWrapper(a)
                && isIntegerWrapper(b)
                && a.longValue() == b.longValue();
    }

    public static void main(String[] args) {
        Integer i = Integer.valueOf(42);
        Long l = Long.valueOf(42L);
        Short s = Short.valueOf((short) 42);
        Byte b = Byte.valueOf((byte) 42);

        System.out.println("Integer.equals(Long): " + i.equals(l));
        System.out.println("Long.equals(Integer): " + l.equals(i));
        System.out.println("Integer.equals(Integer): "
                + i.equals(Integer.valueOf(42)));
        System.out.println("Short.equals(Byte): " + s.equals(b));
        System.out.println("Objects.equals(i, l): "
                + Objects.equals(i, l));

        Number left = i;
        Number right = l;
        System.out.println("Number references ==: " + (left == right));
        System.out.println("int vs long primitives ==: "
                + (i.intValue() == l.longValue()));
        System.out.println("boxed Integer vs primitive long ==: "
                + (i == 42L));

        System.out.println("sameIntegerValue(i, l): "
                + sameIntegerValue(i, l));
        System.out.println("sameIntegerValue(s, b): "
                + sameIntegerValue(s, b));
        System.out.println("sameIntegerValue(i, 43L): "
                + sameIntegerValue(i, Long.valueOf(43L)));
        System.out.println("sameIntegerValue(i, 42.0): "
                + sameIntegerValue(i, Double.valueOf(42.0)));

        System.out.println("Integer hash: " + i.hashCode());
        System.out.println("Long hash: " + l.hashCode());

        Set<Number> numbers = new HashSet<>();
        numbers.add(i);
        numbers.add(l);
        numbers.add(s);
        numbers.add(b);
        System.out.println("set size: " + numbers.size());
        System.out.println("contains Integer(42): "
                + numbers.contains(Integer.valueOf(42)));
        System.out.println("contains Long(42): "
                + numbers.contains(Long.valueOf(42L)));
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac IntegerWrapperEqualityDemo.java
java IntegerWrapperEqualityDemo
```

Đầu ra chính xác:

```text
Integer.equals(Long): false
Long.equals(Integer): false
Integer.equals(Integer): true
Short.equals(Byte): false
Objects.equals(i, l): false
Number references ==: false
int vs long primitives ==: true
boxed Integer vs primitive long ==: true
sameIntegerValue(i, l): true
sameIntegerValue(s, b): true
sameIntegerValue(i, 43L): false
sameIntegerValue(i, 42.0): false
Integer hash: 42
Long hash: 42
set size: 4
contains Integer(42): true
contains Long(42): true
```

### Đọc kết quả theo từng lớp ngữ nghĩa

- `i.equals(l)` và `l.equals(i)` đều `false` vì một bên là `Integer`, bên kia là `Long`.
- `Objects.equals(i, l)` cũng `false`: phương thức này chỉ xử lý null-safe và dựa vào `i.equals(l)`.
- `left` và `right` được khai báo kiểu `Number`, nên phép `left == right` so sánh **tham chiếu** đến hai đối tượng khác nhau: `false`. Không có phép unboxing vì cả hai toán hạng ở đây là tham chiếu `Number`.
- `i.intValue() == l.longValue()` so sánh hai giá trị nguyên thủy; `int` được nâng lên `long` theo quy tắc thăng hạng số của Java, nên `42 == 42L` là `true`.
- `i == 42L` cũng `true` vì một toán hạng là số nguyên thủy `long`, Java unbox `i` thành `int` rồi thăng hạng để so sánh số nguyên thủy. Cú pháp `==` có thể cho kết quả khác nhau tùy **kiểu tĩnh của toán hạng**.
- `sameIntegerValue(i, l)` trả `true` vì ta chủ động định nghĩa phép so sánh theo `longValue()` cho bốn wrapper số nguyên.
- `Double.valueOf(42.0)` bị từ chối bởi `isIntegerWrapper`, dù giá trị toán học là 42. Đây là **phạm vi chính sách của helper**, không có nghĩa không thể so sánh số thực với số nguyên bằng API khác.
- Hai đối tượng `Integer(42)` và `Long(42)` cùng mã băm `42` nhưng vẫn không bằng nhau. **Hash bằng nhau không suy ra `equals()` đúng**.
- `HashSet<Number>` chứa đủ bốn wrapper khác kiểu và đều biểu diễn 42: `size() == 4`. Tập dùng `equals()`/`hashCode()` của từng đối tượng, **không dùng phép chuyển đổi số học tùy ý**.

## 4. Vì sao `==` không thể thay thế `equals()`?

`==` ở Java có hai ngữ nghĩa liên quan đến ví dụ này:

1. **Hai tham chiếu có kiểu tương thích để so sánh tham chiếu**: kiểm tra có cùng trỏ vào một đối tượng trong bộ nhớ hay không.
2. **Hai toán hạng thuộc ngữ cảnh so sánh số nguyên thủy**, có thể thông qua unboxing: kiểm tra giá trị số sau các quy tắc chuyển đổi số của ngôn ngữ.

Ví dụ riêng từng trường hợp:

```java
Integer boxedInt = Integer.valueOf(42);
long primitiveLong = 42L;
boolean numeric = boxedInt == primitiveLong; // true: unbox + widen

Number a = boxedInt;
Number b = Long.valueOf(42L);
boolean sameReference = (a == b); // false: so sánh tham chiếu
```

Hai dòng đầu dùng `==` với số nguyên thủy, hai dòng sau với tham chiếu. Đoạn code là **fragment**, không phải chương trình độc lập.

**Cảnh báo khi nhìn hai biến có kiểu `Integer` và `Long`:** biểu thức `integerObject == longObject` có thể bị trình biên dịch từ chối vì hai kiểu tham chiếu này không tương thích với phép so sánh tham chiếu; Java không có quy tắc “thấy hai wrapper khác loại thì luôn tự unbox”. Đừng suy diễn từ ví dụ `boxedInt == primitiveLong` sang mọi tổ hợp wrapper.

### Bộ nhớ đệm (cache) không phải hợp đồng bằng nhau

`Integer.valueOf` bảo đảm tái sử dụng đối tượng cho ít nhất dải `-128..127`. Điều này có thể làm `==` giữa hai biến `Integer` đôi lúc trả `true` vì chúng trỏ cùng một đối tượng. Ngoài dải đảm bảo, runtime có thể có chính sách cache rộng hơn; không được dùng kết quả `==` để suy luận hai số nguyên boxed có cùng giá trị.

```java
Integer first = Integer.valueOf(42);
Integer second = Integer.valueOf(42);

first == second;      // true trong dải được bảo đảm cache
first.equals(second); // true theo giá trị và kiểu
```

Fragment này dùng để minh họa; nếu mục tiêu là so sánh hai `Integer` theo giá trị, dùng `equals()` hoặc `Objects.equals()` khi cần null-safe.

## 5. Khi cần so sánh số nguyên khác wrapper theo giá trị

### Chuyển đổi rõ ràng trong miền giá trị an toàn

Cả bốn wrapper `Byte`, `Short`, `Integer`, `Long` đều biểu diễn giá trị thuộc miền của `long`. Vì vậy chuyển `longValue()` từ **chính bốn loại này** là chính xác và không mất thông tin:

```java
static boolean sameIntegerValue(Number a, Number b) {
    boolean supportedA = a instanceof Byte || a instanceof Short
            || a instanceof Integer || a instanceof Long;
    boolean supportedB = b instanceof Byte || b instanceof Short
            || b instanceof Integer || b instanceof Long;
    return supportedA && supportedB && a.longValue() == b.longValue();
}
```

Đoạn này là **helper minh họa**, không phải tệp Java chạy độc lập. Điều kiện lọc kiểu trước phép chuyển đổi đóng vai trò quan trọng: `Number` còn có các lớp khác như `Float`, `Double`, `BigInteger`, `BigDecimal`. Với chúng, `longValue()` có thể **cắt phần thập phân**, mất độ chính xác hoặc chỉ giữ phần thấp của giá trị nằm ngoài miền `long`.

Nếu dữ liệu bao gồm `BigInteger` lớn hơn giới hạn `long`, không nên dùng `longValue()` để quyết định hai giá trị bằng nhau. Cần chọn biểu diễn chung đủ chính xác theo miền nghiệp vụ, chẳng hạn chuyển các wrapper số nguyên và `BigInteger` về `BigInteger`, hoặc thiết kế một kiểu giá trị riêng.

### Không tự động đổi chính sách của `equals()`

Một ứng dụng có thể định nghĩa helper `sameIntegerValue` trả `true` với `Integer(42)` và `Long(42)`. Điều này **không làm thay đổi** kết quả `Integer.equals(Long)` hoặc `Long.equals(Integer)` vốn vẫn `false`.

Không thể “sửa” `Integer.equals()` hoặc `Long.equals()` trong thư viện chuẩn chỉ bằng cách dùng helper. Nếu nghiệp vụ muốn coi các kiểu nguồn có cùng số là một khóa, hãy **chuẩn hóa về một kiểu khóa chung** trước khi lưu và so sánh.

Ví dụ nếu miền chỉ cho phép số trong `long`, ta có thể dùng `Long` làm khóa:

```java
Long fromInteger = Long.valueOf(Integer.valueOf(42).longValue());
Long fromLong = Long.valueOf(Long.valueOf(42L).longValue());

boolean equalKeys = fromInteger.equals(fromLong); // true
```

Đây là fragment minh họa. Chuẩn hóa cả hai bên thành `Long` giúp ý nghĩa “cùng giá trị nguyên trong miền long” nhất quán. Trong hệ thống thật, chính sách chuẩn hóa nên áp dụng tại ranh giới dữ liệu (đọc input, tạo key, ghi collection), tránh lúc thì so sánh theo wrapper gốc, lúc thì dùng helper giá trị.

## 6. Ảnh hưởng lên `HashSet`, `HashMap` và các collection

`HashSet` dựa trên quan hệ `equals()` của phần tử và mã băm tương ứng; `HashMap` dùng quan hệ này cho khóa. Khi thêm `Integer.valueOf(42)` và `Long.valueOf(42L)` vào `HashSet<Number>`, chúng được xem là **hai phần tử khác nhau**.

```java
Set<Number> set = new java.util.HashSet<>();
set.add(Integer.valueOf(42));
set.add(Long.valueOf(42L));
System.out.println(set.size()); // 2
```

Đây là fragment: cần `import java.util.Set;` hoặc viết tên kiểu đầy đủ. `hashCode()` của cả `Integer(42)` và `Long(42)` đều trả `42` trong ví dụ, nhưng collision không khiến hai phần tử bị coi bằng nhau. Collection còn phải dùng `equals()` để phân biệt đối tượng.

Hệ quả thực tế: mã dùng `Map<Number, String>` có thể lưu hai entry riêng cho `Integer(42)` và `Long(42)`, ngay cả khi chúng trùng mã băm và trông giống một mã khách hàng. Nếu ý định là “mọi ID nguyên đều cùng hệ quy chiếu”, nên chọn **một kiểu khóa cố định**, thí dụ `Map<Long, String>`, và kiểm tra/chuyển đổi mọi ID trước khi đưa vào map.

Không sửa `hashCode()` đơn lẻ để cố gộp các wrapper khác kiểu. Với Java collection dựa trên hash, cùng mã băm là điều kiện cần cho cặp bằng nhau, nhưng **không đủ để biến hai đối tượng thành bằng nhau**.

## 7. Các trường hợp dễ nhầm và lưu ý về kiểu

### a. `Number` là lớp cha chung, không định nghĩa “equals theo số học”

Các wrapper `Byte`, `Short`, `Integer`, `Long` là con của `Number`, nhưng việc gán chúng cho tham chiếu `Number` **không khiến chúng có chung thuật toán `equals()` theo giá trị số**.

```java
Number n1 = Integer.valueOf(42);
Number n2 = Long.valueOf(42L);

System.out.println(n1.equals(n2)); // false
```

Việc gọi phương thức động vẫn chạy implementation của đối tượng thực tế là `Integer` hoặc `Long`.

### b. Phân biệt `Character` và `Boolean`

`Character` bao ký tự nguyên thủy `char`, có mã ký tự là số nguyên không dấu theo nghĩa giá trị UTF-16 code unit, nhưng **không kế thừa `Number`** và không cùng `equals()` với `Integer` hay `Long`. `Boolean` cũng không phải wrapper số nguyên. Không đưa chúng vào helper `sameIntegerValue(Number, Number)` mà không có quy tắc nghiệp vụ rõ ràng.

### c. Xử lý null

`Integer.equals(null)` trả `false`; nhưng gọi `nullableInteger.equals(anything)` khi `nullableInteger == null` sẽ gây `NullPointerException`. Dùng `Objects.equals(a, b)` nếu cần null-safe mà vẫn muốn **giữ chính sách kiểu của wrapper**:

```java
java.util.Objects.equals(Integer.valueOf(42), Long.valueOf(42L)); // false
java.util.Objects.equals(null, null);                       // true
java.util.Objects.equals(Integer.valueOf(42), null);        // false
```

Đây là fragment minh họa các biểu thức. Nếu muốn helper so sánh theo **số học** chấp nhận null theo một chính sách riêng, phải khai báo rõ: null bằng null hay không, null có được dùng làm khóa hay không; đừng mặc định `Objects.equals` sẽ đổi semantics wrapper.

### d. Tràn số và miền hỗ trợ

So sánh bằng cách ép cả hai về `int` có thể cắt mất thông tin của `Long` lớn hơn `Integer.MAX_VALUE`. Phương thức `longValue()` an toàn cho bốn wrapper nguyên được nêu, nhưng không an toàn tổng quát cho mọi `Number`, đặc biệt `BigInteger`/`BigDecimal`/`Double`.

Nếu chọn `Long` làm kiểu chuẩn hóa, hãy đảm bảo đầu vào nằm trong phạm vi `long`. Nếu chọn `BigInteger`, dùng chuyển đổi **chính xác** từ các kiểu nguyên tiêu chuẩn; còn số thực/decimal có phần thập phân cần quy tắc riêng. Việc làm tròn hay cắt phần thập phân phải là quyết định nghiệp vụ được ghi rõ.

### e. So sánh trong `TreeSet`/`TreeMap` dùng `Comparator`

Khác với các hash collection, collection sắp xếp xác định sự trùng khóa bằng kết quả `compare(a, b) == 0` của comparator (hoặc natural ordering). Một comparator tự viết so sánh các `Number` theo `longValue()` có thể coi `Integer(42)` và `Long(42)` tương đương dù `equals()` cho `false`. Điều này làm thứ tự **không nhất quán với equals**, có thể tạo hành vi khác `HashSet` và vi phạm kỳ vọng của các API `Set`.

Hãy chọn và tài liệu hóa một chính sách khóa nhất quán cho collection; nếu phải định nghĩa comparator xuyên kiểu, kiểm tra tính phản xạ của `compare(x,x)==0`, tính đối dấu, tính bắc cầu, và tính tương thích với mục đích sử dụng.

## 8. Checklist thực hành

1. **Hỏi “bằng nhau” là gì:** cùng wrapper và giá trị, hay cùng giá trị nguyên bất kể wrapper? Đây là hai quan hệ khác nhau, đều có thể hợp lệ trong ngữ cảnh riêng.
2. **Đọc kiểu tĩnh trước khi dùng `==`:** hai tham chiếu so sánh danh tính; một wrapper và một primitive có thể kích hoạt unboxing + promotion; hai wrapper khác kiểu không tự luôn so sánh theo số học.
3. **Nếu cần so sánh wrapper theo hợp đồng Java:** sử dụng `equals()`, hoặc `Objects.equals()` khi có thể null. Kết quả `Integer(42)` với `Long(42)` là `false`.
4. **Nếu cần so sánh số nguyên xuyên kiểu:** kiểm soát tập kiểu hỗ trợ và chuyển sang biểu diễn chung không mất dữ liệu, như `long` cho `Byte/Short/Integer/Long`.
5. **Nếu dùng làm khóa collection:** chuẩn hóa đầu vào về một kiểu khóa trước khi thêm/tìm; đừng dựa vào hash giống nhau hoặc ép kiểu ngầm.
6. **Thử các ca biên:** `null`, số âm, `Long.MIN_VALUE`/`Long.MAX_VALUE`, dữ liệu ngoài miền `int`, và các `Number` không phải wrapper nguyên.

### Tự kiểm tra

**Câu 1:** `Integer.valueOf(7).equals(Long.valueOf(7L))` là gì? — `false` vì hai đối tượng khác lớp.

**Câu 2:** Hai wrapper khác kiểu có cùng `hashCode()` thì có bị `HashSet` gộp thành một phần tử không? — Không; `HashSet` còn kiểm tra quan hệ bằng nhau.

**Câu 3:** `Integer.valueOf(7) == 7L` cho kết quả gì? — `true`: có một toán hạng nguyên thủy nên wrapper được unbox, rồi so sánh số học. Nhưng không được suy diễn rằng mọi phép `==` giữa hai wrapper đều có ngữ nghĩa đó.

**Câu 4:** Vì sao không dùng `Number.longValue()` trực tiếp cho mọi `Number`? — Vì `Double` có phần lẻ và `BigInteger` có thể vượt phạm vi `long`; phép chuyển đổi có thể mất thông tin, làm hai giá trị khác nhau bị xem như bằng nhau.

## Kết luận

**Cùng giá trị số không có nghĩa cùng đối tượng logic trong Java.** `Byte`, `Short`, `Integer` và `Long` áp dụng `equals()` theo **đúng loại wrapper cộng với giá trị lưu trữ**, nên `Integer(42).equals(Long(42L))` là `false`. Khi bài toán cần so sánh số nguyên xuyên kiểu, hãy nói rõ miền và chuyển đổi chính xác sang một biểu diễn chung. Giữ chính sách đó nhất quán ở vị trí so sánh, chuẩn hóa dữ liệu và khi chọn khóa cho collection.
