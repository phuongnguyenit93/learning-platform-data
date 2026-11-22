# Chi phí boxing trong vòng lặp và cấu trúc dữ liệu Java

## 1. Boxing và unboxing là gì?

Trong Java, `int`, `long`, `double` và những kiểu primitive khác giữ giá trị theo các kiểu dữ liệu cơ bản của ngôn ngữ. Những lớp như `Integer`, `Long` và `Double` là **wrapper**: đối tượng tham chiếu biểu diễn giá trị primitive tương ứng.

**Boxing** là chuyển từ primitive sang wrapper. **Unboxing** là lấy giá trị primitive từ wrapper. Java có thể thực hiện chúng tự động khi kiểu/ngữ cảnh cho phép:

~~~java
int primitive = 42;
Integer boxed = primitive;  // autoboxing: int -> Integer
int again = boxed;          // unboxing: Integer -> int
~~~

Đây là đoạn minh họa, chưa phải chương trình độc lập. Về mặt ngữ nghĩa, có thể hình dung:

~~~java
Integer boxed = Integer.valueOf(primitive);
int again = boxed.intValue();
~~~

Điểm chính: **box/unbox là các chuyển đổi kiểu được trình biên dịch diễn giải**, không phải “miễn phí”. Chúng có thể kèm gọi phương thức, tham chiếu đối tượng, xử lý `null` và trong một số điều kiện **có cấp phát đối tượng**.

Khi xuất hiện một hai lần trong mã bình thường, chi phí thường không đáng kể. Nhưng trong **vòng lặp chạy hàng triệu lần**, **collection chứa hàng triệu phần tử** hoặc **đường xử lý hiệu năng nhạy cảm**, số lượng chuyển đổi và đối tượng có thể tác động lên:

- Bộ nhớ dùng để lưu dữ liệu và metadata đối tượng.
- Số lần cấp phát, thu gom rác (*garbage collection* – GC) và áp lực lên heap.
- Tính cục bộ bộ nhớ (*cache locality*), số lần theo tham chiếu và tốc độ truy cập.
- CPU của những phép kiểm tra `null`, chuyển kiểu và mã tạo wrapper nếu chúng không được tối ưu.
- Độ trễ đuôi (*tail latency*) khi GC hoặc cache miss xuất hiện.

Bài này chỉ rõ **nơi boxing ẩn xảy ra**, phân biệt **chi phí có thể phát sinh** với **chi phí chắc chắn xảy ra**, và hướng chọn cấu trúc dữ liệu theo yêu cầu.

## 2. Primitive và wrapper: giống giá trị, khác cách lưu trữ

| Primitive | Wrapper | Ví dụ autoboxing | Có thể chứa `null`? |
|---|---|---|---|
| `byte` | `Byte` | `Byte b = (byte) 5;` | Có |
| `short` | `Short` | `Short s = (short) 5;` | Có |
| `int` | `Integer` | `Integer i = 5;` | Có |
| `long` | `Long` | `Long l = 5L;` | Có |
| `float` | `Float` | `Float f = 1.5f;` | Có |
| `double` | `Double` | `Double d = 1.5;` | Có |
| `char` | `Character` | `Character c = 'A';` | Có |
| `boolean` | `Boolean` | `Boolean flag = true;` | Có |

Primitive không mang giá trị `null`. Wrapper là reference type, nên biến wrapper có thể là `null`; **unboxing `null` ném `NullPointerException`**.

Các wrapper không hoán đổi vai trò với nhau tùy ý. Ví dụ `Integer` là wrapper của `int`, không phải primitive `int`. Dù `Integer` là một `Number`, việc cần đối tượng và việc thực hiện số học là hai cơ chế khác nhau.

### Boxing không đồng nghĩa tạo đối tượng mới ở mọi lần

`Integer.valueOf(int)` sử dụng **caching** đối với ít nhất miền `-128` đến `127`. Cùng giá trị trong miền này có thể được biểu diễn bằng cùng đối tượng wrapper. Cấu hình/triển khai có thể cache thêm giá trị ngoài miền bắt buộc.

Hơn nữa, JVM/JIT có thể tối ưu những đối tượng tạm **không thoát** khỏi phạm vi phân tích (*escape analysis*, scalar replacement) và loại bỏ một số cấp phát vật lý. Vì vậy, phát biểu **“mỗi lần autoboxing chắc chắn cấp phát một đối tượng” là sai**.

Tuy nhiên, cũng không thể kết luận **“JIT sẽ xóa hết mọi boxing”**: khi cần giữ đối tượng `Integer` trong collection hoặc truyền nó đến nơi không thể loại bỏ tham chiếu, có thể phải lưu/cấp phát đối tượng thật. Tối ưu phụ thuộc mã, JVM, dữ liệu và quá trình warm-up.

