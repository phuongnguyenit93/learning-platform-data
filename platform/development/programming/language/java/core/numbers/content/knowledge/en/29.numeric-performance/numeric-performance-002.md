# Boxing trong collection, stream và vòng lặp Java

## 1. Hiểu đúng vấn đề hiệu năng

Java có hai nhóm kiểu số thường gặp:

- **Primitive:** `byte`, `short`, `int`, `long`, `float`, `double`. Một biến primitive giữ trực tiếp giá trị theo kiểu tương ứng; ví dụ `int count = 42;`.
- **Wrapper (kiểu tham chiếu):** `Byte`, `Short`, `Integer`, `Long`, `Float`, `Double`. Ví dụ `Integer count = 42;` lưu tham chiếu đến một đối tượng biểu diễn giá trị số.

**Boxing** là chuyển primitive thành wrapper, ví dụ `int` → `Integer`. **Unboxing** là chuyển wrapper thành primitive, ví dụ `Integer` → `int`. Java hỗ trợ **autoboxing/unboxing** để trình biên dịch thêm những chuyển đổi này tại nơi cú pháp cho phép:

~~~java
int primitive = 42;
Integer boxed = primitive; // boxing, tương đương Integer.valueOf(primitive)
int again = boxed;         // unboxing, tương đương boxed.intValue()
~~~

Cú pháp ngắn không làm hai kiểu trở thành một. Wrapper vẫn là đối tượng tham chiếu, có thể chứa `null` khi dùng biến tham chiếu, có chi phí lưu trữ/quản lý và có thể tạo thêm đối tượng. Đổi lại, wrapper dùng được trong API generic như `List<Integer>`, `Map<Integer, Long>` hoặc những nơi cần sự vắng mặt `null`.

Chủ đề **“Boxing trong collection, stream và vòng lặp”** tập trung vào cả **độ đúng** lẫn **hiệu năng**: boxing xuất hiện ở đâu, tác động của nó khi số lượng phần tử lớn, và lúc nào nên dùng `int[]`, `IntStream`, `LongStream` hoặc `DoubleStream`.

Không phải mọi boxing đều luôn cấp phát đối tượng mới. `Integer.valueOf` có cache cho các giá trị thông dụng; JIT có thể tối ưu một số allocation bằng phân tích escape. Vì vậy cách nói chính xác là **boxing có thể phát sinh công việc, tham chiếu và allocation/GC**, còn mức chi phí thực tế phải đo ở đúng workload.

## 2. Boxing/unboxing diễn ra như thế nào?

### 2.1. Chuyển đổi tự động trong phép gán và biểu thức

~~~java
Integer a = 10; // autobox: Integer.valueOf(10)
int b = a;      // unbox: a.intValue()

Integer sum = a + 5;
// unbox a thành int -> cộng 5 -> box kết quả thành Integer

int next = a + 1;
// unbox a, phép cộng primitive, gán vào int: không cần box kết quả
~~~

Các comment mô tả **ngữ nghĩa chuyển đổi**, không khẳng định máy ảo bắt buộc cấp phát một đối tượng riêng cho mỗi lần boxing. Thư viện `Integer.valueOf(int)` được Java bảo đảm cache ít nhất các giá trị từ `-128` đến `127`; giá trị nằm ngoài khoảng có thể được cache rộng hơn tùy JVM/cấu hình. Không nên suy luận tốc độ từ việc một ví dụ `10` nằm trong cache.

### 2.2. Unboxing của null ném NullPointerException

~~~java
Integer missing = null;
int n = missing; // NullPointerException tại chỗ unboxing
~~~

Không có giá trị `int` đại diện cho `null`. Phép toán số học cũng có thể ngầm unbox và lỗi:

~~~java
Integer count = null;
// int doubled = count * 2; // Ném NullPointerException
~~~

Ví dụ khi cần phân biệt “không có giá trị” với `0`, hãy quyết định chính sách trước khi chuyển kiểu: từ chối null, giữ wrapper/`OptionalInt` ở ranh giới, hoặc dùng giá trị mặc định có chủ đích. Không âm thầm biến mọi null thành 0 nếu hai trạng thái có ý nghĩa khác nhau.

