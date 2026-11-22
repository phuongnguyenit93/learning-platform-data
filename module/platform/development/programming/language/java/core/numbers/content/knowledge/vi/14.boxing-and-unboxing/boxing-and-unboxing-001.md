# Autoboxing và các ngữ cảnh chuyển primitive thành wrapper trong Java

## 1. Autoboxing là gì?

Trong Java, **primitive** là các kiểu dữ liệu nguyên thủy như `int`, `long`, `double`, `boolean`; còn **wrapper** là các lớp đóng gói một giá trị primitive tương ứng thành đối tượng. **Autoboxing** là việc trình biên dịch tự áp dụng *boxing conversion* trong những ngữ cảnh Java cho phép, để một giá trị nguyên thủy có thể được sử dụng ở nơi cần một đối tượng wrapper.

```java
int primitive = 42;
Integer boxed = primitive;  // Autoboxing: int -> Integer.
int again = boxed;          // Unboxing: Integer -> int.

System.out.println(boxed);  // 42
System.out.println(again);  // 42
```

Về mặt ý nghĩa, `Integer boxed = primitive` gần với `Integer.valueOf(primitive)`. Java không yêu cầu bạn viết `new Integer(...)` (constructor wrapper cũ đã bị deprecated và không nên dùng); có thể để trình biên dịch tạo chuyển đổi cần thiết. Tuy nhiên, **autoboxing không có nghĩa Java biến mọi kiểu số thành mọi lớp số tùy ý**; chuyển đổi phải hợp lệ theo đúng ngữ cảnh và kiểu đích.

Ví dụ nổi bật:

- Một danh sách `List<Integer>` chỉ nhận phần tử là tham chiếu `Integer`, nhưng bạn có thể gọi `list.add(5)`; Java box `5` thành `Integer`.
- Một phương thức nhận `Double` có thể được gọi với literal `1.5` kiểu `double` nhờ boxing.
- Một biến `Number n = 5;` hợp lệ: Java **box `int` thành `Integer`, sau đó mở rộng tham chiếu** lên `Number`.
- Ngược lại, `Long x = 5;` **không** hợp lệ: Java không tự thực hiện chuỗi `int -> long -> Long` trong phép gán thông thường. Cần `5L` hoặc chuyển đổi rõ ràng.

## 2. Bảng ánh xạ đầy đủ giữa tám primitive và wrapper

| Primitive | Wrapper | Ví dụ autoboxing | Cách tạo tường minh |
| --- | --- | --- | --- |
| `boolean` | `Boolean` | `Boolean b = true;` | `Boolean.valueOf(true)` |
| `byte` | `Byte` | `Byte b = (byte) 5;` | `Byte.valueOf((byte) 5)` |
| `short` | `Short` | `Short s = (short) 5;` | `Short.valueOf((short) 5)` |
| `char` | `Character` | `Character c = 'A';` | `Character.valueOf('A')` |
| `int` | `Integer` | `Integer n = 5;` | `Integer.valueOf(5)` |
| `long` | `Long` | `Long n = 5L;` | `Long.valueOf(5L)` |
| `float` | `Float` | `Float f = 1.5f;` | `Float.valueOf(1.5f)` |
| `double` | `Double` | `Double d = 1.5;` | `Double.valueOf(1.5)` |

Kiểu `void` có lớp `Void` liên quan trong API, nhưng **không có một giá trị `void` để autobox** như tám primitive ở bảng trên.

**Wrapper là đối tượng và có thể là `null`**, trong khi biến primitive không thể chứa `null`. Wrapper được thiết kế **bất biến** (*immutable*): một đối tượng `Integer` chứa `5` không bị thay giá trị thành `6`; phép tăng trên biến wrapper sẽ unbox, tính toán và box lại một giá trị.

## 3. Ngữ cảnh gán: biến, trường dữ liệu và phần tử mảng

### 3.1. Gán primitive cho wrapper

```java
int quantity = 7;
Integer quantityObject = quantity;

double price = 19.5;
Double priceObject = price;

boolean enabled = true;
Boolean enabledObject = enabled;
```

