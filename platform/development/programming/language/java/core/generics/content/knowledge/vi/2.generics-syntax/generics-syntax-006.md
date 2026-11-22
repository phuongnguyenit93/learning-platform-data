# Chỉ dùng kiểu tham chiếu trong Java Generics: primitive, kiểu bao và autoboxing

Trong Java, **đối số kiểu (type argument) truyền cho generics phải là kiểu tham chiếu**. Vì vậy, `List<Integer>` hợp lệ còn `List<int>` không hợp lệ. Java cung cấp **wrapper class (lớp bao)** như `Integer`, `Double` và cơ chế **autoboxing/unboxing** để làm việc thuận tiện với số, boolean và ký tự khi API yêu cầu kiểu tham chiếu.

Quy tắc tưởng đơn giản này tác động trực tiếp đến cú pháp generic class và method, thao tác `List`/`Map`, lỗi `NullPointerException`, so sánh giá trị, cũng như chi phí bộ nhớ và hiệu năng.

## 1. Phân biệt primitive và reference type

Java có tám kiểu nguyên thủy (*primitive types*): `boolean`, `byte`, `short`, `char`, `int`, `long`, `float` và `double`. Biến primitive giữ một giá trị thuộc kiểu đó, chẳng hạn `int count = 10;` hoặc `boolean active = true;`. Primitive không phải đối tượng và không có phương thức instance.

**Kiểu tham chiếu (reference type)** bao gồm class, interface, array và các loại kiểu tham chiếu khác của Java; biến tham chiếu có thể trỏ đến một đối tượng/mảng hoặc nhận `null`. Ví dụ `String`, `Integer`, `List<String>` và `int[]` đều là kiểu tham chiếu, dù các phần tử của `int[]` là primitive.

Bảng tương ứng thường dùng:

| Primitive | Wrapper class | Ví dụ giá trị |
|---|---|---|
| `boolean` | `Boolean` | `Boolean flag = true;` |
| `byte` | `Byte` | `Byte size = (byte) 7;` |
| `short` | `Short` | `Short code = (short) 12;` |
| `char` | `Character` | `Character letter = 'A';` |
| `int` | `Integer` | `Integer count = 42;` |
| `long` | `Long` | `Long total = 42L;` |
| `float` | `Float` | `Float rate = 1.5f;` |
| `double` | `Double` | `Double amount = 1.5;` |

Wrapper class nằm trong `java.lang`, được import tự động. Chúng là những đối tượng **bất biến (immutable)**: thao tác số học không sửa giá trị bên trong một đối tượng `Integer` đã tồn tại. Cả primitive và wrapper đều có ích; chọn loại phù hợp với hợp đồng API và yêu cầu dữ liệu.

`void` không phải một primitive chứa giá trị để lưu trong collection; `Void` là một lớp tham chiếu đặc biệt, đôi khi dùng làm tham số kiểu để biểu đạt việc không có kết quả giá trị trong API như `Callable<Void>`. Không nên coi `Void` là “kiểu số bao” hoặc một cách lưu giá trị `void`.

## 2. Vì sao `List<int>` sai mà `List<Integer>` đúng?

Generic class hoặc generic interface dùng kiểu tham số hóa, ví dụ `List<E>`, `Map<K, V>` và `Box<T>`. Với Java 17, **đối số kiểu phải là reference type** (hoặc wildcard hợp lệ ở vị trí cho phép); tên kiểu primitive như `int` và `double` không được viết trong ngoặc `<...>` dưới dạng đối số kiểu.

Các ví dụ **không biên dịch**, được đặt riêng để nhận biết lỗi:

```java
List<int> numbers;            // Sai: int không phải reference type
Map<String, double> prices;   // Sai: double không phải reference type
Box<boolean> enabled;         // Sai: boolean không phải reference type
```

Các phiên bản **hợp lệ**:

```java
List<Integer> numbers;
Map<String, Double> prices;
Box<Boolean> enabled;
```

