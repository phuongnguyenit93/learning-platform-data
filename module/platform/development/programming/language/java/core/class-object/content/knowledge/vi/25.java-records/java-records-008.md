# Java record: `equals()`, `hashCode()`, `toString()` và ảnh hưởng của thành phần mảng

## 1. Tại sao chủ đề này quan trọng?

Record trong Java 17+ cho phép định nghĩa một **kiểu dữ liệu mang giá trị** bằng danh sách thành phần (*record components*) đặt trong header:

```java
record Point(int x, int y) {}
```

Nếu tác giả không tự khai báo, compiler cung cấp `equals(Object)`, `hashCode()` và `toString()` dựa trên các record components. Với các kiểu như `int` hoặc `String`, ba phương thức này thường đúng điều người viết mong đợi ở một đối tượng giá trị.

Nhưng xét:

```java
record Numbers(int[] values) {}
```

Mảng `int[]` là một **đối tượng tham chiếu**. Mảng Java không override `Object.equals` để so từng phần tử; hai mảng khác nhau nhưng đều chứa 1, 2 **không equal theo Object.equals**. Generated record methods không tự đổi array thành một value object. Kết quả:

- `equals()` mặc định so **tham chiếu của component mảng**, không so dãy phần tử.
- `hashCode()` mặc định nhất quán với kiểu equality ấy, không phải content hash của mảng.
- `toString()` mặc định thường in dạng nhận diện array object như `[I@...` thay vì toàn bộ numbers.
- Component field là `final` nhưng **phần tử mảng vẫn thay đổi được**.
- Defensive copying chỉ giải quyết aliasing; nếu muốn value equality thực sự, phải thiết kế đồng bộ `equals`, `hashCode` và có thể `toString`.

> **Nguyên tắc:** Record tạo value-oriented methods theo **ngữ nghĩa của component types**. Nó không tự làm deep comparison, deep copying hay định dạng sâu cho mọi object graph.

Bài học sẽ phân tích từng trường hợp, thử với mảng một chiều, mảng hai chiều, `Object[]`, `List`, so sánh bản sao và làm key trong collections, rồi xây một record mảng có contract nhất quán. Các ví dụ có file độc lập cho Java 17, lệnh chạy và stdout xác định.

## 2. Record thuần primitive/String và ba phương thức mặc định

Tạo **`RecordSimpleValueDemo.java`**:

```java
record Employee(String id, int grade) {}

public class RecordSimpleValueDemo {
    public static void main(String[] args) {
        Employee a = new Employee("E-1", 3);
        Employee b = new Employee("E-1", 3);
        Employee c = new Employee("E-1", 4);

        System.out.println(a == b);
        System.out.println(a.equals(b));
        System.out.println(a.equals(c));
        System.out.println(a.hashCode() == b.hashCode());
        System.out.println(a);
    }
}
```

```bash
javac RecordSimpleValueDemo.java
java RecordSimpleValueDemo
```

```text
false
true
false
true
Employee[id=E-1, grade=3]
```

Hai đối tượng `a`, `b` tạo bằng hai lần `new` nên `==` false, nhưng equal theo hai component values. `hashCode` của chúng phải bằng nhau theo contract. `toString` hiển thị tên và giá trị các components.

**Giới hạn:** Hai records cùng text trong `toString` không bắt buộc equal nếu chính sách hiển thị che giấu sự khác nhau. HashCode giống nhau cũng không suy ra equal vì collision hợp lệ.

## 3. Chính xác `equals` được sinh có ý nghĩa gì?

Generated `equals` xét **cùng record class**, sau đó kiểm equality của từng component tương ứng.

| Loại component | So sánh mặc định |
| --- | --- |
| `int`, `long`, `boolean`, `char`… | Theo kiểu primitive tương ứng; với floating-point có quy tắc phù hợp wrapper compare |
| `String` | `String.equals` theo nội dung |
| `BigDecimal` | `BigDecimal.equals`, có xét scale |
| `List<Integer>` | `List.equals` theo các elements và thứ tự |
| `int[]` | Array reference identity |
| `String[]` | Array reference identity |
| `int[][]` | Array reference identity ở component mảng ngoài |
| Object tùy ý | Theo implementation `equals` của object |
| `null` | Hai null ở component tương ứng equal |

Với `float`/`double`, generated record equality ứng xử nhất quán với primitive-wrapper comparison, xử lý NaN và dấu của zero theo semantics đặc tả record; đừng giản lược mọi loại primitive thành biểu thức `==`.

**Cùng tên field không đủ:** `record First(int n)` và `record Second(int n)` là hai types khác nhau, không equal dù n giống nhau.

## 4. Mảng Java: tham chiếu bằng nhau khác nội dung bằng nhau

Tạo **`ArrayIdentityVersusContentDemo.java`**:

```java
import java.util.Arrays;

public class ArrayIdentityVersusContentDemo {
    public static void main(String[] args) {
        int[] a = {1, 2};
        int[] b = {1, 2};
        int[] alias = a;

        System.out.println(a == b);
        System.out.println(a.equals(b));
        System.out.println(Arrays.equals(a, b));
        System.out.println(a == alias);
        System.out.println(a.equals(alias));
    }
}
```

```bash
javac ArrayIdentityVersusContentDemo.java
java ArrayIdentityVersusContentDemo
```

```text
false
false
true
true
true
```

`a` và `b` là hai array objects khác nhau, dù có cùng nội dung. `a.equals(b)` là `Object.equals` dựa trên identity. `Arrays.equals(a,b)` mới duyệt phần tử mảng một chiều. `alias` trỏ chính object a, nên các kiểm tra reference đều true.

Đây là nền tảng để hiểu toàn bộ hành vi record có array component.

## 5. Record chứa mảng: cùng nội dung nhưng generated equals false

Tạo **`RecordArrayEqualsDemo.java`**:

```java
import java.util.Arrays;

record Numbers(int[] values) {}

public class RecordArrayEqualsDemo {
    public static void main(String[] args) {
        Numbers first = new Numbers(new int[] {1, 2});
        Numbers second = new Numbers(new int[] {1, 2});

        System.out.println(first == second);
        System.out.println(first.equals(second));
        System.out.println(
                Arrays.equals(first.values(), second.values()));
        System.out.println(
                first.values() == second.values());
    }
}
```

```bash
javac RecordArrayEqualsDemo.java
java RecordArrayEqualsDemo
```