Trong cả ba trường hợp, phép gán có kiểu đích là wrapper tương ứng nên Java tự boxing. Cơ chế tương tự áp dụng cho việc khởi tạo trường dữ liệu hoặc gán lại một biến wrapper.

Ví dụ khai báo trường trong lớp:

```java
class Product {
    Integer stock = 10;   // Literal int được autobox.
    Boolean active = true; // Literal boolean được autobox.
}
```

Đây là một lớp minh họa độc lập về cú pháp; không yêu cầu phải có `main` mới chứng minh được boxing hợp lệ.

### 3.2. Boxing rồi mở rộng kiểu tham chiếu

```java
Number number = 123; // int -> Integer -> Number.
Object object = 2.5; // double -> Double -> Object.

System.out.println(number.getClass().getSimpleName()); // Integer
System.out.println(object.getClass().getSimpleName()); // Double
```

Đây là *boxing conversion* kết hợp với *widening reference conversion*. Kiểu tĩnh của biến là `Number` hoặc `Object`, nhưng đối tượng được tạo/nhận sau boxing vẫn thuộc lớp wrapper cụ thể.

Vì vậy không nên suy từ `Number n = 123` rằng Java tạo ra một “đối tượng Number” trực tiếp. `Number` là lớp trừu tượng; giá trị `123` ở ví dụ được đóng gói dưới dạng `Integer`.

### 3.3. Khởi tạo mảng wrapper

```java
Integer[] scores = {10, 20, 30}; // Mỗi phần tử được boxing.
Double[] rates = {0.5, 1.5};    // double -> Double.
```

**Không có phép biến đổi tự động cho toàn bộ mảng primitive thành mảng wrapper**:

```java
int[] raw = {1, 2, 3};
// Integer[] boxedArray = raw; // Lỗi biên dịch.
```

Nếu phải chuyển toàn bộ mảng, cần thực hiện trên **từng phần tử** hoặc dùng API thích hợp, ví dụ `IntStream.of(raw).boxed().toArray(Integer[]::new)`. Autoboxing không phải cơ chế “thay kiểu cả container”.

## 4. Ngữ cảnh gọi phương thức: truyền đối số primitive

Phương thức khai báo tham số là wrapper có thể được gọi bằng đối số primitive cùng kiểu:

```java
static void acceptInteger(Integer value) {
    System.out.println(value);
}

static void acceptDouble(Double value) {
    System.out.println(value);
}

// Khi gọi trong mã khác của cùng lớp:
// acceptInteger(8);    // int -> Integer.
// acceptDouble(2.5);   // double -> Double.
```

Trong ngữ cảnh gọi phương thức, trình biên dịch xác định phương thức áp dụng được theo các giai đoạn của **overload resolution**. Boxing được phép trong các giai đoạn phù hợp; tuy nhiên không phải mọi chuỗi chuyển đổi đều được cho phép và không phải overload nhận wrapper luôn được ưu tiên.

### Overload: mở rộng primitive được xét trước boxing

```java
static void pick(long value) {
    System.out.println("long");
}

static void pick(Integer value) {
    System.out.println("Integer");
}

// pick(1); // In "long": int -> long được xét ở giai đoạn strict invocation.
```

Với literal `1` kiểu `int`, `pick(long)` áp dụng được bằng *widening primitive conversion* mà không cần boxing; `pick(Integer)` cần boxing. Java giải quyết phương thức trong pha cho phép chuyển đổi không boxing trước, vì vậy ví dụ trên chọn `pick(long)`.

Điểm thực hành: **đừng thiết kế API chỉ dựa vào cảm giác rằng Java sẽ ưu tiên wrapper “gần hơn”**. Khi các overload trộn primitive, wrapper, varargs và kiểu tham chiếu, hãy đọc chữ ký phương thức và hiểu thứ tự lựa chọn; nếu khó đọc, ép kiểu hoặc truyền giá trị rõ ràng.

### Varargs của wrapper cũng có thể nhận các giá trị primitive

```java
static void acceptMany(Integer... values) {
    System.out.println(values.length);
}

// acceptMany(1, 2, 3); // In 3: từng int được boxing thành Integer.
```

