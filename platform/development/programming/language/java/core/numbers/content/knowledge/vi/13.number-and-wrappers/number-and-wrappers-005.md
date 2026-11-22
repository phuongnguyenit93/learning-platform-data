# Wrapper bất biến và ngữ nghĩa value-based trong Java

## 1. Mục tiêu

Trong Java, mỗi kiểu nguyên thủy có một lớp bọc (*wrapper*) tương ứng. Các lớp bọc cho phép đưa giá trị primitive vào những API yêu cầu đối tượng, chẳng hạn `List<Integer>`, `Map<Long, String>`, `Optional<Double>` hoặc các phương thức nhận `Object`/`Number`.

Điểm quan trọng nhất: **các wrapper là bất biến (immutable) và được Java mô tả là những lớp value-based**. Lập trình viên nên quan tâm đến **giá trị** của chúng, không dựa vào danh tính đối tượng (object identity). Bất biến giúp chia sẻ giá trị an toàn, nhưng không đồng nghĩa các wrapper là primitive hoặc Java đảm bảo hai đối tượng cùng giá trị luôn có cùng địa chỉ/tham chiếu.

Sau bài học, bạn cần giải thích được:

- Vì sao không thể “sửa trực tiếp” nội dung bên trong `Integer`, `Long`, `Double` hay `Boolean`.
- Vì sao `x++` hoặc `x = x + 1` trên biến wrapper không làm wrapper cũ thay đổi.
- Vì sao `equals()` thường đúng mục đích so sánh **giá trị**, còn `==` giữa hai tham chiếu wrapper lại có thể tạo lỗi khó phát hiện.
- Vai trò của `valueOf()`, autoboxing, unboxing và vùng cache của `Integer`.
- Tại sao không nên dùng wrapper làm khóa của `synchronized`, `IdentityHashMap` hoặc các phép xử lý dựa vào identity.
- Các ngoại lệ quan trọng của `Double.equals()`/`Float.equals()` đối với NaN và hai số không có dấu khác nhau `+0.0`/`-0.0`.

Bài sử dụng Java 17+; kiến thức value-based ở đây là hợp đồng API hiện hành và định hướng thiết kế Java, không yêu cầu dùng tính năng preview.

## 2. Primitive và wrapper khác nhau như thế nào?

| Primitive | Wrapper | Ví dụ |
| --- | --- | --- |
| `boolean` | `Boolean` | `Boolean.TRUE` |
| `byte` | `Byte` | `Byte.valueOf((byte) 12)` |
| `short` | `Short` | `Short.valueOf((short) 12)` |
| `char` | `Character` | `Character.valueOf('A')` |
| `int` | `Integer` | `Integer.valueOf(12)` |
| `long` | `Long` | `Long.valueOf(12L)` |
| `float` | `Float` | `Float.valueOf(1.25f)` |
| `double` | `Double` | `Double.valueOf(1.25)` |

Các wrapper số (trừ `Character` và `Boolean`) là lớp con của `java.lang.Number`. Tất cả tám lớp trên là lớp `final`: không thể viết lớp kế thừa từ chúng. Trong Java hiện đại, tài liệu API của chúng cũng mô tả đây là các **value-based classes**.

Sự khác biệt thực tế:

- Một biến primitive trực tiếp mang giá trị của kiểu đó; `int n = 10;`.
- Một biến wrapper là **tham chiếu đến một đối tượng** chứa giá trị primitive; `Integer n = Integer.valueOf(10);`.
- Tham chiếu wrapper có thể bằng `null`; primitive không có giá trị `null`.
- Wrapper có phương thức như `intValue()`, `compareTo()`, `equals()`, `hashCode()`, `toString()` và các phương thức static như `valueOf()`/parse theo từng lớp.
- Generics thông thường không nhận primitive: `List<int>` không hợp lệ, nhưng `List<Integer>` hợp lệ.

**Không nhầm tính bất biến với một biến `final`:** `final` hạn chế việc **gán lại biến**, còn tính bất biến hạn chế việc **thay đổi trạng thái của đối tượng đã có**. Hai khái niệm độc lập.

