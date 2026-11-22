# Arrays.stream cho object và primitive: nguồn Stream từ mảng trong Java

`java.util.Arrays.stream(...)` là cách tiêu chuẩn để tạo **Stream từ một mảng Java**. Nó có các overload cho mảng phần tử tham chiếu (`T[]`) và đúng ba loại mảng primitive: `int[]`, `long[]`, `double[]`. Kết quả không phải lúc nào cũng là `Stream<T>`: các mảng số nguyên thủy có các stream chuyên biệt nhằm tránh boxing không cần thiết.

Cơ chế này xuất hiện từ Java 8 và vẫn được sử dụng trong Java hiện đại. Bài sử dụng ngữ nghĩa API hiện hành, ưu tiên ví dụ **Java 17+** có thể biên dịch và chạy độc lập; những tính năng ra đời sau Java 8 như `Stream.toList()` được ghi chú rõ. Không cần sử dụng mẹo phụ thuộc cấu trúc nội bộ JDK.

**Sau bài này, bạn cần trả lời chính xác:**

1. Khi nào `Arrays.stream(array)` tạo `Stream<T>`, `IntStream`, `LongStream` hoặc `DoubleStream`?
2. Vì sao `Arrays.stream(new int[]{1,2,3})` khác `Stream.of(new int[]{1,2,3})`?
3. Các overload `Arrays.stream(array, startInclusive, endExclusive)` chọn phần tử nào, biên nào gây lỗi?
4. Làm thế nào chuyển qua `boxed()`, `mapToInt` hoặc `mapToObj` khi API cần kiểu khác?
5. Tại sao `byte[]`, `short[]`, `char[]`, `boolean[]` và `float[]` không gọi trực tiếp `Arrays.stream` được?
6. Mảng hai chiều được stream theo **hàng** hay theo **phần tử bên trong**?
7. Khi nào nên dùng `sum`, `average`, `summaryStatistics`, `toArray` hoặc `toList`?
8. Điều gì cần tránh với `null`, thay đổi mảng trong khi traversal, side effects và parallel streams?

## 1. Phân biệt mảng dữ liệu với Stream pipeline

Một mảng là cấu trúc lưu phần tử trong bộ nhớ:

```java
String[] languages = {"Java", "Kotlin", "Scala"};
```

Một Stream là **một cách mô tả và thực hiện quá trình duyệt/xử lý** dữ liệu từ nguồn. Nó không sao chép mảng thành một collection mới chỉ vì ta gọi `stream`:

```java
Stream<String> words = Arrays.stream(languages);
```

Hai đoạn là **minh họa**, cần import `java.util.Arrays` và `java.util.stream.Stream`. `words` là một sequential Stream có mảng `languages` làm nguồn. Có thể tiếp tục bằng các intermediate operations:

```java
List<Integer> lengths = Arrays.stream(languages)
        .map(String::length)
        .toList();
System.out.println(lengths); // [4, 6, 5]
```

Đoạn minh họa cần `java.util.List`. `map` là intermediate operation và thực hiện theo pipeline khi terminal operation `toList()` cần kết quả. `Stream.toList()` có từ Java 16, trả danh sách không hỗ trợ các thao tác thay đổi nội dung/cấu trúc; nó phù hợp khi bạn chỉ cần kết quả để đọc.

**Ba khái niệm khác nhau:**

- **Mảng**: nguồn phần tử, có chỉ số và độ dài cố định.
- **Stream**: pipeline xử lý các phần tử từ nguồn, có thể lazy và chỉ tiêu thụ một lần.
- **Kết quả terminal operation**: scalar, `Optional`, `List`, mảng mới hoặc hiệu ứng khác, tùy phương thức cuối.

Mảng vẫn tồn tại sau khi stream bị tiêu thụ; có thể gọi `Arrays.stream(languages)` **một lần nữa** để tạo stream mới. Nhưng không được chạy một terminal operation thứ hai trên **cùng Stream instance** đã tiêu thụ.

## 2. Bảng overload Arrays.stream quan trọng

| Đối số truyền vào | Kiểu stream nhận được | Kiểu phần tử stream |
| --- | --- | --- |
| `String[]` | `Stream<String>` | `String` |
| `Person[]` | `Stream<Person>` | `Person` |
| `Integer[]` | `Stream<Integer>` | `Integer` wrapper |
| `int[]` | `IntStream` | `int` primitive |
| `long[]` | `LongStream` | `long` primitive |
| `double[]` | `DoubleStream` | `double` primitive |
| `String[][]` | `Stream<String[]>` | Mỗi phần tử là một hàng `String[]` |
| `int[][]` | `Stream<int[]>` | Mỗi phần tử là một hàng `int[]` |
| `byte[]`, `char[]`, `float[]`, `boolean[]`, `short[]` | **Không có overload trực tiếp** | Cần cách tiếp cận khác |

Các overload còn có biến thể nhận **khoảng chỉ số**:

```java
Arrays.stream(T[] array, int startInclusive, int endExclusive)
Arrays.stream(int[] array, int startInclusive, int endExclusive)
Arrays.stream(long[] array, int startInclusive, int endExclusive)
Arrays.stream(double[] array, int startInclusive, int endExclusive)
```

Bốn dòng trên là **chữ ký mô tả API**, không phải các lời gọi Java dùng trực tiếp: `T` là type parameter của phương thức generic. Mỗi phương thức trả một **sequential stream**, có encounter order theo trình tự phần tử/indices của đoạn mảng tương ứng.

**Mẹo nhớ:** Java chỉ có các primitive stream specializations chuẩn là `IntStream`, `LongStream` và `DoubleStream`. Đừng tự suy từ `byte`, `boolean` hay `char` rằng JDK cũng có `ByteStream`, `BooleanStream` hoặc `CharStream` tương tự — không có các loại stream chuyên biệt đó trong `java.util.stream`.

## 3. Mảng object: Arrays.stream(T[]) trả Stream<T>

`Arrays.stream(T[])` áp dụng cho những mảng có **component type là reference type**, như `String[]`, `Integer[]`, `Customer[]` hoặc `List<String>[]` (khi mảng đó đã tồn tại hợp lệ).

```java
String[] names = {"An", "Binh", "Chi"};

List<String> selected = Arrays.stream(names)
        .filter(s -> s.length() > 2)
        .toList();

System.out.println(selected); // [Binh, Chi]
```

Đây là đoạn minh họa cần `Arrays` và `List`. Lambda `s` được suy ra là `String`; `filter` giữ encounter order của những phần tử vượt điều kiện; `toList()` đưa ra danh sách theo thứ tự đó.

### Generic type được suy luận từ mảng

```java
record Product(String id, int price) {}

Product[] products = {
    new Product("A", 20),
    new Product("B", 30)
};

List<String> codes = Arrays.stream(products)
        .map(Product::id)
        .toList();
```

Đây là đoạn minh họa cần đặt trong một class/method phù hợp. `record` được chuẩn hóa từ Java 16, dùng được trên Java 17+. `Arrays.stream(products)` có kiểu `Stream<Product>`, `Product::id` trả `String`, kết quả `codes` là `[A, B]`.