Varargs là cơ chế tạo/nhận một mảng tham số, **không phải boxing toàn bộ một mảng `int[]`**. Lời gọi `acceptMany(rawIntArray)` với `int[]` sẽ không trở thành `Integer[]` hợp lệ chỉ bằng autoboxing.

## 5. Giá trị trả về, lambda và generic

### Return statement

Một phương thức khai báo trả về wrapper có thể trả về primitive khi phép chuyển đổi hợp lệ:

```java
static Integer boxedResult(int input) {
    return input; // int -> Integer trong ngữ cảnh return.
}
```

Ngược lại, phương thức trả về `int` có thể `return` một `Integer` không null nhờ unboxing, nhưng sẽ ném `NullPointerException` nếu giá trị wrapper trả về là `null`.

### Lambda trả về wrapper

```java
import java.util.function.Supplier;

Supplier<Integer> supplier = () -> 42;
System.out.println(supplier.get()); // 42
```

Đích của lambda là một functional interface có kết quả `Integer`. Biểu thức `42` được boxing để đáp ứng kiểu trả về. Điều này hữu ích khi code hiện đại sử dụng `Supplier`, `Function` hoặc các functional interface generic khác.

### Generics chỉ nhận kiểu tham chiếu

```java
import java.util.ArrayList;
import java.util.List;

List<Integer> values = new ArrayList<>();
values.add(10); // int -> Integer.
values.add(20); // int -> Integer.

// List<int> invalid = new ArrayList<>(); // Lỗi biên dịch.
```

Một tham số kiểu generic như `T` của `List<T>` phải là kiểu tham chiếu, không thể là primitive. Các lớp wrapper cho phép dùng dữ liệu số trong generics.

Cũng cần phân biệt `List<Integer>` với `List<Number>`: chúng **không có quan hệ kế thừa trực tiếp** theo quy tắc generic invariance, mặc dù `Integer` kế thừa `Number`. Autoboxing không biến `List<Integer>` thành `List<Number>`.

## 6. Những chuyển đổi Java không tự thực hiện

Autoboxing **không** có nghĩa mọi primitive có thể gán cho mọi wrapper số. Ngữ cảnh và chuỗi chuyển đổi đều quan trọng.

```java
Integer a = 10; // Đúng: int -> Integer.
Long b = 10L;   // Đúng: long -> Long.
Double c = 1.0; // Đúng: double -> Double.

// Long invalid = 10;   // Sai: không tự nối int -> long -> Long.
// Double bad = 1;      // Sai: không tự nối int -> double -> Double.
```

Cách làm rõ nghĩa:

```java
long widened = 10; // int -> long.
Long wrapped = widened; // long -> Long.
// Hoặc:
Long also = 10L;
```

Tương tự, Java không tự đổi wrapper thành wrapper khác bằng phép gán:

```java
Integer input = 10;
// Long invalid = input; // Không biên dịch.
Long converted = input.longValue(); // long -> Long.
```

Cần lưu ý một ngoại lệ ở **ngữ cảnh gán hằng số**: Java cho phép thu hẹp một biểu thức hằng `int` nằm trong miền `byte`, `short` hoặc `char`, rồi boxing vào wrapper tương ứng. Ví dụ:

```java
Byte small = 100; // Hợp lệ: hằng int 100 nằm trong miền byte.
Short shortValue = 123; // Hợp lệ.
// Byte outside = 200; // Lỗi: 200 vượt miền byte.
```

Đây là quy tắc đặc biệt về **constant expression và assignment conversion**, không phải bằng chứng rằng Java tự cho phép mọi chuyển đổi số học rồi boxing. Với biến `int` thông thường, `Byte boxed = someInt;` không hợp lệ nếu không có bước chuyển kiểu rõ ràng.

## 7. Autoboxing và unboxing trong biểu thức số học

Khi wrapper xuất hiện trong phép toán số học, Java thường phải **unbox** để lấy primitive, rồi áp dụng quy tắc nâng kiểu số học của biểu thức.

```java
Integer a = 7;
Integer b = 5;

int sum = a + b; // Unbox a,b -> int; cộng int cho 12.
Integer boxedSum = a + b; // Tính phép cộng int, rồi boxing 12.
```