## 3. Boxing ẩn trong vòng lặp

### 3.1. Biến tích lũy dạng primitive

~~~java
int sum = 0;
for (int i = 0; i < 5; i++) {
    sum += i;
}
~~~

`sum` và `i` đều có kiểu `int`. Vòng lặp thao tác trên primitive; không có boxing do kiểu của các biến này.

### 3.2. Biến tích lũy dạng wrapper

~~~java
Integer sum = 0;
for (int i = 0; i < 5; i++) {
    sum += i;
}
~~~

Hai đoạn là **mã minh họa**, không phải class độc lập. Về ngữ nghĩa, `sum += i` cần:

1. Lấy giá trị primitive từ `sum` (*unbox*).
2. Cộng với `i` kiểu `int`.
3. Chuyển kết quả `int` trở lại `Integer` (*box*) để gán cho biến `sum`.

Có thể hình dung gần tương đương:

~~~java
sum = Integer.valueOf(sum.intValue() + i);
~~~

**Cảnh báo:** đoạn diễn giải này không nhằm mô tả chính xác mọi bước CPU của mã máy do JIT sinh ra. Nó mô tả **nghĩa ngôn ngữ** và nơi việc box/unbox xuất hiện. JVM có thể tối ưu phần nào, nhưng viết tích lũy bằng `Integer` không đem lại lợi ích tự động so với `int` khi không cần đối tượng.

Nếu `sum == null` ở đầu phép cộng, chương trình sẽ ném `NullPointerException` tại bước unbox.

### Ví dụ Java 17+ chạy độc lập

Tạo tệp `BoxingLoopDemo.java`:

~~~java
public class BoxingLoopDemo {
    static int primitiveSum(int limit) {
        int sum = 0;
        for (int i = 0; i < limit; i++) {
            sum += i;
        }
        return sum;
    }

    static int boxedSum(int limit) {
        Integer sum = 0;
        for (int i = 0; i < limit; i++) {
            sum += i; // unboxing, phép cộng int, autoboxing
        }
        return sum; // unboxing khi trả về int
    }

    public static void main(String[] args) {
        System.out.println("primitiveSum=" + primitiveSum(5));
        System.out.println("boxedSum=" + boxedSum(5));

        int primitive = 42;
        Integer boxed = primitive;
        int recovered = boxed;
        System.out.println("recovered=" + recovered);

        Integer missing = null;
        try {
            int value = missing;
            System.out.println(value);
        } catch (NullPointerException ex) {
            System.out.println("nullUnboxing=NPE");
        }
    }
}
~~~

Biên dịch và chạy bằng JDK 17 hoặc mới hơn:

~~~bash
javac BoxingLoopDemo.java
java BoxingLoopDemo
~~~

Đầu ra:

~~~text
primitiveSum=10
boxedSum=10
recovered=42
nullUnboxing=NPE
~~~

Hai vòng lặp tạo cùng **giá trị số**. Khác nhau nằm ở các chuyển đổi kiểu và khả năng tạo đối tượng mà chương trình yêu cầu; **đầu ra không phải thước đo hiệu năng**. Không nên đưa ra số mili-giây cụ thể nếu chưa đo trên môi trường thật.

## 4. `int[]` và `List<Integer>` khác nhau ở đâu?

Java có hai lựa chọn phổ biến để lưu nhiều số nguyên:

- **`int[]`**: một mảng primitive chứa các giá trị `int` trực tiếp.
- **`List<Integer>`**: một collection chứa các **tham chiếu `Integer`**; với `ArrayList<Integer>`, cấu trúc thường dùng một mảng tham chiếu bên trong và những đối tượng wrapper được tham chiếu.

So sánh:

| Khía cạnh | `int[]` | `ArrayList<Integer>` |
|---|---|---|
| Phần tử | Giá trị `int` | Tham chiếu tới `Integer` |
| Có boxing khi thêm số primitive? | Không | Có thể có, ví dụ `add(42)` |
| Truy cập trả về | `int` | `Integer`; dùng số học thường phải unbox |
| Hỗ trợ `null` như phần tử? | Không | Có |
| Kích thước | Cố định sau khi tạo | Tăng/giảm động |
| Tích hợp API `List`/generics | Không trực tiếp | Có |
| Chi phí bộ nhớ mỗi phần tử | Giá trị primitive liên tiếp, ít gián tiếp | Tham chiếu và có thể thêm đối tượng wrapper/overhead |
| Truy cập ngẫu nhiên | `O(1)` | `O(1)` đối với `ArrayList` |
| Tính cục bộ bộ nhớ | Thường tốt với duyệt tuần tự | Thêm bước theo tham chiếu tới wrapper |