```text
false
false
true
false
```

`Numbers` có một component là **một reference tới int[]**. Generated equals so reference semantics của component; nó không thay `values` thành một dãy logic với content equality.

Nếu mục tiêu nghiệp vụ là “hai Numbers mang cùng dãy số thì equal”, cần can thiệp thiết kế. Còn nếu mục tiêu là “hai Numbers chỉ equal khi cùng một buffer”, behavior mặc định có thể có chủ đích.

## 6. Hai records dùng cùng array object lại có thể equal

Tạo **`RecordSharedArrayDemo.java`**:

```java
record Numbers(int[] values) {}

public class RecordSharedArrayDemo {
    public static void main(String[] args) {
        int[] shared = {1, 2};

        Numbers a = new Numbers(shared);
        Numbers b = new Numbers(shared);
        Numbers c = new Numbers(shared.clone());

        System.out.println(a == b);
        System.out.println(a.equals(b));
        System.out.println(a.equals(c));
        System.out.println(a.values() == b.values());
    }
}
```

```bash
javac RecordSharedArrayDemo.java
java RecordSharedArrayDemo
```

```text
false
true
false
true
```

`a` và `b` là hai record instances khác nhau, nhưng cùng giữ reference `shared`, nên generated equals true. `c` giữ một clone khác object: values có nội dung giống hệt nhưng generated equals false.

**Quy tắc tổng quát:** Equality của record phụ thuộc vào **equality của từng component**, chứ không phụ thuộc lời hứa “trông giống giá trị” trong tên record.

## 7. Nếu có nhiều components, tất cả phải tương ứng bằng nhau

Tạo **`RecordMixedComponentsDemo.java`**:

```java
import java.util.Arrays;

record Reading(String unit, int[] samples) {}

public class RecordMixedComponentsDemo {
    public static void main(String[] args) {
        int[] shared = {10, 20};

        Reading a = new Reading("C", shared);
        Reading b = new Reading("C", shared);
        Reading c = new Reading("C", new int[] {10, 20});
        Reading d = new Reading("F", shared);

        System.out.println(a.equals(b));
        System.out.println(a.equals(c));
        System.out.println(a.equals(d));
        System.out.println(
                Arrays.equals(a.samples(), c.samples()));
    }
}
```

```bash
javac RecordMixedComponentsDemo.java
java RecordMixedComponentsDemo
```

```text
true
false
false
true
```

a/b: String cùng giá trị và mảng cùng reference. a/c: String cùng nhưng mảng khác reference. a/d: mảng cùng reference nhưng unit khác. Muốn content equality cho mảng thì phải xử lý riêng, chứ không thể chỉ có một thành phần khác equal là đủ.

## 8. Hợp đồng `equals()` và `hashCode()`

Hai điều phải phân biệt:

- **Nếu `a.equals(b)` true, `a.hashCode() == b.hashCode()` phải true.**
- Nếu hai objects không equal, hashCode **vẫn có thể trùng** vì collision.

Generated methods của record được xây để nhất quán với nhau. Khi array component dùng reference equality, generated hash cũng không hứa phản ánh nội dung mảng. Vì vậy test sau là có ý nghĩa:

Tạo **`RecordArrayHashContractDemo.java`**:

```java
record Data(int[] values) {}

public class RecordArrayHashContractDemo {
    public static void main(String[] args) {
        int[] shared = {2, 4};
        Data a = new Data(shared);
        Data b = new Data(shared);
        Data c = new Data(new int[] {2, 4});

        System.out.println(a.equals(b));
        System.out.println(a.hashCode() == b.hashCode());
        System.out.println(a.equals(c));
    }
}
```

```bash
javac RecordArrayHashContractDemo.java
java RecordArrayHashContractDemo
```

```text
true
true
false
```

Không kiểm bắt buộc hashCode của a và c khác nhau, vì hash collision hợp lệ; cũng không in số hash cố định làm expected output.

**Một nguyên tắc thiết kế:** Nếu override `equals` để dùng `Arrays.equals` trên contents, phải override `hashCode` bằng thuật toán tương thích như `Arrays.hashCode`. Không nên custom một bên mà bỏ bên kia.

## 9. `toString()` mặc định không tự in nội dung mảng

Generated `toString()` thường biểu diễn một record theo dạng `Type[component=value]`. Nhưng array type không có `toString` theo nội dung: `int[]` thường hiển thị dạng `[I@...` chứa identity hash.

Tạo **`RecordArrayToStringDemo.java`**:

```java
import java.util.Arrays;

record Numbers(int[] values) {}

public class RecordArrayToStringDemo {
    public static void main(String[] args) {
        Numbers numbers = new Numbers(new int[] {1, 2});

        System.out.println(
                Arrays.toString(numbers.values()));
        System.out.println(
                numbers.toString().startsWith(
                        "Numbers[values=[I@"));
    }
}
```

```bash
javac RecordArrayToStringDemo.java
java RecordArrayToStringDemo
```

```text
[1, 2]
true
```

Ví dụ chỉ in một phép kiểm đặc điểm hiển thị, **không in chuỗi `[I@...` đầy đủ**, vì hậu tố phụ thuộc object/JVM và không nên hardcode.

`Arrays.toString` in values của một chiều. Nếu muốn record log đẹp, hãy override `toString` có chủ đích. Nhưng custom display **không thay đổi `equals/hashCode`**.

## 10. Hai toString giống nhau vẫn không có nghĩa equal

Tạo **`PrettyButUnequalDemo.java`**:

```java
import java.util.Arrays;

record Numbers(int[] values) {
    @Override
    public String toString() {
        return "Numbers" + Arrays.toString(values);
    }
}

public class PrettyButUnequalDemo {
    public static void main(String[] args) {
        Numbers a = new Numbers(new int[] {1, 2});
        Numbers b = new Numbers(new int[] {1, 2});

        System.out.println(a);
        System.out.println(b);
        System.out.println(a.equals(b));
    }
}
```

```bash
javac PrettyButUnequalDemo.java
java PrettyButUnequalDemo
```

```text
Numbers[1, 2]
Numbers[1, 2]
false
```

Đây là một lỗi suy luận khi debug: hai dòng log giống nhau chứng tỏ formatter cho ra cùng text, **không chứng minh `equals` trả true**.

