# Chi phí boxing và vì sao Java Generics không tự chuyên biệt hóa mã cho primitive

## Mục tiêu học tập

Trong Java, `List<Integer>` là hợp lệ nhưng `List<int>` không hợp lệ. Điều này có hệ quả trực tiếp đối với bộ nhớ, cấp phát và hiệu năng: khi một giá trị nguyên thủy như `int` đi vào cấu trúc generic cần **reference**, Java thường phải **boxing** nó thành một đối tượng wrapper `Integer`; khi dùng trở lại trong phép tính số học, Java thường **unboxing** về `int`.

Bài học này giải thích **cả hai mặt** của vấn đề:

1. **Ngôn ngữ và JVM:** Vì sao generics Java 17 chủ yếu hoạt động với reference types, tại sao erasure dùng `Object`/upper bound thay cho mỗi phiên bản `int`, và vì sao compiler không tự sinh một phiên bản thuật toán generic riêng cho từng primitive.
2. **Chi phí và kiểm thử:** Khi boxing/unboxing phát sinh về mặt ngữ nghĩa, rủi ro `NullPointerException` và identity, overhead bộ nhớ/GC có thể xuất hiện, khi nào cần `int[]` / `IntStream` / primitive functional interface, và cách đo hiệu năng mà không bịa con số.

Sau bài, bạn có thể:

- Phân biệt primitive `int` với reference `Integer`; phân biệt boxing, unboxing, widening và generic erasure.
- Viết được positive/negative compilation tests cho `List<Integer>`, `List<int>`, `Box<int>`, arithmetic trên `T extends Number`, `new T[]` và `T.class`.
- Chứng minh bằng `javap -s` rằng field/method của `Box<T>` sau erasure không trở thành field/method primitive cho `T=Integer`.
- Đọc một vòng lặp `for (int n : List<Integer>)` và nhận ra vị trí unboxing.
- Biết lý do dữ liệu có `null` có thể ném `NullPointerException` tại điểm unboxing.
- Hiểu giá trị số và **object identity** là hai khái niệm khác nhau đối với wrapper.
- So sánh `int[]`, `List<Integer>`, `IntStream`, `Stream<Integer>`, `IntUnaryOperator`, `OptionalInt` và các phương án thiết kế API.
- Phân biệt chi phí tiềm tàng do boxing với số liệu đo đã được kiểm chứng; tránh kết luận “mỗi boxing chắc chắn cấp phát một object” hoặc “IntStream luôn nhanh hơn”.

Các chương trình chạy hoàn chỉnh sử dụng **JDK 17 trở lên**. Mã đã được kiểm chứng với `javac --release 17 -Xlint:all -Werror`, kết quả stdout được ghi đúng theo lượt thử. Những đoạn cố tình không biên dịch được đánh dấu rõ; không đưa chúng vào cùng source set với chương trình hợp lệ.

## 1. Primitive và wrapper: hai kiểu dữ liệu khác nhau

Java có các primitive types:

| Primitive | Wrapper reference |
| --- | --- |
| `boolean` | `Boolean` |
| `byte` | `Byte` |
| `short` | `Short` |
| `char` | `Character` |
| `int` | `Integer` |
| `long` | `Long` |
| `float` | `Float` |
| `double` | `Double` |

`int` là một primitive value type của Java; `Integer` là một **class**, object reference có thể tham chiếu một wrapper instance hoặc `null`. Wrapper cung cấp API như `intValue()`, `parseInt(...)`, `compare(...)` và nhiều API khác.

Đọc sự khác biệt:

```java
int primitive = 42;
Integer wrapper = Integer.valueOf(42);
```

- Biến `primitive` chứa giá trị primitive `int` theo semantics của Java.
- Biến `wrapper` là một reference tới một `Integer` object; reference ấy có thể `null`.
- `Integer` đại diện cho một giá trị số nguyên, nhưng **không đồng nghĩa** kiểu khai báo là `int`.
- `Integer` là subtype của `Number` và `Object`. Primitive `int` **không** phải subtype của `Object` hoặc `Number`.

Một biểu thức gán:

```java
Integer x = 42;
int y = x;
```

được compiler chấp nhận nhờ conversion rules (boxing và unboxing), **không** vì `int` và `Integer` là cùng một kiểu generic hay một quan hệ thừa kế.

## 2. Boxing là gì?

**Boxing conversion** biến một giá trị primitive thành giá trị của wrapper tương ứng. Ví dụ:

```java
int value = 42;
Integer boxed = value; // Autoboxing.
```

Có thể hiểu về mặt ý nghĩa gần như:

```java
Integer boxed = Integer.valueOf(value);
```

Compiler thường chèn lời gọi wrapper factory thích hợp trong bytecode, chẳng hạn `Integer.valueOf(int)`. Đây là lời giải thích về semantics/bytecode thường gặp, không phải cam kết mọi lệnh boxing luôn cấp phát một object mới.

Wrapper factories có thể **cache** hoặc tái sử dụng object theo quy tắc triển khai và tiêu chuẩn. Trình tối ưu JIT cũng có thể loại bỏ những boxing objects không cần phải materialize ra heap khi chương trình giữ nguyên ngữ nghĩa quan sát được.

**Vì vậy:** đánh giá đúng là “boxing *có khả năng* gây allocation và tăng áp lực bộ nhớ/GC”, không phải “mỗi lần autoboxing chắc chắn tạo một object heap mới”.

### Những chỗ thường gặp boxing

```java
List<Integer> numbers = new ArrayList<>();
numbers.add(10);                // int -> Integer.
Integer result = 5 + 7;         // int expression -> Integer.
Object asObject = 12;           // int -> Integer -> Object.
Integer viaFactory = Integer.valueOf(13);
```

Đoạn trên cần imports `java.util.List` và `java.util.ArrayList`, đặt trong method hợp lệ. `List<Integer>` cần phần tử reference, vì thế `numbers.add(10)` phải chuyển đối số primitive thành wrapper compatible.

Khi viết `numbers.add(Integer.valueOf(10))`, boxing được biểu diễn tường minh. Nó **không** làm phần tử trong list trở thành primitive: kiểu element vẫn là `Integer`.

## 3. Unboxing là gì?

**Unboxing conversion** lấy giá trị primitive từ wrapper. Ví dụ:

```java
Integer boxed = 42;
int number = boxed; // Unboxing.
```

Một cách hiểu đơn giản là:

```java
int number = boxed.intValue();
```

Các phép tính primitive thường cần unboxing:

```java
Integer a = 3;
Integer b = 4;
int sum = a + b;
```

