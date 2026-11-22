# Cache wrapper và giới hạn không nên dùng làm hợp đồng nhận dạng trong Java

## 1. Vấn đề: hai đối tượng có cùng giá trị chưa chắc là cùng đối tượng

Khi làm việc với `Integer`, `Long`, `Short`, `Byte` và các lớp wrapper khác, có hai câu hỏi **khác nhau**:

1. **Hai đối tượng biểu diễn cùng một giá trị hay không?** Thông thường dùng `equals` theo hợp đồng của lớp wrapper, hoặc dùng toán tử số học sau khi unbox nếu đã kiểm tra `null`.
2. **Hai biến tham chiếu có trỏ đến chính cùng một đối tượng hay không?** Với hai tham chiếu, `==` kiểm tra *reference identity*.

Java có cơ chế **cache wrapper**: một số lần boxing hoặc gọi `valueOf` có thể trả về đối tượng đã được dùng trước đó thay vì cấp phát đối tượng mới. Vì vậy, `==` giữa một số cặp wrapper có giá trị nhỏ có thể trả `true`, trong khi các giá trị khác có thể trả `false`.

Điều quan trọng nhất của bài học:

> **Cache wrapper không phải hợp đồng nhận dạng số.** Đừng dùng `==` giữa hai tham chiếu wrapper để quyết định chúng có cùng giá trị số, và đừng dùng wrapper làm khóa khóa đồng bộ dựa vào identity.

Ví dụ cơ bản:

```java
Integer a = Integer.valueOf(127);
Integer b = Integer.valueOf(127);
System.out.println(a == b);      // true: thuộc phạm vi cache được bảo đảm

Integer x = Integer.valueOf(200);
Integer y = Integer.valueOf(200);
System.out.println(x.equals(y)); // true: cùng kiểu Integer và cùng giá trị
```

Không kết luận rằng `x == y` **luôn** `false`. Việc cache thêm giá trị ngoài miền bảo đảm tùy triển khai và cấu hình JVM. Điều chắc chắn để kiểm tra giá trị là `x.equals(y)`.

## 2. Wrapper là đối tượng; boxing và unboxing là chuyển đổi

Java có sáu wrapper số quen thuộc:

| Primitive | Wrapper | Ví dụ tạo từ primitive |
| --- | --- | --- |
| `byte` | `Byte` | `Byte.valueOf((byte) 12)` |
| `short` | `Short` | `Short.valueOf((short) 12)` |
| `int` | `Integer` | `Integer.valueOf(12)` |
| `long` | `Long` | `Long.valueOf(12L)` |
| `float` | `Float` | `Float.valueOf(12.0f)` |
| `double` | `Double` | `Double.valueOf(12.0)` |

Mỗi wrapper là lớp `final`, bất biến, mở rộng `Number`. Đối tượng wrapper có **identity** như một đối tượng tham chiếu; nhưng giá trị số mà nó giữ mới là điều thường có ý nghĩa cho nghiệp vụ.

**Boxing** biến primitive thành wrapper:

```java
int primitive = 42;
Integer boxed = primitive; // autoboxing; tương đương ý nghĩa với Integer.valueOf
```

**Unboxing** lấy primitive từ wrapper:

```java
Integer boxed = Integer.valueOf(42);
int primitive = boxed; // gọi chuyển đổi giá trị tương ứng
```

Java tự chèn boxing/unboxing trong nhiều trường hợp, kể cả gán, phép toán, một số phép so sánh và thao tác collection. Những chuyển đổi đó có thể làm code trông như chỉ đang thao tác số, dù trong thực tế có tham chiếu đối tượng và nguy cơ `null`.

Các phương thức `valueOf` là lựa chọn tạo wrapper thông thường. Các constructor kiểu `new Integer(...)`, `new Long(...)` đã bị deprecate, được đánh dấu hướng tới loại bỏ trong Java hiện đại; không nên tạo đối tượng mới chỉ để ép kiểm tra identity. Nếu nghiệp vụ thật sự cần một thực thể có định danh riêng, hãy định nghĩa lớp thực thể có ID phù hợp.

## 3. Cache wrapper thực sự bảo đảm điều gì?