`toString` phục vụ đọc/log, không phải serialize ổn định hoặc identity contract. Trong dữ liệu nhạy cảm, còn phải kiểm xem toString có vô tình lộ secrets không.

## 11. Chọn đúng thư viện `Arrays` cho mảng một chiều

Các overloads `Arrays.equals(int[],int[])`, `Arrays.hashCode(int[])` và `Arrays.toString(int[])` làm việc với nội dung int array một chiều.

Tạo **`ArrayContentHelpersDemo.java`**:

```java
import java.util.Arrays;

public class ArrayContentHelpersDemo {
    public static void main(String[] args) {
        int[] first = {1, 2, 3};
        int[] same = {1, 2, 3};
        int[] reordered = {3, 2, 1};

        System.out.println(Arrays.equals(first, same));
        System.out.println(Arrays.equals(first, reordered));
        System.out.println(
                Arrays.hashCode(first) == Arrays.hashCode(same));
        System.out.println(Arrays.toString(first));
    }
}
```

```bash
javac ArrayContentHelpersDemo.java
java ArrayContentHelpersDemo
```

```text
true
false
true
[1, 2, 3]
```

**Thứ tự elements có ý nghĩa:** hai mảng chứa cùng tập số nhưng đảo thứ tự không equal. Nếu domain coi contents như một set hay multiset, cần representation hoặc normalization/so sánh khác; không dùng `Arrays.equals` máy móc.

## 12. Mảng hai chiều: `equals`, `deepEquals` khác nhau

`int[][]` là array chứa các array references. `Arrays.equals(matrixA,matrixB)` ở outer level dùng equality của các row array objects; muốn so sâu nội dung từng hàng, dùng `Arrays.deepEquals`.

Tạo **`NestedArrayComparisonDemo.java`**:

```java
import java.util.Arrays;

public class NestedArrayComparisonDemo {
    public static void main(String[] args) {
        int[][] a = {{1, 2}, {3, 4}};
        int[][] b = {{1, 2}, {3, 4}};

        System.out.println(Arrays.equals(a, b));
        System.out.println(Arrays.deepEquals(a, b));
        System.out.println(
                Arrays.deepHashCode(a) ==
                Arrays.deepHashCode(b));
        System.out.println(Arrays.deepToString(a));
    }
}
```

```bash
javac NestedArrayComparisonDemo.java
java NestedArrayComparisonDemo
```

```text
false
true
true
[[1, 2], [3, 4]]
```

`Arrays.deepEquals` và `Arrays.deepHashCode` là cặp tương thích khi muốn deep array contents. `Arrays.deepToString` cho biểu diễn nested content.

**Không nhầm:** Record chứa một component `int[][]` vẫn so **reference của outer array** mặc định; compiler không tự gọi `deepEquals`.

## 13. Record với `String[]` vẫn bị ảnh hưởng dù String immutable

Tạo **`RecordStringArrayDemo.java`**:

```java
import java.util.Arrays;

record Tags(String[] values) {}

public class RecordStringArrayDemo {
    public static void main(String[] args) {
        Tags a = new Tags(new String[] {"java", "record"});
        Tags b = new Tags(new String[] {"java", "record"});

        System.out.println(a.equals(b));
        System.out.println(
                Arrays.equals(a.values(), b.values()));
    }
}
```

```bash
javac RecordStringArrayDemo.java
java RecordStringArrayDemo
```

```text
false
true
```

Hai Strings cùng nội dung ở từng vị trí, nhưng **hai arrays khác nhau** vẫn khiến generated record equals false. Loại element không làm array object tự có content equality.

Với `Object[]` chứa arrays, `Arrays.equals` ở outer layer cũng chưa so sâu bên trong. Hãy dùng `Arrays.deepEquals` nếu domain thực sự muốn nested content equality.

## 14. Record component là `private final`, không có nghĩa array bất biến

Record component fields được sinh là `private final`. Từ khóa final **khóa việc gán lại field reference**; nó không đóng băng object được trỏ tới.

Tạo **`RecordArrayAliasingDemo.java`**:

```java
import java.util.Arrays;

record Snapshot(int[] values) {}

public class RecordArrayAliasingDemo {
    public static void main(String[] args) {
        int[] input = {5, 6};
        Snapshot snapshot = new Snapshot(input);

        input[0] = 9;
        System.out.println(
                Arrays.toString(snapshot.values()));

        snapshot.values()[1] = 8;
        System.out.println(Arrays.toString(input));
    }
}
```

```bash
javac RecordArrayAliasingDemo.java
java RecordArrayAliasingDemo
```

```text
[9, 6]
[9, 8]
```

Generated constructor lưu input array reference và generated accessor trả reference ấy. Không có defensive copying ngầm.

Điều này khác với String component: String immutable theo contract, nên reference có thể được chia sẻ mà không cho sửa nội dung String instance.

## 15. Equality có thể giữ nguyên sau khi sửa contents của mảng chung

Tạo **`SharedArrayMutationDemo.java`**:

```java
record Data(int[] values) {}

public class SharedArrayMutationDemo {
    public static void main(String[] args) {
        int[] shared = {1};
        Data a = new Data(shared);
        Data b = new Data(shared);

        System.out.println(a.equals(b));
        shared[0] = 99;
        System.out.println(a.equals(b));
        System.out.println(b.values()[0]);
    }
}
```

```bash
javac SharedArrayMutationDemo.java
java SharedArrayMutationDemo
```

```text
true
true
99
```

`a` và `b` vẫn cùng array reference sau mutation. Generated equality không chú ý mảng chứa 1 hay 99. Vì vậy **generated equals không phải phép kiểm dữ liệu mảng bất biến**.

Nếu business contract muốn value snapshot, cần defensive copying và một equality theo nội dung.

## 16. Thiết kế record `IntVector` có value equality đúng nghĩa

Mục tiêu: hai vectors có cùng values bằng nhau; input/output không cho alias sửa state; hash phù hợp; toString hiển thị contents. Tạo **`IntVectorValueDemo.java`**:

```java
import java.util.Arrays;
import java.util.Objects;

record IntVector(int[] values) {
    IntVector {
        values = Objects.requireNonNull(values).clone();
    }

    @Override
    public int[] values() {
        return values.clone();
    }

    @Override
    public boolean equals(Object other) {
        return this == other
                || (other instanceof IntVector vector
                    && Arrays.equals(values, vector.values));
    }

    @Override
    public int hashCode() {
        return Arrays.hashCode(values);
    }

    @Override
    public String toString() {
        return "IntVector" + Arrays.toString(values);
    }
}

public class IntVectorValueDemo {
    public static void main(String[] args) {
        int[] source = {1, 2};

        IntVector a = new IntVector(source);
        IntVector b = new IntVector(new int[] {1, 2});

        System.out.println(a.equals(b));
        System.out.println(
                a.hashCode() == b.hashCode());

        source[0] = 9;
        int[] extracted = a.values();
        extracted[1] = 8;

        System.out.println(a);
        System.out.println(b);
        System.out.println(Arrays.toString(source));
    }
}
```

```bash
javac IntVectorValueDemo.java
java IntVectorValueDemo
```

```text
true
true
IntVector[1, 2]
IntVector[1, 2]
[9, 2]
```

### Vì sao thiết kế này nhất quán?

1. Compact constructor clone input `int[]`; `Objects.requireNonNull` xác định null policy.
2. Accessor override clone output để không lộ array bên trong.
3. `equals` so **internal arrays theo nội dung** bằng `Arrays.equals`.
4. `hashCode` so cùng representation bằng `Arrays.hashCode`.
5. `toString` dùng `Arrays.toString` để in contents.
6. Các numbers là primitives; clone mảng một chiều là đủ để cô lập giá trị phần tử.

Không dùng tên getter kiểu JavaBean `getValues()` ở đây: record accessor đúng tên là `values()`, và override phải có chữ ký tương thích.

## 17. Hai ranh giới defensive copy đều cần thiết

**Chỉ clone ở constructor** thì generated accessor vẫn trả internal array:

```java
record OnlyInput(int[] values) {
    OnlyInput {
        values = values.clone();
    }
}
```

Client vẫn có thể sửa `onlyInput.values()[0]`.

**Chỉ clone ở accessor** thì constructor vẫn giữ alias của input:

```java
record OnlyOutput(int[] values) {
    @Override
    public int[] values() {
        return values.clone();
    }
}
```

Client giữ input array ban đầu có thể mutate dữ liệu trong record.

Hai kiểu trên là **hai khai báo riêng minh họa hai lỗi khác nhau**, chưa có `main`. Một immutable-value contract đòi kiểm cả ranh giới **nhận dữ liệu** và **trả dữ liệu**.

## 18. Defensive copying có thể phá kỳ vọng sao chép record nếu giữ generated equals

Đây là bẫy khó hơn: nếu clone input và output nhưng vẫn giữ generated equals so identity, thì tạo một bản copy từ component accessor có thể **không equal** original.

Tạo **`RecordCopyInvariantTrapDemo.java`**:

```java
record SafeArray(int[] values) {
    SafeArray {
        values = values.clone();
    }

    @Override
    public int[] values() {
        return values.clone();
    }
}

public class RecordCopyInvariantTrapDemo {
    public static void main(String[] args) {
        SafeArray original =
                new SafeArray(new int[] {1, 2});
        SafeArray copy = new SafeArray(original.values());

        System.out.println(original.equals(copy));
        System.out.println(
                java.util.Arrays.equals(
                        original.values(), copy.values()));
    }
}
```

```bash
javac RecordCopyInvariantTrapDemo.java
java RecordCopyInvariantTrapDemo
```

```text
false
true
```

Vì original và copy giữ **hai internal array references khác nhau**, generated equals false. Contents của chúng lại bằng nhau.

### Bất biến sao chép (*copy invariant*)

Ý nghĩa value carrier của record hướng tới bất biến: nếu lấy các component values qua accessors rồi xây lại cùng record type, bản sao phải equal với bản gốc.

```java
// Dạng khái niệm, với record R(c1, c2, ...):
R copy = new R(original.c1(), original.c2(), ...);
// Mong muốn: original.equals(copy) == true.
```

Đây là **mã giả minh họa**, không phải Java runnable độc lập.

Clone và generated identity-based array equals có thể phá kỳ vọng ấy. Vì vậy **defensive copying phải đi kèm equality/hash phù hợp với logical values**, hoặc bạn cần đổi representation.

## 19. Một lựa chọn khác: `List<Integer>` bất biến theo cấu trúc

Nếu không bắt buộc API dùng primitive array, `List<Integer>` với các phần tử immutable có thể đơn giản hóa equality.

Tạo **`ImmutableListRecordDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

record Values(List<Integer> items) {
    Values {
        items = List.copyOf(items);
    }
}

public class ImmutableListRecordDemo {
    public static void main(String[] args) {
        List<Integer> input =
                new ArrayList<>(List.of(1, 2));

        Values first = new Values(input);
        Values second = new Values(List.of(1, 2));

        System.out.println(first.equals(second));
        System.out.println(
                first.hashCode() == second.hashCode());

        input.add(3);
        System.out.println(first);

        try {
            first.items().add(4);
        } catch (UnsupportedOperationException ex) {
            System.out.println("cannot add");
        }
    }
}
```

```bash
javac ImmutableListRecordDemo.java
java ImmutableListRecordDemo
```

```text
true
true
Values[items=[1, 2]]
cannot add
```

`List.copyOf` tạo/cung cấp unmodifiable snapshot đối với mutable input structure. `List.equals` so các elements theo thứ tự, `Integer` bất biến. Do đó generated equals/hash/toString của record này có value semantics phù hợp.

**Không suy rằng `List.copyOf` deep-copy mọi phần tử**. `List<StringBuilder>` hoặc `List<int[]>` vẫn có thể giữ references tới mutable elements.

## 20. Với `List<int[]>` vẫn có vấn đề ở tầng element

Xét:

```java
record Rows(java.util.List<int[]> parts) {
    Rows {
        parts = java.util.List.copyOf(parts);
    }
}
```

Đây là **khai báo minh họa**.

`List.equals` so các elements bằng equals. Nhưng mỗi element là `int[]`, tức array vẫn dùng identity equality. Hai Rows có hai Lists chứa các mảng khác objects nhưng cùng contents vẫn không equal theo default record equality.

**Nguyên tắc nhiều tầng:** Một collection bên ngoài có value equality không tự làm mọi element bên trong cũng có value equality. Cần xét toàn bộ chuỗi nested types trước khi chọn generated methods.

## 21. Với matrix, hãy đi cùng cặp `deepEquals/deepHashCode`