**Chú ý:** `Arrays.stream(T[])` không loại bỏ `null`. Nếu mảng có phần tử null, stream vẫn có thể chuyển phần tử null tới mapper. `String::length` trên phần tử null có thể ném `NullPointerException`. Với dữ liệu có thể chứa null, cần quyết định chính sách xử lý rõ ràng trước khi dùng method reference.

```java
String[] raw = {"A", null, "B"};

List<String> clean = Arrays.stream(raw)
        .filter(Objects::nonNull)
        .toList();

System.out.println(clean); // [A, B]
```

Đây là minh họa cần `java.util.Objects`. Không nên ngầm bỏ null nếu null mang ý nghĩa nghiệp vụ; chỉ lọc khi đã có quy tắc dữ liệu phù hợp.

## 4. int[]: Arrays.stream trả IntStream, không phải Stream<Integer>

```java
int[] scores = {5, 2, 7, 1};

IntStream values = Arrays.stream(scores);
int total = values.sum();

System.out.println(total); // 15
```

Đây là minh họa cần import `java.util.stream.IntStream`. `IntStream` cung cấp các terminal operations chuyên biệt: `sum()`, `average()`, `min()`, `max()`, `summaryStatistics()` và phép biến đổi trên primitive values.

Vì sao không phải `Stream<Integer>`? Một `Stream<Integer>` chứa reference đến wrapper `Integer`, trong khi `IntStream` xử lý trực tiếp giá trị `int` trong các thao tác chuyên biệt, tránh boxing/unboxing mỗi phần tử ở những bước không cần thiết.

### Các phép tính thông dụng

```java
int[] data = {4, 1, 3, 2};

int sum = Arrays.stream(data).sum();                 // 10
long count = Arrays.stream(data).count();            // 4
double avg = Arrays.stream(data).average()
        .orElseThrow();                              // 2.5
int min = Arrays.stream(data).min().orElseThrow();   // 1
int max = Arrays.stream(data).max().orElseThrow();   // 4
```

Đây là đoạn minh họa cần `Arrays`. Mỗi phép tính tạo một stream **mới** từ cùng mảng, vì không thể dùng lại một `IntStream` sau terminal operation.

### Empty array và Optional

```java
int[] empty = {};

System.out.println(Arrays.stream(empty).sum()); // 0
System.out.println(Arrays.stream(empty).count()); // 0
System.out.println(Arrays.stream(empty).average().isPresent()); // false
```

Đây là minh họa. `sum()` trả identity `0` cho tập rỗng, còn `average()` trả `OptionalDouble.empty()` vì không có trung bình toán học của 0 phần tử. Tương tự `min()`/`max()` trả `OptionalInt.empty()` khi không có phần tử.

Không viết `average().getAsDouble()` nếu mảng có thể rỗng mà không kiểm tra; dùng `orElse(...)`, `orElseThrow()` hoặc phân nhánh từ `isPresent()` theo yêu cầu nghiệp vụ.

## 5. long[]: LongStream và các phép tổng hợp số nguyên dài

```java
long[] amounts = {1_000_000_000L, 2_000_000_000L, 3_000_000_000L};

long total = Arrays.stream(amounts).sum();
System.out.println(total); // 6000000000
```

Đây là minh họa. Nếu cố lưu tổng `6_000_000_000` vào kiểu `int` sẽ vượt phạm vi số nguyên 32 bit; `LongStream` giúp phép tổng hoạt động với kiểu `long`.

`LongStream` có `sum`, `min`, `max`, `average` và `summaryStatistics` tương tự `IntStream`. Tuy nhiên **`long` vẫn có giới hạn**, phép cộng tràn số nguyên `long` cũng có thể xảy ra. Không coi `LongStream.sum()` là kiểu số không giới hạn. Với bài toán kế toán cần độ chính xác/thang đo đặc thù, cân nhắc `BigDecimal` hoặc chiến lược số học thích hợp thay vì `double` hay tổng nguyên tùy ý.

### Khi int[] có nguy cơ tổng vượt int

```java
int[] measurements = {1_500_000_000, 1_500_000_000};

long safeTotal = Arrays.stream(measurements)
        .asLongStream()
        .sum();

System.out.println(safeTotal); // 3000000000
```

Đây là minh họa. `asLongStream()` nâng mỗi giá trị `int` thành `long` trước phép tổng. Đừng gọi `IntStream.sum()` rồi cast kết quả sang `long`, vì nếu tổng `int` đã tràn thì ép kiểu **sau đó** không khôi phục giá trị chính xác.

## 6. double[]: DoubleStream cho phép tính dấu phẩy động

```java
double[] weights = {1.5, 2.0, 2.5};

double sum = Arrays.stream(weights).sum();
double avg = Arrays.stream(weights).average().orElseThrow();

System.out.println(sum); // 6.0
System.out.println(avg); // 2.0
```

Đây là đoạn minh họa. `DoubleStream` dùng primitive `double`, có `sum`, `average`, `min`, `max`, `summaryStatistics` và các phép ánh xạ thích hợp.

### Cảnh giác độ chính xác floating-point

Các phép cộng `double` chịu ảnh hưởng IEEE 754: `0.1 + 0.2` không có biểu diễn thập phân tuyệt đối chính xác trong nhị phân. Với phép tính có nhiều phần tử, các cách nhóm khác nhau có thể tạo khác biệt làm tròn; thư viện cũng có thể dùng kỹ thuật tính tổng nâng độ chính xác. Không kiểm thử `double` bằng việc giả định mọi số thập phân đều có biểu diễn chính xác.

`DoubleStream` không phải lựa chọn thay cho `BigDecimal` trong mọi bài toán tiền tệ. Nếu cần quy tắc làm tròn/thập phân chính xác theo domain, dùng mô hình số học tương ứng.

### NaN và Infinity

Mảng `double[]` có thể chứa `Double.NaN`, `POSITIVE_INFINITY` hoặc `NEGATIVE_INFINITY`. Các operations số học có contract cho các trường hợp này. Khi dữ liệu bên ngoài có thể chứa giá trị đặc biệt, hãy xác định chính sách lọc/từ chối rõ trước khi báo cáo trung bình hoặc tổng, thay vì xem mọi `double` đều là số hữu hạn.

## 7. Phiên bản range: [startInclusive, endExclusive)

Mỗi overload `Arrays.stream` nêu trên còn có biến thể chỉ duyệt **một đoạn liên tiếp** của mảng.

```java
int[] values = {10, 20, 30, 40, 50};

int[] middle = Arrays.stream(values, 1, 4).toArray();

System.out.println(Arrays.toString(middle)); // [20, 30, 40]
```

Đây là minh họa. Chỉ số `1` được **lấy**, chỉ số `4` bị **loại trừ**. Công thức chiều dài của đoạn là `endExclusive - startInclusive`, nếu hai biên hợp lệ.

| Lời gọi | Phần tử chọn | Kết quả |
| --- | --- | --- |
| `Arrays.stream(values,0,5)` | Toàn bộ 5 phần tử | `[10,20,30,40,50]` |
| `Arrays.stream(values,1,4)` | Chỉ số 1,2,3 | `[20,30,40]` |
| `Arrays.stream(values,3,3)` | Đoạn rỗng | `[]` |
| `Arrays.stream(values,5,5)` | Đoạn rỗng tại cuối | `[]` |
| `Arrays.stream(values,-1,2)` | Biên âm | Ném `ArrayIndexOutOfBoundsException` |
| `Arrays.stream(values,4,3)` | `endExclusive < startInclusive` | Ném `ArrayIndexOutOfBoundsException` |
| `Arrays.stream(values,0,6)` | `endExclusive > length` | Ném `ArrayIndexOutOfBoundsException` |