**Đừng suy ra một con số byte tuyệt đối cho mọi JVM:** kích thước header đối tượng, alignment, *compressed ordinary object pointers*, heap và JDK ảnh hưởng footprint. Ví dụ, `int` có giá trị 32 bit, nhưng một `Integer` object trong heap không chỉ có 4 byte vì còn metadata/header và căn chỉnh; `ArrayList` cũng có vùng tham chiếu, capacity dư, và đối tượng danh sách.

Đối với một triệu số `int`, mảng primitive thường tiết kiệm bộ nhớ hơn đáng kể so với một triệu `Integer` không được cache nằm trong `ArrayList`. Nhưng **đo lường thực tế** vẫn cần thiết nếu phải công bố phần trăm tiết kiệm hoặc thời gian chạy.

### Chi phí boxing khi thêm và unboxing khi đọc

~~~java
List<Integer> values = new ArrayList<>();
for (int i = 0; i < 1000; i++) {
    values.add(i);  // int -> Integer
}

long sum = 0;
for (int value : values) { // mỗi Integer được unbox thành int
    sum += value;
}
~~~

Đây là đoạn minh họa; cần `import java.util.List;` và `import java.util.ArrayList;` khi đặt trong chương trình độc lập.

Vòng `for-each` viết `int value` giúp mã ngắn, nhưng không có nghĩa collection đã chứa primitive. Khi duyệt `List<Integer>`, từng phần tử phải được chuyển từ `Integer` sang `int`; phần tử `null` sẽ ném NPE ở thời điểm đó.

## 5. Chương trình Java 17+: so sánh cấu trúc dữ liệu bằng kết quả xác định

Tạo tệp `PrimitiveVsBoxedCollectionsDemo.java`:

~~~java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

public class PrimitiveVsBoxedCollectionsDemo {
    public static void main(String[] args) {
        int[] array = {10, 20, 30};
        List<Integer> list = new ArrayList<>();

        for (int value : array) {
            list.add(value); // boxing từng phần tử
        }

        int arraySum = 0;
        for (int value : array) {
            arraySum += value;
        }

        int listSum = 0;
        for (int value : list) { // unboxing
            listSum += value;
        }

        System.out.println("arraySum=" + arraySum);
        System.out.println("listSum=" + listSum);
        System.out.println("size=" + list.size());

        list.set(0, 15);
        System.out.println("arrayFirst=" + array[0]);
        System.out.println("listFirst=" + list.get(0));

        System.out.println("arrayStreamSum="
                + Arrays.stream(array).sum());
        System.out.println("listStreamSum="
                + list.stream().mapToInt(Integer::intValue).sum());
    }
}
~~~

~~~bash
javac PrimitiveVsBoxedCollectionsDemo.java
java PrimitiveVsBoxedCollectionsDemo
~~~

Đầu ra:

~~~text
arraySum=60
listSum=60
size=3
arrayFirst=10
listFirst=15
arrayStreamSum=60
listStreamSum=65
~~~

Khi chỉnh `list.set(0, 15)`, phần tử đầu mảng vẫn là 10 vì **mảng primitive và danh sách wrapper là hai cấu trúc riêng**. Dòng `arrayStreamSum` đọc trực tiếp `int[]`, còn `listStreamSum` dùng `Integer::intValue` để biến `Stream<Integer>` thành `IntStream`.

Ví dụ này so sánh **ngữ nghĩa và vị trí chuyển đổi kiểu**, **không phải benchmark**.

## 6. Mảng primitive, collection chuẩn và collection primitive-specialized

Khi cần lưu trữ khối lượng lớn dữ liệu số, có thể cân nhắc:

1. **`int[]`, `long[]`, `double[]`**: phù hợp với kích thước xác định hoặc có thể quản lý việc mở rộng mảng. Không boxing từng phần tử và có locality tốt khi duyệt tuần tự.
2. **`ArrayList<Integer>`, `HashMap<Integer, Long>`**: phù hợp khi cần API collection chuẩn, generic, kích thước linh hoạt, tích hợp thư viện, hoặc có thể cần `null`. Đổi lại, có khả năng overhead tham chiếu và wrapper.
3. **`IntStream`, `LongStream`, `DoubleStream`**: đường xử lý stream chuyên biệt cho primitive; giúp tránh một số boxing trong pipeline.
4. **Cấu trúc dữ liệu chuyên biệt cho primitive từ thư viện ngoài**: ví dụ danh sách/map có khóa và giá trị primitive. Có thể giảm overhead trong một số workload, nhưng thêm dependency, API và yêu cầu kiểm tra benchmark/độ ổn định.
5. **Thiết kế theo miền dữ liệu**: `BitSet` phù hợp với tập bit/boolean dày đặc; mảng đa chiều hoặc buffer cũng có thể phù hợp với xử lý số lớn. Chọn theo cách truy cập, không chỉ theo mong muốn “tránh boxing”.