Tạo **`MatrixDeepMethodsDemo.java`**:

```java
import java.util.Arrays;

record Matrix(int[][] rows) {
    @Override
    public boolean equals(Object other) {
        return this == other
                || (other instanceof Matrix m
                    && Arrays.deepEquals(rows, m.rows));
    }

    @Override
    public int hashCode() {
        return Arrays.deepHashCode(rows);
    }

    @Override
    public String toString() {
        return "Matrix" + Arrays.deepToString(rows);
    }
}

public class MatrixDeepMethodsDemo {
    public static void main(String[] args) {
        Matrix a = new Matrix(
                new int[][] {{1, 2}, {3, 4}});
        Matrix b = new Matrix(
                new int[][] {{1, 2}, {3, 4}});

        System.out.println(a.equals(b));
        System.out.println(
                a.hashCode() == b.hashCode());
        System.out.println(a);
    }
}
```

```bash
javac MatrixDeepMethodsDemo.java
java MatrixDeepMethodsDemo
```

```text
true
true
Matrix[[1, 2], [3, 4]]
```

Phương pháp này custom **content equality cho hai chiều** và display dễ đọc. Nhưng nó **chưa immutable**, vì generated constructor/accessor vẫn giữ/trả mảng references. Nếu matrix làm HashMap key, cần defensive copying đúng độ sâu.

## 22. Sao chép mảng nhiều chiều: clone mảng ngoài chưa đủ

Với `int[][]`, lệnh `rows.clone()` chỉ tạo mảng ngoài mới; các row `int[]` bên trong vẫn share references.

Để cô lập primitive matrix values, clone **outer structure** và **từng row**.

Tạo **`ImmutableMatrixRecordDemo.java`**:

```java
import java.util.Arrays;
import java.util.Objects;

record Matrix(int[][] rows) {
    Matrix {
        rows = copy(rows);
    }

    private static int[][] copy(int[][] source) {
        Objects.requireNonNull(source, "rows");

        int[][] result = new int[source.length][];
        for (int i = 0; i < source.length; i++) {
            result[i] = Objects.requireNonNull(
                    source[i], "row").clone();
        }
        return result;
    }

    @Override
    public int[][] rows() {
        return copy(rows);
    }

    @Override
    public boolean equals(Object other) {
        return this == other
                || (other instanceof Matrix m
                    && Arrays.deepEquals(rows, m.rows));
    }

    @Override
    public int hashCode() {
        return Arrays.deepHashCode(rows);
    }

    @Override
    public String toString() {
        return "Matrix" + Arrays.deepToString(rows);
    }
}

public class ImmutableMatrixRecordDemo {
    public static void main(String[] args) {
        int[][] input = {{1, 2}, {3, 4}};

        Matrix a = new Matrix(input);
        Matrix b = new Matrix(
                new int[][] {{1, 2}, {3, 4}});

        input[0][0] = 9;

        int[][] extracted = a.rows();
        extracted[1][1] = 8;

        System.out.println(a.equals(b));
        System.out.println(
                a.hashCode() == b.hashCode());
        System.out.println(a);
        System.out.println(
                Arrays.deepToString(input));
    }
}
```

```bash
javac ImmutableMatrixRecordDemo.java
java ImmutableMatrixRecordDemo
```

```text
true
true
Matrix[[1, 2], [3, 4]]
[[9, 2], [3, 4]]
```

### Phạm vi bảo đảm

- Input/output không share outer array hoặc primitive rows.
- `Arrays.deepEquals` và `Arrays.deepHashCode` dựa trên contents.
- Null outer array/row bị từ chối rõ ràng.
- Ví dụ chấp nhận ragged arrays (hàng dài ngắn khác nhau); nếu domain muốn matrix chữ nhật, thêm validation.
- Với `Object[][]`, clone từng row **chưa clone các object elements**. Muốn immutable sâu phải kiểm types và sao chép theo policy riêng.

## 23. `null` và empty array không phải cùng một giá trị

Record reference components có thể null nếu constructor không cấm.

Tạo **`RecordNullArrayDemo.java`**:

```java
record Data(int[] values) {}

public class RecordNullArrayDemo {
    public static void main(String[] args) {
        Data a = new Data(null);
        Data b = new Data(null);
        Data c = new Data(new int[0]);

        System.out.println(a.equals(b));
        System.out.println(a.equals(c));
        System.out.println(a);
        System.out.println(
                java.util.Arrays.toString((int[]) null));
    }
}
```

```bash
javac RecordNullArrayDemo.java
java RecordNullArrayDemo
```

```text
true
false
Data[values=null]
null
```

Một null component biểu thị không có reference; empty array là một array object dài 0. Nếu domain cấm null, validate ở compact/canonical constructor. Nếu domain muốn biến null thành mảng rỗng, quyết định normalization tường minh.

`Arrays.equals`/`Arrays.hashCode` có các overloads xử lý null thích hợp, nhưng đừng để tiện ích API thay thế business validation.

## 24. Record chứa array và `HashMap`: cú sốc khi tra cứu

Tạo **`RecordArrayMapKeyDemo.java`**:

```java
import java.util.HashMap;
import java.util.Map;

record Key(int[] numbers) {}

public class RecordArrayMapKeyDemo {
    public static void main(String[] args) {
        Map<Key, String> map = new HashMap<>();

        int[] shared = {1, 2};
        map.put(new Key(shared), "stored");

        System.out.println(map.get(new Key(shared)));
        System.out.println(
                map.get(new Key(new int[] {1, 2})));
        System.out.println(map.size());
    }
}
```

```bash
javac RecordArrayMapKeyDemo.java
java RecordArrayMapKeyDemo
```

```text
stored
null
1
```

HashMap không lỗi: hai keys có component arrays khác nhau không equal theo generated methods, nên tra cứu bằng mảng mới không thấy entry. Điều này đặc biệt nguy hiểm nếu bạn dùng record Key với kỳ vọng nó tượng trưng cho “dãy số làm mã”.

**Hướng sửa:** Chuyển sang immutable value representation như List<Integer>, hoặc record defensive-copy arrays và custom equals/hashCode theo content.

## 25. Khi dùng content hash, mutable array khiến Map key thiếu ổn định

Giả sử một record override `hashCode` bằng `Arrays.hashCode` nhưng không defensive-copy input/output. Array contents có thể thay đổi **sau khi map.put**, làm hashCode của key đổi. Một lần `map.get` sau đó có thể tra bucket khác và không tìm thấy entry.