### 3.1. Phạm vi cache được bảo đảm

Các factory `valueOf` của nhóm wrapper nguyên có cam kết tái sử dụng các đối tượng trong phạm vi sau:

| Wrapper | Phạm vi có đối tượng cache được bảo đảm qua `valueOf` | Ghi chú |
| --- | --- | --- |
| `Byte` | Toàn bộ miền `byte`: `-128..127` | Mọi giá trị `byte` đều nằm trong miền này |
| `Short` | `-128..127` | Có thể cache thêm giá trị |
| `Integer` | `-128..127` | Có thể cache thêm giá trị |
| `Long` | `-128..127` | Có thể cache thêm giá trị |
| `Float` | **Không có cam kết phạm vi cache kiểu trên** | Không suy ra identity từ cùng giá trị |
| `Double` | **Không có cam kết phạm vi cache kiểu trên** | Không suy ra identity từ cùng giá trị |

Với `Byte.valueOf`, mọi giá trị hợp lệ đều thuộc khoảng `-128..127`. Với `Short.valueOf`, `Integer.valueOf` và `Long.valueOf`, giá trị trong khoảng đó được trả về từ cache như cam kết của API. Ngoài khoảng, việc hai lời gọi trả về cùng một đối tượng **không phải hợp đồng được bảo đảm**.

```java
Byte a = Byte.valueOf((byte) -128);
Byte b = Byte.valueOf((byte) -128);
// a == b được bảo đảm true

Short c = Short.valueOf((short) 127);
Short d = Short.valueOf((short) 127);
// c == d được bảo đảm true

Long e = Long.valueOf(127L);
Long f = Long.valueOf(127L);
// e == f được bảo đảm true
```

Có các wrapper khác như `Boolean` và `Character` nhưng chúng không thuộc sáu lớp số nói trên. `Boolean.valueOf` trả các instance `TRUE` hoặc `FALSE`; `Character.valueOf` bảo đảm cache các ký tự từ `'\u0000'` đến `'\u007f'`. Những ví dụ này nhấn mạnh rằng **mỗi API có hợp đồng riêng**; không có quy tắc “tất cả wrapper cache `-128..127`”.

### 3.2. Quy tắc boxing trong đặc tả Java

Ngoài cam kết API của `valueOf`, đặc tả Java quy định những trường hợp kết quả boxing có identity được chia sẻ, đáng chú ý gồm các biểu thức hằng (constant expression) kiểu `byte`, `short`, `int`, `long` trong `-128..127`, `char` trong `0..127`, và các giá trị `boolean`.

Nhưng **đừng diễn dịch ngược** rằng mọi phép boxing của bất kỳ biểu thức nào, ở mọi giá trị hoặc mọi wrapper, đều có identity ổn định. Đặc tả cho phép triển khai chia sẻ thêm đối tượng trong một số trường hợp và các tối ưu triển khai có thể thay đổi.

Một ví dụ thường thấy:

```java
Integer a = 100;
Integer b = 100;
System.out.println(a == b); // true trong phạm vi bảo đảm

Integer x = 200;
Integer y = 200;
// Không dựa vào x == y để xác định cùng giá trị
```

Trường hợp thứ hai có thể tạo hai đối tượng hoặc dùng cache mở rộng. **Ứng dụng phải cho cùng quyết định nghiệp vụ trên mọi JVM hợp lệ**, dù kết quả identity có thể khác.

### 3.3. Cache không phải “tập đối tượng có ID số”

Cache giúp giảm số lần cấp phát wrapper thường gặp, nhất là các giá trị nhỏ. Nhưng các giá trị nguyên thủy như `42` không có identity; identity chỉ là thuộc tính của tham chiếu đối tượng wrapper cụ thể.

Không được coi cache như một cơ chế *interning* tổng quát có thể thay cho:

- định danh bản ghi, mã người dùng hay khóa nghiệp vụ;
- cơ chế singleton do ứng dụng thiết kế;
- bộ khóa đồng bộ riêng;
- quan hệ `equals` và `hashCode` trong `HashMap`/`HashSet`.