**Lưu ý:** vì đây là mảng, boundary violation của overload `Arrays.stream(array,start,end)` được API khai báo là `ArrayIndexOutOfBoundsException`, không phải mặc nhiên `IndexOutOfBoundsException` cho mọi trường hợp.

### Range trên object[]

```java
String[] letters = {"A", "B", "C", "D"};

List<String> slice = Arrays.stream(letters, 1, 3).toList();

System.out.println(slice); // [B, C]
```

Đây là minh họa. Kết quả được tạo từ các phần tử chỉ số 1 và 2. Range bản thân nó **không trả bản sao mảng**, mà tạo một stream trên phần mảng được yêu cầu; `toList` là terminal operation tạo kết quả mới.

### Range trên long[] và double[]

```java
long[] times = {10L, 20L, 30L};
double[] rates = {1.5, 2.5, 3.5};

System.out.println(Arrays.stream(times, 1, 3).sum());  // 50
System.out.println(Arrays.stream(rates, 0, 2).sum());   // 4.0
```

Đây là các minh họa. Khi tính toán một cửa sổ mảng đã biết chỉ số đầu/cuối, overload range thể hiện ý định rõ hơn việc tạo toàn bộ stream rồi gọi `skip`/`limit`. Với truy vấn phức tạp, lựa chọn còn tùy hiệu năng và khả năng đọc của pipeline.

## 8. Arrays.stream so với Stream.of: bẫy primitive array

`Stream.of(...)` và `Arrays.stream(...)` không hoàn toàn thay thế nhau.

### Với object array

```java
String[] words = {"Java", "API"};

Stream<String> a = Arrays.stream(words);
Stream<String> b = Stream.of(words);
```

Đây là minh họa cần `Stream`. Với mảng tham chiếu `String[]`, cả hai biểu thức thường cho `Stream<String>` gồm hai chuỗi nhờ overload varargs của `Stream.of`.

### Với int[]: kiểu hoàn toàn khác

```java
int[] numbers = {1, 2, 3};

IntStream ints = Arrays.stream(numbers);
Stream<int[]> oneArray = Stream.of(numbers);

System.out.println(ints.count());       // 3
System.out.println(oneArray.count());   // 1
```

Đây là minh họa cần `IntStream` và `Stream`. `Stream.of(numbers)` xem cả `int[]` là **một phần tử reference**, không tự tạo `IntStream` các giá trị 1, 2, 3.

Kết luận:

- Muốn duyệt **từng int**, dùng `Arrays.stream(int[])` hoặc `IntStream.of(1,2,3)`.
- Muốn một stream **chỉ chứa object int[] làm phần tử**, `Stream.of(numbers)` có thể phù hợp nhưng phải rõ mục đích.
- Không khai báo `Stream<Integer> s = Stream.of(numbers);` rồi kỳ vọng boxing mỗi `int` — đây không phải cùng một kiểu.

### Arrays.asList và primitive array

Một bẫy tương tự:

```java
int[] numbers = {1, 2, 3};

List<int[]> list = Arrays.asList(numbers);
System.out.println(list.size()); // 1
```

Đây là minh họa. `Arrays.asList(numbers)` có một phần tử kiểu `int[]`, không phải `List<Integer>` ba phần tử. Nếu thực sự cần `List<Integer>`, dùng `Arrays.stream(numbers).boxed().toList()`.

## 9. Boxing/unboxing khi chuyển primitive Stream sang object Stream

`IntStream`, `LongStream`, `DoubleStream` cung cấp `boxed()`:

```java
int[] numbers = {4, 1, 3};

List<Integer> boxed = Arrays.stream(numbers)
        .boxed()
        .toList();

System.out.println(boxed); // [4, 1, 3]
```

Đây là minh họa. `boxed()` trả `Stream<Integer>`, sau đó `toList` tạo `List<Integer>`. Tương tự, `LongStream.boxed()` trả `Stream<Long>` và `DoubleStream.boxed()` trả `Stream<Double>`.

**Khi nào nên boxing?** Khi đích API thực sự yêu cầu object references, ví dụ `List<Integer>` hoặc mapper cần wrapper. Nếu chỉ tính `sum`, `average` hoặc `max`, hãy giữ `IntStream` để tránh boxing vô ích.

### mapToObj không giống boxed

```java
String[] labels = Arrays.stream(new int[] {3, 5, 7})
        .mapToObj(n -> "ID-" + n)
        .toArray(String[]::new);

System.out.println(Arrays.toString(labels)); // [ID-3, ID-5, ID-7]
```

Đây là minh họa. `mapToObj` biến mỗi `int` thành **một object do lambda tạo**, ở đây là `String`. `boxed()` chỉ bọc thành kiểu wrapper tương ứng, không tạo nhãn hay DTO.

### Từ Stream<Integer> trở lại IntStream

```java
Integer[] numbers = {2, 4, 6};

int sum = Arrays.stream(numbers)
        .mapToInt(Integer::intValue)
        .sum();

System.out.println(sum); // 12
```

Đây là minh họa. `Integer[]` là object array, nên `Arrays.stream(numbers)` trả `Stream<Integer>`. `mapToInt(Integer::intValue)` thực hiện unboxing để chuyển sang `IntStream`.

Nếu mảng `Integer[]` có phần tử null, việc gọi `intValue()` trên null có thể ném `NullPointerException`. Lọc/validate null trước khi unbox nếu domain cho phép.

## 10. Những primitive arrays không có Arrays.stream overload trực tiếp

Java có tám primitive types, nhưng chỉ có ba primitive stream types chuyên biệt cho `int`, `long` và `double`. Vì vậy những lời gọi dưới đây **không biên dịch**:

```java
// SAI: không có overload Arrays.stream(byte[]).
// Arrays.stream(new byte[] {1, 2});

// SAI: không có overload Arrays.stream(short[]).
// Arrays.stream(new short[] {1, 2});

// SAI: không có overload Arrays.stream(char[]).
// Arrays.stream(new char[] {'A', 'B'});

// SAI: không có overload Arrays.stream(float[]).
// Arrays.stream(new float[] {1.5f, 2.5f});

// SAI: không có overload Arrays.stream(boolean[]).
// Arrays.stream(new boolean[] {true, false});
```

**Không ép kiểu cả mảng** `(int[]) bytes` để “nâng” `byte[]` thành `int[]`. Các primitive array types là những runtime array classes khác nhau; không có phép cast số học theo phần tử cho cả mảng.

### byte[] và short[]: dùng IntStream.range trên chỉ số

```java
byte[] bytes = {1, 2, 3};

int total = IntStream.range(0, bytes.length)
        .map(i -> bytes[i])
        .sum();

System.out.println(total); // 6
```

Đây là minh họa. `bytes[i]` được **widen** từ `byte` sang `int` trong mapper. Với `short[]` làm tương tự, hoặc dùng vòng lặp đơn giản khi pipeline không mang lại ích lợi rõ ràng.

### char[]: mỗi char là UTF-16 code unit