Ở đây cả hai wrappers được sử dụng như `int` trong phép `+`. Nếu muốn diễn đạt một phép toán generic hỗ trợ mọi `Number`, không thể giả định rằng `+` tự định nghĩa trên các generic type variables.

### Null unboxing: lỗi runtime thường bị bỏ qua

```java
Integer missing = null;
int value = missing; // Ném NullPointerException khi chạy.
```

Dòng gán **biên dịch được**: type checker thấy một `Integer` có thể unbox. Nhưng runtime reference là `null`, nên không thể gọi thao tác lấy primitive value.

Lỗi tương tự xảy ra trong `for (int n : listOfInteger)`, `Integer` arithmetic, hoặc `mapToInt(Integer::intValue)` nếu dữ liệu thực chứa `null`. Đây là **runtime test case**, không phải mẫu compiler phải từ chối.

## 4. Vì sao `List<int>` bị từ chối?

Một generic class trong Java 17 nhận **reference types** làm type arguments. `int` là primitive nên không phù hợp.

**Phải biên dịch:**

```java
import java.util.List;

class ValidListOfWrappers {
    List<Integer> numbers = List.of(1, 2, 3);
}
```

**Phải bị từ chối:**

```java
import java.util.List;

class InvalidPrimitiveTypeArgument {
    List<int> numbers;
}
```

Chạy riêng negative fixture:

```bash
javac --release 17 InvalidPrimitiveTypeArgument.java
```

Compiler trong lượt thử trả exit code khác 0 với chẩn đoán về loại `int` không phải một `reference` type argument. Không có chương trình hợp lệ để chạy từ fixture này.

Điều tương tự áp dụng:

```java
class Box<T> {}
class InvalidPrimitiveGenericUse {
    Box<int> value; // Compile-time error.
}
```

Java compiler **không** tự diễn giải `Box<int>` thành `Box<Integer>` chỉ vì autoboxing tồn tại ở expressions/method invocations. Hãy dùng `Box<Integer>`, hoặc nếu API yêu cầu dữ liệu số primitive hiệu quả thì viết/đưa vào một abstraction primitive riêng.

## 5. Generics được biên dịch bằng type erasure

Xét generic holder:

```java
static final class Box<T> {
    private final T value;
    Box(T value) { this.value = value; }
    T get() { return value; }
}
```

Với `T` không có explicit bound, erasure thông thường dùng `Object` tại các vị trí liên quan. Trong file class JVM:

- Field `T value` có descriptor `Ljava/lang/Object;`.
- Constructor `Box(T)` có descriptor `(Ljava/lang/Object;)V`.
- Method `T get()` có descriptor `()Ljava/lang/Object;`.

Compiler vẫn ghi generic `Signature` metadata khi thích hợp để công cụ hiểu khai báo `Box<T>`. Nhưng method descriptor ở mức JVM không trở thành `()I` chỉ vì có caller sử dụng `Box<Integer>`.

Ví dụ:

```java
Box<Integer> box = new Box<>(42);
Integer result = box.get();
```

`42` có thể được boxing để được truyền vào constructor nhận reference theo erasure. Khi caller lấy `Integer`, compiler có thể chèn một type cast hợp lý theo generic contract; nếu caller tiếp tục dùng `int`, có thể thêm unboxing.

**Hai bước khác nhau:**

1. **Erasure** giúp một generic implementation phục vụ nhiều reference type arguments.
2. **Boxing/unboxing** giúp một primitive đi qua vị trí yêu cầu wrapper reference.

Không nên gộp chúng thành một khái niệm. Type erasure không có nghĩa là compiler tự sinh những bản mã máy specialized cho `int` và `long`.

## 6. Vì sao không tự có một `Box<int>` riêng?

Trong Java 17:

- Type arguments của generic classes/methods không bao gồm primitive types.
- Các vị trí sử dụng một unbounded `T` ở mức JVM dựa trên `Object`; với bound khác, erasure dựa trên first bound thích hợp.
- Generic implementation thường **được chia sẻ** giữa `Box<String>` và `Box<Integer>`, không tự có một Java bytecode class `Box$int` do compiler tạo.
- Boxing giúp các giá trị primitive tham gia API chỉ nhận wrapper/reference types, nhưng tạo một **semantic conversion** chứ không tạo specialized generic class.

Nếu muốn field và method dùng **descriptor primitive `I`**, bạn cần code mang primitive kiểu đó thật sự, chẳng hạn:

```java
static final class IntBox {
    private final int value;
    IntBox(int value) { this.value = value; }
    int get() { return value; }
}
```

`Box<Integer>` và `IntBox` có thể cung cấp ý tưởng API giống nhau nhưng **khác representation và chữ ký bytecode**. Cái sau lưu field `int` và trả về `int`; cái trước phải tuân theo generic erasure/reference semantics của `Box<T>`.

Điều này không phải đánh giá “generic luôn xấu”: với thuật toán chủ yếu xử lý references, generics giúp tránh cast thủ công và giữ type safety tốt. Vấn đề boxing đáng cân nhắc khi thao tác **rất nhiều số primitive** trên đường xử lý nóng.

## 7. Chương trình A — Quan sát boxing, unboxing và erasure

Tạo tệp **`BoxingMechanicsDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

public class BoxingMechanicsDemo {
    static final class Box<T> {
        private final T value;
        Box(T value) { this.value = value; }
        T get() { return value; }
    }

    static final class IntBox {
        private final int value;
        IntBox(int value) { this.value = value; }
        int get() { return value; }
    }

    public static void main(String[] args) {
        int primitive = 42;
        Integer boxed = primitive;
        int unboxed = boxed;
        System.out.println("boxed type: "
                + boxed.getClass().getSimpleName());
        System.out.println("unboxed: " + unboxed);

        List<Integer> values = new ArrayList<>();
        for (int i = 1; i <= 3; i++) values.add(i);
        int sum = 0;
        for (int value : values) sum += value;
        System.out.println("generic list: " + values);
        System.out.println("generic sum: " + sum);

        Box<Integer> generic = new Box<>(42);
        IntBox specialized = new IntBox(42);
        System.out.println("generic holder: " + generic.get());
        System.out.println("primitive holder: " + specialized.get());

        Integer cachedA = 127;
        Integer cachedB = 127;
        System.out.println("small boxed identity: "
                + (cachedA == cachedB));
        System.out.println("numeric comparison: "
                + Integer.valueOf(1000)
                         .equals(Integer.valueOf(1000)));

        Integer missing = null;
        try {
            int impossible = missing;
            System.out.println(impossible);
        } catch (NullPointerException ex) {
            System.out.println("null unboxing: "
                    + ex.getClass().getSimpleName());
        }
    }
}
```