### 2.3. So sánh wrapper theo giá trị, không theo identity

~~~java
Integer a = Integer.valueOf(127);
Integer b = Integer.valueOf(127);

System.out.println(a == b); // true: valueOf cache giá trị 127
System.out.println(a.equals(b)); // true: cùng giá trị số
~~~

`==` giữa hai biến kiểu `Integer` kiểm tra **cùng tham chiếu đối tượng**, không so giá trị số. Với các giá trị không được bảo đảm cache như `1000`, kết quả `==` không phải một hợp đồng để kiểm tra bằng nhau. Dùng `a.equals(b)` nếu a chắc chắn khác null hoặc `Objects.equals(a, b)` khi có thể null.

Cũng phải phân biệt khi một vế là `int`:

~~~java
Integer wrapped = 1000;
int primitive = 1000;
boolean same = wrapped == primitive; // true: wrapped được unbox trước khi so sánh
~~~

Khi `wrapped == null`, biểu thức `wrapped == primitive` có thể ném `NullPointerException` vì unboxing. Đừng dùng dấu `==` cho wrapper chỉ vì đã từng thấy ví dụ trả `true`.

## 3. Collection: List<Integer> không phải int[]

### 3.1. Generic collection cần kiểu tham chiếu

~~~java
import java.util.ArrayList;
import java.util.List;

List<Integer> numbers = new ArrayList<>();
numbers.add(1);  // 1 được box khi truyền tới add(Integer)
numbers.add(2);
int first = numbers.get(0); // lấy Integer rồi unbox
~~~

Cú pháp `List<int>` **không hợp lệ** trong Java 17: generic type argument phải là kiểu tham chiếu. Dù danh sách chứa toàn số, `List<Integer>` vẫn quản lý phần tử như các tham chiếu đến wrapper. `ArrayList<Integer>` có một mảng tham chiếu ở bên trong, khác với `int[]` là mảng giá trị primitive.

Điều này có tác động:

- Với `int[]`, mỗi vị trí chứa trực tiếp một `int`; không có `Integer` cho từng phần tử.
- Với `ArrayList<Integer>`, các vị trí chứa tham chiếu. Các đối tượng wrapper có thể mang chi phí bộ nhớ, tham chiếu và tạo áp lực GC, nhất là khi nhiều giá trị nằm ngoài cache.
- `List<Integer>` có thể chứa `null` (nếu loại danh sách cho phép), còn `int[]` không thể.
- `List<Integer>` cung cấp API collection thuận tiện: thay đổi kích thước, thao tác generic, tương tác với thư viện; `int[]` cố định kích thước và dùng API mảng.

Không nên khẳng định mọi `ArrayList<Integer>` luôn dùng đúng một số byte trên từng phần tử: kích thước reference/object còn phụ thuộc JVM, kích thước con trỏ, object alignment và tối ưu hóa runtime. Nhưng cấu trúc **tham chiếu vs primitive** là khác biệt căn bản.

### 3.2. List.of, Arrays.asList và chi phí boxing

~~~java
List<Integer> fixedSize = java.util.Arrays.asList(1, 2, 3);
List<Integer> immutable = List.of(1, 2, 3);
~~~

Các literal nguyên được boxing để trở thành `Integer` trong danh sách. `Arrays.asList` trả một danh sách kích thước cố định được hỗ trợ bởi mảng và **cho phép giá trị null**; `List.of` tạo danh sách không sửa đổi và **không cho null**. Cả hai đều là `List<Integer>`, không biến thành `int[]` chỉ vì phần tử là số.

Nếu cần xử lý mảng primitive:

~~~java
int[] values = {1, 2, 3};
int first = values[0]; // không boxing
~~~

Khi dữ liệu có hàng triệu số nguyên và chủ yếu tính tổng/thống kê, nên cân nhắc lưu/đọc dưới dạng primitive. Khi dữ liệu vốn từ API generic, việc chuyển sang mảng primitive cũng cần **unbox từng phần tử một lần**; không thể loại bỏ chi phí lưu trữ wrapper đã xuất hiện từ trước bằng một lời gọi stream.

### 3.3. Map với key/value là số