## 3. Wrapper bất biến: đối tượng cũ không bị sửa

Một đối tượng `Integer` đã biểu diễn số 10 sẽ tiếp tục biểu diễn số 10 trong suốt vòng đời của đối tượng đó. Lớp không cung cấp `setValue()` hoặc cơ chế hợp lệ nào để thay giá trị primitive bên trong.

~~~java
Integer first = Integer.valueOf(10);
Integer saved = first;

first = Integer.valueOf(20);

System.out.println(saved); // 10
System.out.println(first); // 20
~~~

Đây là **đoạn minh họa trong một phương thức**, không phải chương trình chạy độc lập. Lệnh gán `first = ...` làm biến `first` trỏ đến một giá trị wrapper khác; `saved` vẫn giữ giá trị 10.

Cùng nguyên tắc với `Long`, `Short`, `Double`, `Boolean` và các wrapper còn lại. Một lời gọi như `Integer.sum(a, b)` hoặc `Math.abs(n)` tính **giá trị kết quả**; nó không sửa đối tượng nguồn.

### Bất biến khác với final

~~~java
Integer changeableReference = 7;
changeableReference = 9; // hợp lệ: biến không final

final Integer fixedReference = 7;
// fixedReference = 9;  // lỗi biên dịch: không được gán lại final
~~~

Trong cả hai trường hợp, những đối tượng wrapper mang giá trị 7 vẫn bất biến. `final` không phải điều kiện làm cho wrapper bất biến.

### Biến wrapper tăng ++ thực sự làm gì?

~~~java
Integer counter = 5;
Integer before = counter;
counter++;

System.out.println(before);  // 5
System.out.println(counter); // 6
~~~

Về mặt giá trị, Java thực hiện **unboxing → cộng một trên primitive → boxing** rồi **gán lại** tham chiếu `counter`. Đối tượng gốc không bị sửa. Các quy tắc tràn của primitive vẫn áp dụng: tăng `Integer.MAX_VALUE` sẽ quay về `Integer.MIN_VALUE`, chứ wrapper không tự mở rộng miền số.

### Một lớp dữ liệu bất biến khác

`BigInteger` và `BigDecimal` cũng bất biến: `value.add(...) ` trả về kết quả mới thay vì sửa receiver. Tuy nhiên, chúng không phải wrapper primitive, có miền/độ chính xác và hợp đồng API riêng. Khái niệm “immutable” rộng hơn khái niệm “wrapper” và cũng rộng hơn danh sách lớp được API đánh dấu *value-based*.

## 4. Value-based nghĩa là gì?

Theo tài liệu API Java, những đối tượng của một lớp **value-based** phải được ứng dụng đối xử như **giá trị**: các instance được coi là bằng nhau theo `equals()` thì nên có thể thay thế cho nhau trong những phép sử dụng dựa trên giá trị.

Các hệ quả thiết kế:

1. **Đừng dùng identity làm dữ liệu nghiệp vụ:** tránh kết luận hai wrapper đại diện hai thực thể khác nhau chỉ bởi vì hai tham chiếu không `==`.
2. **Đừng dùng wrapper làm monitor trong `synchronized`:** một số instance có thể được chia sẻ bởi cache hoặc cơ chế tạo đối tượng khác. Java cũng cảnh báo rằng đồng bộ hóa theo value-based instance có thể có hành vi không đoán trước và có thể không còn được hỗ trợ trong tương lai.
3. **Đừng phụ thuộc vào `System.identityHashCode(wrapper)`, `IdentityHashMap` hay phép tra cứu dựa trên object identity** để lưu ý nghĩa của giá trị.
4. **Đừng dựa vào số lượng đối tượng được cấp phát** bởi `valueOf()` hay boxing. Triển khai JVM có thể tái sử dụng hoặc tối ưu đối tượng khi điều đó tương thích với hợp đồng của lớp.