Điều này là **lỗi ownership và mutability**, không phải lỗi HashMap.

Tạo **`SafeVectorMapKeyDemo.java`**:

```java
import java.util.Arrays;
import java.util.HashMap;
import java.util.Map;

record VectorKey(int[] values) {
    VectorKey {
        values = values.clone();
    }

    @Override
    public int[] values() {
        return values.clone();
    }

    @Override
    public boolean equals(Object other) {
        return this == other
                || (other instanceof VectorKey v
                    && Arrays.equals(values, v.values));
    }

    @Override
    public int hashCode() {
        return Arrays.hashCode(values);
    }
}

public class SafeVectorMapKeyDemo {
    public static void main(String[] args) {
        int[] source = {1, 2};

        VectorKey key = new VectorKey(source);
        Map<VectorKey, String> map = new HashMap<>();
        map.put(key, "FOUND");

        source[0] = 99;

        System.out.println(
                map.get(new VectorKey(new int[] {1, 2})));
        System.out.println(map.containsKey(key));
    }
}
```

```bash
javac SafeVectorMapKeyDemo.java
java SafeVectorMapKeyDemo
```

```text
FOUND
true
```

`VectorKey` không giữ alias tới array source; hash dựa trên internal values không thể bị mutate qua accessor. Đây là phương án phù hợp để làm map key theo dãy giá trị.

## 26. `HashSet` cũng hoạt động theo equality hiện có

Tạo **`RecordArraySetDemo.java`**:

```java
import java.util.HashSet;
import java.util.Set;

record Item(int[] digits) {}

public class RecordArraySetDemo {
    public static void main(String[] args) {
        Set<Item> items = new HashSet<>();

        items.add(new Item(new int[] {1, 2}));
        items.add(new Item(new int[] {1, 2}));

        System.out.println(items.size());
    }
}
```

```bash
javac RecordArraySetDemo.java
java RecordArraySetDemo
```

```text
2
```

Hai entries đều tồn tại vì hai `int[]` là references khác nhau. Nếu domain muốn loại bản ghi có cùng contents, default record methods không biểu diễn đúng contract.

**Không test rằng hai hashCode bắt buộc khác nhau.** HashSet chỉ cần equality/hash contract; unequal objects có thể tình cờ hash collision nhưng Set vẫn chứa cả hai.

## 27. Lưu ý với `Objects.hash` và mảng

`Objects.hash` không tự thực hiện deep hashing đối với mảng như ta thường mong muốn.

Ví dụ minh họa trong một method:

```java
int[] array = {1, 2};

int byContents = java.util.Arrays.hashCode(array);
int byReferenceInVarargs =
        java.util.Objects.hash((Object) array);
```

`Arrays.hashCode(int[])` duyệt elements; `Objects.hash((Object)array)` xử lý array reference là một phần tử trong varargs list, không tự duyệt int elements.

Với `Object[]`, truyền thẳng mảng vào varargs còn có thể làm phân biệt between entire array vs its contents trở nên mơ hồ. Hãy chọn helper **phù hợp với chính equality đã định nghĩa**:

- Một chiều: `Arrays.equals` + `Arrays.hashCode`.
- Mảng lồng: `Arrays.deepEquals` + `Arrays.deepHashCode`.
- Custom domain normalization: viết hash từ cùng canonical representation.

## 28. Khi nào generated methods vẫn phù hợp cho mảng?

Không phải mọi record có array component đều phải override. Có trường hợp nghiệp vụ muốn so **chính array/buffer object**, ví dụ hai descriptors cùng trỏ tới một buffer resource thì được xem equal, còn hai buffers khác nhau dù nội dung giống không equal.

Khi đó:

- Generated equality theo reference có thể có chủ đích.
- Generated hashCode tương thích equality ấy.
- Generated toString có thể chưa đủ đọc, vẫn có thể override display riêng.
- Cần ghi rõ array object có thể mutate, aliasing và lifetime.

Nhưng nếu record đại diện một **giá trị logic** như immutable vector, snapshot time series, binary content fingerprint, thì array identity thường **không** phải điều người dùng API mong đợi.

## 29. Khi nào nên tránh component kiểu mảng?

Nếu dữ liệu có số phần tử ít và cố định, các primitive components có tên thường đơn giản hơn:

```java
record RGB(int red, int green, int blue) {}
record RGBArray(int[] channels) {}
```

Tạo **`FixedComponentsDemo.java`**:

```java
record RGB(int red, int green, int blue) {}
record RGBArray(int[] channels) {}

public class FixedComponentsDemo {
    public static void main(String[] args) {
        RGB a = new RGB(10, 20, 30);
        RGB b = new RGB(10, 20, 30);

        RGBArray x =
                new RGBArray(new int[] {10, 20, 30});
        RGBArray y =
                new RGBArray(new int[] {10, 20, 30});

        System.out.println(a.equals(b));
        System.out.println(x.equals(y));
        System.out.println(a);
    }
}
```

```bash
javac FixedComponentsDemo.java
java FixedComponentsDemo
```

```text
true
false
RGB[red=10, green=20, blue=30]
```

Ba channels là bộ dữ liệu có tên và chiều cố định; đặt riêng ở header tận dụng generated equality và display tự nhiên. Khi dãy dài biến động theo input, dùng array/List hoặc type bao mảng chuyên biệt vẫn hợp lý.

## 30. Phân biệt `Arrays.toString` và `Arrays.deepToString` cho việc log

Với int[]:

```java
java.util.Arrays.toString(new int[] {1, 2})
```

trả String `[1, 2]`.

Với int[][]:

```java
java.util.Arrays.deepToString(
        new int[][] {{1, 2}, {3, 4}})
```

trả String `[[1, 2], [3, 4]]`.

Nhưng generated `record.toString()` với int[][] component không tự sử dụng deepToString. Đừng hardcode các chữ `[I@...` hoặc `[[I@...` vào tests; chúng chứa identity-based details không ổn định.

Dù custom toString để đẹp, **không dùng toString làm định dạng lưu trữ, key hoặc JSON contract**. Serializer nên được thiết kế tường minh; output của toString có thể đổi để phục vụ debug mà không nên làm hỏng dữ liệu.

## 31. Cẩn thận với các thành phần nhạy cảm