~~~java
Map<Integer, Integer> counts = new java.util.HashMap<>();

counts.merge(7, 1, Integer::sum);
counts.merge(7, 1, Integer::sum);
// counts.get(7) -> Integer có giá trị 2
~~~

Ở `Map<Integer, Integer>`, cả key và value là wrapper. Trong `Integer::sum`, hai giá trị `Integer` được unbox để cộng primitive và kết quả được box trở lại theo chữ ký `BiFunction` mà `merge` cần. Với nhiều lượt cập nhật tần suất trong vòng lặp nóng, việc quản lý wrapper có thể trở thành chi phí đáng kể.

Không vì thế tự thay mọi map bằng mảng: mảng `int[] counts` chỉ phù hợp khi miền khóa nhỏ, liên tục và ánh xạ trực tiếp được thành chỉ số. Với khóa thưa, miền lớn hoặc tính năng collection phức tạp, `Map` thường là lựa chọn đúng về thiết kế. Đánh giá bộ nhớ, tốc độ, tính đơn giản và yêu cầu API trước khi tối ưu.

## 4. Boxing trong vòng lặp

### 4.1. Vòng lặp primitive tránh boxing ở biến đếm

~~~java
int sum = 0;
for (int i = 0; i < 1_000; i++) {
    sum += i; // chỉ dùng int trong phần phép toán này
}
~~~

Ngược lại:

~~~java
Integer sum = 0;
for (Integer i = 0; i < 1_000; i++) {
    sum += i;
}
~~~

Vòng lặp thứ hai làm nhiều chuyển đổi ngầm: điều kiện `i < 1000` phải unbox, bước `i++` phải unbox/tăng/box, và `sum += i` phải unbox cả hai toán hạng rồi box lại kết quả cho biến `sum`. Những chuyển đổi đó không cần thiết nếu mục tiêu chỉ là tính toán trên số nguyên.

Một số đối tượng có thể được tối ưu hóa bởi JIT và giá trị nhỏ có thể lấy từ cache, nên không suy ra “mỗi vòng luôn có đúng ba object mới”. Nhưng mã primitive có ý nghĩa rõ hơn và tránh đặt trách nhiệm tối ưu toàn bộ phép toán lên compiler/runtime.

### 4.2. Enhanced for trên List<Integer>

~~~java
List<Integer> values = List.of(1, 2, 3, 4);

int total = 0;
for (Integer item : values) {
    total += item; // item được unbox để cộng
}
~~~

Phần tử được lấy từ danh sách là `Integer`; dù biến tích lũy `total` là `int`, giá trị `item` vẫn phải unbox khi cộng. Có thể viết `for (int item : values)` và để unboxing xuất hiện ngay khi gán biến lặp, nhưng **không xóa** phần tử wrapper trong list.

Trong enhanced for trên mảng primitive:

~~~java
int[] values = {1, 2, 3, 4};
int total = 0;

for (int item : values) {
    total += item; // không boxing/unboxing
}
~~~

Với `List<Integer>`, Java thường dùng cơ chế `Iterator<Integer>` cho enhanced for; overhead iterator và thao tác collection là yếu tố riêng ngoài boxing. Với `int[]`, enhanced for duyệt phần tử mảng trực tiếp. Đừng đồng nhất overhead vòng lặp với chỉ boxing: bounds check, branch, cấu trúc dữ liệu, CPU cache và tối ưu JIT đều có thể ảnh hưởng.

### 4.3. Null trong list gây lỗi khi cộng

~~~java
List<Integer> values = java.util.Arrays.asList(1, null, 3);

int total = 0;
for (Integer item : values) {
    total += item; // NPE khi đến phần tử null
}
~~~

Nếu null cần được bỏ qua, hãy nói rõ:

~~~java
int total = 0;
for (Integer item : values) {
    if (item != null) {
        total += item;
    }
}
~~~

Nếu null là dữ liệu không hợp lệ, nên kiểm tra và từ chối thay vì bỏ qua để tránh thay đổi tổng một cách âm thầm.

## 5. Stream<Integer> và IntStream: khác biệt rất quan trọng

### 5.1. Generic Stream chứa wrapper

~~~java
List<Integer> values = List.of(1, 2, 3, 4);