Việc dùng wrapper để đại diện ID hoàn toàn hợp lệ (ví dụ `Map<Integer, Customer>`), **nếu giá trị được so sánh bằng `equals`**, không phải vì hai tham chiếu `Integer` phải trỏ đến cùng một instance.

## 4. `==` giữa hai wrapper khác `==` khi có primitive

Cùng ký hiệu `==` có thể dẫn đến hai cơ chế khác nhau, phụ thuộc **kiểu tĩnh của toán hạng**.

### Hai toán hạng đều là tham chiếu wrapper

```java
Integer a = Integer.valueOf(200);
Integer b = Integer.valueOf(200);

boolean sameObject = (a == b);  // so sánh tham chiếu
boolean sameValue = a.equals(b); // true
```

`sameObject` không nên được dùng để quyết định `sameValue`. Nếu có `null`, gọi `a.equals(b)` khi `a == null` gây `NullPointerException`.

### Một bên wrapper, một bên primitive

```java
Integer boxed = Integer.valueOf(200);
int raw = 200;

System.out.println(boxed == raw); // true: boxed được unbox, rồi so sánh int
```

Khi ngữ cảnh áp dụng *binary numeric promotion*, Java unbox wrapper để thực hiện so sánh giá trị số. Vì vậy kết quả `boxed == raw` có thể đúng ngay cả khi `boxed == anotherBoxed` không có bảo đảm đúng.

Cẩn thận với `null`:

```java
Integer missing = null;
// System.out.println(missing == 0); // Ném NullPointerException do unboxing
```

Đừng “sửa” một phép so sánh wrapper bằng cách đổi một toán hạng thành primitive nếu đầu vào có thể `null` mà chưa quy định cách xử lý dữ liệu thiếu.

### Hai tham chiếu `null`

```java
Integer first = null;
Integer second = null;

System.out.println(first == second); // true: cả hai đều là null
```

`true` ở đây chỉ nghĩa là cùng tham chiếu `null`. Nó **không** nghĩa hai giá trị số tồn tại và bằng nhau. Nếu cần diễn giải `null` là “thiếu dữ liệu”, phải nêu quy tắc riêng.

## 5. Cách kiểm tra giá trị đúng và an toàn

### 5.1. Hai wrapper cùng kiểu, chắc chắn không `null`

```java
Integer left = Integer.valueOf(200);
Integer right = Integer.valueOf(200);

boolean sameValue = left.equals(right); // true
```

`Integer.equals` so sánh giá trị `int` và loại wrapper tương ứng; không dựa vào số lượng đối tượng được cache.

### 5.2. Wrapper có thể `null`

Dùng `java.util.Objects.equals`:

```java
import java.util.Objects;

Integer left = null;
Integer right = Integer.valueOf(200);

System.out.println(Objects.equals(left, right)); // false
System.out.println(Objects.equals(null, null));  // true
```

`Objects.equals(a, b)` trả `true` khi hai tham chiếu cùng `null`, hoặc khi `a != null` và `a.equals(b)`. Đây là chính sách **so sánh đối tượng có tính đến null**, không phải phép kiểm tra “hai số hợp lệ bằng nhau”. Nếu miền nghiệp vụ không cho phép `null`, phải từ chối nó trước.

### 5.3. Nếu muốn so sánh số primitive

```java
Integer left = Integer.valueOf(200);
Integer right = Integer.valueOf(200);

if (left != null && right != null
        && left.intValue() == right.intValue()) {
    System.out.println("Same numeric int");
}
```

Việc unbox tường minh làm rõ phép so sánh giá trị. Đây là cách tốt khi phép tính sau đó thực sự cần `int` và kiểm tra `null` đã hoàn tất.

### 5.4. Hai wrapper thuộc *khác lớp*

`Integer.valueOf(10).equals(Long.valueOf(10L))` là `false`: hợp đồng `equals` của wrapper nguyên yêu cầu cùng loại wrapper và cùng giá trị.

```java
Integer a = Integer.valueOf(10);
Long b = Long.valueOf(10L);
System.out.println(a.equals(b)); // false
```