Điều này **không** có nghĩa wrapper không phải đối tượng ở Java 17. `Integer` vẫn có kiểu tham chiếu, có thể là `null`, có `equals()` và `hashCode()`, và có thể được sử dụng làm khóa trong `HashMap`. Value-based là **cách dùng đúng theo hợp đồng API**, không phải tuyên bố rằng Java 17 đã biến `Integer` thành một kiểu nguyên thủy hoặc một *value class* mới của JVM.

Bất biến và value-based có liên quan nhưng **không đồng nhất**: một đối tượng có thể bất biến mà ứng dụng vẫn cần identity (ví dụ một token danh tính với hợp đồng riêng). Với wrapper, API đã xác định rõ ngữ nghĩa hướng về **giá trị**.

## 5. So sánh: equals() và ==

### Hai wrapper cùng kiểu: hãy so sánh giá trị

~~~java
Integer left = Integer.valueOf(1000);
Integer right = Integer.valueOf(1000);

System.out.println(left.equals(right)); // true
~~~

Không nên viết `left == right` để so sánh giá trị khi **cả hai toán hạng đều là tham chiếu** `Integer`. Khi đó `==` là phép so sánh **cùng đối tượng tham chiếu hay không**, không phải phép so sánh số học.

Điểm dễ nhầm: nếu một toán hạng là primitive, Java có thể unbox wrapper và biến `==` thành **so sánh số học**:

~~~java
Integer boxed = Integer.valueOf(1000);
System.out.println(boxed == 1000); // true: unboxing boxed thành int
~~~

Vì vậy có những câu lệnh nhìn gần giống nhau nhưng `==` có **hai ngữ nghĩa khác nhau** tùy kiểu của toán hạng lúc biên dịch.

### equals so sánh đúng lớp wrapper

~~~java
Integer oneInt = Integer.valueOf(1);
Long oneLong = Long.valueOf(1L);

System.out.println(oneInt.equals(oneLong)); // false
~~~

Hai đối tượng chứa cùng giá trị toán học 1 nhưng `Integer.equals(Object)` chỉ bằng một đối tượng `Integer` cùng giá trị; `Long` không phải `Integer`. Không nên gọi `equals()` giữa các wrapper khác kiểu rồi mong Java tự chuyển số hoặc nâng kiểu như khi cộng primitive.

Nếu thực sự muốn so sánh số học của hai kiểu nguyên, hãy **chuyển có kiểm soát** sang một kiểu có miền thích hợp (ví dụ `long` cho `int` và `long`), hoặc `BigInteger` cho giá trị lớn; với `float`/`double`, cân nhắc sai số và các giá trị đặc biệt.

### Null-safe equality

~~~java
Integer nullable = null;
Integer expected = 10;

System.out.println(java.util.Objects.equals(nullable, expected)); // false
System.out.println(java.util.Objects.equals(null, null));          // true
~~~

`Objects.equals(a, b)` xử lý an toàn trường hợp một hoặc cả hai tham chiếu là `null`. Nó không tự chuyển giá trị từ `Integer` sang `Long` hay thay đổi hợp đồng `equals()` của lớp.

## 6. Cache và Integer.valueOf(): lợi ích có, identity không phải hợp đồng ứng dụng

`Integer.valueOf(int)` **luôn cache** các giá trị từ **−128 đến 127** theo tài liệu Java 17 và **có thể cache thêm** các giá trị khác, tùy môi trường. Vì thế:

~~~java
Integer a = Integer.valueOf(42);
Integer b = Integer.valueOf(42);

System.out.println(a == b);      // true: ví dụ về cache được bảo đảm cho khoảng này
System.out.println(a.equals(b));  // true
~~~

Tuy nhiên, nếu dùng 1000:

~~~java
Integer x = Integer.valueOf(1000);
Integer y = Integer.valueOf(1000);

System.out.println(x.equals(y)); // true
// Không dựa vào (x == y): trạng thái cache ngoài -128..127 không được bảo đảm.
~~~

**Bài học:** dù `a == b` tình cờ đúng nhờ cache ở nhiều trường hợp, không dùng identity để kết luận hai giá trị có bằng nhau. Một đoạn code chạy đúng với 42 nhưng sai với 1000 là lỗi điển hình khi phụ thuộc vào object identity.