Lệnh:

```bash
javac --release 17 -Xlint:all -Werror BoxingMechanicsDemo.java
java BoxingMechanicsDemo
```

**Stdout đã xác minh:**

```text
boxed type: Integer
unboxed: 42
generic list: [1, 2, 3]
generic sum: 6
generic holder: 42
primitive holder: 42
small boxed identity: true
numeric comparison: true
null unboxing: NullPointerException
```

Chương trình biên dịch sạch dưới `-Xlint:all -Werror`.

### Diễn giải chính xác

- `Integer boxed = primitive`: conversion primitive → wrapper.
- `int unboxed = boxed`: wrapper → primitive.
- `values.add(i)`: một `int` được thêm vào `List<Integer>` nên boxing diễn ra theo ngữ nghĩa.
- `for (int value : values)`: khi duyệt `List<Integer>`, từng element reference cần được unbox để gán vào biến `int`.
- `Box<Integer>` không tự chuyển field `T` thành `int`. Nó là generic reference container.
- `IntBox` viết riêng dùng primitive field và primitive getter; so với `Box<Integer>`, khác ở representation.
- `cachedA == cachedB` với cùng hằng `127` cho `true` theo quy tắc boxed integer cache nhỏ; **không** dùng `==` để so sánh giá trị wrappers tổng quát.
- `Integer.valueOf(1000).equals(Integer.valueOf(1000))` so sánh **giá trị**, không yêu cầu hai references là cùng object.
- `missing` unboxing ném `NullPointerException` khi chạy.

Đừng đọc output trên thành benchmark. Chúng chỉ xác minh **behavior và các rủi ro type/runtime**, không đo số allocations hay nanoseconds.

## 8. Kiểm chứng bằng `javap`: reference so với primitive descriptors

Sau khi biên dịch file trên, kiểm tra hai nested classes:

```bash
javap -p -s 'BoxingMechanicsDemo$Box'
javap -p -s 'BoxingMechanicsDemo$IntBox'
```

Trên Windows PowerShell hoặc Bash, dấu nháy đơn quanh tên có `$` giúp tránh shell hiểu nhầm phần sau ký tự ấy.

**Kết quả rút gọn đã xác minh:**

```text
final class BoxingMechanicsDemo$Box<T> {
  private final T value;
    descriptor: Ljava/lang/Object;
  BoxingMechanicsDemo$Box(T);
    descriptor: (Ljava/lang/Object;)V
  T get();
    descriptor: ()Ljava/lang/Object;
}

final class BoxingMechanicsDemo$IntBox {
  private final int value;
    descriptor: I
  BoxingMechanicsDemo$IntBox(int);
    descriptor: (I)V
  int get();
    descriptor: ()I
}
```

Quan sát:

| Vị trí | `Box<T>` không bound | `IntBox` chuyên biệt thủ công |
| --- | --- | --- |
| Field | `Ljava/lang/Object;` | `I` |
| Constructor | `(Ljava/lang/Object;)V` | `(I)V` |
| Getter | `()Ljava/lang/Object;` | `()I` |

**Đây là bằng chứng về dạng mã JVM được phát sinh**, không phải kết quả đo mức độ tối ưu JIT hoặc bộ nhớ thực tế của một benchmark. JVM có thể tối ưu rất mạnh trong những ngữ cảnh cụ thể, nhưng Java compiler vẫn không làm `Box<Integer>` thành một class Java generic instantiation có primitive field.

Để xem call sites chứa boxing/unboxing, dùng:

```bash
javap -p -c BoxingMechanicsDemo
```

Tìm các phương thức như `Integer.valueOf`, `Integer.intValue` và các thao tác class generic/primitive. Bytecode là nơi dễ xác minh **conversion nào được biểu diễn**, còn việc JIT có xóa allocation nào thì cần công cụ khác.

## 9. Có bao nhiêu object được cấp phát khi boxing?

Đây là câu hỏi **không thể trả lời bằng một hằng số chung**.

Với:

```java
Integer a = 42;
Integer b = 42;
```

wrapper instances có thể được **tái sử dụng** theo quy tắc cache. Trên Java, các giá trị integer boxing nhỏ trong khoảng ít nhất `-128..127` có yêu cầu identity nhất định trong ngữ cảnh boxing được quy định; `Integer.valueOf` cũng có cache tối thiểu cho dải này.

Với:

```java
Integer x = Integer.valueOf(1000);
Integer y = Integer.valueOf(1000);
```

không nên viết test **đòi `x != y`** để chứng minh allocation. Triển khai có thể mở rộng cache hoặc JVM có thể tối ưu. Và ngay cả khi hai references khác nhau, vẫn không suy ra chi phí thời gian chính xác của toàn chương trình.

Ngoài caching, compiler/JIT có thể giảm hoặc loại bỏ wrapper allocations nếu object không escape và không có quan sát nào buộc phải materialize object. Ngược lại, lưu hàng triệu boxed values trong một collection có thể khiến nhiều wrapper objects cần được giữ lại.

**Kết luận chuẩn:** boxing có overhead *tiềm tàng* về CPU, memory footprint, object indirection và garbage collection; số overhead thực tế phụ thuộc dữ liệu, môi trường và tối ưu runtime. Chỉ kết luận số lượng allocations/latency bằng profiling hoặc benchmark phù hợp.

## 10. Chi phí bộ nhớ của `List<Integer>` so với `int[]`

Xét hai cấu trúc chứa N số:

```java
int[] primitiveNumbers = {1, 2, 3, 4};
List<Integer> wrappedNumbers = List.of(1, 2, 3, 4);
```

Ở mức khái niệm:

- `int[]` có một array object chứa các phần tử primitive `int` liên tiếp trong phần lưu trữ của array.
- `List<Integer>` cần một collection implementation và các **element references** tới các giá trị wrapper `Integer` (hoặc những objects được tái sử dụng). Cấu trúc backing cụ thể phụ thuộc implementation, không được suy rằng mọi `List` đều dùng `ArrayList`.
- Wrapper `Integer` là object reference value, có thể mang object header/alignment/đường truy cập gián tiếp, nếu thực sự materialize object.
- Số references và object allocations ảnh hưởng locality/cache behavior, áp lực lên garbage collector và số byte phải quản lý.

Do đó, với dữ liệu số lớn và xử lý lặp đi lặp lại, primitive array **thường** là lựa chọn tiết kiệm overhead representation hơn.