Những đoạn trên là **minh họa khai báo**, không phải các chương trình chạy độc lập: cần import `List`, `Map` và định nghĩa lớp `Box<T>` thích hợp.

Tương tự, phương thức generic:

```java
static <T> T identity(T value) {
    return value;
}
```

có thể được gọi bằng `identity(123)` nhưng không có nghĩa `T` trở thành primitive `int`. Trình biên dịch áp dụng **boxing** để biểu diễn đối số bằng `Integer`, sau đó suy luận và kiểm tra kiểu theo các quy tắc áp dụng cho reference type. Lệnh `Integer result = identity(123);` hợp lệ; khi gán kết quả vào `int` có thể phát sinh **unboxing**.

**Type erasure:** phần lớn tham số kiểu của Java bị xóa khi biên dịch: tham số `T` không có bound thường xóa về `Object`, tham số có bound xóa về bound tương ứng. Vì `Object` và các bound là kiểu tham chiếu, wrapper giúp truyền primitive qua ranh giới của các API generic thông thường. Không nên hiểu `List<Integer>` là `List<int>` bí mật được tối ưu thành mảng số nguyên thủy; nó vẫn là danh sách các tham chiếu `Integer`.

## 3. Boxing, autoboxing, unboxing: chính xác là gì?

**Boxing** chuyển giá trị primitive thành giá trị kiểu wrapper tương ứng. **Autoboxing** là boxing được trình biên dịch tự chèn trong các ngữ cảnh Java hỗ trợ. Ngược lại, **unboxing** lấy giá trị primitive từ wrapper; trình biên dịch cũng có thể chèn unboxing tự động.

```java
int primitive = 42;

Integer boxedExplicitly = Integer.valueOf(primitive); // Boxing chủ động
Integer boxedAutomatically = primitive;               // Autoboxing

int unboxedExplicitly = boxedExplicitly.intValue();   // Unboxing chủ động
int unboxedAutomatically = boxedAutomatically;         // Auto-unboxing
```

Đây là đoạn minh họa cần đặt trong method hoặc vùng khai báo hợp lệ. Hai dòng với `Integer.valueOf(...)` và `.intValue()` giúp nhìn rõ cơ chế; trong code thường ngày, autoboxing/unboxing giúp cú pháp ngắn hơn.

Các bối cảnh hay xuất hiện chuyển đổi tự động:

- **Gán và truyền tham số:** `Integer x = 10;`, hoặc truyền `10` vào method đòi `Integer`, nếu ngữ cảnh cho phép boxing.
- **Đưa primitive vào collection:** `List<Integer> values = new ArrayList<>(); values.add(10);` — đối số `10` được boxing thành `Integer`.
- **Lấy wrapper ra để dùng như primitive:** `int x = values.get(0);` — phần tử `Integer` được unbox thành `int`.
- **Toán tử số học và so sánh số:** `Integer x = 10; int y = x + 5;` thường đòi unboxing của `x` trước phép cộng.
- **Generic method:** khi gọi `<T> T echo(T value)` với một primitive, boxing tạo giá trị kiểu wrapper để đi vào vị trí `T`.

**Autoboxing không phải phép chuyển đổi tùy ý giữa mọi wrapper.** Ví dụ để tạo một `Long` từ số nguyên, viết `Long n = 10L;` hoặc `Long.valueOf(10L)`; đừng cho rằng `Integer` và `Long` thay thế trực tiếp cho nhau chỉ vì `int` có thể mở rộng thành `long`. Phép gán `Integer i = 10; Long l = i;` không hợp lệ.

Cũng không có autoboxing từ một kiểu chuỗi tùy ý thành số: `Integer.parseInt("42")` trả `int`, còn `Integer.valueOf("42")` trả `Integer`. Chuyển đổi chữ số trong chuỗi thành số là **parsing**, tách biệt với boxing.

## 4. Ví dụ Java 17 chạy độc lập: từ primitive đến generic collection

Lưu nguyên chương trình dưới tên `PrimitiveGenericsDemo.java`:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Objects;
import java.util.stream.IntStream;