Nếu nghiệp vụ muốn hai số khác kiểu được coi tương đương về giá trị toán học, phải định nghĩa một cách chuẩn hóa **không làm mất dữ liệu** trước khi so sánh. Ví dụ với `Integer` và `Long` hữu hạn, `a.longValue() == b.longValue()` bảo toàn mọi giá trị `int`. Không tự chuyển mọi `Number` thành `double` vì nhiều `long` khác nhau có thể làm tròn thành cùng một `double`.

### 5.5. `Float` và `Double` có hợp đồng đặc biệt

`Double.equals` và `Float.equals` không đồng nhất với toán tử primitive `==` cho các giá trị đặc biệt:

```java
System.out.println(Double.NaN == Double.NaN); // false
System.out.println(
        Double.valueOf(Double.NaN)
                .equals(Double.valueOf(Double.NaN))); // true

System.out.println(+0.0 == -0.0); // true
System.out.println(
        Double.valueOf(+0.0).equals(Double.valueOf(-0.0))); // false
```

Tương tự với `Float`: wrapper `equals` coi các giá trị NaN là bằng nhau và phân biệt `+0.0f`/`-0.0f`. Đây là hợp đồng của lớp, **không** phải hệ quả của cache.

Khi cần so sánh gần đúng kết quả tính toán có sai số dấu phẩy động, phải định nghĩa dung sai và chính sách NaN/vô cực riêng. Quan hệ “gần bằng” không thể mặc nhiên thay `equals` cho khóa collection vì có thể không bắc cầu.

## 6. Ví dụ chạy được trên Java 17

Lưu mã sau vào `WrapperCacheDemo.java`:

```java
import java.util.Objects;

public class WrapperCacheDemo {
    public static void main(String[] args) {
        Integer smallA = Integer.valueOf(127);
        Integer smallB = Integer.valueOf(127);
        System.out.println("Integer 127 same object: " + (smallA == smallB));

        Byte byteA = Byte.valueOf((byte) -128);
        Byte byteB = Byte.valueOf((byte) -128);
        System.out.println("Byte -128 same object: " + (byteA == byteB));

        Short shortA = Short.valueOf((short) 127);
        Short shortB = Short.valueOf((short) 127);
        System.out.println("Short 127 same object: " + (shortA == shortB));

        Long longA = Long.valueOf(127L);
        Long longB = Long.valueOf(127L);
        System.out.println("Long 127 same object: " + (longA == longB));

        Integer largeA = Integer.valueOf(200);
        Integer largeB = Integer.valueOf(200);

        // Không in largeA == largeB: identity ngoài cache bảo đảm
        // không phải kết quả ổn định để dùng làm quy tắc nghiệp vụ.
        System.out.println("Integer 200 equals: "
                + largeA.equals(largeB));
        System.out.println("Integer 200 primitive values: "
                + (largeA.intValue() == largeB.intValue()));

        int primitive = 200;
        System.out.println("Wrapper vs primitive: "
                + (largeA == primitive));

        System.out.println("Integer vs Long equals: "
                + Integer.valueOf(10).equals(Long.valueOf(10L)));

        Integer missing = null;
        System.out.println("Objects.equals(null, 200): "
                + Objects.equals(missing, largeA));

        System.out.println("Double NaN wrapper equals: "
                + Double.valueOf(Double.NaN)
                        .equals(Double.valueOf(Double.NaN)));
        System.out.println("Double signed zero wrapper equals: "
                + Double.valueOf(0.0)
                        .equals(Double.valueOf(-0.0)));
    }
}
```

Biên dịch/chạy:

```bash
javac WrapperCacheDemo.java
java WrapperCacheDemo
```

Đầu ra:

```text
Integer 127 same object: true
Byte -128 same object: true
Short 127 same object: true
Long 127 same object: true
Integer 200 equals: true
Integer 200 primitive values: true
Wrapper vs primitive: true
Integer vs Long equals: false
Objects.equals(null, 200): false
Double NaN wrapper equals: true
Double signed zero wrapper equals: false
```

Các kiểm tra tham chiếu trong chương trình **chỉ dùng phạm vi cache được bảo đảm**. Chương trình chủ động không phụ thuộc kết quả `largeA == largeB`, do đó đầu ra mang cùng ý nghĩa trên các JVM tuân thủ hợp đồng API. Phần còn lại kiểm tra giá trị qua `equals` hoặc primitive sau khi unbox rõ ràng.