Không nên tự động thay mọi `List<Integer>` thành `int[]`. API dạng `List` có lợi thế về thao tác thêm/xóa, cộng tác giữa nhiều thư viện, cấu trúc trừu tượng và mã dễ bảo trì. **Tối ưu dựa trên profile** hiệu quả hơn tối ưu dựa trên một giả định rằng wrapper luôn quá chậm.

### `HashMap<Integer, Integer>` trong vòng lặp nóng

Ví dụ:

~~~java
Map<Integer, Integer> frequencies = new HashMap<>();
for (int number : input) {
    frequencies.merge(number, 1, Integer::sum);
}
~~~

Đây là **đoạn minh họa**, giả sử đã khai báo `int[] input` và import `Map`, `HashMap`. Mã sử dụng `Integer` làm khóa và giá trị; primitive `number` được boxing khi làm key, giá trị đếm là wrapper, và callback `Integer::sum` xử lý các giá trị sau khi unbox thích hợp. Với dữ liệu nhiều khóa và cập nhật liên tục, chi phí hash table và đối tượng có thể đáng kể.

Nhưng thay thành primitive map chỉ có ích nếu workload thực sự bị ảnh hưởng bởi **GC/bộ nhớ/CPU** từ cấu trúc hiện tại và thư viện mới đáp ứng đúng quy tắc khóa, concurrency và hành vi của ứng dụng.

## 7. Stream: primitive stream và `Stream<Integer>`

Java Stream API có các specialization:

| Dạng | Phần tử logic | Phép toán thường dùng |
|---|---|---|
| `Stream<Integer>` | `Integer` (wrapper) | `map`, `filter`, `collect` |
| `IntStream` | `int` | `map`, `filter`, `sum`, `average` |
| `LongStream` | `long` | `map`, `sum`, `summaryStatistics` |
| `DoubleStream` | `double` | `map`, `sum`, `average` |

Ví dụ:

~~~java
int sumPrimitive = java.util.stream.IntStream.rangeClosed(1, 5).sum();
int sumBoxed = java.util.stream.Stream.of(1, 2, 3, 4, 5)
        .mapToInt(Integer::intValue)
        .sum();
~~~

Đây là đoạn minh họa. `Stream.of(1, 2, 3, 4, 5)` tạo một stream các đối tượng `Integer` vì generic type của `Stream` là reference type; còn `IntStream.rangeClosed` làm việc trực tiếp với `int`.

### Những điểm boxing thường lộ ra trong pipeline

- `IntStream.boxed()` biến mỗi phần tử `int` thành `Integer` để trả `Stream<Integer>`.
- `Stream<Integer>.mapToInt(Integer::intValue)` unbox các phần tử thành `int`.
- `Stream<Integer>.reduce(0, Integer::sum)` có thể cần xử lý các giá trị box/unbox ở mỗi bước giảm; không mặc nhiên nhanh bằng `IntStream.sum()`.
- `IntStream.sum()` trả `int`; nếu tổng toán học vượt miền `int` thì **vẫn có thể tràn số**. Tránh boxing **không đồng nghĩa tránh overflow**.
- Nếu cần tổng `long` từ các số `int`, hãy chuyển sang `LongStream` trước khi cộng: `intStream.asLongStream().sum()`.

### Ví dụ Java 17+ chạy độc lập về stream

Tạo tệp `PrimitiveStreamsDemo.java`:

~~~java
import java.util.List;
import java.util.stream.IntStream;

public class PrimitiveStreamsDemo {
    public static void main(String[] args) {
        int sum = IntStream.rangeClosed(1, 5).sum();

        List<Integer> boxed = IntStream.rangeClosed(1, 3)
                .boxed()
                .toList();

        int unboxedSum = boxed.stream()
                .mapToInt(Integer::intValue)
                .sum();

        int overflowed = IntStream.of(Integer.MAX_VALUE, 1).sum();
        long widened = IntStream.of(Integer.MAX_VALUE, 1)
                .asLongStream()
                .sum();

        System.out.println("primitiveSum=" + sum);
        System.out.println("boxedList=" + boxed);
        System.out.println("unboxedSum=" + unboxedSum);
        System.out.println("intOverflow=" + overflowed);
        System.out.println("longSum=" + widened);
    }
}
~~~

~~~bash
javac PrimitiveStreamsDemo.java
java PrimitiveStreamsDemo
~~~

Đầu ra:

~~~text
primitiveSum=15
boxedList=[1, 2, 3]
unboxedSum=6
intOverflow=-2147483648
longSum=2147483648
~~~