Nếu component chứa `byte[] secret`, generated toString thường không in thẳng bytes theo nội dung, nhưng đây **không phải cơ chế bảo mật**:

- Record accessor có thể trả internal array reference.
- Code có quyền truy cập record vẫn có thể đọc secret bytes.
- Những components khác như String token có thể lộ nguyên văn trong generated toString.
- Custom formatter có thể in bytes nếu dùng Arrays.toString mà không kiểm dữ liệu nhạy cảm.
- Logs có thể lưu trong hệ thống lâu dài.

Vì vậy hãy xây policy riêng về redaction, key management và access control. **Không dựa vào array identity string như một dạng mã hóa bí mật**.

## 32. Không cần clone sâu mọi mảng bằng mọi giá

Deep copying có chi phí bộ nhớ, CPU và thiết kế. Hãy hỏi:

1. Object có phải immutable value không?
2. Có ai giữ reference tới input array không?
3. Array chứa primitives, immutable references hay mutable objects?
4. Object có dùng làm map key không?
5. Có cần trả dữ liệu từ accessor với no-copy performance contract không?
6. Mảng hai chiều có cần rectangular validation không?
7. Tập dữ liệu có quá lớn để clone mỗi lần đọc không?

Nếu domain cho phép mutable shared buffer, record với final reference nhưng mutable contents có thể là API có chủ đích, miễn contract ghi rõ. Nếu muốn true immutable value, cân nhắc representation khác thay vì che giấu chi phí copy.

## 33. Self-test một record vector giá trị

Tạo **`VectorRecordSelfTest.java`**:

```java
import java.util.Arrays;

record Vector(int[] values) {
    Vector {
        values = values.clone();
    }

    @Override
    public int[] values() {
        return values.clone();
    }

    @Override
    public boolean equals(Object other) {
        return this == other
                || (other instanceof Vector v
                    && Arrays.equals(values, v.values));
    }

    @Override
    public int hashCode() {
        return Arrays.hashCode(values);
    }

    @Override
    public String toString() {
        return "Vector" + Arrays.toString(values);
    }
}

public class VectorRecordSelfTest {
    static void check(boolean ok, String label) {
        if (!ok) {
            throw new AssertionError(label);
        }
    }

    public static void main(String[] args) {
        int[] input = {1, 2};

        Vector a = new Vector(input);
        Vector b = new Vector(new int[] {1, 2});
        Vector c = new Vector(new int[] {2, 1});
        Vector copy = new Vector(a.values());

        check(a.equals(a), "reflexive");
        check(a.equals(b) && b.equals(a), "symmetric");
        check(!a.equals(c), "ordered contents");
        check(a.equals(copy), "copy invariant");
        check(a.hashCode() == b.hashCode(),
                "hash consistency");
        check(!a.equals(null), "null");

        input[0] = 9;
        int[] exposed = a.values();
        exposed[1] = 8;

        check(a.equals(b), "defensive copies");
        check(a.toString().equals("Vector[1, 2]"),
                "display");

        System.out.println("vector PASS");
    }
}
```

```bash
javac VectorRecordSelfTest.java
java VectorRecordSelfTest
```

```text
vector PASS
```

`check` ném AssertionError trực tiếp, không cần bật `-ea`. Ngoài những checks này, có thể thêm empty arrays, null policy, rất nhiều phần tử và performance. Self-test không tự chứng minh mọi concurrency property hoặc deep immutability với object element types.

## 34. Bài tập 1: dự đoán equality và mutation

Cho đoạn:

```java
record Data(int[] values) {}

int[] source = {3, 4};
Data a = new Data(source);
Data b = new Data(source);
Data c = new Data(new int[] {3, 4});
```

Đây là **mảnh minh họa** ở vị trí sau record declaration trong một method hợp lệ.

Hãy tự trả lời:

1. `a == b`?
2. `a.equals(b)`?
3. `a.equals(c)`?
4. `Arrays.equals(a.values(), c.values())`?
5. `a.hashCode() == b.hashCode()`?
6. Có thể khẳng định `a.hashCode() != c.hashCode()` không?
7. Sau `source[0] = 99`, `a.values()[0]` là bao nhiêu?

**Đáp án:** 1 false; 2 true; 3 false; 4 true trước mutation; 5 true; 6 không, hash collision có thể xảy ra; 7 bằng 99 do shared reference.

## 35. Bài tập 2: sửa một record đang có giá trị bất ổn

Yêu cầu thiết kế `Measurements(int[] readings)` sao cho:

- Cấm null.
- Sao chép đầu vào và đầu ra.
- Hai records equal khi có cùng dãy số theo thứ tự.
- Hash dựa theo từng phần tử.
- toString in đúng `Measurements[10, 20]` với mảng 10,20.
- Tạo copy từ accessor phải equal.

### Lời giải runnable

Tạo **`MeasurementsExercise.java`**:

```java
import java.util.Arrays;
import java.util.Objects;

record Measurements(int[] readings) {
    Measurements {
        readings = Objects.requireNonNull(readings).clone();
    }

    @Override
    public int[] readings() {
        return readings.clone();
    }

    @Override
    public boolean equals(Object other) {
        return this == other
                || (other instanceof Measurements m
                    && Arrays.equals(readings, m.readings));
    }

    @Override
    public int hashCode() {
        return Arrays.hashCode(readings);
    }

    @Override
    public String toString() {
        return "Measurements" + Arrays.toString(readings);
    }
}

public class MeasurementsExercise {
    public static void main(String[] args) {
        int[] input = {10, 20};
        Measurements a = new Measurements(input);
        Measurements b =
                new Measurements(new int[] {10, 20});

        input[0] = 999;

        System.out.println(a.equals(b));
        System.out.println(
                a.hashCode() == b.hashCode());
        System.out.println(a);
    }
}
```

```bash
javac MeasurementsExercise.java
java MeasurementsExercise
```

```text
true
true
Measurements[10, 20]
```

**Giới hạn của lời giải:** Đây là array primitive một chiều với equality có xét thứ tự. Nếu cần so như set không có thứ tự, hoặc nested mutable objects, cần algorithm/representation khác.

## 36. Bảng quyết định