```java
char[] letters = {'A', 'B'};

int[] units = IntStream.range(0, letters.length)
        .map(i -> letters[i])
        .toArray();

System.out.println(Arrays.toString(units)); // [65, 66]
```

Đây là minh họa. `char` là một **UTF-16 code unit**, không đồng nghĩa một Unicode code point hay một grapheme cluster. Nếu mục tiêu là xử lý Unicode text theo code points, có thể dùng `String.codePoints()`, còn text theo code units dùng `String.chars()`. Đừng tự lấy `char[]` rồi giả định mỗi ký tự nhìn thấy trên màn hình chỉ chiếm một `char`.

### float[]: dùng DoubleStream hoặc vòng lặp tùy ngữ nghĩa

```java
float[] readings = {1.5f, 2.5f, 3.0f};

double total = IntStream.range(0, readings.length)
        .mapToDouble(i -> readings[i])
        .sum();

System.out.println(total); // 7.0
```

Đây là minh họa. Mỗi `float` được widen thành `double`. Chuyển sang `double` không tự khôi phục độ chính xác thập phân vốn đã mất khi đọc một `float`; nó chỉ thực hiện phép chuyển đổi số học chuẩn Java.

### boolean[]: đếm hoặc lọc theo chỉ số

```java
boolean[] flags = {true, false, true, true};

long enabled = IntStream.range(0, flags.length)
        .filter(i -> flags[i])
        .count();

System.out.println(enabled); // 3
```

Đây là minh họa. Nếu chỉ cần một vòng lặp đếm đơn giản, vòng lặp `for` cũng rất dễ hiểu và có thể ít overhead hơn. Không bắt buộc đưa mọi mảng vào Stream.

### Tạo object Stream cho primitive arrays không được hỗ trợ

Nếu thật sự cần `Stream<Byte>` hoặc `Stream<Character>`, có thể dùng `IntStream.range(0,array.length).mapToObj(i -> array[i])`; giá trị primitive sẽ được boxing sang wrapper thích hợp theo target type. Nhưng việc này có chi phí boxing và không cần thiết cho các phép tính số đơn giản.

## 11. Mảng hai chiều: stream các hàng trước khi flatten

`int[][]` là mảng của các `int[]`. Vì **mỗi hàng `int[]` là một reference**, overload generic `Arrays.stream(T[])` được chọn và cho `Stream<int[]>`.

```java
int[][] grid = {
    {1, 2},
    {3},
    {4, 5, 6}
};

Stream<int[]> rows = Arrays.stream(grid);
List<Integer> rowLengths = rows
        .map(row -> row.length)
        .toList();

System.out.println(rowLengths); // [2, 1, 3]
```

Đây là minh họa. `Arrays.stream(grid)` **không** tự cho `IntStream` chứa các số 1,2,3,4,5,6.

### Làm phẳng thành IntStream

```java
int[][] grid = {
    {1, 2},
    {3},
    {4, 5, 6}
};

int[] flat = Arrays.stream(grid)
        .flatMapToInt(Arrays::stream)
        .toArray();

System.out.println(Arrays.toString(flat)); // [1, 2, 3, 4, 5, 6]
```

Đây là minh họa. Phép `flatMapToInt(Arrays::stream)` áp dụng `Arrays.stream(int[])` cho mỗi hàng, sau đó gộp các phần tử primitive vào một `IntStream`.

### Với String[][] dùng flatMap

```java
String[][] words = {
    {"a", "b"},
    {"c"}
};

List<String> all = Arrays.stream(words)
        .flatMap(Arrays::stream)
        .toList();

System.out.println(all); // [a, b, c]
```

Đây là minh họa. Với `String[][]`, `Arrays.stream(words)` tạo `Stream<String[]>`, và `flatMap(Arrays::stream)` tạo `Stream<String>`.

**Cẩn thận hàng null:** một mảng hai chiều trong Java có thể chứa hàng null. `Arrays::stream` nhận hàng null sẽ không xử lý được như một mảng hợp lệ. Nếu dữ liệu ngoài có thể có hàng null, validate trước hoặc định nghĩa rõ rằng hàng null được xem là rỗng:

```java
int[][] possibleNullRows = {{1, 2}, null, {3}};
int[] flat = Arrays.stream(possibleNullRows)
        .flatMapToInt(row ->
                row == null ? IntStream.empty() : Arrays.stream(row))
        .toArray();
```

Đây là minh họa; kết quả là `[1,2,3]`. Chọn chính sách này chỉ nếu nghiệp vụ cho phép bỏ qua hàng null; trong hệ thống dữ liệu nghiêm ngặt, fail fast có thể đúng hơn.

## 12. Stream.toArray(): kết quả kiểu mảng chính xác

Các primitive streams có `toArray()` trả primitive array tương ứng:

| Stream | `toArray()` |
| --- | --- |
| `IntStream` | `int[]` |
| `LongStream` | `long[]` |
| `DoubleStream` | `double[]` |

Ví dụ:

```java
int[] doubled = Arrays.stream(new int[] {1, 2, 3})
        .map(x -> x * 2)
        .toArray();

System.out.println(Arrays.toString(doubled)); // [2, 4, 6]
```

Đây là minh họa. Với object `Stream<T>` thì khác: `toArray()` **không đối số** trả `Object[]`, còn overload nhận `IntFunction<A[]>` có thể tạo đúng component type:

```java
String[] upper = Arrays.stream(new String[] {"a", "b"})
        .map(String::toUpperCase)
        .toArray(String[]::new);

System.out.println(Arrays.toString(upper)); // [A, B]
```

Đây là minh họa. `String[]::new` là array constructor reference; nếu pipeline trả `Integer` thì không thể tùy tiện dùng generator `String[]::new` để lưu giá trị không tương thích mà mong mọi thứ tự chuyển đổi.

### toList() hay toArray()?

- **`toList()`:** khi đích cần một danh sách đọc-only, tiện cho API hiện đại. Đây là phương thức từ Java 16, trả unmodifiable List.
- **`toArray()` trên primitive Stream:** khi cần primitive array để tương tác API/mã hiệu năng cao.
- **`toArray(T[]::new)` trên Stream object:** khi cần đúng runtime array component type.
- **`Collectors.toCollection(ArrayList::new)`:** khi thật sự cần một mutable list có loại rõ ràng.

Không coi `Stream.toList()` mặc nhiên thay thế cho `Collectors.toList()` trong mọi ứng dụng nếu code cũ dựa vào việc chỉnh sửa list kết quả; theo contract, `Collectors.toList()` không bảo đảm một loại/mutability cố định, nên hãy khai báo yêu cầu collection rõ.

## 13. summaryStatistics(): giảm nhiều phép duyệt khi cần nhiều chỉ số

Thay vì tạo stream riêng cho `sum`, `min`, `max` và `count`, có thể dùng `summaryStatistics()`:

```java
int[] scores = {4, 1, 3, 2};

IntSummaryStatistics stats = Arrays.stream(scores)
        .summaryStatistics();

System.out.println(stats.getCount());   // 4
System.out.println(stats.getSum());     // 10
System.out.println(stats.getMin());     // 1
System.out.println(stats.getMax());     // 4
System.out.println(stats.getAverage()); // 2.5
```

Đây là minh họa cần import `java.util.IntSummaryStatistics`. Tương tự có `LongSummaryStatistics` và `DoubleSummaryStatistics`.