`Stream.toList()` (Java 16+) trả danh sách không thể sửa bằng các thao tác cập nhật thông thường. Trong ví dụ này, nó lưu `Integer` do trước đó đã gọi `boxed()`. Dòng `intOverflow` là lời nhắc rằng **chọn primitive stream chỉ giải quyết vấn đề boxing**, còn giới hạn miền số vẫn phải tự kiểm soát.

## 8. Autoboxing ở ranh giới phương thức và API generic

Một API nhận `Integer` hoặc `Number` có thể gây boxing ở nơi gọi, mặc dù biến của người gọi là `int`:

~~~java
static void accept(Number value) {
    System.out.println(value.intValue());
}

int count = 10;
accept(count); // int -> Integer -> Number
~~~

Đây là các đoạn minh họa cần đặt trong class. Từ góc độ kiểu tĩnh, `accept(count)` cần boxing một `int` thành `Integer` rồi chuyển tham chiếu tới `Number`.

Ngược lại:

~~~java
static int twice(int value) {
    return value * 2;
}

Integer number = Integer.valueOf(10);
int doubled = twice(number); // unbox Integer -> int
~~~

Một codebase có hàng nghìn dòng có thể chứa nhiều lần box/unbox ở **ranh giới method, generics và collection**, ngay cả khi không có từ khóa `new` hay lời gọi `Integer.valueOf` xuất hiện trực tiếp.

### Overload và unboxing

Nếu có các overload khác nhau:

~~~java
static void use(int value) { /* ... */ }
static void use(Integer value) { /* ... */ }
~~~

thì lựa chọn overload phụ thuộc vào kiểu biểu thức và các pha xác định overload của Java. Không nên dùng boxing như một “thao tác vô hình” để giả định mọi lời gọi đều chọn overload có cùng chi phí. Khi hiệu năng thật sự quan trọng, chọn API primitive rõ ràng có thể giúp tránh nhu cầu chuyển qua wrapper.

## 9. Cạm bẫy `null`, đồng nhất tham chiếu và kiểm tra bằng `==`

### `null` và unboxing

~~~java
Integer count = null;
// int value = count;     // Ném NullPointerException khi chạy
// int next = count + 1;  // Cũng ném NPE do cần unbox
~~~

Đây là mã minh họa, các dòng nguy hiểm đã được comment. Một `List<Integer>` có thể chứa `null`; phép `for (int x : list)` sẽ NPE khi gặp phần tử đó. Primitive array không có trạng thái `null` cho từng phần tử; mọi vị trí `int[]` có giá trị nguyên (mặc định 0 nếu chưa gán).

Nếu `null` có ý nghĩa như “chưa biết”, hãy quyết định chính sách xử lý rõ ràng, thay vì tự động đổi `null` thành 0 mà không kiểm tra yêu cầu.

### `==` với wrapper không có nghĩa so sánh giá trị tổng quát

Khi cả hai toán hạng đều là wrapper `Integer`, `a == b` so sánh **tham chiếu**, không phải luôn so sánh giá trị số. Một số đối tượng `Integer` được cache (ít nhất `-128..127`) nên `==` đôi khi cho `true`, gây nhầm lẫn; ngoài miền đó không nên dựa vào kết quả đồng nhất tham chiếu.

Ví dụ:

~~~java
Integer left = 1000;
Integer right = 1000;

boolean sameValue = left.equals(right);    // true
boolean samePrimitive = left.intValue() == right.intValue(); // true
// left == right so sánh tham chiếu, không dùng làm phép so sánh số.
~~~

Nếu một toán hạng kiểu `int` còn toán hạng kia kiểu `Integer`, phép `==` số học có thể thực hiện unboxing để so sánh primitive — và có thể NPE nếu wrapper `null`. Vì vậy, **kết quả `==` còn phụ thuộc kiểu tĩnh của cả hai toán hạng**.

Dùng `Objects.equals(a, b)` khi cần so sánh nội dung wrapper có thể `null`, hoặc unbox sau khi kiểm tra `null` nếu thật sự cần so sánh primitive.

### Ví dụ Java 17+ chạy độc lập

Tạo tệp `WrapperPitfallsDemo.java`:

~~~java
import java.util.HashMap;
import java.util.Map;
import java.util.Objects;

public class WrapperPitfallsDemo {
    public static void main(String[] args) {
        Integer a = 1000;
        Integer b = 1000;

        System.out.println("equals=" + a.equals(b));
        System.out.println("primitiveEquals="
                + (a.intValue() == b.intValue()));
        System.out.println("objectsEquals=" + Objects.equals(a, b));

        Map<Integer, String> names = new HashMap<>();
        names.put(a, "ok");
        System.out.println("mapLookup=" + names.get(b));

        Integer missing = null;
        try {
            int value = missing + 1;
            System.out.println(value);
        } catch (NullPointerException ex) {
            System.out.println("nullUnboxing=NPE");
        }

        int fallback = missing == null ? 0 : missing;
        System.out.println("fallback=" + fallback);
    }
}
~~~