`Integer.valueOf` thường ưu tiên hơn tạo đối tượng qua constructor. Các constructor như `new Integer(int)` đã **deprecated for removal** trong Java 17; chúng tạo ra identity không cần thiết và không phải hướng tạo wrapper nên dùng. Tương tự, boxing tự động thường đi qua cơ chế tạo wrapper phù hợp chứ không phải lệnh sửa một đối tượng đang có.

Không nên suy rằng mọi wrapper đều có chính sách cache giống `Integer`: phạm vi được bảo đảm khác nhau theo lớp và kiểu; điều ổn định cho logic nghiệp vụ là dùng **`equals()` và `hashCode()` theo giá trị**.

## 7. Autoboxing và unboxing: tiện nhưng có chi phí và rủi ro

**Autoboxing** chuyển primitive thành wrapper ở ngữ cảnh thích hợp:

~~~java
int primitive = 7;
Integer boxed = primitive; // tương tự dùng Integer.valueOf(...)
~~~

**Unboxing** lấy giá trị primitive từ wrapper:

~~~java
Integer boxed = 7;
int primitive = boxed; // tương tự boxed.intValue()
~~~

Điều này khiến Java cho phép:

~~~java
Integer a = 2;
Integer b = 3;
Integer sum = a + b; // unboxing hai số, cộng int, boxing kết quả
System.out.println(sum); // 5
~~~

Quá trình trên **không** làm `a` hoặc `b` thay đổi. Phép `+` thực hiện trên các giá trị primitive theo quy tắc ngôn ngữ; chẳng hạn phép cộng `int` vẫn có thể tràn.

### Unboxing null ném NullPointerException

~~~java
Integer quantity = null;
// int count = quantity; // khi chạy sẽ ném NullPointerException
~~~

Ngay cả khi không gán rõ ràng sang `int`, một phép toán yêu cầu unboxing như `quantity + 1`, `quantity > 0` hoặc `quantity == 0` cũng có thể ném `NullPointerException`. Ngược lại, `quantity == null` là phép kiểm tra tham chiếu hợp lệ và không yêu cầu unboxing.

Không giả định giá trị wrapper lấy từ database, JSON, `Map.get()` hoặc API có thể trả `null` luôn hợp lệ. Dùng cách xử lý thiếu dữ liệu theo hợp đồng (validation, fallback có ý nghĩa hoặc thông báo lỗi).

### Hiệu năng

Tạo/đọc wrapper có thể làm phát sinh boxing/unboxing, đối tượng và truy cập bộ nhớ. Bộ biên dịch JIT có thể tối ưu một số trường hợp, nhưng ứng dụng không nên dựa vào một số lượng cấp phát cụ thể.

Với vòng lặp tính toán rất lớn, ưu tiên `int`, `long`, `double` và mảng primitive khi phù hợp. Với API generic/collection yêu cầu đối tượng, wrapper vẫn là lựa chọn tiêu chuẩn. Chỉ tối ưu dựa trên profiling và yêu cầu thật của chương trình.

## 8. Wrapper trong collection: HashMap, HashSet và bất biến

Các collection theo giá trị, như `HashMap` và `HashSet`, dùng `equals()`/`hashCode()` để nhận biết khóa/phần tử tương đương. Wrapper rất phù hợp làm khóa vì trạng thái giá trị của đối tượng không tự thay đổi sau khi chèn.

~~~java
java.util.Map<Integer, String> labels = new java.util.HashMap<>();
labels.put(Integer.valueOf(1000), "thousand");

String found = labels.get(Integer.valueOf(1000));
System.out.println(found); // thousand
~~~

Không cần bảo đảm hai lần `valueOf(1000)` trả về **cùng một object**: `Integer.equals()` và `hashCode()` giúp tra cứu theo giá trị.

Điều này khác với:

~~~java
java.util.Map<Integer, String> identityMap = new java.util.IdentityHashMap<>();
// Không dùng IdentityHashMap nếu nghiệp vụ cần tra cứu khóa số theo giá trị.
~~~