| Kiểu component và mục đích | `equals` | `hashCode` | Hiển thị |
| --- | --- | --- | --- |
| Primitive/String immutable | Generated | Generated | Generated |
| Immutable `List<Integer>` | Generated | Generated | Generated |
| `int[]` mà identity là contract | Generated theo reference | Generated | Generated hoặc custom |
| `int[]` muốn content equality | `Arrays.equals` | `Arrays.hashCode` | `Arrays.toString` |
| `String[]` muốn content equality | `Arrays.equals` | `Arrays.hashCode` | `Arrays.toString` |
| `int[][]` muốn deep content | `Arrays.deepEquals` | `Arrays.deepHashCode` | `Arrays.deepToString` |
| `Object[]` lồng arrays | `Arrays.deepEquals` nếu phù hợp | `Arrays.deepHashCode` | `Arrays.deepToString` |
| Secrets/tokens | Theo nghiệp vụ, tránh mutable alias | Đồng bộ với equals | Redact, không in raw secrets |

**Đừng thay `deepHashCode` bằng `hashCode` thường trong khi equals dùng deepEquals**: hai contents bằng nhau nhưng nested array references khác nhau có thể tạo hash khác, phá contract.

## 37. Checklist review

- [ ] Tôi có biết record nào chứa array hoặc nested mutable reference không?
- [ ] Miền dữ liệu cần so **array identity** hay **array contents**?
- [ ] Không nhầm `array.equals(other)` với `Arrays.equals`?
- [ ] Với matrix, đã cân nhắc `Arrays.deepEquals`?
- [ ] Nếu custom equals, custom hash dùng đúng cùng semantics?
- [ ] Không khẳng định unequal objects luôn có hash khác?
- [ ] Không hardcode giá trị hash hoặc array identity suffix trong stdout/tests?
- [ ] Custom toString có được coi là formatter, không là serializer?
- [ ] Input array có còn được giữ ở caller và mutate về sau không?
- [ ] Accessor có trả internal array reference không?
- [ ] Nếu cần immutable value, đã copy cả input và output chưa?
- [ ] Với 2D array, đã copy từng row chứ không chỉ outer array?
- [ ] Với object array, đã nghĩ đến mutable elements?
- [ ] Copy invariant có được thỏa khi custom defensive copying?
- [ ] Có null policy rõ, không nhầm null với empty array?
- [ ] Record có làm HashMap/HashSet key không?
- [ ] Logical hash values có ổn định khi object dùng làm key không?
- [ ] Có thể thay array component bằng immutable List hoặc named primitives?
- [ ] toString có thể lộ dữ liệu nhạy cảm không?
- [ ] Tests kiểm reflexive/symmetric/transitive, equality/hash và mutation aliasing?
- [ ] Ví dụ Java 17 có tên tệp, public class, lệnh chạy và stdout khớp?

## 38. Câu hỏi ôn tập

**1.** Generated record equals có tự so từng phần tử int[] không?

*Không. Array component dùng reference equality.*

**2.** Hai arrays khác objects nhưng cùng contents thì `Arrays.equals` trả gì?

*True, nếu cùng các phần tử theo thứ tự.*

**3.** Hai records khác objects nhưng cùng array reference thì generated equals có thể true không?

*Có, nếu các components khác tương ứng cũng equal.*

**4.** Nếu hai records equal, hashCode phải thế nào?

*Phải bằng nhau. Ngược lại không bắt buộc.*

**5.** Generated toString của int[] thường in dạng gì?

*Biểu diễn array object như `[I@...`, không phải tự động dãy số.*

**6.** `Arrays.toString` và `Arrays.deepToString` khác gì?

*toString xử lý một tầng, deepToString đi qua nested array layers.*

**7.** `int[][]` với các hàng khác references nhưng cùng contents cần method nào?

*Arrays.deepEquals nếu muốn deep contents.*

**8.** Array component field final có làm nội dung array immutable không?

*Không; final giữ reference, elements vẫn mutable.*

**9.** Vì sao phải clone input trong canonical/compact constructor?

*Tránh caller giữ original array alias và sửa internal state.*

**10.** Vì sao phải clone output ở accessor?

*Tránh caller sửa array nội bộ qua reference được trả.*

**11.** Copy cả hai nhưng giữ generated equals có thể gây gì?

*Clone tạo array references khác; record copy có contents giống vẫn không equal.*

**12.** Muốn content equals cho int[] thì cặp methods nào?

*Arrays.equals và Arrays.hashCode.*

**13.** Muốn content equals cho int[][] thì cặp nào?

*Arrays.deepEquals và Arrays.deepHashCode.*

**14.** `List.copyOf` có deep-copy Mutable elements không?

*Không.*

**15.** Vì sao record với `List<int[]>` vẫn có thể unequal dù nội dung các arrays giống?

*List.equals dùng equals của từng element int[], vốn là array identity equality.*

**16.** Vì sao record array dùng làm HashMap key có thể tra cứu không được bằng mảng mới cùng nội dung?

*Key mới không equal theo generated array semantics.*

**17.** Nếu hashCode dựa trên contents của mutable array, nguy cơ khi dùng làm Map key?

*Mutation có thể đổi hash sau map.put khiến lookup hỏng.*

**18.** Vì sao toString giống nhau không đồng nghĩa equals?

*Formatter có thể tạo cùng text từ objects không equal.*

**19.** Khi nào giữ generated equality cho array lại đúng?

*Khi domain cố ý so cùng buffer/array object identity thay vì contents.*

**20.** Khi nào nên chọn primitive components hoặc immutable List thay mảng?

*Khi logical value semantics và API clarity quan trọng hơn việc expose array reference.*

---

**Ghi nhớ cuối bài:** Record tạo `equals`, `hashCode`, `toString` dựa trên **chính các thành phần đã khai báo**, nhưng **không tự cho mảng content equality**. Với component `int[]`, hai records chứa hai arrays khác identity vẫn có thể unequal dù numbers bằng nhau. Generated `hashCode` không phải content hash của mảng và generated `toString` không phải pretty printer của nội dung. Muốn một record mang **giá trị dãy số** đúng nghĩa: xác định null/mutation policy, defensive-copy ở constructor/accessor, dùng `Arrays.equals + Arrays.hashCode` (hoặc các `deep` methods cho nested arrays), tùy chọn custom `toString`. Khi các elements có sẵn value semantics và bất biến, một `List.copyOf` hoặc nhiều components primitive có tên đôi khi đơn giản hơn. Sự nhất quán giữa equality, hash, ownership và lifecycle đặc biệt quan trọng khi record được dùng làm key trong Map/Set.