int total = values.stream()
        .mapToInt(Integer::intValue)
        .sum(); // 10
~~~

`values.stream()` có kiểu `Stream<Integer>`. Mỗi phần tử vẫn là `Integer` từ collection. `mapToInt(Integer::intValue)` **unbox** giá trị thành primitive stream `IntStream`. Sau bước này, các phép toán chuyên biệt như `sum()` hoạt động theo giao diện primitive và không cần boxing lại từng giá trị chỉ để cộng.

Vì sao không viết:

~~~java
Integer total = values.stream().reduce(0, Integer::sum);
~~~

Câu lệnh `reduce` trên `Stream<Integer>` hợp lệ, nhưng các lần cập nhật giá trị tích lũy thao tác qua `Integer` theo chữ ký generic; việc unbox/box trung gian có thể tạo thêm chi phí. `mapToInt(...).sum()` diễn đạt mục tiêu tính tổng số nguyên trực tiếp hơn và là lựa chọn phổ biến khi chỉ cần kết quả primitive.

### 5.2. Các primitive stream của Java 17

| Primitive stream | Phần tử | Phương thức tiêu biểu | Khi dùng |
| --- | --- | --- | --- |
| `IntStream` | `int` | `range`, `rangeClosed`, `of`, `sum`, `average` | Chỉ số, số đếm, phép toán nguyên 32 bit |
| `LongStream` | `long` | `range`, `of`, `sum`, `average` | Số nguyên 64 bit, miền rộng hơn |
| `DoubleStream` | `double` | `of`, `sum`, `average`, `map` | Phép tính số thực dấu phẩy động |

Java không có `IntegerStream` chuẩn riêng; `IntStream` là chuyên biệt primitive của `int`. Không có primitive stream chuẩn cho mọi primitive như `ByteStream` hay `ShortStream` trong Java 17.

Ví dụ sinh số nguyên trực tiếp không qua wrapper collection:

~~~java
import java.util.stream.IntStream;

int sumExclusive = IntStream.range(1, 4).sum(); // 1+2+3 = 6
int sumInclusive = IntStream.rangeClosed(1, 4).sum(); // 1+2+3+4 = 10
~~~

`range(startInclusive, endExclusive)` loại cận cuối; `rangeClosed(startInclusive, endInclusive)` gồm cận cuối. Đây là ranh giới thường gặp khiến thuật toán sai một phần tử, không phải sai do boxing.

### 5.3. Chuyển giữa primitive stream và boxed stream

~~~java
IntStream primitive = IntStream.rangeClosed(1, 4);
List<Integer> boxedList = primitive.boxed().toList();
// [1, 2, 3, 4]
~~~

`boxed()` cố ý biến từng phần tử `int` thành `Integer` để dùng API generic hoặc thu về `List<Integer>`. Đây là **ranh giới boxing** rõ ràng. `Stream.toList()` (Java 16+) trả về danh sách **không sửa đổi**; muốn danh sách thay đổi được, có thể tạo `new ArrayList<>(boxedList)`.

Ngược lại:

~~~java
List<Integer> boxed = List.of(1, 2, 3, 4);
int[] primitiveArray = boxed.stream()
        .mapToInt(Integer::intValue)
        .toArray();
~~~

Mỗi phần tử `Integer` cần unbox khi chuyển sang `int[]`. Sau đó, sử dụng `int[]` có thể giúp những vòng lặp/tính toán tiếp theo không duy trì wrapper theo phần tử. Nhưng copy/chuyển đổi cũng có chi phí; không nên làm nhiều lần trong cùng pipeline một cách vô ích.

### 5.4. Chọn đúng thời điểm đưa về primitive

Hai pipeline:

~~~java
List<Integer> values = List.of(1, 2, 3, 4);

int a = values.stream()
        .map(x -> x + 1)
        .mapToInt(Integer::intValue)
        .sum();

int b = values.stream()
        .mapToInt(Integer::intValue)
        .map(x -> x + 1)
        .sum();
~~~