Tuy nhiên, **không gán một con số byte cố định cho mỗi `Integer` trong mọi JVM**. Nó phụ thuộc JDK, kiến trúc 32/64 bit, compressed references, object layout, alignment, collections, caching và escape analysis.

### Một cách ước lượng mang tính mô hình

Nếu N rất lớn:

```text
int[]:
  array header + N × kích thước phần tử int (về representation primitive)

Reference-backed List<Integer>:
  collection/backing structure
  + N × kích thước element reference
  + các wrapper objects thực sự cần tồn tại
  + metadata/overhead tương ứng
```

Mô hình này không phải phép đo trực tiếp. **Đừng** lấy đó làm lời hứa “List<Integer> luôn dùng X lần RAM của int[]”. Khi chọn cấu trúc, hãy profile thực tế, đo heap retained bytes/GC nếu cần, và cân nhắc các API mà phần còn lại của chương trình đang sử dụng.

## 11. Không thể dùng toán tử `+` với mọi `T extends Number`

Có người thử viết:

```java
class InvalidGenericArithmetic<T extends Number> {
    T add(T left, T right) {
        return left + right; // Compile-time error.
    }
}
```

Tệp này **cố ý không biên dịch**:

```bash
javac --release 17 InvalidGenericArithmetic.java
```

Kết quả kiểm chứng là nonzero exit code và diagnostic `bad operand types for binary operator '+'`.

**Vì sao?**

- Generic `T extends Number` chỉ bảo đảm type `T` có các member thừa kế từ `Number` (ví dụ `doubleValue()`).
- Nó không định nghĩa một toán tử static `+` trên mọi subtype `T` và không nói kiểu trả về phép cộng là cùng `T`.
- `Integer`, `Double`, `BigDecimal`, `BigInteger` có semantics số học khác nhau: overflow, precision, rounding, scale, phép chia, v.v.
- Java Generics không tự tạo một phép cộng `T + T` chỉ vì biết upper bound `Number`.

Có thể viết:

```java
static double sumAsDouble(List<? extends Number> source) {
    double sum = 0;
    for (Number n : source) sum += n.doubleValue();
    return sum;
}
```

Nhưng đây **không phải** một generic exact-number adder giữ nguyên subtype `T`. Việc ép số về `double` có thể làm mất precision với số lớn hoặc loại số có độ chính xác cao. Nếu yêu cầu tính toán chính xác trên `BigDecimal`, phải chọn API và quy tắc rounding đúng, không dựa vào `doubleValue()` tùy tiện.

## 12. Tránh boxing ở hot path bằng primitive arrays

Nếu workload chủ yếu là số học trên số `int` và không cần polymorphic collections, `int[]` là lựa chọn tự nhiên:

```java
int[] values = {1, 2, 3, 4};
int total = 0;
for (int value : values) {
    total += value;
}
```

Không có chuyển đổi `int -> Integer -> int` do generic collection tại các thao tác truy cập `values`. Các phần tử là primitive values.

### Nhưng còn điều gì cần kiểm tra?

- `int` arithmetic vẫn có thể **overflow**. Dùng `long` accumulation hoặc `Math.addExact` nếu muốn phát hiện overflow thay vì chấp nhận wraparound.
- Array có kích thước cố định, API thường ít tiện hơn collection đối với chèn/xóa/biến đổi cấu trúc.
- Array vẫn là object runtime và có bộ nhớ header; “primitive array” không có nghĩa là hoàn toàn không allocation.
- Nếu phải chuyển sang `List<Integer>` để tương thích API khác, boxing có thể lại xuất hiện tại ranh giới.
- Kiểm thử độ chính xác và overflow quan trọng không kém kiểm thử hiệu năng.

Không có một kiểu data structure “tốt nhất” cho mọi use case. Hãy chọn primitive array khi điều đó diễn đạt rõ **khối lượng dữ liệu số đồng nhất** mà API thực sự cần.

## 13. Primitive streams: `IntStream` khác `Stream<Integer>`

Thư viện chuẩn cung cấp các stream chuyên biệt:

- `IntStream` cho `int`.
- `LongStream` cho `long`.
- `DoubleStream` cho `double`.

Với primitive streams, các thao tác như `map(IntUnaryOperator)`, `sum()`, `average()`, `max()` và `forEach(IntConsumer)` được định nghĩa theo primitive values, **không yêu cầu mỗi phần tử đi qua một `Integer` trong API stream**.

Đối chiếu:

```java
int[] numbers = {1, 2, 3, 4};
int a = java.util.Arrays.stream(numbers).sum();
int b = java.util.stream.IntStream.of(numbers).sum();
```

Cả hai cách xử lý một sequence `int` và trả tổng `int`. Trái lại:

```java
List<Integer> boxed = List.of(1, 2, 3, 4);
int total = boxed.stream()
        .mapToInt(Integer::intValue)
        .sum();
```

`boxed.stream()` là `Stream<Integer>`. Chuyển sang `IntStream` bằng `mapToInt` có thao tác lấy primitive values khỏi các wrapper elements. Nếu collection có `null`, method reference sẽ gặp lỗi unboxing/dereference khi xử lý phần tử đó.

### Chuyển từ primitive stream sang generic stream

```java
List<Integer> list = java.util.stream.IntStream
        .rangeClosed(1, 4)
        .boxed()
        .toList();
```

`boxed()` yêu cầu tạo một **`Stream<Integer>`** ở API level. Việc chuyển từ primitive path sang reference path có thể làm mất ưu thế tránh boxing; thời gian/allocations thực tế cần được đo với workload.

Các bước `boxed()` / `mapToObj(...)` / đưa kết quả vào `List<Integer>` là **ranh giới chuyển biểu diễn** quan trọng khi phân tích performance.

## 14. Primitive functional interfaces: không dùng generic `Function<Integer,Integer>` khi chỉ cần `int -> int`

Một `Function<Integer,Integer>` biểu diễn phép biến đổi nhận/trả **reference wrapper types**. Nếu dữ liệu đầu vào/đầu ra vốn là primitive, thư viện có interface tương ứng:

| Nhu cầu | API generic wrapper | Primitive specialization |
| --- | --- | --- |
| Hàm `int -> int` | `Function<Integer,Integer>` | `IntUnaryOperator` |
| Nhận một `int` | `Consumer<Integer>` | `IntConsumer` |
| Test `int -> boolean` | `Predicate<Integer>` | `IntPredicate` |
| Sinh một `int` | `Supplier<Integer>` | `IntSupplier` |
| Đọc một số có thể vắng | `Optional<Integer>` | `OptionalInt` |
| Duyệt số `int` | `Stream<Integer>` | `IntStream` |