`IdentityHashMap` kiểm tra khóa theo `==`, vì vậy có thể cho hành vi khác với `HashMap` và chính sách tái sử dụng wrapper. Nó được thiết kế cho những tình huống **thật sự cần nhận diện object**, không phải bảng tra khóa số nguyên thông thường.

Lưu ý wrapper bất biến **không làm collection bất biến**. `labels.put(1000, "...")` vẫn có thể thay đổi dữ liệu của map; nó chỉ không thay đổi giá trị primitive chứa trong wrapper khóa.

## 9. Không dùng wrapper làm monitor đồng bộ hóa

Một đoạn code như sau là **mẫu cần tránh**:

~~~java
// Ví dụ sai về thiết kế, không sử dụng trong ứng dụng:
// Integer lock = Integer.valueOf(1);
// synchronized (lock) {
//     // critical section
// }
~~~

Vấn đề:

- `Integer.valueOf(1)` có thể trả object cache dùng chung với code hoàn toàn không liên quan. Hai luồng/khối code không chủ ý vẫn có thể dùng chung monitor.
- Nếu gán lại biến wrapper, các lệnh `synchronized` trong những lần chạy khác nhau có thể khóa **những đối tượng khác nhau**.
- Tài liệu chính thức cảnh báo wrapper là *value-based* và không nên được sử dụng để đồng bộ hóa; Java có thể thay đổi cách hỗ trợ identity của các giá trị này trong tương lai.
- Trình biên dịch Java 17 có thể phát cảnh báo với lệnh `synchronized` trên một instance của lớp value-based (liên quan JEP 390).

Hãy dùng một đối tượng khóa có identity được dành riêng cho việc đồng bộ:

~~~java
public class SafeCounter {
    private final Object lock = new Object();
    private int value;

    public void increment() {
        synchronized (lock) {
            value++;
        }
    }

    public int get() {
        synchronized (lock) {
            return value;
        }
    }
}
~~~

Đây là **lớp độc lập có thể biên dịch** (lưu thành `SafeCounter.java`) nhưng không có `main`. Với bộ đếm đơn giản cần thao tác atomic trên nhiều luồng, `AtomicInteger` có thể thích hợp; đó là **lớp có trạng thái có thể thay đổi**, không phải wrapper bất biến `Integer`.

## 10. Float và Double: equals khác == ở NaN và signed zero

Wrapper dấu phẩy động phải hỗ trợ một quan hệ `equals()` nhất quán cho những collection như `HashMap`/ `HashSet`. Vì vậy, `Double.equals()` và `Float.equals()` có **quy tắc khác phép `==` trên primitive** ở hai trường hợp đặc biệt.

| Tình huống | Primitive `double == double` | `Double.equals()` |
| --- | --- | --- |
| `1.0` và `1.0` | `true` | `true` |
| `Double.NaN` và `Double.NaN` | `false` | `true` |
| `+0.0` và `-0.0` | `true` | `false` |

Ví dụ:

~~~java
Double nanA = Double.valueOf(Double.NaN);
Double nanB = Double.valueOf(Double.NaN);
System.out.println(nanA.equals(nanB)); // true
System.out.println(nanA.doubleValue() == nanB.doubleValue()); // false

Double positiveZero = Double.valueOf(+0.0);
Double negativeZero = Double.valueOf(-0.0);
System.out.println(positiveZero.equals(negativeZero)); // false
System.out.println(positiveZero.doubleValue() == negativeZero.doubleValue()); // true
~~~

`Double.equals()` dựa trên biểu diễn theo `Double.doubleToLongBits()`, chuẩn hóa các bit pattern NaN để tất cả NaN được coi bằng nhau nhưng giữ phân biệt dấu của zero. `Float.equals()` có cơ chế tương tự dùng `Float.floatToIntBits()`.

Điều này **không phải mâu thuẫn với value-based**: khái niệm “hai instance bằng nhau” được xác định bằng **`equals()` của lớp**, không nhất thiết bằng toán tử số học `==` của primitive.

### compareTo và thứ tự toàn phần của wrapper floating point