Lưu ý:

- `getCount()` trả `long`; khi mảng rất lớn vẫn nên giữ kiểu theo API.
- `getAverage()` là `double`; đừng ép thành int rồi gọi đó là trung bình.
- `getMin()`/`getMax()` của summary statistics trên **tập rỗng** có các giá trị sentinel theo contract; nếu cần phân biệt “không có dữ liệu” với giá trị thật, hãy kiểm tra `getCount()==0` trước.
- `sum()` của `IntStream` có thể tràn kiểu int; `IntSummaryStatistics` lưu sum kiểu `long` và có semantics riêng cho tổng nhiều giá trị.

**Khi nào đáng dùng?** Khi bạn thực sự cần nhiều thống kê trên cùng dữ liệu và muốn một traversal logic. Nếu chỉ cần tổng, `Arrays.stream(values).sum()` rõ ràng hơn.

## 14. Ordered source, sequential mặc định và parallel tùy chọn

`Arrays.stream(...)` tạo **sequential stream**. Để cho phép xử lý song song:

```java
int[] data = {1, 2, 3, 4};

int total = Arrays.stream(data)
        .parallel()
        .sum();

System.out.println(total); // 10
```

Đây là minh họa. Parallel mode không có nghĩa mọi operation chắc chắn nhanh hơn, không hứa số thread cụ thể và không hứa execution order của các callback. Với array source, encounter order theo thứ tự indices vẫn có; một terminal operation bảo toàn order như `toArray` hoặc `toList` có thể tạo kết quả theo source order dù tính toán song song.

### Tránh side effects trên shared mutable state

```java
List<Integer> destination = new ArrayList<>();

// KHÔNG NÊN: ArrayList không thread-safe.
Arrays.stream(new int[] {1, 2, 3})
        .parallel()
        .forEach(destination::add);
```

Đây là **đoạn minh họa phản ví dụ**, cần `List`/`ArrayList`. Thứ tự gọi `forEach` không được bảo đảm trên parallel stream; shared `ArrayList` còn có nguy cơ race condition.

Cách đúng khi muốn mảng kết quả:

```java
int[] doubled = Arrays.stream(new int[] {1, 2, 3})
        .parallel()
        .map(x -> x * 2)
        .toArray();
```

Kết quả mảng là `[2,4,6]` theo encounter order. Không cần một collection mutable chia sẻ giữa các threads.

### Không sửa source array trong lúc dùng stream

Tài liệu `Arrays.stream` coi mảng đầu vào là **không bị thay đổi trong thời gian sử dụng**. Stream không bảo đảm hành vi đúng khi nguồn bị can thiệp không phù hợp trong lúc traversal. Ví dụ:

```java
int[] values = {1, 2, 3};

// KHÔNG NÊN: callback thay đổi chính source trong pipeline.
int[] unsafe = Arrays.stream(values)
        .map(x -> {
            values[0] = 99;
            return x;
        })
        .toArray();
```

Đây là **phản ví dụ**, không lấy một stdout cố định làm chuẩn. Nó vi phạm nguyên tắc non-interference đối với source; kết quả còn phụ thuộc việc khi nào các phần tử được đọc. Hãy biến đổi sang mảng mới hoặc hoàn thành mutation trước khi tạo/tiêu thụ pipeline.

Nếu cần snapshot tránh thay đổi từ code khác, tạo bản sao thích hợp trước:

```java
int[] snapshot = Arrays.copyOf(values, values.length);
int[] output = Arrays.stream(snapshot).map(x -> x * 2).toArray();
```

Đây là minh họa. Bản sao tách array storage, nhưng với **object[]**, `clone`/`copyOf` chỉ sao chép mảng tham chiếu (shallow copy), không tự sao chép sâu những object đang được tham chiếu.

## 15. Vì sao array stream khác Collection.stream()?

Một mảng Java không triển khai `Collection` và không có instance method `stream()`. Vì thế:

```java
int[] numbers = {1, 2, 3};

// SAI: mảng không có .stream().
// numbers.stream();

// ĐÚNG:
int total = Arrays.stream(numbers).sum();
```

Đây là đoạn minh họa. Với `List<Integer>`, `list.stream()` tạo object `Stream<Integer>`; với `int[]`, `Arrays.stream(numbers)` tạo `IntStream`.

| Nhu cầu | Cách nên cân nhắc |
| --- | --- |
| Đã có `String[]` | `Arrays.stream(strings)` |
| Đã có `int[]` và cần tổng | `Arrays.stream(ints).sum()` |
| Đã có `List<String>` | `list.stream()` |
| Muốn vài số nguyên trong pipeline | `IntStream.of(1,2,3)` |
| Muốn dãy số liên tục | `IntStream.range(start,end)` |
| Muốn đối số biến thiên thành object stream | `Stream.of(obj1,obj2,...)` |
| Muốn nhìn dưới dạng từng hàng `int[][]` | `Arrays.stream(matrix)` |
| Muốn tất cả phần tử `int` trong `int[][]` | `Arrays.stream(matrix).flatMapToInt(Arrays::stream)` |

Đừng gọi `Arrays.asList(intArray).stream()` rồi tin rằng nhận được từng số `int`; đây là `Stream<int[]>` gồm một phần tử là cả mảng.

## 16. Empty arrays, null arrays và validation

### Empty array hợp lệ

```java
int[] none = {};

System.out.println(Arrays.stream(none).count()); // 0
System.out.println(Arrays.stream(none).sum());   // 0
```

Không cần tạo một collection rỗng trung gian. Stream từ mảng rỗng hợp lệ; `min`, `max`, `average` sẽ trả Optional rỗng thích hợp.

### Null array không phải empty array

```java
int[] missing = null;

// Ném NullPointerException khi gọi:
 // Arrays.stream(missing);
```

Đây là **đoạn minh họa lỗi**, dòng gọi đã comment. Không nên diễn đạt `Arrays.stream(null)` như một lời gọi luôn tới một overload xác định, vì Java có nhiều overload cho các kiểu mảng không có subtype relation phù hợp, và literal `null` có thể gây **lỗi overload ambiguity khi biên dịch**. Dùng biến typed `int[] missing` để minh họa `NullPointerException` runtime khi hợp đồng hàm yêu cầu một mảng không null.

Nếu hợp đồng ứng dụng xem null array như mảng rỗng, hãy chuyển đổi ở một biên rõ:

```java
int[] safe = missing == null ? new int[0] : missing;
long count = Arrays.stream(safe).count();
```

Đây là minh họa. Chính sách này **không nên áp dụng ngầm** nếu null có nghĩa là “dữ liệu chưa được tải”, “không được phép truy cập” hoặc lỗi mà caller cần biết.

### null elements của object[] là bài toán khác

`Arrays.stream(new String[] {null})` là stream hợp lệ có **một phần tử null**, không phải stream rỗng. Một số terminal operations như `findFirst` có thể ném `NullPointerException` nếu phần tử được chọn là null vì `Optional` không thể chứa null; hãy validate/filter theo domain trước khi dùng những operations đó.

## 17. Hiệu năng: primitive specialization giúp gì?

Với `int[]` đã nằm trong bộ nhớ, `IntStream` không phải tạo `Integer` wrapper cho từng phần tử chỉ để thực hiện các operations nguyên thủy. Điều này có thể giảm allocation và chi phí boxing/unboxing so với một pipeline `Stream<Integer>`.