Lưu ý: đây là **những interface và classes chuyên biệt được thư viện viết/định nghĩa tường minh**, không phải việc compiler tự phát sinh `Function<int,int>`.

Ví dụ:

```java
java.util.function.IntUnaryOperator doubleIt = x -> x * 2;
int value = doubleIt.applyAsInt(7); // 14
```

`IntUnaryOperator.applyAsInt` dùng `int` ở chữ ký. So với `Function<Integer,Integer>.apply`, interface này không yêu cầu wrapper type ở tham số/return contract.

**Nhưng:** lambda allocation, virtual dispatch, inlining và optimization có thể ảnh hưởng hiệu năng tổng thể. “Primitive interface” giúp tránh wrapper representations ở biên API, chứ không hứa mọi lời gọi đều nhanh hơn trong mọi benchmark.

## 15. Chương trình B — So sánh primitive paths và các chuyển đổi

Tạo tệp **`PrimitiveAlternativesDemo.java`**:

```java
import java.util.Arrays;
import java.util.List;
import java.util.OptionalInt;
import java.util.function.IntUnaryOperator;
import java.util.stream.IntStream;
import java.util.stream.Stream;

public class PrimitiveAlternativesDemo {
    public static void main(String[] args) {
        int[] source = {1, 2, 3, 4};
        System.out.println("array sum: "
                + Arrays.stream(source).sum());
        System.out.println("int stream sum: "
                + IntStream.of(source).sum());
        System.out.println("squares sum: "
                + IntStream.of(source)
                           .map(x -> x * x).sum());

        List<Integer> boxed =
                IntStream.of(source).boxed().toList();
        System.out.println("boxed list: " + boxed);
        System.out.println("list sum: "
                + boxed.stream()
                       .mapToInt(Integer::intValue).sum());

        IntUnaryOperator doubleIt = x -> x * 2;
        System.out.println("primitive function: "
                + doubleIt.applyAsInt(7));

        OptionalInt maximum = IntStream.of(source).max();
        OptionalInt absent = IntStream.empty().max();
        System.out.println("max: " + maximum.orElseThrow());
        System.out.println("empty max present: "
                + absent.isPresent());

        try {
            Stream.of(1, null, 3)
                  .mapToInt(Integer::intValue).sum();
        } catch (NullPointerException ex) {
            System.out.println("null stream unboxing: "
                    + ex.getClass().getSimpleName());
        }
    }
}
```

Lệnh:

```bash
javac --release 17 -Xlint:all -Werror PrimitiveAlternativesDemo.java
java PrimitiveAlternativesDemo
```

**Stdout đã xác minh:**

```text
array sum: 10
int stream sum: 10
squares sum: 30
boxed list: [1, 2, 3, 4]
list sum: 10
primitive function: 14
max: 4
empty max present: false
null stream unboxing: NullPointerException
```

Khi xử lý `int[]` và `IntStream`, nhiều toán tử vận hành trực tiếp với `int`. Khi dùng `boxed()`, API kết quả trở thành `Stream<Integer>` và sau `toList()` là `List<Integer>`. `mapToInt` chuyển về primitive path.

### `OptionalInt` khác `Optional<Integer>` ra sao?

`OptionalInt` là một container chuyên biệt cho **một giá trị `int` có thể vắng**, tránh yêu cầu wrapper `Integer` trong API chứa value. `IntStream.max()` trả `OptionalInt` vì stream có thể rỗng. Gọi `orElseThrow()` với stream không rỗng sẽ lấy `int`; với stream rỗng nó có thể ném `NoSuchElementException`.

Không nên biến `OptionalInt` thành một phương án thay thế tổng quát cho tất cả `Optional<T>`. Nó dành cho primitive `int` và có API tương ứng, không chứa arbitrary reference type.

## 16. Những chuyển đổi boxing có thể bị che bởi cú pháp

Java có autoboxing/unboxing để code dễ đọc, nhưng mỗi vị trí chuyển đổi vẫn đáng quan sát khi debug:

```java
Integer objectNumber = 5;  // Boxing.
int plain = objectNumber;   // Unboxing.

List<Integer> values = new ArrayList<>();
values.add(plain);          // Boxing để lưu dưới Integer.

int accumulator = 0;
for (int value : values) {  // Unboxing từng phần tử.
    accumulator += value;
}
```

Không phải mọi phép `+` luôn unbox trong mọi ngữ cảnh. Ví dụ nối chuỗi có quy tắc chuyển đổi sang biểu diễn văn bản, và overload resolution có thể chọn method khác. Muốn biết conversion cụ thể, kiểm tra **kiểu tĩnh** của toán hạng, context của biểu thức và bytecode được compiler sinh ra.

Tuy nhiên, đừng tối ưu một đoạn chỉ bằng cách nhìn thấy `Integer.valueOf` trong bytecode. JIT có thể inline/eliminate nhiều chi phí; cần đo trên workload thực để xác định hot spot.

## 17. Primitive arrays và `List<Integer>`: khác semantics nữa, không chỉ performance

Khi thay một `List<Integer>` bằng `int[]`, bạn thay cả hợp đồng:

| Thuộc tính | `int[]` | `List<Integer>` |
| --- | --- | --- |
| Phần tử | `int` | `Integer` references |
| Có thể chứa null? | Không | Tùy implementation, có thể có |
| Kích thước | Cố định | Tùy implementation/API |
| Generic collection APIs | Không trực tiếp implement `List` | Có |
| Truy cập theo chỉ số | `a[i]` | `list.get(i)` |
| Runtime element type | Primitive component type `int` | Runtime generic argument bị erasure |
| Boxing khi lưu giá trị `int` | Không do element representation | Có conversion sang wrapper ở API |
| API stream chuyên biệt | `Arrays.stream(a)` → `IntStream` | `list.stream()` → `Stream<Integer>` |
| Dữ liệu số lớn | Thường ít overhead representation | Có thể chịu overhead wrappers/references |

Nếu nghiệp vụ cần **null** để biểu diễn “chưa có số”, `int[]` không tự mô tả trạng thái đó. Bạn cần thêm bitset/sentinel/schema hoặc dùng một reference representation. Không thay bằng primitive chỉ để giảm allocation rồi làm mất semantics của dữ liệu.