public class PrimitiveGenericsDemo {
    static <T> T echo(T input) {
        return input;
    }

    public static void main(String[] args) {
        List<Integer> scores = new ArrayList<>();
        scores.add(10); // int -> Integer (autoboxing)
        scores.add(20);

        int first = scores.get(0); // Integer -> int (unboxing)
        System.out.println("first: " + first);

        Integer echoed = echo(42);
        System.out.println("echo: " + echoed);

        int sum = scores.stream().mapToInt(Integer::intValue).sum();
        System.out.println("sum: " + sum);

        int[] raw = {2, 4, 6};
        List<int[]> batches = new ArrayList<>();
        batches.add(raw);
        System.out.println("array value: " + batches.get(0)[1]);

        List<int[]> oneArray = Arrays.asList(raw);
        System.out.println("asList size: " + oneArray.size());

        List<Integer> boxed = Arrays.stream(raw).boxed().toList();
        System.out.println("boxed stream: " + boxed);

        int primitiveSum = IntStream.of(raw).sum();
        System.out.println("primitive sum: " + primitiveSum);

        Integer a = Integer.valueOf(1000);
        Integer b = Integer.valueOf(1000);
        System.out.println("value equality: " + Objects.equals(a, b));

        Integer missing = null;
        System.out.println("missing is null: " + (missing == null));
        try {
            int unavailable = missing;
            System.out.println(unavailable);
        } catch (NullPointerException exception) {
            System.out.println("unboxing null: NullPointerException");
        }

        List<Integer> selected = new ArrayList<>(List.of(10, 20, 30));
        selected.remove(1); // remove(int index): xóa 20
        selected.remove(Integer.valueOf(10)); // remove(Object): xóa 10
        System.out.println("after remove: " + selected);
    }
}
```

Biên dịch/chạy trong thư mục chứa tệp (JDK 17 trở lên):

```bash
javac PrimitiveGenericsDemo.java
java PrimitiveGenericsDemo
```

Stdout theo đúng thứ tự:

```text
first: 10
echo: 42
sum: 30
array value: 4
asList size: 1
boxed stream: [2, 4, 6]
primitive sum: 12
value equality: true
missing is null: true
unboxing null: NullPointerException
after remove: [30]
```

Giải thích những chi tiết dễ bỏ qua:

1. `scores.add(10)` gọi phương thức có tham số kiểu `Integer`; trình biên dịch chèn boxing. `int first = scores.get(0)` tự unbox kết quả `Integer`. Danh sách vẫn chứa wrapper reference, không biến thành `int[]`.
2. `echo(42)` là method generic `<T> T echo(T input)`; `42` được boxing thành `Integer`, và kết quả có thể giữ dưới kiểu `Integer`. `T` không phải kiểu primitive.
3. `mapToInt(Integer::intValue)` chuyển luồng các `Integer` thành `IntStream` để cộng với `sum()`; phương thức này cho kết quả `int`. Vì tất cả phần tử không-null nên việc chuyển đổi an toàn.
4. `int[]` **là reference type**, dù phần tử là `int`. Vì vậy `List<int[]>` hợp lệ, và `batches.get(0)[1]` đọc số `4` trong phần tử mảng.
5. `Arrays.asList(raw)` nhận **một mảng `int[]` làm một phần tử**, tạo `List<int[]>` có kích thước `1`, không phải `List<Integer>` có ba số. Đây là lỗi rất thường gặp khi đưa mảng primitive vào API generic nhận varargs.
6. `Arrays.stream(raw).boxed().toList()` chuyển từng `int` thành `Integer` để tạo `List<Integer>`. `Stream.toList()` trong Java 17 trả danh sách **không hỗ trợ thay đổi cấu trúc/nội dung bằng các method sửa**; nếu cần sửa, có thể bọc `new ArrayList<>(...)`.
7. `IntStream.of(raw)` tính tổng trực tiếp trên luồng `int`, tránh phải tạo danh sách wrapper chỉ để cộng.
8. `Objects.equals(a, b)` so sánh giá trị an toàn với `null`. Không sử dụng `a == b` để kiểm tra số bằng nhau khi cả hai là `Integer`.
9. `missing == null` kiểm tra null an toàn; nhưng `int unavailable = missing;` cố gắng unbox `null` nên ném `NullPointerException`.
10. `List<Integer>.remove(1)` gọi **`remove(int index)`**, còn `remove(Integer.valueOf(10))` gọi **`remove(Object value)`**. Hai phương thức overload có ý nghĩa khác nhau và autoboxing có thể khiến người mới nhầm.

## 5. Mảng primitive là kiểu tham chiếu: ngoại lệ tưởng mâu thuẫn

Quy tắc cấm primitive làm type argument **không có nghĩa mọi thứ chứa primitive đều bị cấm**. Bản thân mảng trong Java là một đối tượng, nên các kiểu `int[]`, `double[]` và `boolean[]` đều là reference type hợp lệ khi làm đối số kiểu:

```java
List<int[]> chunks;
List<double[]> measurements;
Map<String, boolean[]> flags;
```

Đây là khai báo hợp lệ khi đặt trong ngữ cảnh và import `List`, `Map`. Tuy nhiên, `List<int[]>` là **danh sách các mảng số nguyên**, không phải danh sách số nguyên theo từng phần tử. Ví dụ `chunks.get(0)` có kiểu `int[]`, và `chunks.get(0)[0]` mới có kiểu `int`.

So sánh ba cấu trúc:

| Cấu trúc | Chứa gì? | Cách dùng điển hình |
|---|---|---|
| `int[]` | Dãy phần tử primitive `int` | Kích thước biết khi tạo, truy cập chỉ số, tính toán số |
| `List<Integer>` | Dãy tham chiếu tới wrapper `Integer` | Collection API, có khả năng thêm/xóa nếu triển khai hỗ trợ |
| `List<int[]>` | Dãy các đối tượng mảng `int[]` | Nhiều đợt dữ liệu, lô/batch số nguyên |

Khi cần đổi `int[]` thành `List<Integer>`, dùng `Arrays.stream(array).boxed().toList()` nếu chỉ cần đọc; hoặc `Arrays.stream(array).boxed().collect(java.util.stream.Collectors.toCollection(ArrayList::new))` nếu cần danh sách có thể thêm/xóa. Việc chuyển đổi này phải boxing từng phần tử; không thể ép kiểu trực tiếp `(List<Integer>) array`.

Ngược lại, từ `List<Integer>` có thể tạo `int[]` bằng `list.stream().mapToInt(Integer::intValue).toArray()`, nhưng **phần tử null sẽ gây lỗi khi chuyển thành primitive**.

## 6. Null: điểm khác biệt quan trọng giữa primitive và wrapper

Primitive `int` không thể chứa `null`; wrapper `Integer` có thể chứa `null`. Đây vừa là lợi thế biểu đạt “chưa có giá trị”, vừa là nguồn phát sinh lỗi nếu vô tình unbox.

Ví dụ minh họa, cần đặt trong method:

```java
Integer quantity = null;