`Double.compare()`/`Double.compareTo()` thiết lập thứ tự phù hợp với `Double.equals()`:

- `-0.0` được xếp **nhỏ hơn** `+0.0`.
- `NaN` được xếp cao hơn mọi giá trị `double` khác, kể cả `+Infinity`; các NaN so sánh bằng nhau theo thứ tự này.

Đây là lựa chọn để `Double` làm phần tử trong các collection có thứ tự như `TreeSet`. Đừng suy rằng `Double.compare(a, b)` luôn cho cùng ngữ nghĩa với `a < b` khi có NaN hoặc hai zero khác dấu.

## 11. Chương trình Java 17+ đầy đủ

Lưu mã sau vào tệp `WrapperValueDemo.java`:

~~~java
import java.util.HashMap;
import java.util.Map;
import java.util.Objects;

public class WrapperValueDemo {
    public static void main(String[] args) {
        Integer original = Integer.valueOf(10);
        Integer saved = original;
        original++;

        System.out.println("saved=" + saved);
        System.out.println("after increment=" + original);

        Integer left = Integer.valueOf(1000);
        Integer right = Integer.valueOf(1000);
        System.out.println("same value=" + left.equals(right));
        System.out.println("boxed vs primitive=" + (left == 1000));
        System.out.println("cached 42=" +
                (Integer.valueOf(42) == Integer.valueOf(42)));

        System.out.println("cross type equals=" +
                Integer.valueOf(1).equals(Long.valueOf(1L)));
        System.out.println("null safe=" + Objects.equals(null, null));

        Map<Integer, String> labels = new HashMap<>();
        labels.put(Integer.valueOf(1000), "thousand");
        System.out.println("map lookup=" + labels.get(Integer.valueOf(1000)));

        Double nanA = Double.valueOf(Double.NaN);
        Double nanB = Double.valueOf(Double.NaN);
        System.out.println("NaN wrapper equals=" + nanA.equals(nanB));
        System.out.println("NaN primitive equals=" +
                (nanA.doubleValue() == nanB.doubleValue()));

        Double plusZero = Double.valueOf(+0.0);
        Double minusZero = Double.valueOf(-0.0);
        System.out.println("signed zero wrapper equals=" +
                plusZero.equals(minusZero));
        System.out.println("signed zero primitive equals=" +
                (plusZero.doubleValue() == minusZero.doubleValue()));

        Integer missing = null;
        try {
            int primitive = missing;
            System.out.println(primitive);
        } catch (NullPointerException ex) {
            System.out.println("unboxing null: NPE");
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 17 WrapperValueDemo.java
java WrapperValueDemo
~~~

Stdout:

~~~text
saved=10
after increment=11
same value=true
boxed vs primitive=true
cached 42=true
cross type equals=false
null safe=true
map lookup=thousand
NaN wrapper equals=true
NaN primitive equals=false
signed zero wrapper equals=false
signed zero primitive equals=true
unboxing null: NPE
~~~

**Giải thích những điểm quan trọng:**

1. `original++` tính toán qua unboxing/boxing rồi gán lại biến; `saved` vẫn giữ 10.
2. `left.equals(right)` so sánh **giá trị**, không phụ thuộc hai wrapper 1000 có dùng chung object hay không.
3. `left == 1000` đúng vì toán hạng thứ hai là `int` khiến `left` được unbox. `valueOf(42) == valueOf(42)` đúng do mức cache được bảo đảm; **không áp dụng kết luận identity này cho mọi giá trị**.
4. `Integer(1)` và `Long(1L)` không bằng nhau theo `equals()` vì hai lớp khác nhau.
5. `HashMap` tra khóa theo `equals()`/`hashCode()`, vì vậy hai wrapper cùng giá trị truy xuất được cùng entry.
6. So sánh `NaN` và zero có dấu cho thấy ngữ nghĩa khác nhau giữa wrapper `equals()` và primitive `==`.
7. Unboxing `null` phát sinh `NullPointerException`; chương trình bắt exception và in thông báo.

Đây là ví dụ chạy đơn tiến trình, tập trung vào bất biến, identity và equality. Không cần dùng một khối `synchronized` trên wrapper để minh họa vì đó là mẫu thiết kế nên tránh.

## 12. Áp dụng đúng trong API và thiết kế dữ liệu

### Lựa chọn int hay Integer

Chọn `int` khi dữ liệu luôn có giá trị, cần thao tác tính toán và không có ý nghĩa “chưa biết”. Chọn `Integer` khi API generic/collection yêu cầu object hoặc ứng dụng **thật sự cần phân biệt** `null` với `0`.

Ví dụ, trường `retryCount` có thể dùng `int` với mặc định 0; trường dữ liệu database nullable có thể cần `Integer`. Không tự biến `null` thành `0` nếu chúng có hai ý nghĩa khác nhau.

### Không biến wrapper thành một thực thể có identity

Một giá trị `Integer.valueOf(42)` nên được coi là **số 42**, không phải một “đối tượng người dùng số 42” với vòng đời riêng. Nếu ứng dụng cần biểu diễn thực thể có danh tính, hãy tạo lớp/record domain với định danh riêng, ví dụ `CustomerId` hoặc `Order`, thay vì dùng danh tính của instance wrapper.

### Không chọn monitor từ một giá trị số

Nếu bạn cần một khóa riêng của đối tượng, dùng một trường `private final Object lock = new Object()`, `ReentrantLock` hoặc cấu trúc concurrent phù hợp. Nếu cần cập nhật giá trị đếm đồng thời, cân nhắc `AtomicInteger`/`AtomicLong`. Giá trị số chỉ nên là **dữ liệu**, không phải monitor.

### Tính bất biến không chữa được sai số dấu phẩy động

Một `Double` bất biến vẫn chứa giá trị `double` chịu giới hạn IEEE 754: NaN, Infinity, ±0 và sai số làm tròn vẫn tồn tại. Nếu nghiệp vụ cần số thập phân chính xác, `BigDecimal` có thể phù hợp hơn. Đây là quyết định về **mô hình số học**, không phải quyết định về object identity.

## 13. Lỗi thường gặp

| Lỗi | Hậu quả | Cách xử lý |
| --- | --- | --- |
| `Integer a = 1000, b = 1000; if (a == b)...` | So sánh reference, dễ phụ thuộc cache | `a.equals(b)` hoặc `Objects.equals(a,b)` |
| Dùng `==` trên wrapper chỉ vì với `42` thấy đúng | Hành vi khác khi giá trị/vùng cache thay đổi | So sánh giá trị một cách nhất quán |
| `Integer count = null; count++;` | `NullPointerException` khi unbox | Kiểm tra/null policy |
| Cho rằng `count++` sửa đối tượng `Integer` cũ | Hiểu sai alias và tính bất biến | Đây là unbox, cộng, box, gán lại |
| Dùng `synchronized(Integer.valueOf(id))` | Cache gây chia sẻ monitor ngoài ý muốn; vi phạm hướng dẫn value-based | Dùng lock có identity riêng |
| Dùng `IdentityHashMap<Integer, ...>` cho khóa số | Tra cứu theo `==` thay vì giá trị | `HashMap<Integer, ...>` |
| `Integer.valueOf(1).equals(Long.valueOf(1))` được kỳ vọng true | `equals` đòi đúng loại wrapper | Chuyển có kiểm soát khi muốn so sánh số học giữa các kiểu |
| Cho rằng `Double.NaN == Double.NaN` true | So sánh IEEE 754 không thỏa phản xạ với NaN | Dùng `Double.isNaN` hoặc `Double.equals` đúng ý nghĩa |
| Cho rằng `Double.valueOf(+0.0).equals(Double.valueOf(-0.0))` true | `Double.equals` phân biệt signed zero | Chọn ngữ nghĩa so sánh theo nghiệp vụ |
| Tạo wrapper qua constructor deprecated | Cảnh báo; bỏ qua `valueOf`/boxing | `valueOf` hoặc boxing |
| Dùng `Integer` cho biến đếm trong vòng lặp nóng mà không đánh giá chi phí | Boxing/unboxing và truy cập đối tượng không cần thiết | Primitive khi phù hợp, kiểm thử hiệu năng |

## 14. Câu hỏi tự kiểm tra

**1.** Đoạn sau in gì?

~~~java
Integer a = 5;
Integer b = a;
a = a + 1;
System.out.println(a + ", " + b);
~~~

**Đáp án:** `6, 5`. `a` trỏ đến giá trị wrapper mới; `b` không bị thay đổi.

**2.** Vì sao `Integer.valueOf(42) == Integer.valueOf(42)` đúng nhưng vẫn không nên dùng `==` để so sánh wrapper?

**Đáp án:** `Integer.valueOf` bảo đảm cache từ −128 đến 127. Ngoài miền đó, cache không bảo đảm; quan trọng hơn, `==` giữa hai reference kiểm tra object identity, còn mục đích so sánh số nên dùng `equals()`.

**3.** `Integer.valueOf(1000).equals(Long.valueOf(1000L))` có trả `true` không?

**Đáp án:** Không; `equals()` kiểm tra đúng loại lớp wrapper. Muốn so sánh giá trị số của `int` và `long` thì chuyển sang `long` theo cách rõ ràng và so sánh primitive.

**4.** Có thể đồng bộ bằng `synchronized(Integer.valueOf(1))` nếu chỉ một chỗ trong code sử dụng không?

**Đáp án:** Không nên. Wrapper là lớp value-based, có cơ chế cache và không được thiết kế để trở thành lock identity. Dùng `Object`/lock riêng.

**5.** `Double.valueOf(Double.NaN).equals(Double.valueOf(Double.NaN))` và `Double.NaN == Double.NaN` có giống nhau không?

**Đáp án:** Không; biểu thức thứ nhất `true`, thứ hai `false`. Đây là khác biệt chủ động giữa `Double.equals()` và phép so sánh primitive.

**6.** Một `HashMap<Integer, String>` có thể tra được entry với một wrapper cùng giá trị dù không dùng chung instance không?

**Đáp án:** Có. `HashMap` dùng `hashCode()` và `equals()` để xác định khóa tương đương, không cần identity của wrapper.

## 15. Ghi nhớ và tài liệu tham khảo

- Wrapper là **đối tượng bất biến**, còn biến chứa reference có thể được gán lại nếu không khai báo `final`.
- **Value-based** hướng ứng dụng đến giá trị theo `equals()`; không dùng wrapper làm monitor hay phụ thuộc vào object identity.
- `Integer.valueOf()` bảo đảm cache `-128..127`, nhưng đây **không** phải lý do dùng `==` để so sánh giá trị.
- Autoboxing/unboxing tiện lợi nhưng có thể phát sinh chi phí, mất thông tin khi chuyển kiểu số và ném `NullPointerException` nếu unbox `null`.
- `Double.equals()`/`Float.equals()` xử lý NaN và signed zero khác `==` của primitive; chọn đúng phép so sánh theo hợp đồng API.
- Với khóa số trong collection, dùng `HashMap`/`HashSet`; với tính toán nhiều lần, cân nhắc primitive; với đồng bộ, dùng lock riêng hoặc lớp concurrent phù hợp.

Nguồn chính thức:

- [Java SE 17 — Integer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Integer.html): value-based, `valueOf`, cache, `equals`, constructor deprecated.
- [Java SE 17 — Double](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Double.html): equality cho NaN và signed zero; mô tả value-based.
- [Java SE 17 — Objects](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Objects.html): `Objects.equals`.
- [JEP 390 — Warnings for Value-Based Classes](https://openjdk.org/jeps/390): rủi ro liên quan identity và synchronized trên đối tượng value-based.
- [JLS SE 17 — Boxing Conversion](https://docs.oracle.com/javase/specs/jls/se17/html/jls-5.html#jls-5.1.7) và [Unboxing Conversion](https://docs.oracle.com/javase/specs/jls/se17/html/jls-5.html#jls-5.1.8): quy tắc chuyển đổi tự động.