Nếu API cần chèn/xóa tùy ý và tích hợp nhiều collection utilities, một `List<Integer>` có thể thuận tiện hơn; việc chuyển đổi/trả thêm chi phí đôi khi là lựa chọn chấp nhận được.

## 18. Bridge method do erasure không phải primitive specialization

Khi subclass ghi đè một generic method đã được chuyên biệt hóa bằng **reference type**:

```java
class Parent<T> {
    T echo(T value) { return value; }
}
class StringChild extends Parent<String> {
    @Override String echo(String value) { return "v=" + value; }
}
```

`javac` có thể sinh một bridge để lời gọi theo descriptor đã xóa `echo(Object):Object` dispatch đến implementation `echo(String):String`. Bridge có nhiệm vụ bảo toàn overriding sau erasure, **không** cấp phát một class `Parent<int>` và không loại bỏ boxing khỏi `Parent<Integer>`.

## 19. Đối chiếu bridge với API primitive thật

Hai descriptor quan trọng trên class `StringChild` đã biên dịch là:

```text
echo:(Ljava/lang/String;)Ljava/lang/String;   // Implementation
echo:(Ljava/lang/Object;)Ljava/lang/Object;   // Bridge
```

Trong khi đó, một functional interface được **khai báo riêng cho primitive** thật sự có descriptor dùng `I`:

```java
java.util.function.IntUnaryOperator twice = x -> x * 2;
int result = twice.applyAsInt(7); // 14, method nhận/trả primitive int
```

`IntUnaryOperator.applyAsInt(int)` có descriptor `(I)I`, còn `Function<Integer,Integer>.apply` dùng reference-erased descriptor `(Ljava/lang/Object;)Ljava/lang/Object;`. Sự khác nhau đến từ **API primitive được thiết kế tường minh**, không phải compiler tự specialize một generic instantiation. Bài đối chiếu class file/bridge trong chương cung cấp chương trình Java 17 hoàn chỉnh, `javap -s/-v` và Reflection để tìm `ACC_BRIDGE`, `ACC_SYNTHETIC`; ở đây chỉ cần phân biệt đúng với boxing.


## 20. Các mẫu mã bắt buộc bị từ chối bởi compiler

Bên cạnh các chương trình dương, hãy kiểm tra mỗi luật bằng **một fixture âm độc lập**. Năm tệp dưới đây đã được thử bằng `javac --release 17`: tất cả đều trả exit code khác 0 và có compiler error về đúng quy tắc được nêu.

### 20.1. Không dùng primitive type argument

Tệp `InvalidPrimitiveTypeArgument.java`:

```java
import java.util.List;

class InvalidPrimitiveTypeArgument {
    List<int> values;
}
```

Kỳ vọng: **REJECTED** với chẩn đoán cần reference type nhưng gặp `int`.

### 20.2. Không tự tạo generic specialization cho primitive

Tệp `InvalidPrimitiveGenericBox.java`:

```java
class InvalidPrimitiveGenericBox<T> {}

class InvalidPrimitiveGenericUse {
    InvalidPrimitiveGenericBox<int> value;
}
```

Kỳ vọng: **REJECTED**. Cần dùng `InvalidPrimitiveGenericBox<Integer>` hoặc một class primitive-specialized riêng nếu đó là contract mong muốn.

### 20.3. Không giả định toán tử cộng trên `T extends Number`

Tệp `InvalidGenericArithmetic.java`:

```java
class InvalidGenericArithmetic<T extends Number> {
    T add(T left, T right) {
        return left + right;
    }
}
```

Kỳ vọng: **REJECTED** do toán tử `+` không áp dụng trực tiếp cho hai expressions kiểu `T`.

### 20.4. Không tạo array từ type variable tùy ý

Tệp `InvalidGenericArray.java`:

```java
class InvalidGenericArray<T> {
    T[] newItems(int size) {
        return new T[size];
    }
}
```

Kỳ vọng: **REJECTED** vì generic array creation. Dùng cấu trúc/thư viện phù hợp hoặc truyền array factory/token theo contract, chứ không tự tạo `T[]` khi element type chưa reifiable.

### 20.5. Không lấy `T.class` từ type variable

Tệp `InvalidTypeLiteral.java`:

```java
class InvalidTypeLiteral<T> {
    Class<?> token() {
        return T.class;
    }
}
```

Kỳ vọng: **REJECTED** với lỗi tương đương `cannot select from a type variable`. Cần truyền `Class<T>` token hoặc mô tả type thích hợp khi runtime type thông tin là một yêu cầu thực tế.

### Cách chạy một mẫu âm trong Bash

```bash
if javac --release 17 InvalidPrimitiveTypeArgument.java; then
    echo "FAIL: invalid code unexpectedly compiled"
    exit 1
else
    echo "PASS: invalid code rejected"
fi
```

Trong PowerShell 5.1:

```powershell
javac --release 17 InvalidPrimitiveTypeArgument.java
if ($LASTEXITCODE -eq 0) {
    throw "Invalid source unexpectedly compiled"
}
Write-Output "PASS: invalid source rejected"
```

Đừng gọi `java` trên một fixture mà compiler đã từ chối. Nếu thư mục có class files cũ, phải tránh chạy nhầm bản build cũ. Một negative compilation test thành công ở cấp **compiler exit status và diagnostic**, không phải stdout của một chương trình runtime.

## 21. Có thể dùng `T extends Number` để tránh boxing không?

Không. Một bound như:

```java
static <T extends Number> double sum(
        java.util.List<T> values) {
    double result = 0;
    for (T value : values) {
        result += value.doubleValue();
    }
    return result;
}
```

vẫn nhận **reference type arguments** trong Java 17. Nếu caller đưa `List<Integer>`, phần tử vẫn là `Integer` reference; bound chỉ cho phép dùng những member như `doubleValue()`.

Ở bytecode, erasure của `T extends Number` dùng bound `Number` tại vị trí tương ứng, không biến thành primitive `int`. Thêm nữa:

- `doubleValue()` không đồng nghĩa số học chính xác trên mọi subtype.
- `List<Double>` có thể chứa `null` nếu implementation cho phép; gọi `doubleValue()` trên null gây `NullPointerException`.
- Nếu muốn giữ exact numeric type `BigDecimal`, cần toán tử/API dành cho `BigDecimal` thay vì generic bound `Number`.

Bound cung cấp **khả năng gọi method của supertype**, không cung cấp specialized operators hoặc memory layout primitive.

## 22. Boxing trong Map keys, Optional và callback

Boxing không chỉ xuất hiện ở `List`:

```java
java.util.Map<Integer, String> names =
        new java.util.HashMap<>();
names.put(7, "seven"); // int được boxing thành Integer key.

java.util.Optional<Integer> boxedOption =
        java.util.Optional.of(5);
java.util.OptionalInt primitiveOption =
        java.util.OptionalInt.of(5);
```

Với `Map<Integer,V>`, key là reference `Integer`. Không tự giả định HashMap có primitive-specialized storage chỉ vì call site truyền literal `int`.

Nếu truy cập số liệu trên quy mô lớn, các primitive-specialized collections từ thư viện khác có thể cung cấp representations phù hợp, nhưng cần kiểm tra API, licenses, thread-safety, null/sentinel semantics và benchmarking của thư viện đã chọn. Không yêu cầu phải thêm thư viện ngoài chỉ để học generics.

Nếu code chỉ thao tác với một vài số lượng nhỏ, `List<Integer>` và `Map<Integer,V>` có thể đủ tốt, giúp API đơn giản và dễ bảo trì hơn so với các primitive-specific abstractions.

## 23. Giải quyết chi phí qua API design, không chỉ sửa một dòng code

Trước khi tối ưu, xác định **đường đi dữ liệu**:

```text
Nguồn số primitive int[]
        |
        v
   IntStream / int operators  --- primitive path --->
        |
        | boxed(), mapToObj(Integer::valueOf),
        | add vào List<Integer>, map key Integer...
        v
   Stream<Integer> / List<Integer> / generic APIs
        |
        | mapToInt(Integer::intValue),
        | iterator/for(int x : boxedList)...
        v
   int operations lần nữa
```

Điểm cắt giữa hai biểu diễn có thể có boxing/unboxing. Một giải pháp tốt thường tránh **lặp đi lặp lại** các conversions ở một đoạn phải xử lý lượng dữ liệu lớn.

Ví dụ: nếu input là `int[]` và đầu ra chỉ cần tổng, trả primitive `int` hoặc `long` thích hợp, thay vì xây `List<Integer>` trung gian không cần thiết.

Nếu phần còn lại của ứng dụng yêu cầu `List<Integer>`, đôi khi một lần boxing tại ranh giới rõ ràng là hợp lý. Đừng tự viết cả framework specialized chỉ để tránh một vài wrapper values không gây vấn đề measurable.

## 24. Benchmark thế nào mới đáng tin?

**Không có số “boxing chậm hơn X lần” chung cho mọi JDK.** Một benchmark nghiêm túc phải phân biệt:

1. **Allocation rate:** Có bao nhiêu objects thực sự materialize/escape, không chỉ số `Integer.valueOf` trong bytecode?
2. **Throughput/latency:** Tổng thời gian của workload đại diện, không phải thời gian của một vòng lặp quá ngắn.
3. **GC pressure:** Số collections/pause times trong tải thực.
4. **Retained heap memory:** Dữ liệu boxed được giữ trong collection có chiếm thêm bộ nhớ không?
5. **JIT effects:** Inlining, escape analysis, scalar replacement, vectorization và warmup có thể thay đổi kết quả.
6. **Data characteristics:** Kích thước input, range values (liên quan caching), số null, cấu trúc phân bố dữ liệu.
7. **Comparability:** Hai phiên bản phải tính **cùng kết quả** với cùng semantics như overflow, precision và xử lý null.

### Khuyến nghị về công cụ

Dùng profiler cho workload thật; khi cần microbenchmark JVM, ưu tiên **JMH** với warmup, nhiều forks, iterations, tiêu thụ kết quả hợp lệ để tránh JIT xóa công việc. Nếu đo object layout/heap, dùng công cụ phù hợp thay vì suy luận theo một con số cố định cho object header.

Không dùng một chương trình `System.nanoTime()` đo một lượt như bằng chứng thuyết phục rằng boxing luôn tốn số nano giây cụ thể.

### Một mẫu thiết kế benchmark hợp lý

So sánh ba đường đi với cùng số lượng dữ liệu và cùng toán:

- Vòng lặp `for` trên `int[]`.
- Vòng lặp `for` trên `List<Integer>` đã được tạo **trước phần đo**, nếu chỉ muốn đo truy cập/unboxing khi đọc.
- `IntStream` trên `int[]` và `Stream<Integer>.mapToInt` trên list, nếu muốn đo overhead pipeline stream.

Nếu muốn đo cả **chi phí tạo boxed collection**, tạo list bên trong workload được đo; nhưng **đừng** so điều ấy với một `int[]` đã tạo sẵn rồi cho rằng hai bài toán tương đương. Hãy tách chi phí **xây dựng dữ liệu** và **xử lý dữ liệu**.

Đầu ra benchmark phải được kiểm tra giống nhau trước khi công bố kết quả.

## 25. Những trường hợp tối ưu có thể phản tác dụng

- **Chuyển mọi List thành array:** có thể mất null semantics, flexibility, APIs, data ownership và tăng chi phí conversion ở các ranh giới khác.
- **Thay mọi stream bằng loop:** loop có thể nhanh trong một số workload nhưng stream có thể rõ hơn, và JVM tối ưu khác nhau; đừng kết luận thiếu dữ liệu.
- **Tin rằng boxed values luôn tạo objects mới:** cache, JIT optimization và reuse làm mệnh đề này sai.
- **Tin rằng boxed values không có overhead vì JVM tối ưu:** nếu references escape và phải được lưu giữ, overhead vẫn có thể đáng kể.
- **Dùng `==` để kiểm tra Integer equality:** object identity phụ thuộc cache/reuse và không phải so sánh giá trị. Dùng `equals` hoặc unbox có chủ đích.
- **Unbox giá trị có thể null mà không kiểm tra:** có thể phát sinh `NullPointerException` trong vòng lặp tính tổng hoặc `mapToInt`.
- **Dùng `doubleValue()` để cộng mọi `Number`:** có thể làm mất độ chính xác/semantics.
- **Dùng `Integer` thay `int` trong mọi hot loop chỉ vì generic:** API type-safety vẫn có thể giữ ở boundary, còn core numeric path có thể dùng primitives.
- **Dùng primitive array khi dữ liệu yêu cầu heterogeneous types:** mất hợp đồng nghiệp vụ và buộc viết logic bù trừ phức tạp.

Mục tiêu của tối ưu là giữ nguyên **tính đúng + semantics** và giảm một chi phí đã được xác minh, không chỉ làm code trông “ít generic hơn”.

## 26. Bài tập thực hành có đáp án

### Bài 1 — Type argument primitive

Có thể khai báo `List<int>` trên Java 17 không? Nếu không, cách dùng collection chuẩn là gì?