## 7. Tại sao không dùng wrapper làm khóa đồng bộ?

Ví dụ mã có hại:

```java
Integer lock = Integer.valueOf(42);
synchronized (lock) {
    // Không nên khóa theo đối tượng wrapper!
}
```

Một số wrapper được cache hoặc dùng chung; đoạn mã không liên quan cũng có thể nhận đúng **cùng tham chiếu**. Hệ quả có thể là tranh chấp khóa ngoài dự kiến, trì hoãn, hoặc rủi ro đồng bộ rất khó tìm. Các wrapper cũng được Java xem là **value-based classes**: nhà phát triển được khuyến cáo không dựa vào identity để đồng bộ hóa. Với JDK hiện đại, trình biên dịch có thể cảnh báo khi cố `synchronized` trên đối tượng wrapper.

Để khóa bảo vệ trạng thái của một instance, hãy tạo đối tượng khóa chuyên biệt do chính class sở hữu:

```java
public final class SafeCounter {
    private final Object lock = new Object();
    private int count;

    public void increment() {
        synchronized (lock) {
            count++;
        }
    }

    public int get() {
        synchronized (lock) {
            return count;
        }
    }
}
```

Ở đây `lock` có identity riêng phục vụ đồng bộ; không bị dùng chung do cache số nhỏ. Nếu yêu cầu là bộ đếm đồng thời, `AtomicInteger` cũng là lựa chọn có ý nghĩa, tùy bài toán.

**Không nên dùng `System.identityHashCode(integer)` làm ID nghiệp vụ.** Giá trị đó phụ thuộc identity đối tượng, không phải giá trị số hay mã định danh bền vững; nó có thể khác giữa các lần chạy và không bảo đảm duy nhất.

## 8. Cache ảnh hưởng hiệu năng như thế nào?

Wrapper cache chủ yếu là một tối ưu để **tái sử dụng đối tượng** cho những giá trị thường xuất hiện. Nhưng không nên suy diễn:

- Cứ autoboxing là cấp phát mới: nhiều trường hợp có cache hoặc JVM tối ưu loại bỏ cấp phát.
- Cứ `valueOf` là trả về cùng object cho mọi giá trị: ngoài khoảng bảo đảm, không có cam kết chung như vậy.
- Dùng `Integer` hiệu quả như primitive `int` trong mọi tình huống: wrapper là tham chiếu đối tượng, có thể `null`, cần boxing/unboxing và có thể tăng chi phí bộ nhớ hoặc thao tác.
- Mở rộng cache sẽ cải thiện hiệu năng mọi ứng dụng: hiệu quả phụ thuộc dữ liệu, JVM, GC, tối ưu JIT và cách truy cập; phải benchmark đúng tải thực.

Ví dụ:

```java
Integer count = 0;
count++; // unbox -> cộng một int -> box -> gán tham chiếu mới
```

Đối tượng `Integer` là bất biến: phép tăng **không sửa instance cũ**. Nếu giá trị mới thuộc vùng cache, JVM có thể dùng instance tái sử dụng; nếu ngoài vùng, cách triển khai có thể khác.

Để đếm số học thuần túy trong vòng lặp nóng, ưu tiên primitive:

```java
int sum = 0;
for (int i = 0; i < 1000; i++) {
    sum += i;
}
```

Khi cần `List<Integer>`, `Map<String, Long>` hoặc generic nhận kiểu tham chiếu, wrapper là công cụ đúng, nhưng cần phân biệt đánh giá hiệu năng và tính đúng đắn.

## 9. Cache mở rộng và tính di động

JDK/VM có thể có cấu hình hoặc tối ưu riêng để mở rộng phạm vi `Integer` được cache. Điều này giải thích vì sao cùng một đoạn thử:

```java
Integer x = Integer.valueOf(200);
Integer y = Integer.valueOf(200);
boolean sameReference = x == y;
```

có thể trả `true` trong một môi trường và `false` trong một môi trường khác. Kết quả đó **không chứng minh hai giá trị khác nhau**, và cũng **không phải** tín hiệu để phân nhánh logic.