Nhưng “primitive stream luôn nhanh hơn mọi vòng lặp `for`” là một khẳng định **không có bảo đảm chung**. Hiệu năng phụ thuộc:

- Kích thước array và mức độ lặp lại.
- Chi phí mapper/filter; khả năng JVM tối ưu hóa.
- Boxing khi dùng `boxed` hoặc các API cần object stream.
- Lambda capture, allocation và overhead dựng pipeline.
- Sequential/parallel mode và số lượng phần tử.
- Đặc điểm dữ liệu và cache/locality.

Với một mảng vài phần tử và phép cộng rất đơn giản, vòng lặp `for` có thể rõ và nhanh. Với chuỗi biến đổi/aggregation phức tạp, stream giúp mô tả mục tiêu rõ ràng. Khi tối ưu hiệu năng quan trọng, dùng benchmark đáng tin cậy như JMH, có warmup và kiểm soát tác dụng phụ; không quyết định chỉ từ cảm giác.

### Tránh boxing sớm

```java
int[] numbers = {1, 2, 3, 4};

// Trực tiếp trên primitive:
int sum = Arrays.stream(numbers).sum();

// Boxing chỉ khi thực sự cần List<Integer>:
List<Integer> list = Arrays.stream(numbers).boxed().toList();
```

Đây là minh họa. Nếu cuối pipeline chỉ dùng sum/min/max, ưu tiên giữ primitive stream xuyên suốt.

## 18. Chương trình Java 17+ đầy đủ

Chương trình sau kiểm tra:

- Object array và slice của object array;
- `int[]` với sum và slice theo khoảng;
- `long[]`, `double[]` và aggregation;
- `Integer[]` khác `int[]`;
- `boxed()`, `mapToObj()`, `toArray(String[]::new)`;
- `int[][]` được xem là stream các hàng và cách flatten;
- `char[]`/`boolean[]` khi không có overload Arrays.stream;
- `Stream.of(int[])` có **một phần tử mảng**, khác `IntStream`;
- empty array và pipeline song song bảo toàn encounter order.

Lưu nguyên văn thành **ArraysStreamDemo.java**:

```java
import java.util.Arrays;
import java.util.List;
import java.util.Objects;
import java.util.stream.IntStream;
import java.util.stream.Stream;

public class ArraysStreamDemo {

    public static void main(String[] args) {
        String[] words = {"java", "stream", "api"};

        List<String> wordList = Arrays.stream(words).toList();
        List<String> wordSlice = Arrays.stream(words, 1, 3).toList();
        List<Integer> lengths = Arrays.stream(words)
                .map(String::length)
                .toList();

        System.out.println("objects=" + wordList);
        System.out.println("objectSlice=" + wordSlice);
        System.out.println("lengths=" + lengths);

        int[] numbers = {4, 1, 3, 2};
        System.out.println("intSum=" + Arrays.stream(numbers).sum());
        System.out.println("intSlice=" + Arrays.toString(
                Arrays.stream(numbers, 1, 3).toArray()));
        System.out.println("intAverage=" +
                Arrays.stream(numbers).average().orElseThrow());

        List<Integer> boxed = Arrays.stream(numbers)
                .boxed()
                .toList();
        System.out.println("boxed=" + boxed);

        String[] labels = Arrays.stream(numbers)
                .mapToObj(n -> "N" + n)
                .toArray(String[]::new);
        System.out.println("labels=" + Arrays.toString(labels));

        long[] longs = {
                1_000_000_000L, 2_000_000_000L, 3_000_000_000L
        };
        double[] doubles = {1.5, 2.0, 2.5};

        System.out.println("longSum=" + Arrays.stream(longs).sum());
        System.out.println("doubleSum=" + Arrays.stream(doubles).sum());
        System.out.println("doubleAverage=" +
                Arrays.stream(doubles).average().orElseThrow());

        Integer[] wrappers = {2, 4, 6};
        System.out.println("wrapperSum=" +
                Arrays.stream(wrappers)
                        .mapToInt(Integer::intValue)
                        .sum());

        int[][] matrix = {{1, 2}, {3}, {4, 5}};
        int[] rowLengths = Arrays.stream(matrix)
                .mapToInt(row -> row.length)
                .toArray();
        int[] flattened = Arrays.stream(matrix)
                .flatMapToInt(Arrays::stream)
                .toArray();

        System.out.println("rows=" + Arrays.toString(rowLengths));
        System.out.println("flattened=" + Arrays.toString(flattened));

        char[] letters = {'A', 'B'};
        int[] codeUnits = IntStream.range(0, letters.length)
                .map(i -> letters[i])
                .toArray();
        System.out.println("charUnits=" + Arrays.toString(codeUnits));

        boolean[] flags = {true, false, true};
        long trueCount = IntStream.range(0, flags.length)
                .filter(i -> flags[i])
                .count();
        System.out.println("trueCount=" + trueCount);

        Stream<int[]> singleton = Stream.of(numbers);
        System.out.println("streamOfPrimitiveArrayCount=" +
                singleton.count());

        String[] possibleNulls = {"A", null, "B"};
        System.out.println("nonNull=" +
                Arrays.stream(possibleNulls)
                        .filter(Objects::nonNull)
                        .toList());

        System.out.println("emptyAveragePresent=" +
                Arrays.stream(new int[0]).average().isPresent());

        List<String> parallelOrdered = Arrays.stream(words)
                .parallel()
                .map(String::toUpperCase)
                .toList();
        System.out.println("parallelOrdered=" + parallelOrdered);
    }
}
```

Biên dịch/chạy:

```bash
javac ArraysStreamDemo.java
java ArraysStreamDemo
```

**Stdout xác định:**

```text
objects=[java, stream, api]
objectSlice=[stream, api]
lengths=[4, 6, 3]
intSum=10
intSlice=[1, 3]
intAverage=2.5
boxed=[4, 1, 3, 2]
labels=[N4, N1, N3, N2]
longSum=6000000000
doubleSum=6.0
doubleAverage=2.0
wrapperSum=12
rows=[2, 1, 2]
flattened=[1, 2, 3, 4, 5]
charUnits=[65, 66]
trueCount=2
streamOfPrimitiveArrayCount=1
nonNull=[A, B]
emptyAveragePresent=false
parallelOrdered=[JAVA, STREAM, API]
```

### Kiểm tra kết quả từng nhóm