~~~bash
javac WrapperPitfallsDemo.java
java WrapperPitfallsDemo
~~~

Đầu ra:

~~~text
equals=true
primitiveEquals=true
objectsEquals=true
mapLookup=ok
nullUnboxing=NPE
fallback=0
~~~

`HashMap` dùng `equals` và `hashCode` của key, không dùng phép `==` thuần túy như một so sánh nội dung số học. Bởi vậy, hai `Integer` có cùng giá trị có thể tra cứu cùng khóa mặc dù không cần là cùng đối tượng.

Ở biểu thức `missing == null ? 0 : missing`, khi `missing` bằng `null` thì nhánh `0` được chọn, nên nhánh cần unbox `missing` không chạy. Đây là một cách tạo giá trị mặc định rõ ràng, nhưng chỉ hợp lý nếu chính sách nghiệp vụ cho phép coi “thiếu” là 0.

## 10. Chi phí CPU, allocation và GC không giống nhau

Đừng gom mọi ảnh hưởng của boxing thành một “thời gian boxing” duy nhất:

1. **Chuyển kiểu theo nghĩa ngôn ngữ:** compiler phát sinh cách chuyển `int ↔ Integer`. Có thể gồm phương thức wrapper hoặc primitive extraction.
2. **Cấp phát vật lý:** một boxing cần đối tượng mới **khi không được cache hoặc loại bỏ nhờ tối ưu hóa**. Không có đảm bảo mỗi boxing tương ứng một allocation.
3. **Giữ đối tượng sống:** nếu collection giữ tham chiếu đến wrapper, các đối tượng ấy có thể tồn tại lâu và làm tăng lượng live objects phải xử lý.
4. **Chi phí bộ nhớ/CPU khi truy cập:** array primitive đọc giá trị trực tiếp; collection wrapper có thể phải đọc tham chiếu rồi đọc object, ảnh hưởng locality/cache.
5. **GC:** nhiều object cấp phát và sống lâu có thể tăng GC work. Ảnh hưởng cụ thể tùy collector, heap, tốc độ cấp phát và profile ứng dụng.

**Ví dụ vòng lặp accumulator `Integer`:** JIT đôi khi có thể tối ưu mạnh, nên benchmark đơn giản có thể cho kết quả gần primitive. **Ví dụ `ArrayList<Integer>` chứa hàng triệu giá trị khác nhau ngoài cache:** dữ liệu cần tồn tại dưới dạng object và tham chiếu, khó đạt footprint như `int[]`. Vì vậy, bài toán **lưu trữ dữ liệu** và bài toán **tính toán tạm thời** cần đánh giá riêng.

Chi phí phát sinh cũng phụ thuộc boxing của **`Long`/`Double`**, thường ảnh hưởng hơn khi dữ liệu lớn hoặc đường xử lý chứa nhiều bản sao.

## 11. Benchmark đúng: dùng workload thực và JMH khi cần microbenchmark

Không nên kết luận hiệu năng từ một đoạn ngắn như:

~~~java
long start = System.nanoTime();
// một vài phép cộng rất nhanh
long elapsed = System.nanoTime() - start;
~~~

Đây là đoạn minh họa **không phải phép benchmark đáng tin**. JVM có thể chưa warm-up, JIT có thể loại bỏ phép tính không dùng tới, GC ngẫu nhiên, và chi phí đo thời gian có thể lớn so với đoạn mã cần đo.

Với microbenchmark Java, có thể dùng **Java Microbenchmark Harness (JMH)** và thiết kế bài đo có:

- **Warm-up** đủ để JVM biên dịch/ổn định mã nóng.
- Nhiều **measurement iterations** và nhiều **forks** nhằm giảm ảnh hưởng trạng thái tiến trình.
- Input và kích thước dữ liệu phản ánh trường hợp thật: ít giá trị cache, nhiều giá trị ngoài cache, kích thước list/mảng, cách duyệt ngẫu nhiên hay tuần tự.
- Kết quả được **sử dụng thật hoặc truyền cho cơ chế tiêu thụ của JMH** để không bị dead-code elimination.
- Môi trường có kiểm soát tương đối về CPU, GC, heap và tải nền.
- Cả **throughput/latency** lẫn **allocation rate, GC, memory footprint** khi mục tiêu là giảm boxing.

JMH là thư viện/tool ngoài JDK chuẩn, nên muốn dùng phải bổ sung dependency và thiết lập dự án phù hợp; **không** thể giả định có sẵn chỉ vì đang dùng Java 17.

### Chọn baseline thực tế