Câu `Integer boxedSum = a + b` **không có nghĩa hai đối tượng `Integer` cộng trực tiếp với nhau**. Giá trị cần được lấy ra khỏi wrapper, thực hiện phép cộng primitive rồi mới boxing kết quả để gán.

### Gán ghép và tăng giảm wrapper

```java
Integer count = 7;
Integer original = count;

count += 5; // Unbox -> phép cộng int -> boxing về Integer.
count++;    // Unbox -> tăng 1 -> boxing lại.

System.out.println(original); // 7
System.out.println(count);    // 13
```

Đối tượng `original` vẫn chứa `7` vì wrapper **bất biến**. Biến `count` sau các phép toán giữ tham chiếu tới đối tượng boxing kết quả mới (hoặc đối tượng tái sử dụng từ cache), chứ không sửa giá trị của đối tượng cũ.

Những phép toán này vẫn chịu giới hạn miền nguyên thủy:

```java
Integer max = Integer.MAX_VALUE;
max++; // Phép cộng int vượt giới hạn và wraparound.
System.out.println(max); // -2147483648
```

Boxing không tự thêm kiểm tra tràn số. Nếu tràn không được phép, dùng `Math.addExact` hoặc kiểm tra biên phù hợp trước khi boxing kết quả.

## 8. Bẫy quan trọng: wrapper có thể `null`

Primitive không thể là `null`, wrapper có thể:

```java
Integer optionalCount = null;

// int count = optionalCount; // Khi thực thi sẽ ném NullPointerException.
```

Không có giá trị `int` tương ứng với `null`. Bất cứ khi nào Java cần **unbox một tham chiếu null**, chương trình ném `NullPointerException`.

Các tình huống thường gặp:

```java
Integer a = null;

// int x = a;         // NPE khi unbox.
// int y = a + 1;     // NPE trước phép cộng.
// a++;               // NPE khi unbox.
// boolean eq = a == 0; // NPE khi so sánh với primitive 0.
```

Trong khi đó, **boxing một primitive hợp lệ không tự tạo null**; rủi ro ở đây phát sinh từ nơi wrapper có thể chứa null.

Một cách xử lý rõ ràng:

```java
Integer count = null;
int safe = count != null ? count : 0;
System.out.println(safe); // 0
```

Quy tắc `null -> 0` phải là **quyết định nghiệp vụ**, không phải mặc định của autounboxing. Nếu null nghĩa là “chưa biết”, “chưa nhập” hoặc “không áp dụng”, thay bằng 0 có thể làm sai dữ liệu. Khi cần giữ trạng thái thiếu dữ liệu, dùng wrapper/Optional hoặc thông báo lỗi rõ ràng thay vì ép về primitive.

Nếu wrapper được truyền qua `List<Integer>` hoặc `Map<String, Integer>`, dữ liệu lấy ra vẫn có thể `null`. Autoboxing ở bước thêm phần tử không bảo đảm mọi lần đọc sau đều an toàn để unbox.

## 9. Wrapper và dấu `==`: không dùng danh tính làm phép so sánh số

Khi **cả hai toán hạng là tham chiếu wrapper**:

```java
Integer first = Integer.valueOf(1_000);
Integer second = Integer.valueOf(1_000);

System.out.println(first.equals(second)); // true
```

Phương thức `equals` của wrapper so sánh **giá trị theo hợp đồng của lớp**, còn `first == second` so sánh **có cùng đối tượng hay không**. Đừng lấy `==` giữa hai wrapper làm tiêu chí bằng nhau của số.

Có cơ chế **cache/tái sử dụng** đối tượng khi boxing một số giá trị nhỏ. Ví dụ, đối với `Integer`, giá trị `100` thuộc miền được bảo đảm tái sử dụng trong boxing:

```java
Integer a = 100;
Integer b = 100;
System.out.println(a == b); // true theo bảo đảm boxing cho giá trị này.
```

Nhưng với giá trị lớn hơn, việc tái sử dụng đối tượng phụ thuộc quy tắc và triển khai, nên không được viết:

```java
Integer x = 1_000;
Integer y = 1_000;

// boolean equalNumbers = (x == y); // Không dùng: so sánh danh tính.
boolean equalNumbers = x.equals(y); // true.
```