Cả hai cho cùng kết quả 14 với danh sách trên. Tuy nhiên pipeline `a` dùng `Stream<Integer>.map`: lambda đọc `Integer`, tính số nguyên và tạo kết quả theo kiểu wrapper `Integer` của stream. Pipeline `b` chuyển một lần sang `IntStream` rồi dùng phép `map` trên primitive. Khi chuỗi xử lý dài và mỗi bước chỉ làm số học, **chuyển sang primitive sớm** thường làm rõ ý nghĩa và có thể giảm overhead.

Đừng chuyển sang `IntStream` sớm nếu thao tác còn cần biểu diễn `null` hoặc đối tượng phức tạp. Chính sách với null phải được quyết định rõ trước khi unbox.

### 5.5. Xử lý null trong Stream<Integer>

~~~java
List<Integer> values = java.util.Arrays.asList(1, null, 3);

// Nếu null được quy ước là bỏ qua:
int total = values.stream()
        .filter(java.util.Objects::nonNull)
        .mapToInt(Integer::intValue)
        .sum(); // 4
~~~

Nếu bỏ `filter`, `Integer::intValue` gặp null sẽ ném `NullPointerException`. Trường hợp null là lỗi nguồn dữ liệu, hãy xác thực thay vì lọc âm thầm. Với trường hợp “có hoặc không có một số nguyên” đơn lẻ, `OptionalInt` có thể giúp diễn đạt vắng mặt mà không dùng `Integer null`, nhưng cần cân nhắc API và ngữ nghĩa.

## 6. Tổng hợp và thống kê trên primitive stream

Các stream primitive có toán tử được thiết kế cho số:

~~~java
int[] values = {1, 2, 3, 4};

int total = java.util.Arrays.stream(values).sum(); // 10

java.util.IntSummaryStatistics stats =
        java.util.Arrays.stream(values).summaryStatistics();

// stats.getCount(): 4
// stats.getSum(): 10
// stats.getMin(): 1
// stats.getMax(): 4
// stats.getAverage(): 2.5
~~~

`IntSummaryStatistics` chứa count, sum, min, max và average. `getSum()` của thống kê dùng `long`, còn `IntStream.sum()` trả `int` nên tổng primitive vẫn **có thể tràn** nếu tổng vượt phạm vi 32 bit:

~~~java
int overflowed = IntStream.of(Integer.MAX_VALUE, 1).sum();
// -2147483648 do tràn số nguyên int

long safer = IntStream.of(Integer.MAX_VALUE, 1)
        .asLongStream()
        .sum();
// 2147483648L
~~~

Chuyển sang `LongStream` giúp tăng phạm vi nhưng không loại trừ tràn `long` trong mọi trường hợp. Nếu cần tổng vượt 64 bit hoặc số thập phân chính xác, dùng mô hình số học phù hợp như `BigInteger` hoặc `BigDecimal`; chúng là **kiểu đối tượng** và không có primitive stream riêng trong JDK. Mục tiêu hiệu năng không được đặt cao hơn yêu cầu chính xác.

`average()` trả `OptionalDouble` vì stream có thể rỗng; `sum()` trên stream rỗng trả 0. Phải xử lý trường hợp không có dữ liệu theo chính sách nghiệp vụ, thay vì mặc định average luôn có giá trị:

~~~java
double mean = IntStream.of(1, 2, 3, 4)
        .average()
        .orElseThrow(); // 2.5
~~~

Ví dụ là đoạn mã đặt trong phương thức với import `java.util.stream.IntStream`.

## 7. Chương trình Java 17+ chạy được

Tạo file `BoxingPerformanceDemo.java`:

~~~java
import java.util.Arrays;
import java.util.IntSummaryStatistics;
import java.util.List;
import java.util.stream.IntStream;