Ví dụ cần đo tổng một triệu số:

1. Tổng theo `int[]`, vòng `for` primitive.
2. Tổng theo `ArrayList<Integer>`, vòng `for-each` unbox.
3. Tổng theo `Arrays.stream(intArray).asLongStream().sum()` khi cần miền kết quả rộng hơn.
4. Tổng theo `list.stream().mapToLong(Integer::longValue).sum()`.
5. Thao tác **tạo và lấp đầy dữ liệu** đo riêng với **thao tác duyệt**, bởi allocation thường tập trung ở giai đoạn thêm phần tử.

Nếu nghiệp vụ thực tế còn lọc/tra cứu/phân nhóm, hãy đo cả tác vụ đó thay vì chỉ so sánh phép cộng trần. Không thể suy từ **benchmark micro** rằng một ứng dụng backend nhất định sẽ nhanh hơn theo đúng cùng tỷ lệ.

## 12. Cách chọn cấu trúc dữ liệu theo trường hợp

| Bài toán | Lựa chọn khởi đầu | Khi nào cân nhắc thay đổi |
|---|---|---|
| Cộng, nhân, đếm trong vòng lặp tính toán | `int`/`long`/`double` primitive | Chỉ cần wrapper khi API bắt buộc |
| Dãy triệu số nguyên, đọc tuần tự, kích thước biết trước | `int[]` | Cần resize/generic API hoặc nhiều chức năng `List` |
| Danh sách số linh hoạt cho API ứng dụng | `ArrayList<Integer>` | Profile chứng minh bộ nhớ/GC/CPU từ boxing đáng kể |
| Tính toán stream từ `int[]` | `IntStream`/`LongStream` | Chuyển thành `Stream<Integer>` khi API/collector cần object |
| `Map` có khóa nguyên và cập nhật mật độ cao | `HashMap<Integer, ...>` trước cho đơn giản | Nếu bottleneck, cân nhắc thư viện primitive-specialized |
| Dữ liệu số có thể thiếu | Wrapper hoặc kiểu biểu diễn missing rõ ràng | Primitive cần sentinel/bitmap đi kèm, phải tránh nhập nhằng |
| Dữ liệu cần dùng cùng API generic | Wrapper, `List<Integer>` | Đánh giá copy/boxing ở ranh giới hot path |
| Bộ đếm chia sẻ đa luồng | `AtomicInteger` hoặc `LongAdder` tùy yêu cầu | Tránh biến mutable `int` không đồng bộ; boxing không giải quyết concurrency |

Không nên chọn `LongAdder` thay cho `long` trong mọi nơi: nó phục vụ bài toán cập nhật đồng thời và có ngữ nghĩa/chi phí riêng. **Tính an toàn luồng không suy ra từ việc dùng wrapper.** Các wrapper số phổ biến là immutable, nhưng collection chứa chúng vẫn có thể cần đồng bộ khi truy cập/chỉnh sửa từ nhiều luồng.

## 13. Những hiểu lầm phổ biến

| Nhận định | Cách hiểu đúng |
|---|---|
| “Mỗi `Integer` trong vòng lặp đều cấp phát mới.” | Có cache cho miền nhất định và tối ưu JIT; không được khẳng định luôn cấp phát. |
| “Vì JVM tối ưu, boxing hoàn toàn miễn phí.” | Không có bảo đảm; object sống trong collection, heap/GC và truy cập tham chiếu vẫn có thể tốn chi phí. |
| “`List<Integer>` lưu `int` trực tiếp như `int[]`.” | `List<Integer>` làm việc với reference `Integer`. |
| “`for (int value : list)` không boxing/unboxing vì biến là `int`.” | Nếu list chứa `Integer`, phải unbox từng phần tử khi đọc. |
| “`IntStream.boxed()` giúp tránh boxing.” | Ngược lại, nó biến primitive `int` thành wrapper `Integer`. |
| “`Stream<Integer>.sum()` luôn là primitive sum.” | `Stream<Integer>` không có `sum()` trực tiếp; cần `mapToInt` hoặc reducer. |
| “Dùng `IntStream` thì tổng không thể overflow.” | `IntStream.sum()` vẫn trả `int` và có thể overflow. |
| “`Integer a == Integer b` luôn so sánh giá trị.” | Với hai reference, `==` so sánh đồng nhất tham chiếu; dùng `equals` hoặc primitive có kiểm tra `null`. |
| “Unboxing `null` trả 0.” | Ném `NullPointerException`. |
| “`Integer.valueOf` luôn trả đối tượng mới.” | Có cache cho ít nhất `-128..127` và triển khai có thể cache thêm. |
| “`ArrayList<Integer>` luôn chậm hơn mọi `int[]` với mọi workload.” | Không thể kết luận nếu không xét thuật toán, locality, API, tối ưu JVM và benchmark thực tế. |
| “Boxing là vấn đề duy nhất cần tối ưu.” | Thuật toán, số lần tìm kiếm, object lifetime, IO, GC và cấu trúc dữ liệu có thể chi phối hơn nhiều. |