**Đừng giả định mọi giá trị ngoài cache luôn trả false khi dùng `==`**; cách triển khai có thể tái sử dụng một số đối tượng. Dùng `equals` khi muốn so sánh wrapper cùng kiểu, hoặc unbox có kiểm tra null nếu muốn so sánh primitive.

Khi một vế là primitive:

```java
Integer boxed = 5;
int primitive = 5;
System.out.println(boxed == primitive); // true, boxed được unbox.
```

Lúc này `==` là phép so sánh giá trị primitive, không phải so sánh danh tính tham chiếu. Sự khác nhau này giải thích vì sao đổi kiểu khai báo biến có thể vô tình thay đổi ý nghĩa của cùng ký hiệu `==`.

Lưu ý với `Float`/`Double`, các hợp đồng `equals` còn khác `==` primitive ở các giá trị `NaN` và `+0.0`/`-0.0`. Khi dùng wrapper làm khóa `HashMap`/`HashSet`, các collection dựa trên `equals` và `hashCode`, không phải phép so sánh `==` của primitive.

## 10. Ảnh hưởng tới hiệu năng và bộ nhớ

Kiểu wrapper là **đối tượng**, vì vậy có thể đòi hỏi thêm bộ nhớ, việc cấp phát/quản lý đối tượng và chuyển đổi so với làm việc trực tiếp bằng primitive. Trình biên dịch/JVM có thể tối ưu nhiều trường hợp, nhưng không nên giả định việc autoboxing là “miễn phí” trong tất cả vòng lặp nóng hoặc tập dữ liệu lớn.

Ví dụ:

```java
long total = 0L;
for (int i = 0; i < 1_000_000; i++) {
    total += i; // Toàn bộ đường tính toán dùng primitive.
}
```

So với:

```java
Long total = 0L;
for (int i = 0; i < 1_000_000; i++) {
    total += i; // Unboxing và boxing lại tổng mỗi lần lặp.
}
```

Đây là ví dụ để nhận biết **các chuyển đổi được yêu cầu về mặt ngữ nghĩa**, không phải benchmark khẳng định tốc độ chính xác. Hiệu năng thực tế phụ thuộc JVM, tối ưu hóa JIT, escape analysis, kích thước dữ liệu và cách đo.

Khi cần xử lý rất nhiều số nguyên, cân nhắc:

- Dùng `int[]`/`long[]`/`double[]` thay vì mảng wrapper nếu không cần `null` hay API đối tượng.
- Dùng `IntStream`, `LongStream`, `DoubleStream` cho pipeline dữ liệu primitive; gọi `boxed()` chỉ khi cần chuyển sang `Stream<Integer>`, `Stream<Long>` hoặc `Stream<Double>`.
- Dùng `List<Integer>` hoặc wrapper khi API generic, dữ liệu tùy chọn/nullable và cấu trúc tập hợp đòi hỏi đối tượng.

**Không tối ưu vội:** ưu tiên đúng nghĩa và rõ ràng, sau đó dùng benchmark phù hợp (ví dụ JMH) để kiểm chứng chi phí trong phần chương trình thực sự quan trọng.

## 11. Không nhầm autoboxing với mọi chuyển đổi ngầm

Có một số tình huống trông như “biến số thành đối tượng” hoặc “in một số ra màn hình” nhưng **không bắt buộc autoboxing xảy ra**:

```java
System.out.println(10);          // Có overload println(int).
String message = "count=" + 10; // Nối chuỗi có quy tắc string conversion.
```

Không thể lấy hai dòng này làm bằng chứng rằng mọi primitive luôn được tạo thành wrapper. Autoboxing là chuyển đổi được áp dụng trong các ngữ cảnh định kiểu nhất định; nối chuỗi và lựa chọn overload có thể hoạt động mà không cần tạo wrapper.

Tương tự, cast kiểu tham chiếu thông thường và autoboxing là hai việc khác nhau. Việc chuyển `Number number = 10;` tạo ra `Integer` rồi mở rộng kiểu tham chiếu không có nghĩa `Number` là lớp bao trực tiếp cho `int`. Và việc gọi `Integer.valueOf("10")` là **phân tích chuỗi rồi tạo Integer**, không phải autoboxing của một giá trị `String`.