1. **`objects` và `objectSlice`**: object array tạo `Stream<String>`, full array có ba phần tử; range `[1,3)` lấy `stream` và `api`.
2. **`lengths`**: mapper `String::length` cho số ký tự 4, 6 và 3.
3. **`intSum`/`intSlice`/`intAverage`**: `int[] {4,1,3,2}` có tổng 10, đoạn `[1,3)` là `[1,3]`, trung bình là 2.5.
4. **`boxed` và `labels`**: `boxed()` tạo `Integer` wrapper values, còn `mapToObj` tạo `String` theo mẫu `N...`.
5. **`longSum`**: tổng 1 + 2 + 3 tỷ là 6 tỷ, được tính trong `LongStream` với kiểu `long`.
6. **`doubleSum`/`doubleAverage`**: các giá trị 1.5, 2.0, 2.5 có tổng 6.0 và trung bình 2.0.
7. **`wrapperSum`**: `Integer[]` tạo object Stream; `mapToInt` unbox để cộng, tổng bằng 12.
8. **`rows`**: mảng hai chiều gồm ba hàng có độ dài 2, 1, 2.
9. **`flattened`**: `flatMapToInt(Arrays::stream)` gộp các giá trị từng hàng thành `[1,2,3,4,5]`.
10. **`charUnits`**: `'A'` và `'B'` có UTF-16 code units 65 và 66.
11. **`trueCount`**: lọc các chỉ số có giá trị boolean true, kết quả bằng 2.
12. **`Stream.of(numbers)`**: stream có một phần tử là **toàn bộ mảng int[]**, nên `count()` bằng 1.
13. **`nonNull`**: `filter(Objects::nonNull)` bỏ một phần tử null.
14. **`emptyAveragePresent`**: mảng `int[]` rỗng không có giá trị trung bình.
15. **`parallelOrdered`**: `parallel()` cho phép tính toán song song, nhưng `toList()` giữ encounter order của object array, cho `[JAVA, STREAM, API]`.

Chương trình không in các thao tác `parallel().forEach(...)` có thứ tự bất định và không dùng side effect trong mapper. Vì thế đầu ra trên không phụ thuộc cách JVM lập lịch các task song song.

## 19. Thiết kế pipeline theo bài toán thực tế

### Chỉ lấy phần tử vượt ngưỡng

```java
int[] measurements = {7, 12, 4, 18, 9};

int[] above10 = Arrays.stream(measurements)
        .filter(x -> x > 10)
        .toArray();

System.out.println(Arrays.toString(above10)); // [12, 18]
```

Đoạn minh họa. `IntStream.filter` dùng `IntPredicate`, vẫn giữ primitive values và encounter order.

### Đếm số bản ghi object thỏa điều kiện

```java
String[] keys = {"A-1", "B-2", "A-3"};

long aCount = Arrays.stream(keys)
        .filter(key -> key.startsWith("A-"))
        .count();

System.out.println(aCount); // 2
```

Đây là minh họa. Nếu mảng có null cần kiểm tra trước khi gọi `startsWith`.

### Chọn thống kê thay vì tạo collection không cần

```java
int[] costs = {5, 8, 3};

int largest = Arrays.stream(costs)
        .max()
        .orElseThrow();

System.out.println(largest); // 8
```

Không cần `boxed().sorted().toList()` chỉ để tìm max của một mảng số. Terminal `max` diễn đạt đúng mục đích và không phải materialize danh sách trung gian.

### Xử lý một đoạn có index rõ

```java
double[] temperatures = {16.0, 18.0, 20.0, 22.0};

double windowAverage = Arrays.stream(temperatures, 1, 3)
        .average()
        .orElseThrow();

System.out.println(windowAverage); // 19.0
```

Đây là minh họa. Mốc `1` và `3` được hiểu là chỉ số trong array, không phải giá trị nhiệt độ hoặc số lượng phần tử. Khi index được tính từ input bên ngoài, validate `0 <= start <= end <= array.length` trước khi gọi để tạo lỗi ứng dụng có ngữ cảnh rõ.

## 20. Những lỗi phổ biến

| Vấn đề | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Gán `Arrays.stream(int[])` vào `Stream<Integer>` | Overload trả `IntStream` | Giữ `IntStream` hoặc gọi `boxed()` |
| `Stream.of(intArray).count()` trả 1 | Cả mảng là một reference element | Dùng `Arrays.stream(intArray)` |
| `Arrays.asList(intArray)` thành list một phần tử | Varargs không chuyển từng int thành Integer | Dùng `Arrays.stream(intArray).boxed().toList()` |
| `Arrays.stream(char[])` không biên dịch | Không có overload cho `char[]` | `IntStream.range`/`String.chars()` tùy dữ liệu |
| `Arrays.stream(float[])` không biên dịch | Không có `FloatStream` | `IntStream.range(...).mapToDouble(...)` nếu cần |
| Chuyển `int[]` sang `long[]` bằng cast | Primitive array types khác nhau | `Arrays.stream(ints).asLongStream().toArray()` |
| Đọc `Arrays.stream(int[][])` như stream từng int | Generic overload trả `Stream<int[]>` | `flatMapToInt(Arrays::stream)` |
| Range lấy nhầm phần tử cuối | `endExclusive` không được tính vào | Dùng biên `[start,end)` |
| Dùng `average().getAsDouble()` trên mảng rỗng | `OptionalDouble.empty()` | Kiểm tra có giá trị hoặc fallback rõ |
| `NullPointerException` với `Integer[]` | Unboxing null | Validate/filter trước `mapToInt` |
| `NullPointerException` với `String[]` | Mapper gọi method trên null | Định nghĩa chính sách null |
| Sửa array trong lúc stream đang duyệt | Vi phạm non-interference | Hoàn thành mutation trước hoặc copy |
| Cộng int lớn rồi cast sang long | Int sum đã overflow | Nâng lên `asLongStream` trước khi sum |
| So thứ tự output của parallel `forEach` | Không có ordering guarantee | Dùng `toArray`/`toList` hoặc `forEachOrdered` nếu cần |
| Dùng stream một lần rồi terminal lần hai | Stream consumable một lần | Tạo stream mới từ mảng |
| Xem `toList()` là mutable | `Stream.toList()` trả unmodifiable list | Chọn collection mutable tường minh |

### Lỗi nguy hiểm: kiểm thử dựa trên thứ tự không có guarantee

`Arrays.stream(array)` có encounter order theo indices, và nhiều terminal operations giữ order. Nhưng nếu bạn gọi `unordered()` hoặc dùng `parallel().forEach(...)`, không được coi console output là một sequence xác định chỉ vì một vài lần chạy thấy giống nhau.

**Kiểm thử đúng:** so mảng/list kết quả khi operation cam kết giữ encounter order; nếu order không quan trọng, so sorted lists/multisets hoặc các aggregation theo contract, không dựa vào thread scheduling.

## 21. Chọn giải pháp: primitive Stream hay vòng lặp?

Bất kỳ dòng nào cũng không nên ép dùng Stream nếu vòng lặp rõ ràng hơn. Ví dụ với dữ liệu byte:

```java
byte[] bytes = {1, 2, 3};
long sum = 0;

for (byte b : bytes) {
    sum += b;
}

System.out.println(sum); // 6
```

Đây là minh họa. Cách này hợp lệ, dễ hiểu và không cần tạo `IntStream.range` chỉ để duyệt một số phần tử.

**Chọn Stream khi** bài toán là một pipeline biến đổi/lọc/gộp dữ liệu dễ diễn đạt bằng functional operations, hoặc API phía sau nhận Stream.

**Chọn vòng lặp khi** cần thao tác với index và mutable state cục bộ có logic phức tạp, cần xử lý break/continue có kiểm soát, hoặc benchmark cho thấy stream overhead không phù hợp.

Việc dùng mảng primitive không khiến functional style tự động tốt hơn. Mục tiêu là **mã đúng contract, dễ đọc, dễ kiểm thử và phù hợp workload**.

## 22. Checklist đọc một lời gọi Arrays.stream

Khi thấy một dòng `Arrays.stream(input)`, hãy tự hỏi:

1. **Kiểu tĩnh của input là gì?** `T[]`, `int[]`, `long[]`, `double[]`, hay mảng hai chiều?
2. **Overload nào được chọn?** Lấy kiểu trả về chính xác thay vì đoán `Stream<T>` trong mọi trường hợp.
3. **Pipeline cần primitive hay wrapper?** Nếu chỉ sum/min/max, giữ primitive; nếu cần `List<Integer>` thì dùng `boxed`.
4. **Có cần đoạn mảng?** Dùng overload `[startInclusive,endExclusive)` với biên hợp lệ.
5. **Có null không?** Null array và null element là hai rủi ro khác nhau.
6. **Có mảng nhiều chiều không?** Có muốn rows hay tất cả inner values?
7. **Có phép chuyển kiểu số không?** Nâng lên `long`/`double` đúng lúc, tránh tràn hoặc độ chính xác không mong muốn.
8. **Source có bị sửa trong lúc traversal?** Nếu có, cần loại bỏ interference.
9. **Terminal output là gì?** `int[]`, `List<String>`, `OptionalDouble` hay scalar?
10. **Có parallel và side effects?** Không chia sẻ mutable state không đồng bộ; không suy luận thứ tự gọi callback.
11. **API có thể xử lý mảng rỗng?** Kiểm tra Optional cho min/max/average.
12. **Bạn có thực sự cần Stream?** Đôi khi vòng lặp hoặc `Arrays.copyOfRange` dễ đọc hơn.

## 23. Bài tập tự luyện có đáp án

**Bài 1 — Loại Stream.** `Arrays.stream(new int[]{1,2,3})`, `Arrays.stream(new Integer[]{1,2,3})` và `Arrays.stream(new double[]{1.0,2.0})` trả những kiểu gì? **Đáp án:** `IntStream`, `Stream<Integer>`, `DoubleStream`.

**Bài 2 — Stream.of primitive.** Vì sao `Stream.of(new long[]{1,2}).count()` có thể bằng 1? **Đáp án:** phần tử duy nhất là object `long[]`; muốn các giá trị `long` riêng, dùng `Arrays.stream(longArray)` hoặc `LongStream.of(...)`.

**Bài 3 — Slice.** Mảng `{10,20,30,40,50}`, `Arrays.stream(a,2,5).toArray()` trả gì? **Đáp án:** `[30,40,50]`, lấy index 2,3,4.

**Bài 4 — Biên rỗng.** `Arrays.stream(a,3,3).count()` bằng bao nhiêu với một mảng có ít nhất 3 phần tử? **Đáp án:** `0`, vì đoạn nửa mở rỗng.

**Bài 5 — Boxing.** Viết pipeline chuyển `int[] {5,6,7}` thành `List<Integer>`. **Đáp án:** `Arrays.stream(a).boxed().toList()`.

**Bài 6 — Double precision.** `Arrays.stream(new double[]{0.1,0.2}).sum()` có nên dùng để đảm bảo số thập phân tiền tệ chính xác tuyệt đối không? **Đáp án:** không; IEEE 754 và phép tính dấu phẩy động không cung cấp thập phân chính xác như `BigDecimal`.

**Bài 7 — Mảng hai chiều.** `Arrays.stream(new int[][]{{1,2},{3}}).count()` trả gì? **Đáp án:** `2` (số hàng), không phải số integer bên trong là 3.

**Bài 8 — Flatten.** Làm thế nào lấy từng số `int` từ `int[][]`? **Đáp án:** `Arrays.stream(matrix).flatMapToInt(Arrays::stream)`.

**Bài 9 — char[].** Vì sao không có `Arrays.stream(char[])`, và vì sao code points khác char values? **Đáp án:** JDK chỉ có ba primitive stream specializations chuẩn; `char` chứa UTF-16 code unit, code point có thể gồm nhiều code units.

**Bài 10 — byte[].** Viết tổng `byte[]` với `IntStream.range`. **Đáp án:** `IntStream.range(0, bytes.length).map(i -> bytes[i]).sum()`. Khi dùng `byte` làm số nhị phân không dấu, cần xác định rõ quy tắc unsigned conversion như `Byte.toUnsignedInt` nếu phù hợp domain.

**Bài 11 — Mảng rỗng.** `Arrays.stream(new long[0]).average()` có giá trị hay không? **Đáp án:** `OptionalDouble.empty()`.

**Bài 12 — int overflow.** `int[]{1_500_000_000,1_500_000_000}` nên tính tổng thế nào? **Đáp án:** `Arrays.stream(a).asLongStream().sum()` để nâng trước phép cộng.

**Bài 13 — Tạo String[] sau map.** Viết `Arrays.stream(words).map(String::toUpperCase).toArray(String[]::new)`. Tại sao cần generator? **Đáp án:** object `Stream.toArray()` không đối số trả `Object[]`, còn generator yêu cầu mảng `String[]`.

**Bài 14 — Parallel.** `Arrays.stream(a).parallel().map(...).toArray()` có nhất thiết sắp xếp phần tử theo thứ tự hoàn tất của các task không? **Đáp án:** không; với ordered array source, terminal `toArray` bảo toàn encounter order dù map có thể chạy đồng thời.

**Bài 15 — Null array.** Có khác nhau giữa mảng `null` và mảng rỗng không? **Đáp án:** có. Typed null array không phải nguồn hợp lệ cho `Arrays.stream`, còn mảng rỗng tạo stream có 0 phần tử. Tránh lời gọi literal `Arrays.stream(null)` không rõ overload.

## 24. Kết luận

- **Object/reference array `T[]` → `Stream<T>`**; **`int[]` → `IntStream`**, **`long[]` → `LongStream`**, **`double[]` → `DoubleStream`**.
- Các overload dạng `(array,startInclusive,endExclusive)` dùng **khoảng chỉ số nửa mở** và kiểm tra biên mảng.
- Primitive streams hỗ trợ `sum`, `min`, `max`, `average`, `summaryStatistics` và `toArray` đúng loại mảng, thường không cần boxing.
- `boxed()` biến primitive values thành wrappers khi API đích yêu cầu; `mapToObj` cho phép chuyển sang loại object khác.
- `Stream.of(primitiveArray)` có một phần tử là **cả mảng**, không giống `Arrays.stream(primitiveArray)`.
- Mảng nhiều chiều stream theo **hàng** trước, muốn flatten thì dùng `flatMap`/`flatMapToInt`.
- Những loại `byte[]`, `short[]`, `char[]`, `float[]`, `boolean[]` không có overload trực tiếp; có thể dùng `IntStream.range` hoặc vòng lặp.
- Không thay đổi array trong lúc duyệt, không giả định null là empty và không xây logic phụ thuộc execution order của parallel callbacks.
- Chọn kiểu stream và terminal operation theo **kiểu dữ liệu, độ chính xác và contract nghiệp vụ**, không chỉ để viết code ngắn.

### Tài liệu chính thức

- [Java SE 25 — Arrays.stream overloads](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Arrays.html)
- [Java SE 25 — IntStream](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/IntStream.html)
- [Java SE 25 — LongStream](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/LongStream.html)
- [Java SE 25 — DoubleStream](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/DoubleStream.html)
- [Java SE 25 — Stream](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/Stream.html)
- [Java SE 25 — Streams package summary (non-interference, ordering)](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/package-summary.html)
