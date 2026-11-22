# Stream.toArray() và kiểu mảng kết quả (Java 8+)

## 1. Mục tiêu và tình huống sử dụng

Sau bài này, bạn có thể:

- Giải thích vì sao **Stream<T>.toArray()** trả về **Object[]**, dù các phần tử trong stream đều là String, Integer hay kiểu đối tượng cụ thể khác.
- Dùng **toArray(String[]::new)** hoặc một array constructor tương ứng để nhận mảng tham chiếu đúng kiểu; phân biệt kiểu ở thời điểm biên dịch và kiểu thật của mảng khi chạy.
- Chọn **IntStream/LongStream/DoubleStream.toArray()** khi cần mảng nguyên thủy **int[]/long[]/double[]** để tránh boxing không cần thiết.
- Nhận biết các lỗi thường gặp về ép kiểu, phần tử không tương thích, stream đã tiêu thụ, thứ tự, tính hữu hạn và bộ nhớ.

**toArray** là một *terminal operation* (phép toán kết thúc): nó kích hoạt việc xử lý pipeline, lấy toàn bộ các phần tử sau các bước lọc/biến đổi và tạo mảng kết quả. Nó hữu ích khi API nhận mảng, khi cần truy cập theo chỉ số, khi kích thước cố định là phù hợp hoặc khi phải giao tiếp với thư viện yêu cầu một kiểu mảng cụ thể. Các API dưới đây xuất hiện từ Java 8 và vẫn phù hợp với Java hiện đại.

## 2. Bốn dạng toArray cần phân biệt

| Nguồn stream | Lời gọi | Kiểu trả về ở Java | Kiểu phần tử của mảng lúc chạy |
| --- | --- | --- | --- |
| Stream<T> | toArray() | Object[] | Object |
| Stream<T> | toArray(IntFunction<A[]> generator) | A[] | Kiểu mảng do generator tạo, ví dụ String[] hoặc Number[] |
| IntStream | toArray() | int[] | int |
| LongStream / DoubleStream | toArray() | long[] / double[] | long / double |

Ví dụ nhanh:

~~~java
Object[] objects = Stream.of("An", "Binh").toArray();
String[] strings = Stream.of("An", "Binh").toArray(String[]::new);
int[] ints = IntStream.rangeClosed(1, 3).toArray();
long[] longs = java.util.stream.LongStream.of(1L, 2L).toArray();
double[] doubles = java.util.stream.DoubleStream.of(1.5, 2.5).toArray();
~~~

**Mấu chốt:** Kiểu tổng quát **Stream<String>** mô tả phần tử trong pipeline, không biến kết quả của phiên bản **toArray()** không tham số thành String[]. Muốn String[] thực sự, hãy truyền hàm tạo mảng.

## 3. Cơ chế hoạt động của terminal operation

Một pipeline có thể gồm nguồn dữ liệu, các bước trung gian như **filter**, **map**, **sorted**, và bước cuối **toArray**:

~~~text
Danh sách / mảng / nguồn Stream
        -> filter(...) -> map(...) -> toArray(...)
                                          |
                                          v
                               Mảng chứa kết quả đã xử lý
~~~

Các bước trung gian thông thường được đánh giá theo nhu cầu (*lazy*). Khi gọi **toArray**, Java duyệt các phần tử cần thiết để xây dựng mảng; kết quả được vật hóa vào bộ nhớ, khác với một Stream còn có thể xử lý từng phần tử. Với nguồn có encounter order xác định, mảng phản ánh thứ tự đó, sau khi áp dụng các phép trung gian.

Sau phép toán kết thúc, **không được tái sử dụng cùng đối tượng Stream**. Nếu cần cả Object[] và String[] từ một List, hãy gọi **list.stream()** hai lần để tạo hai pipeline riêng. Không có giả định rằng có thể gọi **toArray** hai lần trên một stream đã dùng.

## 4. Ví dụ đầy đủ, chạy được bằng Java 17+

Tạo tệp **StreamToArrayDemo.java**:

~~~java
import java.util.Arrays;
import java.util.List;
import java.util.stream.IntStream;
import java.util.stream.Stream;