public class BoxingPerformanceDemo {
    public static void main(String[] args) {
        List<Integer> values = Arrays.asList(1, 2, 3, 4);

        int loopSum = 0;
        for (Integer boxed : values) {
            loopSum += boxed; // unbox khi cộng
        }
        System.out.println("List<Integer> sum (loop): " + loopSum);

        System.out.println("Stream<Integer> sum: "
                + values.stream().mapToInt(Integer::intValue).sum());

        System.out.println("IntStream sum: "
                + IntStream.rangeClosed(1, 4).sum());

        System.out.println("Primitive -> boxed List: "
                + IntStream.rangeClosed(1, 4).boxed().toList());

        System.out.println("int[] sum: "
                + Arrays.stream(new int[] {1, 2, 3, 4}).sum());

        IntSummaryStatistics stats =
                IntStream.of(1, 2, 3, 4).summaryStatistics();
        System.out.println("stats: "
                + stats.getCount() + ", " + stats.getSum()
                + ", " + stats.getAverage());

        Integer small1 = Integer.valueOf(127);
        Integer small2 = Integer.valueOf(127);
        System.out.println("127 same reference: " + (small1 == small2));
        System.out.println("1000 equal value: "
                + Integer.valueOf(1000).equals(Integer.valueOf(1000)));

        Integer nullable = null;
        try {
            int n = nullable;
            System.out.println(n);
        } catch (NullPointerException ex) {
            System.out.println("unboxing null: NullPointerException");
        }

        List<Integer> withNull = Arrays.asList(1, null, 3);
        try {
            System.out.println(withNull.stream()
                    .mapToInt(Integer::intValue).sum());
        } catch (NullPointerException ex) {
            System.out.println("stream null: NullPointerException");
        }

        System.out.println("range(1,4) sum: "
                + IntStream.range(1, 4).sum());
        System.out.println("rangeClosed(1,4) sum: "
                + IntStream.rangeClosed(1, 4).sum());
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac BoxingPerformanceDemo.java
java BoxingPerformanceDemo
~~~

Kết quả:

~~~text
List<Integer> sum (loop): 10
Stream<Integer> sum: 10
IntStream sum: 10
Primitive -> boxed List: [1, 2, 3, 4]
int[] sum: 10
stats: 4, 10, 2.5
127 same reference: true
1000 equal value: true
unboxing null: NullPointerException
stream null: NullPointerException
range(1,4) sum: 6
rangeClosed(1,4) sum: 10
~~~

Kết quả chỉ minh họa **hành vi**, không đo tốc độ. `int[]`, `List<Integer>` và các dạng stream đều cho tổng 10 ở ví dụ nhỏ nhưng có mô hình lưu trữ/thực thi khác nhau. Hai dòng xử lý null cho thấy unboxing có thể thất bại ở cả vòng lặp và stream. Dòng cache chỉ cho thấy `Integer.valueOf(127)` dùng tham chiếu được chia sẻ theo hợp đồng cache; không dùng `==` để so giá trị wrapper nói chung.

## 8. Cân nhắc hiệu năng thực tế

### 8.1. Nguồn overhead khi boxing nhiều lần

Trong tập dữ liệu lớn, boxing có thể:

- Làm tăng các **tham chiếu** và metadata của wrapper so với mảng primitive.
- Tạo wrapper mới (đặc biệt giá trị ngoài cache), gây allocation và áp lực cho garbage collector.
- Tạo thêm chuyển đổi unbox/box ở vòng lặp, lambda hoặc các phương thức generic.
- Dẫn đến truy cập dữ liệu gián tiếp qua tham chiếu, ảnh hưởng đến locality của bộ nhớ và CPU cache.

Những chi phí này phụ thuộc việc wrapper có sống đủ lâu để phải nằm trên heap, cấu trúc collection, tối ưu escape analysis của JIT, thời gian warmup và đặc tính phần cứng. Không có con số “List<Integer> chậm hơn int[] X lần” áp dụng phổ quát.

### 8.2. Tối ưu đúng điểm

Khi dữ liệu nguyên là mảng `int[]` và nhiệm vụ là tính toán lặp đi lặp lại, dùng vòng lặp primitive hoặc `Arrays.stream(int[])` thường phù hợp. Nếu đang làm việc với `List<Integer>`, dùng `mapToInt` hoặc chuyển một lần sang `int[]` khi việc tính toán số học dài/ngốn tài nguyên đủ để bù chi phí chuyển đổi.

Ngược lại, việc thay tất cả `List<Integer>` thành `int[]` có thể làm mất tính linh hoạt của API, gây thêm công copy khi thêm/xóa phần tử, tăng độ phức tạp hoặc tạo bug. Nếu bottleneck nằm ở I/O, network hoặc database thì giảm boxing trong vài vòng lặp hiếm khi mang lại cải thiện đáng kể.

Với biến đếm và tích lũy ở vòng lặp nóng, chọn primitive khi không cần null và không cần generic wrapper. Ở ranh giới thư viện bắt buộc cần đối tượng, hãy boxing đúng nơi cần thiết.

### 8.3. Benchmark có ý nghĩa: JMH, không đo bằng một lần System.nanoTime

Một thử nghiệm hiệu năng đáng tin nên dùng công cụ như **JMH (Java Microbenchmark Harness)**, với các đặc điểm:

- Có warmup để JIT tối ưu; có nhiều iteration/fork theo cấu hình.
- Dùng `Blackhole` hoặc cách tiêu thụ kết quả để tránh phép tính bị compiler loại bỏ.
- So cùng workload/dữ liệu, kích thước đầu vào và mục tiêu tính toán; phân biệt **chi phí xây dựng collection** với **chi phí duyệt/tính tổng**.
- Đo throughput/latency cùng với allocation và GC khi phù hợp; đánh giá phân phối số, kích thước và tỷ lệ giá trị nằm trong cache của wrapper.
- Không dùng một kết quả nhỏ ở laptop làm bằng chứng áp dụng cho production.

Ví dụ ý tưởng benchmark: chuẩn bị trước một `int[]` và một `List<Integer>` tương đương trong bước setup, rồi đo riêng `for-each` và `stream/mapToInt/sum` trên mỗi cấu trúc. Nếu vừa tạo danh sách vừa đo phép tính, kết quả không còn chỉ phản ánh chi phí duyệt. Đây là hướng thiết kế benchmark, **không phải mã JMH hoàn chỉnh**.

### 8.4. Stream song song không tự động giải quyết boxing

`parallelStream()` có thêm chi phí tách tác vụ, phối hợp thread, gom kết quả và yêu cầu phép toán không có side effect không an toàn. Với danh sách nhỏ, thường không có lý do để sử dụng chỉ nhằm “tăng tốc”. Ngay cả pipeline song song, nếu dữ liệu ở `List<Integer>` thì đầu vào vẫn là wrapper; song song hóa không biến nó thành mảng primitive.

Nếu cần song song, kiểm tra dữ liệu đủ lớn, tính toán đủ tốn CPU, nguồn spliterator phù hợp và phép giảm có tính kết hợp đúng. Không dùng một biến `int sum` bên ngoài rồi tăng từ nhiều luồng bằng `forEach`: vừa tạo race condition vừa không tận dụng phép tổng hợp `sum` vốn có.

## 9. Những lỗi phổ biến

1. **Viết `List<int>`:** Java 17 generic cần kiểu tham chiếu, nên dùng `List<Integer>` hoặc dùng `int[]` khi phù hợp.
2. **Dùng `Integer` cho mọi biến đếm:** trong vòng lặp số học, biến primitive tránh các chuyển đổi không cần thiết.
3. **Nghĩ `List<Integer>` là mảng int bên trong:** danh sách quản lý reference tới wrapper.
4. **Tin boxing nào cũng tạo object mới:** cache `Integer.valueOf` và tối ưu JIT có thể thay đổi việc cấp phát thực tế; hãy đo trước khi kết luận.
5. **Tin boxing không có chi phí vì compiler tự làm:** cách biểu diễn tham chiếu, nullable và boxing ở pipeline vẫn có thể tác động bộ nhớ/GC/latency.
6. **So sánh wrapper bằng `==`:** so identity, không bảo đảm so giá trị; dùng `equals` hoặc `Objects.equals`.
7. **Unbox null không kiểm tra:** `Integer x = null; int y = x;` ném NPE.
8. **`Stream<Integer>.reduce` cho mọi phép tổng:** khi chỉ tính tổng số nguyên, xem xét `mapToInt(...).sum()` hoặc primitive stream từ đầu.
9. **Tưởng `mapToInt` xóa overhead lưu trữ của danh sách đã boxed:** nó unbox từng phần tử nhưng dữ liệu gốc vẫn là wrapper.
10. **Gọi `boxed()` rồi tiếp tục nhiều bước số học:** nếu không cần API generic, giữ `IntStream`, `LongStream` hoặc `DoubleStream` càng lâu càng phù hợp.
11. **Nhầm `range` với `rangeClosed`:** cận trên của `range` không được tính.
12. **Bỏ qua overflow khi chuyển sang primitive sum:** `IntStream.sum()` trả `int` và có thể tràn, ngay cả khi không có boxing.
13. **Lọc null âm thầm:** chỉ dùng `filter(Objects::nonNull)` nếu đây là quy tắc dữ liệu được chấp nhận.
14. **Benchmark bằng vài lần chạy ngắn:** JIT, warmup, GC và loại bỏ mã không sử dụng làm số đo thiếu tin cậy.

## 10. Tự kiểm tra

**Câu 1.** Tại sao `List<Integer>` không thể dùng `List<int>`?

**Đáp án:** Generic type parameter trong Java 17 là kiểu tham chiếu. `Integer` là wrapper cho `int`; cấu trúc primitive như `int[]` không phải một generic collection.

**Câu 2.** Trong vòng lặp `for (Integer i = 0; i < 1000; i++)` có những conversion gì?

**Đáp án:** Giá trị ban đầu 0 được boxing. Kiểm tra `i < 1000` unbox, `i++` unbox để tăng rồi box lại để gán cho biến `Integer`. Tùy mã trong body còn có các conversion khác.

**Câu 3.** `List.of(1,2,3).stream().mapToInt(Integer::intValue).sum()` được bao nhiêu và boxing còn tồn tại ở đâu?

**Đáp án:** Tổng bằng 6. Các phần tử list là `Integer`; `mapToInt` unbox sang primitive stream trước khi cộng.

**Câu 4.** Nếu `List<Integer>` có phần tử null, gọi `mapToInt(Integer::intValue)` có kết quả gì?

**Đáp án:** `NullPointerException` khi gặp null. Lọc bỏ hoặc từ chối null tùy hợp đồng dữ liệu.

**Câu 5.** `IntStream.range(1,4).sum()` và `IntStream.rangeClosed(1,4).sum()` khác nhau thế nào?

**Đáp án:** Lần lượt là 6 (1+2+3) và 10 (1+2+3+4).

**Câu 6.** Muốn thu `IntStream` thành `List<Integer>` thì dùng gì, và khi nào cần cân nhắc chi phí?

**Đáp án:** `stream.boxed().toList()`. Mỗi giá trị primitive được chuyển sang wrapper về mặt ngữ nghĩa; khi dữ liệu lớn hoặc pipeline chủ yếu tính số, nên kiểm tra xem có thật sự cần list generic không.

**Câu 7.** Dùng `IntStream` có ngăn tổng vượt `Integer.MAX_VALUE` bị tràn không?

**Đáp án:** Không. `IntStream.sum()` là phép cộng số nguyên `int`. Có thể chuyển qua `asLongStream().sum()` nếu long đủ phạm vi hoặc dùng số nguyên tùy ý khi cần.

## 11. Tài liệu Java chính thức

- [Autoboxing and Unboxing — Java Tutorials](https://docs.oracle.com/javase/tutorial/java/data/autoboxing.html): cơ chế chuyển primitive sang wrapper và ngược lại.
- [`Integer` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Integer.html): `valueOf`, `intValue`, `equals` và cache.
- [`List` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html): API collection generic.
- [`Stream` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html): các toán tử `mapToInt`, `reduce`, `toList`.
- [`IntStream` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/IntStream.html): `range`, `rangeClosed`, `boxed`, `sum`, `summaryStatistics`.
- [`IntSummaryStatistics` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/IntSummaryStatistics.html): thống kê trên số nguyên.

**Ghi nhớ:** Dùng `Integer` khi cần ngữ nghĩa đối tượng/generic hoặc nullable; dùng `int`, `int[]` và `IntStream` khi chủ yếu xử lý số nguyên trong các đoạn tính toán nhiều lần. Nhìn rõ ranh giới boxing/unboxing, kiểm tra null và overflow, rồi đo đúng workload trước khi đánh đổi thiết kế chỉ vì lo chi phí.