**Đáp án:** không. Generic type arguments cần reference types; dùng `List<Integer>`. Nếu muốn primitive representation, cân nhắc `int[]`, `IntStream` hoặc cấu trúc primitive chuyên biệt.

### Bài 2 — Boxing ở đâu?

```java
List<Integer> list = new java.util.ArrayList<>();
int x = 5;
list.add(x);
```

**Đáp án:** `x` là primitive `int`; method `List<Integer>.add` nhận `Integer` nên có boxing conversion.

### Bài 3 — Unboxing ở đâu?

```java
int sum = 0;
for (int n : list) sum += n;
```

Với `list: List<Integer>`, **đáp án:** mỗi element `Integer` cần unbox sang `int` để gán cho biến `n`. Giá trị null có thể gây `NullPointerException`.

### Bài 4 — Bound có làm toán tử cộng hoạt động?

```java
<T extends Number> T add(T a, T b) {
    return a + b;
}
```

**Đáp án:** không biên dịch. `Number` không khai báo operator `+` trả về `T`. Cần API toán học cụ thể hoặc một conversion/strategy tường minh với semantics đã chọn.

### Bài 5 — Identity của wrappers

`Integer a=127, b=127;` và `Integer x=1000, y=1000;`: có nên so `==` như kiểm tra numeric equality không?

**Đáp án:** không. `==` trên hai references là identity test; với số nhỏ có caching nhưng không được phụ thuộc vào identity cho mọi value. Dùng `a.equals(b)` hoặc các phép so sánh primitive có chủ đích.

### Bài 6 — `OptionalInt`

Khi tính `IntStream.empty().max()`, method trả gì?

**Đáp án:** một `OptionalInt` rỗng; `isPresent()` là `false`. Nó không tạo một `Integer` null để biểu diễn missing value.

### Bài 7 — Erasure descriptor

Vì sao `Box<T>.get()` có `()Ljava/lang/Object;` nhưng `IntBox.get()` có `()I`?

**Đáp án:** `T` unbounded erased thành `Object` trong generic bytecode; `IntBox` được khai báo tường minh dùng primitive `int` nên descriptor trả `int`.

### Bài 8 — Có tự động specialize `Box<Integer>` không?

**Đáp án:** không theo cách biến toàn bộ generic code thành `Box<int>` trên Java 17. `Box<Integer>` dùng cùng generic class representation tương ứng, có wrapper/conversions khi đi qua primitive boundary.

### Bài 9 — So sánh hai benchmark

Benchmark A tạo `List<Integer>` trong phần đo còn benchmark B đọc `int[]` tạo sẵn. Có thể nói chi phí runtime của hai kiểu phần tử đã được so công bằng không?

**Đáp án:** chưa. A bao gồm chi phí tạo cấu trúc còn B không. Phải định nghĩa workloads tương đương và tách creation khỏi processing.

### Bài 10 — Null runtime

`Stream.of(1,null,3).mapToInt(Integer::intValue).sum()` có bị compiler từ chối không?

**Đáp án:** không, mã compile. Nhưng khi pipeline xử lý `null`, gọi `intValue` gây `NullPointerException` tại runtime.

### Bài 11 — Bridge methods

Bridge `echo(Object):Object` do override `echo(String):String` là dấu hiệu compiler đã sinh primitive specialized version không?

**Đáp án:** không. Bridge giữ polymorphic dispatch sau generic erasure; không liên quan trực tiếp tới `int`-specialization.

### Bài 12 — Chọn representation theo mục tiêu

Một xử lý hàng triệu số nguyên chỉ cần tính tổng, output là `long`. Thiết kế nào đáng xem trước?

**Đáp án:** dùng `int[]`/primitive loop hoặc `IntStream` trên primitive source, cộng dồn vào `long` nếu cần hạn chế overflow so với `int`. Đo workload thực trước khi khẳng định cách nào nhanh hơn.

## 27. Checklist thiết kế và kiểm thử

- [ ] Biết biến nào là `int`, biến nào là `Integer`; không xem wrapper là primitive.
- [ ] Không dùng primitive `int` làm generic type argument của Java 17.
- [ ] Nhận ra conversion khi thêm primitive vào `List<Integer>` và lấy lại dưới dạng `int`.
- [ ] Có chính sách null rõ trước khi unbox wrappers hoặc gọi `Integer::intValue`.
- [ ] Không dùng `==` trên wrappers để kiểm tra numeric equality tổng quát.
- [ ] Phân biệt generic erasure `Object`/bound với primitive descriptors `I`, `J`, `D`.
- [ ] Không kỳ vọng `T extends Number` tự cung cấp `+` hoặc specialized primitive operators.
- [ ] Đã thử các negative source tests bằng compiler và không chạy chúng như runtime programs.
- [ ] Nếu cần tối ưu đường xử lý số, đã cân nhắc `int[]`/`IntStream`/`IntUnaryOperator`/`OptionalInt`.
- [ ] Không đưa boxing/`boxed()` vào các pipeline lớn nếu mục tiêu chỉ cần primitive output.
- [ ] Giữ đúng null semantics, overflow, precision và data ownership khi thay representation.
- [ ] Không khẳng định mỗi boxing luôn allocation hoặc tối ưu JIT xóa mọi boxing.
- [ ] Đo allocation, GC, retained heap và throughput trên workload/JDK thực.
- [ ] Không gọi một lần `System.nanoTime()` là benchmark đáng tin.
- [ ] Khi nghi ngờ, dùng `javap -p -s/-c` để kiểm tra descriptors và conversions trước khi kết luận.

## Kết luận

Trên Java 17, **generics không tự tạo primitive specialization**. `List<Integer>` và `Box<Integer>` vẫn là APIs reference-generic, còn `List<int>`/`Box<int>` bị compiler từ chối. Khi primitive values đi qua APIs wrapper, boxing/unboxing có thể xảy ra; null unboxing là một rủi ro runtime, và wrappers/references có thể tăng chi phí memory, CPU và GC trong các workloads lớn.

Thay vì tuyên bố generics “chậm”, hãy chọn **representation đúng vai trò**: generics cho type-safe object APIs, primitive arrays/streams/functions khi cần xử lý số nguyên thủy, và conversion ở những ranh giới thực sự cần. Đối chiếu erasure bằng `javap`, kiểm tra positive/negative compilation, rồi đo hiệu năng thật bằng profiler/JMH trước khi tối ưu. Đó là cách tránh cả **lỗi kiểu** lẫn những kết luận performance thiếu căn cứ.