Một số triển khai có thể tối ưu boxing nhờ phân tích escape hoặc tối ưu máy ảo. Đừng dùng kết quả đo identity, `identityHashCode` hay số lần cấp phát trong một lần chạy làm hợp đồng API về tính bằng nhau.

Quy tắc thiết kế bền vững:

1. Cần *numeric equality* → `equals`, `Objects.equals`, hoặc primitive comparison khi có thể unbox an toàn.
2. Cần định danh thực thể → giữ một ID bất biến riêng và định nghĩa `equals`/`hashCode` theo nghiệp vụ.
3. Cần identity đối tượng thực sự → dùng đối tượng có ownership và vòng đời rõ ràng, không dùng wrapper số.
4. Cần synchronization → dùng khóa riêng (`new Object()`), primitive atomic hoặc cơ chế đồng bộ thích hợp.
5. Cần tối ưu → đo hiệu năng và áp dụng cấu trúc dữ liệu phù hợp, không đánh đổi đúng/sai để phụ thuộc cache.

## 10. Vấn đề với collection và các phép kiểm tra

### `HashMap`/`HashSet` dùng `equals` và `hashCode`

Ví dụ:

```java
import java.util.HashSet;
import java.util.Set;

Set<Integer> ids = new HashSet<>();
ids.add(Integer.valueOf(200));

System.out.println(ids.contains(Integer.valueOf(200))); // true
```

Hai lần `valueOf(200)` **không cần** trả cùng tham chiếu. `HashSet` dùng hợp đồng `hashCode`/`equals` của `Integer` để tìm đúng phần tử.

Ngược lại, `IdentityHashMap` cố ý so sánh khóa theo tham chiếu, nên wrapper không phù hợp nếu ý định là nhận dạng bằng giá trị số. Kể cả khi thử cho thấy một số giá trị nhỏ hoạt động nhờ cache, logic sẽ dễ sai khi giá trị vượt vùng cache hoặc triển khai thay đổi.

### Phép so sánh gần đúng không phải `equals`

Với `Float`/`Double`, nếu cần dung sai vì sai số tính toán, hãy dùng tiêu chí riêng cho phép kiểm thử số học. Một tiêu chí như `Math.abs(a-b) < epsilon` không phải quan hệ tương đương tổng quát: có thể không bắc cầu, cũng không thay hợp đồng `hashCode`.

### Autounboxing trong collection

Khi lấy dữ liệu từ `List<Integer>`:

```java
Integer nullableId = null;
// int id = nullableId; // Ném NullPointerException
```

Bất kể cache có hay không, `null` là một tham chiếu hợp lệ với wrapper và cần chính sách xử lý. `Objects.equals` chỉ giúp so sánh an toàn với `null`; nó không bảo đảm mọi giá trị truyền vào hợp lệ theo miền nghiệp vụ.

## 11. Lỗi thường gặp và cách sửa

| Lỗi | Vì sao sai | Cách làm đúng |
| --- | --- | --- |
| `Integer a=200, b=200; if (a==b)` | So sánh tham chiếu; identity ngoài cache không ổn định | `a.equals(b)` nếu không null |
| Nghĩ toàn bộ wrapper cache `-128..127` | `Float`/`Double` không có cam kết cache như wrapper nguyên | Đọc đúng hợp đồng API từng loại |
| Giả định ngoài `127` thì `==` luôn sai | JVM có thể cache thêm | Không dựa vào identity |
| Dùng `synchronized(Integer.valueOf(1))` | Có thể khóa trùng object dùng chung; wrapper value-based | Khóa riêng do ứng dụng quản lý |
| `Integer x=null; x==0` | Tự unbox `null` gây `NullPointerException` | Kiểm tra `null` trước |
| So sánh `Integer(10)` với `Long(10)` bằng `equals` rồi kỳ vọng `true` | `equals` yêu cầu đúng wrapper type | Chọn chuyển đổi giữ nguyên giá trị và chính sách chung |
| Coi `Double.equals` giống `double ==` với NaN/±0 | Hai API có hợp đồng khác nhau | Dùng đúng kiểu so sánh |
| Tạo wrapper bằng constructor vì muốn identity riêng | API deprecated; wrapper value-based không phù hợp làm thực thể định danh | Thiết kế class định danh riêng |
| Dùng `IdentityHashMap<Integer, ...>` để tìm khóa theo giá trị | Identity khác equality; cache chỉ che giấu lỗi cho một số số | Dùng `HashMap<Integer, ...>` |
| Dùng `System.identityHashCode(wrapper)` làm mã bền vững | Không phải ID số, không bảo đảm duy nhất | Dùng ID rõ ràng từ domain |
| Giả định `Integer` bất biến có thể `++` tại chỗ | `++` unbox, tính, box đối tượng giá trị mới | Dùng primitive/atomic theo yêu cầu |
| Thấy `a==b` đúng nên kết luận phép so sánh số luôn đúng | Có thể tình cờ dùng cache | Viết test trên cả giá trị trong và ngoài cache; kiểm tra `equals` |