public class StreamToArrayDemo {
    public static void main(String[] args) {
        List<String> names = Arrays.asList("An", "Binh", "Chi", "Bao");

        Object[] objects = names.stream()
                .filter(name -> name.startsWith("B"))
                .toArray();

        String[] strings = names.stream()
                .filter(name -> name.startsWith("B"))
                .toArray(String[]::new);

        String[] upper = names.stream()
                .map(String::toUpperCase)
                .toArray(size -> new String[size]);

        int[] squares = IntStream.rangeClosed(1, 4)
                .map(number -> number * number)
                .toArray();

        Integer[] boxed = IntStream.rangeClosed(1, 3)
                .boxed()
                .toArray(Integer[]::new);

        String[] empty = Stream.<String>empty().toArray(String[]::new);

        String[] parallel = Stream.of("A", "B", "C")
                .parallel()
                .toArray(String[]::new);

        System.out.println("Object[]: " + Arrays.toString(objects));
        System.out.println("runtime: " + objects.getClass().getTypeName());
        System.out.println("String[]: " + Arrays.toString(strings));
        System.out.println("runtime: " + strings.getClass().getTypeName());
        System.out.println("upper: " + Arrays.toString(upper));
        System.out.println("int[]: " + Arrays.toString(squares));
        System.out.println("Integer[]: " + Arrays.toString(boxed));
        System.out.println("empty length: " + empty.length);
        System.out.println("parallel: " + Arrays.toString(parallel));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac StreamToArrayDemo.java
java StreamToArrayDemo
~~~

Kết quả chuẩn:

~~~text
Object[]: [Binh, Bao]
runtime: java.lang.Object[]
String[]: [Binh, Bao]
runtime: java.lang.String[]
upper: [AN, BINH, CHI, BAO]
int[]: [1, 4, 9, 16]
Integer[]: [1, 2, 3]
empty length: 0
parallel: [A, B, C]
~~~

Đoạn ví dụ sử dụng các Stream API có từ Java 8 nên cũng có thể chạy trên JDK 8. Việc ghi Java 17+ ở đây phản ánh môi trường thực hành hiện đại; API đang học không phụ thuộc tính năng cũ đã bị loại bỏ.

Phân tích:

1. **objects** có kiểu Object[] ở cả compile time và runtime. Các phần tử bên trong vẫn là String, nhưng kiểu mảng thực tế là Object[].
2. **strings** có kiểu String[] ở cả compile time và runtime vì **String[]::new** tạo ra mảng String.
3. **upper** chứng minh lambda **size -> new String[size]** tương đương array constructor reference **String[]::new** cho mục đích này.
4. **squares** là **int[]** nhờ pipeline nguyên thủy **IntStream**; **boxed** là **Integer[]**, chứa object wrapper.
5. **empty** trả về mảng String[] dài 0. **parallel** vẫn có thứ tự A, B, C do Stream.of có encounter order; việc xử lý có thể diễn ra trên nhiều luồng nhưng kết quả của toArray với nguồn có thứ tự phải giữ thứ tự đó.

## 5. Vì sao toArray() không tham số trả về Object[]?

Chữ **T** của **Stream<T>** là tham số generic. Generic của Java dùng *type erasure*; thư viện không thể tự suy ra một kiểu mảng runtime cụ thể chỉ dựa vào chữ T cho phiên bản không tham số. Hợp đồng API vì thế quy định rõ **Object[] toArray()** và mảng kết quả có thành phần runtime là Object.

~~~java
Object[] a = Stream.of("x", "y").toArray(); // Đúng
// String[] b = Stream.of("x", "y").toArray(); // Không biên dịch
~~~

Không sửa lỗi bằng cách ép kiểu trực tiếp:

~~~java
// Có thể biên dịch nhưng sẽ ném ClassCastException khi chạy:
String[] wrong = (String[]) Stream.of("x", "y").toArray();
~~~

Giải thích: **Object[]** chứa các đối tượng String không đồng nghĩa bản thân object mảng đó là **String[]**. Java kiểm tra kiểu runtime của mảng khi ép kiểu. Muốn kết quả typed, tạo đúng mảng ngay từ đầu:

~~~java
String[] correct = Stream.of("x", "y").toArray(String[]::new);
~~~

Nếu đã có Object[] và cần sao chép các phần tử tương thích sang String[], bạn có thể dùng **Arrays.copyOf(objects, objects.length, String[].class)**; tuy nhiên với pipeline mới, **toArray(String[]::new)** đơn giản và rõ nghĩa hơn.

## 6. Generator: kiểu, kích thước và trách nhiệm của hàm tạo mảng

Chữ ký của phiên bản typed:

~~~java
<A> A[] toArray(java.util.function.IntFunction<A[]> generator)
~~~

**IntFunction<A[]>** là hàm nhận một giá trị **int** chỉ kích thước mảng được yêu cầu và trả về mảng **A[]** có kích thước đó. Cách viết thông dụng:

~~~java
String[] first = Stream.of("a", "b").toArray(String[]::new);
String[] second = Stream.of("a", "b")
        .toArray(length -> new String[length]);
~~~

Hai dòng trên có cùng kiểu và nội dung kết quả. **String[]::new** ngắn gọn, thể hiện rõ kiểu runtime của mảng, và thường là lựa chọn ưu tiên.

Kiểu **A** không bắt buộc viết giống hệt chữ **T** trong **Stream<T>**, miễn mọi phần tử thực tế gán được vào mảng do generator tạo:

~~~java
CharSequence[] texts = Stream.of("a", "b")
        .toArray(CharSequence[]::new);

Number[] numbers = Stream.of(10, 20, 30)
        .toArray(Number[]::new);
~~~

- Stream<String> có thể tạo **CharSequence[]** vì String thực hiện giao diện CharSequence.
- Stream<Integer> có thể tạo **Number[]** vì Integer kế thừa Number.
- Khả năng gán tương thích áp dụng cho từng phần tử ở runtime, không phải phép chuyển đổi nội dung tự động: không thể yêu cầu **String[]** để Java tự biến số nguyên thành chuỗi.

**Lưu ý về cách gọi generator:** Trong quá trình thực thi phân đoạn hoặc phải cấp phát thêm, hệ thống có thể gọi generator nhiều lần với các kích thước khác nhau. Vì vậy, generator nên là hàm đơn giản, tạo một mảng mới đúng loại và đúng độ dài; không dựa vào việc nó chỉ chạy đúng một lần, không dùng side effect để đếm phần tử và không trả về một mảng dùng chung.

## 7. Mảng nguyên thủy và tránh boxing không cần thiết

Khi dữ liệu là số nguyên thủy, ưu tiên dùng đúng specialized stream:

~~~java
int[] scores = IntStream.of(7, 8, 9)
        .map(score -> score * 10)
        .toArray(); // int[]

long[] ids = java.util.stream.LongStream.rangeClosed(1L, 3L)
        .toArray(); // long[]

double[] averages = java.util.stream.DoubleStream.of(2.0, 3.5)
        .toArray(); // double[]
~~~

Phân biệt rõ:

| Pipeline | Kết quả | Đặc điểm |
| --- | --- | --- |
| IntStream.of(1, 2).toArray() | int[] | Phần tử nguyên thủy |
| IntStream.of(1, 2).boxed().toArray(Integer[]::new) | Integer[] | Đóng hộp mỗi int thành Integer |
| Stream.of(1, 2).toArray() | Object[] | Pipeline tham chiếu, mảng Object |
| Stream.of(1, 2).toArray(Integer[]::new) | Integer[] | Pipeline tham chiếu, kiểu mảng rõ ràng |

Không thể đổi **Integer[]** sang **int[]** chỉ bằng ép kiểu; đây là hai kiểu mảng khác nhau. Nếu đang có **Stream<Integer>** và muốn **int[]**, chuyển sang **IntStream** bằng **mapToInt**:

~~~java
List<Integer> values = Arrays.asList(3, 5, 8);
int[] primitive = values.stream()
        .mapToInt(Integer::intValue)
        .toArray();
~~~

Cách này giúp tránh mảng wrapper không cần thiết. **mapToInt(Integer::intValue)** sẽ ném NullPointerException nếu một phần tử Integer bằng null; nếu nguồn có thể chứa null, cần xác định quy tắc loại bỏ hoặc thay thế trước.

## 8. Những trường hợp lỗi phải nhận diện

### 8.1. Yêu cầu kiểu mảng không chứa được mọi phần tử

~~~java
// Ví dụ cố ý gây lỗi runtime:
Object[] source = {"a", 123};
String[] invalid = Arrays.stream(source).toArray(String[]::new);
~~~

**Kết quả:** ném **ArrayStoreException** vì Integer không gán được vào phần tử của String[]. Trong phiên bản typed, generics không phải là bảo đảm tự động chuyển đổi dữ liệu sang kiểu A. Muốn String[], hãy map dữ liệu trước một cách có chủ đích, chẳng hạn **map(String::valueOf)**, nếu yêu cầu nghiệp vụ là biểu diễn mọi giá trị dưới dạng chuỗi.

### 8.2. Nhầm toArray của Stream với toArray của Collection

~~~java
List<String> values = Arrays.asList("a", "b");
String[] fromList = values.toArray(new String[0]); // Collection API
String[] fromStream = values.stream().toArray(String[]::new); // Stream API
~~~

**List.toArray(T[] a)** và **Stream.toArray(IntFunction<A[]> generator)** là hai overload thuộc hai API khác nhau. Trên Stream, tham số phải là hàm tạo mảng; viết **stream.toArray(new String[0])** sẽ không biên dịch. Khi muốn dùng cú pháp giống nhau ở ví dụ, phải nhìn đúng kiểu biến và chữ ký phương thức.

### 8.3. Cố dùng lại stream đã kết thúc

~~~java
Stream<String> once = Stream.of("a", "b");
String[] first = once.toArray(String[]::new);
// Object[] second = once.toArray(); // Sai: stream đã tiêu thụ
~~~

Một stream được thiết kế để xử lý một lần. Hãy tạo stream mới từ nguồn khi cần thao tác tiếp. Một số implementation phát hiện tái sử dụng và ném **IllegalStateException**; không dựa vào khả năng phát hiện này như cơ chế quản lý luồng.

### 8.4. Mong chờ mảng luôn có phần tử hoặc không có null

~~~java
String[] noMatches = Stream.of("a", "b")
        .filter(s -> s.startsWith("z"))
        .toArray(String[]::new); // Mảng dài 0

String[] nullable = Stream.of("a", null, "b")
        .toArray(String[]::new); // Giữ phần tử null
~~~

**toArray** không tự loại null, không tự bỏ phần tử trùng lặp, cũng không tự sắp xếp. Các thay đổi đó phải được biểu diễn qua **filter**, **distinct**, **sorted**... trước terminal operation nếu thực sự cần.

## 9. Thứ tự dữ liệu và parallel stream

**Encounter order** là thứ tự mà nguồn và pipeline định nghĩa; ví dụ **List**, mảng và **Stream.of** là các nguồn có thứ tự. Đối với stream có encounter order, **toArray** trả phần tử theo thứ tự đó, kể cả khi pipeline dùng **parallel()**:

~~~java
String[] ordered = Stream.of("a", "b", "c", "d")
        .parallel()
        .filter(value -> !value.equals("b"))
        .toArray(String[]::new);
// ["a", "c", "d"]
~~~

Đừng nhầm thứ tự của **toArray** với thứ tự thực thi của từng thao tác: khi xử lý song song, các lambda có thể chạy trên các thread khác nhau, không theo thứ tự dễ quan sát. Không đặt logic phụ thuộc thứ tự side effect trong **map**, **filter** hoặc generator.

Một nguồn không có encounter order, chẳng hạn một số Set, hoặc pipeline chủ động gọi **unordered()**, không đảm bảo thứ tự phần tử trong mảng. Nếu cần thứ tự cụ thể, xác định tiêu chí và sử dụng **sorted(comparator)**, hoặc giữ nguồn vốn có thứ tự. Tránh phụ thuộc vào thứ tự tình cờ khi chạy thử.

Parallel stream không mặc nhiên nhanh hơn; hiệu quả phụ thuộc kích thước dữ liệu, chi phí xử lý, chi phí phân chia/gộp và môi trường. Chỉ dùng song song khi đã có lý do hoặc đo đạc phù hợp; **toArray** vẫn cần lưu toàn bộ kết quả cuối cùng.

## 10. Kích thước, bộ nhớ và nguồn vô hạn

- Mảng kết quả có **length** bằng số phần tử thực sự đi qua toàn bộ các phép trung gian, không nhất thiết bằng kích thước nguồn. Ví dụ filter có thể loại nhiều phần tử.
- Mảng có kích thước cố định sau khi được tạo. Nếu cần thêm/xóa phần tử linh hoạt, **List** thường phù hợp hơn; nếu cần mảng thì **toArray** là đích đến trực tiếp.
- **toArray** lưu toàn bộ kết quả vào bộ nhớ, tốn lượng bộ nhớ theo số phần tử; các mảng trung gian, boxing hoặc việc tính kích thước có thể tạo thêm chi phí. Đừng gọi nó trên tập dữ liệu quá lớn chỉ để xử lý lần lượt từng phần tử.
- Với stream vô hạn hoặc không kết thúc, terminal operation **toArray** không thể hoàn thành bình thường; giới hạn dữ liệu trước bằng **limit(n)** hoặc thiết kế nguồn hữu hạn.

Ví dụ có giới hạn:

~~~java
int[] firstFive = IntStream.iterate(1, n -> n + 1)
        .limit(5)
        .toArray(); // [1, 2, 3, 4, 5]
~~~

**limit** đảm bảo tối đa 5 phần tử ở ví dụ trên. Với nguồn đã có thứ tự, việc chọn phần tử cũng ổn định. Không bao giờ dùng **toArray** trên một pipeline vô hạn mà không có điều kiện kết thúc hữu hiệu.

## 11. Dùng toArray trong tình huống thực tế

### 11.1. Chuẩn bị tham số cho API nhận String[]

Giả sử ứng dụng nhận các mã định danh dưới dạng List<String> và API đích yêu cầu String[]:

~~~java
List<String> rawIds = Arrays.asList(" a01 ", "", " b02 ", "c03");
String[] ids = rawIds.stream()
        .map(String::trim)
        .filter(id -> !id.isEmpty())
        .toArray(String[]::new);
// ["a01", "b02", "c03"]
~~~

Pipeline làm rõ quy tắc dữ liệu trước khi chuyển kiểu. Giá trị phần tử vẫn là String, kết quả là **String[]** đúng chuẩn API cần nhận.

### 11.2. Biến đổi sang kiểu mới rồi tạo mảng kiểu mới

~~~java
List<String> digits = Arrays.asList("10", "20", "30");
Integer[] numbers = digits.stream()
        .map(Integer::parseInt)
        .toArray(Integer[]::new);
// [10, 20, 30]
~~~

**map(Integer::parseInt)** chuyển phần tử String thành Integer; **toArray(Integer[]::new)** quyết định kiểu mảng cuối. Nếu cần **int[]** và muốn dùng primitive stream, có thể thay hai bước cuối bằng **mapToInt(Integer::parseInt).toArray()**.

### 11.3. Khi nào chọn List thay cho array?

- Chọn **String[]/int[]** khi hợp đồng API, thuật toán hoặc yêu cầu lưu trữ cần mảng kiểu cụ thể.
- Chọn **List<String>** khi cần giao diện Collection, các phương thức thao tác tập hợp, hoặc cần chuyển giao một danh sách hơn là mảng.
- Trên **Java 16+**, **stream.toList()** trả List không hỗ trợ các thao tác sửa đổi như add/remove/set; muốn List có thể sửa, có thể dùng **collect(Collectors.toCollection(ArrayList::new))**. Không coi **toList()** là cách tạo mảng.
- Tránh chuyển **Stream -> List -> array** nếu bạn chỉ cần một mảng: hãy gọi **toArray(generator)** trực tiếp.

## 12. Các nhầm lẫn phổ biến và cách chọn đúng

| Tình huống | Cách làm đúng | Lý do |
| --- | --- | --- |
| Cần Object[] để chuyển giao các object bất kỳ | stream.toArray() | Phiên bản không tham số thực sự tạo Object[] |
| Cần String[] từ Stream<String> | stream.toArray(String[]::new) | Giữ đúng kiểu runtime của mảng |
| Cần Number[] từ các Integer | stream.toArray(Number[]::new) | Kiểu mảng cha chứa được Integer |
| Cần int[] từ các số nguyên | intStream.toArray() | Không tạo Integer[] |
| Cần int[] từ Stream<Integer> | stream.mapToInt(Integer::intValue).toArray() | Chuyển sang primitive stream |
| Cần phần tử xếp theo quy tắc | stream.sorted(...).toArray(...) | Xác định thứ tự trước terminal |
| Cần dữ liệu từ stream vô hạn | stream.limit(n).toArray(...) | Giới hạn số phần tử |
| Cần dùng lại dữ liệu cho phép toán khác | tạo một Stream mới từ nguồn | Stream đã kết thúc không dùng lại |

**Không nên:** ép **(String[]) stream.toArray()**; giả định **toArray(String[]::new)** tự chuyển mọi kiểu dữ liệu thành chuỗi; cho rằng **parallel()** làm thay đổi thứ tự của một ordered stream; tạo generator có side effect hoặc trả mảng sai độ dài.

## 13. Tự kiểm tra

**Câu 1.** Đoạn sau cho kết quả kiểu gì? Vì sao?

~~~java
var result = Stream.of("a", "b").toArray();
~~~

**Đáp án:** **Object[]**, cả kiểu suy luận cho biến **result** lẫn kiểu runtime của mảng. **var** không thay đổi chữ ký **Object[] toArray()**. Từ khóa **var** có từ Java 10; nếu viết mã thuần Java 8, khai báo biến là **Object[] result**.

**Câu 2.** Có List<Integer> gồm [2, 4, 6]. Hãy tạo int[] với mỗi phần tử gấp đôi.

~~~java
int[] doubled = Arrays.asList(2, 4, 6).stream()
        .mapToInt(Integer::intValue)
        .map(n -> n * 2)
        .toArray();
// [4, 8, 12]
~~~

**Câu 3.** Tại sao đoạn sau không đảm bảo chạy thành công?

~~~java
Stream<Object> mixed = Stream.of("ready", 42);
String[] values = mixed.toArray(String[]::new);
~~~

**Đáp án:** **toArray** phải chèn một Integer vào mảng String[] và sẽ ném **ArrayStoreException**. Nếu muốn chỉ lấy String, có thể dùng **filter(String.class::isInstance).map(String.class::cast).toArray(String[]::new)**; nếu muốn chuyển toàn bộ phần tử thành biểu diễn String, dùng phép chuyển đổi rõ ràng theo yêu cầu nghiệp vụ.

## 14. Tóm tắt cần nhớ

1. **toArray() trên Stream<T> -> Object[]**; kiểu T không quyết định kiểu mảng runtime.
2. **toArray(Type[]::new) -> Type[]**; generator nhận kích thước, có thể được gọi thêm khi xử lý phân đoạn, và mọi phần tử phải tương thích với Type.
3. **IntStream/LongStream/DoubleStream.toArray()** lần lượt cho **int[]/long[]/double[]**.
4. **toArray** kết thúc và tiêu thụ Stream; với ordered stream, kết quả giữ encounter order ngay cả khi chạy song song.
5. Mảng lưu toàn bộ kết quả, cần nguồn hữu hạn và đủ bộ nhớ; kết quả rỗng là mảng dài 0, phần tử null không tự bị loại.
6. Không ép kiểu Object[] thành String[]; hãy tạo đúng mảng ngay từ pipeline.

### Tài liệu API chính thức

- Java Stream, gồm hai chữ ký toArray và ngoại lệ ArrayStoreException: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/stream/Stream.html
- Java IntStream: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/stream/IntStream.html
- Java package java.util.stream, về tính lazy, encounter order và sử dụng stream một lần: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/stream/package-summary.html