// int q = quantity;         // Biên dịch được nhưng khi chạy sẽ ném NPE
boolean absent = quantity == null; // An toàn, true
boolean zero = java.util.Objects.equals(quantity, 0); // An toàn, false
```

Những biểu thức như `quantity + 1`, `quantity < 5` hoặc `int q = quantity` yêu cầu unboxing, nên khi `quantity == null` có thể ném `NullPointerException`. Việc chỉ khai báo wrapper và giữ `null` chưa ném lỗi; lỗi phát sinh khi sử dụng theo cách yêu cầu giá trị primitive.

Tình huống `Map<String, Integer>` thường gây bất ngờ:

```java
Map<String, Integer> counts = new java.util.HashMap<>();
// int count = counts.get("missing"); // get trả null -> auto-unboxing gây NPE
int count = counts.getOrDefault("missing", 0);
```

`getOrDefault` dùng giá trị mặc định nếu khóa không có mặt; với ví dụ map rỗng thì `count = 0`. **Ngoại lệ cần nhớ:** nếu map thực sự chứa ánh xạ từ khóa đó tới giá trị `null`, `getOrDefault` trả `null`, và lệnh gán vào `int` vẫn có thể ném NPE. Khi null là một trạng thái hợp lệ, hãy xử lý tường minh:

```java
Integer maybeCount = counts.get("key");
int safeCount = maybeCount == null ? 0 : maybeCount;
```

Hai ví dụ map là các đoạn minh họa cần import `Map` và đặt trong method. Thiết kế API nên mô tả rõ **null nghĩa là gì**: không có bản ghi, chưa được gán, hay là dữ liệu lỗi. Không xem `0` và `null` tự động là tương đương trong mọi miền nghiệp vụ.

## 7. So sánh wrapper: `==`, `equals()` và unboxing

Với primitive, `int a = 5; int b = 5; a == b` so sánh **giá trị số**. Với hai biến cùng kiểu wrapper reference `Integer`, `a == b` thường là **so sánh tham chiếu**, không phải kiểm tra số có bằng nhau hay không.

Java có cache cho một số giá trị boxed phổ biến (chẳng hạn `Integer.valueOf` phải tái sử dụng instance cho dải giá trị nhỏ theo quy định); cách triển khai có thể cache thêm. Do vậy mã thử `Integer a = 127; Integer b = 127; a == b` có thể cho `true` nhưng không chứng minh `==` là cách so sánh đúng cho mọi số. **Không phụ thuộc vào định danh object của wrapper để so sánh nội dung.**

Ưu tiên:

- `Objects.equals(a, b)` nếu biến wrapper có thể null và cần so sánh giá trị.
- `a.equals(b)` nếu đã chắc `a` không null.
- `a.intValue() == b.intValue()` nếu cần so sánh primitive và đã chắc cả hai không null.

**Thận trọng:** trong một biểu thức gồm wrapper và primitive, ví dụ `Integer a = 5; boolean same = a == 5;`, quy tắc chuyển đổi có thể unbox `a` để so sánh giá trị primitive. Kết quả của `==` phụ thuộc vào **kiểu của hai toán hạng**, nên không có một phát biểu “`==` với Integer luôn so sánh địa chỉ” cho mọi trường hợp. Nếu `a` là null, biểu thức có unboxing này sẽ ném NPE.

Wrapper là immutable. Ví dụ `Integer count = 1; count++;` được biên dịch thành logic gần với “unbox, cộng 1, rồi boxing/gán lại”; phép tăng không sửa đối tượng `Integer` cũ.

## 8. Autoboxing có chi phí: chọn cấu trúc dữ liệu theo nhu cầu

Wrapper hữu ích vì `List<E>`, `Map<K, V>` và các generic API chuẩn làm việc với reference type; đổi lại, một collection số thường cần **tham chiếu tới các đối tượng wrapper**, cùng với boxing/unboxing trong nhiều thao tác. Điều này có thể tốn bộ nhớ, cấp phát và CPU, đặc biệt trong vòng lặp lớn hoặc đường xử lý dữ liệu nóng. JVM có các tối ưu hóa như caching và escape analysis nên **không thể kết luận mỗi lần boxing luôn tạo một đối tượng mới**, cũng không thể suy ra mức chi phí chính xác chỉ từ cú pháp.

Chọn công cụ dựa trên tình huống:

| Nhu cầu | Lựa chọn | Ý nghĩa |
|---|---|---|
| Tích hợp `List`, `Map` hay API generic tiêu chuẩn | `Integer`, `Long`, `Double`... | Tuân theo type argument là reference type |
| Lưu dãy số nguyên kích thước cố định và thao tác theo chỉ số | `int[]` | Dữ liệu phần tử primitive, không cần wrapper cho từng phần tử |
| Tính toán chuỗi số từ mảng/nguồn số | `IntStream`, `LongStream`, `DoubleStream` | API stream chuyên biệt cho primitive |
| Một giá trị số có thể có hoặc không có | `OptionalInt`, `OptionalLong`, `OptionalDouble` nếu phù hợp | Biểu diễn giá trị tùy chọn mà không cần `Optional<Integer>` |
| Cần danh sách có thể thêm/xóa hoặc API collection rộng | `ArrayList<Integer>` hoặc collection phù hợp | Linh hoạt, nhưng sử dụng wrapper |
| Truyền nhiều mảng số theo lô | `List<int[]>` | Mỗi phần tử danh sách là một mảng primitive |

`IntStream` và `OptionalInt` là **API chuyên biệt**, không biến `List<int>` thành cú pháp hợp lệ. Ví dụ `IntStream.range(1, 5).sum()` tính tổng `1 + 2 + 3 + 4 = 10` bằng luồng số primitive. Nếu cuối cùng cần `List<Integer>`, dùng `.boxed()` để chuyển sang luồng wrapper.

Một số kiểu generic có bounded type parameter:

```java
static <N extends Number> double twice(N value) {
    return value.doubleValue() * 2;
}
```

Đây là phương thức minh họa cần đặt trong class. `twice(3)` hợp lệ do `3` được boxing thành `Integer`, vốn là subtype của `Number`; `twice(2.5)` dùng `Double`. Bound `Number` **không cho phép thay `N` bằng primitive `int`**; nó chỉ chấp nhận reference type thích hợp.

Trong tính toán cần hiệu năng cao, đo đạc với dữ liệu và JVM thực tế trước khi tối ưu. Đừng thay mọi `List<Integer>` bằng mảng nếu thiết kế cần những tính năng của collection.

## 9. Các lỗi thường gặp và cách sửa

**Lỗi 1 — Truyền primitive trực tiếp làm type argument.**

```java
List<int> values;       // Sai cú pháp tham số kiểu
List<Integer> values;   // Đúng (viết như phương án thay thế, không khai báo hai lần cùng scope)
```

Cách sửa: dùng wrapper `Integer`, hoặc cân nhắc `int[]`/`IntStream` nếu thao tác thuần số. Tương tự, `Map<String, boolean>` phải đổi thành `Map<String, Boolean>`.

**Lỗi 2 — Nghĩ rằng `List<Integer>` chứa trực tiếp các ô `int`.** Danh sách lưu các tham chiếu theo kiểu `Integer`; boxing/unboxing được áp dụng khi biên dịch tại các ngữ cảnh cần thiết. Sự thuận tiện cú pháp không xóa khác biệt runtime.

**Lỗi 3 — Unbox `null` mà không kiểm tra.** `Integer count = null; int n = count;` biên dịch được nhưng ném `NullPointerException` khi chạy. Kiểm tra null hoặc thiết kế API tránh giá trị null không mong muốn.

**Lỗi 4 — Dùng `==` để so sánh hai wrapper.** Có thể nhận kết quả phụ thuộc cache và identity của object. Dùng `Objects.equals(left, right)` cho so sánh null-safe hoặc `.equals()` khi đối tượng chắc chắn khác null.

**Lỗi 5 — Chuyển nhầm `Arrays.asList(intArray)` thành danh sách số.** Với `int[] array = {1, 2, 3};`, `Arrays.asList(array)` tạo **một phần tử kiểu `int[]`**, không phải ba `Integer`. Dùng `Arrays.stream(array).boxed().toList()` khi muốn một wrapper cho từng giá trị.

**Lỗi 6 — Nhầm `List<Integer>.remove(1)` là xóa số `1`.** Lời gọi tham số primitive `int` chọn `remove(int index)`; nếu muốn xóa giá trị bằng `1`, dùng `remove(Integer.valueOf(1))` (overload `remove(Object)`). Cẩn thận chỉ số ngoài phạm vi.

**Lỗi 7 — Cho rằng collection wrapper nhận mọi kiểu số tương thích nhau.** `List<Integer>` không phải `List<Long>`, và `Integer` không tự chuyển thành `Long` qua boxing. Nếu cần nhiều loại số, chọn API cho `Number` hoặc generic bound phù hợp; nếu cần chuyển kiểu, thực hiện chuyển đổi có chủ đích.

**Lỗi 8 — Quên tính không sửa được của `Stream.toList()`.** Danh sách trả về từ `Arrays.stream(raw).boxed().toList()` không cho `add`, `remove`, `set`. Nếu cần sửa, khởi tạo `new ArrayList<>(result)` hoặc dùng collector tạo `ArrayList`.

**Lỗi 9 — Dùng `Optional<Integer>` cho mọi phép toán số dù không cần API generic.** Trong những nơi cần một số tùy chọn, `OptionalInt` có thể diễn đạt phù hợp hơn và tránh bọc phần tử bằng `Integer`. Tuy nhiên `OptionalInt` không thay thế mọi nơi yêu cầu `Optional<T>` hay `List<T>`: mỗi kiểu có API khác nhau.

**Lỗi 10 — Cho rằng `int[]` bị cấm trong generics vì các phần tử của nó là primitive.** Bản thân mảng là reference type, nên `List<int[]>` hợp lệ. Nhưng đó là danh sách *mảng*, không phải danh sách *số*.

## 10. Câu hỏi tự kiểm tra có đáp án

1. **Vì sao `List<int>` không hợp lệ?** Vì `int` là primitive, còn đối số kiểu của generic API Java 17 phải là reference type. Dùng `List<Integer>` khi cần collection.
2. **`Integer x = 7;` có yêu cầu `new Integer(7)` không?** Không. Compiler tự áp dụng boxing thích hợp; trong code Java mới ưu tiên cú pháp đơn giản hoặc `Integer.valueOf`, tránh gọi constructor wrapper cũ.
3. **`List<Integer> list = new ArrayList<>(); list.add(5);` xảy ra chuyển đổi gì?** Giá trị `5` được autobox thành `Integer` để gọi `add`.
4. **`int number = list.get(0);` xảy ra gì?** Kết quả `Integer` được unbox thành `int`. Nếu phần tử là `null`, có nguy cơ NPE.
5. **`List<int[]>` hợp lệ không?** Có. `int[]` là kiểu tham chiếu đến một mảng, dù từng phần tử trong mảng là primitive.
6. **`Arrays.asList(new int[]{1, 2})` có bao nhiêu phần tử?** Một: phần tử duy nhất là đối tượng `int[]`; không tự boxing từng giá trị của mảng.
7. **Muốn biến `int[]` thành `List<Integer>` cần gì?** `Arrays.stream(array).boxed().toList()` là cách ngắn trong Java 17. Nếu cần sửa danh sách, tạo `new ArrayList<>(...)`.
8. **`Integer maybe = null; boolean b = maybe == null;` có lỗi không?** Không; phép so sánh với `null` ở đây không unbox. Nhưng `maybe == 0` có thể ném NPE vì phải unbox.
9. **Tại sao `Integer a = 1000; Integer b = 1000; a == b` không nên dùng để kiểm tra giá trị?** Hai wrapper có thể là hai tham chiếu khác nhau. Dùng `Objects.equals(a, b)`.
10. **Khi xử lý dữ liệu số lớn, có lựa chọn nào ngoài `List<Integer>`?** Có: `int[]`, `IntStream`, hoặc cấu trúc chuyên biệt phù hợp; đo hiệu năng thực tế trước khi quyết định.

Ghi nhớ: **primitive cung cấp giá trị số/logic cơ bản; wrapper đưa giá trị đó vào thế giới đối tượng và generic API; autoboxing/unboxing kết nối hai thế giới nhưng có thể phát sinh null lỗi và chi phí.** Nhìn thấy `List<Integer>`, hãy nhớ đó là generic của một **reference type**, dù code truyền vào thường viết gọn như số primitive.