## 12. Bài tập có giải thích

**Bài 1.** Hãy dự đoán:

```java
Integer a = Integer.valueOf(127);
Integer b = Integer.valueOf(127);
boolean same = a == b;
```

**Đáp án:** `true`. Đây là phạm vi cache được cam kết bởi `Integer.valueOf`. Tuy nhiên, dùng `equals` vẫn là lựa chọn đúng để biểu diễn ý nghĩa “bằng giá trị”.

**Bài 2.** Nếu thay `127` bằng `200` thì có chắc `same` là `false` không?

**Đáp án:** Không. `Integer.valueOf` có thể cache thêm giá trị ngoài `-128..127`; kết quả identity không bảo đảm. `a.equals(b)` luôn là `true` cho hai `Integer` cùng giá trị 200.

**Bài 3.** Tại sao `Integer.valueOf(200) == 200` là `true` dù phép so sánh hai tham chiếu `Integer` có thể khác?

**Đáp án:** Một toán hạng là primitive `int`, nên wrapper được unbox và so sánh **giá trị số**; ở đây không còn là so sánh hai tham chiếu.

**Bài 4.** Điều gì xảy ra khi chạy `Integer a = null; System.out.println(a == 0);`?

**Đáp án:** `NullPointerException` khi Java cố unbox `a` để so sánh với primitive `0`.

**Bài 5.** `Objects.equals(null, null)` trả gì? Có nghĩa hai giá trị số hợp lệ bằng nhau không?

**Đáp án:** `true` theo hợp đồng so sánh tham chiếu nullable; không, cả hai đều biểu thị không có đối tượng số. Nghiệp vụ cần phân biệt dữ liệu thiếu với số 0.

**Bài 6.** Hai `Long.valueOf(127L)` có được phép coi là cùng tham chiếu? Có nên dùng điều này làm logic định danh?

**Đáp án:** Hợp đồng cache `Long.valueOf` bảo đảm chia sẻ ở `-128..127`. Nhưng không nên dùng identity wrapper làm định danh; thay vào đó so sánh bằng giá trị hoặc mô hình ID nghiệp vụ riêng.

**Bài 7.** Vì sao dùng `Integer.valueOf(42)` làm monitor cho `synchronized` nguy hiểm?

**Đáp án:** Giá trị cache có thể khiến những phần mã khác không liên quan nhận cùng object. Khóa bị chia sẻ ngoài ý muốn, và wrapper thuộc nhóm value-based nên không thích hợp cho đồng bộ dựa vào identity. Dùng đối tượng khóa riêng.

**Bài 8.** Khi một `HashSet<Integer>` chứa `200`, vì sao `contains(Integer.valueOf(200))` đúng mà không cần cache?

**Đáp án:** Collection so khớp dựa vào `hashCode`/`equals`, không dựa vào `==` của tham chiếu. Hai `Integer` cùng giá trị có hợp đồng hash/equality tương thích.

**Kết luận:** Cache wrapper là chi tiết tối ưu có **một số bảo đảm phạm vi cụ thể**, không phải cơ chế định danh giá trị. Đọc đúng kiểu của toán hạng để hiểu `==`; dùng `equals` hoặc `Objects.equals` cho wrapper (với chính sách `null`), dùng primitive khi cần tính toán, và luôn dùng đối tượng riêng khi cần identity hoặc khóa đồng bộ.