## 14. Checklist thực hành

1. **Đánh dấu hot path:** vòng lặp nào chạy nhiều, phương thức nào được gọi thường xuyên, collection nào chiếm nhiều heap?
2. **Kiểm tra kiểu của biến tích lũy:** có dùng `Integer`/`Long` thay cho `int`/`long` chỉ để cộng hoặc đếm không?
3. **Tìm boxing ẩn:** `list.add(i)`, `map.put(intKey, intValue)`, `return primitive` qua API wrapper, `Stream<Integer>` và vòng `for-each` trên collection wrapper.
4. **Chọn đúng cấu trúc lưu trữ:** `int[]` khi dữ liệu primitive dày đặc; `List<Integer>` khi cần collection chung; primitive-specialized map nếu workload chứng minh có lợi.
5. **Đừng bỏ qua `null`:** wrapper có thể biểu diễn thiếu dữ liệu nhưng cũng gây NPE khi unbox.
6. **Dùng primitive streams đúng cách:** `IntStream`/`LongStream`/`DoubleStream`; hiểu `boxed()` tạo luồng wrapper.
7. **Đo với dữ liệu thực:** quy mô, miền giá trị, kiểu truy cập, warm-up, bộ nhớ, allocation rate và GC.
8. **Kiểm tra số học riêng:** tràn số khi cộng/tổng không được giải quyết chỉ nhờ loại boxing.
9. **Giữ code dễ hiểu:** khi lợi ích nhỏ hoặc đường đi không nóng, abstraction chuẩn có thể quan trọng hơn tối ưu vi mô.
10. **Kiểm chứng sau thay đổi:** chạy test về giá trị, `null`, thứ tự, tính đồng thời và đo lại trên cùng workload.

## 15. Tự kiểm tra

1. `Integer sum = 0; sum += i;` thường đòi những chuyển đổi kiểu nào ở cấp ngữ nghĩa?
2. Vì sao không thể khẳng định mọi autoboxing đều cấp phát một object mới?
3. Một `ArrayList<Integer>` thường lưu trực tiếp bit của `int` hay tham chiếu tới các `Integer`?
4. Vòng `for (int n : listOfInteger)` có phát sinh unboxing không? Nếu phần tử là `null` sẽ ra sao?
5. `IntStream.boxed()` làm gì? `Stream<Integer>.mapToInt(Integer::intValue)` làm gì?
6. `IntStream.of(Integer.MAX_VALUE, 1).sum()` cho ra gì? Dùng gì khi cần tổng `long` chính xác ở ví dụ này?
7. Vì sao hai `Integer` có cùng giá trị không nên so sánh bằng `==` nếu mục tiêu là so sánh số?
8. So sánh dùng `System.nanoTime()` chỉ một lần đủ để kết luận `int[]` nhanh hơn `List<Integer>` không?
9. Khi nào nên cân nhắc primitive-specialized collection thay cho `HashMap<Integer, Integer>`?
10. Tại sao bỏ boxing không tự giải quyết bài toán thread safety?

**Gợi ý đáp án:** (1) Unbox `Integer → int`, cộng primitive rồi box lại `int → Integer`. (2) Wrapper có cache và JIT có thể khử đối tượng tạm. (3) Tham chiếu tới `Integer`. (4) Có; `null` gây NPE. (5) Box primitive thành wrapper và unbox wrapper thành primitive. (6) `-2147483648`; dùng `asLongStream().sum()` trước khi cộng để nhận `2147483648L`. (7) Hai wrapper dùng `==` so sánh tham chiếu; dùng `equals` hoặc unbox nếu an toàn. (8) Không; phải warm-up, lặp nhiều, tránh tối ưu loại bỏ mã và đo workload thực. (9) Khi profile chỉ ra overhead boxing/bộ nhớ/hash map là bottleneck và thư viện khác đáp ứng yêu cầu. (10) Tính đúng giữa các luồng là vấn đề đồng bộ/atomic, độc lập với chi phí boxing.

**Ghi nhớ:** Boxing là cầu nối giữa **primitive** và **wrapper**, cần thiết cho nhiều API generic nhưng có thể làm tăng **allocation, overhead bộ nhớ và chi phí truy cập** trong vòng lặp hoặc collection lớn. Ưu tiên primitive ở đường tính toán dày đặc, chọn cấu trúc dữ liệu theo yêu cầu, hiểu cache và JIT, xử lý `null` đúng, rồi **đo đạc** trước khi tối ưu.