## 12. Ví dụ Java 17+ hoàn chỉnh

Tạo tệp **`AutoboxingContextsDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.function.Supplier;

public class AutoboxingContextsDemo {
    static void receive(Integer value) {
        System.out.println("method=" + value);
    }

    static void choose(long value) {
        System.out.println("overload=long");
    }

    static void choose(Integer value) {
        System.out.println("overload=Integer");
    }

    static Integer boxReturn(int input) {
        return input;
    }

    public static void main(String[] args) {
        int primitive = 7;
        Integer boxed = primitive;
        int unboxed = boxed;

        System.out.println("assignment=" + boxed);
        System.out.println("unboxed=" + unboxed);

        receive(8); // Autoboxing tham số.
        choose(1);  // Widening primitive ưu tiên hơn boxing.

        Object object = 2.5;
        Number number = 6;
        System.out.println("Object holds="
                + object.getClass().getSimpleName());
        System.out.println("Number holds="
                + number.getClass().getSimpleName());

        Integer[] array = {2, 3};
        System.out.println("array second=" + array[1]);

        List<Integer> values = new ArrayList<>();
        values.add(4);
        values.add(5);
        int sum = 0;
        for (int value : values) {
            sum += value; // Unbox mỗi Integer.
        }
        System.out.println("list=" + values);
        System.out.println("list sum=" + sum);

        System.out.println("return boxed=" + boxReturn(12));

        Supplier<Integer> supplier = () -> 13;
        System.out.println("lambda boxed=" + supplier.get());

        Integer smallA = 100;
        Integer smallB = 100;
        System.out.println("small cached identity=" + (smallA == smallB));

        Integer largeA = 1_000;
        Integer largeB = 1_000;
        System.out.println("large equals=" + largeA.equals(largeB));

        Integer current = 7;
        Integer previous = current;
        current += 5;
        System.out.println("updated=" + current);
        System.out.println("previous=" + previous);

        Integer missing = null;
        try {
            int willFail = missing;
            System.out.println(willFail);
        } catch (NullPointerException ex) {
            System.out.println("null unboxing=NullPointerException");
        }
    }
}
```

Biên dịch và chạy:

```bash
javac AutoboxingContextsDemo.java
java AutoboxingContextsDemo
```

Kết quả:

```text
assignment=7
unboxed=7
method=8
overload=long
Object holds=Double
Number holds=Integer
array second=3
list=[4, 5]
list sum=9
return boxed=12
lambda boxed=13
small cached identity=true
large equals=true
updated=12
previous=7
null unboxing=NullPointerException
```

Ví dụ thể hiện năm nhóm chuyển đổi: **gán**, **đối số phương thức**, **mảng/generic collection**, **giá trị trả về/lambda**, và **unboxing trong phép toán**. Nó không dựa vào kết quả so sánh danh tính với giá trị lớn ngoài vùng cache; chỉ sử dụng `equals` cho trường hợp đó.

## 13. Các lỗi phổ biến và cách tránh

| Nhầm lẫn | Vì sao sai | Cách làm đúng |
| --- | --- | --- |
| “Autoboxing là đổi mọi primitive sang mọi wrapper.” | Boxing ánh xạ tới wrapper tương ứng và bị giới hạn bởi ngữ cảnh chuyển đổi. | Chọn literal đúng kiểu, dùng cast hoặc chuyển đổi tường minh khi cần. |
| “`Long x = 5` chắc chắn hợp lệ vì `int` mở rộng sang `long`.” | Phép gán không tự nối `int → long → Long`. | `Long x = 5L` hoặc chuyển qua biến `long`. |
| “`List<int>` có thể dùng giống `List<Integer>`.” | Tham số kiểu generics phải là kiểu tham chiếu. | Sử dụng `List<Integer>` hoặc cấu trúc primitive. |
| “`int[]` sẽ tự boxing thành `Integer[]`.” | Boxing không áp dụng trực tiếp cho cả mảng. | Chuyển từng phần tử. |
| “Wrapper luôn không null vì autoboxing.” | Biến/collection tham chiếu có thể giữ `null`. | Kiểm tra null trước khi unbox. |
| “`Integer a == Integer b` luôn so sánh giá trị số.” | Nếu cả hai là tham chiếu, `==` so sánh danh tính. | Dùng `equals` hoặc unbox an toàn. |
| “Ngoài miền cache, `==` chắc chắn false.” | Cách tái sử dụng wrapper ngoài miền bảo đảm không nên được giả định. | Không phụ thuộc identity của boxed number. |
| “`Integer count++;` sửa đối tượng `Integer` tại chỗ.” | Wrapper bất biến; thao tác unbox, tính, rồi box và gán lại. | Hiểu rõ kiểu primitive bên trong phép toán. |
| “Autoboxing ngăn phép toán nguyên tràn số.” | Phép tính vẫn dùng primitive và tuân thủ giới hạn của nó. | Kiểm tra biên/`Math.*Exact` nếu hợp đồng cấm tràn. |
| “Mọi chỗ in số/nghiệm chuỗi đều cấp phát wrapper.” | Overload primitive và string conversion không đồng nghĩa boxing. | Xem đúng API và kiểu biểu thức. |
| “Dùng wrapper trong vòng lặp không thể tốn chi phí.” | Chuyển đổi và quản lý đối tượng có thể phát sinh overhead. | Dùng primitive khi phù hợp, đo hiệu năng trước khi tối ưu. |

## 14. Checklist khi áp dụng autoboxing trong mã nguồn

1. **Kiểu nguồn/đích:** primitive nào được chuyển tới wrapper nào? Có cần widening primitive hay narrowing trước khi boxing không?
2. **Ngữ cảnh:** gán, return, gọi hàm, lambda hay generic collection có cho phép chuyển đổi đó không?
3. **Khả năng null:** wrapper này đến từ đâu? Có thể là `null` khi unboxing không?
4. **So sánh:** bạn cần so sánh giá trị `equals` hay danh tính đối tượng `==`? Nếu là `Float`/`Double`, các trường hợp NaN/signed zero có quan trọng không?
5. **Overloading:** nếu cùng tên hàm có tham số primitive và wrapper, overload nào được chọn theo pha resolution?
6. **Độ chính xác và giới hạn:** boxing chỉ đóng gói giá trị; không sửa tràn số, không phục hồi sai số dấu phẩy động.
7. **Chi phí:** cấu trúc generic có thật sự cần wrapper không, hay kiểu primitive/mảng/stream primitive đủ dùng?
8. **API/độ rõ:** khi nghi ngờ, dùng `Integer.valueOf`, `longValue()`, chuyển kiểu rõ ràng hoặc tách câu lệnh để làm sáng tỏ chuyển đổi.

**Ghi nhớ:** Autoboxing là chuyển đổi do Java tự cung cấp từ **primitive sang wrapper tương ứng trong những ngữ cảnh định kiểu cho phép**. Nó thuận tiện cho API đối tượng và generics, nhưng không tạo ra kiểu số mới, không xử lý tràn, không tự bảo đảm wrapper khác `null`, không thay đổi quy tắc so sánh danh tính và có thể mang chi phí hiệu năng. Hiểu chính xác thời điểm boxing/unboxing giúp tránh lỗi biên dịch, `NullPointerException` và các bug khó nhận ra khi xử lý số.

**Tài liệu tham khảo:** [JLS §5.1.7 — Boxing Conversion](https://docs.oracle.com/javase/specs/jls/se21/html/jls-5.html#jls-5.1.7), [JLS §5.1.8 — Unboxing Conversion](https://docs.oracle.com/javase/specs/jls/se21/html/jls-5.html#jls-5.1.8), [JLS §5.2 — Assignment Contexts](https://docs.oracle.com/javase/specs/jls/se21/html/jls-5.html#jls-5.2), [JLS §5.3 — Invocation Contexts](https://docs.oracle.com/javase/specs/jls/se21/html/jls-5.html#jls-5.3), [JLS §15.12.2 — Compile-Time Step 2: Determine Method Signature](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.12.2), [Integer API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Integer.html).
